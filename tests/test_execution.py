"""The execution path: order construction, the gate, and what each refuses.

This is the only code in the project that can lose money, so the tests here are
weighted toward the refusals rather than the happy path. The headline assertion
is `test_an_off_grid_price_raises_rather_than_clamping` — clamping instead of
raising is the specific mistake that turned a self-announcing API rejection into
a live buy at 99c in the predecessor project.
"""

from __future__ import annotations

import ast
import logging
import math
import random
import sqlite3
import statistics
import time
from pathlib import Path

import pytest

from backend.analysis.clv import CONTROL_HORIZON_HOURS, DEFAULT_HORIZON_HOURS

from backend.config import GateConfig, StalenessConfig
from backend.engine import confirm_recommendation
from backend.gate import (
    ALWAYS_VALID_ALPHA,
    POPULATIONS,
    ClusteredMean,
    _cluster_robust_stderr,
    always_valid_multiplier,
    clustered_clv,
    clv_by_population,
    evaluate_gate,
    live_ages,
    log_gate_progress,
    population_counts,
    recommendation_freshness,
)
from backend.kalshi.grid import parse_price_grid
from backend.kalshi.orders import (
    ORDERS_PATH,
    STATUS_UNRECOGNISED,
    OrderPlacer,
    OrderRefused,
    OrderRequest,
    book_side_for,
    status_from_counts,
)
from backend.store import db
from backend.store.orders import ORDERS_ARE_DRY_RUNS

DAY_MS = 86_400_000

# The grid on 1,426 of 1,426 live game markets (scripts/capture_price_grids.py,
# 2026-08-08), so this is what the order path actually meets today.
WHOLE_CENT_GRID = parse_price_grid(
    [{"start": "0.0000", "end": "1.0000", "step": "0.0100"}],
    structure="linear_cent",
)
# Transcribed from Kalshi's published structure table, not captured -- see
# tests/test_price_grid.py for why that distinction is kept visible.
HALF_CENT_GRID = parse_price_grid(
    [{"start": "0.0000", "end": "1.0000", "step": "0.0050"}],
    structure="center_half_edge_half_cent",
)


def order(**kw) -> OrderRequest:
    defaults = dict(
        ticker="KXNFLGAME-26AUG27KCBAL-KC",
        side="yes",
        action="buy",
        count=20,
        limit_price_tenths=503,
        price_grid=WHOLE_CENT_GRID,
    )
    defaults.update(kw)
    return OrderRequest(**defaults)


class TestPriceSnapping:
    """Snap onto the market's own grid, away from paying more, or refuse."""

    def test_a_buy_snaps_down(self):
        """Snapping a buy up would pay more than the price we evaluated."""
        assert order(limit_price_tenths=509).api_price_tenths == 500

    def test_a_sell_snaps_up(self):
        assert order(action="sell", limit_price_tenths=501).api_price_tenths == 510

    def test_a_price_already_on_the_grid_is_unchanged_either_way(self):
        assert order(limit_price_tenths=500).api_price_tenths == 500
        assert order(action="sell", limit_price_tenths=500).api_price_tenths == 500

    def test_an_off_grid_price_raises_rather_than_clamping(self):
        """The rule that earned itself.

        Clamping turned `no_price=-390` -- which the exchange would have
        rejected outright -- into a live buy at 99c. A price being validated
        must be refused, not coerced onto the nearest legal value.
        """
        with pytest.raises(OrderRefused) as exc:
            order(limit_price_tenths=9)          # snaps to 0
        assert "clamping" in str(exc.value)

    def test_the_top_of_the_grid_is_refused_too(self):
        with pytest.raises(OrderRefused):
            order(action="sell", limit_price_tenths=999)   # snaps to $1.00

    def test_the_grid_boundaries_themselves_are_accepted(self):
        assert order(limit_price_tenths=10).api_price_tenths == 10
        assert order(action="sell", limit_price_tenths=990).api_price_tenths == 990

    def test_an_order_without_a_grid_cannot_be_built(self):
        """There is no default grid. Assuming whole cents is the bug."""
        with pytest.raises(OrderRefused) as exc:
            order(price_grid=None)
        assert "never fills" in str(exc.value)


class TestADeciCentAskIsSentAtTheDeciCent:
    """The defect this change exists for.

    A 50.5c ask floored to 50c is a *legal* price -- Kalshi accepts whole cents
    on every structure -- so it was never rejected. It simply rested behind the
    market forever and entered the paper record as a bet that was placed. On a
    record that is the entire product, an order that cannot fill is worse than
    one that is refused.

    Every assertion here is chosen so the old whole-cent flooring gives a
    *different* answer, per `tasks/lessons.md`: an anchor both implementations
    satisfy proves nothing.
    """

    def test_buying_yes_at_a_half_cent_sends_the_half_cent(self):
        built = order(side="yes", limit_price_tenths=505, price_grid=HALF_CENT_GRID)
        assert built.api_price_tenths == 505          # flooring gave 500
        assert built.api_price_dollars == "0.5050"
        assert built.fill_price_tenths == 505

    def test_buying_no_at_a_half_cent_sends_the_complement(self):
        """V2 quotes the YES leg, so buying NO at 40.5c is selling YES at 59.5c.

        The old code sent `no_price=40` -- an offer to sell YES at 60c, which
        does not cross a resting YES bid of 59.5c. That is the unfillable order,
        stated as arithmetic.
        """
        built = order(side="no", limit_price_tenths=405, price_grid=HALF_CENT_GRID)
        assert built.book_side == "ask"
        assert built.api_price_tenths == 595
        assert built.api_price_dollars == "0.5950"
        assert built.fill_price_tenths == 405          # flooring gave 400

    def test_snapping_never_costs_more_than_the_price_evaluated(self):
        """The invariant that holds on both legs and both grids.

        Buying NO snaps the YES ask *up*, which moves our own price *down* --
        the reflection is where a sign error would hide, and this is the
        property that catches it.
        """
        for grid in (WHOLE_CENT_GRID, HALF_CENT_GRID):
            for side in ("yes", "no"):
                for tenths in (203, 405, 505, 663, 897):
                    built = order(
                        side=side, limit_price_tenths=tenths, price_grid=grid
                    )
                    assert built.fill_price_tenths <= tenths
                    assert grid.is_on_grid(built.api_price_tenths)


class TestTheYesBookConversion:
    """V2 quotes everything from the YES leg. Four combinations, two sides."""

    @pytest.mark.parametrize(
        "side, action, expected",
        [
            ("yes", "buy", "bid"),
            ("no", "sell", "bid"),
            ("yes", "sell", "ask"),
            ("no", "buy", "ask"),
        ],
    )
    def test_the_mapping_is_the_documented_one(self, side, action, expected):
        assert book_side_for(side, action) == expected

    def test_an_unrepresentable_combination_is_refused(self):
        with pytest.raises(OrderRefused):
            book_side_for("maybe", "buy")


