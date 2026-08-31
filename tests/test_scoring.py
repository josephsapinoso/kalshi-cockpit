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

import sqlite3

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
        # No `end_period_ts`, so `observed_ms` falls back to the requested
        # target instant. That is both realistic and necessary: the field is
        # unverified against a real capture, and an arbitrary value here dates
        # the closing line before the recommendation, which
        # `score_recommendations` now (correctly) refuses to score.
        # `close_dollars`, matching the real wire format captured in
        # tests/fixtures/candlesticks_mlb.json. This fake used `close`, which
        # Kalshi has never sent -- so it agreed with the parser's bug and six
        # tests here went green over a scorer that could not read a single
        # quote. A fake that mirrors the code's assumption instead of the wire
        # tests the assumption against itself.
        self.candles = candles if candles is not None else [
            {"yes_bid": {"close_dollars": "0.5200"},
             "yes_ask": {"close_dollars": "0.5400"}}
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
          true_commence=TRUE_COMMENCE, created_ms=None):
    """One linked, unscored recommendation on a game that has already started.

    `created_ms` defaults to **two hours before the true start**, which puts it
    before the 1h closing line is observed. That ordering is required, not
    cosmetic: `score_recommendations` refuses to score an entry against a quote
    that predates it. These tests originally created the recommendation one hour
    before `NOW` — three hours *after* the 1h line was observed — and adding
    that rule turned five of them red, which is the rule working rather than a
    regression.
    """
    if created_ms is None:
        created_ms = true_commence - 2 * HOUR_MS
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
        (created_ms, ticker, link_id, side, ask),
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


def _seed_hand_bet(conn, *, ticker="KXMLBGAME-T-C", side="yes",
                    true_commence=TRUE_COMMENCE, settled_ms=None, linked=True):
    """One of Joe's own settled bets, mirrored into `venue_settlements` with
    no `recommendations` row -- the case the union branch exists for."""
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
    if linked:
        conn.execute(
            "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, odds_event_id, "
            "league, method, commence_skew_ms, linked_ms) "
            "VALUES ('EVT','odds-1','Pro Baseball','exact_alias_pair',?,?)",
            (-3 * HOUR_MS, NOW),
        )
        conn.execute(
            "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, sport_key, "
            "odds_event_id, commence_ms, home_team, away_team, bookmaker, market, "
            "outcome_name, price_decimal) "
            "VALUES (?,?,'baseball_mlb','odds-1',?,'B','A','pinnacle','h2h','A',2.0)",
            (NOW, NOW, true_commence),
        )
    conn.execute(
        "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
        "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths) "
        "VALUES (?, 'EVT', 'yes', ?, ?, 1.0, 480, 5)",
        (ticker, settled_ms if settled_ms is not None else NOW, side),
    )
    conn.commit()


class TestHandBetsJoinTheUnion:
    """`venue_settlements`-only tickers (Joe's own bets, no `recommendations`
    row) need a closing line too, added 2026-08-22. Most hand-bet tickers
    refuse structurally -- no discovery row, or no matcher link -- and that
    is expected and honest, per the partner's ruling on the re-scoped CLV
    item, not a bug to chase.
    """

    async def test_a_linked_hand_bet_with_no_recommendation_is_picked_up(self, conn):
        _seed_hand_bet(conn, ticker="KXMLBGAME-T-C")
        pending = markets_awaiting_scoring(conn, now=NOW)
        assert len(pending) == 1
        assert pending[0]["ticker"] == "KXMLBGAME-T-C"
        assert pending[0]["true_commence_ms"] == TRUE_COMMENCE

    async def test_an_unlinked_hand_bet_refuses_structurally(self, conn):
        """No `event_links` row -- the common case for a hand bet."""
        _seed_hand_bet(conn, ticker="KXMLBGAME-T-D", linked=False)
        assert markets_awaiting_scoring(conn, now=NOW) == []

    async def test_a_hand_bet_gets_a_closing_line_stored(self, conn):
        _seed_hand_bet(conn, ticker="KXMLBGAME-T-C")
        counts = await run_scoring_pass(conn, FakeKalshi(), now=NOW)

        assert counts.lines_stored == 2      # both horizons
        stored = {
            r["horizon_hours"]
            for r in conn.execute(
                "SELECT horizon_hours FROM closing_lines WHERE ticker = ?",
                ("KXMLBGAME-T-C",),
            )
        }
        assert stored == {DEFAULT_HORIZON_HOURS, CONTROL_HORIZON_HOURS}

    async def test_it_stops_once_any_closing_line_exists(self, conn):
        """There is no `clv_scored_ms` on `venue_settlements` to flip, so the
        stop-predicate is structural: any stored `closing_lines` row for the
        ticker, at either horizon -- else it is refetched every pass forever.
        """
        _seed_hand_bet(conn, ticker="KXMLBGAME-T-C")
        await run_scoring_pass(conn, FakeKalshi(), now=NOW)
        assert markets_awaiting_scoring(conn, now=NOW) == []

        again = await run_scoring_pass(conn, FakeKalshi(), now=NOW + 60_000)
        assert again.markets_considered == 0

    async def test_a_bet_on_a_ticker_with_a_scored_recommendation_is_not_double_counted(
        self, conn
    ):
        """The UNION collapses the duplicate (ticker, series, commence) row a
        market shared by both a recommendation and a hand bet would otherwise
        produce."""
        _seed(conn, ticker="KXMLBGAME-T-A")
        _seed_hand_bet(conn, ticker="KXMLBGAME-T-A")
        assert len(markets_awaiting_scoring(conn, now=NOW)) == 1


