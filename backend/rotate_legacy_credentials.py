"""
SEC-002 — Rotate legacy default production credentials and revoke old sessions.

FleetFlow used to auto-seed five default accounts (created_by == "system") with
hardcoded passwords. SEC-001 stopped the seeding but existing databases may
still contain those rows with their known/leaked passwords. This management
command rotates (or deactivates) ONLY those legacy accounts and revokes their
sessions, with strong safeguards so it can never touch demo users, ordinary
staff, or lock out the operating administrator.

Design summary
--------------
* Strict target filter: ``created_by == "system"`` and NOT a demo account.
* Dry-run is the default; ``--apply`` is required to write anything.
* Operator supplies a reviewed, **exhaustive** JSON *manifest*: every discovered
  legacy account must appear exactly once with an explicit ``rotate`` /
  ``deactivate`` / ``skip`` action. The manifest never contains a password;
  passwords for rotations are entered interactively (hidden, twice).
* Administrator lockout protection is **per organisation**: every organisation
  affected by a rotate/deactivate must retain at least one active, non-demo
  administrator, and the manifest must declare a validated recovery
  administrator (by exact ``user_id``) that belongs to each affected
  organisation. An admin in another organisation can never satisfy this.
* Sessions are revoked only for a successfully changed account, only for that
  user, never for demo users. Session tokens are never printed.
* Every applied action is recorded in a global ``security_audit`` collection
  with non-sensitive fields only (never passwords, hashes, tokens or secrets).

Usage (run from /app/backend, never against production during development):

    # 1. List legacy accounts (no secrets, no writes) and get their user_ids:
    python -m rotate_legacy_credentials list

    # 2. Build a manifest.json (see docs/implementation/CREDENTIAL_ROTATION.md),
    #    then preview without writing (default is dry-run):
    python -m rotate_legacy_credentials apply --manifest manifest.json

    # 3. Execute for real (prompts for each rotation password, hidden):
    python -m rotate_legacy_credentials apply --manifest manifest.json --apply

A backend restart is MANDATORY after a production --apply run to flush the
in-memory session cache (see auth._session_cache). Do not rely on the ~60s
cache TTL as the revocation guarantee.
"""
import os
import json
import uuid
import asyncio
import getpass
import logging
from datetime import datetime, timezone

import typer
from passlib.hash import bcrypt

logger = logging.getLogger("fleetflow.rotate_legacy_credentials")

# --- Constants ---------------------------------------------------------------
# The unique provenance marker written by the removed SEC-001 seeder. It is used
# by no other code path (onboarding -> "onboarding", bootstrap -> "bootstrap",
# demo -> "demo_seed", admin-created -> admin UUID), so it cleanly identifies the
# legacy default accounts and nothing else.
LEGACY_MARKER = "system"
DEMO_MARKER = "demo_seed"
DEMO_ORG_ID = "org-fleetflow-demo"  # canonical demo organisation id (demo_seed.DEMO_ORG_ID)

# Administrative roles for lockout protection (mirrors auth.MODULE_ACCESS["users"]).
ADMIN_ROLES = {"admin", "org_admin"}

VALID_ACTIONS = {"rotate", "deactivate", "skip"}

# Password policy: reuse the stronger secure-provisioning minimum used by
# onboarding (routes_orgs) and bootstrap. Never weaker than any app path.
MIN_PASSWORD_LENGTH = 8

AUDIT_COLLECTION = "security_audit"
COMMAND_NAME = "rotate_legacy_credentials"

# Non-secret projection for reading accounts — deliberately excludes
# password_hash and every other sensitive field.
SAFE_USER_PROJECTION = {
    "_id": 0, "id": 1, "username": 1, "role": 1, "org_id": 1,
    "is_active": 1, "is_demo": 1, "created_by": 1, "created_at": 1,
}


