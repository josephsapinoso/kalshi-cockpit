"""A combination bought off the desk carries its legs (ADR 0197, schema v69).

WHAT THIS ESTABLISHES
---------------------
(i)   The venue's settled combination market parses into one leg per
      `mve_selected_legs` entry, labelled in words: discovery's title where
      it has one, else the venue's own words off the combination's title --
      including a leg whose words contain a comma.
(ii)  All legs or none: one unreadable leg, or a title that does not match
      the legs one for one with no other words to use, writes nothing and
      records why.
(iii) `/bets` shows those legs for a combination that has only a
      `venue_settlements` row, with each leg's result from the stored
      `venue_result` when discovery never saw the market, and "unread"
      (None) when neither source has one.
(iv)  The per-kind block counts an off-desk leg under the same rules as a
      held one, with its candle ask as the price, and never counts a leg
      twice when the desk also holds the combination.
(v)   A database stamped v68 with rows in it opens at v69 with
      `tailed_from` on both tables and the CHECK that only a `friend` tag
      carries a name.
(vi)  The older-ticker path: a 404 on `/markets/{ticker}` falls through to
      `/historical/markets/{ticker}`.

The fixture is a stranger's settled combination off the public
`GET /markets?status=settled` list. No account data is used.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- That every one of Joe's past tickets is still served by the venue; the
  live pass reports `not_found` counts.
- Anything about candle prices being read (the backfill script's job).
- That the combination's title order equals the leg order when every leg
  has the same side; see `backend/venue_combo_legs.py`.
"""

from __future__ import annotations

import asyncio
import copy
import json
import sqlite3
from pathlib import Path

import pytest

from backend import bets
from backend import venue_combo_legs as vcl
from backend.store import db

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads(
    (ROOT / "tests" / "fixtures" / "combo_settled_market_with_legs.json").read_text(
        encoding="utf-8"
    )
)
PAYLOAD = FIXTURE["response"]
MARKET = PAYLOAD["market"]
COMBO = MARKET["ticker"]
LEGS = MARKET["mve_selected_legs"]


@pytest.fixture
def conn(tmp_path):
    connection = db.init_db(tmp_path / "t.db")
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()


def _settle(conn, ticker=COMBO, *, first_seen=None, source=None):
    conn.execute(
        "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
        "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths, "
        "position_first_seen_ms, position_time_source) "
        "VALUES (?, 'E', 'no', 1000, 'yes', 2.0, 40, 2, ?, ?)",
        (ticker, first_seen, source),
    )
    conn.commit()


def _getter(pages):
    seen: list[str] = []

    async def get(path):
        seen.append(path)
        return pages.get(path)

    get.seen = seen  # type: ignore[attr-defined]
    return get


def _capture(conn, pages, **kwargs):
    get = _getter(pages)
    counts = asyncio.run(
        vcl.capture_legs(conn, get, limit=10, now_ms=5000, **kwargs)
    )
    return counts, get


def _final(result):
    return {"market": {
        "status": "finalized", "result": result,
        "settlement_value_dollars": "1.0000" if result == "yes" else "0.0000",
    }}


def _results(conn, pages, *, limit=50, now_ms=7000):
    return asyncio.run(
        vcl.capture_results(conn, _getter(pages), limit=limit, now_ms=now_ms)
    )


def _bet(conn, ticker=COMBO):
    return next(b for b in bets.bets_record(conn)["bets"] if b["ticker"] == ticker)


