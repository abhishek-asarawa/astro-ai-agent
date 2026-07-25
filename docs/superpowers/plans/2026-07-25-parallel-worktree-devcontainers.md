# Parallel Worktree Dev Containers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every Git worktree an isolated Python 3.11 development container that can run the full CI gate and an optional Streamlit instance against shared host Ollama.

**Architecture:** Docker Compose owns one idle `app` service, and the Dev Container attaches to that same service. A tested Python support module generates worktree-local Compose metadata and a thin shell helper creates linked worktrees, starts uniquely named Compose projects, and reports commands and dynamic ports.

**Tech Stack:** Python 3.11, pytest, Bash, Git worktrees, Docker Compose, Dev Container specification, Streamlit, host Ollama.

**Design spec:** [docs/superpowers/specs/2026-07-25-parallel-worktree-devcontainers-design.md](../specs/2026-07-25-parallel-worktree-devcontainers-design.md)

## Global Constraints

- Use Python 3.11 in the container; `./scripts/run_ci_checks.sh full` remains the CI-equivalent gate.
- Use one Compose `app` service as the environment source of truth; Dev Container configuration must attach to it rather than duplicate it.
- Keep the app service idle by default; never start Streamlit or Ollama automatically.
- Set `ASTRO_OLLAMA_HOST=http://host.docker.internal:11434`.
- Map `host.docker.internal` through `host-gateway` for Linux while retaining Docker Desktop for macOS compatibility.
- Publish container port `8501` through a Docker-selected host port, never a fixed host port.
- Managed worktrees live under `.worktrees/<slug>` and generated `.devcontainer/.env` and `.devcontainer/compose.local.yaml` files remain untracked.
- Compose project names contain only lowercase ASCII letters, digits, and hyphens, start with an alphanumeric character, and are at most 63 characters.
- Do not copy a primary checkout's `.env`, Chroma database, logs, corpus, or secrets into a new worktree.
- Do not run a private Ollama container, configure GPU passthrough, download models, or add remote-Docker support.
- Helper failures after `git worktree add` retain the worktree and print recovery commands; no failure path deletes a branch or worktree implicitly.
- Keep shell entrypoints executable (`100755`).
- Stage only files named by each task because unrelated untracked `.cursor/` files are present; never use `git add -A`.

---

### Task 1: Worktree-local Compose context generator

**Files:**
- Create: `scripts/devcontainer_support.py`
- Create: `tests/test_devcontainer_support.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: Git's `--show-toplevel` and `--git-common-dir` output for an existing checkout or linked worktree.
- Produces:
  - `DevcontainerContext(worktree: Path, git_common_dir: Path, project_name: str, linked_worktree: bool)`.
  - `sanitize_slug(value: str) -> str`.
  - `resolve_context(worktree: Path) -> DevcontainerContext`.
  - `prepare_local_files(worktree: Path) -> DevcontainerContext`.
  - `compose_command(context: DevcontainerContext, *args: str) -> list[str]`.
  - CLI commands `python3 scripts/devcontainer_support.py slug <value>` and `python3 scripts/devcontainer_support.py prepare --worktree <path>`.

- [ ] **Step 1: Write failing unit tests**

Create `tests/test_devcontainer_support.py`:

```python
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
```

- [ ] **Step 2: Run the tests and confirm the missing module failure**

Run:

```bash
source .venv311/bin/activate
ASTRO_CI=1 python -m pytest tests/test_devcontainer_support.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'scripts.devcontainer_support'`.

- [ ] **Step 3: Implement the context generator**

Create `scripts/devcontainer_support.py`:

```python
#!/usr/bin/env python3
"""Generate deterministic, worktree-local Docker Compose metadata.

Linked worktrees store a `.git` pointer to the primary checkout. This module
resolves that pointer on the host and emits a local Compose override that mounts
the Git common directory at the same absolute path inside the container.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_SLUG_LENGTH = 32
MAX_PROJECT_LENGTH = 63


@dataclass(frozen=True)
class DevcontainerContext:
    """Resolved host paths and stable Compose identity for one worktree."""

    worktree: Path
    git_common_dir: Path
    project_name: str
    linked_worktree: bool


def _git(worktree: Path, *args: str) -> str:
    """Run a read-only Git query rooted at `worktree`."""
    result = subprocess.run(
        ["git", "-C", str(worktree), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def sanitize_slug(value: str) -> str:
    """Convert user or path text to a bounded Compose-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    slug = slug[:MAX_SLUG_LENGTH].rstrip("-")
    if not slug:
        raise ValueError("name must contain at least one letter or digit")
    return slug


