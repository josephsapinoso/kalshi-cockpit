"""The "Not tonight" strip is on every screen where a bet gets decided.

Ticket #45, Joe's A (2026-09-16). `TonightStrip` -- tonight's unsigned
commitment and the one-tap lockout -- was mounted on Games and Picks and not
on `/market/[ticker]`, the screen that carries the buy button. A control the
reader has on the list and loses on the row he tapped through to is a control
that is absent at the moment it is for. This is a control Joe already has, on
a screen that lacked it; it is not a restored brake (ADR 0112 took the five
ceilings off the hand-bet path and this puts none back -- the lockout is his
own tap and the server enforced it on this route already).

Source-text assertions, the same instrument as `tests/test_pass_control.py`
and with the same limitation: a green suite says the page contains the mount
and hands the server's block over whole, not that it renders or is tappable.
The payload half -- that `/api/market/{ticker}` serves the same `tonight`
block as `/api/slate` -- is `tests/test_api.py::TestMarketDetail`.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- Nothing about the strip's own wording or its refusal when the mirror is
  stale; that is `tests/test_scope_sentences.py` and `tests/test_bets.py`.
- Nothing about the lockout being enforced: `tests/test_bets.py` and the
  manual-order tests own that.

Mutations, each observed red:
  1. delete the `<TonightStrip` mount from the market page
  2. mount it with a literal instead of `detail.tonight`
  3. drop a page from `DECIDING_SCREENS` while it still mounts the strip
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
STRIP = FRONTEND / "components" / "TonightStrip.tsx"

#: Every screen on which a bet is decided, and therefore owes the reader
#: tonight's commitment and the way out. Listed rather than discovered;
#: `TestTheListCannotSilentlyBecomeASubset` is what stops it shrinking.
DECIDING_SCREENS = [
    pytest.param(
        FRONTEND / "app" / "slate" / "page.tsx", "data.tonight", id="games"
    ),
    pytest.param(
        FRONTEND / "app" / "picks" / "page.tsx", "data.tonight", id="picks"
    ),
    pytest.param(
        FRONTEND / "app" / "market" / "[ticker]" / "page.tsx",
        "detail.tonight",
        id="market",
    ),
]


def source(path: Path) -> str:
    assert path.exists(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def code(path: Path) -> str:
    """The file with its comments removed, so a comment naming the mount
    cannot satisfy the assertion that the mount exists."""
    text = re.sub(r"/\*.*?\*/", "", source(path), flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


class TestTheFilesAreTheOnesThisModuleThinksTheyAre:
    def test_the_strip_is_the_component_with_the_lockout_tap(self):
        text = source(STRIP)
        assert "export default function TonightStrip(" in text
        assert "engageLockout" in text


class TestEveryDecidingScreenMountsTheStrip:
    @pytest.mark.parametrize("path,block", DECIDING_SCREENS)
    def test_the_strip_is_mounted(self, path, block):
        assert "<TonightStrip" in code(path), (
            f"{path.name} decides bets and does not mount TonightStrip"
        )

    @pytest.mark.parametrize("path,block", DECIDING_SCREENS)
    def test_the_strip_is_handed_the_servers_block_whole(self, path, block):
        """`tonight={<payload>.tonight}` -- the page hands over the server's
        block rather than assembling one, so the three screens cannot come
        to disagree about what "tonight" is. One helper on the server, one
        prop here."""
        assert f"tonight={{{block}}}" in code(path), (
            f"{path.name} builds its own tonight block instead of passing "
            f"{block} through"
        )

    def test_the_market_page_mounts_it_before_the_ticket(self):
        """Above the buy control, not below it: the reader sees what is
        already staked tonight, and the way out, before the button."""
        text = code(FRONTEND / "app" / "market" / "[ticker]" / "page.tsx")
        assert text.index("<TonightStrip") < text.index("<ManualTicket"), (
            "the strip renders after the ticket on the market page"
        )


class TestTheListCannotSilentlyBecomeASubset:
    def test_every_page_that_mounts_the_strip_is_listed(self):
        """A page that grows the strip without joining the list would be
        guarded by nothing; a page dropped from the list while still
        mounting it would be the same gap in the other direction."""
        listed = {p.values[0] for p in DECIDING_SCREENS}
        mounting = {
            page
            for page in (FRONTEND / "app").rglob("page.tsx")
            if "<TonightStrip" in code(page)
        }
        assert mounting == listed, (
            f"pages mounting TonightStrip: {sorted(p.name for p in mounting)}; "
            f"listed: {sorted(p.name for p in listed)}"
        )
