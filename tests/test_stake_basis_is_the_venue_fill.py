"""The sunk stake on `/hedge` is read at the venue's own fill price.

Ticket #49, answered A by Joe on 2026-09-16. Two prices exist for every hand
bet -- `manual_orders.limit_price_tenths`, the ask the desk SENT at intent
time, and `manual_orders.venue_avg_fill_price_tenths`, what Kalshi said it
charged (schema v40, ADR 0143) -- and until this change nothing that ran read
the second one. `parlay_positions.stake_tenths` carried the sent price, and
every rung, every entry fee and the screen's stake line were computed from it.

What these tests establish: where the venue's price is readable AND provably
about this position, the stake is the venue's number; where it is not, the
recorded number stands and the position says which of the named reasons
applies; the stored row is never rewritten, so nothing is backfilled and
nothing has to be unwound; and `venue_avg_fee_dollars` is not read by this
module at all.

What they do not establish:

- **That the hedge figure is now correct.** ADR 0145's table lists at least
  four error terms on it and they do not share a sign; this narrows the
  stake's own price and closes none of them.
- **That the venue's `average_fill_price` is our side's price on a NO
  order.** The opposite: the NO case is refused here precisely because the
  convention has never been established (the registered census's A4.3 rule
  was written for it and never exercised -- all thirteen real orders are
  YES).
- **Anything about how often the two prices differ.** The census of
  2026-09-15 is a census of twelve rows in one stratum and is spent; no
  rate is asserted anywhere below.
- **That `fills` agrees with the create response.** The census names `fills`
  as the primary venue source and the create response as the fallback;
  this reads only the column on `manual_orders`, and says so.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend import hedge
from backend.kalshi.quotes import QuoteUnavailable
from backend.store import db

ROOT = Path(__file__).resolve().parent.parent
NOW_MS = 1_700_000_000_000
PLACED_MS = NOW_MS - 60_000

COMBO = "KXMVECROSSCATEGORY-SHARD1-26SEP16-ABC"
LEG_A = "KXMLBGAME-26SEP16CINSF-CIN"
LEG_B = "KXMLBGAME-26SEP16LADSD-LAD"

#: Four contracts. Sent at 41.0c, so the row the route wrote is 1,640 tenths
#: against a 4,000-tenth return. The venue's own fill lands at 38.8c.
CONTRACTS = 4
SENT_TENTHS = 410
VENUE_TENTHS = 388
STAKE_AT_SENT = CONTRACTS * SENT_TENTHS
STAKE_AT_VENUE = CONTRACTS * VENUE_TENTHS
RETURN_TENTHS = CONTRACTS * 1_000


@pytest.fixture()
def conn(tmp_path):
    connection = db.init_db(tmp_path / "cockpit.db")
    yield connection
    connection.close()


def a_position(
    conn,
    *,
    source="kalshi_combo",
    combo_ticker=COMBO,
    placed_ms=PLACED_MS,
    stake=STAKE_AT_SENT,
    payout=RETURN_TENTHS,
):
    """A held ticket shaped exactly as `_record_combo_position` writes one."""
    return hedge.record_position(
        conn,
        now_ms=NOW_MS,
        source=source,
        label=combo_ticker or "Saturday six",
        stake_tenths=stake,
        return_tenths=payout,
        legs=[
            {"ticker": LEG_A, "side": "yes", "label": "Cincinnati to win"},
            {"ticker": LEG_B, "side": "yes", "label": "Los Angeles to win"},
        ],
        placed_ms=placed_ms,
        combo_ticker=combo_ticker,
    )


def an_order(
    conn,
    *,
    ticker=COMBO,
    submitted_ms=PLACED_MS,
    side="yes",
    dry_run=0,
    venue_count=float(CONTRACTS),
    venue_price=VENUE_TENTHS,
    client_order_id=None,
):
    """A `manual_orders` row, written straight in.

    Direct SQL rather than `reserve_manual_order`: what is under test is the
    read that joins this row to a position, and routing a fixture through the
    order path would drag the consensus snapshot, the idempotency reservation
    and the cap machinery into a bookkeeping test. No payload is parsed here,
    so the captured-fixture rule does not apply.
    """
    cursor = conn.execute(
        "INSERT INTO manual_orders ("
        " client_order_id, submitted_ms, ticker, side, action, count,"
        " limit_price_tenths, max_price_tenths, status, request_body_json,"
        " dry_run, venue_fill_count, venue_avg_fill_price_tenths"
        ") VALUES (?, ?, ?, ?, 'buy', ?, ?, ?, 'filled', '{}', ?, ?, ?)",
        (
            client_order_id or f"cid-{ticker}-{submitted_ms}-{side}",
            submitted_ms,
            ticker,
            side,
            CONTRACTS,
            SENT_TENTHS,
            999,
            dry_run,
            venue_count,
            venue_price,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def basis_of(conn, position_id):
    rows = hedge.open_positions(conn)
    return hedge.stake_bases(conn, rows)[position_id]


class TestTheVenuePriceIsUsedWhenItIsReadable:
    def test_the_stake_is_the_venue_fill_not_the_price_the_desk_sent(self, conn):
        position_id = a_position(conn)
        an_order(conn)

        basis = basis_of(conn, position_id)

        assert basis.basis == hedge.STAKE_BASIS_VENUE_FILL
        assert basis.reason is None
        assert basis.stake_tenths == STAKE_AT_VENUE
        # The whole point: it is NOT the number on the row.
        assert basis.stake_tenths != STAKE_AT_SENT

    def test_the_screen_and_its_entry_fee_are_both_on_the_venue_number(self, conn):
        position_id = a_position(conn)
        an_order(conn)

        row = next(
            p for p in hedge.open_positions(conn) if int(p["id"]) == position_id
        )
        resolved = hedge.position_at_basis(row, basis_of(conn, position_id))

        assert int(resolved["stake_tenths"]) == STAKE_AT_VENUE
        # `entry_fee_tenths` takes the stake it is given, so the fee sunk
        # beside it moves with the price rather than staying on the sent one.
        assert hedge.entry_fee_tenths(resolved) == hedge.combo_entry_fee_tenths(
            STAKE_AT_VENUE, RETURN_TENTHS
        )
        assert hedge.entry_fee_tenths(resolved) != hedge.combo_entry_fee_tenths(
            STAKE_AT_SENT, RETURN_TENTHS
        )

    def test_a_dry_run_order_is_not_a_fill_and_does_not_price_a_stake(self, conn):
        position_id = a_position(conn)
        an_order(conn, dry_run=1)

        basis = basis_of(conn, position_id)

        assert basis.basis == hedge.STAKE_BASIS_AS_RECORDED
        assert basis.reason == "no_order_row"
        assert basis.stake_tenths == STAKE_AT_SENT


class TestTheRecordedStakeStandsAndSaysWhy:
    """Every branch falls back to the number already on the row, never to a
    zero and never to a blend of the two. The reason is a named value, not
    prose, because the reader that needs it most is a later audit."""

    def test_a_pre_v40_row_has_no_venue_price(self, conn):
        position_id = a_position(conn)
        an_order(conn, venue_price=None)

        basis = basis_of(conn, position_id)

        assert basis.basis == hedge.STAKE_BASIS_AS_RECORDED
        assert basis.reason == "no_venue_price"
        assert basis.stake_tenths == STAKE_AT_SENT

    def test_a_missing_venue_count_is_not_a_count_of_zero(self, conn):
        position_id = a_position(conn)
        an_order(conn, venue_count=None)

        basis = basis_of(conn, position_id)

        assert basis.reason == "no_venue_fill_count"
        assert basis.stake_tenths == STAKE_AT_SENT

    def test_a_no_order_refuses_the_venue_price_because_the_side_is_unresolved(
        self, conn
    ):
        """`limit_price_tenths` is OUR side's price -- a NO is reflected onto
        the YES book by `OrderRequest.fill_price_tenths`. The venue's
        `average_fill_price` is stored verbatim with no reflection, and which
        book it quotes on a NO order has never been established. Reading it
        there could halve or double the stake, so it is refused."""
        position_id = a_position(conn)
        an_order(conn, side="no")

        basis = basis_of(conn, position_id)

        assert basis.reason == "side_convention_unresolved"
        assert basis.stake_tenths == STAKE_AT_SENT

    def test_two_orders_on_one_key_make_the_link_unreadable(self, conn):
        position_id = a_position(conn)
        an_order(conn, client_order_id="first")
        an_order(conn, client_order_id="second", venue_price=100)

        basis = basis_of(conn, position_id)

        assert basis.reason == "ambiguous_order_rows"
        assert basis.stake_tenths == STAKE_AT_SENT

    def test_a_count_that_cannot_be_this_position_is_refused(self, conn):
        """`_record_combo_position` writes `return = contracts * $1.00` from
        the same fill count, so the joined row's count must reproduce the
        stored return. When it does not, the row found is about some other
        holding and its price would be multiplied by the wrong number."""
        position_id = a_position(conn)
        an_order(conn, venue_count=7.0)

        basis = basis_of(conn, position_id)

        assert basis.reason == "contract_count_disagrees"
        assert basis.stake_tenths == STAKE_AT_SENT

    def test_a_fractional_venue_count_is_refused_rather_than_rounded(self, conn):
        position_id = a_position(conn)
        an_order(conn, venue_count=2.5)

        basis = basis_of(conn, position_id)

        assert basis.reason == "fractional_venue_fill_count"
        assert basis.stake_tenths == STAKE_AT_SENT

    def test_a_count_of_zero_is_a_count_that_answered_not_a_silent_one(self, conn):
        """An IOC that matched no one reports `0.0` -- a real observation, and
        not the same fact as a column that never got a value. It cannot be a
        holding either way, so the recorded figure stands."""
        position_id = a_position(conn)
        an_order(conn, venue_count=0.0)

        basis = basis_of(conn, position_id)

        assert basis.reason == "venue_fill_count_unusable"
        assert basis.stake_tenths == STAKE_AT_SENT

    def test_a_position_with_no_order_row_keeps_its_own_figure(self, conn):
        position_id = a_position(conn)

        basis = basis_of(conn, position_id)

        assert basis.reason == "no_order_row"
        assert basis.stake_tenths == STAKE_AT_SENT

    def test_a_position_recorded_by_hand_has_no_order_to_join(self, conn):
        """`POST /api/hedge/positions` writes a ticket with no `placed_ms`
        the route controls, so there is no key and nothing to look up."""
        position_id = a_position(conn, placed_ms=None)

        basis = basis_of(conn, position_id)

        assert basis.reason == "no_order_row"
        assert basis.stake_tenths == STAKE_AT_SENT

    def test_a_sportsbook_slip_is_the_figure_joe_typed(self, conn):
        position_id = a_position(
            conn, source="sportsbook", combo_ticker=None, stake=5_000, payout=100_000
        )

        basis = basis_of(conn, position_id)

        assert basis.reason == "not_a_kalshi_combo"
        assert basis.stake_tenths == 5_000


class TestNothingIsBackfilled:
    def test_the_stored_stake_is_never_rewritten(self, conn):
        """Forward-only by construction: the correction lives on the read, so
        the permanent row keeps the price the desk actually sent -- which is
        the number a later audit compares against -- and the undo is deleting
        the reader."""
        position_id = a_position(conn)
        an_order(conn)

        assert basis_of(conn, position_id).stake_tenths == STAKE_AT_VENUE

        stored = conn.execute(
            "SELECT stake_tenths FROM parlay_positions WHERE id = ?",
            (position_id,),
        ).fetchone()
        assert int(stored["stake_tenths"]) == STAKE_AT_SENT

    def test_reading_twice_changes_nothing(self, conn):
        position_id = a_position(conn)
        an_order(conn)

        first = basis_of(conn, position_id)
        second = basis_of(conn, position_id)

        assert first == second
        stored = conn.execute(
            "SELECT stake_tenths FROM parlay_positions WHERE id = ?",
            (position_id,),
        ).fetchone()
        assert int(stored["stake_tenths"]) == STAKE_AT_SENT


class TestThePayloadSaysWhichPriceItIsOn:
    async def test_the_hedge_payload_carries_the_basis_and_the_venue_stake(
        self, conn
    ):
        position_id = a_position(conn)
        an_order(conn)

        async def no_quote(_ticker, *, observed_ms):
            # The real signature (). A stub that did not match it
            # would be exercising the exception branch instead of the
            # no-book one, and the test would pass for the wrong reason.
            raise QuoteUnavailable('no book in this test')

        payload = await hedge.build_payload(
            conn,
            now_ms=NOW_MS,
            max_quote_age_ms=30_000,
            spendable_tenths=None,
            fetch_quote=no_quote,
        )

        row = next(p for p in payload["positions"] if p["id"] == position_id)
        assert row["stake_basis"] == hedge.STAKE_BASIS_VENUE_FILL
        assert row["stake_basis_reason"] is None
        assert row["stake_display"] == "$1.55"

    async def test_a_fallback_position_says_so_on_the_wire(self, conn):
        position_id = a_position(conn)
        an_order(conn, venue_price=None)

        async def no_quote(_ticker, *, observed_ms):
            # The real signature (). A stub that did not match it
            # would be exercising the exception branch instead of the
            # no-book one, and the test would pass for the wrong reason.
            raise QuoteUnavailable('no book in this test')

        payload = await hedge.build_payload(
            conn,
            now_ms=NOW_MS,
            max_quote_age_ms=30_000,
            spendable_tenths=None,
            fetch_quote=no_quote,
        )

        row = next(p for p in payload["positions"] if p["id"] == position_id)
        assert row["stake_basis"] == hedge.STAKE_BASIS_AS_RECORDED
        assert row["stake_basis_reason"] == "no_venue_price"
        assert row["stake_display"] == "$1.64"

    def test_a_raw_row_claims_no_basis_at_all(self, conn):
        """`serialise_position` over an unresolved row reports `None` rather
        than asserting the stake is the venue's. An absence is an absence."""
        position_id = a_position(conn)
        row = next(
            p for p in hedge.open_positions(conn) if int(p["id"]) == position_id
        )
        assessment = hedge.assess(
            row,
            hedge.legs_for(conn, position_id),
            {},
            now_ms=NOW_MS,
            max_quote_age_ms=30_000,
            spendable_tenths=None,
        )

        payload = hedge.serialise_position(
            row, hedge.legs_for(conn, position_id), {}, assessment, now_ms=NOW_MS
        )

        assert payload["stake_basis"] is None
        assert payload["stake_basis_reason"] is None


