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
`read_market_result` accepts a result only at `finalized`, so a reversible
answer never enters a permanent record. The reasoning, with its evidence stated
honestly:

- **Measured:** 42/42 markets returned by `?status=settled` report status
  `finalized`; `finalized` is itself rejected as a status filter with HTTP 400.
- **Measured:** the capture carries `settlement_timer_seconds` values of 60, 90,
  120 and 300, so a settlement timer of 60–300s exists as a *field*.
- **Not measured, and stated as inference:** that `result` is populated at status
  `determined` while that timer runs. `tests/fixtures/markets_settled.json`
  contains **zero** `determined` markets, and its own `result_while_active` and
  `terminal_status_with_empty_result` metadata arrays are both empty. The
  premise is inferred from the existence of the field and from Kalshi's
  documented `determined → finalized` lifecycle, not observed. Refusing anything
  short of `finalized` is therefore the *conservative* reading of an unmeasured
  transition, which is the right way round: if the inference is wrong, this pass
  is merely one settlement-timer late.

A market caught before `finalized` is counted `still_unresolved` and picked up on
the next pass — a routine state, not an alarm.

Bounded, and the bounds are visible
-----------------------------------
Three populations leave the queue, and each has its own counter, because they
need completely different responses and one bucket over all of them is how a
leak hides:

- `still_unresolved` — asked, not settled yet. Resolves on its own, usually
  within a pass or two.
- `refused` / `unreadable_total` — `finalized` and yet unreadable. Refused, never
  guessed, and **asked only once**: the market is stamped `status = 'finalized'`
  with `result` still NULL, which is the state "we asked, Kalshi answered, and
  the answer was not an outcome". Without that stamp the row stays in the queue
  and re-refuses on every pass forever — 2 markets × 96 passes = 192 ERROR lines
  a day from one tied game, which is the shape this repo already has a scar
  from. A logging rate is a property of the caller, and at a 900s cadence a
  per-pass ERROR is a flood.
- `abandoned_total` — the game commenced longer ago than
  `MarketResultConfig.max_age_after_commence_s`. Dropped so a never-settling
  event stops costing requests forever. It is a real loss and is named as one:
  a genuinely late settlement past that window is never recorded.

What this does NOT establish
----------------------------
- **Nothing reads this column.** `kalshi_markets.result` has zero readers today:
  `analysis/clv.py` reads `st.result` from the **`settlements`** table, and
  `warehouse/models/marts/mart_calibration.sql` reads the `settlements` parquet.
  The honest phrasing is that **calibration now has inputs**, not that
  calibration is now possible — the reader is still unwritten.
- **It is not calibration, and it is not evidence of one.** Whether
  `fair_probability` is calibrated is a separate measurement, subject to every
  rule in `CLAUDE.md` — read `n` first, check the parts agree, bucket on the
  price actually payable.
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

from .config import MarketResultConfig
from .kalshi.discovery import SETTLED_STATUS, read_market_result
from .store.db import now_ms

logger = logging.getLogger(__name__)

DAY_MS = 24 * 60 * 60 * 1000

# How many event failures are carried into the merged `pass N ok` line. The
# counts dict is embedded in one log record, so an unbounded list makes a bad
# minute unreadable rather than more informative -- and the 962-line burst that
# hid this project's boot lines is the reason that matters. The count itself is
# never truncated; only the strings are.
MAX_REPORTED_ERRORS = 5


