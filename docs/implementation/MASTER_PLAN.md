# FleetFlow - Upgradation & Security Enhancement Master Implementation Plan

**App:** FleetFlow - Complete Fleet Operations Management  
**Prepared for:** Pankaj Jain / FleetFlow Product Team  
**Version:** 1.0  
**Date:** 14 July 2026  
**Status:** Internal implementation and release-governance document

> This document consolidates the live QA review, product specification, static code/security review, and the full path to a 10/10 production release.


---


# 0. Document Control and How to Use This Plan

| Field | Detail |
| --- | --- |
| Purpose | Provide one complete, implementation-ready plan for upgrading FleetFlow to a secure, reliable, multi-company SaaS product. |
| Primary audience | Pankaj Jain, Emergent, Claude Code, QA engineers, security reviewers, and future development partners. |
| Source inputs | Live product walkthrough dated 14 July 2026; FleetFlow Master Product Spec; static review of the current GitHub codebase; prior product instructions and UI references. |
| Scope | Application architecture, security, multi-tenancy, workflow integrity, UI/UX, mobile, expense intelligence, onboarding, platform owner controls, billing readiness, testing, deployment, and production operations. |
| Document priority | This document supersedes scattered prompts and earlier partial reviews for the purpose of planning and execution. |
| Change rule | Any scope change must be added to this document or the tracked backlog with owner, priority, acceptance criteria, and test evidence. |

> **Important interpretation**  
> FleetFlow has approximately 7/10 product-feature depth, but only about 4.5/10 production and security readiness. The difference is intentional: many valuable modules exist, but critical controls must be strengthened before real customer data or commercial release.


## 0.1 Reading sequence

- Sections 1-5 explain the current position, risks, and immediate priorities.
- Sections 6-19 define the target product, architecture, security controls, workflows, UI/UX, and operations.
- Sections 20-24 define testing, migration, implementation sequencing, and release governance.
- The appendices provide an implementation backlog, security test matrix, permission model, and final release checklist.


## 0.2 Non-negotiable execution rule

> **Do not begin with cosmetic redesign alone**  
> Phase 0 and Phase 1 security, tenant isolation, credential rotation, file isolation, authorization, and workflow protections must be completed before FleetFlow is treated as a production SaaS application. UI work may proceed in parallel only where it does not delay critical fixes.


## 0.3 Status legend

| Priority | Meaning | Release treatment |
| --- | --- | --- |
| P0 - Critical | Possible data exposure, account compromise, financial corruption, or tenant-isolation failure. | Must be fixed and independently verified before any production release. |
| P1 - High | Major workflow bypass, incorrect reporting, broken core experience, or significant operational risk. | Required before beta with real customer data. |
| P2 - Medium | Usability, scalability, consistency, and incomplete management controls. | Complete before general availability. |
| P3 - Enhancement | Differentiation, integrations, automation, and commercial expansion. | Prioritise after the core product is stable. |


---


# Contents

1. 1. Executive Direction and Reconciled Assessment
2. 2. Product Goals and Non-Negotiable Principles
3. 3. Immediate Release Freeze and Critical Actions
4. 4. Consolidated Findings and Defect Register
5. 5. Target Product and Technical Architecture
6. 6. Security Enhancement Programme
7. 7. Data Integrity and Closed Workflow Design
8. 8. Multi-Company SaaS and Organisation Onboarding
9. 9. Platform Owner Control Plane
10. 10. Subscription, Entitlement, and Billing Readiness
11. 11. UI/UX, Design System, and Accessibility
12. 12. Search, Filters, Data Grids, Reports, and Exports
13. 13. Expense Intelligence and Financial Controls
14. 14. Mobile, Driver Experience, and Offline PWA
15. 15. Performance, Scalability, and Data Architecture
16. 16. Integrations, Notifications, and Automation
17. 17. Internationalisation and Localisation
18. 18. Observability, DevOps, Backup, and Operations
19. 19. Testing and Quality Assurance Strategy
20. 20. Data Migration, Deployment, and Rollback
21. 21. Phased Implementation Roadmap
22. 22. Definition of Done and Production Release Gates
23. 23. Instructions for Emergent and Claude Code
24. 24. Traceability Matrix
25. Appendix A. Prioritised Implementation Backlog
26. Appendix B. Security and Tenant-Isolation Test Matrix
27. Appendix C. Role and Permission Model
28. Appendix D. Final Release Checklist


---


# 1. Executive Direction and Reconciled Assessment

FleetFlow is already more than a simple vehicle register. It contains a broad operating system for fleet management: landing and demo experience, multi-step onboarding, dashboards, fleet status, vehicles, drivers, trips, fuel, maintenance, repair tickets, tyres, accidents, FASTag, downtime, compliance, calendar, expenses, budgets, analytics, reports, vendors, user roles, global search, PWA installation, and demo data.

The correct strategy is therefore not to rebuild the application from zero. The correct strategy is to preserve working modules, repair broken wiring, harden security and data isolation, redesign the generic CRUD layer into domain-safe workflows, improve the interface, and add a proper SaaS platform layer.


## 1.1 Reconciled scorecard

| Dimension | Current assessment | Target | Comment |
| --- | --- | --- | --- |
| Feature breadth | 7.0/10 | 9.5/10 | Strong module coverage; several workflows need closure and integrations. |
| Core usability | 5.5/10 | 9.5/10 | Broken row navigation, inconsistent actions, validation, and mobile behaviour reduce confidence. |
| Visual design | 5.0/10 | 9.5/10 | Landing is stronger than the application interior; no unified design system. |
| Multi-company readiness | 4.0/10 | 10/10 | Tenant wrapper exists, but field-level and file-level isolation require hardening. |
| Security readiness | 2.5/10 | 9.5/10 | Hardcoded credentials, token storage, CORS, upload controls, and authorization must be remediated. |
| Data integrity | 4.0/10 | 9.5/10 | Generic CRUD can bypass domain workflows and side effects are not always reversible. |
| Performance and scale | 4.0/10 | 9.0/10 | Heavy pages freeze; N+1 queries and record caps can produce slow or incomplete results. |
| Testing and release maturity | 4.0/10 | 9.5/10 | Some RBAC tests exist; comprehensive tenant, security, workflow, visual, load, and recovery tests are missing. |
| Overall production readiness | 4.5/10 | 9.5/10 | Suitable as an advanced prototype, not yet safe for commercial production. |


## 1.2 Highest-leverage conclusion

> **Preserve the product, replace unsafe plumbing**  
> The detail screens, analytics, and many modules are valuable. The largest gains come from: secure tenant isolation; action-level permissions; workflow state machines; unified data validation; server-side search; mobile design; and a consistent design system.


## 1.3 What a successful end-state looks like

- A company or individual fleet owner can create a workspace, verify identity, complete guided onboarding, and start using FleetFlow without developer assistance.
- Every record, file, report, background job, search result, and export is restricted to the authenticated organisation and permitted branch or scope.
- Every process has a closed lifecycle with allowed transitions, approvals, audit history, reversals, and exception handling.
- The platform owner has a completely separate control plane for organisations, subscriptions, support, feature flags, system health, and audited impersonation.
- Desktop, tablet, and mobile experiences are intentionally designed rather than merely responsive by accident.
- FleetFlow can be monitored, backed up, restored, tested, deployed, and rolled back in a predictable manner.


# 2. Product Goals and Non-Negotiable Principles


## 2.1 Product goals

- Make FleetFlow a secure multi-company SaaS platform that can serve Rajguru Foods and external organisations without data mixing.
- Provide complete visibility of fleet utilisation, cost, compliance, maintenance, driver activity, and operational exceptions.
- Reduce manual spreadsheets, missed renewals, duplicate expenses, incorrect odometers, and uncontrolled repair spending.
- Make the product usable by owners, managers, operations teams, maintenance teams, accounts staff, drivers, auditors, and platform administrators.
- Create a strong Indian-market foundation with GST-aware expenses, WhatsApp-first alerts, Indian languages, and future Razorpay billing.
- Maintain an architecture that can later support GPS, FASTag providers, fuel cards, OCR, predictive maintenance, APIs, and white-labelling.


## 2.2 Non-negotiable engineering principles

| Principle | Required behaviour |
| --- | --- |
| Server is the authority | Frontend visibility is never treated as security. Every permission, tenant rule, workflow transition, limit, and financial calculation is enforced by the backend. |
| Organisation context is session-derived | The server determines org_id from the authenticated session. Clients cannot select, inject, update, or transfer organisation ownership. |
| Domain actions replace generic status edits | Statuses, approvals, payments, disposal, trip closure, and repair stages are changed only through dedicated action endpoints. |
| Financial records are traceable and reversible | Every monetary entry has a source, duplicate key, approval state, payment state, audit trail, and reversal mechanism. |
| No fabricated live data | Simulated FASTag, GPS, OCR, or provider results are restricted to demo workspaces and are clearly labelled. |
| No open process flows | Every process defines start, validation, assignment, approval, completion, cancellation, rejection, reversal, and archival. |
| Secure by default | New endpoints, fields, files, roles, exports, and integrations are private and restricted unless explicitly allowed. |
| Evidence-based release | A task is not complete because code was written. It is complete only after tests, screenshots, logs, migration evidence, and acceptance criteria pass. |
| Performance is a feature | No page may freeze for tens of seconds; no report may silently truncate; heavy processing runs asynchronously. |
| Accessibility and mobile are core | Keyboard, screen-reader, touch, small-screen, and low-bandwidth use cases are part of the acceptance criteria. |


# 3. Immediate Release Freeze and Critical Actions

> **Production freeze recommendation**  
> Do not onboard external paying customers or load sensitive third-party data until the P0 controls below are completed and verified. Internal controlled testing may continue in isolated non-production environments.


## 3.1 Actions to complete immediately

| ID | Action | Owner | Deadline |
| --- | --- | --- | --- |
| P0-01 | Rotate all currently known/default passwords and revoke every active session. | Security owner | Within 24 hours |
| P0-02 | Remove hardcoded production users and passwords from source code, seeds, test reports, screenshots, and documentation. | Backend | Within 24 hours |
| P0-03 | Disable simulated FASTag sync outside the dedicated demo tenant. | Backend | Within 24 hours |
| P0-04 | Restrict CORS to approved development, staging, and production origins. | Backend/DevOps | Within 24 hours |
| P0-05 | Take a verified database and object-storage backup before structural changes. | DevOps | Within 24 hours |
| P0-06 | Block org_id, role, is_admin, approval fields, audit fields, and protected status fields from generic update bodies. | Backend | Sprint 1 |
| P0-07 | Add organisation ownership to file records and enforce file download access by organisation and linked record. | Backend | Sprint 1 |
| P0-08 | Create automated tenant-isolation tests for every resource and HTTP method. | QA/Security | Sprint 1 |
| P0-09 | Add action-level authorization checks to every mutating endpoint. | Backend | Sprint 1 |
| P0-10 | Move authentication away from persistent bearer tokens in localStorage to secure session cookies. | Backend/Frontend | Sprint 1-2 |


## 3.2 Environment controls

- [ ] Create separate development, staging, demo, and production databases, storage namespaces, secrets, domains, and analytics projects.
- [ ] Prevent test and demo users from authenticating against the production organisation database.
- [ ] Disable debug output, auto-seeding, fake integrations, and permissive CORS in production.
- [ ] Make database migrations explicit, versioned, idempotent, reversible where possible, and logged.
- [ ] Enable branch protection and require tests before merging to the production branch.


# 4. Consolidated Findings and Defect Register

