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


SAFE_DB = re.compile(r"^fleetflow_role_e2e_[a-f0-9]{8,32}$")
ROLES = (
    "org_admin", "owner", "fleet_manager", "operations",
    "maintenance", "accounts", "driver", "viewer",
)


def guard(database: str, mongo_url: str) -> None:
    if not SAFE_DB.fullmatch(database):
        raise SystemExit("Refusing fixture operation: unsafe role-E2E database name")
    if not any(host in mongo_url for host in ("localhost", "127.0.0.1", "mongodb")):
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
        credentials[role] = {"username": username, "password": password}
    await db.users.insert_many(users)
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
    print(json.dumps({
        "database": args.database, "run_id": run_id, "org_id": org_id,
        "other_org_id": other_org_id, "vehicle_id": f"{run_id}-vehicle",
        "foreign_vehicle_id": f"{run_id}-foreign-vehicle",
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
