# FleetFlow — Tenant Ownership and Mass-Assignment Protection (TEN-01)

**Status:** Implemented on `feature/ten-01-tenant-ownership`.
**Scope:** Repository-side only. No production data was accessed.

---

## 1. Threat addressed

FleetFlow scopes tenant data through `database.TenantDB` / `TenantCollection`,
which injects the session's `org_id` into queries. Two gaps let a client defeat
that scoping through ordinary request bodies.

### 1.1 Ownership transfer through a generic update (the primary defect)

Six generic update endpoints filtered their request body with a hand-written
denylist:

```python
payload = {k: v for k, v in payload.items()
           if k not in ("id", "_id", "created_at", "created_by", "is_test_data")}
...
await db.vehicles.update_one({"id": vid}, {"$set": payload})
```

Every copy of that list omitted **`org_id`**. `TenantCollection._scope()` adds
`org_id` to the update *filter*, so only the caller's own records match — but it
never inspected the *update document*. An authenticated user could therefore send:

```http
PUT /api/vehicles/{id}
{"org_id": "<another-organisation-id>"}
```

and move their own record into another organisation. The record then vanished
from their tenant and appeared in the victim's, with no audit trail and no error.
The same shape existed on drivers, vendors, calendar events, compliance contacts
and — via `helpers.make_crud` — twelve further collections.

### 1.2 Ownership injection on insert

`TenantCollection.insert_one` used:

```python
doc.setdefault("org_id", org)
```

