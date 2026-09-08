"""The combo depth claims match the committed captures, and "18 units" stays gone.

On 2026-09-08 a figure that had reached a real-money refusal screen was found
to be false three ways over. The refusal Joe would have read said combination
books are "enter-only and the deepest resting bid ever measured here was 18
units, so a larger count could not fill", citing ADR 0012 §5.

1. **The citation is spurious.** ADR 0012 carries no depth figure. Its only
   `18` is the denominator of `same-game 17/18` -- a rate the ADR itself
   withdraws for having too few expected outcomes to speak.
2. **The real source was scoped and the scope was dropped.**
   `docs/measurements/2026-08-18-combo-book-presence-inseason-result.md` says
   "the deepest resting order **here** was 18.00 units". That "here" is one run
   of 11 rows. Every copy downstream promoted it to "ever measured".
3. **Repo-wide it is wrong by ~38x**, and in the direction that matters: the
   committed captures carry resting NO bids to 683 units.

A fourth error rode along on the screen. `PriceOnKalshi.tsx` told Joe to
"expect it to refuse" because "3 of 20 and 3 of 9 rows on 2026-08-09 carried a
resting bid". Those are the `volume` counts -- rows that had ever *traded*.
The resting-bid counts are 16 of 20 and 6 of 9. Five books in six were
quoted while the screen said to expect nothing.

This test pins the arithmetic against the artifacts themselves, so the numbers
in the prose cannot drift from the data again, and pins the struck phrasing
absent from the tree.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about buyability today.** These are three runs on two dates in
  August 2026, 40 books, one operator's ladder. A resting NO bid observed then
  is not an offer available now, and `backend/kalshi/combos.py`'s calendar
  caveat (no NBA, no NFL in the original capture) is untouched.
- **Nothing about the exit.** The zero-YES-bid finding is asserted here as a
  property of the captures, not proven as a fact about the venue; it is the
  claim that survived the correction, not one this test establishes.
- **Nothing about fill quality or fee.** Depth at a price is not a fill, and
  ADR 0012 §5 still records the combo fee model as unverified.
- **Nothing about whether the 250-contract ceiling is the right number.** It
  pins the ceiling's stated *reason*, not its value; the binding bound on this
  path is spend, not count.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MEASUREMENTS = REPO / "docs" / "measurements"

#: The three committed combination-book captures, and the row count each
#: contributed to the "40 of 40" that the surviving exit claim rests on.
CAPTURES = {
    "2026-08-09-combo-e2-book-empty.json": 20,
    "2026-08-09-combo-e3-list-no-bid.json": 9,
    "2026-08-18-combo-book-presence-inseason.json": 11,
}


def _levels(row: dict) -> tuple[list, list]:
    """Return `(yes_levels, no_levels)` for one captured row's book."""
    book = row.get("book") or {}
    yes: list = []
    no: list = []
    for side, levels in book.items():
        if not isinstance(levels, list):
            continue
        parsed = [lv for lv in levels if isinstance(lv, (list, tuple)) and len(lv) >= 2]
        (yes if "yes" in side else no).extend(parsed)
    return yes, no


def _rows(name: str) -> list[dict]:
    payload = json.loads((MEASUREMENTS / name).read_text(encoding="utf-8"))
    return payload["rows"]


