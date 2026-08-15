# Design: automated enforcement of spec-driven development

**Date:** 2026-08-06
**Status:** implemented (2026-08-15)

## Problem

`AGENTS.md` and `.cursor/rules/astro-standards.mdc` instruct agents to read the
matching `docs/specs/<feature>.md` before changing feature behavior, but this is
convention only — nothing prevents an agent (or a human) from skipping it. Published
measurements on comparable setups show instruction files like `AGENTS.md` are
followed roughly 60-70% of the time; deterministic hooks are followed 100% of the
time. This design adds a deterministic gate.

## Constraint: must not depend on one agent/tool

This repo is worked on by multiple AI coding tools (Cursor today; potentially
Claude Code, Codex CLI, or a human elsewhere). A gate implemented only as a
Cursor-specific `preToolUse` hook would silently do nothing for any other tool
or for a plain `git commit`. The enforcement must therefore live primarily at
the **git/CI boundary**, which is agent-agnostic by construction. A
Cursor-specific hook may exist as an *additive* convenience layer, but is never
the source of truth.

## Design

### Three layers, one shared script

```
git diff (staged / PR range)
        │
        ▼
scripts/check_spec_gate.sh   <- single source of truth, mirrors the
        │                        existing scripts/run_ci_checks.sh pattern
   ┌────┼───────────────────────┐
   ▼    ▼                       ▼
.githooks/commit-msg      .githooks/commit-msg        CI job (checks.yml)
(local, per commit)       (same script, same mode)    (merge-base..HEAD, server-side,
                                                         cannot be skipped with --no-verify)

Optional, additive, Cursor-only:
.cursor/hooks/spec-gate.sh (preToolUse on Write|StrReplace)
-> soft "ask" nudge inside Cursor sessions only. Not authoritative.
```

This mirrors the repo's existing shared-gate convention (`scripts/run_ci_checks.sh`
called identically by `.githooks/pre-push` and `.github/workflows/ci.yml`), so the
new gate cannot drift between local and CI the same way the lint/type/test gate
already cannot.

### Check logic (`scripts/check_spec_gate.sh`)

Runs against a file-change list + a set of commit messages, computed differently
depending on caller:

- **Local (`commit-msg` hook):** changed files = `git diff --cached --name-only`;
  commit messages = the message being written (hook receives the message file path
  as `$1`) plus, for a `pre-push`-only fallback (see Open question below), the
  range of unpushed commits.
- **CI:** changed files = `git diff --name-only <merge-base>...<HEAD>`; commit
  messages = `git log <merge-base>..<HEAD>`.

Steps:

1. If no changed file matches the **feature-surface list** (below), pass
   trivially. Infra, tests, docs, and unrelated-module changes are exempt with no
   branch-naming convention required.
2. If the feature surface is touched, pass if **any** of:
   - a file under `docs/specs/` is also in the changed-files list, or
   - a commit message in range contains a line matching `Spec: docs/specs/<slug>.md`
     where `docs/specs/<slug>.md` actually exists in the repo, or
   - a commit message in range contains a line matching `Spec-Exempt: <reason>`
     (passes, but the script prints the reason so it's visible in CI logs / hook
     output, not silently swallowed).
3. Otherwise, fail with a message that:
   - lists exactly which changed files triggered the gate,
   - lists the available specs (from `docs/specs/README.md`'s index),
   - shows the exact trailer format to add (`Spec: docs/specs/<file>.md`) and the
     override format (`Spec-Exempt: <reason>`).

### Feature-surface list

A small, curated constant inside `scripts/check_spec_gate.sh` (not a full
glob→spec precision map — see Alternatives Considered):

- `astro_agent/routing/**`
- `astro_agent/llm/prompts/**`
- `astro_agent/agent/**`
- `astro_agent/intents.py`
- `astro_agent/chart/timing.py`
- `astro_agent/chart/dashas.py`

This list identifies *where user-facing behavior is defined*, not every file a
feature might touch. It is expected to grow slowly (roughly in step with new
specs being promoted from `docs/FUTURE_IMPROVEMENTS.md`), and updating it is a
one-line change reviewed like any other code change — not a per-file mapping
that has to track renames.

### Reference format

A commit message trailer line:

```
Spec: docs/specs/career-guidance.md
```

Rationale: this is git-native (works with any commit tool/agent), doesn't force
an edit to a spec whose content hasn't actually changed (unlike requiring the
spec file itself to be touched every time), and is trivially greppable in both
the local hook and CI without any host-specific API (works on any git remote,
not just GitHub).

