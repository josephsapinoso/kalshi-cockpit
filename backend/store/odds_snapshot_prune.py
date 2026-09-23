"""Thin `odds_snapshots` to each game's closing lines once it is old. #58.

**Joe's decision, 2026-09-23** (#58, three answers in one sitting): prune
`odds_snapshots` before 2026-10-02; for a game past the window keep each
book's **closing line** and delete the in-between readings; the window is
**14 days** after kickoff; no `VACUUM`. ADR recorded beside this change.

Why this table, and why now: it is the one large table with no retention
rule (`retention.py`'s docstring left it out when it was 33.6 MiB), and at
~141 MB/day it is the residual growth `docs/measurements/2026-09-18-fair-
prices-dedup-effect-result.md` §11.2 says exhausts the 4 GB box's residency
advantage about two weeks after 09-18.

**What is kept, per game whose latest kickoff is older than the window:**

1. For every `(bookmaker, market, outcome_description)`, every row of that
   book's **last read at or before kickoff** (`fetched_ms = MAX(fetched_ms)
   WHERE fetched_ms <= commence_ms`). `outcome_description` is the player on
   a prop and NULL on a team market, so a team market keeps the book's whole
   last sweep (both sides, whatever point it had moved to), and each player
   keeps their own last line even when a book dropped them from its final
   sweep (a lineup scratch). Keyed on the market alone, one prop market
   covers every player, and a player missing from the last sweep lost their
   only close: found by review before any run. An alternate-lines market
   whose book re-posted only some points keeps its last sweep's points.
2. The single row with the game's **lowest `commence_ms`** (ties by `id`),
   only when no row kept under (1) already carries that value.
   Five readers take a game's kickoff as `MIN(commence_ms)` from this table
   (`scoring.py:172`, `gate.py:955`, `routers/ledger.py:340`,
   `routes.py:4776/4783`, `parlays.py:2674`) and one takes `sport_key` from
   the lowest-kickoff row. Keeping that row means each of them returns the
   same value after the prune as before it, not merely *a* value.

Everything else for that game is deleted: intermediate pre-kickoff sweeps
and every in-play read. A game with a book that never read it before kickoff
keeps nothing for that book: there is no close to keep.

**What it does NOT establish, and what it destroys.**

- **It does not shrink the file.** Deleted pages go on SQLite's freelist and
  are reused by later inserts, so growth stops; the file stays its size until
  a `VACUUM`, which Joe declined for now (it takes the desk offline and needs
  about the file's size free on the volume).
- **It does not show the desk gets faster.** Residency was argued on file
  size, and the file does not shrink. What it does do is stop old sweeps
  being part of any unbounded reader's walk.
- **It permanently destroys** the line-movement history of every game past
  the window, and with it the ability to reconstruct per-pass
  `oldest_book_age_ms` that `docs/measurements/2026-09-17-preregistration-
  fair-prices-dedup.md` §7.3 warned depends on this table having no
  retention rule. Joe accepted that when he chose the closing-line option.

**Two refusals, the `fair_price_downsample` pattern.** Only `enabled=true`
**and** `dry_run=false` deletes. Nothing on a disk threshold may set either
(the same rule `backend/store/volume.py` is held to). The dry run is loud: it
logs what it would delete for the games its budget reached, so the first
deployed step measures the keep ratio before anything is removed.

**How it walks the table.** A cursor per `sport_key`, stored in `meta`, of
`(commence_ms, odds_event_id)`: each step is one seek on
`idx_odds_sport_commence (sport_key, commence_ms, odds_event_id, ...)` for
the next game strictly after the cursor with `commence_ms` below the cutoff.
The sports themselves are listed by a recursive `MIN(sport_key) > ?` seek on
the same index, never a `DISTINCT` walk. So a pass costs the games it
touches, not the table's size. One game per transaction; the budget is
checked between games. A crash leaves the table partly pruned, which is the
safe direction: the next pass resumes from the cursor, and a game whose
delete did not commit is found again because the cursor is written in the
same transaction as its delete.

A game whose rows carry more than one `commence_ms` (a fixture that moved)
is judged by its **latest** kickoff: if that is inside the window the game is
skipped and the cursor passes it. Its later rows sit further along the same
index, so the walk finds it again once the later kickoff is old.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_MS_PER_DAY = 24 * 60 * 60 * 1000

#: Joe's answer on #58, 2026-09-23.
DEFAULT_RETENTION_DAYS = 14
DEFAULT_BUDGET_S = 30.0
#: The dry run counts at most this many games per pass. It never advances the
#: stored cursor, so without a cap it would re-count the same oldest games for
#: its whole budget on every pass, before pricing, for as long as it is
#: deployed dry.
DRY_RUN_SAMPLE_GAMES = 25

CURSOR_KEY = "odds_snapshot_prune_cursor"

_SPORTS_SQL = """
WITH RECURSIVE s(k) AS (
    SELECT MIN(sport_key) FROM odds_snapshots
    UNION ALL
    SELECT (SELECT MIN(sport_key) FROM odds_snapshots WHERE sport_key > s.k)
    FROM s WHERE s.k IS NOT NULL
)
SELECT k FROM s WHERE k IS NOT NULL
"""

_NEXT_GAME_SQL = """
SELECT commence_ms, odds_event_id
FROM odds_snapshots
WHERE sport_key = :sport
  AND (commence_ms, odds_event_id) > (:c, :e)
  AND commence_ms < :cutoff