def resolve_context(worktree: Path) -> DevcontainerContext:
    """Resolve Git metadata and Compose identity for an existing worktree."""
    root = Path(_git(worktree, "rev-parse", "--show-toplevel")).resolve()
    common_raw = Path(_git(root, "rev-parse", "--git-common-dir"))
    common_dir = common_raw.resolve() if common_raw.is_absolute() else (root / common_raw).resolve()
    repository_slug = sanitize_slug(common_dir.parent.name)
    worktree_slug = sanitize_slug(root.name)
    project_name = f"astro-{repository_slug}-{worktree_slug}"[:MAX_PROJECT_LENGTH].rstrip("-")
    return DevcontainerContext(
        worktree=root,
        git_common_dir=common_dir,
        project_name=project_name,
        linked_worktree=(root / ".git").is_file(),
    )


def _render_override(context: DevcontainerContext) -> str:
    """Render only the host-specific Git metadata mount."""
    if not context.linked_worktree:
        return "services: {}\n"
    path = json.dumps(str(context.git_common_dir))
    return (
        "services:\n"
        "  app:\n"
        "    volumes:\n"
        "      - type: bind\n"
        f"        source: {path}\n"
        f"        target: {path}\n"
    )


def prepare_local_files(worktree: Path) -> DevcontainerContext:
    """Write idempotent local Compose metadata for one checkout."""
    context = resolve_context(worktree)
    devcontainer_dir = context.worktree / ".devcontainer"
    devcontainer_dir.mkdir(exist_ok=True)
    (devcontainer_dir / ".env").write_text(
        f"COMPOSE_PROJECT_NAME={context.project_name}\n"
        f"LOCAL_UID={os.getuid()}\n"
        f"LOCAL_GID={os.getgid()}\n"
    )
    (devcontainer_dir / "compose.local.yaml").write_text(_render_override(context))
    return context


def compose_command(context: DevcontainerContext, *args: str) -> list[str]:
    """Build a Compose command scoped to the context's explicit project."""
    directory = context.worktree / ".devcontainer"
    return [
        "docker",
        "compose",
        "--project-directory",
        str(directory),
        "-f",
        str(directory / "compose.yaml"),
        "-f",
        str(directory / "compose.local.yaml"),
        "-p",
        context.project_name,
        *args,
    ]