class RotationError(Exception):
    """Raised for validation / pre-flight failures. Never carries secrets."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Account identification & classification ---------------------------------

def is_demo_account(user: dict) -> bool:
    """Defence-in-depth demo detection: any one marker is enough to protect."""
    return bool(
        user.get("is_demo") is True
        or user.get("created_by") == DEMO_MARKER
        or user.get("org_id") == DEMO_ORG_ID
        or str(user.get("username", "")).startswith("demo_")
    )


async def find_legacy_accounts(db) -> list:
    """Return legacy default accounts (created_by == "system"), never demo, with
    a safe projection that excludes password_hash. Read-only."""
    accounts = []
    cursor = db.users.find({"created_by": LEGACY_MARKER}, SAFE_USER_PROJECTION)
    async for u in cursor:
        if is_demo_account(u):
            # Should never happen (demo uses created_by "demo_seed"), but skip
            # defensively so a legacy record can never resolve to a demo user.
            continue
        accounts.append(u)
    return accounts


async def _count_active_admins_in_org(db, org_id, *, exclude_ids=None) -> int:
    """Count active, non-demo administrative accounts in ONE organisation,
    optionally excluding some user ids (e.g. those being deactivated).

    Lockout protection is per-organisation: in a multi-tenant system an admin in
    another organisation must never be able to satisfy this org's requirement.
    """
    exclude_ids = set(exclude_ids or [])
    n = 0
    cursor = db.users.find(
        {"org_id": org_id, "role": {"$in": list(ADMIN_ROLES)}, "is_active": True},
        SAFE_USER_PROJECTION,
    )
    async for u in cursor:
        if is_demo_account(u):
            continue
        if u["id"] in exclude_ids:
            continue
        n += 1
    return n


# --- Manifest validation -----------------------------------------------------

def _validate_password_value(password: str) -> None:
    if not password:
        raise RotationError("A replacement password is required (no default exists)")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise RotationError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


async def _validate_recovery_admins(db, manifest: dict) -> dict:
    """Validate the per-organisation recovery-admin section.

    Returns {org_id: {"user": <recovery user>, "has_known_password": bool}}.
    Each recovery admin is identified by exact user_id (never username alone),
    and its username / org_id / role / active status are all validated. Cross-
    organisation and ambiguous declarations are rejected.
    """
    raw = manifest.get("recovery_admins", [])
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise RotationError("Manifest 'recovery_admins' must be a list")

    by_org = {}
    for i, r in enumerate(raw):
        if not isinstance(r, dict):
            raise RotationError(f"recovery_admins[{i}] must be an object")
        if "password" in r:
            raise RotationError(f"recovery_admins[{i}] must not contain a password")
        uid = str(r.get("user_id") or "").strip()
        if not uid:
            raise RotationError(f"recovery_admins[{i}] must identify the admin by 'user_id'")
        declared_org = str(r.get("org_id") or "").strip()
        if not declared_org:
            raise RotationError(f"recovery_admins[{i}] must declare 'org_id'")
        declared_username = str(r.get("username") or "").strip().lower()
        has_known = bool(r.get("has_known_password", False))

        user = await db.users.find_one({"id": uid}, SAFE_USER_PROJECTION)
        if user is None:
            raise RotationError(f"recovery_admins[{i}] references unknown user_id")
        if is_demo_account(user):
            raise RotationError(f"recovery_admins[{i}] cannot be a demo account")
        if user.get("role") not in ADMIN_ROLES:
            raise RotationError(
                f"recovery_admins[{i}] must have an administrative role "
                f"(got {user.get('role')!r})"
            )
        if not user.get("is_active", True):
            raise RotationError(f"recovery_admins[{i}] account is not active")
        if declared_username and declared_username != user["username"]:
            raise RotationError(
                f"recovery_admins[{i}] username does not match the user_id's actual "
                f"username — refusing on integrity mismatch"
            )
        if user.get("org_id") != declared_org:
            raise RotationError(
                f"recovery_admins[{i}] declares org_id {declared_org!r} but the "
                f"user belongs to {user.get('org_id')!r} — cross-organisation "
                f"recovery declaration refused"
            )
        if declared_org in by_org:
            raise RotationError(
                f"recovery_admins declares more than one recovery admin for "
                f"organisation {declared_org!r} — ambiguous"
            )
        by_org[declared_org] = {"user": user, "has_known_password": has_known}
    return by_org


async def validate_manifest(db, manifest: dict) -> dict:
    """Validate a reviewed, exhaustive action manifest against the live legacy set.

    Returns a normalised plan:
        {"operator", "entries": [{user, action}...],
         "recovery_admins": {org_id: {...}}, "affected_orgs": [...]}.
    Raises RotationError on any structural or safety problem. Performs NO writes.
    """
    if not isinstance(manifest, dict):
        raise RotationError("Manifest must be a JSON object")

    operator = str(manifest.get("operator") or "").strip()
    if not operator:
        raise RotationError("Manifest must declare a non-empty 'operator' identifier")

    raw_actions = manifest.get("actions")
    if not isinstance(raw_actions, list) or not raw_actions:
        raise RotationError("Manifest 'actions' must be a non-empty list")

    legacy = {a["id"]: a for a in await find_legacy_accounts(db)}

    seen_ids = set()
    entries = []
    for i, raw in enumerate(raw_actions):
        if not isinstance(raw, dict):
            raise RotationError(f"actions[{i}] must be an object")
        uid = str(raw.get("user_id") or "").strip()
        uname = str(raw.get("username") or "").strip().lower()
        action = str(raw.get("action") or "").strip().lower()
        if "password" in raw:
            raise RotationError(f"actions[{i}] must not contain a password")
        if not uid:
            raise RotationError(f"actions[{i}] is missing 'user_id'")
        if action not in VALID_ACTIONS:
            raise RotationError(
                f"actions[{i}] has invalid action '{action}'; "
                f"expected one of {sorted(VALID_ACTIONS)}"
            )
        if uid in seen_ids:
            raise RotationError(f"actions[{i}] duplicates user_id already in the manifest")
        seen_ids.add(uid)

        user = legacy.get(uid)
        if user is None:
            # Not a legacy account: could be unknown, staff, or demo — refuse.
            probe = await db.users.find_one({"id": uid}, SAFE_USER_PROJECTION)
            if probe is None:
                raise RotationError(f"actions[{i}] references unknown user_id")
            if is_demo_account(probe):
                raise RotationError(f"actions[{i}] targets a demo account — refused")
            raise RotationError(
                f"actions[{i}] targets a non-legacy account (created_by="
                f"{probe.get('created_by')!r}) — only legacy 'system' accounts may be rotated"
            )
        if is_demo_account(user):
            raise RotationError(f"actions[{i}] resolves to a demo account — refused")
        if uname and uname != user["username"]:
            raise RotationError(
                f"actions[{i}] username '{uname}' does not match user_id's actual "
                f"username — refusing on integrity mismatch"
            )
        entries.append({"user": user, "action": action})

    # --- Exhaustiveness: every discovered legacy account must be listed once ---
    missing = [a["username"] for uid, a in legacy.items() if uid not in seen_ids]
    if missing:
        raise RotationError(
            "Manifest is not exhaustive: every discovered legacy account must "
            "appear exactly once with an explicit action. Missing: "
            + ", ".join(sorted(missing))
        )

    # --- Per-organisation recovery admins ---
    recovery_by_org = await _validate_recovery_admins(db, manifest)

    # Organisations affected by an actual change (rotate or deactivate).
    affected_orgs = sorted({
        e["user"].get("org_id") for e in entries if e["action"] in ("rotate", "deactivate")
    })

    # Every affected org needs exactly one validated recovery admin, and no
    # recovery admin may be declared for an unaffected organisation.
    for org_id in affected_orgs:
        if org_id not in recovery_by_org:
            raise RotationError(
                f"Organisation {org_id!r} is affected by this run but has no "
                f"recovery administrator declared in 'recovery_admins'"
            )
    for org_id in recovery_by_org:
        if org_id not in affected_orgs:
            raise RotationError(
                f"recovery_admins declares organisation {org_id!r}, which is not "
                f"affected by this run — remove it"
            )

    entries_by_id = {e["user"]["id"]: e for e in entries}
    for org_id in affected_orgs:
        rec = recovery_by_org[org_id]
        rec_user, rec_known = rec["user"], rec["has_known_password"]
        rec_entry = entries_by_id.get(rec_user["id"])
        if rec_entry is not None:
            if rec_entry["action"] == "deactivate":
                raise RotationError(
                    f"Refusing to deactivate the recovery administrator of "
                    f"organisation {org_id!r}"
                )
            if rec_entry["action"] == "skip" and not rec_known:
                raise RotationError(
                    f"Recovery administrator of {org_id!r} is set to 'skip' but "
                    f"'has_known_password' was not asserted"
                )
            # action == "rotate": a fresh known-good password is set interactively.
        else:
            # Recovery admin (e.g. a bootstrap/onboarding admin) is not changed;
            # operator must assert they already hold a working credential.
            if not rec_known:
                raise RotationError(
                    f"Recovery administrator of {org_id!r} is not in the manifest "
                    f"and 'has_known_password' was not asserted"
                )

        # After deactivations, this org must retain >=1 active, non-demo admin.
        deactivating_admin_ids = [
            e["user"]["id"] for e in entries
            if e["action"] == "deactivate"
            and e["user"].get("org_id") == org_id
            and e["user"].get("role") in ADMIN_ROLES
        ]
        remaining = await _count_active_admins_in_org(
            db, org_id, exclude_ids=deactivating_admin_ids
        )
        if remaining < 1:
            raise RotationError(
                f"Refusing: the selected deactivations would leave organisation "
                f"{org_id!r} with zero active administrators. At least one active "
                f"administrator must remain in every affected organisation."
            )

    return {
        "operator": operator,
        "entries": entries,
        "affected_orgs": affected_orgs,
        "recovery_admins": {
            org: {"user_id": r["user"]["id"], "username": r["user"]["username"],
                  "has_known_password": r["has_known_password"]}
            for org, r in recovery_by_org.items()
        },
    }


# --- Audit -------------------------------------------------------------------

async def _write_audit(db, record: dict) -> None:
    """Insert a non-sensitive audit record. Never called in dry-run mode."""
    doc = {"id": str(uuid.uuid4()), "ts": _now_iso(), "command": COMMAND_NAME}
    doc.update(record)
    await db[AUDIT_COLLECTION].insert_one(doc)


# --- Actions -----------------------------------------------------------------

async def _revoke_sessions(db, user_id: str) -> int:
    """Revoke all sessions of one user. Returns the count revoked. Never touches
    other users. (Demo users are never passed here.)"""
    res = await db.user_sessions.update_many(
        {"user_id": user_id, "revoked": {"$ne": True}}, {"$set": {"revoked": True}}
    )
    return getattr(res, "modified_count", 0) or 0


async def _rotate_one(db, user: dict, new_password: str) -> int:
    """Rotate a single account: validate policy, hash, set must_change_password,
    then (only on success) revoke that user's sessions. Returns sessions revoked.

    If the password update does not succeed, sessions are NOT revoked and the
    error propagates so no half-done state is recorded as success.
    """
    _validate_password_value(new_password)
    res = await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": bcrypt.hash(new_password),
                  "must_change_password": True}},
    )
    if getattr(res, "matched_count", 0) == 0:
        raise RotationError("Password update matched no document; sessions left intact")
    return await _revoke_sessions(db, user["id"])


async def _deactivate_one(db, user: dict) -> int:
    """Deactivate a single account and revoke its sessions. Returns sessions revoked."""
    res = await db.users.update_one({"id": user["id"]}, {"$set": {"is_active": False}})
    if getattr(res, "matched_count", 0) == 0:
        raise RotationError("Deactivation matched no document; sessions left intact")
    return await _revoke_sessions(db, user["id"])


# --- Orchestration -----------------------------------------------------------

async def run_rotation(db, manifest: dict, passwords: dict, *, apply: bool) -> dict:
    """Validate the manifest and either preview (dry-run) or execute.

    `passwords` maps user_id -> plaintext for every entry whose action is
    "rotate". In dry-run mode passwords may be omitted. The plaintext values are
    used only to hash; they are never stored in the report, audit or logs.
    Returns a report dict containing no secrets.
    """
    plan = await validate_manifest(db, manifest)
    operator = plan["operator"]
    report = {
        "mode": "apply" if apply else "dry_run",
        "operator": operator,
        "affected_orgs": plan["affected_orgs"],
        "recovery_admins": plan["recovery_admins"],
        "results": [],
        "totals": {"rotated": 0, "deactivated": 0, "skipped": 0,
                   "failed": 0, "sessions_revoked": 0},
    }

    # In apply mode, verify a password was supplied for every rotate entry
    # BEFORE making any change, so we do not half-apply the plan.
    if apply:
        for e in plan["entries"]:
            if e["action"] == "rotate" and not passwords.get(e["user"]["id"]):
                raise RotationError(
                    f"Missing password for rotation of user_id {e['user']['id']}"
                )

    for e in plan["entries"]:
        user, action = e["user"], e["action"]
        line = {
            "user_id": user["id"], "username": user["username"],
            "org_id": user.get("org_id"), "action": action,
            "outcome": "planned" if not apply else None, "sessions_revoked": 0,
        }

        if not apply:
            # Dry-run: no writes, no audit records.
            report["results"].append(line)
            report["totals"][
                {"rotate": "rotated", "deactivate": "deactivated", "skip": "skipped"}[action]
            ] += 1
            continue

        try:
            if action == "rotate":
                revoked = await _rotate_one(db, user, passwords[user["id"]])
                line["outcome"], line["sessions_revoked"] = "rotated", revoked
                report["totals"]["rotated"] += 1
            elif action == "deactivate":
                revoked = await _deactivate_one(db, user)
                line["outcome"], line["sessions_revoked"] = "deactivated", revoked
                report["totals"]["deactivated"] += 1
            else:  # skip
                line["outcome"] = "skipped"
                report["totals"]["skipped"] += 1
            report["totals"]["sessions_revoked"] += line["sessions_revoked"]
            if action != "skip":
                await _write_audit(db, {
                    "operator": operator, "action": action, "outcome": line["outcome"],
                    "user_id": user["id"], "username": user["username"],
                    "org_id": user.get("org_id"), "sessions_revoked": line["sessions_revoked"],
                })
        except Exception as exc:  # noqa: BLE001 - record failure, continue others
            line["outcome"] = "failed"
            line["failure_category"] = type(exc).__name__
            report["totals"]["failed"] += 1
            # Audit the failure with a category only (never the message/secrets).
            await _write_audit(db, {
                "operator": operator, "action": action, "outcome": "failed",
                "user_id": user["id"], "username": user["username"],
                "org_id": user.get("org_id"), "sessions_revoked": 0,
                "failure_category": type(exc).__name__,
            })

        report["results"].append(line)

    return report


# ----------------------------- CLI wrapper -----------------------------------

cli = typer.Typer(add_completion=False, help="SEC-002 legacy credential rotation.")


@cli.callback()
def _main():
    """SEC-002 legacy credential rotation. Dry-run by default; --apply to execute."""


def _connect():
    """Return (client, db) from MONGO_URL/DB_NAME, or exit with a clear message."""
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        typer.secho("MONGO_URL and DB_NAME must be set to reach the database.",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    client = AsyncIOMotorClient(mongo_url)
    return client, client[db_name]


@cli.command("list")
def list_accounts():
    """List legacy default accounts (no secrets, no writes)."""
    async def _run():
        client, db = _connect()
        try:
            accts = await find_legacy_accounts(db)
            # attach session counts (non-sensitive) for operator review
            for a in accts:
                a["active_sessions"] = await db.user_sessions.count_documents(
                    {"user_id": a["id"], "revoked": {"$ne": True}}
                )
            return accts
        finally:
            client.close()

    accts = asyncio.run(_run())
    if not accts:
        typer.echo("No legacy (created_by='system') accounts found.")
        return
    typer.echo(f"{'user_id':38}  {'username':14}  {'role':12}  active  sessions")
    for a in accts:
        typer.echo(
            f"{a['id']:38}  {a['username']:14}  {str(a.get('role')):12}  "
            f"{str(a.get('is_active', True)):6}  {a.get('active_sessions', 0)}"
        )
    typer.echo("\nBuild a manifest.json selecting an action per account, then run "
               "'apply --manifest manifest.json' (add --apply to execute).")


@cli.command("apply")
def apply_manifest(
    manifest: str = typer.Option(..., "--manifest", help="Path to reviewed action manifest (JSON)."),
    apply: bool = typer.Option(False, "--apply", help="Execute changes. Omitted = dry-run."),
):
    """Validate a manifest and preview (default) or execute (--apply) rotation."""
    try:
        with open(manifest, "r", encoding="utf-8") as fh:
            manifest_doc = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        typer.secho(f"Could not read manifest: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    async def _run(passwords):
        client, db = _connect()
        try:
            return await run_rotation(db, manifest_doc, passwords, apply=apply)
        finally:
            client.close()

    # For --apply, collect a hidden, confirmed password for every rotate entry
    # BEFORE touching the database. Validate the manifest first (read-only) so we
    # only prompt for genuinely valid rotations.
    passwords = {}
    if apply:
        async def _plan():
            client, db = _connect()
            try:
                return await validate_manifest(db, manifest_doc)
            finally:
                client.close()
        try:
            plan = asyncio.run(_plan())
        except RotationError as e:
            typer.secho(f"Manifest rejected: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        rotate_entries = [e for e in plan["entries"] if e["action"] == "rotate"]
        if rotate_entries:
            typer.secho("Enter a new password for each account to rotate "
                        "(hidden, entered twice).", fg=typer.colors.YELLOW)
        for e in rotate_entries:
            u = e["user"]
            while True:
                pw1 = getpass.getpass(f"  New password for '{u['username']}': ")
                pw2 = getpass.getpass(f"  Confirm password for '{u['username']}': ")
                if pw1 != pw2:
                    typer.secho("  Passwords did not match; try again.", fg=typer.colors.RED)
                    continue
                try:
                    _validate_password_value(pw1)
                except RotationError as ve:
                    typer.secho(f"  {ve}", fg=typer.colors.RED)
                    continue
                passwords[u["id"]] = pw1
                break

        # Explicit final confirmation before any write.
        typer.secho(
            f"\nAbout to APPLY changes as operator '{plan['operator']}': "
            f"{len(rotate_entries)} rotate, "
            f"{sum(1 for e in plan['entries'] if e['action']=='deactivate')} deactivate, "
            f"{sum(1 for e in plan['entries'] if e['action']=='skip')} skip.",
            fg=typer.colors.YELLOW,
        )
        typed = typer.prompt("Type APPLY to proceed")
        if typed != "APPLY":
            typer.secho("Aborted; no changes made.", fg=typer.colors.RED)
            raise typer.Exit(code=1)

    try:
        report = asyncio.run(_run(passwords))
    except RotationError as e:
        typer.secho(f"Rotation refused: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    t = report["totals"]
    typer.secho(f"\nMode: {report['mode']}  Operator: {report['operator']}",
                fg=typer.colors.GREEN if report["mode"] == "apply" else typer.colors.CYAN)
    typer.echo(f"Affected organisations: {', '.join(report['affected_orgs']) or '(none)'}")
    typer.echo("Recovery administrators:")
    for org, rec in report["recovery_admins"].items():
        typer.echo(f"  {org}: {rec['username']} ({rec['user_id']})")
    typer.echo("\nComplete discovered legacy set and selected action:")
    typer.echo(f"  {'username':14} {'org_id':22} {'action':11} {'outcome':9} sessions")
    for line in report["results"]:
        typer.echo(f"  {line['username']:14} {str(line.get('org_id')):22} "
                   f"{line['action']:11} {str(line['outcome']):9} "
                   f"{line['sessions_revoked']}")
    typer.echo(f"Totals: rotated={t['rotated']} deactivated={t['deactivated']} "
               f"skipped={t['skipped']} failed={t['failed']} "
               f"sessions_revoked={t['sessions_revoked']}")
    if report["mode"] == "dry_run":
        typer.secho("Dry-run only — no changes were written and no audit records "
                    "were created. Re-run with --apply to execute.", fg=typer.colors.CYAN)
    else:
        typer.secho("APPLIED. You MUST restart the backend now to flush the "
                    "in-memory session cache (auth._session_cache).",
                    fg=typer.colors.YELLOW)


if __name__ == "__main__":
    cli()
