"""The scope sentences name their channel and their source (ADR 0064 §3).

Scope sentences that outlive their wiring are how the last hole stayed open:
/gate advertised "a daily-loss kill switch" for weeks while the switch read
a structurally empty table, and the blanket sentence beside it ("they do not
see, and cannot stop, bets you place yourself") stopped being accurate the
day ADR 0064 rewired the switch to `venue_settlements` -- hand losses DO
count against the line now. These pins tie the words to the wiring so that
rewiring either one turns the screen's claim red instead of letting it age
in place.

WHAT THIS DOES NOT ESTABLISH
----------------------------
That the sentences are true, or good prose -- only that the words which must
change with the wiring are present, and the superseded claim is gone. A
sentence can pass here and still mislead; the ADR review owns the meaning.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATE = REPO / "frontend" / "src" / "app" / "gate" / "page.tsx"
STRIP = REPO / "frontend" / "src" / "components" / "TonightStrip.tsx"


def flat(path: Path) -> str:
    """The file with runs of whitespace collapsed, so a sentence can be
    asserted as prose: JSX wraps sentences across indented lines."""
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


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

    def test_the_gate_does_not_claim_an_in_portal_order_path_yet(self):
        """Honesty in the other direction: until the manual path (ADR 0063)
        ships a button, the gate must still say hand bets fire no check --
        the caps' only stoppable act is this tool's own order."""
        source = flat(GATE)
        assert "fires no check" in source, (
            "/gate stopped saying a hand bet in the Kalshi app fires no "
            "check before it happens; only remove this once the manual "
            "order path actually carries Joe's bets"
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
