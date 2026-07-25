"""
DI-03 — Reconciliation and derived balances.

Every total FleetFlow shows — a dashboard KPI, a report row, a vehicle's
cost-per-km — must be independently recomputable from the canonical source
records defined in DI-01. This module is the **single** place those
recomputations live, so a figure cannot be computed one way on the dashboard and
a different way in a report.

The canonical expense ledger is already ``helpers.gather_expenses``: it turns
every source record (fuel, repairs, tyres, FASTag tolls, trip toll/parking/misc,
accidents, services, greasing, manual expenses) into one row carrying its
``source`` and ``source_id``. Because a row is emitted per *source record*, the
same database record can never appear twice, and everything here derives from
that one ledger rather than re-summing the collections independently.

Derived/stored summaries (the vehicle ``fastag_balance``) are treated as
**caches**: this module recomputes them from the transactions and reports any
drift, rather than trusting the stored number.

All reads go through the tenant-scoped ``database.db``, so every function is
organisation-scoped by construction — a reconciliation run for org A can never
pull in org B's rows (proven by a cross-tenant test).

Honest scope
------------
Some economics the phase lists have **no source field in the current schema**
and are reported as ``None``/unavailable rather than invented: trip *revenue*,
driver *advances/settlements*, and FASTag *reversal/dispute* transaction types
do not exist yet (there is no revenue, advance or reversal field anywhere).
Where a number cannot be derived from a real record it is not fabricated.
"""
from collections import defaultdict

from database import db
from helpers import gather_expenses

# Ledger categories that make up each cost group. A group is the sum of its
# categories in the canonical ledger — no independent re-summing of collections.
COST_GROUPS = {
    "fuel": ("Fuel",),
    "fastag": ("Fastag",),
    "repairs": ("Repair",),
    "maintenance": ("Service", "Greasing"),
    "tyres": ("Tyres",),
    "accidents": ("Accident",),
    "trip_direct": ("Trip",),  # trip toll/parking/misc entered on the trip itself
}


def _round(x):
    return round(x or 0, 2)


def group_totals(rows):
    """Sum ledger rows by category. Returns {category: rounded total}."""
    by_cat = defaultdict(float)
    for r in rows:
        by_cat[r["category"]] += r.get("amount") or 0
    return {c: _round(a) for c, a in by_cat.items()}


async def vehicle_cost_breakdown(vehicle_id, start_date=None, end_date=None, include_test=False):
    """Canonical per-vehicle cost breakdown, grouped and reconciled.

    ``total`` is the sum of the ledger; the group figures partition it. A
    ``other`` bucket captures any category not mapped above (manual expense
    categories such as Insurance, Permits, Road Tax), so the parts always add up
    to the whole — a self-check the caller (and tests) can assert.
    """
    rows = await gather_expenses(
        vehicle_id=vehicle_id, start_date=start_date, end_date=end_date,
        include_test=include_test,
    )
    by_cat = group_totals(rows)
    grouped = {}
    claimed = set()
    for group, cats in COST_GROUPS.items():
        grouped[group] = _round(sum(by_cat.get(c, 0) for c in cats))
        claimed.update(cats)
    other = _round(sum(a for c, a in by_cat.items() if c not in claimed))
    total = _round(sum(by_cat.values()))

    # Distance from completed trips, for cost-per-km.
    trips = await db.trips.find(
        _vehicle_date_q(vehicle_id, start_date, end_date), {"_id": 0, "distance": 1}
    ).to_list(20000)
    distance = _round(sum(t.get("distance") or 0 for t in trips))

    return {
        "vehicle_id": vehicle_id,
        "groups": grouped,
        "other": other,
        "total": total,
        "distance_km": distance,
        "cost_per_km": _round(total / distance) if distance else None,
        # Self-check: the grouped parts + other must reconcile to total.
        "reconciles": abs(sum(grouped.values()) + other - total) < 0.01,
    }


def _vehicle_date_q(vehicle_id, start_date, end_date, date_field="date"):
    q = {}
    if vehicle_id:
        q["vehicle_id"] = vehicle_id
    if start_date:
        q[date_field] = {"$gte": start_date}
    if end_date:
        q.setdefault(date_field, {})
        q[date_field]["$lte"] = end_date
    return q


# --- Fuel ---------------------------------------------------------------------

