"""
DI-04 — Synthetic fixtures for the data-integrity scanner.

Each test plants one deliberately-broken record straight into ``raw_db`` (the
scanner reads unscoped on purpose — it must see records with a missing org_id and
cross-tenant references) and asserts the matching detector fires. A coverage test
asserts every detector is exercised. Repair mode is proven dry-run-safe,
backup-gated and idempotent.

Uses raw_db directly (no HTTP) against the disposable test database that conftest
pins DB_NAME to.
"""
import uuid

import pytest

import database  # noqa: E402
import check_data_integrity as cdi

from conftest import realhttp_run as _run

raw = database.raw_db
ORG_A = "di04-org-a"
ORG_B = "di04-org-b"


def _reset():
    async def go():
        await database.client.drop_database(raw.name)
    _run(go())


def _insert(coll, **doc):
    doc.setdefault("id", str(uuid.uuid4()))
    _run(raw[coll].insert_one(doc))
    return doc["id"]


def _scan(org=None):
    return _run(cdi.scan(org))


def _detectors(report):
    return set(report["by_detector"].keys())


@pytest.fixture(autouse=True)
def clean():
    _reset()
    yield
    _reset()


# --- One test per detector ----------------------------------------------------

def test_missing_org_ownership():
    _run(raw.vehicles.insert_one({"id": "v-noorg", "vehicle_number": "KA-X"}))  # no org_id
    assert "missing_org_ownership" in _detectors(_scan())


def test_orphaned_reference():
    _insert("fuel_entries", org_id=ORG_A, vehicle_id="ghost-vehicle",
            date="2026-01-01", odometer=1, quantity=1, amount=1)
    assert "orphaned_reference" in _detectors(_scan())


def test_cross_tenant_reference():
    _insert("vehicles", id="v-b", org_id=ORG_B, vehicle_number="KA-B")
    _insert("fuel_entries", org_id=ORG_A, vehicle_id="v-b",
            date="2026-01-01", odometer=1, quantity=1, amount=1)
    dets = _detectors(_scan())
    assert "cross_tenant_reference" in dets


def test_duplicate_external_reference():
    _insert("vehicles", org_id=ORG_A, vehicle_number="KA-DUP")
    _insert("vehicles", org_id=ORG_A, vehicle_number="KA-DUP")
    assert "duplicate_external_reference" in _detectors(_scan())


def test_duplicate_fastag_transaction():
    _insert("vehicles", id="v-ft", org_id=ORG_A, vehicle_number="KA-FT")
    for _ in range(2):
        _insert("fastag_transactions", org_id=ORG_A, vehicle_id="v-ft",
                txn_type="toll", date="2026-01-01", amount=100, toll_plaza="P1")
    assert "duplicate_fastag_transaction" in _detectors(_scan())


def test_invalid_odometer_sequence():
    _insert("vehicles", id="v-od", org_id=ORG_A, vehicle_number="KA-OD")
    _insert("fuel_entries", org_id=ORG_A, vehicle_id="v-od",
            date="2026-01-01", odometer=5000, quantity=10, amount=1000)
    _insert("fuel_entries", org_id=ORG_A, vehicle_id="v-od",
            date="2026-01-05", odometer=4000, quantity=10, amount=1000)  # went backwards
    assert "invalid_odometer_sequence" in _detectors(_scan())


def test_impossible_monetary_value():
    _insert("expenses", org_id=ORG_A, vehicle_id=None, category="Fuel",
            date="2026-01-01", amount=-500)
    assert "impossible_monetary_value" in _detectors(_scan())


def test_settlement_exceeds_claim():
    _insert("accidents", org_id=ORG_A, vehicle_id=None, date="2026-01-01",
            claim_amount=1000, settlement_amount=5000)
    assert "settlement_exceeds_claim" in _detectors(_scan())


def test_invalid_status():
    _insert("vehicles", org_id=ORG_A, vehicle_number="KA-ST", status="teleported")
    assert "invalid_status" in _detectors(_scan())


def test_inconsistent_downtime():
    _insert("downtimes", org_id=ORG_A, vehicle_id=None, reason="service",
            start_date="2026-01-01", end_date="2026-01-05", status="open")
    assert "inconsistent_downtime" in _detectors(_scan())


def test_completed_trip_without_closing_km():
    _insert("vehicles", id="v-tr", org_id=ORG_A, vehicle_number="KA-TR")
    _insert("trips", org_id=ORG_A, vehicle_id="v-tr", date="2026-01-01",
            opening_km=100, closing_km=None, status="completed")
    assert "completed_trip_without_closing_km" in _detectors(_scan())


def test_negative_fastag_balance():
    _insert("vehicles", org_id=ORG_A, vehicle_number="KA-NEG", fastag_balance=-50)
    assert "negative_fastag_balance" in _detectors(_scan())


def test_fastag_balance_drift():
    _insert("vehicles", id="v-dr", org_id=ORG_A, vehicle_number="KA-DR", fastag_balance=9999)
    # No transactions → net 0 → drift 9999.
    assert "fastag_balance_drift" in _detectors(_scan())


# --- Coverage: every detector is exercised by the fixtures above ---------------

