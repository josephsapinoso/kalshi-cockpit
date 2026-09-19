"""A question for Joe carries its ticket number, or this test refuses the handoff.

The decay this guards against -- tasks/lessons.md 2026-09-16 (eighth)
------------------------------------------------------------------------
The twenty-second session measured the sharp-anchor rate and filed, as open
item 1 of `tasks/NEXT.md`:

    The NCAAF anchor question is for Joe. Nothing to build until he answers.

One session later that line read "run `sharp-anchor-census` Saturday". The
session after inherited the new wording and re-filed it. Nobody deleted the
question; it was **replaced by the nearest thing a session could execute
alone**, because re-running the instrument that raised a question always
looks like progress on it. Meanwhile map issue #3 -- the only queue Joe
answers from -- had 37 sub-issues and every one was closed. The
infrastructure queue refills itself; the decision queue refills only when
somebody writes a ticket.

The rule (CLAUDE.md workflow step 7): **a question for Joe is a ticket, not a
line.** It is written in the handoff as

    Question for Joe: <one sentence> -- #NN

where `#NN` is a sub-issue of the map, opened in the same session.

What this test establishes
--------------------------
1. Every `Question for Joe` marker in the LATEST `tasks/NEXT.md` entry, and in
   every `docs/measurements/*.md` dated on or after the rule, names an issue
   number on the same line -- and `#3` does not count, because `#3` is the map
   and naming the map is how "I will open one later" gets written.
2. No item in the latest entry's **Still open** list hands a decision to Joe
   in the looser wordings that actually decayed -- *for Joe*, *Joe's call*,
   *until he answers*, *ask Joe* -- without a ticket number in that item.
   The Still open list is scoped because it is the exact place the rewrite
   happens: it is the list the next session copies forward.
3. The parsers find the entry and the list. A guard over an empty slice
   passes vacuously and reads as green, which is the failure mode
   `test_session_files_are_readable.py` exists for one file over.

What it does not establish
--------------------------
- That every question for Joe is *worded* in a way the patterns catch. A
  session that writes "someone should decide whether ..." slips past. The
  canonical marker is the contract; the loose patterns are the wordings this
  repo has actually used. Add a wording here the day it decays.
- That the ticket named is open, is a sub-issue of the map, or asks the
  question the line claims. `gh` answers that; this file is offline.
- Anything about entries older than the latest one, or about measurement
  docs dated before the rule. Those are a record and are not edited to fit a
  rule written after them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NEXT = ROOT / "tasks" / "NEXT.md"
MEASUREMENTS = ROOT / "docs" / "measurements"

# Measurement docs are named YYYY-MM-DD-<slug>.md. Docs dated on or after this
# day are inside the rule; earlier ones are a record and are left alone.
RULE_DATE = "2026-09-17"
MAP_ISSUE = 3

MARKER = re.compile(r"question for joe\s*:", re.IGNORECASE)
TICKET = re.compile(r"#(\d+)\b")
# The wordings that decayed, verbatim from the record. "JOE ONLY" (an
# instruction that a session must not act) and "built for Joe" are not here on
# purpose: they hand him nothing to decide.
ASKS_JOE = re.compile(
    r"("
    r"questions? (is |are )?for joe"
    r"|joe'?s (call|decision|question)"
    r"|ask joe"
    r"|(for|to) joe to (answer|decide|rule|say)"
    r"|until (he|joe) answers"
    r"|joe (has|needs) to (answer|decide|rule)"
    r")",
    re.IGNORECASE,
)
ENTRY_HEADING = re.compile(r"^## \d{4}-\d{2}-\d{2}")
STILL_OPEN_HEADING = re.compile(r"^### Still open", re.IGNORECASE)
ITEM_START = re.compile(r"^\d+\.\s")


def names_a_ticket(text: str) -> bool:
    """True when `text` cites an issue number that is not the map itself."""
    return any(int(n) != MAP_ISSUE for n in TICKET.findall(text))


def latest_entry(text: str) -> str:
    """The first dated `## YYYY-MM-DD` section, up to the next `---` rule."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ENTRY_HEADING.match(ln)), None)
    if start is None:
        return ""
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() == "---"), len(lines))
    return "\n".join(lines[start:end])


def still_open_items(entry: str) -> list[str]:
    """The numbered items under `### Still open`, each with its continuation lines."""
    lines = entry.splitlines()
    start = next((i for i, ln in enumerate(lines) if STILL_OPEN_HEADING.match(ln)), None)
    if start is None:
        return []
    items: list[list[str]] = []
    for ln in lines[start + 1 :]:
        if ln.startswith("#"):
            break
        if ITEM_START.match(ln):
            items.append([ln])
        elif items and ln.strip():
            items[-1].append(ln)
    return ["\n".join(item) for item in items]


