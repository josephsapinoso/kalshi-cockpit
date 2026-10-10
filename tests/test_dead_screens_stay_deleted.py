"""The four dead screens stay deleted -- #342, Joe's answer A, 2026-10-09.

`/board` (Refusals), `/ledger` (Evidence), `/estimate` (Estimates) and
`/dashboards` were removed from the frontend, along with the components only
they imported and the two Next proxies (`/log-estimate`, `/revise-estimate`)
only `/estimate` called. The reasons, for the session that wants one back:

- `/board` streams nothing on live by construction (`review_retired` zeroes
  every row, so the QuoteHub subscribes to nothing) and drew the engine's
  edge in green, the claim ADR 0071 forbids.
- `/ledger` was the dry engine's record at "0 / 300".
- `/estimate` recorded a study stopped 2026-08-20, and its copy contradicted
  ADR 0131.
- `/dashboards` returned 503 on live.

**What this establishes.** No `app/` directory, component file or lib file
named below exists, and no file under `frontend/src` imports one of the
components or the helper. It also pins the footer to Gate and Playbook.

**What it does not establish.** Every `/api/*` route those screens read
still exists and still answers (a separate ticket, #347, removes dead routes
later); nothing here says those routes are right, only that no page reads
them. A successor screen under any of these names needs its own decision --
this test is meant to be edited then, in the same commit, with the reason.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"

DEAD_APP_DIRS = ("board", "ledger", "estimate", "dashboards")
DEAD_PROXY_DIRS = ("log-estimate", "revise-estimate")

DEAD_COMPONENTS = (
    "LiveBoard",
    "OpportunityCard",
    "TicketSheet",
    "TicketProvider",
    "WindowBanner",
    "WindowSchedule",
    "HowToRead",
    "SlateRow",
)
DEAD_FILES = tuple(f"components/{name}.tsx" for name in DEAD_COMPONENTS) + (
    "lib/liveSizing.ts",
)

#: An import (or re-export) whose module specifier ends in a deleted name.
#: Matches `from "@/components/LiveBoard"`, `from "./SlateRow"`,
#: `from "@/lib/liveSizing"` and the bare `import "..."` form.
_DEAD_MODULES = "|".join((*DEAD_COMPONENTS, "liveSizing"))
IMPORT_OF_DEAD = re.compile(
    r"""(?:from|import)\s*["'][^"']*/(?:%s)(?:\.tsx?)?["']""" % _DEAD_MODULES
)


def _live(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


class TestTheDeadScreensStayDeleted:
    def test_the_four_page_directories_are_gone_and_no_deleted_component_is_imported(
        self,
    ):
        assert SRC.is_dir(), SRC
        risen = [
            f"app/{name}"
            for name in (*DEAD_APP_DIRS, *DEAD_PROXY_DIRS)
            if (SRC / "app" / name).exists()
        ]
        assert not risen, f"deleted screens or proxies reappeared: {risen}"

        returned = [rel for rel in DEAD_FILES if (SRC / rel).exists()]
        assert not returned, f"deleted components reappeared: {returned}"

        importers = []
        for path in sorted(SRC.rglob("*.ts*")):
            if IMPORT_OF_DEAD.search(_live(path.read_text(encoding="utf-8"))):
                importers.append(path.relative_to(SRC).as_posix())
        assert not importers, f"these still import a deleted module: {importers}"

    def test_the_import_pattern_matches_the_shapes_it_guards(self):
        """Without this the regex could match nothing and the walk above would
        pass over a file that imports a deleted component."""
        for line in (
            'import LiveBoard from "@/components/LiveBoard";',
            'import { SlateRow } from "./SlateRow";',
            'import { sizing } from "@/lib/liveSizing";',
            'export { TicketSheet } from "../components/TicketSheet.tsx";',
        ):
            assert IMPORT_OF_DEAD.search(line), line
        assert not IMPORT_OF_DEAD.search('import Sheet from "@/components/Sheet";')

    def test_no_api_fetcher_for_a_dead_screen_survives(self):
        api = _live((SRC / "lib" / "api.ts").read_text(encoding="utf-8"))
        for name in (
            "fetchBoard",
            "fetchLedger",
            "fetchDashboards",
            "fetchRecentEstimates",
            "fetchStudyStop",
            "fetchSuppression",
            "logEstimate",
            "reviseEstimate",
            "placeOrder",
        ):
            assert not re.search(rf"\b{name}\b", api), name

    def test_the_proxies_are_out_of_the_middleware_json_set(self):
        middleware = _live((SRC / "middleware.ts").read_text(encoding="utf-8"))
        assert "/log-estimate" not in middleware
        assert "/revise-estimate" not in middleware

    def test_the_footer_links_gate_and_playbook_only(self):
        footer = _live((SRC / "components" / "Footer.tsx").read_text(encoding="utf-8"))
        hrefs = set(re.findall(r'href:\s*"(/[^"]*)"', footer))
        assert hrefs == {"/gate", "/playbook"}, hrefs
