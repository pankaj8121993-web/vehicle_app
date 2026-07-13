"""Fleet Calendar — auto-aggregated + custom events (CP3 §4.2)."""
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Body, Depends, HTTPException
from database import db
from auth import require_user, require_role, require_module
from models import CalendarEventCreate

router = APIRouter(tags=["calendar"])

DISPOSED_STATUSES = ["sold", "scrapped"]
EXITED_DRIVER_STATUSES = ["resigned", "terminated"]
OPEN_TICKET_STATUSES = ["open", "under_review", "approved", "sent_for_repair", "in_repair", "repaired",
                       "reported"]  # include legacy "reported" for backwards compat


def _now():
    return datetime.now(timezone.utc)


def _today():
    return _now().strftime("%Y-%m-%d")


def _severity_from_date(target):
    if not target:
        return "info"
    today = _today()
    if target < today:
        return "danger"
    try:
        td = datetime.fromisoformat(target).date()
        diff = (td - _now().date()).days
    except (ValueError, TypeError):
        return "info"
    if diff <= 15:
        return "warning"
    return "info"


def _expand_recurrence(event, start, end):
    """Expand a custom event with recurrence into one occurrence per matching date in [start, end]."""
    base = event["date"]
    rec = event.get("recurrence")
    cap = event.get("recurrence_until") or end
    if not rec:
        return [event] if start <= base <= end else []
    try:
        cur = datetime.fromisoformat(base).date()
        cap_d = datetime.fromisoformat(cap).date()
        start_d = datetime.fromisoformat(start).date()
        end_d = datetime.fromisoformat(end).date()
    except (ValueError, TypeError):
        return [event]
    out = []
    steps = 0
    while cur <= cap_d and cur <= end_d and steps < 365:
        if cur >= start_d:
            o = dict(event)
            o["date"] = cur.isoformat()
            out.append(o)
        if rec == "weekly":
            cur += timedelta(days=7)
        elif rec == "monthly":
            # naive month increment
            m = cur.month + 1
            y = cur.year + (1 if m > 12 else 0)
            m = ((m - 1) % 12) + 1
            try:
                cur = cur.replace(year=y, month=m)
            except ValueError:
                cur = cur.replace(year=y, month=m, day=28)
        elif rec == "yearly":
            try:
                cur = cur.replace(year=cur.year + 1)
            except ValueError:
                cur = cur.replace(year=cur.year + 1, day=28)
        else:
            break
        steps += 1
    return out


