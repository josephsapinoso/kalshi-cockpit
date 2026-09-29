"""Reads each team's previous game off the desk's one-row-per-game schedule.

No new source, no credits, no tokens. A per-row fact, never ranked by
(ADR 0071 s2.5).

**Reads `odds_fixtures`, never `odds_snapshots`.** The snapshot table is the
~10M-row one (thousands of rows per game); `odds_fixtures` has one row per
game, kept current by `trg_odds_fixtures_upsert` on every snapshot insert.
Identities are primary-key seeks; the window is one range read per sport on
`idx_odds_fixtures_commence (commence_ms, sport_key)`.
`tests/test_team_rest_reader.py` pins both plans and that neither touches
`odds_snapshots`.

What this does not establish: a team's true previous game. It is the latest
game in the feed's schedule inside a 16-day window (enough for an NFL bye).
It relies on the trigger-maintained table, whose `commence_ms` is the latest
belief for a fixture (a rescheduled game shows only its newest start). The
v47 backfill is bounded (kickoffs from about seven days before 2026-09-17),
so a lookback reaching before that can miss games; a missing game reads as
`None`, never a long rest. A team with no row in the window is `None`. Names
are the feed's own; there is no alias guessing.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Iterable, Optional

from backend.core.team_rest import rest_facts

#: Covers an NFL bye week with a day to spare.
WINDOW_DAYS = 16
_DAY_MS = 86_400_000

#: One range on `idx_odds_fixtures_commence`; the sport rides in the same
#: index. `odds_event_id` lets a game skip its own row.
WINDOW_SQL = (
    "SELECT commence_ms, home_team, away_team, odds_event_id "
    "FROM odds_fixtures "
    "WHERE commence_ms >= ? AND commence_ms < ? AND sport_key = ?"
)


def identity_sql(n: int) -> str:
    return (
        "SELECT odds_event_id, sport_key, home_team, away_team "
        f"FROM odds_fixtures WHERE odds_event_id IN ({','.join('?' * n)})"
    )


def _identities(conn, event_ids: list[str]) -> dict[str, tuple]:
    """`odds_event_id -> (sport_key, home_team, away_team)`: primary-key seeks."""
    out: dict[str, tuple] = {}
    for start in range(0, len(event_ids), 500):
        chunk = event_ids[start : start + 500]
        for r in conn.execute(identity_sql(len(chunk)), chunk).fetchall():
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
            (min(commences) - WINDOW_DAYS * _DAY_MS, max(commences), sport),
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
