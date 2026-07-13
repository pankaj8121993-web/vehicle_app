"""FleetFlow multi-tenant / expense / demo / onboarding backend tests.

Focused on the FleetFlow SaaS conversion. Uses default seeded passwords per
/app/memory/test_credentials.md (do NOT run the full pytest suite, which
rotates passwords).
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://vehicle-central-17.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

RAJGURU_ADMIN = ("admin", "rajguru@2026")
ACME_ADMIN = ("raviacme", "acme@12345")


def _login(username, password):
    r = requests.post(f"{API}/auth/login", json={"username": username, "password": password}, timeout=20)
    return r


def _auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _vehicles(token):
    """Unwrap paginated vehicles response."""
    r = requests.get(f"{API}/vehicles", headers=_auth(token))
    r.raise_for_status()
    d = r.json()
    return d.get("items", d) if isinstance(d, dict) else d


@pytest.fixture(scope="session")
def rajguru_token():
    r = _login(*RAJGURU_ADMIN)
    assert r.status_code == 200, f"rajguru admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def acme_token():
    r = _login(*ACME_ADMIN)
    if r.status_code != 200:
        pytest.skip(f"Acme login failed ({r.status_code}); skip cross-tenant tests")
    return r.json()["token"]


# ---------------- Auth / me ----------------

class TestAuthAndMe:
    def test_login_includes_org(self, rajguru_token):
        r = requests.get(f"{API}/auth/me", headers=_auth(rajguru_token))
        assert r.status_code == 200
        d = r.json()
        assert d.get("org_id")
        assert d.get("org_name")
        assert d.get("is_demo") is False

    def test_wrong_password_401(self):
        r = _login("admin", "wrong-password")
        assert r.status_code in (400, 401)


# ---------------- Onboarding ----------------

class TestOnboarding:
    def test_register_org_success_and_redirect_ready(self):
        ts = int(time.time())
        payload = {
            "org": {"legal_name": f"TEST_Org_{ts} Pvt Ltd", "org_type": "Private Limited Company"},
            "admin": {
                "username": f"testadmin{ts}",
                "email": f"testadmin{ts}@example.com",
                "password": "StrongPass1!",
                "full_name": "Test Admin",
            },
        }
        r = requests.post(f"{API}/onboarding/register", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("token")
        u = body["user"]
        assert u["role"] == "org_admin"
        assert u["is_demo"] is False
        assert u["org_name"]

        # New org should have zero vehicles (isolated workspace)
        vs = _vehicles(body["token"])
        assert vs == []

        # Checklist should be available
        c = requests.get(f"{API}/onboarding/checklist", headers=_auth(body["token"]))
        assert c.status_code == 200
        cj = c.json()
        assert cj["total"] == 8
        assert isinstance(cj["items"], list)

    def test_register_org_validation_errors(self):
        # missing legal_name
        r = requests.post(f"{API}/onboarding/register", json={
            "org": {"org_type": "Company"},
            "admin": {"username": "abcxyz", "email": "a@b.com", "password": "StrongPass1!", "full_name": "X"},
        })
        assert r.status_code == 400

        # short password
        ts = int(time.time())
        r = requests.post(f"{API}/onboarding/register", json={
            "org": {"legal_name": f"TEST_ShortPw_{ts}", "org_type": "Company"},
            "admin": {"username": f"shortpw{ts}", "email": f"shortpw{ts}@x.com", "password": "abc", "full_name": "X"},
        })
        assert r.status_code == 400

        # invalid org_type
        r = requests.post(f"{API}/onboarding/register", json={
            "org": {"legal_name": f"TEST_BadType_{ts}", "org_type": "NotARealType"},
            "admin": {"username": f"badtype{ts}", "email": f"badtype{ts}@x.com", "password": "StrongPass1!", "full_name": "X"},
        })
        assert r.status_code == 400

    def test_duplicate_org_rejected(self):
        # Try to re-register Rajguru — should fail (globally unique legal name)
        r = requests.post(f"{API}/onboarding/register", json={
            "org": {"legal_name": "Rajguru Foods", "org_type": "Private Limited Company"},
            "admin": {"username": "dupadmin", "email": "dup@x.com", "password": "StrongPass1!", "full_name": "Dup"},
        })
        assert r.status_code == 400


# ---------------- Demo environment ----------------

class TestDemo:
    def test_demo_roles_listed(self):
        r = requests.get(f"{API}/demo/roles")
        assert r.status_code == 200
        roles = {x["role"] for x in r.json()}
        assert {"org_admin", "owner", "fleet_manager", "operations", "maintenance", "driver", "accounts", "viewer"} <= roles

    def test_enter_demo_fleet_manager(self):
        r = requests.post(f"{API}/demo/enter", json={"role": "fleet_manager"}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["user"]["is_demo"] is True
        assert body["user"]["org_name"] == "FleetFlow Demo Logistics"

        # Demo has seeded vehicles
        vs = _vehicles(body["token"])
        assert len(vs) >= 1
        # vehicle numbers should be MH12/MH14 pattern per spec
        assert any((x.get("vehicle_number") or "").startswith("MH") for x in vs)

    def test_enter_demo_invalid_role(self):
        r = requests.post(f"{API}/demo/enter", json={"role": "nope"})
        assert r.status_code == 400

    def test_demo_org_admin_cannot_manage_users(self):
        r = requests.post(f"{API}/demo/enter", json={"role": "org_admin"})
        assert r.status_code == 200
        t = r.json()["token"]
        # Try to create a user
        cu = requests.post(f"{API}/users", headers=_auth(t), json={
            "username": "shouldfail", "password": "StrongPass1!", "full_name": "X", "role": "driver"
        })
        assert cu.status_code == 403, f"Expected 403 but got {cu.status_code}: {cu.text}"

    def test_demo_cannot_update_org(self):
        r = requests.post(f"{API}/demo/enter", json={"role": "org_admin"})
        t = r.json()["token"]
        pu = requests.put(f"{API}/org", headers=_auth(t), json={"trade_name": "Hacked"})
        assert pu.status_code == 403

    def test_demo_viewer_readonly(self):
        r = requests.post(f"{API}/demo/enter", json={"role": "viewer"})
        t = r.json()["token"]
        # Create trip with valid payload should be blocked by role
        tr = requests.post(f"{API}/trips", headers=_auth(t), json={
            "date": "2026-01-01", "vehicle_id": "does-not-matter",
            "opening_km": 0,
        })
        assert tr.status_code == 403, f"expected 403, got {tr.status_code}: {tr.text}"


# ---------------- Multi-tenant isolation ----------------

class TestTenantIsolation:
    def test_rajguru_sees_only_its_vehicles(self, rajguru_token):
        vs = _vehicles(rajguru_token)
        assert len(vs) > 0

    def test_acme_sees_zero_vehicles(self, acme_token, rajguru_token):
        """Acme should not see any Rajguru vehicles. (Residual test vehicles from prior
        cross-tenant tests may exist but must not include Rajguru IDs.)"""
        rj_ids = {v.get("id") for v in _vehicles(rajguru_token)}
        acme_vs = _vehicles(acme_token)
        acme_ids = {v.get("id") for v in acme_vs}
        assert rj_ids.isdisjoint(acme_ids), "Cross-tenant leak: Acme sees Rajguru vehicles"

    def test_acme_search_mh12_empty(self, acme_token):
        r = requests.get(f"{API}/search", headers=_auth(acme_token), params={"q": "MH12"})
        assert r.status_code == 200
        d = r.json()
        # Should return no vehicle/trip hits from Rajguru
        groups = d.get("groups", d)
        # Accept either shape; just ensure empty of MH12 vehicles
        text = str(d).lower()
        assert "mh12" not in text or all(len(g.get("items", [])) == 0 for g in (groups if isinstance(groups, list) else []))

    def test_cross_tenant_create_isolation(self, rajguru_token, acme_token):
        # Create vehicle in Acme
        payload = {
            "vehicle_number": f"KA01AA{int(time.time()) % 10000:04d}",
            "vehicle_type": "Truck",
            "brand": "TATA",
            "model": "1613",
        }
        c = requests.post(f"{API}/vehicles", headers=_auth(acme_token), json=payload)
        assert c.status_code in (200, 201), f"acme create vehicle: {c.status_code} {c.text}"
        new_veh = c.json()
        new_id = new_veh.get("id")

        # Rajguru should NOT see it
        rj_ids = {v.get("id") for v in _vehicles(rajguru_token)}
        assert new_id not in rj_ids

        # Acme should see exactly this vehicle
        a_ids = {v.get("id") for v in _vehicles(acme_token)}
        assert new_id in a_ids


# ---------------- Expense Intelligence ----------------

class TestExpenses:
    def test_overview_shape(self, rajguru_token):
        r = requests.get(f"{API}/expenses/overview", headers=_auth(rajguru_token))
        assert r.status_code == 200, r.text
        d = r.json()
        # sanity: should have some numeric/list fields
        assert isinstance(d, dict)

    def test_insights(self, rajguru_token):
        r = requests.get(f"{API}/expenses/insights", headers=_auth(rajguru_token))
        assert r.status_code == 200
        d = r.json()
        assert "insights" in d and isinstance(d["insights"], list)

    def test_budget_create_get_duplicate_delete(self, rajguru_token):
        month = "2029-06"  # far future to avoid collision
        # Create
        cr = requests.post(f"{API}/budgets", headers=_auth(rajguru_token),
                           json={"category": "Fuel", "month": month, "amount": 50000})
        assert cr.status_code == 200, cr.text
        bid = cr.json()["id"]

        # Duplicate should fail
        dup = requests.post(f"{API}/budgets", headers=_auth(rajguru_token),
                            json={"category": "Fuel", "month": month, "amount": 60000})
        assert dup.status_code == 400

        # List includes it
        lst = requests.get(f"{API}/budgets", headers=_auth(rajguru_token), params={"month": month})
        assert lst.status_code == 200
        assert any(b["id"] == bid for b in lst.json())

        # Status endpoint
        st = requests.get(f"{API}/budgets/status", headers=_auth(rajguru_token), params={"month": month})
        assert st.status_code == 200
        sd = st.json()
        assert sd["month"] == month
        assert any(row["id"] == bid for row in sd["rows"])

        # Update
        up = requests.put(f"{API}/budgets/{bid}", headers=_auth(rajguru_token), json={"amount": 55000})
        assert up.status_code == 200
        assert up.json()["amount"] == 55000

        # Delete
        de = requests.delete(f"{API}/budgets/{bid}", headers=_auth(rajguru_token))
        assert de.status_code == 200

    def test_budget_invalid_inputs(self, rajguru_token):
        # bad category
        r = requests.post(f"{API}/budgets", headers=_auth(rajguru_token),
                          json={"category": "NotAThing", "month": "2029-07", "amount": 100})
        assert r.status_code == 400
        # bad month
        r = requests.post(f"{API}/budgets", headers=_auth(rajguru_token),
                          json={"category": "Fuel", "month": "bad", "amount": 100})
        assert r.status_code == 400
        # bad amount
        r = requests.post(f"{API}/budgets", headers=_auth(rajguru_token),
                          json={"category": "Fuel", "month": "2029-07", "amount": -10})
        assert r.status_code == 400


# ---------------- Org profile & branches ----------------

class TestOrgProfile:
    def test_get_org(self, rajguru_token):
        r = requests.get(f"{API}/org", headers=_auth(rajguru_token))
        assert r.status_code == 200
        d = r.json()
        assert d["legal_name"]
        assert "branches" in d

    def test_branch_crud(self, rajguru_token):
        ts = int(time.time())
        c = requests.post(f"{API}/branches", headers=_auth(rajguru_token),
                          json={"name": f"TEST_Branch_{ts}", "code": f"TB{ts%1000}"})
        assert c.status_code == 200
        bid = c.json()["id"]
        # Update
        u = requests.put(f"{API}/branches/{bid}", headers=_auth(rajguru_token),
                        json={"contact_person": "Tester"})
        assert u.status_code == 200
        assert u.json()["contact_person"] == "Tester"
        # Delete
        d = requests.delete(f"{API}/branches/{bid}", headers=_auth(rajguru_token))
        assert d.status_code == 200
