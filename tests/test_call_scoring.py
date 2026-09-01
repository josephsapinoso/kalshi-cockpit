"""Scoring Joe's own calls against Kalshi's close -- ticket #11, decision 6.

The claims tested here:

- A decoupled call (`is_study_row = 0`) is scored into the four `call_*`
  columns, at the primary horizon, with the horizon written beside the score.
- **The registered secondary arm is never written.** `clv_tenths`,
  `closing_line_id`, `clv_horizon_hours` and `clv_scored_ms` measure a
  position-bearing quantity this path cannot compute, and they stay NULL.
- A **study row is never scored**, which is the code half of ADR 0044
  Amendment 3.
- The two refusals `score_recommendations` already makes are made here: the
  call must precede the close it is scored against, and a missing bid or ask
  is counted, never substituted.
- The read is **singular**. One call, or None.

What these tests do not establish, and it is the whole point of saying so:
**nothing about whether Joe is right.** The score compares a stated probability
to Kalshi's closing mid, never to an outcome. One outcome cannot grade a
probability -- a good 58% call loses 42% of the time -- and without settlements
"Joe has an edge" and "Joe is noisy" are not separable (ADR 0037: the in-house
model's own error, 4.04 points, exceeded its entire disagreement with Kalshi,
3.72). Every test below is about plumbing and refusals; none of them is
evidence about the forecaster.
"""

from __future__ import annotations

import httpx
import pytest

from backend.analysis.clv import (
    DEFAULT_HORIZON_HOURS,
    call_clv_tenths,
    score_bet_estimate_calls,
)
from backend.api.routes import create_app
from backend.config import AppConfig
from backend.estimates import last_scored_call, record_estimate
from backend.store import db

NOW = 1_755_500_000_000
TICKER = "KXMLBGAME-26AUG20HOUSEA-HOU"
EVENT = "KXMLBGAME-26AUG20HOUSEA"


@pytest.fixture
def conn(tmp_path):
    handle = db.init_db(tmp_path / "calls.db")
    _seed_market(handle)
    yield handle
    handle.close()


def _seed_market(conn, ticker=TICKER):
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events "
        "(event_ticker, title, commence_ms, first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, ?, ?, ?)",
        (EVENT, "Houston at Seattle", NOW + 3_600_000, NOW, NOW),
    )
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets "
        "(ticker, event_ticker, title, status, close_ms, first_seen_ms, "
        " last_seen_ms) VALUES (?, ?, ?, 'active', ?, ?, ?)",
        (ticker, EVENT, "Houston at Seattle", NOW + 100_000_000, NOW, NOW),
    )
    conn.commit()


def _seed_close(
    conn,
    *,
    ticker=TICKER,
    horizon=DEFAULT_HORIZON_HOURS,
    observed_ms=NOW + 1000,
    yes_bid=600,
    yes_ask=620,
):
    conn.execute(
        "INSERT INTO closing_lines (ticker, horizon_hours, observed_ms, "
        "yes_bid_tenths, yes_ask_tenths) VALUES (?, ?, ?, ?, ?)",
        (ticker, horizon, observed_ms, yes_bid, yes_ask),
    )
    conn.commit()


def _call(conn, *, bp=5800, at=NOW, ticker=TICKER):
    return record_estimate(
        conn,
        ticker=ticker,
        stated_probability_bp=bp,
        estimate_server_ms=at,
    )


def _row(conn, row_id):
    return conn.execute(
        "SELECT * FROM bet_estimates WHERE id = ?", (row_id,)
    ).fetchone()


class TestTheUnitIdentity:
    """A contract pays $1, so a price in tenths of a cent IS a probability in
    tenths of a percent. 5800 bp = 58.00% = 580 tenths.

    Written as its own test because the identity is the entire licence for
    subtracting a basis-point field from a tenths-of-a-cent field, and a future
    reader who does not believe it will otherwise re-derive it or "fix" it.
    """

    def test_the_stated_probability_maps_one_to_one_onto_tenths(self):
        # He said 58%; the market closed at 61.0c mid. -30 tenths of a percent.
        assert call_clv_tenths(5800, 610.0) == pytest.approx(-30.0)

    def test_positive_means_he_said_higher_than_the_close(self):
        assert call_clv_tenths(6500, 610.0) == pytest.approx(40.0)

    def test_agreeing_with_the_close_exactly_is_zero_not_missing(self):
        """0.0 is a measurement. Nothing downstream may test it for
        truthiness -- the same trap `DEFAULT_HORIZON_HOURS = 0.0` sets."""
        assert call_clv_tenths(6100, 610.0) == 0.0


