"""Organisation onboarding, profile, branches, setup checklist and demo environment."""
import re
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Body, Depends, HTTPException
from passlib.hash import bcrypt
from database import db, raw_db, current_org_id
from auth import require_user, require_role, create_session, ROLES, allowed_modules
from models import OrgRegister
from tenant_policy import reject_protected_fields
import demo_seed

router = APIRouter(tags=["organisations"])

ORG_TYPES = [
    "Company", "Proprietorship", "Partnership", "LLP", "Private Limited Company",
    "Public Limited Company", "Trust or Institution", "Transport Operator",
    "Logistics Business", "Individual Fleet Owner", "Other",
]
FLEET_OWNERSHIP = ["Owned", "Leased", "Hired", "Rented", "Attached", "Mixed"]


def _now():
    return datetime.now(timezone.utc)


# ---------- Onboarding ----------

@router.post("/onboarding/register")
async def register_org(payload: OrgRegister):
    org = payload.org or {}
    admin = payload.admin or {}

    legal_name = (org.get("legal_name") or "").strip()
    org_type = org.get("org_type") or ""
    if not legal_name:
        raise HTTPException(status_code=400, detail="Organisation legal name is required")
    if org_type not in ORG_TYPES:
        raise HTTPException(status_code=400, detail="Invalid organisation type")

    username = (admin.get("username") or "").lower().strip()
    email = (admin.get("email") or "").lower().strip()
    password = admin.get("password") or ""
    full_name = (admin.get("full_name") or "").strip()
    if not re.fullmatch(r"[a-z0-9._-]{3,40}", username):
        raise HTTPException(status_code=400, detail="Username must be 3-40 chars (letters, numbers, . _ -)")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=400, detail="A valid administrator email is required")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if not full_name:
        raise HTTPException(status_code=400, detail="Administrator full name is required")

    # Global uniqueness (across every organisation)
    if await raw_db.users.find_one({"username": username}):
        raise HTTPException(status_code=400, detail="Username is already taken")
    if await raw_db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="An account with this email already exists")
    if await raw_db.organizations.find_one({"legal_name_lc": legal_name.lower()}):
        raise HTTPException(status_code=400, detail="An organisation with this name is already registered")

    org_id = str(uuid.uuid4())
    org_doc = {
        "id": org_id,
        "legal_name": legal_name,
        "legal_name_lc": legal_name.lower(),
        "trade_name": org.get("trade_name") or legal_name,
        "org_type": org_type,
        "fleet_ownership": org.get("fleet_ownership") if org.get("fleet_ownership") in FLEET_OWNERSHIP else "Owned",
        "industry": org.get("industry"),
        "gstin": org.get("gstin"),
        "pan": org.get("pan"),
        "cin": org.get("cin"),
        "email": org.get("email"),
        "phone": org.get("phone"),
        "website": org.get("website"),
        "year_established": org.get("year_established"),
        "employee_count": org.get("employee_count"),
        "address": org.get("address") or {},
        "country": org.get("country") or "India",
        "state": org.get("state"),
        "city": org.get("city"),
        "currency": org.get("currency") or "INR",
        "timezone": org.get("timezone") or "Asia/Kolkata",
        "fy_start_month": org.get("fy_start_month") or 4,
        "fleet_profile": payload.fleet_profile or {},
        "preferences": payload.preferences or {},
        "compliance_docs": payload.compliance_docs or ["RC", "Insurance", "Fitness", "Permit", "PUC", "Road Tax"],
        "reminder_days": org.get("reminder_days") or 30,
        "is_demo": False,
        "is_default": False,
        "onboarding_completed": True,
        "created_at": _now().isoformat(),
    }
    await raw_db.organizations.insert_one(org_doc)

    user_id = str(uuid.uuid4())
    await raw_db.users.insert_one({
        "id": user_id,
        "org_id": org_id,
        "username": username,
        "email": email,
        "password_hash": bcrypt.hash(password),
        "role": "org_admin",
        "full_name": full_name,
        "designation": admin.get("designation"),
        "mobile": admin.get("mobile"),
        "is_active": True,
        "is_demo": False,
        "must_change_password": False,
        "created_at": _now().isoformat(),
        "created_by": "onboarding",
    })

    branch = payload.branch or {}
    await raw_db.branches.insert_one({
        "id": str(uuid.uuid4()),
        "org_id": org_id,
        "name": branch.get("name") or "Head Office",
        "code": branch.get("code") or "HO",
        "address": branch.get("address"),
        "contact_person": branch.get("contact_person") or full_name,
        "phone": branch.get("phone") or admin.get("mobile"),
        "email": branch.get("email") or email,
        "is_default": True,
        "created_at": _now().isoformat(),
    })

    token = await create_session(user_id)
    return {
        "token": token,
        "user": {
            "id": user_id, "username": username, "full_name": full_name,
            "role": "org_admin", "must_change_password": False,
            "org_id": org_id, "org_name": org_doc["trade_name"], "is_demo": False,
            "modules": allowed_modules("org_admin"),
        },
    }


# ---------- Organisation profile ----------