class TestOrderRequestValidation:
    """An invalid OrderRequest must not be constructible."""

    @pytest.mark.parametrize(
        "patch",
        [
            {"side": "maybe"},
            {"action": "hold"},
            {"count": 0},
            {"count": -5},
            {"ticker": ""},
            {"limit_price_tenths": 0},       # settled loser
            {"limit_price_tenths": 1000},    # settled winner
            {"limit_price_tenths": 5},       # off-grid after snapping
            {"price_grid": None},
            {"time_in_force": "GTT"},        # an internal value, not an API one
            {"self_trade_prevention": "none"},
        ],
    )
    def test_invalid_orders_cannot_be_built(self, patch):
        with pytest.raises(OrderRefused):
            order(**patch)

    def test_validation_happens_at_construction_not_at_send(self):
        """So no caller can hold one of these and forget to check it."""
        with pytest.raises(OrderRefused):
            order(count=0)

    def test_every_order_carries_an_idempotency_key(self):
        assert order().client_order_id
        assert order().client_order_id != order().client_order_id

    def test_the_body_is_the_v2_shape(self):
        """Transcribed from Kalshi's published OpenAPI spec for
        `POST /portfolio/events/orders`. Both `time_in_force` and
        `self_trade_prevention_type` are required there and were absent from the
        legacy body, so an endpoint swap without them is a 400."""
        body = order().to_api_dict()
        assert set(body) == {
            "ticker", "client_order_id", "side", "count", "price",
            "time_in_force", "self_trade_prevention_type",
        }
        assert body["side"] in ("bid", "ask")
        assert body["price"] == "0.5000"
        assert body["count"] == "20.00"        # fixed-point string, not an int

    def test_the_body_carries_no_legacy_price_field(self):
        """`yes_price`/`no_price` are integer cents and cannot name 50.5c.
        Their presence would mean the migration is half-done."""
        body = order().to_api_dict()
        assert "yes_price" not in body
        assert "no_price" not in body

    def test_the_body_carries_the_idempotency_key(self):
        built = order()
        assert built.to_api_dict()["client_order_id"] == built.client_order_id

    def test_worst_case_cost_uses_the_price_actually_sent(self):
        """Snapping is in our favour, so quoting the unsnapped price would
        overstate the cost.

        50.9c snaps down to 50c on a whole-cent grid, giving $50.00 of stake.
        The fee on top is $1.75 -- 50c is exactly where the fee model peaks --
        so the worst case is $51.75. Quoting the unsnapped 50.9c would have said
        $50.90 of stake for a fill that costs $50.00.

        **Was $52.00 until 2026-08-14**, when the retired max-of-models hedge
        stopped lifting 1.75c/contract to 2c via Model B's per-contract cent
        rounding. The claim under test is that the SNAPPED price is used; the
        fee is incidental to it and is pinned in `tests/test_fees.py`.
        """
        built = order(count=100, limit_price_tenths=509)
        assert built.api_price_tenths == 500
        assert built.worst_case_cost_dollars == pytest.approx(51.75)


class TestOrderPlacer:
    async def test_dry_run_is_the_default(self):
        assert OrderPlacer().dry_run is True

    async def test_a_live_placer_without_a_client_is_refused(self):
        """Otherwise it would silently no-op every order."""
        with pytest.raises(OrderRefused) as exc:
            OrderPlacer(dry_run=False)
        assert "no-op" in str(exc.value)

    async def test_a_dry_run_builds_the_body_it_would_have_sent(self):
        outcome = await OrderPlacer().place(order())
        assert outcome.status == "dry_run"
        assert outcome.dry_run is True
        assert outcome.request_body["ticker"] == order().ticker
        assert outcome.request_body["price"] == "0.5000"

    async def test_observers_see_every_order(self):
        seen = []
        placer = OrderPlacer(observers=[seen.append])
        await placer.place(order())
        assert len(seen) == 1

    async def test_a_failing_observer_does_not_unwind_the_order(self):
        """The money has moved either way; losing the record is worse than
        losing the notification."""
        def explode(_outcome):
            raise RuntimeError("observer is broken")

        outcome = await OrderPlacer(observers=[explode]).place(order())
        assert outcome.status == "dry_run"


# Directories that are not the deployed system. Mirrors
# `tests/test_has_callers.NOT_A_CALLER` and for the same reason: `.claude`
# holds parallel lanes' worktrees, which are full second copies of the repo,
# so walking them lets another branch's source decide whether `main` passes.
NOT_PRODUCTION = ("tests", "warehouse", ".venv", "node_modules", "__pycache__", ".claude")


def _production_sources():
    root = Path(__file__).resolve().parent.parent
    for path in root.rglob("*.py"):
        rel = str(path.relative_to(root)).replace("\\", "/")
        if any(part in NOT_PRODUCTION for part in rel.split("/")):
            continue
        yield rel, path


class TestArmingRealTradingIsACodeChange:
    """No configuration turns the order path live. Only an edit does.

    `ORDERS_ARE_DRY_RUNS` is a module constant with no environment read, and
    the one production construction of `OrderPlacer` takes it. So
    `LIVE_TRADING_ENABLED` satisfies one gate condition and moves no money --
    see `docs/adr/0018`, which exists because `gate.py`'s wording invites the
    opposite reading.

    **Why this is source analysis rather than a behavioural test.** Driving the
    endpoint and asserting "no POST happened" would pass for the wrong reason:
    `routes.py` constructs the placer with no REST client, so flipping the
    constant to `False` raises `OrderRefused` at construction instead of
    placing an order. That second barrier is real and is recorded in the ADR,
    but a test standing behind it proves nothing about the first one. These two
    assertions fail on their own subject, verified by making the edits:

        constant -> False                      first assertion red
        call site -> dry_run=False             second red
        call site -> dry_run=True (harmless!)  second red -- the drift the
                                               constant exists to prevent
        walker looks for the wrong name        second red on `found >= 2`
    """

    def test_the_dry_run_constant_is_true(self):
        assert ORDERS_ARE_DRY_RUNS is True, (
            "the order path is armed. This is not a config change and must not "
            "be made as a side effect of one -- ADR 0018 enumerates what else "
            "has to move with it, starting with the REST client that "
            "`routes.py` does not pass."
        )

    def test_no_production_call_site_arms_the_placer(self):
        """Every `OrderPlacer(...)` outside tests takes the constant or the default.

        A hardcoded boolean at a call site is the specific regression, and it is
        not benign even when the boolean is `True`: the constant exists because
        the endpoint's advisory exposure read and `reserve_order`'s
        authoritative check must agree about which exposure population an order
        sizes against, and two literals in two files are free to stop agreeing.
        See `backend/store/orders.py:121-128`.
        """
        offenders: list[str] = []
        found = 0
        for rel, path in _production_sources():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):        # a lane rewriting its file
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = (
                    func.id if isinstance(func, ast.Name)
                    else getattr(func, "attr", None)
                )
                if name != "OrderPlacer":
                    continue
                found += 1
                keywords = {k.arg: k.value for k in node.keywords if k.arg}
                if "dry_run" not in keywords:
                    # The default, which `test_dry_run_is_the_default` pins.
                    continue
                given = keywords["dry_run"]
                if isinstance(given, ast.Name) and given.id == "ORDERS_ARE_DRY_RUNS":
                    continue
                offenders.append(
                    f"{rel}:{node.lineno} passes dry_run={ast.unparse(given)}"
                )

        # A walker that finds nothing passes vacuously, which is how this shape
        # of test goes green after the call site it was written for moves.
        assert found >= 2, (
            f"found {found} OrderPlacer constructions in production sources; "
            f"expected at least the API endpoint and scripts/demo_execution.py. "
            f"The walker has stopped seeing the call sites it exists to check."
        )
        assert not offenders, (
            "a production call site sets dry_run itself: " + "; ".join(offenders)
        )


