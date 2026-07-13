"""Expense Intelligence — overview, insights and budgets."""
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Body, Depends, HTTPException
from database import db
from auth import require_user, require_role, require_module
from helpers import gather_expenses

router = APIRouter(tags=["expenses"])

BUDGET_CATEGORIES = [
    "Fuel", "Fastag", "Service", "Greasing", "Repair", "Tyres", "Trip", "Accident",
    "Insurance", "Permits", "Road Tax", "Fines & Penalties", "Washing", "Parking",
    "GPS Subscription", "Driver Expenses", "Spare Parts", "Miscellaneous",
]


def _month(d):
    return (d or "")[:7]


@router.get("/expenses/overview")
async def expense_overview(start_date: str = None, end_date: str = None, user=Depends(require_module("expenses"))):
    today = datetime.now(timezone.utc)
    cur_month = today.strftime("%Y-%m")
    prev_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    trend_start = (today.replace(day=1) - timedelta(days=365)).strftime("%Y-%m-01")

    include_test = user.get("role") == "test"
    ledger = await gather_expenses(start_date=trend_start if not start_date else min(start_date, trend_start),
                                   include_test=include_test)
    in_range = [r for r in ledger
                if (not start_date or (r.get("date") or "") >= start_date)
                and (not end_date or (r.get("date") or "") <= end_date)]

    by_cat = defaultdict(float)
    by_vehicle = defaultdict(float)
    for r in in_range:
        by_cat[r["category"]] += r["amount"]
        if r.get("vehicle_id"):
            by_vehicle[r["vehicle_id"]] += r["amount"]

    vmap = {v["id"]: v.get("vehicle_number", "") for v in await db.vehicles.find({}, {"_id": 0, "id": 1, "vehicle_number": 1}).to_list(3000)}
    vehicle_rows = sorted(
        [{"vehicle_id": k, "vehicle_number": vmap.get(k, "—"), "amount": round(v, 2)} for k, v in by_vehicle.items()],
        key=lambda x: -x["amount"],
    )

    # Cost per km within range
    tq = {}
    if start_date:
        tq["date"] = {"$gte": start_date}
    if end_date:
        tq.setdefault("date", {})
        tq["date"]["$lte"] = end_date
    trips = await db.trips.find(tq, {"_id": 0, "distance": 1, "vehicle_id": 1}).to_list(20000)
    total_km = sum(t.get("distance") or 0 for t in trips)
    total = sum(r["amount"] for r in in_range)

    # 12-month trend from the full ledger
    trend = defaultdict(float)
    for r in ledger:
        m = _month(r.get("date"))
        if m >= trend_start[:7]:
            trend[m] += r["amount"]
    monthly_trend = [{"month": m, "amount": round(a, 2)} for m, a in sorted(trend.items())]

    cur_total = sum(r["amount"] for r in ledger if _month(r.get("date")) == cur_month)
    prev_total = sum(r["amount"] for r in ledger if _month(r.get("date")) == prev_month)

    active_vehicles = await db.vehicles.count_documents({"status": {"$nin": ["sold", "scrapped"]}})
    trip_count = len(trips)

    return {
        "total": round(total, 2),
        "count": len(in_range),
        "current_month": round(cur_total, 2),
        "previous_month": round(prev_total, 2),
        "mom_change_pct": round((cur_total - prev_total) / prev_total * 100, 1) if prev_total else None,
        "by_category": [{"category": c, "amount": round(a, 2)} for c, a in sorted(by_cat.items(), key=lambda x: -x[1])],
        "by_vehicle": vehicle_rows[:15],
        "cost_per_km": round(total / total_km, 2) if total_km else None,
        "cost_per_vehicle": round(total / active_vehicles, 2) if active_vehicles else None,
        "cost_per_trip": round(total / trip_count, 2) if trip_count else None,
        "total_km": round(total_km, 1),
        "monthly_trend": monthly_trend,
    }


