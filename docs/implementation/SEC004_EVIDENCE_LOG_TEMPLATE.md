# SEC-004 — Evidence Log (Template)

Copy this file for each production run (e.g. `SEC004_EVIDENCE_2026-xx-xx.md`),
fill every field, and retain it with the change record.

> **NEVER record in this log:** passwords, password hashes, session tokens, Mongo
> connection strings (`MONGO_URL`), or encryption keys. Record **references**
> (a backup path/label, a user_id, a count) — never a secret value. This template
> deliberately provides **no field** for any of those.

---

## 1. Change identification

| Field | Value |
| --- | --- |
| Change reference / ticket | |
| Date (UTC) | |
| Maintenance window (start–end, UTC) | |
| Operator (name / id) | |
| Reviewer (name / id) | |
| Environment identifier (e.g. `prod-eu-1`) | |
| Application version / commit | |

## 2. Pre-flight (Section 0)

| Field | Value / Result |
| --- | --- |
| Confirmed production host (not preview/dev) | Yes / No |
| `MONGO_URL` present (value NOT recorded) | Yes / No |
| `DB_NAME` (name only) | |
| Confirmed NOT localhost / NOT `test_database` | Yes / No |
| `mongodump` / `mongorestore` / Python deps present | Yes / No |
| Free disk at backup destination | |
| Backend restart method (as confirmed) | |
| Health-check URL | |
| Health check BEFORE change | Pass / Fail |
| Recovery-admin access confirmed BEFORE change | Yes / No |

## 3. Backup (Section 1)

| Field | Value / Result |
| --- | --- |
| Backup location **reference** (path/label, not contents) | |
| Backup secured (restricted, encrypted at rest) | Yes / No |
| `users.bson` present and non-empty | Yes / No |
| `user_sessions.bson` present and non-empty | Yes / No |
| Backup verification result | Pass / Fail |
| `users` document count (live) | |
| `user_sessions` document count (live) | |

## 4. Discovery and manifest (Sections 2–3)

| Field | Value / Result |
| --- | --- |
| Discovered legacy-account count | |
| Manifest actions count (must equal above) | |
| Manifest exhaustive (every legacy account once) | Yes / No |
| No demo account in manifest | Confirmed Yes / No |
| Manifest review sign-off (reviewer) | |
| Affected organisation IDs | |
| Recovery-admin `user_id` per affected org | |
| Dry-run reviewed and accepted | Yes / No |

## 5. Actions applied (Section 4)

Per account (add rows as needed — **user_id and action only, no secrets**):

| user_id | org_id | Action (rotate/deactivate/skip) | Outcome (ok/failed) | Sessions revoked |
| --- | --- | --- | --- | --- |
| | | | | |
| | | | | |

| Field | Value / Result |
| --- | --- |
| Password rotation success / failure (count) | |
| Deactivation success / failure (count) | |
| Total sessions revoked | |
| `failed` count (must be 0) | |

## 6. Restart and verification (Sections 5–6)

| Field | Result |
| --- | --- |
| Backend restart | Pass / Fail |
| Health check AFTER restart | Pass / Fail |
| Recovery-admin login (each affected org) | Pass / Fail |
| Old / leaked passwords rejected (401) | Pass / Fail |
| Old sessions rejected (401) | Pass / Fail |
| Deactivated accounts cannot log in | Pass / Fail |
| Demo login / behaviour unchanged | Pass / Fail |
| `security_audit` has one record per action, no secrets | Pass / Fail |
| No unexpected database changes observed | Pass / Fail |

## 7. Close-out (Section 7)

| Field | Value / Result |
| --- | --- |
| Rollback required | Yes / No |
| If rollback: reason (stop-condition number) | |
| Temporary manifest / working files securely deleted | Yes / No |
| Backup retention decision | Retain / Delete |
| Backup retention or deletion date | |
| `SECURITY_EXECUTION_STATUS.md` updated | Yes / No |

## 8. Sign-off

| Role | Name / id | Date (UTC) | Signature / approval ref |
| --- | --- | --- | --- |
| Operator | | | |
| Reviewer | | | |

**Outcome:** SEC-004 production credential rotation — **Completed / Rolled back**
(circle one). If completed and independently verified, SEC-005 may be planned
(separately gated).
