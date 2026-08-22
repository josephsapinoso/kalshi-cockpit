"""The row-level gloss must cover the engine's whole vocabulary, and must add
to the code rather than replace it.

Two separate claims, tested separately because they fail for different reasons.

**Coverage.** `frontend/src/lib/suppressionGloss.ts` maps every `Check(...)`
name in `backend/core/suppression.py` to a sentence, in both directions. Same
lane as `tests/test_suppression_screen.py`, which pins the `/rejections`
screen's longer explanations — a rule added to the engine with no sentence here
renders on the Slate as a bare identifier, which is the state the gloss exists
to end, and a sentence naming a rule that no longer exists is a claim about a
system that is gone.

**Additivity.** `SlateRow`'s docstring refused a translation on the grounds
that it would give one rule two names. The gloss is allowed only because it
renders *beside* `rec.suppressed_reason`, not instead of it. That is a property
of the components, so it is asserted against their source: if a future edit
swaps the code out for the sentence, the argument that permitted the gloss
stops holding and this goes red.

**What this does not establish.** That any sentence is *correct*, that the two
lines are legible together, or that the layout survives a long composite
reason. A wrong sentence passes here. The behaviour of the splitting is
executed by node below rather than read, because a substring assertion passes
unchanged on a function that is exactly inverted.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SUPPRESSION = REPO / "backend" / "core" / "suppression.py"
SIZING = REPO / "backend" / "core" / "sizing.py"
ENGINE = REPO / "backend" / "engine.py"
GLOSS_TS = REPO / "frontend" / "src" / "lib" / "suppressionGloss.ts"
SLATE_ROW = REPO / "frontend" / "src" / "components" / "SlateRow.tsx"
CARD = REPO / "frontend" / "src" / "components" / "OpportunityCard.tsx"
SLATE_PAGE = REPO / "frontend" / "src" / "app" / "slate" / "page.tsx"

NODE = shutil.which("node")


def check_names() -> set[str]:
    """Every rule name the engine can write into `suppressed_reason`.

    Read out of the source rather than by calling `evaluate`, because the set
    depends on which branch each input takes -- `no_depth` and
    `insufficient_depth` are mutually exclusive at runtime and both are real.
    """
    source = SUPPRESSION.read_text(encoding="utf-8")
    return set(re.findall(r'Check\(\s*"([a-z_]+)"', source))


def glossed_codes() -> set[str]:
    """The keys of the module's `GLOSS` map."""
    source = GLOSS_TS.read_text(encoding="utf-8")
    block = source.split("const GLOSS", 1)[1].split("\n};", 1)[0]
    return set(re.findall(r"^  ([a-z_]+):", block, flags=re.MULTILINE))


def refusing_constraints() -> set[str]:
    """The `binding_constraint` values that can reach `suppressed_reason`.

    **Only the refusing ones.** `engine.py` writes the `sizing:` prefix under
    `if sizing.refused`, and `refused=True` is set in exactly one place --
    `_refuse`. So the reachable set is `_refuse`'s explicit `constraint=`
    arguments plus its default. The clamping constraints (`kelly`, `no_edge`,
    `max_position_dollars`, ...) live on non-refused results and never appear
    in this column; a sentence for one would describe a state that does not
    occur.
    """
    source = SIZING.read_text(encoding="utf-8")
    # `(?<!binding_)`: `binding_constraint="no_edge"` at `sizing.py:221` sits on
    # a `SizingResult` whose `refused` defaults to false, so it is a *clamp*
    # and never reaches this column. Without the lookbehind it does, and the
    # first version of this test demanded a sentence for a state that cannot
    # occur -- the mirror image of the failure the class exists to catch.
    named = set(re.findall(r'(?<!binding_)constraint="([a-z_]+)"', source))
    default = re.search(r'def _refuse\([^)]*constraint: str = "([a-z_]+)"', source)
    assert default, "the _refuse default constraint could not be read"
    # `binding_constraint=` assignments are on non-refused results.
    return named | {default.group(1)}


