"""The two cuts a list screen may make: league, and kickoff window.

Decision-map ticket #15, resolved by Joe 2026-09-02 as option A: the Games,
Picks and Parlay lists get a sticky bar that cuts them by league and by how
soon the game starts, and `/api/slate` and `/api/parlays` grow the matching
query parameters. This module is the one place the parameters are parsed, so
the two routes cannot come to accept different vocabularies for the same cut.

**What a filter here may and may not do.** It removes rows; it never reorders
them. Both routes keep the ordering they had before the parameter existed
(kickoff on the slate, probability or the clock on the ladder), and nothing in
this module reads `edge_tenths`, `fair_probability`, `breakeven` or any other
figure a reader could take for profit. ADR 0071 §2.5: a gap may be shown on a
row and must never be ranked by, and `beta = -0.141` means a cut on it would
put the least trustworthy rows on top. A third cut is not added here without
saying which of those two rules it does not break.

**The vocabulary is the odds feed's sport key**, `baseball_mlb` and friends —
the keys `frontend/src/lib/leagueLabel.ts` renders and the parlay legs already
carry — never Kalshi's `product_metadata.competition` string ("Pro Baseball"),
which `event_links.league` holds verbatim. The slate resolves a row's league
through its linked fixture's `odds_snapshots.sport_key`, the same column the
ladder reads, so one value cuts both lists on the same partition. The allowed
set is `IN_SCOPE_LEAGUES`' values: a league this deployment cannot devig
against has no linked row to show, so accepting it would only ever return an
empty list that reads as "no games" when it means "not a league here".

**Unknown is refused, never ignored.** An unrecognised `league` or an
out-of-range `within_hours` is a 422 with the allowed values in the detail. A
route that silently dropped a misspelt parameter would show the whole slate
under a heading claiming it was cut, which is the "unreadable resolves to a
value" defect on a query string.

**Absent is absent.** `parse_list_filter` returns `None` when neither
parameter is set, and callers add nothing to the payload in that case — the
unfiltered response stays byte-identical to what it was before this module
existed (`tests/test_list_filters.py` pins it).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .kalshi.discovery import IN_SCOPE_LEAGUES

#: The sport keys a `league` filter may name, sorted so the 422 detail and the
#: OpenAPI description list them in one stable order.
LEAGUE_FILTER_KEYS: tuple[str, ...] = tuple(sorted(set(IN_SCOPE_LEAGUES.values())))

#: The furthest a kickoff window may reach, in hours: one week. The slate
#: window itself holds rows with kickoffs eight days out (ticket #15's own
#: observation), so anything past this is "no cut", and the parameter should
#: be omitted rather than set to a number that means nothing.
MAX_WITHIN_HOURS = 168

_MS_PER_HOUR = 3_600_000


class FilterRefused(ValueError):
    """A parameter value this module will not act on. Carries the reason in
    words, for the 422 detail."""


@dataclass(frozen=True)
class ListFilter:
    """The parsed cut. Either field may be `None`; never both.

    `kickoff_from_ms`/`kickoff_until_ms` are the window `within_hours`
    resolves to at the instant the request was read, in the server's own
    milliseconds — served back so the screen can print the bound it was cut
    on rather than recomputing it from a browser clock.
    """

    league: Optional[str]
    within_hours: Optional[int]
    kickoff_from_ms: Optional[int]
    kickoff_until_ms: Optional[int]

    def as_dict(self, *, hidden: int) -> dict:
        """The echo the payload carries whenever a cut was applied.

        `hidden` is how many rows (slate) or candidate legs (ladder) the cut
        removed — the number that stops a filtered list from silently
        reading as the whole one ("refuses in words, never by omission").
        """
        return {
            "league": self.league,
            "within_hours": self.within_hours,
            "kickoff_from_ms": self.kickoff_from_ms,
            "kickoff_until_ms": self.kickoff_until_ms,
            "hidden": hidden,
        }

    def keeps_kickoff(self, commence_ms: Optional[int]) -> bool:
        """Whether a kickoff passes the window. An unknown kickoff never
        does: a row that cannot say when it starts cannot say it starts
        within three hours."""
        if self.kickoff_until_ms is None:
            return True
        if commence_ms is None:
            return False
        assert self.kickoff_from_ms is not None
        return self.kickoff_from_ms <= commence_ms <= self.kickoff_until_ms


def parse_list_filter(
    league: Optional[str],
    within_hours: Optional[int],
    *,
    now_ms: int,
) -> Optional[ListFilter]:
    """Validate the two query parameters; `None` when neither is set.

    Raises `FilterRefused` for a league outside `LEAGUE_FILTER_KEYS` or a
    window outside `1..MAX_WITHIN_HOURS`. The route turns that into a 422.
    An empty string is not "absent": it is a value, and an unknown one.
    """
    if league is None and within_hours is None:
        return None
    if league is not None and league not in LEAGUE_FILTER_KEYS:
        raise FilterRefused(
            f"league {league!r} is not one this desk carries; "
            f"one of {', '.join(LEAGUE_FILTER_KEYS)}"
        )
    if within_hours is not None and not 1 <= within_hours <= MAX_WITHIN_HOURS:
        raise FilterRefused(
            f"within_hours must be between 1 and {MAX_WITHIN_HOURS}, "
            f"got {within_hours!r}"
        )
    return ListFilter(
        league=league,
        within_hours=within_hours,
        kickoff_from_ms=None if within_hours is None else now_ms,
        kickoff_until_ms=(
            None if within_hours is None else now_ms + within_hours * _MS_PER_HOUR
        ),
    )
