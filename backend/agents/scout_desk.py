"""The scout desk -- a master scout and his staff, convened for one game.

Joe's design, 2026-08-21, in his own words: the Scout should be "the master
scout" with "a team report to him ... scout specialists if you will each
knowing their own home teams player status, team statuses, weather if they're
playing at home", and the master "can collect the notes from each of his staff,
and make more of an expert opinion that would finally serve me at my desk when
i go into the site."

So one briefing is three calls:

- **Two staff scouts, one per team.** Each covers exactly one club: player
  status (injuries, designations, scratches, probable starters), team status
  (form, rest, travel), and -- only when their club is the host -- the weather
  at their own park, because that is the staff scout's home ground and nobody
  else's.
- **One master scout.** He reads nothing but his staff's filed notes. He ranks
  what matters, says where the notes conflict or a source is thin, and admits
  what the desk could not confirm. He is forbidden to add facts of his own:
  a synthesis that quietly introduces new claims is a third researcher wearing
  an editor's title.

**Nobody on the desk outputs a number that could feed a bet.** Not the staff
(`ScoutReport` has no numeric forecast field -- see `scout.py`), and not the
master (`DeskBriefing` is prose fields only, pinned by
`tests/test_scout_desk.py`). The reason is the package rule in `base.py`:
anything producing a number is deterministic code; an unfalsifiable estimate
in a money path is worse than none. The desk serves Joe's own judgement; it
does not price anything.

**Every call is metered.** The desk spends from the same `agent_calls` day the
Skeptic does (`AgentBudget`, reserve-before-call), so a briefing is three of
the day's `AGENT_MAX_CALLS_PER_DAY`. The staff pair is all-or-nothing: one
scout's notes without the opposing scout's is a briefing with a blind side,
so if the budget cannot afford both, the desk refuses rather than files half.
The master is reserved only after the staff return, because a master with no
notes to read is spend with nothing to synthesise.

What this module does NOT establish
-----------------------------------
That the desk's output is any good, that a briefing moves any decision Joe
makes, or that three calls is the right shape. It has never run against a real
slate. It establishes only the contract: metered spend, sourced facts, no
numbers, and honest states for "filed nothing" versus "found nothing".
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .base import AgentConfig, structured_call
from .budget import AgentBudget
from .scout import WEB_SEARCH_TOOL, ScoutReport

logger = logging.getLogger(__name__)

# One staff scout's brief. The two hard rules are copied from `scout.SYSTEM`
# verbatim rather than referenced, because a system prompt is the one place a
# rule must be present to exist at all.
STAFF_SYSTEM_TEMPLATE = """\
You are the {team} scout on a betting research desk. You cover the {team} and \
only the {team} -- your opposite number covers {opponent}, so leave their side \
of the matchup to them.

For this one upcoming game, file notes on your team only:

- Player status: confirmed or probable starters, scratches, injuries and their \
designations, suspensions.
- Team status: recent form, rest, travel, back-to-backs, anything significant \
about the team as a whole.
{venue_clause}

Report only what you can source. For each finding give the fact, where it came \
from, and when it was reported. Recency is the whole point: a note from three \
days ago has usually been priced in by every venue; one from twenty minutes \
ago may not have been.

Two hard rules.

You must NOT estimate any probability, fair price, line, or point spread, and \
must not say whether any bet is good. That is not modesty; those numbers come \
from code that can be backtested, and an unfalsifiable estimate in the middle \
of a money path is worse than no estimate.

If you find nothing noteworthy, say so and return an empty findings list. An \
empty result is a useful answer. Inventing minor observations to look thorough \
makes the whole desk less trustworthy."""

HOME_VENUE_CLAUSE = (
    "- Conditions at your venue: your team is the host, so the ground is "
    "yours. Weather where it affects play (wind, rain, heat, altitude, roof "
    "or indoor status), and any venue news such as a change or postponement "
    "risk."
)
AWAY_VENUE_CLAUSE = (
    "- Your team is the visitor. The host's scout covers the venue and "
    "weather; you cover what travelling there costs your team."
)

MASTER_SYSTEM = """\
You are the master scout on a betting research desk. Your staff scouts -- one \
per team -- have filed their notes on one upcoming game. Synthesise them into \
a briefing for the desk's owner, who is not a professional bettor and reads \
this at a glance -- fill the board first, and keep the prose tight.

First fill in the instrument board: one tile per category (lineup, injury, \
weather, rest_travel, venue, other), each with a state and a note of a few \
words. The states, exactly:

