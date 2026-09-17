"""The hedge card says so when the stake is NOT Kalshi's own number, and
says nothing when it is.

Issue #53, answered A by Joe on 2026-09-16. ADR 0160 made `/api/hedge` resolve
each open position's stake at read time and serve `stake_basis` and
`stake_basis_reason` beside it; §5 of that ADR deliberately left both fields
off `frontend/src/lib/api.ts`, because nothing rendered them. Joe's answer
puts one line on the screen, so the fields are declared and this file is what
keeps the two halves honest. The amendment is in ADR 0160 itself, dated.

WHICH WAY ROUND, AND WHY IT IS THE WHOLE TEST
---------------------------------------------
Joe's principle: *a warning that fires only on the good case reads as a check
that passed.* So a `venue_fill` ticket -- the stake IS what Kalshi charged --
renders nothing extra, and an `as_recorded` ticket renders one line naming the
specific refusal. The inverse failure is real and recent: `ParlayCards`
rendered a note only when `anchored_on_sharp === true` and said nothing at all
when no sharp book backed the leg (fixed 2026-09-15). Neither direction is
allowed, so the render condition is pinned to the note's own presence rather
than to any comparison against a basis value in the component.

The sentence for an unknown reason is the second half of that rule. A code
this build predates must still produce a line, because a blank line is what
the good case looks like -- this is where the gloss parts company with
`suppressionGloss.ts`, where the code itself renders beside the sentence and a
null gloss loses nothing.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That any sentence is correct, or legible on a phone.** A wrong sentence
  passes here; the words are Joe's answer rendered by a session, not ratified
  copy.
- **That anything renders.** Source text and a node-executed function; no
  browser. `tests/test_hedge_positions.py` owns the payload the card reads.
- **Nothing about how often each reason fires.** The census that read the two
  prices against each other is spent (n = 12, one stratum) and no rate is
  computed anywhere in this change.
- **Nothing about the hedge figure's accuracy.** It carries at least four
  error terms of mixed sign (CLAUDE.md, E1-E4); naming whose price the stake
  is narrows none of the other three.

MUTATIONS, each applied to the guarded code and observed red on 2026-09-16
--------------------------------------------------------------------------
  1. delete the `no_venue_price` entry from `STAKE_BASIS_GLOSS`
  2. add a gloss for a reason `stake_basis_for` cannot return
  3. `stakeBasisNote` returns `null` for an unknown reason
  4. `stakeBasisNote` returns a sentence on `venue_fill`
  5. `stakeBasisNote` returns `null` when `basis` is missing altogether
  6. the card renders the line only when `stake_basis === "as_recorded"`
     (the `ParlayCards` defect, in its other direction)
  7. remove `<StakeBasisLine ...>` from the ticket
  8. remove the two field declarations from `api.ts`
  9. the fallback sentence swaps "not been checked" for a claim that the
     stake is the venue's

ISSUE #56 (answered A, 2026-09-17) -- the tenth refusal
-------------------------------------------------------
`stake_basis_for` used one reason for two different facts: a position whose
join key could not be formed (nothing was ever looked up -- a ticket Joe
recorded by hand) and one whose key WAS formed and matched nothing (a gap in
the books). Five of seventeen open positions were the first wearing the
second's sentence, so a genuine gap had nowhere to stand out. The count above
is now ten, and the `no_order_row` sentence is unchanged by design.

MUTATIONS for that split, each observed red on 2026-09-17
---------------------------------------------------------
 10. `stake_basis_for` drops the `_order_key` branch and returns
     `no_order_row` for both -- the pre-fix behaviour
 11. the `hand_recorded_position` entry is deleted from `STAKE_BASIS_GLOSS`
 12. the hand-recorded sentence is given wording that reports a search
 13. the `no_order_row` sentence is softened into the hand-recorded one --
     the sentence this ticket promises NOT to change
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from backend import hedge

ROOT = Path(__file__).resolve().parents[1]
HEDGE_PY = ROOT / "backend" / "hedge.py"
GLOSS_TS = ROOT / "frontend" / "src" / "lib" / "stakeBasisGloss.ts"
API_TS = ROOT / "frontend" / "src" / "lib" / "api.ts"
CARD = ROOT / "frontend" / "src" / "components" / "HedgePositions.tsx"

NODE = shutil.which("node")


def collapsed(path: Path) -> str:
    """`path`'s source with whitespace collapsed.

    Prettier wraps JSX and long string literals at 80 columns, and a guard
    that matches a phrase only when it fits on one line is a guard against
    short sentences (`tasks/lessons.md`, 2026-09-16, tenth).
    """
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def refusal_names() -> set[str]:
    """Every reason `stake_basis_for` (and `stake_bases`) can name.

    Read out of the source rather than by calling the function, because the
    set depends on which branch each input takes and two of the ten --
    `no_order_row` and `ambiguous_order_rows` -- are raised by different
    callers. Every one of them is written as a literal beside
    `STAKE_BASIS_AS_RECORDED`, which is the shape matched here, and grepping
    one function misses `ambiguous_order_rows` entirely.
    """
    source = HEDGE_PY.read_text(encoding="utf-8")
    found = set(re.findall(r'STAKE_BASIS_AS_RECORDED,\s*"([a-z_]+)"', source))
    assert found, "no refusal names could be read out of backend/hedge.py"
    return found


def glossed_names() -> set[str]:
    """The keys of the module's `STAKE_BASIS_GLOSS` map."""
    source = GLOSS_TS.read_text(encoding="utf-8")
    block = source.split("STAKE_BASIS_GLOSS: Record<string, string> = {", 1)[1]
    block = block.split("\n};", 1)[0]
    return set(re.findall(r"^  ([a-z_]+):", block, flags=re.MULTILINE))


