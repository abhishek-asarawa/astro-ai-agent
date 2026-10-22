"""Tests for the ROADMAP.md → GitHub milestones/labels/issues sync."""

import subprocess
from dataclasses import dataclass, field

import pytest

import scripts.sync_roadmap_to_github as sync_module
from scripts.sync_roadmap_to_github import (
    LABELS,
    ROADMAP_PATH,
    GhClient,
    GhError,
    IssueRef,
    epic_title,
    heading_anchor,
    parse_roadmap,
    render_step_body,
    step_title,
    sync,
)


@pytest.fixture(scope="module")
def roadmap():
    return parse_roadmap(ROADMAP_PATH.read_text(encoding="utf-8"))


# --- Parsing the real roadmap ----------------------------------------------


def test_parses_six_milestones_in_order(roadmap):
    assert [m.id for m in roadmap] == ["M1", "M2", "M3", "M4", "M5", "M6"]
    assert roadmap[0].title == "M1 — MVP"


def test_parses_every_step_with_known_labels(roadmap):
    steps = [s for m in roadmap for s in m.steps]
    assert len(steps) == 57
    for step in steps:
        assert step.labels, f"{step.id} has no labels"
        unknown = set(step.labels) - set(LABELS)
        assert not unknown, f"{step.id} uses undefined labels {unknown}"


def test_step_ids_are_unique_and_belong_to_their_milestone(roadmap):
    ids = [s.id for m in roadmap for s in m.steps]
    assert len(ids) == len(set(ids))
    for milestone in roadmap:
        assert all(s.id.startswith(milestone.id + ".") for s in milestone.steps)


def test_closes_references_map_existing_issues_to_steps(roadmap):
    closes = {s.id: s.closes for m in roadmap for s in m.steps if s.closes}
    assert closes == {"M1.1": [6], "M1.2": [2, 3, 4, 5]}


def test_milestone_goal_and_exit_gate(roadmap):
    mvp = roadmap[0]
    assert mvp.goal.startswith("make the existing system trustworthy")
    assert len(mvp.exit_gate) == 6
    assert mvp.exit_gate[0] == "Issues #2–#6 closed"


# --- Rendering ----------------------------------------------------------------


def test_titles_carry_stable_id_prefix(roadmap):
    assert epic_title(roadmap[0]) == "[M1] MVP — epic"
    assert step_title(roadmap[0].steps[2]) == "[M1.3] Guidance policy spec + two-sided eval"


def test_heading_anchor_matches_github_slugs():
    assert heading_anchor("M1.3 Guidance policy spec + two-sided eval") == "m13-guidance-policy-spec--two-sided-eval"
    assert heading_anchor("M1 — MVP") == "m1--mvp"
    assert heading_anchor('M3.8 "Today for you" daily guidance') == "m38-today-for-you-daily-guidance"


def test_inline_todos_render_as_checklist(roadmap):
    provider_step = roadmap[1].steps[0]
    body = render_step_body(provider_step, "owner/repo")
    assert "- [ ] `LLMProvider` interface" in body
    assert "- [ ] Ollama and Claude implementations" in body
    assert "docs/ROADMAP.md#m21-model-provider-abstraction" in body


def test_checklist_todos_are_kept_verbatim(roadmap):
    body = render_step_body(roadmap[0].steps[1], "owner/repo")
    assert "- [ ] Agent loop applies the citation-integrity backstop" in body


# --- Sync against a fake GitHub ------------------------------------------------


