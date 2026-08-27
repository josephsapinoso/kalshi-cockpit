"""`backend/hedge.py` — the record of what Joe holds, and what it is worth now.

What these tests establish: a ticket is refused at entry on the same arithmetic
that refuses it at alert time; a leg resolves once and only from `pending`; the
venue's `result` settles a leg and an unrecognised result settles nothing; the
hedge is bought on the OPPOSITE side at the derived ask with the size behind it;
a ticket with one live leg is a lock and a ticket with several is not; a lost leg
and a voided leg say different things; the payload carries no edge, EV, kelly or
size key; and `backend/gate.py` reads neither new table.

What they do not establish: that a hand-marked leg actually won, that the record
is complete, or that any hedge is worth taking.
"""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from backend import hedge
from backend.core.hedge import Derisk, Lock, Refusal
from backend.store import db

ROOT = Path(__file__).resolve().parent.parent
NOW_MS = 1_700_000_000_000
MAX_AGE_MS = 30_000

CIN = "KXMLBGAME-26AUG26CINSF-CIN"
LAD = "KXMLBGAME-26AUG26LADSD-LAD"


@pytest.fixture()
def conn(tmp_path):
    connection = db.init_db(tmp_path / "cockpit.db")
    yield connection
    connection.close()


def book(
    ticker=CIN,
    *,
    yes_bid=200,
    no_bid=760,
    yes_size=400.0,
    no_size=400.0,
    status="active",
    observed_ms=NOW_MS,
):
    return hedge.MarketBook(
        ticker=ticker,
        yes_bid_tenths=yes_bid,
        no_bid_tenths=no_bid,
        yes_ask_size=yes_size,
        no_ask_size=no_size,
        status=status,
        observed_ms=observed_ms,
    )


def record(conn, *, legs=None, stake=5_000, payout=100_000, **kwargs):
    return hedge.record_position(
        conn,
        now_ms=NOW_MS,
        source=kwargs.pop("source", "sportsbook"),
        label=kwargs.pop("label", "Saturday six"),
        stake_tenths=stake,
        return_tenths=payout,
        legs=legs
        if legs is not None
        else [
            {"ticker": CIN, "side": "yes", "label": "Cincinnati to win"},
            {"ticker": LAD, "side": "yes", "label": "Los Angeles to win"},
        ],
        **kwargs,
    )


def assess(conn, position_id, books, *, spendable=10_000_000):
    position = next(
        row
        for row in hedge.open_positions(conn)
        if int(row["id"]) == position_id
    )
    legs = hedge.legs_for(conn, position_id)
    return position, legs, hedge.assess(
        position,
        legs,
        books,
        now_ms=NOW_MS,
        max_quote_age_ms=MAX_AGE_MS,
        spendable_tenths=spendable,
    )


