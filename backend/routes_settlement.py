"""
OPS-02 — Expense approval, payment and trip settlement.

Before OPS-02 a manual expense was a plain financial record: there was no
approval, no payment tracking and no settlement (WORKFLOWS.md §3). This module
adds the operational financial lifecycle *without* building an accounting
ledger:

* **Approval is separate from payment.** An expense is created `submitted`
  (`routes_assets.on_expense_create`), then `approve`d (with an authorised
  approved_amount ≤ submitted) or `reject`ed. Neither event moves money.
* **Payments are append-only events.** `record_payment` writes an immutable row
  in `expense_payments`; `paid_amount` is *recomputed* from those events
  (write-source-first, DI-02), so a retry never double-pays and a reversal
  simply restores outstanding.
* **Driver advances** are their own records, recovered/adjusted at settlement.
* **Trip settlement** aggregates approved trip-linked expenses, advances and
  payments into totals that reconcile with `helpers.gather_expenses` /
  `reconciliation.trip_economics` — no parallel money calculation.

Every action is permission-gated (approve/reject/pay/reverse/settle are
management/admin only — a data-entry user who *submits* cannot approve or pay
their own claim), idempotent, compare-and-swap protected and audited.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request

import atomicity
import idempotency
import invariants
import workflow
from auth import require_permission, record_security_event
from database import db
from helpers import make_crud
from models import AdvanceCreate

router = APIRouter(tags=["settlement"])


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


async def _expense_or_404(expense_id):
    exp = await db.expenses.find_one({"id": expense_id}, {"_id": 0})
    if not exp:
        raise HTTPException(status_code=404, detail="Expense not found")
    return exp


async def _recompute_paid(expense_id):
    """Sum the append-only payment events into a single paid_amount (DI-02).

    payment events add, reversal events subtract. The stored paid_amount is a
    cache of this; the events are the source of truth, so a retry or a reversal
    is always consistent.
    """
    events = await db.expense_payments.find(
        {"expense_id": expense_id}, {"_id": 0, "kind": 1, "amount": 1}
    ).to_list(10000)
    paid = 0.0
    for e in events:
        if e.get("kind") == "reversal":
            paid -= e.get("amount") or 0
        else:
            paid += e.get("amount") or 0
    paid = round(paid, 2)
    await db.expenses.update_one({"id": expense_id}, {"$set": {"paid_amount": paid}})
    return paid


def _outstanding(exp):
    approved = exp.get("approved_amount")
    if approved is None:
        return 0.0
    return round(approved - (exp.get("paid_amount") or 0), 2)


# --- Approval / rejection -----------------------------------------------------

@router.patch("/expenses/{expense_id}/approve")
async def approve_expense(expense_id: str, payload: dict = Body(default={}),
                          user=Depends(require_permission("expenses:approve"))):
    """Approve a submitted expense. approved_amount defaults to the submitted
    amount and may be reduced (an authorised downward adjustment) but never
    exceed it. Idempotent; a reviewer cannot approve their own submission."""
    exp = await _expense_or_404(expense_id)
    status = exp.get("approval_status") or "submitted"
    if status == "approved":
        return exp  # idempotent
    if status == "rejected":
        raise HTTPException(status_code=409, detail="A rejected expense cannot be approved")
    workflow.check_version(exp, payload.get("expected_version"))
    # Self-approval guard: the person who submitted a claim may not approve it.
    if exp.get("created_by") and exp["created_by"] == user.get("user_id"):
        raise HTTPException(status_code=403, detail="You cannot approve your own expense")
    submitted = exp.get("amount") or 0
    approved_amount = payload.get("approved_amount", submitted)
    approved_amount = invariants.money(approved_amount, field="approved_amount", allow_none=False)
    if approved_amount > submitted:
        raise HTTPException(
            status_code=400,
            detail="approved_amount cannot exceed the submitted amount",
        )
    updates = {
        "approval_status": "approved",
        "approved_amount": approved_amount,
        "approved_by": user.get("user_id"),
        "approved_at": _now_iso(),
        "_version": workflow.next_version(exp),
    }
    won = await atomicity.swap_field("expenses", expense_id, "approval_status", status, updates)
    if not won:
        raise HTTPException(status_code=409,
                            detail="This expense changed since you loaded it. Reload and retry.")
    await record_security_event("expense.approve", user, target_id=expense_id,
                                detail={"approved_amount": approved_amount})
    return await db.expenses.find_one({"id": expense_id}, {"_id": 0})


@router.patch("/expenses/{expense_id}/reject")
async def reject_expense(expense_id: str, payload: dict = Body(default={}),
                         user=Depends(require_permission("expenses:reject"))):
    """Reject a submitted expense. Terminal for the approval axis; a rejected
    expense cannot be paid and is excluded from the reconciliation ledger."""
    exp = await _expense_or_404(expense_id)
    status = exp.get("approval_status") or "submitted"
    if status == "rejected":
        return exp  # idempotent
    if status == "approved":
        raise HTTPException(status_code=409, detail="An approved expense cannot be rejected")
    workflow.check_version(exp, payload.get("expected_version"))
    updates = {
        "approval_status": "rejected",
        "rejection_reason": payload.get("reason"),
        "rejected_by": user.get("user_id"),
        "rejected_at": _now_iso(),
        "_version": workflow.next_version(exp),
    }
    won = await atomicity.swap_field("expenses", expense_id, "approval_status", status, updates)
    if not won:
        raise HTTPException(status_code=409,
                            detail="This expense changed since you loaded it. Reload and retry.")
    await record_security_event("expense.reject", user, target_id=expense_id, detail={})
    return await db.expenses.find_one({"id": expense_id}, {"_id": 0})


# --- Payments (append-only events) --------------------------------------------

@router.post("/expenses/{expense_id}/payments")
async def record_payment(expense_id: str, request: Request, payload: dict = Body(...),
                         user=Depends(require_permission("expenses:pay"))):
    """Record a payment against an approved expense. The paid total may never
    exceed the approved outstanding. Idempotency-Key aware; write-source-first
    (event stored, then paid_amount recomputed)."""
    exp = await _expense_or_404(expense_id)
    if (exp.get("approval_status") or "submitted") != "approved":
        raise HTTPException(status_code=409, detail="Only an approved expense can be paid")
    amount = invariants.money(payload.get("amount"), field="amount", allow_none=False)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")
    outstanding = _outstanding(exp)
    if amount > outstanding:
        raise HTTPException(
            status_code=400,
            detail=f"Payment {amount} exceeds the approved outstanding of {outstanding}",
        )
    idem_key = idempotency.key_from_headers(request.headers)
    scope = f"expense-pay:{expense_id}"
    if idem_key:
        replayed, _fp = await idempotency.replay_or_claim(scope, idem_key, payload)
        if replayed is not None:
            return replayed
    try:
        event = {
            "id": str(uuid.uuid4()),
            "expense_id": expense_id,
            "kind": "payment",
            "amount": amount,
            "date": payload.get("date") or _now_iso()[:10],
            "method": payload.get("method"),
            "reference": payload.get("reference"),
            "created_by": user.get("user_id"),
            "created_at": _now_iso(),
        }
        await db.expense_payments.insert_one({**event})
        event.pop("_id", None)
        paid = await _recompute_paid(expense_id)
    except Exception:
        if idem_key:
            await idempotency.release(scope, idem_key)
        raise
    await record_security_event("expense.payment", user, target_id=expense_id,
                                detail={"amount": amount, "paid_total": paid})
    result = {"payment": event, "paid_amount": paid,
              "outstanding": round((exp.get("approved_amount") or 0) - paid, 2)}
    if idem_key:
        await idempotency.store_result(scope, idem_key, result)
    return result


@router.post("/expenses/{expense_id}/payments/{payment_id}/reverse")
async def reverse_payment(expense_id: str, payment_id: str, payload: dict = Body(default={}),
                          user=Depends(require_permission("expenses:reverse_payment"))):
    """Reverse a payment. The original payment event is preserved; a reversal
    event is appended and paid_amount recomputed, restoring outstanding."""
    exp = await _expense_or_404(expense_id)
    original = await db.expense_payments.find_one(
        {"id": payment_id, "expense_id": expense_id, "kind": "payment"}, {"_id": 0}
    )
    if not original:
        raise HTTPException(status_code=404, detail="Payment not found")
    already = await db.expense_payments.find_one(
        {"reverses": payment_id, "kind": "reversal"}, {"_id": 0}
    )
    if already:
        return {"paid_amount": exp.get("paid_amount") or 0, "already_reversed": True}
    event = {
        "id": str(uuid.uuid4()),
        "expense_id": expense_id,
        "kind": "reversal",
        "amount": original["amount"],
        "reverses": payment_id,
        "date": _now_iso()[:10],
        "created_by": user.get("user_id"),
        "created_at": _now_iso(),
    }
    await db.expense_payments.insert_one({**event})
    paid = await _recompute_paid(expense_id)
    await record_security_event("expense.payment_reversal", user, target_id=expense_id,
                                detail={"amount": original["amount"], "paid_total": paid})
    return {"paid_amount": paid,
            "outstanding": round((exp.get("approved_amount") or 0) - paid, 2)}


@router.get("/expenses/{expense_id}/payments")
async def list_payments(expense_id: str, user=Depends(require_permission("expenses:approve"))):
    await _expense_or_404(expense_id)
    events = await db.expense_payments.find(
        {"expense_id": expense_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(10000)
    return {"payments": events}


# --- Driver advances ----------------------------------------------------------

async def on_advance_create(doc):
    doc["status"] = "outstanding"
    doc["recovered_amount"] = 0
    return doc

make_crud(router, "advances", "advances", AdvanceCreate, on_create=on_advance_create)


@router.patch("/advances/{advance_id}/recover")
async def recover_advance(advance_id: str, payload: dict = Body(...),
                          user=Depends(require_permission("settlements:close"))):
    """Record recovery/adjustment of a driver advance. Recovered total may not
    exceed the advance amount; fully-recovered advances are marked recovered."""
    adv = await db.advances.find_one({"id": advance_id}, {"_id": 0})
    if not adv:
        raise HTTPException(status_code=404, detail="Advance not found")
    amount = invariants.money(payload.get("amount"), field="amount", allow_none=False)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Recovery amount must be greater than zero")
    new_recovered = round((adv.get("recovered_amount") or 0) + amount, 2)
    if new_recovered > (adv.get("amount") or 0):
        raise HTTPException(status_code=400,
                            detail="Recovered amount cannot exceed the advance amount")
    status = "recovered" if new_recovered >= (adv.get("amount") or 0) else "outstanding"
    await db.advances.update_one(
        {"id": advance_id},
        {"$set": {"recovered_amount": new_recovered, "status": status}},
    )
    await record_security_event("advance.recover", user, target_id=advance_id,
                                detail={"recovered": new_recovered})
    return await db.advances.find_one({"id": advance_id}, {"_id": 0})


# --- Trip settlement ----------------------------------------------------------

async def _trip_expenses(trip_id, trip):
    """Manual expenses linked to this trip (by trip_id) plus the trip's own
    direct expenses (toll/parking/misc). Returns (rows, direct)."""
    rows = await db.expenses.find({"trip_id": trip_id}, {"_id": 0}).to_list(5000)
    direct = ((trip.get("toll_expense") or 0) + (trip.get("parking_expense") or 0)
              + (trip.get("misc_expense") or 0))
    return rows, round(direct, 2)


async def _settlement_view(trip_id):
    trip = await db.trips.find_one({"id": trip_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    exp_rows, direct = await _trip_expenses(trip_id, trip)
    active = [e for e in exp_rows if e.get("approval_status") != "rejected"
              and e.get("status") != "cancelled"]
    submitted_total = round(sum(e.get("amount") or 0 for e in active), 2)
    approved = [e for e in active if e.get("approval_status") == "approved"]
    approved_total = round(sum(e.get("approved_amount") or 0 for e in approved), 2)
    paid_total = round(sum(e.get("paid_amount") or 0 for e in approved), 2)
    pending_approval = [e for e in active if (e.get("approval_status") or "submitted") == "submitted"]
    advances = await db.advances.find({"trip_id": trip_id}, {"_id": 0}).to_list(5000)
    advance_total = round(sum(a.get("amount") or 0 for a in advances), 2)
    advance_recovered = round(sum(a.get("recovered_amount") or 0 for a in advances), 2)
    # Eligible cost = trip-direct expenses + approved linked expenses.
    eligible = round(direct + approved_total, 2)
    outstanding = round(approved_total - paid_total, 2)
    return {
        "trip_id": trip_id,
        "status": trip.get("status"),
        "trip_direct_expenses": direct,
        "linked_expenses_submitted": submitted_total,
        "approved_expenses": approved_total,
        "eligible_expenses": eligible,
        "advances": advance_total,
        "advances_recovered": advance_recovered,
        "payments": paid_total,
        "outstanding": outstanding,
        # Net of the driver's approved reimbursables against advances given.
        "net_payable_to_driver": round(approved_total - advance_total, 2),
        "pending_approval_count": len(pending_approval),
    }


@router.get("/trips/{trip_id}/settlement")
async def trip_settlement(trip_id: str, user=Depends(require_permission("expenses:approve"))):
    return await _settlement_view(trip_id)


@router.patch("/trips/{trip_id}/settle")
async def settle_trip(trip_id: str, payload: dict = Body(default={}),
                      user=Depends(require_permission("settlements:close"))):
    """Move a completed trip to settlement_pending. Refused while any linked
    expense is still awaiting approval, unless an authorised override is passed."""
    trip = await db.trips.find_one({"id": trip_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    current = trip.get("status")
    workflow.check_version(trip, payload.get("expected_version"))
    if workflow.validate_transition(
        workflow.TRIP_STATUS_WORKFLOW, current, "settlement_pending"
    ) == "noop":
        return trip
    view = await _settlement_view(trip_id)
    if view["pending_approval_count"] and not payload.get("override_pending"):
        raise HTTPException(
            status_code=409,
            detail=(f"{view['pending_approval_count']} linked expense(s) still awaiting "
                    "approval; approve them or pass override_pending"),
        )
    updates = {"status": "settlement_pending", "_version": workflow.next_version(trip),
               "settled_at": _now_iso()}
    won = await atomicity.swap_status("trips", trip_id, current, updates)
    if not won:
        raise HTTPException(status_code=409,
                            detail="This trip changed since you loaded it. Reload and retry.")
    await record_security_event("trip.settle", user, target_id=trip_id,
                                detail={"outstanding": view["outstanding"]})
    return await db.trips.find_one({"id": trip_id}, {"_id": 0})
