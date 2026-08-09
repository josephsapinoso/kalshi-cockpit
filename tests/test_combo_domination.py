"""The domination verdict, and the honesty of its refusals.

A combination is dominated when it costs more than buying its cheapest leg on
that leg's own side -- more money for a strictly smaller set of winning states.
The arithmetic is trivial; everything that can go wrong here is a substitution
made where a refusal was correct.

What these tests do not establish
---------------------------------
That any combination in the live capture *is* dominated. They establish that
the comparison is made at the price actually paid, that a NO leg is costed
against the bid, that an unjudgeable combination yields nothing rather than a
number, and that a missing timestamp is `unknown` rather than zero -- because
bucketing an unknown age at 0 would hide the staleness confound the age control
exists to expose.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / filename
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


acd = _load("analyse_combo_domination_under_test", "analyse_combo_domination.py")


def _record(legs, quotes, *, joint_ask, created_ms=None, observed_ms=None,
            scope="same_game"):
    return {
        "ticker": "KXMVE-T",
        "scope": scope,
        "legs": legs,
        "leg_quotes": quotes,
        "joint_ask": joint_ask,
        "created_ms": created_ms,
        "joint_observed_ms": observed_ms,
    }


class TestTheCheapestLegIsPricedOnTheSideTaken:
    """The NO side costs `1 - bid`, and it decides which leg is cheapest.

    Anchored so a wrong convention changes the *answer*, not just a decimal:
    under `1 - ask` the NO leg looks cheaper than the YES leg and the verdict
    flips from dominated to not. `tasks/lessons.md` records that a definitional
    anchor only helps when the candidate errors disagree there.
    """

    LEGS = [
        {"market_ticker": "KXA-26AUG09AAABBB-X", "side": "yes"},
        {"market_ticker": "KXB-26AUG09AAABBB-Y", "side": "no"},
    ]
    # YES leg costs its ask, 0.60.
    # NO leg costs 1 - bid = 1 - 0.55 = 0.45 -- so NO is cheapest, at 0.45.
    # Under the wrong rule (1 - ask) it would read 0.35.
    QUOTES = [
        {"bid": 0.55, "ask": 0.60, "observed_ms": 1000},
        {"bid": 0.55, "ask": 0.65, "observed_ms": 1000},
    ]

    def test_the_no_leg_is_costed_against_the_bid(self):
        verdict = acd.verdict_for(
            _record(self.LEGS, self.QUOTES, joint_ask=0.50,
                    created_ms=0, observed_ms=1000)
        )
        assert verdict is not None
        assert verdict.cheapest_leg_cost == pytest.approx(0.45)
        assert verdict.cheapest_leg_ticker == "KXB-26AUG09AAABBB-Y"

    def test_a_combination_dearer_than_its_cheapest_leg_is_dominated(self):
        verdict = acd.verdict_for(
            _record(self.LEGS, self.QUOTES, joint_ask=0.50,
                    created_ms=0, observed_ms=1000)
        )
        assert verdict.dominated
        assert verdict.margin == pytest.approx(0.05)

    def test_a_combination_cheaper_than_every_leg_is_not_dominated(self):
        """The normal case. A joint below the cheapest leg is what dependence
        allows and says nothing on its own."""
        verdict = acd.verdict_for(
            _record(self.LEGS, self.QUOTES, joint_ask=0.30,
                    created_ms=0, observed_ms=1000)
        )
        assert not verdict.dominated
        assert verdict.margin < 0


class TestAnUnjudgeableCombinationYieldsNothing:
    def test_a_leg_with_no_ask_refuses_the_whole_combination(self):
        """The cheapest leg is a minimum, and a minimum over an incomplete set
        is not a minimum. Dropping the unreadable leg would silently raise the
        floor and manufacture domination."""
        legs = [
            {"market_ticker": "KXA-26AUG09AAABBB-X", "side": "yes"},
            {"market_ticker": "KXB-26AUG09AAABBB-Y", "side": "yes"},
        ]
        quotes = [{"bid": 0.55, "ask": 0.60}, {"bid": None, "ask": None}]
        assert acd.verdict_for(_record(legs, quotes, joint_ask=0.50)) is None

    def test_a_no_leg_with_no_bid_refuses(self):
        legs = [{"market_ticker": "KXA-26AUG09AAABBB-X", "side": "no"}]
        quotes = [{"bid": None, "ask": 0.60}]
        assert acd.verdict_for(_record(legs, quotes, joint_ask=0.50)) is None

    def test_a_capture_predating_leg_quotes_yields_no_verdicts_at_all(self):
        """The 55-minute run of 2026-08-09 carries no `leg_quotes`.

        `start.md` claimed leg bids and asks were recorded "as of the last
        run", which would have meant the domination question was answerable
        from stored data. It is not: the field reached the writer after that
        run. This test states that as an invariant so the claim cannot drift
        back, and so a future capture that silently loses the field is caught.
        """
        capture = ROOT / "docs" / "measurements" / (
            "2026-08-09-combo-correlation-55min.json"
        )
        payload = json.loads(capture.read_text(encoding="utf-8"))
        records = payload["measurements"]
        assert len(records) > 100, "capture is thinner than expected"
        assert all(not r.get("leg_quotes") for r in records)
        assert all(acd.verdict_for(r) is None for r in records)


class TestAMissingStampIsUnknownAndNeverZero:
    """Bucketing an unknown age at 0 would put every un-timestamped
    combination in the freshest bucket -- which is exactly where a staleness
    artefact would be hidden from the control designed to find it."""

    LEGS = [{"market_ticker": "KXA-26AUG09AAABBB-X", "side": "yes"}]
    QUOTES = [{"bid": 0.55, "ask": 0.60, "observed_ms": 1000}]

    def test_no_created_ms_gives_an_age_of_none(self):
        verdict = acd.verdict_for(
            _record(self.LEGS, self.QUOTES, joint_ask=0.70, observed_ms=1000)
        )
        assert verdict is not None
        assert verdict.age_ms is None

    def test_no_leg_stamp_gives_a_gap_of_none(self):
        verdict = acd.verdict_for(
            _record(self.LEGS, [{"bid": 0.55, "ask": 0.60}],
                    joint_ask=0.70, observed_ms=1000)
        )
        assert verdict is not None
        assert verdict.gap_ms is None

    def test_a_stamped_pair_reports_the_real_gap(self):
        verdict = acd.verdict_for(
            _record(self.LEGS, self.QUOTES, joint_ask=0.70,
                    created_ms=0, observed_ms=61_000)
        )
        assert verdict.age_ms == 61_000
        assert verdict.gap_ms == 60_000


class TestTheLegEchoIsDetected:
    """The artefact that killed the first reading of this measurement.

    86% of dominated rows in the 2026-08-09 capture had a combination ask equal
    to one of their own legs' costs to within 2c, against a 3-7% base rate.
    Excluding them took cross-game domination from 11.1% to 1.9% and same-game
    from 18.3% to 3.3%. It has to be detected before any rate is printed, not
    discovered afterwards by someone auditing the conclusion.
    """

    def test_an_ask_equal_to_a_leg_is_flagged_as_an_echo(self):
        legs = [
            {"market_ticker": "KXA-26AUG09AAABBB-X", "side": "yes"},
            {"market_ticker": "KXB-26AUG09AAABBB-Y", "side": "yes"},
        ]
        quotes = [{"bid": 0.15, "ask": 0.18}, {"bid": 0.75, "ask": 0.78}]
        v = acd.verdict_for(_record(legs, quotes, joint_ask=0.78))
        assert v.echoes_a_leg

    def test_matching_a_dearer_leg_is_flagged_separately(self):
        """The discriminator, and the reason the echo is not just staleness.

        Dependence can only push a joint toward the CHEAPEST leg. An ask sitting
        on a dearer leg is above `min(marginal)`, which no dependence structure
        produces -- so it cannot be a mispriced joint at all. 119 rows in the
        capture do this.
        """
        legs = [
            {"market_ticker": "KXA-26AUG09AAABBB-X", "side": "yes"},
            {"market_ticker": "KXB-26AUG09AAABBB-Y", "side": "yes"},
        ]
        quotes = [{"bid": 0.15, "ask": 0.18}, {"bid": 0.75, "ask": 0.78}]
        v = acd.verdict_for(_record(legs, quotes, joint_ask=0.78))
        assert v.echoes_a_dearer_leg, "0.78 is the dearer leg, not the cheapest"

        cheap = acd.verdict_for(_record(legs, quotes, joint_ask=0.18))
        assert cheap.echoes_a_leg
        assert not cheap.echoes_a_dearer_leg

    def test_an_ordinary_joint_is_not_an_echo(self):
        """Below both legs, which is where dependence puts a real joint."""
        legs = [
            {"market_ticker": "KXA-26AUG09AAABBB-X", "side": "yes"},
            {"market_ticker": "KXB-26AUG09AAABBB-Y", "side": "yes"},
        ]
        quotes = [{"bid": 0.15, "ask": 0.18}, {"bid": 0.75, "ask": 0.78}]
        v = acd.verdict_for(_record(legs, quotes, joint_ask=0.12))
        assert not v.echoes_a_leg
        assert not v.dominated


class TestANegativeAgeIsNotSilentlyDropped:
    """69 of 2,116 rows had a negative age and vanished from the age table.

    The first bucket required `age_ms >= 0`, so they fell through every bucket
    without reaching the `unknown` line -- a silent drop inside the table built
    to catch confounds. A combination cannot be observed before it was minted,
    so a negative age means the stamp is wrong and every age is suspect.
    """

    def test_a_negative_age_is_kept_and_readable(self):
        legs = [{"market_ticker": "KXA-26AUG09AAABBB-X", "side": "yes"}]
        quotes = [{"bid": 0.55, "ask": 0.60, "observed_ms": 1_000}]
        v = acd.verdict_for(
            _record(legs, quotes, joint_ask=0.70,
                    created_ms=61_000, observed_ms=1_000)
        )
        assert v.age_ms == -60_000, "a negative age must survive, not become None"
