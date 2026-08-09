"""Recording Kalshi's settled outcome for every market discovered.

`kalshi_markets.result` has existed since schema v6 and **no code path has ever
written it**: `upsert_discovered` omitted the column from both its INSERT list
and its `ON CONFLICT` list, so the column was NULL for every row for the
project's life. This module is the writer, and `runner.upsert_discovered` is now
the reader that must not erase it.

Why this is not the settlement pass
-----------------------------------
`settlement.py` also reads finished markets, and the two are deliberately
separate because they select completely different populations. It walks
**orders**, closing paper positions; there are zero real orders, and the only
writers of that table are the auth-gated order endpoint and the demo seeder. So
it can only ever describe markets that were *bet*.

This walks **`kalshi_markets`**, which is every market discovery has ever seen —
roughly 1,400 game markets a day, bet or not. That is the difference between a
calibration sample of nothing and a calibration sample of the whole slate.

Why a separate pass, and not discovery
--------------------------------------
Because discovery cannot see an outcome. `/events?status=open` returns only
`active` markets: 245/245 in `tests/fixtures/events_sports_nested.json`, and
168/168 across MLB, WNBA and NFL on a live probe on 2026-08-09, every one with
`result` an empty string. A market's result becomes visible through
`/markets?event_ticker=…`, after its event has left the open walk. Plumbing the
field through discovery alone — which is the obvious fix, and is also done here
because a field no parser reads is how a payload change goes unnoticed — yields
a column that stays NULL forever. That is this repo's "built but never called"
shape, and it is why the discovery half is not the deliverable.

Only `finalized` is trusted
---------------------------
Kalshi sets `result` at status `determined`, while the settlement timer runs
(`settlement_timer_seconds` reads 60–300 in the capture), and a `disputed`
result can be re-`determined` and `amended`. A determination is not an outcome.
`read_market_result` therefore accepts a result only at `finalized`, so a
reversible answer never enters a permanent record. A market caught mid-timer is
counted `still_unresolved` and picked up on the next pass — it is a routine
state, not an alarm.

What this does NOT establish
----------------------------
- **It is not calibration, and it is not evidence of one.** It supplies the
  outcomes calibration needs. Whether `fair_probability` is calibrated is a
  separate measurement, subject to every rule in `CLAUDE.md` — read `n` first,
  check the parts agree, bucket on the price actually payable.
- **It is not a second opinion on CLV.** Both read Kalshi, so an outcome
  recorded here is not independent evidence that the closing line was beaten.
- **It does not date the pricing.** A row says what happened, never when the
  fair price that is to be scored against it was computed. Anything joining
  this to `recommendations` must state that horizon itself; `last_price` on a
  settled market has already converged on the outcome.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .kalshi.discovery import SETTLED_STATUS, read_market_result
from .store.db import now_ms

logger = logging.getLogger(__name__)

# How long after a game's start to begin asking whether it has settled.
#
# The gate is the **event's commence time**, not the market's `close_ms`. While
# a market is open, `close_time` is the *scheduled* close, which runs up to three
# days past the game (`KXMLBGAME-26AUG092020HOUSD`: game 2026-08-10T03:20Z,
# close 2026-08-13T00:20Z). Gating on it would leave every outcome unrecorded
# for three days. It is kept only as a fallback for a market whose event row is
# missing, where it is at least an upper bound on when the game happened.
#
# Two hours is shorter than any sport in scope, so the first ask usually finds
# the market still active. That is the cheap direction: Kalshi REST is unmetered
# and spends no odds credits, while being late means the calibration sample lags
# reality by a whole pass for no reason.
MIN_AGE_AFTER_COMMENCE_MS = 2 * 60 * 60 * 1000


@dataclass
class MarketResultCounts:
    markets_pending: int = 0
    events_queried: int = 0
    recorded: int = 0
    still_unresolved: int = 0
    # `finalized` and yet unreadable. This is the count that means the wire
    # format moved, and it must never be invisible because it happens to be
    # zero. A market merely waiting on its settlement timer is *not* counted
    # here — that is `still_unresolved`, and conflating the two would bury the
    # alarm under routine traffic twice a day per game.
    refused: int = 0
    errors: list[str] = field(default_factory=list)

    # Always reported, even at zero, for the reason `ScoringCounts` gives:
    # `recorded: 0` alone cannot distinguish "nothing has settled yet" from
    # "nothing was asked" from "everything was refused", and those need
    # completely different responses.
    ALWAYS_REPORT = (
        "markets_pending",
        "recorded",
        "still_unresolved",
        "refused",
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            k: v
            for k, v in self.__dict__.items()
            if v or k in self.ALWAYS_REPORT
        }


def markets_awaiting_result(
    conn, *, now: int, max_events: Optional[int] = None
) -> dict[str, list[str]]:
    """Tickers with no recorded outcome whose game is long enough past, by event.

    Grouped by event because `/markets?event_ticker=…` answers for every market
    on the fixture in one request. Asking per ticker would be two requests for a
    moneyline pair and two chances for them to disagree about one game.

    Ordered most-recently-started first, so a backlog is worked newest-first and
    a market that will never settle — two in the capture have been `closed` with
    no result since February — drifts to the back of the queue instead of
    occupying the head of it forever.
    """
    rows = conn.execute(
        """
        SELECT m.ticker,
               m.event_ticker,
               COALESCE(e.commence_ms, m.close_ms) AS started_ms
        FROM kalshi_markets m
        LEFT JOIN kalshi_events e ON e.event_ticker = m.event_ticker
        WHERE m.result IS NULL
          AND COALESCE(m.event_ticker, '') != ''
          AND COALESCE(e.commence_ms, m.close_ms) <= ?
        ORDER BY started_ms DESC, m.ticker
        """,
        (now - MIN_AGE_AFTER_COMMENCE_MS,),
    ).fetchall()

    pending: dict[str, list[str]] = {}
    for row in rows:
        if max_events is not None and len(pending) >= max_events:
            if row["event_ticker"] not in pending:
                continue
        pending.setdefault(row["event_ticker"], []).append(row["ticker"])
    return pending


def record_result(conn, ticker: str, result: str, *, now: int) -> bool:
    """Write one outcome. `True` if this call is what wrote it.

    `WHERE result IS NULL` makes the write once-only. An outcome that has entered
    the record is never quietly swapped for a different one -- Kalshi can
    re-determine a `disputed` market, and a permanent record that changes under a
    reader is worse than one that is stale, because only the second is visible.
    `status` is set alongside so a row cannot read `active` while carrying an
    outcome; the two would then disagree about whether the game is over.
    """
    cur = conn.execute(
        "UPDATE kalshi_markets SET result = ?, status = ?, last_seen_ms = ? "
        "WHERE ticker = ? AND result IS NULL",
        (result, SETTLED_STATUS, now, ticker),
    )
    return cur.rowcount > 0


async def run_market_result_pass(
    conn,
    kalshi_client,
    *,
    now: Optional[int] = None,
    max_events: Optional[int] = None,
) -> MarketResultCounts:
    """Record Kalshi's outcome for every discovered market that has settled.

    One `GET /markets?event_ticker=…` per event with anything outstanding.
    Kalshi REST is unmetered and this spends no odds credits.

    A failure on one event is recorded and the pass continues, for the reason the
    scoring and settlement passes give: one unreadable payload must not stop the
    other thirty games from being recorded, and an outcome lost is
    indistinguishable from one that never happened.
    """
    stamp = now if now is not None else now_ms()
    counts = MarketResultCounts()

    pending = markets_awaiting_result(conn, now=stamp, max_events=max_events)
    counts.markets_pending = sum(len(t) for t in pending.values())
    if not pending:
        logger.info("market result pass: %s", counts.as_dict())
        return counts

    for event_ticker, tickers in pending.items():
        try:
            payloads = await kalshi_client.markets_for_event(event_ticker)
            counts.events_queried += 1
        except Exception as exc:                                  # noqa: BLE001
            counts.errors.append(f"{event_ticker}: {exc}")
            logger.warning(
                "could not read %s for its outcome: %s", event_ticker, exc
            )
            continue

        # Only the markets this pass is waiting on. The event answers for all of
        # its markets, including ones already recorded, and counting those would
        # make `still_unresolved` grow with history rather than with backlog.
        wanted = set(tickers)
        by_ticker = {
            m.get("ticker"): m
            for m in payloads
            if m.get("ticker") in wanted
        }

        for ticker in tickers:
            market = by_ticker.get(ticker)
            if market is None:
                counts.still_unresolved += 1
                continue

            result = read_market_result(market)
            if result is None:
                if market.get("status") == SETTLED_STATUS:
                    # Finalized and yet unreadable: either `result` is not one
                    # of yes/no -- a 50/50 tie settlement is reachable in sports
                    # and this project has never captured what it reads -- or the
                    # payload contradicts its own `settlement_value_dollars`.
                    # Refused, never guessed: this column feeds calibration,
                    # where a fabricated outcome is a permanent wrong answer
                    # rather than a refused trade.
                    counts.refused += 1
                    counts.errors.append(
                        f"{ticker}: {SETTLED_STATUS} but result "
                        f"{market.get('result')!r} / settlement_value_dollars "
                        f"{market.get('settlement_value_dollars')!r} could not "
                        f"be read as an outcome"
                    )
                    logger.error(
                        "%s is %s and its outcome could not be read; left NULL",
                        ticker, SETTLED_STATUS,
                    )
                else:
                    counts.still_unresolved += 1
                continue

            try:
                if record_result(conn, ticker, result, now=stamp):
                    counts.recorded += 1
            except Exception as exc:                              # noqa: BLE001
                counts.errors.append(f"{ticker}: {exc}")
                logger.exception("could not record the outcome for %s", ticker)

    conn.commit()
    logger.info("market result pass: %s", counts.as_dict())
    return counts
