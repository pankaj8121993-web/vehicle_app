"""
Pytest configuration shared by the FleetFlow backend test suite.

The legacy session teardown that logged in as the seeded default users and
reset their passwords has been removed: SEC-001 removed startup user seeding,
so there are no fixed default credentials to restore. Live-URL integration
tests now read their credentials from environment variables (see
``live_credentials`` below) and skip when those are not provided.
"""
import os
import sys
import uuid
from pathlib import Path

import pytest

# The supported invocation is from the repository root (`python -m pytest
# backend/tests`). Make backend modules importable before pytest imports test
# modules; relying on a caller's working directory made local focused runs pass
# while the documented command and CI failed during collection.
BACKEND_DIR = str(Path(__file__).resolve().parents[1])
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Test clients use plain local HTTP. Set these before `server` or `auth` can
# load backend/.env; otherwise the development cross-site-cookie setting makes
# every real-HTTP session Secure/SameSite=None and httpx correctly declines to
# send it back over HTTP, turning authenticated integration tests into 401s.
os.environ["APP_ENV"] = "test"
os.environ["FLEETFLOW_CROSS_SITE_COOKIES"] = "false"

# TEN-TEST: point the whole suite at a dedicated, disposable database *before*
# anything imports `database` (which resolves DB_NAME at import time).
#
# conftest is loaded before any test module, and python-dotenv does not override
# an existing environment variable, so this wins over backend/.env. Tests
# therefore never read or write the running application's database — previously
# importing `database` in a test bound it to whatever DB_NAME the dev container
# happened to have.
# A unique name per pytest process prevents an interrupted run, a developer
# server, or another CI job from sharing state with this suite. Individual
# real-HTTP modules may still drop/reseed this database because pytest runs
# them serially in this process.
TEST_DB_PREFIX = "fleetflow_automated_tests"
TEST_RUN_ID = os.environ.get("FLEETFLOW_TEST_RUN_ID") or uuid.uuid4().hex[:12]
TEST_DB_NAME = f"{TEST_DB_PREFIX}_{TEST_RUN_ID}"
os.environ["DB_NAME"] = TEST_DB_NAME

if os.environ.get("PYTEST_XDIST_WORKER"):
    raise RuntimeError(
        "FleetFlow database-backed tests must run serially; pytest-xdist is unsupported"
    )


# --- Shared event loop for real-HTTP test modules -----------------------------
#
# The real-app test modules (test_tenant_isolation_matrix, test_authz_enforcement)
# drive the running FastAPI app over an event loop. Motor's client binds to the
# first loop that uses it, so if each module owned its own loop they would work
# in isolation but collide when run together — the second module's operations
# would hit a client bound to the first module's (possibly closed) loop.
#
# One process-wide loop, owned here and never closed by a test module, removes
# that coupling. Modules call realhttp_run() instead of asyncio.run().
import asyncio  # noqa: E402

_SHARED_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_SHARED_LOOP)


def realhttp_run(coro):
    """Drive a coroutine on the shared loop bound to the Motor client."""
    return _SHARED_LOOP.run_until_complete(coro)


# Integration test roles and the environment variables that supply their
# credentials. No credentials are hardcoded; supply them per environment.
LIVE_CRED_ROLES = ("admin", "management", "data_entry", "driver", "test")


def _read_live_credentials():
    """Return (creds_by_role, missing_roles) from FLEETFLOW_TEST_* env vars."""
    creds = {}
    missing = []
    for role in LIVE_CRED_ROLES:
        user = os.environ.get(f"FLEETFLOW_TEST_{role.upper()}_USER")
        password = os.environ.get(f"FLEETFLOW_TEST_{role.upper()}_PASS")
        if not user or not password:
            missing.append(role)
        else:
            creds[role] = (user, password)
    return creds, missing


def require_live_credentials():
    """Return creds dict, or skip the whole module with a clear reason."""
    creds, missing = _read_live_credentials()
    if missing:
        pytest.skip(
            "Live integration credentials not provided. Set "
            "FLEETFLOW_TEST_<ROLE>_USER / _PASS for roles: "
            + ", ".join(missing),
            allow_module_level=True,
        )
    return creds


@pytest.fixture(scope="session")
def live_credentials():
    return require_live_credentials()


@pytest.fixture(scope="session", autouse=True)
def disposable_database():
    """Drop stale same-run state before and after the complete suite."""
    from database import client
    import routes_core

    realhttp_run(client.drop_database(TEST_DB_NAME))
    objects = {}
    original_put = routes_core.put_object
    original_get = routes_core.get_object

    def test_put(path, data, content_type):
        objects[path] = (bytes(data), content_type)
        return {"path": path}

    def test_get(path):
        return objects[path]

    # Storage is an external integration, not the database under test. Keeping
    # it in process makes file-security HTTP tests deterministic while all file
    # metadata and tenant scoping continue through real MongoDB.
    routes_core.put_object = test_put
    routes_core.get_object = test_get
    yield
    routes_core.put_object = original_put
    routes_core.get_object = original_get
    realhttp_run(client.drop_database(TEST_DB_NAME))
    current_org_id = __import__("database").current_org_id
    current_org_id.set(None)
