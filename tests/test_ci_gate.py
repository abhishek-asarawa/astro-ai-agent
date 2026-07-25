"""Contract tests for the shared quality-gate script used by hooks and CI."""

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_ci_checks.sh"


def _run(args, extra_env=None):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )


def test_script_exists_and_is_executable():
    assert SCRIPT.exists(), f"missing {SCRIPT}"
    assert os.access(SCRIPT, os.X_OK), f"{SCRIPT} is not executable"


def test_unknown_mode_is_rejected():
    result = _run(["bogus-mode"])
    assert result.returncode != 0
    assert "Unknown mode" in result.stderr


def test_full_mode_refuses_old_interpreter(tmp_path):
    """A stub interpreter that fails the version probe must block full mode."""
    stub = tmp_path / "python-too-old"
    stub.write_text("#!/usr/bin/env bash\nexit 1\n")
    stub.chmod(0o755)

    result = _run(["full"], extra_env={"PYTHON": str(stub)})
    assert result.returncode != 0
    assert "Python >= 3.11 required" in result.stderr


def test_fast_mode_passes_on_clean_tree():
    """The repo must stay lint-clean so the pre-commit hook is usable."""
    result = _run(["fast"])
    assert result.returncode == 0, result.stdout + result.stderr
