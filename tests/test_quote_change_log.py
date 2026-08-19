"""`kalshi_quotes` is a change log, and `confirmed_ms` is what keeps that safe.

**What this establishes.** That an unchanged quote writes no row and advances
`confirmed_ms` on the existing one; that a moved quote writes a row; that
staleness is measured from `confirmed_ms` and not `observed_ms`; that retention
keeps a row whose price is old but whose confirmation is recent; that the drift
column reports a measured 0 for a market confirmed steady across its window, and
still `None` across a gap in the record; and that recorder liveness survives a
pass that legitimately wrote nothing.

**What it does not.** It does not establish that the write rate falls -- that is
a property of the live slate (84.5% on 2026-08-19) and is measured on live, not
here. It does not establish that any of this is fast. And it says nothing about
concurrent writers: every test here drives one connection, where live has the
loop and the API process.

**Why it exists.** ADR 0055. The prune cannot win at any schedule -- its ceiling
is 3.84M rows/day against 7.77M written -- so the writer has to write less. The
obvious way to do that is a product outage, and these tests exist mostly to pin
the parts that make it not one.

The failure being guarded against is specific and quiet. Suppression refuses a
row whose Kalshi quote is older than 30s. Under a change log `observed_ms` stops
advancing while a price holds, so measuring age from it would refuse **84.5% of
the slate** as stale -- hitting hardest the markets that are quietest, which are
the ones whose prices are most reliably known. Nothing would error. The tool
would simply go quiet.
"""

from __future__ import annotations

import pytest

from backend import runner
from backend.runner import latest_kalshi_quote, quote_age_ms
from backend.slate import kalshi_drift
from backend.store import db, retention

TICKER = "KXMLBGAME-26AUG19CHIPIT-CHI"
NOW = 1_787_000_000_000
HOUR_MS = 3_600_000


@pytest.fixture()
def conn(tmp_path):
    c = db.init_db(tmp_path / "change_log.db")
    c.execute(
        "INSERT INTO kalshi_series (series_ticker, league, has_game_markets, "
        "first_seen_ms, last_seen_ms) VALUES ('KXMLBGAME', 'Pro Baseball', 1, ?, ?)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO kalshi_events (event_ticker, series_ticker, title, category, "
        "commence_ms, status, first_seen_ms, last_seen_ms) "
        "VALUES ('KXMLBGAME-26AUG19CHIPIT', 'KXMLBGAME', 'Cubs at Pirates', "
        "'Sports', ?, 'open', ?, ?)",
        (NOW + HOUR_MS, NOW, NOW),
    )
    c.execute(
        "INSERT INTO kalshi_markets (ticker, event_ticker, series_ticker, title, "
        "market_type, status, first_seen_ms, last_seen_ms) "
        "VALUES (?, 'KXMLBGAME-26AUG19CHIPIT', 'KXMLBGAME', 'Cubs', 'game', "
        "'active', ?, ?)",
        (TICKER, NOW, NOW),
    )
    c.commit()
    try:
        yield c
    finally:
        c.close()


def _quote(conn, *, observed_ms, confirmed_ms, yes_bid=400, no_bid=560):
    conn.execute(
        "INSERT INTO kalshi_quotes (ticker, observed_ms, confirmed_ms, source, "
        "yes_bid_tenths, yes_bid_qty, no_bid_tenths, no_bid_qty) "
        "VALUES (?, ?, ?, 'rest', ?, 100.0, ?, 100.0)",
        (TICKER, observed_ms, confirmed_ms, yes_bid, no_bid),
    )
    conn.commit()


class TestStalenessMeasuresConfirmationNotAppearance:
    """The check that decides whether 84.5% of the slate is bettable."""

    def test_a_price_that_has_held_for_an_hour_is_seconds_old(self, conn):
        _quote(conn, observed_ms=NOW - HOUR_MS, confirmed_ms=NOW - 5_000)

        row = latest_kalshi_quote(conn, TICKER)

        assert quote_age_ms(row, now=NOW) == 5_000, (
            "quote age was measured from when the price first appeared, so a "
            "market that simply has not moved reads as a stale quote and is "
            "suppressed -- the failure ADR 0055 exists to avoid"
        )

    def test_a_genuinely_old_confirmation_is_still_old(self, conn):
        """The other side, or the test above passes on a hardcoded zero."""
        _quote(conn, observed_ms=NOW - HOUR_MS, confirmed_ms=NOW - HOUR_MS)

        row = latest_kalshi_quote(conn, TICKER)

        assert quote_age_ms(row, now=NOW) == HOUR_MS

    def test_a_row_from_before_the_adr_falls_back_to_observed_ms(self, conn):
        """`confirmed_ms` is NULL on every row written before ADR 0055.

        Resolving that to 0, or to `now`, would report a quote nobody has
        looked at since it was written as freshly confirmed -- the migration is
        deliberately backfill-free, so this path is the live one for millions of
        rows.
        """
        conn.execute(
            "INSERT INTO kalshi_quotes (ticker, observed_ms, source, "
            "yes_bid_tenths, no_bid_tenths) VALUES (?, ?, 'rest', 400, 560)",
            (TICKER, NOW - 45_000),
        )
        conn.commit()

        row = latest_kalshi_quote(conn, TICKER)

        assert row["confirmed_ms"] is None
        assert quote_age_ms(row, now=NOW) == 45_000


