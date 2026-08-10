"""Round three's band watcher: does it say "placeable" only when it is?

`scripts/watch_fee_bands.py` is the instrument Joe reads on his phone before
spending the $5.00 authorised on 2026-08-10. It had **no tests at all** while it
watched round two's bands, which is the shape `tasks/lessons.md` records seven
times over: a guard nobody has seen go red.

Every assertion below was observed red under a named mutation. The mutations are
listed beside the tests they kill so a future edit can re-run them.

WHERE THE PAYLOADS COME FROM
----------------------------
`base_market()` starts from a **captured** Kalshi market
(`tests/fixtures/events_sports_nested.json`) and overrides only the three fields
under test -- the ask, the displayed size and `occurrence_datetime`. Nothing is
hand-constructed from scratch, so no key the real payload carries is smoothed
away, and the string-typed money fields (`'0.0100'`, not `0.01`) stay strings.
That typing is not incidental: reading them as floats is how the old integer-cent
field names silently became `None`.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **Nothing about fill probability.** Every quantity here is a *displayed* ask at
  a *displayed* size. Registration §0.4e states that no quote record separates
  real resting liquidity from a maker who pulls, and these tests inherit that
  limit exactly. A green suite means the watcher reports the board faithfully,
  not that an order would fill.
- **Nothing about whether the bands occur.** That is the census
  (`2026-08-10-price-band-reachability-census-result.md`), and it is a different
  document measured on a different population.
- **Nothing about live behaviour.** The network is never touched: `sweep()` is
  driven through a stub client. A green suite says the decision logic is right,
  not that Kalshi's board is reachable from Joe's phone.
- **Nothing about cell `W`'s activation.** Q-W (§1.3) reads the live record and
  cannot run here; the tests pin only that the watcher *reports its own
  ignorance* rather than resolving it.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conftest import load_fixture
from scripts.watch_fee_bands import (
    CELLS,
    OCCURRENCE_OFFSET_MS,
    Cell,
    Hit,
    SweepResult,
    as_cents,
    is_pregame,
    minutes_to_start,
    parse_iso_ms,
    report,
    sweep,
    true_start_ms,
    wnba_cell,
)

NOW_MS = 1_786_000_000_000  # 2026-08-05T21:46:40Z -- fixed, never `now()`.

ROOT = Path(__file__).resolve().parent.parent


def _captured_market() -> dict:
    """One real captured Kalshi market dict, as the wire sends it."""
    payload = load_fixture("events_sports_nested.json")
    events = payload if isinstance(payload, list) else payload["events"]
    for event in events:
        for market in event.get("markets") or []:
            if "yes_ask_dollars" in market and "occurrence_datetime" in market:
                return market
    raise AssertionError("no captured market carried the fields under test")


def base_market(
    *,
    ticker: str = "KXTEST-1-A",
    ask_c: float | None = 8.0,
    size: float | None = 50.0,
    starts_in_minutes: float | None = 120.0,
    status: str = "active",
) -> dict:
    """A captured market with only the fields under test overridden.

    `starts_in_minutes` is minutes from `NOW_MS` to **true first pitch**; the
    stored `occurrence_datetime` is that plus Kalshi's 3-hour lateness, so the
    fixture exercises the offset rather than assuming it away. `None` removes
    the field entirely, which is the unreadable case.
    """
    market = copy.deepcopy(_captured_market())
    market["ticker"] = ticker
    market["status"] = status

    if ask_c is None:
        market.pop("yes_ask_dollars", None)
    else:
        market["yes_ask_dollars"] = f"{ask_c / 100.0:.4f}"

    if size is None:
        market.pop("yes_ask_size_fp", None)
    else:
        market["yes_ask_size_fp"] = f"{size:.2f}"

    if starts_in_minutes is None:
        market.pop("occurrence_datetime", None)
    else:
        stamp_ms = (
            NOW_MS + int(starts_in_minutes * 60_000) + OCCURRENCE_OFFSET_MS
        )
        market["occurrence_datetime"] = (
            datetime.fromtimestamp(stamp_ms / 1000, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    return market


def cell(name: str) -> Cell:
    for c in CELLS:
        if c.name == name:
            return c
    raise AssertionError(f"no registered cell named {name}")


class StubClient:
    """Stands in for `httpx.AsyncClient` at the two functions `sweep` calls.

    `sweep` is driven by monkeypatching `open_events` and `markets`, so this
    object only has to exist. Keeping it inert is deliberate: a stub that
    answered HTTP would let a test pass while the real call shape was wrong.
    """


@pytest.fixture
def board(monkeypatch):
    """Install a board: {series: [(event_ticker, [market, ...]), ...]}."""

    def install(layout: dict[str, list[tuple[str, list[dict]]]]):
        async def fake_open_events(client, series):
            return [ev for ev, _ in layout.get(series, [])]

        async def fake_markets(client, event_ticker):
            for events in layout.values():
                for ev, ms in events:
                    if ev == event_ticker:
                        return ms
            return []

        monkeypatch.setattr("scripts.watch_fee_bands.open_events", fake_open_events)
        monkeypatch.setattr("scripts.watch_fee_bands.markets", fake_markets)

    return install


# ---------------------------------------------------------------------------
# The bands, exactly as §1.1 registers them
# ---------------------------------------------------------------------------


class TestBandEdgesAreInclusive:
    """M1: change either `<=` in `Cell.matches` to `<` and these go red."""

    @pytest.mark.parametrize(
        "name,lo,hi",
        [("S1", 6.0, 15.0), ("S2", 6.0, 13.0), ("S3", 27.0, 39.0), ("R-pass1", 47.0, 52.0)],
    )
    def test_both_edges_are_inside_the_band(self, name, lo, hi):
        c = cell(name)
        assert c.matches(lo, 10_000) is True
        assert c.matches(hi, 10_000) is True

    @pytest.mark.parametrize(
        "name,lo,hi",
        [("S1", 6.0, 15.0), ("S2", 6.0, 13.0), ("S3", 27.0, 39.0), ("R-pass1", 47.0, 52.0)],
    )
    def test_one_tick_outside_either_edge_is_refused(self, name, lo, hi):
        c = cell(name)
        assert c.matches(lo - 1.0, 10_000) is False
        assert c.matches(hi + 1.0, 10_000) is False


class TestTheExcludedTicksAreRefused:
    """M2: delete the `skip_c` clause and every one of these goes red.

    These prices are excluded because at them the cell lands exactly on the
    $0.0001 fee grid under both candidate rates, so the fill discriminates no
    rounding rule. That is the flaw that made round one's ATP cell unable to
    test anything -- a watcher that surfaces one has cost the round a cell.
    """

    @pytest.mark.parametrize(
        "name,tick",
        [
            ("S1", 10.0),
            ("S2", 10.0),
            ("S1+S2", 10.0),
            ("S3", 30.0),
            ("R-pass1", 50.0),
            ("R-pass2", 30.0),
            ("R-pass2", 40.0),
            ("R-pass2", 50.0),
        ],
    )
    def test_excluded_tick_never_matches(self, name, tick):
        c = cell(name)
        assert c.lo_c <= tick <= c.hi_c, "the tick must be inside the band to be a real test"
        assert c.matches(tick, 10_000) is False

    def test_a_deci_cent_away_from_an_excluded_tick_still_matches(self):
        """The exclusion is the tick, not a neighbourhood.

        ~25% of Kalshi markets tick in deci-cents, so 10.1c is a real price and
        is inside `S1`'s band. Widening the exclusion to a range would silently
        shrink a registered band.
        """
        assert cell("S1").matches(10.1, 10_000) is True
        assert cell("S1").matches(9.9, 10_000) is True


class TestDisplayedDepth:
    """M3: change `size >= self.min_size` to `>` and the at-threshold cases die."""

    def test_s2_needs_twenty_and_nineteen_is_refused(self):
        assert cell("S2").matches(8.0, 20) is True
        assert cell("S2").matches(8.0, 19) is False

    def test_the_shared_market_needs_twenty_one(self):
        """`S1` buys 1 and `S2` buys 20 in the same market, so 21 total.

        20 is enough for `S2` alone and NOT enough for the shared market. A
        watcher that offered a 20-deep market as `S1+S2` would send Joe to a
        market that cannot serve both orders.
        """
        assert cell("S1+S2").matches(8.0, 21) is True
        assert cell("S1+S2").matches(8.0, 20) is False

    def test_single_contract_cells_need_one(self):
        for name in ("S1", "S3", "R-pass1", "R-pass2"):
            assert cell(name).matches(cell(name).lo_c, 1) is True
            assert cell(name).matches(cell(name).lo_c, 0) is False


class TestAnUnreadableQuoteIsRefusedNotTreatedAsZero:
    """M4: return `True` on `None` and both go red.

    `CLAUDE.md`: unreadable resolves to `None`, never `0`; callers refuse rather
    than substitute. A `None` ask coerced to 0 would fall inside every low band.
    """

    def test_none_ask_is_refused(self):
        assert cell("S1").matches(None, 10_000) is False

    def test_none_size_is_refused(self):
        assert cell("S1").matches(8.0, None) is False

    def test_as_cents_returns_none_rather_than_zero(self):
        assert as_cents(None) is None
        assert as_cents("") is None
        assert as_cents("not-a-price") is None
        assert as_cents("0.0800") == 8.0


# ---------------------------------------------------------------------------
# Pre-game, and the 3-hour lateness
# ---------------------------------------------------------------------------


class TestPreGameUsesTheThreeHourOffset:
    """M5: drop `- OCCURRENCE_OFFSET_MS` from `true_start_ms` and these go red.

    Kalshi's `occurrence_datetime` runs exactly 3 hours late (ADR 0006). A
    watcher that trusted the raw stamp would call a game pre-game for three
    hours after first pitch -- and an in-play fill VOIDS its cell under P8.
    """

    def test_a_market_whose_stamp_is_ahead_but_whose_game_started_is_in_play(self):
        # Stored stamp is NOW + 2h, so true first pitch was NOW - 1h.
        market = base_market(starts_in_minutes=-60.0)
        assert parse_iso_ms(market["occurrence_datetime"]) > NOW_MS
        assert is_pregame(market, NOW_MS) is False

    def test_a_market_starting_in_two_hours_is_pregame(self):
        assert is_pregame(base_market(starts_in_minutes=120.0), NOW_MS) is True

    def test_true_start_is_the_stamp_minus_three_hours(self):
        market = base_market(starts_in_minutes=90.0)
        stamp = parse_iso_ms(market["occurrence_datetime"])
        assert true_start_ms(market) == stamp - OCCURRENCE_OFFSET_MS

    def test_minutes_to_start_counts_to_true_first_pitch(self):
        assert minutes_to_start(base_market(starts_in_minutes=45.0), NOW_MS) == pytest.approx(45.0)


class TestAnUnreadableStartTimeIsNeitherPreGameNorZero:
    """M6: make `is_pregame` return `True` on a missing stamp and this goes red.

    Both collapses are wrong and in opposite directions. `True` places an
    in-play order. `False` silently excludes every market the moment Kalshi
    renames the field -- an empty board that reads as a quiet one.
    """

    def test_missing_stamp_is_none(self):
        assert is_pregame(base_market(starts_in_minutes=None), NOW_MS) is None

    def test_unparseable_stamp_is_none_not_the_epoch(self):
        market = base_market()
        market["occurrence_datetime"] = "not-a-timestamp"
        assert parse_iso_ms(market["occurrence_datetime"]) is None
        assert true_start_ms(market) is None
        assert is_pregame(market, NOW_MS) is None

    def test_minutes_to_start_is_none_rather_than_a_huge_negative(self):
        assert minutes_to_start(base_market(starts_in_minutes=None), NOW_MS) is None


# ---------------------------------------------------------------------------
# The scan rule: FIRST in board order, and no menu
# ---------------------------------------------------------------------------


class TestTheScanTakesTheFirstQualifyingMarketInBoardOrder:
    """M7: reverse the market loop, or replace `if first is None`, and these die.

    §3: "scan in the app's default order, take the FIRST qualifying market, no
    re-scanning, no comparison between candidates, no waiting for a better
    price." Sorting by attractiveness is exactly the degree of freedom the rule
    removes, so a cheaper later market must NOT win.
    """

    async def test_the_first_wins_even_when_a_later_one_is_cheaper(self, board):
        board(
            {
                "KXMLBSPREAD": [
                    (
                        "EV1",
                        [
                            base_market(ticker="FIRST", ask_c=14.0, size=50.0),
                            base_market(ticker="CHEAPER", ask_c=7.0, size=9_000.0),
                        ],
                    )
                ],
                "KXMLBGAME": [],
            }
        )
        result = await sweep(StubClient(), (cell("S1"),), NOW_MS)
        assert [h.ticker for h in result.hits] == ["FIRST"]

    async def test_rival_candidates_are_counted_never_priced(self, board):
        """A count says the board is not one deep. A menu invites the forbidden
        comparison, so no rival's ticker or price may appear in the output."""
        board(
            {
                "KXMLBSPREAD": [
                    (
                        "EV1",
                        [
                            base_market(ticker="FIRST", ask_c=14.0),
                            base_market(ticker="RIVAL-A", ask_c=7.0),
                            base_market(ticker="RIVAL-B", ask_c=8.0),
                        ],
                    )
                ]
            }
        )
        result = await sweep(StubClient(), (cell("S1"),), NOW_MS)
        assert result.hits[0].others == 2
        rendered = report(result, None)
        assert "RIVAL-A" not in rendered and "RIVAL-B" not in rendered
        assert "FIRST" in rendered

    async def test_board_order_across_events_is_the_api_order(self, board):
        board(
            {
                "KXMLBSPREAD": [
                    ("EV1", [base_market(ticker="E1M1", ask_c=40.0)]),  # out of S1's band
                    ("EV2", [base_market(ticker="E2M1", ask_c=12.0)]),
                    ("EV3", [base_market(ticker="E3M1", ask_c=7.0)]),
                ]
            }
        )
        result = await sweep(StubClient(), (cell("S1"),), NOW_MS)
        assert result.hits[0].ticker == "E2M1"


