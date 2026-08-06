"""Tests for safe agent-worktree creation and Compose startup."""

import os
import subprocess
from pathlib import Path

import pytest

import scripts.devcontainer_worktree as helper
from scripts.devcontainer_support import git_subprocess_env

REPO_ROOT = Path(__file__).resolve().parents[1]
SHELL_HELPER = REPO_ROOT / "scripts" / "devcontainer-worktree.sh"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=git_subprocess_env(),
    )
    return result.stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    repo = tmp_path / "astro-ai-agent"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Helper Test")
    _git(repo, "config", "user.email", "helper@example.test")
    (repo / "README.md").write_text("fixture\n")
    (repo / ".devcontainer").mkdir()
    (repo / ".devcontainer" / "compose.yaml").write_text("services: {}\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture")
    return repo


def test_create_without_start_makes_branch_and_metadata(repository: Path) -> None:
    context = helper.create_agent_worktree(
        "Timing API",
        base="HEAD",
        repo_root=repository,
        start=False,
    )

    assert context.worktree == (repository / ".worktrees" / "timing-api").resolve()
    assert _git(context.worktree, "branch", "--show-current") == "agent/timing-api"
    assert (context.worktree / ".devcontainer" / ".env").exists()
    assert (context.worktree / ".devcontainer" / "compose.local.yaml").exists()


def test_existing_branch_is_rejected_before_path_creation(repository: Path) -> None:
    _git(repository, "branch", "agent/collision")

    with pytest.raises(helper.HelperError, match="branch already exists"):
        helper.create_agent_worktree(
            "collision",
            base="HEAD",
            repo_root=repository,
            start=False,
        )

    assert not (repository / ".worktrees" / "collision").exists()


def test_existing_path_is_rejected(repository: Path) -> None:
    path = repository / ".worktrees" / "collision"
    path.mkdir(parents=True)

    with pytest.raises(helper.HelperError, match="path already exists"):
        helper.create_agent_worktree(
            "collision",
            base="HEAD",
            repo_root=repository,
            start=False,
        )


def test_helper_must_run_from_primary_checkout(repository: Path) -> None:
    existing = helper.create_agent_worktree(
        "existing",
        base="HEAD",
        repo_root=repository,
        start=False,
    )

    with pytest.raises(helper.HelperError, match="primary checkout"):
        helper.create_agent_worktree(
            "nested",
            base="HEAD",
            repo_root=existing.worktree,
            start=False,
        )


def test_missing_prerequisite_has_actionable_error(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(helper.shutil, "which", lambda name: None if name == "docker" else f"/usr/bin/{name}")

    with pytest.raises(helper.HelperError, match="required command not found: docker"):
        helper.check_prerequisites()


def test_shell_entrypoint_is_executable_and_uses_module_mode() -> None:
    assert SHELL_HELPER.exists()
    assert os.access(SHELL_HELPER, os.X_OK)
    assert "-m scripts.devcontainer_worktree" in SHELL_HELPER.read_text()


def test_start_builds_container_and_installs_editable_package(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(helper, "check_prerequisites", lambda: None)
    compose_commands: list[list[str]] = []

    def record_commands(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "compose"]:
            compose_commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.run(command, check=True, text=True, **kwargs)

    monkeypatch.setattr(helper, "_run", record_commands)

    helper.create_agent_worktree(
        "started",
        base="HEAD",
        repo_root=repository,
        start=True,
    )

    assert any(command[-4:] == ["up", "-d", "--build", "app"] for command in compose_commands)
    assert any(command[-7:] == ["python", "-m", "pip", "install", "--user", "-e", "."] for command in compose_commands)


def test_existing_compose_resources_reject_start_without_rewrapping(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(helper, "check_prerequisites", lambda: None)
    compose_commands: list[list[str]] = []

    def record_commands(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "compose"]:
            compose_commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="container-id\n", stderr="")
        return subprocess.run(command, check=True, text=True, **kwargs)

    monkeypatch.setattr(helper, "_run", record_commands)

    with pytest.raises(
        helper.HelperError,
        match=r"^Compose project already has resources: astro-astro-ai-agent-collision$",
    ):
        helper.create_agent_worktree(
            "collision",
            base="HEAD",
            repo_root=repository,
            start=True,
        )

    assert not any(command[-4:] == ["up", "-d", "--build", "app"] for command in compose_commands)
    assert (repository / ".worktrees" / "collision").is_dir()
    assert _git(repository, "show-ref", "--verify", "refs/heads/agent/collision")


def test_streamlit_url_uses_docker_selected_port(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = helper.create_agent_worktree(
        "port-test",
        base="HEAD",
        repo_root=repository,
        start=False,
    )
    monkeypatch.setattr(
        helper,
        "_run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout="0.0.0.0:49152\n",
            stderr="",
        ),
    )

    assert helper.discover_streamlit_url(context) == "http://localhost:49152"


def test_compose_failure_retains_created_worktree(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(helper, "check_prerequisites", lambda: None)

    def fail_compose(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "compose"]:
            raise subprocess.CalledProcessError(1, command, stderr="build failed")
        return subprocess.run(command, **kwargs)

    monkeypatch.setattr(helper, "_run", fail_compose)

    with pytest.raises(helper.HelperError, match="worktree retained"):
        helper.create_agent_worktree(
            "retained",
            base="HEAD",
            repo_root=repository,
            start=True,
        )

    assert (repository / ".worktrees" / "retained").is_dir()
    assert _git(repository, "show-ref", "--verify", "refs/heads/agent/retained")
