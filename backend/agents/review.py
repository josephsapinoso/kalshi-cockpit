"""The seam between the pricing pass and a reviewer, and the refusal that sits in it.

Since ADR 0062 (2026-08-21) the pass's default reviewer is `review_retired`:
every surfaced row comes back refused as `skeptic_unreviewed`, and no Anthropic
call is made from any scheduled path. Since 2026-09-05 no call *can* be made
from here: the metered half of this module -- `review_surfaced`,
`_review_batch`, `_evaluate_one`, `_run_off_loop`, `_amend` -- was deleted
together with `skeptic.py`, the agent it fanned out to
(`docs/adr/DRAFT-the-historian-and-the-skeptic-are-deleted-and-the-desk-has-been-convened.md`).
No production caller had named `review_surfaced` since the retirement; every
reference was a test injecting it. What remains imports neither `base`, nor
`budget`, nor the SDK.

Why the seam stays when the reviewer went
-----------------------------------------
`runner._review_and_persist` still collects every judged row, hands the
surfaced ones to `review`, and persists only afterwards. That two-phase shape
is what keeps a surfaced row from sitting orderable on disk while something
looks at it, and it is what `tests/test_agent_wiring.py::
TestTheScheduledSkepticIsRetired` pins: make any reviewer that passes rows
through the `run_pricing_pass` default and the surfaced row persists orderable,
and the test goes red. The seam is the guard's attachment point, so the seam
stays.

`ReviewCandidate.prompt_kwargs` stays for the same reason. `runner._skeptic_
context` still builds a reviewer's prompt inputs for a surfaced row and nothing
reads them. Dropping the field would be a runner change inside a deletion that
is otherwise confined to `backend/agents/`, and it is the shape an opted-in
reviewer would need back.

The history this module carries, dated
--------------------------------------
- **2026-08-08.** Written as the Skeptic's caller. `backend/agents/*` was the
  fourth module in this project to be complete, tested and called by nothing,
  because `skeptic.apply_verdict` had no caller; this was the caller.
- **2026-08-11.** Metered (`budget.py`): reserve-before-spend, one
  `agent_calls` row per candidate, refusal past the ceiling.
- **2026-08-16.** 24 metered Opus calls in 4m22s from this seam -- the whole
  daily cap -- re-reviewing four prop rows six times at quote-pass cadence.
  `surfaced` read 0 afterwards only because the Skeptic blocked all 24
  (ADR 0062 section 3; `fly.live.toml`, the `agent_calls` note).
- **2026-08-21.** Retired as the default (ADR 0062). `review_retired` is what
  the runner has imported since.
- **2026-09-05.** The metered half deleted. The live-spend seam that CLAUDE.md
  and ADR 0071 section 1 describe no longer exists in the tree. A caller that
  wants a metered reviewer writes one and puts it on
  `tests/test_has_callers.py::BILLED_PATH_CALL_SITES` with its meter named.

What this module does NOT establish
-----------------------------------
That a surfaced row is ever *reviewed*. It is refused, on purpose, and the
refusal is not a verdict: `skeptic_unreviewed` means nobody looked. The
deterministic checks in `core/suppression.py` are the only review a row gets,
and the game screen's skeptic panel renders those (ADR 0068).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from ..engine import Recommendation, with_added_suppression

# The suppression reason a row carries when no reviewer call was made for it.
# Deliberately not one of `core/suppression.ALL_CHECK_NAMES`: that vocabulary is
# the deterministic checks and is part of `strategy_config_version`. This is the
# same class of tag as the `skeptic_defect` rows the record still holds from
# 2026-08-16 -- added after the checks have run, by the layer above them.
UNREVIEWED_REASON = "skeptic_unreviewed"


@dataclass(frozen=True)
class ReviewCandidate:
    """One judged row, plus the prompt inputs a reviewer would take.

    `prompt_kwargs` is the mapping `runner._skeptic_context` builds for a
    surfaced row (empty for every other row). Held as a mapping rather than
    re-declared field by field so this module is not a second place those
    inputs are listed -- two lists of the same fourteen fields drift, and the
    drift is silent. Since 2026-09-05 nothing consumes it: the Skeptic it was
    shaped for is deleted and `review_retired` ignores it.
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
    bets", and the second one has to be reportable. Under `review_retired`
    every row is `unreviewed` and the other two counters are 0.
    """

    recommendations: list[Recommendation]
    reviewed: int = 0
    blocked: int = 0
    unreviewed: int = 0


def _refuse_unreviewed(candidate: ReviewCandidate, reason: str) -> Recommendation:
    """One row that no call was made for, re-stated as not actionable.

    Uses the same machinery as any suppression, which is the point: the four
    fields `with_added_suppression` moves together are exactly the ones that
    stop `POST /api/orders` and stop the card rendering as buyable. A row that
    was never attacked must not be sellable, and it must not read as one a
    reviewer cleared.
    """
    existing = candidate.recommendation.suppressed_reason
    tag = UNREVIEWED_REASON if not existing else f"{existing},{UNREVIEWED_REASON}"
    return with_added_suppression(
        candidate.recommendation,
        reason=tag,
        problem=f"the Skeptic never saw this row: {reason}",
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
    four fields a block moves, so an unattacked row still cannot reach
    `POST /api/orders` as buyable. Retiring the reviewer must not quietly
    promote the rows it used to review. Until 2026-09-05 this docstring said
    `review_surfaced` stayed importable for a caller that opted back in; it is
    deleted, and there is no metered reviewer in the tree to opt into.

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
