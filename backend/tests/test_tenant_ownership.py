"""
TEN-01 — Tenant ownership and mass-assignment protection.

These tests pin the two properties TEN-01 exists to guarantee:

1. Organisation ownership is derived from the authenticated session and can
   never be supplied, overridden or transferred through a request body.
2. Server-owned fields (audit, security, isolation markers, workflow, derived
   values) are rejected rather than silently dropped on generic endpoints.

The suite is deliberately layered. The policy and database-layer tests run
in-process against fakes so they are fast, deterministic and require no live
database. That matters here: the pre-TEN-01 bug was a *silent* one (a
``setdefault`` and a denylist with an omission), so the tests assert on the
mechanism, not merely on an HTTP status.
"""
import asyncio

import pytest
from fastapi import HTTPException

from tenant_policy import (
    PROTECTED_FIELDS,
    TENANT_OWNERSHIP_FIELDS,
    TenantViolation,
    ownership_fields_in_update,
    protected_fields_in,
    reject_protected_fields,
)


def _run(coro):
    """Drive a coroutine without pytest-asyncio (project convention)."""
    return asyncio.run(coro)


# --- Policy: which fields are protected ---------------------------------------

@pytest.mark.parametrize("field", sorted(TENANT_OWNERSHIP_FIELDS))
def test_ownership_fields_are_protected(field):
    assert field in PROTECTED_FIELDS


@pytest.mark.parametrize("field", [
    # Audit provenance
    "created_at", "created_by", "updated_at", "updated_by",
    "deleted_at", "deleted_by", "archived_at", "archived_by",
    # Security posture / escalation vectors
    "role", "roles", "permissions",
    "is_admin", "is_super_admin", "is_platform_admin",
    "password_hash", "must_change_password",
    # Isolation markers
    "is_demo", "is_test_data",
    # Branch scope (reserved ahead of branch scoping)
    "branch_id",
    # Identity
    "id", "_id",
    # Workflow / approval / payment
    "approval_status", "approved_by", "approved_at",
    "payment_status", "paid_by", "paid_at",
    # Optimistic locking
    "_version",
])
def test_field_is_protected(field):
    assert field in PROTECTED_FIELDS


@pytest.mark.parametrize("field", [
    # Ordinary, legitimately client-writable fields must NOT be blocked.
    "vehicle_number", "make", "model", "notes", "amount", "cost", "date",
    "odometer", "driver_id", "vehicle_id", "full_name", "is_active", "name",
    # `status` stays editable on generic endpoints: several modules use it as a
    # plain field. Locking it down belongs to WF-01, with transition endpoints.
    "status",
])
def test_ordinary_field_is_not_protected(field):
    assert field not in PROTECTED_FIELDS


def test_protected_fields_in_reports_all_matches_sorted():
    found = protected_fields_in({"org_id": "x", "role": "admin", "notes": "ok"})
    assert found == ["org_id", "role"]


def test_allow_exempts_a_field():
    assert protected_fields_in({"role": "admin"}, allow={"role"}) == []


def test_non_dict_payload_is_ignored():
    assert protected_fields_in(None) == []
    assert protected_fields_in(["org_id"]) == []


# --- Policy: rejection behaviour ----------------------------------------------

def test_reject_raises_400_naming_the_field():
    with pytest.raises(HTTPException) as e:
        reject_protected_fields({"org_id": "victim-org", "notes": "hi"})
    assert e.value.status_code == 400
    assert "org_id" in e.value.detail


def test_rejection_message_never_echoes_the_submitted_value():
    """An error must not reflect attacker-supplied content back to the client."""
    with pytest.raises(HTTPException) as e:
        reject_protected_fields({"org_id": "s3cret-victim-org-id"})
    assert "s3cret-victim-org-id" not in e.value.detail


def test_clean_payload_passes_through_unchanged():
    payload = {"vehicle_number": "KA01AB1234", "notes": "fine"}
    assert reject_protected_fields(payload) == payload


def test_reject_does_not_mutate_the_payload():
    """Rejection must not silently strip: the caller sees the body as sent."""
    payload = {"notes": "fine"}
    reject_protected_fields(payload)
    assert payload == {"notes": "fine"}


# --- Policy: update-document inspection ---------------------------------------

@pytest.mark.parametrize("update", [
    {"$set": {"org_id": "other"}},
    {"$setOnInsert": {"org_id": "other"}},
    {"$unset": {"org_id": ""}},
    {"$rename": {"org_id": "x"}},
    {"$set": {"org_id.nested": "other"}},          # dotted path, matched at root
    {"org_id": "other"},                            # replacement document
    {"$set": {"notes": "ok"}, "$inc": {"org_id": 1}},
])
def test_ownership_writes_are_detected(update):
    assert "org_id" in ownership_fields_in_update(update)


