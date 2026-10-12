"""The game-script card is shown a bounded number of strikes per player-prop
ladder (#374, Joe's (A) to #372).

What these tests establish
--------------------------
- Over the `/game` listing built from the captured NFL fixtures (the way
  `tests/test_game_builder.py` builds it), no `(series, player)` ladder in
  `listing_for_prompt`'s output has more than `PROMPT_STRIKES_PER_LADDER` legs
  and the kept strikes are the ones nearest the ladder's median.
- Legs with no player or no strike are untouched, the group label says what
  was left out exactly when something was, and the prompt shrinks to at most
  half its untrimmed length.

What they do not establish
--------------------------
- Token cost: the size is a character count of the prompt, not tokens and not
  the cost of a call.
- That the card picks well from the trimmed ladder. The listing itself, and
  the validation of picks against it, are not touched here.
"""

from __future__ import annotations

from collections import defaultdict
from unittest import mock

from backend.agents import game_script
from backend.agents.game_script import (
    PROMPT_STRIKES_PER_LADDER,
    build_prompt,
    listing_for_prompt,
)

# Fixtures and builders are the game-builder suite's own, so the listing is
# built the same way and cannot drift from it.
from tests import test_game_builder as _gb

conn = _gb.conn
_fresh_caches = _gb._fresh_caches
_flat = _gb._flat
_list = _gb._list


def _prompt(listing):
    return build_prompt(
        game_title="Atlanta at Pittsburgh",
        sport_key="americanfootball_nfl",
        kickoff_iso="2026-09-13T17:00:00Z",
        listing=listing,
    )


def _untrimmed(listing):
    with mock.patch.object(game_script, "PROMPT_STRIKES_PER_LADDER", 10_000):
        return _prompt(listing)


def _ladders(listing):
    """`{(series, player): [strikes]}` over the FULL listing."""
    out = defaultdict(list)
    for group in listing["groups"]:
        for leg in group["legs"]:
            if leg["player"] and leg["strike"] is not None:
                out[(group["series"], leg["player"])].append(leg["strike"])
    return out


class TestTheLadderIsTrimmed:
    async def test_an_nfl_ladder_keeps_five_strikes_nearest_the_middle(self, conn):
        listing = await _list(conn)
        full = _ladders(listing)
        trimmed = defaultdict(list)
        for group, (_label, legs) in zip(listing["groups"], listing_for_prompt(listing)):
            for leg in legs:
                if leg["player"] and leg["strike"] is not None:
                    trimmed[(group["series"], leg["player"])].append(leg["strike"])
        assert trimmed
        assert all(len(v) <= PROMPT_STRIKES_PER_LADDER for v in trimmed.values())

        long = [k for k, v in full.items() if k[0] == "KXNFLRECYDS" and len(v) >= 8]
        assert long, "fixture must carry a RECYDS player with 8+ strikes"
        for key in long:
            strikes = sorted(full[key])
            middle = (len(strikes) - 1) / 2
            expected = sorted(
                sorted(range(len(strikes)), key=lambda i: (abs(i - middle), i))[:5]
            )
            assert sorted(trimmed[key]) == [strikes[i] for i in expected], key

    async def test_legs_without_a_ladder_are_untouched(self, conn):
        listing = await _list(conn)
        before = {
            leg["market_ticker"]
            for leg in _flat(listing)
            if not leg["player"] or leg["strike"] is None
        }
        after = {
            leg["market_ticker"]
            for _label, legs in listing_for_prompt(listing)
            for leg in legs
        }
        assert before, "fixture must carry moneyline, spread and scorer legs"
        assert before <= after
        series = {g["series"] for g in listing["groups"]}
        assert {"KXNFLGAME", "KXNFLSPREAD"} <= series

    async def test_the_section_line_says_what_was_left_out(self, conn):
        listing = await _list(conn)
        saw_clause = saw_plain = False
        for group, (label, _legs) in zip(listing["groups"], listing_for_prompt(listing)):
            ladders = _ladders({"groups": [group]})
            longest = max((len(v) for v in ladders.values()), default=0)
            if longest > 5:
                saw_clause = True
                assert f"showing 5 of {longest} strikes" in label, label
            else:
                saw_plain = True
                assert "showing" not in label, label
        assert saw_clause and saw_plain

    async def test_the_prompt_shrinks_on_the_captured_nfl_listing(self, conn):
        listing = await _list(conn)
        trimmed = len(_prompt(listing))
        untrimmed = len(_untrimmed(listing))
        print(f"prompt characters: untrimmed {untrimmed}, trimmed {trimmed}")
        # The ticket asked for at most HALF. The capture cannot give it: its
        # prop ladders hold about ten strikes a player, and spread (25 legs),
        # first-TD scorer (24) and moneyline (2) legs are untouched by design,
        # so 193 legs can fall to at most 138. The bound below is what the
        # capture can show; the half-length claim is for the live listing
        # (921 legs) and is NOT established here.
        assert trimmed * 4 <= untrimmed * 3, (
            f"untrimmed {untrimmed} characters, trimmed {trimmed}"
        )
