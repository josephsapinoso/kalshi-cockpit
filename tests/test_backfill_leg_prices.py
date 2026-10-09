"""`scripts/backfill_leg_prices.py` fills only what is NULL, from bars, and
never touches `closing_lines` (ADR 0194, schema v65, #322).

What these tests do not establish: that a bar's close equals the ask a fill
crossed (`scripts/reconcile_candle_ask.py` owns that), or anything about the
venue's retention window.
"""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from backend import hedge
from backend.store import db
from scripts import backfill_leg_prices as bf

SERIES = "KXMLBGAME"
EVENT = "KXMLBGAME-26AUG071840TORPHI"
YES_LEG = f"{EVENT}-TOR"
NO_LEG = f"{EVENT}-PHI"
PLACED_MS = 1_786_140_000_000
COMMENCE_MS = 1_786_142_400_000  # the odds fixture's start, after the placement
NOW_MS = COMMENCE_MS + 3_600_000


def _bar(end_ts: int, *, yes_bid: str, yes_ask: str) -> dict:
    return {
        "end_period_ts": end_ts,
        "yes_bid": {"close_dollars": yes_bid},
        "yes_ask": {"close_dollars": yes_ask},
    }


class FakeKalshi:
    """Answers candlesticks by (ticker, end_ts): one bar, or none."""

    def __init__(self, bars: dict[tuple[str, int], dict] | None = None) -> None:
        self.bars = bars or {}
        self.calls: list[tuple[str, str, int, int]] = []

    async def candlesticks(self, series_ticker, ticker, *, start_ts, end_ts, period_interval):
        assert period_interval == bf.CANDLE_INTERVAL_MINUTES
        assert end_ts - start_ts == bf.WINDOW_MINUTES * 60
        self.calls.append((series_ticker, ticker, start_ts, end_ts))
        bar = self.bars.get((ticker, end_ts))
        return [bar] if bar else []


def _seed(conn: sqlite3.Connection, *, link: bool = True, placed_ms=PLACED_MS) -> int:
    conn.execute(
        "INSERT INTO kalshi_series (series_ticker, first_seen_ms, last_seen_ms) VALUES (?, 1, 1)",
        (SERIES,),
    )
    conn.execute(
        "INSERT INTO kalshi_events (event_ticker, series_ticker, first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, 1, 1)",
        (EVENT, SERIES),
    )
    for ticker in (YES_LEG, NO_LEG):
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, event_ticker, series_ticker, first_seen_ms, "
            "last_seen_ms) VALUES (?, ?, ?, 1, 1)",
            (ticker, EVENT, SERIES),
        )
    if link:
        conn.execute(
            "INSERT INTO odds_fixtures (odds_event_id, sport_key, commence_ms, last_fetched_ms) "
            "VALUES ('odds-1', 'baseball_mlb', ?, 1)",
            (COMMENCE_MS,),
        )
        conn.execute(
            "INSERT INTO event_links (kalshi_event_ticker, odds_event_id, league, method, "
            "commence_skew_ms, linked_ms) VALUES (?, 'odds-1', 'mlb', 'exact_alias_pair', 0, 1)",
            (EVENT,),
        )
    conn.commit()
    return hedge.record_position(
        conn,
        now_ms=PLACED_MS,
        source="kalshi_combo",
        label="two legs",
        stake_tenths=100,
        return_tenths=1000,
        legs=[
            {"ticker": YES_LEG, "side": "yes", "label": "TOR wins"},
            {"ticker": NO_LEG, "side": "no", "label": "PHI does not win"},
        ],
        placed_ms=placed_ms,
    )


@pytest.fixture
def conn(tmp_path: Path):
    connection = db.init_db(tmp_path / "t.db")
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()


def _legs(conn):
    return {
        r["ticker"]: dict(r)
        for r in conn.execute(
            "SELECT ticker, ask_at_purchase_tenths, ask_source, close_yes_bid_tenths, "
            "close_yes_ask_tenths, close_observed_ms FROM parlay_position_legs"
        ).fetchall()
    }