class TestTheSweepExcludesWhatItMustAndCountsIt:
    async def test_in_play_and_unreadable_markets_are_excluded_and_counted(self, board):
        board(
            {
                "KXMLBSPREAD": [
                    (
                        "EV1",
                        [
                            base_market(ticker="STARTED", ask_c=8.0, starts_in_minutes=-30.0),
                            base_market(ticker="NOSTAMP", ask_c=8.0, starts_in_minutes=None),
                            base_market(ticker="GOOD", ask_c=8.0),
                        ],
                    )
                ]
            }
        )
        result = await sweep(StubClient(), (cell("S1"),), NOW_MS)
        assert [h.ticker for h in result.hits] == ["GOOD"]
        assert result.in_play_skipped == 1
        assert result.no_start_time == 1

    async def test_a_non_active_market_is_skipped(self, board):
        board(
            {
                "KXMLBSPREAD": [
                    (
                        "EV1",
                        [
                            base_market(ticker="CLOSED", ask_c=8.0, status="closed"),
                            base_market(ticker="OPEN", ask_c=8.0),
                        ],
                    )
                ]
            }
        )
        result = await sweep(StubClient(), (cell("S1"),), NOW_MS)
        assert [h.ticker for h in result.hits] == ["OPEN"]

    async def test_every_cell_is_scanned_because_they_are_five_orders_not_alternatives(
        self, board
    ):
        board(
            {
                "KXMLBSPREAD": [
                    (
                        "EV1",
                        [
                            base_market(ticker="LOW", ask_c=8.0, size=5_000.0),
                            base_market(ticker="MID", ask_c=32.0, size=5_000.0),
                        ],
                    )
                ],
                "KXMLBGAME": [("EV9", [base_market(ticker="GAME", ask_c=48.0)])],
            }
        )
        result = await sweep(StubClient(), CELLS, NOW_MS)
        assert {h.cell for h in result.hits} == {"S1", "S2", "S1+S2", "S3", "R-pass1", "R-pass2"}


