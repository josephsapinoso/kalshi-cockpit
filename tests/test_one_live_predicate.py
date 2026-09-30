"""One "is this bet still live" predicate, and two counts that say what they count (#250).

WHAT THIS ESTABLISHES
----------------------
(i)   The expression `pending_legs > 0 && venue_settlement === null` is
      written once in `frontend/src/**`, inside `isLive` in `lib/api.ts`.
(ii)  HedgePositions, /bets and Nav import `isLive` from `@/lib/api` and call
      it; none re-spells the terms.
(iii) "Open now: N positions" (venue) is labelled "at Kalshi" and the /bets
      heading's N is labelled "tickets on the desk", so the two counts never
      appear as unlabelled numbers for the same question.
(iv)  OpenPositions.tsx gained no value import (`isLive` is not pulled in; it is compiled alone in
      another test with only react resolvable).

WHAT THIS DOES NOT ESTABLISH
-----------------------------
Source text only: no DOM, and not that the two counts agree on real data
(they are different quantities on purpose).

MUTATIONS, each observed red
----------------------------
  1. re-inline the predicate in Nav -> (i) and (ii).
  2. drop `isLive` from the HedgePositions import -> (ii).
  3. remove "at Kalshi" -> (iii).
  4. remove "on the desk" -> (iii).
  5. import isLive into OpenPositions -> (iv).
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"
API = SRC / "lib" / "api.ts"
CALLERS = {
    "HedgePositions": SRC / "components" / "HedgePositions.tsx",
    "bets": SRC / "app" / "bets" / "page.tsx",
    "Nav": SRC / "components" / "Nav.tsx",
}
OPEN_POSITIONS = SRC / "components" / "OpenPositions.tsx"

TERMS = re.compile(r"pending_legs\s*>\s*0\s*&&\s*\w+\.venue_settlement\s*===\s*null")
IMPORT_ISLIVE = re.compile(r"import \{[^}]*\bisLive\b[^}]*\} from \"@/lib/api\"")


def code(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", text)


class TestOnePredicate:
    def test_the_expression_appears_once_in_all_of_src_and_it_is_in_api(self):
        hits = []
        for path in SRC.rglob("*.ts*"):
            hits += [path for _ in TERMS.findall(code(path))]
        assert hits == [API], f"predicate spelled in: {hits}"

    def test_isLive_is_exported_from_api(self):
        assert re.search(r"export function isLive\(", code(API))

    def test_every_caller_imports_and_calls_it(self):
        for name, path in CALLERS.items():
            src = code(path)
            assert IMPORT_ISIVE_OK(src), f"{name} does not import isLive from @/lib/api"
            assert re.search(r"\bisLive\(|\(isLive\)|filter\(isLive\)", src), (
                f"{name} never calls isLive"
            )


def IMPORT_ISIVE_OK(src: str) -> bool:
    return IMPORT_ISLIVE.search(src) is not None


class TestTheTwoCountsAreLabelled:
    def test_the_venue_count_says_at_kalshi(self):
        assert '"positions"} at Kalshi </a>' in code(OPEN_POSITIONS)

    def test_the_heading_count_says_tickets_on_the_desk(self):
        src = code(CALLERS["bets"])
        assert '"tickets"} on the desk' in src
        assert "openCount === null ? null" in src

    def test_open_positions_does_not_import_the_predicate(self):
        assert "isLive" not in code(OPEN_POSITIONS)
