# FleetFlow — Release Readiness Gate (Phase 4)

**Date:** 28 July 2026 · **Build:** `develop` @ Phase 3 closeout (`d028b18`),
plus Phase 4 UAT support on `feature/uat-release-readiness`.
**Scope:** repository UAT enablement + release-readiness recording. No production
access; `main` untouched; SEC-004/SEC-005 not performed.

This gate consolidates business UAT status and the operator-led production
prerequisites into one go/no-go record. It sits alongside — and does not
supersede — `SECURITY_RELEASE_GATE.md`, `DATA_INTEGRITY_RELEASE_GATE.md` and
`OPERATIONS_RELEASE_GATE.md`.

---

## 1. Prerequisite status board

| # | Prerequisite | Owner | Status |
| --- | --- | --- | --- |
| 1 | Business UAT execution & sign-off | Business owner | **Automated dry-run PASSED; human sign-off PENDING** |
| 2 | SEC-004 production credential rotation | Operator (security) | Not started (out of Phase 4 scope) |
| 3 | SEC-005 Git-history cleanup | Operator (security) | Not started (out of Phase 4 scope) |
| 4 | Production backup & restore verification | Operator (ops) | Not started |
| 5 | Production data-integrity scan (on a copy) | Operator (ops) | Not started |
| 6 | Required production data repairs | Operator (ops) | Not started |
| 7 | Production environment configuration | Operator (ops) | Not started |
| 8 | CORS & HTTPS configuration | Operator (ops) | Not started |
| 9 | Branch protection & required CI checks | Operator (ops) | Not started |
| 10 | File ownership migration verification | Operator (ops) | Not started |
| 11 | Deployment & rollback procedure | Operator (ops) | Not started |
| 12 | Recovery administrator verification | Operator (security) | Not started |
| 13 | Final business-owner sign-off (production) | Business owner | Not started |

Items 2–13 are operator/business activities that this repository phase is
explicitly forbidden from performing. They are enumerated here and tracked in
`GO_LIVE_CHECKLIST.md`.

## 2. Repository-side UAT readiness — evidence

| Criterion | Result |
| --- | --- |
| Synthetic staging seed (`backend/uat_seed.py`) | Two orgs, every lifecycle state; verified to seed cleanly on a disposable db |
| UAT master plan / test cases / templates / checklist | Authored (`docs/uat/`) — 22 scenarios with required fields |
| Automated UAT scenario dry-run (`test_uat_scenarios.py`) | **18 real-HTTP scenarios, all pass** |
| Full backend regression | **814 passed, 3 skipped** |
| Existing security & data-integrity tests | Green (no weakening/skips) |
| Ruff (changed files) / Python compile / Gitleaks | Clean |
| P0/P1 UAT defects from the dry-run | **None** |

The automated dry-run exercises org/role enforcement, the full trip lifecycle,
reassignment, cancellation, expense approve/pay/reverse, advance & settlement,
repair lifecycle, downtime return, tyre lifecycle, fuel/odometer, document
supersede, accident/claim, exceptions, reconciliation availability, cross-tenant
isolation and session logout — end to end, all green.

## 3. Decision

```
UAT PASSED — technically ready for operator-led production prerequisites
```

**What this means.** Every critical business workflow completes end-to-end on the
current build; the automated UAT dry-run is green with no P0/P1 defects; the UAT
framework, synthetic data and templates are in place for business users to
execute and sign off. The repository is therefore **technically ready** to enter
the operator-led production prerequisites.

**What this does NOT mean.** It is **not** a production go-live authorisation.
Production release remains **blocked** until, at minimum:

* **Business UAT is executed and signed off by real users** (§1 item 1 — the
  automated dry-run is supporting evidence, not a substitute for human
  acceptance);
* **SEC-004** and **SEC-005** are completed and verified;
* **production data** is backed up, integrity-scanned on a copy, reconciled and
  repaired as needed;
* production **environment/config, branch protection, deployment/rollback and
  recovery-admin** verifications (§1 items 7–12) are complete;
* the **final business-owner production sign-off** (§1 item 13) is recorded.

## 4. Recommended sequence to go-live

1. Execute the manual UAT scenarios on staging; log defects; fix P0/P1 via small
   isolated PRs; obtain business sign-off (`UAT_SIGNOFF_TEMPLATE`).
2. Complete SEC-004 and SEC-005 (operator-led).
3. Run the production data prerequisites on a copy; sign off drift; apply repairs.
4. Verify environment/config, branch protection, deployment/rollback,
   recovery-admin (`GO_LIVE_CHECKLIST`).
5. Convene a combined go/no-go across the security, data-integrity, operations
   and this readiness gate; record the final production decision here.