class TestTheVenueMarketParses:
    def test_the_capture_is_a_settled_combination_with_mixed_sides(self):
        # The shape assertion the tests below lean on: settled, several legs,
        # both sides present, and a comma inside one leg's own words.
        assert MARKET["status"] == "finalized"
        assert len(LEGS) >= 2
        assert {leg["side"] for leg in LEGS} == {"yes", "no"}
        assert MARKET["title"].count(",") > len(LEGS) - 1

    def test_every_leg_gets_the_venues_own_words(self):
        legs, reason = vcl.parse_combo_market(PAYLOAD)
        assert reason is None
        assert [leg.ticker for leg in legs] == [g["market_ticker"] for g in LEGS]
        assert [leg.side for leg in legs] == [g["side"] for g in LEGS]
        for leg in legs:
            assert leg.label and leg.label != leg.ticker
            assert leg.label.startswith("NO -- ") == (leg.side == "no")

    def test_a_comma_inside_a_legs_words_does_not_split_it(self):
        words = vcl.title_words(MARKET["title"], [g["side"] for g in LEGS])
        assert words is not None and len(words) == len(LEGS)
        assert any("," in w for w in words)

    def test_a_title_that_names_the_wrong_side_is_not_used(self):
        sides = [g["side"] for g in LEGS]
        flipped = ["no" if s == "yes" else "yes" for s in sides]
        assert vcl.title_words(MARKET["title"], flipped) is None

    def test_discoverys_title_wins_over_the_combination_title(self):
        yes_leg = next(g for g in LEGS if g["side"] == "yes")["market_ticker"]
        legs, _ = vcl.parse_combo_market(PAYLOAD, {yes_leg: "Desk words"})
        assert next(g for g in legs if g.ticker == yes_leg).label == "Desk words"


class TestAllLegsOrNone:
    def test_an_unreadable_venue_leg_list_drops_the_whole_combination(self, conn):
        _settle(conn)
        broken = copy.deepcopy(PAYLOAD)
        broken["market"]["mve_selected_legs"][1]["side"] = "maybe"
        counts, _ = _capture(conn, {f"/markets/{COMBO}": broken})
        assert counts["written"] == 0
        assert counts["refused"] == {vcl.REFUSAL_UNREADABLE_LEG: 1}
        assert conn.execute("SELECT COUNT(*) FROM venue_combo_legs").fetchone()[0] == 0
        assert _bet(conn)["legs"] is None
        row = conn.execute(
            "SELECT reason FROM venue_combo_leg_refusals WHERE combo_ticker = ?",
            (COMBO,),
        ).fetchone()
        assert row["reason"] == vcl.REFUSAL_UNREADABLE_LEG

    def test_a_title_with_too_few_parts_and_no_other_words_is_refused(self):
        broken = copy.deepcopy(PAYLOAD)
        broken["market"]["title"] = "yes only one part"
        legs, reason = vcl.parse_combo_market(broken)
        assert legs is None and reason == vcl.REFUSAL_NO_WORDS

    def test_a_market_with_no_leg_list_is_refused(self):
        broken = copy.deepcopy(PAYLOAD)
        del broken["market"]["mve_selected_legs"]
        assert vcl.parse_combo_market(broken) == (None, vcl.REFUSAL_NO_LEG_LIST)

    def test_a_refused_combination_is_not_re_read_next_pass(self, conn):
        _settle(conn)
        _capture(conn, {})
        counts, get = _capture(conn, {f"/markets/{COMBO}": PAYLOAD})
        assert counts["considered"] == 0 and get.seen == []

    def test_a_dry_run_reads_and_writes_nothing(self, conn):
        _settle(conn)
        counts, _ = _capture(conn, {f"/markets/{COMBO}": PAYLOAD}, commit=False)
        assert counts["written"] == 1
        assert conn.execute("SELECT COUNT(*) FROM venue_combo_legs").fetchone()[0] == 0