def sizing_glossed() -> set[str]:
    source = GLOSS_TS.read_text(encoding="utf-8")
    block = source.split("const SIZING_GLOSS", 1)[1].split(chr(10) + "};", 1)[0]
    return set(re.findall(r"^  ([a-z_]+):", block, flags=re.MULTILINE))


class TestTheSizerRefusalsAreGlossedToo:
    """**A second vocabulary shares this column and does not look like the
    first.** `backend/engine.py` writes `sizing:{binding_constraint}` when the
    sizer refused and no check fired, so a row can read
    `sizing:bankroll_unobserved` -- a string that is not a `Check` name and
    never will be. Pinning only `ALL_CHECK_NAMES` would call the gloss complete
    while an entire class of refusals rendered bare.
    """

    def test_the_prefix_is_still_what_the_engine_writes(self):
        """If `engine.py` stops writing `sizing:`, the prefix handling in the
        gloss is dead code and this whole class is about nothing."""
        assert 'f"sizing:{sizing.binding_constraint}"' in ENGINE.read_text(
            encoding="utf-8"
        )

    def test_the_sizer_defines_the_refusals_this_test_thinks_it_does(self):
        names = refusing_constraints()
        assert "bankroll_unobserved" in names
        assert "max_daily_loss_dollars" in names
        assert len(names) >= 5

    def test_every_reachable_sizer_refusal_has_a_sentence(self):
        missing = refusing_constraints() - sizing_glossed()
        assert not missing, (
            "These sizer refusals render as bare `sizing:` codes with no plain "
            f"English beside them: {sorted(missing)}."
        )

    def test_no_sentence_describes_a_refusal_that_cannot_happen(self):
        extra = sizing_glossed() - refusing_constraints()
        assert not extra, (
            "SIZING_GLOSS explains constraints that never reach "
            f"`suppressed_reason`: {sorted(extra)}. The clamping constraints "
            "live on non-refused results and are shown as 'Bound by' on the "
            "ticket, not as a suppression reason."
        )


class TestTheVocabulariesMatch:
    def test_the_engine_defines_the_rules_this_test_thinks_it_does(self):
        """A capture-style anchor: if the regex stops matching, say so loudly.

        Without this both sets could collapse to empty and agree perfectly,
        which is the shape of every vacuous test in this repo's history.
        """
        names = check_names()
        assert len(names) >= 9
        assert "suspicious_edge" in names
        assert "stale_odds" in names

    def test_the_gloss_map_parses(self):
        """Same anchor on the other side of the comparison."""
        codes = glossed_codes()
        assert len(codes) >= 9
        assert "suspicious_edge" in codes

    def test_every_engine_rule_has_a_sentence(self):
        missing = check_names() - glossed_codes()
        assert not missing, (
            "These suppression codes would render on the Slate as bare "
            f"identifiers with no plain English beside them: {sorted(missing)}. "
            "Add one line each to GLOSS in suppressionGloss.ts."
        )

    def test_no_sentence_names_a_rule_that_no_longer_exists(self):
        extra = glossed_codes() - check_names()
        assert not extra, (
            "suppressionGloss.ts explains rules the engine no longer has: "
            f"{sorted(extra)}. A sentence about a deleted rule is a claim "
            "about a system that is gone."
        )


