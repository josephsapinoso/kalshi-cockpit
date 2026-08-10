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
import logging
from pathlib import Path

import pytest

from backend.kalshi.discovery import (
    RESULTS,
    SETTLED_STATUS,
    build_market,
    read_market_result,
)
from backend.config import MarketResultConfig
from backend.market_results import (
    MAX_REPORTED_ERRORS,
    count_unreadable,
    markets_awaiting_result,
    markets_by_ticker,
    record_result,
    result_coverage,
    run_market_result_pass,
)
from backend.runner import upsert_discovered
from backend.settlement import SettlementRefused, read_outcome
from backend.store import db

FIXTURES = Path(__file__).parent / "fixtures"

DEFAULTS = MarketResultConfig()
NOW = 1_800_000_000_000
COMMENCE = NOW - DEFAULTS.min_age_after_commence_ms - 1
LONG_AGO = NOW - DEFAULTS.max_age_after_commence_ms - 1


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
            close_ms=None, status="active"):
    """A market row and its event, written the way the code writes them."""
    conn.execute(
        "INSERT OR REPLACE INTO kalshi_events (event_ticker, commence_ms, "
        "first_seen_ms, last_seen_ms) VALUES (?, ?, 0, 0)",
        (event, commence_ms),
    )
    conn.execute(
        "INSERT OR REPLACE INTO kalshi_markets (ticker, event_ticker, status, "
        "result, close_ms, first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, ?, ?, ?, 0, 0)",
        (ticker, event, status, result, close_ms),
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
        """A status short of `finalized` is refused, whatever it carries.

        The premise usually given for this -- that Kalshi *populates* `result`
        at `determined` while the settlement timer runs -- is an **inference,
        not a measurement**. The capture holds zero `determined` markets, and
        its own `result_while_active` and `terminal_status_with_empty_result`
        metadata arrays are both empty; what is measured is only that a
        `settlement_timer_seconds` field exists, reading 60/90/120/300. So this
        test asserts the conservative half, which is the half that survives
        either way: an answer at a reversible status does not enter a permanent
        record. If the inference is wrong, the pass is one timer late; if it is
        right, a re-determined `disputed` market cannot rewrite history.
        """
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
        assert markets_awaiting_result(conn, now=NOW).by_event == {}

    def test_a_game_that_has_not_had_time_to_finish_is_left_alone(self, conn):
        _market(conn, "A", commence_ms=NOW - 60_000)
        assert markets_awaiting_result(conn, now=NOW).by_event == {}

    def test_it_gates_on_commence_not_the_scheduled_close(self, conn):
        """`close_time` runs up to three days past the game while a market is
        open, so gating on it would leave every outcome unrecorded for days."""
        _market(conn, "A", commence_ms=COMMENCE, close_ms=NOW + 3 * 86_400_000)
        assert markets_awaiting_result(conn, now=NOW).by_event == {"EV": ["A"]}

    def test_markets_are_grouped_by_event(self, conn):
        _market(conn, "A", event="EV1")
        _market(conn, "B", event="EV1")
        _market(conn, "C", event="EV2")
        pending = markets_awaiting_result(conn, now=NOW)
        assert pending.by_event == {"EV1": ["A", "B"], "EV2": ["C"]}

    def test_max_events_bounds_the_requests_without_splitting_an_event(self, conn):
        _market(conn, "A", event="EV1", commence_ms=COMMENCE)
        _market(conn, "B", event="EV1", commence_ms=COMMENCE)
        _market(conn, "C", event="EV2", commence_ms=COMMENCE - 10_000)
        pending = markets_awaiting_result(conn, now=NOW, max_events=1)
        assert pending.by_event == {"EV1": ["A", "B"]}

    def test_the_cap_says_how_many_events_it_left_out(self, conn):
        """Silent truncation reads as 'covered everything' when it didn't."""
        _market(conn, "A", event="EV1", commence_ms=COMMENCE)
        _market(conn, "B", event="EV2", commence_ms=COMMENCE - 10_000)
        _market(conn, "C", event="EV3", commence_ms=COMMENCE - 20_000)
        pending = markets_awaiting_result(conn, now=NOW, max_events=1)
        assert pending.deferred_events == 2

    def test_the_cap_comes_from_config_when_no_argument_is_given(self, conn):
        """The live loop passes no `max_events`, so the env var is the only
        throttle that exists without a deploy."""
        _market(conn, "A", event="EV1", commence_ms=COMMENCE)
        _market(conn, "B", event="EV2", commence_ms=COMMENCE - 10_000)
        capped = MarketResultConfig(max_events_per_pass=1)
        pending = markets_awaiting_result(conn, now=NOW, config=capped)
        assert list(pending.by_event) == ["EV1"]
        assert pending.deferred_events == 1


class TestTheAgeBoundStopsAskingForever:
    """Finding B. `markets_awaiting_result` had no upper age bound and
    `max_events` is unset on live, so a market that never finalizes was
    re-queried on all 96 passes a day, permanently and invisibly."""

    def test_a_market_older_than_the_window_is_not_asked_about(self, conn):
        _market(conn, "A", commence_ms=LONG_AGO)
        assert markets_awaiting_result(conn, now=NOW).by_event == {}

    def test_the_dropped_population_gets_its_own_counter(self, conn):
        """Not `still_unresolved`. That bucket means 'in the 7th inning', and
        one counter over both a state that resolves in an hour and a state that
        never resolves cannot show the leak."""
        _market(conn, "A", event="EV1", commence_ms=LONG_AGO)
        _market(conn, "B", event="EV2", commence_ms=COMMENCE)
        pending = markets_awaiting_result(conn, now=NOW)
        assert pending.by_event == {"EV2": ["B"]}
        assert pending.abandoned_total == 1

    def test_the_oldest_abandoned_market_is_named_with_its_age(self, conn):
        _market(conn, "STUCK", event="EV1", commence_ms=NOW - 200 * 86_400_000)
        _market(conn, "NEWER", event="EV2", commence_ms=LONG_AGO)
        pending = markets_awaiting_result(conn, now=NOW)
        assert pending.abandoned_total == 2
        assert pending.abandoned_oldest.startswith("STUCK (")
        assert "200d" in pending.abandoned_oldest

    def test_nothing_abandoned_reports_zero_rather_than_going_quiet(self, conn):
        _market(conn, "A", commence_ms=COMMENCE)
        pending = markets_awaiting_result(conn, now=NOW)
        assert pending.abandoned_total == 0
        assert pending.abandoned_oldest == ""

    def test_widening_the_window_brings_an_abandoned_market_back(self, conn):
        """Abandonment is an age bound on a query, not a flag on a row. It has
        to be reversible from config alone or the loss would be permanent."""
        _market(conn, "A", commence_ms=LONG_AGO)
        wide = MarketResultConfig(max_age_after_commence_s=365 * 24 * 60 * 60)
        assert markets_awaiting_result(conn, now=NOW, config=wide).by_event == {
            "EV": ["A"]
        }

    async def test_the_pass_reports_the_bound_on_every_line(self, conn):
        _market(conn, "A", commence_ms=LONG_AGO)
        counts = await run_market_result_pass(conn, FakeKalshi({}), now=NOW)
        assert counts.as_dict()["abandoned_total"] == 1
        assert "abandoned_oldest" in counts.as_dict()
        assert counts.still_unresolved == 0, (
            "an abandoned market must not fall into the bucket that also holds "
            "a game currently in progress"
        )


class TestARefusalIsAskedOnceNotForever:
    """Finding A. The write was guarded by `WHERE result IS NULL`; the *read*
    was not, so a refused market stayed NULL, stayed in the queue, and produced
    an identical ERROR on every pass -- 2 markets x 96 passes = 192 lines a day
    from one tied game, forever."""

    def _tie(self, finalized, ticker="A", event="EV"):
        return dict(
            finalized[0], ticker=ticker, event_ticker=event,
            result="", settlement_value_dollars="0.5000",
        )

    async def test_a_refused_market_leaves_the_queue(self, conn, finalized):
        _market(conn, "A")
        kalshi = FakeKalshi({"EV": [self._tie(finalized)]})
        first = await run_market_result_pass(conn, kalshi, now=NOW)
        assert first.refused == 1

        assert markets_awaiting_result(conn, now=NOW + 1).by_event == {}, (
            "the row is still queued, so it will be re-refused every pass"
        )

    async def test_the_second_pass_neither_asks_nor_logs(
        self, conn, finalized, caplog
    ):
        """The two passes in the audit's run were byte-identical. This is the
        assertion that they cannot be again."""
        _market(conn, "A")
        kalshi = FakeKalshi({"EV": [self._tie(finalized)]})
        await run_market_result_pass(conn, kalshi, now=NOW)

        caplog.clear()
        with caplog.at_level("ERROR", logger="backend.market_results"):
            second = await run_market_result_pass(conn, kalshi, now=NOW + 1)

        assert kalshi.asked == ["EV"], "the event was queried a second time"
        assert second.refused == 0
        assert second.errors == []
        assert caplog.records == []

    async def test_the_refusal_itself_is_unchanged_and_writes_no_outcome(
        self, conn, finalized
    ):
        """Fix the consequence, not the refusal. A tie stays NULL."""
        _market(conn, "A")
        await run_market_result_pass(
            conn, FakeKalshi({"EV": [self._tie(finalized)]}), now=NOW
        )
        result, status = _result_of(conn, "A")
        assert result is None, "a tie was fabricated into an outcome"
        assert status == SETTLED_STATUS

    async def test_the_population_stays_visible_after_it_goes_quiet(
        self, conn, finalized
    ):
        """`refused` returns to zero the pass after; the gauge does not, so the
        stuck market cannot vanish from the log."""
        _market(conn, "A")
        kalshi = FakeKalshi({"EV": [self._tie(finalized)]})
        first = await run_market_result_pass(conn, kalshi, now=NOW)
        assert first.unreadable_total == 1

        second = await run_market_result_pass(conn, kalshi, now=NOW + 1)
        assert second.refused == 0
        assert second.unreadable_total == 1
        assert second.as_dict()["unreadable_total"] == 1

    def test_count_unreadable_ignores_a_market_that_settled_normally(
        self, conn
    ):
        _market(conn, "A", result="yes", status=SETTLED_STATUS)
        assert count_unreadable(conn) == 0

    async def test_a_sibling_still_pending_keeps_its_event_queried(
        self, conn, finalized
    ):
        """A refused market must not take the rest of its fixture with it."""
        _market(conn, "A", event="EV")
        _market(conn, "B", event="EV")
        tie = self._tie(finalized, ticker="A")
        unsettled = dict(finalized[0], ticker="B", status="active", result="")
        kalshi = FakeKalshi({"EV": [tie, unsettled]})

        await run_market_result_pass(conn, kalshi, now=NOW)
        second = await run_market_result_pass(conn, kalshi, now=NOW + 1)

        assert kalshi.asked == ["EV", "EV"]
        assert second.markets_pending == 1
        assert second.still_unresolved == 1
        assert second.refused == 0

    async def test_the_error_list_in_the_log_line_is_bounded(self, conn):
        """The counts dict rides inside one merged `pass N ok` record, so an
        unbounded list makes a bad minute unreadable rather than informative."""
        events = [f"EV{i}" for i in range(MAX_REPORTED_ERRORS + 4)]
        for i, event in enumerate(events):
            _market(conn, f"T{i}", event=event, commence_ms=COMMENCE - i)
        counts = await run_market_result_pass(
            conn, FakeKalshi({}, fail=set(events)), now=NOW
        )
        assert len(counts.errors) == len(events)
        reported = counts.as_dict()["errors"]
        assert len(reported) == MAX_REPORTED_ERRORS + 1
        assert reported[-1].endswith("more")


class TestAMalformedPayloadIsCountedNotRaised:
    """Finding C. The per-event `try` wrapped only the `await`; the dict
    comprehension after it was unguarded. A raise escaping here is not one bad
    pass -- `tempo.completed_full_pass` runs after this, so the loop re-runs the
    same full pass into the same deterministic raise until `LoopFailed` takes
    the container down, and the same row is still in the same volume on
    restart."""

    async def test_a_bare_list_of_strings_does_not_escape(self, conn):
        _market(conn, "A")
        counts = await run_market_result_pass(
            conn, FakeKalshi({"EV": ["not-a-market"]}), now=NOW
        )
        assert counts.errors and "not a dict" in counts.errors[0]
        assert counts.recorded == 0

    async def test_none_does_not_escape(self, conn):
        _market(conn, "A")
        counts = await run_market_result_pass(
            conn, FakeKalshi({"EV": None}), now=NOW
        )
        assert counts.errors and "not a list" in counts.errors[0]

    async def test_one_malformed_event_does_not_stop_the_others(
        self, conn, finalized
    ):
        good = dict(finalized[0], ticker="B", event_ticker="EV2")
        _market(conn, "A", event="EV1")
        _market(conn, "B", event="EV2")
        counts = await run_market_result_pass(
            conn, FakeKalshi({"EV1": None, "EV2": [good]}), now=NOW
        )
        assert counts.recorded == 1
        assert _result_of(conn, "B")[0] == good["result"]

    def test_the_shape_check_names_what_arrived(self):
        with pytest.raises(TypeError, match="not a list"):
            markets_by_ticker(None, wanted={"A"})
        with pytest.raises(TypeError, match="not a dict"):
            markets_by_ticker(["A"], wanted={"A"})

    def test_a_well_formed_payload_is_unaffected(self, finalized):
        wanted = {finalized[0]["ticker"]}
        indexed = markets_by_ticker(list(finalized), wanted=wanted)
        assert set(indexed) == wanted


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
        # The two bounds, reported before they have ever bitten. A bound that
        # only appears in the log the day it drops something reads as no bound
        # at all until then.
        assert reported["unreadable_total"] == 0
        assert reported["abandoned_total"] == 0


class TestTheThresholdsAreTunableAndCannotKillTheContainer:
    """Both bounds move by environment, and neither can raise.

    `MarketResultConfig.load()` runs inside `scripts/run_loop.py`, which
    `docker/entrypoint.sh` supervises with `wait -n`. A `ConfigError` there is a
    container crash loop clearable only with `flyctl secrets unset` -- a laptop
    job, and this tool is operated from a phone. That is the composition
    `RETIRED_SETTINGS` already records, and it applies to any new setting on
    this path. Announced, never enforced.
    """

    def test_the_ask_window_is_read_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("MARKET_RESULT_MIN_AGE_S", "60")
        monkeypatch.setenv("MARKET_RESULT_MAX_AGE_S", "86400")
        config = MarketResultConfig.load()
        assert config.min_age_after_commence_s == 60
        assert config.max_age_after_commence_ms == 86_400_000

    def test_the_per_pass_request_cap_is_read_from_the_environment(
        self, monkeypatch
    ):
        """The audit's point: with the cap a compile-time constant and the loop
        passing no value, a chatty pass had no throttle short of a deploy."""
        monkeypatch.setenv("MARKET_RESULT_MAX_EVENTS_PER_PASS", "25")
        assert MarketResultConfig.load().max_events_per_pass == 25

    def test_unset_means_uncapped_and_is_not_zero(self, monkeypatch):
        monkeypatch.delenv("MARKET_RESULT_MAX_EVENTS_PER_PASS", raising=False)
        assert MarketResultConfig.load().max_events_per_pass is None

    def test_a_cap_of_zero_is_refused_rather_than_meaning_ask_nothing(
        self, monkeypatch, caplog
    ):
        monkeypatch.setenv("MARKET_RESULT_MAX_EVENTS_PER_PASS", "0")
        with caplog.at_level(logging.ERROR, logger="backend.config"):
            config = MarketResultConfig.load()
        assert config.max_events_per_pass is None
        assert caplog.records

    def test_garbage_announces_and_falls_back_instead_of_raising(
        self, monkeypatch, caplog
    ):
        monkeypatch.setenv("MARKET_RESULT_MIN_AGE_S", "two hours")
        with caplog.at_level(logging.ERROR, logger="backend.config"):
            config = MarketResultConfig.load()
        assert config.min_age_after_commence_s == DEFAULTS.min_age_after_commence_s
        assert any(
            "MARKET_RESULT_MIN_AGE_S" in r.getMessage() for r in caplog.records
        ), "a value that is not read must say so, or it is silently ignored"

    def test_an_inverted_window_announces_and_uses_both_defaults(
        self, monkeypatch, caplog
    ):
        """Max below min would abandon every market on the exchange, quietly."""
        monkeypatch.setenv("MARKET_RESULT_MIN_AGE_S", "86400")
        monkeypatch.setenv("MARKET_RESULT_MAX_AGE_S", "60")
        with caplog.at_level(logging.ERROR, logger="backend.config"):
            config = MarketResultConfig.load()
        assert config == DEFAULTS
        assert caplog.records

    def test_no_value_of_any_kind_can_raise(self, monkeypatch):
        """The claim that matters for the container, asserted directly."""
        for value in ["", "0", "-1", "nonsense", "1e9", " ", "999999999999"]:
            monkeypatch.setenv("MARKET_RESULT_MIN_AGE_S", value)
            monkeypatch.setenv("MARKET_RESULT_MAX_AGE_S", value)
            monkeypatch.setenv("MARKET_RESULT_MAX_EVENTS_PER_PASS", value)
            assert MarketResultConfig.load() is not None


class TestResultCoverageSeparatesStatesThatLookAlike:
    """`recorded_total == 0` has three causes needing opposite responses.

    The whole reason this report exists is that the pass announced itself only
    through `flyctl logs`, so a pass that stopped writing was invisible from a
    phone. A report that collapsed "broken" into "nothing to do" would
    reproduce that invisibility with a screen in front of it.

    Each assertion is anchored where a wrong implementation gives a *different*
    answer, per `tasks/lessons.md` -- an anchor both implementations satisfy
    proves nothing.
    """

    def test_an_unresolved_game_in_the_window_is_the_alarm(self, conn):
        _market(conn, "T1", commence_ms=COMMENCE)
        cov = result_coverage(conn, now=NOW)
        assert cov["verdict"] == "NOT RECORDING"
        assert cov["recorded_total"] == 0
        assert cov["pending_total"] == 1

    def test_a_game_too_recent_to_ask_about_is_not_the_alarm(self, conn):
        """The discriminating case: also zero recorded, and healthy."""
        _market(conn, "T1", commence_ms=NOW - 60_000)
        cov = result_coverage(conn, now=NOW)
        assert cov["verdict"] == "nothing due yet"
        assert cov["recorded_total"] == 0
        assert cov["too_new_total"] == 1
        assert cov["pending_total"] == 0

    def test_an_empty_table_is_not_the_alarm_either(self, conn):
        cov = result_coverage(conn, now=NOW)
        assert cov["verdict"] == "no games in scope"
        assert cov["recorded_total"] == 0

    def test_one_recorded_outcome_flips_the_verdict(self, conn):
        _market(conn, "T1", result="yes", commence_ms=COMMENCE)
        _market(conn, "T2", event="EV2", commence_ms=COMMENCE)
        cov = result_coverage(conn, now=NOW)
        assert cov["verdict"] == "recording"
        assert cov["recorded_total"] == 1
        assert cov["recorded_by_outcome"] == {"yes": 1}
        # ...and the outstanding one is still counted. A verdict of "recording"
        # must not hide a backlog.
        assert cov["pending_total"] == 1

    def test_every_verdict_carries_its_own_meaning(self, conn):
        """The verdict and its explanation cannot drift apart if they are one
        lookup. A bare string on a screen gets misread; this repo has the scar
        of a correct statistic printed beside a contradicting verdict."""
        cov = result_coverage(conn, now=NOW)
        assert cov["verdict_meaning"]
        assert isinstance(cov["verdict_meaning"], str)


class TestResultCoverageMakesTheRollingLossVisible:
    """Abandonment is permanent, and the number worth acting on is the one for
    markets that have *not* aged out yet."""

    def test_an_aged_out_market_is_counted_and_named(self, conn):
        _market(conn, "OLD", commence_ms=LONG_AGO)
        cov = result_coverage(conn, now=NOW)
        assert cov["abandoned_total"] == 1
        assert cov["abandoned_oldest"] and "OLD" in cov["abandoned_oldest"]
        # Not double-counted as routine backlog. One bucket over a game in the
        # 7th inning and a game lost six months ago cannot show a leak.
        assert cov["pending_total"] == 0

    def test_a_market_about_to_age_out_is_flagged_before_it_is_lost(self, conn):
        """The forward-looking number. Anchored so a wrong bound differs: this
        game is inside the window (so `pending`) *and* within a day of the
        cutoff (so `expiring_soon`)."""
        about_to_go = NOW - DEFAULTS.max_age_after_commence_ms + 3_600_000
        _market(conn, "SOON", commence_ms=about_to_go)
        cov = result_coverage(conn, now=NOW)
        assert cov["pending_total"] == 1
        assert cov["expiring_soon_total"] == 1
        assert cov["abandoned_total"] == 0

    def test_a_fresh_game_is_not_flagged_as_expiring(self, conn):
        """The pair that stops `expiring_soon` collapsing into `pending`."""
        _market(conn, "FRESH", commence_ms=COMMENCE)
        cov = result_coverage(conn, now=NOW)
        assert cov["pending_total"] == 1
        assert cov["expiring_soon_total"] == 0

    def test_an_unreadable_market_is_a_standing_gauge_not_a_backlog(self, conn):
        """`finalized` with a NULL result: asked once, refused once, and then
        invisible to the per-pass counter. It must not read as routine work."""
        _market(conn, "TIE", commence_ms=COMMENCE, status=SETTLED_STATUS)
        cov = result_coverage(conn, now=NOW)
        assert cov["unreadable_total"] == 1
        assert cov["pending_total"] == 0

    def test_the_report_ignores_the_work_list_cap(self, conn):
        """`markets_awaiting_result` caps events because it is building a work
        list. A population count that inherited that cap would understate the
        backlog exactly when the backlog is what has gone wrong."""
        for i in range(5):
            _market(conn, f"T{i}", event=f"EV{i}", commence_ms=COMMENCE)
        capped = markets_awaiting_result(conn, now=NOW, max_events=2)
        assert capped.market_count == 2
        assert result_coverage(conn, now=NOW)["pending_total"] == 5


class TestAnEmptyQueueIsNotAClaimOfHealth:
    """Found by running it rather than by reading it.

    On a database with nine aged-out markets and nothing outstanding, the first
    version returned `verdict = "no games in scope"` with meaning text reading
    "Also healthy" -- beside `abandoned_total: 9`. Nine permanently lost
    outcomes reported as health, which is the exact failure `tasks/lessons.md`
    records as a correct statistic printed next to a contradicting verdict.

    The fix is two axes: `verdict` says whether the writer works, `attention`
    says whether anything is being lost. They are independent, and both are
    derived from the same counts so neither can contradict them.
    """

    def test_aged_out_outcomes_are_never_reported_as_health(self, conn):
        _market(conn, "LOST", commence_ms=LONG_AGO)
        cov = result_coverage(conn, now=NOW)
        assert cov["verdict"] == "no games in scope"
        assert cov["attention"], (
            "nine lost outcomes read as an empty queue and nothing else; the "
            "standing loss must appear without being looked for"
        )
        assert "unrecoverable" in " ".join(cov["attention"])
        assert "healthy" not in cov["verdict_meaning"].lower()

    def test_a_clean_database_raises_nothing(self, conn):
        """The pair. If `attention` is non-empty on a clean table it is noise,
        and noise is what gets ignored on the day it matters."""
        _market(conn, "OK", result="yes", commence_ms=COMMENCE)
        cov = result_coverage(conn, now=NOW)
        assert cov["verdict"] == "recording"
        assert cov["attention"] == []

    def test_recording_and_losing_are_reported_together(self, conn):
        """The state the single-axis version could not express at all: the
        writer is working *and* a backlog is aging out behind it."""
        _market(conn, "DONE", result="no", commence_ms=COMMENCE)
        _market(conn, "LOST", event="EV2", commence_ms=LONG_AGO)
        cov = result_coverage(conn, now=NOW)
        assert cov["verdict"] == "recording"
        assert cov["recorded_total"] == 1
        assert cov["abandoned_total"] == 1
        assert cov["attention"]

    def test_an_unreadable_market_names_itself_rather_than_sitting_at_a_count(
        self, conn
    ):
        _market(conn, "TIE", commence_ms=COMMENCE, status=SETTLED_STATUS)
        cov = result_coverage(conn, now=NOW)
        assert any("not yes or no" in a for a in cov["attention"])
