"""#410 (epic #407, lane C): user-facing sentences must not contradict the record.

Assertions are over SOURCE TEXT (the repo has no JS test runner). They prove the
sentence is written and the old wording is gone; they do not prove it reaches
the DOM or that a reader understands it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"


def _read(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    """Collapse whitespace and JSX/string-concat seams so wrapped copy matches."""
    text = re.sub(r'"\s*\+\s*"', "", text)
    text = text.replace("&rsquo;", "’").replace("&hellip;", "…")
    return re.sub(r"\s+", " ", text)


def _frozen_block() -> str:
    src = _read("components/SignalStrip.tsx")
    start = src.index("if (!signal.available && signal.frozen)")
    end = src.index("if (!signal.available) {")
    return _flat(src[start:end])


class TestFrozenSignalSaysUnresolved:
    def test_frozen_unavailable_renders_the_registered_sentence(self):
        block = _frozen_block()
        assert "UNRESOLVED" in block
        assert (
            "The registered test ended UNRESOLVED on 2026-10-01; what this box "
            "recomputes on later rows is not that result." in block
        )

    def test_frozen_block_never_says_no_look_or_no_signal(self):
        block = _frozen_block().lower()
        assert "no look was taken" not in block
        assert "no signal" not in block

    def test_frozen_block_carries_no_beta_numbers(self):
        block = _frozen_block()
        assert "beta_hat" not in block and "interval" not in block

    def test_frozen_branch_precedes_the_early_return(self):
        src = _read("components/SignalStrip.tsx")
        assert src.index("signal.available && signal.frozen") < src.index(
            "if (!signal.available) {"
        )

    def test_false_comment_and_dead_branch_are_gone(self):
        flat = _flat(_read("components/SignalStrip.tsx"))
        assert "This is the demo instance's normal state" not in flat
        assert "to go. Every interval measured so far" not in flat
        assert "the rule says wait" not in flat


class TestFiveStepTest:
    def test_hunt_sentence(self):
        flat = _flat(_read("components/FiveStepTest.tsx"))
        assert "found none it could use." in flat
        assert (
            "The main test ended unresolved: no evidence of an edge, which is "
            "not proof there is none." in flat
        )
        assert "measured that there wasn’t one" not in flat

    def test_fee_bar_sentence(self):
        flat = _flat(_read("components/FiveStepTest.tsx"))
        assert "the desk assumes you must be right about 51.75%" in flat
        assert "about 50.9%" in flat
        assert "unchecked" in flat
        assert "you must be right about 51.75% of the time simply to break even" not in flat


class TestGlossary:
    def _g(self) -> str:
        return _flat(_read("lib/glossary.ts"))

    def test_breakeven_fee_bar(self):
        g = self._g()
        assert "the desk assumes you need about 51.75%" in g
        assert "about 50.9%" in g and "is unchecked" in g
        assert "Pay 50c and you need about 51.75%" not in g

    def test_rfq_and_maker_drop_timing_and_agreement_claims(self):
        g = self._g()
        assert "send back private prices. That is why" in g
        assert "for a few seconds" not in g
        assert "Several usually answer at once" not in g
        assert "rarely agree" not in g

    def test_range_treats_bets_as_separate(self):
        g = self._g()
        assert (
            "The range treats each bet as separate. Bets that share a leg or a "
            "game win or lose together, so the real range is wider." in g
        )

    def test_game_script_card_has_no_count(self):
        g = self._g()
        assert "A short story for each game and the same-game picks that fit it." in g
        assert "two or three picks" not in g

    def test_consensus_chance_is_the_desks_estimate(self):
        g = self._g()
        assert "It is the desk's best estimate" in g
        assert "It is the best estimate available" not in g


class TestAskTheMarket:
    def test_no_promise_about_how_fast_makers_answer(self):
        flat = _flat(_read("components/AskTheMarket.tsx"))
        assert "makers usually answer" not in flat
        assert "well under a second" not in flat
        assert "Asking the market…" in flat


class TestGameLegsDemoState:
    def test_router_string_mapped_to_demo_sentence(self):
        flat = _flat(_read("components/GameLegs.tsx"))
        assert "No Kalshi credentials on this instance." in flat
        assert (
            "This demo isn\\u2019t connected to Kalshi, so a game\\u2019s bets "
            "can\\u2019t be listed here." in flat
        )
        assert "error === NO_CREDENTIALS_FROM_ROUTER ? DEMO_NOT_CONNECTED : error" in flat

    def test_no_hint_to_add_credentials(self):
        flat = _flat(_read("components/GameLegs.tsx")).lower()
        assert "add credentials" not in flat and "set credentials" not in flat

    def test_router_not_edited(self):
        router = (ROOT / "backend/api/routers/game.py").read_text(encoding="utf-8")
        assert 'detail="No Kalshi credentials on this instance."' in router


class TestLandingComment:
    def test_board_is_not_described_as_one_tap_away(self):
        flat = _flat(_read("app/page.tsx"))
        assert "one tap away at `/board`" not in flat
        assert "ADR 0195" in flat
