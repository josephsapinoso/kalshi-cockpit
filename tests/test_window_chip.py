"""The nav chip's verdict, executed rather than read.

Same lane as `tests/test_sweep_tone_predicate.py`: the predicate lives in a
React-free module (`frontend/src/lib/windowChip.ts`) so the real shipped
function can be run by node, because a substring assertion passes unchanged on
a predicate that is exactly inverted.

What this establishes: that `windowChip` maps four inputs to the intended
state and words, and that the words never promise a bet. What it does **not**
establish: that `Nav.tsx` renders the chip (a source assertion below covers
the wiring), that the chip is legible, or that `/api/window` computes the
inputs correctly — those are the timing tests' claims.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CHIP_TS = REPO / "frontend" / "src" / "lib" / "windowChip.ts"
NAV_TSX = REPO / "frontend" / "src" / "components" / "Nav.tsx"

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None,
    reason=(
        "node is not on PATH. Skipped rather than xfailed: the guard is real "
        "where node exists (CI and both dev machines)."
    ),
)

_DRIVER = """
import { windowChip } from "./windowChip.ts";
const facts = JSON.parse(process.argv[2]);
console.log(JSON.stringify(windowChip(facts)));
"""

NOW = 1_766_000_000_000


def chip_of(facts: dict) -> dict:
    driver = CHIP_TS.parent / "_chip_driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    try:
        out = subprocess.run(
            [NODE, "--experimental-strip-types", str(driver), json.dumps(facts)],
            capture_output=True,
            text=True,
            # Node writes UTF-8; without this, Windows decodes with the ANSI
            # code page and the label's "·" comes back as U+FFFD.
            encoding="utf-8",
            timeout=60,
            cwd=str(CHIP_TS.parent),
        )
    finally:
        driver.unlink(missing_ok=True)
    assert out.returncode == 0, f"node failed:\n{out.stdout}\n{out.stderr}"
    return json.loads(out.stdout.strip())


class TestTheChipStatesTheWindowAndNothingMore:
    def test_an_open_window_says_open_and_how_long_the_prices_hold(self):
        chip = chip_of(
            {
                "now_ms": NOW,
                "is_open": True,
                "open_until_ms": NOW + 42 * 60_000,
                "next_sweep_ms": None,
            }
        )
        assert chip == {"state": "open", "label": "window open · fresh for 42m"}

    def test_a_closed_window_with_a_sweep_coming_says_when(self):
        chip = chip_of(
            {
                "now_ms": NOW,
                "is_open": False,
                "open_until_ms": None,
                "next_sweep_ms": NOW + (3 * 60 + 12) * 60_000,
            }
        )
        assert chip == {
            "state": "closed",
            "label": "window closed · next sweep in 3h 12m",
        }

    def test_a_closed_window_with_nothing_scheduled_says_only_closed(self):
        """No sweep coming is a different quiet from "one is coming"; the chip
        must not invent a countdown to nothing."""
        chip = chip_of(
            {
                "now_ms": NOW,
                "is_open": False,
                "open_until_ms": None,
                "next_sweep_ms": None,
            }
        )
        assert chip == {"state": "closed", "label": "window closed"}

    def test_a_stale_next_sweep_in_the_past_is_not_a_countdown(self):
        chip = chip_of(
            {
                "now_ms": NOW,
                "is_open": False,
                "open_until_ms": None,
                "next_sweep_ms": NOW - 60_000,
            }
        )
        assert chip["label"] == "window closed"

    def test_the_words_never_promise_a_bet(self):
        """The chip is read alone in the chrome, away from the banner that
        explains it. Whatever the state, the vocabulary of permission must not
        appear."""
        for facts in (
            {"now_ms": NOW, "is_open": True, "open_until_ms": NOW + 600_000, "next_sweep_ms": None},
            {"now_ms": NOW, "is_open": False, "open_until_ms": None, "next_sweep_ms": NOW + 600_000},
        ):
            label = chip_of(facts)["label"].lower()
            for word in ("bet", "edge", "actionable", "opportunit"):
                assert word not in label


class TestTheNavWiring:
    def test_the_nav_renders_the_chip_in_muted_ink_at_xl_only(self):
        nav = NAV_TSX.read_text(encoding="utf-8")
        assert "windowChip" in nav, "Nav no longer consults the predicate"
        chip_span = nav.split("chip !== null", 1)[1].split("</span>", 1)[0]
        assert "text-muted" in chip_span, (
            "the chip left muted ink; any state colour here reads as a verdict"
        )
        assert "xl:flex" in chip_span and "hidden" in chip_span, (
            "the chip must not exist below xl — the phone's four-link budget "
            "is not renegotiated by a desktop feature"
        )
        for cls in ("text-positive", "text-accent", "bg-positive"):
            assert cls not in chip_span
