"""The reconciliation harness's guards, each verified by watching it refuse.

`scripts/reconcile_candle_ask.py` answers ADR 0016 §3.3 -- does a candle's
published `yes_ask.close` equal the ask the live path derives from the NO bid?
Its answer is only worth anything if the *exclusions* work, because every one of
them exists to stop a market being compared when the comparison would be
meaningless:

- a book read at one instant against a bar that averages an interval
- a bar whose level moved inside the interval
- a side of the book that is empty, where the live path returns `None` and a
  candle does not

An exclusion that silently fails admits a market whose apparent (dis)agreement
is really a price change. That is the same shape as the whole project's
recurring defect -- a plausible value where there should be a refusal -- so each
guard below is tested by constructing the state it exists to reject and
asserting the verdict names it.

Wire-format claims load `tests/fixtures/` captures, never hand-built payloads.
The hand-built dicts here are *state machine* inputs to `compare`, which is pure
logic over already-parsed tenths and has no wire contract of its own.

What these tests do NOT establish
---------------------------------
- **That candles and derived asks agree.** That is a measurement, not a test;
  it needs the network and it is recorded in
  `docs/measurements/2026-08-09-candle-ask-reconciliation.md`. These tests only
  establish that the harness would have *noticed* a disagreement.
- **That the bracket timing is correct.** The arithmetic that places bars
  between two book reads runs inside `run()` against the wall clock and is not
  exercised here; the harness's own CONTROL row is what checks it at runtime.
- **That Kalshi's wire format is what the fixture says.** The fixture pins a
  capture from one day. It cannot notice a rename that happens tomorrow.
"""

from __future__ import annotations

from conftest import load_fixture
from scripts.reconcile_candle_ask import (
    Bar,
    Book,
    best_bid,
    compare,
    parse_bar,
    spread_by_volume,
)


def _book(ticker="T", yes=500, no=490) -> Book:
    return Book(ticker, 0, yes, no, 1.0, 1.0)


def _bar(end=60, bid=500, ask=510) -> Bar:
    """A flat bar: the level never moved inside the interval."""
    bar = Bar(end_period_ts=end)
    for group, value in (("yes_bid", bid), ("yes_ask", ask)):
        target = getattr(bar, group)
        for name in ("open", "high", "low", "close"):
            target[name] = value
    return bar


def _row(stratum="game", structure="linear_cent", volume="1.0") -> dict:
    return {
        "ticker": "T",
        "series": "S",
        "stratum": stratum,
        "market": {"price_level_structure": structure, "volume_fp": volume},
    }


class TestBestBidRefusesRatherThanGuessing:
    def test_empty_side_is_none_not_zero(self):
        """No bid is not a free fill.

        `(0, 0.0)` would flow into `derive_yes_ask` as a real 0c bid and produce
        a $1.00 ask out of nothing. CLAUDE.md: unreadable resolves to None so
        the caller refuses.
        """
        assert best_bid([]) == (None, None)
        assert best_bid(None) == (None, None)

    def test_takes_the_highest_bid_not_the_last_level(self):
        """The captured book happens to be ascending; the code must not rely on it.

        Kalshi returns levels ascending, so `levels[-1]` is right today. This
        asserts the max is taken, so a day Kalshi reverses the order does not
        silently return the *worst* bid -- a wrong price that looks entirely
        plausible.
        """
        book = load_fixture("market_single.json")["orderbook"]["orderbook_fp"]
        forward, _ = best_bid(book["yes_dollars"])
        reversed_order, _ = best_bid(list(reversed(book["yes_dollars"])))
        assert forward == reversed_order

    def test_matches_the_market_objects_own_published_bid(self):
        """The book's best bid is the same number the market summary publishes.

        Cross-checks the side keys (`yes_dollars` / `no_dollars`, *not* the
        socket's `*_fp` names) against an independent field in the same capture.
        A wrong key would return None here rather than a plausible number.
        """
        fixture = load_fixture("market_single.json")
        book = fixture["orderbook"]["orderbook_fp"]
        single = fixture["single"]["market"]
        from backend.core.prices import dollars_to_tenths

        assert best_bid(book["yes_dollars"])[0] == dollars_to_tenths(
            single["yes_bid_dollars"]
        )
        assert best_bid(book["no_dollars"])[0] == dollars_to_tenths(
            single["no_bid_dollars"]
        )

    def test_the_derived_ask_identity_holds_on_the_captured_book(self):
        """`1000 - best_no_bid` reproduces the market object's published ask.

        This is the identity ADR 0016 §3.3 asks about, on the *market* payload
        where it is already known to hold. It is the fixed point the live
        measurement extends to candles.
        """
        from backend.core.prices import dollars_to_tenths
        from backend.store.db import derive_yes_ask

        fixture = load_fixture("market_single.json")
        book = fixture["orderbook"]["orderbook_fp"]
        single = fixture["single"]["market"]
        assert derive_yes_ask(best_bid(book["no_dollars"])[0]) == dollars_to_tenths(
            single["yes_ask_dollars"]
        )


