"""The matcher: §7.2/§7.3 of the calibration registration, as registered.

The rules under test were fixed before any data existed: the 24h window is
half-open `(estimate, estimate+24h]`; the LATER of two competing estimates
matches; `position_first_seen_ms` upgrades only toward earlier venue-side
evidence; outcomes prefer the public market result and a void stays NULL.

What this does not establish: anything about the analysis. Coverage,
attrition rates and every aggregate stay embargoed until the registered stop;
these tests assert per-row bookkeeping only.
"""

from __future__ import annotations

import pytest

from backend.estimate_match import (
    ensure_estimate_markets_known,
    match_estimates,
    refine_first_seen,
    score_outcomes,
    run_match_pass,
)
from backend.estimates import record_estimate
from backend.kalshi.discovery import DiscoveredMarket
from backend.kalshi.quotes import LiveQuote, QuoteUnavailable
from backend.store import db

NOW = 1_787_000_000_000
HOUR = 3_600_000
TICKER = "KXUFCFIGHT-26AUG30-JONASP"


@pytest.fixture
def conn(tmp_path):
    handle = db.init_db(tmp_path / "match.db")
    yield handle
    handle.close()


def _estimate(conn, *, ticker=TICKER, at=NOW, bp=6000):
    return record_estimate(
        conn, ticker=ticker, stated_probability_bp=bp, estimate_server_ms=at
    )


def _settlement(conn, *, ticker=TICKER, settled=NOW + 6 * HOUR, side="yes",
                result="yes", first_seen=None, source=None):
    cursor = conn.execute(
        "INSERT INTO venue_settlements (ticker, market_result, settled_ms, "
        "side, contracts, position_first_seen_ms, "
        "position_time_source) VALUES (?, ?, ?, ?, 200, ?, ?)",
        (ticker, result, settled, side, first_seen, source),
    )
    conn.commit()
    return cursor.lastrowid


def _fill(conn, *, ticker=TICKER, filled=NOW + 2 * HOUR):
    conn.execute(
        "INSERT INTO fills (ticker, filled_ms, count, price_tenths, is_taker, "
        "fee_predicted, fee_model_used, source) "
        "VALUES (?, ?, 2, 400, 1, 0.05, 'model_a', 'venue_hand')",
        (ticker, filled),
    )
    conn.commit()


def _row(conn, estimate_id):
    return conn.execute(
        "SELECT * FROM bet_estimates WHERE id = ?", (estimate_id,)
    ).fetchone()


class TestMatching:
    def test_an_estimate_matches_a_position_inside_its_window(self, conn):
        est = _estimate(conn)
        position = _settlement(conn, first_seen=NOW + 2 * HOUR,
                               source="poll_instant")
        counts = match_estimates(conn, now_ms=NOW + 30 * HOUR)
        assert counts["matched"] == 1
        row = _row(conn, est)
        assert row["matched_position_id"] == position
        assert row["match_status"] == "matched"

    def test_the_window_is_half_open_on_the_left(self, conn):
        """A position first seen AT the estimate instant did not follow it."""
        est = _estimate(conn, at=NOW)
        _settlement(conn, first_seen=NOW, source="poll_instant")
        match_estimates(conn, now_ms=NOW + 30 * HOUR)
        assert _row(conn, est)["match_status"] == "unmatched_no_position"

    def test_the_later_of_two_competing_estimates_wins(self, conn):
        """Registered §7.3 conflict rule, chosen before any data existed."""
        earlier = _estimate(conn, at=NOW)
        later = _estimate(conn, at=NOW + HOUR)
        position = _settlement(conn, first_seen=NOW + 2 * HOUR,
                               source="poll_instant")
        match_estimates(conn, now_ms=NOW + 30 * HOUR)
        assert _row(conn, later)["matched_position_id"] == position
        assert _row(conn, earlier)["matched_position_id"] is None

    def test_an_expired_window_is_a_status_not_a_deletion(self, conn):
        est = _estimate(conn)
        counts = match_estimates(conn, now_ms=NOW + 25 * HOUR)
        assert counts["expired"] == 1
        assert _row(conn, est)["match_status"] == "unmatched_no_position"

    def test_a_window_still_open_stays_pending(self, conn):
        est = _estimate(conn)
        counts = match_estimates(conn, now_ms=NOW + HOUR)
        assert counts["pending"] == 1
        assert _row(conn, est)["match_status"] is None

    def test_a_revised_estimate_is_never_matched(self, conn):
        est = _estimate(conn)
        conn.execute(
            "UPDATE bet_estimates SET stated_probability_is_revised = 1 "
            "WHERE id = ?", (est,),
        )
        conn.commit()
        _settlement(conn, first_seen=NOW + 2 * HOUR, source="poll_instant")
        counts = match_estimates(conn, now_ms=NOW + 30 * HOUR)
        assert counts["matched"] == 0

    def test_settled_time_is_the_last_resort_clock(self, conn):
        """A position with no first-seen still matches -- on `settled_ms`,
        which §7.2 permits and the stored source must reveal."""
        est = _estimate(conn)
        _settlement(conn, settled=NOW + 6 * HOUR, first_seen=None, source=None)
        counts = match_estimates(conn, now_ms=NOW + 30 * HOUR)
        assert counts["matched"] == 1
        assert _row(conn, est)["match_status"] == "matched"