class TestTheV2ResponseIsUnverifiedAndSaysSo:
    """**No order has ever been placed by this project**, so the response shape
    below is transcribed from Kalshi's OpenAPI spec and has never been observed.

    This class exists because the *previous* version had the same gap and hid
    it: it read `response["order"]["status"]` with a default of `"resting"`. V2
    emits neither an `order` envelope nor a `status` field, so every live order
    would have been recorded as resting with a null order id -- a plausible
    default over an unread response, which is the failure mode this repo has hit
    most often (`tasks/lessons.md`, "the WebSocket path was dead").

    The protection is structural rather than documentary: an unreadable response
    produces `unrecognised_response`, which no caller can mistake for success.
    A skipped test next to confident assertions does not stop the assertions
    from being believed.
    """

    class _FakeRest:
        def __init__(self, response):
            self.response = response
            self.calls = []

        async def post(self, path, json_body=None):
            self.calls.append((path, json_body))
            return self.response

    async def test_the_order_goes_to_the_v2_path(self):
        rest = self._FakeRest(
            {"order_id": "abc", "fill_count": "0.00", "remaining_count": "20.00"}
        )
        await OrderPlacer(rest, dry_run=False).place(order())
        assert rest.calls[0][0] == ORDERS_PATH
        assert ORDERS_PATH == "/portfolio/events/orders"

    @pytest.mark.parametrize(
        "fill, remaining, expected",
        [
            ("0.00", "20.00", "resting"),
            ("20.00", "0.00", "filled"),
            ("5.00", "15.00", "partially_filled"),
            ("0.00", "0.00", "unfilled"),
        ],
    )
    async def test_status_is_derived_from_the_fill_counts(
        self, fill, remaining, expected
    ):
        rest = self._FakeRest(
            {"order_id": "abc", "fill_count": fill, "remaining_count": remaining}
        )
        outcome = await OrderPlacer(rest, dry_run=False).place(order())
        assert outcome.status == expected

    @pytest.mark.parametrize(
        "response",
        [
            {},                                          # empty
            {"order": {"status": "resting"}},            # the LEGACY shape
            {"order_id": "abc"},                         # no counts
            {"fill_count": "0.00", "remaining_count": "20.00"},   # no id
            None,
        ],
    )
    async def test_an_unreadable_response_never_reads_as_success(self, response):
        """Including the legacy envelope, which is the shape the old parser
        expected -- if Kalshi ever answers that way, we must notice."""
        rest = self._FakeRest(response)
        outcome = await OrderPlacer(rest, dry_run=False).place(order())
        assert outcome.status == STATUS_UNRECOGNISED
        assert "may have been placed" in outcome.error_text

    def test_unreadable_counts_do_not_default_to_resting(self):
        assert status_from_counts(None, None) == STATUS_UNRECOGNISED
        assert status_from_counts(0.0, None) == STATUS_UNRECOGNISED

    async def test_the_measured_fee_is_kept_when_the_exchange_reports_one(self):
        """`average_fee_paid` is the reading `core/fees.py` is hedging for want
        of. It arrives in the order response, so the fee-calibration trades do
        not also need a `/portfolio/fills` poll to be useful."""
        rest = self._FakeRest({
            "order_id": "abc", "fill_count": "20.00", "remaining_count": "0.00",
            "average_fill_price": "0.5000", "average_fee_paid": "0.0200",
        })
        outcome = await OrderPlacer(rest, dry_run=False).place(order())
        assert outcome.average_fee_paid_dollars == "0.0200"
        assert outcome.average_fill_price_dollars == "0.5000"


@pytest.fixture
def gate_db(tmp_path):
    """An empty operational database with the real schema."""
    path = tmp_path / "gate.db"
    db.init_db(path).close()
    return path