ORDER BY commence_ms, odds_event_id
LIMIT 1
"""

_LATEST_KICKOFF_SQL = (
    "SELECT MAX(commence_ms) FROM odds_snapshots WHERE odds_event_id = :e"
)

#: The rows a game keeps. The lowest-kickoff row is added only when no
#: closing row already carries the game's lowest `commence_ms`; otherwise
#: every game would keep one arbitrary in-between reading as well.
KEEP_SQL = """
WITH closing AS (
    SELECT o.id, o.commence_ms
    FROM odds_snapshots o
    JOIN (
        SELECT bookmaker, market, outcome_description,
               MAX(fetched_ms) AS closing_ms
        FROM odds_snapshots
        WHERE odds_event_id = :e AND fetched_ms <= commence_ms
        GROUP BY bookmaker, market, outcome_description
    ) k ON k.bookmaker = o.bookmaker
       AND k.market = o.market
       AND k.outcome_description IS o.outcome_description
       AND k.closing_ms = o.fetched_ms
    WHERE o.odds_event_id = :e
),
lowest AS (
    SELECT id, commence_ms FROM odds_snapshots
    WHERE odds_event_id = :e
    ORDER BY commence_ms, id
    LIMIT 1
)
SELECT id FROM closing
UNION
SELECT id FROM lowest
WHERE commence_ms < COALESCE((SELECT MIN(commence_ms) FROM closing),
                             commence_ms + 1)
