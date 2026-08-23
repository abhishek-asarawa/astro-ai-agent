#!/usr/bin/env bash
# One-time setup: point git at the repo-owned hooks in .githooks/.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

git config core.hooksPath .githooks
chmod +x .githooks/pre-commit .githooks/commit-msg .githooks/pre-push \
    scripts/run_ci_checks.sh scripts/check_spec_gate.sh

echo "Git hooks installed (core.hooksPath=.githooks)."
echo "  commit -> scripts/run_ci_checks.sh fast + scripts/check_spec_gate.sh commit-msg"
echo "  push   -> scripts/run_ci_checks.sh full + scripts/check_spec_gate.sh range (per pushed ref)"
