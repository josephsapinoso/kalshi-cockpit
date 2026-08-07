"""The execution path: order construction, the gate, and what each refuses.

This is the only code in the project that can lose money, so the tests here are
weighted toward the refusals rather than the happy path. The headline assertion
is `test_an_off_grid_price_raises_rather_than_clamping` — clamping instead of
raising is the specific mistake that turned a self-announcing API rejection into
a live buy at 99c in the predecessor project.
"""

from __future__ import annotations

import sqlite3
import time

import pytest

from backend.config import GateConfig, StalenessConfig
from backend.gate import evaluate_gate, recommendation_freshness
from backend.kalshi.orders import (
    API_PRICE_MAX,
    API_PRICE_MIN,
    OrderPlacer,
    OrderRefused,
    OrderRequest,
    api_price_cents,
)
from backend.store import db

DAY_MS = 86_400_000


def order(**kw) -> OrderRequest:
    defaults = dict(
        ticker="KXNFLGAME-26AUG27KCBAL-KC",
        side="yes",
        action="buy",
        count=20,
        limit_price_tenths=503,
    )
    defaults.update(kw)
    return OrderRequest(**defaults)


class TestApiPriceRounding:
    """Round away from paying more, and refuse rather than clamp."""

    def test_a_buy_rounds_down(self):
        """Rounding a buy up would pay more than the price we evaluated."""
        assert api_price_cents(509, "buy") == 50

    def test_a_sell_rounds_up(self):
        assert api_price_cents(501, "sell") == 51

    def test_an_exact_cent_is_unchanged_either_way(self):
        assert api_price_cents(500, "buy") == 50
        assert api_price_cents(500, "sell") == 50

    def test_an_off_grid_price_raises_rather_than_clamping(self):
        """The rule that earned itself.

        Clamping turned `no_price=-390` -- which the exchange would have
        rejected outright -- into a live buy at 99c. A price being validated
        must be refused, not coerced onto the nearest legal value.
        """
        with pytest.raises(OrderRefused) as exc:
            api_price_cents(9, "buy")        # rounds to 0c
        assert "clamping" in str(exc.value)
        assert str(API_PRICE_MIN) in str(exc.value)

    def test_the_top_of_the_grid_is_refused_too(self):
        with pytest.raises(OrderRefused):
            api_price_cents(999, "sell")     # rounds to 100c

    def test_the_grid_boundaries_themselves_are_accepted(self):
        assert api_price_cents(10, "buy") == API_PRICE_MIN
        assert api_price_cents(990, "sell") == API_PRICE_MAX

    def test_an_unknown_action_is_refused(self):
        with pytest.raises(OrderRefused):
            api_price_cents(500, "hedge")


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
            {"limit_price_tenths": 5},       # off-grid after rounding
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

    def test_the_body_names_the_price_field_per_side(self):
        assert "yes_price" in order(side="yes").to_api_dict()
        assert "no_price" in order(side="no").to_api_dict()

    def test_the_body_carries_the_idempotency_key(self):
        built = order()
        assert built.to_api_dict()["client_order_id"] == built.client_order_id

    def test_worst_case_cost_uses_the_price_actually_sent(self):
        """Rounding is in our favour, so quoting the unrounded price would
        overstate the cost.

        50.9c rounds down to 50c, giving $50.00 of stake. The fee on top is
        $2.00 -- 50c is exactly where the conservative model peaks, at 2c per
        contract -- so the worst case is $52.00. Quoting the unrounded 50.9c
        would have said $50.90 of stake for a fill that costs $50.00.
        """
        built = order(count=100, limit_price_tenths=509)
        assert built.api_price == 50
        assert built.worst_case_cost_dollars == pytest.approx(52.0)


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
        assert "yes_price" in outcome.request_body

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


def _add_recommendation(
    conn, *, clv_tenths=None, scored=True, quote_age=1000, odds_age=60_000,
    suppressed=None, created_ms=None, ask=503,
):
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, series_ticker) "
        "VALUES ('T', 'E', 'S')"
    )
    conn.execute(
        """
        INSERT INTO recommendations (
            created_ms, ticker, strategy_config_version, side, entry_ask_tenths,
            fair_probability, edge_tenths, fee_predicted, ev_net_dollars,
            suggested_contracts, kelly_fraction, kalshi_quote_age_ms,
            odds_age_ms, suppressed_reason, reason_text, clv_tenths,
            clv_scored_ms
        ) VALUES (?, 'T', 1, 'yes', ?, 0.55, 20.0, 0.1, 0.5, 20, 0.02, ?, ?, ?,
                  'test', ?, ?)
        """,
        (
            created_ms or int(time.time() * 1000), ask, quote_age, odds_age,
            suppressed, clv_tenths,
            int(time.time() * 1000) if scored else None,
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
        and it is inside two standard errors of zero."""
        conn = _conn(gate_db)
        # Alternating +/- with a small positive drift: positive mean, huge spread.
        for i in range(400):
            _add_recommendation(conn, clv_tenths=(50.0 if i % 2 else -48.0))

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
            _add_recommendation(conn, clv_tenths=20.0 + (1.0 if i % 2 else -1.0))
        decision = evaluate_gate(
            conn, GateConfig(live_trading_enabled=True, min_scored_recommendations=300)
        )
        noise = next(c for c in decision.conditions if c.name == "clv_survives_noise_guard")
        assert noise.met

    def test_a_small_sample_cannot_clear_the_guard_by_being_extreme(self, gate_db):
        conn = _conn(gate_db)
        for _ in range(5):
            _add_recommendation(conn, clv_tenths=100.0)
        decision = evaluate_gate(
            conn, GateConfig(live_trading_enabled=True, min_scored_recommendations=300)
        )
        assert not decision.open
        assert any(c.name == "scored_recommendations" for c in decision.unmet)


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
