"""A team-less parlay leg draws its game, on every place the leg is drawn.

On 2026-09-15 the "Three totals" card showed Joe three "Under 8.5 runs
scored" rows he could not tell apart. `event_title` had been on every leg
of the wire since ADR 0051 (`backend/parlays.py:_serialise_leg`) and was
rendered nowhere on the parlay path: the leg row, the provenance list, the
origins list and the per-leg buy list all printed `leg.label` alone, and a
total's label is Kalshi's subtitle, which names a line and a unit and no
teams.

There is no component test harness in `frontend/`, so this is a source
scan, the same shape as `test_parlay_exclusion_words.py`: it pins that the
game line is drawn from `event_title` and that all four leg renderers
mount it. Mutation observed red: removing any one `<LegGame leg={leg} />`.

What it does not establish: that the line is visible at phone width, or
what a total event's title looks like on live -- the SSR read of
`/parlays` after deploy is that check.
"""

from __future__ import annotations

import re
from pathlib import Path

CARDS = (
    Path(__file__).resolve().parents[1]
    / "frontend" / "src" / "components" / "ParlayCards.tsx"
)


def _source() -> str:
    return CARDS.read_text(encoding="utf-8")


class TestTheGameLineIsDrawnFromTheEventTitle:
    def test_the_helper_reads_event_title_and_only_on_a_team_less_leg(self):
        src = _source()
        helper = re.search(r"function legGame\(leg: ParlayCardLeg\).*?\n}\n", src, re.S)
        assert helper, "legGame() is gone"
        body = helper.group(0)
        assert "leg.event_title" in body
        assert "if (leg.team !== null) return null;" in body, (
            "a team leg's label already names the team; the game line is for "
            "totals and props"
        )

    def test_every_leg_renderer_mounts_it(self):
        """The leg row, "what the desk checked", "where each number came
        from" and "bet this leg" each draw the leg; each draws its game."""
        src = _source()
        assert src.count("<LegGame leg={leg} />") == 4, (
            "a leg renderer dropped the game line, or a fifth one was added "
            "without it"
        )
