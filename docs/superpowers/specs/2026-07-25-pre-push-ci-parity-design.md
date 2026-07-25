# Pre-push CI parity design

Date: 2026-07-25  
Status: approved for planning  
Branch context: `refactor/repo-hardening` (and future mainline work)

## Problem

PR #1 failed all GitHub Actions checks (ruff, mypy, pytest) even though local pytest had passed. Failures were discovered only after push because:

1. No active local git hooks (only `.git/hooks/*.sample`).
2. `scripts/run_ci_checks.sh` did not mirror CI (pytest only; stale `evaluate_template.py` path; no ruff/mypy).
3. CI never ran `pip install -e .`, so imports of `astro_agent` / `tests` failed in Actions while working in a local venv layout.
4. Local Python was often 3.9 while CI uses 3.11.

Developers should hit the same gate **before** a PR, not only on GitHub.

## Goals

- Fast feedback on every commit (lint/format).
- Full CI-equivalent gate on every push (lint, typecheck, unit tests).
- One shared command used by hooks **and** GitHub Actions (no command drift).
- Require Python ≥ 3.11 locally for the full gate (true CI parity).
- Make the gate usable on day one by fixing current CI-blocking issues as part of enablement.

## Non-goals

- Docker-based local CI.
- Adopting the pre-commit.com framework (explicitly declined; may revisit later).
- Running Ollama / eval harnesses in hooks.
- Server-side enforcement beyond existing GitHub Actions (Actions remain the remote backstop).

## Decisions

| Decision | Choice |
|----------|--------|
| When to block | Commit: fast checks. Push: full suite. |
| Hook mechanism | Repo-owned `.githooks/` + `core.hooksPath` via install script |
| Shared runner | `scripts/run_ci_checks.sh` with `fast` / `full` modes |
| Python version | Full mode requires ≥ 3.11; fail with setup instructions if lower |
| CI alignment | Workflow calls the same script; editable install for package imports |

## Architecture

```text
git commit
  → .githooks/pre-commit
      → scripts/run_ci_checks.sh fast
          → ruff check + ruff format --check (astro_agent/, tests/)

git push
  → .githooks/pre-push
      → scripts/run_ci_checks.sh full
          → assert python >= 3.11
          → ruff check + ruff format --check
          → mypy astro_agent/
          → ASTRO_CI=1 pytest tests/

GitHub Actions
  → pip install -e ".[dev]" (or requirements-dev + editable)
  → scripts/run_ci_checks.sh full   # same commands as pre-push
```

## Components

### 1. `scripts/run_ci_checks.sh` (rewrite)

- Usage: `scripts/run_ci_checks.sh [fast|full]` (default: `full`).
- Resolve Python as `python3` (or `PYTHON` env override); for `full`, refuse if version < 3.11.
- Ensure tools exist; on missing ruff/mypy/pytest, fail with install hint:
  `pip install -r requirements-dev.txt && pip install -e .`
- `fast`:
  - `ruff check astro_agent/ tests/`
  - `ruff format --check astro_agent/ tests/`
- `full`:
  - same ruff steps
  - `mypy astro_agent/`
  - `ASTRO_CI=1 pytest tests/ -q --tb=short`
- Remove stale `evaluate_template.py` invocation.
- Exit non-zero on first failure (`set -euo pipefail`).

### 2. `.githooks/pre-commit`

- Runs `scripts/run_ci_checks.sh fast`.
- Blocks commit on failure.

### 3. `.githooks/pre-push`

- Runs `scripts/run_ci_checks.sh full`.
- Blocks push on failure.
- On Python < 3.11, print clear venv upgrade instructions.

### 4. `scripts/install-hooks.sh`

- Sets `git config core.hooksPath .githooks` for this repository.
- Idempotent; safe to re-run.
- Documented as required after clone in README.

### 5. `.github/workflows/ci.yml`

- Install package in editable mode with `requirements-dev.txt` (includes runtime + ruff/mypy/pytest).
- Prefer **one** job that runs `scripts/run_ci_checks.sh full` on Python 3.11 so CI cannot diverge from pre-push.
- If parallel jobs are kept for speed, the script must expose exact subset modes (`ruff`, `mypy`, `pytest`) that compose into `full` with no extra/missing flags.

### 6. Docs

- README setup: Python 3.11 venv, `pip install -e .` + `requirements-dev.txt`, `scripts/install-hooks.sh`.
- `docs/standards/testing.md`: note that pre-push runs the same full gate as CI.
- Mention emergency bypass once: `git push --no-verify` / documented skip — not recommended.

## Day-one enablement (must ship with the gate)

So hooks are not immediately unusable:

1. Fix CI package import: `pip install -e .` (and ensure `tests` imports work without relying on cwd hacks, or document `python -m pytest` with package installed).
2. Clear current ruff failures (autofix where safe; `zip(..., strict=True)` / import order / unused imports).
3. Clear mypy annotations on `yogas.py` / `lords.py` (or other reported errors).
4. Confirm `scripts/run_ci_checks.sh full` passes locally on Python 3.11 before declaring done.

## Error handling

| Condition | Behavior |
|-----------|----------|
| Missing ruff/mypy/pytest | Fail with install instructions |
| Python < 3.11 on `full` | Fail; do not continue |
| Hooks not installed | No local block; CI still fails — README requires install |
| Emergency skip | `git commit/push --no-verify` allowed but discouraged |

## Success criteria

- After `scripts/install-hooks.sh`, a deliberate ruff violation blocks `git commit`.
- A failing unit test blocks `git push`.
- `scripts/run_ci_checks.sh full` on Python 3.11 matches GitHub Actions outcome for the same commit.
- PR checks can go green without developers discovering new *command-set* surprises that local full mode would not have caught.

## Implementation notes (for the plan, not speculative scope creep)

- Prefer rewriting existing `scripts/run_ci_checks.sh` over adding a second parallel checker.
- Do not vendor pre-commit.com in this iteration.
- Keep hook scripts executable in git (`chmod +x`).
