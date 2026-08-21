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
        """A position first seen AT the estimate instant did not follow it.

        Asserted on the match itself since Amendment 2: the row's terminal
        status now runs through the A11 absence ladder, but the boundary
        claim was always that this settlement must not MATCH."""
        est = _estimate(conn, at=NOW)
        _settlement(conn, first_seen=NOW, source="poll_instant")
        counts = match_estimates(conn, now_ms=NOW + 30 * HOUR)
        row = _row(conn, est)
        assert counts["matched"] == 0
        assert row["matched_position_id"] is None
        assert row["match_status"] != "matched"

    def test_the_later_of_two_competing_estimates_wins(self, conn):
        """Registered §7.3 conflict rule, chosen before any data existed."""
        earlier = _estimate(conn, at=NOW)
        later = _estimate(conn, at=NOW + HOUR)
        position = _settlement(conn, first_seen=NOW + 2 * HOUR,
                               source="poll_instant")
        match_estimates(conn, now_ms=NOW + 30 * HOUR)
        assert _row(conn, later)["matched_position_id"] == position
        assert _row(conn, earlier)["matched_position_id"] is None

    def test_a_closed_window_alone_no_longer_expires_anything(self, conn):
        """Amendment 2 (A10): this asserted `expired == 1` until 2026-08-20,
        pinning the stamp that wrote "he did not bet" on bets Joe made. A
        closed window with the market's result unknown now stays pending --
        the market may simply not have settled yet."""
        est = _estimate(conn)
        counts = match_estimates(conn, now_ms=NOW + 25 * HOUR)
        assert counts["expired"] == 0
        assert counts["pending"] == 1
        assert _row(conn, est)["match_status"] is None

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


def _market_result(conn, *, ticker=TICKER, result="yes"):
    conn.execute(
        "INSERT INTO kalshi_markets (ticker, result, first_seen_ms, "
        "last_seen_ms) VALUES (?, ?, 1, 1) "
        "ON CONFLICT(ticker) DO UPDATE SET result = excluded.result",
        (ticker, result),
    )
    conn.commit()


def _settlements_poll(conn, *, at):
    conn.execute(
        "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count) "
        "VALUES (?, 'settlements', 1, 0)",
        (at,),
    )
    conn.commit()


class TestAbsenceNeedsProof:
    """Amendment 2 (A11): 'he did not bet' takes three proofs, not a clock.

    Each guard below was verified red under a named mutation of
    `match_estimates` -- the mutation is stated on the test.
    """

    def test_result_known_moves_to_absence_pending_not_expired(self, conn):
        """Mutation: stamp `unmatched_no_position` directly when the result
        is known (skip the intermediate state). Red on the status assert."""
        est = _estimate(conn)
        _market_result(conn)
        counts = match_estimates(conn, now_ms=NOW + 25 * HOUR)
        row = _row(conn, est)
        assert counts["absence_pending"] == 1
        assert counts["expired"] == 0
        assert row["match_status"] == "absence_pending"
        assert row["match_status_ms"] == NOW + 25 * HOUR

    def test_a_poll_after_the_stamp_proves_absence(self, conn):
        est = _estimate(conn)
        _market_result(conn)
        match_estimates(conn, now_ms=NOW + 25 * HOUR)
        _settlements_poll(conn, at=NOW + 26 * HOUR)
        counts = match_estimates(conn, now_ms=NOW + 27 * HOUR)
        assert counts["expired"] == 1
        assert _row(conn, est)["match_status"] == "unmatched_no_position"

    def test_a_poll_before_the_stamp_proves_nothing(self, conn):
        """Mutation: drop the `polled_ms > match_status_ms` comparison and
        accept any successful settlements poll. Red here -- this poll
        pre-dates our sight of the result, so the sweep it describes cannot
        have carried the settlement row."""
        est = _estimate(conn)
        _settlements_poll(conn, at=NOW + 20 * HOUR)
        _market_result(conn)
        match_estimates(conn, now_ms=NOW + 25 * HOUR)
        counts = match_estimates(conn, now_ms=NOW + 27 * HOUR)
        assert counts["expired"] == 0
        assert _row(conn, est)["match_status"] == "absence_pending"

    def test_a_failed_poll_is_not_proof(self, conn):
        """Mutation: drop `ok = 1` from the poll predicate. Red here."""
        est = _estimate(conn)
        _market_result(conn)
        match_estimates(conn, now_ms=NOW + 25 * HOUR)
        conn.execute(
            "INSERT INTO poll_log (polled_ms, endpoint, ok, error) "
            "VALUES (?, 'settlements', 0, 'boom')",
            (NOW + 26 * HOUR,),
        )
        conn.commit()
        counts = match_estimates(conn, now_ms=NOW + 27 * HOUR)
        assert counts["expired"] == 0
        assert _row(conn, est)["match_status"] == "absence_pending"

    def test_absence_pending_is_still_matchable(self, conn):
        """The load-bearing half of the amendment: a settlement row arriving
        late for a position opened INSIDE the window still matches. Mutation:
        restore the old candidate filter (`match_status IS NULL OR ''`). Red
        here -- the row would be invisible to its own settlement."""
        est = _estimate(conn)
        _market_result(conn)
        match_estimates(conn, now_ms=NOW + 25 * HOUR)
        _settlement(conn, settled=NOW + 30 * HOUR, first_seen=NOW + 2 * HOUR,
                    source="fill")
        counts = match_estimates(conn, now_ms=NOW + 31 * HOUR)
        row = _row(conn, est)
        assert counts["matched"] == 1
        assert row["match_status"] == "matched"
        assert row["matched_position_id"] is not None