`setdefault` keeps a value the caller already supplied. Any endpoint that passed
a client-controlled dictionary into an insert would file the new record under a
**client-chosen** organisation. The typed create models did not carry `org_id`
(Pydantic's default `extra="ignore"` dropped it), so this was not reachable from
every endpoint today — but the primitive was unsafe and one raw-dict create
endpoint away from being exploitable.

---

## 2. Architecture implemented

Three layers, each independently sufficient for the common case, so a mistake in
one does not open the hole.

| Layer | File | Responsibility |
| --- | --- | --- |
| Policy | `backend/tenant_policy.py` | One canonical definition of protected fields; the rejection helper; update-document inspection. |
| Request validation | `backend/models.py` (`TenantSafeModel`), route bodies | Reject protected fields at the edge with a clear 400. |
| Database (fail-closed) | `backend/database.py` (`TenantCollection`) | Force ownership on insert; refuse any update that writes an ownership field. |

### 2.1 Canonical protected-field policy

`tenant_policy.PROTECTED_FIELDS` replaces the six scattered denylists. It is the
union of named groups, so the intent of each entry stays legible:

| Group | Fields |
| --- | --- |
| `TENANT_OWNERSHIP_FIELDS` | `org_id`, `organization_id`, `tenant_id` |
| `IDENTITY_FIELDS` | `id`, `_id` |
| `AUDIT_FIELDS` | `created_at/by`, `updated_at/by`, `deleted_at/by`, `archived_at/by` |
| `SECURITY_FIELDS` | `role`, `roles`, `permissions`, `is_admin`, `is_super_admin`, `is_platform_admin`, `password`, `password_hash`, `must_change_password` |
| `ISOLATION_MARKER_FIELDS` | `is_demo`, `is_test_data` |
| `BRANCH_SCOPE_FIELDS` | `branch_id` |
| `VERSION_FIELDS` | `_version` |
| `WORKFLOW_FIELDS` | `approval_status/by/at`, `rejection_reason`, `rejected_by/at`, `payment_status`, `paid_by/at`, `ticket_number` |
| `DERIVED_FIELDS` | `total`, `totals`, `balance`, `computed_total` |

`organization_id`, `tenant_id`, `branch_id` and `_version` are not in today's
schema. They are protected pre-emptively so a future rename or feature cannot
silently open a hole.

### 2.2 Server-derived ownership rule

> **`org_id` is never read from a request body. It is taken from
> `database.current_org_id`, which `auth.require_user` sets from the
> authenticated session on every request.**

`TenantCollection._force_ownership()` now *assigns* rather than `setdefault`s,
and raises `TenantViolation` if a caller supplied a **different** `org_id` —
nothing in the application legitimately inserts a foreign owner, so a mismatch
means the caller is confused or hostile and must not proceed.

`TenantCollection._guard_update()` inspects the update document for any operator
(`$set`, `$setOnInsert`, `$unset`, `$rename`, `$inc`, …) that writes an ownership
field, matching dotted paths at their root, and refuses. Ownership writes are
rejected **even when the value equals the caller's own org**, because ownership
is server-derived and there is no legitimate reason to write it.

### 2.3 Reject, never silently drop

Supplying a protected field returns **HTTP 400** naming the rejected *fields* and
never echoing their values. The previous behaviour — silently stripping — told
the client its write had succeeded as sent, which is how a mass-assignment bug
stays invisible.

### 2.4 Why not `extra="forbid"`

`TenantSafeModel` rejects *protected* fields but still ignores unknown
non-protected ones. A blanket `extra="forbid"` was considered and rejected: it
adds no tenant safety, and the frontend legitimately sends fields the models do
not declare (e.g. `Vehicles.jsx` spreads `include_disposed` into create bodies),
so it would have turned harmless drift into 422s across the app.

---

## 3. Explicit exceptions

Protected fields remain editable through their dedicated, permission-checked
paths. Exceptions are declared per model as a `ClassVar`, never inferred:

| Model / endpoint | Exempt fields | Why it is safe |
| --- | --- | --- |
| `UserCreate` (`POST /api/users`) | `role`, `password` | Admin-only user administration. `auth.create_user` validates the role against `ROLES`; the insert goes through `TenantCollection`, which pins the new user to the **caller's** org. |
| `UserUpdate` (`PUT /api/users/{id}`) | `role` | Admin-only. `org_id` is deliberately absent, so users cannot be moved between organisations. Role changes already revoke the target's sessions. |
| `LoginRequest` | `password` | Login is the one place a caller is meant to send a password. |
| `routes_ops.advance_repair` | ticket status/stage fields | Already a dedicated transition endpoint with a state graph and role checks; it builds its update explicitly and never spreads the body. |
| `routes_orgs.update_org` / `update_branch` | — | Allowlist-based; now also rejects protected fields rather than dropping them. |

---

## 4. Raw-database access policy

`database.raw_db` bypasses all tenant scoping. It is legitimate only where the
operation is inherently cross-tenant or pre-session, and every current use is:

| Use | Location | Justification |
| --- | --- | --- |
| Startup index creation and legacy `org_id` backfill | `server.py` | Runs at startup with no session; migration must span tenants. |
| Global username/email uniqueness checks | `routes_orgs.register_org` | Must detect collisions across all organisations. |
| Organisation + first admin + default branch creation | `routes_orgs.register_org` | Runs **before** a session exists, so there is no `current_org_id` to derive from; `org_id` is generated server-side in the same function. |
| Organisation profile read/update | `routes_orgs`, `auth._org_name` | `organizations` is not a tenant-scoped collection (it *is* the tenant); both are filtered by `user["org_id"]` from the session. |

**Policy:** new `raw_db` use requires a comment justifying why tenant scoping
cannot apply, and must derive any organisation filter from session context, never
from a request body. Prefer `db` (the `TenantDB` wrapper) in all other cases.

---

## 5. Compatibility impact

* **Intentionally breaking:** a request body containing a protected field now
  returns 400 instead of being silently accepted-and-stripped. No current
  frontend call site sends one — verified by inspecting every `api.post`/`api.put`
  call: `CrudModule` builds payloads from declared fields only, and `OrgSettings`
  seeds its form from an explicit field list.
* **Not breaking:** unknown non-protected fields are still ignored.
* **No migration required.** No schema or stored-document change; existing records
  are untouched. Records that already lack `org_id` are handled by the
  pre-existing startup backfill in `server.py`.
* **Demo unchanged.** Demo isolation relies on `is_demo` / `org_id`, both now
  harder to forge. `demo_seed` runs without a session, so the no-context path
  (no stamping) preserves its behaviour exactly.

---

## 6. Tests and verification

`backend/tests/test_tenant_ownership.py` — 106 tests, following the project's
`asyncio.run()` convention (no new dependency). Coverage:

* Policy membership: every ownership/audit/security/isolation/workflow/version
  field is protected; ordinary fields (`notes`, `amount`, `status`, …) are not.
* Rejection: 400 naming the field; never echoes the submitted value; does not
  mutate the payload.
* Update inspection: `$set`, `$setOnInsert`, `$unset`, `$rename`, `$inc`, dotted
  paths and replacement documents all detected; clean updates pass.
* Insert: ownership stamped from session; matching org allowed; **foreign org
  raises `TenantViolation` and writes nothing**; `insert_many` covers every doc.
* Update: cross-tenant transfer refused (single and bulk); refused even for the
  caller's own org; ordinary updates still work and stay filter-scoped.
* Non-tenant collections (`user_sessions`) are not stamped; no-session contexts
  (management commands, `demo_seed`) are not stamped.
* Models: each protected field rejected on create; role escalation rejected;
  valid creates still work; `allow_protected` is not a request field.
* Exceptions: user admin may set role/password; may not move a user between orgs;
  login may send a password but cannot inject ownership.
* Wiring: `make_crud` enforces the policy, and the old incomplete denylist string
  cannot reappear in any route module.

**Results:** 172 passed, 3 skipped (full backend suite; 66 pre-existing tests
still green). Ruff clean on all touched files. Gitleaks: no leaks. Frontend
builds. Server imports and `GET /api/` returns 200 in the dev container.

---

## 7. Remaining limitations (owned by later workstreams)

TEN-01 does **not** close these. They are named here so no one mistakes overlap
for completion:

* **WF-01** — `status` is still writable through generic update endpoints. Several
  modules use it as an ordinary field; removing it requires dedicated transition
  endpoints and a state graph first. Approval/payment fields are blocked from
  generic bodies, but their dedicated action endpoints do not exist yet.
* **FILE-01** — file records (`/api/upload`, storage objects) are not covered.
* **AUTHZ-01** — enforcement is still role-tier based (`require_role`), not
  action-level permissions.
* **TEN-TEST** — this suite proves the *mechanism*. The full cross-tenant HTTP
  matrix (every resource × every method, with two live organisations) is TEN-TEST.
* **Branch scoping** — no collection carries `branch_id` yet. The field is
  protected in advance; deriving branch scope from session context is future work.
* **Optimistic locking** — `_version` is protected but not yet issued or checked.
  Introducing it needs a read-modify-write change per module, which would exceed
  TEN-01's scope; no current flow was found where a lost update is a security
  boundary rather than a UX concern.
