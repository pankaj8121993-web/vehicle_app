# SEC-004 — Operator Execution Checklist

**Purpose:** the exact, ordered steps for an **authorised operator** to rotate the
legacy default credentials in the **live production** FleetFlow database and
revoke their sessions, using the already-built and tested SEC-002 tool.

**This is a production operational task.** It is not, and must not be, run by an
automated agent, from the preview/development container, or against
`test_database`. Read this whole document, then rehearse (`scripts/rehearse_sec004.sh`,
see `SEC004_DRY_RUN_GUIDE.md`) before touching production.

**Companion documents**
- `docs/implementation/CREDENTIAL_ROTATION.md` — the underlying runbook (commands).
- `docs/implementation/SEC004_DRY_RUN_GUIDE.md` — how the tool and manifest work.
- `docs/implementation/SEC004_EVIDENCE_LOG_TEMPLATE.md` — record every result here.
- `scripts/rehearse_sec004.sh` — prove the tool on synthetic data first.

---

## STOP CONDITIONS — abort and roll back immediately if any occur

> If **any** of these is true at any point, **stop, do not proceed, and roll back**
> to the verified backup (Section 9) if a change has already been applied:
>
> 1. You are not certain you are connected to the correct **production** database.
> 2. The backup failed, is incomplete, or its counts cannot be verified.
> 3. The manifest is not exhaustive (a discovered legacy account is missing).
> 4. Any demo account appears in the manifest actions.
> 5. Recovery-admin validation fails for any affected organisation.
> 6. The plan would leave any organisation with **zero** active administrators.
> 7. Rotation partially fails (`failed > 0` in the report).
> 8. Session-revocation counts are inconsistent with the actions applied.
> 9. The backend restart fails or the service does not come back healthy.
> 10. The health check does not return success.
> 11. The recovery administrator cannot log in after the change.
> 12. Demo login or demo behaviour changes in any way.
> 13. Any unexpected database change appears (rows/counts you did not intend).
>
> Rollback restores the **previously exposed** password hashes — it is an
> emergency measure only (Section 9). Keep the backup until every verification
> in Section 8 has passed.

---

## Section 0 — Environment and prerequisites (no writes)

- [ ] **0.1 Confirm the maintenance window** is open and stakeholders are notified.
- [ ] **0.2 Confirm you are on the production operator host**, not the preview
      container, not a developer laptop pointed at a shared DB.
- [ ] **0.3 Confirm `MONGO_URL` and `DB_NAME` are set _in the environment_ without
      printing their values:**
      ```bash
      test -n "$MONGO_URL" && echo "MONGO_URL is set" || echo "MONGO_URL MISSING"
      test -n "$DB_NAME"  && echo "DB_NAME is set: $DB_NAME" || echo "DB_NAME MISSING"
      ```
      (Printing `DB_NAME` is fine; it is not a secret. **Never** echo `MONGO_URL`.)
- [ ] **0.4 Confirm you are NOT pointed at localhost or `test_database`:**
      ```bash
      python3 - <<'PY'
      import os, urllib.parse
      p = urllib.parse.urlparse(os.environ["MONGO_URL"])
      host = (p.hostname or "").lower()
      print("host is local:", host in ("localhost", "127.0.0.1"))
      print("DB_NAME is test_database:", os.environ.get("DB_NAME") == "test_database")
      PY
      ```
      If **host is local: True** or **DB_NAME is test_database: True**, you are NOT
      on production — **STOP** (condition 1).
- [ ] **0.5 Confirm tooling is present:**
      ```bash
      command -v mongodump && command -v mongorestore && python3 --version
      python3 -c "import typer, passlib, motor; print('deps OK')"
      ```
- [ ] **0.6 Confirm adequate free disk** at the backup destination (the dump must
      fit; allow headroom): `df -h /secure/backups`.
- [ ] **0.7 Confirm the backend restart method** for this deployment (systemd unit,
      container restart, process manager) and write it in the evidence log.
- [ ] **0.8 Confirm the health-check URL** (e.g. `https://<prod>/api/`) returns 200
      **now**, before changes: `curl -fsS -o /dev/null -w '%{http_code}\n' "$HEALTH_URL"`.
- [ ] **0.9 Confirm recovery-admin access BEFORE any change** — log in as the
      intended recovery administrator for each organisation you will touch, and
      confirm it works. If you cannot, **STOP** (condition 11 pre-empted).
- [ ] **0.10 Record** the application version/commit deployed (evidence log).

## Section 1 — Backup (mandatory, before any change)

- [ ] **1.1 Back up `users`:**
      ```bash
      STAMP=$(date -u +%Y%m%dT%H%M%SZ)
      DEST="/secure/backups/sec004-$STAMP"     # restricted, encrypted-at-rest
      mongodump --uri "$MONGO_URL" --db "$DB_NAME" --collection users --out "$DEST"
      ```
- [ ] **1.2 Back up `user_sessions`:**
      ```bash
      mongodump --uri "$MONGO_URL" --db "$DB_NAME" --collection user_sessions --out "$DEST"
      ```
      (Prefer exporting `MONGO_URL` and omitting `--uri` to keep it out of shell
      history / the process list.)
- [ ] **1.3 Verify the backup files exist and are non-empty:**
      ```bash
      ls -l "$DEST/$DB_NAME/users.bson" "$DEST/$DB_NAME/user_sessions.bson"
      ```
- [ ] **1.4 Verify backup counts** against the live DB (record both numbers):
      ```bash
      mongosh "$MONGO_URL" --quiet --eval \
        'db.getSiblingDB(process.env.DB_NAME).users.countDocuments({})'
      ```
      If files are empty or counts look wrong — **STOP** (condition 2).