class TestSelection:
    async def test_only_unscored_linked_markets_are_considered(self, conn):
        _seed(conn)
        pending = markets_awaiting_scoring(conn, now=NOW)
        assert len(pending) == 1
        assert pending[0]["true_commence_ms"] == TRUE_COMMENCE
        assert pending[0]["started"] is True

        await run_scoring_pass(conn, FakeKalshi(), now=NOW)
        assert markets_awaiting_scoring(conn, now=NOW) == []


class TestTheScoringPassRespectsTheTemporalRule:
    """The two halves have to agree about when the closing line was observed.

    `scoring.py` decides *when* to read a quote; `clv.score_recommendations`
    decides whether an entry may be compared against it. They are in different
    modules and nothing links them, so this pins the interaction.
    """

    async def test_an_entry_after_the_line_is_not_scored(self, conn):
        """The rule itself, at the primary horizon.

        The line is observed at kickoff, so an entry *after* kickoff post-dates
        it. The runner refuses to record a started game now, but rows written
        before that guard existed are on the live volume, and the rule is what
        stops them being scored against a price that predates them.
        """
        _seed(conn, created_ms=TRUE_COMMENCE + 30 * 60_000)
        counts = await run_scoring_pass(conn, FakeKalshi(), now=NOW)

        assert counts.scored == 0
        assert counts.skipped_entry_after_close == 1
        assert counts.skipped_no_mid == 0, "wrong reason -- the quote was readable"
        assert conn.execute(
            "SELECT clv_tenths FROM recommendations"
        ).fetchone()["clv_tenths"] is None

    async def test_the_rule_is_relative_to_the_horizon_not_to_kickoff(self, conn):
        """The same entry, scoreable at one horizon and not at another.

        A recommendation 30 minutes before kickoff sits *after* a line read an
        hour out and *before* one read at kickoff. That is the whole of ADR
        0011 in one pair: the horizon decides which rows can be measured at all,
        and at 1.0h against today's sweep timing the answer was none of them.
        """
        _seed(conn, created_ms=TRUE_COMMENCE - 30 * 60_000)

        at_an_hour = await run_scoring_pass(
            conn, FakeKalshi(), now=NOW, primary_horizon=1.0
        )
        assert at_an_hour.scored == 0
        assert at_an_hour.skipped_entry_after_close == 1

        at_kickoff = await run_scoring_pass(
            conn, FakeKalshi(), now=NOW, primary_horizon=DEFAULT_HORIZON_HOURS
        )
        assert at_kickoff.scored == 1

    async def test_an_earlier_recommendation_on_the_same_game_is_scored(self, conn):
        """The discriminating pair: same fixture, same line, different entry time."""
        _seed(conn, created_ms=TRUE_COMMENCE - 2 * HOUR_MS)
        assert (await run_scoring_pass(conn, FakeKalshi(), now=NOW)).scored == 1


