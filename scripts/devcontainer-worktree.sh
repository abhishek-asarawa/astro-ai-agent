#!/usr/bin/env bash
# Stable shell entrypoint for the tested Python worktree helper.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
exec python3 -m scripts.devcontainer_worktree "$@"