def sentences() -> dict[str, str]:
    """Each refusal's sentence, as one line with its wrapping removed."""
    source = re.sub(r"\s+", " ", GLOSS_TS.read_text(encoding="utf-8"))
    block = source.split("STAKE_BASIS_GLOSS: Record<string, string> = {", 1)[1]
    block = block.split("};", 1)[0]
    return {
        name: text
        for name, text in re.findall(r'([a-z_]+): "((?:[^"\\]|\\.)*)"', block)
    }


class TestTheTwoVocabulariesMatch:
    """A refusal with no sentence renders as nothing on an unchecked ticket,
    and a sentence for a refusal the backend cannot produce is a claim about
    a system that is gone. Both directions, because they fail differently."""

    def test_every_refusal_the_backend_can_name_has_a_sentence(self):
        missing = sorted(refusal_names() - glossed_names())
        assert not missing, (
            f"`stake_basis_for` can refuse with {missing} and the card has no "
            "words for it; the ticket would fall through to the unnamed "
            "sentence with a bare code on it"
        )

    def test_every_sentence_names_a_refusal_the_backend_can_produce(self):
        stale = sorted(glossed_names() - refusal_names())
        assert not stale, (
            f"the card explains {stale}, which `stake_basis_for` no longer "
            "returns"
        )

    def test_there_are_ten_of_them(self):
        """The anchor. Both assertions above pass on two empty sets, which is
        also what a moved file or a broken regex produces.

        Nine was what ADR 0160 §3 decided, and the tenth arrived as a
        decision rather than a refactor: issue #56, answered A by Joe on
        2026-09-17, split `hand_recorded_position` out of `no_order_row`
        (ADR 0160, Amendment 2). An eleventh needs the same."""
        assert len(refusal_names()) == 10
        assert len(glossed_names()) == 10

    def test_the_good_case_is_spelled_the_same_on_both_sides(self):
        """The one string the card compares against. A typo here renders the
        caveat on every ticket, including the ones it is wrong about."""
        source = GLOSS_TS.read_text(encoding="utf-8")
        assert f'STAKE_BASIS_VENUE_FILL = "{hedge.STAKE_BASIS_VENUE_FILL}"' in source

    def test_the_payload_still_carries_the_two_fields(self):
        """Vacuity guard for the whole file: with the fields gone from the
        serialiser every ticket renders the unnamed sentence, and every
        assertion here still passes."""
        source = HEDGE_PY.read_text(encoding="utf-8")
        assert '"stake_basis": _optional(position, "stake_basis"),' in source
        assert (
            '"stake_basis_reason": _optional(position, "stake_basis_reason"),'
            in source
        )


