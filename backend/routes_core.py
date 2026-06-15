import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Body, Depends, HTTPException, Request, UploadFile, File, Response
from database import db
from auth import require_user, require_role
from models import VehicleCreate, DriverCreate, DocumentCreate
from helpers import make_crud, enrich, gather_expenses
from storage import put_object, get_object, APP_NAME

router = APIRouter(tags=["core"])

DOC_TYPES = ["RC", "Insurance", "Fitness", "Permit", "PUC", "Road Tax", "Fastag", "Other"]
DISPOSED_STATUSES = ["sold", "scrapped"]
DRIVER_EXIT_STATUSES = ["resigned", "terminated"]
DRIVER_ACTIVE_STATUSES = ["active", "on_leave"]

# Collections checked when blocking a vehicle delete
VEHICLE_HISTORY_COLLECTIONS = [
    "trips", "fuel_entries", "services", "repairs", "tyres", "tyre_events",
    "accidents", "fastag_transactions", "downtimes", "expenses", "documents",
]
# Collections checked when blocking a driver delete
DRIVER_HISTORY_COLLECTIONS = ["trips", "fuel_entries", "accidents"]


def today_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------- Vehicles ----------
@router.get("/vehicles")
async def list_vehicles(request: Request, user=Depends(require_user)):
    p = dict(request.query_params)
    include_disposed = (p.get("include_disposed") or "").lower() == "true"
    q = {} if include_disposed else {"status": {"$nin": DISPOSED_STATUSES}}
    if p.get("all") == "true":
        return await db.vehicles.find(q, {"_id": 0}).sort("vehicle_number", 1).to_list(3000)
    page = max(int(p.get("page", 1)), 1)
    page_size = min(max(int(p.get("page_size", 25)), 1), 200)
    total = await db.vehicles.count_documents(q)
    items = await db.vehicles.find(q, {"_id": 0}).sort("vehicle_number", 1).skip((page - 1) * page_size).limit(page_size).to_list(page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/vehicles")
async def create_vehicle(payload: VehicleCreate, user=Depends(require_user)):
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.vehicles.insert_one({**doc})
    doc.pop("_id", None)
    return doc


@router.put("/vehicles/{vid}")
async def update_vehicle(vid: str, payload: dict = Body(...), user=Depends(require_role("data_entry", "management", "admin"))):
    payload = {k: v for k, v in payload.items() if k not in ("id", "_id", "created_at")}
    existing = await db.vehicles.find_one({"id": vid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    new_status = payload.get("status")
    is_disposing = (
        new_status in DISPOSED_STATUSES
        and existing.get("status") not in DISPOSED_STATUSES
    )
    if is_disposing:
        if user.get("role") not in ("management", "admin"):
            raise HTTPException(status_code=403, detail="Only Management or Admin can mark a vehicle as Sold or Scrapped")
        if not payload.get("disposal_date"):
            payload["disposal_date"] = today_iso()
        # Close any open downtimes
        await db.downtimes.update_many(
            {"vehicle_id": vid, "status": "open"},
            {"$set": {"status": "closed", "end_date": payload["disposal_date"]}},
        )
        # Unassign any drivers currently linked to this vehicle
        await db.drivers.update_many(
            {"assigned_vehicle_id": vid},
            {"$set": {"assigned_vehicle_id": None}},
        )

    res = await db.vehicles.update_one({"id": vid}, {"$set": payload})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return await db.vehicles.find_one({"id": vid}, {"_id": 0})


@router.delete("/vehicles/{vid}")
async def delete_vehicle(vid: str, user=Depends(require_role("admin"))):
    existing = await db.vehicles.find_one({"id": vid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    # Block delete if any history exists (cascade-delete removed in Phase 1)
    for coll in VEHICLE_HISTORY_COLLECTIONS:
        if await db[coll].count_documents({"vehicle_id": vid}, limit=1):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Cannot delete vehicle with existing history. "
                    "Mark it as Sold or Scrapped instead to preserve records."
                ),
            )
    await db.vehicles.delete_one({"id": vid})
    return {"ok": True}


@router.get("/vehicles/{vid}/summary")
async def vehicle_summary(vid: str, user=Depends(require_user)):
    vehicle = await db.vehicles.find_one({"id": vid}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    docs = await db.documents.find({"vehicle_id": vid}, {"_id": 0}).to_list(500)
    expiries = {}
    for d in docs:
        if d.get("expiry_date"):
            t = d["doc_type"]
            if t not in expiries or d["expiry_date"] > expiries[t]:
                expiries[t] = d["expiry_date"]

    latest_service = await db.services.find({"vehicle_id": vid}, {"_id": 0}).sort("date", -1).to_list(1)
    next_due_date = latest_service[0].get("next_due_date") if latest_service else None
    next_due_km = latest_service[0].get("next_due_km") if latest_service else None

    trips = await db.trips.find({"vehicle_id": vid}, {"_id": 0}).to_list(5000)
    total_km = sum(t.get("distance") or 0 for t in trips)

    fuel = await db.fuel_entries.find({"vehicle_id": vid}, {"_id": 0}).to_list(5000)
    mileages = [f["mileage"] for f in fuel if f.get("mileage")]
    avg_mileage = round(sum(mileages) / len(mileages), 2) if mileages else None

    expenses = await gather_expenses(vehicle_id=vid)
    total_cost = round(sum(r["amount"] for r in expenses), 2)
    cost_per_km = round(total_cost / total_km, 2) if total_km else None

    accidents_count = await db.accidents.count_documents({"vehicle_id": vid})
    open_repairs = await db.repairs.count_documents({"vehicle_id": vid, "status": {"$nin": ["completed", "closed"]}})
    downtimes = await db.downtimes.find({"vehicle_id": vid}, {"_id": 0}).to_list(1000)
    downtime_days = sum(d.get("days") or 0 for d in downtimes)

    return {
        "vehicle": vehicle,
        "document_expiries": expiries,
        "next_service_due_date": next_due_date,
        "next_service_due_km": next_due_km,
        "total_trips": len(trips),
        "total_km": total_km,
        "total_fuel_quantity": round(sum(f.get("quantity") or 0 for f in fuel), 2),
        "total_fuel_cost": round(sum(f.get("amount") or 0 for f in fuel), 2),
        "avg_mileage": avg_mileage,
        "total_operating_cost": total_cost,
        "cost_per_km": cost_per_km,
        "accidents_count": accidents_count,
        "open_repairs": open_repairs,
        "downtime_days": downtime_days,
    }


# ---------- Drivers ----------
async def _enrich_drivers(drivers, vmap):
    for d in drivers:
        if d.get("assigned_vehicle_id"):
            d["assigned_vehicle_number"] = vmap.get(d["assigned_vehicle_id"], "")
    return drivers


# IMPORTANT: define /drivers/active BEFORE any /drivers/{did} routes so FastAPI matches it first.
@router.get("/drivers/active")
async def list_active_drivers(user=Depends(require_user)):
    """Active + on_leave drivers — for dropdowns in trip/fuel/accident forms."""
    drivers = await db.drivers.find(
        {"status": {"$in": DRIVER_ACTIVE_STATUSES}}, {"_id": 0}
    ).sort("name", 1).to_list(3000)
    vmap = {v["id"]: v.get("vehicle_number", "") for v in await db.vehicles.find({}, {"_id": 0, "id": 1, "vehicle_number": 1}).to_list(3000)}
    return await _enrich_drivers(drivers, vmap)


@router.get("/drivers")
async def list_drivers(request: Request, user=Depends(require_user)):
    p = dict(request.query_params)
    vmap = {v["id"]: v.get("vehicle_number", "") for v in await db.vehicles.find({}, {"_id": 0, "id": 1, "vehicle_number": 1}).to_list(3000)}
    if p.get("all") == "true":
        drivers = await db.drivers.find({}, {"_id": 0}).sort("name", 1).to_list(3000)
        return await _enrich_drivers(drivers, vmap)
    page = max(int(p.get("page", 1)), 1)
    page_size = min(max(int(p.get("page_size", 25)), 1), 200)
    total = await db.drivers.count_documents({})
    drivers = await db.drivers.find({}, {"_id": 0}).sort("name", 1).skip((page - 1) * page_size).limit(page_size).to_list(page_size)
    drivers = await _enrich_drivers(drivers, vmap)
    return {"items": drivers, "total": total, "page": page, "page_size": page_size}


@router.post("/drivers")
async def create_driver(payload: DriverCreate, user=Depends(require_user)):
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.drivers.insert_one({**doc})
    doc.pop("_id", None)
    return doc


@router.put("/drivers/{did}")
async def update_driver(did: str, payload: dict = Body(...), user=Depends(require_role("data_entry", "management", "admin"))):
    payload = {k: v for k, v in payload.items() if k not in ("id", "_id", "created_at")}
    existing = await db.drivers.find_one({"id": did}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Driver not found")

    new_status = payload.get("status")
    is_exiting = (
        new_status in DRIVER_EXIT_STATUSES
        and existing.get("status") not in DRIVER_EXIT_STATUSES
    )
    if is_exiting:
        if user.get("role") not in ("management", "admin"):
            raise HTTPException(status_code=403, detail="Only Management or Admin can mark a driver as Resigned or Terminated")
        if not payload.get("exit_date"):
            payload["exit_date"] = today_iso()
        # Auto-unassign vehicle
        payload["assigned_vehicle_id"] = None

    res = await db.drivers.update_one({"id": did}, {"$set": payload})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Driver not found")
    return await db.drivers.find_one({"id": did}, {"_id": 0})


@router.delete("/drivers/{did}")
async def delete_driver(did: str, user=Depends(require_role("admin"))):
    existing = await db.drivers.find_one({"id": did}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Driver not found")
    for coll in DRIVER_HISTORY_COLLECTIONS:
        if await db[coll].count_documents({"driver_id": did}, limit=1):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Cannot delete driver with existing trips, fuel entries or accidents. "
                    "Mark them as Resigned or Terminated instead to preserve records."
                ),
            )
    await db.drivers.delete_one({"id": did})
    return {"ok": True}


@router.get("/drivers/{did}/stats")
async def driver_stats(did: str, user=Depends(require_user)):
    driver = await db.drivers.find_one({"id": did}, {"_id": 0})
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    if driver.get("assigned_vehicle_id"):
        v = await db.vehicles.find_one({"id": driver["assigned_vehicle_id"]}, {"_id": 0, "vehicle_number": 1})
        driver["assigned_vehicle_number"] = v.get("vehicle_number") if v else ""
    trips = await db.trips.find({"driver_id": did}, {"_id": 0}).to_list(10000)
    fuel = await db.fuel_entries.find({"driver_id": did}, {"_id": 0}).to_list(10000)
    mileages = [f["mileage"] for f in fuel if f.get("mileage")]
    return {
        "driver": driver,
        "total_trips": len(trips),
        "total_km": round(sum(t.get("distance") or 0 for t in trips), 1),
        "trip_expenses": round(sum((t.get("toll_expense") or 0) + (t.get("parking_expense") or 0) + (t.get("misc_expense") or 0) for t in trips), 2),
        "fuel_entries": len(fuel),
        "total_fuel_cost": round(sum(f.get("amount") or 0 for f in fuel), 2),
        "avg_mileage": round(sum(mileages) / len(mileages), 2) if mileages else None,
        "accidents_count": await db.accidents.count_documents({"driver_id": did}),
    }


# ---------- Documents ----------
make_crud(router, "documents", "documents", DocumentCreate, date_field="expiry_date")


# ---------- File upload / download ----------
MIME_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf",
    "csv": "text/csv", "txt": "text/plain",
}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), user=Depends(require_user)):
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "bin"
    content_type = file.content_type or MIME_TYPES.get(ext, "application/octet-stream")
    path = f"{APP_NAME}/uploads/{user['user_id']}/{uuid.uuid4()}.{ext}"
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 15MB)")
    try:
        result = put_object(path, data, content_type)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Storage upload failed: {e}")
    file_id = str(uuid.uuid4())
    await db.files.insert_one({
        "id": file_id,
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "is_deleted": False,
        "uploaded_by": user["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"file_id": file_id, "original_filename": file.filename}


@router.get("/files/{file_id}")
async def download_file(file_id: str, user=Depends(require_user)):
    record = await db.files.find_one({"id": file_id, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        data, content_type = get_object(record["storage_path"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Storage download failed: {e}")
    return Response(
        content=data,
        media_type=record.get("content_type", content_type),
        headers={"Content-Disposition": f'inline; filename="{record.get("original_filename", "file")}"'},
    )
