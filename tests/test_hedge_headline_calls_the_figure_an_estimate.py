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
- **The Discord push's RENDERED output** is `tests/test_hedge_alerts.py`
  (`TestTheHedgeAvailableEmbed`, `TestTheLegsInPlayEmbed`). What this file
  adds for it (`TestTheDiscordCopyAgrees`) is the source-level guard: every
  string literal the two embed builders and `_estimate_field` carry, read
  with `ast`, refuses the struck words -- so a reworded field cannot come
  back under a name no rendered test happens to select.
- **Nothing about the grain's content.** What `uncertainty_display` says, and
  that it refuses the same words, is `tests/test_hedge_positions.py`.

Mutations, each observed red on a backup copy (2026-09-16):
  1. heading text back to "lock available"
  2. caption back to "whichever way the last leg goes"
  3. `grain` moved out of the figure's <p> into a `text-xs` line under it
  4. caller passes `grain={null}` instead of `block.uncertainty_display`
  5. glossary `lock` definition back to "arithmetic, not a guess"
  6. discord.py: `_estimate_field` titled "Locks" again
  7. discord.py: `hedge_lock` description back to "a known answer in both branches"
  8. discord.py: `_estimate_field` value back to "... whichever way it goes"
  9. discord.py: `position_state` renders its own "Locks" field instead of `_estimate_field`
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARDS = ROOT / "frontend" / "src" / "components" / "HedgePositions.tsx"
GLOSSARY = ROOT / "frontend" / "src" / "lib" / "glossary.ts"
DISCORD = ROOT / "backend" / "notify" / "discord.py"

#: The functions in `discord.py` whose string literals are the push's copy.
EMBED_BUILDERS = ("hedge_lock", "position_state", "_estimate_field")

#: Literals that are wire names, not copy: the state a block reports and the
#: flag the alert predicate is named for. Exact matches only, so "lock" the
#: key passes and "Locks" the field title does not.
WIRE_NAMES = {"lock", "guaranteed", "guaranteed_display", "uncertainty_display", "hedge_lock"}

#: The one sentence in the many-live branch that may say "locks", because it
#: says nothing does. Pinned by name in `test_hedge_alerts.py`.
MANY_LIVE_BOILERPLATE = "No figure locks"

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


def _embed_literals(name: str) -> list[str]:
    """Every string literal inside `name`'s body, docstring excluded."""
    tree = ast.parse(DISCORD.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            body = node.body[1:] if ast.get_docstring(node) else node.body
            return [
                n.value
                for stmt in body
                for n in ast.walk(stmt)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            ]
    raise AssertionError(f"{name} is not defined in discord.py")


class TestTheDiscordCopyAgrees:
    """The push carries the screen's words, at the source.

    Read with `ast` rather than as raw text so the code around the copy --
    `block.get("kind") != "lock"`, `block.get("guaranteed")` -- is not a false
    hit and cannot be a hiding place either: every literal is checked except
    the exact wire names.
    """

    def test_every_builder_is_present_and_carries_copy(self):
        # Vacuity guard: a renamed builder would make the scan below scan nothing.
        for name in EMBED_BUILDERS:
            assert len(_embed_literals(name)) > 3, name

    def test_the_figure_line_is_about_either_way_an_estimate(self):
        literals = " ".join(_embed_literals("_estimate_field"))
        assert "either way — an estimate" in literals
        assert "Comes to" in literals
        # Both embeds reach the figure through the one helper.
        for name in ("hedge_lock", "position_state"):
            src = DISCORD.read_text(encoding="utf-8")
            start = src.index(f"async def {name}(")
            end = src.find("\n    async def ", start + 1)
            assert "_estimate_field(block)" in src[start : end if end > 0 else None], name

    def test_the_copy_refuses_the_struck_words(self):
        struck = (
            r"\bLocks\b",
            r"\block available\b",
            r"\block in\b",
            r"\blocked\b",
            r"\bwhichever\b",
            r"\bknown answer\b",
            r"\bguaranteed\b",
            r"\bceiling\b",
            r"\bfloor\b",
            r"\bconservative\b",
            r"\bat least\b",
            r"\bcan only be\b",
        )
        for name in EMBED_BUILDERS:
            for literal in _embed_literals(name):
                if literal in WIRE_NAMES or literal == MANY_LIVE_BOILERPLATE:
                    continue
                if "locks nothing" in literal:
                    # The many-live sentence: "buying one side of one leg
                    # locks nothing". A refusal, not a claim; its field is
                    # `MANY_LIVE_BOILERPLATE` and it is pinned by name.
                    continue
                for pattern in struck:
                    assert not re.search(pattern, literal), (
                        f"discord.py {name} says {pattern!r} again in {literal!r}. "
                        "Joe struck it on 2026-09-16 (#43, A); the push is the "
                        "first place he reads the figure."
                    )
