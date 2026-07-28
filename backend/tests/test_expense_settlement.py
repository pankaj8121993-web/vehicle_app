"""
OPS-02 — Expense approval, payment and trip settlement (real HTTP).

Proves the operational financial lifecycle: approval separate from payment,
approved ≤ submitted, paid ≤ approved outstanding, rejected cannot be paid,
idempotent approval, no double payment, reversal restores outstanding,
self-approval refused, cross-tenant isolation, advances in settlement, settlement
totals reconciling with the canonical ledger, and generic-write locks.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import server  # noqa: E402
import database  # noqa: E402
import session_security as ss  # noqa: E402

from conftest import realhttp_run as _run


class Client:
    def __init__(self, client, role, org_id, user_id=None):
        self.client = client
        self.role = role
        self.org_id = org_id
        self.user_id = user_id

    def _h(self, method):
        if method in ss.SAFE_METHODS:
            return {}
        csrf = self.client.cookies.get(ss.CSRF_COOKIE)
        return {ss.CSRF_HEADER: csrf} if csrf else {}

    async def req(self, method, url, **kw):
        kw.setdefault("headers", {}).update(self._h(method))
        return await self.client.request(method, url, **kw)


DEMO_ROLES = {"org_admin": "admin", "owner": "management", "operations": "data_entry"}
_PW = "ops02-" + "throwaway-passphrase"


async def _enter_demo(role):
    transport = ASGITransport(app=server.app)
    client = AsyncClient(transport=transport, base_url="http://ops02")
    r = await client.post("/api/demo/enter", json={"role": role})
    assert r.status_code == 200, f"demo/enter {role}: {r.status_code} {r.text[:200]}"
    j = r.json()["user"]
    return Client(client, role, j["org_id"], j["id"])


async def _register_org(slug):
    transport = ASGITransport(app=server.app)
    client = AsyncClient(transport=transport, base_url="http://ops02b")
    r = await client.post("/api/onboarding/register", json={
        "org": {"legal_name": f"OPS02 {slug} Ltd", "org_type": "Company"},
        "admin": {"username": f"ops02_{slug}", "email": f"{slug}@ops02.invalid",
                  "password": _PW, "full_name": f"OPS02 {slug}"},
    })
    assert r.status_code == 200, f"onboarding failed: {r.status_code} {r.text[:200]}"
    j = r.json()["user"]
    return Client(client, "admin", j["org_id"], j["id"])


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
    return _run(oc.req("POST", "/api/vehicles", json={"vehicle_number": _uniq("KA-EXP")})).json()


def _expense(oc, vid, amount=1000, **extra):
    body = {"vehicle_id": vid, "category": "Miscellaneous", "date": "2026-06-01", "amount": amount}
    body.update(extra)
    r = _run(oc.req("POST", "/api/expenses", json=body))
    assert r.status_code == 200, r.text[:200]
    return r.json()


def _approve(oc, eid, **body):
    return _run(oc.req("PATCH", f"/api/expenses/{eid}/approve", json=body))


def _pay(oc, eid, amount, **extra):
    body = {"amount": amount}
    body.update(extra)
    return _run(oc.req("POST", f"/api/expenses/{eid}/payments", json=body))


def _audits(action, target_id):
    return _run(database.raw_db.security_audit.count_documents(
        {"action": action, "target_id": target_id}))


# --- Submission / approval ----------------------------------------------------

def test_expense_created_submitted(env):
    v = _vehicle(_admin(env))
    e = _expense(_admin(env), v["id"])
    assert e["approval_status"] == "submitted"
    assert e["approved_amount"] is None and e["paid_amount"] == 0


def test_approval_within_submitted(env):
    admin, owner = _admin(env), env["clients"]["owner"]
    v = _vehicle(admin)
    e = _expense(admin, v["id"], amount=1000)
    r = _approve(owner, e["id"], approved_amount=800)
    assert r.status_code == 200, r.text[:200]
    assert r.json()["approval_status"] == "approved" and r.json()["approved_amount"] == 800
    assert _audits("expense.approve", e["id"]) == 1


def test_approval_exceeding_submitted_rejected(env):
    admin, owner = _admin(env), env["clients"]["owner"]
    v = _vehicle(admin)
    e = _expense(admin, v["id"], amount=1000)
    r = _approve(owner, e["id"], approved_amount=1500)
    assert r.status_code == 400, r.text[:200]


def test_double_approval_idempotent(env):
    admin, owner = _admin(env), env["clients"]["owner"]
    v = _vehicle(admin)
    e = _expense(admin, v["id"], amount=500)
    r1 = _approve(owner, e["id"])
    r2 = _approve(owner, e["id"])
    assert r1.status_code == 200 and r2.status_code == 200
    assert _audits("expense.approve", e["id"]) == 1


def test_self_approval_refused(env):
    """The submitter cannot approve their own expense."""
    owner = env["clients"]["owner"]  # management: may both submit and approve
    v = _vehicle(owner)
    e = _expense(owner, v["id"], amount=400)
    r = _approve(owner, e["id"])
    assert r.status_code == 403, r.text[:200]


def test_data_entry_cannot_approve(env):
    admin, ops = _admin(env), env["clients"]["operations"]
    v = _vehicle(admin)
    e = _expense(ops, v["id"], amount=300)
    r = _approve(ops, e["id"])
    assert r.status_code == 403, r.text[:200]


# --- Payment ------------------------------------------------------------------

def test_payment_within_approved(env):
    admin, owner = _admin(env), env["clients"]["owner"]
    v = _vehicle(admin)
    e = _expense(admin, v["id"], amount=1000)
    _approve(owner, e["id"], approved_amount=1000)
    r = _pay(owner, e["id"], 600)
    assert r.status_code == 200, r.text[:200]
    assert r.json()["paid_amount"] == 600 and r.json()["outstanding"] == 400
    r2 = _pay(owner, e["id"], 400)
    assert r2.status_code == 200 and r2.json()["paid_amount"] == 1000


def test_payment_exceeding_outstanding_rejected(env):
    admin, owner = _admin(env), env["clients"]["owner"]
    v = _vehicle(admin)
    e = _expense(admin, v["id"], amount=1000)
    _approve(owner, e["id"], approved_amount=700)
    r = _pay(owner, e["id"], 800)
    assert r.status_code == 400, r.text[:200]


def test_unapproved_cannot_be_paid(env):
    admin, owner = _admin(env), env["clients"]["owner"]
    v = _vehicle(admin)
    e = _expense(admin, v["id"], amount=1000)
    r = _pay(owner, e["id"], 100)
    assert r.status_code == 409, r.text[:200]


def test_rejected_cannot_be_paid(env):
    admin, owner = _admin(env), env["clients"]["owner"]
    v = _vehicle(admin)
    e = _expense(admin, v["id"], amount=1000)
    rej = _run(owner.req("PATCH", f"/api/expenses/{e['id']}/reject", json={"reason": "no receipt"}))
    assert rej.status_code == 200 and rej.json()["approval_status"] == "rejected"
    r = _pay(owner, e["id"], 100)
    assert r.status_code == 409, r.text[:200]
    # And approving a rejected expense is refused.
    assert _approve(owner, e["id"]).status_code == 409


def test_double_payment_idempotent_with_key(env):
    admin, owner = _admin(env), env["clients"]["owner"]
    v = _vehicle(admin)
    e = _expense(admin, v["id"], amount=1000)
    _approve(owner, e["id"], approved_amount=1000)
    key = "idem-" + uuid.uuid4().hex
    r1 = _run(owner.req("POST", f"/api/expenses/{e['id']}/payments",
                        json={"amount": 500}, headers={"Idempotency-Key": key}))
    r2 = _run(owner.req("POST", f"/api/expenses/{e['id']}/payments",
                        json={"amount": 500}, headers={"Idempotency-Key": key}))
    assert r1.status_code == 200 and r2.status_code == 200
    # The replay must not double the paid total.
    final = _run(owner.req("GET", f"/api/expenses/{e['id']}/payments")).json()
    assert sum(p["amount"] for p in final["payments"] if p["kind"] == "payment") == 500


def test_reversal_restores_outstanding(env):
    admin, owner = _admin(env), env["clients"]["owner"]
    v = _vehicle(admin)
    e = _expense(admin, v["id"], amount=1000)
    _approve(owner, e["id"], approved_amount=1000)
    pay = _pay(owner, e["id"], 1000)
    pid = pay.json()["payment"]["id"]
    rev = _run(owner.req("POST", f"/api/expenses/{e['id']}/payments/{pid}/reverse", json={}))
    assert rev.status_code == 200, rev.text[:200]
    assert rev.json()["paid_amount"] == 0 and rev.json()["outstanding"] == 1000
    # Outstanding restored → a fresh payment is allowed again.
    assert _pay(owner, e["id"], 200).status_code == 200


def test_generic_amount_edit_locked_after_approval(env):
    admin, owner = _admin(env), env["clients"]["owner"]
    v = _vehicle(admin)
    e = _expense(admin, v["id"], amount=1000)
    _approve(owner, e["id"])
    r = _run(admin.req("PUT", f"/api/expenses/{e['id']}", json={"amount": 5}))
    assert r.status_code == 409, r.text[:200]
    # Protected workflow fields are still refused on a generic write too.
    r2 = _run(admin.req("PUT", f"/api/expenses/{e['id']}", json={"approval_status": "approved"}))
    assert r2.status_code == 400, r2.text[:200]


# --- Cross-tenant -------------------------------------------------------------

def test_cross_tenant_expense_isolated(env):
    beta = env["beta"]
    v = _vehicle(beta)
    e = _expense(beta, v["id"], amount=500)
    # Demo-org admin cannot see or act on beta's expense (404, no disclosure).
    r = _approve(_admin(env), e["id"])
    assert r.status_code == 404, r.text[:200]


# --- Advances & settlement ----------------------------------------------------

def test_advance_recovery_bounds(env):
    admin, owner = _admin(env), env["clients"]["owner"]
    d = _run(admin.req("POST", "/api/drivers", json={"name": _uniq("Drv")})).json()
    adv = _run(admin.req("POST", "/api/advances", json={
        "driver_id": d["id"], "date": "2026-06-01", "amount": 1000})).json()
    assert adv["status"] == "outstanding" and adv["recovered_amount"] == 0
    over = _run(owner.req("PATCH", f"/api/advances/{adv['id']}/recover", json={"amount": 1500}))
    assert over.status_code == 400, over.text[:200]
    ok = _run(owner.req("PATCH", f"/api/advances/{adv['id']}/recover", json={"amount": 1000}))
    assert ok.status_code == 200 and ok.json()["status"] == "recovered"


def test_settlement_totals_and_reconciliation(env):
    admin, owner = _admin(env), env["clients"]["owner"]
    import reconciliation
    v = _vehicle(admin)
    d = _run(admin.req("POST", "/api/drivers", json={"name": _uniq("Drv")})).json()
    # A completed trip with direct expenses.
    trip = _run(admin.req("POST", "/api/trips", json={
        "date": "2026-06-10", "vehicle_id": v["id"], "driver_id": d["id"],
        "opening_km": 0, "closing_km": 100, "toll_expense": 200, "misc_expense": 50})).json()
    # A trip-linked manual expense: approved 300 of 400.
    e = _expense(admin, v["id"], amount=400, trip_id=trip["id"])
    _approve(owner, e["id"], approved_amount=300)
    # A driver advance against the trip.
    _run(admin.req("POST", "/api/advances", json={
        "driver_id": d["id"], "trip_id": trip["id"], "date": "2026-06-09", "amount": 500}))

    view = _run(owner.req("GET", f"/api/trips/{trip['id']}/settlement")).json()
    assert view["trip_direct_expenses"] == 250   # toll 200 + misc 50
    assert view["approved_expenses"] == 300
    assert view["eligible_expenses"] == 550       # direct + approved
    assert view["advances"] == 500
    assert view["net_payable_to_driver"] == -200  # 300 approved − 500 advance
    # Trip-direct figure reconciles with the canonical trip economics.
    token = database.current_org_id.set(owner.org_id)
    try:
        econ = _run(reconciliation.trip_economics(trip["id"]))
    finally:
        database.current_org_id.reset(token)
    assert view["trip_direct_expenses"] == econ["direct_expenses"]


def test_rejected_expense_excluded_from_ledger(env):
    admin, owner = _admin(env), env["clients"]["owner"]
    v = _vehicle(admin)
    e = _expense(admin, v["id"], amount=777)
    ledger_before = _run(admin.req("GET", "/api/expenses/ledger", params={"vehicle_id": v["id"]})).json()
    assert any(r["amount"] == 777 for r in ledger_before["rows"])
    _run(owner.req("PATCH", f"/api/expenses/{e['id']}/reject", json={"reason": "dup"}))
    ledger_after = _run(admin.req("GET", "/api/expenses/ledger", params={"vehicle_id": v["id"]})).json()
    assert not any(r["source_id"] == e["id"] for r in ledger_after["rows"])


def test_settle_blocked_by_pending_approval(env):
    admin, owner = _admin(env), env["clients"]["owner"]
    v = _vehicle(admin)
    d = _run(admin.req("POST", "/api/drivers", json={"name": _uniq("Drv")})).json()
    trip = _run(admin.req("POST", "/api/trips", json={
        "date": "2026-06-11", "vehicle_id": v["id"], "driver_id": d["id"],
        "opening_km": 0, "closing_km": 10})).json()  # created ongoing
    _run(admin.req("PATCH", f"/api/trips/{trip['id']}/close", json={"closing_km": 10}))  # → completed
    # A submitted (unapproved) linked expense blocks settlement.
    _expense(admin, v["id"], amount=100, trip_id=trip["id"])
    blocked = _run(owner.req("PATCH", f"/api/trips/{trip['id']}/settle", json={}))
    assert blocked.status_code == 409, blocked.text[:200]
    ok = _run(owner.req("PATCH", f"/api/trips/{trip['id']}/settle", json={"override_pending": True}))
    assert ok.status_code == 200 and ok.json()["status"] == "settlement_pending"
