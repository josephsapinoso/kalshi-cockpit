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
import math
import re
import sqlite3
from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, Field

from ..store import game_script_cards
from .base import AgentConfig, CallUsage, search_cap_rule, structured_call
from .budget import AgentBudget
from .scout import WEB_SEARCH_TOOL

logger = logging.getLogger(__name__)

AGENT_NAME = "game_script"

#: Bumped whenever `SYSTEM` or the prompt's shape changes, so a stored card
#: says which instructions built it.
PROMPT_VERSION = "5"

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
this card (for example a starter ruled out). Name ONE person and a status \
that is public before kickoff (out, scratched, in the lineup, starting): \
never something that happens in the game ("pulled early"), never "than \
expected", never "or" between triggers. Never name something already \
settled, like a suspension that runs past the game. \
Say "confirmed" or "starting" only when a source dated TODAY says so; \
otherwise say "expected". If you cannot build a \
coherent card, or the facts are too thin, set skip to true and say why in \
reason; a skip is a good answer.

""" + search_cap_rule(GAME_SCRIPT_MAX_SEARCHES) + """

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


_NUM_WORDS = {
    w: i for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve "
        "thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
    )
}
_NUM_WORDS.update({
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
})
_NUM = (
    r"(\d+(?:\.\d+)?|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
    r"(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?|"
    + "|".join(sorted((w for w in _NUM_WORDS), key=len, reverse=True))
    + r")"
)
#: `(pattern, side, inclusive)` for a stated bound in `ticket_needs`. A phrase
#: like "seven or fewer" is matched before a bare "under" so one number is read
#: one way.
_BOUND_PATTERNS = (
    (rf"\b{_NUM}\s+or\s+(?:fewer|less|under|lower|below)\b", "hi", True),
    (rf"\b(?:at most|no more than|up to|a maximum of)\s+{_NUM}\b", "hi", True),
    (rf"\b{_NUM}\s+or\s+(?:more|higher|greater|over|above)\b", "lo", True),
    (rf"\b{_NUM}\s*\+", "lo", True),
    (rf"\b(?:at least|a minimum of)\s+{_NUM}\b", "lo", True),
    (rf"\b(?:fewer than|less than|under|below)\s+{_NUM}\b", "hi", False),
    (rf"\b(?:more than|over|above|exceeds?|greater than)\s+{_NUM}\b", "lo", False),
)
_TOTAL_WORDS = ("total", "combined", "combine", "together", "two teams", "both teams")


def _number_of(token: str) -> Optional[float]:
    token = token.strip().lower()
    try:
        return float(token)
    except ValueError:
        pass
    parts = re.split(r"[- ]", token)
    if all(p in _NUM_WORDS for p in parts):
        return float(sum(_NUM_WORDS[p] for p in parts))
    return None


def _stated_bound(clause: str) -> Optional[tuple[str, int]]:
    """`("hi", n)` (at most n) or `("lo", n)` (at least n) when `clause` states
    exactly one bound with one number; `None` for none, a range, or anything
    read two ways. Whole numbers: "under 7" is at most 6."""
    text = clause.lower()
    found: list[tuple[str, int]] = []
    taken: list[tuple[int, int]] = []
    for pattern, side, inclusive in _BOUND_PATTERNS:
        for m in re.finditer(pattern, text):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            value = _number_of(m.group(1))
            if value is None:
                return None
            taken.append((m.start(), m.end()))
            if inclusive:
                n = math.ceil(value) if side == "lo" else math.floor(value)
            elif side == "hi":
                n = math.ceil(value) - 1
            else:
                n = math.floor(value) + 1
            found.append((side, n))
    # Any number left outside a matched bound ("1 to 3") makes it ambiguous.
    rest = text
    for s, e in sorted(taken, reverse=True):
        rest = rest[:s] + " " + rest[e:]
    for phrase in _TOTAL_WORDS:  # "the two teams" names the teams, not a bound
        rest = rest.replace(phrase, " ")
    if re.search(rf"\b{_NUM}\b", rest):
        return None
    return found[0] if len(found) == 1 else None


_TOTAL_LEG = re.compile(r"^(Over|Under) (\d+(?:\.\d+)?)\b", re.IGNORECASE)
_SPREAD_LEG = re.compile(r"^(.+?) wins by over (\d+(?:\.\d+)?)\b", re.IGNORECASE)
_PROP_LEG = re.compile(r"^(.+?):\s*(\d+)\+")


