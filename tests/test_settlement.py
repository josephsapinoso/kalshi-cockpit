"""The paper settlement path.

Wire-format assertions load `tests/fixtures/markets_settled.json` — 44 markets
captured off the live exchange **before** `backend/settlement.py` was written,
per the rule in `CLAUDE.md`. Every hand-built payload in this file is a
*deliberate deformation* of one from the capture, used to test a refusal that
the real slate does not currently contain. That distinction matters: the shapes
the parser accepts come from real bytes, and only the shapes it rejects are
invented.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.settlement import (
    SETTLED_STATUS,
    SettlementCounts,
    SettlementRefused,
    daily_realised_pnl_dollars,
    open_position_dollars,
    position_pnl_cents,
    positions_awaiting_settlement,
    read_outcome,
    run_settlement_pass,
)
from backend.store import db
from backend.store.orders import DEPTH_CAPPED_TAKER, current_exposure_dollars

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def capture() -> dict:
    return json.loads((FIXTURES / "markets_settled.json").read_text("utf-8"))


@pytest.fixture(scope="module")
def finalized(capture) -> list[dict]:
    return [m for m in capture["markets"] if m["status"] == SETTLED_STATUS]


@pytest.fixture(scope="module")
def closed_unresolved(capture) -> list[dict]:
    return [m for m in capture["markets"] if m["status"] == "closed"]


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "settle.db")
    yield c
    c.close()


def _order(conn, *, ticker="T", side="yes", count=10, price=500, dry_run=True,
           status="dry_run", response=None):
    """One market and one order, written the way the code writes them."""
    conn.execute(
        "INSERT OR REPLACE INTO kalshi_markets (ticker, first_seen_ms, "
        "last_seen_ms) VALUES (?, 0, 0)",
        (ticker,),
    )
    cur = conn.execute(
        "INSERT INTO orders (client_order_id, submitted_ms, ticker, side, "
        "action, order_type, count, limit_price_tenths, status, "
        "request_body_json, dry_run, fill_assumption, assumed_filled_count, "
        "response_body_json) "
        "VALUES (?, 0, ?, ?, 'buy', 'limit', ?, ?, ?, '{}', ?, ?, ?, ?)",
        (
            f"c{id(conn)}-{conn.execute('SELECT COUNT(*) c FROM orders').fetchone()['c']}",
            ticker, side, count, price, status, 1 if dry_run else 0,
            DEPTH_CAPPED_TAKER, count, response,
        ),
    )
    conn.commit()
    return cur.lastrowid


class FakeKalshi:
    """Returns a canned payload per ticker, and records what was asked."""

    def __init__(self, payloads: dict, *, fail: set[str] = frozenset()):
        self.payloads = payloads
        self.fail = fail
        self.asked: list[str] = []

    async def get(self, path: str) -> dict:
        ticker = path.rsplit("/", 1)[-1]
        self.asked.append(ticker)
        if ticker in self.fail:
            raise RuntimeError("boom")
        return {"market": self.payloads[ticker]}


class TestTheCaptureItself:
    """Assert the fixture's contents, so a re-capture cannot quietly gut this file.

    Without this, a truncated or re-scoped capture makes every test below
    vacuous while all of them still pass.
    """

    def test_it_holds_settled_and_unresolved_markets(self, finalized, closed_unresolved):
        assert len(finalized) >= 20, "too few settled markets to pin the shape"
        assert closed_unresolved, (
            "no closed-but-unresolved market, so the third state is untested"
        )

    def test_the_status_field_is_not_the_word_the_filter_uses(self, capture):
        """The finding that would have broken everything silently.

        `?status=settled` returns markets reporting `finalized`, and `finalized`
        is rejected as a filter. A parser matching `== "settled"` settles
        nothing, forever.
        """
        assert SETTLED_STATUS == "finalized"
        assert not [m for m in capture["markets"] if m["status"] == "settled"]
        assert any(
            q.get("status") == "settled" and q.get("returned")
            for q in capture["queries"]
        ), "the capture no longer records that `settled` was the filter asked for"

    def test_an_unresolved_market_sends_an_empty_string_not_null(
        self, closed_unresolved
    ):
        """So `if not result` reads an active market as a settled one."""
        for market in closed_unresolved:
            assert market["result"] == ""
            assert market["result"] is not None


class TestReadingTheOutcome:
    def test_every_settled_market_in_the_capture_parses(self, finalized):
        for market in finalized:
            outcome = read_outcome({"market": market})
            assert outcome is not None, market["ticker"]
            assert outcome.result in ("yes", "no")
            assert outcome.settled_ms > 0

    def test_a_closed_market_is_not_settled_and_is_not_a_loss(self, closed_unresolved):
        """Two in the capture closed 2026-02-03 and still carry no result.

        `None` means "not yet", which leaves the position open. Reading it as a
        loss would write an outcome Kalshi has not published.
        """
        for market in closed_unresolved:
            assert read_outcome({"market": market}) is None

    def test_an_unrecognised_status_refuses(self, finalized):
        market = dict(finalized[0], status="expired")
        with pytest.raises(SettlementRefused, match="unrecognised status"):
            read_outcome({"market": market})

    def test_a_settled_market_with_no_result_refuses(self, finalized):
        market = dict(finalized[0], result="")
        with pytest.raises(SettlementRefused, match="not one of"):
            read_outcome({"market": market})

    def test_a_settled_market_with_no_timestamp_refuses(self, finalized):
        """Rather than substituting `close_time` or `expiration_time`.

        On the captured sample `expiration_time` sits three days after
        `close_time`, so it is not a settlement instant at all.
        """
        market = dict(finalized[0], settlement_ts="")
        with pytest.raises(SettlementRefused, match="settlement_ts"):
            read_outcome({"market": market})

    def test_a_payload_that_contradicts_itself_refuses(self, finalized):
        """`result` and `settlement_value_dollars` agree on 42 of 42 real markets.

        They are two statements of one fact, so a disagreement means one is
        being misread and neither should be trusted.
        """
        market = dict(finalized[0], result="yes", settlement_value_dollars="0.0000")
        with pytest.raises(SettlementRefused, match="contradicts itself"):
            read_outcome({"market": market})

    def test_a_result_on_an_active_market_refuses(self, capture):
        market = dict(
            next(m for m in capture["markets"] if m["status"] == "closed"),
            result="yes",
        )
        with pytest.raises(SettlementRefused, match="disagree"):
            read_outcome({"market": market})


class TestThePnLArithmetic:
    """Anchors chosen where a wrong implementation gives a *different* answer.

    A sign convention with two plausible directions needs a case fixed by
    definition, not by reasoning — this repo has shipped an inverted one whose
    own test asserted the inversion.
    """

    def test_a_winning_yes_is_paid_the_complement_of_what_it_cost(self):
        """10 contracts of YES at 50c, resolving YES: +$5.00 gross, less fee.

        Deliberately not 50c-symmetric in the way that hides errors: the losing
        case below costs a different number, so an implementation that
        confused cost with payout gives a different answer on one of them.
        """
        from backend.core.fees import calculate_fee_cents

        fee = calculate_fee_cents(500, 10)
        assert position_pnl_cents(
            side="yes", count=10, price_tenths=500, result="yes"
        ) == 500 - fee

    def test_a_losing_yes_loses_exactly_what_it_cost(self):
        from backend.core.fees import calculate_fee_cents

        fee = calculate_fee_cents(500, 10)
        assert position_pnl_cents(
            side="yes", count=10, price_tenths=500, result="no"
        ) == -500 - fee

    def test_a_no_position_wins_when_the_market_resolves_no(self):
        """The case an inverted side mapping gets backwards.

        Chosen off 50c on purpose: at 50c a swapped side gives the same
        magnitude and the test would pass under both conventions.
        """
        from backend.core.fees import calculate_fee_cents

        fee = calculate_fee_cents(300, 10)
        # 10 NO at 30c: wins 70c each = +$7.00 gross.
        assert position_pnl_cents(
            side="no", count=10, price_tenths=300, result="no"
        ) == 700 - fee
        # And the same position on the other outcome loses its $3.00 stake.
        assert position_pnl_cents(
            side="no", count=10, price_tenths=300, result="yes"
        ) == -300 - fee

    def test_the_fee_is_charged_once_not_on_a_round_trip(self):
        """A bet held to settlement pays the entry fee only."""
        from backend.core.fees import calculate_fee_cents, round_trip_fee

        fee = calculate_fee_cents(300, 10)
        pnl = position_pnl_cents(side="no", count=10, price_tenths=300, result="no")
        assert 700 - pnl == fee
        assert fee < int(round(round_trip_fee(300, 300, 10) * 100))

    def test_a_sub_cent_price_refuses_rather_than_rounding(self):
        """Half a cent is half the edge being hunted, so it is not rounded away.

        Unreachable on today's slate — all 1,426 game markets walked are
        `linear_cent` — and reachable the day a market's grid changes while it
        is open.
        """
        assert position_pnl_cents(
            side="yes", count=3, price_tenths=505, result="yes"
        ) is None

    def test_an_untradeable_price_refuses(self):
        """A zero fee at an untradeable price is what fabricated a +55c edge once."""
        assert position_pnl_cents(
            side="yes", count=10, price_tenths=1000, result="yes"
        ) is None


class TestThePass:
    async def test_a_settled_market_closes_its_position(self, conn, finalized):
        market = finalized[0]
        _order(conn, ticker=market["ticker"], side=market["result"])
        client = FakeKalshi({market["ticker"]: market})

        counts = await run_settlement_pass(conn, client)

        assert counts.settled == 1
        assert counts.positions_open == 1
        row = conn.execute("SELECT * FROM settlements").fetchone()
        assert row["result"] == market["result"]
        assert row["dry_run"] == 1
        assert row["fill_assumption"] == DEPTH_CAPPED_TAKER

    async def test_an_unsettled_market_leaves_the_position_open(
        self, conn, closed_unresolved
    ):
        market = closed_unresolved[0]
        _order(conn, ticker=market["ticker"])
        client = FakeKalshi({market["ticker"]: market})

        counts = await run_settlement_pass(conn, client)

        assert counts.settled == 0
        assert counts.still_unresolved == 1
        assert conn.execute("SELECT COUNT(*) c FROM settlements").fetchone()["c"] == 0

    async def test_it_asks_once_per_ticker_not_once_per_position(
        self, conn, finalized
    ):
        """Two positions on one market share an outcome.

        Asking twice would spend two requests and invite the two rows to
        disagree about a fact that has one value.
        """
        market = finalized[0]
        _order(conn, ticker=market["ticker"], side="yes")
        _order(conn, ticker=market["ticker"], side="no")
        client = FakeKalshi({market["ticker"]: market})

        counts = await run_settlement_pass(conn, client)

        assert client.asked == [market["ticker"]]
        assert counts.settled == 2

    async def test_one_unreadable_market_does_not_stop_the_others(
        self, conn, finalized
    ):
        """A position left open holds exposure and looks like one nobody read."""
        good, bad = finalized[0], finalized[2]
        _order(conn, ticker=good["ticker"], side=good["result"])
        _order(conn, ticker=bad["ticker"], side=bad["result"])
        client = FakeKalshi(
            {good["ticker"]: good, bad["ticker"]: bad}, fail={bad["ticker"]}
        )

        counts = await run_settlement_pass(conn, client)

        assert counts.settled == 1
        assert counts.still_unresolved == 1
        assert counts.errors

    async def test_a_refusal_is_counted_separately_from_not_yet_settled(
        self, conn, finalized
    ):
        """"The wire format moved" and "the game is still on" need opposite
        responses, so they are different numbers."""
        market = dict(finalized[0], status="expired")
        _order(conn, ticker=market["ticker"])
        client = FakeKalshi({market["ticker"]: market})

        counts = await run_settlement_pass(conn, client)

        assert counts.refused == 1
        assert counts.still_unresolved == 1
        assert counts.settled == 0

    async def test_settling_is_not_repeated_on_the_next_pass(self, conn, finalized):
        market = finalized[0]
        _order(conn, ticker=market["ticker"], side=market["result"])
        client = FakeKalshi({market["ticker"]: market})

        await run_settlement_pass(conn, client)
        second = await run_settlement_pass(conn, client)

        assert second.positions_open == 0
        assert second.settled == 0
        assert conn.execute("SELECT COUNT(*) c FROM settlements").fetchone()["c"] == 1

    def test_a_settled_position_does_not_hide_its_neighbour_on_the_same_ticker(
        self, conn, finalized
    ):
        """`positions_awaiting_settlement` joins on `order_id`, not `ticker`.

        Found by disabling: swapping the join to `s.ticker = o.ticker` left the
        whole file green. Every other test settles both positions on a ticker in
        one pass, where the two joins cannot differ — the difference only shows
        when one position on a market is closed and another is not, which is the
        exact case schema v4 was rebuilt for.

        Two places encode "which positions are still open": this query and the
        exposure query. They had the same defect and only one had a test.
        """
        market = finalized[0]
        first = _order(conn, ticker=market["ticker"], side="yes")
        _order(conn, ticker=market["ticker"], side="no")
        conn.execute(
            "INSERT INTO settlements (order_id, ticker, settled_ms, result, "
            "contracts, pnl_cents, dry_run) VALUES (?, ?, 1, 'yes', 10, 500, 1)",
            (first, market["ticker"]),
        )
        conn.commit()

        open_ids = [p["id"] for p in positions_awaiting_settlement(conn)]
        assert open_ids == [first + 1], (
            "settling one position hid the other one on the same ticker"
        )

    async def test_a_terminal_order_is_never_settled(self, conn, finalized):
        """A rejected order is not a position. It holds no capital and closing
        it would put a P&L on a bet that never existed."""
        market = finalized[0]
        _order(conn, ticker=market["ticker"], status="rejected")
        client = FakeKalshi({market["ticker"]: market})

        counts = await run_settlement_pass(conn, client)

        assert counts.positions_open == 0
        assert client.asked == []

    async def test_the_observed_depth_is_carried_from_the_stored_response(
        self, conn, finalized
    ):
        """It is the evidence for the fill assumption, so a re-analysis needs it."""
        market = finalized[0]
        _order(
            conn, ticker=market["ticker"], side=market["result"],
            response=json.dumps({"quote": {"depth_at_ask": 640.95}}),
        )
        await run_settlement_pass(conn, FakeKalshi({market["ticker"]: market}))

        row = conn.execute("SELECT depth_at_order FROM settlements").fetchone()
        assert row["depth_at_order"] == pytest.approx(640.95)

    async def test_a_missing_depth_stays_missing(self, conn, finalized):
        """Rather than defaulting. An order with no recorded response has no
        observed depth, and inventing one invents the evidence for the fill."""
        market = finalized[0]
        _order(conn, ticker=market["ticker"], side=market["result"])
        await run_settlement_pass(conn, FakeKalshi({market["ticker"]: market}))

        row = conn.execute("SELECT depth_at_order FROM settlements").fetchone()
        assert row["depth_at_order"] is None


class TestExposureIsReleased:
    async def test_settling_releases_the_paper_capital(self, conn, finalized):
        """The whole reason this module exists.

        Without it paper exposure only ratchets up, which is a cap that can
        only close — an off switch, per ADR 0008.
        """
        market = finalized[0]
        _order(conn, ticker=market["ticker"], side=market["result"],
               count=10, price=500)
        assert current_exposure_dollars(conn, dry_run=True) == pytest.approx(
            5.20  # $5.00 of stake plus the 20c taker fee
        )

        await run_settlement_pass(conn, FakeKalshi({market["ticker"]: market}))

        assert current_exposure_dollars(conn, dry_run=True) == 0.0


def _settlement(conn, order_id, *, ticker="T", settled_ms, pnl_cents, dry_run=True):
    conn.execute(
        "INSERT INTO settlements (order_id, ticker, settled_ms, result, "
        "contracts, pnl_cents, dry_run, fill_assumption) "
        "VALUES (?, ?, ?, 'no', 10, ?, ?, 'test')",
        (order_id, ticker, settled_ms, pnl_cents, 1 if dry_run else 0),
    )
    conn.commit()


NOON_UTC = 1_786_363_200_000        # 2026-08-10 12:00Z, two hours past the roll


class TestTheDaysRealisedPnLCanBeRead:
    """`settlements.pnl_cents` has been written since ADR 0010 and nothing
    summed it. There was no `SUM` of that column anywhere in the repo -- only
    `analysis/clv.py` and `analysis/validate.py`, both reporting after the fact.
    That absence is the whole of the 2026-08-10 finding: the kill switch was
    correct code with no producer.
    """

    def test_an_empty_table_is_zero_rather_than_unreadable(self, conn):
        """A measurement, not an absence. Nothing has settled, so nothing has
        been lost -- and returning `None` here would refuse every order on a
        fresh database, which is a kill switch that fires before the first
        bet."""
        assert daily_realised_pnl_dollars(
            conn, now_ms=NOON_UTC, dry_run=True
        ) == 0.0

    def test_losses_inside_the_risk_day_sum_in_dollars(self, conn):
        for i in range(40):
            order = _order(conn, ticker=f"T{i}")
            _settlement(conn, order, ticker=f"T{i}",
                        settled_ms=NOON_UTC, pnl_cents=-50_000)
        assert daily_realised_pnl_dollars(
            conn, now_ms=NOON_UTC, dry_run=True
        ) == pytest.approx(-20_000.0)

    def test_a_profit_is_positive_and_offsets_a_loss(self, conn):
        """The sign convention, stated by a test rather than by a comment. This
        repo has already had a sign convention agree with its own test and both
        be wrong; here the direction is fixed by the *caller* -- `size_position`
        refuses at `<= -abs(limit)` -- so an inverted sign would turn a
        profitable day into a kill switch."""
        a, b = _order(conn, ticker="A"), _order(conn, ticker="B")
        _settlement(conn, a, ticker="A", settled_ms=NOON_UTC, pnl_cents=-1_500)
        _settlement(conn, b, ticker="B", settled_ms=NOON_UTC, pnl_cents=900)
        assert daily_realised_pnl_dollars(
            conn, now_ms=NOON_UTC, dry_run=True
        ) == pytest.approx(-6.0)

    def test_yesterdays_loss_is_not_todays(self, conn):
        """Otherwise the daily limit is a permanent off switch after one bad
        night -- and it would pass every test that only seeds today."""
        order = _order(conn)
        _settlement(conn, order, settled_ms=NOON_UTC - 86_400_000,
                    pnl_cents=-50_000)
        assert daily_realised_pnl_dollars(
            conn, now_ms=NOON_UTC, dry_run=True
        ) == 0.0

    def test_the_risk_day_rolls_at_the_budget_days_hour_not_midnight(self, conn):
        """The design decision, asserted rather than described.

        22:00Z on 2026-08-09 is 6pm ET -- the middle of the US evening slate,
        and two hours *after* UTC midnight would have rolled the day. It belongs
        to the same risk day as 08:00Z the next morning, and to a different one
        from noon on the 10th. A UTC-midnight implementation gets the first of
        these wrong, which is the failure that matters: the kill switch would
        disengage mid-slate.
        """
        evening = 1_786_312_800_000            # 2026-08-09 22:00Z
        order = _order(conn)
        _settlement(conn, order, settled_ms=evening, pnl_cents=-50_000)

        early_next_morning = 1_786_348_800_000  # 2026-08-10 08:00Z
        assert daily_realised_pnl_dollars(
            conn, now_ms=early_next_morning, dry_run=True
        ) == pytest.approx(-500.0), (
            "an evening loss stopped counting before the night was over"
        )
        assert daily_realised_pnl_dollars(
            conn, now_ms=NOON_UTC, dry_run=True
        ) == 0.0, "the risk day never rolled at all"

    def test_the_roll_hour_is_configurable_and_actually_used(self, conn):
        """Anchors the test above against an implementation that hardcoded 10.

        The order endpoint passes `OddsConfig.budget_day_start_utc_hour`, so a
        parameter that were ignored would silently put the risk day and the odds
        budget day on different clocks whenever `.env` sets that variable.
        """
        evening = 1_786_312_800_000            # 2026-08-09 22:00Z
        order = _order(conn)
        _settlement(conn, order, settled_ms=evening, pnl_cents=-50_000)
        morning = 1_786_348_800_000            # 2026-08-10 08:00Z

        assert daily_realised_pnl_dollars(
            conn, now_ms=morning, dry_run=True, day_start_hour=10
        ) == pytest.approx(-500.0)
        assert daily_realised_pnl_dollars(
            conn, now_ms=morning, dry_run=True, day_start_hour=0
        ) == 0.0, "day_start_hour is not reaching the query"

    def test_paper_and_live_are_never_pooled(self, conn):
        """A live loss must not stop a paper order, and -- the dangerous
        direction -- a paper profit must never offset a live loss."""
        paper, live = _order(conn, ticker="A"), _order(conn, ticker="B")
        _settlement(conn, paper, ticker="A", settled_ms=NOON_UTC,
                    pnl_cents=-1_000, dry_run=True)
        _settlement(conn, live, ticker="B", settled_ms=NOON_UTC,
                    pnl_cents=-9_000, dry_run=False)

        assert daily_realised_pnl_dollars(
            conn, now_ms=NOON_UTC, dry_run=True
        ) == pytest.approx(-10.0)
        assert daily_realised_pnl_dollars(
            conn, now_ms=NOON_UTC, dry_run=False
        ) == pytest.approx(-90.0)

    def test_an_unreadable_database_is_none_and_never_zero(self, conn):
        """`CLAUDE.md`: unreadable resolves to `None`, never `0`. On a loss
        limit, `0.0` is the maximally permissive substitution available."""
        conn.execute("DROP TABLE settlements")
        conn.commit()
        assert daily_realised_pnl_dollars(
            conn, now_ms=NOON_UTC, dry_run=True
        ) is None


class TestThePositionOnOneTickerCanBeRead:
    """The other missing producer. `max_position_dollars` is a per-market cap
    and nothing measured the per-market position -- 76 contracts and ~$38.00
    accumulated on one ticker against a $10 cap before the portfolio cap bound.
    """

    def test_it_counts_only_the_ticker_asked_about(self, conn):
        _order(conn, ticker="A", count=10, price=500)
        _order(conn, ticker="B", count=20, price=500)
        assert open_position_dollars(conn, "A", dry_run=True) == pytest.approx(5.20)
        assert open_position_dollars(conn, "B", dry_run=True) == pytest.approx(10.40)

    def test_a_ticker_with_nothing_open_is_zero(self, conn):
        _order(conn, ticker="A")
        assert open_position_dollars(conn, "B", dry_run=True) == 0.0

    def test_it_agrees_with_the_portfolio_sum_on_a_one_ticker_book(self, conn):
        """The two are the same predicate scoped differently, and this is what
        keeps them that way. Not proof -- this repo has recorded two paths that
        agreed and were both wrong -- but the arithmetic here comes from
        `exposure_contribution`, the project's only definition of what an open
        order commits, so what is pinned is the *filter* rather than the sum."""
        _order(conn, ticker="A", count=7, price=430)
        _order(conn, ticker="A", count=3, price=610)
        assert open_position_dollars(conn, "A", dry_run=True) == pytest.approx(
            current_exposure_dollars(conn, dry_run=True)
        )

    def test_a_settled_position_no_longer_counts(self, conn):
        """Settling releases the capital, exactly as it does for exposure. A
        per-market cap that counted closed positions would ratchet shut."""
        order = _order(conn, ticker="A", count=10, price=500)
        assert open_position_dollars(conn, "A", dry_run=True) > 0
        _settlement(conn, order, ticker="A", settled_ms=NOON_UTC, pnl_cents=100)
        assert open_position_dollars(conn, "A", dry_run=True) == 0.0

    def test_paper_and_live_are_never_pooled(self, conn):
        _order(conn, ticker="A", count=10, price=500, dry_run=True)
        _order(conn, ticker="A", count=40, price=500, dry_run=False,
               status="resting")
        assert open_position_dollars(conn, "A", dry_run=True) == pytest.approx(5.20)
        assert open_position_dollars(conn, "A", dry_run=False) == pytest.approx(20.80)

    def test_an_unreadable_price_refuses_the_whole_sum(self, conn):
        """Skipping it would report a smaller position than the truth and hand
        the next order room it does not have."""
        _order(conn, ticker="A", count=10, price=500)
        conn.execute("UPDATE orders SET limit_price_tenths = NULL")
        conn.commit()
        assert open_position_dollars(conn, "A", dry_run=True) is None


class TestTheGateNeverReadsSettlements:
    def test_gate_does_not_reference_the_settlements_table(self):
        """Structural, not advisory — ADR 0010 decision 5.

        Paper P&L is easier to read than CLV, arrives sooner, and has none of
        the noise discipline. This repo has already recorded what happens when a
        legible number sits beside a careful contradicting one. Independence is
        asserted here so it is a property of the code rather than of anyone
        remembering.
        """
        source = (
            Path(__file__).parent.parent / "backend" / "gate.py"
        ).read_text("utf-8")
        assert "settlements" not in source
        assert "pnl" not in source.lower()


class TestTheCountsSurviveTheFilter:
    def test_the_numbers_that_mean_nothing_happened_are_still_printed(self):
        as_dict = SettlementCounts().as_dict()
        for key in ("positions_open", "settled", "still_unresolved", "refused"):
            assert key in as_dict, f"{key} vanishes at zero"

    def test_an_ordinary_empty_field_is_still_filtered(self):
        """Or the assertions above would pass against a serialiser that had
        abandoned filtering entirely."""
        assert "markets_queried" not in SettlementCounts().as_dict()
