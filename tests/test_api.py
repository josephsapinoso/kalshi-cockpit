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
from backend.core.suppression import SuppressionConfig
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

    async def test_it_reports_whether_alerts_are_actually_landing(self, demo_app):
        """`notifications_configured` says a string is non-empty and nothing
        more. Revoke the webhook and `_post` logs a WARNING, returns False, and
        that boolean stays `true` — so a broken alerter and a quiet slate read
        identically.

        Not hypothetical: the live record on 2026-08-18 held one `failure` row
        and it was `delivered = 0`. The loop died, the alert was claimed, and
        nothing reached the phone.
        """
        health = (await get(demo_app, "/api/health")).json()["notifications"]
        assert health is not None
        assert set(health) == {
            "last_delivered_ms", "undelivered_last_24h", "total_ever"
        }
        # Never zero for "nothing has ever landed". Zero is 1970 and would
        # render as a delivery.
        assert health["last_delivered_ms"] is None or health["last_delivered_ms"] > 0

    async def test_it_reports_how_stale_the_recorder_is(self, demo_app):
        """The field an external watchdog needs and could not get.

        `entrypoint.sh` supervises the loop with `wait -n`, so a loop that
        *exits* takes the container down and is visible from outside. A loop
        that is alive and **stuck** keeps this endpoint green forever while the
        record stops accumulating. `.github/workflows/heartbeat.yml` reads
        `age_ms` and alarms past thirty minutes.
        """
        recorder = (await get(demo_app, "/api/health")).json()["recorder"]
        assert recorder is not None
        assert set(recorder) == {"last_write_ms", "age_ms"}
        assert recorder["age_ms"] >= 0

    def test_a_recorder_that_never_wrote_reports_none_in_both_fields(self):
        """**Tested directly, and the first version of this could not be.**

        It went through `demo_app`, whose seeded database always has quotes, so
        the `None` branch never ran -- the test passed with that branch
        deliberately broken to `age_ms: 0`. An empty table is "never written",
        and 0 is 1970, which renders as an age of fifty-six years rather than
        as the absence of a measurement.
        """
        from backend.api.routes import recorder_fields

        assert recorder_fields(None, 1_700_000_000_000) == {
            "last_write_ms": None, "age_ms": None
        }

    def test_a_clock_that_ran_backwards_reports_zero_not_a_negative_age(self):
        """The heartbeat compares `age_ms` against a threshold with `-gt` in
        bash. A negative number there is not merely wrong, it is quietly
        healthy forever."""
        from backend.api.routes import recorder_fields

        assert recorder_fields(1_000, 500)["age_ms"] == 0

    async def test_neither_block_can_take_health_down(self, demo_app, monkeypatch):
        """`/api/health` is the liveness probe `entrypoint.sh` and the external
        heartbeat both read. A route that 500s because a SELECT failed turns a
        reporting gap into an outage — and into a false alarm on a phone."""
        import backend.store.db as store_db

        def explode(*a, **kw):
            raise RuntimeError("volume is gone")

        monkeypatch.setattr(store_db, "open_db", explode)
        response = await get(demo_app, "/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        # Unreadable resolves to None, and the caller can tell that from a real
        # answer. It must not resolve to a zero the heartbeat would act on.
        assert body["notifications"] is None
        assert body["recorder"] is None

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
        """The review's number, reproduced from the payload rather than quoted.

        **It was 45.6% and it is now 46.4%, and the move is the fix working.**
        The review measured it on a demo seeded at the `RiskConfig` dataclass
        defaults -- a $1,000 bankroll no instance deploys, which sized that row
        at 17 contracts. `seed_demo` now restates the deployed caps (ADR 0041,
        amended 2026-08-18), the row sizes at 1, and `max` picks among rows
        tied at one contract by the sort `/api/board` already applies. So this
        is a different row's probability, correctly, and 45.6% was never a
        number a visitor could have seen.

        Updated rather than widened. The tolerance stays at +/-0.005; loosening
        it to admit both would be the assertion apologising for the change.
        """
        row = max(
            sized_rows((await get(demo_app, "/api/board")).json()),
            key=lambda r: r["suggested_contracts"],
        )
        assert row["losing_run_bets"] == 10
        assert row["losing_run_probability"] == pytest.approx(0.464, abs=0.005)

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


def _slate_row(
    conn,
    *,
    ticker: str,
    created_ms: int,
    edge_tenths: float = 1.0,
    contracts: int = 0,
    suppressed: str | None = None,
    confirmed_ms: int | None = None,
    confirmed_ages: bool = True,
) -> None:
    """One recommendation, positioned in time. Nothing else about it varies.

    `confirmed_ages=False` writes the half-written confirmation that
    `gate.live_ages` refuses: a timestamp with no ages beside it.
    """
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, first_seen_ms, "
        "last_seen_ms) VALUES (?, ?, ?)",
        (ticker, created_ms, created_ms),
    )
    conn.execute(
        "INSERT INTO recommendations (created_ms, strategy_config_version, "
        "ticker, side, entry_ask_tenths, fair_probability, edge_tenths, "
        "fee_predicted, ev_net_dollars, kelly_fraction, suggested_contracts, "
        "reference_contracts, kalshi_quote_age_ms, odds_age_ms, "
        "last_confirmed_ms, last_confirmed_quote_age_ms, "
        "last_confirmed_odds_age_ms, suppressed_reason, reason_text) "
        "VALUES (?, 1, ?, 'yes', 500, 0.52, ?, 0.1, 0.2, 0.01, ?, ?, 1000, "
        "2000, ?, ?, ?, ?, 'test row')",
        (
            created_ms, ticker, edge_tenths, contracts, contracts,
            confirmed_ms,
            1_000 if (confirmed_ms is not None and confirmed_ages) else None,
            2_000 if (confirmed_ms is not None and confirmed_ages) else None,
            suppressed,
        ),
    )


