# Pre-push CI Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Catch ruff, mypy, and pytest failures locally on commit/push instead of discovering them on the PR.

**Architecture:** One shared shell script (`scripts/run_ci_checks.sh`) with `fast` and `full` modes becomes the single source of truth. Thin git hooks in `.githooks/` call it (fast on commit, full on push), and GitHub Actions calls the same script so the command list cannot drift. Full mode refuses to run on Python older than 3.11 so local results match CI.

**Tech Stack:** Bash, git `core.hooksPath`, ruff, mypy, pytest, GitHub Actions, Python 3.11.

**Design spec:** [docs/superpowers/specs/2026-07-25-pre-push-ci-parity-design.md](../specs/2026-07-25-pre-push-ci-parity-design.md)

## Global Constraints

- Full gate requires Python >= 3.11 (CI pins `python-version: "3.11"`); fail with setup instructions if lower.
- Local machine currently has **no** Python 3.11: `python3` is 3.14.4 and `venv/` is 3.9.6. Task 1 creates `.venv311`.
- Ruff config lives in `pyproject.toml` (`line-length = 120`, `select = ["E", "F", "W", "I", "UP", "B"]`, `E501` ignored). Do not change ruff rule selection to make errors disappear.
- Ruff targets exactly `astro_agent/ tests/` (matches current CI).
- Mypy targets exactly `astro_agent/`, stays non-strict (`strict = false` in `pyproject.toml`).
- Tests always run with `ASTRO_CI=1`.
- Tests must be invoked as `python -m pytest` (not bare `pytest`) so the repo root lands on `sys.path`; bare `pytest` is the exact reason CI failed with `ModuleNotFoundError: No module named 'astro_agent'` and `No module named 'tests'`.
- Do NOT adopt pre-commit.com in this iteration. Do NOT add Docker-based CI. Do NOT run Ollama or `evals/` in hooks.
- Keep hook scripts and shell scripts executable in git (mode `755`).
- Branch for this work: `refactor/repo-hardening` (PR #1 already open).

---

### Task 1: Bootstrap a Python 3.11 dev environment

**Files:**
- Create: `.venv311/` (untracked, local only)
- Modify: `.gitignore` (add `.venv311/`)

**Interfaces:**
- Consumes: nothing.
- Produces: a Python 3.11 interpreter at `.venv311/bin/python` with `ruff`, `mypy`, `pytest`, and the `astro_agent` package installed in editable mode. Every later task runs commands with `.venv311` activated.

- [ ] **Step 1: Confirm no 3.11 exists yet**

Run: `python3 --version && ls /opt/homebrew/opt/python@3.11/bin/python3.11 2>/dev/null || echo "no 3.11"`
Expected: prints `Python 3.14.4` and `no 3.11`.

- [ ] **Step 2: Install Python 3.11**

```bash
brew install python@3.11
```

Expected: Homebrew installs it; `/opt/homebrew/opt/python@3.11/bin/python3.11` now exists.

- [ ] **Step 3: Create and populate the 3.11 virtualenv**

```bash
cd /Users/abhishekasarawa/astro-ai-agent
/opt/homebrew/opt/python@3.11/bin/python3.11 -m venv .venv311
source .venv311/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -e .
```

- [ ] **Step 4: Verify all three tools resolve on 3.11**

```bash
source .venv311/bin/activate
python --version
python -m ruff --version
python -m mypy --version
python -m pytest --version
python -c "import astro_agent; print(astro_agent.__file__)"
```

Expected: `Python 3.11.x`, a version line for ruff/mypy/pytest, and a path to `astro_agent/__init__.py`.

- [ ] **Step 5: Ignore the new venv**

Add this line to `.gitignore` (keep existing content):

```gitignore
.venv311/
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore .venv311 python 3.11 dev environment"
```

---

### Task 2: Shared quality-gate script with fast/full modes

**Files:**
- Modify (full rewrite): `scripts/run_ci_checks.sh`
- Test: `tests/test_ci_gate.py`

**Interfaces:**
- Consumes: `.venv311` from Task 1.
- Produces: `scripts/run_ci_checks.sh [fast|full]`.
  - `fast` runs `ruff check` + `ruff format --check` on `astro_agent/ tests/`.
  - `full` runs the version guard, then ruff (same two commands), then `mypy astro_agent/`, then `ASTRO_CI=1 python -m pytest tests/ -q --tb=short`.
  - Interpreter is `${PYTHON:-python3}`; exit code 0 on success, non-zero on any failure.
  - Failure messages are written to stderr and prefixed `[run_ci_checks]`.
  - Unknown mode prints `Unknown mode` to stderr. Old interpreter prints `Python >= 3.11 required`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ci_gate.py`:

```python
"""Contract tests for the shared quality-gate script used by hooks and CI."""

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_ci_checks.sh"


def _run(args, extra_env=None):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )


