"""
Secure one-time first-installation bootstrap for FleetFlow.

Creates the very first organisation and its `org_admin` on a *completely new*
installation. It refuses to run if the database already contains any user, so
it can never reset or modify existing accounts.

Usage (run from /app/backend, or `python -m bootstrap` with backend on PYTHONPATH):

    python -m bootstrap create-admin

Interactive prompts collect the organisation name, username, email, full name
and a hidden (confirmed) password. There is no default password and no fallback
credential of any kind.

Non-interactive automation (optional) reads the values from explicit
environment variables and fails safely if any required value is missing:

    FLEETFLOW_BOOTSTRAP_ORG_NAME
    FLEETFLOW_BOOTSTRAP_USERNAME
    FLEETFLOW_BOOTSTRAP_EMAIL
    FLEETFLOW_BOOTSTRAP_FULL_NAME
    FLEETFLOW_BOOTSTRAP_PASSWORD

    python -m bootstrap create-admin --non-interactive

The password is never accepted as an ordinary command-line argument, and is
never printed, returned, logged or embedded in an exception message.
"""
import os
import re
import uuid
import asyncio
import logging
from datetime import datetime, timezone

import typer
from passlib.hash import bcrypt

logger = logging.getLogger("fleetflow.bootstrap")

# --- Validation rules (mirror onboarding in routes_orgs.register_org) ---------
# Kept intentionally identical to the self-registration flow. SEC-001 does not
# redesign the password policy; it only reuses the existing minimum.
USERNAME_RE = re.compile(r"[a-z0-9._-]{3,40}")
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
MIN_PASSWORD_LENGTH = 8