class TestTheCapturesSayWhatTheProseSaysTheySay:
    def test_the_captures_are_all_present_and_total_forty_rows(self):
        total = 0
        for name, expected in CAPTURES.items():
            assert (MEASUREMENTS / name).exists(), f"{name} is the evidence; do not delete it"
            rows = _rows(name)
            assert len(rows) == expected, f"{name} changed shape: {len(rows)} rows, expected {expected}"
            total += len(rows)
        assert total == 40, "the '40 of 40' in CLAUDE.md and README.md is this sum"

    def test_no_capture_carries_a_single_resting_yes_bid(self):
        """The exit claim -- the one that survived the correction."""
        for name in CAPTURES:
            for row in _rows(name):
                yes, _ = _levels(row)
                assert yes == [], (
                    f"{name} carries a resting YES bid on {row.get('ticker')}. "
                    "If this fires the exit claim is refuted and CLAUDE.md's "
                    "combo row, ADR 0078's justification and the combination "
                    "contract ceiling all need re-deciding."
                )

    def test_thirty_three_of_the_forty_rows_carry_a_resting_no_bid(self):
        """Entry, which the screen had backwards. A NO bid IS the ask you buy at."""
        per_capture = {}
        for name in CAPTURES:
            per_capture[name] = sum(1 for row in _rows(name) if _levels(row)[1])
        assert per_capture == {
            "2026-08-09-combo-e2-book-empty.json": 16,
            "2026-08-09-combo-e3-list-no-bid.json": 6,
            "2026-08-18-combo-book-presence-inseason.json": 11,
        }
        assert sum(per_capture.values()) == 33

    def test_the_resting_bid_rate_is_not_the_volume_rate(self):
        """The conflation that produced 'expect it to refuse'.

        3 of 20 and 3 of 9 are the rows that had ever TRADED. Reporting them
        as the resting-bid rate understated buyability by more than 5x.
        """
        traded = {}
        for name in ("2026-08-09-combo-e2-book-empty.json", "2026-08-09-combo-e3-list-no-bid.json"):
            rows = _rows(name)
            traded[name] = sum(1 for r in rows if float(r.get("volume") or 0) > 0)
        assert traded == {
            "2026-08-09-combo-e2-book-empty.json": 3,
            "2026-08-09-combo-e3-list-no-bid.json": 3,
        }, "these are the 3-of-20 and 3-of-9 that were misreported as resting bids"
        # And they are strictly rarer than a quoted book, which is the point.
        for name, n_traded in traded.items():
            n_bid = sum(1 for r in _rows(name) if _levels(r)[1])
            assert n_bid > n_traded

    def test_the_deepest_resting_bid_in_the_record_is_683_units_not_18(self):
        deepest_overall = 0.0
        per_capture = {}
        for name in CAPTURES:
            sizes = [float(lv[1]) for row in _rows(name) for lv in _levels(row)[1]]
            per_capture[name] = max(sizes) if sizes else 0.0
            deepest_overall = max(deepest_overall, per_capture[name])
        assert deepest_overall == 683.0
        # 18.0 is real, and is the 2026-08-18 run's within-run maximum only.
        # That is exactly the scope the struck phrasing dropped.
        assert per_capture["2026-08-18-combo-book-presence-inseason.json"] == 18.0
        assert per_capture["2026-08-09-combo-e2-book-empty.json"] == 413.0


#: Files that carried the struck claim. Prose may be rewritten; what may not
#: come back is a repo-wide depth bound of 18 units.
#:
#: **EVERY ADR is pinned, added 2026-09-08, and the omission is why this list
#: needed extending at all.** The guard shipped on 2026-09-08 covering five
#: named files -- and the claim it exists to catch was, at that moment, still
#: asserted as fact in FOUR documents it did not read. `0073` stated *"3 of 20
#: and 3 of 9 rows ... it is rarely live"* about a resting-NO-bid rate that is
#: really 33 of 40, in the very ADR that decided how the buy control behaves
#: on a combination; `0070` and `0075` carried the struck depth figure. All
#: four could have sat there indefinitely with CI green.
#:
#: That is this repo's recurring shape -- a bound relaxed and the next one
#: binding in silence -- except here it was a guard whose scope stopped just
#: short of where the defect actually lived. **A guard that reads the code but
#: not the decisions is half a guard**, because an ADR is what the next
#: session reads to decide whether to re-litigate something.
#:
#: The directory is globbed rather than listed, so a NEW ADR is covered the
#: day it is written. A list would have to be remembered.
PINNED = [
    Path("backend") / "api" / "routes.py",
    Path("backend") / "store" / "manual_orders.py",
    Path("frontend") / "src" / "components" / "PriceOnKalshi.tsx",
    Path("CLAUDE.md"),
    Path("README.md"),
] + sorted(
    p.relative_to(REPO) for p in (REPO / "docs" / "adr").glob("*.md")
)


#: A guard that simply forbids a string also forbids the record of why it was
#: struck, and this repo keeps wrong text verbatim on purpose. So an occurrence
#: is allowed only where a strike marker sits close before it -- which is what
#: a correction note has and a fresh assertion does not.
STRIKE_MARKERS = (
    "struck",
    "was false",
    "is false",
    "wrong three ways",
    "corrected 2026-09-08",
    "used to read",
    "used to be",
    "used to give",
    "must not be cited",
)

#: How far to look for the marker. One paragraph, not one file: a marker at
#: the top of a 4,000-line module must not license a claim at the bottom.
#:
#: The window reaches FORWARD as well as back, because a correction note
#: often opens with the struck phrase and marks it in the same sentence --
#: `"<phrase>" was struck on ...`. A backward-only window failed on exactly
#: that shape in CLAUDE.md.
STRIKE_WINDOW_BEFORE = 700
STRIKE_WINDOW_AFTER = 250

#: **A limitation this guard has and cannot remove, stated rather than
#: discovered later.** Because a marker within the window licenses the phrase,
#: the ONE place a struck claim can quietly come back is immediately beside
#: its own correction note -- the reintroduction inherits the shield. Verified
#: 2026-09-08: re-inserting the struck depth phrase into ADR 0070's corrected
#: paragraph left the suite green; planting it in an ADR with no note failed
#: as intended.
#:
#: This is the accepted cost of keeping wrong text verbatim, not a defect to
#: fix by narrowing the window -- a backward-only window already failed on
#: CLAUDE.md's real shape. What it means in practice: **when editing a
#: paragraph that already carries a correction note, the note does not check
#: your work.** Read what the note says the claim IS before adding to it.


