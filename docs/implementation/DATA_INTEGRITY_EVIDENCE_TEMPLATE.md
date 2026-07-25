# FleetFlow — Data-Integrity Evidence Log (DI-04)

**Purpose:** Record evidence of each data-integrity scan/repair run. Copy this
template per run. **Never paste secrets or personal data** — the tool's output is
already redacted; keep it that way here.

Companion to [DATA_INTEGRITY_RUNBOOK.md](DATA_INTEGRITY_RUNBOOK.md).

---

## Run header

| Field | Value |
| --- | --- |
| Run id | `<uuid or ticket ref>` |
| Date / time (UTC) | `<YYYY-MM-DDThh:mm:ssZ>` |
| Operator | `<name / role>` |
| Environment | `disposable-test` / `staging` / `production` |
| Database name (`DB_NAME`) | `<db name — not the connection string>` |
| Organisation scope (`--org`) | `<org_id or ALL>` |
| Tool version / commit | `<git commit sha>` |

> Do **not** record `MONGO_URL` or any credential here.

---

## Pre-run backup (required before any repair)

| Field | Value |
| --- | --- |
| Backup taken? | Yes / No |
| Backup location (non-secret label) | `<label, not a signed URL>` |
| Restore verified? | Yes / No |
| Verified by | `<name>` |

---

## Scan result (dry-run)

Command:

```
python -m check_data_integrity scan --org <org_id> --json > scan-before.json
```

| Metric | Value |
| --- | --- |
| Total findings | `<n>` |
| Errors | `<n>` |
| Warnings | `<n>` |

Per-detector counts:

| Detector | Count | Notes / disposition |
| --- | --- | --- |
| missing_org_ownership | | |
| orphaned_reference | | |
| cross_tenant_reference | | |
| duplicate_external_reference | | |
| duplicate_fastag_transaction | | |
| invalid_odometer_sequence | | |
| impossible_monetary_value | | |
| settlement_exceeds_claim | | |
| invalid_status | | |
| inconsistent_downtime | | |
| completed_trip_without_closing_km | | |
| negative_fastag_balance | | |
| fastag_balance_drift | | |

Attach: `scan-before.json` (redacted).

---

## Repairs applied (if any)

| Field | Value |
| --- | --- |
| Action | `recompute-fastag-balance` |
| Reviewed by | `<name>` |
| Dry-run previewed? | Yes / No |
| `--confirm-backup` given? | Yes / No |
| Vehicles changed | `<n>` |
| `data_integrity_audit` row id(s) | `<ids>` |

Findings **not** auto-repaired and their manual disposition (corrected in app,
accepted, ticketed):

| Detector | Record id(s) | Disposition |
| --- | --- | --- |
| | | |

---

## Post-run re-scan

Command:

```
python -m check_data_integrity scan --org <org_id> --json > scan-after.json
```

| Metric | Before | After |
| --- | --- | --- |
| Total findings | | |
| Errors | | |
| Warnings | | |

Attach: `scan-after.json` (redacted).

---

## Sign-off

| Field | Value |
| --- | --- |
| Outcome | Clean / Residual findings accepted / Follow-up required |
| Follow-up ticket | `<ref>` |
| Signed off by | `<name / role>` |
| Date (UTC) | `<YYYY-MM-DDThh:mm:ssZ>` |