class TestTheSchemaCarriesTheNewTables:
    def test_a_fresh_database_has_both(self, conn):
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"parlay_positions", "parlay_position_legs"} <= names

    def test_the_previous_version_gains_them_without_a_migration_step(self, tmp_path):
        """The claim ADR 0074's Consequences makes, executed rather than asserted.

        A pure new table needs no `_MIGRATIONS` entry because `init_db` applies
        `schema.sql` with `CREATE TABLE IF NOT EXISTS` on every open. ADR 0072
        made the same claim for `loop_failures` and verified it against a real
        v21 database; this does the same for the volume that is actually out
        there.
        """
        path = tmp_path / "v22.db"
        connection = db.init_db(path)
        connection.execute("DROP TABLE parlay_position_legs")
        connection.execute("DROP TABLE parlay_positions")
        # One version back, read from `SCHEMA_VERSION` rather than typed. It
        # said "22" until the merge with `main`, which had ALSO claimed v23 --
        # so a hand-written number here starts asserting about a version two
        # steps back the moment another lane adds a table.
        db._set_meta(connection, "schema_version", str(db.SCHEMA_VERSION - 1))
        connection.commit()
        connection.close()

        # `init_db` is the boot path (`scripts/migrate_db.py` calls it);
        # `open_db` deliberately refuses a version mismatch rather than
        # migrating, so reopening the other way would test the refusal.
        reopened = db.init_db(path)
        try:
            names = {
                row[0]
                for row in reopened.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            assert {"parlay_positions", "parlay_position_legs"} <= names
            assert db.get_meta(reopened, "schema_version") == str(db.SCHEMA_VERSION)
        finally:
            reopened.close()


class TestRecordingATicket:
    def test_it_comes_back_with_its_legs_in_order(self, conn):
        position_id = record(conn)
        legs = hedge.legs_for(conn, position_id)
        assert [leg["leg_index"] for leg in legs] == [0, 1]
        assert [leg["outcome"] for leg in legs] == ["pending", "pending"]
        assert [leg["resolved_source"] for leg in legs] == [None, None]

    def test_a_misplaced_decimal_point_is_refused_at_entry(self, conn):
        # Refused HERE, while he is still typing, and not only in the sixth
        # inning when the alert would have used it.
        with pytest.raises(hedge.PositionRefused):
            record(conn, stake=5_000, payout=5_000_000_000)
        assert hedge.open_positions(conn) == []

    def test_a_ticket_with_no_legs_is_refused(self, conn):
        with pytest.raises(hedge.PositionRefused):
            record(conn, legs=[])

    def test_a_ticket_with_no_name_is_refused(self, conn):
        with pytest.raises(hedge.PositionRefused):
            record(conn, label="   ")

    def test_a_refusal_carries_the_reason_as_data(self, conn):
        with pytest.raises(hedge.PositionRefused) as caught:
            record(conn, stake=10_000, payout=9_000)
        assert isinstance(caught.value.refusal, Refusal)
        assert caught.value.refusal.detail


class TestResolvingALeg:
    def test_a_leg_moves_once(self, conn):
        position_id = record(conn)
        leg_id = int(hedge.legs_for(conn, position_id)[0]["id"])
        assert hedge.resolve_leg(
            conn, leg_id=leg_id, outcome="won", now_ms=NOW_MS, source="manual"
        )
        # A settled leg is a fact. Letting a second write flip it would make a
        # lock computed an hour ago unreproducible from the record.
        assert not hedge.resolve_leg(
            conn, leg_id=leg_id, outcome="lost", now_ms=NOW_MS, source="manual"
        )
        assert hedge.legs_for(conn, position_id)[0]["outcome"] == "won"

    def test_the_source_is_recorded_because_the_two_are_not_equal(self, conn):
        position_id = record(conn)
        leg_id = int(hedge.legs_for(conn, position_id)[0]["id"])
        hedge.resolve_leg(
            conn, leg_id=leg_id, outcome="won", now_ms=NOW_MS, source="manual"
        )
        assert hedge.legs_for(conn, position_id)[0]["resolved_source"] == "manual"

    @pytest.mark.parametrize("bad", ["pending", "cancelled", ""])
    def test_an_unknown_outcome_raises_rather_than_being_stored(self, conn, bad):
        position_id = record(conn)
        leg_id = int(hedge.legs_for(conn, position_id)[0]["id"])
        with pytest.raises(ValueError):
            hedge.resolve_leg(
                conn, leg_id=leg_id, outcome=bad, now_ms=NOW_MS, source="manual"
            )


class TestResolvingFromTheVenue:
    def _market(self, conn, ticker, result):
        # `kalshi_markets` carries real foreign keys to the series and the
        # event, so the parents are inserted rather than the constraint
        # loosened -- the row this test needs is the shape the recorder writes.
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_series "
            "(series_ticker, title, first_seen_ms, last_seen_ms) "
            "VALUES ('SER', 'series', ?, ?)",
            (NOW_MS, NOW_MS),
        )
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_events "
            "(event_ticker, series_ticker, title, first_seen_ms, last_seen_ms) "
            "VALUES ('EV', 'SER', 'event', ?, ?)",
            (NOW_MS, NOW_MS),
        )
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, event_ticker, series_ticker, "
            "market_type, title, result, first_seen_ms, last_seen_ms) "
            "VALUES (?, 'EV', 'SER', 'binary', 't', ?, ?, ?)",
            (ticker, result, NOW_MS, NOW_MS),
        )
        conn.commit()

    def test_a_matching_result_wins_the_leg(self, conn):
        position_id = record(conn)
        self._market(conn, CIN, "yes")
        assert hedge.resolve_from_venue(conn, now_ms=NOW_MS) == 1
        legs = hedge.legs_for(conn, position_id)
        assert legs[0]["outcome"] == "won"
        assert legs[0]["resolved_source"] == "venue"
        assert legs[1]["outcome"] == "pending"

    def test_an_opposite_result_loses_the_leg(self, conn):
        position_id = record(conn)
        self._market(conn, CIN, "no")
        hedge.resolve_from_venue(conn, now_ms=NOW_MS)
        assert hedge.legs_for(conn, position_id)[0]["outcome"] == "lost"

    @pytest.mark.parametrize("result", ["", "void", "  ", "VOIDED"])
    def test_an_unrecognised_result_settles_nothing(self, conn, result):
        # Unreadable resolves to NOTHING, never to a loss: marking a leg lost
        # off an unparsed field kills a live ticket on the screen and silences
        # its alerts.
        position_id = record(conn)
        self._market(conn, CIN, result)
        assert hedge.resolve_from_venue(conn, now_ms=NOW_MS) == 0
        assert hedge.legs_for(conn, position_id)[0]["outcome"] == "pending"

    def test_a_leg_with_no_ticker_is_structurally_out_of_reach(self, conn):
        position_id = record(
            conn,
            legs=[
                {"ticker": None, "side": "yes", "label": "A book-only leg"},
                {"ticker": CIN, "side": "yes", "label": "Cincinnati to win"},
            ],
        )
        self._market(conn, CIN, "yes")
        hedge.resolve_from_venue(conn, now_ms=NOW_MS)
        assert hedge.legs_for(conn, position_id)[0]["outcome"] == "pending"

    def test_a_closed_position_is_left_alone(self, conn):
        position_id = record(conn)
        hedge.close_position(
            conn, position_id=position_id, now_ms=NOW_MS, status="settled"
        )
        self._market(conn, CIN, "yes")
        assert hedge.resolve_from_venue(conn, now_ms=NOW_MS) == 0


