"""The game-script seat: one same-game parlay card for one game (ADR 0190, #215).

Joe's #212 answer (A): the desk proposes the same-game build itself. This seat
reads one game's leg listing and returns a 2-3 leg story on his four factors
(who is playing, game script, rest and travel, matchups), the conditions under
which to drop it, or a skip with a reason.

**Shape copied from `leg_verdict.py`, not shared with it**: one metered call
through the shared `AgentBudget`, at most `GAME_SCRIPT_MAX_SEARCHES` searches,
`agent = 'game_script'` on `agent_calls`; a budget check before anything,
`reserve` before the request, `settle` whatever happens.

**The model never sees a price or a chance** (ADR 0189). `listing_for_prompt`
reduces each leg to an explicit whitelist of fields, so a field added to
`list_game_legs` later reaches the model only by being named here.
`CardOutput` has no probability, confidence or edge field, and the prompt
forbids one. No combined or "as if independent" figure exists anywhere.

**The server validates before storing and never re-asks** (`validate_card`):
every leg must be in the listing, sides must be allowed (`is_yes_only`), no
event may exceed its `size_max` (one rung per `size_max 1` event), and there
must be 2-3 legs. A failure is a `refused_invalid` row with the reason.

What this does not establish: that a story is right, that the facts it cites
are current, or that Kalshi will mint the combination.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, Field

from ..store import game_script_cards
from .base import AgentConfig, CallUsage, structured_call
from .budget import AgentBudget
from .scout import WEB_SEARCH_TOOL

logger = logging.getLogger(__name__)

AGENT_NAME = "game_script"

#: Bumped whenever `SYSTEM` or the prompt's shape changes, so a stored card
#: says which instructions built it.
PROMPT_VERSION = "3"

GAME_SCRIPT_MAX_SEARCHES = 3
GAME_SCRIPT_SEARCH_TOOL = {**WEB_SEARCH_TOOL, "max_uses": GAME_SCRIPT_MAX_SEARCHES}

MIN_LEGS = 2
MAX_LEGS = 3

#: The only leg fields the model is shown. Whitelisted, never "everything but
#: the prices": see the module docstring.
PROMPT_LEG_FIELDS = (
    "market_ticker",
    "event_ticker",
    "title",
    "yes_label",
    "no_label",
    "player",
    "strike",
    "allowed_sides",
    "one_per_event",
)

SYSTEM = """\
You are the game-script scout at a betting research desk. Joe, who reads \
this, is a beginner. For ONE game you build a single same-game parlay card: \
two or three bets on this game, joined into one ticket, chosen because they \
tell one coherent story about how the game is likely to go.

Build the story from four things, in this order: (1) who is playing -- \
injuries, inactives, starters, lineups, starting goalies or quarterbacks; \
(2) the game script -- pace, who is likely to lead, how the game is expected \
to be played; (3) schedule and rest -- days off, travel, a back-to-back; \
(4) matchups. Spend your searches on TODAY'S news first: confirmed lineups \
and starters, then the injury report. Last season's stats are already in \
every price, so never spend a search on them alone.

Use ONLY the legs in the list you are given. Copy each leg's market_ticker \
and event_ticker exactly, and pick a side (yes or no) from the sides that leg \
allows. Some events allow only one leg per ticket; never pick two legs from \
one of those. Pick two or three legs, never fewer or more. Never pair a team winning with that same team winning by a margin: Kalshi refuses the pair, because winning by the margin already includes winning. Never pick a full-game total and a first-half total in the same direction (both over, or both under): that is one opinion counted twice, not two.

Write the story in a few short sentences of everyday words: what you found \
and how the legs fit together. List every page you took a fact from in \
sources, each with its address and the date it was published (YYYY-MM-DD, \
or empty if the page gives none); a card with no source is refused. Write \
ticket_needs: in plain words, what has to happen in the game for every leg \
to win at once (for example "Virginia Tech wins by 1 to 3 points and the \
game stays under 52 points"). Then write drop_if: the specific news, still \
unknown now and able to change before kickoff, that would make Joe drop \
this card (for example a starter ruled out). Never name something already \
settled, like a suspension that runs past the game. If you cannot build a \
coherent card, or the facts are too thin, set skip to true and say why in \
reason; a skip is a good answer.

Two hard rules.

You must NOT estimate any probability, fair price, line, or point spread, and \
must not say whether any bet is good. That is not modesty; those numbers come \
from code that can be backtested, and an unfalsifiable estimate in the middle \
of a money path is worse than no estimate.

