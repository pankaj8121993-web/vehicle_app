"""
Global search across vehicles, drivers, tickets and documents.
Case-insensitive substring search, results capped at 10 per group.
Excludes test data and disposed vehicles / exited drivers.
"""
import re
from fastapi import APIRouter, Depends, Query
from database import db
from auth import require_user, require_module

router = APIRouter(tags=["search"])

DISPOSED_STATUSES = ["sold", "scrapped"]
EXITED_STATUSES = ["resigned", "terminated"]


@router.get("/search")
async def search(q: str = Query(""), user=Depends(require_module("search"))):
    q = (q or "").strip()
    if len(q) < 2:
        return {"vehicles": [], "drivers": [], "tickets": [], "documents": []}
    rx = {"$regex": re.escape(q), "$options": "i"}
    base = {"is_test_data": {"$ne": True}}

    vehicles = await db.vehicles.find(
        {**base,
         "status": {"$nin": DISPOSED_STATUSES},
         "$or": [
             {"vehicle_number": rx}, {"make": rx}, {"model": rx},
             {"chassis_number": rx}, {"engine_number": rx},
         ]},
        {"_id": 0},
    ).limit(10).to_list(10)

    drivers = await db.drivers.find(
        {**base,
         "status": {"$nin": EXITED_STATUSES},
         "$or": [
             {"name": rx}, {"mobile": rx}, {"license_number": rx},
             {"aadhaar": rx}, {"employee_number": rx},
         ]},
        {"_id": 0},
    ).limit(10).to_list(10)

    tickets = await db.repairs.find(
        {**base, "$or": [{"ticket_number": rx}, {"issue": rx}]},
        {"_id": 0},
    ).limit(10).to_list(10)

    documents = await db.documents.find(
        {**base, "$or": [{"doc_number": rx}, {"doc_type": rx}]},
        {"_id": 0},
    ).limit(10).to_list(10)

    # Enrich tickets and documents with vehicle_number
    vmap = {
        v["id"]: v.get("vehicle_number", "")
        for v in await db.vehicles.find({}, {"_id": 0, "id": 1, "vehicle_number": 1}).to_list(3000)
    }
    for item in tickets:
        item["vehicle_number"] = vmap.get(item.get("vehicle_id"), "")
    for item in documents:
        item["vehicle_number"] = vmap.get(item.get("vehicle_id"), "")

    return {
        "vehicles": vehicles,
        "drivers": drivers,
        "tickets": tickets,
        "documents": documents,
    }
