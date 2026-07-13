"""
Compliance & Expiry Alerts (Phase 2) + Compliance Contacts (E2).
"""
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Body, Depends, HTTPException
from database import db
from auth import require_user, require_role, require_module
from models import ComplianceContactCreate

router = APIRouter(tags=["compliance"])

DISPOSED_STATUSES = ["sold", "scrapped"]
EXITED_DRIVER_STATUSES = ["resigned", "terminated"]
COMPLIANCE_TYPES = ["RC", "Insurance", "Fitness", "Permit", "PUC", "Road Tax", "Fastag", "License", "Other"]


def _now():
    return datetime.now(timezone.utc)


def _today_iso():
    return _now().strftime("%Y-%m-%d")


def _severity(days_remaining):
    if days_remaining is None:
        return "info"
    if days_remaining < 0 or days_remaining <= 7:
        return "danger"
    if days_remaining <= 30:
        return "warning"
    return "info"


def _days_between(target_iso):
    if not target_iso:
        return None
    try:
        td = datetime.fromisoformat(target_iso).date()
        return (td - _now().date()).days
    except (ValueError, TypeError):
        return None


@router.get("/compliance")
async def compliance_overview(severity: str = "all", vehicle_id: str = None,
                              days_ahead: int = 90, user=Depends(require_module("compliance"))):
    today = _today_iso()
    horizon = (_now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    # Active vehicles map (excludes disposed + test data)
    vfilter = {"status": {"$nin": DISPOSED_STATUSES}, "is_test_data": {"$ne": True}}
    if vehicle_id:
        vfilter["id"] = vehicle_id
    vehicles = await db.vehicles.find(vfilter, {"_id": 0}).to_list(3000)
    vmap = {v["id"]: v for v in vehicles}

    # Documents — latest per (vehicle_id, doc_type)
    docs = await db.documents.find(
        {"expiry_date": {"$ne": None}, "is_test_data": {"$ne": True}}, {"_id": 0}
    ).to_list(5000)
    latest = {}
    for d in docs:
        if d["vehicle_id"] not in vmap:
            continue
        k = (d["vehicle_id"], d["doc_type"])
        if k not in latest or (d.get("expiry_date") or "") > (latest[k].get("expiry_date") or ""):
            latest[k] = d
    documents = []
    for d in latest.values():
        if d["expiry_date"] > horizon:
            continue
        v = vmap[d["vehicle_id"]]
        dr = _days_between(d["expiry_date"])
        documents.append({
            "vehicle_id": d["vehicle_id"], "vehicle_number": v.get("vehicle_number", ""),
            "doc_type": d["doc_type"], "doc_number": d.get("doc_number"),
            "expiry_date": d["expiry_date"], "days_remaining": dr, "severity": _severity(dr),
        })
    documents.sort(key=lambda r: r["expiry_date"])

    # Licenses — active + on_leave drivers only, excluding test
    drivers = await db.drivers.find(
        {"status": {"$nin": EXITED_DRIVER_STATUSES}, "is_test_data": {"$ne": True},
         "license_expiry": {"$ne": None}}, {"_id": 0}
    ).to_list(3000)
    licenses = []
    for dv in drivers:
        if dv["license_expiry"] > horizon:
            continue
        dr = _days_between(dv["license_expiry"])
        licenses.append({
            "driver_id": dv["id"], "name": dv["name"],
            "employee_number": dv.get("employee_number"),
            "license_number": dv.get("license_number"),
            "license_expiry": dv["license_expiry"],
            "days_remaining": dr, "severity": _severity(dr),
        })
    licenses.sort(key=lambda r: r["license_expiry"])

    # Services + greasings: latest per vehicle, alert if due_date <= 30d or odometer >= due_km
    services = []
    greasings = []
    for v in vehicles:
        for coll, target_list in (("services", services), ("greasings", greasings)):
            latest_x = await db[coll].find({"vehicle_id": v["id"]}, {"_id": 0}).sort("date", -1).to_list(1)
            if not latest_x:
                continue
            s = latest_x[0]
            due_date = s.get("next_due_date")
            due_km = s.get("next_due_km")
            odo = v.get("current_odometer") or 0
            is_overdue = (due_date and due_date < today) or (due_km and odo >= due_km)
            is_soon = due_date and today <= due_date <= horizon
            if not (is_overdue or is_soon):
                continue
            dr = _days_between(due_date)
            target_list.append({
                "vehicle_id": v["id"], "vehicle_number": v["vehicle_number"],
                "last_date": s.get("date"), "next_due_date": due_date,
                "next_due_km": due_km, "current_odometer": odo,
                "days_remaining": dr, "severity": "danger" if is_overdue else _severity(dr),
            })
    services.sort(key=lambda r: r["next_due_date"] or "9999")
    greasings.sort(key=lambda r: r["next_due_date"] or "9999")

    # Fastag low balance
    fastag_low = []
    for v in vehicles:
        if v.get("fastag_number") and (v.get("fastag_balance") or 0) < 500:
            fastag_low.append({
                "vehicle_id": v["id"], "vehicle_number": v["vehicle_number"],
                "fastag_number": v["fastag_number"],
                "balance": v.get("fastag_balance") or 0,
                "severity": "danger" if (v.get("fastag_balance") or 0) < 200 else "warning",
            })

    all_items = documents + licenses + services + greasings + fastag_low

    def _sev_filter(rows):
        if severity == "all":
            return rows
        return [r for r in rows if r.get("severity") == severity]

    summary = {
        "total_items": len(all_items),
        "expired": sum(1 for r in all_items if (r.get("days_remaining") or 999) < 0),
        "expiring_7": sum(1 for r in all_items if r.get("days_remaining") is not None and 0 <= r["days_remaining"] <= 7),
        "expiring_30": sum(1 for r in all_items if r.get("days_remaining") is not None and 0 <= r["days_remaining"] <= 30),
        "expiring_90": sum(1 for r in all_items if r.get("days_remaining") is not None and 0 <= r["days_remaining"] <= 90),
    }

    return {
        "documents": _sev_filter(documents),
        "licenses": _sev_filter(licenses),
        "services": _sev_filter(services),
        "greasings": _sev_filter(greasings),
        "fastag_low": _sev_filter(fastag_low),
        "summary": summary,
    }


# ---------- Compliance Contacts (E2) ----------

@router.get("/compliance/contacts")
async def list_contacts(user=Depends(require_module("compliance"))):
    items = await db.compliance_contacts.find(
        {"is_test_data": {"$ne": True}}, {"_id": 0}
    ).sort("compliance_type", 1).to_list(500)
    return items


@router.post("/compliance/contacts")
async def create_contact(payload: ComplianceContactCreate,
                          user=Depends(require_role("management", "admin"))):
    if payload.compliance_type not in COMPLIANCE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid compliance type")
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = _now().isoformat()
    doc["created_by"] = user["id"]
    doc["is_test_data"] = user.get("role") == "test"
    await db.compliance_contacts.insert_one({**doc})
    doc.pop("_id", None)
    return doc


@router.put("/compliance/contacts/{cid}")
async def update_contact(cid: str, payload: dict = Body(...),
                          user=Depends(require_role("management", "admin"))):
    payload = {k: v for k, v in payload.items() if k not in ("id", "_id", "created_at", "created_by", "is_test_data")}
    res = await db.compliance_contacts.update_one({"id": cid}, {"$set": payload})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Contact not found")
    return await db.compliance_contacts.find_one({"id": cid}, {"_id": 0})


@router.delete("/compliance/contacts/{cid}")
async def delete_contact(cid: str, user=Depends(require_role("admin"))):
    await db.compliance_contacts.delete_one({"id": cid})
    return {"ok": True}
