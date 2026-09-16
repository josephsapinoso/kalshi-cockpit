"""The hedge screen's headline calls its figure an estimate, and puts the
uncertainty beside the number at the number's size.

Issue #43, answered A by Joe on 2026-09-16. Until then the block over the
figure read **"lock available"** and the caption under it **"whichever way
the last leg goes"** -- a guarantee's words on a number that CLAUDE.md's
`/hedge` paragraph says carries at least four error terms of mixed sign
(E1-E4), one of which the 2026-09-15 census observed at 22 tenths a contract
on one of twelve rows. The headline is the sentence he acts on during a live
game, and it was the flattering one.

What A asked for, and what this pins
------------------------------------
1. The headline block (`EstimateHeadline` in `HedgePositions.tsx`) says
   "about", "either way" and "an estimate", and does not say lock, whichever,
   guaranteed, ceiling, floor, conservative, at least, or can only be. Refused
   at word boundaries, so `block` and `locks` are not false hits and the
   payload field `guaranteed` -- kept for its blast radius and read only by
   the CALLER of the headline -- cannot hide in the headline's source.
2. The uncertainty (`uncertainty_display`, rendered server-side by
   `hedge.estimate_grain`) is set INSIDE the figure's own element and there is
   no `text-xs` or `text-sm` in the figure branch -- "beside the number, not
   in smaller type underneath", Joe's words.
3. The glossary's `lock` entry no longer says the figure is "arithmetic, not a
   guess"; it calls it an estimate.

What this does NOT establish
----------------------------
- **Source text, not rendering.** Same instrument as
  `tests/test_soft_fallback_is_shown_on_every_price_surface.py`: a green suite
  says the component contains these words and lacks those, not that the page
  renders, wraps legibly at 390px, or that Joe reads it.
- **Nothing about the Discord push.** `notify/discord.py` still titles its
  field "Locks" and says "whichever way it goes"; #43 decided the screen
  headline and three tests in `test_hedge_alerts.py` pin the embed by name.
  That is a separate surface and, as of this test, a separate open question.
- **Nothing about the grain's content.** What `uncertainty_display` says, and
  that it refuses the same words, is `tests/test_hedge_positions.py`.

Mutations, each observed red on a backup copy (2026-09-16):
  1. heading text back to "lock available"
  2. caption back to "whichever way the last leg goes"
  3. `grain` moved out of the figure's <p> into a `text-xs` line under it
  4. caller passes `grain={null}` instead of `block.uncertainty_display`
  5. glossary `lock` definition back to "arithmetic, not a guess"
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARDS = ROOT / "frontend" / "src" / "components" / "HedgePositions.tsx"
GLOSSARY = ROOT / "frontend" / "src" / "lib" / "glossary.ts"

#: Words the headline may not use, from CLAUDE.md's `/hedge` paragraph plus
#: the two Joe struck. Matched at word boundaries, case-insensitively.
REFUSED = (
    r"\block\b",
    r"\blocks\b",
    r"\blocked\b",
    r"\bwhichever\b",
    r"\bguaranteed?\b",
    r"\bceiling\b",
    r"\bfloor\b",
    r"\bconservative\b",
    r"\bat least\b",
    r"\bcan only be\b",
)


def _strip_comments(tsx: str) -> str:
    tsx = re.sub(r"/\*.*?\*/", " ", tsx, flags=re.S)
    return re.sub(r"//[^\n]*", " ", tsx)


def headline_source() -> str:
    """`EstimateHeadline`'s source, comments removed, up to the next
    top-level function."""
    text = CARDS.read_text(encoding="utf-8")
    start = text.index("function EstimateHeadline(")
    rest = text[start:]
    end = re.search(r"\n(?:export )?function ", rest[1:])
    body = rest[: end.start() + 1] if end else rest
    return _strip_comments(body)


class TestTheHeadlineCallsTheFigureAnEstimate:
    def test_it_says_about_either_way_and_an_estimate(self):
        source = headline_source()
        assert "about {figure} either way" in source
        assert "an estimate" in source

    def test_it_refuses_the_words_that_promise(self):
        source = headline_source()
        for pattern in REFUSED:
            assert not re.search(pattern, source, flags=re.I), (
                f"the hedge headline says {pattern!r} again. Joe struck it on "
                "2026-09-16 (#43, A): the figure is an estimate with four "
                "terms of mixed sign on it, and these words render on the "
                "phone during a live game."
            )

    def test_the_uncertainty_sits_in_the_figures_own_element(self):
        """Beside the number, at the number's size -- not underneath, smaller."""
        source = headline_source()
        # The figure branch is the <p> that carries `{figure}`; `grain` must
        # be rendered inside that same <p>.
        figure_p = re.search(r"<p[^>]*>(?:(?!</p>).)*\{figure\}(?:(?!</p>).)*</p>", source, flags=re.S)
        assert figure_p is not None, "no <p> renders {figure}"
        assert "grain" in figure_p.group(0), "the grain is not in the figure's element"
        # And that element is not set in the muted small type the old caption
        # used; the block's only small type is the heading and the no-figure
        # sentence.
        opening = re.match(r"<p[^>]*>", figure_p.group(0)).group(0)
        assert "text-lg" in opening
        assert "text-xs" not in opening and "text-sm" not in opening
        assert "text-muted" not in opening

    def test_the_caller_feeds_it_the_servers_grain(self):
        """Vacuity guard for the test above: a headline that renders `grain`
        but is handed `null` would pass it and show nothing."""
        text = _strip_comments(CARDS.read_text(encoding="utf-8"))
        assert re.search(r"grain=\{block\.uncertainty_display", text), (
            "EstimateHeadline is not passed block.uncertainty_display"
        )
        assert "EstimateHeadline" in text.split("function EstimateHeadline(")[0]

    def test_the_caller_still_reads_the_guaranteed_flag_under_a_comment(self):
        """The payload field kept its name for its blast radius; the render
        site must say so or the next reader "fixes" the mismatch back."""
        text = CARDS.read_text(encoding="utf-8")
        site = text.index("<EstimateHeadline")
        preceding = text[max(0, site - 800) : site]
        assert "guaranteed" in preceding and "#43" in preceding


class TestTheGlossaryEntryAgrees:
    def test_lock_is_defined_as_an_estimate_not_arithmetic(self):
        text = GLOSSARY.read_text(encoding="utf-8")
        start = text.index("  lock: {")
        entry = text[start : text.index("  },", start)]
        assert "estimate" in entry
        assert "not a guess" not in entry
        assert "whichever" not in entry
