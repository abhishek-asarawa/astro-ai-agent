# Coding standards

How this repo expects code to be written, reviewed, and verified.

These docs are the **source of truth**. There are no editor-specific rule files; agents reach these docs through [AGENTS.md](../../AGENTS.md), and tooling enforces them (see below).

## Documents

| Doc | Covers |
|-----|--------|
| [coding.md](coding.md) | Architecture boundaries, single sources of truth, typed public APIs |
| [comments.md](comments.md) | Module/public/helper docstrings and rationale at heuristics |
| [testing.md](testing.md) | Unit tests, fixtures, mocked LLM calls, evals as quality gates |
| [config.md](config.md) | Named constants, env overrides, rationale at tunables |

## How standards are enforced

1. **Ruff** — lint + format on `astro_agent/` and `tests/` (see `[tool.ruff]` in `pyproject.toml`). CI job `Lint (ruff)` runs `ruff check` and `ruff format --check`.
2. **Mypy** — static types on `astro_agent/` (`[tool.mypy]` in `pyproject.toml`). CI job `Type-check (mypy)`.
3. **Pytest** — unit tests under `tests/`. CI job `Unit tests (pytest)` with `ASTRO_CI=1` so Ollama/SwissEph-heavy paths are skipped or stubbed.
4. **Spec gate** — `scripts/check_spec_gate.sh` requires a `Spec: docs/specs/<file>.md` (or `Spec-Exempt: <reason>`) trailer on commits that touch the feature surface.
5. **Git hooks** — `./scripts/install-hooks.sh` once per clone; commits run the fast gate, pushes run the full CI-equivalent gate (`scripts/run_ci_checks.sh full`).
6. **Human / agent review** — PRs and agent edits should cite the matching standard when touching layout, comments, tests, or config.

## Related product docs

Product direction and milestones live in [docs/ROADMAP.md](../ROADMAP.md). Feature behavior (what the product must do) lives under [docs/specs/](../specs/README.md), not here.

Engineering backlog remains in [docs/FUTURE_IMPROVEMENTS.md](../FUTURE_IMPROVEMENTS.md).