def test_script_exists_and_is_executable():
    assert SCRIPT.exists(), f"missing {SCRIPT}"
    assert os.access(SCRIPT, os.X_OK), f"{SCRIPT} is not executable"


def test_unknown_mode_is_rejected():
    result = _run(["bogus-mode"])
    assert result.returncode != 0
    assert "Unknown mode" in result.stderr


def test_full_mode_refuses_old_interpreter(tmp_path):
    """A stub interpreter that fails the version probe must block full mode."""
    stub = tmp_path / "python-too-old"
    stub.write_text("#!/usr/bin/env bash\nexit 1\n")
    stub.chmod(0o755)

    result = _run(["full"], extra_env={"PYTHON": str(stub)})
    assert result.returncode != 0
    assert "Python >= 3.11 required" in result.stderr
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv311/bin/activate && ASTRO_CI=1 python -m pytest tests/test_ci_gate.py -v`
Expected: FAIL — `test_unknown_mode_is_rejected` and `test_full_mode_refuses_old_interpreter` fail because the current script ignores arguments and has no version guard.

- [ ] **Step 3: Rewrite the script**

Replace the entire contents of `scripts/run_ci_checks.sh` with:

```bash
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
```

- [ ] **Step 4: Make it executable and run the tests**

```bash
chmod +x scripts/run_ci_checks.sh
source .venv311/bin/activate
ASTRO_CI=1 python -m pytest tests/test_ci_gate.py -v
```

Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/run_ci_checks.sh tests/test_ci_gate.py
git commit -m "feat(ci): shared fast/full quality gate script with python 3.11 guard"
```

---

### Task 3: Make ruff clean

**Files:**
- Modify: `astro_agent/chart/lords.py:24` (B904)
- Modify: `astro_agent/rag/builder.py:320` (B007)
- Modify: `astro_agent/rag/search.py:313` (B005), `:382`, `:488`, `:678`, `:688` (B905)
- Modify: `astro_agent/llm/client.py:11` (F401)
- Modify: `astro_agent/llm/conversation.py:10` (UP035)
- Modify: `astro_agent/service/consultation.py:12` (UP035 + F401)
- Modify: many files via autofix/format (whitespace W291/W293/W292, import order I001)
- Test: `tests/test_ci_gate.py` (add fast-mode smoke test)

**Interfaces:**
- Consumes: `scripts/run_ci_checks.sh fast` from Task 2.
- Produces: `scripts/run_ci_checks.sh fast` exits 0. No public function signatures change in this task.

CI reported **51 ruff errors, 44 auto-fixable**: 18 W293, 12 I001, 6 W291, 4 W292, 4 B905, 2 UP035, 2 F401, 1 B904, 1 B007, 1 B005.

- [ ] **Step 1: Apply the automatic fixes**

```bash
source .venv311/bin/activate
python -m ruff check --fix astro_agent/ tests/
python -m ruff format astro_agent/ tests/
```

Expected: whitespace and import-order errors disappear; a sizable formatting diff is normal and acceptable.

- [ ] **Step 2: See what remains**

Run: `python -m ruff check astro_agent/ tests/`
Expected: only the non-auto-fixable errors remain (B905 x4, B904, B007, B005, UP035 x2, F401 x2).

- [ ] **Step 3: Fix `B904` in `astro_agent/chart/lords.py`**

Change:

```python
    try:
        lagna_idx = RASHIS.index(lagna_rashi)
    except ValueError:
        raise ValueError(f"Invalid Rashi: {lagna_rashi}")
```

to:

