#!/usr/bin/env bash
# One-time setup: point git at the repo-owned hooks in .githooks/.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

git config core.hooksPath .githooks
chmod +x .githooks/pre-commit .githooks/pre-push scripts/run_ci_checks.sh

echo "Git hooks installed (core.hooksPath=.githooks)."
echo "  commit -> scripts/run_ci_checks.sh fast"
echo "  push   -> scripts/run_ci_checks.sh full"