def markers_without_a_ticket(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if MARKER.search(ln) and not names_a_ticket(ln)]


def open_items_asking_joe_without_a_ticket(entry: str) -> list[str]:
    return [item for item in still_open_items(entry) if ASKS_JOE.search(item) and not names_a_ticket(item)]


def open_items_without_a_ticket(entry: str) -> list[str]:
    """Every Still open item, not only the ones that ask Joe -- one queue, 2026-09-19."""
    return [item for item in still_open_items(entry) if not names_a_ticket(item)]


def measurement_docs_inside_the_rule() -> list[Path]:
    return sorted(p for p in MEASUREMENTS.glob("*.md") if p.name[:10] >= RULE_DATE)


class TestTheMarkerNamesATicket:
    def test_a_marker_with_no_number_is_refused(self):
        assert markers_without_a_ticket("Question for Joe: is 30% anchored worth showing?") == [
            "Question for Joe: is 30% anchored worth showing?"
        ]

    def test_a_marker_with_a_number_passes(self):
        assert markers_without_a_ticket("**Question for Joe:** the anchor rate — #41") == []

    def test_the_map_itself_is_not_a_ticket(self):
        # "#3" is how "I will open one on the map later" gets written.
        assert markers_without_a_ticket("Question for Joe: anchor rate — map #3") == [
            "Question for Joe: anchor rate — map #3"
        ]

    def test_the_number_must_be_on_the_marker_line(self):
        text = "Question for Joe: anchor rate.\nSee #41 above."
        assert markers_without_a_ticket(text) == ["Question for Joe: anchor rate."]

    def test_a_bare_mention_of_the_phrase_is_not_a_marker(self):
        # Prose that talks ABOUT questions for Joe (this rule, the lesson) has
        # no colon and is not a claim to have raised one.
        assert markers_without_a_ticket("a measurement that raises a question for Joe opens a ticket") == []


class TestTheOpenListCannotAskJoeWithoutATicket:
    ENTRY = (
        "## 2026-09-16 (n-th session) — heading\n\n"
        "Prose that quotes the old line: *the question is for Joe* — history, not an item.\n\n"
        "### Still open, in order\n\n"
        "1. **The NCAAF anchor question is for Joe.** Nothing to build\n"
        "   until he answers; the flag is already on the row.\n"
        "2. **One \"Price on Kalshi\" tap on the props card — JOE ONLY.** A session must not do it.\n"
        "3. **Which clock the kickoff column tells — Joe's call, #26.**\n"
        "4. Carried parks: the shard probe (ADR 0158).\n"
    )

    def test_an_item_that_asks_joe_with_no_ticket_is_refused(self):
        flagged = open_items_asking_joe_without_a_ticket(self.ENTRY)
        assert len(flagged) == 1
        assert flagged[0].startswith("1. **The NCAAF anchor question is for Joe.**")
        assert "until he answers" in flagged[0], "continuation lines belong to the item"

    def test_an_item_with_a_ticket_passes(self):
        assert not any("Joe's call, #26" in item for item in open_items_asking_joe_without_a_ticket(self.ENTRY))

    def test_an_instruction_to_a_session_is_not_a_question(self):
        assert not any("JOE ONLY" in item for item in open_items_asking_joe_without_a_ticket(self.ENTRY))

    def test_prose_above_the_list_is_not_an_item(self):
        assert not any("history, not an item" in item for item in open_items_asking_joe_without_a_ticket(self.ENTRY))

    def test_the_map_number_does_not_satisfy_an_item(self):
        entry = "## 2026-09-16 x\n### Still open\n1. Ask Joe whether to keep it — open a map #3 ticket.\n"
        assert len(open_items_asking_joe_without_a_ticket(entry)) == 1

    def test_the_list_ends_at_the_next_heading(self):
        entry = "## 2026-09-16 x\n### Still open\n1. done, #40\n### Reservations\n1. for Joe to decide later\n"
        assert open_items_asking_joe_without_a_ticket(entry) == []


