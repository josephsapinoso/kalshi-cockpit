"""Recommendation engine tests.

The two behaviours worth guarding hardest:

1. **Suppressed candidates are still stored and still scored.** Dropping them
   would make 300 CLV observations require 300 wagers, and would turn the
   suppression log from evidence into a bin.
2. **Every row carries its `strategy_config_version`.** Without it the learning
   loop cannot tell whether a threshold change helped.
"""

from __future__ import annotations

import pytest

from backend.config import RiskConfig
from backend.core.devig import devig
from backend.core.suppression import SuppressionConfig
from backend.engine import (
    Candidate,
    build_recommendation,
    ensure_strategy_config,
    persist_recommendation,
    suppression_summary,
)
from backend.store import db

RISK = RiskConfig(
    bankroll_dollars=1000.0, kelly_fraction=0.25, max_order_contracts=50,
    max_position_dollars=100.0, max_exposure_dollars=400.0,
    max_daily_loss_dollars=100.0,
)
SUPPRESSION = SuppressionConfig()
NOW = 1_754_800_000_000


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "engine.db")
    c.execute(
        "INSERT INTO kalshi_markets (ticker, first_seen_ms, last_seen_ms) "
        "VALUES ('KXMLBGAME-26AUG09HOUSD-HOU', 0, 0)"
    )
    # recommendations.strategy_config_version is a foreign key -- a row cannot
    # exist without the config that produced it, by design.
    for version in (1, 7):
        c.execute(
            "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
            "config_json, rationale) VALUES (?, 0, 0, '{}', 'test')",
            (version,),
        )
    c.commit()
    yield c
    c.close()


def candidate(**overrides) -> Candidate:
    """A candidate with a genuine but *realistic* edge.

    Consensus fairs Houston near 53.9c; Kalshi asks 50.5c. That is ~3.4c gross
    and ~2.4c after fees -- the size of edge this venue plausibly offers.

    Worth recording how this fixture was chosen: the first version asked 46c,
    giving ~8 points of edge, and the suppression layer correctly flagged it as
    `suspicious_edge`. The safety net caught a hand-picked example on its first
    run, which is a reasonable sign it is calibrated somewhere near reality.
    """
    args = dict(
        ticker="KXMLBGAME-26AUG09HOUSD-HOU",
        side="yes",
        outcome_name="Houston",
        ask_tenths=505,
        depth_at_ask=500.0,
        kalshi_quote_age_ms=3_000,
        link_id=None,
        fair_price_id=None,
        devig=devig(["Houston", "San Diego"], [1.80, 2.10]),
        book_count=4,
        market_width=0.01,
        odds_age_ms=60_000,
        commence_skew_ms=0,
    )
    args.update(overrides)
    return Candidate(**args)


def build(cand: Candidate, **overrides):
    args = dict(
        risk=RISK,
        suppression=SUPPRESSION,
        strategy_config_version=1,
        # A clean book, stated. `build_recommendation` has no defaults for the
        # three risk-state inputs any more: an omission there used to become a
        # zero, which is how the daily loss limit came to be applied to a number
        # nothing in production supplied. Individual tests override these.
        current_exposure_dollars=0.0,
        current_position_dollars=0.0,
        daily_pnl_dollars=0.0,
        created_ms=NOW,
    )
    args.update(overrides)
    return build_recommendation(cand, **args)