def _leg_constraint(leg_side: str, facts: dict) -> Optional[tuple[str, str, str, int]]:
    """`(kind, who, bound side, n)` for a leg whose served wording states a
    strike we can read, else `None`. Wording is what the desk serves: the YES
    sub-title, or the reworded NO label (a NO the desk cannot reword is
    skipped, never guessed)."""
    if leg_side == "no":
        candidates = [facts.get("no_label")]
    else:
        candidates = [facts.get("yes_label"), facts.get("title")]
    for text in candidates:
        text = (text or "").strip()
        m = _TOTAL_LEG.match(text)
        if m:
            line = float(m.group(2))
            if m.group(1).lower() == "over":
                return ("total", "", "lo", math.floor(line) + 1)
            return ("total", "", "hi", math.ceil(line) - 1)
        if leg_side == "no":
            continue
        m = _SPREAD_LEG.match(text)
        if m:
            return ("spread", m.group(1).strip(), "lo", math.floor(float(m.group(2))) + 1)
        m = _PROP_LEG.match(text)
        if m:
            return ("prop", m.group(1).strip(), "lo", int(m.group(2)))
    return None


def _names_in(clause: str, who: str) -> bool:
    low = clause.lower()
    who = who.lower()
    return bool(who) and (who in low or who.split()[-1] in low)


def ticket_needs_mismatch(needs: str, constraints: list[tuple[str, str, str, int]]) -> Optional[str]:
    """The reason `needs` disagrees with a leg's strike, or `None`.

    Conservative on purpose: a clause is checked only when it states exactly
    one number and is tied to exactly one leg (a total clause needs one total
    leg; a spread or prop clause must name the team or player). Anything
    ambiguous passes; this refuses a stated number that contradicts, nothing
    more."""
    clauses = re.split(r"[,;]|\band\b|\bwhile\b|\bbut\b|\bwhereas\b", needs, flags=re.IGNORECASE)
    for clause in clauses:
        bound = _stated_bound(clause)
        if bound is None:
            continue
        low = clause.lower()
        tied = None
        props = [c for c in constraints if c[0] == "prop" and _names_in(clause, c[1])]
        if len(props) == 1:
            tied = props[0]
        elif any(w in low for w in _TOTAL_WORDS):
            totals = [c for c in constraints if c[0] == "total"]
            if len(totals) == 1:
                tied = totals[0]
        else:
            spreads = [
                c for c in constraints
                if c[0] == "spread" and _names_in(clause, c[1]) and re.search(r"\bby\b", low)
            ]
            if len(spreads) == 1:
                tied = spreads[0]
        if tied is None:
            continue
        kind, who, leg_side, leg_n = tied
        if bound != (leg_side, leg_n):
            word = "at most" if leg_side == "hi" else "at least"
            stated = "at most" if bound[0] == "hi" else "at least"
            return (
                f"what the ticket needs says {stated} {bound[1]} "
                f"({clause.strip()!r}) but the {kind} leg"
                f"{' for ' + who if who else ''} needs {word} {leg_n}"
            )
    return None


#: Wording a pre-kickoff re-check cannot search for (#310): what happens in the
#: game, an unnamed baseline, or a workload no team announces. Deliberately
#: narrow: a plain "X is ruled out" or "X is not in the lineup" passes.
_DROP_IF_UNCHECKABLE = re.compile(
    r"\bpulled\b|\bduring (?:the |a )?(?:game|play|match)\b|\bin[- ]game\b"
    r"|\bthan expected\b|\bworkload\b",
    re.IGNORECASE,
)

#: A claim that something is settled today, which needs a source from today.
_CONFIRMED_CLAIM = re.compile(
    r"\bconfirmed\b|\b(?:is|are|will be|to be)\s+(?:the\s+)?starting\b|\bwill start\b",
    re.IGNORECASE,
)

#: The zone kickoff dates are shown in everywhere else: the frontend's
#: `DISPLAY_TIME_ZONE` (frontend/src/lib/format.ts) and `parlays.DESK_TIME_ZONE`
#: are both America/Los_Angeles. Not imported, to keep agents free of parlays.
GAME_DAY_TIME_ZONE = "America/Los_Angeles"


def _game_day(kickoff_ms: int) -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.fromtimestamp(kickoff_ms / 1000, ZoneInfo(GAME_DAY_TIME_ZONE)).strftime(
        "%Y-%m-%d"
    )


def validate_card(
    card: CardOutput, listing: dict, kickoff_ms: Optional[int] = None
) -> Optional[str]:
    """`None` if the card may be stored as built, else the reason it may not.

    Runs on the server before anything is stored; the model is never asked
    again on a failure. `kickoff_ms` arms the game-day-source rule; without it
    that one rule cannot be judged and is skipped.
    """
    if not card.story.strip() or not card.drop_if.strip():
        return "the card has no story or no drop-if condition"
    hit = _DROP_IF_UNCHECKABLE.search(card.drop_if)
    if hit:
        return (
            f"the drop-if condition says {hit.group(0)!r}, which cannot be checked "
            "before kickoff; name one person and a status public before the game"
        )
    if kickoff_ms is not None and _CONFIRMED_CLAIM.search(card.story):
        day = _game_day(kickoff_ms)
        if not any((src.published or "").strip()[:10] == day for src in card.sources):
            return (
                "the story says confirmed or starting but no source is dated on "
                f"game day ({day})"
            )
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
    constraints: list[tuple[str, str, str, int]] = []
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
        constraint = _leg_constraint(leg.side, facts)
        if constraint is not None:
            constraints.append(constraint)
    return ticket_needs_mismatch(needs, constraints)


