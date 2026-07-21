"""
DI-01 — Canonical record invariants (pure, DB-free).

Every FleetFlow business event is a document written through a create/update
endpoint. Before DI-01 those endpoints accepted whatever the Pydantic model let
through: a fuel entry with ``quantity: 0``, a repair with ``cost: -5000``, a
trip whose ``closing_km`` was below its ``opening_km`` on creation, a monetary
amount of ``1e309`` (``inf``) — all stored verbatim and silently corrupting
every downstream total, mileage figure and cost-per-km.

This module is the single place those numeric and ordering invariants live. It
is deliberately free of any database or FastAPI-request coupling (beyond raising
``HTTPException`` for a uniform 400) so the rules are unit-testable in isolation
and can be reused by the create path, the generic update path and the DI-04
integrity scanner alike.

Design rules
------------
* **Money is decimal.** Amounts are validated and quantised through
  :class:`decimal.Decimal` with ``ROUND_HALF_UP`` to two places, so ``0.1 + 0.2``
  round-trips as ``0.30`` and a client cannot store sub-paisa noise that makes a
  reconciliation total drift. The quantised value is returned as ``float`` only
  at the boundary, because the store (MongoDB) has no decimal128 in this schema;
  the *validation* is exact even though the *storage* is not.
* **Reject, don't coerce silently.** A negative amount, a non-finite number, a
  zero/negative quantity or an out-of-order odometer is a 400 that names the
  field — never a value that is quietly clamped, because a clamp hides the bad
  input from the person who submitted it.
* **Reversals are explicit.** Negative money is refused everywhere *except* where
  the caller passes ``allow_negative=True`` for a documented reversal/credit
  line. There is no implicit negative anywhere in the current schema, so the
  default is fail-closed.
* **Bounds catch the impossible, not the merely large.** The ceilings here are
  loose (100 crore per line, 100 million km) — they exist to reject ``inf``,
  fat-finger ``1e12`` and overflow, not to second-guess a legitimately large
  fleet. Business ceilings (per-role approval limits) are a separate concern.
"""
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import math

from fastapi import HTTPException


# --- Bounds -------------------------------------------------------------------

# A single monetary line above this is treated as impossible input rather than a
# real transaction (₹100 crore). Catches inf/overflow/fat-finger, not big fleets.
MONEY_MAX = Decimal("10000000000")   # 1e10

# Odometer / kilometre readings above this are impossible (100 million km).
ODO_MAX = 100_000_000

# A single fuel fill above this many litres is impossible input.
QTY_MAX = 100_000

_CENTS = Decimal("0.01")


# --- Money --------------------------------------------------------------------

def money(value, *, field="amount", allow_none=True, allow_negative=False):
    """Validate and quantise a monetary value; return a 2dp ``float`` or ``None``.

    Raises HTTP 400 (naming ``field``) if the value is non-numeric, non-finite,
    negative (unless ``allow_negative``), or beyond :data:`MONEY_MAX`. ``None`` is
    passed through when ``allow_none`` — an optional amount that was simply not
    supplied is not an error.
    """
    if value is None:
        if allow_none:
            return None
        raise HTTPException(status_code=400, detail=f"{field} is required")
    # Reject bool explicitly: bool is an int subclass, and True/False as an
    # amount is always a mistake.
    if isinstance(value, bool):
        raise HTTPException(status_code=400, detail=f"{field} must be a number")
    if isinstance(value, float) and not math.isfinite(value):
        raise HTTPException(status_code=400, detail=f"{field} must be a finite number")
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"{field} must be a number")
    if not dec.is_finite():
        raise HTTPException(status_code=400, detail=f"{field} must be a finite number")
    if not allow_negative and dec < 0:
        raise HTTPException(
            status_code=400,
            detail=f"{field} cannot be negative (use a documented reversal instead)",
        )
    if abs(dec) > MONEY_MAX:
        raise HTTPException(status_code=400, detail=f"{field} is out of range")
    quantised = dec.quantize(_CENTS, rounding=ROUND_HALF_UP)
    return float(quantised)


def quantity(value, *, field="quantity", allow_none=False):
    """Validate a physical quantity (litres). Must be finite and > 0.

    Zero is rejected: a fill of zero litres is not a real fuel event and would
    make a mileage denominator zero.
    """
    if value is None:
        if allow_none:
            return None
        raise HTTPException(status_code=400, detail=f"{field} is required")
    if isinstance(value, bool):
        raise HTTPException(status_code=400, detail=f"{field} must be a number")
    if isinstance(value, float) and not math.isfinite(value):
        raise HTTPException(status_code=400, detail=f"{field} must be a finite number")
    try:
        num = float(value)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"{field} must be a number")
    if not math.isfinite(num):
        raise HTTPException(status_code=400, detail=f"{field} must be a finite number")
    if num <= 0:
        raise HTTPException(status_code=400, detail=f"{field} must be greater than zero")
    if num > QTY_MAX:
        raise HTTPException(status_code=400, detail=f"{field} is out of range")
    return num


