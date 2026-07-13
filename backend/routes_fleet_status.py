"""Fleet Status Board (E4) — live status per vehicle (running/idle/under-repair/downtime/disposed)."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from database import db
from auth import require_user, require_module

router = APIRouter(tags=["fleet-status"])

DISPOSED_STATUSES = ["sold", "scrapped"]
OPEN_TICKET_STATUSES = ["open", "under_review", "approved", "sent_for_repair", "in_repair", "repaired", "reported"]


def _now():
    return datetime.now(timezone.utc)


@router.get("/fleet-status")
async def fleet_status(user=Depends(require_module("fleet-status"))):
    vehicles = await db.vehicles.find(
        {"is_test_data": {"$ne": True}}, {"_id": 0}
    ).sort("vehicle_number", 1).to_list(3000)

    drivers = {d["id"]: d for d in await db.drivers.find(
        {"is_test_data": {"$ne": True}}, {"_id": 0}).to_list(3000)}

    trip_by_vehicle = {}
    for t in await db.trips.find(
        {"status": "ongoing", "is_test_data": {"$ne": True}}, {"_id": 0}).to_list(3000):
        trip_by_vehicle[t["vehicle_id"]] = t

    ticket_by_vehicle = {}
    for t in await db.repairs.find(
        {"status": {"$in": OPEN_TICKET_STATUSES}, "is_test_data": {"$ne": True}},
        {"_id": 0}).sort("date", -1).to_list(3000):
        ticket_by_vehicle.setdefault(t["vehicle_id"], t)

    downtime_by_vehicle = {d["vehicle_id"]: d for d in await db.downtimes.find(
        {"status": "open", "is_test_data": {"$ne": True}}, {"_id": 0}).to_list(3000)}

    rows = []
    for v in vehicles:
        if v.get("status") in DISPOSED_STATUSES:
            status = "DISPOSED"
            detail = {"disposition": v.get("status"), "disposal_date": v.get("disposal_date")}
        elif v["id"] in ticket_by_vehicle:
            t = ticket_by_vehicle[v["id"]]
            status = "UNDER_REPAIR"
            detail = {
                "ticket_number": t.get("ticket_number") or t["id"][:8],
                "ticket_status": t.get("status"),
                "issue": t.get("issue"),
                "ticket_date": t.get("date"),
            }
        elif v["id"] in downtime_by_vehicle:
            dt = downtime_by_vehicle[v["id"]]
            days_since = None
            try:
                start = datetime.fromisoformat(dt["start_date"])
                days_since = max((_now() - start.replace(tzinfo=timezone.utc)).days, 0)
            except (ValueError, TypeError):
                pass
            status = "DOWNTIME"
            detail = {"reason": dt.get("reason"), "start_date": dt.get("start_date"), "days_since": days_since}
        elif v["id"] in trip_by_vehicle:
            t = trip_by_vehicle[v["id"]]
            driver = drivers.get(t.get("driver_id"))
            status = "RUNNING"
            detail = {
                "driver_id": t.get("driver_id"),
                "driver_name": driver["name"] if driver else None,
                "destination": t.get("destination"),
                "origin": t.get("origin"),
                "trip_date": t.get("date"),
                "opening_km": t.get("opening_km"),
            }
        else:
            status = "IDLE"
            detail = {}

        rows.append({
            "vehicle_id": v["id"],
            "vehicle_number": v["vehicle_number"],
            "vtype": v.get("vtype"),
            "current_odometer": v.get("current_odometer"),
            "status": status,
            "detail": detail,
        })

    counts = {"RUNNING": 0, "IDLE": 0, "UNDER_REPAIR": 0, "DOWNTIME": 0, "DISPOSED": 0}
    for r in rows:
        counts[r["status"]] += 1

    return {"rows": rows, "counts": counts, "total": len(rows), "as_of": _now().isoformat()}
