"""Games (slate) says its standing disclaimer once, not under every row (#247).

The page ran ~19,500 words over 100 rows because "Bet this by hand" carried
a note, "This is your own bet ... never counts toward the gate", under each
row. Said once above the list now. The per-row **refusal code** is different
on each row and stays on every one of them: the board mixes `stale_odds`
with "no edge after fees", and that code is what tells them apart.

The headline count reads "Showing N of M": the server cuts the list at its
LIMIT, so a bare N read as the size of the slate. `slate.in_window` (the
count before the cut) is already served.

Source-reading tests, like `tests/test_hud_slate.py`: this repo has no React
runner. What this does NOT establish: that the sentence paints once in a
browser, or how the headline wraps at 390px -- only opening the page does.
"""

from __future__ import annotations

import re
from pathlib import Path

SLATE_PAGE = Path(__file__).resolve().parent.parent / "frontend/src/app/slate/page.tsx"


def _src() -> str:
    return SLATE_PAGE.read_text(encoding="utf-8")


def _row_body(source: str) -> str:
    """The text of the `Row` component, up to the next top-level function."""
    body = source.split("\nfunction Row(", 1)[1]
    return re.split(r"\n(?:export )?(?:async )?function |\n/\*\*\n", body, maxsplit=1)[0]


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


class TestTheDisclaimerIsSaidOnce:
    def test_the_own_bet_sentence_appears_once_in_the_page(self):
        flat = _flat(_src())
        assert flat.count("never counts toward the gate") == 1

    def test_it_is_outside_the_row_that_is_mapped_100_times(self):
        assert "counts toward the gate" not in _row_body(_src())

    def test_the_row_ticket_carries_no_note(self):
        row = _row_body(_src())
        ticket = row.split("<ManualTicket", 1)[1].split("/>", 1)[0]
        assert "note=" not in ticket

    def test_the_sentence_sits_above_the_list(self):
        src = _src()
        assert src.index("never") < src.index("<ul className=\"mt-8 divide-y")
        assert "toward the gate" in src.split('<ul className="mt-8 divide-y', 1)[0]

    def test_the_row_still_offers_the_door(self):
        assert 'openLabel="Bet this by hand"' in _row_body(_src())


class TestEveryRowKeepsItsRefusalCode:
    def test_the_row_renders_the_suppressed_reason(self):
        row = _row_body(_src())
        assert "{row.suppressed_reason}" in row

    def test_the_code_is_not_conditional_on_anything_but_being_set(self):
        assert "row.suppressed_reason && (" in _row_body(_src())


class TestTheHeadlineSaysShowingNOfM:
    def test_the_stat_reads_showing_n_of_m(self):
        flat = _flat(_src())
        assert re.search(r'<Stat label="Showing" value=\{`\$\{slate\.returned\} of \$\{', flat)

    def test_m_is_the_window_before_the_cut(self):
        assert "slate.in_window" in _src().split("<Stat", 1)[1].split("/>", 1)[0]

    def test_the_bare_count_headline_is_gone(self):
        assert 'label="On the slate"' not in _src()


TICKET = Path(__file__).resolve().parent.parent / "frontend/src/components/ManualTicket.tsx"
FRONTEND_SRC = Path(__file__).resolve().parent.parent / "frontend/src"
CLOSED_SENTENCE = "Nothing is sent until you confirm"


class TestTheClosedStateSentenceRendersOnceOnGames:
    """#253: ManualTicket's closed-state sentence sat under all 100 rows.

    Copy only: the prop gates one paragraph and nothing on the order path.
    """

    def test_the_ticket_gates_the_sentence_behind_a_prop_defaulting_true(self):
        src = TICKET.read_text(encoding="utf-8")
        assert "closedNote = true," in src
        assert "closedNote?: boolean;" in src
        flat = _flat(src)
        assert re.search(
            r"\{closedNote && \( <p [^>]*> The ticket reads Kalshi&rsquo;s live book"
            r".{0,120}" + CLOSED_SENTENCE,
            flat,
        )

    def test_the_games_row_switches_it_off(self):
        ticket = _row_body(_src()).split("<ManualTicket", 1)[1].split("/>", 1)[0]
        assert "closedNote={false}" in ticket

    def test_games_says_it_once_above_the_list(self):
        flat = _flat(_src())
        assert flat.count(CLOSED_SENTENCE.replace("Nothing", "nothing")) == 1
        above = _src().split('<ul className="mt-8 divide-y', 1)[0]
        assert "nothing is sent until you confirm" in _flat(above)

    def test_every_other_screen_keeps_the_default(self):
        mounts = 0
        for path in FRONTEND_SRC.rglob("*.tsx"):
            if path == SLATE_PAGE or path == TICKET:
                continue
            text = path.read_text(encoding="utf-8")
            for chunk in text.split("<ManualTicket")[1:]:
                head = chunk.split("/>", 1)[0]
                if "ticker=" in head:
                    mounts += 1
                    assert "closedNote" not in head, path.name
        assert mounts >= 5
