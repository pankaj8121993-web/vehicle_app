# FleetFlow — Critical Security Release Gate (SEC-CLOSEOUT)

**Prepared by:** autonomous security programme.
**Date:** 20 July 2026.
**Baseline:** `develop` after WF-01 (`79c27dd`) + this closeout branch.
**`main`:** unchanged at `157dde5` throughout the programme.
**Production accessed:** No.

---

## Release decision

```
Repository security hardening:   Complete
Production security operations:  Incomplete
Production release approval:     Blocked pending SEC-004 and SEC-005
```

### Repository controls completed

- Secure bootstrap (SEC-001)
- Credential-rotation tooling (SEC-002)
- Secret scanning (SEC-003)
- Tenant ownership (TEN-01)
- File isolation (FILE-01)
- Secure authentication and sessions (AUTH-01)
- Tenant-isolation matrix (TEN-TEST)
- Minimum action authorisation (AUTHZ-01)
- Demo-only FASTag simulation (FASTAG-01)
- Critical workflow-field protection (WF-01)

### Operational controls incomplete

- SEC-004 — production credential rotation and session revocation
- SEC-005 — historical-secret removal from Git history

Every repository-side P0 control below is implemented, tested and merged into
`develop`. Two controls require a **live production operator environment** that
does not exist here — **SEC-004** (rotate the already-known legacy credentials in
the live database and revoke their sessions) and **SEC-005** (remove those
historical values from Git history). Until both are executed and verified,
FleetFlow is **not** production-ready, regardless of how complete the code is.
This document does not, and must not, claim otherwise.

**Test evidence baseline:** the full backend suite is **606 passed, 3 skipped**.
The 3 skips are live-URL integration tests that need a running deployment and
credentials (they are not unit-level gaps). Gitleaks is clean across history.

---

## P0 control reconciliation

Legend — **Prod. verified:** whether the control has been confirmed against a
real production environment (as opposed to code + the preview container).

### 1. Default credentials removed

- **Workstream:** SEC-001 · **PR #1**
- **Implementation:** `backend/bootstrap.py`; startup seeding removed from
  `server.py`; org-scoped last-admin delete guard.
- **Test evidence:** `test_bootstrap.py`.
- **Prod. verified:** N/A (code) — but see SEC-004: legacy rows may persist in
  the live DB.
- **Exception / decision:** Merged. Closed at code level.

### 2. Credential-rotation tooling

- **Workstream:** SEC-002 · **PR #2** · merge `f648e64`
- **Implementation:** `backend/rotate_legacy_credentials.py`;
  `docs/implementation/CREDENTIAL_ROTATION.md`.
- **Test evidence:** `test_rotate_legacy_credentials.py` (34).
- **Prod. verified:** No. **Exception:** tooling only.

### 3. Production credential rotation + session revocation

- **Workstream:** **SEC-004** · **BLOCKED — OPERATOR-LED PRODUCTION ACTIVITY**
- **Implementation:** runbook ready (SEC-002).
- **Prod. verified:** **No — NOT EXECUTED.** No production DB is reachable from
  the preview container (`mongodb://localhost:27017/test_database` is a local
  dev DB, not production).
- **Exception / decision:** **OPEN P0 RELEASE BLOCKER.** Must be run by an
  operator with production credentials and connectivity.

### 4. Secret scanning

- **Workstream:** SEC-003 · **PR #3** · merge `334fde4`
- **Implementation:** `.github/workflows/secret-scan.yml` (gitleaks 8.30.1,
  SHA-pinned), `.gitleaks.toml`, `scripts/scan-secrets.sh`.
- **Test evidence:** `test_secret_scanning.py`; tracked tree scans clean.
- **CI:** gitleaks required-status workflow runs on push + PR.
- **Prod. verified:** N/A. **Decision:** Closed.

### 5. Historical-secret remediation (Git history)

- **Workstream:** **SEC-005** · **BLOCKED BY SEC-004 — OPERATOR-LED DESTRUCTIVE**
- **Implementation:** procedure prepared in `SECRET_SCANNING.md`;
  `git-filter-repo` available.
- **Prod. verified:** **No — NOT EXECUTED.** Preconditioned on SEC-004.
- **Exception / decision:** **OPEN P0 RELEASE BLOCKER.**

### 6. Tenant ownership / mass-assignment

- **Workstream:** TEN-01 · **PR #4** · merge `d9ffc09`
- **Implementation:** `backend/tenant_policy.py`; forced server-derived ownership
  on insert; fail-closed ownership-write guard on update; protected-field
  rejection.
- **Test evidence:** `test_tenant_ownership.py` (106).
- **Mutation:** removing `vehicles` from `TENANT_COLLECTIONS` fails the isolation
  matrix (incl. "A deleted B's record").
- **Decision:** Closed. Fixed a **live cross-tenant record-transfer P0**.

