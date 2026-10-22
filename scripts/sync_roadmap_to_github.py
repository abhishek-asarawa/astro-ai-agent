#!/usr/bin/env python3
"""Sync docs/ROADMAP.md into GitHub milestones, labels, epics, and step issues.

The roadmap is the source of truth for scope and order (ROADMAP §8). This
script mirrors it into GitHub so work can be tracked there:

1. Every label in ``LABELS`` exists.
2. Each roadmap milestone (``### M1 — MVP``) has a GitHub milestone.
3. Each milestone has one epic issue (``[M1] MVP — epic``) whose body holds
   the goal and the exit-gate checklist.
4. Each step (``#### M1.3 …``) has an issue (``[M1.3] …``) attached as a
   sub-issue of its epic. Inline ``Todos:`` text is rendered as a checklist.
5. Existing issues a step closes (``closes #N`` in its todos) get the
   step's milestone and become sub-issues of the step.

It is idempotent: items are matched by milestone title and by the ``[M1]`` /
``[M1.3]`` issue-title prefix, only missing items are created, and existing
issue bodies are never rewritten (issues own todo progress). The default is
a dry run; pass ``--apply`` to write. Talks to GitHub through the ``gh`` CLI,
so it uses whatever auth ``gh`` already has.

Usage:
    python scripts/sync_roadmap_to_github.py [--apply] [--repo owner/name]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[1]
ROADMAP_PATH = REPO_ROOT / "docs" / "ROADMAP.md"

# GitHub's secondary rate limits reject bursts of content-creating requests;
# its guidance is to leave at least a second between POSTs.
CREATE_PAUSE_S = 1.0

# Reads are retried because flaky networks drop TLS handshakes and connections
# mid-run. Writes are not: a write whose response was lost may have landed, and
# the next run's title-prefix matching picks it up instead of duplicating it.
READ_ATTEMPTS = 3
RETRY_BACKOFF_S = 2.0

AREA_COLOR = "c5def5"
LABELS: dict[str, tuple[str, str]] = {
    "area:rag": (AREA_COLOR, "Retrieval, ranking, citations"),
    "area:chart": (AREA_COLOR, "Chart math: dashas, transits, divisional charts, matching"),
    "area:agent": (AREA_COLOR, "Agent loop / LangGraph orchestration and tools"),
    "area:api": (AREA_COLOR, "FastAPI backend and service contracts"),
    "area:ui": (AREA_COLOR, "Web UI and Streamlit dev console"),
    "area:corpus": (AREA_COLOR, "Book acquisition, OCR, manifests, ingestion"),
    "area:evals": (AREA_COLOR, "Golden sets and evaluation gates"),
    "area:infra": (AREA_COLOR, "CI, hosting, observability"),
    "area:i18n": (AREA_COLOR, "Hindi / Hinglish and localization"),
    "area:safety": (AREA_COLOR, "Guidance policy, privacy, security"),
    "area:docs": (AREA_COLOR, "Documentation"),
    "area:llm": (AREA_COLOR, "Model providers, prompts, generation"),
    "area:storage": (AREA_COLOR, "Profiles, conversations, persistence"),
    "area:knowledge": (AREA_COLOR, "Structured astrology knowledge base"),
    "type:epic": ("5319e7", "Roadmap milestone epic"),
    "type:feature": ("a2eeef", "New capability"),
    "type:bug": ("d73a4a", "Something is broken"),
    "type:chore": ("fef2c0", "Maintenance, cleanup, tooling"),
    "type:spec": ("0e8a16", "Spec or design work comes first"),
    "type:spike": ("fbca04", "Time-boxed investigation; output is a decision"),
    "blocked": ("b60205", "Waiting on another step or an external dependency"),
}

_MILESTONE_RE = re.compile(r"^### (M\d+) — (.+)$")
_STEP_RE = re.compile(r"^#### (M\d+\.\d+) (.+)$")
_EXIT_GATE_RE = re.compile(r"^\*\*M\d+ exit gate\*\*$")
_CHECKBOX_RE = re.compile(r"^- \[[ xX]\] (.+)$")
_CLOSES_RE = re.compile(r"closes #(\d+)")
_INLINE_TODOS_RE = re.compile(r"^- \*\*Todos:\*\* (.+)$")
_MILESTONES_SECTION = "## 7. Milestones"
_AFTER_MILESTONES_PREFIX = "## 8."


@dataclass
class Step:
    """One roadmap step (``#### M1.3 Title``) and its markdown body."""

    id: str
    title: str
    body: str = ""
    labels: list[str] = field(default_factory=list)
    closes: list[int] = field(default_factory=list)


@dataclass
class Milestone:
    """One roadmap milestone (``### M1 — Name``) with its goal, steps, and exit gate."""

    id: str
    name: str
    goal: str = ""
    steps: list[Step] = field(default_factory=list)
    exit_gate: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return f"{self.id} — {self.name}"


@dataclass(frozen=True)
class IssueRef:
    """The GitHub issue fields the sync needs (``id`` is what the sub-issue API takes)."""

    number: int
    id: int
    title: str
    milestone: int | None


class GitHubApi(Protocol):
    """GitHub operations the sync uses; ``GhClient`` implements them over ``gh api``."""

    def list_labels(self) -> set[str]: ...
    def create_label(self, name: str, color: str, description: str) -> None: ...
    def list_milestones(self) -> dict[str, int]: ...
    def create_milestone(self, title: str, description: str) -> int: ...
    def list_issues(self) -> list[IssueRef]: ...
    def create_issue(self, title: str, body: str, labels: list[str], milestone: int | None) -> IssueRef: ...
    def set_milestone(self, number: int, milestone: int) -> None: ...
    def list_sub_issue_ids(self, parent: int) -> set[int]: ...
    def add_sub_issue(self, parent: int, child_id: int) -> None: ...


# --- Parsing -------------------------------------------------------------------


def parse_roadmap(text: str) -> list[Milestone]:
    """Parse the milestones section of ROADMAP.md into milestones and steps."""
    milestones: list[Milestone] = []
    step: Step | None = None
    mode = "skip"
    body_lines: list[str] = []

    def finish_step() -> None:
        if step is not None:
            step.body = "\n".join(body_lines).strip()
            step.labels = _parse_labels(step.body)
            step.closes = list(dict.fromkeys(int(n) for n in _CLOSES_RE.findall(step.body)))

    in_section = False
    for line in text.splitlines():
        if line.startswith(_MILESTONES_SECTION):
            in_section = True
            continue
        if not in_section:
            continue
        if line.startswith(_AFTER_MILESTONES_PREFIX):
            break

        if match := _MILESTONE_RE.match(line):
            finish_step()
            step = None
            milestones.append(Milestone(id=match.group(1), name=match.group(2).strip()))
            mode = "intro"
        elif match := _STEP_RE.match(line):
            finish_step()
            step = Step(id=match.group(1), title=match.group(2).strip())
            milestones[-1].steps.append(step)
            body_lines = []
            mode = "step"
        elif _EXIT_GATE_RE.match(line):
            finish_step()
            step = None
            mode = "exit_gate"
        elif line.strip() == "---":
            finish_step()
            step = None
            mode = "skip"
        elif mode == "intro" and (line.startswith("**Goal:**") or (milestones[-1].goal and line.strip())):
            goal_part = line.removeprefix("**Goal:**").strip()
            milestones[-1].goal = f"{milestones[-1].goal} {goal_part}".strip()
        elif mode == "intro" and not line.strip() and milestones[-1].goal:
            mode = "skip"
        elif mode == "step":
            body_lines.append(line)
        elif mode == "exit_gate" and (match := _CHECKBOX_RE.match(line)):
            milestones[-1].exit_gate.append(match.group(1).strip())
    finish_step()
    return milestones


def _parse_labels(body: str) -> list[str]:
    """Labels are the backticked names after ``**Labels:**``, up to ``**Depends on:**``."""
    for line in body.splitlines():
        if "**Labels:**" in line:
            segment = line.split("**Labels:**", 1)[1].split("**Depends on:**", 1)[0]
            return re.findall(r"`([^`]+)`", segment)
    return []


# --- Rendering -----------------------------------------------------------------


def heading_anchor(heading: str) -> str:
    """GitHub's markdown heading slug: lowercase, drop punctuation, spaces → hyphens."""
    kept = re.sub(r"[^\w\- ]", "", heading.lower())
    return kept.replace(" ", "-")


def epic_title(milestone: Milestone) -> str:
    return f"[{milestone.id}] {milestone.name} — epic"


def step_title(step: Step) -> str:
    return f"[{step.id}] {step.title}"


def _roadmap_url(repo: str, heading: str) -> str:
    return f"https://github.com/{repo}/blob/main/docs/ROADMAP.md#{heading_anchor(heading)}"


def milestone_description(milestone: Milestone) -> str:
    gate = "; ".join(milestone.exit_gate)
    return f"{milestone.goal}\n\nExit gate: {gate}"


def render_epic_body(milestone: Milestone, repo: str) -> str:
    """Epic body: goal, roadmap link, and the exit gate as a checklist."""
    gate = "\n".join(f"- [ ] {item}" for item in milestone.exit_gate)
    link = _roadmap_url(repo, milestone.title)
    return (
        f"Epic for roadmap milestone **[{milestone.title}]({link})**. "
        "Steps are attached as sub-issues.\n\n"
        f"**Goal:** {milestone.goal}\n\n"
        "## Exit gate\n\n"
        "Close this epic only when every item is verified, with evidence "
        "(eval numbers, test runs, links) posted here (ROADMAP §6.3).\n\n"
        f"{gate}\n"
    )


def render_step_body(step: Step, repo: str) -> str:
    """Step body: roadmap link plus the step's markdown, inline todos turned into a checklist."""
    link = _roadmap_url(repo, f"{step.id} {step.title}")
    lines = [_expand_inline_todos(line) for line in step.body.splitlines()]
    return (
        f"Roadmap step **[{step.id}]({link})**. The roadmap is authoritative for "
        "scope and order; track progress by ticking the todos here.\n\n" + "\n".join(lines) + "\n"
    )


def _expand_inline_todos(line: str) -> str:
    """Turn ``- **Todos:** a; b; c.`` into a nested checklist; leave other lines alone.

    A todo line that ends with ``:`` introduces its own nested list, so it is kept verbatim.
    """
    match = _INLINE_TODOS_RE.match(line)
    if not match or match.group(1).rstrip().endswith(":"):
        return line
    items = [item.strip().rstrip(".") for item in match.group(1).split("; ") if item.strip()]
    return "- **Todos:**\n" + "\n".join(f"  - [ ] {item}" for item in items)


# --- Sync ----------------------------------------------------------------------


def sync(
    roadmap: list[Milestone],
    gh: GitHubApi,
    *,
    repo: str,
    apply: bool,
    pause_s: float = CREATE_PAUSE_S,
) -> list[str]:
    """Create whatever the roadmap needs that GitHub lacks; return the actions taken or planned."""
    actions: list[str] = []

    def pause() -> None:
        if apply and pause_s:
            time.sleep(pause_s)

    existing_labels = gh.list_labels()
    for name, (color, description) in LABELS.items():
        if name not in existing_labels:
            actions.append(f"create label '{name}'")
            if apply:
                gh.create_label(name, color, description)

    milestones = gh.list_milestones()
    issues = gh.list_issues()
    by_number = {issue.number: issue for issue in issues}

    def find(prefix: str) -> IssueRef | None:
        return next((issue for issue in issues if issue.title.startswith(prefix)), None)

    def create(title: str, body: str, labels: list[str], milestone: int | None) -> IssueRef | None:
        actions.append(f"create issue '{title}'")
        if not apply:
            return None
        ref = gh.create_issue(title, body, labels, milestone)
        issues.append(ref)
        pause()
        return ref

    for milestone in roadmap:
        ms_number = milestones.get(milestone.title)
        if ms_number is None:
            actions.append(f"create milestone '{milestone.title}'")
            if apply:
                ms_number = gh.create_milestone(milestone.title, milestone_description(milestone))
                pause()

        epic = find(f"[{milestone.id}] ") or create(
            epic_title(milestone), render_epic_body(milestone, repo), ["type:epic"], ms_number
        )
        epic_children = gh.list_sub_issue_ids(epic.number) if epic else set()

        for step in milestone.steps:
            ref = find(f"[{step.id}] ") or create(
                step_title(step), render_step_body(step, repo), step.labels, ms_number
            )
            if ref is None or ref.id not in epic_children:
                actions.append(f"attach '{step_title(step)}' under '{epic_title(milestone)}'")
                if apply and epic is not None and ref is not None:
                    gh.add_sub_issue(epic.number, ref.id)

            step_children = gh.list_sub_issue_ids(ref.number) if ref else set()
            for number in step.closes:
                existing = by_number.get(number)
                if existing is None:
                    actions.append(f"skip #{number}: referenced by {step.id} but not found")
                    continue
                if existing.milestone is None:
                    actions.append(f"set milestone '{milestone.title}' on #{number}")
                    if apply and ms_number is not None:
                        gh.set_milestone(number, ms_number)
                if existing.id not in step_children:
                    actions.append(f"attach #{number} under '{step_title(step)}'")
                    if apply and ref is not None:
                        gh.add_sub_issue(ref.number, existing.id)
    return actions


# --- GitHub over the gh CLI ----------------------------------------------------


class GhError(RuntimeError):
    """A ``gh api`` call failed."""


class GhClient:
    """``GitHubApi`` implemented with ``gh api`` so the user's existing gh auth is reused."""

    def __init__(self, repo: str) -> None:
        self.repo = repo

    def _api(self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
        cmd = ["gh", "api", "--method", method, "-H", "X-GitHub-Api-Version: 2022-11-28", f"repos/{self.repo}/{path}"]
        paginate = method == "GET"
        if paginate:
            cmd += ["--paginate", "--slurp"]
        if payload is not None:
            cmd += ["--input", "-"]
        attempts = READ_ATTEMPTS if method == "GET" else 1
        for attempt in range(1, attempts + 1):
            result = subprocess.run(
                cmd,
                input=json.dumps(payload) if payload is not None else None,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                break
            if attempt < attempts:
                time.sleep(RETRY_BACKOFF_S * attempt)
        else:
            raise GhError(f"gh api {method} {path} failed: {result.stderr.strip()}")
        data = json.loads(result.stdout) if result.stdout.strip() else None
        if paginate:
            return [item for page in data or [] for item in page]
        return data

    def list_labels(self) -> set[str]:
        return {label["name"] for label in self._api("labels?per_page=100")}

    def create_label(self, name: str, color: str, description: str) -> None:
        self._api("labels", method="POST", payload={"name": name, "color": color, "description": description})

    def list_milestones(self) -> dict[str, int]:
        return {m["title"]: m["number"] for m in self._api("milestones?state=all&per_page=100")}

    def create_milestone(self, title: str, description: str) -> int:
        return self._api("milestones", method="POST", payload={"title": title, "description": description})["number"]

    def list_issues(self) -> list[IssueRef]:
        return [_issue_ref(item) for item in self._api("issues?state=all&per_page=100") if "pull_request" not in item]

    def create_issue(self, title: str, body: str, labels: list[str], milestone: int | None) -> IssueRef:
        payload: dict[str, Any] = {"title": title, "body": body, "labels": labels}
        if milestone is not None:
            payload["milestone"] = milestone
        return _issue_ref(self._api("issues", method="POST", payload=payload))

    def set_milestone(self, number: int, milestone: int) -> None:
        self._api(f"issues/{number}", method="PATCH", payload={"milestone": milestone})

    def list_sub_issue_ids(self, parent: int) -> set[int]:
        return {item["id"] for item in self._api(f"issues/{parent}/sub_issues?per_page=100")}

    def add_sub_issue(self, parent: int, child_id: int) -> None:
        self._api(f"issues/{parent}/sub_issues", method="POST", payload={"sub_issue_id": child_id})


def _issue_ref(item: dict[str, Any]) -> IssueRef:
    milestone = item.get("milestone")
    return IssueRef(
        number=item["number"],
        id=item["id"],
        title=item["title"],
        milestone=milestone["number"] if milestone else None,
    )


def _current_repo() -> str:
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        raise GhError(f"could not detect the GitHub repo: {result.stderr.strip()}")
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write to GitHub (default: dry run)")
    parser.add_argument("--repo", help="owner/name (default: the repo gh resolves from this checkout)")
    parser.add_argument("--roadmap", type=Path, default=ROADMAP_PATH, help="path to ROADMAP.md")
    args = parser.parse_args(argv)

    roadmap = parse_roadmap(args.roadmap.read_text(encoding="utf-8"))
    repo = args.repo or _current_repo()
    step_count = sum(len(m.steps) for m in roadmap)
    print(f"Roadmap: {len(roadmap)} milestones, {step_count} steps → {repo} ({'apply' if args.apply else 'dry run'})")

    actions = sync(roadmap, GhClient(repo), repo=repo, apply=args.apply)
    for action in actions:
        print(f"  {'' if args.apply else '[dry run] '}{action}")
    print(f"{len(actions)} action(s); {'done' if args.apply else 're-run with --apply to write'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