class TestFirstSeenRefinement:
    def test_a_mirrored_fill_upgrades_the_poll_instant(self, conn):
        position = _settlement(conn, first_seen=NOW + 6 * HOUR,
                               source="poll_instant")
        _fill(conn, filled=NOW + 2 * HOUR)
        assert refine_first_seen(conn) == 1
        row = conn.execute(
            "SELECT * FROM venue_settlements WHERE id = ?", (position,)
        ).fetchone()
        assert row["position_first_seen_ms"] == NOW + 2 * HOUR
        assert row["position_time_source"] == "fill_created_time"
        assert row["n_fills_in_position"] == 1

    def test_idempotent(self, conn):
        _settlement(conn, first_seen=NOW + 6 * HOUR, source="poll_instant")
        _fill(conn, filled=NOW + 2 * HOUR)
        refine_first_seen(conn)
        assert refine_first_seen(conn) == 0


class TestOutcomes:
    def _matched(self, conn, *, side="yes", venue_result="yes",
                 public_result=None):
        est = _estimate(conn)
        _settlement(conn, side=side, result=venue_result,
                    first_seen=NOW + 2 * HOUR, source="poll_instant")
        match_estimates(conn, now_ms=NOW + 30 * HOUR)
        if public_result is not None:
            conn.execute(
                "INSERT INTO kalshi_series (series_ticker, first_seen_ms, "
                "last_seen_ms) VALUES ('KXUFCFIGHT', 1, 1)"
            )
            conn.execute(
                "INSERT INTO kalshi_markets (ticker, series_ticker, result, "
                "status, first_seen_ms, last_seen_ms) "
                "VALUES (?, 'KXUFCFIGHT', ?, 'finalized', 1, 1)",
                (TICKER, public_result),
            )
            conn.commit()
        return est

    def test_the_public_result_is_preferred_and_named(self, conn):
        est = self._matched(conn, side="yes", venue_result="yes",
                            public_result="yes")
        score_outcomes(conn, now_ms=NOW + 31 * HOUR)
        row = _row(conn, est)
        assert row["outcome_win"] == 1
        assert row["outcome_source"] == "public_market"
        assert row["market_result_public"] == "yes"

    def test_the_venue_result_is_the_fallback_and_named(self, conn):
        est = self._matched(conn, side="no", venue_result="yes")
        score_outcomes(conn, now_ms=NOW + 31 * HOUR)
        row = _row(conn, est)
        assert row["outcome_win"] == 0
        assert row["outcome_source"] == "venue_settlement"

    def test_a_void_stays_null_never_zero(self, conn):
        """A void is the absence of an outcome, not an outcome."""
        est = self._matched(conn, venue_result=None, public_result="void")
        counts = score_outcomes(conn, now_ms=NOW + 31 * HOUR)
        assert counts["awaiting"] == 1
        row = _row(conn, est)
        assert row["outcome_win"] is None
        assert row["market_result_public"] == "void"

    def test_unsettled_stays_null(self, conn):
        est = self._matched(conn, venue_result=None)
        score_outcomes(conn, now_ms=NOW + 31 * HOUR)
        assert _row(conn, est)["outcome_win"] is None


