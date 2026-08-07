"""Fetching closing lines and scoring on CLV.

The headline is `TestItReadsAgainstTheTrueStart`. Kalshi's `occurrence_datetime`
runs three hours late, so a "one hour before close" reading taken against it
lands **two hours into the game** — a quote from after the outcome is partly
known. That does not fail; it produces a strong, entirely fake CLV signal,
because a price that has already moved toward the result looks like a price we
beat. It would have contaminated the single measurement this whole project
exists to make.
"""

from __future__ import annotations

import pytest

from backend.analysis.clv import CONTROL_HORIZON_HOURS, DEFAULT_HORIZON_HOURS
from backend.scoring import (
    WINDOW_MINUTES,
    fetch_closing_line,
    markets_awaiting_scoring,
    run_scoring_pass,
)
from backend.store import db

NOW = 1_786_200_000_000
HOUR_MS = 3_600_000
TRUE_COMMENCE = NOW - 3 * HOUR_MS          # game started three hours ago
KALSHI_COMMENCE = TRUE_COMMENCE + 3 * HOUR_MS   # Kalshi's field, 3h late


class FakeKalshi:
    """Records the windows requested and returns a fixed candle."""

    def __init__(self, candles=None, fail_on=()):
        self.calls = []
        self.candles = candles if candles is not None else [
            {"yes_bid": {"close": 52}, "yes_ask": {"close": 54},
             "end_period_ts": 1_786_000_000}
        ]
        self.fail_on = set(fail_on)

    async def candlesticks(self, series_ticker, ticker, *, start_ts, end_ts,
                           period_interval=60):
        self.calls.append(
            {"series": series_ticker, "ticker": ticker,
             "start_ts": start_ts, "end_ts": end_ts,
             "interval": period_interval}
        )
        if ticker in self.fail_on:
            raise RuntimeError("candlesticks 404")
        return list(self.candles)


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "scoring.db")
    yield c
    c.close()


