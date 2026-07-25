"""
WF-01 — Protected workflow transitions.

Generic CRUD let a client drive operational state directly: `PUT /vehicles/{id}`
with `{"status": "sold"}` disposed a vehicle without the disposal side effects
running through the intended path, `PUT /downtime/{id}` could flip a downtime
closed→open, and nothing stopped a status jumping straight from `open` to
`closed` skipping the states between. Status was deliberately left out of the
TEN-01 protected-field policy precisely so WF-01 could give it a real model.

This module is the shared transition engine: a small set of explicit state graphs
plus one validator every status change goes through. It has no DB/FastAPI
coupling beyond raising `HTTPException`, so the graphs are unit-testable directly.

Design rules
------------
* **Explicit graphs, no free transitions.** Every allowed `from → to` is listed.
  Anything not listed is a 409 Conflict, not a silent write.
* **Terminal states are terminal.** A disposed vehicle or an exited driver cannot
  transition back — that would rewrite history and corrupt reporting.
* **Idempotent.** Transitioning to the current state is a no-op success, so a
  retried request cannot error or double-apply a side effect.
* **Optimistic concurrency where it matters.** Transition endpoints may pass an
  expected version; a mismatch is a 409 so two concurrent transitions cannot both
  win (no double approval / double close).
* **Audited.** Every applied transition is recorded (ids + states only).

Features with **no genuine workflow** are documented in WORKFLOWS.md rather than
given invented states: FleetFlow has no expense-approval, payment or generic
approval workflow, and tyre/FASTag `status` is a label, not a state machine.
"""
from fastapi import HTTPException


class Workflow:
    """An explicit state machine for one collection's ``status`` field.

    ``transitions`` maps each state to the states reachable from it. ``roles``
    optionally restricts *entering* a state to certain effective roles (checked
    by the caller, which knows the user). ``initial`` documents the state a fresh
    record starts in.
    """

    def __init__(self, name, transitions, *, initial, roles=None):
        self.name = name
        self.transitions = {k: tuple(v) for k, v in transitions.items()}
        self.initial = initial
        self.roles = roles or {}
        self.states = set(transitions) | {s for v in transitions.values() for s in v}

    def is_terminal(self, state):
        return not self.transitions.get(state)

    def can_transition(self, current, target):
        return target in self.transitions.get(current, ())

    def required_roles(self, target):
        return self.roles.get(target)


# --- Definitions --------------------------------------------------------------

# Repair tickets — mirrors the pre-WF-01 TICKET_FLOW exactly, now expressed
# through the engine. under_review → open is the rejection path.
REPAIR_WORKFLOW = Workflow(
    "repairs",
    {
        "open": ["under_review"],
        "under_review": ["approved", "open"],
        "approved": ["sent_for_repair"],
        "sent_for_repair": ["in_repair"],
        "in_repair": ["repaired"],
        "repaired": ["closed"],
        "closed": [],
    },
    initial="open",
    roles={
        "approved": ("management", "admin"),
        "closed": ("management", "admin"),
        "open": ("management", "admin"),   # rejection back to open
    },
)

# Vehicle lifecycle. The operational states interconvert freely; disposal
# (sold/scrapped) is management/admin only and TERMINAL — a vehicle cannot be
# un-disposed, which previously a generic update could do. The operational set is
# derived from the status values the app actually uses.
_VEHICLE_OPERATIONAL = ("active", "inactive", "maintenance", "idle")
_VEHICLE_DISPOSED = ("sold", "scrapped")
VEHICLE_STATUS_WORKFLOW = Workflow(
    "vehicles",
    {
        **{s: [o for o in _VEHICLE_OPERATIONAL if o != s] + list(_VEHICLE_DISPOSED)
           for s in _VEHICLE_OPERATIONAL},
        **{s: [] for s in _VEHICLE_DISPOSED},
    },
    initial="active",
    roles={
        "sold": ("management", "admin"),
        "scrapped": ("management", "admin"),
    },
)

# Driver lifecycle. Exit (resigned/terminated) is terminal.
DRIVER_STATUS_WORKFLOW = Workflow(
    "drivers",
    {
        "active": ["on_leave", "resigned", "terminated"],
        "on_leave": ["active", "resigned", "terminated"],
        "resigned": [],
        "terminated": [],
    },
    initial="active",
    roles={
        "resigned": ("management", "admin"),
        "terminated": ("management", "admin"),
    },
)

# Downtime. Opens on creation; closing is terminal for the record's lifecycle.
DOWNTIME_STATUS_WORKFLOW = Workflow(
    "downtimes",
    {
        "open": ["closed"],
        "closed": [],
    },
    initial="open",
)

