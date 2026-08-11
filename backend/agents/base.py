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

from ..config import ConfigError

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5"

# Conservative on purpose, and neither number is measured -- the population they
# would be measured on has never existed, because `surfaced` has been 0 on every
# live pass. The arithmetic they *are* derived from:
#
#   one Skeptic call ~= 1,400 input + ~1,500 output tokens
#   claude-opus-5 list price = $5 / $25 per million
#   -> ~$0.045 a call, so 8 a pass is ~$0.36 and 24 a day is ~$1.10 (~$33/month)
#
# 8 per pass bounds one `asyncio.gather`; 24 a day is three saturated passes, on
# a loop that wakes up to 96 times. The daily cap is the one that actually binds
# the bill -- 96 x 8 would be 768 calls, ~$35 a day.
#
# **These will bind the first time this project succeeds, and that is intended.**
# If the `stale_odds` question resolves the way it might, a pass could surface
# ~23 rows; 15 of them would come back refused rather than reviewed. That is the
# right direction for a first ceiling on a path that had none: the alternative
# is discovering the correct number from an invoice. Raising it is one line in
# `fly.live.toml` and a deploy, taken deliberately after the first real bill.
DEFAULT_MAX_CALLS_PER_PASS = 8
DEFAULT_MAX_CALLS_PER_DAY = 24

T = TypeVar("T", bound=BaseModel)


def _positive_int_env(key: str, default: int) -> int:
    """Parse a ceiling from the environment. Malformed raises; it never defaults.

    `backend/config.py`'s rule, applied here because these are risk caps and not
    preferences: *a silently-defaulted cap is how you discover your exposure
    limit was 0 or unset at the worst possible moment*. A typo in
    `AGENT_MAX_CALLS_PER_DAY` must not resolve to "the generous default".

    Zero is accepted and means "make no calls" -- a legitimate way to hold the
    fleet at zero spend without unsetting the key. Negative is not, because it
    is not a quantity anything can mean.
    """
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key}={raw!r} is not an integer.") from exc
    if value < 0:
        raise ConfigError(f"{key}={value} must be zero or more.")
    return value


class AgentUnavailable(RuntimeError):
    """No API key configured. Agents are optional; the pipeline is not."""


@dataclass(frozen=True)
class AgentConfig:
    api_key: str
    model: str = DEFAULT_MODEL
    # The spend ceilings. They live here, beside the key and the model, because
    # this is already the fleet's one env-reading site -- and because a config
    # object that carries "which model to bill" and not "how much of it" is the
    # shape that let the spend path ship with no ceiling at all.
    max_calls_per_pass: int = DEFAULT_MAX_CALLS_PER_PASS
    max_calls_per_day: int = DEFAULT_MAX_CALLS_PER_DAY

    @classmethod
    def from_env(cls) -> Optional["AgentConfig"]:
        """None when unconfigured, rather than raising.

        The fleet is decision support. A missing key must degrade the tool to
        "no agent commentary", never stop the ingest loop that is recording the
        evidence the whole project depends on.

        **A malformed ceiling is the one thing here that does raise**, and the
        asymmetry is deliberate. An absent key means "no agents", which costs
        nothing; an unreadable cap means "we do not know what the limit is", and
        the only safe reading of that on a metered path is to stop. The blast
        radius is bounded to instances that have the key set at all.
        """
        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not key:
            return None
        return cls(
            api_key=key,
            model=os.getenv("AGENT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
            max_calls_per_pass=_positive_int_env(
                "AGENT_MAX_CALLS_PER_PASS", DEFAULT_MAX_CALLS_PER_PASS
            ),
            max_calls_per_day=_positive_int_env(
                "AGENT_MAX_CALLS_PER_DAY", DEFAULT_MAX_CALLS_PER_DAY
            ),
        )


# Shared across all three agents. Kept byte-stable, because a change here
# invalidates the cached prefix for every agent.
#
# **It is not the cache breakpoint, and putting one here cached nothing.**
# Measured 2026-08-08 with `messages.count_tokens` against `claude-opus-5`
# (`scripts/measure_agent_cache_prefix.py`):
#
#     HOUSE_CONTEXT alone        401 tokens
#     house + skeptic system     985
#     house + scout system       738
#     house + historian system   876
#     minimum cacheable prefix   512     <- Claude Opus 5
#
# A prefix under the minimum does not cache and does not complain: no error,
# no warning, `cache_creation_input_tokens: 0`. The breakpoint sat on this
# block behind a comment calling the savings "the whole reason to cache", and
# there were none. See `structured_call` for where it went instead.
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

    **The cache breakpoint is on the last system block, not the shared one.**
    The shared house context is 401 tokens and the minimum cacheable prefix is
    512, so a breakpoint after it cached nothing at all — silently, which is
    the only way a cache can fail. On the last block the cached prefix is
    738–985 tokens depending on the agent, which is over the line.

    The cost is one cache entry per agent instead of one shared across three.
    That is a real loss and it is smaller than it looks: an agent runs many
    times in a row on a slate, so the reuse that matters is an agent against
    itself — and the alternative on offer was no cache at all.
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": [
            {"type": "text", "text": HOUSE_CONTEXT},
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            },
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
