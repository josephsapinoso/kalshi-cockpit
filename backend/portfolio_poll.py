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
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from .core.fees import calculate_fee
from .core.prices import dollars_to_tenths
from .kalshi.discovery import parse_ms
from .kalshi.rest import KalshiRestClient, parse_position_fp
from .store import db as store_db

logger = logging.getLogger(__name__)

# The wire values `source` may take here. 'engine' is reserved for the order
# path and this module must never write it -- see ADR 0043.
VENUE_SOURCE = "venue_hand"

#: How long a `venue_positions` snapshot is kept. The writer deletes older
#: rows in the same transaction as the snapshot it just wrote, so the table
#: bounds itself whether or not the runner's slow pass -- where
#: `store/retention.py` runs -- is alive; that loop has been observed down
#: while this one was up. The only production reader (`bets.open_positions`)
#: takes the newest successful poll, so any window past
#: `bets.TONIGHT_STALE_AFTER_MS` (30 minutes) serves it; seven days keeps a
#: week of snapshots to diagnose against, at (positions held) x 288 rows a
#: day.
VENUE_POSITIONS_RETENTION_MS = 7 * 24 * 3600 * 1000


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


@dataclass(frozen=True)
class ParsedPosition:
    """One `/portfolio/positions` row: the wire's text verbatim, plus three
    derived columns that are `None` -- never 0 -- when unreadable.

    Unlike `ParsedFill` and `ParsedSettlement`, `parse_position` never
    refuses the whole row. The verbatim strings are the record of what the
    venue said, and they are worth keeping even when a derived value is not
    computable from them -- the next reader can check the derivation against
    the source without another capture. What IS refused is the derived
    figure, and `bets.open_positions` refuses its sum when any row's
    `exposure_tenths` is `None`, rather than summing the rest.
    """

    ticker: Optional[str]
    exchange_index: Optional[int]
    position_fp: Optional[str]
    market_exposure_dollars: Optional[str]
    total_traded_dollars: Optional[str]
    fees_paid_dollars: Optional[str]
    realized_pnl_dollars: Optional[str]
    last_updated_ts: Optional[str]
    #: REAL quantity, `abs(position_fp)`; the schema's convention for a count.
    contracts: Optional[float]
    #: 'yes' | 'no' from the sign of `position_fp`; None at zero or unreadable.
    side: Optional[str]
    #: Integer tenths of a cent: EXPOSURE AT COST, from
    #: `market_exposure_dollars`. Money in, before fees. Not market value.
    exposure_tenths: Optional[int]