class TestEveryOpenItemNamesATicket:
    """One queue (2026-09-19): an open item that is not a ticket belongs to nobody.

    The earlier class only refused items that hand Joe a decision. The rest of
    the list -- repo and infrastructure work -- lived in prose here and was
    re-derived every session instead of dispatched. Now every item points at
    a ticket under map #3 or the backlog root, and this list is pointers.
    """

    ENTRY = (
        "## 2026-09-19 (n-th session) — heading\n\n"
        "### Still open\n\n"
        "1. #81 — the volume, still with Joe on #58.\n"
        "2. `scoring.py` scans the whole index on every pass. Its own item.\n"
        "3. #85 — orchestration; board.py is in a lane.\n"
        "4. The 882 MB nobody owns — see map #3.\n"
    )

    def test_an_item_with_no_number_is_refused(self):
        flagged = open_items_without_a_ticket(self.ENTRY)
        assert any(item.startswith("2. `scoring.py`") for item in flagged)

    def test_an_item_naming_a_ticket_passes(self):
        flagged = open_items_without_a_ticket(self.ENTRY)
        assert not any(item.startswith("1. #81") for item in flagged)
        assert not any(item.startswith("3. #85") for item in flagged)

    def test_the_map_number_alone_does_not_count(self):
        flagged = open_items_without_a_ticket(self.ENTRY)
        assert any(item.startswith("4. The 882 MB") for item in flagged)

    def test_exactly_the_two_bad_items_are_flagged(self):
        assert len(open_items_without_a_ticket(self.ENTRY)) == 2


class TestTheParsersFindSomething:
    """A guard over an empty slice is green for the wrong reason."""

    def test_next_md_has_a_dated_latest_entry(self):
        entry = latest_entry(NEXT.read_text(encoding="utf-8"))
        assert entry.startswith("## 20"), "no `## YYYY-MM-DD` entry found at the top of tasks/NEXT.md"

    def test_the_latest_entry_has_a_still_open_list(self):
        entry = latest_entry(NEXT.read_text(encoding="utf-8"))
        assert still_open_items(entry), (
            "the latest NEXT.md entry has no `### Still open` list with numbered items; "
            "that list is the front door and the thing this rule protects"
        )

    def test_the_latest_entry_ends_at_a_rule_not_at_eof(self):
        text = NEXT.read_text(encoding="utf-8")
        entry = latest_entry(text)
        assert len(entry) < len(text) / 2, "the entry parser ran to end of file; it would scan history"


class TestTheRecordHonoursTheRule:
    def test_every_marker_in_the_latest_entry_names_a_ticket(self):
        entry = latest_entry(NEXT.read_text(encoding="utf-8"))
        assert markers_without_a_ticket(entry) == [], (
            "a `Question for Joe:` line in the latest tasks/NEXT.md entry names no ticket. "
            "Open a sub-issue of map #3 (docs/agents/issue-tracker.md, 'Open a ticket for Joe') "
            "and write its number on that line. #3 is the map, not a ticket."
        )

    def test_no_open_item_hands_joe_a_decision_without_a_ticket(self):
        entry = latest_entry(NEXT.read_text(encoding="utf-8"))
        assert open_items_asking_joe_without_a_ticket(entry) == [], (
            "an item in the latest entry's Still open list asks Joe to decide something and "
            "names no ticket. This is the exact line that decayed into 'run the instrument' "
            "twice in three sessions. Open the ticket now; the question does not exist until then."
        )

    def test_every_open_item_names_a_ticket(self):
        entry = latest_entry(NEXT.read_text(encoding="utf-8"))
        assert open_items_without_a_ticket(entry) == [], (
            "an item in the latest entry's Still open list names no ticket. Since 2026-09-19 "
            "there is one queue: every open item is a GitHub issue under map #3 or the backlog "
            "root, and this list is `#NN — one line` pointers (docs/agents/orchestration.md). "
            "Open the ticket, then write its number on the item."
        )

    @pytest.mark.parametrize("doc", measurement_docs_inside_the_rule(), ids=lambda p: p.name)
    def test_every_marker_in_a_measurement_doc_names_a_ticket(self, doc: Path):
        assert markers_without_a_ticket(doc.read_text(encoding="utf-8")) == [], (
            f"{doc.name} writes `Question for Joe:` without a ticket number"
        )

    def test_the_measurement_scope_is_a_date_prefix_not_a_guess(self):
        # Every measurement doc is named YYYY-MM-DD-<slug>.md; if that changes,
        # the date comparison above silently compares slugs.
        names = [p.name for p in MEASUREMENTS.glob("*.md")]
        assert names, "docs/measurements has no .md files"
        bad = [n for n in names if not re.match(r"^\d{4}-\d{2}-\d{2}-", n)]
        assert bad == [], f"measurement docs without a date prefix: {bad}"