class TestTheGlossIsAdditive:
    """The code must still render. This is the condition the gloss was allowed
    under, and it is a property of the components rather than of the map.

    **A bare count of `rec.suppressed_reason` does not work, and the first
    version of this test was decoration because of it.** Both components
    reference the field as a *condition* as well — `if (rec.suppressed_reason)`
    in SlateRow, `suppressed && rec.suppressed_reason &&` in the Card — so
    swapping the rendered code out for the sentence left the count non-zero and
    the guard green. Verified the way this repo verifies everything: by making
    that exact swap and watching it not fail.

    So the check is for the field in a *rendering* position — the value of a
    JSX expression container (`{rec.suppressed_reason}`) or a ternary branch
    (`? rec.suppressed_reason`), which is how the two files spell it. Both
    spellings are admitted rather than one pinned, so this stays a claim about
    what renders and not a formatting test. Comments are stripped first: a
    docstring describing the field must not satisfy it.
    """

    @staticmethod
    def _renders_raw_code(source: str, receiver: str) -> bool:
        rendered = re.compile(
            r"(?:\?|\{)\s*" + re.escape(receiver) + r"\.suppressed_reason\s*(?:\}|$)",
            re.MULTILINE,
        )
        without_comments = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
        without_comments = re.sub(
            r"^\s*//.*$", "", without_comments, flags=re.MULTILINE
        )
        return rendered.search(without_comments) is not None

    def test_the_slate_row_still_renders_the_raw_code(self):
        source = SLATE_ROW.read_text(encoding="utf-8")
        assert self._renders_raw_code(source, "rec"), (
            "SlateRow no longer renders the engine's own code. The gloss was "
            "permitted because it is a caption on the code, not a replacement "
            "for it -- one rule, one name, plus an explanation."
        )
        assert "glossSentence(rec.suppressed_reason)" in source

    def test_the_card_still_renders_the_raw_code(self):
        source = CARD.read_text(encoding="utf-8")
        assert self._renders_raw_code(source, "rec")
        assert "glossSentence(rec.suppressed_reason)" in source

    def test_the_slate_page_still_renders_the_raw_code(self):
        source = SLATE_PAGE.read_text(encoding="utf-8")
        assert self._renders_raw_code(source, "row")
        assert "glossSentence(row.suppressed_reason)" in source


class TestEveryRenderSiteIsGlossed:
    """**The third site was missed on the first pass, and only a running page
    found it.** `SlateRow` is the *Board's* compact row; `/slate` -- the screen
    Joe's phone habit actually goes through -- renders `suppressed_reason` from
    its own markup in `app/slate/page.tsx`. Two of three sites were glossed and
    the one that mattered most was not, which a component-by-component test
    written from the same wrong list would have called complete.

    So this asserts the *list* rather than its members: any file that renders
    the field must also call the gloss. A fourth render site added later fails
    here instead of shipping a bare identifier.
    """

    #: Every file under `frontend/src` is scanned; these need no gloss and say
    #: why. (`/rejections` and its own `EXPLAINED` map were deleted in the
    #: 2026-08-22 review -- the per-code counts now render on the Slate as a
    #: disclosure, captioned by the same glossSentence the rows use.)
    EXEMPT = {
        "lib/api.ts": "types and helpers, renders nothing",
        "lib/suppressionGloss.ts": "is the gloss",
        "components/CrewBubble.tsx": "quotes the code inside a sentence it writes itself",
    }

    def test_every_file_that_renders_the_field_also_glosses_it(self):
        src = REPO / "frontend" / "src"
        offenders = []
        for path in sorted(src.rglob("*.ts*")):
            rel = path.relative_to(src).as_posix()
            if rel in self.EXEMPT:
                continue
            source = path.read_text(encoding="utf-8")
            without_comments = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
            without_comments = re.sub(
                r"^\s*//.*$", "", without_comments, flags=re.MULTILINE
            )
            renders = re.search(
                r"(?:\?|\{)\s*\w+\.suppressed_reason\s*(?:\}|$)",
                without_comments,
                re.MULTILINE,
            )
            if renders and "glossSentence(" not in without_comments:
                offenders.append(rel)
        assert not offenders, (
            "These files render a suppression code with no plain English "
            f"beside it: {offenders}. Either call glossSentence() there or add "
            "the file to EXEMPT with the reason."
        )

    def test_the_scan_finds_the_sites_it_is_supposed_to_find(self):
        """The anchor. Without it an over-eager regex change makes the scan
        find nothing and pass perfectly."""
        src = REPO / "frontend" / "src"
        found = {
            path.relative_to(src).as_posix()
            for path in src.rglob("*.ts*")
            if re.search(
                r"(?:\?|\{)\s*\w+\.suppressed_reason\s*(?:\}|$)",
                path.read_text(encoding="utf-8"),
                re.MULTILINE,
            )
        }
        assert {
            "components/SlateRow.tsx",
            "components/OpportunityCard.tsx",
            "app/slate/page.tsx",
        } <= found, found