@router.get("/org")
async def get_org(user=Depends(require_user)):
    org = await raw_db.organizations.find_one({"id": user.get("org_id")}, {"_id": 0, "legal_name_lc": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    branches = await db.branches.find({}, {"_id": 0}).sort("name", 1).to_list(200)
    return {**org, "branches": branches}


@router.put("/org")
async def update_org(payload: dict = Body(...), user=Depends(require_role("admin", "management"))):
    if user.get("is_demo"):
        raise HTTPException(status_code=403, detail="Demo users cannot change organisation settings")
    reject_protected_fields(payload)
    allowed = {
        "trade_name", "industry", "gstin", "pan", "cin", "email", "phone", "website",
        "year_established", "employee_count", "address", "country", "state", "city",
        "currency", "fy_start_month", "preferences", "compliance_docs", "reminder_days",
        "logo_file_id",
    }
    updates = {k: v for k, v in payload.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    await raw_db.organizations.update_one({"id": user["org_id"]}, {"$set": updates})
    return await raw_db.organizations.find_one({"id": user["org_id"]}, {"_id": 0, "legal_name_lc": 0})


# ---------- Branches ----------

@router.get("/branches")
async def list_branches(user=Depends(require_user)):
    return await db.branches.find({}, {"_id": 0}).sort("name", 1).to_list(200)


@router.post("/branches")
async def create_branch(payload: dict = Body(...), user=Depends(require_role("admin", "management"))):
    reject_protected_fields(payload)
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Branch name is required")
    doc = {
        "id": str(uuid.uuid4()),
        "name": name,
        "code": payload.get("code"),
        "address": payload.get("address"),
        "contact_person": payload.get("contact_person"),
        "phone": payload.get("phone"),
        "email": payload.get("email"),
        "is_default": False,
        "created_at": _now().isoformat(),
    }
    await db.branches.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/branches/{bid}")
async def update_branch(bid: str, payload: dict = Body(...), user=Depends(require_role("admin", "management"))):
    reject_protected_fields(payload)
    updates = {k: v for k, v in payload.items() if k in ("name", "code", "address", "contact_person", "phone", "email")}
    res = await db.branches.update_one({"id": bid}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Branch not found")
    return await db.branches.find_one({"id": bid}, {"_id": 0})


@router.delete("/branches/{bid}")
async def delete_branch(bid: str, user=Depends(require_role("admin"))):
    branch = await db.branches.find_one({"id": bid}, {"_id": 0})
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    if branch.get("is_default"):
        raise HTTPException(status_code=400, detail="Cannot delete the default branch")
    await db.branches.delete_one({"id": bid})
    return {"ok": True}


# ---------- Setup checklist ----------

@router.get("/onboarding/checklist")
async def setup_checklist(user=Depends(require_user)):
    org = await raw_db.organizations.find_one({"id": user.get("org_id")}, {"_id": 0}) or {}
    vehicles = await db.vehicles.count_documents({})
    drivers = await db.drivers.count_documents({})
    vendors = await db.vendors.count_documents({})
    users = await db.users.count_documents({})
    trips = await db.trips.count_documents({})
    docs = await db.documents.count_documents({})
    items = [
        {"key": "profile", "label": "Complete organisation profile", "done": bool(org.get("gstin") or org.get("pan") or org.get("phone"))},
        {"key": "logo", "label": "Add your logo", "done": bool(org.get("logo_file_id"))},
        {"key": "vehicle", "label": "Add your first vehicle", "done": vehicles > 0},
        {"key": "driver", "label": "Add your first driver", "done": drivers > 0},
        {"key": "vendor", "label": "Add your first vendor", "done": vendors > 0},
        {"key": "compliance", "label": "Upload compliance documents", "done": docs > 0},
        {"key": "users", "label": "Invite your team", "done": users > 1},
        {"key": "trip", "label": "Record your first trip", "done": trips > 0},
    ]
    return {"items": items, "completed": sum(1 for i in items if i["done"]), "total": len(items),
            "dismissed": bool(org.get("checklist_dismissed"))}


@router.post("/onboarding/checklist/dismiss")
async def dismiss_checklist(user=Depends(require_user)):
    await raw_db.organizations.update_one({"id": user["org_id"]}, {"$set": {"checklist_dismissed": True}})
    return {"ok": True}


# ---------- Demo environment ----------

DEMO_ROLES = {
    "org_admin": "Organisation Super Admin",
    "owner": "Owner / Management",
    "fleet_manager": "Fleet Manager",
    "operations": "Operations User",
    "maintenance": "Maintenance Manager",
    "driver": "Driver",
    "accounts": "Accounts User",
    "viewer": "Auditor / Viewer",
}


@router.get("/demo/roles")
async def demo_roles():
    return [{"role": r, "label": l} for r, l in DEMO_ROLES.items()]


@router.post("/demo/enter")
async def enter_demo(payload: dict = Body(...)):
    role = payload.get("role")
    if role not in DEMO_ROLES:
        raise HTTPException(status_code=400, detail="Invalid demo role")
    await demo_seed.ensure_demo()
    duser = await raw_db.users.find_one({"username": f"demo_{role}", "is_demo": True})
    if not duser:
        raise HTTPException(status_code=500, detail="Demo user not available")
    token = await create_session(duser["id"])
    return {
        "token": token,
        "user": {
            "id": duser["id"], "username": duser["username"], "full_name": duser["full_name"],
            "role": duser["role"], "must_change_password": False,
            "org_id": duser["org_id"], "org_name": "FleetFlow Demo Logistics", "is_demo": True,
            "modules": allowed_modules(duser["role"]),
        },
    }
