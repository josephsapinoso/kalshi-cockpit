"""What a NO leg pays on, in words (#275).

Kalshi sends `no_sub_title` equal to `yes_sub_title` on the markets this desk
lists (`tests/fixtures/events_nhl_same_game.json`, `backend/kalshi/discovery.py`
reads the same field), so a NO leg shown with Kalshi's label reads exactly like
the YES leg beside it: "Columbus wins by over 2.5 goals" under both boxes. This
module words the opposite per leg KIND, from the YES sub-title:

    TOTAL   "Over 2.5 goals scored"            -> "Under 2.5 goals scored"
    GAME    "Columbus"                         -> "Columbus does not win"
    SPREAD  "Columbus wins by over 2.5 goals"  -> "Not: Columbus wins by 3+"
    other / unreadable                         -> "NO -- this does not happen"

**The kind is never guessed.** It is read from the series ticker with the
league prefix cut off (`KXNHLSPREAD` under `KXNHL` is `SPREAD`; `KXNHL1HSPREAD`
is `1HSPREAD`, a different kind, and gets the generic line). A sub-title that
does not match the shape the kind expects also gets the generic line.

What this does NOT establish: that the wording is how Kalshi settles an edge
case. "Under 2.5" is exact because a half-point strike cannot tie; on a whole
number strike a push is possible and this helper does not word it (it falls
through to the generic line, since `Over 3` is not `.5`).
"""

from __future__ import annotations

import math
import re
from typing import Optional

#: What a NO leg says when its kind or sub-title cannot be read. Never a guess.
GENERIC_NO_WORDS = "NO — this does not happen"

_LEAGUE_PREFIX = re.compile(r"^(KX[A-Z0-9]*)GAME-")
_HALF_STRIKE = r"\d+\.5"
_OVER = re.compile(rf"^Over ({_HALF_STRIKE})(\b.*)$")
_COVER = re.compile(rf"^(.+?) wins by over ({_HALF_STRIKE})(?: [A-Za-z]+)?$")


def league_prefix_of(game_event_ticker: str) -> Optional[str]:
    """`KXNFLGAME-26SEP13ATLPIT` -> `KXNFL`; `None` if it is not a game ticker."""
    match = _LEAGUE_PREFIX.match((game_event_ticker or "").strip().upper())
    return match.group(1) if match else None


def kind_of_series(series: str, league_prefix: Optional[str]) -> Optional[str]:
    """The series with the league prefix cut off, or `None` when it is not
    under that prefix. `KXNFLSPREAD`, `KXNFL` -> `SPREAD`."""
    series = (series or "").strip().upper()
    if not league_prefix or not series.startswith(league_prefix):
        return None
    return series[len(league_prefix):] or None


def no_side_words(
    *, kind: Optional[str], yes_label: Optional[str]
) -> str:
    """The NO side's wording for a leg of `kind` whose YES sub-title is
    `yes_label`. Falls back to `GENERIC_NO_WORDS` whenever either is unusable."""
    label = (yes_label or "").strip()
    if not label or kind is None:
        return GENERIC_NO_WORDS
    if kind == "TOTAL":
        match = _OVER.match(label)
        if match:
            return f"Under {match.group(1)}{match.group(2)}"
    elif kind == "GAME":
        # A moneyline sub-title is the bare team name; anything with a verb in
        # it is not that shape and is not reworded.
        if not re.search(r"\b(wins?|over|under|by)\b", label, re.IGNORECASE):
            return f"{label} does not win"
    elif kind == "SPREAD":
        match = _COVER.match(label)
        if match:
            needed = math.floor(float(match.group(2))) + 1
            return f"Not: {match.group(1)} wins by {needed}+"
    return GENERIC_NO_WORDS


def no_words_for(
    *, series: str, game_event_ticker: str, yes_label: Optional[str]
) -> str:
    """`no_side_words` for a leg named by its series and its game's ticker."""
    kind = kind_of_series(series, league_prefix_of(game_event_ticker))
    return no_side_words(kind=kind, yes_label=yes_label)
