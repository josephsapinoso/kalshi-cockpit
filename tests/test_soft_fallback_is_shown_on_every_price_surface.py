"""Every screen that shows a consensus price says when no sharp book backed it.

`consensus_devig` reads `selected = sharp or usable`, so a rung no purchased
sharp book reached silently falls back to the full book set -- a wide consensus
wearing a sharp consensus's name. Measured on live 2026-09-16: about two of
three NCAAF `spreads` and `totals` rows are that fallback, and NCAAF is the
Saturday slate.

THE DEFECT THIS PINS, AND IT IS AN ASYMMETRY RATHER THAN AN ABSENCE
-------------------------------------------------------------------
`ParlayCards.tsx` rendered its anchor note only on `anchored_on_sharp === true`
-- it told the reader when the anchor was GOOD and said nothing when there was
none. The slate page, the picks block and the consensus panel already marked
the soft case. So the one surface that stayed quiet about bad news was the
surface Joe actually taps: `parlay_lookups` holds 77 lifetime taps and his real
fills are KXMVE combos.

That is the shape `tasks/lessons.md` records from ADR 0154 -- fix every reader,
not the one whose symptom you saw, and the flattering half is the one that
survives. A missing warning and a warning that fires only on good news look
identical in a screenshot and are not the same bug: the second reads as
"we checked".

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Source text, not rendering.** Same instrument and same limitation as
  `tests/test_good_chance_picks.py` and `test_crew_bubble.py`: a green suite
  says the component contains the right branches, not that they render, are
  reachable on a phone, or are legible.
- **Nothing about the server half.** Whether `anchored_on_sharp` is correct on
  a row is `backend/core/devig.py` and `tests/test_devig.py`; whether it
  reaches the payload is `backend/api/serialise.py`. This is the screen only.
- **Nothing about whether the WORDS work.** It pins that a sentence naming the
  missing sharp book is present, not that it changes anyone's bet.

Mutations, each observed red:
  1. delete the `=== false` branch from `ParlayCards.tsx` (the original defect)
  2. render the soft note in muted rather than accent ink
  3. delete the soft-fallback branch from `GoodChancePicks.tsx`
  4. move `Anchor`'s null guard below its truthiness branch, so an unknown row
     renders as a measured absence
  5. drop a surface from `PRICE_SURFACES` while it still reads the flag
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"

PARLAY_CARDS = FRONTEND / "components" / "ParlayCards.tsx"
SLATE_PAGE = FRONTEND / "app" / "slate" / "page.tsx"
PICKS = FRONTEND / "components" / "GoodChancePicks.tsx"
CONSENSUS = FRONTEND / "components" / "ConsensusPanel.tsx"

#: Every surface that puts a consensus-derived price in front of Joe and
#: therefore owes him the caveat.
#:
#: Listed rather than discovered, and `TestTheSurfaceListCannotSilentlyBecomeASubset`
#: is what stops the list becoming a subset -- which it caught on its first
#: run, when `ConsensusPanel` was missing from this literal while already
#: handling the flag correctly. The enumeration found the gap in the TEST
#: rather than in the code, which is the direction that usually goes unnoticed.
PRICE_SURFACES = [
    pytest.param(PARLAY_CARDS, id="ParlayCards"),
    pytest.param(SLATE_PAGE, id="slate-page"),
    pytest.param(PICKS, id="GoodChancePicks"),
    pytest.param(CONSENSUS, id="ConsensusPanel"),
]


def source(path: Path) -> str:
    assert path.exists(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def code_only(text: str) -> str:
    """`text` with comments stripped.

    A prohibition's own explanation must not satisfy the grep that enforces it
    -- the `test_crew_bubble` lesson. The fix under test ships with a long
    comment naming the very strings asserted below, so without this every
    assertion would pass on the comment alone.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


class TestTheSoftCaseIsMarkedEverywhereAPriceIsShown:
    """Mutations 1 and 3: delete the soft branch from any surface."""

    @pytest.mark.parametrize("path", PRICE_SURFACES)
    def test_the_surface_distinguishes_all_three_values(self, path):
        """Two idioms are accepted, because two are in use and both are right.

        Most surfaces branch inline on `anchored_on_sharp === false`. The slate
        page routes the flag through an `Anchor` component that returns early
        on null/undefined and then falls through to the soft note -- the same
        three-way distinction expressed as control flow. Demanding the literal
        `=== false` everywhere would fail a correct surface and push whoever
        hit it into rewriting working code to satisfy a grep.

        What may NOT happen is a surface that reads the flag and handles only
        one of its values.
        """
        text = code_only(source(path))
        inline = "anchored_on_sharp === false" in text
        early_return = bool(
            re.search(r"anchored === null \|\| anchored === undefined", text)
        )
        assert inline or early_return, (
            f"{path.name} shows a consensus price and never separates 'no "
            "sharp book' from 'not known', so it is silent or wrong exactly "
            "when the consensus is weakest"
        )

    @pytest.mark.parametrize("path", PRICE_SURFACES)
    def test_the_surface_says_something_a_person_can_act_on(self, path):
        """The words matter, not just the branch: a sentence naming the
        missing sharp book, never a bare icon."""
        text = code_only(source(path))
        assert re.search(
            r"soft[- ]book|soft fallback|No sharp book", text, re.IGNORECASE
        ), f"{path.name} branches on the flag but prints nothing legible"


