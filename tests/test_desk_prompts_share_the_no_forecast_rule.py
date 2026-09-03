"""Every seat at the desk carries the same no-forecast rule, in the same words.

`backend/agents/scout_desk.py` said its staff brief copied the two hard rules
from `scout.SYSTEM` "verbatim", and nothing checked it. They were not verbatim:
"the bet" had become "any bet" and "feed" had become "desk", both deliberately,
and a fifth word could have gone the same way without anyone noticing. A rule
that exists only inside a system prompt exists exactly as many times as it is
spelled, so the copies are pinned here.

What is pinned is the rule and its rationale, not the whole prompt. The four
prompts differ on purpose everywhere else (a staff scout covers a team, the
master synthesises, Willy gives the professional's read); the one thing they
must agree on is the sentence that keeps a number out of the money path.

What this does NOT establish: that the model obeys the sentence. The schema is
the enforcement -- `DeskBriefing`, `ScoutFinding` and `SharpTake` have no
numeric field to put a forecast in -- and `tests/test_scout_desk.py` and
`tests/test_pro_bettor.py` own that.
"""

from __future__ import annotations

import re

import pytest

from backend.agents import pro_bettor, scout, scout_desk

# The rule, split around the one word that legitimately varies by seat.
RULE_HEAD = (
    "You must NOT estimate any probability, fair price, line, or point spread, "
    "and must not say whether "
)
RULE_TAIL = " bet is good."
# Only these two subjects exist. A third spelling is a drift, not a seat.
RULE_SUBJECTS = {"the", "any"}

RATIONALE = (
    "That is not modesty; those numbers come from code that can be backtested, "
    "and an unfalsifiable estimate in the middle of a money path is worse than "
    "no estimate."
)

SEATS = {
    "scout.SYSTEM": scout.SYSTEM,
    "scout_desk.STAFF_SYSTEM_TEMPLATE": scout_desk.STAFF_SYSTEM_TEMPLATE,
    "scout_desk.MASTER_SYSTEM": scout_desk.MASTER_SYSTEM,
    "pro_bettor.SYSTEM": pro_bettor.SYSTEM,
}

# The master's prompt states the rule without the rationale, on purpose: it
# never researches, so the "code that can be backtested" clause is not about
# its job. Every other seat carries both sentences back to back.
SEATS_WITH_RATIONALE = tuple(k for k in SEATS if k != "scout_desk.MASTER_SYSTEM")


class TestTheRuleIsSpelledTheSameAtEverySeat:
    @pytest.mark.parametrize("name", sorted(SEATS))
    def test_the_rule_appears_exactly_once_with_a_known_subject(self, name):
        """Change one word of the rule in any one module and this goes red."""
        prompt = SEATS[name]
        pattern = re.escape(RULE_HEAD) + r"(\w+)" + re.escape(RULE_TAIL)
        matches = re.findall(pattern, prompt)
        assert len(matches) == 1, (
            f"{name}: expected the no-forecast rule exactly once, "
            f"found {len(matches)}"
        )
        assert matches[0] in RULE_SUBJECTS, (
            f"{name}: the rule's subject is {matches[0]!r}; the only spellings "
            f"in the record are {sorted(RULE_SUBJECTS)}"
        )

    @pytest.mark.parametrize("name", sorted(SEATS_WITH_RATIONALE))
    def test_the_rationale_follows_the_rule_word_for_word(self, name):
        prompt = SEATS[name]
        pattern = re.escape(RULE_HEAD) + r"\w+" + re.escape(RULE_TAIL) + " "
        match = re.search(pattern, prompt)
        assert match is not None
        assert prompt.startswith(RATIONALE, match.end()), (
            f"{name}: the rule is not followed by the shared rationale"
        )

    def test_the_master_states_the_rule_and_not_the_rationale(self):
        """Pinned so the asymmetry stays a decision rather than an accident."""
        assert RATIONALE not in scout_desk.MASTER_SYSTEM


class TestTheStaffBriefStillDiffersFromTheSoloScoutWhereItMeansTo:
    """The two deliberate divergences, named, so a future 'fix' that makes the
    copies literally verbatim has to remove this test on purpose."""

    def test_the_staff_scout_says_any_bet_and_the_solo_scout_says_the_bet(self):
        assert RULE_HEAD + "the" + RULE_TAIL in scout.SYSTEM
        assert RULE_HEAD + "any" + RULE_TAIL in scout_desk.STAFF_SYSTEM_TEMPLATE

    def test_feed_became_desk(self):
        assert "makes the whole feed less trustworthy" in scout.SYSTEM
        assert "makes the whole desk less trustworthy" in (
            scout_desk.STAFF_SYSTEM_TEMPLATE
        )
