"""#388: the nav is read on a phone, so each link is a 44px tap target and the
window-freshness line ("fresh for Nm") renders at 390px, not only at xl.

Establishes: source assertions over `Nav.tsx`. Does not establish rendered
geometry; `scripts/check_mobile.py` measures overflow at 390.
"""

from __future__ import annotations

import re
from pathlib import Path

NAV = Path(__file__).resolve().parent.parent / "frontend" / "src" / "components" / "Nav.tsx"


def _link_class() -> str:
    src = NAV.read_text(encoding="utf-8")
    inside = src.split("LINKS.map(", 1)[1].split("</Link>", 1)[0]
    return re.search(r"className=\{`([^`]*)`", inside).group(1)


def test_every_nav_link_is_at_least_44px_tall():
    cls = _link_class().split()
    assert "min-h-11" in cls, "nav links lost their 44px minimum height"
    assert "inline-flex" in cls and "items-center" in cls, (
        "min-h-11 without flex centring leaves the label stuck at the top"
    )
    src = NAV.read_text(encoding="utf-8")
    assert src.count("{ href:") == 4, "the nav is exactly four links"


def test_the_freshness_gauge_renders_at_390():
    src = NAV.read_text(encoding="utf-8")
    block = src.split("data-phone-chip", 1)[1].split("</div>", 1)[0]
    assert "chip.label" in block, "the phone line no longer shows the chip label"
    assert "xl:hidden" in block, "the phone line must hand over to the desktop chip at xl"
    assert not re.search(r"(?<![:\w-])hidden\b", block.replace("xl:hidden", "")), (
        "the phone line is hidden at base width"
    )
    assert "text-muted" in block
    for cls in ("text-negative", "text-red", "text-positive", "text-accent"):
        assert cls not in block, "an age is never coloured"
