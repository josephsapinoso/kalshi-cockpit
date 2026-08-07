"""API tests, against a seeded database.

No live server and no network: `httpx.ASGITransport` drives the app in-process.

The assertions that matter are the boundary ones. The demo instance must have
no reachable execution path, and the gate must state *which* condition is
unmet rather than just refusing.
"""

from __future__ import annotations

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import AppConfig
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


class TestBoard:
    async def test_returns_surfaced_opportunities(self, demo_app):
        body = (await get(demo_app, "/api/board")).json()
        assert body["counts"]["surfaced"] >= 1
        assert all(r["suggested_contracts"] > 0 for r in body["surfaced"])

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
        row = (await get(demo_app, "/api/board")).json()["surfaced"][0]
        assert isinstance(row["ask_tenths"], int)
        assert row["ask_display"].endswith("c")

    async def test_every_row_carries_its_config_version(self, demo_app):
        row = (await get(demo_app, "/api/board")).json()["surfaced"][0]
        assert row["strategy_config_version"] >= 1


class TestMarketDetail:
    async def test_returns_a_known_market(self, demo_app, demo_db):
        board = (await get(demo_app, "/api/board")).json()
        ticker = board["surfaced"][0]["ticker"]
        body = (await get(demo_app, f"/api/market/{ticker}")).json()
        assert body["ticker"] == ticker
        assert body["reason_text"]

    async def test_an_unknown_market_is_404_not_an_empty_object(self, demo_app):
        assert (await get(demo_app, "/api/market/NOPE")).status_code == 404


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
            json={"recommendation_id": row["id"], "contracts": 20},
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
