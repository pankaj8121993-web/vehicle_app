# FleetFlow — Operational Exceptions, Alerts and Closure (OPS-05)

**Status:** Implemented on `feature/ops-05-exceptions`.
**Scope:** Repository-side only. No production data was accessed.

---

## 1. Goal

Make pending operational work visible without building a new analytics platform,
new financial calculations or any email/SMS/WhatsApp integration. One org-scoped,
permission-checked exceptions feed derived **live** from canonical source data.

## 2. The feed (`routes_exceptions.py`)

`GET /api/exceptions` returns categorised exception items plus a `by_category`
summary and the thresholds in effect. Categories, all derived from the
tenant-scoped `db`:

| Category | Source condition |
| --- | --- |
| `trips_awaiting_dispatch` | trip in `planned`/`assigned` |
| `trips_overdue_completion` | `ongoing` trip older than `trip_overdue_days` |
| `trips_awaiting_settlement` | `completed`/`settlement_pending` trip |
| `missing_closing_odometer` | `completed` trip with no `closing_km` |
| `unapproved_expenses` | expense `approval_status = submitted` |
| `unpaid_approved_expenses` | approved expense with outstanding > 0 |
| `repairs_awaiting_approval` | repair `open`/`under_review` |
| `repairs_overdue_completion` | repair in workshop older than `repair_overdue_days` |
| `open_downtime` | downtime `open` |
| `vehicles_under_repair` | vehicle `maintenance` |
| `documents_expiring_soon` / `expired_documents` | current document within/over horizon |
| `licences_expiring` | active driver licence within horizon |
| `open_accident_claims` | claim not yet settled/closed |
| `claims_awaiting_settlement` | claim `approved`, not settled |

**Design properties**

* **Derived, not stored.** Every item is computed from the source collections, so
  a *resolved* item leaves the list the moment its condition clears — proven by
  the close-downtime test. There is no parallel alert store to drift.
* **Stable identifiers.** Each item's id is `category:source_id`, so the same
  record never yields two alerts (no-duplicate test) and an acknowledgement pins
  to it deterministically.
* **Configurable thresholds.** `trip_overdue_days` (default 2),
  `repair_overdue_days` (7) and `doc_horizon_days` (30) are query parameters with
  documented defaults; boundary behaviour is tested.
* **No parallel money math.** Financial items reuse the same
  `approved_amount`/`paid_amount` fields the OPS-02 lifecycle maintains.

## 3. Acknowledgement

`POST /api/exceptions/{id}/acknowledge` upserts a row in the org-scoped
`exception_acks` (unique per `exception_id`), recording who/when and an optional
note. It is **idempotent** and — crucially — **does not remove** the item while
the source condition persists; the feed simply flags it `acknowledged`. An
acknowledgement can never permanently hide an unresolved problem.

## 4. Permissions & isolation

The feed uses `require_module("dashboard")` (all roles, drivers included);
acknowledgement uses the new `exceptions:acknowledge` permission
(admin/management/data_entry — viewer refused). The feed reads only through the
tenant-scoped `db`, so another organisation's records never appear (cross-tenant
test). `exception_acks` is org-scoped (tenant-isolation matrix exemption: no CRUD
surface, written only via the acknowledge action). Every acknowledgement is
audited (`exception.acknowledge`).

## 5. Frontend

The Dashboard gains an **Operational Exceptions** panel listing the live items
grouped with severity colouring and per-item Acknowledge buttons — a minimal
addition to an existing view, no new analytics dashboard.

## 6. Verification

`backend/tests/test_operational_exceptions.py` — **9 real-HTTP tests**: open
downtime appears then resolves on close; unapproved expense and awaiting-dispatch
trip appear; no duplicate ids; category totals equal the item list; trip-overdue
threshold boundary; acknowledge flags without hiding and is idempotent (one ack
row); cross-tenant isolation; viewer cannot acknowledge.

| Check | Result |
| --- | --- |
| Full backend suite | **796 passed, 3 skipped** |
| OPS-05 additions | 9 |
| Mutation test | Neutralising the overdue threshold fails `test_trip_overdue_threshold_boundary` |
| Ruff (changed files) | F/E clean · Gitleaks clean · Frontend build green |

## 7. Remaining limitations (non-blocking)

* **FASTag drift / fuel anomalies / data-integrity findings** are surfaced by the
  existing reconciliation service and the DI-04 data-integrity scanner rather
  than duplicated into this feed; folding their summaries into `GET /exceptions`
  is a small, additive follow-up (the sources already exist and are org-scoped).
* **Acknowledgement staleness.** An acknowledgement pins to the stable id; if a
  condition clears and later recurs for the same record, the old ack still
  matches. Surfacing "acknowledged before the latest recurrence" is a refinement
  left for later.
