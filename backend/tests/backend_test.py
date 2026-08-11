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


# ---------------- ITERATION 5: Requisitos Configuráveis ----------------
class TestStageRequirements:
    def test_get_requirements_defaults(self, mestre_s):
        r = requests.get(f"{API}/master/stage-requirements", headers=_h(mestre_s["token"]))
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 6
        for s in data:
            assert "order" in s and "require_lessons" in s and "require_mandatory_lives" in s

    @pytest.mark.parametrize("role_key", ["formador_s", "membro_s", "admin_s"])
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

    @pytest.mark.parametrize("role_key", ["formador_s", "membro_s", "admin_s"])
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


# ---------------- AI smoke check ----------------
class TestAISmoke:
    def test_assistant_responds(self, membro_s):
        r = requests.post(f"{API}/assistant/ask",
                          json={"question": "O que é a Eucaristia?"},
                          headers=_h(membro_s["token"]), timeout=90)
        assert r.status_code == 200
        assert len(r.json().get("answer", "")) > 20


# ---------------- ITERATION 6 — GRANULAR PERMISSIONS / CONTENT / LIVES ----------------
PREVOC = {"email": "prevocacionado@caminho.app", "password": "***REMOVED***"}

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
