"""The same-game parlay builder (#202): `backend/game_builder.py` and
`/api/game/{event_ticker}/legs|mint`.

What these tests establish
--------------------------
- The listing is ONE game's legs, in a fixed order that does not move when the
  chances do, each priced by the desk's pool or `None` with a worded reason.
- The mint writes a `parlay_lookups` row (`card_key = "game"`, NULL fair joint)
  that `combo_rfq._recorded_lookup` finds, WITHOUT reaching any joint-
  probability function (each is stubbed to raise), and refuses the four bad
  requests in words before a single venue call.

What they do not establish
--------------------------
- **That Kalshi mints any same-game combination.** `lookup_combo` is stubbed;
  the wire format of a same-game mint has never been captured by this repo.
- **The catch-all collection's real `associated_events`.** No capture of the
  open `-R` catch-alls exists (the collection list is not a public read).
  `_catch_all_for_atlpit` takes the captured `KXMVESPORTSMULTIGAMEEXTENDED`
  payload and its captured entry shape and points them at the Atlanta at
  Pittsburgh events whose markets ARE captured (`events_nfl_preseason.json`,
  `events_nfl_spread.json`, `events_nfl_props_nested.json`, all 2026-09). The
  `size_max` split (1 on game/spread/scorer events, absent on props) is the
  ticket's own measurement of 2026-09-29, not something a fixture here shows.
- Anything about what a same-game combination costs.
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
from pathlib import Path

import httpx
import pytest

from backend import combo_rfq, game_builder, parlays
from backend.api.routes import create_app
from backend.config import AppConfig
from backend.kalshi.combos import parse_collection
from backend.store import db as store
from backend.store.db import now_ms

FIXTURES = Path(__file__).parent / "fixtures"
HEADERS = {"Authorization": "Bearer secret-token"}
MAX_ODDS_AGE_MS = 6 * 60 * 60 * 1000

GAME = "KXNFLGAME-26SEP13ATLPIT"
ATL = "KXNFLGAME-26SEP13ATLPIT-ATL"
PIT = "KXNFLGAME-26SEP13ATLPIT-PIT"
SPREAD_EVENT = "KXNFLSPREAD-26SEP13ATLPIT"
REC_EVENT = "KXNFLRECYDS-26SEP13ATLPIT"
PASS_EVENT = "KXNFLPASSYDS-26SEP13ATLPIT"
OTHER_GAME_EVENT = "KXNFLGAME-26SEP13BALIND"
CATCH_ALL = "KXMVESPORTSMULTIGAMEEXTENDED-R"

#: Series the fixture game carries, in the order `SERIES_ORDER` puts them.
EXPECTED_SERIES = [
    "KXNFLGAME", "KXNFLSPREAD", "KXNFLFIRSTTD",
    "KXNFLPASSYDS", "KXNFLRSHYDS", "KXNFLRECYDS",
]


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _event_markets() -> dict[str, list[dict]]:
    """Captured markets, keyed by event ticker, for the Atlanta at Pittsburgh
    game and (to prove it is excluded) the Baltimore at Indianapolis moneyline."""
    out: dict[str, list[dict]] = {}
    for event in _load("events_nfl_preseason.json")["events"]:
        if event["event_ticker"] in (GAME, OTHER_GAME_EVENT):
            out[event["event_ticker"]] = event["markets"]
    for event in _load("events_nfl_spread.json")["events"]:
        if event["event_ticker"] == SPREAD_EVENT:
            out[event["event_ticker"]] = event["markets"]
    for events in _load("events_nfl_props_nested.json")["events_by_series"].values():
        for event in events:
            if event["event_ticker"].endswith("26SEP13ATLPIT"):
                out[event["event_ticker"]] = event["markets"]
    return out


def _catch_all_for_atlpit():
    """The captured catch-all, its events swapped for this game's. See the
    module docstring for exactly what is captured and what is not."""
    payload = copy.deepcopy(_load("combo_collections.json")[
        "KXMVESPORTSMULTIGAMEEXTENDED"
    ])
    template = payload["associated_events"][0]
    one_rung = {GAME, SPREAD_EVENT, "KXNFLFIRSTTD-26SEP13ATLPIT", OTHER_GAME_EVENT}
    tickers = [
        *sorted(_event_markets()),
    ]
    events = []
    for ticker in tickers:
        entry = dict(template, ticker=ticker)
        if ticker not in one_rung:
            entry.pop("size_max", None)
        events.append(entry)
    payload["associated_events"] = events
    payload["associated_event_tickers"] = tickers
    return parse_collection(payload)


class FakeApi:
    def __init__(self, *, markets=None, unreadable=()):
        self.markets = markets if markets is not None else _event_markets()
        self.unreadable = set(unreadable)
        self.calls: list[tuple] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self.delay = 0.0

    async def markets_for_event(self, event_ticker):
        self.calls.append(("markets_for_event", event_ticker))
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if event_ticker in self.unreadable:
                raise RuntimeError("boom")
            return self.markets[event_ticker]
        finally:
            self.in_flight -= 1

    async def orderbook(self, ticker, depth=10):
        self.calls.append(("orderbook", ticker))
        return {"yes_dollars": [], "no_dollars": []}


def seed_moneyline(conn, *, atl_p, computed_ms):
    """Atlanta and Pittsburgh moneylines with a fresh consensus, in the shape
    `tests/test_parlay_check.py:seed_game` writes (NFL tickers this time)."""
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events (event_ticker, title, "
        "first_seen_ms, last_seen_ms) VALUES (?, 'Atlanta vs Pittsburgh', 0, 0)",
        (GAME,),
    )
    for ticker, team in ((ATL, "Atlanta"), (PIT, "Pittsburgh")):
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, "
            "title, yes_side_team, market_type, status, first_seen_ms, "
            "last_seen_ms) VALUES (?, ?, ?, ?, 'moneyline', 'active', 0, 0)",
            (ticker, GAME, f"Will {team} win?", team),
        )
    conn.execute(
        "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, "
        "odds_event_id, league, method, commence_skew_ms, linked_ms) "
        "VALUES (?, 'nfl-atlpit', 'Pro Football', 'exact_alias_pair', 0, 0)",
        (GAME,),
    )
    link_id = conn.execute(
        "SELECT id FROM event_links WHERE kalshi_event_ticker = ?", (GAME,)
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
        "commence_ms, home_team, away_team, bookmaker, market, outcome_name, "
        "price_decimal) VALUES (?, 'americanfootball_nfl', 'nfl-atlpit', ?, "
        "'Pittsburgh', 'Atlanta', 'pinnacle', 'h2h', 'Atlanta', 1.6)",
        (computed_ms, now_ms() + 3 * 3_600_000),
    )
    for outcome, prob in (("Atlanta", atl_p), ("Pittsburgh", 1 - atl_p - 0.02)):
        conn.execute(
            "INSERT INTO fair_prices (computed_ms, link_id, market, "
            "outcome_name, p_multiplicative, p_additive, p_power, p_shin, "
            "p_conservative, book_count, books_used, anchored_on_sharp, "
            "oldest_book_age_ms) "
            "VALUES (?, ?, 'h2h', ?, ?, ?, ?, ?, ?, 3, '[]', 1, 5000)",
            (computed_ms, link_id, outcome,
             prob + 0.02, prob + 0.01, prob + 0.015, prob + 0.005, prob),
        )
    conn.commit()


@pytest.fixture(autouse=True)
def _fresh_caches(monkeypatch):
    monkeypatch.setattr(parlays, "_collections_cache", {"at_ms": 0, "items": None})
    monkeypatch.setattr(game_builder, "_listing_memory", {})
    calls: list = []

    async def fake_fetch(api, max_pages=25):
        calls.append(1)
        return [_catch_all_for_atlpit()]

    monkeypatch.setattr(parlays, "fetch_collections", fake_fetch)
    return calls


@pytest.fixture
def conn(tmp_path):
    c = store.init_db(tmp_path / "game.db")
    yield c
    c.close()


async def _list(conn, api=None, game=GAME):
    return await game_builder.list_game_legs(
        conn, game_event_ticker=game, now_ms=now_ms(),
        max_odds_age_ms=MAX_ODDS_AGE_MS, api=api or FakeApi(),
    )


def _flat(listing):
    return [leg for group in listing["groups"] for leg in group["legs"]]


class TestTheLegsListing:
    async def test_it_lists_this_games_legs_and_no_other_games(self, conn):
        listing = await _list(conn)
        tickers = {l["market_ticker"] for l in _flat(listing)}
        assert ATL in tickers and PIT in tickers
        assert all(t.split("-")[1] == "26SEP13ATLPIT" for t in tickers)
        assert not any("BALIND" in t for t in tickers)
        assert listing["collection_ticker"] == CATCH_ALL
        assert listing["game_market_ticker"] == ATL

    async def test_series_come_in_the_fixed_order_and_strikes_ascend(self, conn):
        listing = await _list(conn)
        assert [g["series"] for g in listing["groups"]] == EXPECTED_SERIES
        spread = next(g for g in listing["groups"] if g["series"] == "KXNFLSPREAD")
        strikes = [l["strike"] for l in spread["legs"]]
        assert strikes == sorted(strikes)
        rec = next(g for g in listing["groups"] if g["series"] == "KXNFLRECYDS")
        keys = [(l["strike"], l["player"]) for l in rec["legs"]]
        assert keys == sorted(keys)

    async def test_the_order_does_not_move_when_the_chances_do(self, tmp_path):
        """Any chance-dependent sort changes the order in one of the two
        runs: the favourite is Atlanta in the first and Pittsburgh in the
        second, and ticker order (ATL, PIT) is right for only one of them."""
        orders = []
        for i, atl_p in enumerate((0.70, 0.28)):
            c = store.init_db(tmp_path / f"order-{i}.db")
            try:
                seed_moneyline(c, atl_p=atl_p, computed_ms=now_ms() - 30_000)
                listing = await _list(c)
            finally:
                c.close()
            game_group = listing["groups"][0]
            assert game_group["legs"][0]["sides"]["yes"]["chance"] is not None
            orders.append([l["market_ticker"] for l in _flat(listing)])
        assert orders[0] == orders[1]
        assert orders[0].index(ATL) < orders[0].index(PIT)

    async def test_a_pool_priced_leg_carries_its_chance(self, conn):
        seed_moneyline(conn, atl_p=0.61, computed_ms=now_ms() - 30_000)
        listing = await _list(conn)
        atl = next(l for l in _flat(listing) if l["market_ticker"] == ATL)
        yes = atl["sides"]["yes"]
        assert yes["chance"] == pytest.approx(0.61)
        assert yes["unknown_reason"] is None
        assert yes["chance_display"] == "61%"

    async def test_an_unpriced_leg_is_null_with_a_reason_never_zero(self, conn):
        seed_moneyline(conn, atl_p=0.61, computed_ms=now_ms() - 30_000)
        listing = await _list(conn)
        legs = _flat(listing)
        prop = next(l for l in legs if l["series"] == "KXNFLRECYDS")
        spread = next(l for l in legs if l["series"] == "KXNFLSPREAD")
        atl_no = next(l for l in legs if l["market_ticker"] == ATL)["sides"]["no"]
        for side in (prop["sides"]["yes"], prop["sides"]["no"],
                     spread["sides"]["yes"], atl_no):
            assert side["chance"] is None
            assert side["chance_display"] is None
            assert side["unknown_reason"]
            assert side["unknown_reason_code"]
        assert "no consensus reading" in prop["sides"]["yes"]["unknown_reason"]

    async def test_one_rung_events_are_marked_and_props_are_not(self, conn):
        listing = await _list(conn)
        groups = {g["series"]: g for g in listing["groups"]}
        for series in ("KXNFLGAME", "KXNFLSPREAD", "KXNFLFIRSTTD"):
            assert groups[series]["one_per_event"] is True
            assert all(l["one_per_event"] for l in groups[series]["legs"])
        for series in ("KXNFLPASSYDS", "KXNFLRECYDS", "KXNFLRSHYDS"):
            assert groups[series]["one_per_event"] is False

    async def test_kalshis_own_words_ride_on_each_leg(self, conn):
        listing = await _list(conn)
        atl = next(l for l in _flat(listing) if l["market_ticker"] == ATL)
        assert atl["title"] == (
            "Will Atlanta win the Atlanta vs Pittsburgh Pro Football game?"
        )
        assert atl["yes_label"] == "Atlanta"
        rec = next(l for l in _flat(listing) if l["series"] == "KXNFLRECYDS")
        assert rec["player"] and rec["strike"] is not None

    async def test_the_listing_carries_no_combined_chance(self, conn):
        listing = await _list(conn)
        blob = json.dumps(listing).lower()
        assert "joint" not in blob and "fair_joint" not in blob

    async def test_an_unreadable_event_is_stated_not_dropped_silently(self, conn):
        listing = await _list(conn, FakeApi(unreadable=[REC_EVENT]))
        assert [u["event_ticker"] for u in listing["unreadable_events"]] == [REC_EVENT]
        assert "KXNFLRECYDS" not in [g["series"] for g in listing["groups"]]
        assert "KXNFLGAME" in [g["series"] for g in listing["groups"]]

    async def test_events_are_read_concurrently_but_capped(self, conn, monkeypatch):
        monkeypatch.setattr(game_builder, "MARKET_READ_CONCURRENCY", 2)
        api = FakeApi()
        api.delay = 0.02
        await _list(conn, api)
        assert api.max_in_flight == 2

    async def test_the_collection_read_is_cached_across_page_views(
        self, conn, _fresh_caches
    ):
        await _list(conn)
        await _list(conn)
        assert len(_fresh_caches) == 1

    async def test_a_spread_ticker_is_not_a_game(self, conn):
        with pytest.raises(parlays.LookupRefused) as caught:
            await _list(conn, game=SPREAD_EVENT)
        assert caught.value.status_code == 422

    async def test_a_game_no_collection_lists_is_a_stated_404(self, conn):
        with pytest.raises(parlays.LookupRefused) as caught:
            await _list(conn, game="KXNFLGAME-26SEP20ZZZYYY")
        assert caught.value.status_code == 404


# -- the mint ---------------------------------------------------------------


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


def _leg(market, side="yes"):
    event = "-".join(market.split("-")[:2])
    return {"market_ticker": market, "event_ticker": event, "side": side}


def _rec_markets():
    return [m["ticker"] for m in _event_markets()[REC_EVENT]]


@pytest.fixture
def build(tmp_path, monkeypatch):
    def _build():
        path = tmp_path / "mint.db"
        c = store.init_db(path)
        c.close()

        fake = FakeApi()
        lookups: list[tuple] = []

        async def fake_lookup(api, collection_ticker, legs, *, side="yes",
                              allow_market_creation=False):
            assert allow_market_creation is True
            lookups.append((collection_ticker, list(legs)))
            return {
                "market_ticker": "KXMVESPORTSMULTIGAMEEXTENDED-S2026GAMETEST-ABC123",
                "market": {"mve_selected_legs": [
                    {"event_ticker": e, "market_ticker": m, "side": s}
                    for e, m, s in reversed(list(legs))
                ]},
            }

        def _raises(name):
            def boom(*args, **kwargs):
                raise AssertionError(f"{name} was called on the same-game path")
            return boom

        monkeypatch.setattr(game_builder, "lookup_combo", fake_lookup)
        # Every place a joint-probability function is bound, so a mutation
        # that imports one anywhere still reaches the stub.
        monkeypatch.setattr(
            "backend.core.correlation.joint_probability_all",
            _raises("joint_probability_all"),
        )
        monkeypatch.setattr("backend.core.ladder.joint_for", _raises("joint_for"))
        monkeypatch.setattr(parlays, "joint_for", _raises("joint_for"))
        monkeypatch.setattr(
            "backend.core.parlay.value_parlay", _raises("value_parlay")
        )
        monkeypatch.setattr(parlays, "value_parlay", _raises("value_parlay"))
        monkeypatch.setattr(
            game_builder, "joint_for", _raises("joint_for"), raising=False
        )
        monkeypatch.setattr(
            game_builder, "joint_probability_all", _raises("joint_probability_all"),
            raising=False,
        )
        monkeypatch.setattr(
            game_builder, "value_parlay", _raises("value_parlay"), raising=False
        )

        monkeypatch.setattr(
            "backend.api.routes.KalshiRestClient", lambda config, client=None: fake
        )
        monkeypatch.setenv("KALSHI_API_KEY", "key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(_pem(tmp_path)))
        app = create_app(
            AppConfig(instance_mode="live", auth_token="secret-token", db_path=path)
        )
        return app, fake, lookups, path
    return _build


async def _get(app, path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.get(path)


async def _mint(app, legs, headers=HEADERS, game=GAME):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post(
            f"/api/game/{game}/mint", json={"legs": legs}, headers=headers
        )


def _rows(path):
    c = store.connect(path)
    try:
        return c.execute("SELECT * FROM parlay_lookups ORDER BY id").fetchall()
    finally:
        c.close()


class TestTheLegsRoute:
    async def test_the_route_lists_the_game(self, build):
        app, _fake, _lookups, _path = build()
        response = await _get(app, f"/api/game/{GAME}/legs")
        assert response.status_code == 200
        body = response.json()
        assert body["game_event_ticker"] == GAME
        assert [g["series"] for g in body["groups"]] == EXPECTED_SERIES

    async def test_a_non_game_ticker_is_a_worded_422(self, build):
        app, *_ = build()
        response = await _get(app, f"/api/game/{SPREAD_EVENT}/legs")
        assert response.status_code == 422
        assert "not a game" in response.json()["detail"]


class TestTheMintWritesTheRowTheRfqNeeds:
    async def test_it_mints_without_any_joint_and_writes_a_null_fair_row(
        self, build
    ):
        app, fake, lookups, path = build()
        rec = _rec_markets()
        await _get(app, f"/api/game/{GAME}/legs")
        legs = [_leg(ATL), _leg(rec[0]), _leg(rec[1], "no")]
        response = await _mint(app, legs)
        assert response.status_code == 200, response.text
        body = response.json()
        minted = body["minted_market_ticker"]
        assert body["status"] == "minted"

        assert len(lookups) == 1
        collection, wire = lookups[0]
        assert collection == CATCH_ALL
        assert sorted(wire) == sorted(
            (l["event_ticker"], l["market_ticker"], l["side"]) for l in legs
        )

        rows = _rows(path)
        assert len(rows) == 1
        row = rows[0]
        assert row["card_key"] == "game"
        assert row["fair_joint_conservative"] is None
        assert row["hold"] is None
        assert row["collection_ticker"] == CATCH_ALL
        assert row["minted_market_ticker"] == minted
        assert row["status"] == "book_empty"
        stored = json.loads(row["selected_legs"])
        assert {s["market_ticker"] for s in stored} == {l["market_ticker"] for l in legs}
        assert {s["market_ticker"]: s["side"] for s in stored}[rec[1]] == "no"
        assert all(s["label"] for s in stored)

        # The RFQ path's own reader finds exactly this row.
        c = store.connect(path)
        try:
            found = combo_rfq._recorded_lookup(c, minted)
        finally:
            c.close()
        assert found["card_key"] == "game"
        assert found["collection_ticker"] == CATCH_ALL

    async def test_several_rungs_on_a_prop_event_are_allowed(self, build):
        app, _fake, lookups, _path = build()
        rec = _rec_markets()
        await _get(app, f"/api/game/{GAME}/legs")
        response = await _mint(app, [_leg(rec[0]), _leg(rec[1]), _leg(rec[2])])
        assert response.status_code == 200, response.text
        assert len(lookups) == 1

    async def test_it_needs_auth(self, build):
        app, _fake, lookups, _path = build()
        response = await _mint(app, [_leg(ATL), _leg(_rec_markets()[0])], headers={})
        assert response.status_code in (401, 403)
        assert lookups == []


class TestTheFourRefusalsCostNoVenueCall:
    """Each refusal is a worded 422, and comes with zero venue calls: the
    collection cache and the listing memory are warm from the page view, the
    call log is cleared, and nothing may reach `lookup_combo` or the client."""

    async def _refused(self, build, legs, *, fragment):
        app, fake, lookups, path = build()
        await _get(app, f"/api/game/{GAME}/legs")
        fake.calls.clear()
        response = await _mint(app, legs)
        assert response.status_code == 422, response.text
        assert fragment in response.json()["detail"]
        assert lookups == []
        assert fake.calls == []
        assert _rows(path) == []

    async def test_fewer_than_two_legs(self, build):
        await self._refused(build, [_leg(ATL)], fragment="at least two legs")

    async def test_no_legs_at_all(self, build):
        await self._refused(build, [], fragment="at least two legs")

    async def test_two_legs_on_one_one_rung_event(self, build):
        await self._refused(
            build, [_leg(ATL), _leg(PIT)], fragment="lets a combination take 1 leg"
        )

    async def test_both_sides_of_one_market(self, build):
        await self._refused(
            build, [_leg(_rec_markets()[0]), _leg(_rec_markets()[0], "no")],
            fragment="both sides",
        )

    async def test_a_leg_from_another_game(self, build):
        other = f"{OTHER_GAME_EVENT}-BAL"
        await self._refused(
            build, [_leg(ATL), _leg(other)], fragment="not on this game's list"
        )

    async def test_a_market_the_page_never_listed(self, build):
        ghost = f"{REC_EVENT}-PITNOBODY99-500"
        await self._refused(
            build, [_leg(ATL), _leg(ghost)], fragment="not on this game's list"
        )


class TestTheBuilderNeverReachesForAJoint:
    def test_no_joint_function_is_named_in_the_module(self):
        source = Path(game_builder.__file__).read_text(encoding="utf-8")
        code = re.sub(r'""".*?"""', "", source, flags=re.DOTALL)
        code = re.sub(r"#.*", "", code)
        for name in ("joint_for", "joint_probability_all", "value_parlay",
                     "CorrelationRefused"):
            assert name not in code, f"{name} appears in game_builder's code"