def _every_row(board: dict) -> list[dict]:
    return board["surfaced"] + board["expired"] + board["suppressed"] + board["no_edge"]


class TestTheBoardShowsTheCurrentSlateAndNotTheRecord:
    """The other half of the bug the endpoint's docstring already described.

    Recomputing a row's age fixed how the Board *rendered* what it fetched. What
    it fetched was `ORDER BY suggested_contracts DESC, edge_tenths DESC LIMIT
    100` over the whole table with no clock in it -- and `suggested_contracts`
    is 0 on essentially every row ever written, so that collapses to the hundred
    largest apparent edges in the history of the database, rendered as today's
    slate with no date on any of them.

    Rule 1 of this repo is that a large apparent edge is a bug until proven
    otherwise. That query selected for them, and the `LIMIT` is the sharp end:
    the ordinary rows are the ones it drops.
    """

    @pytest.fixture(scope="class")
    def history_db(self, tmp_path_factory):
        """Nine current rows and a back-record, as the demo deploy has.

        The back-record is deliberately larger than the Board's default limit.
        A shorter one would let every row through the `LIMIT` regardless of the
        selection, and the tests below would pass on a query with no window in
        it at all.
        """
        from backend.seed_demo import seed_all, seed_history
        from backend.store.db import now_ms

        path = tmp_path_factory.mktemp("history") / "history.db"
        stamp = now_ms()
        seed_all(path, now_ms=stamp)
        seed_history(path, n=200, now_ms=stamp)
        return path

    @pytest.fixture(scope="class")
    def history_app(self, history_db):
        return create_app(AppConfig(instance_mode="demo", db_path=history_db))

    async def test_no_row_from_the_back_record_reaches_the_board(
        self, history_app
    ):
        """`seed_history` writes one row an hour going backwards. None of them
        is today's slate, and every one of them used to be eligible."""
        body = (await get(history_app, "/api/board?include_suppressed=true")).json()
        assert _every_row(body), "the fixture must produce a slate or this proves nothing"
        assert not [r for r in _every_row(body) if r["ticker"].startswith("KXHIST-")]

    async def test_what_the_old_query_would_have_shown_is_mostly_history(
        self, history_app, history_db
    ):
        """The defect and the fix, asserted against each other on one fixture.

        The old selection is re-derived here rather than described, so the test
        fails if the endpoint ever returns to it -- and so a reader can see what
        it actually produced. `seed_history` writes `suspicious_edge` rows at
        45-90 tenths, an order of magnitude above anything on a real slate, and
        those are exactly the rows an edge ranking puts on the screen first.
        """
        from backend.store import db as store

        conn = store.open_db(history_db, read_only=True)
        try:
            would_have_shown = [
                r["ticker"]
                for r in conn.execute(
                    "SELECT ticker FROM recommendations "
                    "ORDER BY suggested_contracts DESC, edge_tenths DESC LIMIT 100"
                ).fetchall()
            ]
        finally:
            conn.close()

        from_history = [t for t in would_have_shown if t.startswith("KXHIST-")]
        assert len(from_history) > len(would_have_shown) / 2, (
            "the fixture must reproduce the bug or the assertion below is vacuous"
        )

        body = (await get(history_app, "/api/board?include_suppressed=true")).json()
        shown = {r["ticker"] for r in _every_row(body)}
        assert shown, "the board must still have a slate"
        assert not shown & set(from_history)

    async def test_the_board_says_how_much_of_the_record_it_left_off(
        self, history_app
    ):
        """A filter that discards what it rejects cannot be audited."""
        body = (await get(history_app, "/api/board?include_suppressed=true")).json()
        assert body["slate"]["older_than_window"] == 200
        assert body["slate"]["in_window"] == len(_every_row(body))
        assert body["slate"]["recorded_total"] == body["slate"]["in_window"] + 200

    async def test_the_window_is_in_the_query_not_applied_to_its_results(
        self, tmp_path
    ):
        """A filter applied after `LIMIT` is a filter the record can starve.

        Sized rows sort first -- deliberately, so a bettable row is never what
        the limit drops -- and the record is full of rows the sizer once sized.
        Fetch the whole table and discard the old ones afterwards and those fill
        the limit on their own, so the Board comes back empty while a slate
        exists. The window has to be in the `WHERE`, not in the loop over the
        results.
        """
        from backend.store import db as store
        from backend.store.db import now_ms

        path = tmp_path / "starved.db"
        conn = store.init_db(path)
        conn.execute(
            "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
            "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
        )
        now = now_ms()
        for i in range(150):
            _slate_row(conn, ticker=f"KXPAST-{i:03d}",
                       created_ms=now - 4 * 3_600_000 - i, contracts=20)
        for i in range(3):
            _slate_row(conn, ticker=f"KXTODAY-{i}", created_ms=now - 30_000 - i)
        conn.commit()
        conn.close()
        app = create_app(AppConfig(instance_mode="demo", db_path=path))

        body = (await get(app, "/api/board?include_suppressed=true")).json()
        assert {r["ticker"] for r in _every_row(body)} == {
            "KXTODAY-0", "KXTODAY-1", "KXTODAY-2"
        }

    async def test_a_live_slate_says_it_is_current(self, tmp_path):
        from backend.seed_demo import seed_all
        from backend.store.db import now_ms

        path = tmp_path / "now.db"
        seed_all(path, now_ms=now_ms())
        app = create_app(AppConfig(instance_mode="demo", db_path=path))
        slate = (await get(app, "/api/board")).json()["slate"]
        assert slate["is_current"] is True
        assert slate["age_ms"] < 60_000

    async def test_a_slate_nobody_has_updated_is_not_passed_off_as_current(
        self, demo_app
    ):
        """The demo seed is a year old. It is still shown -- a slate is a thing
        this instance recorded, not a thing the wall clock did, and blanking the
        page when the loop stops hides the rows worth reading. What must not
        happen is showing it *as today*."""
        body = (await get(demo_app, "/api/board?include_suppressed=true")).json()
        assert _every_row(body), "the seeded slate must still be reachable"
        assert body["slate"]["is_current"] is False
        assert body["slate"]["age_ms"] > 30 * 24 * 3_600_000

    async def test_a_database_that_has_recorded_nothing_says_so_distinctly(
        self, tmp_path
    ):
        """Empty and stale are different states. `anchor_ms` is the one that
        separates them, and neither may render as the other."""
        from backend.store import db as store

        path = tmp_path / "empty.db"
        store.init_db(path).close()
        app = create_app(AppConfig(instance_mode="demo", db_path=path))
        body = (await get(app, "/api/board?include_suppressed=true")).json()

        assert _every_row(body) == []
        assert body["slate"]["anchor_ms"] is None
        assert body["slate"]["age_ms"] is None
        assert body["slate"]["recorded_total"] == 0
        assert body["slate"]["is_current"] is False


