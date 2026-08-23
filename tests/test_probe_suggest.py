"""--suggest sends nothing, and the shape of the code makes that checkable.

Two kinds of test here. The structural ones parse the probe script's AST and
pin the property the flag advertises: the suggest branch returns out of `main`
before anything that can build or send an order, and nothing reachable from it
references the order-construction machinery. The behavioural ones drive
`suggest_candidates` -- a pure function -- through every cut with synthetic
events, no network.

Mutation run, red and restored byte-identical (2026-08-22): the `return` on
`main`'s suggest branch replaced with a bare call (the branch then falls
through into the refusal check and the probes) --
`test_the_suggest_branch_exits_main_before_the_order_path` fails.

WHAT THIS DOES NOT ESTABLISH
----------------------------
That a suggested market still looks like that when Joe runs the real command
minutes later (the probe re-reads the book and re-confirms), or that the live
walk returns any candidate at all on a given day.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from probe_create_order import (  # noqa: E402
    MAX_FILL_ASK_TENTHS,
    ONE_CENT_TENTHS,
    SPEND_FLAG,
    SuggestedProbe,
    parse_args,
    suggest_candidates,
)

from backend.kalshi.discovery import (  # noqa: E402
    DiscoveredEvent,
    DiscoveredMarket,
)
from backend.kalshi.grid import PriceBand, PriceGrid  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_create_order.py"

# Every name that belongs to the order-construction-and-send path. If any of
# these is reachable from the suggest code, the "sends nothing" claim is
# decoration. `raw_request` is the only function in the script that performs a
# non-GET; `OrderRequest`/`to_api_dict` build the body; the two paths are what
# the POSTs and DELETEs are addressed to; `run_probes` is the sender.
ORDER_PATH_NAMES = {
    "OrderRequest",
    "to_api_dict",
    "raw_request",
    "run_probes",
    "ORDERS_PATH",
    "LEGACY_ORDERS_PATH",
    "post",
    "delete",
}


def _tree() -> ast.Module:
    return ast.parse(SCRIPT.read_text(encoding="utf-8"))


def _top_level_def(tree: ast.Module, name: str) -> ast.AST:
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.name == name
        ):
            return node
    raise AssertionError(
        f"no top-level def/class {name!r} in {SCRIPT.name} -- renamed? The "
        f"structural guarantee this suite pins must be re-established, not "
        f"skipped."
    )


def _names_used(node: ast.AST) -> set[str]:
    """Every identifier a subtree touches: bare names and attribute accesses."""
    used: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            used.add(child.id)
        elif isinstance(child, ast.Attribute):
            used.add(child.attr)
    return used


class TestTheSuggestPathCannotReachTheSendPath:
    def test_the_suggest_branch_exits_main_before_the_order_path(self):
        """`main` must dispatch `if args.suggest: return ...` strictly before
        any statement that references `run_probes` (or the refusal machinery
        the probes sit behind). A suggest branch that falls through is the
        mutation this test was verified red against."""
        tree = _tree()
        main = _top_level_def(tree, "main")

        suggest_index = None
        first_order_index = None
        for index, statement in enumerate(main.body):
            names = _names_used(statement)
            if (
                isinstance(statement, ast.If)
                and "suggest" in _names_used(statement.test)
                and suggest_index is None
            ):
                suggest_index = index
                assert isinstance(statement.body[-1], ast.Return), (
                    "the suggest branch in main() does not END in a return; "
                    "it can fall through into the order path"
                )
                assert not (_names_used(statement) & ORDER_PATH_NAMES), (
                    "the suggest branch in main() itself references the "
                    "order path"
                )
            if names & {"run_probes", "refusal_reason"} and first_order_index is None:
                first_order_index = index

        assert suggest_index is not None, (
            "main() has no `if args.suggest` dispatch -- the structural "
            "guarantee is gone"
        )
        assert first_order_index is not None, (
            "main() never reaches run_probes/refusal_reason -- the scan is "
            "vacuous (renamed?) and proves nothing"
        )
        assert suggest_index < first_order_index, (
            "main() consults the order path before the suggest dispatch; "
            "--suggest is no longer structurally unable to send"
        )

    def test_nothing_reachable_from_suggest_references_order_construction(self):
        """`run_suggest`, `suggest_candidates` and `SuggestedProbe` must not
        touch OrderRequest, raw_request, the order paths, or any client
        write verb. GETs only."""
        tree = _tree()
        for name in ("run_suggest", "suggest_candidates", "SuggestedProbe"):
            used = _names_used(_top_level_def(tree, name))
            forbidden = used & ORDER_PATH_NAMES
            assert not forbidden, (
                f"{name} references the order path: {sorted(forbidden)}"
            )

    def test_the_forbidden_names_really_are_the_order_path(self):
        """Anti-vacuity anchor, per the desk_passes idiom: `run_probes` must
        use the names the scan forbids, or a rename has made the whole scan
        prove nothing."""
        used = _names_used(_top_level_def(_tree(), "run_probes"))
        for name in ("OrderRequest", "raw_request", "ORDERS_PATH", "to_api_dict"):
            assert name in used, (
                f"run_probes no longer uses {name!r}; update ORDER_PATH_NAMES "
                f"to track the real send path or the guard is decoration"
            )

    def test_the_anonymous_auth_refuses_to_sign_a_non_get(self):
        """Belt to the AST braces: even if code drifted past the structure,
        the credential-less client cannot produce headers for a write."""
        from probe_create_order import _AnonymousMarketDataAuth

        auth = _AnonymousMarketDataAuth()
        assert auth.get_rest_headers("GET", "/trade-api/v2/events")
        with pytest.raises(RuntimeError):
            auth.get_rest_headers("POST", "/trade-api/v2/portfolio/orders")


class TestSuggestNeedsNoTickerAndAProbeStillDoes:
    def test_suggest_alone_parses(self):
        args = parse_args(["--suggest"])
        assert args.suggest is True
        assert args.ticker is None

    def test_a_probe_run_without_ticker_and_side_still_refuses_to_parse(self):
        """Relaxing `required=True` for --suggest must not have relaxed the
        probe run's contract."""
        with pytest.raises(SystemExit):
            parse_args([SPEND_FLAG])
        with pytest.raises(SystemExit):
            parse_args([SPEND_FLAG, "--ticker", "KXT"])  # side missing


