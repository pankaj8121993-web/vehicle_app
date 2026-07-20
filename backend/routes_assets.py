import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from database import db
from auth import require_user, require_module, require_permission, record_security_event
from models import TyreCreate, TyreEventCreate, AccidentCreate, FastagTxnCreate, DowntimeCreate, ExpenseCreate
from helpers import make_crud, gather_expenses, enrich
import fastag_simulation

router = APIRouter(tags=["assets"])


# ---------- Tyres ----------
make_crud(router, "tyres", "tyres", TyreCreate, date_field="installation_date", module="tyres")


async def on_tyre_event_create(doc):
    if not doc.get("vehicle_id"):
        tyre = await db.tyres.find_one({"id": doc["tyre_id"]}, {"_id": 0})
        if tyre:
            doc["vehicle_id"] = tyre["vehicle_id"]
    if doc["event_type"] == "replacement":
        await db.tyres.update_one({"id": doc["tyre_id"]}, {"$set": {"status": "removed", "removal_km": doc.get("odometer")}})
    return doc

make_crud(router, "tyre-events", "tyre_events", TyreEventCreate, on_create=on_tyre_event_create, module="tyres")


# ---------- Accidents ----------
make_crud(router, "accidents", "accidents", AccidentCreate)


# ---------- Fastag ----------
async def on_fastag_create(doc):
    delta = doc["amount"] if doc["txn_type"] == "recharge" else -doc["amount"]
    await db.vehicles.update_one({"id": doc["vehicle_id"]}, {"$inc": {"fastag_balance": delta}})
    return doc

make_crud(router, "fastag", "fastag_transactions", FastagTxnCreate, on_create=on_fastag_create, module="fastag")


# FASTAG-01: FASTag "sync" is a demo-only *simulation* — there is no public
# NPCI/bank FASTag API. The guard, generation, idempotency and balance logic live
# in fastag_simulation.py; this endpoint is the thin, fail-closed entry point.
@router.post("/fastag/sync/{vehicle_id}")
async def fastag_sync(
    vehicle_id: str,
    idempotency_key: str = Query(None, alias="idempotency_key"),
    user=Depends(require_permission("fastag:simulate")),
):
    # Fail closed off the demo organisation: a real tenant must never receive
    # fabricated FASTag activity. Checked before any read or write.
    fastag_simulation.assert_simulation_allowed(user)

    # db.vehicles is tenant-scoped, so this only ever resolves a vehicle in the
    # caller's (demo) organisation — a cross-tenant id simply 404s.
    vehicle = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    if not vehicle.get("fastag_number"):
        raise HTTPException(status_code=400, detail="Link a Fastag number to this vehicle first (edit the vehicle)")

    batch_key = fastag_simulation._batch_key(vehicle_id, idempotency_key)

    # Idempotency / safe replay: if this batch already ran, return the original
    # result and write nothing new. Only meaningful when a key was supplied.
    if idempotency_key:
        existing = await db.fastag_transactions.find(
            {"vehicle_id": vehicle_id, "sim_batch": batch_key}, {"_id": 0}
        ).to_list(100)
        if existing:
            all_txns = await db.fastag_transactions.find(
                {"vehicle_id": vehicle_id}, {"_id": 0}
            ).to_list(5000)
            return {
                "synced_transactions": len(existing),
                "balance": fastag_simulation.computed_balance(all_txns),
                "simulated": True,
                "replayed": True,
            }

    txns = fastag_simulation.build_simulated_batch(vehicle_id, user, batch_key)
    await db.fastag_transactions.insert_many([{**t} for t in txns])

    # Balance is computed from the vehicle's transactions, never a random number,
    # so a replay is stable and the figure is not fabricated out of thin air.
    all_txns = await db.fastag_transactions.find(
        {"vehicle_id": vehicle_id}, {"_id": 0}
    ).to_list(5000)
    new_balance = fastag_simulation.computed_balance(all_txns)
    await db.vehicles.update_one({"id": vehicle_id}, {"$set": {"fastag_balance": new_balance}})

    await record_security_event(
        "fastag.simulate", user, target_id=vehicle_id,
        detail={"generated": len(txns), "batch": batch_key},
    )
    return {"synced_transactions": len(txns), "balance": new_balance, "simulated": True}


# ---------- Downtime ----------
async def on_downtime_create(doc):
    if doc.get("end_date"):
        try:
            d1 = datetime.fromisoformat(doc["start_date"])
            d2 = datetime.fromisoformat(doc["end_date"])
            doc["days"] = max((d2 - d1).days + 1, 1)
        except ValueError:
            doc["days"] = None
        doc["status"] = "closed"
    else:
        doc["days"] = None
        doc["status"] = "open"
    return doc

make_crud(router, "downtime", "downtimes", DowntimeCreate, date_field="start_date", on_create=on_downtime_create, module="downtime")


# ---------- Expenses ----------
@router.get("/expenses/ledger")
async def expense_ledger(vehicle_id: str = None, start_date: str = None, end_date: str = None, user=Depends(require_module("expenses"))):
    include_test = user.get("role") == "test"
    rows = await gather_expenses(vehicle_id=vehicle_id, start_date=start_date, end_date=end_date, include_test=include_test)
    rows = await enrich(rows)
    by_category = {}
    by_vehicle = {}
    for r in rows:
        by_category[r["category"]] = round(by_category.get(r["category"], 0) + r["amount"], 2)
        key = r.get("vehicle_number") or r.get("vehicle_id") or "Unknown"
        by_vehicle[key] = round(by_vehicle.get(key, 0) + r["amount"], 2)
    return {
        "rows": rows,
        "total": round(sum(r["amount"] for r in rows), 2),
        "by_category": by_category,
        "by_vehicle": by_vehicle,
    }

make_crud(router, "expenses", "expenses", ExpenseCreate, module="expenses")
