"""
Vendor Master (Enhancement E3).
Centralized vendor directory used by service / repair / tyre / greasing forms.
"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from database import db
from auth import require_permission, require_module
from models import VendorCreate
from tenant_policy import reject_protected_fields

router = APIRouter(tags=["vendors"])

VENDOR_TYPES = ["Repair", "Tyre", "Showroom", "Breakdown", "Insurance", "Fastag", "Fuel", "Other"]


@router.get("/vendors")
async def list_vendors(request: Request, user=Depends(require_module("vendors"))):
    p = dict(request.query_params)
    q = {}
    include_test = (p.get("include_test") or "").lower() == "true"
    if not (include_test and user.get("role") == "admin"):
        q["is_test_data"] = {"$ne": True}
    if p.get("vendor_type"):
        q["vendor_type"] = p["vendor_type"]
    if p.get("active_only") == "true":
        q["is_active"] = True
    if p.get("all") == "true":
        items = await db.vendors.find(q, {"_id": 0}).sort("name", 1).to_list(2000)
        return items
    page = max(int(p.get("page", 1)), 1)
    page_size = min(max(int(p.get("page_size", 25)), 1), 200)
    total = await db.vendors.count_documents(q)
    items = await db.vendors.find(q, {"_id": 0}).sort("name", 1).skip((page - 1) * page_size).limit(page_size).to_list(page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/vendors")
async def create_vendor(payload: VendorCreate, user=Depends(require_permission("vendors:create"))):
    if user.get("role") in ("driver", "viewer"):
        raise HTTPException(status_code=403, detail="You do not have permission to manage vendors")
    if payload.vendor_type not in VENDOR_TYPES:
        raise HTTPException(status_code=400, detail="Invalid vendor type")
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by"] = user.get("user_id") or user.get("id")
    doc["is_test_data"] = user.get("role") == "test"
    await db.vendors.insert_one({**doc})
    doc.pop("_id", None)
    return doc


@router.put("/vendors/{vid}")
async def update_vendor(vid: str, payload: dict = Body(...),
                        user=Depends(require_permission("vendors:update"))):
    reject_protected_fields(payload)
    if user.get("role") == "test":
        existing = await db.vendors.find_one({"id": vid}, {"_id": 0, "is_test_data": 1})
        if not existing or not existing.get("is_test_data"):
            raise HTTPException(status_code=403, detail="Test mode: cannot modify real vendors")
    if payload.get("vendor_type") and payload["vendor_type"] not in VENDOR_TYPES:
        raise HTTPException(status_code=400, detail="Invalid vendor type")
    res = await db.vendors.update_one({"id": vid}, {"$set": payload})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return await db.vendors.find_one({"id": vid}, {"_id": 0})


@router.delete("/vendors/{vid}")
async def delete_vendor(vid: str, user=Depends(require_permission("vendors:delete"))):
    if user.get("role") == "test":
        existing = await db.vendors.find_one({"id": vid}, {"_id": 0, "is_test_data": 1})
        if not existing or not existing.get("is_test_data"):
            raise HTTPException(status_code=403, detail="Test mode: cannot delete real vendors")
    await db.vendors.delete_one({"id": vid})
    return {"ok": True}