### 7. File isolation

- **Workstream:** FILE-01 · **PR #5** · merge `ea489f9`
- **Implementation:** `files` tenant-scoped; `backend/file_policy.py` (type
  allowlist, magic-byte detection, filename sanitisation, org-namespaced storage
  names, safe download headers, SHA-256); per-uploader ownership migration.
- **Test evidence:** `test_file_security.py` (76).
- **Prod. verified:** No — the ownership backfill migration has **not** run
  against production (see SEC-004 for the general production-data caveat).
- **Decision:** Code closed; fixed a **live cross-tenant file-disclosure P0**.
  **Exception:** production migration pending a production run.

### 8. Authentication and cookies

- **Workstream:** AUTH-01 · **PR #6** · merge `ffd465c`
- **Implementation:** `backend/session_security.py`; SHA-256 hashed tokens;
  HttpOnly cookies; idle+absolute expiry; rotation; frontend off `localStorage`.
- **Test evidence:** `test_auth_sessions.py` (56); live smoke.
- **Decision:** Closed. Fixed **plaintext session storage** (a dump yielded live
  sessions) and unbounded expiry.

### 9. CSRF

- **Workstream:** AUTH-01
- **Implementation:** double-submit token; enforced on cookie-authenticated
  state changes; empty values never validate.
- **Test evidence:** `test_auth_sessions.py` + live smoke (**forged write 403,
  legitimate 200**).
- **Decision:** Closed.

### 10. Session expiry, revocation and cache invalidation

- **Workstream:** AUTH-01 (+ TEN-TEST fix)
- **Implementation:** TTL index on `absolute_expires_at`; single
  `revoke_user_sessions` path that evicts the in-memory cache; revocation on
  password/role/activation/deletion.
- **Test evidence:** `test_auth_sessions.py`; TEN-TEST found and fixed
  `delete_user` not evicting the cache.
- **Decision:** Closed.

### 11. User deletion / deactivation effects

- **Workstream:** AUTH-01, TEN-TEST
- **Implementation:** deletion, deactivation and role change all revoke sessions
  and evict the cache.