def _conn(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


_DEFAULT_EVENT = object()


def _add_recommendation(
    conn, *, clv_tenths=None, scored=True, quote_age=1000, odds_age=60_000,
    suppressed=None, created_ms=None, ask=503, ticker="T", event=_DEFAULT_EVENT,
    contracts=20, horizon=DEFAULT_HORIZON_HOURS,
):
    """Insert one recommendation, and the market row it hangs off.

    `ticker`/`event` default to a single market on a single game, so calls that
    do not care produce one cluster. Anything asserting something about *sample
    size* must pass distinct tickers: the gate counts independent games, and a
    thousand rows on one game is one observation. That distinction is the point
    of `TestObservationsAreClusteredByGame` below. Pass `event=None` to model a
    market whose event ticker is genuinely unknown.

    `first_seen_ms`/`last_seen_ms` are supplied because they are `NOT NULL`.
    Without them the `INSERT OR IGNORE` silently inserted nothing -- the row
    never existed, every `LEFT JOIN kalshi_markets` in a gate test matched
    nothing, and the tests exercised the no-event fallback while reading as
    though they covered the join. `OR IGNORE` suppresses constraint failures,
    which is exactly what makes it able to hide this.
    """
    event = f"EVT-{ticker}" if event is _DEFAULT_EVENT else event
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets "
        "(ticker, event_ticker, series_ticker, first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, 'S', 0, 0)",
        (ticker, event),
    )
    conn.execute(
        """
        INSERT INTO recommendations (
            created_ms, ticker, strategy_config_version, side, entry_ask_tenths,
            fair_probability, edge_tenths, fee_predicted, ev_net_dollars,
            suggested_contracts, reference_contracts, kelly_fraction,
            kalshi_quote_age_ms,
            odds_age_ms, suppressed_reason, reason_text, clv_tenths,
            clv_scored_ms, clv_horizon_hours
        ) VALUES (?, ?, 1, 'yes', ?, 0.55, 20.0, 0.1, 0.5, ?, ?, 0.02, ?, ?, ?,
                  'test', ?, ?, ?)
        """,
        (
            created_ms or int(time.time() * 1000), ticker, ask, contracts,
            contracts,
            quote_age, odds_age, suppressed, clv_tenths,
            int(time.time() * 1000) if scored else None,
            # See the note in test_quote_refresh's builder: without this the
            # gate cannot see the row and every test below reads 423.
            horizon if scored else None,
        ),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


class TestGateConditions:
    def test_an_empty_record_is_locked_on_every_evidence_condition(self, gate_db):
        conn = _conn(gate_db)
        decision = evaluate_gate(conn, GateConfig(live_trading_enabled=True))
        assert not decision.open
        names = {c.name for c in decision.unmet}
        assert "scored_recommendations" in names
        assert "clv_survives_noise_guard" in names
        assert "fee_model_verified" in names

    def test_the_reason_names_every_unmet_condition_not_just_the_first(
        self, gate_db
    ):
        """Otherwise fixing one reveals the next, one round trip at a time."""
        conn = _conn(gate_db)
        reason = evaluate_gate(conn, GateConfig(live_trading_enabled=True)).reason
        assert reason.count("|") >= 2

    def test_no_fills_is_not_a_passing_fee_check(self, gate_db):
        """The convenient reading of an absence. With no fills the model is an
        untested hedge between two sources that disagree."""
        conn = _conn(gate_db)
        decision = evaluate_gate(conn, GateConfig(live_trading_enabled=True))
        fee = next(c for c in decision.conditions if c.name == "fee_model_verified")
        assert not fee.met
        assert "no fills yet" in fee.detail

    def test_config_alone_does_not_open_the_gate(self, gate_db):
        conn = _conn(gate_db)
        assert not evaluate_gate(conn, GateConfig(live_trading_enabled=True)).open

    def test_evidence_alone_does_not_open_the_gate(self, gate_db):
        """Arming stays a deliberate human act, separate from the statistics."""
        conn = _conn(gate_db)
        for _ in range(5):
            _add_recommendation(conn, clv_tenths=30.0)
        decision = evaluate_gate(conn, GateConfig(live_trading_enabled=False))
        assert not decision.open
        assert any(c.name == "config_enabled" for c in decision.unmet)


class TestClvNoiseGuard:
    def test_a_positive_but_indistinguishable_clv_does_not_count(self, gate_db):
        """The condition that a naive gate would miss: mean CLV is positive,
        and it is inside two standard errors of zero.

        One game each, so the sample size is genuine and the only thing under
        test is the noise guard.
        """
        conn = _conn(gate_db)
        # Alternating +/- with a small positive drift: positive mean, huge spread.
        for i in range(400):
            _add_recommendation(
                conn, clv_tenths=(50.0 if i % 2 else -48.0), ticker=f"T{i}"
            )

        decision = evaluate_gate(
            conn, GateConfig(live_trading_enabled=True, min_scored_recommendations=300)
        )
        sample = next(c for c in decision.conditions if c.name == "scored_recommendations")
        noise = next(c for c in decision.conditions if c.name == "clv_survives_noise_guard")

        assert sample.met, "sample size is satisfied"
        assert not noise.met, "but the effect is inside the noise band"
        assert "(noise)" in noise.detail

    def test_a_consistent_edge_clears_the_guard(self, gate_db):
        conn = _conn(gate_db)
        for i in range(400):
            _add_recommendation(
                conn, clv_tenths=20.0 + (1.0 if i % 2 else -1.0), ticker=f"T{i}"
            )
        decision = evaluate_gate(
            conn, GateConfig(live_trading_enabled=True, min_scored_recommendations=300)
        )
        noise = next(c for c in decision.conditions if c.name == "clv_survives_noise_guard")
        assert noise.met

    def test_a_small_sample_cannot_clear_the_guard_by_being_extreme(self, gate_db):
        conn = _conn(gate_db)
        for i in range(5):
            _add_recommendation(conn, clv_tenths=100.0, ticker=f"T{i}")
        decision = evaluate_gate(
            conn, GateConfig(live_trading_enabled=True, min_scored_recommendations=300)
        )
        assert not decision.open
        assert any(c.name == "scored_recommendations" for c in decision.unmet)


class TestObservationsAreClusteredByGame:
    """The gate counts independent games, not rows.

    The engine writes a fresh recommendation row on every pass, and every row for
    one game scores against **one** closing line. Counting rows made the
    300-observation floor reachable from ~10 markets polled 30 times, and shrank
    the standard error by `sqrt(k)` for evidence that never grew.

    The first two tests are the anchors: their expected values are fixed by
    definition rather than by reasoning, which is what `tasks/lessons.md` asks
    for after a guard, its code and its test were once written from one mental
    model and agreed with each other while all three were wrong.
    """

    def test_singleton_clusters_reproduce_the_classical_standard_error(self):
        """Definitional anchor 1: independent data must not be penalised.

        With one observation per cluster the sandwich estimator collapses
        algebraically to `s^2 / n`. If this drifts, the estimator has stopped
        being cluster-robust and started being merely conservative.
        """
        ys = [12.0, -4.0, 31.0, 7.5, -18.0, 22.0, 0.5, 9.0]
        _, _, mean, stderr = _cluster_robust_stderr([(1, y) for y in ys])

        classical = math.sqrt(statistics.variance(ys) / len(ys))
        assert mean == pytest.approx(statistics.fmean(ys), rel=1e-12)
        assert stderr == pytest.approx(classical, rel=1e-12)

    def test_duplicating_every_observation_changes_nothing(self):
        """Definitional anchor 2, and the one that discriminates.

        Recording each game `k` times adds no information, so the mean and the
        standard error must come back bit-identical. The naive estimator returns
        `stderr / sqrt(k)` on the same input -- asserted below, because a test
        that only checks the new number is right cannot show the old one was
        wrong.
        """
        games = [12.0, -4.0, 31.0, 7.5, -18.0, 22.0, 0.5, 9.0]
        k = 30

        _, g_once, mean_once, stderr_once = _cluster_robust_stderr(
            [(1, y) for y in games]
        )
        _, g_many, mean_many, stderr_many = _cluster_robust_stderr(
            [(k, y * k) for y in games]
        )

        assert g_once == g_many == len(games)
        assert mean_many == pytest.approx(mean_once, rel=1e-12)
        assert stderr_many == pytest.approx(stderr_once, rel=1e-12)

        # What the replaced implementation would have said about the duplicated
        # record: sqrt(sample variance / row count), over 240 rows.
        duplicated = [y for y in games for _ in range(k)]
        naive = math.sqrt(statistics.variance(duplicated) / len(duplicated))
        understatement = stderr_many / naive
        assert understatement == pytest.approx(
            math.sqrt((len(games) * k - 1) / (len(games) - 1)), rel=1e-12
        )
        assert understatement > 5.0, "the old estimator was ~sqrt(30) too small"

    def test_one_game_polled_four_hundred_times_is_one_observation(self, gate_db):
        """End to end. This is the exact shape the old suite asserted was fine."""
        conn = _conn(gate_db)
        for _ in range(400):
            _add_recommendation(conn, clv_tenths=20.0, ticker="T", event="E")

        stats = clustered_clv(conn)
        assert stats.n_rows == 400
        assert stats.n_clusters == 1
        # One cluster carries no between-game spread, so there is no standard
        # error to report and the caller must refuse rather than substitute one.
        assert stats.stderr_tenths is None

        decision = evaluate_gate(
            conn, GateConfig(live_trading_enabled=True, min_scored_recommendations=300)
        )
        sample = next(c for c in decision.conditions if c.name == "scored_recommendations")
        noise = next(c for c in decision.conditions if c.name == "clv_survives_noise_guard")
        assert not sample.met
        assert not noise.met
        assert "1 of 300 independent actionable games" in sample.detail
        assert "400 recommendation rows" in sample.detail

    def test_the_floor_counts_games_so_ten_markets_cannot_reach_three_hundred(
        self, gate_db
    ):
        """The audit's headline: 10 markets polled 40 times is not 400 observations."""
        conn = _conn(gate_db)
        for game in range(10):
            for _ in range(40):
                _add_recommendation(conn, clv_tenths=20.0, ticker=f"T{game}")

        stats = clustered_clv(conn)
        assert (stats.n_rows, stats.n_clusters) == (400, 10)

        sample = next(
            c
            for c in evaluate_gate(
                conn,
                GateConfig(live_trading_enabled=True, min_scored_recommendations=300),
            ).conditions
            if c.name == "scored_recommendations"
        )
        assert not sample.met, "400 rows from 10 games must not clear a 300 floor"

    def test_a_consistent_edge_on_ten_games_does_not_clear_the_noise_guard(
        self, gate_db
    ):
        """The regression that matters: the old estimator opened on this.

        Ten games polled forty times each, every row +2.0c with a hair of
        spread. Naively that is n=400 with a tiny standard error and a decisive
        z. Clustered, it is ten observations, and ten is not enough to tell.
        """
        conn = _conn(gate_db)
        # Real between-game spread, constant within a game -- which is the true
        # shape, since every row for one game scores against one closing line.
        per_game = [-5.0, 45.0, 10.0, 30.0, 0.0, 40.0, 5.0, 35.0, 15.0, 25.0]
        for game, value in enumerate(per_game):
            for _ in range(40):
                _add_recommendation(conn, clv_tenths=value, ticker=f"T{game}")

        rows = [
            r["clv_tenths"]
            for r in conn.execute(
                "SELECT clv_tenths FROM recommendations WHERE clv_tenths IS NOT NULL"
            ).fetchall()
        ]
        naive_stderr = math.sqrt(statistics.variance(rows) / len(rows))
        stats = clustered_clv(conn)

        assert stats.mean_tenths == pytest.approx(20.0)
        assert stats.mean_tenths > 2 * naive_stderr, (
            "the replaced estimator would have called this decisive"
        )
        assert not stats.distinguishable(300), (
            "clustered by game, ten observations cannot establish it"
        )

    def test_one_games_moneyline_spread_and_total_are_a_single_cluster(self, gate_db):
        """Three markets, three tickers, one final score.

        Clustering on ticker rather than event would count these as three
        independent observations. They resolve from one game, and their closing
        lines move together.
        """
        conn = _conn(gate_db)
        for market in ("KXMLBGAME-X", "KXMLBSPREAD-X", "KXMLBTOTAL-X"):
            _add_recommendation(conn, clv_tenths=15.0, ticker=market, event="EVT-GAME-X")

        stats = clustered_clv(conn)
        assert stats.n_rows == 3
        assert stats.n_clusters == 1

    def test_a_market_with_no_event_ticker_is_reported_not_silently_approximated(
        self, gate_db
    ):
        """Falling back to the ticker is an approximation, so it must be visible.

        An unreported approximation inside a money guard is indistinguishable
        from a correct calculation.
        """
        conn = _conn(gate_db)
        for _ in range(3):
            _add_recommendation(conn, clv_tenths=15.0, ticker="ORPHAN", event=None)
        _add_recommendation(conn, clv_tenths=15.0, ticker="T2")

        stats = clustered_clv(conn)
        assert stats.unclustered_rows == 3
        # Still collapsed to one cluster by ticker -- repeated polls of the same
        # market are caught. What is lost is correlation with its siblings.
        assert stats.n_clusters == 2

        sample = next(
            c
            for c in evaluate_gate(conn, GateConfig()).conditions
            if c.name == "scored_recommendations"
        )
        assert "no event ticker" in sample.detail


class TestTheGateCountsTheRightPopulation:
    """Whose closing-line behaviour is the gate's headline number about?

    It pooled every scored row with no filter on `suppressed_reason` or
    `suggested_contracts`, so the first live digest's "16 / 300" was drawn
    overwhelmingly from rows the strategy explicitly *refused*. That measures
    the closing-line behaviour of any Kalshi market this instance happened to
    poll — not of this strategy.

    These do not yet change which population the floor counts; that decision is
    Joe's and needs the numbers first. They make the mixture impossible to read
    as a result.
    """

    def test_the_three_populations_partition_every_scored_row(self, gate_db):
        """A split that quietly drops rows is worse than no split.

        Rows partition; games do not, and the docstring on `clv_by_population`
        says so — one game can contribute an actionable row and a suppressed
        one, so cluster counts may sum to more than the pooled count while row
        counts must sum exactly.
        """
        conn = _conn(gate_db)
        _add_recommendation(conn, clv_tenths=8.0, ticker="A", contracts=5)
        _add_recommendation(conn, clv_tenths=3.0, ticker="B", contracts=0)
        _add_recommendation(
            conn, clv_tenths=-2.0, ticker="C", suppressed="suspicious_edge"
        )
        # Same game as A, refused: this is what stops the games from partitioning.
        _add_recommendation(
            conn, clv_tenths=1.0, ticker="A", suppressed="stale_odds",
        )

        groups = clv_by_population(conn)
        parts = sum(groups[name].n_rows for name in POPULATIONS)
        assert parts == groups["pooled"].n_rows == 4

        assert groups["actionable"].n_rows == 1
        assert groups["no_edge"].n_rows == 1
        assert groups["suppressed"].n_rows == 2

    def test_population_counts_partition_every_row(self, gate_db):
        """The parts must sum to the whole, or the progress line is a lie.

        `population_counts` reads `POPULATIONS`, so this also pins the property
        that makes sharing them worth it: whatever the gate admits is exactly
        what the progress line counts toward admission. A row that belongs to
        no population would be invisible to both, and a row in two would be
        double-counted in one of them.
        """
        conn = _conn(gate_db)
        _add_recommendation(conn, ticker="A", contracts=5)
        _add_recommendation(conn, ticker="B", contracts=0)
        _add_recommendation(conn, ticker="C", suppressed="suspicious_edge")
        _add_recommendation(conn, ticker="D", suppressed="stale_odds", contracts=7)

        counts = population_counts(conn)
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM recommendations"
        ).fetchone()["n"]

        assert sum(counts.values()) == total == 4
        assert counts["actionable"] == 1
        assert counts["no_edge"] == 1
        # Suppressed wins over a positive size: D is refused, not bettable.
        assert counts["suppressed"] == 2

    def test_a_suppressed_row_never_counts_as_progress_toward_the_gate(
        self, gate_db
    ):
        """The whole reason this counter exists.

        Live has written recommendations on every pass since it was deployed and
        every one was suppressed, so the 300-game floor cannot be approached at
        all — however long the loop runs and however well CLV scoring works.
        A counter that moved on suppressed rows would report progress toward a
        threshold it can never reach, which is worse than reporting nothing.
        """
        conn = _conn(gate_db)
        for i in range(50):
            _add_recommendation(
                conn, ticker=f"S{i}", suppressed="edge_within_method_noise",
                contracts=3,
            )

        counts = population_counts(conn)
        assert counts["suppressed"] == 50
        assert counts["actionable"] == 0

    def test_the_window_excludes_rows_older_than_it(self, gate_db):
        conn = _conn(gate_db)
        _add_recommendation(conn, ticker="OLD", contracts=5, created_ms=1_000)
        _add_recommendation(conn, ticker="NEW", contracts=5, created_ms=9_000)

        assert population_counts(conn, since_ms=5_000)["actionable"] == 1
        assert population_counts(conn, since_ms=0)["actionable"] == 2

    def test_the_progress_line_prints_zero_rather_than_nothing(
        self, gate_db, caplog
    ):
        """Zero is the value this counter has held for the project's life.

        A line filtered out at zero cannot be told from a line that stopped
        being computed — the failure `tasks/lessons.md` records twice, and both
        times on a counter whose interesting value *was* zero.
        """
        conn = _conn(gate_db)
        with caplog.at_level(logging.INFO, logger="backend.gate"):
            log_gate_progress(conn, since_ms=0, required=300)

        lines = [r.getMessage() for r in caplog.records if "gate progress" in
                 r.getMessage()]
        assert len(lines) == 1
        assert "actionable=0 of 300 needed" in lines[0]
        assert "suppressed by: none" in lines[0], lines[0]

    def test_the_progress_line_names_why_rows_were_suppressed(
        self, gate_db, caplog
    ):
        """`actionable=0` alone cannot separate a quiet slate from a bad rule.

        A dominant reason is a miscalibration to investigate; a spread of them
        with `no_edge` large is the honest no-edge answer. Both are findings,
        and they are different ones.
        """
        conn = _conn(gate_db)
        for i in range(3):
            _add_recommendation(
                conn, ticker=f"N{i}", suppressed="edge_within_method_noise"
            )
        _add_recommendation(conn, ticker="W", suppressed="wide_market")
        _add_recommendation(conn, ticker="OK", contracts=4)

        with caplog.at_level(logging.INFO, logger="backend.gate"):
            log_gate_progress(conn, since_ms=0, required=300)

        line = [r.getMessage() for r in caplog.records
                if "gate progress" in r.getMessage()][0]
        assert "actionable=1 of 300 needed" in line
        assert "suppressed=4" in line
        assert "edge_within_method_noise=3" in line
        assert "wide_market=1" in line

    def test_a_refused_row_is_not_counted_as_the_strategys_edge(self, gate_db):
        """The discriminating case, and the reason this is not merely tidier.

        Dilution toward zero would only be conservative. The danger is a
        *systematic* CLV in the refused population — `suspicious_edge` rows are
        the ones most likely to carry one — which moves the pooled mean rather
        than blunting it. Here every refused row beats the close by 40 tenths
        and nothing actionable exists at all, so the pooled figure looks like a
        strong edge and the strategy has demonstrated nothing.
        """
        conn = _conn(gate_db)
        for i in range(12):
            _add_recommendation(
                conn, clv_tenths=40.0, ticker=f"S{i}", suppressed="suspicious_edge"
            )

        groups = clv_by_population(conn)
        assert groups["pooled"].mean_tenths == pytest.approx(40.0)
        assert groups["actionable"].n_rows == 0
        assert groups["actionable"].mean_tenths is None, (
            "an empty population must report no mean rather than 0.0 — "
            "'no measurement' and 'measured zero' are different claims"
        )

        # The floor counts actionable games, so a record made entirely of
        # refused ones is worth exactly zero toward it however well those
        # refused games beat the close.
        decision = evaluate_gate(
            conn, GateConfig(live_trading_enabled=True, min_scored_recommendations=3)
        )
        sample = next(
            c for c in decision.conditions if c.name == "scored_recommendations"
        )
        noise = next(
            c for c in decision.conditions if c.name == "clv_survives_noise_guard"
        )
        assert not sample.met, (
            "12 games at +40 tenths cleared a floor of 3, on games the strategy "
            "refused to bet"
        )
        assert not noise.met
        assert not decision.open

        assert "0 of 3 independent actionable games" in sample.detail
        assert "suppressed 12g/12r" in sample.detail
        assert "actionable 0g/0r" in sample.detail
        assert "the floor does not count them" in sample.detail, (
            "the gate showed a zero with no explanation beside a record of 12 "
            "scored games, which reads as a fault rather than as the answer"
        )

    def test_the_disclaimer_is_absent_once_something_is_actionable(self, gate_db):
        """A sentence that always appears carries no information.

        The other direction of the guard above: as soon as a single actionable
        row is scored, the number stops being purely a claim about refused rows
        and the copy must stop saying it is.
        """
        conn = _conn(gate_db)
        _add_recommendation(conn, clv_tenths=5.0, ticker="S", suppressed="stale_odds")
        _add_recommendation(conn, clv_tenths=5.0, ticker="A", contracts=3)

        sample = next(
            c
            for c in evaluate_gate(conn, GateConfig()).conditions
            if c.name == "scored_recommendations"
        )
        assert "actionable 1g/1r" in sample.detail
        assert "the floor does not count them" not in sample.detail

    def test_an_empty_record_claims_nothing_about_any_population(self, gate_db):
        """With no rows at all there is nothing to disclaim either."""
        conn = _conn(gate_db)
        sample = next(
            c
            for c in evaluate_gate(conn, GateConfig()).conditions
            if c.name == "scored_recommendations"
        )
        assert "actionable 0g/0r" in sample.detail
        assert "the floor does not count them" not in sample.detail

    def test_an_unknown_population_refuses_rather_than_pooling(self, gate_db):
        """Falling through to the mixture under a group's name is the exact
        confusion the parameter exists to end."""
        conn = _conn(gate_db)
        with pytest.raises(ValueError, match="unknown population"):
            clustered_clv(conn, "actionabel")