> **SEC-001 progress (code portion complete; not the full SEC-01 lifecycle).**
> Delivered on `feature/sec-001-secure-bootstrap`:
> - Removed hardcoded default users/passwords and all startup user seeding from `backend/server.py`.
> - Removed automatic creation of the hardcoded default organisation at startup (the org id is retained solely for the existing legacy migration).
> - Added `backend/bootstrap.py`: a manual, one-time first-admin provisioning command that refuses unless the database has zero users, requires explicit inputs, has no default password, and hashes with the app's bcrypt utility. Documented in `docs/implementation/BOOTSTRAP.md`.
> - Replaced the `username == "admin"` deletion guard with an org-scoped "last active org_admin" rule in `backend/auth.py`.
> - Redacted committed credentials from tests, reports and `memory/test_credentials.md`; live-URL tests now read credentials from environment variables and skip when absent.
> - Added focused unit tests in `backend/tests/test_bootstrap.py`.
>
> **Still outstanding for SEC-01 (separate operational work, NOT done here):**
> rotating any already-seeded live passwords, revoking existing sessions,
> disabling obsolete test accounts, Git-history secret cleanup, and full secret
> scanning. The demo feature is unchanged.

> **SEC-002 progress (tooling complete; production execution still pending).**
> Delivered on `feature/sec-002-credential-rotation`:
> - Added `backend/rotate_legacy_credentials.py`: an auditable, dry-run-by-default
>   management command that rotates or deactivates ONLY the legacy
>   `created_by:"system"` accounts and revokes their sessions, driven by a
>   reviewed no-password **exhaustive** manifest. It hashes with the app bcrypt,
>   sets `must_change_password`, enforces **per-organisation** administrator-lockout
>   protection (recovery admin declared by exact `user_id`, validated to belong to
>   each affected organisation; an admin in another org can never satisfy it),
>   excludes demo accounts with multiple markers, and writes non-secret
>   `security_audit` records.
> - Added `docs/implementation/CREDENTIAL_ROTATION.md` (backup/verify/apply/restart/
>   rollback runbook) and focused tests in `backend/tests/test_rotate_legacy_credentials.py`.
> - **NOT done:** the actual production rotation/session-revocation run (requires a
>   maintenance window, verified backup, operator manifest and backend restart),
>   Git-history cleanup, and full secret scanning. No production data was touched.

> **SEC-003 progress (secret scanning in place; history rewrite prepared, not executed).**
> Delivered on `feature/sec-003-secret-scanning`:
> - Added automated secret scanning with **gitleaks pinned to v8.30.1** (checksum-verified):
>   CI workflow `.github/workflows/secret-scan.yml` (push + PR, third-party actions
>   pinned by SHA) and a local `scripts/scan-secrets.sh` helper, governed by a narrow,
>   justified `.gitleaks.toml` allowlist.
> - Added a deterministic self-test (`backend/tests/test_secret_scanning.py` +
>   `backend/tests/fixtures_secret_scan/`) proving safe fixtures pass and a dummy
>   secret is detected, and that the tracked tree scans clean.
> - Hardened `.gitignore` for env files, DB dumps/backups, rotation manifests and key material.
> - Added `docs/implementation/SECRET_SCANNING.md`: detection, response, rotation linkage,
>   a redacted historical inventory, and a **prepared** Git-history cleanup procedure.
> - **Inventory (redacted):** the tracked tree scans clean; the legacy default-password
>   category still exists in pre-SEC-001 history and requires a future, approved history
>   rewrite (contributor-coordinated force-push) — **not executed** in SEC-003.
> - Contributes to OPS-001 (secret scanning clean); AUTH-001 secret-scan evidence.

> **SEC-004 — BLOCKED: OPERATOR-LED PRODUCTION ACTIVITY (open P0 release blocker).**
> Rotating the live legacy `created_by:"system"` credentials and revoking their
> sessions requires a genuine production operator environment. The Emergent preview
> container is **not** one: it reaches only a local `mongod` (`test_database`) inside
> itself. SEC-004 will be executed separately by an operator using the merged
> `CREDENTIAL_ROTATION.md` runbook. **Not executed. No production data accessed.**

> **SEC-005 — BLOCKED BY SEC-004: OPERATOR-LED DESTRUCTIVE ACTIVITY (open P0 release blocker).**
> The Git-history rewrite is preconditioned on SEC-004 succeeding (old passwords
> invalid, old sessions revoked). Rewriting history while those values are still
> live would destroy the record of what needs rotating. **Not executed.**

> **TEN-01 progress (repository work complete; PR open).**
> Delivered on `feature/ten-01-tenant-ownership`:
> - **Fixed a P0 cross-tenant write defect:** six generic update endpoints filtered
>   request bodies with hand-written denylists that all omitted `org_id`, while
>   `TenantCollection` scoped only the update *filter*, not the update *document*.
>   An authenticated user could transfer their own record into another organisation
>   via `PUT /api/<resource>/{id}` with `{"org_id": "<victim-org>"}`. `insert_one`
>   also used `setdefault("org_id", ...)`, letting a client-supplied owner win.
> - Added `backend/tenant_policy.py`: one canonical protected-field policy replacing
>   the scattered denylists, covering ownership, identity, audit, security, isolation
>   marker, branch, version, workflow and derived fields.
> - Ownership is now **forced** from authenticated session context on insert, and any
>   update writing an ownership field is refused fail-closed (`TenantViolation`).
> - Protected fields are **rejected** (HTTP 400 naming the field, never its value)
>   rather than silently stripped. Legitimate paths keep explicit, declared exceptions.
> - Added `docs/implementation/TENANT_OWNERSHIP.md` and 106 tests
>   (`backend/tests/test_tenant_ownership.py`). Full suite: 172 passed, 3 skipped.
> - **NOT done here:** `status` on generic updates and dedicated transition endpoints
>   (WF-01), file isolation (FILE-01), action-level permissions (AUTHZ-01), the full
>   cross-tenant HTTP matrix (TEN-TEST), branch scoping and optimistic locking.

> **FILE-01 progress (repository work complete; PR open).**
> Delivered on `feature/file-01-tenant-file-security`:
> - **Fixed a P0 cross-tenant file-disclosure defect:** `files` was absent from
>   `TENANT_COLLECTIONS`, so file records carried no `org_id` and
>   `GET /api/files/{file_id}` matched on id alone. Any authenticated user of any
>   organisation could download any other organisation's file — RC books, insurance
>   documents, Aadhaar scans, accident photos — given only a file id, and ids are
>   returned in ordinary API responses.
> - Also fixed: Content-Disposition header injection and stored XSS (unsanitised
>   filename + client-declared content type + `inline` disposition, no `nosniff`);
>   traversal-shaped storage paths; no file-signature validation; unrestricted file
>   types; size limit applied only after buffering the whole body; no integrity hash.
> - Added `backend/file_policy.py`: type allowlist, magic-byte detection,
>   filename sanitisation, server-generated org-namespaced storage names, safe
>   Content-Disposition, SHA-256 integrity.
> - Downloads force `attachment` for everything except images, with `nosniff`,
>   a restrictive CSP and `no-store`.
> - **Migration:** files are excluded from the blanket `DEFAULT_ORG_ID` backfill,
>   which would have handed every organisation's files to the default org.
>   `_migrate_file_org_ids()` derives the real owner from each file's uploader;
>   unresolvable files are quarantined fail-closed. Not run against production.
> - Added `docs/implementation/FILE_SECURITY.md` and 76 tests
>   (`backend/tests/test_file_security.py`). Full suite: 248 passed, 3 skipped.
> - **NOT done here:** malware scanning (no infrastructure), short-lived signed URLs
>   (single app-wide storage key), linked-record permissions (AUTHZ-01), branch
>   scope, orphaned-object reaping.

> **AUTH-01 progress (repository work complete; PR open).**
> Delivered on `feature/auth-01-secure-sessions`:
> - **Fixed P0 session defects:** tokens were stored in the database **in plaintext**
>   (any dump/backup/injection yielded live sessions); the token was returned in the
>   login body and held in `localStorage` (one XSS = persistent account takeover);
>   sliding expiry had **no absolute cap** (a stolen token lived forever if used);
>   tokens were never rotated (session fixation, stale privilege after role change);
>   `reset_password` did not evict the session cache; no login throttling;
>   `allow_credentials=True` with wildcard CORS origins.
> - Sessions are now identified by SHA-256 hash, delivered in an HttpOnly cookie,
>   protected by double-submit CSRF on cookie-authenticated writes, bounded by
>   independent idle (12h) and absolute (7d) clocks, and rotated on login and
>   password change. One revocation path flips the flag *and* evicts the cache.
> - Login throttling per username **and** per IP; non-enumerating errors with a
>   bcrypt verify even for unknown users so timing does not leak.
> - TTL indexes reap expired sessions and login attempts. CORS credentials only
>   with an explicit allowlist.
> - Frontend no longer stores any token; revalidates on route change, tab focus and
>   back/forward-cache restore.
> - **Migration:** pre-hashing sessions are revoked, **not rehashed** — hashing an
>   already-exposed token would keep it working. Users sign in once. Bearer tokens
>   remain accepted so newly-issued tokens keep working.
> - Added `docs/implementation/AUTHENTICATION.md` and 56 tests. Full suite: 304
>   passed, 3 skipped. A live smoke test verified CSRF blocks forged writes and
>   revoke-all is immediate — and caught two real bugs unit tests missed.
> - **NOT done here:** self-service password reset (no mail transport — open item),
>   organisation suspension (concept does not exist), removal of the bearer
>   fallback, frontend test harness.

> **TEN-TEST progress (repository work complete; PR open).**
> Delivered on `feature/ten-test-isolation-matrix`:
> - 188 tests driving **real HTTP against the real app with two real organisations**
>   in a dedicated disposable database, authenticating by cookie + CSRF exactly as
>   the frontend does. TEN-01/FILE-01/AUTH-01 had only been proven at the mechanism
>   level (fakes, source guards); a route that forgot to use the tenant-scoped `db`
>   would have passed all of them and still leaked.
> - A `RESOURCE_REGISTRY` drives every case; a guard test fails the build when a new
>   tenant-scoped collection is added without isolation coverage.
> - Covers list/read/create-with-injected-ownership/update/delete/transfer, search,
>   dashboard, reports, **exports**, drilldowns, calendar, compliance, files,
>   sessions, and org/user administration. Asserts **404 not 403**, and that a real
>   cross-tenant id and a random id return byte-identical responses.
> - **Found two real defects, both fixed here:** `auth._resolve_session` resolved the
>   user through the tenant-scoped `db.users`, so it depended on ambient
>   `current_org_id` (worked under uvicorn only because the contextvar defaults to
>   None — luck, not design); and `delete_user` flipped `revoked` directly instead of
>   using `revoke_user_sessions()`, leaving a **deleted user's session usable for up
>   to the 60s cache TTL**.
> - **Mutation-tested:** removing `"vehicles"` from `TENANT_COLLECTIONS` produces 4
>   failures including "A deleted B's record", proving the suite detects a real leak.
> - Added `docs/implementation/TENANT_TEST_MATRIX.md`. Full suite: 492 passed, 3 skipped.
> - **NOT done here:** background-job/notification coverage (neither exists), signed-URL
>   coverage (FILE-01 streams instead), timing-channel analysis, N-tenant isolation.

> **AUTHZ-01 progress (repository work complete; PR open).**
> Delivered on `feature/authz-01-permission-engine`:
> - Replaced scattered `require_role(...)` lists and hard-coded viewer/driver checks
>   with a canonical **action-permission catalogue** (`backend/permissions.py`):
>   `resource:action` permissions, an explicit role→permission map keyed on the six
>   effective tiers, and `auth.require_permission(...)` as the single primitive every
>   mutating endpoint depends on.
> - Platform permissions are defined separately and held by **no current role**
>   (`org_admin` is an organisation top, not a platform superuser; no platform
>   console exists yet).
> - Built to reproduce the pre-AUTHZ-01 guards **exactly** — all 492 prior tests stay
>   green — with two deliberate tightenings: a read-only viewer can no longer upload,
>   and trip-close/repair-advance are no longer open to viewers (both were
>   `require_user`).
> - `roles:assign` separated from `users:manage`; role changes and user creation are
>   **audited** to `security_audit` (ids/action only, no secrets) and trigger immediate
>   session revocation.
> - A build-time guard walks the AST of every route module and fails if any mutating
>   endpoint lacks `require_permission`.
> - Added `docs/implementation/AUTHORIZATION.md`, 34 catalogue/wiring unit tests and 18
>   real-HTTP per-role enforcement tests. Full suite: 544 passed, 3 skipped.
>   Mutation-tested; live-smoke-verified (admin allowed, viewer denied, reads OK).
> - **NOT done here:** branch-scoped permissions (no branch_id yet), enforced monetary
>   limits (predicate ready, no product rule), record-state conditions (WF-01),
>   fastag_sync lockdown (FASTAG-01).

