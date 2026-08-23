"""Willy Balters' seat at the scout desk (ADR 0069).

Joe asked for this voice by (his spelling of) the name: a professional
bettor's read of the game, sitting beside the scouts. **Willy Balters is a
fiction with a fiction's name** — the same house character who already
speaks on slate rows (`frontend/src/components/CrewBubble.tsx`), never the
living professional the name winks at. `.claude/agents/sharp-bettor.md`
forbids putting invented words in a real person's mouth;
`tests/test_crew_bubble.py` and `tests/test_pro_bettor.py` both pin the
spelling.

What the seat is: a fourth metered call per convening, **after** the master
settles, reading ONLY what the desk filed — the staff's notes and the
master's briefing. No tools (the search budget belongs to the staff), no
prices, no payloads. Words in, words out.

What the seat is not, structurally:

- **Not a forecast.** `SharpTake` has no numeric field anywhere, walked by
  test exactly as `DeskBriefing` is. The two hard rules below are copied
  from `scout_desk.py` verbatim, because a system prompt is the one place a
  rule must be present to exist at all.
- **Not a researcher.** It may not add facts. A pro's value here is
  process: what would move a professional, what is already in the line,
  and what would change his mind.
- **Not required.** The convening's `status` semantics are unchanged
  (`complete` still means staff pair + master); an unaffordable or failed
  seat becomes an honest absent-state, never a downgraded briefing.

What this module does not establish: that the take is any good. It has the
same epistemic status as the scouts' work — words for Joe's own judgement,
metered and sourced from the desk's filings alone.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

SYSTEM = """\
You are Willy Balters, the professional bettor's seat at a betting research \
desk. You are a house character -- a fiction, not a real person. Your staff \
-- two team scouts and a master scout -- have filed their notes on one \
upcoming game, and the desk's owner is not a professional: define any \
betting jargon in passing, plainly.

Read ONLY what the desk filed. Give the professional's read:

- What in these filings would actually matter to a professional, and what \
is noise. Most filed "news" is already in the line by the time anyone reads \
it -- say which items are plausibly not, and why.
- Process over picks: what a disciplined bettor would do with this game -- \
including passing, which is a position. Shopping the number, sizing small, \
waiting for a lineup confirmation: name the discipline that applies.
- What would change your mind: the specific facts that, if they arrived, \
would make this game interesting in either direction.

Two hard rules.

You must NOT estimate any probability, fair price, line, or point spread, and \
must not say whether any bet is good. That is not modesty; those numbers come \
from code that can be backtested, and an unfalsifiable estimate in the middle \
of a money path is worse than no estimate.

You may use ONLY what the staff and the master filed. You must not add facts, \
however well known. If the filings are thin, say so -- a short take over thin \
notes is honest; a padded one is not."""


class SharpTake(BaseModel):
    """The pro's read. Prose and words only — no field can carry a forecast.

    Every leaf in this schema is a string, deliberately and forever:
    `tests/test_pro_bettor.py` walks it recursively and fails if any numeric
    type appears anywhere — the package's no-numbers rule made structural,
    exactly as it is for `DeskBriefing` and `ScoutFinding`.
    """

    headline: str = Field(
        description="One sentence: the professional's single most important "
        "observation about this game's filings, or the honest statement "
        "that they contain nothing a pro would act on."
    )
    read: str = Field(
        description="The pro's read of the desk's filings, a short "
        "paragraph. Which items are plausibly not yet in the line, which "
        "are noise, and why. Never new facts, never a number."
    )
    discipline: list[str] = Field(
        default_factory=list,
        description="The process points that apply to this game — passing "
        "as a position, waiting for confirmations, shopping the number. "
        "Each in plain words a non-professional can use.",
    )
    would_change_my_mind: list[str] = Field(
        default_factory=list,
        description="The specific facts that, if they arrived, would make "
        "this game interesting in either direction.",
    )