class TestSurfacing:
    def test_a_genuine_edge_surfaces_with_a_size(self):
        rec = build(candidate())
        assert rec.surfaced, rec.reason_text
        assert rec.suggested_contracts > 0
        assert rec.edge_tenths > 0

    def test_the_reason_leads_with_fair_versus_what_you_pay(self):
        """Written for a few seconds on a phone, not for a log reader."""
        rec = build(candidate())
        assert "Houston" in rec.reason_text
        assert "fair" in rec.reason_text
        assert "asks" in rec.reason_text

    def test_no_edge_produces_a_row_with_no_size(self):
        """Kalshi asking above fair is the common case, not an error."""
        rec = build(candidate(ask_tenths=700))
        assert rec.suggested_contracts == 0
        assert not rec.surfaced

    def test_the_reason_reports_a_size_and_does_not_instruct(self):
        """Indicative, not imperative -- ADR 0038.

        `beta = -0.141` refuted that `edge_tenths` predicts Kalshi's close. The
        comparison in the head survives that; the instruction does not. A tool
        whose registered statistic says its edge number carries no information
        may report a size, but may not tell anyone to take it.

        This is pinned because the offending string was one word and read as
        natural product copy for the life of the project -- exactly the kind of
        edit a future session restores without noticing it is a claim.
        """
        rec = build(candidate())
        assert rec.surfaced, rec.reason_text
        assert f"Sized at {rec.suggested_contracts}." in rec.reason_text
        for imperative in ("Buy ", "Bet ", "Take ", "Back "):
            assert imperative not in rec.reason_text, (
                f"reason_text instructs the reader: {rec.reason_text!r}"
            )

    def test_the_size_is_still_reported(self):
        """The count stays even though the verb went.

        `reference_contracts` is what the gate's `actionable` predicate counts,
        so dropping the number to make the sentence read better would change
        what is measured in order to reach a target. Record the number; drop
        the verb -- both halves are load-bearing.
        """
        rec = build(candidate())
        assert str(rec.suggested_contracts) in rec.reason_text


class TestSuppressionIsRecordedNotDropped:
    def test_a_stale_quote_suppresses_but_still_produces_a_row(self):
        rec = build(candidate(kalshi_quote_age_ms=600_000))
        assert rec.suppressed_reason
        assert "stale_kalshi_quote" in rec.suppressed_reason
        assert rec.suggested_contracts == 0
        assert rec.fair_probability > 0, "the row must still carry its evidence"

    def test_a_suspicious_edge_is_suppressed(self):
        """Kalshi asking 20c on something fair at 54c is a defect, not a gift."""
        rec = build(candidate(ask_tenths=200))
        assert "suspicious_edge" in rec.suppressed_reason

    def test_unfillable_depth_suppresses(self):
        rec = build(candidate(depth_at_ask=2.0))
        assert "insufficient_depth" in rec.suppressed_reason

    def test_a_suppressed_row_still_records_the_edge_for_later_analysis(self):
        rec = build(candidate(kalshi_quote_age_ms=600_000))
        assert rec.edge_tenths != 0.0

    def test_multiple_failures_are_all_named(self):
        rec = build(candidate(kalshi_quote_age_ms=600_000, depth_at_ask=1.0))
        assert "stale_kalshi_quote" in rec.suppressed_reason
        assert "insufficient_depth" in rec.suppressed_reason


class TestSizingInteraction:
    def test_unreadable_exposure_blocks_the_bet(self):
        rec = build(candidate(), current_exposure_dollars=None)
        assert rec.suggested_contracts == 0
        assert rec.suppressed_reason

    def test_the_kill_switch_blocks_the_bet(self):
        rec = build(candidate(), daily_pnl_dollars=-500.0)
        assert rec.suggested_contracts == 0

    def test_edge_is_computed_at_the_size_actually_sent(self):
        """Fees round up on the whole order, so a per-contract edge computed
        independently of size is wrong for every size but one.

        **The ask is overridden to 48.1c, and that override IS the test.** At
        the fixture's default 50.5c both sizes yield an identical edge, so the
        assertion could not tell "the engine passes the real size" from "the
        engine assumes 1". This is `tests/test_fees.py`'s at-the-money-anchor
        lesson in a second place: an anchor that agrees under both hypotheses
        proves neither.

        **Why it stopped discriminating, and it is worth knowing.** Near 50c,
        `0.07 * C * P * (1-P)` is `0.0175 * C`, which lands exactly on the
        $0.0001 grid for every integer `C` -- so the per-order ceiling does not
        round at all and the fee is exactly proportional to size. While fees
        rounded to the CENT the ceiling bit almost everywhere and any price
        would do. On the finer grid, sweeping this fixture across 200-900
        tenths leaves **12 asks** at which the engine's edge still varies with
        size, all in 48.1c-49.2c. The property is real and it is now narrow.
        """
        small_bankroll = RiskConfig(
            bankroll_dollars=100.0, kelly_fraction=0.25, max_order_contracts=50,
            max_position_dollars=100.0, max_exposure_dollars=400.0,
            max_daily_loss_dollars=100.0,
        )
        big = build(candidate(ask_tenths=481))
        small = build(candidate(ask_tenths=481), risk=small_bankroll)
        assert big.suggested_contracts != small.suggested_contracts
        assert big.edge_tenths != small.edge_tenths

        # And the anchor discriminates -- stated as a pair, so the override
        # above cannot be quietly reverted to a price that proves nothing.
        flat = build(candidate(ask_tenths=505))
        flat_small = build(candidate(ask_tenths=505), risk=small_bankroll)
        assert flat.suggested_contracts != flat_small.suggested_contracts
        assert flat.edge_tenths == flat_small.edge_tenths, (
            "50.5c is fee-flat across these sizes; if this ever differs, the "
            "override above is no longer necessary and should be removed"
        )


