"""The poller that mirrors Joe's hand bets before the venue drops them.

**Why these payloads are synthetic, and why that is a decision rather than a
shortcut.** CLAUDE.md requires wire-format tests to load captured payloads --
and the captures exist (`data/captures/portfolio_*.json`, taken 2026-08-18) --
but they are a real account's trading history and this repo is public, so they
are gitignored and cannot ship. This is the ADR 0035 position: synthetic
payloads carrying the **observed** field set, plus a shape assertion, plus a
local-only test at the bottom that parses the real captures whenever they are
present on disk. Every field name below was read off the live wire, not the
docs.

**What this establishes:** that both parsers read the observed shape into the
repo's units; that refusal is None and never zero; that a poll failure leaves a
`poll_log` row; that polling twice writes nothing twice; and that a polled fill
carries `source='venue_hand'` and therefore cannot reach the gate (ADR 0043).

**What it does not establish:** that the mirror is complete (a position opened
and closed between polls is gone), anything about the fee model's correctness,
or anything about estimate matching -- which is analysis, not ingest.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.core.fees import FEE_MATCH_TOLERANCE_DOLLARS, calculate_fee
from backend.gate import _fee_model_verified
from backend.notify.alerts import Alerter
from backend.portfolio_poll import (
    ParsedFill,
    ParsedSettlement,
    parse_balance_tenths,
    parse_fill,
    parse_portfolio_value_tenths,
    parse_settlement,
    backfill_settlement_taker,
    poll_portfolio,
    poll_portfolio_forever,
    poll_settlements,
    poll_positions,
    predict_fill_fee,
    reconcile_fill,
)
from backend.store import db


# The field set observed on the live wire, 2026-08-18. If Kalshi renames one,
# the local-captures test at the bottom is what notices; these constants keep
# the synthetic rows honest about which shape they claim to be.
SETTLEMENT_FIELDS = {
    "event_ticker", "fee_cost", "market_result", "no_count_fp",
    "no_total_cost_dollars", "revenue", "settled_time", "ticker", "value",
    "yes_count_fp", "yes_total_cost_dollars",
}
FILL_FIELDS = {
    "action", "book_side", "count_fp", "created_time", "fee_cost", "fill_id",
    "is_taker", "market_ticker", "no_price_dollars", "order_id",
    "outcome_side", "side", "subaccount_number", "ticker", "trade_id", "ts",
    "yes_price_dollars",
}


def settlement_row(**overrides) -> dict:
    """A synthetic settlement in the observed shape. Values from the real
    KXMLBGAME 11.27-contract row, the one whose count is fractional."""
    row = {
        "ticker": "KXMLBGAME-26AUG102210KCLAD-KC",
        "event_ticker": "KXMLBGAME-26AUG102210KCLAD",
        "market_result": "no",
        "settled_time": "2026-08-11T02:37:35.803785Z",
        "yes_count_fp": "11.27",
        "no_count_fp": "0.00",
        "yes_total_cost_dollars": "3.042900",
        "no_total_cost_dollars": "0.000000",
        "fee_cost": "0.077800",
        "revenue": 0,
        "value": 0,
    }
    row.update(overrides)
    assert set(row) == SETTLEMENT_FIELDS, "synthetic row drifted from the observed shape"
    return row


def fill_row(**overrides) -> dict:
    """A synthetic fill in the observed shape. Values from the real 1c fill --
    chosen because its yes/no prices are maximally asymmetric (1c vs 99c), so
    reading the wrong side's price cannot pass by coincidence."""
    row = {
        "fill_id": "438c7362-4665-4e54-ff12-b6759e604844",
        "trade_id": "438c7362-4665-4e54-ff12-b6759e604844",
        "order_id": "a40b142b-b213-436e-913b-d2844765e70a",
        "ticker": "KXTOPUSAGEAI-26AUG10-ANTH",
        "market_ticker": "KXTOPUSAGEAI-26AUG10-ANTH",
        "side": "yes",
        "action": "buy",
        "book_side": "bid",
        "outcome_side": "yes",
        "count_fp": "10.00",
        "yes_price_dollars": "0.0100",
        "no_price_dollars": "0.9900",
        "fee_cost": "0.007000",
        "is_taker": True,
        "created_time": "2026-08-17T02:20:38.000097Z",
        "ts": 1786933238,
        "subaccount_number": 0,
    }
    row.update(overrides)
    assert set(row) == FILL_FIELDS, "synthetic row drifted from the observed shape"
    return row


class TestParseSettlement:
    def test_the_fractional_count_row_parses_exactly(self):
        parsed = parse_settlement(settlement_row())

        assert parsed == ParsedSettlement(
            ticker="KXMLBGAME-26AUG102210KCLAD-KC",
            event_ticker="KXMLBGAME-26AUG102210KCLAD",
            market_result="no",
            settled_ms=1786415855803,
            side="yes",
            contracts=11.27,
            # 3.0429 / 11.27 = 27.0c exactly at tenths resolution -- the
            # average entry the venue's own pair implies.
            entry_price_tenths=270,
            fee_cost_tenths=78,
        )

    def test_a_no_side_position_reads_the_no_pair(self):
        parsed = parse_settlement(settlement_row(
            yes_count_fp="0.00", yes_total_cost_dollars="0.000000",
            no_count_fp="10.00", no_total_cost_dollars="1.600000",
        ))

        assert parsed is not None
        assert (parsed.side, parsed.contracts, parsed.entry_price_tenths) == (
            "no", 10.0, 160,
        )

    @pytest.mark.parametrize("overrides, reason", [
        ({"ticker": None}, "no ticker"),
        ({"settled_time": None}, "no settled time"),
        ({"settled_time": "not-a-time"}, "unreadable settled time"),
        ({"yes_count_fp": "0.00"}, "no position on either side"),
        ({"yes_count_fp": "garbage", "no_count_fp": "also garbage"},
         "both counts unreadable"),
    ])
    def test_a_row_that_cannot_carry_a_position_is_refused(self, overrides, reason):
        """None, never a half-parsed row. A refusal is countable; a guess is not."""
        assert parse_settlement(settlement_row(**overrides)) is None, reason

    def test_an_unreadable_cost_refuses_the_price_and_keeps_the_row(self):
        """The position is real even when its price is not readable."""
        parsed = parse_settlement(settlement_row(yes_total_cost_dollars="garbage"))

        assert parsed is not None
        assert parsed.entry_price_tenths is None, "never 0, never invented"


