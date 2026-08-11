"""The Historian — the weekly post-mortem, and the flywheel's brake.

Runs weekly over the marts, writes a dated lesson, and may propose changes to
the strategy config. That last part is where a learning loop usually goes
wrong, so the guards matter more than the agent does.

**The Historian is handed conclusions, not raw data.** It receives the output
of `mart_clv_by_bucket`, `mart_calibration`, `mart_suppression_audit` and
`mart_multiple_comparisons` — each of which has already applied the noise
guard, the pooling check, and the multiple-comparisons correction. It is not
asked to do statistics; it is asked to read statistics that have already been
done properly and say what they mean. An agent invited to find patterns in raw
outcomes will find them, and they will be noise.

**It cannot change anything.** A proposal is a diff with a rationale, stored
`approved_by_user = 0`. Nothing takes effect until a human accepts it, and
every recommendation records the config version that produced it, so the effect
of an accepted change is measurable afterwards rather than a matter of opinion.

**A proposal must clear the same bar as any other finding.** The prompt makes
the sample size and the chance-expectation explicit, and instructs the agent to
propose nothing when the evidence does not support it. Twenty bets is not
evidence, and a flywheel that tunes on twenty bets is just overfitting with
extra steps.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .base import AgentConfig, structured_call

logger = logging.getLogger(__name__)

SYSTEM = """\
You are the Historian. Once a week you read the measurement marts and write up \
what the record shows.

Everything you receive has ALREADY been through the statistical guards: the \
noise guard, the pooling check across subgroups, and a multiple-comparisons \
correction. Cells that could not be distinguished from noise are marked as \
such. Do not attempt to re-derive significance, and do not treat a cell marked \
"(noise)" as weak evidence — it is no evidence.

Read the multiple-comparisons verdict FIRST. If it says the findings are \
consistent with chance, then there are no findings this week, however \
interesting an individual bucket looks.

Your output has two parts.

A LESSON: what the record shows, in a few sentences. "Nothing yet" is the \
correct and expected answer most weeks, especially early. Say it plainly \
rather than manufacturing an observation.

Optionally, CONFIG PROPOSALS. Propose a change only when a specific number \
supports it and the sample is adequate. Each proposal must name the parameter, \
the current and proposed values, the evidence, and the sample size behind it. \
If a suppression rule shows it is rejecting bets that went on to beat the \
close, that is the clearest legitimate case for loosening one.

Propose nothing if nothing is supported. An empty proposal list is a good \
week's work. The cost of a bad proposal is not that it gets rejected — it is \
that it gets accepted, and then the config drifts toward whatever the last \
twenty bets happened to do."""


class ConfigProposal(BaseModel):
    """A proposed change. Inert until a human accepts it."""

    parameter: str = Field(description="Config key, e.g. 'max_market_width'.")
    current_value: str
    proposed_value: str
    rationale: str = Field(description="Which number supports this, and how.")
    supporting_sample_size: int = Field(
        ge=0, description="Observations behind the evidence. Small numbers "
        "should stop you proposing at all."
    )
    risk_if_wrong: str = Field(
        description="What gets worse if this change is a mistake."
    )


class HistorianReport(BaseModel):
    period: str
    lesson_title: str = Field(description="Short, and a claim rather than a topic.")
    lesson_body: str = Field(
        description="What the record shows. 'Nothing yet' is correct most weeks."
    )
    evidence_read: list[str] = Field(
        description="Which marts you read and what each one said.", min_length=1
    )
    findings_are_distinguishable_from_chance: bool = Field(
        description="Taken from the multiple-comparisons verdict, not your own "
        "judgement of the buckets."
    )
    proposals: list[ConfigProposal] = Field(
        default_factory=list,
        description="Empty is a good week's work.",
    )

    @property
    def proposes_change(self) -> bool:
        return bool(self.proposals)


