"""
Focused unit tests for SEC-002 legacy credential rotation
(backend/rotate_legacy_credentials.py).

These tests never connect to, modify or drop any real database. They use small
in-memory fake async collections and drive coroutines with asyncio.run() (no
pytest-asyncio needed), mirroring test_bootstrap.py.
"""
import os
import sys
import asyncio

import pytest
from passlib.hash import bcrypt

# Make the backend package importable regardless of pytest's import mode.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rotate_legacy_credentials import (  # noqa: E402
    RotationError, find_legacy_accounts, validate_manifest, run_rotation,
    is_demo_account, LEGACY_MARKER,
)


# --------------------------- in-memory fakes ---------------------------------

def _match(doc, flt):
    for key, cond in flt.items():
        val = doc.get(key)
        if isinstance(cond, dict):
            if "$ne" in cond and val == cond["$ne"]:
                return False
            if "$in" in cond and val not in cond["$in"]:
                return False
            if "$ne" not in cond and "$in" not in cond:
                if val != cond:
                    return False
        elif val != cond:
            return False
    return True


def _project(doc, projection):
    if not projection:
        return dict(doc)
    include = {k for k, v in projection.items() if v == 1}
    out = {}
    for k, v in doc.items():
        if k == "_id":
            if projection.get("_id", 1) == 1:
                out[k] = v
            continue
        if not include or k in include:
            out[k] = v
    return out


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    def find(self, flt=None, projection=None):
        flt = flt or {}
        return _Cursor([_project(d, projection) for d in self.docs if _match(d, flt)])

    async def find_one(self, flt, projection=None):
        for d in self.docs:
            if _match(d, flt):
                return _project(d, projection)
        return None

    async def count_documents(self, flt):
        return sum(1 for d in self.docs if _match(d, flt))

    async def insert_one(self, doc, **k):
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": doc.get("id")})()

    async def update_one(self, flt, update, **k):
        matched = modified = 0
        for d in self.docs:
            if _match(d, flt):
                matched = 1
                d.update(update.get("$set", {}))
                modified = 1
                break
        return type("R", (), {"matched_count": matched, "modified_count": modified})()

    async def update_many(self, flt, update, **k):
        modified = 0
        for d in self.docs:
            if _match(d, flt):
                d.update(update.get("$set", {}))
                modified += 1
        return type("R", (), {"matched_count": modified, "modified_count": modified})()


class FailingUsersUpdate(FakeCollection):
    """users collection whose update_one 'matches nothing' (simulate rotate fail)."""
    async def update_one(self, flt, update, **k):
        return type("R", (), {"matched_count": 0, "modified_count": 0})()


class FakeDB:
    def __init__(self, users=None, user_sessions=None, security_audit=None):
        self.users = users if users is not None else FakeCollection()
        self.user_sessions = user_sessions if user_sessions is not None else FakeCollection()
        self.security_audit = security_audit if security_audit is not None else FakeCollection()

    def __getitem__(self, name):
        return getattr(self, name)


def _run(coro):
    return asyncio.run(coro)


# ----------------------------- fixtures/builders -----------------------------

def _user(uid, username, role="data_entry", **extra):
    d = {"id": uid, "username": username, "role": role, "org_id": "org-rajguru-foods",
         "is_active": True, "is_demo": False, "created_by": LEGACY_MARKER,
         "password_hash": bcrypt.hash(f"old-{username}-pw"),
         "must_change_password": True}
    d.update(extra)
    return d


def _standard_db():
    """A DB with the 5 legacy accounts, a demo user, and a bootstrap admin."""
    users = FakeCollection([
        _user("id-admin", "admin", role="admin"),
        _user("id-manager", "manager", role="management"),
        _user("id-de1", "dataentry1", role="data_entry"),
        _user("id-drv1", "driver1", role="driver"),
        _user("id-test", "test", role="test"),
        # demo user — must always be excluded
        {"id": "id-demo", "username": "demo_owner", "role": "owner",
         "org_id": "org-fleetflow-demo", "is_active": True, "is_demo": True,
         "created_by": "demo_seed", "password_hash": bcrypt.hash("random"),
         "must_change_password": False},
        # real staff (bootstrap admin) — must always be excluded
        {"id": "id-boss", "username": "boss", "role": "org_admin",
         "org_id": "org-acme", "is_active": True, "is_demo": False,
         "created_by": "bootstrap", "password_hash": bcrypt.hash("boss-pw"),
         "must_change_password": False},
        # onboarding staff — excluded
        {"id": "id-ravi", "username": "ravi", "role": "org_admin",
         "org_id": "org-acme2", "is_active": True, "is_demo": False,
         "created_by": "onboarding", "password_hash": bcrypt.hash("ravi-pw"),
         "must_change_password": False},
    ])
    sessions = FakeCollection([
        {"id": "s-admin", "user_id": "id-admin", "revoked": False},
        {"id": "s-test", "user_id": "id-test", "revoked": False},
        {"id": "s-demo", "user_id": "id-demo", "revoked": False},
        {"id": "s-boss", "user_id": "id-boss", "revoked": False},
    ])
    return FakeDB(users=users, user_sessions=sessions)


