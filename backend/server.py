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


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
