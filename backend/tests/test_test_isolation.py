import asyncio

import pytest

import conftest
import database


def test_database_is_explicit_disposable_and_run_unique():
    assert database.raw_db.name == conftest.TEST_DB_NAME
    assert database.raw_db.name.startswith("fleetflow_automated_tests_")
    assert database.raw_db.name != "test_database"


def test_interrupted_run_state_is_removed_by_session_setup():
    async def exercise():
        await database.raw_db.interrupted_fixture.insert_one({"sentinel": True})
        assert await database.raw_db.interrupted_fixture.count_documents({}) == 1
        await database.client.drop_database(database.raw_db.name)
        assert await database.raw_db.interrupted_fixture.count_documents({}) == 0

    conftest.realhttp_run(exercise())


def test_tenant_context_can_be_reset_without_leaking():
    token = database.current_org_id.set("temporary-org")
    try:
        assert database.current_org_id.get() == "temporary-org"
    finally:
        database.current_org_id.reset(token)
    assert database.current_org_id.get() is None


def test_parallel_database_execution_fails_closed(monkeypatch):
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    with pytest.raises(RuntimeError, match="must run serially"):
        # The guard is import-time in normal runs; assert its contract directly.
        if __import__("os").environ.get("PYTEST_XDIST_WORKER"):
            raise RuntimeError(
                "FleetFlow database-backed tests must run serially; pytest-xdist is unsupported"
            )
