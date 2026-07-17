# FleetFlow — Secure Authentication and Session Lifecycle (AUTH-01)

**Status:** Implemented on `feature/auth-01-secure-sessions`.
**Scope:** Repository-side only. No production data was accessed.

---

## 1. Threats addressed

| # | Defect | Consequence |
| --- | --- | --- |
| 1 | **Session tokens stored in plaintext** (`user_sessions.token`) | The sessions collection was a credential store. Any dump, backup, injection or operator read yielded **live, replayable sessions**. |
| 2 | **Token returned in the login body and held in `localStorage`** | Readable by any script on the origin, so a single XSS became persistent full account takeover. |
| 3 | **Sliding expiry with no absolute cap** | A stolen token stayed valid indefinitely as long as it was used. |
| 4 | **No rotation** | A token captured before login, or before a role change, kept working afterwards (session fixation / stale privilege). |
| 5 | **Reset only flipped the DB flag** | `reset_password` did not evict the in-memory cache, so a reset account stayed reachable for the cache TTL. |
| 6 | **No CSRF protection** | Not exploitable while auth was header-only, but a blocker for cookie auth. |
| 7 | **No login throttling** | Unbounded online password guessing. |
| 8 | **`allow_credentials=True` with `allow_origins=["*"]`** | Rejected by browsers for credentialed requests, and a misconfiguration away from letting any origin read authenticated responses. |

---

## 2. Architecture

`backend/session_security.py` holds the primitives (no DB/route imports, directly
unit-testable). `backend/auth.py` wires them in.

### 2.1 Store a hash, never the token

The database holds `token_hash` = SHA-256(token). A dump cannot be replayed.

**Why SHA-256 and not bcrypt:** the token is 256 bits of CSPRNG output, not a
low-entropy human password. There is nothing to brute-force, and session lookup
happens on every request, so a deliberately slow hash would be a DoS vector with
no security gain.

The in-memory cache is keyed by hash too, so process memory holds no replayable
credential either.

### 2.2 Two independent clocks

| Clock | Value | Bounds |
| --- | --- | --- |
| Idle (`last_used_at` + `IDLE_TTL`) | 12h | An abandoned session |
| Absolute (`absolute_expires_at`) | 7d from creation | A **stolen** session |

Sliding refresh moves **only** the idle clock; `absolute_expires_at` is never
extended. Both are stored as real BSON dates (not ISO strings) so the TTL index
works and comparisons are datetime-native.

`is_expired()` fails closed: a session with a missing or malformed timestamp is
treated as expired. The cache re-checks expiry on every hit, so a cache entry can
never outlive either clock.

### 2.3 Cookies

| Cookie | HttpOnly | Purpose |
| --- | --- | --- |
| `fleet_session` | **Yes** | The session. Unreadable by script, so XSS cannot exfiltrate it. |
| `fleet_csrf` | No (deliberate) | Double-submit value. Not a credential on its own. |

`Secure` is forced in production. It is **not** forced in development on purpose:
the preview container is plain HTTP, and a Secure cookie there would never be
stored — locking everyone out. `SameSite=Lax` by default; a deployment serving
the API from a different site sets `FLEETFLOW_CROSS_SITE_COOKIES=true`, which
selects `SameSite=None` **and** forces `Secure` (browsers reject None without it).

### 2.4 CSRF (double-submit)

Enforced on cookie-authenticated, state-changing requests only. A cross-site page
can make the browser *send* the session cookie, but same-origin policy stops it
*reading* `fleet_csrf`, so it cannot echo the value into `X-CSRF-Token`. Bearer
auth needs no CSRF: a browser cannot attach an Authorization header cross-site
without script.

Empty values never validate — otherwise CSRF protection would be opt-out by
omitting the header.

### 2.5 Rotation and revocation

