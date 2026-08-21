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

**5. The fan-out is metered, and what it cannot afford is refused rather than
dropped.** Until 2026-08-11 `_review_batch` gathered over every candidate with
no cap of any kind, so the bill was bounded only by `surfaced == 0` -- a
measurement outcome, not a setting. `agents/budget.py` now bounds one pass and
the day. When the ceiling binds, the rows past it come back **suppressed with
`skeptic_unreviewed`**, not silently truncated: a row nobody attacked must not
be indistinguishable from one the Skeptic tried and failed to break. Per
CLAUDE.md the unreadable resolves to a refusal, never to a pass.

That choice has money attached in the other direction too, and it is worth
stating plainly rather than burying: **the rows the ceiling refuses are rows the
tool will not bet**, so the ceiling can cost opportunities as well as save
dollars. The slice is the caller's order -- the order rows were judged, which is
discovery order and is not a ranking. Nothing here decides that the first eight
rows are the eight worth reviewing; the ceiling is meant to be set high enough
that it does not choose, and its binding is meant to be visible on the card.

Cost note
---------
The client is constructed per batch, because each batch runs on its own event
loop and an `httpx.AsyncClient` cannot be shared across loops. That is ~500ms
(`tasks/lessons.md`), paid only on passes that surface something -- never on
the quote passes that make up the cadence.

What this module does NOT establish
-----------------------------------
(beyond the note above)

**That every row reaching the database was attacked.** A Skeptic outage still
returns `None` per row and `None` still means "no opinion", so on a bad day a
surfaced row reaches the screen having been *asked about* and not answered. That
is decision 4 and it is unchanged here. Only rows that were never asked about --
because the ceiling refused the call -- carry `skeptic_unreviewed`. The two
states are recorded differently in `agent_calls` (an outage writes a row with a
`NULL` verdict; a refusal writes nothing, because nothing was spent) but they
are **not** distinguishable on the card, and that gap is not closed here.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from ..engine import Recommendation, with_added_suppression
from ..store.db import now_ms
from . import skeptic
from .base import AgentConfig, StructuredCallOutcome, build_client
from .budget import AgentBudget

logger = logging.getLogger(__name__)

# The suppression reason a row carries when no Skeptic call was made for it.
# Deliberately not one of `core/suppression.ALL_CHECK_NAMES`: that vocabulary is
# the deterministic checks and is part of `strategy_config_version`. This is the
# same class of tag as `skeptic_defect` -- added after the checks have run, by
# the layer above them.
UNREVIEWED_REASON = "skeptic_unreviewed"


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
    """What the review did, so a pass can report it rather than imply it.

    `unreviewed` is separate from `reviewed` rather than derivable from it,
    because the caller holds the total and this object does not: a pass that
    reviewed 8 rows looks identical whether it was handed 8 or 23. That is the
    difference between "the fleet ran" and "the fleet ran and refused fifteen
    bets", and the second one has to be reportable.
    """

    recommendations: list[Recommendation]
    reviewed: int = 0
    blocked: int = 0
    unreviewed: int = 0


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