def _verbatim(value: Any) -> Optional[str]:
    """The wire value as text, exactly. A string is itself; anything else
    is its JSON so an integer, a bool and a nested object all survive
    unambiguously. `None` stays `None` -- an absent field is not `'null'`."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


def parse_position(row: dict) -> ParsedPosition:
    """One `/portfolio/positions` row into the mirror's columns.

    The shape is the one observed on this account 2026-08-30
    (`tests/test_rest.py::OBSERVED_POSITION_ROW`): `position_fp` a
    fixed-point string, signed by side; `market_exposure_dollars` and its
    three siblings six-decimal dollar strings; `last_updated_ts` ISO-8601;
    `exchange_index` an integer.

    - `contracts`/`side` come through `kalshi.rest.parse_position_fp`
      (Decimal; never `int()`, which misreads "22.88", never `float`
      first). The sign is the side per the venue's convention; the
      magnitude is the count.
    - `exposure_tenths` comes through `core.prices.dollars_to_tenths`, the
      wallet's one dollars-to-tenths spelling: `Decimal * 1000`,
      ROUND_HALF_UP to a whole tenth, so a fractional-contract exposure
      such as "7.641920" (7641.92 tenths) lands on the tenth grid within
      +-0.05 tenths. That helper also refuses a negative -- deliberately
      kept here: whether the venue signs a NO-side exposure has never been
      observed, and `abs()` would be a guess wearing a number.

    Unreadable resolves to `None`, never 0, per column; the verbatim text is
    kept either way. This function establishes nothing about fees (whether
    the exposure includes them is untested) and reads nothing from
    `event_positions`.
    """
    ticker = row.get("ticker")
    exchange_index = row.get("exchange_index")
    quantity = parse_position_fp(row.get("position_fp"))
    if quantity is None:
        contracts: Optional[float] = None
        side: Optional[str] = None
    else:
        contracts = float(abs(quantity))
        side = "yes" if quantity > 0 else "no" if quantity < 0 else None
    return ParsedPosition(
        ticker=str(ticker) if ticker is not None else None,
        exchange_index=(
            exchange_index
            if isinstance(exchange_index, int)
            and not isinstance(exchange_index, bool)
            else None
        ),
        position_fp=_verbatim(row.get("position_fp")),
        market_exposure_dollars=_verbatim(row.get("market_exposure_dollars")),
        total_traded_dollars=_verbatim(row.get("total_traded_dollars")),
        fees_paid_dollars=_verbatim(row.get("fees_paid_dollars")),
        realized_pnl_dollars=_verbatim(row.get("realized_pnl_dollars")),
        last_updated_ts=_verbatim(row.get("last_updated_ts")),
        contracts=contracts,
        side=side,
        exposure_tenths=dollars_to_tenths(row.get("market_exposure_dollars")),
    )


def log_poll_attempt(
    conn: sqlite3.Connection,
    *,
    now_ms: int,
    endpoint: str,
    ok: bool,
    row_count: Optional[int] = None,
    error: Optional[str] = None,
) -> int:
    """Write the attempt; return the new `poll_log.id`, which a mirror row
    that came from this attempt must carry (`venue_positions.poll_log_id`)."""
    cursor = conn.execute(
        "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count, error) "
        "VALUES (?, ?, ?, ?, ?)",
        (now_ms, endpoint, 1 if ok else 0, row_count, error),
    )
    return int(cursor.lastrowid)


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

    **Each step commits before the next network call, and that is a lock
    property rather than a durability one.** Until 2026-08-31 the four steps
    shared one transaction: `poll_settlements` INSERTs, which acquires SQLite's
    write lock, and nothing released it until the single commit **three Kalshi
    round trips later**. Every other writer landing in that window waited out
    `BUSY_TIMEOUT_MS` and raised -- `store_closing_line` on the scoring pass
    most often, which kills the whole pass and loses closing lines that cannot
    be re-observed.

    The comment below this block reasons carefully about **rollback scope**
    ("so a matcher failure cannot roll back the mirror") and says nothing about
    **lock duration**. They are different questions and only one had been asked.

    **Nothing that is relied upon becomes less atomic.** The four steps write
    independent records to different tables from different endpoints, each an
    `INSERT OR IGNORE`; a failure in one never made the rows already written
    wrong, and each endpoint's outcome is recorded in `poll_log` separately
    either way. The rule: **never hold a write transaction across an `await`
    that performs I/O** -- a lock is held in wall-clock time and an `await` is
    an unbounded amount of it.
    """
    summary: dict[str, Any] = {}

    # -- settlements: the primary statistic's inputs live here ---------------
    summary["settlements"] = await poll_settlements(conn, client, now_ms=now_ms)
    conn.commit()

    # -- fills: source='venue_hand', never 'engine' (ADR 0043) ---------------
    summary["fills"] = await poll_fills(conn, client, now_ms=now_ms)
    conn.commit()

    # -- positions: counted in poll_log AND mirrored (schema v33) -----------
    summary["positions"] = await poll_positions(conn, client, now_ms=now_ms)
    conn.commit()

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
        # Every sibling endpoint's failure lands in poll_log; until 2026-08-29
        # this one landed only in a log line, and `flyctl logs` is lossy -- a
        # matcher throwing on every mirror for a week was invisible. The
        # commit is deliberate: this runs after the mirror's own commit above,
        # and a failure row left riding an open transaction until the next
        # fast cycle is a row a crash silently discards.
        log_poll_attempt(
            conn, now_ms=now_ms, endpoint="match", ok=False, error=repr(exc)
        )
        conn.commit()
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
        log_poll_attempt(
            conn, now_ms=now_ms, endpoint="settlements", ok=False,
            error=repr(exc),
        )
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
    log_poll_attempt(
        conn, now_ms=now_ms, endpoint="settlements", ok=True,
        row_count=len(rows),
    )
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
    complete. **The matcher** stays on the registered 12-hour clock, and it
    is now the only thing that does: settlements joined this cadence with
    ADR 0064 (`poll_settlements`) and positions on 2026-08-29
    (`poll_positions`). The matcher is the one of the four that writes a
    registered variable, which is why it did not come with them.

    The caller commits; this function only writes, exactly as
    `poll_balance` does, so `poll_portfolio` can reuse it in its own
    transaction.
    """
    try:
        rows = await client.fills(limit=200)
    except Exception as exc:  # noqa: BLE001 -- every failure must land in poll_log
        log_poll_attempt(
            conn, now_ms=now_ms, endpoint="fills", ok=False, error=repr(exc)
        )
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
    log_poll_attempt(
        conn, now_ms=now_ms, endpoint="fills", ok=True, row_count=len(rows)
    )
    return {"seen": len(rows), "new": written, "refused": refused}


async def poll_positions(
    conn: sqlite3.Connection,
    client: KalshiRestClient,
    *,
    now_ms: int,
) -> Any:
    """The open positions, mirrored: counted in `poll_log` AND stored in
    `venue_positions`, on the 5-minute cadence.

    **Until schema v33 this counted and discarded.** The docstring here read
    *"Still COUNTED, NOT PARSED"* and the loop below it logged a warning that
    the per-row shape had *"never been captured"*. The shape was captured on
    2026-08-30 (`scripts/capture_positions_fixture.py`;
    `tests/test_rest.py::OBSERVED_POSITION_ROW` carries it), so from that day
    the warning was false and the discard was a choice. `bets.open_positions`
    meanwhile served "Open now: N" beside an unconditional refusal where the
    money figure belonged (ADR 0101 section 2.3, third reason). Now every row
    the venue returns is written through `parse_position`: the wire text
    verbatim, three derived columns that are NULL when unreadable, all stamped
    with the `poll_log` row this call just wrote -- so the count and the sum a
    reader takes from them come from ONE venue read with ONE stamp.

    **`poll_log.row_count` is written exactly as before**, from `len(rows)`,
    and stays the count the desk serves. A failed call leaves its `poll_log`
    row and writes nothing to the mirror; the previous snapshot stays the
    newest. After a successful write, rows older than
    `VENUE_POSITIONS_RETENTION_MS` are deleted in the same transaction -- the
    table bounds itself (see the constant for why not `store/retention.py`).

    Extracted from `poll_portfolio` (2026-08-29) for the reason `poll_fills`
    and `poll_settlements` were extracted before it: a consumer refuses on a
    stale read, and on the 12-hour mirror alone the refusal is the wrong one.
    Since 2026-08-26 Joe places real hand bets through `/api/manual-orders`
    one contract at a time, so a bet he just placed did not move the count for
    up to twelve hours -- and only ever *looked* fresh because this instance's
    containers keep restarting and `poll_portfolio_forever`'s first cycle is
    a full mirror; the freshness was the boot clock, not the poller.

    **This is not an amendment to the registered cadence, and the
    registration draws the line itself.** A1 sets `fills`, `settlements` and
    `positions` to 12 hours as a FLOOR on the mirror's completeness -- polling
    an unmetered venue endpoint more often can only make the mirror more
    complete -- and A7 separates an *operational clock* from an *analysis
    clock*, granting the operational one a 5-minute cadence in those words.
    A7's reason for keeping the two apart is an unbounded number of implicit
    looks at a stopping arm, and it does not reach here: **no registered
    statistic reads `positions` or `venue_positions`.** `MIRROR_INTERVAL_S`
    is untouched, and `run_match_pass` -- which does write a registered
    variable (`outcome_win`) -- stays on it.

    The caller commits; this function only writes, exactly as `poll_balance`
    does, so `poll_portfolio` can reuse it inside its own transaction. The
    one network `await` is the first statement, before any write, which is
    the property `tests/test_poller_holds_no_lock_across_io.py` guards in the
    callers.

    Returns `{"seen", "stored", "exposure_unreadable"}`: rows the venue
    returned, rows written (always equal -- a row is never refused whole), and
    rows whose `exposure_tenths` is NULL, which the reader will refuse to sum.
    """
    try:
        rows = await client.positions()
    except Exception as exc:  # noqa: BLE001 -- every failure must land in poll_log
        log_poll_attempt(
            conn, now_ms=now_ms, endpoint="positions", ok=False,
            error=repr(exc),
        )
        return f"FAILED: {exc}"
    poll_log_id = log_poll_attempt(
        conn, now_ms=now_ms, endpoint="positions", ok=True,
        row_count=len(rows),
    )
    unreadable = 0
    for row in rows:
        parsed = parse_position(row if isinstance(row, dict) else {})
        if parsed.exposure_tenths is None:
            unreadable += 1
            logger.warning(
                "positions: exposure at cost did not parse for %r "
                "(market_exposure_dollars=%r); stored verbatim with the "
                "derived column NULL, and the staked figure will refuse",
                parsed.ticker, parsed.market_exposure_dollars,
            )
        conn.execute(
            "INSERT INTO venue_positions "
            "(poll_log_id, polled_ms, ticker, exchange_index, position_fp, "
            " market_exposure_dollars, total_traded_dollars, fees_paid_dollars, "
            " realized_pnl_dollars, last_updated_ts, contracts, side, "
            " exposure_tenths) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                poll_log_id, now_ms, parsed.ticker, parsed.exchange_index,
                parsed.position_fp, parsed.market_exposure_dollars,
                parsed.total_traded_dollars, parsed.fees_paid_dollars,
                parsed.realized_pnl_dollars, parsed.last_updated_ts,
                parsed.contracts, parsed.side, parsed.exposure_tenths,
            ),
        )
    conn.execute(
        "DELETE FROM venue_positions WHERE polled_ms < ?",
        (now_ms - VENUE_POSITIONS_RETENTION_MS,),
    )
    return {
        "seen": len(rows), "stored": len(rows), "exposure_unreadable": unreadable,
    }


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
        log_poll_attempt(
            conn, now_ms=now_ms, endpoint="balance", ok=False, error=repr(exc)
        )
        return f"FAILED: {exc}"
    balance_tenths = parse_balance_tenths(payload)
    conn.execute(
        "INSERT INTO venue_balance_snapshots "
        "(observed_ms, balance_tenths, portfolio_value_tenths) "
        "VALUES (?, ?, ?)",
        (now_ms, balance_tenths, parse_portfolio_value_tenths(payload)),
    )
    log_poll_attempt(conn, now_ms=now_ms, endpoint="balance", ok=True, row_count=1)
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
# (2026-08-21 ruling), settlements (ADR 0064) and positions (2026-08-29)
# riding the 5-minute clock because their consumers refuse on a stale read;
# §7.6 is a floor, and polling an unmetered endpoint more often only raises
# completeness. Constants rather than configuration, deliberately -- the
# cadence is REGISTERED, and a knob invites the deployed value to drift from
# the protocol without anyone deciding it. Changing these is amending the
# registration, and should read like it.
#
# **Two intervals, and there will not be a third.** Every endpoint that left
# the mirror shares `BALANCE_INTERVAL_S` rather than naming its own
# "recently" -- a fourth definition is how the loosest one wins in silence,
# and `bets.TONIGHT_STALE_AFTER_MS` is the single staleness bound read
# against all of them at 6x this cadence. What is still on `MIRROR_INTERVAL_S`
# is `run_match_pass` alone, and it is there because it writes a registered
# variable (`outcome_win`) -- the analysis clock of amendment A7, not an
# oversight.
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
                    # **Which branch ran, in the data.** Both branches write
                    # `poll_log` rows stamped with this cycle's `now_ms` and
                    # nothing in them said whether the cycle was a mirror or a
                    # fast one -- so `lock-attribution`, which groups bursts by
                    # `DISTINCT polled_ms`, could not tell the two apart. §7 of
                    # `docs/measurements/2026-09-01-lock-holder-attribution-
                    # result.md` needs exactly that split: a post-fix burst
                    # after a MIRROR cycle is explained by the matcher's own
                    # loop and would not refute ADR 0091, so a forward
                    # registration cannot state a decision rule until the split
                    # exists. `endpoint` is free-form TEXT; no schema change.
                    #
                    # A branch marker, not a poll attempt: `ok = 1` records
                    # that the branch was entered, `row_count` is NULL because
                    # nothing was counted, and no consumer reads
                    # `endpoint = 'mirror'` -- every existing query filters on
                    # one of the four endpoint names or on `ok = 0`.
                    #
                    # Written BEFORE the mirror and committed immediately, for
                    # two reasons. A cycle that dies inside `poll_portfolio`
                    # was still a mirror cycle and is exactly the cycle a burst
                    # may follow, so an after-marker would go missing where it
                    # is most needed; and the commit is what keeps this INSERT
                    # from holding the write lock across the mirror's first
                    # round trip, which is the rule this module already states.
                    log_poll_attempt(
                        conn, now_ms=now_ms, endpoint="mirror", ok=True
                    )
                    conn.commit()
                    summary = await poll_portfolio(conn, client, now_ms=now_ms)
                    last_mirror = now
                    logger.info("portfolio mirror: %s", summary)
                else:
                    # **Each step commits before the next network call.**
                    # This branch runs every `balance_interval_s` -- 300s, so
                    # 288 times a day -- and until 2026-08-31 all four shared
                    # one transaction: `poll_balance` INSERTs, taking SQLite's
                    # write lock, and nothing released it until the commit
                    # below, THREE Kalshi round trips later. Any other writer
                    # landing in that window waited out `BUSY_TIMEOUT_MS` and
                    # raised `database is locked` -- most often
                    # `store_closing_line` on the scoring pass, which kills the
                    # whole pass and loses closing lines that cannot be
                    # re-observed.
                    #
                    # **The frequency is why this branch is the one that
                    # mattered.** `poll_portfolio` above had the identical
                    # shape and was fixed with it, but the mirror runs twice a
                    # day; this runs every five minutes. The observed failure
                    # rate (four to five a day) fits 288 windows and does not
                    # fit two.
                    result = await poll_balance(conn, client, now_ms=now_ms)
                    conn.commit()
                    # Fills ride the balance cadence (2026-08-21 ruling) so
                    # the landing screen's "tonight" strip is at most minutes
                    # behind the venue, not hours. See `poll_fills` for why
                    # this is not a registration amendment. Settlements ride
                    # it too (ADR 0064): the daily-loss kill switch reads the
                    # mirror and refuses when it is older than 30 minutes, so
                    # on the 12-hour clock alone the order path would be
                    # refused nearly all day -- see `poll_settlements`.
                    fills_result = await poll_fills(conn, client, now_ms=now_ms)
                    conn.commit()
                    settle_result = await poll_settlements(
                        conn, client, now_ms=now_ms
                    )
                    conn.commit()
                    # Positions ride it too (2026-08-29): the open-positions
                    # count on the landing screen is this endpoint's newest
                    # successful poll, and a hand bet placed at 8pm did not
                    # appear on it until the next mirror -- see
                    # `poll_positions` for why this is not an amendment
                    # either, and why `run_match_pass` did not come with it.
                    positions_result = await poll_positions(
                        conn, client, now_ms=now_ms
                    )
                    conn.commit()
                    logger.debug(
                        "balance snapshot: %s; fills: %s; settlements: %s; "
                        "positions: %s",
                        result, fills_result, settle_result, positions_result,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 -- see the docstring
                logger.exception("portfolio poll cycle failed; loop continues")
            await sleep(balance_interval_s)
    finally:
        conn.close()
