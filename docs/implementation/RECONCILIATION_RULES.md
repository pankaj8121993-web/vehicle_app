# FleetFlow — Reconciliation Rules (DI-03)

**Phase:** Data Integrity and Financial Correctness
**Workstream:** DI-03 — Reconciliation and derived balances
**Status:** Repository controls implemented and tested with known-total fixtures. Production reconciliation not performed.

> Builds on DI-01 ([DATA_INTEGRITY_MODEL.md](DATA_INTEGRITY_MODEL.md)) and DI-02
> ([ATOMICITY_AND_IDEMPOTENCY.md](ATOMICITY_AND_IDEMPOTENCY.md)). Ensures every
> total the product shows can be independently recomputed from source records.

---

## 1. Principle: one ledger, one service

- **The canonical expense ledger is `helpers.gather_expenses`.** It converts each
  source record — fuel, repairs, tyres, FASTag tolls, trip toll/parking/misc,
  accidents, services, greasing, manual expenses — into one ledger row carrying
  its `source` and `source_id`. It is already the shared basis of the dashboard,
  the expense overview/insights/ledger, drilldowns, vehicle summary/statistics
  and the expense/category reports. **There are no competing expense formulas.**
- **The canonical reconciliation service is `backend/reconciliation.py`.** Every
  DI-03 total derives from the ledger (or directly from source collections for
  fuel/FASTag/maintenance/payments), never from an independent re-sum. Because a
  ledger row is emitted per source record, the same record can never be counted
  twice within a source.
- **Stored summaries are caches, verified against source.** The vehicle
  `fastag_balance` is recomputed from its transactions and any drift reported —
  the stored number is never trusted as authoritative.
- **Organisation-scoped by construction.** Every read goes through the
  tenant-scoped `database.db`, so a reconciliation run for org A can never pull
  in org B's rows (proven by `test_reconciliation_is_org_scoped`).

---

## 2. Reconciliations implemented

### 2.1 Vehicle costs — `vehicle_cost_breakdown`
Groups the ledger into `fuel`, `fastag`, `repairs`, `maintenance`
(service + greasing), `tyres`, `accidents`, `trip_direct`, with an `other`
bucket for any remaining category (Insurance, Permits, Road Tax, …). The parts
plus `other` always reconcile to `total` (a `reconciles` self-check flag). Adds
`distance_km` (completed trips) and `cost_per_km`.

### 2.2 Fuel — `fuel_reconciliation`
`total_quantity`, `total_amount`, `avg_rate` (amount ÷ quantity), `distance_km`
(odometer span), `avg_mileage` (km between consecutive fills ÷ litres, full-tank
assumption). **Rates/mileage are recomputed from raw quantity/amount/odometer**,
not read from stored `mileage`, so a corrupted stored field cannot skew the
result. Reports `odometer_continuity_breaks` (a fill whose odometer is below a
chronologically earlier one) and `mileage_variance_flags` (a fill more than 2×
or less than 0.5× the median mileage).

### 2.3 FASTag — `fastag_reconciliation`
`toll_total`, `recharge_total`, `net` (recharges − tolls), `transaction_count`,
`duplicate_count` (identical vehicle+date+amount+type+plaza seen more than once),
`unmatched_vehicle_count` (transactions whose vehicle no longer exists),
`trip_linked_tolls` vs `unlinked_tolls` (a toll on a date the vehicle also has a
trip), and per-vehicle `balance_cache` with `stored_balance`, `computed_net` and
`drift`. `reversed_or_disputed` is `0` — no such transaction type exists in the
schema yet (documented, not invented).

### 2.4 Maintenance — `maintenance_reconciliation`
`repair_count`, `repair_cost`, `downtime_days`, repairs `by_status`, and
`repeat_repairs` (same vehicle + category 3+ times).

### 2.5 Payments — `payment_reconciliation`
FleetFlow has **no standalone payment ledger** (DI-01). The realised money states
are reconciled from the records that carry them: accident `claim_total`,
`settlement_total`, `outstanding` (claim − settlement), and `approved_repair_cost`
(repairs in an approved-or-later state). Original/approved/paid/reversed for a
generic payment do not exist as fields and are not fabricated.

