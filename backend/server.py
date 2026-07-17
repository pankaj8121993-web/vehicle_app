import os
import logging
from fastapi import FastAPI, APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from database import client, raw_db, TENANT_COLLECTIONS
from tenant_policy import TenantViolation
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
import routes_orgs
import routes_expenses
from storage import init_storage

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="FleetFlow — Complete Fleet Operations Management")

api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"message": "FleetFlow API", "tagline": "Complete Fleet Operations Management"}


api_router.include_router(auth.router)
api_router.include_router(routes_orgs.router)
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
api_router.include_router(routes_expenses.router)

app.include_router(api_router)


@app.exception_handler(TenantViolation)
async def _tenant_violation_handler(request: Request, exc: TenantViolation):
    """TEN-01 last-resort guard.

    Routes reject protected fields before the database layer is reached, so a
    TenantViolation means a code path tried to write across organisations. Log it
    as an error for investigation and fail closed with an opaque response — the
    client learns nothing about the tenancy model or the offending record.
    """
    logger.error(
        "Tenant ownership violation on %s %s: %s",
        request.method, request.url.path, exc,
    )
    return JSONResponse(status_code=400, content={"detail": "Invalid request"})


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


# Organisation id used ONLY to tag pre-multi-tenancy legacy records during
# migration (_migrate_org_ids). Startup never creates this organisation or any
# user — the first administrator is provisioned manually via `bootstrap.py`.
DEFAULT_ORG_ID = "org-rajguru-foods"


@app.on_event("startup")
async def startup():
    try:
        init_storage()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed (uploads will retry lazily): {e}")

    # NOTE: Ordinary startup must never create, reset, disable or modify any
    # user or organisation. The first admin is created out-of-band by running
    # `python -m bootstrap create-admin` (see docs/implementation/BOOTSTRAP.md).
    await _migrate_org_ids()
    await _ensure_indexes()
    # Ticket system migrations (Checkpoint 4) — idempotent
    await _migrate_repair_statuses()
    await _backfill_ticket_numbers()


async def _migrate_org_ids():
    """Assign every legacy record (pre multi-tenancy) to the default organisation."""
    total = 0
    for coll in TENANT_COLLECTIONS:
        res = await raw_db[coll].update_many(
            {"org_id": {"$exists": False}}, {"$set": {"org_id": DEFAULT_ORG_ID}}
        )
        total += res.modified_count
    if total:
        logger.info(f"Multi-tenancy migration: tagged {total} legacy records with default org_id")


async def _ensure_indexes():
    try:
        for coll in TENANT_COLLECTIONS:
            await raw_db[coll].create_index("org_id")
        await raw_db.users.create_index("username", unique=True)
        await raw_db.user_sessions.create_index("token")
        await raw_db.organizations.create_index("id", unique=True)
    except Exception as e:
        logger.warning(f"Index creation issue: {e}")


async def _migrate_repair_statuses():
    """Map legacy 4-state repair flow to new 7-state ticket flow."""
    mapping = {"reported": "open", "completed": "closed"}
    for old, new in mapping.items():
        res = await raw_db.repairs.update_many({"status": old}, {"$set": {"status": new}})
        if res.modified_count:
            logger.info(f"Migrated {res.modified_count} repairs: {old} → {new}")


async def _backfill_ticket_numbers():
    """Assign TKT-YYYY-NNNN to any repair record missing ticket_number."""
    repairs = await raw_db.repairs.find(
        {"ticket_number": {"$in": [None, ""]}}, {"_id": 0, "id": 1, "date": 1}
    ).sort("date", 1).to_list(20000)
    missing = await raw_db.repairs.find(
        {"ticket_number": {"$exists": False}}, {"_id": 0, "id": 1, "date": 1}
    ).sort("date", 1).to_list(20000)
    seen = {r["id"] for r in repairs}
    for m in missing:
        if m["id"] not in seen:
            repairs.append(m)
    if not repairs:
        return
    existing_by_year = {}
    async for r in raw_db.repairs.find(
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
        await raw_db.repairs.update_one({"id": r["id"]}, {"$set": {"ticket_number": ticket_num}})
    logger.info(f"Backfilled ticket numbers for {len(repairs)} repair records")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
