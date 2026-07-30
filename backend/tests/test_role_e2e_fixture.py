"""Safety and lifecycle tests for the disposable role-backed browser fixture."""
import asyncio
import os
import re
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.hash import bcrypt

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import role_e2e_fixture as fixture  # noqa: E402


LOCAL_MONGO = os.getenv("MONGO_URL", "mongodb://127.0.0.1:27017")


def _guard(monkeypatch, database="fleetflow_role_e2e_deadbeef", mongo=LOCAL_MONGO):
    monkeypatch.setenv("FLEETFLOW_ROLE_E2E_ALLOW", "true")
    monkeypatch.setenv("APP_ENV", "test")
    fixture.guard(database, mongo)


def test_unique_database_name_and_guard_rejections(monkeypatch):
    first = f"fleetflow_role_e2e_{uuid.uuid4().hex[:12]}"
    second = f"fleetflow_role_e2e_{uuid.uuid4().hex[:12]}"
    assert first != second and re.fullmatch(fixture.SAFE_DB, first)
    _guard(monkeypatch, first)
    with pytest.raises(SystemExit, match="unsafe"):
        fixture.guard("production", LOCAL_MONGO)
    with pytest.raises(SystemExit, match="local"):
        fixture.guard(first, "mongodb://prod.example.com:27017")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(SystemExit, match="production"):
        fixture.guard(first, LOCAL_MONGO)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("FLEETFLOW_ROLE_E2E_ALLOW")
    with pytest.raises(SystemExit, match="safety flag"):
        fixture.guard(first, LOCAL_MONGO)


def test_seed_rerun_and_teardown(monkeypatch, capsys):
    run_id = uuid.uuid4().hex[:12]
    database = f"fleetflow_role_e2e_{run_id}"
    password = uuid.uuid4().hex + uuid.uuid4().hex
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("FLEETFLOW_ROLE_E2E_ALLOW", "true")
    monkeypatch.setenv("FLEETFLOW_ROLE_E2E_RUN_ID", run_id)
    monkeypatch.setenv("FLEETFLOW_ROLE_E2E_PASSWORD", password)
    args = SimpleNamespace(action="seed", database=database, mongo_url=LOCAL_MONGO)
    async def scenario():
        client = AsyncIOMotorClient(LOCAL_MONGO)
        try:
            await fixture.run(args)
            # A second seed simulates recovery after an interrupted prior run.
            await fixture.run(args)
            db = client[database]
            assert await db.organizations.count_documents({}) == 2
            own_users = await db.users.find({"org_id": f"role-e2e-org-{run_id}"}).to_list(None)
            assert {u["role"] for u in own_users} == set(fixture.ROLES)
            assert all(bcrypt.verify(password, u["password_hash"]) for u in own_users)
            for name in ("vehicles", "drivers", "trips", "expenses", "fuel_entries",
                         "fastag_transactions", "repairs", "tyres", "downtimes",
                         "documents", "accidents", "vendors", "exception_acks"):
                assert await db[name].count_documents({}) >= 2
                assert await db[name].count_documents({"org_id": f"role-e2e-other-{run_id}"}) >= 1
            args.action = "teardown"
            await fixture.run(args)
            assert database not in await client.list_database_names()
        finally:
            await client.drop_database(database)
            client.close()

    asyncio.run(scenario())
    output = capsys.readouterr().out
    assert password not in output
    assert "password_hash" not in output
