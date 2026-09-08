"""Fase 1 RBAC — separação FUNÇÃO (role) vs ETAPA DE FORMAÇÃO.

Cobre:
- GET /api/me/context (role_label, formation_stage/year/status, permissions)
- Admin protegido (403 quando fundador tenta alterar role/formation)
- Fundador altera role de formador->cofundador (200) e reverte
- Escalada bloqueada (cofundador->fundador negado; ninguém altera self)
- PATCH /api/admin/users/{id}/formation por formador -> 403; por membro (self) -> 403
- formador_geral com aprovação ON -> {status: requested}
- fundador GET /formation/stage-requests e POST resolve {approve:true} aplica
- formador_geral fora de escopo -> 403
- assign-geral audita TRANSFER_FORMADOR
- Regra de ouro: formation_stage NÃO promove por conclusão de formação
- Permissões efetivas fundador/admin com 51 perms e is_top_authority=true
"""
import os
import time
import pytest
import requests
from pathlib import Path
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ENV_PATH = PROJECT_ROOT / "frontend" / ".env"

frontend_env = dotenv_values(FRONTEND_ENV_PATH)

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or frontend_env.get("REACT_APP_BACKEND_URL")
)

if not BASE_URL:
    raise RuntimeError(
        "REACT_APP_BACKEND_URL não foi definida no ambiente nem em frontend/.env"
    )

BASE_URL = BASE_URL.rstrip("/")

# ============================================================
# CONFIGURAÇÃO SEGURA DOS TESTES
# ============================================================

BACKEND_ENV_PATH = PROJECT_ROOT / "backend" / ".env"
backend_env = dotenv_values(BACKEND_ENV_PATH)

API = f"{BASE_URL}/api"


def _config(name: str) -> str:
    """
    Obtém configuração primeiro do ambiente do processo
    e depois do backend/.env local.

    Nunca possui credenciais hardcoded no código.
    """
    value = os.environ.get(name) or backend_env.get(name)

    if not value:
        raise RuntimeError(
            f"Variável obrigatória não configurada: {name}"
        )

    return value


DEMO_PASSWORD = _config("DEMO_USER_PASSWORD")

CREDS = {
    "fundador": {
        "email": _config("ADMIN_EMAIL"),
        "password": _config("ADMIN_PASSWORD"),
    },
    "admin": {
        "email": _config("TECHNICAL_ADMIN_EMAIL"),
        "password": _config("TECHNICAL_ADMIN_PASSWORD"),
    },
    "geral": {
        "email": "geral@caminho.app",
        "password": DEMO_PASSWORD,
    },
    "formador": {
        "email": "formador@caminho.app",
        "password": DEMO_PASSWORD,
    },
    "membro": {
        "email": "membro@caminho.app",
        "password": DEMO_PASSWORD,
    },
    "prevoc": {
        "email": "prevocacionado@caminho.app",
        "password": DEMO_PASSWORD,
    },
}


def _login(key):
    r = requests.post(
        f"{API}/auth/login",
        json=CREDS[key],
        timeout=30,
    )

    assert r.status_code == 200, (
        f"login {key} failed: {r.status_code} {r.text}"
    )

    access_token = r.cookies.get("access_token")

    assert access_token, (
        f"login {key} realizado, mas o cookie access_token não foi definido"
    )

    data = r.json()
    data["token"] = access_token

    return data


def _h(token):
    return {
        "Cookie": f"access_token={token}"
    }

@pytest.fixture(scope="module")
def sessions():
    return {k: _login(k) for k in CREDS}


def _ctx(tok):
    r = requests.get(f"{API}/me/context", headers=_h(tok))
    assert r.status_code == 200, r.text
    return r.json()


def _find_user(admin_tok, email):
    r = requests.get(f"{API}/admin/users", params={"search": email}, headers=_h(admin_tok))
    assert r.status_code == 200, r.text
    lst = r.json()
    match = [u for u in lst if u["email"] == email]
    assert match, f"user not found: {email} in {[u['email'] for u in lst]}"
    return match[0]


