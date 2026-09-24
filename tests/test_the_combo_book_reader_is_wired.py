"""The combination-book reader reaches `/api/hedge` on a credentialed
instance, stays unconstructed on the demo, is bounded in count and in wait,
and is NOT handed to the hedge watcher (#128 -- the wiring #95 deliberately
left to main).

Why this file exists
--------------------
#95 shipped five book states and every caller of `build_payload` passed
`read_combo_book=None`, so every combination row rendered `no_reader_wired`
-- pixel-identical to the screen before the ticket. That is this repo's
five-times-repeated failure (complete, tested, invoked by nothing), and no
test inside #95's lane could catch it because the omission sat in a file the
lane could not touch: `backend/api/routes.py:hedge_router.register(...)`.

What this establishes
---------------------
- On a `live` instance the reader wired into `/api/hedge` is
  `KalshiRestClient.orderbook` on the shared client `combo_api()` builds --
  a payload it returns renders as `bid`, and an exception it raises renders
  as `unreadable`. The wire reaches the venue method, not a stand-in.
- On the `demo` instance `/api/hedge` still serves 200, every combination
  row is `combo_book is None` with reason `no_reader_wired`, and
  `KalshiConfig.load` is never entered -- the keyless branch is absent, not
  handled (#128's "do not regress the demo" clause).
- The reads are BOUNDED (the #128 review's two named changes). A
  combination whose legs have all resolved is never read at the venue
  (`nothing_pending`) -- `open_positions` is unclosed bookkeeping, not live
  games, and 41 rows were "open" with every game settled on 2026-09-21. Two
  positions on one `combo_ticker` share one read. And one read that hangs
  renders `unreadable` inside `COMBO_BOOK_READ_TIMEOUT_S` rather than
  holding the screen through the client's 15s socket timeout and four
  retries, under Next's 30s proxy ceiling.
- `hedge_watch.watch_once` calls `build_payload` WITHOUT a reader. That is
  a decision, pinned here on purpose: the watcher runs every 60 s unattended
  while a game is in play (`WATCH_INTERVAL_S`), nothing it pushes reads
  `combo_book`, and one venue read per position per minute that no consumer
  reads is a spend nobody has decided to make. If that ever flips, this test
  is the one that must be rewritten, and the flip is an ADR because it
  spends.

What this does not establish
----------------------------
- That Kalshi serves the combination book at all, or what it holds. The
  live half of #128's Done-when is a read of `/api/hedge` on the deployed
  instance, recorded on the ticket, not a test.
- Anything about a `live`-mode instance that holds no key. The live deploy
  cannot start keyless (`docker/entrypoint.sh`), so that state exists only
  in tests -- a dev machine -- where the client cannot be built and the row
  renders `unreadable`. That slightly over-states it: no read was attempted,
  the client construction failed. It is the one instance class where a
  failed build and a failed read share a pixel, and it is not a deployable
  one.
- Anything about how often any book state occurs. No rate is claimed.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import httpx
import pytest

from backend import hedge, hedge_watch
from backend.api import routes
from backend.api.routes import create_app
from backend.config import AppConfig, KalshiConfig
from backend.kalshi.rest import KalshiRestClient
from backend.notify.alerts import Alerter
from backend.store import db as store

NOW_MS = 1_700_000_000_000
COMBO = "KXMVE-READERWIRED-TEST"
CIN = "KXMLBGAME-26AUG26CINSF-CIN"
LAD = "KXMLBGAME-26AUG26LADSD-LAD"

#: A real inner orderbook payload with a resting YES bid -- captured, not
#: hand-built (#107; `tests/test_combo_book_capture_with_yes_bid.py` says
#: where it came from). Its best YES level is 0.0130 x 1411.78.
A_YES_BID = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "combo_orderbook_with_yes_bid.json")
    .read_text(encoding="utf-8")
)["response"]["orderbook_fp"]


def seed_combo_position(conn, *, label: str = "two legs") -> int:
    return hedge.record_position(
        conn,
        now_ms=NOW_MS,
        source="kalshi_combo",
        label=label,
        stake_tenths=1_020,
        return_tenths=10_000,
        legs=[
            {"ticker": CIN, "side": "yes", "label": "Cincinnati"},
            {"ticker": LAD, "side": "yes", "label": "Los Angeles"},
        ],
        combo_ticker=COMBO,
        placed_ms=NOW_MS,
    )


def settle_every_leg(conn, position_id: int) -> None:
    for leg in hedge.legs_for(conn, position_id):
        hedge.resolve_leg(
            conn, leg_id=int(leg["id"]), outcome="won", now_ms=NOW_MS,
            source="manual",
        )


def make_app(tmp_path, mode: str, seed=None):
    """An app over a fresh database holding one combination position, or
    whatever `seed(conn)` writes instead."""
    path = tmp_path / "cockpit.db"
    conn = store.init_db(path)
    try:
        if seed is None:
            seed_combo_position(conn)
        else:
            seed(conn)
        conn.commit()
    finally:
        conn.close()
    return create_app(
        AppConfig(db_path=path, instance_mode=mode, auth_token="secret-token"),
        quote_source=NoVenueQuotes(),
    )


class NoVenueQuotes:
    """Stands in for `LiveQuoteSource` so the LEG reads on `/api/hedge`
    never reach a socket. Without it the lazily built source dials the
    real venue (four retries a leg, ~15s) and calls `KalshiConfig.load`
    itself -- which would make the demo tripwire below fire for the wrong
    path and the timeout test measure the wrong wait. `read_books` renders
    a raising fetch as "no price this pass", which is the state wanted."""

    async def fetch(self, ticker, *, observed_ms):
        raise RuntimeError("no venue in this test")

    async def aclose(self):
        return None


async def get_hedge(app) -> dict:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get("/api/hedge")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture()
def keyless_kalshi_config(monkeypatch):
    """`KalshiConfig.load` yields a public-read config, so `combo_api()`
    can build its client in a test process holding no PEM; what the client
    then does is patched per test."""
    monkeypatch.setattr(
        KalshiConfig,
        "load",
        classmethod(
            lambda cls: cls(
                api_key="",
                private_key_path=None,
                rest_url="https://api.test.kalshi.com/trade-api/v2",
                ws_url="wss://api.test.kalshi.com/trade-api/ws/v2",
            )
        ),
    )


def recording_orderbook(monkeypatch, payload=A_YES_BID) -> list[str]:
    """Patch the venue method to return `payload` and record every ticker
    it was asked for."""
    asked: list[str] = []

    async def orderbook(self, ticker, depth=10):
        asked.append(ticker)
        return payload

    monkeypatch.setattr(KalshiRestClient, "orderbook", orderbook)
    return asked


class TestALiveInstanceReadsTheVenue:
    async def test_the_shared_clients_orderbook_is_what_renders(
        self, tmp_path, monkeypatch, keyless_kalshi_config
    ):
        asked = recording_orderbook(monkeypatch)

        body = await get_hedge(make_app(tmp_path, "live"))

        (row,) = body["positions"]
        assert asked == [COMBO]
        assert row["combo_book_reason"] is None
        assert row["combo_book"]["state"] == hedge.COMBO_BOOK_BID
        assert row["combo_book"]["price_display"] == "1.3c"
        assert row["combo_book"]["size"] == 1411.78

    async def test_a_read_that_raises_is_unreadable_not_silence(
        self, tmp_path, monkeypatch, keyless_kalshi_config
    ):
        async def orderbook(self, ticker, depth=10):
            raise RuntimeError("venue said no")

        monkeypatch.setattr(KalshiRestClient, "orderbook", orderbook)

        body = await get_hedge(make_app(tmp_path, "live"))

        (row,) = body["positions"]
        assert row["combo_book_reason"] is None
        assert row["combo_book"]["state"] == hedge.COMBO_BOOK_UNREADABLE


class TestTheDemoNeverBuildsAReader:
    async def test_every_combination_row_is_no_reader_wired(
        self, tmp_path, monkeypatch
    ):
        # A recorder rather than a raising tripwire: `combo_book_state`
        # catches every exception a reader raises and renders `unreadable`,
        # so a raise here would fail the test on the wrong assertion and
        # never say WHY. The recorder names the cause.
        loaded: list[str] = []

        def record(cls):
            loaded.append("KalshiConfig.load entered on the demo")
            raise RuntimeError("keyless")

        monkeypatch.setattr(KalshiConfig, "load", classmethod(record))

        body = await get_hedge(make_app(tmp_path, "demo"))

        assert loaded == [], loaded
        (row,) = body["positions"]
        assert row["combo_book"] is None
        assert row["combo_book_reason"] == hedge.COMBO_BOOK_REASON_NO_READER_WIRED


class TestTheReadsAreBounded:
    """The #128 review's two named changes, each pinned by the mutation that
    removes it: drop the `pending_legs == 0` gate in `build_payload` and the
    settled test reads the venue; drop the per-call memo and the two-position
    test reads twice; drop the `wait_for` in `routes.py` and the hung test
    renders a bid after the sleep instead of `unreadable` before it."""

    async def test_a_settled_combination_is_never_read(
        self, tmp_path, monkeypatch, keyless_kalshi_config
    ):
        asked = recording_orderbook(monkeypatch)

        def seed(conn):
            settle_every_leg(conn, seed_combo_position(conn))

        body = await get_hedge(make_app(tmp_path, "live", seed=seed))

        (row,) = body["positions"]
        assert asked == []
        assert row["pending_legs"] == 0
        assert row["combo_book"] is None
        assert row["combo_book_reason"] == hedge.COMBO_BOOK_REASON_NOTHING_PENDING

    async def test_two_positions_on_one_combination_share_one_read(
        self, tmp_path, monkeypatch, keyless_kalshi_config
    ):
        asked = recording_orderbook(monkeypatch)

        def seed(conn):
            seed_combo_position(conn, label="first")
            seed_combo_position(conn, label="second")

        body = await get_hedge(make_app(tmp_path, "live", seed=seed))

        assert len(body["positions"]) == 2
        assert asked == [COMBO]
        for row in body["positions"]:
            assert row["combo_book"]["state"] == hedge.COMBO_BOOK_BID

    async def test_a_hung_read_is_unreadable_inside_the_timeout(
        self, tmp_path, monkeypatch, keyless_kalshi_config
    ):
        """Proves the per-read `wait_for` bounds a hung combination-book
        read WITHOUT asserting on the wall-clock of the whole route -- a
        suite-load failure observed 2026-09-22 (`elapsed < 1.0` got `1.25`
        under a 13-minute suite; route startup + two leg-quote passes ate
        ~1.2s on their own, 3/3 alone on the same tree) showed the old bound
        was load-sensitive, not wrong about the guard.

        Amended 2026-09-22: do BOTH halves of the fix rather than choosing
        between them, because timing only the read (form (b)) only removes
        load sensitivity if the ~1.2s of route startup/leg passes happens
        BEFORE the combo read, and that ordering is not established. So the
        stub records `time.monotonic()` at entry into a mutable holder
        (`read_started`), sleeps `30.0` (> 3x the observed 1.25s whole-route
        wall-clock under load, so the timeout has room to fire well before
        the stub would ever return), and the assertion bounds only the gap
        from the read's own start to the route's return at `8.0` (>= 5x that
        same 1.25s observation, so ordinary suite load cannot trip it --
        load would have to add ~7s to fail this, which it cannot). Under the
        mutation "remove `wait_for` / its timeout around the combo read"
        the stub is awaited in full, so `elapsed` lands near 30.0 and this
        assertion goes red long before the stub would return on its own.
        """
        monkeypatch.setattr(routes, "COMBO_BOOK_READ_TIMEOUT_S", 0.05)

        read_started = {}

        async def orderbook(self, ticker, depth=10):
            read_started["at"] = time.monotonic()
            await asyncio.sleep(30.0)
            return A_YES_BID

        monkeypatch.setattr(KalshiRestClient, "orderbook", orderbook)

        body = await get_hedge(make_app(tmp_path, "live"))
        elapsed = time.monotonic() - read_started["at"]

        (row,) = body["positions"]
        assert row["combo_book"]["state"] == hedge.COMBO_BOOK_UNREADABLE
        assert elapsed < 8.0, elapsed


class TestTheWatcherDoesNotGetIt:
    async def test_watch_once_calls_build_payload_with_no_reader(
        self, tmp_path, monkeypatch
    ):
        """Pinned negative. See the module docstring for why the watcher is
        kept off the venue's combination book: a 60 s unattended cadence and
        no consumer of the field. `build_payload` defaults the parameter to
        `None`, so the assertion is on the keyword being ABSENT from the
        call -- a later caller passing `read_combo_book=None` explicitly
        would still be a decision and would still fail here."""
        path = tmp_path / "cockpit.db"
        conn = store.init_db(path)
        seed_combo_position(conn)
        conn.commit()
        seen: list[dict] = []
        real = hedge.build_payload

        async def recording(conn, **kwargs):
            seen.append(dict(kwargs))
            return await real(conn, **kwargs)

        monkeypatch.setattr(hedge, "build_payload", recording)

        class Notifier:
            enabled = True

            async def hedge_lock(self, position, *, notes):
                return True

            async def position_state(self, position, *, notes, as_of_ms):
                return True

        async def fetch(ticker, *, observed_ms):
            raise RuntimeError("no venue in this test")

        try:
            await hedge_watch.watch_once(
                conn,
                Alerter(conn, Notifier()),
                now_ms=NOW_MS,
                max_quote_age_ms=30_000,
                fetch_quote=fetch,
            )
        finally:
            conn.close()

        assert len(seen) == 1
        assert "read_combo_book" not in seen[0]