class TestWhichSideTheHedgeBuys:
    def test_a_yes_leg_is_hedged_by_buying_no(self):
        assert hedge.hedge_side("yes") == "no"
        assert hedge.hedge_side("no") == "yes"

    def test_the_ask_is_derived_from_the_opposing_bid(self):
        # YES bid 20c, NO bid 76c. Hedging a YES leg buys NO, and the NO ask
        # is 1000 - the YES bid = 80c -- never the NO bid, and never a mid.
        quote = hedge.quote_for_hedge("yes", book(yes_bid=200, no_bid=760))
        assert quote.side == "no"
        assert quote.ask_tenths == 800
        assert quote.depth_at_ask == 400.0
        # The leg's own ask rides along only so the crossed-book test has both
        # sides. 1000 - 760 = 240.
        assert quote.leg_ask_tenths == 240

    def test_an_empty_opposing_side_derives_no_ask_rather_than_a_dollar(self):
        # The venue reports an empty side as 0.0000, and `1000 - 0` is a
        # settled outcome wearing a price's clothes. Fixed at three call sites
        # over eleven days; refused at the source here.
        quote = hedge.quote_for_hedge("yes", book(yes_bid=0))
        assert quote.ask_tenths is None

    def test_the_leg_price_is_the_bid_and_not_the_ask(self):
        # Valuing a position you hold uses what somebody will PAY you.
        assert hedge.leg_probability("yes", book(yes_bid=200)) == pytest.approx(0.2)
        assert hedge.leg_probability("no", book(no_bid=760)) == pytest.approx(0.76)

    def test_an_untradeable_bid_is_no_probability_at_all(self):
        assert hedge.leg_probability("yes", book(yes_bid=0)) is None
        assert hedge.leg_probability("yes", book(yes_bid=1000)) is None
        assert hedge.leg_probability("yes", book(yes_bid=None)) is None