class TestRepairFalseAbsence:
    """A12: the rows the pre-amendment stamp falsified are re-bucketed once.

    A pre-amendment stamp is `unmatched_no_position` with `match_status_ms`
    NULL -- the column arrived with the amendment, so the pair is its own
    signature and the repair guard self-extinguishes.
    """

    @staticmethod
    def _false_stamp(conn, est_id):
        conn.execute(
            "UPDATE bet_estimates SET match_status = 'unmatched_no_position', "
            "match_status_ms = NULL WHERE id = ?",
            (est_id,),
        )
        conn.commit()

    def test_a_falsely_stamped_bet_is_recovered(self, conn):
        """The defect verbatim: Joe bet inside the window, the market settled
        after 24h, the old pass stamped 'he did not bet'. Repair matches it."""
        est = _estimate(conn)
        self._false_stamp(conn, est)
        _settlement(conn, settled=NOW + 40 * HOUR, first_seen=NOW + 3 * HOUR,
                    source="fill")
        from backend.estimate_match import repair_false_absence

        counts = repair_false_absence(conn, now_ms=NOW + 41 * HOUR)
        row = _row(conn, est)
        assert counts["reset"] == 1
        assert counts["matched"] == 1
        assert row["match_status"] == "matched"

    def test_a_stamped_row_with_no_bet_reenters_the_ladder(self, conn):
        """No settlement exists: the row goes back to pending/absence_pending
        rather than keeping a stamp it never earned."""
        est = _estimate(conn)
        self._false_stamp(conn, est)
        from backend.estimate_match import repair_false_absence

        counts = repair_false_absence(conn, now_ms=NOW + 41 * HOUR)
        assert counts["reset"] == 1
        assert _row(conn, est)["match_status"] is None  # result unknown

    def test_unexplained_hand_fills_are_reported_not_assumed_zero(self, conn):
        est = _estimate(conn)
        self._false_stamp(conn, est)
        _fill(conn, filled=NOW + 2 * HOUR)
        from backend.estimate_match import repair_false_absence

        counts = repair_false_absence(conn, now_ms=NOW + 41 * HOUR)
        assert counts["unexplained_hand_fills"] == 1


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


def _study_start(conn, at):
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value, updated_ms) "
        "VALUES ('calibration_study_start_ms', ?, 0)",
        (str(at),),
    )
    conn.commit()


