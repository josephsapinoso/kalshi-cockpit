"""The desk's pass record: every deliberate "no", append-only, never scored.

Why this exists (slice B6, 2026-08-22): the record held 39 settled bets and
zero evidence Joe ever chose *not* to bet, so the only unit any screen could
count was bets placed -- a scoreboard on which betting is the sole recordable
act. This module makes the decision the unit: a pass row is written when the
"not tonight" lockout is engaged (scope ``'tonight'`` -- one gesture, two
records) or when a per-market pass is posted (scope = the ticker).

The honesty rules, all load-bearing:

- **Append-only.** No function here updates or deletes a row, and
  ``tests/test_desk_passes.py`` greps the codebase to keep it that way. A
  "no" that can be edited afterwards is a story, not a record.
- **Never scored, never rated.** Nothing joins passes against outcomes,
  prices, or the settlement mirror to say whether a pass was "right".
  Grading the one pressure-free act in the product would recreate the
  pressure it exists to relieve.
- **A reason is optional everywhere.** ``NULL`` means none was given, and
  none is ever required -- a required reason is a toll on the correct
  boring action.

What this module does NOT establish
-----------------------------------
That a night without a pass row had no passes. Only taps are recorded; a
game skipped in silence leaves nothing here, so the count is a floor on
deliberate passes, never a census of restraint.
"""

from __future__ import annotations

import sqlite3
from typing import Optional


def record_pass(
    conn: sqlite3.Connection,
    *,
    now_ms: int,
    scope: str,
    reason: Optional[str] = None,
) -> int:
    """Append one pass. Returns the new row's id.

    ``scope`` is ``'tonight'`` or a market ticker; the caller owns
    normalisation (the route uppercases tickers, matching every other
    ticker write). An empty or whitespace reason is stored as ``NULL`` --
    "said nothing" is one state, not two.
    """
    cleaned = reason.strip() if isinstance(reason, str) else None
    cursor = conn.execute(
        "INSERT INTO desk_passes (created_ms, scope, reason) VALUES (?, ?, ?)",
        (now_ms, scope, cleaned or None),
    )
    conn.commit()
    return int(cursor.lastrowid)


def pass_summary(conn: sqlite3.Connection) -> dict:
    """The headline's numbers: how many passes, and since when.

    ``first_ms`` is ``None`` on an empty table -- "no passes recorded" is a
    real state and renders as words, never as a date of 1970. Counts only:
    per the module docstring, nothing here reads an outcome or a price.
    """
    row = conn.execute(
        "SELECT COUNT(*) AS n, MIN(created_ms) AS first_ms FROM desk_passes"
    ).fetchone()
    return {
        "total": int(row["n"]),
        "first_ms": row["first_ms"],
    }