> **FASTAG-01 progress (repository work complete; PR open).**
> Delivered on `feature/fastag-01-demo-simulation`:
> - **Fixed a P0:** `POST /fastag/sync/{vehicle_id}` was `require_user`, so any user in
>   any organisation could fabricate 4-8 random toll transactions plus a recharge for a
>   real vehicle and **overwrite its `fastag_balance` with `random.uniform(250, 2800)`**.
> - `backend/fastag_simulation.py`: simulation fails closed off the canonical demo org
>   (requires both `is_demo` and `DEMO_ORG_ID`; non-demo callers get 403 before any
>   write) and requires the `fastag:simulate` permission. Idempotent via a batch key
>   (replay writes nothing new); balance is **computed** from the vehicle's transactions,
>   never random; amounts/dates/size bounded; simulated rows marked
>   `source="demo_simulation"`; each run audited.
> - Demo simulation, manual import (`POST /fastag`) and a fail-closed (non-existent)
>   live-provider path are explicitly separated.
> - Added `docs/implementation/FASTAG_SIMULATION.md` and 21 tests (+1 in the matrix).
>   Full suite: 566 passed, 3 skipped. Mutation-tested; live-smoke-verified (real-org
>   sync 403, demo replay idempotent).
> - **NOT done here:** live-provider integration (deliberately absent, must not reuse the
>   simulation path).

> **WF-01 progress (repository work complete; PR open).**
> Delivered on `feature/wf-01-workflow-transitions`:
> - **Fixed a defect class:** generic CRUD could drive operational state directly —
>   un-dispose a vehicle, reopen a closed downtime, jump a repair open→closed skipping
>   approval, or re-close a completed trip (recomputing distance/odometer).
> - `backend/workflow.py`: explicit state graphs (repairs, vehicles, drivers, downtime,
>   trips) + one validator every status change runs through. Invalid edge → 409; terminal
>   states can't be left; disposal/exit role-gated; idempotent; optimistic concurrency via
>   `_version`; every transition audited. Generic updates validate status changes before
>   writing, so a generic PUT cannot bypass the workflow.
> - **No genuine workflow, documented not invented:** no expense-approval, payment or
>   generic-approval workflow exists (only the repair `approved` state); tyre/FASTag status
>   is a label; odometer is a monotonic invariant.
> - Added `docs/implementation/WORKFLOWS.md` and 35 tests. Full suite: 601 passed, 3
>   skipped. Mutation-tested; live-verified (dispose 200, un-dispose 409).
> - **NOT done here:** rejecting a lower odometer on generic update (data-quality gap);
>   `_version` wired only to the repair transition; no reversal path for terminal states.

> **SEC-CLOSEOUT progress (repository work complete; PR open).**
> Delivered on `feature/sec-closeout-release-gate`:
> - Added `docs/implementation/SECURITY_RELEASE_GATE.md` — every P0 control reconciled
>   with implementation reference, test + mutation evidence, PR/commit, production-verification
>   status, remaining exception and a release decision.
> - Added an app-wide security-headers middleware (nosniff, X-Frame-Options: DENY,
>   Referrer-Policy, HSTS in production), closing a gap the gate surfaced. 5 tests.
> - **Release decision:** repository security programme COMPLETE; production security
>   operations BLOCKED pending SEC-004 and SEC-005; production release **NOT APPROVED**.
> - Full suite: 606 passed, 3 skipped.

> **Security programme frozen (21 July 2026).** The repository-side critical security
> programme is **complete**: SEC-001/002/003, TEN-01, FILE-01, AUTH-01, TEN-TEST,
> AUTHZ-01, FASTAG-01, WF-01 and SEC-CLOSEOUT are all merged into `develop`. A final
> consolidation branch (`feature/security-final-closeout`) closed lint debt from the
> FASTAG-01 refactor and finalised the release-gate conclusion. No further security
> phase is planned. The only remaining critical work is operator-led: **SEC-004**
> (production credential rotation) then **SEC-005** (Git-history cleanup). Release
> conclusion: repository security hardening Complete; production security operations
> Incomplete; production release Blocked pending SEC-004 and SEC-005. See
> `docs/implementation/SECURITY_RELEASE_GATE.md`.

| ID | Priority | Finding | Impact | Required resolution |
| --- | --- | --- | --- | --- |
| SEC-01 | P0 | Hardcoded default credentials and auto-created users | Credentials in source/test artefacts can lead to unauthorised access. | Remove, rotate, revoke, and create first admin only through verified provisioning. |
| TEN-01 | P0 | Mass-assignment risk for org_id and protected fields | Generic dictionaries may permit record transfer or protected-field manipulation. | Strict schemas, immutable server fields, session-derived org context, tests. |
| FILE-01 | P0 | File records/downloads not fully tenant-scoped | A file identifier must never be enough to access another organisation file. | Add org_id and linked-record ACL; signed URLs; security scanning. |
| AUTH-01 | P0 | Bearer token stored in localStorage | XSS can expose long-lived session tokens. | Secure HttpOnly SameSite cookies, CSRF controls, token hashing and session management. |
| AUTHZ-01 | P0 | Broad role tiers can authorise unrelated writes | Operations, maintenance, and accounts roles can collapse into broad data-entry privileges. | Explicit action permissions and backend enforcement. |
| FASTAG-01 | P0 | Simulated FASTag sync can write random live transactions | Financial and operational data can be corrupted. | Demo-only simulation; real integration or import with idempotency. |
| WF-01 | P0 | Generic PUT can bypass controlled repair workflow | Protected status and approval stages may be changed without authorised transitions. | Dedicated transition APIs and immutable workflow fields. |
| BUG-01 | P1 | Vehicle, driver, and ticket rows do not reliably open detail pages | Existing high-quality profiles appear broken or inaccessible. | Wire row navigation and explicit view actions. |
| PERF-01 | P1 | Vehicle profile and onboarding administrator step can freeze for 30-60 seconds | Severe usability and conversion issue. | Lazy tabs, memoisation, virtualisation, profiling, skeletons. |
| VAL-01 | P1 | Validation is silent, toast-only, or one-error-at-a-time | Users cannot identify and correct form errors efficiently. | Schema-driven forms with inline errors and all-errors-on-submit. |
| ROUTE-01 | P1 | Authenticated users can reach guest-only routes and Back may show onboarding/login | Confusing and potentially security-relevant session behaviour. | Unified protected/guest guard, replace navigation, pageshow revalidation. |
| DEMO-01 | P1 | Enter Demo and Exit Demo are flaky; shared demo state | Poor trial experience and cross-visitor interference. | Idempotent transitions, feedback, isolated disposable demo workspace. |
| DATA-01 | P1 | Trip conflicts and availability rules are incomplete | Same vehicle/driver can be double-booked; invalid resources may be dispatched. | Trip state machine and atomic availability checks. |
| FUEL-01 | P1 | Mileage calculation assumes comparable fills and does not recalculate history | Misleading KPI and cost-per-km reporting. | Full-tank model, sequence validation, recalculation service. |
| SIDEFX-01 | P1 | FASTag, tyre, downtime, and odometer side effects are not consistently reversible | Edits/deletes may leave incorrect balances or statuses. | Domain services, transactions, reversals, rebuild jobs. |
| EXP-01 | P1 | Unified expense view may double-count the same economic event | Trip toll + FASTag, repair + accident, tyre + event, or manual duplicate. | Single source-linked expense ledger with unique keys and reversals. |
| SEARCH-01 | P1 | List search filters only the current loaded page | Records on later pages cannot be found. | Server-side search, filters, sorting, and URL state. |
| PERF-02 | P1 | Analytics contain high record caps and N+1 queries | Large organisations may receive incomplete or slow reports. | Aggregation pipelines, background jobs, no silent truncation. |
| MOBILE-01 | P1 | Mobile layout clips, wraps, and overlaps dashboard values | Driver and owner use on phones is unreliable. | Mobile-first layouts, cards, agenda views, bottom navigation. |
| BRAND-01 | P2 | Old Rajguru branding remains in generic reports | Multi-company output is inconsistent. | Organisation-aware templates and FleetFlow attribution. |
| STATUS-01 | P2 | Dashboard and Fleet Status derive different vehicle states | Users see conflicting KPIs. | Single central status derivation service. |
| CHART-01 | P2 | Month buckets and chart labels are inconsistent | Trend analysis can be misleading. | Central time-bucket service and locale formatting. |
| CRUD-01 | P2 | ACTIONS columns and add/edit behaviour are inconsistent | UI appears unfinished. | Standard data-grid action pattern and clear demo mode. |
| ONB-01 | P2 | Onboarding lacks save/resume, verification, approval pipeline, and progressive setup | Self-serve SaaS conversion and governance are incomplete. | Drafts, verification, provisioning states, owner approval, checklist. |
| PLATFORM-01 | P2 | No platform-owner control plane | Operator cannot govern organisations, plans, support, or global health. | Separate /platform scope and audited controls. |


## 4.1 Live QA issues that must remain in the tracked backlog

- Dead row navigation for Vehicles, Drivers, and Tickets.
- Heavy render freezes on Vehicle Profile and Onboarding Administrator step.
- Silent or disconnected onboarding validation.
- Dashboard versus Fleet Status metric mismatch.
- Malformed month-axis labels and missing month buckets.
- Empty ACTIONS columns and inconsistent CRUD controls.
- Authenticated access to guest routes and broken browser Back behaviour.
- Flaky Enter Demo and Exit Demo actions.
- Partial-month versus full-month comparison without annotation.
- Odometer source drift, decimal-format inconsistency, and truncated sidebar behaviour.


# 5. Target Product and Technical Architecture


## 5.1 Recommended logical architecture

```text
Client applications
  - Web app (owner, manager, operations, accounts, auditor)
  - Mobile/PWA driver experience
  - Platform owner console
        |
API gateway / application backend
  - Authentication and session service
  - Organisation and branch context
  - Permission and entitlement engine
  - Domain services: trips, fuel, maintenance, tickets, tyres, expenses, compliance
  - Reporting/export service
  - File security service
  - Notification service
        |
Data and infrastructure
  - Transactional MongoDB with compound tenant indexes
  - Object storage with tenant metadata and signed access
  - Background job queue for exports, OCR, alerts, imports and rebuilds
  - Cache for dashboards and lookup data
  - Audit/event store and immutable security logs
  - Monitoring, error tracking, backups and restore automation
```


## 5.2 Domain-boundary rule

Generic CRUD may remain for low-risk master data only. High-risk operational and financial modules must use domain services that validate business rules and perform all linked changes atomically. The service layer is responsible for permissions, organisation scope, state transitions, audit events, expense generation, odometer updates, balance updates, and notifications.


## 5.3 Recommended backend layers

| Layer | Responsibility |
| --- | --- |
| API route | Parse request, invoke permission guard, call service, return safe response. No business calculations in route handlers. |
| Schema/DTO | Explicit create, update, action, filter, and response models. Reject unknown fields. |
| Permission service | Check action, role, organisation, branch, ownership, amount limit, and record state. |
| Domain service | Implement workflow, validation, transactions, linked records, and audit events. |
| Repository/data access | Apply organisation scope automatically and provide safe query primitives. |
| Event/outbox | Publish reliable notifications, analytics events, integrations, and audit events after commit. |
| Background workers | Imports, exports, OCR, notification dispatch, recalculation, data repair, and scheduled checks. |


## 5.4 Data ownership fields