def main() -> int:
    """Run the host-side metadata CLI."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    slug_parser = subparsers.add_parser("slug")
    slug_parser.add_argument("value")
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--worktree", type=Path, default=Path.cwd())
    args = parser.parse_args()

    if args.command == "slug":
        print(sanitize_slug(args.value))
        return 0

    context = prepare_local_files(args.worktree)
    print(context.project_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Ignore managed worktrees and generated metadata**

Append a focused section to `.gitignore`:

```gitignore
# --- Worktree Dev Containers (host-specific, generated) ---
.worktrees/
.devcontainer/.env
.devcontainer/compose.local.yaml
```

- [ ] **Step 5: Run focused tests and formatting**

Run:

```bash
source .venv311/bin/activate
python -m ruff format scripts/devcontainer_support.py tests/test_devcontainer_support.py
ASTRO_CI=1 python -m pytest tests/test_devcontainer_support.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit the context generator**

```bash
git add .gitignore scripts/devcontainer_support.py tests/test_devcontainer_support.py
git commit -m "feat(devcontainer): generate worktree compose context"
```

---

### Task 2: Safe helper for creating and starting agent worktrees

**Files:**
- Create: `scripts/devcontainer_worktree.py`
- Create: `scripts/devcontainer-worktree.sh`
- Create: `tests/test_devcontainer_worktree.py`

**Interfaces:**
- Consumes: `prepare_local_files()` and `compose_command()` from Task 1; Git and Docker Compose executables on the host.
- Produces:
  - `create_agent_worktree(task_name: str, base: str, repo_root: Path, start: bool = True) -> DevcontainerContext`.
  - `discover_streamlit_url(context: DevcontainerContext) -> str`.
  - Host command `./scripts/devcontainer-worktree.sh <task-name> [--base REF] [--no-start]`.
  - Branch `agent/<slug>`, path `.worktrees/<slug>`, and Compose project from Task 1.

- [ ] **Step 1: Write failing helper tests**

Create `tests/test_devcontainer_worktree.py`:

```python
"""Tests for safe agent-worktree creation and Compose startup."""

import os
import subprocess
from pathlib import Path

import pytest

import scripts.devcontainer_worktree as helper

REPO_ROOT = Path(__file__).resolve().parents[1]
SHELL_HELPER = REPO_ROOT / "scripts" / "devcontainer-worktree.sh"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
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
    assert any(
        command[-7:] == ["python", "-m", "pip", "install", "--user", "-e", "."]
        for command in compose_commands
    )


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
```

- [ ] **Step 2: Run tests and confirm the missing module failure**

Run:

```bash
source .venv311/bin/activate
ASTRO_CI=1 python -m pytest tests/test_devcontainer_worktree.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'scripts.devcontainer_worktree'`.

- [ ] **Step 3: Implement the Python helper**

Create `scripts/devcontainer_worktree.py`:

```python
#!/usr/bin/env python3
"""Create a linked worktree and optionally start its isolated Compose project."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from scripts.devcontainer_support import (
    DevcontainerContext,
    compose_command,
    prepare_local_files,
    sanitize_slug,
)


class HelperError(RuntimeError):
    """An expected setup failure with an actionable user-facing message."""


def _run(
    command: list[str],
    **kwargs: object,
) -> subprocess.CompletedProcess[str]:
    """Run a helper subprocess; isolated for deterministic unit tests."""
    return subprocess.run(command, check=True, text=True, **kwargs)


