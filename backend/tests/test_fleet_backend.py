"""
Backend test suite for Rajguru Foods Fleet Management.
Covers auth, vehicles, drivers, documents, trips, fuel, services, repairs,
tyres+events, fastag, downtime, expenses (ledger + manual), reports
(generate + Excel/PDF export), upload/files, users/role, dashboard, alerts.
"""
import os
import io
import uuid
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SESSION_TOKEN = "test_session_main"


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {SESSION_TOKEN}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def unauth_client():
    return requests.Session()


@pytest.fixture(scope="session")
def vehicle_id(client):
    """Create a fresh test vehicle for destructive tests."""
    vnum = f"TEST KA {uuid.uuid4().hex[:4].upper()} 9999"
    r = client.post(f"{API}/vehicles", json={
        "vehicle_number": vnum, "make": "Tata", "model": "407",
        "fuel_type": "diesel", "current_odometer": 50000,
        "fastag_number": f"FT{uuid.uuid4().hex[:6]}", "fastag_balance": 1000
    })
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    yield vid
    # cleanup at end
    client.delete(f"{API}/vehicles/{vid}")


@pytest.fixture(scope="session")
def seeded_vehicle_id(client):
    r = client.get(f"{API}/vehicles")
    assert r.status_code == 200
    for v in r.json():
        if v["vehicle_number"] == "MH 12 AB 1234":
            return v["id"]
    pytest.skip("Seeded vehicle MH 12 AB 1234 not found")


# ===== Auth =====
class TestAuth:
    def test_me_with_bearer(self, client):
        r = client.get(f"{API}/auth/me")
        assert r.status_code == 200
        u = r.json()
        assert u["user_id"] == "test-user-main"
        assert u["role"] == "management"
        assert "_id" not in u

    def test_protected_requires_auth(self, unauth_client):
        r = unauth_client.get(f"{API}/vehicles")
        assert r.status_code == 401

    def test_invalid_token_401(self, unauth_client):
        r = unauth_client.get(f"{API}/vehicles",
                              headers={"Authorization": "Bearer not_real"})
        assert r.status_code == 401


# ===== Vehicles =====
class TestVehicles:
    def test_list(self, client):
        r = client.get(f"{API}/vehicles")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_get_update_delete(self, client):
        vnum = f"TEST DL {uuid.uuid4().hex[:4].upper()} 1"
        c = client.post(f"{API}/vehicles", json={
            "vehicle_number": vnum, "current_odometer": 100})
        assert c.status_code == 200
        vid = c.json()["id"]
        # GET via list
        listed = client.get(f"{API}/vehicles").json()
        assert any(x["id"] == vid for x in listed)
        # update
        u = client.put(f"{API}/vehicles/{vid}", json={
            "vehicle_number": vnum, "make": "Mahindra"})
        assert u.status_code == 200
        listed2 = {x["id"]: x for x in client.get(f"{API}/vehicles").json()}
        assert listed2[vid]["make"] == "Mahindra"
        # summary
        s = client.get(f"{API}/vehicles/{vid}/summary")
        assert s.status_code == 200
        assert s.json()["vehicle"]["id"] == vid
        # delete
        d = client.delete(f"{API}/vehicles/{vid}")
        assert d.status_code == 200
        listed3 = client.get(f"{API}/vehicles").json()
        assert not any(x["id"] == vid for x in listed3)

    def test_summary_seeded(self, client, seeded_vehicle_id):
        r = client.get(f"{API}/vehicles/{seeded_vehicle_id}/summary")
        assert r.status_code == 200
        data = r.json()
        assert data["vehicle"]["id"] == seeded_vehicle_id
        # summary returns counts/aggregates keyed differently — verify shape
        assert any(k in data for k in ("avg_mileage", "cost_per_km"))


# ===== Drivers =====
class TestDrivers:
    def test_create_list_delete(self, client, vehicle_id):
        r = client.post(f"{API}/drivers", json={
            "name": f"TEST_Driver_{uuid.uuid4().hex[:4]}",
            "license_number": "DL12345",
            "license_expiry": (date.today() + timedelta(days=20)).isoformat(),
            "assigned_vehicle_id": vehicle_id
        })
        assert r.status_code == 200
        did = r.json()["id"]
        lst = client.get(f"{API}/drivers").json()
        assert any(x["id"] == did for x in lst)
        # stats
        st = client.get(f"{API}/drivers/{did}/stats")
        assert st.status_code == 200
        client.delete(f"{API}/drivers/{did}")


# ===== Documents =====
class TestDocuments:
    def test_create_expiring(self, client, vehicle_id):
        r = client.post(f"{API}/documents", json={
            "vehicle_id": vehicle_id, "doc_type": "Insurance",
            "doc_number": "INS-TEST", "issue_date": "2026-01-01",
            "expiry_date": (date.today() + timedelta(days=10)).isoformat()
        })
        assert r.status_code == 200
        did = r.json()["id"]
        lst = client.get(f"{API}/documents").json()
        assert any(x["id"] == did for x in lst)