# Trips (OPS-01). The full operational lifecycle:
#
#   planned → assigned → ongoing(dispatched) → completed → settlement_pending → closed
#
# plus cancellation from any pre-completion state. The legacy quick-entry path
# (POST /trips with a closing_km) still lands a trip directly in "completed" and
# the ongoing→completed hop is still what PATCH /trips/{id}/close performs, so
# every pre-OPS-01 trip and test keeps working; the earlier states and the
# terminal "closed"/"cancelled" states are additive.
#
# Terminal states (closed, cancelled) cannot transition out. completed is *not*
# terminal any more — it advances to settlement/closure — but PATCH .../close
# stays idempotent on an already-completed trip (it performs ongoing→completed
# only), so the WF-01 double-close guarantee is unchanged; final closure is the
# separate PATCH .../finalize action.
_TRIP_ACTIVE_ALLOCATION = ("assigned", "ongoing")
TRIP_STATUS_WORKFLOW = Workflow(
    "trips",
    {
        "planned": ["assigned", "cancelled"],
        "assigned": ["ongoing", "planned", "cancelled"],
        "ongoing": ["completed", "cancelled"],
        "completed": ["settlement_pending", "closed"],
        "settlement_pending": ["closed"],
        "closed": [],
        "cancelled": [],
    },
    initial="planned",
)

# Collections whose ``status`` may only ever be changed through a dedicated
# workflow action, never a generic PUT. For trips a generic status write would
# skip the allocation/odometer/audit side effects the dedicated endpoints carry
# (assign, dispatch, complete/close, cancel), so it is refused outright — a
# generic update must not be a bypass. A no-op (same status) is still allowed.
DEDICATED_ONLY_STATUS = {"trips"}

# Collections whose ``status`` is workflow-controlled. A generic update that
# tries to change status on one of these is routed through validate_transition
# rather than written blindly. Everything else may set status freely (it is a
# plain label — see WORKFLOWS.md).
STATUS_WORKFLOWS = {
    "vehicles": VEHICLE_STATUS_WORKFLOW,
    "drivers": DRIVER_STATUS_WORKFLOW,
    "downtimes": DOWNTIME_STATUS_WORKFLOW,
    "trips": TRIP_STATUS_WORKFLOW,
    "repairs": REPAIR_WORKFLOW,
}


# --- Validation ---------------------------------------------------------------

def validate_transition(workflow: Workflow, current, target, *, role=None):
    """Validate a status change. Returns "noop" | "ok", or raises.

    * current == target → "noop" (idempotent; the caller skips side effects).
    * disallowed edge → 409 Conflict, naming both states, no write.
    * an unknown target state → 400.
    * a role-restricted target the role may not enter → 403.
    """
    current = current or workflow.initial
    if target == current:
        return "noop"
    if target not in workflow.states:
        raise HTTPException(status_code=400, detail=f"Unknown {workflow.name} status: {target!r}")
    if not workflow.can_transition(current, target):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot change {workflow.name} status from {current!r} to {target!r}",
        )
    needed = workflow.required_roles(target)
    if needed and role not in needed:
        raise HTTPException(
            status_code=403,
            detail=f"Changing {workflow.name} status to {target!r} requires {' or '.join(needed)}",
        )
    return "ok"


def check_version(existing: dict, expected_version):
    """Optimistic-concurrency guard for a transition.

    If the caller supplied an expected version and it does not match the record's
    current ``_version``, another transition has run in between — 409, so the two
    cannot both apply (no double approval/close/reversal). No expectation supplied
    means the caller opted out of the check.
    """
    if expected_version is None:
        return
    current = existing.get("_version", 0)
    if int(expected_version) != int(current):
        raise HTTPException(
            status_code=409,
            detail="This record changed since you loaded it. Reload and retry.",
        )


def next_version(existing: dict) -> int:
    return int(existing.get("_version", 0)) + 1


def enforce_generic_status_change(collection: str, existing: dict, payload: dict, *, role=None):
    """Guard a status change coming through a *generic* update endpoint.

    For a workflow-controlled collection, a status change in a generic PUT must
    still satisfy the state graph — a generic update must not be a way around the
    workflow. Returns True if status is actually transitioning (so the caller can
    bump the version / audit), False if unchanged or not workflow-controlled.
    Raises on an invalid transition.
    """
    if "status" not in payload:
        return False
    wf = STATUS_WORKFLOWS.get(collection)
    if wf is None:
        return False
    current = (existing or {}).get("status") or wf.initial
    target = payload["status"]
    if collection in DEDICATED_ONLY_STATUS and target != current:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{wf.name} status is driven by dedicated actions, not a generic "
                "update. Use the assign / dispatch / close / cancel endpoints."
            ),
        )
    result = validate_transition(wf, current, target, role=role)
    return result == "ok"