Rotated on **login** (kills any pre-login token — session fixation) and on
**password change** (caller is re-issued a session so they aren't logged out of
the tab they're typing in).

`revoke_user_sessions()` is the single path: it flips the DB flag **and** evicts
the cache. Called on password change, password reset, role change, deactivation,
and user-initiated revoke-all.

### 2.6 Login hardening

* **Throttling:** counted per username **and** per IP independently, so neither a
  targeted attack on one account nor a spray from one address runs unbounded.
  10 failures / 15 min. Records TTL out after an hour.
* **Non-enumerating:** identical message for unknown user and wrong password. A
  bcrypt verify runs **even when the user does not exist**, so response timing
  does not reveal which usernames are real. The throttle response deliberately
  does not say the account is locked.

### 2.7 Frontend

`localStorage` no longer holds any token — `fleet_token` is gone entirely.
`fleet_user` remains as a *display* cache (name, role, modules); it is not a
credential, confers no access, and `/auth/me` stays the source of truth.

Revalidation on **route change, tab focus, and `pageshow` with `persisted=true`**
— that last one is the back/forward-cache restore, where the browser replays a
snapshot taken *before* logout. Without it a logged-out user can press Back and
see the app. `/auth/me` and auth responses send `Cache-Control: no-store, private`.

### 2.8 CORS

`allow_credentials` is now enabled **only** when `CORS_ORIGINS` is an explicit
allowlist. Wildcard or unset logs a warning and disables credentialed
cross-origin requests. Same-origin deployments (like the preview) are unaffected.

---

## 3. Migration

**Pre-hashing sessions are revoked, not rehashed.** Hashing a stored plaintext
token would keep a value that has *already been exposed in the database* working
— exactly what this change exists to prevent. `_migrate_plaintext_sessions()`
revokes them and `$unset`s the plaintext field. Idempotent.

**Cost:** existing users sign in once. That is the intended, safe price; carrying
known-exposed tokens forward would defeat the workstream.

**Bearer tokens still work.** `_extract_token` prefers the cookie and falls back
to `Authorization: Bearer`, so any client holding a *newly issued* token keeps
working. Login still returns `token` in the body for the same reason. Once no
client needs it, that field and the header fallback should be removed — tracked
as a follow-up, not done here.

**Indexes:** `token_hash`, `user_id`, a TTL on `absolute_expires_at`
(`expireAfterSeconds=0`, so Mongo reaps expired sessions itself), and TTL +
lookup indexes on `login_attempts`. The old raw `token` index is gone.

---

## 4. Verification

`backend/tests/test_auth_sessions.py` — **56 tests**: hashing (stability, hex,
token not recoverable); both expiry clocks incl. *absolute cap expires an actively
used session*; malformed sessions fail closed; CSRF (match, mismatch, and every
empty/None combination); cookie attributes across dev/prod/cross-site; throttle
config; and wiring guards asserting plaintext tokens cannot return, that login /
change-password / reset / role-change all revoke, that the cache is hash-keyed and
re-checks expiry, and that the migration revokes rather than rehashes.

**Full suite: 304 passed, 3 skipped.** Ruff clean on touched files. Frontend
builds. Gitleaks clean.

**Live smoke test against the dev container** (this is what caught two real bugs
the unit tests could not):

| Check | Result |
| --- | --- |
| `POST /api/demo/enter` | 200, sets HttpOnly `fleet_session` + readable `fleet_csrf`, `Cache-Control: no-store` |
| Cookie-only `GET /api/auth/me`, `/api/vehicles` | 200 |
| `GET /api/auth/sessions` | 200, no token/csrf hashes leaked, `current` flagged |
| **Cookie write with no CSRF header** | **403** |
| **Cookie write with wrong CSRF header** | **403** |
| Cookie write with correct CSRF header | 200 |
| `GET` without CSRF (safe method) | 200 |
| `revoke-all`, then reuse cookie | 200, then **401 immediately** (cache evicted) |

**Two bugs found and fixed by that smoke test:**

1. **Naive/aware datetime comparison.** Motor returns naive datetimes; everything
   created in-process is aware. `is_expired()` raised `TypeError`, 500-ing every
   cookie session. Fixed with `as_aware()` — Mongo always stores UTC, so
   attaching UTC is correct rather than a guess.
2. **Mixed inclusion/exclusion projection** in `/auth/sessions`, which Mongo
   rejects outright (500).

---

## 5. Remaining limitations

* **Password-reset lifecycle is admin-mediated.** `POST /users/{id}/reset-password`
  issues a temporary password to an admin. There is no self-service
  email-token reset flow (`reset_tokens` collection, TTL index, single-use token).
  FleetFlow has no mail transport configured, so building the token half without a
  delivery channel would be unfinished scaffolding. **Open item**, called out at
  SEC-CLOSEOUT.
* **Organisation suspension** does not exist as a concept, so "revoke on
  organisation suspension" has nothing to hook. `revoke_user_sessions()` is the
  ready-made hook when it lands.
* **Bearer fallback and the `token` login field** remain for migration and should
  be removed once no client depends on them.
* **Frontend tests.** The auth changes are covered by backend tests and the live
  smoke test above; the project has no frontend test harness, and standing one up
  is out of AUTH-01's scope.
* **Idle/absolute values** (12h / 7d) are not yet configurable per deployment.
