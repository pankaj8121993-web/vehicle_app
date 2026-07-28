import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from database import db
from auth import require_module, require_permission, record_security_event
from models import TyreCreate, TyreEventCreate, AccidentCreate, FastagTxnCreate, DowntimeCreate, ExpenseCreate
from helpers import make_crud, gather_expenses, enrich
from references import validate_references
import atomicity
import invariants
import fastag_simulation


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# OPS-03: tyre lifecycle. A tyre is active on exactly one vehicle; removal /
# scrapping are terminal for its "on a vehicle" state.
TYRE_FITTED_STATUSES = ("active",)
TYRE_TERMINAL_STATUSES = ("scrapped",)

router = APIRouter(tags=["assets"])


# ---------- Tyres ----------
async def on_tyre_create(doc):
    # OPS-03: a physical tyre (identified by tyre_number) cannot be fitted to two
    # vehicles at once. Refuse a create that would make the same tyre_number
    # active on a second vehicle.
    number = doc.get("tyre_number")
    if number:
        clash = await db.tyres.find_one(
            {"tyre_number": number, "status": {"$in": list(TYRE_FITTED_STATUSES)}},
            {"_id": 0, "id": 1, "vehicle_id": 1},
        )
        if clash and clash.get("vehicle_id") != doc.get("vehicle_id"):
            raise HTTPException(
                status_code=409,
                detail="This tyre is already fitted to another vehicle",
            )
    return doc

make_crud(router, "tyres", "tyres", TyreCreate, date_field="installation_date",
          on_create=on_tyre_create, module="tyres")


async def _tyre_or_404(tyre_id):
    tyre = await db.tyres.find_one({"id": tyre_id}, {"_id": 0})
    if not tyre:
        raise HTTPException(status_code=404, detail="Tyre not found")
    return tyre


async def _record_tyre_event(tyre, event_type, *, vehicle_id=None, odometer=None,
                             cost=0, notes=None, user=None):
    """Append an immutable tyre lifecycle event (history is never rewritten)."""
    await db.tyre_events.insert_one({
        "id": str(uuid.uuid4()),
        "tyre_id": tyre["id"],
        "vehicle_id": vehicle_id or tyre.get("vehicle_id"),
        "event_type": event_type,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "odometer": odometer,
        "cost": cost or 0,
        "notes": notes,
        "created_at": _now_iso(),
        "created_by": (user or {}).get("user_id"),
        "is_test_data": tyre.get("is_test_data", False),
    })


@router.patch("/tyres/{tyre_id}/transfer")
async def transfer_tyre(tyre_id: str, payload: dict = Body(...),
                        user=Depends(require_permission("tyres:update"))):
    """Move a fitted tyre to another same-tenant vehicle, preserving history.
    A removed/scrapped tyre cannot be transferred."""
    tyre = await _tyre_or_404(tyre_id)
    if tyre.get("status") in TYRE_TERMINAL_STATUSES or tyre.get("status") == "removed":
        raise HTTPException(status_code=409,
                            detail="A removed or scrapped tyre cannot be transferred")
    to_vehicle = payload.get("to_vehicle_id")
    if not to_vehicle:
        raise HTTPException(status_code=400, detail="to_vehicle_id is required")
    if to_vehicle == tyre.get("vehicle_id"):
        raise HTTPException(status_code=400, detail="Tyre is already on that vehicle")
    # Same-org, in-service target vehicle (DI-01 references).
    await validate_references("tyres", {"vehicle_id": to_vehicle})
    odo = None
    if payload.get("odometer") is not None:
        odo = invariants.odometer(payload["odometer"], field="odometer", allow_none=False)
    from_vehicle = tyre.get("vehicle_id")
    await db.tyres.update_one(
        {"id": tyre_id},
        {"$set": {"vehicle_id": to_vehicle, "status": "active"}},
    )
    await _record_tyre_event(tyre, "transfer", vehicle_id=to_vehicle, odometer=odo,
                             notes=payload.get("notes"), user=user)
    await record_security_event("tyre.transfer", user, target_id=tyre_id,
                                detail={"from_vehicle": from_vehicle, "to_vehicle": to_vehicle})
    return await db.tyres.find_one({"id": tyre_id}, {"_id": 0})


