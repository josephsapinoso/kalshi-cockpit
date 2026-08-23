"""Mirror the venue's record of Joe's hand-placed bets, before Kalshi drops it.

Why this exists, and why it is urgent rather than nice
------------------------------------------------------
Both portfolio endpoints have now been observed to lose history.
`/portfolio/fills` retains roughly three months (measured 2026-08-10: empty on
an account whose settlements then reached back to 2025-11). And
`/portfolio/settlements` -- which the calibration registration originally
called "the safety net" at nine-plus months of reach -- returned 55 records on
2026-08-10 and **22 entirely different ones eight days later**, cursor empty,
one page. A poll that does not happen does not delay the record. It loses it.

This module is the first production caller of any portfolio endpoint in this
project's life. `balance()`, `positions()`, `fills()` and `settlements()` were
all built, tested against their envelopes, and called by nothing -- the
"built but never called" pattern `tasks/lessons.md` records. The calibration
registration (§7.6, as amended) is what finally supplies a caller.

What it writes, and what it refuses to write
--------------------------------------------
- `venue_settlements` -- one row per settled position, mirrored verbatim-ish:
  parsed into the repo's units, never summarised. `INSERT OR IGNORE` on the
  `(ticker, settled_ms)` key makes every poll idempotent.
- `fills` with `source = 'venue_hand'` -- **never** `'engine'`. The gate's
  `_fee_model_verified` counts engine fills only (ADR 0043), and that filter
  landed before this module existed precisely so switching this on cannot move
  a live-trading interlock in either direction.
- `venue_balance_snapshots` -- from `balance_dollars` (a dollar string,
  "20.6583"), **never** the `balance` integer beside it, which is whole cents
  and drops the 0.83c. Observed 2026-08-18, both fields side by side.
- `poll_log` -- one row per endpoint per attempt, **including failures**. Every
  retention tripwire in the registration is a gap between successive
  successful polls, and a failure that writes nothing is invisible: it reads
  exactly like a quiet week in which nothing was bet.

**`positions` is counted and not parsed.** The per-row shape has never been
observed on this account -- both reads returned an empty list -- and this repo
has been burned five separate times by parsers written against imagined wire
formats. The count lands in `poll_log.row_count`; the first non-empty payload
should be captured (`scripts/capture_fills_fixture.py` is the pattern) before
anyone writes a parser.

What this does NOT establish
-----------------------------
- **That the mirror is complete.** A position opened and closed entirely
  between polls, on an endpoint that drops history, is gone. The poll cadence
  bounds that window; it cannot close it.
- **Anything about the fee model.** `fee_predicted` is populated (the column
  is NOT NULL, and a real `fee_actual` beside a prediction is the comparison
  H4 and `core/fees.py` are waiting for) but nothing here evaluates the match.
  That analysis is off-gate by ADR 0043 and belongs to its own harness.
- **Which estimate a position matches.** Matching is analysis (§7.3 of the
  registration), runs on read, and is deliberately not done at ingest: a
  matcher inside the poller would bake today's matching rule into the stored
  record.

Money is integer tenths of a cent. Quantities are REAL (fractional counts are
real: `0.27` and `11.27` are both in the live record). Unreadable resolves to
`None`, never `0` -- and a row whose money fields cannot be read is **skipped
and counted**, never written half-parsed.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from .core.fees import calculate_fee
from .core.prices import dollars_to_tenths
from .kalshi.discovery import parse_ms
from .kalshi.rest import KalshiRestClient
from .store import db as store_db

logger = logging.getLogger(__name__)

# The wire values `source` may take here. 'engine' is reserved for the order
# path and this module must never write it -- see ADR 0043.
VENUE_SOURCE = "venue_hand"


def _fractional_count(value: Any) -> Optional[float]:
    """A `*_count_fp` string ("11.27") to a float count. None when unreadable.

    Not `dollars_to_tenths`: this is a quantity, not money, and the schema's
    convention for quantities is REAL. Negative counts are refused the same way
    negative prices are -- a count is being validated, not trusted.
    """
    if value is None:
        return None
    try:
        as_decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not as_decimal.is_finite() or as_decimal < 0:
        return None
    return float(as_decimal)


@dataclass(frozen=True)
class ParsedSettlement:
    ticker: str
    event_ticker: Optional[str]
    market_result: Optional[str]
    settled_ms: int
    side: str
    contracts: float
    entry_price_tenths: Optional[int]
    fee_cost_tenths: Optional[int]


def parse_settlement(row: dict) -> Optional[ParsedSettlement]:
    """One `/portfolio/settlements` record into the repo's units.

    Returns None -- refusal, not zero -- when the row cannot carry a position:
    no ticker, no settled time, or a count pair that reads as neither side.
    Field names are the ones observed on this account 2026-08-18
    (`data/captures/portfolio_settlements.json`), not the docs' names.

    `revenue` and `value` are deliberately not read: both are the deprecated
    integer-cent legacy fields and both were 0 on every observed record.
    """
    ticker = row.get("ticker")
    settled_ms = parse_ms(row.get("settled_time"))
    if not ticker or settled_ms is None:
        return None

    yes_count = _fractional_count(row.get("yes_count_fp"))
    no_count = _fractional_count(row.get("no_count_fp"))
    if yes_count and yes_count > 0:
        side, contracts, cost_key = "yes", yes_count, "yes_total_cost_dollars"
    elif no_count and no_count > 0:
        side, contracts, cost_key = "no", no_count, "no_total_cost_dollars"
    else:
        # Both zero, or both unreadable. A settlement with no position on
        # either side is not a position; refuse rather than invent a side.
        return None

    # Average entry price: total cost over count, both from the venue. The
    # division happens in Decimal via the dollar string so a fractional count
    # cannot smuggle float error into a money figure.
    entry_price_tenths: Optional[int] = None
    try:
        total_cost = Decimal(str(row.get(cost_key)))
        if total_cost.is_finite() and total_cost >= 0 and contracts > 0:
            entry_price_tenths = dollars_to_tenths(
                total_cost / Decimal(str(contracts))
            )
    except (InvalidOperation, ValueError, TypeError):
        entry_price_tenths = None

    return ParsedSettlement(
        ticker=str(ticker),
        event_ticker=row.get("event_ticker"),
        market_result=row.get("market_result"),
        settled_ms=settled_ms,
        side=side,
        contracts=contracts,
        entry_price_tenths=entry_price_tenths,
        fee_cost_tenths=dollars_to_tenths(row.get("fee_cost")),
    )


@dataclass(frozen=True)
class ParsedFill:
    kalshi_fill_id: str
    ticker: str
    filled_ms: int
    count: float
    price_tenths: int
    is_taker: bool
    fee_actual: Optional[float]
    # The venue's own order id for the order this fill answered (D3,
    # 2026-08-22). Present on every fill in the 2026-08-18 capture and
    # DISCARDED until now — without it a portal-placed order's fill lands
    # labelled `venue_hand` with no join back to the manual_orders row that
    # caused it. Optional: a fill without one still records (refusing a real
    # fill over a missing join key is the wrong way round).
    venue_order_id: Optional[str] = None


def parse_fill(row: dict) -> Optional[ParsedFill]:
    """One `/portfolio/fills` record into the repo's units. None on refusal.

    The shape is the one observed on this account 2026-08-18 -- 25 fills,
    every field present on all 25 (`data/captures/portfolio_fills.json`). The
    price paid is `yes_price_dollars` or `no_price_dollars` **by the fill's own
    `side`**; reading the wrong one books a 1c fill as a 99c one.

    `fee_cost` stays in dollars (REAL) because `fills.fee_actual` is the
    column `_fee_model_verified` compares in dollars. It is the one money field
    in this module not stored in tenths, and that is the existing table's
    contract, not a new decision.
    """
    fill_id = row.get("fill_id")
    ticker = row.get("ticker")
    side = row.get("side")
    if not fill_id or not ticker or side not in ("yes", "no"):
        return None

    # `created_time` is ISO-8601 with microseconds; `ts` is whole seconds.
    # Prefer the precise one, fall back to the coarse one, refuse on neither.
    filled_ms = parse_ms(row.get("created_time"))
    if filled_ms is None:
        ts = row.get("ts")
        filled_ms = int(ts) * 1000 if isinstance(ts, int) and ts > 0 else None
    if filled_ms is None:
        return None

    count = _fractional_count(row.get("count_fp"))
    price_key = "yes_price_dollars" if side == "yes" else "no_price_dollars"
    price_tenths = dollars_to_tenths(row.get(price_key))
    is_taker = row.get("is_taker")
    if count is None or count <= 0 or price_tenths is None:
        return None
    if not isinstance(is_taker, bool):
        # The maker/taker flag is the one field the fee question turns on.
        # A guessed default here would poison the comparison it exists for.
        return None

    order_id = row.get("order_id")
    return ParsedFill(
        kalshi_fill_id=str(fill_id),
        ticker=str(ticker),
        filled_ms=filled_ms,
        count=count,
        price_tenths=price_tenths,
        is_taker=is_taker,
        fee_actual=_fee_dollars(row.get("fee_cost")),
        venue_order_id=str(order_id) if order_id else None,
    )


def _fee_dollars(value: Any) -> Optional[float]:
    """A `fee_cost` dollar string to a float, refusing garbage. None never 0."""
    if value is None:
        return None
    try:
        as_decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not as_decimal.is_finite() or as_decimal < 0:
        return None
    return float(as_decimal)


def parse_balance_tenths(payload: dict) -> Optional[int]:
    """`balance_dollars` to tenths. **Never the `balance` integer.**

    Observed side by side on 2026-08-18: `balance` was 2065 while
    `balance_dollars` was "20.6583". The integer is whole cents and silently
    drops the 0.83c -- the deci-cent error CLAUDE.md opens with, in a wallet.
    """
    return dollars_to_tenths(payload.get("balance_dollars"))


def parse_portfolio_value_tenths(payload: dict) -> Optional[int]:
    """`portfolio_value`, accepted only at the one value whose unit is known.

    The field has been observed exactly once, as the integer `0`, with no
    `_dollars` twin beside it. Zero is zero in every candidate unit, so it is
    stored. **Any non-zero value is refused (None) until the unit is pinned**
    by an observation against a non-empty position list -- guessing cents by
    analogy with `balance` is exactly the convenient-column error, one field
    over. When this starts returning None on a real portfolio, that is the
    prompt to capture a payload and pin the unit, not to widen this function.
    """
    value = payload.get("portfolio_value")
    if value == 0:
        return 0
    return None


def _log(
    conn: sqlite3.Connection,
    *,
    now_ms: int,
    endpoint: str,
    ok: bool,
    row_count: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    conn.execute(
        "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count, error) "
        "VALUES (?, ?, ?, ?, ?)",
        (now_ms, endpoint, 1 if ok else 0, row_count, error),
    )


async def poll_portfolio(
    conn: sqlite3.Connection,
    client: KalshiRestClient,
    *,
    now_ms: int,
) -> dict[str, Any]:
    """One pass over all four endpoints. Every attempt leaves a `poll_log` row.

    Endpoints are independent: a failure on one is logged and the rest still
    run, because the registration's tripwires are per-endpoint and a
    settlements outage must not blind the balance record.

    Returns a summary dict for the caller's log line. The summary is
    convenience; `poll_log` is the record.
    """
    summary: dict[str, Any] = {}

    # -- settlements: the primary statistic's inputs live here ---------------
    summary["settlements"] = await poll_settlements(conn, client, now_ms=now_ms)

    # -- fills: source='venue_hand', never 'engine' (ADR 0043) ---------------
    summary["fills"] = await poll_fills(conn, client, now_ms=now_ms)

    # -- positions: COUNTED, NOT PARSED. Shape never observed. ---------------
    try:
        rows = await client.positions()
    except Exception as exc:  # noqa: BLE001
        _log(conn, now_ms=now_ms, endpoint="positions", ok=False, error=repr(exc))
        summary["positions"] = f"FAILED: {exc}"
    else:
        _log(conn, now_ms=now_ms, endpoint="positions", ok=True, row_count=len(rows))
        summary["positions"] = {"seen": len(rows)}
        if rows:
            # The first observation of the shape. Capture before parsing.
            logger.warning(
                "positions returned %d rows -- the per-row shape has never "
                "been captured; run scripts/capture_fills_fixture.py-style "
                "capture before writing a parser", len(rows),
            )

    # -- balance: dollars string, never the cents integer --------------------
    summary["balance"] = await poll_balance(conn, client, now_ms=now_ms)

    conn.commit()

    # -- the matcher: the reader for everything mirrored above ---------------
    # After the commit, so a matcher failure cannot roll back the mirror --
    # the record is the point and the join is derived from it, rerunnable on
    # the next cycle. Absorbed like the endpoints: the study's bookkeeping
    # must not take down the poller that feeds it.
    try:
        from .estimate_match import run_match_pass
        from .kalshi.quotes import LiveQuoteSource

        summary["match"] = await run_match_pass(
            conn, LiveQuoteSource(rest=client), now_ms=now_ms
        )
    except Exception as exc:  # noqa: BLE001 -- never blind the mirror
        logger.exception("estimate match pass failed: %s", exc)
        summary["match"] = f"FAILED: {exc}"
    return summary


async def poll_settlements(
    conn: sqlite3.Connection,
    client: KalshiRestClient,
    *,
    now_ms: int,
) -> Any:
    """The settlements mirror alone, so it can run on the 5-minute cadence.

    Extracted from `poll_portfolio` for ADR 0064: the daily-loss kill
    switch's producer (`bets.venue_daily_realised_pnl_dollars`) reads this
    table and REFUSES when its freshest successful read is older than
    `bets.TONIGHT_STALE_AFTER_MS` (30 min = 6x this cadence). On the
    12-hour mirror clock alone that refusal would stand almost all day,
    and worse, a mirror read at 10am carries none of the evening's losses
    -- the false negative in the flattering direction, on the exact
    quantity that exists to stop the next bet. The registration argument
    is `poll_fills`'s, unchanged: §7.6 sets a floor on the mirror's
    completeness, and polling an unmetered venue endpoint more often can
    only make the mirror more complete.

    The caller commits; this function only writes, exactly as
    `poll_balance` does, so `poll_portfolio` can reuse it in its own
    transaction.
    """
    try:
        rows = await client.settlements(limit=200)
    except Exception as exc:  # noqa: BLE001 -- every failure must land in poll_log
        _log(conn, now_ms=now_ms, endpoint="settlements", ok=False, error=repr(exc))
        return f"FAILED: {exc}"
    written = refused = 0
    for row in rows:
        parsed = parse_settlement(row)
        if parsed is None:
            refused += 1
            logger.warning("settlement refused, ticker=%s", row.get("ticker"))
            continue
        cursor = conn.execute(
            "INSERT OR IGNORE INTO venue_settlements "
            "(ticker, event_ticker, market_result, settled_ms, side, "
            " contracts, entry_price_tenths, fee_cost_tenths, "
            " position_first_seen_ms, position_time_source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                parsed.ticker, parsed.event_ticker, parsed.market_result,
                parsed.settled_ms, parsed.side, parsed.contracts,
                parsed.entry_price_tenths, parsed.fee_cost_tenths,
                now_ms, "poll_instant",
            ),
        )
        written += cursor.rowcount
    _log(conn, now_ms=now_ms, endpoint="settlements", ok=True, row_count=len(rows))
    return {"seen": len(rows), "new": written, "refused": refused}


async def poll_fills(
    conn: sqlite3.Connection,
    client: KalshiRestClient,
    *,
    now_ms: int,
) -> Any:
    """The fills alone, so they can run on the 5-minute cadence too.

    Extracted from `poll_portfolio` on the 2026-08-21 partner ruling: the
    landing screen's "tonight" strip reads this table, and on the 12-hour
    mirror alone it would say "no bets tonight" at 8pm off a 10am read --
    a false negative in the flattering direction, on the one screen whose
    purpose is to interrupt. **This is not an amendment to the registered
    cadence**: §7.6 sets a floor on the mirror's completeness, and polling
    an unmetered venue endpoint more often can only make the mirror more
    complete. Positions and the matcher stay on their registered 12-hour
    clock (settlements joined this cadence with ADR 0064 -- see
    `poll_settlements`).

    The caller commits; this function only writes, exactly as
    `poll_balance` does, so `poll_portfolio` can reuse it in its own
    transaction.
    """
    try:
        rows = await client.fills(limit=200)
    except Exception as exc:  # noqa: BLE001 -- every failure must land in poll_log
        _log(conn, now_ms=now_ms, endpoint="fills", ok=False, error=repr(exc))
        return f"FAILED: {exc}"
    written = refused = 0
    for row in rows:
        parsed = parse_fill(row)
        if parsed is None:
            refused += 1
            logger.warning("fill refused, id=%s", row.get("fill_id"))
            continue
        predicted = calculate_fee(
            price_tenths=parsed.price_tenths,
            contracts=parsed.count,
            maker=not parsed.is_taker,
        )
        cursor = conn.execute(
            "INSERT OR IGNORE INTO fills "
            "(kalshi_fill_id, ticker, filled_ms, count, price_tenths, "
            " is_taker, fee_actual, fee_predicted, fee_model_used, source, "
            " venue_order_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                parsed.kalshi_fill_id, parsed.ticker, parsed.filled_ms,
                parsed.count, parsed.price_tenths,
                1 if parsed.is_taker else 0, parsed.fee_actual,
                predicted, "model_a_deci", VENUE_SOURCE,
                parsed.venue_order_id,
            ),
        )
        written += cursor.rowcount
    _log(conn, now_ms=now_ms, endpoint="fills", ok=True, row_count=len(rows))
    return {"seen": len(rows), "new": written, "refused": refused}


async def poll_balance(
    conn: sqlite3.Connection,
    client: KalshiRestClient,
    *,
    now_ms: int,
) -> Any:
    """The balance alone: the 5-minute cadence, without the 12-hour mirror.

    Separated because the registration (§7.6 as amended) runs the two on
    different clocks -- the balance is what the stopping rule reads and what
    the operational display shows, while the mirror is the record. The caller
    commits; this function only writes, so `poll_portfolio` can reuse it
    inside its own transaction.
    """
    try:
        payload = await client.balance()
    except Exception as exc:  # noqa: BLE001 -- every failure must land in poll_log
        _log(conn, now_ms=now_ms, endpoint="balance", ok=False, error=repr(exc))
        return f"FAILED: {exc}"
    balance_tenths = parse_balance_tenths(payload)
    conn.execute(
        "INSERT INTO venue_balance_snapshots "
        "(observed_ms, balance_tenths, portfolio_value_tenths) "
        "VALUES (?, ?, ?)",
        (now_ms, balance_tenths, parse_portfolio_value_tenths(payload)),
    )
    _log(conn, now_ms=now_ms, endpoint="balance", ok=True, row_count=1)
    _mark_study_start(conn, now_ms=now_ms, balance_tenths=balance_tenths)
    return {"balance_tenths": balance_tenths}


# Amendment A6's "written once on day 1" meta row. Joe declared the study open
# on 2026-08-18 (his ruling, delegated in-session: start now, top up as
# needed, the $100 cumulative-loss stop is the cap either way), so the first
# successful balance poll after this code lands stamps day 1. Idempotent:
# written exactly once, from the venue's own number, never from memory.
#
# A6 prints the value as "206583 tenths ($20.6583)". Those two cannot both be
# right -- $20.6583 is 20,658 tenths, and the poller's own live read on
# 2026-08-18 stored 20658 -- so the integer in A6 is the dollar string with
# its decimal point dropped, and the registered INTENT (the venue balance on
# day 1, in tenths) is what this writes. Recorded here so nobody "corrects"
# the stored value to the typo.
STUDY_START_MS_KEY = "calibration_study_start_ms"
STUDY_START_BALANCE_KEY = "balance_at_study_start_tenths"


def _mark_study_start(
    conn: sqlite3.Connection, *, now_ms: int, balance_tenths: Optional[int]
) -> None:
    """Stamp the study's day 1 on the first readable balance, exactly once.

    An unreadable balance must not stamp the start: `None` here means the
    venue could not be read, and a start marker with no balance beside it
    would make the A6 row a guess. The next successful poll stamps it.
    """
    if balance_tenths is None:
        return
    if store_db.get_meta(conn, STUDY_START_MS_KEY) is not None:
        return
    store_db._set_meta(conn, STUDY_START_MS_KEY, str(now_ms))
    store_db._set_meta(conn, STUDY_START_BALANCE_KEY, str(balance_tenths))
    logger.info(
        "calibration study day 1 stamped: start_ms=%d balance_tenths=%d",
        now_ms,
        balance_tenths,
    )


# The registered cadence, §7.6 of the calibration registration as amended:
# the full mirror every 12 hours, the balance every 5 minutes -- with fills
# (2026-08-21 ruling) and settlements (ADR 0064) riding the 5-minute clock
# because two consumers refuse on a stale read; §7.6 is a floor, and polling
# an unmetered endpoint more often only raises completeness. Constants rather
# than configuration, deliberately -- the cadence is REGISTERED, and a knob
# invites the deployed value to drift from the protocol without anyone
# deciding it. Changing these is amending the registration, and should read
# like it.
MIRROR_INTERVAL_S = 12 * 3600
BALANCE_INTERVAL_S = 300


async def poll_portfolio_forever(
    db_path,
    client: KalshiRestClient,
    *,
    mirror_interval_s: float = MIRROR_INTERVAL_S,
    balance_interval_s: float = BALANCE_INTERVAL_S,
    sleep=asyncio.sleep,
    clock=time.time,
    max_cycles: Optional[int] = None,
) -> None:
    """The poller as a long-running task beside the chain runner.

    Every `balance_interval_s` it snapshots the balance; whenever
    `mirror_interval_s` has elapsed since the last full mirror it runs
    `poll_portfolio` instead, which includes the balance. The first cycle is a
    full mirror, so a restart re-anchors the record immediately rather than
    twelve hours later -- restarts are exactly when a gap is most likely to be
    open.

    **A failed cycle is logged and the loop continues.** The failure record is
    `poll_log`, written inside `poll_portfolio`/`poll_balance` themselves; the
    registration's gap tripwires are the detection mechanism for a poller that
    keeps failing, and they only work if the loop survives to keep attempting.
    The catch-all below is therefore not swallowing errors -- it is what makes
    the error record complete. Only `CancelledError` exits, because the caller
    cancelling the task is the one legitimate way this loop ends.

    **Own connection, on purpose.** The chain runner's connection is used
    sequentially by its pass; sharing it from a concurrent task would
    interleave two transactions on one handle. A second connection in the same
    process is what WAL is for, and every connection already carries the busy
    timeout.

    `sleep`, `clock` and `max_cycles` exist for tests. Production callers pass
    none of them.
    """
    conn = store_db.connect(db_path)
    try:
        last_mirror: Optional[float] = None
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            cycles += 1
            now = clock()
            now_ms = int(now * 1000)
            try:
                if last_mirror is None or now - last_mirror >= mirror_interval_s:
                    summary = await poll_portfolio(conn, client, now_ms=now_ms)
                    last_mirror = now
                    logger.info("portfolio mirror: %s", summary)
                else:
                    result = await poll_balance(conn, client, now_ms=now_ms)
                    # Fills ride the balance cadence (2026-08-21 ruling) so
                    # the landing screen's "tonight" strip is at most minutes
                    # behind the venue, not hours. See `poll_fills` for why
                    # this is not a registration amendment. Settlements ride
                    # it too (ADR 0064): the daily-loss kill switch reads the
                    # mirror and refuses when it is older than 30 minutes, so
                    # on the 12-hour clock alone the order path would be
                    # refused nearly all day -- see `poll_settlements`.
                    fills_result = await poll_fills(conn, client, now_ms=now_ms)
                    settle_result = await poll_settlements(
                        conn, client, now_ms=now_ms
                    )
                    conn.commit()
                    logger.debug(
                        "balance snapshot: %s; fills: %s; settlements: %s",
                        result, fills_result, settle_result,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 -- see the docstring
                logger.exception("portfolio poll cycle failed; loop continues")
            await sleep(balance_interval_s)
    finally:
        conn.close()