@router.get("/calendar")
async def calendar(start: str, end: str, user=Depends(require_module("calendar"))):
    events = []

    vmap = {v["id"]: v for v in await db.vehicles.find(
        {"is_test_data": {"$ne": True}}, {"_id": 0}).to_list(3000)}
    dmap = {d["id"]: d for d in await db.drivers.find(
        {"is_test_data": {"$ne": True}}, {"_id": 0}).to_list(3000)}
    active_vids = {vid for vid, v in vmap.items() if v.get("status") not in DISPOSED_STATUSES}

    # 1. Documents — latest per (vehicle_id, doc_type)
    docs = await db.documents.find(
        {"expiry_date": {"$gte": start, "$lte": end}, "is_test_data": {"$ne": True}}, {"_id": 0}
    ).to_list(5000)
    latest = {}
    for d in docs:
        if d["vehicle_id"] not in active_vids:
            continue
        k = (d["vehicle_id"], d["doc_type"])
        if k not in latest or (d.get("expiry_date") or "") > (latest[k].get("expiry_date") or ""):
            latest[k] = d
    for d in latest.values():
        v = vmap[d["vehicle_id"]]
        events.append({
            "id": f"auto-doc-{d['id']}", "title": f"{d['doc_type']} — {v.get('vehicle_number','')}",
            "date": d["expiry_date"], "time": None, "type": "doc_expiry",
            "severity": _severity_from_date(d["expiry_date"]),
            "vehicle_id": d["vehicle_id"], "vehicle_number": v.get("vehicle_number"),
            "driver_id": None, "driver_name": None, "responsible_person": None,
            "notes": d.get("doc_number"), "is_auto": True, "source_id": d["id"],
        })

    # 2. Driver licenses
    for dv in await db.drivers.find(
        {"status": {"$nin": EXITED_DRIVER_STATUSES}, "is_test_data": {"$ne": True},
         "license_expiry": {"$gte": start, "$lte": end}}, {"_id": 0}).to_list(3000):
        events.append({
            "id": f"auto-license-{dv['id']}", "title": f"License — {dv['name']}",
            "date": dv["license_expiry"], "time": None, "type": "license_expiry",
            "severity": _severity_from_date(dv["license_expiry"]),
            "vehicle_id": None, "vehicle_number": None,
            "driver_id": dv["id"], "driver_name": dv["name"],
            "responsible_person": None, "notes": dv.get("license_number"),
            "is_auto": True, "source_id": dv["id"],
        })

    # 3. Services + 4. Greasings — latest per active vehicle, next_due_date in window
    for coll, etype in (("services", "service_due"), ("greasings", "greasing_due")):
        for vid in active_vids:
            latest_x = await db[coll].find({"vehicle_id": vid}, {"_id": 0}).sort("date", -1).to_list(1)
            if not latest_x:
                continue
            s = latest_x[0]
            due = s.get("next_due_date")
            if not due or due < start or due > end:
                continue
            v = vmap[vid]
            events.append({
                "id": f"auto-{etype}-{s['id']}", "title": f"{'Service' if etype == 'service_due' else 'Greasing'} — {v.get('vehicle_number','')}",
                "date": due, "time": None, "type": etype,
                "severity": _severity_from_date(due),
                "vehicle_id": vid, "vehicle_number": v.get("vehicle_number"),
                "driver_id": None, "driver_name": None, "responsible_person": None,
                "notes": None, "is_auto": True, "source_id": s["id"],
            })

    # 5. Downtimes — open in window
    for dt in await db.downtimes.find(
        {"status": "open", "is_test_data": {"$ne": True},
         "start_date": {"$gte": start, "$lte": end}}, {"_id": 0}).to_list(2000):
        if dt["vehicle_id"] not in active_vids:
            continue
        v = vmap[dt["vehicle_id"]]
        events.append({
            "id": f"auto-downtime-{dt['id']}", "title": f"Downtime ({dt.get('reason')}) — {v.get('vehicle_number','')}",
            "date": dt["start_date"], "time": None, "type": "downtime_open",
            "severity": "warning",
            "vehicle_id": dt["vehicle_id"], "vehicle_number": v.get("vehicle_number"),
            "driver_id": None, "driver_name": None, "responsible_person": None,
            "notes": dt.get("notes"), "is_auto": True, "source_id": dt["id"],
        })

    # 6. Tickets — non-closed in window
    for t in await db.repairs.find(
        {"status": {"$in": OPEN_TICKET_STATUSES}, "is_test_data": {"$ne": True},
         "date": {"$gte": start, "$lte": end}}, {"_id": 0}).to_list(2000):
        if t["vehicle_id"] not in active_vids:
            continue
        v = vmap[t["vehicle_id"]]
        events.append({
            "id": f"auto-ticket-{t['id']}", "title": f"Ticket #{t.get('ticket_number') or t['id'][:8]} — {v.get('vehicle_number','')}",
            "date": t["date"], "time": None, "type": "ticket_open",
            "severity": "warning",
            "vehicle_id": t["vehicle_id"], "vehicle_number": v.get("vehicle_number"),
            "driver_id": None, "driver_name": None, "responsible_person": None,
            "notes": t.get("issue"), "is_auto": True, "source_id": t["id"],
        })

    # 7. Accidents
    for a in await db.accidents.find(
        {"is_test_data": {"$ne": True}, "date": {"$gte": start, "$lte": end}}, {"_id": 0}).to_list(2000):
        v = vmap.get(a["vehicle_id"], {})
        events.append({
            "id": f"auto-accident-{a['id']}", "title": f"Accident — {v.get('vehicle_number','')}",
            "date": a["date"], "time": a.get("time"), "type": "accident",
            "severity": "info",
            "vehicle_id": a["vehicle_id"], "vehicle_number": v.get("vehicle_number"),
            "driver_id": a.get("driver_id"),
            "driver_name": dmap.get(a.get("driver_id"), {}).get("name") if a.get("driver_id") else None,
            "responsible_person": None, "notes": a.get("description"),
            "is_auto": True, "source_id": a["id"],
        })

    # 8. Disposed vehicles
    for v in vmap.values():
        if v.get("status") in DISPOSED_STATUSES and v.get("disposal_date") and start <= v["disposal_date"] <= end:
            events.append({
                "id": f"auto-disposal-{v['id']}", "title": f"Disposed — {v.get('vehicle_number','')}",
                "date": v["disposal_date"], "time": None, "type": "vehicle_disposed",
                "severity": "muted",
                "vehicle_id": v["id"], "vehicle_number": v.get("vehicle_number"),
                "driver_id": None, "driver_name": None, "responsible_person": None,
                "notes": v.get("disposal_remarks"), "is_auto": True, "source_id": v["id"],
            })

    # 9. Driver exits
    for dv in dmap.values():
        if dv.get("status") in EXITED_DRIVER_STATUSES and dv.get("exit_date") and start <= dv["exit_date"] <= end:
            events.append({
                "id": f"auto-driverexit-{dv['id']}", "title": f"Exited — {dv['name']}",
                "date": dv["exit_date"], "time": None, "type": "driver_exit",
                "severity": "muted",
                "vehicle_id": None, "vehicle_number": None,
                "driver_id": dv["id"], "driver_name": dv["name"],
                "responsible_person": None, "notes": dv.get("exit_reason"),
                "is_auto": True, "source_id": dv["id"],
            })

    # 10. Custom calendar events (with recurrence)
    custom = await db.calendar_events.find(
        {"is_test_data": {"$ne": True}}, {"_id": 0}).to_list(2000)
    for e in custom:
        for occ in _expand_recurrence(e, start, end):
            v = vmap.get(occ.get("vehicle_id"), {}) if occ.get("vehicle_id") else {}
            dv = dmap.get(occ.get("driver_id"), {}) if occ.get("driver_id") else {}
            events.append({
                "id": e["id"], "title": e["title"], "date": occ["date"], "time": e.get("time"),
                "type": "custom", "severity": "info",
                "vehicle_id": e.get("vehicle_id"), "vehicle_number": v.get("vehicle_number") if v else None,
                "driver_id": e.get("driver_id"), "driver_name": dv.get("name") if dv else None,
                "responsible_person": e.get("responsible_person"),
                "notes": e.get("notes"), "is_auto": False, "source_id": e["id"],
            })

    events.sort(key=lambda x: (x["date"], x.get("time") or "00:00"))
    return {"events": events}