class TestBetsShowsTheLegs:
    def test_a_combo_bought_off_the_desk_shows_its_legs(self, conn):
        _settle(conn)
        assert _bet(conn)["legs"] is None
        counts, _ = _capture(conn, {f"/markets/{COMBO}": PAYLOAD})
        assert counts["written"] == 1 and counts["legs_written"] == len(LEGS)
        legs = _bet(conn)["legs"]
        assert [leg["ticker"] for leg in legs] == [g["market_ticker"] for g in LEGS]
        assert all(leg["result"] is None for leg in legs)

    def test_an_older_ticker_is_read_from_the_historical_path(self, conn):
        _settle(conn)
        counts, get = _capture(conn, {f"/historical/markets/{COMBO}": PAYLOAD})
        assert counts["written"] == 1
        assert get.seen == [f"/markets/{COMBO}", f"/historical/markets/{COMBO}"]

    def test_a_ticker_neither_path_serves_is_counted_not_found(self, conn):
        _settle(conn)
        counts, _ = _capture(conn, {})
        assert counts["refused"] == {vcl.REFUSAL_NOT_FOUND: 1}

    def test_a_leg_result_comes_from_the_venue_when_discovery_never_saw_it(self, conn):
        _settle(conn)
        _capture(conn, {f"/markets/{COMBO}": PAYLOAD})
        first, second = LEGS[0], LEGS[1]
        pages = {
            f"/markets/{first['market_ticker']}": _final(first["side"]),
            f"/historical/markets/{second['market_ticker']}": _final(
                "no" if second["side"] == "yes" else "yes"
            ),
        }
        counts = _results(conn, pages)
        assert counts["written"] == 2
        assert counts["not_found"] == len(LEGS) - 2
        by_ticker = {leg["ticker"]: leg["result"] for leg in _bet(conn)["legs"]}
        assert by_ticker[first["market_ticker"]] == "won"
        assert by_ticker[second["market_ticker"]] == "lost"
        # Unread stays unread, never "lost".
        assert [r for t, r in by_ticker.items()
                if t not in (first["market_ticker"], second["market_ticker"])] == (
            [None] * (len(LEGS) - 2)
        )

    def test_an_unsettled_leg_market_writes_no_result(self, conn):
        _settle(conn)
        _capture(conn, {f"/markets/{COMBO}": PAYLOAD})
        ticker = LEGS[0]["market_ticker"]
        pages = {f"/markets/{ticker}": {"market": {"status": "active", "result": ""}}}
        counts = _results(conn, pages)
        assert counts["written"] == 0 and counts["unsettled"] == 1

    def test_a_result_is_not_taken_from_a_market_that_is_not_finalized(self, conn):
        # `determined` can still be reversed, and this table never overwrites.
        _settle(conn)
        _capture(conn, {f"/markets/{COMBO}": PAYLOAD})
        ticker = LEGS[0]["market_ticker"]
        pages = {f"/markets/{ticker}": {"market": {
            "status": "determined", "result": "yes",
            "settlement_value_dollars": "1.0000",
        }}}
        counts = _results(conn, pages)
        assert counts["written"] == 0 and counts["unsettled"] == 1

    def test_legs_that_cannot_resolve_do_not_block_the_ones_that_can(self, conn):
        _settle(conn)
        _capture(conn, {f"/markets/{COMBO}": PAYLOAD})
        last = conn.execute(
            "SELECT ticker, side FROM venue_combo_legs ORDER BY id LIMIT 1"
        ).fetchone()
        pages = {f"/markets/{last['ticker']}": _final(last["side"])}
        # A limit one short of the leg count: the first pass tries the
        # newest legs, finds nothing, and stamps them ...
        first = _results(conn, pages, limit=len(LEGS) - 1, now_ms=10)
        assert first["written"] == 0
        # ... so the next pass reaches the one leg that has a result.
        second = _results(conn, pages, limit=len(LEGS) - 1, now_ms=20)
        assert second["considered"] == 1 and second["written"] == 1
        # And a stamped leg is retried once the wait has passed.
        later = _results(conn, {}, limit=50, now_ms=20 + vcl.RESULT_RETRY_AFTER_MS)
        assert later["considered"] == len(LEGS) - 1

    def test_a_combination_the_desk_holds_is_never_written_here(self, conn):
        _settle(conn)
        conn.execute(
            "INSERT INTO parlay_positions (created_ms, source, label, "
            "stake_tenths, return_tenths, status, combo_ticker) "
            "VALUES (1, 'kalshi_combo', 'held', 100, 1000, 'open', ?)",
            (COMBO,),
        )
        conn.commit()
        counts, get = _capture(conn, {f"/markets/{COMBO}": PAYLOAD})
        assert counts["considered"] == 0 and get.seen == []


