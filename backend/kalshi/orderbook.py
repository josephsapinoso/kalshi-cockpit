"""Order book state, with sequence-gap detection.

Two failure modes this module exists to prevent, both of which the previous
project had and neither of which announced itself:

**Silent empty books.** Its `apply_snapshot` read `data["yes"]` while the API
sent a different field name. Every book parsed to zero levels, for the entire
life of the project, while 305 synthetic tests passed. So this parser
**raises** when it cannot find a levels field, naming what it looked for. An
empty book must come from an empty book, never from a rename.

**Silent corruption from dropped frames.** Kalshi's `orderbook_delta` carries a
`seq`; the previous project had no `seq` handling anywhere. A dropped or
reordered frame corrupts the book permanently — no error, no resync, and the
prices simply drift from reality. Here a gap raises `SequenceGap`, and the
caller's only correct response is to discard the book and re-snapshot. Do not
attempt to patch forward across a gap.

Prices are integer tenths of a cent throughout. Quantities are floats — Kalshi
sends fractional sizes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from ..core.prices import PRICE_MAX, complement, dollars_to_tenths, parse_quantity

# Field names the levels array has been seen or documented under. Order
# matters only for determinism; any one of them is accepted.
#
# `yes_dollars_fp` / `no_dollars_fp` are what the live feed actually sends,
# confirmed against `tests/fixtures/ws_orderbook_stream.json` (269 frames off
# `wss://api.elections.kalshi.com`, 2026-08-07). The others are kept as
# tolerated aliases, not as guesses.
_YES_LEVEL_KEYS = ("yes_dollars_fp", "yes_dollars", "yes_levels", "yes")
_NO_LEVEL_KEYS = ("no_dollars_fp", "no_dollars", "no_levels", "no")

# A delta names one price level and a signed size change. Live field names,
# same capture. `price` / `delta` were assumed by an earlier version of this
# module and do not exist on the wire.
_DELTA_PRICE_KEYS = ("price_dollars", "price")
_DELTA_SIZE_KEYS = ("delta_fp", "delta")

# Sanity bound on a single level's quantity, to catch a units error (dollars
# read as contracts) rather than to judge whether an order is large.
#
# Calibrated, not invented. The first version of this was 1,000,000 and it
# rejected a real WNBA snapshot carrying 1,174,194 contracts resting at 1c --
# penny levels on a liquid Kalshi market genuinely run into seven figures. The
# bound now sits two orders of magnitude above the largest level in
# `tests/fixtures/ws_orderbook_stream.json`, which still catches the ~100x
# misread it exists for while passing real books.
MAX_PLAUSIBLE_QUANTITY = 100_000_000.0


class SequenceGap(RuntimeError):
    """Frames were dropped on the connection. Every book on it is suspect.

    `seq` is a **per-connection** counter shared by every subscription, not a
    per-market one -- confirmed against a real capture. So a gap does not tell
    you *which* book lost an update, only that something on this connection did.
    The correct response is therefore to invalidate and re-snapshot **all** of
    them, not just one.
    """

    def __init__(self, expected: int, received: int, tickers: tuple[str, ...] = ()):
        self.expected = expected
        self.received = received
        self.tickers = tickers
        super().__init__(
            f"connection sequence gap: expected {expected} got {received} "
            f"({received - expected} frame(s) lost). Every book on this "
            f"connection must be discarded and re-snapshotted -- the gap does "
            f"not say which market lost an update, and patching forward "
            f"corrupts a book silently and permanently. Affects: "
            f"{', '.join(tickers) if tickers else 'all subscribed markets'}"
        )


class MalformedBookMessage(RuntimeError):
    """A message did not contain the fields a book needs.

    Raised rather than returning an empty book, because an empty book and an
    unparseable message look identical downstream and only one of them is a bug.
    """


def _parse_price(raw: Any, *, ticker: str, side: str) -> int:
    """One wire price to integer tenths, or raise.

    Kalshi sends **dollar strings** here -- `"0.4300"`, `"0.0100"` -- not whole
    cents. An earlier version of this module did `int(price) * 10`, which throws
    on every real frame; the whole WebSocket path was dead and no test caught it
    because every test fed it hand-written integers.

    Using `dollars_to_tenths` for everything also makes a future units change
    self-announcing rather than silent: if Kalshi ever sends `43` meaning 43
    cents, this yields 43,000 tenths, which fails the 0..1000 range check below
    instead of quietly pricing a contract at 100x.
    """
    price_tenths = dollars_to_tenths(raw)
    if price_tenths is None:
        raise MalformedBookMessage(
            f"{ticker}: unparseable {side} price {raw!r}"
        )
    # STRICT, matching `is_valid_price`. 0 and 1000 are settled outcomes, not
    # quotes -- a resting bid at either is a contract someone will give you for
    # nothing or sell you for a certain dollar, and neither belongs in a live
    # book. The loose bound here disagreed with `is_valid_price` used everywhere
    # else, so the same number was tradeable in one module and not in another.
    if not 0 < price_tenths < PRICE_MAX:
        raise MalformedBookMessage(
            f"{ticker}: {side} price {raw!r} converts to {price_tenths} tenths, "
            f"outside 0..{PRICE_MAX}. If the feed switched from dollars to "
            f"cents this is what that looks like -- capture a fixture before "
            f"changing the parser."
        )
    return price_tenths


def _parse_levels(raw: Any, *, ticker: str, side: str) -> dict[int, float]:
    """Parse `[[price, qty], ...]` into `{price_tenths: qty}`.

    Both entries arrive as strings -- `["0.4300", "1250.00"]`. Prices are
    normalised to tenths here so the rest of the codebase never sees two price
    units.
    """
    if raw is None:
        return {}
    if not isinstance(raw, Iterable):
        raise MalformedBookMessage(
            f"{ticker}: {side} levels were {type(raw).__name__}, expected a list"
        )

    levels: dict[int, float] = {}
    for entry in raw:
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            raise MalformedBookMessage(
                f"{ticker}: {side} level {entry!r} is not a [price, quantity] pair"
            )
        price_raw, qty_raw = entry[0], entry[1]

        price_tenths = _parse_price(price_raw, ticker=ticker, side=side)
        quantity = parse_quantity(qty_raw)
        if quantity is None:
            raise MalformedBookMessage(
                f"{ticker}: unparseable {side} level {entry!r}"
            )
        if quantity > MAX_PLAUSIBLE_QUANTITY:
            raise MalformedBookMessage(
                f"{ticker}: {side} quantity {quantity} exceeds the plausible "
                f"bound {MAX_PLAUSIBLE_QUANTITY:,.0f} -- likely a units error"
            )
        if quantity > 0:
            levels[price_tenths] = quantity
    return levels


def _find_levels(msg: dict, keys: tuple[str, ...], *, ticker: str, side: str) -> Any:
    """Locate the levels array, or raise naming everything we tried.

    This is the guard against the rename that silently emptied every book in
    the previous project.
    """
    for key in keys:
        if key in msg:
            return msg[key]
    raise MalformedBookMessage(
        f"{ticker}: no {side} levels field found. Tried {keys!r}; message had "
        f"{sorted(msg.keys())!r}. If Kalshi renamed the field, update "
        f"_YES_LEVEL_KEYS/_NO_LEVEL_KEYS and capture a fixture -- do NOT let "
        f"this fall through to an empty book."
    )


@dataclass
class OrderBook:
    """One market's book. Kalshi publishes YES bids and NO bids only."""

    ticker: str
    yes_bids: dict[int, float] = field(default_factory=dict)
    no_bids: dict[int, float] = field(default_factory=dict)
    last_seq: Optional[int] = None
    updated_ms: Optional[int] = None
    # Set when a gap is detected. A stale book must not be quoted from.
    invalid: bool = False

    # -- reads -------------------------------------------------------------

    @property
    def best_yes_bid(self) -> Optional[int]:
        return max(self.yes_bids) if self.yes_bids else None

    @property
    def best_no_bid(self) -> Optional[int]:
        return max(self.no_bids) if self.no_bids else None

    @property
    def best_yes_ask(self) -> Optional[int]:
        """What you would pay to buy YES. Derived, never quoted."""
        best = self.best_no_bid
        return complement(best) if best is not None else None

    @property
    def best_no_ask(self) -> Optional[int]:
        best = self.best_yes_bid
        return complement(best) if best is not None else None

    def ask_for(self, side: str) -> Optional[int]:
        if side == "yes":
            return self.best_yes_ask
        if side == "no":
            return self.best_no_ask
        raise ValueError(f"side must be 'yes' or 'no', got {side!r}")

    def depth_at_ask(self, side: str) -> Optional[float]:
        """Size available at the best ask.

        This is the *opposing bid's* quantity — there is no separate ask book.
        A caller sizing an order needs this, because an edge you cannot fill is
        not an edge.
        """
        if side == "yes":
            best = self.best_no_bid
            return self.no_bids.get(best) if best is not None else None
        if side == "no":
            best = self.best_yes_bid
            return self.yes_bids.get(best) if best is not None else None
        raise ValueError(f"side must be 'yes' or 'no', got {side!r}")

    @property
    def spread_tenths(self) -> Optional[int]:
        bid, ask = self.best_yes_bid, self.best_yes_ask
        return ask - bid if bid is not None and ask is not None else None

    # -- writes ------------------------------------------------------------

    def apply_snapshot(self, msg: dict, seq: Optional[int], observed_ms: int) -> None:
        """Replace the whole book.

        A snapshot always clears first — a snapshot is the complete state, so
        merging into stale levels would keep prices that no longer exist.

        Note the previous project deliberately *ignored* an empty snapshot
        arriving over existing data, to avoid wiping state on reconnect. That
        also meant a genuinely emptied book stayed populated forever. Here an
        empty snapshot empties the book, because quoting from a book that no
        longer exists is the worse failure.
        """
        yes_raw = _find_levels(msg, _YES_LEVEL_KEYS, ticker=self.ticker, side="yes")
        no_raw = _find_levels(msg, _NO_LEVEL_KEYS, ticker=self.ticker, side="no")

        self.yes_bids = _parse_levels(yes_raw, ticker=self.ticker, side="yes")
        self.no_bids = _parse_levels(no_raw, ticker=self.ticker, side="no")
        self.last_seq = seq
        self.updated_ms = observed_ms
        self.invalid = False

    def apply_delta(self, msg: dict, seq: Optional[int], observed_ms: int) -> None:
        """Apply one incremental change.

        **Sequence continuity is not checked here, and that is a correction.**
        An earlier version compared `seq` against this book's own last value and
        raised `SequenceGap` on any discontinuity. The captured stream shows why
        that is wrong: `seq` is a **per-connection** counter, not per-market.
        Twelve tickers subscribed on one connection share one `sid` and one
        strictly-increasing sequence (1..268 across 257 frames), so every frame
        for another market looks like a gap. The check fired on essentially
        every delta and would have resubscribed in a permanent loop.

        Gap detection now lives in `KalshiWebSocket`, where the sequence
        actually lives. See `tests/fixtures/ws_orderbook_stream.json`.

        `seq` is still recorded here, because it is useful for diagnostics and
        because a caller replaying a single-market stream may want it.
        """
        side = msg.get("side")
        if side not in ("yes", "no"):
            raise MalformedBookMessage(
                f"{self.ticker}: delta side was {side!r}, expected 'yes' or 'no'"
            )

        # Same guard as the snapshot levels: name every key tried, so a rename
        # raises instead of falling through to "no change".
        price_raw = _find_levels(
            msg, _DELTA_PRICE_KEYS, ticker=self.ticker, side="delta price"
        )
        delta_raw = _find_levels(
            msg, _DELTA_SIZE_KEYS, ticker=self.ticker, side="delta size"
        )

        price_tenths = _parse_price(price_raw, ticker=self.ticker, side="delta")
        delta = parse_quantity(delta_raw)
        if delta is None:
            raise MalformedBookMessage(
                f"{self.ticker}: unparseable delta quantity {delta_raw!r}"
            )

        levels = self.yes_bids if side == "yes" else self.no_bids
        updated = levels.get(price_tenths, 0.0) + delta

        if updated > MAX_PLAUSIBLE_QUANTITY:
            raise MalformedBookMessage(
                f"{self.ticker}: {side} level at {price_tenths} reached {updated}, "
                f"above the plausible bound -- the book has diverged"
            )

        if updated <= 0:
            levels.pop(price_tenths, None)
        else:
            levels[price_tenths] = updated

        if seq is not None:
            self.last_seq = seq
        self.updated_ms = observed_ms

    def age_ms(self, now_ms: int) -> Optional[int]:
        """How stale this book is. None when it has never been populated.

        Feeds the staleness gate. Note a *derived* ask inherits its freshness
        from the opposing bid, so one stale level makes two quotes stale.
        """
        return None if self.updated_ms is None else now_ms - self.updated_ms

    def is_quotable(self, now_ms: int, max_age_ms: int) -> bool:
        """Whether this book may be used to price a bet.

        False when invalidated by a gap, never populated, or stale. All three
        are refusals, not warnings — the order endpoint checks this
        independently of whatever the UI decided to render.
        """
        if self.invalid or self.updated_ms is None:
            return False
        age = self.age_ms(now_ms)
        return age is not None and age <= max_age_ms
