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


def classification_source() -> str:
    """The page's `COULD_NOT_FIRE` / `DID_NOT_FIRE` / `classify` / `BADGE` block.

    Lifted whole, from the first map to the component, for the same reason the
    derivation is: `classify` is where "could not fire" stops being a sentence
    and becomes a branch, and a test that regexed for the string `could not
    fire` would pass on a page that renders one badge for every zero.
    """
    source = SCREEN.read_text(encoding="utf-8")
    start = source.index("const COULD_NOT_FIRE")
    end = source.index("export default async function")
    return source[start:end]


def header_source() -> str:
    """The page's own `statuses` / `countOf` lines, which drive the header strip.

    Lifted rather than retyped for the reason the rest is: the header counter
    that used to read `Never fired: 6` is the defect in one number, and a
    harness that recomputed it from the maps would go green on a page whose
    header still counted six. The counters must come from `classify`.
    """
    source = SCREEN.read_text(encoding="utf-8")
    start = source.index("  const statuses = entries.map")
    end = source.index(";", source.index("  const countOf =")) + 1
    return source[start:end]


def _run(program: str) -> object:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on PATH, so the page's derivation cannot be run")

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "derivation.ts")
        Path(path).write_text(program, encoding="utf-8")
        done = subprocess.run(
            [node, path], capture_output=True, text=True, timeout=120
        )
    assert done.returncode == 0, f"the page's derivation did not run:\n{done.stderr}"
    return json.loads(done.stdout)


def _page_program(counts: dict[str, int], tail: str) -> str:
    """Every lifted fragment, in the order the page declares it, plus `tail`.

    `classify` is a hoisted function declaration but the maps it closes over are
    `const`, so the classification block has to precede the row derivation here
    exactly as it does on the page.
    """
    return "\n".join(
        [
            f"const suppression = {{ counts: {json.dumps(counts)} }};",
            derivation_source(),
            classification_source(),
            header_source(),
            tail,
        ]
    )


def render_rows(counts: dict[str, int]) -> list[tuple[str, int]]:
    """What the page would put in its `<ol>` for this `/api/suppression` body.

    Run as TypeScript by Node, which strips the annotations -- so the page's
    real expressions execute, types and all, with nothing rewritten by hand.
    """
    rows = _run(_page_program(counts, "console.log(JSON.stringify(entries));"))
    return [(name, count) for name, count in rows]  # type: ignore[misc]


def render_statuses(counts: dict[str, int]) -> dict[str, dict]:
    """`{check: {kind, reason?}}` -- what badge each row would carry."""
    rows = _run(
        _page_program(
            counts,
            "console.log(JSON.stringify(Object.fromEntries("
            "entries.map(([name, count], i) => [name, statuses[i]]))));",
        )
    )
    return rows  # type: ignore[return-value]


def render_header(counts: dict[str, int]) -> dict[str, int]:
    """The four counters in the page's header strip, computed by the page."""
    rows = _run(
        _page_program(
            counts,
            "console.log(JSON.stringify({"
            'fired: countOf("fired"),'
            'could_not_fire: countOf("could_not_fire"),'
            'did_not_fire: countOf("did_not_fire"),'
            'unclassified: countOf("unclassified"),'
            'classification_stale: countOf("classification_stale"),'
            "}));",
        )
    )
    return rows  # type: ignore[return-value]


def classified() -> tuple[set[str], set[str]]:
    """The keys of the two classification maps, read off the page source."""
    block = classification_source()

    def keys(name: str) -> set[str]:
        body = block.split(f"const {name}", 1)[1].split("\n};", 1)[0]
        return set(re.findall(r"^  ([a-z_]+):", body, flags=re.MULTILINE))

    return keys("COULD_NOT_FIRE"), keys("DID_NOT_FIRE")


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


# ---------------------------------------------------------------------------
# "Could not fire" is not "did not fire"
# ---------------------------------------------------------------------------

# The record the classification is read off. Named once so a test that pretends
# to check the four unreachable rules cannot quietly check three.
COULD_NOT_FIRE_ON_THE_RECORD = {
    "stale_kalshi_quote",
    "no_commence_time",
    "commence_skew",
    "inconsistent_consensus_metadata",
}
QUIET_ON_THE_RECORD = {"wide_market", "no_depth"}

# The payload as `/api/suppression` served it for the pinned pull: one rule
# doing nearly all the refusing, and the six that refused nothing absent.
RECORD_COUNTS = {"stale_odds": 859, "too_few_books": 245, "no_market_width": 18}


