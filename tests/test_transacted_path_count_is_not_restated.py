"""CLAUDE.md names the transacted-path instrument. It does not restate its count.

The decay this guards against -- ADR 0162
------------------------------------------
The transacted-path paragraph in CLAUDE.md ("Three quantities circulate as
the count of the transacted path...") carried a live row count inline and
was corrected four times in nine days -- "two" until 2026-09-10, "four by
2026-09-09" until 2026-09-14, a 7/6/4 reading until 2026-09-15 (found six
orders stale), and a 13/12/10 reading until 2026-09-17 (found stale two days
after it was written, three orders and seven positions off). Joe keeps
placing orders; that is the point of the tool, not a defect to fix. A
document every session is told to trust cannot carry a number that decays
on that clock.

ADR 0162's fix is to state the durable claim and the instrument that
answers it, and to move any point-in-time reading to a dated file in
`docs/measurements/` that is allowed to go stale because nothing points a
session at it as ground truth. This test pins that shape: the paragraph
keeps naming its instruments, and none of the three concrete formats this
number has previously been written in -- each one individually the subject
of a same-week correction -- has come back.

What this test establishes
---------------------------
1. CLAUDE.md still names the instruments a session needs to get a current
   number: `manual-orders-audit`, `/api/hedge`, and the durable "stale on
   sight" disclaimer that stops a session from trusting a stale figure
   instead of re-running them.
2. None of the three exact shapes this line has recurred in -- a
   `manual_orders ... rows, dry_run` count, an "N OPEN rows, ids 1-N" count,
   and a "**N real rows, N filled, N unfilled**" restatement -- appears
   anywhere in the file. These are the literal patterns that were each
   individually wrong within days of being written; a regression to any one
   of them is the same failure recurring, whatever prose surrounds it.

What it does not establish
---------------------------
- That no other live count exists anywhere in CLAUDE.md. A generic
  digit-pattern guard over the whole file would be noise (ADR numbers,
  dates, line numbers, fee coefficients, the beta fits, the 300-game floor
  are all made of digits and are not the failure this guards against); this
  test is intentionally narrow to the three shapes that have actually
  recurred, not "any number near this paragraph."
- That a NEW, differently-worded live count could not be written here. If
  the paragraph decays into a fourth shape, extend `_KILLED_SHAPES` the day
  it happens, per the pattern in `test_a_question_for_joe_has_a_ticket.py`.
- Anything about `docs/measurements/*.md`, where a dated reading is
  correct and expected to go stale by design.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_MD = ROOT / "CLAUDE.md"

# The exact shapes this paragraph has recurred in. Each was individually
# wrong within days of being written (see the module docstring); pinning the
# literal shape, not just "a number", is what makes a mutation catch a
# regression rather than a rewording.
_KILLED_SHAPES = {
    "a `manual_orders ... rows, dry_run` count": re.compile(
        r"manual_orders\s+\d+\s+rows,\s*dry_run"
    ),
    "an 'N OPEN rows, ids 1-N' parlay_positions count": re.compile(
        r"\d+\s+OPEN rows,\s*ids\s+1-\d+"
    ),
    "a '**N real rows, N filled, N unfilled**' restatement": re.compile(
        r"\*\*\d+\s+real rows,\s*\d+\s+filled,\s*\d+\s+unfilled\*\*"
    ),
}

# The durable claim must still name what a session re-runs, not what this
# file last read. Matched at the token level (`\s+` between words, not a
# literal space) because CLAUDE.md is hard-wrapped -- a phrase that happens
# to fall across a line break must not silently pass this guard's own
# collapsed comparison while failing a literal one, per
# tasks/lessons.md 2026-09-16 (tenth).
_REQUIRED_PHRASES = (
    re.compile(r"manual-orders-audit"),
    re.compile(r"/api/hedge"),
    re.compile(r"stale\s+on\s+sight"),
)


def _text() -> str:
    return CLAUDE_MD.read_text(encoding="utf-8")


class TestTheParsersFindSomething:
    """A guard over an empty read passes vacuously and reads as green."""

    def test_claude_md_is_readable_and_the_size_a_real_spine_is(self):
        text = _text()
        assert len(text) > 10_000, "CLAUDE.md read suspiciously small -- wrong path?"


class TestTheTransactedPathParagraphNamesItsInstrumentNotADigit:
    def test_it_still_names_every_instrument_and_the_disclaimer(self):
        text = _text()
        missing = [p.pattern for p in _REQUIRED_PHRASES if not p.search(text)]
        assert missing == [], (
            f"CLAUDE.md is missing: {missing}. ADR 0162 requires the "
            f"transacted-path paragraph to name the instrument and say any "
            f"number is stale on sight, in place of stating a count itself."
        )

    def test_none_of_the_killed_live_count_shapes_have_returned(self):
        text = _text()
        offenders = [name for name, pat in _KILLED_SHAPES.items() if pat.search(text)]
        assert offenders == [], (
            f"CLAUDE.md has regrown a live count shaped like: {offenders}. "
            f"This paragraph went stale four times in nine days carrying a "
            f"number written exactly like this (ADR 0162) -- move any new "
            f"reading to docs/measurements/ instead of restating it here."
        )