class TestTheGateIsEvaluatedRepeatedly:
    """The noise guard must hold under continuous monitoring, not one look.

    `evaluate_gate` runs on every request against a database that grows all day.
    A two-standard-error threshold is a statement about one pre-registered look;
    under a zero-edge process the running z-score wanders and crosses it
    eventually with probability 1. This is the multiple-comparisons lesson along
    the time axis, on the path that arms real money.
    """

    def test_pure_noise_crosses_two_standard_errors_under_repeated_looks(self):
        """The problem, demonstrated rather than asserted.

        Twelve hundred zero-edge sequences, each looked at after every new game.
        The fixed-sample rule fires on 13.7% of them. It is not miscalibrated —
        it is being used for something it does not cover.

        13.7% is a *floor* on the real rate, not an estimate of it: this looks
        100 times at a sequence of 120 games, while the live gate is evaluated
        on every request for as long as the record grows.
        """
        rng = random.Random(20260807)
        fired = 0
        trials = 1200

        for _ in range(trials):
            values: list[float] = []
            for _ in range(120):
                values.append(rng.gauss(0.0, 30.0))
                if len(values) < 20:
                    continue
                _, _, mean, stderr = _cluster_robust_stderr([(1, v) for v in values])
                if mean > 2 * stderr:
                    fired += 1
                    break

        rate = fired / trials
        assert rate == pytest.approx(0.137, abs=0.02), (
            f"expected the naive rule to fire on ~13.7% of pure-noise sequences, "
            f"got {rate:.1%}"
        )
        assert rate > 2.5 * ALWAYS_VALID_ALPHA, (
            "the whole point is that this is far above the nominal level"
        )

    def test_the_always_valid_bound_holds_under_the_same_repeated_looks(self):
        """The fix, on the identical sequences and the identical looking schedule.

        The false-positive rate must sit at or below alpha across the whole
        sequence of looks, not per look.
        """
        rng = random.Random(20260807)
        fired = 0
        trials = 1200

        for _ in range(trials):
            values: list[float] = []
            for _ in range(120):
                values.append(rng.gauss(0.0, 30.0))
                if len(values) < 20:
                    continue
                n_rows, n_clusters, mean, stderr = _cluster_robust_stderr(
                    [(1, v) for v in values]
                )
                stats = ClusteredMean(
                    n_rows=n_rows,
                    n_clusters=n_clusters,
                    mean_tenths=mean,
                    stderr_tenths=stderr,
                )
                if stats.distinguishable(300):
                    fired += 1
                    break

        rate = fired / trials
        assert rate <= ALWAYS_VALID_ALPHA, (
            f"always-valid bound must hold across all looks, fired {rate:.1%}"
        )

    def test_the_bound_is_wider_than_two_standard_errors_and_says_so(self):
        """The price of unlimited peeking, stated rather than hidden.

        At the pre-registered floor the multiplier is 3.66 rather than 2.

        The assertion that matters is the last one: there is **no** sample size
        at which this decays back into the fixed-sample rule. A bound that
        approached 2 for large `n` would be always-valid in name and
        fixed-sample in the regime the gate actually runs in.
        """
        at_floor = always_valid_multiplier(300, tuning=300)
        assert at_floor == pytest.approx(3.66, abs=0.01)
        assert at_floor / 2.0 == pytest.approx(1.83, abs=0.01)

        # Falls to a floor near n ~ 8m, then climbs like sqrt(log n). Not
        # minimised at n == m, which is easy to assume and wrong.
        curve = {n: always_valid_multiplier(n, tuning=300) for n in (20, 300, 2464, 100_000)}
        assert curve[20] > curve[300] > curve[2464] < curve[100_000]
        assert min(curve.values()) == pytest.approx(3.04, abs=0.01)

        for n in (2, 10, 300, 2_464, 10_000, 1_000_000):
            assert always_valid_multiplier(n, tuning=300) > 3.0, (
                f"multiplier at n={n} must never approach the fixed-sample 2"
            )

    def test_the_gate_reports_the_boundary_it_actually_used(self, gate_db):
        """A threshold a reader cannot see is a threshold they cannot check."""
        conn = _conn(gate_db)
        for i in range(40):
            _add_recommendation(conn, clv_tenths=float(i % 7), ticker=f"T{i}")

        noise = next(
            c
            for c in evaluate_gate(
                conn,
                GateConfig(live_trading_enabled=True, min_scored_recommendations=300),
            ).conditions
            if c.name == "clv_survives_noise_guard"
        )
        assert "always-valid bound" in noise.detail
        assert "not 2" in noise.detail
        assert "standard errors" in noise.detail


