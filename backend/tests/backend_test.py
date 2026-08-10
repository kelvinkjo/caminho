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



# ------------- STAGE HIERARCHY per user (item 59) -------------
STAGE_USERS = [
    ("prevocacionado@caminho.app", 1),
    ("vocacionado@caminho.app", 2),
    ("discipulo2@caminho.app", 4),
    ("compromissado@caminho.app", 5),
    ("consagrado@caminho.app", 6),
]


class TestStageHierarchy:
    @pytest.mark.parametrize("email,expected_stage", STAGE_USERS)
    def test_hierarchy(self, email, expected_stage):
        d = _login({"email": email, "password": "***REMOVED***"})
        token = d["token"]
        me = requests.get(f"{API}/auth/me", headers=_headers(token)).json()
        assert me["current_stage_order"] == expected_stage, f"{email} expected stage {expected_stage}, got {me['current_stage_order']}"
        # allowed orders
        for order in range(1, expected_stage + 1):
            r = requests.get(f"{API}/stages/{order}/modules", headers=_headers(token))
            assert r.status_code == 200, f"{email} stage {order} should be accessible, got {r.status_code}"
        # blocked orders
        for order in range(expected_stage + 1, 7):
            r = requests.get(f"{API}/stages/{order}/modules", headers=_headers(token))
            assert r.status_code == 403, f"{email} stage {order} should be 403, got {r.status_code}"


# ------------- CANNOT CHANGE OWN LEVEL -------------
class TestCannotChangeOwnLevel:
    def test_membro_patch_self_forbidden(self, membro_session):
        me = requests.get(f"{API}/auth/me", headers=_headers(membro_session["token"])).json()
        r = requests.patch(f"{API}/admin/users/{me['id']}",
                           json={"current_stage_order": 6},
                           headers=_headers(membro_session["token"]))
        assert r.status_code == 403

    def test_formador_patch_forbidden(self, formador_session):
        # formador should not be able to admin-patch users either
        me = requests.get(f"{API}/auth/me", headers=_headers(formador_session["token"])).json()
        r = requests.patch(f"{API}/admin/users/{me['id']}",
                           json={"current_stage_order": 1},
                           headers=_headers(formador_session["token"]))
        assert r.status_code == 403


# ------------- FORMADOR forbidden on admin endpoints -------------
class TestFormadorRoleGating:
    @pytest.mark.parametrize("path", ["/admin/stats", "/admin/users", "/formadores"])
    def test_formador_no_admin(self, formador_session, path):
        r = requests.get(f"{API}{path}", headers=_headers(formador_session["token"]))
        assert r.status_code == 403


# ------------- AI ASSISTANT (Fase 8) -------------
class TestAssistant:
    def test_unauthenticated(self):
        r = requests.post(f"{API}/assistant/ask", json={"question": "O que é a Eucaristia?"})
        assert r.status_code == 401

    def test_empty_question(self, membro_session):
        r = requests.post(f"{API}/assistant/ask", json={"question": "   "},
                          headers=_headers(membro_session["token"]))
        assert r.status_code == 400

    def test_ask_and_history(self, membro_session):
        token = membro_session["token"]
        r = requests.post(f"{API}/assistant/ask",
                          json={"question": "O que é a Eucaristia segundo a Igreja Católica?"},
                          headers=_headers(token), timeout=90)
        assert r.status_code == 200, f"assistant ask failed: {r.status_code} {r.text[:400]}"
        data = r.json()
        assert "answer" in data and isinstance(data["answer"], str) and len(data["answer"]) > 20
        assert "session_id" in data and data["session_id"]
        sid = data["session_id"]

        # Second turn same session
        r2 = requests.post(f"{API}/assistant/ask",
                           json={"question": "E qual número do Catecismo fala sobre isso?", "session_id": sid},
                           headers=_headers(token), timeout=90)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["session_id"] == sid
        assert len(d2["answer"]) > 20

        # History
        h = requests.get(f"{API}/assistant/history", params={"session_id": sid},
                         headers=_headers(token))
        assert h.status_code == 200
        msgs = h.json()
        assert isinstance(msgs, list) and len(msgs) >= 4
        roles = [m["role"] for m in msgs]
        assert roles.count("user") >= 2 and roles.count("assistant") >= 2



