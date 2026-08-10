"""API tests, against a seeded database.

No live server and no network: `httpx.ASGITransport` drives the app in-process.

The assertions that matter are the boundary ones. The demo instance must have
no reachable execution path, and the gate must state *which* condition is
unmet rather than just refusing.
"""

from __future__ import annotations

import httpx
import pytest

from fastapi.testclient import TestClient

from backend.api.routes import create_app
from backend.config import AppConfig, GateConfig, StalenessConfig
from backend.seed_demo import seed_all


@pytest.fixture(scope="module")
def demo_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("api") / "demo.db"
    seed_all(path)
    return path


@pytest.fixture
def demo_app(demo_db):
    return create_app(AppConfig(instance_mode="demo", db_path=demo_db))


@pytest.fixture
def live_app(demo_db):
    return create_app(
        AppConfig(instance_mode="live", auth_token="secret-token", db_path=demo_db)
    )


async def get(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, **kwargs)


async def post(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.post(path, **kwargs)


class TestHealth:
    async def test_reports_demo_mode(self, demo_app):
        body = (await get(demo_app, "/api/health")).json()
        assert body["instance_mode"] == "demo"

    async def test_demo_never_reports_execution_available(self, demo_app):
        """A public URL must not be mistakable for the real thing."""
        assert (await get(demo_app, "/api/health")).json()["execution_available"] is False

    async def test_it_says_whether_alerting_is_configured(
        self, demo_app, monkeypatch
    ):
        """Setting a Fly secret from a phone has no feedback of its own.

        The loop logs `discord=on` at startup and Fly's log tail has usually
        rolled past it by the time anyone looks, so "I set the secret" and "the
        secret is in effect" are otherwise indistinguishable — and the failure
        mode of the second is silence, which is also what a working alerter
        looks like on a quiet night. `.github/workflows/secrets.yml` polls this
        field and fails the run if it stays false.
        """
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        monkeypatch.delenv("DISCORD_CHANNEL_ID", raising=False)
        body = (await get(demo_app, "/api/health")).json()
        assert body["notifications_configured"] is False

        monkeypatch.setenv(
            "DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/secret-token"
        )
        body = (await get(demo_app, "/api/health")).json()
        assert body["notifications_configured"] is True

    async def test_health_never_carries_the_credential_itself(
        self, demo_app, monkeypatch
    ):
        """A boolean is the whole point. `/api/health` must stay public — Fly's
        check reads it — so anything on it is world-readable."""
        monkeypatch.setenv(
            "DISCORD_WEBHOOK_URL",
            "https://discord.com/api/webhooks/1/xQ2v9LmT4pR7wYzB1nK6sHf",
        )
        body = (await get(demo_app, "/api/health")).text
        assert "xQ2v9LmT4pR7wYzB1nK6sHf" not in body


def sized_rows(board: dict) -> list[dict]:
    """Every row the engine sized, whether or not it is still bettable.

    `surfaced` is now a claim about *this instant* -- both ages inside the
    staleness contract -- so a fixture seeded at the fixed demo timestamp has
    none, correctly. Tests about the *shape* of a row use this; tests about
    actionability use a fixture on the current clock and say so.
    """
    return board["surfaced"] + board["expired"]


class TestBoard:
    async def test_returns_the_opportunities_the_engine_sized(self, demo_app):
        body = (await get(demo_app, "/api/board")).json()
        rows = sized_rows(body)
        assert len(rows) >= 1
        assert all(r["suggested_contracts"] > 0 for r in rows)

    async def test_suppressed_are_hidden_by_default(self, demo_app):
        assert (await get(demo_app, "/api/board")).json()["suppressed"] == []

    async def test_suppressed_are_available_with_their_reasons(self, demo_app):
        """They are evidence, not noise -- hiding them entirely would make a
        miscalibrated rule invisible."""
        body = (await get(demo_app, "/api/board?include_suppressed=true")).json()
        assert body["suppressed"]
        assert all(r["suppressed_reason"] for r in body["suppressed"])

    async def test_an_empty_board_is_explained_as_normal(self, demo_app):
        """Most candidates have no edge. That must not read as a malfunction."""
        assert "normal" in (await get(demo_app, "/api/board")).json()["note"]

    async def test_prices_are_sent_as_tenths_and_as_display_text(self, demo_app):
        """The frontend must never re-derive a price from a float."""
        row = sized_rows((await get(demo_app, "/api/board")).json())[0]
        assert isinstance(row["ask_tenths"], int)
        assert row["ask_display"].endswith("c")

    async def test_every_row_carries_its_config_version(self, demo_app):
        row = sized_rows((await get(demo_app, "/api/board")).json())[0]
        assert row["strategy_config_version"] >= 1


class TestTheRowSaysWhatLeavesTheAccount:
    """`COST` was the stake alone, with `FEE` beside it and no total anywhere.

    The understatement is 3.6% at 50c and 10% at 10c -- against 0.38 points of
    total headroom. Every figure here is computed server-side: a second
    implementation of the fee curve in the browser would be two money
    calculations one refresh apart, and the curve itself is an unresolved hedge
    between two disagreeing sources.
    """

    async def test_the_total_is_the_stake_plus_the_fee(self, demo_app):
        row = sized_rows((await get(demo_app, "/api/board")).json())[0]
        assert row["total_cost_dollars"] == pytest.approx(
            row["stake_dollars"] + row["fee_predicted"]
        )

    async def test_the_total_exceeds_the_stake_whenever_there_is_a_fee(
        self, demo_app
    ):
        """The assertion that fails if the total is silently the stake again."""
        rows = [r for r in sized_rows((await get(demo_app, "/api/board")).json())
                if r["fee_predicted"] > 0]
        assert rows
        assert all(r["total_cost_dollars"] > r["stake_dollars"] for r in rows)

    async def test_the_stake_is_the_ask_times_the_size(self, demo_app):
        row = sized_rows((await get(demo_app, "/api/board")).json())[0]
        assert row["stake_dollars"] == pytest.approx(
            row["ask_tenths"] * row["suggested_contracts"] / 1000
        )


class TestTheRowSaysWhatHappensWhenItLoses:
    """Nothing on the card said what the downside was.

    The demo's best row is +$0.26 expected with a standard deviation of $7.48 --
    29 times the mean. Ten such bets is a 46% chance of a losing week even if the
    edge is entirely real, and a beginner supplied with only the mean will
    conclude the tool is broken or double up.
    """

    async def test_the_deviation_is_the_binary_one_for_the_whole_position(
        self, demo_app
    ):
        """A contract settles at $1 or $0, so its payoff spread is exactly $1.

        The fee is deterministic and contributes no variance, so the position's
        deviation is `contracts * sqrt(p(1-p))` and nothing else. Reproduced on
        the demo's best row before anything derived from it was rendered:
        15 contracts at p=0.5385 gives $7.478.
        """
        import math

        for row in sized_rows((await get(demo_app, "/api/board")).json()):
            p = row["fair_probability"]
            assert row["sd_dollars"] == pytest.approx(
                row["suggested_contracts"] * math.sqrt(p * (1 - p))
            )

    async def test_the_deviation_dwarfs_the_expected_value(self, demo_app):
        """The finding itself, asserted so it cannot quietly stop being true."""
        row = max(
            sized_rows((await get(demo_app, "/api/board")).json()),
            key=lambda r: r["suggested_contracts"],
        )
        assert row["sd_dollars"] > 10 * abs(row["ev_net_dollars"])

    async def test_an_unsized_row_has_no_deviation(self, demo_app):
        """Zero contracts is zero risk, not an unmeasurable one."""
        body = (await get(demo_app, "/api/board?include_suppressed=true")).json()
        assert body["suppressed"]
        assert all(r["sd_dollars"] == 0 for r in body["suppressed"])

    async def test_ten_bets_this_shape_lose_money_almost_half_the_time(
        self, demo_app
    ):
        """The review's 46%, reproduced from the payload rather than quoted."""
        row = max(
            sized_rows((await get(demo_app, "/api/board")).json()),
            key=lambda r: r["suggested_contracts"],
        )
        assert row["losing_run_bets"] == 10
        assert row["losing_run_probability"] == pytest.approx(0.456, abs=0.005)

    async def test_a_row_with_no_position_reports_no_run_probability(
        self, demo_app
    ):
        """`None`, never 0.5 and never 0: there is no run to lose."""
        body = (await get(demo_app, "/api/board?include_suppressed=true")).json()
        assert body["suppressed"]
        assert all(r["losing_run_probability"] is None for r in body["suppressed"])


class TestAProbabilityIsSentAsOne:
    async def test_the_fair_value_is_sent_as_a_percentage(self, demo_app):
        row = sized_rows((await get(demo_app, "/api/board")).json())[0]
        assert row["fair_percent_display"].endswith("%")

    async def test_it_agrees_with_the_probability_it_came_from(self, demo_app):
        row = sized_rows((await get(demo_app, "/api/board")).json())[0]
        assert float(row["fair_percent_display"].removesuffix("%")) == pytest.approx(
            row["fair_probability"] * 100, abs=0.06
        )


class TestTheWholeSlateIsAvailable:
    """Mispricing is a factor, not a filter.

    With zero actionable across ~200 decisions, the rows that did not survive
    are the only content the board has. Returning them relaxes nothing:
    `suggested_contracts` is still 0 on every one, and the order endpoint
    re-derives the decision server-side.
    """

    async def test_the_rest_of_the_slate_is_hidden_by_default(self, demo_app):
        assert (await get(demo_app, "/api/board")).json()["no_edge"] == []

    async def test_the_no_edge_rows_are_returned_with_the_rejected_ones(
        self, demo_app
    ):
        body = (await get(demo_app, "/api/board?include_suppressed=true")).json()
        assert len(body["no_edge"]) == body["counts"]["no_edge"]
        assert body["no_edge"]

    async def test_no_returned_row_outside_surfaced_offers_a_size(self, demo_app):
        """Visible is not bettable. If this fails, the board is offering a bet."""
        body = (await get(demo_app, "/api/board?include_suppressed=true")).json()
        for row in body["no_edge"] + body["suppressed"]:
            assert row["suggested_contracts"] == 0


class TestTheBoardCannotOfferWhatTheServerWillRefuse:
    """`surfaced` is a claim about this instant, not about the whole record.

    The Board ordered by `suggested_contracts` over every row ever written,
    with no clock in the query, and rendered each as a live buy with a size and
    a cost. So the best row an instance ever recorded sat at the top forever --
    and `POST /api/orders`, which recomputes the same ages, would have refused
    it. No money was ever at risk; the reader was.
    """

    @pytest.fixture
    def now_app(self, tmp_path):
        from backend.seed_demo import seed_all
        from backend.store.db import now_ms

        path = tmp_path / "now.db"
        seed_all(path, now_ms=now_ms())
        return create_app(AppConfig(instance_mode="demo", db_path=path))

    async def test_a_year_old_row_is_expired_rather_than_surfaced(self, demo_app):
        """The default seed is anchored on a fixed past timestamp."""
        body = (await get(demo_app, "/api/board")).json()
        assert body["counts"]["surfaced"] == 0
        assert body["counts"]["expired"] >= 1

    async def test_a_row_written_moments_ago_is_surfaced(self, now_app):
        body = (await get(now_app, "/api/board")).json()
        assert body["counts"]["surfaced"] >= 1
        assert all(r["actionable"] for r in body["surfaced"])

    async def test_a_stale_recorded_quote_is_a_stale_price_not_an_expired_row(
        self, tmp_path
    ):
        """Two limits bound one window, and they stopped meaning the same thing.

        This test used to assert the opposite: five minutes after a pass the
        books are inside their fifteen-minute limit and the quote is ten times
        outside its thirty-second one, so the row was `expired`. That was
        correct while the recorded quote was the price the order endpoint used.
        It is not any more -- the endpoint re-reads Kalshi inside the request,
        so the recorded age decides whether the **price on the card** is
        current, and the odds decide whether the row is bettable at all.

        Keeping the old assertion would have been the two-screens-disagree
        failure with the sign flipped: everything between thirty seconds and
        fifteen minutes after a pass -- which is nearly the whole window --
        struck through as expired while the server sold it.
        """
        from backend.seed_demo import seed_all
        from backend.store.db import now_ms

        path = tmp_path / "five-minutes-ago.db"
        seed_all(path, now_ms=now_ms() - 300_000)
        app = create_app(AppConfig(instance_mode="demo", db_path=path))
        body = (await get(app, "/api/board")).json()

        assert body["counts"]["surfaced"] >= 1
        assert body["counts"]["price_stale"] == body["counts"]["surfaced"]
        row = body["surfaced"][0]
        assert row["quote_age_now_ms"] > 30_000        # the price has moved on
        assert row["odds_age_now_ms"] < 900_000        # the consensus has not
        assert row["actionable"] is True
        assert row["price_is_current"] is False

    async def test_the_odds_clock_is_what_expires_a_row(self, tmp_path):
        """The other half of the pair above, and the one that must still hold.

        Nothing in this endpoint can refresh a sportsbook consensus -- that
        costs one of the day's two odds credits -- so once it ages out the row
        is dead however recently Kalshi was read.
        """
        from backend.seed_demo import seed_all
        from backend.store.db import now_ms

        path = tmp_path / "twenty-minutes-ago.db"
        seed_all(path, now_ms=now_ms() - 1_200_000)
        app = create_app(AppConfig(instance_mode="demo", db_path=path))
        body = (await get(app, "/api/board")).json()

        assert body["counts"]["surfaced"] == 0
        row = body["expired"][0]
        assert row["odds_age_now_ms"] > 900_000
        assert row["actionable"] is False

    async def test_an_expired_row_is_returned_rather_than_dropped(self, demo_app):
        """"Nothing to bet" and "the moment has passed" need different
        responses, and a filter that discards what it rejects cannot be
        audited."""
        body = (await get(demo_app, "/api/board")).json()
        assert body["expired"]
        assert all(r["suggested_contracts"] > 0 for r in body["expired"])
        assert all(r["actionable"] is False for r in body["expired"])

    async def test_the_current_age_is_sent_beside_the_recorded_one(self, demo_app):
        """A row from a year ago still stores "quote 3s old", because that is
        what it was. Rendering that number as the present is the whole bug."""
        row = sized_rows((await get(demo_app, "/api/board")).json())[0]
        assert row["kalshi_quote_age_ms"] < 1_000_000        # as recorded
        assert row["quote_age_now_ms"] > 10_000_000_000      # as it is now

    async def test_the_ledger_keeps_the_recorded_age_untouched(self, demo_app):
        """There the age is a historical fact about the observation. One field
        name meaning "then" on one screen and "now" on another is how two
        screens come to disagree."""
        row = (await get(demo_app, "/api/ledger")).json()["rows"][0]
        assert "quote_age_now_ms" not in row
        assert row["kalshi_quote_age_ms"] < 1_000_000

    async def test_the_board_states_the_limits_it_judged_against(self, demo_app):
        body = (await get(demo_app, "/api/board")).json()
        assert body["staleness"]["max_kalshi_quote_age_s"] == 30
        assert body["staleness"]["max_odds_age_s"] == 900

    async def test_the_board_and_the_order_endpoint_agree_on_expiry(
        self, tmp_path
    ):
        """The screen and the control share the arithmetic. If they diverge,
        the screen is the one that gets believed."""
        from backend.gate import recommendation_freshness
        from backend.seed_demo import seed_all
        from backend.store import db as store
        from backend.store.db import now_ms

        path = tmp_path / "agree.db"
        seed_all(path, now_ms=now_ms())
        app = create_app(AppConfig(instance_mode="demo", db_path=path))
        body = (await get(app, "/api/board")).json()

        conn = store.open_db(path, read_only=True)
        try:
            for row in sized_rows(body):
                control = recommendation_freshness(conn, row["id"])
                assert control["kalshi_quote_age_ms"] == pytest.approx(
                    row["quote_age_now_ms"], abs=2_000
                )
                assert control["odds_age_ms"] == pytest.approx(
                    row["odds_age_now_ms"], abs=2_000
                )
        finally:
            conn.close()

    async def test_a_confirmed_row_is_live_on_the_board_and_at_the_order_endpoint(
        self, tmp_path
    ):
        """The pair that would have come apart.

        `persist_if_changed` re-derives an unchanged decision and stamps the row
        rather than writing a new one, so the freshness basis moves. A Board
        still measuring from `created_ms` would report a ten-minute-old price on
        a row the quote pass re-checked two seconds ago -- and would go on
        reporting it after every confirmation, so the fast cadence would buy
        nothing visible. They share `live_ages` precisely so this cannot happen.
        """
        from backend.engine import confirm_recommendation
        from backend.gate import recommendation_freshness
        from backend.seed_demo import seed_all
        from backend.store import db as store
        from backend.store.db import now_ms

        path = tmp_path / "confirmed.db"
        # Ten minutes ago: the books are still inside their 900s limit, so the
        # rows are bettable, and every quote is far outside its 30s one, so the
        # prices shown are not the prices anyone would pay.
        seed_all(path, now_ms=now_ms() - 600_000)
        app = create_app(AppConfig(instance_mode="demo", db_path=path))
        before = (await get(app, "/api/board")).json()
        assert before["counts"]["price_stale"] == before["counts"]["surfaced"] >= 1
        target = before["surfaced"][0]

        writer = store.init_db(path)
        try:
            confirm_recommendation(
                writer, target["id"], confirmed_ms=now_ms() - 2_000,
                kalshi_quote_age_ms=0, odds_age_ms=602_000,
            )
        finally:
            writer.close()

        after = (await get(app, "/api/board")).json()
        surfaced = [r for r in after["surfaced"] if r["id"] == target["id"]]
        assert surfaced, "a re-derived row dropped off the board"
        assert surfaced[0]["freshness_confirmed"] is True
        assert surfaced[0]["price_is_current"] is True, (
            "a confirmation two seconds ago must make the displayed price current"
        )
        assert surfaced[0]["quote_age_now_ms"] < 30_000
        # Still bounded by the odds, which the confirmation did not refresh.
        assert 600_000 < surfaced[0]["odds_age_now_ms"] < 900_000

        conn = store.open_db(path, read_only=True)
        try:
            control = recommendation_freshness(conn, target["id"])
            assert control["confirmed"] is True
            assert control["kalshi_quote_age_ms"] == pytest.approx(
                surfaced[0]["quote_age_now_ms"], abs=2_000
            )
        finally:
            conn.close()


class TestMarketDetail:
    async def test_returns_a_known_market(self, demo_app, demo_db):
        board = (await get(demo_app, "/api/board")).json()
        ticker = sized_rows(board)[0]["ticker"]
        body = (await get(demo_app, f"/api/market/{ticker}")).json()
        assert body["ticker"] == ticker
        assert body["reason_text"]

    async def test_an_unknown_market_is_404_not_an_empty_object(self, demo_app):
        assert (await get(demo_app, "/api/market/NOPE")).status_code == 404


class TestActionableWindow:
    """Whether a pick can be acted on, which the Board could not previously say.

    Two sweeps a day at fifteen minutes each means the tool is actionable for
    about half an hour out of twenty-four. Without this endpoint an empty
    Board, a Board of expired rows, and a Board during the window all render
    identically.
    """

    @pytest.fixture
    def fresh_app(self, tmp_path):
        """A slate whose books moved a minute ago, on the current clock.

        Seeded at real `now` rather than the demo's fixed stamp: the window is
        the one number in this system measured against the wall clock, so a
        frozen slate can only ever demonstrate the closed state.
        """
        from backend.seed_demo import seed_all
        from backend.store.db import now_ms

        path = tmp_path / "fresh.db"
        seed_all(path, now_ms=now_ms())
        return create_app(AppConfig(instance_mode="demo", db_path=path))

    async def test_a_freshly_swept_slate_reports_an_open_window(self, fresh_app):
        body = (await get(fresh_app, "/api/window")).json()
        assert body["is_open"] is True
        assert 0 < body["seconds_remaining"] <= 900

    async def test_a_year_old_slate_reports_a_closed_window(self, demo_app):
        """The default demo seed is anchored on a fixed past timestamp."""
        body = (await get(demo_app, "/api/window")).json()
        assert body["is_open"] is False
        assert body["seconds_remaining"] is None

    async def test_open_never_claims_there_is_something_to_bet(self, fresh_app):
        """The two are independent, and conflating them is how a freshness
        indicator becomes a buy signal."""
        body = (await get(fresh_app, "/api/window")).json()
        assert "does not mean there is anything to bet" in body["note"]

    async def test_it_counts_fixtures_rather_than_averaging_them(self, fresh_app):
        """A slate can be half stale. One number for it would describe neither
        half -- and the seed deliberately contains a fixture whose books did
        not move, to demonstrate `stale_odds`."""
        body = (await get(fresh_app, "/api/window")).json()
        assert body["fixtures_upcoming"] > body["fixtures_fresh"] >= 1

    async def test_it_reports_the_remaining_budget_in_sweeps(self, fresh_app):
        """16 credits a day at 6 a call is two sweeps, and the seed spends both."""
        body = (await get(fresh_app, "/api/window")).json()
        assert body["spent_today"] == 12
        assert body["sweeps_remaining_today"] == 0

    async def test_the_demo_needs_no_odds_credential_to_render_it(self, tmp_path):
        """The demo instance holds no keys. A timetable must not require one."""
        import os

        from backend.seed_demo import seed_all

        path = tmp_path / "nocreds.db"
        seed_all(path)
        saved = os.environ.pop("ODDS_API_KEY", None)
        try:
            app = create_app(AppConfig(instance_mode="demo", db_path=path))
            assert (await get(app, "/api/window")).status_code == 200
        finally:
            if saved is not None:
                os.environ["ODDS_API_KEY"] = saved


class TestLedger:
    async def test_includes_suppressed_rows(self, demo_app):
        """Every recommendation is scored on CLV whether or not it was bet."""
        body = (await get(demo_app, "/api/ledger")).json()
        assert any(r["suppressed_reason"] for r in body["rows"])

    async def test_reports_progress_towards_the_gate(self, demo_app):
        body = (await get(demo_app, "/api/ledger")).json()
        assert body["clv_required"] == 300
        assert body["gate_open"] is False


class TestSuppressionSummary:
    async def test_counts_each_rule(self, demo_app):
        counts = (await get(demo_app, "/api/suppression")).json()["counts"]
        assert counts
        assert sum(counts.values()) >= 1


class TestGate:
    async def test_is_closed_and_says_why(self, demo_app):
        """A refusal without a reason is not actionable."""
        body = (await get(demo_app, "/api/gate")).json()
        assert body["open"] is False
        unmet = [c for c in body["conditions"] if not c["met"]]
        assert unmet
        assert all(c["detail"] for c in unmet)

    async def test_names_the_scored_recommendation_shortfall(self, demo_app):
        body = (await get(demo_app, "/api/gate")).json()
        condition = next(
            c for c in body["conditions"] if c["name"] == "scored_recommendations"
        )
        assert "300" in condition["detail"]


class TestMarketResults:
    """`/api/results` exists so a broken outcome pass is visible from a phone.

    The pass reported itself only through counters on the merged log line, i.e.
    `flyctl logs`, i.e. a laptop. A pass that silently stopped writing was
    undetectable from the one device always to hand, while outcomes aged out
    permanently at one day per day.
    """

    async def test_it_answers_and_leads_with_a_verdict(self, demo_app):
        body = (await get(demo_app, "/api/results")).json()
        assert body["verdict"] in {
            "recording", "NOT RECORDING", "nothing due yet", "no games in scope"
        }
        assert body["verdict_meaning"]

    async def test_the_verdict_agrees_with_the_numbers_beside_it(self, demo_app):
        """The failure this repo has already had: a correct statistic printed
        next to a verdict computed by a parallel path, where the verdict is the
        half that gets read. Here they must be one derivation."""
        body = (await get(demo_app, "/api/results")).json()
        if body["recorded_total"] > 0:
            assert body["verdict"] == "recording"
        elif body["pending_total"] > 0:
            assert body["verdict"] == "NOT RECORDING"

    async def test_it_reports_the_bounds_that_decide_what_is_lost(self, demo_app):
        """Abandonment is a query-time age bound, so the window is part of the
        answer. Without it a reader cannot tell whether `abandoned_total` means
        a broken pass or a deliberately narrow window."""
        body = (await get(demo_app, "/api/results")).json()
        assert body["max_age_after_commence_s"] > body["min_age_after_commence_s"]
        for key in ("abandoned_total", "expiring_soon_total", "unreadable_total"):
            assert isinstance(body[key], int)

    async def test_the_residue_populations_are_never_omitted_at_zero(
        self, demo_app
    ):
        """Zero is the healthy value for all three and must still be printed.
        A bound that only appears once it has dropped something reads as no
        bound at all until the day it bites."""
        body = (await get(demo_app, "/api/results")).json()
        assert {"abandoned_total", "unreadable_total", "expiring_soon_total"} <= (
            set(body)
        )


class TestExecutionBoundary:
    """The security boundary between the public demo and the live instance."""

    async def test_the_demo_refuses_order_placement_outright(self, demo_app):
        response = await post(demo_app, "/api/orders")
        assert response.status_code == 403
        assert "demo" in response.json()["detail"].lower()

    async def test_the_live_instance_requires_a_token(self, live_app):
        assert (await post(live_app, "/api/orders")).status_code == 401

    async def test_a_wrong_token_is_rejected(self, live_app):
        response = await post(
            live_app, "/api/orders", headers={"Authorization": "Bearer wrong"}
        )
        assert response.status_code == 401

    async def test_a_valid_token_still_meets_the_locked_gate(self, live_app, demo_db):
        """Authentication gets you to the gate. It does not open it."""
        import sqlite3

        conn = sqlite3.connect(demo_db)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id FROM recommendations WHERE suppressed_reason IS NULL LIMIT 1"
        ).fetchone()
        conn.close()

        response = await post(
            live_app,
            "/api/orders",
            headers={"Authorization": "Bearer secret-token"},
            json={
                "recommendation_id": row["id"],
                "contracts": 20,
                "idempotency_key": "gate-locked-probe",
            },
        )
        assert response.status_code == 423, "Locked"
        assert "locked" in str(response.json()["detail"]).lower()