You are never shown a price, and you must not state one, nor a combined \
chance, a confidence, or an edge. Your card is a story and a list of legs, \
nothing more."""


class CardLeg(BaseModel):
    market_ticker: str
    event_ticker: str
    side: Literal["yes", "no"]


class CardSource(BaseModel):
    """One page a fact came from. `published` is a date string, never parsed
    into a number: an unknown date is the empty string, not a guess."""

    url: str = Field(description="The page's full address.")
    published: str = Field(
        default="", description="The date the page was published, YYYY-MM-DD, or empty."
    )


class CardOutput(BaseModel):
    """A story and legs, or a skip. No field can carry a probability,
    confidence or edge: `tests/test_game_script_card.py` walks the schema."""

    skip: bool = Field(
        default=False,
        description="true if no coherent 2-3 leg card can be built.",
    )
    reason: str = Field(
        default="", description="Why you skipped. Empty when you built a card."
    )
    story: str = Field(
        default="",
        description="A few short everyday-word sentences: the facts, their "
        "source, and how the legs fit. No probability, price or edge.",
    )
    legs: list[CardLeg] = Field(
        default_factory=list, description="Two or three legs from the list."
    )
    drop_if: str = Field(
        default="",
        description="The specific news, still unknown and able to change before "
        "kickoff, that should make Joe drop this card.",
    )
    sources: list[CardSource] = Field(
        default_factory=list,
        description="Every page a fact in the story came from, with its date.",
    )
    ticket_needs: str = Field(
        default="",
        description="In plain words, what has to happen in the game for every "
        "leg to win at once. Words only: no probability, price or edge.",
    )


def listing_for_prompt(listing: dict) -> list[tuple[str, list[dict]]]:
    """`(group label, legs)` from a `list_game_legs` result, each leg reduced
    to `PROMPT_LEG_FIELDS`. Everything else, prices and chances included, is
    dropped here and nowhere else."""
    return [
        (
            str(group.get("label") or group.get("series") or ""),
            [{f: leg.get(f) for f in PROMPT_LEG_FIELDS} for leg in group.get("legs", [])],
        )
        for group in listing.get("groups", [])
    ]


def build_prompt(*, game_title: str, sport_key: str, kickoff_iso: str, listing: dict) -> str:
    """The user turn: the game, kickoff, and the price-free leg list."""
    lines = []
    for label, legs in listing_for_prompt(listing):
        lines.append(f"## {label}")
        for leg in legs:
            parts = [
                f"market_ticker={leg['market_ticker']}",
                f"event_ticker={leg['event_ticker']}",
                f"title={leg['title']!r}",
            ]
            if leg["yes_label"]:
                parts.append(f"yes={leg['yes_label']!r}")
            if leg["no_label"]:
                parts.append(f"no={leg['no_label']!r}")
            if leg["player"]:
                parts.append(f"player={leg['player']}")
            if leg["strike"] is not None:
                parts.append(f"strike={leg['strike']}")
            parts.append("sides=" + "/".join(leg["allowed_sides"]))
            if leg["one_per_event"]:
                parts.append("ONE LEG ONLY from this event")
            lines.append("- " + "; ".join(parts))
    return "\n".join([
        f"Game: {game_title} ({sport_key}).",
        f"Kickoff: {kickoff_iso}.",
        "Build one same-game card from these legs, or skip:",
        *lines,
    ])


#: Words that would turn `ticket_needs` from a description of the game into a
#: forecast or a price (rule 2: no combined chance). Matched on lower-cased
#: text; a margin like "by 1 to 3 points" is a fact about the game and passes.
TICKET_NEEDS_FORBIDDEN = ("%", "probab", "chance", "odds", "likel", "edge", "cents", "price")


def validate_card(card: CardOutput, listing: dict) -> Optional[str]:
    """`None` if the card may be stored as built, else the reason it may not.

    Runs on the server before anything is stored; the model is never asked
    again on a failure.
    """
    if not card.story.strip() or not card.drop_if.strip():
        return "the card has no story or no drop-if condition"
    if not any(src.url.strip().startswith(("http://", "https://")) for src in card.sources):
        return "the card names no source page for its facts"
    needs = card.ticket_needs.strip()
    if not needs:
        return "the card does not say what the ticket needs to happen"
    if any(word in needs.lower() for word in TICKET_NEEDS_FORBIDDEN):
        return "what the ticket needs must be words about the game, not a chance or a price"
    if not MIN_LEGS <= len(card.legs) <= MAX_LEGS:
        return f"the card has {len(card.legs)} legs; it needs {MIN_LEGS} to {MAX_LEGS}"
    by_market = {
        leg["market_ticker"]: leg
        for group in listing.get("groups", [])
        for leg in group.get("legs", [])
    }
    seen: set[str] = set()
    per_event: dict[str, int] = {}
    for leg in card.legs:
        facts = by_market.get(leg.market_ticker)
        if facts is None or facts["event_ticker"] != leg.event_ticker:
            return f"{leg.market_ticker} is not in this game's leg listing"
        if leg.market_ticker in seen:
            return f"{leg.market_ticker} is named twice"
        seen.add(leg.market_ticker)
        if leg.side not in facts["allowed_sides"]:
            return f"{leg.market_ticker} does not allow the {leg.side} side"
        per_event[leg.event_ticker] = per_event.get(leg.event_ticker, 0) + 1
        cap = facts.get("size_max")
        if cap and cap > 0 and per_event[leg.event_ticker] > cap:
            return (
                f"{leg.event_ticker} allows {cap} leg"
                f"{'' if cap == 1 else 's'} in a combination"
            )
    return None


@dataclass(frozen=True)
class CardResult:
    """One seat run, already stored. `status` is the row's status."""

    status: str
    card_id: int
    reason: Optional[str]
    usage: Optional[CallUsage]
    agent_call_id: Optional[int]


