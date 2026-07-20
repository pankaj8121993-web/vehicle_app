"""
WF-01 — Protected workflow transitions.

The defect class: generic CRUD could drive operational state directly —
`PUT /vehicles/{id}` with `{"status": "sold"}` disposed a vehicle (or, worse,
`{"status": "active"}` *un-disposed* one), a status could jump straight from
`open` to `closed` skipping the states between, and a trip could be re-closed.

Two layers: unit tests over the pure engine, and real-HTTP tests proving the
generic update endpoints cannot bypass the state graphs and that concurrent
transitions cannot both win.
"""
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

import server  # noqa: E402
import database  # noqa: E402
import session_security as ss  # noqa: E402
import workflow as wf
from workflow import (
    STATUS_WORKFLOWS,
    check_version,
    enforce_generic_status_change,
    next_version,
    validate_transition,
)

from conftest import realhttp_run as _run  # shared loop (see conftest)


# --- Engine unit tests --------------------------------------------------------

def test_valid_transition_ok():
    assert validate_transition(wf.VEHICLE_STATUS_WORKFLOW, "active", "maintenance") == "ok"


def test_same_state_is_idempotent_noop():
    assert validate_transition(wf.TRIP_STATUS_WORKFLOW, "completed", "completed") == "noop"


def test_invalid_edge_is_409():
    with pytest.raises(HTTPException) as e:
        validate_transition(wf.REPAIR_WORKFLOW, "open", "closed")  # skips the middle
    assert e.value.status_code == 409


def test_unknown_target_is_400():
    with pytest.raises(HTTPException) as e:
        validate_transition(wf.VEHICLE_STATUS_WORKFLOW, "active", "banana")
    assert e.value.status_code == 400


@pytest.mark.parametrize("wf_obj,terminal", [
    (wf.VEHICLE_STATUS_WORKFLOW, "sold"),
    (wf.VEHICLE_STATUS_WORKFLOW, "scrapped"),
    (wf.DRIVER_STATUS_WORKFLOW, "resigned"),
    (wf.DRIVER_STATUS_WORKFLOW, "terminated"),
    (wf.TRIP_STATUS_WORKFLOW, "completed"),
    (wf.DOWNTIME_STATUS_WORKFLOW, "closed"),
    (wf.REPAIR_WORKFLOW, "closed"),
])
def test_terminal_states_have_no_exit(wf_obj, terminal):
    assert wf_obj.is_terminal(terminal)


def test_cannot_leave_a_terminal_state():
    """The exact bug: un-disposing a vehicle."""
    with pytest.raises(HTTPException) as e:
        validate_transition(wf.VEHICLE_STATUS_WORKFLOW, "sold", "active")
    assert e.value.status_code == 409


@pytest.mark.parametrize("role,ok", [
    ("admin", True), ("management", True),
    ("data_entry", False), ("driver", False), ("viewer", False),
])
def test_disposal_role_enforced(role, ok):
    if ok:
        assert validate_transition(wf.VEHICLE_STATUS_WORKFLOW, "active", "sold", role=role) == "ok"
    else:
        with pytest.raises(HTTPException) as e:
            validate_transition(wf.VEHICLE_STATUS_WORKFLOW, "active", "sold", role=role)
        assert e.value.status_code == 403


def test_driver_exit_role_enforced():
    with pytest.raises(HTTPException) as e:
        validate_transition(wf.DRIVER_STATUS_WORKFLOW, "active", "resigned", role="data_entry")
    assert e.value.status_code == 403


def test_none_current_uses_initial():
    """A record with no status yet is treated as its initial state."""
    assert validate_transition(wf.TRIP_STATUS_WORKFLOW, None, "completed") == "ok"


# --- Version / optimistic concurrency ----------------------------------------

def test_version_match_passes():
    check_version({"_version": 3}, 3)  # no raise


def test_version_mismatch_is_409():
    with pytest.raises(HTTPException) as e:
        check_version({"_version": 3}, 1)
    assert e.value.status_code == 409


def test_no_expected_version_skips_check():
    check_version({"_version": 3}, None)  # opted out, no raise


def test_next_version_increments():
    assert next_version({"_version": 4}) == 5
    assert next_version({}) == 1


# --- enforce_generic_status_change -------------------------------------------

def test_generic_status_change_valid_returns_true():
    assert enforce_generic_status_change(
        "vehicles", {"status": "active"}, {"status": "maintenance"}, role="admin"
    ) is True


def test_generic_status_change_unchanged_returns_false():
    assert enforce_generic_status_change(
        "vehicles", {"status": "active"}, {"notes": "x"}, role="admin"
    ) is False


def test_generic_status_change_non_workflow_collection_is_free():
    """A plain-label status (e.g. vendors) is not workflow-controlled."""
    assert enforce_generic_status_change(
        "vendors", {"status": "active"}, {"status": "inactive"}, role="admin"
    ) is False


def test_generic_status_change_invalid_raises():
    with pytest.raises(HTTPException) as e:
        enforce_generic_status_change(
            "vehicles", {"status": "sold"}, {"status": "active"}, role="admin"
        )
    assert e.value.status_code == 409


def test_every_status_workflow_is_a_real_workflow():
    for name, w in STATUS_WORKFLOWS.items():
        assert isinstance(w, wf.Workflow)
        assert w.states


# --- Real HTTP: generic update cannot bypass the workflow ---------------------