# ---------------------------------------------------------------------------
# suggest_candidates, driven synthetically. These are NOT wire-format tests:
# the wire is parsed by discovery, whose own tests load captured payloads;
# this function consumes discovery's already-parsed dataclasses.
# ---------------------------------------------------------------------------

NOW_MS = 1_787_000_000_000
LATER_MS = NOW_MS + 3_600_000

# 1c..99c at a 1c step, in micro-dollars.
GRID = PriceGrid(bands=(PriceBand(10_000, 990_000, 10_000),))


def _market(ticker="KXMLBGAME-TEST-AAA", **overrides) -> DiscoveredMarket:
    fields = dict(
        ticker=ticker,
        event_ticker="KXMLBGAME-TEST",
        series_ticker="KXMLBGAME",
        market_type="moneyline",
        title="Team A wins",
        yes_side="Team A",
        strike=None,
        close_ms=None,
        status="active",
        volume_24h=0.0,
        open_interest=0.0,
        price_structure=None,
        # NO bid 93c => derived YES ask 7c; YES bid 20c => derived NO ask 80c.
        yes_bid_tenths=200,
        no_bid_tenths=930,
        yes_ask_size=25.0,
        no_ask_size=40.0,
        price_grid=GRID,
    )
    fields.update(overrides)
    return DiscoveredMarket(**fields)


def _event(markets, event_ticker="KXMLBGAME-TEST", commence_ms=LATER_MS):
    return DiscoveredEvent(
        event_ticker=event_ticker,
        series_ticker="KXMLBGAME",
        league="Pro Baseball",
        sport_key="baseball_mlb",
        market_type="moneyline",
        title="Team A at Team B",
        commence_ms=commence_ms,
        markets=tuple(markets),
    )