# ------------- LIVES (Fase 3 - iteration 3) -------------
STAGE_CREDS = {n: {"email": e, "password": "***REMOVED***"} for e, n in [
    ("prevocacionado@caminho.app", 1),
    ("vocacionado@caminho.app", 2),
    ("membro@caminho.app", 3),
    ("discipulo2@caminho.app", 4),
    ("compromissado@caminho.app", 5),
    ("consagrado@caminho.app", 6),
]}


class TestLives:
    def test_lives_shape_and_stage_scoping(self):
        # stage 1 member should NOT see stage-3 mandatory live
        d1 = _login(STAGE_CREDS[1])
        r = requests.get(f"{API}/lives", headers=_headers(d1["token"]))
        assert r.status_code == 200
        data = r.json()
        for k in ("live_now", "upcoming", "recorded"):
            assert k in data and isinstance(data[k], list)
        all_titles = [l["title"] for k in data for l in data[k]]
        assert "Formação: Viver como Discípulo" not in all_titles, \
            f"stage-1 member should NOT see stage-3 mandatory live; saw {all_titles}"

        # A membro at stage>=3 SHOULD see it
        m = _login(MEMBRO)
        me = requests.get(f"{API}/auth/me", headers=_headers(m["token"])).json()
        if me["current_stage_order"] >= 3:
            r2 = requests.get(f"{API}/lives", headers=_headers(m["token"]))
            titles = [l["title"] for k in r2.json() for l in r2.json()[k]]
            assert "Formação: Viver como Discípulo" in titles

    def test_presence_confirmed_vs_not(self):
        # membro (stage>=3) posts presence on stage-3 mandatory live
        m = _login(MEMBRO)
        token = m["token"]
        me = requests.get(f"{API}/auth/me", headers=_headers(token)).json()
        if me["current_stage_order"] < 3:
            pytest.skip("membro below stage 3; cannot access stage-3 live")
        buckets = requests.get(f"{API}/lives", headers=_headers(token)).json()
        target = None
        for k in buckets:
            for l in buckets[k]:
                if l["title"] == "Formação: Viver como Discípulo":
                    target = l; break
        assert target is not None
        r_low = requests.post(f"{API}/lives/{target['id']}/presence",
                              json={"percent": 50}, headers=_headers(token))
        assert r_low.status_code == 200
        assert r_low.json()["confirmed"] is False
        r_ok = requests.post(f"{API}/lives/{target['id']}/presence",
                             json={"percent": 100}, headers=_headers(token))
        assert r_ok.status_code == 200
        assert r_ok.json()["confirmed"] is True

    def test_presence_forbidden_above_stage(self):
        # stage-1 member tries to POST presence on stage-3 live via admin lookup
        adm = _login(ADMIN)
        # find stage-3 live id via admin who sees all
        lives = requests.get(f"{API}/lives", headers=_headers(adm["token"])).json()
        target = None
        for k in lives:
            for l in lives[k]:
                if l.get("stage_order") == 3 and l.get("required"):
                    target = l; break
        assert target is not None
        p1 = _login(STAGE_CREDS[1])
        r = requests.post(f"{API}/lives/{target['id']}/presence",
                          json={"percent": 100}, headers=_headers(p1["token"]))
        assert r.status_code == 403


# ------------- MANDATORY LIVE gating request-approval -------------
class TestMandatoryLiveApproval:
    def test_mandatory_live_blocks_then_allows(self):
        # Ensures that with all stage-3 lessons complete but presence NOT confirmed on the mandatory live,
        # request-approval returns 400 with the specific message; then after confirming presence -> 200.
        m = _login(MEMBRO)
        token = m["token"]
        me = requests.get(f"{API}/auth/me", headers=_headers(token)).json()
        cur = me["current_stage_order"]
        # Only meaningful when membro is at stage 3 with a stage-3 mandatory live
        if cur != 3:
            pytest.skip(f"membro not at stage 3 (currently {cur}); cannot exercise mandatory-live gating")

        # Reset attendance to unconfirmed by setting percent=0 via API
        buckets = requests.get(f"{API}/lives", headers=_headers(token)).json()
        target = None
        for k in buckets:
            for l in buckets[k]:
                if l.get("stage_order") == 3 and l.get("required"):
                    target = l; break
        assert target is not None
        requests.post(f"{API}/lives/{target['id']}/presence",
                      json={"percent": 0}, headers=_headers(token))

        # Complete all stage-3 lessons
        mods = requests.get(f"{API}/stages/3/modules", headers=_headers(token)).json()
        for mm in mods["modules"]:
            for l in mm["lessons"]:
                requests.post(f"{API}/lessons/{l['id']}/progress",
                              json={"completed": True, "percent": 100}, headers=_headers(token))

        # request-approval should be 400 because mandatory live not confirmed
        r_bad = requests.post(f"{API}/stages/request-approval", headers=_headers(token))
        assert r_bad.status_code == 400
        assert "live" in r_bad.text.lower() or "presença" in r_bad.text.lower()

        # Confirm presence
        r_conf = requests.post(f"{API}/lives/{target['id']}/presence",
                               json={"percent": 100}, headers=_headers(token))
        assert r_conf.json()["confirmed"] is True

        # Now request-approval should succeed
        r_ok = requests.post(f"{API}/stages/request-approval", headers=_headers(token))
        assert r_ok.status_code == 200, f"expected 200 after presence confirmed, got {r_ok.status_code} {r_ok.text}"
        assert r_ok.json().get("status") == "pending"


