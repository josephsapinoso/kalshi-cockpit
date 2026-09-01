"""`POST /api/parlays/lookup` — "Price on Kalshi" (ADR 0070, Slice C).

What these tests establish: the endpoint is auth-gated; the legs the client
echoes are re-checked ONE AT A TIME against the current candidate pool and a
leg the desk would not serve is refused before anything touches the exchange
(the 2026-08-30 change: the old rule demanded the whole card still be the one
the ladder would compose, which one quote pass was enough to break); the minted market's ticker is
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
from backend.parlays import end_of_desk_day_ms
from backend.kalshi.combos import echoed_legs
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
        # `event_links.league` holds Kalshi's COMPETITION string, not a
        # sport key -- measured on this repo's own database:
        # 'Pro Baseball', 'Pro Basketball (W)', 'Pro Football'. This
        # fixture used to write 'baseball_mlb' here, which made it
        # agree with a reader that believed the same wrong thing and
        # hid the alias bug for the life of the parlay desk. Seed what
        # production seeds.
        "VALUES (?, ?, 'Pro Baseball', 'exact_alias_pair', 0, 0)",
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
        # Clamped inside the desk day; see the note in
        # `test_parlays_api.py`'s `seed_game`. A bare `now + 1h`
        # empties every ladder when the suite runs near the 4am
        # rollover, which would be a clock-dependent suite.
        (computed_ms, game,
         min(now_ms() + 3_600_000, end_of_desk_day_ms(now_ms()) - 60_000),
         team, other, team),
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


#: The three events `build` seeds, in the shape `seed_game` writes them.
SEEDED_EVENTS = tuple(f"KXMLBGAME-game-{i}" for i in range(3))


class FakeCollections:
    """The shape `_choose_collection` reads, with the fields it now reads.

    **This class used to default to zero legs, and that hid the branch under
    test.** `fake_fetch` returned `FakeCollections([])`, so
    `leg_event_tickers <= set()` was false on every call, `covering` was empty
    on every call, and the prefix fallback returned the collection every time.
    Every green test in this file was exercising the fallback -- the branch
    nobody intended to exercise -- while the covering path, which was 100% of
    the live slate on 2026-08-27, had never once been run. Line coverage was
    total and evidential value was nil.

    So the default now COVERS, and a test that wants the fallback asks for it
    by name. `size_min`, `size_max` and `is_all_yes` carry the values the
    committed capture actually shows for the catch-all collections
    (`tests/fixtures/combo_collections.json`): 2, 0 and False. `size_max = 0`
    is an unbounded sentinel and `is_all_yes = False` means *unrestricted*, and
    both matter -- a guard reading either literally would refuse every tap.
    """

    def __init__(
        self,
        tickers=SEEDED_EVENTS,
        *,
        collection_ticker="KXMVESPORTSMULTIGAMEEXTENDED-R",
        size_min=2,
        size_max=0,
        is_all_yes=False,
    ):
        from backend.kalshi.combos import ComboScope

        self.collection_ticker = collection_ticker
        self.scope = ComboScope.MULTI_GAME
        self.size_min = size_min
        self.size_max = size_max
        self.is_all_yes = is_all_yes
        self.legs = tuple(
            type("L", (), {"event_ticker": t})() for t in tickers
        )


class FakeApi:
    def __init__(self, book_payload, book_error=None):
        self.book_payload = book_payload
        self.book_error = book_error
        self.orderbook_calls = []
        #: One entry per `KalshiRestClient(...)` the route builds.
        self.constructions: list = []

    async def orderbook(self, ticker, depth=10):
        self.orderbook_calls.append((ticker, depth))
        if self.book_error is not None:
            raise self.book_error
        return self.book_payload


@pytest.fixture
def build(tmp_path, monkeypatch):
    """App factory + monkeypatched exchange surface. Clears the module-level
    collections cache so tests cannot leak into each other."""
    def _build(*, book_payload=CAPTURED_EMPTY_BOOK, response=None,
               collections=None, lookup_error=None, book_error=None,
               collections_error=None, collections_calls=None):
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
            if collections_calls is not None:
                collections_calls.append(1)
            if collections_error is not None:
                raise collections_error
            if collections is not None:
                return collections
            # Covers the seeded events: the production-normal path. Pass
            # `collections=[FakeCollections([])]` to drive the fallback.
            return [FakeCollections()]

        async def fake_lookup(api, collection_ticker, legs, *, side="yes",
                              allow_market_creation=False):
            """Mints, and echoes the legs back the way the venue does.

            **The canned `CAPTURED_RESPONSE` echoes NFL legs**, which are not
            the legs any test here asks for -- and that went unnoticed for the
            life of this file because nothing compared the two. `echoed_legs`
            compares them now, so the fake has to be faithful or every test
            refuses for the wrong reason.

            The echo is REVERSED on purpose. In the real capture
            (`combo_lookup_repeat.json`) the request order is `[PITBUF, NECLE]`
            and the echo comes back `[NECLE, PITBUF]`, so a comparison that
            depended on order would pass here and fail on the venue.
            """
            assert allow_market_creation is True
            assert side == "yes"
            if lookup_error is not None:
                raise lookup_error
            if response is not None:
                return response
            payload = json.loads(json.dumps(CAPTURED_RESPONSE))
            payload["market"]["mve_selected_legs"] = [
                {"event_ticker": e, "market_ticker": m, "side": side}
                for e, m in reversed(list(legs))
            ]
            return payload

        monkeypatch.setattr(parlays, "fetch_collections", fake_fetch)
        monkeypatch.setattr(parlays, "lookup_combo", fake_lookup)

        fake_api = FakeApi(book_payload, book_error=book_error)
        # The route now builds ONE client lazily and shares it (2026-08-24
        # code review, finding 10), so the fake is constructed with the same
        # `(config, client=...)` signature and its construction count is what
        # `TestTheClientIsSharedAcrossTaps` reads.
        def _fake_client(config, client=None):
            fake_api.constructions.append(1)
            return fake_api

        monkeypatch.setattr("backend.api.routes.KalshiRestClient", _fake_client)
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


def _with_no_bid(price_dollars: str, size: str) -> dict:
    """The CAPTURED empty combo book with one resting NO level added.

    **Why this is built rather than loaded** (2026-08-24 code review, the
    cut-by-cap finding on hand-constructed payloads). The wire-format rule
    says fixtures load captured payloads, and its one recorded exception is
    MLBAM (ADR 0035). This is not a second exception: **no populated
    combination book has ever existed to capture.** `yes_dollars` is empty on
    40 of 40 combo books this repo has ever read, and the resting NO side was
    empty on both of the freshly minted markets captured 2026-08-23. The
    market shape the desk must price is one nobody here has yet observed.

    So the ENVELOPE is captured — this starts from
    `combo_lookup_orderbook.json` and asserts its key set is unchanged — and
    only the level inside it is synthetic. That is the same construction ADR
    0035 blessed for MLB: a synthetic payload with a shape assertion, rather
    than a hand-typed dict that could drift from the wire silently. If a
    populated combo book is ever captured, this function is what it replaces.
    """
    assert set(CAPTURED_EMPTY_BOOK) == {"yes_dollars", "no_dollars"}, (
        "the captured combo orderbook envelope changed shape -- this "
        "synthetic level is built on it and must be rechecked"
    )
    assert not CAPTURED_EMPTY_BOOK["no_dollars"], (
        "the captured book is supposed to be the EMPTY one"
    )
    book = {k: list(v) for k, v in CAPTURED_EMPTY_BOOK.items()}
    book["no_dollars"] = [[price_dollars, size]]
    return book


#: A populated combo book: one resting NO bid at $0.985 (98.5c = 985 tenths),
#: 18 units — the deepest resting order the combo record has ever seen, E2's
#: shape, in the captured envelope.
POPULATED_BOOK = _with_no_bid("0.9850", "18.00")

#: The same book with depth far exceeding any preset stake, so the depth cap
#: is not what bounds the fill.
DEEP_BOOK = _with_no_bid("0.9850", "5000.00")


class TestRefusals:
    async def test_the_endpoint_is_auth_gated(self, build):
        app, _, _ = build()
        legs = await _served_legs(app)
        response = await post(
            app, "/api/parlays/lookup", {"card_key": "safe", "legs": legs}
        )
        assert response.status_code in (401, 403)

    async def test_a_leg_the_desk_never_served_is_refused_by_name(self, build):
        """A lookup MINTS a market, so an unknown ticker may not reach Kalshi.

        The bound that replaced set-equality: not "would the desk pick these
        six", but "is each of these one the desk would serve at all".
        """
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
        detail = response.json()["detail"]
        assert "KXMLBGAME-x-A" in detail and "KXMLBGAME-y-B" in detail
        assert "no longer on the desk's slate" in detail
        assert fake_api.orderbook_calls == []
        assert _lookup_rows(path) == []

    async def test_the_refusal_never_tells_him_to_refresh_and_try_again(
        self, build
    ):
        """The sentence this replaces sent Joe into a loop on 2026-08-30.

        "Refresh the page and look again" was advice that could not work: the
        ladder re-ranks on every request, so refreshing restarted the same
        race. A refusal may name what is wrong with a leg; it may not promise
        that reloading fixes it. Same shape as the copy correction in
        CLAUDE.md -- a screen that names a condition to wait for is lying
        whenever the condition is not the cause.
        """
        app, _, _ = build()
        response = await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": [
                {"event_ticker": "KXMLBGAME-x", "market_ticker": "KXMLBGAME-x-A"},
                {"event_ticker": "KXMLBGAME-y", "market_ticker": "KXMLBGAME-y-B"},
            ]},
            headers=HEADERS,
        )
        detail = response.json()["detail"].lower()
        assert "slate has moved" not in detail
        assert "look again before pricing" not in detail

    async def test_the_legs_are_priced_even_when_the_desk_would_rerank_them(
        self, build
    ):
        """The bug itself: a quote pass between the render and the tap.

        The served card is the two likeliest games. A fresher `fair_prices`
        row then makes a THIRD game the likeliest, so the ladder would now
        compose a different Safe card -- which is exactly what the old
        set-equality check refused. The legs the reader tapped are all still
        pre-game, fresh and priced, so they price.
        """
        app, fake_api, path = build()
        legs = await _served_legs(app)

        conn = store.connect(path)
        seed_game(conn, game="game-2", team="Team Alpha2", other="Team Beta2",
                  p=0.95, computed_ms=now_ms())
        conn.commit()
        conn.close()

        reranked = await _served_legs(app)
        assert reranked != legs, "the fixture did not actually move the slate"

        response = await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )
        assert response.status_code == 200, response.json()
        assert response.json()["status"] in ("priced", "book_empty")
        # The legs recorded are the ones tapped, not the ones the desk would
        # pick now -- an audit row naming a different combination than the one
        # minted would be worse than no row.
        recorded = json.loads(_lookup_rows(path)[0]["selected_legs"])
        assert sorted(l["market_ticker"] for l in recorded) == sorted(
            l["market_ticker"] for l in legs
        )

    async def test_a_stale_leg_is_refused_and_the_words_say_which(self, build):
        """Freshness is still enforced -- per leg, and said out loud."""
        app, fake_api, path = build()
        legs = await _served_legs(app)

        conn = store.connect(path)
        # Push every consensus row back beyond the freshness window.
        conn.execute(
            "UPDATE fair_prices SET computed_ms = ?, oldest_book_age_ms = ?",
            (now_ms() - 86_400_000, 86_400_000),
        )
        conn.commit()
        conn.close()

        response = await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )
        assert response.status_code == 409
        assert fake_api.orderbook_calls == []

    async def test_a_card_may_not_be_used_to_mint_more_legs_than_it_holds(
        self, build
    ):
        app, fake_api, _ = build()
        legs = await _served_legs(app) + [
            {"event_ticker": "KXMLBGAME-z", "market_ticker": "KXMLBGAME-z-C"},
        ]
        response = await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )
        assert response.status_code == 409
        assert "takes 2-3 legs" in response.json()["detail"]
        assert fake_api.orderbook_calls == []

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
        """**Inverted 2026-08-24** (code review, finding 4). This test used to
        assert `~333` contracts and a `$333.33` payout on a book with about
        eighteen contracts resting, and called that "the cousin's arithmetic".
        It is not: 315 of those 333 contracts do not exist. On an enter-only
        market a single stale NO bid at 1.5c manufactures exactly the giant
        apparent number CLAUDE.md rule 1 exists to suppress, and the payout
        slot is the most flattering place it could be shown. The payout is now
        bounded by the resting depth."""
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
        # $5 at 1.5c WANTS 333 contracts; 18 rest, so 18 is what it buys --
        # 27c spent, $18 back if every leg hits.
        at_stake = body["quoted"]["at_stake"]
        assert at_stake["contracts_display"] == "~18"
        assert at_stake["cost_display"] == "$0.27"
        assert at_stake["payout_display"] == "$18.00"
        assert "cannot all be spent" in at_stake["depth_note"]
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
        # Sourced from the module, not retyped: a caveat asserted as a
        # literal freezes it, which is how "40 of 40" outlived the census
        # that refuted it. See `parlays.COMBO_CENSUS_*`.
        assert body["notes"]["unquoted"] == parlays.NOTES["unquoted"]
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


class TestThePayoutCannotExceedTheBook:
    """2026-08-24 code review, finding 4 — CLAUDE.md rule 1 on a payout.

    A depth-blind `stake / ask` turns one stale resting bid on an enter-only
    market into a four-figure payout on the card. These pin that the number
    shown is one the book could actually fill.
    """

    async def test_a_deep_book_is_not_capped(self, build):
        """The cap must bind only when depth actually binds -- otherwise it
        is a silent haircut on every quote."""
        app, _, _ = build(book_payload=DEEP_BOOK)
        legs = await _served_legs(app)
        body = (await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "stake_cents": 500, "legs": legs},
            headers=HEADERS,
        )).json()
        at_stake = body["quoted"]["at_stake"]
        # 5,000 resting against 333 wanted: the stake is what binds.
        assert at_stake["contracts_display"] == "~333"
        assert at_stake["payout_display"] == "$333.33"
        assert at_stake["cost_display"] == "$5.00"
        assert at_stake["depth_note"] is None

    async def test_a_zero_size_level_is_an_empty_book_not_a_free_payout(
        self, build
    ):
        """The route's own answer to "what if depth is nothing".

        `_parse_levels` drops any level with `quantity <= 0`, so a resting NO
        bid of size zero leaves no book at all — which is the `book_empty`
        refusal, not a price with an unbounded payout behind it. This is why
        the `depth is None` branch below is tested directly instead.
        """
        app, _, _ = build(book_payload=_with_no_bid("0.9850", "0"))
        legs = await _served_legs(app)
        body = (await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "stake_cents": 500, "legs": legs},
            headers=HEADERS,
        )).json()
        assert body["status"] == "book_empty"

    def test_an_unreadable_depth_shows_no_payout_at_all(self):
        """Unreadable resolves to a refusal, never to a number.

        Called directly, because the route cannot reach it (the test above
        says why): `depth_at_ask` is typed `Optional` and this function must
        honour that type rather than invent a payout for a caller who does.
        """
        at_stake = parlays._at_stake(500, ask_tenths=15, depth=None)
        assert at_stake["payout_display"] is None
        assert at_stake["contracts_display"] is None
        assert at_stake["cost_display"] is None
        assert at_stake["depth_note"] is not None
        # The stake the person asked about is still named -- a refusal that
        # drops the question is not an answer.
        assert at_stake["stake_display"] == "$5.00"


class TestEveryOutcomeAfterTheMintIsRecorded:
    """2026-08-24 code review, findings 3 and 5.

    `parlay_lookups`' docstring promises a row for every outcome. Two paths
    escaped it: the order-book fetch that runs AFTER the market is minted,
    and a cold-cache failure reading the collection list.
    """

    async def test_a_failed_book_read_keeps_the_minted_ticker(self, build):
        """The one outcome where a missing row costs something: the market
        exists on the exchange and nothing else in this repo records that."""
        app, _, path = build(book_error=RuntimeError("read timeout"))
        legs = await _served_legs(app)
        response = await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )
        assert response.status_code == 502
        rows = _lookup_rows(path)
        assert [r["status"] for r in rows] == ["error"]
        assert rows[0]["minted_market_ticker"] == CAPTURED_RESPONSE["market_ticker"]
        assert "orderbook after mint" in rows[0]["error"]
        # And the words name the ticker, so it is recoverable by hand.
        assert CAPTURED_RESPONSE["market_ticker"] in response.json()["detail"]

    async def test_a_cold_collections_failure_is_a_row_not_a_500(self, build):
        app, _, path = build(collections_error=RuntimeError("HTTP 503"))
        legs = await _served_legs(app)
        response = await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )
        assert response.status_code == 502
        rows = _lookup_rows(path)
        assert [r["status"] for r in rows] == ["error"]
        assert rows[0]["minted_market_ticker"] is None
        assert "HTTP 503" in rows[0]["error"]


class TestTheCollectionsCacheCannotStrand:
    """2026-08-24 code review, finding 5's other two halves."""

    async def test_an_empty_result_is_not_cached(self, build):
        """`[]` is indistinguishable from a failed page walk at this layer.
        Cached, it hands the screen a confident statement about the venue for
        a full hour."""
        calls: list = []
        app, _, _ = build(collections=[], collections_calls=calls)
        legs = await _served_legs(app)
        for _ in range(2):
            body = (await post(
                app, "/api/parlays/lookup",
                {"card_key": "safe", "legs": legs}, headers=HEADERS,
            )).json()
            assert body["status"] == "no_collection"
        assert len(calls) == 2, (
            "an empty collection list must be re-read, not served from cache"
        )

    async def test_a_failed_lookup_drops_the_cache(self, build):
        """The `-R` suffix on collection tickers rotates and the fallback is
        prefix-matched, so the ticker this cache named is the most likely
        thing that was wrong. Without this, one rotation is an hour of 502s
        with no recovery short of a restart."""
        calls: list = []
        app, _, _ = build(
            lookup_error=RuntimeError("HTTP 404 no such collection"),
            collections_calls=calls,
        )
        legs = await _served_legs(app)
        for _ in range(2):
            response = await post(
                app, "/api/parlays/lookup",
                {"card_key": "safe", "legs": legs}, headers=HEADERS,
            )
            assert response.status_code == 502
        assert len(calls) == 2, (
            "a failed lookup must invalidate the collections cache"
        )

    async def test_a_good_list_is_still_cached(self, build):
        """The cache has to keep working -- `fetch_collections` walks up to
        25 pages and a per-tap fetch would spend seconds of rate budget."""
        calls: list = []
        app, _, _ = build(book_payload=POPULATED_BOOK, collections_calls=calls)
        legs = await _served_legs(app)
        for _ in range(2):
            body = (await post(
                app, "/api/parlays/lookup",
                {"card_key": "safe", "legs": legs}, headers=HEADERS,
            )).json()
            assert body["status"] == "priced"
        assert len(calls) == 1


