# FleetFlow — UAT Master Plan (Phase 4)

**Status:** Ready for business UAT. **Prepared:** 28 July 2026.
**Repository baseline:** `develop` @ Phase 3 closeout (`d028b18`), backend suite
814 passed / 3 skipped (796 + 18 automated UAT-scenario dry-runs).
**Scope discipline:** No new modules, integrations, analytics, AI, GPS or mobile
work. Phase 4 is acceptance testing and release-readiness only.

---

## 1. Purpose

Give business users a structured way to accept FleetFlow's operational workflows
before any production release, and to record the operator-led prerequisites that
remain. This plan defines the environment, data, scenarios, roles, defect rules,
and entry/exit criteria; the scenarios themselves are in `UAT_TEST_CASES.md`.

## 2. UAT environment

* **Isolated staging** running the same container image as production would, but
  pointed at a **staging database** (`DB_NAME=fleetflow_uat` or similar). Never
  the production database.
* **HTTPS** in front of the app; **CORS** set to the explicit staging origin
  (not `*`) so cookie auth works and is representative.
* **No production data.** All data comes from the synthetic seed (§4).
* **Secrets** are staging-only; production credential rotation (SEC-004) and
  Git-history cleanup (SEC-005) are **out of scope** here and tracked in the
  release gate.

### Bring-up

1. Deploy the current `develop` build to staging.
2. Configure `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS` (explicit), cookie/HTTPS.
3. Seed data: `DB_NAME=fleetflow_uat python -m uat_seed --wipe`
   (creates orgs *UAT Alpha* and *UAT Bravo*; prints synthetic logins).
4. Smoke check: log in as `uat_alpha_org_admin`, open the Dashboard, confirm the
   Operational Exceptions panel and seeded records render.

## 3. Roles and participants

| UAT role | App role | Responsibility |
| --- | --- | --- |
| Fleet owner / sponsor | owner | Final business sign-off |
| Operations lead | operations (data_entry) | Trips, dispatch, expenses submission |
| Accounts | accounts | Approvals, payments, settlements |
| Maintenance lead | maintenance | Repairs, downtime, tyres |
| Administrator | org_admin | Users, roles, org settings |
| Driver | driver | Field create (trip/fuel/repair) |
| Auditor | viewer | Read-only verification |

Each named seed user (`uat_alpha_<role>`) exists for Alpha; Bravo has an admin
only, used for cross-tenant isolation checks.

## 4. Test data

The synthetic seed (`backend/uat_seed.py`) creates two organisations with records
in every lifecycle state:

* Two orgs (Alpha full, Bravo minimal for isolation).
* Eight role logins (Alpha), synthetic random passwords printed at seed time.
* Vehicles: active, inactive, maintenance, sold.
* Drivers: active and resigned (exited).
* Trips: planned, assigned, ongoing, completed, settlement_pending, closed, cancelled.
* Expenses: submitted, approved (paid and unpaid), rejected — with a payment event.
* Advances: outstanding and recovered.
* Repairs: open, under_review, approved, in_repair (+ linked open downtime), closed; plus a closed downtime.
* Tyres: active, removed, scrapped (+ scrap event).
* Documents: valid, expiring soon, expired, and a superseded record.
* Accidents/claims: reported, approved, settled, closed.
* FASTag (toll + recharge) and fuel transactions.

**Data safety:** everything is marked `is_uat: True` under dedicated org ids,
uses throwaway passwords, and contains no real personal or confidential data.
`--wipe` removes only the UAT orgs.

## 5. Approach

* **Manual acceptance** of each scenario in `UAT_TEST_CASES.md` by the assigned
  role, recording actual result, pass/fail, evidence (screenshot/record id),
  defect ref, tester and date.
* **Automated dry-run** (`backend/tests/test_uat_scenarios.py`, 18 real-HTTP
  cases) proves each workflow completes end-to-end before humans start, so a
  failing scenario points to expectation/usability rather than plumbing. The
  automated result is recorded as *supporting evidence* per case, not as a
  substitute for business sign-off.

## 6. Defect classification

| Sev | Definition | Blocks sign-off? |
| --- | --- | --- |
| **P0** | Security, tenant leak, financial corruption or data loss | **Yes** |
| **P1** | A critical business workflow cannot be completed | **Yes** |
| P2 | Major inconvenience with a practical workaround | No |
| P3 | Cosmetic or minor usability issue | No |

Defects are logged in `UAT_DEFECT_LOG_TEMPLATE.md`. **Only P0/P1 block.** Fixes
are made on small isolated branches/PRs; a UAT defect is never a licence for UI
redesign, new modules, new integrations, advanced analytics, AI, GPS/route
optimisation, accounting integration or a mobile app.

## 7. Entry criteria

* Phase 3 merged; backend suite green (814/3).
* Staging deployed with HTTPS + explicit CORS.
* Synthetic seed loaded.
* Automated UAT dry-run green.

## 8. Exit criteria

* Every scenario executed and recorded.
* No open P0 or P1 defects.
* `UAT_SIGNOFF_TEMPLATE.md` completed by the business owner.
* Outcome recorded in `RELEASE_READINESS_GATE.md` as PASSED / CONDITIONALLY
  PASSED / FAILED.

## 9. Out of scope (unchanged from the programme scope limits)

Production access, production data, SEC-004, SEC-005, `main` changes, new
features, and all excluded integrations remain out of scope for Phase 4.
