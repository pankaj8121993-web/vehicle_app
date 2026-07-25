"""
OPS-01 — Trip, dispatch and allocation lifecycle (real HTTP).

Drives the running app over ASGI to prove the dedicated trip lifecycle actions
(plan → assign → dispatch → complete → finalize, plus reassign and cancel)
enforce the OPS-01 controls: same-org and in-service allocation, allocation
conflict prevention, downtime-blocked dispatch, reassignment authority,
idempotent transitions, compare-and-swap concurrency, generic-bypass rejection
and audit coverage.

Conventions mirror the AUTHZ/DI real-HTTP suites: one shared event loop
(conftest), demo-org role sessions via /demo/enter for permission coverage, and
a second onboarded organisation for cross-tenant rejection.
"""
import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import server  # noqa: E402
import database  # noqa: E402
import session_security as ss  # noqa: E402

from conftest import realhttp_run as _run


class Client:
    def __init__(self, client, role, org_id):
        self.client = client
        self.role = role
        self.org_id = org_id

    def _h(self, method):
        if method in ss.SAFE_METHODS:
            return {}
        csrf = self.client.cookies.get(ss.CSRF_COOKIE)
        return {ss.CSRF_HEADER: csrf} if csrf else {}

    async def req(self, method, url, **kw):
        kw.setdefault("headers", {}).update(self._h(method))
        return await self.client.request(method, url, **kw)


DEMO_ROLES = {
    "org_admin": "admin",
    "operations": "data_entry",
    "viewer": "viewer",
}

_PW = "ops01-" + "throwaway-passphrase"


async def _enter_demo(role):
    transport = ASGITransport(app=server.app)
    client = AsyncClient(transport=transport, base_url="http://ops01")
    r = await client.post("/api/demo/enter", json={"role": role})
    assert r.status_code == 200, f"demo/enter {role}: {r.status_code} {r.text[:200]}"
    return Client(client, role, r.json()["user"]["org_id"])


async def _register_org(slug):
    transport = ASGITransport(app=server.app)
    client = AsyncClient(transport=transport, base_url="http://ops01b")
    r = await client.post("/api/onboarding/register", json={
        "org": {"legal_name": f"OPS01 {slug} Ltd", "org_type": "Company"},
        "admin": {"username": f"ops01_{slug}", "email": f"{slug}@ops01.invalid",
                  "password": _PW, "full_name": f"OPS01 {slug}"},
    })
    assert r.status_code == 200, f"onboarding failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    return Client(client, "admin", body["user"]["org_id"])


def _uniq(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def env():
    async def build():
        await database.client.drop_database(database.raw_db.name)
        await database.raw_db.idempotency_keys.create_index(
            [("org_id", 1), ("scope", 1), ("key", 1)],
            name="uniq_org_scope_key", unique=True,
        )
        clients = {role: await _enter_demo(role) for role in DEMO_ROLES}
        beta = await _register_org("beta")
        return clients, beta

    clients, beta = _run(build())
    yield {"clients": clients, "beta": beta}

    async def teardown():
        for c in clients.values():
            await c.client.aclose()
        await beta.client.aclose()
        await database.client.drop_database(database.raw_db.name)

    _run(teardown())


# --- helpers ------------------------------------------------------------------

def _admin(env):
    return env["clients"]["org_admin"]


def _vehicle(oc, **extra):
    body = {"vehicle_number": _uniq("KA-OPS")}
    body.update(extra)
    r = _run(oc.req("POST", "/api/vehicles", json=body))
    assert r.status_code == 200, r.text[:200]
    return r.json()


def _driver(oc, **extra):
    body = {"name": _uniq("Driver")}
    body.update(extra)
    r = _run(oc.req("POST", "/api/drivers", json=body))
    assert r.status_code == 200, r.text[:200]
    return r.json()


def _plan(oc, **extra):
    body = {"date": "2026-06-01"}
    body.update(extra)
    r = _run(oc.req("POST", "/api/trips/plan", json=body))
    return r


def _planned_trip(oc, **extra):
    r = _plan(oc, **extra)
    assert r.status_code == 200, r.text[:200]
    return r.json()


def _assign(oc, trip_id, **body):
    return _run(oc.req("PATCH", f"/api/trips/{trip_id}/assign", json=body))


def _dispatch(oc, trip_id, **body):
    return _run(oc.req("PATCH", f"/api/trips/{trip_id}/dispatch", json=body))


def _audits(action, target_id, **detail):
    q = {"action": action, "target_id": target_id}
    for k, v in detail.items():
        q[f"detail.{k}"] = v
    return _run(database.raw_db.security_audit.count_documents(q))


# --- Plan ---------------------------------------------------------------------

def test_plan_creates_a_planned_trip(env):
    trip = _planned_trip(_admin(env), origin="A", destination="B")
    assert trip["status"] == "planned"
    assert trip["distance"] is None
    assert _audits("trip.plan", trip["id"]) == 1


def test_plan_idempotent_with_key(env):
    key = "idem-" + uuid.uuid4().hex
    body = {"date": "2026-06-02", "origin": "X"}
    r1 = _run(_admin(env).req("POST", "/api/trips/plan", json=body,
                              headers={"Idempotency-Key": key}))
    r2 = _run(_admin(env).req("POST", "/api/trips/plan", json=body,
                              headers={"Idempotency-Key": key}))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]