class TestPositionSideCoverage:
    """Amendment 3 (A13/A14): the §7.5 denominator's rows, stamped where a
    position actually lives. Mutation observed red: point the UPDATE at
    match_status instead of estimate_match_status -- every test below fails
    on the column read."""

    @staticmethod
    def _status(conn, position_id):
        return conn.execute(
            "SELECT estimate_match_status FROM venue_settlements WHERE id = ?",
            (position_id,),
        ).fetchone()[0]

    def test_a_matched_position_is_stamped_matched(self, conn):
        from backend.estimate_match import classify_positions

        _study_start(conn, NOW - HOUR)
        est = _estimate(conn)
        _settlement(conn, first_seen=NOW + 2 * HOUR, source="fill")
        match_estimates(conn, now_ms=NOW + 3 * HOUR)
        counts = classify_positions(conn)
        assert counts["matched"] == 1
        row = conn.execute(
            "SELECT matched_position_id FROM bet_estimates WHERE id = ?",
            (est,),
        ).fetchone()
        assert self._status(conn, row["matched_position_id"]) == "matched"

    def test_an_unmatched_in_window_sports_position_is_the_unlogged_half(
        self, conn
    ):
        from backend.estimate_match import classify_positions

        _study_start(conn, NOW - HOUR)
        pos = _settlement(conn, first_seen=NOW + 2 * HOUR, source="fill")
        counts = classify_positions(conn)
        assert counts["position_unlogged"] == 1
        assert self._status(conn, pos) == "position_unlogged"

    def test_a_post_stop_position_is_out_of_scope_not_unlogged(self, conn):
        """Amendment 2 ended accrual at the owner stop instant; a position
        first seen at or after it is not an unlogged bet. The window is
        half-open on the right -- 1ms before the stop is still in -- so
        mutating `<` to `<=` (or dropping the bound) turns this red."""
        from backend.estimate_match import classify_positions
        from backend.estimates import STUDY_STOPPED_BY_OWNER_MS

        _study_start(conn, NOW - HOUR)
        at_stop = _settlement(
            conn, first_seen=STUDY_STOPPED_BY_OWNER_MS, source="fill"
        )
        just_before = _settlement(
            conn,
            ticker="KXUFCFIGHT-26AUG30-OTHER",
            first_seen=STUDY_STOPPED_BY_OWNER_MS - 1,
            source="fill",
        )
        counts = classify_positions(conn)
        assert self._status(conn, at_stop) == "out_of_scope"
        assert self._status(conn, just_before) == "position_unlogged"
        assert counts["out_of_scope"] == 1
        assert counts["position_unlogged"] == 1

    def test_a_pre_study_position_is_out_of_scope_not_unlogged(self, conn):
        """The account's history goes back to 2025-11; §7.5's denominator
        must not be diluted by it."""
        from backend.estimate_match import classify_positions

        _study_start(conn, NOW + 10 * HOUR)
        pos = _settlement(conn, first_seen=NOW + 2 * HOUR, source="fill")
        classify_positions(conn)
        assert self._status(conn, pos) == "out_of_scope"

    def test_a_non_sports_position_is_out_of_scope(self, conn):
        from backend.estimate_match import classify_positions
        from backend.estimates import classify_ticker

        assert classify_ticker("KXTRUMPSAY-26AUG20-X")[0] == 0
        _study_start(conn, NOW - HOUR)
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, first_seen_ms, last_seen_ms) "
            "VALUES ('KXTRUMPSAY-26AUG20-X', 1, 1)"
        )
        pos = _settlement(
            conn, ticker="KXTRUMPSAY-26AUG20-X",
            first_seen=NOW + 2 * HOUR, source="fill",
        )
        classify_positions(conn)
        assert self._status(conn, pos) == "out_of_scope"

    def test_no_study_start_means_out_of_scope_never_unlogged(self, conn):
        """No study window exists, so nothing can be inside it. `NULL start`
        must not read as `always in window` -- that would stamp the account's
        whole pre-study history into the denominator."""
        from backend.estimate_match import classify_positions

        pos = _settlement(conn, first_seen=NOW + 2 * HOUR, source="fill")
        classify_positions(conn)
        assert self._status(conn, pos) == "out_of_scope"

    def test_a_late_match_moves_unlogged_to_matched(self, conn):
        """A11's late-arriving settlement, seen from the position's side:
        re-stamping is why the column is not write-once."""
        from backend.estimate_match import classify_positions

        _study_start(conn, NOW - HOUR)
        pos = _settlement(conn, first_seen=NOW + 2 * HOUR, source="fill")
        classify_positions(conn)
        assert self._status(conn, pos) == "position_unlogged"
        _estimate(conn)
        match_estimates(conn, now_ms=NOW + 3 * HOUR)
        classify_positions(conn)
        assert self._status(conn, pos) == "matched"

    def test_it_computes_no_rate(self, conn):
        """A15: the stamps are bookkeeping; coverage itself stays embargoed
        until the registered stop. The function returns counts and nothing
        with a division in it."""
        from backend.estimate_match import classify_positions

        _study_start(conn, NOW - HOUR)
        _settlement(conn, first_seen=NOW + 2 * HOUR, source="fill")
        counts = classify_positions(conn)
        assert set(counts) == {"matched", "position_unlogged", "out_of_scope"}
        assert all(isinstance(v, int) for v in counts.values())