@dataclass
class MarketResultCounts:
    """Per-pass events, plus two standing gauges named `_total`.

    The `_total` fields are properties of the whole database, not of this pass:
    how many markets are currently stuck in each terminal-but-unrecorded state.
    They are gauges precisely because those states recur -- and a state that
    recurs on every pass must be reported as a level, not raised as an
    exception, or it becomes 96 identical ERROR lines a day.
    """

    markets_pending: int = 0
    events_queried: int = 0
    recorded: int = 0
    still_unresolved: int = 0
    # `finalized` and yet unreadable, **first time only**. This is the count
    # that means the wire format moved, and it must never be invisible because
    # it happens to be zero. A market merely waiting on its settlement timer is
    # *not* counted here -- that is `still_unresolved`, and conflating the two
    # would bury the alarm under routine traffic twice a day per game.
    refused: int = 0
    # The standing population of the same thing: every market that is stamped
    # terminal with no readable outcome. `refused` returns to 0 the pass after
    # a tie settles; this does not, so the population never becomes invisible.
    unreadable_total: int = 0
    # Markets dropped from the queue for being too old to keep asking about.
    # Deliberately NOT folded into `still_unresolved`: that bucket means "an
    # MLB game currently in the 7th inning", and one counter covering both a
    # state that resolves in an hour and a state that never resolves cannot
    # show a leak.
    abandoned_total: int = 0
    # The single oldest abandoned market, named. One bounded string rather than
    # a growing list: enough to identify the population from a phone, and it
    # cannot itself become the flood.
    abandoned_oldest: str = ""
    # Events with work outstanding that were not asked about this pass because
    # `max_events_per_pass` capped the queue. Silent truncation reads as
    # "covered everything" when it didn't.
    deferred_events: int = 0
    errors: list[str] = field(default_factory=list)

    # Always reported, even at zero, for the reason `ScoringCounts` gives:
    # `recorded: 0` alone cannot distinguish "nothing has settled yet" from
    # "nothing was asked" from "everything was refused", and those need
    # completely different responses. The two gauges are here for the same
    # reason in reverse -- a bound that only appears in the log once it has
    # dropped something reads as no bound at all until the day it bites.
    ALWAYS_REPORT = (
        "markets_pending",
        "recorded",
        "still_unresolved",
        "refused",
        "unreadable_total",
        "abandoned_total",
    )

    def as_dict(self) -> dict[str, Any]:
        out = {
            k: v
            for k, v in self.__dict__.items()
            if v or k in self.ALWAYS_REPORT
        }
        if len(self.errors) > MAX_REPORTED_ERRORS:
            out["errors"] = [
                *self.errors[:MAX_REPORTED_ERRORS],
                f"... and {len(self.errors) - MAX_REPORTED_ERRORS} more",
            ]
        return out


@dataclass(frozen=True)
class PendingWork:
    """What to ask about this pass, and what was left out of that answer.

    Returned as one object rather than a bare dict so a caller cannot take the
    queue without also being handed the population the queue excludes. The
    bound and the report of the bound arrive together or not at all.
    """

    by_event: dict[str, list[str]]
    abandoned_total: int = 0
    abandoned_oldest: str = ""
    deferred_events: int = 0

    @property
    def market_count(self) -> int:
        return sum(len(t) for t in self.by_event.values())


# The queue, and the two populations excluded from it, share one shape so the
# three can never drift apart: unrecorded, attached to an event, and carrying a
# usable start time.
#
# The start time gate is the **event's commence time**, not the market's
# `close_ms`. While a market is open, `close_time` is the *scheduled* close,
# which runs up to three days past the game (`KXMLBGAME-26AUG092020HOUSD`: game
# 2026-08-10T03:20Z, close 2026-08-13T00:20Z). Gating on it would leave every
# outcome unrecorded for three days. It is kept only as a fallback for a market
# whose event row is missing, where it is at least an upper bound on when the
# game happened.
_PENDING_FROM = """
    FROM kalshi_markets m
    LEFT JOIN kalshi_events e ON e.event_ticker = m.event_ticker
    WHERE m.result IS NULL
      AND COALESCE(m.event_ticker, '') != ''
      AND COALESCE(m.status, '') != ?
"""