class TestScoringADecoupledCall:
    def test_it_writes_the_score_and_the_horizon_together(self, conn):
        """Mutation observed red: drop `call_clv_horizon_hours` from the
        UPDATE. Without it the column is a silent mixture of the 0.0h anchor
        and the 1.0h control, which is the failure `clv_horizon_hours` was
        added one table over to prevent."""
        _seed_close(conn)
        row_id = _call(conn, bp=5800)

        counts = score_bet_estimate_calls(conn, scored_ms=NOW + 5000)

        assert counts["scored"] == 1
        row = _row(conn, row_id)
        assert row["call_clv_tenths"] == pytest.approx(-30.0)
        assert row["call_clv_horizon_hours"] == DEFAULT_HORIZON_HOURS
        assert row["call_clv_scored_ms"] == NOW + 5000
        assert row["call_closing_line_id"] is not None

    def test_a_scored_call_is_not_scored_twice(self, conn):
        _seed_close(conn)
        _call(conn)
        assert score_bet_estimate_calls(conn)["scored"] == 1
        again = score_bet_estimate_calls(conn)
        assert again["scored"] == 0
        assert again["rows_joined"] == 0

    def test_only_the_asked_horizon_is_scored(self, conn):
        """The control horizon's line exists and must not be the one used --
        pooling the two is how a convergence result gets read as edge."""
        _seed_close(conn, horizon=1.0, yes_bid=400, yes_ask=420)
        _call(conn, bp=5800)
        assert score_bet_estimate_calls(conn)["rows_joined"] == 0

    def test_a_call_on_a_market_with_no_close_is_simply_unscored(self, conn):
        """Not an error and not a zero: the game has not closed yet, or the
        market is outside the slate's coverage (decision 11's ~4% tail)."""
        row_id = _call(conn)
        counts = score_bet_estimate_calls(conn)
        assert counts == {
            "scored": 0,
            "skipped_no_mid": 0,
            "skipped_entry_after_close": 0,
            "rows_joined": 0,
        }
        assert _row(conn, row_id)["call_clv_scored_ms"] is None


class TestTheTwoRefusals:
    """Both inherited verbatim from `score_recommendations`, both counted."""

    def test_a_call_typed_after_the_close_is_refused_not_scored(self, conn):
        """Mutation observed red: delete the `estimate_server_ms >
        closing_observed_ms` branch.

        Otherwise whichever way the market drifted between the close and the
        call lands directly in the number, and whether that flatters or
        punishes him is pure chance.
        """
        _seed_close(conn, observed_ms=NOW - 1)
        row_id = _call(conn, at=NOW)

        counts = score_bet_estimate_calls(conn)

        assert counts["skipped_entry_after_close"] == 1
        assert counts["scored"] == 0
        assert _row(conn, row_id)["call_clv_tenths"] is None

    def test_a_call_exactly_at_the_close_is_scored(self, conn):
        """The boundary is `>`, not `>=`: a call typed in the same millisecond
        as the observation did precede it in the only sense that matters."""
        _seed_close(conn, observed_ms=NOW)
        _call(conn, at=NOW)
        assert score_bet_estimate_calls(conn)["scored"] == 1

    def test_an_unreadable_side_is_counted_never_substituted(self, conn):
        """Mutation observed red: fall back to the readable side, or to 0.

        A settled loser genuinely trades at 0, so a zero standing in for
        "unreadable" is indistinguishable from real data -- and here it would
        render as "Kalshi closed 0%", the most flattering possible verdict on
        any call he made.
        """
        _seed_close(conn, yes_bid=None)
        row_id = _call(conn)

        counts = score_bet_estimate_calls(conn)

        assert counts["skipped_no_mid"] == 1
        assert counts["scored"] == 0
        assert _row(conn, row_id)["call_clv_tenths"] is None

    def test_joined_but_skipped_is_distinguishable_from_never_joined(self, conn):
        """`scored: 0` alone cannot tell the two apart and they need different
        fixes -- the reason `rows_joined` exists on the recommendation arm."""
        _seed_close(conn, yes_ask=None)
        _call(conn)
        counts = score_bet_estimate_calls(conn)
        assert counts["rows_joined"] == 1 and counts["scored"] == 0