class TestTwoLegsOfOneGame:
    """Found by driving the real venue, not by a test (2026-08-26).

    A ticket recorded with Boston-to-win and Miami-to-win — which cannot both
    happen — was priced as two independent legs and handed back a joint
    probability. The two sides of one fixture have different market tickers, so
    without the fixture key they looked unrelated.
    """

    def test_the_fixture_is_derived_from_the_market_ticker(self):
        assert (
            hedge.event_ticker_for("KXMLBGAME-26AUG261840BOSMIA-BOS")
            == "KXMLBGAME-26AUG261840BOSMIA"
        )
        assert hedge.event_ticker_for(
            "KXMLBGAME-26AUG261840BOSMIA-MIA"
        ) == hedge.event_ticker_for("KXMLBGAME-26AUG261840BOSMIA-BOS")

    @pytest.mark.parametrize(
        "ticker", [None, "", "KXMVESOMETHING", "A-B", "A-B-C-D"]
    )
    def test_a_ticker_it_cannot_read_returns_nothing_rather_than_guessing(
        self, ticker
    ):
        # A wrong fixture key MERGES two real games and refuses a legitimate
        # joint, which is worse than not knowing.
        assert hedge.event_ticker_for(ticker) is None

    def test_recording_fills_the_fixture_in(self, conn):
        position_id = record(
            conn,
            legs=[
                {
                    "ticker": "KXMLBGAME-26AUG261840BOSMIA-BOS",
                    "side": "yes",
                    "label": "Boston wins",
                },
            ],
        )
        leg = hedge.legs_for(conn, position_id)[0]
        assert leg["event_ticker"] == "KXMLBGAME-26AUG261840BOSMIA"

    def test_an_explicit_fixture_is_never_overwritten(self, conn):
        position_id = record(
            conn,
            legs=[
                {
                    "ticker": "KXMLBGAME-26AUG261840BOSMIA-BOS",
                    "side": "yes",
                    "label": "Boston wins",
                    "event_ticker": "SOMETHING-ELSE",
                },
            ],
        )
        assert (
            hedge.legs_for(conn, position_id)[0]["event_ticker"]
            == "SOMETHING-ELSE"
        )

    def test_a_mutually_exclusive_pair_gets_no_joint_at_all(self, conn):
        bos = "KXMLBGAME-26AUG261840BOSMIA-BOS"
        mia = "KXMLBGAME-26AUG261840BOSMIA-MIA"
        position_id = record(
            conn,
            legs=[
                {"ticker": bos, "side": "yes", "label": "Boston wins"},
                {"ticker": mia, "side": "yes", "label": "Miami wins"},
            ],
        )
        _, _, assessment = assess(
            conn,
            position_id,
            {
                bos: book(ticker=bos, yes_bid=200, no_bid=790),
                mia: book(ticker=mia, yes_bid=790, no_bid=200),
            },
        )
        assert assessment.state == hedge.STATE_DERISK
        # The per-leg prices still render; only the joint is withheld. This
        # repo has no measured same-game correlation (ADR 0012 §5), and a pair
        # that cannot both win is where inventing one is most wrong.
        assert assessment.outcome.joint_probability is None
        assert assessment.outcome.notional_value_tenths is None
        assert assessment.outcome.joint_refusal is not None
        assert assessment.outcome.ladder

    def test_a_row_written_without_a_fixture_still_classifies(self, conn):
        """The read-side fallback, and the only thing that reaches it.

        `record_position` fills the fixture in, so a row missing one came from
        somewhere else — a future import path, a hand-written INSERT, or a row
        predating this column being populated. Deriving it again on read is
        cheap and the alternative is a mutually exclusive pair quietly getting
        a joint. A mutation removing this stayed GREEN until the row was
        written the way something other than `record_position` would write it.
        """
        bos = "KXMLBGAME-26AUG261840BOSMIA-BOS"
        mia = "KXMLBGAME-26AUG261840BOSMIA-MIA"
        position_id = record(conn, legs=[{"ticker": bos, "side": "yes", "label": "Boston wins"}])
        conn.execute(
            "INSERT INTO parlay_position_legs (position_id, leg_index, ticker, "
            "side, label, event_ticker, outcome) "
            "VALUES (?, 1, ?, 'yes', 'Miami wins', NULL, 'pending')",
            (position_id, mia),
        )
        conn.execute(
            "UPDATE parlay_position_legs SET event_ticker = NULL WHERE ticker = ?",
            (bos,),
        )
        conn.commit()
        assert all(
            leg["event_ticker"] is None for leg in hedge.legs_for(conn, position_id)
        )

        _, _, assessment = assess(
            conn,
            position_id,
            {
                bos: book(ticker=bos, yes_bid=200, no_bid=790),
                mia: book(ticker=mia, yes_bid=790, no_bid=200),
            },
        )
        assert assessment.outcome.joint_probability is None
        assert assessment.outcome.joint_refusal is not None

    def test_two_different_games_still_get_one(self, conn):
        # The vacuity guard on the test above: a fixture key that merged every
        # ticker would pass it and break this.
        position_id = record(conn)
        _, _, assessment = assess(
            conn, position_id, {CIN: book(), LAD: book(ticker=LAD)}
        )
        assert assessment.outcome.joint_probability is not None