@dataclass
class FakeGitHub:
    """In-memory stand-in for the GitHub API with the same surface as GhClient."""

    labels: set[str] = field(default_factory=set)
    milestones: dict[str, int] = field(default_factory=dict)
    issues: dict[int, IssueRef] = field(default_factory=dict)
    children: dict[int, set[int]] = field(default_factory=dict)
    writes: int = 0

    def __post_init__(self):
        for number in (2, 3, 4, 5, 6):
            self.issues[number] = IssueRef(number=number, id=1000 + number, title=f"bug {number}", milestone=None)

    def list_labels(self):
        return set(self.labels)

    def create_label(self, name, color, description):
        self.writes += 1
        self.labels.add(name)

    def list_milestones(self):
        return dict(self.milestones)

    def create_milestone(self, title, description):
        self.writes += 1
        number = len(self.milestones) + 1
        self.milestones[title] = number
        return number

    def list_issues(self):
        return list(self.issues.values())

    def create_issue(self, title, body, labels, milestone):
        self.writes += 1
        number = max(self.issues) + 1
        ref = IssueRef(number=number, id=1000 + number, title=title, milestone=milestone)
        self.issues[number] = ref
        return ref

    def set_milestone(self, number, milestone):
        self.writes += 1
        old = self.issues[number]
        self.issues[number] = IssueRef(number=number, id=old.id, title=old.title, milestone=milestone)

    def list_sub_issue_ids(self, parent):
        return set(self.children.get(parent, set()))

    def add_sub_issue(self, parent, child_id):
        self.writes += 1
        self.children.setdefault(parent, set()).add(child_id)


def _by_title_prefix(gh, prefix):
    return next(i for i in gh.issues.values() if i.title.startswith(prefix))


def test_first_sync_creates_full_hierarchy(roadmap):
    gh = FakeGitHub()
    sync(roadmap, gh, repo="owner/repo", apply=True, pause_s=0)

    assert set(LABELS) <= gh.labels
    assert len(gh.milestones) == 6
    assert len(gh.issues) == 5 + 6 + 57

    epic = _by_title_prefix(gh, "[M1] ")
    m1_steps = {_by_title_prefix(gh, f"[M1.{n}] ").id for n in range(1, 11)}
    assert gh.children[epic.number] == m1_steps

    step_1_2 = _by_title_prefix(gh, "[M1.2] ")
    assert gh.children[step_1_2.number] == {1002, 1003, 1004, 1005}
    assert gh.issues[2].milestone == gh.milestones["M1 — MVP"]


def test_second_sync_is_a_no_op(roadmap):
    gh = FakeGitHub()
    sync(roadmap, gh, repo="owner/repo", apply=True, pause_s=0)
    writes_after_first = gh.writes

    sync(roadmap, gh, repo="owner/repo", apply=True, pause_s=0)

    assert gh.writes == writes_after_first


def _fake_gh_run(outcomes, calls):
    """A subprocess.run stand-in that replays (returncode, stdout, stderr) outcomes in order."""

    def run(cmd, **kwargs):
        calls.append(cmd)
        code, out, err = outcomes.pop(0)
        return subprocess.CompletedProcess(cmd, code, stdout=out, stderr=err)

    return run


def test_gh_client_retries_reads_on_transient_network_errors(monkeypatch):
    calls = []
    outcomes = [(1, "", "net/http: TLS handshake timeout"), (0, '[[{"name": "area:rag"}]]', "")]
    monkeypatch.setattr(sync_module.subprocess, "run", _fake_gh_run(outcomes, calls))
    monkeypatch.setattr(sync_module, "RETRY_BACKOFF_S", 0)

    assert GhClient("owner/repo").list_labels() == {"area:rag"}
    assert len(calls) == 2


def test_gh_client_does_not_retry_writes(monkeypatch):
    calls = []
    outcomes = [(1, "", "read: connection reset by peer"), (0, '{"number": 1}', "")]
    monkeypatch.setattr(sync_module.subprocess, "run", _fake_gh_run(outcomes, calls))
    monkeypatch.setattr(sync_module, "RETRY_BACKOFF_S", 0)

    with pytest.raises(GhError):
        GhClient("owner/repo").create_milestone("M1 — MVP", "goal")
    assert len(calls) == 1


def test_dry_run_writes_nothing_and_reports_plan(roadmap):
    gh = FakeGitHub()
    actions = sync(roadmap, gh, repo="owner/repo", apply=False, pause_s=0)

    assert gh.writes == 0
    assert any("create milestone 'M1 — MVP'" in a for a in actions)
    assert any("create issue '[M1.3] Guidance policy spec + two-sided eval'" in a for a in actions)