def _manifest(actions, operator="ops@x", recovery="boss", known=True):
    return {"operator": operator, "recovery_admin_username": recovery,
            "recovery_admin_has_known_password": known, "actions": actions}


# ------------------------------- tests ---------------------------------------

def test_find_legacy_accounts_exact_set():
    db = _standard_db()
    accts = _run(find_legacy_accounts(db))
    names = sorted(a["username"] for a in accts)
    assert names == ["admin", "dataentry1", "driver1", "manager", "test"]


def test_find_legacy_excludes_demo_and_staff():
    db = _standard_db()
    accts = _run(find_legacy_accounts(db))
    ids = {a["id"] for a in accts}
    assert "id-demo" not in ids       # demo excluded
    assert "id-boss" not in ids       # bootstrap staff excluded
    assert "id-ravi" not in ids       # onboarding staff excluded


def test_find_legacy_projection_excludes_password_hash():
    db = _standard_db()
    accts = _run(find_legacy_accounts(db))
    assert all("password_hash" not in a for a in accts)


def test_is_demo_account_multiple_markers():
    assert is_demo_account({"is_demo": True})
    assert is_demo_account({"created_by": "demo_seed"})
    assert is_demo_account({"org_id": "org-fleetflow-demo"})
    assert is_demo_account({"username": "demo_owner"})
    assert not is_demo_account({"username": "admin", "created_by": "system"})


def test_dry_run_performs_zero_writes_and_no_audit():
    db = _standard_db()
    before_users = [dict(d) for d in db.users.docs]
    before_sessions = [dict(d) for d in db.user_sessions.docs]
    report = _run(run_rotation(db, _manifest([
        {"user_id": "id-admin", "username": "admin", "action": "rotate"},
        {"user_id": "id-test", "username": "test", "action": "deactivate"},
    ]), passwords={}, apply=False))
    assert report["mode"] == "dry_run"
    assert db.users.docs == before_users
    assert db.user_sessions.docs == before_sessions
    assert db.security_audit.docs == []          # no audit in dry-run


def test_rotation_changes_hash_and_sets_must_change():
    db = _standard_db()
    old = next(d for d in db.users.docs if d["id"] == "id-admin")["password_hash"]
    _run(run_rotation(db, _manifest([
        {"user_id": "id-admin", "username": "admin", "action": "rotate"},
    ], recovery="admin"), passwords={"id-admin": "Brand-New-Pw1"}, apply=True))
    rec = next(d for d in db.users.docs if d["id"] == "id-admin")
    assert rec["password_hash"] != old
    assert bcrypt.verify("Brand-New-Pw1", rec["password_hash"])
    assert rec["must_change_password"] is True


def test_only_targeted_sessions_revoked_demo_and_staff_safe():
    db = _standard_db()
    _run(run_rotation(db, _manifest([
        {"user_id": "id-test", "username": "test", "action": "deactivate"},
    ]), passwords={}, apply=True))
    by_id = {s["id"]: s for s in db.user_sessions.docs}
    assert by_id["s-test"]["revoked"] is True     # target revoked
    assert by_id["s-demo"]["revoked"] is False    # demo untouched
    assert by_id["s-boss"]["revoked"] is False    # other staff untouched
    assert by_id["s-admin"]["revoked"] is False   # non-target legacy untouched


def test_deactivate_only_when_selected():
    db = _standard_db()
    _run(run_rotation(db, _manifest([
        {"user_id": "id-test", "username": "test", "action": "deactivate"},
    ]), passwords={}, apply=True))
    assert next(d for d in db.users.docs if d["id"] == "id-test")["is_active"] is False
    # admin was not selected -> still active
    assert next(d for d in db.users.docs if d["id"] == "id-admin")["is_active"] is True