- Every tenant record: org_id, branch_id where applicable, created_at, created_by, updated_at, updated_by, version, archived_at, archived_by.
- Every financial record: source_module, source_record_id, source_component, approval_status, payment_status, currency, reversal_of, reversed_by.
- Every file: org_id, branch_id, uploaded_by, linked_module, linked_record_id, hash, scan_status, content_type, original_filename, size, retention_class.
- Every security event: actor, organisation, session, IP, device, action, target, result, reason, timestamp, correlation ID.


# 6. Security Enhancement Programme

Security must be treated as a product capability, not a final checklist. Controls below are required in architecture, code review, automated tests, deployment, support, and incident response.


## 6.1 Tenant isolation and IDOR prevention

- Derive organisation context from the authenticated server session for every request and background job.
- Remove org_id from all public create/update schemas. If received, reject the request rather than silently accepting it.
- Force org_id on insert; never use setdefault for tenant ownership.
- Add organisation scope to files, budgets, sessions where appropriate, imports, exports, audit logs, notifications, and generated reports.
- Use organisation-scoped unique indexes for usernames where desired, vehicle numbers, ticket sequences, invoice references, and source expense keys.
- Return 404 rather than revealing whether a cross-tenant UUID exists, unless policy requires an explicit 403.
- Create a security test that obtains valid IDs from Organisation B and attempts every read, update, delete, action, file, search, report, and export from Organisation A.
- Platform-owner cross-organisation access must use separate credentials, separate routes, explicit reason, optional customer consent, and immutable audit logs.


## 6.2 Authentication and account lifecycle

- Remove auto-created production accounts and all known passwords from code and test artefacts.
- Require verified email before organisation activation; support optional mobile OTP for India-focused onboarding.
- Use strong password rules, breached-password checks, secure reset tokens, and non-enumerating reset responses.
- Provide administrator MFA and optional organisation-enforced MFA.
- Add login rate limiting by username, IP, device, and organisation; add progressive delay and temporary lockout.
- Record last successful login, failed attempts, password change, MFA enrollment, and suspicious login events.
- Provide session/device list, revoke one session, revoke all sessions, and force re-authentication for sensitive operations.
- Suspend or deactivate accounts without deleting operational history.


## 6.3 Session security

- Use Secure, HttpOnly, SameSite cookies instead of storing bearer tokens in localStorage.
- Use CSRF protection for state-changing requests when cookie authentication is enabled.
- Store only hashes of session tokens or rotate opaque session identifiers after authentication and privilege changes.
- Use absolute and idle expiry; shorter policies for platform administrators; configurable organisation policy where appropriate.
- Revoke all sessions after password reset, role change, account deactivation, organisation suspension, or suspected compromise.
- Add automatic database TTL indexes for expired sessions and reset tokens.
- Revalidate session on route changes, pageshow, tab focus for sensitive screens, and after browser Back/Forward cache restoration.


## 6.4 Authorisation and permission model

Replace broad legacy tiers with explicit permissions. A role becomes a named collection of permissions, and permissions are checked by the backend for each action. Branch, ownership, amount limit, and record-state conditions are evaluated separately.

| Permission family | Examples |
| --- | --- |
| Vehicle | vehicle.view, vehicle.create, vehicle.edit, vehicle.assign, vehicle.dispose, vehicle.export |
| Driver | driver.view, driver.create, driver.edit, driver.assign, driver.exit, driver.view_sensitive |
| Trip | trip.create, trip.assign, trip.dispatch, trip.close, trip.cancel, trip.settle, trip.approve |
| Fuel | fuel.create, fuel.edit, fuel.verify, fuel.approve, fuel.export |
| Maintenance | service.create, service.schedule, ticket.review, ticket.approve, ticket.send, ticket.close |
| Finance | expense.create, expense.verify, expense.approve, expense.pay, budget.manage, report.export |
| Compliance | document.upload, document.verify, compliance.manage, reminder.configure |
| Administration | user.manage, role.manage, organisation.manage, branch.manage, audit.view, data.export |
| Platform | platform.org.manage, platform.impersonate, platform.plan.manage, platform.support, platform.system.view |


## 6.5 Input validation and mass-assignment protection

- Use strict request schemas with unknown-field rejection for create, update, patch, and action requests.
- Separate user-editable fields from system, audit, approval, status, balance, total, and ownership fields.
- Validate enumerations, dates, date order, numeric ranges, currency, odometer sequence, file type, GSTIN, PAN, mobile, email, and registration numbers.
- Apply the same business validation at the service layer even when client-side validation exists.
- Use optimistic locking or version checks to prevent lost updates.
- Support idempotency keys for onboarding, payment, import, sync, trip closure, and integration callbacks.


## 6.6 API, web, and browser protections

- Explicitly whitelist CORS origins per environment; do not use wildcard origins with credentials.
- Add Content-Security-Policy, HSTS, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, and frame-ancestors controls.
- Sanitise user-generated rich text and avoid unsafe HTML rendering.
- Add request size limits, JSON depth limits, upload limits, export limits, and rate limits.
- Return stable error codes and safe messages; never expose stack traces, storage credentials, database errors, or internal paths.
- Use request correlation IDs and structured security logs.
- Add bot and abuse controls on signup, login, password reset, demo entry, search, exports, and public contact forms.


## 6.7 File upload and document security

- Whitelist required extensions and MIME types; verify file signatures instead of trusting extension or browser content type.
- Reject executable, script, HTML, unsafe SVG, macro-enabled, and archive formats unless specifically approved.
- Scan all uploads for malware and keep files quarantined until scan completion.
- Generate server-side storage names; retain the original filename only as metadata and sanitise it for display/download.
- Calculate a cryptographic hash for duplicate detection and integrity verification.
- Store files in a tenant-specific namespace and enforce linked-record permission on every download.
- Serve private files using short-lived signed URLs or a permission-checked streaming endpoint.
- Use attachment disposition for risky formats and inline only safe images/PDFs where required.
- Add retention, deletion, legal-hold, and backup policies for compliance files and personal documents.


## 6.8 Sensitive data and privacy

- Inventory personal data: names, mobile numbers, addresses, licences, Aadhaar, PF/UAN, ESI, emergency contacts, GPS locations, and uploaded documents.
- Avoid storing full Aadhaar unless strictly necessary; mask display and restrict sensitive-field permission.
- Encrypt high-risk fields or use application-level field encryption where operationally practical.
- Record purpose, consent, retention period, access history, export, correction, and deletion requests.
- Provide organisation data export and account closure workflows without compromising statutory retention requirements.
- Mask sensitive fields in analytics, session recordings, logs, Sentry traces, support screenshots, and test fixtures.
- Self-host fonts and disclose analytics/session recording. Provide consent or disable recording where required.


## 6.9 Audit logging and support impersonation

- Audit login, logout, failed login, password reset, MFA, role change, export, file access, workflow transitions, approval, payment, reversal, delete, restore, and platform actions.
- Audit records are append-only and cannot be edited through normal application endpoints.
- Capture before/after values for high-risk changes while masking secrets and protected personal data.
- Platform support impersonation requires reason, ticket reference, optional customer approval, time limit, visible banner, restricted actions, and complete audit history.
- Provide an organisation audit viewer with filters and export rights restricted to authorised roles.


## 6.10 Secrets, dependencies, and software supply chain

- Store secrets in environment-specific secret management, never in Git, frontend bundles, screenshots, or build logs.
- Rotate database, storage, email, SMS, analytics, and integration credentials periodically and after staff/contractor changes.
- Enable Git secret scanning, dependency alerts, software composition analysis, and static analysis in CI.
- Pin and review dependencies; remove unused packages and excessive backend libraries.
- Generate a software bill of materials for production releases.
- Use protected branches, required reviews, signed release tags where practical, and reproducible build artefacts.


## 6.11 Incident response and recovery

- Define severity levels, incident owner, contact list, evidence preservation, containment, communication, recovery, and post-incident review.
- Prepare runbooks for credential leak, cross-tenant exposure, ransomware, database corruption, storage outage, notification abuse, and payment-webhook compromise.
- Test backup restoration at least quarterly and before major migrations.
- Provide the ability to suspend an organisation, revoke all sessions, disable an integration, and block exports rapidly.


## 6.12 Security acceptance controls

| Control | Requirement | Evidence required |
| --- | --- | --- |
| TEN-001 | Client cannot create or update org_id. | Schema rejects field; automated test passes. |
| TEN-002 | All CRUD and action queries are scoped to session organisation. | Cross-tenant matrix returns 404/403 for every method. |
| TEN-003 | Files are organisation- and record-scoped. | Organisation A cannot access Organisation B file ID or URL. |
| TEN-004 | Background jobs retain organisation context. | Job tests show correct tenant on exports, alerts, OCR and imports. |
| AUTH-001 | No default production credentials exist. | Repository and secret scan clean; first admin created by provisioning. |
| AUTH-002 | Login is rate-limited and non-enumerating. | Automated abuse tests and consistent error responses. |
| AUTH-003 | Admin MFA is available. | Enrollment, challenge, recovery and disable tests pass. |
| SESS-001 | Session is stored in Secure HttpOnly cookie. | Browser storage contains no reusable auth token. |
| SESS-002 | Role/password changes revoke sessions. | Integration tests confirm immediate invalidation. |
| AUTHZ-001 | Every mutation uses action permission. | Endpoint permission inventory has no unguarded route. |
| AUTHZ-002 | Sensitive fields require separate permission. | Aadhaar/licence tests verify masking and restricted access. |
| API-001 | Unknown fields are rejected. | Mass-assignment tests fail safely. |
| API-002 | CORS is environment-restricted. | Only listed origins succeed with credentials. |
| WEB-001 | Security headers are present. | Automated header test passes on production-like deployment. |
| FILE-001 | Uploads are signature-checked and scanned. | Unsafe fixture files are rejected/quarantined. |
| AUD-001 | High-risk actions generate immutable audit entries. | Action-to-audit test matrix passes. |
| OPS-001 | Secrets are not present in repository or bundle. | Secret scanning and frontend bundle inspection clean. |
| DR-001 | Backup restore is proven. | Documented restore drill meets target recovery objectives. |


# 7. Data Integrity and Closed Workflow Design

FleetFlow must move from generic record editing to explicit lifecycle management. Each module below requires defined states, transitions, permissions, validations, side effects, audit events, notifications, reversals, and reporting treatment.


## 7.1 Universal workflow standard

- Every state change occurs through a named action endpoint, not a free-form status field.
- Allowed transitions are validated by current state, permission, organisation, branch, assignment, and required data.
- Actions are atomic: linked expense, odometer, vehicle status, driver assignment, downtime, and notifications commit together or roll back together.
- Every transition stores actor, timestamp, reason, remarks, attachments, and previous/new state.
- Cancelled, rejected, corrected, and reversed records remain in history; hard deletion is limited to safe master records and test data.
- Concurrency is controlled with unique indexes, transactions, version fields, and idempotency keys.


## 7.2 Trip lifecycle

```text
DRAFT -> PLANNED -> ASSIGNED -> DISPATCHED -> IN_TRANSIT -> ARRIVED -> POD_PENDING -> SETTLEMENT_PENDING -> CLOSED
   |         |          |             |             |               |
CANCELLED  REJECTED   REASSIGNED    BREAKDOWN     ACCIDENT        DISPUTED
```

- Prevent simultaneous active trips for the same vehicle or driver unless an explicit multi-driver policy allows it.
- Block assignment when vehicle is disposed, under repair, in downtime, non-compliant, or already dispatched.
- Block driver assignment for inactive status, expired licence, incompatible licence category, leave, or active trip conflict.
- Validate opening odometer against vehicle odometer and previous activity; require closing odometer not lower than opening.
- Capture route, purpose, customer/location, load, challan/e-way bill, planned distance, actual distance, POD, toll, parking, driver advance, and settlement.
- Provide cancellation, reassignment, breakdown, accident, and missing-POD exceptions.
- Close only after required POD and settlement conditions, with manager override logged separately.


## 7.3 Fuel lifecycle and mileage integrity