- [ ] **1.5 Secure the backup location** (restricted permissions, encrypted at
      rest). It contains password **hashes** — treat as sensitive. Record its
      **reference** (path/label) in the evidence log — never its contents.

## Section 2 — Discover and plan (no writes)

- [ ] **2.1 List the legacy accounts** (read-only; no secrets):
      ```bash
      cd /path/to/app/backend
      python -m rotate_legacy_credentials list
      ```
      Record the **count** of discovered legacy accounts.
- [ ] **2.2 Build the exhaustive manifest** (`SEC004_DRY_RUN_GUIDE.md` §Manifest).
      Every discovered legacy account must appear **exactly once** with an action
      (`rotate` / `deactivate` / `skip`). The manifest contains **no passwords**.
- [ ] **2.3 Verify exhaustiveness:** the number of `actions` equals the discovered
      count from 2.1, and no `user_id` repeats.
- [ ] **2.4 Verify per-organisation recovery admins by exact `user_id`:** every
      organisation touched by a `rotate`/`deactivate` has exactly one
      `recovery_admins` entry identifying an **active, non-demo administrator** by
      `user_id`, with `org_id` matching. Confirm no demo account is anywhere in
      the manifest. If any check fails — **STOP** (conditions 3–6).

## Section 3 — Dry-run (no writes)

- [ ] **3.1 Run the dry-run** (default; makes no changes):
      ```bash
      python -m rotate_legacy_credentials apply --manifest manifest.json
      ```
- [ ] **3.2 Review the dry-run output:** the "Complete discovered legacy set and
      selected action" table lists **every** legacy account, the actions match your
      intent, affected organisations and recovery admins are correct, and the tool
      did **not** reject the manifest. If it printed `Rotation refused` or
      `Manifest rejected` — fix the manifest and repeat. Do not proceed on any
      rejection.

## Section 4 — Apply (writes changes)

- [ ] **4.1 Execute:**
      ```bash
      python -m rotate_legacy_credentials apply --manifest manifest.json --apply
      ```
- [ ] **4.2 Enter each rotation password** at the hidden prompt (entered twice).
      Choose strong, unique passwords. The tool never echoes or stores them.
- [ ] **4.3 Type `APPLY`** at the final confirmation. (Anything else aborts with no
      change.)
- [ ] **4.4 Confirm `failed=0`** in the totals. If `failed > 0` — **STOP** and roll
      back (condition 7).
- [ ] **4.5 Record the session-revocation counts** (per account and the total) in
      the evidence log. Confirm they are consistent with the rotate/deactivate
      actions (condition 8).

## Section 5 — Restart the backend (mandatory, immediately)

- [ ] **5.1 Restart the backend** so the in-memory session cache
      (`auth._session_cache`, ~60s TTL) is flushed and revocation is global:
      ```bash
      # however THIS deployment restarts the API — confirmed in 0.7, e.g.:
      sudo systemctl restart fleetflow-backend
      ```
      Do not rely on the cache TTL as the revocation guarantee. If the restart
      fails — **STOP** (condition 9).

## Section 6 — Verify (all must pass)

- [ ] **6.1 Health check** returns success: `curl -fsS -o /dev/null -w '%{http_code}\n' "$HEALTH_URL"`.
- [ ] **6.2 Recovery-admin login works** for every affected organisation (if that
      admin was rotated, it is prompted to change password). Fail → **STOP** (11).
- [ ] **6.3 Old/leaked passwords are rejected** (`POST /api/auth/login` → 401) for
      rotated/deactivated accounts.
- [ ] **6.4 An old session token for a rotated/deactivated user is rejected** (401).
- [ ] **6.5 Deactivated accounts cannot log in.**
- [ ] **6.6 Demo flow unchanged:** `POST /api/demo/enter` still works; existing
      demo sessions remain valid; demo users are untouched. Any change → **STOP** (12).
- [ ] **6.7 `security_audit`** contains one record per applied action, with **no
      secrets**. (Non-secret metadata only.)
- [ ] **6.8 No unexpected changes:** spot-check that only the intended accounts and
      sessions changed (condition 13).

## Section 7 — Close out

- [ ] **7.1 Retain rollback capability** until **every** check in Section 6 has
      passed. Only then consider the change committed.
- [ ] **7.2 Securely delete temporary manifests** and any working files:
      ```bash
      shred -u manifest.json 2>/dev/null || rm -f manifest.json
      ```
- [ ] **7.3 Retain or delete the backup per policy.** If retained, keep it in the
      restricted encrypted location and record the retention/deletion date. If the
      policy is to delete after a hold period, schedule and record it.
- [ ] **7.4 Complete the evidence log** (`SEC004_EVIDENCE_LOG_TEMPLATE.md`) and
      obtain the reviewer sign-off.
- [ ] **7.5 Notify** that SEC-004 is complete and update
      `SECURITY_EXECUTION_STATUS.md` (SEC-004 → executed, with date, without
      secrets). SEC-005 may now be planned (it is separately gated).

## Section 8 — Rollback (emergency only)

Use only if a stop condition forces it (e.g. the recovery admin is locked out).

```bash
mongorestore --uri "$MONGO_URL" --db "$DB_NAME" --collection users \
             --drop "$DEST/$DB_NAME/users.bson"
mongorestore --uri "$MONGO_URL" --db "$DB_NAME" --collection user_sessions \
             --drop "$DEST/$DB_NAME/user_sessions.bson"
# then restart the backend again (Section 5).
```

> ⚠️ Restoring `users` **reinstates the previously exposed password hashes** — it
> brings the leaked credentials back. As soon as access is recovered, re-plan and
> re-run the rotation (Sections 1–6) so the exposed credentials do not remain
> valid. The SEC-001 bootstrap **cannot** be used for recovery once users exist.
