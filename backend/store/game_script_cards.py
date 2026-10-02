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
    sources: Optional[Sequence[dict]] = None,
    ticket_needs: Optional[str] = None,
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
        "kickoff_ms, built_ms, status, story, legs_json, drop_if, sources_json, "
        "ticket_needs, reason, prompt_version, agent_call_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            game_event_ticker,
            sport_key,
            kickoff_ms,
            built_ms,
            status,
            story if built else None,
            json.dumps(list(legs)) if built else None,
            drop_if if built else None,
            json.dumps(list(sources)) if built and sources else None,
            ticket_needs if built and ticket_needs else None,
            reason,
            prompt_version,
            agent_call_id,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


RECHECK_STATUSES = ("triggered", "not_found", "unknown", "refused_budget")


def record_recheck(
    conn: sqlite3.Connection,
    card_id: int,
    *,
    recheck_ms: int,
    status: str,
    note: Optional[str] = None,
    source: Optional[dict] = None,
) -> None:
    """Stamp a card's T-2h drop-if re-check (#289). Once only: a card that
    already carries a re-check is never overwritten, so a second pass cannot
    pay twice or replace a `triggered` with a later `not_found`."""
    if status not in RECHECK_STATUSES:
        raise ValueError(f"unknown recheck status {status!r}")
    conn.execute(
        "UPDATE game_script_cards SET recheck_ms = ?, recheck_status = ?, "
        "recheck_note = ?, recheck_source_json = ? "
        "WHERE id = ? AND recheck_ms IS NULL",
        (recheck_ms, status, note, json.dumps(source) if source else None, card_id),
    )
    conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    out = dict(row)
    raw = out.pop("legs_json", None)
    legs = json.loads(raw) if raw else None
    out["dropped_legs"] = []
    if legs:
        legs, out["dropped_legs"] = drop_implied_win_legs(legs)
    out["legs"] = legs
    # NULL on every card built before v61 and on every skip: no sources were
    # asked for, so none are claimed. Never an empty list standing in for one.
    raw_sources = out.pop("sources_json", None)
    out["sources"] = json.loads(raw_sources) if raw_sources else None
    raw_recheck = out.pop("recheck_source_json", None)
    out["recheck_source"] = json.loads(raw_recheck) if raw_recheck else None
    return out


def _series_and_team(market_ticker: str) -> Optional[tuple[str, str, str]]:
    """`KXNHLSPREAD-26SEP29CHIVGK-VGK2` -> `("KXNHLSPREAD", "26SEP29CHIVGK",
    "VGK")`: series, game suffix, team with any trailing rung digits cut.
    `None` for a ticker that is not three dash-separated parts."""
    parts = market_ticker.strip().upper().split("-")
    if len(parts) != 3:
        return None
    return parts[0], parts[1], parts[2].rstrip("0123456789")


def drop_implied_win_legs(legs: list[dict]) -> tuple[list[dict], list[dict]]:
    """Drop a YES "team wins" leg when the card also has YES "that team wins
    by N+" for the same game. Returns `(kept, dropped)`.

    Kalshi refuses the pair as `duplicated_legs` ("Vegas winning by 2+
    already guarantees Vegas winning"; Joe hit it on /parlays 2026-09-30).
    Dropping the win leg is lossless: both-happen IS the cover, so the
    combination pays on exactly the same outcomes. Nothing else is touched.
    The stored `legs_json` keeps what the scout wrote; this runs on read.
    """
    covers = set()
    for leg in legs:
        parsed = _series_and_team(leg.get("market_ticker", ""))
        if parsed and leg.get("side") == "yes" and parsed[0].endswith("SPREAD"):
            covers.add((parsed[0][: -len("SPREAD")], parsed[1], parsed[2]))
    kept, dropped = [], []
    for leg in legs:
        parsed = _series_and_team(leg.get("market_ticker", ""))
        if (
            parsed
            and leg.get("side") == "yes"
            and parsed[0].endswith("GAME")
            and (parsed[0][: -len("GAME")], parsed[1], parsed[2]) in covers
        ):
            dropped.append(leg)
        else:
            kept.append(leg)
    return kept, dropped


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