def markets_awaiting_result(
    conn,
    *,
    now: int,
    config: Optional[MarketResultConfig] = None,
    max_events: Optional[int] = None,
) -> PendingWork:
    """Tickers with no recorded outcome whose game is inside the ask window.

    Grouped by event because `/markets?event_ticker=…` answers for every market
    on the fixture in one request. Asking per ticker would be two requests for a
    moneyline pair and two chances for them to disagree about one game.

    Three exclusions, each of which was an unbounded retry before:

    - **Too new.** The game has not had time to finish
      (`min_age_after_commence_s`, default two hours — shorter than any sport in
      scope, so the first ask usually finds the market still active. That is the
      cheap direction: Kalshi REST is unmetered and spends no odds credits,
      while being late means the calibration sample lags reality for no reason).
    - **Too old.** Past `max_age_after_commence_s`, the market is presumed never
      to settle and is dropped — counted in `abandoned_total`, never silently.
      Ordering the queue newest-first, which is what this function used to do
      about it, only reorders: with no cap nothing is ever dropped, so on live
      (`max_events` unset) ordering bought nothing at all.
    - **Already answered, unreadably.** `status = 'finalized'` with `result`
      still NULL is the stamp `run_market_result_pass` leaves on a market Kalshi
      called final and this code refused to read. Without excluding it the row
      is re-queried and re-refused on every pass, permanently.

    `max_events` overrides `config.max_events_per_pass`, for tests that want the
    cap without an environment.
    """
    config = config or MarketResultConfig()
    cap = max_events if max_events is not None else config.max_events_per_pass
    newest = now - config.min_age_after_commence_ms
    oldest = now - config.max_age_after_commence_ms

    rows = conn.execute(
        f"""
        SELECT m.ticker,
               m.event_ticker,
               COALESCE(e.commence_ms, m.close_ms) AS started_ms
        {_PENDING_FROM}
          AND COALESCE(e.commence_ms, m.close_ms) <= ?
          AND COALESCE(e.commence_ms, m.close_ms) > ?
        ORDER BY started_ms DESC, m.ticker
        """,
        (SETTLED_STATUS, newest, oldest),
    ).fetchall()

    pending: dict[str, list[str]] = {}
    deferred: set[str] = set()
    for row in rows:
        event = row["event_ticker"]
        if cap is not None and event not in pending and len(pending) >= cap:
            deferred.add(event)
            continue
        pending.setdefault(event, []).append(row["ticker"])

    return PendingWork(
        by_event=pending,
        deferred_events=len(deferred),
        **_abandoned(conn, oldest=oldest, now=now),
    )