class _StubSource:
    """A6 ensure-fetch double: one canned market, or a refusal."""

    def __init__(self, *, fail=False):
        self.fail = fail
        self.fetched: list[str] = []

    async def fetch(self, ticker, *, observed_ms):
        self.fetched.append(ticker)
        if self.fail:
            raise QuoteUnavailable("nope", permanent=True)
        return LiveQuote(
            market=DiscoveredMarket(
                ticker=ticker,
                event_ticker="KXUFCFIGHT-26AUG30",
                series_ticker="KXUFCFIGHT",
                market_type="moneyline",
                title="Jones vs Aspinall",
                yes_side=None,
                strike=None,
                close_ms=NOW + 10 * HOUR,
                status="active",
                volume_24h=0.0,
                open_interest=0.0,
                price_structure=None,
            ),
            observed_ms=observed_ms,
        )


class TestEnsureFetch:
    async def test_an_unknown_ticker_gains_market_and_event_rows(self, conn):
        _estimate(conn)
        source = _StubSource()
        counts = await ensure_estimate_markets_known(conn, source, now_ms=NOW)
        assert counts == {"missing": 1, "fetched": 1, "unreadable": 0}
        market = conn.execute(
            "SELECT event_ticker, close_ms FROM kalshi_markets "
            "WHERE ticker = ?", (TICKER,),
        ).fetchone()
        assert market["event_ticker"] == "KXUFCFIGHT-26AUG30"
        # The event row exists too, so market_results' event join works.
        event = conn.execute(
            "SELECT 1 FROM kalshi_events WHERE event_ticker = ?",
            ("KXUFCFIGHT-26AUG30",),
        ).fetchone()
        assert event is not None

    async def test_a_known_ticker_is_not_refetched(self, conn):
        _estimate(conn)
        source = _StubSource()
        await ensure_estimate_markets_known(conn, source, now_ms=NOW)
        again = await ensure_estimate_markets_known(conn, source, now_ms=NOW)
        assert again["missing"] == 0
        assert len(source.fetched) == 1

    async def test_a_refusal_is_counted_and_retried_next_cycle(self, conn):
        _estimate(conn)
        source = _StubSource(fail=True)
        counts = await ensure_estimate_markets_known(conn, source, now_ms=NOW)
        assert counts["unreadable"] == 1
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM kalshi_markets"
        ).fetchone()["n"] == 0


class TestTheWholePass:
    async def test_end_to_end_scores_a_hand_bet(self, conn):
        est = _estimate(conn)
        _settlement(conn, side="yes", result="yes",
                    first_seen=NOW + 6 * HOUR, source="poll_instant")
        _fill(conn, filled=NOW + 2 * HOUR)
        summary = await run_match_pass(
            conn, _StubSource(), now_ms=NOW + 30 * HOUR
        )
        assert summary["match"]["matched"] == 1
        assert summary["outcomes"]["scored"] == 1
        row = _row(conn, est)
        assert row["outcome_win"] == 1
        # The matcher never touched the measurement or the other population.
        assert row["stated_probability_bp"] == 6000
        n_recs = conn.execute(
            "SELECT COUNT(*) AS n FROM recommendations"
        ).fetchone()["n"]
        assert n_recs == 0
