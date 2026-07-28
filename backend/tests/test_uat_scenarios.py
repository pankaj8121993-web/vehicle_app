"""
Phase 4 — Automated UAT scenario dry-run (real HTTP).

Walks the critical business scenarios end-to-end over the running app, mirroring
the manual cases in docs/uat/UAT_TEST_CASES.md. This is the *automated evidence*
that each workflow completes; the exhaustive edge-case coverage lives in the
Phase 3 suites (test_trip_operations, test_expense_settlement, …). Each test
here maps to a UAT-xx case id and proves the happy path (plus the key control)
runs green, so a human tester can focus on judgement rather than plumbing.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import server  # noqa: E402
import database  # noqa: E402
import session_security as ss  # noqa: E402

from conftest import realhttp_run as _run


class Client:
    def __init__(self, client, role, org_id):
        self.client, self.role, self.org_id = client, role, org_id

    def _h(self, method):
        if method in ss.SAFE_METHODS:
            return {}
        csrf = self.client.cookies.get(ss.CSRF_COOKIE)
        return {ss.CSRF_HEADER: csrf} if csrf else {}

    async def req(self, method, url, **kw):
        kw.setdefault("headers", {}).update(self._h(method))
        return await self.client.request(method, url, **kw)


_PW = "uat-" + "throwaway-passphrase"


async def _enter_demo(role):
    transport = ASGITransport(app=server.app)
    client = AsyncClient(transport=transport, base_url="http://uat")
    r = await client.post("/api/demo/enter", json={"role": role})
    assert r.status_code == 200, f"demo/enter {role}: {r.status_code} {r.text[:200]}"
    return Client(client, role, r.json()["user"]["org_id"])


async def _register_org(slug):
    transport = ASGITransport(app=server.app)
    client = AsyncClient(transport=transport, base_url="http://uatb")
    r = await client.post("/api/onboarding/register", json={
        "org": {"legal_name": f"UAT {slug} Ltd", "org_type": "Company"},
        "admin": {"username": f"uat_{slug}", "email": f"{slug}@uat.invalid",
                  "password": _PW, "full_name": f"UAT {slug}"}})
    assert r.status_code == 200, r.text[:200]
    return Client(client, "admin", r.json()["user"]["org_id"])


def _uniq(p):
    return f"{p}-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def env():
    async def build():
        await database.client.drop_database(database.raw_db.name)
        await database.raw_db.idempotency_keys.create_index(
            [("org_id", 1), ("scope", 1), ("key", 1)], name="uniq_org_scope_key", unique=True)
        admin = await _enter_demo("org_admin")
        viewer = await _enter_demo("viewer")
        beta = await _register_org("beta")
        return admin, viewer, beta

    admin, viewer, beta = _run(build())
    yield {"admin": admin, "viewer": viewer, "beta": beta}

    async def teardown():
        for c in (admin, viewer, beta):
            await c.client.aclose()
        await database.client.drop_database(database.raw_db.name)
    _run(teardown())


def _v(oc):
    return _run(oc.req("POST", "/api/vehicles", json={"vehicle_number": _uniq("KA-UAT")})).json()


def _d(oc):
    return _run(oc.req("POST", "/api/drivers", json={"name": _uniq("Driver")})).json()


# UAT-03 Vehicle onboarding & status
def test_uat03_vehicle_onboarding_and_status(env):
    admin = env["admin"]
    v = _v(admin)
    assert v["status"] == "active"
    upd = _run(admin.req("PUT", f"/api/vehicles/{v['id']}", json={"status": "maintenance"}))
    assert upd.status_code == 200 and upd.json()["status"] == "maintenance"


# UAT-04 Driver onboarding, assignment & exit
def test_uat04_driver_lifecycle(env):
    admin = env["admin"]
    d = _d(admin)
    assert d["status"] == "active"
    exit_ = _run(admin.req("PUT", f"/api/drivers/{d['id']}", json={"status": "resigned"}))
    assert exit_.status_code == 200 and exit_.json()["status"] == "resigned"


# UAT-05 Full trip lifecycle
def test_uat05_trip_full_lifecycle(env):
    admin = env["admin"]
    v, d = _v(admin), _d(admin)
    trip = _run(admin.req("POST", "/api/trips/plan", json={"date": "2026-07-01"})).json()
    assert trip["status"] == "planned"
    assert _run(admin.req("PATCH", f"/api/trips/{trip['id']}/assign",
                          json={"vehicle_id": v["id"], "driver_id": d["id"]})).json()["status"] == "assigned"
    assert _run(admin.req("PATCH", f"/api/trips/{trip['id']}/dispatch",
                          json={"opening_km": 100})).json()["status"] == "ongoing"
    assert _run(admin.req("PATCH", f"/api/trips/{trip['id']}/close",
                          json={"closing_km": 260})).json()["status"] == "completed"
    settled = _run(admin.req("PATCH", f"/api/trips/{trip['id']}/settle", json={}))
    assert settled.status_code == 200 and settled.json()["status"] == "settlement_pending"
    assert _run(admin.req("PATCH", f"/api/trips/{trip['id']}/finalize", json={})).json()["status"] == "closed"


# UAT-06 Reassignment before dispatch
def test_uat06_reassignment(env):
    admin = env["admin"]
    v1, v2 = _v(admin), _v(admin)
    trip = _run(admin.req("POST", "/api/trips/plan", json={"date": "2026-07-02"})).json()
    _run(admin.req("PATCH", f"/api/trips/{trip['id']}/assign", json={"vehicle_id": v1["id"]}))
    r = _run(admin.req("PATCH", f"/api/trips/{trip['id']}/reassign", json={"vehicle_id": v2["id"]}))
    assert r.status_code == 200 and r.json()["vehicle_id"] == v2["id"]


# UAT-07 Trip cancellation releases resources
def test_uat07_trip_cancellation(env):
    admin = env["admin"]
    v, d = _v(admin), _d(admin)
    trip = _run(admin.req("POST", "/api/trips/plan", json={"date": "2026-07-03"})).json()
    _run(admin.req("PATCH", f"/api/trips/{trip['id']}/assign", json={"vehicle_id": v["id"], "driver_id": d["id"]}))
    _run(admin.req("PATCH", f"/api/trips/{trip['id']}/dispatch", json={"opening_km": 1}))
    assert _run(admin.req("PATCH", f"/api/trips/{trip['id']}/cancel", json={"reason": "x"})).json()["status"] == "cancelled"
    trip2 = _run(admin.req("POST", "/api/trips/plan", json={"date": "2026-07-03"})).json()
    assert _run(admin.req("PATCH", f"/api/trips/{trip2['id']}/assign",
                          json={"vehicle_id": v["id"], "driver_id": d["id"]})).status_code == 200


# UAT-08/10 Expense submit→approve→pay→reverse
def test_uat08_expense_approve_pay_reverse(env):
    admin, owner = env["admin"], _run_owner(env)
    v = _v(admin)
    e = _run(admin.req("POST", "/api/expenses", json={
        "vehicle_id": v["id"], "category": "Miscellaneous", "date": "2026-07-01", "amount": 1000})).json()
    assert e["approval_status"] == "submitted"
    assert _run(owner.req("PATCH", f"/api/expenses/{e['id']}/approve", json={"approved_amount": 1000})).json()["approval_status"] == "approved"
    pay = _run(owner.req("POST", f"/api/expenses/{e['id']}/payments", json={"amount": 1000}))
    assert pay.status_code == 200 and pay.json()["paid_amount"] == 1000
    pid = pay.json()["payment"]["id"]
    rev = _run(owner.req("POST", f"/api/expenses/{e['id']}/payments/{pid}/reverse", json={}))
    assert rev.status_code == 200 and rev.json()["paid_amount"] == 0


# UAT-09 Advance + settlement
def test_uat09_advance_and_settlement(env):
    admin, owner = env["admin"], _run_owner(env)
    v, d = _v(admin), _d(admin)
    trip = _run(admin.req("POST", "/api/trips", json={
        "date": "2026-07-01", "vehicle_id": v["id"], "driver_id": d["id"],
        "opening_km": 0, "closing_km": 100, "toll_expense": 100})).json()
    adv = _run(admin.req("POST", "/api/advances", json={
        "driver_id": d["id"], "trip_id": trip["id"], "date": "2026-07-01", "amount": 500})).json()
    assert adv["status"] == "outstanding"
    view = _run(owner.req("GET", f"/api/trips/{trip['id']}/settlement")).json()
    assert view["advances"] == 500 and view["trip_direct_expenses"] == 100


# UAT-11 Repair ticket lifecycle
def test_uat11_repair_lifecycle(env):
    admin = env["admin"]
    v = _v(admin)
    rid = _run(admin.req("POST", "/api/repairs", json={
        "vehicle_id": v["id"], "repair_type": "major", "issue": "Engine",
        "date": "2026-07-01", "cost": 5000})).json()["id"]
    for s in ["under_review", "approved", "sent_for_repair", "in_repair", "repaired", "closed"]:
        assert _run(admin.req("PATCH", f"/api/repairs/{rid}/status", json={"status": s})).status_code == 200


# UAT-12 Downtime and return to service
def test_uat12_downtime_return(env):
    admin = env["admin"]
    v = _v(admin)
    dt = _run(admin.req("POST", "/api/downtime", json={
        "vehicle_id": v["id"], "reason": "service", "start_date": "2026-07-01"})).json()
    r = _run(admin.req("PATCH", f"/api/downtime/{dt['id']}/close", json={"reason": "done"}))
    assert r.status_code == 200 and r.json()["status"] == "closed"


# UAT-13 Tyre fitment, transfer, scrap
def test_uat13_tyre_lifecycle(env):
    admin = env["admin"]
    v1, v2 = _v(admin), _v(admin)
    tyre = _run(admin.req("POST", "/api/tyres", json={"vehicle_id": v1["id"], "tyre_number": _uniq("T")})).json()
    assert _run(admin.req("PATCH", f"/api/tyres/{tyre['id']}/transfer",
                          json={"to_vehicle_id": v2["id"]})).json()["vehicle_id"] == v2["id"]
    assert _run(admin.req("PATCH", f"/api/tyres/{tyre['id']}/scrap", json={"reason": "worn"})).json()["status"] == "scrapped"


# UAT-14 Fuel & odometer
def test_uat14_fuel_entry(env):
    admin = env["admin"]
    v = _v(admin)
    f = _run(admin.req("POST", "/api/fuel", json={
        "vehicle_id": v["id"], "date": "2026-07-01", "odometer": 5000, "quantity": 40, "amount": 3800}))
    assert f.status_code == 200
    veh = _run(admin.req("GET", "/api/vehicles", params={"all": "true"})).json()
    assert next(x for x in veh if x["id"] == v["id"])["current_odometer"] == 5000


# UAT-16 Document upload, replacement & expiry
def test_uat16_document_supersede(env):
    admin = env["admin"]
    v = _v(admin)
    d1 = _run(admin.req("POST", "/api/documents", json={
        "vehicle_id": v["id"], "doc_type": "Insurance",
        "issue_date": "2025-01-01", "expiry_date": "2026-01-01"})).json()
    d2 = _run(admin.req("POST", "/api/documents", json={
        "vehicle_id": v["id"], "doc_type": "Insurance",
        "issue_date": "2026-01-01", "expiry_date": "2027-01-01"})).json()
    docs = _run(admin.req("GET", "/api/documents", params={"vehicle_id": v["id"], "all": "true"})).json()
    items = docs if isinstance(docs, list) else docs.get("items", [])
    assert next(x for x in items if x["id"] == d1["id"])["is_current"] is False
    assert next(x for x in items if x["id"] == d2["id"])["is_current"] is True


# UAT-17 Accident & claim lifecycle
def test_uat17_accident_claim(env):
    admin, owner = env["admin"], _run_owner(env)
    v = _v(admin)
    a = _run(admin.req("POST", "/api/accidents", json={
        "vehicle_id": v["id"], "date": "2026-06-01", "claim_amount": 10000})).json()
    for s in ["evidence_collected", "claim_submitted", "under_survey"]:
        assert _run(admin.req("PATCH", f"/api/accidents/{a['id']}/claim", json={"status": s})).status_code == 200
    assert _run(owner.req("PATCH", f"/api/accidents/{a['id']}/claim",
                          json={"status": "approved", "approved_amount": 8000})).status_code == 200
    assert _run(owner.req("PATCH", f"/api/accidents/{a['id']}/claim",
                          json={"status": "settled", "settlement_amount": 8000})).status_code == 200


# UAT-18 Operational exceptions
def test_uat18_exceptions_feed(env):
    admin = env["admin"]
    v = _v(admin)
    _run(admin.req("POST", "/api/downtime", json={
        "vehicle_id": v["id"], "reason": "service", "start_date": "2026-07-01"}))
    feed = _run(admin.req("GET", "/api/exceptions")).json()
    assert feed["total"] >= 1 and "open_downtime" in feed["by_category"]


# UAT-19 Reports / reconciliation
def test_uat19_reconciliation_available(env):
    admin = env["admin"]
    r = _run(admin.req("GET", "/api/expenses/ledger"))
    assert r.status_code == 200 and "total" in r.json()


# UAT-20 Cross-tenant isolation
def test_uat20_cross_tenant_isolation(env):
    admin, beta = env["admin"], env["beta"]
    bv = _v(beta)
    # Demo admin cannot act on beta's vehicle.
    r = _run(admin.req("PUT", f"/api/vehicles/{bv['id']}", json={"notes": "x"}))
    assert r.status_code == 404


# UAT-02 Role enforcement (viewer read-only)
def test_uat02_role_enforcement(env):
    viewer = env["viewer"]
    r = _run(viewer.req("POST", "/api/vehicles", json={"vehicle_number": "X"}))
    assert r.status_code == 403


# UAT-21 Session logout
def test_uat21_session_logout(env):
    oc = _run(_enter_demo("operations"))
    assert _run(oc.req("GET", "/api/vehicles")).status_code == 200
    assert _run(oc.req("POST", "/api/auth/logout", json={})).status_code in (200, 204)
    after = _run(oc.req("GET", "/api/vehicles"))
    assert after.status_code == 401


_OWNER = {}


def _run_owner(env):
    if "c" not in _OWNER:
        _OWNER["c"] = _run(_enter_demo("owner"))
    return _OWNER["c"]
