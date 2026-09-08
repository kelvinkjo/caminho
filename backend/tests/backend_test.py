"""CAMINHO backend tests — Master (Login Mestre) stage-control rules.

REGRA INVIOLÁVEL: apenas o Login Mestre (role 'mestre', permissão MANAGE_FORMATION_STAGE)
altera/mantém a etapa de formação. Concluir a formação NUNCA promove o usuário.
"""
import os
from pathlib import Path
import pytest
import requests
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]

FRONTEND_ENV_PATH = PROJECT_ROOT / "frontend" / ".env"
BACKEND_ENV_PATH = PROJECT_ROOT / "backend" / ".env"

frontend_env = dotenv_values(FRONTEND_ENV_PATH)
backend_env = dotenv_values(BACKEND_ENV_PATH)

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or frontend_env.get("REACT_APP_BACKEND_URL")
)

if not BASE_URL:
    raise RuntimeError(
        "REACT_APP_BACKEND_URL não foi definida no ambiente nem em frontend/.env"
    )

BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"


def _config(name: str) -> str:
    value = os.environ.get(name) or backend_env.get(name)

    if not value:
        raise RuntimeError(
            f"Variável obrigatória não configurada: {name}"
        )

    return value


TEST_DEMO_PASSWORD = _config("DEMO_USER_PASSWORD")

# Nome MESTRE mantido temporariamente para compatibilidade com a suíte antiga.
# Na arquitetura atual, o Fundador exerce essa autoridade institucional.
MESTRE = {
    "email": _config("ADMIN_EMAIL"),
    "password": _config("ADMIN_PASSWORD"),
}

ADMIN = {
    "email": _config("TECHNICAL_ADMIN_EMAIL"),
    "password": _config("TECHNICAL_ADMIN_PASSWORD"),
}

FORMADOR = {
    "email": "formador@caminho.app",
    "password": TEST_DEMO_PASSWORD,
}

MEMBRO = {
    "email": "membro@caminho.app",
    "password": TEST_DEMO_PASSWORD,
}

def _login(creds):
    email = creds["email"]

    r = requests.post(
        f"{API}/auth/login",
        json={
            "email": email,
            "password": creds["password"],
        },
        timeout=30,
    )

    if r.status_code != 200:
        pytest.fail(
            f"login failed for {email}: {r.status_code} {r.text}",
            pytrace=False,
        )

    data = r.json()
    access_token = r.cookies.get("access_token")

    # Compatibilidade com os testes existentes.
    # A autenticação real agora usa o cookie HttpOnly.
    data["token"] = access_token

    return data

def _h(token):
    return {"Cookie": f"access_token={token}"}


@pytest.fixture(scope="session")
def mestre_s():
    return _login(MESTRE)


@pytest.fixture(scope="session")
def admin_s():
    return _login(ADMIN)


@pytest.fixture(scope="session")
def formador_s():
    return _login(FORMADOR)


@pytest.fixture(scope="session")
def membro_s():
    return _login(MEMBRO)


def _me(token):
    return requests.get(f"{API}/auth/me", headers=_h(token)).json()


def _reset_membro_to_stage_3(mestre_token, membro_id):
    """Ensure membro is on stage 3 for tests that require it."""
    cur = requests.get(f"{API}/master/users/{membro_id}", headers=_h(mestre_token)).json()
    if cur["current_stage_order"] != 3:
        r = requests.post(f"{API}/master/users/{membro_id}/stage",
                          json={"new_stage_order": 3, "reason": "TEST reset to stage 3", "action": "change"},
                          headers=_h(mestre_token))
        assert r.status_code == 200


# ---------------- AUTH sanity ----------------
class TestAuth:
    def test_login_roles(self):
        assert _login(MESTRE)["user"]["role"] == "fundador"
        assert _login(ADMIN)["user"]["role"] == "admin"
        assert _login(FORMADOR)["user"]["role"] == "formador"
        assert _login(MEMBRO)["user"]["role"] == "membro"

    def test_bad_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": MEMBRO["email"], "password": "wrong"})
        assert r.status_code == 401

    def test_me_no_token(self):
        assert requests.get(f"{API}/auth/me").status_code == 401


# ---------------- TESTE 1 — Conclusão NÃO promove ----------------
class TestConclusionDoesNotPromote:
    def test_formation_status_concluded_but_stage_unchanged(self, membro_s, mestre_s):
        # reset membro to stage 3 first
        me = _me(membro_s["token"])
        _reset_membro_to_stage_3(mestre_s["token"], me["id"])

        # Complete all lessons of stage 3
        mods = requests.get(f"{API}/stages/3/modules", headers=_h(membro_s["token"])).json()
        for m in mods["modules"]:
            for l in m["lessons"]:
                requests.post(f"{API}/lessons/{l['id']}/progress",
                              json={"completed": True, "percent": 100}, headers=_h(membro_s["token"]))

        # Confirm mandatory live presence if there is one
        buckets = requests.get(f"{API}/lives", headers=_h(membro_s["token"])).json()
        for k in buckets:
            for l in buckets[k]:
                if l.get("stage_order") == 3 and l.get("required"):
                    requests.post(f"{API}/lives/{l['id']}/presence",
                                  json={"percent": 100}, headers=_h(membro_s["token"]))

        fs = requests.get(f"{API}/formation/status", headers=_h(membro_s["token"]))
        assert fs.status_code == 200
        d = fs.json()
        assert d["concluded"] is True, f"expected concluded=true, got {d}"
        assert d["percent"] == 100

        # Stage must remain 3
        me2 = _me(membro_s["token"])
        assert me2["current_stage_order"] == 3, f"conclusão NÃO deve promover; stage={me2['current_stage_order']}"


# ---------------- TESTE 2 — Mestre mantém etapa (MAINTAIN_STAGE) ----------------
class TestMasterMaintain:
    def test_maintain_stage(self, mestre_s, membro_s):
        me = _me(membro_s["token"])
        _reset_membro_to_stage_3(mestre_s["token"], me["id"])
        prev_stage = 3

        # empty reason must fail
        r_bad = requests.post(f"{API}/master/users/{me['id']}/stage",
                              json={"action": "maintain", "reason": "   "}, headers=_h(mestre_s["token"]))
        assert r_bad.status_code == 400

        r = requests.post(f"{API}/master/users/{me['id']}/stage",
                          json={"action": "maintain", "reason": "TEST manter etapa 3"},
                          headers=_h(mestre_s["token"]))
        assert r.status_code == 200, r.text
        log = r.json()["log"]
        assert log["change_type"] == "MAINTAIN_STAGE"
        assert log["previous_stage"] == prev_stage
        assert log["new_stage"] == prev_stage
        assert log["reason"] == "TEST manter etapa 3"

        # user still at same stage
        me2 = _me(membro_s["token"])
        assert me2["current_stage_order"] == prev_stage

        # history has MAINTAIN_STAGE
        det = requests.get(f"{API}/master/users/{me['id']}", headers=_h(mestre_s["token"])).json()
        assert any(h["change_type"] == "MAINTAIN_STAGE" and h["reason"] == "TEST manter etapa 3" for h in det["history"])


# ---------------- TESTE 3 — Mestre muda etapa (ADVANCEMENT + RETROCESSION) ----------------
class TestMasterChange:
    def test_advance_then_retrocede(self, mestre_s, membro_s):
        me = _me(membro_s["token"])
        _reset_membro_to_stage_3(mestre_s["token"], me["id"])

        # advance to 4
        r = requests.post(f"{API}/master/users/{me['id']}/stage",
                          json={"new_stage_order": 4, "reason": "TEST avançar", "action": "change"},
                          headers=_h(mestre_s["token"]))
        assert r.status_code == 200
        assert r.json()["log"]["change_type"] == "ADVANCEMENT"

        det = requests.get(f"{API}/master/users/{me['id']}", headers=_h(mestre_s["token"])).json()
        assert det["current_stage_order"] == 4

        me_now = _me(membro_s["token"])
        assert me_now["current_stage_order"] == 4

        # retrocede back to 3
        r2 = requests.post(f"{API}/master/users/{me['id']}/stage",
                           json={"new_stage_order": 3, "reason": "TEST voltar", "action": "change"},
                           headers=_h(mestre_s["token"]))
        assert r2.status_code == 200
        assert r2.json()["log"]["change_type"] == "RETROCESSION"
        assert _me(membro_s["token"])["current_stage_order"] == 3

    def test_invalid_stage_rejected(self, mestre_s, membro_s):
        me = _me(membro_s["token"])
        r = requests.post(f"{API}/master/users/{me['id']}/stage",
                          json={"new_stage_order": 9, "reason": "x", "action": "change"},
                          headers=_h(mestre_s["token"]))
        assert r.status_code == 400


