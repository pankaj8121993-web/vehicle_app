"""
OPS-05 — Operational exceptions, alerts and closure (real HTTP).

Proves exceptions are org-scoped, derived live from canonical data (a resolved
source leaves the list), acknowledgement flags without hiding, no duplicate
alerts, threshold boundaries, category totals match the underlying items, and
permission/tenant isolation hold.
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


DEMO_ROLES = {"org_admin": "admin", "viewer": "viewer"}
_PW = "ops05-" + "throwaway-passphrase"


async def _enter_demo(role):
    transport = ASGITransport(app=server.app)
    client = AsyncClient(transport=transport, base_url="http://ops05")
    r = await client.post("/api/demo/enter", json={"role": role})
    assert r.status_code == 200, f"demo/enter {role}: {r.status_code} {r.text[:200]}"
    return Client(client, role, r.json()["user"]["org_id"])


async def _register_org(slug):
    transport = ASGITransport(app=server.app)
    client = AsyncClient(transport=transport, base_url="http://ops05b")
    r = await client.post("/api/onboarding/register", json={
        "org": {"legal_name": f"OPS05 {slug} Ltd", "org_type": "Company"},
        "admin": {"username": f"ops05_{slug}", "email": f"{slug}@ops05.invalid",
                  "password": _PW, "full_name": f"OPS05 {slug}"},
    })
    assert r.status_code == 200, r.text[:200]
    return Client(client, "admin", r.json()["user"]["org_id"])


def _uniq(p):
    return f"{p}-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def env():
    async def build():
        await database.client.drop_database(database.raw_db.name)
        await database.raw_db.idempotency_keys.create_index(
            [("org_id", 1), ("scope", 1), ("key", 1)],
            name="uniq_org_scope_key", unique=True,
        )
        clients = {r: await _enter_demo(r) for r in DEMO_ROLES}
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


def _admin(env):
    return env["clients"]["org_admin"]


def _vehicle(oc):
    return _run(oc.req("POST", "/api/vehicles", json={"vehicle_number": _uniq("KA-EXC")})).json()


def _exceptions(oc, **params):
    r = _run(oc.req("GET", "/api/exceptions", params=params))
    assert r.status_code == 200, r.text[:200]
    return r.json()


def _ids(feed, category):
    return {i["id"] for i in feed["items"] if i["category"] == category}


# --- Visibility & derivation --------------------------------------------------

def test_open_downtime_appears_and_resolves(env):
    admin = _admin(env)
    v = _vehicle(admin)
    dt = _run(admin.req("POST", "/api/downtime", json={
        "vehicle_id": v["id"], "reason": "service", "start_date": "2026-06-01"})).json()
    exc_id = f"open_downtime:{dt['id']}"
    feed = _exceptions(admin)
    assert exc_id in _ids(feed, "open_downtime")
    # Closing the downtime (resolving the source) drops it from the live feed.
    _run(admin.req("PATCH", f"/api/downtime/{dt['id']}/close", json={"reason": "done"}))
    feed2 = _exceptions(admin)
    assert exc_id not in _ids(feed2, "open_downtime")


def test_unapproved_expense_appears(env):
    admin = _admin(env)
    v = _vehicle(admin)
    e = _run(admin.req("POST", "/api/expenses", json={
        "vehicle_id": v["id"], "category": "Miscellaneous", "date": "2026-06-01", "amount": 500})).json()
    feed = _exceptions(admin)
    assert f"unapproved_expenses:{e['id']}" in _ids(feed, "unapproved_expenses")


def test_trip_awaiting_dispatch_appears(env):
    admin = _admin(env)
    trip = _run(admin.req("POST", "/api/trips/plan", json={"date": "2026-06-01"})).json()
    feed = _exceptions(admin)
    assert f"trips_awaiting_dispatch:{trip['id']}" in _ids(feed, "trips_awaiting_dispatch")


def test_no_duplicate_alerts(env):
    admin = _admin(env)
    v = _vehicle(admin)
    _run(admin.req("POST", "/api/downtime", json={
        "vehicle_id": v["id"], "reason": "service", "start_date": "2026-06-01"}))
    feed = _exceptions(admin)
    ids = [i["id"] for i in feed["items"]]
    assert len(ids) == len(set(ids)), "duplicate exception ids in the feed"


def test_category_totals_match_items(env):
    feed = _exceptions(_admin(env))
    recomputed = {}
    for i in feed["items"]:
        recomputed[i["category"]] = recomputed.get(i["category"], 0) + 1
    assert feed["by_category"] == recomputed
    assert feed["total"] == len(feed["items"])


# --- Thresholds ---------------------------------------------------------------

def test_trip_overdue_threshold_boundary(env):
    admin = _admin(env)
    v = _vehicle(admin)
    # An ongoing trip dated well in the past.
    trip = _run(admin.req("POST", "/api/trips", json={
        "date": "2020-01-01", "vehicle_id": v["id"], "opening_km": 0})).json()
    tid = f"trips_overdue_completion:{trip['id']}"
    # A huge threshold suppresses it; a small one surfaces it.
    assert tid not in _ids(_exceptions(admin, trip_overdue_days=100000), "trips_overdue_completion")
    assert tid in _ids(_exceptions(admin, trip_overdue_days=1), "trips_overdue_completion")


# --- Acknowledgement ----------------------------------------------------------

def test_acknowledge_flags_without_hiding(env):
    admin = _admin(env)
    v = _vehicle(admin)
    dt = _run(admin.req("POST", "/api/downtime", json={
        "vehicle_id": v["id"], "reason": "service", "start_date": "2026-06-01"})).json()
    exc_id = f"open_downtime:{dt['id']}"
    ack = _run(admin.req("POST", f"/api/exceptions/{exc_id}/acknowledge", json={"note": "aware"}))
    assert ack.status_code == 200
    feed = _exceptions(admin)
    item = next(i for i in feed["items"] if i["id"] == exc_id)
    # Still present (source unresolved) but flagged acknowledged.
    assert item["acknowledged"] is True
    # Idempotent acknowledge — no duplicate ack rows.
    _run(admin.req("POST", f"/api/exceptions/{exc_id}/acknowledge", json={}))
    assert _run(database.raw_db.exception_acks.count_documents({"exception_id": exc_id})) == 1


# --- Isolation & permission ---------------------------------------------------

def test_cross_tenant_exception_isolation(env):
    admin, beta = _admin(env), env["beta"]
    bv = _vehicle(beta)
    bdt = _run(beta.req("POST", "/api/downtime", json={
        "vehicle_id": bv["id"], "reason": "service", "start_date": "2026-06-01"})).json()
    # Beta's downtime must not surface in the demo org's feed.
    feed = _exceptions(admin)
    assert f"open_downtime:{bdt['id']}" not in _ids(feed, "open_downtime")


def test_viewer_cannot_acknowledge(env):
    viewer = env["clients"]["viewer"]
    r = _run(viewer.req("POST", "/api/exceptions/open_downtime:x/acknowledge", json={}))
    assert r.status_code == 403, r.text[:200]
