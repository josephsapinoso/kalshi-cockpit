"""Does a combination about to be bought bet against one Joe already holds?

Joe, 2026-10-03, after a night on which three of his tickets bet against
each other (Penn St. -2.5 YES on one ticket and NO on another; Over and
Under the same Pitt/VT total; Northwestern to win beside Penn St. to cover).
In each pair one ticket had to lose that leg, so part of the stake paid two
fees to cancel itself. He chose a warning at the moment of the bet.

**Two clashes, both exact, nothing inferred:**

- `opposite_side` -- the same market, the other side. One of the two legs
  loses whatever happens.
- `other_winner` -- two different YES outcomes of the same full-game winner
  event (a series ending in `GAME`: `KXNHLGAME`, `KXNCAAFGAME`). At most one
  team wins. A first-half winner market is NOT included: it has a tie
  outcome, and neither leg might win.

A clash between DIFFERENT market families (a team to win beside the other
team to cover a spread, a moneyline beside a total) is not detected: whether
two such legs can both win depends on the score, and saying so would be a
guess. The module says it found nothing, never that nothing clashes.

**It warns and never blocks.** Nothing on the order, RFQ or hedge path reads
this module; a clash is a fact on the screen, and sometimes a deliberate one
(a hedge is exactly a bet on the other side).

What this does NOT establish: that the held positions are still live at the
venue (it reads `parlay_positions` open rows with pending legs, the same
bookkeeping `/api/hedge` lists), or anything about a combination whose legs
the desk never recorded (no `parlay_lookups` row parses for it).
"""

from __future__ import annotations

import re
import sqlite3
from typing import Optional

from .parlays import legs_for_position

OPPOSITE_SIDE = "opposite_side"
OTHER_WINNER = "other_winner"

#: A full-game winner market: `<league>GAME-<fixture>-<team>`.
_GAME_MARKET = re.compile(r"^(KX[A-Z0-9]*GAME-[A-Z0-9]+)-[A-Z0-9]+$")


def candidate_legs(
    conn: sqlite3.Connection, combo_ticker: str
) -> Optional[list[dict]]:
    """The legs of `combo_ticker` as the desk recorded them when it minted
    or looked it up (newest readable `parlay_lookups` row), or None."""
    for row in conn.execute(
        "SELECT selected_legs FROM parlay_lookups "
        "WHERE minted_market_ticker = ? ORDER BY requested_ms DESC, id DESC",
        (combo_ticker,),
    ):
        parsed = legs_for_position(row[0])
        if parsed is not None:
            return [
                {"ticker": leg["ticker"], "side": leg["side"], "label": leg["label"]}
                for leg in parsed.legs
            ]
    return None


def _held_legs(conn: sqlite3.Connection, exclude_combo: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT p.id AS position_id, p.label AS position_label, "
        "l.ticker, l.side, l.label "
        "FROM parlay_positions p "
        "JOIN parlay_position_legs l ON l.position_id = p.id "
        "WHERE p.status = 'open' AND l.outcome = 'pending' "
        "AND l.ticker IS NOT NULL "
        "AND (p.combo_ticker IS NULL OR p.combo_ticker != ?) "
        "ORDER BY p.id, l.leg_index",
        (exclude_combo,),
    ).fetchall()


def clashes(legs: list[dict], held: list) -> list[dict]:
    """Every (candidate leg, held leg) pair that is one of the two exact
    clashes. Pure, so the rule is testable without a database."""
    out: list[dict] = []
    for leg in legs:
        ticker, side = leg["ticker"], leg["side"]
        leg_game = _GAME_MARKET.match(ticker or "")
        for h in held:
            kind = None
            if h["ticker"] == ticker and h["side"] != side:
                kind = OPPOSITE_SIDE
            elif (
                leg_game
                and side == "yes"
                and h["side"] == "yes"
                and h["ticker"] != ticker
            ):
                held_game = _GAME_MARKET.match(h["ticker"] or "")
                if held_game and held_game.group(1) == leg_game.group(1):
                    kind = OTHER_WINNER
            if kind:
                out.append({
                    "kind": kind,
                    "leg_label": leg["label"],
                    "held_label": h["label"],
                    "position_id": h["position_id"],
                    "position_label": h["position_label"],
                })
    return out


def held_conflicts(conn: sqlite3.Connection, combo_ticker: str) -> dict:
    """The payload `/api/held-conflicts` serves for one combination."""
    legs = candidate_legs(conn, combo_ticker)
    if legs is None:
        return {"checked": False, "conflicts": []}
    return {"checked": True, "conflicts": clashes(legs, _held_legs(conn, combo_ticker))}
