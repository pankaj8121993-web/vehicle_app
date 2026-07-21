# SEC-004 — Dry-Run Guide (how the rotation tool works)

A plain-language explanation of `backend/rotate_legacy_credentials.py` so an
operator can build a correct manifest and read the output with confidence. **All
examples use synthetic identifiers.** Pair this with `SEC004_OPERATOR_CHECKLIST.md`
(the ordered steps) and `scripts/rehearse_sec004.sh` (prove it on synthetic data).

---

## The two commands

```bash
# 1) list — read-only. Prints the discovered legacy accounts and their active
#    session counts. No secrets, no writes.
python -m rotate_legacy_credentials list

# 2) apply — validates a manifest and either previews or executes.
python -m rotate_legacy_credentials apply --manifest manifest.json           # dry-run (default)
python -m rotate_legacy_credentials apply --manifest manifest.json --apply    # executes
```

**Dry-run is the default.** Without `--apply`, the tool validates the manifest and
prints exactly what it *would* do, writing **nothing** and creating **no audit
records**. `--apply` is the only thing that changes data.

## What counts as a "legacy" account

Discovery selects users with `created_by == "system"` — the provenance marker the
removed SEC-001 seeder wrote — and **excludes demo accounts**. A demo account is
anything with `is_demo == true`, `created_by == "demo_seed"`, `org_id` equal to the
canonical demo org, or a `demo_`-prefixed username. Onboarding/bootstrap/admin-
created accounts (`created_by` of `onboarding`, `bootstrap`, or an admin UUID) are
**not** legacy and cannot be targeted.

## Manifest structure

The manifest is a JSON file you build after reviewing `list`. It **never contains
passwords**. Synthetic example:

```json
{
  "operator": "your-operator-id",
  "actions": [
    {"user_id": "usr-1111", "username": "legacy_admin",   "action": "rotate"},
    {"user_id": "usr-2222", "username": "legacy_test",     "action": "deactivate"},
    {"user_id": "usr-3333", "username": "legacy_viewer",   "action": "skip"}
  ],
  "recovery_admins": [
    {"user_id": "usr-9999", "org_id": "org-abc",
     "username": "recovery_admin", "has_known_password": true}
  ]
}
```

- **`operator`** — a non-empty identifier for who is running this. Recorded in the
  audit and the report.
- **`actions`** — one entry **per discovered legacy account**. Each has a
  `user_id`, an optional `username` (checked against the real one as an integrity
  guard), and an `action`. **No `password` field is allowed** anywhere.
- **`recovery_admins`** — one entry **per affected organisation**, identifying the
  administrator who guarantees continued access.

### The three actions

| Action | Effect |
| --- | --- |
| `rotate` | Set a new password (entered interactively at `--apply`), set `must_change_password`, and revoke that user's sessions. |
| `deactivate` | Set `is_active = false` and revoke that user's sessions. |
| `skip` | Leave the account entirely unchanged. |

### `recovery_admins` — by exact `user_id`

Every organisation touched by a `rotate` or `deactivate` **must** declare exactly
one recovery administrator, identified by **exact `user_id`** (not username alone).
The tool validates that this user: exists, is **not** a demo account, has an
administrative role (`admin` / `org_admin`), is **active**, has a `username`
matching the `user_id`, and belongs to the declared `org_id`. An admin in a
different organisation can never satisfy another org's requirement.

- If the recovery admin is itself being **`rotate`**d, that is fine — a fresh
  known-good password is set for it during the run.
- If the recovery admin is **not** in `actions`, or is set to **`skip`**, you must
  assert `"has_known_password": true` — you are declaring that this admin already
  holds a working credential you can log in with.
- The tool **refuses to `deactivate` a recovery administrator**, and refuses any
  plan that would leave an affected organisation with **zero** active admins.

## Enforcement the tool applies (why a manifest gets rejected)

- **Exhaustive:** every discovered legacy account must appear **exactly once**. A
  missing one is rejected (`Manifest is not exhaustive: … Missing: …`). Duplicates
  are rejected.