# ---------------------------------------------------------------------------
# What the report must say out loud
# ---------------------------------------------------------------------------


def _hit(cell_name: str) -> Hit:
    return Hit(
        cell=cell_name,
        ticker="KXTEST-1-A",
        ask_c=8.0,
        size=100.0,
        mins_to_start=42.0,
        note="",
        others=0,
    )


def _result(*cell_names: str) -> SweepResult:
    return SweepResult(
        hits=[_hit(n) for n in cell_names],
        no_start_time=0,
        in_play_skipped=0,
        events_scanned=3,
    )


class TestTheReportSaysWhatIsMissing:
    """M8: delete the `R` warning branch and the first two go red.

    `R` is the round's weakest availability citation (Correction A §X3: no depth
    census, no time-of-day census, and the one adjacent figure adverse at 7%),
    and gate G1 makes its absence fatal to the whole round. Four green lines
    with `R` quietly missing is the output that wastes Joe's $5.00.
    """

    def test_missing_r_is_called_out_as_fatal(self):
        rendered = report(_result("S1", "S2", "S3"), None)
        assert "R IS NOT PLACEABLE" in rendered
        assert "G1" in rendered

    def test_r_pass_two_alone_does_not_trigger_the_warning(self):
        rendered = report(_result("R-pass2"), None)
        assert "R IS NOT PLACEABLE" not in rendered

    def test_pass_one_is_preferred_and_said_so(self):
        rendered = report(_result("R-pass1", "R-pass2"), None)
        assert "pass 1" in rendered

    def test_an_empty_board_is_not_silent(self):
        rendered = report(_result(), None)
        assert "no qualifying market" in rendered

    def test_the_shared_market_is_preferred_when_present(self):
        assert "Prefer it" in report(_result("S1", "S2", "S1+S2"), None)


