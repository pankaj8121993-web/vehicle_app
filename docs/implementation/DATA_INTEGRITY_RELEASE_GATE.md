# FleetFlow — Data-Integrity Release Gate (DI-CLOSEOUT)

**Phase:** Data Integrity and Financial Correctness
**Workstream:** DI-CLOSEOUT — Data-integrity release gate
**Date:** 25 July 2026
**Status:** Evidence-based assessment of the repository data-integrity programme.

> One consolidated, honest assessment of whether FleetFlow's core operational and
> financial data model is dependable. Companion to the security release gate
> ([SECURITY_RELEASE_GATE.md](SECURITY_RELEASE_GATE.md)).

---

## 1. Programme summary

| Workstream | Scope | PR | Merge commit |
| --- | --- | --- | --- |
| DI-01 | Canonical records and invariants | #14 | `4be98ef` |
| DI-02 | Atomic operations and idempotency | #15 | `551dc0b` |
| DI-03 | Reconciliation and derived balances | #16 | `f2c3858` |
| DI-04 | Data-quality controls and repair tooling | #17 | `b2e542c` |
| DI-CLOSEOUT | This gate | #18 | *(this PR)* |

**Reference docs:** [DATA_INTEGRITY_MODEL.md](DATA_INTEGRITY_MODEL.md),
[ATOMICITY_AND_IDEMPOTENCY.md](ATOMICITY_AND_IDEMPOTENCY.md),
[RECONCILIATION_RULES.md](RECONCILIATION_RULES.md),
[DATA_INTEGRITY_RUNBOOK.md](DATA_INTEGRITY_RUNBOOK.md),
[DATA_INTEGRITY_EVIDENCE_TEMPLATE.md](DATA_INTEGRITY_EVIDENCE_TEMPLATE.md).

**Test evidence (whole programme):** full backend suite **712 passed, 3 skipped**.
**Mutation evidence:** two controls mutation-tested (DI-02) — disabling
idempotency replay fails `test_retried_create_with_same_key_writes_one_record`;
dropping the compare-and-swap status filter fails
`test_swap_status_is_compare_and_swap`. DI-04 has a per-detector coverage test
that fails if any detector stops firing. Ruff clean; frontend build OK; gitleaks
clean. Existing security/tenant suites unchanged.

**Deployment note:** the environment's MongoDB is a **standalone** — multi-document
transactions are unavailable — so atomicity uses single-document compare-and-swap
plus write-source-first compensation (see DI-02). This is a design constraint, not
a gap; the code is ready to opt into real transactions on a replica set.

---

## 2. Per-domain assessment

Legend — Production verification status is **Not performed** for every domain:
no production data was accessed, and reconciliation against real data is
operator-gated (§3).

### Vehicles
- **Canonical source:** `vehicles` (`(org_id, vehicle_number)` unique).
- **Validation:** money (`purchase_price`, `sale_value`); status lifecycle (WF-01); disposal terminal & role-gated.
- **Duplicate protection:** `uniq_org_vehicle_number`; idempotency key on create.
- **Atomicity:** disposal transition + side effects (close downtimes, unassign drivers), idempotent.
- **Reconciliation:** `vehicle_cost_breakdown` (all cost groups + cost/km).
- **Tests:** DI-01 enforcement, DI-03 breakdown, DI-04 duplicate/status detectors. **Mutation:** DI-02 idempotency.
- **PR/commit:** DI-01 `4be98ef`, DI-03 `f2c3858`. **Limitation:** chassis/engine uniqueness not yet indexed. **Prod:** Not performed.

### Drivers
- **Canonical source:** `drivers`.
- **Validation:** status lifecycle (WF-01); `assigned_vehicle_id` must be real, same-org, in-service.
- **Duplicate protection:** idempotency key on create.
- **Atomicity:** exit transition unassigns vehicle atomically per-document.
- **Reconciliation:** driver stats derive from trips/fuel (canonical ledger).
- **Tests:** DI-01 reference validation, DI-04 orphaned/cross-tenant/status. **Mutation:** DI-02 idempotency (shared create path).
- **PR/commit:** DI-01 `4be98ef`. **Limitation:** no driver-advance ledger. **Prod:** Not performed.

### Trips
- **Canonical source:** `trips`.
- **Validation:** `closing_km ≥ opening_km` (create + close); references in-service vehicle / non-exited driver; `distance` server-computed & client-rejected.
- **Duplicate protection:** idempotency key on create.
- **Atomicity:** close is compare-and-swap on `ongoing` → no double close / double odometer bump.
- **Reconciliation:** `trip_economics` (direct expenses; revenue/advance flagged unavailable).
- **Tests:** DI-01 km ordering + refs, DI-02 concurrent close, DI-04 completed-without-closing-km. **Mutation:** DI-02 compare-and-swap.
- **PR/commit:** DI-01 `4be98ef`, DI-02 `551dc0b`. **Limitation:** no revenue field → contribution only. **Prod:** Not performed.

