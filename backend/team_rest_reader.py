"""Reads each team's previous game off the odds schedule the desk already stores.

No new source, no credits, no tokens. A per-row fact, never ranked by
(ADR 0071 s2.5).

**One window query per sport per request**, served by the covering index
`idx_odds_sport_commence (sport_key, commence_ms, odds_event_id, home_team,
away_team)` (schema v31): `odds_snapshots` is the ~10M-row table and an
unindexed read of it stalls the live desk. `tests/test_team_rest_reader.py`
pins the plan.

What this does not establish: a team's true previous game. It is the latest
game in the sportsbook feed's own schedule inside a 16-day window (enough for
an NFL bye). A team with no row in the window is `None`, never a long rest.
Names are the feed's own; there is no alias guessing.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Iterable, Optional

from backend.core.team_rest import rest_facts

#: Covers an NFL bye week with a day to spare.
WINDOW_DAYS = 16
_DAY_MS = 86_400_000

#: `odds_event_id` is in the index, so it rides along free; it lets a game
#: skip its own earlier (rescheduled) start times.
WINDOW_SQL = (
    "SELECT DISTINCT commence_ms, home_team, away_team, odds_event_id "
    "FROM odds_snapshots "
    "WHERE sport_key = ? AND commence_ms >= ? AND commence_ms < ?"
)


def _identities(conn, event_ids: list[str]) -> dict[str, tuple]:
    """`odds_event_id -> (sport_key, home_team, away_team)`, via
    `idx_odds_event_commence`."""
    out: dict[str, tuple] = {}
    for start in range(0, len(event_ids), 500):
        chunk = event_ids[start : start + 500]
        marks = ",".join("?" * len(chunk))
        rows = conn.execute(
            "SELECT odds_event_id, sport_key, home_team, away_team "
            f"FROM odds_snapshots WHERE odds_event_id IN ({marks}) "
            "GROUP BY odds_event_id",
            chunk,
        ).fetchall()
        for r in rows:
            out[r[0]] = (r[1], r[2], r[3])
    return out


def rest_for_games(
    conn: sqlite3.Connection, games: Iterable[tuple[str, Optional[int]]]
) -> dict[str, Optional[dict]]:
    """`{odds_event_id: {"home": {...}, "away": {...}} | None}`.

    `games` is `(odds_event_id, commence_ms)`. `None` when the game cannot be
    identified. Each side is `{team, days_rest, back_to_back, short_week}`.
    """
    games = list(games)
    wanted = {eid: c for eid, c in games if eid and c is not None}
    result: dict[str, Optional[dict]] = {eid: None for eid, _ in games if eid}
    if not wanted:
        return result
    ident = _identities(conn, sorted(wanted))
    by_sport: dict[str, list[str]] = defaultdict(list)
    for eid in wanted:
        if eid in ident and ident[eid][0]:
            by_sport[ident[eid][0]].append(eid)
    for sport, eids in by_sport.items():
        commences = [wanted[e] for e in eids]
        rows = conn.execute(
            WINDOW_SQL,
            (sport, min(commences) - WINDOW_DAYS * _DAY_MS, max(commences)),
        ).fetchall()
        for eid in eids:
            this_ms = wanted[eid]
            _, home, away = ident[eid]
            sides = {}
            for role, team in (("home", home), ("away", away)):
                prev = None
                for r in rows if team is not None else ():
                    if r[3] == eid or r[0] >= this_ms:
                        continue
                    if team in (r[1], r[2]) and (prev is None or r[0] > prev):
                        prev = r[0]
                facts = rest_facts(sport, this_ms, prev)
                sides[role] = {
                    "team": team,
                    "days_rest": facts.days_rest,
                    "back_to_back": facts.back_to_back,
                    "short_week": facts.short_week,
                }
            result[eid] = sides
    return result