# --- Allocation ---------------------------------------------------------------

def test_same_tenant_valid_allocation(env):
    admin = _admin(env)
    v, d = _vehicle(admin), _driver(admin)
    trip = _planned_trip(admin)
    r = _assign(admin, trip["id"], vehicle_id=v["id"], driver_id=d["id"])
    assert r.status_code == 200, r.text[:200]
    assert r.json()["status"] == "assigned"
    assert r.json()["vehicle_id"] == v["id"] and r.json()["driver_id"] == d["id"]
    assert _audits("trip.assign", trip["id"]) == 1


def test_cross_tenant_vehicle_rejected(env):
    admin = _admin(env)
    beta_vehicle = _vehicle(env["beta"])
    trip = _planned_trip(admin)
    r = _assign(admin, trip["id"], vehicle_id=beta_vehicle["id"])
    assert r.status_code == 400, r.text[:200]


def test_cross_tenant_driver_rejected(env):
    admin = _admin(env)
    beta_driver = _driver(env["beta"])
    v = _vehicle(admin)
    trip = _planned_trip(admin)
    r = _assign(admin, trip["id"], vehicle_id=v["id"], driver_id=beta_driver["id"])
    assert r.status_code == 400, r.text[:200]


def test_disposed_vehicle_rejected(env):
    admin = _admin(env)
    v = _vehicle(admin)
    _run(admin.req("PUT", f"/api/vehicles/{v['id']}", json={"status": "sold"}))
    trip = _planned_trip(admin)
    r = _assign(admin, trip["id"], vehicle_id=v["id"])
    assert r.status_code == 400, r.text[:200]


def test_exited_driver_rejected(env):
    admin = _admin(env)
    v, d = _vehicle(admin), _driver(admin)
    _run(admin.req("PUT", f"/api/drivers/{d['id']}", json={"status": "resigned"}))
    trip = _planned_trip(admin)
    r = _assign(admin, trip["id"], vehicle_id=v["id"], driver_id=d["id"])
    assert r.status_code == 400, r.text[:200]


def test_double_allocation_prevented(env):
    """A vehicle already on an active (dispatched) trip cannot be allocated to another."""
    admin = _admin(env)
    v, d = _vehicle(admin), _driver(admin)
    t1 = _planned_trip(admin)
    assert _assign(admin, t1["id"], vehicle_id=v["id"], driver_id=d["id"]).status_code == 200
    assert _dispatch(admin, t1["id"], opening_km=10).status_code == 200
    # v and d are now actively allocated to t1.
    t2 = _planned_trip(admin)
    r_v = _assign(admin, t2["id"], vehicle_id=v["id"])
    assert r_v.status_code == 409, r_v.text[:200]
    r_d = _assign(admin, t2["id"], driver_id=d["id"])
    assert r_d.status_code == 409, r_d.text[:200]


def test_concurrent_assign_same_trip_one_wins(env):
    admin = _admin(env)
    v1, v2 = _vehicle(admin), _vehicle(admin)
    trip = _planned_trip(admin)

    async def race():
        return await asyncio.gather(
            admin.req("PATCH", f"/api/trips/{trip['id']}/assign",
                      json={"vehicle_id": v1["id"]}, headers=admin._h("PATCH")),
            admin.req("PATCH", f"/api/trips/{trip['id']}/assign",
                      json={"vehicle_id": v2["id"]}, headers=admin._h("PATCH")),
        )

    r1, r2 = _run(race())
    codes = sorted([r1.status_code, r2.status_code])
    assert codes == [200, 409], codes
    # Exactly one assign audit for this trip.
    assert _audits("trip.assign", trip["id"]) == 1


