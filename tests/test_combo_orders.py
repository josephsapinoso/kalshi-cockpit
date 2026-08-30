"""Resting bids on a combination: the caps, the shard, and the deadline.

**Why this exists.** A combination book is enter-only -- no resting YES bid on
40 of 40 books this repo has read -- so the only way in is to become the offer.
That makes this the first order shape in the project that outlives its request
and can fill while nobody is watching, which is exactly why each of these
guards is here rather than assumed.

**What this establishes.** That the affordability check reads the SHARD's
balance rather than the account total; that an unreadable balance refuses
instead of resolving to zero; that a stake rounds DOWN into contracts; that the
spend ceiling is the same $3 the hand-bet path uses rather than a second larger
one; that a pending row counts against exposure; that the auto-cancel deadline
is the first kickoff and that a missing deadline is never treated as due; and
that a remaining count on a GTC reads as RESTING rather than as unfilled.

**What it does not establish.** That a bid ever fills, what a fill costs in
fees (ADR 0046 is unverified and Kalshi's changelog puts the combo maker
multiplier at 0.5 against this repo's 0.25), or that the venue behaves as the
one 2026-08-30 probe observed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.store import db as store                            # noqa: E402
from backend.store.combo_orders import (                         # noqa: E402
    COMBO_ORDER_MAX_CONTRACTS,
    COMBO_ORDER_MAX_SPEND_TENTHS,
    STATUS_PENDING,
    STATUS_RESTING,
    ComboOrderRefused,
    ShardFunds,
    check_affordable,
    contracts_for_stake,
    due_for_cancel,
    open_exposure_tenths,
    read_shard_funds,
    record_cancel,
    record_intent,
    status_from_response,
    working_orders,
)


#: The payload shape observed on the live account 2026-08-30. Dollars as 4dp
#: strings, one row per shard, the combinations shard holding a penny.
LIVE_BALANCE = {
    "balance": 2141,
    "balance_dollars": "21.4120",
    "balance_breakdown": [
        {"balance": "21.4020", "exchange_index": 0},
        {"balance": "0.0100", "exchange_index": 1},
        {"balance": "0.0000", "exchange_index": 2},
        {"balance": "0.0000", "exchange_index": 3},
    ],
}


@pytest.fixture
def conn(tmp_path):
    c = store.init_db(tmp_path / "combo.db")
    yield c
    c.close()


def _place(conn, **kw):
    defaults = dict(
        now_ms=1_788_000_000_000,
        ticker="KXMVECROSSCATEGORY-SHARD1-ABC",
        card_key="safe",
        legs=[("E1", "M1"), ("E2", "M2")],
        exchange_index=1,
        contracts=4,
        price_tenths=220,
        fair_joint=0.251,
        cancel_after_ms=1_788_000_600_000,
        request_body={"client_order_id": "cid-1", "ticker": "T"},
        dry_run=False,
    )
    defaults.update(kw)
    return record_intent(conn, **defaults)


class TestTheShardIsWhatPaysForIt:
    def test_the_penny_shard_is_read_not_the_account_total(self):
        """$21.41 in the account, $0.01 where the combination trades."""
        funds = read_shard_funds(LIVE_BALANCE, exchange_index=1)
        assert funds.available_tenths == 10          # $0.0100 -> 10 tenths

        whole_account = read_shard_funds(LIVE_BALANCE, exchange_index=0)
        assert whole_account.available_tenths == 21_402

    def test_a_two_cent_bid_is_refused_against_the_penny_shard(self):
        """The live refusal, reproduced before it reaches the venue.

        This is the exact order that came back `insufficient_balance` on
        2026-08-30. The desk's version says WHICH shard and how to fix it,
        because the venue's bare error reads as a bug in the desk.
        """
        funds = read_shard_funds(LIVE_BALANCE, exchange_index=1)
        with pytest.raises(ComboOrderRefused) as caught:
            check_affordable(contracts=1, price_tenths=20, funds=funds)

        detail = caught.value.detail
        assert "shard 1" in detail
        assert "$0.01" in detail
        assert "exchange-indexes" in detail, "the refusal must say how to fix it"

    def test_the_bid_that_fits_inside_the_penny_is_allowed(self):
        """0.5c is what the probe actually got accepted."""
        funds = read_shard_funds(LIVE_BALANCE, exchange_index=1)
        check_affordable(contracts=1, price_tenths=5, funds=funds)

    def test_an_unreadable_balance_refuses_rather_than_reading_as_empty(self):
        """`None`, never `0` -- the repo's standing rule.

        A zero would refuse with "the shard holds $0.00", which is a claim
        about the account. An unparsed payload is not that claim.
        """
        funds = read_shard_funds({"balance_breakdown": "not a list"},
                                 exchange_index=1)
        assert funds.available_tenths is None
        with pytest.raises(ComboOrderRefused) as caught:
            check_affordable(contracts=1, price_tenths=5, funds=funds)
        assert "could not be read" in caught.value.detail

    def test_a_shard_absent_from_the_breakdown_is_unknown_not_empty(self):
        funds = read_shard_funds(LIVE_BALANCE, exchange_index=7)
        assert funds.available_tenths is None


class TestTheCeilings:
    def test_the_spend_cap_matches_the_hand_bet_path(self):
        """One ceiling, not two.

        A second larger ceiling reachable through a new route is the cap being
        raised by accident, which is how a $3 desk becomes a $30 one without
        anyone deciding.
        """
        from backend.store.manual_orders import MANUAL_ORDER_MAX_SPEND_TENTHS

        assert COMBO_ORDER_MAX_SPEND_TENTHS == MANUAL_ORDER_MAX_SPEND_TENTHS

    def test_a_bid_over_the_spend_cap_is_refused(self):
        funds = ShardFunds(exchange_index=1, available_tenths=100_000)
        with pytest.raises(ComboOrderRefused) as caught:
            check_affordable(contracts=100, price_tenths=250, funds=funds)
        assert "ceiling" in caught.value.detail

    def test_a_stake_rounds_down_into_contracts(self):
        """Up would spend more than he typed."""
        assert contracts_for_stake(2000, 220) == 9      # $2.00 at 22c
        assert contracts_for_stake(2000, 251) == 7
        assert contracts_for_stake(100, 220) == 0

    def test_a_stake_that_buys_nothing_says_so(self):
        funds = ShardFunds(exchange_index=1, available_tenths=100_000)
        with pytest.raises(ComboOrderRefused) as caught:
            check_affordable(contracts=0, price_tenths=220, funds=funds)
        assert "no whole contracts" in caught.value.detail

    def test_the_contract_ceiling_still_binds_on_a_cheap_market(self):
        """$3 at a tenth of a cent is thirty thousand contracts."""
        funds = ShardFunds(exchange_index=1, available_tenths=100_000)
        with pytest.raises(ComboOrderRefused) as caught:
            check_affordable(
                contracts=COMBO_ORDER_MAX_CONTRACTS + 1, price_tenths=1,
                funds=funds,
            )
        assert str(COMBO_ORDER_MAX_CONTRACTS) in caught.value.detail


class TestTheRecordIsWrittenBeforeTheRequestLeaves:
    def test_a_pending_row_exists_and_counts_against_exposure(self, conn):
        """An order nobody recorded is an order nobody can cancel."""
        row_id = _place(conn)
        rows = working_orders(conn)
        assert [r["id"] for r in rows] == [row_id]
        assert rows[0]["status"] == STATUS_PENDING
        # 4 contracts at 22c
        assert open_exposure_tenths(conn) == 880

    def test_a_cancelled_row_stops_counting(self, conn):
        row_id = _place(conn)
        record_cancel(conn, row_id, now_ms=1, reduced_by=4.0, reason="test")
        assert open_exposure_tenths(conn) == 0
        assert working_orders(conn) == []

    def test_a_dry_run_never_counts_as_exposure(self, conn):
        _place(conn, dry_run=True, request_body={"client_order_id": "cid-dry"})
        assert open_exposure_tenths(conn) == 0


class TestTheDeadlineIsTheFirstKickoff:
    def test_a_bid_past_its_deadline_is_due(self, conn):
        _place(conn, cancel_after_ms=1_788_000_600_000)
        due = due_for_cancel(conn, now_ms=1_788_000_600_001)
        assert len(due) == 1

    def test_a_bid_before_its_deadline_is_left_alone(self, conn):
        _place(conn, cancel_after_ms=1_788_000_600_000)
        assert due_for_cancel(conn, now_ms=1_788_000_599_999) == []

    def test_a_missing_deadline_is_never_due(self, conn):
        """An unknown deadline is not an expired one.

        Cancelling on a NULL would silently retire orders nobody asked to
        retire -- the failure mode where an absence borrows a present value's
        meaning, which this repo has paid for before.
        """
        _place(conn, cancel_after_ms=None)
        assert due_for_cancel(conn, now_ms=9_999_999_999_999) == []


class TestAGoodTillCancelledRemainderIsAlive:
    def test_a_remainder_reads_as_resting_not_unfilled(self):
        """The one place this differs from the IOC reading, and it matters.

        On an IOC a remaining count means the order died with work undone. On
        a GTC it means the order is working. Reading it as unfilled would drop
        a live order out of the desk's own record.
        """
        status, order_id = status_from_response(
            {"order_id": "abc", "fill_count": "0.00", "remaining_count": "1.00"}
        )
        assert status == STATUS_RESTING
        assert order_id == "abc"

    def test_the_live_probe_response_reads_as_resting(self):
        """Verbatim shape from the 2026-08-30 probe's 201."""
        status, order_id = status_from_response({
            "client_order_id": "cd380140-bedf-432a-b02d-dbceedb88132",
            "fill_count": "0.00",
            "order_id": "01a05460-2430-73a4-a84c-c8063a968d85",
            "remaining_count": "1.00",
            "ts_ms": 1788121982698,
        })
        assert status == STATUS_RESTING
        assert order_id == "01a05460-2430-73a4-a84c-c8063a968d85"

    def test_an_unreadable_response_is_rejected_not_assumed_resting(self):
        status, _ = status_from_response("not a dict")
        assert status != STATUS_RESTING