- **Legacy-only:** an action targeting a non-legacy or unknown `user_id` is
  rejected; a demo account anywhere is rejected.
- **No secrets in the manifest:** any `password` field is rejected.
- **Per-org admin protection:** as above — recovery admin validated, last-admin
  loss refused, recovery admin cannot be deactivated.

## How passwords are entered (never in a file)

At `--apply`, the tool validates the manifest first (read-only), then prompts for a
**hidden** new password for each `rotate` account, **entered twice**, before any
change is made. It also requires you to type `APPLY` as a final confirmation.
Passwords are used only to hash (bcrypt) and are **never** written to the manifest,
the report, the audit, or logs.

## Session revocation and the mandatory restart

A successful `rotate`/`deactivate` revokes that user's sessions (`revoked = true`)
in the database. **This is not enough on its own:** the backend keeps a short-lived
in-memory session cache, so you **must restart the backend immediately** after
`--apply` for revocation to take effect globally with no stale-token window. This
is a required step, not optional.

## Audit behaviour

At `--apply` (never in dry-run), the tool writes one `security_audit` record per
applied `rotate`/`deactivate` action, containing **non-secret metadata only**:
operator, action, outcome, `user_id`, `username`, `org_id`, and the session-
revocation count. Failures are audited with a failure **category** only — never a
message or any secret.

## Reading the output

The report prints the mode (`dry_run` / `apply`), the operator, the affected
organisations, the recovery administrators, then a table of **every** discovered
legacy account with its action and outcome, and totals:

```
Totals: rotated=2 deactivated=1 skipped=1 failed=0 sessions_revoked=3
```

- **Dry-run** ends with a reminder that nothing was written.
- **Apply** ends with a reminder that you **must restart the backend now**.
- `failed` must be `0`. Any failure means **stop and roll back**.

## Common validation failures

| Message (paraphrased) | Cause / fix |
| --- | --- |
| Manifest is not exhaustive … Missing … | A discovered legacy account has no action. Add it. |
| targets a non-legacy account | The `user_id` is not `created_by:"system"`. Remove it. |
| targets a demo account — refused | A demo account is in the manifest. Remove it. |
| must not contain a password | Remove every `password` field from the manifest. |
| references unknown user_id | The `user_id` does not exist. Re-check against `list`. |
| Organisation … has no recovery administrator declared | Add a `recovery_admins` entry for that org. |
| declares organisation … not affected — remove it | A `recovery_admins` org is not touched by any action. Remove it. |
| would leave organisation … with zero active administrators | Your deactivations remove the last admin. Keep one active. |
| username does not match the user_id's actual username | Integrity guard — fix the `username` or the `user_id`. |

## What dry-run does **not** prove

- It does **not** prove the backend restart works, the health check passes, or
  the recovery admin can actually log in — those are live steps in Sections 5–6 of
  the checklist.
- It does **not** take or verify a backup — that is Section 1, and is mandatory
  before `--apply`.
- It does **not** prove your production **connectivity or identity** — confirm
  those in Section 0.
- It validates the manifest against the **current** database; if the data changes
  between dry-run and `--apply`, re-run the dry-run.

## Why rollback is emergency-only

Restoring the `users` backup reinstates the **previously exposed** password hashes
— it brings the leaked default credentials back to life. Use it only to recover
from a stop condition (e.g. a locked-out recovery admin), and re-run the rotation
immediately afterwards so the exposed credentials do not remain valid. The SEC-001
bootstrap cannot help here — it refuses to run once any user exists.

## Rehearse first

Before production, run the harness against a disposable synthetic database:

```bash
MONGO_URL=mongodb://localhost:27017 bash scripts/rehearse_sec004.sh
```

It seeds synthetic organisations, legacy accounts, a demo account, recovery
admins and sessions; runs the tool in dry-run then `--apply` against a **uniquely
named throwaway database only**; asserts that rotated hashes changed, deactivated
users went inactive, skipped users are untouched, target sessions were revoked,
non-target and demo sessions survived, each org kept an active admin, and the
audit holds no secrets; then drops the throwaway database. It refuses any
production-like target and never prints `MONGO_URL`.
