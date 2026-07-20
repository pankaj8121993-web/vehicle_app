# FleetFlow — Action-Level Permission Engine (AUTHZ-01)

**Status:** Implemented on `feature/authz-01-permission-engine`.
**Scope:** Repository-side only. No production data was accessed.

---

## 1. What was wrong

Authorisation was a scatter of role-tier checks:

* Every endpoint carried its own role list —
  `require_role("data_entry", "management", "admin", "test")` copied by hand from
  endpoint to endpoint.
* The generic CRUD helper hard-coded `if user["role"] == "viewer"` and a driver
  special-case in Python.
* The allowed roles for the *same conceptual action* differed between modules
  (`compliance:create` was management+, `budgets:create` included data_entry)
  with nothing central to compare them against.
* Two workflow endpoints — trip close and repair advance — were `require_user`,
  so **any authenticated user including a read-only viewer could drive them**.
* Upload was `require_user`, so a viewer could store files.

Adding an endpoint meant copying a role list and hoping it matched intent. There
was no single place that answered "what can this role do?"

## 2. The engine

`backend/permissions.py` — a fixed catalogue of **action** permissions
(`resource:action`), an explicit map from each enforcement role to the
permissions it holds, and pure query/condition helpers. No DB or FastAPI
imports, so it is unit-testable in isolation.

`auth.require_permission("vehicles:delete")` is the single primitive every
mutating endpoint now depends on. It resolves the session, blocks
must-change-password users, and checks the **effective** role against the
catalogue. An unknown permission string raises at wiring time, so a typo becomes
an immediate error rather than a silently-ungranted (always-403) endpoint.

### 2.1 Effective roles

Enforcement is keyed on the six tiers `auth.ROLE_EQUIV` collapses the eight named
roles onto (`admin, management, data_entry, driver, viewer, test`). A new named
role only needs a tier mapping, not a sweep of every endpoint.
`test_enforcement_roles_match_auth_tiers` fails the build if the two ever drift.

### 2.2 Catalogue

* **Resource actions** — `create/update/delete` for each of the 18 tenant CRUD
  resources.
* **Organisation actions** — `branches:*`, `org:update`, `users:manage`,
  `roles:assign`, `files:upload`, `trips:close`, `repairs:transition`,
  `fastag:simulate`, `testdata:purge`.
* **Platform actions** — `platform:manage_orgs`, `platform:impersonate`,
  `platform:manage_billing`. Defined for separation and held by **no current
  role**: FleetFlow has no platform-owner console yet (PLATFORM-01), and
  `org_admin` is the top of an *organisation*, not a platform superuser.
  `test_no_role_holds_a_platform_permission` enforces this.

### 2.3 Role → permission map

Built to **reproduce the pre-AUTHZ-01 guards exactly** (a refactor of *where* the
rules live, not a change to who-can-do-what), with each grant commenting the
guard it descends from. Two deliberate, documented tightenings:

| Tightening | Before | After |
| --- | --- | --- |
| `files:upload` | `require_user` — any authenticated user, incl. viewer | Acting roles only; **viewer is truly read-only** |
| `trips:close`, `repairs:transition` | `require_user` — incl. viewer | Acting roles only (WF-01 refines further) |

`roles:assign` is separated from `users:manage`: changing a user's role (or
creating one with a role) requires it explicitly, and each such change is
**audited** and triggers **immediate session revocation** (from AUTH-01).

### 2.4 Conditional checks

`PermissionContext` plus pure predicates — `can_act_on_record` (cross-tenant
defence in depth at the authorisation layer, on top of `TenantCollection`
scoping), `within_monetary_limit` (role→ceiling, fails closed on malformed
amounts). The infrastructure is in place; monetary ceilings are not yet wired to
a specific endpoint (no approval-limit requirement exists in the current
product) and are covered by unit tests so the mechanism is ready for WF-01.

## 3. Enforcement — every mutating endpoint

`test_every_mutating_endpoint_enforces_a_permission` walks the AST of every route
module and **fails if any POST/PUT/PATCH/DELETE handler lacks
`require_permission`**, with a small explicit `EXEMPT` set (unauthenticated flows:
login/logout/register/demo; self-service session endpoints guarded by
`require_user` + own-session ownership; and `fastag_sync`, which FASTAG-01 will
lock to the demo org). This is the guard that keeps the catalogue load-bearing as
the app grows.

## 4. Audit

`auth.record_security_event` appends to the shared `security_audit` collection
(the same one SEC-002 writes to) on user create, role change and
activation change. Records the action, actor id/role, org and target id only —
**never** a password, hash, token or the content of any changed field. Enforced
by `test_security_event_records_no_secrets`.

## 5. Verification

* **544 passed, 3 skipped** (full suite; 492 pre-AUTHZ still green — the
  behaviour-preservation proof).
* **34** catalogue/wiring unit tests + **18** real-HTTP per-role enforcement
  tests (via the demo roles), driving the actual app: viewer/driver denied where
  expected, data_entry can update but not delete, non-admins cannot list/create
  users or purge test data.
* **Mutation test:** replacing `make_crud`'s create permission with `require_user`
  made a driver able to create a service and tripped both wiring guards — proving
  the enforcement tests are load-bearing. Reverted, re-verified green.
* **Live smoke** against the dev container: demo org_admin creates a vehicle and
  lists users (200); demo viewer is refused both (403) but still reads (200).
* Ruff clean on touched files. Gitleaks clean.

## 6. Remaining limitations

* **Branch-scoped permissions** — the catalogue is org-scoped. No record carries
  `branch_id` yet (blocked on branch scoping generally, see TEN-01), so
  branch-level permission conditions are infrastructure-only.
* **Monetary/approval limits** — the predicate exists and is tested, but no
  endpoint enforces a ceiling because the product defines no approval-limit rule
  yet. WF-01 is the natural home if one is introduced.
* **Record-state conditions** — `can_act_on_record` covers ownership; state-based
  authorisation (e.g. "cannot edit a paid expense") is part of the workflow model
  and belongs to WF-01.
* **`fastag_sync`** remains `require_user`; FASTAG-01 locks it to the demo org.
* **`require_role`** is retained (unused by routes) for any external caller; it
  can be removed once confirmed dead.
