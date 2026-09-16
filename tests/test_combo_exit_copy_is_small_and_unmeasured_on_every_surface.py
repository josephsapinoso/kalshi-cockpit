"""Every sentence about getting out of a combination says the way out is small and unmeasured.

The universal -- *no combination book has ever carried a resting YES bid, so
the only exit is the outcome* -- died on 2026-09-10 when two
`KXMVECROSSCATEGORY-SHARD1` books were read carrying resting YES bids of ten
contracts each (`backend/parlays.py`, `COMBO_EXIT_SHARD_YES_BID_*`;
`docs/measurements/2026-09-13-combo-exit-nfl-sunday-result.md` §4). An
existence proof kills a universal and supplies no rate: ADR 0146 killed the
frequency question, so "how often" is unmeasured and no screen may imply a
rate in either direction.

THE DEFECT THIS PINS
--------------------
The correction landed on 2026-09-10 on the surfaces someone was looking at
(the server's `combo_note`, the bid route's refusal, the `/parlays` lede, the
`PriceOnKalshi` buy note) and on the buy ticket's FALLBACK paragraph -- and
not on the checkbox six lines below that paragraph, which Joe reads and ticks
on every combination he buys, nor on the parlay card's price-to-beat note.
Both kept the dead claim for six days. The one test on this claim,
`tests/test_buy_controls.py::test_the_combo_buy_names_the_missing_exit`,
asserted the word "exit" in one note and touched neither -- a slice narrow
enough to stay green while the claim was false two files away. Issue #41,
answered A by Joe on 2026-09-16, supplied the checkbox's words.

The shape is the one `tasks/lessons.md` records from ADR 0154: fix every
reader, not the one whose symptom you saw. And the flattering half is the one
that survives -- here "flattering" ran the CAUTIOUS way (Joe was told a bet
was less exitable than it may be), which is exactly why nobody hurried.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Source text, not rendering.** Same instrument and same limit as
  `test_soft_fallback_is_shown_on_every_price_surface.py`: a green suite says
  the words are in the file, not that they render, fit a phone, or are read.
- **Nothing about whether the exit claim is true.** `test_combo_book_depth_claims`
  owns the 40-book census; the two shard-1 books are a disclosed unregistered
  look and nothing here measures them again.
- **Nothing about the digits.** Whether a census number is sourced or typed is
  `test_the_exit_census_copy_names_its_scope.py` and its `ast` siblings.
- **Nothing about Joe's ratified lede.** `/parlays` says "hardly anyone is
  bidding to buy it back" in words he re-ratified on 2026-09-10; this file
  checks only that it carries no absolute, and leaves its wording to
  `test_tab_ledes.py`.

Mutations, each observed red on 2026-09-16:
  1. restore "no way out of this bet except the outcome" on the checkbox
  2. restore "nobody bids to buy it back, so the only exit once you own it is
     the outcome" on ParlayCards
  3. drop "unmeasured" from the PriceOnKalshi `note=`
  4. restore "you cannot exit it" in the ManualTicket fallback paragraph
  5. restore "the hedge is its only exit" in `routes.py`'s position note
  6. remove the ParlayCards entry from `FRONTEND_SURFACES` while the sentence
     is still there (the sweep names the orphaned sentence)
  7. add a fresh "a combination has no exit" string to `backend/api/routes.py`
     outside any listed marker (the sweep names it)
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

#: What every exit sentence owes the reader: that the way out is SMALL and
#: that its FREQUENCY is unmeasured. Two words rather than one phrase, because
#: the surfaces say it in their own sentences ("small and unmeasured", "tiny.
#: How often is unmeasured", "small, and its frequency is unmeasured") and a
#: single literal would force every surface to be rewritten to satisfy a
#: grep, or -- the way it actually goes -- would be satisfied by one surface
#: and never applied to the rest.
SIZE = re.compile(r"\bsmall\b|\btiny\b", re.IGNORECASE)
UNMEASURED = re.compile(
    r"unmeasured|never been measured|not been measured", re.IGNORECASE
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
        BackendSurface(ROUTES, "hold it to the outcome"), id="routes-combo_note"
    ),
    pytest.param(
        BackendSurface(ROUTES, "getting out is small"),
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
        BackendSurface(BID_ROUTER, "close to enter-only"), id="bid-router-422"
    ),
    pytest.param(
        BackendSurface(PARLAYS, "Getting out is the half"),
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


class TestEverySurfaceSaysTheWayOutIsSmallAndUnmeasured:
    """Mutation 3, and the requirement the checkbox never had.

    Both halves, separately, so neither can be dropped: "an exit exists"
    without its size is an availability claim, and "small" without
    "unmeasured" is a rate nobody measured.
    """

    @pytest.mark.parametrize("surface", FRONTEND_SURFACES)
    def test_the_screen_names_the_size_and_disclaims_the_rate(self, surface):
        if surface.ratified:
            pytest.skip(f"Joe's wording; pinned by {surface.owner}")
        words = frontend_slice(surface)
        if surface.path == PRICE_ON_KALSHI:
            # The `note=` string, not the element: the element carries a JSX
            # comment about the exit and `code_only` has already removed it,
            # but the attribute is what renders and is what to read.
            words = words[words.index('note="') + len('note="') :]
            words = words[: words.index('"')]
        assert SIZE.search(words), (
            f"{surface.path.name}: the exit sentence does not say the way "
            "out is small"
        )
        assert UNMEASURED.search(words), (
            f"{surface.path.name}: the exit sentence does not say how often "
            "a way out is there is unmeasured"
        )

    @pytest.mark.parametrize("surface", BACKEND_SURFACES)
    def test_the_server_names_the_size_and_disclaims_the_rate(self, surface):
        words = backend_slice(surface)
        assert SIZE.search(words), (
            f"{surface.path.name}: {surface.marker!r} does not say the way "
            "out is small"
        )
        assert UNMEASURED.search(words), (
            f"{surface.path.name}: {surface.marker!r} does not say how often "
            "a way out is there is unmeasured"
        )

    def test_the_checkbox_carries_joes_words(self):
        """Issue #41, answer A, verbatim -- the sentence Joe ticks."""
        words = frontend_slice(
            FrontendSurface(MANUAL_TICKET, "checked={comboOk}", "</label>")
        )
        words = re.sub(r"\s+", " ", words)
        assert (
            "I understand I may not be able to get out of this bet, and any "
            "way out is small and unmeasured." in words
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
