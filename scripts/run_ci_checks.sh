#!/usr/bin/env bash
# Shared quality gate. Git hooks and GitHub Actions both call this script so the
# command list cannot drift between local pushes and PR checks.
#
# Usage: scripts/run_ci_checks.sh [fast|full]
#   fast : ruff lint + format check            (pre-commit)
#   full : fast + mypy + unit tests            (pre-push, CI)
set -euo pipefail

MODE="${1:-full}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Override with PYTHON=... to test the gate against a specific interpreter.
PY="${PYTHON:-python3}"

die() {
    printf '\n[run_ci_checks] %s\n' "$1" >&2
    exit 1
}

step() {
    printf '[run_ci_checks] %s\n' "$1"
}

require_python_version() {
    # CI pins 3.11; older interpreters can produce different lint/type/test
    # results, which is exactly the PR surprise this gate exists to prevent.
    if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
        die "Python >= 3.11 required for full checks.
Set up a 3.11 environment:
  brew install python@3.11
  /opt/homebrew/opt/python@3.11/bin/python3.11 -m venv .venv311
  source .venv311/bin/activate
  pip install -r requirements-dev.txt && pip install -e .
Then re-run: scripts/run_ci_checks.sh full"
    fi
}

require_tool() {
    local tool="$1"
    if ! "$PY" -m "$tool" --version >/dev/null 2>&1; then
        die "$tool is not available for '$PY'.
Install dev tooling:
  pip install -r requirements-dev.txt && pip install -e ."
    fi
}

run_ruff() {
    step "ruff check astro_agent/ tests/"
    "$PY" -m ruff check astro_agent/ tests/
    step "ruff format --check astro_agent/ tests/"
    "$PY" -m ruff format --check astro_agent/ tests/
}

run_mypy() {
    step "mypy astro_agent/"
    "$PY" -m mypy astro_agent/
}

run_pytest() {
    # `python -m pytest` keeps the repo root on sys.path so `astro_agent` and
    # `tests.fixtures` import without an editable install.
    step "pytest tests/ (ASTRO_CI=1)"
    ASTRO_CI=1 "$PY" -m pytest tests/ -q --tb=short
}

case "$MODE" in
    fast)
        require_tool ruff
        run_ruff
        ;;
    full)
        require_python_version
        require_tool ruff
        require_tool mypy
        require_tool pytest
        run_ruff
        run_mypy
        run_pytest
        ;;
    *)
        die "Unknown mode '$MODE' (expected: fast|full)"
        ;;
esac

step "$MODE checks passed."