class TestParseFill:
    def test_the_one_cent_fill_parses_exactly(self):
        parsed = parse_fill(fill_row())

        assert parsed == ParsedFill(
            kalshi_fill_id="438c7362-4665-4e54-ff12-b6759e604844",
            ticker="KXTOPUSAGEAI-26AUG10-ANTH",
            filled_ms=1786933238000,
            count=10.0,
            price_tenths=10,
            is_taker=True,
            fee_actual=0.007,
            # v18 (D3): the venue's own order id, present on every captured
            # fill and now kept -- the join key from a portal-placed manual
            # order to the fill that answered it.
            venue_order_id="a40b142b-b213-436e-913b-d2844765e70a",
        )

    def test_a_no_fill_reads_the_no_price(self):
        """1c vs 99c: the wrong side's price cannot pass by coincidence."""
        parsed = parse_fill(fill_row(side="no"))

        assert parsed is not None
        assert parsed.price_tenths == 990

    def test_the_quarter_contract_fill_survives(self):
        """The 0.27 that INTEGER storage would have zeroed."""
        parsed = parse_fill(fill_row(count_fp="0.27"))

        assert parsed is not None
        assert parsed.count == pytest.approx(0.27)

    def test_the_precise_timestamp_wins_when_both_disagree(self):
        """The real fill's created_time and ts agree to the millisecond, so
        agreement proves nothing about which was read. Force them apart."""
        parsed = parse_fill(fill_row(ts=1_111_111_111))

        assert parsed is not None
        assert parsed.filled_ms == 1786933238000, "created_time, not ts"

    def test_the_coarse_timestamp_is_the_fallback(self):
        parsed = parse_fill(fill_row(created_time=None, ts=1_786_000_000))

        assert parsed is not None
        assert parsed.filled_ms == 1_786_000_000_000, "ts seconds, promoted to ms"

    @pytest.mark.parametrize("overrides, reason", [
        ({"fill_id": None}, "no identity, no idempotency"),
        ({"side": "maybe"}, "side is neither yes nor no"),
        ({"count_fp": "0.00"}, "a zero-contract fill is not a fill"),
        ({"yes_price_dollars": "garbage"}, "unreadable price"),
        ({"is_taker": None}, "the maker/taker flag is what the fee question turns on"),
        ({"created_time": None, "ts": None}, "no time at all"),
    ])
    def test_refusals(self, overrides, reason):
        assert parse_fill(fill_row(**overrides)) is None, reason


class TestBalanceParsing:
    def test_the_dollars_string_is_read_and_the_cents_integer_is_not(self):
        """Both observed side by side: 2065 vs "20.6583". The integer drops
        0.83c -- the deci-cent error, in a wallet."""
        payload = {"balance": 2065, "balance_dollars": "20.6583",
                   "portfolio_value": 0, "updated_ts": 1787022429}

        assert parse_balance_tenths(payload) == 20658

    def test_a_missing_dollars_field_is_none_and_never_the_integer(self):
        assert parse_balance_tenths({"balance": 2065}) is None

    def test_portfolio_value_is_accepted_only_at_zero(self):
        """Zero is zero in every candidate unit. Anything else waits for the
        unit to be pinned against a real position list."""
        assert parse_portfolio_value_tenths({"portfolio_value": 0}) == 0
        assert parse_portfolio_value_tenths({"portfolio_value": 1234}) is None
        assert parse_portfolio_value_tenths({}) is None


class FakeClient:
    """The four portfolio methods, returning canned payloads or raising."""

    def __init__(self, *, settlements=None, fills=None, positions=None,
                 balance=None, fail=()):
        self._settlements = settlements if settlements is not None else []
        self._fills = fills if fills is not None else []
        self._positions = positions if positions is not None else []
        self._balance = balance if balance is not None else {
            "balance": 2065, "balance_dollars": "20.6583", "portfolio_value": 0,
        }
        self._fail = set(fail)

    async def settlements(self, *, limit=200):
        if "settlements" in self._fail:
            raise RuntimeError("boom settlements")
        return self._settlements

    async def fills(self, *, limit=200):
        if "fills" in self._fail:
            raise RuntimeError("boom fills")
        return self._fills

    async def positions(self):
        if "positions" in self._fail:
            raise RuntimeError("boom positions")
        return self._positions

    async def balance(self):
        if "balance" in self._fail:
            raise RuntimeError("boom balance")
        return self._balance


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "cockpit.db")
    yield c
    c.close()