class TestTheStudysOwnRowsAreNeverScored:
    """ADR 0044 Amendment 3, in code rather than in prose.

    The embargo binds the study's own rows. The one row collected under the
    promise that its score would never be shown to Joe is never *given* a
    score, so there is nothing to show and nothing to leak.
    """

    def test_a_study_row_is_not_scored(self, conn):
        """Mutation observed red: remove `AND e.is_study_row = 0` from the
        scorer's WHERE clause."""
        _seed_close(conn)
        row_id = _call(conn)
        conn.execute(
            "UPDATE bet_estimates SET is_study_row = 1 WHERE id = ?", (row_id,)
        )
        conn.commit()

        counts = score_bet_estimate_calls(conn)

        assert counts["rows_joined"] == 0
        assert _row(conn, row_id)["call_clv_scored_ms"] is None

    def test_a_study_row_is_not_served_by_the_read(self, conn):
        """Belt and braces, and deliberately so: the row is unscoreable AND
        unreadable. Either guard alone would be one edit from a leak."""
        _seed_close(conn)
        row_id = _call(conn)
        score_bet_estimate_calls(conn)
        conn.execute(
            "UPDATE bet_estimates SET is_study_row = 1 WHERE id = ?", (row_id,)
        )
        conn.commit()
        assert last_scored_call(conn) is None


class TestTheRegisteredArmIsNotReused:
    """The four registered columns measure a different quantity and stay NULL.

    Registration 2026-08-17 §3, "Secondary: mean CLV":
    `clv_tenths(entry_ask_tenths, close_mid, side)`, where `entry_ask_tenths`
    is "the venue's own average entry price" and `side` comes from the venue.
    **That requires a position.** Decision 6's verdict is position-free, so
    writing one into the other would make the column a silent mixture of two
    regimes -- exactly what `clv_horizon_hours` was added to prevent.
    """

    def test_scoring_a_call_leaves_the_registered_four_null(self, conn):
        """Mutation observed red: name `clv_tenths` in the scorer's UPDATE."""
        _seed_close(conn)
        row_id = _call(conn)
        score_bet_estimate_calls(conn)

        row = _row(conn, row_id)
        assert row["call_clv_tenths"] is not None
        for registered in (
            "clv_tenths",
            "closing_line_id",
            "clv_horizon_hours",
            "clv_scored_ms",
        ):
            assert row[registered] is None, (
                f"{registered} belongs to the registered position-bearing arm "
                f"and was written by the position-free one"
            )


class TestTheReadIsSingular:
    """Decision 8: one call at a time until 30 scored. A list is a scoreboard
    with extra steps, and eye-aggregation is still aggregation."""

    def test_nothing_scored_reads_as_none_not_as_a_zero(self, conn):
        assert last_scored_call(conn) is None

    def test_it_returns_the_most_recently_scored_call(self, conn):
        _seed_close(conn)
        _call(conn, bp=5800)
        score_bet_estimate_calls(conn, scored_ms=NOW + 1000)

        _seed_market(conn, ticker="KXMLBGAME-26AUG20HOUSEA-SEA")
        _seed_close(conn, ticker="KXMLBGAME-26AUG20HOUSEA-SEA", yes_bid=300,
                    yes_ask=320)
        _call(conn, bp=4000, ticker="KXMLBGAME-26AUG20HOUSEA-SEA")
        score_bet_estimate_calls(conn, scored_ms=NOW + 2000)

        call = last_scored_call(conn)
        assert call["stated_probability_bp"] == 4000
        assert call["call_clv_scored_ms"] == NOW + 2000

    def test_the_closing_mid_is_recovered_by_arithmetic_not_re_read(self, conn):
        """`store_closing_line` upserts, so the row can move after the score
        was taken. `stated / 10 - clv` is exact and cannot drift.

        Mutation observed red: read the mid back from `closing_lines`, then
        move the line -- the verdict starts quoting a mid it was not computed
        from.
        """
        _seed_close(conn, yes_bid=600, yes_ask=620)
        _call(conn, bp=5800)
        score_bet_estimate_calls(conn)

        conn.execute(
            "UPDATE closing_lines SET yes_bid_tenths = 100, "
            "yes_ask_tenths = 120 WHERE ticker = ?",
            (TICKER,),
        )
        conn.commit()

        call = last_scored_call(conn)
        assert call["closing_mid_tenths"] == pytest.approx(610.0)
        assert call["call_clv_tenths"] == pytest.approx(-30.0)

    def test_the_reader_computes_no_aggregate(self, conn):
        """Decision 8 as a property of the source, not of one payload.

        No average, win rate, hit rate, streak or fitted trend over Joe's own
        calls, anywhere, until n >= 30 with the per-group view alongside. The
        cheapest way to break that rule is a helper that quietly grows a
        `COUNT(*)` beside the row, so the source is asserted rather than the
        output.
        """
        import inspect

        source = inspect.getsource(last_scored_call).lower()
        body = source.split('"""')[2] if source.count('"""') >= 2 else source
        for banned in ("avg(", "count(", "sum(", "mean", "streak", "limit ?"):
            assert banned not in body, (
                f"{banned!r} appeared in the singular read's body"
            )
        assert "limit 1" in body


