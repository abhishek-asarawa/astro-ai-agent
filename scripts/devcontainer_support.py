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

# Git hooks (and some IDEs) export GIT_DIR / GIT_WORK_TREE. Those override
# `git -C <path>`, so fixture repos and helper `-C` calls would hit the parent
# checkout instead of the intended tree. Strip them for every `-C` invocation.
_GIT_ENV_OVERRIDE_KEYS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_INDEX_FILE",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)


def git_subprocess_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """Return an environment where `git -C` is not overridden by parent GIT_* vars."""
    env = dict(os.environ if base is None else base)
    for key in _GIT_ENV_OVERRIDE_KEYS:
        env.pop(key, None)
    return env


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
        env=git_subprocess_env(),
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


def _bind_mount(path: Path) -> str:
    """Render one same-path bind-mount Compose volume entry."""
    quoted = json.dumps(str(path))
    return f"      - type: bind\n        source: {quoted}\n        target: {quoted}\n"


def _render_override(context: DevcontainerContext) -> str:
    """Render the host-specific mounts only a linked worktree needs.

    A linked worktree's `.git` file, and the matching
    `<git-common-dir>/worktrees/<name>/gitdir` pointer maintained by the
    primary checkout, both record this worktree's absolute host path. If the
    container only mounted the worktree at `/workspace` (as compose.yaml
    does) and the common dir at its own absolute path (below), those
    pointers would resolve to a path that does not exist inside the
    container. Git treats that as a dangling worktree, so `git worktree
    prune`/`list` run from inside the container could delete this worktree's
    administrative metadata. Mounting the worktree at its own absolute host
    path too — the same trick already used for the common dir — keeps both
    pointers valid from inside the container.
    """
    if not context.linked_worktree:
        return "services: {}\n"
    volumes = _bind_mount(context.git_common_dir) + _bind_mount(context.worktree)
    return f"services:\n  app:\n    volumes:\n{volumes}"


def prepare_local_files(worktree: Path) -> DevcontainerContext:
    """Write idempotent local Compose metadata for one checkout."""
    context = resolve_context(worktree)
    devcontainer_dir = context.worktree / ".devcontainer"
    devcontainer_dir.mkdir(exist_ok=True)
    (devcontainer_dir / ".env").write_text(
        f"COMPOSE_PROJECT_NAME={context.project_name}\nLOCAL_UID={os.getuid()}\nLOCAL_GID={os.getgid()}\n"
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
