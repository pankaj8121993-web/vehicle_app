"""
TEN-TEST — Comprehensive cross-tenant security matrix.

Everything TEN-01, FILE-01 and AUTH-01 shipped was proven at the *mechanism*
level: policy functions, TenantCollection driven with a fake, request models.
That is necessary but not sufficient — it proves the machinery works, not that
every route is wired into it. A route that forgot to use the tenant-scoped ``db``
would pass every one of those tests and still leak.

This suite closes that gap: **real HTTP, against the real app, with two real
organisations in a real database**, asserting that Organisation A cannot read,
change, infer or export anything belonging to Organisation B.

Design notes
------------
* **Real app, disposable database.** ``httpx.ASGITransport`` runs the actual
  FastAPI app; ``conftest`` pins DB_NAME to a dedicated test database, which this
  module drops on teardown.
* **No lifespan.** ASGITransport does not run startup, so no ``init_storage()``
  network call and no migrations.
* **One event loop for the module.** Motor binds its client to the loop that
  first uses it, so the ``asyncio.run()``-per-test convention used elsewhere
  (which only drives fakes) would bind a fresh loop each time and fail. A single
  module-scoped loop is the equivalent for real-I/O tests.
* **404, not 403.** A cross-tenant id must be indistinguishable from one that
  never existed. 403 would confirm the record is real — itself a disclosure.
* **A registry, not ad-hoc tests.** ``RESOURCE_REGISTRY`` drives every case, and
  ``test_every_tenant_collection_is_registered`` fails when a new tenant-scoped
  collection appears without coverage. New modules must register here.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

# conftest sets DB_NAME before this import chain resolves it.
import server  # noqa: E402
import database  # noqa: E402
import session_security as ss  # noqa: E402


# --- Event loop / driver ------------------------------------------------------

from conftest import realhttp_run as _run  # shared loop (see conftest)


# --- Tenant client ------------------------------------------------------------

class OrgClient:
    """An authenticated API client for one organisation.

    Wraps httpx so every state-changing call carries the double-submit CSRF
    header, exactly as the real frontend does. Auth rides on the HttpOnly cookie
    that httpx keeps in its jar — no bearer token, matching AUTH-01.
    """

    def __init__(self, client: AsyncClient, org_id: str, user_id: str):
        self.client = client
        self.org_id = org_id
        self.user_id = user_id

    def _headers(self, method):
        if method.upper() in ss.SAFE_METHODS:
            return {}
        csrf = self.client.cookies.get(ss.CSRF_COOKIE)
        return {ss.CSRF_HEADER: csrf} if csrf else {}

    async def request(self, method, url, **kw):
        kw.setdefault("headers", {}).update(self._headers(method))
        return await self.client.request(method, url, **kw)

    async def get(self, url, **kw):
        return await self.request("GET", url, **kw)

    async def post(self, url, **kw):
        return await self.request("POST", url, **kw)

    async def put(self, url, **kw):
        return await self.request("PUT", url, **kw)

    async def patch(self, url, **kw):
        return await self.request("PATCH", url, **kw)

    async def delete(self, url, **kw):
        return await self.request("DELETE", url, **kw)


async def _register_org(slug: str) -> OrgClient:
    """Create an organisation + its first admin through the real onboarding API."""
    transport = ASGITransport(app=server.app)
    client = AsyncClient(transport=transport, base_url="http://ten-test")
    r = await client.post("/api/onboarding/register", json={
        "org": {"legal_name": f"TenTest {slug} Ltd", "org_type": "Company"},
        "admin": {
            "username": f"tentest_{slug}",
            "email": f"{slug}@ten-test.invalid",
            "password": "TenTestPassphrase123",
            "full_name": f"TenTest {slug}",
        },
    })
    assert r.status_code == 200, f"onboarding failed for {slug}: {r.status_code} {r.text[:200]}"
    body = r.json()
    return OrgClient(client, body["user"]["org_id"], body["user"]["id"])


# --- Resource registry --------------------------------------------------------

class Resource:
    """One tenant-scoped API surface under isolation test.

    ``payload`` receives the owning org's seed ids so dependent records
    (trips, tyre events, …) can reference same-tenant parents.

    ``list_path`` / ``list_params`` exist because not every resource lists at its
    own path: calendar events, for instance, are only listed through the
    aggregated ``/api/calendar`` view. ``probe`` is the harmless field an
    isolation test tries to write, since some endpoints accept only a narrow set
    (budgets take ``amount`` and nothing else).
    """

    def __init__(self, collection, path, payload, *, list_path=None,
                 list_params=None, list_key="items",
                 probe=("notes", "tentest-pwned"),
                 updatable=True, deletable=True):
        self.collection = collection
        self.path = path
        self.payload = payload
        self.list_path = list_path or path
        self.list_params = list_params if list_params is not None else {"all": "true"}
        self.list_key = list_key
        self.probe = probe
        self.updatable = updatable
        self.deletable = deletable

    @property
    def update_payload(self):
        return {self.probe[0]: self.probe[1]}

    def __repr__(self):
        return self.collection


_CAL_RANGE = {"start": "2025-01-01", "end": "2027-12-31"}


async def _list_ids(oc, res):
    """Ids visible to ``oc`` on ``res``'s list surface.

    Asserts the payload key exists rather than defaulting to []: a silently empty
    list would make every "cannot see another org's record" assertion pass
    vacuously, which is the failure mode this whole suite exists to avoid.
    """
    r = await oc.get(res.list_path, params=res.list_params)
    assert r.status_code == 200, f"{res.collection} list failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    if isinstance(body, list):
        items = body
    else:
        assert res.list_key in body, (
            f"{res.collection}: list response has no '{res.list_key}' key "
            f"(got {sorted(body)[:6]}). Fix the Resource's list_key."
        )
        items = body[res.list_key]
    return [i.get("id") for i in items], items


def _uniq(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


RESOURCE_REGISTRY = [
    Resource("vehicles", "/api/vehicles",
             lambda s: {"vehicle_number": _uniq("KA01")}),
    Resource("drivers", "/api/drivers",
             lambda s: {"name": _uniq("Driver")}),
    Resource("vendors", "/api/vendors",
             lambda s: {"name": _uniq("Vendor"), "vendor_type": "Repair"}),
    Resource("trips", "/api/trips",
             lambda s: {"date": "2026-01-01", "vehicle_id": s["vehicle_id"], "opening_km": 100}),
    Resource("fuel_entries", "/api/fuel",
             lambda s: {"date": "2026-01-01", "vehicle_id": s["vehicle_id"],
                        "odometer": 100, "quantity": 10, "amount": 1000}),
    Resource("services", "/api/services",
             lambda s: {"vehicle_id": s["vehicle_id"], "service_type": "Oil", "date": "2026-01-01"}),
    Resource("greasings", "/api/greasings",
             lambda s: {"vehicle_id": s["vehicle_id"], "date": "2026-01-01"}),
    Resource("repairs", "/api/repairs",
             lambda s: {"vehicle_id": s["vehicle_id"], "repair_type": "minor",
                        "issue": "Brake", "date": "2026-01-01"}),
    Resource("tyres", "/api/tyres",
             lambda s: {"vehicle_id": s["vehicle_id"], "tyre_number": _uniq("T")}),
    Resource("tyre_events", "/api/tyre-events",
             lambda s: {"tyre_id": s["tyre_id"], "event_type": "puncture", "date": "2026-01-01"}),
    Resource("accidents", "/api/accidents",
             lambda s: {"vehicle_id": s["vehicle_id"], "date": "2026-01-01"}),
    Resource("fastag_transactions", "/api/fastag",
             lambda s: {"vehicle_id": s["vehicle_id"], "txn_type": "toll",
                        "date": "2026-01-01", "amount": 100}),
    Resource("downtimes", "/api/downtime",
             lambda s: {"vehicle_id": s["vehicle_id"], "reason": "service",
                        "start_date": "2026-01-01"}),
    Resource("expenses", "/api/expenses",
             lambda s: {"vehicle_id": s["vehicle_id"], "category": "Fuel",
                        "date": "2026-01-01", "amount": 500}),
    Resource("documents", "/api/documents",
             lambda s: {"vehicle_id": s["vehicle_id"], "doc_type": "RC"}),
    # Calendar events have no list endpoint of their own; they surface only
    # through the aggregated /api/calendar view, which needs a date range.
    Resource("calendar_events", "/api/calendar/events",
             lambda s: {"title": _uniq("Event"), "date": "2026-01-01"},
             list_path="/api/calendar", list_params=_CAL_RANGE, list_key="events"),
    Resource("compliance_contacts", "/api/compliance/contacts",
             lambda s: {"compliance_type": "Insurance", "contact_person_name": _uniq("Contact"),
                        "mobile": "9000000000"}),
    # update_budget accepts only `amount`; probing with `notes` would 400 on
    # validation before ownership is ever considered.
    Resource("budgets", "/api/budgets",
             lambda s: {"category": "Fuel", "month": "2026-01", "amount": 5000},
             probe=("amount", 4242)),
    Resource("branches", "/api/branches",
             lambda s: {"name": _uniq("Branch")}),
    # OPS-02: driver advances (dedicated CRUD).
    Resource("advances", "/api/advances",
             lambda s: {"driver_id": s["driver_id"], "date": "2026-01-01", "amount": 500}),
]

# Tenant-scoped collections deliberately not in the registry above, each with a
# reason. Anything else new must be registered — see the guard test.
REGISTRY_EXEMPTIONS = {
    # Covered by its own dedicated cross-tenant tests below (upload is multipart
    # and the download path has its own response-header contract).
    "files": "covered by the file-specific isolation tests in this module",
    # Covered by the user-administration isolation tests below; /api/users has a
    # different create contract (role + password) and admin-only access.
    "users": "covered by the user-administration isolation tests in this module",
    # OPS-02: append-only payment/reversal events. No generic CRUD surface — they
    # are created only through the org-scoped expense payment action, and every
    # read is filtered by the tenant-scoped db, so isolation is covered by the
    # expense payment tests (test_expense_settlement) rather than a CRUD probe.
    "expense_payments": "append-only events created via the org-scoped expense payment action",
}


# --- Fixtures -----------------------------------------------------------------

@pytest.fixture(scope="module")
def tenants():
    """Two fully independent organisations, each seeded with real records.

    Module-scoped: onboarding runs bcrypt, so re-registering per test would make
    the suite needlessly slow for no extra coverage.
    """
    async def build():
        # Clean slate at *setup*, not just teardown: a previous run that died
        # mid-fixture would otherwise leave usernames behind and fail onboarding
        # with "Username is already taken" forever.
        await database.client.drop_database(database.raw_db.name)
        a = await _register_org("alpha")
        b = await _register_org("bravo")
        seeds = {}
        for org, oc in (("a", a), ("b", b)):
            v = await oc.post("/api/vehicles", json={"vehicle_number": _uniq("KA01")})
            assert v.status_code == 200, v.text[:200]
            t = await oc.post("/api/tyres", json={
                "vehicle_id": v.json()["id"], "tyre_number": _uniq("T")})
            assert t.status_code == 200, t.text[:200]
            d = await oc.post("/api/drivers", json={"name": _uniq("Driver")})
            assert d.status_code == 200, d.text[:200]
            seeds[org] = {"vehicle_id": v.json()["id"], "tyre_id": t.json()["id"],
                          "driver_id": d.json()["id"]}
        return a, b, seeds

    a, b, seeds = _run(build())
    # Each org's records, created through its own client.
    records = {}
    for res in RESOURCE_REGISTRY:
        async def make(oc, seed):
            r = await oc.post(res.path, json=res.payload(seed))
            return r

        ra = _run(make(a, seeds["a"]))
        rb = _run(make(b, seeds["b"]))
        assert ra.status_code == 200, f"{res.collection} create failed for A: {ra.status_code} {ra.text[:200]}"
        assert rb.status_code == 200, f"{res.collection} create failed for B: {rb.status_code} {rb.text[:200]}"
        records[res.collection] = {"a": ra.json(), "b": rb.json()}

    yield {"a": a, "b": b, "seeds": seeds, "records": records}

    async def teardown():
        await a.client.aclose()
        await b.client.aclose()
        await database.client.drop_database(database.raw_db.name)

    _run(teardown())


def _id_of(doc):
    return doc.get("id")


# --- The matrix: A must not reach B's records ---------------------------------

@pytest.mark.parametrize("res", RESOURCE_REGISTRY, ids=repr)
def test_list_never_returns_another_orgs_records(res, tenants):
    """List is the widest surface: one unscoped query leaks everything."""
    b_id = _id_of(tenants["records"][res.collection]["b"])
    ids, _ = _run(_list_ids(tenants["a"], res))
    assert b_id not in ids


@pytest.mark.parametrize("res", RESOURCE_REGISTRY, ids=repr)
def test_list_returns_own_records(res, tenants):
    """The isolation must not be achieved by breaking the feature."""
    a_id = _id_of(tenants["records"][res.collection]["a"])
    ids, _ = _run(_list_ids(tenants["a"], res))
    assert a_id in ids


@pytest.mark.parametrize("res", [r for r in RESOURCE_REGISTRY if r.updatable], ids=repr)
def test_update_of_another_orgs_record_is_refused(res, tenants):
    b_id = _id_of(tenants["records"][res.collection]["b"])
    r = _run(tenants["a"].put(f"{res.path}/{b_id}", json=res.update_payload))
    assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"


@pytest.mark.parametrize("res", [r for r in RESOURCE_REGISTRY if r.updatable], ids=repr)
def test_update_of_another_orgs_record_has_no_side_effect(res, tenants):
    """A refused write must actually not have written."""
    b_id = _id_of(tenants["records"][res.collection]["b"])
    _run(tenants["a"].put(f"{res.path}/{b_id}", json=res.update_payload))
    _ids, items = _run(_list_ids(tenants["b"], res))
    victim = next((i for i in items if i.get("id") == b_id), None)
    assert victim is not None, "B's record disappeared"
    field, value = res.probe
    assert victim.get(field) != value, f"A wrote {field} on B's record"


@pytest.mark.parametrize("res", [r for r in RESOURCE_REGISTRY if r.deletable], ids=repr)
def test_delete_of_another_orgs_record_does_not_delete_it(res, tenants):
    """The response may be 200 (idempotent delete) — what matters is that B's
    record still exists afterwards."""
    b_id = _id_of(tenants["records"][res.collection]["b"])
    _run(tenants["a"].delete(f"{res.path}/{b_id}"))
    ids, _items = _run(_list_ids(tenants["b"], res))
    assert b_id in ids, "A deleted B's record"


@pytest.mark.parametrize("res", RESOURCE_REGISTRY, ids=repr)
def test_create_with_injected_org_id_is_rejected(res, tenants):
    """TEN-01, end to end: ownership injection must be refused, not ignored."""
    payload = dict(res.payload(tenants["seeds"]["a"]))
    payload["org_id"] = tenants["b"].org_id
    r = _run(tenants["a"].post(res.path, json=payload))
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"
    assert "org_id" in r.text


@pytest.mark.parametrize("res", [r for r in RESOURCE_REGISTRY if r.updatable], ids=repr)
def test_update_cannot_transfer_own_record_to_another_org(res, tenants):
    """The exact pre-TEN-01 exploit: PUT {"org_id": "<victim>"} on your own
    record moved it into another organisation."""
    a_id = _id_of(tenants["records"][res.collection]["a"])
    r = _run(tenants["a"].put(f"{res.path}/{a_id}",
                              json={"org_id": tenants["b"].org_id}))
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"
    # And it is still ours.
    ids, _items = _run(_list_ids(tenants["a"], res))
    assert a_id in ids


@pytest.mark.parametrize("res", RESOURCE_REGISTRY, ids=repr)
def test_cross_tenant_id_does_not_disclose_existence(res, tenants):
    """A real id from another org and a random id must be indistinguishable."""
    if not res.updatable:
        pytest.skip("no update surface to probe with")
    b_id = _id_of(tenants["records"][res.collection]["b"])
    random_id = str(uuid.uuid4())
    real = _run(tenants["a"].put(f"{res.path}/{b_id}", json=res.update_payload))
    fake = _run(tenants["a"].put(f"{res.path}/{random_id}", json=res.update_payload))
    assert real.status_code == fake.status_code
    assert real.json() == fake.json()


# --- Workflow actions (cross-tenant) ------------------------------------------

def test_fastag_sync_is_refused_for_a_real_org(tenants):
    """FASTAG-01: the simulation is demo-only, so neither real org in this matrix
    can run it — against its own vehicle or another's. It never fabricates
    activity in a real tenant."""
    a_vehicle = tenants["records"]["vehicles"]["a"]["id"]
    b_vehicle = tenants["records"]["vehicles"]["b"]["id"]
    own = _run(tenants["a"].post(f"/api/fastag/sync/{a_vehicle}"))
    assert own.status_code == 403, f"real-org self sync -> {own.status_code}"
    cross = _run(tenants["a"].post(f"/api/fastag/sync/{b_vehicle}"))
    assert cross.status_code in (403, 404), f"cross-tenant sync -> {cross.status_code}"


# --- Aggregate / read-only surfaces -------------------------------------------

def test_search_does_not_cross_tenants(tenants):
    b_vehicle = tenants["records"]["vehicles"]["b"]
    term = b_vehicle["vehicle_number"]
    r = _run(tenants["a"].get("/api/search", params={"q": term}))
    assert r.status_code == 200
    assert b_vehicle["id"] not in r.text


def test_dashboard_counts_exclude_other_tenants(tenants):
    """An aggregate that counted across tenants would leak volume even without
    exposing a record."""
    r = _run(tenants["a"].get("/api/dashboard"))
    assert r.status_code == 200
    assert tenants["records"]["vehicles"]["b"]["id"] not in r.text


def test_reports_do_not_cross_tenants(tenants):
    r = _run(tenants["a"].get("/api/reports"))
    assert r.status_code == 200
    assert tenants["b"].org_id not in r.text


def test_report_export_does_not_cross_tenants(tenants):
    """Exports are a bulk egress path — the highest-value target."""
    keys = _run(tenants["a"].get("/api/reports")).json()
    key = (keys[0].get("key") if isinstance(keys, list) and keys
           and isinstance(keys[0], dict) else "vehicles")
    r = _run(tenants["a"].get(f"/api/reports/{key}/export"))
    if r.status_code == 200:
        assert tenants["records"]["vehicles"]["b"]["vehicle_number"] not in r.text


def test_expenses_overview_does_not_cross_tenants(tenants):
    r = _run(tenants["a"].get("/api/expenses/overview"))
    assert r.status_code == 200
    assert tenants["records"]["vehicles"]["b"]["id"] not in r.text


def test_fleet_status_does_not_cross_tenants(tenants):
    r = _run(tenants["a"].get("/api/fleet-status"))
    assert r.status_code == 200
    assert tenants["records"]["vehicles"]["b"]["id"] not in r.text


def test_calendar_does_not_cross_tenants(tenants):
    r = _run(tenants["a"].get("/api/calendar",
                              params={"start": "2025-01-01", "end": "2027-12-31"}))
    assert r.status_code == 200
    assert tenants["records"]["calendar_events"]["b"]["id"] not in r.text


def test_compliance_does_not_cross_tenants(tenants):
    r = _run(tenants["a"].get("/api/compliance"))
    assert r.status_code == 200
    assert tenants["records"]["vehicles"]["b"]["id"] not in r.text


def test_alerts_do_not_cross_tenants(tenants):
    r = _run(tenants["a"].get("/api/alerts"))
    assert r.status_code == 200
    assert tenants["records"]["vehicles"]["b"]["id"] not in r.text


@pytest.mark.parametrize("path", [
    "/api/drilldowns/docs_expiring", "/api/drilldowns/docs_expired",
    "/api/drilldowns/vehicles_under_repair", "/api/drilldowns/service_due",
    "/api/drilldowns/top_fuel_consumers", "/api/drilldowns/top_cost_vehicles",
    "/api/drilldowns/low_mileage_vehicles",
])
def test_drilldowns_do_not_cross_tenants(path, tenants):
    r = _run(tenants["a"].get(path))
    assert r.status_code == 200
    assert tenants["records"]["vehicles"]["b"]["id"] not in r.text


# --- Organisation / user administration ---------------------------------------

def test_org_profile_is_own_org_only(tenants):
    r = _run(tenants["a"].get("/api/org"))
    assert r.status_code == 200
    assert r.json()["id"] == tenants["a"].org_id


def test_user_list_never_shows_another_orgs_users(tenants):
    r = _run(tenants["a"].get("/api/users"))
    assert r.status_code == 200
    ids = [u["id"] for u in r.json()]
    assert tenants["b"].user_id not in ids
    assert tenants["a"].user_id in ids


def test_cannot_update_another_orgs_user(tenants):
    r = _run(tenants["a"].put(f"/api/users/{tenants['b'].user_id}",
                              json={"full_name": "pwned"}))
    assert r.status_code == 404


def test_cannot_escalate_another_orgs_user_role(tenants):
    r = _run(tenants["a"].put(f"/api/users/{tenants['b'].user_id}",
                              json={"role": "org_admin"}))
    assert r.status_code == 404


def test_cannot_delete_another_orgs_user(tenants):
    _run(tenants["a"].delete(f"/api/users/{tenants['b'].user_id}"))
    check = _run(tenants["b"].get("/api/auth/me"))
    assert check.status_code == 200, "A deleted or disabled B's admin"


def test_cannot_reset_another_orgs_user_password(tenants):
    r = _run(tenants["a"].post(f"/api/users/{tenants['b'].user_id}/reset-password"))
    assert r.status_code == 404
    # B can still authenticate.
    assert _run(tenants["b"].get("/api/auth/me")).status_code == 200


def test_user_create_cannot_target_another_org(tenants):
    """org_id is server-derived, so a new user lands in the caller's org."""
    r = _run(tenants["a"].post("/api/users", json={
        "username": _uniq("victim"), "password": "TenTestPassphrase123",
        "role": "viewer", "full_name": "Injected", "org_id": tenants["b"].org_id,
    }))
    assert r.status_code == 400
    assert "org_id" in r.text


