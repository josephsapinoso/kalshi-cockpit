"""Shared plumbing for the agent fleet.

The fleet mirrors Billy Walters' team, with one hard split that keeps it honest:

**Anything producing a number is deterministic code. LLM agents do research,
triage, and learning.**

That split is not stylistic. An agent asked to estimate a win probability will
lose to a market of professionals, confidently and unfalsifiably. So no agent
in this package returns a probability, a price, or a stake — those come from
`core/devig.py`, `core/ev.py`, `core/sizing.py` and `model/elo.py`, all of
which can be backtested. Agents return *judgements about data quality* and
*structured research*, which is work they are genuinely good at and which no
amount of arithmetic can do.

Three agents:

- **Skeptic** — argues a flagged edge is a bug. Rejection is the default.
- **Scout** — gathers injury, weather, lineup and travel context. Cites sources.
  Never outputs a probability.
- **Historian** — weekly post-mortem; may propose config changes, but only
  behind the same noise guard as any other finding.

All three use structured outputs, so a verdict is a validated object rather
than prose that has to be parsed. Prose is where an agent's hedging leaks into
a decision.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5"

T = TypeVar("T", bound=BaseModel)


class AgentUnavailable(RuntimeError):
    """No API key configured. Agents are optional; the pipeline is not."""


@dataclass(frozen=True)
class AgentConfig:
    api_key: str
    model: str = DEFAULT_MODEL

    @classmethod
    def from_env(cls) -> Optional["AgentConfig"]:
        """None when unconfigured, rather than raising.

        The fleet is decision support. A missing key must degrade the tool to
        "no agent commentary", never stop the ingest loop that is recording the
        evidence the whole project depends on.
        """
        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not key:
            return None
        return cls(api_key=key, model=os.getenv("AGENT_MODEL", DEFAULT_MODEL).strip()
                   or DEFAULT_MODEL)


# Shared across all three agents and marked for caching. Kept byte-stable: any
# change invalidates the cached prefix for every agent, and the savings on a
# repeated system prompt are the whole reason to cache.
HOUSE_CONTEXT = """\
You are part of a tool that prices Kalshi sports markets against devigged \
sportsbook consensus. Some context that governs how you should reason:

Kalshi's advantage over a sportsbook is COST, not information. Holding a \
contract to settlement pays one fee rather than a round trip, which lowers the \
break-even win rate from 52.38% to about 52.00%. That is the entire edge the \
venue offers.

Everything else is against the user. Kalshi prices sports to roughly 2 cents. \
An independent census found 13 automated market makers there, nearly all \
quoting under 200 milliseconds. Real edges on this venue are 2-3 cents. A 6 \
cent edge is not an opportunity thirteen professional firms overlooked; it is \
almost always a stale quote, a mis-joined fixture, or a market that means \
something other than what the tool assumed.

The spread between devig methods is 0.2 points on an even moneyline and 2 \
points on a longshot, so on lopsided lines method choice alone can manufacture \
an apparent edge larger than the real one.

Write plainly and briefly. State conclusions, not the reasoning that led to \
them, unless the reasoning is the point. Do not hedge with qualifiers when the \
structured fields already carry your confidence."""


def build_client(config: AgentConfig):
    """Construct the Anthropic client. Imported lazily so the SDK is optional."""
    import anthropic

    return anthropic.AsyncAnthropic(api_key=config.api_key)


async def structured_call(
    client,
    *,
    model: str,
    system: str,
    user_content: Any,
    output_model: Type[T],
    max_tokens: int = 4096,
    effort: str = "medium",
    tools: Optional[list[dict]] = None,
) -> Optional[T]:
    """One structured call. Returns a validated model, or None on failure.

    Returning None rather than raising is deliberate: an agent is advisory, and
    a Claude outage must not take down a recommendation pipeline. Callers treat
    a None verdict as "no opinion", which for the Skeptic means the suppression
    layer's own deterministic checks stand alone — as they always do anyway.

    The system prompt is sent as two blocks with a cache breakpoint after the
    shared house context, so the per-agent half can change without invalidating
    the common prefix.
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": [
            {
                "type": "text",
                "text": HOUSE_CONTEXT,
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": system},
        ],
        "messages": [{"role": "user", "content": user_content}],
        "output_format": output_model,
        # Adaptive thinking is on by default on this model; stated explicitly
        # so the intent survives a model change.
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": effort},
    }
    if tools:
        kwargs["tools"] = tools

    try:
        response = await client.messages.parse(**kwargs)
    except Exception:
        logger.exception("agent call failed; continuing without a verdict")
        return None

    # A safety refusal returns HTTP 200 with stop_reason "refusal" and content
    # that will not match the schema. Check before touching parsed_output.
    if getattr(response, "stop_reason", None) == "refusal":
        logger.warning(
            "agent call refused (%s)",
            getattr(getattr(response, "stop_details", None), "category", "unknown"),
        )
        return None

    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        logger.warning("agent returned no parseable structured output")
    return parsed
