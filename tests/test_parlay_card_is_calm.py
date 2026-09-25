"""The parlay card is a calm summary, and buying happens in a panel (#158).

Joe, 2026-09-25: an expanded card "gets over-filled with info". The cause was
structural: three buy flows unfolded three deep inside a card about 277px
wide, with up to three filled buttons visible at once. He chose the
slide-over panel. These tests pin the properties that make that change safe
as well as calm:

- the card itself wears no filled button (the fill is for spending);
- the grid does not squeeze cards to three columns below the widest screens;
- the panel never unmounts what it holds, because a receipt or an UNKNOWN
  acceptance must survive a close;
- the panel will not close while an order or an acceptance is in flight;
- opening the panel spends nothing: the legs tab's verdict request fires
  from the tap that chooses the tab, never from a mount.

**What these tests do not establish.** They read source text; there is no
DOM test runner in this repo. They cannot see layout, focus order at run
time, or whether the panel looks right at 390px. That is checked by
screenshot on the live instance, recorded in the session's NEXT.md entry.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "frontend" / "src" / "components"
CARDS = COMPONENTS / "ParlayCards.tsx"
SHEET = COMPONENTS / "Sheet.tsx"
TICKET = COMPONENTS / "ManualTicket.tsx"
ASK = COMPONENTS / "AskTheMarket.tsx"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    end = source.find("\nfunction ", start + 1)
    return source[start:] if end == -1 else source[start:end]


class TestTheCardIsASummary:
    def test_the_card_wears_no_filled_button(self):
        """Opening the panel spends nothing, so the card's one way in is
        outlined. Mutation observed red: `tone="primary"` on the Buy
        button."""
        source = _read(CARDS)
        filled = [
            line
            for line in source.splitlines()
            if "className=" in line and "bg-accent-fill" in line
        ]
        assert filled == [], filled
        assert 'tone="primary"' not in source

    def test_the_chart_and_the_stake_estimate_sit_behind_the_tap(self):
        """Joe, 2026-09-25, by option button: both come off the card face
        into "How these numbers were made"; neither is deleted. Mutation
        observed red: mount `<Stakes` back in `Card`."""
        source = _read(CARDS)
        card = _function(source, "Card")
        assert "<ParlayDifficulty" not in card
        assert "<Stakes" not in card
        made = _function(source, "HowTheseNumbersWereMade")
        assert "<ParlayDifficulty" in made
        assert "<Stakes card={card} />" in made

    def test_cards_are_not_three_across_below_the_widest_screens(self):
        """Mutation observed red: restore `lg:grid-cols-3`."""
        source = _read(CARDS)
        assert "lg:grid-cols-3" not in source
        assert "md:grid-cols-2 2xl:grid-cols-3" in source

    def test_the_verdicts_render_once_per_view_on_the_card_file(self):
        """The card's scouts block and the legs tab each draw verdicts; the
        whole-parlay tab draws its own in `PriceOnKalshi`. A third mount in
        this file would bring back the repetition #158 removed."""
        # A mount, not a mention: comments name `<LegVerdicts>` and the
        # types name `LegVerdictsResult`.
        assert len(re.findall(r"<LegVerdicts\s", _read(CARDS))) == 2


class TestThePanelKeepsWhatItHolds:
    def test_a_closed_sheet_is_hidden_not_unmounted(self):
        """Mutation observed red: `if (!open) return null;` in Sheet."""
        source = _read(SHEET)
        assert "hidden={!open}" in source
        assert not re.search(r"if\s*\(\s*!open\s*\)\s*return\s+null", source)

    def test_the_card_mounts_its_sheet_once_and_toggles_open(self):
        """Mutation observed red: `{buyOpen && (` around the sheet."""
        card = _function(_read(CARDS), "Card")
        assert "{mounted && (" in card
        assert "open={buyOpen}" in card
        assert "buyOpen && (" not in card

    def test_a_shown_tab_stays_mounted_when_another_is_chosen(self):
        """Mutation observed red: `tab === "legs" &&` in place of the
        `seen` gate."""
        tabs = _function(_read(CARDS), "BuyTabs")
        for key in ("whole", "legs", "record"):
            assert f'seen.has("{key}") &&' in tabs, key
            assert f'hidden={{tab !== "{key}"}}' in tabs, key


class TestThePanelWillNotCloseMidSend:
    def test_escape_and_the_backdrop_refuse_while_busy(self):
        """Mutation observed red: delete the in-flight check from either
        the Escape branch or `tryClose`."""
        source = _read(SHEET)
        escape = source[source.index('event.key === "Escape"'):]
        escape = escape[: escape.index("close.current();")]
        assert "if (inFlight.current.size > 0) return;" in escape
        try_close = source[source.index("const tryClose"):]
        try_close = try_close[: try_close.index("};")]
        assert "if (inFlight.current.size > 0) return;" in try_close
        assert "onClick={tryClose}" in source

    def test_the_ticket_itself_will_not_close_mid_send(self):
        """The Sheet's guard is only as good as the ticket's own: before the
        #158 review, ManualTicket's Escape and Close cleared the phase (and
        the intent key) mid-send, released the Sheet's busy lock, and made a
        second order with a fresh key reachable. Mutation observed red:
        drop the `sending` condition from either."""
        source = _read(TICKET)
        assert (
            'if (event.key === "Escape" && phase.name !== "sending") close();'
            in source
        )
        assert 'disabled={phase.name === "sending"}' in source

    def test_asking_again_cannot_discard_a_take(self):
        """"Ask again" unmounts the quote block and TakeIt with it, whose
        answer can be an UNKNOWN with no retry. It stands down once a take
        has started. Mutation observed red: render it unconditionally."""
        source = _read(ASK)
        assert '{takeKind === "idle" && (\n            <RetryButton' in (
            source.replace("\r\n", "\n")
        )

    def test_both_spending_controls_report_their_request(self):
        """Mutation observed red: remove either `useReportBusy` call."""
        assert 'useReportBusy(phase.name === "sending");' in _read(TICKET)
        take = _function(_read(ASK), "TakeIt")
        assert 'useReportBusy(state.kind === "sending");' in take


class TestOpeningThePanelSpendsNothing:
    def test_the_legs_verdict_request_fires_from_the_tab_choice(self):
        """Mutation observed red: move the request into a `useEffect` in
        `LegBuys`."""
        tabs = _function(_read(CARDS), "BuyTabs")
        choose = tabs[tabs.index("const choose = "):]
        choose = choose[: choose.index("\n  };")]
        assert 'requestLegVerdicts(legInputs, "leg_buys_open"' in choose
        assert "useEffect" not in tabs
        leg_buys = _function(_read(CARDS), "LegBuys")
        assert "requestLegVerdicts" not in leg_buys
        assert "useEffect" not in leg_buys