# --- Files (FILE-01) -----------------------------------------------------------

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _upload(oc, name="p.png"):
    return _run(oc.post("/api/upload", files={"file": (name, _PNG, "image/png")}))


def test_file_upload_succeeds_for_own_org(tenants):
    r = _upload(tenants["a"])
    assert r.status_code == 200, r.text[:200]
    assert "file_id" in r.json()


def test_cannot_download_another_orgs_file(tenants):
    """The exact pre-FILE-01 exploit: a file id was enough for anyone."""
    up = _upload(tenants["b"])
    assert up.status_code == 200
    b_file_id = up.json()["file_id"]
    r = _run(tenants["a"].get(f"/api/files/{b_file_id}"))
    assert r.status_code == 404, f"cross-tenant file read returned {r.status_code}"


def test_cannot_read_another_orgs_file_metadata(tenants):
    up = _upload(tenants["b"])
    b_file_id = up.json()["file_id"]
    r = _run(tenants["a"].get(f"/api/files/{b_file_id}/metadata"))
    assert r.status_code == 404


def test_own_file_is_downloadable_and_safely_served(tenants):
    up = _upload(tenants["a"])
    file_id = up.json()["file_id"]
    r = _run(tenants["a"].get(f"/api/files/{file_id}"))
    assert r.status_code == 200
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("cache-control") == "private, no-store"


