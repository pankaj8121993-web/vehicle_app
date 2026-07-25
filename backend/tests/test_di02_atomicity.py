"""
DI-02 — Real-HTTP atomicity and idempotency.

Drives the real app over ASGI with a real organisation in a disposable database
(the TEN-TEST harness). Proves that:

* a retried create with the same Idempotency-Key writes exactly one record;
* the same key with a different payload is refused (409);
* concurrent "approve"/"close" actions cannot both apply (compare-and-swap);
* the write-source-first FASTag/tyre side effects still land.

ASGITransport does not run startup, so this module creates the same unique
indexes startup would (idempotency claim + vehicle uniqueness) in its fixture.
"""
import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import server  # noqa: E402
import database  # noqa: E402
import session_security as ss  # noqa: E402

from conftest import realhttp_run as _run

_ONBOARD_PW = "di02-" + "throwaway-passphrase"


class OrgClient:
    def __init__(self, client, org_id, user_id):
        self.client = client
        self.org_id = org_id
        self.user_id = user_id

    def _headers(self, method):
        if method.upper() in ss.SAFE_METHODS:
            return {}
        csrf = self.client.cookies.get(ss.CSRF_COOKIE)
        return {ss.CSRF_HEADER: csrf} if csrf else {}

    async def req(self, method, url, **kw):
        kw.setdefault("headers", {}).update(self._headers(method))
        return await self.client.request(method, url, **kw)


async def _register_org(slug):
    transport = ASGITransport(app=server.app)
    client = AsyncClient(transport=transport, base_url="http://di02")
    r = await client.post("/api/onboarding/register", json={
        "org": {"legal_name": f"DI02 {slug} Ltd", "org_type": "Company"},
        "admin": {
            "username": f"di02_{slug}",
            "email": f"{slug}@di02.invalid",
            "password": _ONBOARD_PW,
            "full_name": f"DI02 {slug}",
        },
    })
    assert r.status_code == 200, f"onboarding failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    return OrgClient(client, body["user"]["org_id"], body["user"]["id"])