def _code_strings(source: str, *, inside: str | None = None) -> list[str]:
    """Every string literal in `source` that is not a docstring.

    Over the syntax tree rather than the text, because a text guard over a
    column name pins the NAME and not the claim: a comment saying why the
    column is NOT read would trip it, and a correction trail describing the
    column would trip it too. What matters is whether any code -- a subscript
    key, a SQL fragment -- names it. `inside` narrows the walk to one
    function.
    """
    module = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(module)
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    tree = module
    if inside is not None:
        tree = next(
            node
            for node in ast.walk(module)
            if isinstance(node, ast.FunctionDef) and node.name == inside
        )
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


class TestTheCopyShipsWithTheFix:
    """A caveat naming a condition is falsified by fixing the condition, so
    the sentence and the code go in one commit (`tasks/lessons.md`). E2 --
    the sent-versus-charged stake -- is not a term on a ticket whose stake
    IS the charge, and nothing shown to Joe may say it is."""

    def _lock(self):
        """A `Lock` with one affordable rung. Only `best_available.fee_tenths`
        is read by `estimate_grain`; the rest is the dataclass's shape."""
        from backend.core.hedge import HedgeQuote, Lock, Rung

        rung = Rung(
            contracts=CONTRACTS,
            cost_tenths=2_000,
            fee_tenths=90,
            if_leg_wins_tenths=1_000,
            if_leg_loses_tenths=1_000,
            floor_tenths=1_000,
            fillable=True,
            affordable=True,
        )
        quote = HedgeQuote(
            ticker=LEG_A,
            side="no",
            ask_tenths=500,
            depth_at_ask=100.0,
            observed_ms=NOW_MS,
            status="active",
            leg_ask_tenths=500,
        )
        return Lock(
            quote=quote,
            stake_tenths=STAKE_AT_VENUE,
            return_tenths=RETURN_TENTHS,
            equalising=rung,
            best_available=rung,
            ladder=(rung,),
            depth_contracts=100,
            affordable_contracts=100,
        )

    def test_a_venue_priced_ticket_is_not_told_it_carries_the_sent_price_gap(
        self, conn
    ):
        position_id = a_position(conn)
        an_order(conn)
        row = next(
            p for p in hedge.open_positions(conn) if int(p["id"]) == position_id
        )
        resolved = hedge.position_at_basis(row, basis_of(conn, position_id))

        grain = hedge.estimate_grain(resolved, self._lock())

        assert "price the desk sent" not in grain
        assert "hedge fee here" in grain

    def test_a_ticket_still_on_the_sent_price_is_told_so(self, conn):
        position_id = a_position(conn)
        an_order(conn, venue_price=None)
        row = next(
            p for p in hedge.open_positions(conn) if int(p["id"]) == position_id
        )
        resolved = hedge.position_at_basis(row, basis_of(conn, position_id))

        grain = hedge.estimate_grain(resolved, self._lock())

        assert "price the desk sent" in grain

    def test_the_caveat_no_longer_asserts_the_stake_is_not_kalshis_charge(self):
        note = hedge.NOTES["upper_bound"]
        assert "Kalshi's own fill price where the venue reported one" in note
        assert "the price the desk sent where it did not" in note


