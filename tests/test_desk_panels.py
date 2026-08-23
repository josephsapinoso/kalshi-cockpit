"""The five-panel desk's screen half (ADR 0068).

Source-text assertions over the market screen and its panels, the
`test_crew_bubble.py` instrument with the same stated limitation: green says
the files contain and omit the right text, not that anything renders.

The server half — the gauntlet reconstruction and the market route's new
fields — is `tests/test_gauntlet_view.py` and `tests/test_api.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
MARKET_PAGE = FRONTEND / "app" / "market" / "[ticker]" / "page.tsx"
CONSENSUS = FRONTEND / "components" / "ConsensusPanel.tsx"
SKEPTIC = FRONTEND / "components" / "SkepticPanel.tsx"
SCOUT_DESK = FRONTEND / "components" / "ScoutDesk.tsx"


def source(path: Path) -> str:
    assert path.exists(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def code_only(text: str) -> str:
    """Comments removed, so a prohibition's own explanation cannot fail the
    grep that enforces it (the `test_crew_bubble` lesson)."""
    text = re.sub(r"\{\s*/\*.*?\*/\s*\}", "", text, flags=re.DOTALL)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


class TestTheFiveAreasAreNamedAndReachable:
    def test_the_nav_links_all_five_sections(self):
        text = source(MARKET_PAGE)
        for anchor in ("#consensus", "#skeptic", "#scout", "#specialists",
                       "#willy"):
            assert anchor in text, f"nav is missing {anchor}"

    def test_every_section_id_exists_somewhere_on_the_screen(self):
        """A nav link into nothing is a broken promise. The ids live across
        the page and the desk component; both are checked."""
        combined = source(MARKET_PAGE) + source(SCOUT_DESK) + source(
            CONSENSUS
        ) + source(SKEPTIC)
        for section_id in ("consensus", "skeptic", "scout", "specialists",
                           "willy"):
            assert f'id="{section_id}"' in combined, section_id


class TestNothingIsBehindAReveal:
    """Joe's constraint, verbatim: "I don't want to hover over every game
    anymore." Navigation is allowed; concealment is not."""

    def test_the_free_panels_contain_no_details_element(self):
        for path in (CONSENSUS, SKEPTIC):
            assert "<details" not in code_only(source(path)), (
                f"{path.name} hides desk content behind a reveal"
            )

    def test_the_scout_desk_keeps_exactly_one_details_and_it_is_the_meter(
        self,
    ):
        """The master's read and the staff filings both sat in <details>
        and came out (ADR 0068). The one survivor is the SpendDisclosure
        meter — a meter is chrome, not desk content. Wrapping the staff
        cards or the master's read back in a reveal adds a second <details>
        and turns this red."""
        text = code_only(source(SCOUT_DESK))
        assert text.count("<details") == 1
        assert "SpendDisclosure" in text

    def test_the_staff_cards_render_in_the_specialists_section(self):
        text = code_only(source(SCOUT_DESK))
        specialists = text.split('id="specialists"', 1)
        assert len(specialists) == 2, "the specialists section is missing"
        assert "<StaffNoteCard" in specialists[1], (
            "the specialists section does not render the staff filings"
        )


class TestTheConsensusPanelIsHonest:
    def test_the_explainer_paragraph_is_present(self):
        """The sentence Joe asked the site to carry: sport factors are
        already in the sharp line (ADR 0036/0037, stated as product copy)."""
        text = source(CONSENSUS)
        assert "priced them in" in text
        assert "adds noise, not information" in text

    def test_break_even_never_renders_beside_fair(self):
        """`edge = fair − break-even`: the identity that keeps these two out
        of one block. The panel renders fair%, so no break-even token may
        appear in it."""
        text = code_only(source(CONSENSUS)).lower()
        for banned in ("breakeven", "break_even"):
            assert banned not in text

    def test_no_edge_or_ev_token_appears(self):
        text = code_only(source(CONSENSUS))
        for banned in ("edge_tenths", "edge_cents", "ev_net", "edgeTone"):
            assert banned not in text


class TestTheSkepticPanelIsTheMechanicalChecks:
    def test_codes_render_verbatim_with_the_gloss_as_caption(self):
        """ADR 0050: a label and a caption, never a translation."""
        text = source(SKEPTIC)
        assert "{check.code}" in text
        assert "glossSuppression" in text

    def test_the_as_of_caption_is_served(self):
        """The verdicts are facts about when the row was judged; a board
        with no clock claims the present."""
        assert "judged_ms" in source(SKEPTIC)

    def test_it_calls_no_model_and_says_so(self):
        text = code_only(source(SKEPTIC))
        assert "sendScoutDesk" not in text
        assert "/api/scout" not in text