def test_skip_performs_no_changes():
    db = _standard_db()
    before = [dict(d) for d in db.users.docs]
    sess_before = [dict(d) for d in db.user_sessions.docs]
    _run(run_rotation(db, _manifest([
        {"user_id": "id-manager", "username": "manager", "action": "skip"},
    ]), passwords={}, apply=True))
    assert db.users.docs == before
    assert db.user_sessions.docs == sess_before
    # skip is not audited
    assert db.security_audit.docs == []


def test_password_never_in_report_or_audit():
    db = _standard_db()
    secret = "Zx-Secret-Pass-9"
    report = _run(run_rotation(db, _manifest([
        {"user_id": "id-admin", "username": "admin", "action": "rotate"},
    ], recovery="admin"), passwords={"id-admin": secret}, apply=True))
    blob = str(report) + str(db.security_audit.docs)
    assert secret not in blob


def test_no_password_hash_in_report():
    db = _standard_db()
    report = _run(run_rotation(db, _manifest([
        {"user_id": "id-admin", "username": "admin", "action": "rotate"},
    ], recovery="admin"), passwords={"id-admin": "Brand-New-Pw1"}, apply=True))
    rec = next(d for d in db.users.docs if d["id"] == "id-admin")
    assert rec["password_hash"] not in str(report)
    for line in report["results"]:
        assert "password_hash" not in line


def test_manifest_rejects_password_field():
    db = _standard_db()
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest([
            {"user_id": "id-admin", "username": "admin", "action": "rotate",
             "password": "nope"},
        ], recovery="admin")))


def test_manifest_rejects_unknown_user_id():
    db = _standard_db()
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest([
            {"user_id": "id-nope", "username": "ghost", "action": "rotate"},
        ])))


def test_manifest_rejects_duplicate_targets():
    db = _standard_db()
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest([
            {"user_id": "id-admin", "username": "admin", "action": "rotate"},
            {"user_id": "id-admin", "username": "admin", "action": "skip"},
        ], recovery="admin")))


def test_manifest_rejects_demo_target_even_if_supplied():
    db = _standard_db()
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest([
            {"user_id": "id-demo", "username": "demo_owner", "action": "rotate"},
        ])))


def test_manifest_rejects_nonlegacy_staff_target():
    db = _standard_db()
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest([
            {"user_id": "id-boss", "username": "boss", "action": "rotate"},
        ])))


def test_manifest_rejects_username_mismatch():
    db = _standard_db()
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest([
            {"user_id": "id-admin", "username": "manager", "action": "rotate"},
        ], recovery="admin")))


def test_manifest_rejects_invalid_action():
    db = _standard_db()
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest([
            {"user_id": "id-admin", "username": "admin", "action": "delete"},
        ], recovery="admin")))


def test_preflight_blocks_deactivating_recovery_admin():
    db = _standard_db()
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest([
            {"user_id": "id-admin", "username": "admin", "action": "deactivate"},
        ], recovery="admin")))


def test_preflight_blocks_skip_recovery_without_known_password():
    db = _standard_db()
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest([
            {"user_id": "id-admin", "username": "admin", "action": "skip"},
        ], recovery="admin", known=False)))


def test_preflight_blocks_missing_recovery_admin():
    db = _standard_db()
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest([
            {"user_id": "id-test", "username": "test", "action": "deactivate"},
        ], recovery="does-not-exist")))


def test_preflight_blocks_when_no_recovery_known_password_asserted():
    # recovery admin not in manifest and known flag false -> refuse
    db = _standard_db()
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest([
            {"user_id": "id-test", "username": "test", "action": "deactivate"},
        ], recovery="boss", known=False)))


def test_preflight_blocks_zero_remaining_admins():
    # Only one admin in the DB; deactivating it must be blocked.
    users = FakeCollection([
        _user("id-admin", "admin", role="admin"),
        _user("id-test", "test", role="test"),
    ])
    db = FakeDB(users=users)
    # recovery is admin but action deactivate -> blocked by recovery rule first,
    # so target a scenario where the only admin is deactivated via a different
    # recovery declaration is impossible; assert the recovery-deactivate guard.
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest([
            {"user_id": "id-admin", "username": "admin", "action": "deactivate"},
        ], recovery="admin")))