class TestTheSentencesSayWhatTheyMay:
    """The words themselves, guarded rather than snapshotted: Joe has not
    ratified this wording, so what is pinned is what it must not say."""

    REFUSED = (
        "ceiling",
        "floor",
        "conservative",
        "at least",
        "can only be",
        "guaranteed",
        "exact",
    )

    def test_no_sentence_claims_a_direction_or_a_bound(self):
        """The same list `tests/test_hedge_positions.py` refuses around the
        lock figure. These sentences sit on the same card, under the same
        number, and the figure is an estimate pinned in neither direction."""
        for name, text in sentences().items():
            lowered = text.lower()
            for word in self.REFUSED:
                assert word not in lowered, (
                    f"the {name} sentence says {word!r} about a stake whose "
                    "own figure carries four error terms of mixed sign"
                )

    def test_no_sentence_calls_the_recorded_stake_wrong_or_right(self):
        """It is a different number from Kalshi's, and on eleven of the twelve
        rows the spent census joined it was the same number. The line says
        whose price it is, and claims nothing about the gap."""
        for name, text in sentences().items():
            lowered = text.lower()
            for word in ("wrong", "incorrect", "too high", "too low", "correct"):
                assert word not in lowered, f"the {name} sentence prices the gap"

    def test_each_sentence_is_one_short_line(self):
        """Small type under a money figure, read on a phone mid-game."""
        for name, text in sentences().items():
            assert len(text) <= 180, f"the {name} sentence is {len(text)} chars"
            assert text.endswith("."), f"the {name} sentence is not a sentence"

    def test_the_hand_recorded_line_does_not_report_a_search(self):
        """Issue #56. The whole point of the split is that only one of these
        two describes a lookup. A ticket with no join key was never looked
        for, so its line may not say that nothing matched -- that wording is
        what made five designed states read as five near-misses."""
        texts = sentences()
        assert "hand_recorded_position" in texts, (
            "the tenth refusal has no sentence; `stake_basis_for` can return "
            "it and the card would fall through to the unnamed line"
        )
        hand = texts["hand_recorded_position"].lower()
        for phrase in ("no kalshi order", "matches", "cannot be read"):
            assert phrase not in hand, (
                f"the hand-recorded sentence says {phrase!r}, which reports a "
                "lookup that never ran"
            )

    def test_the_missing_order_line_still_reads_like_a_bookkeeping_gap(self):
        """The sentence issue #56 deliberately did NOT touch. With the five
        false alarms moved off it, it fires only when the key WAS formed and
        the lookup found nothing, and that is a real gap -- so it has to keep
        saying a search came up empty rather than being softened into the
        hand-recorded one."""
        assert (
            "no kalshi order matches this ticket"
            in sentences()["no_order_row"].lower()
        )

    def test_the_unnamed_sentence_claims_only_that_nothing_was_checked(self):
        """Mutation 9. It is what renders when the reason is one this build
        has never heard of, so it may not assert which price the stake is --
        only that it was not checked against Kalshi's own record."""
        source = re.sub(r"\s+", " ", GLOSS_TS.read_text(encoding="utf-8"))
        unnamed = re.search(r'STAKE_BASIS_UNNAMED = "([^"]+)"', source)
        assert unnamed, "the unnamed-reason sentence could not be read"
        text = unnamed.group(1).lower()
        assert "not been checked" in text
        assert "kalshi" in text


