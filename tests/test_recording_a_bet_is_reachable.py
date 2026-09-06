"""Where the desk lets Joe record a bet he placed somewhere else.

**Why this exists.** On 2026-09-06 Joe had the exchange's offer-making
controls removed -- *"I don't want to make offers or find offers in shares"* --
and asked, in the same breath, to be able to pay for a combination at a
sportsbook *"from the betting and parlay pages"*. The desk cannot place a
sportsbook bet; what it can do is record one, which is what ADR 0078's
`RecordParlay` already did, on exactly one screen nobody starts from.

So this pins the reach, not the rendering. A sportsbook bet never enters
`fills` -- that is the hole ADR 0078 exists for, and the reason the 2026-09-04
census could count only Kalshi taker hand fills -- so a screen that loses this
control loses the only path by which that class of bet is recorded at all, and
loses it silently: nothing errors, the form is simply not there.

**What this establishes.** That the control is reachable from all four screens
Joe named; that the parlay desk's copy arrives prefilled from the card he was
looking at; and that the prefill stops short of the two money fields.

**What it does not establish.** That the form submits, that the server accepts
what it sends, or that a recorded position is priced correctly -- those are
`test_hedge_api.py` and `test_hedge_arithmetic.py`. This reads source text,
so it also cannot establish that the control is *visible* rather than merely
mounted; it is inside a collapsed `<details>` by design.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "app"
COMPONENTS = ROOT / "frontend" / "src" / "components"

#: The four screens Joe named, by his words for them, plus `/hedge` where the
#: control has always lived. `/` re-exports `/slate`, so the slate file covers
#: "Games" -- asserting on `page.tsx` instead would pass on a one-line
#: re-export that renders nothing of its own.
SCREENS = {
    "Games": APP / "slate" / "page.tsx",
    "Picks": APP / "picks" / "page.tsx",
    "Parlays": COMPONENTS / "ParlayCards.tsx",
    "Your bets": APP / "bets" / "page.tsx",
    "Hedging": APP / "hedge" / "page.tsx",
}


@pytest.fixture(scope="module")
def sources() -> dict[str, str]:
    missing = [name for name, path in SCREENS.items() if not path.exists()]
    assert not missing, f"screens moved or were renamed: {missing}"
    return {
        name: path.read_text(encoding="utf-8") for name, path in SCREENS.items()
    }


class TestTheControlIsReachable:
    def test_every_screen_joe_named_can_record_a_bet(self, sources):
        """His instruction was about reach, so reach is what is pinned.

        The failure this catches is not a crash. A page that drops the
        import renders exactly as it did before -- one line shorter -- and
        the only symptom is that a bet placed at a book never gets recorded,
        which surfaces weeks later as an empty `parlay_positions`.
        """
        # **A prefix match is not a match**, and the first version of this
        # test made exactly that mistake: it asked for `"<RecordParlay" in
        # source`, which a mutation to `<RecordParlayX` satisfied, so the
        # guard reported green over a screen that no longer rendered the
        # control. The element name has to END where the tag does.
        element = re.compile(r"<RecordParlay(?=[\s/>])")

        for name, source in sources.items():
            assert element.search(source), (
                f"{name} no longer offers to record a bet placed elsewhere. "
                f"Joe asked for it on this screen (2026-09-06); removing it "
                f"needs his word."
            )
            assert 'from "@/components/RecordParlay"' in source, name


class TestTheParlayCardFillsItIn:
    def test_the_card_hands_over_its_own_legs(self, sources):
        """A form re-typed from the card above it is one nobody fills.

        The legs come from `card.legs`, not from a literal: a hand-written
        leg list would drift from the card it sits under, and the drift
        would be invisible because both render.
        """
        source = sources["Parlays"]
        assert "prefill={{" in source
        assert "card.legs.map((leg)" in source
        assert "label: card.title" in source
        assert 'source: "sportsbook"' in source

    def test_the_prefill_stops_short_of_the_money(self, sources):
        """The two fields the desk must not guess.

        Only his book knows the stake and the total return. `RecordParlay`'s
        own docstring records why a guessed return is worse than a blank
        one: the equalising hedge is exactly that many dollars of contracts,
        so a wrong return lands directly in the size of a real order.

        Pinned on the component rather than the card, because the prefill
        type is what would have to grow a field for this to become possible
        anywhere.
        """
        prefill_type = (COMPONENTS / "RecordParlay.tsx").read_text(
            encoding="utf-8"
        )
        start = prefill_type.index("export type RecordParlayPrefill")
        block = prefill_type[start : prefill_type.index("};", start)]

        for field in ("stake", "payout", "return"):
            assert field not in block, (
                f"`{field}` entered RecordParlayPrefill. The desk does not "
                f"know what a sportsbook paid, and a guessed return lands in "
                f"the size of a hedge."
            )