```python
    try:
        lagna_idx = RASHIS.index(lagna_rashi)
    except ValueError:
        raise ValueError(f"Invalid Rashi: {lagna_rashi}") from None
```

- [ ] **Step 4: Fix `B007` in `astro_agent/rag/builder.py`**

The loop variable `ve` is unused. Change:

```python
    for vs, ve, body in verses:
```

to:

```python
    for vs, _ve, body in verses:
```

- [ ] **Step 5: Fix `B005` in `astro_agent/rag/search.py`**

`str.strip()` with a multi-character string is misleading. Replace:

```python
    out = out.strip("\"'""''").strip()
```

with an explicit surrounding-quote strip:

```python
    out = _SURROUNDING_QUOTES_RE.sub("", out).strip()
```

and add this module-level constant immediately after the existing `_REF_TAG_ANY_RE = re.compile(r"\[ref:[^\]]+\]")` line (~line 278):

```python
# Strip straight and curly quotes that models wrap around rewritten queries.
_SURROUNDING_QUOTES_RE = re.compile(r'^["\'\u201c\u201d\u2018\u2019]+|["\'\u201c\u201d\u2018\u2019]+$')
```

- [ ] **Step 6: Fix the four `B905` zip calls in `astro_agent/rag/search.py`**

Use `strict=False` to preserve today's truncating behavior (`strict=True` would raise on ragged inputs).

Line ~382:

```python
    for i, (cid, doc, meta, dist) in enumerate(zip(ids, docs, metas, dists, strict=False)):
```

Line ~488:

```python
    by_id = {cid: {"text": d, "metadata": m or {}} for cid, d, m in zip(ids_list, docs_list, metas_list, strict=False)}
```

Line ~678:

```python
    for chunk, hn, cn in zip(chunks, heur_n, ce_n, strict=False):
```

Line ~688:

```python
    for chunk, s in zip(chunks, scores, strict=False):
```

- [ ] **Step 7: Fix `UP035` in `astro_agent/llm/conversation.py`**

Change:

```python
from typing import Callable
```

to:

```python
from collections.abc import Callable
```

- [ ] **Step 8: Fix `UP035` + `F401` in `astro_agent/service/consultation.py`**

`Any` is unused and `Callable`/`Iterator` must come from `collections.abc`. Change:

```python
from typing import Any, Callable, Iterator
```

to:

```python
from collections.abc import Callable, Iterator
```

- [ ] **Step 9: Fix `F401` in `astro_agent/llm/client.py`**

`build_prompt_for_intent` is imported but unused. Change:

```python
from astro_agent.llm.prompts.builder import build_career_prompt, build_prompt_for_intent
```

to:

```python
from astro_agent.llm.prompts.builder import build_career_prompt
```

- [ ] **Step 10: Add a fast-mode smoke test**

Append to `tests/test_ci_gate.py`:

```python
def test_fast_mode_passes_on_clean_tree():
    """The repo must stay lint-clean so the pre-commit hook is usable."""
    result = _run(["fast"])
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 11: Verify ruff and tests are green**

```bash
source .venv311/bin/activate
./scripts/run_ci_checks.sh fast
ASTRO_CI=1 python -m pytest tests/ -q
```

Expected: `fast checks passed.` and all tests pass. If the prompt-fingerprint test in `tests/test_characterization_baselines.py` fails, formatting changed a prompt string — revert that specific formatting change rather than editing the expected hash.

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "style: make ruff clean (autofix, format, strict zip, quote strip, imports)"
```

---

### Task 4: Make mypy clean

**Files:**
- Modify: `astro_agent/chart/yogas.py:24`
- Modify: `astro_agent/chart/lords.py:26`

**Interfaces:**
- Consumes: nothing from earlier tasks beyond the 3.11 env.
- Produces: `python -m mypy astro_agent/` exits 0. `get_planetary_dignity` still returns a list of tag strings; `get_house_lords` still returns a dict mapping planet name to a list of house numbers.

CI reported exactly two errors:
```
astro_agent/chart/yogas.py:24: error: Need type annotation for "tags"
astro_agent/chart/lords.py:26: error: Need type annotation for "lordships"
```

- [ ] **Step 1: Reproduce the failure**