class TestFreshness:
    def test_age_is_recomputed_from_the_clock_not_read_off_the_row(self, gate_db):
        """The subtle one. `kalshi_quote_age_ms` is the age *when the
        recommendation was written*. Reading it straight out would let a
        day-old recommendation report a three-second-old quote forever."""
        conn = _conn(gate_db)
        recommendation_id = _add_recommendation(
            conn,
            clv_tenths=10.0,
            quote_age=3_000,
            created_ms=int(time.time() * 1000) - DAY_MS,
        )
        freshness = recommendation_freshness(conn, recommendation_id)
        assert freshness["kalshi_quote_age_ms"] > DAY_MS

    def test_a_stale_quote_fails_the_freshness_condition(self, gate_db):
        conn = _conn(gate_db)
        decision = evaluate_gate(
            conn, GateConfig(live_trading_enabled=True),
            staleness=StalenessConfig(max_kalshi_quote_age_s=30, max_odds_age_s=900),
            kalshi_quote_age_ms=DAY_MS,
            odds_age_ms=1_000,
        )
        fresh = next(c for c in decision.conditions if c.name == "data_fresh")
        assert not fresh.met

    def test_fresh_data_passes(self, gate_db):
        conn = _conn(gate_db)
        decision = evaluate_gate(
            conn, GateConfig(live_trading_enabled=True),
            staleness=StalenessConfig(max_kalshi_quote_age_s=30, max_odds_age_s=900),
            kalshi_quote_age_ms=2_000,
            odds_age_ms=60_000,
        )
        fresh = next(c for c in decision.conditions if c.name == "data_fresh")
        assert fresh.met

    def test_freshness_is_absent_when_no_ages_are_supplied(self, gate_db):
        """The Gate screen reports standing readiness; freshness belongs to a
        single order at a single instant."""
        conn = _conn(gate_db)
        decision = evaluate_gate(conn, GateConfig(live_trading_enabled=True))
        assert not any(c.name == "data_fresh" for c in decision.conditions)

    def test_a_missing_recommendation_is_reported_as_absent(self, gate_db):
        assert recommendation_freshness(_conn(gate_db), 99999)["found"] is False


