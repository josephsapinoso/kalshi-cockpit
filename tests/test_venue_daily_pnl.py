"""The daily-loss ledger reads the venue's own record, and refuses when it
cannot (ADR 0064).

`bets.venue_daily_realised_pnl_dollars` is the producer behind
`core/sizing.py`'s daily-loss kill switch on the order path. What this file
establishes: the source table is `venue_settlements` and never the engine-path
`settlements`; the day bound is the shared 10:00Z-style roll hour; staleness
of the settlements mirror refuses (`None`) rather than zeroing; a void row is
excluded while a decided-but-unreadable row refuses the whole figure.

What it does NOT establish: that the mirror is complete (the poller's tests
own ingestion), or that the sizer refuses on `None` -- that comparison is
pinned by `tests/test_ev_sizing.py::TestSizingRefusals::
test_unreadable_daily_pnl_refuses_rather_than_assuming_no_losses`, and the
route-level consequence by `tests/test_quote_refresh.py::
TestTheDailyLossLimitReachesTheOrderPath`.

Mutations run against `backend/bets.py`, each red and the file restored
byte-identical: (1) the staleness check removed -- the stale-mirror tests
fail; (2) the `settled_ms >= ?` day bound removed -- the day-boundary test
fails; (3) the source table swapped back to `settlements` -- the fresh-mirror
sum tests fail.
"""

from __future__ import annotations

from backend import bets
from backend.store import db

# The same fixed instants test_bets.py uses: NOW is mid-evening on the 10:00Z
# day, ROLL is that day's start.
DAY_HOUR = 10
ROLL_MS = 1_786_615_200_000  # 2026-08-09T10:00:00Z
NOW_MS = ROLL_MS + 10 * 3_600_000


def _settlements_poll(conn, *, polled_ms, ok=True):
    conn.execute(
        "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count) "
        "VALUES (?, 'settlements', ?, 0)",
        (polled_ms, 1 if ok else 0),
    )
    conn.commit()


def _fills_poll(conn, *, polled_ms, ok=True):
    conn.execute(
        "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count) "
        "VALUES (?, 'fills', ?, 0)",
        (polled_ms, 1 if ok else 0),
    )
    conn.commit()


_TICKER_SEQ = iter(range(10_000))


def _venue(conn, **overrides):
    """One venue settlement. Defaults to a lost $2.00 yes bet with a 2c fee.

    net = payout - cost - fee = 0 - 4x500 - 20 = -2020 tenths (-$2.02).
    Tickers are unique per row because the mirror keys on
    (ticker, settled_ms) and these tests settle many rows at one instant.
    """
    row = {
        "ticker": f"KXVDP-{next(_TICKER_SEQ)}",
        "event_ticker": "KXVDP",
        "market_result": "no",
        "settled_ms": ROLL_MS + 3_600_000,
        "side": "yes",
        "contracts": 4.0,
        "entry_price_tenths": 500,
        "fee_cost_tenths": 20,
    }
    row.update(overrides)
    conn.execute(
        "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
        "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths) "
        "VALUES (:ticker, :event_ticker, :market_result, :settled_ms, :side, "
        ":contracts, :entry_price_tenths, :fee_cost_tenths)",
        row,
    )
    conn.commit()


def _engine_settlement(conn, *, pnl_cents, settled_ms, dry_run=1):
    """A settled engine-path position, exactly as `settle_position` writes one."""
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, first_seen_ms, "
        "last_seen_ms) VALUES ('KXENG-1', 0, 0)"
    )
    conn.execute(
        "INSERT INTO orders (client_order_id, recommendation_id, submitted_ms, "
        "ticker, side, action, order_type, count, limit_price_tenths, status, "
        "request_body_json, dry_run) "
        "VALUES (?, NULL, ?, 'KXENG-1', 'yes', 'buy', 'limit', 10, 500, "
        "'filled', '{}', ?)",
        (f"engine-{next(_TICKER_SEQ)}", settled_ms, dry_run),
    )
    conn.execute(
        "INSERT INTO settlements (order_id, ticker, settled_ms, result, "
        "contracts, pnl_cents, dry_run, fill_assumption) "
        "VALUES (last_insert_rowid(), 'KXENG-1', ?, 'no', 10, ?, ?, 'test')",
        (settled_ms, pnl_cents, dry_run),
    )
    conn.commit()


def _read(conn):
    return bets.venue_daily_realised_pnl_dollars(
        conn, now_ms=NOW_MS, day_start_hour=DAY_HOUR
    )


