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

A fourth silence, found 2026-08-17 and closed 2026-08-25 (v21)
--------------------------------------------------------------
The three above are all about a call that was *never made*. There was a fourth
about a call that was made and **failed**, and it was the worse one, because it
did not merely leave no trace -- it left a trace saying the opposite.

`odds/client.py` records the credit before checking the status, which is right:
some error classes still consume credits. But that row satisfied
`_SERVED_SWEEP`, so a 401 moved the sport's last-sweep stamp to now, deferred
the retry a full refresh interval, and rendered the odds on screen as freshly
bought. Meanwhile this table got nothing: `REFUSED` means the budget declined,
`SKIPPED` means the pass chose not to look, and `NO_DATA` means the call
succeeded against an empty slate. **None of the four outcomes could say "the
upstream refused us"**, so the outage was written as no outcome at all.

`FAILED` and `api_credits.http_status` close it. The credit is still recorded,
the sweep is no longer counted as served, and the failure has a row with the
status on it.

What this does not establish
----------------------------
That anyone notices. This module makes the silence *legible*; it does not raise
an alarm. A health check that goes red on a long gap, or an alert, would be the
thing that closes the 17 hours, and neither is here.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

# The five states a pass can end an odds sweep in. Mirrored by a CHECK
# constraint in `schema.sql` -- the constraint is the guarantee, this is for
# callers and for the error message when one gets it wrong.
SERVED = "served"
REFUSED = "refused"
NO_DATA = "no_data"
SKIPPED = "skipped"
# The call went out and the upstream refused it. v21, 2026-08-25.
#
# **None of the other four could say this, and the gap was not cosmetic.**
# `REFUSED` means the budget declined -- *we* stopped. `SKIPPED` means the pass
# chose not to look. `NO_DATA` means the call succeeded and the slate was empty,
# which is a quiet night, the opposite of an outage. So an upstream 401 or 5xx
# had no outcome to be written as, and it was written as nothing at all: the
# only trace was an `api_credits` row with NULL rate-limit headers, which is
# also what a successful call looks like when the headers are missing.
#
# This module's docstring says it exists because "silence was indistinguishable
# from a system that never looked". An upstream failure is that case exactly,
# and it was the one outcome the vocabulary could not name.
FAILED = "failed"

OUTCOMES = (SERVED, REFUSED, NO_DATA, SKIPPED, FAILED)


def record_sweep_outcome(
    conn: sqlite3.Connection,
    *,
    pass_ms: int,
    outcome: str,
    detail: str,
    sport_key: Optional[str] = None,
    quotes_stored: Optional[int] = None,
    failed_status: Optional[int] = None,
) -> None:
    """Write one row saying what this pass did about odds, and why.

    `detail` is required rather than optional, and that is the whole point of
    the table: a row that records a refusal without its reason turns one
    unanswerable question ("did it look?") into another ("why did it stop?").

    `quotes_stored` stays `None` for every outcome but `served`. Nothing stored
    and nothing attempted are different states; a 0 in both would make a refused
    sweep and an empty slate read identically in any aggregate.

    `failed_status` is the upstream status and belongs only to `FAILED`. It is a
    column rather than prose in `detail` so a reader can count 401s without
    parsing a sentence -- the difference between "the key is dead" and "the
    aggregator is having a bad hour" is the difference between rotating a
    credential and waiting, and `detail` carries it in words for a human while
    this carries it in a number for a query.
    """
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}, got {outcome!r}")
    if not detail:
        raise ValueError(
            "a sweep outcome with no reason records the silence it exists to "
            "explain"
        )
    if failed_status is not None and outcome != FAILED:
        # The CHECK in `schema.sql` is the guarantee; this is the readable
        # error. A status on a `served` row would say the call both worked and
        # did not.
        raise ValueError(
            f"failed_status belongs to {FAILED!r} rows only, got {outcome!r}"
        )
    conn.execute(
        "INSERT INTO odds_sweep_log (pass_ms, sport_key, outcome, detail, "
        "quotes_stored, failed_status) VALUES (?, ?, ?, ?, ?, ?)",
        (pass_ms, sport_key, outcome, detail, quotes_stored, failed_status),
    )
    conn.commit()


def last_sweep_outcome(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    """The most recent decision of any kind, or `None` if none was ever made.

    `None` here means "this database has never recorded a pass looking at
    odds", which after a deploy is the true state and must not be presented as
    "it looked and found nothing".
    """
    return conn.execute(
        "SELECT pass_ms, sport_key, outcome, detail, quotes_stored, "
        "failed_status "
        "FROM odds_sweep_log ORDER BY pass_ms DESC, id DESC LIMIT 1"
    ).fetchone()
