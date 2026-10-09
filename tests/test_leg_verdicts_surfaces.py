"""The leg scouts on the game surfaces: tap only (#290, town hall 2026-10-02).

Joe answered #271 (A): `/game/<event>`'s "Your combination" panel and the
game-script card each get a "Check these legs" button that asks the leg
scouts about the ticked or card legs. Each tap spends about 51K tokens, so:

- **it is a tap and nothing else**: `requestLegVerdicts` is called from one
  click handler, never from an effect, never at module or render level;
- **it is never chained to Ask the market**: the handler is not `build`,
  `ask` or any function that mints, builds a card or draws `<AskTheMarket>`,
  and those functions do not call it;
- **both surfaces render the one button** and show the existing
  `<LegVerdicts>` panel, the opinion beside the legs and never a gate;
- it adds no new trigger value: it sends `card_button`, so no schema CHECK
  moves.

Source assertions (this repo has no JS test runner), the pattern of
`tests/test_leg_verdicts_ui.py`.

What this does not establish: that the panel renders, polls, or reads well at
phone width, or what a verdict costs on a given day.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "frontend" / "src"
CARD = SRC / "components" / "GameScriptCard.tsx"
LEGS = SRC / "components" / "GameLegs.tsx"
LEG_VERDICTS_ROUTE = REPO / "backend" / "api" / "routers" / "leg_verdicts.py"


def _code(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)


def _function(src: str, name: str) -> str:
    start = src.index(f"export function {name}")
    end = src.index("\n}\n", start)
    return src[start:end]


class TestVerdictsFireOnlyOnTap:
    def test_verdicts_fire_only_on_tap_on_game_surfaces(self):
        card = _code(CARD)
        # One call, inside the handler the button's onClick is bound to.
        assert len(re.findall(r"requestLegVerdicts\(", card)) == 1
        body = _function(card, "CheckTheseLegs")
        handler = body[body.index("const check = async"): body.index("return (")]
        assert "requestLegVerdicts(legs," in handler
        assert "onClick={check}" in body
        # Not from an effect, a memo or the render path of any component.
        assert "useEffect" not in body and "useMemo" not in body
        outside = card.replace(body, "")
        assert "requestLegVerdicts(" not in outside.replace(
            "  requestLegVerdicts,\n", ""
        )
        # GameLegs asks through the shared button, never itself.
        assert "requestLegVerdicts" not in _code(LEGS)
        assert "<CheckTheseLegs" in _code(LEGS)

    def test_the_call_sends_the_existing_card_button_trigger(self):
        body = _function(_code(CARD), "CheckTheseLegs")
        assert '"card_button"' in body
        assert '"card_button"' in LEG_VERDICTS_ROUTE.read_text(encoding="utf-8")


class TestNeverChainedToAskTheMarket:
    def test_neither_build_path_reaches_the_verdict_call(self):
        card = _code(CARD)
        ask = card[card.index("const ask = async"): card.index("if (card.status")]
        assert "requestLegVerdicts" not in ask and "CheckTheseLegs" not in ask
        legs = _code(LEGS)
        build = legs[legs.index("const build = async"): legs.index("if (error)")]
        assert "requestLegVerdicts" not in build and "CheckTheseLegs" not in build
        # And the check does not mint or ask: it holds no combination.
        check = _function(card, "CheckTheseLegs")
        for forbidden in ("mintGameCombo", "AskTheMarket", "buildGameCard"):
            assert forbidden not in check

    def test_the_game_bar_build_button_does_not_trigger_it(self):
        legs = _code(LEGS)
        bar = legs[legs.index('aria-label="Build bar"'):]
        assert "CheckTheseLegs" not in bar and "requestLegVerdicts" not in bar


class TestBothSurfacesRenderTheButtonAndThePanel:
    def test_the_card_and_the_combination_panel_render_it(self):
        card = _code(CARD)
        legs = _code(LEGS)
        assert "Check these legs" in card
        assert "<CheckTheseLegs" in card
        panel = legs[legs.index('aria-label="Your combination"'): legs.index("</aside>")]
        assert "<CheckTheseLegs" in panel
        assert 'import { CheckTheseLegs } from "@/components/GameScriptCard"' in legs

    def test_the_panel_is_the_existing_leg_verdicts_component(self):
        body = _function(_code(CARD), "CheckTheseLegs")
        assert "<LegVerdicts" in body
        # Drawn only after a tap: nothing reads or polls before one.
        assert "requestedAtMs !== null" in body
        # An opinion beside the legs, never a gate.
        assert "disabled" in body and "busy || legs.length === 0" in body

    def test_the_panel_forgets_a_verdict_when_the_ticked_legs_change(self):
        legs = _code(LEGS)
        panel = legs[legs.index("<CheckTheseLegs"):]
        assert "key={tickedLegs" in panel[:200]


def test_more_than_eight_legs_says_only_eight_are_checked():
    """#299: `requestLegVerdicts` slices to 8, so the panel must be handed the
    same 8 and the screen must say the rest are not checked, instead of
    drawing them as legs nobody has asked about."""
    card = _code(CARD)
    api = _code(SRC / "lib" / "api.ts")
    body = _function(card, "CheckTheseLegs")

    # The component's limit is the sender's limit.
    limit = re.search(r"const CHECK_LEG_LIMIT = (\d+);", card)
    sender = re.search(r"const LEG_VERDICT_MAX_LEGS = (\d+);", api)
    assert limit and sender and limit.group(1) == sender.group(1) == "8"

    # The legs sent AND the legs the panel draws are the cut list.
    assert "const legs = allLegs.slice(0, CHECK_LEG_LIMIT);" in body
    assert "const unchecked = allLegs.length - legs.length;" in body
    assert "requestLegVerdicts(legs," in body
    assert re.search(r"<LegVerdicts\s+legs=\{legs\}", body)
    assert "allLegs" not in body[re.search(r"<LegVerdicts\s", body).start():]

    # The sentence names the limit, the ticked count and the unchecked rest,
    # and is shown without waiting for a tap.
    notice = body[body.index("{unchecked > 0 && ("): body.index("{requestedAtMs !== null")]
    assert "Only the first {CHECK_LEG_LIMIT} of your {allLegs.length} legs are" in notice
    assert "{unchecked}" in notice and "not" in notice
    assert "max-w-[65ch]" in notice


CHECK_SCREEN = SRC / "components" / "CheckAParlay.tsx"


def _ask_the_scouts(check: str) -> str:
    return check[check.index("function AskTheScouts"): check.index("function CheckedResult")]


class TestTheCheckScreenAsksOnATapOnly:
    """#325: the Check-a-parlay result mounts the scouts behind ONE button.
    Leg-verdict registration Amendment 1: the `check_button` verdict is fired
    only by Joe's tap -- never on load, paste or from a watcher."""

    def test_the_check_screen_mounts_the_panel_and_the_button(self):
        check = _code(CHECK_SCREEN)
        assert "Ask the scouts" in check
        assert "<LegVerdicts" in _ask_the_scouts(check)
        assert "<AskTheScouts" in check

    def test_the_call_is_one_tap_handler_sending_check_button(self):
        check = _code(CHECK_SCREEN)
        assert len(re.findall(r"requestLegVerdicts\(", check)) == 1
        body = _ask_the_scouts(check)
        handler = body[body.index("const ask = async"): body.index("return (")]
        assert 'requestLegVerdicts(legs, "check_button", null)' in handler
        assert "onClick={ask}" in body
        assert "useEffect" not in check and "useMemo" not in check
        # Nothing before a tap: the panel draws only after one.
        assert "requestedAtMs !== null" in body

    def test_the_route_admits_the_check_trigger(self):
        assert '"check_button"' in LEG_VERDICTS_ROUTE.read_text(encoding="utf-8")
