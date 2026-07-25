# FleetFlow — Data-Integrity Runbook (DI-04)

**Phase:** Data Integrity and Financial Correctness
**Workstream:** DI-04 — Data-quality controls and repair tooling
**Status:** Repository tooling implemented and tested against synthetic fixtures. Not run against production.

> Operator runbook for `backend/check_data_integrity.py`: how to detect existing
> inconsistent data and, where reviewed, repair it safely. Builds on DI-01/02/03.

---

## 1. Safety contract

The tool is built around a hard safety contract; read it before running:

- **Dry-run by default.** `scan` only reads. It never writes findings data.
- **Never deletes.** No code path removes a document. The only repair recomputes
  a numeric cache.
- **Backup confirmation before any write.** `repair --apply` refuses without
  `--confirm-backup`.
- **Per organisation.** Findings carry `org_id`; `--org` scopes a run. Missing
  ownership and cross-tenant references are themselves detectors.
- **Never prints secrets or personal data.** Findings and audit rows carry ids,
  collection/field names, statuses and numeric amounts only — never names,
  Aadhaar, licence, mobile, passwords, hashes or tokens.
- **Safe to rerun.** Detectors are pure reads; the repair is idempotent.
- **Never against production during development.** Rehearse only against an
  **isolated, disposable** database. Do not run against production data as part
  of this repository phase (see DATA_INTEGRITY_RELEASE_GATE.md — production
  reconciliation is operator-gated and not performed here).

---

## 2. Detectors

| Detector | Severity | What it finds |
| --- | --- | --- |
| `missing_org_ownership` | error | Tenant record with no `org_id`. |
| `orphaned_reference` | error | `vehicle_id`/`driver_id`/`tyre_id`/`trip_id`/`vendor_id`/`assigned_vehicle_id` pointing at a record that does not exist. |
| `cross_tenant_reference` | error | A foreign key resolving to a record in a **different** organisation. |
| `duplicate_external_reference` | error | Duplicate `vehicle_number` / `tyre_number` / `ticket_number` within an org. |
| `duplicate_fastag_transaction` | warning | Identical vehicle+date+amount+type+plaza FASTag rows. |
| `invalid_odometer_sequence` | warning | A fuel entry whose odometer is below a chronologically earlier one. |
| `impossible_monetary_value` | error | A monetary field that is negative, non-finite or out of range. |
| `settlement_exceeds_claim` | error | Accident `settlement_amount` > `claim_amount`. |
| `invalid_status` | warning | A status value outside the known set for the collection. |
| `inconsistent_downtime` | warning | Downtime with an `end_date` but not `closed`. |
| `completed_trip_without_closing_km` | warning | A trip marked `completed` with no `closing_km`. |
| `negative_fastag_balance` | error | Stored `fastag_balance` below zero (impossible). |
| `fastag_balance_drift` | warning | Stored balance ≠ recomputed transaction net (may be a legitimate opening balance — review). |

Every detector has a synthetic-fixture test in `tests/test_di04_data_integrity.py`,
plus a coverage test asserting all of them fire.

---

## 3. Detect (dry-run)

```bash
cd /app/backend

# All organisations, human summary:
python -m check_data_integrity scan

# One organisation:
python -m check_data_integrity scan --org <org_id>

# Narrow to a collection or a single record:
python -m check_data_integrity scan --collection fastag_transactions
python -m check_data_integrity scan --record <record_id>

# Full machine-readable, redacted report (for the evidence log):
python -m check_data_integrity scan --org <org_id> --json > scan-<org>-<date>.json
```

The summary prints the total, a severity breakdown and a per-detector count.
`--json` emits the full redacted finding list. A `scan` run records a non-secret
audit row (`data_integrity_audit`) with counts only.

---

## 4. Repair (reviewed, backup-gated, non-destructive)

Only one reviewed repair exists today:

- **`recompute-fastag-balance`** — sets each vehicle's `fastag_balance` to the net
  of its FASTag transactions (recharges − tolls). It treats the transactions as
  authoritative, i.e. **assumes a zero opening balance**. Only run it after
  confirming opening balances are zero or already folded in (review the
  `fastag_balance_drift` findings first). It is idempotent and never deletes.

```bash
# 1. Take and verify a backup of the target database.

# 2. Preview (dry-run — shows every from -> to, writes nothing):
python -m check_data_integrity repair --action recompute-fastag-balance --org <org_id>

# 3. Apply (requires the explicit backup assertion):
python -m check_data_integrity repair --action recompute-fastag-balance \
    --org <org_id> --confirm-backup --apply
```

`--apply` without `--confirm-backup` is refused. An applied repair records a
non-secret `data_integrity_audit` row with the change count.

---

## 5. Standard procedure

1. **Backup** the target database and verify the backup restores.
2. **Scan** the organisation; export the `--json` report into the evidence log
   (`DATA_INTEGRITY_EVIDENCE_TEMPLATE.md`).
3. **Triage** findings: `error` first. Many are data to correct by hand in the
   app (a wrong status, a duplicate the user must merge), not by this tool.
4. **Repair** only the categories with a reviewed automated action, dry-run then
   `--apply` with `--confirm-backup`.
5. **Re-scan** to confirm the finding count dropped and nothing new appeared
   (the tool is safe to rerun).
6. **Record** evidence: attach the before/after `--json` reports and the audit
   row ids to the evidence log.

---

## 6. What the tool does *not* do

- It does not delete, merge or hand-edit records — those are human decisions made
  in the app.
- It does not fix orphaned/cross-tenant references automatically (reassigning
  ownership is a judgement call; doing it wrong is a cross-tenant disclosure).
- It does not touch production as part of this phase. Production integrity
  scanning and reconciliation are operator-gated (DATA_INTEGRITY_RELEASE_GATE.md).