class TestParseBarReadsTheWireNotMemory:
    def test_close_dollars_parses_to_tenths_on_a_real_capture(self):
        """`close_dollars`, not `close`.

        `parse_candlestick`'s docstring records reading `close` and returning
        None for both sides of every candle ever fetched, which pinned the live
        CLV counter at zero while every stage reported success. This harness
        delegates to that same function, so this test pins the delegation.
        """
        fixture = load_fixture("candlesticks_mlb.json")
        market = next(iter(fixture["markets"].values()))
        bar = parse_bar(market["candlesticks"][0])
        assert bar.yes_bid["close"] == 330
        assert bar.yes_ask["close"] == 340
        assert bar.end_period_ts == 1786137900

    def test_ohlc_is_parsed_for_the_constancy_test(self):
        fixture = load_fixture("candlesticks_mlb.json")
        market = next(iter(fixture["markets"].values()))
        bar = parse_bar(market["candlesticks"][0])
        for name in ("open", "high", "low", "close"):
            assert bar.yes_ask[name] == 340

    def test_a_bar_with_no_ask_block_is_not_flat(self):
        """Four equal absences must not pass a constancy test.

        A market that barely traded can return a candle with no `yes_ask`. If
        `flat` compared `None == None == None == None` it would return True and
        the bar would enter the comparison carrying nothing.
        """
        bar = parse_bar({"end_period_ts": 60, "yes_bid": {"close_dollars": "0.5000"}})
        assert bar.yes_ask["close"] is None
        assert bar.flat("yes_ask") is False
        assert bar.flat("yes_bid") is False  # open/high/low absent


class TestTheExclusionsActuallyFire:
    """Each guard is given the state it exists to reject."""

    def test_a_quote_that_stood_still_is_compared(self):
        """The baseline. If this fails, every exclusion below proves nothing."""
        result = compare(_row(), _book(), _book(), [_bar(bid=500, ask=510)])
        assert result.verdict == "compared"
        assert result.bid_delta == 0
        assert result.ask_delta == 0

    def test_a_book_that_moved_between_reads_is_excluded(self):
        """Disabling this admits a price change dressed as a construction error."""
        moved = compare(_row(), _book(no=490), _book(no=480), [_bar()])
        assert moved.verdict == "book_moved"
        assert moved.ask_delta is None

    def test_a_bar_whose_level_moved_inside_the_interval_is_excluded(self):
        """Two book reads cannot see a move-and-return; the bar's OHLC can.

        The book is identical at both reads, so the `book_moved` guard passes
        this through. Only the flatness check catches it -- which is why both
        exist.
        """
        bar = _bar(ask=510)
        bar.yes_ask["high"] = 530
        result = compare(_row(), _book(), _book(), [bar])
        assert result.verdict == "bar_not_flat"

    def test_bars_that_disagree_with_each_other_are_excluded(self):
        """Each bar flat, but at different levels: the quote moved between them."""
        result = compare(
            _row(), _book(), _book(), [_bar(end=60, ask=510), _bar(end=120, ask=520)]
        )
        assert result.verdict in ("bar_not_flat", "bars_disagree")
        assert result.ask_delta is None

    def test_a_one_sided_book_is_excluded_and_named(self):
        """Named as its own state, not folded into `book_moved`.

        This is the case where the live path returns `None` and a candle does
        not, so the census that counts it is the one that finds the divergence.
        """
        result = compare(_row(), _book(no=None), _book(no=None), [_bar()])
        assert result.verdict == "one_sided_book"
        assert result.derived_yes_ask is None

    def test_no_bars_is_not_agreement(self):
        result = compare(_row(), _book(), _book(), [])
        assert result.verdict == "no_bars"
        assert result.ask_delta is None


class TestTheTestWouldNoticeADisagreement:
    def test_an_off_by_one_tick_ask_is_reported_not_absorbed(self):
        """The whole point. A one-tick error is the size that decides a 4c edge."""
        result = compare(_row(), _book(no=490), _book(no=490), [_bar(ask=520)])
        assert result.verdict == "compared"
        assert result.derived_yes_ask == 510
        assert result.ask_delta == 10

    def test_the_control_is_independent_of_the_test(self):
        """A wrong bar bid shows up on the control while the ask still agrees.

        Without this, a broken bracket would look like an ask disagreement.
        """
        result = compare(_row(), _book(yes=500, no=490), _book(yes=500, no=490),
                         [_bar(bid=490, ask=510)])
        assert result.ask_delta == 0
        assert result.bid_delta == -10

    def test_deci_cent_prices_survive_the_comparison_in_tenths(self):
        """An off-whole-cent price must compare exactly, not round to a cent.

        ~25% of Kalshi markets tick in deci-cents. Money is integer tenths
        everywhere in the risk path; a float dollar round-trip here would make
        a real half-cent disagreement vanish.
        """
        result = compare(_row(), _book(yes=845, no=113), _book(yes=845, no=113),
                         [_bar(bid=845, ask=887)])
        assert result.derived_yes_ask == 887
        assert result.ask_delta == 0


class TestSamplingCoversTheRangeRatherThanTheTop:
    def test_it_spreads_across_volume_instead_of_taking_the_fattest(self):
        """Sampling the top would answer the question only where it is easiest."""
        rows = [
            {"ticker": str(i), "market": {"volume_fp": str(i)}} for i in range(100)
        ]
        picked = spread_by_volume(rows, 5)
        volumes = [float(r["market"]["volume_fp"]) for r in picked]
        assert len(picked) == 5
        assert min(volumes) < 10
        assert max(volumes) > 70

    def test_it_takes_everything_when_the_universe_is_small(self):
        rows = [{"ticker": "a", "market": {"volume_fp": "1"}}]
        assert spread_by_volume(rows, 50) == rows

    def test_an_unparseable_volume_does_not_abort_the_sample(self):
        rows = [
            {"ticker": "a", "market": {"volume_fp": None}},
            {"ticker": "b", "market": {"volume_fp": "5"}},
        ]
        assert len(spread_by_volume(rows, 2)) == 2
