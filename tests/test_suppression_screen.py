"""The Rejections screen must speak the engine's vocabulary.

`/api/suppression` counts rules by the `Check` names in
`backend/core/suppression.py`, and the screen renders one explanation per code.
Nothing connects the two files, so the ordinary failure is silent: someone adds
a rule, it starts dominating the counts, and the one screen built to say *which
check is killing everything* renders it as a bare identifier with a sentence
saying no explanation is recorded.

**What this does not establish.** It checks the vocabularies match, not that any
explanation is correct or current. A wrong sentence passes here.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SUPPRESSION = ROOT / "backend" / "core" / "suppression.py"
SCREEN = ROOT / "frontend" / "src" / "app" / "rejections" / "page.tsx"


def check_names() -> set[str]:
    """Every rule name the engine can write into `suppressed_reason`.

    Read out of the source rather than by calling `evaluate`, because the set
    depends on which branch each input takes -- `no_depth` and
    `insufficient_depth` are mutually exclusive at runtime and both are real.
    """
    source = SUPPRESSION.read_text(encoding="utf-8")
    return set(re.findall(r'Check\(\s*"([a-z_]+)"', source))


def explained_codes() -> set[str]:
    """The keys of the screen's `EXPLAINED` map."""
    source = SCREEN.read_text(encoding="utf-8")
    block = source.split("const EXPLAINED", 1)[1].split("\n};", 1)[0]
    return set(re.findall(r"^  ([a-z_]+):", block, flags=re.MULTILINE))


class TestTheScreenExplainsEveryRule:
    def test_the_engine_defines_the_rules_this_test_thinks_it_does(self):
        """A capture-style anchor: if the regex stops matching, say so loudly.

        Without this the two sets could both collapse to empty and agree
        perfectly, which is the shape of every vacuous test in this repo's
        history.
        """
        names = check_names()
        assert len(names) >= 9
        assert "suspicious_edge" in names
        assert "stale_odds" in names

    @pytest.mark.parametrize("name", sorted(check_names()))
    def test_every_rule_has_an_explanation_on_the_screen(self, name):
        assert name in explained_codes(), (
            f"{name} fires in the engine and the Rejections screen has no "
            f"sentence for it, so it renders as a bare identifier."
        )

    def test_the_screen_explains_nothing_the_engine_cannot_emit(self):
        """An explanation for a rule that no longer exists is a lie with a
        long shelf life -- it reads as documentation of live behaviour."""
        assert explained_codes() <= check_names()


# ---------------------------------------------------------------------------
# The rules that fired ZERO times
# ---------------------------------------------------------------------------


def derivation_source() -> str:
    """The page's own row-list derivation, lifted verbatim so it can be RUN.

    Regex-matching the source for an identifier would pass on a file that
    happens to mention `ALL_CHECKS` and renders nothing with it. Lifting the
    real expressions and executing them tests the behaviour instead: the only
    thing the harness supplies is the payload.

    Three fragments, in the order the page declares them -- the `EXPLAINED` map
    (which is the vocabulary, pinned to `ALL_CHECK_NAMES` by the class above),
    the `ALL_CHECKS` line derived from it, and the block from `fired` to
    `largest`. If any anchor stops matching this raises rather than silently
    testing an empty program; `test_the_extraction_still_finds_the_derivation`
    is the loud version of that.
    """
    source = SCREEN.read_text(encoding="utf-8")

    explained = "const EXPLAINED" + source.split("const EXPLAINED", 1)[1].split(
        "\n};", 1
    )[0] + "\n};"

    all_checks = next(
        line for line in source.splitlines() if line.startswith("const ALL_CHECKS")
    )

    start = source.index("  const fired =")
    end = source.index(";", source.index("  const largest =")) + 1

    return "\n".join([explained, all_checks, source[start:end]])


