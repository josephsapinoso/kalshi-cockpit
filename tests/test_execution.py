"""The execution path: order construction, the gate, and what each refuses.

This is the only code in the project that can lose money, so the tests here are
weighted toward the refusals rather than the happy path. The headline assertion
is `test_an_off_grid_price_raises_rather_than_clamping` — clamping instead of
raising is the specific mistake that turned a self-announcing API rejection into
a live buy at 99c in the predecessor project.
"""

from __future__ import annotations

import math
import random
import sqlite3
import statistics
import time

import pytest

from backend.config import GateConfig, StalenessConfig
from backend.gate import (
    ALWAYS_VALID_ALPHA,
    ClusteredMean,
    _cluster_robust_stderr,
    always_valid_multiplier,
    clustered_clv,
    evaluate_gate,
    recommendation_freshness,
)
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


_DEFAULT_EVENT = object()


def _add_recommendation(
    conn, *, clv_tenths=None, scored=True, quote_age=1000, odds_age=60_000,
    suppressed=None, created_ms=None, ask=503, ticker="T", event=_DEFAULT_EVENT,
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
            suggested_contracts, kelly_fraction, kalshi_quote_age_ms,
            odds_age_ms, suppressed_reason, reason_text, clv_tenths,
            clv_scored_ms
        ) VALUES (?, ?, 1, 'yes', ?, 0.55, 20.0, 0.1, 0.5, 20, 0.02, ?, ?, ?,
                  'test', ?, ?)
        """,
        (
            created_ms or int(time.time() * 1000), ticker, ask, quote_age, odds_age,
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
        assert "1 of 300 independent games" in sample.detail
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
