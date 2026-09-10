"""The manual order path (ADR 0063): a separate door with unwaivable guards.

Every check is server-side and every test here drives the route the way a
client would — the demo-unreachability halves, the lockout and cool-off 423s,
the KXMVE refusal, the daily-loss switch over the venue mirror, the derived
caps, the price ceiling, the depth check, the netting guard over the
`position_fp` shape observed 2026-08-30, and the reserve-then-check
transaction in `manual_orders`. Plus the two separation pins that make ADR 0063 an
architecture rather than a promise: `gate.py` never reads the table, and no
production call site passes the dry-run constant as anything but itself.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- Nothing about the venue's create-order response (never observed; C0 owns
  that) — the placer here runs dry.
- Nothing about the frontend ticket. There is no masking left to establish:
  the ticket stopped asking for a probability on 2026-09-09 (ADR 0131, superseding ADR 0065 §2),
  and the pins below assert only that the route no longer requires one and
  that the row records NULL rather than a zero.
"""

from __future__ import annotations

import ast
import re
import json
import sqlite3
import time
from pathlib import Path

import httpx
import pytest

import backend.parlays as parlays
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
from tests.test_rest import OBSERVED_POSITION_ROW
from backend.store import db
from backend.store import manual_orders as manual_store
from backend.store.orders import ExposureCapExceeded

REPO = Path(__file__).resolve().parents[1]
TICKER = "KXMLBGAME-26AUG22TEST-AAA"
COMBO_TICKER = "KXMVECROSSCATEGORY0-SHARD1-S2026TEST-ABC"
AUTH = {"Authorization": "Bearer secret-token"}


def _payload(*, ticker=TICKER, yes_bid_tenths=350, no_bid_tenths=550,
             yes_ask_size=500.0, price_ranges=True, exchange_index=0):
    market = {
        "ticker": ticker,
        "status": "active",
        # The shard this market settles on. Kalshi sends it on every market
        # row (observed: 0 on `KXNFLGAME-*`, 1 on `KXMVE*`), and the order
        # path refuses without it, so a stub that omitted it would make every
        # test exercise the unreadable-shard branch instead of the real one.
        # Pass `exchange_index=None` to reach that branch deliberately.
        **({} if exchange_index is None else {"exchange_index": exchange_index}),
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
                 fetch_error=None, shard_tenths=50000, balance_error=None,
                 balance_payload=None):
        self._payload = payload if payload is not None else _payload()
        self._positions = positions if positions is not None else []
        self._positions_error = positions_error
        self._fetch_error = fetch_error
        # Funded by default and generously, so a test about something else
        # never fails on collateral. The shard-specific tests set it.
        self._shard_tenths = shard_tenths
        self._balance_error = balance_error
        self._balance_payload = balance_payload

    async def fetch(self, ticker, *, observed_ms):
        if self._fetch_error is not None:
            raise self._fetch_error
        return parse_market_quote(self._payload, observed_ms=observed_ms)

    async def shard_balance(self, *, exchange_index: int):
        """`/portfolio/balance?exchange_index=N`, in the venue's own shape.

        `balance_breakdown` rows carry `balance` as a 4dp dollar STRING, which
        is what `read_shard_funds` parses; building the stub any other way
        would pin a shape Kalshi does not send.
        """
        if self._balance_error is not None:
            raise self._balance_error
        if self._balance_payload is not None:
            return self._balance_payload
        return {
            "balance_breakdown": [
                {
                    "exchange_index": exchange_index,
                    "balance": f"{self._shard_tenths / 1000:.4f}",
                }
            ]
        }

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


#: The live shape of `parlay_lookups` id=41, the most recent real combination
#: bet: a 0.33862 conservative joint against a 410-tenth derived ask, holding
#: 17.4%. Used rather than round numbers so the arithmetic below is checked
#: against a row the venue and the desk actually produced.
LIVE_LOOKUP_FAIR_JOINT = 0.33862
LIVE_LOOKUP_ASK_TENTHS = 410
LIVE_LOOKUP_HOLD = 1.0 - LIVE_LOOKUP_FAIR_JOINT * (1000.0 / LIVE_LOOKUP_ASK_TENTHS)


def _seed_parlay_lookup(
    path,
    *,
    minted=COMBO_TICKER,
    status="priced",
    fair_joint=LIVE_LOOKUP_FAIR_JOINT,
    ask_tenths=LIVE_LOOKUP_ASK_TENTHS,
    hold=LIVE_LOOKUP_HOLD,
    requested_ms=1_700_000_002_000,
    card_key="safe",
):
    """A `parlay_lookups` row, the way `parlays._record_lookup` writes one.

    This is the combination's consensus: `fair_joint_conservative` is the
    joint of each leg's `p_conservative`, and it is what the buy ticket
    renders as "Fair value ... hold ..." one component above the button.

    Returns the row id.
    """
    conn = db.open_db(path)
    try:
        row_id = conn.execute(
            "INSERT INTO parlay_lookups (requested_ms, card_key, stake_cents, "
            "selected_legs, collection_ticker, status, minted_market_ticker, "
            "book_no_bid_tenths, derived_yes_ask_tenths, book_depth, "
            "fair_joint_conservative, hold, collection_unverified) "
            "VALUES (?, ?, 100, ?, 'KXMVECROSSCATEGORY0-SHARD1', ?, ?, ?, ?, "
            "        3.0, ?, ?, 0)",
            (
                requested_ms,
                card_key,
                json.dumps([
                    {"event_ticker": "E1", "market_ticker": "LEG-A",
                     "side": "yes", "label": "A to win"},
                    {"event_ticker": "E2", "market_ticker": "LEG-B",
                     "side": "yes", "label": "B to win"},
                ]),
                status,
                minted,
                None if ask_tenths is None else 1000 - ask_tenths,
                ask_tenths,
                fair_joint,
                hold,
            ),
        ).lastrowid
        conn.commit()
    finally:
        conn.close()
    return int(row_id)


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
        # Not asked, so not known. NULL, never 0 -- a zero would read as "he
        # thought this had no chance", which on a money row is a lie.
        assert row["p_yes_bp"] is None
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

    async def test_a_bet_needs_no_probability_and_records_none(
        self, tmp_path, records_only
    ):
        """**Inverted 2026-09-09 on Joe's instruction, not to make it pass.**

        This asserted a 422 when the body carried no `p_yes_bp` -- ADR 0065's
        precondition, enforced server-side so the client's masking could not
        be the only thing holding it. Joe removed the field: "what is even the
        point of the (p)yes score entry? I don't need it. it just gets in the
        way." ADR 0065 shipped over a red-team objection that an unscored form
        is a speed bump a user learns to type through, and it lost on one
        premise -- that `bets.bet_clv()` had given a pre-bet P(YES) a
        consumer. Nothing in the tree ever SELECTed the column. See
        `docs/adr/0131.md`.

        Kept and reversed rather than deleted, because the thing worth pinning
        is that a bet with no probability GOES THROUGH -- a deletion would
        leave nothing to fail if a future session restored the precondition.
        And the distinguishing consequence is asserted, not merely the absence
        of a refusal: the row exists and its `p_yes_bp` is NULL.
        """
        path = _base_db(tmp_path)
        app = _app(path)
        body = _body()
        assert "p_yes_bp" not in body, "the ticket no longer sends one"
        response = await post(app, "/api/manual-orders", json=body, headers=AUTH)
        assert response.status_code == 200, response.text
        assert "p_yes_bp" not in response.json(), (
            "the receipt still reports a probability the ticket never asked for"
        )
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM manual_orders").fetchone()
        conn.close()
        assert row is not None, "the order was accepted but nothing was written"
        assert row["p_yes_bp"] is None

    async def test_a_stale_client_that_still_sends_one_is_not_refused(
        self, tmp_path, records_only
    ):
        """A phone holding an old bundle must not start 422ing.

        The field is gone from `ManualOrderRequest`, and Pydantic ignores an
        extra key rather than rejecting it -- so the order lands and the row
        records NULL, which is the truth about a number this server did not
        ask for and does not read.
        """
        path = _base_db(tmp_path)
        app = _app(path)
        response = await post(
            app, "/api/manual-orders", json=_body(p_yes_bp=7000), headers=AUTH,
        )
        assert response.status_code == 200, response.text
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT p_yes_bp FROM manual_orders").fetchone()
        conn.close()
        assert row["p_yes_bp"] is None, (
            "a client-supplied probability was written after the server "
            "stopped asking for one"
        )