class TestTheCardRendersOnTheNoteNotOnTheBasis:
    """Mutations 6 and 7 -- the `ParlayCards` defect, refused in both
    directions."""

    def test_the_ticket_renders_the_line(self):
        assert "<StakeBasisLine position={position} />" in collapsed(CARD)

    def test_the_component_never_compares_against_the_good_case(self):
        """A component that asked `stake_basis === "venue_fill"` (or its
        negation) would decide the asymmetry twice, and the second decision is
        the one that goes stale: an unresolved `null` basis would then render
        nothing, which is what a CHECKED ticket looks like. The comparison
        lives in `stakeBasisNote` and nowhere else."""
        source = CARD.read_text(encoding="utf-8")
        body = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
        body = re.sub(r"(?m)^\s*//.*$", "", body)
        for forbidden in ('"venue_fill"', '"as_recorded"', "stake_basis ="):
            assert forbidden not in body, (
                f"HedgePositions.tsx decides on {forbidden!r} itself; the "
                "asymmetry belongs to stakeBasisNote, which returns null for "
                "exactly one input"
            )
        assert "if (!note) return null;" in body

    def test_both_fields_are_declared_on_the_payload_type(self):
        """Mutation 8, and the reversal of ADR 0160 §5: a component renders
        them now, so `api.ts` declares them."""
        types = collapsed(API_TS)
        assert 'stake_basis: "venue_fill" | "as_recorded" | null;' in types
        assert "stake_basis_reason: string | null;" in types


_DRIVER = """
import { stakeBasisNote } from "./stakeBasisGloss.ts";
const args = JSON.parse(process.argv[2]);
console.log(JSON.stringify({ note: stakeBasisNote(args.basis, args.reason) }));
"""


def note_for(basis, reason):
    driver = GLOSS_TS.parent / "_laneC_stake_basis_driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    try:
        out = subprocess.run(
            [NODE, "--experimental-strip-types", str(driver),
             json.dumps({"basis": basis, "reason": reason})],
            capture_output=True,
            text=True,
            # Node writes UTF-8; without this Windows decodes with the ANSI
            # code page and an em dash comes back as U+FFFD.
            encoding="utf-8",
            timeout=60,
            cwd=str(GLOSS_TS.parent),
        )
    finally:
        driver.unlink(missing_ok=True)
    assert out.returncode == 0, f"node failed:\n{out.stdout}\n{out.stderr}"
    return json.loads(out.stdout.strip())["note"]


@pytest.mark.skipif(
    NODE is None,
    reason=(
        "node is not on PATH. Skipped rather than xfailed: the guard is real "
        "where node exists (CI and both dev machines)."
    ),
)
class TestTheAsymmetryIsExecuted:
    """Substring assertions pass unchanged on a function that is exactly
    inverted, and an inverted function here is the defect this exists to
    prevent. So it is run."""

    def test_a_checked_stake_says_nothing_extra(self):
        assert note_for("venue_fill", None) is None

    def test_every_refusal_produces_its_own_sentence(self):
        """Not a generic caveat: nine reasons, nine different lines."""
        seen = {name: note_for("as_recorded", name) for name in refusal_names()}
        assert all(seen.values()), (
            f"a refusal rendered nothing: {[k for k, v in seen.items() if not v]}"
        )
        assert len(set(seen.values())) == len(seen), (
            "two refusals render the same sentence, which is a generic caveat "
            "wearing nine names"
        )

    def test_an_unknown_reason_still_renders_and_carries_its_code(self):
        """Mutation 3. Null here would put a reason this build predates on the
        same blank row as a checked ticket."""
        note = note_for("as_recorded", "a_reason_from_2027")
        assert note is not None
        assert "a_reason_from_2027" in note

    def test_a_missing_basis_is_not_treated_as_a_checked_one(self):
        """Mutation 5, and the house rule: unreadable resolves to nothing
        plausible, and the plausible thing here is silence."""
        for basis in (None, "", "something_else"):
            assert note_for(basis, None) is not None

    def test_the_good_case_wins_over_a_stray_reason(self):
        """A `venue_fill` that somehow carries a reason string still says
        nothing: the stake IS the venue's number, and the reason column is
        the one that would be stale."""
        assert note_for("venue_fill", "no_venue_price") is None