class TestPersistence:
    def test_a_suppressed_row_is_stored(self, conn):
        rec = build(candidate(kalshi_quote_age_ms=600_000))
        persist_recommendation(conn, rec)
        row = conn.execute("SELECT * FROM recommendations").fetchone()
        assert row["suppressed_reason"]
        assert row["suggested_contracts"] == 0

    def test_every_row_carries_its_config_version(self, conn):
        """Without this, 'did loosening that threshold help?' is unanswerable."""
        persist_recommendation(conn, build(candidate(), strategy_config_version=7))
        row = conn.execute("SELECT strategy_config_version FROM recommendations").fetchone()
        assert row["strategy_config_version"] == 7

    def test_the_entry_price_stored_is_the_ask(self, conn):
        """Bucketing on the mid while transacting at the ask produced a
        +25.4-point 'edge' that lost money in the previous project."""
        persist_recommendation(conn, build(candidate(ask_tenths=460)))
        row = conn.execute("SELECT entry_ask_tenths FROM recommendations").fetchone()
        assert row["entry_ask_tenths"] == 460


class TestStrategyConfigVersioning:
    """Uses a clean database -- the shared fixture pre-seeds versions."""

    @pytest.fixture
    def conn(self, tmp_path):
        c = db.init_db(tmp_path / "versions.db")
        yield c
        c.close()

    def test_the_first_config_is_version_one(self, conn):
        assert ensure_strategy_config(conn, {"a": 1}, "initial") == 1

    def test_an_unchanged_config_does_not_mint_a_new_version(self, conn):
        """Fragmenting the record on every restart leaves no version with
        enough sample to compare."""
        first = ensure_strategy_config(conn, {"a": 1}, "initial")
        second = ensure_strategy_config(conn, {"a": 1}, "restart")
        assert first == second

    def test_a_changed_config_mints_a_new_version_and_closes_the_old(self, conn):
        ensure_strategy_config(conn, {"edge_ceiling": 40}, "initial", now=NOW)
        v2 = ensure_strategy_config(conn, {"edge_ceiling": 60}, "loosened", now=NOW + 1)
        assert v2 == 2
        old = conn.execute(
            "SELECT effective_to_ms FROM strategy_configs WHERE version = 1"
        ).fetchone()
        assert old["effective_to_ms"] == NOW + 1

    def test_the_rationale_is_stored(self, conn):
        ensure_strategy_config(conn, {"a": 1}, "because the noise guard cleared it")
        row = conn.execute("SELECT rationale FROM strategy_configs").fetchone()
        assert "noise guard" in row["rationale"]


class TestSuppressionSummary:
    def test_counts_each_rule_that_fired(self, conn):
        """A rule firing constantly is either miscalibrated or catching a real
        upstream problem. Both are findings."""
        persist_recommendation(conn, build(candidate(kalshi_quote_age_ms=600_000)))
        persist_recommendation(conn, build(candidate(kalshi_quote_age_ms=600_000)))
        persist_recommendation(conn, build(candidate(depth_at_ask=1.0)))

        summary = suppression_summary(conn, since_ms=0)
        assert summary["stale_kalshi_quote"] == 2
        assert summary["insufficient_depth"] == 1

    def test_a_row_failing_several_checks_counts_against_each(self, conn):
        persist_recommendation(
            conn, build(candidate(kalshi_quote_age_ms=600_000, depth_at_ask=1.0))
        )
        summary = suppression_summary(conn, since_ms=0)
        assert summary["stale_kalshi_quote"] == 1
        assert summary["insufficient_depth"] == 1

    def test_surfaced_rows_are_not_counted(self, conn):
        persist_recommendation(conn, build(candidate()))
        assert suppression_summary(conn, since_ms=0) == {}
