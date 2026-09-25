"""The leg-verdict seat: TAKE or PASS on one parlay leg, before Joe buys (ADR 0186).

Joe's decision, 2026-09-25 (#151): point the scouts at the legs of a card he
is about to buy and have them say whether they would make that bet, in plain
words. His "safe" and "middle" parlays had been losing, and the question is
whether a scout read would have been a useful second check between picking a
card and paying for it.

**This seat is the one exception to ADR 0060's no-verdict rule, and only this
seat.** The four desk seats (`scout.SYSTEM`, the staff pair, the master and
`pro_bettor.SYSTEM`) keep the no-forecast rule word for word, and
`tests/test_desk_prompts_share_the_no_forecast_rule.py` still pins it there.
It also pins that this seat does not carry the rule, so the exception stays a
decision instead of drift.

What the seat may say: `take` or `pass`, plus a reason of one or two everyday
sentences. What it may not say is still a number. `LegVerdict` has no numeric
field anywhere (walked by test), and the prompt forbids a probability, a fair
price, a line and a stake. The verdict is scored forward against the leg's
settlement (`docs/measurements/2026-09-25-preregistration-scout-leg-verdicts.md`),
so it has to be falsifiable, and it is: an enum plus a price recorded
server-side.

**What TAKE and PASS mean is fixed here, so the scoring has one meaning to
test.** PASS means the seat found a specific, current reason to avoid this
side at this price: a scratch, an injury, weather, rest or travel, or a line
that has not caught up with the news. TAKE means it found no such reason.
TAKE is therefore the absence of a named objection, not a claim that the bet
wins, and the prompt says so to the model.

**The house context leans toward PASS.** `structured_call` always sends
`HOUSE_CONTEXT` first, and that block says to treat any apparent opportunity
as a defect. Fixing PASS to a *named* reason is the counterweight: a PASS
with no concrete fact behind it is off-spec. The pre-registration records
the lean as a known bias of the instrument.

Joe is a beginner (`PLAIN_WORDS_RULE`). The reason is capped at
`REASON_MAX_CHARS`. The cap is checked after parsing, not on the pydantic
field, because a field-level `max_length` would raise inside
`messages.parse`, and that branch loses the call's usage. An over-length
reason is recorded as failed, not clipped: cutting it would change what the
model said.

Money contract, the same as every desk seat: `can_afford` before anything,
`reserve` before the request, and `settle` whatever happens. One verdict is
exactly one metered call with at most `LEG_VERDICT_MAX_SEARCHES` searches.

What this module does not establish: that a verdict is any good. That is the
pre-registered measurement's job, and until it declares, a verdict is an
opinion shown beside the buy button, never a gate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .base import AgentConfig, CallUsage, structured_call
from .budget import AgentBudget
from .scout import WEB_SEARCH_TOOL

logger = logging.getLogger(__name__)

#: One verdict searches at most this many times. A full desk convening
#: searches up to 12 (two staff scouts at 6) and measured ~170K tokens on day
#: one; this seat is meant to cost a small fraction of that.
LEG_VERDICT_MAX_SEARCHES = 3
LEG_VERDICT_SEARCH_TOOL = {**WEB_SEARCH_TOOL, "max_uses": LEG_VERDICT_MAX_SEARCHES}

#: The reason's hard cap, checked after parsing (see the module docstring).
REASON_MAX_CHARS = 220

AGENT_NAME = "leg_verdict"

PLAIN_WORDS_RULE = (
    "Joe, who reads this, is a beginner, not a professional bettor. Write the "
    "reason as one or two short sentences in everyday words, under 200 "
    "characters. Do not use betting jargon -- CLV, devig, steam, sharp money, "
    "juice, handle, vig, chalk -- unless you explain it in the same sentence. "
    "Say what you found, not how you reasoned. Example: \"Their starting "
    "pitcher was scratched this morning, and this price hasn't moved since.\""
)

SYSTEM = f"""\
You are the leg scout at a betting research desk. Joe is about to buy a \
parlay (several bets joined into one ticket that pays only if every leg \
wins), and you are looking at ONE leg of it: one side of one market on one \
game, at the price Kalshi is asking right now.

Your job is one word and a reason: TAKE or PASS.

- PASS means you found a specific, current reason to avoid THIS side at THIS \
price: a starter scratched or doubtful, an injury, weather that affects play, \
a hard travel or rest spot, a lineup change, or news the price does not seem \
to have caught up with. Name the fact.
- TAKE means you looked and found no such reason. It does not mean the bet \
will win; it means nothing you found argues against it. Do not say PASS \
merely because betting is hard or prices are efficient -- that is true of \
every leg and tells Joe nothing. A PASS must name a concrete fact.