class TestByLegKindCountsOffDeskLegs:
    def _priced(self, conn, *, ask=400):
        _settle(conn)
        _capture(conn, {f"/markets/{COMBO}": PAYLOAD})
        conn.execute(
            "UPDATE venue_combo_legs SET venue_result = side, "
            "ask_at_purchase_tenths = ?, ask_source = 'candle'",
            (ask,),
        )
        conn.commit()

    def _cells(self, conn):
        summary = bets.by_leg_kind_summary(conn)
        return [
            (league["league"], kind)
            for league in summary["leagues"]
            for kind in league["kinds"]
        ]

    def test_an_off_desk_leg_carries_its_candle_ask_into_by_leg_kind(self, conn):
        assert self._cells(conn) == []
        self._priced(conn)
        cells = self._cells(conn)
        settled = 0
        for _, kind in cells:
            settled += kind["settled"]
            assert kind["ask_not_recorded"] == 0
            assert kind["expected"]["n"] == kind["settled"]
            assert kind["expected"]["won"] == kind["settled"]
        assert settled == len(LEGS)

    def test_a_leg_with_no_ask_is_counted_as_not_recorded(self, conn):
        self._priced(conn)
        conn.execute("UPDATE venue_combo_legs SET ask_at_purchase_tenths = NULL")
        conn.commit()
        cells = self._cells(conn)
        missing = 0
        for _, kind in cells:
            missing += kind["ask_not_recorded"]
        assert missing == len(LEGS)

    def test_a_leg_with_no_result_is_in_no_cell(self, conn):
        self._priced(conn)
        conn.execute("UPDATE venue_combo_legs SET venue_result = NULL")
        conn.commit()
        assert self._cells(conn) == []

    def test_an_unfollowed_sport_is_filed_under_its_series(self, conn):
        self._priced(conn)
        leagues = {league for league, _ in self._cells(conn)}
        series = {g["event_ticker"].split("-")[0] for g in LEGS}
        assert leagues == series


class TestMigrationToV69:
    def test_migration_v68_to_v69_on_a_populated_db(self, tmp_path):
        path = tmp_path / "old.db"
        connection = db.init_db(path)
        # Put the file back to what v68 looked like: no new columns, no new
        # tables, and the stamp one behind.
        connection.execute("DROP TABLE pick_sources")
        connection.execute(
            "CREATE TABLE pick_sources (ticker TEXT PRIMARY KEY, "
            "source TEXT NOT NULL CHECK (source IN "
            "('card', 'verdict', 'preset', 'chat', 'friend', 'own')), "
            "tagged_ms INTEGER NOT NULL)"
        )
        connection.execute(
            "INSERT INTO pick_sources (ticker, source, tagged_ms) "
            "VALUES ('T-OLD', 'friend', 1)"
        )
        connection.execute("ALTER TABLE parlay_lookups DROP COLUMN tailed_from")
        connection.execute("DROP TABLE venue_combo_legs")
        connection.execute("DROP TABLE venue_combo_leg_refusals")
        db._set_meta(connection, "schema_version", "68")
        connection.commit()
        connection.close()

        connection = db.init_db(path)
        try:
            assert db.get_meta(connection, "schema_version") == "69"
            for table in ("pick_sources", "parlay_lookups"):
                columns = {r[1] for r in connection.execute(f"PRAGMA table_info({table})")}
                assert "tailed_from" in columns, table
            row = connection.execute(
                "SELECT source, tailed_from FROM pick_sources WHERE ticker = 'T-OLD'"
            ).fetchone()
            assert tuple(row) == ("friend", None)
            connection.execute(
                "UPDATE pick_sources SET tailed_from = 'a sharp' WHERE ticker = 'T-OLD'"
            )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO pick_sources (ticker, source, tagged_ms, tailed_from) "
                    "VALUES ('T-NEW', 'own', 2, 'a sharp')"
                )
            assert connection.execute(
                "SELECT COUNT(*) FROM venue_combo_legs"
            ).fetchone()[0] == 0
        finally:
            connection.close()

    def test_a_fresh_database_refuses_a_name_on_any_other_source(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO pick_sources (ticker, source, tagged_ms, tailed_from) "
                "VALUES ('T', 'card', 1, 'a sharp')"
            )


