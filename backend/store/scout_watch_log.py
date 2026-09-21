"""The record of every unattended scout-watch decision, including the decision not to.

Why this module exists
----------------------
`scout_briefings` records that the desk WAS convened. Every way the watcher
declines to convene returned before that table's `INSERT` and left no trace in
any table in the schema:

    scout_watch.py:152    the SCOUT_AUTO_MAX_CONVENINGS_PER_DAY brake
    scout_watch.py:167    AgentBudget.refusal_reason -- calls, tokens, searches
    routers/scout.py:277  a tap over a ceiling, raised as HTTP 429

So `scout_briefings.refusal_reason` -- whose own schema comment says "which
ceiling refused" -- is written by none of the four ceilings that actually gate a
convening. A row reaches `status = 'refused'` only from *inside* a desk run that
had already started (`agents/scout_desk.py:441`). Asked "how many convenings
were refused, and at which ceiling", the schema could not answer at all, and the
only trace was a production log stream that drops lines.

**This is `backend/odds/sweeplog.py`'s failure in a second subsystem**, and that
module's argument is adopted here rather than re-derived: silence was
indistinguishable from a watcher that never looked. It is worth restating why
that matters here specifically. Measured on 2026-09-21, the afternoon unattended
scouting was armed, the token ceiling bound within two and a half hours and
refused every cycle afterwards -- including Joe's own taps -- and **no row
anywhere recorded that it had happened.** The binding had to be reconstructed
from a budget summary on a served route.

One row per work item, not one per sighting -- ADR 0056
-------------------------------------------------------
The watcher wakes every `DEFAULT_INTERVAL_S` (600 s), so once a ceiling binds it
refuses roughly 144 times before the budget day rolls. A row per cycle would be
noise, and would make this table's own growth a retention problem on the box
ticket #58 is about.

The `unmatched_items` shape carries strictly more information for a bounded
number of rows. `cycle_count` separates a ceiling that bound once from one that
bound all evening -- the difference between a brake working and a brake stuck --
and `first_ms` ordered within a budget day answers "which ceiling bound first",
which is the one question this table exists for.

What this module does NOT establish
-----------------------------------
- **Nothing about spend.** It records which ceiling refused, never what a
  convening cost. `agent_calls` is the meter; this is the decision log, and a
  reader that wants tokens must go there.
- **Nothing before 2026-09-21.** There is no backfill and none is possible:
  earlier refusals went only to a log stream that drops lines. The first row
  here is the first one that exists, and a gap before it is missing
  instrumentation, not a quiet watcher.
- **Nothing about taps.** `routers/scout.py`'s 429 path is a refusal of Joe's
  own request and is not written here; this table is the *unattended* watcher's
  decision log. A tap that was refused is still invisible, deliberately, because
  Joe saw the refusal on his screen at the time.
- **Nothing about whether a convening produced a usable briefing.** `convened`
  means the desk was sent. What came back is `scout_briefings.status`.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

#: The desk was sent; a `scout_briefings` row exists for this cycle.
CONVENED = "convened"
#: `SCOUT_AUTO_MAX_CONVENINGS_PER_DAY`. `detail` says n of m.
REFUSED_ALLOWANCE = "refused_allowance"
#: A ceiling inside `AgentBudget.refusal_reason` -- calls, tokens or searches.
#: `detail` is that function's own sentence, verbatim.
REFUSED_BUDGET = "refused_budget"
#: No `ANTHROPIC_API_KEY`: nothing to convene with.
#:
#: **Not a refusal, and it must never be counted as one.** No ceiling bound; the
#: desk does not exist in this configuration (the demo deploy is permanently
#: here). Folding it into `refused_budget` would report a budget problem on an
#: instance that has no budget, which is the `api_credits` trap `sweeplog`
#: describes -- absence borrowing presence's representation.
KEYLESS = "keyless"
#: The ladder was walked and nothing was eligible: no fixture resolved to a
#: ticker, or every one already had a briefing inside `SCOUT_AUTO_REFRESH_HOURS`.
#: A quiet night, not a brake.
NO_CANDIDATE = "no_candidate"

OUTCOMES = (CONVENED, REFUSED_ALLOWANCE, REFUSED_BUDGET, KEYLESS, NO_CANDIDATE)


def record_watch_outcome(
    conn: sqlite3.Connection,
    *,
    budget_day_ms: int,
    now_ms: int,
    outcome: str,
    detail: str,
) -> None:
    """Upsert one cycle's decision onto its (budget day, outcome, detail) row.

    `budget_day_ms` is the AGENT BUDGET day (`AgentBudget.day_start_ms`), never
    a calendar day -- the same clock the allowance is counted against, so the
    two can never be accidentally compared.

    `detail` is the reason in the words the decision itself used. **It is not
    re-derived here**: a paraphrase of a reason is a second implementation of
    it, and `agents/budget.py`'s own argument against a second `can_afford`
    applies unchanged. Callers pass `refusal_reason`'s sentence through
    verbatim. For the outcomes that have no reason of their own, the caller
    passes a literal, because `detail` is part of the unique key and SQLite
    treats NULLs in a unique index as distinct -- a nullable `detail` would let
    every cycle insert afresh, which is the exact behaviour this shape exists to
    prevent, surviving behind an index that claims to prevent it.

    **This function cannot fail the decision it records.** A refusal is already
    the safe path, and a raising recorder would turn a cheap no-op into a crash
    loop on the watcher the project depends on for its unattended spend. So the
    write is wrapped and logged, never propagated -- the same contract
    `record_position`'s caller keeps, and for the same reason. The cost of that
    choice is stated plainly: a write that fails is invisible except in the log,
    so this table can undercount. It cannot overcount, and it cannot lie about
    *which* ceiling bound.
    """
    if outcome not in OUTCOMES:
        # A caller naming an outcome the CHECK would reject. Log and drop
        # rather than raise, for the reason in the docstring -- but say so
        # loudly, because it means a new decision path was added upstream
        # without a vocabulary for it, which is this table's whole subject.
        logger.error(
            "scout watch log: unknown outcome %r (detail %r) -- not recorded",
            outcome, detail,
        )
        return
    try:
        conn.execute(
            "INSERT INTO scout_watch_log "
            "(budget_day_ms, first_ms, last_ms, cycle_count, outcome, detail) "
            "VALUES (?, ?, ?, 1, ?, ?) "
            "ON CONFLICT(budget_day_ms, outcome, detail) DO UPDATE SET "
            # `last_ms` takes the later of the two rather than the incoming
            # value: cycles are not guaranteed to arrive in clock order (a
            # retry, a clock step), and a bare assignment would let a late
            # cycle move `last_ms` backwards past `first_ms` and trip the
            # table's own CHECK on a write that is merely out of order.
            "  last_ms = MAX(last_ms, excluded.last_ms), "
            "  cycle_count = cycle_count + 1",
            (budget_day_ms, now_ms, now_ms, outcome, detail),
        )
        conn.commit()
    except Exception:                                            # noqa: BLE001
        logger.exception(
            "scout watch log: could not record %s (detail %r)", outcome, detail
        )


def read_watch_log(
    conn: sqlite3.Connection, *, days: int, now_ms: Optional[int] = None
) -> list[sqlite3.Row]:
    """The last `days` budget days of decisions, newest day first.

    Within a day, ordered by `first_ms` -- so the first row of a day is the
    first thing that happened, which is what "which ceiling bound first" asks.
    Bounded by `days` rather than by row count: a caller asking for three days
    wants all of all three, and a `LIMIT` on rows would silently truncate the
    busiest one.
    """
    rows = conn.execute(
        "SELECT budget_day_ms, first_ms, last_ms, cycle_count, outcome, detail "
        "FROM scout_watch_log "
        "WHERE budget_day_ms IN ("
        "  SELECT DISTINCT budget_day_ms FROM scout_watch_log "
        "  ORDER BY budget_day_ms DESC LIMIT ?"
        ") "
        "ORDER BY budget_day_ms DESC, first_ms ASC",
        (days,),
    ).fetchall()
    return list(rows)
