# FleetFlow — Expense Approval, Payment and Settlement (OPS-02)

**Status:** Implemented on `feature/ops-02-expenses-settlement`.
**Scope:** Repository-side only. No production data was accessed.

---

## 1. What was missing

WORKFLOWS.md §3 recorded the honest pre-OPS-02 position: FleetFlow had **no
expense-approval, payment or settlement workflow**. A manual expense was a plain
record; `approval_status`/`payment_status`/`paid_by` were protected pre-emptively
by TEN-01 but *unused*; there was no notion of an approved amount, a paid amount,
an outstanding balance, a payment event, a reversal, a driver advance or a trip
settlement.

OPS-02 adds the operational financial lifecycle **without** building an
accounting ledger (no double-entry, no chart of accounts, no revenue).

## 2. The model — approval is not payment

Each manual expense now carries two independent axes:

| Axis | Field | Values |
| --- | --- | --- |
| Approval | `approval_status` | `submitted` → `approved` / `rejected` |
| Payment | `paid_amount` (derived) | 0 … `approved_amount` |

* **Incurred / submitted** — set on create (`routes_assets.on_expense_create`).
* **Approved** — `approved_amount` (≤ submitted) is fixed by the approve action.
* **Rejected** — terminal; excluded from the reconciliation ledger and unpayable.
* **Paid / outstanding** — `paid_amount` is the **sum of append-only payment
  events** minus reversals; `outstanding = approved_amount − paid_amount`.

Payment and approval are deliberately different events with different
permissions; a reversal preserves the original event and restores outstanding.

## 3. Dedicated actions (`routes_settlement.py`)

| Action | Endpoint | Permission | Controls |
| --- | --- | --- | --- |
| Approve | `PATCH /expenses/{id}/approve` | `expenses:approve` | `approved_amount ≤ submitted`; **self-approval refused**; idempotent; CAS on `approval_status` |
| Reject | `PATCH /expenses/{id}/reject` | `expenses:reject` | only from submitted; idempotent; excluded from ledger |
| Record payment | `POST /expenses/{id}/payments` | `expenses:pay` | only if approved; `amount>0`; `paid+amount ≤ approved`; append-only event; Idempotency-Key aware |
| Reverse payment | `POST /expenses/{id}/payments/{pid}/reverse` | `expenses:reverse_payment` | original preserved; reversal event restores outstanding; idempotent per payment |
| Recover advance | `PATCH /advances/{id}/recover` | `settlements:close` | recovered ≤ advance amount; marks recovered |
| Trip settlement | `GET /trips/{id}/settlement` | `expenses:approve` | read-only aggregation |
| Settle trip | `PATCH /trips/{id}/settle` | `settlements:close` | `completed → settlement_pending`; **blocked while linked expenses await approval** unless `override_pending` |

Driver advances are their own tenant-scoped `advances` collection (dedicated
CRUD), recovered/adjusted at settlement.

## 4. Controls

* **Approval ceiling.** `approved_amount` can never exceed the submitted amount
  (an authorised *downward* adjustment is allowed; upward is a 400).
* **Payment ceiling.** The running paid total can never exceed the approved
  outstanding (400).
* **Rejected is unpayable** and does not appear as an active cost.
* **Idempotency / replay.** Approve/reject are idempotent no-ops when already in
  state; payment is `Idempotency-Key` aware; `paid_amount` is recomputed from
  events (write-source-first, DI-02) so a retry never double-pays.
* **Concurrency.** Approve/reject use `atomicity.swap_field` (compare-and-swap on
  `approval_status`) and honour `expected_version`, so two concurrent approvals
  cannot both apply.
* **Self-approval.** The user who submitted an expense (`created_by`) cannot
  approve it; approval/payment are management/admin only, so a data-entry
  submitter cannot approve or pay their own claim at all.
* **No silent edits.** A generic `PUT /expenses/{id}` that changes `amount` after
  approval/rejection is refused (409); the workflow fields remain TEN-01
  protected.
* **Reconciliation.** Rejected/cancelled expenses are excluded from
  `helpers.gather_expenses`; the trip-settlement direct-expense figure equals
  `reconciliation.trip_economics(trip_id).direct_expenses` — no parallel money
  calculation.
* **Audit.** `expense.approve`, `expense.reject`, `expense.payment`,
  `expense.payment_reversal`, `advance.recover`, `trip.settle`.

## 5. Permissions (AUTHZ-01 extension)

New org permissions `expenses:approve`, `expenses:reject`, `expenses:pay`,
`expenses:reverse_payment`, `settlements:close` — granted to **management and
admin only**. `advances` is a new CRUD resource (create/update by data_entry+,
delete admin-only). `expenses:create` (submission) stays with data_entry, so
submission and approval are held by different tiers.

## 6. Frontend

The **Manual Entries** tab (`Expenses.jsx`) gains an Approval column and per-row
dedicated-action buttons — Approve (with an editable approved amount), Reject and
Record Payment (showing outstanding). Every button calls a dedicated endpoint.

## 7. Verification

`backend/tests/test_expense_settlement.py` — **18 real-HTTP tests**: submitted on
create; approval within/over submitted; double approval idempotent; self-approval
and data-entry approval refused; payment within/over outstanding; unapproved and
rejected unpayable; double payment idempotent with key; reversal restores
outstanding; generic amount edit locked; cross-tenant expense isolated; advance
recovery bounds; settlement totals reconciling with `trip_economics`; rejected
excluded from ledger; settlement blocked by pending approval. The tenant
isolation matrix now covers `advances`.

| Check | Result |
| --- | --- |
| Full backend suite | **761 passed, 3 skipped** |
| OPS-02 additions | 18 (+ matrix coverage for advances) |
| Mutation test | Removing the payment ceiling fails `test_payment_exceeding_outstanding_rejected` |
| Ruff (changed files) | F/E clean · Gitleaks clean · Frontend build green |

## 8. Remaining limitations (non-blocking)

* **Advances vs the wider ledger.** Advances net against a driver's approved
  reimbursables in the settlement view (`net_payable_to_driver`), but there is no
  driver-level running account across trips — that would be a driver-ledger
  feature beyond OPS-02's scope.
* **Approval only on manual expenses.** The approval/payment lifecycle applies to
  the `expenses` collection (the natural expense-claim entity). Derived costs
  (fuel, repairs, tolls) keep their existing controls (e.g. the repair approval
  workflow) rather than being funnelled through expense approval.
