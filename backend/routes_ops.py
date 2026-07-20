from fastapi import APIRouter, Body, Depends, HTTPException
from database import db
from auth import require_permission
from models import TripCreate, FuelCreate, ServiceCreate, RepairCreate, GreasingCreate
from helpers import make_crud

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
    closing_km = payload.get("closing_km")
    if closing_km is None or closing_km < trip["opening_km"]:
        raise HTTPException(status_code=400, detail="closing_km must be >= opening_km")
    distance = round(closing_km - trip["opening_km"], 1)
    await db.trips.update_one({"id": trip_id}, {"$set": {"closing_km": closing_km, "distance": distance, "status": "completed"}})
    await _update_vehicle_odometer(trip["vehicle_id"], closing_km)
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
TICKET_FLOW = {
    "open": ["under_review"],
    "under_review": ["approved", "open"],  # under_review → open allowed for rejection
    "approved": ["sent_for_repair"],
    "sent_for_repair": ["in_repair"],
    "in_repair": ["repaired"],
    "repaired": ["closed"],
    "closed": [],
}

STATUS_REQUIRES_ROLE = {
    "approved": ("management", "admin"),
    "closed": ("management", "admin"),
    "open": ("management", "admin"),  # rejection back to open requires management+
}

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
async def advance_repair(repair_id: str, payload: dict = Body(...), user=Depends(require_permission("repairs:transition"))):
    repair = await db.repairs.find_one({"id": repair_id}, {"_id": 0})
    if not repair:
        raise HTTPException(status_code=404, detail="Ticket not found")
    new_status = payload.get("status")
    current = repair.get("status", "open")
    # Legacy migration: if record still has old status, accept "reported" → "open"
    if current == "reported":
        current = "open"
    allowed_next = TICKET_FLOW.get(current, [])
    if new_status not in allowed_next:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition {current} → {new_status}",
        )
    required_roles = STATUS_REQUIRES_ROLE.get(new_status)
    if required_roles and user.get("role") not in required_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Status '{new_status}' requires Management or Admin",
        )
    updates = {"status": new_status}
    field = STAGE_FIELD_FILLED.get(new_status)
    if field:
        from datetime import datetime, timezone
        ts_field, user_field = field
        updates[ts_field] = datetime.now(timezone.utc).isoformat()
        if user_field:
            updates[user_field] = user.get("name") or user.get("full_name") or user.get("username")
    # Pass-through optional fields
    if payload.get("cost") is not None:
        updates["cost"] = payload["cost"]
    if payload.get("vendor"):
        updates["vendor"] = payload["vendor"]
    if payload.get("vendor_id"):
        updates["vendor_id"] = payload["vendor_id"]
    if payload.get("notes"):
        updates["notes"] = payload["notes"]
    if payload.get("rejection_reason"):
        updates["rejection_reason"] = payload["rejection_reason"]
    await db.repairs.update_one({"id": repair_id}, {"$set": updates})
    return await db.repairs.find_one({"id": repair_id}, {"_id": 0})