async def build_card(
    conn: sqlite3.Connection,
    client,
    config: AgentConfig,
    budget: AgentBudget,
    *,
    game_event_ticker: str,
    sport_key: str,
    kickoff_ms: int,
    game_title: str,
    kickoff_iso: str,
    listing: dict,
    now_ms: int,
) -> CardResult:
    """One metered call, or a refusal that spends nothing. Always one row."""

    def store(status, **kw) -> int:
        return game_script_cards.insert_card(
            conn,
            game_event_ticker=game_event_ticker,
            sport_key=sport_key,
            kickoff_ms=kickoff_ms,
            built_ms=now_ms,
            status=status,
            prompt_version=PROMPT_VERSION,
            **kw,
        )

    reason = budget.refusal_reason(
        1, now_ms, searches_worst_case=GAME_SCRIPT_MAX_SEARCHES
    )
    if reason is not None:
        logger.warning("the game-script scout is refused: %s", reason)
        return CardResult(
            "refused_budget", store("refused_budget", reason=reason), reason, None, None
        )

    call_id = budget.reserve(
        called_ms=now_ms,
        agent=AGENT_NAME,
        model=config.model,
        ticker=game_event_ticker,
        side=None,
    )
    prompt = build_prompt(
        game_title=game_title, sport_key=sport_key,
        kickoff_iso=kickoff_iso, listing=listing,
    )
    try:
        outcome = await structured_call(
            client,
            model=config.model,
            system=SYSTEM,
            user_content=prompt,
            output_model=CardOutput,
            max_tokens=3000,
            effort="medium",
            tools=[GAME_SCRIPT_SEARCH_TOOL],
        )
        parsed, usage = outcome.parsed, outcome.usage
    except Exception:
        logger.exception("the game-script scout died")
        parsed, usage = None, None

    if parsed is None:
        budget.settle(call_id, verdict="filed_nothing", usage=usage)
        why = "the call returned nothing"
        return CardResult(
            "refused_invalid",
            store("refused_invalid", reason=why, agent_call_id=call_id),
            why, usage, call_id,
        )

    if parsed.skip:
        budget.settle(call_id, verdict="skip", usage=usage)
        why = parsed.reason.strip() or "the scout skipped this game without saying why"
        return CardResult(
            "skipped",
            store("skipped", reason=why, agent_call_id=call_id),
            why, usage, call_id,
        )

    # A win leg beside the same team's cover is dropped before validation,
    # not refused: the pair pays on the same outcomes as the cover alone, and
    # Kalshi refuses it as `duplicated_legs`. The stored legs stay as the
    # scout wrote them; `game_script_cards` drops the same leg on read.
    kept, _dropped = game_script_cards.drop_implied_win_legs(
        [leg.model_dump() for leg in parsed.legs]
    )
    invalid = validate_card(
        parsed.model_copy(update={"legs": [CardLeg(**leg) for leg in kept]}), listing
    )
    if invalid is not None:
        budget.settle(call_id, verdict="invalid", usage=usage)
        return CardResult(
            "refused_invalid",
            store("refused_invalid", reason=invalid, agent_call_id=call_id),
            invalid, usage, call_id,
        )

    budget.settle(call_id, verdict="built", usage=usage)
    return CardResult(
        "built",
        store(
            "built",
            story=parsed.story.strip(),
            legs=[leg.model_dump() for leg in parsed.legs],
            drop_if=parsed.drop_if.strip(),
            sources=[
                src.model_dump() for src in parsed.sources
                if src.url.strip().startswith(("http://", "https://"))
            ],
            ticket_needs=parsed.ticket_needs.strip(),
            agent_call_id=call_id,
        ),
        None, usage, call_id,
    )