- Capture full tank/partial fill, fuel type, litres, rate, amount, odometer, station/vendor, payment mode, invoice, tank level, and GPS/location where available.
- Calculate mileage only between valid comparable full-tank points; display provisional values for partial fills.
- Validate litres against tank capacity and rate against configurable tolerance.
- Detect duplicate invoice/date/amount/vehicle combinations and suspicious odometer or quantity patterns.
- Recalculate all affected downstream mileage entries when a historical entry is corrected or reversed.
- Never decrease the vehicle master odometer automatically without an approved correction event.


## 7.4 Maintenance and repair tickets

```text
OPEN -> UNDER_REVIEW -> APPROVED -> SENT_TO_VENDOR -> IN_REPAIR -> QUALITY_CHECK -> REPAIRED -> CLOSED
  |           |             |                |             |
REJECTED   MORE_INFO     CANCELLED        PARTS_WAIT   REWORK
```

- Separate minor direct maintenance from approval-controlled repairs through clear thresholds and policy.
- Require estimate, vendor, expected completion, approval limit, and reason before approval.
- Support parts, labour, tax, warranty, insurance recovery, downtime, root cause, repeat issue, and quality check.
- Create or close downtime and vehicle status automatically from ticket state.
- Generate expense only from approved invoice or authorised final cost, not from multiple overlapping fields.
- Detect repeat repairs by vehicle, component, vendor, and period.


## 7.5 Tyre lifecycle

```text
IN_STOCK -> INSTALLED -> ROTATED/REPAIRED/RETREADED -> REMOVED -> SCRAPPED or RETURNED
```

- Each tyre requires unique serial, make, size, purchase date, vendor, cost, warranty, installation vehicle/position/odometer, and removal details.
- A tyre cannot occupy two positions simultaneously; a position cannot hold two active tyres.
- Replacement, rotation, retreading, puncture, and scrapping are domain actions with reversible history.
- Calculate tyre life, cost per kilometre, puncture frequency, retread count, and warranty recovery.


## 7.6 FASTag lifecycle

- Treat provider transactions as immutable imported events with provider transaction ID, source file/API, and reconciliation status.
- Use idempotency to prevent duplicate imports and syncs.
- Compute balance from authoritative provider balance or reconciled ledger; do not rely on random or editable values.
- Differentiate toll, recharge, refund, reversal, adjustment, and failed transaction.
- Reconcile tolls against trips by vehicle, date, time, route, and plaza; flag unmatched or duplicate toll costs.
- Keep simulation exclusively inside a disposable demo workspace.


## 7.7 Vehicle lifecycle

```text
DRAFT -> ACTIVE -> IDLE / RUNNING / UNDER_REPAIR / DOWNTIME -> SOLD or SCRAPPED -> ARCHIVED
```

- Vehicle number, chassis, and engine uniqueness must be organisation-scoped and normalised.
- Disposal requires date, sale value/scrap value, buyer, approval, document transfer, open-trip check, active-driver unassignment, and final compliance state.
- Historical records remain accessible after disposal; normal lists exclude disposed vehicles by default but reports can include them.
- Deletion is blocked when history exists; use archival or disposal instead.


## 7.8 Driver lifecycle

```text
APPLICANT -> ACTIVE -> ON_LEAVE / SUSPENDED -> RESIGNED or TERMINATED -> ARCHIVED
```

- Validate mobile, licence, categories, expiry, emergency contact, employment identifiers, and assigned vehicle.
- Separate personal and sensitive statutory data permissions.
- Exit requires date, reason, open-trip check, vehicle unassignment, asset/document handover, final settlement reference, and approval.
- Driver login is linked to a driver record and limited to assigned/authorised operations.


## 7.9 Expense and payment lifecycle

```text
DRAFT -> SUBMITTED -> VERIFIED -> APPROVED -> PAYMENT_DUE -> PAID -> RECONCILED
   |          |           |             |
CANCELLED   REJECTED   RETURNED      PARTIALLY_PAID

Any posted transaction -> REVERSAL -> corrected replacement transaction
```

- Do not edit an approved/paid financial entry in place; reverse and replace it.
- Approval rules can depend on category, amount, branch, role, budget, vendor, and missing attachment.
- Payment records must reference approved expenses and support partial payments, advances, TDS/GST where relevant, and reconciliation.
- All automated module expenses use a unique source key so the same economic event cannot be posted twice.


# 8. Multi-Company SaaS and Organisation Onboarding


## 8.1 Workspace model

- Each customer receives an isolated organisation workspace with branches, departments, cost centres, roles, users, numbering, preferences, compliance configuration, and subscription.
- A user may belong to one or multiple organisations only through explicit memberships; each membership has role, branch scope, status, and invitation history.
- Organisation switching must refresh permissions, entitlements, caches, and session context without retaining data from the previous workspace.
- Rajguru Foods becomes one normal organisation tenant, not a special hardcoded default in product logic.


## 8.2 Redesigned onboarding stages

| Stage | Content | System outcome |
| --- | --- | --- |
| 1. Account intent | Individual fleet owner, company, transporter, logistics business, institution, or trial/demo. | Account type and intended use. |
| 2. Organisation identity | Legal name, trade name, industry, GSTIN/PAN where applicable, contact details. | Minimal required fields; optional details can be completed later. |
| 3. Address and branch | Registered address, operating address, billing address, first branch, PIN/city/state helper. | Create default branch and timezone. |
| 4. Administrator | Full name, email, mobile, username, password, designation, verification. | Create pending admin identity; inline validation and availability checks. |
| 5. Fleet profile | Fleet size, vehicle classes, ownership type, drivers, operation types, states/countries. | Configure relevant modules and defaults. |
| 6. Controls and preferences | Compliance documents, reminders, numbering, financial year, currency, date format, language, approval preferences. | Generate organisation configuration. |
| 7. Data setup | Start empty, use sample data, or import vehicles/drivers/documents. | Template download and validation preview. |
| 8. Review and consent | Review, terms/privacy version, consent timestamp, plan, approval status. | Submit onboarding application. |


## 8.3 Provisioning state machine

```text
DRAFT -> PENDING_VERIFICATION -> PENDING_APPROVAL -> PROVISIONING -> ACTIVE
             |                     |                |
          EXPIRED              REJECTED        PROVISIONING_FAILED
                                                   |
                                               RETRY / MANUAL_REVIEW

ACTIVE -> SUSPENDED -> ACTIVE or CLOSED
```


## 8.4 Onboarding UX requirements

- Inline field errors, field highlighting, helper text, all errors at once, and focus on the first invalid field.
- Save and resume with secure link; preserve completed steps and allow backward navigation.
- Debounced username/email availability checks with suggestions.
- Clear loading, success, pending-approval, rejection, and provisioning-failure states.
- Email verification and optional mobile OTP before activation.
- Store consent document version, timestamp, IP, and user identity.
- Time-to-first-insight target below ten minutes using imports, sample data, and guided setup checklist.


## 8.5 Demo design

- Landing page offers Try Demo, then asks the visitor to choose a predefined role.
- No visible usernames or passwords are required.
- Each demo session receives isolated or disposable data so visitors do not affect each other.
- Demo users cannot access real data, organisation settings that affect live systems, billing, user invitations, exports containing personal data, or live integrations.
- Enter Demo and Exit Demo are idempotent, single-click, and show progress and error feedback.


# 9. Platform Owner Control Plane

FleetFlow requires a separate platform-owner application above organisation administration. It must use separate routes, permissions, session policy, audit rules, and data-access services. Ordinary organisation tokens must never access platform endpoints.


## 9.1 Platform modules

| Module | Capabilities |
| --- | --- |
| Organisation directory | Search, filter, view status, usage, plan, users, fleet size, support status, and risk flags. |
| Onboarding approvals | Approve, reject, request information, set plan, set limits, and review application answers. |
| Subscription management | Plans, entitlements, trials, coupons, grandfathering, invoices, payment status, dunning, and cancellation. |
| Feature flags | Enable by environment, plan, organisation, percentage rollout, or support override. |
| Support console | Tickets, diagnostics, organisation health, audited impersonation, announcements, and knowledge base. |
| System health | Errors, latency, jobs, queues, storage, database health, email/SMS delivery, and uptime. |
| Security centre | Suspicious logins, export activity, failed tenant tests, session revocation, and incident controls. |
| Data operations | Organisation export, backup status, restore request, retention, deletion request, and migration status. |
| Commercial analytics | MRR, ARR, trials, conversion, churn, active organisations, feature adoption, and usage. |
| Global masters | Vehicle makes, document types, categories, countries/states, templates, and localisation content. |


## 9.2 Impersonation controls

- [ ] Require platform permission and recent MFA confirmation.
- [ ] Capture reason, ticket/reference, organisation, actor, start time, and expiry.
- [ ] Show a persistent impersonation banner and prohibit silent background impersonation.
- [ ] Optionally require organisation consent for non-emergency support access.
- [ ] Block billing, password, MFA, subscription, export, and destructive actions unless separately authorised.
- [ ] Record every impersonated read and mutation in immutable audit logs.


# 10. Subscription, Entitlement, and Billing Readiness


## 10.1 Build entitlement plumbing now

- Create plans, features, plan_entitlements, subscriptions, subscription_events, usage_records, invoices, payments, credits, and coupons schemas.
- Seed a Free/Beta plan with unlimited or configured limits and all currently released features enabled.
- Auto-subscribe each organisation during provisioning.
- Use a central entitlement service for every feature and limit decision; never scatter plan-name checks through UI code.
- Enforce limits on the backend and expose a safe entitlement summary to the frontend.
- Create a provider interface with a no-op billing provider now and Razorpay implementation later.


## 10.2 Entitlement examples

| Entitlement type | Examples |
| --- | --- |
| Quantity limits | vehicles.max, users.max, branches.max, storage_gb.max, exports_monthly.max |
| Feature flags | gps.enabled, fastag.enabled, api.enabled, scheduled_reports.enabled, whatsapp.enabled |
| Service level | support_level, data_retention_days, audit_retention_days, export_queue_priority |
| Branding | custom_logo.enabled, custom_domain.enabled, white_label.enabled |
| Security | mfa_enforcement.enabled, sso.enabled, ip_allowlist.enabled |


## 10.3 Paid billing phase

- Razorpay checkout, subscriptions, UPI AutoPay/e-mandates, verified webhooks, retries, dunning, grace periods, and cancellation.
- GST invoice generation with organisation and place-of-supply data, CGST/SGST or IGST logic, sequential invoice numbering, credit notes, and download history.
- Monthly and annual plans, trial conversion, coupons, grandfathered plans, plan change, proration, and overage where required.
- Billing portal for plan, payment method, invoices, usage, next billing date, cancellation, and support.


# 11. UI/UX, Design System, and Accessibility


## 11.1 Brand and interface direction

Use FleetFlow as the central brand with the tagline “Complete Fleet Operations Management.” The interface should be premium, modern, clean, minimal, and professional, using dark navy/charcoal, warm amber as a controlled accent, white/light backgrounds, strong typography, and restrained motion.


## 11.2 Design system

- Define tokens for colour, typography, spacing, radius, elevation, borders, focus rings, motion, and chart palette.
- Create reusable components for page headers, KPI cards, filters, tables, forms, dialogs, drawers, empty states, skeletons, errors, status pills, notifications, and audit timelines.
- Use Storybook or a component catalogue to review states before page implementation.
- Support light and dark mode without reducing contrast or status clarity.
- Use consistent language, currency, date, time, decimal, percentage, and unit formatting.


## 11.3 Smart sidebar specification

- Expanded desktop state with full labels; compact icon-only state with tooltips; mobile off-canvas drawer.
- Smooth toggle with remembered preference; no ugly residual strip after collapse.
- Hide the visible scrollbar while retaining keyboard, wheel, and touch scrolling.
- Keep brand header and user/profile footer fixed while only the menu area scrolls.
- Group modules logically and collapse groups; show only modules allowed by the backend modules/permissions response.
- Provide a clear active state, hover state, focus state, and badge/count state without large distracting blocks.