class TestPollPortfolio:
    async def test_one_pass_mirrors_everything_and_logs_every_endpoint(self, conn):
        client = FakeClient(settlements=[settlement_row()], fills=[fill_row()])

        summary = await poll_portfolio(conn, client, now_ms=1_787_100_000_000)

        assert summary["settlements"] == {"seen": 1, "new": 1, "refused": 0,
                                          "taker_backfilled": 0, "taker_mixed": 0}
        assert summary["fills"] == {"seen": 1, "new": 1, "refused": 0}
        assert summary["balance"] == {"balance_tenths": 20658}
        log = {
            r["endpoint"]: (r["ok"], r["row_count"])
            for r in conn.execute("SELECT endpoint, ok, row_count FROM poll_log")
        }
        assert log == {
            "settlements": (1, 1), "fills": (1, 1),
            "positions": (1, 0), "balance": (1, 1),
        }

    async def test_polling_twice_writes_nothing_twice(self, conn):
        """Idempotency is what makes a 12-hour cadence safe to overlap."""
        client = FakeClient(settlements=[settlement_row()], fills=[fill_row()])
        await poll_portfolio(conn, client, now_ms=1)

        summary = await poll_portfolio(conn, client, now_ms=2)

        assert summary["settlements"]["new"] == 0
        assert summary["fills"]["new"] == 0
        assert conn.execute("SELECT COUNT(*) FROM venue_settlements").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0] == 1
        # The balance is a time series, not a mirror: two polls, two rows.
        assert conn.execute(
            "SELECT COUNT(*) FROM venue_balance_snapshots"
        ).fetchone()[0] == 2

    async def test_a_failed_endpoint_is_logged_and_the_rest_still_run(self, conn):
        """A settlements outage must not blind the balance record."""
        client = FakeClient(fills=[fill_row()], fail={"settlements"})

        summary = await poll_portfolio(conn, client, now_ms=1)

        assert "FAILED" in summary["settlements"]
        row = conn.execute(
            "SELECT ok, row_count, error FROM poll_log WHERE endpoint='settlements'"
        ).fetchone()
        assert (row["ok"], row["row_count"]) == (0, None), (
            "a failure recorded as 0 rows reads as a quiet week"
        )
        assert "boom settlements" in row["error"]
        assert summary["fills"]["new"] == 1
        assert summary["balance"]["balance_tenths"] == 20658

    async def test_a_refused_row_is_counted_and_the_good_ones_still_land(self, conn):
        client = FakeClient(
            settlements=[settlement_row(),
                         settlement_row(ticker=None)],
        )

        summary = await poll_portfolio(conn, client, now_ms=1)

        assert summary["settlements"] == {"seen": 2, "new": 1, "refused": 1,
                                          "taker_backfilled": 0, "taker_mixed": 0}

    async def test_a_polled_fill_is_venue_hand_and_cannot_reach_the_gate(self, conn):
        """The ADR 0043 seam, exercised end to end through the real poller.

        The fill carries a real fee_actual, which is exactly what would have
        flipped `_fee_model_verified` before the filter landed.
        """
        await poll_portfolio(conn, FakeClient(fills=[fill_row()]), now_ms=1)

        assert conn.execute(
            "SELECT source FROM fills"
        ).fetchone()["source"] == "venue_hand"
        condition = _fee_model_verified(conn)
        assert condition.met is False
        assert "no fills yet" in condition.detail

    async def test_a_polled_fill_predicts_a_fee_beside_the_actual(self, conn):
        """`fee_predicted` is NOT NULL by schema, and populating it is the
        whole point: a real fee beside a predicted one is the comparison H4
        has been waiting for -- computed off-gate, by its own harness."""
        await poll_portfolio(conn, FakeClient(fills=[fill_row()]), now_ms=1)

        row = conn.execute("SELECT fee_actual, fee_predicted FROM fills").fetchone()
        assert row["fee_actual"] == pytest.approx(0.007)
        assert row["fee_predicted"] > 0

    async def test_an_mlb_fills_predicted_fee_stays_on_the_flat_model(
        self, conn
    ):
        """ADR 0058's tripwire, half one. `fills.fee_predicted` must keep
        being written under the flat 0.070 model even on a series whose true
        multiplier is 0.5 -- because `_fee_model_verified`
        (`backend/gate.py`) compares this exact column against `fee_actual`,
        and moving it to per-series would decide ADR 0043's open hand-fills
        question in the permissive direction as a side effect. (Half two --
        the `source = 'engine'` filter -- is pinned by
        `tests/test_gate_counts_engine_fills_only.py`.)

        Arithmetic by hand: 10 contracts at 1c taker, flat model
        ceil(0.07*10*0.01*0.99) at $0.0001 = $0.0070; a per-series MLB model
        would predict $0.0035. If this fails, read ADR 0058 before touching
        the assertion.

        Verified red by passing `fee_multiplier=0.5` into the poller's
        `calculate_fee` call.
        """
        mlb = fill_row(
            fill_id="adr58", trade_id="adr58", order_id="adr58",
            ticker="KXMLBGAME-26AUG20TEST-NYY",
            market_ticker="KXMLBGAME-26AUG20TEST-NYY",
        )
        await poll_portfolio(conn, FakeClient(fills=[mlb]), now_ms=1)

        row = conn.execute(
            "SELECT fee_predicted, fee_model_used FROM fills"
        ).fetchone()
        assert row["fee_predicted"] == pytest.approx(0.0070)
        assert row["fee_model_used"] == "model_a_deci"

    async def test_positions_log_the_failure_as_well_as_the_success(
        self, conn
    ):
        """`poll_positions` matches its three siblings on the seam that
        matters: **a failed attempt leaves a row.**

        `poll_log` is the registration's only evidence of which polls
        happened, and every retention tripwire is a gap between successive
        SUCCESSFUL rows. A failure that writes nothing is not neutral -- it
        is invisible, and reads exactly like a quiet evening in which nothing
        was bet. `bets.open_positions` filters on `ok = 1`, so the failure
        row never serves a count; it exists so the gap can be attributed.
        """
        client = FakeClient(fail={"positions"})

        result = await poll_positions(conn, client, now_ms=4_242)
        conn.commit()

        assert str(result).startswith("FAILED:")
        row = conn.execute(
            "SELECT polled_ms, ok, row_count, error FROM poll_log "
            "WHERE endpoint = 'positions'"
        ).fetchone()
        assert row is not None, (
            "a failed positions poll must leave a row -- silence is "
            "indistinguishable from a night with no bets"
        )
        assert (row["polled_ms"], row["ok"], row["row_count"]) == (4_242, 0, None)
        assert "boom positions" in row["error"]

    async def test_positions_write_but_do_not_commit_like_their_siblings(
        self, conn
    ):
        """The shape `poll_portfolio` depends on: the function writes inside
        the caller's transaction and the CALLER commits, so a mirror pass is
        one transaction and not four."""
        await poll_positions(
            conn, FakeClient(positions=[{"ticker": "A"}]), now_ms=7
        )
        conn.rollback()
        assert conn.execute(
            "SELECT COUNT(*) FROM poll_log WHERE endpoint = 'positions'"
        ).fetchone()[0] == 0, "poll_positions must not commit on its own"

    async def test_positions_are_counted_and_mirrored_verbatim(self, conn):
        """This test used to be `test_positions_are_counted_never_parsed`,
        docstring *"The shape has never been observed; a parser would be
        imagined."* The shape was observed on 2026-08-30
        (`tests/test_rest.py::OBSERVED_POSITION_ROW`) and schema v33 mirrors
        the rows (`tests/test_venue_positions.py` carries the wire-shape
        tests). What survives from the old claim: the count in `poll_log`
        is still `len(rows)`, and a row that will not parse is still never
        refused whole -- its text is kept and its derived columns are NULL.
        """
        client = FakeClient(positions=[{"never": "observed"}])

        summary = await poll_portfolio(conn, client, now_ms=1)

        assert summary["positions"] == {
            "seen": 1, "stored": 1, "exposure_unreadable": 1,
        }
        mirrored = conn.execute(
            "SELECT ticker, exposure_tenths, contracts, side "
            "FROM venue_positions"
        ).fetchall()
        assert [tuple(r) for r in mirrored] == [(None, None, None, None)]

    async def test_a_mirror_pass_carries_the_matchers_own_summary(self, conn):
        """The wiring guard on `run_match_pass`'s only production call.

        The matcher writes `outcome_win`, a registered variable, and reaches
        production through exactly one line -- the mirror branch of
        `poll_portfolio`. Before this test, stubbing `run_match_pass` to an
        async no-op left every portfolio-poll test green: the wiring was
        unguarded. So this asserts the mirror summary carries the *matcher's
        own* summary shape, not merely that the key exists -- a no-op stub
        puts `None` there and goes red.

        Verified red by that exact mutation on 2026-08-29: `run_match_pass`
        redefined as an async no-op made this fail while the rest of the
        file stayed green.
        """
        summary = await poll_portfolio(conn, FakeClient(), now_ms=1)

        match = summary["match"]
        assert isinstance(match, dict), (
            f"the mirror did not run the real matcher: {match!r}"
        )
        assert {
            "ensure", "first_seen_upgraded", "match", "positions", "outcomes",
        } <= set(match), match

    async def test_a_matcher_failure_lands_in_poll_log(self, conn, monkeypatch):
        """The matcher joins its siblings on the seam that matters.

        Every endpoint's failure leaves a `poll_log` row; until 2026-08-29 a
        matcher failure left only a log line, and `flyctl logs` is lossy --
        a matcher throwing on every mirror for a week read exactly like a
        healthy one. The rollback before the read is the durability check:
        the failure row must be committed, not riding an open transaction
        that the next crash discards.
        """
        from backend import estimate_match

        async def exploding(conn, source, *, now_ms):
            raise RuntimeError("boom matcher")

        monkeypatch.setattr(estimate_match, "run_match_pass", exploding)

        summary = await poll_portfolio(conn, FakeClient(), now_ms=4_243)

        assert summary["match"] == "FAILED: boom matcher"
        conn.rollback()
        row = conn.execute(
            "SELECT polled_ms, ok, row_count, error FROM poll_log "
            "WHERE endpoint = 'match'"
        ).fetchone()
        assert row is not None, (
            "a failed match pass must leave a committed row -- a log line "
            "alone is invisible once flyctl drops it"
        )
        assert (row["polled_ms"], row["ok"], row["row_count"]) == (4_243, 0, None)
        assert "boom matcher" in row["error"]


def _settlement(conn, ticker, *, settled_ms=1_000, is_taker=None):
    conn.execute(
        "INSERT INTO venue_settlements (ticker, market_result, settled_ms, "
        "side, contracts, entry_price_tenths, fee_cost_tenths, is_taker) "
        "VALUES (?, 'yes', ?, 'yes', 4, 375, 66, ?)",
        (ticker, settled_ms, is_taker),
    )


def _fill(conn, ticker, fill_id, *, is_taker, source="venue_hand"):
    conn.execute(
        "INSERT INTO fills (kalshi_fill_id, ticker, filled_ms, count, "
        "price_tenths, is_taker, fee_actual, fee_predicted, fee_model_used, "
        "source) VALUES (?, ?, 1, 4, 375, ?, 0.0657, 0.0657, 'model_a_deci', ?)",
        (fill_id, ticker, 1 if is_taker else 0, source),
    )