class BootstrapError(Exception):
    """Raised for any refusal or validation failure. Never carries secrets."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_identity(*, org_name: str, username: str, email: str, full_name: str) -> tuple:
    org_name = (org_name or "").strip()
    username = (username or "").lower().strip()
    email = (email or "").lower().strip()
    full_name = (full_name or "").strip()

    if not org_name:
        raise BootstrapError("Organisation name is required")
    if not USERNAME_RE.fullmatch(username):
        raise BootstrapError("Username must be 3-40 chars (letters, numbers, . _ -)")
    if not EMAIL_RE.fullmatch(email):
        raise BootstrapError("A valid administrator email is required")
    if not full_name:
        raise BootstrapError("Administrator full name is required")
    return org_name, username, email, full_name


def _validate_password(password: str) -> None:
    # Never include the password value in the error.
    if not password:
        raise BootstrapError("A password is required (no default password exists)")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise BootstrapError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


async def create_first_admin(
    db,
    *,
    org_name: str,
    username: str,
    email: str,
    full_name: str,
    password: str,
) -> dict:
    """Create the first organisation + org_admin, only on an empty installation.

    Refuses (raises BootstrapError) if the database already contains ANY user,
    so it can never reset or modify an existing account. Returns a safe summary
    dict that never contains the password or the password hash.
    """
    org_name, username, email, full_name = _validate_identity(
        org_name=org_name, username=username, email=email, full_name=full_name
    )
    _validate_password(password)

    # Hard refusal: the installation must have zero users. We deliberately count
    # *all* users rather than checking for a matching username/email so a second
    # run (or any pre-existing account, including a demo user) is non-destructive.
    total_users = await db.users.count_documents({})
    if total_users > 0:
        raise BootstrapError(
            "Refusing to bootstrap: the database already contains "
            f"{total_users} user(s). The first admin can only be created on a "
            "completely new installation. No account was modified."
        )

    org_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    created_at = _now_iso()

    org_doc = {
        "id": org_id,
        "legal_name": org_name,
        "legal_name_lc": org_name.lower(),
        "trade_name": org_name,
        "org_type": "Company",
        "fleet_ownership": "Owned",
        "country": "India",
        "currency": "INR",
        "timezone": "Asia/Kolkata",
        "fy_start_month": 4,
        "compliance_docs": ["RC", "Insurance", "Fitness", "Permit", "PUC", "Road Tax"],
        "is_demo": False,
        "is_default": False,
        "onboarding_completed": True,
        "created_at": created_at,
        "created_by": "bootstrap",
    }
    user_doc = {
        "id": user_id,
        "org_id": org_id,
        "username": username,
        "email": email,
        "password_hash": bcrypt.hash(password),
        "role": "org_admin",
        "full_name": full_name,
        "is_active": True,
        "is_demo": False,
        "must_change_password": False,
        "created_at": created_at,
        "created_by": "bootstrap",
    }

    # No cross-document transaction is assumed (standalone Mongo is supported).
    # Insert the organisation first, then the user; if the user insert fails,
    # compensate by removing the just-created organisation so we never leave a
    # half-provisioned tenant behind. The zero-user precondition guarantees we
    # are not racing an existing installation.
    await db.organizations.insert_one(org_doc)
    try:
        await db.users.insert_one(user_doc)
    except Exception:
        try:
            await db.organizations.delete_one({"id": org_id})
        except Exception:
            logger.error("Bootstrap rollback failed for organisation %s", org_id)
        raise

    logger.info(
        "Bootstrap created first organisation %s and org_admin %s (%s)",
        org_id, user_id, username,
    )
    # Safe summary only — never expose password or hash.
    return {
        "org_id": org_id,
        "org_name": org_name,
        "user_id": user_id,
        "username": username,
        "email": email,
        "role": "org_admin",
    }


# ----------------------------- CLI wrapper -----------------------------------

cli = typer.Typer(add_completion=False, help="FleetFlow first-installation bootstrap.")


@cli.callback()
def _main():
    """FleetFlow first-installation bootstrap.

    Present so the CLI keeps its explicit `create-admin` subcommand rather than
    collapsing into a single flat command.
    """

_ENV = {
    "org_name": "FLEETFLOW_BOOTSTRAP_ORG_NAME",
    "username": "FLEETFLOW_BOOTSTRAP_USERNAME",
    "email": "FLEETFLOW_BOOTSTRAP_EMAIL",
    "full_name": "FLEETFLOW_BOOTSTRAP_FULL_NAME",
    "password": "FLEETFLOW_BOOTSTRAP_PASSWORD",
}


def _collect_non_interactive() -> dict:
    values = {}
    missing = []
    for field, env in _ENV.items():
        val = os.environ.get(env)
        if not val:
            missing.append(env)
        else:
            values[field] = val
    if missing:
        # Never print secret values; only names of the missing variables.
        raise BootstrapError(
            "Missing required environment variable(s): " + ", ".join(missing)
        )
    return values


def _collect_interactive() -> dict:
    return {
        "org_name": typer.prompt("Organisation name"),
        "username": typer.prompt("Admin username"),
        "email": typer.prompt("Admin email"),
        "full_name": typer.prompt("Admin full name"),
        # Hidden, entered twice; never echoed.
        "password": typer.prompt(
            "Admin password", hide_input=True, confirmation_prompt=True
        ),
    }


@cli.command("create-admin")
def create_admin(
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Read all values from FLEETFLOW_BOOTSTRAP_* environment variables.",
    ),
):
    """Create the first administrator for a brand-new installation."""
    # Imported lazily so the module is importable in tests without a live DB.
    from motor.motor_asyncio import AsyncIOMotorClient

    try:
        values = _collect_non_interactive() if non_interactive else _collect_interactive()
    except BootstrapError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        typer.secho(
            "MONGO_URL and DB_NAME must be set to reach the database.",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=2)

    async def _run():
        client = AsyncIOMotorClient(mongo_url)
        try:
            db = client[db_name]
            return await create_first_admin(db, **values)
        finally:
            client.close()

    try:
        result = asyncio.run(_run())
    except BootstrapError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho("First administrator created.", fg=typer.colors.GREEN)
    typer.echo(f"  Organisation : {result['org_name']} ({result['org_id']})")
    typer.echo(f"  Username     : {result['username']}")
    typer.echo(f"  Email        : {result['email']}")
    typer.echo(f"  Role         : {result['role']}")
    typer.echo("You can now log in with the password you just entered.")


if __name__ == "__main__":
    cli()
