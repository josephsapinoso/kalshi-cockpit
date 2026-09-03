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

**Where the sentence renders (ticket #16, Joe's answer 16A, 2026-09-02).**
The two *row* sites -- the Board's `SlateRow` and `/slate`'s own row -- keep
the code and no longer carry the sentence; beside the code is a link to the
game screen's skeptic section, where `SkepticPanel` captions the same code
from the same map. So the rule for a render site is now: gloss in place, OR
point at the place that does. The Ledger, the card and the disclosure at the
foot of `/slate` still gloss in place -- the ticket cut the row, not the
screen -- and the two row sites are pinned to the *other* branch, so a future
edit that quietly puts the paragraph back on the row goes red here.

**What this does not establish.** That any sentence is *correct*, that the two
lines are legible together, or that the layout survives a long composite
reason. A wrong sentence passes here. The behaviour of the splitting is
executed by node below rather than read, because a substring assertion passes
unchanged on a function that is exactly inverted. Nor that the link *lands*:
the market page's scroll-after-fetch is asserted as source, not driven in a
browser.
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
MARKET_PAGE = REPO / "frontend" / "src" / "app" / "market" / "[ticker]" / "page.tsx"
SKEPTIC_PANEL = REPO / "frontend" / "src" / "components" / "SkepticPanel.tsx"

NODE = shutil.which("node")


def without_comments(source: str) -> str:
    """The file with its comments removed. A docstring that quotes the old
    `glossSentence(rec.suppressed_reason)` line to explain its absence must
    neither satisfy nor break an assertion about what renders."""
    stripped = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", stripped, flags=re.MULTILINE)


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
        return rendered.search(without_comments(source)) is not None

    def test_the_slate_row_still_renders_the_raw_code(self):
        """The Board's row: the code, and a link to where it is explained.

        Ticket #16 (16A) took the sentence off this row. The code is still
        the row's content -- it is what `/api/suppression` counts -- and the
        thing beside it is now a pointer, not a paragraph. Mutation observed
        red both ways: put `glossSentence(rec.suppressed_reason)` back, or
        drop the `whyRefusedHref` link.
        """
        source = SLATE_ROW.read_text(encoding="utf-8")
        assert self._renders_raw_code(source, "rec"), (
            "SlateRow no longer renders the engine's own code. The link was "
            "permitted because it sits beside the code, not in place of it -- "
            "one rule, one name, and the explanation one tap away."
        )
        live = without_comments(source)
        assert "glossSentence(" not in live, (
            "SlateRow renders the gloss sentence on the row again. Ticket #16 "
            "(16A) moved it to the game screen; the row keeps the code and a "
            "link, and eleven rows of prose is what the ticket was opened for."
        )
        assert "whyRefusedHref(rec.ticker)" in live, (
            "SlateRow dropped the sentence without pointing at where it went. "
            "A beginner who cannot see why a row was refused cannot learn from "
            "the refusal -- the ticket's own words."
        )

    def test_the_card_still_renders_the_raw_code(self):
        source = CARD.read_text(encoding="utf-8")
        assert self._renders_raw_code(source, "rec")
        assert "glossSentence(rec.suppressed_reason)" in source

    def test_the_slate_page_still_renders_the_raw_code(self):
        """`/slate`'s own row, the screen the ticket measured. Same shape as
        the Board's row: code stays, sentence goes, link arrives. The
        disclosure at the foot of the same file still captions each counted
        code in place -- `glossSentence(reason)` -- and that is pinned too,
        because the ticket cut the row, not the screen.
        """
        source = SLATE_PAGE.read_text(encoding="utf-8")
        assert self._renders_raw_code(source, "row")
        live = without_comments(source)
        assert "glossSentence(row.suppressed_reason)" not in live, (
            "/slate renders the gloss sentence on every row again -- the "
            "state ticket #16 was opened to end."
        )
        assert "whyRefusedHref(row.ticker)" in live, (
            "/slate's row dropped the sentence without a link to where it went."
        )
        assert "glossSentence(reason)" in live, (
            "the suppression-count disclosure at the foot of /slate stopped "
            "captioning its codes. That is outside ticket #16, which cut the "
            "ROW; a per-code caption once per screen is not the prose it "
            "measured."
        )


class TestEveryRenderSiteIsGlossed:
    """**The third site was missed on the first pass, and only a running page
    found it.** `SlateRow` is the *Board's* compact row; `/slate` -- the screen
    Joe's phone habit actually goes through -- renders `suppressed_reason` from
    its own markup in `app/slate/page.tsx`. Two of three sites were glossed and
    the one that mattered most was not, which a component-by-component test
    written from the same wrong list would have called complete.

    So this asserts the *list* rather than its members: any file that renders
    the field must also explain it -- **in place, or by pointing at the game
    screen that does** (ticket #16, 16A). A fourth render site added later
    fails here instead of shipping a bare identifier with nowhere to go.
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

    #: The row sites ticket #16 cut. These must take the *pointer* branch and
    #: not the in-place one -- listed by name, because the scan below accepts
    #: either and would call a row that grew its paragraph back complete.
    POINT_AWAY = {"components/SlateRow.tsx", "app/slate/page.tsx"}

    @staticmethod
    def _explains(live: str) -> bool:
        return "glossSentence(" in live or "whyRefusedHref(" in live

    def test_every_file_that_renders_the_field_also_explains_it(self):
        src = REPO / "frontend" / "src"
        offenders = []
        for path in sorted(src.rglob("*.ts*")):
            rel = path.relative_to(src).as_posix()
            if rel in self.EXEMPT:
                continue
            live = without_comments(path.read_text(encoding="utf-8"))
            renders = re.search(
                r"(?:\?|\{)\s*\w+\.suppressed_reason\s*(?:\}|$)",
                live,
                re.MULTILINE,
            )
            if renders and not self._explains(live):
                offenders.append(rel)
        assert not offenders, (
            "These files render a suppression code with no plain English "
            f"beside it and no link to where it is explained: {offenders}. "
            "Either call glossSentence() there, link whyRefusedHref(), or add "
            "the file to EXEMPT with the reason."
        )

    def test_the_cut_rows_point_away_and_do_not_gloss_in_place(self):
        """The half the scan cannot see. It accepts either branch, so a row
        that carried BOTH the link and the sentence would pass it -- and that
        row is the ~12,000px screen the ticket measured, plus a link."""
        src = REPO / "frontend" / "src"
        for rel in sorted(self.POINT_AWAY):
            live = without_comments((src / rel).read_text(encoding="utf-8"))
            assert "whyRefusedHref(" in live, f"{rel} does not link to the game screen"
            in_place = re.search(r"glossSentence\(\s*\w+\.suppressed_reason\s*\)", live)
            assert not in_place, (
                f"{rel} glosses the row's own suppressed_reason in place again"
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


class TestTheProseLivesOnTheGameScreen:
    """The other end of the link. A row that says "why ->" and lands on a page
    that does not explain has deleted the provenance, which is the option Joe
    was offered and did NOT choose (ticket #16: relocated, not deleted).

    Three facts, each its own test because each fails for its own reason: the
    game screen mounts the skeptic panel; the panel captions refused codes
    from the same map the rows used to; and the link's fragment is the panel's
    actual `id`, read from the panel's source rather than assumed.
    """

    @staticmethod
    def _anchor() -> str:
        found = re.search(
            r'export const SKEPTIC_ANCHOR = "([a-z_-]+)"',
            GLOSS_TS.read_text(encoding="utf-8"),
        )
        assert found, "SKEPTIC_ANCHOR is no longer exported from suppressionGloss.ts"
        return found.group(1)

    def test_the_market_page_mounts_the_skeptic_panel(self):
        live = without_comments(MARKET_PAGE.read_text(encoding="utf-8"))
        assert "<SkepticPanel" in live, (
            "/market/[ticker] no longer mounts SkepticPanel, so the row's "
            "'why' link lands on a page with no explanation on it."
        )

    def test_the_skeptic_panel_captions_from_the_same_map(self):
        live = without_comments(SKEPTIC_PANEL.read_text(encoding="utf-8"))
        assert "glossSuppression(" in live, (
            "SkepticPanel stopped reading suppressionGloss.ts. The row's "
            "sentence moved here on the promise that it is the SAME sentence."
        )
        assert re.search(r"\{\s*gloss\s*\}", live), (
            "SkepticPanel computes the gloss and renders something else."
        )

    def test_the_links_fragment_is_the_panels_own_id(self):
        """Mutation observed red: rename the section's `id` -- the link then
        points at nothing and the page stays at the top."""
        anchor = self._anchor()
        panel = without_comments(SKEPTIC_PANEL.read_text(encoding="utf-8"))
        assert f'id="{anchor}"' in panel, (
            f"SkepticPanel has no element with id={anchor!r}, which is where "
            "whyRefusedHref() sends every refused row."
        )
        gloss_ts = GLOSS_TS.read_text(encoding="utf-8")
        href = gloss_ts.split("function whyRefusedHref", 1)[1]
        assert "#${SKEPTIC_ANCHOR}" in href, (
            "whyRefusedHref builds its fragment from something other than "
            "SKEPTIC_ANCHOR, so the constant this test reads is not the one "
            "the link uses."
        )

    def test_the_landing_scrolls_once_the_panel_exists(self):
        """The panel mounts after `fetchMarketDetail` resolves, and the
        browser's own fragment scroll fires at navigation -- before there is
        anything to scroll to. So the page must re-run it when `detail`
        arrives, and the effect that does so must depend on `detail` and on
        nothing narrower. Mutation observed red: change the dependency list
        to `[]`."""
        live = without_comments(MARKET_PAGE.read_text(encoding="utf-8"))
        assert "scrollIntoView" in live, (
            "/market/[ticker] never scrolls to the hash itself, so a 'why' "
            "link lands at the top of a page that says Loading."
        )
        effect_start = live.rfind("useEffect(", 0, live.index("scrollIntoView"))
        assert effect_start >= 0, "scrollIntoView is not inside a useEffect"
        effect = live[effect_start:]
        deps = re.search(r"\}, \[([^\]]*)\]\);", effect)
        assert deps and deps.group(1).strip() == "detail", (
            "the hash-scroll effect does not re-run when `detail` arrives, "
            f"its dependencies are [{deps.group(1) if deps else '?'}]"
        )
        assert "location.hash" in effect[: effect.index("scrollIntoView")], (
            "the effect scrolls to something other than the URL's own hash"
        )


_DRIVER = """
import { glossSuppression, glossSentence, whyRefusedHref } from "./suppressionGloss.ts";
const reason = JSON.parse(process.argv[2]);
console.log(JSON.stringify({
  codes: glossSuppression(reason),
  sentence: glossSentence(reason),
  href: whyRefusedHref("KX A/B"),
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

    def test_the_why_link_encodes_the_ticker_and_targets_the_skeptic(self):
        """Executed, not read: a ticker is user-facing data on a URL path, and
        the encoding is the one place a substring assertion could pass on a
        function that forgot it."""
        got = gloss_of("stale_odds")
        assert got["href"] == "/market/KX%20A%2FB#skeptic"
