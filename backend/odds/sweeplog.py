"""The record of every odds-sweep decision, including the decision not to.

A refused sweep used to leave no trace in any table in the schema. Three
independent silences, each individually reasonable:

    api_credits    written only when an HTTP call was actually made, so a call
                   that was never made is indistinguishable from a day nobody
                   ran the loop.
    notifications  writes `window_open` only when a sweep succeeded -- correct,
                   because announcing an intended sweep would put "the window is
                   open" on a phone at the moment the odds API was down.
    the log        `decide_sweeps` returns a reason string that was only logged,
                   and the production log stream is lossy.

Together they made silence indistinguishable from a system that never looked,
which is how odds fetching stopped at 2026-08-09T23:37:15Z and ran 17+ hours
behind a green health check.

Why this is a separate table
----------------------------
The obvious fix is a zero-cost row in `api_credits`. It is a trap:
`timing.last_sweep_by_sport` asks that table "has this sport been swept today",
so a refusal row is read as a *served* sweep -- the scheduler drops that sport's
slot as already covered and spends its one daily bootstrap attempt on it. The
trace intended to reveal the silence would have caused it, for exactly the sport
it was recording a refusal for.

`api_credits` means "a call went out and it cost credits". That is a statement
about presence, and this module records absence. They are different facts, and
this repo's standing rule is that absence never borrows presence's
representation -- the same rule as "unreadable resolves to `None`, never `0`".

`timing._SERVED_SWEEP` now filters on `cost > 0` as well, so the trap cannot be
sprung even by someone who writes the refusal row anyway. That is belt and
braces, not the reason this table exists.

What this does not establish
----------------------------
That anyone notices. This module makes the silence *legible*; it does not raise
an alarm. A health check that goes red on a long gap, or an alert, would be the
thing that closes the 17 hours, and neither is here.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

# The four states a pass can end an odds sweep in. Mirrored by a CHECK
# constraint in `schema.sql` -- the constraint is the guarantee, this is for
# callers and for the error message when one gets it wrong.
SERVED = "served"
REFUSED = "refused"
NO_DATA = "no_data"
SKIPPED = "skipped"

OUTCOMES = (SERVED, REFUSED, NO_DATA, SKIPPED)


def record_sweep_outcome(
    conn: sqlite3.Connection,
    *,
    pass_ms: int,
    outcome: str,
    detail: str,
    sport_key: Optional[str] = None,
    quotes_stored: Optional[int] = None,
) -> None:
    """Write one row saying what this pass did about odds, and why.

    `detail` is required rather than optional, and that is the whole point of
    the table: a row that records a refusal without its reason turns one
    unanswerable question ("did it look?") into another ("why did it stop?").

    `quotes_stored` stays `None` for every outcome but `served`. Nothing stored
    and nothing attempted are different states; a 0 in both would make a refused
    sweep and an empty slate read identically in any aggregate.
    """
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}, got {outcome!r}")
    if not detail:
        raise ValueError(
            "a sweep outcome with no reason records the silence it exists to "
            "explain"
        )
    conn.execute(
        "INSERT INTO odds_sweep_log (pass_ms, sport_key, outcome, detail, "
        "quotes_stored) VALUES (?, ?, ?, ?, ?)",
        (pass_ms, sport_key, outcome, detail, quotes_stored),
    )
    conn.commit()


def last_sweep_outcome(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    """The most recent decision of any kind, or `None` if none was ever made.

    `None` here means "this database has never recorded a pass looking at
    odds", which after a deploy is the true state and must not be presented as
    "it looked and found nothing".
    """
    return conn.execute(
        "SELECT pass_ms, sport_key, outcome, detail, quotes_stored "
        "FROM odds_sweep_log ORDER BY pass_ms DESC, id DESC LIMIT 1"
    ).fetchone()
