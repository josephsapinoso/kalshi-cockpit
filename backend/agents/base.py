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

# **The count cap is the safety claim, and it holds whatever a call costs.**
# 24 calls a day is 24 HTTP requests a day (see `build_client`: `max_retries=0`
# makes that an identity, not an estimate). Everything below converts that count
# into dollars, and the conversion rests on a rate this repo cannot verify.
#
# Token counts per Skeptic call, ~1,730 input:
#
#   401   HOUSE_CONTEXT              measured (`scripts/measure_agent_cache_prefix.py`)
#   ~584  skeptic.SYSTEM             measured, same script (house+skeptic = 985)
#   ~330  the user prompt            estimated from `skeptic.build_prompt`
#   ~415  the `SkepticVerdict` schema  sent as `output_format`, BILLED AS INPUT
#
# and up to 3,000 output, because `skeptic.evaluate` sets `max_tokens=3000` and
# `thinking: {"type": "adaptive"}` (see `structured_call`) bills thinking tokens
# as output. So use the ceiling, not a midpoint: an adaptive-thinking call can
# spend the whole budget.
#
#   **[ASSUMED, uncited] claude-opus-5 list price = $5 / $25 per million.**
#   Nothing in this repo cites that rate. It is not on an invoice, not in a
#   fixture, and not read from any API. It matches the cached model table in the
#   `claude-api` skill (cached 2026-06-24), which is corroboration and not a
#   citation: a future session may not have that skill, and a cached table is
#   not a bill. Treat every dollar figure below as conditional on it.
#
# On that assumption, and only on it:
#
#   ceiling  1,730 x $5/M + 3,000 x $25/M  = $0.084 a call
#   floor    1,730 x $5/M +  ~200 x $25/M  = $0.014 a call  (a terse verdict,
#                                            little thinking -- not measured)
#   -> a saturated day of 24 calls is **$0.35 to $2.01**, so ~$10-$60 a month.
#
# The old figure in this block was ~$0.045 a call and ~$1.10 a day. It was wrong
# twice over: it used ~1,400 input (no schema) and ~1,500 output (half the real
# `max_tokens`), and it counted one HTTP request per candidate while the SDK's
# `DEFAULT_MAX_RETRIES = 2` allowed three -- up to $0.25 a call and ~$6.05 a
# day. `max_retries=0` closed the second gap; this block closes the first.
#
# **These will bind the first time this project succeeds, and that is intended.**
# If the `stale_odds` question resolves the way it might, a pass could surface
# ~23 rows; 15 of them would come back refused rather than reviewed. That is the
# right direction for a first ceiling on a path that had none: the alternative
# is discovering the correct number from an invoice. Raising it is one line in
# `fly.live.toml` and a deploy, taken deliberately after the first real bill.
#
# What each cap does -- they are not two spend ceilings. See `budget.py`:
# `allowance = max(0, min(per_pass, remaining_today))` puts both in one `min()`,
# so the **day** is the money control (24 calls, whatever `per_pass` is) and the
# **pass** cap controls fan-out width and how the day's 24 are spread over the
# day's passes.
DEFAULT_MAX_CALLS_PER_PASS = 8
DEFAULT_MAX_CALLS_PER_DAY = 24

