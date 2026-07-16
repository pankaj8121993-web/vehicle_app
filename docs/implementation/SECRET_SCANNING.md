# FleetFlow — Secret Scanning & Git-History Remediation (SEC-003)

This document describes FleetFlow's automated secret scanning, the developer
workflow, the incident-response procedure, and the **prepared (not executed)**
Git-history cleanup procedure for the historical leaked credentials.

Scanner: **gitleaks**, pinned to **v8.30.1** and verified by SHA-256 checksum in
both CI and the local helper. No secret values appear anywhere in this document —
only redacted fingerprints (rule id, commit, path).

---

## 1. What runs where

| Surface | How | What it does |
| --- | --- | --- |
| **CI (push & PR)** | `.github/workflows/secret-scan.yml` | Installs pinned, checksum-verified gitleaks; runs `gitleaks git . --config .gitleaks.toml --redact`; fails the job on any finding; uploads a redacted SARIF artifact. Third-party actions are pinned by commit SHA. |
| **Local (developer)** | `scripts/scan-secrets.sh` | Same pinned scanner and config. `--all` (history+tree, default), `--staged` (pre-commit), `--tree` (working tree). Redacted output; non-zero exit on findings. |
| **Config** | `.gitleaks.toml` | Extends the upstream ruleset (`useDefault = true`) and adds a narrow, justified allowlist. |
| **Self-test** | `backend/tests/test_secret_scanning.py` + `backend/tests/fixtures_secret_scan/` | Proves a safe fixture yields zero findings and a deliberate dummy-secret fixture is detected; proves the committed config allowlists the fixtures and the tracked tree scans clean. |

### Run it locally

```bash
scripts/scan-secrets.sh            # scan git history + working tree
scripts/scan-secrets.sh --staged   # pre-commit: scan staged changes only
scripts/scan-secrets.sh --tree     # scan the working tree without history
```

The helper downloads the pinned gitleaks into `~/.cache/fleetflow-gitleaks/`
(never committed) and verifies its checksum before use.

---

## 2. Allowlist policy (`.gitleaks.toml`)

Allowlisting is a last resort and every entry must be justified. Current entries:

- **`(^|/)\.env$` and `.env.*` paths** — local environment files are gitignored
  and must never be committed; real secrets live there only on a developer /
  operator machine.
- **`backend/tests/fixtures_secret_scan/.*`** — intentional dummy-secret fixtures
  for the scanner self-test. The self-test scans them **without** this config, so
  detection is still proven.
- **Placeholder regexes** (`YOUR_*TOKEN`, `<your-...>`, `<token>`) — documentation
  placeholders (e.g. `auth_testing.md`).

Do not add file-wide or repository-wide allowlists. Prefer removing the secret.

---

## 3. Response procedure — when the scanner flags something

1. **Do not print the secret** in tickets, chat, or CI logs (scans use `--redact`).
2. **Classify** the finding:
   - *False positive / placeholder* → add a **narrow** allowlist entry to
     `.gitleaks.toml` with a one-line justification, or rename the placeholder.
   - *Real secret in an unmerged change* → remove it from the change, replace
     with an env var / secret manager reference, and re-run the scan.
   - *Real secret already merged* → treat as an incident (next steps).
3. **Rotate first, always.** A committed secret must be considered compromised
   even after removal, because it remains in history and any clone/fork. Rotate
   the credential at its source (see `CREDENTIAL_ROTATION.md` for legacy
   application accounts; rotate DB/storage/API keys with the relevant provider).
4. **Revoke** active sessions/tokens derived from the secret where applicable.
5. **Remove from the working tree**, add an appropriate `.gitignore` rule, and
   land the fix.
6. **Plan history remediation** (section 5) if the secret is high-value and must
   not remain retrievable from history.
7. **Record** the incident (what category, when, rotation completed) without the
   secret value.

---

## 4. Current inventory (redacted fingerprints)

As of SEC-003 the **tracked working tree scans clean** under the committed
config. The scanner still reports findings in **historical** commits, which is
expected until a history rewrite is performed (section 5).

Redacted fingerprints (category · commit · path — **no values**):

