"""`leagueLabel` renders Kalshi's competition strings and the odds feed's sport
keys to the same word, and its copy of Kalshi's spellings cannot drift from
the backend's.

Why this exists: `/api/board` and `/api/slate` fill a row's `league` from
`event_links.league` -- Kalshi's `product_metadata.competition`, "Pro
Baseball" -- while the #15 filter chip renders The Odds API's `baseball_mlb`.
Both went through `leagueLabel`, which knew only the sport keys, so a Games
row read "PRO BASEBALL" under a chip that said "MLB". Noted at the #15 merge
(2026-09-02) and fixed 2026-09-03.

The Python half pins the TypeScript map byte-for-byte against
`IN_SCOPE_LEAGUES` in `backend/kalshi/discovery.py`: a league added to scope
without the frontend learning its spelling would render as a vendor string,
silently, on every row of that league. The node half executes the function
rather than grepping it, because a substring cannot tell a branch from its
inversion.

WHAT THIS DOES NOT ESTABLISH: that every surface passes `league` through
`leagueLabel` at all. That is `LeagueTag`'s contract and is pinned where it
is rendered.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.kalshi.discovery import IN_SCOPE_LEAGUES

REPO = Path(__file__).resolve().parents[1]
LIB_TS = REPO / "frontend" / "src" / "lib" / "leagueLabel.ts"

NODE = shutil.which("node")

_DRIVER = """
import { leagueLabel } from "./leagueLabel.ts";
const args = JSON.parse(process.argv[2]);
console.log(JSON.stringify(args.map((v) => leagueLabel(v))));
"""


def _labels(values: list[str]) -> list[str]:
    driver = LIB_TS.parent / "_league_label_driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    try:
        out = subprocess.run(
            [NODE, "--experimental-strip-types", str(driver), json.dumps(values)],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(LIB_TS.parent),
        )
    finally:
        driver.unlink(missing_ok=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def _ts_competitions() -> dict[str, str]:
    """The `KALSHI_COMPETITIONS` literal, parsed from the source."""
    src = LIB_TS.read_text(encoding="utf-8")
    block = re.search(
        r"const KALSHI_COMPETITIONS: Record<string, string> = \{(.*?)\};",
        src,
        re.S,
    )
    assert block, "KALSHI_COMPETITIONS literal not found"
    pairs = re.findall(r'"([^"]+)":\s*"([^"]+)"', block.group(1))
    return dict(pairs)


class TestTheTwoSpellingsCannotDrift:
    def test_the_frontend_copy_equals_in_scope_leagues(self):
        assert _ts_competitions() == dict(IN_SCOPE_LEAGUES)

    def test_every_in_scope_league_has_a_word(self):
        src = LIB_TS.read_text(encoding="utf-8")
        for sport_key in IN_SCOPE_LEAGUES.values():
            assert re.search(rf"^\s*{re.escape(sport_key)}:\s*\"", src, re.M), (
                f"{sport_key} is in scope and has no label"
            )


@pytest.mark.skipif(NODE is None, reason="node not on PATH")
class TestBothVocabulariesReadTheSameWord:
    def test_kalshis_competition_and_the_sport_key_agree(self):
        competitions = list(IN_SCOPE_LEAGUES)
        keys = [IN_SCOPE_LEAGUES[c] for c in competitions]
        assert _labels(competitions) == _labels(keys)

    def test_pro_baseball_reads_mlb(self):
        assert _labels(["Pro Baseball", "baseball_mlb"]) == ["MLB", "MLB"]

    def test_an_unknown_value_renders_as_itself(self):
        assert _labels(["Curling (Mixed)"]) == ["Curling (Mixed)"]
