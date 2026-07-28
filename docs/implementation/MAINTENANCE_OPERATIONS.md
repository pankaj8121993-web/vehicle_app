# FleetFlow — Maintenance Operations (OPS-03)

**Status:** Implemented on `feature/ops-03-maintenance`.
**Scope:** Repository-side only. No production data was accessed.

---

## 1. Starting point

Much of the maintenance surface already existed: the repair ticket state machine
(`workflow.REPAIR_WORKFLOW` + `advance_repair`, with role-gated approval,
idempotency, compare-and-swap and audit), tyre records with an append-only event
log, and open/closed downtime under WF-01. OPS-03 **connects** these into one
operational flow and closes the specific gaps.

## 2. Repair ⇄ downtime ⇄ vehicle availability

* **Entering the workshop takes the vehicle off the road.** When a repair
  transitions to `in_repair`, `_ensure_repair_downtime` opens a downtime linked
  to the ticket (`repair_id`) if none is open and moves an operational vehicle to
  `maintenance`. Idempotent — a second `in_repair` creates nothing.
* **Closing the repair does not clear the downtime.** Per the brief, an
  unresolved downtime must be closed explicitly; `advance_repair` never
  auto-closes it.
* **Completion odometer.** On `repaired`/`closed` the caller may pass `odometer`;
  it is validated (DI-01) and forwarded to the vehicle master via the existing
  monotonic `_update_vehicle_odometer`.

## 3. Dedicated downtime close

`PATCH /downtime/{id}/close` records the closure `end_date` and `reason`,
computes `days`, and — if the vehicle has no other open downtime — brings a
`maintenance` vehicle back to `active`. Compare-and-swap on `open` makes it
idempotent; WF-01 already blocks a generic reopen (closed is terminal).

## 4. Tyre lifecycle integrity

* **No double-fit.** `on_tyre_create` refuses a create that would make the same
  `tyre_number` active on a second vehicle (409).
* **Transfer preserves history.** `PATCH /tyres/{id}/transfer` moves a fitted
  tyre to another **same-tenant, in-service** vehicle (DI-01 references),
  appends an immutable `transfer` tyre-event, and audits it. A `removed` or
  `scrapped` tyre cannot be transferred (409).
* **Scrap is terminal.** `PATCH /tyres/{id}/scrap` marks the tyre `scrapped`
  (idempotent), records the removal odometer/reason and an event; a scrapped
  tyre can no longer be transferred or fitted.
* **Odometer validated.** Tyre-event odometers pass DI-01 (`invariants.odometer`)
  — a negative/non-finite reading is a 400.

History is never rewritten: every fitment/transfer/removal/scrap is an appended
`tyre_events` row.

## 5. Controls & permissions

Repair approval/closure keep their existing role gating (`repairs:transition` +
per-state management/admin). Tyre transfer/scrap use `tyres:update`; downtime
close uses `downtime:update` — all existing catalogue permissions, so AUTHZ-01 is
unchanged. Every new mutating action is audited (`tyre.transfer`, `tyre.scrap`,
`downtime.close`) and the repair side effects ride on the existing
`repair.transition` audit.

## 6. Frontend

Tyre rows gain **Transfer** (vehicle picker + odometer) and **Scrap** actions;
downtime rows gain a **Close** action (end date + reason). All call dedicated
endpoints.

## 7. Verification

`backend/tests/test_maintenance_operations.py` — **15 real-HTTP tests**: repair
→ downtime + maintenance; closing a repair leaves the downtime open; completion
odometer forwards the master; invalid repair jump refused; cross-tenant vehicle
on a repair refused; dedicated downtime close records reason/days and reopen is
refused; downtime close brings the vehicle back; tyre double-fit prevented;
transfer preserves history; removed/scrapped tyre cannot be transferred;
odometer validated; cross-tenant transfer target refused; approved repair cost
feeds `payment_reconciliation`.

| Check | Result |
| --- | --- |
| Full backend suite | **776 passed, 3 skipped** |
| OPS-03 additions | 15 |
| Mutation test | Removing the double-fit guard fails `test_tyre_double_fit_prevented` |
| Ruff (changed files) | F/E clean · Gitleaks clean · Frontend build green |

## 8. Remaining limitations (non-blocking)

* **Repair-linked downtime reason.** The auto-opened downtime uses reason
  `breakdown`; distinguishing scheduled service vs breakdown at auto-open is a
  small enhancement left out here.
* **Tyre-event vs vehicle odometer.** Tyre-event odometers are validated for
  sanity (finite, ≥ 0) but not cross-checked against the vehicle master beyond
  DI-04's existing scanner; a stricter "cannot be below current odometer without
  correction" gate is a follow-up.
