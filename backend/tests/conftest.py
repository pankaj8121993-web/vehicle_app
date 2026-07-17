"""
Pytest configuration shared by the FleetFlow backend test suite.

The legacy session teardown that logged in as the seeded default users and
reset their passwords has been removed: SEC-001 removed startup user seeding,
so there are no fixed default credentials to restore. Live-URL integration
tests now read their credentials from environment variables (see
``live_credentials`` below) and skip when those are not provided.
"""
import os

import pytest

# TEN-TEST: point the whole suite at a dedicated, disposable database *before*
# anything imports `database` (which resolves DB_NAME at import time).
#
# conftest is loaded before any test module, and python-dotenv does not override
# an existing environment variable, so this wins over backend/.env. Tests
# therefore never read or write the running application's database — previously
# importing `database` in a test bound it to whatever DB_NAME the dev container
# happened to have.
TEST_DB_NAME = "fleetflow_automated_tests"
os.environ["DB_NAME"] = TEST_DB_NAME


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