def unstruck_occurrences(text: str, phrase: str) -> list[int]:
    """Offsets where `phrase` appears with no strike marker near it."""
    bare: list[int] = []
    start = 0
    while (found := text.find(phrase, start)) != -1:
        end = found + len(phrase)
        context = text[
            max(0, found - STRIKE_WINDOW_BEFORE):end + STRIKE_WINDOW_AFTER
        ].lower()
        if not any(marker in context for marker in STRIKE_MARKERS):
            bare.append(found)
        start = end
    return bare


FORBIDDEN = (
    "≤18 units deep",
    "deepest resting bid ever measured",
    "deepest resting bid this repo has ever measured",
    "the deepest resting order the combo record has ever seen",
    "so a larger count could not fill",
    "so a far larger count",
    # **The OTHER half of the 2026-09-08 defect, added the same day the ADRs
    # were corrected.** The depth figure and the entry/exit conflation shipped
    # together and only the depth figure was guarded, so `0073` went on
    # asserting that a resting NO bid is rare -- in the ADR that decided how
    # the buy control behaves on a combination -- with CI green.
    #
    # `3 of 20` and `3 of 9` are the counts of books that had ever TRADED. The
    # resting-NO-bid counts are 16 of 20, 6 of 9 and 11 of 11: 33 of 40, and a
    # resting NO bid IS the ask you buy at. Reporting the volume figure as the
    # liquidity figure is what told Joe to "expect it to refuse" while five
    # books in six were quoted.
    "it is rarely live",
    "3 of 20 and 3 of 9",
)


class TestTheGuardItself:
    """Disable-and-watch-it-fail, per CLAUDE.md. A guard nobody has broken on
    purpose is decoration."""

    def test_a_bare_assertion_is_caught(self):
        assert unstruck_occurrences(
            "Combination books are enter-only and the deepest resting bid "
            "ever measured here was 18 units.",
            "deepest resting bid ever measured",
        )

    def test_a_correction_note_is_permitted(self):
        assert unstruck_occurrences(
            "This was struck on 2026-09-08: it said the deepest resting bid "
            "ever measured was 18 units, and the record reaches 683.",
            "deepest resting bid ever measured",
        ) == []

    def test_a_distant_marker_does_not_license_a_later_claim(self):
        text = (
            "struck."
            + ("x" * (STRIKE_WINDOW_BEFORE + 50))
            + "deepest resting bid ever measured"
            + ("x" * (STRIKE_WINDOW_AFTER + 50))
        )
        assert unstruck_occurrences(text, "deepest resting bid ever measured")


class TestTheStruckPhrasingStaysStruck:
    @pytest.mark.parametrize("relative", PINNED, ids=lambda p: p.name)
    def test_no_file_claims_a_repo_wide_depth_of_eighteen_units(self, relative: Path):
        text = (REPO / relative).read_text(encoding="utf-8")
        for phrase in FORBIDDEN:
            assert not unstruck_occurrences(text, phrase), (
                f"{relative} asserts the struck claim {phrase!r} without "
                "marking it struck. The deepest resting bid in the committed "
                "record is 683 units; 18 was one 11-row run's maximum, scoped "
                "by the word 'here' in docs/measurements/"
                "2026-08-18-combo-book-presence-inseason-result.md."
            )

    def test_the_refusal_detail_joe_reads_carries_no_fill_bound(self):
        """The money-facing half: this string reached him inside a 422.

        Checked on the f-string fragments rather than the file, because the
        correction note above them is allowed to quote what it replaced.
        """
        routes = (REPO / "backend" / "api" / "routes.py").read_text(encoding="utf-8")
        detail_start = routes.index("a combination order is capped at")
        detail = routes[detail_start:detail_start + 900]
        assert "could not fill" not in detail
        assert "18 units" not in detail
        assert "resting YES bid" in detail, "the true half must still be said"

    def test_the_screen_no_longer_tells_him_to_expect_a_refusal(self):
        source = (
            REPO / "frontend" / "src" / "components" / "PriceOnKalshi.tsx"
        ).read_text(encoding="utf-8")
        assert "**Expect it to refuse.**" not in source
        assert "kills nearly every combo order" not in source

    def test_the_surviving_exit_claim_is_still_stated_where_it_is_load_bearing(self):
        """A correction that deletes the true half too is not a correction."""
        routes = (REPO / "backend" / "api" / "routes.py").read_text(encoding="utf-8")
        assert "resting YES bid" in routes
        manual = (REPO / "backend" / "store" / "manual_orders.py").read_text(encoding="utf-8")
        assert "40/40" in manual or "40 of 40" in manual
