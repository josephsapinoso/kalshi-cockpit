"""The refresh card follows the league chip (Joe, 2026-09-15).

With NFL selected on Games, the "Refresh the odds" card listed every MLB
game with a prop tap and nothing NFL, which reads as "there are no NFL
props" rather than "no NFL game is inside the card's 24-hour horizon".
`frontend/src/lib/refreshableCut.ts` is the pure decision; this executes it
with node the way `test_refresh_urgency.py` does, because the case that
matters -- the chosen league has nothing inside the horizon while other
leagues do -- must be told apart from an empty horizon, and a substring pin
on the panel cannot tell those states apart.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- Nothing about the words the panel draws for each state; only that it
  reaches the cut and both list screens hand it the chip (source pins).
- Nothing about the 24-hour horizon itself, which is the server's
  (`routers/odds.py`) and unchanged here.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CUT_TS = REPO / "frontend" / "src" / "lib" / "refreshableCut.ts"
PANEL = REPO / "frontend" / "src" / "components" / "RefreshOddsPanel.tsx"
SLATE_PAGE = REPO / "frontend" / "src" / "app" / "slate" / "page.tsx"
PARLAYS_PAGE = REPO / "frontend" / "src" / "app" / "parlays" / "page.tsx"

NODE = shutil.which("node")

_DRIVER = """
import { cutRefreshable } from "./refreshableCut.ts";
const args = JSON.parse(process.argv[2]);
console.log(JSON.stringify(cutRefreshable(args.sports, args.league)));
"""


def cut(sports, league):
    driver = CUT_TS.parent / "_refreshable_cut_driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    try:
        out = subprocess.run(
            [
                NODE,
                "--experimental-strip-types",
                str(driver),
                json.dumps({"sports": sports, "league": league}),
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=CUT_TS.parent,
        )
    finally:
        driver.unlink(missing_ok=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


MLB = {"sport_key": "baseball_mlb", "fixtures": [1, 2]}
WNBA = {"sport_key": "basketball_wnba", "fixtures": [3]}


@pytest.mark.skipif(NODE is None, reason="node is not on PATH")
class TestTheCardFollowsTheChip:
    def test_no_chip_lists_every_league(self):
        got = cut([MLB, WNBA], None)
        assert got == {"kind": "listed", "sports": [MLB, WNBA]}

    def test_the_chips_league_is_the_only_one_listed(self):
        """Mutation: drop the `filter` and return every sport -- fails."""
        got = cut([MLB, WNBA], "baseball_mlb")
        assert got == {"kind": "listed", "sports": [MLB]}

    def test_a_league_with_no_game_inside_the_horizon_is_named_not_hidden(self):
        """The 2026-09-15 screen: NFL chip, MLB-only horizon. The card must
        say NFL has nothing inside 24 hours and that other leagues do, so
        the reader clears the chip rather than concluding NFL props do not
        exist. Mutation: return `nothing_stored` for an empty cut -- fails
        on `kind` and loses the count."""
        got = cut([MLB, WNBA], "americanfootball_nfl")
        assert got == {
            "kind": "league_outside_horizon",
            "league": "americanfootball_nfl",
            "others": 2,
        }

    def test_an_empty_horizon_is_empty_whatever_the_chip_says(self):
        """No stored fixture at all is a different state from a cut that
        removed them, and it says so even under a chip."""
        assert cut([], "americanfootball_nfl") == {"kind": "nothing_stored"}
        assert cut([], None) == {"kind": "nothing_stored"}


class TestTheScreensHandTheChipToTheCard:
    def test_the_panel_reaches_the_cut(self):
        src = PANEL.read_text(encoding="utf-8")
        assert "cutRefreshable(data.sports, league)" in src
        assert 'cut.kind === "league_outside_horizon"' in src
        # The map draws the cut, never the raw payload.
        assert "cut.sports.map(" in src
        assert "data.sports.map(" not in src

    def test_both_list_screens_pass_their_filter(self):
        """The Board has no bar and keeps the unfiltered card; the two
        screens under a `FilterBar` must hand the same `filter` down, or the
        rows and the card disagree about which league is showing."""
        for page, path in ((SLATE_PAGE, "/slate"), (PARLAYS_PAGE, "/parlays")):
            src = page.read_text(encoding="utf-8")
            calls = [
                line for line in src.splitlines() if "<RefreshOddsPanel" in line
            ]
            assert calls, page
            for line in calls:
                assert "filter={filter}" in line, (page, line)
                assert f'pathname="{path}"' in line, (page, line)
