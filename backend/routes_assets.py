import random
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from database import db
from auth import require_user
from models import TyreCreate, TyreEventCreate, AccidentCreate, FastagTxnCreate, DowntimeCreate, ExpenseCreate
from helpers import make_crud, gather_expenses, enrich

router = APIRouter(tags=["assets"])


# ---------- Tyres ----------
make_crud(router, "tyres", "tyres", TyreCreate, date_field="installation_date")


async def on_tyre_event_create(doc):
    if not doc.get("vehicle_id"):
        tyre = await db.tyres.find_one({"id": doc["tyre_id"]}, {"_id": 0})
        if tyre:
            doc["vehicle_id"] = tyre["vehicle_id"]
    if doc["event_type"] == "replacement":
        await db.tyres.update_one({"id": doc["tyre_id"]}, {"$set": {"status": "removed", "removal_km": doc.get("odometer")}})
    return doc

make_crud(router, "tyre-events", "tyre_events", TyreEventCreate, on_create=on_tyre_event_create)


# ---------- Accidents ----------
make_crud(router, "accidents", "accidents", AccidentCreate)


# ---------- Fastag ----------
async def on_fastag_create(doc):
    delta = doc["amount"] if doc["txn_type"] == "recharge" else -doc["amount"]
    await db.vehicles.update_one({"id": doc["vehicle_id"]}, {"$inc": {"fastag_balance": delta}})
    return doc

make_crud(router, "fastag", "fastag_transactions", FastagTxnCreate, on_create=on_fastag_create)


# SIMULATED Fastag auto-sync (no public NPCI/bank Fastag API exists).
# Generates demo toll transactions + an authoritative balance. Swap with a real API later.
TOLL_PLAZAS = ["Khed Shivapur Plaza", "Talegaon Plaza", "Anewadi Plaza", "Tasawade Plaza",
               "Kini Plaza", "Vashi Plaza", "Charoti Plaza", "Dahisar Plaza"]


@router.post("/fastag/sync/{vehicle_id}")
async def fastag_sync(vehicle_id: str, user=Depends(require_user)):
    vehicle = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    if not vehicle.get("fastag_number"):
        raise HTTPException(status_code=400, detail="Link a Fastag number to this vehicle first (edit the vehicle)")
    now = datetime.now(timezone.utc)
    txns = []
    for _ in range(random.randint(4, 8)):
        d = now - timedelta(days=random.randint(0, 30))
        txns.append({
            "id": str(uuid.uuid4()),
            "vehicle_id": vehicle_id,
            "txn_type": "toll",
            "date": d.strftime("%Y-%m-%d"),
            "toll_plaza": random.choice(TOLL_PLAZAS),
            "amount": float(random.choice([45, 65, 85, 105, 140, 165, 210, 240, 330])),
            "notes": None,
            "source": "auto_sync",
            "created_at": now.isoformat(),
            "created_by": user["user_id"],
        })
    if random.random() < 0.7:
        d = now - timedelta(days=random.randint(0, 25))
        txns.append({
            "id": str(uuid.uuid4()),
            "vehicle_id": vehicle_id,
            "txn_type": "recharge",
            "date": d.strftime("%Y-%m-%d"),
            "toll_plaza": None,
            "amount": float(random.choice([500, 1000, 2000])),
            "notes": "Auto recharge",
            "source": "auto_sync",
            "created_at": now.isoformat(),
            "created_by": user["user_id"],
        })
    await db.fastag_transactions.insert_many([{**t} for t in txns])
    new_balance = round(random.uniform(250, 2800), 2)
    await db.vehicles.update_one({"id": vehicle_id}, {"$set": {"fastag_balance": new_balance}})
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

make_crud(router, "downtime", "downtimes", DowntimeCreate, date_field="start_date", on_create=on_downtime_create)


# ---------- Expenses ----------
@router.get("/expenses/ledger")
async def expense_ledger(vehicle_id: str = None, start_date: str = None, end_date: str = None, user=Depends(require_user)):
    rows = await gather_expenses(vehicle_id=vehicle_id, start_date=start_date, end_date=end_date)
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

make_crud(router, "expenses", "expenses", ExpenseCreate)
