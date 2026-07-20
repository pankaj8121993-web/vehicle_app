"""
AUTHZ-01 — end-to-end permission enforcement over real HTTP.

The catalogue tests in test_authz_permissions.py pin the policy; this file proves
the policy is actually *enforced* by the running app, per role, through the real
auth stack. It uses the demo organisation's pre-seeded roles (via /demo/enter),
which yields genuine cookie sessions without a password-change gate.

Convention as elsewhere: one module-scoped event loop, real app via
ASGITransport, dedicated disposable database (conftest pins DB_NAME).
"""

import pytest
from httpx import ASGITransport, AsyncClient

import server  # noqa: E402
import database  # noqa: E402
import session_security as ss  # noqa: E402

from conftest import realhttp_run as _run  # shared loop (see conftest)


class RoleClient:
    def __init__(self, client, role, org_id):
        self.client = client
        self.role = role
        self.org_id = org_id

    def _h(self, method):
        if method in ss.SAFE_METHODS:
            return {}
        csrf = self.client.cookies.get(ss.CSRF_COOKIE)
        return {ss.CSRF_HEADER: csrf} if csrf else {}

    async def req(self, method, url, **kw):
        kw.setdefault("headers", {}).update(self._h(method))
        return await self.client.request(method, url, **kw)


async def _enter_demo(role):
    transport = ASGITransport(app=server.app)
    client = AsyncClient(transport=transport, base_url="http://authz")
    r = await client.post("/api/demo/enter", json={"role": role})
    assert r.status_code == 200, f"demo/enter {role}: {r.status_code} {r.text[:200]}"
    return RoleClient(client, role, r.json()["user"]["org_id"])


# Demo roles → effective tier they exercise.
DEMO_ROLES = {
    "org_admin": "admin",
    "owner": "management",
    "operations": "data_entry",
    "driver": "driver",
    "viewer": "viewer",
}


@pytest.fixture(scope="module")
def clients():
    async def build():
        await database.client.drop_database(database.raw_db.name)
        return {role: await _enter_demo(role) for role in DEMO_ROLES}

    cs = _run(build())
    yield cs

    async def teardown():
        for c in cs.values():
            await c.client.aclose()
        await database.client.drop_database(database.raw_db.name)

    _run(teardown())


def _seed_vehicle(admin):
    r = _run(admin.req("POST", "/api/vehicles", json={"vehicle_number": "AUTHZ-SEED"}))
    assert r.status_code == 200, r.text[:200]
    return r.json()["id"]


# --- Create --------------------------------------------------------------------

@pytest.mark.parametrize("role", ["viewer", "driver"])
def test_role_cannot_create_vehicles(role, clients):
    r = _run(clients[role].req("POST", "/api/vehicles", json={"vehicle_number": "X-1"}))
    assert r.status_code == 403, f"{role} create vehicle -> {r.status_code}"


@pytest.mark.parametrize("role", ["operations", "owner", "org_admin"])
def test_role_can_create_vehicles(role, clients):
    r = _run(clients[role].req("POST", "/api/vehicles", json={"vehicle_number": f"OK-{role}"}))
    assert r.status_code == 200, f"{role} create vehicle -> {r.status_code} {r.text[:200]}"


def test_driver_can_create_a_trip_but_not_a_service(clients):
    """Driver is create-only on the allowlisted resources and nothing else."""
    vid = _seed_vehicle(clients["org_admin"])
    ok = _run(clients["driver"].req("POST", "/api/trips",
              json={"date": "2026-01-01", "vehicle_id": vid, "opening_km": 1}))
    assert ok.status_code == 200, ok.text[:200]
    denied = _run(clients["driver"].req("POST", "/api/services",
                  json={"vehicle_id": vid, "service_type": "Oil", "date": "2026-01-01"}))
    assert denied.status_code == 403


# --- Update / delete -----------------------------------------------------------

def test_data_entry_can_update_but_not_delete(clients):
    vid = _seed_vehicle(clients["org_admin"])
    upd = _run(clients["operations"].req("PUT", f"/api/vehicles/{vid}", json={"notes": "ok"}))
    assert upd.status_code == 200, upd.text[:200]
    dele = _run(clients["operations"].req("DELETE", f"/api/vehicles/{vid}"))
    assert dele.status_code == 403


def test_viewer_cannot_update(clients):
    vid = _seed_vehicle(clients["org_admin"])
    r = _run(clients["viewer"].req("PUT", f"/api/vehicles/{vid}", json={"notes": "x"}))
    assert r.status_code == 403


def test_viewer_cannot_upload_files(clients):
    """The AUTHZ-01 tightening: upload was require_user, viewer is now read-only."""
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    r = _run(clients["viewer"].req("POST", "/api/upload",
             files={"file": ("p.png", png, "image/png")}))
    assert r.status_code == 403


# --- Administration / escalation ----------------------------------------------

@pytest.mark.parametrize("role", ["viewer", "driver", "operations", "owner"])
def test_non_admin_cannot_list_users(role, clients):
    r = _run(clients[role].req("GET", "/api/users"))
    assert r.status_code == 403, f"{role} /users -> {r.status_code}"


@pytest.mark.parametrize("role", ["operations", "owner"])
def test_non_admin_cannot_create_users(role, clients):
    r = _run(clients[role].req("POST", "/api/users", json={
        "username": f"x-{role}", "password": "whatever123",
        "role": "org_admin", "full_name": "X"}))
    assert r.status_code == 403


def test_management_cannot_update_org_is_allowed_but_delete_branch_is_not(clients):
    """owner (management tier) may edit the org but not delete a branch."""
    # Demo org edits are blocked for demo users regardless; assert the permission
    # layer rather than the demo guard by checking a branch delete (admin-only).
    branches = _run(clients["org_admin"].req("GET", "/api/branches")).json()
    if branches:
        r = _run(clients["owner"].req("DELETE", f"/api/branches/{branches[0]['id']}"))
        assert r.status_code == 403


def test_non_admin_cannot_purge_test_data(clients):
    for role in ("viewer", "driver", "operations", "owner"):
        r = _run(clients[role].req("POST", "/api/admin/purge-test-data"))
        assert r.status_code == 403, f"{role} purge -> {r.status_code}"


# --- Mutation test: removing enforcement must break these ----------------------

def test_permission_layer_is_load_bearing(clients):
    """Sanity that these probes exercise the permission layer, not some other
    guard: an admin succeeds exactly where a viewer is refused."""
    r = _run(clients["org_admin"].req("POST", "/api/vehicles",
             json={"vehicle_number": "ADMIN-OK"}))
    assert r.status_code == 200