class TestTheLegOrderIsDeterministic:
    async def test_the_recorded_legs_are_sorted(self, build):
        """2026-08-24 code review, finding 6. `list(set)` varies by hash seed
        across processes, and that order is both what goes on the wire to
        Kalshi and what lands in `selected_legs` -- which makes the audit
        table's rows incomparable between restarts for no reason."""
        app, _, path = build(book_payload=POPULATED_BOOK)
        legs = await _served_legs(app)
        await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )
        recorded = json.loads(_lookup_rows(path)[0]["selected_legs"])
        pairs = [(r["event_ticker"], r["market_ticker"]) for r in recorded]
        assert pairs == sorted(pairs)


class TestTheClientIsSharedAcrossTaps:
    async def test_one_client_serves_every_tap(self, build):
        """2026-08-24 code review, finding 10.

        The route built a `KalshiConfig.load()` + PEM re-parse + fresh
        `httpx.AsyncClient` per request -- ~500ms of SSL context setup a tap,
        against this repo's "one shared AsyncClient, not one per call"
        convention, with the discarded sockets a port-exhaustion risk under
        repeat use. `LiveQuoteSource` had the pattern already.
        """
        app, fake_api, _ = build(book_payload=POPULATED_BOOK)
        legs = await _served_legs(app)
        for _ in range(3):
            response = await post(
                app, "/api/parlays/lookup",
                {"card_key": "safe", "legs": legs}, headers=HEADERS,
            )
            assert response.status_code == 200
        assert len(fake_api.constructions) == 1
        assert len(fake_api.orderbook_calls) == 3

    async def test_it_is_built_lazily_not_at_boot(self, build):
        """The demo deploy runs `create_app` from the same image and holds no
        Kalshi credentials. A client built eagerly takes the public demo down
        to support a route the demo does not expose."""
        app, fake_api, _ = build()
        assert fake_api.constructions == []