class TestWhatStateATicketIsIn:
    def test_one_live_leg_with_the_rest_won_is_a_lock(self, conn):
        position_id = record(conn)
        legs = hedge.legs_for(conn, position_id)
        hedge.resolve_leg(
            conn,
            leg_id=int(legs[1]["id"]),
            outcome="won",
            now_ms=NOW_MS,
            source="manual",
        )
        _, _, assessment = assess(conn, position_id, {CIN: book()})
        assert assessment.state == hedge.STATE_LOCK
        assert isinstance(assessment.outcome, Lock)
        assert assessment.hedge_leg_id == int(legs[0]["id"])

    def test_two_live_legs_is_a_derisk_and_locks_nothing(self, conn):
        position_id = record(conn)
        _, _, assessment = assess(
            conn, position_id, {CIN: book(), LAD: book(ticker=LAD, yes_bid=600)}
        )
        assert assessment.state == hedge.STATE_DERISK
        assert isinstance(assessment.outcome, Derisk)

    def test_the_leg_in_most_trouble_is_the_one_priced_for_a_hedge(self, conn):
        position_id = record(conn)
        legs = hedge.legs_for(conn, position_id)
        # Cincinnati at 20c, Los Angeles at 60c: the hedge is priced on the
        # market the venue currently likes least.
        _, _, assessment = assess(
            conn,
            position_id,
            {CIN: book(yes_bid=200), LAD: book(ticker=LAD, yes_bid=600)},
        )
        assert assessment.hedge_leg_id == int(legs[0]["id"])

    def test_a_leg_nobody_is_bidding_on_does_not_count_as_the_weakest(self, conn):
        # A leg with no bid looks like the weakest and is actually the one we
        # know least about. Hedging it would be acting on a missing number.
        position_id = record(conn)
        legs = hedge.legs_for(conn, position_id)
        _, _, assessment = assess(
            conn,
            position_id,
            {CIN: book(yes_bid=0), LAD: book(ticker=LAD, yes_bid=600)},
        )
        assert assessment.hedge_leg_id == int(legs[1]["id"])

    def test_a_lost_leg_ends_the_ticket(self, conn):
        position_id = record(conn)
        legs = hedge.legs_for(conn, position_id)
        hedge.resolve_leg(
            conn,
            leg_id=int(legs[0]["id"]),
            outcome="lost",
            now_ms=NOW_MS,
            source="manual",
        )
        _, _, assessment = assess(conn, position_id, {LAD: book(ticker=LAD)})
        assert assessment.state == hedge.STATE_DEAD
        assert assessment.outcome is None

    def test_a_voided_leg_refuses_to_guess_a_new_payout(self, conn):
        position_id = record(conn)
        legs = hedge.legs_for(conn, position_id)
        hedge.resolve_leg(
            conn,
            leg_id=int(legs[0]["id"]),
            outcome="void",
            now_ms=NOW_MS,
            source="manual",
        )
        _, _, assessment = assess(conn, position_id, {LAD: book(ticker=LAD)})
        assert assessment.state == hedge.STATE_VOID_LEG
        assert assessment.outcome is None

    def test_every_leg_won_leaves_nothing_to_hedge(self, conn):
        position_id = record(conn)
        for leg in hedge.legs_for(conn, position_id):
            hedge.resolve_leg(
                conn,
                leg_id=int(leg["id"]),
                outcome="won",
                now_ms=NOW_MS,
                source="manual",
            )
        _, _, assessment = assess(conn, position_id, {})
        assert assessment.state == hedge.STATE_WON
        assert assessment.outcome is None

    def test_no_readable_market_says_so_rather_than_pricing_nothing(self, conn):
        position_id = record(conn)
        _, _, assessment = assess(conn, position_id, {})
        assert assessment.state == hedge.STATE_NOT_HEDGEABLE
        assert assessment.outcome is None
        assert "no hedge to price" in assessment.detail

    def test_every_state_it_can_return_is_declared(self, conn):
        assert set(hedge.STATES) == {
            hedge.STATE_LOCK,
            hedge.STATE_DERISK,
            hedge.STATE_DEAD,
            hedge.STATE_WON,
            hedge.STATE_VOID_LEG,
            hedge.STATE_NOT_HEDGEABLE,
        }


