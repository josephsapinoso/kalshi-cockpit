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

import ast
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
from backend.core.fees import calculate_fee, combo_taker_fee
from backend.kalshi.orders import OrderRequest
from backend.kalshi.grid import read_price_grid
from backend.kalshi.quotes import QuoteUnavailable, parse_market_quote
from backend.store import db
from backend.store import manual_orders as manual_store
from backend.store.orders import ExposureCapExceeded

REPO = Path(__file__).resolve().parents[1]
TICKER = "KXMLBGAME-26AUG22TEST-AAA"
COMBO_TICKER = "KXMVECROSSCATEGORY0-SHARD1-S2026TEST-ABC"
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


def _base_db(tmp_path, *, balance_tenths=50000, name="manual.db"):
    """A db whose mirror is fresh-and-empty and whose balance is $50
    (50,000 tenths) -> derived caps: position $5, exposure $20, daily $5.

    `balance_tenths` is a parameter because the per-bet cap can only be made
    to bind at one contract by shrinking the bankroll: the path is armed at
    `MANUAL_ORDER_MAX_CONTRACTS`, so the old way of reaching that guard —
    asking for twenty — now stops at the size ceiling one check earlier."""
    path = tmp_path / name
    conn = db.init_db(path)
    now = int(time.time() * 1000)
    conn.execute(
        "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count) "
        "VALUES (?, 'settlements', 1, 0)", (now,),
    )
    conn.execute(
        "INSERT INTO venue_balance_snapshots (observed_ms, balance_tenths) "
        "VALUES (?, ?)", (now, balance_tenths),
    )
    conn.commit()
    conn.close()
    return path


#: The eight snapshot columns v28 adds, named once so a test cannot assert
#: "the columns are NULL" while silently checking six of them.
SNAPSHOT_COLUMNS = (
    "consensus_fair_tenths",
    "consensus_edge_tenths",
    "consensus_book_count",
    "consensus_anchored_on_sharp",
    "consensus_computed_ms",
    "consensus_fair_price_id",
    "consensus_link_id",
)