def _refuse_unreviewed(candidate: ReviewCandidate, reason: str) -> Recommendation:
    """One row that no call was made for, re-stated as not actionable.

    Uses the same machinery as a Skeptic block, which is the point: the four
    fields `with_added_suppression` moves together are exactly the ones that
    stop `POST /api/orders` and stop the card rendering as buyable. A row that
    was never attacked must not be sellable, and it must not read as one the
    Skeptic cleared.
    """
    existing = candidate.recommendation.suppressed_reason
    tag = UNREVIEWED_REASON if not existing else f"{existing},{UNREVIEWED_REASON}"
    return with_added_suppression(
        candidate.recommendation,
        reason=tag,
        problem=f"the Skeptic never saw this row: {reason}",
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
        # No response arrived, so there is no usage to record either; the
        # reserve row settles to NULLs, and `calls_unmetered_today` counts it.
        return StructuredCallOutcome(parsed=None, usage=None)


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
    conn,
    config: Optional[AgentConfig] = None,
    client_factory=build_client,
    budget: Optional[AgentBudget] = None,
    now: Optional[int] = None,
) -> ReviewOutcome:
    """Attack every surfaced row the budget affords, and fold the verdicts in.

    Callers pass **only** rows they intend to surface -- filtering is the
    caller's job because the caller is what holds the un-surfaced rows, and
    passing them here would make the cheap path (no surfaced rows, no API key,
    no calls) depend on a check inside a module the runner would then always
    have to enter.

    Degrades to "no commentary" rather than failing when `ANTHROPIC_API_KEY` is
    unset: `AgentConfig.from_env()` returns `None` and every row comes back
    untouched. That is the state on any instance without the secret set,
    including every local run.

    **`conn` is required, and there is no default.** It is what makes the daily
    ceiling durable, and an optional connection would mean a caller could reach
    the billed path with the meter silently absent -- which is a precise
    restatement of the defect this function was changed to fix. The signature is
    the enforcement: a caller with no database cannot spend money by omission.

    **The whole fan-out is reserved before any call goes out.** `meter.reserve`
    writes one `agent_calls` row per reviewable candidate *before*
    `_run_off_loop`, and `meter.settle` fills in the verdicts when the batch
    returns. Until 2026-08-11 this docstring claimed that and the code did the
    opposite: the first row was written only after every call in the batch had
    returned, so a process death mid-`gather` left up to
    `AGENT_MAX_CALLS_PER_PASS` billed calls with no row at all -- and since
    `spent_today` is `COUNT(*)`, the next pass saw a *larger* allowance than it
    was owed. `docker/entrypoint.sh` restarts, `run_loop` re-prices the same
    slate, the same rows surface, and nothing in this repo bounded the loop.

    Reserving first inverts the error: a crash now over-counts, so the day is
    charged for calls it may not have made. That costs reviews, which tomorrow
    returns; the other direction costs money, which it does not.

    Both the reserve and the settle happen on the **calling** thread, not inside
    `_review_batch`. The batch runs on a dedicated thread with its own event
    loop and a `sqlite3` connection is thread-affine, so writing from there
    raises.
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

    meter = budget if budget is not None else AgentBudget.from_config(conn, resolved)
    stamp = now if now is not None else now_ms()

    allowance = meter.allowance(stamp)
    reviewable = list(candidates[:allowance])
    refused = list(candidates[allowance:])
    # Asked for the *whole* batch, so the reason names the real shortfall rather
    # than the part that happened to fit.
    refusal = meter.refusal_reason(len(candidates), stamp) if refused else None
    # Was `# pragma: no cover` and unverified: no test could reach it, so by
    # this repo's standard it was decoration. `TestAGuardIsNotAGuardUntilItHasFired`
    # now drives it with a budget whose `allowance` and `refusal_reason`
    # disagree, and the mutation is recorded there.
    if refused and refusal is None:
        raise RuntimeError(
            f"the agent budget allowed {allowance} of {len(candidates)} calls "
            f"and then declined to say which ceiling bound. Refusing to persist "
            f"rows whose refusal has no stated reason."
        )

    # Reserve first. One row per call this pass is about to make, written and
    # committed before `_run_off_loop` starts any of them, so a death anywhere
    # in the fan-out leaves the day charged rather than unrecorded.
    reservations = [
        meter.reserve(
            called_ms=stamp,
            agent="skeptic",
            model=resolved.model,
            ticker=candidate.recommendation.ticker,
            side=candidate.recommendation.side,
        )
        for candidate in reviewable
    ]

    verdicts = (
        _run_off_loop(lambda: _review_batch(reviewable, resolved, client_factory))
        if reviewable
        else []
    )

    out: list[Recommendation] = []
    blocked = 0
    for candidate, call_id, outcome in zip(reviewable, reservations, verdicts):
        verdict = outcome.parsed
        row, did_block = _amend(candidate, verdict)
        # Settled here rather than inside the batch because the batch runs on a
        # dedicated thread with its own event loop and a sqlite3 connection is
        # thread-affine -- writing from there raises. A `None` verdict settles
        # to the NULLs `reserve` already wrote: the call cost money and consumed
        # the day's allowance either way, and "said nothing" must not be stored
        # as "looked and did not block".
        meter.settle(
            call_id,
            verdict=None if verdict is None else verdict.verdict,
            blocked=None if verdict is None else did_block,
            usage=outcome.usage,
        )
        out.append(row)
        blocked += 1 if did_block else 0
        if did_block:
            logger.warning(
                "skeptic blocked %s %s: %s",
                row.ticker, row.side, row.suppressed_reason,
            )

    for candidate in refused:
        row = _refuse_unreviewed(candidate, refusal or "")
        out.append(row)
        logger.warning(
            "skeptic did not review %s %s: %s", row.ticker, row.side, refusal
        )

    return ReviewOutcome(
        recommendations=out,
        reviewed=len(reviewable),
        blocked=blocked,
        unreviewed=len(refused),
    )


def review_retired(
    candidates: Sequence[ReviewCandidate],
    *,
    conn,
    now: Optional[int] = None,
) -> ReviewOutcome:
    """The scheduled Skeptic is retired (ADR 0062). Refuse every row, call nothing.

    This is the production default for `run_pricing_pass` since 2026-08-21.
    The edge surface no longer determines any decision (the tool is a betting
    desk; the edge-finder is a feature, not a determiner), so a metered LLM
    re-attacking surfaced rows was spend against a decision nobody makes --
    measured at 24 Opus calls in 4m22s on 2026-08-16, the whole daily cap,
    re-reviewing four prop rows six times over.

    Refusal, not pass-through, on purpose: `_refuse_unreviewed` moves the same
    four fields a Skeptic block moves, so an unattacked row still cannot reach
    `POST /api/orders` as buyable. Retiring the reviewer must not quietly
    promote the rows it used to review. `review_surfaced` stays importable for
    a caller that deliberately opts back in; nothing scheduled does.

    `conn` and `now` are accepted unused so this drops into the seam
    `_review_and_persist` calls without a second calling convention.
    """
    del conn, now
    return ReviewOutcome(
        recommendations=[
            _refuse_unreviewed(c, "retired (ADR 0062)") for c in candidates
        ],
        unreviewed=len(candidates),
    )
