import os
import logging
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

from database import client
import auth
import routes_core
import routes_ops
import routes_assets
import routes_analytics
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

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    try:
        init_storage()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed (uploads will retry lazily): {e}")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
