import os
import contextvars
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

client = AsyncIOMotorClient(os.environ['MONGO_URL'])
raw_db = client[os.environ['DB_NAME']]

# Per-request organisation context — set by auth.require_user
current_org_id = contextvars.ContextVar("current_org_id", default=None)

# Collections automatically scoped to the current organisation
TENANT_COLLECTIONS = {
    "vehicles", "drivers", "documents", "trips", "fuel_entries", "services",
    "repairs", "greasings", "tyres", "tyre_events", "accidents",
    "fastag_transactions", "downtimes", "expenses", "vendors",
    "calendar_events", "compliance_contacts", "budgets", "branches", "users",
}


class TenantCollection:
    """Wraps a Motor collection and injects org_id into every query/insert."""

    def __init__(self, coll, name):
        self._c = coll
        self._tenant = name in TENANT_COLLECTIONS

    def _scope(self, flt):
        org = current_org_id.get()
        if self._tenant and org:
            flt = dict(flt or {})
            flt["org_id"] = org
        return flt if flt is not None else {}

    def find(self, flt=None, *a, **k):
        return self._c.find(self._scope(flt), *a, **k)

    async def find_one(self, flt=None, *a, **k):
        return await self._c.find_one(self._scope(flt), *a, **k)

    async def count_documents(self, flt=None, **k):
        return await self._c.count_documents(self._scope(flt), **k)

    async def insert_one(self, doc, **k):
        org = current_org_id.get()
        if self._tenant and org:
            doc.setdefault("org_id", org)
        return await self._c.insert_one(doc, **k)

    async def insert_many(self, docs, **k):
        org = current_org_id.get()
        if self._tenant and org:
            for d in docs:
                d.setdefault("org_id", org)
        return await self._c.insert_many(docs, **k)

    async def update_one(self, flt, update, **k):
        return await self._c.update_one(self._scope(flt), update, **k)

    async def update_many(self, flt, update, **k):
        return await self._c.update_many(self._scope(flt), update, **k)

    async def delete_one(self, flt, **k):
        return await self._c.delete_one(self._scope(flt), **k)

    async def delete_many(self, flt, **k):
        return await self._c.delete_many(self._scope(flt), **k)

    def aggregate(self, pipeline, **k):
        org = current_org_id.get()
        if self._tenant and org:
            pipeline = [{"$match": {"org_id": org}}] + list(pipeline)
        return self._c.aggregate(pipeline, **k)

    async def distinct(self, key, flt=None, **k):
        return await self._c.distinct(key, self._scope(flt), **k)

    async def create_index(self, *a, **k):
        return await self._c.create_index(*a, **k)


class TenantDB:
    def __init__(self, raw):
        self._raw = raw

    def __getattr__(self, name):
        return TenantCollection(getattr(self._raw, name), name)

    def __getitem__(self, name):
        return TenantCollection(self._raw[name], name)


db = TenantDB(raw_db)