### Expenses
- **Canonical source:** `expenses` + the unified ledger (`gather_expenses`).
- **Validation:** money (`amount`); references vehicle.
- **Duplicate protection:** idempotency key; DI-04 duplicate detectors; DI-03 one-row-per-source (no double count).
- **Atomicity:** single-record create.
- **Reconciliation:** the canonical ledger; report == ledger == reconciliation total (tested).
- **Tests:** DI-03 equality + breakdown, DI-01 money. **Mutation:** DI-02 idempotency.
- **PR/commit:** DI-01 `4be98ef`, DI-03 `f2c3858`. **Limitation:** cross-source overlap (trip toll vs FASTag toll) surfaced, not merged. **Prod:** Not performed.

### Fuel
- **Canonical source:** `fuel_entries`.
- **Validation:** `quantity > 0`, `odometer ≥ 0`, money; `mileage`/`fuel_cost_per_km` server-computed & client-rejected.
- **Duplicate protection:** idempotency key; DI-04 duplicate + odometer-sequence detectors.
- **Atomicity:** create + odometer forward (monotonic, self-healing).
- **Reconciliation:** `fuel_reconciliation` (rate/mileage recomputed from raw fields; continuity & variance flags).
- **Tests:** DI-01 quantity/odometer, DI-03 fuel metrics, DI-04 odometer sequence. **Mutation:** DI-02 idempotency.
- **PR/commit:** DI-01 `4be98ef`, DI-03 `f2c3858`. **Limitation:** full-tank assumption for mileage. **Prod:** Not performed.

### FASTag
- **Canonical source:** `fastag_transactions`; vehicle `fastag_balance` is a **cache**.
- **Validation:** money (`amount`); `txn_type` ∈ toll/recharge.
- **Duplicate protection:** idempotency key; demo sim idempotent by `sim_batch`; DI-04 duplicate detector.
- **Atomicity:** write-source-first — transaction stored before balance `$inc` (rebuildable).
- **Reconciliation:** `fastag_reconciliation` — balance drift, duplicates, unmatched, trip-linked vs unlinked.
- **Tests:** DI-03 cache-drift + duplicate detection, DI-04 balance detectors. **Mutation:** DI-02 idempotency.
- **PR/commit:** DI-02 `551dc0b`, DI-03 `f2c3858`, DI-04 `b2e542c`. **Limitation:** no reversal/dispute type; opening-balance caveat on drift. **Prod:** Not performed.

### Repairs
- **Canonical source:** `repairs` (`(org_id, ticket_number)` unique).
- **Validation:** money (`cost`); WF-01 state graph; **cost locked once approved** (generic PUT → 409).
- **Duplicate protection:** `uniq_org_ticket_number`; idempotency key on create and on the transition action.
- **Atomicity:** transition is compare-and-swap on stored status → no double approval; `_version` optimistic check.
- **Reconciliation:** `maintenance_reconciliation` (cost, by-status, repeat repairs); `payment_reconciliation` (approved cost).
- **Tests:** DI-01 cost-lock, DI-02 concurrent approval applies once (audit ground-truth). **Mutation:** DI-02 compare-and-swap.
- **PR/commit:** DI-01 `4be98ef`, DI-02 `551dc0b`, DI-03 `f2c3858`. **Limitation:** approval role rules unchanged from WF-01. **Prod:** Not performed.

### Tyres
- **Canonical source:** `tyres` (`(org_id, tyre_number)` unique) + `tyre_events`.
- **Validation:** money (`cost`); odometer fields.
- **Duplicate protection:** `uniq_org_tyre_number`; idempotency key on create.
- **Atomicity:** replacement — event stored before tyre status change (write-source-first).
- **Reconciliation:** tyre costs flow into the canonical ledger / vehicle breakdown.
- **Tests:** DI-02 tyre-replacement side effect lands, DI-04 duplicate/status. **Mutation:** DI-02 idempotency.
- **PR/commit:** DI-01 `4be98ef`, DI-02 `551dc0b`. **Limitation:** no two-tyres-one-position invariant yet. **Prod:** Not performed.