# ===== Trips =====
class TestTrips:
    def test_trip_create_close_updates_odo(self, client, vehicle_id):
        # opening km = 50000 (vehicle initial). Create trip
        r = client.post(f"{API}/trips", json={
            "date": date.today().isoformat(),
            "vehicle_id": vehicle_id, "opening_km": 50000,
            "origin": "A", "destination": "B"
        })
        assert r.status_code == 200, r.text
        trip = r.json()
        assert trip["status"] == "ongoing"
        tid = trip["id"]
        # close
        c = client.patch(f"{API}/trips/{tid}/close",
                         json={"closing_km": 50150})
        assert c.status_code == 200
        cd = c.json()
        assert cd["status"] == "completed"
        assert cd["distance"] == 150
        # vehicle odo updated
        v = next(x for x in client.get(f"{API}/vehicles").json()
                 if x["id"] == vehicle_id)
        assert v["current_odometer"] >= 50150


# ===== Fuel auto-mileage =====
class TestFuel:
    def test_two_entries_mileage(self, client, vehicle_id):
        # entry 1 (no prior, mileage=None)
        e1 = client.post(f"{API}/fuel", json={
            "date": "2026-01-05", "vehicle_id": vehicle_id,
            "odometer": 60000, "quantity": 20, "amount": 2000
        })
        assert e1.status_code == 200
        # entry 2
        e2 = client.post(f"{API}/fuel", json={
            "date": "2026-01-10", "vehicle_id": vehicle_id,
            "odometer": 60400, "quantity": 40, "amount": 4000
        })
        assert e2.status_code == 200
        d2 = e2.json()
        # mileage = (60400-60000)/40 = 10 km/L
        assert d2.get("mileage") is not None
        assert abs(d2["mileage"] - 10.0) < 0.01


# ===== Services =====
class TestServices:
    def test_service_creates_and_dues(self, client, vehicle_id):
        r = client.post(f"{API}/services", json={
            "vehicle_id": vehicle_id, "service_type": "oil_change",
            "date": date.today().isoformat(), "cost": 1500,
            "next_due_date": (date.today() + timedelta(days=3)).isoformat()
        })
        assert r.status_code == 200
        # Check alert
        a = client.get(f"{API}/alerts").json()
        assert any(al["type"] == "service_due" for al in a)


# ===== Repairs =====
class TestRepairs:
    def test_minor_immediately_completed(self, client, vehicle_id):
        r = client.post(f"{API}/repairs", json={
            "vehicle_id": vehicle_id, "repair_type": "minor",
            "issue": "small leak", "date": date.today().isoformat(),
            "cost": 200
        })
        assert r.status_code == 200
        assert r.json()["status"] == "completed"

    def test_major_workflow(self, client, vehicle_id):
        r = client.post(f"{API}/repairs", json={
            "vehicle_id": vehicle_id, "repair_type": "major",
            "issue": "engine failure", "date": date.today().isoformat(),
            "cost": 50000
        })
        assert r.status_code == 200, r.text
        rd = r.json()
        assert rd["status"] == "reported"
        rid = rd["id"]
        # approve
        a = client.patch(f"{API}/repairs/{rid}/status",
                        json={"status": "approved"})
        assert a.status_code == 200, a.text
        assert a.json()["status"] == "approved"
        # start
        s = client.patch(f"{API}/repairs/{rid}/status",
                        json={"status": "in_repair"})
        assert s.status_code == 200
        assert s.json()["status"] == "in_repair"
        # complete
        c = client.patch(f"{API}/repairs/{rid}/status",
                        json={"status": "completed"})
        assert c.status_code == 200
        assert c.json()["status"] == "completed"


# ===== Tyres & Events =====
class TestTyres:
    def test_tyre_and_replacement_event(self, client, vehicle_id):
        t = client.post(f"{API}/tyres", json={
            "vehicle_id": vehicle_id, "tyre_number": f"T{uuid.uuid4().hex[:6]}",
            "brand": "MRF", "installation_date": "2026-01-01",
            "installation_km": 50000
        })
        assert t.status_code == 200
        tid = t.json()["id"]
        # puncture event
        p = client.post(f"{API}/tyre-events", json={
            "tyre_id": tid, "vehicle_id": vehicle_id,
            "event_type": "puncture", "date": date.today().isoformat(),
            "cost": 100
        })
        assert p.status_code == 200
        # replacement -> tyre status becomes removed
        rep = client.post(f"{API}/tyre-events", json={
            "tyre_id": tid, "vehicle_id": vehicle_id,
            "event_type": "replacement", "date": date.today().isoformat()
        })
        assert rep.status_code == 200
        # tyre marked removed
        t_after = next(x for x in client.get(f"{API}/tyres").json()
                       if x["id"] == tid)
        assert t_after["status"] in ("removed", "replaced")