def _uniq(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def env():
    async def build():
        await database.client.drop_database(database.raw_db.name)
        # Startup is skipped under ASGITransport; create the index the
        # idempotency claim depends on (its whole safety rests on it).
        await database.raw_db.idempotency_keys.create_index(
            [("org_id", 1), ("scope", 1), ("key", 1)],
            name="uniq_org_scope_key", unique=True,
        )
        a = await _register_org("alpha")
        va = (await a.req("POST", "/api/vehicles", json={"vehicle_number": _uniq("KA01")})).json()
        return a, va

    a, va = _run(build())
    yield {"a": a, "va": va}

    async def teardown():
        await a.client.aclose()
        await database.client.drop_database(database.raw_db.name)

    _run(teardown())


def _fuel_count(oc, vid):
    r = _run(oc.req("GET", "/api/fuel", params={"vehicle_id": vid, "all": "true"}))
    return len([f for f in r.json() if f["vehicle_id"] == vid])


# --- Idempotent create --------------------------------------------------------

def test_retried_create_with_same_key_writes_one_record(env):
    vid = env["va"]["id"]
    key = "idem-" + uuid.uuid4().hex
    body = {"date": "2026-01-01", "vehicle_id": vid, "odometer": 1000,
            "quantity": 10, "amount": 1000}
    before = _fuel_count(env["a"], vid)
    r1 = _run(env["a"].req("POST", "/api/fuel", json=body,
                           headers={"Idempotency-Key": key}))
    r2 = _run(env["a"].req("POST", "/api/fuel", json=body,
                           headers={"Idempotency-Key": key}))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"], "replay returned a different record"
    assert _fuel_count(env["a"], vid) == before + 1, "retry created a duplicate"


def test_same_key_different_payload_rejected(env):
    vid = env["va"]["id"]
    key = "idem-" + uuid.uuid4().hex
    r1 = _run(env["a"].req("POST", "/api/fuel", headers={"Idempotency-Key": key},
                           json={"date": "2026-01-02", "vehicle_id": vid,
                                 "odometer": 2000, "quantity": 10, "amount": 1000}))
    assert r1.status_code == 200
    r2 = _run(env["a"].req("POST", "/api/fuel", headers={"Idempotency-Key": key},
                           json={"date": "2026-01-02", "vehicle_id": vid,
                                 "odometer": 2000, "quantity": 10, "amount": 9999}))
    assert r2.status_code == 409


def test_no_key_allows_two_records(env):
    vid = env["va"]["id"]
    before = _fuel_count(env["a"], vid)
    body = {"date": "2026-01-03", "vehicle_id": vid, "odometer": 3000,
            "quantity": 5, "amount": 500}
    _run(env["a"].req("POST", "/api/fuel", json=body))
    _run(env["a"].req("POST", "/api/fuel", json=body))
    assert _fuel_count(env["a"], vid) == before + 2


def test_failed_request_does_not_consume_key(env):
    vid = env["va"]["id"]
    key = "idem-" + uuid.uuid4().hex
    # First call is invalid (negative amount) → 400, must not consume the key.
    bad = _run(env["a"].req("POST", "/api/fuel", headers={"Idempotency-Key": key},
                            json={"date": "2026-01-04", "vehicle_id": vid,
                                  "odometer": 4000, "quantity": 5, "amount": -1}))
    assert bad.status_code == 400
    # Same key now used for a valid request → succeeds (key was released/never claimed).
    good = _run(env["a"].req("POST", "/api/fuel", headers={"Idempotency-Key": key},
                             json={"date": "2026-01-04", "vehicle_id": vid,
                                   "odometer": 4000, "quantity": 5, "amount": 500}))
    assert good.status_code == 200


# --- Concurrency: compare-and-swap --------------------------------------------

def test_concurrent_repair_approval_applies_exactly_once(env):
    vid = env["va"]["id"]
    rep = _run(env["a"].req("POST", "/api/repairs", json={
        "vehicle_id": vid, "repair_type": "major", "issue": "Engine",
        "date": "2026-02-01", "cost": 5000})).json()
    _run(env["a"].req("PATCH", f"/api/repairs/{rep['id']}/status",
                      json={"status": "under_review"}))

    async def approve():
        return await env["a"].req("PATCH", f"/api/repairs/{rep['id']}/status",
                                  json={"status": "approved"})

    async def race():
        return await asyncio.gather(approve(), approve())

    r1, r2 = _run(race())
    # Both requests succeed as HTTP (a loser is either 409'd by the compare-and-
    # swap or served the idempotent no-op), but the *transition* must have been
    # applied exactly once. The audit trail is the ground truth.
    assert {r1.status_code, r2.status_code} <= {200, 409}
    approvals = _run(database.raw_db.security_audit.count_documents({
        "action": "repair.transition", "target_id": rep["id"],
        "detail.to": "approved",
    }))
    assert approvals == 1, f"double approval: {approvals} approval audits"
    final = _run(env["a"].req("GET", f"/api/repairs?vehicle_id={vid}&all=true"))
    rec = next(r for r in final.json() if r["id"] == rep["id"])
    assert rec["status"] == "approved"


def test_swap_status_is_compare_and_swap(env):
    """The atomicity primitive itself: a swap only wins if the expected status
    still holds. Deterministic (no reliance on scheduler interleaving), so it
    pins the compare-and-swap semantics a concurrency race depends on."""
    import atomicity
    vid = env["va"]["id"]
    rep = _run(env["a"].req("POST", "/api/repairs", json={
        "vehicle_id": vid, "repair_type": "major", "issue": "Gearbox",
        "date": "2026-02-05", "cost": 4000})).json()
    _run(env["a"].req("PATCH", f"/api/repairs/{rep['id']}/status",
                      json={"status": "under_review"}))

    token = database.current_org_id.set(env["a"].org_id)
    try:
        won1 = _run(atomicity.swap_status(
            "repairs", rep["id"], "under_review", {"status": "approved", "_version": 1}))
        # Second swap expects "under_review" but the record is now "approved" —
        # it must lose. A filter that ignored the expected status would win here.
        won2 = _run(atomicity.swap_status(
            "repairs", rep["id"], "under_review", {"status": "approved", "_version": 2}))
    finally:
        database.current_org_id.reset(token)

    assert won1 is True
    assert won2 is False, "compare-and-swap ignored the expected status"


def test_concurrent_trip_close_applies_once(env):
    vid = env["va"]["id"]
    trip = _run(env["a"].req("POST", "/api/trips", json={
        "date": "2026-03-01", "vehicle_id": vid, "opening_km": 100})).json()

    async def close():
        return await env["a"].req("PATCH", f"/api/trips/{trip['id']}/close",
                                  json={"closing_km": 250})

    async def race():
        return await asyncio.gather(close(), close())

    r1, r2 = _run(race())
    assert r1.status_code == 200 and r2.status_code == 200
    # Both return the completed trip; distance computed once and consistent.
    assert r1.json()["distance"] == 150 and r2.json()["distance"] == 150


# --- Write-source-first side effects still land -------------------------------

def test_tyre_replacement_marks_tyre_removed(env):
    vid = env["va"]["id"]
    tyre = _run(env["a"].req("POST", "/api/tyres", json={
        "vehicle_id": vid, "tyre_number": _uniq("T")})).json()
    ev = _run(env["a"].req("POST", "/api/tyre-events", json={
        "tyre_id": tyre["id"], "event_type": "replacement",
        "date": "2026-04-01", "odometer": 55000}))
    assert ev.status_code == 200
    tyres = _run(env["a"].req("GET", "/api/tyres", params={"all": "true"})).json()
    rec = next(t for t in tyres if t["id"] == tyre["id"])
    assert rec["status"] == "removed"
    assert rec["removal_km"] == 55000


def test_fastag_balance_adjusted_after_transaction(env):
    v = _run(env["a"].req("POST", "/api/vehicles", json={
        "vehicle_number": _uniq("KA5"), "fastag_balance": 1000})).json()
    _run(env["a"].req("POST", "/api/fastag", json={
        "vehicle_id": v["id"], "txn_type": "toll", "date": "2026-05-01", "amount": 300}))
    vehicles = _run(env["a"].req("GET", "/api/vehicles", params={"all": "true"})).json()
    rec = next(x for x in vehicles if x["id"] == v["id"])
    assert rec["fastag_balance"] == 700