def _bars_for_both_legs() -> dict:
    placed_s = PLACED_MS // 1000
    close_s = COMMENCE_MS // 1000  # DEFAULT_HORIZON_HOURS is 0.0
    return {
        (YES_LEG, placed_s): _bar(placed_s, yes_bid="0.6000", yes_ask="0.6200"),
        (NO_LEG, placed_s): _bar(placed_s, yes_bid="0.3000", yes_ask="0.3300"),
        (YES_LEG, close_s): _bar(close_s, yes_bid="0.6500", yes_ask="0.6700"),
        (NO_LEG, close_s): _bar(close_s, yes_bid="0.2800", yes_ask="0.3100"),
    }


class TestTheAskIsTheSideHeld:
    def test_a_yes_leg_takes_the_yes_ask_and_a_no_leg_the_reflected_bid(self, conn):
        _seed(conn)
        api = FakeKalshi(_bars_for_both_legs())
        counts = asyncio.run(bf.fill(conn, api, commit=True, now_ms=NOW_MS))
        legs = _legs(conn)
        assert legs[YES_LEG]["ask_at_purchase_tenths"] == 620
        assert legs[NO_LEG]["ask_at_purchase_tenths"] == 1000 - 300
        assert {legs[YES_LEG]["ask_source"], legs[NO_LEG]["ask_source"]} == {"candle"}
        assert counts.asks_written == 2

    def test_the_close_is_the_bar_before_the_true_start(self, conn):
        _seed(conn)
        api = FakeKalshi(_bars_for_both_legs())
        asyncio.run(bf.fill(conn, api, commit=True, now_ms=NOW_MS))
        legs = _legs(conn)
        assert (legs[YES_LEG]["close_yes_bid_tenths"], legs[YES_LEG]["close_yes_ask_tenths"]) == (650, 670)
        assert legs[YES_LEG]["close_observed_ms"] == COMMENCE_MS
        # The candlestick window ends at the fixture's start, never at a
        # Kalshi clock three hours later.
        assert all(end_ts in (PLACED_MS // 1000, COMMENCE_MS // 1000) for *_, end_ts in api.calls)


class TestOnlyNullsAreWritten:
    def test_a_value_the_forward_path_wrote_is_never_overwritten(self, conn):
        _seed(conn)
        conn.execute(
            "UPDATE parlay_position_legs SET ask_at_purchase_tenths = 555, ask_source = 'lookup' "
            "WHERE ticker = ?",
            (YES_LEG,),
        )
        conn.commit()
        api = FakeKalshi(_bars_for_both_legs())
        asyncio.run(bf.fill(conn, api, commit=True, now_ms=NOW_MS))
        legs = _legs(conn)
        assert legs[YES_LEG]["ask_at_purchase_tenths"] == 555
        assert legs[YES_LEG]["ask_source"] == "lookup"
        # ...and the leg still got its close, which WAS null.
        assert legs[YES_LEG]["close_yes_bid_tenths"] == 650

    def test_a_second_run_writes_nothing(self, conn):
        _seed(conn)
        api = FakeKalshi(_bars_for_both_legs())
        asyncio.run(bf.fill(conn, api, commit=True, now_ms=NOW_MS))
        again = asyncio.run(bf.fill(conn, FakeKalshi(), commit=True, now_ms=NOW_MS))
        assert again.legs_considered == 0
        assert again.asks_written == 0 and again.closes_written == 0

    def test_a_dry_run_reads_bars_and_writes_nothing(self, conn):
        _seed(conn)
        api = FakeKalshi(_bars_for_both_legs())
        counts = asyncio.run(bf.fill(conn, api, commit=False, now_ms=NOW_MS))
        assert counts.mode == "dry-run"
        assert counts.asks_written == 2 and counts.closes_written == 2
        assert api.calls  # the venue WAS read
        legs = _legs(conn)
        assert all(v["ask_at_purchase_tenths"] is None for v in legs.values())
        assert all(v["close_yes_bid_tenths"] is None for v in legs.values())


class TestUnknownStaysNullAndIsCounted:
    def test_no_link_leaves_the_close_null(self, conn):
        _seed(conn, link=False)
        api = FakeKalshi(_bars_for_both_legs())
        counts = asyncio.run(bf.fill(conn, api, commit=True, now_ms=NOW_MS))
        legs = _legs(conn)
        assert all(v["close_yes_bid_tenths"] is None for v in legs.values())
        assert counts.no_link == 2
        # The asks still fill: they need placed_ms, not the link.
        assert counts.asks_written == 2

    def test_a_game_still_ahead_is_not_started_not_missing(self, conn):
        _seed(conn)
        api = FakeKalshi(_bars_for_both_legs())
        counts = asyncio.run(bf.fill(conn, api, commit=True, now_ms=COMMENCE_MS - 1))
        assert counts.not_started == 2
        assert counts.no_bars_close == 0

    def test_no_placed_ms_leaves_the_ask_null(self, conn):
        _seed(conn, placed_ms=None)
        api = FakeKalshi(_bars_for_both_legs())
        counts = asyncio.run(bf.fill(conn, api, commit=True, now_ms=NOW_MS))
        assert counts.no_placed_ms == 2
        assert all(v["ask_at_purchase_tenths"] is None for v in _legs(conn).values())

    def test_no_bar_is_counted_and_never_becomes_zero(self, conn):
        _seed(conn)
        counts = asyncio.run(bf.fill(conn, FakeKalshi(), commit=True, now_ms=NOW_MS))
        assert counts.no_bars_ask == 2 and counts.no_bars_close == 2
        legs = _legs(conn)
        assert all(v["ask_at_purchase_tenths"] is None for v in legs.values())
        assert all(v["close_yes_bid_tenths"] is None for v in legs.values())

    def test_an_unreadable_bar_is_counted_not_zeroed(self, conn):
        _seed(conn)
        placed_s = PLACED_MS // 1000
        api = FakeKalshi({(YES_LEG, placed_s): {"end_period_ts": placed_s, "yes_bid": {}, "yes_ask": {}}})
        counts = asyncio.run(bf.fill(conn, api, commit=True, now_ms=NOW_MS))
        assert counts.unreadable_ask == 1
        assert _legs(conn)[YES_LEG]["ask_at_purchase_tenths"] is None


class TestClosingLinesIsNeverTouched:
    def test_no_row_reaches_closing_lines(self, conn):
        _seed(conn)
        asyncio.run(bf.fill(conn, FakeKalshi(_bars_for_both_legs()), commit=True, now_ms=NOW_MS))
        assert conn.execute("SELECT COUNT(*) FROM closing_lines").fetchone()[0] == 0

    def test_the_script_does_not_even_import_the_closing_line_writer(self):
        source = Path(bf.__file__).read_text(encoding="utf-8")
        assert "store_closing_line" not in source
        assert "INSERT INTO closing_lines" not in source


class TestTheSeriesComesFromTheCaptureFirst:
    def test_a_market_discovery_never_saw_uses_the_ticker_prefix_and_is_counted(self, conn):
        _seed(conn)
        conn.execute("DELETE FROM kalshi_markets WHERE ticker = ?", (NO_LEG,))
        conn.commit()
        api = FakeKalshi(_bars_for_both_legs())
        counts = asyncio.run(bf.fill(conn, api, commit=True, now_ms=NOW_MS))
        assert counts.series_from_ticker == 1
        assert {series for series, *_ in api.calls} == {SERIES}


class TestTheCommandLine:
    def test_it_refuses_to_run_without_a_mode(self):
        with pytest.raises(SystemExit):
            bf.main(["--db", "x.db"])

    def test_it_refuses_a_non_positive_limit(self):
        with pytest.raises(SystemExit):
            bf.main(["--db", "x.db", "--dry-run", "--limit", "0"])