def _seed(conn, *, ticker="KXMLBGAME-T-A", side="yes", ask=480,
          true_commence=TRUE_COMMENCE):
    """One linked, unscored recommendation on a game that has already started."""
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_series (series_ticker, league, "
        "has_game_markets, first_seen_ms, last_seen_ms) "
        "VALUES ('KXMLBGAME','Pro Baseball',1,?,?)", (NOW, NOW),
    )
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events (event_ticker, series_ticker, title, "
        "category, commence_ms, status, first_seen_ms, last_seen_ms) "
        "VALUES ('EVT','KXMLBGAME','A vs B','Sports',?,'open',?,?)",
        (KALSHI_COMMENCE, NOW, NOW),
    )
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, series_ticker, "
        "first_seen_ms, last_seen_ms) VALUES (?,'EVT','KXMLBGAME',?,?)",
        (ticker, NOW, NOW),
    )
    conn.execute(
        "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, odds_event_id, "
        "league, method, commence_skew_ms, linked_ms) "
        "VALUES ('EVT','odds-1','Pro Baseball','exact_alias_pair',?,?)",
        (-3 * HOUR_MS, NOW),
    )
    link_id = conn.execute("SELECT id FROM event_links").fetchone()["id"]
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, sport_key, "
        "odds_event_id, commence_ms, home_team, away_team, bookmaker, market, "
        "outcome_name, price_decimal) "
        "VALUES (?,?,'baseball_mlb','odds-1',?,'B','A','pinnacle','h2h','A',2.0)",
        (NOW, NOW, true_commence),
    )
    # Before the recommendation that references it -- foreign keys are enforced.
    conn.execute(
        "INSERT OR IGNORE INTO strategy_configs (version, created_ms, "
        "effective_from_ms, config_json, rationale, approved_by_user) "
        "VALUES (1,?,?,'{}','test',0)", (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO recommendations (created_ms, strategy_config_version, ticker, "
        "link_id, side, entry_ask_tenths, fair_probability, edge_tenths, "
        "fee_predicted, ev_net_dollars, kelly_fraction, suggested_contracts, "
        "kalshi_quote_age_ms, odds_age_ms, reason_text) "
        "VALUES (?,1,?,?,?,?,0.5,1.0,0.1,0.1,0.01,0,1000,1000,'t')",
        (NOW - HOUR_MS, ticker, link_id, side, ask),
    )
    conn.commit()
    return link_id


class TestItReadsAgainstTheTrueStart:
    """The clock this reads from decides whether the measurement means anything."""

    async def test_the_window_is_anchored_on_the_sportsbook_commence(self, conn):
        """Not Kalshi's, which is three hours late.

        Anchoring on Kalshi's field would place a "1h before close" reading two
        hours *into* the game. The assertion is on the requested window rather
        than on the returned number, because the returned number would look
        entirely reasonable either way -- that is what makes this dangerous.
        """
        _seed(conn)
        kalshi = FakeKalshi()
        await run_scoring_pass(conn, kalshi, now=NOW)

        primary = next(
            c for c in kalshi.calls
            if c["end_ts"] == (TRUE_COMMENCE - int(DEFAULT_HORIZON_HOURS * HOUR_MS)) // 1000
        )
        assert primary, "no window anchored on the true start"

        # And explicitly NOT the Kalshi clock.
        wrong_end = (KALSHI_COMMENCE - int(DEFAULT_HORIZON_HOURS * HOUR_MS)) // 1000
        assert all(c["end_ts"] != wrong_end for c in kalshi.calls), (
            "a window was anchored on Kalshi's late commence time"
        )

    async def test_the_reading_precedes_the_game(self, conn):
        """The property that actually matters, stated independently."""
        _seed(conn)
        kalshi = FakeKalshi()
        await run_scoring_pass(conn, kalshi, now=NOW)

        for call in kalshi.calls:
            assert call["end_ts"] * 1000 <= TRUE_COMMENCE, (
                "read a quote from during or after the game"
            )

    async def test_the_window_ends_on_the_target_so_the_last_candle_is_the_one(
        self, conn
    ):
        """Avoids parsing a candle timestamp field this project has never captured."""
        _seed(conn)
        kalshi = FakeKalshi()
        await run_scoring_pass(conn, kalshi, now=NOW)

        for call in kalshi.calls:
            assert call["end_ts"] - call["start_ts"] == WINDOW_MINUTES * 60
            assert call["interval"] == 1


class TestBothHorizons:
    async def test_lines_are_stored_at_both_horizons(self, conn):
        """`horizons_agree` needs both; a finding that moves was convergence."""
        _seed(conn)
        await run_scoring_pass(conn, FakeKalshi(), now=NOW)

        stored = {
            r["horizon_hours"]
            for r in conn.execute("SELECT horizon_hours FROM closing_lines")
        }
        assert stored == {DEFAULT_HORIZON_HOURS, CONTROL_HORIZON_HOURS}

    async def test_only_the_primary_horizon_is_scored(self, conn):
        """Scoring both would make `clv_tenths` a silent mixture.

        `score_recommendations` fills whatever is unscored, so a second call at
        another horizon would score a different subset with no column recording
        which horizon produced which row.
        """
        _seed(conn)
        await run_scoring_pass(conn, FakeKalshi(), now=NOW)

        rows = conn.execute(
            "SELECT r.clv_tenths, c.horizon_hours FROM recommendations r "
            "JOIN closing_lines c ON c.id = r.closing_line_id"
        ).fetchall()
        assert rows
        assert {r["horizon_hours"] for r in rows} == {DEFAULT_HORIZON_HOURS}


class TestScoring:
    async def test_a_started_game_gets_scored(self, conn):
        _seed(conn, side="yes", ask=480)
        counts = await run_scoring_pass(conn, FakeKalshi(), now=NOW)

        assert counts.scored == 1
        row = conn.execute(
            "SELECT clv_tenths, clv_scored_ms FROM recommendations"
        ).fetchone()
        # Candle closes yes_bid 52c / yes_ask 54c -> mid 530 tenths.
        # YES bought at 480 is worth 530: +50.
        assert row["clv_tenths"] == pytest.approx(50.0)
        assert row["clv_scored_ms"] == NOW

    async def test_the_no_side_uses_the_complement(self, conn):
        """A NO at 48c on a market closing 53c YES is worth 47c: -10 tenths."""
        _seed(conn, side="no", ask=480)
        await run_scoring_pass(conn, FakeKalshi(), now=NOW)

        row = conn.execute("SELECT clv_tenths FROM recommendations").fetchone()
        assert row["clv_tenths"] == pytest.approx((1000 - 530) - 480)

    async def test_a_game_that_has_not_started_is_not_scored(self, conn):
        """A closing line does not exist yet. Normal state, not a failure."""
        _seed(conn, true_commence=NOW + 2 * HOUR_MS)
        counts = await run_scoring_pass(conn, FakeKalshi(), now=NOW)

        assert counts.not_started_yet == 1
        assert counts.scored == 0
        assert conn.execute(
            "SELECT COUNT(*) n FROM closing_lines"
        ).fetchone()["n"] == 0

    async def test_an_empty_candle_window_is_counted_not_substituted(self, conn):
        _seed(conn)
        counts = await run_scoring_pass(conn, FakeKalshi(candles=[]), now=NOW)

        assert counts.candles_missing == 2      # both horizons
        assert counts.lines_stored == 0
        assert counts.scored == 0

    async def test_one_markets_failure_does_not_stop_the_others(self, conn):
        """An observation lost is indistinguishable from one never generated."""
        _seed(conn, ticker="KXMLBGAME-T-A")
        _seed(conn, ticker="KXMLBGAME-T-B")
        kalshi = FakeKalshi(fail_on={"KXMLBGAME-T-A"})

        counts = await run_scoring_pass(conn, kalshi, now=NOW)
        assert len(counts.errors) == 2          # both horizons for the bad one
        assert counts.scored == 1, "the healthy market must still be scored"

    async def test_rerunning_does_not_double_score(self, conn):
        _seed(conn)
        await run_scoring_pass(conn, FakeKalshi(), now=NOW)
        again = await run_scoring_pass(conn, FakeKalshi(), now=NOW + 60_000)

        assert again.scored == 0
        assert conn.execute(
            "SELECT COUNT(*) n FROM closing_lines"
        ).fetchone()["n"] == 2, "closing lines are upserted, not duplicated"


class TestSelection:
    async def test_only_unscored_linked_markets_are_considered(self, conn):
        _seed(conn)
        pending = markets_awaiting_scoring(conn, now=NOW)
        assert len(pending) == 1
        assert pending[0]["true_commence_ms"] == TRUE_COMMENCE
        assert pending[0]["started"] is True

        await run_scoring_pass(conn, FakeKalshi(), now=NOW)
        assert markets_awaiting_scoring(conn, now=NOW) == []
