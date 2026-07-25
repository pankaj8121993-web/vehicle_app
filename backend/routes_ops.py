from fastapi import APIRouter, Body, Depends, HTTPException, Request
from database import db
from auth import require_permission, record_security_event
from models import TripCreate, FuelCreate, ServiceCreate, RepairCreate, GreasingCreate
from helpers import make_crud
import atomicity
import idempotency
import invariants
import workflow

router = APIRouter(tags=["operations"])


async def _update_vehicle_odometer(vehicle_id: str, odometer):
    if odometer is None:
        return
    vehicle = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if vehicle and (vehicle.get("current_odometer") or 0) < odometer:
        await db.vehicles.update_one({"id": vehicle_id}, {"$set": {"current_odometer": odometer}})


# ---------- Trips ----------
async def on_trip_create(doc):
    if doc.get("closing_km") is not None:
        doc["distance"] = round(doc["closing_km"] - doc["opening_km"], 1)
        doc["status"] = "completed"
        await _update_vehicle_odometer(doc["vehicle_id"], doc["closing_km"])
    else:
        doc["distance"] = None
        doc["status"] = "ongoing"
    return doc

make_crud(router, "trips", "trips", TripCreate, on_create=on_trip_create, driver_can_create=True)


@router.patch("/trips/{trip_id}/close")
async def close_trip(trip_id: str, payload: dict = Body(...), user=Depends(require_permission("trips:close"))):
    trip = await db.trips.find_one({"id": trip_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    # WF-01: closing is a one-way transition. A trip already completed is not
    # re-closed — that would recompute distance/odometer from a new closing_km
    # and double-apply the odometer bump. Idempotent: return it unchanged.
    if workflow.validate_transition(
        workflow.TRIP_STATUS_WORKFLOW, trip.get("status"), "completed"
    ) == "noop":
        return trip
    closing_km = payload.get("closing_km")
    if closing_km is None:
        raise HTTPException(status_code=400, detail="closing_km must be >= opening_km")
    # DI-01: validate the reading itself (finite, non-negative, bounded) before
    # the ordering check, so inf/NaN cannot slip past the comparison.
    closing_km = invariants.odometer(closing_km, field="closing_km", allow_none=False)
    if closing_km < trip["opening_km"]:
        raise HTTPException(status_code=400, detail="closing_km must be >= opening_km")
    distance = round(closing_km - trip["opening_km"], 1)
    # DI-02: compare-and-swap on the still-"ongoing" trip. Two concurrent closes
    # cannot both apply the odometer bump — exactly one matches "ongoing" and
    # wins; the loser sees the trip already completed and returns it idempotently.
    won = await atomicity.swap_status(
        "trips", trip_id, trip.get("status") or "ongoing",
        {"closing_km": closing_km, "distance": distance, "status": "completed"},
    )
    if not won:
        return await db.trips.find_one({"id": trip_id}, {"_id": 0})
    await _update_vehicle_odometer(trip["vehicle_id"], closing_km)
    await record_security_event("trip.close", user, target_id=trip_id,
                                detail={"distance": distance})
    return await db.trips.find_one({"id": trip_id}, {"_id": 0})


# ---------- Fuel ----------
async def on_fuel_create(doc):
    prev = await db.fuel_entries.find(
        {"vehicle_id": doc["vehicle_id"], "odometer": {"$lt": doc["odometer"]}}, {"_id": 0}
    ).sort("odometer", -1).to_list(1)
    if prev and doc.get("quantity"):
        km = doc["odometer"] - prev[0]["odometer"]
        doc["mileage"] = round(km / doc["quantity"], 2) if doc["quantity"] > 0 else None
        doc["fuel_cost_per_km"] = round(doc["amount"] / km, 2) if km > 0 else None
    else:
        doc["mileage"] = None
        doc["fuel_cost_per_km"] = None
    await _update_vehicle_odometer(doc["vehicle_id"], doc["odometer"])
    return doc

make_crud(router, "fuel", "fuel_entries", FuelCreate, on_create=on_fuel_create, driver_can_create=True)


# ---------- Services (Maintenance) ----------
async def on_service_create(doc):
    await _update_vehicle_odometer(doc["vehicle_id"], doc.get("odometer"))
    return doc

make_crud(router, "services", "services", ServiceCreate, on_create=on_service_create, module="maintenance")


# ---------- Greasing (Phase 1.5) ----------
async def on_greasing_create(doc):
    await _update_vehicle_odometer(doc["vehicle_id"], doc.get("odometer"))
    return doc

make_crud(router, "greasings", "greasings", GreasingCreate, on_create=on_greasing_create, module="maintenance")


# ---------- Repairs / Service Tickets ----------
# WF-01: the ticket state graph and per-state role rules moved to
# workflow.REPAIR_WORKFLOW (the single source of truth for every workflow). Only
# the per-stage timestamp/actor fields remain here, as they are repair-specific
# presentation rather than transition rules.
STAGE_FIELD_FILLED = {
    "under_review": ("reviewed_at", "reviewed_by"),
    "approved": ("approved_at", "approved_by"),
    "sent_for_repair": ("sent_to_vendor_at", None),
    "in_repair": ("in_repair_at", None),
    "repaired": ("repaired_at", None),
    "closed": ("closed_at", "closed_by"),
}


async def _next_ticket_number(year: str) -> str:
    last = await db.repairs.find(
        {"ticket_number": {"$regex": f"^TKT-{year}-"}},
        {"_id": 0, "ticket_number": 1},
    ).sort("ticket_number", -1).to_list(1)
    if last and last[0].get("ticket_number"):
        try:
            n = int(last[0]["ticket_number"].split("-")[-1]) + 1
        except (ValueError, IndexError):
            n = 1
    else:
        n = 1
    return f"TKT-{year}-{n:04d}"


async def on_repair_create(doc):
    # Default status by repair_type
    doc["status"] = "closed" if doc.get("repair_type") == "minor" else "open"
    # Auto-assign ticket number
    if not doc.get("ticket_number"):
        year = (doc.get("date") or "1970-01-01")[:4]
        doc["ticket_number"] = await _next_ticket_number(year)
    return doc

make_crud(router, "repairs", "repairs", RepairCreate, on_create=on_repair_create, driver_can_create=True)


@router.patch("/repairs/{repair_id}/status")
async def advance_repair(repair_id: str, request: Request, payload: dict = Body(...), user=Depends(require_permission("repairs:transition"))):
    # DI-02: optional idempotency for the transition action — a double-tapped
    # "Approve" with the same Idempotency-Key replays the first result.
    idem_key = idempotency.key_from_headers(request.headers)
    scope = f"repair-transition:{repair_id}"
    if idem_key:
        replayed, _fp = await idempotency.replay_or_claim(scope, idem_key, payload)
        if replayed is not None:
            return replayed
    repair = await db.repairs.find_one({"id": repair_id}, {"_id": 0})
    if not repair:
        if idem_key:
            await idempotency.release(scope, idem_key)
        raise HTTPException(status_code=404, detail="Ticket not found")
    new_status = payload.get("status")
    stored_status = repair.get("status", "open")
    current = stored_status
    # Legacy migration: if record still has old status, accept "reported" → "open"
    if current == "reported":
        current = "open"
    # WF-01: the ticket state graph and its per-state role rules are now the
    # shared engine's REPAIR_WORKFLOW. Optimistic-concurrency check: a caller may
    # pass expected_version so two managers cannot both advance the same ticket.
    workflow.check_version(repair, payload.get("expected_version"))
    kind = workflow.validate_transition(
        workflow.REPAIR_WORKFLOW, current, new_status, role=user.get("role")
    )
    if kind == "noop":
        # DI-02: the ticket is already in the requested state. Return it
        # idempotently without rewriting timestamps or emitting a second audit —
        # so a retried/serialised double "approve" cannot double-apply.
        result = await db.repairs.find_one({"id": repair_id}, {"_id": 0})
        if idem_key:
            await idempotency.store_result(scope, idem_key, result)
        return result
    updates = {"status": new_status, "_version": workflow.next_version(repair)}
    field = STAGE_FIELD_FILLED.get(new_status)
    if field:
        from datetime import datetime, timezone
        ts_field, user_field = field
        updates[ts_field] = datetime.now(timezone.utc).isoformat()
        if user_field:
            updates[user_field] = user.get("name") or user.get("full_name") or user.get("username")
    # Pass-through optional fields
    if payload.get("cost") is not None:
        # DI-01: the authorised cost still passes canonical money validation.
        updates["cost"] = invariants.money(payload["cost"], field="cost")
    if payload.get("vendor"):
        updates["vendor"] = payload["vendor"]
    if payload.get("vendor_id"):
        updates["vendor_id"] = payload["vendor_id"]
    if payload.get("notes"):
        updates["notes"] = payload["notes"]
    if payload.get("rejection_reason"):
        updates["rejection_reason"] = payload["rejection_reason"]
    # DI-02: compare-and-swap on the ticket's stored status. Of two concurrent
    # requests advancing the same ticket, only the one whose expected status
    # still matches wins — the other gets 409, so a ticket cannot be
    # double-approved or double-closed. A single atomic single-document update,
    # safe without a multi-document transaction.
    won = await atomicity.swap_status("repairs", repair_id, stored_status, updates)
    if not won:
        if idem_key:
            await idempotency.release(scope, idem_key)
        raise HTTPException(
            status_code=409,
            detail="This ticket changed since you loaded it. Reload and retry.",
        )
    await record_security_event("repair.transition", user, target_id=repair_id,
                                detail={"from": current, "to": new_status})
    result = await db.repairs.find_one({"id": repair_id}, {"_id": 0})
    if idem_key:
        await idempotency.store_result(scope, idem_key, result)
    return result
