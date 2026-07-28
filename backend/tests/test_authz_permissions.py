"""
AUTHZ-01 — Action-level permission engine.

Two layers, matching the rest of the programme:

* **Catalogue/mapping unit tests** (fast, no I/O) pin exactly who may do what and
  guard the invariants — no role holds a platform permission, viewer is
  read-only, unknown permissions fail closed, the enforcement roles match
  ``auth.ROLE_EQUIV``.
* **Wiring tests** assert every mutating endpoint actually depends on
  ``require_permission`` rather than a bare role check, so the catalogue is not
  merely decorative.

The end-to-end proof that a denied action returns 403 across the real app — per
role, per endpoint — lives in the TEN-TEST matrix and its RBAC probes, which run
against real HTTP. This file pins the policy those rely on.
"""
import ast
import inspect

import pytest

import auth
from permissions import (
    ALL_PERMISSIONS,
    ENFORCEMENT_ROLES,
    PLATFORM_PERMISSIONS,
    PermissionContext,
    ROLE_PERMISSIONS,
    can_act_on_record,
    has_permission,
    permissions_for,
    within_monetary_limit,
)


# --- Catalogue shape ----------------------------------------------------------

def test_enforcement_roles_match_auth_tiers():
    """A named role with no tier, or a tier with no permission entry, would 403
    every request for that role in production. Catch it here instead."""
    tiers = set(auth.ROLE_EQUIV.values()) | {
        r for r in auth.ROLES if r not in auth.ROLE_EQUIV
    }
    assert tiers == set(ENFORCEMENT_ROLES)
    assert set(ROLE_PERMISSIONS) == set(ENFORCEMENT_ROLES)


def test_every_granted_permission_is_in_the_catalogue():
    for role, perms in ROLE_PERMISSIONS.items():
        unknown = perms - ALL_PERMISSIONS
        assert not unknown, f"{role} holds uncatalogued permissions: {unknown}"


def test_permissions_are_namespaced():
    for p in ALL_PERMISSIONS:
        assert ":" in p, f"permission {p!r} is not resource:action"


# --- Fail closed --------------------------------------------------------------

def test_unknown_role_gets_nothing():
    assert permissions_for("nonsense") == frozenset()
    assert not has_permission("nonsense", "vehicles:create")


def test_unknown_permission_is_never_granted():
    for role in ENFORCEMENT_ROLES:
        assert not has_permission(role, "vehicles:obliterate")


def test_require_permission_rejects_an_uncatalogued_permission():
    """A typo'd permission at a call site must fail loudly at import/wiring time,
    not silently become an always-403 endpoint."""
    with pytest.raises(ValueError):
        auth.require_permission("vehicles:destroy_all")


# --- Platform vs organisation separation --------------------------------------

def test_no_role_holds_a_platform_permission():
    """org_admin is the top of an organisation, not a platform superuser."""
    for role, perms in ROLE_PERMISSIONS.items():
        assert not (perms & PLATFORM_PERMISSIONS), f"{role} holds a platform permission"


def test_platform_and_org_permissions_are_disjoint():
    from permissions import ORG_PERMISSIONS, ALL_RESOURCE_PERMISSIONS
    assert not (PLATFORM_PERMISSIONS & ORG_PERMISSIONS)
    assert not (PLATFORM_PERMISSIONS & ALL_RESOURCE_PERMISSIONS)


# --- Role capability invariants (the security-relevant ones) ------------------

def test_viewer_is_read_only():
    """Viewer must hold no mutating permission at all — this is the AUTHZ-01
    tightening (upload used to be open to everyone)."""
    assert permissions_for("viewer") == frozenset()


def test_driver_can_only_create_the_allowlisted_resources():
    driver = permissions_for("driver")
    creatable = {p for p in driver if p.endswith(":create")}
    assert creatable == {"trips:create", "fuel:create", "repairs:create"}
    # No updates, no deletes, no admin.
    assert not any(p.endswith(":update") or p.endswith(":delete") for p in driver)
    assert "users:manage" not in driver
    assert "roles:assign" not in driver


def test_only_admin_manages_users_and_assigns_roles():
    for role in ENFORCEMENT_ROLES:
        expected = role == "admin"
        assert has_permission(role, "users:manage") == expected
        assert has_permission(role, "roles:assign") == expected


def test_only_admin_deletes_the_admin_only_resources():
    # compliance and branches delete were admin-only pre-AUTHZ-01.
    for role in ENFORCEMENT_ROLES:
        assert has_permission(role, "compliance:delete") == (role == "admin")
        assert has_permission(role, "branches:delete") == (role == "admin")


def test_data_entry_cannot_delete_or_administer():
    de = permissions_for("data_entry")
    assert not any(p.endswith(":delete") for p in de)
    assert "org:update" not in de
    assert "users:manage" not in de


def test_data_entry_cannot_create_compliance_but_can_create_budgets():
    """Preserves the exact pre-AUTHZ-01 asymmetry between these two modules."""
    assert not has_permission("data_entry", "compliance:create")
    assert has_permission("data_entry", "budgets:create")


