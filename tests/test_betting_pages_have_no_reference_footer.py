"""The 'Also served' reference footer is off /parlays and /game (#298).

The sharp-bettor's read at the 2026-10-02 town hall: Gate, Playbook,
Estimates, Evidence and Refusals under a parlay builder is decoration on a
betting screen. The footer is drawn once, by the root layout, so the cut is
made where the footer decides: it reads the path and draws nothing on the
two betting screens.

Source assertions (this repo has no JS test runner).

What they establish: the footer is a client component that reads the
pathname; `/parlays` and `/game` (and anything beneath them) are the screens
it skips; every reference link is still in `SECONDARY` and the layout still
draws the footer, so the five pages stay reachable from the other screens
(`tests/test_every_screen_is_reachable.py` pins that independently). They do
NOT establish how it looks on any screen.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"
FOOTER = SRC / "components" / "Footer.tsx"
LAYOUT = SRC / "app" / "layout.tsx"
REFERENCE = ("/gate", "/playbook")


def _code(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)


def test_parlays_and_game_carry_no_also_served_footer():
    code = _code(FOOTER)
    assert code.lstrip().startswith('"use client"')
    assert "usePathname()" in code
    assert 'const BETTING_SCREENS = ["/parlays", "/game"];' in code
    # The skip happens before any markup is returned.
    component = code[code.index("export default function Footer"):]
    assert component.index("isBettingScreen(pathname)") < component.index("<footer")
    assert re.search(r"if \(isBettingScreen\(pathname\)\) return null;", component)
    # Sub-routes of a betting screen are skipped too (/game/<event>).
    helper = code[code.index("export function isBettingScreen"):]
    helper = helper[: helper.index("\n}\n")]
    assert "pathname === screen" in helper
    assert "pathname.startsWith(`${screen}/`)" in helper


def test_the_reference_pages_are_not_deleted_or_unlinked():
    code = _code(FOOTER)
    for href in REFERENCE:
        assert f'href: "{href}"' in code, href
    assert "Also served" in code
    assert "<Footer />" in _code(LAYOUT)
