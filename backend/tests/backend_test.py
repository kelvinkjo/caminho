"""CAMINHO backend tests - auth, stage security, formation, approval, formador, admin."""
import os
from pathlib import Path
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "kelvinjose.oliveira@gmail.com", "password": "***REMOVED***"}
FORMADOR = {"email": "formador@caminho.app", "password": "***REMOVED***"}
MEMBRO = {"email": "membro@caminho.app", "password": "***REMOVED***"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed {creds['email']} {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and "user" in data
    return data


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def membro_session():
    return _login(MEMBRO)


@pytest.fixture(scope="session")
def formador_session():
    return _login(FORMADOR)


@pytest.fixture(scope="session")
def admin_session():
    return _login(ADMIN)


# ------------- AUTH -------------
class TestAuth:
    def test_login_membro(self):
        d = _login(MEMBRO)
        assert d["user"]["email"] == MEMBRO["email"]
        assert d["user"]["role"] == "membro"
        assert "password_hash" not in d["user"]

    def test_login_admin_formador(self):
        a = _login(ADMIN); assert a["user"]["role"] == "admin"
        f = _login(FORMADOR); assert f["user"]["role"] == "formador"

    def test_auth_me(self, membro_session):
        r = requests.get(f"{API}/auth/me", headers=_headers(membro_session["token"]))
        assert r.status_code == 200
        assert r.json()["email"] == MEMBRO["email"]

    def test_invalid_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": MEMBRO["email"], "password": "wrong"})
        assert r.status_code == 401

    def test_no_token(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401


# ------------- STAGE SECURITY -------------
class TestStageSecurity:
    def test_accessible_stage(self, membro_session):
        # membro current stage may be 3+ (advanced by approval test). Get from /auth/me.
        me = requests.get(f"{API}/auth/me", headers=_headers(membro_session["token"])).json()
        cur = me["current_stage_order"]
        r = requests.get(f"{API}/stages/{cur}/modules", headers=_headers(membro_session["token"]))
        assert r.status_code == 200
        r1 = requests.get(f"{API}/stages/1/modules", headers=_headers(membro_session["token"]))
        assert r1.status_code == 200

    def test_blocked_stage(self, membro_session):
        for order in (5, 6):
            r = requests.get(f"{API}/stages/{order}/modules", headers=_headers(membro_session["token"]))
            # Only block if user's stage < order
            me = requests.get(f"{API}/auth/me", headers=_headers(membro_session["token"])).json()
            if order > me["current_stage_order"]:
                assert r.status_code == 403, f"stage {order} should be blocked, got {r.status_code}"

    def test_blocked_lesson(self, membro_session, admin_session):
        # Admin fetches lesson of stage > membro's current
        me = requests.get(f"{API}/auth/me", headers=_headers(membro_session["token"])).json()
        cur = me["current_stage_order"]
        # Find a stage above cur that has lessons in seed (only 1,2,3 have lessons). If cur>=3, skip.
        higher_stages = [o for o in (1, 2, 3) if o > cur]
        if not higher_stages:
            pytest.skip(f"membro already at stage {cur}; no higher seeded stage to test lesson block")
        target = higher_stages[0]
        mods = requests.get(f"{API}/stages/{target}/modules", headers=_headers(admin_session["token"])).json()
        lesson_id = mods["modules"][0]["lessons"][0]["id"]
        r = requests.get(f"{API}/lessons/{lesson_id}", headers=_headers(membro_session["token"]))
        assert r.status_code == 403
        r2 = requests.post(f"{API}/lessons/{lesson_id}/progress",
                           json={"completed": True, "percent": 100}, headers=_headers(membro_session["token"]))
        assert r2.status_code == 403


# ------------- ROLE SECURITY -------------
class TestRoleSecurity:
    @pytest.mark.parametrize("path", ["/formador/people", "/approvals", "/admin/stats", "/admin/users"])
    def test_membro_forbidden(self, membro_session, path):
        r = requests.get(f"{API}{path}", headers=_headers(membro_session["token"]))
        assert r.status_code == 403, f"{path} should be 403, got {r.status_code}"


# ------------- FORMATION + APPROVAL FLOW -------------
class TestApprovalFlow:
    def test_full_flow(self, membro_session, formador_session):
        token = membro_session["token"]
        me = requests.get(f"{API}/auth/me", headers=_headers(token)).json()
        original_stage = me["current_stage_order"]

        if original_stage >= 6:
            pytest.skip("membro already at final stage")

        # Request approval BEFORE completing lessons - if progress<100 should be 400.
        # First, check current progress.
        stages_r = requests.get(f"{API}/stages", headers=_headers(token)).json()
        current_stage = next(s for s in stages_r if s["order"] == original_stage)
        if current_stage["progress"]["percent"] < 100:
            r_bad = requests.post(f"{API}/stages/request-approval", headers=_headers(token))
            assert r_bad.status_code == 400

        # Complete all lessons of current stage
        mods = requests.get(f"{API}/stages/{original_stage}/modules", headers=_headers(token)).json()
        for m in mods["modules"]:
            for l in m["lessons"]:
                rr = requests.post(f"{API}/lessons/{l['id']}/progress",
                                   json={"completed": True, "percent": 100}, headers=_headers(token))
                assert rr.status_code == 200

        stages_r = requests.get(f"{API}/stages", headers=_headers(token)).json()
        current_stage = next(s for s in stages_r if s["order"] == original_stage)
        assert current_stage["progress"]["percent"] == 100

        # Request approval - should succeed
        r_ok = requests.post(f"{API}/stages/request-approval", headers=_headers(token))
        assert r_ok.status_code == 200
        assert r_ok.json().get("status") == "pending"

        # Stage now awaiting_approval
        stages_r = requests.get(f"{API}/stages", headers=_headers(token)).json()
        current_stage = next(s for s in stages_r if s["order"] == original_stage)
        assert current_stage["status"] == "awaiting_approval"

        # Formador sees pending
        f_token = formador_session["token"]
        approvals = requests.get(f"{API}/approvals", headers=_headers(f_token))
        assert approvals.status_code == 200
        items = approvals.json()
        target = next((a for a in items if a["user_id"] == me["id"] and a["stage_order"] == original_stage), None)
        assert target is not None, "formador should see the pending approval"

        # Approve
        ap = requests.post(f"{API}/approvals/{target['id']}/approve", headers=_headers(f_token))
        assert ap.status_code == 200

        # Verify membro's stage advanced
        me2 = requests.get(f"{API}/auth/me", headers=_headers(token)).json()
        assert me2["current_stage_order"] == min(original_stage + 1, 6)


# ------------- FORMADOR PEOPLE / RADAR -------------
class TestFormadorPeople:
    def test_my_people(self, formador_session):
        r = requests.get(f"{API}/formador/people", headers=_headers(formador_session["token"]))
        assert r.status_code == 200
        people = r.json()
        assert len(people) >= 1
        joao = next((p for p in people if p["email"] == MEMBRO["email"]), None)
        assert joao is not None
        assert joao["radar"] in ("green", "yellow", "red")
        assert "progress" in joao


# ------------- DASHBOARD & MISSIONS -------------
class TestDashboardMissions:
    def test_dashboard(self, membro_session):
        r = requests.get(f"{API}/dashboard", headers=_headers(membro_session["token"]))
        assert r.status_code == 200
        d = r.json()
        for k in ("user", "stage", "progress", "word", "missions", "events"):
            assert k in d

    def test_missions_complete(self, membro_session):
        r = requests.get(f"{API}/missions", headers=_headers(membro_session["token"]))
        assert r.status_code == 200
        missions = r.json()
        assert len(missions) > 0
        mid = missions[0]["id"]
        c = requests.post(f"{API}/missions/{mid}/complete", headers=_headers(membro_session["token"]))
        assert c.status_code == 200
        # Verify persisted
        again = requests.get(f"{API}/missions", headers=_headers(membro_session["token"])).json()
        m = next(x for x in again if x["id"] == mid)
        assert m["completed"] is True


# ------------- ADMIN -------------
class TestAdmin:
    def test_stats(self, admin_session):
        r = requests.get(f"{API}/admin/stats", headers=_headers(admin_session["token"]))
        assert r.status_code == 200
        d = r.json()
        assert "total_users" in d and "by_stage" in d
        assert isinstance(d["by_stage"], list) and len(d["by_stage"]) == 6

    def test_users_and_patch(self, admin_session):
        users = requests.get(f"{API}/admin/users", headers=_headers(admin_session["token"])).json()
        membro_u = next(u for u in users if u["email"] == MEMBRO["email"])
        original_stage = membro_u["current_stage_order"]

        # Patch to same value (no side effect) - just verify endpoint works
        r = requests.patch(f"{API}/admin/users/{membro_u['id']}",
                           json={"current_stage_order": original_stage},
                           headers=_headers(admin_session["token"]))
        assert r.status_code == 200

        users2 = requests.get(f"{API}/admin/users", headers=_headers(admin_session["token"])).json()
        m2 = next(u for u in users2 if u["email"] == MEMBRO["email"])
        assert m2["current_stage_order"] == original_stage