- "fresh": at least one filed item in this category is recent enough that \
the market may not have absorbed it.
- "stale_only": items were filed, but every one is flagged as likely already \
priced in. Old news, checked.
- "unconfirmed": a scout searched this category and could not confirm it -- \
ran out of searches, found nothing where something should exist, or filed an \
unverified report. Unconfirmed is a warning, never an all-clear.
- "clear": the category was covered and there is genuinely nothing notable.

Then the prose, which is judgement about the notes, never new research:

- Rank what actually matters for this game, most important first, and name \
which scout each point came from.
- Where the notes conflict, or a source looks thin or stale, say so plainly.
- Say what the desk could not confirm, so an absence reads as "unanswered" \
rather than "fine".
- Plain language: define any betting or sports jargon in passing.

Three hard rules.

You may use ONLY what your staff filed. You must not add facts, however well \
known -- a synthesis that introduces new claims is a third researcher wearing \
an editor's title. If a staff note is marked as likely already priced in, \
carry that caveat with it.

You must NOT estimate any probability, fair price, line, or point spread, and \
must not say whether any bet is good.

If the staff filed little or nothing, say exactly that. A short briefing over \
thin notes is honest; a padded one is not."""


class BoardTile(BaseModel):
    """One instrument on the desk's board: a category, a state, a few words.

    Joe reads this at a glance -- phone and desktop both -- and asked for a
    cockpit, not prose ("I am more of a visual guy"), and for it to work on
    every sport -- so the categories
    are the sport-neutral ones `ScoutFinding` already uses, and the states are
    words rather than scores. `unconfirmed` exists because the first real
    briefing's most decision-relevant fact was a *gap* (weather unchecked):
    a board that can only show findings renders a gap as calm.
    """

    category: Literal[
        "lineup", "injury", "weather", "rest_travel", "venue", "other"
    ]
    state: Literal["fresh", "stale_only", "unconfirmed", "clear"]
    note: str = Field(
        description="A few words for the tile, e.g. 'starters long known' or "
        "'roof status unchecked'. Never a number."
    )


class DeskBriefing(BaseModel):
    """The master's synthesis. Prose and words only -- no field can carry a
    forecast.

    Every leaf in this schema is a string (including the `Literal` members on
    the board tiles), deliberately and forever: `tests/test_scout_desk.py`
    walks it recursively and fails if any numeric type appears anywhere. That
    is the package's no-numbers rule made structural, as it is for
    `ScoutFinding`.
    """

    board: list[BoardTile] = Field(
        default_factory=list,
        description="One tile per category, always all six, filled from the "
        "staff's notes. The phone renders these before any prose.",
    )
    headline: str = Field(
        description="One sentence: the single most important thing the desk "
        "found, or the honest statement that it found little."
    )
    assessment: str = Field(
        description="The master scout's read of his staff's notes, a short "
        "paragraph. Judgement about relevance and reliability -- never new "
        "facts, never a number that could feed a bet."
    )
    what_matters: list[str] = Field(
        default_factory=list,
        description="Ranked, most important first. Each entry names which "
        "scout filed the underlying note.",
    )
    conflicts: list[str] = Field(
        default_factory=list,
        description="Where staff notes disagree, or a source is thin, stale, "
        "or likely already priced in. Empty when the notes stand together.",
    )
    unanswered: list[str] = Field(
        default_factory=list,
        description="What the desk looked for and could not confirm. An "
        "absence must read as unanswered, not as fine.",
    )


@dataclass(frozen=True)
class StaffNote:
    """One staff scout's filing, with the identity the master needs.

    `report is None` means **the scout filed nothing** -- the call failed or
    was refused -- which is a different fact from a report with an empty
    findings list ("looked, found nothing"). The two must never collapse into
    each other; the master is told which one happened, in words.
    """

    role: Literal["home", "away"]
    team: str
    report: Optional[ScoutReport]


@dataclass(frozen=True)
class DeskResult:
    """What one convening produced. `status` is the honest one-word version.

    - `complete`: both staff filed, master synthesised.
    - `partial`: something filed, but a scout or the master is missing.
    - `failed`: nothing came back at all.
    - `refused`: the budget could not afford the staff pair; **no call was
      made** and nothing was spent.
    """

    status: Literal["complete", "partial", "failed", "refused"]
    staff: list[StaffNote]
    briefing: Optional[DeskBriefing]
    refusal_reason: Optional[str] = None


def _staff_prompt(
    *, event_title: str, league: str, commence_iso: Optional[str], team: str
) -> str:
    return (
        f"The game: {event_title}\n"
        f"League: {league}\n"
        f"Scheduled start (UTC): {commence_iso or 'unknown'}\n\n"
        f"File your notes on the {team} for this game. Search for current "
        f"news. Sourced facts only, and flag anything old enough to already "
        f"be priced in."
    )


def _master_prompt(staff: list[StaffNote], *, event_title: str) -> str:
    parts = [f"The game: {event_title}\n\nYour staff's filed notes:\n"]
    for note in staff:
        title = f"The {note.team} scout ({note.role} side)"
        if note.report is None:
            # Filed nothing != found nothing. The master must know which.
            parts.append(
                f"## {title}\nFILED NOTHING. The call failed; this is not the "
                f"same as finding nothing, and the briefing must say this "
                f"side of the desk is dark.\n"
            )
        else:
            parts.append(f"## {title}\n{note.report.model_dump_json(indent=2)}\n")
    parts.append(
        "\nWrite the desk briefing from these notes only. Rank what matters, "
        "flag conflicts and stale notes, and list what stayed unanswered."
    )
    return "\n".join(parts)


async def _staff_call(
    client,
    config: AgentConfig,
    *,
    role: Literal["home", "away"],
    team: str,
    opponent: str,
    event_title: str,
    league: str,
    commence_iso: Optional[str],
) -> StaffNote:
    """One staff scout. Exceptions become a filed-nothing note, never a raise:
    one dead scout must not take the other down with it through `gather`."""
    system = STAFF_SYSTEM_TEMPLATE.format(
        team=team,
        opponent=opponent,
        venue_clause=HOME_VENUE_CLAUSE if role == "home" else AWAY_VENUE_CLAUSE,
    )
    try:
        report = await structured_call(
            client,
            model=config.model,
            system=system,
            user_content=_staff_prompt(
                event_title=event_title,
                league=league,
                commence_iso=commence_iso,
                team=team,
            ),
            output_model=ScoutReport,
            max_tokens=6000,
            effort="high",
            tools=[WEB_SEARCH_TOOL],
        )
    except Exception:
        logger.exception("the %s scout (%s) died", team, role)
        report = None
    return StaffNote(role=role, team=team, report=report)


async def convene_desk(
    client,
    config: AgentConfig,
    budget: AgentBudget,
    *,
    ticker: str,
    event_title: str,
    league: str,
    commence_iso: Optional[str],
    home_team: str,
    away_team: str,
    now_ms: int,
) -> DeskResult:
    """Send the staff, then the master. Three metered calls, or a refusal.

    The order of operations is the money contract:

    1. The staff pair is affordable or nothing happens. Two `reserve` rows are
       written **before** the first request (crash direction: over-count, which
       costs a briefing and never money -- `budget.py` has the argument).
    2. The master is reserved only after at least one scout filed. No notes,
       no synthesis call.
    """
    if not budget.can_afford(2, now_ms):
        reason = budget.refusal_reason(2, now_ms)
        logger.warning("the desk is refused: %s", reason)
        return DeskResult(
            status="refused", staff=[], briefing=None, refusal_reason=reason
        )

    staff_ids = [
        budget.reserve(
            called_ms=now_ms,
            agent=f"scout_staff_{role}",
            model=config.model,
            ticker=ticker,
        )
        for role in ("home", "away")
    ]
    home_note, away_note = await asyncio.gather(
        _staff_call(
            client,
            config,
            role="home",
            team=home_team,
            opponent=away_team,
            event_title=event_title,
            league=league,
            commence_iso=commence_iso,
        ),
        _staff_call(
            client,
            config,
            role="away",
            team=away_team,
            opponent=home_team,
            event_title=event_title,
            league=league,
            commence_iso=commence_iso,
        ),
    )
    staff = [home_note, away_note]
    for call_id, note in zip(staff_ids, staff):
        budget.settle(
            call_id,
            verdict=(
                "filed_nothing"
                if note.report is None
                else f"{len(note.report.findings)} findings"
            ),
        )

    filed = [n for n in staff if n.report is not None]
    if not filed:
        return DeskResult(status="failed", staff=staff, briefing=None)

    if not budget.can_afford(1, now_ms):
        # The staff's notes still exist and are still served; the result is
        # honest about the synthesis being unaffordable today.
        logger.warning(
            "the master scout is unaffordable: %s",
            budget.refusal_reason(1, now_ms),
        )
        return DeskResult(status="partial", staff=staff, briefing=None)

    master_id = budget.reserve(
        called_ms=now_ms, agent="scout_master", model=config.model, ticker=ticker
    )
    try:
        briefing = await structured_call(
            client,
            model=config.model,
            system=MASTER_SYSTEM,
            user_content=_master_prompt(staff, event_title=event_title),
            output_model=DeskBriefing,
            max_tokens=4000,
            effort="high",
        )
    except Exception:
        logger.exception("the master scout died")
        briefing = None
    budget.settle(
        master_id, verdict="briefing" if briefing is not None else "filed_nothing"
    )
    if briefing is not None:
        briefing = complete_board(briefing, staff)

    if briefing is not None and len(filed) == len(staff):
        return DeskResult(status="complete", staff=staff, briefing=briefing)
    return DeskResult(status="partial", staff=staff, briefing=briefing)


BOARD_CATEGORIES: tuple[str, ...] = (
    "lineup", "injury", "weather", "rest_travel", "venue", "other",
)

# Most-alarming first. Used when the master files two tiles for one category:
# the one demanding more caution wins, because a collapse that picks the calm
# tile is a collapse that hides a warning.
_STATE_SEVERITY = {"fresh": 0, "unconfirmed": 1, "stale_only": 2, "clear": 3}

# What a staff scout's `searched_for` entry must mention for a category to
# count as *searched*. Free text against fixed words is a heuristic and is
# used only in the safe direction: failing to match turns a `clear` into an
# `unconfirmed`, never the reverse.
_CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "lineup": ("lineup", "starter", "starting", "scratch", "probable"),
    "injury": ("injur", "suspens", "designat"),
    "weather": ("weather", "forecast", "wind", "rain", "roof", "temperature"),
    "rest_travel": ("travel", "rest", "back-to-back", "schedule", "fatigue"),
    "venue": ("venue", "stadium", "park", "arena", "ground", "field", "court"),
}


def _searched_categories(staff: list[StaffNote]) -> set[str]:
    """Categories some scout actually looked at: filed a finding in it, or
    named it in `searched_for`. `other` is covered by any filing at all --
    it is the catch-all, and demanding a search string for it would turn
    every quiet briefing's sixth tile amber for no reason."""
    covered: set[str] = set()
    searched_text = " ".join(
        term.lower()
        for note in staff
        if note.report is not None
        for term in note.report.searched_for
    )
    for note in staff:
        if note.report is None:
            continue
        covered.add("other")
        for finding in note.report.findings:
            covered.add(finding.category)
    for category, hints in _CATEGORY_HINTS.items():
        if any(hint in searched_text for hint in hints):
            covered.add(category)
    return covered


