"""The Scout — the information network, minus the part that doesn't transfer.

Walters' team had people who knew about an injury before the line moved. That
is not reproducible with a web search: by the time news is indexed, thirteen
market makers quoting under 200ms have already repriced it.

So the Scout is not a speed play. It exists to answer a different question:
**given that the tool has flagged this game, what does a human need to know
before deciding?** Whether the starter was scratched, whether it is 40mph wind
in the Bronx, whether a team is on the back end of a road trip. Facts, with
sources and timestamps.

**The Scout never outputs a probability.** Not a win probability, not a fair
price, not an adjustment factor. The moment an agent starts producing numbers
that feed a bet, the tool has an unfalsifiable component in its money path.
Its output is context a person reads, and its schema has no numeric field to
put a forecast in — that is enforcement, not etiquette.

**Since 2026-08-21 this module holds the desk's shared schema and prompt
material, and nothing that spends.** The solo `research()` function this file
carried through its quarantine years (ADR 0022, ADR 0040) was deleted rather
than wired: the revival that finally came (ADR 0060, on the owner's word) is a
*desk* — two staff scouts and a master in `scout_desk.py`, metered by
`AgentBudget` — and an unmetered solo function beside a metered desk would
have been exactly the back door `tests/test_has_callers.py` exists to shut.
"""

from __future__ import annotations


from typing import Literal, Optional

from pydantic import BaseModel, Field


# Server-side web search. Injury reports, weather and lineup news are exactly
# what it is for, and results come back with citations.
WEB_SEARCH_TOOL = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": 6,
}

SYSTEM = """\
You are the Scout. You gather facts about one upcoming game so a person can \
decide whether a flagged price makes sense.

Report only what you can source. For each finding give the fact, where it came \
from, and when it was reported. Recency is the whole point: a lineup note from \
three days ago has usually already been priced in by every venue, while one \
from twenty minutes ago may not have been.

Look for: confirmed or probable starters and scratches, injuries and their \
designations, weather where it affects play, rest and travel, and any \
significant news about the fixture itself such as a venue change or \
postponement risk.

Two hard rules.

You must NOT estimate any probability, fair price, line, or point spread, and \
must not say whether the bet is good. That is not modesty; those numbers come \
from code that can be backtested, and an unfalsifiable estimate in the middle \
of a money path is worse than no estimate.

If you find nothing noteworthy, say so and return an empty findings list. An \
empty result is a useful answer. Inventing minor observations to look thorough \
makes the whole feed less trustworthy."""


class ScoutFinding(BaseModel):
    """One sourced fact. No numeric forecast field exists here, by design."""

    category: Literal[
        "injury", "lineup", "weather", "rest_travel", "venue", "other"
    ]
    fact: str = Field(description="What is true, in one or two sentences.")
    source: str = Field(description="Publication or outlet name.")
    source_url: Optional[str] = None
    reported_when: str = Field(
        description="When this was reported, as precisely as the source allows."
    )
    likely_already_priced: bool = Field(
        description="True if this is old enough that every venue has almost "
        "certainly reacted. Old news explains nothing about a current gap."
    )
    affects_side: Optional[str] = Field(
        default=None, description="Which team this bears on, if either."
    )


class ScoutReport(BaseModel):
    game: str
    findings: list[ScoutFinding] = Field(
        default_factory=list,
        description="Empty is a valid and useful answer.",
    )
    summary: str = Field(
        description="Two sentences at most. If nothing was found, say that."
    )
    searched_for: list[str] = Field(
        description="What you looked for, so a reader knows what an empty "
        "result actually rules out.",
        min_length=1,
    )

    @property
    def has_fresh_news(self) -> bool:
        """Any finding recent enough to plausibly explain a current mispricing."""
        return any(f for f in self.findings if not f.likely_already_priced)