class TestWhatThisReadMayNotTouch:
    def test_the_venues_own_fee_column_is_not_read(self):
        """Option B, refused. `venue_avg_fee_dollars` is REAL dollars on the
        same row, its rounding onto integer tenths is undecided, and deciding
        it in passing would be a money change nobody registered. The entry
        fee stays `combo_entry_fee_tenths`' modelled number."""
        source = (ROOT / "backend" / "hedge.py").read_text(encoding="utf-8")
        assert not [
            literal
            for literal in _code_strings(source)
            if "venue_avg_fee_dollars" in literal
        ]

    def test_the_order_read_is_bounded_by_the_open_positions(self):
        """Never a scan of the order history: both halves of the join key are
        an `IN` list built from the open positions, so the read cannot widen
        as `manual_orders` grows."""
        source = (ROOT / "backend" / "hedge.py").read_text(encoding="utf-8")
        assert '"WHERE dry_run = 0 "' in source
        assert "AND ticker IN (" in source
        assert "AND submitted_ms IN (" in source

    def test_the_write_path_still_records_the_price_it_sent(self):
        """The armed path is untouched. `_record_combo_position` writes the
        sent price, as it always did, and the permanent row keeps it."""
        source = (ROOT / "backend" / "api" / "routes.py").read_text(
            encoding="utf-8"
        )
        assert "stake_tenths = contracts * fill_price_tenths" in source
        assert not [
            literal
            for literal in _code_strings(source, inside="_record_combo_position")
            if "venue_" in literal
        ]

    def test_the_route_no_longer_claims_the_stored_stake_is_what_he_paid(self):
        """The killed sentence, gone and not reproduced in its own correction
        trail -- `tasks/lessons.md` 2026-09-16 (tenth): a trail that quotes
        the dead wording re-trips the guard that killed it."""
        source = (ROOT / "backend" / "api" / "routes.py").read_text(
            encoding="utf-8"
        )
        assert "Stake is what he paid" not in source
