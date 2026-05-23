#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pytest tests/ -q --ignore=tests/test_cities_network.py 2>/dev/null || python3 -m pytest tests/ -q
python3 evaluate_template.py --fail-on-regression
echo "CI checks passed."