# ===== Fastag balance =====
class TestFastag:
    def test_recharge_then_toll(self, client, vehicle_id):
        before = next(x for x in client.get(f"{API}/vehicles").json()
                      if x["id"] == vehicle_id).get("fastag_balance") or 0
        # recharge +500
        r = client.post(f"{API}/fastag", json={
            "vehicle_id": vehicle_id, "txn_type": "recharge",
            "date": date.today().isoformat(), "amount": 500
        })
        assert r.status_code == 200
        # toll -100
        t = client.post(f"{API}/fastag", json={
            "vehicle_id": vehicle_id, "txn_type": "toll",
            "date": date.today().isoformat(), "amount": 100,
            "toll_plaza": "X"
        })
        assert t.status_code == 200
        after = next(x for x in client.get(f"{API}/vehicles").json()
                     if x["id"] == vehicle_id).get("fastag_balance") or 0
        assert abs((after - before) - 400) < 0.01


# ===== Downtime =====
class TestDowntime:
    def test_downtime_computes_days(self, client, vehicle_id):
        r = client.post(f"{API}/downtime", json={
            "vehicle_id": vehicle_id, "reason": "service",
            "start_date": "2026-01-01", "end_date": "2026-01-05"
        })
        assert r.status_code == 200
        d = r.json()
        assert d.get("days") in (4, 5)  # inclusive or exclusive both ok
        assert d.get("status") == "closed"


# ===== Expenses Manual + Ledger =====
class TestExpenses:
    def test_manual_expense_crud(self, client, vehicle_id):
        r = client.post(f"{API}/expenses", json={
            "vehicle_id": vehicle_id, "category": "misc",
            "date": date.today().isoformat(), "amount": 250
        })
        assert r.status_code == 200
        eid = r.json()["id"]
        lst = client.get(f"{API}/expenses").json()
        assert any(x["id"] == eid for x in lst)
        client.delete(f"{API}/expenses/{eid}")

    def test_ledger_aggregates(self, client, vehicle_id):
        r = client.get(f"{API}/expenses/ledger",
                       params={"vehicle_id": vehicle_id})
        assert r.status_code == 200
        data = r.json()
        # Backend uses 'rows' / 'total' for ledger
        assert "rows" in data
        assert "total" in data
        assert data["total"] >= 0


# ===== Reports & Export =====
class TestReports:
    def test_list_reports(self, client):
        r = client.get(f"{API}/reports")
        assert r.status_code == 200
        keys = [x["key"] for x in r.json()]
        for k in ("trips", "fuel", "services", "repairs",
                  "documents", "expenses"):
            assert k in keys

    def test_generate_trips(self, client):
        r = client.get(f"{API}/reports/trips")
        assert r.status_code == 200
        data = r.json()
        assert "columns" in data and "rows" in data

    def test_export_excel(self, client):
        r = client.get(f"{API}/reports/trips/export",
                       params={"format": "excel"})
        assert r.status_code == 200
        assert len(r.content) > 100
        # xlsx zip signature
        assert r.content[:2] == b"PK"

    def test_export_pdf(self, client):
        r = client.get(f"{API}/reports/expenses/export",
                       params={"format": "pdf"})
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"


# ===== Upload / Files =====
class TestFiles:
    def test_upload_and_get(self, client):
        data = b"hello-file-bytes"
        files = {"file": ("hello.txt", io.BytesIO(data), "text/plain")}
        # remove json content-type for multipart
        h = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        r = requests.post(f"{API}/upload", files=files, headers=h)
        assert r.status_code == 200, r.text
        fid = r.json().get("id") or r.json().get("file_id")
        assert fid
        g = requests.get(f"{API}/files/{fid}", headers=h)
        assert g.status_code == 200
        assert g.content == data


# ===== Dashboard / Alerts =====
class TestDashboard:
    def test_dashboard(self, client):
        r = client.get(f"{API}/dashboard")
        assert r.status_code == 200
        d = r.json()
        for k in ("compliance", "operations", "fuel", "maintenance",
                  "financial", "alerts"):
            assert k in d

    def test_alerts(self, client):
        r = client.get(f"{API}/alerts")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ===== Users / Role =====
class TestUsers:
    def test_list_users(self, client):
        r = client.get(f"{API}/users")
        assert r.status_code == 200
        users = r.json()
        assert any(u["user_id"] == "test-user-main" for u in users)

    def test_role_update_roundtrip(self, client):
        # Create a sandbox user so we don't downgrade ourselves
        import pymongo, os as _os
        cli = pymongo.MongoClient(_os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = cli[_os.environ.get("DB_NAME", "test_database")]
        uid = f"test-user-role-{uuid.uuid4().hex[:6]}"
        db.users.insert_one({"user_id": uid, "email": f"{uid}@example.com",
                             "name": "Role Sandbox", "role": "driver",
                             "picture": ""})
        try:
            r = client.patch(f"{API}/users/{uid}/role",
                             json={"role": "fleet_manager"})
            assert r.status_code == 200, r.text
            back = client.patch(f"{API}/users/{uid}/role",
                                json={"role": "driver"})
            assert back.status_code == 200, back.text
        finally:
            db.users.delete_one({"user_id": uid})