@router.get("/expenses/insights")
async def expense_insights(user=Depends(require_module("expenses"))):
    today = datetime.now(timezone.utc)
    cur_month = today.strftime("%Y-%m")
    prev_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    start = (today - timedelta(days=190)).strftime("%Y-%m-%d")
    include_test = user.get("role") == "test"
    ledger = await gather_expenses(start_date=start, include_test=include_test)

    vmap = {v["id"]: v.get("vehicle_number", "") for v in await db.vehicles.find({}, {"_id": 0, "id": 1, "vehicle_number": 1}).to_list(3000)}
    insights = []

    # Highest-cost vehicles (last 90 days)
    cutoff = (today - timedelta(days=90)).strftime("%Y-%m-%d")
    by_vehicle = defaultdict(float)
    for r in ledger:
        if (r.get("date") or "") >= cutoff and r.get("vehicle_id"):
            by_vehicle[r["vehicle_id"]] += r["amount"]
    top = sorted(by_vehicle.items(), key=lambda x: -x[1])[:3]
    if top:
        insights.append({
            "type": "top_cost_vehicles", "severity": "info",
            "title": "Highest-cost vehicles (90 days)",
            "detail": ", ".join(f"{vmap.get(k, '—')} ₹{round(v):,}" for k, v in top),
        })

    # Month-on-month category spikes (>40% and >₹2000)
    cur_cat, prev_cat = defaultdict(float), defaultdict(float)
    for r in ledger:
        m = _month(r.get("date"))
        if m == cur_month:
            cur_cat[r["category"]] += r["amount"]
        elif m == prev_month:
            prev_cat[r["category"]] += r["amount"]
    for cat, amt in cur_cat.items():
        prev = prev_cat.get(cat, 0)
        if prev > 0 and amt > prev * 1.4 and (amt - prev) > 2000:
            insights.append({
                "type": "category_spike", "severity": "warning",
                "title": f"{cat} spend up {round((amt - prev) / prev * 100)}% this month",
                "detail": f"₹{round(prev):,} last month → ₹{round(amt):,} so far this month",
            })

    # High repair frequency (3+ repairs in 90 days)
    repair_freq = defaultdict(int)
    for r in ledger:
        if r["category"] == "Repair" and (r.get("date") or "") >= cutoff and r.get("vehicle_id"):
            repair_freq[r["vehicle_id"]] += 1
    for vid, n in repair_freq.items():
        if n >= 3:
            insights.append({
                "type": "repair_frequency", "severity": "warning",
                "title": f"{vmap.get(vid, '—')} — {n} repairs in the last 90 days",
                "detail": "Frequent repairs may indicate a recurring mechanical problem worth investigating.",
            })

    # Duplicate expense suspicion (manual entries: same vehicle+date+amount+category)
    manual = await db.expenses.find({"is_test_data": {"$ne": True}}, {"_id": 0}).to_list(10000)
    seen, dupes = {}, 0
    for e in manual:
        key = (e.get("vehicle_id"), e.get("date"), e.get("amount"), e.get("category"))
        if key in seen:
            dupes += 1
        seen[key] = True
    if dupes:
        insights.append({
            "type": "duplicate_suspicion", "severity": "warning",
            "title": f"{dupes} possible duplicate manual expense entr{'y' if dupes == 1 else 'ies'}",
            "detail": "Entries share the same vehicle, date, category and amount. Review the manual ledger.",
        })

    # Manual expenses without attachments
    no_attach = sum(1 for e in manual if not e.get("file_id"))
    if no_attach:
        insights.append({
            "type": "missing_attachments", "severity": "info",
            "title": f"{no_attach} manual expense entr{'y has' if no_attach == 1 else 'ies have'} no attachment",
            "detail": "Attach invoices or receipts to keep the ledger audit-ready.",
        })

    # Budget overshoot for current month
    budgets = await db.budgets.find({"month": cur_month}, {"_id": 0}).to_list(200)
    for b in budgets:
        actual = cur_cat.get(b["category"], 0)
        if b.get("amount") and actual > b["amount"]:
            insights.append({
                "type": "budget_overshoot", "severity": "critical",
                "title": f"{b['category']} is over budget",
                "detail": f"Budget ₹{round(b['amount']):,} · Actual ₹{round(actual):,} ({round(actual / b['amount'] * 100)}%)",
            })

    if not insights:
        insights.append({
            "type": "all_clear", "severity": "info",
            "title": "No anomalies detected",
            "detail": "Spending patterns look normal based on the data recorded so far.",
        })
    return {"insights": insights, "generated_at": today.isoformat()}


# ---------- Budgets ----------

@router.get("/budgets")
async def list_budgets(month: str = None, user=Depends(require_module("expenses"))):
    q = {"month": month} if month else {}
    return await db.budgets.find(q, {"_id": 0}).sort("month", -1).to_list(500)


@router.post("/budgets")
async def create_budget(payload: dict = Body(...), user=Depends(require_role("management", "admin", "data_entry"))):
    category = payload.get("category")
    month = payload.get("month")
    amount = payload.get("amount")
    if not category or category not in BUDGET_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid budget category")
    if not month or len(month) != 7:
        raise HTTPException(status_code=400, detail="Month must be in YYYY-MM format")
    if not isinstance(amount, (int, float)) or amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be a positive number")
    existing = await db.budgets.find_one({"category": category, "month": month}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail=f"A {category} budget already exists for {month}")
    doc = {"id": str(uuid.uuid4()), "category": category, "month": month, "amount": amount,
           "created_at": datetime.now(timezone.utc).isoformat(), "created_by": user["user_id"]}
    await db.budgets.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/budgets/{bid}")
async def update_budget(bid: str, payload: dict = Body(...), user=Depends(require_role("management", "admin", "data_entry"))):
    amount = payload.get("amount")
    if not isinstance(amount, (int, float)) or amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be a positive number")
    res = await db.budgets.update_one({"id": bid}, {"$set": {"amount": amount}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Budget not found")
    return await db.budgets.find_one({"id": bid}, {"_id": 0})


@router.delete("/budgets/{bid}")
async def delete_budget(bid: str, user=Depends(require_role("management", "admin"))):
    await db.budgets.delete_one({"id": bid})
    return {"ok": True}


@router.get("/budgets/status")
async def budget_status(month: str = None, user=Depends(require_module("expenses"))):
    month = month or datetime.now(timezone.utc).strftime("%Y-%m")
    budgets = await db.budgets.find({"month": month}, {"_id": 0}).to_list(200)
    include_test = user.get("role") == "test"
    ledger = await gather_expenses(start_date=f"{month}-01", end_date=f"{month}-31", include_test=include_test)
    actual = defaultdict(float)
    for r in ledger:
        actual[r["category"]] += r["amount"]
    rows = []
    for b in budgets:
        a = round(actual.get(b["category"], 0), 2)
        rows.append({
            "id": b["id"], "category": b["category"], "month": month,
            "budget": b["amount"], "actual": a,
            "variance": round(b["amount"] - a, 2),
            "variance_pct": round((a - b["amount"]) / b["amount"] * 100, 1) if b["amount"] else None,
            "over_budget": a > b["amount"],
        })
    unbudgeted = [{"category": c, "actual": round(a, 2)} for c, a in sorted(actual.items(), key=lambda x: -x[1])
                  if c not in {b["category"] for b in budgets} and a > 0]
    return {"month": month, "rows": rows, "unbudgeted": unbudgeted, "categories": BUDGET_CATEGORIES}
