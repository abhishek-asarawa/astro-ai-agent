#!/usr/bin/env bash
# Spec-driven development gate. Single source of truth, called identically by
# .githooks/commit-msg (single commit, fast local check), .githooks/pre-push
# (full unpushed range), and the CI spec-gate job (merge-base..HEAD on PRs).
# Mirrors the scripts/run_ci_checks.sh shared-script pattern so the gate
# cannot drift between local and CI.
#
# Usage:
#   scripts/check_spec_gate.sh commit-msg <commit-msg-file>
#   scripts/check_spec_gate.sh range <base-ref> <head-ref>
#
# See docs/superpowers/specs/2026-08-06-spec-driven-enforcement-design.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Feature-surface list: where user-facing behavior is defined, not every file
# a feature might touch. Grows in step with specs promoted from
# docs/FUTURE_IMPROVEMENTS.md; update alongside a spec, reviewed like any
# other code change (see "Feature-surface list" in the design doc).
FEATURE_SURFACE_PATTERNS='
astro_agent/routing/
astro_agent/llm/prompts/
astro_agent/agent/
astro_agent/intents.py
astro_agent/chart/timing.py
astro_agent/chart/dashas.py
'

die() {
    printf '\n[check_spec_gate] %s\n' "$1" >&2
    exit 1
}

step() {
    printf '[check_spec_gate] %s\n' "$1"
}

matches_feature_surface() {
    local path="$1" pattern
    while IFS= read -r pattern; do
        [ -z "$pattern" ] && continue
        case "$path" in
            "$pattern"*) return 0 ;;
        esac
    done <<< "$FEATURE_SURFACE_PATTERNS"
    return 1
}

# $1 = newline-separated changed files -> prints the subset matching the
# feature surface, one per line.
triggered_files() {
    local files="$1" f
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        if matches_feature_surface "$f"; then
            printf '%s\n' "$f"
        fi
    done <<< "$files"
}

touches_spec_dir() {
    local files="$1" f
    while IFS= read -r f; do
        case "$f" in
            docs/specs/*.md) return 0 ;;
        esac
    done <<< "$files"
    return 1
}

# $1 = commit message text -> prints the first referenced spec whose file
# actually exists, exit 1 if none found.
find_valid_spec_trailer() {
    local text="$1" line spec
    while IFS= read -r line; do
        line="${line%$'\r'}"
        case "$line" in
            Spec:\ docs/specs/*.md)
                spec="${line#Spec: }"
                spec="${spec%"${spec##*[![:space:]]}"}" # trim trailing whitespace
                if [ -f "$spec" ]; then
                    printf '%s\n' "$spec"
                    return 0
                fi
                ;;
        esac
    done <<< "$text"
    return 1
}

# $1 = commit message text -> prints the first exemption reason, exit 1 if none.
find_exempt_trailer() {
    local text="$1" line
    while IFS= read -r line; do
        line="${line%$'\r'}"
        case "$line" in
            Spec-Exempt:\ *)
                printf '%s\n' "${line#Spec-Exempt: }"
                return 0
                ;;
        esac
    done <<< "$text"
    return 1
}

list_available_specs() {
    local f
    for f in docs/specs/*.md; do
        [ "$(basename "$f")" = "README.md" ] && continue
        printf '  - %s\n' "$f"
    done
}

fail_with_help() {
    local triggered="$1"
    {
        printf '\n[check_spec_gate] Feature-surface files changed without a spec reference:\n'
        printf '%s\n' "$triggered" | sed 's/^/  - /'
        printf '\nFix one of:\n'
        printf '  1. Add a spec reference trailer to a commit message in this change:\n'
        printf '       Spec: docs/specs/<file>.md\n'
        printf '  2. Touch the matching file under docs/specs/ in this change.\n'
        printf '  3. If genuinely exempt, explain why:\n'
        printf '       Spec-Exempt: <reason>\n'
        printf '\nAvailable specs:\n'
        list_available_specs
    } >&2
    exit 1
}

# $1 = newline-separated changed files, $2 = commit message text (may span
# multiple commits).
run_gate() {
    local changed_files="$1" commit_text="$2" triggered

    triggered="$(triggered_files "$changed_files")"

    if [ -z "$triggered" ]; then
        step "No feature-surface files changed; gate passes trivially."
        return 0
    fi

    if touches_spec_dir "$changed_files"; then
        step "docs/specs/ file changed alongside feature surface; gate passes."
        return 0
    fi

    local spec_ref
    if spec_ref="$(find_valid_spec_trailer "$commit_text")"; then
        step "Spec reference '$spec_ref' found; gate passes."
        return 0
    fi

    local exempt_reason
    if exempt_reason="$(find_exempt_trailer "$commit_text")"; then
        step "Spec-Exempt: ${exempt_reason}"
        return 0
    fi

    fail_with_help "$triggered"
}

MODE="${1:-}"
case "$MODE" in
    commit-msg)
        MSG_FILE="${2:?usage: check_spec_gate.sh commit-msg <commit-msg-file>}"
        CHANGED="$(git diff --cached --name-only)"
        COMMIT_TEXT="$(cat "$MSG_FILE")"
        run_gate "$CHANGED" "$COMMIT_TEXT"
        ;;
    range)
        BASE="${2:?usage: check_spec_gate.sh range <base-ref> <head-ref>}"
        HEAD_REF="${3:-HEAD}"
        CHANGED="$(git diff --name-only "$BASE...$HEAD_REF")"
        MERGE_BASE="$(git merge-base "$BASE" "$HEAD_REF")"
        COMMIT_TEXT="$(git log "$MERGE_BASE..$HEAD_REF" --format=%B)"
        run_gate "$CHANGED" "$COMMIT_TEXT"
        ;;
    *)
        die "Unknown mode '$MODE' (expected: commit-msg|range)"
        ;;
esac

step "spec gate passed."