## 11.4 Validation and form standard

- Use React Hook Form with schema validation such as Zod; mirror critical rules in backend schemas.
- Validate on blur and submit; show all field errors together; scroll/focus to first error.
- Field error appears below the field, border and icon indicate error, and accessibility attributes connect label, helper, and error.
- Toasts are used for system success/failure, not as the only field validation message.
- Disable submission and show spinner during save; prevent double submission and use idempotency for critical actions.
- Conditional fields appear only when relevant and preserve values safely when hidden.


## 11.5 Page interaction standard

- Rows that open detail pages show pointer, hover, keyboard focus, and a visible View action or chevron.
- No empty ACTIONS columns. Use a consistent kebab menu for secondary actions and explicit primary action where needed.
- Every page has loading, empty, no-results, error, offline, permission-denied, and success states.
- Destructive actions use confirmation with record context; high-risk actions may require typed confirmation or recent re-authentication.
- Cards that are clickable must visually behave like controls and be keyboard accessible.


## 11.6 Accessibility target

- Target WCAG AA: keyboard access, visible focus, meaningful headings, labels, table headers, alt text, contrast, scalable text, and reduced motion.
- Use status text/icons in addition to colour.
- Provide screen-reader announcements for saves, validation, loading, and asynchronous updates.
- Test at 200% zoom and with keyboard-only navigation.


# 12. Search, Filters, Data Grids, Reports, and Exports


## 12.1 Server-side list standard

- Search, filters, sorting, pagination, total count, and permissions are processed by the server.
- Search never applies only to the currently loaded 25 records.
- Use debounced queries, cancellation of stale requests, and URL-persisted state.
- Offer advanced filter drawer, active filter chips, clear-all, saved views, and organisation defaults.
- Allow page size, density, column show/hide, column order, sort, and export of current filtered result.
- Use asynchronous searchable comboboxes for vehicles, drivers, tyres, vendors, branches, and users instead of loading thousands of options.


## 12.2 Global search

- Search vehicles, drivers, trips, tickets, documents, vendors, invoices, expenses, and compliance records according to permission.
- Return grouped results with type, primary identifier, context, branch, and direct navigation.
- Index normalised values and avoid unbounded regex scans as data grows.
- Mask sensitive fields and do not expose records outside branch or role scope.


## 12.3 Reports and exports

- Reports use organisation logo, legal/trade name, selected period, filters, generated-by user, generated timestamp, and FleetFlow attribution.
- Remove hardcoded Rajguru Foods headings from generic templates.
- Run large reports asynchronously and notify the user when ready; exports have expiry and access control.
- No report silently truncates at 5,000 records. Display a warning and use background generation when large.
- Provide Excel and professional PDF formatting, repeated headers, totals, page numbers, and print-friendly layouts.
- Audit sensitive exports and allow administrators to restrict export permission.


# 13. Expense Intelligence and Financial Controls


## 13.1 Single expense ledger architecture

Create one canonical expense ledger. Operational modules generate linked draft or posted expense components through the expense service. The user interface may show expenses by module, but totals come from the canonical ledger rather than repeatedly summing unrelated collections.


## 13.2 Required fields

| Group | Fields |
| --- | --- |
| Identity | expense_id, org_id, branch_id, cost_centre_id, department_id, project_id |
| Source | source_module, source_record_id, source_component, source_transaction_id, idempotency_key |
| Classification | category, subcategory, direct/indirect, fixed/variable, owned/hired, capital/revenue |
| Operational links | vehicle_id, driver_id, trip_id, ticket_id, vendor_id |
| Document | invoice number, invoice date, description, attachments, purchase order/reference |
| Amounts | taxable value, GST components, other tax/charges, total, currency, exchange rate |
| Workflow | draft/submitted/verified/approved/payment_due/paid/reconciled/reversed |
| Payment | payment method, due date, payment reference, partial payments, advance adjustment |
| Audit | created/updated/approved/paid/reversed by and timestamps, version, reason |


## 13.3 Duplicate prevention

- Unique source key: org_id + source_module + source_record_id + source_component.
- Manual duplicate suspicion: vehicle/vendor + invoice + date + amount + category within configurable tolerance.
- Toll reconciliation prevents the same toll being counted from trip expense and FASTag import.
- Accident, repair, and insurance recovery are linked components rather than independent totals.
- Tyre purchase and tyre event use separate economic components only where both are genuinely chargeable.


## 13.4 Smart views and insights

- Total spend, current period, comparable prior period, budget variance, unpaid, overdue, and cost per kilometre.
- Drill down by category/subcategory, vehicle, vehicle class, driver, trip, route, vendor, branch, department, project, ownership, and payment status.
- Month-on-month and year-on-year comparisons using comparable elapsed periods; clearly label partial periods.
- Vehicle total cost of ownership: purchase/depreciation or lease, fuel, maintenance, tyres, compliance, insurance, tolls, downtime, and disposal recovery.
- Anomalies: duplicate entries, missing bills, rate spikes, mileage deterioration, repeated repairs, budget overshoot, vendor concentration, unusual tolls, and high cost per kilometre.
- Every chart and KPI supports drill-through to source transactions.


## 13.5 Approval and payment controls

- Configurable approval matrix by category, amount, branch, role, and budget variance.
- Approver cannot approve own expense where segregation is required.
- Paid records are immutable; corrections use reversal and replacement.
- Optional GST/ITC tracking, vendor GSTIN validation, and future reconciliation to accounting/GSTR data.


# 14. Mobile, Driver Experience, and Offline PWA


## 14.1 Responsive requirements

- Audit every primary page at 360, 390, 414, 768, 1024, and desktop widths.
- Dashboard uses one-column cards on small screens, equal-height rows where grouped, fluid typography, and non-wrapping critical values.
- Tables become stacked record cards or purpose-built mobile lists; do not force users to zoom or scroll wide tables for routine tasks.
- Vehicle profile uses horizontally scrollable tab strip or mobile section menu; calendar has agenda view.
- Use safe-area insets, dvh/svh units, large tap targets, and sufficient bottom padding for fixed controls or platform badges.


## 14.2 Driver-first mobile home

- Bottom navigation: Home, Trips, Fuel, Report Issue, Profile.
- Prominent quick actions: start trip, close trip, add fuel, report breakdown, report accident, upload document/photo.
- Show only assigned vehicle and authorised trip/driver data.
- Camera capture for odometer, fuel bill, POD, accident, and document; compress before upload while preserving legibility.
- Offline queue for approved actions with clear pending/synced/failed state and conflict handling.
- Local language preference per user and large readable controls.


## 14.3 Offline safety

- Do not mark financial or workflow actions as final until server acknowledgement.
- Assign local idempotency keys so retries do not create duplicates.
- Encrypt sensitive offline data, minimise retention, and clear it on logout or account revocation.
- Display last sync time and prevent silent data loss.


# 15. Performance, Scalability, and Data Architecture


## 15.1 Immediate performance fixes

- Profile the vehicle profile and onboarding administrator step to identify blocking render, repeated requests, chart resize loops, or excessive DOM work.
- Mount only the active tab; code-split heavy pages and charts; memoise derived datasets; virtualise long lists.
- Add skeletons and progressive rendering so navigation responds immediately.
- Debounce resize and search; cancel stale API requests.


## 15.2 Backend query design

- Replace loops that query each vehicle/tyre with aggregation pipelines and batch lookups.
- Create compound indexes beginning with org_id and common filters/sorts: status, date, vehicle_id, driver_id, branch_id, source keys, ticket number, expiry date.
- Use projections to avoid loading unnecessary fields and personal data.
- Remove silent to_list limits from financial totals and reports; use pagination or background aggregation.
- Cache dashboard aggregates and invalidate/rebuild them after relevant events.
- Use a job queue for large exports, imports, OCR, scheduled reports, bulk notifications, recalculation, and data-repair tasks.


## 15.3 Performance budgets

| Metric | Target for production-like environment |
| --- | --- |
| Navigation response | Visible page shell or skeleton within 300 ms after route change. |
| Typical API read | p95 below 500 ms for normal organisation sizes. |
| Typical mutation | p95 below 800 ms excluding file upload/external provider time. |
| Dashboard | Primary KPIs usable within 2 seconds; remaining charts progressively load. |
| Search | Results begin within 500 ms after debounce for indexed queries. |
| Large export | Queued within 1 second; generated asynchronously with progress/status. |
| Mobile | No horizontal overflow on primary workflows at 360 px. |


# 16. Integrations, Notifications, and Automation


## 16.1 Communication infrastructure

- Transactional email for verification, password reset, onboarding status, welcome, approval, reports, and billing.
- SMS/mobile OTP provider for verification and critical alerts where required.
- WhatsApp Business API for expiry reminders, approvals, driver instructions, and payment/operation confirmations.
- In-app notification centre with read/unread, type, priority, action link, and retention.
- Per-user notification preferences by event, channel, quiet hours, and branch scope.


## 16.2 Integration framework

- Create provider interfaces and adapters for FASTag, GPS, fuel cards, maps, OCR, email, SMS, WhatsApp, billing, accounting, and cloud storage.
- Store provider credentials encrypted per organisation and restrict who can configure or view them.
- Use webhooks with signature verification, replay prevention, idempotency, retry, dead-letter queue, and audit logs.
- Provide integration health, last sync, error, retry, and manual reconciliation screens.
- Never label a simulated or placeholder integration as live.


## 16.3 Priority integrations

| Stage | Integration | Value |
| --- | --- | --- |
| Near term | CSV/Excel imports for vehicles, drivers, documents, trips, fuel, FASTag | Fast onboarding and migration from spreadsheets. |
| Near term | Document OCR for expiry and identifiers | Reduces entry effort and missed compliance. |
| Near term | Email/WhatsApp alerts | Creates immediate operational value. |
| Mid term | FASTag provider/import reconciliation | Automates toll cost and route exceptions. |
| Mid term | GPS/telematics | Live map, utilisation, geofence, route and harsh-driving data. |
| Mid term | Accounting/Tally export or integration | Reduces duplicate accounting entry and improves reconciliation. |
| Long term | Fuel cards and predictive maintenance | Fraud detection and preventive cost savings. |


# 17. Internationalisation and Localisation

- Use a mature i18n framework and extract all user-facing strings into namespaces.
- Initial languages: English, Hindi, Marathi, and Kannada; prioritise driver quick actions and compliance alerts.
- Persist language per user, not only per organisation.
- Use locale-aware number, Indian currency grouping, date, time, month, percentage, and unit formatting.
- Self-host suitable fonts for Latin, Devanagari, and Kannada scripts.
- User-entered data is not automatically translated; interface labels, system messages, templates, and notifications are localised.
- Translation changes require review and visual testing for expansion, wrapping, and mobile layouts.


# 18. Observability, DevOps, Backup, and Operations


## 18.1 Environments and deployment

- Separate dev, staging, demo, and production with independent databases, storage, secrets, integrations, analytics, and domains.
- Use CI/CD to run lint, type checks, unit tests, integration tests, security scans, build, and deployment smoke tests.
- Create preview environments for major pull requests where practical.
- Use versioned migrations and a deployment checklist with rollback conditions.
- Deploy behind health/readiness checks and avoid routing traffic until the new version is ready.


## 18.2 Observability

- Structured logs with correlation ID, organisation ID, user ID, action, latency, result, and safe error code.
- Application error tracking with personal-data scrubbing.
- Metrics for request rate, error rate, latency, database operations, queue length, job failures, storage failures, login failures, and notification delivery.
- Distributed tracing for slow cross-service or integration operations where architecture requires it.
- Dashboards and alerts with clear owner and runbook; public status page when commercial customers depend on the service.


## 18.3 Backup and disaster recovery

- Automated encrypted database backups and object-storage protection with documented retention.
- Point-in-time recovery where feasible and regular restore verification in a non-production environment.
- Define recovery time and recovery point objectives appropriate to customer commitments.
- Back up configuration, templates, entitlement data, audit logs, and integration metadata in addition to operational records.
- Document disaster-recovery runbook and perform scheduled drills.