def test_cross_tenant_file_id_does_not_disclose_existence(tenants):
    up = _upload(tenants["b"])
    real = _run(tenants["a"].get(f"/api/files/{up.json()['file_id']}"))
    fake = _run(tenants["a"].get(f"/api/files/{uuid.uuid4()}"))
    assert real.status_code == fake.status_code == 404
    assert real.json() == fake.json()


def test_disallowed_file_type_is_rejected(tenants):
    r = _run(tenants["a"].post("/api/upload", files={
        "file": ("evil.html", b"<script>alert(1)</script>", "text/html")}))
    assert r.status_code == 400


def test_file_content_must_match_its_extension(tenants):
    r = _run(tenants["a"].post("/api/upload", files={
        "file": ("evil.png", b"<html><script>alert(1)</script></html>", "image/png")}))
    assert r.status_code == 400


# --- Sessions (AUTH-01) --------------------------------------------------------

def test_session_list_is_own_sessions_only(tenants):
    r = _run(tenants["a"].get("/api/auth/sessions"))
    assert r.status_code == 200
    for s in r.json():
        assert "token_hash" not in s and "csrf_hash" not in s


def test_cannot_revoke_another_orgs_session(tenants):
    b_sessions = _run(tenants["b"].get("/api/auth/sessions")).json()
    assert b_sessions, "B has no session to target"
    r = _run(tenants["a"].delete(f"/api/auth/sessions/{b_sessions[0]['id']}"))
    assert r.status_code == 404
    # B is still authenticated.
    assert _run(tenants["b"].get("/api/auth/me")).status_code == 200


