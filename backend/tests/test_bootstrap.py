"""
Focused unit tests for the SEC-001 secure first-installation bootstrap and the
last-active-org_admin deletion guard.

These tests never connect to or drop the real application database. They use
small in-memory fake async collections. They also do not require pytest-asyncio:
each async call is driven with asyncio.run().
"""
import os
import sys
import asyncio

import pytest
from passlib.hash import bcrypt

# Make the backend package importable regardless of pytest's import mode.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bootstrap import create_first_admin, BootstrapError  # noqa: E402
from auth import is_last_active_org_admin  # noqa: E402


# --------------------------- in-memory fakes ---------------------------------

def _match(doc, flt):
    for key, cond in flt.items():
        val = doc.get(key)
        if isinstance(cond, dict) and "$ne" in cond:
            if val == cond["$ne"]:
                return False
        elif val != cond:
            return False
    return True


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    async def count_documents(self, flt):
        return sum(1 for d in self.docs if _match(d, flt))

    async def find_one(self, flt, *a, **k):
        for d in self.docs:
            if _match(d, flt):
                return dict(d)
        return None

    async def insert_one(self, doc, **k):
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": doc.get("id")})()

    async def delete_one(self, flt, **k):
        for i, d in enumerate(self.docs):
            if _match(d, flt):
                del self.docs[i]
                break
        return type("R", (), {"deleted_count": 1})()


class FailingUsers(FakeCollection):
    """Users collection whose insert always fails (to test org rollback)."""
    async def insert_one(self, doc, **k):
        raise RuntimeError("simulated user insert failure")


class FakeDB:
    def __init__(self, users=None, organizations=None):
        self.users = users if users is not None else FakeCollection()
        self.organizations = organizations if organizations is not None else FakeCollection()


VALID = dict(
    org_name="Acme Transport",
    username="firstadmin",
    email="admin@acme.example",
    full_name="First Admin",
    password="Sup3r-Secret-Pw",
)


def _run(coro):
    return asyncio.run(coro)


# ------------------------------- tests ---------------------------------------

def test_empty_db_creates_one_org_and_one_admin():
    db = FakeDB()
    result = _run(create_first_admin(db, **VALID))
    assert len(db.organizations.docs) == 1
    assert len(db.users.docs) == 1
    user = db.users.docs[0]
    assert user["role"] == "org_admin"
    assert user["is_active"] is True
    assert user["is_demo"] is False
    org = db.organizations.docs[0]
    assert org["is_demo"] is False
    # user is linked to the created organisation
    assert user["org_id"] == org["id"] == result["org_id"]


def test_existing_user_causes_refusal():
    db = FakeDB(users=FakeCollection([{"id": "u1", "username": "someone", "role": "owner"}]))
    with pytest.raises(BootstrapError):
        _run(create_first_admin(db, **VALID))
    # nothing created
    assert len(db.users.docs) == 1
    assert len(db.organizations.docs) == 0


def test_existing_user_and_hash_unchanged_after_refusal():
    existing_hash = bcrypt.hash("do-not-touch-me")
    existing = {"id": "u1", "username": "keep", "role": "owner",
                "password_hash": existing_hash, "is_active": True}
    db = FakeDB(users=FakeCollection([existing]))
    with pytest.raises(BootstrapError):
        _run(create_first_admin(db, **VALID))
    assert db.users.docs[0]["password_hash"] == existing_hash
    assert db.users.docs[0] == existing


def test_existing_admin_unchanged():
    admin = {"id": "a1", "username": "boss", "role": "org_admin",
             "password_hash": bcrypt.hash("boss-pw"), "is_active": True}
    db = FakeDB(users=FakeCollection([admin]))
    with pytest.raises(BootstrapError):
        _run(create_first_admin(db, **VALID))
    assert db.users.docs == [admin]


def test_second_bootstrap_is_non_destructive():
    db = FakeDB()
    first = _run(create_first_admin(db, **VALID))
    snapshot_users = [dict(d) for d in db.users.docs]
    snapshot_orgs = [dict(d) for d in db.organizations.docs]
    with pytest.raises(BootstrapError):
        _run(create_first_admin(db, org_name="Second Co", username="second",
                                email="second@x.example", full_name="Second",
                                password="Another-Pw-123"))
    assert db.users.docs == snapshot_users
    assert db.organizations.docs == snapshot_orgs
    # still exactly the first admin
    assert db.users.docs[0]["id"] == first["user_id"]


