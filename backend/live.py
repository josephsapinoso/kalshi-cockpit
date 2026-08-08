"""The ticker: live Kalshi prices pushed to the cockpit.

Why this exists
---------------
The Board renders a price the recorder wrote. Three separate mechanisms have
been built to manage the gap between that price and the real one — a
thirty-second staleness limit, a fifteen-second quote pass, and an order-time
refresh — and all three are compensations for *polling*. A push feed removes
the first two as a display problem: the price on the screen is the price.

`kalshi/ws.py` has done the hard half since the WebSocket path was verified
against a 269-frame capture, and **nothing has ever called it**. It is the fifth
module in this project to be complete, tested and orphaned. This is its caller.

What streaming does not fix, and must not be allowed to imply
-------------------------------------------------------------
**It does not widen the actionable window.** The fair value on every card comes
from a devigged sportsbook consensus costing ~16 credits a day, six a sweep.
A live Kalshi ask against a consensus swept fourteen minutes ago is a live
number on one side of a comparison. The window is an odds-budget fact and no
amount of Kalshi streaming touches it — which is why `odds_age` still expires a
row and this module does not report it as fresh.

**It does not replace the order-time refresh.** A price that arrived over this
feed is a *client-supplied* price by the time it is on screen, and the server
must never trust one. `POST /api/orders` re-reads the book itself. Streaming
means the two usually agree; it does not mean one can stand in for the other.

**It does not remove freshness tracking, it makes the numbers small.** A stuck
feed serving prices that look live is the worst failure this system can have —
it is `docker/entrypoint.sh`'s half-dead-container problem moved into the
browser. So every frame carries the book's own `updated_ms`, a heartbeat goes
out on a fixed interval whether or not anything moved, and `FeedDied` is
broadcast as an event rather than logged and swallowed. A ticker that stops must
*look* stopped.

What it deliberately does not do
--------------------------------
**It writes nothing.** The runner remains the only writer of `recommendations`.
A display path that also recorded would put two writers on the evidence table
and change what the record contains mid-stream, which is the thing
`persist_if_changed` was version-gated to avoid. Everything here is derived and
thrown away.

**It does not re-devig.** The fair probability is read from the row the runner
wrote. Only Kalshi's side of the comparison moves.

**The browser is not given the arithmetic.** Edge and size are recomputed here,
in Python, by the same `edge_after_fees_tenths` and `size_position` the order
endpoint calls. Shipping the fee curve to TypeScript so the client could
subtract it would put two implementations of a money calculation one refresh
apart, which is the failure this repo has recorded three times.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .config import KalshiConfig, RiskConfig, StalenessConfig
from .core.ev import edge_after_fees_tenths
from .core.prices import format_price, is_valid_price
from .core.sizing import size_position
from .kalshi.orderbook import OrderBook
from .kalshi.ws import FeedDied, KalshiWebSocket
from .store import db

logger = logging.getLogger(__name__)

# How often a frame goes out even when no book moved. Without it, "the market is
# quiet" and "the feed is dead" render identically -- which is the entire failure
# mode a ticker introduces that a polled page does not have.
HEARTBEAT_S = 10.0

# How often the subscription set is rebuilt from the database. The runner writes
# new rows on its own cadence; this is a display following it, so it does not
# need to be fast, and re-subscribing churns the socket.
RESUBSCRIBE_S = 120.0

# A slow or wedged browser must not hold frames in memory forever. Small on
# purpose: a client that cannot keep up with ten quotes has no business being
# sent the eleventh, and the newest frame is the only one that matters.
CLIENT_QUEUE_SIZE = 32


@dataclass(frozen=True)
class Priced:
    """One side of one market, re-priced against the live book.

    `fair_probability` and `authorised_contracts` come from the recorded
    recommendation and do not move; everything else is derived from the book
    that just arrived.
    """

    ticker: str
    side: str
    recommendation_id: int
    ask_tenths: int
    depth_at_ask: Optional[float]
    edge_tenths: float
    contracts: int
    observed_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.recommendation_id,
            "ticker": self.ticker,
            "side": self.side,
            "ask_tenths": self.ask_tenths,
            "ask_display": format_price(self.ask_tenths),
            "ask_dollars": self.ask_tenths / 1000.0,
            "edge_tenths": self.edge_tenths,
            "edge_cents": self.edge_tenths / 10.0,
            "depth_at_ask": self.depth_at_ask,
            "contracts": self.contracts,
            "observed_ms": self.observed_ms,
        }


@dataclass
class _Subscription:
    """What the hub needs to re-price one recorded decision."""

    recommendation_id: int
    ticker: str
    side: str
    fair_probability: float
    authorised_contracts: int


def open_decisions(conn, *, staleness: StalenessConfig, now_ms: int) -> list[_Subscription]:
    """The sized rows whose consensus has not aged out, newest per (ticker, side).

    Scoped to rows that could still be ordered, for two reasons and the second
    is the one that matters. A subscription list built from the whole table
    would grow without bound and re-subscribe the socket to markets that settled
    weeks ago. And a ticker showing live prices for rows nobody can bet is a
    screen full of movement that means nothing — the failure this project
    already had once, when the Board ranked every row it had ever written.

    The cutoff is the **odds** limit, because that is what the order endpoint
    enforces now: the Kalshi quote is re-read at order time, so its recorded age
    does not decide whether a row is live. See `api/routes._live_ages`.
    """
    horizon = now_ms - staleness.max_odds_age_s * 1000
    rows = conn.execute(
        """
        SELECT r.id, r.ticker, r.side, r.fair_probability, r.suggested_contracts,
               r.created_ms, r.odds_age_ms, r.last_confirmed_ms,
               r.last_confirmed_odds_age_ms
        FROM recommendations r
        WHERE r.suggested_contracts > 0 AND r.suppressed_reason IS NULL
        ORDER BY r.created_ms DESC, r.id DESC
        """
    ).fetchall()

    seen: set[tuple[str, str]] = set()
    out: list[_Subscription] = []
    for row in rows:
        key = (row["ticker"], row["side"])
        if key in seen:
            continue
        seen.add(key)
        # The instant the consensus was observed, reconstructed the same way
        # `gate.live_ages` does -- a confirmation moves the basis, and a row the
        # quote pass re-derived a minute ago is not fifteen minutes old.
        basis = row["created_ms"]
        odds_age = row["odds_age_ms"]
        if (
            row["last_confirmed_ms"] is not None
            and row["last_confirmed_odds_age_ms"] is not None
            and row["last_confirmed_ms"] >= basis
        ):
            basis, odds_age = row["last_confirmed_ms"], row["last_confirmed_odds_age_ms"]
        if basis - odds_age < horizon:
            continue
        out.append(
            _Subscription(
                recommendation_id=int(row["id"]),
                ticker=row["ticker"],
                side=row["side"],
                fair_probability=float(row["fair_probability"]),
                authorised_contracts=int(row["suggested_contracts"]),
            )
        )
    return out


def price_against(
    book: OrderBook,
    subscription: _Subscription,
    *,
    risk: RiskConfig,
    exposure_dollars: Optional[float],
    now_ms: int,
) -> Optional[Priced]:
    """Re-price one recorded decision against the book that just arrived.

    Returns `None` -- meaning "say nothing about this row" -- when the book
    cannot be priced from. An invalid book (a sequence gap, mid-resync) and a
    book with no opposing bid both land here, and in both cases the honest
    output is silence rather than a number: the last frame the client received
    stays on screen with its own age visible, which is what the heartbeat is for.

    The size comes from `size_position` at the live ask and is capped at what the
    engine authorised, exactly as the order endpoint does it. A ticker that
    showed a bigger size than the server would accept would be inviting a
    refusal.
    """
    if book.invalid:
        return None
    ask = book.ask_for(subscription.side)
    if not is_valid_price(ask):
        return None

    sizing = size_position(
        side=subscription.side,
        ask_tenths=ask,
        fair_probability=subscription.fair_probability,
        risk=risk,
        current_exposure_dollars=exposure_dollars,
    )
    contracts = min(sizing.contracts, subscription.authorised_contracts)
    if contracts < 0:
        contracts = 0

    # Quoted at the size that would actually be sent, because the fee -- and so
    # the edge -- depends on it. A per-contract edge computed independently of
    # size is wrong for every size but one.
    edge = edge_after_fees_tenths(
        ask_tenths=ask,
        contracts=max(1, contracts),
        fair_probability=subscription.fair_probability,
    )
    return Priced(
        ticker=subscription.ticker,
        side=subscription.side,
        recommendation_id=subscription.recommendation_id,
        ask_tenths=ask,
        depth_at_ask=book.depth_at_ask(subscription.side),
        edge_tenths=edge,
        contracts=contracts,
        observed_ms=book.updated_ms or now_ms,
    )


class QuoteHub:
    """One Kalshi feed, many browsers.

    A single WebSocket connection is shared by every viewer. The alternative --
    a connection per browser tab -- would multiply the exchange's view of this
    account by however many phones are open, which is both rude and a good way
    to get rate limited.
    """

    def __init__(
        self,
        db_path,
        *,
        config: Optional[KalshiConfig] = None,
        risk: Optional[RiskConfig] = None,
        staleness: Optional[StalenessConfig] = None,
        heartbeat_s: float = HEARTBEAT_S,
        resubscribe_s: float = RESUBSCRIBE_S,
        socket_factory=None,
    ) -> None:
        self._db_path = db_path
        self._config = config
        self._risk = risk or RiskConfig()
        self._staleness = staleness or StalenessConfig()
        self._heartbeat_s = heartbeat_s
        self._resubscribe_s = resubscribe_s
        # Injected in tests. A hub that could only be exercised against a live
        # exchange would be a hub nothing tests.
        self._socket_factory = socket_factory or self._build_socket

        self._clients: set[asyncio.Queue] = set()
        self._subscriptions: dict[str, list[_Subscription]] = {}
        self._latest: dict[int, Priced] = {}
        self._task: Optional[asyncio.Task] = None
        self._down_reason: Optional[str] = None

    # -- lifecycle ---------------------------------------------------------

    def _build_socket(self, tickers: Iterable[str]) -> KalshiWebSocket:
        return KalshiWebSocket(
            self._config or KalshiConfig.load(),
            tickers,
            on_book_update=self._on_book,
            on_feed_down=self._on_feed_down,
        )

    @property
    def is_down(self) -> bool:
        return self._down_reason is not None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="quote-hub")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        """Hold the feed up, re-reading the subscription list periodically.

        A `FeedDied` is broadcast and then re-raised into a restart rather than
        being retried in place: `KalshiWebSocket.run` has already exhausted its
        own backoff by that point, so retrying immediately would hammer a
        service that has told us ten times it is unavailable.
        """
        while True:
            subscriptions = await asyncio.to_thread(self._load_subscriptions)
            if not subscriptions:
                # Nothing bettable, so nothing to stream. Not an error -- it is
                # the state for most of the day -- but it is broadcast so the
                # client can say "no live rows" rather than "connecting...".
                await self._broadcast({"type": "idle"})
                await asyncio.sleep(self._resubscribe_s)
                continue

            socket = self._socket_factory(sorted(self._subscriptions))
            self._down_reason = None
            await self._broadcast({"type": "up", "tickers": len(self._subscriptions)})
            feed = asyncio.create_task(socket.run(), name="quote-hub-socket")
            try:
                await asyncio.wait_for(
                    asyncio.shield(feed), timeout=self._resubscribe_s
                )
            except asyncio.TimeoutError:
                # The refresh interval elapsed with the feed healthy: rebuild the
                # subscription list and reconnect.
                feed.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await feed
            except FeedDied as exc:
                self._down_reason = str(exc)
                await self._broadcast({"type": "down", "reason": str(exc)})
                await asyncio.sleep(self._resubscribe_s)
            except asyncio.CancelledError:
                feed.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await feed
                raise

    def _load_subscriptions(self) -> list[_Subscription]:
        """Read the bettable rows. Runs on a thread -- sqlite3 is blocking."""
        conn = db.open_db(self._db_path, read_only=True)
        try:
            found = open_decisions(
                conn, staleness=self._staleness, now_ms=db.now_ms()
            )
        finally:
            conn.close()

        by_ticker: dict[str, list[_Subscription]] = {}
        for sub in found:
            by_ticker.setdefault(sub.ticker, []).append(sub)
        self._subscriptions = by_ticker
        return found

    # -- the feed ----------------------------------------------------------

    async def _on_book(self, book: OrderBook) -> None:
        """One book moved. Re-price every recorded side of that market."""
        subs = self._subscriptions.get(book.ticker)
        if not subs:
            return
        now = db.now_ms()
        frames = []
        for sub in subs:
            priced = price_against(
                book, sub,
                risk=self._risk,
                # Zero rather than a read per frame. The order endpoint applies
                # the real exposure; here it would mean a database round trip
                # per book update, and the number it changes is a display size
                # that the server re-derives before accepting anything.
                exposure_dollars=0.0,
                now_ms=now,
            )
            if priced is None:
                continue
            previous = self._latest.get(sub.recommendation_id)
            self._latest[sub.recommendation_id] = priced
            # Only changes go out. A book update that leaves the derived ask
            # untouched -- most of them, since the book moves at levels nobody
            # is buying at -- is not news.
            if previous is None or previous.ask_tenths != priced.ask_tenths:
                frames.append(priced.to_dict())

        if frames:
            await self._broadcast({"type": "quotes", "quotes": frames})

    def _on_feed_down(self, reason: str) -> None:
        self._down_reason = reason

    # -- fan-out -----------------------------------------------------------

    async def _broadcast(self, event: dict[str, Any]) -> None:
        stamped = {**event, "at_ms": db.now_ms()}
        for queue in list(self._clients):
            try:
                queue.put_nowait(stamped)
            except asyncio.QueueFull:
                # Drop the client rather than the frame stream. A queue that
                # cannot keep up is a browser that is gone, asleep, or wedged,
                # and blocking the feed on it would stall every other viewer.
                self._clients.discard(queue)
                logger.info("dropped a stream client that fell behind")

    async def subscribe(self):
        """An async iterator of events for one browser.

        Opens with the latest known price for every row, so a client that
        connects mid-window sees the board immediately rather than waiting for
        the next tick on each market.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=CLIENT_QUEUE_SIZE)
        self._clients.add(queue)
        try:
            opening: dict[str, Any] = {
                "type": "snapshot",
                "quotes": [p.to_dict() for p in self._latest.values()],
                "at_ms": db.now_ms(),
            }
            if self._down_reason:
                opening["down"] = self._down_reason
            yield opening

            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=self._heartbeat_s
                    )
                except asyncio.TimeoutError:
                    # The frame that distinguishes a quiet market from a dead
                    # feed. Without it the client cannot tell the difference,
                    # and neither can the person reading it.
                    event = {
                        "type": "heartbeat",
                        "at_ms": db.now_ms(),
                        "down": self._down_reason,
                    }
                yield event
        finally:
            self._clients.discard(queue)


def sse(event: dict[str, Any]) -> str:
    """One Server-Sent Events frame.

    SSE rather than a second WebSocket: the payload is one-directional, it
    survives proxies that mangle upgrades, and the browser reconnects on its own.
    The cockpit already proxies `/api/*` through Next, and a WebSocket would need
    that rewrite to handle upgrades -- a second transport to get wrong for no
    capability this needs.
    """
    return f"data: {json.dumps(event)}\n\n"