def _seed_consensus(
    path,
    *,
    ticker=TICKER,
    side="yes",
    fair_probability=0.551,
    edge_tenths=-18.4,
    book_count=7,
    anchored_on_sharp=1,
    computed_ms=1_700_000_000_000,
    created_ms=1_700_000_001_000,
):
    """A priced row for `(ticker, side)`, the way the runner writes one.

    The whole chain, because `PRAGMA foreign_keys = ON`: series -> event ->
    market, and event -> link -> fair price. A shortcut here would test a
    lookup against a shape the database cannot hold.

    Returns `(fair_price_id, link_id)` so a test can assert the breadcrumbs
    point at the rows that were actually read, rather than at any integer.
    """
    conn = db.open_db(path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO strategy_configs (version, created_ms, "
            "effective_from_ms, config_json, rationale, approved_by_user) "
            "VALUES (1, 0, 0, '{}', '', 1)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_series (series_ticker, league, "
            "has_game_markets, first_seen_ms, last_seen_ms) "
            "VALUES ('KXMLBGAME', 'mlb', 1, 0, 0)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_events (event_ticker, series_ticker, "
            "title, category, first_seen_ms, last_seen_ms) "
            "VALUES ('E1', 'KXMLBGAME', 'A at B', 'Sports', 0, 0)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, "
            "series_ticker, first_seen_ms, last_seen_ms) VALUES (?, 'E1', "
            "'KXMLBGAME', 0, 0)",
            (ticker,),
        )
        conn.execute(
            "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, "
            "odds_event_id, league, method, commence_skew_ms, linked_ms) "
            "VALUES ('E1', 'odds-1', 'mlb', 'exact_alias_pair', 0, 0)"
        )
        link = conn.execute(
            "SELECT id FROM event_links WHERE kalshi_event_ticker = 'E1' "
            "AND odds_event_id = 'odds-1'"
        ).fetchone()["id"]
        fair = conn.execute(
            "INSERT INTO fair_prices (computed_ms, link_id, market, "
            "outcome_name, p_conservative, book_count, books_used, "
            "anchored_on_sharp) "
            "VALUES (?, ?, 'h2h', 'A', ?, ?, '[]', ?)",
            (computed_ms, link, fair_probability, book_count, anchored_on_sharp),
        ).lastrowid
        conn.execute(
            "INSERT INTO recommendations (created_ms, strategy_config_version, "
            "ticker, link_id, fair_price_id, side, entry_ask_tenths, "
            "fair_probability, edge_tenths, fee_predicted, ev_net_dollars, "
            "kelly_fraction, suggested_contracts, kalshi_quote_age_ms, "
            "odds_age_ms, reason_text) "
            "VALUES (?, 1, ?, ?, ?, ?, 520, ?, ?, 0.1, 0.0, 0.0, 0, 0, 0, 'x')",
            (created_ms, ticker, link, fair, side, fair_probability, edge_tenths),
        )
        conn.commit()
    finally:
        conn.close()
    return int(fair), int(link)


def _manual_row(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT * FROM manual_orders ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()


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


@pytest.fixture
def records_only(monkeypatch):
    """Run the route's recording path instead of its sending path.

    The deployed constant is False since 2026-08-26 (the path is armed), so a
    test driving the happy path asks for a REST client -- which `conftest.py`
    makes impossible by removing the credentials, giving a 503 rather than an
    order. That refusal is asserted on its own in
    `TestTheArmedPathCannotReachTheVenueFromATest`.

    Everything ELSE the route does is unchanged by arming: the twelve checks,
    the reserve-then-check write, the idempotency replay, the cool-off it
    starts. Those are what the tests below are about, so they pin the constant
    to True and exercise the same code with the POST short-circuited -- which
    is precisely the property `kalshi/orders.py` claims for a dry run ("a dry
    run builds the identical request body ... and writes the identical row").
    """
    monkeypatch.setattr(manual_store, "MANUAL_ORDERS_ARE_DRY_RUNS", True)


class TestTheHappyPathRunsDry:
    async def test_a_dry_run_is_recorded_and_says_so(self, tmp_path, records_only):
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

    async def test_a_duplicate_key_replays_the_first_answer(
        self, tmp_path, records_only
    ):
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
    async def test_a_second_order_hits_the_cooloff(self, tmp_path, records_only):
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

    async def test_kxmve_is_refused_without_the_acknowledgement(self, tmp_path):
        """ADR 0073 narrowed the blanket refusal to a bounded one; the
        default is still NO. Mutation observed red: default the field True."""
        app = _app(_base_db(tmp_path))
        response = await post(
            app, "/api/manual-orders",
            json=_body(ticker=COMBO_TICKER), headers=AUTH,
        )
        assert response.status_code == 422
        assert "enter" in response.json()["detail"]
        assert "acknowledgement" in response.json()["detail"]

    async def test_a_combination_keeps_a_tighter_structural_ceiling(
        self, tmp_path
    ):
        """**Re-pointed 2026-08-26: one contract became a spend cap.**

        This asserted a combination was capped at ONE contract. That number
        came from ADR 0073 §5, which justified it by saying the cap "makes an
        error in that hedge cost a fraction of a cent instead of scaling with
        size" — but the combo fee is `k · C · P · (1-P)`, proportional to
        SPEND, not to count. Capping spend caps that error directly; capping
        count capped it only through whatever the price happened to be.

        So the money bound moved to `MANUAL_ORDER_MAX_SPEND_TENTHS` and what
        survives here is a structural ceiling, tighter for combinations than
        for single markets: the deepest resting bid ever measured on a
        combination book was 18 units (ADR 0012 §5), so a far larger count
        could not fill anyway.
        """
        app = _app(_base_db(tmp_path, balance_tenths=3_000_000))
        response = await post(
            app, "/api/manual-orders",
            json=_body(
                ticker=COMBO_TICKER,
                contracts=manual_store.COMBO_MAX_CONTRACTS + 1,
                combo_acknowledged=True,
            ),
            headers=AUTH,
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "enter-only" in detail, detail
        assert "could not fill" in detail, detail

    async def test_a_combination_is_bounded_tighter_than_a_single_market(self):
        """The two structural ceilings are not the same number, on purpose."""
        assert manual_store.COMBO_MAX_CONTRACTS < manual_store.MANUAL_ORDER_MAX_CONTRACTS

    async def test_an_acknowledged_combo_reaches_the_book(
        self, tmp_path, records_only
    ):
        """The acknowledgement opens the door; the book is what decides.
        The stub quotes a two-sided combo, which the record says is rare —
        the point of this test is that step 4 no longer refuses on the
        ticker alone."""
        quotes = StubQuotes(_payload(ticker=COMBO_TICKER))
        app = _app(_base_db(tmp_path), quotes=quotes)
        response = await post(
            app, "/api/manual-orders",
            json=_body(ticker=COMBO_TICKER, combo_acknowledged=True),
            headers=AUTH,
        )
        assert response.status_code == 200, response.json()
        assert response.json()["ticker"] == COMBO_TICKER

    async def test_the_combo_fee_hedge_is_what_the_cap_is_checked_against(
        self, tmp_path
    ):
        """ADR 0073: a combo's worst case runs through `combo_taker_fee`,
        not `calculate_fee`.

        Pinned on the CAP rather than on the displayed cost, and the reason
        is a defect this test caught in its first draft: the two fees differ
        by $0.0002 at one contract, and `worst_case_cost_display` is rounded
        to cents, so a display assertion stayed GREEN with the hedge removed
        — a test of a guard that could not see the guard.

        The bankroll is chosen so the per-bet cap ($0.4675) falls strictly
        between the two answers: $0.4674 through the deployed model, which
        would be admitted, and $0.4676 through the hedge, which is refused.
        Mutation observed red: price the combo through `calculate_fee`."""
        stake = 450 / 1000
        hedged = combo_taker_fee(450, 1)
        plain = calculate_fee(450, 1)
        assert hedged is not None and plain is not None
        cap = 0.4675
        assert stake + plain <= cap < stake + hedged, (
            "the bankroll no longer separates the two fee models; this test "
            "cannot see the guard it exists to pin"
        )
        quotes = StubQuotes(_payload(ticker=COMBO_TICKER))
        app = _app(
            _base_db(tmp_path, balance_tenths=4675), quotes=quotes
        )
        response = await post(
            app, "/api/manual-orders",
            json=_body(ticker=COMBO_TICKER, combo_acknowledged=True),
            headers=AUTH,
        )
        assert response.status_code == 422
        assert "per-bet cap" in response.json()["detail"]

    async def test_the_spend_ceiling_binds_before_anything_is_bought(
        self, tmp_path
    ):
        """**Re-pointed 2026-08-26: the ceiling is money, not contracts.**

        This asserted `contracts=2` was refused because the path armed at one
        contract. That ceiling was replaced by
        `MANUAL_ORDER_MAX_SPEND_TENTHS` on the owner's word -- one contract of
        a combination near a cent is a bet of $0.015, and he bets 25c to $3, so
        a contract cap did not make his bet small, it made the door
        decorative.

        The property survives and is the same one: **a size ceiling binds
        before anything is bought.** It is now expressed in the unit the risk
        is actually denominated in. The balance here is large enough that the
        balance-derived cap does not bind first, so the spend cap is the one
        under test.
        """
        # $3,000 balance -> $300 per-bet cap, far above the $3 spend cap, so
        # the spend cap is what refuses. Without this the test would pass for
        # the wrong reason.
        app = _app(_base_db(tmp_path, balance_tenths=3_000_000))
        response = await post(
            app, "/api/manual-orders", json=_body(contracts=20), headers=AUTH,
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "cap this path is set to" in detail, detail
        assert "$3.00" in detail, detail

    async def test_the_structural_contract_ceiling_still_exists(self, tmp_path):
        """Money is the binding bound; this is the backstop.

        A market priced at a tenth of a cent turns $3 into thousands of
        contracts, and a count that large is a different kind of order -- it
        moves a thin book on its own -- even when the money is small.
        """
        app = _app(_base_db(tmp_path, balance_tenths=3_000_000))
        response = await post(
            app, "/api/manual-orders",
            json=_body(contracts=manual_store.MANUAL_ORDER_MAX_CONTRACTS + 1),
            headers=AUTH,
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "structural ceiling" in detail, detail

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
        """$4 balance -> $0.40 per-bet cap; one contract at 45c is $0.4674
        fee-inclusive. Reached at one contract deliberately: the size
        ceiling would otherwise refuse a larger order first, and a guard
        standing behind a stricter guard is decoration (ADR 0018's own
        argument)."""
        app = _app(_base_db(tmp_path, balance_tenths=4000))
        response = await post(
            app, "/api/manual-orders", json=_body(), headers=AUTH,
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
        only dry_run value any production call site may pass.

        **The scan reads whole argument lists, not one line, and counts
        them.** It matched a one-line `OrderPlacer(dry_run=...)` until the
        manual path took a `rest=` argument (ADR 0018's second barrier,
        wired ahead of arming) and wrapped onto three lines -- at which
        point the regex stopped matching that call and the pin quietly
        covered one construction instead of two, while staying green. The
        count assertion is here so that silence cannot repeat: a third
        production placer has to be looked at rather than absorbed."""
        routes = (REPO / "backend" / "api" / "routes.py").read_text(encoding="utf-8")
        calls = re.findall(r"OrderPlacer\(([^)]*)\)", routes, re.S)
        assert len(calls) == 2, (
            f"expected exactly two production OrderPlacer constructions "
            f"(engine, manual); found {len(calls)}"
        )
        for args in calls:
            found = re.search(r"dry_run=([A-Za-z_][\w.]*)", args)
            assert found, f"OrderPlacer constructed with no dry_run: {args!r}"
            assert found.group(1) in (
                "ORDERS_ARE_DRY_RUNS",
                "manual_store.MANUAL_ORDERS_ARE_DRY_RUNS",
            ), f"OrderPlacer constructed with dry_run={found.group(1)!r}"

    def test_the_armed_path_would_get_a_rest_client(self):
        """ADR 0018's second barrier, pinned on the source because it cannot
        be driven while the constant is True: a live `OrderPlacer` with no
        REST client raises, so arming without this wiring produces a 503
        rather than an order. Mutation observed red: drop `rest=placer_rest`
        from the construction."""
        routes = (REPO / "backend" / "api" / "routes.py").read_text(encoding="utf-8")
        manual = routes[routes.index("def place_manual_order"):]
        placer = manual[manual.index("OrderPlacer("):]
        placer = placer[: placer.index(")")]
        assert "rest=" in placer, (
            "the manual placer takes no REST client; flipping "
            "MANUAL_ORDERS_ARE_DRY_RUNS would produce a 503, not an order"
        )
        assert "if not manual_store.MANUAL_ORDERS_ARE_DRY_RUNS:" in manual, (
            "the REST client is built unconditionally; a dry run on a "
            "keyless instance would then refuse where it works today"
        )

    def test_the_manual_path_is_armed_and_the_engine_path_is_not(self):
        """The two doors have separate switches, and only one is open.

        This test asserted `MANUAL_ORDERS_ARE_DRY_RUNS is True` until
        2026-08-26, when Joe armed the manual path. The assertion is not
        weakened to make that pass -- it is **re-pointed at the property that
        still has to hold**: arming one door must not arm the other. The
        engine's path is gated by ADR 0015's 300-game evidence floor, and no
        act of Joe's discretion may open it (ADR 0063 §2's hardest rule is the
        same boundary, drawn on populations rather than on switches).

        If this file ever needs to say the manual path is dry again, that is a
        disarm: set the constant back to True and change the assertion below in
        the same commit."""
        assert manual_store.MANUAL_ORDERS_ARE_DRY_RUNS is False, (
            "the manual path was disarmed without updating this pin"
        )
        from backend.store.orders import ORDERS_ARE_DRY_RUNS

        assert ORDERS_ARE_DRY_RUNS is True, (
            "the ENGINE path is armed; ADR 0015 and ADR 0018 both say that "
            "takes the gate's 300 scored games, not a hand-bet decision"
        )

    def test_neither_switch_can_be_moved_by_the_environment(self):
        """Both are module constants (ADR 0018: "no environment read, no
        config object, no override"), so arming stays a commit and a deploy
        rather than something a secret can do at 2am."""
        for module in ("manual_orders", "orders"):
            source = (REPO / "backend" / "store" / f"{module}.py").read_text(
                encoding="utf-8"
            )
            for name in ("ARE_DRY_RUNS = ",):
                assignments = [
                    line for line in source.splitlines() if name in line
                ]
                assert len(assignments) == 1, (module, assignments)
                assert assignments[0].split("=")[1].strip() in ("True", "False")
            # Code only. The first draft scanned the whole file and went red on
            # a COMMENT that used the word "environment" -- a source scan that
            # reads prose is a scan whose population includes the argument for
            # the rule it is enforcing.
            code = ast.parse(source)
            reads = [
                node
                for node in ast.walk(code)
                if isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "os"
            ]
            assert not reads, (
                f"{module} reads the environment; both switches are module "
                f"constants by ADR 0018, so that a secret cannot arm anything"
            )


class TestTheArmedPathCannotReachTheVenueFromATest:
    """The suite is structurally incapable of sending an order.

    From 2026-08-26 the deployed constant is False, so the happy path asks for
    a REST client. `conftest.py::no_live_kalshi_credentials` removes
    `KALSHI_API_KEY` and `KALSHI_PRIVATE_KEY_PATH` for every test, so
    `KalshiConfig.load()` raises and the route answers 503 **before** anything
    is written or sent.

    Without that fixture, running this suite on the machine that holds `.env`
    would have placed a real immediate-or-cancel order on the exchange. That is
    the single worst failure this repo could have, and it is why the guard is
    asserted here rather than left as a property of a conftest nobody reads.
    """

    async def test_the_route_refuses_and_says_nothing_was_sent(self, tmp_path):
        """Mutation observed red: drop the `delenv` calls from the fixture (on
        a machine with credentials this then places a REAL order, so the
        mutation is run by DELETING the env vars' source, never by restoring
        them)."""
        path = _base_db(tmp_path)
        app = _app(path)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 503, response.text
        detail = response.json()["detail"]
        assert "no Kalshi credentials" in detail
        assert "Nothing was sent" in detail

    async def test_the_refusal_writes_no_row_that_could_read_as_a_bet(
        self, tmp_path
    ):
        """The credentials check runs BEFORE `reserve_manual_order`, so a
        refused request leaves the record untouched — no pending row to
        reconcile, and no exposure held against a bet that never existed."""
        path = _base_db(tmp_path)
        app = _app(path)
        await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        conn = sqlite3.connect(path)
        count = conn.execute("SELECT COUNT(*) FROM manual_orders").fetchone()[0]
        conn.close()
        assert count == 0

    def test_the_credential_fixture_is_autouse(self):
        """Pinned on the source: an opt-in guard against sending real money is
        a guard that the one test which forgets it does not have."""
        source = (REPO / "conftest.py").read_text(encoding="utf-8")
        block = source[source.index("def no_live_kalshi_credentials"):]
        marker = source[: source.index("def no_live_kalshi_credentials")]
        assert marker.rstrip().endswith("@pytest.fixture(autouse=True)"), (
            "no_live_kalshi_credentials is no longer autouse"
        )
        assert 'delenv("KALSHI_API_KEY"' in block
        assert 'delenv("KALSHI_PRIVATE_KEY_PATH"' in block


class TestAnEmptyBookIsNotAFreeContract:
    """A derived ask off the tradeable range is not a price.

    Asks are derived (`yes_ask = 1000 - best_no_bid`), so an empty book does
    not report "no ask" -- it reports the endpoint. A missing NO bid reads as
    a resting bid of 100c and hands back a **0c YES ask**. That is the shape
    of every combination market on the venue today (`no_bid_dollars =
    1.0000`, depth 0.0), and it rendered as "YES 0c" on the ticket the first
    time the screen was driven against a real book (2026-08-26).

    The order path was already safe -- `OrderRequest` refuses 0 on the grid --
    so this is a screen defect, and the reason it counts is CLAUDE.md rule 1:
    a free contract on the venue's most illiquid product is a large apparent
    edge, and those are bugs until proven otherwise.
    """

    EMPTY = dict(yes_bid_tenths=0, no_bid_tenths=1000)

    async def test_the_read_reports_no_ask_rather_than_zero_cents(self, tmp_path):
        """Mutation observed red: return `ask_tenths` unfiltered."""
        quotes = StubQuotes(_payload(**self.EMPTY))
        app = _app(_base_db(tmp_path), quotes=quotes)
        body = (await get(app, f"/api/manual/market/{TICKER}")).json()
        assert body["sides"]["yes"]["ask_tenths"] is None
        assert body["sides"]["yes"]["ask_display"] is None
        assert body["sides"]["no"]["ask_tenths"] is None
        assert body["sides"]["yes"]["authorised_contracts"] in (None, 0)

    async def test_the_order_refuses_and_names_the_endpoint(self, tmp_path):
        quotes = StubQuotes(_payload(**self.EMPTY))
        app = _app(_base_db(tmp_path), quotes=quotes)
        response = await post(
            app, "/api/manual-orders", json=_body(), headers=AUTH,
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "no live ask" in detail
        assert "endpoint" in detail

    async def test_a_real_ask_still_gets_through(self, tmp_path):
        """The filter must refuse the endpoints and nothing else."""
        app = _app(_base_db(tmp_path))
        body = (await get(app, f"/api/manual/market/{TICKER}")).json()
        assert body["sides"]["yes"]["ask_tenths"] == 450


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
        # The read reports the DEPLOYED value, not a fixture's preference: the
        # ticket renders "this path runs DRY" off this field, and a screen that
        # says dry while the route sends is the worst wrong answer available.
        assert body["dry_run"] is False

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


class TestTheRowRecordsWhatTheDeskWasShowing:
    """ADR 0082: the consensus, frozen at intent-write time, not pointed at.

    Until v28 a hand bet recorded his typed estimate and nothing about what
    the desk had on screen when he typed it, so the devigged consensus at the
    moment of the bet was unrecoverable -- and, for a KXMVE combination,
    unrecoverable in principle, since discovery drops that prefix and no
    `kalshi_markets` row ever exists.
    """

    async def test_the_snapshot_is_the_value_the_desk_was_showing(
        self, tmp_path, records_only
    ):
        """Mutation observed red: drop the snapshot arguments from
        `_insert_intent`'s VALUES tuple."""
        path = _base_db(tmp_path)
        fair_id, link_id = _seed_consensus(
            path, fair_probability=0.551, edge_tenths=-18.4, book_count=7,
            anchored_on_sharp=1, computed_ms=1_700_000_000_000,
        )
        app = _app(path)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 200, response.text

        row = _manual_row(path)
        # 0.551 -> 551 tenths of a cent. Integer, on the same 0-1000 scale as
        # `limit_price_tenths` -- never float dollars.
        assert row["consensus_fair_tenths"] == 551
        assert isinstance(row["consensus_fair_tenths"], int)
        assert row["consensus_edge_tenths"] == -18
        assert isinstance(row["consensus_edge_tenths"], int)
        assert row["consensus_book_count"] == 7
        assert row["consensus_anchored_on_sharp"] == 1
        assert row["consensus_computed_ms"] == 1_700_000_000_000
        assert row["consensus_fair_price_id"] == fair_id
        assert row["consensus_link_id"] == link_id
        assert row["consensus_absent_reason"] is None

    async def test_the_ask_is_not_duplicated_because_limit_price_already_is_it(
        self, tmp_path, records_only
    ):
        """`limit_price_tenths` IS the market ask at the tap.

        `OrderRequest.fill_price_tenths` for our side, off the live quote,
        snapped to the venue grid, and bounded by the typed ceiling because
        check 7 refuses rather than re-prices. So no second ask column exists,
        and this test is the reason the absence is deliberate rather than an
        oversight. The stub book quotes a 550-tenth NO bid, so the YES ask is
        its complement, 450.
        """
        path = _base_db(tmp_path)
        app = _app(path)
        assert (
            await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        ).status_code == 200
        row = _manual_row(path)
        assert row["limit_price_tenths"] == 450
        columns = row.keys()
        assert not [c for c in columns if "ask" in c], (
            "an ask column was added beside limit_price_tenths; that is one "
            "fact under two names"
        )

    async def test_the_snapshot_follows_the_side_that_was_bought(
        self, tmp_path, records_only
    ):
        """A NO bet must not borrow the YES row's fair value.

        The YES row is seeded LAST and NEWEST on purpose: the ordering alone
        would then pick it, so dropping the side filter changes the answer.
        Seeded the other way round the test passes with the filter removed,
        which is what the first version of it did.

        Mutation observed red: drop `AND r.side = ?` from `_read_consensus`.
        """
        path = _base_db(tmp_path)
        _seed_consensus(
            path, side="no", fair_probability=0.402, created_ms=1_000
        )
        _seed_consensus(
            path, side="yes", fair_probability=0.551, created_ms=2_000
        )
        app = _app(path)
        body = _body(side="no", max_price_tenths=700)
        assert (
            await post(app, "/api/manual-orders", json=body, headers=AUTH)
        ).status_code == 200
        assert _manual_row(path)["consensus_fair_tenths"] == 402

    async def test_the_freshest_priced_row_wins(self, tmp_path, records_only):
        """Mutation observed red: `ORDER BY r.created_ms ASC`."""
        path = _base_db(tmp_path)
        _seed_consensus(path, fair_probability=0.300, created_ms=1_000)
        _seed_consensus(path, fair_probability=0.700, created_ms=2_000)
        app = _app(path)
        assert (
            await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        ).status_code == 200
        assert _manual_row(path)["consensus_fair_tenths"] == 700

    async def test_an_unpriced_ticker_records_the_absence_not_a_zero(
        self, tmp_path, records_only
    ):
        path = _base_db(tmp_path)
        app = _app(path)
        assert (
            await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        ).status_code == 200
        row = _manual_row(path)
        for column in SNAPSHOT_COLUMNS:
            assert row[column] is None, column
        assert row["consensus_absent_reason"] == manual_store.ABSENT_NO_PRICED_ROW

    def test_an_out_of_range_probability_is_refused_rather_than_clamped(self):
        """`probability_to_tenths` clamps, so the bounds check is the guard.

        Mutation observed red: `return probability_to_tenths(value)` with the
        range test removed -- 1.5 then reads as 1000 tenths, a settled
        outcome written down as a live consensus.
        """
        assert manual_store._fair_tenths(1.5) is None
        assert manual_store._fair_tenths(-0.2) is None
        assert manual_store._fair_tenths(float("nan")) is None
        assert manual_store._fair_tenths(None) is None
        assert manual_store._fair_tenths(0.551) == 551

    def test_a_snapshot_cannot_be_a_hole_with_no_stated_cause(self):
        """The invariant that makes every NULL in the table interpretable."""
        with pytest.raises(ValueError):
            manual_store.ConsensusSnapshot()
        with pytest.raises(ValueError):
            manual_store.ConsensusSnapshot(fair_tenths=551, absent_reason="x")


class TestACombinationHasNoConsensusAndSaysSo:
    """`KXMVE` has no devigged consensus and never can.

    `kalshi/discovery.JUNK_PREFIX` drops the prefix, so no `kalshi_markets`
    row exists, so no `recommendations` or `fair_prices` row can. Zero would
    read as "the sportsbooks say this is worth nothing", which on a money row
    is a lie rather than a gap.
    """

    async def test_every_snapshot_column_is_null_never_zero(
        self, tmp_path, records_only
    ):
        """Mutation observed red: delete the `is_combo_ticker` branch from
        `_read_consensus`."""
        path = _base_db(tmp_path)
        app = _app(path, quotes=StubQuotes(_payload(ticker=COMBO_TICKER)))
        body = _body(
            ticker=COMBO_TICKER, combo_acknowledged=True, max_price_tenths=700
        )
        response = await post(app, "/api/manual-orders", json=body, headers=AUTH)
        assert response.status_code == 200, response.text

        row = _manual_row(path)
        for column in SNAPSHOT_COLUMNS:
            assert row[column] is None, f"{column} is {row[column]!r}, not NULL"
            assert row[column] != 0
        assert row["consensus_absent_reason"] == manual_store.ABSENT_COMBO

    def test_the_combo_branch_refuses_before_it_reads_anything(self):
        """The NULLs above are over-determined, so this isolates the branch.

        A combination has no `recommendations` row either -- the same
        `JUNK_PREFIX` that stops it -- so the route-level test would still see
        NULLs with the combo branch removed, and it does: deleting the branch
        turns `combo_ticker` into `no_priced_row` and nothing else. This one
        hands `_read_consensus` a connection that raises on any query, so a
        combination that reached the database at all would go red.

        Mutation observed red: delete the `is_combo_ticker` branch --
        sqlite3.ProgrammingError instead of a snapshot.
        """
        class NeverQueried:
            def execute(self, *args, **kwargs):
                raise AssertionError(
                    "a combination reached the database; there is nothing "
                    "there for it to find"
                )

        snapshot = manual_store._read_consensus(
            NeverQueried(), ticker=COMBO_TICKER, side="yes"
        )
        assert snapshot.absent_reason == manual_store.ABSENT_COMBO
        assert snapshot.fair_tenths is None

    def test_the_route_and_the_store_share_one_combo_predicate(self):
        """Two spellings of one boundary is the failure this repo repeats.

        Mutation observed red: put the prefix comparison back in
        `routes._is_combo`; the bare literal reappears in the parse tree.

        Read off the AST rather than the text, so the prefix may still be
        NAMED in a comment or a docstring -- which it is, and should be -- but
        may not be a value the module compares against.
        """
        source = (REPO / "backend" / "api" / "routes.py").read_text(
            encoding="utf-8"
        )
        assert "manual_store.is_combo_ticker(ticker)" in source
        literals = [
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant)
            and node.value == manual_store.COMBO_PREFIX
        ]
        assert literals == [], (
            "routes.py carries its own copy of the combination prefix; the "
            "predicate lives in store/manual_orders.is_combo_ticker"
        )


class TestTheSnapshotCanNeverBlockABet:
    """Additive recording. If the lookup breaks, the order still goes.

    The order path's behaviour must be byte-for-byte what it was before the
    snapshot existed, and this is the test that says so.
    """

    async def test_a_raising_lookup_still_places_the_order(
        self, tmp_path, records_only, monkeypatch
    ):
        """Mutation observed red: remove the `except Exception` from
        `consensus_snapshot` -- the POST becomes a 503 and no row is written.
        """
        def boom(conn, *, ticker, side):
            raise RuntimeError("the consensus read fell over")

        monkeypatch.setattr(manual_store, "_read_consensus", boom)
        path = _base_db(tmp_path)
        _seed_consensus(path)
        app = _app(path)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "dry_run"

        row = _manual_row(path)
        for column in SNAPSHOT_COLUMNS:
            assert row[column] is None, column
        assert row["consensus_absent_reason"] == manual_store.ABSENT_LOOKUP_FAILED

    async def test_a_teardown_is_not_relabelled_as_a_missing_fair_value(
        self, tmp_path, records_only, monkeypatch
    ):
        """`BaseException` is deliberately not caught.

        A `KeyboardInterrupt` is the process being torn down; recording it as
        `lookup_failed` would hide a shutdown inside a data column.
        """
        def interrupted(conn, *, ticker, side):
            raise KeyboardInterrupt

        monkeypatch.setattr(manual_store, "_read_consensus", interrupted)
        conn = db.open_db(_base_db(tmp_path))
        try:
            with pytest.raises(KeyboardInterrupt):
                manual_store.consensus_snapshot(conn, ticker=TICKER, side="yes")
        finally:
            conn.close()

    def test_the_lookup_runs_outside_the_write_lock(self):
        """It must not lengthen the window the runner contends for.

        Read off the source rather than timed: the snapshot line has to come
        before `BEGIN IMMEDIATE`, and a timing assertion would be flaky where
        an ordering assertion is exact.
        """
        source = (
            REPO / "backend" / "store" / "manual_orders.py"
        ).read_text(encoding="utf-8")
        body = source[source.index("def reserve_manual_order"):]
        assert body.index("consensus_snapshot(conn") < body.index("BEGIN IMMEDIATE")

    def test_gate_py_still_never_reads_the_manual_table(self):
        """The snapshot must not have opened a door into the interlock."""
        source = (REPO / "backend" / "gate.py").read_text(encoding="utf-8")
        assert "manual_orders" not in source
        assert "consensus_fair_tenths" not in source


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
