"""Picks is ordered by kickoff, earliest first (#241, Joe's #235 A).

Source-text assertions over the route and the screens; the behavioural half
(the served order, ties, unknown kickoff) is `tests/test_slate_picks.py`.

What these pin:

- **The sort key is kickoff.** `commence_ms` then `ticker`, read off the pick
  dict; mutation observed red: restore `ranked.sort(key=lambda pair: -pair[0])`.
- **The sort never reads chance or edge** (ADR 0071: a per-row fact is
  transparency, an ordering is a claim). Mutation observed red: add
  `fair_probability` to the sort key.
- **No screen source renders "Likely winners".** Mutation observed red: put
  the heading back in `GoodChancePicks.tsx` or mount it on the slate page.

Not established: that the page renders; only that the source says so.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = ROOT / "backend" / "api" / "routes.py"
FRONTEND = ROOT / "frontend" / "src"


def picks_sort_statement() -> str:
    text = ROUTES.read_text(encoding="utf-8")
    start = text.index("ranked.sort(")
    depth = 0
    for j in range(text.index("(", start), len(text)):
        depth += text[j] == "("
        depth -= text[j] == ")"
        if depth == 0:
            return text[start : j + 1]
    raise AssertionError("unbalanced ranked.sort(")


def test_the_only_picks_sort_is_keyed_on_kickoff_then_ticker():
    text = ROUTES.read_text(encoding="utf-8")
    assert text.count("ranked.sort(") == 1
    stmt = picks_sort_statement()
    assert 'pair[1]["commence_ms"]' in stmt
    assert 'pair[1]["ticker"]' in stmt


def test_the_sort_never_reads_chance_or_edge():
    stmt = picks_sort_statement()
    assert "pair[0]" not in stmt, "the fair-probability slot of the tuple"
    for banned in ("fair", "edge", "breakeven", "chance", "ask"):
        assert banned not in stmt.lower(), f"{banned!r} is in the picks sort"


def test_no_screen_source_renders_likely_winners():
    offenders = []
    for path in FRONTEND.rglob("*.tsx"):
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        text = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
        if re.search(r"likely\s+winners", text, flags=re.IGNORECASE):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_the_slate_page_no_longer_mounts_the_block():
    text = (FRONTEND / "app" / "slate" / "page.tsx").read_text(encoding="utf-8")
    assert "GoodChancePicks" not in text


def test_the_picks_page_says_kickoff_not_chance():
    raw = (FRONTEND / "app" / "picks" / "page.tsx").read_text(encoding="utf-8")
    text = re.sub(r"\s+", " ", raw)
    assert "ordered by kickoff, earliest first" in text
    assert "ordered by that chance" not in text
