#!/usr/bin/env python3
"""Create or remove the isolated, real-auth Playwright role fixture."""
import argparse
import asyncio
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse


SAFE_DB = re.compile(r"^fleetflow_role_e2e_[a-f0-9]{8,32}$")
ROLES = (
    "org_admin", "owner", "fleet_manager", "operations",
    "maintenance", "accounts", "driver", "viewer",
)


def guard(database: str, mongo_url: str) -> None:
    if os.environ.get("FLEETFLOW_ROLE_E2E_ALLOW") != "true":
        raise SystemExit("Refusing fixture operation: explicit role-E2E safety flag is required")
    if not SAFE_DB.fullmatch(database):
        raise SystemExit("Refusing fixture operation: unsafe role-E2E database name")
    hostname = urlparse(mongo_url).hostname
    if hostname not in {"localhost", "127.0.0.1", "mongodb"}:
        raise SystemExit("Refusing fixture operation: MongoDB must be local or a test container")
    if os.environ.get("APP_ENV", "test").lower() == "production":
        raise SystemExit("Refusing fixture operation in production")


async def run(args) -> None:
    from motor.motor_asyncio import AsyncIOMotorClient
    from passlib.hash import bcrypt

    guard(args.database, args.mongo_url)
    client = AsyncIOMotorClient(args.mongo_url, serverSelectionTimeoutMS=5000)
    await client.admin.command("ping")
    if args.action == "teardown":
        await client.drop_database(args.database)
        client.close()
        return

    password = os.environ.get("FLEETFLOW_ROLE_E2E_PASSWORD")
    run_id = os.environ.get("FLEETFLOW_ROLE_E2E_RUN_ID")
    if not password or len(password) < 24 or not run_id:
        raise SystemExit("Run-generated role E2E password and run id are required")

    await client.drop_database(args.database)
    db = client[args.database]
    now = datetime.now(timezone.utc).isoformat()
    org_id = f"role-e2e-org-{run_id}"
    other_org_id = f"role-e2e-other-{run_id}"
    await db.organizations.insert_many([
        {
            "id": org_id, "legal_name": "Synthetic Role Matrix Limited",
            "trade_name": "Role Matrix Fleet", "is_demo": False,
            "created_at": now, "fixture_run_id": run_id,
        },
        {
            "id": other_org_id, "legal_name": "Synthetic Isolation Limited",
            "trade_name": "Isolation Fleet", "is_demo": False,
            "created_at": now, "fixture_run_id": run_id,
        },
    ])
    password_hash = bcrypt.hash(password)
    users = []
    credentials = {}
    for role in ROLES:
        username = f"uxr1_{run_id}_{role}"
        users.append({
            "id": str(uuid.uuid4()), "username": username,
            "password_hash": password_hash, "full_name": f"UX R1 {role.replace('_', ' ').title()}",
            "role": role, "org_id": org_id, "is_active": True,
            "is_demo": False, "must_change_password": False,
            "created_at": now, "fixture_run_id": run_id,
        })
        credentials[role] = {"username": username}
    await db.users.insert_many(users)
    await db.users.insert_one({
        "id": str(uuid.uuid4()), "username": f"uxr1_{run_id}_foreign_admin",
        "password_hash": password_hash, "full_name": "UX R1 Foreign Administrator",
        "role": "org_admin", "org_id": other_org_id, "is_active": True,
        "is_demo": False, "must_change_password": False,
        "created_at": now, "fixture_run_id": run_id,
    })
    await db.vehicles.insert_many([
        {
            "id": f"{run_id}-vehicle", "org_id": org_id,
            "vehicle_number": f"UXR1-{run_id.upper()}", "make": "Synthetic",
            "model": "Matrix", "status": "active", "current_odometer": 100,
            "created_at": now, "fixture_run_id": run_id,
        },
        {
            "id": f"{run_id}-foreign-vehicle", "org_id": other_org_id,
            "vehicle_number": f"FOREIGN-{run_id.upper()}", "make": "Synthetic",
            "model": "Isolation", "status": "active", "current_odometer": 100,
            "created_at": now, "fixture_run_id": run_id,
        },
    ])
    trip_id = f"{run_id}-domain-trip"
    expense_id = f"{run_id}-domain-expense"
    await db.trips.insert_one({
        "id": trip_id, "org_id": org_id, "vehicle_id": f"{run_id}-vehicle",
        "date": "2026-07-28", "purpose": "UX-R1 domain action",
        "status": "ongoing", "opening_km": 100, "created_by": users[3]["id"],
        "created_at": now, "fixture_run_id": run_id,
    })
    await db.expenses.insert_one({
        "id": expense_id, "org_id": org_id, "vehicle_id": f"{run_id}-vehicle",
        "date": "2026-07-28", "category": "Maintenance", "description": "UX-R1 approval",
        "amount": 500, "approval_status": "submitted", "status": "submitted",
        "created_by": users[3]["id"], "created_at": now, "fixture_run_id": run_id,
    })
    # Every collection used below contains a realistic Organisation A record and
    # an Organisation B counterpart.  Tests deliberately query these through
    # the application so accidental removal of tenant filters is observable.
    representative = {
        "drivers": {"name": "Synthetic Driver", "license_number": f"LIC-{run_id}", "status": "active"},
        "fuel_entries": {"vehicle_id": f"{run_id}-vehicle", "litres": 42.5, "amount": 4250, "status": "verified"},
        "fastag_transactions": {"vehicle_id": f"{run_id}-vehicle", "amount": 185, "plaza": "Synthetic Toll", "status": "matched"},
        "repairs": {"vehicle_id": f"{run_id}-vehicle", "description": "Brake inspection", "status": "approved", "estimated_cost": 8500},
        "tyres": {"vehicle_id": f"{run_id}-vehicle", "serial_number": f"TYRE-{run_id}", "status": "fitted"},
        "downtimes": {"vehicle_id": f"{run_id}-vehicle", "reason": "Scheduled maintenance", "status": "open"},
        "documents": {"entity_type": "vehicle", "entity_id": f"{run_id}-vehicle", "name": "Synthetic permit.pdf", "status": "active"},
        "accidents": {"vehicle_id": f"{run_id}-vehicle", "description": "Synthetic minor incident", "status": "reported", "claim_status": "submitted"},
        "vendors": {"name": "Synthetic Workshop", "vendor_type": "maintenance", "status": "active"},
        "exception_acks": {"exception_id": f"{run_id}-exception", "status": "open", "reason": "Synthetic compliance alert"},
    }
    representative_ids = {}
    for collection, fields in representative.items():
        own_id = f"{run_id}-{collection}-a"
        foreign_id = f"{run_id}-{collection}-b"
        representative_ids[collection] = {"own": own_id, "foreign": foreign_id}
        common = {"created_at": now, "fixture_run_id": run_id}
        await db[collection].insert_many([
            {"id": own_id, "org_id": org_id, **fields, **common},
            {"id": foreign_id, "org_id": other_org_id, **fields, **common},
        ])
    # Claims are represented by the claim lifecycle fields on accidents.
    await db.trips.insert_one({
        "id": f"{run_id}-foreign-trip", "org_id": other_org_id,
        "vehicle_id": f"{run_id}-foreign-vehicle", "date": "2026-07-28",
        "purpose": "Tenant isolation", "status": "planned", "opening_km": 50,
        "created_at": now, "fixture_run_id": run_id,
    })
    await db.expenses.insert_one({
        "id": f"{run_id}-foreign-expense", "org_id": other_org_id,
        "vehicle_id": f"{run_id}-foreign-vehicle", "date": "2026-07-28",
        "category": "Fuel", "description": "Tenant isolation", "amount": 100,
        "approval_status": "submitted", "status": "submitted",
        "created_at": now, "fixture_run_id": run_id,
    })
    print(json.dumps({
        "database": args.database, "run_id": run_id, "org_id": org_id,
        "other_org_id": other_org_id, "vehicle_id": f"{run_id}-vehicle",
        "foreign_vehicle_id": f"{run_id}-foreign-vehicle",
        "trip_id": trip_id, "expense_id": expense_id,
        "representative_ids": representative_ids,
        "credentials": credentials,
    }))
    client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("seed", "teardown"))
    parser.add_argument("--database", required=True)
    parser.add_argument("--mongo-url", default="mongodb://127.0.0.1:27017")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except Exception as exc:
        print(f"role fixture failed: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
