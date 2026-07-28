# FleetFlow — UAT Test Cases (Phase 4)

Each case records the required fields. **Actual result / Pass-Fail / Evidence /
Defect / Tester / Test date / Sign-off** are filled by the human tester during
execution. The **Automated dry-run** line records the real-HTTP scenario in
`backend/tests/test_uat_scenarios.py` (or the Phase 3 suite) that already proves
the happy path plus its key control — supporting evidence, not a substitute for
business sign-off.

Login as the seeded `uat_alpha_<role>` user unless noted. Cross-tenant cases use
`uat_bravo_org_admin`.

---

## UAT-01 — Organisation administrator and user management
* **Objective:** An admin can create, deactivate and reset users within their own org.
* **Role:** org_admin · **Preconditions:** Alpha seeded.
* **Test data:** a new user `uat_temp_ops` (operations).
* **Steps:** 1) Admin → Users → Add user (role operations). 2) Deactivate the user. 3) Reset password. 4) Attempt to set role to a platform/superuser value.
* **Expected:** Create/deactivate/reset succeed within the org; role escalation beyond org roles is refused; every change is audited.
* **Automated dry-run:** covered indirectly by role/enforcement tests; `test_authz_permissions.py`, `test_rbac_matrix.py`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-02 — Role and permission enforcement
* **Objective:** Each role can do only what its permission set allows.
* **Role:** viewer, driver, operations, accounts, admin · **Preconditions:** Alpha seeded.
* **Test data:** one vehicle.
* **Steps:** As viewer attempt to create a vehicle; as driver attempt to create a service; as operations attempt to approve an expense; as accounts approve an expense.
* **Expected:** Viewer create → 403; driver service → 403; operations approve → 403; accounts approve → 200.
* **Automated dry-run:** `test_uat_scenarios.py::test_uat02_role_enforcement` + `test_authz_enforcement.py`, `test_expense_settlement.py::test_data_entry_cannot_approve`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-03 — Vehicle onboarding and status management
* **Objective:** Add a vehicle and move it through operational/disposal states.
* **Role:** operations/admin · **Preconditions:** Alpha seeded.
* **Steps:** Create a vehicle; set to maintenance; attempt to un-dispose a sold vehicle.
* **Expected:** Create active; maintenance succeeds; un-disposing a sold vehicle is refused (409, WF-01).
* **Automated dry-run:** `test_uat_scenarios.py::test_uat03_vehicle_onboarding_and_status` + `test_workflow_transitions.py`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-04 — Driver onboarding, assignment and exit
* **Objective:** Add a driver, assign a vehicle, then exit (resign).
* **Role:** operations/admin.
* **Steps:** Create a driver; mark resigned; confirm the vehicle is unassigned and the driver cannot be assigned to a new trip.
* **Expected:** Create active; resign is management/admin-gated and terminal; exited driver rejected on new trip allocation.
* **Automated dry-run:** `test_uat_scenarios.py::test_uat04_driver_lifecycle` + `test_trip_operations.py::test_exited_driver_rejected`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-05 — Trip planning → assignment → dispatch → completion → settlement → closure
* **Objective:** Complete the full trip lifecycle.
* **Role:** operations (plan/assign/dispatch/complete), accounts (settle/close).
* **Steps:** Plan a trip; assign vehicle+driver; dispatch; complete with closing km; settle; finalize (close).
* **Expected:** planned → assigned → ongoing → completed → settlement_pending → closed; distance computed once; odometer forwarded; each step audited.
* **Automated dry-run:** `test_uat_scenarios.py::test_uat05_trip_full_lifecycle` + `test_trip_operations.py`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-06 — Vehicle or driver reassignment
* **Objective:** Reassign before dispatch freely; after dispatch requires authority + reason.
* **Role:** operations (before), management/admin (after).
* **Steps:** Reassign an assigned trip's vehicle; dispatch; as operations attempt reassign (expect 403); as admin reassign with a reason.
* **Expected:** Pre-dispatch reassign succeeds; post-dispatch reassign by operations → 403; by admin with reason → 200, audited as post-dispatch.
* **Automated dry-run:** `test_uat_scenarios.py::test_uat06_reassignment` + `test_trip_operations.py::test_reassign_after_dispatch_requires_authority`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-07 — Trip cancellation
* **Objective:** Cancel a pre-completion trip; resources are released.
* **Role:** operations.
* **Steps:** Cancel an ongoing trip; re-allocate the same vehicle/driver to a new trip.
* **Expected:** Cancel preserves history, releases the vehicle/driver; the new allocation succeeds; a completed trip cannot be cancelled.
* **Automated dry-run:** `test_uat_scenarios.py::test_uat07_trip_cancellation` + `test_trip_operations.py::test_cancellation_releases_vehicle_and_driver`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-08 — Expense submission, approval, rejection and payment
* **Objective:** Submit an expense, approve within submitted amount, and pay.
* **Role:** operations (submit), accounts (approve/pay).
* **Steps:** Submit an expense; approve ≤ submitted; pay ≤ approved outstanding; attempt to approve one's own submission (expect refusal); reject another and attempt to pay it.
* **Expected:** approve within amount; over-amount refused; payment within outstanding; self-approval 403; rejected unpayable.
* **Automated dry-run:** `test_uat_scenarios.py::test_uat08_expense_approve_pay_reverse` + `test_expense_settlement.py`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-09 — Driver advance and trip settlement
* **Objective:** Record an advance and view it netted in trip settlement.
* **Role:** operations (advance), accounts (settlement).
* **Steps:** Create an advance against a trip; open the trip settlement view.
* **Expected:** Settlement shows eligible expenses, approved, advances, payments and outstanding, reconciling with trip economics.
* **Automated dry-run:** `test_uat_scenarios.py::test_uat09_advance_and_settlement` + `test_expense_settlement.py::test_settlement_totals_and_reconciliation`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-10 — Payment reversal
* **Objective:** Reverse a payment; outstanding is restored, original preserved.
* **Role:** accounts.
* **Steps:** Pay an approved expense in full; reverse the payment; confirm outstanding restored and a fresh payment allowed.
* **Expected:** Reversal appends an event (original kept); paid_amount returns to 0; outstanding restored.
* **Automated dry-run:** `test_uat_scenarios.py::test_uat08_expense_approve_pay_reverse` + `test_expense_settlement.py::test_reversal_restores_outstanding`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-11 — Repair ticket lifecycle
* **Objective:** Walk a repair ticket open → closed with approval gating.
* **Role:** maintenance (transitions), management/admin (approve/close).
* **Steps:** Create a major repair; advance through under_review → approved → sent_for_repair → in_repair → repaired → closed; attempt an invalid jump.
* **Expected:** Valid transitions succeed; approval/close role-gated; invalid jump → 409; entering in_repair opens a downtime and sets the vehicle to maintenance.
* **Automated dry-run:** `test_uat_scenarios.py::test_uat11_repair_lifecycle` + `test_maintenance_operations.py`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-12 — Vehicle downtime and return to service
* **Objective:** Open and close a downtime; the vehicle returns to service.
* **Role:** maintenance.
* **Steps:** Create an open downtime; close it with reason; confirm days computed and the vehicle back to active; attempt a generic reopen.
* **Expected:** Close records reason/days; vehicle back to active; generic reopen refused (409).
* **Automated dry-run:** `test_uat_scenarios.py::test_uat12_downtime_return` + `test_maintenance_operations.py::test_downtime_cannot_be_reopened_generically`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-13 — Tyre fitment, transfer, removal and scrapping
* **Objective:** Manage a tyre through its lifecycle.
* **Role:** maintenance.
* **Steps:** Fit a tyre; transfer to another vehicle; scrap it; attempt to transfer a scrapped tyre; attempt to fit the same tyre number to two vehicles.
* **Expected:** Transfer preserves history; scrap is terminal; scrapped transfer refused; double-fit refused.
* **Automated dry-run:** `test_uat_scenarios.py::test_uat13_tyre_lifecycle` + `test_maintenance_operations.py`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-14 — Fuel and odometer entry
* **Objective:** Record fuel; the vehicle odometer forwards.
* **Role:** driver/operations.
* **Steps:** Add a fuel entry with odometer; confirm mileage computed and the master odometer forwarded; attempt a lower odometer.
* **Expected:** Fuel stored; odometer monotonic; mileage derived.
* **Automated dry-run:** `test_uat_scenarios.py::test_uat14_fuel_entry` + `test_di02_atomicity.py`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-15 — FASTag manual entry and demo-simulation isolation
* **Objective:** Manual FASTag entries update balance; simulation is demo-only.
* **Role:** accounts/admin.
* **Steps:** Add a toll and a recharge; confirm balance adjusts; on a non-demo org confirm the FASTag *sync/simulate* endpoint is refused.
* **Expected:** Manual entries adjust the balance; simulation fails closed outside the demo org.
* **Automated dry-run:** `test_fastag_simulation.py`, `test_di02_atomicity.py::test_fastag_balance_adjusted_after_transaction`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-16 — Document upload, replacement and expiry
* **Objective:** Upload a document, replace it (supersede), and see expiry surfaced.
* **Role:** operations/admin.
* **Steps:** Upload an Insurance doc; upload a newer one; confirm the old is superseded (history kept); confirm an expired mandatory doc appears in compliance/exceptions; attempt expiry before issue date.
* **Expected:** New doc current, old superseded; expired doc surfaced; expiry < issue refused (400).
* **Automated dry-run:** `test_uat_scenarios.py::test_uat16_document_supersede` + `test_compliance_claims.py`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-17 — Accident and insurance claim lifecycle
* **Objective:** Record an accident and walk the claim to settlement/closure.
* **Role:** operations (report), accounts/management (approve/settle).
* **Steps:** Report an accident; collect evidence → submit → survey; approve ≤ claim; settle ≤ approved; close; attempt over-settlement and a closed edit.
* **Expected:** Valid flow succeeds; ceilings enforced; settlement idempotent; closed claim locked.
* **Automated dry-run:** `test_uat_scenarios.py::test_uat17_accident_claim` + `test_compliance_claims.py`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-18 — Operational exceptions and alerts
* **Objective:** The exceptions feed surfaces pending work and supports acknowledgement.
* **Role:** operations/admin.
* **Steps:** Open the Dashboard exceptions panel; confirm open downtime / unapproved expense / expiring document appear; acknowledge one; resolve a source and confirm it drops.
* **Expected:** Items derived live; acknowledge flags without hiding; resolved item leaves the list.
* **Automated dry-run:** `test_uat_scenarios.py::test_uat18_exceptions_feed` + `test_operational_exceptions.py`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-19 — Reports, exports and reconciliation
* **Objective:** Ledger/reports totals reconcile with source data.
* **Role:** accounts/viewer.
* **Steps:** Open the expense ledger and reconciliation views; export a report; compare totals against underlying records.
* **Expected:** One canonical figure across dashboard/reports/exports; no double counting; rejected expenses excluded.
* **Automated dry-run:** `test_uat_scenarios.py::test_uat19_reconciliation_available` + `test_di03_reconciliation.py`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-20 — Cross-tenant isolation
* **Objective:** One org can never see or act on another org's data.
* **Role:** uat_bravo_org_admin vs Alpha.
* **Steps:** As Bravo admin, attempt to read/update an Alpha vehicle id; confirm Alpha records never appear in Bravo lists/exceptions.
* **Expected:** 404 (no existence disclosure); no cross-org data anywhere.
* **Automated dry-run:** `test_uat_scenarios.py::test_uat20_cross_tenant_isolation` + `test_tenant_isolation_matrix.py`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-21 — Session logout, expiry and revocation
* **Objective:** Logout ends the session; expired/revoked sessions are rejected.
* **Role:** any.
* **Steps:** Log in; log out; confirm subsequent API calls are 401; (admin) revoke a user's sessions and confirm rejection.
* **Expected:** Logout → 401 afterwards; revocation invalidates sessions.
* **Automated dry-run:** `test_uat_scenarios.py::test_uat21_session_logout` + `test_auth_sessions.py`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

## UAT-22 — File access and download security
* **Objective:** Files are tenant-scoped and served safely.
* **Role:** operations vs Bravo admin.
* **Steps:** Upload a file in Alpha; download it as Alpha; attempt to download the same file id as Bravo; inspect response headers.
* **Expected:** Cross-tenant download → 404; downloads carry nosniff + safe CSP + private cache; viewer cannot upload.
* **Automated dry-run:** `test_file_security.py`, `test_security_headers.py`.
* Actual: __ · Pass/Fail: __ · Evidence: __ · Defect: __ · Tester: __ · Date: __ · Sign-off: __

---

### Automated dry-run summary

`backend/tests/test_uat_scenarios.py` — **18 real-HTTP scenario tests, all
passing** — plus the referenced Phase 1–3 suites. Full backend regression at the
time of writing: **814 passed, 3 skipped**. Human execution and sign-off of the
cases above is still required for business acceptance.