# ---------------- TESTE 4 — Formador NÃO altera etapa ----------------
class TestFormadorCannotChangeStage:
    @pytest.mark.parametrize("path,method", [
        ("/master/users", "GET"),
        ("/master/recommendations", "GET"),
        ("/master/settings", "GET"),
    ])
    def test_formador_forbidden_master(self, formador_s, path, method):
        r = requests.request(method, f"{API}{path}", headers=_h(formador_s["token"]))
        assert r.status_code == 403

    def test_formador_forbidden_master_stage_post(self, formador_s, membro_s):
        me = _me(membro_s["token"])
        r = requests.post(f"{API}/master/users/{me['id']}/stage",
                          json={"new_stage_order": 5, "reason": "x", "action": "change"},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 403

    def test_formador_recommend_empty_justification_400(self, formador_s, membro_s):
        me = _me(membro_s["token"])
        r = requests.post(f"{API}/formador/recommend",
                          json={"user_id": me["id"], "recommended_stage_order": 4, "justification": "   "},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 400

    def test_formador_can_recommend(self, formador_s, membro_s):
        me = _me(membro_s["token"])
        r = requests.post(f"{API}/formador/recommend",
                          json={"user_id": me["id"], "recommended_stage_order": 4,
                                "justification": "TEST justificativa"},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        # visible to formador
        recs = requests.get(f"{API}/formador/recommendations", headers=_h(formador_s["token"])).json()
        assert any(x["user_id"] == me["id"] and x["status"] == "pending" for x in recs)


# ---------------- TESTE 5 — Usuário comum NÃO altera etapa; admin patch removed field ----------------
class TestMembroAdminCannotChangeStage:
    @pytest.mark.parametrize("path", ["/master/users", "/master/recommendations", "/master/settings"])
    def test_membro_forbidden(self, membro_s, path):
        r = requests.get(f"{API}{path}", headers=_h(membro_s["token"]))
        assert r.status_code == 403

    def test_admin_can_access_master(self, admin_s):
        assert requests.get(
            f"{API}/master/users",
            headers=_h(admin_s["token"]),
        ).status_code == 200

        assert requests.get(
            f"{API}/master/recommendations",
            headers=_h(admin_s["token"]),
        ).status_code == 200

    def test_admin_patch_ignores_current_stage_order(self, admin_s, membro_s, mestre_s):
        me = _me(membro_s["token"])
        _reset_membro_to_stage_3(mestre_s["token"], me["id"])
        # Try to change via admin PATCH — server model has NO current_stage_order (extra field ignored by Pydantic).
        r = requests.patch(f"{API}/admin/users/{me['id']}",
                           json={"current_stage_order": 6},
                           headers=_h(admin_s["token"]))
        # Endpoint may accept (200) but must ignore the field
        assert r.status_code in (200, 422)
        me2 = _me(membro_s["token"])
        assert me2["current_stage_order"] == 3, "admin PATCH must NOT change stage"


# ---------------- TESTE 6 — Acesso a etapa superior bloqueado ----------------
class TestStageAccessControl:
    def test_lower_stages_accessible(self, membro_s, mestre_s):
        me = _me(membro_s["token"])
        _reset_membro_to_stage_3(mestre_s["token"], me["id"])
        for order in (1, 2, 3):
            r = requests.get(f"{API}/stages/{order}/modules", headers=_h(membro_s["token"]))
            assert r.status_code == 200, f"stage {order} should be accessible"

    def test_higher_stages_blocked(self, membro_s, mestre_s):
        me = _me(membro_s["token"])
        _reset_membro_to_stage_3(mestre_s["token"], me["id"])
        for order in (4, 5, 6):
            r = requests.get(f"{API}/stages/{order}/modules", headers=_h(membro_s["token"]))
            assert r.status_code == 403, f"stage {order} should be 403"

    def test_higher_stage_lesson_blocked(self, membro_s, mestre_s):
        me = _me(membro_s["token"])
        _reset_membro_to_stage_3(mestre_s["token"], me["id"])
        # find a stage-4/5/6 lesson via mestre view
        for target in (4, 5, 6):
            mods = requests.get(f"{API}/stages/{target}/modules", headers=_h(mestre_s["token"])).json()
            if mods.get("modules") and mods["modules"][0].get("lessons"):
                lid = mods["modules"][0]["lessons"][0]["id"]
                r = requests.get(f"{API}/lessons/{lid}", headers=_h(membro_s["token"]))
                assert r.status_code == 403
                return
        pytest.skip("no seeded lesson above stage 3 to exercise block")


# ---------------- TESTE 7 & 8 — Histórico & Manutenção registrados ----------------
class TestAuditLog:
    def test_history_contains_change_and_maintain(self, mestre_s, membro_s):
        me = _me(membro_s["token"])
        _reset_membro_to_stage_3(mestre_s["token"], me["id"])

        # change (already covered in reset if it was different; do explicit maintain + change)
        r_m = requests.post(f"{API}/master/users/{me['id']}/stage",
                            json={"action": "maintain", "reason": "TEST audit maintain"},
                            headers=_h(mestre_s["token"]))
        assert r_m.status_code == 200

        r_c = requests.post(f"{API}/master/users/{me['id']}/stage",
                            json={"new_stage_order": 4, "reason": "TEST audit advance", "action": "change"},
                            headers=_h(mestre_s["token"]))
        assert r_c.status_code == 200

        # roll back for other tests
        requests.post(f"{API}/master/users/{me['id']}/stage",
                      json={"new_stage_order": 3, "reason": "TEST audit rollback", "action": "change"},
                      headers=_h(mestre_s["token"]))

        det = requests.get(f"{API}/master/users/{me['id']}", headers=_h(mestre_s["token"])).json()
        hist = det["history"]
        assert len(hist) >= 3
        # each entry must have required fields
        for entry in hist[:3]:
            for k in ("previous_stage", "new_stage", "changed_by_name", "changed_at", "reason", "change_type"):
                assert k in entry and entry[k] not in (None, ""), f"missing/empty {k} in {entry}"

        change_types = [h["change_type"] for h in hist]
        assert "MAINTAIN_STAGE" in change_types
        assert "ADVANCEMENT" in change_types or "RETROCESSION" in change_types

    def test_reason_required(self, mestre_s, membro_s):
        me = _me(membro_s["token"])
        r = requests.post(f"{API}/master/users/{me['id']}/stage",
                          json={"new_stage_order": 4, "reason": "", "action": "change"},
                          headers=_h(mestre_s["token"]))
        assert r.status_code == 400


# ---------------- RECOMMENDATION FLOW ----------------
class TestRecommendationFlow:
    def test_full_cycle_accept(self, mestre_s, formador_s, membro_s):
        me = _me(membro_s["token"])
        _reset_membro_to_stage_3(mestre_s["token"], me["id"])

        # formador recommends stage 4
        rec_r = requests.post(f"{API}/formador/recommend",
                              json={"user_id": me["id"], "recommended_stage_order": 4,
                                    "justification": "TEST accept flow"},
                              headers=_h(formador_s["token"]))
        assert rec_r.status_code == 200
        rec_id = rec_r.json()["recommendation"]["id"]

        # master sees it
        pending = requests.get(f"{API}/master/recommendations", headers=_h(mestre_s["token"])).json()
        assert any(p["id"] == rec_id for p in pending)

        # accept
        res = requests.post(f"{API}/master/recommendations/{rec_id}/resolve",
                            json={"accept": True, "reason": "TEST aceitar"},
                            headers=_h(mestre_s["token"]))
        assert res.status_code == 200
        assert res.json()["status"] == "accepted"

        # stage applied
        me2 = _me(membro_s["token"])
        assert me2["current_stage_order"] == 4

        # log created
        det = requests.get(f"{API}/master/users/{me['id']}", headers=_h(mestre_s["token"])).json()
        assert any(h["change_type"] == "ADVANCEMENT" for h in det["history"])

        # rollback
        requests.post(f"{API}/master/users/{me['id']}/stage",
                      json={"new_stage_order": 3, "reason": "TEST rollback", "action": "change"},
                      headers=_h(mestre_s["token"]))

    def test_reject_does_not_apply(self, mestre_s, formador_s, membro_s):
        me = _me(membro_s["token"])
        _reset_membro_to_stage_3(mestre_s["token"], me["id"])

        rec_r = requests.post(f"{API}/formador/recommend",
                              json={"user_id": me["id"], "recommended_stage_order": 5,
                                    "justification": "TEST reject flow"},
                              headers=_h(formador_s["token"]))
        rec_id = rec_r.json()["recommendation"]["id"]

        res = requests.post(f"{API}/master/recommendations/{rec_id}/resolve",
                            json={"accept": False, "reason": "TEST recusar"},
                            headers=_h(mestre_s["token"]))
        assert res.status_code == 200
        assert res.json()["status"] == "rejected"

        assert _me(membro_s["token"])["current_stage_order"] == 3

        # formador sees status rejected
        recs = requests.get(f"{API}/formador/recommendations", headers=_h(formador_s["token"])).json()
        target = next((r for r in recs if r["id"] == rec_id), None)
        assert target is not None
        assert target["status"] == "rejected"


# ---------------- ADMIN role gating ----------------
class TestAdminRoleGating:
    def test_admin_can_access_admin(self, admin_s):
        assert requests.get(f"{API}/admin/stats", headers=_h(admin_s["token"])).status_code == 200
        assert requests.get(f"{API}/admin/users", headers=_h(admin_s["token"])).status_code == 200

    def test_admin_can_access_master(self, admin_s):
        assert requests.get(f"{API}/master/users", headers=_h(admin_s["token"])).status_code == 200

    def test_mestre_can_access_both(self, mestre_s):
        assert requests.get(f"{API}/admin/stats", headers=_h(mestre_s["token"])).status_code == 200
        assert requests.get(f"{API}/master/users", headers=_h(mestre_s["token"])).status_code == 200


# ---------------- NOTIFICATIONS ----------------
class TestNotifications:
    def test_notifications_created_on_change(self, mestre_s, formador_s, membro_s):
        me = _me(membro_s["token"])
        _reset_membro_to_stage_3(mestre_s["token"], me["id"])

        # ensure formador is linked (check formador/people includes membro)
        people = requests.get(f"{API}/formador/people", headers=_h(formador_s["token"])).json()
        linked = any(p["email"] == MEMBRO["email"] for p in people)

        # Perform a stage change
        r = requests.post(f"{API}/master/users/{me['id']}/stage",
                          json={"new_stage_order": 4, "reason": "TEST notify", "action": "change"},
                          headers=_h(mestre_s["token"]))
        assert r.status_code == 200

        # user gets notification
        notifs = requests.get(f"{API}/notifications", headers=_h(membro_s["token"])).json()
        assert any("TEST" not in n["title"] and "etapa" in (n["title"] + n["body"]).lower() for n in notifs), \
            f"membro should have a stage notification. Got: {[n['title'] for n in notifs[:5]]}"

        # formador also receives one when linked
        if linked:
            fn = requests.get(f"{API}/notifications", headers=_h(formador_s["token"])).json()
            assert len(fn) >= 1

        # rollback
        requests.post(f"{API}/master/users/{me['id']}/stage",
                      json={"new_stage_order": 3, "reason": "TEST rollback notify", "action": "change"},
                      headers=_h(mestre_s["token"]))


# ---------------- Stage hierarchy for other demo users ----------------
STAGE_USERS = [
    ("prevocacionado@caminho.app", 1),
    ("vocacionado@caminho.app", 2),
    ("discipulo2@caminho.app", 4),
    ("compromissado@caminho.app", 5),
    ("consagrado@caminho.app", 6),
]


class TestStageHierarchy:
    @pytest.mark.parametrize("email,expected", STAGE_USERS)
    def test_stage(self, email, expected):
        d = _login({"email": email, "password": TEST_DEMO_PASSWORD})
        me = _me(d["token"])
        assert me["current_stage_order"] == expected
        for order in range(1, expected + 1):
            assert requests.get(f"{API}/stages/{order}/modules", headers=_h(d["token"])).status_code == 200
        for order in range(expected + 1, 7):
            assert requests.get(f"{API}/stages/{order}/modules", headers=_h(d["token"])).status_code == 403


# ---------------- ITERATION 5: Requisitos Configuráveis ----------------
class TestStageRequirements:
    def test_get_requirements_defaults(self, mestre_s):
        r = requests.get(f"{API}/master/stage-requirements", headers=_h(mestre_s["token"]))
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 6
        for s in data:
            assert "order" in s and "require_lessons" in s and "require_mandatory_lives" in s

    @pytest.mark.parametrize("role_key", ["formador_s", "membro_s"])
    def test_non_master_forbidden(self, request, role_key):
        s = request.getfixturevalue(role_key)
        r = requests.get(f"{API}/master/stage-requirements", headers=_h(s["token"]))
        assert r.status_code == 403
        r2 = requests.put(f"{API}/master/stage-requirements/3",
                          json={"require_lessons": False, "require_mandatory_lives": False},
                          headers=_h(s["token"]))
        assert r2.status_code == 403

    def test_toggle_affects_formation_status_but_not_stage(self, mestre_s, membro_s):
        me = _me(membro_s["token"])
        _reset_membro_to_stage_3(mestre_s["token"], me["id"])
        stage_before = me["current_stage_order"]

        # First reset progress by getting current status
        fs_before = requests.get(f"{API}/formation/status", headers=_h(membro_s["token"])).json()

        # Toggle both requirements OFF for stage 3
        r = requests.put(f"{API}/master/stage-requirements/3",
                        json={"require_lessons": False, "require_mandatory_lives": False},
                        headers=_h(mestre_s["token"]))
        assert r.status_code == 200

        try:
            fs_after = requests.get(f"{API}/formation/status", headers=_h(membro_s["token"])).json()
            # with both off, concluded must be True regardless
            assert fs_after["concluded"] is True
            assert fs_after["requirements"]["require_lessons"] is False
            assert fs_after["requirements"]["require_mandatory_lives"] is False

            # Stage MUST NOT change
            me_after = _me(membro_s["token"])
            assert me_after["current_stage_order"] == stage_before, "requisitos toggle NÃO deve mudar etapa"
        finally:
            # Restore defaults
            requests.put(f"{API}/master/stage-requirements/3",
                        json={"require_lessons": True, "require_mandatory_lives": True},
                        headers=_h(mestre_s["token"]))


# ---------------- ITERATION 5: Passaporte da Jornada ----------------
class TestPassport:
    def test_get_passport_structure(self, membro_s):
        r = requests.get(f"{API}/passport", headers=_h(membro_s["token"]))
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 8
        assert len(data["items"]) == 8
        for item in data["items"]:
            for k in ("key", "title", "icon", "description", "earned", "awarded_at"):
                assert k in item

    def test_passport_available_to_any_user(self, formador_s, admin_s, mestre_s):
        for s in (formador_s, admin_s, mestre_s):
            r = requests.get(f"{API}/passport", headers=_h(s["token"]))
            assert r.status_code == 200

    def test_master_grants_milestone(self, mestre_s, membro_s):
        me = _me(membro_s["token"])
        r = requests.post(f"{API}/master/users/{me['id']}/passport/primeiro_retiro",
                        headers=_h(mestre_s["token"]))
        assert r.status_code == 200
        p = requests.get(f"{API}/passport", headers=_h(membro_s["token"])).json()
        retiro = next(i for i in p["items"] if i["key"] == "primeiro_retiro")
        assert retiro["earned"] is True
        assert retiro["awarded_at"] is not None

    def test_master_grant_invalid_key(self, mestre_s, membro_s):
        me = _me(membro_s["token"])
        r = requests.post(f"{API}/master/users/{me['id']}/passport/does_not_exist",
                        headers=_h(mestre_s["token"]))
        assert r.status_code == 404

    def test_non_master_cannot_grant(self, formador_s, membro_s):
        me = _me(membro_s["token"])
        r = requests.post(f"{API}/master/users/{me['id']}/passport/primeiro_retiro",
                        headers=_h(formador_s["token"]))
        assert r.status_code == 403

    def test_lesson_completion_awards_milestone(self, membro_s, mestre_s):
        me = _me(membro_s["token"])
        _reset_membro_to_stage_3(mestre_s["token"], me["id"])
        # complete some lesson
        mods = requests.get(f"{API}/stages/3/modules", headers=_h(membro_s["token"])).json()
        if mods.get("modules") and mods["modules"][0].get("lessons"):
            lid = mods["modules"][0]["lessons"][0]["id"]
            requests.post(f"{API}/lessons/{lid}/progress",
                        json={"completed": True, "percent": 100}, headers=_h(membro_s["token"]))
            p = requests.get(f"{API}/passport", headers=_h(membro_s["token"])).json()
            pf = next(i for i in p["items"] if i["key"] == "primeira_formacao")
            assert pf["earned"] is True


# ---------------- ITERATION 5: Relatório Pastoral ----------------
class TestPastoralReport:
    def test_pastoral_report_shape(self, mestre_s, membro_s):
        me = _me(membro_s["token"])
        _reset_membro_to_stage_3(mestre_s["token"], me["id"])
        # Ensure membro is concluded (complete all stage 3 lessons + lives)
        mods = requests.get(f"{API}/stages/3/modules", headers=_h(membro_s["token"])).json()
        for m in mods["modules"]:
            for l in m["lessons"]:
                requests.post(f"{API}/lessons/{l['id']}/progress",
                            json={"completed": True, "percent": 100}, headers=_h(membro_s["token"]))
        buckets = requests.get(f"{API}/lives", headers=_h(membro_s["token"])).json()
        for k in buckets:
            for l in buckets[k]:
                if l.get("stage_order") == 3 and l.get("required"):
                    requests.post(f"{API}/lives/{l['id']}/presence",
                                json={"percent": 100}, headers=_h(membro_s["token"]))

        r = requests.get(f"{API}/master/pastoral-report", headers=_h(mestre_s["token"]))
        assert r.status_code == 200
        data = r.json()
        assert "by_stage" in data and "awaiting" in data
        assert "awaiting_count" in data and "total_membros" in data
        assert isinstance(data["by_stage"], list)
        for b in data["by_stage"]:
            for k in ("order", "stage", "total", "concluded"):
                assert k in b
        # membro should appear in awaiting (100% stage 3)
        assert any(a["id"] == me["id"] for a in data["awaiting"]), \
            f"membro should be in awaiting: {[a['name'] for a in data['awaiting']]}"
        member = next(a for a in data["awaiting"] if a["id"] == me["id"])
        assert member["order"] == 3
        assert "formador" in member
        assert data["awaiting_count"] == len(data["awaiting"])

    @pytest.mark.parametrize("role_key", ["formador_s", "membro_s"])
    def test_non_master_forbidden(self, request, role_key):
        s = request.getfixturevalue(role_key)
        r = requests.get(f"{API}/master/pastoral-report", headers=_h(s["token"]))
        assert r.status_code == 403


# ---------------- ITERATION 5: Notificações Central ----------------
class TestNotificationsCentral:
    def test_get_notifications_returns_list(self, membro_s):
        r = requests.get(f"{API}/notifications", headers=_h(membro_s["token"]))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_mark_read(self, mestre_s, membro_s):
        me = _me(membro_s["token"])
        _reset_membro_to_stage_3(mestre_s["token"], me["id"])
        # Trigger a notification via stage change
        requests.post(f"{API}/master/users/{me['id']}/stage",
                    json={"new_stage_order": 4, "reason": "TEST notif central", "action": "change"},
                    headers=_h(mestre_s["token"]))
        try:
            before = requests.get(f"{API}/notifications", headers=_h(membro_s["token"])).json()
            assert len(before) >= 1
            unread_before = sum(1 for n in before if not n.get("read"))
            assert unread_before >= 1

            r = requests.post(f"{API}/notifications/read", headers=_h(membro_s["token"]))
            assert r.status_code == 200

            after = requests.get(f"{API}/notifications", headers=_h(membro_s["token"])).json()
            unread_after = sum(1 for n in after if not n.get("read"))
            assert unread_after == 0
        finally:
            requests.post(f"{API}/master/users/{me['id']}/stage",
                        json={"new_stage_order": 3, "reason": "TEST rollback", "action": "change"},
                        headers=_h(mestre_s["token"]))

    def test_notifications_ordered_desc(self, membro_s):
        items = requests.get(f"{API}/notifications", headers=_h(membro_s["token"])).json()
        if len(items) >= 2:
            for i in range(len(items) - 1):
                assert items[i].get("at", "") >= items[i + 1].get("at", ""), "must be sorted desc by at"

class TestAISmoke:
    def test_assistant_responds(self, membro_s):
        llm_key = (
            os.environ.get("EMERGENT_LLM_KEY")
            or backend_env.get("EMERGENT_LLM_KEY")
        )

        if not llm_key:
            pytest.skip(
                "Integração de IA não configurada: EMERGENT_LLM_KEY ausente."
            )

        r = requests.post(
            f"{API}/assistant/ask",
            json={"question": "O que é a Eucaristia?"},
            headers=_h(membro_s["token"]),
            timeout=90,
        )

        assert r.status_code == 200
        assert len(r.json().get("answer", "")) > 20

# ---------------- ITERATION 6 — GRANULAR PERMISSIONS / CONTENT / LIVES ----------------
PREVOC = {
    "email": "prevocacionado@caminho.app",
    "password": TEST_DEMO_PASSWORD,
}

DEMO_FORMADOR_PERMS = [
    "CREATE_COURSE", "CREATE_MODULE", "CREATE_LESSON", "PUBLISH_LESSON",
    "UPLOAD_VIDEO", "UPLOAD_AUDIO", "UPLOAD_DOCUMENT",
    "CREATE_ANNOUNCEMENT", "DELETE_ANNOUNCEMENT",
    "CREATE_LIVE", "EDIT_LIVE", "START_LIVE", "END_LIVE", "MODERATE_LIVE",
    "VIEW_ANALYTICS",
]


@pytest.fixture(scope="session")
def prevoc_s():
    return _login(PREVOC)


def _get_formador_perms(mestre_token, fid):
    r = requests.get(f"{API}/master/formadores-permissions", headers=_h(mestre_token))
    for f in r.json():
        if f["id"] == fid:
            return f["permissions"]
    return []


def _set_perms(mestre_token, fid, perms):
    r = requests.put(f"{API}/master/formadores/{fid}/permissions",
                     json={"permissions": perms}, headers=_h(mestre_token))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def formador_id(formador_s):
    return _me(formador_s["token"])["id"]


@pytest.fixture(scope="session")
def restore_formador_perms(mestre_s, formador_id):
    """Snapshot demo formador perms; restore on teardown."""
    original = _get_formador_perms(mestre_s["token"], formador_id)
    yield original
    _set_perms(mestre_s["token"], formador_id, original or DEMO_FORMADOR_PERMS)


# ------ TESTE 1 & 2: create_course permission gating ------
class TestCoursesPermission:
    def test_membro_cannot_create_course(self, membro_s):
        r = requests.post(f"{API}/courses",
                          json={"title": "TEST curso membro", "stages": [3], "publish": True},
                          headers=_h(membro_s["token"]))
        assert r.status_code == 403

    def test_formador_authorized_creates_course(self, formador_s):
        r = requests.post(f"{API}/courses",
                          json={"title": "TEST curso formador", "stages": [3], "publish": True},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert "id" in data
        assert data["title"] == "TEST curso formador"
        assert data["status"] == "published"

    def test_formador_without_create_course_denied(self, mestre_s, formador_s, formador_id, restore_formador_perms):
        # revoke CREATE_COURSE
        reduced = [p for p in restore_formador_perms if p != "CREATE_COURSE"]
        _set_perms(mestre_s["token"], formador_id, reduced)
        # re-login so JWT/user fetched again picks up perms (backend reads DB each request via get_current_user)
        tok = _login(FORMADOR)["token"]
        r = requests.post(f"{API}/courses",
                          json={"title": "TEST denied", "stages": [3], "publish": True},
                          headers=_h(tok))
        assert r.status_code == 403
        # restore
        _set_perms(mestre_s["token"], formador_id, restore_formador_perms)


# ------ TESTE 3 & 4: ownership + EDIT_ALL_CONTENT ------
class TestLessonOwnershipEdit:
    def _create_second_formador(self, admin_s, mestre_s):
        """Promote prevocacionado -> formador (using admin PATCH). Returns (user_id, login token)."""
        # find prevoc user
        users = requests.get(f"{API}/admin/users", headers=_h(admin_s["token"])).json()
        u = next(x for x in users if x["email"] == PREVOC["email"])
        original_role = u["role"]
        original_stage = u["current_stage_order"]
        # promote
        r = requests.patch(f"{API}/admin/users/{u['id']}",
                          json={"role": "formador"}, headers=_h(admin_s["token"]))
        assert r.status_code == 200
        return u["id"], original_role, original_stage

    def _restore_user(self, admin_s, mestre_s, uid, original_role, original_stage):
        requests.patch(f"{API}/admin/users/{uid}",
                       json={"role": original_role}, headers=_h(admin_s["token"]))
        # if the user was a membro, ensure stage restored via mestre (should not have changed but be safe)
        if original_role == "membro":
            _reset = requests.get(f"{API}/master/users/{uid}", headers=_h(mestre_s["token"])).json()
            if _reset.get("current_stage_order") != original_stage:
                requests.post(f"{API}/master/users/{uid}/stage",
                              json={"new_stage_order": original_stage, "reason": "TEST restore", "action": "change"},
                              headers=_h(mestre_s["token"]))
        # clear permissions we added
        requests.put(f"{API}/master/formadores/{uid}/permissions",
                     json={"permissions": []}, headers=_h(mestre_s["token"]))

    def test_ownership_and_edit_all_content(self, admin_s, mestre_s, formador_s, formador_id, restore_formador_perms):
        # ensure a module exists (created by demo formador with CREATE_MODULE)
        mod = requests.post(f"{API}/modules",
                            json={"stage_order": 3, "title": "TEST mod owner", "description": ""},
                            headers=_h(formador_s["token"]))
        assert mod.status_code == 200, mod.text
        module_id = mod.json()["id"]

        # create lesson owned by demo formador
        les = requests.post(f"{API}/lessons",
                            json={"module_id": module_id, "title": "TEST aula owner",
                                  "stage_order": 3, "publish": True},
                            headers=_h(formador_s["token"]))
        assert les.status_code == 200, les.text
        lesson_id = les.json()["id"]

        # create second formador
        uid, orig_role, orig_stage = self._create_second_formador(admin_s, mestre_s)
        try:
            # grant only EDIT_LESSON (NOT EDIT_ALL_CONTENT)
            _set_perms(mestre_s["token"], uid, ["EDIT_LESSON"])
            tok2 = _login(PREVOC)["token"]

            # TESTE 3: edit denied (owner mismatch, no EDIT_ALL_CONTENT)
            r = requests.patch(f"{API}/lessons/{lesson_id}",
                               json={"title": "TEST hijack"}, headers=_h(tok2))
            assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text}"

            # TESTE 4: grant EDIT_ALL_CONTENT
            _set_perms(mestre_s["token"], uid, ["EDIT_LESSON", "EDIT_ALL_CONTENT"])
            tok2 = _login(PREVOC)["token"]
            r2 = requests.patch(f"{API}/lessons/{lesson_id}",
                                json={"title": "TEST edited by other"}, headers=_h(tok2))
            assert r2.status_code == 200, r2.text
        finally:
            self._restore_user(admin_s, mestre_s, uid, orig_role, orig_stage)


# ------ TESTE 5, 6, 13: Lives lifecycle ------
class TestLivesLifecycle:
    def test_create_live_without_start_perm_cannot_start(self, mestre_s, formador_s, formador_id, restore_formador_perms):
        # grant CREATE_LIVE but remove START_LIVE
        perms = [p for p in restore_formador_perms if p != "START_LIVE"]
        if "CREATE_LIVE" not in perms:
            perms.append("CREATE_LIVE")
        _set_perms(mestre_s["token"], formador_id, perms)
        tok = _login(FORMADOR)["token"]
        try:
            r = requests.post(f"{API}/lives",
                              json={"title": "TEST live no-start", "stages": [3]},
                              headers=_h(tok))
            assert r.status_code == 200, r.text
            lid = r.json()["id"]
            s = requests.post(f"{API}/lives/{lid}/start", headers=_h(tok))
            assert s.status_code == 403
        finally:
            _set_perms(mestre_s["token"], formador_id, restore_formador_perms)

    def test_start_and_end_live(self, mestre_s, formador_s, membro_s, prevoc_s, restore_formador_perms, formador_id):
        # ensure demo perms
        _set_perms(mestre_s["token"], formador_id, restore_formador_perms)
        tok = _login(FORMADOR)["token"]

        # create stage-3 live
        r = requests.post(f"{API}/lives",
                          json={"title": "TEST live stage3", "stages": [3], "presenter": "Maria"},
                          headers=_h(tok))
        assert r.status_code == 200
        lid = r.json()["id"]

        # membro (stage3) baseline notifications count
        n_before = len(requests.get(f"{API}/notifications", headers=_h(membro_s["token"])).json())

        # start
        s = requests.post(f"{API}/lives/{lid}/start", headers=_h(tok))
        assert s.status_code == 200, s.text
        assert s.json()["status"] == "live"

        # TESTE 9: stage-1 member does NOT see this live in any bucket
        buckets_prevoc = requests.get(f"{API}/lives", headers=_h(prevoc_s["token"])).json()
        all_ids_prevoc = [x["id"] for k in ("live_now", "upcoming", "recorded") for x in buckets_prevoc.get(k, [])]
        assert lid not in all_ids_prevoc

        # TESTE 10: stage-3 member sees it in live_now
        buckets_membro = requests.get(f"{API}/lives", headers=_h(membro_s["token"])).json()
        assert any(x["id"] == lid for x in buckets_membro["live_now"])

        # notification created for stage-3 members
        notes = requests.get(f"{API}/notifications", headers=_h(membro_s["token"])).json()
        assert len(notes) > n_before
        assert any("Ao vivo" in (n.get("title", "") + n.get("body", "")) for n in notes[:5])

        # end
        e = requests.post(f"{API}/lives/{lid}/end", headers=_h(tok))
        assert e.status_code == 200, e.text

        # verify status ended
        buckets_after = requests.get(f"{API}/lives", headers=_h(tok))
        assert buckets_after.status_code == 200
        found = None
        for k in ("live_now", "upcoming", "recorded"):
            for x in buckets_after.json().get(k, []):
                if x["id"] == lid:
                    found = x
                    break
        assert found is not None
        assert found["status"] == "ended"
        # duration_min may be 0 (started/ended in the same minute) but must be an int if present
        if found.get("duration_min") is not None:
            assert isinstance(found["duration_min"], int)


# ------ TESTE 7 & 8: stage invariant ------
class TestStageInvariant:
    def test_formador_cannot_change_stage(self, formador_s, membro_s):
        me = _me(membro_s["token"])
        before = me["current_stage_order"]
        r = requests.post(f"{API}/master/users/{me['id']}/stage",
                          json={"new_stage_order": 5, "reason": "hack", "action": "change"},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 403
        # unchanged
        after = _me(membro_s["token"])["current_stage_order"]
        assert after == before

    def test_mestre_stage_change_requires_reason(self, mestre_s, membro_s):
        me = _me(membro_s["token"])
        _reset_membro_to_stage_3(mestre_s["token"], me["id"])
        # empty reason -> 400/422
        r = requests.post(f"{API}/master/users/{me['id']}/stage",
                          json={"new_stage_order": 4, "reason": "", "action": "change"},
                          headers=_h(mestre_s["token"]))
        assert r.status_code in (400, 422), f"expected 4xx got {r.status_code}"

        # valid change
        r2 = requests.post(f"{API}/master/users/{me['id']}/stage",
                           json={"new_stage_order": 4, "reason": "TEST invariant", "action": "change"},
                           headers=_h(mestre_s["token"]))
        assert r2.status_code == 200
        # rollback
        requests.post(f"{API}/master/users/{me['id']}/stage",
                      json={"new_stage_order": 3, "reason": "TEST rollback", "action": "change"},
                      headers=_h(mestre_s["token"]))


# ------ Permissions Management endpoints ------
class TestPermissionsMgmt:
    def test_list_formadores_permissions_master_only(self, mestre_s, formador_s, membro_s):
        r_m = requests.get(f"{API}/master/formadores-permissions", headers=_h(mestre_s["token"]))
        assert r_m.status_code == 200
        assert isinstance(r_m.json(), list) and len(r_m.json()) >= 1
        # non-master denied
        assert requests.get(f"{API}/master/formadores-permissions", headers=_h(formador_s["token"])).status_code == 403
        assert requests.get(f"{API}/master/formadores-permissions", headers=_h(membro_s["token"])).status_code == 403

    def test_put_permissions_master_only(self, mestre_s, formador_s, membro_s, formador_id, restore_formador_perms):
        # invalid perm string is filtered out (kept only if in ALL_PERMISSIONS)
        r = requests.put(f"{API}/master/formadores/{formador_id}/permissions",
                         json={"permissions": ["CREATE_COURSE", "NOT_A_REAL_PERM"]},
                         headers=_h(mestre_s["token"]))
        assert r.status_code == 200
        assert set(r.json()["permissions"]) == {"CREATE_COURSE"}

        # non-master denied
        assert requests.put(f"{API}/master/formadores/{formador_id}/permissions",
                            json={"permissions": []}, headers=_h(formador_s["token"])).status_code == 403
        assert requests.put(f"{API}/master/formadores/{formador_id}/permissions",
                            json={"permissions": []}, headers=_h(membro_s["token"])).status_code == 403

        # restore
        _set_perms(mestre_s["token"], formador_id, restore_formador_perms)


# ------ Announcements ------
class TestAnnouncements:
    def test_create_and_list_and_stage_filter(self, mestre_s, formador_s, membro_s, prevoc_s, formador_id, restore_formador_perms):
        _set_perms(mestre_s["token"], formador_id, restore_formador_perms)
        tok = _login(FORMADOR)["token"]
        r = requests.post(f"{API}/announcements",
                          json={"title": "TEST aviso stage3", "message": "Somente etapa 3",
                                "stages": [3], "publish": True},
                          headers=_h(tok))
        assert r.status_code == 200, r.text
        aid = r.json()["id"]

        # stage 3 member sees it
        m3 = requests.get(f"{API}/announcements", headers=_h(membro_s["token"])).json()
        assert any(a["id"] == aid for a in m3)

        # stage 1 member does NOT see it
        m1 = requests.get(f"{API}/announcements", headers=_h(prevoc_s["token"])).json()
        assert not any(a["id"] == aid for a in m1)

    def test_member_cannot_create_announcement(self, membro_s):
        r = requests.post(f"{API}/announcements",
                          json={"title": "TEST hack", "message": "no", "publish": True},
                          headers=_h(membro_s["token"]))
        assert r.status_code == 403



# ------ Central de Mídia Externa (iteration 7) ------
class TestMediaParse:
    def test_parse_youtube_watch(self, formador_s):
        r = requests.post(f"{API}/media/parse",
                          json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["provider"] == "youtube"
        assert j["external_id"] == "dQw4w9WgXcQ"
        assert j["embed_url"] == "https://www.youtube.com/embed/dQw4w9WgXcQ"
        assert j["watch_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert j["can_embed"] is True

    def test_parse_youtube_short(self, formador_s):
        r = requests.post(f"{API}/media/parse",
                          json={"url": "https://youtu.be/dQw4w9WgXcQ"},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 200
        assert r.json()["external_id"] == "dQw4w9WgXcQ"

    def test_parse_youtube_live(self, formador_s):
        r = requests.post(f"{API}/media/parse",
                          json={"url": "https://www.youtube.com/live/abcdefghijk"},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 200
        assert r.json()["provider"] == "youtube"
        assert r.json()["external_id"] == "abcdefghijk"

    def test_parse_vimeo(self, formador_s):
        r = requests.post(f"{API}/media/parse",
                          json={"url": "https://vimeo.com/76979871"},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 200
        j = r.json()
        assert j["provider"] == "vimeo"
        assert j["external_id"] == "76979871"
        assert j["embed_url"] == "https://player.vimeo.com/video/76979871"

    def test_parse_vimeo_player(self, formador_s):
        r = requests.post(f"{API}/media/parse",
                          json={"url": "https://player.vimeo.com/video/76979871"},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 200
        assert r.json()["external_id"] == "76979871"

    def test_parse_invalid_url(self, formador_s):
        r = requests.post(f"{API}/media/parse", json={"url": "not-a-url"},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 400
        assert "inválida" in r.json().get("detail", "").lower()

    def test_parse_unsupported_provider(self, formador_s):
        r = requests.post(f"{API}/media/parse",
                          json={"url": "https://www.dailymotion.com/video/x7tgad0"},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 400
        assert "não suportado" in r.json().get("detail", "").lower() or "nao suportado" in r.json().get("detail", "").lower()

    def test_parse_forbidden_for_member(self, membro_s):
        r = requests.post(f"{API}/media/parse",
                          json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
                          headers=_h(membro_s["token"]))
        assert r.status_code == 403


class TestExternalMediaCRUDAndAccess:
    def test_create_and_stage_access_control(self, formador_s, prevoc_s, mestre_s):
        # Use prevoc (stable stage 1) as the "member" subject to avoid races with
        # TestMasterChange that toggles membro's stage in parallel workers.
        prevoc_tok = prevoc_s["token"]
        # Formador creates stage-1 restricted VIDEO
        r = requests.post(f"{API}/external-media", headers=_h(formador_s["token"]),
                          json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaaa",
                                "title": "TEST midia etapa1 video", "kind": "video",
                                "stages": [1], "publish": True})
        assert r.status_code == 200, r.text
        mid_stage1 = r.json()["id"]
        assert r.json()["provider"] == "youtube"
        assert r.json()["stages"] == [1]

        # Formador creates a stage-3 restricted VIDEO
        r = requests.post(f"{API}/external-media", headers=_h(formador_s["token"]),
                          json={"url": "https://youtu.be/bbbbbbbbbbb",
                                "title": "TEST midia etapa3 video", "kind": "video",
                                "stages": [3], "publish": True})
        assert r.status_code == 200, r.text
        mid_stage3 = r.json()["id"]

        # LIST — prevoc (etapa 1) should see stage1 but NOT stage3
        lst = requests.get(f"{API}/external-media", headers=_h(prevoc_tok)).json()
        ids = {x["id"] for x in lst}
        assert mid_stage1 in ids
        assert mid_stage3 not in ids

        # GET detail: prevoc on stage3 media -> 403
        r = requests.get(f"{API}/external-media/{mid_stage3}", headers=_h(prevoc_tok))
        assert r.status_code == 403

        # GET detail: prevoc on stage1 media -> 200 + history registered
        r = requests.get(f"{API}/external-media/{mid_stage1}", headers=_h(prevoc_tok))
        assert r.status_code == 200
        assert r.json()["id"] == mid_stage1
        hist = requests.get(f"{API}/external-media/history", headers=_h(prevoc_tok)).json()
        assert any(h["id"] == mid_stage1 for h in hist)

        # Favorite toggle
        r = requests.post(f"{API}/external-media/{mid_stage1}/favorite", headers=_h(prevoc_tok))
        assert r.status_code == 200 and r.json()["favorited"] is True
        favs = requests.get(f"{API}/external-media/favorites", headers=_h(prevoc_tok)).json()
        assert any(f["id"] == mid_stage1 for f in favs)
        r = requests.post(f"{API}/external-media/{mid_stage1}/favorite", headers=_h(prevoc_tok))
        assert r.json()["favorited"] is False

        # Prevoc (membro) cannot favorite stage3 media (403)
        r = requests.post(f"{API}/external-media/{mid_stage3}/favorite", headers=_h(prevoc_tok))
        assert r.status_code == 403

        # Cleanup
        for x in (mid_stage1, mid_stage3):
            requests.delete(f"{API}/external-media/{x}", headers=_h(formador_s["token"]))

    def test_live_status_lifecycle_and_notify(self, formador_s, membro_s):
        # Create a live for stage 3
        r = requests.post(f"{API}/external-media", headers=_h(formador_s["token"]),
                          json={"url": "https://www.youtube.com/live/liveid00001"[:47],
                                "title": "TEST live externa",
                                "kind": "live", "stages": [3],
                                "live_status": "scheduled", "publish": True})
        if r.status_code != 200:
            r = requests.post(f"{API}/external-media", headers=_h(formador_s["token"]),
                              json={"url": "https://www.youtube.com/live/lllllllllll",
                                    "title": "TEST live externa",
                                    "kind": "live", "stages": [3],
                                    "live_status": "scheduled", "publish": True})
        assert r.status_code == 200, r.text
        lid = r.json()["id"]

        # Invalid status
        r = requests.post(f"{API}/external-media/{lid}/live-status",
                          json={"live_status": "bogus"}, headers=_h(formador_s["token"]))
        assert r.status_code == 400

        # Go live -> should notify stage-3 members
        r = requests.post(f"{API}/external-media/{lid}/live-status",
                          json={"live_status": "live"}, headers=_h(formador_s["token"]))
        assert r.status_code == 200 and r.json()["live_status"] == "live"

        notifs = requests.get(f"{API}/notifications", headers=_h(membro_s["token"])).json()
        assert any("ao vivo" in (n.get("title", "") + n.get("message", "")).lower() for n in notifs)

        # Membro cannot change live status
        r = requests.post(f"{API}/external-media/{lid}/live-status",
                          json={"live_status": "ended"}, headers=_h(membro_s["token"]))
        assert r.status_code == 403

        # End
        r = requests.post(f"{API}/external-media/{lid}/live-status",
                          json={"live_status": "ended"}, headers=_h(formador_s["token"]))
        assert r.status_code == 200

        requests.delete(f"{API}/external-media/{lid}", headers=_h(formador_s["token"]))

    def test_providers_endpoints(self, mestre_s, membro_s):
        r = requests.get(f"{API}/media/providers", headers=_h(membro_s["token"]))
        assert r.status_code == 200
        keys = {p["key"] for p in r.json()["providers"]}
        assert {"youtube", "vimeo"} <= keys

        # Only mestre can set providers
        r = requests.put(f"{API}/master/media/providers",
                         json={"enabled": ["youtube", "vimeo"]},
                         headers=_h(membro_s["token"]))
        assert r.status_code in (401, 403)

        r = requests.put(f"{API}/master/media/providers",
                         json={"enabled": ["youtube", "vimeo"]},
                         headers=_h(mestre_s["token"]))
        assert r.status_code == 200
        assert set(r.json()["enabled"]) == {"youtube", "vimeo"}


# ---------------- ITERATION 8 — CENTRAL DE TRANSMISSÃO (LiveKit não configurado) ----------------
NEW_LIVE_PERMS = {"MANAGE_LIVE", "MANAGE_CAMERA", "MANAGE_MICROPHONE",
                  "MANAGE_SCENES", "MANAGE_SOURCES", "VIEW_LIVE_ANALYTICS", "TAKE_OVER_LIVE"}


class TestLiveKitStatusAndPermissions:
    def test_livekit_status_not_configured(self, membro_s):
        r = requests.get(f"{API}/livekit/status", headers=_h(membro_s["token"]))
        assert r.status_code == 200
        data = r.json()
        assert data == {"configured": False}, data

    def test_livekit_status_requires_auth(self):
        assert requests.get(f"{API}/livekit/status").status_code == 401

    def test_permissions_catalog_has_new_live_perms(self, formador_s):
        r = requests.get(f"{API}/permissions/catalog", headers=_h(formador_s["token"]))
        assert r.status_code == 200
        perms = set(r.json()["permissions"])
        missing = NEW_LIVE_PERMS - perms
        assert not missing, f"missing perms: {missing}"


def _ensure_prevoc_stage_1(mestre_token):
    prevoc = _login(PREVOC)
    if prevoc["user"]["current_stage_order"] != 1:
        r = requests.post(f"{API}/master/users/{prevoc['user']['id']}/stage",
                          json={"new_stage_order": 1, "reason": "TEST reset to stage 1", "action": "change"},
                          headers=_h(mestre_token))
        assert r.status_code == 200


class TestBroadcastCRUDAndAccess:
    def test_member_cannot_create_broadcast(self, membro_s):
        r = requests.post(f"{API}/broadcasts",
                          json={"title": "TEST membro cria", "stages": [3]},
                          headers=_h(membro_s["token"]))
        assert r.status_code == 403

    def test_formador_creates_broadcast(self, formador_s, mestre_s):
        r = requests.post(f"{API}/broadcasts",
                          json={"title": "TEST_BC formador cria", "description": "d", "stages": [3], "mode": "simple"},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["title"] == "TEST_BC formador cria"
        assert b["stages"] == [3]
        assert b["status"] in ("scheduled", "created", "idle")  # default before start
        assert "id" in b and "room_name" in b
        # persistence via GET
        r2 = requests.get(f"{API}/broadcasts/{b['id']}", headers=_h(formador_s["token"]))
        assert r2.status_code == 200
        assert r2.json()["id"] == b["id"]
        # cleanup via mestre (MANAGE_LIVE)
        requests.delete(f"{API}/broadcasts/{b['id']}", headers=_h(mestre_s["token"]))

    def test_get_broadcast_stage_forbidden(self, formador_s, mestre_s):
        _ensure_prevoc_stage_1(mestre_s["token"])
        r = requests.post(f"{API}/broadcasts",
                          json={"title": "TEST_BC restrita etapa3", "stages": [3]},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 200
        bid = r.json()["id"]
        try:
            prevoc = _login(PREVOC)
            g = requests.get(f"{API}/broadcasts/{bid}", headers=_h(prevoc["token"]))
            assert g.status_code == 403
        finally:
            requests.delete(f"{API}/broadcasts/{bid}", headers=_h(mestre_s["token"]))

    def test_list_filters_by_stage_and_status(self, formador_s, membro_s, mestre_s):
        # create two broadcasts: one for stage 3 (visible to membro), one for stage 5 (not)
        r1 = requests.post(f"{API}/broadcasts",
                           json={"title": "TEST_BC list-visible", "stages": [3]},
                           headers=_h(formador_s["token"]))
        r2 = requests.post(f"{API}/broadcasts",
                           json={"title": "TEST_BC list-hidden", "stages": [5]},
                           headers=_h(formador_s["token"]))
        assert r1.status_code == 200 and r2.status_code == 200
        b1, b2 = r1.json(), r2.json()
        try:
            # start b1 so it becomes 'live' and is visible to membro (scheduled/live only)
            s = requests.post(f"{API}/broadcasts/{b1['id']}/start", headers=_h(formador_s["token"]))
            assert s.status_code == 200, s.text
            # membro list
            lst = requests.get(f"{API}/broadcasts", headers=_h(membro_s["token"])).json()
            ids = {b["id"] for b in lst}
            assert b1["id"] in ids, "membro (etapa 3) deveria ver broadcast live etapa 3"
            assert b2["id"] not in ids, "membro (etapa 3) NÃO deveria ver broadcast etapa 5"
            # staff (formador) vê ambos
            lst_staff = requests.get(f"{API}/broadcasts", headers=_h(formador_s["token"])).json()
            ids_staff = {b["id"] for b in lst_staff}
            assert {b1["id"], b2["id"]} <= ids_staff
        finally:
            requests.post(f"{API}/broadcasts/{b1['id']}/end", headers=_h(formador_s["token"]))
            requests.delete(f"{API}/broadcasts/{b1['id']}", headers=_h(mestre_s["token"]))
            requests.delete(f"{API}/broadcasts/{b2['id']}", headers=_h(mestre_s["token"]))


class TestBroadcastLifecycleAndNotify:
    def test_start_notifies_stage_members_and_end_calculates_duration(self, formador_s, membro_s, mestre_s):
        _reset_membro_to_stage_3(mestre_s["token"], _me(membro_s["token"])["id"])
        r = requests.post(f"{API}/broadcasts",
                          json={"title": "TEST_BC start-notify", "stages": [3]},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 200
        bid = r.json()["id"]
        try:
            # Snapshot notifications count for membro
            n0 = requests.get(f"{API}/notifications", headers=_h(membro_s["token"])).json()
            titles_before = [n.get("title", "") for n in n0]

            s = requests.post(f"{API}/broadcasts/{bid}/start", headers=_h(formador_s["token"]))
            assert s.status_code == 200, s.text
            assert s.json()["status"] == "live"

            # broadcast status
            g = requests.get(f"{API}/broadcasts/{bid}", headers=_h(formador_s["token"])).json()
            assert g["status"] == "live"

            # notification arrived
            import time
            time.sleep(0.4)
            n1 = requests.get(f"{API}/notifications", headers=_h(membro_s["token"])).json()
            found = any("Estamos ao vivo" in (n.get("title", "") + n.get("body", "")) for n in n1)
            assert found, f"esperava notificação '🔴 Estamos ao vivo!' — recebidas: {[n.get('title') for n in n1[:5]]}"

            # end
            e = requests.post(f"{API}/broadcasts/{bid}/end", headers=_h(formador_s["token"]))
            assert e.status_code == 200
            body = e.json()
            assert body["status"] == "ended"
            assert body.get("duration_min") is not None
            assert isinstance(body["duration_min"], int)
        finally:
            requests.delete(f"{API}/broadcasts/{bid}", headers=_h(mestre_s["token"]))

    def test_token_returns_503_when_livekit_not_configured(self, formador_s, mestre_s):
        r = requests.post(f"{API}/broadcasts",
                          json={"title": "TEST_BC token503", "stages": [3]},
                          headers=_h(formador_s["token"]))
        bid = r.json()["id"]
        try:
            requests.post(f"{API}/broadcasts/{bid}/start", headers=_h(formador_s["token"]))
            t = requests.post(f"{API}/broadcasts/{bid}/token", headers=_h(formador_s["token"]))
            assert t.status_code == 503, t.text
            data = t.json()
            # não pode vazar segredo em nenhum lugar da resposta
            raw = t.text.lower()
            assert "secret" not in raw and "api_secret" not in raw
            # mensagem menciona configuração / livekit
            detail = (data.get("detail") or "").lower()
            assert ("configur" in detail) or ("livekit" in detail)
        finally:
            requests.post(f"{API}/broadcasts/{bid}/end", headers=_h(formador_s["token"]))
            requests.delete(f"{API}/broadcasts/{bid}", headers=_h(mestre_s["token"]))

    def test_takeover_only_mestre(self, formador_s, mestre_s, membro_s):
        r = requests.post(f"{API}/broadcasts",
                          json={"title": "TEST_BC takeover", "stages": [3]},
                          headers=_h(formador_s["token"]))
        bid = r.json()["id"]
        try:
            # membro/formador não têm TAKE_OVER_LIVE
            assert requests.post(f"{API}/broadcasts/{bid}/takeover", headers=_h(membro_s["token"])).status_code == 403
            assert requests.post(f"{API}/broadcasts/{bid}/takeover", headers=_h(formador_s["token"])).status_code == 403
            # mestre pode
            tk = requests.post(f"{API}/broadcasts/{bid}/takeover", headers=_h(mestre_s["token"]))
            assert tk.status_code == 200, tk.text
            g = requests.get(f"{API}/broadcasts/{bid}", headers=_h(mestre_s["token"])).json()
            assert g["presenter_id"] == _me(mestre_s["token"])["id"]
        finally:
            requests.delete(f"{API}/broadcasts/{bid}", headers=_h(mestre_s["token"]))


class TestBroadcastChatAndModeration:
    def test_chat_post_get_and_block(self, formador_s, membro_s, mestre_s):
        _reset_membro_to_stage_3(mestre_s["token"], _me(membro_s["token"])["id"])
        r = requests.post(f"{API}/broadcasts",
                          json={"title": "TEST_BC chat", "stages": [3]},
                          headers=_h(formador_s["token"]))
        bid = r.json()["id"]
        try:
            requests.post(f"{API}/broadcasts/{bid}/start", headers=_h(formador_s["token"]))
            # membro posta
            p = requests.post(f"{API}/broadcasts/{bid}/chat",
                              json={"text": "olá TESTE_chat"}, headers=_h(membro_s["token"]))
            assert p.status_code == 200, p.text
            msg_id = p.json()["id"]

            # GET chat
            g = requests.get(f"{API}/broadcasts/{bid}/chat", headers=_h(membro_s["token"]))
            assert g.status_code == 200
            texts = [m["text"] for m in g.json()["messages"]]
            assert "olá TESTE_chat" in texts

            # membro NÃO pode moderar (delete requires MODERATE_LIVE)
            d_forbidden = requests.delete(f"{API}/broadcasts/{bid}/chat/{msg_id}", headers=_h(membro_s["token"]))
            assert d_forbidden.status_code == 403

            # formador pode moderar
            d_ok = requests.delete(f"{API}/broadcasts/{bid}/chat/{msg_id}", headers=_h(formador_s["token"]))
            assert d_ok.status_code == 200

            # membro NÃO pode moderar action=block
            m_forbidden = requests.post(f"{API}/broadcasts/{bid}/moderate",
                                        json={"action": "block", "user_id": _me(membro_s["token"])["id"]},
                                        headers=_h(membro_s["token"]))
            assert m_forbidden.status_code == 403

            # formador bloqueia membro
            membro_id = _me(membro_s["token"])["id"]
            m_ok = requests.post(f"{API}/broadcasts/{bid}/moderate",
                                 json={"action": "block", "user_id": membro_id},
                                 headers=_h(formador_s["token"]))
            assert m_ok.status_code == 200

            # membro bloqueado -> 403 ao postar
            p2 = requests.post(f"{API}/broadcasts/{bid}/chat",
                               json={"text": "não devo passar"}, headers=_h(membro_s["token"]))
            assert p2.status_code == 403

            # unblock para não deixar resíduo
            requests.post(f"{API}/broadcasts/{bid}/moderate",
                          json={"action": "unblock", "user_id": membro_id},
                          headers=_h(formador_s["token"]))

            # toggle_chat desativa
            tg = requests.post(f"{API}/broadcasts/{bid}/moderate",
                               json={"action": "toggle_chat"}, headers=_h(formador_s["token"]))
            assert tg.status_code == 200
            # com chat desativado, membro recebe 403
            p3 = requests.post(f"{API}/broadcasts/{bid}/chat",
                               json={"text": "desativado"}, headers=_h(membro_s["token"]))
            assert p3.status_code == 403
        finally:
            requests.post(f"{API}/broadcasts/{bid}/end", headers=_h(formador_s["token"]))
            requests.delete(f"{API}/broadcasts/{bid}", headers=_h(mestre_s["token"]))
            # garantia extra: desbloquear caso finally acima tenha pulado
            try:
                requests.post(f"{API}/broadcasts/{bid}/moderate",
                              json={"action": "unblock", "user_id": _me(membro_s["token"])["id"]},
                              headers=_h(formador_s["token"]))
            except Exception:
                pass

    def test_prevoc_cannot_post_chat_on_stage3_broadcast(self, formador_s, mestre_s):
        _ensure_prevoc_stage_1(mestre_s["token"])
        r = requests.post(f"{API}/broadcasts",
                          json={"title": "TEST_BC chat-stage-block", "stages": [3]},
                          headers=_h(formador_s["token"]))
        bid = r.json()["id"]
        try:
            requests.post(f"{API}/broadcasts/{bid}/start", headers=_h(formador_s["token"]))
            prevoc = _login(PREVOC)
            r_get = requests.get(f"{API}/broadcasts/{bid}/chat", headers=_h(prevoc["token"]))
            assert r_get.status_code == 403
            r_post = requests.post(f"{API}/broadcasts/{bid}/chat",
                                   json={"text": "não"}, headers=_h(prevoc["token"]))
            assert r_post.status_code == 403
        finally:
            requests.post(f"{API}/broadcasts/{bid}/end", headers=_h(formador_s["token"]))
            requests.delete(f"{API}/broadcasts/{bid}", headers=_h(mestre_s["token"]))


class TestBroadcastAnalytics:
    def test_heartbeat_stats_and_report_permission(self, formador_s, membro_s, mestre_s):
        _reset_membro_to_stage_3(mestre_s["token"], _me(membro_s["token"])["id"])
        r = requests.post(f"{API}/broadcasts",
                          json={"title": "TEST_BC stats", "stages": [3]},
                          headers=_h(formador_s["token"]))
        bid = r.json()["id"]
        try:
            requests.post(f"{API}/broadcasts/{bid}/start", headers=_h(formador_s["token"]))
            hb = requests.post(f"{API}/broadcasts/{bid}/heartbeat", headers=_h(membro_s["token"]))
            assert hb.status_code == 200
            data = hb.json()
            assert "viewers" in data and data["viewers"] >= 1
            st = requests.get(f"{API}/broadcasts/{bid}/stats", headers=_h(formador_s["token"]))
            assert st.status_code == 200
            assert st.json()["viewers"] >= 1
            # report requer VIEW_LIVE_ANALYTICS -> membro 403
            rep_forbidden = requests.get(f"{API}/broadcasts/{bid}/report", headers=_h(membro_s["token"]))
            assert rep_forbidden.status_code == 403
            # mestre tem tudo
            rep_ok = requests.get(f"{API}/broadcasts/{bid}/report", headers=_h(mestre_s["token"]))
            assert rep_ok.status_code == 200
            rep = rep_ok.json()
            assert rep["title"] == "TEST_BC stats"
            assert "unique_viewers" in rep and rep["unique_viewers"] >= 1
        finally:
            requests.post(f"{API}/broadcasts/{bid}/end", headers=_h(formador_s["token"]))
            requests.delete(f"{API}/broadcasts/{bid}", headers=_h(mestre_s["token"]))


class TestBroadcastStageInvariant:
    """Nenhum endpoint de broadcast deve alterar user.current_stage_order."""
    def test_start_end_takeover_do_not_change_stage(self, formador_s, membro_s, mestre_s):
        membro_id = _me(membro_s["token"])["id"]
        _reset_membro_to_stage_3(mestre_s["token"], membro_id)
        stage_before = requests.get(f"{API}/master/users/{membro_id}",
                                    headers=_h(mestre_s["token"])).json()["current_stage_order"]
        r = requests.post(f"{API}/broadcasts",
                          json={"title": "TEST_BC invariant", "stages": [3]},
                          headers=_h(formador_s["token"]))
        bid = r.json()["id"]
        try:
            requests.post(f"{API}/broadcasts/{bid}/start", headers=_h(formador_s["token"]))
            requests.post(f"{API}/broadcasts/{bid}/heartbeat", headers=_h(membro_s["token"]))
            requests.post(f"{API}/broadcasts/{bid}/chat",
                          json={"text": "TEST inv"}, headers=_h(membro_s["token"]))
            requests.post(f"{API}/broadcasts/{bid}/takeover", headers=_h(mestre_s["token"]))
            requests.post(f"{API}/broadcasts/{bid}/end", headers=_h(formador_s["token"]))
            stage_after = requests.get(f"{API}/master/users/{membro_id}",
                                       headers=_h(mestre_s["token"])).json()["current_stage_order"]
            assert stage_after == stage_before
        finally:
            requests.delete(f"{API}/broadcasts/{bid}", headers=_h(mestre_s["token"]))


# ================= ITERATION 9 — Fase 2 (Cenas/Overlays) + Agenda + Badge Ao Vivo =================
import datetime as _dt
from dotenv import dotenv_values as _dv

_BACKEND_ENV = _dv(BACKEND_ENV_PATH)
WEBHOOK_CRON_SECRET = os.environ.get("WEBHOOK_CRON_SECRET") or _BACKEND_ENV.get("WEBHOOK_CRON_SECRET", "")


def _iso_in(minutes: int) -> str:
    return (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=minutes)).isoformat()


class TestScenesAndActiveScene:
    """Fase 2 — PUT /scenes (MANAGE_SCENES + dono) e POST /active-scene (dono/operador)."""

    def test_save_scenes_and_active_scene_flow(self, formador_s, membro_s, mestre_s):
        # formador cria broadcast (é dono, tem MANAGE_SCENES)
        r = requests.post(f"{API}/broadcasts",
                          json={"title": "TEST_BC scenes", "stages": [3]},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 200, r.text
        bid = r.json()["id"]
        try:
            # PUT scenes com uma cena custom
            scenes = [{"name": "Cena 1", "layout": "pip",
                       "lower_third": {"name": "Formador", "role": "Apresentador", "visible": True},
                       "banner": {"text": "Aviso", "visible": True}}]
            r = requests.put(f"{API}/broadcasts/{bid}/scenes",
                             json={"scenes": scenes}, headers=_h(formador_s["token"]))
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["ok"] is True
            assert data["scenes"] == scenes

            # Confirma persistência via GET
            g = requests.get(f"{API}/broadcasts/{bid}", headers=_h(formador_s["token"])).json()
            assert g["scenes"] == scenes

            # POST active-scene define overlay atual
            payload = {"layout": "side",
                       "lower_third": {"name": "João", "role": "Formador", "visible": True},
                       "banner": {"text": "🔴 Ao vivo agora", "visible": True}}
            r = requests.post(f"{API}/broadcasts/{bid}/active-scene",
                              json=payload, headers=_h(formador_s["token"]))
            assert r.status_code == 200, r.text
            active = r.json()["active_scene"]
            assert active["layout"] == "side"
            assert active["lower_third"]["name"] == "João"
            assert active["banner"]["visible"] is True

            # start live para acesso do membro; overlays devem chegar via stats/heartbeat
            requests.post(f"{API}/broadcasts/{bid}/start", headers=_h(formador_s["token"]))
            stats = requests.get(f"{API}/broadcasts/{bid}/stats",
                                 headers=_h(membro_s["token"])).json()
            assert "active_scene" in stats
            assert stats["active_scene"]["layout"] == "side"
            assert stats["active_scene"]["lower_third"]["name"] == "João"

            hb = requests.post(f"{API}/broadcasts/{bid}/heartbeat",
                               headers=_h(membro_s["token"])).json()
            assert hb["active_scene"]["banner"]["text"] == "🔴 Ao vivo agora"

            # Membro comum (sem MANAGE_SCENES) → 403 no PUT /scenes
            r = requests.put(f"{API}/broadcasts/{bid}/scenes",
                             json={"scenes": []}, headers=_h(membro_s["token"]))
            assert r.status_code == 403, r.text

            # Membro comum não é operador → 403 no active-scene
            r = requests.post(f"{API}/broadcasts/{bid}/active-scene",
                              json=payload, headers=_h(membro_s["token"]))
            assert r.status_code == 403, r.text
        finally:
            requests.post(f"{API}/broadcasts/{bid}/end", headers=_h(formador_s["token"]))
            requests.delete(f"{API}/broadcasts/{bid}", headers=_h(mestre_s["token"]))


class TestBroadcastScheduleAndRemind:
    """Agenda: criação scheduled_at, listagem por etapa, toggle remind, flag reminded."""

    def test_scheduled_creation_and_reminder_toggle(self, formador_s, membro_s, prevoc_s, mestre_s):
        sched = _iso_in(30)
        r = requests.post(f"{API}/broadcasts",
                          json={"title": "TEST_BC scheduled", "stages": [3], "scheduled_at": sched},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 200, r.text
        bc = r.json()
        bid = bc["id"]
        assert bc["status"] == "scheduled"
        assert bc["scheduled_at"] == sched
        try:
            # Membro etapa 3 vê a live agendada com reminded=False
            lst = requests.get(f"{API}/broadcasts", headers=_h(membro_s["token"])).json()
            match = [x for x in lst if x["id"] == bid]
            assert len(match) == 1
            assert match[0]["status"] == "scheduled"
            assert match[0]["reminded"] is False

            # Membro etapa 1 (prevoc) NÃO vê a live stage-3
            lst_p = requests.get(f"{API}/broadcasts", headers=_h(prevoc_s["token"])).json()
            assert not any(x["id"] == bid for x in lst_p)

            # POST remind → true
            r = requests.post(f"{API}/broadcasts/{bid}/remind", headers=_h(membro_s["token"]))
            assert r.status_code == 200, r.text
            assert r.json()["reminded"] is True

            # GET single: reminded True
            g = requests.get(f"{API}/broadcasts/{bid}", headers=_h(membro_s["token"])).json()
            assert g["reminded"] is True

            # GET list: reminded True
            lst = requests.get(f"{API}/broadcasts", headers=_h(membro_s["token"])).json()
            assert next(x for x in lst if x["id"] == bid)["reminded"] is True

            # POST remind again → toggle off
            r = requests.post(f"{API}/broadcasts/{bid}/remind", headers=_h(membro_s["token"]))
            assert r.status_code == 200
            assert r.json()["reminded"] is False

            # prevoc → 403 no remind (sem acesso à etapa)
            r = requests.post(f"{API}/broadcasts/{bid}/remind", headers=_h(prevoc_s["token"]))
            assert r.status_code == 403
        finally:
            requests.delete(f"{API}/broadcasts/{bid}", headers=_h(mestre_s["token"]))


class TestCronBroadcastReminders:
    """POST /api/cron/broadcast-reminders exige Bearer WEBHOOK_CRON_SECRET; dispara notificação."""

    def test_cron_auth_and_notification_dispatch(self, formador_s, membro_s, mestre_s):
        # 401 sem Authorization
        r = requests.post(f"{API}/cron/broadcast-reminders")
        assert r.status_code == 401, r.text

        # 401 com token errado
        r = requests.post(f"{API}/cron/broadcast-reminders",
                          headers={"Authorization": "Bearer wrong-secret"})
        assert r.status_code == 401

        assert WEBHOOK_CRON_SECRET, "WEBHOOK_CRON_SECRET missing"

        # cria live scheduled dentro da janela de 15 min
        sched = _iso_in(10)
        r = requests.post(f"{API}/broadcasts",
                          json={"title": "TEST_BC cron reminder", "stages": [3], "scheduled_at": sched},
                          headers=_h(formador_s["token"]))
        assert r.status_code == 200, r.text
        bid = r.json()["id"]
        try:
            # membro registra lembrete
            r = requests.post(f"{API}/broadcasts/{bid}/remind", headers=_h(membro_s["token"]))
            assert r.status_code == 200 and r.json()["reminded"] is True

            # captura notificações do membro (baseline)
            before = requests.get(f"{API}/notifications",
                                  headers=_h(membro_s["token"])).json()
            before_ids = {n["id"] for n in before}

            # dispara cron com Bearer válido → 2xx
            r = requests.post(f"{API}/cron/broadcast-reminders",
                              headers={"Authorization": f"Bearer {WEBHOOK_CRON_SECRET}"})
            assert r.status_code == 200, r.text

            # BackgroundTasks é assíncrono → aguarda
            import time
            found = None
            for _ in range(10):
                time.sleep(1)
                after = requests.get(f"{API}/notifications",
                                     headers=_h(membro_s["token"])).json()
                new = [n for n in after if n["id"] not in before_ids]
                cand = [n for n in new if "começa em breve" in (n.get("title") or "")]
                if cand:
                    found = cand[0]
                    break
            assert found is not None, "expected '📺 Sua live começa em breve' notification"

            # segunda chamada não duplica (notified=True já)
            r = requests.post(f"{API}/cron/broadcast-reminders",
                              headers={"Authorization": f"Bearer {WEBHOOK_CRON_SECRET}"})
            assert r.status_code == 200
            time.sleep(2)
            after2 = requests.get(f"{API}/notifications",
                                  headers=_h(membro_s["token"])).json()
            dup = [n for n in after2 if n["id"] not in before_ids
                   and "começa em breve" in (n.get("title") or "")]
            assert len(dup) == 1, f"cron não deve duplicar lembrete (got {len(dup)})"
        finally:
            requests.delete(f"{API}/broadcasts/{bid}", headers=_h(mestre_s["token"]))


class TestLiveBroadcastsBadge:
    """GET /api/live-broadcasts filtra por status=live e por etapa do usuário."""

    def test_live_badge_visible_to_stage_member_only(self, formador_s, membro_s, prevoc_s, mestre_s):
        r = requests.post(f"{API}/broadcasts",
                          json={"title": "TEST_BC live badge", "stages": [3]},
                          headers=_h(formador_s["token"]))
        bid = r.json()["id"]
        try:
            # Antes de start: NÃO deve aparecer
            lst = requests.get(f"{API}/live-broadcasts", headers=_h(membro_s["token"])).json()
            assert not any(x["id"] == bid for x in lst)

            # start
            r = requests.post(f"{API}/broadcasts/{bid}/start", headers=_h(formador_s["token"]))
            assert r.status_code == 200, r.text

            # Membro etapa 3 vê
            lst = requests.get(f"{API}/live-broadcasts", headers=_h(membro_s["token"])).json()
            assert any(x["id"] == bid and x["status"] == "live" for x in lst)

            # Prevoc (etapa 1) não vê
            lst_p = requests.get(f"{API}/live-broadcasts", headers=_h(prevoc_s["token"])).json()
            assert not any(x["id"] == bid for x in lst_p)
        finally:
            requests.post(f"{API}/broadcasts/{bid}/end", headers=_h(formador_s["token"]))
            requests.delete(f"{API}/broadcasts/{bid}", headers=_h(mestre_s["token"]))


class TestBroadcastPhase2StageInvariant:
    """INVARIANTE: nenhum endpoint novo (scenes/active-scene/remind/live-broadcasts/cron)
    altera user.current_stage_order."""

    def test_new_endpoints_do_not_mutate_stage(self, formador_s, membro_s, mestre_s):
        membro_id = _me(membro_s["token"])["id"]
        _reset_membro_to_stage_3(mestre_s["token"], membro_id)
        before = requests.get(f"{API}/master/users/{membro_id}",
                              headers=_h(mestre_s["token"])).json()["current_stage_order"]

        r = requests.post(f"{API}/broadcasts",
                          json={"title": "TEST_BC invariant p2", "stages": [3],
                                "scheduled_at": _iso_in(10)},
                          headers=_h(formador_s["token"]))
        bid = r.json()["id"]
        try:
            requests.put(f"{API}/broadcasts/{bid}/scenes",
                         json={"scenes": [{"name": "S1", "layout": "full",
                                           "lower_third": {"name": "", "role": "", "visible": False},
                                           "banner": {"text": "", "visible": False}}]},
                         headers=_h(formador_s["token"]))
            requests.post(f"{API}/broadcasts/{bid}/active-scene",
                          json={"layout": "pip",
                                "lower_third": {"name": "X", "role": "Y", "visible": True},
                                "banner": {"text": "Z", "visible": True}},
                          headers=_h(formador_s["token"]))
            requests.post(f"{API}/broadcasts/{bid}/remind", headers=_h(membro_s["token"]))
            requests.get(f"{API}/live-broadcasts", headers=_h(membro_s["token"]))
            requests.post(f"{API}/cron/broadcast-reminders",
                          headers={"Authorization": f"Bearer {WEBHOOK_CRON_SECRET}"})

            after = requests.get(f"{API}/master/users/{membro_id}",
                                 headers=_h(mestre_s["token"])).json()["current_stage_order"]
            assert after == before, f"stage mudou de {before} para {after}"
        finally:
            requests.delete(f"{API}/broadcasts/{bid}", headers=_h(mestre_s["token"]))
