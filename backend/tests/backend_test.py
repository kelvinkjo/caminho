"""CAMINHO backend tests — Master (Login Mestre) stage-control rules.

REGRA INVIOLÁVEL: apenas o Login Mestre (role 'mestre', permissão MANAGE_FORMATION_STAGE)
altera/mantém a etapa de formação. Concluir a formação NUNCA promove o usuário.
"""
import os
from pathlib import Path
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"

MESTRE = {"email": "kelvinjose.oliveira@gmail.com", "password": "***REMOVED***"}
ADMIN = {"email": "admin@caminho.app", "password": "***REMOVED***"}
FORMADOR = {"email": "formador@caminho.app", "password": "***REMOVED***"}
MEMBRO = {"email": "membro@caminho.app", "password": "***REMOVED***"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed {creds['email']} {r.status_code} {r.text}"
    return r.json()


def _h(token):
    return {"Authorization": f"Bearer {token}"}


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
        assert _login(MESTRE)["user"]["role"] == "mestre"
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

    def test_admin_forbidden_master(self, admin_s):
        r = requests.get(f"{API}/master/users", headers=_h(admin_s["token"]))
        assert r.status_code == 403

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

    def test_admin_forbidden_master(self, admin_s):
        assert requests.get(f"{API}/master/users", headers=_h(admin_s["token"])).status_code == 403
        assert requests.get(f"{API}/master/recommendations", headers=_h(admin_s["token"])).status_code == 403

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
        d = _login({"email": email, "password": "***REMOVED***"})
        me = _me(d["token"])
        assert me["current_stage_order"] == expected
        for order in range(1, expected + 1):
            assert requests.get(f"{API}/stages/{order}/modules", headers=_h(d["token"])).status_code == 200
        for order in range(expected + 1, 7):
            assert requests.get(f"{API}/stages/{order}/modules", headers=_h(d["token"])).status_code == 403


# ---------------- AI smoke check ----------------
class TestAISmoke:
    def test_assistant_responds(self, membro_s):
        r = requests.post(f"{API}/assistant/ask",
                          json={"question": "O que é a Eucaristia?"},
                          headers=_h(membro_s["token"]), timeout=90)
        assert r.status_code == 200
        assert len(r.json().get("answer", "")) > 20