### 2.6 Trip economics — `trip_economics`
`distance_km`, `direct_expenses` (toll + parking + misc). `revenue`,
`driver_advance` and `outstanding` are reported as `None` — **there is no
revenue/advance/settlement field in the trip schema yet**, so contribution is the
negative of direct expenses until such a field exists. This is called out rather
than invented.

---

## 3. Treatment of non-standard records

| Case | Treatment |
| --- | --- |
| **Test data** (`is_test_data`) | Excluded by default; included only for the `test` role, consistent with the rest of the app. |
| **Disposed vehicle** | Historical costs remain in the ledger (the spend really happened); DI-01 blocks *new* activity on it. |
| **Cancelled/rejected repair** | Cost counts toward `repair_cost` totals but only an approved-or-later repair counts toward `approved_repair_cost`. |
| **Reversed/disputed FASTag** | No reversal transaction type exists; reported as `0`. A future reversal type would net naturally (it would be a negative-signed movement). |
| **Deleted records** | Hard deletion is blocked where history exists (DI-01); a genuinely deleted source record simply produces no ledger row, so totals stay consistent. |
| **Double counting** | Prevented structurally: one ledger row per source record. Cross-source overlap (a trip's `toll_expense` vs a FASTag toll for the same journey) is surfaced as `trip_linked_tolls`/`unlinked_tolls` for review, not silently summed as one figure. |

---

## 4. Report / export / API equality

Because the reports (`/api/reports/*`, incl. Excel/PDF export), the expense
ledger (`/api/expenses/ledger`) and the reconciliation service all derive from
the same `gather_expenses` ledger, their totals agree for the same filter. This
is asserted directly by `test_report_ledger_and_reconciliation_totals_agree`
(report total == ledger total == reconciliation total == the fixture's expected
₹25,200).

---

## 5. API surface

`backend/routes_reconciliation.py` (gated on the reports module):

| Endpoint | Returns |
| --- | --- |
| `GET /api/reconciliation/vehicle/{id}` | cost breakdown + fuel + maintenance + payments + FASTag for one vehicle |
| `GET /api/reconciliation/fastag` | org-wide FASTag reconciliation (duplicates, unmatched, balance drift) |
| `GET /api/reconciliation/maintenance` | org-wide maintenance reconciliation |
| `GET /api/reconciliation/payments` | org-wide payment reconciliation |
| `GET /api/reconciliation/trip/{id}` | per-trip economics |

These are read-only verification surfaces; the DI-04 scanner reuses the same
service functions to detect drift across the whole dataset.

---

## 6. Tests

`tests/test_di03_reconciliation.py` (10, real-HTTP, two orgs, disposable DB):
- Known-fixture cost breakdown matches hand-computed group totals and grand total (₹25,200).
- Grouped parts + other reconcile to total; cost-per-km correct.
- Fuel totals, average rate and mileage recomputed correctly; no false continuity break.
- FASTag balance cache matches source (drift 0 for a clean vehicle); **drift detected** for a corrupt stored balance; **duplicate detection**.
- Payment reconciliation (accident claim/settlement/outstanding; approved repair cost).
- **Report total == ledger total == reconciliation total.**
- **Cross-tenant:** an empty org sees zero, and cannot reconcile another org's vehicle.

Full backend suite after DI-03: **692 passed, 3 skipped**. Ruff clean; frontend
build OK; secret scan clean.

---

## 7. Non-goals / future work

- **Trip revenue, driver advances and settlements** — no schema fields yet; add a
  revenue/advance model to compute true trip profit and outstanding.
- **FASTag reversal/dispute** transaction types.
- **Opening FASTag balance** as a first-class field, so balance-cache drift can be
  verified without the opening-balance caveat (today a clean vehicle starts at 0).
- **Materialised/cached reconciliation** for very large fleets (current service
  computes on demand).
