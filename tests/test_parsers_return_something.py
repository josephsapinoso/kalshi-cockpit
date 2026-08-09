"""One assertion, against every captured payload: **the parser found rows.**

This project has now read the wrong wire key four times:

    data["yes"]                        vs  yes_dollars_fp          (predecessor)
    multivariate_event_collections     vs  multivariate_contracts
    competition_scope == "game"        vs  "Game"
    payload["orderbook"]               vs  orderbook_fp

Every one returned something **empty, correctly typed, and entirely
plausible** — zero levels, `[]`, six events of twenty-four, `{}`. None raised.
Between them they made the order book parse to nothing for a whole project's
life, invented "Kalshi has no combo product", silently discarded every spread
and total in the universe, and reported a market with 21,256 contracts of open
interest as unquoted.

The written rule — *capture the payload before writing the parser* — was in
place after the first and did not stop the next three. It is a rule about
diligence, and diligence is not a control. So this file is the mechanical
version, and it is one line per parser:

    the parser, run on a real capture, must return something NON-EMPTY.

That single assertion kills all four. Nothing else does: a wrong key yields a
well-formed empty collection, so every assertion written about the *contents*
of the result is vacuously satisfied, and a test suite full of them stays green.

What this file does not establish
---------------------------------
That the parsed values are **correct** — only that they exist. Correctness is
the job of the suite beside it, which is large and specific. This is the floor
underneath it, and the floor is the part that has repeatedly been missing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.kalshi.combos import parse_collection
from backend.kalshi.discovery import discover_from_events
from backend.kalshi.grid import parse_price_grid
from backend.kalshi.orderbook import OrderBook
from backend.kalshi.quotes import parse_market_quote
from backend.kalshi.rest import ORDERBOOK_KEY
from backend.settlement import read_outcome

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
TEST_SOURCES = sorted(ROOT.glob("tests/*.py")) + sorted(ROOT.glob("*.py"))


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Fixtures that are evidence rather than parser input
# ---------------------------------------------------------------------------
# Named with a reason, so an exclusion is a decision rather than an accident --
# the same rule this repo applies to the discovery classifier's rejects. Adding
# a capture and forgetting to wire it in is its own recorded failure, so the
# default has to be "something must read this".
EVIDENCE_NOT_PARSER_INPUT = {
    "occurrence_datetime_probe.json": (
        "the persisted evidence for the +3h occurrence_datetime measurement. "
        "No production code parses it; scripts/measure_occurrence_datetime.py "
        "re-derives the finding against the live API."
    ),
    "sports_coverage.json": (
        "a one-off census of how much of /events is game-level. It informed "
        "the scope decision in docs/adr/0001 and is read by nothing since."
    ),
    "combo_collections_summary.json": (
        "aggregate counts beside combo_collections.json, which is the payload "
        "capture. Read by tests/test_combos.py for the totals only."
    ),
}


class TestEveryCaptureIsReadBySomething:
    """A captured fixture that no test loads is decoration.

    Already recorded in `tasks/lessons.md` after a 392KB odds capture sat unused
    for a day while the file it was meant to replace went on being
    hand-written. The directory listing looks identical either way, so it needs
    a test rather than a habit.
    """

    def test_no_fixture_is_unread(self):
        sources = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in TEST_SOURCES
        )
        unread = [
            path.name
            for path in sorted(FIXTURES.glob("*.json"))
            if path.name not in sources
        ]
        assert not unread, (
            f"{unread} are captured and read by no test. Either wire them in "
            f"or record why they are evidence rather than input, in "
            f"EVIDENCE_NOT_PARSER_INPUT."
        )

    def test_the_exclusions_are_still_real_files(self):
        """Anchors the list against its own rot.

        A stale name in the exclusion dict excuses nothing and hides that the
        capture it referred to is gone.
        """
        for name in EVIDENCE_NOT_PARSER_INPUT:
            assert (FIXTURES / name).exists(), f"{name} no longer exists"


class TestTheParsersFindRows:
    """Each case: a real capture in, a non-empty result out.

    Written as separate tests rather than a parametrised loop so a failure
    names the parser rather than an index.
    """

    def test_discovery_finds_events(self):
        events = discover_from_events(load("events_sports_nested.json"))
        assert events, (
            "discovery parsed zero events from a real /events capture. This is "
            "the exact shape of the `competition_scope == 'game'` bug, which "
            "returned 6 of 24 and looked fine."
        )

    def test_discovery_finds_markets_under_those_events(self):
        """One level down, and it is where the scope bug actually lived.

        Events survived; every spread and total inside them was discarded. A
        count at the top level alone would have stayed green.
        """
        events = discover_from_events(load("events_sports_nested.json"))
        assert sum(len(e.markets) for e in events) > 0
        types = {m.market_type for e in events for m in e.markets}
        assert len(types) > 1, (
            f"only {types} survived classification -- a filter dropping every "
            f"spread and total looks identical to one working correctly"
        )

    def test_the_single_market_endpoint_yields_a_quote(self):
        capture = load("market_single.json")
        quote = parse_market_quote(capture["single"], observed_ms=1_000)
        assert quote.ask_tenths("yes") is not None
        assert quote.ask_tenths("no") is not None

    def test_the_rest_order_book_has_levels(self):
        """The fourth bug, pinned. `payload["orderbook"]` gave `{}` here."""
        book = load("market_single.json")["orderbook"][ORDERBOOK_KEY]
        assert book["yes_dollars"], "no YES levels"
        assert book["no_dollars"], "no NO levels"

    def test_the_socket_order_book_has_levels(self):
        """The first bug, pinned. `data["yes"]` gave 0 of 257 frames."""
        stream = load("ws_orderbook_stream.json")
        books: dict[str, OrderBook] = {}
        applied = 0
        for record in stream["frames"]:
            frame = record["frame"]
            if frame.get("type") != "orderbook_snapshot":
                continue
            message = frame.get("msg") or {}
            ticker = message.get("market_ticker")
            if not ticker:
                continue
            book = books.setdefault(ticker, OrderBook(ticker))
            book.apply_snapshot(
                message, seq=frame.get("seq"), observed_ms=record["received_ms"]
            )
            applied += 1

        assert applied, "no snapshot frame in the capture parsed at all"
        with_levels = [b for b in books.values() if b.yes_bids or b.no_bids]
        assert with_levels, (
            f"{len(books)} books parsed and every one is empty. That is the "
            f"predecessor's defect exactly: 0 of 257 frames, silently, while "
            f"every hand-written test passed."
        )

    def test_the_combo_collections_have_legs(self):
        """The second bug, pinned. The wrong envelope key gave `[]`."""
        captured = load("combo_collections.json")
        collections = [parse_collection(entry) for entry in captured.values()]
        assert collections
        assert sum(len(c.legs) for c in collections) > 0, (
            "every collection parsed to zero legs -- which is what reading "
            "`associated_events` alone produced, since it is empty on the wire "
            "for several real collections"
        )

    def test_the_priced_combinations_have_legs_and_a_price(self):
        capture = load("combo_priced_markets.json")
        assert capture["combos"]
        assert capture["legs"]
        assert all(c["mve_selected_legs"] for c in capture["combos"])

    def test_the_odds_capture_yields_quotes(self):
        """Parsed through the client, not read out of the JSON by hand.

        Counting events in the file would pass against a `_parse` that returns
        nothing, which is the failure being guarded.
        """
        from backend.odds.client import OddsClient

        capture = load("odds_mlb_h2h_spreads_totals.json")
        quotes = OddsClient._parse(
            None, capture["events"], sport_key="baseball_mlb", fetched_ms=1_000
        )
        assert quotes, "the odds parser found no quotes in a 392KB capture"
        assert {q.bookmaker for q in quotes}, "no bookmaker survived"

    def test_the_settled_markets_yield_outcomes(self):
        markets = load("markets_settled.json")["markets"]
        assert markets
        outcomes = [read_outcome(m) for m in markets]
        assert [o for o in outcomes if o is not None], (
            "no settled market produced an outcome. `?status=settled` returns "
            "markets whose `status` field reads `finalized`, so matching on "
            "'settled' would settle nothing, forever."
        )

    def test_the_settled_markets_yield_results_for_the_markets_table(self):
        """`read_market_result` is the reader `kalshi_markets.result` is written
        from, and it is a *different* function from `read_outcome` above. Both
        are asserted here because a fixture read by only one of two parsers of
        the same bytes is exactly the gap this file exists to close."""
        from backend.kalshi.discovery import read_market_result

        markets = load("markets_settled.json")["markets"]
        assert markets
        results = [read_market_result(m) for m in markets]
        assert [r for r in results if r is not None], (
            "no captured market yielded a result, so `kalshi_markets.result` "
            "would stay NULL for every row -- the state it was in for the "
            "project's entire life"
        )

    def test_the_price_grids_parse(self):
        grids = load("price_grids.json")["grids"]
        assert grids
        parsed = [
            parse_price_grid(
                entry["price_ranges"], structure=entry["price_level_structure"]
            )
            for entry in grids
        ]
        assert parsed
        assert all(grid.bands for grid in parsed), (
            "a grid with no bands accepts no price at all, so it would refuse "
            "every order on that market"
        )
        # And the bands have to admit a real price. An empty band range parses
        # into a grid object just as happily as a full one.
        assert all(grid.is_on_grid(500) for grid in parsed), (
            "50c is not on the captured grid -- the bands parsed to nothing "
            "usable"
        )

    def test_the_candlestick_capture_has_bars(self):
        markets = load("candlesticks_mlb.json")["markets"]
        assert markets
        assert any(
            entry.get("candlesticks") for entry in markets.values()
        ), "no market in the capture carries a single bar"


@pytest.mark.parametrize("name", sorted(EVIDENCE_NOT_PARSER_INPUT))
def test_an_excluded_fixture_still_carries_its_evidence(name):
    """Not a parser check -- a check that the evidence is still there.

    These are excluded from the parser table because nothing parses them. That
    is not a reason for them to be empty.
    """
    payload = load(name)
    assert payload, f"{name} is empty"
    assert len(payload) > 1, f"{name} has almost nothing in it"