# **The token and search caps see what the call cap cannot** (2026-08-21,
# betting-desk item 6). A scout-desk staff call carries the web-search tool
# with `max_uses: 6`, and each search bills per-search AND injects its results
# as input tokens -- so one metered "call" can be a small fixed spend or a
# large one, and the 24-call cap cannot tell them apart. These two are brakes
# evaluated over *recorded* usage (`agent_calls.input_tokens` etc.) BEFORE the
# next reserve -- never over a post-hoc field of the work the money bought
# (`tasks/lessons.md`, "a field written after the spend is not a spend gate").
#
# The defaults are chosen to bind early and be raised deliberately, like the
# call caps above. Arithmetic, on the same [ASSUMED] rates and the desk's own
# ceilings (staff `max_tokens=6000`, up to 6 searches each; master 4000):
#
#   one saturated convening  ~2 x (50K in + 6K out) + (5K in + 4K out)  ~ 121K
#   tokens: 500K a day  ~ 4 saturated convenings, more when calls run lean
#   searches: 60 a day  ~ 5 convenings that spend all 12, more when fewer
#
# The call cap alone would allow 8 convenings x 12 searches = 96 searches and
# an unbounded token day. A crashed call settles no usage (NULL, never 0), so
# these sums can under-count -- the call cap, which needs no response to
# enforce, remains the outer bound, and `calls_unmetered_today` reports how
# many rows the sums do not cover.
DEFAULT_MAX_SEARCHES_PER_DAY = 60
DEFAULT_MAX_TOKENS_PER_DAY = 500_000

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
class CallUsage:
    """What one billed call consumed, from the API's own usage block.

    `input_tokens` is the whole presented prompt -- uncached plus cache read
    plus cache write -- because this is a token meter, not a dollar meter:
    the three classes bill at different rates and summing them does not
    pretend otherwise (`AgentSpendSummary` has the counts-not-dollars rule).
    `web_searches` is the server-tool count the API reports; those bill
    per-search on top of tokens.
    """

    input_tokens: int
    output_tokens: int
    web_searches: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class StructuredCallOutcome:
    """One call's parsed result and its recorded cost, separately nullable.

    The two halves fail independently and the meter needs the difference:
    a safety refusal or unparseable output has `parsed=None` with real
    `usage` -- the call was billed and must be counted -- while a transport
    death has `usage=None`, which settles NULL usage columns ("unreadable
    resolves to None, never 0") and is counted by `calls_unmetered_today`.
    """

    parsed: Optional[Any]
    usage: Optional[CallUsage]