# ------------- RECOMMENDATIONS -------------
class TestRecommendations:
    def test_recommendations_shape_and_tip(self):
        # Use stage-1 user who has no lessons completed → next_lesson should be present
        d = _login(STAGE_CREDS[1])
        r = requests.get(f"{API}/recommendations", headers=_headers(d["token"]), timeout=60)
        assert r.status_code == 200
        data = r.json()
        for k in ("next_lesson", "mission", "reading", "tip"):
            assert k in data
        assert isinstance(data["tip"], str) and len(data["tip"]) > 0, "tip must be non-empty (AI-generated)"
        # No markdown asterisks
        assert "**" not in data["tip"] and "*" not in data["tip"], f"tip contains markdown: {data['tip']!r}"
        # next_lesson for a fresh stage-1 user should exist
        assert data["next_lesson"] is not None
        assert "id" in data["next_lesson"] and "title" in data["next_lesson"]


# ------------- APOLOGETICS -------------
class TestApologetics:
    def test_list_and_categories(self, membro_session):
        r = requests.get(f"{API}/apologetics", headers=_headers(membro_session["token"]))
        assert r.status_code == 200
        data = r.json()
        assert "categories" in data and "items" in data
        assert len(data["categories"]) >= 6
        assert len(data["items"]) >= 6

    def test_filter_by_category(self, membro_session):
        r = requests.get(f"{API}/apologetics", params={"category": "Eucaristia"},
                         headers=_headers(membro_session["token"]))
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        assert all(i["category"] == "Eucaristia" for i in items)

    def test_detail_fields(self, membro_session):
        listing = requests.get(f"{API}/apologetics", headers=_headers(membro_session["token"])).json()
        aid = listing["items"][0]["id"]
        r = requests.get(f"{API}/apologetics/{aid}", headers=_headers(membro_session["token"]))
        assert r.status_code == 200
        d = r.json()
        for k in ("question", "answer", "explanation", "bible", "tradition", "catechism", "magisterium"):
            assert k in d and isinstance(d[k], str)

    def test_detail_404(self, membro_session):
        r = requests.get(f"{API}/apologetics/nonexistent-id", headers=_headers(membro_session["token"]))
        assert r.status_code == 404


# ------------- SEARCH -------------
class TestSearch:
    def test_search_min_length(self, membro_session):
        r = requests.get(f"{API}/search", params={"q": "a"}, headers=_headers(membro_session["token"]))
        assert r.status_code == 400

    def test_search_eucaristia(self, membro_session):
        r = requests.get(f"{API}/search", params={"q": "eucaristia"},
                         headers=_headers(membro_session["token"]), timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert "lessons" in d and "apologetics" in d and "answer" in d
        assert isinstance(d["answer"], str) and len(d["answer"]) > 10, "AI answer must be non-empty"
        # apologetics should include Eucaristia match
        assert any("euca" in a["question"].lower() or a["category"].lower() == "eucaristia" for a in d["apologetics"])

    def test_search_stage_scoping(self):
        # stage-1 member: search "eucaristia" — stage-2 lesson "A Eucaristia, fonte e ápice" should NOT appear
        d = _login(STAGE_CREDS[1])
        r = requests.get(f"{API}/search", params={"q": "eucaristia"},
                         headers=_headers(d["token"]), timeout=60)
        assert r.status_code == 200
        lessons = r.json()["lessons"]
        assert all(l["stage_order"] <= 1 for l in lessons), f"stage-1 leak: {lessons}"

    def test_unauth(self):
        r = requests.get(f"{API}/search", params={"q": "jesus"})
        assert r.status_code == 401