class TestAStoreFailureLosesOneLineNotThePass:
    """The half of "one market's failure does not stop the others" that the
    `try` did not cover.

    The docstring on `run_scoring_pass` has always promised that a single
    market must not stop the other thirty. The `try` delivered it for the
    FETCH and left `store_closing_line` outside, so a `database is locked` on
    one write -- which happened four to five times a day (ADR 0091) -- escaped
    the function, killed the whole pass, and abandoned every market still in
    the loop.

    That is the expensive direction: a closing line not stored is not deferred,
    it is lost. Candlesticks age out and the game only closes once.

    **This is a different repair from ADR 0091 and neither replaces the other.**
    That one removed the biggest lock holder; this one makes the loop survive
    the next holder, whatever it turns out to be.
    """

    async def test_a_failing_store_does_not_abandon_the_remaining_markets(
        self, conn, monkeypatch
    ):
        """Mutation observed red: move `store_closing_line` back outside the
        `try`, and the pass raises instead of scoring the healthy market."""
        _seed(conn, ticker="KXMLBGAME-T-A")
        _seed(conn, ticker="KXMLBGAME-T-B")

        import backend.scoring as scoring

        real = scoring.store_closing_line
        seen: list[str] = []

        def flaky(conn_, line):
            seen.append(line.ticker)
            if line.ticker == "KXMLBGAME-T-A":
                raise sqlite3.OperationalError("database is locked")
            return real(conn_, line)

        monkeypatch.setattr(scoring, "store_closing_line", flaky)

        counts = await run_scoring_pass(conn, FakeKalshi(), now=NOW)

        assert "KXMLBGAME-T-B" in seen, (
            "the pass stopped at the failing market and never reached the "
            "healthy one -- which is the defect, not the symptom"
        )
        assert counts.scored == 1, "the healthy market must still be scored"

    async def test_a_lost_line_is_counted_as_lost_not_as_missing_candles(
        self, conn, monkeypatch
    ):
        """`lines_unstored` is its own counter for a reason.

        A 404 from candlesticks is history the venue no longer has. A failed
        store is history we HELD and dropped. Only the second is our fault and
        only the second is recoverable by fixing something, so folding it into
        `candles_missing` would make a lock storm read as a bad night for the
        candle endpoint.
        """
        _seed(conn, ticker="KXMLBGAME-T-A")

        import backend.scoring as scoring

        def always_locked(conn_, line):
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(scoring, "store_closing_line", always_locked)

        counts = await run_scoring_pass(conn, FakeKalshi(), now=NOW)

        assert counts.lines_unstored == 2       # both horizons
        assert counts.lines_stored == 0
        assert counts.candles_missing == 0, (
            "a store failure was counted as a missing candle; those have "
            "different causes and different fixes"
        )
        assert any("store failed" in e for e in counts.errors)

    async def test_the_connection_is_rolled_back_so_the_next_store_can_work(
        self, conn, monkeypatch
    ):
        """One failure must not become all of them.

        **The fake leaves a REAL open transaction, and that is the whole point
        of it.** The first version raised before touching SQL, so nothing was
        left mid-transaction, the rollback was never needed, and deleting the
        rollback left the test green -- a guard that guarded nothing. Recorded
        rather than quietly fixed: it is ADR 0087's failure again.

        The production shape it models: `store_closing_line` runs
        `conn.execute(INSERT ...)` and then `conn.commit()`. A lock can refuse
        the COMMIT rather than the execute, and that leaves the write
        transaction open -- so every subsequent store in the pass fails too,
        turning one lost line into the whole loop's worth by a different route.

        Mutation observed red: delete the `conn.rollback()` in `scoring.py`.
        """
        _seed(conn, ticker="KXMLBGAME-T-A")
        _seed(conn, ticker="KXMLBGAME-T-B")

        import backend.scoring as scoring

        real = scoring.store_closing_line
        calls = {"n": 0}

        def fail_first(conn_, line):
            calls["n"] += 1
            if calls["n"] == 1:
                # A real write, then a refusal -- so the connection is left
                # mid-transaction exactly as a lock on COMMIT would leave it.
                # A seeded ticker at an unused horizon: `closing_lines` has
                # a FOREIGN KEY on `ticker`, so an invented one raises
                # IntegrityError *before* opening a transaction -- which is
                # how the first version of this probe silently tested nothing.
                conn_.execute(
                    "INSERT INTO closing_lines (ticker, horizon_hours, "
                    "observed_ms, yes_bid_tenths, yes_ask_tenths) "
                    "VALUES ('KXMLBGAME-T-A', 99.0, 1, 1, 1)"
                )
                raise sqlite3.OperationalError("database is locked")
            return real(conn_, line)

        monkeypatch.setattr(scoring, "store_closing_line", fail_first)

        counts = await run_scoring_pass(conn, FakeKalshi(), now=NOW)

        assert counts.lines_unstored == 1
        assert counts.lines_stored >= 1, (
            "every store after the first failure also failed; the connection "
            "was not rolled back"
        )
        assert conn.execute(
            "SELECT COUNT(*) n FROM closing_lines WHERE horizon_hours = 99.0"
        ).fetchone()["n"] == 0, (
            "the half-written row survived; the rollback did not happen, so "
            "the failing store's transaction rode along with the next commit"
        )

    async def test_a_healthy_pass_reports_no_losses(self, conn):
        """The counter must stay quiet when nothing is wrong, or it is noise."""
        _seed(conn)
        counts = await run_scoring_pass(conn, FakeKalshi(), now=NOW)
        assert counts.lines_unstored == 0
        assert "lines_unstored" not in counts.as_dict(), (
            "a zero loss count should not be reported; `as_dict` omits falsy "
            "fields outside ALWAYS_REPORT and this is not one of them"
        )
