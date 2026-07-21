#!/usr/bin/env bash
#
# SEC-004 rehearsal harness — exercises the credential-rotation tool end to end
# against a UNIQUE, DISPOSABLE, SYNTHETIC database so an operator can prove the
# tool behaves before touching production.
#
# It NEVER touches production and NEVER touches the dev "test_database":
#   * it reads the Mongo endpoint from the environment only (never from an
#     argument), and refuses a connection string that carries credentials or a
#     non-local host unless REHEARSAL_ALLOW_REMOTE=1 is explicitly set;
#   * it creates its own throwaway database with a generated name and refuses to
#     run if that name resolves to "test_database";
#   * every organisation, user and session it creates is synthetic;
#   * it drops the throwaway database on exit, including on failure (trap);
#   * it prints only synthetic identifiers and redacted results, and never
#     prints the connection string.
#
# Usage:
#   MONGO_URL=mongodb://localhost:27017 bash scripts/rehearse_sec004.sh
#   REHEARSAL_ASSUME_YES=1 ...   # skip the confirmation prompt (CI)
#   REHEARSAL_ALLOW_REMOTE=1 ... # allow a non-local host (still refuses creds)
#
# Exit code is non-zero if any assertion fails.

set -euo pipefail

# --- No connection string may be passed as an argument -----------------------
if [ "$#" -gt 0 ]; then
  echo "ERROR: this script takes no arguments. Configure MONGO_URL in the" >&2
  echo "       environment instead (never pass a connection string on the CLI)." >&2
  exit 2
fi

PY="${REHEARSAL_PYTHON:-/root/.venv/bin/python}"
MONGO_URL="${MONGO_URL:-mongodb://localhost:27017}"

# --- Refuse production-like / unsafe targets ---------------------------------
# These checks operate on the endpoint's shape only; the value is never printed.
"$PY" - "$MONGO_URL" <<'PYGUARD'
import sys, urllib.parse
url = sys.argv[1]
p = urllib.parse.urlparse(url)
import os
allow_remote = os.environ.get("REHEARSAL_ALLOW_REMOTE") == "1"
if p.username or p.password or "@" in (p.netloc or ""):
    sys.stderr.write("ERROR: refusing a connection string that carries credentials "
                     "(looks production-like).\n")
    sys.exit(2)
host = (p.hostname or "").lower()
if host not in ("localhost", "127.0.0.1") and not allow_remote:
    sys.stderr.write("ERROR: refusing a non-local Mongo host. Set "
                     "REHEARSAL_ALLOW_REMOTE=1 only if this is a disposable test "
                     "instance, never production.\n")
    sys.exit(2)
# A path component in the URI (a default DB) must not be the dev database.
if (p.path or "").lstrip("/").split("?")[0] == "test_database":
    sys.stderr.write("ERROR: refusing a URI whose database is 'test_database'.\n")
    sys.exit(2)
PYGUARD

# --- Generate the throwaway database name ------------------------------------
STAMP="$(date -u +%Y%m%d%H%M%S)"
REHEARSAL_DB="sec004_rehearsal_${STAMP}_$$"
if [ "$REHEARSAL_DB" = "test_database" ]; then
  echo "ERROR: generated name collided with test_database; aborting." >&2
  exit 2
fi
echo "Rehearsal database: $REHEARSAL_DB  (synthetic, disposable)"

# --- Cleanup trap: drop the throwaway DB on any exit -------------------------
cleanup() {
  MONGO_URL="$MONGO_URL" REHEARSAL_DB="$REHEARSAL_DB" "$PY" - <<'PYDROP' || true
import os
from pymongo import MongoClient
try:
    MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=3000).drop_database(
        os.environ["REHEARSAL_DB"])
    print(f"Dropped rehearsal database {os.environ['REHEARSAL_DB']}.")
except Exception as e:  # noqa: BLE001
    print(f"(cleanup) could not drop rehearsal database: {type(e).__name__}")
PYDROP
}
trap cleanup EXIT

# --- Confirmation before applying changes to the throwaway database ----------
if [ "${REHEARSAL_ASSUME_YES:-}" != "1" ]; then
  echo
  echo "This will SEED synthetic data into '$REHEARSAL_DB' and run the SEC-002"
  echo "rotation tool in dry-run and then --apply mode AGAINST THAT THROWAWAY"
  echo "DATABASE ONLY. Nothing else is touched. The database is dropped at the end."
  read -r -p "Type REHEARSE to proceed: " reply
  if [ "$reply" != "REHEARSE" ]; then
    echo "Aborted; nothing was changed."
    exit 1
  fi
