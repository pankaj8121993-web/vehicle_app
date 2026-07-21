"""
SEC-004 Operator Pack — smoke test for the rehearsal harness.

Runs scripts/rehearse_sec004.sh end to end against a disposable synthetic
database and asserts it passes and cleans up. This keeps the harness (and,
transitively, the rotation tool's real behaviour) covered by CI. It never
touches production or test_database — the harness generates its own throwaway
database and drops it.

Skips cleanly if the local MongoDB used by the rest of the suite is not
reachable, so it never becomes a flaky failure in a Mongo-less environment.
"""
import os
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "rehearse_sec004.sh"


def _mongo_reachable():
    try:
        from pymongo import MongoClient
        MongoClient("mongodb://localhost:27017",
                    serverSelectionTimeoutMS=1500).admin.command("ping")
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _SCRIPT.exists(), reason="rehearsal script not present")
@pytest.mark.skipif(not _mongo_reachable(), reason="local MongoDB not reachable")
def test_rehearsal_harness_passes_and_cleans_up():
    env = dict(os.environ)
    env["REHEARSAL_ASSUME_YES"] = "1"
    env["MONGO_URL"] = "mongodb://localhost:27017"
    proc = subprocess.run(
        ["bash", str(_SCRIPT)],
        env=env, capture_output=True, text=True, timeout=180,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"harness failed:\n{out[-2000:]}"
    assert "REHEARSAL PASSED" in out
    assert "Dropped rehearsal database" in out
    # The connection string must never be echoed by the harness.
    assert "mongodb://" not in proc.stdout


@pytest.mark.skipif(not _SCRIPT.exists(), reason="rehearsal script not present")
def test_rehearsal_refuses_a_connection_string_argument():
    """No connection string may be passed as an argument."""
    proc = subprocess.run(
        ["bash", str(_SCRIPT), "mongodb://localhost:27017"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode != 0
    assert "takes no arguments" in (proc.stdout + proc.stderr)


@pytest.mark.skipif(not _SCRIPT.exists(), reason="rehearsal script not present")
def test_rehearsal_refuses_credentialled_uri():
    """A production-like URI carrying credentials is refused before any work."""
    env = dict(os.environ)
    env["REHEARSAL_ASSUME_YES"] = "1"
    env["MONGO_URL"] = "mongodb://user:pass@db.example.internal:27017"
    proc = subprocess.run(
        ["bash", str(_SCRIPT)],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode != 0
    assert "credentials" in (proc.stdout + proc.stderr).lower()


@pytest.mark.skipif(not _SCRIPT.exists(), reason="rehearsal script not present")
def test_rehearsal_refuses_test_database_uri():
    """The dev database must never be a target."""
    env = dict(os.environ)
    env["REHEARSAL_ASSUME_YES"] = "1"
    env["MONGO_URL"] = "mongodb://localhost:27017/test_database"
    proc = subprocess.run(
        ["bash", str(_SCRIPT)],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode != 0
    assert "test_database" in (proc.stdout + proc.stderr)