@pytest.mark.parametrize("update", [
    {"$set": {"notes": "ok"}},
    {"$inc": {"cost": 5}},
    {"$set": {"status": "closed", "vehicle_id": "v1"}},
    {},
])
def test_clean_updates_are_allowed(update):
    assert ownership_fields_in_update(update) == []


def test_non_dict_update_is_ignored():
    assert ownership_fields_in_update(None) == []


# --- Database layer: forced ownership on insert --------------------------------

class _FakeMotorCollection:
    """Records what would reach Mongo, so tests assert on the actual write."""

    def __init__(self):
        self.inserted = []
        self.updates = []

    async def insert_one(self, doc, **k):
        self.inserted.append(doc)
        return doc

    async def insert_many(self, docs, **k):
        self.inserted.extend(docs)
        return docs

    async def update_one(self, flt, update, **k):
        self.updates.append((flt, update))
        return update

    async def update_many(self, flt, update, **k):
        self.updates.append((flt, update))
        return update


@pytest.fixture
def tenant_ctx():
    """Bind a tenant collection to org "org-a" and restore context afterwards."""
    import database

    fake = _FakeMotorCollection()
    coll = database.TenantCollection(fake, "vehicles")
    token = database.current_org_id.set("org-a")
    yield coll, fake
    database.current_org_id.reset(token)


def test_insert_stamps_org_id_from_session(tenant_ctx):
    coll, fake = tenant_ctx
    _run(coll.insert_one({"id": "v1", "vehicle_number": "KA01"}))
    assert fake.inserted[0]["org_id"] == "org-a"


def test_insert_with_matching_org_id_is_allowed(tenant_ctx):
    coll, fake = tenant_ctx
    _run(coll.insert_one({"id": "v1", "org_id": "org-a"}))
    assert fake.inserted[0]["org_id"] == "org-a"


def test_insert_rejects_a_foreign_org_id(tenant_ctx):
    """The regression that motivated TEN-01.

    The old code was ``doc.setdefault("org_id", org)``, so a client-supplied
    org_id won and the record was filed under another organisation.
    """
    coll, fake = tenant_ctx
    with pytest.raises(TenantViolation):
        _run(coll.insert_one({"id": "v1", "org_id": "org-b"}))
    assert fake.inserted == []


def test_insert_many_forces_ownership_on_every_document(tenant_ctx):
    coll, fake = tenant_ctx
    _run(coll.insert_many([{"id": "v1"}, {"id": "v2"}]))
    assert [d["org_id"] for d in fake.inserted] == ["org-a", "org-a"]


def test_insert_many_rejects_a_foreign_org_id_in_any_document(tenant_ctx):
    coll, fake = tenant_ctx
    with pytest.raises(TenantViolation):
        _run(coll.insert_many([{"id": "v1"}, {"id": "v2", "org_id": "org-b"}]))
    assert fake.inserted == []


# --- Database layer: no ownership transfer on update ---------------------------

def test_update_cannot_transfer_a_record_to_another_org(tenant_ctx):
    """Scoping the filter is not enough — the update document must be guarded.

    ``_scope`` restricts which documents match, but ``$set: {org_id: ...}`` would
    still move a matched record out of the tenant.
    """
    coll, fake = tenant_ctx
    with pytest.raises(TenantViolation):
        _run(coll.update_one({"id": "v1"}, {"$set": {"org_id": "org-b"}}))
    assert fake.updates == []


def test_update_many_cannot_transfer_records(tenant_ctx):
    coll, fake = tenant_ctx
    with pytest.raises(TenantViolation):
        _run(coll.update_many({}, {"$set": {"org_id": "org-b"}}))
    assert fake.updates == []


def test_update_rejects_ownership_change_even_to_the_same_org(tenant_ctx):
    """Ownership is server-derived; there is no legitimate reason to write it."""
    coll, fake = tenant_ctx
    with pytest.raises(TenantViolation):
        _run(coll.update_one({"id": "v1"}, {"$set": {"org_id": "org-a"}}))
    assert fake.updates == []


def test_ordinary_update_still_works_and_is_org_scoped(tenant_ctx):
    coll, fake = tenant_ctx
    _run(coll.update_one({"id": "v1"}, {"$set": {"notes": "ok"}}))
    flt, update = fake.updates[0]
    assert flt == {"id": "v1", "org_id": "org-a"}      # filter scoped to tenant
    assert update == {"$set": {"notes": "ok"}}          # update untouched


def test_reads_are_scoped_to_the_session_org(tenant_ctx):
    coll, _ = tenant_ctx
    assert coll._scope({"id": "v1"}) == {"id": "v1", "org_id": "org-a"}


# --- Non-tenant collections are unaffected -------------------------------------