class TestChoosingACollection:
    """`_choose_collection`, which had no test of its own until 2026-08-27.

    It has two routes and they mean opposite things -- one knows the collection
    lists these events, the other is a prefix guess -- and nothing separated
    them, in the code or in this file. See `FakeCollections` for how the
    default fixture kept the guessing route running on every test.
    """

    def _c(self, tickers, ticker="KXMVESPORTSMULTIGAMEEXTENDED-R", **kw):
        return FakeCollections(tickers, collection_ticker=ticker, **kw)

    def test_a_covering_collection_wins_and_says_so(self):
        cover = self._c(("A", "B", "C"))
        chosen = parlays._choose_collection([cover], {"A", "B"}, leg_count=2)
        assert chosen.collection is cover
        assert chosen.verified is True

    def test_the_smallest_covering_collection_wins(self):
        """Fewest legs first, then ticker. A tighter collection is a closer
        description of the bet than a catch-all that also contains it."""
        wide = self._c(("A", "B", "C", "D"), ticker="KXMVECROSSCATEGORY-WIDE")
        tight = self._c(("A", "B"), ticker="KXMVECROSSCATEGORY-TIGHT")
        for order in ([wide, tight], [tight, wide]):
            chosen = parlays._choose_collection(order, {"A", "B"}, leg_count=2)
            assert chosen.collection is tight

    def test_the_tiebreak_is_the_ticker_not_the_input_order(self):
        """Otherwise the same slate picks a different collection depending on
        what order Kalshi happened to paginate it in."""
        a = self._c(("A", "B"), ticker="KXMVECROSSCATEGORY-AAA")
        b = self._c(("A", "B"), ticker="KXMVECROSSCATEGORY-BBB")
        for order in ([a, b], [b, a]):
            chosen = parlays._choose_collection(order, {"A", "B"}, leg_count=2)
            assert chosen.collection.collection_ticker.endswith("AAA")

    def test_nothing_covering_falls_back_and_admits_it(self):
        """The branch every test in this file used to take silently."""
        other = self._c(("X", "Y"))
        chosen = parlays._choose_collection([other], {"A", "B"}, leg_count=2)
        assert chosen.collection is other
        assert chosen.verified is False, (
            "the legs were never checked against this collection"
        )

    def test_the_fallback_prefixes_are_tried_in_their_stated_order(self):
        cross = self._c((), ticker="KXMVECROSSCATEGORY-R")
        sports = self._c((), ticker="KXMVESPORTSMULTIGAMEEXTENDED-R")
        for order in ([cross, sports], [sports, cross]):
            chosen = parlays._choose_collection(order, {"A"}, leg_count=2)
            assert chosen.collection.collection_ticker.startswith(
                parlays._FALLBACK_COLLECTION_PREFIXES[0]
            )

    def test_no_collection_at_all_is_none(self):
        assert parlays._choose_collection([], {"A"}, leg_count=2) is None

    def test_a_collection_outside_the_prefixes_is_not_guessed_at(self):
        """`None` must stay reachable. It is the only honest refusal, and the
        route turns it into words."""
        odd = self._c(("X",), ticker="KXMVESOMETHINGELSE-R")
        assert parlays._choose_collection([odd], {"A"}, leg_count=2) is None

    def test_a_card_below_size_min_is_refused(self):
        """Server-side, because the client's own length check is the only
        other size guard and the server never trusts the UI."""
        c = self._c(("A", "B"), size_min=3)
        assert parlays._choose_collection([c], {"A", "B"}, leg_count=2) is None
        assert parlays._choose_collection(
            [c], {"A", "B"}, leg_count=3
        ).collection is c

    def test_size_max_zero_is_unbounded_not_zero_legs(self):
        """The sentinel, pinned because reading it literally is the obvious
        mistake and it would refuse every tap.

        Sourced: all three catch-all collections in
        `tests/fixtures/combo_collections.json` carry `size_max 0`, and the
        `lottery` rung the desk pushes has six legs.
        """
        c = self._c(tuple(f"E{i}" for i in range(6)), size_max=0)
        chosen = parlays._choose_collection(
            [c], {f"E{i}" for i in range(6)}, leg_count=6
        )
        assert chosen is not None and chosen.collection is c

    def test_is_all_yes_false_does_not_refuse(self):
        """Same shape of mistake. `False` means *unrestricted*, not yes-only;
        every catch-all in the capture carries it while the desk posts
        all-YES."""
        c = self._c(("A", "B"), is_all_yes=False)
        assert parlays._choose_collection(
            [c], {"A", "B"}, leg_count=2
        ).collection is c