# 19. Testing and Quality Assurance Strategy


## 19.1 Required test layers

| Layer | Coverage |
| --- | --- |
| Unit | Validation, calculations, state transitions, permission predicates, status derivation, period buckets, expense components, and formatting. |
| Service integration | Database scoping, transactions, side effects, reversals, idempotency, unique constraints, and audit events. |
| API contract | Schemas, error codes, authentication, permissions, pagination, filters, export status, and unknown-field rejection. |
| Tenant security | Cross-tenant IDs and files across every HTTP method, search, reports, exports, jobs, and integrations. |
| RBAC/ABAC | Every role and permission; branch scope; record assignment; amount limits; sensitive-field masking. |
| End-to-end | Onboarding, login/logout, demo, vehicle/driver setup, full trip, fuel, ticket, expense, approval, compliance, and report flows. |
| Visual regression | Desktop and mobile screenshots for core pages, light/dark mode, languages, and validation states. |
| Accessibility | Keyboard, screen reader, contrast, focus, zoom, labels, status messages, and table semantics. |
| Performance/load | Dashboard, search, imports, exports, high record volume, concurrent trip assignment, and background queues. |
| Security | Rate limit, session revocation, CSRF, XSS, upload, headers, secret scan, dependency scan, and lightweight penetration test. |
| Recovery | Migration rollback, backup restore, job retry, provider outage, and partial failure. |


## 19.2 Role test matrix minimum

| Role | Minimum scenarios |
| --- | --- |
| Organisation Admin | All organisation settings, users, roles, branches, deletes/archives, exports, audit, and no platform access. |
| Owner/Management | Dashboards, reports, approvals, disposal, budgets; restricted user/security administration as configured. |
| Fleet Manager | Vehicle/driver/trip operations, approvals within limit, reports, no unrelated finance/security controls. |
| Operations | Create/edit permitted trips and operations only; no maintenance, budget, or user administration unless granted. |
| Maintenance | Service/ticket/tyre/vendor actions only; no unrelated trip or finance mutation. |
| Accounts | Expense, budget, payment, report actions only; no operational mutation unless granted. |
| Driver | Own/assigned trips, fuel, breakdown/accident, documents; no fleet-wide lists or sensitive data. |
| Viewer/Auditor | Read-only permitted modules; exports only if explicitly granted. |
| Platform Admin | Platform-only operations with MFA and audit; cannot silently use ordinary org routes to bypass impersonation controls. |


## 19.3 Regression focus for known defects

- [ ] Rows open correct Vehicle, Driver, and Ticket detail pages with mouse and keyboard.
- [ ] Vehicle Profile and Onboarding Administrator step meet performance budget.
- [ ] All onboarding errors are inline and displayed together.
- [ ] Authenticated users cannot access login/get-started/demo guest screens; logout Back does not show protected content.
- [ ] Enter Demo and Exit Demo work once, show feedback, and isolate data.
- [ ] Dashboard and Fleet Status use identical central status derivation.
- [ ] Charts show complete month buckets and correct labels.
- [ ] Search finds records beyond the first page.
- [ ] Reports and totals do not silently truncate.


# 20. Data Migration, Deployment, and Rollback


## 20.1 Migration preparation

- Profile current collections for missing org_id, duplicate vehicle numbers, invalid statuses, orphaned files, inconsistent odometers, duplicate tickets, and overlapping expenses.
- Back up database and object storage and verify restore before migration.
- Create a dry-run report showing records to change, conflicts, defaults, and manual-review items.
- Do not silently assign uncertain records; place them in a migration exception queue.


## 20.2 Recommended migration sequence

- Add immutable ownership/audit fields and compound indexes without removing old fields.
- Backfill org_id and branch_id with verified mapping.
- Create new permission/membership structures and map existing users.
- Create canonical expense ledger and backfill source-linked entries with duplicate analysis.
- Add workflow history and normalise statuses.
- Add file tenant metadata and scan/validate existing files where possible.
- Run reconciliation reports and obtain approval before switching reads to new structures.
- Switch writes, monitor, then retire old paths only after stable period.


## 20.3 Deployment safety

- Use feature flags for high-risk module transitions and new UI surfaces.
- Prefer backward-compatible expand/migrate/contract database changes.
- Define rollback triggers: elevated error rate, failed tenant tests, financial mismatch, login failure, or data migration inconsistency.
- Keep a documented rollback procedure for code, schema, jobs, and feature flags.
- Run post-deployment smoke tests using separate test organisations and roles.


# 21. Phased Implementation Roadmap

| Phase | Indicative duration | Scope | Exit gate |
| --- | --- | --- | --- |
| Phase 0 - Emergency hardening | 1-3 days | Credential rotation, session revocation, backups, disable simulated live sync, CORS restriction, production freeze. | No known shared/default credential; safe backup available. |
| Phase 1 - Tenant and security foundation | 2-3 weeks | Strict schemas, org isolation, file isolation, action permissions, secure sessions, rate limits, audit logs, tenant tests. | P0 security controls pass. |
| Phase 2 - Workflow and data integrity | 3-5 weeks | Domain services, state machines, transactions, reversals, trip conflicts, mileage recalculation, canonical expenses. | Core workflows cannot be bypassed; reconciliation passes. |
| Phase 3 - Core UX and performance | 3-4 weeks | Dead navigation, route guards, validation, smart sidebar, server search/filter, page speed, mobile core. | Primary desktop/mobile flows pass UX and performance tests. |
| Phase 4 - SaaS onboarding and platform | 4-6 weeks | Provisioning pipeline, owner control plane, organisation memberships, feature flags, entitlement layer, isolated demo. | External beta organisations can be governed safely. |
| Phase 5 - Financial intelligence and reporting | 3-5 weeks | Expense ledger UI, approval/payment, multidimensional insights, professional reports, scheduled exports. | Finance totals reconcile and drill through to source. |
| Phase 6 - Communications, i18n, and first integrations | 4-8 weeks | Email/OTP/WhatsApp, imports, OCR, EN/HI/MR/KN, notification centre. | Onboarding and compliance alerts operate end to end. |
| Phase 7 - Commercial and advanced moat | Ongoing | Razorpay, GST billing, GPS, FASTag live providers, accounting integration, offline PWA, predictive maintenance, white-label. | Commercial plan and advanced integrations released under feature flags. |


## 21.1 Parallel workstreams

- Security/backend workstream: tenant isolation, authentication, authorization, files, audit, state machines.
- Frontend/design workstream: design system, route guards, forms, data grids, mobile, accessibility.
- Data/analytics workstream: canonical expenses, status derivation, queries, indexes, reports, migration.
- Platform/operations workstream: owner console, entitlements, environments, CI/CD, observability, backups.
- QA workstream begins in Phase 0 and writes tests before or alongside each fix.


# 22. Definition of Done and Production Release Gates


## 22.1 Definition of Done for every task

- [ ] Requirement and acceptance criteria are documented.
- [ ] Backend permission, tenant scope, validation, audit, and error handling are implemented.
- [ ] Frontend includes loading, empty, error, permission, mobile, keyboard, and accessibility states.
- [ ] Unit/integration/E2E tests are added and passing.
- [ ] No existing feature regression; relevant screenshots and test evidence are attached.
- [ ] Migration and rollback impact is documented.
- [ ] No TODO, placeholder, fake provider, hardcoded customer name, test credential, or hidden unfinished flow remains.
- [ ] Code is reviewed, merged through protected branch, deployed to staging, and smoke-tested.


## 22.2 Beta release gates

- [ ] All P0 controls are closed and tenant-isolation penetration tests pass.
- [ ] No hardcoded credentials or production fake integrations.
- [ ] Secure sessions, rate limiting, password reset, and administrator MFA available.
- [ ] Critical workflows use state machines and cannot be bypassed by generic update.
- [ ] Files and exports are organisation-scoped.
- [ ] Primary desktop and mobile flows pass E2E and accessibility checks.
- [ ] Backups and one full restore drill are complete.
- [ ] Monitoring, alerting, incident contacts, privacy policy, terms, and support channel exist.


## 22.3 General availability gates

- [ ] No known critical or high security vulnerability.
- [ ] Independent security review or lightweight penetration test completed.
- [ ] Performance budgets met at expected customer volume.
- [ ] Canonical expense totals reconcile to source transactions.
- [ ] All eight organisation roles and platform roles pass permission matrix.
- [ ] Imports, exports, notifications, and background jobs have retry and failure visibility.
- [ ] Disaster-recovery drill meets defined objectives.
- [ ] Release notes, user documentation, onboarding guidance, and support procedures are ready.


# 23. Instructions for Emergent and Claude Code

> **Implementation mandate**  
> Complete the application, do not merely redesign screens. Preserve working features, close all process flows, eliminate security risks, and provide test evidence. Do not leave TODOs, placeholder buttons, fake live data, partial workflows, or inconsistent role behaviour.


## 23.1 Working method

- Create a dedicated upgrade branch and commit small, logically grouped changes with clear messages.
- Before coding, produce a current route/endpoint/collection/permission inventory and map it to requirements in this document.
- For each phase, create a checklist with requirement ID, files changed, migration, tests, screenshots, known limitations, and rollback.
- Write failing tests for security and workflow defects before the fix where practical.
- Do not alter production data directly without migration script, dry run, backup, and reconciliation output.
- Use feature flags for unfinished new modules; hidden code is not considered complete.
- Run all automated tests, build, lint, dependency scan, and staging smoke test before each merge.


## 23.2 Required final output from each phase

| Deliverable | Required content |
| --- | --- |
| Change summary | What was changed, why, and which requirement IDs are closed. |
| Files and migrations | Exact files, schema/index changes, and migration commands. |
| Security evidence | Tenant/RBAC tests, header checks, secret scan, file tests, and unresolved risks. |
| QA evidence | Automated test result, screenshots by viewport/role, performance measurements, and manual scenarios. |
| Data reconciliation | Counts and totals before/after for affected modules. |
| Deployment and rollback | Environment variables, deployment steps, smoke tests, rollback steps. |
| Open items | Only explicitly accepted deferred items with owner and date; no vague “later” items. |


## 23.3 Prohibited shortcuts

- Do not rely on hidden frontend buttons as permission enforcement.
- Do not pass org_id from the client or trust any client ownership field.
- Do not allow status, approval, payment, balance, odometer, or audit fields in generic updates.
- Do not fabricate live provider data.
- Do not silence errors, swallow exceptions, or show raw backend errors to users.
- Do not mark a task complete without tests and staging evidence.
- Do not replace working business logic with visual mock-ups or static data.


# 24. Traceability Matrix

| Source ID | Original concern | Master-plan control | Phase |
| --- | --- | --- | --- |
| BUG-01 | Dead master rows | UX-ROW, data-grid standard, E2E regression | Phase 3 |
| BUG-02 | Render freeze | Performance budgets, lazy rendering, profiling | Phase 3 |
| BUG-03 / VAL-01 | Validation defects | Form standard and onboarding UX | Phase 3 |
| BUG-04 / STATUS-01 | Conflicting status metrics | Central status derivation service | Phase 2 |
| BUG-05 / CHART-01 | Month labels/buckets | Time-bucket service and visual tests | Phase 3 |
| BUG-12 / ROUTE-01 | Guest/protected routing | Unified route/session guards | Phase 3 |
| BUG-13 / DEMO-01 | Flaky demo | Isolated idempotent demo sessions | Phase 4 |
| SEC-01 | Default credentials | Authentication lifecycle and release freeze | Phase 0-1 |
| TEN-01 | Mass assignment/tenant risk | Strict schemas and tenant isolation controls | Phase 1 |
| FILE-01 | File isolation | File security service and tenant metadata | Phase 1 |
| AUTH-01 | localStorage tokens | Secure cookie sessions and CSRF | Phase 1 |
| AUTHZ-01 | Broad role tiers | Action permission engine | Phase 1 |
| FASTAG-01 | Random sync | Demo-only simulation and provider framework | Phase 0 / 6 |
| WF-01 | Workflow bypass | Domain actions and state machines | Phase 2 |
| DATA-01 | Trip conflicts | Trip state machine and availability locks | Phase 2 |
| FUEL-01 | Mileage integrity | Tank-to-tank model and recalculation | Phase 2 |
| EXP-01 | Expense duplicates | Canonical source-linked ledger | Phase 2 / 5 |
| SEARCH-01 | Current-page search | Server data-grid APIs | Phase 3 |
| PERF-02 | N+1 and record caps | Aggregations and async reports | Phase 2-3 |
| ONB-01 | Incomplete SaaS onboarding | Provisioning and approval pipeline | Phase 4 |
| PLATFORM-01 | No owner console | Platform control plane | Phase 4 |