def complete_board(briefing: DeskBriefing, staff: list[StaffNote]) -> DeskBriefing:
    """Project the master's board onto exactly the six categories, safely.

    The schema alone cannot promise a complete board: `board` has no length or
    uniqueness validator, so the model can file four tiles -- and a missing
    tile would render as *nothing*, which reads calmer than "unconfirmed".
    That is the exact defect the board was written to close (an unchecked
    instrument must never look like a clear one), reintroduced by omission.

    Three rules, each in the safe direction only:

    - A category the master did not file becomes `unconfirmed`.
    - Duplicate tiles collapse to the most-alarming state filed.
    - `clear` must be earned: if no scout filed a finding in the category or
      named it in `searched_for`, the tile is rewritten `unconfirmed` --
      "nothing notable" from a desk that never looked is not a finding.
    """
    by_category: dict[str, BoardTile] = {}
    for tile in briefing.board:
        held = by_category.get(tile.category)
        if held is None or (
            _STATE_SEVERITY[tile.state] < _STATE_SEVERITY[held.state]
        ):
            by_category[tile.category] = tile

    covered = _searched_categories(staff)
    completed: list[BoardTile] = []
    for category in BOARD_CATEGORIES:
        tile = by_category.get(category)
        if tile is None:
            tile = BoardTile(
                category=category,  # type: ignore[arg-type]
                state="unconfirmed",
                note="the master filed no tile here",
            )
        elif tile.state == "clear" and category not in covered:
            tile = BoardTile(
                category=tile.category,
                state="unconfirmed",
                note=(tile.note + " — but no scout searched this").strip(" —"),
            )
        completed.append(tile)
    return briefing.model_copy(update={"board": completed})
