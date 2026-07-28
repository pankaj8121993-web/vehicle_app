"""
OPS-03 — Repairs, maintenance, tyres and downtime (real HTTP).

Proves the maintenance flow ties together: a repair entering the workshop takes
the vehicle off the road (opens downtime + maintenance status) and closing it
does not silently clear the downtime; completion odometer forwards the master;
tyre fitment/transfer/scrap integrity holds (no double-fit, no fitting a
removed/scrapped tyre, transfer preserves history); the dedicated downtime close
records reason/days and cannot be reopened generically; and approved repair cost
still feeds reconciliation.
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


_PW = "ops03-" + "throwaway-passphrase"


async def _enter_demo(role):
    transport = ASGITransport(app=server.app)
    client = AsyncClient(transport=transport, base_url="http://ops03")
    r = await client.post("/api/demo/enter", json={"role": role})
    assert r.status_code == 200, f"demo/enter {role}: {r.status_code} {r.text[:200]}"
    return Client(client, role, r.json()["user"]["org_id"])


async def _register_org(slug):
    transport = ASGITransport(app=server.app)
    client = AsyncClient(transport=transport, base_url="http://ops03b")
    r = await client.post("/api/onboarding/register", json={
        "org": {"legal_name": f"OPS03 {slug} Ltd", "org_type": "Company"},
        "admin": {"username": f"ops03_{slug}", "email": f"{slug}@ops03.invalid",
                  "password": _PW, "full_name": f"OPS03 {slug}"},
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
        admin = await _enter_demo("org_admin")
        beta = await _register_org("beta")
        return admin, beta

    admin, beta = _run(build())
    yield {"admin": admin, "beta": beta}

    async def teardown():
        await admin.client.aclose()
        await beta.client.aclose()
        await database.client.drop_database(database.raw_db.name)

    _run(teardown())


def _vehicle(oc):
    return _run(oc.req("POST", "/api/vehicles", json={"vehicle_number": _uniq("KA-MNT")})).json()


def _tyre(oc, vid, number=None):
    return _run(oc.req("POST", "/api/tyres", json={
        "vehicle_id": vid, "tyre_number": number or _uniq("T")}))


def _repair(oc, vid, **extra):
    body = {"vehicle_id": vid, "repair_type": "major", "issue": "Engine", "date": "2026-06-01", "cost": 5000}
    body.update(extra)
    return _run(oc.req("POST", "/api/repairs", json=body)).json()


def _advance(oc, rid, status, **extra):
    body = {"status": status}
    body.update(extra)
    return _run(oc.req("PATCH", f"/api/repairs/{rid}/status", json=body))


def _open_downtimes(oc, vid):
    r = _run(oc.req("GET", "/api/downtime", params={"vehicle_id": vid, "status": "open", "all": "true"}))
    body = r.json()
    items = body if isinstance(body, list) else body.get("items", [])
    return [d for d in items if d["vehicle_id"] == vid]


def _drive_to(oc, rid, target):
    """Walk a repair ticket forward through the state graph to `target`."""
    order = ["under_review", "approved", "sent_for_repair", "in_repair", "repaired", "closed"]
    for s in order:
        r = _advance(oc, rid, s)
        assert r.status_code == 200, f"{s}: {r.status_code} {r.text[:200]}"
        if s == target:
            return r
    return None


# --- Repair → downtime linkage ------------------------------------------------

def test_in_repair_opens_downtime_and_maintenance(env):
    admin = env["admin"]
    v = _vehicle(admin)
    rid = _repair(admin, v["id"])["id"]
    assert _open_downtimes(admin, v["id"]) == []
    _drive_to(admin, rid, "in_repair")
    dts = _open_downtimes(admin, v["id"])
    assert len(dts) == 1 and dts[0].get("repair_id") == rid
    veh = _run(admin.req("GET", "/api/vehicles", params={"all": "true"})).json()
    rec = next(x for x in veh if x["id"] == v["id"])
    assert rec["status"] == "maintenance"


def test_closing_repair_does_not_close_downtime(env):
    admin = env["admin"]
    v = _vehicle(admin)
    rid = _repair(admin, v["id"])["id"]
    _drive_to(admin, rid, "closed")   # includes odometer? no
    # Downtime opened at in_repair must still be open after the repair closes.
    assert len(_open_downtimes(admin, v["id"])) == 1


def test_completion_odometer_forwards_master(env):
    admin = env["admin"]
    v = _vehicle(admin)  # odometer 0
    rid = _repair(admin, v["id"])["id"]
    _drive_to(admin, rid, "repaired")
    r = _advance(admin, rid, "closed", odometer=44000)
    assert r.status_code == 200 and r.json().get("completion_odometer") == 44000
    veh = _run(admin.req("GET", "/api/vehicles", params={"all": "true"})).json()
    rec = next(x for x in veh if x["id"] == v["id"])
    assert rec["current_odometer"] == 44000


def test_invalid_repair_jump_rejected(env):
    admin = env["admin"]
    v = _vehicle(admin)
    rid = _repair(admin, v["id"])["id"]
    r = _advance(admin, rid, "closed")   # open → closed skips the middle
    assert r.status_code == 409, r.text[:200]


def test_cross_tenant_vehicle_on_repair_rejected(env):
    admin, beta = env["admin"], env["beta"]
    beta_v = _vehicle(beta)
    r = _run(admin.req("POST", "/api/repairs", json={
        "vehicle_id": beta_v["id"], "repair_type": "major", "issue": "X", "date": "2026-06-01"}))
    assert r.status_code == 400, r.text[:200]


# --- Downtime -----------------------------------------------------------------

def test_dedicated_downtime_close_records_reason_and_days(env):
    admin = env["admin"]
    v = _vehicle(admin)
    dt = _run(admin.req("POST", "/api/downtime", json={
        "vehicle_id": v["id"], "reason": "service", "start_date": "2026-06-01"})).json()
    r = _run(admin.req("PATCH", f"/api/downtime/{dt['id']}/close",
                       json={"end_date": "2026-06-05", "reason": "parts fitted"}))
    assert r.status_code == 200, r.text[:200]
    assert r.json()["status"] == "closed" and r.json()["days"] == 5
    assert r.json()["closure_reason"] == "parts fitted"


def test_downtime_cannot_be_reopened_generically(env):
    admin = env["admin"]
    v = _vehicle(admin)
    dt = _run(admin.req("POST", "/api/downtime", json={
        "vehicle_id": v["id"], "reason": "service", "start_date": "2026-06-01",
        "end_date": "2026-06-02"})).json()   # created closed
    r = _run(admin.req("PUT", f"/api/downtime/{dt['id']}", json={"status": "open"}))
    assert r.status_code == 409, r.text[:200]


def test_downtime_close_brings_vehicle_back(env):
    admin = env["admin"]
    v = _vehicle(admin)
    rid = _repair(admin, v["id"])["id"]
    _drive_to(admin, rid, "in_repair")   # → maintenance + open downtime
    dt = _open_downtimes(admin, v["id"])[0]
    _run(admin.req("PATCH", f"/api/downtime/{dt['id']}/close", json={"reason": "done"}))
    veh = _run(admin.req("GET", "/api/vehicles", params={"all": "true"})).json()
    rec = next(x for x in veh if x["id"] == v["id"])
    assert rec["status"] == "active"


# --- Tyres --------------------------------------------------------------------

def test_tyre_double_fit_prevented(env):
    admin = env["admin"]
    v1, v2 = _vehicle(admin), _vehicle(admin)
    num = _uniq("T")
    assert _tyre(admin, v1["id"], num).status_code == 200
    # Same physical tyre number cannot be fitted to a second vehicle.
    r = _tyre(admin, v2["id"], num)
    assert r.status_code == 409, r.text[:200]


def test_tyre_transfer_preserves_history(env):
    admin = env["admin"]
    v1, v2 = _vehicle(admin), _vehicle(admin)
    tyre = _tyre(admin, v1["id"]).json()
    r = _run(admin.req("PATCH", f"/api/tyres/{tyre['id']}/transfer",
                       json={"to_vehicle_id": v2["id"], "odometer": 12000}))
    assert r.status_code == 200 and r.json()["vehicle_id"] == v2["id"]
    events = _run(admin.req("GET", "/api/tyre-events",
                            params={"tyre_id": tyre["id"], "all": "true"})).json()
    evs = events if isinstance(events, list) else events.get("items", [])
    assert any(e["event_type"] == "transfer" and e["vehicle_id"] == v2["id"] for e in evs)


def test_scrapped_tyre_cannot_be_transferred(env):
    admin = env["admin"]
    v1, v2 = _vehicle(admin), _vehicle(admin)
    tyre = _tyre(admin, v1["id"]).json()
    scrap = _run(admin.req("PATCH", f"/api/tyres/{tyre['id']}/scrap",
                           json={"odometer": 60000, "reason": "worn"}))
    assert scrap.status_code == 200 and scrap.json()["status"] == "scrapped"
    r = _run(admin.req("PATCH", f"/api/tyres/{tyre['id']}/transfer",
                       json={"to_vehicle_id": v2["id"]}))
    assert r.status_code == 409, r.text[:200]


def test_removed_tyre_cannot_be_transferred(env):
    admin = env["admin"]
    v1, v2 = _vehicle(admin), _vehicle(admin)
    tyre = _tyre(admin, v1["id"]).json()
    # A replacement event marks the tyre removed.
    _run(admin.req("POST", "/api/tyre-events", json={
        "tyre_id": tyre["id"], "event_type": "replacement", "date": "2026-06-01", "odometer": 50000}))
    r = _run(admin.req("PATCH", f"/api/tyres/{tyre['id']}/transfer",
                       json={"to_vehicle_id": v2["id"]}))
    assert r.status_code == 409, r.text[:200]


def test_tyre_event_odometer_validated(env):
    admin = env["admin"]
    v1, v2 = _vehicle(admin), _vehicle(admin)
    tyre = _tyre(admin, v1["id"]).json()
    r = _run(admin.req("PATCH", f"/api/tyres/{tyre['id']}/transfer",
                       json={"to_vehicle_id": v2["id"], "odometer": -5}))
    assert r.status_code == 400, r.text[:200]


def test_cross_tenant_tyre_transfer_target_rejected(env):
    admin, beta = env["admin"], env["beta"]
    v1 = _vehicle(admin)
    beta_v = _vehicle(beta)
    tyre = _tyre(admin, v1["id"]).json()
    r = _run(admin.req("PATCH", f"/api/tyres/{tyre['id']}/transfer",
                       json={"to_vehicle_id": beta_v["id"]}))
    assert r.status_code == 400, r.text[:200]


# --- Reconciliation -----------------------------------------------------------

def test_approved_repair_feeds_reconciliation(env):
    import reconciliation
    admin = env["admin"]
    v = _vehicle(admin)
    rid = _repair(admin, v["id"], cost=8000)["id"]
    _drive_to(admin, rid, "approved")
    token = database.current_org_id.set(admin.org_id)
    try:
        recon = _run(reconciliation.payment_reconciliation(vehicle_id=v["id"]))
    finally:
        database.current_org_id.reset(token)
    assert recon["approved_repair_cost"] == 8000
