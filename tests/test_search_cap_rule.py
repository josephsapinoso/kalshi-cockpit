"""Every search-carrying prompt tells the model its cap and to search one
query per code block (#319, Joe's (A), 2026-10-06).

Why: under `web_search_20260209` a search past the tool's `max_uses` fails
the whole code block and loses every result it held
(`tests/fixtures/anthropic_scout_captured.json`, fourth
`code_execution_tool_result`; `tests/test_agent_web_search_errors.py`). Five
cards in one morning searched up to the cap, lost everything, and reported
"search unavailable". The rule is the fix Joe chose over a bigger cap.

What this establishes: each prompt carries the rule with ITS OWN cap, built
from the same constant that sets the tool's `max_uses`, so the two cannot
drift apart; and the rule says what it must say. What it does not establish:
that the model obeys it. That is read off
`inspect_live_db.py agent-tool-errors` as `server_tool_use_limit` falling,
and nothing here may claim it.
"""

from __future__ import annotations

import pytest

from backend.agents import game_script, leg_verdict, scout_desk
from backend.agents.base import search_cap_rule
from backend.agents.scout import WEB_SEARCH_TOOL


class TestTheRuleSaysWhatItMust:
    def test_it_names_the_cap_and_one_search_per_block(self):
        rule = search_cap_rule(3)
        assert "3 web searches" in rule
        assert "ONE search per code block" in rule
        assert "never loop" in rule
        assert "fails the whole block" in rule
        assert "tool use limit exceeded" in rule

    def test_a_cap_of_one_reads_as_one_search(self):
        assert "one web search for this call" in search_cap_rule(1)
        assert "1 web searches" not in search_cap_rule(1)


PROMPTS = [
    ("game-script card", lambda: game_script.SYSTEM,
     lambda: game_script.GAME_SCRIPT_SEARCH_TOOL["max_uses"]),
    ("T-2h re-check", lambda: game_script.RECHECK_SYSTEM,
     lambda: game_script.RECHECK_SEARCH_TOOL["max_uses"]),
    ("leg verdict", lambda: leg_verdict.SYSTEM,
     lambda: leg_verdict.LEG_VERDICT_SEARCH_TOOL["max_uses"]),
    ("staff scout", lambda: scout_desk.STAFF_SYSTEM_TEMPLATE,
     lambda: WEB_SEARCH_TOOL["max_uses"]),
]


class TestEveryPromptCarriesItsOwnCap:
    @pytest.mark.parametrize("name,prompt,cap", PROMPTS, ids=[p[0] for p in PROMPTS])
    def test_the_prompt_ends_with_the_rule_for_the_tool_it_carries(self, name, prompt, cap):
        text = prompt()
        assert search_cap_rule(int(cap())) in text, name
        # Exactly one cap is stated, and it is the tool's own.
        assert text.count("for this call, and no more") == 1, name

    def test_the_staff_template_still_formats(self):
        rendered = scout_desk.STAFF_SYSTEM_TEMPLATE.format(
            team="Ottawa", opponent="Detroit", venue_clause=scout_desk.HOME_VENUE_CLAUSE
        )
        assert search_cap_rule(int(WEB_SEARCH_TOOL["max_uses"])) in rendered

    def test_the_card_prompt_version_moved_with_the_text(self):
        """A card built under the rule is distinguishable from one built
        without it, so the `game-script-latest-prompt` read can tell them
        apart."""
        assert game_script.PROMPT_VERSION == "5"
        assert game_script.RECHECK_PROMPT_VERSION == "2"
