"""Unit tests for worktree-specific Dev Container metadata."""

import os
import subprocess
from pathlib import Path

import pytest

from scripts.devcontainer_support import (
    compose_command,
    prepare_local_files,
    resolve_context,
    sanitize_slug,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.fixture
def linked_worktree(tmp_path: Path) -> tuple[Path, Path]:
    primary = tmp_path / "Astro App"
    primary.mkdir()
    _git(primary, "init")
    _git(primary, "config", "user.name", "Devcontainer Test")
    _git(primary, "config", "user.email", "devcontainer@example.test")
    (primary / "README.md").write_text("fixture\n")
    _git(primary, "add", "README.md")
    _git(primary, "commit", "-m", "fixture")

    worktree = primary / ".worktrees" / "Agent One"
    worktree.parent.mkdir()
    _git(primary, "worktree", "add", "-b", "agent-one", str(worktree))
    return primary, worktree


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Agent One", "agent-one"),
        ("feature/API_v2", "feature-api-v2"),
        ("---Mixed---Case---", "mixed-case"),
        ("x" * 80, "x" * 32),
    ],
)
def test_sanitize_slug(value: str, expected: str) -> None:
    assert sanitize_slug(value) == expected


def test_sanitize_slug_rejects_empty_value() -> None:
    with pytest.raises(ValueError, match="at least one letter or digit"):
        sanitize_slug("***")


def test_resolve_context_detects_linked_worktree(
    linked_worktree: tuple[Path, Path],
) -> None:
    primary, worktree = linked_worktree

    context = resolve_context(worktree)

    assert context.worktree == worktree.resolve()
    assert context.git_common_dir == (primary / ".git").resolve()
    assert context.project_name == "astro-astro-app-agent-one"
    assert context.linked_worktree is True


def test_prepare_writes_gitignored_compose_metadata(
    linked_worktree: tuple[Path, Path],
) -> None:
    primary, worktree = linked_worktree

    context = prepare_local_files(worktree)

    env_text = (worktree / ".devcontainer" / ".env").read_text()
    override = (worktree / ".devcontainer" / "compose.local.yaml").read_text()
    assert f"COMPOSE_PROJECT_NAME={context.project_name}\n" in env_text
    assert f"LOCAL_UID={os.getuid()}\n" in env_text
    assert f"LOCAL_GID={os.getgid()}\n" in env_text
    assert f'source: "{(primary / ".git").resolve()}"' in override
    assert f'target: "{(primary / ".git").resolve()}"' in override

    # The worktree's own `.git` file records an absolute host path back to
    # this checkout; git also resolves that path from the *other* direction
    # via the common dir's `worktrees/<name>/gitdir` pointer. Mounting the
    # worktree at that same absolute path (in addition to /workspace) keeps
    # both pointers valid inside the container, so `git worktree
    # prune`/`list` never see a dangling worktree and delete its metadata.
    resolved_worktree = worktree.resolve()
    assert f'source: "{resolved_worktree}"' in override
    assert f'target: "{resolved_worktree}"' in override
    assert override.count("type: bind") == 2


def test_primary_checkout_gets_empty_local_override(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / ".devcontainer").mkdir()

    context = prepare_local_files(repo)

    assert context.linked_worktree is False
    assert (repo / ".devcontainer" / "compose.local.yaml").read_text() == "services: {}\n"


def test_compose_command_uses_both_files_and_explicit_project(
    linked_worktree: tuple[Path, Path],
) -> None:
    _, worktree = linked_worktree
    context = prepare_local_files(worktree)

    command = compose_command(context, "up", "-d", "app")

    assert command[:2] == ["docker", "compose"]
    assert command[-3:] == ["up", "-d", "app"]
    assert ["-p", context.project_name] == command[command.index("-p") : command.index("-p") + 2]
    assert str(worktree / ".devcontainer" / "compose.yaml") in command
    assert str(worktree / ".devcontainer" / "compose.local.yaml") in command