Search for recent news on this game and these teams or players. Recency \
matters: news from this morning may not be in the price, news from three days \
ago almost always is. If a desk briefing on the game is included, use it, and \
check whether anything has changed since.

Two hard rules.

Never state a probability, a fair price, a line, a point spread, or how much \
to stake. Your answer is TAKE or PASS and words, nothing more.

{PLAIN_WORDS_RULE}"""


class LegVerdict(BaseModel):
    """TAKE or PASS and a plain reason. No field can carry a number.

    Every leaf is a string or an enum of strings, deliberately:
    `tests/test_leg_verdict_seat.py` walks the JSON schema and fails if a
    numeric type appears anywhere.
    """

    verdict: Literal["take", "pass"] = Field(
        description="take: you found no specific reason to avoid this side at "
        "this price. pass: you found one, and the reason names it."
    )
    reason: str = Field(
        description="One or two short sentences in everyday words, under 200 "
        "characters, no jargon, no numbers for probability, price or stake. "
        "For pass: the concrete fact. For take: what you checked and found "
        "nothing against."
    )


@dataclass(frozen=True)
class LegVerdictResult:
    """One seat run. `verdict` is set only on `complete`.

    `status`:
      complete  -- a verdict within the length cap
      failed    -- the call died, returned nothing parseable, or overran the cap
      refused   -- a ceiling said no; nothing was reserved and nothing spent
    """

    status: Literal["complete", "failed", "refused"]
    verdict: Optional[LegVerdict]
    usage: Optional[CallUsage]
    refusal_reason: Optional[str]
    agent_call_id: Optional[int]


def build_prompt(
    *,
    label: str,
    side: str,
    ask_display: str,
    event_title: str,
    league: str,
    commence_iso: Optional[str],
    briefing_text: Optional[str],
) -> str:
    """The user turn. It carries the leg, the side, Kalshi's ask as words, and
    kickoff. It deliberately omits the tool's own fair percentage: the verdict is
    scored against the price, so it must not be built from our model of it."""
    parts = [
        f"Game: {event_title} ({league}).",
        f"Kickoff: {commence_iso or 'unknown'}.",
        f"The leg: {label}.",
        f"Joe would be buying {side.upper()} on it. {ask_display}.",
    ]
    if briefing_text:
        parts.append(
            "The desk's earlier briefing on this game (check whether anything "
            "has changed since):\n" + briefing_text
        )
    else:
        parts.append("The desk has no briefing on this game; search yourself.")
    parts.append("TAKE or PASS on this leg, with the reason.")
    return "\n".join(parts)


async def give_leg_verdict(
    client,
    config: AgentConfig,
    budget: AgentBudget,
    *,
    ticker: str,
    side: str,
    prompt: str,
    now_ms: int,
) -> LegVerdictResult:
    """One metered call, or a refusal that spends nothing."""
    reason = budget.refusal_reason(
        1, now_ms, searches_worst_case=LEG_VERDICT_MAX_SEARCHES
    )
    if reason is not None:
        logger.warning("the leg scout is refused: %s", reason)
        return LegVerdictResult("refused", None, None, reason, None)

    call_id = budget.reserve(
        called_ms=now_ms,
        agent=AGENT_NAME,
        model=config.model,
        ticker=ticker,
        side=side,
    )
    try:
        outcome = await structured_call(
            client,
            model=config.model,
            system=SYSTEM,
            user_content=prompt,
            output_model=LegVerdict,
            max_tokens=2000,
            effort="medium",
            tools=[LEG_VERDICT_SEARCH_TOOL],
        )
        parsed, usage = outcome.parsed, outcome.usage
    except Exception:
        logger.exception("the leg scout died")
        parsed, usage = None, None

    if parsed is not None and len(parsed.reason) > REASON_MAX_CHARS:
        logger.warning(
            "leg verdict reason over the %d-character cap (%d); recorded failed",
            REASON_MAX_CHARS,
            len(parsed.reason),
        )
        budget.settle(call_id, verdict="over_length", usage=usage)
        return LegVerdictResult(
            "failed", None, usage, "reason over length cap", call_id
        )

    budget.settle(
        call_id,
        verdict=parsed.verdict if parsed is not None else "filed_nothing",
        usage=usage,
    )
    if parsed is None:
        return LegVerdictResult("failed", None, usage, "the call returned nothing", call_id)
    return LegVerdictResult("complete", parsed, usage, None, call_id)
