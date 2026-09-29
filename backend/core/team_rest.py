"""How rested a team is going into a game, from two start times.

A per-row FACT shown beside a leg (ADR 0071 s2.5): it is never a sort key, a
filter, a score or an input to a price. Nothing here reads a database.

What this does not establish: that rest moves a price or a result. It says how
long ago the team's previous game on the desk's schedule began, no more. The
previous start time is the sportsbook feed's, so a game the feed never listed
(a preseason game, a cancelled-then-replayed one) is invisible and the rest
reads longer than it was.

**Hours between start times, never calendar dates.** A 10:30pm ET tip is the
next UTC day, so comparing dates calls a real back-to-back "1 day of rest".

**No previous game on record is `None` on every field, never `0`.** A zero
would say "played yesterday" about a team we simply have no schedule for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_HOUR_MS = 3_600_000

#: Under this gap, two games of a nightly league are a back-to-back.
BACK_TO_BACK_HOURS = 36
#: Under this gap, an NFL/NCAAF game follows a short week.
SHORT_WEEK_HOURS = 6 * 24

_NIGHTLY_PREFIXES = ("basketball_", "icehockey_")
_FOOTBALL_PREFIXES = ("americanfootball_",)


@dataclass(frozen=True)
class RestFacts:
    days_rest: Optional[int]
    back_to_back: Optional[bool]
    short_week: Optional[bool]


_UNKNOWN = RestFacts(days_rest=None, back_to_back=None, short_week=None)


def rest_facts(
    sport_key: str,
    this_commence_ms: int,
    previous_commence_ms: Optional[int],
) -> RestFacts:
    """Rest before this game. `back_to_back` is nightly leagues only (None
    elsewhere), `short_week` is NFL/NCAAF only, MLB gets `days_rest` alone."""
    if previous_commence_ms is None or previous_commence_ms >= this_commence_ms:
        return _UNKNOWN
    gap_hours = (this_commence_ms - previous_commence_ms) / _HOUR_MS
    # Round-half-up, not Python's banker's rounding. Clamped at 0 so a
    # same-day doubleheader does not read as -1.
    days_rest = max(0, int(gap_hours / 24 + 0.5) - 1)
    key = sport_key or ""
    back_to_back = (
        gap_hours < BACK_TO_BACK_HOURS if key.startswith(_NIGHTLY_PREFIXES) else None
    )
    short_week = (
        gap_hours < SHORT_WEEK_HOURS if key.startswith(_FOOTBALL_PREFIXES) else None
    )
    return RestFacts(days_rest=days_rest, back_to_back=back_to_back, short_week=short_week)
