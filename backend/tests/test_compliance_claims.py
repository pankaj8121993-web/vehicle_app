"""
OPS-04 — Compliance, documents, accidents and claims (real HTTP).

Proves document validity (expiry ≥ issue) and supersede history; cross-tenant
vehicle/driver/trip rejection on accidents; the insurance-claim lifecycle with
its transition validity, approval/settlement ceilings, idempotent settlement,
closed-claim lock and generic-bypass rejection; and audit coverage.
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


DEMO_ROLES = {"org_admin": "admin", "operations": "data_entry"}
_PW = "ops04-" + "throwaway-passphrase"


async def _enter_demo(role):
    transport = ASGITransport(app=server.app)
    client = AsyncClient(transport=transport, base_url="http://ops04")
    r = await client.post("/api/demo/enter", json={"role": role})
    assert r.status_code == 200, f"demo/enter {role}: {r.status_code} {r.text[:200]}"
    return Client(client, role, r.json()["user"]["org_id"])


async def _register_org(slug):
    transport = ASGITransport(app=server.app)
    client = AsyncClient(transport=transport, base_url="http://ops04b")
    r = await client.post("/api/onboarding/register", json={
        "org": {"legal_name": f"OPS04 {slug} Ltd", "org_type": "Company"},
        "admin": {"username": f"ops04_{slug}", "email": f"{slug}@ops04.invalid",
                  "password": _PW, "full_name": f"OPS04 {slug}"},
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
    return _run(oc.req("POST", "/api/vehicles", json={"vehicle_number": _uniq("KA-CMP")})).json()


def _accident(oc, vid, **extra):
    body = {"vehicle_id": vid, "date": "2026-06-01", "claim_amount": 10000}
    body.update(extra)
    return _run(oc.req("POST", "/api/accidents", json=body))


def _claim(oc, aid, status, **extra):
    body = {"status": status}
    body.update(extra)
    return _run(oc.req("PATCH", f"/api/accidents/{aid}/claim", json=body))


def _audits(action, target_id):
    return _run(database.raw_db.security_audit.count_documents(
        {"action": action, "target_id": target_id}))


# --- Documents ----------------------------------------------------------------

def test_document_expiry_before_issue_rejected(env):
    admin = _admin(env)
    v = _vehicle(admin)
    r = _run(admin.req("POST", "/api/documents", json={
        "vehicle_id": v["id"], "doc_type": "Insurance",
        "issue_date": "2026-06-01", "expiry_date": "2026-01-01"}))
    assert r.status_code == 400, r.text[:200]


def test_document_supersede_preserves_history(env):
    admin = _admin(env)
    v = _vehicle(admin)
    d1 = _run(admin.req("POST", "/api/documents", json={
        "vehicle_id": v["id"], "doc_type": "Insurance",
        "issue_date": "2025-01-01", "expiry_date": "2026-01-01"})).json()
    assert d1["is_current"] is True
    d2 = _run(admin.req("POST", "/api/documents", json={
        "vehicle_id": v["id"], "doc_type": "Insurance",
        "issue_date": "2026-01-01", "expiry_date": "2027-01-01"})).json()
    assert d2["is_current"] is True
    # The old record still exists but is now superseded (history preserved).
    docs = _run(admin.req("GET", "/api/documents", params={"vehicle_id": v["id"], "all": "true"})).json()
    items = docs if isinstance(docs, list) else docs.get("items", [])
    old = next(x for x in items if x["id"] == d1["id"])
    assert old["is_current"] is False and old["superseded_by"] == d2["id"]


# --- Accident references ------------------------------------------------------

def test_cross_tenant_vehicle_on_accident_rejected(env):
    admin, beta = _admin(env), env["beta"]
    beta_v = _vehicle(beta)
    r = _accident(admin, beta_v["id"])
    assert r.status_code == 400, r.text[:200]


def test_cross_tenant_trip_on_accident_rejected(env):
    admin, beta = _admin(env), env["beta"]
    v = _vehicle(admin)
    beta_v = _vehicle(beta)
    beta_trip = _run(beta.req("POST", "/api/trips", json={
        "date": "2026-06-01", "vehicle_id": beta_v["id"], "opening_km": 0})).json()
    r = _accident(admin, v["id"], trip_id=beta_trip["id"])
    assert r.status_code == 400, r.text[:200]


# --- Claim lifecycle ----------------------------------------------------------

def test_accident_created_reported(env):
    admin = _admin(env)
    v = _vehicle(admin)
    a = _accident(admin, v["id"]).json()
    assert a["claim_status"] == "reported"


def test_invalid_claim_transition_rejected(env):
    admin = _admin(env)
    v = _vehicle(admin)
    a = _accident(admin, v["id"]).json()
    # reported → settled skips the whole middle.
    r = _claim(admin, a["id"], "settled", settlement_amount=100)
    assert r.status_code == 409, r.text[:200]


def test_full_claim_flow_and_ceilings(env):
    admin = _admin(env)
    v = _vehicle(admin)
    a = _accident(admin, v["id"], claim_amount=10000).json()
    assert _claim(admin, a["id"], "evidence_collected").status_code == 200
    assert _claim(admin, a["id"], "claim_submitted").status_code == 200
    assert _claim(admin, a["id"], "under_survey").status_code == 200
    # Approve above claim is refused.
    assert _claim(admin, a["id"], "approved", approved_amount=15000).status_code == 400
    assert _claim(admin, a["id"], "approved", approved_amount=8000).status_code == 200
    # Settlement above approved is refused.
    assert _claim(admin, a["id"], "settled", settlement_amount=9000).status_code == 400
    ok = _claim(admin, a["id"], "settled", settlement_amount=8000)
    assert ok.status_code == 200 and ok.json()["settlement_amount"] == 8000
    assert _audits("accident.claim", a["id"]) >= 5


def test_double_settlement_idempotent(env):
    admin = _admin(env)
    v = _vehicle(admin)
    a = _accident(admin, v["id"], claim_amount=5000).json()
    for s in ("evidence_collected", "claim_submitted", "under_survey"):
        _claim(admin, a["id"], s)
    _claim(admin, a["id"], "approved", approved_amount=5000)
    r1 = _claim(admin, a["id"], "settled", settlement_amount=5000)
    r2 = _claim(admin, a["id"], "settled", settlement_amount=9999)
    assert r1.status_code == 200 and r2.status_code == 200
    # The second is an idempotent no-op — settlement not overwritten.
    assert r2.json()["settlement_amount"] == 5000


def test_data_entry_cannot_approve_claim(env):
    admin, ops = _admin(env), env["clients"]["operations"]
    v = _vehicle(admin)
    a = _accident(admin, v["id"]).json()
    for s in ("evidence_collected", "claim_submitted", "under_survey"):
        _claim(admin, a["id"], s)
    r = _claim(ops, a["id"], "approved", approved_amount=100)
    assert r.status_code == 403, r.text[:200]


def test_closed_claim_locked(env):
    admin = _admin(env)
    v = _vehicle(admin)
    a = _accident(admin, v["id"], claim_amount=5000).json()
    for s in ("evidence_collected", "claim_submitted", "under_survey"):
        _claim(admin, a["id"], s)
    _claim(admin, a["id"], "approved", approved_amount=5000)
    _claim(admin, a["id"], "settled", settlement_amount=5000)
    assert _claim(admin, a["id"], "closed").status_code == 200
    # A closed claim is terminal, and its financials are locked to generic edits.
    assert _claim(admin, a["id"], "settled", settlement_amount=1).status_code == 409
    r = _run(admin.req("PUT", f"/api/accidents/{a['id']}", json={"settlement_amount": 1}))
    assert r.status_code == 409, r.text[:200]


def test_generic_claim_status_write_rejected(env):
    admin = _admin(env)
    v = _vehicle(admin)
    a = _accident(admin, v["id"]).json()
    r = _run(admin.req("PUT", f"/api/accidents/{a['id']}", json={"claim_status": "approved"}))
    assert r.status_code == 409, r.text[:200]
