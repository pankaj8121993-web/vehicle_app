# FleetFlow — Legacy Credential Rotation Runbook (SEC-002)

This runbook covers rotating the **legacy default production accounts** (the five
`created_by: "system"` accounts formerly auto-seeded before SEC-001) and revoking
their sessions, using `backend/rotate_legacy_credentials.py`.

It never touches demo users, ordinary staff, onboarding/bootstrap admins, or any
non-legacy account, and it is designed so it cannot lock out the operating
administrator. **Do not run any `--apply` step until the backup is verified.**

---

## 0. What the command changes

| Collection | Change | Rollback source |
| --- | --- | --- |
| `users` | `password_hash`, `must_change_password` (rotate); `is_active=false` (deactivate) | backup of `users` |
| `user_sessions` | `revoked=true` for the targeted user only | backup of `user_sessions` |
| `security_audit` | **insert-only** non-secret audit records | not needed for rollback |

Legacy target filter is strict: `created_by == "system"` AND not a demo account.
Demo (`is_demo:true` / `created_by:"demo_seed"` / `org-fleetflow-demo` / `demo_*`
usernames) is always excluded and rejected even if a manifest lists it.

---

## 1. Minimum production access required (for the operator)

- Network connectivity to the production MongoDB (`MONGO_URL`, `DB_NAME`).
- DB permission to **read and update** `users`.
- DB permission to **read and update** `user_sessions`.
- DB permission to **insert** into `security_audit`.
- Permission and tooling to run and verify `mongodump` / `mongorestore`.
- Ability to **restart the backend** immediately after `--apply`.
- An approved maintenance window and a secure operator terminal (hidden input
  support for password entry; no shared screen / logging of the terminal).

---

## 2. Backup (mandatory before any `--apply`)

`mongodump` dumps a single collection per `-c`. Back up the two mutable
collections with **two separate commands** (this build has no `--nsInclude`):

```bash
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DEST="/secure/backups/sec002-$STAMP"     # restricted, encrypted-at-rest location

mongodump --uri "$MONGO_URL" --db "$DB_NAME" --collection users \
          --out "$DEST"
mongodump --uri "$MONGO_URL" --db "$DB_NAME" --collection user_sessions \
          --out "$DEST"
```

> Storing the URI on the command line can leak it via shell history/process list.
> Prefer exporting `MONGO_URL` in the environment and omitting `--uri`, or use a
> credentials file. Never commit or share the dump; it contains password hashes.

### Verify the backup

```bash
ls -l "$DEST/$DB_NAME/users.bson" "$DEST/$DB_NAME/user_sessions.bson"

# Optional integrity/count check against the live DB:
mongosh "$MONGO_URL" --quiet --eval \
  'db.getSiblingDB(process.env.DB_NAME).users.countDocuments({})'
```

Confirm the `.bson`/`.metadata.json` files exist and are non-empty and that the
document counts look right. **Do not proceed without a verified backup.**

---

## 3. Identify legacy accounts (no secrets, no writes)

```bash
cd /app/backend
python -m rotate_legacy_credentials list
```

This prints `user_id`, `username`, `role`, `is_active` and active-session counts
only. No passwords or hashes are ever shown. Record the `user_id`s.

---

## 4. Build the reviewed manifest (no passwords in it)

Create `manifest.json`. It must declare the operator, the recovery administrator,
and one action per targeted account. **Passwords never go in the manifest.**

```json
{
  "operator": "ops-person@your-org",
  "recovery_admin_username": "admin",
  "recovery_admin_has_known_password": false,
  "actions": [
    { "user_id": "<uuid-of-admin>",      "username": "admin",      "action": "rotate" },
    { "user_id": "<uuid-of-manager>",    "username": "manager",    "action": "rotate" },
    { "user_id": "<uuid-of-dataentry1>", "username": "dataentry1", "action": "rotate" },
    { "user_id": "<uuid-of-driver1>",    "username": "driver1",    "action": "rotate" },
    { "user_id": "<uuid-of-test>",       "username": "test",       "action": "deactivate" }
  ]
}
```

Field notes:
- `recovery_admin_username` — the administrator the operator will use for
  continued access. Must be an active, non-demo administrative account.