def build_prompt(
    *,
    period: str,
    multiple_comparisons: dict,
    clv_by_bucket: list[dict],
    calibration: list[dict],
    suppression_audit: list[dict],
    fee_reconciliation: list[dict],
    current_config: dict,
) -> str:
    payload = {
        "period": period,
        "multiple_comparisons_READ_THIS_FIRST": multiple_comparisons,
        "clv_by_bucket": clv_by_bucket,
        "calibration": calibration,
        "suppression_audit": suppression_audit,
        "fee_reconciliation": fee_reconciliation,
        "current_strategy_config": current_config,
    }
    return (
        "Here is this period's record. Every cell has already been through the "
        "noise guard and the pooling check.\n\n"
        f"```json\n{json.dumps(payload, indent=2, default=str)}\n```\n\n"
        "Read the multiple-comparisons verdict before anything else."
    )


async def review(
    client, config: AgentConfig, **prompt_kwargs: Any
) -> Optional[HistorianReport]:
    """Run the weekly post-mortem. **Nothing calls this.**

    There is no weekly scheduler, no route, and no reference outside this module
    and `scripts/measure_agent_cache_prefix.py` -- which imports the prompt text
    to count tokens and never runs the agent. The module's own docstring
    describes a cadence ("Once a week you read the measurement marts") that
    nothing produces; the same shape as `scout.research`, and recorded in
    `docs/adr/0022-quarantine-the-orphaned-modules.md`, which classifies this
    module **QUARANTINED**.

    Do not wire it up. ADR 0022 §4 keeps it parked rather than deleted because
    it plausibly matters under ADR 0021 §8 Options B and F, both of which need a
    post-mortem loop -- but turning it on is live Anthropic spend and is Joe's
    call. `tests/test_has_callers.py` fails if an import connects it to a
    deployed entry point.
    """
    return await structured_call(
        client,
        model=config.model,
        system=SYSTEM,
        user_content=build_prompt(**prompt_kwargs),
        output_model=HistorianReport,
        max_tokens=8000,
        # The hardest reasoning in the fleet: reading several marts together
        # and resisting the pull toward finding something.
        effort="high",
    )


def store_report(conn, report: HistorianReport, *, created_ms: int) -> int:
    """Persist a lesson and any proposals, all unapproved.

    `accepted_by_user` is NULL, meaning undecided. Proposals sit in the
    Playbook until a human acts, and the config is untouched either way.
    """
    cursor = conn.execute(
        "INSERT INTO lessons (created_ms, title, body, evidence_json, "
        "sample_size, proposed_config_diff, accepted_by_user) "
        "VALUES (?, ?, ?, ?, ?, ?, NULL)",
        (
            created_ms,
            report.lesson_title,
            report.lesson_body,
            json.dumps(
                {
                    "evidence_read": report.evidence_read,
                    "distinguishable_from_chance":
                        report.findings_are_distinguishable_from_chance,
                }
            ),
            max((p.supporting_sample_size for p in report.proposals), default=0),
            json.dumps([p.model_dump() for p in report.proposals])
            if report.proposals else None,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def validate_proposals(
    report: HistorianReport, *, min_sample: int = 100
) -> tuple[list[ConfigProposal], list[str]]:
    """Filter proposals that the agent should not have made.

    A second, deterministic gate behind the prompt's instruction. Prompts are
    guidance; this is enforcement, and the two disagreeing is exactly the case
    worth catching — an agent that proposes a change off thirty observations
    is not malfunctioning, it is being agreeable, which is harder to notice.
    """
    kept: list[ConfigProposal] = []
    rejected: list[str] = []

    for proposal in report.proposals:
        if not report.findings_are_distinguishable_from_chance:
            rejected.append(
                f"{proposal.parameter}: the period's findings are not "
                f"distinguishable from chance, so no change is supported."
            )
        elif proposal.supporting_sample_size < min_sample:
            rejected.append(
                f"{proposal.parameter}: {proposal.supporting_sample_size} "
                f"observations is below the {min_sample} minimum. Tuning on a "
                f"sample this size is overfitting."
            )
        else:
            kept.append(proposal)

    if rejected:
        logger.info("rejected %d Historian proposal(s): %s", len(rejected), rejected)
    return kept, rejected
