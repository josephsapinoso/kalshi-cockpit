"""/game legs show Kalshi's ask as listed, with its depth and read time (#276).

What these tests establish
--------------------------
- Each allowed side of each leg carries Kalshi's `yes_ask_dollars` /
  `no_ask_dollars` in integer tenths, read off the captured markets
  (`events_nfl_preseason.json`, `events_nfl_spread.json`,
  `events_nfl_props_nested.json` via the builder's own harness).
- Depth at the YES ask is `yes_ask_size_fp`; depth at the NO ask is
  `yes_bid_size_fp` (a NO ask is a resting YES bid). There is no
  `no_bid_size_fp` and the listing never reads one.
- An ask or size that is missing, unparseable, finer than a tenth, or not a
  tradeable level is `None`, never `0`; no size without an ask.
- The listing stamps its read time, makes no Kalshi call beyond the market
  reads it already made, and the order does not move with the asks.

What they do not establish
--------------------------
- That the listed ask is takeable: it is the market object's printed field,
  not a book walk, and it is as old as the stamped read time.
- Anything about a combination's price; each side is one leg's.
"""

from __future__ import annotations

import copy

import pytest

from backend.core.prices import dollars_to_tenths
from backend.store import db as store
from tests.test_game_builder import (  # noqa: F401
    ATL,
    FakeApi,
    _event_markets,
    _flat,
    _fresh_caches,
    _list,
)


@pytest.fixture
def conn(tmp_path):
    c = store.init_db(tmp_path / "legs_ask.db")
    yield c
    c.close()


def _raw(ticker: str) -> dict:
    for markets in _event_markets().values():
        for market in markets:
            if market["ticker"] == ticker:
                return market
    raise AssertionError(ticker)


def _leg(listing, ticker):
    return next(l for l in _flat(listing) if l["market_ticker"] == ticker)


async def test_game_leg_ask_comes_from_the_listing_and_unreadable_is_none(conn):
    api = FakeApi()
    listing = await _list(conn, api)
    legs = _flat(listing)
    checked = 0
    for leg in legs:
        raw = _raw(leg["market_ticker"])
        listed = leg["listed"]
        assert listed["read_ms"] == listing["now_ms"]
        for side in leg["allowed_sides"]:
            want_ask = dollars_to_tenths(raw.get(f"{side}_ask_dollars"))
            depth_field = "yes_ask_size_fp" if side == "yes" else "yes_bid_size_fp"
            got = listed[side]
            if want_ask is not None and 0 < want_ask < 1000:
                assert got["ask_tenths"] == want_ask, (leg["market_ticker"], side)
                assert isinstance(got["ask_tenths"], int)
                assert got["size"] == float(raw[depth_field])
                checked += 1
            else:
                assert got["ask_tenths"] is None and got["size"] is None
    assert checked > 20, "the capture must carry many listed asks"

    # The moneyline's two depths differ, so a swapped field cannot pass.
    atl = _raw(ATL)
    assert atl["yes_ask_size_fp"] != atl["yes_bid_size_fp"]
    assert _leg(listing, ATL)["listed"]["no"]["size"] == float(atl["yes_bid_size_fp"])
    assert _leg(listing, ATL)["listed"]["yes"]["size"] == float(atl["yes_ask_size_fp"])

    # No extra Kalshi call: market reads only, no order book.
    assert {name for name, _ in api.calls} == {"markets_for_event"}

    # Unreadable is None, never 0.
    bad = copy.deepcopy(_event_markets())
    atl_market = next(m for m in bad[atl["event_ticker"]] if m["ticker"] == ATL)
    atl_market["yes_ask_dollars"] = "abc"
    atl_market["no_ask_dollars"] = "0.0000"
    atl_market["yes_ask_size_fp"] = "nan"
    atl_market["yes_bid_size_fp"] = None
    listed = _leg(await _list(conn, FakeApi(markets=bad)), ATL)["listed"]
    assert listed["yes"] == {
        "ask_tenths": None, "ask_display": None, "size": None, "size_display": None,
    }
    assert listed["no"]["ask_tenths"] is None and listed["no"]["size"] is None

    # An ask with a missing or negative size keeps the ask, drops the size.
    atl_market["yes_ask_dollars"] = "0.5000"
    atl_market["yes_ask_size_fp"] = "-5"
    atl_market["no_ask_dollars"] = "0.5100"
    atl_market["yes_bid_size_fp"] = None
    listed = _leg(await _list(conn, FakeApi(markets=bad)), ATL)["listed"]
    assert listed["yes"]["ask_tenths"] == 500 and listed["yes"]["size"] is None
    assert listed["no"]["ask_tenths"] == 510 and listed["no"]["size"] is None

    # A price finer than a tenth of a cent is refused, not rounded.
    atl_market["yes_ask_dollars"] = "0.50004"
    listed = _leg(await _list(conn, FakeApi(markets=bad)), ATL)["listed"]
    assert listed["yes"]["ask_tenths"] is None


async def test_the_order_does_not_move_with_the_asks(conn):
    base = [l["market_ticker"] for l in _flat(await _list(conn))]
    shifted = copy.deepcopy(_event_markets())
    for markets in shifted.values():
        for i, market in enumerate(markets):
            market["yes_ask_dollars"] = f"0.{(i * 37) % 90 + 5:02d}00"
    after = [l["market_ticker"] for l in _flat(await _list(conn, FakeApi(markets=shifted)))]
    assert after == base


def test_the_screen_labels_the_listed_ask_and_shows_depth_and_read_time():
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "frontend" / "src" / "components" / "GameLegs.tsx"
    ).read_text(encoding="utf-8")
    assert "Kalshi ask, as listed" in src
    assert '<Term k="ask">' in src and '<Term k="depth">' in src
    assert "formatClock(listed.read_ms)" in src
    assert "ask_display" in src and "size_display" in src