class TestWhatTheBalanceIsAllowedToDecide:
    def test_a_read_balance_bounds_the_hedge(self, conn):
        # $100 against an 80c hedge plus its fee: 124 contracts, not 125.
        count, known = hedge.affordable_contracts(
            100_000, 800, depth_contracts=10_000
        )
        assert known is True
        assert count == 100_000 // (800 + 12)

    def test_an_unread_balance_is_not_a_balance_of_zero(self, conn):
        # The poller answers None on any five-minute outage. Folding that into
        # a cap of zero would make every hedge unaffordable and silence the
        # alert for as long as the mirror was behind.
        count, known = hedge.affordable_contracts(
            None, 800, depth_contracts=250
        )
        assert known is False
        assert count == 250

    def test_an_unreadable_ask_cannot_bound_anything_either(self, conn):
        assert hedge.affordable_contracts(100_000, None, depth_contracts=7) == (
            7,
            False,
        )
        assert hedge.affordable_contracts(100_000, 1000, depth_contracts=7) == (
            7,
            False,
        )

    def test_the_screen_is_told_the_cap_was_not_real(self, conn):
        position_id = record(conn)
        legs = hedge.legs_for(conn, position_id)
        hedge.resolve_leg(
            conn,
            leg_id=int(legs[1]["id"]),
            outcome="won",
            now_ms=NOW_MS,
            source="manual",
        )
        _, _, assessment = assess(
            conn, position_id, {CIN: book()}, spendable=None
        )
        assert assessment.bankroll_known is False

    def test_a_real_balance_says_so(self, conn):
        position_id = record(conn)
        legs = hedge.legs_for(conn, position_id)
        hedge.resolve_leg(
            conn,
            leg_id=int(legs[1]["id"]),
            outcome="won",
            now_ms=NOW_MS,
            source="manual",
        )
        _, _, assessment = assess(
            conn, position_id, {CIN: book()}, spendable=100_000
        )
        assert assessment.bankroll_known is True


class TestTheWatchedSet:
    def test_it_is_the_pending_legs_of_open_tickets_only(self, conn):
        position_id = record(conn)
        legs = hedge.legs_for(conn, position_id)
        assert set(hedge.watched_tickers(conn)) == {CIN, LAD}

        hedge.resolve_leg(
            conn,
            leg_id=int(legs[0]["id"]),
            outcome="won",
            now_ms=NOW_MS,
            source="manual",
        )
        assert hedge.watched_tickers(conn) == [LAD]

        hedge.close_position(
            conn, position_id=position_id, now_ms=NOW_MS, status="settled"
        )
        assert hedge.watched_tickers(conn) == []

    def test_a_leg_with_no_ticker_is_not_watched(self, conn):
        record(
            conn,
            legs=[{"ticker": None, "side": "yes", "label": "A book-only leg"}],
        )
        assert hedge.watched_tickers(conn) == []