- **Test evidence:** `test_tenant_isolation_matrix.py` (admin cannot disable
  another org's admin); `test_auth_sessions.py`.
- **Decision:** Closed. **Exception:** organisation *suspension* does not exist
  as a concept yet — its revocation hook (`revoke_user_sessions`) is ready.

### 12. Action-level authorisation

- **Workstream:** AUTHZ-01 · **PR #8** · merge `e47db5a`
- **Implementation:** `backend/permissions.py` (canonical `resource:action`
  catalogue, role→permission map, `require_permission` on every mutating
  endpoint, platform/org separation); role-change audit + revocation.
- **Test evidence:** `test_authz_permissions.py` (34) +
  `test_authz_enforcement.py` (18 real-HTTP per-role).
- **Mutation:** removing `make_crud`'s create permission lets a driver create a
  service and trips the AST wiring guard.
- **Decision:** Closed. Frontend visibility is not treated as security.

### 13. FASTag simulation

- **Workstream:** FASTAG-01 · **PR #9** · merge `b4bb793`
- **Implementation:** `backend/fastag_simulation.py`; fail-closed off the demo
  org (403, no writes); idempotent; computed (not random) balance; audited.
- **Test evidence:** `test_fastag_simulation.py` (21) + matrix; live smoke
  (**real-org sync 403**).
- **Mutation:** disabling the demo guard fails both unit and real-HTTP layers.
- **Decision:** Closed. Fixed a **P0** — fabricated financial activity + balance
  corruption in real tenants.

### 14. Protected workflows

- **Workstream:** WF-01 · **PR #10** · merge `79c27dd`
- **Implementation:** `backend/workflow.py` (state graphs for repairs, vehicles,
  drivers, downtime, trips); generic updates validated against the graph;
  role-gated, idempotent, versioned, audited transitions.
- **Test evidence:** `test_workflow_transitions.py` (35).
- **Mutation:** disabling the edge check fails 6 tests (incl. real-HTTP
  un-dispose, downtime-reopen).
- **Decision:** Closed. No expense-approval/payment workflow exists — documented,
  not invented (`WORKFLOWS.md`).

### 15. Cross-tenant isolation test matrix

- **Workstream:** TEN-TEST · **PR #7** · merge `dc4d3c5`
- **Implementation:** `test_tenant_isolation_matrix.py` — real-HTTP, two-org,
  registry-driven; a build-guard forces new tenant collections to register.
- **Test evidence:** 188+ cross-tenant assertions; **mutation-verified**.
- **Decision:** Closed. Found and fixed two real `auth.py` defects.

### 16. CORS allowlisting

- **Workstream:** AUTH-01
- **Implementation:** `allow_credentials` enabled **only** with an explicit
  origin allowlist; wildcard/unset disables credentialed cross-origin and warns.
- **Test evidence:** `test_auth_sessions.py`
  (`test_credentials_are_not_allowed_with_wildcard_origin`).
- **Prod. verified:** No — **exception:** production must set `CORS_ORIGINS` to
  its real frontend origin(s). Documented in `AUTHENTICATION.md`.

### 17. Security headers

- **Workstream:** SEC-CLOSEOUT (this branch)
- **Implementation:** app-wide middleware in `server.py` — `nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, HSTS in production;
  file downloads add stricter CSP/`no-store`.
- **Test evidence:** `test_security_headers.py` (5); live-verified.
- **Decision:** Closed.

### 18. Debug / auto-seed / fake-integration production controls

- **Assessment:** No debug endpoints; startup never seeds users/orgs (first admin
  is manual via `bootstrap.py`); the demo org is seeded **on demand** via
  `/demo/enter` and is tenant-isolated; the fake FASTag integration is now
  demo-only (FASTAG-01). `--reload` is a dev-runner flag, not app code.
- **Decision:** Closed at code level. **Exception:** production must run the
  backend without `--reload` and with `APP_ENV=production` (enables cookie
  `Secure` + HSTS).

### 19. Environment separation

- **Implementation:** `APP_ENV` gates cookie `Secure` and HSTS;
  `FLEETFLOW_CROSS_SITE_COOKIES` for split-origin deployments; `CORS_ORIGINS`
  allowlist; secrets via env (`MONGO_URL`, `DB_NAME`, `.env` git-ignored).
- **Decision:** Mechanisms in place. **Exception:** production must set
  `APP_ENV=production` and the allowlist — a deployment-config responsibility.

### 20. Backup and restore readiness

- **Workstream:** SEC-002 runbook.
- **Decision:** Documented. **Exception:** no production backup has been taken or
  restore-tested (part of the SEC-004 operator activity).

### 21. Branch protection and required checks

- **Assessment:** `main` and `develop` are **NOT** branch-protected;
  the gitleaks workflow runs but is not a *required* status check.
- **Prod. verified:** No.
- **Exception / decision:** **OPEN control gap.** Deliberately **not** enabled
  autonomously: turning on required reviews/checks is a repository-governance
  decision that can disrupt the maintainer's workflow. **Recommended before
  production:** protect `main` (and `develop`), require the secret-scan check and
  a PR review, and disallow force-pushes — except during the approved SEC-005
  history rewrite, which explicitly toggles and restores protection.

### 22. Security audit logging

- **Workstreams:** SEC-002 (rotation), AUTHZ-01 (role/permission changes),
  WF-01 (transitions), FASTAG-01 (simulation).
- **Implementation:** shared `security_audit` collection;
  `auth.record_security_event` records action + ids only, **never** secrets.
- **Test evidence:** `test_authz_permissions.py`
  (`test_security_event_records_no_secrets`).
- **Decision:** Closed for the security-sensitive actions above. **Exception:**
  no general request/access log aggregation or alerting pipeline — an operational
  (P1/ops) concern, not a P0 control.

---

## Open exceptions carried to production

| # | Exception | Owner | Blocks release? |
| --- | --- | --- | --- |
| 1 | **SEC-004** production credential rotation + session revocation | Operator | **Yes (P0)** |
| 2 | **SEC-005** Git-history secret removal | Operator | **Yes (P0)** |
| 3 | FILE-01 ownership-backfill migration not run in production | Operator | Yes, until run |
| 4 | Branch protection + required checks not enabled | Maintainer | Recommended |
| 5 | Production env config (`APP_ENV=production`, `CORS_ORIGINS`, no `--reload`) | Deployer | Yes, until set |
| 6 | Production backup taken + restore-tested | Operator | Yes (part of SEC-004) |

Deferred (not P0 release blockers): organisation-suspension concept; self-service
password reset (no mail transport); odometer-decrease rejection on generic
update; `_version` on vehicle/driver transitions; general access-log aggregation;
removal of the AUTH-01 bearer-token migration fallback.

---

## Conclusion

The **repository-side critical security programme is complete**: eight P0
workstreams (TEN-01, FILE-01, AUTH-01, AUTHZ-01, FASTAG-01, WF-01, TEN-TEST,
SEC-CLOSEOUT) merged into `develop`, each tested and — for the security-critical
controls — mutation-verified, having closed **four live P0 vulnerabilities**
found in the process (cross-tenant record transfer, cross-tenant file disclosure,
plaintext session tokens, and demo-simulation financial fabrication) plus two
session-lifecycle defects.

**Production is NOT approved for release.** SEC-004 and SEC-005 are operator-led
activities that have not been executed, and the production-configuration and
backup exceptions above remain open. `main` is untouched; promoting `develop` to
a production release is a separate, gated decision that must not be taken until
the P0 exceptions are closed and independently verified.