---


# Appendix A. Prioritised Implementation Backlog

| Priority | ID | Task | Owner | Status |
| --- | --- | --- | --- | --- |
| P0 | SEC-01 | Remove default credentials; rotate passwords; revoke sessions | Backend/Security | **OPEN P0 BLOCKER.** SEC-001 code done; SEC-002 tooling done; SEC-003 scanning done. SEC-004 (production rotation) is BLOCKED: OPERATOR-LED PRODUCTION ACTIVITY — no production operator environment is available. SEC-005 (history rewrite) BLOCKED BY SEC-004. |
| P0 | TEN-01 | Reject org_id/protected fields and force server ownership | Backend | Repository work complete on `feature/ten-01-tenant-ownership` (PR open) — canonical protected-field policy, forced server-derived ownership, fail-closed DB guard, 106 tests. Fixed a live cross-tenant record-transfer defect. |
| P0 | FILE-01 | Tenant-scope files and downloads | Backend | Repository work complete on `feature/file-01-tenant-file-security` (PR open) — `files` tenant-scoped, per-uploader ownership migration, type/signature allowlist, safe download headers, 76 tests. Fixed a live cross-tenant file-disclosure defect. Exceptions: no malware scanning, no signed URLs, no linked-record ACL (AUTHZ-01). |
| P0 | AUTH-01 | Secure cookie session, CSRF, TTL, device management | Full stack | Repository work complete on `feature/auth-01-secure-sessions` (PR open) — hashed tokens, HttpOnly cookies, double-submit CSRF, idle+absolute expiry, rotation, revoke one/all, TTL indexes, login throttling, CORS allowlist, 56 tests. Fixed plaintext session storage and unbounded sliding expiry. Exception: no self-service password reset (no mail transport). |
| P0 | AUTHZ-01 | Action-level permission engine and endpoint inventory | Backend | Repository work complete on `feature/authz-01-permission-engine` (PR open) — canonical `resource:action` catalogue, role→permission map, `require_permission` on every mutating endpoint (AST-guarded), platform/org separation, role-change audit + revocation, 52 tests, mutation-tested. Behaviour preserved (492 prior tests green). |
| P0 | FASTAG-01 | Disable simulated sync in live organisations | Backend | Repository work complete on `feature/fastag-01-demo-simulation` (PR open) — simulation fails closed off the demo org (403, no writes), idempotent, computed (not random) balance, audited; demo/manual/live-provider paths separated. 21 tests, mutation-tested. Live-verified real-org 403. |
| P0 | WF-01 | Protect status/approval/payment fields from generic updates | Backend | Repository work complete on `feature/wf-01-workflow-transitions` (PR open) — shared transition engine (state graphs, role-gated, idempotent, versioned, audited); generic updates cannot bypass workflows; no-workflow features documented not invented. 35 tests, mutation-tested. |
| P1 | TEN-TEST | Automated cross-tenant test suite | QA/Security | Repository work complete on `feature/ten-test-isolation-matrix` (PR open) — 188 real-HTTP two-org isolation tests, registry-driven so new modules must register, mutation-tested. Found and fixed two real defects in `auth.py`. |
| P1 | BUG-01 | Row navigation and actions | Frontend | Not started |
| P1 | BUG-02 | Profile/onboarding performance profiling and fixes | Frontend | Not started |
| P1 | VAL-01 | Schema-driven inline validation across forms | Frontend/Backend | Not started |
| P1 | ROUTE-01 | Guest/protected route guards and Back handling | Frontend | Not started |
| P1 | DEMO-01 | Reliable isolated demo session | Full stack | Not started |
| P1 | TRIP-01 | Trip state machine and resource conflicts | Backend | Not started |
| P1 | FUEL-01 | Full-tank mileage and recalculation | Backend/Data | Not started |
| P1 | SIDEFX-01 | Reversible FASTag/tyre/downtime/odometer side effects | Backend | Not started |
| P1 | EXP-01 | Canonical expense ledger and source keys | Backend/Data | Not started |
| P1 | SEARCH-01 | Server-side data-grid APIs | Full stack | Not started |
| P1 | MOBILE-01 | Mobile primary workflows | Frontend | Not started |
| P1 | PERF-02 | Indexes, aggregation, async exports, remove caps | Backend/Data | Not started |
| P2 | ONB-01 | Save/resume, verification, approval and provisioning | Full stack | Not started |
| P2 | PLATFORM-01 | Platform owner console | Full stack | Not started |
| P2 | ENT-01 | Entitlement service and Free plan | Backend/Frontend | Not started |
| P2 | DESIGN-01 | Design system, sidebar, dark mode, accessibility | Frontend/Design | Not started |
| P2 | REPORT-01 | Organisation-aware professional reports | Full stack | Not started |
| P2 | I18N-01 | English/Hindi/Marathi/Kannada | Frontend/Content | Not started |
| P3 | COMM-01 | Email, OTP, WhatsApp, notification centre | Full stack | Deferred |
| P3 | IMPORT-01 | Bulk import and validation report | Full stack | Deferred |
| P3 | OCR-01 | Document OCR and expiry extraction | Integration | Deferred |
| P3 | BILL-01 | Razorpay and GST billing | Platform/Finance | Deferred |
| P3 | GPS-01 | GPS/telematics provider framework | Integration | Deferred |
| P3 | FASTAG-LIVE | Live FASTag provider/import reconciliation | Integration | Deferred |


# Appendix B. Security and Tenant-Isolation Test Matrix

| Test | Scenario | Surface | Expected result |
| --- | --- | --- | --- |
| T-01 | Read Organisation B vehicle from Organisation A | GET /vehicles/{id} | 404/403; no metadata leakage |
| T-02 | Update Organisation B vehicle from Organisation A | PUT/PATCH | 404/403; B record unchanged |
| T-03 | Attempt org_id transfer on own record | PUT with org_id | 400 validation error; ownership unchanged |
| T-04 | Download Organisation B file | GET /files/{id} | 404/403; no signed URL issued |
| T-05 | Search Organisation B identifier | Global search | No cross-tenant result |
| T-06 | Export report with Organisation B ID/filter | Report/export | 404/403; no job/file created |
| T-07 | Background export context | Queued export | Output contains only requesting org data |
| T-08 | Driver requests full fleet list | Vehicle lookup | Only assigned/authorised lookup fields |
| A-01 | Operations user writes maintenance record directly | POST/PUT service | 403 without permission |
| A-02 | Maintenance user writes expense/budget | POST expense/budget | 403 without permission |
| A-03 | Viewer attempts mutation | Any POST/PUT/PATCH/DELETE | 403 |
| A-04 | Ticket status changed via generic PUT | PUT repair status | 400/403; action endpoint required |
| A-05 | User escalates role in request body | PUT user/own profile | 400/403; role unchanged |
| S-01 | Brute-force login | Repeated invalid attempts | Rate limit/lockout; safe message |
| S-02 | Password change role revocation | Change password/role | Old sessions immediately invalid |
| S-03 | Browser Back after logout | SPA navigation | Protected content not rendered |
| F-01 | Upload executable renamed as PDF | Upload | Rejected by signature validation |
| F-02 | Upload malware test fixture | Upload | Quarantined/rejected; no download |
| F-03 | Unsafe filename header injection | Upload/download | Filename sanitised; headers safe |
| X-01 | Stored XSS payload in notes | Create/view | Rendered as text or sanitised |
| C-01 | Cross-origin credential request | CORS | Blocked except approved origin |
| R-01 | Replay onboarding/payment request | Idempotent action | Single organisation/payment event |


# Appendix C. Role and Permission Model

| Role | Default scope |
| --- | --- |
| Organisation Admin | All organisation permissions except platform controls; sensitive exports and destructive actions may require MFA. |
| Owner / Management | Dashboards, reports, approvals, disposal, budgets, organisation preferences; user/security management only if granted. |
| Fleet Manager | Vehicles, drivers, trips, maintenance oversight, approvals within limit, reports. |
| Operations | Trips, fuel, assigned operational records, basic documents; no maintenance/finance administration by default. |
| Maintenance | Services, repair tickets, tyres, maintenance vendors, downtime; read vehicle context. |
| Accounts | Expenses, budgets, payments, financial reports, vendor tax details; read operational source references. |
| Driver | Own profile, assigned vehicle/trips, fuel, breakdown, accident, POD/doc uploads; no fleet-wide sensitive data. |
| Viewer / Auditor | Read-only selected modules, audit/report access as granted, no mutation. |
| Platform Support | Platform support and audited impersonation; no subscription/security changes unless separately granted. |
| Platform Admin | Organisation, plan, feature flag, system health, support, and security controls with MFA. |


## C.1 Permission evaluation order

```text
1. Is session valid and active?
2. Is organisation active and subscription/entitlement valid?
3. Does the role/membership contain the required action permission?
4. Is the requested record in the session organisation?
5. Is the record within permitted branch/department/assignment scope?
6. Is the action allowed in the current workflow state?
7. Are amount limits, segregation rules, and recent-authentication requirements satisfied?
8. Execute domain action atomically and write audit event.
```


# Appendix D. Final Release Checklist


## D.1 Security and privacy

- [ ] No default or test credentials in production, repository, documentation, or reports.
- [ ] Cross-tenant test matrix passes for all resources, files, reports, exports, and jobs.
- [ ] Secure cookie sessions, CSRF, rate limits, password reset, MFA, and session revocation pass.
- [ ] Action permissions cover every mutating endpoint.
- [ ] Uploads are tenant-scoped, validated, scanned, and safely served.
- [ ] Security headers, secret scanning, dependency scanning, and audit logs are verified.
- [ ] Privacy policy, terms, consent records, retention, export, and deletion process are available.


## D.2 Data and workflows

- [ ] Trip, repair, expense, vehicle, driver, tyre, FASTag, and onboarding state machines pass end-to-end tests.
- [ ] Protected workflow fields cannot be changed through generic updates.
- [ ] Financial entries are source-linked, unique, reversible, approved, and reconciled.
- [ ] Odometer and mileage correction/rebuild tests pass.
- [ ] No report or dashboard silently truncates data.


## D.3 Product and UX

- [ ] Brand is FleetFlow throughout; organisation reports use tenant branding.
- [ ] All rows/actions work and no empty action columns remain.
- [ ] All forms use inline validation and safe errors.
- [ ] Desktop, tablet, and mobile primary flows pass at required widths.
- [ ] Accessibility, keyboard, zoom, light/dark, and initial languages pass review.
- [ ] No unfinished button, dead link, placeholder, fake live integration, or TODO remains visible.


## D.4 Operations

- [ ] Development, staging, demo, and production are separated.
- [ ] CI/CD checks and protected branch rules are active.
- [ ] Monitoring, alerting, logs, queues, health checks, and support contacts are ready.
- [ ] Backup and restore drill completed successfully.
- [ ] Deployment and rollback runbooks are approved.
- [ ] Release notes, help content, onboarding guidance, and incident procedures are published internally.


## D.5 Final certification statement

> **Release certification**  
> FleetFlow may be called a global-standard production release only after every P0 item is closed, all release gates are evidenced, financial and tenant reconciliation passes, and no critical/high security issue remains open.
