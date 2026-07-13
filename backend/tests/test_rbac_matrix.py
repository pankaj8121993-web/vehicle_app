"""RBAC module-access matrix tests (iteration 6)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://vehicle-central-17.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _enter(role):
    r = requests.post(f"{API}/demo/enter", json={"role": role}, timeout=30)
    assert r.status_code == 200, f"demo/enter {role} failed: {r.status_code} {r.text}"
    data = r.json()
    return data["token"], data["user"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


# -------- Driver ---------
class TestDriverRBAC:
    @classmethod
    def setup_class(cls):
        cls.tok, cls.user = _enter("driver")

    def test_user_modules(self):
        expected = {"dashboard", "documents", "trips", "fuel", "repairs", "accidents"}
        assert set(self.user["modules"]) == expected, self.user["modules"]
        # search, reports, vehicles, drivers, fleet-status, compliance etc. NOT in modules
        for m in ["search", "reports", "vehicles", "drivers", "fleet-status", "compliance",
                  "expenses", "tyres", "fastag", "downtime", "vendors", "maintenance", "calendar"]:
            assert m not in self.user["modules"], m

    @pytest.mark.parametrize("path", [
        "/reports", "/fleet-status", "/compliance", "/expenses/ledger",
        "/expenses/overview", "/tyres", "/fastag", "/downtime", "/vendors",
        "/drivers", "/search?q=MH",
    ])
    def test_forbidden(self, path):
        r = requests.get(f"{API}{path}", headers=_hdr(self.tok), timeout=30)
        assert r.status_code == 403, f"{path} -> {r.status_code} {r.text[:200]}"

    @pytest.mark.parametrize("path", [
        "/vehicles", "/trips", "/fuel", "/repairs", "/accidents", "/documents", "/drivers/active",
    ])
    def test_allowed(self, path):
        r = requests.get(f"{API}{path}", headers=_hdr(self.tok), timeout=30)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"


# -------- Maintenance ---------
class TestMaintenanceRBAC:
    @classmethod
    def setup_class(cls):
        cls.tok, cls.user = _enter("maintenance")

    def test_modules(self):
        mods = set(self.user["modules"])
        assert "maintenance" in mods and "tyres" in mods and "vehicles" in mods
        assert "reports" not in mods
        assert "expenses" not in mods

    def test_apis(self):
        assert requests.get(f"{API}/services", headers=_hdr(self.tok), timeout=30).status_code == 200
        assert requests.get(f"{API}/reports", headers=_hdr(self.tok), timeout=30).status_code == 403
        assert requests.get(f"{API}/expenses/overview", headers=_hdr(self.tok), timeout=30).status_code == 403


# -------- Accounts ---------
class TestAccountsRBAC:
    @classmethod
    def setup_class(cls):
        cls.tok, cls.user = _enter("accounts")

    def test_modules(self):
        mods = set(self.user["modules"])
        assert "reports" in mods
        assert "expenses" in mods

    def test_apis(self):
        assert requests.get(f"{API}/reports", headers=_hdr(self.tok), timeout=30).status_code == 200
        assert requests.get(f"{API}/expenses/overview", headers=_hdr(self.tok), timeout=30).status_code == 200
        r = requests.get(f"{API}/budgets/status", headers=_hdr(self.tok), timeout=30)
        assert r.status_code == 200, f"budgets/status {r.status_code} {r.text[:200]}"


# -------- Viewer ---------
class TestViewerRBAC:
    @classmethod
    def setup_class(cls):
        cls.tok, cls.user = _enter("viewer")

    def test_modules(self):
        mods = set(self.user["modules"])
        for m in ("reports", "expenses", "vehicles", "drivers", "fleet-status"):
            assert m in mods, m

    def test_reads_allowed(self):
        for p in ("/reports", "/expenses/overview", "/vehicles", "/drivers"):
            r = requests.get(f"{API}{p}", headers=_hdr(self.tok), timeout=30)
            assert r.status_code == 200, f"{p} -> {r.status_code}"

    def test_write_rejected(self):
        # attempt to create a trip with a valid payload so RBAC (not validation) triggers
        vehicles = requests.get(f"{API}/vehicles", headers=_hdr(self.tok), timeout=30).json()
        items = vehicles.get("items", vehicles) if isinstance(vehicles, dict) else vehicles
        vid = items[0]["id"] if items else "any"
        payload = {"date": "2026-01-01", "vehicle_id": vid, "opening_km": 1000, "purpose": "TEST_viewer_write"}
        r = requests.post(f"{API}/trips", json=payload, headers=_hdr(self.tok), timeout=30)
        assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text[:200]}"


# -------- Fleet Manager ---------
class TestFleetManagerRBAC:
    @classmethod
    def setup_class(cls):
        cls.tok, cls.user = _enter("fleet_manager")

    def test_modules(self):
        mods = set(self.user["modules"])
        for m in ("reports", "expenses", "org-settings", "vehicles", "drivers"):
            assert m in mods, m

    def test_apis(self):
        for p in ("/reports", "/expenses/overview", "/vehicles", "/drivers"):
            r = requests.get(f"{API}{p}", headers=_hdr(self.tok), timeout=30)
            assert r.status_code == 200, f"{p} {r.status_code}"


# -------- Admin login (Rajguru) ---------
class TestAdminLogin:
    @classmethod
    def setup_class(cls):
        r = requests.post(f"{API}/auth/login", json={"username": "admin", "password": "rajguru@2026"}, timeout=30)
        if r.status_code != 200:
            pytest.skip(f"admin login failed: {r.status_code} {r.text[:200]}")
        d = r.json()
        cls.tok = d["token"]
        cls.user = d["user"]

    def test_modules_full(self):
        mods = set(self.user["modules"])
        for m in ("reports", "expenses", "users", "org-settings", "search", "vehicles", "drivers"):
            assert m in mods, m

    def test_apis(self):
        for p in ("/reports", "/expenses/overview", "/vehicles", "/users", "/search?q=MH"):
            r = requests.get(f"{API}{p}", headers=_hdr(self.tok), timeout=30)
            assert r.status_code == 200, f"{p} {r.status_code} {r.text[:200]}"


# -------- Driver workflow endpoints (dropdowns) ---------
class TestDriverWorkflowSupport:
    @classmethod
    def setup_class(cls):
        cls.tok, cls.user = _enter("driver")

    def test_vehicle_list_for_form(self):
        r = requests.get(f"{API}/vehicles", headers=_hdr(self.tok), timeout=30)
        assert r.status_code == 200
        body = r.json()
        items = body.get("items") if isinstance(body, dict) else body
        assert isinstance(items, list) and len(items) > 0

    def test_drivers_active(self):
        r = requests.get(f"{API}/drivers/active", headers=_hdr(self.tok), timeout=30)
        assert r.status_code == 200
