"""
Deterministic verification for SEC-003 secret scanning.

Proves that the pinned scanner (gitleaks) and the safe working-tree file
selection behave as required:

  * the committed config does NOT broadly allowlist `.env`;
  * an ignored, untracked local `.env` is excluded from the working-tree scan;
  * a tracked / force-added `.env` containing a secret IS scanned and detected;
  * a normal (non-ignored) untracked file with a secret IS scanned and detected;
  * safe tracked files pass;
  * the deliberate dummy-secret fixture is detected without the repo allowlist;
  * output is redacted.

Everything uses temporary isolated git repositories and the committed dummy
fixture. No real secrets are used, and no detectable secret pattern is inlined
in this test's source (the dummy value is read from the allowlisted fixture at
runtime), so the repository's own scan of this file stays clean.

If gitleaks is not available (neither on PATH nor in the local cache used by
scripts/scan-secrets.sh) the scanner-dependent tests skip with a clear reason.
"""
import os
import re
import json
import shutil
import subprocess
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
FIXTURES = os.path.join(HERE, "fixtures_secret_scan")
SAFE = os.path.join(FIXTURES, "safe_example.txt")
DUMMY = os.path.join(FIXTURES, "dummy_leak_example.txt")
CONFIG = os.path.join(REPO_ROOT, ".gitleaks.toml")
SCRIPT = os.path.join(REPO_ROOT, "scripts", "scan-secrets.sh")
PINNED_VERSION = "8.30.1"

# The deliberately-fake secret is read from the allowlisted fixture at runtime so
# no detectable secret pattern lives in this test's source.
DUMMY_SECRET_TEXT = open(DUMMY).read()
SAFE_TEXT = open(SAFE).read()


def _find_gitleaks():
    exe = shutil.which("gitleaks")
    if exe:
        return exe
    cache = os.path.join(
        os.environ.get("XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache")),
        "fleetflow-gitleaks", PINNED_VERSION, "gitleaks",
    )
    return cache if os.path.exists(cache) else None


GITLEAKS = _find_gitleaks()
requires_gitleaks = pytest.mark.skipif(
    GITLEAKS is None,
    reason="gitleaks not installed; run scripts/scan-secrets.sh once or install "
           f"gitleaks {PINNED_VERSION} to exercise these tests",
)


# --------------------------- helpers -----------------------------------------

def _gitleaks_dir(path, use_config):
    """Run gitleaks on a directory/file; return the list of findings (redacted)."""
    with tempfile.TemporaryDirectory() as tmp:
        report = os.path.join(tmp, "report.json")
        cmd = [GITLEAKS, "dir", path, "--redact", "--no-banner",
               "--report-format", "json", "--report-path", report]
        if use_config:
            cmd += ["--config", CONFIG]
        subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        with open(report) as fh:
            return json.load(fh)


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(repo):
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "test")


def _safe_file_set(repo):
    """Tracked + non-ignored untracked files — the working-tree scan candidates."""
    out = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout
    return [p for p in out.split("\0") if p]


def _scan_safe_tree(repo, use_config):
    """Replicate scripts/scan-secrets.sh --tree: copy the safe file set into a
    temp dir (preserving paths) and scan it."""
    files = _safe_file_set(repo)
    with tempfile.TemporaryDirectory() as tmp:
        scan = os.path.join(tmp, "scan")
        for f in files:
            dst = os.path.join(scan, f)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(repo, f), dst)
        report = os.path.join(tmp, "report.json")
        cmd = [GITLEAKS, "dir", scan, "--redact", "--no-banner",
               "--report-format", "json", "--report-path", report]
        if use_config:
            cmd += ["--config", CONFIG]
        subprocess.run(cmd, capture_output=True, text=True)
        with open(report) as fh:
            return json.load(fh)


# --------------------------- config regression -------------------------------

def test_fixtures_and_config_exist():
    assert os.path.exists(SAFE) and os.path.exists(DUMMY) and os.path.exists(CONFIG)
    assert os.path.exists(SCRIPT)


def test_config_does_not_broadly_allowlist_env():
    try:
        import tomllib
    except ModuleNotFoundError:  # py<3.11
        import tomli as tomllib
    with open(CONFIG, "rb") as fh:
        cfg = tomllib.load(fh)
    paths = cfg.get("allowlist", {}).get("paths", [])
    # No allowlist path may match a `.env` file — otherwise a tracked/force-added
    # .env would be silently ignored by the scanner.
    for pattern in paths:
        assert not re.search(pattern, ".env"), f"path allowlist matches .env: {pattern}"
        assert not re.search(pattern, "backend/.env"), f"path allowlist matches .env: {pattern}"
        assert not re.search(pattern, ".env.production"), f"allowlist matches .env.*: {pattern}"


