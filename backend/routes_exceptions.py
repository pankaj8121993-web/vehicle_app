"""
OPS-05 — Operational exceptions, alerts and closure.

Makes pending operational work visible without a new analytics platform. Every
exception is *derived from canonical source data* through the tenant-scoped db
(no parallel financial calculation, no duplicated alert store), so an item
disappears the moment its source condition clears — a resolved item leaves the
list on its own.

Each item carries a **stable identifier** (`category:source_id`) so the same
underlying record never produces two alerts and an acknowledgement can pin to it.
Acknowledgement records who/when in `exception_acks` but never removes the item
while the condition persists — it flags it, so a real problem can't be hidden
permanently.

Ageing thresholds are query parameters with documented defaults.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, Query

from auth import require_module, require_permission, record_security_event
from database import db

router = APIRouter(tags=["exceptions"])

# Documented default ageing thresholds (all overridable via query params).
DEFAULT_TRIP_OVERDUE_DAYS = 2
DEFAULT_REPAIR_OVERDUE_DAYS = 7
DEFAULT_DOC_HORIZON_DAYS = 30


def _today():
    return datetime.now(timezone.utc).date()


def _age_days(date_str):
    if not date_str:
        return None
    try:
        return (_today() - datetime.fromisoformat(str(date_str)[:10]).date()).days
    except (ValueError, TypeError):
        return None


def _days_until(date_str):
    if not date_str:
        return None
    try:
        return (datetime.fromisoformat(str(date_str)[:10]).date() - _today()).days
    except (ValueError, TypeError):
        return None


def _item(category, entity_type, entity_id, label, *, severity="warning", **detail):
    """Build one exception with a stable id. `entity_id` is the source record id."""
    return {
        "id": f"{category}:{entity_id}",
        "category": category,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "label": label,
        "severity": severity,
        "detail": detail,
    }


async def _vehicle_number_map():
    return {v["id"]: v.get("vehicle_number", "")
            for v in await db.vehicles.find({}, {"_id": 0, "id": 1, "vehicle_number": 1}).to_list(5000)}


async def _build_exceptions(trip_overdue_days, repair_overdue_days, doc_horizon_days):
    out = []
    vmap = await _vehicle_number_map()
    nt = {"is_test_data": {"$ne": True}}

    # --- Trips ---------------------------------------------------------------
    for t in await db.trips.find({**nt, "status": {"$in": ["planned", "assigned"]}}, {"_id": 0}).to_list(20000):
        out.append(_item("trips_awaiting_dispatch", "trip", t["id"],
                         f"Trip {t.get('origin', '')}→{t.get('destination', '')} awaiting dispatch",
                         severity="info", status=t.get("status")))
    for t in await db.trips.find({**nt, "status": "ongoing"}, {"_id": 0}).to_list(20000):
        age = _age_days(t.get("date"))
        if age is not None and age >= trip_overdue_days:
            out.append(_item("trips_overdue_completion", "trip", t["id"],
                             f"Trip ongoing for {age} days", severity="danger", age_days=age))
    for t in await db.trips.find({**nt, "status": {"$in": ["completed", "settlement_pending"]}}, {"_id": 0}).to_list(20000):
        out.append(_item("trips_awaiting_settlement", "trip", t["id"],
                         "Completed trip awaiting settlement/closure", severity="info"))
    for t in await db.trips.find({**nt, "status": "completed", "closing_km": None}, {"_id": 0}).to_list(20000):
        out.append(_item("missing_closing_odometer", "trip", t["id"],
                         "Completed trip has no closing odometer", severity="warning"))

    # --- Expenses ------------------------------------------------------------
    for e in await db.expenses.find({**nt, "approval_status": "submitted"}, {"_id": 0}).to_list(20000):
        out.append(_item("unapproved_expenses", "expense", e["id"],
                         f"Expense ₹{e.get('amount', 0)} awaiting approval", severity="warning",
                         amount=e.get("amount")))
    for e in await db.expenses.find({**nt, "approval_status": "approved"}, {"_id": 0}).to_list(20000):
        outstanding = round((e.get("approved_amount") or 0) - (e.get("paid_amount") or 0), 2)
        if outstanding > 0:
            out.append(_item("unpaid_approved_expenses", "expense", e["id"],
                             f"Approved expense with ₹{outstanding} outstanding",
                             severity="warning", outstanding=outstanding))

    # --- Repairs / maintenance / downtime ------------------------------------
    for r in await db.repairs.find({**nt, "status": {"$in": ["open", "under_review"]}}, {"_id": 0}).to_list(20000):
        out.append(_item("repairs_awaiting_approval", "repair", r["id"],
                         f"Repair {r.get('ticket_number', '')} awaiting approval", severity="warning"))
    active_repair = {"sent_for_repair", "in_repair"}
    for r in await db.repairs.find({**nt, "status": {"$in": list(active_repair)}}, {"_id": 0}).to_list(20000):
        age = _age_days(r.get("date"))
        if age is not None and age >= repair_overdue_days:
            out.append(_item("repairs_overdue_completion", "repair", r["id"],
                             f"Repair in progress for {age} days", severity="danger", age_days=age))
    for d in await db.downtimes.find({**nt, "status": "open"}, {"_id": 0}).to_list(20000):
        out.append(_item("open_downtime", "downtime", d["id"],
                         f"Open downtime on {vmap.get(d.get('vehicle_id'), '')}", severity="warning"))
    for v in await db.vehicles.find({**nt, "status": "maintenance"}, {"_id": 0}).to_list(20000):
        out.append(_item("vehicles_under_repair", "vehicle", v["id"],
                         f"{v.get('vehicle_number', '')} under maintenance", severity="info"))

    # --- Compliance ----------------------------------------------------------
    docs = await db.documents.find(
        {**nt, "expiry_date": {"$ne": None}, "is_current": {"$ne": False}}, {"_id": 0}).to_list(20000)
    for d in docs:
        du = _days_until(d.get("expiry_date"))
        if du is None:
            continue
        if du < 0:
            out.append(_item("expired_documents", "document", d["id"],
                             f"{d.get('doc_type')} expired {(-du)} days ago", severity="danger",
                             doc_type=d.get("doc_type")))
        elif du <= doc_horizon_days:
            out.append(_item("documents_expiring_soon", "document", d["id"],
                             f"{d.get('doc_type')} expires in {du} days", severity="warning",
                             doc_type=d.get("doc_type")))
    drivers = await db.drivers.find(
        {**nt, "status": {"$nin": ["resigned", "terminated"]}, "license_expiry": {"$ne": None}}, {"_id": 0}).to_list(20000)
    for dv in drivers:
        du = _days_until(dv.get("license_expiry"))
        if du is not None and du <= doc_horizon_days:
            out.append(_item("licences_expiring", "driver", dv["id"],
                             f"Licence expiring in {du} days", severity="danger" if du < 0 else "warning"))

    # --- Accidents / claims --------------------------------------------------
    open_claim = {"reported", "evidence_collected", "claim_submitted", "under_survey", "approved"}
    for a in await db.accidents.find({**nt, "claim_status": {"$in": list(open_claim)}}, {"_id": 0}).to_list(20000):
        out.append(_item("open_accident_claims", "accident", a["id"],
                         f"Open accident claim ({a.get('claim_status')})", severity="info"))
    for a in await db.accidents.find({**nt, "claim_status": "approved"}, {"_id": 0}).to_list(20000):
        out.append(_item("claims_awaiting_settlement", "accident", a["id"],
                         "Approved claim awaiting settlement", severity="warning"))
    return out


@router.get("/exceptions")
async def list_exceptions(
    trip_overdue_days: int = Query(DEFAULT_TRIP_OVERDUE_DAYS, ge=0),
    repair_overdue_days: int = Query(DEFAULT_REPAIR_OVERDUE_DAYS, ge=0),
    doc_horizon_days: int = Query(DEFAULT_DOC_HORIZON_DAYS, ge=0),
    category: str = None,
    user=Depends(require_module("dashboard")),
):
    """Org-scoped operational exceptions across every module, derived live from
    canonical data. Acknowledged items are flagged (not removed)."""
    items = await _build_exceptions(trip_overdue_days, repair_overdue_days, doc_horizon_days)
    # Merge acknowledgement state (a flag, never a filter that hides the source).
    acks = {a["exception_id"]: a for a in
            await db.exception_acks.find({}, {"_id": 0}).to_list(50000)}
    for it in items:
        ack = acks.get(it["id"])
        it["acknowledged"] = bool(ack)
        it["acknowledged_by"] = ack.get("acknowledged_by") if ack else None
        it["acknowledged_at"] = ack.get("acknowledged_at") if ack else None
    if category:
        items = [i for i in items if i["category"] == category]
    by_category = {}
    for i in items:
        by_category[i["category"]] = by_category.get(i["category"], 0) + 1
    return {
        "items": items,
        "total": len(items),
        "unacknowledged": sum(1 for i in items if not i["acknowledged"]),
        "by_category": by_category,
        "thresholds": {
            "trip_overdue_days": trip_overdue_days,
            "repair_overdue_days": repair_overdue_days,
            "doc_horizon_days": doc_horizon_days,
        },
    }


@router.post("/exceptions/{exception_id}/acknowledge")
async def acknowledge_exception(exception_id: str, payload: dict = Body(default={}),
                                user=Depends(require_permission("exceptions:acknowledge"))):
    """Acknowledge an exception by its stable id. Idempotent (upsert on a unique
    (org, exception_id)); records who/when and an optional note. Does not resolve
    the underlying condition — the item stays until its source clears."""
    now = datetime.now(timezone.utc).isoformat()
    await db.exception_acks.update_one(
        {"exception_id": exception_id},
        {"$set": {
            "exception_id": exception_id,
            "acknowledged_by": user.get("user_id"),
            "acknowledged_at": now,
            "note": payload.get("note"),
        }},
        upsert=True,
    )
    await record_security_event("exception.acknowledge", user, target_id=exception_id, detail={})
    return {"exception_id": exception_id, "acknowledged": True, "acknowledged_at": now}
