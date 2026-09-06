"""`POST /api/parlays/bid` -- the resting bid, its refusals, and its cancel.

**Why this exists.** This is the first order shape in the repo that outlives
its request. Every real order before it was immediate-or-cancel: it filled
against visible depth or it died, and nothing could still be working a minute
later. A combination has no depth to fill against -- 40 of 40 books read carried
no resting YES bid -- so the desk becomes the offer, and an offer that stands
can fill while nobody is watching.

**What this establishes.** That the route is auth-gated; that a combination
cannot be bid on without the enter-only acknowledgement; that the shard's
balance is what the affordability check reads, so the refusal Joe hit on
2026-08-30 is caught before the venue sees it and is worded so he can act on
it; that the bid is recorded BEFORE the request leaves; that the cancel sends
the stored shard; and that a bid with no exchange order id is not silently
dropped.

**What it does not establish.** That a bid fills, what a fill costs (ADR 0046
is unverified), or that Kalshi still behaves as the one 2026-08-30 probe
observed. Every payload here is synthetic apart from the balance breakdown,
which is the shape the live account returned that day.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import backend.parlays as parlays                                  # noqa: E402
from backend.api.routes import create_app                          # noqa: E402
from backend.config import AppConfig                               # noqa: E402
from backend.store import db as store                              # noqa: E402
from backend.store.db import now_ms                                # noqa: E402
from tests.test_parlay_lookup import (                             # noqa: E402
    CAPTURED_EMPTY_BOOK,
    FakeCollections,
    _pem,
    seed_game,
)

HEADERS = {"Authorization": "Bearer secret-token"}

#: The live account's shape on 2026-08-30: $21.41 in total, one penny on the
#: shard the combinations trade on.
LIVE_BALANCE = {
    "balance": 2141,
    "balance_dollars": "21.4120",
    "balance_breakdown": [
        {"balance": "21.4020", "exchange_index": 0},
        {"balance": "0.0100", "exchange_index": 1},
        {"balance": "0.0000", "exchange_index": 2},
        {"balance": "0.0000", "exchange_index": 3},
    ],
}

MINTED = "KXMVECROSSCATEGORY-SHARD1-TEST"

#: What the MINT response carries -- the shape of
#: `tests/fixtures/combo_lookup_response.json`, which describes the market it
#: just created. `deci_cent` bands are what make a sub-penny bid expressible.
MINTED_MARKET = {
    "ticker": MINTED,
    "exchange_index": 1,
    "price_level_structure": "deci_cent",
    "price_ranges": [{"start": "0.0000", "end": "1.0000", "step": "0.0010"}],
}


class FakeApi:
    """The exchange surface the bid path touches, with its shard behaviour."""

    def __init__(self, *, balance=None, exchange_index=1, create=None):
        self._balance = balance if balance is not None else LIVE_BALANCE
        self.shard = exchange_index
        self._create = create or {
            "order_id": "ord-1",
            "fill_count": "0.00",
            "remaining_count": "1.00",
        }
        self.created: list = []
        self.cancelled: list = []

    async def orderbook(self, ticker, depth=10):
        return CAPTURED_EMPTY_BOOK

    async def get(self, path, **params):
        """**404s a freshly minted combination, exactly as the venue does.**

        This is the live 2026-08-30 failure: `GET /markets/{ticker}` returns
        404 `not_found` for a combination minted seconds earlier, while the
        orderbook endpoint answers for the same ticker immediately. The bid
        path must never depend on this call.
        """
        from backend.kalshi.rest import KalshiAPIError

        raise KalshiAPIError(404, f"https://example.invalid{path}", "not found")

    async def balance(self, *, exchange_index=None):
        return self._balance

    async def request(self, method, path, *, json_body=None, **kw):
        self.created.append((method, path, json_body))
        return self._create

    async def cancel_order(self, order_id, *, exchange_index=None):
        self.cancelled.append((order_id, exchange_index))
        return {"order_id": order_id, "reduced_by": "1.00"}


@pytest.fixture
def build(tmp_path, monkeypatch):
    def _build(*, api=None, dry_run=False):
        path = tmp_path / "bids.db"
        conn = store.init_db(path)
        base = now_ms() - 30_000
        for i in range(3):
            seed_game(conn, game=f"game-{i}", team=f"Team Alpha{i}",
                      other=f"Team Beta{i}", p=0.7 - i * 0.03, computed_ms=base)
        conn.commit()
        conn.close()

        fake = api or FakeApi()
        parlays.invalidate_collections_cache()

        # **Armed for these tests, and that is the point of the switch.**
        # `COMBO_ORDERS_ARE_DRY_RUNS` ships True so a resting order -- the
        # first shape in this repo that can fill unattended -- rehearses dry
        # before anyone arms it. The live path still has to be exercised, so
        # it is flipped here explicitly rather than shipped off.
        monkeypatch.setattr(
            "backend.store.combo_orders.COMBO_ORDERS_ARE_DRY_RUNS", dry_run
        )

        async def fake_fetch(*a, **kw):
            return [FakeCollections()]

        monkeypatch.setattr(parlays, "fetch_collections", fake_fetch)

        async def fake_lookup(api_, collection, legs, **kw):
            return {
                "market_ticker": MINTED,
                "market": {**MINTED_MARKET, "exchange_index": fake.shard},
            }

        monkeypatch.setattr(parlays, "lookup_combo", fake_lookup)
        monkeypatch.setattr(
            parlays, "echoed_legs",
            lambda legs, response, side="yes": type(
                "E", (), {"verdict": "match", "is_mismatch": False, "detail": ""}
            )(),
        )

        # `combo_api` is a closure inside `create_app`, so it cannot be
        # patched by name. The route's own construction seam is
        # `KalshiRestClient`, which the lookup suite patches the same way.
        monkeypatch.setattr(
            "backend.api.routes.KalshiRestClient",
            lambda config, client=None: fake,
        )
        monkeypatch.setenv("KALSHI_API_KEY", "key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(_pem(tmp_path)))

        config = AppConfig(
            db_path=path, auth_token="secret-token", instance_mode="live",
        )
        return create_app(config), fake, path
    return _build


async def _post(app, path, body, headers=None):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as c:
        return await c.post(path, json=body, headers=headers or {})


async def _get(app, path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as c:
        return await c.get(path)


async def _legs(app):
    body = (await _get(app, "/api/parlays")).json()
    card = next(c for c in body["cards"] if c["key"] == "safe")
    return [
        {"event_ticker": l["event_ticker"], "market_ticker": l["ticker"]}
        for l in card["legs"]
    ]


def _bid(legs, **kw):
    body = {
        "card_key": "safe",
        "legs": legs,
        "price_tenths": 5,
        "stake_cents": 1,
        "combo_acknowledged": True,
    }
    body.update(kw)
    return body


class TestTheDoorIsGuarded:
    async def test_the_route_is_auth_gated(self, build):
        app, _, _ = build()
        response = await _post(app, "/api/parlays/bid", _bid(await _legs(app)))
        assert response.status_code in (401, 403)

    async def test_a_combination_needs_the_enter_only_acknowledgement(
        self, build
    ):
        """The same field, and the same reason, as the hand-bet ticket.

        A client that has never heard of combinations refuses one rather than
        resting a bid on it silently.
        """
        app, api, _ = build()
        response = await _post(
            app, "/api/parlays/bid",
            _bid(await _legs(app), combo_acknowledged=False), HEADERS,
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "enter-only" in detail
        # The exit census, in its own digits -- asserted against the constants
        # and never against the literals, for the reason
        # `backend/parlays.py`'s census block records: a test that pins the
        # literal keeps a refuted sentence green.
        #
        # **The 2026-09-06 parlay census does not touch this claim.** It
        # refuted the ENTRY half elsewhere (51 of 52 combination positions
        # were taker fills) and measured nothing about the way out. No
        # combination book this repo has read has carried a resting YES bid,
        # so the refusal stays exactly as strong as it is; ADR 0085
        # Amendment 1 §A1.4 is what forbids softening it.
        assert str(parlays.COMBO_EXIT_CENSUS_BOOKS_NO_YES_BID) in detail
        assert str(parlays.COMBO_EXIT_CENSUS_BOOKS_READ) in detail
        assert "no YES bid" in detail
        assert api.created == [], "nothing may reach the venue"

    def test_no_census_number_in_the_bid_refusal_is_typed_rather_than_sourced(
        self,
    ):
        """The refusal's digits come from the constants, or this is theatre.

        The assertions above read `str(COMBO_EXIT_CENSUS_BOOKS_READ) in
        detail`, which passes just as happily on a **typed** "40" as on a
        sourced one -- and a typed "40 of 40" is exactly how the refuted entry
        sentence survived a green suite for eleven days. This reads the source
        of the f-string instead and refuses any bare integer in it.

        Follows `tests/test_parlays_api.py::
        test_no_census_number_in_the_note_is_typed_rather_than_sourced`.

        **The one carve-out is an ADR citation.** "(ADR 0046)" is a permanent
        document identifier, not a measurement, and it cannot go stale the
        way a census count can -- so it is stripped before the digit check
        rather than allowed to disable it. Only `status_code=422` is excluded
        structurally: the check reads the `detail` expression alone.

        The carve-out matches a section number too ("ADR 0012 §5"), which
        this string does not carry and its sibling in
        `tests/test_manual_orders.py` does. Kept identical on purpose: a
        half-stripped citation leaves an orphan digit, which reads as a typed
        census number and would force a choice between deleting the citation
        and turning the guard off.

        Mutation observed red: replace `{COMBO_EXIT_CENSUS_BOOKS_READ}` with a
        literal `40` in `backend/api/routers/parlays.py`.
        """
        source = (
            ROOT / "backend" / "api" / "routers" / "parlays.py"
        ).read_text(encoding="utf-8")
        route = next(
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "parlay_bid"
        )
        detail = next(
            kw.value
            for inner in ast.walk(route)
            if isinstance(inner, ast.Raise) and isinstance(inner.exc, ast.Call)
            for kw in inner.exc.keywords
            if kw.arg == "detail"
            and "enter-only" in ast.unparse(kw.value)
        )
        rendered = ast.unparse(detail)
        # An ADR citation, section number and all -- see the docstring.
        stripped = re.sub(r"ADR \d+(?:\s*§\s*[\d.]+)?", "ADR", rendered)
        digits = [ch for ch in stripped if ch.isdigit()]
        assert not digits, f"a census number is typed in: {rendered}"
        names = {n.id for n in ast.walk(detail) if isinstance(n, ast.Name)}
        assert "COMBO_EXIT_CENSUS_BOOKS_NO_YES_BID" in names
        assert "COMBO_EXIT_CENSUS_BOOKS_READ" in names


class TestTheShardIsWhatPaysForIt:
    async def test_the_refusal_joe_hit_is_caught_before_the_venue(self, build):
        """$2 against a $21 account, refused because of WHERE the money is.

        This is the live 2026-08-30 refusal. Kalshi answers
        `insufficient_balance`, which on a $21 account reads as a bug in the
        desk. It is not, and only the desk can say so.
        """
        app, api, _ = build()
        response = await _post(
            app, "/api/parlays/bid",
            _bid(await _legs(app), price_tenths=220, stake_cents=200),
            HEADERS,
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "shard 1" in detail
        assert "$0.01" in detail
        assert "exchange-indexes" in detail
        assert api.created == []

    async def test_a_bid_inside_the_shards_balance_is_placed(self, build):
        """0.5c is what the live probe actually got accepted."""
        app, api, path = build()
        response = await _post(
            app, "/api/parlays/bid", _bid(await _legs(app)), HEADERS
        )
        assert response.status_code == 200, response.json()
        body = response.json()
        assert body["status"] == "resting"
        assert body["exchange_index"] == 1
        assert len(api.created) == 1
        method, sent_path, sent = api.created[0]
        assert method == "POST"
        assert sent["time_in_force"] == "good_till_canceled", (
            "an IOC on an empty book fills nothing and dies"
        )

    async def test_the_words_never_promise_a_fill(self, build):
        """The screen may not turn a standing offer into a placed bet."""
        app, _, _ = build()
        body = (await _post(
            app, "/api/parlays/bid", _bid(await _legs(app)), HEADERS
        )).json()
        assert "on a combination nobody may" in body["words"]

    async def test_an_unreadable_shard_refuses_rather_than_assuming_zero(
        self, build
    ):
        app, api, _ = build(api=FakeApi(balance={"balance_breakdown": "bad"}))
        response = await _post(
            app, "/api/parlays/bid", _bid(await _legs(app)), HEADERS
        )
        assert response.status_code == 502
        assert "could not be read" in response.json()["detail"]
        assert api.created == []

    async def test_the_shard_is_read_from_the_market_not_hardcoded(
        self, build
    ):
        """Kalshi moved baseball to a new shard six days before this shipped.

        A desk that assumed the combinations shard would cancel into the wrong
        one the day Kalshi moves them, and a cancel that cannot find its order
        is the whole failure this path exists to avoid.
        """
        api = FakeApi(exchange_index=0)
        app, api, _ = build(api=api)
        body = (await _post(
            app, "/api/parlays/bid", _bid(await _legs(app)), HEADERS
        )).json()
        assert body["exchange_index"] == 0


class TestTheRecordAndTheCancel:
    async def test_the_bid_is_listed_and_then_cancelled_with_its_shard(
        self, build
    ):
        app, api, _ = build()
        placed = (await _post(
            app, "/api/parlays/bid", _bid(await _legs(app)), HEADERS
        )).json()

        listed = (await _get(app, "/api/parlays/bids")).json()
        assert [b["id"] for b in listed["bids"]] == [placed["order_row_id"]]
        assert listed["bids"][0]["note"] == (
            "Waiting for a seller. You hold nothing yet."
        )

        cancelled = await _post(
            app, f"/api/parlays/bids/{placed['order_row_id']}/cancel",
            {"reason": "test"}, HEADERS,
        )
        assert cancelled.status_code == 200
        assert api.cancelled == [("ord-1", 1)], (
            "the cancel must carry the stored shard: without it the venue "
            "404s an order that is demonstrably resting"
        )
        assert (await _get(app, "/api/parlays/bids")).json()["bids"] == []

    async def test_cancelling_twice_is_refused_rather_than_repeated(
        self, build
    ):
        app, _, _ = build()
        placed = (await _post(
            app, "/api/parlays/bid", _bid(await _legs(app)), HEADERS
        )).json()
        first = await _post(
            app, f"/api/parlays/bids/{placed['order_row_id']}/cancel",
            {}, HEADERS,
        )
        assert first.status_code == 200
        second = await _post(
            app, f"/api/parlays/bids/{placed['order_row_id']}/cancel",
            {}, HEADERS,
        )
        assert second.status_code == 409

    async def test_the_row_exists_before_the_request_leaves(self, build):
        """An order nobody recorded is an order nobody can cancel.

        The venue is made to raise, and the row must survive it -- as
        `pending`, which keeps counting against exposure and shows on the
        screen as something to check.
        """
        class Exploding(FakeApi):
            async def request(self, method, path, *, json_body=None, **kw):
                raise RuntimeError("the socket died")

        app, _, path = build(api=Exploding())
        response = await _post(
            app, "/api/parlays/bid", _bid(await _legs(app)), HEADERS
        )
        assert response.status_code == 502
        assert "may" in response.json()["detail"]

        conn = store.connect(path)
        rows = conn.execute("SELECT status, error_text FROM combo_orders").fetchall()
        conn.close()
        assert [r["status"] for r in rows] == ["pending"]
        assert "socket died" in rows[0]["error_text"]


class TestTheSwitch:
    def test_the_armed_state_is_stated_here_so_a_flip_is_never_silent(self):
        """The switch is ARMED, on Joe's word, 2026-08-30.

        This test asserted `is True` until the moment it was armed, which is
        the point of writing it that way: flipping the constant turns this red
        and the flip has to be acknowledged in the same commit. It is not a
        rubber stamp on the value -- it is the thing that makes arming a
        decision somebody made rather than a diff nobody noticed.

        Its blocking precondition was verified, not assumed: shard 1 read
        $21.4100 (up from $0.0100), so a bid on a combination can be paid for.

        To disarm: set the constant True and change this to `is True`.
        """
        from backend.store.combo_orders import COMBO_ORDERS_ARE_DRY_RUNS

        assert COMBO_ORDERS_ARE_DRY_RUNS is False

    def test_arming_this_door_did_not_arm_the_engine(self):
        """The engine path stays dry, and the interlock stays untouched.

        `ORDERS_ARE_DRY_RUNS` is a different constant on a different path, and
        the whole design of ADR 0063 was that the two doors are separate. A
        commit that armed both while claiming to arm one is exactly what this
        catches.
        """
        from backend.store.orders import ORDERS_ARE_DRY_RUNS

        assert ORDERS_ARE_DRY_RUNS is True

    def test_the_gate_cannot_read_the_resting_bids_table(self):
        """A resting bid is discretion, not evidence.

        Same boundary `manual_orders` has: the live-trading interlock counts
        neither, so arming a hand door can never move the 300-game counter.
        """
        gate_source = (
            ROOT / "backend" / "gate.py"
        ).read_text(encoding="utf-8")

        assert "combo_orders" not in gate_source

    async def test_a_dry_run_sends_nothing_and_says_so(self, build):
        app, api, _ = build(dry_run=True)
        body = (await _post(
            app, "/api/parlays/bid", _bid(await _legs(app)), HEADERS
        )).json()
        assert body["status"] == "dry_run"
        assert "Nothing" in body["words"]
        assert api.created == []


class TestTheCatalogueIsNotOnThePath:
    """The 500 Joe hit on 2026-08-30, and why it cannot come back.

    The bid path re-read `GET /markets/{ticker}` for the price grid and the
    exchange shard. That endpoint returns 404 `not_found` for a combination
    minted seconds earlier -- the catalogue lags the mint, while the orderbook
    endpoint answers for the same ticker immediately, which is exactly why the
    lookup path never noticed and the probe never hit it (it used a market
    minted ninety minutes earlier).

    `FakeApi.get` now raises 404 for every catalogue read, so any future
    version that reaches for it fails this whole file rather than one test.
    """

    async def test_a_bid_is_placed_without_reading_the_catalogue(self, build):
        app, api, _ = build()
        response = await _post(
            app, "/api/parlays/bid", _bid(await _legs(app)), HEADERS
        )
        assert response.status_code == 200, response.json()
        assert response.json()["status"] == "resting"

    async def test_a_mint_that_describes_nothing_refuses_in_words(self, build):
        """Refusing beats guessing: the grid decides which prices the venue
        accepts and the shard decides whether the bid can ever be cancelled."""
        app, api, _ = build()
        import backend.parlays as parlays

        async def blind_lookup(api_, collection, legs, **kw):
            return {"market_ticker": MINTED}

        # No `market` block at all -- the shape an older venue build sent.
        object.__setattr__(parlays, "lookup_combo", blind_lookup)
        response = await _post(
            app, "/api/parlays/bid", _bid(await _legs(app)), HEADERS
        )
        assert response.status_code == 502
        assert "did not describe it" in response.json()["detail"]
        assert api.created == []


class TestTheScreenSaysWhichSideOfTheTradeHeIsOn:
    """Joe read the first version of this copy as having SOLD something.

    His words: "i don't want to make a bid to sell. I want to win money if the
    parlay succeeds." He was buying -- `side: yes, action: buy`, confirmed at
    the venue -- but the words said "an offer standing", and in market language
    an offer is the sell side.

    A screen that leaves a person unsure which side of a trade they are on has
    failed at the one job ADR 0071 gives this desk: price transparency at the
    moment of a bet. Same shape as the CLAUDE.md correction where a refresh
    banner told him closing the page would buy fresher books -- copy that is
    literally defensible and read backwards is still wrong.
    """

    async def test_the_words_say_buy_and_never_say_offer(self, build):
        app, _, _ = build()
        body = (await _post(
            app, "/api/parlays/bid", _bid(await _legs(app)), HEADERS
        )).json()

        words = body["words"]
        assert "BUY order" in words
        assert "offer" not in words.lower(), (
            "in market language an offer is the SELL side"
        )

    async def test_the_words_state_what_winning_pays(self, build):
        """The number he came for, and no version of this screen had it.

        A settled YES contract pays $1.00, so the payout is the contract count
        in dollars. Arithmetic, not a projection.
        """
        app, _, _ = build()
        body = (await _post(
            app, "/api/parlays/bid", _bid(await _legs(app)), HEADERS
        )).json()

        assert "$1.00" in body["words"], "say what a winning contract pays"
        assert "parlay hits" in body["words"]

    async def test_the_words_still_refuse_to_promise_a_fill(self, build):
        """Correcting the buy/sell confusion may not oversell the position.

        He holds nothing until someone sells to him, and on a combination
        nobody has ever been observed doing so.
        """
        app, _, _ = build()
        body = (await _post(
            app, "/api/parlays/bid", _bid(await _legs(app)), HEADERS
        )).json()

        assert "until it fills you hold nothing" in body["words"].lower()

    def test_no_user_facing_surface_calls_a_buy_an_offer(self):
        """Pinned across the screen too, not just the wire.

        **Widened 2026-09-06, because its two named files were deleted.** It
        used to open `RestingBid.tsx` and `RestingBids.tsx` by name and read
        them; when those were removed on Joe's instruction the guard did not
        report that the surfaces were gone, it raised `FileNotFoundError` --
        a guard keyed to a filename dies with the file instead of adopting
        what replaced it. It now sweeps every component, so a new screen
        inherits the rule rather than needing to be added to a list.

        `app/parlay-bid-cancel/route.ts` stays exempt for the original
        reason and now by construction: its "offer standing" is a comment
        about a stale order, not text a person sees, and it does not live
        under `components/`.
        """
        root = ROOT / "frontend" / "src" / "components"
        surfaces = sorted(root.glob("*.tsx"))
        assert surfaces, "no components found -- the sweep would pass vacuously"
        for path in surfaces:
            source = path.read_text(encoding="utf-8")
            assert "offer standing" not in source, path.name
            assert "Nobody is offering" not in source, path.name

    def test_the_offer_making_controls_stay_off_the_screen(self):
        """Joe's instruction, 2026-09-06: no making or finding offers.

        His words were *"I don't want to make offers or find offers in
        shares"*, and *"get rid of this thing from the site"* against the
        resting-bids panel. ADR 0084 built both, and its own docstring argued
        the panel was "the other half of the control that places a bid" --
        which is exactly why they had to leave together. A future session
        reading that ADR will find a well-argued case for a screen the owner
        has since refused, so the refusal is pinned here where the ADR cannot
        outvote it.

        **The backend is deliberately NOT pinned absent.** The route, the
        `combo_orders` table and `bid_watch`'s kickoff auto-cancel still run:
        a bid placed before this change may still be resting at the venue,
        and the watcher is what withdraws it.
        """
        root = ROOT / "frontend" / "src" / "components"
        for name in ("RestingBid.tsx", "RestingBids.tsx"):
            assert not (root / name).exists(), (
                f"{name} is back. It was removed on Joe's instruction "
                f"(2026-09-06); re-adding it needs his word, not an ADR's."
            )

        rendered = (root / "ParlayCards.tsx").read_text(encoding="utf-8")
        assert "<RestingBid" not in rendered
        assert "<RestingBids" not in rendered

    async def test_the_words_say_where_to_look_for_it(self, build):
        """Joe went looking under Positions and found nothing, reasonably.

        On a sportsbook a parlay is accepted the moment it is placed. On an
        exchange it is an order until someone sells, and the screen owes him
        that distinction in the words he reads after tapping.
        """
        app, _, _ = build()
        body = (await _post(
            app, "/api/parlays/bid", _bid(await _legs(app)), HEADERS
        )).json()

        assert "Orders, not Positions" in body["words"]