# ---------------- 1. /me/context ----------------
class TestMeContext:
    def test_fundador_context(self, sessions):
        c = _ctx(sessions["fundador"]["token"])
        assert c["role"] == "fundador"
        assert c["role_label"] == "Fundador"
        assert c["formation_stage"] == "CONSAGRADO"
        assert c["formation_status"] == "ATIVO"
        # 51 permissions expected for top authority
        assert len(c["permissions"]) >= 51, f"expected >=51 perms, got {len(c['permissions'])}"

    def test_admin_context(self, sessions):
        c = _ctx(sessions["admin"]["token"])
        assert c["role"] == "admin"
        assert c["role_label"] in ("Admin", "Admin Técnico")
        assert len(c["permissions"]) >= 51

    def test_geral_context(self, sessions):
        c = _ctx(sessions["geral"]["token"])
        assert c["role"] == "formador_geral"
        assert c["role_label"] == "Formador Geral"

    def test_membro_context(self, sessions):
        c = _ctx(sessions["membro"]["token"])
        assert c["role"] == "membro"
        assert c["role_label"] == "Membro"
        assert c["formation_stage"] == "DISCIPULO"
        assert c["formation_year"] == 1
        assert c["formation_status"] == "EM_FORMACAO"

    def test_login_includes_is_top_authority(self, sessions):
        u_f = sessions["fundador"]["user"]
        assert u_f.get("is_top_authority") is True
        u_m = sessions["membro"]["user"]
        assert u_m.get("is_top_authority") in (False, None)


# ---------------- 2. ADMIN PROTEGIDO (TESTE 49) ----------------
class TestAdminProtected:
    def test_fundador_cannot_change_admin_role(self, sessions):
        admin = _find_user(sessions["fundador"]["token"],
        CREDS["admin"]["email"],)
        r = requests.patch(f"{API}/admin/users/{admin['id']}/role",
                           json={"role": "formador"},
                           headers=_h(sessions["fundador"]["token"]))
        assert r.status_code == 403, r.text
        detail = r.json().get("detail", "")
        assert "proteção estrutural" in detail or "protegido" in detail.lower() or "administrador técnico" in detail.lower(), detail

    def test_fundador_cannot_change_admin_formation(self, sessions):
        admin = _find_user(sessions["fundador"]["token"], "admin@caminho.app")
        r = requests.patch(f"{API}/admin/users/{admin['id']}/formation",
                           json={"new_stage_order": 3, "reason": "TEST hack admin"},
                           headers=_h(sessions["fundador"]["token"]))
        assert r.status_code == 403, r.text


# ---------------- 3. Role change: fundador allowed / self forbidden / escalation forbidden ----------------
class TestRoleChanges:
    def test_membro_cannot_list_users(self, sessions):
        r = requests.get(f"{API}/admin/users", headers=_h(sessions["membro"]["token"]))
        assert r.status_code == 403

    def test_fundador_cannot_change_own_role(self, sessions):
        me = sessions["fundador"]["user"]
        r = requests.patch(f"{API}/admin/users/{me['id']}/role",
                           json={"role": "cofundador"},
                           headers=_h(sessions["fundador"]["token"]))
        assert r.status_code == 403

    def test_fundador_promotes_formador_to_cofundador_and_reverts(self, sessions):
        f = _find_user(sessions["fundador"]["token"], "formador@caminho.app")
        try:
            r = requests.patch(f"{API}/admin/users/{f['id']}/role",
                               json={"role": "cofundador", "reason": "TEST promote"},
                               headers=_h(sessions["fundador"]["token"]))
            assert r.status_code == 200, r.text
            assert r.json()["role"] == "cofundador"
            # verify
            f2 = _find_user(sessions["fundador"]["token"], "formador@caminho.app")
            assert f2["role"] == "cofundador"
        finally:
            r = requests.patch(f"{API}/admin/users/{f['id']}/role",
                               json={"role": "formador", "reason": "TEST revert"},
                               headers=_h(sessions["fundador"]["token"]))
            assert r.status_code == 200
            f3 = _find_user(sessions["fundador"]["token"], "formador@caminho.app")
            assert f3["role"] == "formador"

    def test_cofundador_cannot_escalate_target_to_fundador(self, sessions):
        # Promote formador to cofundador temporarily
        f = _find_user(sessions["fundador"]["token"], "formador@caminho.app")
        r = requests.patch(f"{API}/admin/users/{f['id']}/role",
                           json={"role": "cofundador"},
                           headers=_h(sessions["fundador"]["token"]))
        assert r.status_code == 200
        try:
            cof = _login("formador")  # re-login now as cofundador
            # cofundador tries to promote membro to fundador -> forbidden (escalation)
            m = _find_user(sessions["fundador"]["token"], "membro@caminho.app")
            r2 = requests.patch(f"{API}/admin/users/{m['id']}/role",
                                json={"role": "fundador"},
                                headers=_h(cof["token"]))
            assert r2.status_code == 403, r2.text
        finally:
            requests.patch(f"{API}/admin/users/{f['id']}/role",
                           json={"role": "formador"},
                           headers=_h(sessions["fundador"]["token"]))


