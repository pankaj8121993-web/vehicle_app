import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from database import db
from auth import require_user, require_permission, MODULE_ACCESS
from tenant_policy import reject_protected_fields
import workflow


def _check_module(user, module):
    if not module:
        return
    role = user.get("actual_role") or user.get("role")
    if role not in MODULE_ACCESS.get(module, set()):
        raise HTTPException(status_code=403, detail="Your role does not have access to this module")


async def get_lookup_maps():
    vmap = {v["id"]: v.get("vehicle_number", "") for v in await db.vehicles.find({}, {"_id": 0, "id": 1, "vehicle_number": 1}).to_list(2000)}
    dmap = {d["id"]: d.get("name", "") for d in await db.drivers.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(2000)}
    return vmap, dmap


async def enrich(items):
    vmap, dmap = await get_lookup_maps()
    for it in items:
        if it.get("vehicle_id"):
            it["vehicle_number"] = vmap.get(it["vehicle_id"], "")
        if it.get("driver_id"):
            it["driver_name"] = dmap.get(it["driver_id"], "")
    return items


def make_crud(router: APIRouter, path: str, coll: str, CreateModel, date_field: str = "date", on_create=None, driver_can_create: bool = False, module: str = None, perm_resource: str = None):
    # AUTHZ-01: the permission resource is the path with hyphens normalised
    # ("tyre-events" -> "tyre_events"), matching permissions.CRUD_RESOURCES.
    # driver_can_create is retained only for signature compatibility; the driver
    # create allowlist now lives in the permission catalogue.
    perm = perm_resource or path.replace("-", "_")

    @router.get(f"/{path}")
    async def list_items(request: Request, user=Depends(require_user)):
        _check_module(user, module)
        p = dict(request.query_params)
        q = {}
        for key in ("vehicle_id", "driver_id", "tyre_id", "category", "status", "doc_type"):
            if p.get(key):
                q[key] = p[key]
        if p.get("start_date"):
            q[date_field] = {"$gte": p["start_date"]}
        if p.get("end_date"):
            q.setdefault(date_field, {})
            q[date_field]["$lte"] = p["end_date"]
        # is_test_data default-exclude (admins can opt-in via ?include_test=true)
        include_test = (p.get("include_test") or "").lower() == "true"
        if not (include_test and user.get("role") == "admin"):
            q["is_test_data"] = {"$ne": True}
        if p.get("all") == "true":
            items = await db[coll].find(q, {"_id": 0}).sort(date_field, -1).to_list(3000)
            return await enrich(items)
        page = max(int(p.get("page", 1)), 1)
        page_size = min(max(int(p.get("page_size", 25)), 1), 200)
        total = await db[coll].count_documents(q)
        items = await db[coll].find(q, {"_id": 0}).sort(date_field, -1).skip((page - 1) * page_size).limit(page_size).to_list(page_size)
        return {"items": await enrich(items), "total": total, "page": page, "page_size": page_size}

    @router.post(f"/{path}")
    async def create_item(payload: CreateModel, user=Depends(require_permission(f"{perm}:create"))):
        doc = payload.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        doc["created_by"] = user["user_id"]
        doc["is_test_data"] = user.get("role") == "test"
        if on_create:
            doc = await on_create(doc)
        await db[coll].insert_one({**doc})
        doc.pop("_id", None)
        return doc

    @router.put(f"/{path}/{{item_id}}")
    async def update_item(item_id: str, payload: dict = Body(...), user=Depends(require_permission(f"{perm}:update"))):
        reject_protected_fields(payload)
        # WF-01: a generic update must not be a way around a workflow. If this
        # collection's status is workflow-controlled and the payload changes it,
        # the change is validated against the state graph (invalid → 409) before
        # anything is written. Needs the existing record, so read it up front for
        # workflow-controlled collections.
        needs_existing = "status" in payload and coll in workflow.STATUS_WORKFLOWS
        existing = None
        if needs_existing or user.get("role") == "test":
            existing = await db[coll].find_one({"id": item_id}, {"_id": 0})
            if not existing:
                raise HTTPException(status_code=404, detail="Not found")
        if user.get("role") == "test" and not existing.get("is_test_data"):
            raise HTTPException(status_code=403, detail="Test mode: cannot modify real records")
        if needs_existing:
            workflow.enforce_generic_status_change(coll, existing, payload, role=user.get("role"))
        res = await db[coll].update_one({"id": item_id}, {"$set": payload})
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="Not found")
        return await db[coll].find_one({"id": item_id}, {"_id": 0})

    @router.delete(f"/{path}/{{item_id}}")
    async def delete_item(item_id: str, user=Depends(require_permission(f"{perm}:delete"))):
        if user.get("role") == "test":
            existing = await db[coll].find_one({"id": item_id}, {"_id": 0, "is_test_data": 1})
            if not existing or not existing.get("is_test_data"):
                raise HTTPException(status_code=403, detail="Test mode: cannot delete real records")
        await db[coll].delete_one({"id": item_id})
        return {"ok": True}