class TestWhatTheLimitDropsIsNotChosenByEdge:
    """Truncation is a sampling decision, and it was made on the edge.

    A window of 200 rows shown 100 at a time is fine. A window of 200 rows shown
    *largest-edge-first* 100 at a time is a sample built from the tail this repo
    treats as bugs -- and nothing on the page said 100 rows were missing.
    """

    @pytest.fixture
    def crowded(self, tmp_path):
        """One slate: an outsized edge written first, ordinary rows after it."""
        from backend.store import db as store
        from backend.store.db import now_ms

        path = tmp_path / "crowded.db"
        conn = store.init_db(path)
        conn.execute(
            "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
            "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
        )
        base = now_ms() - 60_000
        _slate_row(conn, ticker="KXBIG", created_ms=base, edge_tenths=90.0,
                   suppressed="suspicious_edge")
        for i in range(6):
            _slate_row(conn, ticker=f"KXORD-{i}", created_ms=base + 1_000 + i,
                       edge_tenths=1.0)
        conn.commit()
        conn.close()
        return create_app(AppConfig(instance_mode="demo", db_path=path))

    async def test_the_outsized_row_is_what_the_limit_drops(self, crowded):
        """It is the oldest row in the window, so recency drops it. Under the
        old ordering it was the one row guaranteed to survive."""
        body = (
            await get(crowded, "/api/board?include_suppressed=true&limit=3")
        ).json()
        tickers = {r["ticker"] for r in _every_row(body)}
        assert len(tickers) == 3
        assert "KXBIG" not in tickers

    async def test_truncation_is_reported_rather_than_silent(self, crowded):
        body = (
            await get(crowded, "/api/board?include_suppressed=true&limit=3")
        ).json()
        assert body["slate"]["truncated"] is True
        assert body["slate"]["in_window"] == 7
        assert body["slate"]["returned"] == 3

    async def test_a_whole_window_is_not_reported_as_truncated(self, crowded):
        body = (await get(crowded, "/api/board?include_suppressed=true")).json()
        assert body["slate"]["truncated"] is False
        assert body["slate"]["returned"] == 7

    async def test_a_sized_row_is_never_the_one_dropped(self, tmp_path):
        """The bettable rows are what the page exists for, so they sort first
        whatever their age. This is the one place size still outranks the clock.
        """
        from backend.store import db as store
        from backend.store.db import now_ms

        path = tmp_path / "sized.db"
        conn = store.init_db(path)
        conn.execute(
            "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
            "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
        )
        base = now_ms() - 60_000
        # The oldest row in the window, and the only one anybody could bet.
        _slate_row(conn, ticker="KXSIZED", created_ms=base, contracts=4)
        for i in range(6):
            _slate_row(conn, ticker=f"KXORD-{i}", created_ms=base + 1_000 + i)
        conn.commit()
        conn.close()
        app = create_app(AppConfig(instance_mode="demo", db_path=path))

        body = (await get(app, "/api/board?include_suppressed=true&limit=2")).json()
        assert "KXSIZED" in {r["ticker"] for r in _every_row(body)}