class TestCellWReportsIgnoranceRatherThanResolvingIt:
    """M9: print "W: not registered" instead and this goes red.

    Q-W (§1.3) reads the live record, which this machine does not have. "No
    series passed, so `W` IS NOT REGISTERED" is a §1.3 *decision* that licenses
    §Power's four-cell enumeration. "Q-W has not been run" licenses nothing.
    Rendering the second as the first is this repo's absence-reads-as-zero
    failure aimed at a registration.
    """

    def test_without_the_flag_w_is_unresolved_not_deregistered(self):
        rendered = report(_result("S1"), None)
        assert "UNRESOLVED" in rendered
        assert "Q-W not run" in rendered
        assert "not registered" not in rendered.lower().replace("not registered'", "")

    def test_with_a_series_the_unresolved_line_is_gone(self):
        rendered = report(_result("S1", "W"), "KXWNBASPREAD")
        assert "UNRESOLVED" not in rendered

    def test_the_w_cell_carries_the_series_q_w_selected(self):
        c = wnba_cell("KXWNBATOTAL")
        assert c.series == ("KXWNBATOTAL",)
        assert (c.lo_c, c.hi_c, c.skip_c, c.min_size) == (27.0, 39.0, (30.0,), 1)

    async def test_w_is_not_scanned_unless_asked_for(self, board):
        board({"KXWNBAGAME": [("EVW", [base_market(ticker="WNBA", ask_c=32.0)])]})
        result = await sweep(StubClient(), CELLS, NOW_MS)
        assert all(h.cell != "W" for h in result.hits)


