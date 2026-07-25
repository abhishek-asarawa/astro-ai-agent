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
