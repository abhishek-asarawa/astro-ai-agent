"""Contract and behavior tests for the spec-driven development gate."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_spec_gate.sh"
HOOKS_DIR = REPO_ROOT / ".githooks"


def test_script_exists_and_is_executable():
    assert SCRIPT.exists(), f"missing {SCRIPT}"
    assert os.access(SCRIPT, os.X_OK), f"{SCRIPT} is not executable"


def test_unknown_mode_is_rejected():
    result = subprocess.run([str(SCRIPT), "bogus-mode"], capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode != 0
    assert "Unknown mode" in result.stderr


def test_commit_msg_mode_requires_msg_file_arg():
    result = subprocess.run([str(SCRIPT), "commit-msg"], capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode != 0


def test_hooks_exist_and_are_executable():
    for name in ("pre-commit", "commit-msg", "pre-push"):
        hook = HOOKS_DIR / name
        assert hook.exists(), f"missing hook {hook}"
        assert os.access(hook, os.X_OK), f"{hook} is not executable"


def test_commit_msg_hook_calls_spec_gate():
    body = (HOOKS_DIR / "commit-msg").read_text()
    assert "check_spec_gate.sh" in body
    assert "commit-msg" in body


def test_pre_push_hook_calls_spec_gate_and_full_checks():
    body = (HOOKS_DIR / "pre-push").read_text()
    assert "check_spec_gate.sh" in body
    assert "range" in body
    assert "run_ci_checks.sh" in body
    assert "full" in body


def test_install_hooks_script_chmods_spec_gate_files():
    installer = REPO_ROOT / "scripts" / "install-hooks.sh"
    body = installer.read_text()
    assert "commit-msg" in body
    assert "check_spec_gate.sh" in body


def test_ci_workflow_has_spec_gate_job():
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "check_spec_gate.sh" in workflow
    assert "spec-gate" in workflow


# --- Functional tests against a throwaway git repo -------------------------


def _git(repo: Path, *args):
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def _run_gate(repo: Path, *args, expect_success=None):
    script = repo / "scripts" / "check_spec_gate.sh"
    result = subprocess.run([str(script), *args], cwd=repo, capture_output=True, text=True)
    if expect_success is not None:
        assert (result.returncode == 0) is expect_success, (
            f"exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    return result


@pytest.fixture
def gate_repo(tmp_path):
    """A throwaway git repo with the gate script and feature-surface dirs."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "astro_agent" / "routing").mkdir(parents=True)
    (repo / "docs" / "specs").mkdir(parents=True)
    shutil.copy2(SCRIPT, repo / "scripts" / "check_spec_gate.sh")
    os.chmod(repo / "scripts" / "check_spec_gate.sh", 0o755)

    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "test")
    (repo / "README.md").write_text("init\n")
    (repo / "docs" / "specs" / "career-guidance.md").write_text("spec\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


def _write_msg(repo: Path, text: str) -> Path:
    msg_file = repo / "COMMIT_MSG"
    msg_file.write_text(text)
    return msg_file


def test_non_feature_file_passes(gate_repo):
    (gate_repo / "README.md").write_text("changed\n")
    _git(gate_repo, "add", "README.md")
    msg = _write_msg(gate_repo, "docs: tweak readme\n")
    _run_gate(gate_repo, "commit-msg", str(msg), expect_success=True)


def test_feature_file_without_spec_fails_with_helpful_message(gate_repo):
    (gate_repo / "astro_agent" / "routing" / "intent_router.py").write_text("x = 1\n")
    _git(gate_repo, "add", "astro_agent/routing/intent_router.py")
    msg = _write_msg(gate_repo, "feat: change routing\n")
    result = _run_gate(gate_repo, "commit-msg", str(msg), expect_success=False)
    assert "astro_agent/routing/intent_router.py" in result.stderr
    assert "Spec:" in result.stderr
    assert "Spec-Exempt:" in result.stderr
    assert "docs/specs/career-guidance.md" in result.stderr


def test_feature_file_with_exempt_trailer_passes(gate_repo):
    (gate_repo / "astro_agent" / "routing" / "intent_router.py").write_text("x = 1\n")
    _git(gate_repo, "add", "astro_agent/routing/intent_router.py")
    msg = _write_msg(gate_repo, "feat: change routing\n\nSpec-Exempt: internal rename only\n")
    _run_gate(gate_repo, "commit-msg", str(msg), expect_success=True)


def test_feature_file_with_valid_spec_trailer_passes(gate_repo):
    (gate_repo / "astro_agent" / "routing" / "intent_router.py").write_text("x = 1\n")
    _git(gate_repo, "add", "astro_agent/routing/intent_router.py")
    msg = _write_msg(
        gate_repo,
        "feat: change routing\n\nSpec: docs/specs/career-guidance.md\n",
    )
    _run_gate(gate_repo, "commit-msg", str(msg), expect_success=True)


def test_feature_file_with_nonexistent_spec_trailer_fails(gate_repo):
    (gate_repo / "astro_agent" / "routing" / "intent_router.py").write_text("x = 1\n")
    _git(gate_repo, "add", "astro_agent/routing/intent_router.py")
    msg = _write_msg(
        gate_repo,
        "feat: change routing\n\nSpec: docs/specs/does-not-exist.md\n",
    )
    _run_gate(gate_repo, "commit-msg", str(msg), expect_success=False)


def test_feature_file_with_spec_dir_touched_passes(gate_repo):
    (gate_repo / "astro_agent" / "routing" / "intent_router.py").write_text("x = 1\n")
    (gate_repo / "docs" / "specs" / "career-guidance.md").write_text("spec v2\n")
    _git(
        gate_repo,
        "add",
        "astro_agent/routing/intent_router.py",
        "docs/specs/career-guidance.md",
    )
    msg = _write_msg(gate_repo, "feat: change routing\n")
    _run_gate(gate_repo, "commit-msg", str(msg), expect_success=True)


def test_range_mode_fails_when_no_commit_in_range_engages_spec(gate_repo):
    base = _git(gate_repo, "rev-parse", "HEAD").strip()
    (gate_repo / "astro_agent" / "routing" / "intent_router.py").write_text("x = 1\n")
    _git(gate_repo, "add", "astro_agent/routing/intent_router.py")
    _git(gate_repo, "commit", "-qm", "feat: routing change, no spec")
    _run_gate(gate_repo, "range", base, "HEAD", expect_success=False)


def test_range_mode_passes_when_any_commit_in_range_has_valid_spec_trailer(gate_repo):
    base = _git(gate_repo, "rev-parse", "HEAD").strip()
    (gate_repo / "astro_agent" / "routing" / "intent_router.py").write_text("x = 1\n")
    _git(gate_repo, "add", "astro_agent/routing/intent_router.py")
    _git(gate_repo, "commit", "-qm", "feat: routing change, no spec yet")

    (gate_repo / "README.md").write_text("more\n")
    _git(gate_repo, "add", "README.md")
    msg = _write_msg(gate_repo, "docs: unrelated\n\nSpec: docs/specs/career-guidance.md\n")
    _git(gate_repo, "commit", "-qF", str(msg))

    _run_gate(gate_repo, "range", base, "HEAD", expect_success=True)


def test_range_mode_passes_trivially_with_no_changes(gate_repo):
    head = _git(gate_repo, "rev-parse", "HEAD").strip()
    _run_gate(gate_repo, "range", head, "HEAD", expect_success=True)