class _Client:
    def __init__(self, client, org_id):
        self.client = client
        self.org_id = org_id

    def _h(self, m):
        if m in ss.SAFE_METHODS:
            return {}
        c = self.client.cookies.get(ss.CSRF_COOKIE)
        return {ss.CSRF_HEADER: c} if c else {}

    async def req(self, m, u, **kw):
        kw.setdefault("headers", {}).update(self._h(m))
        return await self.client.request(m, u, **kw)


async def _demo(role):
    t = ASGITransport(app=server.app)
    c = AsyncClient(transport=t, base_url="http://wf")
    r = await c.post("/api/demo/enter", json={"role": role})
    assert r.status_code == 200, r.text[:200]
    return _Client(c, r.json()["user"]["org_id"])


@pytest.fixture(scope="module")
def env():
    async def build():
        await database.client.drop_database(database.raw_db.name)
        admin = await _demo("org_admin")
        de = await _demo("operations")   # data_entry tier
        return {"admin": admin, "de": de}

    e = _run(build())
    yield e

    async def teardown():
        await e["admin"].client.aclose()
        await e["de"].client.aclose()
        await database.client.drop_database(database.raw_db.name)

    _run(teardown())


def _make_vehicle(client, status="active"):
    r = _run(client.req("POST", "/api/vehicles",
             json={"vehicle_number": f"WF-{status}-{id(client)%9999}"}))
    assert r.status_code == 200, r.text[:200]
    return r.json()["id"]


def test_generic_update_cannot_undispose_a_vehicle(env):
    vid = _make_vehicle(env["admin"])
    # Dispose it properly.
    r = _run(env["admin"].req("PUT", f"/api/vehicles/{vid}", json={"status": "sold"}))
    assert r.status_code == 200, r.text[:200]
    # Now try to un-dispose via generic update.
    r2 = _run(env["admin"].req("PUT", f"/api/vehicles/{vid}", json={"status": "active"}))
    assert r2.status_code == 409, f"un-dispose -> {r2.status_code}"


def test_generic_update_disposal_requires_privilege(env):
    vid = _make_vehicle(env["admin"])
    r = _run(env["de"].req("PUT", f"/api/vehicles/{vid}", json={"status": "scrapped"}))
    assert r.status_code == 403, f"data_entry dispose -> {r.status_code}"
    # And the vehicle is untouched.
    got = _run(env["admin"].req("GET", "/api/vehicles", params={"all": "true"})).json()
    vlist = got if isinstance(got, list) else got.get("items", [])
    v = next(x for x in vlist if x["id"] == vid)
    assert v["status"] != "scrapped"


def test_generic_update_allows_valid_status_change(env):
    vid = _make_vehicle(env["admin"])
    r = _run(env["admin"].req("PUT", f"/api/vehicles/{vid}", json={"status": "maintenance"}))
    assert r.status_code == 200, r.text[:200]


def test_repair_invalid_transition_is_rejected(env):
    vid = _make_vehicle(env["admin"])
    rep = _run(env["admin"].req("POST", "/api/repairs", json={
        "vehicle_id": vid, "repair_type": "major", "issue": "Brake", "date": "2026-01-01"}))
    assert rep.status_code == 200, rep.text[:200]
    rid = rep.json()["id"]
    # open -> closed skips the middle of the flow.
    r = _run(env["admin"].req("PATCH", f"/api/repairs/{rid}/status", json={"status": "closed"}))
    assert r.status_code == 409, f"invalid repair jump -> {r.status_code}"


def test_repair_concurrent_transition_is_rejected(env):
    """Optimistic concurrency: two advances from the same version cannot both
    win — no double approval."""
    vid = _make_vehicle(env["admin"])
    rep = _run(env["admin"].req("POST", "/api/repairs", json={
        "vehicle_id": vid, "repair_type": "major", "issue": "Clutch", "date": "2026-01-01"}))
    rid = rep.json()["id"]
    # First advance at version 0 succeeds.
    a = _run(env["admin"].req("PATCH", f"/api/repairs/{rid}/status",
             json={"status": "under_review", "expected_version": 0}))
    assert a.status_code == 200, a.text[:200]
    # A second advance still quoting version 0 is stale.
    b = _run(env["admin"].req("PATCH", f"/api/repairs/{rid}/status",
             json={"status": "under_review", "expected_version": 0}))
    assert b.status_code == 409, f"stale transition -> {b.status_code}"


def test_trip_double_close_is_idempotent(env):
    vid = _make_vehicle(env["admin"])
    trip = _run(env["admin"].req("POST", "/api/trips", json={
        "date": "2026-01-01", "vehicle_id": vid, "opening_km": 100}))
    tid = trip.json()["id"]
    first = _run(env["admin"].req("PATCH", f"/api/trips/{tid}/close", json={"closing_km": 200}))
    assert first.status_code == 200
    assert first.json()["distance"] == 100
    # Re-close with a different km must NOT recompute distance/odometer.
    second = _run(env["admin"].req("PATCH", f"/api/trips/{tid}/close", json={"closing_km": 999}))
    assert second.status_code == 200
    assert second.json()["distance"] == 100, "re-close recomputed distance"


def test_downtime_cannot_be_reopened_via_generic_update(env):
    vid = _make_vehicle(env["admin"])
    dt = _run(env["admin"].req("POST", "/api/downtime", json={
        "vehicle_id": vid, "reason": "service", "start_date": "2026-01-01",
        "end_date": "2026-01-03"}))  # end_date → created closed
    assert dt.status_code == 200, dt.text[:200]
    did = dt.json()["id"]
    if dt.json().get("status") == "closed":
        r = _run(env["admin"].req("PUT", f"/api/downtime/{did}", json={"status": "open"}))
        assert r.status_code == 409, f"downtime reopen -> {r.status_code}"
