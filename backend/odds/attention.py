"""Whether anyone is looking at the desk, which is what the odds feed follows.

ADR 0071 §2.6, settled with Joe: **the odds feed follows attention, not the
clock.** The fixed `ODDS_DESK_WINDOW_UTC` bought a sweep every ten minutes for
twelve hours a day whether or not the site was open -- ~576 credits/day at two
sports, ~17,300/month against an 18,000 self-cap, and ~1,152/day at four, which
breaks even the 20,000 paid tier. NCAAF and NFL enter scope this week. Joe looks
at the desk for a fraction of that window, so the feed buys while a page is open
and falls back to a slow floor when it is not.

What a stamp means, and what it does not
----------------------------------------
A row here says **a browser told us it had the page open and visible**, at that
instant. It is a claim by the client, not an observation of a human: a page left
open on a second monitor stamps exactly like a page being read. That is the
honest limit of what a heartbeat can know, and it is why the sub-ceiling exists
rather than trust alone.

`None` is "nobody has ever looked", never `0`
---------------------------------------------
The repo convention, and here the direction matters more than usual. `0` reads
as "last seen at the epoch", which is *also* the safe answer -- the desk stays
shut. A bug returning `now_ms` would be the expensive one: the desk would read
as permanently attended and buy at the ten-minute cadence forever, which is the
1,152/day worst case with nobody watching. So the failure this module is written
against is a false *present*, not a false absent.

Append-only, because the saving is unmeasured
----------------------------------------------
Every "attended hours" figure in the design is a guess. A single mutable
last-seen row would answer the trigger and destroy the only evidence that could
check the guess; a table of stamps is the instrument. `seen_at_least_once_since`
exists so the measurement can be taken without a second query shape.

What this module does not establish
-----------------------------------
- **Nothing about whether the page is being read.** See above.
- **Nothing about cost.** It reports attention; `odds/timing.py` decides what to
  buy and `CreditBudget` decides whether it may.
- **Nothing about who.** One operator, one instance (ADR 0071 §1). There is no
  session or user column and adding one would be a claim about a future that
  does not exist.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

# How long a stamp keeps the desk open after it lands.
#
# One refresh interval, near enough: a closed tab costs at most one more sweep
# before the desk goes quiet. Shorter and an ordinary gap between heartbeats
# (`Nav.tsx` polls every 60s) would flap the trigger; longer and every visit
# buys a tail of sweeps nobody sees.
#
# **This is a ceiling on waste, not a promise of freshness.** It bounds how long
# the feed keeps buying after the last heartbeat; it says nothing about how
# stale the odds are when a cold page opens, which is the floor's job.
DEFAULT_ATTENTION_TTL_MS = 300_000


def stamp(conn: sqlite3.Connection, *, now_ms: int) -> None:
    """Record that someone has the desk open."""
    conn.execute("INSERT INTO desk_attention (seen_ms) VALUES (?)", (now_ms,))
    conn.commit()


def last_seen_ms(conn: sqlite3.Connection) -> Optional[int]:
    """The most recent heartbeat, or `None` if there has never been one.

    `None` and not `0`: an empty table means nobody has ever looked, which is a
    different fact from having looked at the epoch, and the two would be
    indistinguishable in any age arithmetic a caller does.
    """
    row = conn.execute(
        "SELECT MAX(seen_ms) AS seen_ms FROM desk_attention"
    ).fetchone()
    if row is None or row["seen_ms"] is None:
        return None
    return int(row["seen_ms"])


def is_attended(
    conn: sqlite3.Connection,
    *,
    now_ms: int,
    ttl_ms: int = DEFAULT_ATTENTION_TTL_MS,
) -> bool:
    """Whether a heartbeat has landed recently enough to keep the desk open.

    The one predicate the trigger asks, so the answer cannot be re-derived
    differently by the loop and by the screen -- the rule `timing.py` states at
    `firing_for_slot` and the desk trigger spent five sites ignoring.

    A stamp from the *future* is treated as attended rather than refused. Clock
    skew between the browser and the box is real and small; the stamp is written
    with the server's own `now_ms` anyway, so a future value means the server
    clock moved backwards, and the conservative reading of that is not "buy
    forever" -- it is bounded by `ttl_ms` either way.
    """
    seen = last_seen_ms(conn)
    if seen is None:
        return False
    return now_ms - seen <= ttl_ms


def seen_at_least_once_since(conn: sqlite3.Connection, *, since_ms: int) -> int:
    """How many heartbeats landed since `since_ms`.

    **The instrument, not a trigger input.** Nothing in the sweep path calls
    this. It exists so "how many hours a day is the page actually open" can be
    answered from the record rather than assumed, because the entire saving this
    design claims rests on that number and nobody has measured it. Summed
    per budget-day beside `api_credits`, it is what turns the claim into a
    measurement.
    """
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM desk_attention WHERE seen_ms >= ?",
        (since_ms,),
    ).fetchone()
    return int(row["n"]) if row else 0