fi

# --- Run the rehearsal (seed → dry-run → apply → assert) ---------------------
cd "$(dirname "$0")/../backend"
MONGO_URL="$MONGO_URL" REHEARSAL_DB="$REHEARSAL_DB" "$PY" - <<'PYREHEARSE'
import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient
from passlib.hash import bcrypt

import rotate_legacy_credentials as rot
from demo_seed import DEMO_ORG_ID

MONGO_URL = os.environ["MONGO_URL"]
DB = os.environ["REHEARSAL_DB"]

# --- Synthetic identifiers (never real) --------------------------------------
ORG_A = "org-rehearsal-alpha"
ORG_B = "org-rehearsal-bravo"

# password_hash values are synthetic — created here, thrown away with the DB.
def H(pw):
    return bcrypt.hash(pw)

# Users: (id, org, username, role, created_by, is_active, is_demo, password)
USERS = [
    # Org A
    ("ra-recovery-a", ORG_A, "recovery_admin_a", "org_admin", "onboarding", True, False, "OldRecoveryA!1"),
    ("ra-legacy-de-a", ORG_A, "legacy_de_a",     "data_entry", "system",    True, False, "LeakedDefault!1"),
    ("ra-legacy-test-a", ORG_A, "legacy_test_a", "test",      "system",     True, False, "LeakedDefault!2"),
    # Org B
    ("rb-legacy-admin-b", ORG_B, "legacy_admin_b", "org_admin", "system",   True, False, "LeakedDefault!3"),
    ("rb-legacy-view-b",  ORG_B, "legacy_view_b",  "viewer",    "system",   True, False, "LeakedDefault!4"),
    # Demo (must remain untouched)
    ("rd-demo-admin", DEMO_ORG_ID, "demo_org_admin", "org_admin", "demo_seed", True, True, "DemoPass!1"),
]

# Sessions: (id, user_id, revoked)
SESSIONS = [
    ("s-recovery-a",  "ra-recovery-a",   False),   # skip user  → must stay active
    ("s-legacy-de-a", "ra-legacy-de-a",  False),   # rotate     → must be revoked
    ("s-legacy-test-a", "ra-legacy-test-a", False),# deactivate → must be revoked
    ("s-legacy-admin-b", "rb-legacy-admin-b", False), # rotate  → must be revoked
    ("s-legacy-view-b", "rb-legacy-view-b", False),# skip       → must stay active
    ("s-demo",        "rd-demo-admin",   False),   # demo       → must stay active
]

# Exhaustive manifest: every discovered legacy account (created_by="system",
# non-demo) exactly once, with an explicit action.
MANIFEST = {
    "operator": "rehearsal-synthetic",
    "actions": [
        {"user_id": "ra-legacy-de-a",   "username": "legacy_de_a",   "action": "rotate"},
        {"user_id": "ra-legacy-test-a", "username": "legacy_test_a", "action": "deactivate"},
        {"user_id": "rb-legacy-admin-b","username": "legacy_admin_b","action": "rotate"},
        {"user_id": "rb-legacy-view-b", "username": "legacy_view_b", "action": "skip"},
    ],
    "recovery_admins": [
        # Org A: a non-legacy admin the operator asserts already has a known password.
        {"user_id": "ra-recovery-a", "org_id": ORG_A, "username": "recovery_admin_a",
         "has_known_password": True},
        # Org B: the rotated legacy admin becomes the recovery admin (a fresh
        # known-good password is set during rotation).
        {"user_id": "rb-legacy-admin-b", "org_id": ORG_B, "username": "legacy_admin_b"},
    ],
}

# New passwords for the rotate entries (synthetic; used only to hash).
PASSWORDS = {
    "ra-legacy-de-a":    "RehearsalNew!aa11",
    "rb-legacy-admin-b": "RehearsalNew!bb22",
}

FAILURES = []

def check(cond, msg):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {msg}")
    if not cond:
        FAILURES.append(msg)