class TestAnImminentFirstPitchIsFlaggedButNeverFiltered:
    """Observed live on 2026-08-10: the first qualifying `S1` was 2m from start.

    Both halves matter and they pull opposite ways. A fill that lands after
    first pitch VOIDS its cell under P8, and the four-point check takes real
    time on a phone -- so the operator must be told. But §3's rule is take the
    FIRST qualifying market in board order, and "qualifying" is band, depth and
    not-started. Dropping one for being close to start would silently redefine
    "first", which is a change to the registration that an operator aid has no
    standing to make.

    M11: filter imminent hits out of `sweep` and the second test goes red.
    M12: delete the warning branch in `report` and the first goes red.
    """

    def test_an_imminent_start_is_called_out(self):
        hit = Hit(
            cell="S1",
            ticker="KXTEST-1-A",
            ask_c=8.0,
            size=100.0,
            mins_to_start=2.0,
            note="",
            others=0,
        )
        assert hit.is_imminent is True
        rendered = report(
            SweepResult(hits=[hit], no_start_time=0, in_play_skipped=0, events_scanned=1),
            None,
        )
        assert "STARTS SOON" in rendered
        assert "VOIDS the cell" in rendered

    async def test_an_imminent_market_is_still_the_registered_pick(self, board):
        """The 2-minute market is first in board order, so it must still win --
        even though a later one is comfortably far from its first pitch."""
        board(
            {
                "KXMLBSPREAD": [
                    (
                        "EV1",
                        [
                            base_market(ticker="IMMINENT", ask_c=8.0, starts_in_minutes=2.0),
                            base_market(ticker="ROOMY", ask_c=8.0, starts_in_minutes=180.0),
                        ],
                    )
                ]
            }
        )
        result = await sweep(StubClient(), (cell("S1"),), NOW_MS)
        assert [h.ticker for h in result.hits] == ["IMMINENT"]
        assert result.hits[0].others == 1

    def test_a_comfortable_start_is_not_flagged(self):
        hit = Hit(
            cell="S1",
            ticker="KXTEST-1-A",
            ask_c=8.0,
            size=100.0,
            mins_to_start=180.0,
            note="",
            others=0,
        )
        assert hit.is_imminent is False
        rendered = report(
            SweepResult(hits=[hit], no_start_time=0, in_play_skipped=0, events_scanned=1),
            None,
        )
        assert "STARTS SOON" not in rendered

    def test_an_unknown_start_is_not_silently_called_imminent(self):
        """`None` minutes means the stamp was unreadable, not that the game is
        about to start. Flagging it would train the operator to ignore the flag."""
        hit = Hit(
            cell="S1",
            ticker="KXTEST-1-A",
            ask_c=8.0,
            size=100.0,
            mins_to_start=None,
            note="",
            others=0,
        )
        assert hit.is_imminent is False


