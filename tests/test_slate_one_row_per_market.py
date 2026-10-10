"""The Games list carries each market once, freshest evaluation, kickoff order.

Ticket #357. On live 2026-10-10 the default `/api/slate` window held 506 rows
that were 128 distinct tickers (the runner re-evaluates the window every pass),
and the route ordered by an inert `suggested_contracts DESC` then freshness, so
the default `LIMIT 100` showed "the markets touched most recently, several
times each".

What this establishes: with more rows than the default limit across two days
and repeated tickers, the default response has each ticker once, as its row
with the greatest `freshness_measured_from_ms`, in `commence_ms` order
(unknown last, ticker the tiebreak), and `in_window` / `returned` / `truncated`
count that deduplicated population.

What it does not establish: query cost on a live-sized table (the plan test
only names the access method), nor anything about the screen's rendering.
Nothing here orders by edge, fair value or the consensus gap (ADR 0071).
"""

from __future__ import annotations

import httpx
import pytest

from backend.api.routes import _BASIS_SQL, _FRESHEST_PER_TICKER_SQL, create_app
from backend.config import AppConfig
from backend.store import db

HOUR_MS = 3_600_000
GAMES = 110  # 3 rows each = 330 rows; 111 markets, over the default limit of 100


async def get(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, **kwargs)


def _seed(conn, now):
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
    )
    expected_freshest: dict[str, int] = {}
    # Insert in a scrambled kickoff order so insertion order cannot pass.
    order = [(i * 37) % GAMES for i in range(GAMES)]
    for i in order:
        key = f"G{i:03d}"
        # Hourly kickoffs across days: tonight, tomorrow, later.
        kickoff = now + (i + 1) * HOUR_MS
        event = f"KXT{key}-EVENT"
        ticker = f"KXT{key}-YES"
        conn.execute(
            "INSERT INTO kalshi_events (event_ticker, title, first_seen_ms, "
            "last_seen_ms) VALUES (?, ?, 1000, 1000)",
            (event, f"Game {key}"),
        )
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, event_ticker, title, "
            "yes_side_team, first_seen_ms, last_seen_ms) "
            "VALUES (?, ?, ?, ?, 1000, 1000)",
            (ticker, event, f"Game {key} ml", f"Team {key}"),
        )
        cur = conn.execute(
            "INSERT INTO event_links (kalshi_event_ticker, odds_event_id, "
            "league, method, commence_skew_ms, linked_ms) "
            "VALUES (?, ?, 'x', 'exact_alias_pair', 0, 1000)",
            (event, f"odds-{key}"),
        )
        link = int(cur.lastrowid)
        for offset in (600_000, 0):
            conn.execute(
                "INSERT INTO odds_snapshots (fetched_ms, sport_key, "
                "odds_event_id, commence_ms, home_team, away_team, bookmaker, "
                "market, outcome_name, price_decimal) VALUES "
                "(1000, 'baseball_mlb', ?, ?, 'H', 'A', 'pinnacle', 'h2h', 'H', 1.9)",
                (f"odds-{key}", kickoff + offset),
            )
        # Three evaluations; the FRESHEST is inserted FIRST (lowest id), so
        # neither "last inserted" nor "highest id" can stand in for freshest.
        for rank, age in enumerate((1_000, 60_000, 120_000)):
            basis = now - age
            if rank == 0:
                expected_freshest[ticker] = basis
            conn.execute(
                "INSERT INTO recommendations (created_ms, "
                "strategy_config_version, ticker, link_id, side, "
                "entry_ask_tenths, fair_probability, edge_tenths, "
                "fee_predicted, ev_net_dollars, kelly_fraction, "
                "suggested_contracts, reference_contracts, "
                "kalshi_quote_age_ms, odds_age_ms, reason_text) VALUES "
                "(?, 1, ?, ?, 'yes', ?, 0.52, ?, 0.1, 0.2, 0.01, 0, 0, 1000, "
                "2000, 'test row')",
                # Edges run AGAINST kickoff order, so an edge-ordered list
                # cannot pass.
                (basis, ticker, link, 500 + rank, float(i)),
            )
    # A market with no known kickoff: must sort last.
    conn.execute(
        "INSERT INTO kalshi_events (event_ticker, title, first_seen_ms, "
        "last_seen_ms) VALUES ('KXTZZ-EVENT', 'Unlinked', 1000, 1000)"
    )
    conn.execute(
        "INSERT INTO kalshi_markets (ticker, event_ticker, title, "
        "yes_side_team, first_seen_ms, last_seen_ms) "
        "VALUES ('KXTAAA-YES', 'KXTZZ-EVENT', 'u', 'U', 1000, 1000)"
    )
    conn.execute(
        "INSERT INTO recommendations (created_ms, strategy_config_version, "
        "ticker, link_id, side, entry_ask_tenths, fair_probability, "
        "edge_tenths, fee_predicted, ev_net_dollars, kelly_fraction, "
        "suggested_contracts, reference_contracts, kalshi_quote_age_ms, "
        "odds_age_ms, reason_text) VALUES (?, 1, 'KXTAAA-YES', NULL, 'yes', "
        "500, 0.52, 99.0, 0.1, 0.2, 0.01, 0, 0, 1000, 2000, 'test row')",
        (now,),
    )
    return expected_freshest