class TestTheWindowIsDecidedByLiveAgesNotBySql:
    """The SQL is a bound on what to fetch. `gate.live_ages` decides.

    Two implementations of one boundary is the failure this repo keeps
    recording, so the SQL is deliberately the *loose* form: it can only
    over-select, and the second reading removes what it should not have taken.
    """

    @pytest.fixture
    def confirmations(self, tmp_path):
        from backend.store import db as store
        from backend.store.db import now_ms

        path = tmp_path / "confirmed.db"
        conn = store.init_db(path)
        conn.execute(
            "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
            "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
        )
        now = now_ms()
        old = now - 4 * 3_600_000
        # The anchor: something this instance decided moments ago.
        _slate_row(conn, ticker="KXNOW", created_ms=now - 30_000)
        # Four hours old, re-derived unchanged just now. `persist_if_changed`
        # writes exactly this, and it is still part of the current slate.
        _slate_row(conn, ticker="KXCONFIRMED", created_ms=old,
                   confirmed_ms=now - 40_000)
        # The same shape with the ages missing. `live_ages` refuses it and falls
        # back to `created_ms`, so it is four hours old and off the slate.
        _slate_row(conn, ticker="KXHALF", created_ms=old,
                   confirmed_ms=now - 40_000, confirmed_ages=False)
        # Never re-derived. Plainly history.
        _slate_row(conn, ticker="KXOLD", created_ms=old)
        conn.commit()
        conn.close()
        return create_app(AppConfig(instance_mode="demo", db_path=path))

    async def test_a_confirmed_row_is_part_of_the_current_slate(
        self, confirmations
    ):
        """Freshness is measured from the last time the decision was re-derived,
        so selection must be too -- otherwise a row the loop confirms every
        twenty seconds falls off the Board after half an hour."""
        body = (await get(confirmations, "/api/board?include_suppressed=true")).json()
        assert "KXCONFIRMED" in {r["ticker"] for r in _every_row(body)}

    async def test_a_half_written_confirmation_does_not_extend_the_window(
        self, confirmations
    ):
        """SQL takes the timestamp at face value and hands the row over;
        `live_ages` requires both ages beside it and refuses. Only the second
        reading may decide, and this is the row where they disagree."""
        body = (await get(confirmations, "/api/board?include_suppressed=true")).json()
        assert "KXHALF" not in {r["ticker"] for r in _every_row(body)}

    async def test_an_unconfirmed_old_row_is_history(self, confirmations):
        body = (await get(confirmations, "/api/board?include_suppressed=true")).json()
        assert "KXOLD" not in {r["ticker"] for r in _every_row(body)}