NFL = "americanfootball_nfl"
DAY = 86_400_000
NOW = 1_754_800_000_000


def _leg(label, p, event, offset=0):
    return {
        "label": label,
        "probability": p,
        "event_key": event,
        "league": NFL,
        "commence_ms": NOW + offset,
    }


class TestDashboards:
    async def test_an_unbuilt_warehouse_returns_503_not_an_empty_payload(
        self, demo_db, tmp_path
    ):
        """An empty dashboard reads as 'nothing to report'. Only one of those
        two states needs someone to do something about it."""
        app = create_app(
            AppConfig(
                instance_mode="demo",
                db_path=demo_db,
                warehouse_path=tmp_path / "absent.duckdb",
            )
        )
        response = await get(app, "/api/dashboards")
        assert response.status_code == 503
        assert "dbt build" in response.json()["detail"]


class TestPlaybook:
    """The screen that reads `strategy_config_version` back.

    It cannot 503 the way `/api/dashboards` can: everything it needs is written
    by the same pass that writes a recommendation, so there is no separate
    build step to be missing.
    """

    async def test_it_reports_the_versions_the_seed_recorded(self, demo_app):
        body = (await get(demo_app, "/api/playbook")).json()
        assert body["config_versions"], "the demo seed records a strategy config"
        assert body["current_version"] is not None
        assert sum(v["recommendations"] for v in body["config_versions"]) > 0

    async def test_the_row_counts_agree_with_the_board(self, demo_app):
        """Both read the same table, so a disagreement is a query bug.

        Suppressed rows are included on purpose -- the suppression log is the
        thing that makes the record auditable, and a playbook that counted only
        surfaced rows would report a strategy as having produced nothing.
        """
        playbook = (await get(demo_app, "/api/playbook")).json()
        board = (await get(
            demo_app, "/api/board", params={"include_suppressed": "true"}
        )).json()

        counted = sum(v["recommendations"] for v in playbook["config_versions"])
        shown = (
            len(board["surfaced"]) + len(board["expired"])
            + len(board["suppressed"])
        )
        assert counted >= shown, (
            f"the playbook counted {counted} rows and the Board shows {shown}; "
            f"they read the same table"
        )

    async def test_it_says_the_historian_has_not_run(self, demo_app):
        """The demo seeds no lessons, and neither does live: nothing calls the
        Historian. The payload has to carry that rather than an empty list."""
        body = (await get(demo_app, "/api/playbook")).json()
        assert body["historian_has_run"] is False
        assert body["lessons"] == []

    async def test_it_is_reachable_on_the_demo_instance(self, demo_app):
        """No credentials, no order path, nothing to protect."""
        assert (await get(demo_app, "/api/playbook")).status_code == 200

    async def test_the_limit_is_bounded(self, demo_app):
        """An unbounded `limit` from a query string is a free table scan."""
        assert (await get(
            demo_app, "/api/playbook", params={"limit": "100000"}
        )).status_code == 200
        assert (await get(
            demo_app, "/api/playbook", params={"limit": "0"}
        )).status_code == 200