class TestSettlementTakerIsWrittenFromTheFills:
    """The column had ten siblings in the INSERT and no writer of its own.

    Live, 2026-09-09: `venue_settlements.is_taker` was NULL on 90 of 90 rows
    while 62 of 62 `KXMVE` settlement tickers had a matching `fills` row
    carrying the venue's own boolean. `backend/bets.py` selects the column and
    puts it on the `/bets` screen, so the screen said "unknown" about a fact
    the next table over had held since 2026-08-18.
    """

    def test_a_taker_position_gets_is_taker_1(self, conn):
        _settlement(conn, "KXMVE-A")
        _fill(conn, "KXMVE-A", "f1", is_taker=True)

        assert backfill_settlement_taker(conn) == {"written": 1, "mixed": 0}
        assert conn.execute(
            "SELECT is_taker FROM venue_settlements WHERE ticker = 'KXMVE-A'"
        ).fetchone()[0] == 1

    def test_a_maker_position_gets_is_taker_0_not_left_null(self, conn):
        _settlement(conn, "KXMVE-B")
        _fill(conn, "KXMVE-B", "f2", is_taker=False)

        assert backfill_settlement_taker(conn) == {"written": 1, "mixed": 0}
        assert conn.execute(
            "SELECT is_taker FROM venue_settlements WHERE ticker = 'KXMVE-B'"
        ).fetchone()[0] == 0

    def test_a_position_whose_fills_disagree_stays_null(self, conn):
        """Mixed has no single answer, and a majority would be an invention."""
        _settlement(conn, "KXMVE-C")
        _fill(conn, "KXMVE-C", "f3", is_taker=True)
        _fill(conn, "KXMVE-C", "f4", is_taker=True)
        _fill(conn, "KXMVE-C", "f5", is_taker=False)

        assert backfill_settlement_taker(conn) == {"written": 0, "mixed": 1}
        assert conn.execute(
            "SELECT is_taker FROM venue_settlements WHERE ticker = 'KXMVE-C'"
        ).fetchone()[0] is None

    def test_a_position_with_no_mirrored_fill_stays_null(self, conn):
        """No evidence resolves to None, never to 0."""
        _settlement(conn, "KXMVE-D")

        assert backfill_settlement_taker(conn) == {"written": 0, "mixed": 0}
        assert conn.execute(
            "SELECT is_taker FROM venue_settlements WHERE ticker = 'KXMVE-D'"
        ).fetchone()[0] is None

    def test_an_engine_fill_counts_too(self, conn):
        """`refine_first_seen` filters to `venue_hand`; this must not.

        A position filled partly by the order path and partly by hand is one
        position, and answering maker/taker from a subset of its fills is the
        same substitution the mixed case refuses.
        """
        _settlement(conn, "KXMVE-E")
        _fill(conn, "KXMVE-E", "f6", is_taker=True, source="engine")

        assert backfill_settlement_taker(conn) == {"written": 1, "mixed": 0}
        assert conn.execute(
            "SELECT is_taker FROM venue_settlements WHERE ticker = 'KXMVE-E'"
        ).fetchone()[0] == 1

    def test_a_second_pass_rewrites_nothing(self, conn):
        """Idempotent: only rows still NULL are ever considered."""
        _settlement(conn, "KXMVE-F")
        _fill(conn, "KXMVE-F", "f7", is_taker=True)
        backfill_settlement_taker(conn)

        assert backfill_settlement_taker(conn) == {"written": 0, "mixed": 0}

    def test_an_already_written_flag_is_never_overwritten(self, conn):
        """History, not a derived view: a row already answered is left alone."""
        _settlement(conn, "KXMVE-G", is_taker=0)
        _fill(conn, "KXMVE-G", "f8", is_taker=True)

        assert backfill_settlement_taker(conn) == {"written": 0, "mixed": 0}
        assert conn.execute(
            "SELECT is_taker FROM venue_settlements WHERE ticker = 'KXMVE-G'"
        ).fetchone()[0] == 0

    async def test_the_settlements_poll_writes_it_without_being_asked(self, conn):
        """The reachable caller: this runs on the five-minute fast branch.

        `poll_settlements` <- `poll_portfolio_forever` <- `scripts/run_loop.py`.
        A backfill nothing invokes is not a fix.
        """
        row = settlement_row()
        client = FakeClient(settlements=[row])
        _fill(conn, row["ticker"], "f9", is_taker=True)

        result = await poll_settlements(conn, client, now_ms=1)

        assert result["taker_backfilled"] == 1, result
        assert conn.execute(
            "SELECT is_taker FROM venue_settlements WHERE ticker = ?",
            (row["ticker"],),
        ).fetchone()[0] == 1