def freeze_leg_at_build(leg: dict, listing: dict) -> dict:
    """The stored leg plus `at_build`: Kalshi's listed ask for the side the
    scout picked, the size at it, and when the listing was read (#283).

    **Per leg only.** Nothing here multiplies, adds or otherwise combines the
    legs' asks; a product would read as the combination's price, which only
    the makers' quote is (ADR 0189, rule 2). An ask the listing could not read
    stays `None`, never `0`. The model never saw these numbers: they are read
    from the same listing AFTER the call, for the record and for the
    "when written" figure on the card, and nothing scores a card on them
    (ADR 0190 section 7).
    """
    facts = next(
        (
            l for group in listing.get("groups", []) for l in group.get("legs", [])
            if l.get("market_ticker") == leg["market_ticker"]
        ),
        None,
    )
    listed = (facts or {}).get("listed") or {}
    side = listed.get(leg["side"]) or {}
    return {
        **leg,
        "at_build": {
            "ask_tenths": side.get("ask_tenths"),
            "size": side.get("size"),
            "read_ms": listed.get("read_ms"),
        },
    }


#: A reason that starts with this is a machine failure, not a judgement of the
#: scout's (#309): the card is retried and the screen says so.
CALL_FAILED_PREFIX = "the call failed"

_FAILURE_WORDS = {
    "schema_mismatch": (
        "the scout's answer did not match the card schema (a refusal or "
        "malformed output); its tokens are not counted"
    ),
    "call_error": "the call to the model errored (connection or API failure)",
    "refusal": "the model refused to answer",
    "no_output": "the model returned no parseable card",
    "search_failed": "the web search failed",
}

_SEARCH_BROKE_WORDS = (
    "unavailable", "not available", "error", "failed", "could not", "couldn't", "unable",
)


def _reason_says_search_broke(reason: str) -> bool:
    low = (reason or "").lower()
    return "search" in low and any(w in low for w in _SEARCH_BROKE_WORDS)


def call_failed_reason(kind: str, *, detail: str = "") -> str:
    text = f"{CALL_FAILED_PREFIX}: {_FAILURE_WORDS.get(kind, kind)}"
    return f"{text} ({detail})" if detail else text


def skip_is_search_failure(reason: str, usage: Optional[CallUsage]) -> bool:
    """A skip is a machine failure when the call searched zero times (usage
    read and 0, never an unreadable usage) or its reason says search broke."""
    if usage is not None and usage.web_searches == 0:
        return True
    return _reason_says_search_broke(reason)


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
        failure = outcome.failure
        detail = outcome.failure_detail or ""
    except Exception:
        logger.exception("the game-script scout died")
        parsed, usage, failure, detail = None, None, "call_error", "exception"

    if parsed is None:
        budget.settle(call_id, verdict="filed_nothing", usage=usage)
        why = call_failed_reason(failure or "no_output", detail=detail)
        return CardResult(
            "refused_invalid",
            store("refused_invalid", reason=why, agent_call_id=call_id),
            why, usage, call_id,
        )

    if parsed.skip:
        why = parsed.reason.strip() or "the scout skipped this game without saying why"
        if skip_is_search_failure(parsed.reason, usage):
            # A machine failure, not the scout's judgement (#309). Stored as
            # `refused_invalid`, which the watcher and the tap both retry;
            # `skipped` is a done status and would end the game's chances.
            budget.settle(call_id, verdict="search_failed", usage=usage)
            why = call_failed_reason("search_failed", detail=why)
            return CardResult(
                "refused_invalid",
                store("refused_invalid", reason=why, agent_call_id=call_id),
                why, usage, call_id,
            )
        budget.settle(call_id, verdict="skip", usage=usage)
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
        parsed.model_copy(update={"legs": [CardLeg(**leg) for leg in kept]}), listing,
        kickoff_ms=kickoff_ms,
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
            legs=[freeze_leg_at_build(leg.model_dump(), listing) for leg in parsed.legs],
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


# --- the T-2h drop-if re-check (#289, Joe's (A) to #270) ---------------------

RECHECK_AGENT_NAME = "game_script_recheck"
RECHECK_PROMPT_VERSION = "2"
RECHECK_MAX_SEARCHES = 1
#: A re-check that answers `unknown` is asked once more (Joe, 2026-10-03).
RECHECK_ATTEMPTS = 2
RECHECK_SEARCH_TOOL = {**WEB_SEARCH_TOOL, "max_uses": RECHECK_MAX_SEARCHES}