class TestBuilderParlay:
    async def test_a_typical_parlay_reports_the_book_hold(self, demo_app):
        body = {
            "legs": [
                _leg("A", 0.50, "E1"),
                _leg("B", 0.50, "E2", 8 * DAY),
                _leg("C", 0.53, "E3", 16 * DAY),
            ],
            "offered_american": 550,
        }
        payload = (await post(demo_app, "/api/builder/parlay", json=body)).json()
        assert payload["hold"] > 0.10
        assert not payload["is_positive_ev"]
        assert "holds" in payload["verdict"]

    async def test_same_game_legs_are_refused_with_the_reason(self, demo_app):
        """422 carrying the refusal text, not a plausible number."""
        body = {
            "legs": [_leg("Chiefs ML", 0.62, "E1"), _leg("Over 44.5", 0.51, "E1")],
            "offered_american": 250,
        }
        response = await post(demo_app, "/api/builder/parlay", json=body)
        assert response.status_code == 422
        assert "same fixture" in response.json()["detail"]
        assert "overstate" in response.json()["detail"]

    async def test_a_measured_correlation_unlocks_the_same_game_price(
        self, demo_app
    ):
        body = {
            "legs": [_leg("Chiefs ML", 0.62, "E1"), _leg("Over 44.5", 0.51, "E1")],
            "offered_american": 250,
            "correlation_overrides": [
                {"a": "Chiefs ML", "b": "Over 44.5", "rho": 0.35}
            ],
        }
        payload = (await post(demo_app, "/api/builder/parlay", json=body)).json()
        assert payload["correlation_was_supplied"] is True
        assert 0.0 < payload["fair_probability"] < 1.0

    async def test_the_independence_error_is_always_returned(self, demo_app):
        body = {
            "legs": [_leg("A", 0.55, "E1"), _leg("B", 0.52, "E2", 3_600_000)],
            "offered_american": 260,
        }
        payload = (await post(demo_app, "/api/builder/parlay", json=body)).json()
        assert "independence_error_points" in payload

    async def test_a_certainty_is_rejected_at_the_schema(self, demo_app):
        body = {
            "legs": [_leg("A", 1.0, "E1"), _leg("B", 0.5, "E2", 8 * DAY)],
            "offered_american": 260,
        }
        assert (
            await post(demo_app, "/api/builder/parlay", json=body)
        ).status_code == 422

    async def test_one_leg_is_not_a_parlay(self, demo_app):
        body = {"legs": [_leg("A", 0.5, "E1")], "offered_american": 260}
        assert (
            await post(demo_app, "/api/builder/parlay", json=body)
        ).status_code == 422

    async def test_the_kalshi_alternative_is_framed_as_a_different_bet(
        self, demo_app
    ):
        body = {
            "legs": [_leg("A", 0.50, "E1"), _leg("B", 0.50, "E2", 8 * DAY)],
            "offered_american": 260,
        }
        payload = (await post(demo_app, "/api/builder/parlay", json=body)).json()
        assert "Not the same bet" in payload["kalshi_alternative"]["note"]

    async def test_the_builder_is_available_on_the_demo_instance(self, demo_app):
        """It computes on supplied numbers and touches no credentials, so it is
        one of the more interesting things the public demo can show."""
        body = {
            "legs": [_leg("A", 0.50, "E1"), _leg("B", 0.50, "E2", 8 * DAY)],
            "offered_american": 260,
        }
        assert (
            await post(demo_app, "/api/builder/parlay", json=body)
        ).status_code == 200


