"""Tests for `scripts/board.py`.

Real-capture cases (blocked_leaf, assigned_leaf, a non-leaf, owner:agent
variants) come from `tests/fixtures/board_issues.json`'s `synthetic` key --
the real capture under both roots (checked 2026-09-19) has no blocked node,
no open+assigned leaf, no non-leaf and no owner:agent node at all, so those
cases could not be pulled from the live trees. See that fixture's own
`synthetic.description` for what is real and what is hand-appended.

What this does not establish
-----------------------------
- That `scripts/board.py` reads the *current* live trees correctly -- only
  that it classifies the shape captured on 2026-09-19 correctly. A schema
  change on GitHub's side (a renamed field, a different sub_issues shape) is
  invisible here; `fetch_tree`'s own gh calls are not exercised by any test.
- That `--fixture`'s JSON shape is the only shape `fetch_tree` can produce --
  it is the shape captured once, by hand, from the real payload.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import board  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "board_issues.json"
PYTHON = sys.executable


def load_fixture_data() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def synthetic(name: str) -> dict:
    return load_fixture_data()["synthetic"][name]


def classified(name: str) -> dict:
    return board.classify(synthetic(name))


# --------------------------------------------------------------------------
# frontier exclusions
# --------------------------------------------------------------------------


class TestFrontierExcludesNonReadyLeaves:
    def test_a_blocked_leaf_is_not_on_the_frontier(self):
        node = classified("blocked_leaf")
        assert node["leaf"] is True
        assert node["ready"] is False
        assert board.frontier([node]) == []

    def test_an_assigned_leaf_is_not_on_the_frontier(self):
        node = classified("assigned_leaf")
        assert node["leaf"] is True
        assert node["ready"] is False
        assert board.frontier([node]) == []

    def test_a_closed_leaf_is_not_on_the_frontier(self):
        # Real capture: #4 under the map is closed and assigned.
        data = load_fixture_data()
        raw = next(c for c in data["roots"]["3"]["children"] if c["number"] == 4)
        node = board.classify(raw)
        assert raw["state"] == "closed"
        assert node["ready"] is False
        assert board.frontier([node]) == []

    def test_a_non_leaf_is_not_on_the_frontier(self):
        tree = board.classify_tree(synthetic("non_leaf_with_open_child"))
        assert tree["leaf"] is False
        assert tree["ready"] is False
        all_nodes = board.flatten(tree)
        ready_numbers = {n["number"] for owner, model, nodes in board.frontier(all_nodes) for n in nodes}
        assert tree["number"] not in ready_numbers

    def test_an_open_unblocked_unassigned_leaf_is_ready(self):
        # Real capture: #76 under the map -- open, no assignee, no blocker,
        # sub_issues_summary.total == 0.
        data = load_fixture_data()
        raw = next(c for c in data["roots"]["3"]["children"] if c["number"] == 76)
        node = board.classify(raw)
        assert node["ready"] is True


# --------------------------------------------------------------------------
# owner inference
# --------------------------------------------------------------------------


class TestOwnerInference:
    def test_owner_is_inferred_joe_from_wayfinder_grilling(self):
        node = classified("grilling_infers_joe")
        assert node["owner"] == "joe"

    def test_explicit_owner_label_wins_over_wayfinder_inference(self):
        node = classified("explicit_owner_override")
        # Carries wayfinder:grilling (which alone would infer joe) AND owner:main.
        assert node["owner"] == "main"

    def test_wayfinder_task_does_not_infer_an_owner(self):
        # Real capture: #76 has label wayfinder:task and no owner: label.
        data = load_fixture_data()
        raw = next(c for c in data["roots"]["3"]["children"] if c["number"] == 76)
        node = board.classify(raw)
        assert node["type"] == "task"
        assert node["owner"] is None

    def test_a_node_with_no_type_or_wayfinder_label_is_untyped(self):
        # Real capture: #78 carries no labels at all.
        data = load_fixture_data()
        raw = next(c for c in data["roots"]["3"]["children"] if c["number"] == 78)
        node = board.classify(raw)
        assert raw["labels"] == []
        assert node["type"] == "untyped"

    def test_an_explicit_type_label_is_used_verbatim(self):
        # Real capture: #80 (backlog root) carries type:epic.
        data = load_fixture_data()
        node = board.classify(data["roots"]["80"])
        assert node["type"] == "epic"


# --------------------------------------------------------------------------
# warnings
# --------------------------------------------------------------------------


class TestWarnings:
    def test_an_agent_leaf_without_a_model_warns(self):
        node = classified("agent_leaf_no_model")
        lines = board.warnings([node], next_text=None)
        assert any("no model:" in ln for ln in lines)

    def test_an_agent_leaf_without_a_done_when_line_warns(self):
        node = classified("agent_leaf_no_done_when")
        lines = board.warnings([node], next_text=None)
        assert any("Done when" in ln for ln in lines)

    def test_an_agent_leaf_with_model_and_done_when_is_silent(self):
        node = classified("agent_leaf_clean")
        lines = board.warnings([node], next_text=None)
        assert lines == []

    def test_an_open_leaf_with_no_owner_warns(self):
        # Real capture: #78, no labels at all -> owner None.
        data = load_fixture_data()
        raw = next(c for c in data["roots"]["3"]["children"] if c["number"] == 78)
        node = board.classify(raw)
        assert node["owner"] is None
        lines = board.warnings([node], next_text=None)
        assert any("no owner" in ln for ln in lines)

    def test_an_inferred_joe_leaf_with_no_explicit_owner_label_is_fine(self):
        # CLAUDE.md-adjacent rule the build brief states explicitly: a
        # wayfinder:grilling/research/prototype leaf that infers owner joe,
        # with no explicit owner:joe label, is NOT a warning.
        node = classified("grilling_infers_joe")
        assert node["owner"] == "joe"
        lines = board.warnings([node], next_text=None)
        assert lines == []

    def test_a_closed_leaf_with_no_owner_does_not_warn(self):
        # The rule is "OPEN leaf with no owner" -- a closed one is history.
        data = load_fixture_data()
        raw = next(
            c
            for c in data["roots"]["3"]["children"]
            if c["state"] == "closed" and c["assignee"] is None
        )
        node = board.classify(raw)
        lines = board.warnings([node], next_text=None)
        assert lines == []


class TestStillOpenTicketWarning:
    NEXT_WITH_UNTICKETED_ITEM = (
        "## 2026-09-19 (test session)\n\n"
        "### Still open\n\n"
        "1. Carried parks: the shard probe (ADR 0158).\n"
        "2. Done -- live deployed, #79.\n"
    )
    NEXT_WITH_ONLY_MAP_NUMBER = (
        "## 2026-09-19 (test session)\n\n"
        "### Still open\n\n"
        "1. Ask Joe whether to keep it -- open a map #3 ticket.\n"
    )
    NEXT_ALL_TICKETED = (
        "## 2026-09-19 (test session)\n\n"
        "### Still open\n\n"
        "1. Done -- live deployed, #79.\n"
        "2. Another item, #26.\n"
    )

    def test_a_still_open_item_naming_no_ticket_warns(self):
        lines = board.warnings([], self.NEXT_WITH_UNTICKETED_ITEM)
        assert any("no ticket besides #3" in ln for ln in lines)
        assert any("shard probe" in ln for ln in lines)

    def test_an_item_naming_only_the_map_number_still_warns(self):
        lines = board.warnings([], self.NEXT_WITH_ONLY_MAP_NUMBER)
        assert any("no ticket besides #3" in ln for ln in lines)

    def test_an_item_with_a_real_ticket_does_not_warn(self):
        lines = board.warnings([], self.NEXT_ALL_TICKETED)
        assert lines == []

    def test_next_text_of_none_produces_no_still_open_warnings(self):
        # None means "could not be read" -- the caller reports that as
        # UNREADABLE separately; warnings() must not also complain.
        lines = board.warnings([], None)
        assert lines == []


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


class TestRenderShowsEveryRoot:
    def test_render_prints_every_roots_number_in_tree(self):
        data = load_fixture_data()
        trees = [board.classify_tree(data["roots"]["3"]), board.classify_tree(data["roots"]["80"])]
        all_nodes = [n for t in trees for n in board.flatten(t)]
        text = board.render(trees, all_nodes, warning_lines=[], unreadable_reasons=[])
        assert "root #3" in text
        assert "root #80" in text

    def test_verdict_line_reports_counts_and_exit_code(self):
        data = load_fixture_data()
        trees = [board.classify_tree(data["roots"]["3"]), board.classify_tree(data["roots"]["80"])]
        all_nodes = [n for t in trees for n in board.flatten(t)]
        warns = board.warnings(all_nodes, next_text=None)
        text = board.render(trees, all_nodes, warns, unreadable_reasons=[])
        ready_count = sum(1 for n in all_nodes if n["ready"])
        assert f"READY {ready_count}" in text
        assert f"WARNINGS {len(warns)}" in text
        assert "UNREADABLE 0" in text


# --------------------------------------------------------------------------
# exit codes, via the CLI (subprocess, exactly as a session would run it)
# --------------------------------------------------------------------------


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, str(ROOT / "scripts" / "board.py"), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        timeout=60,
    )


class TestExitCodes:
    def test_a_next_md_with_no_unticketed_items_and_no_agent_leaves_exits_clean(self, tmp_path):
        # Build a fixture with only the two clean real roots (no synthetic
        # cases -- those are what manufacture the warnings) and a NEXT.md
        # whose Still-open items are all ticketed.
        data = load_fixture_data()
        clean = {"roots": {"3": data["roots"]["3"], "80": data["roots"]["80"]}}
        # Strip the two real untyped/no-owner open leaves under #3 (#76, #78),
        # and the five open/no-owner epics under #80 -- give #80 itself an
        # owner so it (a now-childless leaf) is not itself a warning. This
        # test is about exit-code wiring, not about re-proving the warnings
        # tests above.
        clean["roots"]["3"] = dict(clean["roots"]["3"])
        clean["roots"]["3"]["children"] = [
            c for c in clean["roots"]["3"]["children"] if c["number"] not in (76, 78)
        ]
        clean["roots"]["80"] = dict(clean["roots"]["80"])
        clean["roots"]["80"]["children"] = []
        clean["roots"]["80"]["labels"] = clean["roots"]["80"]["labels"] + [{"name": "owner:joe"}]
        fixture_path = tmp_path / "clean.json"
        fixture_path.write_text(json.dumps(clean), encoding="utf-8")
        next_path = tmp_path / "NEXT.md"
        next_path.write_text(
            "## 2026-09-19 (test)\n\n### Still open\n\n1. Everything is ticketed, #79.\n",
            encoding="utf-8",
        )
        result = run_cli("--fixture", str(fixture_path), "--next", str(next_path))
        assert result.returncode == 0, result.stdout + result.stderr
        assert "VERDICT" in result.stdout
        assert "-> exit 0" in result.stdout

    def test_warnings_present_exits_1(self):
        # The committed fixture's real #76/#78 (open leaves, no owner) and
        # NEXT.md's own unticketed Still-open items guarantee at least one
        # warning without needing the synthetic cases.
        result = run_cli("--fixture", str(FIXTURE))
        assert result.returncode == 1, result.stdout + result.stderr
        assert "-> exit 1" in result.stdout

    def test_a_missing_fixture_is_unreadable_and_exits_3(self):
        result = run_cli("--fixture", "this-file-does-not-exist.json")
        assert result.returncode == 3, result.stdout + result.stderr
        assert "UNREADABLE" in result.stdout
        assert "-> exit 3" in result.stdout

    def test_a_missing_next_md_is_unreadable_and_exits_3(self, tmp_path):
        result = run_cli("--fixture", str(FIXTURE), "--next", str(tmp_path / "nope.md"))
        assert result.returncode == 3, result.stdout + result.stderr
        assert "UNREADABLE" in result.stdout

    def test_undecodable_json_is_unreadable_and_exits_3(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        result = run_cli("--fixture", str(bad))
        assert result.returncode == 3, result.stdout + result.stderr
        assert "UNREADABLE" in result.stdout

    def test_json_flag_emits_parseable_json_and_the_same_exit_code(self):
        result = run_cli("--fixture", str(FIXTURE), "--json")
        assert result.returncode == 1, result.stdout + result.stderr
        parsed = json.loads(result.stdout)
        assert isinstance(parsed, list)
        assert {t["number"] for t in parsed} == {3, 80}


# --------------------------------------------------------------------------
# the parsers this file re-implements from
# tests/test_a_question_for_joe_has_a_ticket.py -- kept in sync by hand; see
# board.py's own module docstring for why importing that test is refused.
# --------------------------------------------------------------------------


class TestReimplementedNextMdParsers:
    def test_names_a_ticket_refuses_the_map_alone(self):
        assert board.names_a_ticket("see map #3") is False
        assert board.names_a_ticket("see #3 and #41") is True

    def test_latest_entry_stops_at_a_rule(self):
        text = "## 2026-09-19 a\nbody\n---\n## 2026-09-18 b\nolder\n"
        entry = board.latest_entry(text)
        assert "2026-09-19" in entry
        assert "2026-09-18" not in entry

    def test_still_open_items_keeps_continuation_lines(self):
        entry = "## 2026-09-19 x\n### Still open\n1. first line\n   continued\n2. second\n"
        items = board.still_open_items(entry)
        assert len(items) == 2
        assert "continued" in items[0]
