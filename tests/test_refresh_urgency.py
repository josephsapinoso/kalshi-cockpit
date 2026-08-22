"""The refresh panel outranks the games only when something is actually stale.

The 2026-08-22 review measured the landing screen's first game row at
~1,700px — below the fold on the phone AND the desktop — with the refresh
apparatus above it. The ruling: games first; the panel takes the top slot
only when it can fix what the reader is about to misread (stale consensus,
or a slate that is not current). `frontend/src/lib/refreshUrgency.ts` is the
pure decision; this executes it with node the way `test_suppression_gloss.py`
executes the gloss, because a substring assertion passes unchanged on an
inverted comparison.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- Nothing about where the panel actually renders — the source pin below
  checks both call sites exist with opposite polarity, not the layout.
- Nothing about the odds-age limit's value; the page passes the server's own
  `staleness.max_odds_age_s`, and that number is the server's to state.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
URGENCY_TS = REPO / "frontend" / "src" / "lib" / "refreshUrgency.ts"
SLATE_PAGE = REPO / "frontend" / "src" / "app" / "slate" / "page.tsx"

NODE = shutil.which("node")

_DRIVER = """
import { refreshIsUrgent } from "./refreshUrgency.ts";
const args = JSON.parse(process.argv[2]);
console.log(JSON.stringify(
  refreshIsUrgent(args.rows, args.maxOddsAgeMs, args.slateIsCurrent),
));
"""


def urgent(rows, max_odds_age_ms=900_000, slate_is_current=True):
    driver = URGENCY_TS.parent / "_urgency_driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    try:
        out = subprocess.run(
            [
                NODE,
                "--experimental-strip-types",
                str(driver),
                json.dumps(
                    {
                        "rows": rows,
                        "maxOddsAgeMs": max_odds_age_ms,
                        "slateIsCurrent": slate_is_current,
                    }
                ),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            cwd=str(URGENCY_TS.parent),
        )
    finally:
        driver.unlink(missing_ok=True)
    assert out.returncode == 0, f"node failed:\n{out.stdout}\n{out.stderr}"
    return json.loads(out.stdout.strip())


FRESH = {"odds_age_now_ms": 60_000, "suppressed_reason": None}
STALE = {"odds_age_now_ms": 1_200_000, "suppressed_reason": None}


@pytest.mark.skipif(
    NODE is None,
    reason=(
        "node is not on PATH. Skipped rather than xfailed: the guard is real "
        "where node exists (CI and both dev machines)."
    ),
)
class TestUrgencyIsExecuted:
    def test_a_fresh_slate_is_not_urgent(self):
        assert urgent([FRESH, FRESH]) is False

    def test_one_stale_row_is_urgent(self):
        """The whole point. Mutation observed red: `>` flipped to `<` in
        refreshIsUrgent makes fresh slates urgent and this stale one calm."""
        assert urgent([FRESH, STALE]) is True

    def test_a_non_current_slate_is_urgent_even_with_no_rows(self):
        """Mutation observed red: the `!slateIsCurrent` early return dropped."""
        assert urgent([], slate_is_current=False) is True

    def test_a_missing_age_makes_no_claim(self):
        """A missing clock is not a stale clock — the repo's null-never-zero
        rule pointed the other way: null must also never mean 'stale'."""
        assert urgent([{"odds_age_now_ms": None, "suppressed_reason": None}]) is False

    def test_an_engine_refusal_for_staleness_counts_without_an_age(self):
        """The engine's own `stale_odds` verdict is evidence even when the
        row's age column is missing — the refusal happened."""
        assert (
            urgent([{"odds_age_now_ms": None, "suppressed_reason": "stale_odds"}])
            is True
        )

    def test_the_limit_is_a_boundary_not_a_neighborhood(self):
        assert urgent([{"odds_age_now_ms": 900_000, "suppressed_reason": None}]) is False
        assert urgent([{"odds_age_now_ms": 900_001, "suppressed_reason": None}]) is True


class TestThePageUsesTheDecisionInBothPositions:
    def test_the_panel_renders_above_when_urgent_and_below_when_not(self):
        """The page must call refreshIsUrgent twice with opposite polarity —
        one gate for the top slot, its negation for the bottom — so the panel
        always renders exactly once. Counting call sites is the cheapest pin
        that catches 'the demotion was reverted' and 'the panel vanished
        entirely' at the same time."""
        source = SLATE_PAGE.read_text(encoding="utf-8")
        assert source.count("refreshIsUrgent(") == 2
        assert source.count("!refreshIsUrgent(") == 1
        assert source.count("<RefreshOddsPanel") == 2