def test_management_can_delete_budgets_but_not_vehicles():
    assert has_permission("management", "budgets:delete")
    assert not has_permission("management", "vehicles:delete")


def test_admin_holds_every_org_permission():
    from permissions import ORG_PERMISSIONS, ALL_RESOURCE_PERMISSIONS
    admin = permissions_for("admin")
    assert ORG_PERMISSIONS <= admin
    assert ALL_RESOURCE_PERMISSIONS <= admin


# --- Conditional checks -------------------------------------------------------

def _ctx(role="data_entry", org="org-a"):
    return PermissionContext(role=role, user_id="u1", org_id=org)


def test_cross_tenant_record_is_never_actionable():
    assert can_act_on_record(_ctx(org="org-a"), {"org_id": "org-a"})
    assert not can_act_on_record(_ctx(org="org-a"), {"org_id": "org-b"})


def test_record_without_owner_is_actionable():
    """Legacy/global records with no org_id are not treated as foreign."""
    assert can_act_on_record(_ctx(), {"id": "x"})


def test_missing_record_is_not_actionable():
    assert not can_act_on_record(_ctx(), None)


@pytest.mark.parametrize("amount,ok", [
    (100, True), (5000, True), (5000.0, True), (5001, False), (10000, False),
])
def test_monetary_limit_enforced(amount, ok):
    limits = {"data_entry": 5000}
    assert within_monetary_limit("data_entry", amount, limits) == ok


def test_no_limit_means_unlimited():
    assert within_monetary_limit("admin", 10**9, {"data_entry": 5000})


@pytest.mark.parametrize("bad", ["not-a-number", None, -1, float("nan")])
def test_malformed_amount_fails_closed(bad):
    assert not within_monetary_limit("data_entry", bad, {"data_entry": 5000})


# --- Wiring: endpoints must enforce, not decorate -----------------------------

_ROUTE_MODULES = [
    "routes_core", "routes_ops", "routes_assets", "routes_vendors",
    "routes_calendar", "routes_compliance", "routes_expenses", "routes_orgs",
    "routes_settlement", "routes_exceptions", "helpers", "auth",
]


def _mutating_endpoints_without_permission():
    """Yield (module, function) for every POST/PUT/PATCH/DELETE handler whose
    dependencies do not include require_permission.

    A handful are legitimately exempt (see EXEMPT): unauthenticated flows and the
    session-scoped self-service endpoints that use require_user with their own
    ownership checks.
    """
    import importlib

    EXEMPT = {
        # Unauthenticated by design.
        "login", "logout", "register_org", "enter_demo",
        # Self-service, guarded by require_user + own-session ownership.
        "change_password", "revoke_session", "revoke_all_sessions",
        "dismiss_checklist",
    }
    offenders = []
    for modname in _ROUTE_MODULES + ["routes_assets"]:
        mod = importlib.import_module(modname)
        src = inspect.getsource(mod)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            deco_src = " ".join(
                ast.get_source_segment(src, d) or "" for d in node.decorator_list
            )
            if not any(m in deco_src for m in (".post(", ".put(", ".patch(", ".delete(")):
                continue
            if node.name in EXEMPT:
                continue
            func_src = ast.get_source_segment(src, node) or ""
            # Look at the signature line(s) up to the body.
            header = func_src.split("):", 1)[0]
            if "require_permission" not in header:
                offenders.append(f"{modname}.{node.name}")
    return offenders


def test_every_mutating_endpoint_enforces_a_permission():
    offenders = _mutating_endpoints_without_permission()
    assert not offenders, (
        "Mutating endpoints not guarded by require_permission (add the guard, or "
        f"add to EXEMPT with a reason): {offenders}"
    )


def test_make_crud_uses_permission_dependencies():
    src = inspect.getsource(__import__("helpers").make_crud)
    assert 'require_permission(f"{perm}:create")' in src
    assert 'require_permission(f"{perm}:update")' in src
    assert 'require_permission(f"{perm}:delete")' in src
    # The old bare role/viewer checks must be gone.
    assert 'user["role"] == "viewer"' not in src


# --- Audit --------------------------------------------------------------------

def test_role_change_is_audited():
    src = inspect.getsource(auth.update_user)
    assert "record_security_event" in src
    assert "revoke_user_sessions" in src


def test_user_create_is_audited_and_role_gated():
    src = inspect.getsource(auth.create_user)
    assert "record_security_event" in src
    assert 'has_permission(user.get("role"), "roles:assign")' in src


def test_security_event_records_no_secrets():
    """The audit writer must not persist password/hash/token fields.

    Inspects the code body only — the docstring legitimately *names* those fields
    to say it excludes them, so a raw substring check would false-positive."""
    fn = ast.parse(inspect.getsource(auth.record_security_event)).body[0]
    body = fn.body[1:] if (fn.body and isinstance(fn.body[0], ast.Expr)
                           and isinstance(fn.body[0].value, ast.Constant)) else fn.body
    code = "\n".join(ast.get_source_segment(inspect.getsource(auth.record_security_event), n)
                     or "" for n in body)
    for banned in ("password", "hash", "token", "csrf"):
        assert banned not in code.lower(), f"audit writer references {banned!r}"