| Category | Commit (short) | Path | Status |
| --- | --- | --- | --- |
| legacy default password (real) | `02b7a8827a` | `backend/server.py` | remediated in tree (SEC-001); still in history |
| legacy default password (real) | `02b7a8827a` | `backend/tests/test_fleet_backend.py` | remediated in tree (SEC-002); still in history |
| legacy default password (real) | `3e16d82658` | `backend/tests/test_fleetflow.py` | remediated in tree (SEC-002); still in history |
| legacy default password (real) | `86122eb5fc` | `backend/tests/test_rbac_matrix.py` | remediated in tree (SEC-002); still in history |
| session-token placeholder (false positive) | `353cc81000` | `auth_testing.md` | placeholder; allowlisted |

> Additional broad-rule matches in `742fe57b…` (`backend/bootstrap.py`,
> `backend/tests/test_bootstrap.py`, `docs/implementation/BOOTSTRAP.md`) are
> **dummy test values and documentation placeholders**, not real secrets, and are
> not flagged by the committed default-rule configuration.

**Credential categories identified:** (1) legacy default application passwords
for the seeded accounts (`admin`, `manager`, `dataentry1`, `driver1`, `test`) and
one dev-test onboarding account; (2) a documentation session-token placeholder
(not a real secret). The category-(1) values are also present in the earlier
`test_reports/*.json` and the gitignored `memory/test_credentials.md`, both of
which were redacted in the tree by SEC-001/SEC-002.

---

## 5. Git-history cleanup procedure (PREPARED — do not execute without approval)

> ⚠️ Rewriting shared history is **destructive**: it changes every commit SHA
> from the first affected commit onward, requires a coordinated force-push, and
> invalidates every existing clone/fork/open PR. SEC-003 **prepares** this
> procedure only. It must not be executed until the execution proposal (below)
> is approved and a maintenance window is scheduled. **Rotate the affected
> credentials first** — a history rewrite does not un-leak anything already
> exposed.

### Preconditions
1. All affected credentials have been rotated and old sessions revoked
   (`CREDENTIAL_ROTATION.md`). History cleanup is defence-in-depth, not a
   substitute for rotation.
2. A full mirror backup exists and is verified (see below).
3. Contributors are notified and have pushed/merged outstanding work; open PRs
   are paused.

### Backup (mandatory)
```bash
# Full mirror backup (all refs) BEFORE any rewrite:
git clone --mirror git@github.com:<owner>/<repo>.git repo-backup-$(date -u +%Y%m%dT%H%M%SZ).git
```
Store the mirror in a secure, access-controlled location.

### Recommended tool: git filter-repo
```bash
# 1. Fresh mirror working copy:
git clone --mirror git@github.com:<owner>/<repo>.git repo-rewrite.git
cd repo-rewrite.git

# 2. Provide the exact literal strings to purge via a replacements file
#    (kept OUTSIDE the repo; never committed). One rule per secret:
#      literal-old==>REDACTED
#    Build this file from the rotated (now-invalid) values.
git filter-repo --replace-text /secure/path/replacements.txt

#    Optionally also remove whole paths that only ever held secrets, e.g.:
#    git filter-repo --path memory/test_credentials.md --invert-paths

# 3. Review, then force-update the remote (coordinated window only):
git push --force --mirror
```
> `git filter-repo` is preferred over BFG for flexibility; BFG
> (`bfg --replace-text replacements.txt`) is an acceptable alternative. Do **not**
> use `git filter-branch` (slow, error-prone).

### After the rewrite
- Every collaborator must **re-clone** (or hard-reset to the rewritten refs);
  old local branches will not fast-forward.
- Re-open/rebase any PRs that were paused.
- Re-run `scripts/scan-secrets.sh --all` to confirm history is clean.
- Confirm the rotated credentials are the only valid ones.

### Approval boundary
The following are **out of scope for SEC-003** and require explicit approval and a
scheduled window: running `git filter-repo`/BFG on shared history, force-pushing
any branch or tag, deleting/rewriting remote refs, and invalidating clones. See
the SEC-003 PR / final report for the consolidated execution proposal (affected
refs, redacted categories, exact commands, backup method, contributor
coordination, force-push scope, clone-invalidation impact, rotation dependencies,
rollback limitations, and recommended maintenance window).

---

## 6. Upgrading the scanner
Bump `GITLEAKS_VERSION` and the pinned SHA-256 in **both** `.github/workflows/
secret-scan.yml` and `scripts/scan-secrets.sh` together (and
`PINNED_VERSION` in the self-test). Take the checksums from the official
`gitleaks_<version>_checksums.txt` release asset.
