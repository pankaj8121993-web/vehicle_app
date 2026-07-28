# FleetFlow — UAT Defect Log (Template)

Copy this file per UAT cycle (e.g. `UAT_DEFECT_LOG_2026-08.md`). Log every defect
found during UAT. **Only P0 and P1 block sign-off.**

## Severity legend

| Sev | Definition | Blocks sign-off |
| --- | --- | --- |
| P0 | Security, tenant leak, financial corruption or data loss | Yes |
| P1 | A critical business workflow cannot be completed | Yes |
| P2 | Major inconvenience with a practical workaround | No |
| P3 | Cosmetic or minor usability issue | No |

## Log

| Defect ID | UAT case | Severity | Summary | Steps to reproduce | Expected | Actual | Environment / build | Reported by | Date | Status (Open/Fixed/Verified/Deferred) | Fix branch / PR | Verified by | Verified date |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DEF-001 | UAT-__ | P_ | | | | | develop @ ____ | | | Open | | | |
| DEF-002 | | | | | | | | | | | | | |

## Handling rules

* Fix P0/P1 via a **small, isolated branch and PR** against `develop`; add or
  extend an automated test that fails before the fix and passes after.
* A UAT defect must **not** be used to justify UI redesign, new modules, new
  integrations, advanced analytics, AI, GPS/route optimisation, accounting
  integration or mobile-app development. Record such requests as future backlog,
  not Phase 4 work.
* P2/P3 defects are recorded and triaged into the normal backlog; they do not
  block sign-off.

## Summary (fill at cycle close)

* Open P0: __ · Open P1: __ · Open P2: __ · Open P3: __
* Sign-off blocked: **Yes / No** (blocked only if any open P0 or P1)
