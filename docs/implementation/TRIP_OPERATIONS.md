# FleetFlow — Trip, Dispatch and Allocation Lifecycle (OPS-01)

**Status:** Implemented on `feature/ops-01-trip-lifecycle`.
**Scope:** Repository-side only. No production data was accessed.

---

## 1. What was missing

Before OPS-01 a trip had exactly two operational states — `ongoing` and
`completed` — set directly by the create path (`on_trip_create`) or the
dedicated close endpoint. There was:

* no *planning* state (a trip could not exist before its vehicle/driver were
  chosen);
* no *allocation* step, and therefore no prevention of the **same vehicle or
  driver being actively booked on two trips at once**;
* no dispatch gate — an in-service check existed at create time (DI-01) but
  **open downtime did not block putting a vehicle on the road**;
* no reassignment path with authority/audit;
* no cancellation path (a mistaken trip could only be deleted, losing history);
* and a **generic `PUT /trips/{id}` could still set `status`** to any value the
  state graph allowed, skipping the distance/odometer/audit side effects.

## 2. The lifecycle

```
planned ─▶ assigned ─▶ ongoing (dispatched) ─▶ completed ─▶ settlement_pending ─▶ closed
   │           │            │
   └───────────┴────────────┴────────────────▶ cancelled
```

Modelled in `workflow.TRIP_STATUS_WORKFLOW` (the single WF-01 engine). `closed`
and `cancelled` are **terminal**. `completed` is no longer terminal — it
advances to settlement/closure — but the WF-01 double-close guarantee is
unchanged because `PATCH /trips/{id}/close` only ever performs the
`ongoing → completed` hop and is idempotent on an already-completed trip.

**Backward compatibility.** The legacy quick full-entry path (`POST /trips`
with a `closing_km`) still lands a trip directly in `ongoing`/`completed`, so
every pre-OPS-01 client, test and reconciliation figure is unaffected. The
earlier states and the terminal states are strictly additive.

## 3. Dedicated actions

| Action | Endpoint | Transition | Notes |
| --- | --- | --- | --- |
| Plan | `POST /trips/plan` | → planned | vehicle/driver/opening_km all optional; idempotency-key aware |
| Assign vehicle/driver | `PATCH /trips/{id}/assign` | planned/assigned → assigned | same-org + in-service refs; allocation-conflict check; CAS |
| Reassign | `PATCH /trips/{id}/reassign` | (state unchanged) | before dispatch: any acting role; after dispatch (ongoing): **management/admin + reason** |
| Dispatch | `PATCH /trips/{id}/dispatch` | assigned → ongoing | requires vehicle **and** driver; **blocked by open downtime**; conflict re-check; CAS |
| Confirm reach / completion | `PATCH /trips/{id}/close` | ongoing → completed | records closing_km, computes distance, forwards odometer; idempotent (WF-01) |
| Close out | `PATCH /trips/{id}/finalize` | completed/settlement_pending → closed | terminal; releases allocation; idempotent |
| Cancel | `PATCH /trips/{id}/cancel` | planned/assigned/ongoing → cancelled | preserves history; releases allocation; idempotent |

*Settlement.* `completed → settlement_pending` is defined in the graph and
consumed by OPS-02 (Expenses & Settlement); `finalize` accepts either
`completed` or `settlement_pending`.

## 4. Controls enforced

* **Tenant + in-service.** Every assign/reassign runs `references.validate_references`
  against the tenant-scoped `db`, so a cross-tenant vehicle/driver simply does
  not resolve (400), and a disposed vehicle / exited driver is refused.
* **Allocation conflict.** A vehicle or driver already on a trip in
  `assigned`/`ongoing` cannot be allocated to another (`409`). Completing,
  cancelling or closing a trip releases the resource (it leaves the active set).
* **Downtime gate.** Dispatch is refused (`409`) while the vehicle has any open
  downtime.
* **Reassignment authority.** Reassigning a *dispatched* trip requires
  management/admin and a reason; both are audited (`detail.post_dispatch`).
* **Idempotency & concurrency.** Plan supports `Idempotency-Key`. Every
  transition uses `atomicity.swap_status` (compare-and-swap on the loaded
  status) and honours an optional `expected_version`, so two concurrent
  assign/dispatch/complete/close/cancel calls cannot both apply.
* **No generic bypass.** `trips` is in `workflow.DEDICATED_ONLY_STATUS`; a
  `status` change through the generic `PUT /trips/{id}` is refused (`409`) — the
  dedicated actions are the only path.
* **Audit.** `trip.plan`, `trip.assign`, `trip.reassign`, `trip.dispatch`,
  `trip.close`, `trip.finalize`, `trip.cancel` are written to `security_audit`
  (ids/states only).
* **DI scanner.** `check_data_integrity._VALID_STATUSES["trips"]` now recognises
  every lifecycle state, so valid records are not flagged `invalid_status`.

## 5. Permissions

The lifecycle transition actions reuse the existing acting permission
`trips:close` (held by admin/management/data_entry/test/driver-less viewer is
excluded); planning uses `trips:create`. Post-dispatch reassignment additionally
requires the `management`/`admin` role inside the endpoint. No new catalogue
entries were needed, so the AUTHZ-01 matrix is unchanged.

## 6. Frontend

`TripsPage` gains lifecycle status tabs (Planned/Assigned/Ongoing/Completed/
Closed/Cancelled) and per-row dedicated-action buttons — Dispatch (assigned),
Complete (ongoing), Close out (completed), Cancel (pre-completion). Every button
calls a dedicated endpoint; there are no generic status writes in the UI. The
`CloseTripAction` export is retained as an alias so the Vehicle/Driver profile
screens pick up the richer actions without change.

## 7. Verification

`backend/tests/test_trip_operations.py` — **22 real-HTTP tests**: valid
same-tenant allocation; cross-tenant vehicle/driver rejection; disposed-vehicle
and exited-driver rejection; double-allocation prevention; concurrent assign
(exactly one wins); reassignment before dispatch, and after dispatch requiring
authority + reason; dispatch blocked by downtime; dispatch requires prior
assignment; double dispatch / double completion / double finalize idempotent;
cancellation releases the vehicle & driver; cancel/finalize refused out of
order; generic status write rejected; viewer cannot drive the lifecycle; and the
legacy quick-create path unchanged.

| Check | Result |
| --- | --- |
| Full backend suite | **735 passed, 3 skipped** (712 pre-OPS-01 still green) |
| OPS-01 additions | 22 |
| WF-01 trip tests | updated for the new terminal states / initial |
| Mutation test | Neutralising the allocation-conflict check fails `test_double_allocation_prevented` |
| Ruff (changed files) | F/E clean |
| Gitleaks | No leaks |
| Frontend build | Succeeds |

## 8. Remaining limitations (non-blocking)

* **Cross-trip simultaneous grab.** The allocation-conflict check plus per-trip
  compare-and-swap prevents the sequential double-booking and the same-trip
  concurrent race. A truly *simultaneous* assign of one vehicle to **two
  different** planned trips is a narrow TOCTOU window not fully closed on a
  standalone MongoDB (no cross-document transaction, and `$in` cannot be used in
  a partial-unique-index filter). Documented for a later allocation-index
  follow-up; the common cases are covered.
* **Assign/reassign UI.** The frontend exposes dispatch/complete/close/cancel as
  one-click actions; choosing a *different* vehicle/driver (full plan→assign UI
  with dropdowns) is done through the create form today and left as a small
  follow-up. The plan/assign/reassign **APIs** are complete and tested.