def _abandoned(conn, *, oldest: int, now: int) -> dict[str, Any]:
    """How many markets the age bound is dropping, and the oldest one by name.

    Separate query rather than a second pass over the rows above, because those
    rows are exactly the ones this excludes. Counted every pass and reported
    every pass: a workflow that bounds its coverage and does not say what it
    dropped reads as "covered everything" when it didn't.
    """
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS n,
               MIN(COALESCE(e.commence_ms, m.close_ms)) AS oldest_ms
        {_PENDING_FROM}
          AND COALESCE(e.commence_ms, m.close_ms) <= ?
        """,
        (SETTLED_STATUS, oldest),
    ).fetchone()
    total = row["n"] or 0
    if not total:
        return {"abandoned_total": 0, "abandoned_oldest": ""}

    named = conn.execute(
        f"""
        SELECT m.ticker
        {_PENDING_FROM}
          AND COALESCE(e.commence_ms, m.close_ms) <= ?
        ORDER BY COALESCE(e.commence_ms, m.close_ms) ASC, m.ticker
        LIMIT 1
        """,
        (SETTLED_STATUS, oldest),
    ).fetchone()
    days = max(0, (now - (row["oldest_ms"] or now))) // DAY_MS
    return {
        "abandoned_total": total,
        "abandoned_oldest": f"{named['ticker']} ({days}d)",
    }


def count_unreadable(conn) -> int:
    """Markets stamped terminal with no readable outcome. A standing gauge.

    Zero is the healthy state and is reported anyway. This is the population a
    human has to look at — the wire format carrying something `read_market_result`
    does not recognise, a 50/50 tie among them — and after the once-only stamp
    the per-pass `refused` counter goes quiet, so without this the population
    would disappear from the log the pass after it appeared.
    """
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM kalshi_markets "
        "WHERE result IS NULL AND status = ?",
        (SETTLED_STATUS,),
    ).fetchone()
    return row["n"] or 0


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


def mark_unreadable(conn, ticker: str, *, now: int) -> bool:
    """Stamp a market as asked-and-unanswerable. **No outcome is written.**

    `result` stays NULL — the refusal is not being softened, and a tie is not
    being guessed into a side. What changes is only the *consequence* of the
    refusal: `status` moves to `finalized`, and `finalized` with a NULL `result`
    is the one state that means "Kalshi called this final and the answer was not
    yes or no". `markets_awaiting_result` excludes it, so the market is asked
    about once and refused once instead of on all 96 passes of every day
    thereafter.

    The cost, stated: if Kalshi later amends that market to a readable outcome —
    a `disputed` result can be re-determined — this pass will not pick it up.
    The row stays NULL and stays counted in `unreadable_total`, which is where a
    human would go looking. Reversing it is one UPDATE, not a schema change,
    because nothing about this stamp is a new column.
    """
    cur = conn.execute(
        "UPDATE kalshi_markets SET status = ?, last_seen_ms = ? "
        "WHERE ticker = ? AND result IS NULL",
        (SETTLED_STATUS, now, ticker),
    )
    return cur.rowcount > 0


def markets_by_ticker(payloads: Any, *, wanted: set[str]) -> dict[str, dict]:
    """The wanted markets out of one event's payload, keyed by ticker.

    A function, and called inside the caller's `try`, because it is the half of
    the per-event work that used to sit *outside* it. The `await` was guarded
    and the dict comprehension immediately after was not, so a client returning
    a bare list of strings escaped with `AttributeError` and one returning
    `None` escaped with `TypeError` — verified empirically, not reasoned.

    Unreachable through `KalshiRestClient` today, which always returns a list of
    dicts. That is the point: the safety of this module rested on an invariant
    enforced in `kalshi/rest.py` and asserted in neither file. What a raise
    escaping here becomes is a crash loop — `tempo.completed_full_pass` runs
    *after* this pass, so `last_full_ms` never advances, `pass_kind` returns
    `"full"` again immediately, the same deterministic raise hits five times,
    `LoopFailed` ends the process, `wait -n` takes the container down, Fly
    restarts, and the same row is still in the same volume. Recovery would need
    flyctl. This pass is the first whose input is an unbounded, ever-growing set
    of historical rows, which is what makes a DB-state-driven raise plausible
    here rather than theoretical.

    So the shape is checked and refused by name. A refusal is one counted event
    error and the pass continues; an escape is the container.
    """
    if not isinstance(payloads, list):
        raise TypeError(
            f"markets_for_event returned {type(payloads).__name__}, not a list"
        )
    out: dict[str, dict] = {}
    for market in payloads:
        if not isinstance(market, dict):
            raise TypeError(
                f"a market in the payload is {type(market).__name__}, not a dict"
            )
        ticker = market.get("ticker")
        if ticker in wanted:
            out[ticker] = market
    return out


async def run_market_result_pass(
    conn,
    kalshi_client,
    *,
    now: Optional[int] = None,
    config: Optional[MarketResultConfig] = None,
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
    config = config or MarketResultConfig()
    counts = MarketResultCounts()

    work = markets_awaiting_result(
        conn, now=stamp, config=config, max_events=max_events
    )
    counts.markets_pending = work.market_count
    counts.abandoned_total = work.abandoned_total
    counts.abandoned_oldest = work.abandoned_oldest
    counts.deferred_events = work.deferred_events
    counts.unreadable_total = count_unreadable(conn)
    if not work.by_event:
        logger.info("market result pass: %s", counts.as_dict())
        return counts

    for event_ticker, tickers in work.by_event.items():
        try:
            payloads = await kalshi_client.markets_for_event(event_ticker)
            counts.events_queried += 1
            # Only the markets this pass is waiting on. The event answers for
            # all of its markets, including ones already recorded, and counting
            # those would make `still_unresolved` grow with history rather than
            # with backlog. Inside the `try` -- see `markets_by_ticker`.
            by_ticker = markets_by_ticker(payloads, wanted=set(tickers))
        except Exception as exc:                                  # noqa: BLE001
            counts.errors.append(f"{event_ticker}: {exc}")
            logger.warning(
                "could not read %s for its outcome: %s", event_ticker, exc
            )
            continue

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
                    #
                    # Stamped first, so the ERROR below is logged once in the
                    # life of the market rather than once per pass. If the stamp
                    # fails the row stays in the queue, which is the safe way for
                    # this to break: a repeated question, not a lost refusal.
                    try:
                        mark_unreadable(conn, ticker, now=stamp)
                    except Exception as exc:                      # noqa: BLE001
                        counts.errors.append(f"{ticker}: {exc}")
                        logger.exception(
                            "could not stamp %s as unreadable; it will be asked "
                            "again next pass", ticker,
                        )
                    counts.refused += 1
                    counts.unreadable_total += 1
                    counts.errors.append(
                        f"{ticker}: {SETTLED_STATUS} but result "
                        f"{market.get('result')!r} / settlement_value_dollars "
                        f"{market.get('settlement_value_dollars')!r} could not "
                        f"be read as an outcome"
                    )
                    logger.error(
                        "%s is %s and its outcome could not be read; left NULL "
                        "and not asked about again. It stays counted in "
                        "unreadable_total.",
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
