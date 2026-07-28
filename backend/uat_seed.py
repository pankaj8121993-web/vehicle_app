"""
Phase 4 — Synthetic UAT/staging seed.

Populates two isolated organisations ("UAT Alpha", "UAT Bravo") with records in
every lifecycle state the Phase 3 workflows can reach, so business testers can
exercise the UAT scenarios against realistic data. It is deliberately synthetic:

* passwords are random throwaways (never a real/default credential);
* no real personal documents or confidential data;
* every record is marked ``is_uat: True`` and lives under a dedicated org id, so
  it is trivially separable from any other data and safe to wipe.

Usage (against a *staging* database only — never production):

    DB_NAME=fleetflow_uat python -m uat_seed            # seed both orgs
    DB_NAME=fleetflow_uat python -m uat_seed --wipe     # wipe UAT orgs then seed

The seeder writes directly through ``database.raw_db`` using the same field
shapes the API writes, so the seeded records behave in the app and in the
reconciliation/exception services.
"""
import argparse
import asyncio
import secrets
import uuid
from datetime import datetime, timezone, timedelta

from passlib.hash import bcrypt

from database import raw_db, TENANT_COLLECTIONS

ALPHA = "org-uat-alpha"
BRAVO = "org-uat-bravo"
UAT_ORGS = (ALPHA, BRAVO)

# All eight named roles get a login in Alpha so role-enforcement scenarios can be
# run by real testers. Bravo gets an admin only (enough for cross-tenant checks).
ROLES = ["org_admin", "owner", "fleet_manager", "operations",
         "maintenance", "driver", "accounts", "viewer"]

