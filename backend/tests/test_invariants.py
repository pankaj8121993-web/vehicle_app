"""
DI-01 — Unit tests for the pure canonical-record invariants.

These exercise ``invariants`` in isolation (no DB, no HTTP), which is where the
money/quantity/odometer/ordering rules actually live. The real-HTTP wiring is
proven separately in ``test_di01_enforcement``.
"""
import math

import pytest
from fastapi import HTTPException

import invariants


# --- money --------------------------------------------------------------------

def test_money_quantises_to_two_places_half_up():
    assert invariants.money(100.005) == 100.01
    assert invariants.money(100.004) == 100.00
    assert invariants.money("2500.1") == 2500.10


def test_money_float_noise_is_cleaned():
    # 0.1 + 0.2 == 0.30000000000000004 in binary float; the ledger must not store
    # that sub-paisa noise.
    assert invariants.money(0.1 + 0.2) == 0.30


def test_money_none_allowed_by_default():
    assert invariants.money(None) is None


def test_money_none_rejected_when_required():
    with pytest.raises(HTTPException) as e:
        invariants.money(None, allow_none=False)
    assert e.value.status_code == 400


@pytest.mark.parametrize("bad", [-1, -0.01, -1000])
def test_money_rejects_negative(bad):
    with pytest.raises(HTTPException) as e:
        invariants.money(bad, field="cost")
    assert e.value.status_code == 400
    assert "cost" in e.value.detail


def test_money_allows_negative_for_documented_reversal():
    assert invariants.money(-50, allow_negative=True) == -50.00


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_money_rejects_non_finite(bad):
    with pytest.raises(HTTPException) as e:
        invariants.money(bad)
    assert e.value.status_code == 400


def test_money_rejects_bool():
    with pytest.raises(HTTPException):
        invariants.money(True)


def test_money_rejects_non_numeric_string():
    with pytest.raises(HTTPException):
        invariants.money("free")


def test_money_rejects_out_of_range():
    with pytest.raises(HTTPException):
        invariants.money(1e11)


# --- quantity -----------------------------------------------------------------

@pytest.mark.parametrize("bad", [0, -1, -0.0001])
def test_quantity_rejects_zero_and_negative(bad):
    with pytest.raises(HTTPException) as e:
        invariants.quantity(bad)
    assert e.value.status_code == 400


def test_quantity_accepts_positive():
    assert invariants.quantity(42.5) == 42.5


def test_quantity_rejects_non_finite():
    with pytest.raises(HTTPException):
        invariants.quantity(math.inf)


def test_quantity_required_by_default():
    with pytest.raises(HTTPException):
        invariants.quantity(None)


# --- odometer -----------------------------------------------------------------

def test_odometer_accepts_zero_and_positive():
    assert invariants.odometer(0) == 0
    assert invariants.odometer(123456) == 123456


def test_odometer_rejects_negative():
    with pytest.raises(HTTPException):
        invariants.odometer(-1)


def test_odometer_rejects_non_finite():
    with pytest.raises(HTTPException):
        invariants.odometer(math.nan)


def test_odometer_none_allowed():
    assert invariants.odometer(None) is None


# --- ordering -----------------------------------------------------------------

def test_require_order_passes_when_upper_ge_lower():
    invariants.require_order(100, 200, lower_field="a", upper_field="b")
    invariants.require_order(100, 100, lower_field="a", upper_field="b")


def test_require_order_rejects_upper_below_lower():
    with pytest.raises(HTTPException) as e:
        invariants.require_order(200, 100, lower_field="opening_km", upper_field="closing_km")
    assert e.value.status_code == 400
    assert "closing_km" in e.value.detail


def test_require_order_none_side_passes():
    invariants.require_order(None, 100, lower_field="a", upper_field="b")
    invariants.require_order(100, None, lower_field="a", upper_field="b")


def test_require_date_order_rejects_end_before_start():
    with pytest.raises(HTTPException):
        invariants.require_date_order("2026-05-10", "2026-05-01")


def test_require_date_order_allows_equal_and_after():
    invariants.require_date_order("2026-05-01", "2026-05-01")
    invariants.require_date_order("2026-05-01", "2026-05-10")


# --- enforce_record_invariants (integration of the above per collection) ------

def test_enforce_fuel_quantises_amount_and_checks_quantity():
    doc = {"amount": 1000.005, "quantity": 10, "odometer": 5000}
    invariants.enforce_record_invariants("fuel_entries", doc)
    assert doc["amount"] == 1000.01


def test_enforce_fuel_rejects_zero_quantity():
    with pytest.raises(HTTPException):
        invariants.enforce_record_invariants(
            "fuel_entries", {"amount": 1000, "quantity": 0, "odometer": 1})


def test_enforce_trip_rejects_closing_below_opening():
    with pytest.raises(HTTPException) as e:
        invariants.enforce_record_invariants(
            "trips", {"opening_km": 500, "closing_km": 400})
    assert e.value.status_code == 400


def test_enforce_trip_allows_open_trip_without_closing():
    invariants.enforce_record_invariants("trips", {"opening_km": 500})


def test_enforce_repair_rejects_negative_cost():
    with pytest.raises(HTTPException):
        invariants.enforce_record_invariants("repairs", {"cost": -100})


def test_enforce_accident_rejects_settlement_over_claim():
    with pytest.raises(HTTPException) as e:
        invariants.enforce_record_invariants(
            "accidents", {"claim_amount": 1000, "settlement_amount": 1500})
    assert e.value.status_code == 400


def test_enforce_accident_allows_settlement_within_claim():
    doc = {"claim_amount": 1000, "settlement_amount": 800, "repair_cost": 500}
    invariants.enforce_record_invariants("accidents", doc)
    assert doc["settlement_amount"] == 800.00


def test_enforce_is_idempotent():
    doc = {"amount": 100.1, "quantity": 5, "odometer": 10}
    invariants.enforce_record_invariants("fuel_entries", doc)
    once = dict(doc)
    invariants.enforce_record_invariants("fuel_entries", doc)
    assert doc == once


def test_enforce_downtime_rejects_end_before_start():
    with pytest.raises(HTTPException):
        invariants.enforce_record_invariants(
            "downtimes", {"start_date": "2026-05-10", "end_date": "2026-05-01"})