class TestRetentionKeepsWhatIsStillTrue:
    def test_a_price_confirmed_now_survives_however_old_it_is(self, conn):
        """Selecting on `observed_ms` would delete the live quote.

        A market whose price has genuinely not moved in three days has exactly
        one row under a change log. Deleting it leaves the market with no quote
        at all until the next pass rewrites it -- `latest_kalshi_quote` returns
        `None` for a market that is perfectly well priced.
        """
        four_days = 4 * 24 * HOUR_MS
        _quote(conn, observed_ms=NOW - four_days, confirmed_ms=NOW - 5_000)

        removed = retention.prune_quotes(conn, now=NOW)

        assert removed == 0, "retention deleted the price standing right now"
        assert latest_kalshi_quote(conn, TICKER) is not None

    def test_a_price_nobody_has_confirmed_since_the_window_still_goes(self, conn):
        """Or the guard above is satisfied by a prune that deletes nothing."""
        four_days = 4 * 24 * HOUR_MS
        _quote(conn, observed_ms=NOW - four_days, confirmed_ms=NOW - four_days)

        removed = retention.prune_quotes(conn, now=NOW)

        assert removed == 1
        assert latest_kalshi_quote(conn, TICKER) is None


class TestDriftSurvivesTheCopiesBeingRemoved:
    def test_a_market_confirmed_steady_all_window_reports_zero(self, conn):
        """A measured 0, not an absent reading.

        Under the pre-ADR writer this market had ~240 identical rows in the
        window and the answer was 0. It has one row now, and returning `None`
        would blank the column for exactly the markets whose drift is most
        confidently known.
        """
        _quote(conn, observed_ms=NOW - 3 * HOUR_MS, confirmed_ms=NOW - 1_000)

        assert kalshi_drift(
            conn, TICKER, "yes", now_ms=NOW, window_ms=HOUR_MS
        ) == 0

    def test_a_gap_in_the_record_is_not_differenced_across(self, conn):
        """The ambiguity `confirmed_ms` exists to resolve.

        No row for an hour means either the price held or nobody was looking.
        A quote last confirmed before the window opened is the second case, and
        differencing across it would report a recorder outage as an hour of
        movement.
        """
        _quote(
            conn,
            observed_ms=NOW - 3 * HOUR_MS,
            confirmed_ms=NOW - 2 * HOUR_MS,
            no_bid=900,
        )
        _quote(conn, observed_ms=NOW, confirmed_ms=NOW, no_bid=500)

        assert kalshi_drift(
            conn, TICKER, "yes", now_ms=NOW, window_ms=HOUR_MS
        ) is None, (
            "a quote nobody confirmed inside the window was used as a baseline, "
            "so a gap in the record reads as price movement"
        )

    def test_a_real_move_is_still_measured(self, conn):
        _quote(
            conn,
            observed_ms=NOW - 3 * HOUR_MS,
            confirmed_ms=NOW - 30 * 60_000,
            no_bid=900,
        )
        _quote(conn, observed_ms=NOW - 10 * 60_000, confirmed_ms=NOW, no_bid=500)

        # yes ask = 1000 - no_bid, so 100 -> 500.
        assert kalshi_drift(
            conn, TICKER, "yes", now_ms=NOW, window_ms=HOUR_MS
        ) == 400