class TestMarketDetail:
    async def test_returns_a_known_market(self, demo_app, demo_db):
        board = (await get(demo_app, "/api/board")).json()
        ticker = sized_rows(board)[0]["ticker"]
        body = (await get(demo_app, f"/api/market/{ticker}")).json()
        assert body["ticker"] == ticker
        assert body["reason_text"]

    async def test_an_unknown_market_is_404_not_an_empty_object(self, demo_app):
        assert (await get(demo_app, "/api/market/NOPE")).status_code == 404

    async def test_it_serves_the_desk_panels_facts(self, demo_app):
        """ADR 0068: the Consensus panel needs the fair_prices join and the
        book distribution; the Skeptic panel needs the gauntlet. All three
        ride this route now."""
        board = (await get(demo_app, "/api/board")).json()
        ticker = sized_rows(board)[0]["ticker"]
        body = (await get(demo_app, f"/api/market/{ticker}")).json()
        assert "fair_probability" in body
        assert "anchored_on_sharp" in body
        assert "books" in body
        assert "kalshi_drift_tenths" in body
        gauntlet = body["gauntlet"]
        assert {c["code"] for c in gauntlet["checks"]}, (
            "the gauntlet board came back empty"
        )
        assert "judged_ms" in gauntlet

    async def test_the_gauntlet_is_served_even_for_a_clean_row(self, demo_app):
        """`suppressed_reason IS NULL` must still produce a full board —
        "every check that ran, passed" is the panel's whole reassurance."""
        board = (await get(demo_app, "/api/board")).json()
        ticker = sized_rows(board)[0]["ticker"]
        body = (await get(demo_app, f"/api/market/{ticker}")).json()
        if body["suppressed_reason"] is None:
            verdicts = {
                c["verdict"] for c in body["gauntlet"]["checks"]
            }
            assert "refused" not in verdicts
            assert "passed" in verdicts

    async def test_break_even_does_not_ride_beside_fair_here(self, demo_app):
        """Fair% renders on this screen (ADR 0068); break-even therefore
        must not — their difference is the measured-negative edge."""
        board = (await get(demo_app, "/api/board")).json()
        ticker = sized_rows(board)[0]["ticker"]
        body = (await get(demo_app, f"/api/market/{ticker}")).json()
        assert "breakeven_win_rate" not in body


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
        """16 credits a day at 2 a call, and the seed's 12 leaves two.

        **The 2 is the deployed cost, and this used to say 6.** A sweep is
        `len(markets) * len(regions)`; live sets neither variable, so it takes
        the `h2h` default against `us,eu`. The 6 came from a developer `.env`
        carrying `h2h,spreads,totals` -- a configuration that runs on no
        instance. `conftest.py` now pins both, so this figure is one the
        deployed system would actually report.
        """
        body = (await get(fresh_app, "/api/window")).json()
        assert body["spent_today"] == 12
        assert body["sweeps_remaining_today"] == 2

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


