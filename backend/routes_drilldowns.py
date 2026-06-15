"""
Phase 1 — Drill-down endpoints for clickable Dashboard widgets.
All endpoints exclude sold/scrapped vehicles.
"""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from database import db
from auth import require_user
from helpers import gather_expenses, get_lookup_maps

router = APIRouter(prefix="/drilldowns", tags=["drilldowns"])

DISPOSED_STATUSES = ["sold", "scrapped"]


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def _active_vehicle_map():
    """{id: vehicle_number} for non-disposed vehicles only."""
    vs = await db.vehicles.find(
        {"status": {"$nin": DISPOSED_STATUSES}}, {"_id": 0}
    ).to_list(3000)
    return {v["id"]: v for v in vs}


@router.get("/docs_expiring")
async def docs_expiring(days: int = 30, user=Depends(require_user)):
    """Documents expiring within N days (latest expiry per vehicle/doc_type)."""
    today = _today()
    target = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")
    vmap = await _active_vehicle_map()
    docs = await db.documents.find({"expiry_date": {"$ne": None}}, {"_id": 0}).to_list(5000)
    latest = {}
    for d in docs:
        if d["vehicle_id"] not in vmap:
            continue
        key = (d["vehicle_id"], d["doc_type"])
        if key not in latest or (d.get("expiry_date") or "") > (latest[key].get("expiry_date") or ""):
            latest[key] = d
    rows = []
    for d in latest.values():
        exp = d["expiry_date"]
        if today <= exp <= target:
            v = vmap[d["vehicle_id"]]
            rows.append({
                "vehicle_id": d["vehicle_id"],
                "vehicle_number": v.get("vehicle_number", ""),
                "doc_type": d["doc_type"],
                "doc_number": d.get("doc_number"),
                "expiry_date": exp,
            })
    rows.sort(key=lambda r: r["expiry_date"])
    return rows


@router.get("/docs_expired")
async def docs_expired(user=Depends(require_user)):
    """Documents already expired (latest expiry per vehicle/doc_type)."""
    today = _today()
    vmap = await _active_vehicle_map()
    docs = await db.documents.find({"expiry_date": {"$ne": None}}, {"_id": 0}).to_list(5000)
    latest = {}
    for d in docs:
        if d["vehicle_id"] not in vmap:
            continue
        key = (d["vehicle_id"], d["doc_type"])
        if key not in latest or (d.get("expiry_date") or "") > (latest[key].get("expiry_date") or ""):
            latest[key] = d
    rows = []
    for d in latest.values():
        if d["expiry_date"] < today:
            v = vmap[d["vehicle_id"]]
            rows.append({
                "vehicle_id": d["vehicle_id"],
                "vehicle_number": v.get("vehicle_number", ""),
                "doc_type": d["doc_type"],
                "doc_number": d.get("doc_number"),
                "expiry_date": d["expiry_date"],
            })
    rows.sort(key=lambda r: r["expiry_date"])
    return rows


@router.get("/vehicles_under_repair")
async def vehicles_under_repair(user=Depends(require_user)):
    """Vehicles with open repair tickets (reported/approved/in_repair) — active vehicles only."""
    vmap = await _active_vehicle_map()
    repairs = await db.repairs.find(
        {"status": {"$in": ["reported", "approved", "in_repair"]}}, {"_id": 0}
    ).sort("date", -1).to_list(5000)
    rows = []
    seen = set()
    for r in repairs:
        vid = r["vehicle_id"]
        if vid not in vmap or vid in seen:
            continue
        seen.add(vid)
        v = vmap[vid]
        rows.append({
            "vehicle_id": vid,
            "vehicle_number": v.get("vehicle_number", ""),
            "repair_type": r.get("repair_type"),
            "issue": r.get("issue"),
            "date": r.get("date"),
            "status": r.get("status"),
            "cost": r.get("cost"),
        })
    return rows


@router.get("/service_due")
async def service_due(window: str = "due_or_overdue", user=Depends(require_user)):
    """Service due/overdue list. window: due_soon | overdue | due_or_overdue."""
    today = _today()
    in_15 = (datetime.now(timezone.utc) + timedelta(days=15)).strftime("%Y-%m-%d")
    vmap = await _active_vehicle_map()
    rows = []
    for vid, v in vmap.items():
        latest = await db.services.find({"vehicle_id": vid}, {"_id": 0}).sort("date", -1).to_list(1)
        if not latest:
            continue
        s = latest[0]
        due_date = s.get("next_due_date")
        due_km = s.get("next_due_km")
        odo = v.get("current_odometer") or 0
        is_overdue = (due_date and due_date < today) or (due_km and odo >= due_km)
        is_due_soon = due_date and today <= due_date <= in_15 and not is_overdue
        match = False
        if window == "overdue":
            match = is_overdue
        elif window == "due_soon":
            match = is_due_soon
        else:
            match = is_overdue or is_due_soon
        if not match:
            continue
        rows.append({
            "vehicle_id": vid,
            "vehicle_number": v.get("vehicle_number", ""),
            "last_service_date": s.get("date"),
            "next_due_date": due_date,
            "next_due_km": due_km,
            "current_odometer": odo,
            "status": "OVERDUE" if is_overdue else "DUE SOON",
        })
    rows.sort(key=lambda r: r["next_due_date"] or "9999")
    return rows


