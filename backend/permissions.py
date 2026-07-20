"""
AUTHZ-01 — Canonical action-level permission catalogue and enforcement policy.

Before AUTHZ-01, authorisation was a scatter of role-tier checks: each endpoint
carried its own ``require_role("data_entry", "management", "admin", "test")`` (or
similar), the generic CRUD helper hard-coded ``if user["role"] == "viewer"``, and
the allowed roles for the *same conceptual action* differed subtly between
modules with nothing central to compare them against. Adding an endpoint meant
copying a role list and hoping it matched intent.

This module makes the model explicit: a fixed catalogue of **action** permissions
(``vehicles:create``, ``users:manage``, …), an explicit map from each enforcement
role to the permissions it holds, and helpers the routes call. Frontend
visibility is never the control — every mutating endpoint checks a permission
here.

Design rules
------------
* **Actions, not roles, at the call site.** A route asks for
  ``require_permission("vehicles:delete")``, not for a role list. What a role can
  do lives here and nowhere else.
* **Enforce on the *effective* role.** ``auth.ROLE_EQUIV`` collapses the eight
  named roles onto six enforcement tiers; permissions are keyed by tier, so a new
  named role only needs a tier mapping, not a sweep of every endpoint.
* **Fail closed.** An unknown permission, or a role with no entry, grants nothing.
* **Platform vs organisation.** Platform permissions are defined separately and
  held by no current role — FleetFlow has no platform-owner console yet
  (PLATFORM-01). ``org_admin`` is the top of an *organisation*, not a platform
  superuser, and cannot act across organisations (proven by the TEN-TEST matrix).
* **Preserve today's behaviour exactly.** The role→permission map is derived from
  the guards that existed before AUTHZ-01, so this is a refactor of *where* the
  rules live, not a change to who-can-do-what — with two deliberate, documented
  tightenings (see ``DELIBERATE_TIGHTENINGS``).
"""
from dataclasses import dataclass


# --- Enforcement roles (effective tiers) --------------------------------------

# The six tiers auth.ROLE_EQUIV collapses every named role onto. Kept here as the
# authoritative list so a mismatch with auth is caught by a test rather than by a
# production 403.
ENFORCEMENT_ROLES = ("admin", "management", "data_entry", "driver", "viewer", "test")


# --- Resource action permissions ----------------------------------------------

# Tenant resources managed through the generic CRUD helper or an equivalent
# create/update/delete surface. Each yields ``<name>:create/update/delete``.
CRUD_RESOURCES = (
    "vehicles", "drivers", "documents", "trips", "fuel", "services",
    "greasings", "repairs", "tyres", "tyre_events", "accidents", "fastag",
    "downtime", "expenses", "vendors", "calendar", "compliance", "budgets",
)

# Resources drivers may create (breakdown/field reporting from a phone). Drivers
# get *only* create on these and nothing else.
DRIVER_CREATABLE = ("trips", "fuel", "repairs")

# Administrative / organisation-level actions.
ORG_PERMISSIONS = frozenset({
    "branches:create", "branches:update", "branches:delete",
    "org:update",
    "users:manage",          # create / deactivate / delete / reset users
    "roles:assign",          # change a user's role — escalation-sensitive
    "files:upload",
    "trips:close",           # dedicated trip-close action (WF-01 refines)
    "repairs:transition",    # dedicated repair status action (WF-01 refines)
    "fastag:simulate",       # demo FASTag simulation (FASTAG-01 refines)
    "testdata:purge",        # wipe is_test_data records
})

# Platform-owner actions. Defined for separation; held by NO current role.
PLATFORM_PERMISSIONS = frozenset({
    "platform:manage_orgs",
    "platform:impersonate",
    "platform:manage_billing",
})


def _crud(resource):
    return {f"{resource}:create", f"{resource}:update", f"{resource}:delete"}


ALL_RESOURCE_PERMISSIONS = frozenset(
    p for r in CRUD_RESOURCES for p in _crud(r)
)

ALL_PERMISSIONS = ALL_RESOURCE_PERMISSIONS | ORG_PERMISSIONS | PLATFORM_PERMISSIONS


# --- Role → permission map ----------------------------------------------------
#
# Built to reproduce the pre-AUTHZ-01 guards exactly. The comments record the
# guard each grant descends from, so the mapping stays auditable.