class TestThePayload:
    def _payload(self, conn, position_id, books, **kwargs):
        position, legs, assessment = assess(conn, position_id, books, **kwargs)
        return hedge.serialise_position(
            position, legs, books, assessment, now_ms=NOW_MS
        )

    def test_money_arrives_as_strings_rendered_here(self, conn):
        position_id = record(conn, stake=5_000, payout=100_000)
        payload = self._payload(conn, position_id, {CIN: book(), LAD: book(ticker=LAD)})
        assert payload["stake_display"] == "$5.00"
        assert payload["return_display"] == "$100.00"

    def test_it_carries_no_edge_ev_kelly_or_size_key(self, conn):
        """The key-walk `tests/test_parlays_api.py` runs on the parlay desk.

        ADR 0038 closed the hunt and ADR 0074 keeps this surface out of it: a
        hedge takes the venue's price as given and claims nothing about
        mispricing. A key named for an edge is how that stops being true.
        """
        position_id = record(conn)
        payload = self._payload(conn, position_id, {CIN: book(), LAD: book(ticker=LAD)})

        forbidden = (
            "edge",
            "ev",
            "kelly",
            "breakeven",
            "break_even",
            "suggested_contracts",
            "fair_probability",
            "model_probability",
        )
        seen: list[str] = []

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    seen.append(key)
                    assert key not in forbidden, key
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(payload)
        # Vacuity guard: a walk that visited nothing would pass silently.
        assert len(seen) > 20

    def test_a_lock_reports_the_full_hedge_even_when_it_is_out_of_reach(self, conn):
        position_id = record(conn, stake=5_000, payout=100_000)
        legs = hedge.legs_for(conn, position_id)
        hedge.resolve_leg(
            conn,
            leg_id=int(legs[1]["id"]),
            outcome="won",
            now_ms=NOW_MS,
            source="manual",
        )
        # $2.50 of balance against an 80c hedge: five contracts.
        payload = self._payload(conn, position_id, {CIN: book()}, spendable=2_500)
        block = payload["hedge"]
        assert block["kind"] == hedge.STATE_LOCK
        assert block["equalising"]["contracts"] == 100
        assert block["equalising"]["affordable"] is False
        assert block["full_hedge_is_out_of_reach"] is True

    def test_a_derisk_has_no_guarantee_key_at_all(self, conn):
        # Not `guaranteed: false`. A ticket with several legs live does not
        # have a guarantee that happens to be absent; it has none to have.
        position_id = record(conn)
        payload = self._payload(
            conn, position_id, {CIN: book(), LAD: book(ticker=LAD)}
        )
        assert payload["hedge"]["kind"] == hedge.STATE_DERISK
        assert "guaranteed" not in payload["hedge"]

    def test_an_unpriceable_book_renders_a_refusal_and_not_a_number(self, conn):
        position_id = record(conn, stake=5_000, payout=100_000)
        legs = hedge.legs_for(conn, position_id)
        hedge.resolve_leg(
            conn,
            leg_id=int(legs[1]["id"]),
            outcome="won",
            now_ms=NOW_MS,
            source="manual",
        )
        payload = self._payload(conn, position_id, {CIN: book(yes_bid=0)})
        assert payload["hedge"]["refusal"]["reason"]
        assert "ask_display" not in payload["hedge"]

    def test_nothing_to_hedge_and_nothing_readable_are_different_answers(self, conn):
        won = record(conn, label="all won")
        for leg in hedge.legs_for(conn, won):
            hedge.resolve_leg(
                conn,
                leg_id=int(leg["id"]),
                outcome="won",
                now_ms=NOW_MS,
                source="manual",
            )
        assert self._payload(conn, won, {})["hedge"] is None

        live = record(conn, label="still live")
        block = self._payload(conn, live, {CIN: book(status="settled")})["hedge"]
        assert block is not None and block["refusal"] is not None

    def test_a_leg_with_no_bid_shows_no_percentage_rather_than_zero(self, conn):
        position_id = record(conn)
        payload = self._payload(
            conn, position_id, {CIN: book(yes_bid=0), LAD: book(ticker=LAD)}
        )
        cin = next(leg for leg in payload["legs"] if leg["ticker"] == CIN)
        assert cin["chance_display"] == "--"

    def test_the_caveats_travel_with_the_payload(self, conn):
        record(conn)
        payload = {"notes": dict(hedge.NOTES)}
        assert set(payload["notes"]) == {
            "upper_bound",
            "not_advice",
            "no_button",
            "derisk",
        }


