# FleetFlow — UAT Sign-off (Template)

Complete at the end of the UAT cycle. Sign-off requires **no open P0 or P1
defects** and every scenario executed.

## Cycle details

* UAT cycle / date range: ____
* Build under test: `develop` @ ________
* Staging environment: ____ (DB, HTTPS, CORS confirmed)
* Seed loaded: `uat_seed` (UAT Alpha + UAT Bravo) — Yes / No

## Scenario results

| Case | Title | Pass/Fail | Tester | Date |
| --- | --- | --- | --- | --- |
| UAT-01 | Org admin & user management | | | |
| UAT-02 | Role & permission enforcement | | | |
| UAT-03 | Vehicle onboarding & status | | | |
| UAT-04 | Driver onboarding, assignment & exit | | | |
| UAT-05 | Trip full lifecycle | | | |
| UAT-06 | Reassignment | | | |
| UAT-07 | Trip cancellation | | | |
| UAT-08 | Expense submit/approve/reject/pay | | | |
| UAT-09 | Advance & settlement | | | |
| UAT-10 | Payment reversal | | | |
| UAT-11 | Repair ticket lifecycle | | | |
| UAT-12 | Downtime & return to service | | | |
| UAT-13 | Tyre fitment/transfer/removal/scrap | | | |
| UAT-14 | Fuel & odometer | | | |
| UAT-15 | FASTag manual & demo isolation | | | |
| UAT-16 | Document upload/replace/expiry | | | |
| UAT-17 | Accident & claim lifecycle | | | |
| UAT-18 | Operational exceptions & alerts | | | |
| UAT-19 | Reports, exports & reconciliation | | | |
| UAT-20 | Cross-tenant isolation | | | |
| UAT-21 | Session logout/expiry/revocation | | | |
| UAT-22 | File access & download security | | | |

## Defect position

* Open P0: __ · Open P1: __ · Open P2: __ · Open P3: __
* Reference: `UAT_DEFECT_LOG_<cycle>.md`

## Decision

Select one:

- [ ] **UAT PASSED** — all scenarios pass, no open P0/P1.
- [ ] **UAT CONDITIONALLY PASSED** — listed P1 items remain (enumerate below).
- [ ] **UAT FAILED** — critical workflow or security defects remain.

Conditional/failed notes: ____

## Business owner sign-off

| Name | Role | Signature | Date |
| --- | --- | --- | --- |
| | Fleet owner / sponsor | | |
| | Operations lead | | |
| | Accounts | | |
| | Administrator | | |

> Sign-off here authorises proceeding to the **operator-led production
> prerequisites** in `GO_LIVE_CHECKLIST.md`. It does **not** by itself authorise
> production release — see `RELEASE_READINESS_GATE.md`.