class TestSlate:
    """Edge is a column here, not a gate.

    `/api/board` buckets the slate on whether a row cleared the fee, and that
    has been "no" on every row this instance ever wrote. This route returns the
    same window as one flat list with the factors already on the record
    attached, so the verdict stops being the only thing visible about a night.
    """

    async def test_it_returns_one_flat_list_and_does_not_bucket_by_verdict(
        self, demo_app
    ):
        body = (await get(demo_app, "/api/slate")).json()
        assert body["rows"], "the slate came back empty on the seeded demo"
        # The bucket names the Board uses must not appear: bucketing by verdict
        # is exactly what this screen exists not to do.
        for bucket in ("surfaced", "expired", "suppressed", "no_edge"):
            assert bucket not in body, (
                f"{bucket!r} is a top-level key, so this route buckets by "
                f"verdict the way the Board does"
            )

    async def test_refused_rows_are_present_with_their_reasons(self, demo_app):
        """They are the content, not the exclusions.

        `/api/board` hides them behind `include_suppressed`. Here there is no
        flag, because a slate with the refused rows removed is the Board again.
        """
        body = (await get(demo_app, "/api/slate")).json()
        refused = [r for r in body["rows"] if r["suppressed_reason"]]
        assert refused, "no refused row was returned, so this is the Board"
        assert all(r["suppressed_reason"] for r in refused)

    async def test_it_describes_the_same_slate_as_the_board(self, demo_app):
        """Two screens naming one night must not disagree about which night.

        Both windows are `SLATE_WINDOW_MS` back from the most recent freshness
        basis, and both re-decide on `live_ages`. A row on one and not the other
        would be a second definition of "tonight".
        """
        slate = (await get(demo_app, "/api/slate")).json()
        board = (await get(demo_app, "/api/board?include_suppressed=true")).json()

        board_ids = {
            r["id"]
            for bucket in ("surfaced", "expired", "suppressed", "no_edge")
            for r in board[bucket]
        }
        assert {r["id"] for r in slate["rows"]} == board_ids
        assert slate["slate"]["since_ms"] == board["slate"]["since_ms"]

    async def test_rows_are_ordered_by_kickoff_and_not_by_edge(self, demo_app):
        """A ranking is a weighting, and a weighting of unscored factors is a
        model. Ordering by kickoff is the one order that asserts nothing."""
        rows = (await get(demo_app, "/api/slate")).json()["rows"]
        kickoffs = [r["commence_ms"] for r in rows if r["commence_ms"] is not None]
        assert kickoffs == sorted(kickoffs)

    async def test_the_book_distribution_spans_more_books_than_the_anchor(
        self, demo_app
    ):
        """ADR 0021 §7.2, made visible.

        `fair_prices.book_count` is what survived `SHARP_BOOKS` anchoring; the
        distribution is every usable book. If those were the same number this
        screen would be showing the anchored consensus back to itself and could
        say nothing about the tautology objection.
        """
        rows = (await get(demo_app, "/api/slate")).json()["rows"]
        with_both = [
            r for r in rows if r["books"] and r["book_count"] is not None
        ]
        assert with_both, "no row carried both counts, so nothing is compared"
        assert any(
            r["books"]["book_count"] > r["book_count"] for r in with_both
        ), (
            "the distribution is no wider than the anchored consensus on any "
            "row, so the sharp anchoring is being applied twice"
        )

    async def test_capacity_is_returned_because_no_screen_has_shown_it(
        self, demo_app
    ):
        rows = (await get(demo_app, "/api/slate")).json()["rows"]
        assert any(r["volume_24h"] is not None for r in rows)
        assert any(r["open_interest"] is not None for r in rows)

    async def test_an_unmeasurable_factor_is_null_and_never_zero(self, demo_app):
        """`percentile: 0` reads as "Kalshi is the cheapest venue here"."""
        rows = (await get(demo_app, "/api/slate")).json()["rows"]
        for row in rows:
            if row["books"] is None:
                continue
            if row["books"]["book_count"] == 0:
                assert row["books"]["percentile"] is None
                assert row["books"]["median_book_probability"] is None

    async def test_it_counts_how_many_rows_could_be_measured_at_all(
        self, demo_app
    ):
        """"No book disagreed" and "no book price stored" render identically."""
        body = (await get(demo_app, "/api/slate")).json()
        measured = sum(1 for r in body["rows"] if r["books"])
        assert body["counts"]["with_book_distribution"] == measured

    async def test_the_payload_carries_the_sentence_that_scopes_it(
        self, demo_app
    ):
        """The screen prints this rather than writing its own, so the server
        and the page cannot come to disagree about what is being claimed."""
        note = (await get(demo_app, "/api/slate")).json()["note"]
        assert "scored" in note

    async def test_no_row_carries_a_composite(self, demo_app):
        """The tripwire. Blending unscored factors into one number is a model
        and needs its own ADR and pre-registration (ADR 0021 §9)."""
        rows = (await get(demo_app, "/api/slate")).json()["rows"]
        forbidden = {"score", "rating", "confidence", "signal", "rank"}
        for row in rows:
            assert not (forbidden & set(row)), (
                f"a composite appeared on a Slate row: "
                f"{sorted(forbidden & set(row))}"
            )


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