class TestConfirmationSeparatesTwoKindsOfStale:
    """"This observation is old" and "this price is old" were one number.

    `persist_if_changed` writes no second row for an unchanged decision -- right
    for the record, because ~98% of it would otherwise be repetition -- and
    every freshness check measured from `created_ms`. So a row expired thirty
    seconds after the pass that wrote it on a market that had not moved at all,
    and the tool was actionable for about a minute a day rather than the fifteen
    minutes documented everywhere in this repo.

    A confirmation restates *both* ages at one instant. The tests below are
    chosen so that the tempting half-fix -- refresh the quote clock, leave the
    odds clock alone -- gives a different answer from the correct one.
    """

    def _confirm(self, conn, rec_id, *, at, quote_age, odds_age):
        confirm_recommendation(
            conn, rec_id, confirmed_ms=at,
            kalshi_quote_age_ms=quote_age, odds_age_ms=odds_age,
        )
        return conn.execute(
            "SELECT * FROM recommendations WHERE id = ?", (rec_id,)
        ).fetchone()

    def test_an_unconfirmed_row_still_ages_from_when_it_was_written(self, gate_db):
        """The pre-existing behaviour, unchanged, for every row already recorded.

        The migration adds NULL columns to a live database, so this is the path
        every historical row takes and it must not move.
        """
        conn = _conn(gate_db)
        rec_id = _add_recommendation(
            conn, quote_age=3_000, odds_age=60_000, created_ms=1_000_000
        )
        row = conn.execute(
            "SELECT * FROM recommendations WHERE id = ?", (rec_id,)
        ).fetchone()

        ages = live_ages(row, now_ms=1_000_000 + 20_000)
        assert ages.quote_age_ms == 23_000
        assert ages.odds_age_ms == 80_000
        assert ages.confirmed is False
        assert ages.measured_from_ms == 1_000_000

    def test_a_confirmed_row_ages_from_the_confirmation(self, gate_db):
        """The fix. Same row, same market, re-derived twenty seconds later."""
        conn = _conn(gate_db)
        rec_id = _add_recommendation(
            conn, quote_age=0, odds_age=60_000, created_ms=1_000_000
        )
        row = self._confirm(
            conn, rec_id, at=1_000_000 + 800_000, quote_age=0, odds_age=860_000
        )

        # Twenty seconds after the confirmation, not 820 seconds after the row.
        ages = live_ages(row, now_ms=1_000_000 + 820_000)
        assert ages.quote_age_ms == 20_000
        assert ages.confirmed is True

        # Without the confirmation this row would read 820s old and be refused.
        assert 820_000 > StalenessConfig().max_kalshi_quote_age_s * 1000

    def test_confirming_cannot_outlive_the_odds_window(self, gate_db):
        """**The discriminating case.** Fast polling must not buy immortality.

        A row confirmed every twenty seconds has a permanently fresh Kalshi
        quote. If a confirmation reset the odds clock too -- or simply took the
        quote's freshness for both -- the row would stay bettable for as long as
        the process ran, on a sportsbook consensus swept hours earlier. That is
        the failure this whole project is built to avoid: an edge measured
        against a price nobody is offering any more.

        So: quote perfectly fresh, odds past their limit, and the row must be
        refused on the odds.
        """
        conn = _conn(gate_db)
        rec_id = _add_recommendation(
            conn, quote_age=0, odds_age=10_000, created_ms=1_000_000
        )
        # An hour of quote passes later. The quote is current; the consensus is
        # the same one swept at the start, so it has aged the whole hour.
        row = self._confirm(
            conn, rec_id, at=1_000_000 + 3_600_000, quote_age=0, odds_age=3_610_000
        )

        ages = live_ages(row, now_ms=1_000_000 + 3_600_000)
        assert ages.quote_age_ms == 0
        assert ages.odds_age_ms == 3_610_000
        assert ages.odds_age_ms > StalenessConfig().max_odds_age_s * 1000, (
            "a confirmed row must still expire when its odds do"
        )

    def test_the_odds_clock_is_untouched_by_a_confirmation_with_no_new_sweep(
        self, gate_db
    ):
        """A definitional anchor: with no new sweep, confirming changes nothing.

        The odds observation instant is fixed, so measuring from `created_ms`
        and measuring from the confirmation must give the *same* odds age --
        bit-identical, not merely close. An implementation that credited a
        confirmation with fresher odds than it observed fails here.
        """
        conn = _conn(gate_db)
        rec_id = _add_recommendation(
            conn, quote_age=0, odds_age=60_000, created_ms=1_000_000
        )
        before = live_ages(
            conn.execute(
                "SELECT * FROM recommendations WHERE id = ?", (rec_id,)
            ).fetchone(),
            now_ms=1_000_000 + 500_000,
        )
        # The same consensus, re-read 500s later: its age grew by exactly 500s.
        row = self._confirm(
            conn, rec_id, at=1_000_000 + 500_000, quote_age=0, odds_age=560_000
        )
        after = live_ages(row, now_ms=1_000_000 + 500_000)

        assert after.odds_age_ms == before.odds_age_ms == 560_000

    def test_a_half_written_confirmation_falls_back_rather_than_guessing(
        self, gate_db
    ):
        """A timestamp with a missing age is not a confirmation.

        Substituting the created-time age for the missing half would silently
        build a freshness claim out of two different instants. Refusing is the
        same rule as refusing an unreadable price.
        """
        conn = _conn(gate_db)
        rec_id = _add_recommendation(
            conn, quote_age=3_000, odds_age=60_000, created_ms=1_000_000
        )
        conn.execute(
            "UPDATE recommendations SET last_confirmed_ms = ?, "
            "last_confirmed_quote_age_ms = 0 WHERE id = ?",
            (1_000_000 + 800_000, rec_id),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM recommendations WHERE id = ?", (rec_id,)
        ).fetchone()
        ages = live_ages(row, now_ms=1_000_000 + 820_000)
        assert ages.confirmed is False
        assert ages.quote_age_ms == 823_000

    def test_a_confirmation_before_the_decision_is_ignored(self, gate_db):
        """Nothing should produce one, and if something does it must not
        move the basis backwards and make a row look younger than it is."""
        conn = _conn(gate_db)
        rec_id = _add_recommendation(
            conn, quote_age=1_000, odds_age=60_000, created_ms=1_000_000
        )
        row = self._confirm(
            conn, rec_id, at=1_000_000 - 500_000, quote_age=0, odds_age=0
        )
        ages = live_ages(row, now_ms=1_000_000 + 10_000)
        assert ages.confirmed is False
        assert ages.quote_age_ms == 11_000

    def test_the_order_endpoint_reads_the_confirmation(self, gate_db):
        """The whole chain, through the function the money path actually calls.

        `live_ages` being right is not the claim; the claim is that the control
        which refuses orders uses it.
        """
        conn = _conn(gate_db)
        now = int(time.time() * 1000)
        rec_id = _add_recommendation(
            conn, quote_age=0, odds_age=60_000, created_ms=now - 600_000
        )

        stale = recommendation_freshness(conn, rec_id)
        assert stale["kalshi_quote_age_ms"] > 30_000
        assert stale["confirmed"] is False

        confirm_recommendation(
            conn, rec_id, confirmed_ms=now - 2_000,
            kalshi_quote_age_ms=0, odds_age_ms=658_000,
        )
        fresh = recommendation_freshness(conn, rec_id)
        assert fresh["kalshi_quote_age_ms"] < 30_000
        assert fresh["confirmed"] is True
        assert fresh["created_ms"] == now - 600_000, (
            "the record must say when the decision was made, not when it was "
            "last re-derived"
        )