class TestTheMintedLegsAreCheckedAgainstWhatWasAsked:
    """`echoed_legs` -- the only check that can catch a wrong mint.

    `mve_selected_legs` is on every captured response and was read by nothing
    until 2026-08-27, so a market minted over the wrong legs would have been
    priced and shown as the card.
    """

    CAPTURE = json.loads(
        (FIXTURES / "combo_lookup_repeat.json").read_text(encoding="utf-8")
    )

    def _requested(self):
        return [
            (m["event_ticker"], m["market_ticker"])
            for m in self.CAPTURE["selected_markets"]
        ]

    def test_the_real_capture_matches_despite_a_different_order(self):
        """Request order is PITBUF then NECLE; the echo is NECLE then PITBUF.
        A list comparison would call every real tap a mismatch."""
        request = self._requested()
        echoed = [
            leg["event_ticker"]
            for leg in self.CAPTURE["first_call"]["response"]["market"][
                "mve_selected_legs"
            ]
        ]
        assert [e for e, _ in request] != echoed, (
            "the capture must actually be reordered, or this asserts nothing"
        )
        for call in ("first_call", "second_call"):
            assert echoed_legs(
                request, self.CAPTURE[call]["response"]
            ).verdict == "match"

    def test_the_posted_collection_is_not_what_binds(self):
        """Why the echo is needed at all: Kalshi re-homes the market.

        The capture posted to KXMVESPORTSMULTIGAMEEXTENDED-R and got back
        KXMVECROSSCATEGORY-SHARD1-R. So choosing the collection well
        guarantees nothing about the legs, and only the legs can check them.
        """
        posted = self.CAPTURE["collection_ticker"]
        homed = self.CAPTURE["first_call"]["response"]["market"][
            "mve_collection_ticker"
        ]
        assert posted != homed

    def test_a_substituted_leg_is_a_mismatch(self):
        """The failure that matters: the OTHER team in the same game."""
        request = self._requested()
        wrong = [
            (event, market.replace("-NE", "-CLE"))
            for event, market in request
        ]
        assert wrong != request
        echo = echoed_legs(wrong, self.CAPTURE["first_call"]["response"])
        assert echo.is_mismatch
        assert "CLE" in echo.detail

    def test_a_flipped_side_is_a_mismatch(self):
        """A leg echoed back as `no` is a different bet, not a spelling."""
        response = {
            "market": {
                "mve_selected_legs": [
                    {"event_ticker": "E", "market_ticker": "M", "side": "no"}
                ]
            }
        }
        assert echoed_legs([("E", "M")], response, side="yes").is_mismatch

    def test_a_missing_field_is_unreadable_not_agreement(self):
        """Three values, not a boolean. `unreadable` must never silently pass:
        that is how an absent field becomes a check nobody notices died."""
        echo = echoed_legs([("E", "M")], {"market_ticker": "X"})
        assert echo.verdict == "unreadable"
        assert not echo.is_mismatch

    def test_a_malformed_leg_list_is_unreadable(self):
        echo = echoed_legs([("E", "M")], {"market": {"mve_selected_legs": [1]}})
        assert echo.verdict == "unreadable"