def _build_role_permissions():
    grants = {r: set() for r in ENFORCEMENT_ROLES}

    def grant(permission, *roles):
        for r in roles:
            grants[r].add(permission)

    for r in CRUD_RESOURCES:
        # Each grant records the pre-AUTHZ-01 guard it descends from, so the map
        # stays auditable against the old behaviour.
        if r == "compliance":
            # create/update require_role(management, admin); delete admin-only.
            grant(f"{r}:create", "management", "admin")
            grant(f"{r}:update", "management", "admin")
            grant(f"{r}:delete", "admin")
        elif r == "budgets":
            # create/update require_role(management, admin, data_entry) — NOT
            # test; delete require_role(management, admin).
            grant(f"{r}:create", "management", "admin", "data_entry")
            grant(f"{r}:update", "management", "admin", "data_entry")
            grant(f"{r}:delete", "management", "admin")
        else:
            # create: make_crud blocked only viewer and non-allowlisted drivers.
            grant(f"{r}:create", "data_entry", "management", "admin", "test")
            # update: require_role(data_entry, management, admin, test).
            grant(f"{r}:update", "data_entry", "management", "admin", "test")
            # delete: require_role(admin, test).
            grant(f"{r}:delete", "admin", "test")

    # Drivers: create only, and only the allowlisted resources.
    for r in DRIVER_CREATABLE:
        grant(f"{r}:create", "driver")

    # Organisation-level.
    grant("branches:create", "admin", "management")   # require_role(admin, management)
    grant("branches:update", "admin", "management")
    grant("org:update", "admin", "management")
    grant("branches:delete", "admin")                 # require_role(admin)
    grant("users:manage", "admin")                    # user admin was admin-only
    grant("roles:assign", "admin")
    grant("testdata:purge", "admin")                  # purge-test-data was admin-only

    admin = grants["admin"]
    management = grants["management"]
    data_entry = grants["data_entry"]
    driver = grants["driver"]
    viewer = grants["viewer"]      # read-only: holds no mutating permission
    test = grants["test"]

    # files:upload was require_user (any authenticated). Deliberately NOT granted
    # to viewer — see DELIBERATE_TIGHTENINGS.
    for role in (admin, management, data_entry, driver, test):
        role.add("files:upload")

    # trips:close and repairs:transition were require_user. Granted to every
    # acting role except viewer (an auditor closing a trip was never intended);
    # the per-status escalation checks inside advance_repair still apply on top.
    for role in (admin, management, data_entry, driver, test):
        role.update({"trips:close", "repairs:transition"})

    # fastag:simulate was require_user. FASTAG-01 will fail it closed outside the
    # demo org; here it keeps its current reach minus viewer.
    for role in (admin, management, data_entry, driver, test):
        role.add("fastag:simulate")

    return {
        "admin": frozenset(admin),
        "management": frozenset(management),
        "data_entry": frozenset(data_entry),
        "driver": frozenset(driver),
        "viewer": frozenset(viewer),
        "test": frozenset(test),
    }


ROLE_PERMISSIONS = _build_role_permissions()

# Two intentional differences from the pre-AUTHZ-01 behaviour, called out so a
# reviewer sees them as decisions rather than accidents:
DELIBERATE_TIGHTENINGS = {
    "files:upload": (
        "Upload was require_user, so a read-only viewer could store files. "
        "Viewers are now truly read-only."
    ),
    "trips:close+repairs:transition": (
        "Trip close and repair advance were require_user, so a viewer could "
        "drive a workflow. Now restricted to acting roles; WF-01 refines further."
    ),
}


# --- Query API ----------------------------------------------------------------

def permissions_for(role: str) -> frozenset:
    """Permissions held by an effective role. Unknown role → nothing (fail closed)."""
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: str, permission: str) -> bool:
    return permission in permissions_for(role)


# --- Conditional (record-scoped) checks ---------------------------------------
#
# Base permission answers "may this role ever do X". Conditions answer "may they
# do it to *this* record" — ownership, record state, monetary ceilings. Kept as
# small pure predicates so routes and tests share one definition.

@dataclass(frozen=True)
class PermissionContext:
    """Everything a conditional check needs, with no request/db coupling."""
    role: str
    user_id: str
    org_id: str
    is_demo: bool = False


def can_act_on_record(ctx: PermissionContext, record: dict) -> bool:
    """Cross-tenant guard at the authorisation layer (defence in depth).

    TenantCollection already scopes queries, so a route normally never sees
    another org's record. This is the belt-and-braces check for any path that
    reaches a record by an unscoped read: a record from another organisation is
    never actionable, regardless of permission.
    """
    if record is None:
        return False
    owner = record.get("org_id")
    return owner is None or owner == ctx.org_id


def within_monetary_limit(role: str, amount, limits: dict) -> bool:
    """True if ``amount`` is within ``role``'s ceiling for an action.

    ``limits`` maps role → maximum (None or missing = no ceiling). Non-numeric or
    negative amounts fail closed so a malformed value cannot slip past a limit.
    """
    ceiling = limits.get(role) if limits else None
    if ceiling is None:
        return True
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return False
    if value < 0:
        return False
    return value <= ceiling