@router.post("/calendar/events")
async def create_event(payload: CalendarEventCreate,
                        user=Depends(require_role("data_entry", "management", "admin", "test"))):
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = _now().isoformat()
    doc["created_by"] = user["id"]
    doc["is_test_data"] = user.get("role") == "test"
    await db.calendar_events.insert_one({**doc})
    doc.pop("_id", None)
    return doc


@router.put("/calendar/events/{eid}")
async def update_event(eid: str, payload: dict = Body(...),
                        user=Depends(require_role("data_entry", "management", "admin", "test"))):
    payload = {k: v for k, v in payload.items() if k not in ("id", "_id", "created_at", "created_by", "is_test_data")}
    if user.get("role") == "test":
        existing = await db.calendar_events.find_one({"id": eid}, {"_id": 0, "is_test_data": 1})
        if not existing or not existing.get("is_test_data"):
            raise HTTPException(status_code=403, detail="Test mode: cannot modify real records")
    res = await db.calendar_events.update_one({"id": eid}, {"$set": payload})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    return await db.calendar_events.find_one({"id": eid}, {"_id": 0})


@router.delete("/calendar/events/{eid}")
async def delete_event(eid: str, user=Depends(require_role("admin", "test"))):
    if user.get("role") == "test":
        existing = await db.calendar_events.find_one({"id": eid}, {"_id": 0, "is_test_data": 1})
        if not existing or not existing.get("is_test_data"):
            raise HTTPException(status_code=403, detail="Test mode: cannot delete real records")
    await db.calendar_events.delete_one({"id": eid})
    return {"ok": True}