class TestTheTwoKindsOfZeroAreToldapart:
    """Six checks fired zero times and the screen badged all six the same way.

    Four of them **could not fire**: `stale_kalshi_quote`'s input is 0 on 1,564
    of 1,564 rows, `no_commence_time` is unreachable downstream of the linker,
    `commence_skew`'s limit is exactly the tolerance the linker already
    enforced, and `inconsistent_consensus_metadata` was never deployed. Two --
    `wide_market` and `no_depth` -- were evaluated on live denominators and
    refused nothing. Pooling those is the same error ADR 0021 S10 is criticised
    for, and it shipped on this screen in `ebd6c6f`.

    **What this does not establish.** It runs `classify`, not the render: that
    a row is classified `could_not_fire` says nothing about whether its badge
    reaches the DOM. The JSX is covered by `npx tsc --noEmit` and by eye. Nor
    does it check that any *reason* is true -- a wrong citation passes here, and
    only re-reading the cited line catches it.
    """

    def test_the_classification_extraction_still_finds_the_maps(self):
        """Loud rather than vacuous: without this, empty sets agree perfectly."""
        lifted = classification_source()
        assert "const COULD_NOT_FIRE" in lifted
        assert "const DID_NOT_FIRE" in lifted
        assert "function classify" in lifted
        # The header counters must be the page's own, computed off `classify`.
        # Recomputing them in the harness would go green on a page whose header
        # still said `Never fired: 6`, which is the defect being fixed.
        header = header_source()
        assert "classify(name, count)" in header
        assert "countOf" in header
        could_not, did_not = classified()
        assert could_not == COULD_NOT_FIRE_ON_THE_RECORD
        assert did_not == QUIET_ON_THE_RECORD

    @pytest.mark.parametrize("name", sorted(COULD_NOT_FIRE_ON_THE_RECORD))
    def test_a_rule_that_could_not_fire_says_so(self, name):
        status = render_statuses(RECORD_COUNTS)[name]
        assert status["kind"] == "could_not_fire", (
            f"{name} was never in a position to refuse anything, and the screen "
            f"renders its zero as {status['kind']} -- which reads as a working "
            f"guard."
        )

    @pytest.mark.parametrize("name", sorted(QUIET_ON_THE_RECORD))
    def test_a_rule_that_was_asked_and_said_no_says_that_instead(self, name):
        status = render_statuses(RECORD_COUNTS)[name]
        assert status["kind"] == "did_not_fire"

    def test_the_two_zeros_are_different_states_and_not_just_different_prose(self):
        """The point of the whole change: one badge became two kinds."""
        statuses = render_statuses(RECORD_COUNTS)
        kinds = {statuses[n]["kind"] for n in COULD_NOT_FIRE_ON_THE_RECORD}
        quiet = {statuses[n]["kind"] for n in QUIET_ON_THE_RECORD}
        assert len(kinds) == 1 and len(quiet) == 1
        assert kinds.isdisjoint(quiet)

    def test_the_header_reports_two_working_guards_not_six(self):
        """`Never fired: 6` was the defect in one number."""
        header = render_header(RECORD_COUNTS)
        assert header["could_not_fire"] == 4
        assert header["did_not_fire"] == 2
        assert header["fired"] == 3
        assert header["classification_stale"] == 0

    @pytest.mark.parametrize("name", sorted(COULD_NOT_FIRE_ON_THE_RECORD))
    def test_every_could_not_fire_reason_cites_where_it_rests(self, name):
        """A bare assertion that a rule cannot fire is worth nothing.

        Each one has to name the line or the document a future session can
        re-check in thirty seconds -- a `file.py:NN`, an ADR, or `tasks/NEXT.md`.
        """
        reason = render_statuses(RECORD_COUNTS)[name]["reason"]
        assert re.search(r"\.py:\d+|ADR \d{4}|tasks/NEXT\.md", reason), (
            f"{name}'s reason cites nothing checkable: {reason!r}"
        )

    @pytest.mark.parametrize("name", sorted(QUIET_ON_THE_RECORD))
    def test_every_quiet_reason_carries_its_denominator(self, name):
        """A zero with no denominator beside it is the unreadable case."""
        reason = render_statuses(RECORD_COUNTS)[name]["reason"]
        assert re.search(r"\d{1,3},\d{3}", reason), (
            f"{name} is called genuinely quiet with no count of how many rows "
            f"it was evaluated on: {reason!r}"
        )

    def test_a_rule_on_neither_list_is_still_the_open_question(self):
        """A rule added tomorrow must land in `unclassified`, not in either
        answered bucket. Silence about a rule nobody has looked at is the
        honest output; guessing is not."""
        statuses = render_statuses({})
        assert statuses["too_few_books"]["kind"] == "unclassified"
        assert statuses["insufficient_depth"]["kind"] == "unclassified"

    def test_a_rule_recorded_as_unable_to_fire_that_fires_is_flagged_loudly(self):
        """The classification is read off a pinned pull, so it can go stale.

        The failure that matters is a sentence saying "this cannot fire" sitting
        beside a count proving it did. The page must say the sentence is wrong,
        not print both and let the reader choose.
        """
        statuses = render_statuses({"commence_skew": 3})
        assert statuses["commence_skew"]["kind"] == "classification_stale"
        assert "out of date" in statuses["commence_skew"]["reason"]
        header = render_header({"commence_skew": 3})
        assert header["classification_stale"] == 1
        assert header["could_not_fire"] == 3

    def test_a_quiet_rule_that_starts_firing_is_just_a_fired_rule(self):
        """No alarm here: `wide_market` firing is the guard working. Only the
        `could_not_fire` claim is falsifiable by a count."""
        statuses = render_statuses({"wide_market": 7})
        assert statuses["wide_market"]["kind"] == "fired"

    def test_the_classification_only_names_rules_the_engine_has(self):
        """A reason attached to a rule that no longer exists renders nowhere and
        reads, in the source, as documentation of live behaviour."""
        could_not, did_not = classified()
        assert (could_not | did_not) <= check_names()

    def test_the_two_classification_maps_are_disjoint(self):
        """A rule cannot both be unable to fire and have been asked."""
        could_not, did_not = classified()
        assert not (could_not & did_not)