class TestPollPortfolioForever:
    """The long-running task the chain runner starts beside itself.

    The cadence is registered (mirror 12h, balance 5min), so these tests drive
    the loop on a fake clock rather than trusting the intervals by reading
    them: the schedule is behaviour, and behaviour is what regresses.
    """

    @staticmethod
    def _clockwork(step_s: float):
        """A fake clock and a sleep that advances it. No real time passes."""
        state = {"now": 1_787_000_000.0}

        def clock():
            return state["now"]

        async def sleep(_seconds):
            state["now"] += step_s

        return clock, sleep

    async def test_the_first_cycle_is_a_full_mirror(self, tmp_path):
        """A restart re-anchors the record immediately, not 12 hours later --
        restarts are exactly when a gap is most likely to be open."""
        path = tmp_path / "cockpit.db"
        db.init_db(path).close()
        clock, sleep = self._clockwork(step_s=300)

        await poll_portfolio_forever(
            path, FakeClient(settlements=[settlement_row()], fills=[fill_row()]),
            sleep=sleep, clock=clock, max_cycles=1,
        )

        conn = db.open_db(path, read_only=True)
        assert conn.execute("SELECT COUNT(*) FROM venue_settlements").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0] == 1
        conn.close()

    async def test_the_balance_runs_every_cycle_and_the_mirror_waits_12h(
        self, tmp_path, monkeypatch
    ):
        """Every venue endpoint runs every cycle; the MIRROR still waits 12h.

        Balance, fills, settlements and -- since 2026-08-29 -- positions all
        ride the 5-minute clock, because each has a consumer that refuses on
        a stale read. What stays on `MIRROR_INTERVAL_S` is `poll_portfolio`
        itself, and the only thing inside it the fast branch does not also do
        is `run_match_pass`, which writes a registered variable.

        The mirror is counted by spying on `poll_portfolio` rather than by
        counting 'positions' rows, because positions are no longer the
        mirror's fingerprint -- a test that counted them would now go green
        on a loop that had stopped mirroring altogether.
        """
        from backend import portfolio_poll as module

        path = tmp_path / "cockpit.db"
        db.init_db(path).close()
        # 5-minute steps; 145 cycles spans just over 12 hours, so the full
        # mirror should fire exactly twice: cycle 1 and the first cycle past
        # 12h.
        clock, sleep = self._clockwork(step_s=300)

        real_mirror = module.poll_portfolio
        mirrors = {"n": 0}

        async def counting_mirror(conn, client, *, now_ms, **kwargs):
            mirrors["n"] += 1
            return await real_mirror(conn, client, now_ms=now_ms, **kwargs)

        monkeypatch.setattr(module, "poll_portfolio", counting_mirror)

        await poll_portfolio_forever(
            path, FakeClient(), sleep=sleep, clock=clock, max_cycles=146,
        )

        conn = db.open_db(path, read_only=True)
        balances = conn.execute(
            "SELECT COUNT(*) FROM venue_balance_snapshots"
        ).fetchone()[0]
        settlements = conn.execute(
            "SELECT COUNT(*) FROM poll_log WHERE endpoint = 'settlements'"
        ).fetchone()[0]
        positions = conn.execute(
            "SELECT COUNT(*) FROM poll_log WHERE endpoint = 'positions'"
        ).fetchone()[0]
        conn.close()
        assert balances == 146, "the balance is every cycle, mirror included"
        assert settlements == 146, (
            "settlements ride the fast cadence (ADR 0064): the kill switch's "
            "producer refuses on a mirror older than 30 minutes"
        )
        assert positions == 146, (
            "positions ride the fast cadence too (2026-08-29): the "
            "open-positions count refuses on a read older than 30 minutes, "
            "and a hand bet placed at 8pm must not wait for the next mirror"
        )
        assert mirrors["n"] == 2, (
            "cycle 1, then the first cycle past the 12h mark -- "
            "MIRROR_INTERVAL_S is untouched, so run_match_pass stays on it"
        )

    async def test_endpoint_failures_are_absorbed_and_logged_per_cycle(
        self, tmp_path
    ):
        """The per-endpoint catches inside the poll functions, driven from the
        loop. Note what this does NOT test: nothing here reaches the loop's
        own catch-all, because the poll functions catch everything they call.
        The test below is the one that exercises the outer guard."""
        path = tmp_path / "cockpit.db"
        db.init_db(path).close()
        clock, sleep = self._clockwork(step_s=300)
        client = FakeClient(fail={"settlements", "fills", "positions", "balance"})

        await poll_portfolio_forever(
            path, client, sleep=sleep, clock=clock, max_cycles=3,
        )

        conn = db.open_db(path, read_only=True)
        failures = conn.execute(
            "SELECT COUNT(*) FROM poll_log WHERE ok = 0"
        ).fetchone()[0]
        conn.close()
        # Cycle 1 is a mirror (4 endpoints fail); cycles 2-3 are the fast
        # cadence, which is now balance AND fills (2026-08-21 ruling) AND
        # settlements (ADR 0064) AND positions (2026-08-29) -- four failures
        # each, so 4 + 4 + 4.
        assert failures == 12, "every failed attempt left a row, and the loop ran on"
        conn = db.open_db(path, read_only=True)
        by_endpoint = dict(
            conn.execute(
                "SELECT endpoint, COUNT(*) FROM poll_log WHERE ok = 0 "
                "GROUP BY endpoint"
            )
        )
        conn.close()
        assert by_endpoint == {
            "balance": 3, "fills": 3, "positions": 3, "settlements": 3,
        }, (
            "each endpoint failed once per cycle and each failure left its "
            "own row -- a pooled 12 is also reached by one endpoint failing "
            "twelve times while three write nothing at all"
        )

    async def test_a_failure_that_escapes_the_poll_does_not_kill_the_loop(
        self, tmp_path, monkeypatch
    ):
        """The loop's OWN catch-all, which the per-endpoint catches shadow.

        The poll functions catch every venue error, so the only things that
        reach the outer guard are the ones nobody predicted -- a DB error, a
        bug. Simulated by making `poll_balance` itself raise: the loop must
        absorb it and keep cycling, because the registration's gap tripwires
        read `poll_log` and only a surviving loop keeps writing it. The first
        mutation draft of this file did not test this seam at all and the
        catch-all was provably decoration; this is the repair.
        """
        from backend import portfolio_poll as module

        path = tmp_path / "cockpit.db"
        db.init_db(path).close()
        clock, sleep = self._clockwork(step_s=300)
        calls = {"n": 0}

        async def exploding_balance(conn, client, *, now_ms):
            calls["n"] += 1
            raise RuntimeError("nobody predicted this")

        monkeypatch.setattr(module, "poll_balance", exploding_balance)

        # Must return normally: cycle 1 is a mirror (which also calls the
        # exploding balance, inside poll_portfolio), cycles 2-3 are the
        # balance-only path raising straight into the loop body.
        await poll_portfolio_forever(
            path, FakeClient(), sleep=sleep, clock=clock, max_cycles=3,
        )

        assert calls["n"] == 3, "the loop kept attempting after each escape"

    async def test_the_matcher_runs_on_the_mirror_and_never_on_the_fast_cycle(
        self, tmp_path, monkeypatch
    ):
        """`summary["match"]` exists on a mirror cycle and nowhere else.

        The matcher writes `outcome_win`, a registered variable, which is why
        it alone stays on `MIRROR_INTERVAL_S` -- amendment A7's analysis
        clock -- while fills, settlements and positions all moved to the fast
        cadence. Both directions have to be pinned: a matcher that stops
        running on the mirror silently freezes the registered record, and a
        matcher that starts running on the fast cadence is an unbounded
        number of implicit looks at a stopping arm. Three cycles at 300s:
        cycle 1 is the only mirror, so the real matcher must run exactly once.
        """
        from backend import estimate_match

        path = tmp_path / "cockpit.db"
        db.init_db(path).close()
        clock, sleep = self._clockwork(step_s=300)
        calls = {"n": 0}
        real = estimate_match.run_match_pass

        async def counting(conn, source, *, now_ms):
            calls["n"] += 1
            return await real(conn, source, now_ms=now_ms)

        monkeypatch.setattr(estimate_match, "run_match_pass", counting)

        await poll_portfolio_forever(
            path, FakeClient(), sleep=sleep, clock=clock, max_cycles=3,
        )

        assert calls["n"] == 1, (
            "cycle 1 is the only mirror in fifteen minutes; the matcher must "
            "run there and must not ride the fast cadence -- that would be "
            "re-reading a registered variable on an operational clock"
        )

    async def test_a_mirror_cycle_is_distinguishable_from_a_fast_one(
        self, tmp_path
    ):
        """Which branch ran must be readable from `poll_log`, not inferred.

        Both branches stamp their rows with the same cycle `now_ms` and name
        the same four endpoints, so until 2026-09-01 nothing in the data told
        the 12-hour mirror from the 5-minute cadence. §7 of
        `docs/measurements/2026-09-01-lock-holder-attribution-result.md` needs
        exactly that split before a forward look can have a decision rule: a
        post-fix lock burst following a MIRROR cycle is explained by the
        matcher's own loop and would not refute ADR 0091.

        Three cycles at 300s: cycle 1 is the only mirror. The marker must land
        on that cycle's `polled_ms` -- a marker on a stamp of its own would be
        a fifth cycle to `lock-attribution`, which groups by DISTINCT
        `polled_ms`, and would corrupt the very join it exists to serve.
        """
        path = tmp_path / "cockpit.db"
        db.init_db(path).close()
        clock, sleep = self._clockwork(step_s=300)

        await poll_portfolio_forever(
            path, FakeClient(), sleep=sleep, clock=clock, max_cycles=3,
        )

        conn = db.open_db(path, read_only=True)
        markers = conn.execute(
            "SELECT polled_ms, ok, row_count FROM poll_log "
            "WHERE endpoint = 'mirror' ORDER BY polled_ms"
        ).fetchall()
        cycles = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT polled_ms FROM poll_log ORDER BY polled_ms"
            )
        ]
        conn.close()

        assert len(markers) == 1, (
            "one marker per mirror cycle and none on a fast cycle; cycle 1 is "
            "the only mirror in fifteen minutes"
        )
        assert markers[0]["polled_ms"] == cycles[0], (
            "the marker must share its cycle's stamp -- a stamp of its own "
            "would read as an extra cycle to `lock-attribution`"
        )
        assert len(cycles) == 3, (
            "three cycles, not four: the marker added a row, not a stamp"
        )
        assert markers[0]["ok"] == 1 and markers[0]["row_count"] is None, (
            "a branch marker, not a poll attempt: nothing was counted, and "
            "`ok = 0` would land it in the failed-poll tripwires"
        )


