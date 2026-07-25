# FleetFlow — Data-Integrity Execution Status

**Purpose:** Persistent source of truth for the Data Integrity and Financial
Correctness programme (Phase 2) across working sessions. Read together with
`MASTER_PLAN.md`, `DATA_INTEGRITY_RELEASE_GATE.md` and the relevant reference doc
before resuming any workstream.

**Last updated:** 25 July 2026

> **Rule of this document:** repository controls and tooling are never recorded as
> production execution. A workstream that has shipped and been tested but not run
> against production data is *complete (repository)*, not *production-verified*.

---

## Summary

| ID | Workstream | Status | PR | Merge | Production executed |
| --- | --- | --- | --- | --- | --- |
| DI-01 | Canonical records and invariants | **Merged** | #14 | `4be98ef` | N/A (code only) |
| DI-02 | Atomic operations and idempotency | **Merged** | #15 | `551dc0b` | N/A (code only) |
| DI-03 | Reconciliation and derived balances | **Merged** | #16 | `f2c3858` | N/A (code only) |
| DI-04 | Data-quality controls and repair tooling | **Merged** | #17 | `b2e542c` | **No** (not run against production) |
| DI-CLOSEOUT | Data-integrity release gate | **Merged** | #18 | *(this PR)* | N/A |

---

## What each workstream delivered

- **DI-01** — `invariants.py` (decimal money, quantity/odometer bounds, ordering),
  `references.py` (same-org / in-service foreign keys), calculated-field
  protection, approved-repair cost lock, org-scoped uniqueness indexes. Docs:
  `DATA_INTEGRITY_MODEL.md`. Tests: `test_invariants.py` (38),
  `test_di01_enforcement.py` (16).
- **DI-02** — `idempotency.py` (Idempotency-Key claim/replay via a unique index),
  `atomicity.py` (transaction probe + compare-and-swap), write-source-first side
  effects. Standalone MongoDB → no multi-document transactions; compensation used.
  Docs: `ATOMICITY_AND_IDEMPOTENCY.md`. Tests: `test_idempotency.py` (7),
  `test_di02_atomicity.py` (11). **Mutation-tested** (idempotency + compare-and-swap).
- **DI-03** — `reconciliation.py` (single canonical calc service over the shared
  `gather_expenses` ledger), `routes_reconciliation.py`. Docs:
  `RECONCILIATION_RULES.md`. Tests: `test_di03_reconciliation.py` (10, known
  totals + report==ledger==reconciliation + cross-tenant).
- **DI-04** — `check_data_integrity.py` (dry-run scanner, 13 detectors, redacted
  report, backup-gated non-destructive repair). Docs: `DATA_INTEGRITY_RUNBOOK.md`,
  `DATA_INTEGRITY_EVIDENCE_TEMPLATE.md`. Tests: `test_di04_data_integrity.py` (20).
- **DI-CLOSEOUT** — `DATA_INTEGRITY_RELEASE_GATE.md` (per-domain evidence + release
  decision), this status doc, `MASTER_PLAN.md` update.

---

## Evidence snapshot

- **Full backend suite:** 712 passed, 3 skipped.
- **Mutation evidence:** DI-02 idempotency-replay and compare-and-swap controls
  both fail their tests when broken; DI-04 per-detector coverage test.
- **Ruff:** clean. **Frontend build:** OK. **Secret scan (gitleaks):** clean.
- **Security/tenant suites:** unchanged and passing.

---

## Outstanding (operator-led, NOT executed)

Production dependability is **not** established by this repository programme:

1. **Production backup** (verified) before any production integrity activity.
2. **Production integrity scan** — run `check_data_integrity.py scan` against a
   production-cloned/disposable copy; triage findings.
3. **Production reconciliation sign-off** — confirm dashboards/reports/exports
   reconcile to source on real data.

No production data was accessed or modified. `main` was not modified.

## Future work (documented, out of scope)

Standalone payment ledger; trip revenue / driver advances / FASTag reversal
fields; real multi-document transactions on a replica set; mandatory idempotency
on the frontend; chassis/engine & tyre-position invariants; materialised
reconciliation caches.
