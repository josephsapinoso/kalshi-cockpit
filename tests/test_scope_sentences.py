"""The scope sentences name their channel and their source (ADR 0064 §3).

Scope sentences that outlive their wiring are how the last hole stayed open:
/gate advertised "a daily-loss kill switch" for weeks while the switch read
a structurally empty table, and the blanket sentence beside it ("they do not
see, and cannot stop, bets you place yourself") stopped being accurate the
day ADR 0064 rewired the switch to `venue_settlements` -- hand losses DO
count against the line now. These pins tie the words to the wiring so that
rewiring either one turns the screen's claim red instead of letting it age
in place.

**THIS FILE ITSELF PINNED A FALSE SENTENCE FOR THREE DAYS, AND THAT IS THE
LESSON WORTH MORE THAN THE GUARD.** From 2026-08-26 to 2026-08-29
`test_the_gate_does_not_claim_an_in_portal_order_path_yet` asserted that
/gate must keep saying hand bets "fire no check". Its own docstring named
the condition that would retire it -- "until the manual path (ADR 0063)
ships a button" -- and that button shipped: `MANUAL_ORDERS_ARE_DRY_RUNS`
went False on 2026-08-26 and `POST /api/manual-orders` began sending real
immediate-or-cancel orders behind a dozen server-side refusals. A guard
that verifies a lie is worse than no guard, because the next session reads
a green test as an established fact and stops checking. So the fix is not
to delete the pin -- it is to point it at what is true, and to make the
retirement condition something a test can see rather than something a
future reader has to notice.

The claim now pinned, in three parts, because dropping any one of them
produces a different falsehood:

1. the in-portal Buy button sends REAL orders, and the screen says so;
2. what guards it is named -- server-side checks, not the gate;
3. the gate's 300-game interlock does NOT cover hand bets and must not be
   described as if it does (`gate.py` never reads `manual_orders`), and the
   Kalshi *app* remains the door where nothing fires beforehand.

WHAT THIS DOES NOT ESTABLISH
----------------------------
That the sentences are true, or good prose -- only that the words which must
change with the wiring are present, and the superseded claim is gone. A
sentence can pass here and still mislead; the ADR review owns the meaning.

Nor that the count "a dozen" is right: nothing here counts the refusals in
`place_manual_order`. It pins that guards are NAMED, not how many there are.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATE = REPO / "frontend" / "src" / "app" / "gate" / "page.tsx"
STRIP = REPO / "frontend" / "src" / "components" / "TonightStrip.tsx"

#: Where a screen keeps its reasoning. One block pattern, not two: a JSX
#: `{/* ... */}` is a `/* ... */` inside braces, so stripping the block
#: strips it (the braces survive as `{ }`, which no assertion spans). A
#: separate JSX pattern was tried and stayed green when disabled, which
#: makes it decoration rather than a guard.
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"^\s*//.*$", re.MULTILINE)


def flat(path: Path) -> str:
    """The RENDERED prose, with runs of whitespace collapsed.

    Two things happen here and both are load-bearing. Whitespace collapses
    because JSX wraps a sentence across indented lines, so a sentence can be
    asserted as prose. Comments are stripped because a comment explaining a
    retired sentence quotes it verbatim -- and an assertion that a false
    sentence is GONE would then be satisfied by the file's own explanation of
    why it went. Only what a reader sees on the screen counts as the screen
    saying something.
    """
    source = path.read_text(encoding="utf-8")
    source = _BLOCK_COMMENT.sub(" ", source)
    source = _LINE_COMMENT.sub(" ", source)
    return re.sub(r"\s+", " ", source)


class TestTheScopeSentencesNameTheirChannel:
    def test_the_gate_names_the_daily_loss_switch_source(self):
        """ADR 0064 §3 verbatim requirement: the sentence describing the
        kill switch names its channel and its source ("the venue's settled
        record, refused when stale")."""
        source = flat(GATE)
        assert "settled record" in source, (
            "/gate no longer says the daily-loss switch reads the venue's "
            "settled record; if the wiring changed, change ADR 0064 first"
        )
        assert "refused when" in source or "refuses" in source, (
            "/gate no longer says the switch refuses on a stale mirror"
        )

    def test_the_gate_dropped_the_blanket_blindness_claim(self):
        """The pre-0064 sentence said the caps "do not see" hand bets --
        false since the switch's denominator became `venue_settlements`."""
        source = flat(GATE)
        assert "They do not see, and cannot stop" not in source, (
            "the superseded scope sentence is back; hand losses have "
            "counted against the daily-loss line since ADR 0064"
        )

    def test_the_gate_says_the_in_portal_buy_button_sends_real_orders(self):
        """Part 1. The manual path is armed (`MANUAL_ORDERS_ARE_DRY_RUNS`
        False, 2026-08-26, ADR 0073), so the screen that exists to say what
        can move money must say that this button moves it. Silence here is
        the falsehood the old version of this test protected."""
        source = flat(GATE)
        assert "it sends real orders" in source, (
            "/gate no longer says the in-portal Buy button sends REAL "
            "orders. If MANUAL_ORDERS_ARE_DRY_RUNS went back to True, "
            "disarm it in ADR form first and rewrite this test to match; "
            "do not let the screen go quiet about a live order path"
        )

    def test_the_gate_names_what_actually_guards_a_hand_bet(self):
        """Part 2. "Nothing stops it" was the old lie; "the gate stops it"
        would be the new one. What stops it is a stack of server-side
        refusals on `place_manual_order`, and the screen names them so the
        reader knows which one to expect."""
        source = flat(GATE)
        assert "checks the server runs before the order leaves" in source, (
            "/gate no longer says the in-portal order is checked "
            "server-side before it is sent"
        )
        for guard in (
            "the desk lockout",
            "cool-off",
            "the daily-loss switch",
            "a refusal if the ask has moved above the price you agreed to",
            "a refusal if you already hold this market",
        ):
            assert guard in source, (
                f"/gate stopped naming {guard!r} as a guard on the "
                f"in-portal Buy button; if that check was removed from "
                f"`place_manual_order`, say so in an ADR first"
            )

    def test_the_gate_keeps_the_interlock_off_the_hand_bet_path(self):
        """Part 3, and the one that must never be lost. `gate.py` does not
        read `manual_orders` and must not: arming the button did not arm
        the engine, so the 300-game count is not a guard on hand bets and
        the screen may not imply it is."""
        source = flat(GATE)
        assert "did not arm the engine" in source, (
            "/gate no longer distinguishes the two doors. The 300-game "
            "interlock guards the automated engine only; a screen that "
            "blurs that reads as if the gate vets hand bets, which "
            "`gate.py` has never done"
        )
        assert "The 300-game count does not cover it" in source, (
            "/gate no longer says the interlock does not cover the "
            "in-portal Buy button"
        )

    def test_the_no_check_claim_is_scoped_to_the_kalshi_app(self):
        """The surviving true half. A bet placed in Kalshi's OWN app fires
        nothing here beforehand -- but the sentence is only true with that
        scope on it, and unscoped it is exactly the sentence this file used
        to pin. Every occurrence must carry the scope."""
        source = flat(GATE)
        assert "in the Kalshi app fires no check" in source, (
            "/gate stopped saying a bet placed in Kalshi's own app fires "
            "no check before it happens; that door is still open and the "
            "screen must still say so"
        )
        unscoped = [
            m.start()
            for m in re.finditer(r"fires no check", source)
            if not source[: m.start()].endswith("in the Kalshi app ")
        ]
        assert not unscoped, (
            "/gate says 'fires no check' without scoping it to the Kalshi "
            "app. Unscoped it covers the in-portal Buy button too, which "
            "runs a dozen server-side refusals -- the exact false sentence "
            "this test file pinned from 2026-08-26 to 2026-08-29"
        )

    def test_the_gate_dropped_the_never_carried_an_order_claim(self):
        """The other half of the same staleness. "Orders placed through
        this tool -- a channel that has never carried one" was true of the
        engine and false of the Buy button from the day it was armed."""
        source = flat(GATE)
        assert "a channel that has never carried one" not in source, (
            "the superseded scope sentence is back; the in-portal Buy "
            "button has carried real orders since 2026-08-26"
        )
        assert "the only act any of these caps can stop" not in source, (
            "the superseded scope sentence is back; the caps also stop "
            "the in-portal Buy button's order"
        )

    def test_the_strip_aligns_with_the_gate(self):
        """TonightStrip's locked note is the other place the scope claim
        renders; the two must not drift apart."""
        source = flat(STRIP)
        assert "cannot stop a bet placed in the Kalshi app" in source
        assert "settled record" in source, (
            "TonightStrip's locked note no longer names the venue's "
            "settled record as the after-the-fact witness"
        )
