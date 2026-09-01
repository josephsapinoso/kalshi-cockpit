"""The Games list may not be ordered, at any depth, by the consensus gap.

Decision map ticket #27. `map #3` rules out of scope *"ordering or filtering ANY
screen by the Kalshi-vs-consensus gap (measured beta = -0.141, ranking by it
puts the least trustworthy rows on top)"* -- and `/api/slate` had been doing it
since before the rule was written, as the third key of its sort:

    items.sort(key=lambda r: (r["commence_ms"] is None,
                              r["commence_ms"] or 0,
                              -(r["edge_tenths"] or 0)))

**It was not a rare tiebreak.** Both sides of a moneyline carry a byte-identical
`commence_ms`, so the third key decided which side of *every* game printed
first, and the side printed first was the higher-apparent-edge one. The row
renders neither `side` nor `event_title`, so the reader could not see which
side they were being shown.

What this file establishes
--------------------------
That rows sharing a kickoff come back in an order that does not depend on
`edge_tenths`, and that the source carries no `edge_tenths` in its sort key.

What it does not establish
--------------------------
- **That the ordering is *good*.** Ticker order inside a kickoff is arbitrary;
  it is chosen because it is deterministic and carries no claim, not because
  it helps anyone. If a better claimless key is wanted, this test should be
  changed with it.
- **Anything about `/api/board` or `/api/parlays`**, which sort on their own
  keys for their own reasons.
- **That no other screen ranks by the gap.** This file covers one sort.
"""

from __future__ import annotations

import inspect
import re


class TestTheSortKeyCarriesNoClaim:
    def test_the_slate_sort_does_not_mention_edge_tenths(self):
        """A source assertion, because the behavioural test below cannot
        distinguish "ticker order" from "edge order" when the two agree by
        chance -- and with two rows they agree half the time."""
        from backend.api import routes

        source = inspect.getsource(routes)
        match = re.search(
            r"items\.sort\(\s*key=lambda r: \((.*?)\)\s*\)", source, re.S
        )
        assert match, "the /api/slate sort could not be located"
        key = match.group(1)
        assert "edge_tenths" not in key, (
            "the Games list is ordered by the Kalshi-vs-consensus gap, which "
            "the decision map rules out of scope: beta = -0.141 means this "
            f"puts the least trustworthy rows first. Key was: {key.strip()}"
        )
        assert "ticker" in key, (
            "the tiebreak must be something deterministic that carries no "
            f"claim. Key was: {key.strip()}"
        )

    def test_the_comment_says_why_rather_than_only_what(self):
        """A bare `r["ticker"]` invites the next session to 'improve' the sort
        by putting the best rows on top, which is the whole defect. The reason
        has to sit beside the key."""
        from backend.api import routes

        source = inspect.getsource(routes)
        i = source.index("items.sort(")
        preamble = source[max(0, i - 1600):i]
        assert "-0.141" in preamble, (
            "the sort's comment does not carry the measurement that forbids "
            "the old key"
        )
        assert "byte-identical" in preamble, (
            "the comment does not record that this key decides EVERY pair, "
            "which is the reason the 'it is only a tiebreak' reading fails"
        )


class TestRowsSharingAKickoffDoNotOrderByEdge:
    """The behavioural half. Two rows, identical `commence_ms`, and the one
    with the larger `edge_tenths` deliberately sorts LAST by ticker -- so a
    reversion to the edge key flips them and this fails."""

    def _sorted_items(self, rows: list[dict]) -> list[dict]:
        """Apply the route's own key, read out of the source.

        Re-implementing the key here would test the copy rather than the
        route, which is the failure `tests/lessons` records as "a test that
        names a symbol is not a guard on that symbol".
        """
        import inspect as inspect_module

        from backend.api import routes

        source = inspect_module.getsource(routes)
        match = re.search(
            r"items\.sort\(\s*(key=lambda r: \(.*?\))\s*\)", source, re.S
        )
        assert match, "the /api/slate sort could not be located"
        key = eval(  # noqa: S307 -- the expression comes from our own source
            match.group(1).replace("key=", ""), {}, {}
        )
        return sorted(rows, key=key)

    def test_the_bigger_edge_does_not_come_first(self):
        rows = [
            {"ticker": "ZZZ-YES", "commence_ms": 1_788_000_000_000,
             "edge_tenths": 900},
            {"ticker": "AAA-NO", "commence_ms": 1_788_000_000_000,
             "edge_tenths": -400},
        ]
        order = [r["ticker"] for r in self._sorted_items(rows)]
        assert order == ["AAA-NO", "ZZZ-YES"], (
            "the row with the larger apparent edge sorted first on a pair "
            "sharing a kickoff -- the ordering the map rules out of scope"
        )

    def test_kickoff_still_wins_over_the_tiebreak(self):
        """The fix must not cost the ordering the screen exists for."""
        rows = [
            {"ticker": "AAA", "commence_ms": 1_788_000_100_000,
             "edge_tenths": 0},
            {"ticker": "ZZZ", "commence_ms": 1_788_000_000_000,
             "edge_tenths": 0},
        ]
        order = [r["ticker"] for r in self._sorted_items(rows)]
        assert order == ["ZZZ", "AAA"], "kickoff order was lost"

    def test_an_unknown_kickoff_still_sorts_last(self):
        """`commence_ms` is nullable and a row with no kickoff is the least
        decidable thing on the screen. Putting it first would give it the most
        attention -- the route's own stated reason."""
        rows = [
            {"ticker": "AAA", "commence_ms": None, "edge_tenths": 5000},
            {"ticker": "ZZZ", "commence_ms": 1_788_000_000_000,
             "edge_tenths": 0},
        ]
        order = [r["ticker"] for r in self._sorted_items(rows)]
        assert order == ["ZZZ", "AAA"], "a row with no kickoff sorted first"