# --- Reassignment -------------------------------------------------------------

def test_reassign_before_dispatch_allowed(env):
    admin = _admin(env)
    v1, v2 = _vehicle(admin), _vehicle(admin)
    trip = _planned_trip(admin)
    assert _assign(admin, trip["id"], vehicle_id=v1["id"]).status_code == 200
    r = _run(admin.req("PATCH", f"/api/trips/{trip['id']}/reassign",
                       json={"vehicle_id": v2["id"]}))
    assert r.status_code == 200, r.text[:200]
    assert r.json()["vehicle_id"] == v2["id"]


def test_reassign_after_dispatch_requires_authority(env):
    admin = _admin(env)
    ops = env["clients"]["operations"]  # data_entry: may drive trips, not reassign post-dispatch
    v1, v2, d = _vehicle(admin), _vehicle(admin), _driver(admin)
    trip = _planned_trip(admin)
    _assign(admin, trip["id"], vehicle_id=v1["id"], driver_id=d["id"])
    _dispatch(admin, trip["id"], opening_km=5)
    # data_entry cannot reassign a dispatched trip
    denied = _run(ops.req("PATCH", f"/api/trips/{trip['id']}/reassign",
                          json={"vehicle_id": v2["id"], "reason": "breakdown"}))
    assert denied.status_code == 403, denied.text[:200]
    # admin without a reason is refused
    no_reason = _run(admin.req("PATCH", f"/api/trips/{trip['id']}/reassign",
                               json={"vehicle_id": v2["id"]}))
    assert no_reason.status_code == 400, no_reason.text[:200]
    # admin with a reason succeeds and is audited as post-dispatch
    ok = _run(admin.req("PATCH", f"/api/trips/{trip['id']}/reassign",
                        json={"vehicle_id": v2["id"], "reason": "breakdown"}))
    assert ok.status_code == 200, ok.text[:200]
    assert _audits("trip.reassign", trip["id"], post_dispatch=True) == 1


# --- Dispatch -----------------------------------------------------------------

def test_dispatch_requires_assignment_first(env):
    admin = _admin(env)
    trip = _planned_trip(admin)
    # A planned trip cannot jump straight to ongoing.
    r = _dispatch(admin, trip["id"], opening_km=1)
    assert r.status_code == 409, r.text[:200]


def test_dispatch_blocked_by_open_downtime(env):
    admin = _admin(env)
    v, d = _vehicle(admin), _driver(admin)
    dt = _run(admin.req("POST", "/api/downtime", json={
        "vehicle_id": v["id"], "reason": "breakdown", "start_date": "2026-06-01"}))
    assert dt.status_code == 200, dt.text[:200]
    trip = _planned_trip(admin)
    _assign(admin, trip["id"], vehicle_id=v["id"], driver_id=d["id"])
    r = _dispatch(admin, trip["id"], opening_km=1)
    assert r.status_code == 409, r.text[:200]


def test_double_dispatch_idempotent(env):
    admin = _admin(env)
    v, d = _vehicle(admin), _driver(admin)
    trip = _planned_trip(admin)
    _assign(admin, trip["id"], vehicle_id=v["id"], driver_id=d["id"])
    r1 = _dispatch(admin, trip["id"], opening_km=100)
    r2 = _dispatch(admin, trip["id"], opening_km=999)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["status"] == "ongoing" and r2.json()["status"] == "ongoing"
    # Second dispatch is a no-op — one dispatch audit only.
    assert _audits("trip.dispatch", trip["id"]) == 1


# --- Completion / closure -----------------------------------------------------

def test_double_completion_idempotent(env):
    admin = _admin(env)
    v, d = _vehicle(admin), _driver(admin)
    trip = _planned_trip(admin)
    _assign(admin, trip["id"], vehicle_id=v["id"], driver_id=d["id"])
    _dispatch(admin, trip["id"], opening_km=200)
    r1 = _run(admin.req("PATCH", f"/api/trips/{trip['id']}/close", json={"closing_km": 350}))
    r2 = _run(admin.req("PATCH", f"/api/trips/{trip['id']}/close", json={"closing_km": 9999}))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["distance"] == 150 and r2.json()["distance"] == 150