- If the recovery admin is set to `rotate`, a fresh known-good password is entered
  interactively, so `recovery_admin_has_known_password` may stay `false`.
- If the recovery admin is `skip` or is not listed at all, you must set
  `recovery_admin_has_known_password: true` to assert you already hold a working
  password for it; otherwise the command refuses.
- `action`: `rotate` | `deactivate` | `skip`.

**Recommended production classification** (operator confirms explicitly; the
command never decides from usernames alone):
- `test` (obsolete sandbox) → `deactivate`
- `admin`, `manager`, `dataentry1`, `driver1` (potentially legitimate) → `rotate`
- Demo accounts → always excluded (cannot be listed)
- Non-legacy staff → always excluded (cannot be listed)

---

## 5. Dry-run (default — makes no changes)

```bash
python -m rotate_legacy_credentials apply --manifest manifest.json
```

Review the planned per-account actions and totals. Dry-run performs **zero**
writes and creates **no** audit records. Resolve any manifest rejection
(unknown/duplicate/demo/non-legacy target, integrity mismatch, or admin-lockout
pre-flight failure) before continuing.

---

## 6. Apply (writes changes)

```bash
python -m rotate_legacy_credentials apply --manifest manifest.json --apply
```

- For every `rotate` account you are prompted for a new password (hidden, entered
  twice) that must satisfy the app policy (minimum 8 characters). Passwords are
  hashed with the application bcrypt implementation and never printed/logged.
- Rotated accounts get `must_change_password: true` so the owner must set their
  own password on next login.
- You must type `APPLY` at the final confirmation prompt.
- Sessions are revoked only for successfully changed accounts, only for that
  user. The report shows a session-revocation **count** (never tokens).

Distribute each new password to its legitimate owner out-of-band (never by email
in plaintext, never in a ticket). The `test` account is deactivated, not deleted.

---

## 7. Restart the backend (mandatory)

The server keeps an in-memory session cache (`auth._session_cache`, ~60s TTL)
that a DB-side revocation cannot clear. **Immediately restart the backend** so
revocation takes effect globally with no stale-token window:

```bash
# however this deployment restarts the API, e.g.:
sudo systemctl restart fleetflow-backend        # or your process manager / container
```

Do not treat the ~60s cache TTL as an acceptable production revocation delay.

---

## 8. Post-change verification

- Old/leaked passwords are rejected at `POST /api/auth/login` (401).
- A previously-issued session token for a rotated/deactivated user returns 401.
- The recovery administrator can still log in (and, if rotated, is prompted to
  change password).
- The deactivated `test` account cannot log in.
- **Demo unchanged:** `POST /api/demo/enter` still works; existing demo sessions
  remain valid; demo users are untouched.
- `security_audit` contains one record per applied action (no secrets).

---

## 9. Rollback / emergency recovery

Use only in an emergency (e.g. the recovery administrator is locked out).

```bash
# Restore the two collections from the verified backup:
mongorestore --uri "$MONGO_URL" --db "$DB_NAME" --collection users \
             --drop "$DEST/$DB_NAME/users.bson"
mongorestore --uri "$MONGO_URL" --db "$DB_NAME" --collection user_sessions \
             --drop "$DEST/$DB_NAME/user_sessions.bson"
```

Then **restart the backend** again (step 7) to flush the session cache.

> ⚠️ **Warning:** restoring `users` reinstates the **previously exposed password
> hashes** — i.e. it brings the leaked default credentials back. Rollback is an
> emergency measure only. As soon as access is recovered, run a fresh controlled
> rotation (steps 2–7) so the exposed credentials do not remain valid.

**Break-glass note:** the SEC-001 bootstrap (`python -m bootstrap create-admin`)
**cannot** be used for recovery once users exist — it refuses on any non-empty
user table. Emergency access therefore depends on (a) the recovery administrator
credential captured during rotation and (b) this verified backup. Keep both
available before starting.

### Post-restore verification
- The recovery administrator can log in.
- Application starts cleanly; no user/organisation was created at startup.
- Re-plan and re-run rotation to remove the restored leaked credentials.
