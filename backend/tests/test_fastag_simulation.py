"""
FASTAG-01 — demo-only FASTag simulation protection.

The defect: ``POST /fastag/sync/{vehicle_id}`` was ``require_user`` and available
to every organisation. Any authenticated user could fabricate 4–8 random toll
transactions plus a random recharge for a real vehicle and overwrite its
``fastag_balance`` with ``random.uniform(250, 2800)`` — fabricated financial
activity and silent balance corruption in a real tenant.

Two layers: fast unit tests over the pure simulation module, and real-HTTP tests
proving a real (onboarded) organisation is refused while the demo org still works.
"""
import pytest
from httpx import ASGITransport, AsyncClient

import server  # noqa: E402
import database  # noqa: E402
import session_security as ss  # noqa: E402
import fastag_simulation as fs
from fastag_simulation import (
    PROVIDER_INTEGRATION_AVAILABLE,
    SIMULATION_SOURCE,
    build_simulated_batch,
    computed_balance,
    simulation_allowed,
)
from demo_seed import DEMO_ORG_ID

from conftest import realhttp_run as _run  # shared loop (see conftest)


# --- Unit: the demo-only guard ------------------------------------------------

def test_demo_user_in_demo_org_is_allowed():
    assert simulation_allowed({"is_demo": True, "org_id": DEMO_ORG_ID})


@pytest.mark.parametrize("user", [
    {"is_demo": False, "org_id": DEMO_ORG_ID},          # not flagged demo
    {"is_demo": True, "org_id": "org-real"},            # demo flag, wrong org
    {"is_demo": False, "org_id": "org-real"},           # ordinary real user
    {"org_id": DEMO_ORG_ID},                            # missing flag
    {},                                                 # nothing
])
def test_non_demo_users_are_refused(user):
    """Both markers must agree — a stray is_demo flag or the demo org alone is
    not enough, so a real tenant can never satisfy it."""
    assert not simulation_allowed(user)


def test_assert_raises_403_off_demo():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        fs.assert_simulation_allowed({"is_demo": False, "org_id": "org-real"})
    assert e.value.status_code == 403


# --- Unit: batch generation, idempotency, balance -----------------------------

def _user():
    return {"user_id": "u-demo", "is_demo": True, "org_id": DEMO_ORG_ID}


def test_batch_is_deterministic_in_the_key():
    """Same key → identical run (idempotency depends on this)."""
    a = build_simulated_batch("v1", _user(), "key-abc")
    b = build_simulated_batch("v1", _user(), "key-abc")
    assert [(t["txn_type"], t["amount"], t["date"]) for t in a] == \
           [(t["txn_type"], t["amount"], t["date"]) for t in b]


def test_different_keys_differ():
    a = build_simulated_batch("v1", _user(), "key-a")
    b = build_simulated_batch("v1", _user(), "key-b")
    assert [t["id"] for t in a] != [t["id"] for t in b]


def test_every_row_is_marked_as_simulation():
    for t in build_simulated_batch("v1", _user(), "k"):
        assert t["source"] == SIMULATION_SOURCE
        assert t["sim_batch"] == fs._batch_key("v1", "k") or t["sim_batch"] == "k"


def test_amounts_are_from_the_bounded_sets():
    for t in build_simulated_batch("v1", _user(), "k"):
        if t["txn_type"] == "toll":
            assert t["amount"] in {float(a) for a in fs.TOLL_AMOUNTS}
        else:
            assert t["amount"] in {float(a) for a in fs.RECHARGE_AMOUNTS}


def test_run_size_is_bounded():
    tolls = [t for t in build_simulated_batch("v1", _user(), "k") if t["txn_type"] == "toll"]
    assert 4 <= len(tolls) <= fs.MAX_TOLLS_PER_RUN


def test_balance_is_computed_not_random():
    txns = [
        {"txn_type": "recharge", "amount": 1000},
        {"txn_type": "toll", "amount": 200},
        {"txn_type": "toll", "amount": 50},
    ]
    assert computed_balance(txns) == 750.0


def test_balance_is_stable_on_replay():
    txns = build_simulated_batch("v1", _user(), "k")
    assert computed_balance(txns) == computed_balance(txns)


def test_no_live_provider():
    """A future live path must fail closed until it actually exists."""
    assert PROVIDER_INTEGRATION_AVAILABLE is False


def test_simulation_source_is_distinct_from_manual():
    """Simulated rows must be identifiable and never look like a manual import
    (which carries no source) or the old 'auto_sync' marker."""
    assert SIMULATION_SOURCE not in ("", None, "auto_sync")


# --- Real HTTP: production tenants are protected ------------------------------

class _Client:
    def __init__(self, client, org_id):
        self.client = client
        self.org_id = org_id

    def _h(self, method):
        if method in ss.SAFE_METHODS:
            return {}
        csrf = self.client.cookies.get(ss.CSRF_COOKIE)
        return {ss.CSRF_HEADER: csrf} if csrf else {}

    async def req(self, method, url, **kw):
        kw.setdefault("headers", {}).update(self._h(method))
        return await self.client.request(method, url, **kw)