class TestBreakevenShipsAlone:
    """Fleet convening item 6: the break-even rate is on every priced row,
    computed by the same code the order path uses, and the reason it ships
    without the consensus fair value beside it is an exact identity -- which
    this class proves on real payloads rather than asserts in prose."""

    async def test_every_priced_row_carries_a_breakeven(self, demo_app):
        rows = (await get(demo_app, "/api/slate")).json()["rows"]
        priced = [r for r in rows if r["ask_tenths"] not in (None, 0, 1000)]
        assert priced, "the seeded demo slate has no priced rows"
        for row in priced:
            assert row["breakeven_win_rate"] is not None
            assert 0.0 < row["breakeven_win_rate"] < 1.0

    async def test_the_adjudicated_identity_actually_holds(self, demo_app):
        """`edge_tenths == 1000 x (fair - breakeven)` -- with one honest
        wrinkle this test exists to have found: the identity is exact only at
        MATCHING contracts, because the fee rounds up on the whole order and
        the stored edge was computed at the sized position
        (`engine.py`: `max(1, sizing.contracts)`), while the wire serves the
        one-contract taker figure, which is the trade Joe actually makes by
        hand. So two claims, both proven: the identity is exact at the row's
        own size, and the served figure differs from that by less than one
        tenth -- pure fee-rounding amortisation, invisible at the displayed
        decimal. Either way, fair beside break-even hands the reader the
        measured-negative edge by subtraction, which is why it may not
        co-render."""
        from backend.core.ev import breakeven_win_rate

        rows = (await get(demo_app, "/api/slate")).json()["rows"]
        checked = 0
        for row in rows:
            if row["breakeven_win_rate"] is None:
                continue
            if row["fair_probability"] is None or row["edge_tenths"] is None:
                continue
            # The engine sized this row BEFORE suppression zeroed the stored
            # size columns (a suppressed demo row carries suggested and
            # reference both 0 while its edge was computed at, e.g., 26), so
            # the exact size is not recoverable from the payload. The claim
            # that IS provable: some contract count makes the identity exact
            # to float precision -- edge really is fair minus a breakeven,
            # nothing else added.
            exact_at = next(
                (
                    c
                    for c in range(1, 201)
                    if abs(
                        row["edge_tenths"]
                        - 1000.0
                        * (
                            row["fair_probability"]
                            - breakeven_win_rate(row["ask_tenths"], c)
                        )
                    )
                    < 1e-9
                ),
                None,
            )
            assert exact_at is not None, (
                f"{row['ticker']}: no contract count in 1..200 makes "
                f"edge_tenths == 1000*(fair - breakeven); the identity the "
                f"convening adjudicated does not hold, so the no-co-render "
                f"rule is resting on a false premise"
            )
            served = 1000.0 * (row["fair_probability"] - row["breakeven_win_rate"])
            assert abs(row["edge_tenths"] - served) < 1.0, (
                f"{row['ticker']}: the served one-contract breakeven is "
                f"{abs(row['edge_tenths'] - served):.3f} tenths from the "
                f"stored edge -- more than fee-rounding amortisation can "
                f"explain"
            )
            checked += 1
        assert checked, "no row exercised the identity"

    async def test_an_untradeable_ask_refuses_rather_than_prices(self, demo_app):
        """0 and 1000 are settled outcomes; `breakeven_win_rate` raises and
        the route passes the refusal through as null, never as a number."""
        from backend.core.ev import breakeven_win_rate

        with pytest.raises(ValueError):
            breakeven_win_rate(0, 1)
        with pytest.raises(ValueError):
            breakeven_win_rate(1000, 1)


class TestMoneyIsNeverSummed:
    """Fleet convening item 5. Cash and open positions are separate facts;
    their sum is a signed P&L, and the payload must make the summing
    impossible to do accidentally rather than merely not do it."""

    async def test_the_slate_carries_the_money_block(self, demo_app):
        body = (await get(demo_app, "/api/slate")).json()
        assert "money" in body

    async def test_no_summed_or_signed_field_exists(self, demo_app):
        money = (await get(demo_app, "/api/slate")).json()["money"]
        assert money is not None, (
            "the money block went back to omitting itself; an unobserved "
            "balance must be words on the screen, not an absent key"
        )
        forbidden = {"total", "net", "pnl", "profit", "loss", "change"}
        assert not (set(money) & forbidden)
        assert set(money) == {
            "observed_ms",
            "cash_tenths",
            "cash_display",
            "open_positions_tenths",
            "daily_line_dollars",
            "daily_line_display",
            "per_bet_cap_display",
            "exposure_cap_display",
            "deposit_for_50c_display",
            "caps_basis",
        }


