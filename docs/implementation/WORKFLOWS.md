# FleetFlow — Protected Workflow Transitions (WF-01)

**Status:** Implemented on `feature/wf-01-workflow-transitions`.
**Scope:** Repository-side only. No production data was accessed.

---

## 1. What was wrong

Generic CRUD could drive operational state directly. Because `status` was
deliberately left out of the TEN-01 protected-field policy (so WF-01 could give
it a real model), a client could:

* `PUT /vehicles/{id}` `{"status": "sold"}` — dispose a vehicle, or worse
  `{"status": "active"}` to **un-dispose** one, rewriting history;
* `PUT /downtime/{id}` `{"status": "open"}` — **reopen** a closed downtime;
* jump a repair ticket straight from `open` to `closed`, skipping approval and
  every stage between;
* re-close a completed trip, **recomputing distance and re-applying the odometer
  bump** from a new `closing_km`.

There was no shared notion of "which state changes are allowed".

## 2. The engine

`backend/workflow.py` — a small set of explicit state graphs plus one validator
every status change goes through. No DB/FastAPI coupling beyond raising
`HTTPException`, so the graphs are unit-testable directly.

* **Explicit graphs.** Every allowed `from → to` is listed; anything else is a
  **409 Conflict**, not a silent write.
* **Terminal states are terminal.** A disposed vehicle, exited driver, closed
  downtime, completed trip or closed ticket cannot transition out.
* **Idempotent.** Transitioning to the current state is a no-op success, so a
  retry cannot error or double-apply a side effect.
* **Role-gated targets.** Entering `sold`/`scrapped` (vehicles) or
  `resigned`/`terminated` (drivers) requires management/admin — enforced in the
  engine, not re-implemented per endpoint.
* **Optimistic concurrency.** `check_version`/`next_version` — a transition
  endpoint may quote an expected `_version`; a mismatch is a 409 so two
  concurrent transitions cannot both win (no double approval/close/reversal).
* **Audited.** Every applied transition writes a `security_audit` event (ids and
  states only).

### 2.1 The state graphs

| Workflow | States | Terminal | Role-gated |
| --- | --- | --- | --- |
| Repairs | open → under_review → approved → sent_for_repair → in_repair → repaired → closed (+ under_review → open rejection) | closed | approved, closed, open(reject): management/admin |
| Vehicles | active/inactive/maintenance/idle interconvert → sold/scrapped | sold, scrapped | sold, scrapped: management/admin |
| Drivers | active/on_leave → resigned/terminated | resigned, terminated | resigned, terminated: management/admin |
| Downtime | open → closed | closed | — |
| Trips | ongoing → completed | completed | — |

The graphs use the **actual** status values the app writes (verified against the
code): trips are `ongoing`/`completed`, minor repairs are created `closed`,
vehicles include `idle`.

### 2.2 How it is enforced

* **Generic updates** (`make_crud` PUT, `update_vehicle`, `update_driver`) call
  `enforce_generic_status_change`, which validates any `status` change against
  the collection's graph **before writing**. A generic update is no longer a way
  around the workflow.
* **Dedicated transition endpoints** — repair advance (`PATCH
  /repairs/{id}/status`) and trip close (`PATCH /trips/{id}/close`) — now run the
  engine, audit the transition, and are idempotent (a completed trip is not
  re-closed; the repair endpoint accepts `expected_version` for concurrency).
* The disposal/exit **side effects** (close downtimes, unassign drivers) are
  unchanged; only the *authorisation and validity* of the transition moved to the
  engine.

## 3. Features with NO genuine workflow (documented, not invented)

Per the WF-01 brief — *"where an existing feature has no genuine workflow,
document that conclusion rather than inventing unnecessary states"* — the
following were assessed and deliberately **not** given state machines:

| Feature | Finding |
| --- | --- |
| **Expenses** | Plain financial records. FleetFlow has **no expense-approval workflow** — no endpoint sets `approval_status`, and the field is protected pre-emptively by TEN-01. Nothing to model. |
| **Payments** | **No payment entity or workflow exists** in the product. `payment_status`/`paid_by` are protected pre-emptively but unused. |
| **Approvals** | The only approval in the system is the repair `approved` state, which is covered by REPAIR_WORKFLOW. There is no generic approval object. |
| **Tyres** | `tyre.status` is a label (active/…); tyre *events* (puncture/rotation/…) are an append-only log, not a state machine. No enforced lifecycle beyond the event records. |
| **FASTag transactions** | No status workflow — demo simulation (FASTAG-01) and manual import are the only write paths; transactions are immutable records. |
| **Odometer** | Not a state machine but a **monotonic invariant**: `current_odometer` only ever increases, enforced by `_update_vehicle_odometer` (trips/fuel take the max). A generic vehicle update setting a lower odometer is a data-quality concern noted below, not a workflow. |

If any of these gains a real approval/payment lifecycle later, it must be added
to `STATUS_WORKFLOWS` with its own graph and dedicated endpoints.

## 4. Verification

`backend/tests/test_workflow_transitions.py` — **35 tests**: engine unit tests
(valid/invalid/terminal/role-gated/idempotent/unknown-state, version checks) and
real-HTTP tests proving a generic update **cannot un-dispose a vehicle** (409),
disposal requires privilege (403, no write), an invalid repair jump is refused
(409), **concurrent repair transitions cannot both win** (409 on the stale one),
a **trip double-close is idempotent** (distance not recomputed), and a downtime
cannot be reopened via generic update.

| Check | Result |
| --- | --- |
| Full backend suite | **601 passed, 3 skipped** (566 pre-WF still green) |
| WF-01 additions | 35 |
| Mutation test | Disabling the transition edge check fails 6 tests, incl. the real-HTTP un-dispose and downtime-reopen |
| Ruff / Gitleaks | Clean |
| Live smoke | admin dispose 200; un-dispose 409 |

## 5. Remaining limitations

* **Odometer monotonicity on generic update.** `_update_vehicle_odometer` keeps
  the odometer monotonic on the trip/fuel paths, but a direct
  `PUT /vehicles/{id}` `{"current_odometer": <lower>}` is still accepted. This is
  a data-quality gap, not a workflow bypass; tightening it (reject a decrease)
  is a small follow-up, left out here to avoid coupling odometer validation into
  the status-transition change.
* **Version fields are opt-in.** Only the repair transition currently issues and
  checks `_version`. The engine supports it everywhere; wiring it into the
  vehicle/driver generic updates would need the frontend to round-trip the
  version, which is a frontend change out of WF-01's backend scope.
* **Reversal/reopen paths** are intentionally absent where the state is terminal
  (disposal, exit) — reversing those is a deliberate, audited administrative
  action that does not exist yet and should not be a silent generic update.
