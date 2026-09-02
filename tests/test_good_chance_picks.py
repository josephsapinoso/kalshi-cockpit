"""The "likely winners tonight" block's screen half (ADR 0067).

Source-text assertions, the same instrument as `tests/test_crew_bubble.py`
and with the same limitation: a green suite says the component contains and
omits the right text, not that it renders, is reachable, or is legible.

The server half — ranking, staleness, the counted exclusions, the note's
exact sentence, and the no-edge-key walk — is `tests/test_slate_picks.py`.
These tests pin what only the screen can get wrong: rendering the payload's
own sentence rather than writing one, offering no order affordance, and not
wearing money ink.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
PICKS = FRONTEND / "components" / "GoodChancePicks.tsx"
SLATE_PAGE = FRONTEND / "app" / "slate" / "page.tsx"
#: The block as a screen of its own (decision-map #8, 2026-09-02). Every
#: chase-surface prohibition on the block applies to the page that hosts it
#: under the nav word "Picks"; the walk below runs over both.
PICKS_PAGE = FRONTEND / "app" / "picks" / "page.tsx"
CHASE_SURFACES = [
    pytest.param(PICKS, id="GoodChancePicks"),
    pytest.param(PICKS_PAGE, id="picks-page"),
]


def source(path: Path) -> str:
    assert path.exists(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def code_only(text: str) -> str:
    """`text` with comments removed, so a prohibition's own explanation
    cannot fail the grep that enforces it (the `test_crew_bubble` lesson)."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


class TestTheBlockRendersTheServersSentence:
    def test_the_note_renders_verbatim_from_the_payload(self):
        """`{picks.note}` in the JSX — the screen prints the server's
        chance≠edge sentence rather than authoring its own, so the two
        cannot come to disagree about what the block claims."""
        assert "{picks.note}" in source(PICKS)

    def test_the_counted_exclusions_render_in_words(self):
        text = source(PICKS)
        assert "not_ranked.stale_consensus" in text
        assert "not_ranked.favorite_unpriced" in text


class TestTheBlockIsNotAChaseSurface:
    """Walked over the block AND the `/picks` page that hosts it (#8
    amendment 3): a prohibition that held for a block on Games and lapsed the
    day the block got a nav slot would have lapsed exactly where it matters.
    Mutation observed red on the page: import `ManualTicket` into
    `app/picks/page.tsx` -- `test_nothing_here_opens_a_ticket[picks-page]`."""

    @pytest.mark.parametrize("path", CHASE_SURFACES)
    def test_no_money_ink(self, path):
        """`bg-accent` is reserved for money (ADR 0061); a favorites list
        wearing it would read as a buy button per game."""
        assert "bg-accent" not in code_only(source(path))

    @pytest.mark.parametrize("path", CHASE_SURFACES)
    def test_nothing_here_opens_a_ticket(self, path):
        """Entries link to the game's own screen and nowhere else. A ticket
        on a ranked favorites list is the tilt reviewer's chase surface."""
        text = code_only(source(path))
        for banned in ("TicketSheet", "TicketTrigger", "ManualTicket",
                       "/api/orders", "/api/manual-orders"):
            assert banned not in text, f"{banned} appears in {path.name}"

    @pytest.mark.parametrize("path", CHASE_SURFACES)
    def test_no_streak_or_hit_count(self, path):
        """A "picks that hit" tally is the ego-loaded aggregate the CLV
        ruling banned below n >= 30; this block must never grow one."""
        text = code_only(source(path)).lower()
        for banned in ("hit rate", "hitrate", "streak", "record:"):
            assert banned not in text


class TestTheSlatePageCarriesIt:
    def test_the_page_renders_the_block(self):
        assert "<GoodChancePicks" in source(SLATE_PAGE)

    def test_the_page_passes_the_payload_block_through(self):
        """`picks={data.picks}` — the page hands the server's block over
        whole; deriving picks client-side from the rows would be a second
        ranking implementation that could disagree with the first."""
        assert "picks={data.picks}" in source(SLATE_PAGE)
