"""#321: the Price-on-Kalshi sentence states the fact and issues no verdict.

The served sentence used to end "...so this is -Y% EV. Don't." or "+Z% EV.
Rare -- verify the legs...". Both are a verdict on Joe's behalf (ADR 0071
2.1: the desk informs, it does not abstain for him) and a fee-net EV on a
combination overstates by construction (ADR 0046). The sentence now carries
the fact the tiles already show: Kalshi's ask, the books' fair value, the hold.

What this does not establish: that the numbers in the sentence are right (the
valuation tests pin those), only that no verdict word travels with them.
"""
from __future__ import annotations

import re
from pathlib import Path

from backend.core.correlation import Leg
from backend.core.parlay import ParlayQuote, american_to_decimal, value_parlay

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "frontend" / "src" / "components" / "PriceOnKalshi.tsx"

NOW = 1_800_000_000_000
DAY = 86_400_000
VERDICT_WORDS = re.compile(r"Don't|Rare|\bEV\b")


def _quote(offered_american: int) -> ParlayQuote:
    legs = (
        Leg(label="A", probability=0.50, event_key="E1",
            league="americanfootball_nfl", commence_ms=NOW),
        Leg(label="B", probability=0.50, event_key="E2",
            league="americanfootball_nfl", commence_ms=NOW + 8 * DAY),
        Leg(label="C", probability=0.53, event_key="E3",
            league="americanfootball_nfl", commence_ms=NOW + 16 * DAY),
    )
    return ParlayQuote(legs=legs, offered_decimal=american_to_decimal(offered_american))


class TestNoVerdictSentence:
    def test_a_priced_card_below_fair_carries_no_verdict_word(self):
        sentence = value_parlay(_quote(+550)).verdict
        assert not VERDICT_WORDS.search(sentence), sentence

    def test_a_priced_card_above_fair_carries_no_verdict_word(self):
        valuation = value_parlay(_quote(+900))
        assert valuation.is_positive_ev
        assert not VERDICT_WORDS.search(valuation.verdict), valuation.verdict

    def test_the_sentence_is_the_ask_the_fair_value_and_the_hold(self):
        valuation = value_parlay(_quote(+550))
        ask = 100.0 / valuation.offered_decimal
        fair = 100.0 / valuation.fair_decimal
        assert valuation.verdict == (
            f"Kalshi's ask is {ask:.1f}c against the books' fair value of "
            f"{fair:.1f}c; hold {valuation.hold * 100:.1f}%."
        )

    def test_the_component_source_carries_no_verdict_word(self):
        source = COMPONENT.read_text(encoding="utf-8")
        assert not VERDICT_WORDS.search(source), [
            m.group(0) for m in VERDICT_WORDS.finditer(source)
        ]
