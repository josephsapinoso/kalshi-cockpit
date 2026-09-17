"""Every sentence about getting out of a combination says what it COSTS.

Renamed from `..._is_small_and_unmeasured_on_every_surface.py` on 2026-09-17.
That name was the old contract, and the old contract is refuted.

THE CLAIM, AND WHY IT IS ABOUT PRICE
------------------------------------
Sell-side RFQs on **all three combinations Joe holds** drew a bid for the side
he holds -- 16 of 44 quotes, 3 of 3 positions, every bid at the full size
asked -- and two of those three also carry a resting YES bid on the PUBLIC
book, 38,709 and 24,900 contracts deep against holdings of 8.22 and 60.97
(`docs/measurements/2026-09-17-combinations-can-be-exited.md`, ADR 0164). So
"the way out is small" is false and "how often is unmeasured" is stale.

**This is the fourth version of this sentence and the first that is not about
availability.** The three before it each asserted a FREQUENCY and each was
falsified within days:

  1. "no way out except the outcome"            -- dead 2026-09-10
  2. "any way out is small and unmeasured"      -- #41 answer A, dead 2026-09-17
  3. "a resting bid ... two books, ten contracts each" -- off by 3 orders of
     magnitude on the same day

Issue #60, answer (a): say what the exit **costs**, not how often it is there.
Every best bid on every position has sat BELOW the cost basis in every reading
ever taken, and unlike a frequency that does not decay with the next
measurement.

THE DEFECT THIS PINS
--------------------
Not one sentence -- the *set*. The 2026-09-10 correction landed on the four
surfaces someone was looking at and missed the checkbox six lines below one of
them, which Joe ticks on every combination he buys. That checkbox kept a dead
claim for six days while a green suite watched, because the only test on it
asserted the word "exit" in a different file. The sweep at the bottom exists
so a *new* exit sentence cannot appear anywhere without being enumerated here.

The shape is `tasks/lessons.md`'s ADR 0154 entry: fix every reader, not the
one whose symptom you saw. And the surviving error runs CAUTIOUS -- Joe was
told a bet was less exitable than it is -- which is exactly why nobody hurried.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Source text, not rendering.** Same instrument and limit as
  `test_soft_fallback_is_shown_on_every_price_surface.py`: a green suite says
  the words are in the file, not that they render, fit a phone, or are read.
- **Nothing about whether the exit claim is true.** The measurement owns that;
  this file owns only that every surface states it consistently. n = 3
  positions at one moment, and nothing here re-measures them.
- **Nothing about the digits.** Whether a census number is sourced or typed is
  `test_the_exit_census_copy_names_its_scope.py` and its `ast` siblings.
- **Nothing about Joe's ratified lede.** `/parlays` keeps wording he
  re-ratified; this file checks only that it carries no absolute and leaves
  its words to `test_tab_ledes.py`.

Mutations observed red on 2026-09-17:
  1. restore "any way out is small and unmeasured" on the checkbox
  2. drop the cost clause from the `PriceOnKalshi` `note=`
  3. drop the cost clause from `routes.py`'s `combo_note`
  4. restore "an exit is not impossible -- it is small" in `routes.py`
  5. remove a surface from the lists while its sentence is still there
     (the sweep names the orphan)
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
BACKEND = ROOT / "backend"

MANUAL_TICKET = FRONTEND / "components" / "ManualTicket.tsx"
PARLAY_CARDS = FRONTEND / "components" / "ParlayCards.tsx"
PRICE_ON_KALSHI = FRONTEND / "components" / "PriceOnKalshi.tsx"
PARLAYS_PAGE = FRONTEND / "app" / "parlays" / "page.tsx"
ROUTES = BACKEND / "api" / "routes.py"
BID_ROUTER = BACKEND / "api" / "routers" / "parlays.py"
PARLAYS = BACKEND / "parlays.py"

#: The wording of the dead universal, in every form it has been found in.
#: Matched case-insensitively over comment-stripped source, so a comment that
#: quotes the old sentence as history is not a hit but a rendered one is.
ABSOLUTE = re.compile(
    r"no way out"
    r"|only exit"
    r"|only way out"
    r"|cannot exit"
    r"|can(?:'|’)t exit"
    r"|can not exit"
    r"|no exit"
    r"|nobody bids"
    r"|nobody is bidding"
    r"|except the outcome"
    r"|has no exit",
    re.IGNORECASE,
)

#: **The requirement, since issue #60 answer (a) on 2026-09-17.** Every exit
#: sentence must say that selling back may COST more than holding. Not that a
#: way out exists, and not how often one is there — the cost.
COST = re.compile(
    r"cost (?:you |me |more)|more than holding|below what (?:had been |was |you )?paid"
    r"|BELOW what",
    re.IGNORECASE,
)

#: **The newly-forbidden claim, and the reason this file was renamed.**
#:
#: It *required* "small" and "unmeasured" until 2026-09-17, when sell-side
#: RFQs on all three combinations Joe holds drew a bid for the side he holds —
#: two of them also carrying resting YES bids 38,709 and 24,900 contracts deep
#: against holdings of 8.22 and 60.97. "Ten contracts each" was off by three
#: orders of magnitude, so "small" is false and "unmeasured" is stale.
#:
#: **The pattern this file has now demonstrated three times: every version of
#: this sentence that asserted a FREQUENCY was wrong within days.** The cost
#: claim replaces it because it has held in every reading ever taken — every
#: best bid, on every position, sat below the cost basis.
UNDERSIZED = re.compile(
    r"way out is small"
    r"|is small and unmeasured"
    r"|a way out exists and is tiny"
    r"|is small, and its frequency is unmeasured"
    r"|getting out is small",
    re.IGNORECASE,
)

#: The vocabulary of a sentence about leaving a combination. Anything in the
#: rendered source that says one of these is a combo-exit surface and must be
#: enumerated below, or the sweep at the bottom fails on it. Chosen against
#: the two trees as they stand: "getting out is" rather than "getting out",
#: because the glossary's `volume` entry says "getting out of a position can
#: be hard" about any thin market and is not a claim about combinations; and
#: "an exit is" rather than "exit is", because `StaleOddsExit.tsx` is the way
#: out of a grey slate and says so.
VOCABULARY = re.compile(
    r"way out"
    r"|sell it back"
    r"|buy it back"
    r"|bidding to buy"
    r"|hold (?:it )?to the outcome"
    r"|hold to settlement"
    r"|only exit"
    r"|no exit"
    r"|cannot exit"
    r"|except the outcome"
    r"|an exit (?:is|exists)"
    r"|exit once you own"
    r"|getting out is"
    r"|get out of this bet",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FrontendSurface:
    """A stretch of a TSX file between `start` and the next `end`."""

    path: Path
    start: str
    end: str
    #: `True` for a sentence whose wording is Joe's and is pinned elsewhere:
    #: it must still carry no absolute, but this file does not dictate its
    #: words. Named so the exemption is a category with a reason, not a
    #: parking space (the `AGGREGATE_SURFACES` lesson).
    ratified: bool = False
    #: Where the ratified wording is pinned, so the exemption costs a name.
    owner: str | None = None


@dataclass(frozen=True)
class BackendSurface:
    """A Python string literal (plain or f-string) that contains `marker`."""

    path: Path
    marker: str


#: Every sentence Joe can read about leaving a combination, on the screen.
FRONTEND_SURFACES = [
    pytest.param(
        FrontendSurface(MANUAL_TICKET, "checked={comboOk}", "</label>"),
        id="ManualTicket-checkbox",
    ),
    pytest.param(
        FrontendSurface(MANUAL_TICKET, "market.combo_note ??", "</p>"),
        id="ManualTicket-fallback",
    ),
    pytest.param(
        FrontendSurface(PARLAY_CARDS, "price_to_beat_display && (", "</div>"),
        id="ParlayCards-price-to-beat",
    ),
    pytest.param(
        FrontendSurface(PRICE_ON_KALSHI, "<ManualTicket\n", "/>"),
        id="PriceOnKalshi-note",
    ),
    pytest.param(
        FrontendSurface(
            PARLAYS_PAGE,
            "cards cut from tonight",
            "</p>",
            ratified=True,
            owner="tests/test_tab_ledes.py",
        ),
        id="parlays-lede",
    ),
]

#: Every sentence the server composes about leaving a combination, whether it
#: reaches a screen (`combo_note`, the two refusals, the position note) or a
#: permanent row (`parlay_positions.note`, written by `_record_combo_position`
#: and never read back today -- still authored copy, still on the record).
BACKEND_SURFACES = [
    pytest.param(
        BackendSurface(ROUTES, "You can sell a combination back"),
        id="routes-combo_note",
    ),
    pytest.param(
        BackendSurface(ROUTES, "need the acknowledgement"),
        id="routes-acknowledgement-refusal",
    ),
    pytest.param(
        BackendSurface(ROUTES, "legs could not be recovered"),
        id="routes-position_note",
    ),
    pytest.param(
        BackendSurface(ROUTES, "Recorded automatically from the hand-bet path"),
        id="routes-recorded-position-note",
    ),
    pytest.param(
        BackendSurface(BID_ROUTER, "a combination can be sold back"),
        id="bid-router-422",
    ),
    pytest.param(
        BackendSurface(PARLAYS, "Getting out works too"),
        id="parlays-NOTES-unquoted",
    ),
]


def code_only(text: str) -> str:
    """`text` with comments stripped -- the `test_crew_bubble` lesson.

    Both corrected surfaces carry a comment quoting the sentence they
    replaced. Without this, the prohibition below would fail on its own
    explanation, and the requirement would pass on it.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


