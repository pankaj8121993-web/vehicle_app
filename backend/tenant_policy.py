"""
TEN-01 — Canonical tenant-ownership and mass-assignment policy.

Before TEN-01 each generic update endpoint carried its own hand-written denylist
(``k not in ("id", "_id", "created_at", "created_by", "is_test_data")``). Those
lists were duplicated in six places and every one of them omitted ``org_id``, so
a client could transfer a record into another organisation by sending
``{"org_id": "<victim-org>"}`` to a normal update endpoint. This module replaces
those scattered lists with one policy that the routes and the database layer
both consult.

Design rules
------------
* **Server-derived ownership.** ``org_id`` is never accepted from a request body.
  It comes from ``database.current_org_id``, which ``auth.require_user`` sets
  from the authenticated session. See :mod:`database` for enforcement.
* **Reject, never silently drop.** Supplying a protected field is a client bug or
  an attack; either way the caller is told, rather than being led to believe the
  write succeeded as sent. Errors name the rejected *fields*, never their values.
* **Fail closed.** Anything not known to be safely client-writable on a generic
  endpoint is protected. Legitimately editable fields keep their explicit,
  permission-checked paths (e.g. role changes via ``auth.update_user``, ticket
  status via ``routes_ops.advance_repair``).

This module deliberately has no imports from :mod:`database`, so the database
layer can import these constants without a cycle.
"""
from fastapi import HTTPException

# --- Field groups -------------------------------------------------------------

# Tenant ownership. Never client-writable on any endpoint, generic or dedicated.
# ``organization_id`` / ``tenant_id`` are not used by the current schema; they are
# listed so that a future rename cannot silently open a hole.
TENANT_OWNERSHIP_FIELDS = frozenset({
    "org_id", "organization_id", "tenant_id",
})

# Record identity. Changing these on an update re-points or duplicates a record.
IDENTITY_FIELDS = frozenset({
    "id", "_id",
})

# Audit provenance. Server-written only, so history cannot be forged.
AUDIT_FIELDS = frozenset({
    "created_at", "created_by",
    "updated_at", "updated_by",
    "deleted_at", "deleted_by",
    "archived_at", "archived_by",
})

# Security posture. Escalation vectors — only ever set through the explicit,
# permission-checked user-administration path.
SECURITY_FIELDS = frozenset({
    "role", "roles", "permissions",
    "is_admin", "is_super_admin", "is_platform_admin",
    "password", "password_hash", "must_change_password",
})

# Demo and test markers. A client that could set these could either escape demo
# isolation or, via ``is_test_data``, hide records from the default listings.
ISOLATION_MARKER_FIELDS = frozenset({
    "is_demo", "is_test_data",
})

# Branch scope. FleetFlow stores branches but does not yet scope records to them
# (no collection carries ``branch_id`` today). It is protected pre-emptively so
# that when branch scoping lands it cannot be assigned from a request body.
BRANCH_SCOPE_FIELDS = frozenset({
    "branch_id",
})

# Optimistic-locking version. Server-incremented; a client-chosen value would
# defeat the lost-update check.
VERSION_FIELDS = frozenset({
    "_version",
})

# Workflow, approval and payment state that must move through dedicated action
# endpoints rather than a generic update body.
#
# Scope note: TEN-01 protects these fields on the *generic* update paths only.
# Building the full transition model — allowed state graphs, rejection and
# reversal paths, atomic side effects — is WF-01. ``status`` is deliberately
# absent here: several modules still use plain ``status`` as an ordinary editable
# field (e.g. vehicle active/inactive) and removing it from generic updates is a
# WF-01 decision that needs its own transition endpoints first.
WORKFLOW_FIELDS = frozenset({
    "approval_status", "approved_by", "approved_at",
    "rejection_reason", "rejected_by", "rejected_at",
    "payment_status", "paid_by", "paid_at",
    "ticket_number",
})

# System-calculated values. Derived server-side from other records; a client
# value would silently corrupt finance and reporting.
DERIVED_FIELDS = frozenset({
    "total", "totals", "balance", "computed_total",
})

# The full set rejected on generic create/update request bodies.
PROTECTED_FIELDS = frozenset().union(
    TENANT_OWNERSHIP_FIELDS,
    IDENTITY_FIELDS,
    AUDIT_FIELDS,
    SECURITY_FIELDS,
    ISOLATION_MARKER_FIELDS,
    BRANCH_SCOPE_FIELDS,
    VERSION_FIELDS,
    WORKFLOW_FIELDS,
    DERIVED_FIELDS,
)


class TenantViolation(Exception):
    """Raised by the database layer when a write would breach tenant ownership.

    This is a programming-error guard of last resort, not a user-facing error:
    routes reject protected fields long before the database layer sees them.
    Never carries field values.
    """


def protected_fields_in(payload, *, allow=frozenset()):
    """Return the sorted protected field names present in ``payload``.

    ``allow`` exempts fields that the calling endpoint legitimately owns (for
    example the user-administration endpoint, which may set ``role``).
    """
    if not isinstance(payload, dict):
        return []
    return sorted((set(payload) & PROTECTED_FIELDS) - set(allow))


def reject_protected_fields(payload, *, allow=frozenset()):
    """Raise HTTP 400 if ``payload`` carries protected fields.

    The message names the rejected fields so an honest client can fix its
    request, and never echoes the submitted values.
    """
    found = protected_fields_in(payload, allow=allow)
    if found:
        raise HTTPException(
            status_code=400,
            detail=(
                "These fields are set by the server and cannot be supplied in a "
                f"request body: {', '.join(found)}. "
                "Organisation ownership is derived from your session; role, "
                "approval, payment and audit fields have dedicated endpoints."
            ),
        )
    return payload


# --- Update-document inspection (database layer) ------------------------------

# Mongo update operators that write field values. ``$setOnInsert`` counts: on an
# upsert it would set ownership on the newly created document.
_FIELD_WRITING_OPERATORS = (
    "$set", "$setOnInsert", "$unset", "$inc", "$mul", "$min", "$max",
    "$rename", "$push", "$pull", "$addToSet", "$pop", "$pullAll", "$bit",
    "$currentDate",
)


def ownership_fields_in_update(update):
    """Return tenant-ownership field names an update document would write.

    Handles both operator documents (``{"$set": {...}}``) and, defensively, a
    plain replacement document. Dotted paths (``"org_id.x"``) are matched on
    their root so a nested write cannot slip through.
    """
    if not isinstance(update, dict):
        return []
    found = set()

    def _scan(mapping):
        for key in mapping:
            root = str(key).split(".", 1)[0]
            if root in TENANT_OWNERSHIP_FIELDS:
                found.add(root)

    has_operator = any(k.startswith("$") for k in update)
    if has_operator:
        for op in _FIELD_WRITING_OPERATORS:
            section = update.get(op)
            if isinstance(section, dict):
                _scan(section)
    else:
        # Replacement document — every top-level key is written.
        _scan(update)
    return sorted(found)