class TestTheRouteActsOnTheLegEcho:
    """End to end: a wrong mint is refused rather than priced.

    The mint has already happened by the time the echo can be read -- this
    cannot prevent it. What it changes is whether Joe is shown a price for a
    parlay he did not ask for, or told that is what happened.
    """

    def _wrong_legs_response(self):
        payload = json.loads(json.dumps(CAPTURED_RESPONSE))
        payload["market"]["mve_selected_legs"] = [
            {
                "event_ticker": "KXNFLGAME-SOMETHING-ELSE",
                "market_ticker": "KXNFLGAME-SOMETHING-ELSE-XXX",
                "side": "yes",
            }
        ]
        return payload

    async def test_a_mismatched_mint_is_refused_not_priced(self, build):
        app, _, path = build(
            book_payload=POPULATED_BOOK, response=self._wrong_legs_response()
        )
        legs = await _served_legs(app)
        response = await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )
        assert response.status_code == 502
        assert "not the ones asked for" in response.json()["detail"]

    async def test_the_mismatch_is_recorded_with_the_minted_ticker(self, build):
        """The market exists. Losing its ticker off the audit table is the one
        outcome where a missing row costs something."""
        app, _, path = build(
            book_payload=POPULATED_BOOK, response=self._wrong_legs_response()
        )
        legs = await _served_legs(app)
        await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )
        conn = store.open_db(path, read_only=True)
        row = conn.execute(
            "SELECT * FROM parlay_lookups ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row["status"] == "error"
        assert "leg echo mismatch" in row["error"]
        assert row["minted_market_ticker"], (
            "the minted ticker must survive the refusal"
        )

    async def test_an_unreadable_echo_still_prices(self, build):
        """`unreadable` is not agreement, but it is not a refusal either.

        The field could simply stop being sent. Refusing then would lose a real
        market over a wire change, and the market exists either way -- so it is
        logged and the tap proceeds. Asserted so a later 'tighten this up'
        has to argue with the reason.
        """
        payload = json.loads(json.dumps(CAPTURED_RESPONSE))
        payload["market"].pop("mve_selected_legs", None)
        app, _, _ = build(book_payload=POPULATED_BOOK, response=payload)
        legs = await _served_legs(app)
        body = (await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )).json()
        assert body["status"] == "priced"