async def gather_expenses(vehicle_id=None, start_date=None, end_date=None, include_test=False):
    """Aggregate all expense rows across modules into a unified ledger."""
    def q(date_field="date", extra=None):
        qq = dict(extra or {})
        if not include_test:
            qq["is_test_data"] = {"$ne": True}
        if vehicle_id:
            qq["vehicle_id"] = vehicle_id
        if start_date:
            qq[date_field] = {"$gte": start_date}
        if end_date:
            qq.setdefault(date_field, {})
            qq[date_field]["$lte"] = end_date
        return qq

    rows = []
    for f in await db.fuel_entries.find(q(), {"_id": 0}).to_list(5000):
        rows.append({"date": f.get("date"), "vehicle_id": f["vehicle_id"], "category": "Fuel",
                     "amount": f.get("amount") or 0, "description": f.get("station") or "Fuel purchase",
                     "source": "fuel", "source_id": f.get("id")})
    for s in await db.services.find(q(), {"_id": 0}).to_list(5000):
        rows.append({"date": s.get("date"), "vehicle_id": s["vehicle_id"], "category": "Service",
                     "amount": s.get("cost") or 0, "description": s.get("service_type") or "Service",
                     "source": "maintenance", "source_id": s.get("id")})
    for g in await db.greasings.find(q(), {"_id": 0}).to_list(5000):
        if g.get("cost"):
            rows.append({"date": g.get("date"), "vehicle_id": g["vehicle_id"], "category": "Greasing",
                         "amount": g.get("cost") or 0, "description": "Greasing",
                         "source": "maintenance", "source_id": g.get("id")})
    for r in await db.repairs.find(q(), {"_id": 0}).to_list(5000):
        rows.append({"date": r.get("date"), "vehicle_id": r["vehicle_id"], "category": "Repair",
                     "amount": r.get("cost") or 0, "description": r.get("issue") or "Repair",
                     "source": "repairs", "source_id": r.get("id"), "reference": r.get("ticket_number")})
    for t in await db.tyres.find(q("installation_date"), {"_id": 0}).to_list(5000):
        if t.get("cost"):
            rows.append({"date": t.get("installation_date"), "vehicle_id": t["vehicle_id"], "category": "Tyres",
                         "amount": t.get("cost") or 0, "description": f"Tyre {t.get('tyre_number', '')}",
                         "source": "tyres", "source_id": t.get("id")})
    for e in await db.tyre_events.find(q(), {"_id": 0}).to_list(5000):
        if e.get("cost"):
            rows.append({"date": e.get("date"), "vehicle_id": e.get("vehicle_id"), "category": "Tyres",
                         "amount": e.get("cost") or 0, "description": e.get("event_type") or "Tyre event",
                         "source": "tyres", "source_id": e.get("id")})
    for a in await db.accidents.find(q(), {"_id": 0}).to_list(5000):
        if a.get("repair_cost"):
            rows.append({"date": a.get("date"), "vehicle_id": a["vehicle_id"], "category": "Accident",
                         "amount": a.get("repair_cost") or 0, "description": a.get("location") or "Accident repair",
                         "source": "accidents", "source_id": a.get("id")})
    for ft in await db.fastag_transactions.find(q(extra={"txn_type": "toll"}), {"_id": 0}).to_list(5000):
        rows.append({"date": ft.get("date"), "vehicle_id": ft["vehicle_id"], "category": "Fastag",
                     "amount": ft.get("amount") or 0, "description": ft.get("toll_plaza") or "Toll",
                     "source": "fastag", "source_id": ft.get("id")})
    for tr in await db.trips.find(q(), {"_id": 0}).to_list(5000):
        amt = (tr.get("toll_expense") or 0) + (tr.get("parking_expense") or 0) + (tr.get("misc_expense") or 0)
        if amt:
            rows.append({"date": tr.get("date"), "vehicle_id": tr["vehicle_id"], "category": "Trip",
                         "amount": amt, "description": f"{tr.get('origin', '')} → {tr.get('destination', '')}",
                         "source": "trips", "source_id": tr.get("id")})
    for ex in await db.expenses.find(q(), {"_id": 0}).to_list(5000):
        rows.append({"date": ex.get("date"), "vehicle_id": ex["vehicle_id"], "category": ex.get("category", "Miscellaneous"),
                     "amount": ex.get("amount") or 0, "description": ex.get("description") or "",
                     "source": "expenses", "source_id": ex.get("id")})
    rows.sort(key=lambda r: r.get("date") or "", reverse=True)
    return rows
