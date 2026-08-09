"""The E2 book-presence harness reads the wire, and refuses when it cannot.

The measurement this guards is a *rate of emptiness*, which is the one shape
where a wrong wire key produces a large, tidy, entirely false number instead of
an error. `KalshiRestClient.orderbook` once read `payload["orderbook"]` against
a wire that says `orderbook_fp`, and returned `{}` for every market on the
exchange without complaining -- a 100% book-empty rate that was a typo.

So these load the **captured** payloads from `tests/fixtures/combo_orderbooks.json`
(20 real books read 2026-08-09), never hand-built dicts, for anything that
asserts a field name. Hand-built payloads are how the predecessor's 305 green
tests coexisted with a parser that produced zero levels for the project's life.

What these do not establish
---------------------------
That the rate reported by the run is *right*. They establish that the parser
reads the wire Kalshi actually sent, that a renamed envelope raises instead of
reading as empty, and that an unpriceable leg is refused rather than scored.
The number itself is a measurement, not a test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))

from backend.kalshi.rest import (  # noqa: E402
    ORDERBOOK_KEY,
    MalformedOrderbookResponse,
)
from measure_combo_book_presence import (  # noqa: E402
    ECHO_TOLERANCE,
    GRID_TOL,
    Row,
    book_is_empty,
    book_signature,
    derived_yes_ask,
    derived_yes_prices,
    echo_gap,
    eligible,
    parse_levels,
    read_book,
    round_robin,
    wilson,
)

FIXTURE = _ROOT / "tests" / "fixtures" / "combo_orderbooks.json"


def captured() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestTheWireIsWhatKalshiSent:
    def test_the_envelope_key_is_orderbook_fp_on_every_captured_book(self):
        books = captured()
        assert books, "the capture is empty; it cannot pin anything"
        assert all(ORDERBOOK_KEY in entry for entry in books)

    def test_the_sides_are_yes_dollars_and_no_dollars(self):
        # Not the socket's names. Asserted against the capture rather than
        # against memory, because memory is what got this wrong three times.
        for entry in captured():
            assert set(entry[ORDERBOOK_KEY]) == {"yes_dollars", "no_dollars"}

    def test_levels_parse_out_of_the_captured_strings(self):
        # Prices and sizes arrive as STRINGS ("0.8120", "369.00"). A parser
        # that assumed floats would return nothing and read as an empty book.
        parsed = [
            parse_levels(entry[ORDERBOOK_KEY], "no_dollars")
            for entry in captured()
        ]
        assert any(parsed), "no NO level parsed out of 20 real books"
        for levels in parsed:
            for price, size in levels:
                assert 0.0 <= price <= 1.0
                assert size > 0

    def test_four_of_the_twenty_captured_books_are_genuinely_empty(self):
        # The observation this whole measurement turns on, pinned to the bytes.
        empty = [e for e in captured() if book_is_empty(e[ORDERBOOK_KEY])]
        assert len(empty) == 4

    def test_no_captured_book_has_a_yes_level(self):
        # Every non-empty book in this sample is a single resting NO bid. If a
        # later capture breaks this, the yes-side path has never been exercised
        # on real bytes and this test is the notice of that.
        assert all(
            not parse_levels(e[ORDERBOOK_KEY], "yes_dollars") for e in captured()
        )


class TestARenamedEnvelopeRaisesRatherThanReadingAsEmpty:
    class _Reader:
        def __init__(self, payload: dict):
            self.payload = payload

        async def get(self, path: str, **params) -> dict:
            return self.payload

    async def test_a_missing_envelope_raises(self):
        with pytest.raises(MalformedOrderbookResponse):
            await read_book(
                self._Reader({"orderbook": {"yes_dollars": [], "no_dollars": []}}),
                "T",
                10,
            )

    async def test_a_present_envelope_returns_the_book(self):
        real = captured()[0][ORDERBOOK_KEY]
        book = await read_book(self._Reader({ORDERBOOK_KEY: real}), "T", 10)
        assert book == real

    async def test_an_empty_book_under_the_right_key_is_NOT_an_error(self):
        # The distinction that makes the whole rate meaningful: emptiness is a
        # state, a rename is a fault, and they must not share a return value.
        book = await read_book(
            self._Reader({ORDERBOOK_KEY: {"yes_dollars": [], "no_dollars": []}}),
            "T",
            10,
        )
        assert book_is_empty(book)


class TestTheDerivedAskIdentity:
    def test_yes_ask_is_one_minus_the_best_no_bid(self):
        # The levels are deliberately NOT symmetric about 0.5. The original
        # anchor here was the run's own `[0.4530, 0.5000]`, asserting 0.500 --
        # and at 0.5000 the two conventions this test is named for agree,
        # because `1 - 0.5 == 0.5`. It discriminated max-vs-first and not
        # `1 - p` vs `p`, which is the `clv_tenths(500, 500, "no")` failure
        # wearing the name of the identity it does not check.
        book = {"no_dollars": [["0.4530", "93"], ["0.6000", "102"]],
                "yes_dollars": []}
        # Best NO bid is the HIGHEST NO price (0.6000), so the derived YES ask
        # is 1 - 0.6000. Each wrong implementation now gives a DIFFERENT and
        # wrong number, and no two of them collide:
        #   first level rather than best   -> 0.547
        #   the NO price itself, not 1 - p -> 0.600
        #   1 - the lowest NO bid          -> 0.547
        assert derived_yes_ask(book) == pytest.approx(0.400)

    def test_the_anchor_would_catch_each_wrong_convention(self):
        # A guard is decoration until it is watched failing, so the three
        # near-miss implementations are computed here and asserted DIFFERENT
        # from the right answer, on the same levels the test above uses.
        levels = [0.4530, 0.6000]
        right = 1.0 - max(levels)
        assert right != pytest.approx(1.0 - levels[0])   # first, not best
        assert right != pytest.approx(max(levels))       # p, not 1 - p
        assert right != pytest.approx(1.0 - min(levels))  # worst, not best

    def test_an_empty_book_derives_no_ask_rather_than_zero(self):
        assert derived_yes_ask({"no_dollars": [], "yes_dollars": []}) is None

    def test_every_level_is_expressed_on_the_yes_scale(self):
        book = {"no_dollars": [["0.4530", "93"]], "yes_dollars": [["0.3000", "5"]]}
        assert sorted(derived_yes_prices(book)) == pytest.approx([0.300, 0.547])


class TestEchoScoringRefusesRatherThanSubstitutes:
    def test_an_unpriceable_leg_gives_none_not_false(self):
        # `None` means "cannot answer" and is excluded from (c)'s denominator.
        # `False` would mean "no echo" and would deflate the rate silently.
        row = Row(
            ticker="T", series="S", collection="", scope="cross_game",
            created_ms=None, legs=({"side": "yes", "market_ticker": "L"},),
            list_ask=0.5, list_bid=None, list_no_bid=None,
            list_observed_ms=0,
            volume=None, open_interest=None,
            leg_costs=[], legs_all_priceable=False,
            book={"no_dollars": [["0.5000", "10"]], "yes_dollars": []},
        )
        assert row.echoes_a_leg is None

    def test_an_empty_book_gives_none_not_false(self):
        assert echo_gap({"no_dollars": [], "yes_dollars": []}, [0.5]) is None

    def test_the_tolerance_is_the_one_the_rest_of_the_project_uses(self):
        from analyse_combo_domination import ECHO_TOLERANCE as DOMINATION_TOL

        assert ECHO_TOLERANCE == DOMINATION_TOL

    def test_a_level_inside_two_cents_counts_and_one_outside_does_not(self):
        book = {"no_dollars": [["0.3800", "10"]], "yes_dollars": []}  # -> 0.62
        assert echo_gap(book, [0.635]) < ECHO_TOLERANCE
        assert echo_gap(book, [0.65]) > ECHO_TOLERANCE

    def test_the_boundary_itself_is_a_float_coin_flip_and_is_declared(self):
        """A gap of exactly 0.02 may land either side. Recorded, not hidden.

        `0.62 - 0.64` is `-0.020000000000000018` in binary floating point, so a
        leg exactly two cents from a level fails `<= 0.02`. The threshold was
        pre-registered at 0.02 before collection and is **not** being retuned
        here to make a nicer number; the alternative -- adding an epsilon after
        seeing the data -- is the move this whole document exists to avoid.

        What makes that safe is not the argument, it is
        `test_no_observed_row_sits_on_the_boundary` below: no row in the run
        came within a thousandth of it, so the artifact cannot have moved the
        reported rate. `analyse_combo_domination` and `measure_combo_leg_echo`
        carry the same knife edge, so this is the project's behaviour, not a
        new defect introduced by this harness.
        """
        book = {"no_dollars": [["0.3800", "10"]], "yes_dollars": []}
        assert echo_gap(book, [0.64]) == pytest.approx(0.02)
        assert echo_gap(book, [0.64]) > ECHO_TOLERANCE  # the artifact, pinned

    def test_no_observed_row_sits_on_the_boundary(self):
        run = json.loads(
            (_ROOT / "docs" / "measurements"
             / "2026-08-09-combo-e2-book-empty.json").read_text(encoding="utf-8")
        )
        gaps = [r["gap_to_leg"] for r in run["rows"] if r["gap_to_leg"] is not None]
        assert gaps, "no row scored (c) at all; the guard above proves nothing"
        assert all(abs(g - ECHO_TOLERANCE) > 1e-3 for g in gaps)


class TestReproductionIsGridEquality:
    def _row(self, list_ask: float, no_bid: float) -> Row:
        return Row(
            ticker="T", series="S", collection="", scope="cross_game",
            created_ms=None, legs=(), list_ask=list_ask, list_bid=None,
            list_no_bid=None, list_observed_ms=0, volume=None,
            open_interest=None,
            book={"no_dollars": [[f"{no_bid:.4f}", "10"]], "yes_dollars": []},
        )

    def test_an_exact_match_reproduces(self):
        assert self._row(0.1880, 0.8120).reproduces is True

    def test_one_deci_cent_out_does_not_reproduce(self):
        # 0.001 is a real tick on this venue, so it is a disagreement, not
        # rounding. GRID_TOL is half a deci-cent for exactly this reason.
        row = self._row(0.4830, 0.5180)
        assert abs(row.ask_diff) == pytest.approx(0.001)
        assert row.reproduces is False
        assert GRID_TOL < 0.001

    def test_no_no_side_gives_none_not_false(self):
        row = Row(
            ticker="T", series="S", collection="", scope="cross_game",
            created_ms=None, legs=(), list_ask=0.5, list_bid=None,
            list_no_bid=None, list_observed_ms=0, volume=None,
            open_interest=None,
            book={"no_dollars": [], "yes_dollars": []},
        )
        assert row.reproduces is None


class TestSelectionSpansTheSeriesRatherThanTheFirstOne:
    """The defect that voided E2's transfer, pinned so it cannot come back.

    `DISCOVERY_SERIES` is an ordered tuple and the pages were concatenated, so
    "the first 20 eligible rows in discovery order" took 20/20 from the first
    series -- while the 2,116-row harvest it was meant to inform is 66% the
    *second*. Nothing errored and nothing looked short. The sample simply did
    not contain the population.
    """

    def test_concatenating_the_pages_would_take_only_the_first_series(self):
        # The bug, stated as arithmetic. This is what the old code did.
        a = [{"s": "A", "i": i} for i in range(50)]
        b = [{"s": "B", "i": i} for i in range(50)]
        first20 = (a + b)[:20]
        assert {row["s"] for row in first20} == {"A"}, (
            "if this ever passes with B in it, the concatenation is no longer "
            "the failure mode this test was written for"
        )

    def test_round_robin_takes_from_every_series(self):
        a = [{"s": "A", "i": i} for i in range(50)]
        b = [{"s": "B", "i": i} for i in range(50)]
        first20 = round_robin([a, b])[:20]
        assert {row["s"] for row in first20} == {"A", "B"}
        assert sum(1 for r in first20 if r["s"] == "A") == 10
        assert sum(1 for r in first20 if r["s"] == "B") == 10

    def test_a_short_series_shows_up_as_a_short_sample_not_an_absent_one(self):
        # Under-supply must degrade gracefully: the other series fills in, but
        # the short one is still represented rather than silently dropped.
        a = [{"s": "A", "i": i} for i in range(50)]
        b = [{"s": "B", "i": i} for i in range(3)]
        out = round_robin([a, b])[:20]
        assert sum(1 for r in out if r["s"] == "B") == 3
        assert len(out) == 20

    def test_max_legs_matches_the_harvests_own_eligibility_rule(self):
        # `measure_combo_correlation` refuses above 3 legs, so the 2,116 stored
        # rows are 2- and 3-leg only. A sample at 10-15 legs is not a sample of
        # them, whatever its `n`.
        four = {"mve_selected_legs": [{}, {}, {}, {}],
                "yes_ask_dollars": "0.5000"}
        three = {"mve_selected_legs": [{}, {}, {}],
                 "yes_ask_dollars": "0.5000"}
        assert eligible(four) is True            # unrestricted, as E2 ran
        assert eligible(four, max_legs=3) is False
        assert eligible(three, max_legs=3) is True


class TestAPooledRateIsSplitOnTheQuoterThatCarriesIt:
    def test_identical_books_share_a_signature(self):
        one = {"no_dollars": [["0.9980", "300.00"]], "yes_dollars": []}
        two = {"no_dollars": [["0.9980", "300.00"]], "yes_dollars": []}
        assert book_signature(one) == book_signature(two)

    def test_a_different_size_is_a_different_quoter(self):
        # Same price, different resting size, so not the same order. Grouping
        # on price alone would merge two quoters into one cluster.
        one = {"no_dollars": [["0.9980", "300.00"]], "yes_dollars": []}
        two = {"no_dollars": [["0.9980", "301.00"]], "yes_dollars": []}
        assert book_signature(one) != book_signature(two)

    def test_the_captured_run_contains_exactly_one_six_row_cluster(self):
        # Pinned to the bytes: E2's pooled 68.8% "reproduces" was a blend of a
        # 6/6 cluster and 5/10 on everything else.
        from collections import Counter

        sigs = Counter(book_signature(e[ORDERBOOK_KEY]) for e in captured())
        clusters = {s: n for s, n in sigs.items() if n > 1 and s != ((), ())}
        assert list(clusters.values()) == [6]
        (sig,) = clusters
        assert sig == ((), ((0.998, 300.0),))


class TestWilsonSpeaksHonestlyAtSmallN:
    def test_zero_of_fourteen_does_not_claim_zero(self):
        lo, hi = wilson(0, 14)
        assert lo == 0.0
        # The point estimate is 0%. The interval must not be, or "no empty
        # books in 14" would read as "empty books do not happen".
        assert hi > 0.2

    def test_four_of_twenty_spans_most_of_the_plausible_range(self):
        lo, hi = wilson(4, 20)
        assert lo == pytest.approx(0.081, abs=0.002)
        assert hi == pytest.approx(0.416, abs=0.002)

    def test_n_zero_is_total_ignorance_not_a_rate(self):
        assert wilson(0, 0) == (0.0, 1.0)