class TestTheParlayCardNoLongerOnlyReportsGoodNews:
    """Mutations 1 and 2, stated as the specific regression.

    The generic coverage above would go green again if someone restored the
    `=== true`-only version on a surface not yet listed. This names the file
    the defect was actually in.
    """

    def test_it_marks_the_bad_case_and_not_only_the_good_one(self):
        text = code_only(source(PARLAY_CARDS))
        assert "anchored_on_sharp === true" in text, "the good-news note"
        assert "anchored_on_sharp === false" in text, (
            "ParlayCards rendered ONLY the `true` note until 2026-09-16 -- it "
            "told the reader when the anchor was good and went quiet when "
            "there was none, on the surface he actually taps"
        )

    def test_the_bad_case_is_not_quieter_than_the_good_one(self):
        """A warning in muted grey beside a reassurance in body text is a
        warning that loses. The soft note carries the accent class the slate
        page uses for the same fact."""
        text = code_only(source(PARLAY_CARDS))
        after = text.split("anchored_on_sharp === false", 1)[1][:400]
        assert "text-accent-2" in after, (
            "the soft-fallback note must not be rendered in muted text"
        )


class TestNullIsNotTreatedAsAbsent:
    """`anchored_on_sharp` is three-valued.

    `null` means the LEFT JOIN missed -- `serialise.py` is explicit that the
    column is `NOT NULL DEFAULT 0`, so `null` can only mean "no row", never
    "no sharp book". Warning on it would put a red sentence on rows nothing is
    known about, which teaches the reader to ignore the sentence.
    """

    @pytest.mark.parametrize("path", PRICE_SURFACES)
    def test_the_check_is_strict_equality_not_falsiness(self, path):
        text = code_only(source(path))
        assert not re.search(r"!\s*\w+\.anchored_on_sharp", text), (
            f"{path.name} tests the flag for falsiness, which fires on null "
            "as well as false"
        )
        assert not re.search(r"anchored_on_sharp\s*==\s*false", text), (
            f"{path.name} uses loose equality on a three-valued flag"
        )

    def test_the_slate_component_rules_out_null_before_any_warning(self):
        """Mutation 4: the control-flow idiom has to get its order right.

        `Anchor` handles null/undefined FIRST and returns a neutral dash. If
        that guard moved below the truthiness branch, an unknown row would
        fall through to the soft-fallback warning and read as a measured
        absence -- the same wrong reading, arrived at by a different route.
        """
        text = code_only(source(SLATE_PAGE))
        block = text.split("function Anchor", 1)[1][:900]
        null_at = block.find("anchored === null")
        truthy_at = block.find("if (anchored)")
        assert null_at != -1 and truthy_at != -1, block[:200]
        assert null_at < truthy_at, (
            "Anchor must rule out null before branching on truthiness, or an "
            "unknown row renders as a soft fallback"
        )


class TestTheSurfaceListCannotSilentlyBecomeASubset:
    def test_every_component_reading_the_flag_is_listed_here(self):
        """Mutation 5, and the `test_has_callers.py` shape: enumerate rather
        than remember.

        A screen that reads `anchored_on_sharp` and is not in
        `PRICE_SURFACES` is exempt from every assertion above -- which is
        exactly how `ParlayCards` stayed half-marked while three other
        surfaces were correct.
        """
        listed = {p.values[0] for p in PRICE_SURFACES}
        # `api.ts` is the type surface, not a screen: it declares the field
        # and renders nothing.
        allowed_unlisted = {FRONTEND / "lib" / "api.ts"}
        found = {
            path
            for path in FRONTEND.rglob("*.ts*")
            if "anchored_on_sharp" in code_only(path.read_text(encoding="utf-8"))
        }
        unlisted = found - listed - allowed_unlisted
        assert not unlisted, (
            f"{sorted(p.name for p in unlisted)} read anchored_on_sharp and "
            "are not in PRICE_SURFACES, so nothing checks that they mark the "
            "soft case"
        )
