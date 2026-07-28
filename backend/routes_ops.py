import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from database import db
from auth import require_permission, record_security_event
from models import TripCreate, TripPlan, FuelCreate, ServiceCreate, RepairCreate, GreasingCreate
from helpers import make_crud
from references import validate_references
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


# ---------- Trips (OPS-01 lifecycle) ----------
# Full operational lifecycle:
#   planned → assigned → ongoing(dispatched) → completed → settlement_pending → closed
# plus cancellation from any pre-completion state. The quick full-entry path
# (POST /trips) is unchanged — it still lands a trip directly in ongoing or
# completed — so every pre-OPS-01 client and test keeps working. The dedicated
# actions below add planning, allocation, dispatch, reassignment and closure
# with allocation-conflict, downtime, idempotency, concurrency and audit
# controls. Generic PUT /trips can no longer touch status (workflow guard).

# A vehicle/driver is "actively allocated" while on a trip in one of these
# states; leaving them (complete/cancel/close) releases the resource.
TRIP_ACTIVE_ALLOCATION = ("assigned", "ongoing")
# Reassigning a trip that has already been dispatched needs explicit authority.
TRIP_REASSIGN_AFTER_DISPATCH_ROLES = ("management", "admin")


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


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


async def _trip_or_404(trip_id):
    trip = await db.trips.find_one({"id": trip_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


async def _assert_no_active_allocation_conflict(vehicle_id, driver_id, exclude_trip_id):
    """A vehicle/driver may be actively allocated to only one trip at a time.

    'Active' is assigned or ongoing — not planned, completed, settlement_pending,
    closed or cancelled. Prevents double-booking the same resource across
    incompatible trips.
    """
    if vehicle_id:
        clash = await db.trips.find_one(
            {"vehicle_id": vehicle_id, "id": {"$ne": exclude_trip_id},
             "status": {"$in": list(TRIP_ACTIVE_ALLOCATION)}},
            {"_id": 0, "id": 1},
        )
        if clash:
            raise HTTPException(status_code=409,
                                detail="Vehicle is already allocated to an active trip")
    if driver_id:
        clash = await db.trips.find_one(
            {"driver_id": driver_id, "id": {"$ne": exclude_trip_id},
             "status": {"$in": list(TRIP_ACTIVE_ALLOCATION)}},
            {"_id": 0, "id": 1},
        )
        if clash:
            raise HTTPException(status_code=409,
                                detail="Driver is already allocated to an active trip")


def _trip_transition(trip, target, *, role=None):
    """Validate a trip status transition; raises the workflow's 409/400/403."""
    return workflow.validate_transition(
        workflow.TRIP_STATUS_WORKFLOW, trip.get("status"), target, role=role
    )


@router.post("/trips/plan")
async def plan_trip(payload: TripPlan, request: Request,
                    user=Depends(require_permission("trips:create"))):
    """Create a trip in the 'planned' state, before a vehicle/driver is committed."""
    body = payload.model_dump()
    doc = dict(body)
    invariants.enforce_record_invariants("trips", doc)
    await validate_references("trips", doc)  # same-org, in-service, only if supplied
    idem_key = idempotency.key_from_headers(request.headers)
    scope = "trip-plan"
    if idem_key:
        replayed, _fp = await idempotency.replay_or_claim(scope, idem_key, body)
        if replayed is not None:
            return replayed
    try:
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = _now_iso()
        doc["created_by"] = user["user_id"]
        doc["is_test_data"] = user.get("role") == "test"
        doc["status"] = "planned"
        doc["distance"] = None
        await db.trips.insert_one({**doc})
        doc.pop("_id", None)
    except Exception:
        if idem_key:
            await idempotency.release(scope, idem_key)
        raise
    await record_security_event("trip.plan", user, target_id=doc["id"],
                                detail={"vehicle_id": doc.get("vehicle_id")})
    if idem_key:
        await idempotency.store_result(scope, idem_key, doc)
    return doc


@router.patch("/trips/{trip_id}/assign")
async def assign_trip(trip_id: str, payload: dict = Body(...),
                      user=Depends(require_permission("trips:close"))):
    """Allocate a vehicle and/or driver to a planned/assigned trip (before dispatch)."""
    trip = await _trip_or_404(trip_id)
    current = trip.get("status")
    if current not in ("planned", "assigned"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot allocate a trip in state {current!r}; it is already dispatched or closed",
        )
    workflow.check_version(trip, payload.get("expected_version"))
    vehicle_id = payload["vehicle_id"] if "vehicle_id" in payload else trip.get("vehicle_id")
    driver_id = payload["driver_id"] if "driver_id" in payload else trip.get("driver_id")
    if not vehicle_id and not driver_id:
        raise HTTPException(status_code=400, detail="Assign a vehicle and/or driver")
    ref = {}
    if vehicle_id:
        ref["vehicle_id"] = vehicle_id
    if driver_id:
        ref["driver_id"] = driver_id
    await validate_references("trips", ref)
    await _assert_no_active_allocation_conflict(vehicle_id, driver_id, trip_id)
    updates = {"vehicle_id": vehicle_id, "driver_id": driver_id,
               "status": "assigned", "_version": workflow.next_version(trip)}
    # CAS on the loaded status so two concurrent assigns cannot both win.
    won = await atomicity.swap_status("trips", trip_id, current, updates)
    if not won:
        raise HTTPException(status_code=409,
                            detail="This trip changed since you loaded it. Reload and retry.")
    await record_security_event("trip.assign", user, target_id=trip_id,
                                detail={"vehicle_id": vehicle_id, "driver_id": driver_id})
    return await db.trips.find_one({"id": trip_id}, {"_id": 0})


@router.patch("/trips/{trip_id}/reassign")
async def reassign_trip(trip_id: str, payload: dict = Body(...),
                        user=Depends(require_permission("trips:close"))):
    """Change a trip's vehicle/driver. Before dispatch: any acting role. After
    dispatch (ongoing): management/admin only, with a mandatory reason."""
    trip = await _trip_or_404(trip_id)
    current = trip.get("status")
    reason = payload.get("reason")
    if current in ("planned", "assigned"):
        pass  # reassignment before dispatch is a routine correction
    elif current == "ongoing":
        if user.get("role") not in TRIP_REASSIGN_AFTER_DISPATCH_ROLES:
            raise HTTPException(status_code=403,
                                detail="Reassigning a dispatched trip requires management or admin")
        if not reason:
            raise HTTPException(status_code=400,
                                detail="A reason is required to reassign a dispatched trip")
    else:
        raise HTTPException(status_code=409,
                            detail=f"Cannot reassign a trip in state {current!r}")
    workflow.check_version(trip, payload.get("expected_version"))
    vehicle_id = payload["vehicle_id"] if "vehicle_id" in payload else trip.get("vehicle_id")
    driver_id = payload["driver_id"] if "driver_id" in payload else trip.get("driver_id")
    ref = {}
    if vehicle_id:
        ref["vehicle_id"] = vehicle_id
    if driver_id:
        ref["driver_id"] = driver_id
    await validate_references("trips", ref)
    await _assert_no_active_allocation_conflict(vehicle_id, driver_id, trip_id)
    updates = {"vehicle_id": vehicle_id, "driver_id": driver_id,
               "_version": workflow.next_version(trip)}
    if reason:
        updates["reassign_reason"] = reason
    won = await atomicity.swap_status("trips", trip_id, current, updates)
    if not won:
        raise HTTPException(status_code=409,
                            detail="This trip changed since you loaded it. Reload and retry.")
    await record_security_event(
        "trip.reassign", user, target_id=trip_id,
        detail={"from_vehicle": trip.get("vehicle_id"), "to_vehicle": vehicle_id,
                "from_driver": trip.get("driver_id"), "to_driver": driver_id,
                "post_dispatch": current == "ongoing"},
    )
    return await db.trips.find_one({"id": trip_id}, {"_id": 0})


@router.patch("/trips/{trip_id}/dispatch")
async def dispatch_trip(trip_id: str, payload: dict = Body(default={}),
                        user=Depends(require_permission("trips:close"))):
    """Dispatch an assigned trip (assigned → ongoing). Requires an allocated
    vehicle and driver, and is blocked while the vehicle has open downtime."""
    trip = await _trip_or_404(trip_id)
    current = trip.get("status")
    workflow.check_version(trip, payload.get("expected_version"))
    # assigned → ongoing. A planned trip is refused here (assign first); an
    # already-ongoing trip is an idempotent no-op (double dispatch).
    if _trip_transition(trip, "ongoing") == "noop":
        return trip
    if not trip.get("vehicle_id"):
        raise HTTPException(status_code=400, detail="Assign a vehicle before dispatch")
    if not trip.get("driver_id"):
        raise HTTPException(status_code=400, detail="Assign a driver before dispatch")
    open_dt = await db.downtimes.find_one(
        {"vehicle_id": trip["vehicle_id"], "status": "open"}, {"_id": 0, "id": 1}
    )
    if open_dt:
        raise HTTPException(status_code=409,
                            detail="Vehicle has open downtime; resolve it before dispatch")
    await _assert_no_active_allocation_conflict(trip["vehicle_id"], trip["driver_id"], trip_id)
    updates = {"status": "ongoing", "_version": workflow.next_version(trip),
               "dispatched_at": _now_iso()}
    if payload.get("opening_km") is not None:
        updates["opening_km"] = invariants.odometer(payload["opening_km"], field="opening_km",
                                                     allow_none=False)
    if payload.get("actual_start_date"):
        updates["actual_start_date"] = payload["actual_start_date"]
    won = await atomicity.swap_status("trips", trip_id, current, updates)
    if not won:
        raise HTTPException(status_code=409,
                            detail="This trip changed since you loaded it. Reload and retry.")
    await record_security_event("trip.dispatch", user, target_id=trip_id,
                                detail={"vehicle_id": trip["vehicle_id"], "driver_id": trip["driver_id"]})
    return await db.trips.find_one({"id": trip_id}, {"_id": 0})


@router.patch("/trips/{trip_id}/close")
async def close_trip(trip_id: str, payload: dict = Body(...), user=Depends(require_permission("trips:close"))):
    """Confirm reach / completion (ongoing → completed): record the closing
    odometer, compute distance and forward the vehicle odometer. Idempotent."""
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


@router.patch("/trips/{trip_id}/finalize")
async def finalize_trip(trip_id: str, payload: dict = Body(default={}),
                        user=Depends(require_permission("trips:close"))):
    """Final operational closure (completed/settlement_pending → closed). Terminal;
    releases the vehicle/driver. Idempotent on an already-closed trip."""
    trip = await _trip_or_404(trip_id)
    current = trip.get("status")
    workflow.check_version(trip, payload.get("expected_version"))
    if _trip_transition(trip, "closed") == "noop":
        return trip
    updates = {"status": "closed", "_version": workflow.next_version(trip),
               "closed_at": _now_iso()}
    won = await atomicity.swap_status("trips", trip_id, current, updates)
    if not won:
        raise HTTPException(status_code=409,
                            detail="This trip changed since you loaded it. Reload and retry.")
    await record_security_event("trip.finalize", user, target_id=trip_id,
                                detail={"from": current})
    return await db.trips.find_one({"id": trip_id}, {"_id": 0})


@router.patch("/trips/{trip_id}/cancel")
async def cancel_trip(trip_id: str, payload: dict = Body(default={}),
                      user=Depends(require_permission("trips:close"))):
    """Cancel a pre-completion trip (planned/assigned/ongoing → cancelled).
    Preserves history and releases the vehicle/driver. Idempotent."""
    trip = await _trip_or_404(trip_id)
    current = trip.get("status")
    workflow.check_version(trip, payload.get("expected_version"))
    if _trip_transition(trip, "cancelled") == "noop":
        return trip
    reason = payload.get("reason")
    updates = {"status": "cancelled", "_version": workflow.next_version(trip),
               "cancelled_at": _now_iso()}
    if reason:
        updates["cancel_reason"] = reason
    won = await atomicity.swap_status("trips", trip_id, current, updates)
    if not won:
        raise HTTPException(status_code=409,
                            detail="This trip changed since you loaded it. Reload and retry.")
    await record_security_event("trip.cancel", user, target_id=trip_id,
                                detail={"from": current})
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
    # OPS-03: capture the odometer at completion and forward the vehicle master
    # (only meaningful once the vehicle is actually back — repaired/closed).
    if payload.get("odometer") is not None and new_status in ("repaired", "closed"):
        updates["completion_odometer"] = invariants.odometer(
            payload["odometer"], field="odometer", allow_none=False)
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
    # OPS-03: operational side effects run after the source transition is stored
    # (write-source-first). Entering active repair takes the vehicle off the road;
    # completion forwards the odometer. Closing a repair deliberately does NOT
    # auto-close the downtime — an unresolved downtime must be closed explicitly.
    if new_status == "in_repair":
        await _ensure_repair_downtime(repair, user)
    if updates.get("completion_odometer") is not None:
        await _update_vehicle_odometer(repair["vehicle_id"], updates["completion_odometer"])
    await record_security_event("repair.transition", user, target_id=repair_id,
                                detail={"from": current, "to": new_status})
    result = await db.repairs.find_one({"id": repair_id}, {"_id": 0})
    if idem_key:
        await idempotency.store_result(scope, idem_key, result)
    return result


async def _ensure_repair_downtime(repair, user):
    """Take a vehicle off the road when a repair enters the workshop.

    Opens a downtime linked to the repair if none is open, and moves an
    operational vehicle to 'maintenance'. Idempotent: a second call while a
    downtime is already open creates nothing.
    """
    vid = repair["vehicle_id"]
    existing = await db.downtimes.find_one(
        {"vehicle_id": vid, "status": "open"}, {"_id": 0, "id": 1})
    if not existing:
        await db.downtimes.insert_one({
            "id": str(uuid.uuid4()),
            "vehicle_id": vid,
            "reason": "breakdown",
            "start_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "status": "open",
            "days": None,
            "repair_id": repair.get("id"),
            "created_at": _now_iso(),
            "created_by": user.get("user_id"),
            "is_test_data": repair.get("is_test_data", False),
        })
    # Move an operational vehicle into maintenance (disposed vehicles untouched).
    await db.vehicles.update_one(
        {"id": vid, "status": {"$in": ["active", "inactive", "idle"]}},
        {"$set": {"status": "maintenance"}},
    )
