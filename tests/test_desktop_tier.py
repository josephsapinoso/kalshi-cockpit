"""The desktop tier widens the data and never the prose.

ADR 0047: the shell gains `xl:`/`2xl:` caps so tables and card grids can use a
monitor, but a paragraph's measure is a readability constraint, not a layout
one — the same ~65ch at 320px and at 2560px. Before this, `WindowBanner` and
`SignalStrip` carried no width cap at all and already rendered ~134ch lines
inside the 1024px shell; a wider shell would have taken them to ~190ch.

**What this does not establish.** These are source-text assertions: they check
that every paragraph in the named files declares *a* `max-w-` cap, not that
the cap is the right size, that the rendered line actually breaks there, or
that a capped paragraph is legible. Only opening the page shows that. Files
not listed here are not covered — a new prose component starts uncovered.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"

PROSE_FILES = [
    SRC / "components" / "WindowBanner.tsx",
    SRC / "components" / "SignalStrip.tsx",
    SRC / "components" / "WindowSchedule.tsx",
    SRC / "components" / "HowToRead.tsx",
    SRC / "app" / "board" / "page.tsx",
]

# `<p className="...">` with a static string, or `<p className={`...`}` with a
# template literal. The className is always the first attribute in this
# codebase's paragraphs; the anchor test below fails if that stops being true.
P_TAG = re.compile(r"<p\s+className=(?:\"([^\"]*)\"|\{`([^`]*)`\})")


class TestProseKeepsItsMeasureAtEveryWidth:
    def test_the_pattern_still_matches_something_everywhere(self):
        """A regex that matches nothing passes vacuously; this pins that every
        listed file still contains at least one paragraph the guard can see."""
        for path in PROSE_FILES:
            matches = P_TAG.findall(path.read_text(encoding="utf-8"))
            if path.name == "HowToRead.tsx":
                continue  # its prose is a <ul>, asserted separately below
            assert matches, f"{path.name} has no <p className=...> the guard can read"

    def test_every_paragraph_declares_a_width_cap(self):
        for path in PROSE_FILES:
            text = path.read_text(encoding="utf-8")
            for match in P_TAG.finditer(text):
                classes = match.group(1) or match.group(2)
                assert "max-w-" in classes, (
                    f"{path.name}: an uncapped paragraph — at the xl shell "
                    f"this renders ~190 characters per line: <p "
                    f"className=\"{classes}\">"
                )

    def test_how_to_read_caps_its_list(self):
        text = (SRC / "components" / "HowToRead.tsx").read_text(encoding="utf-8")
        ul = re.search(r"<ul\s+className=\"([^\"]*)\"", text)
        assert ul is not None, "HowToRead no longer renders its list the guard reads"
        assert "max-w-" in ul.group(1), (
            "HowToRead's list is uncapped; it measured 132ch inside the old "
            "1024px shell before the cap."
        )


class TestTheChromeAndTheContentShareOneWidth:
    """Board shell, nav and footer import `SHELL_WIDTH` rather than repeating
    it. A board widened without its chrome hangs cards outside the nav rails,
    which reads as a bug at every width — and three copies of one decision
    held only as long as nobody edited one of them."""

    def test_all_three_import_the_constant(self):
        for path in (
            SRC / "app" / "board" / "page.tsx",
            SRC / "components" / "Nav.tsx",
            SRC / "components" / "Footer.tsx",
        ):
            text = path.read_text(encoding="utf-8")
            assert 'from "@/lib/shell"' in text, f"{path.name} does not import shell.ts"
            assert "SHELL_WIDTH" in text
            assert "max-w-5xl" not in text, (
                f"{path.name} still carries its own width literal beside the "
                f"shared one — the drift this constant exists to prevent"
            )

    def test_the_constant_is_one_complete_literal(self):
        """Tailwind v4 finds classes by scanning for complete literals; a
        width assembled from fragments compiles to nothing, silently."""
        text = (SRC / "lib" / "shell.ts").read_text(encoding="utf-8")
        assert '"mx-auto w-full max-w-5xl xl:max-w-[84rem] 2xl:max-w-[96rem]"' in text.replace("\n  ", " ")


class TestTheRailIsALayoutAndNotAReordering:
    """At xl the Board's context (banner, schedule, refresh panel) moves into
    a right-hand rail. The move is done with grid column assignment only, so
    below xl the DOM renders in the exact order the phone-first design chose:
    banner, schedule, panel, then the evidence column. A reordering would be a
    UX change smuggled in as a layout change."""

    def test_the_phone_reading_order_is_unchanged_in_the_dom(self):
        page = (SRC / "app" / "board" / "page.tsx").read_text(encoding="utf-8")
        sequence = [
            "<WindowBanner",
            "<WindowSchedule",
            "<RefreshOddsPanel",
            "<SignalStrip",
            "<LiveBoard",
            "The rest of the slate",
            "<HowToRead",
        ]
        positions = [page.index(token) for token in sequence]
        assert positions == sorted(positions), (
            "the Board's DOM order changed; the rail must move blocks with "
            "grid column assignment, never by reordering the source"
        )

    def test_the_rail_is_assigned_to_the_second_column_at_xl_only(self):
        page = (SRC / "app" / "board" / "page.tsx").read_text(encoding="utf-8")
        assert "xl:grid-cols-[minmax(0,1fr)_24rem]" in page
        rail = page.index("xl:col-start-2")
        main = page.index("xl:col-start-1")
        assert rail < main, (
            "the rail block must come first in the DOM (it is the phone's "
            "banner-first order) and be *assigned* to column 2, not moved there"
        )
        # Both blocks share row 1, or the grid stacks them and the rail
        # becomes a full-width band above the cards at xl.
        assert page.count("xl:row-start-1") == 2

    def test_the_wide_main_column_can_shrink(self):
        """`minmax(0,1fr)` + `min-w-0`: without the min-width release, one
        long unbroken string in a card would widen the whole column past the
        shell and push the rail off-screen."""
        page = (SRC / "app" / "board" / "page.tsx").read_text(encoding="utf-8")
        assert 'className="min-w-0 xl:col-start-1 xl:row-start-1"' in page


class TestTheTicketIsADialogOnADesktop:
    """`TicketSheet` is a bottom sheet: `fixed inset-0` with a `w-full` panel.
    On a 2560px monitor that rendered a monitor-wide filled Confirm on the
    order path — the largest, brightest control in the app, on the one screen
    that spends money. From `lg` it becomes a centred, width-capped dialog.
    `check_mobile` cannot see any of this: the sheet mounts on a tap."""

    def test_the_panel_is_width_capped_and_centred_from_lg(self):
        sheet = (SRC / "components" / "TicketSheet.tsx").read_text(encoding="utf-8")
        assert "lg:items-center" in sheet and "lg:justify-center" in sheet
        assert "lg:max-w-xl" in sheet, "the panel is monitor-wide again at lg"

    def test_the_drag_handle_is_a_phone_affordance(self):
        sheet = (SRC / "components" / "TicketSheet.tsx").read_text(encoding="utf-8")
        assert "lg:hidden" in sheet

    def test_the_scroll_lock_does_not_jump_the_page(self):
        """The sheet sets `body.overflow = hidden` while open; without a
        reserved gutter a desktop scrollbar vanishes and the page shifts
        sideways on every open."""
        css = (SRC / "app" / "globals.css").read_text(encoding="utf-8")
        assert "scrollbar-gutter: stable" in css


class TestTheRecordsHiddenFactorsReachTheSlate:
    """`anchored_on_sharp` and `market_width` were typed, serialised, and
    rendered nowhere. The first says whether the devig fell back to soft books
    (every actionable row ever recorded was such a fallback); the second says
    whether the books' own disagreement drowns the edge. Source assertions
    only — the arithmetic of `Width` is one multiply and one compare."""

    def test_the_slate_row_renders_both(self):
        slate = (SRC / "app" / "slate" / "page.tsx").read_text(encoding="utf-8")
        assert "row.anchored_on_sharp" in slate
        assert "row.market_width" in slate

    def test_a_missed_join_is_a_dash_and_never_a_default(self):
        """`null` means the join missed; `false`/`0` are real measured states.
        The recurring 'zero that means no measurement' must not come back
        through the two newest columns."""
        slate = (SRC / "app" / "slate" / "page.tsx").read_text(encoding="utf-8")
        for fn in ("function Anchor(", "function Width("):
            body = slate.split(fn, 1)[1].split("\n}\n", 1)[0]
            assert "null" in body and "undefined" in body
            assert "—" in body

    def test_the_soft_fallback_wears_the_warning_ink(self):
        slate = (SRC / "app" / "slate" / "page.tsx").read_text(encoding="utf-8")
        anchor = slate.split("function Anchor(", 1)[1].split("\n}\n", 1)[0]
        fallback = anchor.split("return (", 2)[2]
        assert "text-accent-2" in fallback, (
            "the soft-fallback state renders muted; it is the one factor that "
            "invalidates the edge's reference class and must read as a warning"
        )