class TestWhatQualifiesAsACandidate:
    def test_a_cheap_ask_with_depth_on_a_live_pregame_market_is_suggested(self):
        picks = suggest_candidates([_event([_market()])], now_ms=NOW_MS)
        assert len(picks) == 1
        assert picks[0].side == "yes"
        assert picks[0].ask_tenths == 70  # complement of the 93c NO bid
        assert picks[0].depth_contracts == 25.0

    def test_the_command_is_the_exact_copy_paste_line(self):
        (pick,) = suggest_candidates([_event([_market()])], now_ms=NOW_MS)
        assert pick.command == (
            ".venv\\Scripts\\python.exe scripts\\probe_create_order.py "
            "--i-am-joe-and-this-spends-money "
            "--ticker KXMLBGAME-TEST-AAA --side yes"
        )

    def test_an_ask_above_the_fill_cap_is_not_suggested(self):
        # NO bid 88c => YES ask 12c, above probe 3's 10c cap.
        market = _market(no_bid_tenths=1000 - MAX_FILL_ASK_TENTHS - 20)
        assert suggest_candidates([_event([market])], now_ms=NOW_MS) == []

    def test_an_ask_at_one_cent_or_below_is_not_suggested(self):
        # Probe 1 rests a 1c IOC that must NOT fill; an ask <= 1c would fill it.
        for no_bid in (1000 - ONE_CENT_TENTHS, 995):
            market = _market(no_bid_tenths=no_bid)
            assert suggest_candidates([_event([market])], now_ms=NOW_MS) == [], (
                no_bid
            )

    def test_an_empty_or_unreadable_book_side_is_skipped_not_defaulted(self):
        no_depth = _market(yes_ask_size=0.0)
        unreadable = _market(no_bid_tenths=None, yes_ask_size=None)
        for market in (no_depth, unreadable):
            assert suggest_candidates([_event([market])], now_ms=NOW_MS) == []

    def test_a_market_that_is_not_active_is_not_suggested(self):
        market = _market(status="finalized")
        assert suggest_candidates([_event([market])], now_ms=NOW_MS) == []

    def test_a_game_already_started_is_not_suggested(self):
        event = _event([_market()], commence_ms=NOW_MS - 1)
        assert suggest_candidates([event], now_ms=NOW_MS) == []

    def test_a_market_without_a_readable_grid_is_not_suggested(self):
        # The order path refuses grid=None; suggesting one buys four refusals.
        market = _market(price_grid=None)
        assert suggest_candidates([_event([market])], now_ms=NOW_MS) == []

    def test_a_kxmve_ticker_is_never_suggested_even_if_it_reaches_here(self):
        market = _market(ticker="KXMVE-COMBO-XYZ")
        assert suggest_candidates([_event([market])], now_ms=NOW_MS) == []

    def test_the_no_side_qualifies_on_its_own_ask(self):
        # YES bid 91c => derived NO ask 9c with 15 resting; the YES ask is
        # far above the cap, so the suggestion must be the NO side.
        market = _market(
            yes_bid_tenths=910, no_bid_tenths=300, no_ask_size=15.0
        )
        (pick,) = suggest_candidates([_event([market])], now_ms=NOW_MS)
        assert pick.side == "no"
        assert pick.ask_tenths == 90


class TestTheListIsThreeIndependentBooks:
    def test_one_candidate_per_event_the_deepest(self):
        shallow = _market(ticker="KXMLBGAME-TEST-AAA", yes_ask_size=5.0)
        deep = _market(ticker="KXMLBGAME-TEST-BBB", yes_ask_size=50.0)
        picks = suggest_candidates([_event([shallow, deep])], now_ms=NOW_MS)
        assert [p.ticker for p in picks] == ["KXMLBGAME-TEST-BBB"]

    def test_at_most_three_deepest_first_across_events(self):
        events = [
            _event(
                [_market(ticker=f"KXMLBGAME-T{i}-AAA", yes_ask_size=float(i))],
                event_ticker=f"KXMLBGAME-T{i}",
            )
            for i in (2, 9, 4, 7)
        ]
        picks = suggest_candidates(events, now_ms=NOW_MS)
        assert [p.depth_contracts for p in picks] == [9.0, 7.0, 4.0]

    def test_every_pick_is_a_suggested_probe_with_a_spend_flag_command(self):
        picks = suggest_candidates([_event([_market()])], now_ms=NOW_MS)
        assert all(isinstance(p, SuggestedProbe) for p in picks)
        assert all(SPEND_FLAG in p.command for p in picks)
