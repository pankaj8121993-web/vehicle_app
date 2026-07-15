"""
Focused unit tests for SEC-002 legacy credential rotation
(backend/rotate_legacy_credentials.py).

These tests never connect to, modify or drop any real database. They use small
in-memory fake async collections and drive coroutines with asyncio.run() (no
pytest-asyncio needed), mirroring test_bootstrap.py.

Covers the strengthened design: per-organisation administrator-lockout
protection with recovery admins identified by exact user_id, and an exhaustive
manifest (every discovered legacy account must be listed with an explicit action).
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
    is_demo_account, _count_active_admins_in_org, LEGACY_MARKER,
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


# ----------------------------- builders --------------------------------------

ORG = "org-rajguru-foods"

# The five legacy accounts as created by the removed seeder (single org).
LEGACY_SPECS = [
    ("id-admin", "admin", "admin"),
    ("id-manager", "manager", "management"),
    ("id-de1", "dataentry1", "data_entry"),
    ("id-drv1", "driver1", "driver"),
    ("id-test", "test", "test"),
]


def _legacy(uid, username, role, org=ORG, active=True):
    return {"id": uid, "username": username, "role": role, "org_id": org,
            "is_active": active, "is_demo": False, "created_by": LEGACY_MARKER,
            "password_hash": bcrypt.hash(f"old-{username}-pw"),
            "must_change_password": True}


def _staff(uid, username, role, org, created_by="bootstrap", active=True):
    return {"id": uid, "username": username, "role": role, "org_id": org,
            "is_active": active, "is_demo": False, "created_by": created_by,
            "password_hash": bcrypt.hash(f"{username}-pw"), "must_change_password": False}


def _demo(uid="id-demo", username="demo_owner"):
    return {"id": uid, "username": username, "role": "owner", "org_id": "org-fleetflow-demo",
            "is_active": True, "is_demo": True, "created_by": "demo_seed",
            "password_hash": bcrypt.hash("random"), "must_change_password": False}


def _standard_db(extra_users=None):
    """Single-org DB: the 5 legacy accounts + a demo user + staff in other orgs."""
    users = [
        _legacy(uid, uname, role) for uid, uname, role in LEGACY_SPECS
    ] + [
        _demo(),
        _staff("id-boss", "boss", "org_admin", "org-acme", created_by="bootstrap"),
        _staff("id-ravi", "ravi", "org_admin", "org-acme2", created_by="onboarding"),
    ]
    users += (extra_users or [])
    sessions = FakeCollection([
        {"id": "s-admin", "user_id": "id-admin", "revoked": False},
        {"id": "s-test", "user_id": "id-test", "revoked": False},
        {"id": "s-demo", "user_id": "id-demo", "revoked": False},
        {"id": "s-boss", "user_id": "id-boss", "revoked": False},
    ])
    return FakeDB(users=FakeCollection(users), user_sessions=sessions)


def _rec(user_id="id-admin", username="admin", org_id=ORG, known=True):
    return {"user_id": user_id, "username": username, "org_id": org_id,
            "has_known_password": known}


def _exhaustive_actions(overrides=None):
    """All 5 legacy accounts, default 'skip', with per-user_id overrides."""
    overrides = overrides or {}
    return [{"user_id": uid, "username": uname, "action": overrides.get(uid, "skip")}
            for uid, uname, _ in LEGACY_SPECS]


def _manifest(actions, recovery_admins=None, operator="ops@x"):
    m = {"operator": operator, "actions": actions}
    if recovery_admins is not None:
        m["recovery_admins"] = recovery_admins
    return m


def _std_manifest(overrides=None, recovery_admins=None, operator="ops@x"):
    """Exhaustive single-org manifest; recovery defaults to admin (known)."""
    if recovery_admins is None:
        recovery_admins = [_rec()]
    return _manifest(_exhaustive_actions(overrides), recovery_admins, operator)


# ============================= identification ================================

def test_find_legacy_accounts_exact_set():
    db = _standard_db()
    names = sorted(a["username"] for a in _run(find_legacy_accounts(db)))
    assert names == ["admin", "dataentry1", "driver1", "manager", "test"]


def test_find_legacy_excludes_demo_and_staff():
    db = _standard_db()
    ids = {a["id"] for a in _run(find_legacy_accounts(db))}
    assert "id-demo" not in ids and "id-boss" not in ids and "id-ravi" not in ids


def test_find_legacy_projection_excludes_password_hash():
    db = _standard_db()
    assert all("password_hash" not in a for a in _run(find_legacy_accounts(db)))


def test_is_demo_account_multiple_markers():
    assert is_demo_account({"is_demo": True})
    assert is_demo_account({"created_by": "demo_seed"})
    assert is_demo_account({"org_id": "org-fleetflow-demo"})
    assert is_demo_account({"username": "demo_owner"})
    assert not is_demo_account({"username": "admin", "created_by": "system"})


# ============================= exhaustiveness ================================

def test_manifest_omitting_a_legacy_account_is_rejected():
    db = _standard_db()
    # Drop 'test' from the actions list.
    actions = [a for a in _exhaustive_actions({"id-admin": "rotate"})
               if a["user_id"] != "id-test"]
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest(actions, [_rec()])))


def test_complete_manifest_with_explicit_skip_is_accepted():
    db = _standard_db()
    # admin rotate; everyone else explicitly skip; recovery = admin (rotate).
    plan = _run(validate_manifest(db, _std_manifest(
        {"id-admin": "rotate"}, recovery_admins=[_rec(known=False)])))
    actions = {e["user"]["username"]: e["action"] for e in plan["entries"]}
    assert actions == {"admin": "rotate", "manager": "skip", "dataentry1": "skip",
                       "driver1": "skip", "test": "skip"}


def test_dry_run_shows_complete_set_and_no_writes_no_audit():
    db = _standard_db()
    before_users = [dict(d) for d in db.users.docs]
    before_sessions = [dict(d) for d in db.user_sessions.docs]
    report = _run(run_rotation(
        db, _std_manifest({"id-admin": "rotate", "id-test": "deactivate"}),
        passwords={}, apply=False))
    assert report["mode"] == "dry_run"
    # every discovered legacy account appears in the result
    assert sorted(r["username"] for r in report["results"]) == \
        ["admin", "dataentry1", "driver1", "manager", "test"]
    assert db.users.docs == before_users
    assert db.user_sessions.docs == before_sessions
    assert db.security_audit.docs == []


# ============================= rotation core ================================

def test_rotation_changes_hash_and_sets_must_change():
    db = _standard_db()
    old = next(d for d in db.users.docs if d["id"] == "id-admin")["password_hash"]
    _run(run_rotation(db, _std_manifest({"id-admin": "rotate"},
                                        recovery_admins=[_rec(known=False)]),
                      passwords={"id-admin": "Brand-New-Pw1"}, apply=True))
    rec = next(d for d in db.users.docs if d["id"] == "id-admin")
    assert rec["password_hash"] != old
    assert bcrypt.verify("Brand-New-Pw1", rec["password_hash"])
    assert rec["must_change_password"] is True


def test_only_targeted_sessions_revoked_demo_and_staff_safe():
    db = _standard_db()
    _run(run_rotation(db, _std_manifest({"id-test": "deactivate"}),
                      passwords={}, apply=True))
    by_id = {s["id"]: s for s in db.user_sessions.docs}
    assert by_id["s-test"]["revoked"] is True
    assert by_id["s-demo"]["revoked"] is False
    assert by_id["s-boss"]["revoked"] is False
    assert by_id["s-admin"]["revoked"] is False


def test_deactivate_only_when_selected():
    db = _standard_db()
    _run(run_rotation(db, _std_manifest({"id-test": "deactivate"}),
                      passwords={}, apply=True))
    assert next(d for d in db.users.docs if d["id"] == "id-test")["is_active"] is False
    assert next(d for d in db.users.docs if d["id"] == "id-admin")["is_active"] is True


def test_skip_performs_no_changes_and_no_recovery_needed():
    db = _standard_db()
    before = [dict(d) for d in db.users.docs]
    sess_before = [dict(d) for d in db.user_sessions.docs]
    # all skip -> no affected orgs -> recovery_admins not required
    _run(run_rotation(db, _manifest(_exhaustive_actions()), passwords={}, apply=True))
    assert db.users.docs == before
    assert db.user_sessions.docs == sess_before
    assert db.security_audit.docs == []


# ======================= secrecy & isolation ================================

def test_password_never_in_report_or_audit():
    db = _standard_db()
    secret = "Zx-Secret-Pass-9"
    report = _run(run_rotation(db, _std_manifest({"id-admin": "rotate"},
                                                 recovery_admins=[_rec(known=False)]),
                               passwords={"id-admin": secret}, apply=True))
    assert secret not in (str(report) + str(db.security_audit.docs))


def test_no_password_hash_in_report():
    db = _standard_db()
    report = _run(run_rotation(db, _std_manifest({"id-admin": "rotate"},
                                                 recovery_admins=[_rec(known=False)]),
                               passwords={"id-admin": "Brand-New-Pw1"}, apply=True))
    rec = next(d for d in db.users.docs if d["id"] == "id-admin")
    assert rec["password_hash"] not in str(report)
    for line in report["results"]:
        assert "password_hash" not in line


def test_demo_target_rejected_even_if_supplied():
    db = _standard_db()
    actions = _exhaustive_actions() + [
        {"user_id": "id-demo", "username": "demo_owner", "action": "rotate"}]
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest(actions, [_rec()])))


def test_audit_written_for_success_and_failure():
    db = _standard_db()
    _run(run_rotation(db, _std_manifest({"id-test": "deactivate"}),
                      passwords={}, apply=True))
    assert len(db.security_audit.docs) == 1
    a = db.security_audit.docs[0]
    assert a["outcome"] == "deactivated" and a["action"] == "deactivate"
    assert "password" not in a and "password_hash" not in a and "token" not in a

    # failure path: rotate that can't match a document
    users = FailingUsersUpdate([
        _legacy("id-admin", "admin", "admin"),
        _staff("id-boss2", "boss2", "org_admin", ORG),
    ])
    db2 = FakeDB(users=users)
    _run(run_rotation(db2, _manifest(
        [{"user_id": "id-admin", "username": "admin", "action": "rotate"}],
        [_rec("id-boss2", "boss2", ORG, known=True)]),
        passwords={"id-admin": "Brand-New-Pw1"}, apply=True))
    assert any(r["outcome"] == "failed" and r.get("failure_category")
               for r in db2.security_audit.docs)


# ======================= manifest structural rejects ========================

def test_manifest_rejects_password_field():
    db = _standard_db()
    actions = _exhaustive_actions({"id-admin": "rotate"})
    actions[0]["password"] = "nope"
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest(actions, [_rec()])))


def test_manifest_rejects_unknown_user_id():
    db = _standard_db()
    actions = _exhaustive_actions() + [
        {"user_id": "id-nope", "username": "ghost", "action": "rotate"}]
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest(actions, [_rec()])))


def test_manifest_rejects_duplicate_targets():
    db = _standard_db()
    actions = _exhaustive_actions() + [
        {"user_id": "id-admin", "username": "admin", "action": "skip"}]
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest(actions, [_rec()])))


def test_manifest_rejects_nonlegacy_staff_target():
    db = _standard_db()
    actions = _exhaustive_actions() + [
        {"user_id": "id-boss", "username": "boss", "action": "rotate"}]
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest(actions, [_rec()])))


def test_manifest_rejects_username_mismatch():
    db = _standard_db()
    actions = _exhaustive_actions({"id-admin": "rotate"})
    actions[0]["username"] = "manager"   # wrong username for id-admin
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest(actions, [_rec()])))


def test_manifest_rejects_invalid_action():
    db = _standard_db()
    actions = _exhaustive_actions()
    actions[0]["action"] = "delete"
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest(actions, [_rec()])))


# =================== per-organisation lockout protection ====================

def _two_org_db():
    """org-A: legacy admin 'admina' + legacy driver 'drivera'.
       org-B: legacy admin 'adminb'."""
    users = FakeCollection([
        _legacy("id-a-admin", "admina", "admin", org="org-A"),
        _legacy("id-a-drv", "drivera", "driver", org="org-A"),
        _legacy("id-b-admin", "adminb", "admin", org="org-B"),
    ])
    return FakeDB(users=users)


def test_orgB_admin_cannot_protect_orgA():
    db = _two_org_db()
    # Exhaustive manifest (all three legacy accounts), affecting org-A, but the
    # only recovery admin declared belongs to org-B.
    actions = [
        {"user_id": "id-a-admin", "username": "admina", "action": "rotate"},
        {"user_id": "id-a-drv", "username": "drivera", "action": "skip"},
        {"user_id": "id-b-admin", "username": "adminb", "action": "skip"},
    ]
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest(
            actions, [_rec("id-b-admin", "adminb", "org-B", known=True)])))


def test_last_admin_in_affected_org_cannot_be_deactivated():
    db = _two_org_db()
    actions = [
        {"user_id": "id-a-admin", "username": "admina", "action": "deactivate"},
        {"user_id": "id-a-drv", "username": "drivera", "action": "skip"},
        {"user_id": "id-b-admin", "username": "adminb", "action": "skip"},
    ]
    # Recovery for org-A can only be admina, but it's being deactivated -> refuse.
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest(
            actions, [_rec("id-a-admin", "admina", "org-A", known=True)])))


def test_recovery_admin_must_belong_to_affected_org():
    db = _two_org_db()
    actions = [
        {"user_id": "id-a-admin", "username": "admina", "action": "rotate"},
        {"user_id": "id-a-drv", "username": "drivera", "action": "skip"},
        {"user_id": "id-b-admin", "username": "adminb", "action": "skip"},
    ]
    # Declare adminb but claim it belongs to org-A -> cross-org mismatch refused.
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest(
            actions, [_rec("id-b-admin", "adminb", "org-A", known=True)])))


def test_recovery_by_exact_user_id_works():
    db = _two_org_db()
    actions = [
        {"user_id": "id-a-admin", "username": "admina", "action": "rotate"},
        {"user_id": "id-a-drv", "username": "drivera", "action": "skip"},
        {"user_id": "id-b-admin", "username": "adminb", "action": "skip"},
    ]
    plan = _run(validate_manifest(db, _manifest(
        actions, [_rec("id-a-admin", "admina", "org-A", known=False)])))
    assert plan["affected_orgs"] == ["org-A"]
    assert plan["recovery_admins"]["org-A"]["user_id"] == "id-a-admin"


def test_duplicate_usernames_across_orgs_no_ambiguity():
    # Two users share username 'admin' across orgs; recovery is by user_id.
    users = FakeCollection([
        _legacy("id-a-admin", "admin", "admin", org="org-A"),
        _legacy("id-b-admin", "admin", "admin", org="org-B"),
    ])
    db = FakeDB(users=users)
    actions = [
        {"user_id": "id-a-admin", "username": "admin", "action": "rotate"},
        {"user_id": "id-b-admin", "username": "admin", "action": "skip"},
    ]
    plan = _run(validate_manifest(db, _manifest(
        actions, [_rec("id-a-admin", "admin", "org-A", known=False)])))
    # Unambiguously resolved to the org-A user by id.
    assert plan["recovery_admins"]["org-A"]["user_id"] == "id-a-admin"


def test_nonlegacy_bootstrap_admin_same_org_may_be_recovery():
    # org-A: legacy admin being deactivated, plus a bootstrap admin that remains.
    users = FakeCollection([
        _legacy("id-a-admin", "admina", "admin", org="org-A"),
        _staff("id-a-boss", "aboss", "org_admin", "org-A", created_by="bootstrap"),
    ])
    db = FakeDB(users=users)
    actions = [{"user_id": "id-a-admin", "username": "admina", "action": "deactivate"}]
    # Recovery = the non-legacy bootstrap admin in the SAME org, known password.
    plan = _run(validate_manifest(db, _manifest(
        actions, [_rec("id-a-boss", "aboss", "org-A", known=True)])))
    assert plan["recovery_admins"]["org-A"]["user_id"] == "id-a-boss"
    # And it can be applied: legacy admin deactivated, bootstrap admin remains.
    _run(run_rotation(db, _manifest(actions,
                                    [_rec("id-a-boss", "aboss", "org-A", known=True)]),
                      passwords={}, apply=True))
    assert next(d for d in db.users.docs if d["id"] == "id-a-admin")["is_active"] is False
    assert next(d for d in db.users.docs if d["id"] == "id-a-boss")["is_active"] is True


def test_recovery_admin_wrong_role_rejected():
    db = _two_org_db()
    actions = [
        {"user_id": "id-a-admin", "username": "admina", "action": "rotate"},
        {"user_id": "id-a-drv", "username": "drivera", "action": "skip"},
        {"user_id": "id-b-admin", "username": "adminb", "action": "skip"},
    ]
    # drivera is not an admin role -> cannot be recovery admin.
    with pytest.raises(RotationError):
        _run(validate_manifest(db, _manifest(
            actions, [_rec("id-a-drv", "drivera", "org-A", known=True)])))


def test_count_active_admins_is_per_org():
    users = FakeCollection([
        _legacy("id-a-admin", "admina", "admin", org="org-A"),
        _staff("id-b-admin", "adminb", "org_admin", "org-B"),
        _demo("id-a-demoadmin", "demo_admin"),   # demo never counts
    ])
    db = FakeDB(users=users)
    assert _run(_count_active_admins_in_org(db, "org-A")) == 1
    assert _run(_count_active_admins_in_org(db, "org-B")) == 1
    # excluding org-A's only admin leaves zero for org-A (B's admin never helps)
    assert _run(_count_active_admins_in_org(db, "org-A", exclude_ids=["id-a-admin"])) == 0


# ======================= failure / integrity paths ==========================

def test_partial_failure_does_not_revoke_sessions():
    users = FailingUsersUpdate([
        _legacy("id-admin", "admin", "admin"),
        _staff("id-boss2", "boss2", "org_admin", ORG),
    ])
    sessions = FakeCollection([{"id": "s-admin", "user_id": "id-admin", "revoked": False}])
    db = FakeDB(users=users, user_sessions=sessions)
    report = _run(run_rotation(db, _manifest(
        [{"user_id": "id-admin", "username": "admin", "action": "rotate"}],
        [_rec("id-boss2", "boss2", ORG, known=True)]),
        passwords={"id-admin": "Brand-New-Pw1"}, apply=True))
    assert report["totals"]["failed"] == 1
    assert db.user_sessions.docs[0]["revoked"] is False


def test_missing_password_for_rotate_in_apply_is_refused():
    db = _standard_db()
    with pytest.raises(RotationError):
        _run(run_rotation(db, _std_manifest({"id-admin": "rotate"},
                                            recovery_admins=[_rec(known=False)]),
                          passwords={}, apply=True))
    rec = next(d for d in db.users.docs if d["id"] == "id-admin")
    assert bcrypt.verify("old-admin-pw", rec["password_hash"])


def test_weak_password_rotation_fails_without_side_effects():
    db = _standard_db()
    report = _run(run_rotation(db, _std_manifest({"id-admin": "rotate"},
                                                 recovery_admins=[_rec(known=True)]),
                               passwords={"id-admin": "short7"}, apply=True))
    assert report["totals"]["failed"] == 1
    rec = next(d for d in db.users.docs if d["id"] == "id-admin")
    assert bcrypt.verify("old-admin-pw", rec["password_hash"])
    assert next(s for s in db.user_sessions.docs if s["id"] == "s-admin")["revoked"] is False


def test_unrelated_users_unchanged_after_apply():
    db = _standard_db()
    boss_before = dict(next(d for d in db.users.docs if d["id"] == "id-boss"))
    demo_before = dict(next(d for d in db.users.docs if d["id"] == "id-demo"))
    _run(run_rotation(db, _std_manifest({"id-admin": "rotate", "id-test": "deactivate"},
                                        recovery_admins=[_rec(known=False)]),
                      passwords={"id-admin": "Brand-New-Pw1"}, apply=True))
    assert next(d for d in db.users.docs if d["id"] == "id-boss") == boss_before
    assert next(d for d in db.users.docs if d["id"] == "id-demo") == demo_before


def test_rollback_simulation_restores_prior_hashes():
    db = _standard_db()
    snapshot = [dict(d) for d in db.users.docs]          # 'backup'
    _run(run_rotation(db, _std_manifest({"id-admin": "rotate"},
                                        recovery_admins=[_rec(known=False)]),
                      passwords={"id-admin": "Brand-New-Pw1"}, apply=True))
    assert not bcrypt.verify(
        "old-admin-pw",
        next(d for d in db.users.docs if d["id"] == "id-admin")["password_hash"])
    db.users.docs = [dict(d) for d in snapshot]          # 'mongorestore --drop'
    restored = next(d for d in db.users.docs if d["id"] == "id-admin")
    assert bcrypt.verify("old-admin-pw", restored["password_hash"])
