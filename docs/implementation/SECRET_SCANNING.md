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
scripts/scan-secrets.sh --tree     # scan tracked + non-ignored untracked files (no history)
```

The helper downloads the pinned gitleaks into `~/.cache/fleetflow-gitleaks/`
(never committed) and verifies its checksum before use.

---

## 2. Allowlist policy (`.gitleaks.toml`)

Allowlisting is a last resort and every entry must be justified. Current entries:

- **`backend/tests/fixtures_secret_scan/.*`** — intentional dummy-secret fixtures
  for the scanner self-test. The self-test scans them **without** this config, so
  detection is still proven.
- **Placeholder regexes** (`YOUR_*TOKEN`, `<your-...>`, `<token>`) — documentation
  placeholders (e.g. `auth_testing.md`).

**`.env` files are deliberately NOT allowlisted.** Local `.env` files are kept
out of scans by `.gitignore` **plus** git-based file selection — the working-tree
scan (`scripts/scan-secrets.sh --tree`) scans exactly
`git ls-files -co --exclude-standard` (tracked + non-ignored untracked), so an
ordinary ignored `.env` is never copied or scanned, **but a tracked or
force-added `.env` is still scanned and will fail CI, staged, history and
working-tree scans**. This is a correctness property, verified by
`backend/tests/test_secret_scanning.py`.

Do not add file-wide, `.env`-wide, or repository-wide allowlists. Prefer removing
the secret.

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

There are **two distinct findings**; do not conflate them:

**A. Committed gitleaks rules (the automated scanner).** The pinned ruleset in
`.gitleaks.toml` detects supported *high-signal* secret patterns (API keys,
tokens, private keys, etc.). Under this config the **tracked working tree scans
clean**, and CI + local scans gate against new secrets of those categories.

**B. Legacy default passwords — a separate, manual known-value historical
audit.** The old seeded default passwords are **simple, low-entropy strings**
that generic secret-scanner rules do **not** reliably detect. Their presence in
old history was established by a **separate one-time audit that searched history
for the already-known, already-compromised values** (values learned during
SEC-001/SEC-002), producing only **redacted** counts, paths and commit ids. This
audit is not part of the committed scanner and its inputs are not stored in the
repository.

> ⚠️ **A green gitleaks result does NOT prove the low-entropy legacy defaults are
> absent from old history.** Absence of those specific values must be verified
> separately with a secure external known-value list (never committed), reporting
> only redacted counts/paths/commits — see §5.

Redacted fingerprints from audit **B** (category · commit · path — **no values**):

| Category | Commit (short) | Path |
| --- | --- | --- |
| legacy default password | `02b7a8827a` | `backend/server.py` |
| legacy default password | `02b7a8827a` | `backend/tests/test_fleet_backend.py` |
| legacy default password | `3e16d82658` | `backend/tests/test_fleetflow.py` |
| legacy default password | `86122eb5fc` | `backend/tests/test_rbac_matrix.py` |

The same category also appears in earlier `test_reports/*.json` and the
gitignored `memory/test_credentials.md`; all were redacted in the tree by
SEC-001/SEC-002. A separate scanner match on `353cc81000` `auth_testing.md` is a
documentation **session-token placeholder** (false positive; allowlisted), and
broad-probe matches in `742fe57b…` (`backend/bootstrap.py`,
`backend/tests/test_bootstrap.py`, `docs/implementation/BOOTSTRAP.md`) are
**dummy test values / doc placeholders**, not real secrets.

**None of the actual legacy password values are stored anywhere in this
repository** — not in `.gitleaks.toml`, tests, scripts, fixtures, logs, or this
document. Only redacted fingerprints (category, commit, path) are recorded.

---

## 5. Git-history cleanup procedure (PREPARED — do not execute without approval)

> ⚠️ Rewriting shared history is **destructive and irreversible for downstream
> copies**: it changes every commit SHA from the first affected commit onward,
> requires a coordinated `--force` push, and invalidates every existing
> clone/fork/open PR. SEC-003 **prepares** this procedure only. Even a completed
> rewrite **cannot** remove the values from third-party clones, forks, caches, or
> any uncontrolled copy — so **rotation (§ SEC-002) is the primary control** and
> history cleanup is defence-in-depth. This aligns with GitHub's current
> "removing sensitive data from a repository" guidance.

### 5.1 Preconditions (all must hold before starting)
1. **SEC-002 production credential rotation and session revocation are complete
   and verified** (`CREDENTIAL_ROTATION.md`): the leaked values are already
   invalid. History cleanup never substitutes for rotation.
2. **All open pull requests are merged or closed** (a rewrite orphans PR refs).
3. A **verified secure mirror backup** exists (5.2).
4. `git filter-repo` **>= 2.47** is installed (`git filter-repo --version`).
5. Contributors are notified; a maintenance window is scheduled; a fork
   inventory has been taken (5.6).

### 5.2 Backup (mandatory)
```bash
# Full mirror of ALL refs BEFORE any rewrite; store in secure, access-controlled storage.
git clone --mirror git@github.com:<owner>/<repo>.git repo-backup-$(date -u +%Y%m%dT%H%M%SZ).git
# Verify it: confirm ref count / branch tips match the live remote.
git -C repo-backup-*.git for-each-ref | wc -l
```

### 5.3 Rewrite (git filter-repo, sensitive-data mode)
```bash
# Fresh mirror working copy (never rewrite your everyday clone):
git clone --mirror git@github.com:<owner>/<repo>.git repo-rewrite.git
cd repo-rewrite.git

# The replacement/verification file lives OUTSIDE the repo on secure storage and
# is NEVER committed. One rule per known value, built from the already-rotated
# (now-invalid) values:  <literal-old>==>REDACTED
#
# Use --sensitive-data-removal so filter-repo keeps the original commit
# messages/authorship semantics appropriate for secret removal.
git filter-repo \
  --sensitive-data-removal \
  --replace-text /secure/replacements.txt

# Where the inspection confirms a path only ever held secrets, also drop it:
git filter-repo --sensitive-data-removal --path memory/test_credentials.md --invert-paths
```
> `git filter-repo` is the recommended tool; `git filter-branch` must not be
> used. BFG is an acceptable alternative only if filter-repo is unavailable.

### 5.4 Post-rewrite verification (before pushing)
- Re-run detection over the rewritten history:
  `gitleaks git . --config .gitleaks.toml --redact` → expect clean.
- Verify the **known low-entropy defaults** are gone using the **external**
  known-value file (never printed, never committed); report only **redacted**
  counts / paths / commit ids.
- Determine everything the rewrite changed by inspecting:
  ```bash
  cat .git/filter-repo/changed-refs
  ```
  and **record**: the first changed commit(s) per ref, the number and identifiers
  of affected **PR refs** (`refs/pull/*`), and any **orphaned LFS objects**.

### 5.5 Coordinated force-push (approved window only)
```bash
# Temporarily relax branch protection on affected branches if it blocks the push,
# then restore it IMMEDIATELY afterwards.
git push --force --mirror origin
```
- Scope: `--force --mirror` rewrites **all** server refs from the backup/rewrite
  mirror — this is the one operation that also rewrites `main`. It must happen
  only inside the approved window.

### 5.6 After the push
1. **GitHub Support follow-up** (web UI rewrite alone does not purge server-side
   copies). Open a ticket requesting: dereferencing of affected **PR references**,
   removal of **cached/stale views**, repository **garbage collection**, and
   **LFS cleanup** where applicable.
2. **Restore branch protection** immediately if it was relaxed.
3. **Contributor instructions:** every collaborator must **re-clone**, or very
   carefully rebase in-flight work onto the rewritten history.
4. ⚠️ **Never merge an old clone or old branch into the rewritten history** —
   doing so **reintroduces the removed commits** (and the secrets). Abandon or
   cherry-pick-with-care instead.
5. **Forks:** coordinate with every fork owner from the 5.1 inventory to rewrite
   or delete their copy; GitHub does not rewrite forks for you.
6. Re-open/rebase the PRs that were closed in 5.1 preconditions.

### 5.7 Residual-risk statement
Even after a successful rewrite and GitHub cleanup, the values may persist in
third-party clones, forks, mirrors, CI caches, and backups outside your control.
Treat the credentials as permanently compromised — **rotation is what protects
you**, not the rewrite.

### Approval boundary
Out of scope for SEC-003 and requiring explicit approval + a scheduled window:
running `git filter-repo`, force-pushing any branch/tag, deleting/rewriting
remote refs, invalidating clones, and GitHub Support actions. The consolidated
execution proposal (affected refs, redacted categories, exact commands, backup,
contributor coordination, force-push scope, clone-invalidation impact, rotation
dependencies, rollback limits, window) accompanies the SEC-003 report.

---

## 6. Upgrading the scanner
Bump `GITLEAKS_VERSION` and the pinned SHA-256 in **both** `.github/workflows/
secret-scan.yml` and `scripts/scan-secrets.sh` together (and
`PINNED_VERSION` in the self-test). Take the checksums from the official
`gitleaks_<version>_checksums.txt` release asset.