class TestTheGateCanActuallyOpen:
    """`GateDecision.open` was never asserted `True` anywhere in the suite.

    Every gate test checked that it stays shut. So `evaluate_gate` could have
    returned a permanently-closed decision — a hardcoded `False`, a condition
    that can never be satisfied, a typo in a threshold — and all of them would
    have passed. A lock nobody has ever unlocked is not a verified lock; it is
    an untested one that happens to be in the safe state.

    This matters more than it sounds: several conditions here were tightened
    today (clustering by game, the always-valid bound, the fee tolerance going
    to 1e-9). Any of those could have made the gate unsatisfiable in principle,
    and nothing would have said so.
    """

    def _fully_satisfied(self, conn):
        """A record meeting every evidence condition.

        400 distinct games with a consistent +2c CLV and a hair of spread, so it
        clears the always-valid bound rather than merely two standard errors,
        plus one fill whose predicted fee matches exactly.
        """
        for i in range(400):
            _add_recommendation(
                conn, clv_tenths=20.0 + (0.5 if i % 2 else -0.5), ticker=f"G{i}"
            )
        conn.execute(
            "INSERT INTO fills (kalshi_fill_id, ticker, filled_ms, count, "
            "price_tenths, is_taker, fee_actual, fee_predicted, fee_model_used) "
            "VALUES ('f1', 'G0', 1, 10, 500, 1, 0.35, 0.35, 'conservative')"
        )
        conn.commit()

    def test_every_condition_can_be_satisfied_at_once(self, gate_db):
        conn = _conn(gate_db)
        self._fully_satisfied(conn)

        decision = evaluate_gate(
            conn, GateConfig(live_trading_enabled=True, min_scored_recommendations=300)
        )
        assert decision.open, f"gate stayed shut: {decision.reason}"
        assert decision.unmet == ()

    def test_removing_any_single_condition_shuts_it_again(self, gate_db):
        """Proves the open state is earned rather than accidental.

        If the gate opened for a reason unrelated to the conditions, knocking
        one out would leave it open.
        """
        conn = _conn(gate_db)
        self._fully_satisfied(conn)
        assert evaluate_gate(
            conn, GateConfig(live_trading_enabled=True, min_scored_recommendations=300)
        ).open

        # The human act, withheld.
        assert not evaluate_gate(
            conn, GateConfig(live_trading_enabled=False, min_scored_recommendations=300)
        ).open

        # The evidence floor, raised beyond the record.
        assert not evaluate_gate(
            conn, GateConfig(live_trading_enabled=True, min_scored_recommendations=500)
        ).open

        # A fee the model got wrong.
        conn.execute("UPDATE fills SET fee_actual = 0.36")
        conn.commit()
        shut = evaluate_gate(
            conn, GateConfig(live_trading_enabled=True, min_scored_recommendations=300)
        )
        assert not shut.open
        assert any(c.name == "fee_model_verified" for c in shut.unmet)

    def test_a_stale_quote_shuts_an_otherwise_open_gate(self, gate_db):
        """Freshness is judged per order, so it is checked separately."""
        conn = _conn(gate_db)
        self._fully_satisfied(conn)
        armed = GateConfig(live_trading_enabled=True, min_scored_recommendations=300)

        assert evaluate_gate(
            conn, armed, kalshi_quote_age_ms=1_000, odds_age_ms=60_000
        ).open
        assert not evaluate_gate(
            conn, armed, kalshi_quote_age_ms=900_000, odds_age_ms=60_000
        ).open


class TestTheGateCountsOneHorizonOnly:
    """Found by disabling: removing the horizon filter from `clustered_clv` left
    the suite green.

    Not an unreachable guard — a missing input. Every fixture scored every row
    at one horizon, so a filter on it could not change any outcome. The
    discriminating case needs two horizons in one database, which is exactly the
    state ADR 0011 creates: the record now holds 1.0h lines as the control while
    the primary is 0.0.
    """

    def test_a_row_scored_at_the_control_horizon_does_not_count(self, gate_db):
        conn = _conn(gate_db)
        _add_recommendation(
            conn, clv_tenths=20.0, ticker="A", event="E1",
            horizon=DEFAULT_HORIZON_HOURS,
        )
        _add_recommendation(
            conn, clv_tenths=20.0, ticker="B", event="E2",
            horizon=CONTROL_HORIZON_HOURS,
        )

        stats = clustered_clv(conn)
        assert stats.n_rows == 1, (
            "the gate averaged rows anchored at two different instants"
        )
        assert stats.n_clusters == 1

    def test_changing_the_horizon_drops_the_counter_rather_than_blending(
        self, gate_db
    ):
        """The consequence, asserted as the intended behaviour.

        A horizon change must invalidate evidence *loudly*. If the counter held
        steady while the anchor moved, the gate would be averaging two
        measurements and reporting the mixture under one name — the failure
        `clv_by_population` was built to end, one level down.
        """
        conn = _conn(gate_db)
        for i in range(5):
            _add_recommendation(
                conn, clv_tenths=20.0, ticker=f"T{i}", event=f"E{i}",
                horizon=CONTROL_HORIZON_HOURS,
            )

        assert clustered_clv(conn).n_rows == 0
