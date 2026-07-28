import os
import logging
from fastapi import FastAPI, APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from database import client, raw_db, TENANT_COLLECTIONS
from tenant_policy import TenantViolation
import atomicity
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
import routes_settlement
import routes_reconciliation
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
api_router.include_router(routes_settlement.router)
api_router.include_router(routes_reconciliation.router)

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


# AUTH-01: sessions now ride in a cookie, so CORS correctness is a security
# control rather than a convenience. `allow_credentials=True` with
# `allow_origins=["*"]` is rejected outright by browsers for credentialed
# requests, and echoing an arbitrary origin back with credentials would let any
# site read authenticated responses. So: an explicit allowlist, and credentials
# are only enabled when one is configured.
_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
_cors_allowlisted = bool(_cors_origins) and "*" not in _cors_origins

if not _cors_allowlisted:
    logger.warning(
        "CORS_ORIGINS is unset or wildcard — credentialed cross-origin requests "
        "are disabled. Set CORS_ORIGINS to an explicit comma-separated allowlist "
        "for cookie authentication to work across origins."
    )

app.add_middleware(
    CORSMiddleware,
    allow_credentials=_cors_allowlisted,
    allow_origins=_cors_origins if _cors_allowlisted else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    """SEC-CLOSEOUT: baseline security headers on every response.

    This is a JSON API, so the set is deliberately small and safe:
    * nosniff — never let a browser re-interpret a response's content type;
    * X-Frame-Options: DENY — API responses are never meant to be framed;
    * Referrer-Policy: no-referrer — do not leak URLs to third parties;
    * HSTS — only in production, where the deployment is HTTPS. Emitting it from
      the plain-HTTP preview would pin browsers to HTTPS for a host that does not
      serve it.
    The file-download endpoints add their own stricter CSP/`no-store` on top.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if os.environ.get("APP_ENV", "development").lower() == "production":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


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
    await _migrate_file_org_ids()
    await _migrate_plaintext_sessions()
    await _ensure_indexes()
    # Ticket system migrations (Checkpoint 4) — idempotent
    await _migrate_repair_statuses()
    await _backfill_ticket_numbers()
    # DI-01: organisation-scoped uniqueness. Runs after the backfills so
    # ticket_number is populated before its unique index is attempted.
    await _ensure_integrity_indexes()
    # DI-02: idempotency-key index + one-time transaction-support probe.
    await _ensure_idempotency_indexes()
    await atomicity.probe_transactions()


# FILE-01: files are excluded from the blanket default-org backfill below.
# A file's owner is knowable from its uploader, so assigning every pre-FILE-01
# file to DEFAULT_ORG_ID would misfile other organisations' documents into the
# default organisation — a data-integrity fault and a cross-tenant disclosure.
# _migrate_file_org_ids() derives the real owner instead.
DEFAULT_ORG_BACKFILL_COLLECTIONS = TENANT_COLLECTIONS - {"files"}

# Files whose uploader cannot be resolved are parked here rather than guessed at.
# No session ever carries this org_id, so such files fail closed (404) until an
# operator reassigns them.
UNRESOLVED_FILE_ORG_ID = "org-unresolved-quarantine"


async def _migrate_org_ids():
    """Assign every legacy record (pre multi-tenancy) to the default organisation."""
    total = 0
    for coll in DEFAULT_ORG_BACKFILL_COLLECTIONS:
        res = await raw_db[coll].update_many(
            {"org_id": {"$exists": False}}, {"$set": {"org_id": DEFAULT_ORG_ID}}
        )
        total += res.modified_count
    if total:
        logger.info(f"Multi-tenancy migration: tagged {total} legacy records with default org_id")


async def _migrate_file_org_ids():
    """FILE-01: give every pre-existing file record its real owning organisation.

    Derived from the uploading user, which is the only trustworthy signal on a
    legacy record. Idempotent: only touches files that have no org_id yet.
    """
    missing = await raw_db.files.count_documents({"org_id": {"$exists": False}})
    if not missing:
        return

    # uploaded_by -> org_id, resolved in one pass rather than per file.
    owners = {}
    async for u in raw_db.users.find({}, {"_id": 0, "id": 1, "org_id": 1}):
        if u.get("org_id"):
            owners[u["id"]] = u["org_id"]

    resolved = 0
    quarantined = 0
    async for f in raw_db.files.find(
        {"org_id": {"$exists": False}}, {"_id": 0, "id": 1, "uploaded_by": 1}
    ):
        org_id = owners.get(f.get("uploaded_by"))
        if not org_id:
            org_id = UNRESOLVED_FILE_ORG_ID
            quarantined += 1
        else:
            resolved += 1
        await raw_db.files.update_one({"id": f["id"]}, {"$set": {"org_id": org_id}})

    logger.info(
        "FILE-01 migration: assigned owning organisation to %d file(s) from their uploader",
        resolved,
    )
    if quarantined:
        logger.warning(
            "FILE-01 migration: %d file(s) have no resolvable uploader and were "
            "quarantined as '%s'. They are unreachable until an operator "
            "reassigns them; this is deliberate (fail closed).",
            quarantined, UNRESOLVED_FILE_ORG_ID,
        )


async def _migrate_plaintext_sessions():
    """AUTH-01: retire every session that predates token hashing.

    Old rows hold the token in plaintext under "token". They cannot be migrated
    in place — hashing the stored value would keep a token that has already been
    exposed in the database working, which is the whole point of the change.

    So they are revoked instead. Existing users are asked to log in once; that is
    the intended, safe cost of the migration and is far better than carrying
    known-exposed tokens forward. Idempotent.
    """
    stale = await raw_db.user_sessions.count_documents({"token": {"$exists": True}})
    if not stale:
        return
    await raw_db.user_sessions.update_many(
        {"token": {"$exists": True}},
        {
            "$set": {"revoked": True, "revoked_reason": "auth01_plaintext_migration"},
            "$unset": {"token": ""},   # do not keep the plaintext value around
        },
    )
    logger.warning(
        "AUTH-01 migration: revoked %d pre-hashing session(s) and removed their "
        "plaintext tokens. Affected users must sign in again — deliberate.",
        stale,
    )


async def _ensure_indexes():
    try:
        for coll in TENANT_COLLECTIONS:
            await raw_db[coll].create_index("org_id")
        await raw_db.users.create_index("username", unique=True)
        await raw_db.organizations.create_index("id", unique=True)
        # AUTH-01: sessions are looked up by token hash; the raw "token" index
        # is gone along with the plaintext field.
        await raw_db.user_sessions.create_index("token_hash")
        await raw_db.user_sessions.create_index("user_id")
        # TTL: Mongo deletes expired sessions itself, so a revoked or lapsed
        # session cannot linger as a replayable row. Requires a BSON date, which
        # is why absolute_expires_at is stored as a datetime, not an ISO string.
        await raw_db.user_sessions.create_index("absolute_expires_at", expireAfterSeconds=0)
        # Failed-login records are only needed for the throttle window.
        await raw_db.login_attempts.create_index("at", expireAfterSeconds=3600)
        await raw_db.login_attempts.create_index([("username", 1), ("at", -1)])
        await raw_db.login_attempts.create_index([("ip", 1), ("at", -1)])
    except Exception as e:
        logger.warning(f"Index creation issue: {e}")


# DI-01: organisation-scoped uniqueness indexes. Each is a compound index on
# (org_id, <natural key>) so the same vehicle number / tyre serial / ticket
# number can exist in different organisations but never twice within one. Built
# with a partial filter so records missing the key (legacy/optional) do not
# collide on null.
#
# Created best-effort and independently: on a database that already holds a
# duplicate, the unique build raises, and we log a warning and continue rather
# than crash startup. The DI-04 integrity scanner reports those duplicates so an
# operator can resolve them; only then will the index build succeed. Nothing
# here deletes or rewrites data.
_INTEGRITY_INDEXES = [
    ("vehicles", [("org_id", 1), ("vehicle_number", 1)], "uniq_org_vehicle_number",
     {"vehicle_number": {"$type": "string"}}),
    ("tyres", [("org_id", 1), ("tyre_number", 1)], "uniq_org_tyre_number",
     {"tyre_number": {"$type": "string"}}),
    ("repairs", [("org_id", 1), ("ticket_number", 1)], "uniq_org_ticket_number",
     {"ticket_number": {"$type": "string"}}),
]


async def _ensure_integrity_indexes():
    for coll, keys, name, partial in _INTEGRITY_INDEXES:
        try:
            await raw_db[coll].create_index(
                keys, name=name, unique=True,
                partialFilterExpression=partial,
            )
        except Exception as e:
            logger.warning(
                "DI-01: could not build unique index %s on %s (likely existing "
                "duplicates — run check_data_integrity.py to find them): %s",
                name, coll, e,
            )


async def _ensure_idempotency_indexes():
    """DI-02: unique key claim + TTL expiry for idempotency records.

    The unique (org_id, scope, key) index is the atomic claim mechanism — the
    first inserter wins, a concurrent duplicate hits DuplicateKeyError. The TTL
    reaps old keys so the collection cannot grow without bound; 24h is far longer
    than any legitimate client retry window.
    """
    try:
        await raw_db.idempotency_keys.create_index(
            [("org_id", 1), ("scope", 1), ("key", 1)],
            name="uniq_org_scope_key", unique=True,
        )
        await raw_db.idempotency_keys.create_index(
            "created_at_dt", name="idem_ttl", expireAfterSeconds=86400,
        )
    except Exception as e:
        logger.warning("DI-02: idempotency index creation issue: %s", e)


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