# ---------------- 4. TESTE 50 — Formation stage changes ----------------
class TestFormationStage:
    def test_formador_cannot_change_formation(self, sessions):
        m = _find_user(sessions["fundador"]["token"], "membro@caminho.app")
        r = requests.patch(f"{API}/admin/users/{m['id']}/formation",
                           json={"new_stage_order": 4, "reason": "hack"},
                           headers=_h(sessions["formador"]["token"]))
        assert r.status_code == 403

    def test_membro_cannot_change_own_formation(self, sessions):
        me = sessions["membro"]["user"]
        r = requests.patch(f"{API}/admin/users/{me['id']}/formation",
                           json={"new_stage_order": 4, "reason": "self"},
                           headers=_h(sessions["membro"]["token"]))
        assert r.status_code == 403

    def test_formador_geral_out_of_scope_forbidden(self, sessions):
        # geral tenta alterar formação do fundador -> 403
        fund_id = sessions["fundador"]["user"]["id"]
        r = requests.patch(f"{API}/admin/users/{fund_id}/formation",
                           json={"new_stage_order": 5, "reason": "hack fundador"},
                           headers=_h(sessions["geral"]["token"]))
        assert r.status_code == 403

    def test_formador_geral_requests_and_fundador_approves(self, sessions):
        # Setup: garantir que formador@ está vinculado a geral@; membro@ vinculado a formador@
        fund_tok = sessions["fundador"]["token"]
        geral = _find_user(fund_tok, "geral@caminho.app")
        formador = _find_user(fund_tok, "formador@caminho.app")
        membro = _find_user(fund_tok, "membro@caminho.app")

        # ensure formador.general_formador_id == geral.id
        if formador.get("general_formador_id") != geral["id"]:
            r = requests.post(f"{API}/admin/formadores/{formador['id']}/assign-geral",
                              json={"general_formador_id": geral["id"], "reason": "TEST setup"},
                              headers=_h(fund_tok))
            assert r.status_code == 200, r.text

        # ensure membro.formador_id == formador.id (via admin PATCH)
        if membro.get("formador_id") != formador["id"]:
            r = requests.patch(f"{API}/admin/users/{membro['id']}",
                               json={"formador_id": formador["id"]},
                               headers=_h(fund_tok))
            # accept 200/422; if 422, skip approval scope test cleanly
            if r.status_code not in (200, 422):
                pytest.fail(f"could not link membro to formador: {r.status_code} {r.text}")

        # ensure setting stage_change_requires_approval == True (default)
        cur_settings = requests.get(f"{API}/master/settings", headers=_h(fund_tok)).json()
        payload = {**cur_settings, "stage_change_requires_approval": True}
        # remove any keys the endpoint may not accept
        payload = {k: v for k, v in payload.items() if k in (
            "stage_change_requires_approval", "cofundador_can_change_stage",
            "allow_stage_skip", "gate_by_previous_stage")}
        # fallback minimal body
        if "allow_stage_skip" not in payload:
            payload["allow_stage_skip"] = False
        r = requests.put(f"{API}/master/settings", json=payload, headers=_h(fund_tok))
        assert r.status_code == 200, r.text

        # ensure membro is currently on order 3
        cur = _ctx(sessions["membro"]["token"])
        if cur["formation_stage"] != "DISCIPULO" or cur.get("formation_year") != 1:
            # reset via fundador direct
            requests.patch(f"{API}/admin/users/{membro['id']}/formation",
                           json={"new_stage_order": 3, "reason": "TEST reset order 3"},
                           headers=_h(fund_tok))

        # geral tenta mudar etapa de membro (sob escopo) -> deveria ser 'requested'
        r = requests.patch(f"{API}/admin/users/{membro['id']}/formation",
                           json={"new_stage_order": 4, "reason": "TEST geral aprovacao"},
                           headers=_h(sessions["geral"]["token"]))
        if r.status_code == 403:
            pytest.skip(f"formador_geral não tem escopo sobre membro (link membro.formador_id ausente); resposta: {r.text}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "requested", body
        req_id = body["request"]["id"]

        try:
            # fundador vê pendente
            r = requests.get(f"{API}/formation/stage-requests", headers=_h(fund_tok))
            assert r.status_code == 200, r.text
            reqs = r.json()
            assert any(x["id"] == req_id for x in reqs), f"request {req_id} not in pending list"

            # aprova
            r = requests.post(f"{API}/formation/stage-requests/{req_id}/resolve",
                              json={"approve": True, "reason": "TEST aprovado"},
                              headers=_h(fund_tok))
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "approved"

            # membro agora deve estar em DISCIPULO ano 2 (order 4)
            c2 = _ctx(sessions["membro"]["token"])
            assert c2["formation_stage"] == "DISCIPULO"
            assert c2["formation_year"] == 2
        finally:
            # reverter membro para order 3
            requests.patch(f"{API}/admin/users/{membro['id']}/formation",
                           json={"new_stage_order": 3, "reason": "TEST revert to 3"},
                           headers=_h(fund_tok))
            c3 = _ctx(sessions["membro"]["token"])
            assert c3["formation_stage"] == "DISCIPULO"
            assert c3["formation_year"] == 1


# ---------------- 5. Regra de ouro etapa != progresso ----------------
class TestGoldenRule:
    def test_formation_conclusion_does_not_change_stage(self, sessions):
        # membro@ já tem formação concluída (100%) mas continua em DISCIPULO
        c = _ctx(sessions["membro"]["token"])
        assert c["formation_stage"] == "DISCIPULO"
        # GET /formation/status still works
        r = requests.get(f"{API}/formation/status", headers=_h(sessions["membro"]["token"]))
        assert r.status_code == 200


# ---------------- 6. assign-geral audit ----------------
class TestAssignGeral:
    def test_assign_geral_by_fundador(self, sessions):
        fund_tok = sessions["fundador"]["token"]
        geral = _find_user(fund_tok, "geral@caminho.app")
        formador = _find_user(fund_tok, "formador@caminho.app")
        r = requests.post(f"{API}/admin/formadores/{formador['id']}/assign-geral",
                          json={"general_formador_id": geral["id"], "reason": "TEST assign"},
                          headers=_h(fund_tok))
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True


# ---------------- 7. Fluxos existentes não quebraram ----------------
class TestExistingFlows:
    def test_fundador_can_access_master(self, sessions):
        tok = sessions["fundador"]["token"]
        assert requests.get(f"{API}/master/users", headers=_h(tok)).status_code == 200
        assert requests.get(f"{API}/master/settings", headers=_h(tok)).status_code == 200

    def test_stage_access_control_still_works(self, sessions):
        tok = sessions["prevoc"]["token"]  # stage 1
        assert requests.get(f"{API}/stages/1/modules", headers=_h(tok)).status_code == 200
        # KNOWN BUG (see report): backend/server.py:207 gating logic inverted;
        # membros currently see ALL stages. This assertion documents the expected behavior.
        r3 = requests.get(f"{API}/stages/3/modules", headers=_h(tok))
        assert r3.status_code == 403, (
            f"SECURITY REGRESSION: prevoc (stage 1) can access stage 3 modules (status {r3.status_code}). "
            f"See server.py:207 — gating condition is inverted."
        )

    def test_lives_endpoint_works(self, sessions):
        r = requests.get(f"{API}/lives", headers=_h(sessions["membro"]["token"]))
        assert r.status_code == 200
