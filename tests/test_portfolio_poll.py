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

from backend.gate import _fee_model_verified
from backend.portfolio_poll import (
    ParsedFill,
    ParsedSettlement,
    parse_balance_tenths,
    parse_fill,
    parse_portfolio_value_tenths,
    parse_settlement,
    poll_portfolio,
    poll_portfolio_forever,
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

        assert summary["settlements"] == {"seen": 1, "new": 1, "refused": 0}
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

        assert summary["settlements"] == {"seen": 2, "new": 1, "refused": 1}

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

    async def test_positions_are_counted_never_parsed(self, conn):
        """The shape has never been observed; a parser would be imagined."""
        client = FakeClient(positions=[{"never": "observed"}])

        summary = await poll_portfolio(conn, client, now_ms=1)

        assert summary["positions"] == {"seen": 1}


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
        self, tmp_path
    ):
        path = tmp_path / "cockpit.db"
        db.init_db(path).close()
        # 5-minute steps; 145 cycles spans just over 12 hours, so the mirror
        # should fire exactly twice: cycle 1 and the first cycle past 12h.
        clock, sleep = self._clockwork(step_s=300)

        await poll_portfolio_forever(
            path, FakeClient(), sleep=sleep, clock=clock, max_cycles=146,
        )

        conn = db.open_db(path, read_only=True)
        balances = conn.execute(
            "SELECT COUNT(*) FROM venue_balance_snapshots"
        ).fetchone()[0]
        mirrors = conn.execute(
            "SELECT COUNT(*) FROM poll_log WHERE endpoint = 'settlements'"
        ).fetchone()[0]
        conn.close()
        assert balances == 146, "the balance is every cycle, mirror included"
        assert mirrors == 2, "cycle 1, then the first cycle past the 12h mark"

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
        # Cycle 1 is a mirror (4 endpoints fail), cycles 2-3 are balance-only.
        assert failures == 6, "every failed attempt left a row, and the loop ran on"

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