AUTH = {"Authorization": "Bearer t"}


async def _request(app, method, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.request(method, path, **kwargs)


class TestTheRouteServesOneCallOrNull:
    @pytest.fixture
    def db_path(self, tmp_path):
        path = tmp_path / "api.db"
        handle = db.init_db(path)
        _seed_market(handle)
        yield path
        handle.close()

    async def test_nothing_scored_serves_null(self, db_path):
        app = create_app(
            AppConfig(instance_mode="live", auth_token="t", db_path=db_path)
        )
        response = await _request(app, "GET", "/api/estimates/last-scored")
        assert response.status_code == 200
        assert response.json() == {"call": None}

    async def test_a_scored_call_is_served_with_its_regime_declared(
        self, db_path
    ):
        """The payload says `is_study_row: 0` out loud.

        That is not decoration: the embargo walker keys on it, so a payload
        may only show a score if it states which regime the row belongs to.
        A score with no declaration fails the walker.
        """
        handle = db.open_db(db_path)
        try:
            _seed_close(handle)
            _call(handle, bp=5800)
            score_bet_estimate_calls(handle, scored_ms=NOW + 5000)
        finally:
            handle.close()

        app = create_app(
            AppConfig(instance_mode="live", auth_token="t", db_path=db_path)
        )
        payload = (
            await _request(app, "GET", "/api/estimates/last-scored")
        ).json()

        call = payload["call"]
        assert call["is_study_row"] == 0
        assert call["stated_probability_bp"] == 5800
        assert call["call_clv_tenths"] == pytest.approx(-30.0)
        assert call["closing_mid_tenths"] == pytest.approx(610.0)

        from tests.test_estimates import _assert_embargo_holds

        _assert_embargo_holds(payload)

    async def test_the_payload_carries_no_list(self, db_path):
        """Decision 8, at the wire. There is no `limit` to raise and no array
        to grow into a scoreboard."""
        handle = db.open_db(db_path)
        try:
            _seed_close(handle)
            _call(handle)
            score_bet_estimate_calls(handle)
        finally:
            handle.close()

        app = create_app(
            AppConfig(instance_mode="live", auth_token="t", db_path=db_path)
        )
        payload = (
            await _request(app, "GET", "/api/estimates/last-scored")
        ).json()
        assert set(payload) == {"call"}
        assert not any(isinstance(v, list) for v in payload["call"].values())

    async def test_recent_still_serves_no_score(self, db_path):
        """The list route stays score-free, which is what keeps decision 8
        true: a list of scores is the aggregate it forbids, computed by eye."""
        handle = db.open_db(db_path)
        try:
            _seed_close(handle)
            _call(handle)
            score_bet_estimate_calls(handle)
        finally:
            handle.close()

        app = create_app(
            AppConfig(instance_mode="live", auth_token="t", db_path=db_path)
        )
        payload = (await _request(app, "GET", "/api/estimates/recent")).json()

        from tests.test_estimates import SAFE_KEYS, _assert_embargo_holds

        _assert_embargo_holds(payload)
        assert set(payload["estimates"][0]) == SAFE_KEYS
