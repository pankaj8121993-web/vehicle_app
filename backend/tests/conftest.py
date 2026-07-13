"""
Pytest conftest for Rajguru Fleet backend tests.

Session-scoped teardown resets all seeded users back to their default
passwords listed in `/app/memory/test_credentials.md` so manual UI logins
keep working after test runs.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://vehicle-central-17.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ROTATIONS = {
    "admin":       ("admin",      "rajguru@2026",    "Admin@Test1"),
    "manager":     ("manager",    "manager@2026",    "Mgmt@Test1"),
    "dataentry1":  ("dataentry1", "dataentry@2026",  "Data@Test1"),
    "driver1":     ("driver1",    "driver@2026",     "Driver@Test1"),
    "test":        ("test",       "test@2026",       "Test@Test1"),
}


@pytest.fixture(scope="session", autouse=True)
def _restore_default_passwords():
    yield
    # Post-test teardown: revert to original seeded passwords
    for _, (username, original, rotated) in ROTATIONS.items():
        try:
            r = requests.post(f"{API}/auth/login",
                              json={"username": username, "password": rotated},
                              timeout=10)
            if r.status_code != 200:
                continue  # Already at original
            tok = r.json()["token"]
            requests.post(f"{API}/auth/change-password",
                          headers={"Authorization": f"Bearer {tok}"},
                          json={"current_password": rotated, "new_password": original},
                          timeout=10)
        except Exception:
            pass  # Best-effort teardown; never fail the run