class TestTheLedgerReadsTheVenueRecord:
    def test_a_fresh_empty_mirror_is_a_true_zero(self, tmp_path):
        """Nothing has settled today, so $0.00 is a measurement, not an
        absence -- the distinction the staleness check exists to preserve."""
        conn = db.init_db(tmp_path / "v.db")
        _settlements_poll(conn, polled_ms=NOW_MS - 60_000)
        assert _read(conn) == 0.0

    def test_the_days_settlements_sum_by_the_registered_formula(self, tmp_path):
        """One loss (-$2.02) and one win (+$1.18, `test_bets.py`'s worked
        example: 2 contracts at 40c winning, 2c fee), in dollars."""
        conn = db.init_db(tmp_path / "v.db")
        _settlements_poll(conn, polled_ms=NOW_MS - 60_000)
        _venue(conn)  # -2020 tenths
        _venue(
            conn, market_result="yes", contracts=2.0, entry_price_tenths=400,
        )  # +1180 tenths
        assert _read(conn) == (-2020 + 1180) / 1000.0

    def test_the_engine_settlements_table_is_ignored_even_when_populated(
        self, tmp_path
    ):
        """The defect ADR 0064 corrects, inverted: engine-path `settlements`
        is written only by a sweep over `orders`, which has never held a real
        bet, so it must not be the denominator -- paper losses there, on
        either `dry_run` flag, do not move the venue figure."""
        conn = db.init_db(tmp_path / "v.db")
        _settlements_poll(conn, polled_ms=NOW_MS - 60_000)
        _engine_settlement(conn, pnl_cents=-50_000, settled_ms=NOW_MS, dry_run=1)
        _engine_settlement(conn, pnl_cents=-50_000, settled_ms=NOW_MS, dry_run=0)
        assert _read(conn) == 0.0


class TestAStaleMirrorRefuses:
    """`None`, never `0.0`: "cannot determine what I have lost today" must
    not resolve to "nothing" on the exact quantity built to stop a bet."""

    def test_a_stale_mirror_refuses_rather_than_reporting_no_losses(
        self, tmp_path
    ):
        conn = db.init_db(tmp_path / "v.db")
        _settlements_poll(
            conn, polled_ms=NOW_MS - bets.TONIGHT_STALE_AFTER_MS - 1
        )
        _venue(conn)  # a real loss is sitting in the mirror
        assert _read(conn) is None

    def test_a_mirror_never_polled_refuses(self, tmp_path):
        conn = db.init_db(tmp_path / "v.db")
        assert _read(conn) is None

    def test_a_failed_poll_is_not_a_read(self, tmp_path):
        conn = db.init_db(tmp_path / "v.db")
        _settlements_poll(conn, polled_ms=NOW_MS - 60_000, ok=False)
        assert _read(conn) is None

    def test_a_fresh_fills_poll_does_not_vouch_for_the_settlements_mirror(
        self, tmp_path
    ):
        """The staleness bound is per endpoint. Fills ride the same 5-minute
        cadence and an implementation copying `tonight_activity`'s
        `endpoint = 'fills'` read would pass every other test here while
        summing a settlements table nobody has refreshed."""
        conn = db.init_db(tmp_path / "v.db")
        _fills_poll(conn, polled_ms=NOW_MS - 60_000)
        _settlements_poll(
            conn, polled_ms=NOW_MS - bets.TONIGHT_STALE_AFTER_MS - 1
        )
        assert _read(conn) is None


class TestTheDayBoundary:
    def test_a_loss_before_the_day_roll_does_not_count(self, tmp_path):
        """The limit is daily: yesterday's loss is outside the risk day, at
        the same roll hour the `tonight` strip and the odds budget use --
        summing it would turn the kill switch into a permanent off switch
        after one bad night."""
        conn = db.init_db(tmp_path / "v.db")
        _settlements_poll(conn, polled_ms=NOW_MS - 60_000)
        _venue(conn, settled_ms=ROLL_MS - 1)  # before the roll: excluded
        _venue(conn, settled_ms=ROLL_MS)      # on the roll: counted
        assert _read(conn) == -2020 / 1000.0


class TestVoidAndUnreadableRows:
    def test_a_void_settlement_is_excluded_not_a_wash(self, tmp_path):
        """A `market_result` that is neither yes nor no has no registered
        payout. It is excluded and counted, matching `bets_record` -- one
        scratched market must not stand as a permanent order block."""
        conn = db.init_db(tmp_path / "v.db")
        _settlements_poll(conn, polled_ms=NOW_MS - 60_000)
        _venue(conn)                          # -2020 tenths
        _venue(conn, market_result=None)      # void: excluded
        assert _read(conn) == -2020 / 1000.0

    def test_a_decided_but_unreadable_row_refuses_the_whole_figure(
        self, tmp_path
    ):
        """The one place this module is stricter than the display: the sizer
        receives a single float with no `uncomputable` count beside it, so a
        silently dropped loss would understate the day in the flattering
        direction. Refuse instead."""
        conn = db.init_db(tmp_path / "v.db")
        _settlements_poll(conn, polled_ms=NOW_MS - 60_000)
        _venue(conn)  # perfectly readable
        _venue(conn, market_result="no", entry_price_tenths=None)
        assert _read(conn) is None
