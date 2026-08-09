"""Recording Kalshi's settled outcome into `kalshi_markets.result`.

The column existed from schema v6 and nothing ever wrote it, so every assertion
here is about a path that produced NULL until now.

Wire-format assertions load `tests/fixtures/markets_settled.json` (44 real
markets, `finalized` and `closed`) and `tests/fixtures/events_sports_nested.json`
(245 real `active` markets), per the rule in `CLAUDE.md`. The only hand-built
payloads are deliberate deformations of captured ones, used for refusals the
real slate does not currently contain -- a `determined` market mid-settlement
timer, and a `finalized` market whose two statements of the outcome disagree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.kalshi.discovery import (
    RESULTS,
    SETTLED_STATUS,
    build_market,
    read_market_result,
)
from backend.market_results import (
    MIN_AGE_AFTER_COMMENCE_MS,
    markets_awaiting_result,
    record_result,
    run_market_result_pass,
)
from backend.runner import upsert_discovered
from backend.settlement import SettlementRefused, read_outcome
from backend.store import db

FIXTURES = Path(__file__).parent / "fixtures"

NOW = 1_800_000_000_000
COMMENCE = NOW - MIN_AGE_AFTER_COMMENCE_MS - 1


@pytest.fixture(scope="module")
def capture() -> dict:
    return json.loads((FIXTURES / "markets_settled.json").read_text("utf-8"))


@pytest.fixture(scope="module")
def finalized(capture) -> list[dict]:
    return [m for m in capture["markets"] if m["status"] == SETTLED_STATUS]


@pytest.fixture(scope="module")
def closed_unresolved(capture) -> list[dict]:
    return [m for m in capture["markets"] if m["status"] == "closed"]


@pytest.fixture(scope="module")
def active_markets() -> list[dict]:
    events = json.loads((FIXTURES / "events_sports_nested.json").read_text("utf-8"))
    return [m for e in events for m in (e.get("markets") or [])]


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "results.db")
    yield c
    c.close()


def _market(conn, ticker, *, event="EV", result=None, commence_ms=COMMENCE,
            close_ms=None):
    """A market row and its event, written the way the code writes them."""
    conn.execute(
        "INSERT OR REPLACE INTO kalshi_events (event_ticker, commence_ms, "
        "first_seen_ms, last_seen_ms) VALUES (?, ?, 0, 0)",
        (event, commence_ms),
    )
    conn.execute(
        "INSERT OR REPLACE INTO kalshi_markets (ticker, event_ticker, status, "
        "result, close_ms, first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, 'active', ?, ?, 0, 0)",
        (ticker, event, result, close_ms),
    )
    conn.commit()


def _result_of(conn, ticker):
    row = conn.execute(
        "SELECT result, status FROM kalshi_markets WHERE ticker = ?", (ticker,)
    ).fetchone()
    return row["result"], row["status"]


class FakeKalshi:
    """Answers `/markets?event_ticker=` from canned payloads."""

    def __init__(self, by_event: dict, *, fail: set = frozenset()):
        self.by_event = by_event
        self.fail = fail
        self.asked: list[str] = []

    async def markets_for_event(self, event_ticker: str) -> list[dict]:
        self.asked.append(event_ticker)
        if event_ticker in self.fail:
            raise RuntimeError("boom")
        return self.by_event.get(event_ticker, [])


class TestTheCaptureStillCarriesBothStates:
    """Without this, a re-capture makes every test below vacuous and still green."""

    def test_it_holds_settled_and_unsettled_markets(
        self, finalized, closed_unresolved, active_markets
    ):
        assert len(finalized) >= 20
        assert closed_unresolved
        assert len(active_markets) >= 100

    def test_an_unsettled_market_sends_an_empty_string_not_null(
        self, closed_unresolved, active_markets
    ):
        """The whole reason `None` and `"no"` must not be confused.

        Every unsettled market on the exchange carries `result: ""`. A reader
        testing `if not result` would record a loss for all of them.
        """
        for market in closed_unresolved + active_markets:
            assert market["result"] == ""
            assert market["result"] is not None


class TestReadingTheResultOffTheWire:
    def test_every_settled_market_in_the_capture_yields_an_outcome(self, finalized):
        outcomes = [read_market_result(m) for m in finalized]
        assert all(o in RESULTS for o in outcomes), (
            "a settled market parsed to nothing -- which is what reading a key "
            "other than `result`, or matching status against the filter word "
            "'settled' rather than the field value 'finalized', produces"
        )
        assert len({o for o in outcomes}) == 2, "only one side ever won"

    def test_an_active_market_is_not_a_loss(self, active_markets):
        """245 real active markets, none of which may become `'no'`."""
        assert active_markets
        assert all(read_market_result(m) is None for m in active_markets)

    def test_a_closed_market_with_no_published_result_stays_unknown(
        self, closed_unresolved
    ):
        """`closed` is durable, not transient. Game over is not outcome known."""
        assert all(read_market_result(m) is None for m in closed_unresolved)

    def test_a_determined_result_is_not_trusted_until_finalized(self, finalized):
        """Kalshi sets `result` while the settlement timer runs, and a
        `disputed` determination can be re-determined and amended. Trusting it
        would put a reversible answer into a permanent record."""
        determined = dict(finalized[0], status="determined")
        assert determined["result"] in RESULTS
        assert read_market_result(determined) is None

    def test_an_empty_result_on_a_finalized_market_does_not_become_a_loss(
        self, finalized
    ):
        """The membership test, isolated from everything that would mask it.

        `settlement_value_dollars` is *removed*, not altered, because it is
        absent on every unsettled market in both captures -- so a payload
        carrying an empty result and no settlement value is a real shape, and it
        is the one where `result or "no"` silently fabricates a loss. Written
        after the disable-check found the guard passing on its own break: the
        cross-check below it was catching the deformation instead, which made
        this line decoration.
        """
        blank = {k: v for k, v in finalized[0].items()
                 if k != "settlement_value_dollars"}
        blank["result"] = ""
        assert blank["status"] == SETTLED_STATUS
        assert read_market_result(blank) is None

    def test_a_result_this_parser_does_not_know_is_not_forced_into_yes_or_no(
        self, finalized
    ):
        """Kalshi's docs name `scalar` as a third value and this project has
        never captured one. Sports has its own unmeasured case: the NCAAF rules
        in the capture say a tie resolves 50/50, and nobody knows what `result`
        reads then. Whatever arrives, it must not be coerced into a side."""
        odd = {k: v for k, v in finalized[0].items()
               if k != "settlement_value_dollars"}
        odd["result"] = "scalar"
        assert read_market_result(odd) is None

    def test_a_payload_that_contradicts_itself_is_refused(self, finalized):
        """The outcome is stated twice; if they disagree, neither is readable."""
        winner = next(m for m in finalized if m["result"] == "yes")
        assert read_market_result(winner) == "yes"
        assert read_market_result(
            dict(winner, settlement_value_dollars="0.0000")
        ) is None

    def test_it_agrees_with_the_settlement_reader_on_every_captured_market(
        self, capture
    ):
        """Two readers of one wire format is how `data["yes"]` happened.

        They cannot be one function -- the paper-P&L path must *raise* so its
        refusals are counted, while discovery must not fail a pass over one odd
        market -- so this pins them together instead. If either drifts, this
        goes red.
        """
        for market in capture["markets"]:
            try:
                outcome = read_outcome(market)
            except SettlementRefused:
                strict = None
            else:
                strict = outcome.result if outcome else None
            assert read_market_result(market) == strict, market["ticker"]


class TestTheDiscoveryParserCarriesIt:
    def test_build_market_reads_the_result(self, finalized):
        parsed = build_market(finalized[0], market_type="moneyline")
        assert parsed.result == finalized[0]["result"]

    def test_build_market_leaves_an_active_market_unknown(self, active_markets):
        parsed = [build_market(m, market_type="moneyline") for m in active_markets]
        assert parsed
        assert all(p.result is None for p in parsed)


class TestTheUpsertWritesTheColumn:
    """`upsert_discovered` omitted `result` from both its INSERT list and its
    `ON CONFLICT` list, so the column was NULL for every row ever written."""

    def _event(self, market_payload, ticker="EV-T"):
        from backend.kalshi.discovery import DiscoveredEvent

        market = build_market(
            dict(market_payload, ticker=ticker),
            market_type="moneyline",
            event_ticker="EV",
            series_ticker="SER",
        )
        return DiscoveredEvent(
            event_ticker="EV", series_ticker="SER", league="MLB",
            sport_key="baseball_mlb", market_type="moneyline", title="t",
            commence_ms=COMMENCE, markets=(market,),
        )

    def test_the_insert_path_stores_a_result(self, conn, finalized):
        upsert_discovered(conn, [self._event(finalized[0])], now=NOW)
        assert _result_of(conn, "EV-T")[0] == finalized[0]["result"]

    def test_the_update_path_fills_in_a_row_that_already_exists(
        self, conn, finalized
    ):
        """**The branch that matters.** A market is INSERTed once while open and
        UPDATEd on every later pass, so a `result` present only in the INSERT
        list would never be filled in for any market the system had already
        seen -- which is all of them."""
        active = json.loads((FIXTURES / "events_sports_nested.json").read_text("utf-8"))
        first_active = next(
            m for e in active for m in (e.get("markets") or [])
        )
        upsert_discovered(conn, [self._event(first_active)], now=NOW)
        assert _result_of(conn, "EV-T")[0] is None

        upsert_discovered(conn, [self._event(finalized[0])], now=NOW + 1)
        assert _result_of(conn, "EV-T")[0] == finalized[0]["result"]

    def test_a_later_pass_carrying_no_result_does_not_erase_one(
        self, conn, finalized
    ):
        """Every market discovery sees is active with an empty result, so
        `result = excluded.result` would wipe a recorded outcome on the very
        next pass -- silently, and only while the event is still open."""
        upsert_discovered(conn, [self._event(finalized[0])], now=NOW)
        assert _result_of(conn, "EV-T")[0] in RESULTS

        active = json.loads((FIXTURES / "events_sports_nested.json").read_text("utf-8"))
        first_active = next(m for e in active for m in (e.get("markets") or []))
        upsert_discovered(conn, [self._event(first_active)], now=NOW + 1)
        assert _result_of(conn, "EV-T")[0] in RESULTS, (
            "an unknown overwrote a known outcome"
        )


class TestChoosingWhatToAsk:
    def test_a_market_with_a_result_is_not_asked_about_again(self, conn):
        _market(conn, "A", result="yes")
        assert markets_awaiting_result(conn, now=NOW) == {}

    def test_a_game_that_has_not_had_time_to_finish_is_left_alone(self, conn):
        _market(conn, "A", commence_ms=NOW - 60_000)
        assert markets_awaiting_result(conn, now=NOW) == {}

    def test_it_gates_on_commence_not_the_scheduled_close(self, conn):
        """`close_time` runs up to three days past the game while a market is
        open, so gating on it would leave every outcome unrecorded for days."""
        _market(conn, "A", commence_ms=COMMENCE, close_ms=NOW + 3 * 86_400_000)
        assert markets_awaiting_result(conn, now=NOW) == {"EV": ["A"]}

    def test_markets_are_grouped_by_event(self, conn):
        _market(conn, "A", event="EV1")
        _market(conn, "B", event="EV1")
        _market(conn, "C", event="EV2")
        pending = markets_awaiting_result(conn, now=NOW)
        assert pending == {"EV1": ["A", "B"], "EV2": ["C"]}

    def test_max_events_bounds_the_requests_without_splitting_an_event(self, conn):
        _market(conn, "A", event="EV1", commence_ms=COMMENCE)
        _market(conn, "B", event="EV1", commence_ms=COMMENCE)
        _market(conn, "C", event="EV2", commence_ms=COMMENCE - 10_000)
        pending = markets_awaiting_result(conn, now=NOW, max_events=1)
        assert pending == {"EV1": ["A", "B"]}


class TestThePass:
    async def test_it_records_the_outcome_for_a_row_that_already_exists(
        self, conn, finalized
    ):
        """The UPDATE path end to end: rows are already in the table with a NULL
        result, exactly as every row in the live database is today."""
        pair = [m for m in finalized if m["event_ticker"] == finalized[0]["event_ticker"]]
        assert len(pair) == 2, "the capture no longer holds a full event"
        event = pair[0]["event_ticker"]
        for m in pair:
            _market(conn, m["ticker"], event=event)

        kalshi = FakeKalshi({event: pair})
        counts = await run_market_result_pass(conn, kalshi, now=NOW)

        assert counts.recorded == 2
        assert counts.refused == 0
        assert kalshi.asked == [event], "one request per event, not per market"
        for m in pair:
            stored, status = _result_of(conn, m["ticker"])
            assert stored == m["result"]
            assert status == SETTLED_STATUS
        assert {_result_of(conn, m["ticker"])[0] for m in pair} == {"yes", "no"}

    async def test_an_unsettled_market_is_left_null_and_counted(self, conn, active_markets):
        payload = dict(active_markets[0], ticker="A", event_ticker="EV")
        _market(conn, "A")
        counts = await run_market_result_pass(conn, FakeKalshi({"EV": [payload]}), now=NOW)

        assert counts.recorded == 0
        assert counts.still_unresolved == 1
        assert counts.refused == 0, "waiting is not an alarm"
        assert _result_of(conn, "A")[0] is None

    async def test_a_finalized_market_that_cannot_be_read_is_refused_not_guessed(
        self, conn, finalized
    ):
        """A 50/50 tie settlement is reachable in sports and nobody has captured
        what `result` reads on one. Whatever it is, it must not become `'no'`."""
        broken = dict(
            finalized[0], ticker="A", event_ticker="EV",
            result="", settlement_value_dollars="0.5000",
        )
        _market(conn, "A")
        counts = await run_market_result_pass(conn, FakeKalshi({"EV": [broken]}), now=NOW)

        assert counts.refused == 1
        assert counts.recorded == 0
        assert counts.errors
        assert _result_of(conn, "A")[0] is None

    async def test_one_broken_event_does_not_stop_the_others(self, conn, finalized):
        good = dict(finalized[0], ticker="B", event_ticker="EV2")
        _market(conn, "A", event="EV1")
        _market(conn, "B", event="EV2")

        counts = await run_market_result_pass(
            conn, FakeKalshi({"EV2": [good]}, fail={"EV1"}), now=NOW
        )
        assert counts.recorded == 1
        assert counts.errors
        assert _result_of(conn, "B")[0] == good["result"]
        assert _result_of(conn, "A")[0] is None

    def test_a_recorded_outcome_is_never_swapped_for_a_different_one(
        self, conn, finalized
    ):
        winner = next(m for m in finalized if m["result"] == "yes")
        _market(conn, "A", result="yes")
        assert record_result(conn, "A", "no", now=NOW) is False
        assert _result_of(conn, "A")[0] == "yes"
        assert winner["result"] == "yes"

    async def test_counts_are_reported_even_at_zero(self, conn):
        counts = await run_market_result_pass(conn, FakeKalshi({}), now=NOW)
        reported = counts.as_dict()
        assert reported["recorded"] == 0
        assert reported["refused"] == 0
        assert reported["still_unresolved"] == 0
        assert reported["markets_pending"] == 0
