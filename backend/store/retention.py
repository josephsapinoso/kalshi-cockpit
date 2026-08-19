"""Bounded growth for the two recording tables that had none.

Nothing in this project deleted a row until 2026-08-19. `kalshi_quotes` and
`unmatched_events` accumulated for the life of the volume, which is two
separate failures rather than one:

- **Disk.** The volume filled on 2026-08-16 and was 79% full again three days
  later, growing ~214 MiB/day and accelerating. A full SQLite volume is a hard
  down that a restart does not clear, and `VACUUM` needs roughly twice the free
  space it would have by then.
- **Latency.** Each quote pass inserts ~5,300 rows into `kalshi_quotes` behind
  a `(ticker, observed_ms DESC)` index that had reached 476 MiB on a machine
  with 1 GiB of RAM. The insert leg measured 0.17s at 279k rows, and 6.0s then
  14.0s at 6.9M -- on a 15s cadence. See
  `docs/measurements/2026-08-19-quote-pass-leg-attribution.md`.

The second is why this is not merely housekeeping: the index is the thing the
pass writes into every fifteen seconds, and its size is the pass's cost.

What is kept, and why it is safe
--------------------------------
Every production reader of `kalshi_quotes` was enumerated before this was
written, because a retention rule is only as good as the claim that nothing
reads what it drops:

===========================  ==============================================
`runner.latest_kalshi_quote` newest row for one ticker
`routes.py` recorder health  newest row overall
`slate.kalshi_drift_tenths`  a **one hour** window
`clv_signal.py`              joined to a row in `recommendations`
===========================  ==============================================

So the only reader that reaches back beyond an hour reaches back through
`recommendations.ticker`. A row is kept when **either** it is inside the
retention window **or** its ticker has ever produced a recommendation --
`recommendations` is the only downstream table carrying a ticker at all
(`fair_prices` is keyed by `link_id`). On live at 6,946,356 rows, 4.8% of the
table is ticker-recommended and is kept regardless of age.

What this does NOT do
---------------------
- **It does not shrink the file.** SQLite returns freed pages to a free list,
  not to the filesystem; only `VACUUM` gives space back to the OS. Freed pages
  *are* reused by subsequent inserts, so the growth stops even without one --
  but a report that the database is smaller must come from `VACUUM`, not from
  this.
- **It does not bound the tables it does not name.** `odds_snapshots` was
  33.6 MiB and growing slowly when this was written; it is deliberately out of
  scope rather than forgotten.
- **It does not make the retention window a claim about the record's value.**
  The window is set by what the readers reach, not by how long a quote is
  interesting. If a future reader wants older history, it must raise the
  window here rather than discover the rows are gone.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_MS_PER_DAY = 24 * 60 * 60 * 1000

#: How far back a quote is kept for a ticker that never produced a
#: recommendation. Three days against a one-hour longest reader is a ~72x
#: margin, chosen so that a reader added without reading this file has room to
#: be wrong before it is silently starved.
DEFAULT_QUOTE_RETENTION_MS = 3 * _MS_PER_DAY

#: `unmatched_events` is a diagnostic: a row per event the linker could not
#: match, written every pass, so the same unmatched event is re-recorded
#: hundreds of times a day. No production code path reads it -- the linker
#: writes it and `store/publish.py` exposes it to dbt. Kept longer than the
#: quotes because it is small per row in aggregate terms and because a
#: matching regression is diagnosed over days, not hours.
DEFAULT_UNMATCHED_RETENTION_MS = 7 * _MS_PER_DAY

#: Rows deleted per statement. A single unbounded `DELETE` over millions of
#: rows holds the write lock for the whole of it, and the loop's next quote
#: pass would block behind it -- turning a disk fix into a latency incident.
#: Batching lets the writer interleave.
DELETE_BATCH = 20_000


@dataclass(frozen=True)
class PruneResult:
    """What one prune removed. Zero is a normal, reportable answer."""

    quotes_deleted: int = 0
    unmatched_deleted: int = 0

    @property
    def total(self) -> int:
        return self.quotes_deleted + self.unmatched_deleted


def _delete_in_batches(conn, sql: str, params: tuple) -> int:
    """Run a bounded `DELETE` until it stops matching. Returns rows removed.

    Each batch is its own transaction. A crash midway therefore leaves the
    table partly pruned rather than rolled back, which is the correct
    direction: the rows were surplus, and resuming simply removes the rest.
    """
    removed = 0
    while True:
        cursor = conn.execute(sql, params)
        conn.commit()
        if not cursor.rowcount:
            return removed
        removed += cursor.rowcount


def prune_quotes(conn, *, now: int, retention_ms: int = DEFAULT_QUOTE_RETENTION_MS) -> int:
    """Drop quotes older than the window whose ticker never produced a bet.

    The `NOT IN` is against `recommendations.ticker` rather than against a
    join, because the question is about the ticker's whole history and not
    about any one recommendation's timing: a market quoted for hours before it
    was ever recommended keeps that entire run, which is what makes the
    surviving series usable for closing-line work.
    """
    return _delete_in_batches(
        conn,
        "DELETE FROM kalshi_quotes WHERE id IN ("
        "  SELECT id FROM kalshi_quotes"
        "  WHERE observed_ms < ?"
        "    AND ticker NOT IN (SELECT ticker FROM recommendations)"
        "  LIMIT ?"
        ")",
        (now - retention_ms, DELETE_BATCH),
    )


def prune_unmatched(
    conn, *, now: int, retention_ms: int = DEFAULT_UNMATCHED_RETENTION_MS
) -> int:
    """Drop unmatched-event diagnostics older than the window.

    Unconditional on `resolved`, unlike the quotes rule, and that is
    deliberate: on live, **0 of 506,655** rows had ever been marked resolved,
    so a rule that spared resolved rows would spare nothing and would read as a
    safeguard while being a no-op. If the resolution path is ever built, this
    is the line to revisit.
    """
    return _delete_in_batches(
        conn,
        "DELETE FROM unmatched_events WHERE id IN ("
        "  SELECT id FROM unmatched_events WHERE observed_ms < ? LIMIT ?"
        ")",
        (now - retention_ms, DELETE_BATCH),
    )


def prune(
    conn,
    *,
    now: int,
    quote_retention_ms: int = DEFAULT_QUOTE_RETENTION_MS,
    unmatched_retention_ms: int = DEFAULT_UNMATCHED_RETENTION_MS,
) -> PruneResult:
    """Both prunes, for the full pass to call once per slow interval.

    **Never call this on the quote cadence.** The prune competes for the same
    write lock as the inserts it exists to keep fast, and at the 15s cadence it
    would run during exactly the minutes a bettable window is open.
    """
    result = PruneResult(
        quotes_deleted=prune_quotes(conn, now=now, retention_ms=quote_retention_ms),
        unmatched_deleted=prune_unmatched(
            conn, now=now, retention_ms=unmatched_retention_ms
        ),
    )
    if result.total:
        logger.info(
            "retention: pruned %d kalshi_quotes and %d unmatched_events rows",
            result.quotes_deleted,
            result.unmatched_deleted,
        )
    return result