### Optional Cursor companion hook

**Not yet implemented** — the authoritative git/CI layer (script + `commit-msg`
+ `pre-push` + CI job) shipped 2026-08-15; this layer is still additive/optional
per the design and untested against Cursor's actual hook runtime, so it was
left for a follow-up rather than shipped unverified.

`.cursor/hooks/spec-gate.sh` registered on `preToolUse`, matching `Write` and
`StrReplace` tool calls whose target path matches the feature-surface list.

- Tracks, per session (keyed by the hook's session/conversation id, written to a
  temp state file), which `docs/specs/*.md` files have been read via a matching
  `postToolUse` observer on `Read`.
- If the target file matches the feature surface and no spec has been read yet
  this session, returns `{"permission": "ask", "user_message": "...", "agent_message": "..."}`
  naming `docs/specs/README.md` and, where derivable, the likely matching spec.
- Never returns `"deny"` — the git/CI layer is the actual enforcement boundary;
  this layer only shortens the feedback loop for Cursor sessions specifically.
- Fails open (allows the edit) on any internal error, per the hooks skill's
  safety guidance.

## Alternatives considered

1. **Cursor-only `preToolUse` hard block.** Rejected as the primary mechanism —
   does nothing for non-Cursor tools or plain git usage, per the explicit
   constraint above. Kept as an optional additive layer instead.
2. **Precise glob→spec mapping file** (map every code path to its exact
   spec(s), enforce the exact match was read/touched). Rejected for now:
   `docs/specs/*.md` map to product themes, not files 1:1 (e.g.
   `timing-windows.md` spans `chart/timing.py`, `chart/dashas.py`, and pieces of
   `routing/`); a real-world case study of exactly this kind of anchor-mapping
   grew from a 57-line check to 220 lines just to handle renames. Revisit only if
   the coarse gate proves too imprecise in practice.
3. **Require the spec file itself to be modified in every touching commit**
   (the literal `sdd-harness` pattern). Rejected as the sole path: it would force
   meaningless edits to stable, already-correct specs. Kept as one of two ways to
   satisfy the gate (alongside the commit-message reference), not the only way.

## Out of scope

- Verifying an agent *actually understood* the spec content (no tool can check
  comprehension; this design only makes "spec was engaged with" mechanically
  checkable).
- Precise per-symbol spec↔code traceability (à la artgraph/spec-sync). Revisit
  if/when the corpus of specs and code grows enough to justify the tooling.
- Enforcing this for `docs/FUTURE_IMPROVEMENTS.md`-only backlog work (no code
  change, nothing to gate).

## Open question for the implementation plan

Local `commit-msg` hooks only see the message + currently staged diff, not prior
unpushed commits. Decide during planning whether to:
(a) also run the gate in `.githooks/pre-push` over the full unpushed commit range
(consistent with how `run_ci_checks.sh full` already runs there), or
(b) rely on CI alone to catch multi-commit cases and keep `commit-msg` as a
single-commit fast check.
**Resolved (a):** `.githooks/pre-push` reads the `<local-ref> <local-sha>
<remote-ref> <remote-sha>` lines git feeds it on stdin and calls
`scripts/check_spec_gate.sh range <remote-sha-or-merge-base> <local-sha>` per
updated ref before running the full quality gate, matching the existing
local/CI parity principle. A new remote ref (no `remote-sha`) falls back to
the merge-base with `origin/main`/`origin/master`; if that can't be
determined the local check is skipped for that ref and CI remains
authoritative.

## Success signal

- A PR that adds/changes behavior in the feature-surface list without a `Spec:`
  reference or a `docs/specs/` file change fails CI with a message naming the
  exact fix.
- The same PR, after adding a `Spec: docs/specs/<file>.md` trailer (or editing
  the relevant spec), passes.
- A docs-only, test-only, or infra-only PR is never blocked by this gate.
- Cursor users editing feature-surface files without having opened any spec see
  an in-session nudge before the git-level gate would catch it at commit time.