_NOW = datetime.now(timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%d")


def _now_iso():
    return _NOW.isoformat()


async def _wipe():
    for org in UAT_ORGS:
        await raw_db.organizations.delete_many({"id": org})
        await raw_db.users.delete_many({"org_id": org})
        for coll in TENANT_COLLECTIONS:
            await raw_db[coll].delete_many({"org_id": org})
        await raw_db.expense_payments.delete_many({"org_id": org})
        await raw_db.exception_acks.delete_many({"org_id": org})


def _base(org, extra=None):
    d = {"id": str(uuid.uuid4()), "org_id": org, "is_test_data": False,
         "is_uat": True, "created_at": _now_iso(), "created_by": "uat_seed"}
    d.update(extra or {})
    return d


async def _org(org, name):
    await raw_db.organizations.update_one(
        {"id": org},
        {"$set": {
            "id": org, "legal_name": name, "legal_name_lc": name.lower(),
            "trade_name": name, "org_type": "Logistics Business",
            "city": "Pune", "state": "Maharashtra", "country": "India",
            "currency": "INR", "timezone": "Asia/Kolkata", "fy_start_month": 4,
            "is_uat": True, "onboarding_completed": True,
            "compliance_docs": ["RC", "Insurance", "Fitness", "Permit", "PUC", "Road Tax"],
            "created_at": _now_iso(),
        }},
        upsert=True,
    )


async def _users(org, roles):
    creds = {}
    for role in roles:
        username = f"uat_{org.split('-')[-1]}_{role}"
        pw = secrets.token_urlsafe(12)
        creds[role] = (username, pw)
        await raw_db.users.update_one(
            {"username": username},
            {"$set": {
                "id": str(uuid.uuid4()), "org_id": org, "username": username,
                "email": f"{username}@uat.fleetflow.invalid",
                "password_hash": bcrypt.hash(pw),
                "role": role, "full_name": role.replace("_", " ").title(),
                "is_active": True, "is_uat": True, "must_change_password": False,
                "created_at": _now_iso(), "created_by": "uat_seed",
            }},
            upsert=True,
        )
    return creds


async def _seed_org(org, name, *, full):
    await _org(org, name)
    roles = ROLES if full else ["org_admin"]
    creds = await _users(org, roles)
    if not full:
        # Bravo only needs a couple of records to prove cross-tenant isolation.
        v = _base(org, {"vehicle_number": "BR-01 UAT 0001", "make": "Tata",
                        "status": "active", "current_odometer": 10000})
        await raw_db.vehicles.insert_one(v)
        d = _base(org, {"name": "Bravo Driver", "status": "active",
                        "license_number": "BRV-UAT-0001",
                        "license_expiry": _iso(_NOW + timedelta(days=365))})
        await raw_db.drivers.insert_one(d)
        return creds

    # ---- Vehicles across statuses -------------------------------------------
    vids = []
    veh_specs = [
        ("MH12 UAT 0001", "active", 48500), ("MH12 UAT 0002", "active", 61200),
        ("MH14 UAT 0003", "active", 83400), ("MH12 UAT 0004", "inactive", 39800),
        ("MH14 UAT 0005", "maintenance", 112000), ("MH12 UAT 0006", "sold", 90000),
    ]
    for num, status, odo in veh_specs:
        v = _base(org, {"vehicle_number": num, "make": "Tata", "model": "407",
                        "vtype": "LCV", "fuel_type": "diesel", "status": status,
                        "current_odometer": odo,
                        "fastag_number": f"FTUAT{secrets.randbelow(10**9):09d}",
                        "fastag_balance": 850})
        if status == "sold":
            v["disposal_date"] = _iso(_NOW - timedelta(days=30))
            v["sale_value"] = 250000
        vids.append(v["id"])
        await raw_db.vehicles.insert_one(v)

    # ---- Drivers (active + exited) ------------------------------------------
    dids = []
    drv_specs = [("Active One", "active", 400), ("Active Two", "active", 25),
                 ("Active Three", "active", 700), ("Exited Four", "resigned", 120)]
    for i, (nm, status, lic_days) in enumerate(drv_specs):
        d = _base(org, {"name": nm, "mobile": f"90000000{i:02d}",
                        "license_number": f"UAT-LIC-{i:04d}",
                        "license_expiry": _iso(_NOW + timedelta(days=lic_days)),
                        "status": status})
        if status == "resigned":
            d["exit_date"] = _iso(_NOW - timedelta(days=15))
        dids.append(d["id"])
        await raw_db.drivers.insert_one(d)

    # ---- Trips across the full lifecycle ------------------------------------
    def trip(status, extra=None):
        base = {"date": _iso(_NOW - timedelta(days=3)), "vehicle_id": vids[0],
                "driver_id": dids[0], "origin": "Pune", "destination": "Mumbai",
                "opening_km": 48500, "status": status, "distance": None}
        base.update(extra or {})
        return _base(org, base)
    await raw_db.trips.insert_one(trip("planned", {"vehicle_id": None, "driver_id": None}))
    await raw_db.trips.insert_one(trip("assigned", {"vehicle_id": vids[1], "driver_id": dids[1]}))
    await raw_db.trips.insert_one(trip("ongoing", {"vehicle_id": vids[2], "driver_id": dids[2]}))
    completed = trip("completed", {"closing_km": 48655, "distance": 155})
    await raw_db.trips.insert_one(completed)
    await raw_db.trips.insert_one(trip("settlement_pending", {"closing_km": 48700, "distance": 200}))
    await raw_db.trips.insert_one(trip("closed", {"closing_km": 48800, "distance": 300}))
    await raw_db.trips.insert_one(trip("cancelled", {"cancel_reason": "customer cancelled"}))

    # ---- Expenses across approval/payment states ----------------------------
    def expense(status, amount, extra=None):
        e = {"vehicle_id": vids[0], "category": "Miscellaneous",
             "date": _iso(_NOW - timedelta(days=2)), "amount": amount,
             "approval_status": status, "approved_amount": None, "paid_amount": 0,
             "trip_id": completed["id"]}
        e.update(extra or {})
        return _base(org, e)
    await raw_db.expenses.insert_one(expense("submitted", 1000))
    approved_unpaid = expense("approved", 2000, {"approved_amount": 2000})
    await raw_db.expenses.insert_one(approved_unpaid)
    approved_paid = expense("approved", 3000, {"approved_amount": 3000, "paid_amount": 3000})
    await raw_db.expenses.insert_one(approved_paid)
    await raw_db.expense_payments.insert_one(_base(org, {
        "expense_id": approved_paid["id"], "kind": "payment", "amount": 3000,
        "date": _iso(_NOW - timedelta(days=1))}))
    await raw_db.expenses.insert_one(expense("rejected", 500, {"rejection_reason": "no receipt"}))

    # ---- Advances -----------------------------------------------------------
    await raw_db.advances.insert_one(_base(org, {
        "driver_id": dids[0], "trip_id": completed["id"], "date": _iso(_NOW - timedelta(days=4)),
        "amount": 1500, "status": "outstanding", "recovered_amount": 0}))
    await raw_db.advances.insert_one(_base(org, {
        "driver_id": dids[1], "date": _iso(_NOW - timedelta(days=10)),
        "amount": 1000, "status": "recovered", "recovered_amount": 1000}))

    # ---- Repairs + downtime -------------------------------------------------
    for i, status in enumerate(["open", "under_review", "approved", "in_repair", "closed"]):
        r = _base(org, {"vehicle_id": vids[i % len(vids)], "repair_type": "major",
                        "issue": f"UAT repair {status}", "date": _iso(_NOW - timedelta(days=5)),
                        "cost": 5000, "status": status,
                        "ticket_number": f"TKT-UAT-{i:04d}"})
        await raw_db.repairs.insert_one(r)
        if status == "in_repair":
            await raw_db.downtimes.insert_one(_base(org, {
                "vehicle_id": r["vehicle_id"], "reason": "breakdown",
                "start_date": _iso(_NOW - timedelta(days=5)), "status": "open",
                "days": None, "repair_id": r["id"]}))
    await raw_db.downtimes.insert_one(_base(org, {
        "vehicle_id": vids[0], "reason": "service", "start_date": _iso(_NOW - timedelta(days=20)),
        "end_date": _iso(_NOW - timedelta(days=18)), "days": 3, "status": "closed",
        "closure_reason": "service complete"}))

    # ---- Tyres in multiple states + events ----------------------------------
    for i, status in enumerate(["active", "removed", "scrapped"]):
        t = _base(org, {"vehicle_id": vids[0], "tyre_number": f"UAT-TYRE-{i:04d}",
                        "brand": "Apollo", "status": status,
                        "installation_date": _iso(_NOW - timedelta(days=200)),
                        "installation_km": 30000})
        if status in ("removed", "scrapped"):
            t["removal_km"] = 60000
        await raw_db.tyres.insert_one(t)
        if status == "scrapped":
            await raw_db.tyre_events.insert_one(_base(org, {
                "tyre_id": t["id"], "vehicle_id": vids[0], "event_type": "scrap",
                "date": _iso(_NOW - timedelta(days=1)), "odometer": 60000, "notes": "worn out"}))

    # ---- Documents: valid / expiring / expired (+ supersede chain) ----------
    doc_specs = [("RC", 900), ("Insurance", 20), ("PUC", -5)]
    for doc_type, offset in doc_specs:
        await raw_db.documents.insert_one(_base(org, {
            "vehicle_id": vids[0], "doc_type": doc_type, "doc_number": f"{doc_type}-UAT",
            "issue_date": _iso(_NOW - timedelta(days=365)),
            "expiry_date": _iso(_NOW + timedelta(days=offset)), "is_current": True}))
    # A superseded Insurance (history preserved).
    await raw_db.documents.insert_one(_base(org, {
        "vehicle_id": vids[1], "doc_type": "Insurance", "doc_number": "INS-OLD",
        "issue_date": _iso(_NOW - timedelta(days=730)),
        "expiry_date": _iso(_NOW - timedelta(days=10)), "is_current": False,
        "superseded_by": "uat-newer", "superseded_at": _now_iso()}))

    # ---- Accidents + claims across states -----------------------------------
    for i, cs in enumerate(["reported", "approved", "settled", "closed"]):
        a = _base(org, {"vehicle_id": vids[0], "driver_id": dids[0],
                        "date": _iso(_NOW - timedelta(days=30 + i)),
                        "location": "NH48", "description": "Minor collision",
                        "claim_status": cs, "claim_amount": 20000, "repair_cost": 12000})
        if cs in ("approved", "settled", "closed"):
            a["approved_amount"] = 18000
        if cs in ("settled", "closed"):
            a["settlement_amount"] = 18000
        await raw_db.accidents.insert_one(a)

    # ---- FASTag + fuel ------------------------------------------------------
    await raw_db.fastag_transactions.insert_one(_base(org, {
        "vehicle_id": vids[0], "txn_type": "toll", "date": _iso(_NOW - timedelta(days=2)),
        "toll_plaza": "Khed Shivapur", "amount": 120}))
    await raw_db.fastag_transactions.insert_one(_base(org, {
        "vehicle_id": vids[0], "txn_type": "recharge", "date": _iso(_NOW - timedelta(days=3)),
        "amount": 1000}))
    await raw_db.fuel_entries.insert_one(_base(org, {
        "vehicle_id": vids[0], "driver_id": dids[0], "date": _iso(_NOW - timedelta(days=2)),
        "odometer": 48600, "quantity": 40, "amount": 3800, "station": "HP Hadapsar"}))

    return creds


async def seed_uat(wipe=False):
    if wipe:
        await _wipe()
    alpha_creds = await _seed_org(ALPHA, "UAT Alpha Logistics Pvt Ltd", full=True)
    bravo_creds = await _seed_org(BRAVO, "UAT Bravo Transport Pvt Ltd", full=False)
    return {"alpha": alpha_creds, "bravo": bravo_creds}


async def _main():
    parser = argparse.ArgumentParser(description="Seed synthetic UAT data (staging only).")
    parser.add_argument("--wipe", action="store_true", help="wipe UAT orgs before seeding")
    args = parser.parse_args()
    creds = await seed_uat(wipe=args.wipe)
    print(f"UAT seed complete for DB '{raw_db.name}'.")
    print("Login credentials (synthetic — staging only):")
    for org, roles in creds.items():
        for role, (user, pw) in roles.items():
            print(f"  [{org}] {role:14s} {user}  /  {pw}")


if __name__ == "__main__":
    asyncio.run(_main())