class TestTheGuardsRefuse:
    async def test_a_second_order_no_longer_hits_a_cooloff(
        self, tmp_path, records_only
    ):
        """**Inverted 2026-09-08 on Joe's instruction, not to make it pass.**

        This asserted 423 and "resting" on the second order inside ten
        minutes. He removed the cool-off
        (`docs/adr/0112-the-caps-come-off-the-hand-bet-path.md` §1, answer
        3), having first been told what it would cost him: he averages ~2.3
        fills per sitting, so this brake fired on most sittings rather than
        rare ones.

        The assertion is kept and reversed rather than deleted, because the
        thing worth pinning is that back-to-back betting WORKS -- a deletion
        would leave nothing to fail if a future session restored the brake,
        and ADR §5 says restoring it needs Joe.
        """
        path = _base_db(tmp_path)
        app = _app(path)
        first = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert first.status_code == 200
        second = await post(
            app, "/api/manual-orders",
            json=_body(idempotency_key="test-key-00000002"), headers=AUTH,
        )
        assert second.status_code == 200, second.json()
        # And the response must not promise a rest that will not happen: the
        # screen gates its buy control on this field.
        assert second.json()["cooloff_until_ms"] is None

    async def test_the_market_route_reports_no_cooloff_either(
        self, tmp_path, records_only
    ):
        """The half a server-side removal alone would have missed.

        `ManualTicket` refuses client-side on `market.cooloff_until_ms`.
        Removing the brake in the route and leaving `/api/manual/market`
        populating this field would have left the screen enforcing a rule the
        server had dropped -- the "one predicate with two spellings" failure
        this repo has now hit three times.
        """
        app = _app(_base_db(tmp_path))
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 200
        estimate = await get(app, f"/api/manual/market/{TICKER}", headers=AUTH)
        assert estimate.status_code == 200, estimate.json()
        assert estimate.json()["cooloff_until_ms"] is None

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
        detail = response.json()["detail"]
        assert "enter" in detail
        assert "acknowledgement" in detail
        # The exit census, in its own digits -- asserted against the constants
        # and never against the literals. This is the third of the three
        # sentences that carried a typed "40 of 40"; the reason all three are
        # sourced now is that a reader grepping the phrase must not find one
        # authoritative copy and two frozen ones.
        #
        # **The 2026-09-06 parlay census does not touch this claim.** It
        # refuted the ENTRY half (51 of 52 combination positions were taker
        # fills) and measured nothing about the way out. ADR 0085
        # Amendment 1 §A1.4 forbids softening the exit claim on the strength
        # of that entry finding, and it still does.
        #
        # **What DID move it, on 2026-09-10: two shard-1 books were read
        # carrying resting YES bids.** "You can enter and you cannot exit"
        # was a universal and one counterexample ends it. §A1.4 protects a
        # claim that holds; it does not require a real-money refusal path to
        # keep asserting a falsified one. The refusal keeps its force by
        # naming the size instead -- ten contracts at a single price -- and
        # still refuses to imply a rate, which Arm D measures on 2026-09-13.
        assert str(parlays.COMBO_EXIT_CENSUS_BOOKS_NO_YES_BID) in detail
        assert str(parlays.COMBO_EXIT_CENSUS_BOOKS_READ) in detail
        assert "NO YES BID" in detail
        assert str(parlays.COMBO_EXIT_SHARD_YES_BID_BOOKS) in detail
        assert str(parlays.COMBO_EXIT_SHARD_YES_BID_SIZE_CONTRACTS) in detail
        # Both halves of the replacement, so neither can be dropped: the
        # entry door is still open, and the way out is small and unmeasured.
        assert "you can enter" in detail
        assert "small and unmeasured" in detail
        # The killed universal must not return.
        assert "cannot exit" not in detail

    def test_no_census_number_in_the_combo_acknowledgement_refusal_is_typed_rather_than_sourced(
        self,
    ):
        """The refusal's digits come from the constants, or this is theatre.

        The assertions above read `str(COMBO_EXIT_CENSUS_BOOKS_READ) in
        detail`, which passes just as happily on a **typed** "40" as on a
        sourced one -- and a typed "40 of 40" is exactly how the refuted entry
        sentence survived a green suite for eleven days. This reads the source
        of the f-string instead and refuses any bare integer in it.

        Same pattern and same carve-out as
        `tests/test_combo_bid_routes.py::
        test_no_census_number_in_the_bid_refusal_is_typed_rather_than_sourced`
        -- this string carries TWO document identifiers ("ADR 0012 §5" and
        "ADR 0046"), which are permanent names rather than measurements and
        cannot go stale the way a census count can, so they are stripped
        before the digit check rather than allowed to disable it. Only
        `status_code=422` is excluded structurally: the check reads the
        `detail` expression alone.

        **The section number is part of the identifier, and the first draft
        of this test proved it by failing on the `5` of "§5".** The carve-out
        matches `ADR 0012 §5` whole rather than leaving an orphan digit
        behind -- a citation half-stripped would have forced a choice between
        deleting the section reference from a real-money refusal and turning
        the guard off.

        Mutation observed red: replace `{COMBO_EXIT_CENSUS_BOOKS_READ}` with a
        literal `40` in `backend/api/routes.py`.
        """
        route = next(
            node
            for node in ast.walk(ast.parse(
                (REPO / "backend" / "api" / "routes.py").read_text(
                    encoding="utf-8"
                )
            ))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "place_manual_order"
        )
        detail = next(
            kw.value
            for inner in ast.walk(route)
            if isinstance(inner, ast.Raise) and isinstance(inner.exc, ast.Call)
            for kw in inner.exc.keywords
            if kw.arg == "detail"
            and "need the acknowledgement" in ast.unparse(kw.value)
        )
        rendered = ast.unparse(detail)
        # An ADR citation, section number and all -- see the docstring.
        stripped = re.sub(r"ADR \d+(?:\s*§\s*[\d.]+)?", "ADR", rendered)
        digits = [ch for ch in stripped if ch.isdigit()]
        assert not digits, f"a census number is typed in: {rendered}"
        names = {n.id for n in ast.walk(detail) if isinstance(n, ast.Name)}
        assert "COMBO_EXIT_CENSUS_BOOKS_NO_YES_BID" in names
        assert "COMBO_EXIT_CENSUS_BOOKS_READ" in names

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
        for single markets.

        **Its stated reason was false and was replaced 2026-09-08; the cap and
        this assertion are unchanged.** The reason used to be "the deepest
        resting bid ever measured on a combination book was 18 units (ADR 0012
        §5), so a far larger count could not fill anyway." ADR 0012 carries no
        such figure, the real source scoped it to a single 11-row run with the
        word "here", and the committed captures reach 683 units. The ceiling
        now rests on the exit instead, which is measured and unrefuted: zero
        resting YES bids on 40 of 40 combination books. Easy to open, possibly
        impossible to close. See `test_the_combo_depth_claims_match_the
        _committed_captures`.
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
        # **Re-pointed 2026-09-08, and deliberately made STRONGER rather than
        # looser.** This used to assert the tokens "enter-only" and "could not
        # fill". The second was a false claim (see
        # `tests/test_combo_book_depth_claims.py`) and the first is jargon Joe
        # has asked not to be handed undefined. What the refusal must now carry
        # is the substance: which side of the book is missing, over how many
        # observations, and that the risk is the EXIT rather than the entry.
        assert "resting YES bid" in detail, detail
        assert "40 of 40" in detail, detail
        assert "exit" in detail, detail
        # And it must not have regained the fill bound it could never support.
        assert "could not fill" not in detail, detail
        assert "18 units" not in detail, detail
        # **Inverted 2026-09-08, and it is the third claim this one assertion
        # has pinned.** It required the refusal to name the "$3.00 spend cap"
        # as the real bound. Joe removed that cap (ADR 0112) and the route
        # stopped applying it the same day, so the sentence became a promise
        # of a brake that is not there -- on the message a real-money refusal
        # hands him. A test asserting the stale phrase PRESENT is what kept it
        # shipping, which is the failure `backend/parlays.py:105-111` records
        # about "40 of 40": the binding preserved the error instead of
        # catching it.
        #
        # So the phrase is now pinned ABSENT, and what must be named instead
        # is what actually binds: the book and the venue's collateral.
        assert "spend cap" not in detail, detail
        assert "shard" in detail, detail
        assert "depth" in detail, detail

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

    async def test_the_combo_fee_hedge_still_prices_the_worst_case(
        self, tmp_path, records_only
    ):
        """ADR 0073: a combo's worst case runs through `combo_taker_fee`,
        not `calculate_fee`.

        **Re-pointed 2026-09-08, and the re-pointing was forced rather than
        chosen.** This pinned the hedge through the PER-BET CAP -- a bankroll
        picked so the cap fell strictly between the two fee models, admitting
        one and refusing the other. Joe removed that cap
        (`docs/adr/0112-the-caps-come-off-the-hand-bet-path.md` §1), which
        removed the only observable this test had.

        Its own first draft already recorded why the obvious substitute does
        not work: the models differ by $0.0002 at one contract and
        `worst_case_cost_display` is rounded to cents, so a display assertion
        at one contract stays GREEN with the hedge removed -- a test of a
        guard that cannot see the guard.

        The fix is size, not a softer assertion. At `COMBO_MAX_CONTRACTS` the
        two models differ by ~$0.05, which survives rounding to cents, and the
        removal of the cap is exactly what makes an order that large reachable
        here. The guard is pinned harder than before: the displayed figure must
        equal the hedged answer and must NOT equal the plain one.
        """
        contracts = manual_store.COMBO_MAX_CONTRACTS
        stake = contracts * 450 / 1000
        hedged = combo_taker_fee(450, contracts)
        plain = calculate_fee(450, contracts)
        assert hedged is not None and plain is not None
        assert f"${stake + plain:.2f}" != f"${stake + hedged:.2f}", (
            "at this size the two fee models round to the same cents; this "
            "test cannot see the guard it exists to pin"
        )
        # Shard 1 funded well past the $112.50 this order costs: the point of
        # this test is the FEE MODEL, and a collateral refusal would make it
        # pass for the wrong reason.
        quotes = StubQuotes(
            _payload(ticker=COMBO_TICKER, yes_ask_size=1000.0, exchange_index=1),
            shard_tenths=500_000,
        )
        app = _app(_base_db(tmp_path, balance_tenths=5_000_000), quotes=quotes)
        response = await post(
            app, "/api/manual-orders",
            json=_body(
                ticker=COMBO_TICKER,
                contracts=contracts,
                combo_acknowledged=True,
            ),
            headers=AUTH,
        )
        assert response.status_code == 200, response.json()
        display = response.json()["worst_case_cost_display"]
        assert display == f"${stake + hedged:.2f}", display
        assert display != f"${stake + plain:.2f}", (
            "the combo was priced through calculate_fee, which undercharged "
            "four of the eight combo fills on the record (ADR 0073)"
        )

    async def test_the_spend_ceiling_no_longer_binds(
        self, tmp_path, records_only
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

        **Re-pointed again 2026-09-08, and this time the property does NOT
        survive: it was removed on purpose.** Joe: "remove the cap. i will
        decide." Both money ceilings are gone -- the $3.00 spend cap and the
        balance-derived one -- see
        `docs/adr/0112-the-caps-come-off-the-hand-bet-path.md` §1 and §4.

        The assertion is inverted rather than deleted so that a restored cap
        fails loudly. A deleted test would let a future session put the brake
        back silently, and ADR §5 reserves that to Joe.
        """
        # $3,000 balance. This order costs ~$9 -- comfortably over BOTH the
        # old $3.00 spend cap and, at a smaller balance, the derived one. It
        # must now go through.
        app = _app(_base_db(tmp_path, balance_tenths=3_000_000))
        response = await post(
            app, "/api/manual-orders", json=_body(contracts=20), headers=AUTH,
        )
        assert response.status_code == 200, response.json()
        body = response.json()
        assert body["contracts"] == 20
        # And no refusal may name either dead ceiling.
        rendered = json.dumps(body)
        assert "cap this path is set to" not in rendered
        assert "per-bet cap" not in rendered

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

    async def test_a_stale_mirror_no_longer_refuses_now_that_nothing_acts_on_it(
        self, tmp_path, records_only
    ):
        """**Inverted 2026-09-08, and the ADR 0064 rule it tested is intact.**

        This refused when today's realised P&L could not be read, on the rule
        that "cannot read the losses" must never resolve to "no losses". That
        refusal existed to protect the daily-loss KILL SWITCH -- its own
        message said so, "so the daily-loss switch cannot be applied". Joe
        removed the switch, so the refusal guarded nothing and would have
        blocked a bet on the strength of a bound that no longer exists.

        **What ADR 0064 forbids is still forbidden, and is pinned below:** the
        unreadable figure is reported as `None`, never coerced to `0.0`, which
        would render as "no losses today" on a screen he reads.
        """
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
        assert response.status_code == 200, response.json()
        assert response.json()["venue_daily_pnl_dollars"] is None

    async def test_an_unobserved_balance_no_longer_refuses(
        self, tmp_path, records_only
    ):
        """**Inverted 2026-09-08 (ADR 0112 Amendment 1).**

        Every cap this precondition existed for is gone -- the per-bet cap and
        daily-loss line under ADR 0112, and the total-exposure ceiling when Joe
        removed the last brake: "remove the exposure ceiling too."

        Refusing on a precondition for nothing is how a removed cap comes back
        by accident, so it does not refuse. The bet must go through with the
        balance never observed.
        """
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
        assert response.status_code == 200, response.json()

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

    async def test_the_per_bet_cap_no_longer_binds_on_the_worst_case(
        self, tmp_path, records_only
    ):
        """**Inverted 2026-09-08. This is the headline of Joe's instruction.**

        It asserted a $4 balance produced a $0.40 per-bet cap that refused one
        contract at 45c ($0.4674 fee-inclusive). He removed that ceiling in
        those words -- "remove the cap. i will decide" -- and reaffirmed it
        after being shown that the daily-loss switch was the same number and
        would close the desk on his first losing bet over it. See
        `docs/adr/0112-the-caps-come-off-the-hand-bet-path.md` §1, §4.

        The same setup is kept exactly, and only the expectation is reversed,
        so this test still exercises the arithmetic that used to bind: a
        balance so small the old cap was $0.40, against an order worth more
        than that. **A bet over the old cap must now go through.**
        """
        app = _app(_base_db(tmp_path, balance_tenths=4000))
        response = await post(
            app, "/api/manual-orders", json=_body(), headers=AUTH,
        )
        assert response.status_code == 200, response.json()
        assert "per-bet cap" not in json.dumps(response.json())

    async def test_no_ceiling_of_ours_bounds_a_hand_bet_any_more(
        self, tmp_path, records_only
    ):
        """**Written and then inverted the same day, which is the point.**

        Hours earlier this pinned the OPPOSITE: the total-exposure ceiling as
        "the one he did not remove", surviving ADR 0112 precisely because he
        had not been asked about it. He was then asked, and said: "remove the
        exposure ceiling too." ADR 0112 Amendment 1.

        So the whole class is gone -- per-bet cap, daily-loss switch,
        cool-off, exposure ceiling. This asserts the class is empty rather
        than asserting any one removal, because that is the property ADR 0112
        §5 reserves to Joe and the one a future session is most likely to
        breach by restoring "just one".

        A balance that has NEVER been observed is used deliberately: it is the
        state in which every derived ceiling is `None`, and under the old rules
        it refused outright.
        """
        path = tmp_path / "no-balance.db"
        conn = db.init_db(path)
        conn.commit()
        conn.close()
        app = _app(path)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 200, response.json()
        rendered = json.dumps(response.json())
        for dead in ("per-bet cap", "exposure ceiling", "daily-loss switch",
                     "cap this path is set to"):
            assert dead not in rendered, f"{dead!r} came back: {rendered}"
        assert response.json()["cooloff_until_ms"] is None

    async def test_holding_the_ticker_refuses_the_buy(self, tmp_path):
        """Kalshi nets; a buy that closes a position must not book an open.

        The row is the shape observed 2026-08-30: `position_fp`, a
        fixed-point string, fractional. The old fixture said `"position":
        "1"` — a field name that has never been seen on the wire.
        """
        quotes = StubQuotes(
            positions=[{"ticker": TICKER, "position_fp": "22.88"}]
        )
        app = _app(_base_db(tmp_path), quotes=quotes)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 422
        assert "nets" in response.json()["detail"]

    async def test_a_short_position_refuses_the_buy_too(self, tmp_path):
        """`position_fp` is signed — negative is a NO-side holding, and a YES
        buy against it is exactly the netting the guard exists to catch."""
        quotes = StubQuotes(
            positions=[{"ticker": TICKER, "position_fp": "-3.00"}]
        )
        app = _app(_base_db(tmp_path), quotes=quotes)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 422
        assert "nets" in response.json()["detail"]

    async def test_an_exited_market_no_longer_refuses_the_buy(
        self, tmp_path, records_only
    ):
        """Observed 2026-08-30: the bare endpoint returns `position_fp:
        '0.00'` rows for markets already exited. Until this date the guard
        compared ticker alone, so re-entering a market Joe had exited was
        refused as if he still held it — a false refusal on the desk's core
        function. The venue's zero is 'no position', and the bet proceeds.
        """
        quotes = StubQuotes(
            positions=[{"ticker": TICKER, "position_fp": "0.00"}]
        )
        app = _app(_base_db(tmp_path), quotes=quotes)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 200, response.text

    async def test_a_matching_row_with_an_unparseable_quantity_refuses(
        self, tmp_path
    ):
        """Unreadable resolves to a refusal, never to zero — a quantity that
        will not parse must not read as 'no position here'."""
        quotes = StubQuotes(
            positions=[{"ticker": TICKER, "position_fp": "not a number"}]
        )
        app = _app(_base_db(tmp_path), quotes=quotes)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 422
        assert "cannot be verified" in response.json()["detail"]

    async def test_an_unreadable_position_row_refuses_too(self, tmp_path):
        """A row that cannot name its ticker cannot prove it is not this
        one."""
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


class TestTheLivePositionsReadIsStamped:
    """Step 10's live read lands in `poll_log` (2026-08-29).

    The route already asked the venue for positions on every attempted bet
    and threw the observation away, so the open-positions count claimed to
    be older than the newest read actually taken. The stamp is honest by the
    table's own definition -- the venue WAS asked -- and is written through
    the poller's own `log_poll_attempt` under the same 'positions' endpoint
    name, so there is one population and not two.

    What the stamp does NOT establish, asserted here so it stays true: it is
    pre-order (its row_count cannot include the bet being placed) and it
    fires only on a tap -- it supplements `portfolio_poll.poll_positions`
    and can never substitute for it, because a night with no bets writes
    nothing here.
    """

    async def test_a_dry_run_bet_stamps_the_read_it_took(
        self, tmp_path, records_only
    ):
        path = _base_db(tmp_path)
        app = _app(path)
        response = await post(
            app, "/api/manual-orders", json=_body(), headers=AUTH
        )
        assert response.status_code == 200, response.text
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT ok, row_count FROM poll_log WHERE endpoint = 'positions'"
        ).fetchall()
        conn.close()
        assert [(r["ok"], r["row_count"]) for r in rows] == [(1, 0)], (
            "one successful stamp for the one live read the route took; "
            "the stub held no positions, so the pre-order count is 0"
        )

    async def test_a_failed_read_is_stamped_as_a_failure(self, tmp_path):
        """Matching the poller's convention: a failure that writes nothing
        is invisible and reads like a quiet evening. The 503 the route
        already returned is unchanged."""
        quotes = StubQuotes(positions_error=QuoteUnavailable("no answer"))
        path = _base_db(tmp_path)
        app = _app(path, quotes=quotes)
        response = await post(
            app, "/api/manual-orders", json=_body(), headers=AUTH
        )
        assert response.status_code == 503
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT ok, row_count, error FROM poll_log "
            "WHERE endpoint = 'positions'"
        ).fetchone()
        conn.close()
        assert row is not None, "the venue was asked; the attempt must land"
        assert row["ok"] == 0
        assert row["row_count"] is None
        assert "no answer" in row["error"]

    async def test_the_route_keeps_the_rows_it_read_and_marks_the_stamp(
        self, tmp_path, records_only
    ):
        """ADR 0107 section 9, the integrator's edit: the hand-bet path's read
        feeds the money figure instead of being counted and thrown away.

        `poll_log` has two writers of positions reads and until 2026-09-05
        only the poller kept rows, so a reader taking the newest successful
        poll found this route's stamp with `row_count = 1` and nothing under
        it, and refused the staked figure for up to five minutes after every
        hand bet. Asserted together on purpose: the row landing in
        `venue_positions` under THIS stamp's id, and `mirrored = 1` on the
        stamp -- either alone can pass while the pair is broken."""
        quotes = StubQuotes(positions=[dict(OBSERVED_POSITION_ROW)])
        path = _base_db(tmp_path)
        app = _app(path, quotes=quotes)
        response = await post(
            app, "/api/manual-orders", json=_body(), headers=AUTH
        )
        assert response.status_code == 200, response.text
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        stamp = conn.execute(
            "SELECT id, ok, row_count, mirrored FROM poll_log "
            "WHERE endpoint = 'positions'"
        ).fetchone()
        kept = conn.execute(
            "SELECT poll_log_id, ticker, contracts, side FROM venue_positions"
        ).fetchall()
        conn.close()
        assert (stamp["ok"], stamp["row_count"]) == (1, 1)
        assert stamp["mirrored"] == 1, (
            "the stamp must say it kept its rows, or `bets.open_positions` "
            "cannot tell it apart from the bare stamp this route used to write"
        )
        assert [r["poll_log_id"] for r in kept] == [stamp["id"]], (
            "the mirrored rows must hang off THIS read, not a poller's"
        )
        assert kept[0]["ticker"] == OBSERVED_POSITION_ROW["ticker"]
        assert kept[0]["side"] == "yes"

    async def test_an_empty_account_is_kept_as_marked_and_empty(
        self, tmp_path, records_only
    ):
        """`rows=[]` is the venue saying the account holds nothing -- a real
        observation, stored as a marked snapshot with zero rows. It is not the
        same state as a stamp that kept nothing, and no count can tell them
        apart, which is why the marker rather than a count carries it."""
        path = _base_db(tmp_path)
        app = _app(path)  # the default stub holds no positions
        response = await post(
            app, "/api/manual-orders", json=_body(), headers=AUTH
        )
        assert response.status_code == 200, response.text
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        stamp = conn.execute(
            "SELECT id, row_count, mirrored FROM poll_log "
            "WHERE endpoint = 'positions'"
        ).fetchone()
        kept = conn.execute("SELECT COUNT(*) FROM venue_positions").fetchone()[0]
        conn.close()
        assert stamp["row_count"] == 0
        assert stamp["mirrored"] == 1
        assert kept == 0

    async def test_a_failed_read_keeps_nothing_and_is_left_unmarked(
        self, tmp_path
    ):
        """The venue answered with an error, so there is no observation to
        mirror. Marking it would tell the reader rows were kept when none
        were -- the one failure `bets.open_positions` could not detect."""
        quotes = StubQuotes(positions_error=QuoteUnavailable("no answer"))
        path = _base_db(tmp_path)
        app = _app(path, quotes=quotes)
        response = await post(
            app, "/api/manual-orders", json=_body(), headers=AUTH
        )
        assert response.status_code == 503
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        stamp = conn.execute(
            "SELECT ok, mirrored FROM poll_log WHERE endpoint = 'positions'"
        ).fetchone()
        kept = conn.execute("SELECT COUNT(*) FROM venue_positions").fetchone()[0]
        conn.close()
        assert stamp["ok"] == 0
        assert stamp["mirrored"] is None
        assert kept == 0

    async def test_rows_offered_with_a_failed_read_are_still_refused(
        self, tmp_path
    ):
        """The `ok and` half of the mirror guard, pinned directly because the
        route cannot reach it.

        On every failure path the route passes no rows at all, so `rows is
        None` already blocks the write and `ok and` never decides anything --
        a mutation removing it stays green through the API. That makes it
        decoration by this repo's standard unless something tests it, and the
        thing it defends against is a future caller that has rows in hand from
        a read the venue then failed. Called at the function rather than
        through the route, which is the only level the branch is reachable
        from."""
        from backend.api.routes import _stamp_positions_read

        path = _base_db(tmp_path)
        await _stamp_positions_read(
            path,
            now_ms=int(time.time() * 1000),
            ok=False,
            error="the venue said no",
            rows=[dict(OBSERVED_POSITION_ROW)],
        )
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        stamp = conn.execute(
            "SELECT ok, mirrored FROM poll_log WHERE endpoint = 'positions'"
        ).fetchone()
        kept = conn.execute("SELECT COUNT(*) FROM venue_positions").fetchone()[0]
        conn.close()
        assert stamp["ok"] == 0
        assert stamp["mirrored"] is None, (
            "a failed read must not be marked as having kept rows, however "
            "many rows the caller offers"
        )
        assert kept == 0

    async def test_a_refusal_before_the_read_stamps_nothing(self, tmp_path):
        """The stamp means 'the venue was asked'. An order refused at an
        earlier guard never asked, so a synthetic row here would be exactly
        the fabrication `odds/sweeplog.py` refuses for `api_credits`."""
        path = _base_db(tmp_path)
        app = _app(path)
        body = _body(max_price_tenths=100)  # under the 650 ask: step 7 refuses
        response = await post(app, "/api/manual-orders", json=body, headers=AUTH)
        assert response.status_code == 422
        conn = sqlite3.connect(path)
        count = conn.execute(
            "SELECT COUNT(*) FROM poll_log WHERE endpoint = 'positions'"
        ).fetchone()[0]
        conn.close()
        assert count == 0


class TestTheReserveIsAtomic:
    def test_an_unreadable_exposure_rolls_the_row_back(self, tmp_path, monkeypatch):
        """**Re-pointed 2026-09-08, and the atomicity guarantee is unchanged.**

        This drove the rollback through the EXPOSURE CAP, which Joe removed
        (ADR 0112 Amendment 1). The insert-then-check-under-BEGIN-IMMEDIATE
        shape is not gone with it: one refusal still stands inside the
        transaction, and it is the one that must -- an exposure figure that
        cannot be READ.

        That is not a cap and did not go with the caps. "Cannot determine the
        budget must never resolve to unlimited" is a rule about reading; an
        unreadable total means a broken write, whatever ceiling does or does
        not apply to it. If this ever leaves a row behind, a half-written
        intent survives a failure and the desk's record of what it sent is
        wrong.
        """
        path = _base_db(tmp_path)
        conn = db.open_db(path)
        grid = read_price_grid(_payload()["market"])
        order = OrderRequest(
            ticker=TICKER, side="yes", action="buy", count=10,
            limit_price_tenths=450, price_grid=grid,
            time_in_force="immediate_or_cancel",
        )
        monkeypatch.setattr(
            manual_store, "current_manual_exposure_dollars",
            lambda *a, **k: None,
        )
        with pytest.raises(manual_store.OrderNotRecorded):
            manual_store.reserve_manual_order(
                conn, order, dry_run=True, submitted_ms=1,
                max_price_tenths=700, idempotency_key="k-00000001",
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
        # No `p_yes_required` flag since 2026-09-09: the ticket asks for no
        # probability and masks nothing, so a flag saying otherwise would be
        # the screen enforcing a rule the route had dropped.
        assert "p_yes_required" not in body
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

    async def test_the_combo_note_carries_the_exit_census_numbers(
        self, tmp_path
    ):
        """The exit half, on the ticket, in the census's own digits.

        Asserted against `parlays.COMBO_EXIT_CENSUS_*` and never against the
        digits, for the reason `backend/parlays.py`'s census block records:
        a test that pins the literal keeps a refuted sentence green.

        **This is the entry claim's neighbour and not the entry claim.** The
        2026-09-06 parlay census refuted "you probably cannot get in" (51 of
        52 combination positions were taker fills); it measured nothing about
        the way out, and ADR 0085 Amendment 1 §A1.4 forbids softening the
        exit sentence on the strength of the entry finding.

        **The exit sentence DID move on 2026-09-10, and not for that
        forbidden reason.** Two `KXMVECROSSCATEGORY-SHARD1` books were read
        that day carrying resting YES bids -- an existence proof, which kills
        the universal "you cannot exit it" outright. §A1.4 bars softening a
        claim that still holds; it does not require repeating a falsified
        one on a real-money surface.

        So this test now pins the REPLACEMENT's load-bearing words with the
        same force. The warning must still be a warning -- it names the size,
        because an exit of ten contracts is the fact that keeps "an exit
        exists" from reading as reassurance -- and it must still claim no
        rate, because Arm D measures that on 2026-09-13 and §11.3 forbids the
        screens implying a frequency before it does.
        """
        quotes = StubQuotes(_payload(ticker=COMBO_TICKER))
        app = _app(_base_db(tmp_path), quotes=quotes)
        body = (await get(app, f"/api/manual/market/{COMBO_TICKER}")).json()
        note = body["combo_note"]
        assert note
        assert str(parlays.COMBO_EXIT_CENSUS_BOOKS_NO_YES_BID) in note
        assert str(parlays.COMBO_EXIT_CENSUS_BOOKS_READ) in note
        assert "no YES" in note
        # The falsifying observation, in the census's own sourcing style.
        assert str(parlays.COMBO_EXIT_SHARD_YES_BID_BOOKS) in note
        assert str(parlays.COMBO_EXIT_SHARD_YES_BID_SIZE_CONTRACTS) in note
        assert parlays.COMBO_EXIT_SHARD_YES_BID_DATE in note
        # The exit claim itself, in words, so the numbers cannot survive the
        # sentence they belong to being softened out from under them. The
        # size and the ignorance are BOTH load-bearing: drop "small" and the
        # note reads as an exit being available, drop "never been measured"
        # and it implies a rate nobody has measured.
        assert "small" in note
        assert "never been measured" in note
        assert "hold it to the outcome" in note
        # And the killed universal must not creep back in any form.
        assert "cannot exit" not in note
        assert "only way out" not in note
        # A single market gets no note at all: the caveat is about
        # combinations, and a caveat everywhere is a caveat nowhere. Its own
        # app, because `StubQuotes` answers every ticker with the payload it
        # was handed -- reusing the combo stub would have read the note off a
        # combination and called it a single market.
        plain = _app(_base_db(tmp_path, name="single.db"))
        single = (await get(plain, f"/api/manual/market/{TICKER}")).json()
        assert single["combo_note"] is None

    def test_no_census_number_in_the_combo_note_is_typed_rather_than_sourced(
        self,
    ):
        """The note's digits come from the constants, or the guard is theatre.

        The assertion above reads `str(COMBO_EXIT_CENSUS_BOOKS_READ) in note`,
        which passes just as happily on a **typed** "40" as on a sourced one
        -- and a typed "40 of 40" is exactly how the refuted entry sentence
        survived a green suite for eleven days. This reads the source of the
        f-string instead and refuses any bare integer in it.

        Follows `tests/test_parlays_api.py::
        test_no_census_number_in_the_note_is_typed_rather_than_sourced`.

        Mutation observed red: replace `{COMBO_EXIT_CENSUS_BOOKS_READ}` with a
        literal `40` in `backend/api/routes.py`.
        """
        tree = ast.parse((REPO / "backend" / "api" / "routes.py").read_text(
            encoding="utf-8"
        ))
        note = next(
            # `<string> if _is_combo(...) else None` -- the string branch is
            # what reaches the ticket; the condition carries no census number.
            value.body if isinstance(value, ast.IfExp) else value
            for node in ast.walk(tree)
            if isinstance(node, ast.Dict)
            for key, value in zip(node.keys, node.values)
            if getattr(key, "value", None) == "combo_note"
        )
        rendered = ast.unparse(note)
        digits = [ch for ch in rendered if ch.isdigit()]
        assert not digits, f"a census number is typed into the note: {rendered}"
        # And the names are actually the census's, not some other integer
        # dressed up as one.
        names = {
            n.id for n in ast.walk(note) if isinstance(n, ast.Name)
        }
        assert "COMBO_EXIT_CENSUS_BOOKS_NO_YES_BID" in names
        assert "COMBO_EXIT_CENSUS_BOOKS_READ" in names


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


class TestACombinationCarriesTheConsensusTheDeskComputed:
    """A `KXMVE` combination HAS a devigged consensus, and now records it.

    This class used to be `TestACombinationHasNoConsensusAndSaysSo` and it
    asserted the defect. The true half of that name is still true --
    `kalshi/discovery.JUNK_PREFIX` drops the prefix, so no `kalshi_markets`
    row and no `recommendations` row can ever exist for a combination -- but
    the conclusion drawn from it was wrong. `parlays.price_card_on_kalshi`
    writes `parlay_lookups.fair_joint_conservative`, the joint of each leg's
    `p_conservative` off the same worst-of-four devig, and `PriceOnKalshi.tsx`
    renders it one component above the buy button. Four real combination bets
    were placed against a number on the screen and recorded as though no such
    number existed.

    The tests are inverted rather than deleted (`tasks/lessons.md`,
    2026-09-09): a deleted test leaves no evidence the question was settled.
    Zero is still never written -- an unreadable joint refuses, exactly as an
    unreadable `fair_probability` does.
    """

    async def test_a_combination_records_the_fair_value_the_screen_showed(
        self, tmp_path, records_only
    ):
        """Mutation observed red: restore `return _absent(ABSENT_COMBO)` in
        `_read_consensus`'s combination branch."""
        path = _base_db(tmp_path)
        _seed_parlay_lookup(path)
        app = _app(path, quotes=StubQuotes(_payload(ticker=COMBO_TICKER)))
        body = _body(
            ticker=COMBO_TICKER, combo_acknowledged=True, max_price_tenths=700
        )
        response = await post(app, "/api/manual-orders", json=body, headers=AUTH)
        assert response.status_code == 200, response.text

        row = _manual_row(path)
        # 0.33862 -> 339 tenths of a cent. Integer, on the same 0-1000 scale
        # as `limit_price_tenths` -- never float dollars, and never the ratio.
        assert row["consensus_fair_tenths"] == 339
        assert isinstance(row["consensus_fair_tenths"], int)
        assert row["consensus_computed_ms"] == 1_700_000_002_000
        assert row["consensus_absent_reason"] is None

    async def test_the_recorded_fair_value_reproduces_the_hold_he_was_shown(
        self, tmp_path, records_only
    ):
        """The claim is that this is the SAME number, not a parallel one.

        `hold = 1 - fair x offered_decimal`, so the fair value written here,
        put back against the ask the lookup was priced at, has to return the
        hold `parlay_lookups` stored -- to within the tenth of a cent that
        rounding to the money scale costs. If it did not, the row would be
        recording some other quantity under a name that promises this one.

        Mutation observed red: source `fair_tenths` from `row["hold"]`
        instead of `row["fair_joint_conservative"]`.
        """
        path = _base_db(tmp_path)
        _seed_parlay_lookup(path)
        app = _app(path, quotes=StubQuotes(_payload(ticker=COMBO_TICKER)))
        body = _body(
            ticker=COMBO_TICKER, combo_acknowledged=True, max_price_tenths=700
        )
        assert (
            await post(app, "/api/manual-orders", json=body, headers=AUTH)
        ).status_code == 200

        fair_tenths = _manual_row(path)["consensus_fair_tenths"]
        reconstructed = 1.0 - fair_tenths / LIVE_LOOKUP_ASK_TENTHS
        assert abs(reconstructed - LIVE_LOOKUP_HOLD) < 0.0025, (
            f"the recorded fair value implies a hold of {reconstructed:.4f}, "
            f"but the desk showed {LIVE_LOOKUP_HOLD:.4f}"
        )

    async def test_a_combination_the_desk_never_priced_records_that_and_not_zero(
        self, tmp_path, records_only
    ):
        """He can buy a combination built in the Kalshi app.

        There is then no `priced` lookup, no fair value, and the row says
        which absence it was -- `combo_no_priced_lookup`, never a zero and
        never `combo_ticker`, which meant "we did not look".
        """
        path = _base_db(tmp_path)
        app = _app(path, quotes=StubQuotes(_payload(ticker=COMBO_TICKER)))
        body = _body(
            ticker=COMBO_TICKER, combo_acknowledged=True, max_price_tenths=700
        )
        assert (
            await post(app, "/api/manual-orders", json=body, headers=AUTH)
        ).status_code == 200

        row = _manual_row(path)
        for column in SNAPSHOT_COLUMNS:
            assert row[column] is None, f"{column} is {row[column]!r}, not NULL"
            assert row[column] != 0
        assert (
            row["consensus_absent_reason"]
            == manual_store.ABSENT_COMBO_NO_PRICED_LOOKUP
        )

    async def test_an_unpriced_lookup_is_not_mistaken_for_a_priced_one(
        self, tmp_path, records_only
    ):
        """A `book_empty` lookup carries a joint but no ask and no hold.

        It minted the ticker and it computed the fair value, so a query that
        dropped `status = 'priced'` would find it -- and would record a
        consensus for a market nobody was offering to sell. `priced_lookup_for`
        is the one that decides, and this pins that the combination branch
        goes through it.

        Mutation observed red: drop `AND status = 'priced'` from
        `parlays.priced_lookup_for`.
        """
        path = _base_db(tmp_path)
        _seed_parlay_lookup(
            path, status="book_empty", ask_tenths=None, hold=None,
        )
        app = _app(path, quotes=StubQuotes(_payload(ticker=COMBO_TICKER)))
        body = _body(
            ticker=COMBO_TICKER, combo_acknowledged=True, max_price_tenths=700
        )
        assert (
            await post(app, "/api/manual-orders", json=body, headers=AUTH)
        ).status_code == 200

        row = _manual_row(path)
        assert row["consensus_fair_tenths"] is None
        assert (
            row["consensus_absent_reason"]
            == manual_store.ABSENT_COMBO_NO_PRICED_LOOKUP
        )

    async def test_the_freshest_priced_lookup_wins(self, tmp_path, records_only):
        """Rows 39 and 40 on live share one `minted_market_ticker`.

        A card can be looked up repeatedly and re-mint the same market, so the
        joint is not unique to the ticker and the most recent priced row is
        the one he was looking at.

        Mutation observed red: `ORDER BY requested_ms ASC` in
        `parlays.priced_lookup_for`.
        """
        path = _base_db(tmp_path)
        _seed_parlay_lookup(path, fair_joint=0.200, requested_ms=1_000)
        _seed_parlay_lookup(path, fair_joint=0.700, requested_ms=2_000)
        app = _app(path, quotes=StubQuotes(_payload(ticker=COMBO_TICKER)))
        body = _body(
            ticker=COMBO_TICKER, combo_acknowledged=True, max_price_tenths=700
        )
        assert (
            await post(app, "/api/manual-orders", json=body, headers=AUTH)
        ).status_code == 200
        assert _manual_row(path)["consensus_fair_tenths"] == 700

    async def test_a_no_side_combination_refuses_rather_than_complementing(
        self, tmp_path, records_only
    ):
        """`1 - joint` is not the conservative devig for the NO side.

        Worst-of-four is conservative in the direction it was taken, so its
        complement is ANTI-conservative -- rule 2 inside out, and an
        optimistic number on a money row. The lookup prices YES only; a NO bet
        records the absence and names it.

        Mutation observed red: drop the `side != "yes"` branch -- the NO row
        then records 339, the YES fair value, for a bet on the other side.
        """
        path = _base_db(tmp_path)
        _seed_parlay_lookup(path)
        app = _app(path, quotes=StubQuotes(_payload(ticker=COMBO_TICKER)))
        body = _body(
            ticker=COMBO_TICKER, side="no", combo_acknowledged=True,
            max_price_tenths=700,
        )
        assert (
            await post(app, "/api/manual-orders", json=body, headers=AUTH)
        ).status_code == 200

        row = _manual_row(path)
        assert row["side"] == "no"
        assert row["consensus_fair_tenths"] is None
        assert (
            row["consensus_absent_reason"]
            == manual_store.ABSENT_COMBO_SIDE_NOT_PRICED
        )

    def test_an_unreadable_joint_refuses_rather_than_clamping(self):
        """Same guard as its single-market twin, on the combination's source.

        `probability_to_tenths` clamps, so a joint of 1.5 would be written as
        1000 tenths -- a settled outcome recorded as a live consensus.

        Mutation observed red: return `probability_to_tenths(...)` from
        `_read_combo_consensus` without going through `_fair_tenths`.
        """
        class OneRow:
            def __init__(self, row):
                self._row = row

            def execute(self, *args, **kwargs):
                return self

            def fetchone(self):
                return self._row

        snapshot = manual_store._read_combo_consensus(
            OneRow({"fair_joint_conservative": 1.5, "requested_ms": 1}),
            ticker=COMBO_TICKER, side="yes",
        )
        assert snapshot.fair_tenths is None
        assert (
            snapshot.absent_reason
            == manual_store.ABSENT_COMBO_UNREADABLE_FAIR_VALUE
        )

    def test_combo_ticker_is_a_closed_historical_set(self):
        """The reason code stops meaning two things.

        `combo_ticker` meant "this is a combination, we did not try", and it
        is the value on all four real combination bets. Every combination row
        written from here on says what the desk FOUND -- a fair value, or one
        of the three combination absences. If any code path could still write
        `combo_ticker`, the four historical rows would be indistinguishable
        from new ones and the column would be a NULL with extra steps.

        Read off the AST rather than the text, so the constant may still be
        DEFINED and explained in prose -- which it is, and must be, because
        the rows carrying it have to keep their meaning.

        Mutation observed red: put `_absent(ABSENT_COMBO)` back in
        `_read_consensus`.
        """
        source = (
            REPO / "backend" / "store" / "manual_orders.py"
        ).read_text(encoding="utf-8")
        writes = [
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_absent"
            and any(
                isinstance(arg, ast.Name) and arg.id == "ABSENT_COMBO"
                for arg in node.args
            )
        ]
        assert writes == [], (
            "something still writes consensus_absent_reason = 'combo_ticker'; "
            "that value means 'the desk never looked' and no row written "
            "since the combination consensus landed can honestly say so"
        )
        assert manual_store.ABSENT_COMBO == "combo_ticker", (
            "the historical value was renamed; the four live rows carrying it "
            "would stop being interpretable"
        )

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


class TestTheConsensusStampSurvivedTheDedupe:
    """What `consensus_computed_ms` means now that v36 confirms in place.

    ADR 0133 stopped `write_fair_price` reinserting an unchanged consensus, so
    `fair_prices.computed_ms` freezes at the instant a value FIRST appeared and
    `confirmed_ms` carries the last time it was re-derived. `_read_consensus`
    selects `COALESCE(f.confirmed_ms, f.computed_ms)`, mirroring
    `backend/parlays.py::_live_age_ms`'s own COALESCE, so the gap it records
    is "how long since this consensus was last computed OR reconfirmed" --
    never staler than the freshest confirm.

    **Neither reading is pinned by the schema, so it is pinned here.** These
    tests fail if the coalesce regresses to the frozen `computed_ms` alone.
    """

    def _confirm(self, path, fair_id, *, confirmed_ms, book_age_ms=None):
        """Age a seeded row the way a confirming pass would: value untouched."""
        conn = db.open_db(path)
        try:
            conn.execute(
                "UPDATE fair_prices SET confirmed_ms = ?, "
                "confirmed_oldest_book_age_ms = ? WHERE id = ?",
                (confirmed_ms, book_age_ms, fair_id),
            )
            conn.commit()
        finally:
            conn.close()

    def test_the_consensus_stamp_reads_the_confirm_when_one_exists(
        self, tmp_path
    ):
        """The recorded stamp is the confirm, when a confirm is newer.

        Mutation observed red: change `COALESCE(f.confirmed_ms,
        f.computed_ms)` back to bare `f.computed_ms` in `_read_consensus`'s
        SELECT -- the snapshot then reports the frozen first-seen stamp and
        this assertion fails.

        The two stamps are an hour apart on purpose. A consensus that has held
        an hour is exactly the case where the readings diverge enough to change
        what a reader concludes, and it is the common case rather than a corner
        one: 344 of 494 live keys changed zero times across four hours.
        """
        path = _base_db(tmp_path)
        first_seen = 1_700_000_000_000
        confirmed = first_seen + 3_600_000
        fair_id, _ = _seed_consensus(path, computed_ms=first_seen)
        self._confirm(path, fair_id, confirmed_ms=confirmed)

        conn = db.open_db(path)
        try:
            snap = manual_store.consensus_snapshot(
                conn, ticker=TICKER, side="yes"
            )
        finally:
            conn.close()

        assert snap.computed_ms == confirmed, (
            "the snapshot must record when this consensus was last computed "
            "OR reconfirmed (ADR 0133); a frozen first-seen stamp here "
            "understates recency for any consensus that has held a while"
        )
        assert snap.fair_price_id == fair_id

    def test_a_row_that_was_never_reconfirmed_falls_back_to_computed_ms(
        self, tmp_path
    ):
        """The v36 columns are nullable, so the COALESCE falls back for them.

        This is the whole live table on the day v36 deployed, so a snapshot
        that needed `confirmed_ms` to be present would have reported nothing
        for every historical row.
        """
        path = _base_db(tmp_path)
        first_seen = 1_700_000_000_000
        fair_id, _ = _seed_consensus(path, computed_ms=first_seen)

        conn = db.open_db(path)
        try:
            row = conn.execute(
                "SELECT confirmed_ms, confirmed_oldest_book_age_ms "
                "FROM fair_prices WHERE id = ?",
                (fair_id,),
            ).fetchone()
            snap = manual_store.consensus_snapshot(
                conn, ticker=TICKER, side="yes"
            )
        finally:
            conn.close()

        assert row["confirmed_ms"] is None
        assert row["confirmed_oldest_book_age_ms"] is None
        assert snap.computed_ms == first_seen, (
            "with no confirm recorded, the COALESCE must fall back to the "
            "frozen computed_ms rather than reporting nothing"
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


class TestTheTicketAsksForNoProbability:
    """**Inverted 2026-09-09 on Joe's instruction, not deleted.**

    This class was `TestTheTicketAsksBeforeItShows` and pinned ADR 0065's
    client half: an estimate step that renders no ask, and a market read that
    cannot run until a probability is typed. Joe removed the field, so what is
    pinned now is the opposite claim -- there is no estimate step, no
    probability state and nothing between the open affordance and the live
    book. Reversed rather than dropped so a future session restoring the gate
    goes red instead of finding a silence.

    (The auth pin below is unchanged: removing a data-collection field must
    not remove a credential.)
    """

    TICKET = REPO / "frontend" / "src" / "components" / "ManualTicket.tsx"

    def _without_comments(self, source: str) -> str:
        """Source with comments stripped, so a pin on what the ticket DOES is
        neither satisfied nor defeated by prose about what it used to do --
        and this component's header is now three paragraphs of exactly that.
        """
        source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        return re.sub(r"//[^\n]*", "", source)

    def test_no_probability_is_typed_anywhere_in_the_ticket(self):
        """Mutation observed red: restore the `pYesBp` state and its input."""
        source = self._without_comments(
            self.TICKET.read_text(encoding="utf-8")
        )
        for banned in ("p_yes_bp", "pYesBp", "percentToBp", "P(YES)"):
            assert banned not in source, (
                f"`{banned}` is back in the ticket; Joe removed the "
                f"probability entry 2026-09-09 (ADR "
                f"ADR 0131)"
            )

    def test_opening_the_ticket_reads_the_book_with_nothing_in_between(self):
        """The inverse of the pin this replaces, which required the market
        read to come after a typed estimate.

        Mutation observed red: reintroduce an `estimate` phase between the
        open affordance and `openTicket`.
        """
        source = self._without_comments(
            self.TICKET.read_text(encoding="utf-8")
        )
        assert 'name: "estimate"' not in source, (
            "the estimate phase is back -- the open affordance no longer "
            "reaches the live book directly"
        )
        assert "void openTicket()" in source, (
            "the open affordance no longer opens the ticket"
        )
        opener = source.index("const openTicket")
        assert source.index("fetchManualMarket(") > opener, (
            "the market read left openTicket"
        )

    def test_the_ask_is_not_masked_by_anything(self):
        """The mask was surface-dependent and both wordings are gone with it.

        Mutation observed red: restore either branch of the old ternary.
        """
        source = self._without_comments(
            self.TICKET.read_text(encoding="utf-8")
        )
        for banned in ("priceAlreadyVisible", "already on this screen",
                       "wearing your handwriting"):
            assert banned not in source, (
                f"the masked-ask wording `{banned}` survives a ticket that "
                f"masks nothing"
            )

    def test_the_typed_token_is_gone_and_the_order_goes_through_the_proxy(self):
        """**Inverted 2026-09-08 on Joe's instruction.**

        This asserted the confirm was gated on `token.trim().length > 0` — a
        43-character bearer token retyped from scratch on every order. He
        removed it (`docs/adr/0112-the-caps-come-off-the-hand-bet-path.md`
        §1, answer 3) after being told the part the first framing left out:
        the typed act was the CREDENTIAL, not merely friction, so after this
        a person holding his unlocked phone can bet his money.

        **What is pinned instead is that auth did not simply vanish.** The
        order must post to the same-origin `/manual-order` route handler,
        which proves session by cookie and adds the bearer server-side — the
        pattern `/parlay-bid` already used. If a future change makes the
        browser hold a token again, or posts straight at the backend without
        one, this fails.
        """
        source = self.TICKET.read_text(encoding="utf-8")
        gate = source.index("const canConfirm")
        block = source[gate:source.index("return (", gate)]
        assert "token" not in block, (
            "the confirm is gated on a token again; Joe removed the typed act"
        )
        # No token state, no token input, anywhere in the ticket.
        assert "setToken" not in source
        assert 'type="password"' not in source

        api = (REPO / "frontend" / "src" / "lib" / "api.ts").read_text(
            encoding="utf-8"
        )
        start = api.index("export async function placeManualOrder")
        body = api[start:start + 2000]
        assert '"/manual-order"' in body or "`/manual-order`" in body, (
            "the hand bet must go through the server-side proxy route"
        )
        assert "Authorization" not in body, (
            "the browser is holding a bearer token again"
        )

    def test_the_proxy_route_exists_and_is_named_in_the_middleware(self):
        """Without the middleware entry an unauthenticated POST gets an HTML
        login redirect, which `fetch` reads as success — on the one route that
        spends real money with only a cookie in front of it."""
        route = REPO / "frontend" / "src" / "app" / "manual-order" / "route.ts"
        assert route.exists(), "the hand bet's server-side proxy is missing"
        source = route.read_text(encoding="utf-8")
        assert "backendToken()" in source
        assert '"/api/manual-orders"' in source
        middleware = (REPO / "frontend" / "src" / "middleware.ts").read_text(
            encoding="utf-8"
        )
        # The closing bracket must be searched FROM the set, not from the top
        # of the file: an earlier `]);` made this slice empty and the
        # assertion vacuous in its first draft.
        start = middleware.index("JSON_ROUTE_HANDLERS")
        json_routes = middleware[start : middleware.index("]);", start)]
        assert "/refresh-odds" in json_routes, "the slice missed the set"
        assert '"/manual-order"' in json_routes


class TestARefusalIsARecord:
    """v29 (2026-08-30): every pre-reservation refusal lands in
    `manual_order_refusals`, durably.

    Until then all ~23 refusal branches raised and wrote nothing --
    reservation happens at check 11, so the desk could not say which of its
    own brakes fired on an attempted bet, or with what values. Forensic, not
    analytic: no screen reads the table, and `gate.py` never may (the
    ADR 0063 boundary, pinned below beside the `manual_orders` pin).
    """

    @staticmethod
    def _refusals(path):
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM manual_order_refusals ORDER BY id"
        ).fetchall()
        conn.close()
        return rows

    async def test_a_structural_refusal_writes_the_row_it_shows(self, tmp_path):
        """Check 4, refused before any quote: the row carries the check's
        number and name, the exact detail Joe saw, and NULL -- not 0 -- for
        the ask no quote ever produced."""
        path = _base_db(tmp_path)
        app = _app(path)
        response = await post(
            app, "/api/manual-orders", json=_body(contracts=501), headers=AUTH,
        )
        assert response.status_code == 422
        rows = self._refusals(path)
        assert len(rows) == 1
        row = rows[0]
        assert row["check_number"] == 4
        assert row["check_name"] == "structural_ceilings"
        assert row["http_status"] == 422
        assert row["detail"] == response.json()["detail"]
        assert row["ticker"] == TICKER
        assert row["side"] == "yes"
        assert row["requested_contracts"] == 501
        assert row["idempotency_key"] == "test-key-00000001"
        assert row["ask_tenths"] is None

    async def test_a_netting_refusal_carries_the_live_ask(self, tmp_path):
        """Check 10 fires after the quote, so the row records what the
        market was asking when the brake came on."""
        path = _base_db(tmp_path)
        quotes = StubQuotes(
            positions=[{"ticker": TICKER, "position_fp": "22.88"}]
        )
        app = _app(path, quotes=quotes)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 422
        (row,) = self._refusals(path)
        assert row["check_number"] == 10
        assert row["check_name"] == "netting_guard"
        # _payload(): no_bid 550 tenths -> derived YES ask 450 tenths.
        assert row["ask_tenths"] == 450

    async def test_a_completed_bet_writes_no_refusal_row(
        self, tmp_path, records_only
    ):
        path = _base_db(tmp_path)
        app = _app(path)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 200, response.text
        assert self._refusals(path) == []

    async def test_a_recording_failure_never_converts_the_422(
        self, tmp_path, monkeypatch
    ):
        """The refusal outranks its record: a recorder that blows up entirely
        must leave the 4xx standing, not replace it with a 500."""
        def _boom(*args, **kwargs):
            raise RuntimeError("recorder down")

        monkeypatch.setattr(manual_store, "record_refusal_durably", _boom)
        app = _app(_base_db(tmp_path))
        response = await post(
            app, "/api/manual-orders", json=_body(contracts=501), headers=AUTH,
        )
        assert response.status_code == 422

    def test_an_unwritable_database_falls_back_to_the_journal(self, tmp_path):
        """`record_loop_failure_durably`'s precedent: an append beside the
        database that no lock can refuse, naming what the database refused
        with. Returns 'journal_only' -- never raises."""
        bare = tmp_path / "no-tables.db"
        sqlite3.connect(bare).close()  # a real SQLite file with no schema
        outcome = manual_store.record_refusal_durably(
            bare,
            created_ms=1,
            check_number=3,
            check_name="cooloff",
            http_status=423,
            detail="resting",
        )
        assert outcome == "journal_only"
        journal = tmp_path / "manual_order_refusals.jsonl"
        line = journal.read_text(encoding="utf-8").strip()
        assert '"check_name": "cooloff"' in line
        assert "db_refused_with" in line

    def test_a_writable_database_records(self, tmp_path):
        path = _base_db(tmp_path)
        outcome = manual_store.record_refusal_durably(
            path,
            created_ms=2,
            check_number=10,
            check_name="netting_guard",
            http_status=422,
            detail="held",
            ticker=TICKER,
            side="no",
            ask_tenths=450,
        )
        assert outcome == "recorded"
        (row,) = self._refusals(path)
        assert (row["check_name"], row["side"], row["ask_tenths"]) == (
            "netting_guard", "no", 450,
        )

    def test_gate_py_never_reads_the_refusals_table_either(self):
        """The identical boundary `manual_orders` carries: a refusal must not
        move the live-trading interlock's counter. Substring chosen so a
        future `manual_order_refusals` join cannot hide behind the existing
        `manual_orders` pin, which does not match this table's name."""
        source = (REPO / "backend" / "gate.py").read_text(encoding="utf-8")
        assert "manual_order_refusals" not in source
        assert "refusal" not in source.lower()


class TestTheDeskNamesTheShardBeforeTheVenueRefuses:
    """Check 9a, added 2026-09-08 from Joe's own allocation.

    He read his balances off Kalshi mid-session: **shard 1 (Combos) $22.24,
    shard 0 (Default) $0.00**. Every single-market bet draws on shard 0, so
    each one would have been refused by the VENUE with a bare
    `insufficient_balance` -- which against a $22 account reads as a broken
    cockpit rather than as "your money is in the other pocket". The
    combination path solved this in ADR 0084 and the reasoning was never
    carried across.

    **This is not a reinstated brake.** ADR 0112 removed the desk's own
    ceilings; this refuses only what Kalshi was always going to refuse, one
    round trip earlier and in words naming the fix. Nothing here bounds a bet
    the venue would have accepted.

    WHAT THIS DOES NOT ESTABLISH
    ----------------------------
    - Nothing about whether the venue then accepts the order. Collateral is
      one of its preconditions, not all of them; shard 3 is separately blocked
      by an undocumented `user_not_found` and this check cannot see that.
    - Nothing about the balance being current. It is read live at order time,
      but a fill elsewhere between the read and the send is not excluded.
    """

    async def test_joes_actual_split_refuses_a_single_and_names_the_pocket(
        self, tmp_path
    ):
        """The exact configuration he is in right now."""
        quotes = StubQuotes(_payload(exchange_index=0), shard_tenths=0)
        app = _app(_base_db(tmp_path), quotes=quotes)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "exchange shard 0" in detail, detail
        assert "$0.00" in detail, detail
        # The remedy, and that this is the venue's rule rather than ours.
        assert "kalshi.com/account/exchange-indexes" in detail, detail
        assert "not a cap of yours" in detail, detail
        assert "Nothing was sent" in detail, detail

    async def test_the_funded_combo_shard_goes_through(
        self, tmp_path, records_only
    ):
        """The other half of his split: shard 1 holds $22.24 and combos are
        the path that actually works today."""
        quotes = StubQuotes(
            _payload(ticker=COMBO_TICKER, exchange_index=1), shard_tenths=22_240
        )
        app = _app(_base_db(tmp_path), quotes=quotes)
        response = await post(
            app, "/api/manual-orders",
            json=_body(ticker=COMBO_TICKER, combo_acknowledged=True),
            headers=AUTH,
        )
        assert response.status_code == 200, response.json()

    async def test_the_total_across_shards_cannot_pay_for_it(self, tmp_path):
        """The defect the unscoped balance would reintroduce.

        Measured 2026-08-30: the account read $21.41 in total while the
        combinations shard held $0.01 and a 2c order was refused. A payload
        carrying a fat total and a thin row for THIS shard must refuse.
        """
        quotes = StubQuotes(
            _payload(exchange_index=0),
            balance_payload={
                "balance": "21.4120",
                "balance_breakdown": [
                    {"exchange_index": 0, "balance": "0.0100"},
                    {"exchange_index": 1, "balance": "21.4020"},
                ],
            },
        )
        app = _app(_base_db(tmp_path), quotes=quotes)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 422
        assert "$0.01" in response.json()["detail"]

    async def test_an_unreadable_shard_refuses_and_never_assumes_zero(
        self, tmp_path
    ):
        """A market that does not say which shard it settles on.

        Refusing beats guessing 0: 0 is a real shard, and a wrong guess sends
        an order the venue was always going to reject after he has typed a
        price and confirmed.
        """
        quotes = StubQuotes(_payload(exchange_index=None))
        app = _app(_base_db(tmp_path), quotes=quotes)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "which exchange shard" in detail, detail
        assert "Nothing was sent" in detail, detail

    async def test_an_unreadable_balance_refuses_rather_than_spending(
        self, tmp_path
    ):
        """`None` is not zero and is not "fine": an unparsed payload must not
        resolve to a spendable balance in either direction."""
        quotes = StubQuotes(
            _payload(exchange_index=0), balance_payload={"nothing": "useful"}
        )
        app = _app(_base_db(tmp_path), quotes=quotes)
        response = await post(app, "/api/manual-orders", json=_body(), headers=AUTH)
        assert response.status_code == 502
        assert "could not be read" in response.json()["detail"]

    async def test_the_shard_is_read_off_the_market_not_the_ticker_prefix(self):
        """Kalshi's docs call `exchange_index` the authoritative source of
        truth and say ticker formats move. A prefix heuristic would be a
        second definition that silently rots."""
        source = (REPO / "backend" / "api" / "routes.py").read_text(
            encoding="utf-8"
        )
        start = source.index('name="shard_collateral"')
        block = source[start:start + 1200]
        assert "quote.exchange_index" in block
        assert "KXMVE" not in block, (
            "the shard is being inferred from the ticker prefix"
        )


class TestTheButtonAgreesWithTheRoute:
    """**The brake Joe removed was still on the button.** Added 2026-09-08.

    `ManualTicket.tsx` disables Confirm above `authorised_contracts`, and that
    number was built from `min($3.00 spend cap, 10% of the observed balance)`.
    Joe removed both by name (ADR 0112 and its Amendment 1) and the POST route
    obeyed the same day. The read did not. So the cockpit went on refusing at
    roughly six contracts while the route would have taken two hundred -- on
    the one path that spends real money.

    This is the repo's named failure, *one predicate with two spellings and
    the screen believing the wrong one*, running the other way round. The
    three earlier instances were a screen promising buying that was not
    happening; this one refused betting that was permitted.

    What the count must equal now is what the POST route applies to SIZE and
    nothing else: the structural ceiling (check 4), the depth at the ask
    (check 8) and what the market's shard can pay for (check 9a).
    """

    async def test_no_removed_cap_is_left_in_the_count(self, tmp_path):
        """The regression itself, at the size that exposes it.

        A $50 shard against a 45c ask is 111 contracts of collateral. The
        removed caps would have answered 6 -- `$3.00 / 0.45` -- and that is
        the number the button used to enforce. Verified red by restoring the
        old bound: `authorised = min(authorised, int(3.00 / 0.45))` returns 6
        and this fails.
        """
        app = _app(_base_db(tmp_path))
        body = (await get(app, f"/api/manual/market/{TICKER}")).json()
        yes = body["sides"]["yes"]
        assert yes["ask_tenths"] == 450
        assert yes["authorised_contracts"] == 111, yes
        assert yes["authorised_binding"] == "shard", yes
        # The specific dead numbers, named so a reintroduction is legible in
        # the failure rather than merely being "not 111".
        assert yes["authorised_contracts"] != 6, "the $3.00 spend cap is back"

    async def test_collateral_binds_and_says_so(self, tmp_path):
        """A thin shard is the bound, and the field names which one.

        `_manual_cap_dollars` carried this virtue for the caps it replaced and
        its docstring said why: a refusal that does not say which bound it hit
        sends the reader to fix the wrong thing. Waiting for the book and
        moving money between shards are different remedies.
        """
        quotes = StubQuotes(shard_tenths=4_500)
        app = _app(_base_db(tmp_path), quotes=quotes)
        body = (await get(app, f"/api/manual/market/{TICKER}")).json()
        assert body["sides"]["yes"]["authorised_contracts"] == 10
        assert body["sides"]["yes"]["authorised_binding"] == "shard"

    async def test_an_unreadable_shard_refuses_rather_than_authorising(
        self, tmp_path
    ):
        """Unreadable resolves to a refusal, never to a spendable default.

        POST 502s on this (check 9a), so a ticket that offered a count here
        would offer one the route cannot honour. `None` is what the screen
        renders as a refusal.
        """
        quotes = StubQuotes(balance_payload={"balance_breakdown": "not a list"})
        app = _app(_base_db(tmp_path), quotes=quotes)
        body = (await get(app, f"/api/manual/market/{TICKER}")).json()
        assert body["sides"]["yes"]["authorised_contracts"] is None
        assert body["sides"]["yes"]["authorised_binding"] == "shard_unreadable"

    async def test_a_market_with_no_shard_refuses_rather_than_guessing_zero(
        self, tmp_path
    ):
        """`0` is a real shard, so an absent `exchange_index` is unknown.

        Same rule the POST route applies at check 9a, and the same reason: a
        guessed shard is how a "payable" order dies at the venue after he has
        typed a price and confirmed.
        """
        quotes = StubQuotes(_payload(exchange_index=None))
        app = _app(_base_db(tmp_path), quotes=quotes)
        body = (await get(app, f"/api/manual/market/{TICKER}")).json()
        assert body["sides"]["yes"]["authorised_contracts"] is None
        assert body["sides"]["yes"]["authorised_binding"] == "shard_unreadable"

    async def test_an_unobserved_balance_no_longer_empties_the_ticket(
        self, tmp_path
    ):
        """The read had the same precondition the POST route shed.

        Until 2026-09-08 this returned `None` whenever the account balance had
        never been observed, because every ceiling derived from it. `ebbb809`
        made POST accept exactly that state, which left the screen refusing
        what the server permits -- the mismatch WIDENED by the fix that was
        supposed to close it. The shard's own balance is what pays for a bet
        and it is read from the venue, not from `latest_balance_tenths`.
        """
        path = tmp_path / "nobal-read.db"
        conn = db.init_db(path)
        conn.close()
        app = _app(path)
        body = (await get(app, f"/api/manual/market/{TICKER}")).json()
        assert body["caps"]["derived"] is False
        assert body["sides"]["yes"]["authorised_contracts"] == 111

    async def test_the_count_is_never_more_than_the_route_would_take(
        self, tmp_path, records_only
    ):
        """The agreement property, driven through both surfaces.

        This is the assertion that would have caught the original defect from
        either direction, and it is the reason the two are computed from the
        same three bounds rather than merely reconciled once by hand.
        """
        quotes = StubQuotes(shard_tenths=4_500)
        app = _app(_base_db(tmp_path), quotes=quotes)
        body = (await get(app, f"/api/manual/market/{TICKER}")).json()
        authorised = body["sides"]["yes"]["authorised_contracts"]

        ok = await post(
            app, "/api/manual-orders",
            json=_body(contracts=authorised), headers=AUTH,
        )
        assert ok.status_code == 200, ok.json()

        over = await post(
            app, "/api/manual-orders",
            json=_body(contracts=authorised + 1, idempotency_key="k-00000002"),
            headers=AUTH,
        )
        assert over.status_code == 422, over.json()
        assert "shard" in over.json()["detail"]

    async def test_depth_binds_when_it_is_the_thinnest_bound(self, tmp_path):
        """An IOC for more than the book holds part-fills at best (check 8)."""
        quotes = StubQuotes(_payload(yes_ask_size=7.0))
        app = _app(_base_db(tmp_path), quotes=quotes)
        body = (await get(app, f"/api/manual/market/{TICKER}")).json()
        assert body["sides"]["yes"]["authorised_contracts"] == 7
        assert body["sides"]["yes"]["authorised_binding"] == "depth"
        # The OTHER side is untouched by that book change and is still bound
        # by collateral, which is what makes this a depth test rather than a
        # test that any thin number propagates everywhere.
        assert body["sides"]["no"]["authorised_binding"] == "shard"