@pytest.fixture
def seeded(tmp_path):
    path = tmp_path / "one_row_per_market.db"
    conn = db.init_db(path)
    now = db.now_ms()
    expected = _seed(conn, now)
    conn.commit()
    conn.close()
    return create_app(AppConfig(instance_mode="demo", db_path=path)), expected


class TestTheDefaultListIsOneRowPerMarketInKickoffOrder:
    async def test_every_market_in_the_window_appears_once_freshest_first_and_tonight_before_later(
        self, seeded
    ):
        app, expected = seeded
        payload = (await get(app, "/api/slate")).json()
        rows = payload["rows"]
        tickers = [r["ticker"] for r in rows]

        # Default limit 100: each ticker once, and the 100 are the EARLIEST
        # kickoffs (tonight before later), not "the most recently touched".
        assert len(tickers) == len(set(tickers)) == 100
        assert tickers == [f"KXTG{i:03d}-YES" for i in range(100)]
        kicks = [r["commence_ms"] for r in rows]
        assert None not in kicks and kicks == sorted(kicks)

        # Its freshest evaluation, not merely any.
        for r in rows:
            assert (
                r["freshness_measured_from_ms"] == expected[r["ticker"]]
            ), r["ticker"]

        # The counts describe the deduplicated population (111 markets, not
        # 331 rows), so the footnote "N in the window, M shown" stays true.
        slate = payload["slate"]
        assert slate["in_window"] == GAMES + 1
        assert slate["returned"] == 100
        assert slate["truncated"] is True

    async def test_the_whole_list_ends_with_the_unknown_kickoff(self, seeded):
        app, _ = seeded
        payload = (await get(app, "/api/slate", params={"limit": 500})).json()
        tickers = [r["ticker"] for r in payload["rows"]]
        assert len(tickers) == len(set(tickers)) == GAMES + 1
        assert tickers[-1] == "KXTAAA-YES"
        assert payload["rows"][-1]["commence_ms"] is None
        assert payload["slate"]["truncated"] is False

    async def test_the_limit_cuts_the_later_games_not_a_random_few(self, seeded):
        app, _ = seeded
        payload = (await get(app, "/api/slate", params={"limit": 10})).json()
        assert [r["ticker"] for r in payload["rows"]] == [
            f"KXTG{i:03d}-YES" for i in range(10)
        ]
        assert payload["slate"]["in_window"] == GAMES + 1
        assert payload["slate"]["returned"] == 10
        assert payload["slate"]["truncated"] is True


class TestTheTwoSidesOfOneMarketAreStillTwoRows:
    async def test_a_yes_and_a_no_row_of_one_ticker_both_survive_the_dedupe(
        self, tmp_path
    ):
        """A ticker has a YES and a NO row (`test_row_names_its_own_side`
        pins both). The dedupe is per (ticker, side): collapsing by ticker
        alone dropped the NO row whenever it was fresher, and with it the
        game's YES row from the picks block."""
        path = tmp_path / "sides.db"
        conn = db.init_db(path)
        now = db.now_ms()
        _seed(conn, now)
        conn.execute(
            "INSERT INTO recommendations (created_ms, strategy_config_version, "
            "ticker, link_id, side, entry_ask_tenths, fair_probability, "
            "edge_tenths, fee_predicted, ev_net_dollars, kelly_fraction, "
            "suggested_contracts, reference_contracts, kalshi_quote_age_ms, "
            "odds_age_ms, reason_text) VALUES (?, 1, 'KXTG000-YES', NULL, "
            "'no', 500, 0.48, 1.0, 0.1, 0.2, 0.01, 0, 0, 1000, 2000, 'no row')",
            (now,),
        )
        conn.commit()
        conn.close()
        app = create_app(AppConfig(instance_mode="demo", db_path=path))
        rows = (await get(app, "/api/slate", params={"limit": 500})).json()["rows"]
        pairs = [(r["ticker"], r["side"]) for r in rows]
        assert len(pairs) == len(set(pairs)) == GAMES + 2
        assert ("KXTG000-YES", "yes") in pairs
        assert ("KXTG000-YES", "no") in pairs


class TestTheDedupeStaysAnIndexedSeek:
    def test_the_per_ticker_probe_seeks_the_ticker_index(self, tmp_path):
        conn = db.init_db(tmp_path / "plan.db")
        sql = (
            "SELECT r.id FROM recommendations r "
            f"WHERE {_BASIS_SQL} >= ?{_FRESHEST_PER_TICKER_SQL}"
        )
        steps = [
            r["detail"] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, (0,))
        ]
        assert any("SEARCH r2" in s and "ticker=?" in s for s in steps), steps
        conn.close()
