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

        # **Inverted 2026-09-08.** This required the prefill to carry
        # `source: "sportsbook"`. Joe disowned that option's premise -- when
        # the earlier work said "sportsbook" he meant KALSHI'S sportsbook
        # (ADR 0113) -- and the hard-coded value is precondition P2 of the
        # successor registration for the `parlay_positions` census. The
        # 09-15 clause was vacated because the number of days a NEUTRAL
        # choice had been shown was 0, and a steer left in the prefill keeps
        # it at 0.
        #
        # Asserted over the PREFILL BLOCK, not the file: the comment above
        # the control quotes the removed line to say what it replaced, and a
        # guard that refused the quotation would forbid explaining the fix.
        # Same allowance `tests/test_combo_book_depth_claims.py` makes.
        start = source.index("prefill={{")
        block = source[start : source.index("}}", start)]
        assert "source:" not in block, (
            "the parlay card is steering `source` again. No default, not the "
            "other default -- a flipped steer is still a steer."
        )

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


class TestTheSourceQuestionIsNotAnsweredForHim:
    """**Precondition P2 of the successor registration.** Added 2026-09-08.

    The `parlay_positions` deletion clause dated 2026-09-15 was VACATED rather
    than deferred, and the reason was this form: it defaulted `source` to
    `"sportsbook"` and `ParlayCards.tsx` hard-coded the same value into its
    prefill, so **the number of days on which a neutral choice had been shown
    was 0.** A census taken against that form could not separate "hedging is
    unwanted" from "logging someone else's slip is unwanted", because only one
    of the two was ever offered as the resting answer.

    Joe then disowned the option's premise outright: when the earlier work
    said "sportsbook" he meant KALSHI'S sportsbook, and he bets through the
    cockpit into Kalshi (ADR 0113).

    **The fix is no default, not the other default.** A flipped steer is still
    a steer and would void the window for the same reason. The clean window
    opens at this code's deploy, so a silent regression here does not merely
    break a preference -- it restarts the clock on a measurement that has
    already been thrown away once.
    """

    def test_the_form_starts_with_no_source_chosen(self):
        form = (COMPONENTS / "RecordParlay.tsx").read_text(encoding="utf-8")
        start = form.index("const [source, setSource]")
        block = form[start : form.index(";", start)]
        assert 'prefill?.source ?? ""' in block, block
        for steer in ('?? "sportsbook"', '?? "kalshi_combo"'):
            assert steer not in block, (
                f"{steer} is back in the initial state. No default, not the "
                f"other default."
            )

    def test_the_empty_choice_is_offered_in_the_dropdown(self):
        """It must be selectable, not merely the initial value.

        A `<select>` whose only unchosen state is unreachable turns a mis-tap
        into a wrong recorded row, and the row is what the census reads.
        """
        form = (COMPONENTS / "RecordParlay.tsx").read_text(encoding="utf-8")
        assert '<option value="">' in form

    def test_an_unanswered_source_cannot_be_recorded(self):
        """Both halves: the button is disabled AND the submit refuses.

        The button alone is not enough -- a form can be submitted from the
        keyboard -- and `schemas.py` requires the field against a two-value
        pattern, so an empty string reaches the server as a 422 the reader
        cannot act on. The client says what to do instead.
        """
        form = " ".join(
            (COMPONENTS / "RecordParlay.tsx").read_text(encoding="utf-8").split()
        )
        assert 'disabled={busy || source === ""}' in form
        assert 'if (source === "")' in form
        assert "Choose where this ticket is" in form