class TestWongScreen:
    async def test_only_the_documented_windows_come_back(self, demo_app):
        response = await get(
            demo_app,
            "/api/builder/wong-screen",
            params={"lines": "Chiefs:-8,Eagles:-3.5,Jets:2,Bears:7.5,Bills:-7.5"},
        )
        teams = {c["team"] for c in response.json()["candidates"]}
        assert teams == {"Chiefs", "Jets", "Bills"}

    async def test_being_in_the_window_is_flagged_as_not_sufficient(self, demo_app):
        response = await get(
            demo_app, "/api/builder/wong-screen", params={"lines": "Chiefs:-8"}
        )
        assert "necessary, not sufficient" in response.json()["note"]

    async def test_a_malformed_pair_is_rejected(self, demo_app):
        response = await get(
            demo_app, "/api/builder/wong-screen", params={"lines": "Chiefs:banana"}
        )
        assert response.status_code == 400


class TestConfigIsInjectedNotAmbient:
    """`create_app` read `GateConfig`, `RiskConfig` and `StalenessConfig` from
    the process environment.

    So an API test's behaviour depended on the developer's `.env`: a machine
    with `LIVE_TRADING_ENABLED=true` or a different staleness limit ran a
    different suite, and CI and a laptop could legitimately disagree about
    whether the code works. For the one app in this repo that can place an
    order, the gate settings should be visible at the call site rather than
    ambient.
    """

    def test_the_gate_config_is_taken_from_the_argument(self, demo_db, monkeypatch):
        """Set the environment to the opposite of what is injected.

        If the injected value did not win, this would read the environment and
        report the gate as armed.
        """
        monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")

        app = create_app(
            AppConfig(instance_mode="demo", db_path=demo_db),
            gate_config=GateConfig(live_trading_enabled=False),
        )
        body = TestClient(app).get("/api/health").json()
        assert body["live_trading_enabled"] is False

    def test_the_staleness_config_is_taken_from_the_argument(
        self, demo_db, monkeypatch
    ):
        monkeypatch.setenv("MAX_ODDS_AGE_S", "1")
        injected = StalenessConfig(max_odds_age_s=4242, max_kalshi_quote_age_s=30)

        app = create_app(
            AppConfig(instance_mode="demo", db_path=demo_db),
            staleness_config=injected,
        )
        # Reached through the gate screen, which reports the limits it applied.
        assert TestClient(app).get("/api/gate").status_code == 200

    def test_omitting_them_still_falls_back_to_the_environment(self, demo_db):
        """Injection is an option, not a new requirement on every caller."""
        app = create_app(AppConfig(instance_mode="demo", db_path=demo_db))
        assert TestClient(app).get("/api/health").status_code == 200