Run: `source .venv311/bin/activate && python -m mypy astro_agent/`
Expected: FAIL with the two `var-annotated` errors above.

- [ ] **Step 2: Annotate `tags` in `astro_agent/chart/yogas.py`**

Change:

```python
    tags = []
```

to:

```python
    tags: list[str] = []
```

- [ ] **Step 3: Annotate `lordships` in `astro_agent/chart/lords.py`**

Change:

```python
    lordships = {
        "Sun": [], "Moon": [], "Mars": [], "Mercury": [],
        "Jupiter": [], "Venus": [], "Saturn": [], "Rahu": [], "Ketu": []
    }
```

to:

```python
    lordships: dict[str, list[int]] = {
        "Sun": [], "Moon": [], "Mars": [], "Mercury": [],
        "Jupiter": [], "Venus": [], "Saturn": [], "Rahu": [], "Ketu": []
    }
```

- [ ] **Step 4: Verify mypy passes and nothing regressed**

```bash
source .venv311/bin/activate
python -m mypy astro_agent/
python -m ruff check astro_agent/ tests/
ASTRO_CI=1 python -m pytest tests/ -q
```

Expected: `Success: no issues found`, ruff clean, tests pass.

- [ ] **Step 5: Commit**

```bash
git add astro_agent/chart/yogas.py astro_agent/chart/lords.py
git commit -m "fix(types): annotate dignity tags and house lordship containers"
```

---

### Task 5: Prove the full gate is green end-to-end

**Files:**
- Test: no new files; this task validates `scripts/run_ci_checks.sh full`

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: a verified-green `scripts/run_ci_checks.sh full` on Python 3.11, which is the exact command CI will run in Task 7.

- [ ] **Step 1: Run the full gate**

```bash
source .venv311/bin/activate
./scripts/run_ci_checks.sh full
```

Expected final line: `[run_ci_checks] full checks passed.`

- [ ] **Step 2: Prove the packaging fix works without the editable install**

This reproduces CI's original `ModuleNotFoundError` conditions.

```bash
source .venv311/bin/activate
pip uninstall -y astro-ai-agent
./scripts/run_ci_checks.sh full
pip install -e .
```

Expected: still passes, because the script uses `python -m pytest` (repo root on `sys.path`).

- [ ] **Step 3: Prove the version guard blocks the old 3.9 venv**

```bash
PYTHON=venv/bin/python ./scripts/run_ci_checks.sh full
```

Expected: non-zero exit with `Python >= 3.11 required for full checks.`

- [ ] **Step 4: Commit (only if any fix was needed)**

If Steps 1-3 required a script change:

```bash
git add scripts/run_ci_checks.sh
git commit -m "fix(ci): keep full gate green without editable install"
```

If nothing changed, skip the commit and note the verification output in the task report.

---

### Task 6: Install git hooks (fast on commit, full on push)

**Files:**
- Create: `.githooks/pre-commit`
- Create: `.githooks/pre-push`
- Create: `scripts/install-hooks.sh`
- Test: `tests/test_ci_gate.py` (add hook wiring assertions)

**Interfaces:**
- Consumes: `scripts/run_ci_checks.sh` modes from Task 2.
- Produces: `scripts/install-hooks.sh` sets `core.hooksPath=.githooks`. `.githooks/pre-commit` runs mode `fast`; `.githooks/pre-push` runs mode `full`. Both are executable and block the git operation on non-zero exit.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ci_gate.py`:

```python
HOOKS_DIR = REPO_ROOT / ".githooks"


def test_hooks_exist_and_are_executable():
    for name in ("pre-commit", "pre-push"):
        hook = HOOKS_DIR / name
        assert hook.exists(), f"missing hook {hook}"
        assert os.access(hook, os.X_OK), f"{hook} is not executable"


def test_pre_commit_runs_fast_mode():
    body = (HOOKS_DIR / "pre-commit").read_text()
    assert "run_ci_checks.sh" in body
    assert "fast" in body


def test_pre_push_runs_full_mode():
    body = (HOOKS_DIR / "pre-push").read_text()
    assert "run_ci_checks.sh" in body
    assert "full" in body


