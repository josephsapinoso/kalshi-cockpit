"""The calibration bet log's write path, and the guards the registration names.

Registration: `docs/measurements/2026-08-17-preregistration-joe-calibration-
bet-log.md` (as amended). The claims tested here:

- `stated_probability_bp` is write-once and the record append-only, enforced
  by the DATABASE (§7.4) -- verified by attempting the forbidden statements,
  and the guard itself was verified by dropping the triggers and watching
  these tests fail.
- The estimate-time quote is captured server-side and NEVER serialised into
  any response a phone could render (§7.7, the embargo).
- Nothing here writes to `recommendations` (the ADR 0021/0034 population).

What these tests do not establish: anything about the analysis. The one-look
rule, the matcher and the tripwires are not built here.
"""

from __future__ import annotations

import sqlite3

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import AppConfig
from backend.estimates import (
    STUDY_LOSS_CEILING_DOLLARS,
    classify_ticker,
    record_estimate,
    recent_estimates,
    revise_estimate,
    search_markets,
    study_loss_dollars,
    study_stop_fired,
)
from backend.portfolio_poll import STUDY_START_MS_KEY
from backend.kalshi.discovery import DiscoveredMarket
from backend.kalshi.quotes import LiveQuote, QuoteUnavailable
from backend.store import db

NOW = 1_755_500_000_000
TICKER = "KXMLBGAME-26AUG20HOUSEA-HOU"


@pytest.fixture
def conn(tmp_path):
    handle = db.init_db(tmp_path / "estimates.db")
    yield handle
    handle.close()


def _seed_market(
    conn,
    ticker=TICKER,
    event_ticker="KXMLBGAME-26AUG20HOUSEA",
    commence_ms=NOW + 3_600_000,
    title="Houston at Seattle",
):
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events "
        "(event_ticker, title, commence_ms, first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, ?, ?, ?)",
        (event_ticker, title, commence_ms, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO kalshi_markets "
        "(ticker, event_ticker, title, status, close_ms, first_seen_ms, "
        " last_seen_ms) VALUES (?, ?, ?, 'active', ?, ?, ?)",
        # Far future in real-clock terms too: the search route compares
        # against `db.now_ms()`, not this file's fixed NOW.
        (ticker, event_ticker, title, NOW + 100_000_000_000, NOW, NOW),
    )
    conn.commit()


def _estimate(conn, **kwargs):
    args = dict(
        ticker=TICKER,
        stated_probability_bp=6250,
        estimate_server_ms=NOW,
    )
    args.update(kwargs)
    return record_estimate(conn, **args)