def test_non_tenant_collection_is_not_stamped():
    """user_sessions is global; stamping it with org_id would corrupt lookups."""
    import database

    fake = _FakeMotorCollection()
    coll = database.TenantCollection(fake, "user_sessions")
    token = database.current_org_id.set("org-a")
    try:
        _run(coll.insert_one({"id": "s1", "token": "t"}))
        assert "org_id" not in fake.inserted[0]
    finally:
        database.current_org_id.reset(token)


def test_no_org_context_means_no_stamping():
    """Management commands and startup migrations run without a session."""
    import database

    fake = _FakeMotorCollection()
    coll = database.TenantCollection(fake, "vehicles")
    token = database.current_org_id.set(None)
    try:
        _run(coll.insert_one({"id": "v1"}))
        assert "org_id" not in fake.inserted[0]
    finally:
        database.current_org_id.reset(token)


# --- Request models -----------------------------------------------------------

def test_create_model_rejects_injected_org_id():
    from models import VehicleCreate

    with pytest.raises(HTTPException) as e:
        VehicleCreate(vehicle_number="KA01AB1234", org_id="org-b")
    assert e.value.status_code == 400
    assert "org_id" in e.value.detail


@pytest.mark.parametrize("field,value", [
    ("org_id", "org-b"),
    ("created_by", "someone-else"),
    ("created_at", "1999-01-01T00:00:00Z"),
    ("is_demo", True),
    ("is_test_data", True),
    ("is_admin", True),
    ("is_platform_admin", True),
    ("permissions", ["*"]),
    ("branch_id", "branch-b"),
    ("approval_status", "approved"),
    ("payment_status", "paid"),
    ("_version", 99),
])
def test_create_model_rejects_each_protected_field(field, value):
    from models import VehicleCreate

    with pytest.raises(HTTPException) as e:
        VehicleCreate(**{"vehicle_number": "KA01AB1234", field: value})
    assert e.value.status_code == 400
    assert field in e.value.detail


def test_create_model_rejects_role_escalation():
    from models import ExpenseCreate

    with pytest.raises(HTTPException) as e:
        ExpenseCreate(vehicle_id="v1", category="Fuel", date="2026-01-01",
                      amount=100, role="admin")
    assert e.value.status_code == 400


def test_valid_create_still_works():
    from models import VehicleCreate

    v = VehicleCreate(vehicle_number="KA01AB1234", make="Tata")
    assert v.vehicle_number == "KA01AB1234"
    assert not hasattr(v, "org_id")


def test_unknown_non_protected_field_is_ignored_not_rejected():
    """Deliberate: only protected fields are rejected, so harmless frontend/model
    drift does not become a 422. See TenantSafeModel."""
    from models import VehicleCreate

    v = VehicleCreate(vehicle_number="KA01AB1234", some_future_field="x")
    assert v.vehicle_number == "KA01AB1234"


def test_allow_protected_is_not_a_request_field():
    """It is policy metadata (ClassVar); if it leaked into the schema a client
    could send it and widen its own exemptions."""
    from models import UserCreate, VehicleCreate

    assert "allow_protected" not in VehicleCreate.model_fields
    assert "allow_protected" not in UserCreate.model_fields


# --- Legitimate exceptions keep working ----------------------------------------

def test_user_admin_may_set_role_and_password():
    from models import UserCreate

    u = UserCreate(username="jo", password="secret123", role="data_entry",
                   full_name="Jo")
    assert u.role == "data_entry"


def test_user_admin_may_change_role():
    from models import UserUpdate

    assert UserUpdate(role="management").role == "management"


def test_user_admin_still_cannot_move_a_user_between_orgs():
    from models import UserUpdate

    with pytest.raises(HTTPException) as e:
        UserUpdate(role="management", org_id="org-b")
    assert "org_id" in e.value.detail


def test_login_may_send_a_password():
    from models import LoginRequest

    assert LoginRequest(username="jo", password="pw").password == "pw"


def test_login_cannot_inject_ownership():
    from models import LoginRequest

    with pytest.raises(HTTPException):
        LoginRequest(username="jo", password="pw", org_id="org-b")


# --- Policy is actually wired into the routes ----------------------------------

def test_generic_crud_update_enforces_the_policy():
    """helpers.make_crud serves 12 collections; it is the largest single
    mass-assignment surface and previously carried a denylist without org_id."""
    import inspect
    import helpers

    src = inspect.getsource(helpers.make_crud)
    assert "reject_protected_fields(payload)" in src


@pytest.mark.parametrize("module_name", [
    "helpers", "routes_core", "routes_calendar", "routes_compliance",
    "routes_vendors", "routes_expenses", "routes_orgs",
])
def test_no_module_still_uses_the_old_incomplete_denylist(module_name):
    """The old pattern omitted org_id. If it reappears anywhere, fail loudly."""
    import importlib
    import inspect

    src = inspect.getsource(importlib.import_module(module_name))
    assert 'k not in ("id", "_id", "created_at", "created_by", "is_test_data")' not in src