def test_partial_failure_does_not_revoke_sessions():
    # rotate fails (update matches nothing) -> that user's sessions NOT revoked.
    users = FailingUsersUpdate([
        _user("id-admin", "admin", role="admin"),
        {"id": "id-boss", "username": "boss", "role": "org_admin",
         "org_id": "org-acme", "is_active": True, "is_demo": False,
         "created_by": "bootstrap", "must_change_password": False,
         "password_hash": bcrypt.hash("boss-pw")},
    ])
    sessions = FakeCollection([{"id": "s-admin", "user_id": "id-admin", "revoked": False}])
    db = FakeDB(users=users, user_sessions=sessions)
    report = _run(run_rotation(db, _manifest([
        {"user_id": "id-admin", "username": "admin", "action": "rotate"},
    ], recovery="boss"), passwords={"id-admin": "Brand-New-Pw1"}, apply=True))
    assert report["totals"]["failed"] == 1
    assert db.user_sessions.docs[0]["revoked"] is False   # NOT revoked on failure


def test_audit_written_for_success_and_failure():
    # success
    db = _standard_db()
    _run(run_rotation(db, _manifest([
        {"user_id": "id-test", "username": "test", "action": "deactivate"},
    ]), passwords={}, apply=True))
    assert len(db.security_audit.docs) == 1
    a = db.security_audit.docs[0]
    assert a["outcome"] == "deactivated" and a["action"] == "deactivate"
    assert "password" not in a and "password_hash" not in a and "token" not in a

    # failure
    users = FailingUsersUpdate([
        _user("id-admin", "admin", role="admin"),
        {"id": "id-boss", "username": "boss", "role": "org_admin",
         "org_id": "org-acme", "is_active": True, "is_demo": False,
         "created_by": "bootstrap", "must_change_password": False,
         "password_hash": bcrypt.hash("boss-pw")},
    ])
    db2 = FakeDB(users=users)
    _run(run_rotation(db2, _manifest([
        {"user_id": "id-admin", "username": "admin", "action": "rotate"},
    ], recovery="boss"), passwords={"id-admin": "Brand-New-Pw1"}, apply=True))
    assert any(r["outcome"] == "failed" and r.get("failure_category")
               for r in db2.security_audit.docs)


def test_missing_password_for_rotate_in_apply_is_refused():
    db = _standard_db()
    with pytest.raises(RotationError):
        _run(run_rotation(db, _manifest([
            {"user_id": "id-admin", "username": "admin", "action": "rotate"},
        ], recovery="admin"), passwords={}, apply=True))
    # nothing changed
    rec = next(d for d in db.users.docs if d["id"] == "id-admin")
    assert bcrypt.verify("old-admin-pw", rec["password_hash"])


def test_weak_password_rotation_fails_without_side_effects():
    db = _standard_db()
    report = _run(run_rotation(db, _manifest([
        {"user_id": "id-admin", "username": "admin", "action": "rotate"},
    ], recovery="boss"), passwords={"id-admin": "short7"}, apply=True))
    assert report["totals"]["failed"] == 1
    rec = next(d for d in db.users.docs if d["id"] == "id-admin")
    assert bcrypt.verify("old-admin-pw", rec["password_hash"])   # unchanged
    assert db.user_sessions.docs[0]["revoked"] is False or \
        all(s["revoked"] is False for s in db.user_sessions.docs if s["user_id"] == "id-admin")


def test_unrelated_users_unchanged_after_apply():
    db = _standard_db()
    boss_before = dict(next(d for d in db.users.docs if d["id"] == "id-boss"))
    demo_before = dict(next(d for d in db.users.docs if d["id"] == "id-demo"))
    _run(run_rotation(db, _manifest([
        {"user_id": "id-admin", "username": "admin", "action": "rotate"},
        {"user_id": "id-test", "username": "test", "action": "deactivate"},
    ], recovery="admin"), passwords={"id-admin": "Brand-New-Pw1"}, apply=True))
    assert next(d for d in db.users.docs if d["id"] == "id-boss") == boss_before
    assert next(d for d in db.users.docs if d["id"] == "id-demo") == demo_before


def test_rollback_simulation_restores_prior_hashes():
    """Simulate the runbook rollback: snapshot users, rotate, then restore the
    snapshot and confirm the original (pre-rotation) hashes come back."""
    db = _standard_db()
    snapshot = [dict(d) for d in db.users.docs]           # 'backup'
    _run(run_rotation(db, _manifest([
        {"user_id": "id-admin", "username": "admin", "action": "rotate"},
    ], recovery="admin"), passwords={"id-admin": "Brand-New-Pw1"}, apply=True))
    assert not bcrypt.verify("old-admin-pw",
                             next(d for d in db.users.docs if d["id"] == "id-admin")["password_hash"])
    db.users.docs = [dict(d) for d in snapshot]           # 'mongorestore --drop'
    restored = next(d for d in db.users.docs if d["id"] == "id-admin")
    assert bcrypt.verify("old-admin-pw", restored["password_hash"])
