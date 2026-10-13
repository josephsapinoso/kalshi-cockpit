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
import math
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
        legs, out["dropped_legs"] = drop_implied_legs(legs)
    out["legs"] = legs
    # NULL on every card built before v61 and on every skip: no sources were
    # asked for, so none are claimed. Never an empty list standing in for one.
    raw_sources = out.pop("sources_json", None)
    out["sources"] = json.loads(raw_sources) if raw_sources else None
    raw_recheck = out.pop("recheck_source_json", None)
    out["recheck_source"] = json.loads(raw_recheck) if raw_recheck else None
    return out


def _score_predicate(market_ticker: str, side: str):
    """A game-line leg as a condition on the two teams' final scores, or None.

    `(group, team, ca, cb, lo, hi)`: the leg wins when
    `lo <= ca*score[team] + cb*score[other] <= hi`. `group` is the series'
    league prefix plus the game suffix, so a first-five or first-half series
    never shares scores with the full game. Kalshi's rung number is the whole
    score the leg needs, read off every captured strike (`MLBTOTAL-...-7` is
    "Over 6.5", `SPREAD-...-CLE2` "wins by over 1.5", `TEAMTOTAL-...-CLE3`
    "over 2.5"). `team` is None for a game total. Anything else -- props,
    a tie market, an unreadable rung -- is None and never dropped.
    """
    parts = market_ticker.strip().upper().split("-")
    if len(parts) != 3 or side not in ("yes", "no"):
        return None
    series, game, rung = parts
    team = rung.rstrip("0123456789")
    digits = rung[len(team):]
    if series.endswith("TEAMTOTAL"):
        kind, league = "teamtotal", series[: -len("TEAMTOTAL")]
    elif series.endswith("TOTAL"):
        kind, league = "total", series[: -len("TOTAL")]
    elif series.endswith("SPREAD"):
        kind, league = "spread", series[: -len("SPREAD")]
    elif series.endswith("GAME"):
        kind, league = "game", series[: -len("GAME")]
    else:
        return None
    if kind == "total":
        if team or not digits:
            return None
        ca, cb, k = 1, 1, int(digits)
    elif kind == "game":
        if not team or digits or team == "TIE":
            return None
        ca, cb, k = 1, -1, 1
    else:
        if not team or not digits:
            return None
        ca, cb, k = (1, 0, int(digits)) if kind == "teamtotal" else (1, -1, int(digits))
    lo, hi = (k, None) if side == "yes" else (None, k - 1)
    return (league, game), (team or None), ca, cb, lo, hi


def _b_interval(pred, a: int) -> tuple[float, float]:
    """The other team's scores (B >= 0) that satisfy `pred` given A = `a`."""
    ca, cb, lo, hi = pred
    lo = -math.inf if lo is None else lo
    hi = math.inf if hi is None else hi
    v = ca * a
    if cb == 0:
        return (0.0, math.inf) if lo <= v <= hi else (1.0, 0.0)
    if cb == 1:
        return max(0.0, lo - v), hi - v
    return max(0.0, v - hi), v - lo


def _implied(target, others) -> bool:
    """Every final score that wins all of `others` also wins `target`, and at
    least one such score exists. Scores are whole numbers >= 0; for each
    team-A score the other team's winning scores form one interval, so this
    walks A and compares intervals. A counterexample, if any, sits within
    a couple of rungs of the largest one, which bounds the walk."""
    rungs = [abs(x) for p in (target, *others) for x in p[2:] if x is not None]
    top = 2 * max(rungs, default=0) + 4
    feasible = False
    for a in range(top + 1):
        lo, hi = 0.0, math.inf
        for p in others:
            plo, phi = _b_interval(p, a)
            lo, hi = max(lo, plo), min(hi, phi)
        lo = math.ceil(lo)
        if lo > hi:
            continue
        feasible = True
        tlo, thi = _b_interval(target, a)
        tlo = math.ceil(tlo)
        # Some B in [lo, hi] outside [tlo, thi] loses the target.
        if lo < tlo or hi > thi or tlo > thi:
            return False
    return feasible


def drop_implied_legs(legs: list[dict]) -> tuple[list[dict], list[dict]]:
    """Drop every game-line leg the card's other legs already guarantee.
    Returns `(kept, dropped)`.

    Kalshi refuses such a combination as `duplicated_legs`: "Vegas winning by
    2+ already guarantees Vegas winning" (Joe, /parlays 2026-09-30), and
    "Over 6.5 runs and Cleveland winning by 2+ already guarantee Cleveland
    scoring over 2.5 runs" (Joe, a game-script card, 2026-10-13 -- three legs,
    which the win-beside-cover check this replaced could not see). Dropping a
    guaranteed leg is lossless: the combination pays on exactly the same
    final scores. Reads game winner, spread, game total and team total legs
    on either side; props are never read and never dropped, and only legs on
    other events count (two rungs of one event is the validator's refusal).
    One leg is dropped at a time and the rest re-checked, so two legs that
    guarantee each other lose only one. The stored `legs_json` keeps what the scout
    wrote; this runs on read.
    """
    kept, dropped = list(legs), []
    while True:
        preds = [
            _score_predicate(leg.get("market_ticker", ""), leg.get("side", ""))
            for leg in kept
        ]
        for i, pred in enumerate(preds):
            if pred is None:
                continue
            # Only legs on OTHER events: two rungs of one event, or one leg
            # twice, is the validator's to refuse, not this to drop.
            event = kept[i].get("event_ticker")
            group = [
                p for j, p in enumerate(preds)
                if j != i and p is not None and p[0] == pred[0]
                and kept[j].get("event_ticker") != event
            ]
            teams = {p[1] for p in (pred, *group) if p[1] is not None}
            if not group or len(teams) > 2:
                continue
            # Team A is the target's team (or either, for a game total); a
            # leg on the other team reads with its coefficients swapped.
            a_team = pred[1] or next(iter(teams), None)

            def oriented(p):
                _g, team, ca, cb, lo, hi = p
                if team is None or team == a_team:
                    return ca, cb, lo, hi
                return cb, ca, lo, hi

            if _implied(oriented(pred), [oriented(p) for p in group]):
                dropped.append(kept.pop(i))
                break
        else:
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