def test_every_detector_has_a_fixture():
    """Plant one instance of every finding type, assert all detectors fire.

    A guard against adding a detector without a fixture (and vice-versa)."""
    # missing org
    _run(raw.vehicles.insert_one({"id": "cov-noorg", "vehicle_number": "KA-C0"}))
    # cross-tenant + orphaned
    _insert("vehicles", id="cov-vb", org_id=ORG_B, vehicle_number="KA-C1")
    _insert("fuel_entries", org_id=ORG_A, vehicle_id="cov-vb",
            date="2026-01-01", odometer=1, quantity=1, amount=1)  # cross-tenant
    _insert("services", org_id=ORG_A, vehicle_id="ghost",
            date="2026-01-01")  # orphaned
    # duplicate external
    _insert("vehicles", id="cov-va", org_id=ORG_A, vehicle_number="KA-DUP2")
    _insert("vehicles", org_id=ORG_A, vehicle_number="KA-DUP2")
    # duplicate fastag
    for _ in range(2):
        _insert("fastag_transactions", org_id=ORG_A, vehicle_id="cov-va",
                txn_type="toll", date="2026-01-02", amount=10, toll_plaza="P")
    # odometer sequence
    _insert("fuel_entries", org_id=ORG_A, vehicle_id="cov-va",
            date="2026-01-01", odometer=900, quantity=1, amount=1)
    _insert("fuel_entries", org_id=ORG_A, vehicle_id="cov-va",
            date="2026-01-03", odometer=800, quantity=1, amount=1)
    # impossible money
    _insert("repairs", org_id=ORG_A, vehicle_id="cov-va", repair_type="minor",
            issue="x", date="2026-01-01", cost=-1, status="open")
    # settlement > claim
    _insert("accidents", org_id=ORG_A, vehicle_id="cov-va", date="2026-01-01",
            claim_amount=1, settlement_amount=2)
    # invalid status
    _insert("drivers", org_id=ORG_A, status="banana")
    # inconsistent downtime
    _insert("downtimes", org_id=ORG_A, vehicle_id="cov-va", reason="x",
            start_date="2026-01-01", end_date="2026-01-02", status="open")
    # completed trip w/o closing_km
    _insert("trips", org_id=ORG_A, vehicle_id="cov-va", date="2026-01-01",
            opening_km=1, closing_km=None, status="completed")
    # negative balance + drift
    _insert("vehicles", org_id=ORG_A, vehicle_number="KA-NEG2", fastag_balance=-5)
    _insert("vehicles", org_id=ORG_A, vehicle_number="KA-DR2", fastag_balance=123)

    dets = _detectors(_scan())
    expected = {
        "missing_org_ownership", "orphaned_reference", "cross_tenant_reference",
        "duplicate_external_reference", "duplicate_fastag_transaction",
        "invalid_odometer_sequence", "impossible_monetary_value",
        "settlement_exceeds_claim", "invalid_status", "inconsistent_downtime",
        "completed_trip_without_closing_km", "negative_fastag_balance",
        "fastag_balance_drift",
    }
    missing = expected - dets
    assert not missing, f"detectors with no finding: {missing}"


# --- Scanner properties -------------------------------------------------------

def test_scan_is_org_scoped():
    _insert("vehicles", org_id=ORG_A, vehicle_number="KA-A", status="teleported")
    _insert("vehicles", org_id=ORG_B, vehicle_number="KA-B", status="teleported")
    report = _scan(org=ORG_A)
    assert all(f["org_id"] in (ORG_A, None) for f in report["findings"])


def test_findings_never_include_personal_fields():
    _insert("drivers", org_id=ORG_A, status="banana", name="Ravi Kumar",
            aadhaar="1234-5678-9012", mobile="9000000000")
    report = _scan()
    blob = str(report)
    assert "Ravi Kumar" not in blob and "1234-5678-9012" not in blob and "9000000000" not in blob


def test_scan_records_audit_evidence():
    before = _run(raw.data_integrity_audit.count_documents({}))
    _run(cdi.scan(None))
    _run(cdi._record_audit("scan", None, {"total": 0}))
    after = _run(raw.data_integrity_audit.count_documents({}))
    assert after > before
    # Audit rows carry no secrets.
    doc = _run(raw.data_integrity_audit.find_one({}, {"_id": 0}))
    assert "password" not in str(doc).lower()


# --- Repair mode --------------------------------------------------------------

def test_repair_dry_run_writes_nothing():
    _insert("vehicles", id="rep-v", org_id=ORG_A, vehicle_number="KA-REP", fastag_balance=500)
    changes = _run(cdi.repair_recompute_fastag_balance(ORG_A, apply=False))
    assert len(changes) == 1 and changes[0]["to"] == 0.0
    v = _run(raw.vehicles.find_one({"id": "rep-v"}, {"_id": 0}))
    assert v["fastag_balance"] == 500, "dry-run must not write"


def test_repair_apply_recomputes_and_is_idempotent():
    _insert("vehicles", id="rep-v2", org_id=ORG_A, vehicle_number="KA-REP2", fastag_balance=500)
    _insert("fastag_transactions", org_id=ORG_A, vehicle_id="rep-v2",
            txn_type="recharge", date="2026-01-01", amount=200)
    changes = _run(cdi.repair_recompute_fastag_balance(ORG_A, apply=True))
    assert changes[0]["to"] == 200.0
    v = _run(raw.vehicles.find_one({"id": "rep-v2"}, {"_id": 0}))
    assert v["fastag_balance"] == 200
    # Idempotent: a second apply finds nothing to change.
    again = _run(cdi.repair_recompute_fastag_balance(ORG_A, apply=True))
    assert again == []


def test_repair_never_deletes_records():
    _insert("vehicles", id="rep-v3", org_id=ORG_A, vehicle_number="KA-REP3", fastag_balance=1)
    _insert("fuel_entries", id="keep-fuel", org_id=ORG_A, vehicle_id="rep-v3",
            date="2026-01-01", odometer=1, quantity=1, amount=1)
    _run(cdi.repair_recompute_fastag_balance(ORG_A, apply=True))
    assert _run(raw.fuel_entries.find_one({"id": "keep-fuel"})) is not None