def test_finalize_and_double_finalize_idempotent(env):
    admin = _admin(env)
    v, d = _vehicle(admin), _driver(admin)
    trip = _planned_trip(admin)
    _assign(admin, trip["id"], vehicle_id=v["id"], driver_id=d["id"])
    _dispatch(admin, trip["id"], opening_km=300)
    _run(admin.req("PATCH", f"/api/trips/{trip['id']}/close", json={"closing_km": 400}))
    r1 = _run(admin.req("PATCH", f"/api/trips/{trip['id']}/finalize", json={}))
    r2 = _run(admin.req("PATCH", f"/api/trips/{trip['id']}/finalize", json={}))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["status"] == "closed" and r2.json()["status"] == "closed"
    assert _audits("trip.finalize", trip["id"]) == 1


def test_cannot_finalize_before_completion(env):
    admin = _admin(env)
    v, d = _vehicle(admin), _driver(admin)
    trip = _planned_trip(admin)
    _assign(admin, trip["id"], vehicle_id=v["id"], driver_id=d["id"])
    _dispatch(admin, trip["id"], opening_km=1)
    # ongoing → closed is not a valid edge.
    r = _run(admin.req("PATCH", f"/api/trips/{trip['id']}/finalize", json={}))
    assert r.status_code == 409, r.text[:200]


# --- Cancellation -------------------------------------------------------------

def test_cancellation_releases_vehicle_and_driver(env):
    admin = _admin(env)
    v, d = _vehicle(admin), _driver(admin)
    t1 = _planned_trip(admin)
    _assign(admin, t1["id"], vehicle_id=v["id"], driver_id=d["id"])
    _dispatch(admin, t1["id"], opening_km=1)
    # Cancel releases the allocation.
    c = _run(admin.req("PATCH", f"/api/trips/{t1['id']}/cancel", json={"reason": "customer cancelled"}))
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    assert _audits("trip.cancel", t1["id"]) == 1
    # The same vehicle/driver may now be allocated to a fresh trip.
    t2 = _planned_trip(admin)
    r = _assign(admin, t2["id"], vehicle_id=v["id"], driver_id=d["id"])
    assert r.status_code == 200, r.text[:200]


def test_cancel_after_completion_refused(env):
    admin = _admin(env)
    v, d = _vehicle(admin), _driver(admin)
    trip = _planned_trip(admin)
    _assign(admin, trip["id"], vehicle_id=v["id"], driver_id=d["id"])
    _dispatch(admin, trip["id"], opening_km=1)
    _run(admin.req("PATCH", f"/api/trips/{trip['id']}/close", json={"closing_km": 50}))
    r = _run(admin.req("PATCH", f"/api/trips/{trip['id']}/cancel", json={}))
    assert r.status_code == 409, r.text[:200]


# --- Generic bypass & permissions ---------------------------------------------

def test_generic_status_write_rejected(env):
    admin = _admin(env)
    v, d = _vehicle(admin), _driver(admin)
    trip = _planned_trip(admin)
    _assign(admin, trip["id"], vehicle_id=v["id"], driver_id=d["id"])
    _dispatch(admin, trip["id"], opening_km=1)
    # A generic PUT must not drive trip status — no distance/odometer/audit path.
    r = _run(admin.req("PUT", f"/api/trips/{trip['id']}", json={"status": "completed"}))
    assert r.status_code == 409, r.text[:200]
    # And it must not reopen a terminal trip either.
    r2 = _run(admin.req("PUT", f"/api/trips/{trip['id']}", json={"status": "planned"}))
    assert r2.status_code == 409, r2.text[:200]


def test_viewer_cannot_drive_lifecycle(env):
    admin = _admin(env)
    viewer = env["clients"]["viewer"]
    v = _vehicle(admin)
    trip = _planned_trip(admin)
    assert _assign(viewer, trip["id"], vehicle_id=v["id"]).status_code == 403
    assert _run(viewer.req("PATCH", f"/api/trips/{trip['id']}/cancel", json={})).status_code == 403
    # viewer cannot even plan (no trips:create)
    assert _plan(viewer).status_code == 403


def test_quick_create_path_unchanged(env):
    """The legacy full-entry POST /trips still lands ongoing/completed directly,
    so pre-OPS-01 clients and reconciliation are unaffected."""
    admin = _admin(env)
    v = _vehicle(admin)
    ongoing = _run(admin.req("POST", "/api/trips", json={
        "date": "2026-07-01", "vehicle_id": v["id"], "opening_km": 10})).json()
    assert ongoing["status"] == "ongoing"
    completed = _run(admin.req("POST", "/api/trips", json={
        "date": "2026-07-02", "vehicle_id": v["id"], "opening_km": 10,
        "closing_km": 60, "toll_expense": 100})).json()
    assert completed["status"] == "completed" and completed["distance"] == 50