class TestTheInterlockCannotSeeThisRecord:
    def test_gate_reads_neither_new_table(self):
        """The `manual_orders` rule, applied to the same class of row.

        `backend/gate.py` decides whether live trading may be enabled. These
        rows are Joe's own discretion — a ticket he typed in, a leg he marked
        won — and letting them into an evidence population would mean the
        interlock could move because he filled in a form.

        Asserted over the source rather than by convention, because a
        convention is what the `manual_orders` comment already is and this is
        the half that a reviewer cannot forget to apply.
        """
        source = (ROOT / "backend" / "gate.py").read_text(encoding="utf-8")
        assert "parlay_positions" not in source
        assert "parlay_position_legs" not in source
        assert "backend.hedge" not in source
        assert "from .hedge" not in source

    def test_the_hedge_modules_write_no_recommendation_row(self):
        """No in-play row enters the evidence record (ADR 0006, ADR 0074 §4)."""
        for name in ("hedge.py", "core/hedge.py"):
            source = (ROOT / "backend" / name).read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    assert "INSERT INTO recommendations" not in node.value
                    assert "UPDATE recommendations" not in node.value

    def test_no_anthropic_client_is_reachable_from_the_hedge_path(self):
        """Joe's constraint, made executable: no token is spent here, ever.

        Over the CODE, not the prose — a module that explains in its docstring
        why it never calls an agent must not fail for the sentence.
        """
        from conftest import python_code_without_prose

        for name in ("hedge.py", "core/hedge.py"):
            code = python_code_without_prose(ROOT / "backend" / name)
            assert "anthropic" not in code.lower()
            assert "structured_call" not in code
            assert "agents" not in code
            assert "hedge_lock" in code or "record_position" in code

    def test_no_odds_credit_is_spent_from_the_hedge_path(self):
        """And the other half: Kalshi is unmetered, The Odds API is not."""
        from conftest import python_code_without_prose

        for name in ("hedge.py", "core/hedge.py"):
            code = python_code_without_prose(ROOT / "backend" / name)
            assert "api_credits" not in code
            assert "CreditBudget" not in code
            assert "fetch_odds" not in code


class TestReadingTheBooks:
    async def test_a_ticker_that_refuses_is_absent_rather_than_empty(self):
        # An absent book and an empty book are different states, and a screen
        # that renders them identically says "nobody is resting" about a
        # market it could not reach.
        async def fetch(ticker, *, observed_ms):
            if ticker == CIN:
                raise RuntimeError("the venue did not answer")
            return _FakeQuote(ticker, observed_ms)

        books = await hedge.read_books(
            [CIN, LAD], now_ms=NOW_MS, fetch_quote=fetch
        )
        assert CIN not in books
        assert LAD in books

    async def test_it_never_raises_into_the_caller(self):
        async def fetch(ticker, *, observed_ms):
            raise RuntimeError("everything is down")

        assert await hedge.read_books(
            [CIN, LAD], now_ms=NOW_MS, fetch_quote=fetch
        ) == {}


class _FakeMarket:
    yes_bid_tenths = 200
    no_bid_tenths = 760
    yes_ask_size = 400.0
    no_ask_size = 400.0


class _FakeQuote:
    def __init__(self, ticker, observed_ms):
        self.ticker = ticker
        self.observed_ms = observed_ms
        self.status = "active"
        self.market = _FakeMarket()