def frontend_slice(surface: FrontendSurface) -> str:
    text = code_only(surface.path.read_text(encoding="utf-8"))
    assert surface.start in text, (
        f"{surface.path.name}: the surface anchored on {surface.start!r} moved"
    )
    block = text[text.index(surface.start) :]
    return block[: block.index(surface.end)]


def _is_docstring(node: ast.AST, parent: ast.AST) -> bool:
    body = getattr(parent, "body", None)
    return (
        isinstance(body, list)
        and bool(body)
        and body[0] is node
        and isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def backend_strings(path: Path) -> list[str]:
    """Every string literal in `path` that is not a docstring, unparsed.

    Rendered by `ast.unparse` so an f-string reads as its source (the placeholder
    names stay in), which is what the sibling guards read and for the same
    reason: a rendered string cannot tell a sourced number from a typed one.
    Docstrings are excluded because they describe code to a maintainer, not a
    bet to Joe; the report that ships with this test lists the ones that still
    say "only exit".
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip: set[int] = set()
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            if _is_docstring(child, parent):
                skip.add(id(child.value))
        if isinstance(parent, ast.JoinedStr):
            # An f-string's literal fragments are `Constant` nodes too, and
            # `ast.walk` visits them. Counting them would report one sentence
            # as several -- which the first run of this file did, and which
            # let a fragment satisfy a marker meant for a whole sentence.
            for piece in parent.values:
                skip.add(id(piece))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            found.append(ast.unparse(node))
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in skip
        ):
            found.append(node.value)
    return found


def backend_slice(surface: BackendSurface) -> str:
    hits = [s for s in backend_strings(surface.path) if surface.marker in s]
    assert hits, f"{surface.path.name}: no string carries {surface.marker!r}"
    assert len(hits) == 1, (
        f"{surface.path.name}: {surface.marker!r} is in {len(hits)} strings; "
        "pick a marker that names one sentence"
    )
    return hits[0]


class TestNoSurfaceStillAssertsTheDeadUniversal:
    """Mutations 1, 2, 4, 5."""

    @pytest.mark.parametrize("surface", FRONTEND_SURFACES)
    def test_the_screen_does_not_say_there_is_no_way_out(self, surface):
        # The whole file, not the slice: a prohibition is cheap to widen and
        # the same sentence could be pasted into a sibling paragraph.
        text = code_only(surface.path.read_text(encoding="utf-8"))
        hit = ABSOLUTE.search(text)
        assert hit is None, (
            f"{surface.path.name} still says {hit.group(0)!r}: two shard-1 "
            "books carried resting YES bids on 2026-09-10, so 'no way out' "
            "is false and the sentence to write is 'small and unmeasured'"
        )

    @pytest.mark.parametrize("surface", BACKEND_SURFACES)
    def test_the_server_does_not_say_there_is_no_way_out(self, surface):
        for s in backend_strings(surface.path):
            hit = ABSOLUTE.search(s)
            assert hit is None, (
                f"{surface.path.name} composes {hit.group(0)!r} for a "
                f"screen: {s[:120]!r}"
            )


class TestEverySurfaceNamesWhatTheExitCosts:
    """The requirement since #60 answer (a), 2026-09-17.

    Two halves, separately, so neither can be dropped: every surface must SAY
    the cost, and no surface may still call the way out small. The second is
    not implied by the first — the shipped ParlayCards sentence carried both
    a size claim and a measurement in the same breath.
    """

    @pytest.mark.parametrize("surface", FRONTEND_SURFACES)
    def test_the_screen_says_selling_back_may_cost_more(self, surface):
        if surface.ratified:
            pytest.skip(f"Joe's wording; pinned by {surface.owner}")
        words = frontend_slice(surface)
        if surface.path == PRICE_ON_KALSHI:
            # The `note=` string, not the element: the element carries a JSX
            # comment about the exit and `code_only` has already removed it,
            # but the attribute is what renders and is what to read.
            words = words[words.index('note="') + len('note="') :]
            words = words[: words.index('"')]
        assert COST.search(words), (
            f"{surface.path.name}: the exit sentence does not say that "
            "selling back may cost more than holding"
        )

    @pytest.mark.parametrize("surface", BACKEND_SURFACES)
    def test_the_server_says_selling_back_may_cost_more(self, surface):
        words = backend_slice(surface)
        assert COST.search(words), (
            f"{surface.path.name}: {surface.marker!r} does not say that "
            "selling back may cost more than holding"
        )

    @pytest.mark.parametrize("surface", FRONTEND_SURFACES)
    def test_the_screen_no_longer_calls_the_way_out_small(self, surface):
        """Refuted 2026-09-17 — two held positions had 38,709 and 24,900
        contracts resting on the public book, against holdings of 8 and 61."""
        text = code_only(surface.path.read_text(encoding="utf-8"))
        hit = UNDERSIZED.search(text)
        assert hit is None, (
            f"{surface.path.name} still says {hit.group(0)!r}: the exit was "
            "measured on 3 of 3 held combinations and is not small"
        )

    @pytest.mark.parametrize("surface", BACKEND_SURFACES)
    def test_the_server_no_longer_calls_the_way_out_small(self, surface):
        for s in backend_strings(surface.path):
            hit = UNDERSIZED.search(s)
            assert hit is None, (
                f"{surface.path.name} composes {hit.group(0)!r}: {s[:120]!r}"
            )

    def test_the_checkbox_carries_joes_words(self):
        """Issue #60, answer (a), verbatim — the sentence Joe ticks.

        The fourth version, and the first that is about price rather than
        availability. The previous three each asserted a frequency and each
        was falsified: "no way out except the outcome" (dead 2026-09-10),
        "any way out is small and unmeasured" (#41 answer A, dead
        2026-09-17), and the ParlayCards "ten contracts each" that went with
        it. This one makes no claim that a later measurement can move.
        """
        words = frontend_slice(
            FrontendSurface(MANUAL_TICKET, "checked={comboOk}", "</label>")
        )
        words = re.sub(r"\s+", " ", words)
        assert (
            "I understand selling this back may cost me more than holding it "
            "to the outcome." in words
        )

    def test_the_ratified_lede_is_pinned_where_this_file_says_it_is(self):
        """The exemption costs a name, or it becomes a parking space."""
        for param in FRONTEND_SURFACES:
            surface = param.values[0]
            if not surface.ratified:
                continue
            owner = ROOT / surface.owner
            assert owner.exists(), f"{surface.owner} is missing"
            assert surface.path.name in owner.read_text(encoding="utf-8"), (
                f"{surface.owner} does not name {surface.path.name}, so the "
                "ratified sentence is checked by nobody"
            )


class TestTheSurfaceListCannotSilentlyBecomeASubset:
    """Mutations 6 and 7: enumerate rather than remember.

    A sentence about leaving a combination that is not inside a listed slice
    is exempt from every assertion above -- which is exactly how the checkbox
    stayed wrong for six days while the paragraph above it was fixed.
    """

    def test_every_exit_sentence_on_a_screen_is_inside_a_listed_slice(self):
        spans: dict[Path, list[tuple[int, int]]] = {}
        for param in FRONTEND_SURFACES:
            surface = param.values[0]
            text = code_only(surface.path.read_text(encoding="utf-8"))
            start = text.index(surface.start)
            end = start + text[start:].index(surface.end) + len(surface.end)
            spans.setdefault(surface.path, []).append((start, end))
        orphans: list[str] = []
        for path in sorted(FRONTEND.rglob("*.ts*")):
            text = code_only(path.read_text(encoding="utf-8"))
            for hit in VOCABULARY.finditer(text):
                covered = any(
                    a <= hit.start() < b for a, b in spans.get(path, [])
                )
                if not covered:
                    line = text.count("\n", 0, hit.start()) + 1
                    orphans.append(
                        f"{path.relative_to(ROOT)}:{line} {hit.group(0)!r}"
                    )
        assert not orphans, (
            "combo-exit sentences outside every listed surface, so nothing "
            f"checks what they claim: {orphans}"
        )

    def test_every_exit_sentence_the_server_composes_carries_a_listed_marker(
        self,
    ):
        markers: dict[Path, list[str]] = {}
        for param in BACKEND_SURFACES:
            surface = param.values[0]
            markers.setdefault(surface.path, []).append(surface.marker)
        orphans: list[str] = []
        for path in sorted(BACKEND.rglob("*.py")):
            for s in backend_strings(path):
                if not VOCABULARY.search(s):
                    continue
                if any(m in s for m in markers.get(path, [])):
                    continue
                orphans.append(f"{path.relative_to(ROOT)}: {s[:100]!r}")
        assert not orphans, (
            "server-composed combo-exit sentences with no listed marker, so "
            f"nothing checks what they claim: {orphans}"
        )