### Odometer
- **Canonical source:** per-event odometer readings; vehicle `current_odometer` forwarded upward only.
- **Validation:** `odometer ≥ 0`, finite, bounded; `closing_km ≥ opening_km`.
- **Duplicate protection:** n/a (a reading, not a transaction).
- **Atomicity:** forward-only update; never decreased silently.
- **Reconciliation:** `fuel_reconciliation` continuity breaks; DI-04 `invalid_odometer_sequence`.
- **Tests:** DI-01 odometer bounds, DI-03 continuity, DI-04 sequence detector. **Mutation:** DI-04 coverage test.
- **PR/commit:** DI-01 `4be98ef`, DI-03 `f2c3858`, DI-04 `b2e542c`. **Limitation:** out-of-sequence backdated readings detected, not blocked. **Prod:** Not performed.

### Payments
- **Canonical source:** no standalone payment ledger; realised money-states are accident `claim`/`settlement` and approved repair cost.
- **Validation:** `settlement_amount ≤ claim_amount`.
- **Duplicate protection:** idempotency key on accident create.
- **Atomicity:** single-record.
- **Reconciliation:** `payment_reconciliation` (claim/settlement/outstanding, approved repair cost).
- **Tests:** DI-01 settlement≤claim, DI-03 payment reconciliation, DI-04 settlement-exceeds-claim. **Mutation:** DI-02 idempotency.
- **PR/commit:** DI-01 `4be98ef`, DI-03 `f2c3858`, DI-04 `b2e542c`. **Limitation:** **no dedicated payment ledger** (partial payments/TDS/GST) — future work. **Prod:** Not performed.

### Approvals
- **Canonical source:** repair `approved` state (the only genuine approval workflow — WF-01).
- **Validation:** WF-01 state graph + role gate.
- **Duplicate protection:** compare-and-swap prevents double approval; idempotent re-approve.
- **Atomicity:** compare-and-swap + optimistic `_version`.
- **Reconciliation:** approved repair cost in `payment_reconciliation`.
- **Tests:** DI-02 concurrent approval applies exactly once. **Mutation:** DI-02 compare-and-swap.
- **PR/commit:** DI-02 `551dc0b`. **Limitation:** no generic expense/payment approval workflow. **Prod:** Not performed.

### Dashboards
- **Canonical source:** derive from the canonical ledger (`gather_expenses`) + source collections.
- **Validation/atomicity:** n/a (read-only).
- **Duplicate protection:** one ledger row per source record (no double count).
- **Reconciliation:** same service basis as reports (no competing formulas).
- **Tests:** DI-03 equality proves the shared basis; existing dashboard tests unchanged.
- **PR/commit:** DI-03 `f2c3858`. **Limitation:** no materialised cache verification for very large fleets. **Prod:** Not performed.

### Reports
- **Canonical source:** `gather_expenses` + source collections.
- **Reconciliation:** **report total == ledger total == reconciliation total** (tested).
- **Tests:** DI-03 `test_report_ledger_and_reconciliation_totals_agree`.
- **PR/commit:** DI-03 `f2c3858`. **Limitation:** none new. **Prod:** Not performed.

### Exports
- **Canonical source:** the same `build_report` rows as the API reports (Excel/PDF).
- **Reconciliation:** exports render the same rows as the report API for the same filter, so totals match by construction (DI-03 report-equality basis).
- **Tests:** DI-03 report equality (export shares `build_report`); existing export tests unchanged.
- **PR/commit:** DI-03 `f2c3858`. **Limitation:** export-vs-API equality proven via the shared builder, not a byte-level export diff test. **Prod:** Not performed.

---

## 3. What is NOT covered (honest limitations)

- **No production reconciliation.** Every "Production verification" above is *Not
  performed*. No production data was accessed or modified in this phase.
- **Standalone MongoDB** — real multi-document transactions are unavailable here;
  compare-and-swap + compensation are used (safe, but a replica set would allow
  stronger guarantees).
- **No standalone payment ledger** (partial payments, TDS/GST, generic approval).
- **No trip revenue / driver-advance / FASTag-reversal fields** — related
  economics are reported as unavailable rather than invented.
- **Idempotency is opt-in** (header-driven), not yet mandatory on the frontend.
- **Some data-quality issues are detected, not blocked** (out-of-sequence
  odometer, cross-source toll overlap) — surfaced by the DI-04 scanner for review.

---

## 4. Release decision

```
Repository data-integrity controls: Complete
Production data reconciliation: Not performed
Production release approval: Pending production backup, integrity scan and reconciliation sign-off
```

The repository-side data-integrity programme (DI-01…DI-04) is **complete, tested
and mutation-tested**. Production dependability cannot be asserted from passing
tests alone: it requires an operator-led production backup, a
`check_data_integrity.py` scan of production data, and reconciliation sign-off
against real records (see DATA_INTEGRITY_RUNBOOK.md). Until then, production
release is **not approved** on data-integrity grounds.

> This gate does not claim production data is clean. It claims the *controls* that
> keep it clean are implemented and verified in the repository.
