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

import json
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


class FakeApi:
    """The exchange surface the bid path touches, with its shard behaviour."""

    def __init__(self, *, balance=None, exchange_index=1, create=None):
        self._balance = balance if balance is not None else LIVE_BALANCE
        self._exchange_index = exchange_index
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
        return {
            "market": {
                "ticker": MINTED,
                "exchange_index": self._exchange_index,
                "price_level_structure": "deci_cent",
                # The combination the probe placed a bid on reported a
                # `deci_cent` grid, which is what makes a 0.5c bid expressible
                # at all. `parse_price_grid` refuses a payload without bands
                # rather than assuming whole cents, so the fake carries them.
                "price_ranges": [
                    {"start": "0.0000", "end": "1.0000", "step": "0.0010"}
                ],
            }
        }

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
            return {"market_ticker": MINTED}

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
        assert "enter-only" in response.json()["detail"]
        assert api.created == [], "nothing may reach the venue"


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
        assert "Nobody has to take it" in body["words"]

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
        assert listed["bids"][0]["note"] == "Resting. Nobody has to take it."

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
    def test_resting_bids_are_dry_runs_until_a_commit_arms_them(self):
        """The first order shape that can fill while nobody is watching.

        `MANUAL_ORDERS_ARE_DRY_RUNS` was flipped in a commit of its own so the
        arming was reviewable and revertible on its own; this switch follows
        that convention, and this test is what makes arming it a deliberate
        act rather than a diff nobody noticed.
        """
        from backend.store.combo_orders import COMBO_ORDERS_ARE_DRY_RUNS

        assert COMBO_ORDERS_ARE_DRY_RUNS is True

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
