# Agent instructions

This repo’s direction, coding standards, and feature specs live under `docs/`.
Agents should treat those docs as the source of truth—not this file. This is
the single, editor-agnostic entrypoint for every agent (no editor-specific rule
files; see ROADMAP decision D13).

## Where to look

- **Product roadmap:** [docs/ROADMAP.md](docs/ROADMAP.md) — vision, decisions,
  milestones M1–M6, numbered steps, and exit gates
- **Standards index:** [docs/standards/README.md](docs/standards/README.md)
- **Feature specs index:** [docs/specs/README.md](docs/specs/README.md)

## Workflow

1. Before picking up work, open the roadmap, find the active milestone, and
   take the next unblocked step (ROADMAP §6.1). Each step has a GitHub issue
   titled `[M1.3] …`.
2. Before writing or changing code, open the standards index and follow the
   relevant docs under `docs/standards/`.
3. Before building or changing a feature, open the specs index and read
   `docs/specs/<feature>.md`.
4. When exploring project context (including brainstorming), include
   `docs/ROADMAP.md` and `docs/specs/README.md` so design work stays aligned
   with the agreed direction and existing specs.

## Guardrails

Standards are enforced by tooling, not by editor rules: ruff and mypy, pytest
(`ASTRO_CI=1`), and the spec-driven commit gate (`scripts/check_spec_gate.sh`).
The git hooks run them locally (`./scripts/install-hooks.sh`) and CI runs the
same `scripts/run_ci_checks.sh`.