def test_install_hooks_script_sets_hooks_path():
    installer = REPO_ROOT / "scripts" / "install-hooks.sh"
    assert installer.exists()
    assert os.access(installer, os.X_OK)
    assert "core.hooksPath" in installer.read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv311/bin/activate && ASTRO_CI=1 python -m pytest tests/test_ci_gate.py -v`
Expected: FAIL — the `.githooks/` directory and installer do not exist yet.

- [ ] **Step 3: Create `.githooks/pre-commit`**

```bash
#!/usr/bin/env bash
# Fast lint/format gate. Full suite runs on push (see .githooks/pre-push).
set -euo pipefail
exec "$(git rev-parse --show-toplevel)/scripts/run_ci_checks.sh" fast
```

- [ ] **Step 4: Create `.githooks/pre-push`**

```bash
#!/usr/bin/env bash
# Full CI-equivalent gate so PR checks hold no surprises.
set -euo pipefail
exec "$(git rev-parse --show-toplevel)/scripts/run_ci_checks.sh" full
```

- [ ] **Step 5: Create `scripts/install-hooks.sh`**

```bash
#!/usr/bin/env bash
# One-time setup: point git at the repo-owned hooks in .githooks/.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

git config core.hooksPath .githooks
chmod +x .githooks/pre-commit .githooks/pre-push scripts/run_ci_checks.sh

echo "Git hooks installed (core.hooksPath=.githooks)."
echo "  commit -> scripts/run_ci_checks.sh fast"
echo "  push   -> scripts/run_ci_checks.sh full"
```

- [ ] **Step 6: Make everything executable and install**

```bash
chmod +x .githooks/pre-commit .githooks/pre-push scripts/install-hooks.sh
./scripts/install-hooks.sh
git config --get core.hooksPath
```

Expected: prints `.githooks`.

- [ ] **Step 7: Run the tests**

Run: `source .venv311/bin/activate && ASTRO_CI=1 python -m pytest tests/test_ci_gate.py -v`
Expected: PASS (all hook tests green).

- [ ] **Step 8: Prove the pre-commit hook actually blocks a violation**

```bash
printf 'import os\n' > astro_agent/_hook_probe.py   # unused import => ruff F401
git add astro_agent/_hook_probe.py
git commit -m "test: should be blocked"   # expect failure
```

Expected: commit is rejected and ruff reports `F401`. Then clean up:

```bash
git reset HEAD astro_agent/_hook_probe.py
rm astro_agent/_hook_probe.py
```

- [ ] **Step 9: Commit the hooks**

```bash
git add .githooks/pre-commit .githooks/pre-push scripts/install-hooks.sh tests/test_ci_gate.py
git commit -m "feat(ci): add pre-commit/pre-push hooks calling the shared gate"
```

Note: this commit itself now runs the fast gate — it must pass.

---

### Task 7: Point GitHub Actions at the same script

**Files:**
- Modify (full rewrite): `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `scripts/run_ci_checks.sh full` verified in Task 5.
- Produces: one CI job named `Checks (ruff, mypy, pytest)` that installs dev deps plus the editable package and then runs the shared script.

- [ ] **Step 1: Replace the workflow**

Overwrite `.github/workflows/ci.yml` with:

```yaml
name: CI

on:
  push:
    branches: ["main", "master"]
  pull_request:

jobs:
  checks:
    name: Checks (ruff, mypy, pytest)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-dev.txt
          pip install -e .
      - name: Run shared quality gate
        # Same command as the local pre-push hook, so PR checks cannot drift.
        run: ./scripts/run_ci_checks.sh full
```

- [ ] **Step 2: Confirm the script is executable in git**

Run: `git ls-files -s scripts/run_ci_checks.sh`
Expected: mode `100755`. If it shows `100644`, fix it:

```bash
git update-index --chmod=+x scripts/run_ci_checks.sh
```

- [ ] **Step 3: Verify the exact CI command locally one more time**

```bash
source .venv311/bin/activate
./scripts/run_ci_checks.sh full
```

Expected: `full checks passed.`