"""

_DELETE_SQL = (
    "DELETE FROM odds_snapshots WHERE odds_event_id = :e "
    f"AND id NOT IN ({KEEP_SQL})"
)
_COUNT_SQL = (
    "SELECT COUNT(*) FROM odds_snapshots WHERE odds_event_id = :e "
    f"AND id NOT IN ({KEEP_SQL})"
)


@dataclass
class PruneResult:
    games: int = 0
    rows_deleted: int = 0
    #: Dry run only: rows the armed rule would have removed from `games`.
    rows_would_delete: int = 0
    #: Dry run only: every row those games hold, so the keep ratio is readable.
    rows_examined: int = 0
    skipped_moved: int = 0
    sports_done: list[str] = field(default_factory=list)


def _read_cursor(conn) -> dict[str, list]:
    row = conn.execute(
        "SELECT value FROM meta WHERE key = ?", (CURSOR_KEY,)
    ).fetchone()
    if row is None:
        return {}
    try:
        value = json.loads(row[0])
    except (TypeError, ValueError):
        # An unreadable cursor restarts the walk rather than guessing a
        # position. Restarting is safe: a pruned game's delete finds nothing.
        logger.error("odds_snapshot prune: unreadable cursor %r; restarting", row[0])
        return {}
    if not isinstance(value, dict):
        return {}
    return {
        k: v for k, v in value.items()
        if isinstance(v, list) and len(v) == 2
        and isinstance(v[0], int) and isinstance(v[1], str)
    }


def _write_cursor(conn, cursor: dict[str, list], now: int) -> None:
    conn.execute(
        "INSERT INTO meta (key, value, updated_ms) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
        "updated_ms = excluded.updated_ms",
        (CURSOR_KEY, json.dumps(cursor, sort_keys=True), now),
    )


def run(conn, *, now: int, config, budget_s: float | None = None) -> PruneResult:
    """Prune games older than the window to their closing lines.

    Returns what it did. Deletes nothing unless `config.deletes`.
    """
    result = PruneResult()
    if not getattr(config, "enabled", False):
        return result
    retention_days = getattr(config, "retention_days", DEFAULT_RETENTION_DAYS)
    if budget_s is None:
        budget_s = getattr(config, "budget_s", DEFAULT_BUDGET_S)
    deletes = bool(getattr(config, "deletes", False))
    cutoff = now - retention_days * _MS_PER_DAY
    deadline = time.monotonic() + budget_s

    cursor = _read_cursor(conn)
    sports = [r[0] for r in conn.execute(_SPORTS_SQL).fetchall()]
    out_of_time = False
    for sport in sports:
        c, e = cursor.get(sport, [-1, ""])
        while True:
            if time.monotonic() >= deadline or (
                not deletes and result.games >= DRY_RUN_SAMPLE_GAMES
            ):
                out_of_time = True
                break
            nxt = conn.execute(
                _NEXT_GAME_SQL, {"sport": sport, "c": c, "e": e, "cutoff": cutoff}
            ).fetchone()
            if nxt is None:
                result.sports_done.append(sport)
                break
            c, e = nxt[0], nxt[1]
            latest = conn.execute(_LATEST_KICKOFF_SQL, {"e": e}).fetchone()[0]
            if latest is not None and latest >= cutoff:
                result.skipped_moved += 1
                cursor[sport] = [c, e]
                if deletes:
                    _write_cursor(conn, cursor, now)
                    conn.commit()
                continue
            result.games += 1
            if deletes:
                deleted = conn.execute(_DELETE_SQL, {"e": e}).rowcount
                cursor[sport] = [c, e]
                _write_cursor(conn, cursor, now)
                conn.commit()
                result.rows_deleted += max(deleted, 0)
            else:
                # The dry run advances an in-memory cursor only, so it samples
                # the oldest games each pass and never moves the stored one.
                result.rows_would_delete += conn.execute(
                    _COUNT_SQL, {"e": e}
                ).fetchone()[0]
                result.rows_examined += conn.execute(
                    "SELECT COUNT(*) FROM odds_snapshots WHERE odds_event_id = ?",
                    (e,),
                ).fetchone()[0]
        if out_of_time:
            break

    if deletes:
        if result.games or result.skipped_moved:
            logger.info(
                "odds_snapshots prune: %d games thinned to closing lines, "
                "%d rows deleted, %d skipped (kickoff moved inside the "
                "window); sports finished: %s",
                result.games, result.rows_deleted, result.skipped_moved,
                ",".join(result.sports_done) or "none",
            )
    else:
        # Loud on purpose: a silent dry run reads exactly like one never wired.
        logger.info(
            "odds_snapshots prune DRY RUN (window %d days): the %d oldest "
            "games (sample cap %d) would lose %d of %d rows, %d skipped "
            "(kickoff moved); nothing was deleted.",
            retention_days, result.games, DRY_RUN_SAMPLE_GAMES,
            result.rows_would_delete, result.rows_examined,
            result.skipped_moved,
        )
    return result