def test_empty_password_rejected():
    db = FakeDB()
    with pytest.raises(BootstrapError):
        _run(create_first_admin(db, **{**VALID, "password": ""}))
    assert db.users.docs == [] and db.organizations.docs == []


def test_weak_password_rejected():
    db = FakeDB()
    with pytest.raises(BootstrapError):
        _run(create_first_admin(db, **{**VALID, "password": "short7"}))  # 6 chars
    assert db.users.docs == []


def test_invalid_email_rejected():
    db = FakeDB()
    with pytest.raises(BootstrapError):
        _run(create_first_admin(db, **{**VALID, "email": "not-an-email"}))
    assert db.users.docs == []


@pytest.mark.parametrize("field", ["org_name", "username", "full_name"])
def test_required_identity_fields_enforced(field):
    db = FakeDB()
    with pytest.raises(BootstrapError):
        _run(create_first_admin(db, **{**VALID, field: "   "}))
    assert db.users.docs == []


def test_stored_password_is_hashed_and_differs_from_input():
    db = FakeDB()
    _run(create_first_admin(db, **VALID))
    stored = db.users.docs[0]["password_hash"]
    assert stored != VALID["password"]
    assert bcrypt.verify(VALID["password"], stored)


def test_no_plaintext_password_field_is_stored():
    db = FakeDB()
    _run(create_first_admin(db, **VALID))
    user = db.users.docs[0]
    assert "password" not in user
    assert VALID["password"] not in " ".join(str(v) for v in user.values())


def test_password_absent_from_success_output_error_and_logs(caplog):
    db = FakeDB()
    with caplog.at_level("DEBUG"):
        result = _run(create_first_admin(db, **VALID))
    # success summary
    assert VALID["password"] not in " ".join(str(v) for v in result.values())
    # logs
    assert VALID["password"] not in caplog.text
    # error output on refusal
    with pytest.raises(BootstrapError) as ei:
        _run(create_first_admin(db, **VALID))
    assert VALID["password"] not in str(ei.value)


def test_production_bootstrap_creates_no_demo_user():
    db = FakeDB()
    _run(create_first_admin(db, **VALID))
    assert all(u.get("is_demo") is False for u in db.users.docs)
    assert not any(u["username"].startswith("demo_") for u in db.users.docs)
    assert db.users.docs[0]["created_by"] == "bootstrap"


def test_only_demo_user_still_causes_refusal():
    demo = {"id": "d1", "username": "demo_owner", "role": "owner", "is_demo": True,
            "password_hash": bcrypt.hash("random"), "is_active": True}
    db = FakeDB(users=FakeCollection([demo]))
    with pytest.raises(BootstrapError):
        _run(create_first_admin(db, **VALID))
    assert db.users.docs == [demo]
    assert db.organizations.docs == []


def test_org_rollback_when_user_insert_fails():
    db = FakeDB(users=FailingUsers())
    with pytest.raises(RuntimeError):
        _run(create_first_admin(db, **VALID))
    # the organisation created just before the failed user insert is rolled back
    assert db.organizations.docs == []


# ---------------- last active org_admin deletion guard -----------------------

def test_last_active_org_admin_cannot_be_deleted():
    users = FakeCollection([
        {"id": "a1", "role": "org_admin", "is_active": True},
        {"id": "o1", "role": "owner", "is_active": True},
    ])
    target = {"id": "a1", "role": "org_admin", "is_active": True}
    assert _run(is_last_active_org_admin(users, "a1", target)) is True


def test_org_with_another_active_admin_allows_deletion():
    users = FakeCollection([
        {"id": "a1", "role": "org_admin", "is_active": True},
        {"id": "a2", "role": "org_admin", "is_active": True},
    ])
    target = {"id": "a1", "role": "org_admin", "is_active": True}
    assert _run(is_last_active_org_admin(users, "a1", target)) is False


def test_inactive_second_admin_does_not_count():
    users = FakeCollection([
        {"id": "a1", "role": "org_admin", "is_active": True},
        {"id": "a2", "role": "org_admin", "is_active": False},
    ])
    target = {"id": "a1", "role": "org_admin", "is_active": True}
    assert _run(is_last_active_org_admin(users, "a1", target)) is True


def test_non_admin_deletion_never_blocked():
    users = FakeCollection([{"id": "a1", "role": "org_admin", "is_active": True}])
    target = {"id": "x1", "role": "owner", "is_active": True}
    assert _run(is_last_active_org_admin(users, "x1", target)) is False
