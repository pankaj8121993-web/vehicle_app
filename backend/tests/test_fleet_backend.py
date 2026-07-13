"""
Rajguru Foods Fleet Management — backend tests (post-Checkpoint 2).
Auth model: username/password → opaque session token → Authorization: Bearer <token>.
The h(role) helper transparently logs in and caches tokens so legacy tests keep working.

Default seeded users (must_change_password=True on first boot — tests handle that):
  admin       / rajguru@2026
  manager     / manager@2026          (role=management)
  dataentry1  / dataentry@2026
  driver1     / driver@2026
  test        / test@2026
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://vehicle-central-17.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

SEEDED_VEHICLE_ID = "0e572cbb-d447-4107-a08b-e7c7f409c73b"

# Default credentials per spec — tests assume these (seeded on first boot)
CREDS = {
    "admin": ("admin", "rajguru@2026"),
    "management": ("manager", "manager@2026"),
    "data_entry": ("dataentry1", "dataentry@2026"),
    "driver": ("driver1", "driver@2026"),
    "test": ("test", "test@2026"),
}
NEW_PASSWORDS = {
    "admin": "Admin@Test1",
    "management": "Mgmt@Test1",
    "data_entry": "Data@Test1",
    "driver": "Driver@Test1",
    "test": "Test@Test1",
}

_TOKENS = {}


def _ensure_password_changed(role):
    """First-time login each user is forced to change password. Tests use NEW_PASSWORDS afterward."""
    username, original_pw = CREDS[role]
    new_pw = NEW_PASSWORDS[role]
    # Try login with new password first (idempotent across reruns)
    r = requests.post(f"{API}/auth/login", json={"username": username, "password": new_pw})
    if r.status_code == 200:
        return r.json()["token"]
    # Else use seeded password and change it
    r = requests.post(f"{API}/auth/login", json={"username": username, "password": original_pw})
    if r.status_code != 200:
        raise AssertionError(f"Initial login for {username} failed: {r.status_code} {r.text}")
    token = r.json()["token"]
    if r.json()["user"].get("must_change_password"):
        cp = requests.post(f"{API}/auth/change-password",
                           headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                           json={"current_password": original_pw, "new_password": new_pw})
        assert cp.status_code == 200, f"change-password for {username} failed: {cp.text}"
        # Session is preserved per spec; just re-login to be safe
        r2 = requests.post(f"{API}/auth/login", json={"username": username, "password": new_pw})
        assert r2.status_code == 200, r2.text
        return r2.json()["token"]
    return token


def _token(role):
    if role not in _TOKENS:
        _TOKENS[role] = _ensure_password_changed(role)
    return _TOKENS[role]


def h(role):
    return {"Authorization": f"Bearer {_token(role)}", "Content-Type": "application/json"}


# ---------------- Roles ----------------
class TestRoles:
    def test_list_roles(self):
        r = requests.get(f"{API}/roles", headers=h("admin"))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) == 12
        roles = [d["role"] for d in data]
        assert {"driver", "data_entry", "management", "admin", "test",
                "org_admin", "owner", "fleet_manager", "operations",
                "maintenance", "accounts", "viewer"} == set(roles)
        for d in data:
            assert "label" in d and "rights" in d


# ---------------- Pagination shape ----------------
class TestPagination:
    def test_trips_paginated(self):
        r = requests.get(f"{API}/trips?page=1&page_size=25", headers=h("admin"))
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, dict)
        for k in ("items", "total", "page", "page_size"):
            assert k in d
        assert d["page"] == 1 and d["page_size"] == 25
        assert isinstance(d["items"], list)

    def test_trips_all(self):
        r = requests.get(f"{API}/trips?all=true", headers=h("admin"))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_vehicles_paginated(self):
        r = requests.get(f"{API}/vehicles?page=1&page_size=25", headers=h("admin"))
        assert r.status_code == 200
        d = r.json()
        assert {"items", "total", "page", "page_size"}.issubset(d.keys())

    def test_vehicles_all(self):
        r = requests.get(f"{API}/vehicles?all=true", headers=h("admin"))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_drivers_paginated(self):
        r = requests.get(f"{API}/drivers?page=1&page_size=25", headers=h("admin"))
        assert r.status_code == 200
        d = r.json()
        assert {"items", "total", "page", "page_size"}.issubset(d.keys())

    def test_expenses_paginated(self):
        r = requests.get(f"{API}/expenses?page=1&page_size=25", headers=h("admin"))
        assert r.status_code == 200
        d = r.json()
        assert {"items", "total", "page", "page_size"}.issubset(d.keys())


# ---------------- RBAC: Driver ----------------
class TestRbacDriver:
    def test_driver_cannot_create_document(self):
        payload = {"vehicle_id": SEEDED_VEHICLE_ID, "doc_type": "RC",
                   "doc_number": "TEST_RC1", "expiry_date": "2027-01-01"}
        r = requests.post(f"{API}/documents", headers=h("driver"), json=payload)
        assert r.status_code == 403

    def test_driver_can_create_trip(self):
        payload = {
            "vehicle_id": SEEDED_VEHICLE_ID,
            "date": "2026-01-15",
            "origin": "TEST_Pune",
            "destination": "TEST_Mumbai",
            "opening_km": 10000,
            "status": "ongoing",
        }
        r = requests.post(f"{API}/trips", headers=h("driver"), json=payload)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert "id" in body
        # Cleanup as admin
        requests.delete(f"{API}/trips/{body['id']}", headers=h("admin"))

    def test_driver_cannot_update(self):
        # Need an existing trip to attempt update
        r0 = requests.get(f"{API}/trips?page=1&page_size=1", headers=h("admin"))
        items = r0.json().get("items", [])
        if not items:
            pytest.skip("No trips to update")
        tid = items[0]["id"]
        r = requests.put(f"{API}/trips/{tid}", headers=h("driver"), json={"origin": "X"})
        assert r.status_code == 403

    def test_driver_cannot_delete(self):
        r0 = requests.get(f"{API}/trips?page=1&page_size=1", headers=h("admin"))
        items = r0.json().get("items", [])
        if not items:
            pytest.skip("No trips")
        tid = items[0]["id"]
        r = requests.delete(f"{API}/trips/{tid}", headers=h("driver"))
        assert r.status_code == 403


# ---------------- RBAC: Data Entry ----------------
class TestRbacDataEntry:
    def test_data_entry_can_create_document(self):
        payload = {"vehicle_id": SEEDED_VEHICLE_ID, "doc_type": "PUC",
                   "doc_number": "TEST_PUC_DE", "expiry_date": "2027-06-01"}
        r = requests.post(f"{API}/documents", headers=h("data_entry"), json=payload)
        assert r.status_code in (200, 201), r.text
        did = r.json()["id"]
        # Verify can edit
        r2 = requests.put(f"{API}/documents/{did}", headers=h("data_entry"),
                          json={"doc_number": "TEST_PUC_DE2"})
        assert r2.status_code == 200
        # Cannot delete
        r3 = requests.delete(f"{API}/documents/{did}", headers=h("data_entry"))
        assert r3.status_code == 403
        # Admin cleanup
        requests.delete(f"{API}/documents/{did}", headers=h("admin"))


# ---------------- RBAC: Admin delete ----------------
class TestRbacAdminDelete:
    def test_admin_delete_works(self):
        payload = {"vehicle_id": SEEDED_VEHICLE_ID, "doc_type": "Other",
                   "doc_number": "TEST_DEL_ADM", "expiry_date": "2027-01-01"}
        c = requests.post(f"{API}/documents", headers=h("admin"), json=payload)
        assert c.status_code in (200, 201)
        did = c.json()["id"]
        r = requests.delete(f"{API}/documents/{did}", headers=h("admin"))
        assert r.status_code == 200


# ---------------- Repair approval RBAC ----------------
class TestRepairApproval:
    @pytest.fixture
    def repair_id(self):
        payload = {
            "vehicle_id": SEEDED_VEHICLE_ID,
            "date": "2026-01-10",
            "repair_type": "major",
            "issue": "TEST_engine_overhaul",
            "status": "reported",
        }
        r = requests.post(f"{API}/repairs", headers=h("data_entry"), json=payload)
        assert r.status_code in (200, 201), r.text
        rid = r.json()["id"]
        yield rid
        requests.delete(f"{API}/repairs/{rid}", headers=h("admin"))

    def test_data_entry_cannot_approve(self, repair_id):
        # Under new 7-stage flow, open→approved is invalid transition (400).
        # After moving to under_review, data_entry approving must return 403.
        requests.patch(f"{API}/repairs/{repair_id}/status",
                       headers=h("data_entry"), json={"status": "under_review"})
        r = requests.patch(f"{API}/repairs/{repair_id}/status",
                           headers=h("data_entry"), json={"status": "approved"})
        assert r.status_code == 403, f"Unexpected: {r.status_code} {r.text}"

    def test_management_can_approve(self, repair_id):
        # Move through the required flow before approval
        requests.patch(f"{API}/repairs/{repair_id}/status",
                       headers=h("data_entry"), json={"status": "under_review"})
        r = requests.patch(f"{API}/repairs/{repair_id}/status",
                           headers=h("management"), json={"status": "approved"})
        assert r.status_code == 200, r.text


# ---------------- Dashboard trends ----------------
class TestDashboard:
    def test_dashboard_basic(self):
        r = requests.get(f"{API}/dashboard", headers=h("admin"))
        assert r.status_code == 200
        d = r.json()
        for k in ("compliance", "operations", "fuel", "maintenance", "financial", "alerts"):
            assert k in d

    def test_dashboard_trends_6_months(self):
        r = requests.get(f"{API}/dashboard/trends", headers=h("admin"))
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, list) and len(d) == 6
        for m in d:
            assert {"month", "expense", "km", "fuel_cost"}.issubset(m.keys())


# ---------------- Driver stats ----------------
class TestDriverStats:
    def test_driver_stats(self):
        # Find first driver
        rd = requests.get(f"{API}/drivers?all=true", headers=h("admin"))
        assert rd.status_code == 200
        drivers = rd.json()
        if not drivers:
            pytest.skip("No drivers seeded")
        did = drivers[0]["id"]
        r = requests.get(f"{API}/drivers/{did}/stats", headers=h("admin"))
        assert r.status_code == 200
        s = r.json()
        for k in ("driver", "total_trips", "total_km", "fuel_entries", "total_fuel_cost", "accidents_count"):
            assert k in s


# ---------------- Fastag sync (SIMULATED) ----------------
class TestFastagSync:
    def test_sync_seeded_vehicle(self):
        r = requests.post(f"{API}/fastag/sync/{SEEDED_VEHICLE_ID}", headers=h("admin"))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("simulated") is True
        assert 4 <= d["synced_transactions"] <= 9
        assert isinstance(d["balance"], (int, float))

    def test_sync_unknown_vehicle(self):
        r = requests.post(f"{API}/fastag/sync/nonexistent-id-zzz", headers=h("admin"))
        assert r.status_code == 404

    def test_sync_vehicle_without_fastag(self):
        # Create a vehicle without fastag_number
        vid = None
        payload = {
            "vehicle_number": f"TEST_VH_{uuid.uuid4().hex[:6]}",
            "vehicle_type": "Truck",
            "make": "Tata",
            "model": "Test",
            "year": 2020,
        }
        c = requests.post(f"{API}/vehicles", headers=h("admin"), json=payload)
        assert c.status_code in (200, 201), c.text
        vid = c.json()["id"]
        try:
            r = requests.post(f"{API}/fastag/sync/{vid}", headers=h("admin"))
            assert r.status_code == 400, f"Expected 400 for vehicle w/o fastag, got {r.status_code}: {r.text}"
        finally:
            requests.delete(f"{API}/vehicles/{vid}", headers=h("admin"))


# ---------------- Reports regression ----------------
class TestReports:
    def test_list_reports(self):
        r = requests.get(f"{API}/reports", headers=h("admin"))
        assert r.status_code == 200
        assert isinstance(r.json(), list) and len(r.json()) >= 10

    def test_get_trips_report(self):
        r = requests.get(f"{API}/reports/trips", headers=h("admin"))
        assert r.status_code == 200
        d = r.json()
        assert "columns" in d and "rows" in d

    def test_export_excel(self):
        r = requests.get(f"{API}/reports/trips/export?format=excel", headers=h("admin"))
        assert r.status_code == 200
        assert "spreadsheet" in r.headers.get("content-type", "")

    def test_export_pdf(self):
        r = requests.get(f"{API}/reports/trips/export?format=pdf", headers=h("admin"))
        assert r.status_code == 200
        assert "pdf" in r.headers.get("content-type", "")


# ---------------- Expense ledger ----------------
class TestExpenseLedger:
    def test_ledger(self):
        r = requests.get(f"{API}/expenses/ledger", headers=h("admin"))
        assert r.status_code == 200
        d = r.json()
        for k in ("rows", "total", "by_category", "by_vehicle"):
            assert k in d


# ---------------- Vehicle summary ----------------
class TestVehicleSummary:
    def test_summary(self):
        r = requests.get(f"{API}/vehicles/{SEEDED_VEHICLE_ID}/summary", headers=h("admin"))
        assert r.status_code == 200
        d = r.json()
        for k in ("vehicle", "total_trips", "total_km", "total_operating_cost"):
            assert k in d


# ---------------- Phase 1: Driver Exit Management ----------------
class TestDriverExit:
    def _create_driver(self, name_prefix="TEST_EXIT"):
        payload = {"name": f"{name_prefix}_{uuid.uuid4().hex[:6]}", "mobile": "9999999999"}
        r = requests.post(f"{API}/drivers", headers=h("admin"), json=payload)
        assert r.status_code in (200, 201), r.text
        return r.json()

    def test_drivers_active_endpoint(self):
        r = requests.get(f"{API}/drivers/active", headers=h("admin"))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        for d in data:
            assert d.get("status") in ("active", "on_leave", None)

    def test_data_entry_cannot_set_resigned(self):
        d = self._create_driver()
        try:
            r = requests.put(f"{API}/drivers/{d['id']}", headers=h("data_entry"),
                             json={"status": "resigned"})
            assert r.status_code == 403, f"data_entry should not set resigned: {r.status_code} {r.text}"
        finally:
            requests.delete(f"{API}/drivers/{d['id']}", headers=h("admin"))

    def test_management_can_set_resigned_with_auto_exit_date(self):
        d = self._create_driver()
        try:
            r = requests.put(f"{API}/drivers/{d['id']}", headers=h("management"),
                             json={"status": "resigned"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["status"] == "resigned"
            assert body.get("exit_date"), "exit_date should be auto-filled"
            assert body.get("assigned_vehicle_id") in (None, ""), "vehicle should be unassigned on exit"
        finally:
            requests.delete(f"{API}/drivers/{d['id']}", headers=h("admin"))

    def test_terminate_requires_management(self):
        d = self._create_driver()
        try:
            # data_entry blocked
            r1 = requests.put(f"{API}/drivers/{d['id']}", headers=h("data_entry"),
                              json={"status": "terminated"})
            assert r1.status_code == 403
            # admin allowed
            r2 = requests.put(f"{API}/drivers/{d['id']}", headers=h("admin"),
                              json={"status": "terminated"})
            assert r2.status_code == 200
            assert r2.json().get("exit_date")
        finally:
            requests.delete(f"{API}/drivers/{d['id']}", headers=h("admin"))

    def test_delete_driver_blocked_when_has_trips(self):
        d = self._create_driver()
        trip_id = None
        try:
            # Create a trip referencing this driver
            tr = requests.post(f"{API}/trips", headers=h("admin"), json={
                "vehicle_id": SEEDED_VEHICLE_ID, "driver_id": d["id"],
                "date": "2026-01-20", "opening_km": 5000,
            })
            assert tr.status_code in (200, 201), tr.text
            trip_id = tr.json()["id"]
            # Now delete should fail
            r = requests.delete(f"{API}/drivers/{d['id']}", headers=h("admin"))
            assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        finally:
            if trip_id:
                requests.delete(f"{API}/trips/{trip_id}", headers=h("admin"))
            requests.delete(f"{API}/drivers/{d['id']}", headers=h("admin"))

    def test_active_endpoint_excludes_resigned(self):
        d = self._create_driver(name_prefix="TEST_RESIGN_EXCLUDED")
        try:
            requests.put(f"{API}/drivers/{d['id']}", headers=h("admin"),
                         json={"status": "resigned"})
            r = requests.get(f"{API}/drivers/active", headers=h("admin"))
            assert r.status_code == 200
            ids = [x["id"] for x in r.json()]
            assert d["id"] not in ids
        finally:
            requests.delete(f"{API}/drivers/{d['id']}", headers=h("admin"))


# ---------------- Phase 1: Vehicle Disposal ----------------
class TestVehicleDisposal:
    def _create_vehicle(self):
        payload = {"vehicle_number": f"TEST_DISP_{uuid.uuid4().hex[:6]}",
                   "vtype": "Truck", "make": "Tata", "model": "Test"}
        r = requests.post(f"{API}/vehicles", headers=h("admin"), json=payload)
        assert r.status_code in (200, 201), r.text
        return r.json()

    def test_data_entry_cannot_mark_sold(self):
        v = self._create_vehicle()
        try:
            r = requests.put(f"{API}/vehicles/{v['id']}", headers=h("data_entry"),
                             json={"status": "sold"})
            assert r.status_code == 403, r.text
        finally:
            requests.delete(f"{API}/vehicles/{v['id']}", headers=h("admin"))

    def test_management_can_sell_auto_date(self):
        v = self._create_vehicle()
        try:
            r = requests.put(f"{API}/vehicles/{v['id']}", headers=h("management"),
                             json={"status": "sold", "sale_value": 350000, "buyer_name": "Test Buyer"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["status"] == "sold"
            assert body.get("disposal_date")
            assert body.get("sale_value") == 350000
        finally:
            requests.delete(f"{API}/vehicles/{v['id']}", headers=h("admin"))

    def test_management_can_scrap_auto_date(self):
        v = self._create_vehicle()
        try:
            r = requests.put(f"{API}/vehicles/{v['id']}", headers=h("admin"),
                             json={"status": "scrapped"})
            assert r.status_code == 200, r.text
            assert r.json().get("disposal_date")
        finally:
            requests.delete(f"{API}/vehicles/{v['id']}", headers=h("admin"))

    def test_dashboard_excludes_disposed(self):
        v = self._create_vehicle()
        # Mark disposed
        requests.put(f"{API}/vehicles/{v['id']}", headers=h("admin"), json={"status": "scrapped"})
        try:
            r = requests.get(f"{API}/dashboard", headers=h("admin"))
            assert r.status_code == 200
            # Default vehicle list (no include_disposed) must NOT include it
            r2 = requests.get(f"{API}/vehicles?all=true", headers=h("admin"))
            assert v["id"] not in [x["id"] for x in r2.json()]
            # With include_disposed=true it IS there
            r3 = requests.get(f"{API}/vehicles?all=true&include_disposed=true", headers=h("admin"))
            assert v["id"] in [x["id"] for x in r3.json()]
        finally:
            requests.delete(f"{API}/vehicles/{v['id']}", headers=h("admin"))

    def test_delete_blocked_when_has_history(self):
        v = self._create_vehicle()
        tr_id = None
        try:
            tr = requests.post(f"{API}/trips", headers=h("admin"), json={
                "vehicle_id": v["id"], "date": "2026-01-21", "opening_km": 1000,
            })
            assert tr.status_code in (200, 201)
            tr_id = tr.json()["id"]
            r = requests.delete(f"{API}/vehicles/{v['id']}", headers=h("admin"))
            assert r.status_code == 400, f"Should block delete with history: {r.status_code} {r.text}"
            # After removing trip, delete should succeed
            requests.delete(f"{API}/trips/{tr_id}", headers=h("admin"))
            tr_id = None
            r2 = requests.delete(f"{API}/vehicles/{v['id']}", headers=h("admin"))
            assert r2.status_code == 200
        finally:
            if tr_id:
                requests.delete(f"{API}/trips/{tr_id}", headers=h("admin"))
            requests.delete(f"{API}/vehicles/{v['id']}", headers=h("admin"))


# ---------------- Phase 1: Drilldown endpoints ----------------
class TestDrilldowns:
    def test_docs_expiring(self):
        r = requests.get(f"{API}/drilldowns/docs_expiring?days=30", headers=h("admin"))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_docs_expired(self):
        r = requests.get(f"{API}/drilldowns/docs_expired", headers=h("admin"))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_vehicles_under_repair(self):
        r = requests.get(f"{API}/drilldowns/vehicles_under_repair", headers=h("admin"))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_service_due_windows(self):
        for w in ("due_soon", "overdue", "due_or_overdue"):
            r = requests.get(f"{API}/drilldowns/service_due?window={w}", headers=h("admin"))
            assert r.status_code == 200, f"{w}: {r.text}"
            assert isinstance(r.json(), list)

    def test_top_fuel_consumers(self):
        r = requests.get(f"{API}/drilldowns/top_fuel_consumers", headers=h("admin"))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        if data:
            assert "vehicle_number" in data[0] and "amount" in data[0]

    def test_top_cost_vehicles(self):
        r = requests.get(f"{API}/drilldowns/top_cost_vehicles", headers=h("admin"))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        if data:
            assert "total" in data[0] and "by_category" in data[0]

    def test_low_mileage_vehicles(self):
        r = requests.get(f"{API}/drilldowns/low_mileage_vehicles?threshold=100", headers=h("admin"))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_licenses_expiring(self):
        r = requests.get(f"{API}/drilldowns/licenses_expiring?days=365", headers=h("admin"))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_active_trips(self):
        r = requests.get(f"{API}/drilldowns/active_trips", headers=h("admin"))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_drilldowns_exclude_disposed_vehicles(self):
        # Create disposed vehicle + a doc that would expire — verify it's NOT in drilldown
        v_payload = {"vehicle_number": f"TEST_DL_{uuid.uuid4().hex[:6]}",
                     "vtype": "Truck", "make": "Tata", "model": "DL"}
        vc = requests.post(f"{API}/vehicles", headers=h("admin"), json=v_payload)
        vid = vc.json()["id"]
        doc_id = None
        try:
            past = "2020-01-01"
            dc = requests.post(f"{API}/documents", headers=h("admin"), json={
                "vehicle_id": vid, "doc_type": "RC", "doc_number": "TEST_DL",
                "expiry_date": past,
            })
            assert dc.status_code in (200, 201)
            doc_id = dc.json()["id"]
            # Should show in docs_expired
            r1 = requests.get(f"{API}/drilldowns/docs_expired", headers=h("admin"))
            assert vid in [x["vehicle_id"] for x in r1.json()]
            # Dispose vehicle
            requests.put(f"{API}/vehicles/{vid}", headers=h("admin"), json={"status": "scrapped"})
            # Now NOT in docs_expired
            r2 = requests.get(f"{API}/drilldowns/docs_expired", headers=h("admin"))
            assert vid not in [x["vehicle_id"] for x in r2.json()]
        finally:
            if doc_id:
                requests.delete(f"{API}/documents/{doc_id}", headers=h("admin"))
            requests.delete(f"{API}/vehicles/{vid}", headers=h("admin"))

    def test_licenses_expiring_excludes_resigned(self):
        from datetime import datetime, timedelta
        expiry = (datetime.utcnow() + timedelta(days=10)).strftime("%Y-%m-%d")
        payload = {"name": f"TEST_LIC_{uuid.uuid4().hex[:6]}",
                   "mobile": "9999999999", "license_number": "LIC123",
                   "license_expiry": expiry}
        r = requests.post(f"{API}/drivers", headers=h("admin"), json=payload)
        did = r.json()["id"]
        try:
            r1 = requests.get(f"{API}/drilldowns/licenses_expiring?days=30",
                              headers=h("admin"))
            assert did in [d["driver_id"] for d in r1.json()]
            requests.put(f"{API}/drivers/{did}", headers=h("admin"),
                         json={"status": "resigned"})
            r2 = requests.get(f"{API}/drilldowns/licenses_expiring?days=30",
                              headers=h("admin"))
            assert did not in [d["driver_id"] for d in r2.json()]
        finally:
            requests.delete(f"{API}/drivers/{did}", headers=h("admin"))


# ---------------- Phase 1.5: Greasing module + downtime auto-close ----------------
class TestGreasing:
    def test_greasing_crud(self):
        payload = {"vehicle_id": SEEDED_VEHICLE_ID, "date": "2026-02-01",
                   "odometer": 12000, "responsible_person": "TEST_PERSON",
                   "cost": 250, "next_due_date": "2026-05-01", "next_due_km": 18000}
        r = requests.post(f"{API}/greasings", headers=h("admin"), json=payload)
        assert r.status_code in (200, 201), r.text
        gid = r.json()["id"]
        try:
            r2 = requests.get(f"{API}/greasings?page=1&page_size=25", headers=h("admin"))
            assert r2.status_code == 200
            assert {"items", "total", "page", "page_size"}.issubset(r2.json().keys())
            # Driver can NOT create greasing (driver_can_create=False)
            r3 = requests.post(f"{API}/greasings", headers=h("driver"), json=payload)
            assert r3.status_code == 403
            # data_entry can edit
            r4 = requests.put(f"{API}/greasings/{gid}", headers=h("data_entry"),
                              json={"cost": 300})
            assert r4.status_code == 200
            assert r4.json()["cost"] == 300
        finally:
            requests.delete(f"{API}/greasings/{gid}", headers=h("admin"))

    def test_greasing_dashboard_widgets(self):
        r = requests.get(f"{API}/dashboard", headers=h("admin"))
        assert r.status_code == 200
        m = r.json()["maintenance"]
        assert "greasing_due" in m and "greasing_overdue" in m

    def test_greasing_due_drilldown(self):
        r = requests.get(f"{API}/drilldowns/greasing_due?window=due_or_overdue", headers=h("admin"))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_greasing_reports(self):
        r = requests.get(f"{API}/reports", headers=h("admin"))
        keys = [x["key"] for x in r.json()]
        assert "greasing" in keys and "greasing_due" in keys
        # Get the report works
        r2 = requests.get(f"{API}/reports/greasing", headers=h("admin"))
        assert r2.status_code == 200
        assert "columns" in r2.json() and "rows" in r2.json()


class TestDowntimeDisposalAutoClose:
    def test_disposal_closes_downtimes_with_days_set(self):
        # Create vehicle, create open downtime 10 days ago, dispose today
        from datetime import datetime, timedelta, timezone
        v_payload = {"vehicle_number": f"TEST_DT_{uuid.uuid4().hex[:6]}",
                     "vtype": "Truck", "make": "Tata", "model": "DT"}
        vc = requests.post(f"{API}/vehicles", headers=h("admin"), json=v_payload)
        vid = vc.json()["id"]
        ten_days_ago = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dt_id = None
        try:
            dt = requests.post(f"{API}/downtime", headers=h("admin"), json={
                "vehicle_id": vid, "reason": "service", "start_date": ten_days_ago,
            })
            assert dt.status_code in (200, 201)
            dt_id = dt.json()["id"]
            assert dt.json()["status"] == "open"
            # Dispose vehicle
            r = requests.put(f"{API}/vehicles/{vid}", headers=h("admin"),
                             json={"status": "sold", "disposal_date": today})
            assert r.status_code == 200
            # Verify downtime is closed with days set
            r2 = requests.get(f"{API}/downtime?all=true", headers=h("admin"))
            assert r2.status_code == 200
            ours = [d for d in r2.json() if d["id"] == dt_id]
            assert len(ours) == 1
            assert ours[0]["status"] == "closed"
            assert ours[0]["end_date"] == today
            assert ours[0]["days"] == 11  # 10 days inclusive
        finally:
            if dt_id:
                requests.delete(f"{API}/downtime/{dt_id}", headers=h("admin"))
            requests.delete(f"{API}/vehicles/{vid}", headers=h("admin"))


# ---------------- Phase 1.5: Driver enrichment ----------------
class TestDriverEnrichment:
    def test_driver_with_employee_number_and_skills(self):
        payload = {"name": f"TEST_ENR_{uuid.uuid4().hex[:6]}", "employee_number": "EMP-T001",
                   "skills": ["Heavy Commercial Vehicle", "Light Commercial Vehicle"]}
        r = requests.post(f"{API}/drivers", headers=h("admin"), json=payload)
        assert r.status_code in (200, 201)
        did = r.json()["id"]
        try:
            assert r.json()["employee_number"] == "EMP-T001"
            assert r.json()["skills"] == ["Heavy Commercial Vehicle", "Light Commercial Vehicle"]
            # Update skills
            r2 = requests.put(f"{API}/drivers/{did}", headers=h("admin"),
                              json={"skills": ["Tractor"]})
            assert r2.status_code == 200
            assert r2.json()["skills"] == ["Tractor"]
        finally:
            requests.delete(f"{API}/drivers/{did}", headers=h("admin"))


# ---------------- Checkpoint 2: Authentication ----------------
class TestAuth:
    def test_login_invalid_credentials(self):
        r = requests.post(f"{API}/auth/login", json={"username": "noone", "password": "nope"})
        assert r.status_code == 401

    def test_login_and_me(self):
        # The test harness performs the forced-password rotation. Use whichever password
        # is currently active (initial or rotated).
        username = CREDS["admin"][0]
        for pw in (NEW_PASSWORDS["admin"], CREDS["admin"][1]):
            r = requests.post(f"{API}/auth/login", json={"username": username, "password": pw})
            if r.status_code == 200:
                break
        assert r.status_code == 200, r.text
        token = r.json()["token"]
        assert r.json()["user"]["role"] == "admin"
        m = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert m.status_code == 200
        assert m.json()["username"] == username

    def test_unauthenticated_request_returns_401(self):
        r = requests.get(f"{API}/vehicles")
        assert r.status_code == 401
        r2 = requests.get(f"{API}/vehicles", headers={"Authorization": "Bearer not-a-token"})
        assert r2.status_code == 401

    def test_change_password_wrong_current(self):
        token = _token("management")
        r = requests.post(f"{API}/auth/change-password",
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                          json={"current_password": "wrong", "new_password": "anything123"})
        assert r.status_code == 400

    def test_change_password_too_short(self):
        token = _token("management")
        r = requests.post(f"{API}/auth/change-password",
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                          json={"current_password": NEW_PASSWORDS["management"], "new_password": "abc"})
        assert r.status_code == 400

    def test_logout_revokes_session(self):
        # Fresh login so we don't kill the cached test session.
        # _ensure_password_changed performs a fresh login and returns a valid
        # token regardless of whether the seeded password has been rotated yet.
        token = _ensure_password_changed("data_entry")
        # Verify session works
        m1 = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert m1.status_code == 200
        # Logout
        lo = requests.post(f"{API}/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert lo.status_code == 200
        # Now session is dead
        m2 = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert m2.status_code == 401


class TestUserManagement:
    def test_only_admin_lists_users(self):
        r_admin = requests.get(f"{API}/users", headers=h("admin"))
        assert r_admin.status_code == 200
        assert isinstance(r_admin.json(), list)
        assert all("password_hash" not in u for u in r_admin.json())
        r_other = requests.get(f"{API}/users", headers=h("management"))
        assert r_other.status_code == 403
        r_de = requests.get(f"{API}/users", headers=h("data_entry"))
        assert r_de.status_code == 403

    def test_create_user_lifecycle(self):
        uname = f"u_{uuid.uuid4().hex[:6]}"
        payload = {"username": uname, "password": "secret123",
                   "role": "data_entry", "full_name": "Lifecycle Test"}
        r = requests.post(f"{API}/users", headers=h("admin"), json=payload)
        assert r.status_code in (200, 201), r.text
        uid = r.json()["id"]
        assert r.json()["must_change_password"] is True
        try:
            # Login + change pw flow
            l1 = requests.post(f"{API}/auth/login", json={"username": uname, "password": "secret123"})
            assert l1.status_code == 200
            assert l1.json()["user"]["must_change_password"] is True
            tok = l1.json()["token"]
            cp = requests.post(f"{API}/auth/change-password",
                               headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                               json={"current_password": "secret123", "new_password": "newer123"})
            assert cp.status_code == 200
            l2 = requests.post(f"{API}/auth/login", json={"username": uname, "password": "newer123"})
            assert l2.status_code == 200
            assert l2.json()["user"]["must_change_password"] is False
            # Admin updates role
            upd = requests.put(f"{API}/users/{uid}", headers=h("admin"), json={"role": "management"})
            assert upd.status_code == 200
            assert upd.json()["role"] == "management"
            # Role change revokes prior sessions
            me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"})
            assert me.status_code == 401
            # Admin resets pw
            rp = requests.post(f"{API}/users/{uid}/reset-password", headers=h("admin"))
            assert rp.status_code == 200
            assert "temporary_password" in rp.json()
            temp = rp.json()["temporary_password"]
            l3 = requests.post(f"{API}/auth/login", json={"username": uname, "password": temp})
            assert l3.status_code == 200
            assert l3.json()["user"]["must_change_password"] is True
            # Deactivate via admin
            deact = requests.put(f"{API}/users/{uid}", headers=h("admin"), json={"is_active": False})
            assert deact.status_code == 200
            # Can't login while inactive
            blocked = requests.post(f"{API}/auth/login", json={"username": uname, "password": temp})
            assert blocked.status_code == 401
        finally:
            requests.delete(f"{API}/users/{uid}", headers=h("admin"))

    def test_cannot_delete_self(self):
        # Find admin's id via /auth/me
        m = requests.get(f"{API}/auth/me", headers=h("admin"))
        assert m.status_code == 200
        my_id = m.json()["id"]
        r = requests.delete(f"{API}/users/{my_id}", headers=h("admin"))
        assert r.status_code == 400

    def test_duplicate_username_rejected(self):
        uname = f"dup_{uuid.uuid4().hex[:6]}"
        payload = {"username": uname, "password": "secret123", "role": "driver", "full_name": "Dup1"}
        r = requests.post(f"{API}/users", headers=h("admin"), json=payload)
        assert r.status_code in (200, 201)
        uid = r.json()["id"]
        try:
            payload["full_name"] = "Dup2"
            r2 = requests.post(f"{API}/users", headers=h("admin"), json=payload)
            assert r2.status_code == 400
        finally:
            requests.delete(f"{API}/users/{uid}", headers=h("admin"))


class TestTestRoleSandbox:
    def test_test_user_creates_are_flagged_is_test_data(self):
        payload = {"vehicle_number": f"TEST_SBX_{uuid.uuid4().hex[:6]}",
                   "vtype": "Truck", "make": "Tata", "model": "Sandbox"}
        r = requests.post(f"{API}/vehicles", headers=h("test"), json=payload)
        assert r.status_code in (200, 201), r.text
        vid = r.json()["id"]
        assert r.json().get("is_test_data") is True
        try:
            # Real admin's list excludes test data
            list_admin = requests.get(f"{API}/vehicles?all=true", headers=h("admin"))
            assert vid not in [v["id"] for v in list_admin.json()]
            # Admin can opt-in via include_test=true
            list_admin_inc = requests.get(f"{API}/vehicles?all=true&include_test=true", headers=h("admin"))
            assert vid in [v["id"] for v in list_admin_inc.json()]
            # Test user's list shows ONLY test data
            list_test = requests.get(f"{API}/vehicles?all=true", headers=h("test"))
            ids = [v["id"] for v in list_test.json()]
            assert vid in ids
            assert SEEDED_VEHICLE_ID not in ids
        finally:
            requests.delete(f"{API}/vehicles/{vid}", headers=h("admin"))

    def test_test_cannot_modify_real_records(self):
        r = requests.put(f"{API}/vehicles/{SEEDED_VEHICLE_ID}", headers=h("test"),
                         json={"notes": "hack attempt"})
        assert r.status_code == 403
        r2 = requests.delete(f"{API}/vehicles/{SEEDED_VEHICLE_ID}", headers=h("test"))
        assert r2.status_code == 403

    def test_test_can_modify_own_records(self):
        # Test user creates a vehicle then edits & deletes it
        payload = {"vehicle_number": f"TEST_OWN_{uuid.uuid4().hex[:6]}", "vtype": "Truck"}
        r = requests.post(f"{API}/vehicles", headers=h("test"), json=payload)
        assert r.status_code in (200, 201)
        vid = r.json()["id"]
        try:
            upd = requests.put(f"{API}/vehicles/{vid}", headers=h("test"),
                               json={"notes": "edited by test user"})
            assert upd.status_code == 200
        finally:
            d = requests.delete(f"{API}/vehicles/{vid}", headers=h("test"))
            assert d.status_code == 200

    def test_purge_endpoint_admin_only(self):
        r_de = requests.post(f"{API}/admin/purge-test-data", headers=h("data_entry"))
        assert r_de.status_code == 403
        r_mgmt = requests.post(f"{API}/admin/purge-test-data", headers=h("management"))
        assert r_mgmt.status_code == 403
        r = requests.post(f"{API}/admin/purge-test-data", headers=h("admin"))
        assert r.status_code == 200
        assert "deleted" in r.json() and "total" in r.json()

    def test_dashboard_and_drilldowns_exclude_test_data(self):
        # Test user creates a vehicle + an expired doc → real admin's dashboard / docs_expired must not include it
        v = requests.post(f"{API}/vehicles", headers=h("test"),
                          json={"vehicle_number": f"TEST_EXC_{uuid.uuid4().hex[:6]}", "vtype": "Truck"})
        vid = v.json()["id"]
        doc_id = None
        try:
            d = requests.post(f"{API}/documents", headers=h("test"),
                              json={"vehicle_id": vid, "doc_type": "RC", "doc_number": "TEST_DOC",
                                    "expiry_date": "2020-01-01"})
            assert d.status_code in (200, 201)
            doc_id = d.json()["id"]
            # Verify it's NOT in docs_expired drilldown for admin
            r = requests.get(f"{API}/drilldowns/docs_expired", headers=h("admin"))
            assert vid not in [x["vehicle_id"] for x in r.json()]
        finally:
            if doc_id:
                requests.delete(f"{API}/documents/{doc_id}", headers=h("admin"))
            requests.delete(f"{API}/vehicles/{vid}", headers=h("admin"))


# ---------------- Phase 2 / Visibility cluster ----------------
class TestDriverMasterFields:
    def test_driver_with_full_statutory_and_license_categories(self):
        payload = {
            "name": f"TEST_FULL_{uuid.uuid4().hex[:6]}",
            "employee_number": "EMP-F001",
            "license_categories": ["LMV", "HMV"],
            "esi_number": "ESI-1234567890",
            "pf_uan_number": "UAN-9876543210",
            "emergency_contact_name": "Spouse Name",
            "emergency_contact_relationship": "Spouse",
            "emergency_contact_mobile": "9000000000",
        }
        r = requests.post(f"{API}/drivers", headers=h("admin"), json=payload)
        assert r.status_code in (200, 201), r.text
        did = r.json()["id"]
        try:
            d = r.json()
            assert d["license_categories"] == ["LMV", "HMV"]
            assert d["esi_number"] == "ESI-1234567890"
            assert d["pf_uan_number"] == "UAN-9876543210"
            assert d["emergency_contact_mobile"] == "9000000000"
        finally:
            requests.delete(f"{API}/drivers/{did}", headers=h("admin"))


class TestCompliance:
    def test_compliance_response_shape(self):
        r = requests.get(f"{API}/compliance", headers=h("admin"))
        assert r.status_code == 200
        body = r.json()
        for k in ("documents", "licenses", "services", "greasings", "fastag_low", "summary"):
            assert k in body
        s = body["summary"]
        for k in ("total_items", "expired", "expiring_7", "expiring_30", "expiring_90"):
            assert k in s and isinstance(s[k], int)

    def test_compliance_severity_filter(self):
        r = requests.get(f"{API}/compliance", headers=h("admin"), params={"severity": "danger"})
        assert r.status_code == 200
        for sect in ("documents", "licenses", "services", "greasings", "fastag_low"):
            for row in r.json()[sect]:
                assert row["severity"] == "danger"


class TestComplianceContacts:
    def test_crud_and_rbac(self):
        bad = requests.post(f"{API}/compliance/contacts", headers=h("data_entry"),
                            json={"compliance_type": "RC", "contact_person_name": "X", "mobile": "9"})
        assert bad.status_code == 403
        payload = {"compliance_type": "Insurance", "contact_person_name": f"Test {uuid.uuid4().hex[:4]}",
                   "mobile": "9988776655", "email": "x@example.com", "vendor_name": "Acme Insurance"}
        r = requests.post(f"{API}/compliance/contacts", headers=h("management"), json=payload)
        assert r.status_code in (200, 201), r.text
        cid = r.json()["id"]
        try:
            # Drivers no longer have access to the compliance module (RBAC matrix)
            r_drv = requests.get(f"{API}/compliance/contacts", headers=h("driver"))
            assert r_drv.status_code == 403
            r2 = requests.get(f"{API}/compliance/contacts", headers=h("data_entry"))
            assert r2.status_code == 200
            assert cid in [c["id"] for c in r2.json()]
            upd = requests.put(f"{API}/compliance/contacts/{cid}", headers=h("management"),
                               json={"notes": "test note"})
            assert upd.status_code == 200
            assert upd.json()["notes"] == "test note"
            d_de = requests.delete(f"{API}/compliance/contacts/{cid}", headers=h("data_entry"))
            assert d_de.status_code == 403
            d_mgmt = requests.delete(f"{API}/compliance/contacts/{cid}", headers=h("management"))
            assert d_mgmt.status_code == 403
        finally:
            requests.delete(f"{API}/compliance/contacts/{cid}", headers=h("admin"))

    def test_invalid_compliance_type_rejected(self):
        r = requests.post(f"{API}/compliance/contacts", headers=h("admin"),
                          json={"compliance_type": "Bogus", "contact_person_name": "X", "mobile": "9"})
        assert r.status_code == 400


class TestCalendar:
    def test_calendar_returns_events(self):
        r = requests.get(f"{API}/calendar", headers=h("admin"),
                         params={"start": "2026-01-01", "end": "2026-12-31"})
        assert r.status_code == 200
        body = r.json()
        assert "events" in body
        for e in body["events"]:
            for k in ("id", "title", "date", "type", "severity"):
                assert k in e

    def test_custom_event_crud(self):
        payload = {"title": f"Test Event {uuid.uuid4().hex[:4]}", "date": "2026-08-15",
                   "responsible_person": "Test Person", "notes": "test"}
        r = requests.post(f"{API}/calendar/events", headers=h("admin"), json=payload)
        assert r.status_code in (200, 201)
        eid = r.json()["id"]
        try:
            cal = requests.get(f"{API}/calendar", headers=h("admin"),
                               params={"start": "2026-08-01", "end": "2026-08-31"})
            ids = [e["id"] for e in cal.json()["events"]]
            assert eid in ids
            upd = requests.put(f"{API}/calendar/events/{eid}", headers=h("admin"),
                               json={"notes": "updated"})
            assert upd.status_code == 200
        finally:
            requests.delete(f"{API}/calendar/events/{eid}", headers=h("admin"))

    def test_recurrence_expansion(self):
        payload = {"title": f"Weekly {uuid.uuid4().hex[:4]}", "date": "2026-09-01",
                   "recurrence": "weekly", "recurrence_until": "2026-09-30"}
        r = requests.post(f"{API}/calendar/events", headers=h("admin"), json=payload)
        eid = r.json()["id"]
        try:
            cal = requests.get(f"{API}/calendar", headers=h("admin"),
                               params={"start": "2026-09-01", "end": "2026-09-30"})
            occurrences = [e for e in cal.json()["events"] if e.get("source_id") == eid]
            # Sep 1, 8, 15, 22, 29 → 5 weekly occurrences
            assert len(occurrences) == 5
        finally:
            requests.delete(f"{API}/calendar/events/{eid}", headers=h("admin"))


class TestFleetStatus:
    def test_fleet_status_shape(self):
        r = requests.get(f"{API}/fleet-status", headers=h("admin"))
        assert r.status_code == 200
        body = r.json()
        assert "rows" in body and "counts" in body and "total" in body and "as_of" in body
        for k in ("RUNNING", "IDLE", "UNDER_REPAIR", "DOWNTIME", "DISPOSED"):
            assert k in body["counts"]
        assert sum(body["counts"].values()) == body["total"]
        for row in body["rows"]:
            assert row["status"] in ("RUNNING", "IDLE", "UNDER_REPAIR", "DOWNTIME", "DISPOSED")


class TestVehicleStatistics:
    def test_statistics_response_shape(self):
        r = requests.get(f"{API}/vehicles/{SEEDED_VEHICLE_ID}/statistics", headers=h("admin"))
        assert r.status_code == 200
        body = r.json()
        for k in ("lifetime", "mileage_trend", "cost_composition", "monthly_cost_vs_km"):
            assert k in body
        L = body["lifetime"]
        for k in ("total_trips", "total_km", "total_fuel_litres", "total_fuel_cost",
                  "avg_mileage", "total_services", "total_greasings", "total_repairs",
                  "total_accidents", "total_operating_cost", "total_downtime_days",
                  "utilization_pct"):
            assert k in L


class TestVendors:
    def _mk(self, name=None, vtype="Repair"):
        payload = {"name": name or f"Vendor {uuid.uuid4().hex[:6]}", "vendor_type": vtype,
                   "mobile": "9998887777", "gst_number": "27ABC1234E1Z5"}
        return requests.post(f"{API}/vendors", headers=h("admin"), json=payload)

    def test_create_list_update_delete(self):
        r = self._mk(vtype="Tyre")
        assert r.status_code == 200, r.text
        vid = r.json()["id"]
        try:
            g = requests.get(f"{API}/vendors?all=true&vendor_type=Tyre", headers=h("admin"))
            assert any(v["id"] == vid for v in g.json())
            u = requests.put(f"{API}/vendors/{vid}", headers=h("admin"), json={"mobile": "1234567890"})
            assert u.status_code == 200 and u.json()["mobile"] == "1234567890"
        finally:
            d = requests.delete(f"{API}/vendors/{vid}", headers=h("admin"))
            assert d.status_code == 200

    def test_invalid_type_rejected(self):
        r = requests.post(f"{API}/vendors", headers=h("admin"),
                          json={"name": "X", "vendor_type": "Bogus"})
        assert r.status_code == 400

    def test_driver_forbidden_to_create(self):
        r = requests.post(f"{API}/vendors", headers=h("driver"),
                          json={"name": "Drv Vendor", "vendor_type": "Repair"})
        assert r.status_code == 403

    def test_active_only_filter(self):
        r1 = self._mk(name=f"ActiveV {uuid.uuid4().hex[:4]}")
        r2 = self._mk(name=f"InactiveV {uuid.uuid4().hex[:4]}")
        v1, v2 = r1.json()["id"], r2.json()["id"]
        try:
            requests.put(f"{API}/vendors/{v2}", headers=h("admin"), json={"is_active": False})
            g = requests.get(f"{API}/vendors?all=true&active_only=true", headers=h("admin"))
            ids = {v["id"] for v in g.json()}
            assert v1 in ids and v2 not in ids
        finally:
            for vid in (v1, v2):
                requests.delete(f"{API}/vendors/{vid}", headers=h("admin"))


class TestTicketWorkflow:
    def _create(self, role="data_entry", category="Engine"):
        payload = {"vehicle_id": SEEDED_VEHICLE_ID, "repair_type": "major",
                   "issue": f"Ticket test {uuid.uuid4().hex[:6]}", "date": "2026-06-15",
                   "ticket_category": category}
        r = requests.post(f"{API}/repairs", headers=h(role), json=payload)
        assert r.status_code == 200, r.text
        return r.json()

    def test_ticket_number_auto_generated(self):
        t = self._create()
        try:
            assert t["ticket_number"].startswith("TKT-2026-")
            assert t["status"] == "open"
        finally:
            requests.delete(f"{API}/repairs/{t['id']}", headers=h("admin"))

    def test_minor_repair_auto_closed(self):
        payload = {"vehicle_id": SEEDED_VEHICLE_ID, "repair_type": "minor",
                   "issue": "small fix", "date": "2026-06-15"}
        r = requests.post(f"{API}/repairs", headers=h("admin"), json=payload)
        try:
            assert r.status_code == 200 and r.json()["status"] == "closed"
        finally:
            requests.delete(f"{API}/repairs/{r.json()['id']}", headers=h("admin"))

    def test_full_seven_stage_workflow(self):
        t = self._create()
        tid = t["id"]
        try:
            stages = [
                ("under_review", "data_entry"),
                ("approved", "management"),
                ("sent_for_repair", "management"),
                ("in_repair", "management"),
                ("repaired", "management"),
                ("closed", "management"),
            ]
            for status, role in stages:
                extras = {"vendor": "V1"} if status == "sent_for_repair" else ({"cost": 5000} if status == "closed" else {})
                r = requests.patch(f"{API}/repairs/{tid}/status", headers=h(role),
                                   json={"status": status, **extras})
                assert r.status_code == 200, f"{status}: {r.text}"
                assert r.json()["status"] == status
            # Timestamps and 'by' fields populated
            final = requests.get(f"{API}/repairs?page_size=100", headers=h("admin")).json()
            row = next(x for x in final["items"] if x["id"] == tid)
            assert row.get("approved_at") and row.get("approved_by")
            assert row.get("closed_at") and row.get("closed_by")
            assert row.get("cost") == 5000
        finally:
            requests.delete(f"{API}/repairs/{tid}", headers=h("admin"))

    def test_invalid_transition_rejected(self):
        t = self._create()
        try:
            r = requests.patch(f"{API}/repairs/{t['id']}/status", headers=h("admin"),
                               json={"status": "in_repair"})
            assert r.status_code == 400
        finally:
            requests.delete(f"{API}/repairs/{t['id']}", headers=h("admin"))

    def test_data_entry_cannot_approve(self):
        t = self._create()
        tid = t["id"]
        try:
            requests.patch(f"{API}/repairs/{tid}/status", headers=h("data_entry"),
                           json={"status": "under_review"})
            r = requests.patch(f"{API}/repairs/{tid}/status", headers=h("data_entry"),
                               json={"status": "approved"})
            assert r.status_code == 403
        finally:
            requests.delete(f"{API}/repairs/{tid}", headers=h("admin"))

    def test_rejection_reason_persists(self):
        t = self._create()
        tid = t["id"]
        try:
            requests.patch(f"{API}/repairs/{tid}/status", headers=h("data_entry"),
                           json={"status": "under_review"})
            r = requests.patch(f"{API}/repairs/{tid}/status", headers=h("management"),
                               json={"status": "open", "rejection_reason": "Need photos"})
            assert r.status_code == 200
            assert r.json()["status"] == "open"
            assert r.json()["rejection_reason"] == "Need photos"
        finally:
            requests.delete(f"{API}/repairs/{tid}", headers=h("admin"))


class TestGlobalSearch:
    def test_search_min_length(self):
        r = requests.get(f"{API}/search?q=a", headers=h("admin"))
        assert r.status_code == 200
        body = r.json()
        for k in ("vehicles", "drivers", "tickets", "documents"):
            assert body[k] == []

    def test_search_finds_vehicle(self):
        v = requests.get(f"{API}/vehicles?all=true", headers=h("admin")).json()[0]
        q = v["vehicle_number"][:4]
        r = requests.get(f"{API}/search", headers=h("admin"), params={"q": q})
        assert r.status_code == 200
        ids = {x["id"] for x in r.json()["vehicles"]}
        assert v["id"] in ids

    def test_search_shape(self):
        r = requests.get(f"{API}/search?q=zz", headers=h("admin"))
        assert r.status_code == 200
        body = r.json()
        for k in ("vehicles", "drivers", "tickets", "documents"):
            assert isinstance(body[k], list)

    def test_search_excludes_test_data(self):
        # Create a test-tagged vendor & vehicle via test role; ensure search doesn't return them
        vname = f"ZZSEARCH_{uuid.uuid4().hex[:4]}"
        create = requests.post(f"{API}/vehicles", headers=h("test"),
                               json={"vehicle_number": vname, "make": "TestBrand", "model": "X"})
        vid = create.json().get("id")
        try:
            r = requests.get(f"{API}/search", headers=h("admin"), params={"q": vname})
            ids = {x["id"] for x in r.json()["vehicles"]}
            assert vid not in ids
        finally:
            if vid:
                requests.delete(f"{API}/vehicles/{vid}", headers=h("test"))



if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
