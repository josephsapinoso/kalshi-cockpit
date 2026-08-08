"""The seam between the pricing pass and the Skeptic.

`backend/agents/*` was the fourth module in this project to be complete, tested
and called by nothing -- ~40 green tests implying a safety layer that could not
block anything, because `skeptic.apply_verdict` had no caller. This is the
caller.

What this module does NOT establish
-----------------------------------
**That this has ever run on a row the tool found by itself.** The Skeptic is
deliberately run only on rows that would be *surfaced*, and `surfaced` has been
0 for the life of this project, on every live pass. So on the deployed instance
this path has never executed and the fleet has cost nothing.

The wiring itself *is* verified against the live API, which the design note for
this work assumed was impossible: `tests/test_agent_wiring.py` builds a slate
from the captured Kalshi and odds payloads with one number changed, that row
surfaces, and on the first real run the Skeptic blocked it for a concrete
reason no deterministic check could reach. So read the green suite as evidence
that the mechanism works given a surfaced row -- and not as evidence that a
surfaced row has ever existed outside a fixture.

Four decisions, each of which took a while to arrive at
------------------------------------------------------
**1. Only surfaced rows are reviewed.** A live pass builds ~100 rows and almost
all of them have no edge. Reviewing every candidate would spend real money to be
told "no" a hundred times a pass, at 96 passes a day. The population worth
attacking is the one the tool would actually act on: `suggested_contracts > 0`
with no suppression reason -- exactly `Recommendation.surfaced`.

**2. Review happens before persistence, not after.** `apply_verdict` folds into
`suppressed_reason`, and if the row is already on disk there is a window one
Anthropic round trip wide in which `POST /api/orders` would sell an unreviewed
row. The pricing pass therefore collects, reviews, applies verdicts, and only
then persists.

**3. The async boundary is here, and it is a thread rather than `asyncio.run`.**
`run_pricing_pass` is sync; `structured_call` is async. Making the pass async
would touch every caller and test, so the seam is the right place -- but a bare
`asyncio.run` is wrong in a way that no test would have caught: `run_once` and
`run_quote_pass` are `async def` and call the pass directly, so in production
this executes *inside a running event loop*, where `asyncio.run` raises. It
would have passed every sync test and died the first time a row surfaced on the
live instance. A dedicated thread with its own loop behaves the same either way.

**4. A Skeptic outage must not stop the pass.** `structured_call` already
returns `None` on failure and `apply_verdict` already treats `None` as "no
opinion", so most of this falls out -- but "most" is not "all": `evaluate`
builds its prompt *before* the API call, so a bad field raises before
`structured_call` can swallow anything, and one raised exception inside
`asyncio.gather` takes the whole batch with it. Every candidate is therefore
isolated, and the result is asserted rather than assumed. The alternative is a
slate that silently stops being recorded.

Cost note
---------
The client is constructed per batch, because each batch runs on its own event
loop and an `httpx.AsyncClient` cannot be shared across loops. That is ~500ms
(`tasks/lessons.md`), paid only on passes that surface something -- never on
the quote passes that make up the cadence.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from ..engine import Recommendation, with_added_suppression
from . import skeptic
from .base import AgentConfig, build_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReviewCandidate:
    """One judged row, plus the context the Skeptic needs to attack it.

    `prompt_kwargs` is the keyword set `skeptic.build_prompt` takes. Held as a
    mapping rather than re-declared field by field so this module does not
    become a second place the prompt's inputs are listed -- two lists of the
    same fourteen fields drift, and the drift is silent.
    """

    recommendation: Recommendation
    prompt_kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewOutcome:
    """What the review did, so a pass can report it rather than imply it."""

    recommendations: list[Recommendation]
    reviewed: int = 0
    blocked: int = 0


def _amend(candidate: ReviewCandidate, verdict) -> tuple[Recommendation, bool]:
    """Fold one verdict into one row. Returns the row and whether it blocked."""
    existing = candidate.recommendation.suppressed_reason
    reason = skeptic.apply_verdict(verdict, existing)
    if reason == existing:
        # No verdict, or a `plausible` one. Note that `plausible` explicitly
        # does not mean the edge is real -- it means the Skeptic tried to break
        # it and could not, which changes nothing about the row.
        return candidate.recommendation, False
    # The concern is a model-written sentence and usually ends in a full stop;
    # `with_added_suppression` adds its own. Two of them on a card read as a
    # typo, and this string goes to a phone.
    concern = (verdict.primary_concern or "").strip().rstrip(".")
    return (
        with_added_suppression(
            candidate.recommendation,
            reason=reason,
            problem=f"the Skeptic calls this {verdict.verdict}: {concern}",
        ),
        True,
    )


async def _evaluate_one(client, config: AgentConfig, candidate: ReviewCandidate):
    """One candidate, with its own failure boundary.

    `structured_call` already turns an API failure into `None`. This catches the
    rest -- a prompt that cannot be built, a client that cannot be reached --
    because a single raised exception inside `asyncio.gather` cancels the batch,
    and a cancelled batch means the pass raises and the slate goes unrecorded.
    """
    try:
        return await skeptic.evaluate(client, config, **candidate.prompt_kwargs)
    except Exception:
        logger.exception(
            "skeptic review failed for %s; continuing with no opinion",
            candidate.recommendation.ticker,
        )
        return None


async def _review_batch(
    candidates: Sequence[ReviewCandidate], config: AgentConfig, client_factory
) -> list[Any]:
    client = client_factory(config)
    try:
        return list(
            await asyncio.gather(
                *(_evaluate_one(client, config, c) for c in candidates)
            )
        )
    finally:
        closer = getattr(client, "close", None)
        if closer is not None:
            try:
                result = closer()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # pragma: no cover - closing is best effort
                logger.exception("closing the agent client failed")


def _run_off_loop(coroutine_factory: Callable[[], Any]) -> Any:
    """Run an async batch from sync code, in or out of a running loop.

    See decision 3 in the module docstring. This is not defensive style: the
    production callers of `run_pricing_pass` are coroutines, so the in-a-loop
    case is the *only* one that matters live, and it is the one `asyncio.run`
    refuses to serve.
    """
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coroutine_factory())).result()


def review_surfaced(
    candidates: Sequence[ReviewCandidate],
    *,
    config: Optional[AgentConfig] = None,
    client_factory=build_client,
) -> ReviewOutcome:
    """Attack every surfaced row, and fold the verdicts back in.

    Callers pass **only** rows they intend to surface -- filtering is the
    caller's job because the caller is what holds the un-surfaced rows, and
    passing them here would make the cheap path (no surfaced rows, no API key,
    no calls) depend on a check inside a module the runner would then always
    have to enter.

    Degrades to "no commentary" rather than failing when `ANTHROPIC_API_KEY` is
    unset: `AgentConfig.from_env()` returns `None` and every row comes back
    untouched. That is the state on any instance without the secret set,
    including every local run.
    """
    if not candidates:
        return ReviewOutcome(recommendations=[])

    resolved = config if config is not None else AgentConfig.from_env()
    if resolved is None:
        logger.info(
            "%d surfaced row(s) not reviewed: no ANTHROPIC_API_KEY, so the fleet "
            "is unconfigured. The deterministic suppression checks still stand.",
            len(candidates),
        )
        return ReviewOutcome(recommendations=[c.recommendation for c in candidates])

    verdicts = _run_off_loop(
        lambda: _review_batch(candidates, resolved, client_factory)
    )

    out: list[Recommendation] = []
    blocked = 0
    for candidate, verdict in zip(candidates, verdicts):
        row, did_block = _amend(candidate, verdict)
        out.append(row)
        blocked += 1 if did_block else 0
        if did_block:
            logger.warning(
                "skeptic blocked %s %s: %s",
                row.ticker, row.side, row.suppressed_reason,
            )

    return ReviewOutcome(
        recommendations=out, reviewed=len(candidates), blocked=blocked
    )