async def main():
    client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    db = client[DB]
    try:
        # Guard again inside Python: never operate on test_database.
        assert db.name != "test_database", "refusing test_database"

        # --- Seed ---
        await db.users.insert_many([
            {"id": uid, "org_id": org, "username": un, "role": role,
             "created_by": cb, "is_active": act, "is_demo": demo,
             "password_hash": H(pw)}
            for (uid, org, un, role, cb, act, demo, pw) in USERS
        ])
        await db.user_sessions.insert_many([
            {"id": sid, "user_id": uid, "revoked": rev, "token_hash": "synthetic"}
            for (sid, uid, rev) in SESSIONS
        ])
        print(f"Seeded {len(USERS)} synthetic users and {len(SESSIONS)} sessions "
              f"into {DB}.")

        # Snapshot before-state for the assertions.
        before = {u["id"]: u async for u in db.users.find({}, {"_id": 0})}

        # --- Dry-run (must write nothing) ---
        print("\nDry-run:")
        report = await rot.run_rotation(db, MANIFEST, {}, apply=False)
        check(report["mode"] == "dry_run", "dry-run reported as dry_run")
        after_dry = {u["id"]: u async for u in db.users.find({}, {"_id": 0})}
        check(all(before[i]["password_hash"] == after_dry[i]["password_hash"]
                  for i in before), "dry-run changed no password hash")
        check(await db[rot.AUDIT_COLLECTION].count_documents({}) == 0,
              "dry-run wrote no audit records")

        # --- Apply (throwaway DB only) ---
        print("\nApply:")
        report = await rot.run_rotation(db, MANIFEST, PASSWORDS, apply=True)
        t = report["totals"]
        print(f"  totals: rotated={t['rotated']} deactivated={t['deactivated']} "
              f"skipped={t['skipped']} failed={t['failed']} "
              f"sessions_revoked={t['sessions_revoked']}")

        after = {u["id"]: u async for u in db.users.find({}, {"_id": 0})}

        # 1. Password hashes changed ONLY for rotated users.
        rotated = {"ra-legacy-de-a", "rb-legacy-admin-b"}
        for uid in before:
            changed = before[uid]["password_hash"] != after[uid]["password_hash"]
            check(changed == (uid in rotated),
                  f"hash change for {uid} is correct ({'changed' if changed else 'unchanged'})")

        # 2. Deactivated users are inactive.
        check(after["ra-legacy-test-a"]["is_active"] is False,
              "deactivated user ra-legacy-test-a is inactive")

        # 3. Explicit skip users are unchanged.
        check(before["rb-legacy-view-b"] == after["rb-legacy-view-b"],
              "skip user rb-legacy-view-b is completely unchanged")

        # 4/5. Sessions: targets revoked, others still active.
        sess = {s["id"]: s async for s in db.user_sessions.find({}, {"_id": 0})}
        for sid in ("s-legacy-de-a", "s-legacy-test-a", "s-legacy-admin-b"):
            check(sess[sid]["revoked"] is True, f"target session {sid} revoked")
        for sid in ("s-recovery-a", "s-legacy-view-b", "s-demo"):
            check(sess[sid]["revoked"] is False, f"non-target session {sid} still active")

        # 6. Demo account and session unchanged.
        check(before["rd-demo-admin"] == after["rd-demo-admin"],
              "demo account unchanged")
        check(sess["s-demo"]["revoked"] is False, "demo session unchanged")

        # 7. Each affected org retains an active administrator.
        for org in (ORG_A, ORG_B):
            n = await db.users.count_documents(
                {"org_id": org, "role": {"$in": list(rot.ADMIN_ROLES)},
                 "is_active": True, "is_demo": {"$ne": True}})
            check(n >= 1, f"organisation {org} retains an active administrator")

        # 8. Audit records contain no secrets.
        audits = [a async for a in db[rot.AUDIT_COLLECTION].find({}, {"_id": 0})]
        banned = ("password", "hash", "token", "secret")
        clean = all(
            not any(b in str(k).lower() for b in banned) for a in audits for k in a
        )
        check(clean, "audit records contain no secret-looking fields")
        check(len(audits) >= 3, "audit records were written for applied actions")

    finally:
        await client.drop_database(DB)
        client.close()

    print()
    if FAILURES:
        print(f"REHEARSAL FAILED: {len(FAILURES)} assertion(s) failed.")
        raise SystemExit(1)
    print("REHEARSAL PASSED: the rotation tool behaved correctly on synthetic data.")


asyncio.run(main())
PYREHEARSE

echo
echo "Rehearsal complete."
