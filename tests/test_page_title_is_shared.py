"""Every page heading renders through one `PageTitle` component (#394).

Before this ticket, 14 `<h1>` tags across 10 files carried 5 different class
strings -- tabs one tap apart (Gate vs. Picks, Parlays vs. Games) wore
visibly different headlines. Now `frontend/src/components/PageTitle.tsx` is
the only file in `frontend/src` that writes a literal `<h1`, and it offers
at most two variants: `page` (every tab) and `detail` (a matchup heading on
`/market` and `/game`).

WHAT THIS ESTABLISHES
----------------------
(i)   No `<h1` appears anywhere under `frontend/src` except inside
      `PageTitle.tsx` itself.
(ii)  `PageTitle.tsx` defines at most two variants.
(iii) Every page this ticket's "Lane owns" names imports `PageTitle` and
      renders its heading through it, by name, so a page cannot satisfy (i)
      by hiding an h1 behind some other component instead.

WHAT THIS DOES NOT ESTABLISH
-----------------------------
- Rendering, layout, or mobile overflow at 390/1440 -- that is
  `scripts/check_mobile.py --shots` against a local build, run by hand.
- That the chosen sizes are the "right" ones -- only that there is one.

MUTATIONS, each observed red
-----------------------------
  1. put one raw `<h1 className="...">` back in `slate/page.tsx` -> (i).
  2. add a third entry to `PageTitle.tsx`'s variant map -> (ii).
"""

from __future__ import annotations

import re
from pathlib import Path

FRONTEND_SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"
PAGE_TITLE = FRONTEND_SRC / "components" / "PageTitle.tsx"

PAGES_USING_PAGE_TITLE = [
    FRONTEND_SRC / "app" / "bets" / "page.tsx",
    FRONTEND_SRC / "app" / "gate" / "page.tsx",
    FRONTEND_SRC / "app" / "login" / "page.tsx",
    FRONTEND_SRC / "app" / "market" / "[ticker]" / "page.tsx",
    FRONTEND_SRC / "app" / "parlays" / "page.tsx",
    FRONTEND_SRC / "app" / "picks" / "loading.tsx",
    FRONTEND_SRC / "app" / "picks" / "page.tsx",
    FRONTEND_SRC / "app" / "playbook" / "page.tsx",
    FRONTEND_SRC / "app" / "slate" / "page.tsx",
    FRONTEND_SRC / "components" / "GameHeader.tsx",
]


def _tsx_files() -> list[Path]:
    return sorted(FRONTEND_SRC.rglob("*.tsx"))


class TestNoRawH1OutsidePageTitle:
    def test_no_h1_anywhere_except_page_title_component(self):
        offenders = {}
        for path in _tsx_files():
            if path == PAGE_TITLE:
                continue
            text = path.read_text(encoding="utf-8")
            if "<h1" in text:
                offenders[str(path.relative_to(FRONTEND_SRC))] = text.count("<h1")
        assert offenders == {}

    def test_page_title_itself_renders_exactly_one_h1(self):
        text = PAGE_TITLE.read_text(encoding="utf-8")
        assert text.count("<h1") == 1


class TestAtMostTwoVariants:
    def test_variant_map_has_at_most_two_entries(self):
        text = PAGE_TITLE.read_text(encoding="utf-8")
        match = re.search(r"const VARIANTS = \{(.*?)\} as const;", text, re.DOTALL)
        assert match is not None
        entries = [
            line
            for line in match.group(1).splitlines()
            if ":" in line and line.strip() and not line.strip().startswith("//")
        ]
        assert len(entries) <= 2


class TestEveryOwnedPageRendersThroughPageTitle:
    def test_every_page_imports_and_uses_page_title(self):
        missing_import = []
        missing_use = []
        for path in PAGES_USING_PAGE_TITLE:
            text = path.read_text(encoding="utf-8")
            if '"@/components/PageTitle"' not in text:
                missing_import.append(str(path.relative_to(FRONTEND_SRC)))
            if "<PageTitle" not in text:
                missing_use.append(str(path.relative_to(FRONTEND_SRC)))
        assert missing_import == []
        assert missing_use == []
