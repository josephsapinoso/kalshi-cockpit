"""Shape one Kalshi candlestick into what a price chart can draw.

`analysis/clv.py` reads exactly two numbers off a candle (closing bid/ask)
because CLV needs nothing else. The market chart needs the whole bar --
open/high/low/close of the traded price, the book's closing bid and ask, and
volume -- so this parser exists beside it rather than widening the CLV one:
the CLV parser is part of a registered measurement's producer chain and gains
nothing from carrying chart fields.

Field names are pinned by `tests/fixtures/candlesticks_mlb.json`, a real
capture: the per-side blocks carry `close_dollars` (a dollar string), NOT
`close` -- the documentation-derived spelling that once zeroed the entire CLV
pipeline. Money goes through `dollars_to_tenths`; **unreadable resolves to
`None`, never `0`** -- a settled loser genuinely trades at 0, so a substituted
zero is indistinguishable from data.

What this does not establish: anything about liquidity between candles, or
any price anyone could have transacted at -- `price` OHLC is the traded
price, and a chart drawn from it is history, not a quote. The order path
never reads this module.
"""

from __future__ import annotations

from typing import Any, Optional

from ..core.prices import dollars_to_tenths


def _tenths(block: Any, key: str) -> Optional[int]:
    if not isinstance(block, dict):
        return None
    value = block.get(key)
    if value is None:
        return None
    return dollars_to_tenths(value)


def _volume(value: Any) -> Optional[float]:
    """`volume_fp` is a fixed-point string. None when unreadable, never 0."""
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def parse_chart_candle(candle: dict) -> Optional[dict]:
    """One wire candlestick -> a chart bar, prices in integer tenths.

    Returns None -- refusal, not zero -- when the candle carries no timestamp,
    since a bar with no position on the time axis cannot be drawn. Every
    price field is independently nullable: a candle in which nothing traded
    has no OHLC and a book can be one-sided, and the chart must show a gap
    rather than a bar invented at zero.
    """
    ts = candle.get("end_period_ts")
    if not isinstance(ts, (int, float)):
        return None
    price = candle.get("price")
    return {
        "t_ms": int(ts) * 1000,
        "open_tenths": _tenths(price, "open_dollars"),
        "high_tenths": _tenths(price, "high_dollars"),
        "low_tenths": _tenths(price, "low_dollars"),
        "close_tenths": _tenths(price, "close_dollars"),
        "yes_bid_close_tenths": _tenths(candle.get("yes_bid"), "close_dollars"),
        "yes_ask_close_tenths": _tenths(candle.get("yes_ask"), "close_dollars"),
        "volume": _volume(candle.get("volume_fp")),
    }