# ---------------------------------------------------------------------------
# The real captures, when this machine has them. Never in CI: the files are a
# real account's history, gitignored, and their absence must skip rather than
# fail -- but when present, every observed row must parse with zero refusals,
# which is the strongest wire-format check this repo can run without
# publishing the data.
# ---------------------------------------------------------------------------
CAPTURES = Path(__file__).resolve().parents[1] / "data" / "captures"


@pytest.mark.skipif(
    not (CAPTURES / "portfolio_fills.json").exists(),
    reason="local captures not present (gitignored account history)",
)
class TestTheRealCapturesParseInFull:
    def test_every_captured_fill_parses(self):
        capture = json.loads(
            (CAPTURES / "portfolio_fills.json").read_text(encoding="utf-8")
        )
        # The capture script wraps the verbatim envelope under "payload".
        rows = capture["payload"]["fills"]

        parsed = [parse_fill(r) for r in rows]

        assert parsed and all(p is not None for p in parsed), (
            "a live fill was refused -- the wire moved or the parser is wrong"
        )

    def test_every_captured_settlement_parses(self):
        capture = json.loads(
            (CAPTURES / "portfolio_settlements.json").read_text(encoding="utf-8")
        )
        rows = capture["payload"]["settlements"]

        parsed = [parse_settlement(r) for r in rows]

        assert parsed and all(p is not None for p in parsed)


class TestStudyStartIsStampedOnce:
    """Amendment A6's day-1 meta row: the venue's number, written exactly once.

    The value is the polled balance in tenths, NOT A6's literal "206583" --
    that integer is $20.6583 with its decimal dropped, and the code comment on
    `_mark_study_start` records the discrepancy so nobody restores the typo.
    """

    async def test_the_first_readable_balance_stamps_day_one(self, conn):
        await poll_portfolio(conn, FakeClient(), now_ms=1_787_100_000_000)

        assert db.get_meta(conn, "calibration_study_start_ms") == "1787100000000"
        assert db.get_meta(conn, "balance_at_study_start_tenths") == "20658"

    async def test_a_later_poll_never_moves_it(self, conn):
        await poll_portfolio(conn, FakeClient(), now_ms=1_787_100_000_000)
        richer = FakeClient(
            balance={"balance": 4000, "balance_dollars": "40.0000",
                     "portfolio_value": 0}
        )

        await poll_portfolio(conn, richer, now_ms=1_787_100_300_000)

        assert db.get_meta(conn, "calibration_study_start_ms") == "1787100000000"
        assert db.get_meta(conn, "balance_at_study_start_tenths") == "20658"

    async def test_a_failed_balance_poll_does_not_stamp(self, conn):
        await poll_portfolio(
            conn, FakeClient(fail=("balance",)), now_ms=1_787_100_000_000
        )

        assert db.get_meta(conn, "calibration_study_start_ms") is None
        assert db.get_meta(conn, "balance_at_study_start_tenths") is None

    async def test_an_unreadable_balance_does_not_stamp(self, conn):
        """`None` is "could not read", and a day-1 row with a guessed balance
        would defeat the row's purpose. The next readable poll stamps."""
        unreadable = FakeClient(balance={"balance": 2065, "portfolio_value": 0})

        await poll_portfolio(conn, unreadable, now_ms=1_787_100_000_000)

        assert db.get_meta(conn, "calibration_study_start_ms") is None


# ---------------------------------------------------------------------------
# The redacted twins of the captures above, committed. Generated by
# `scripts/redact_captures.py`: same envelope, same field names, every money
# string VERBATIM (fractional counts, the sub-deci-cent fee grid), with
# identity removed -- synthetic UUIDs, series-prefix-only tickers,
# hour-floored timestamps. This is what lets the wire-format claim run in CI
# and on every machine, instead of skipping everywhere but the laptop that
# holds the gitignored account history. The local class above stays: it is
# the stronger check, on the verbatim record, when present.
# ---------------------------------------------------------------------------
FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestTheRedactedFixturesParseInFull:
    def test_every_redacted_fill_parses(self):
        capture = json.loads(
            (FIXTURES / "portfolio_fills_redacted.json").read_text(
                encoding="utf-8"
            )
        )
        rows = capture["payload"]["fills"]

        parsed = [parse_fill(r) for r in rows]

        assert parsed and all(p is not None for p in parsed), (
            "a redacted fill was refused -- the redaction changed a value "
            "shape, or the parser regressed"
        )

    def test_every_redacted_settlement_parses(self):
        capture = json.loads(
            (FIXTURES / "portfolio_settlements_redacted.json").read_text(
                encoding="utf-8"
            )
        )
        rows = capture["payload"]["settlements"]

        parsed = [parse_settlement(r) for r in rows]

        assert parsed and all(p is not None for p in parsed)

    def test_the_redaction_kept_the_fractional_counts(self):
        """The one wire fact these fixtures exist to pin.

        A redaction that normalised "0.27" to an integer would leave the
        fixture green while removing exactly the case D1 and the REAL-count
        schema decision were written for.
        """
        capture = json.loads(
            (FIXTURES / "portfolio_fills_redacted.json").read_text(
                encoding="utf-8"
            )
        )
        counts = [r["count_fp"] for r in capture["payload"]["fills"]]

        assert any(
            "." in c and not c.endswith(".00") for c in counts
        ), "no fractional count survived the redaction"

    def test_the_redaction_carries_no_real_identifiers(self):
        """Committable means checkable: nothing UUID-shaped that is real.

        Every id must be the synthetic 00000000-0000-4000-8000-... form and
        every ticker must carry the REDACTED marker after its series prefix.
        """
        capture = json.loads(
            (FIXTURES / "portfolio_fills_redacted.json").read_text(
                encoding="utf-8"
            )
        )
        for row in capture["payload"]["fills"]:
            for key in ("fill_id", "order_id", "trade_id"):
                assert row[key].startswith("00000000-0000-4000-8000-"), row[key]
            assert "REDACTED" in row["ticker"], row["ticker"]
            assert row["subaccount_number"] == 0


