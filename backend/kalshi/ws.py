"""Kalshi WebSocket client for the `orderbook_delta` channel.

This is the live-data path. Everything the staleness gate depends on comes
through here, which makes its failure modes the expensive ones.

Three incidents from the previous project are designed against directly:

**Data stopped while the socket stayed healthy.** Ping/pong kept succeeding for
16 minutes while no market data arrived. TCP liveness does not imply data flow.
So there is an *application-level* receive timeout: no message within
`receive_timeout_s` forces a reconnect regardless of what the transport thinks.

**Reconnect gave up silently.** After 10 consecutive failures its client broke
out of its loop and the process sat there with a stale display forever — no
exit, no alert, no supervisor. Here exhausting the retries raises
`FeedDied`, and `on_feed_down` fires so a caller can alert. A dead feed must be
loud, because every downstream price silently freezes at its last value.

**Dropped frames corrupted books permanently.** No `seq` handling existed. Here
a `SequenceGap` triggers an automatic unsubscribe/resubscribe for that one
ticker, which yields a fresh snapshot. The book is unusable in between and
`is_quotable` says so.

Subscriptions are one command per ticker. Kalshi accepts a `market_tickers`
array; this sends them individually because a per-ticker subscription id is
what makes per-ticker resubscription possible after a gap.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Awaitable, Callable, Iterable, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from ..config import KalshiConfig
from .auth import KalshiAuth
from .orderbook import MalformedBookMessage, OrderBook, SequenceGap
from .rest import KalshiCredentialsRequired

logger = logging.getLogger(__name__)

DEFAULT_RECEIVE_TIMEOUT_S = 60.0
DEFAULT_MAX_RECONNECT_ATTEMPTS = 10
DEFAULT_BACKOFF_BASE_S = 1.0
DEFAULT_BACKOFF_CAP_S = 60.0

BookCallback = Callable[[OrderBook], Awaitable[None] | None]


class ResyncRequired(RuntimeError):
    """Internal signal: drop the connection and re-snapshot everything.

    Not an error condition. It unwinds the consume loop so `run()` reconnects,
    which is the only resync route this project has actually observed working.
    """


class FeedDied(RuntimeError):
    """The feed could not be re-established. Downstream prices are frozen."""


def _now_ms() -> int:
    return int(time.time() * 1000)


class KalshiWebSocket:
    """Maintains live order books for a set of tickers.

    Usage::

        ws = KalshiWebSocket(cfg, tickers=["KXMLBGAME-..."])
        await ws.run()          # runs until cancelled or the feed dies

        ws.book("KXMLBGAME-...")   # current state, may be stale or invalid
    """

    def __init__(
        self,
        config: KalshiConfig,
        tickers: Iterable[str],
        auth: Optional[KalshiAuth] = None,
        *,
        receive_timeout_s: float = DEFAULT_RECEIVE_TIMEOUT_S,
        max_reconnect_attempts: int = DEFAULT_MAX_RECONNECT_ATTEMPTS,
        on_book_update: Optional[BookCallback] = None,
        on_feed_down: Optional[Callable[[str], None]] = None,
    ):
        self.config = config
        # The socket has no public half: Kalshi's `/trade-api/ws/v2` authenticates
        # at the handshake, so unlike the REST client there is no subset of it a
        # credential-free instance can reach. Refused at construction with the
        # setting named, rather than letting `KalshiAuth(None)` raise about a
        # path -- a stranger running KALSHI_PUBLIC_READ_ONLY should be told the
        # ticker is off, not handed a traceback about a PEM.
        if auth is None and config.private_key_path is None:
            raise KalshiCredentialsRequired(
                "The live ticker needs a Kalshi API key and this instance has "
                "none (KALSHI_PUBLIC_READ_ONLY). Public reads cover market "
                "data over REST; the WebSocket feed authenticates at the "
                "handshake and has no unauthenticated mode."
            )
        self.auth = auth or KalshiAuth(config.api_key, config.private_key_path)
        self.tickers = list(dict.fromkeys(tickers))  # de-dupe, keep order
        self.receive_timeout_s = receive_timeout_s
        self.max_reconnect_attempts = max_reconnect_attempts
        self.on_book_update = on_book_update
        self.on_feed_down = on_feed_down

        self.books: dict[str, OrderBook] = {t: OrderBook(t) for t in self.tickers}
        # One sid serves every ticker on a connection, so this is one-to-many.
        self._sids: dict[int, set[str]] = {}
        self._ticker_sids: dict[str, int] = {}
        # Command id -> ticker, awaiting its `subscribed` ack. The ack carries
        # no ticker, so this is the only correlation available.
        self._pending_subscriptions: dict[int, str] = {}
        self._command_id = 0
        self._ws = None
        self._last_message_ms: Optional[int] = None
        # Sequence is per-connection, so it is tracked here rather than per book.
        self._last_seq: Optional[int] = None
        self._pending_resync = False

    # -- state -------------------------------------------------------------

    def book(self, ticker: str) -> Optional[OrderBook]:
        return self.books.get(ticker)

    def quotable_books(self, max_age_ms: int) -> dict[str, OrderBook]:
        """Only the books safe to price from right now."""
        now = _now_ms()
        return {
            t: b for t, b in self.books.items() if b.is_quotable(now, max_age_ms)
        }

    # -- connection --------------------------------------------------------

    async def run(self) -> None:
        """Connect, subscribe, and consume until cancelled or the feed dies."""
        attempt = 0
        while True:
            try:
                await self._connect_and_consume()
                attempt = 0  # a clean session resets the budget
            except asyncio.CancelledError:
                raise
            except ResyncRequired as signal:
                # Not a failure, so it must not consume the reconnect budget --
                # otherwise a burst of dropped frames looks like a dying feed.
                logger.warning("%s", signal)
                attempt = 0
                continue
            except websockets.exceptions.InvalidStatus as exc:
                # A rejected handshake (401 on bad credentials, 403 on a
                # blocked IP) is not an OSError, so it used to escape `run()`
                # entirely -- past the retry budget, past FeedDied, and without
                # firing on_feed_down. The alerting path this class exists to
                # guarantee was skipped for the most likely failure of all.
                message = (
                    f"Kalshi rejected the WebSocket handshake: {exc}. "
                    "Check KALSHI_API_KEY and the private key. Every "
                    "downstream price is now frozen at its last value."
                )
                logger.error(message)
                if self.on_feed_down:
                    self.on_feed_down(message)
                raise FeedDied(message) from exc
            except (ConnectionClosed, OSError, asyncio.TimeoutError) as exc:
                attempt += 1
                if attempt > self.max_reconnect_attempts:
                    message = (
                        f"Kalshi feed died after {self.max_reconnect_attempts} "
                        f"reconnect attempts: {type(exc).__name__}: {exc}. "
                        "Every downstream price is now frozen at its last value."
                    )
                    logger.error(message)
                    if self.on_feed_down:
                        self.on_feed_down(message)
                    raise FeedDied(message) from exc

                delay = self._backoff(attempt)
                logger.warning(
                    "feed dropped (%s), reconnecting in %.1fs (attempt %d/%d)",
                    type(exc).__name__, delay, attempt, self.max_reconnect_attempts,
                )
                await asyncio.sleep(delay)

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff with full jitter.

        The previous project had no jitter, so a shared outage produced a
        thundering herd of reconnects on exactly the same schedule.
        """
        return random.uniform(
            0, min(DEFAULT_BACKOFF_CAP_S, DEFAULT_BACKOFF_BASE_S * (2**attempt))
        )

    async def _connect_and_consume(self) -> None:
        headers = self.auth.get_ws_headers()
        logger.info("connecting to %s (%d tickers)", self.config.ws_url, len(self.tickers))

        async with websockets.connect(
            self.config.ws_url, additional_headers=headers
        ) as ws:
            self._ws = ws
            self._sids.clear()
            self._ticker_sids.clear()
            self._pending_subscriptions.clear()
            self._last_message_ms = _now_ms()
            # Every book predates this connection and has not been confirmed by
            # a fresh snapshot. Leaving them valid lets a book quoted a second
            # before the drop stay priceable through a 16s backoff, on data
            # that never saw the outage.
            for book in self.books.values():
                book.invalid = True
            # A new connection restarts the sequence at 1. Carrying the old
            # value across would report a gap on the first frame of every
            # reconnect and resync a book that is already correct.
            self._last_seq = None
            self._pending_resync = False

            for ticker in self.tickers:
                await self._subscribe(ticker)

            while True:
                # Application-level timeout. The 16-minute silent stall that
                # motivated this had a perfectly healthy ping/pong throughout.
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=self.receive_timeout_s)
                except asyncio.TimeoutError:
                    logger.warning(
                        "no message in %.0fs -- forcing reconnect. TCP liveness "
                        "does not imply data flow.",
                        self.receive_timeout_s,
                    )
                    raise

                self._last_message_ms = _now_ms()
                await self._handle(raw)

                # Resync outside _handle so the resubscribe commands are not
                # issued from inside frame dispatch.
                if self._pending_resync:
                    await self._resync_all()

    # -- protocol ----------------------------------------------------------

    async def _send(self, payload: dict) -> None:
        self._command_id += 1
        payload["id"] = self._command_id
        await self._ws.send(json.dumps(payload))

    async def _subscribe(self, ticker: str) -> None:
        # Record the command id before sending: the ack names only the id, so
        # this map is the sole link from an ack back to its market.
        self._pending_subscriptions[self._command_id + 1] = ticker
        await self._send(
            {
                "cmd": "subscribe",
                "params": {"channels": ["orderbook_delta"], "market_tickers": [ticker]},
            }
        )

    async def _resubscribe(self, ticker: str) -> None:
        """Drop and re-add one ticker to force a fresh snapshot after a gap."""
        sid = self._ticker_sids.pop(ticker, None)
        if sid is not None:
            self._sids.pop(sid, None)
            try:
                await self._send({"cmd": "unsubscribe", "params": {"sids": [sid]}})
            except (ConnectionClosed, OSError):
                raise  # let run() reconnect; a partial resubscribe is worse
        self.books[ticker] = OrderBook(ticker)
        await self._subscribe(ticker)

    async def _handle(self, raw: str) -> None:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("undecodable frame: %.200s", raw)
            return

        msg_type = message.get("type")

        # Sequence first, before any type dispatch.
        #
        # `seq` counts frames on the *connection*, not on a market: a capture of
        # twelve tickers showed one shared sid and one strictly-increasing
        # sequence across all of them. Control frames participate -- `ok` frames
        # carry `seq` in the capture -- so any early return before this point
        # would let a frame consume a sequence number unnoticed and make the
        # *next* frame look like a gap. `subscribed` is the sole exception and
        # is handled inside `_check_sequence` by having no `seq` at all.
        if not self._check_sequence(message):
            return

        if msg_type in ("subscribed", "ok"):
            # Kalshi acknowledges subscriptions in **two different shapes**, and
            # missing the second leaves the registry mostly empty:
            #
            #   subscribed -> msg {"channel", "sid"}   -- no ticker, sid on msg
            #   ok         -> msg {"market_tickers"}   -- ticker present, sid on frame
            #
            # Only the *first* subscribe on a connection gets `subscribed`; every
            # one after it is acked with `ok`. A capture of twelve tickers had
            # exactly one `subscribed` and eleven `ok`. Handling only the first
            # registered 1 of 6 tickers in a live run.
            params = message.get("msg") or {}
            sid = params.get("sid", message.get("sid"))

            tickers = list(params.get("market_tickers") or ())
            if not tickers:
                # `subscribed` names no market, so fall back to the command id
                # we recorded when sending -- the sole correlation available.
                matched = self._pending_subscriptions.pop(message.get("id"), None)
                if matched:
                    tickers = [matched]
            else:
                self._pending_subscriptions.pop(message.get("id"), None)

            if sid is None or not tickers:
                logger.warning(
                    "subscription ack (%s, id=%s) could not be matched to a "
                    "ticker; resync for it will not know its sid",
                    msg_type, message.get("id"),
                )
                return

            for ticker in tickers:
                self._ticker_sids[ticker] = sid
                # One sid serves every ticker on the connection, so a reverse
                # sid -> ticker map cannot exist. Kept as sid -> {tickers}.
                self._sids.setdefault(sid, set()).add(ticker)
            return

        if msg_type == "error":
            # Errors arrive as opaque strings with no correlation back to the
            # pending subscription. Log the whole frame so the context is not
            # lost the way it was in the previous project.
            logger.error("feed error frame: %s", message)
            return

        if msg_type in ("orderbook_snapshot", "orderbook_delta"):
            await self._apply(msg_type, message)
            return

    def _check_sequence(self, message: dict) -> bool:
        """Track the connection sequence. Returns False when a gap was handled.

        Every frame carrying a `seq` participates, including `ok` acknowledgements
        -- in the capture they consume sequence numbers alongside book frames, so
        skipping them would manufacture gaps that are not there.

        On a gap, every book on this connection is invalidated and re-subscribed.
        A gap identifies the connection, never the market, so invalidating only
        one book would leave the others quietly wrong.
        """
        seq = message.get("seq")
        if seq is None:
            return True

        if self._last_seq is not None and seq != self._last_seq + 1:
            if seq <= self._last_seq:
                # Duplicate or reorder rather than loss. Dropping it is correct;
                # applying it would double-count a delta.
                logger.warning(
                    "out-of-order frame seq=%s after %s; dropping", seq, self._last_seq
                )
                return False

            gap = SequenceGap(self._last_seq + 1, seq, tuple(self.books))
            logger.warning("%s", gap)
            for book in self.books.values():
                book.invalid = True
            self._pending_resync = True
            self._last_seq = seq
            return False

        self._last_seq = seq
        return True

    async def _resync_all(self) -> None:
        """Recover from a connection-level gap by reconnecting.

        Reconnecting rather than re-subscribing, deliberately. A gap identifies
        the connection and not the market, so everything on it needs a fresh
        snapshot -- and whether Kalshi answers a *redundant* subscribe with a
        new snapshot or a bare `ok` has not been observed. Building recovery on
        unobserved behaviour is how a resync path comes to exist without ever
        working; a reconnect is the one route already exercised on every
        backoff, and it is guaranteed to re-snapshot.
        """
        self._pending_resync = False
        for book in self.books.values():
            book.invalid = True
        raise ResyncRequired(
            "connection sequence gap -- reconnecting to re-snapshot every book"
        )

    async def _apply(self, msg_type: str, message: dict) -> None:
        payload = message.get("msg") or {}
        ticker = payload.get("market_ticker") or self._sids.get(message.get("sid"))
        if not ticker:
            logger.error("book frame with no resolvable ticker: %s", message)
            return

        book = self.books.get(ticker)
        if book is None:
            return  # not subscribed; ignore rather than inventing state

        seq = message.get("seq")
        observed_ms = _now_ms()

        try:
            if msg_type == "orderbook_snapshot":
                book.apply_snapshot(payload, seq, observed_ms)
            else:
                book.apply_delta(payload, seq, observed_ms)
        except MalformedBookMessage as exc:
            # Never swallow. A book we cannot parse must not keep quoting the
            # last values it happened to hold.
            logger.error("malformed book message: %s", exc)
            book.invalid = True
            return

        if self.on_book_update:
            result = self.on_book_update(book)
            if asyncio.iscoroutine(result):
                await result
