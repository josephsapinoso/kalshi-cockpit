"""The buy-sheet cost line is the price restated, and nothing else (#328).

One sentence at the moment of buying: "{n} legs. Wins about 1 in {N}. Fee is
{x}% of stake. The same picks as singles: {y}%." The arithmetic lives in one
module, `frontend/src/lib/parlayCost.ts`, and these tests read its source (and
the three screens that render it) the way `test_ask_the_market_screen.py` does.

What these tests establish
--------------------------
That `1 in N` is `round(1000 / price_tenths)`; that the fee share is
`k * (1 - P)` with `k` derived from a served quote's own fee and never typed
as a literal in any file that shows the line; that the line is absent on a null
price; that the singles clause is absent when any leg lacks an ask; that the
line carries no ranking or praise words.

What they do not establish
--------------------------
That the rendered page reads well, or that the arithmetic is evaluated
correctly at runtime (the source is read, not executed; the TypeScript
compiler and the build cover the types). Nor that the served quote's fee equals
what Kalshi will charge: the fee model is an estimate (ADR 0027).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "frontend" / "src"
COST = SRC / "lib" / "parlayCost.ts"
SCREENS = {
    "AskTheMarket": SRC / "components" / "AskTheMarket.tsx",
    "CheckAParlay": SRC / "components" / "CheckAParlay.tsx",
    "ParlayCards": SRC / "components" / "ParlayCards.tsx",
    "PriceOnKalshi": SRC / "components" / "PriceOnKalshi.tsx",
}


def strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)


def code(path: Path) -> str:
    return strip_comments(path.read_text(encoding="utf-8"))


def function_body(source: str, name: str) -> str:
    start = source.index(f"export function {name}(")
    end = source.find("\nexport ", start + 1)
    return source[start : end if end != -1 else len(source)]


class TestTheLineIsThePriceRestated:
    def test_one_in_is_round_of_1000_over_price_tenths(self):
        body = function_body(code(COST), "oneIn")
        assert "Math.round(1000 / priceTenths)" in body

    def test_fee_share_is_k_times_one_minus_price(self):
        body = function_body(code(COST), "feeSharePercent")
        assert "k * (1 - priceTenths / 1000)" in body

    def test_singles_is_sum_k_p_one_minus_p_over_sum_p(self):
        body = function_body(code(COST), "singlesFeeSharePercent")
        assert "fee += k * p * (1 - p)" in body
        assert "stake += p" in body
        assert "fee / stake" in body

    def test_the_coefficient_comes_from_a_served_fee_not_a_literal(self):
        """A literal 0.07 / 0.071 anywhere the line is built goes red."""
        offenders = []
        for label, path in {"parlayCost": COST, **SCREENS}.items():
            if re.search(r"(?<![\d.])0\.07\d?(?!\d)", code(path)):
                offenders.append(label)
        assert not offenders, f"literal fee coefficient in {offenders}"
        body = function_body(code(COST), "coefficientFromQuote")
        assert "feeTenths / (contractsCost * (1 - priceTenths / 1000))" in body
        # The Ask-the-market line takes k from the best quote's own fee.
        ask = code(SCREENS["AskTheMarket"])
        assert "coefficientFromQuote(" in ask
        assert "best.fee_tenths" in ask

    def test_absent_on_a_null_price(self):
        cost = code(COST)
        assert "if (n === null) return null;" in function_body(cost, "costLine")
        assert "priceTenths === null" in function_body(cost, "oneIn")
        # The component renders nothing when the line is null.
        assert "if (line === null) return null;" in code(SCREENS["AskTheMarket"])

    def test_singles_clause_absent_when_a_leg_lacks_an_ask(self):
        body = function_body(code(COST), "singlesFeeSharePercent")
        guard = body.index("if (tenths === null")
        assert "return null;" in body[guard : guard + 120]
        # A card hands the legs' asks through; an unreadable one is null.
        assert "tenthsFromDisplay(leg.ask_display)" in code(SCREENS["ParlayCards"])
        # CheckAParlay's payload carries no per-leg ask, so it passes none.
        assert "legAsksTenths: null" in code(SCREENS["CheckAParlay"])

    def test_the_fee_and_singles_clauses_need_a_coefficient(self):
        cost = code(COST)
        assert "if (k === null || priceTenths === null) return null;" in cost
        assert "k === null || legAsksTenths === null" in cost

    def test_the_line_is_wired_into_all_three_screens(self):
        assert "ParlayCostLine" in code(SCREENS["AskTheMarket"])
        assert "<ParlayCostLine" in code(SCREENS["CheckAParlay"])
        assert "ParlayLegsContext.Provider" in code(SCREENS["ParlayCards"])

    def test_the_line_claims_no_praise_and_no_ranking(self):
        component = code(SCREENS["AskTheMarket"])
        component = component[component.index("export function ParlayCostLine") :]
        for word in ("cheap", "good", "edge", "best", "better", "worth", "predict"):
            assert not re.search(rf"\b{word}\b", component, re.IGNORECASE), word
        for word in ("cheap", "predict"):
            assert word not in code(COST).lower()


class TestTheServedCoefficientIsPreferred:
    """#334: `fee_coefficient` rides on the lookup and check payloads."""

    def test_the_served_coefficient_wins_over_a_quote_derived_one(self):
        body = function_body(code(COST), "resolveCoefficient")
        served = body.index("typeof served === \"number\"")
        assert "return served;" in body[served : served + 160]
        assert body.rstrip().rstrip("}").rstrip().endswith("return fromQuote;")

    def test_the_cost_line_resolves_through_it(self):
        component = code(SCREENS["AskTheMarket"])
        component = component[component.index("export function ParlayCostLine") :]
        assert "resolveCoefficient(legs?.feeCoefficient, coefficient)" in component

    def test_the_line_beside_the_book_tile_carries_the_fee_clause(self):
        """PriceOnKalshi renders the line under the tiles, with the served
        coefficient in the context -- not `null` all the way down."""
        source = code(SCREENS["PriceOnKalshi"])
        assert re.search(r"<ParlayCostLine\b", source)
        assert "tenthsFromDisplay(value.quoted.ask_display)" in source
        assert "feeCoefficient: value.fee_coefficient ?? null" in source
        # The line sits after the tiles and before the stake line.
        assert re.search(r"<ParlayCostLine\b", source).start() > source.index("<Stat")

    def test_check_a_parlay_completes_the_line_from_the_payload(self):
        source = code(SCREENS["CheckAParlay"])
        assert source.count("feeCoefficient: value.fee_coefficient ?? null") == 2

    def test_the_payload_types_carry_the_field(self):
        types = code(SRC / "lib" / "types" / "parlays.ts")
        assert types.count("fee_coefficient?: number | null;") == 2

