# FleetFlow — Cross-Tenant Security Matrix (TEN-TEST)

**Status:** Implemented on `feature/ten-test-isolation-matrix`.
**Scope:** Repository-side only. No production data was accessed.

---

## 1. Why this exists

TEN-01, FILE-01 and AUTH-01 were each proven at the **mechanism** level: policy
functions, `TenantCollection` driven with a fake, request models, source-wiring
guards. That is necessary but not sufficient. It proves the machinery works — not
that every route is *wired into* it.

A route that forgot to use the tenant-scoped `db`, or that listed through an
aggregate view nobody thought about, would pass every one of those tests and
still leak. TEN-TEST closes that gap by driving **real HTTP against the real app
with two real organisations in a real database**.

It found two genuine defects on its first run. See §4.

---

## 2. How it works

`backend/tests/test_tenant_isolation_matrix.py`.

| Decision | Reason |
| --- | --- |
| `httpx.ASGITransport` against the real `server.app` | No mocks. A misrouted or unscoped query fails here. |
| Dedicated disposable database (`conftest.TEST_DB_NAME`) | Tests never touch the running app's database. Dropped at **setup** as well as teardown, so a run that dies mid-fixture cannot poison the next one with "username already taken". |
| No lifespan | ASGITransport skips startup, so no `init_storage()` network call and no migrations. |
| One module-scoped event loop | Motor binds its client to the loop that first uses it. The `asyncio.run()`-per-test convention used elsewhere only drives fakes; for real I/O a single loop is the equivalent. |
| Cookie auth + CSRF header | `OrgClient` behaves exactly like the real frontend (AUTH-01), so the tests exercise the real auth path rather than a bypass. |
| **404, never 403** | A cross-tenant id must be indistinguishable from one that never existed. 403 confirms the record is real — itself a disclosure. |
| Paired "cannot see B" **and** "can see own" assertions | A broken list returning `[]` would make every negative assertion pass vacuously. This is not hypothetical — it caught exactly that (§4.3). |

### 2.1 The registry

`RESOURCE_REGISTRY` drives every parametrised case. Each `Resource` declares its
create payload, and — where the resource does not follow the common shape — its
`list_path`, `list_params`, `list_key` and `probe` field.

`test_every_tenant_collection_is_registered` fails when a collection is added to
`database.TENANT_COLLECTIONS` without isolation coverage. **New modules must
register here or the build breaks.** `REGISTRY_EXEMPTIONS` allows an opt-out, but
only with a stated reason, and `test_exemptions_are_all_real_tenant_collections`
stops an exemption lingering after a rename.

Currently registered: 19 resources. Exempt (with dedicated tests instead):
`files`, `users`.

---

## 3. Coverage

**188 tests.** Per registered resource: list (must not show B's, must show own),
update refused, update has no side effect, delete does not delete B's record,
create with injected `org_id` rejected, update cannot transfer own record to
another org, and cross-tenant id does not disclose existence (a real id and a
random id must return byte-identical responses).

Aggregate and egress surfaces: search, dashboard, reports, **report export**,
expenses overview, fleet status, calendar, compliance, alerts, and all seven
drilldowns.

Organisation/user administration: org profile scoped to own org; user list;
cannot update, escalate, delete or reset another org's user; user create cannot
target another org.

Files (FILE-01): upload works for own org; **cannot download another org's file**;
cannot read its metadata; own file served with `nosniff` + `no-store`;
cross-tenant file id does not disclose existence; disallowed type rejected;
content must match extension.

Sessions (AUTH-01): session list exposes no hashes; cannot revoke another org's
session; unauthenticated request rejected; state change without CSRF refused.

---

## 4. What it found

### 4.1 `_resolve_session` depended on ambient tenant context (real, fixed)

`auth._resolve_session` looked the user up through the **tenant-scoped** `db.users`,
so the query was filtered by whatever `current_org_id` happened to hold. Session
resolution is inherently cross-tenant — which organisation the caller belongs to
is only known *after* the user is resolved, and the contextvar is not set for that
request yet.

Under uvicorn each request gets a fresh context copy where the value defaults to
`None`, so `_scope` added nothing and it worked. That is luck, not design: it only
appeared correct because of a default. In the test harness, where requests share a
context, a stale org id from a previous request made every subsequent
authentication fail with "Session expired or invalid".

Fixed by resolving sessions through `raw_db`, with a comment explaining why.

### 4.2 `delete_user` did not evict the session cache (real, fixed)

It flipped `revoked` in the database directly instead of calling
`revoke_user_sessions()`, so a **deleted user's session stayed usable for up to
the 60-second cache TTL** — the same defect AUTH-01 fixed in `reset_password`, in
a path that had been missed. Now routed through the shared revocation path.

### 4.3 A vacuously-passing isolation test (test defect, fixed)

`/api/calendar` returns `{"events": [...]}`, not `{"items": [...]}`. The list
helper silently produced `[]`, which made "A cannot see B's calendar event" pass
**while asserting nothing**. Caught by the paired "can see own records" test.

The helper now *asserts* the expected key exists rather than defaulting to `[]`,
so this class of false pass fails loudly instead.

---

## 5. Verification

* **492 passed, 3 skipped** (full backend suite; 304 pre-existing still green).
* **188** TEN-TEST additions.
* Ruff clean on touched files. Gitleaks clean.
* Live smoke re-run after the `auth.py` fixes: demo login, `/auth/me` and
  `/vehicles` all 200 against the dev container.

### 5.1 Mutation test

A green isolation suite proves nothing unless it fails on a real leak. Removing
`"vehicles"` from `TENANT_COLLECTIONS` — simulating exactly the FILE-01 defect
class — produced **4 failures**, including *"A deleted B's record"* and
*list returns another org's records*. The change was then reverted and the suite
re-verified green.

---

## 6. Limitations

* **Read-only aggregate assertions are substring-based.** They assert B's ids do
  not appear in A's response body. That catches disclosure, not a subtler
  aggregate leak (e.g. a count that includes B's rows without naming them).
  Strengthening this needs per-report fixtures with known values.
* **No background-job or notification coverage** — FleetFlow has no background
  job runner or notification system, so there is nothing to test. The brief lists
  them; they are not applicable rather than skipped.
* **No signed-URL coverage** — FILE-01 uses permission-checked streaming, not
  signed URLs (single app-wide storage key). Nothing to test until that changes.
* **Audit-data surface** — `security_audit` is written by the SEC-002 rotation
  tool and has no API surface, so there is no endpoint to isolate.
* **Timing analysis is out of scope.** The suite asserts responses are identical
  for real vs random cross-tenant ids, which covers content-based disclosure but
  not a timing side channel.
* **Two organisations, not N.** Isolation is pairwise; a bug needing three tenants
  to manifest would not be caught.