class TestTheProbabilityIsWriteOnce:
    """§7.4, enforced below every caller.

    Guard verification: with `trg_bet_estimates_write_once` and
    `trg_bet_estimates_no_delete` removed from `schema.sql`, every test in
    this class fails. Recorded 2026-08-18.
    """

    def test_an_update_is_rejected_by_the_database(self, conn):
        row_id = _estimate(conn)
        with pytest.raises(sqlite3.DatabaseError, match="write-once"):
            conn.execute(
                "UPDATE bet_estimates SET stated_probability_bp = 7000 "
                "WHERE id = ?",
                (row_id,),
            )

    def test_rewriting_the_same_value_is_also_rejected(self, conn):
        """A statement that names the column at all is outside the protocol.

        'It happened to be a no-op' is not an audit trail, so the trigger has
        no value comparison to slip through.
        """
        row_id = _estimate(conn, stated_probability_bp=6250)
        with pytest.raises(sqlite3.DatabaseError, match="write-once"):
            conn.execute(
                "UPDATE bet_estimates SET stated_probability_bp = 6250 "
                "WHERE id = ?",
                (row_id,),
            )

    def test_delete_is_rejected_because_it_is_the_trivial_bypass(self, conn):
        row_id = _estimate(conn)
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("DELETE FROM bet_estimates WHERE id = ?", (row_id,))

    def test_other_columns_stay_updatable(self, conn):
        """The matcher and the outcome backfill must still be able to write."""
        row_id = _estimate(conn)
        conn.execute(
            "UPDATE bet_estimates SET match_status = 'unmatched_no_position' "
            "WHERE id = ?",
            (row_id,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT match_status FROM bet_estimates WHERE id = ?", (row_id,)
        ).fetchone()
        assert row["match_status"] == "unmatched_no_position"


class TestTheRevisionPath:
    def test_revising_flags_the_row_and_records_the_reason(self, conn):
        row_id = _estimate(conn)
        assert revise_estimate(
            conn, row_id, reason="fat-fingered 62.50 as 26.50", revised_ms=NOW + 1
        )
        row = conn.execute(
            "SELECT stated_probability_is_revised FROM bet_estimates "
            "WHERE id = ?",
            (row_id,),
        ).fetchone()
        assert row["stated_probability_is_revised"] == 1
        revision = conn.execute(
            "SELECT reason, revised_ms FROM bet_estimate_revisions "
            "WHERE estimate_id = ?",
            (row_id,),
        ).fetchone()
        assert revision["reason"] == "fat-fingered 62.50 as 26.50"
        assert revision["revised_ms"] == NOW + 1

    def test_a_missing_row_returns_false_rather_than_inventing_one(self, conn):
        assert not revise_estimate(conn, 999, reason="typo", revised_ms=NOW)

    def test_a_reason_is_mandatory(self, conn):
        row_id = _estimate(conn)
        with pytest.raises(ValueError):
            revise_estimate(conn, row_id, reason="   ", revised_ms=NOW)


class TestClassification:
    """String-only on purpose: a hand bet can be on an undiscovered market."""

    def test_a_baseball_game_is_sports(self):
        assert classify_ticker("KXMLBGAME-26AUG20HOUSEA-HOU") == (1, "mlb", 0)

    def test_tennis_doubles_is_tennis(self):
        """The A1 coverage gap made concrete: discovery never saw this series."""
        assert classify_ticker("KXATPDOUBLES-26AUG20-XYZ") == (1, "tennis", 0)

    def test_a_combo_is_multi_leg_and_excluded_from_sports(self):
        assert classify_ticker("KXMVESPORTS-ABC-DEF") == (0, None, 1)

    def test_an_unknown_series_is_not_sports_rather_than_a_guess(self):
        assert classify_ticker("KXBTC-26AUG20-40") == (0, None, 0)

    def test_ncaab_is_not_swallowed_by_the_nba_prefix(self):
        assert classify_ticker("KXNCAABGAME-26MAR20DUKUNC-DUK")[1] == "ncaab"


class TestDerivations:
    def test_cluster_key_is_the_event_when_discovered(self, conn):
        _seed_market(conn)
        row_id = _estimate(conn)
        row = conn.execute(
            "SELECT cluster_key, is_in_play FROM bet_estimates WHERE id = ?",
            (row_id,),
        ).fetchone()
        assert row["cluster_key"] == "KXMLBGAME-26AUG20HOUSEA"
        assert row["is_in_play"] == 0

    def test_cluster_key_falls_back_to_the_ticker_when_not(self, conn):
        row_id = _estimate(conn, ticker="KXUFC-26AUG30-JONASP")
        row = conn.execute(
            "SELECT cluster_key, sport, is_sports FROM bet_estimates "
            "WHERE id = ?",
            (row_id,),
        ).fetchone()
        assert row["cluster_key"] == "KXUFC-26AUG30-JONASP"
        assert (row["is_sports"], row["sport"]) == (1, "mma")

    def test_an_estimate_after_commence_is_in_play(self, conn):
        _seed_market(conn, commence_ms=NOW - 1)
        row_id = _estimate(conn)
        row = conn.execute(
            "SELECT is_in_play FROM bet_estimates WHERE id = ?", (row_id,)
        ).fetchone()
        assert row["is_in_play"] == 1

    def test_the_bounds_mirror_the_schema_check(self, conn):
        with pytest.raises(ValueError):
            _estimate(conn, stated_probability_bp=0)
        with pytest.raises(ValueError):
            _estimate(conn, stated_probability_bp=10_000)

    def test_nothing_is_written_to_recommendations(self, conn):
        """The ADR 0021/0034 population must not gain a row from this path."""
        _seed_market(conn)
        _estimate(conn)
        count = conn.execute("SELECT COUNT(*) AS n FROM recommendations").fetchone()
        assert count["n"] == 0


# ---------------------------------------------------------------------------
# The routes
# ---------------------------------------------------------------------------

# The registration's embargo, as a set: every payload the form can receive is
# checked against it. `server_` catches the whole captured-quote family.
EMBARGOED_FRAGMENTS = ("bid", "ask", "quote", "server_yes", "outcome", "clv")

SAFE_KEYS = {
    "id",
    "ticker",
    "stated_probability_bp",
    "estimate_server_ms",
    "had_already_opened_kalshi",
    "stated_probability_is_revised",
}


def _assert_embargo_holds(payload):
    def walk(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                for fragment in EMBARGOED_FRAGMENTS:
                    assert fragment not in key.lower(), (
                        f"embargoed key {key!r} reached a renderable payload"
                    )
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(payload)


class _StubQuotes:
    """Injectable `LiveQuoteSource`: one canned book, or one canned failure."""

    def __init__(self, error=None, yes_bid=610, no_bid=350):
        self._error = error
        self._yes_bid = yes_bid
        self._no_bid = no_bid
        self.calls: list[str] = []

    async def fetch(self, ticker: str, *, observed_ms: int) -> LiveQuote:
        self.calls.append(ticker)
        if self._error is not None:
            raise self._error
        market = DiscoveredMarket(
            ticker=ticker,
            event_ticker="KXMLBGAME-26AUG20HOUSEA",
            series_ticker="KXMLBGAME",
            market_type="moneyline",
            title="Houston at Seattle",
            yes_side=None,
            strike=None,
            close_ms=None,
            status="active",
            volume_24h=0.0,
            open_interest=0.0,
            price_structure=None,
            yes_bid_tenths=self._yes_bid,
            no_bid_tenths=self._no_bid,
        )
        return LiveQuote(market=market, observed_ms=observed_ms)

    async def aclose(self) -> None:
        pass


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "api.db"
    handle = db.init_db(path)
    _seed_market(handle)
    handle.close()
    return path


def _app(db_path, quotes=None, *, mode="live"):
    config = (
        AppConfig(instance_mode="demo", db_path=db_path)
        if mode == "demo"
        else AppConfig(instance_mode="live", auth_token="t", db_path=db_path)
    )
    return create_app(config, quote_source=quotes or _StubQuotes())


AUTH = {"Authorization": "Bearer t"}


async def _request(app, method, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.request(method, path, **kwargs)


def _body(ticker=TICKER, bp=6250, opened=0):
    return {
        "ticker": ticker,
        "stated_probability_bp": bp,
        "had_already_opened_kalshi": opened,
    }


class TestLoggingAnEstimate:
    async def test_it_writes_the_row_and_captures_the_quote(self, db_path):
        app = _app(db_path)
        response = await _request(
            app, "POST", "/api/estimates", json=_body(), headers=AUTH
        )
        assert response.status_code == 200
        conn = db.open_db(db_path, read_only=True)
        try:
            row = conn.execute("SELECT * FROM bet_estimates").fetchone()
        finally:
            conn.close()
        assert row["ticker"] == TICKER
        assert row["stated_probability_bp"] == 6250
        assert row["had_already_opened_kalshi"] == 0
        assert row["server_yes_bid_tenths"] == 610
        # The derived ask: 1000 - the resting NO bid.
        assert row["server_yes_ask_tenths"] == 650
        assert row["server_quote_observed_ms"] is not None
        assert row["server_quote_unreadable_reason"] is None

    async def test_the_response_never_carries_the_quote(self, db_path):
        """§7.7: rendering the captured book would hand the anchoring
        reference to the person being measured."""
        app = _app(db_path)
        response = await _request(
            app, "POST", "/api/estimates", json=_body(), headers=AUTH
        )
        payload = response.json()
        _assert_embargo_holds(payload)
        assert set(payload) <= SAFE_KEYS

    async def test_an_unreadable_quote_is_a_reason_not_a_refusal(self, db_path):
        """A transient failure must not cost the row: the estimate is the
        measurement, the quote is a diagnostic."""
        quotes = _StubQuotes(error=QuoteUnavailable("kalshi timed out"))
        app = _app(db_path, quotes)
        response = await _request(
            app, "POST", "/api/estimates", json=_body(), headers=AUTH
        )
        assert response.status_code == 200
        conn = db.open_db(db_path, read_only=True)
        try:
            row = conn.execute("SELECT * FROM bet_estimates").fetchone()
        finally:
            conn.close()
        assert row["server_yes_bid_tenths"] is None
        assert "timed out" in row["server_quote_unreadable_reason"]

    async def test_a_ticker_nobody_has_heard_of_is_refused(self, db_path):
        """Permanent 404 from Kalshi AND absent from discovery: a typo, and
        an unjoinable row is worse than a retype."""
        quotes = _StubQuotes(
            error=QuoteUnavailable("no such market", permanent=True)
        )
        app = _app(db_path, quotes)
        response = await _request(
            app,
            "POST",
            "/api/estimates",
            json=_body(ticker="KXMLBGAME-TYPO"),
            headers=AUTH,
        )
        assert response.status_code == 422
        conn = db.open_db(db_path, read_only=True)
        try:
            n = conn.execute("SELECT COUNT(*) AS n FROM bet_estimates").fetchone()
        finally:
            conn.close()
        assert n["n"] == 0

    async def test_a_discovered_ticker_survives_a_permanent_quote_failure(
        self, db_path
    ):
        """Discovery has seen it, so the string is real even if the quote
        endpoint refuses today -- record, with the reason."""
        quotes = _StubQuotes(
            error=QuoteUnavailable("market closed", permanent=True)
        )
        app = _app(db_path, quotes)
        response = await _request(
            app, "POST", "/api/estimates", json=_body(), headers=AUTH
        )
        assert response.status_code == 200

    async def test_the_bounds_are_refused_with_a_422(self, db_path):
        app = _app(db_path)
        for bad in (0, 10_000):
            response = await _request(
                app, "POST", "/api/estimates", json=_body(bp=bad), headers=AUTH
            )
            assert response.status_code == 422

    async def test_it_requires_auth(self, db_path):
        response = await _request(_app(db_path), "POST", "/api/estimates", json=_body())
        assert response.status_code == 401

    async def test_the_demo_instance_refuses(self, db_path):
        response = await _request(
            _app(db_path, mode="demo"), "POST", "/api/estimates", json=_body()
        )
        assert response.status_code == 403


class TestTheReadRoutes:
    async def test_recent_serves_only_the_safe_columns(self, db_path):
        conn = db.open_db(db_path)
        try:
            record_estimate(
                conn,
                ticker=TICKER,
                stated_probability_bp=6250,
                estimate_server_ms=NOW,
                server_yes_bid_tenths=610,
                server_yes_ask_tenths=650,
                server_quote_observed_ms=NOW,
            )
        finally:
            conn.close()
        response = await _request(_app(db_path), "GET", "/api/estimates/recent")
        payload = response.json()
        _assert_embargo_holds(payload)
        assert len(payload["estimates"]) == 1
        assert set(payload["estimates"][0]) == SAFE_KEYS

    async def test_market_search_finds_by_title_and_serves_no_price(self, db_path):
        response = await _request(
            _app(db_path), "GET", "/api/estimates/markets", params={"q": "Seattle"}
        )
        payload = response.json()
        assert [m["ticker"] for m in payload["markets"]] == [TICKER]
        _assert_embargo_holds(payload)

    async def test_a_one_character_query_returns_nothing(self, db_path):
        response = await _request(
            _app(db_path), "GET", "/api/estimates/markets", params={"q": "S"}
        )
        assert response.json() == {"markets": []}


class TestRevisingOverTheApi:
    async def test_the_flow(self, db_path):
        app = _app(db_path)
        logged = await _request(
            app, "POST", "/api/estimates", json=_body(), headers=AUTH
        )
        row_id = logged.json()["id"]
        revised = await _request(
            app,
            "POST",
            f"/api/estimates/{row_id}/revise",
            json={"reason": "mistyped"},
            headers=AUTH,
        )
        assert revised.status_code == 200
        recent = await _request(app, "GET", "/api/estimates/recent")
        assert recent.json()["estimates"][0]["stated_probability_is_revised"] == 1

    async def test_a_missing_row_is_a_404(self, db_path):
        response = await _request(
            _app(db_path),
            "POST",
            "/api/estimates/999/revise",
            json={"reason": "typo"},
            headers=AUTH,
        )
        assert response.status_code == 404

    async def test_it_requires_auth(self, db_path):
        response = await _request(
            _app(db_path), "POST", "/api/estimates/1/revise", json={"reason": "x"}
        )
        assert response.status_code == 401


class TestSearchAndRecentHelpers:
    def test_search_matches_ticker_fragments_case_blind(self, conn):
        _seed_market(conn)
        found = search_markets(conn, "housea", now_ms=NOW)
        assert [m["ticker"] for m in found] == [TICKER]

    def test_a_closed_market_is_not_offered(self, conn):
        _seed_market(conn)
        conn.execute(
            "UPDATE kalshi_markets SET close_ms = ? WHERE ticker = ?",
            (NOW - 1, TICKER),
        )
        conn.commit()
        assert search_markets(conn, "Seattle", now_ms=NOW) == []

    def test_recent_returns_newest_first(self, conn):
        first = _estimate(conn, estimate_server_ms=NOW - 10)
        second = _estimate(conn, estimate_server_ms=NOW)
        listed = recent_estimates(conn)
        assert [row["id"] for row in listed] == [second, first]


class TestTheHonestyTapIsServerRequired:
    async def test_a_payload_without_the_answer_is_refused(self, db_path):
        """'Never trust that the UI disabled a button.' The question must be
        answered before the number exists; a payload without it skipped the
        ordering the study depends on."""
        app = _app(db_path)
        body = {"ticker": TICKER, "stated_probability_bp": 6250}
        response = await _request(
            app, "POST", "/api/estimates", json=body, headers=AUTH
        )
        assert response.status_code == 422


def _seed_settlement(
    conn,
    *,
    settled_ms,
    side="yes",
    contracts=2.0,
    entry_price_tenths=450,
    fee_cost_tenths=70,
    market_result="no",
    ticker="KXMLBGAME-26AUG20HOUSEA-HOU",
):
    conn.execute(
        "INSERT INTO venue_settlements (ticker, settled_ms, side, contracts, "
        "entry_price_tenths, fee_cost_tenths, market_result) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            ticker,
            settled_ms,
            side,
            contracts,
            entry_price_tenths,
            fee_cost_tenths,
            market_result,
        ),
    )
    conn.commit()


START = NOW - 1_000_000


def _open_study(conn, start_ms=START):
    db._set_meta(conn, STUDY_START_MS_KEY, str(start_ms))
    conn.commit()


class TestStudyLossReader:
    """§5 arm 3, as amended by A2: sum(payout - cost - fee), negated to a loss.

    The refusal semantics are the point: `None` means "the record cannot
    carry the registered formula", and it is never collapsed into 0.0 --
    a broken read and a clean sheet are different states.
    """

    def test_no_study_start_means_none_not_zero(self, conn):
        _seed_settlement(conn, settled_ms=NOW)
        assert study_loss_dollars(conn) is None

    def test_open_study_with_no_settlements_is_a_true_zero(self, conn):
        _open_study(conn)
        assert study_loss_dollars(conn) == 0.0

    def test_a_loss_is_cost_plus_fee(self, conn):
        _open_study(conn)
        # 2 contracts at 45.0c, 7.0c fee, market went the other way:
        # payout 0 - cost 900 - fee 70 = -970 tenths = $0.97 lost.
        _seed_settlement(conn, settled_ms=NOW, side="yes", market_result="no")
        assert study_loss_dollars(conn) == pytest.approx(0.97)

    def test_a_win_reduces_the_loss_below_zero(self, conn):
        _open_study(conn)
        # payout 2000 - cost 900 - fee 70 = +1030 tenths: loss is -$1.03.
        _seed_settlement(conn, settled_ms=NOW, side="yes", market_result="yes")
        assert study_loss_dollars(conn) == pytest.approx(-1.03)

    def test_fractional_contracts_stay_exact(self, conn):
        _open_study(conn)
        # The live record holds 0.27-contract positions; Decimal math means
        # 0.27 * 300 is exactly 81 tenths, not 80.999...
        _seed_settlement(
            conn,
            settled_ms=NOW,
            contracts=0.27,
            entry_price_tenths=300,
            fee_cost_tenths=10,
            side="no",
            market_result="no",
        )
        # payout 270 - cost 81 - fee 10 = +179 tenths: loss -$0.179.
        assert study_loss_dollars(conn) == pytest.approx(-0.179)

    def test_pre_study_settlements_do_not_count(self, conn):
        _open_study(conn)
        _seed_settlement(conn, settled_ms=START - 1, side="yes", market_result="no")
        assert study_loss_dollars(conn) == 0.0

    def test_an_unreadable_entry_price_refuses_the_whole_sum(self, conn):
        _open_study(conn)
        _seed_settlement(conn, settled_ms=NOW)
        _seed_settlement(
            conn,
            settled_ms=NOW + 1,
            entry_price_tenths=None,
            ticker="KXMLBGAME-26AUG20HOUSEA-SEA",
        )
        assert study_loss_dollars(conn) is None

    def test_a_void_result_refuses_rather_than_inventing_a_payout(self, conn):
        _open_study(conn)
        _seed_settlement(conn, settled_ms=NOW, market_result="void")
        assert study_loss_dollars(conn) is None

    def test_stop_fires_at_the_ceiling_exactly(self, conn):
        _open_study(conn)
        # 200 contracts at 50.0c, no fee, lost: exactly $100.00.
        _seed_settlement(
            conn,
            settled_ms=NOW,
            contracts=200.0,
            entry_price_tenths=500,
            fee_cost_tenths=0,
            side="yes",
            market_result="no",
        )
        assert study_loss_dollars(conn) == pytest.approx(100.0)
        assert study_stop_fired(conn) is True

    def test_stop_is_tristate(self, conn):
        assert study_stop_fired(conn) is None
        _open_study(conn)
        assert study_stop_fired(conn) is False


class TestTheMoneyArmOverTheApi:
    """The strip's route is embargo-safe (A7) and the 423 is server-side."""

    def _seed(self, db_path, loss_dollars=None, void=False):
        handle = db.open_db(db_path)
        _open_study(handle)
        if void:
            _seed_settlement(handle, settled_ms=NOW, market_result="void")
        elif loss_dollars is not None:
            # loss = contracts * entry, no fee, side lost. entry 50.0c each:
            # contracts = dollars * 2.
            _seed_settlement(
                handle,
                settled_ms=NOW,
                contracts=loss_dollars * 2.0,
                entry_price_tenths=500,
                fee_cost_tenths=0,
                side="yes",
                market_result="no",
            )
        handle.close()

    async def test_the_strip_reads_unknown_as_null(self, db_path):
        response = await _request(_app(db_path), "GET", "/api/estimates/stop")
        assert response.status_code == 200
        payload = response.json()
        assert payload == {
            "loss_dollars": None,
            "ceiling_dollars": STUDY_LOSS_CEILING_DOLLARS,
            "stopped": None,
        }
        _assert_embargo_holds(payload)

    async def test_the_strip_shows_the_loss(self, db_path):
        self._seed(db_path, loss_dollars=12.5)
        response = await _request(_app(db_path), "GET", "/api/estimates/stop")
        payload = response.json()
        assert payload["loss_dollars"] == pytest.approx(12.5)
        assert payload["stopped"] is False
        _assert_embargo_holds(payload)

    async def test_a_fired_stop_locks_the_write_path(self, db_path):
        self._seed(db_path, loss_dollars=100.0)
        app = _app(db_path)
        strip = (await _request(app, "GET", "/api/estimates/stop")).json()
        assert strip["stopped"] is True
        response = await _request(
            app, "POST", "/api/estimates", json=_body(), headers=AUTH
        )
        assert response.status_code == 423
        assert "$100.00" in response.json()["detail"]

    async def test_an_unreadable_record_does_not_lock_joe_out(self, db_path):
        # A void row makes the loss uncomputable. That must read as unknown,
        # not as a firing -- and must not refuse the log.
        self._seed(db_path, void=True)
        response = await _request(
            _app(db_path), "POST", "/api/estimates", json=_body(), headers=AUTH
        )
        assert response.status_code == 200

    async def test_below_the_ceiling_the_write_path_is_open(self, db_path):
        self._seed(db_path, loss_dollars=99.0)
        response = await _request(
            _app(db_path), "POST", "/api/estimates", json=_body(), headers=AUTH
        )
        assert response.status_code == 200