class TestTheRecordSaysWhetherTheCollectionWasVerified:
    """`parlay_lookups.collection_unverified` -- the measurement nobody has.

    Whether a catch-all accepts legs it does not enumerate is unmeasured: the
    2026-08-23 capture says Kalshi minted such a post, and that is one
    observation. This column is what turns the question into a rate.
    """

    async def test_a_covering_choice_is_recorded_as_verified(self, build):
        app, _, path = build(book_payload=POPULATED_BOOK)
        legs = await _served_legs(app)
        await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )
        conn = store.open_db(path, read_only=True)
        row = conn.execute(
            "SELECT * FROM parlay_lookups ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row["status"] == "priced"
        assert row["collection_unverified"] == 0

    async def test_a_fallback_choice_is_recorded_as_unverified(self, build):
        """A zero-leg collection covers nothing, so the prefix fallback picks
        it -- which is exactly what this whole file used to do by default."""
        app, _, path = build(
            book_payload=POPULATED_BOOK, collections=[FakeCollections([])]
        )
        legs = await _served_legs(app)
        await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )
        conn = store.open_db(path, read_only=True)
        row = conn.execute(
            "SELECT * FROM parlay_lookups ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row["status"] == "priced"
        assert row["collection_unverified"] == 1

    async def test_an_unverified_failure_does_not_flush_the_collections_cache(
        self, build
    ):
        """The flush exists for a rotated `-R` suffix making the list stale.

        That is the wrong diagnosis when the fallback chose the collection
        without checking the legs: there the list was fine and the legs were
        the problem, so flushing throws away a good fetch and re-buys it on
        the next tap. `test_a_failed_lookup_drops_the_cache` still holds for
        the covering case, and the two together are the whole rule.
        """
        calls: list = []
        app, _, _ = build(
            collections=[FakeCollections([])],
            lookup_error=RuntimeError("HTTP 400 leg not in collection"),
            collections_calls=calls,
        )
        legs = await _served_legs(app)
        for _ in range(2):
            response = await post(
                app, "/api/parlays/lookup",
                {"card_key": "safe", "legs": legs}, headers=HEADERS,
            )
            assert response.status_code == 502
        assert len(calls) == 1, (
            "a leg problem must not be blamed on the collection list"
        )


class TestKalshiWillNotCombineEveryMarketItTrades:
    """Joe's 2026-08-28 report: a parlay page of NCAA football games, and
    every tap answered

        HTTP 400 ... {"error":{"code":"invalid_parameters"}}

    The games were real Kalshi markets -- the desk cannot build a leg without
    matching one -- and Kalshi priced them fine on their own. What it would
    not do is COMBINE them. Measured against the venue the same day:
    `KXMVECROSSCATEGORY-R`, `KXMVECROSSCATEGORY-SHARD1-R` and
    `KXMVESPORTSMULTIGAMEEXTENDED-R` carry the **same 2,365 legs**, of which
    64 are NCAAF and all 64 are inside two days. The failing cards were dated
    a week out and covered 1 of 6, 1 of 6 and 1 of 3 legs.

    So this is not a wrong-collection bug and retrying another catch-all fixes
    nothing -- they enumerate the same legs. It is the desk offering cards the
    venue cannot price, and only finding out after a tap.

    WHAT THIS DOES NOT ESTABLISH
    ----------------------------
    - Nothing about the parlay LADDER, which still builds cards from any
      matched Kalshi market and so still offers uncombinable ones. Fixing that
      needs eligibility readable without a network call: `GET /api/parlays` is
      sync and `build_ladder_payload` also runs inside the scheduler pass, so
      a collections walk there is the shape that killed the pass tail on
      2026-08-28. That needs persistence and its own change.
    - Nothing about whether the combination, once accepted, is worth buying.
      `yes_dollars` is empty on 40 of 40 books this repo has read.
    """

    async def test_a_leg_in_no_collection_is_refused_before_the_post(
        self, build
    ):
        """The whole point: no HTTP call at all.

        `lookup_error` is the instrument -- if the POST is reached the fake
        raises and the status is `error`, so this cannot pass by accident.
        """
        app, _, path = build(
            collections=[
                FakeCollections(
                    tickers=("KXNCAAFGAME-elsewhere",),
                    collection_ticker="KXMVESPORTSMULTIGAMEEXTENDED-R",
                )
            ],
            lookup_error=RuntimeError("the POST must not happen"),
        )
        legs = await _served_legs(app)
        response = await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "legs_not_combinable"
        assert sorted(body["absent_event_tickers"]) == sorted(SEEDED_EVENTS)
        assert "Nothing was created" in body["words"]

    async def test_the_refusal_names_the_games_and_is_recorded(self, build):
        """`invalid_parameters` tells the reader nothing they can act on;
        which games cannot be parlayed is the fact they can."""
        app, _, path = build(
            collections=[
                FakeCollections(
                    tickers=(SEEDED_EVENTS[0],),
                    collection_ticker="KXMVESPORTSMULTIGAMEEXTENDED-R",
                )
            ],
            lookup_error=RuntimeError("the POST must not happen"),
        )
        legs = await _served_legs(app)
        body = (await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )).json()
        assert body["status"] == "legs_not_combinable"
        # The covered one is not accused; the other two are named verbatim.
        assert SEEDED_EVENTS[0] not in body["absent_event_tickers"]
        for absent in body["absent_event_tickers"]:
            assert absent in body["words"]
        # `no_collection` in the table because that column has a CHECK
        # constraint a new value would violate -- the INSERT would crash and
        # the clean refusal would become a 500. The specific reason rides in
        # `error`, which is unconstrained, so the record still separates this
        # from a card no collection would take the shape of.
        rows = _lookup_rows(path)
        assert [r["status"] for r in rows] == ["no_collection"]
        assert rows[0]["error"].startswith("legs_not_combinable: ")
        for absent in body["absent_event_tickers"]:
            assert absent in rows[0]["error"]

    async def test_a_leg_in_SOME_collection_still_posts(self, build):
        """**The 2026-08-23 capture is not overturned.** It posted NFL legs to
        a collection that did not enumerate them and Kalshi minted the market
        anyway, so a catch-all's leg list understates what it accepts. That is
        why the guard asks whether a leg is in ANY collection rather than in
        the chosen one -- "not in the one we picked" and "not in anything the
        venue combines" are different claims and only the second is refusable.

        Here no single collection covers all three legs, so the prefix
        fallback picks one that is missing two of them -- and the tap must
        still go through, because the union has them.
        """
        app, fake_api, _ = build(
            collections=[
                FakeCollections(
                    tickers=(SEEDED_EVENTS[0],),
                    collection_ticker="KXMVESPORTSMULTIGAMEEXTENDED-R",
                ),
                FakeCollections(
                    tickers=SEEDED_EVENTS[1:],
                    collection_ticker="KXMVECROSSCATEGORY-R",
                ),
            ],
        )
        legs = await _served_legs(app)
        body = (await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )).json()
        assert body["status"] != "legs_not_combinable"
        assert fake_api.orderbook_calls, "the tap never reached the exchange"

    async def test_an_unreadable_leg_list_refuses_nothing(self, build):
        """`parse_collection` yields zero legs when the wire omits the detail
        block -- `backend/kalshi/combos.py` records four whole collections
        doing exactly that. An empty union is therefore a failed read, not a
        venue that combines nothing, and refusing every card on it would be an
        outage wearing a guard's clothes. Unreadable resolves to a refusal to
        claim, never to a fact.
        """
        app, fake_api, _ = build(collections=[FakeCollections(tickers=())])
        legs = await _served_legs(app)
        body = (await post(
            app, "/api/parlays/lookup",
            {"card_key": "safe", "legs": legs}, headers=HEADERS,
        )).json()
        assert body["status"] != "legs_not_combinable"
        assert fake_api.orderbook_calls, "the tap never reached the exchange"

    def test_every_non_priced_status_is_drawn_by_the_screen(self):
        """A status the component does not name falls through to the priced
        renderer and reads `value.quoted`, which only `priced` carries -- so
        the failure mode is not a missing message, it is `undefined` rendered
        into the price line.
        """
        src = (
            Path(__file__).resolve().parents[1]
            / "frontend" / "src" / "components" / "PriceOnKalshi.tsx"
        ).read_text(encoding="utf-8")
        for status in ("no_collection", "book_empty", "legs_not_combinable"):
            assert f'value.status === "{status}"' in src, status
