"""
DI-03 — Reconciliation with known fixtures and expected totals.

Real-HTTP against the app with two organisations in a disposable database. One
org is seeded with a hand-computed set of records; the tests assert the
reconciliation service reproduces the totals exactly, that the grouped parts
reconcile to the whole, that the FASTag balance cache is verified against source
(drift + duplicates), that report/ledger/reconciliation totals agree, and that
org A's reconciliation never sees org B's data.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import server  # noqa: E402
import database  # noqa: E402
import session_security as ss  # noqa: E402

from conftest import realhttp_run as _run

_ONBOARD_PW = "di03-" + "throwaway-passphrase"


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
    client = AsyncClient(transport=transport, base_url="http://di03")
    r = await client.post("/api/onboarding/register", json={
        "org": {"legal_name": f"DI03 {slug} Ltd", "org_type": "Company"},
        "admin": {"username": f"di03_{slug}", "email": f"{slug}@di03.invalid",
                  "password": _ONBOARD_PW, "full_name": f"DI03 {slug}"},
    })
    assert r.status_code == 200, f"onboarding failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    return OrgClient(client, body["user"]["org_id"], body["user"]["id"])


def _uniq(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# Hand-computed expected totals for the seeded vehicle (see build()).
EXPECTED = {
    "fuel": 9000.0, "repairs": 3000.0, "maintenance": 2000.0, "tyres": 8000.0,
    "fastag": 500.0, "trip_direct": 200.0, "accidents": 1500.0,
    "other": 1000.0, "total": 25200.0, "distance": 500.0,
}


@pytest.fixture(scope="module")
def env():
    async def build():
        await database.client.drop_database(database.raw_db.name)
        a = await _register_org("alpha")
        b = await _register_org("bravo")
        # Vehicle with a zero opening FASTag balance so net == stored is checkable.
        v = (await a.req("POST", "/api/vehicles", json={
            "vehicle_number": _uniq("KA01"), "fastag_balance": 0})).json()
        vid = v["id"]
        # Fuel: 40L@4000 then 50L@5000 → qty 90, amount 9000, mileage 500/50=10.
        await a.req("POST", "/api/fuel", json={"date": "2026-01-01", "vehicle_id": vid,
                    "odometer": 1000, "quantity": 40, "amount": 4000})
        await a.req("POST", "/api/fuel", json={"date": "2026-01-10", "vehicle_id": vid,
                    "odometer": 1500, "quantity": 50, "amount": 5000})
        # Repair 3000 (open), Service 2000, Tyre 8000.
        await a.req("POST", "/api/repairs", json={"vehicle_id": vid, "repair_type": "major",
                    "issue": "Engine", "date": "2026-01-05", "cost": 3000})
        await a.req("POST", "/api/services", json={"vehicle_id": vid, "service_type": "Oil",
                    "date": "2026-01-06", "cost": 2000})
        await a.req("POST", "/api/tyres", json={"vehicle_id": vid, "tyre_number": _uniq("T"),
                    "installation_date": "2026-01-02", "cost": 8000})
        # FASTag: recharge 2000, toll 500 → net 1500, ledger cost (toll) 500.
        await a.req("POST", "/api/fastag", json={"vehicle_id": vid, "txn_type": "recharge",
                    "date": "2026-01-03", "amount": 2000})
        await a.req("POST", "/api/fastag", json={"vehicle_id": vid, "txn_type": "toll",
                    "date": "2026-01-04", "amount": 500})
        # Trip: distance 500, direct toll 200.
        await a.req("POST", "/api/trips", json={"date": "2026-01-04", "vehicle_id": vid,
                    "opening_km": 1000, "closing_km": 1500, "toll_expense": 200})
        # Accident: repair_cost 1500 (ledger), claim 5000, settlement 3000.
        await a.req("POST", "/api/accidents", json={"vehicle_id": vid, "date": "2026-01-07",
                    "repair_cost": 1500, "claim_amount": 5000, "settlement_amount": 3000})
        # Manual expense: Insurance 1000 → "other".
        await a.req("POST", "/api/expenses", json={"vehicle_id": vid, "category": "Insurance",
                    "date": "2026-01-08", "amount": 1000})
        return a, b, vid

    a, b, vid = _run(build())
    yield {"a": a, "b": b, "vid": vid}

    async def teardown():
        await a.client.aclose()
        await b.client.aclose()
        await database.client.drop_database(database.raw_db.name)

    _run(teardown())


def _get(oc, url, **params):
    r = _run(oc.req("GET", url, params=params or None))
    assert r.status_code == 200, f"{url}: {r.status_code} {r.text[:200]}"
    return r.json()


# --- Cost breakdown -----------------------------------------------------------

def test_vehicle_cost_breakdown_matches_expected(env):
    data = _get(env["a"], f"/api/reconciliation/vehicle/{env['vid']}")
    cb = data["cost_breakdown"]
    g = cb["groups"]
    assert g["fuel"] == EXPECTED["fuel"]
    assert g["repairs"] == EXPECTED["repairs"]
    assert g["maintenance"] == EXPECTED["maintenance"]
    assert g["tyres"] == EXPECTED["tyres"]
    assert g["fastag"] == EXPECTED["fastag"]
    assert g["trip_direct"] == EXPECTED["trip_direct"]
    assert g["accidents"] == EXPECTED["accidents"]
    assert cb["other"] == EXPECTED["other"]
    assert cb["total"] == EXPECTED["total"]
    assert cb["distance_km"] == EXPECTED["distance"]


def test_breakdown_parts_reconcile_to_total(env):
    cb = _get(env["a"], f"/api/reconciliation/vehicle/{env['vid']}")["cost_breakdown"]
    assert cb["reconciles"] is True
    assert round(sum(cb["groups"].values()) + cb["other"], 2) == cb["total"]


def test_cost_per_km(env):
    cb = _get(env["a"], f"/api/reconciliation/vehicle/{env['vid']}")["cost_breakdown"]
    assert cb["cost_per_km"] == round(EXPECTED["total"] / EXPECTED["distance"], 2)


# --- Fuel ---------------------------------------------------------------------

def test_fuel_reconciliation(env):
    fuel = _get(env["a"], f"/api/reconciliation/vehicle/{env['vid']}")["fuel"]
    assert fuel["entries"] == 2
    assert fuel["total_quantity"] == 90.0
    assert fuel["total_amount"] == 9000.0
    assert fuel["avg_rate"] == 100.0
    assert fuel["avg_mileage"] == 10.0
    assert fuel["odometer_continuity_breaks"] == []


# --- FASTag cache verification ------------------------------------------------

def test_fastag_balance_cache_matches_source(env):
    fastag = _get(env["a"], f"/api/reconciliation/vehicle/{env['vid']}")["fastag"]
    assert fastag["toll_total"] == 500.0
    assert fastag["recharge_total"] == 2000.0
    assert fastag["net"] == 1500.0
    drift = next(d for d in fastag["balance_cache"] if d["vehicle_id"] == env["vid"])
    assert drift["computed_net"] == 1500.0
    assert drift["stored_balance"] == 1500.0
    assert drift["drift"] == 0.0


def test_fastag_drift_detected_for_corrupt_balance(env):
    # A vehicle whose stored balance disagrees with its (empty) transaction set.
    v = _run(env["a"].req("POST", "/api/vehicles", json={
        "vehicle_number": _uniq("KA9"), "fastag_balance": 9999})).json()
    fastag = _get(env["a"], "/api/reconciliation/fastag")
    drift = next(d for d in fastag["balance_cache"] if d["vehicle_id"] == v["id"])
    assert drift["computed_net"] == 0.0
    assert drift["drift"] == 9999.0


def test_fastag_duplicate_detection(env):
    v = _run(env["a"].req("POST", "/api/vehicles", json={"vehicle_number": _uniq("KA8")})).json()
    body = {"vehicle_id": v["id"], "txn_type": "toll", "date": "2026-02-02",
            "amount": 250, "toll_plaza": "Plaza-X"}
    _run(env["a"].req("POST", "/api/fastag", json=body))
    _run(env["a"].req("POST", "/api/fastag", json=body))
    fastag = _get(env["a"], "/api/reconciliation/fastag")
    assert fastag["duplicate_count"] >= 1


# --- Payments -----------------------------------------------------------------

def test_payment_reconciliation(env):
    pay = _get(env["a"], f"/api/reconciliation/vehicle/{env['vid']}")["payments"]
    assert pay["accident_claim_total"] == 5000.0
    assert pay["accident_settlement_total"] == 3000.0
    assert pay["accident_outstanding"] == 2000.0
    # Repair is still "open", so nothing approved yet.
    assert pay["approved_repair_cost"] == 0.0


# --- Report / ledger / reconciliation agreement -------------------------------

def test_report_ledger_and_reconciliation_totals_agree(env):
    vid = env["vid"]
    recon_total = _get(env["a"], f"/api/reconciliation/vehicle/{vid}")["cost_breakdown"]["total"]
    ledger = _get(env["a"], "/api/expenses/ledger", vehicle_id=vid)
    ledger_total = ledger["total"]
    report = _get(env["a"], "/api/reports/expenses", vehicle_id=vid)
    # Report "Amount" column is the last cell in each row.
    report_total = round(sum((row[-1] or 0) for row in report["rows"]), 2)
    assert recon_total == ledger_total == report_total == EXPECTED["total"]


# --- Cross-tenant -------------------------------------------------------------

def test_reconciliation_is_org_scoped(env):
    # Org B is empty: its fastag reconciliation and a breakdown of A's vehicle
    # (which B cannot see) must both be empty/zero.
    b_fastag = _get(env["b"], "/api/reconciliation/fastag")
    assert b_fastag["transaction_count"] == 0
    assert b_fastag["balance_cache"] == []
    b_view = _get(env["b"], f"/api/reconciliation/vehicle/{env['vid']}")
    assert b_view["cost_breakdown"]["total"] == 0.0
    assert b_view["fuel"]["entries"] == 0