RECHECK_SYSTEM = """\
You are re-checking one condition for a betting research desk, about two \
hours before a game. Earlier today the desk wrote a card for this game and \
said Joe should drop it if a specific thing happened. Do ONE search for \
today's news on exactly that thing, and report what you found.

Set status to "triggered" ONLY if a page you found says the thing happened, \
and give that page's address and published date in source. Set status to \
"not_found" if your one search did not find it. Set status to "unknown" if \
the news is unclear, conflicting, or you could not search. "not_found" is \
not a confirmation that the card is right; it only means one search did not \
find the drop-if news.

""" + search_cap_rule(RECHECK_MAX_SEARCHES) + """

In note, say in one or two plain sentences what you found. Never estimate a \
probability, price or edge, and never say whether to bet."""


class RecheckOutput(BaseModel):
    """The re-check's answer. No field carries a probability, confidence or
    edge, and `tests/test_game_script_recheck.py` walks the schema."""

    status: Literal["triggered", "not_found", "unknown"] = Field(
        default="unknown",
        description="triggered only with a dated source; not_found if one "
        "search did not find it; unknown otherwise.",
    )
    note: str = Field(default="", description="One or two plain sentences.")
    source: Optional[CardSource] = Field(
        default=None, description="The page that says it happened, with its date."
    )


def recheck_prompt(*, game_title: str, kickoff_iso: str, drop_if: str) -> str:
    return "\n".join([
        f"Game: {game_title}.",
        f"Kickoff: {kickoff_iso}.",
        f"Drop the card if: {drop_if}",
    ])


def settle_recheck(parsed: Optional[RecheckOutput]) -> tuple[str, Optional[str], Optional[dict]]:
    """`(status, note, source)` as stored. A `triggered` with no web-address
    source is downgraded to `unknown`: the claim that the drop-if happened is
    the one that would change Joe's mind, so it is the one that needs a page.
    Nothing the model returns becomes `not_found` by default."""
    if parsed is None:
        return "unknown", "The re-check returned nothing.", None
    note = parsed.note.strip() or None
    source = parsed.source
    has_source = source is not None and source.url.strip().startswith(("http://", "https://"))
    if parsed.status == "triggered" and not has_source:
        return "unknown", note, None
    return parsed.status, note, (source.model_dump() if has_source else None)


async def recheck_card(
    conn: sqlite3.Connection,
    client,
    config: AgentConfig,
    budget: AgentBudget,
    *,
    card: dict,
    game_title: str,
    kickoff_iso: str,
    now_ms: int,
) -> str:
    """Up to `RECHECK_ATTEMPTS` metered calls with one search each, or a budget
    refusal that spends nothing. Always stamps the card once; returns the
    stored status.

    **One retry, on `unknown` only (Joe, 2026-10-03).** On 2026-10-02 a
    re-check came back `unknown` because the search tool errored, and the
    card carried "could not tell" into the game. A second attempt is one
    more call and one more search inside the same ceilings; if it is also
    `unknown`, the note says it was tried twice. `triggered` and `not_found`
    are answers and are never re-asked -- re-asking until the answer changes
    would be shopping for one.
    """
    status, note, source = "unknown", None, None
    for attempt in range(1, RECHECK_ATTEMPTS + 1):
        reason = budget.refusal_reason(1, now_ms, searches_worst_case=RECHECK_MAX_SEARCHES)
        if reason is not None:
            if attempt == 1:
                game_script_cards.record_recheck(
                    conn, card["id"], recheck_ms=now_ms, status="refused_budget",
                    note=reason,
                )
                return "refused_budget"
            break
        call_id = budget.reserve(
            called_ms=now_ms, agent=RECHECK_AGENT_NAME, model=config.model,
            ticker=card["game_event_ticker"], side=None,
        )
        try:
            outcome = await structured_call(
                client,
                model=config.model,
                system=RECHECK_SYSTEM,
                user_content=recheck_prompt(
                    game_title=game_title, kickoff_iso=kickoff_iso,
                    drop_if=card.get("drop_if") or "",
                ),
                output_model=RecheckOutput,
                max_tokens=1000,
                effort="low",
                tools=[RECHECK_SEARCH_TOOL],
            )
            parsed, usage = outcome.parsed, outcome.usage
        except Exception:
            logger.exception("the drop-if re-check died")
            parsed, usage = None, None
        status, note, source = settle_recheck(parsed)
        budget.settle(call_id, verdict=status, usage=usage)
        if status != "unknown":
            break
    if status == "unknown" and attempt > 1:
        note = f"Tried twice. {note}" if note else "Tried twice; neither attempt could tell."
    game_script_cards.record_recheck(
        conn, card["id"], recheck_ms=now_ms, status=status, note=note, source=source
    )
    return status