- [ ] **Step 4: Commit and push**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run the shared quality gate in a single python 3.11 job"
git push
```

Expected: the pre-push hook runs the full gate first and passes; push succeeds.

- [ ] **Step 5: Confirm PR #1 checks pass**

```bash
gh pr checks 1 --watch
```

Expected: `Checks (ruff, mypy, pytest)` reports `pass`.

---

### Task 8: Document the gate

**Files:**
- Modify: `README.md` (setup + checks sections)
- Modify: `docs/standards/testing.md`

**Interfaces:**
- Consumes: Tasks 1-7.
- Produces: documentation telling a fresh contributor to use Python 3.11, install hooks once, and run `./scripts/run_ci_checks.sh full` before pushing.

- [ ] **Step 1: Update `README.md` setup instructions**

Replace the "### 2. Install Python dependencies" block with:

````markdown
### 2. Install Python dependencies

CI runs Python 3.11, and the pre-push gate requires 3.11 or newer.

```bash
brew install python@3.11
/opt/homebrew/opt/python@3.11/bin/python3.11 -m venv .venv311
source .venv311/bin/activate
pip install -r requirements-dev.txt
pip install -e .
```

### 2b. Install git hooks (once per clone)

```bash
./scripts/install-hooks.sh
```

This points git at `.githooks/`: commits run the fast lint gate, pushes run the
full CI-equivalent gate (ruff, mypy, pytest), so PR checks hold no surprises.
````

- [ ] **Step 2: Update the README checks section**

Replace the "### Unit tests / lint" block with:

````markdown
### Quality gate

Local hooks and GitHub Actions run the same script:

```bash
./scripts/run_ci_checks.sh fast   # ruff lint + format check (pre-commit)
./scripts/run_ci_checks.sh full   # + mypy + ASTRO_CI=1 pytest (pre-push, CI)
```

Bypass only in emergencies with `git push --no-verify`; CI will still fail.
````

- [ ] **Step 3: Add a note to `docs/standards/testing.md`**

Append this section to the end of the file:

```markdown
## Local gate matches CI

`.githooks/pre-push` runs `scripts/run_ci_checks.sh full`, which is the same
command GitHub Actions runs: ruff check, ruff format check, `mypy astro_agent/`,
and `ASTRO_CI=1 pytest tests/`. Full mode requires Python >= 3.11 because CI
pins 3.11. Install the hooks once with `./scripts/install-hooks.sh`.
```

- [ ] **Step 4: Verify docs did not break the gate**

```bash
source .venv311/bin/activate
./scripts/run_ci_checks.sh full
```

Expected: `full checks passed.`

- [ ] **Step 5: Commit and push**

```bash
git add README.md docs/standards/testing.md
git commit -m "docs: document python 3.11 setup, git hooks, and shared quality gate"
git push
```

---

## Self-Review

**1. Spec coverage**

| Spec requirement | Task |
|---|---|
| Fast checks on commit | Task 6 (`.githooks/pre-commit`) |
| Full CI-equivalent gate on push | Task 6 (`.githooks/pre-push`) |
| One shared command for hooks + Actions | Task 2 (script), Task 7 (workflow) |
| Python >= 3.11 required locally, clear failure message | Task 1 (env), Task 2 (guard), Task 5 Step 3 (proof) |
| `scripts/run_ci_checks.sh` rewrite, drop stale `evaluate_template.py` | Task 2 Step 3 |
| `.githooks/` + `core.hooksPath` install script | Task 6 |
| CI editable install / import fix | Task 5 Step 2, Task 7 Step 1 |
| Day-one: clear ruff failures | Task 3 |
| Day-one: clear mypy failures | Task 4 |
| Docs (README + standards) | Task 8 |
| Emergency bypass mentioned once | Task 8 Step 2 |
| Non-goals respected (no Docker, no pre-commit.com, no evals in hooks) | Global Constraints |

No spec requirement is unassigned.

**2. Placeholder scan** — no TBD/TODO items; every code step contains the literal content to write, and every command lists expected output.

**3. Type consistency** — mode names (`fast`, `full`), env override (`PYTHON`), message strings (`Unknown mode`, `Python >= 3.11 required`), and paths (`scripts/run_ci_checks.sh`, `.githooks/pre-commit`, `.githooks/pre-push`, `scripts/install-hooks.sh`) are identical across the script, the tests in Tasks 2/6, the workflow in Task 7, and the docs in Task 8.