def check_prerequisites() -> None:
    """Verify required host commands and a responsive Docker daemon."""
    for command in ("git", "docker"):
        if shutil.which(command) is None:
            raise HelperError(f"required command not found: {command}")
    try:
        _run(["docker", "compose", "version"], capture_output=True)
        _run(["docker", "info"], capture_output=True)
    except subprocess.CalledProcessError as exc:
        raise HelperError("Docker Compose or the Docker daemon is unavailable") from exc


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run Git in the primary checkout."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def create_agent_worktree(
    task_name: str,
    *,
    base: str,
    repo_root: Path,
    start: bool = True,
) -> DevcontainerContext:
    """Create one collision-safe worktree and optionally start Compose."""
    root = Path(_git(repo_root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if not (root / ".git").is_dir():
        raise HelperError("run this helper from the primary checkout, not a linked worktree")
    slug = sanitize_slug(task_name)
    branch = f"agent/{slug}"
    worktree = root / ".worktrees" / slug

    branch_check = _git(root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False)
    if branch_check.returncode == 0:
        raise HelperError(f"branch already exists: {branch}")
    if worktree.exists():
        raise HelperError(f"worktree path already exists: {worktree}")

    if start:
        check_prerequisites()
    worktree.parent.mkdir(exist_ok=True)
    try:
        _run(["git", "-C", str(root), "worktree", "add", "-b", branch, str(worktree), base])
    except subprocess.CalledProcessError as exc:
        raise HelperError(f"git worktree add failed for {worktree}") from exc

    context = prepare_local_files(worktree)
    if not start:
        return context

    try:
        existing = _run(
            compose_command(context, "ps", "-q"),
            capture_output=True,
        )
        if existing.stdout.strip():
            raise HelperError(f"Compose project already has resources: {context.project_name}")
        _run(compose_command(context, "up", "-d", "--build", "app"))
        _run(
            compose_command(
                context,
                "exec",
                "-T",
                "app",
                "python",
                "-m",
                "pip",
                "install",
                "--user",
                "-e",
                ".",
            )
        )
    except (subprocess.CalledProcessError, HelperError) as exc:
        recovery = " ".join(compose_command(context, "down"))
        raise HelperError(
            f"container setup failed; worktree retained at {worktree}\n"
            f"Inspect it there, or remove only container resources with:\n  {recovery}"
        ) from exc
    return context


def discover_streamlit_url(context: DevcontainerContext) -> str:
    """Resolve Docker's dynamic host port to a browser URL."""
    try:
        result = _run(
            compose_command(context, "port", "app", "8501"),
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise HelperError("failed to discover the Streamlit host port") from exc
    endpoint = result.stdout.strip()
    port = endpoint.rsplit(":", 1)[-1]
    if not port.isdigit():
        raise HelperError(f"failed to parse the Streamlit host port from: {endpoint!r}")
    return f"http://localhost:{port}"


def _print_handoff(context: DevcontainerContext, started: bool) -> None:
    """Print commands that remain scoped to the new worktree project."""
    print(f"Worktree: {context.worktree}")
    print(f"Compose project: {context.project_name}")
    print(f"Open in Cursor: cursor {context.worktree}")
    if not started:
        print("Container startup skipped (--no-start).")
        return
    print(f"Streamlit URL (after starting the app): {discover_streamlit_url(context)}")
    print("Run CI:")
    print("  " + " ".join(compose_command(context, "exec", "-T", "app", "./scripts/run_ci_checks.sh", "full")))
    print("Start Streamlit:")
    print(
        "  "
        + " ".join(
            compose_command(
                context,
                "exec",
                "app",
                "streamlit",
                "run",
                "app.py",
                "--server.address",
                "0.0.0.0",
            )
        )
    )
    print("Discover URL:")
    print("  " + " ".join(compose_command(context, "port", "app", "8501")))
    print("Stop this container project:")
    print("  " + " ".join(compose_command(context, "down")))


def main() -> int:
    """Parse the host helper CLI."""
    parser = argparse.ArgumentParser()
    parser.add_argument("task_name")
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--no-start", action="store_true")
    args = parser.parse_args()
    try:
        repo_root = Path(
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        context = create_agent_worktree(
            args.task_name,
            base=args.base,
            repo_root=repo_root,
            start=not args.no_start,
        )
        _print_handoff(context, started=not args.no_start)
    except (HelperError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"devcontainer-worktree: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add the executable shell entrypoint**

Create `scripts/devcontainer-worktree.sh`:

```bash
#!/usr/bin/env bash
# Stable shell entrypoint for the tested Python worktree helper.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
exec python3 -m scripts.devcontainer_worktree "$@"
```

Then make both entrypoints executable:

```bash
chmod +x scripts/devcontainer-worktree.sh scripts/devcontainer_worktree.py scripts/devcontainer_support.py
```

- [ ] **Step 5: Run helper tests and lint**

Run:

```bash
source .venv311/bin/activate
python -m ruff format scripts/devcontainer_worktree.py tests/test_devcontainer_worktree.py
python -m ruff check scripts/devcontainer_support.py scripts/devcontainer_worktree.py tests/test_devcontainer_support.py tests/test_devcontainer_worktree.py
ASTRO_CI=1 python -m pytest tests/test_devcontainer_support.py tests/test_devcontainer_worktree.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit the helper**

```bash
git add scripts/devcontainer-worktree.sh scripts/devcontainer_worktree.py scripts/devcontainer_support.py tests/test_devcontainer_worktree.py
git commit -m "feat(devcontainer): create isolated agent worktrees"
```

---

### Task 3: Shared Compose and Dev Container environment

**Files:**
- Create: `.devcontainer/Dockerfile`
- Create: `.devcontainer/compose.yaml`
- Create: `.devcontainer/devcontainer.json`
- Create: `tests/test_devcontainer_config.py`

**Interfaces:**
- Consumes: `.devcontainer/.env` and `.devcontainer/compose.local.yaml` generated by Task 1.
- Produces:
  - Compose service `app` at workspace `/workspace`.
  - Container port `8501` published through an automatically selected host port.
  - Dev Container named `Astro AI Agent`, attached to Compose service `app`.
  - Host initialization command `python3 scripts/devcontainer_support.py prepare --worktree .`.

- [ ] **Step 1: Write failing configuration contract tests**

Create `tests/test_devcontainer_config.py`:

```python
"""Static contracts for the shared Compose and Dev Container environment."""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEVCONTAINER = REPO_ROOT / ".devcontainer"


def test_dockerfile_uses_python_311_and_cached_dependency_layer() -> None:
    text = (DEVCONTAINER / "Dockerfile").read_text()
    assert "python:1-3.11-bookworm" in text
    assert "COPY requirements.txt requirements-dev.txt pyproject.toml" in text
    assert "pip install --no-cache-dir -r requirements-dev.txt" in text
    assert text.index("COPY requirements.txt") < text.index("pip install --no-cache-dir")
    assert "USER vscode" in text


def test_compose_service_is_idle_and_uses_shared_ollama() -> None:
    text = (DEVCONTAINER / "compose.yaml").read_text()
    assert "app:" in text
    assert "target: /workspace" in text
    assert "sleep infinity" in text
    assert "ASTRO_OLLAMA_HOST: http://host.docker.internal:11434" in text
    assert "host.docker.internal:host-gateway" in text
    assert 'target: 8501' in text
    assert 'published: "0"' in text
    assert "streamlit run" not in text


def test_devcontainer_attaches_to_compose_app_service() -> None:
    config = json.loads((DEVCONTAINER / "devcontainer.json").read_text())
    assert config["service"] == "app"
    assert config["workspaceFolder"] == "/workspace"
    assert config["dockerComposeFile"] == ["compose.yaml", "compose.local.yaml"]
    assert config["initializeCommand"] == "python3 scripts/devcontainer_support.py prepare --worktree ."
    assert config["postCreateCommand"] == "python -m pip install --user -e ."
    assert config["remoteUser"] == "vscode"
    assert config["shutdownAction"] == "stopCompose"
```

- [ ] **Step 2: Run tests and verify missing configuration files**

Run:

```bash
source .venv311/bin/activate
ASTRO_CI=1 python -m pytest tests/test_devcontainer_config.py -v
```

Expected: tests fail with `FileNotFoundError` for `.devcontainer/Dockerfile`, `compose.yaml`, and `devcontainer.json`.

- [ ] **Step 3: Create the cached Python 3.11 development image**

Create `.devcontainer/Dockerfile`:

```dockerfile
FROM mcr.microsoft.com/devcontainers/python:1-3.11-bookworm

USER root

# Build tools cover Python packages that do not provide a wheel for the host
# architecture; curl supports explicit Ollama health checks.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Keep expensive ML and Chroma dependencies cached until a manifest changes.
COPY requirements.txt requirements-dev.txt pyproject.toml /tmp/astro-deps/
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r /tmp/astro-deps/requirements-dev.txt

USER vscode
CMD ["sleep", "infinity"]
```

- [ ] **Step 4: Create the single Compose app service**

Create `.devcontainer/compose.yaml`:

```yaml
name: ${COMPOSE_PROJECT_NAME}

services:
  app:
    build:
      context: ..
      dockerfile: .devcontainer/Dockerfile
    working_dir: /workspace
    command: sleep infinity
    init: true
    volumes:
      - type: bind
        source: ..
        target: /workspace
    environment:
      ASTRO_OLLAMA_HOST: http://host.docker.internal:11434
      PYTHONUNBUFFERED: "1"
    extra_hosts:
      - host.docker.internal:host-gateway
    ports:
      - target: 8501
        published: "0"
        protocol: tcp
```

- [ ] **Step 5: Create the Dev Container attachment configuration**

Create `.devcontainer/devcontainer.json`:

```json
{
  "name": "Astro AI Agent",
  "dockerComposeFile": [
    "compose.yaml",
    "compose.local.yaml"
  ],
  "service": "app",
  "workspaceFolder": "/workspace",
  "initializeCommand": "python3 scripts/devcontainer_support.py prepare --worktree .",
  "postCreateCommand": "python -m pip install --user -e .",
  "remoteUser": "vscode",
  "updateRemoteUserUID": true,
  "shutdownAction": "stopCompose",
  "forwardPorts": [
    8501
  ],
  "portsAttributes": {
    "8501": {
      "label": "Astro Streamlit",
      "onAutoForward": "notify"
    }
  }
}
```

- [ ] **Step 6: Run static tests and validate rendered Compose**

Run:

```bash
source .venv311/bin/activate
python scripts/devcontainer_support.py prepare --worktree .
ASTRO_CI=1 python -m pytest tests/test_devcontainer_config.py tests/test_devcontainer_support.py -v
docker compose \
  --project-directory .devcontainer \
  -f .devcontainer/compose.yaml \
  -f .devcontainer/compose.local.yaml \
  config --quiet
git status --short
```

Expected:
- All tests pass.
- `docker compose config --quiet` exits zero.
- `.devcontainer/.env` and `.devcontainer/compose.local.yaml` do not appear in `git status`.

- [ ] **Step 7: Build and verify the base container**

Run:

```bash
PROJECT="$(python scripts/devcontainer_support.py prepare --worktree .)"
docker compose \
  --project-directory .devcontainer \
  -f .devcontainer/compose.yaml \
  -f .devcontainer/compose.local.yaml \
  -p "$PROJECT" up -d --build app
docker compose \
  --project-directory .devcontainer \
  -f .devcontainer/compose.yaml \
  -f .devcontainer/compose.local.yaml \
  -p "$PROJECT" exec -T app python --version
docker compose \
  --project-directory .devcontainer \
  -f .devcontainer/compose.yaml \
  -f .devcontainer/compose.local.yaml \
  -p "$PROJECT" exec -T app python -m pip install --user -e .
docker compose \
  --project-directory .devcontainer \
  -f .devcontainer/compose.yaml \
  -f .devcontainer/compose.local.yaml \
  -p "$PROJECT" exec -T app python -c "import astro_agent; print(astro_agent.__file__)"
```

Expected: Python reports `3.11.x`; editable installation succeeds; import prints `/workspace/astro_agent/__init__.py`.

- [ ] **Step 8: Commit the shared environment**

```bash
git add .devcontainer/Dockerfile .devcontainer/compose.yaml .devcontainer/devcontainer.json tests/test_devcontainer_config.py
git commit -m "feat(devcontainer): add shared compose environment"
```

---

### Task 4: Contributor workflow, parallel smoke test, and final verification

**Files:**
- Create: `docs/development/devcontainers.md`
- Modify: `README.md`
- Modify: `tests/test_devcontainer_config.py`

**Interfaces:**
- Consumes: helper and Compose environment from Tasks 1–3.
- Produces: documented helper, manual attach, CI, Streamlit, Ollama-health, port-discovery, cleanup, and two-worktree smoke-test workflows.

- [ ] **Step 1: Extend the contract test to require workflow documentation**

Append to `tests/test_devcontainer_config.py`:

```python
def test_documentation_covers_required_workflows() -> None:
    text = (REPO_ROOT / "docs" / "development" / "devcontainers.md").read_text()
    required_phrases = (
        "./scripts/devcontainer-worktree.sh",
        "Reopen in Container",
        "./scripts/run_ci_checks.sh full",
        "streamlit run app.py --server.address 0.0.0.0",
        "docker compose port app 8501",
        "http://host.docker.internal:11434/api/tags",
        "docker compose",
        "down",
        "does not remove the Git worktree or branch",
    )
    for phrase in required_phrases:
        assert phrase in text
```

- [ ] **Step 2: Run the test and verify documentation is missing**

Run:

```bash
source .venv311/bin/activate
ASTRO_CI=1 python -m pytest tests/test_devcontainer_config.py::test_documentation_covers_required_workflows -v
```

Expected: fails with `FileNotFoundError: docs/development/devcontainers.md`.

- [ ] **Step 3: Write the complete Dev Container guide**

Create `docs/development/devcontainers.md` with these exact sections and commands:

````markdown
# Parallel worktree Dev Containers

## Prerequisites

Install Git and Docker Desktop (or Docker Engine with Compose). Start host
Ollama and pull the models listed in the root README. Containers reach it at
`http://host.docker.internal:11434`.

Check the host service:

```bash
curl http://localhost:11434/api/tags
```

## Create an isolated agent worktree

From the primary checkout:

```bash
./scripts/devcontainer-worktree.sh timing-window
```

The helper creates branch `agent/timing-window`, worktree
`.worktrees/timing-window`, and a unique Compose project. Use `--base <ref>` to
change the starting revision or `--no-start` to create files without Docker.
It never copies `.env`, Chroma data, logs, or corpus files.

## Open manually

Open either the primary checkout or a linked worktree in Cursor or VS Code and
choose **Dev Containers: Reopen in Container**. The host initialization command
generates worktree-local, gitignored Compose metadata before attachment.

## Test and run

Inside the container, run the CI-equivalent gate:

```bash
./scripts/run_ci_checks.sh full
```

Check shared Ollama from inside the container:

```bash
curl http://host.docker.internal:11434/api/tags
```

CI does not require Ollama. If the health check fails, start Ollama on the host
and confirm Docker permits `host.docker.internal`.

Start the UI on demand:

```bash
streamlit run app.py --server.address 0.0.0.0
```

In a host terminal, use the helper's printed Compose command ending in:

```bash
docker compose port app 8501
```

Open `http://localhost:<reported-port>`. Every worktree receives a distinct
Docker-selected host port.

## Stop one container project

Run the exact `docker compose ... down` command printed by the helper. It
targets only that worktree's explicit Compose project and does not remove the
Git worktree or branch. Remove those later with explicit `git worktree remove`
and `git branch -d` commands when their changes are safely integrated.

## Parallel smoke test

Create two temporary worktrees:

```bash
./scripts/devcontainer-worktree.sh smoke-one
./scripts/devcontainer-worktree.sh smoke-two
```

For each worktree, use its printed commands to:

1. Run `python --version` and confirm Python 3.11.
2. Run `python -c "import astro_agent; print(astro_agent.__file__)"`.
3. Run `./scripts/run_ci_checks.sh full`.
4. Run `git status`.
5. Make an empty test commit with explicit smoke-test identity:
   `git -c user.name=Smoke -c user.email=smoke@example.test commit --allow-empty -m "test: container git smoke"`.
6. Check `curl http://host.docker.internal:11434/api/tags`.
7. Start Streamlit and resolve `docker compose port app 8501`.

Confirm the project names, containers, networks, and reported host ports differ.
Stop `smoke-one` and verify `smoke-two` still responds. Run the full CI gate in
one container with host Ollama stopped to prove CI remains offline-safe.

After verification, run each printed `down` command, then explicitly remove the
temporary worktrees and branches:

```bash
git worktree remove .worktrees/smoke-one
git worktree remove .worktrees/smoke-two
git branch -D agent/smoke-one agent/smoke-two
```
````

- [ ] **Step 4: Link the guide from README**

In `README.md`, add this bullet under **Standards & specs (for contributors and agents)**:

```markdown
- Parallel worktree Dev Containers: [`docs/development/devcontainers.md`](docs/development/devcontainers.md)
```

- [ ] **Step 5: Run documentation and unit contracts**

Run:

```bash
source .venv311/bin/activate
python -m ruff format tests/test_devcontainer_config.py
ASTRO_CI=1 python -m pytest \
  tests/test_devcontainer_support.py \
  tests/test_devcontainer_worktree.py \
  tests/test_devcontainer_config.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Run the full repository quality gate inside the container**

Use the project command printed by `python scripts/devcontainer_support.py prepare --worktree .`:

```bash
PROJECT="$(python scripts/devcontainer_support.py prepare --worktree .)"
docker compose \
  --project-directory .devcontainer \
  -f .devcontainer/compose.yaml \
  -f .devcontainer/compose.local.yaml \
  -p "$PROJECT" exec -T app ./scripts/run_ci_checks.sh full
```

Expected: ruff, mypy, and `ASTRO_CI=1` pytest pass.

- [ ] **Step 7: Execute the documented parallel smoke test**

Follow `docs/development/devcontainers.md#parallel-smoke-test` exactly.

Expected:
- Two distinct Compose projects, containers, networks, and mapped host ports.
- Git status and the hook-protected empty commit work in each container.
- Both containers reach host Ollama.
- Both Streamlit URLs respond.
- CI passes while host Ollama is stopped.
- Stopping one project leaves the second running.
- Rebuilding after only a source edit reports the dependency installation layer as cached.

- [ ] **Step 8: Check for leaked generated files and unrelated changes**

Run:

```bash
git status --short
git check-ignore .devcontainer/.env .devcontainer/compose.local.yaml .worktrees/
git diff --check
```

Expected:
- Generated metadata and `.worktrees/` are ignored.
- Only planned tracked files are modified.
- `git diff --check` exits zero.

- [ ] **Step 9: Commit documentation and final contracts**

```bash
git add README.md docs/development/devcontainers.md tests/test_devcontainer_config.py
git commit -m "docs: explain parallel devcontainer workflow"
```

- [ ] **Step 10: Final verification from a clean container**

Remove only the base checkout's Compose project, rebuild, and rerun all gates:

```bash
PROJECT="$(python scripts/devcontainer_support.py prepare --worktree .)"
docker compose \
  --project-directory .devcontainer \
  -f .devcontainer/compose.yaml \
  -f .devcontainer/compose.local.yaml \
  -p "$PROJECT" down
docker compose \
  --project-directory .devcontainer \
  -f .devcontainer/compose.yaml \
  -f .devcontainer/compose.local.yaml \
  -p "$PROJECT" up -d --build app
docker compose \
  --project-directory .devcontainer \
  -f .devcontainer/compose.yaml \
  -f .devcontainer/compose.local.yaml \
  -p "$PROJECT" exec -T app python -m pip install --user -e .
docker compose \
  --project-directory .devcontainer \
  -f .devcontainer/compose.yaml \
  -f .devcontainer/compose.local.yaml \
  -p "$PROJECT" exec -T app ./scripts/run_ci_checks.sh full
git status --short
```

Expected: clean build succeeds, the full quality gate passes, and only the pre-existing unrelated untracked `.cursor/` files remain.