async def fuel_reconciliation(vehicle_id):
    """Fuel totals + odometer continuity + mileage-variance detection.

    Rates and mileage are derived here from the raw quantity/amount/odometer, not
    read from any stored field, so a corrupted stored ``mileage`` cannot skew the
    reconciliation.
    """
    entries = await db.fuel_entries.find(
        {"vehicle_id": vehicle_id, "is_test_data": {"$ne": True}}, {"_id": 0}
    ).to_list(20000)
    entries.sort(key=lambda e: (e.get("odometer") or 0, e.get("date") or ""))

    total_qty = sum(e.get("quantity") or 0 for e in entries)
    total_amount = sum(e.get("amount") or 0 for e in entries)

    # Odometer continuity: an entry whose odometer is below a chronologically
    # earlier entry's is a break (backdated/mis-keyed reading).
    by_date = sorted(entries, key=lambda e: (e.get("date") or "", e.get("odometer") or 0))
    continuity_breaks = []
    prev_odo = None
    for e in by_date:
        odo = e.get("odometer")
        if odo is not None and prev_odo is not None and odo < prev_odo:
            continuity_breaks.append({"id": e.get("id"), "date": e.get("date"),
                                      "odometer": odo, "previous": prev_odo})
        if odo is not None:
            prev_odo = odo

    # Distance and mileage between consecutive fills (full-tank assumption noted
    # in RECONCILIATION_RULES.md).
    mileages = []
    for i in range(1, len(entries)):
        km = (entries[i].get("odometer") or 0) - (entries[i - 1].get("odometer") or 0)
        qty = entries[i].get("quantity") or 0
        if km > 0 and qty > 0:
            mileages.append(km / qty)
    avg_mileage = _round(sum(mileages) / len(mileages)) if mileages else None

    # Variance: a fill whose implied mileage is wildly off the median.
    variance_flags = []
    if len(mileages) >= 3:
        srt = sorted(mileages)
        median = srt[len(srt) // 2]
        for i, m in enumerate(mileages, start=1):
            if median > 0 and (m > median * 2 or m < median * 0.5):
                variance_flags.append({"id": entries[i].get("id"),
                                       "mileage": _round(m), "median": _round(median)})

    return {
        "vehicle_id": vehicle_id,
        "entries": len(entries),
        "total_quantity": _round(total_qty),
        "total_amount": _round(total_amount),
        "avg_rate": _round(total_amount / total_qty) if total_qty else None,
        "distance_km": _round((by_date[-1]["odometer"] - by_date[0]["odometer"]))
        if len(by_date) >= 2 and by_date[-1].get("odometer") and by_date[0].get("odometer") else 0,
        "avg_mileage": avg_mileage,
        "odometer_continuity_breaks": continuity_breaks,
        "mileage_variance_flags": variance_flags,
    }


# --- FASTag -------------------------------------------------------------------

def computed_fastag_net(transactions):
    """Net of a transaction set: recharges add, tolls subtract. The canonical
    definition of a vehicle's FASTag movement (matches fastag_simulation)."""
    total = 0.0
    for t in transactions:
        amt = t.get("amount") or 0
        total += amt if t.get("txn_type") == "recharge" else -amt
    return round(total, 2)


async def fastag_reconciliation(vehicle_id=None):
    """FASTag totals, duplicates, unmatched vehicles, and balance-cache drift.

    The vehicle ``fastag_balance`` is a **cache**: this recomputes the net from
    the transactions and reports the drift instead of trusting the stored value.
    """
    q = {"is_test_data": {"$ne": True}}
    if vehicle_id:
        q["vehicle_id"] = vehicle_id
    txns = await db.fastag_transactions.find(q, {"_id": 0}).to_list(50000)

    toll_total = sum(t.get("amount") or 0 for t in txns if t.get("txn_type") == "toll")
    recharge_total = sum(t.get("amount") or 0 for t in txns if t.get("txn_type") == "recharge")

    # Duplicates: identical (vehicle, date, amount, type, plaza) more than once.
    seen = defaultdict(int)
    for t in txns:
        key = (t.get("vehicle_id"), t.get("date"), t.get("amount"),
               t.get("txn_type"), t.get("toll_plaza"))
        seen[key] += 1
    duplicate_count = sum(n - 1 for n in seen.values() if n > 1)

    # Unmatched: a transaction whose vehicle no longer exists in this org.
    vehicle_ids = {v["id"] for v in await db.vehicles.find({}, {"_id": 0, "id": 1}).to_list(20000)}
    unmatched = [t.get("id") for t in txns if t.get("vehicle_id") not in vehicle_ids]

    # Trip-linked vs unlinked tolls: a toll on a date the vehicle also has a trip.
    trip_days = defaultdict(set)
    for tr in await db.trips.find({}, {"_id": 0, "vehicle_id": 1, "date": 1}).to_list(50000):
        trip_days[tr.get("vehicle_id")].add(tr.get("date"))
    linked = unlinked = 0
    for t in txns:
        if t.get("txn_type") != "toll":
            continue
        if t.get("date") in trip_days.get(t.get("vehicle_id"), set()):
            linked += 1
        else:
            unlinked += 1

    # Per-vehicle balance-cache drift (stored vs recomputed net).
    drifts = []
    per_vehicle = defaultdict(list)
    for t in txns:
        per_vehicle[t.get("vehicle_id")].append(t)
    vq = {"id": vehicle_id} if vehicle_id else {}
    vehicles = await db.vehicles.find(vq, {"_id": 0, "id": 1, "fastag_balance": 1, "vehicle_number": 1}).to_list(20000)
    for v in vehicles:
        net = computed_fastag_net(per_vehicle.get(v["id"], []))
        stored = v.get("fastag_balance") or 0
        drift = round(stored - net, 2)
        drifts.append({"vehicle_id": v["id"], "vehicle_number": v.get("vehicle_number"),
                       "stored_balance": _round(stored), "computed_net": net,
                       "drift": drift})

    return {
        "transaction_count": len(txns),
        "toll_total": _round(toll_total),
        "recharge_total": _round(recharge_total),
        "net": _round(recharge_total - toll_total),
        "duplicate_count": duplicate_count,
        "unmatched_vehicle_count": len(unmatched),
        "unmatched_transaction_ids": unmatched[:100],
        "trip_linked_tolls": linked,
        "unlinked_tolls": unlinked,
        # No reversal/dispute transaction type exists in the schema yet.
        "reversed_or_disputed": 0,
        "balance_cache": drifts,
    }


# --- Maintenance --------------------------------------------------------------

async def maintenance_reconciliation(vehicle_id=None):
    """Repair cost, downtime and repeat-repair patterns from source records."""
    rq = {"is_test_data": {"$ne": True}}
    if vehicle_id:
        rq["vehicle_id"] = vehicle_id
    repairs = await db.repairs.find(rq, {"_id": 0}).to_list(50000)
    downtimes = await db.downtimes.find(rq, {"_id": 0}).to_list(50000)

    repair_cost = sum(r.get("cost") or 0 for r in repairs)
    downtime_days = sum(d.get("days") or 0 for d in downtimes)

    by_status = defaultdict(int)
    for r in repairs:
        by_status[r.get("status") or "unknown"] += 1

    # Repeat repairs: same vehicle + category seen 3+ times.
    combo = defaultdict(int)
    for r in repairs:
        combo[(r.get("vehicle_id"), r.get("ticket_category") or r.get("repair_type"))] += 1
    repeat = [{"vehicle_id": vid, "category": cat, "count": n}
              for (vid, cat), n in combo.items() if n >= 3]

    return {
        "repair_count": len(repairs),
        "repair_cost": _round(repair_cost),
        "downtime_days": _round(downtime_days),
        "by_status": dict(by_status),
        "repeat_repairs": repeat,
    }


# --- Payments -----------------------------------------------------------------

async def payment_reconciliation(vehicle_id=None):
    """Money-state reconciliation for the records that actually carry it.

    FleetFlow has no standalone payment ledger (DI-01). The realised money states
    are: accident claim vs settlement (outstanding = claim − settlement), and
    approved repair cost. Both are derived from source records here.
    """
    aq = {"is_test_data": {"$ne": True}}
    if vehicle_id:
        aq["vehicle_id"] = vehicle_id
    accidents = await db.accidents.find(aq, {"_id": 0}).to_list(50000)
    claim_total = sum(a.get("claim_amount") or 0 for a in accidents)
    settlement_total = sum(a.get("settlement_amount") or 0 for a in accidents)

    repairs = await db.repairs.find(aq, {"_id": 0}).to_list(50000)
    approved_states = {"approved", "sent_for_repair", "in_repair", "repaired", "closed"}
    approved_repair_cost = sum(
        r.get("cost") or 0 for r in repairs if r.get("status") in approved_states
    )

    return {
        "accident_claim_total": _round(claim_total),
        "accident_settlement_total": _round(settlement_total),
        "accident_outstanding": _round(claim_total - settlement_total),
        "approved_repair_cost": _round(approved_repair_cost),
    }


# --- Trip economics -----------------------------------------------------------

async def trip_economics(trip_id):
    """Per-trip economics from the trip's own fields.

    ``revenue`` and driver ``advances/settlements`` have no schema field yet and
    are reported as ``None`` rather than invented; contribution is therefore the
    negative of the direct trip expenses until a revenue field exists.
    """
    trip = await db.trips.find_one({"id": trip_id}, {"_id": 0})
    if not trip:
        return None
    direct = (trip.get("toll_expense") or 0) + (trip.get("parking_expense") or 0) + (trip.get("misc_expense") or 0)
    revenue = trip.get("revenue")  # not in the current schema → None
    return {
        "trip_id": trip_id,
        "distance_km": _round(trip.get("distance") or 0),
        "direct_expenses": _round(direct),
        "revenue": revenue,
        "driver_advance": trip.get("driver_advance"),  # not in schema → None
        "contribution": _round((revenue or 0) - direct) if revenue is not None else _round(-direct),
        "outstanding": None,  # requires revenue/advance fields (future work)
    }