# ---------------------------------------------------------------------------
# The fee alarm at the fill-ingest path.
#
# **What these establish:** that a fill whose charge matches the prediction is
# silent; that a charge above it alerts; that the boundary is
# `core.fees.FEE_MATCH_TOLERANCE_DOLLARS` and not a number chosen here; that an
# absent `fee_actual` refuses instead of reading as $0.00; that the per-day
# alert key is not defeated by many fills or many polls; that the two numbers
# handed to `Alerter.check_fee` are DOLLARS; and that the combination branch
# exists because the flat coefficient would otherwise fire on a real combo
# fill this repo has on disk.
#
# **What they do NOT establish.** Nothing about whether `core/fees.py` is
# *correct* -- the test is one-sided, so every "silent" case here is consistent
# with a prediction that is far too high, and on baseball it demonstrably is
# (2.00x, by ADR 0058 policy). Nothing about combinations beyond the eight
# fills of ADR 0046: the ceiling is a hedge above what has been seen, not a
# bound on what Kalshi charges, and no combo fill at a mid price has ever been
# observed. Nothing about delivery -- the notifier here is a recorder, and
# whether Discord accepts the embed is `test_discord.py`'s question. Nothing
# about delivery beyond the call: `scripts/run_loop.py:1048` now passes
# `alerter_factory=lambda poll_conn: Alerter(poll_conn, discord)`, so the alarm
# has a production caller -- but whether Discord accepts the embed is
# `test_discord.py`'s question, and whether the deployed loop is running is the
# live box's.
# ---------------------------------------------------------------------------

# The 2026-08-14 fee-rate attribution, cells W and R
# (`docs/measurements/2026-08-14-fee-rate-attribution-round-three-result.md`),
# plus one combination fill from `tests/fixtures/portfolio_fills_redacted.json`.
# Real charges, so no expected value below is a number this test invented.
#
#   W   KXWNBAGAME   1 @ 28c   charged $0.014200   calculate_fee $0.0142  equal
#   R   KXMLBGAME    1 @ 52c   charged $0.008800   calculate_fee $0.0175  2.00x
#   C   KXMVE   227.27 @ 0.1c  charged $0.015930   combo ceiling  $0.0162
#                                                  flat 0.070     $0.0159 UNDER
WNBA_TICKER = "KXWNBAGAME-26AUG14DALIND-DAL"
WNBA_CHARGE = "0.014200"
WNBA_PREDICTION = 0.0142
MLB_TICKER = "KXMLBGAME-26AUG141810MIACIN-CIN"
COMBO_TICKER = "KXMVECROSSCATEGORY-REDACTED000"
FEE_DAY_ONE_MS = 1_787_100_000_000
FEE_DAY_TWO_MS = FEE_DAY_ONE_MS + 26 * 3_600_000


def wnba_fill(**overrides) -> dict:
    """Cell W: the one observed fill `calculate_fee` predicts exactly."""
    row = dict(
        fill_id="w-0001",
        trade_id="w-0001",
        order_id="w-order",
        ticker=WNBA_TICKER,
        market_ticker=WNBA_TICKER,
        count_fp="1.00",
        yes_price_dollars="0.2800",
        no_price_dollars="0.7200",
        fee_cost=WNBA_CHARGE,
        is_taker=True,
    )
    row.update(overrides)
    return fill_row(**row)


class RecordingNotifier:
    """Records what would have been pushed. Delivery is `test_discord.py`'s."""

    enabled = True

    def __init__(self):
        self.fee_calls = []

    async def fee_mismatch(self, ticker, predicted, actual):
        self.fee_calls.append((ticker, predicted, actual))
        return True


@pytest.fixture
def notifier():
    return RecordingNotifier()


@pytest.fixture
def alerter(conn, notifier):
    """The real `Alerter` on the real `notifications` table.

    A fake alerter would let the per-day key be asserted against a
    re-implementation of it, which is how a dedupe test stays green while the
    real one is broken. `Alerter._claim` is what is under test in
    `test_many_mismatching_fills_send_one_alert_for_the_day`.
    """
    return Alerter(conn, notifier)


class TestWhatCountsAsAFeeMismatch:
    """The predicate alone, on real charges, with no poller around it."""

    def test_a_charge_equal_to_the_prediction_is_not_a_mismatch(self):
        check = reconcile_fill(parse_fill(wnba_fill()))

        assert check is not None
        assert check.predicted_dollars == WNBA_PREDICTION
        assert check.actual_dollars == WNBA_PREDICTION
        assert not check.is_mismatch

    def test_a_charge_inside_the_tolerance_is_not_a_mismatch(self):
        """Float dust off SQLite's REAL, not a business allowance."""
        check = reconcile_fill(parse_fill(wnba_fill(fee_cost="0.0142000005")))

        assert check is not None
        assert 0 < check.undercharge_dollars < FEE_MATCH_TOLERANCE_DOLLARS
        assert not check.is_mismatch

    def test_a_charge_one_grid_step_past_the_tolerance_is_a_mismatch(self):
        """$0.00001 is the finest grid any Kalshi charge has been observed on
        (ADR 0046's combo rows), so it is the smallest real disagreement -- and
        it is seven orders of magnitude above the tolerance."""
        check = reconcile_fill(parse_fill(wnba_fill(fee_cost="0.014210")))

        assert check is not None
        assert check.is_mismatch

    def test_the_known_two_times_overstatement_on_baseball_stays_silent(self):
        """Cell R: charged $0.0088 against a $0.0175 prediction.

        ADR 0058 keeps the flat 0.070 coefficient on every path that is not
        record-writing while MLB is charged at 0.035, so a two-sided test would
        fire on every baseball hand bet forever -- an alarm that must be muted,
        which is worse than no alarm.
        """
        check = reconcile_fill(parse_fill(wnba_fill(
            ticker=MLB_TICKER, market_ticker=MLB_TICKER,
            yes_price_dollars="0.5200", no_price_dollars="0.4800",
            fee_cost="0.008800",
        )))

        assert check is not None
        assert (check.predicted_dollars, check.actual_dollars) == (0.0175, 0.0088)
        assert not check.is_mismatch, "overstating is the designed direction"

    def test_a_combination_is_priced_by_the_ceiling_the_order_path_uses(self):
        """And the flat coefficient would have cried wolf on this exact row.

        The fill is from `portfolio_fills_redacted.json`: 227.27 contracts at
        0.1c, charged $0.015930. `calculate_fee` at 0.070 predicts $0.0159 --
        an undercharge of $0.00003, a true mismatch against a model ADR 0046
        already refutes for combos. `combo_taker_fee` (ADR 0073, k = 0.071)
        predicts $0.0162 and is silent.
        """
        combo = parse_fill(wnba_fill(
            ticker=COMBO_TICKER, market_ticker=COMBO_TICKER,
            count_fp="227.27",
            yes_price_dollars="0.0010", no_price_dollars="0.9990",
            fee_cost="0.015930",
        ))
        flat = calculate_fee(price_tenths=combo.price_tenths,
                             contracts=combo.count, maker=False)

        check = reconcile_fill(combo)

        assert flat < combo.fee_actual, (
            "the premise of the combo branch has changed: the flat coefficient "
            "no longer undercharges this observed fill"
        )
        assert check is not None
        assert check.model == "combo_taker_ceiling_0071"
        assert check.predicted_dollars == 0.0162
        assert not check.is_mismatch

    def test_a_maker_combination_fill_is_refused_rather_than_guessed(self):
        """No maker combo fill has ever been observed and ADR 0073 permits
        taker IOC buys only, so there is no coefficient to predict with."""
        prediction = predict_fill_fee(parse_fill(wnba_fill(
            ticker=COMBO_TICKER, market_ticker=COMBO_TICKER, is_taker=False,
        )))

        assert prediction.dollars is None, "never 0, never the single-market rate"
        assert "maker" in prediction.refusal

    def test_an_untradeable_price_refuses_rather_than_pricing_at_zero(self):
        """`calculate_fee` returns None at 0 tenths; a 0.0 prediction against a
        real charge would be a mismatch manufactured out of a settled price."""
        assert reconcile_fill(parse_fill(wnba_fill(
            yes_price_dollars="0.0000", no_price_dollars="1.0000",
        ))) is None


