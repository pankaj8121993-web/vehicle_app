from fastapi import APIRouter, Body, Depends, HTTPException
from database import db
from auth import require_user, require_role
from models import TripCreate, FuelCreate, ServiceCreate, RepairCreate
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

make_crud(router, "trips", "trips", TripCreate, on_create=on_trip_create)


@router.patch("/trips/{trip_id}/close")
async def close_trip(trip_id: str, payload: dict = Body(...), user=Depends(require_user)):
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

make_crud(router, "fuel", "fuel_entries", FuelCreate, on_create=on_fuel_create)


# ---------- Services (Maintenance) ----------
async def on_service_create(doc):
    await _update_vehicle_odometer(doc["vehicle_id"], doc.get("odometer"))
    return doc

make_crud(router, "services", "services", ServiceCreate, on_create=on_service_create)


# ---------- Repairs ----------
REPAIR_FLOW = ["reported", "approved", "in_repair", "completed"]


async def on_repair_create(doc):
    doc["status"] = "completed" if doc["repair_type"] == "minor" else "reported"
    return doc

make_crud(router, "repairs", "repairs", RepairCreate, on_create=on_repair_create)


@router.patch("/repairs/{repair_id}/status")
async def advance_repair(repair_id: str, payload: dict = Body(...), user=Depends(require_user)):
    repair = await db.repairs.find_one({"id": repair_id}, {"_id": 0})
    if not repair:
        raise HTTPException(status_code=404, detail="Repair not found")
    new_status = payload.get("status")
    if new_status not in REPAIR_FLOW:
        raise HTTPException(status_code=400, detail="Invalid status")
    if new_status == "approved" and user.get("role") not in ("fleet_manager", "management"):
        raise HTTPException(status_code=403, detail="Only Fleet Manager or Management can approve repairs")
    updates = {"status": new_status}
    if new_status == "approved":
        updates["approved_by"] = user["name"]
    if payload.get("cost") is not None:
        updates["cost"] = payload["cost"]
    await db.repairs.update_one({"id": repair_id}, {"$set": updates})
    return await db.repairs.find_one({"id": repair_id}, {"_id": 0})
