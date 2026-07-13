import os
import logging
import uuid as _uuid
from datetime import datetime, timezone
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware
from passlib.hash import bcrypt

from database import client, db
import auth
import routes_core
import routes_ops
import routes_assets
import routes_analytics
import routes_drilldowns
import routes_compliance
import routes_calendar
import routes_fleet_status
import routes_vendors
import routes_search
from storage import init_storage

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Rajguru Foods Fleet Management")

api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"message": "Rajguru Foods Fleet Management API"}


api_router.include_router(auth.router)
api_router.include_router(routes_core.router)
api_router.include_router(routes_ops.router)
api_router.include_router(routes_assets.router)
api_router.include_router(routes_analytics.router)
api_router.include_router(routes_drilldowns.router)
api_router.include_router(routes_compliance.router)
api_router.include_router(routes_calendar.router)
api_router.include_router(routes_fleet_status.router)
api_router.include_router(routes_vendors.router)
api_router.include_router(routes_search.router)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


DEFAULT_USERS = [
    {"username": "admin", "password": "rajguru@2026", "role": "admin", "full_name": "Pankaj (Admin)"},
    {"username": "manager", "password": "manager@2026", "role": "management", "full_name": "Manager"},
    {"username": "dataentry1", "password": "dataentry@2026", "role": "data_entry", "full_name": "Data Entry Operator"},
    {"username": "driver1", "password": "driver@2026", "role": "driver", "full_name": "Driver"},
    {"username": "test", "password": "test@2026", "role": "test", "full_name": "Test User"},
]


@app.on_event("startup")
async def startup():
    try:
        init_storage()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed (uploads will retry lazily): {e}")
    # Seed default users on first boot
    existing = await db.users.count_documents({})
    if existing == 0:
        for u in DEFAULT_USERS:
            await db.users.insert_one({
                "id": str(_uuid.uuid4()),
                "username": u["username"],
                "password_hash": bcrypt.hash(u["password"]),
                "role": u["role"],
                "full_name": u["full_name"],
                "is_active": True,
                "must_change_password": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": "system",
            })
        logger.info(f"Seeded {len(DEFAULT_USERS)} default users")
    # Ticket system migrations (Checkpoint 4) — idempotent
    await _migrate_repair_statuses()
    await _backfill_ticket_numbers()


async def _migrate_repair_statuses():
    """Map legacy 4-state repair flow to new 7-state ticket flow."""
    mapping = {"reported": "open", "completed": "closed"}
    for old, new in mapping.items():
        res = await db.repairs.update_many({"status": old}, {"$set": {"status": new}})
        if res.modified_count:
            logger.info(f"Migrated {res.modified_count} repairs: {old} → {new}")


async def _backfill_ticket_numbers():
    """Assign TKT-YYYY-NNNN to any repair record missing ticket_number."""
    repairs = await db.repairs.find(
        {"ticket_number": {"$in": [None, ""]}}, {"_id": 0, "id": 1, "date": 1}
    ).sort("date", 1).to_list(20000)
    # Also pick up docs missing the field entirely
    missing = await db.repairs.find(
        {"ticket_number": {"$exists": False}}, {"_id": 0, "id": 1, "date": 1}
    ).sort("date", 1).to_list(20000)
    seen = {r["id"] for r in repairs}
    for m in missing:
        if m["id"] not in seen:
            repairs.append(m)
    if not repairs:
        return
    # Find the highest existing ticket number per year so we don't collide
    existing_by_year = {}
    async for r in db.repairs.find(
        {"ticket_number": {"$regex": "^TKT-"}},
        {"_id": 0, "ticket_number": 1},
    ):
        tn = r.get("ticket_number") or ""
        parts = tn.split("-")
        if len(parts) == 3:
            try:
                year = parts[1]
                num = int(parts[2])
                existing_by_year[year] = max(existing_by_year.get(year, 0), num)
            except ValueError:
                pass
    repairs.sort(key=lambda r: r.get("date") or "1970-01-01")
    for r in repairs:
        year = (r.get("date") or "1970-01-01")[:4]
        existing_by_year[year] = existing_by_year.get(year, 0) + 1
        ticket_num = f"TKT-{year}-{existing_by_year[year]:04d}"
        await db.repairs.update_one({"id": r["id"]}, {"$set": {"ticket_number": ticket_num}})
    logger.info(f"Backfilled ticket numbers for {len(repairs)} repair records")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