from scripts import backfill_venue_combo_legs as bv  # noqa: E402

PLACED_MS = 1_786_140_000_000


class _Candles:
    """One bar for every (ticker, end) asked, or none when `empty`."""

    def __init__(self, *, empty: bool = False) -> None:
        self.empty = empty
        self.calls: list[tuple[str, int]] = []

    async def candlesticks(self, series_ticker, ticker, *, start_ts, end_ts, period_interval):
        self.calls.append((ticker, end_ts))
        if self.empty:
            return []
        return [{
            "end_period_ts": end_ts,
            "yes_bid": {"close_dollars": "0.40"},
            "yes_ask": {"close_dollars": "0.44"},
        }]


def _prices(conn, candles, *, commit=True):
    return asyncio.run(bv.fill_prices(
        conn, candles, limit=50, commit=commit, now_ms=PLACED_MS + 1
    ))


class TestThePricePass:
    def _with_legs(self, conn, *, source):
        _settle(conn, first_seen=PLACED_MS, source=source)
        _capture(conn, {f"/markets/{COMBO}": PAYLOAD})

    def test_a_leg_gets_the_ask_for_the_side_held_at_the_fill_time(self, conn):
        self._with_legs(conn, source=bv.FILL_TIME_SOURCE)
        candles = _Candles()
        counts = _prices(conn, candles)
        assert counts["asks_written"] == len(LEGS)
        assert {end for _, end in candles.calls} == {PLACED_MS // 1000}
        asks = {
            r["side"]: r["ask_at_purchase_tenths"]
            for r in conn.execute("SELECT side, ask_at_purchase_tenths FROM venue_combo_legs")
        }
        # YES pays the YES ask; NO pays 1000 minus the YES bid.
        assert asks == {"yes": 440, "no": 600}

    def test_a_poll_instant_is_not_a_purchase_time(self, conn):
        self._with_legs(conn, source="poll_instant")
        candles = _Candles()
        counts = _prices(conn, candles)
        assert counts["no_fill_time"] == len(LEGS)
        assert counts["asks_written"] == 0 and candles.calls == []

    def test_a_finished_leg_leaves_the_queue_even_with_no_bars(self, conn):
        self._with_legs(conn, source=bv.FILL_TIME_SOURCE)
        first = _prices(conn, _Candles(empty=True))
        assert first["no_bars_ask"] == len(LEGS)
        second = _prices(conn, _Candles(empty=True))
        assert second["legs_considered"] == 0

    def test_a_dry_run_writes_no_price_and_no_stamp(self, conn):
        self._with_legs(conn, source=bv.FILL_TIME_SOURCE)
        counts = _prices(conn, _Candles(), commit=False)
        assert counts["asks_written"] == len(LEGS)
        row = conn.execute(
            "SELECT COUNT(ask_at_purchase_tenths), COUNT(price_read_ms) "
            "FROM venue_combo_legs"
        ).fetchone()
        assert tuple(row) == (0, 0)

    def test_the_report_is_counts_only(self, conn):
        _settle(conn, first_seen=PLACED_MS, source=bv.FILL_TIME_SOURCE)
        report = asyncio.run(bv.run_passes(
            conn, _getter({f"/markets/{COMBO}": PAYLOAD}), _Candles(),
            limit=50, commit=True, now_ms=PLACED_MS + 1,
        ))
        text = json.dumps(report)
        assert COMBO not in text
        assert all(g["market_ticker"] not in text for g in LEGS)
        assert report["before"]["combos_with_venue_legs"] == 0
        assert report["after"]["combos_with_venue_legs"] == 1
        assert report["after"]["venue_legs_with_ask"] == len(LEGS)


class TestThePollerReadsThem:
    def test_the_poller_pass_writes_legs_and_survives_a_venue_failure(self, conn):
        from backend import portfolio_poll
        from backend.kalshi.rest import KalshiAPIError

        _settle(conn)

        class Client:
            def __init__(self, fail):
                self.fail = fail

            async def get(self, path, **params):
                if self.fail:
                    raise RuntimeError("venue down")
                if path == f"/markets/{COMBO}":
                    return PAYLOAD
                raise KalshiAPIError(404, path, "not found")

        failed = asyncio.run(
            portfolio_poll.poll_venue_combo_legs(conn, Client(True), now_ms=1)
        )
        # One ticker's failure is counted inside the pass, never raised.
        assert failed["legs"]["errors"] == 1
        ok = asyncio.run(
            portfolio_poll.poll_venue_combo_legs(conn, Client(False), now_ms=2)
        )
        assert ok["legs"]["written"] == 1
        assert ok["results"]["not_found"] == len(LEGS)
        assert _bet(conn)["legs"] is not None

    def test_the_fast_branch_calls_it(self):
        import inspect

        from backend import portfolio_poll

        source = inspect.getsource(portfolio_poll.poll_portfolio_forever)
        assert "await poll_venue_combo_legs(" in source


class TestTheArchiveKeepsOlderBars:
    FIX = json.loads(
        (ROOT / "tests" / "fixtures" / "candlesticks_historical_archive.json").read_text(
            encoding="utf-8"
        )
    )

    def test_the_archive_spells_the_close_differently(self):
        from backend.analysis.clv import parse_candlestick

        bar = self.FIX["response"]["candlesticks"][0]
        assert "close" in bar["yes_ask"] and "close_dollars" not in bar["yes_ask"]
        assert parse_candlestick(bar) == (None, None)
        from backend.core.prices import dollars_to_tenths

        expected = (
            dollars_to_tenths(bar["yes_bid"]["close"]),
            dollars_to_tenths(bar["yes_ask"]["close"]),
        )
        assert None not in expected and expected[0] < expected[1]
        assert parse_candlestick(bv.archive_bar(bar)) == expected

    def test_a_live_bar_is_left_exactly_as_it_is(self):
        live = {"yes_bid": {"close_dollars": "0.40"}, "yes_ask": {"close_dollars": "0.44"}}
        assert bv.archive_bar(live) == live

    def test_the_archive_is_asked_only_when_the_live_read_is_empty(self):
        bars = self.FIX["response"]["candlesticks"]

        class Response:
            def __init__(self, status, body):
                self.status_code, self._body = status, body

            def json(self):
                return self._body

            def raise_for_status(self):
                assert self.status_code < 400

        class Client:
            def __init__(self, live):
                self.live, self.urls = live, []

            async def get(self, url, params=None):
                self.urls.append(url)
                if "/historical/" in url:
                    return Response(200, {"candlesticks": bars})
                if self.live:
                    return Response(200, {"candlesticks": self.live})
                return Response(404, {})

        async def read(client):
            reader = bv.CandlesWithArchive(client)
            got = await reader.candlesticks(
                "S", "T", start_ts=1, end_ts=2, period_interval=1
            )
            return reader, got

        cold = Client(live=[])
        reader, got = asyncio.run(read(cold))
        assert len(cold.urls) == 2 and "/historical/markets/T/candlesticks" in cold.urls[1]
        assert reader.archive_reads == 1
        assert got[-1]["yes_ask"]["close_dollars"] == bars[-1]["yes_ask"]["close"]

        warm = Client(live=[{"yes_ask": {"close_dollars": "0.10"}}])
        reader, _ = asyncio.run(read(warm))
        assert len(warm.urls) == 1 and reader.archive_reads == 0


class TestThePollerPassHasABudget:
    def test_a_slow_venue_costs_the_cycle_no_more_than_the_budget(self, conn):
        from backend import portfolio_poll

        _settle(conn)

        class Slow:
            async def get(self, path, **params):
                await asyncio.sleep(30)

        import time

        started = time.monotonic()
        result = asyncio.run(
            portfolio_poll.poll_venue_combo_legs(conn, Slow(), now_ms=1, budget_s=0.05)
        )
        assert result == "FAILED: budget"
        # The budget passed in is the one that binds: a 30-second read under a
        # 0.05-second budget returns in well under two seconds, not in thirty.
        assert time.monotonic() - started < 2.0


class _WriteLock:
    """A second connection holding SQLite's write lock on the same file, which
    is what the recorder is to a backfill pass (#428)."""

    def __init__(self, conn):
        path = conn.execute("PRAGMA database_list").fetchone()[2]
        # The pass must not sit out the 5 s busy timeout once per leg.
        conn.execute("PRAGMA busy_timeout = 0")
        self.other = sqlite3.connect(path, timeout=0)

    def __enter__(self):
        self.other.execute("BEGIN IMMEDIATE")
        return self

    def __exit__(self, *exc):
        self.other.rollback()
        self.other.close()


class TestALockedDatabaseDoesNotEndThePass:
    def test_a_locked_result_write_is_counted_and_the_pass_carries_on(self, conn):
        _settle(conn)
        _capture(conn, {f"/markets/{COMBO}": PAYLOAD})
        first, second = LEGS[0], LEGS[1]
        pages = {
            f"/markets/{first['market_ticker']}": _final(first["side"]),
            f"/markets/{second['market_ticker']}": _final(second["side"]),
        }
        with _WriteLock(conn):
            locked = _results(conn, pages)
        # Every leg was still considered: the first locked write ended nothing.
        assert locked["considered"] == len(LEGS)
        assert locked["write_errors"] == len(LEGS)
        # Nothing is reported written that was not.
        assert locked["written"] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM venue_combo_legs "
            "WHERE venue_result IS NOT NULL OR result_read_ms IS NOT NULL"
        ).fetchone()[0] == 0
        # And the unwritten legs are still in the queue for the next pass.
        after = _results(conn, pages)
        assert after["written"] == 2 and after["write_errors"] == 0

    def test_a_locked_leg_write_is_counted_and_the_combination_stays_queued(self, conn):
        _settle(conn)
        with _WriteLock(conn):
            locked, _ = _capture(conn, {f"/markets/{COMBO}": PAYLOAD})
        assert locked["write_errors"] == 1
        assert locked["written"] == 0 and locked["legs_written"] == 0
        after, _ = _capture(conn, {f"/markets/{COMBO}": PAYLOAD})
        assert after["written"] == 1 and after["legs_written"] == len(LEGS)

    def test_a_locked_refusal_write_is_not_counted_as_a_refusal(self, conn):
        _settle(conn)
        with _WriteLock(conn):
            locked, _ = _capture(conn, {})
        assert locked["refused"] == {} and locked["write_errors"] == 1
        after, _ = _capture(conn, {})
        assert after["refused"] == {vcl.REFUSAL_NOT_FOUND: 1}

    def test_a_locked_price_stamp_is_counted_and_the_pass_carries_on(self, conn):
        # A poll instant is no purchase time, so the only write is the stamp
        # that takes the leg out of the queue: the write nothing guarded.
        TestThePricePass()._with_legs(conn, source="poll_instant")
        with _WriteLock(conn):
            locked = _prices(conn, _Candles())
        assert locked["write_errors"] == len(LEGS)
        assert conn.execute(
            "SELECT COUNT(*) FROM venue_combo_legs WHERE price_read_ms IS NOT NULL"
        ).fetchone()[0] == 0
        after = _prices(conn, _Candles())
        assert after["no_fill_time"] == len(LEGS) and "write_errors" not in after
