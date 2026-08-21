"""The Skeptic — argues that a flagged edge is a bug.

This is the safety layer, and its design is adversarial on purpose. Given an
opportunity that cleared every deterministic check, the Skeptic's job is to
find the reason it is wrong. **Rejection is the default verdict**, and the
prompt says so explicitly, because an agent asked to "evaluate" an opportunity
will find something agreeable to say about most of them.

Why an agent at all, when `core/suppression.py` already runs seven checks?
Because those checks are the failure modes we *thought of*. They test freshness,
depth, market width, and edge size — all things expressible as a number. What
they cannot test is whether the two prices being compared are answering the
same question: whether the Kalshi market is "winner including overtime" while
the sportsbook line is regulation-only, whether a starting pitcher was scratched
an hour ago, whether the alias table quietly matched a reserve-team fixture to
a first-team one. Those are reading problems, and reading is what an agent is
for.

**It cannot approve anything.** A verdict of `plausible` means the Skeptic
failed to find a defect, not that the edge is real. The deterministic checks
still stand, and the live gate still stands behind them.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .base import AgentConfig, StructuredCallOutcome, structured_call

logger = logging.getLogger(__name__)

SYSTEM = """\
You are the Skeptic. Your job is to find the defect in an apparent betting edge.

Assume the edge is an artifact until you have tried and failed to explain it \
away. That is not pessimism, it is base rates: on a venue priced to two cents \
by thirteen sub-second market makers, an unclaimed multi-cent edge is far more \
often a data problem than an opportunity.

Work through the ways this could be wrong:

1. MARKET MISMATCH. Do the Kalshi contract and the sportsbook line resolve on \
the same question? Watch for regulation-time versus including-overtime, \
first-innings versus full-game, series versus single game, and markets that \
settle on a different source.
2. FIXTURE MISMATCH. Same two teams, different game — doubleheaders, reserve \
or youth sides, neutral-site duplicates, postponed-and-replayed fixtures.
3. STALE INFORMATION. Would recent news explain the gap? A scratched starter, \
a late injury, weather, or a lineup announcement moves one venue before the \
other, and the venue that has not moved yet looks mispriced.
4. STRUCTURAL. Illiquid book, one-sided quoting, a market about to close, or \
a line that never gets taken.

Then give your verdict:

- "defect" — you identified a specific, concrete reason this is not a real \
edge. Name it.
- "suspicious" — something is off but you cannot pin it down. Say what \
bothers you.
- "plausible" — you tried the above and found nothing. This does NOT mean the \
edge is real; it means you failed to break it.

You cannot approve a bet. Nothing you say relaxes any other check. Be \
concrete: "the Kalshi market settles on regulation time, the book line \
includes overtime" is useful, "there may be differences between the markets" \
is not."""


class SkepticVerdict(BaseModel):
    """Structured verdict. Deliberately carries no probability or price."""

    verdict: Literal["defect", "suspicious", "plausible"] = Field(
        description="defect if you found a concrete reason this is not real; "
        "suspicious if something is off but unidentified; plausible if you "
        "tried to break it and could not."
    )
    primary_concern: str = Field(
        description="The single most likely reason this edge is not real, in "
        "one sentence. If verdict is plausible, state what you checked."
    )
    checks_performed: list[str] = Field(
        description="Each specific check you ran and what you concluded.",
        min_length=1,
    )
    recommended_action: Literal["reject", "investigate", "proceed_with_caution"] = (
        Field(description="What the tool should do. Never 'bet'.")
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Your confidence in the verdict itself, not in the bet.",
    )

    @property
    def blocks_bet(self) -> bool:
        """Whether this verdict should stop the recommendation surfacing."""
        return self.verdict in ("defect", "suspicious")


def build_prompt(
    *,
    ticker: str,
    market_title: str,
    outcome_name: str,
    event_title: str,
    kalshi_ask_cents: float,
    consensus_fair_cents: float,
    edge_cents: float,
    quote_age_s: float,
    odds_age_s: float,
    book_count: int,
    # `None` when fewer than two books contributed, so disagreement could not be
    # measured at all. Passed through as null rather than rounded to 0.0: zero
    # width is a legitimate reading (two books quoting identically) and the two
    # states must not share a representation on the way to the agent either.
    market_width_points: Optional[float],
    depth_at_ask: Optional[float],
    devig_methods: dict[str, float],
    commence_iso: Optional[str],
    matched_sportsbook_teams: Optional[list[str]] = None,
) -> str:
    """Everything the Skeptic needs to attack the edge, and nothing else.

    Deliberately excludes the suggested stake and the bankroll. Those would
    invite the agent to reason about whether the bet is *worth* it, which is
    sizing — a job for `core/sizing.py`, which can be tested.
    """
    payload = {
        "kalshi": {
            "ticker": ticker,
            "market_title": market_title,
            "event_title": event_title,
            "side_pays_on": outcome_name,
            "ask_cents": round(kalshi_ask_cents, 1),
            "quote_age_seconds": round(quote_age_s, 1),
            "depth_at_ask": depth_at_ask,
            "commence_time_utc": commence_iso,
        },
        "sportsbook_consensus": {
            "fair_cents": round(consensus_fair_cents, 1),
            "books_used": book_count,
            "market_width_points": (
                None if market_width_points is None else round(market_width_points, 2)
            ),
            "odds_age_seconds": round(odds_age_s, 1),
            "matched_teams": matched_sportsbook_teams,
            "devig_by_method_cents": {
                k: round(v * 100, 1) for k, v in devig_methods.items()
            },
        },
        "claimed_edge_cents": round(edge_cents, 1),
    }
    return (
        "Attack this apparent edge.\n\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```\n\n"
        "Note the devig methods are shown per method. If they disagree by more "
        "than the claimed edge, the edge is a statement about method choice "
        "rather than about the market — that alone is a defect."
    )


async def evaluate(
    client,
    config: AgentConfig,
    **prompt_kwargs: Any,
) -> StructuredCallOutcome:
    """Run the Skeptic on one candidate.

    `parsed` is None when unavailable or refused. A None verdict means "no
    opinion" — the deterministic suppression checks stand on their own, which
    they were always designed to do. `usage` rides alongside so the caller
    can settle what the call actually consumed (v17 token meter).
    """
    return await structured_call(
        client,
        model=config.model,
        system=SYSTEM,
        user_content=build_prompt(**prompt_kwargs),
        output_model=SkepticVerdict,
        # Enough headroom to work through four attack lines without the answer
        # being truncated mid-check.
        max_tokens=3000,
        effort="medium",
    )


def apply_verdict(
    verdict: Optional[SkepticVerdict], existing_reason: Optional[str]
) -> Optional[str]:
    """Fold a Skeptic verdict into a recommendation's suppression reason.

    The Skeptic can only ever *add* a reason. It cannot clear one — an agent
    that could un-suppress a candidate would be a way to argue past the
    deterministic checks, which is exactly what the checks are for.
    """
    if verdict is None or not verdict.blocks_bet:
        return existing_reason
    tag = f"skeptic_{verdict.verdict}"
    if not existing_reason:
        return tag
    return f"{existing_reason},{tag}"
