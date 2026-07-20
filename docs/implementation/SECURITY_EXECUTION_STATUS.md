# FleetFlow — Security Execution Status

**Purpose:** Persistent source of truth for the critical security programme across
working sessions. Read this together with `MASTER_PLAN.md` and the relevant
runbook before resuming any workstream.

**Last updated:** 16 July 2026

> **Rule of this document:** preparation and tooling are never recorded as
> production execution. A workstream that has shipped code but has not been run
> against production is recorded as *prepared*, not *complete*.

---

## Summary

| ID | Workstream | Status | Production executed |
| --- | --- | --- | --- |
| SEC-001 | Secure bootstrap / remove default credentials | Merged | N/A (code only) |
| SEC-002 | Credential-rotation tooling | Merged | **No** |
| SEC-003 | Secret scanning + history-remediation prep | Merged | **No** (rewrite not executed) |
| SEC-004 | Production legacy credential rotation | **BLOCKED: OPERATOR-LED PRODUCTION ACTIVITY** | **No** |
| SEC-005 | Git-history sensitive-data removal | **BLOCKED BY SEC-004: OPERATOR-LED DESTRUCTIVE ACTIVITY** | **No** |
| TEN-01 | Tenant ownership / mass-assignment | **Merged** (PR #4, `d9ffc09`) | N/A |
| FILE-01 | Tenant-scoped file security | **Merged** (PR #5, `ea489f9`) | N/A |
| AUTH-01 | Secure session lifecycle | **Merged** (PR #6, `ffd465c`) | N/A |
| AUTHZ-01 | Action-level permission engine | **Merged** (PR #8, `e47db5a`) | N/A |
| FASTAG-01 | Demo-only simulation protection | In progress — PR open | N/A |
| WF-01 | Protected workflows | Not started | N/A |
| TEN-TEST | Cross-tenant security matrix | In progress — PR open | N/A |
| SEC-CLOSEOUT | Critical security release gate | Not started | N/A |

---

## SEC-001 — Secure bootstrap

- **Status:** Complete and merged.
- **Branch:** `feature/sec-001-secure-bootstrap` (merged via PR #1).
- **Scope:** Removed hardcoded default users/passwords and startup seeding;
  added `backend/bootstrap.py` manual first-admin provisioning; org-scoped
  last-admin deletion guard; redacted committed credentials.
- **Production impact:** None. Code-only.
- **Remaining risk:** Legacy `created_by:"system"` rows may still exist in live
  databases with known passwords. That is SEC-004's problem, not SEC-001's.

## SEC-002 — Credential-rotation tooling

- **Status:** Tooling complete and merged. **Production rotation NOT executed.**
- **Branch:** `feature/sec-002-credential-rotation` (merged via PR #2).
- **Merge commit:** `f648e64`.
- **Deliverables:** `backend/rotate_legacy_credentials.py` (647 lines),
  `docs/implementation/CREDENTIAL_ROTATION.md`,
  `backend/tests/test_rotate_legacy_credentials.py` (34 tests).
- **Production impact:** None. No production data has been touched.

## SEC-003 — Secret scanning and history-remediation preparation

- **Status:** Complete and merged. **History rewrite NOT executed.**
- **Branch:** `feature/sec-003-secret-scanning` (deleted after merge).
- **PR:** #3 — merged 2026-07-16T08:00:32Z.
- **Head SHA:** `5cf03ebc0fc0229f5fc0f1ce6889c292ab8948d8` (matches expected).
- **Merge commit:** `334fde42326907e97bf6c8bd091d1acac805074a`.
- **Scope:** Nine files, as expected — secret-scan workflow, `.gitleaks.toml`,
  `.gitignore` hardening, two fixtures, `test_secret_scanning.py`,
  `scan-secrets.sh`, and two docs.
- **Verification:** `develop` and `origin/develop` both at `334fde4`;
  `main` unmodified at `157dde5`; feature branch deleted locally and remotely.
- **Production impact:** None.
- **Remaining risk:** Legacy default-password values remain in pre-SEC-001 Git
  history. Removal is SEC-005 and requires an approved, coordinated rewrite.

---

## SEC-004 — BLOCKED: OPERATOR-LED PRODUCTION ACTIVITY

**This is a permanent classification, not a temporary state.** SEC-004 will be
executed separately by an operator using the merged SEC-002 runbook when a
genuine production operator environment with production connectivity exists. It
is not attempted from the Emergent preview container, and the live-execution
approval gate is not raised again until such an environment is available.

**SEC-004 remains an open P0 release blocker.** It must appear as such in
`MASTER_PLAN.md` and in `SECURITY_RELEASE_GATE.md` at closeout. It does not block
independent repository-side workstreams, which continue in parallel.

### Why it is blocked

The rotation command resolves its target database from the environment
(`rotate_legacy_credentials._connect()` reads `MONGO_URL` and `DB_NAME`). In
this container those resolve to:

- `MONGO_URL` → `mongodb://localhost:27017` — a `mongod` running **inside this
  same container**, supervised locally (`supervisorctl` group `mongodb`).
- `DB_NAME` → `test_database`.

There is no production connection string, no staging target, and no evidence
that a production database is network-reachable from here. Running the rotation
command in this container would modify a local development database and would
**not** constitute a production rotation. Recording it as one would be a false
claim of production work.

**Consequence:** the `APPROVE LIVE SEC-004 EXECUTION` gate is not meaningful for
the coding agent. Approval alone would not grant production access. SEC-004 must
be executed by an operator who holds production credentials, from an environment
with production network reachability, following
`docs/implementation/CREDENTIAL_ROTATION.md`.

### Preview-container facts — NOT production architecture

> **These describe the Emergent preview/development container only.** They are
> recorded to explain why SEC-004 cannot run here. **None of them may be cited as
> FleetFlow production architecture**, and the production operator must establish
> each fact independently against the real environment.

| Question | Preview container (NOT production) |
| --- | --- |
| Backend process | `uvicorn server:app --host 0.0.0.0 --port 8001`, supervisor program `backend` |
| Restart procedure | `supervisorctl restart backend` |
| Health check | `GET /api/` (`server.py`, `api_router.get("/")`) |
| Mongo target | `mongodb://localhost:27017` — a `mongod` inside this same container |
| Database name | `test_database` |
| Backup tool | `mongodump` present at `/usr/bin/mongodump` |
| Encrypted backup location | None designated |
| Staging / restored copy | None available |

### What the operator must supply before SEC-004 can proceed

1. Production `MONGO_URL` and `DB_NAME`, supplied **via the operator's own
   environment** — never pasted into chat, a repository file, or a log.
2. Confirmation of the production restart procedure and health-check URL.
3. A designated encrypted backup destination with a retention policy.
4. A maintenance window.
5. Ideally a restored production copy in an isolated environment, so the runbook
   can be rehearsed against realistic data before touching production.

### Repository-side work still open for SEC-004

- Rehearsal harness that exercises the runbook end-to-end against an isolated,
  clearly-named throwaway database (not `test_database`).
- Deployment-specific command appendix in `CREDENTIAL_ROTATION.md`, written once
  the production facts above are confirmed.
- Non-secret evidence-log template.

### Production impact to date

**None.** No production database has been read, backed up, or modified. No
legacy-account metadata has been read. A local database read was attempted
during preparation and was correctly blocked by the sandbox policy before the
approval gate.

---

## SEC-005 — BLOCKED BY SEC-004: OPERATOR-LED DESTRUCTIVE ACTIVITY

**Permanent classification.** SEC-005 rewrites Git history to remove the
already-rotated historical credential values. Its stated precondition is that
SEC-004 has succeeded — old passwords confirmed invalid, old sessions revoked.
Since SEC-004 is operator-led and not executed, SEC-005 cannot begin.

Rewriting history *before* the credentials are rotated would be actively harmful:
it would destroy the audit trail of which values need rotating while those values
remain live.

- **Preparation available:** the procedure is documented in
  `docs/implementation/SECRET_SCANNING.md`; `git-filter-repo` (>= 2.47) is
  installed in this container.
- **Requires when unblocked:** contributor notification, verified mirror backup,
  fork/clone inventory, maintenance window, branch-protection change and
  restoration, GitHub Support follow-up, and the explicit
  `APPROVE SEC-005 HISTORY REWRITE` gate.
- **SEC-005 remains an open P0 release blocker.**

---

## TEN-01 — Tenant ownership and mass-assignment protection

- **Status:** **Merged into `develop`.**
- **Branch:** `feature/ten-01-tenant-ownership` (deleted after merge).
- **PR:** #4. **Merge commit:** `d9ffc09`. **Commit:** `578f6fa`.
- **CI:** gitleaks pass. No review findings.
- **Implementation doc:** `docs/implementation/TENANT_OWNERSHIP.md`.
- **Production impact:** None. No production data accessed.

**Defect found and fixed (P0, previously unreported):** six generic update
endpoints filtered request bodies with a hand-written denylist that omitted
`org_id`, while `TenantCollection` scoped only the update *filter* and not the
update *document*. An authenticated user could move their own record into another
organisation with `PUT /api/<resource>/{id}` and `{"org_id": "<victim-org>"}`.
`insert_one` additionally used `setdefault("org_id", ...)`, so a client-supplied
owner would win on any raw-dict create path.

**Fix:** a canonical policy (`backend/tenant_policy.py`) replacing the scattered
denylists, protected-field rejection at the request edge (`TenantSafeModel` plus
route-level checks), and a fail-closed database layer that forces ownership on
insert and refuses any update writing an ownership field.

**Tests/checks:** 172 passed, 3 skipped (106 new). Ruff clean on touched files.
Gitleaks clean. Frontend builds. Server imports; `GET /api/` returns 200.

**Remaining limitations (explicitly NOT complete):** `status` still writable via
generic updates (WF-01); files uncovered (FILE-01); role-tier not action-level
authorisation (AUTHZ-01); full cross-tenant HTTP matrix (TEN-TEST); branch scoping
and optimistic locking prepared but not issued/enforced.

---

## FILE-01 — Tenant-scoped file security

- **Status:** **Merged into `develop`.**
- **Branch:** `feature/file-01-tenant-file-security` (deleted after merge).
- **PR:** #5. **Merge commit:** `ea489f9`. **CI:** gitleaks pass.
- **Implementation doc:** `docs/implementation/FILE_SECURITY.md`.
- **Production impact:** None. No production data accessed.

**Defect found and fixed (P0, previously unreported):** `files` was absent from
`TENANT_COLLECTIONS`, so file records carried no `org_id` and
`GET /api/files/{file_id}` matched on id alone. **Any authenticated user of any
organisation could download any other organisation's file** (RC books, insurance
documents, Aadhaar scans, accident photos) given only a file id — and ids are
returned in ordinary API responses. Also fixed: Content-Disposition header
injection and stored XSS via unsanitised filenames + client-declared content type
+ `inline` disposition; traversal-shaped storage paths from
`filename.split(".")[-1]`; no signature validation; no type restriction;
post-read size check; no integrity hash.

**Fix:** `files` is now tenant-scoped; `backend/file_policy.py` holds the type
allowlist, magic-byte detection, filename sanitisation, server-generated
org-namespaced storage names, safe disposition and SHA-256 hashing; downloads
force `attachment` for non-images with `nosniff` + CSP + `no-store`; size is
enforced while streaming.

**Migration note:** files are deliberately **excluded** from the blanket
`DEFAULT_ORG_ID` backfill — that would have handed every organisation's existing
files to the default org. `_migrate_file_org_ids()` derives the real owner from
each file's uploader; unresolvable files are quarantined under an org no session
holds (fail closed) and logged for operator follow-up. Idempotent, but it is a
data change and has **not** been run against production.

**Tests/checks:** 248 passed, 3 skipped (76 new). Ruff no new findings. Gitleaks
clean. Frontend builds. `GET /api/` 200.

**Remaining limitations (explicitly NOT complete):** no malware scanning (no
infrastructure — explicit SEC-CLOSEOUT exception); no short-lived signed URLs
(single app-wide storage key; permission-checked streaming used instead); no
linked-record permission model, so any member of the owning org can read its
files (AUTHZ-01); no branch scope; orphaned storage objects not reaped.

---

## AUTH-01 — Secure authentication and session lifecycle

- **Status:** **Merged into `develop`.**
- **Branch:** `feature/auth-01-secure-sessions` (deleted after merge).
- **PR:** #6. **Merge commit:** `ffd465c`. **CI:** gitleaks pass.
- **Implementation doc:** `docs/implementation/AUTHENTICATION.md`.
- **Production impact:** None. No production data accessed.

**Defects found and fixed (P0):** session tokens were stored **in plaintext**, so
any database dump, backup or injection yielded live replayable sessions; the token
was returned in the login body and kept in `localStorage`, making one XSS a
persistent account takeover; expiry slid forward on every use with **no absolute
cap**, so a stolen token lived indefinitely; tokens were never rotated (session
fixation, stale privilege); `reset_password` flipped the DB flag without evicting
the in-memory cache, leaving reset accounts reachable; no login throttling; and
`allow_credentials=True` with `allow_origins=["*"]`.

**Fix:** sessions identified by SHA-256 hash (never the token); HttpOnly cookie +
double-submit CSRF; independent idle (12h) and absolute (7d) clocks, the latter
never extended by sliding refresh; rotation on login and password change; one
revocation path that also evicts the cache; per-username **and** per-IP login
throttling with a constant-time, non-enumerating error; TTL indexes; CORS
credentials only with an explicit allowlist; frontend moved off `localStorage`
tokens with back/forward-cache and focus revalidation.

**Migration note:** pre-hashing sessions are **revoked, not rehashed** — hashing
an already-exposed value would keep it working. Existing users sign in once;
that is the intended cost. Bearer tokens remain accepted so newly-issued tokens
keep working during the transition.

**Tests/checks:** 304 passed, 3 skipped (56 new). Ruff clean on touched files.
Gitleaks clean. Frontend builds. **Live smoke test** confirmed cookie auth, CSRF
blocking forged writes (403) while allowing legitimate ones, and immediate
revoke-all (401) — and caught two real bugs unit tests missed (naive/aware
datetime comparison 500-ing every cookie session; an invalid Mongo projection).

**Remaining limitations (explicitly NOT complete):** no self-service password-reset
flow (no mail transport configured — open SEC-CLOSEOUT item); organisation
suspension does not exist as a concept, so its revocation hook is unused; bearer
fallback and the login `token` field remain for migration; no frontend test
harness; idle/absolute TTLs not per-deployment configurable.

---

## TEN-TEST — Comprehensive cross-tenant security matrix

- **Status:** Repository work complete; PR open against `develop`.
- **Branch:** `feature/ten-test-isolation-matrix`.
- **Implementation doc:** `docs/implementation/TENANT_TEST_MATRIX.md`.
- **Production impact:** None. No production data accessed.

**Why it ran before AUTHZ-01:** TEN-01, FILE-01 and AUTH-01 were all proven at the
*mechanism* level (policy functions, `TenantCollection` with a fake, source-wiring
guards). None had been exercised against real cross-tenant traffic. Building
AUTHZ-01 and WF-01 on top of an unproven foundation is how a security programme
ends up looking complete without being it.

**What it is:** 188 tests driving real HTTP through `httpx.ASGITransport` against
the real app, with two real organisations in a dedicated disposable database,
authenticating by cookie + CSRF exactly as the frontend does. A `RESOURCE_REGISTRY`
drives every case, and a guard test fails the build when a new tenant-scoped
collection is added without isolation coverage.

**Defects it found on its first run — both real, both fixed here:**

1. **`auth._resolve_session` depended on ambient tenant context.** It resolved the
   user through the tenant-scoped `db.users`, so the lookup was filtered by
   whatever `current_org_id` happened to hold. Session resolution is inherently
   cross-tenant — the caller's org is only known *after* the user is resolved. It
   worked under uvicorn only because each request gets a fresh context defaulting
   to `None`; that is luck, not design. Now resolved through `raw_db`.
2. **`delete_user` did not evict the session cache.** It flipped `revoked`
   directly instead of using `revoke_user_sessions()`, so a **deleted user's
   session stayed usable for up to the 60s cache TTL** — the same defect AUTH-01
   fixed in `reset_password`, in a path that had been missed.

It also caught a vacuously-passing test of its own (`/api/calendar` returns
`{"events": …}`, not `{"items": …}`, so an isolation assertion was checking an
empty list); the list helper now asserts its key exists rather than defaulting.

**Mutation-tested:** removing `"vehicles"` from `TENANT_COLLECTIONS` produces 4
failures including *"A deleted B's record"*, proving the suite detects a real leak
rather than merely passing.

**Tests/checks:** 492 passed, 3 skipped (188 new). Ruff clean. Gitleaks clean.
Live smoke re-verified after the `auth.py` fixes.

**Remaining limitations:** aggregate assertions are substring-based (catch
disclosure, not a subtler count-level leak); no background-job/notification
coverage (neither exists in FleetFlow — not applicable rather than skipped); no
signed-URL coverage (FILE-01 streams instead); no timing-channel analysis;
pairwise (two-org) isolation only.

---

## AUTHZ-01 — Action-level permission engine

- **Status:** **Merged into `develop`.**
- **Branch:** `feature/authz-01-permission-engine` (deleted after merge).
- **PR:** #8. **Merge commit:** `e47db5a`. **CI:** gitleaks pass.
- **Implementation doc:** `docs/implementation/AUTHORIZATION.md`.
- **Production impact:** None. No production data accessed.

**What it replaces:** scattered `require_role(...)` lists and hard-coded
`if user["role"] == "viewer"` checks, with subtly different allowed-role sets for
the same conceptual action across modules and nothing central to compare them.

**Engine:** `backend/permissions.py` — a canonical catalogue of `resource:action`
permissions, an explicit role→permission map keyed on the six effective tiers,
and `auth.require_permission(...)` as the single primitive every mutating
endpoint depends on. Platform permissions are defined separately and held by no
current role (no platform console exists yet).

**Key properties:** built to reproduce the pre-AUTHZ-01 guards exactly (behaviour
preserved — all 492 prior tests still green), with two deliberate tightenings
(viewer can no longer upload; trip-close/repair-advance no longer open to
viewers — both were `require_user`). `roles:assign` is separated from
`users:manage`; role changes and user creates are audited to `security_audit`
(ids/action only, no secrets) and trigger immediate session revocation.

**Enforcement guard:** a test walks the AST of every route module and fails the
build if any mutating endpoint lacks `require_permission` (small explicit exempt
set for unauthenticated/self-service flows and fastag_sync → FASTAG-01).

**Defects found:** two real-HTTP test modules each owned their own event loop,
which collided (Motor binds to the first loop) when run together — 186 errors.
Fixed by a single shared loop owned by conftest.

**Tests/checks:** 544 passed, 3 skipped (34 catalogue/wiring unit tests + 18
real-HTTP per-role enforcement tests). Mutation-tested (removing make_crud's
create permission let a driver create a service and tripped the wiring guards).
Ruff clean. Gitleaks clean. Live smoke: admin allowed, viewer denied, reads OK.

**Remaining limitations:** branch-scoped permissions are infrastructure-only (no
branch_id yet); monetary/approval limits have a tested predicate but no endpoint
enforces one (no product rule yet); record-state conditions belong to WF-01;
fastag_sync still require_user (FASTAG-01).

---

## FASTAG-01 — Demo-only FASTag simulation protection

- **Status:** Repository work complete; PR open against `develop`.
- **Branch:** `feature/fastag-01-demo-simulation`.
- **Implementation doc:** `docs/implementation/FASTAG_SIMULATION.md`.
- **Production impact:** None. No production data accessed.

**Defect (P0):** `POST /fastag/sync/{vehicle_id}` was `require_user`, so any user
in **any** organisation could fabricate 4–8 random toll transactions plus a
recharge for a real vehicle and **overwrite its `fastag_balance` with a random
number**. Non-idempotent — every click added more fake activity.

**Fix (`fastag_simulation.py`):** fail closed off the demo org (requires both
`is_demo` and `DEMO_ORG_ID`; a non-demo caller gets 403 before any write), plus
the `fastag:simulate` permission (defence in depth). Idempotent via a batch key
(replay returns the original result, writes nothing new). Balance is **computed**
from the vehicle's transactions, never random. Bounded amounts/dates/size.
Simulated rows carry `source="demo_simulation"`, distinct from manual imports and
the old `auto_sync`. Each run is audited. Manual import (`POST /fastag`) and a
(non-existent, fail-closed) live-provider path are explicitly separated.

**Tests/checks:** 566 passed, 3 skipped (21 new + 1 matrix). Mutation-tested
(disabling the demo guard fails both unit and real-HTTP layers). Ruff clean.
Gitleaks clean. Live smoke: demo sync 200 with `replayed:true` on retry; real-org
sync 403.

**Remaining limitations:** simulated balance can go negative (deterministic, demo
realism only); `fastag:simulate` is held by all acting roles with the demo-org
check doing the real restriction; live-provider integration deliberately absent
and must not reuse the simulation path when added.

---

## Environment / tooling notes

- GitHub CLI is authenticated as `pankaj8121993-web` with scopes
  `gist, read:org, repo, workflow`. Configuration lives under
  `/root/.config/gh`; CLI state under `/root/.local/state/gh`. No
  authentication artefacts exist inside `/app`.
- `HOME` is unset in non-login shells, which prevents `gh` from resolving its
  config directory. `/root/.bashrc` now exports `HOME`, `PATH`
  (`/root/.local/bin`) and `GH_CONFIG_DIR` so future shells work.
- `git-filter-repo` is installed (required for SEC-005).

---

## Next target

**WF-01 — Protected workflow transitions**, once FASTAG-01 is merged.

TEN-TEST was deliberately run before AUTHZ-01: it validates the three merged
stages against real cross-tenant traffic, so AUTHZ-01 and WF-01 build on a
proven foundation rather than an assumed one. It found two real defects on its
first run.

SEC-004 and SEC-005 stay open as operator-led P0 release blockers and do not gate
the remaining repository-side workstreams (FILE-01, AUTH-01, AUTHZ-01, FASTAG-01,
WF-01, TEN-TEST). They must both be resolved before SEC-CLOSEOUT can declare the
critical security programme complete.