# --------------------------- detection (no repo allowlist) -------------------

@requires_gitleaks
def test_safe_fixture_has_no_findings_default_rules():
    assert _gitleaks_dir(SAFE, use_config=False) == []


@requires_gitleaks
def test_dummy_secret_is_detected_default_rules():
    findings = _gitleaks_dir(DUMMY, use_config=False)
    assert len(findings) >= 1
    assert any("private-key" in f.get("RuleID", "") for f in findings)


@requires_gitleaks
def test_repo_config_allowlists_intentional_fixtures():
    # With the committed config the intentional dummy fixture is allowlisted, so
    # a repo-wide scan is not blocked by it.
    assert _gitleaks_dir(DUMMY, use_config=True) == []


@requires_gitleaks
def test_output_is_redacted():
    findings = _gitleaks_dir(DUMMY, use_config=False)
    assert findings
    for f in findings:
        assert f.get("Secret", "") in ("", "REDACTED")


# --------------------------- safe working-tree selection ---------------------

@requires_gitleaks
def test_ignored_untracked_env_is_excluded_from_safe_tree():
    with tempfile.TemporaryDirectory() as repo:
        _init_repo(repo)
        with open(os.path.join(repo, ".gitignore"), "w") as fh:
            fh.write(".env\n")
        with open(os.path.join(repo, "app.txt"), "w") as fh:
            fh.write(SAFE_TEXT)                      # safe tracked file
        _git(repo, "add", ".gitignore", "app.txt")
        _git(repo, "commit", "-qm", "init")
        # ignored, untracked .env holding a dummy secret
        with open(os.path.join(repo, ".env"), "w") as fh:
            fh.write(DUMMY_SECRET_TEXT)
        assert ".env" not in _safe_file_set(repo)     # excluded from the set
        assert _scan_safe_tree(repo, use_config=True) == []   # and not scanned


@requires_gitleaks
def test_tracked_forced_env_with_secret_is_detected():
    with tempfile.TemporaryDirectory() as repo:
        _init_repo(repo)
        with open(os.path.join(repo, ".gitignore"), "w") as fh:
            fh.write(".env\n")
        # Force-add a .env despite .gitignore, so it is TRACKED.
        with open(os.path.join(repo, ".env"), "w") as fh:
            fh.write(DUMMY_SECRET_TEXT)
        _git(repo, "add", ".gitignore")
        _git(repo, "add", "-f", ".env")
        _git(repo, "commit", "-qm", "init")
        assert ".env" in _safe_file_set(repo)          # tracked -> in the set
        findings = _scan_safe_tree(repo, use_config=True)
        assert len(findings) >= 1                        # and detected
        assert all(f.get("Secret", "") in ("", "REDACTED") for f in findings)


@requires_gitleaks
def test_untracked_nonignored_file_with_secret_is_detected():
    with tempfile.TemporaryDirectory() as repo:
        _init_repo(repo)
        with open(os.path.join(repo, "readme.txt"), "w") as fh:
            fh.write(SAFE_TEXT)
        _git(repo, "add", "readme.txt")
        _git(repo, "commit", "-qm", "init")
        # untracked, NOT ignored -> a commit candidate -> must be scanned
        with open(os.path.join(repo, "leak.txt"), "w") as fh:
            fh.write(DUMMY_SECRET_TEXT)
        assert "leak.txt" in _safe_file_set(repo)
        assert len(_scan_safe_tree(repo, use_config=True)) >= 1


@requires_gitleaks
def test_safe_tracked_files_pass():
    with tempfile.TemporaryDirectory() as repo:
        _init_repo(repo)
        with open(os.path.join(repo, "config.txt"), "w") as fh:
            fh.write(SAFE_TEXT)
        _git(repo, "add", "config.txt")
        _git(repo, "commit", "-qm", "init")
        assert _scan_safe_tree(repo, use_config=True) == []


# --------------------------- real-repo integration ---------------------------

@requires_gitleaks
def test_working_tree_script_scan_is_clean():
    # The actual helper must report the tracked tree clean (ignored local
    # backend/.env is excluded by the git-based file selection).
    r = subprocess.run(["bash", SCRIPT, "--tree"], cwd=REPO_ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