class TestTheFeeAlarmAtIngest:
    """The alarm as the poller runs it: a real `Alerter`, a real DB."""

    async def test_a_fill_that_matches_the_prediction_does_not_alert(
        self, conn, alerter, notifier
    ):
        client = FakeClient(fills=[wnba_fill()])

        summary = await poll_portfolio(
            conn, client, now_ms=FEE_DAY_ONE_MS, alerter=alerter
        )

        assert summary["fee_reconciliation"] == {
            "checked": 1, "mismatched": 0, "alerted": None,
        }
        assert notifier.fee_calls == []

    async def test_a_fill_charged_above_the_prediction_alerts(
        self, conn, alerter, notifier
    ):
        """The schedule moving against us: cell W's fill at k = 0.08."""
        client = FakeClient(fills=[wnba_fill(fee_cost="0.016128")])

        summary = await poll_portfolio(
            conn, client, now_ms=FEE_DAY_ONE_MS, alerter=alerter
        )

        assert summary["fee_reconciliation"]["mismatched"] == 1
        assert summary["fee_reconciliation"]["alerted"] is True
        assert len(notifier.fee_calls) == 1
        assert notifier.fee_calls[0][0] == WNBA_TICKER

    async def test_the_alert_carries_dollars_and_not_tenths(
        self, conn, alerter, notifier
    ):
        """`fills.fee_actual` is dollars and `calculate_fee` returns dollars.

        A tenths-of-a-cent value at this call site would be 1000x too large and
        would render as `$14.20` on the phone against a $0.28 stake.
        """
        client = FakeClient(fills=[wnba_fill(fee_cost="0.016128")])

        await poll_portfolio(conn, client, now_ms=FEE_DAY_ONE_MS, alerter=alerter)

        _ticker, predicted, actual = notifier.fee_calls[0]
        assert predicted == pytest.approx(WNBA_PREDICTION)
        assert actual == pytest.approx(0.016128)

    async def test_a_missing_fee_actual_refuses_rather_than_alerting(
        self, conn, alerter, notifier
    ):
        """Unreadable resolves to None, never 0. A $0.00 charge read against a
        positive prediction would alert on every fill the venue has not
        reported a fee for."""
        client = FakeClient(fills=[wnba_fill(fee_cost=None)])

        summary = await poll_portfolio(
            conn, client, now_ms=FEE_DAY_ONE_MS, alerter=alerter
        )

        assert conn.execute(
            "SELECT fee_actual FROM fills"
        ).fetchone()["fee_actual"] is None, "the fill itself is still recorded"
        assert summary["fee_reconciliation"]["checked"] == 0
        assert notifier.fee_calls == []

    async def test_many_mismatching_fills_send_one_alert_for_the_day(
        self, conn, alerter, notifier
    ):
        """`check_fee` is keyed per day on purpose: a wrong fee model is wrong
        on every fill, and one alert saying stop-the-line is the whole message.
        Three fills in one poll, then a fourth in a later poll the same day."""
        client = FakeClient(fills=[
            wnba_fill(fill_id=f"w-{i}", trade_id=f"w-{i}", fee_cost="0.016128")
            for i in range(3)
        ])
        await poll_portfolio(conn, client, now_ms=FEE_DAY_ONE_MS, alerter=alerter)

        later = FakeClient(fills=[
            wnba_fill(fill_id="w-9", trade_id="w-9", fee_cost="0.016128")
        ])
        await poll_portfolio(
            conn, later, now_ms=FEE_DAY_ONE_MS + 3_600_000, alerter=alerter
        )

        assert len(notifier.fee_calls) == 1, "one alert, not one per fill"
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM notifications WHERE kind = 'failure'"
        ).fetchone()["n"] == 1

    async def test_a_new_day_can_alert_again(self, conn, alerter, notifier):
        """The dedupe is a day key, not a permanent mute: an unfixed model is
        worth saying again tomorrow."""
        client = FakeClient(fills=[wnba_fill(fee_cost="0.016128")])
        await poll_portfolio(conn, client, now_ms=FEE_DAY_ONE_MS, alerter=alerter)

        tomorrow = FakeClient(fills=[
            wnba_fill(fill_id="w-2", trade_id="w-2", fee_cost="0.016128")
        ])
        await poll_portfolio(conn, tomorrow, now_ms=FEE_DAY_TWO_MS, alerter=alerter)

        assert len(notifier.fee_calls) == 2

    async def test_only_newly_stored_fills_are_reconciled(
        self, conn, alerter, notifier
    ):
        """The venue returns the same 200 fills every five minutes. Re-checking
        them would make the alarm's workload a function of Kalshi's retention
        rather than of what happened, and would re-alert every day for as long
        as a bad fill stayed in the window."""
        client = FakeClient(fills=[wnba_fill(fee_cost="0.016128")])
        await poll_portfolio(conn, client, now_ms=FEE_DAY_ONE_MS, alerter=alerter)

        second = await poll_portfolio(
            conn, client, now_ms=FEE_DAY_TWO_MS, alerter=alerter
        )

        assert second["fills"]["new"] == 0
        assert second["fee_reconciliation"]["checked"] == 0
        assert len(notifier.fee_calls) == 1

    async def test_without_an_alerter_the_mirror_still_records_the_fill(self, conn):
        """Alerting is optional infrastructure; the record is not."""
        client = FakeClient(fills=[wnba_fill(fee_cost="0.016128")])

        summary = await poll_portfolio(conn, client, now_ms=FEE_DAY_ONE_MS)

        assert summary["fills"]["new"] == 1
        assert summary["fee_reconciliation"]["mismatched"] == 1
        assert summary["fee_reconciliation"]["alerted"] is None

    async def test_an_alerter_that_explodes_does_not_take_down_the_poll(self, conn):
        class Exploding:
            async def check_fee(self, **_kwargs):
                raise RuntimeError("discord is on fire")

        client = FakeClient(fills=[wnba_fill(fee_cost="0.016128")])

        summary = await poll_portfolio(
            conn, client, now_ms=FEE_DAY_ONE_MS, alerter=Exploding()
        )

        assert summary["fills"]["new"] == 1
        assert "FAILED" in summary["fee_reconciliation"]["alerted"]

    async def test_the_loop_builds_its_alerter_on_its_own_connection(
        self, tmp_path, notifier
    ):
        """`poll_portfolio_forever` takes a FACTORY, like the hedge watcher: an
        `Alerter` binds a connection and this task owns the only one it may
        use."""
        db_path = tmp_path / "loop.db"
        db.init_db(db_path).close()
        client = FakeClient(fills=[wnba_fill(fee_cost="0.016128")])
        built = []

        def factory(poll_conn):
            built.append(poll_conn)
            return Alerter(poll_conn, notifier)

        async def no_sleep(_seconds):
            return None

        await poll_portfolio_forever(
            db_path, client, alerter_factory=factory,
            sleep=no_sleep, clock=lambda: FEE_DAY_ONE_MS / 1000, max_cycles=1,
        )

        assert len(built) == 1, "one alerter, on the poller's own connection"
        assert len(notifier.fee_calls) == 1