async def _demo_client():
    t = ASGITransport(app=server.app)
    c = AsyncClient(transport=t, base_url="http://fastag")
    r = await c.post("/api/demo/enter", json={"role": "org_admin"})
    assert r.status_code == 200, r.text[:200]
    return _Client(c, r.json()["user"]["org_id"])


async def _real_org_client(slug):
    t = ASGITransport(app=server.app)
    c = AsyncClient(transport=t, base_url="http://fastag")
    r = await c.post("/api/onboarding/register", json={
        "org": {"legal_name": f"FastagReal {slug} Ltd", "org_type": "Company"},
        "admin": {"username": f"fastag_{slug}", "email": f"{slug}@fastag.invalid",
                  "password": "FastagPassphrase123", "full_name": f"Fastag {slug}"},
    })
    assert r.status_code == 200, r.text[:200]
    return _Client(c, r.json()["user"]["org_id"])


@pytest.fixture(scope="module")
def env():
    async def build():
        await database.client.drop_database(database.raw_db.name)
        demo = await _demo_client()
        real = await _real_org_client("alpha")
        # A demo vehicle with a linked FASTag.
        dv = await demo.req("POST", "/api/vehicles",
                            json={"vehicle_number": "DEMO-FT", "fastag_number": "FT-DEMO-1"})
        assert dv.status_code == 200, dv.text[:200]
        # A real vehicle with a linked FASTag.
        rv = await real.req("POST", "/api/vehicles",
                            json={"vehicle_number": "REAL-FT", "fastag_number": "FT-REAL-1"})
        assert rv.status_code == 200, rv.text[:200]
        return {"demo": demo, "real": real,
                "demo_vehicle": dv.json()["id"], "real_vehicle": rv.json()["id"]}

    e = _run(build())
    yield e

    async def teardown():
        await e["demo"].client.aclose()
        await e["real"].client.aclose()
        await database.client.drop_database(database.raw_db.name)

    _run(teardown())


def test_real_org_cannot_run_simulation(env):
    """The core FASTAG-01 guarantee: a real tenant is refused, fail-closed."""
    r = _run(env["real"].req("POST", f"/api/fastag/sync/{env['real_vehicle']}"))
    assert r.status_code == 403, f"real org sync -> {r.status_code} {r.text[:200]}"


def test_real_org_simulation_writes_nothing(env):
    """Refusal must not have produced any transaction or touched the balance."""
    before = _run(env["real"].req("GET", "/api/fastag", params={"all": "true"})).json()
    _run(env["real"].req("POST", f"/api/fastag/sync/{env['real_vehicle']}"))
    after = _run(env["real"].req("GET", "/api/fastag", params={"all": "true"})).json()
    b = before if isinstance(before, list) else before.get("items", [])
    a = after if isinstance(after, list) else after.get("items", [])
    assert len(a) == len(b) == 0


def test_demo_org_can_run_simulation(env):
    r = _run(env["demo"].req("POST", f"/api/fastag/sync/{env['demo_vehicle']}"))
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["simulated"] is True
    assert body["synced_transactions"] >= 4


def test_simulation_is_idempotent_under_a_key(env):
    """Same idempotency key → no new transactions on replay (safe retry)."""
    key = "run-42"
    first = _run(env["demo"].req(
        "POST", f"/api/fastag/sync/{env['demo_vehicle']}",
        params={"idempotency_key": key}))
    assert first.status_code == 200
    count1 = _run(env["demo"].req("GET", "/api/fastag", params={"all": "true"})).json()
    n1 = len(count1 if isinstance(count1, list) else count1.get("items", []))

    second = _run(env["demo"].req(
        "POST", f"/api/fastag/sync/{env['demo_vehicle']}",
        params={"idempotency_key": key}))
    assert second.status_code == 200
    assert second.json().get("replayed") is True
    count2 = _run(env["demo"].req("GET", "/api/fastag", params={"all": "true"})).json()
    n2 = len(count2 if isinstance(count2, list) else count2.get("items", []))
    assert n1 == n2, "replay created new transactions"


def test_demo_balance_matches_computed(env):
    """The returned balance equals recharges − tolls over the vehicle's rows."""
    _run(env["demo"].req("POST", f"/api/fastag/sync/{env['demo_vehicle']}"))
    txns = _run(env["demo"].req("GET", "/api/fastag", params={"all": "true"})).json()
    items = txns if isinstance(txns, list) else txns.get("items", [])
    mine = [t for t in items if t.get("vehicle_id") == env["demo_vehicle"]]
    expected = computed_balance(mine)
    veh = _run(env["demo"].req("GET", "/api/vehicles", params={"all": "true"})).json()
    vlist = veh if isinstance(veh, list) else veh.get("items", [])
    v = next(x for x in vlist if x["id"] == env["demo_vehicle"])
    assert abs(v["fastag_balance"] - expected) < 0.01
