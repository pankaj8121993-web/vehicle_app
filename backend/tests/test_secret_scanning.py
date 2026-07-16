"""
Deterministic verification for SEC-003 secret scanning.

Proves that the pinned scanner (gitleaks) behaves as required:
  * a known-safe fixture (placeholders only) produces zero findings, and
  * a deliberate dummy-secret fixture is detected.

It also proves the committed repo config (.gitleaks.toml) allowlists the
intentional fixtures, so the repository-wide scan is not blocked by them.

The test drives the real scanner via subprocess. If gitleaks is not available
(neither on PATH nor in the local cache used by scripts/scan-secrets.sh) the
test skips with a clear reason rather than failing.
"""
import os
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
PINNED_VERSION = "8.30.1"


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


def _scan(path, use_config):
    """Run gitleaks on a single file; return the list of findings (redacted)."""
    with tempfile.TemporaryDirectory() as tmp:
        report = os.path.join(tmp, "report.json")
        cmd = [GITLEAKS, "dir", path, "--redact", "--no-banner",
               "--report-format", "json", "--report-path", report]
        if use_config:
            cmd += ["--config", CONFIG]
        # gitleaks exits 1 when leaks are found; both 0 and 1 are expected here.
        subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        with open(report) as fh:
            return json.load(fh)


def test_fixtures_exist():
    assert os.path.exists(SAFE) and os.path.exists(DUMMY) and os.path.exists(CONFIG)


@requires_gitleaks
def test_safe_fixture_has_no_findings_default_rules():
    assert _scan(SAFE, use_config=False) == []


@requires_gitleaks
def test_dummy_secret_is_detected_default_rules():
    findings = _scan(DUMMY, use_config=False)
    assert len(findings) >= 1
    # never assert on secret values — only that a rule fired, redacted
    assert all(f.get("Secret") in (None, "", "REDACTED") for f in findings)
    assert any("private-key" in f.get("RuleID", "") for f in findings)


@requires_gitleaks
def test_repo_config_allowlists_intentional_fixtures():
    # With the committed config, the intentional dummy fixture is allowlisted,
    # so a repo-wide scan is not blocked by it.
    assert _scan(DUMMY, use_config=True) == []


@requires_gitleaks
def test_repo_tree_scan_is_clean_with_committed_config():
    # The whole tracked working tree must scan clean under the committed config.
    with tempfile.TemporaryDirectory() as tmp:
        report = os.path.join(tmp, "report.json")
        subprocess.run(
            [GITLEAKS, "dir", ".", "--config", CONFIG, "--redact", "--no-banner",
             "--report-format", "json", "--report-path", report],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        with open(report) as fh:
            findings = json.load(fh)
    assert findings == [], f"unexpected secret findings in tree: " \
        f"{[(f.get('RuleID'), f.get('File')) for f in findings]}"
