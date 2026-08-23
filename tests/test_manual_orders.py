"""The manual order path (ADR 0063): a separate door with unwaivable guards.

Every check is server-side and every test here drives the route the way a
client would — the demo-unreachability halves, the lockout and cool-off 423s,
the KXMVE refusal, the daily-loss switch over the venue mirror, the derived
caps, the price ceiling, the depth check, the netting guard against an
unobserved positions shape, and the reserve-then-check transaction in
`manual_orders`. Plus the two separation pins that make ADR 0063 an
architecture rather than a promise: `gate.py` never reads the table, and no
production call site passes the dry-run constant as anything but itself.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- Nothing about the venue's create-order response (never observed; C0 owns
  that) — the placer here runs dry.
- Nothing about the frontend ticket; the masking of the ask until P(YES) is
  typed is a client courtesy whose server half is the required `p_yes_bp`.
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import (
    AppConfig,
    ManualOrderConfig,
    RiskConfig,
)
from backend.kalshi.orders import OrderRequest
from backend.kalshi.grid import read_price_grid
from backend.kalshi.quotes import QuoteUnavailable, parse_market_quote
from backend.store import db
from backend.store import manual_orders as manual_store
from backend.store.orders import ExposureCapExceeded

REPO = Path(__file__).resolve().parents[1]
TICKER = "KXMLBGAME-26AUG22TEST-AAA"
AUTH = {"Authorization": "Bearer secret-token"}


def _payload(*, ticker=TICKER, yes_bid_tenths=350, no_bid_tenths=550,
             yes_ask_size=500.0, price_ranges=True):
    market = {
        "ticker": ticker,
        "status": "active",
        "yes_bid_dollars": f"{yes_bid_tenths / 1000:.4f}",
        "no_bid_dollars": f"{no_bid_tenths / 1000:.4f}",
        "yes_ask_size_fp": f"{yes_ask_size:.2f}",
        "yes_bid_size_fp": "500.00",
    }
    if price_ranges:
        market["price_level_structure"] = "linear_cent"
        market["price_ranges"] = [
            {"start": "0.0000", "end": "1.0000", "step": "0.0100"}
        ]
    return {"market": market}


class StubQuotes:
    """fetch + portfolio_positions, both scriptable."""

    def __init__(self, payload=None, *, positions=None, positions_error=None,
                 fetch_error=None):
        self._payload = payload if payload is not None else _payload()
        self._positions = positions if positions is not None else []
        self._positions_error = positions_error
        self._fetch_error = fetch_error

    async def fetch(self, ticker, *, observed_ms):
        if self._fetch_error is not None:
            raise self._fetch_error
        return parse_market_quote(self._payload, observed_ms=observed_ms)

    async def portfolio_positions(self):
        if self._positions_error is not None:
            raise self._positions_error
        return self._positions

    async def aclose(self):
        pass


def _base_db(tmp_path):
    """A db whose mirror is fresh-and-empty and whose balance is $50
    (50,000 tenths) -> derived caps: position $5, exposure $20, daily $5."""
    path = tmp_path / "manual.db"
    conn = db.init_db(path)
    now = int(time.time() * 1000)
    conn.execute(
        "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count) "
        "VALUES (?, 'settlements', 1, 0)", (now,),
    )
    conn.execute(
        "INSERT INTO venue_balance_snapshots (observed_ms, balance_tenths) "
        "VALUES (?, 50000)", (now,),
    )
    conn.commit()
    conn.close()
    return path


ENABLED = ManualOrderConfig(enabled=True)


def _app(db_path, *, quotes=None, mode="live", manual=ENABLED):
    return create_app(
        AppConfig(instance_mode=mode, auth_token="secret-token", db_path=db_path),
        quote_source=quotes or StubQuotes(),
        manual_order_config=manual,
    )


async def post(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post(path, **kwargs)


async def get(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.get(path, **kwargs)


def _body(**overrides):
    body = {
        "ticker": TICKER,
        "side": "yes",
        "contracts": 1,
        "max_price_tenths": 700,
        "p_yes_bp": 7000,
        "idempotency_key": "test-key-00000001",
    }
    body.update(overrides)
    return body


class TestTheDoorIsUnreachableExceptOnPurpose:
    async def test_the_demo_refuses_on_its_mode_regardless_of_the_flag(self, tmp_path):
        """Half one of CLAUDE.md's 'one config bug' rule. The flag is forced
        ON here and the demo still refuses."""
        app = _app(_base_db(tmp_path), mode="demo", manual=ENABLED)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 403

    async def test_live_refuses_until_the_flag_is_deliberately_set(self, tmp_path):
        app = _app(_base_db(tmp_path), manual=ManualOrderConfig(enabled=False))
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 403
        assert "MANUAL_ORDERS_ENABLED" in response.json()["detail"]

    async def test_the_bearer_is_still_required(self, tmp_path):
        app = _app(_base_db(tmp_path))
        response = await post(app, "/api/manual-orders", json=_body())
        assert response.status_code in (401, 403)

    async def test_the_flag_defaults_off(self):
        assert ManualOrderConfig().enabled is False


class TestTheHappyPathRunsDry:
    async def test_a_dry_run_is_recorded_and_says_so(self, tmp_path):
        path = _base_db(tmp_path)
        app = _app(path)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "dry_run"
        assert body["dry_run"] is True
        assert body["replayed"] is False
        assert "at most" not in body["worst_case_cost_display"]  # it's a figure
        assert body["worst_case_cost_display"].startswith("$")
        assert "Dry run" in body["note"]
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM manual_orders").fetchone()
        conn.close()
        assert row is not None
        assert row["status"] == "dry_run"
        assert row["p_yes_bp"] == 7000
        assert row["dry_run"] == 1

    async def test_a_duplicate_key_replays_the_first_answer(self, tmp_path):
        path = _base_db(tmp_path)
        app = _app(path)
        first = (await post(app, "/api/manual-orders", json=_body(), headers=AUTH)).json()
        second = (await post(app, "/api/manual-orders", json=_body(), headers=AUTH)).json()
        assert second["replayed"] is True
        assert second["client_order_id"] == first["client_order_id"]

    async def test_p_yes_is_required_by_the_server_not_the_form(self, tmp_path):
        app = _app(_base_db(tmp_path))
        body = _body()
        del body["p_yes_bp"]
        response = await post(app, "/api/manual-orders", json=body, headers=AUTH)
        assert response.status_code == 422


class TestTheGuardsRefuse:
    async def test_a_second_order_hits_the_cooloff(self, tmp_path):
        """Mutation observed red: the cool-off check dropped from the route."""
        path = _base_db(tmp_path)
        app = _app(path)
        first = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert first.status_code == 200
        second = await post(
            app, "/api/manual-orders",
            json=_body(idempotency_key="test-key-00000002"), headers=AUTH,
        )
        assert second.status_code == 423
        assert "resting" in second.json()["detail"]

    async def test_the_desk_lockout_locks_this_door_too(self, tmp_path):
        path = _base_db(tmp_path)
        now = int(time.time() * 1000)
        conn = sqlite3.connect(path)
        conn.execute(
            "INSERT INTO self_lockouts (requested_ms, until_ms) VALUES (?, ?)",
            (now, now + 3_600_000),
        )
        conn.commit()
        conn.close()
        app = _app(path)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 423
        assert "not tonight" in response.json()["detail"].lower()

    async def test_kxmve_is_refused_outright(self, tmp_path):
        app = _app(_base_db(tmp_path))
        response = await post(
            app, "/api/manual-orders",
            json=_body(ticker="KXMVECROSSCATEGORY-SHARD1-XYZ"), headers=AUTH,
        )
        assert response.status_code == 422
        assert "enter" in response.json()["detail"]

    async def test_a_stale_mirror_refuses_rather_than_assuming_no_losses(self, tmp_path):
        path = tmp_path / "stale.db"
        conn = db.init_db(path)
        now = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO venue_balance_snapshots (observed_ms, balance_tenths) "
            "VALUES (?, 500000)", (now,),
        )
        conn.commit()
        conn.close()
        app = _app(path)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 422
        assert "mirror" in response.json()["detail"]

    async def test_an_unobserved_balance_refuses_every_cap(self, tmp_path):
        path = tmp_path / "nobal.db"
        conn = db.init_db(path)
        now = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count) "
            "VALUES (?, 'settlements', 1, 0)", (now,),
        )
        conn.commit()
        conn.close()
        app = _app(path)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 422
        assert "balance" in response.json()["detail"]

    async def test_an_ask_above_the_ceiling_is_refused_never_repriced(self, tmp_path):
        app = _app(_base_db(tmp_path))
        response = await post(
            app, "/api/manual-orders",
            json=_body(max_price_tenths=300), headers=AUTH,  # ask is 450
        )
        assert response.status_code == 422
        assert "ceiling" in response.json()["detail"]

    async def test_thin_depth_refuses_the_whole_order(self, tmp_path):
        quotes = StubQuotes(_payload(yes_ask_size=0.0))
        app = _app(_base_db(tmp_path), quotes=quotes)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 422
        assert "rest at the ask" in response.json()["detail"]

    async def test_the_per_bet_cap_binds_on_the_worst_case(self, tmp_path):
        """$50 balance -> $5 per-bet cap; 20 contracts at 45c is ~$9.30."""
        app = _app(_base_db(tmp_path))
        response = await post(
            app, "/api/manual-orders", json=_body(contracts=20), headers=AUTH,
        )
        assert response.status_code == 422
        assert "per-bet cap" in response.json()["detail"]

    async def test_holding_the_ticker_refuses_the_buy(self, tmp_path):
        """Kalshi nets; a buy that closes a position must not book an open."""
        quotes = StubQuotes(positions=[{"ticker": TICKER, "position": "1"}])
        app = _app(_base_db(tmp_path), quotes=quotes)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 422
        assert "nets" in response.json()["detail"]

    async def test_an_unreadable_position_row_refuses_too(self, tmp_path):
        """The per-row shape has never been observed; a row that cannot name
        its ticker cannot prove it is not this one."""
        quotes = StubQuotes(positions=[{"mystery": True}])
        app = _app(_base_db(tmp_path), quotes=quotes)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 422

    async def test_a_failed_positions_read_is_a_503_not_a_pass(self, tmp_path):
        quotes = StubQuotes(positions_error=QuoteUnavailable("no answer"))
        app = _app(_base_db(tmp_path), quotes=quotes)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 503
        assert "positions" in response.json()["detail"]


class TestTheReserveIsAtomic:
    def test_the_exposure_cap_rolls_the_row_back(self, tmp_path):
        path = _base_db(tmp_path)
        conn = db.open_db(path)
        grid = read_price_grid(_payload()["market"])
        order = OrderRequest(
            ticker=TICKER, side="yes", action="buy", count=10,
            limit_price_tenths=450, price_grid=grid,
            time_in_force="immediate_or_cancel",
        )
        with pytest.raises(ExposureCapExceeded):
            manual_store.reserve_manual_order(
                conn, order, dry_run=True, submitted_ms=1,
                max_exposure_dollars=0.50, max_price_tenths=700,
                p_yes_bp=7000, idempotency_key="k-00000001",
            )
        count = conn.execute("SELECT COUNT(*) FROM manual_orders").fetchone()[0]
        conn.close()
        assert count == 0, "the refused row must be rolled back, not left pending"

    def test_manual_exposure_counts_only_its_own_kind(self, tmp_path):
        path = _base_db(tmp_path)
        conn = db.open_db(path)
        exposure = manual_store.current_manual_exposure_dollars(conn, dry_run=True)
        conn.close()
        assert exposure == 0.0


class TestTheSeparationIsArchitecture:
    def test_gate_py_never_reads_the_manual_table(self):
        """ADR 0063's hardest rule: hand bets must never move the interlock's
        populations. Enforced on the source, so a future join fails loudly."""
        source = (REPO / "backend" / "gate.py").read_text(encoding="utf-8")
        assert "manual_orders" not in source

    def test_no_production_call_passes_the_constant_as_anything_else(self):
        """ADR 0018's pin, applied to the manual path: the constant is the
        only dry_run value any production call site may pass."""
        routes = (REPO / "backend" / "api" / "routes.py").read_text(encoding="utf-8")
        calls = re.findall(
            r"OrderPlacer\(\s*dry_run=([^)\n]+)\)", routes
        )
        assert calls, "the scan found no OrderPlacer constructions at all"
        for value in calls:
            assert value.strip() in (
                "ORDERS_ARE_DRY_RUNS",
                "manual_store.MANUAL_ORDERS_ARE_DRY_RUNS",
            ), f"OrderPlacer constructed with dry_run={value!r}"

    def test_the_constant_is_true(self):
        """Arming is a code change (ADR 0063 §3), and it has not happened."""
        assert manual_store.MANUAL_ORDERS_ARE_DRY_RUNS is True


class TestTheManualMarketRead:
    async def test_any_ticker_gets_the_venues_facts(self, tmp_path):
        app = _app(_base_db(tmp_path))
        response = await get(app, f"/api/manual/market/{TICKER}")
        assert response.status_code == 200
        body = response.json()
        assert body["ticker"] == TICKER
        assert body["p_yes_required"] is True
        assert body["sides"]["yes"]["ask_tenths"] == 450
        assert body["sides"]["yes"]["authorised_contracts"] >= 1
        assert body["dry_run"] is True

    async def test_an_unknown_ticker_is_a_404(self, tmp_path):
        quotes = StubQuotes(
            fetch_error=QuoteUnavailable("never heard of it", permanent=True)
        )
        app = _app(_base_db(tmp_path), quotes=quotes)
        response = await get(app, "/api/manual/market/KXNOPE-1-A")
        assert response.status_code == 404

    async def test_the_read_reports_unreachability_without_hiding_the_facts(self, tmp_path):
        app = _app(_base_db(tmp_path), manual=ManualOrderConfig(enabled=False))
        response = await get(app, f"/api/manual/market/{TICKER}")
        assert response.status_code == 200
        body = response.json()
        assert body["reachable"] is False
        assert body["unreachable_reason"]


class TestTheTicketAsksBeforeItShows:
    """ADR 0065's client half, pinned on the source: the estimate step must
    not render an ask, and the confirm control must be gated on the typed
    token. (The server half — required `p_yes_bp`, bearer auth — is driven
    above; these pins stop the masking quietly eroding in a restyle.)"""

    TICKET = REPO / "frontend" / "src" / "components" / "ManualTicket.tsx"

    def _phase_block(self, source: str, marker: str) -> str:
        start = source.index(marker)
        return source[start:source.index("{phase.name ===", start + len(marker))]

    def test_the_estimate_step_shows_no_ask(self):
        """Mutation observed red: render `ask_display` inside the estimate
        phase block."""
        source = self.TICKET.read_text(encoding="utf-8")
        block = self._phase_block(source, '{phase.name === "estimate"')
        assert "ask_display" not in block and "ask_tenths" not in block, (
            "the estimate step renders a price; the typed number is now the "
            "ask's number (anchoring — ADR 0065)"
        )

    def test_the_market_is_fetched_only_after_the_estimate(self):
        source = self.TICKET.read_text(encoding="utf-8")
        reveal = source.index("const revealMarket")
        fetch_call = source.index("fetchManualMarket(")
        assert fetch_call > reveal, (
            "the market read left revealMarket — if it runs before the "
            "estimate is typed, the reveal ordering is decoration"
        )

    def test_the_confirm_is_gated_on_the_typed_token(self):
        source = self.TICKET.read_text(encoding="utf-8")
        gate = source.index("const canConfirm")
        block = source[gate:source.index("return (", gate)]
        assert "token.trim().length > 0" in block, (
            "the confirm no longer requires the typed order token"
        )