@router.get("/top_fuel_consumers")
async def top_fuel_consumers(month: str = None, user=Depends(require_user)):
    """Top fuel consumers for given YYYY-MM (defaults to current month)."""
    if not month:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
    start = f"{month}-01"
    # Compute month end (exclusive)
    y, m = map(int, month.split("-"))
    if m == 12:
        end_y, end_m = y + 1, 1
    else:
        end_y, end_m = y, m + 1
    end_excl = f"{end_y:04d}-{end_m:02d}-01"

    vmap = await _active_vehicle_map()
    fuel = await db.fuel_entries.find(
        {"date": {"$gte": start, "$lt": end_excl}}, {"_id": 0}
    ).to_list(10000)
    agg = {}
    for f in fuel:
        vid = f["vehicle_id"]
        if vid not in vmap:
            continue
        a = agg.setdefault(vid, {"vehicle_id": vid, "vehicle_number": vmap[vid].get("vehicle_number", ""),
                                  "entries": 0, "litres": 0.0, "amount": 0.0})
        a["entries"] += 1
        a["litres"] = round(a["litres"] + (f.get("quantity") or 0), 2)
        a["amount"] = round(a["amount"] + (f.get("amount") or 0), 2)
    rows = sorted(agg.values(), key=lambda r: -r["amount"])
    return rows


@router.get("/top_cost_vehicles")
async def top_cost_vehicles(month: str = None, user=Depends(require_user)):
    """Top operating cost vehicles for given YYYY-MM with category breakdown."""
    if not month:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
    start = f"{month}-01"
    y, m = map(int, month.split("-"))
    if m == 12:
        end_y, end_m = y + 1, 1
    else:
        end_y, end_m = y, m + 1
    end_excl = f"{end_y:04d}-{end_m:02d}-01"
    # gather_expenses uses $lte; emulate exclusive by going one day before
    end_inclusive = (datetime(end_y, end_m, 1, tzinfo=timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    vmap = await _active_vehicle_map()
    rows_raw = await gather_expenses(start_date=start, end_date=end_inclusive)
    agg = {}
    for r in rows_raw:
        vid = r.get("vehicle_id")
        if vid not in vmap:
            continue
        a = agg.setdefault(vid, {"vehicle_id": vid, "vehicle_number": vmap[vid].get("vehicle_number", ""),
                                  "total": 0.0, "by_category": {}})
        a["total"] = round(a["total"] + r["amount"], 2)
        cat = r.get("category", "Other")
        a["by_category"][cat] = round(a["by_category"].get(cat, 0) + r["amount"], 2)
    rows = sorted(agg.values(), key=lambda r: -r["total"])
    return rows


@router.get("/low_mileage_vehicles")
async def low_mileage_vehicles(threshold: float = 5.0, user=Depends(require_user)):
    """Vehicles with average mileage below threshold (km/L). Active vehicles only."""
    vmap = await _active_vehicle_map()
    rows = []
    for vid, v in vmap.items():
        fuel = await db.fuel_entries.find({"vehicle_id": vid, "mileage": {"$ne": None}}, {"_id": 0}).to_list(5000)
        mileages = [f["mileage"] for f in fuel if f.get("mileage")]
        if not mileages:
            continue
        avg = round(sum(mileages) / len(mileages), 2)
        if avg < threshold:
            rows.append({
                "vehicle_id": vid,
                "vehicle_number": v.get("vehicle_number", ""),
                "avg_mileage": avg,
                "entries": len(mileages),
                "fuel_type": v.get("fuel_type"),
            })
    rows.sort(key=lambda r: r["avg_mileage"])
    return rows


@router.get("/licenses_expiring")
async def licenses_expiring(days: int = 30, user=Depends(require_user)):
    """Driver licenses expiring within N days. Excludes resigned/terminated drivers."""
    today = _today()
    target = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")
    drivers = await db.drivers.find({
        "license_expiry": {"$gte": today, "$lte": target},
        "status": {"$nin": ["resigned", "terminated"]},
    }, {"_id": 0}).sort("license_expiry", 1).to_list(3000)
    return [{
        "driver_id": d["id"],
        "name": d["name"],
        "mobile": d.get("mobile"),
        "license_number": d.get("license_number"),
        "license_expiry": d.get("license_expiry"),
        "status": d.get("status"),
    } for d in drivers]


@router.get("/active_trips")
async def active_trips(user=Depends(require_user)):
    """Currently ongoing trips (active vehicles only)."""
    vmap = await _active_vehicle_map()
    _, dmap = await get_lookup_maps()
    trips = await db.trips.find({"status": "ongoing"}, {"_id": 0}).sort("date", -1).to_list(2000)
    rows = []
    for t in trips:
        vid = t.get("vehicle_id")
        if vid not in vmap:
            continue
        rows.append({
            "trip_id": t["id"],
            "vehicle_id": vid,
            "vehicle_number": vmap[vid].get("vehicle_number", ""),
            "driver_id": t.get("driver_id"),
            "driver_name": dmap.get(t.get("driver_id"), ""),
            "date": t.get("date"),
            "origin": t.get("origin"),
            "destination": t.get("destination"),
            "opening_km": t.get("opening_km"),
        })
    return rows