def _usage_from(response) -> Optional[CallUsage]:
    """Read the usage block off a response, or None when there is none.

    `server_tool_use` absent means no server tool ran, so 0 searches is an
    observation there, not a substitution; a missing `usage` object entirely
    is the unreadable case and resolves to None.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    server = getattr(usage, "server_tool_use", None)
    searches = getattr(server, "web_search_requests", 0) if server is not None else 0
    return CallUsage(
        input_tokens=(
            int(getattr(usage, "input_tokens", 0) or 0)
            + int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
            + int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        ),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        web_searches=int(searches or 0),
    )


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
    max_searches_per_day: int = DEFAULT_MAX_SEARCHES_PER_DAY
    max_tokens_per_day: int = DEFAULT_MAX_TOKENS_PER_DAY

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
            max_searches_per_day=_positive_int_env(
                "AGENT_MAX_SEARCHES_PER_DAY", DEFAULT_MAX_SEARCHES_PER_DAY
            ),
            max_tokens_per_day=_positive_int_env(
                "AGENT_MAX_TOKENS_PER_DAY", DEFAULT_MAX_TOKENS_PER_DAY
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
break-even win rate from 52.38% to about 51.75%. That is the entire edge the \
venue offers, and it is a DISCOUNT rather than a signal: a cheaper venue \
multiplies an edge, it cannot create one. This tool measured every place it \
could reach for an edge to multiply and found none (beta = -0.141), so treat \
any apparent opportunity as a defect to explain rather than a find.

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
    """Construct the Anthropic client. Imported lazily so the SDK is optional.

    **`max_retries=0`, so one candidate is exactly one HTTP request.**

    The installed SDK (`anthropic` 0.120.2) defaults to `DEFAULT_MAX_RETRIES =
    2` and retries 408/409/429/>=500 and connection errors. `structured_call`
    collapses every attempt into one return value, and `AgentBudget` records
    once per candidate -- so under the default the 24/day ceiling permitted up
    to **72 billed requests** and the meter could not see the other 48. The cap
    was a cap on candidates wearing a cap on spend's name.

    **The choice was between `0` and `1`, and it is a real trade.** A retry that
    is not made is a row that goes unreviewed: `structured_call` returns `None`,
    `apply_verdict` treats that as "no opinion", and the row reaches the card
    with only the deterministic checks behind it. `max_retries=1` would buy that
    row back at the cost of exactness -- one candidate would be one *or* two
    requests, and the day's true bill would be somewhere in 24-48 with nothing
    able to say where.

    `0` wins because **the retry already exists one level up, where it is
    metered.** `run_loop` re-prices the same slate every `RUNNER_INTERVAL_S`; a
    row lost to a 429 is re-surfaced and re-attacked on the next pass, at a cost
    of one call that `agent_calls` records. An SDK-level retry is an unmetered
    duplicate of a metered mechanism, and this repo's rule is that the
    unreadable resolves to a refusal rather than to a silent substitution.

    So the relationship is stated and exact, not assumed:

        1 candidate == 1 `messages.parse` == 1 HTTP request
        AGENT_MAX_CALLS_PER_DAY == the day's HTTP request ceiling

    `tests/test_agent_budget.py::TestOneCandidateIsExactlyOneRequest` pins it
    with a stub that *would* retry if the client let it.
    """
    import anthropic

    return anthropic.AsyncAnthropic(api_key=config.api_key, max_retries=0)


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
) -> StructuredCallOutcome:
    """One structured call. Returns the parsed model and the recorded usage.

    `parsed` is None rather than raised on failure, deliberately: an agent is
    advisory, and a Claude outage must not take down a recommendation
    pipeline. Callers treat a None verdict as "no opinion", which for the
    Skeptic means the suppression layer's own deterministic checks stand alone
    — as they always do anyway. `usage` is carried even when `parsed` is None
    (a refusal or unparseable output was still billed) and is None only when
    no response arrived at all — the caller settles that as NULL, never 0.

    **The cache breakpoint is on the last system block, not the shared one.**
    The shared house context is 401 tokens and the minimum cacheable prefix is
    512, so a breakpoint after it cached nothing at all — silently, which is
    the only way a cache can fail. On the last block the cached prefix is
    738–985 tokens depending on the agent, which is over the line.

    The cost is one cache entry per agent instead of one shared across three.

    **That cost is not recovered within a pass, and the earlier claim here that
    "an agent runs many times in a row on a slate" was false for the deployed
    shape.** `review._review_batch` puts every candidate in flight at once under
    `asyncio.gather`, so no call in a batch can read a prefix another call in
    the same batch has not finished writing — all of them pay the 1.25x
    cache-*write* premium. The reuse is *across* passes, not within one: the
    entry a pass writes is read by the next pass that surfaces a row, if that
    happens inside the 5-minute ephemeral TTL. On a `RUNNER_INTERVAL_S` of 900
    it usually will not.

    In dollars this is small -- 985 cached tokens at the 0.25x premium is a
    fraction of a cent a call against a ~$0.084 ceiling. It is corrected because
    a false stated rationale is how the next reader justifies the next thing.

    **On the deployed model since 2026-08-24, this breakpoint caches nothing,
    and that is expected rather than broken.** ADR 0071 section 2.7 moved live
    to `claude-sonnet-5`, whose minimum cacheable prefix is **1024 tokens**
    against Claude Opus 5's 512 (`scripts/measure_agent_cache_prefix.py:47-50`).
    Every prefix measured on 2026-08-08 -- 985 skeptic, 876 historian, 738
    scout -- clears 512 and none clears 1024. So `cache_creation_input_tokens`
    and `cache_read_input_tokens` are now **0 on every live call**, silently,
    exactly as the comment above HOUSE_CONTEXT warns a too-short prefix always
    fails.

    Do not "fix" this by padding the prompt. The trade was made knowingly: a
    Sonnet call is cheaper uncached than an Opus call cached, and the caching
    was already documented above as worth a fraction of a cent against a
    ~$0.084 ceiling, recovered across passes rather than within one. Growing a
    system prompt past 1024 tokens to win back a fraction of a cent would cost
    more in input tokens than it saves.

    **Not measured: the scout-desk and pro-bettor seats.** The 2026-08-08 table
    covers skeptic, scout and historian. The four seats that actually spend
    money on live today (`agents/scout_desk.py`, `agents/pro_bettor.py`) have
    never had their prefixes counted, so whether any of them clears 1024 is
    unknown. `scripts/measure_agent_cache_prefix.py` answers it for free --
    `count_tokens` is not billed -- and nobody has run it since the seats were
    built.
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
        return StructuredCallOutcome(parsed=None, usage=None)

    usage = _usage_from(response)

    # A safety refusal returns HTTP 200 with stop_reason "refusal" and content
    # that will not match the schema. Check before touching parsed_output.
    if getattr(response, "stop_reason", None) == "refusal":
        logger.warning(
            "agent call refused (%s)",
            getattr(getattr(response, "stop_details", None), "category", "unknown"),
        )
        return StructuredCallOutcome(parsed=None, usage=usage)

    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        logger.warning("agent returned no parseable structured output")
    return StructuredCallOutcome(parsed=parsed, usage=usage)