def odometer(value, *, field="odometer", allow_none=True):
    """Validate an odometer / kilometre reading. Must be finite and >= 0."""
    if value is None:
        if allow_none:
            return None
        raise HTTPException(status_code=400, detail=f"{field} is required")
    if isinstance(value, bool):
        raise HTTPException(status_code=400, detail=f"{field} must be a number")
    if isinstance(value, float) and not math.isfinite(value):
        raise HTTPException(status_code=400, detail=f"{field} must be a finite number")
    try:
        num = float(value)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"{field} must be a number")
    if not math.isfinite(num):
        raise HTTPException(status_code=400, detail=f"{field} must be a finite number")
    if num < 0:
        raise HTTPException(status_code=400, detail=f"{field} cannot be negative")
    if num > ODO_MAX:
        raise HTTPException(status_code=400, detail=f"{field} is out of range")
    return num


def require_order(lower, upper, *, lower_field, upper_field):
    """Require ``upper >= lower`` when both are present. Raises HTTP 400 otherwise.

    Used for closing_km vs opening_km and settlement vs claim. Either side
    ``None`` means the constraint does not yet apply (an open trip has no closing
    reading), so it passes.
    """
    if lower is None or upper is None:
        return
    try:
        lo, up = float(lower), float(upper)
    except (ValueError, TypeError):
        return  # type validation happens in the dedicated helpers above
    if up < lo:
        raise HTTPException(
            status_code=400,
            detail=f"{upper_field} ({upper}) cannot be less than {lower_field} ({lower})",
        )


def require_date_order(start, end, *, start_field="start_date", end_field="end_date"):
    """Require ``end >= start`` for ISO date/datetime strings when both present.

    Compares lexically, which is correct for zero-padded ISO-8601. A malformed
    value is left for the field-level validators rather than guessed at.
    """
    if not start or not end:
        return
    if str(end) < str(start):
        raise HTTPException(
            status_code=400,
            detail=f"{end_field} cannot be before {start_field}",
        )


# --- Per-collection field policy ----------------------------------------------
#
# Which fields on each canonical record are monetary. Amounts here are validated
# non-negative and quantised on both create and generic update. fastag balance
# and vehicle odometer are deliberately absent: the balance is a running figure
# that DI-03 recomputes from transactions, and the master odometer is maintained
# by the odometer-forwarding logic, not entered as money.

MONEY_FIELDS = {
    "vehicles": ("purchase_price", "sale_value"),
    "trips": ("toll_expense", "parking_expense", "misc_expense"),
    "fuel_entries": ("amount",),
    "services": ("cost",),
    "repairs": ("cost",),
    "greasings": ("cost",),
    "tyres": ("cost",),
    "tyre_events": ("cost",),
    "accidents": ("repair_cost", "claim_amount", "settlement_amount"),
    "fastag_transactions": ("amount",),
    "expenses": ("amount",),
}

# Odometer-like fields per collection (validated >= 0, finite, bounded).
ODO_FIELDS = {
    "trips": ("opening_km", "closing_km"),
    "fuel_entries": ("odometer",),
    "services": ("odometer",),
    "greasings": ("odometer",),
    "tyres": ("installation_km", "removal_km"),
    "tyre_events": ("odometer",),
}


def normalize_money_fields(collection, doc):
    """Validate + quantise every known monetary field present in ``doc`` in place.

    Only touches keys that are actually present, so it is safe on a partial
    generic-update body as well as a full create document. Returns ``doc``.
    """
    for field in MONEY_FIELDS.get(collection, ()):
        if field in doc and doc[field] is not None:
            doc[field] = money(doc[field], field=field)
    return doc


def normalize_odometer_fields(collection, doc):
    """Validate every known odometer field present in ``doc`` in place."""
    for field in ODO_FIELDS.get(collection, ()):
        if field in doc and doc[field] is not None:
            doc[field] = odometer(doc[field], field=field)
    return doc


def enforce_record_invariants(collection, doc):
    """Apply every pure invariant for ``collection`` to ``doc`` in place.

    Money quantisation, odometer bounds, quantity checks and the cross-field
    ordering rules. Pure and idempotent — running it twice yields the same doc.
    Raises HTTP 400 on the first violation. Returns ``doc``.
    """
    normalize_money_fields(collection, doc)
    normalize_odometer_fields(collection, doc)

    if collection == "fuel_entries" and "quantity" in doc:
        doc["quantity"] = quantity(doc["quantity"], field="quantity")

    if collection == "trips":
        require_order(
            doc.get("opening_km"), doc.get("closing_km"),
            lower_field="opening_km", upper_field="closing_km",
        )

    if collection == "downtimes":
        require_date_order(doc.get("start_date"), doc.get("end_date"))

    if collection == "accidents":
        # A settlement cannot exceed the amount claimed — the one "paid cannot
        # exceed eligible" rule the current schema actually expresses.
        _enforce_settlement_within_claim(doc)

    return doc


def _enforce_settlement_within_claim(doc):
    claim = doc.get("claim_amount")
    settlement = doc.get("settlement_amount")
    if claim is None or settlement is None:
        return
    try:
        if float(settlement) > float(claim):
            raise HTTPException(
                status_code=400,
                detail="settlement_amount cannot exceed claim_amount",
            )
    except (ValueError, TypeError):
        return