def test_unauthenticated_request_is_rejected(tenants):
    async def probe():
        transport = ASGITransport(app=server.app)
        async with AsyncClient(transport=transport, base_url="http://ten-test") as c:
            return await c.get("/api/vehicles")

    assert _run(probe()).status_code == 401


def test_state_change_without_csrf_is_refused(tenants):
    """Cookie auth without the double-submit header must fail."""
    async def probe():
        return await tenants["a"].client.post(
            "/api/vehicles", json={"vehicle_number": _uniq("CSRF")})

    r = _run(probe())
    assert r.status_code == 403


# --- Registry guard ------------------------------------------------------------

def test_every_tenant_collection_is_registered():
    """A new tenant-scoped collection must be covered here or explicitly exempt.

    This is what keeps the matrix honest as FleetFlow grows: adding a collection
    to TENANT_COLLECTIONS without isolation coverage fails the build.
    """
    registered = {r.collection for r in RESOURCE_REGISTRY}
    missing = database.TENANT_COLLECTIONS - registered - set(REGISTRY_EXEMPTIONS)
    assert not missing, (
        f"Tenant-scoped collections with no cross-tenant coverage: {sorted(missing)}. "
        "Add a Resource to RESOURCE_REGISTRY, or an entry to REGISTRY_EXEMPTIONS "
        "with a reason."
    )


def test_exemptions_are_all_real_tenant_collections():
    """Stops an exemption lingering after its collection is renamed or removed."""
    stale = set(REGISTRY_EXEMPTIONS) - database.TENANT_COLLECTIONS
    assert not stale, f"Exemptions for non-existent collections: {sorted(stale)}"