_DRIVER = """
import { glossSuppression, glossSentence } from "./suppressionGloss.ts";
const reason = JSON.parse(process.argv[2]);
console.log(JSON.stringify({
  codes: glossSuppression(reason),
  sentence: glossSentence(reason),
}));
"""


def gloss_of(reason):
    driver = GLOSS_TS.parent / "_gloss_driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    try:
        out = subprocess.run(
            [NODE, "--experimental-strip-types", str(driver), json.dumps(reason)],
            capture_output=True,
            text=True,
            # Node writes UTF-8; without this, Windows decodes with the ANSI
            # code page and an em dash comes back as U+FFFD.
            encoding="utf-8",
            timeout=60,
            cwd=str(GLOSS_TS.parent),
        )
    finally:
        driver.unlink(missing_ok=True)
    assert out.returncode == 0, f"node failed:\n{out.stdout}\n{out.stderr}"
    return json.loads(out.stdout.strip())


@pytest.mark.skipif(
    NODE is None,
    reason=(
        "node is not on PATH. Skipped rather than xfailed: the guard is real "
        "where node exists (CI and both dev machines)."
    ),
)
class TestTheSplittingIsExecuted:
    def test_a_single_code_gets_its_sentence(self):
        got = gloss_of("suspicious_edge")
        assert len(got["codes"]) == 1
        assert got["codes"][0]["code"] == "suspicious_edge"
        assert got["codes"][0]["gloss"]
        assert got["sentence"] == got["codes"][0]["gloss"]

    def test_a_composite_reason_is_split_on_the_comma(self):
        """`suppressed_reason` is comma-joined, and a `.includes()` on the whole
        string matches across the boundary. This is the repo's oldest re-learned
        fact about this field."""
        got = gloss_of("stale_odds,too_few_books")
        assert [c["code"] for c in got["codes"]] == ["stale_odds", "too_few_books"]
        assert all(c["gloss"] for c in got["codes"])

    def test_the_joined_sentence_does_not_use_a_comma(self):
        """The codes themselves are comma-joined, so a comma between sentences
        reads as another code."""
        got = gloss_of("stale_odds,too_few_books")
        assert "; " in got["sentence"]

    def test_an_unknown_code_glosses_to_null_and_not_to_a_guess(self):
        """A code this build has never heard of means the server is running a
        rule the frontend predates. Inventing wording would hide that; the
        house rule is that unreadable resolves to nothing."""
        got = gloss_of("a_rule_from_the_future")
        assert got["codes"] == [{"code": "a_rule_from_the_future", "gloss": None}]
        assert got["sentence"] is None

    def test_a_known_and_an_unknown_code_together_keep_the_known_sentence(self):
        got = gloss_of("stale_odds,a_rule_from_the_future")
        assert [c["gloss"] is None for c in got["codes"]] == [False, True]
        assert got["sentence"] and ";" not in got["sentence"]

    def test_a_sizer_refusal_is_glossed_through_its_prefix(self):
        """`sizing:` codes are not `Check` names and a flat lookup misses them
        all -- which is a whole class of rows rendering bare."""
        got = gloss_of("sizing:bankroll_unobserved")
        assert got["codes"][0]["code"] == "sizing:bankroll_unobserved"
        assert got["codes"][0]["gloss"]
        assert "balance" in got["sentence"]

    def test_a_clamping_constraint_is_not_glossed_as_a_refusal(self):
        """`max_exposure_dollars` clamps; it never reaches this column. If a
        sentence appeared for it, the map would be describing the ticket's
        'Bound by' field rather than a suppression reason."""
        got = gloss_of("sizing:max_exposure_dollars")
        assert got["codes"][0]["gloss"] is None
        assert got["sentence"] is None

    def test_a_bare_check_name_is_not_read_as_a_sizer_code(self):
        """The prefix branch must not swallow the ordinary vocabulary."""
        got = gloss_of("stale_odds")
        assert got["codes"][0]["gloss"]

    def test_no_reason_is_not_an_unknown_reason(self):
        for empty in (None, "", "   ", ","):
            got = gloss_of(empty)
            assert got["codes"] == [], empty
            assert got["sentence"] is None, empty
