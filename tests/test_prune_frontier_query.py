"""`inspect_live_db.py prune-frontier`: the durable stand-in for `quotes_pruned`.

Why it exists
-------------
On 2026-08-20 the window-gate registration
(`docs/measurements/2026-08-20-window-gate-plan.md`) registered four
observations, and observation 1 -- "no `quotes_pruned` above 0 on any pass
inside the open window" -- turned out to have no durable reading at all.
`quotes_pruned` is a `PassCounts` field that reaches the process log and no
table, and `flyctl logs` drops lines, so the absence of a prune line is
indistinguishable from a dropped one. This query is what makes the next window
measurable instead.

The whole point is one column choice
------------------------------------
The handoff proposed `MIN(observed_ms)` as the proxy. It is wrong, and wrong in
the direction that flatters: `prune_quotes` selects on
`COALESCE(confirmed_ms, observed_ms)`, so a change-log row with an ancient
`observed_ms` and a fresh `confirmed_ms` survives every prune and pins
`MIN(observed_ms)` in place. A frontier computed that way would have read "no
prune ran" through a prune that deleted 40,000 rows. `TestTheColumnChoiceIsTheWholePoint`
is that scenario, and it is red against the `observed_ms` spelling.

Every class below states the mutation it was observed red under, per the
standard `tests/test_inspect_live_db.py` sets.

What these tests do not establish
---------------------------------
- **Nothing about the live database**, or about whether a prune ever ran on it.
  Every row here was inserted by this file.
- **Nothing about when a prune ran**, which the query itself disclaims: while
  the backlog is non-zero the frontier lags the cutoff by an unknown amount and
  only its *change* between two readings is interpretable.
- **Nothing about `unmatched_items`**, which has its own retention and budget.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pytest

from backend.store import retention
from scripts.inspect_live_db import (
    _QUOTE_RETENTION_MS,
    QUERIES,
    connect_readonly,
    resolve_query,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "backend" / "store" / "schema.sql"

DAY_MS = 24 * 60 * 60 * 1000
#: A fixed "now" so the fixtures do not drift with the wall clock. The query
#: stamps its own `now`, so the rows are placed relative to a cutoff derived the
#: same way the query derives it.
NOW_MS = 1787232000000  # 2026-08-20T13:20:00Z


def _args(limit: int = 2000) -> argparse.Namespace:
    return argparse.Namespace(limit=limit)


def _db(tmp_path, quotes, *, recommended: tuple[str, ...] = ()) -> Path:
    """A schema-real database holding exactly `quotes`.

    `quotes` is `(ticker, observed_ms, confirmed_ms)`. Tickers in `recommended`
    get a `recommendations` row, which is what puts them beyond the prune's
    reach and therefore outside the frontier.
    """
    path = tmp_path / "cockpit.db"
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO kalshi_series (series_ticker, league, first_seen_ms, "
        "last_seen_ms) VALUES ('KXMLBGAME', 'mlb', 1, 1)"
    )
    conn.execute(
        "INSERT INTO kalshi_events (event_ticker, series_ticker, commence_ms, "
        "close_ms, status, first_seen_ms, last_seen_ms) "
        "VALUES ('E1', 'KXMLBGAME', 1, NULL, 'open', 1, 1)"
    )
    for ticker in sorted({q[0] for q in quotes}):
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, event_ticker, series_ticker, "
            "market_type, status, first_seen_ms, last_seen_ms) "
            "VALUES (?, 'E1', 'KXMLBGAME', 'moneyline', 'active', 1, 1)",
            (ticker,),
        )
    for ticker, observed_ms, confirmed_ms in quotes:
        conn.execute(
            "INSERT INTO kalshi_quotes (ticker, observed_ms, confirmed_ms, "
            "source, yes_bid_tenths, no_bid_tenths) VALUES (?, ?, ?, 'rest', "
            "500, 500)",
            (ticker, observed_ms, confirmed_ms),
        )
    if recommended:
        # `recommendations.strategy_config_version` is a real foreign key, so
        # the seed row is required rather than tidy.
        conn.execute(
            "INSERT INTO strategy_configs (version, created_ms, "
            "effective_from_ms, config_json, rationale) "
            "VALUES (1, 1, 1, '{}', 'seed')"
        )
    for ticker in recommended:
        conn.execute(
            "INSERT INTO recommendations (created_ms, strategy_config_version, "
            "ticker, side, entry_ask_tenths, fair_probability, edge_tenths, "
            "fee_predicted, ev_net_dollars, kelly_fraction, "
            "suggested_contracts, kalshi_quote_age_ms, odds_age_ms, "
            "reason_text) VALUES (1, 1, ?, 'yes', 500, 0.5, 1.0, 0.01, 0.01, "
            "0.01, 0, 100, 100, 'x')",
            (ticker,),
        )
    conn.commit()
    conn.close()
    return path


def _read(path: Path) -> dict:
    conn = connect_readonly(str(path))
    try:
        sections = resolve_query("prune-frontier").run(conn, _args())
    finally:
        conn.close()
    section = sections[0]
    assert section.row_count == 1, "the frontier is one aggregate row"
    return dict(zip(section.columns, section.rows[0]))


class TestItIsOnTheWhitelist:
    """Mutation: delete the `"prune-frontier"` entry from `QUERIES`. Red."""

    def test_the_name_resolves(self):
        assert "prune-frontier" in QUERIES
        assert resolve_query("prune-frontier").run is not None

    def test_its_description_names_the_column_that_matters(self):
        """A caller choosing off the whitelist must be told which column the
        frontier is on, because the obvious other one is wrong."""
        assert "confirmed_ms" in QUERIES["prune-frontier"].description


class TestTheRetentionConstantCannotDriftFromThePrune:
    """Mutation: change `_QUOTE_RETENTION_MS` to 2 days. Red.

    The script is deliberately stdlib-only, so the window is duplicated rather
    than imported. Duplication is acceptable only while something checks it.
    """

    def test_it_equals_the_prunes_own_default(self):
        assert _QUOTE_RETENTION_MS == retention.DEFAULT_QUOTE_RETENTION_MS


class TestTheColumnChoiceIsTheWholePoint:
    """Mutation: swap `COALESCE(confirmed_ms, observed_ms)` for `observed_ms`
    in `_SQL_PRUNE_FRONTIER`. Red on both tests below."""

    def test_a_stale_observed_ms_with_a_fresh_confirmed_ms_is_not_the_frontier(
        self, tmp_path
    ):
        # The ADR 0055 change-log row: first seen ten days ago, re-confirmed a
        # minute ago because the price never moved. The prune keeps it.
        path = _db(tmp_path, [("T1", NOW_MS - 10 * DAY_MS, NOW_MS - 60_000)])
        row = _read(path)
        assert row["frontier_ms"] == NOW_MS - 60_000
        assert row["backlog_rows"] == 0

    def test_that_row_is_not_counted_as_backlog(self, tmp_path):
        """The flattering failure: a frontier on `observed_ms` reports a
        ten-day-old backlog that the prune will never touch, so a session
        chasing it finds a prune that deletes nothing and calls it broken."""
        path = _db(tmp_path, [("T1", NOW_MS - 10 * DAY_MS, NOW_MS - 60_000)])
        assert _read(path)["backlog_rows"] == 0

    def test_a_null_confirmed_ms_falls_back_to_observed_ms(self, tmp_path):
        """COALESCE, not a bare `confirmed_ms`. Mutation: drop the COALESCE and
        select `confirmed_ms` alone -- rows never re-confirmed vanish from the
        frontier entirely and it reads NULL."""
        path = _db(tmp_path, [("T1", NOW_MS - 10 * DAY_MS, None)])
        row = _read(path)
        assert row["frontier_ms"] == NOW_MS - 10 * DAY_MS
        assert row["backlog_rows"] == 1


class TestRecommendedTickersAreOutsideTheFrontier:
    """Mutation: delete `AND ticker NOT IN (SELECT ticker FROM recommendations)`
    from both subqueries. Red on both tests below.

    `prune_quotes` carries the same exclusion, so a row it may not delete is not
    part of how far it has got. Counting one would pin the frontier at a row no
    prune can ever move, and every reading either side of a window would then be
    identical -- which reads as "no prune ran", always.
    """

    def test_a_recommended_tickers_old_row_does_not_pin_the_frontier(self, tmp_path):
        path = _db(
            tmp_path,
            [
                ("T1", NOW_MS - 10 * DAY_MS, NOW_MS - 10 * DAY_MS),
                ("T2", NOW_MS - 60_000, NOW_MS - 60_000),
            ],
            recommended=("T1",),
        )
        row = _read(path)
        assert row["frontier_ms"] == NOW_MS - 60_000

    def test_it_is_not_counted_as_backlog_either(self, tmp_path):
        path = _db(
            tmp_path,
            [("T1", NOW_MS - 10 * DAY_MS, NOW_MS - 10 * DAY_MS)],
            recommended=("T1",),
        )
        row = _read(path)
        assert row["backlog_rows"] == 0
        assert row["prunable_rows"] == 0
        # Still visible in the total, so the row is excluded rather than lost.
        assert row["total_rows"] == 1


class TestTheBacklogIsTheDenominator:
    """Mutation: change `<` to `<=` on the backlog predicate, or drop the
    `:cutoff` bind and hardcode a date. Red.

    A zero prune inside a window means nothing if the prune had nothing to
    delete. This is the number to read first, which is why it is in the same row
    rather than a second query nobody runs.
    """

    def test_rows_below_the_cutoff_are_backlog(self, tmp_path):
        path = _db(
            tmp_path,
            [
                ("T1", NOW_MS - 5 * DAY_MS, NOW_MS - 5 * DAY_MS),
                ("T2", NOW_MS - 4 * DAY_MS, NOW_MS - 4 * DAY_MS),
                ("T3", NOW_MS - 60_000, NOW_MS - 60_000),
            ],
        )
        row = _read(path)
        assert row["backlog_rows"] == 2
        assert row["prunable_rows"] == 3

    def test_an_empty_backlog_is_reported_as_zero_and_not_as_null(self, tmp_path):
        """`0` here means "the prune has nothing to do", which is a real state
        and must not arrive as NULL beside a NULL frontier."""
        path = _db(tmp_path, [("T1", NOW_MS - 60_000, NOW_MS - 60_000)])
        row = _read(path)
        assert row["backlog_rows"] == 0
        assert row["frontier_ms"] is not None

    def test_the_cutoff_is_reported_so_the_reading_carries_its_own_moment(
        self, tmp_path
    ):
        path = _db(tmp_path, [("T1", NOW_MS - 60_000, NOW_MS - 60_000)])
        row = _read(path)
        assert row["cutoff_iso"] is not None
        assert row["cutoff_ms"] < row["frontier_ms"]


class TestAnEmptyTableSaysNothingRatherThanZero:
    """Mutation: wrap the frontier in `COALESCE(..., 0)`. Red.

    This repo's standing rule: unreadable resolves to `None`, never `0`. A
    frontier of 0 is 1970, and `frontier + retention` would date the last prune
    to the Nixon administration rather than refusing to answer.
    """

    def test_the_frontier_is_null_on_an_empty_table(self, tmp_path):
        row = _read(_db(tmp_path, []))
        assert row["frontier_ms"] is None
        assert row["frontier_iso"] is None
        assert row["total_rows"] == 0


class TestItStaysReadOnly:
    """Mutation: open the connection without `mode=ro`. Red."""

    def test_the_connection_refuses_a_write(self, tmp_path):
        path = _db(tmp_path, [("T1", NOW_MS - 60_000, NOW_MS - 60_000)])
        conn = connect_readonly(str(path))
        try:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute("DELETE FROM kalshi_quotes")
        finally:
            conn.close()
