"""Both surfaces carrying the exit census say which population it measured.

Required by
`docs/measurements/2026-09-09-preregistration-combo-exit-nfl-sunday.md` §12.4,
and landed **before** the 2026-09-13 run rather than after it.

The sentence those surfaces carry -- *"every combination book this repo has
ever read had no YES bid, 40 of 40"* -- is **true** and **correctly sourced**.
Nothing about its digits is wrong, which is exactly why the existing
`ast`-parsing guards could not catch this: what was wrong is the **scope a
reader supplies**. All 40 books came from `KXMVESPORTSMULTIGAMEEXTENDED` and
`KXMVECROSSCATEGORY`; **zero** came from `KXMVECROSSCATEGORY-SHARD1** -- and
every hand fill this desk has taken is on that shard. Joe read the unscoped
sentence while tapping a shard-1 combination.

Waiting for Sunday was refused by the registrar for a named reason: it would
leave the screen making an unscoped claim *during* the measurement that scopes
it, and in the ABORTED-THIN branch the correction would never land at all --
the textbook shape of a caveat selected for being survivable.

**Both surfaces, in one file, because that is the claim.** Correcting the buy
ticket and not the bid route reproduces the original defect on the surface
nobody looks at, and two tests in two files would let one be deleted quietly.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about shard 1's books.** None has been read. The copy must imply
  neither that the shard was measured nor that it differs, and the tests below
  assert the absence of both implications rather than trusting the prose.
- Nothing about whether the exit claim is true. `test_combo_book_depth_claims`
  owns that against the captured evidence.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.parlays import (  # noqa: E402
    COMBO_EXIT_CENSUS_BOOKS_READ,
    COMBO_EXIT_CENSUS_SERIES,
    COMBO_EXIT_CENSUS_SHARD_BOOKS_READ,
    COMBO_EXIT_CENSUS_SHARD_SERIES,
)

#: The two strings that carry the census to a person about to spend money.
#: The marker is text that appears INSIDE the f-string, never the name of the
#: variable holding it -- a dict key or a parameter name is not part of the
#: sentence and would let the copy be moved out from under this guard.
SURFACES = {
    "buy ticket combo_note": (
        REPO / "backend" / "api" / "routes.py",
        "cannot exit it",
    ),
    "bid route 422": (
        REPO / "backend" / "api" / "routers" / "parlays.py",
        "enter-only",
    ),
}


def _copy_source(path: Path, marker: str) -> str:
    """The unparsed source of the f-string carrying `marker`.

    Read as SOURCE, not as a rendered string, for the same reason every other
    guard on these two sentences does: a rendered string cannot tell a sourced
    value from a typed one.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        rendered = ast.unparse(node)
        if marker in rendered and "combination book" in rendered:
            return rendered
    raise AssertionError(f"no census copy found in {path.name} for {marker!r}")


class TestBothSurfacesNameTheScope:
    def test_every_surface_names_the_series_the_forty_were_measured_on(self):
        for label, (path, marker) in SURFACES.items():
            source = _copy_source(path, marker)
            assert "COMBO_EXIT_CENSUS_SERIES" in source, (
                f"{label} states a census over 40 books without saying which "
                f"population they came from. A reader tapping a shard-1 "
                f"combination supplies the scope themselves, and it is wrong. "
                f"Registration §12.4."
            )

    def test_every_surface_says_the_shard_was_not_read(self):
        for label, (path, marker) in SURFACES.items():
            source = _copy_source(path, marker)
            assert "COMBO_EXIT_CENSUS_SHARD_SERIES" in source, (
                f"{label} does not name the shard the census did not reach."
            )
            assert "COMBO_EXIT_CENSUS_SHARD_BOOKS_READ" in source, (
                f"{label} names the shard without sourcing how many of its "
                f"books were read. Typing the zero is how the count and the "
                f"sentence drift apart."
            )

    def test_the_scope_clause_is_sourced_and_never_typed(self):
        """`KXMVECROSSCATEGORY-SHARD1` carries a digit.

        So typing it would either trip the existing bare-integer guards or
        force somebody to weaken them -- and weakening one is how "40 of 40"
        survived eleven days after the entry half was refuted. The series name
        must arrive through the constant.
        """
        for label, (path, marker) in SURFACES.items():
            source = _copy_source(path, marker)
            assert COMBO_EXIT_CENSUS_SHARD_SERIES not in source, (
                f"{label} types the shard series as a literal instead of "
                f"sourcing it from parlays.COMBO_EXIT_CENSUS_SHARD_SERIES."
            )
            for series in COMBO_EXIT_CENSUS_SERIES:
                assert series not in source, (
                    f"{label} types {series} as a literal."
                )
            # Same rule the sibling guards apply, restated here so this file
            # fails on its own if a digit is introduced by the scope clause.
            stripped = re.sub(r"ADR \d+(?:\s*§\s*[\d.]+)?", "ADR", source)
            assert not [c for c in stripped if c.isdigit()], (
                f"{label} carries a typed digit: {stripped}"
            )


class TestTheScopeClaimsOnlyWhatWasMeasured:
    """The clause has two ways to be wrong and neither is a digit."""

    def test_no_surface_implies_the_shard_was_measured(self):
        # Nothing has been read there, so no surface may use the vocabulary of
        # a completed measurement about it.
        forbidden = ("shard was read", "measured on the shard", "shard books had")
        for label, (path, marker) in SURFACES.items():
            source = _copy_source(path, marker).lower()
            for phrase in forbidden:
                assert phrase not in source, f"{label} implies a shard measurement"

    def test_no_surface_implies_the_shard_is_different(self):
        """The opposite error, and the easier one to make by accident.

        "unlike", "however", "but" after the census sentence all smuggle in a
        contrast that no data supports. Registration §11.3 forbids the screens
        hinting in either direction; the honest statement is that nothing is
        known there.
        """
        for label, (path, marker) in SURFACES.items():
            source = _copy_source(path, marker).lower()
            assert "nothing is known" in source, (
                f"{label} names the shard without saying that nothing is "
                f"known about it either way, which is the only claim the "
                f"record supports."
            )
            for phrase in ("unlike", "whereas", "may differ", "different there"):
                assert phrase not in source, (
                    f"{label} suggests the shard differs; nothing measured "
                    f"says so."
                )

    def test_the_constants_still_describe_the_record_they_summarise(self):
        """If a shard book is ever read this goes red, and it should.

        The copy says zero shard books were read. The day that stops being
        true, the sentence is stale on a real-money surface -- and stale
        reassurance is the failure mode this repo has been bitten by most.
        """
        assert COMBO_EXIT_CENSUS_SHARD_BOOKS_READ == 0
        assert COMBO_EXIT_CENSUS_BOOKS_READ == 40
        assert COMBO_EXIT_CENSUS_SHARD_SERIES == "KXMVECROSSCATEGORY-SHARD1"
        assert COMBO_EXIT_CENSUS_SERIES == (
            "KXMVESPORTSMULTIGAMEEXTENDED", "KXMVECROSSCATEGORY",
        )