class TestRecorderLivenessSurvivesAQuietSlate:
    """A pass that wrote nothing and a recorder that is dead look identical.

    Before ADR 0055 liveness was "the newest row in `kalshi_quotes`", which was
    exact while every pass wrote ~6,000 of them. Under a change log a slate
    where nothing moved legitimately writes none.
    """

    def test_a_database_whose_recorder_never_ran_reads_none(self, conn):
        assert db.recorder_last_write_ms(conn) is None, (
            "an unknown heartbeat resolved to a number, so a recorder that has "
            "never run would report as healthy"
        )

    def test_the_heartbeat_survives_a_pass_that_wrote_no_row(self, conn):
        _quote(conn, observed_ms=NOW - HOUR_MS, confirmed_ms=NOW - HOUR_MS)
        db.set_recorder_heartbeat(conn, NOW)
        conn.commit()

        assert db.recorder_last_write_ms(conn) == NOW

    def test_a_pass_that_wrote_no_row_still_moves_the_heartbeat(self, conn):
        """**The claim the two tests above cannot make**, and the gap was real.

        Deleting `db.set_recorder_heartbeat` from the writer left every other
        test in this file green, because they all call the helper directly.
        That is a guard testing itself. This one drives the writer and asserts
        the side effect, on the quiet-slate path -- an unchanged book, where no
        row is written and the heartbeat is the *only* evidence the recorder
        ran.
        """
        writer = TestTheWriterItself()
        events = [writer._market(yes_bid_tenths=400, no_bid_tenths=560)]
        runner.store_quotes_from_discovery(conn, events, now=NOW)

        _, written = runner.store_quotes_from_discovery(
            conn, events, now=NOW + 15_000
        )

        assert written == 0, "the book moved; this is not the quiet-slate path"
        assert db.recorder_last_write_ms(conn) == NOW + 15_000, (
            "a pass that legitimately wrote no row left the heartbeat behind, "
            "so a healthy recorder on a quiet slate reports as stuck"
        )

    def test_it_moves_forward_rather_than_accumulating(self, conn):
        db.set_recorder_heartbeat(conn, NOW)
        db.set_recorder_heartbeat(conn, NOW + 15_000)
        conn.commit()

        assert db.recorder_last_write_ms(conn) == NOW + 15_000
        assert conn.execute(
            "SELECT COUNT(*) n FROM meta WHERE key = ?",
            (db.RECORDER_HEARTBEAT_KEY,),
        ).fetchone()["n"] == 1


class TestTheWriterItself:
    """`store_quotes_from_discovery` at the level the pass tests cannot reach."""

    def _market(self, *, yes_bid_tenths, no_bid_tenths):
        from backend.kalshi.discovery import DiscoveredEvent, DiscoveredMarket

        market = DiscoveredMarket(
            ticker=TICKER,
            event_ticker="KXMLBGAME-26AUG19CHIPIT",
            series_ticker="KXMLBGAME",
            title="Cubs",
            yes_side="Chicago Cubs",
            market_type="game",
            strike=None,
            player_name=None,
            price_structure=None,
            close_ms=NOW + HOUR_MS,
            status="active",
            result=None,
            volume_24h=0,
            open_interest=0,
            yes_bid_tenths=yes_bid_tenths,
            no_bid_tenths=no_bid_tenths,
            yes_ask_size=100.0,
            no_ask_size=100.0,
        )
        return DiscoveredEvent(
            event_ticker="KXMLBGAME-26AUG19CHIPIT",
            series_ticker="KXMLBGAME",
            league="Pro Baseball",
            sport_key="baseball_mlb",
            market_type="game",
            title="Cubs at Pirates",
            commence_ms=NOW + HOUR_MS,
            markets=[market],
        )

    def test_an_unchanged_quote_writes_no_row_and_confirms_the_old_one(self, conn):
        events = [self._market(yes_bid_tenths=400, no_bid_tenths=560)]

        quoted, written = runner.store_quotes_from_discovery(
            conn, events, now=NOW
        )
        assert (quoted, written) == (1, 1), "the first observation must be stored"

        quoted, written = runner.store_quotes_from_discovery(
            conn, events, now=NOW + 15_000
        )

        assert quoted == 1, "the market still carried a readable quote"
        assert written == 0, "an unchanged quote wrote a row"
        assert conn.execute(
            "SELECT COUNT(*) n FROM kalshi_quotes"
        ).fetchone()["n"] == 1
        assert latest_kalshi_quote(conn, TICKER)["confirmed_ms"] == NOW + 15_000

    def test_a_moved_quote_writes_a_row(self, conn):
        runner.store_quotes_from_discovery(
            conn, [self._market(yes_bid_tenths=400, no_bid_tenths=560)], now=NOW
        )

        quoted, written = runner.store_quotes_from_discovery(
            conn,
            [self._market(yes_bid_tenths=410, no_bid_tenths=550)],
            now=NOW + 15_000,
        )

        assert (quoted, written) == (1, 1)
        assert conn.execute(
            "SELECT COUNT(*) n FROM kalshi_quotes"
        ).fetchone()["n"] == 2
        assert latest_kalshi_quote(conn, TICKER)["yes_bid_tenths"] == 410

    def test_a_market_with_neither_bid_is_neither_quoted_nor_written(self, conn):
        quoted, written = runner.store_quotes_from_discovery(
            conn,
            [self._market(yes_bid_tenths=None, no_bid_tenths=None)],
            now=NOW,
        )

        assert (quoted, written) == (0, 0), (
            "a market with no readable bid was counted as quoted, which would "
            "put a fabricated price in the denominator"
        )