def render_rows(counts: dict[str, int]) -> list[tuple[str, int]]:
    """What the page would put in its `<ol>` for this `/api/suppression` body.

    Run as TypeScript by Node, which strips the annotations -- so the page's
    real expressions execute, types and all, with nothing rewritten by hand.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on PATH, so the page's derivation cannot be run")

    program = (
        f"const suppression = {{ counts: {json.dumps(counts)} }};\n"
        f"{derivation_source()}\n"
        "console.log(JSON.stringify(entries));\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "derivation.ts")
        Path(path).write_text(program, encoding="utf-8")
        done = subprocess.run(
            [node, path], capture_output=True, text=True, timeout=120
        )
    assert done.returncode == 0, f"the page's derivation did not run:\n{done.stderr}"
    return [(name, count) for name, count in json.loads(done.stdout)]


class TestTheScreenShowsTheRulesThatFiredNothing:
    """A check that has never fired is invisible on the screen built to say
    which check refused everything.

    `/api/suppression` groups over rows that carry a reason, so a rule that
    refused nothing has no key in the payload at all. The page iterated the
    payload, so six of the twelve declared checks -- `stale_kalshi_quote`,
    `no_commence_time`, `commence_skew`, `no_depth`, `wide_market` and
    `inconsistent_consensus_metadata`, zero fires each across 1,564 recorded
    rows -- could not be seen here, and neither could the fact that they were
    zero. A guard that has never fired is an assumption, not a guard, and the
    screen has to show one to raise the question.

    **What this does not establish.** It runs the derivation, not the render:
    that the twelve rows are *computed* says nothing about whether they reach
    the DOM, and nothing here checks the badge, the wording or the styling.
    There is no JS test runner in this repo, so the JSX below the derivation is
    covered by `npx tsc --noEmit` and by eye, and by nothing else.
    """

    def test_the_extraction_still_finds_the_derivation(self):
        """Both halves must be present, or every assertion below is vacuous."""
        lifted = derivation_source()
        assert "const ALL_CHECKS" in lifted
        assert "const fired" in lifted
        assert "const entries" in lifted

    def test_every_declared_rule_renders_even_when_it_never_fired(self):
        """The whole point: twelve rows out, from a payload naming one."""
        rendered = dict(render_rows({"stale_odds": 859}))
        missing = explained_codes() - set(rendered)
        assert not missing, (
            f"{sorted(missing)} fired zero times and the screen would not list "
            f"them, so the one page that says which check refused everything "
            f"cannot say that these refused nothing."
        )
        assert rendered["stale_odds"] == 859

    def test_a_rule_that_did_not_fire_renders_as_zero_not_as_absent(self):
        rendered = dict(render_rows({"stale_odds": 859}))
        assert rendered["wide_market"] == 0
        assert rendered["no_depth"] == 0

    def test_an_empty_payload_still_lists_every_rule(self):
        """`{}` is "nothing was rejected", not "there are no rules"."""
        rendered = dict(render_rows({}))
        assert set(rendered) == explained_codes()
        assert set(rendered.values()) == {0}

    def test_the_counted_rules_keep_the_order_the_server_sorted_them_into(self):
        """`suppression_summary` sorts descending, and that order is the finding.

        Zero-filling must append, not merge-and-resort: a page that re-sorted
        would be re-deciding server-side analysis on the client.
        """
        rendered = render_rows({"stale_odds": 859, "too_few_books": 245})
        assert rendered[0] == ("stale_odds", 859)
        assert rendered[1] == ("too_few_books", 245)
        assert all(count == 0 for _, count in rendered[2:])

    def test_a_code_the_engine_can_emit_outside_the_check_vocabulary_survives(self):
        """`engine.py` also writes `sizing:{constraint}`, and `review.py` its own
        tags. Zero-filling from the vocabulary must not drop what the payload
        actually carried -- an unexplained rule firing is still a rule firing."""
        rendered = dict(render_rows({"sizing:max_position": 4}))
        assert rendered["sizing:max_position"] == 4
        assert explained_codes() <= set(rendered)
