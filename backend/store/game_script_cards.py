"""`game_script_cards`: one row per card the game-script seat produced (ADR 0190).

A card is a 2-3 leg same-game story on Joe's four factors (who is playing,
game script, rest and travel, matchups), its `drop_if` conditions, or a skip
with a reason. **The table has no price, probability, confidence or edge
column, by design** (ADR 0189, ADR 0038): the model never sees a price and
the screen puts Kalshi's own single-leg asks beside the legs at read time.

Every outcome is a row, so nothing the seat did is silent: `built`,
`skipped` (the model declined, with its reason), `refused_budget` (a ceiling
said no; the reason names it) and `refused_invalid` (the server's validation
rejected the model's answer; the reason says which rule). A refused card is
never re-asked (ADR 0190 section 2).

The two CHECKs in `schema.sql` are mirrored here so a bad call fails with a
sentence naming the fault instead of a bare `IntegrityError`.

What this does not establish: that a card is any good. Nothing is registered
on a card; `combo_ticker` is kept only so which cards Joe bet can be counted.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Optional, Sequence

STATUSES = ("built", "skipped", "refused_budget", "refused_invalid")


def insert_card(
    conn: sqlite3.Connection,
    *,
    game_event_ticker: str,
    sport_key: str,
    kickoff_ms: int,
    built_ms: int,
    status: str,
    story: Optional[str] = None,
    legs: Optional[Sequence[dict]] = None,
    drop_if: Optional[str] = None,
    reason: Optional[str] = None,
    prompt_version: Optional[str] = None,
    agent_call_id: Optional[int] = None,
) -> int:
    """Write one card row and return its id."""
    if status not in STATUSES:
        raise ValueError(f"unknown card status {status!r}")
    if status == "built" and not (story and legs):
        raise ValueError("a built card needs a story and legs")
    if status != "built" and not reason:
        raise ValueError(f"a {status} card needs a reason")
    built = status == "built"
    cursor = conn.execute(
        "INSERT INTO game_script_cards (game_event_ticker, sport_key, "
        "kickoff_ms, built_ms, status, story, legs_json, drop_if, reason, "
        "prompt_version, agent_call_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            game_event_ticker,
            sport_key,
            kickoff_ms,
            built_ms,
            status,
            story if built else None,
            json.dumps(list(legs)) if built else None,
            drop_if if built else None,
            reason,
            prompt_version,
            agent_call_id,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _row_to_dict(row: sqlite3.Row) -> dict:
    out = dict(row)
    raw = out.pop("legs_json", None)
    out["legs"] = json.loads(raw) if raw else None
    return out


def sport_key_for(game_event_ticker: str) -> str:
    """The `sport_key` a card row carries, from the game's event ticker.

    The lower-cased league prefix with `KX` and `GAME` removed:
    `KXNFLGAME-26SEP13ATLPIT` -> `"nfl"`. Import this rather than re-deriving.
    """
    series = game_event_ticker.strip().upper().split("-")[0]
    if series.startswith("KX"):
        series = series[2:]
    if series.endswith("GAME"):
        series = series[: -len("GAME")]
    return series.lower()


def latest_for_game(
    conn: sqlite3.Connection,
    game_event_ticker: str,
    statuses: Optional[Sequence[str]] = None,
) -> Optional[dict]:
    """The newest card row for a game (`built_ms` DESC), legs decoded, or
    `None`. With `statuses`, only rows in one of them: the dedupe asks for
    `built`/`skipped`, so a refusal never blocks a retry."""
    sql = "SELECT * FROM game_script_cards WHERE game_event_ticker = ?"
    args: list = [game_event_ticker]
    if statuses:
        sql += " AND status IN (%s)" % ",".join("?" * len(statuses))
        args += list(statuses)
    row = conn.execute(sql + " ORDER BY built_ms DESC, id DESC LIMIT 1", args).fetchone()
    return _row_to_dict(row) if row is not None else None


def card_by_id(conn: sqlite3.Connection, card_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM game_script_cards WHERE id = ?", (card_id,)
    ).fetchone()
    return _row_to_dict(row) if row is not None else None
