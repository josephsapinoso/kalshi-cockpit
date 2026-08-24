"""`POST /api/parlays/lookup` — "Price on Kalshi" (ADR 0070, Slice C).

What these tests establish: the endpoint is auth-gated; a drifted card is
refused before anything touches the exchange; the minted market's ticker is
read from the CAPTURED lookup response shape (`market_ticker` top-level,
`tests/fixtures/combo_lookup_response.json`, taken live 2026-08-23 — the
first lookup this repo ever spent); the quoted cost is derived from the
ORDER BOOK as `1000 − best resting NO bid`, never the list row; an empty
book (the captured reality of a freshly minted combo) is an honest refusal;
and every outcome — priced, empty, no-collection, error — writes a
`parlay_lookups` row.

What they do not establish: what a POPULATED combo book looks like on the
wire — none has ever been captured; the populated-book test builds levels in
the `orderbook_fp` envelope the capture and `kalshi/orderbook.py`'s own
fixtures pin. Nor anything about combo fees (ADR 0046: unverified, and no EV
is computed here).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

import backend.parlays as parlays
from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db as store
from backend.store.db import now_ms

FIXTURES = Path(__file__).parent / "fixtures"
CAPTURED_RESPONSE = json.loads(
    (FIXTURES / "combo_lookup_response.json").read_text(encoding="utf-8")
)
# `KalshiRestClient.orderbook` validates the `orderbook_fp` envelope and
# returns the INNER book — the fakes below stand in for that client, so they
# unwrap the captured payload exactly as it does.
CAPTURED_EMPTY_BOOK = json.loads(
    (FIXTURES / "combo_lookup_orderbook.json").read_text(encoding="utf-8")
)["orderbook_fp"]

HEADERS = {"Authorization": "Bearer secret-token"}


def seed_game(conn, *, game, team, other, p, computed_ms):
    event_ticker = f"KXMLBGAME-{game}"
    ticker = f"{event_ticker}-{team[:6].upper().replace(' ', '')}"
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events (event_ticker, title, "
        "first_seen_ms, last_seen_ms) VALUES (?, ?, 0, 0)",
        (event_ticker, f"{other} at {team}"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, "
        "yes_side_team, market_type, status, first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, ?, 'moneyline', 'active', 0, 0)",
        (ticker, event_ticker, team),
    )
    conn.execute(
        "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, "
        "odds_event_id, league, method, commence_skew_ms, linked_ms) "
        "VALUES (?, ?, 'baseball_mlb', 'exact_alias_pair', 0, 0)",
        (event_ticker, game),
    )
    link_id = conn.execute(
        "SELECT id FROM event_links WHERE kalshi_event_ticker = ?",
        (event_ticker,),
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
        "commence_ms, home_team, away_team, bookmaker, market, outcome_name, "
        "price_decimal) VALUES (?, 'baseball_mlb', ?, ?, ?, ?, 'pinnacle', "
        "'h2h', ?, 1.6)",
        (computed_ms, game, now_ms() + 3_600_000, team, other, team),
    )
    for outcome, prob in ((team, p), (other, 1 - p - 0.02)):
        conn.execute(
            "INSERT INTO fair_prices (computed_ms, link_id, market, "
            "outcome_name, p_multiplicative, p_additive, p_power, p_shin, "
            "p_conservative, book_count, books_used, anchored_on_sharp, "
            "oldest_book_age_ms) "
            "VALUES (?, ?, 'h2h', ?, ?, ?, ?, ?, ?, 3, '[]', 1, 5000)",
            (computed_ms, link_id, outcome,
             prob + 0.02, prob + 0.01, prob + 0.015, prob + 0.005, prob),
        )


class FakeCollections:
    """The smallest shape `_choose_collection` reads."""

    def __init__(self, tickers):
        from backend.kalshi.combos import ComboScope

        self.collection_ticker = "KXMVESPORTSMULTIGAMEEXTENDED-R"
        self.scope = ComboScope.MULTI_GAME
        self.legs = tuple(
            type("L", (), {"event_ticker": t})() for t in tickers
        )


class FakeApi:
    def __init__(self, book_payload):
        self.book_payload = book_payload
        self.orderbook_calls = []

    async def orderbook(self, ticker, depth=10):
        self.orderbook_calls.append((ticker, depth))
        return self.book_payload


@pytest.fixture
def build(tmp_path, monkeypatch):
    """App factory + monkeypatched exchange surface. Clears the module-level
    collections cache so tests cannot leak into each other."""
    def _build(*, book_payload=CAPTURED_EMPTY_BOOK, response=None,
               collections=None, lookup_error=None):
        path = tmp_path / "lookup.db"
        conn = store.init_db(path)
        base = now_ms() - 30_000
        for i in range(3):
            seed_game(conn, game=f"game-{i}", team=f"Team Alpha{i}",
                      other=f"Team Beta{i}", p=0.7 - i * 0.03, computed_ms=base)
        conn.commit()
        conn.close()

        monkeypatch.setattr(
            parlays, "_collections_cache", {"at_ms": 0, "items": None}
        )

        async def fake_fetch(api, max_pages=25):
            if collections is not None:
                return collections
            return [FakeCollections([])]

        async def fake_lookup(api, collection_ticker, legs, *, side="yes",
                              allow_market_creation=False):
            assert allow_market_creation is True
            assert side == "yes"
            if lookup_error is not None:
                raise lookup_error
            return response if response is not None else CAPTURED_RESPONSE

        monkeypatch.setattr(parlays, "fetch_collections", fake_fetch)
        monkeypatch.setattr(parlays, "lookup_combo", fake_lookup)

        fake_api = FakeApi(book_payload)
        monkeypatch.setattr(
            "backend.api.routes.KalshiRestClient",
            lambda config: _ContextApi(fake_api),
        )
        monkeypatch.setenv("KALSHI_API_KEY", "key")
        monkeypatch.setenv(
            "KALSHI_PRIVATE_KEY_PATH", str(_pem(tmp_path))
        )
        app = create_app(
            AppConfig(
                instance_mode="live", auth_token="secret-token", db_path=path
            )
        )
        return app, fake_api, path
    return _build


class _ContextApi:
    def __init__(self, api):
        self.api = api

    async def __aenter__(self):
        return self.api

    async def __aexit__(self, *exc_info):
        return False


def _pem(tmp_path) -> Path:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    path = tmp_path / "key.pem"
    if not path.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    return path


async def post(app, path, body, headers=None):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.post(path, json=body, headers=headers or {})


async def get(app, path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path)


async def _served_legs(app, card_key="safe"):
    body = (await get(app, "/api/parlays")).json()
    card = next(c for c in body["cards"] if c["key"] == card_key)
    return [
        {"event_ticker": l["event_ticker"], "market_ticker": l["ticker"]}
        for l in card["legs"]
    ]


def _lookup_rows(path):
    conn = store.connect(path)
    rows = conn.execute(
        "SELECT * FROM parlay_lookups ORDER BY id"
    ).fetchall()
    conn.close()
    return rows


#: A populated combo book in the captured envelope: one resting NO bid at
#: $0.985 (98.5c = 985 tenths), 18 units — the deepest resting order the
#: combo record has ever seen, E2's shape.
POPULATED_BOOK = {
    "yes_dollars": [],
    "no_dollars": [["0.9850", "18.00"]],
}


class TestRefusals:
    async def test_the_endpoint_is_auth_gated(self, build):
        app, _, _ = build()
        legs = await _served_legs(app)
        response = await post(
            app, "/api/parlays/lookup", {"card_key": "safe", "legs": legs}
        )
        assert response.status_code in (401, 403)

    async def test_a_drifted_card_is_refused_before_the_exchange(self, build):
        app, fake_api, path = build()
        response = await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": [
                {"event_ticker": "KXMLBGAME-x", "market_ticker": "KXMLBGAME-x-A"},
                {"event_ticker": "KXMLBGAME-y", "market_ticker": "KXMLBGAME-y-B"},
            ]},
            headers=HEADERS,
        )
        assert response.status_code == 409
        assert "slate has moved" in response.json()["detail"]
        assert fake_api.orderbook_calls == []
        assert _lookup_rows(path) == []

    async def test_no_collection_is_words_and_a_row(self, build):
        app, _, path = build(collections=[])
        legs = await _served_legs(app)
        response = await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "no_collection"
        assert "Nothing was created" in body["words"]
        rows = _lookup_rows(path)
        assert [r["status"] for r in rows] == ["no_collection"]

    async def test_an_exchange_error_is_recorded_then_worded(self, build):
        app, _, path = build(lookup_error=RuntimeError("HTTP 400 nope"))
        legs = await _served_legs(app)
        response = await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )
        assert response.status_code == 502
        rows = _lookup_rows(path)
        assert [r["status"] for r in rows] == ["error"]
        assert "nope" in rows[0]["error"]


class TestTheCapturedShapes:
    async def test_an_empty_book_is_an_honest_refusal_not_a_price(self, build):
        """The captured reality: a freshly minted combo's book is empty on
        both sides. The response says so in words and records the row."""
        app, fake_api, path = build()
        legs = await _served_legs(app)
        response = await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "book_empty"
        assert body["minted_market_ticker"] == CAPTURED_RESPONSE["market_ticker"]
        assert "no price you could actually pay" in body["words"]
        rows = _lookup_rows(path)
        assert [r["status"] for r in rows] == ["book_empty"]
        assert rows[0]["minted_market_ticker"] == CAPTURED_RESPONSE["market_ticker"]
        assert rows[0]["derived_yes_ask_tenths"] is None

    async def test_the_minted_ticker_reads_from_the_captured_key(self, build):
        """`market_ticker` at the top level — the shape the 2026-08-23
        capture pinned. A response without it is an error row, not a guess."""
        app, _, path = build(response={"event_ticker": "E", "something": 1})
        legs = await _served_legs(app)
        response = await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )
        assert response.status_code == 502
        assert [r["status"] for r in _lookup_rows(path)] == ["error"]


class TestPricing:
    async def test_the_ask_is_the_complement_of_the_best_no_bid(self, build):
        app, fake_api, path = build(book_payload=POPULATED_BOOK)
        legs = await _served_legs(app)
        response = await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "stake_cents": 500, "legs": legs},
            headers=HEADERS,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "priced"
        # 1000 - 985 = 15 tenths = 1.5c
        assert body["quoted"]["ask_display"] == "1.5c per $1 contract"
        assert "18" in body["quoted"]["depth_display"]
        # $5 at 1.5c -> ~333 contracts -> ~$333 — the cousin's arithmetic.
        assert body["quoted"]["at_stake"]["contracts_display"] == "~333"
        assert body["quoted"]["at_stake"]["payout_display"] == "$333.33"
        assert body["hold_display"].endswith("%")
        assert "hold" in body["verdict"].lower() or "EV" in body["verdict"]
        rows = _lookup_rows(path)
        assert rows[0]["status"] == "priced"
        assert rows[0]["book_no_bid_tenths"] == 985
        assert rows[0]["derived_yes_ask_tenths"] == 15
        assert rows[0]["hold"] is not None

    async def test_the_caveats_travel_with_the_price(self, build):
        app, _, _ = build(book_payload=POPULATED_BOOK)
        legs = await _served_legs(app)
        body = (await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )).json()
        assert "enter-only" in body["notes"]["enter_only"]
        assert "unverified" in body["notes"]["fee"]
        # No fee-net EV key anywhere (ADR 0046): the hold is the verdict.
        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    assert not key.lower().startswith("ev")
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
        walk(body)