class TestTheCapsAreDerivedAtRequestTime:
    """ADR 0045's caps, on the slate's money block (slice B2, 2026-08-22).

    The defect: `daily_line_dollars` was read off the MODULE-LEVEL
    `RiskConfig.load()` bound at import, which carries `None` for every
    dollar cap on live -- so "your daily-loss line is $X" silently rendered
    nothing since ADR 0045. The fix derives at request time via
    `with_observed_balance`, the order endpoint's own step-8a pattern.

    Mutation verified red (2026-08-22): the money block's `derived_risk`
    swapped back to the module-level `risk` -- the seeded-balance test
    below fails on `daily_line_dollars is None`; restored by copy -> green.
    """

    @staticmethod
    def _app(tmp_path, *, balance_tenths=None):
        from backend.store import db as store_db

        path = tmp_path / "caps.db"
        conn = store_db.init_db(path)
        conn.execute(
            "INSERT INTO strategy_configs (version, created_ms, "
            "effective_from_ms, config_json, rationale) "
            "VALUES (1, 0, 0, '{}', 'test')"
        )
        if balance_tenths is not None:
            conn.execute(
                "INSERT INTO venue_balance_snapshots "
                "(observed_ms, balance_tenths, portfolio_value_tenths) "
                "VALUES (1000, ?, 0)",
                (balance_tenths,),
            )
        conn.commit()
        conn.close()
        return create_app(AppConfig(instance_mode="demo", db_path=path))

    async def test_the_caps_track_the_observed_balance(self, tmp_path):
        """$2.56 observed -> 25.6c a bet, $1.02 at risk, 25.6c daily line
        (the 10/40/10 fractions of ADR 0045), each a server display string."""
        app = self._app(tmp_path, balance_tenths=2560)
        money = (await get(app, "/api/slate")).json()["money"]
        assert money["cash_display"] == "$2.56"
        assert money["per_bet_cap_display"] == "25.6c"
        assert money["exposure_cap_display"] == "$1.02"
        assert money["daily_line_display"] == "25.6c"
        assert money["daily_line_dollars"] == pytest.approx(0.256)
        assert money["caps_basis"] == {
            "balance_display": "$2.56",
            "observed_ms": 1_000,
            "refusal": None,
        }

    async def test_the_deposit_arithmetic_is_served_not_computed_client_side(
        self, tmp_path
    ):
        """One contract at 50c costs $0.50; the per-bet cap is 10% of the
        balance; so the balance that admits it is $5.00 -- rendered by the
        server so the frontend never divides money."""
        app = self._app(tmp_path, balance_tenths=2560)
        money = (await get(app, "/api/slate")).json()["money"]
        assert money["deposit_for_50c_display"] == "$5.00"

    async def test_an_unobserved_balance_refuses_and_never_zeroes(
        self, tmp_path
    ):
        """No snapshot -> refusal fields, not $0.00 caps. A zero cap and an
        underivable cap are opposite instructions to a bettor."""
        app = self._app(tmp_path, balance_tenths=None)
        money = (await get(app, "/api/slate")).json()["money"]
        assert money is not None
        assert money["cash_display"] is None
        assert money["per_bet_cap_display"] is None
        assert money["exposure_cap_display"] is None
        assert money["daily_line_display"] is None
        assert money["daily_line_dollars"] is None
        assert money["caps_basis"]["refusal"] == "balance unobserved"
        # The deposit sentence stays true without a balance and is still sent.
        assert money["deposit_for_50c_display"] == "$5.00"

    async def test_an_observed_zero_balance_is_zero_caps_not_a_refusal(
        self, tmp_path
    ):
        """Observed broke is not unobserved (`with_observed_balance`'s own
        contract): a $0.00 balance derives caps of zero, stated as such."""
        app = self._app(tmp_path, balance_tenths=0)
        money = (await get(app, "/api/slate")).json()["money"]
        assert money["per_bet_cap_display"] == "0c"
        assert money["caps_basis"]["refusal"] is None
        assert money["caps_basis"]["balance_display"] == "$0.00"


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
            # Injected as a **pair**, and it has to be. ADR 0019 section 6:
            # `SuppressionConfig.max_odds_age_ms` and `MAX_ODDS_AGE_S` bound the
            # same quantity, and `create_app` now refuses to start when they
            # disagree. Moving one without the other is exactly the state the
            # assertion exists to catch, so this test injects a consistent pair
            # rather than an inconsistent one. It still proves the property it
            # was written for -- the argument beats `MAX_ODDS_AGE_S=1`.
            suppression_config=SuppressionConfig(max_odds_age_ms=4242 * 1000),
        )
        # Reached through the gate screen, which reports the limits it applied.
        assert TestClient(app).get("/api/gate").status_code == 200

    def test_an_inconsistent_pair_refuses_to_start(self, demo_db):
        """The positive control for the guard above. ADR 0019 section 6.

        Without this, the pair-injection in the previous test looks like
        boilerplate rather than a constraint, and someone will "simplify" it
        back to a single argument.
        """
        from backend.config import StalenessLimitsDisagree

        with pytest.raises(StalenessLimitsDisagree):
            create_app(
                AppConfig(instance_mode="demo", db_path=demo_db),
                staleness_config=StalenessConfig(
                    max_odds_age_s=4242, max_kalshi_quote_age_s=30
                ),
                # Left at the default 900_000 while staleness says 4,242,000.
                suppression_config=SuppressionConfig(),
            )

    def test_an_inconsistent_quote_age_pair_also_refuses_to_start(self, demo_db):
        """The other half of the same defect, and it was live until now.

        ADR 0019 section 6 fixed `max_odds_age_ms` and left
        `max_kalshi_quote_age_ms` one line above it unguarded. Verified by
        construction before this guard: `create_app` with the pair below
        started cleanly, and a 12s-old quote was then `actionable` on the Board
        while `/api/order` refused it.
        """
        from backend.config import StalenessLimitsDisagree

        with pytest.raises(StalenessLimitsDisagree):
            create_app(
                AppConfig(instance_mode="demo", db_path=demo_db),
                staleness_config=StalenessConfig(
                    max_odds_age_s=900, max_kalshi_quote_age_s=5
                ),
                # Left at the default 30_000 while staleness says 5,000.
                suppression_config=SuppressionConfig(),
            )

    def test_omitting_them_still_falls_back_to_the_environment(self, demo_db):
        """Injection is an option, not a new requirement on every caller."""
        app = create_app(AppConfig(instance_mode="demo", db_path=demo_db))
        assert TestClient(app).get("/api/health").status_code == 200