class TestTheReportRefusesToImplyFillability:
    """The one caveat that governs, and it must survive a copy-edit.

    §0.4e: a displayed ask at a displayed size is consistent both with real
    resting liquidity and with a maker who pulls on any incoming order. The
    whole round exists to separate those two, so the watcher must never be read
    as having done it.
    """

    def test_every_report_states_that_displayed_is_not_filled(self):
        for res in (_result(), _result("S1", "R-pass1")):
            rendered = report(res, None)
            assert "DISPLAYED" in rendered
            assert "not evidence" in rendered


class TestATruncatedSweepIsNotANo:
    """M10: catch the exception inside `sweep` and this goes red.

    An HTTP failure partway through the board yields "no qualifying market" for
    every unscanned cell. That absence is caused by our own failure and reads
    identically to a real one -- this repo's most-repeated defect shape.
    """

    async def test_a_failing_event_call_propagates_rather_than_returning_empty(
        self, monkeypatch
    ):
        async def boom(client, series):
            raise RuntimeError("429 after retries")

        monkeypatch.setattr("scripts.watch_fee_bands.open_events", boom)
        with pytest.raises(RuntimeError):
            await sweep(StubClient(), (cell("S1"),), NOW_MS)

    async def test_a_failing_market_call_propagates(self, monkeypatch):
        async def ok(client, series):
            return ["EV1"]

        async def boom(client, event_ticker):
            raise RuntimeError("500")

        monkeypatch.setattr("scripts.watch_fee_bands.open_events", ok)
        monkeypatch.setattr("scripts.watch_fee_bands.markets", boom)
        with pytest.raises(RuntimeError):
            await sweep(StubClient(), (cell("S1"),), NOW_MS)