@router.patch("/tyres/{tyre_id}/scrap")
async def scrap_tyre(tyre_id: str, payload: dict = Body(default={}),
                     user=Depends(require_permission("tyres:update"))):
    """Scrap a tyre (terminal). A scrapped tyre cannot be fitted or transferred."""
    tyre = await _tyre_or_404(tyre_id)
    if tyre.get("status") == "scrapped":
        return tyre  # idempotent
    odo = None
    if payload.get("odometer") is not None:
        odo = invariants.odometer(payload["odometer"], field="odometer", allow_none=False)
    await db.tyres.update_one(
        {"id": tyre_id},
        {"$set": {"status": "scrapped", "removal_km": odo, "scrap_reason": payload.get("reason")}},
    )
    await _record_tyre_event(tyre, "scrap", odometer=odo, notes=payload.get("reason"), user=user)
    await record_security_event("tyre.scrap", user, target_id=tyre_id, detail={})
    return await db.tyres.find_one({"id": tyre_id}, {"_id": 0})


async def on_tyre_event_create(doc):
    # Derive the event's own vehicle_id from its tyre when omitted. This shapes
    # the record itself, so it stays in the pre-insert hook.
    if not doc.get("vehicle_id"):
        tyre = await db.tyres.find_one({"id": doc["tyre_id"]}, {"_id": 0})
        if tyre:
            doc["vehicle_id"] = tyre["vehicle_id"]
    return doc


async def after_tyre_event_create(doc):
    # DI-02: the tyre status change is a *derived* side effect and now runs after
    # the event is stored (write-source-first). If it failed, the event still
    # exists and the tyre's status is rebuildable from its events, rather than a
    # tyre flipped to "removed" with no event to explain it.
    if doc.get("event_type") == "replacement":
        await db.tyres.update_one(
            {"id": doc["tyre_id"]},
            {"$set": {"status": "removed", "removal_km": doc.get("odometer")}},
        )

make_crud(router, "tyre-events", "tyre_events", TyreEventCreate,
          on_create=on_tyre_event_create, after_create=after_tyre_event_create, module="tyres")


# ---------- Accidents ----------
make_crud(router, "accidents", "accidents", AccidentCreate)


# ---------- Fastag ----------
async def after_fastag_create(doc):
    # DI-02: adjust the running balance *after* the transaction is stored. The
    # transaction is the source of truth; the vehicle balance is a derived cache
    # (DI-03 recomputes it from the transaction set). Doing the balance write
    # first — as the pre-DI-02 hook did — could increment the balance for a
    # transaction that then failed to insert.
    delta = doc["amount"] if doc["txn_type"] == "recharge" else -doc["amount"]
    await db.vehicles.update_one({"id": doc["vehicle_id"]}, {"$inc": {"fastag_balance": delta}})

make_crud(router, "fastag", "fastag_transactions", FastagTxnCreate,
          after_create=after_fastag_create, module="fastag")


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


@router.patch("/downtime/{downtime_id}/close")
async def close_downtime(downtime_id: str, payload: dict = Body(default={}),
                         user=Depends(require_permission("downtime:update"))):
    """Close an open downtime, recording the closure date and reason and
    computing the downtime days. Idempotent; a closed downtime is terminal and
    cannot be reopened (WF-01), and closing brings an idle vehicle back to
    active."""
    dt = await db.downtimes.find_one({"id": downtime_id}, {"_id": 0})
    if not dt:
        raise HTTPException(status_code=404, detail="Downtime not found")
    if dt.get("status") == "closed":
        return dt  # idempotent
    end_date = payload.get("end_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    invariants.require_date_order(dt.get("start_date"), end_date)
    try:
        d1 = datetime.fromisoformat(dt["start_date"])
        d2 = datetime.fromisoformat(end_date)
        days = max((d2 - d1).days + 1, 1)
    except (ValueError, TypeError):
        days = None
    updates = {"status": "closed", "end_date": end_date, "days": days,
               "closure_reason": payload.get("reason")}
    won = await atomicity.swap_status("downtimes", downtime_id, "open", updates)
    if not won:
        return await db.downtimes.find_one({"id": downtime_id}, {"_id": 0})
    # Bring the vehicle back on the road if it has no other open downtime.
    other = await db.downtimes.find_one(
        {"vehicle_id": dt["vehicle_id"], "status": "open"}, {"_id": 0, "id": 1})
    if not other:
        await db.vehicles.update_one(
            {"id": dt["vehicle_id"], "status": "maintenance"},
            {"$set": {"status": "active"}},
        )
    await record_security_event("downtime.close", user, target_id=downtime_id,
                                detail={"days": days})
    return await db.downtimes.find_one({"id": downtime_id}, {"_id": 0})


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

async def on_expense_create(doc):
    # OPS-02: a manual expense enters the approval workflow as "submitted". The
    # approved/paid figures are server-owned and filled by the dedicated
    # approve/pay actions (routes_settlement); they are protected against a
    # generic write by TEN-01.
    doc["approval_status"] = "submitted"
    doc["approved_amount"] = None
    doc["paid_amount"] = 0
    return doc

make_crud(router, "expenses", "expenses", ExpenseCreate, module="expenses",
          on_create=on_expense_create)