class TestTheRegisteredCellsMatchTheRegistration:
    """A transcription guard. §1.1 is the source of truth; this is the copy.

    Round one lost a cell to a transcription slip, and a band that is wrong here
    sends Joe to buy the wrong thing with real money. Written from the
    registration table, not from the code.
    """

    def test_the_bands_are_as_registered(self):
        expected = {
            "S1": ("KXMLBSPREAD", 6.0, 15.0, (10.0,), 1),
            "S2": ("KXMLBSPREAD", 6.0, 13.0, (10.0,), 20),
            "S1+S2": ("KXMLBSPREAD", 6.0, 13.0, (10.0,), 21),
            "S3": ("KXMLBSPREAD", 27.0, 39.0, (30.0,), 1),
            "R-pass1": ("KXMLBGAME", 47.0, 52.0, (50.0,), 1),
            "R-pass2": ("KXMLBGAME", 27.0, 52.0, (30.0, 40.0, 50.0), 1),
        }
        assert {c.name for c in CELLS} == set(expected)
        for c in CELLS:
            series, lo, hi, skip, size = expected[c.name]
            assert c.series == (series,), c.name
            assert (c.lo_c, c.hi_c, c.skip_c, c.min_size) == (lo, hi, skip, size), c.name

    def test_no_cell_watches_round_twos_dead_band(self):
        """`KXMLBGAME` below 20c: 0 of 51,286 pre-game observations, cheapest
        26.0c. A cell reaching there watches for something the record says
        cannot happen, and reports "no" forever."""
        for c in CELLS:
            if c.series == ("KXMLBGAME",):
                assert c.lo_c >= 26.0, c.name


class TestThePhoneSheetAgreesWithTheRegisteredCells:
    """`docs/round-three-phone-sheet.md` is what Joe actually reads.

    **Why this is not the pattern §S13 was told off for.** That ruling —
    *"delete one of the two texts, do not test that they agree"* — is about two
    documents each claiming to be the specification. Here there is exactly one
    specification (§1.1 of the registration, mirrored in `CELLS`) and one
    **derived operator's copy**, which has to be short enough to read on a
    handset at 11pm and therefore cannot be the registration. The copy is
    checked against its source; the two are not peers.

    The failure this catches is not cosmetic. A band mistyped here sends Joe to
    buy the wrong thing with real money, and the fill is unrecoverable.
    """

    SHEET = ROOT / "docs" / "round-three-phone-sheet.md"

    def _text(self) -> str:
        return self.SHEET.read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "phrase",
        [
            "**6c – 15c** · **skip exactly 10c**",  # order 1 == S1
            "**6c – 13c** · **skip exactly 10c**",  # order 2 == S2
            "**27c – 39c** · **skip exactly 30c**",  # order 3 == S3
            "47c – 52c",  # order 4 pass 1 == R-pass1
            "27c – 52c",  # order 4 pass 2 == R-pass2
            "**27c – 39c** (skip 30c)",  # order 5 == W
        ],
    )
    def test_every_registered_band_appears_verbatim(self, phrase):
        assert phrase in self._text()

    def test_the_share_counts_are_whole_numbers_and_match_the_cells(self):
        """P5 is the round's likeliest waste: round one's app bought 0.27
        contracts. The sheet must name `1` and `20` and nothing else."""
        text = self._text()
        assert "**Shares field:** `20`" in text
        assert "**Shares field:** `1`" in text
        assert cell("S2").min_size == 20
        assert cell("S1+S2").min_size == 21

    def test_the_sheet_carries_the_four_point_check_and_the_sixty_second_rule(self):
        text = self._text()
        assert "FOUR-POINT CHECK" in text
        assert "60 seconds" in text
        assert "CANCEL IT" in text

    def test_cell_w_is_presented_as_unresolved_not_as_a_no(self):
        """The same distinction the watcher's output makes. A sheet that said
        "W is off" would license §Power's four-cell branch, which Q-W has not
        earned."""
        text = self._text()
        assert "UNRESOLVED" in text
        assert "not** the same as" in text

    def test_the_money_figures_match_the_registration(self):
        text = self._text()
        assert "$5.00" in text
        assert "−$4.27" in text
        assert "2026-08-31" in text
