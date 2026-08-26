"""An unmatched fixture says WHICH kind of unmatched it is.

Live on 2026-08-26 the pass line read `events_unmatched: 525` of 746
discovered. That number is either "college football has stopped resolving" or
"Kalshi lists Division II and the sportsbook feed does not", and those want
opposite responses -- one is an alias file, the other is nobody's action item.
A pooled counter cannot tell them apart, and neither could the refusal reason.

**Why the reason string could not carry it.** `link_event` refuses with
"no sportsbook fixture within the commence-time window" when the books have
nothing at that kickoff. With a handful of concurrent MLB games that branch
fires exactly when the game is not carried. The window is FOUR HOURS, and on a
Saturday college slate dozens of games start inside four hours of each other --
so the branch almost never fires and every out-of-scope fixture lands in
"no team-pair bijection" instead, beside the genuine spelling problems.

Measured against the captured slate: 231 of 339 Kalshi `KXNCAAFGAME` events
have no sportsbook counterpart at all. Reading those as name failures reports a
working league as broken and sends somebody to write 231 alias entries that
cannot help.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That `name_unresolved` is fixable.** It means an in-window fixture already
  resolves one side, so an alias PLAUSIBLY helps. Four fixtures on the captured
  slate are `name_unresolved` and provably unfixable by any alias -- the
  same-state class pinned in `test_ncaaf_names_resolve.py`.
- **Anything about the props or spreads path.** `link_prop_event` inherits its
  game's link and is not classified here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.match.linker import (
    NAME_UNRESOLVED,
    NOT_CARRIED,
    MatchCandidate,
    TeamAliases,
    link_event,
    load_aliases,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SPORT_KEY = "americanfootball_ncaaf"

HOUR = 3_600_000
KICKOFF = 1_787_000_000_000


def _candidate(home: str, away: str, offset_ms: int = 0) -> MatchCandidate:
    return MatchCandidate(
        odds_event_id=f"{away}@{home}",
        commence_ms=KICKOFF + offset_ms,
        home_team=home,
        away_team=away,
    )


def _link(teams, candidates, aliases=None):
    return link_event(
        kalshi_event_ticker="KX-TEST",
        kalshi_teams=teams,
        kalshi_commence_ms=KICKOFF,
        candidates=candidates,
        aliases=aliases or TeamAliases(sport_key=SPORT_KEY),
    )


class TestARefusalNamesItsKind:
    def test_a_match_carries_no_refusal_kind(self):
        result = _link(
            ["Houston", "Seattle"],
            [_candidate("Houston Astros", "Seattle Mariners")],
        )
        assert result.matched
        assert result.refusal_kind is None

    def test_an_empty_window_is_not_carried(self):
        """Nothing at this kickoff at all."""
        result = _link(
            ["Houston", "Seattle"],
            [_candidate("Houston Astros", "Seattle Mariners", offset_ms=9 * HOUR)],
        )
        assert result.refusal_kind == NOT_CARRIED

    def test_a_window_full_of_other_games_is_not_carried(self):
        """The case the reason string could not distinguish.

        Fixtures ARE in the window -- they are simply different games. Before
        `refusal_kind` this returned "no team-pair bijection", which reads as a
        naming problem and is not one.
        """
        result = _link(
            ["Wagner", "Robert Morris"],
            [
                _candidate("TCU Horned Frogs", "North Carolina Tar Heels"),
                _candidate("USC Trojans", "San Jose State Spartans"),
            ],
        )
        assert result.refusal_kind == NOT_CARRIED
        assert "scope, not a naming problem" in (result.reason or "")

    def test_a_fixture_sharing_one_side_is_a_name_problem(self):
        """One side resolves, the other does not: an alias plausibly helps."""
        result = _link(
            ["Stanford", "Hawai'i"],
            [
                _candidate("TCU Horned Frogs", "North Carolina Tar Heels"),
                _candidate("Stanford Cardinal", "Hawaii Rainbow Warriors"),
            ],
        )
        assert result.refusal_kind == NAME_UNRESOLVED
        assert "Add an alias" in (result.reason or "")

    def test_the_reason_names_the_fixture_that_shares_a_side(self):
        """The near-miss sample must be the SHARING fixture, not the first three.

        `link_event` used to print `in_window[:3]`. On the real slate that was
        three unrelated games while the true counterpart sat elsewhere in the
        same window -- observed for `Stanford vs Hawai'i`, whose counterpart
        turned up in a different row's sample. A near-miss list that does not
        contain the near miss cannot be read into an alias entry.
        """
        result = _link(
            ["Stanford", "Hawai'i"],
            [
                _candidate("TCU Horned Frogs", "North Carolina Tar Heels"),
                _candidate("USC Trojans", "San Jose State Spartans"),
                _candidate("Virginia Cavaliers", "NC State Wolfpack"),
                _candidate("Stanford Cardinal", "Hawaii Rainbow Warriors"),
            ],
        )
        assert "Stanford Cardinal" in (result.reason or "")
        assert "TCU Horned Frogs" not in (result.reason or "")


class TestTheSplitOnTheCapturedSlate:
    """The numbers this exists for, on real payloads rather than toys."""

    @pytest.fixture(scope="class")
    def slate(self):
        events = json.loads(
            (FIXTURES / "ncaaf_names_kalshi.json").read_text(encoding="utf-8")
        )["events"]
        books = json.loads(
            (FIXTURES / "ncaaf_names_books.json").read_text(encoding="utf-8")
        )["fixtures"]
        candidates = [
            MatchCandidate(
                odds_event_id=b["id"],
                commence_ms=b["commence_ms"],
                home_team=b["home_team"],
                away_team=b["away_team"],
            )
            for b in books
            if b.get("commence_ms") is not None
        ]
        return events, candidates

    def _split(self, slate, aliases):
        events, candidates = slate
        out: dict[str, int] = {}
        for event in events:
            if event.get("commence_ms") is None:
                continue
            result = link_event(
                kalshi_event_ticker=event["event_ticker"],
                kalshi_teams=event["teams"],
                kalshi_commence_ms=event["commence_ms"],
                candidates=candidates,
                aliases=aliases,
            )
            key = "matched" if result.matched else (result.refusal_kind or "other")
            out[key] = out.get(key, 0) + 1
        return out

    def test_most_college_fixtures_are_not_carried_rather_than_misnamed(self, slate):
        """The headline, and the reason a pooled counter misleads.

        231 of 339 have no counterpart. If those read as name failures, the
        obvious response is to write alias entries, and not one of them would
        change any answer.
        """
        split = self._split(slate, load_aliases(SPORT_KEY))
        assert split[NOT_CARRIED] == 231
        assert split["matched"] == 100
        assert split[NAME_UNRESOLVED] == 8

    def test_the_alias_file_moves_fixtures_out_of_name_unresolved_only(self, slate):
        """An alias can only ever fix the actionable half.

        `not_carried` must be identical with and without the file -- if adding
        aliases changed it, the classifier would be reading names where it
        claims to be reading scope.
        """
        without = self._split(slate, TeamAliases(sport_key=SPORT_KEY))
        with_file = self._split(slate, load_aliases(SPORT_KEY))

        assert without[NOT_CARRIED] == with_file[NOT_CARRIED] == 231
        assert without[NAME_UNRESOLVED] == 15
        assert with_file[NAME_UNRESOLVED] == 8
        assert with_file["matched"] - without["matched"] == 7


class TestTheRunnerActuallyFillsTheSplit:
    """The classifier being right is not the same as the counter being wired.

    **Found by mutation, 2026-08-26.** Disabling the runner's fill left every
    other test in this file green: the classifier tests call `link_event`
    directly, and `test_has_callers` proves the parameter is PASSED but not
    that anything is written into it. A counter that is handed a dict and
    ignores it reads zero forever, which is indistinguishable from a healthy
    slate -- the exact failure the split exists to end.
    """

    def test_link_discovered_events_fills_the_dict_it_is_given(self, tmp_path):
        from backend.kalshi.discovery import DiscoveredEvent
        from backend.runner import link_discovered_events
        from backend.store import db

        conn = db.init_db(tmp_path / "split.db")
        try:
            events = [
                DiscoveredEvent(
                    event_ticker="KXNCAAFGAME-TEST",
                    series_ticker="KXNCAAFGAME",
                    league="NCAA Football",
                    sport_key=SPORT_KEY,
                    market_type="moneyline",
                    title="Wagner vs Robert Morris",
                    commence_ms=KICKOFF,
                    markets=(),
                )
            ]
            split: dict = {}
            link_discovered_events(
                conn, events, now=KICKOFF, unmatched_by_sport=split
            )
        finally:
            conn.close()

        assert split, (
            "the runner was handed a dict and wrote nothing into it. The "
            "parameter is passed (test_has_callers proves that) and ignored."
        )
        assert SPORT_KEY in split, f"keyed on the wrong thing: {sorted(split)}"
        assert sum(split[SPORT_KEY].values()) == 1

    def test_the_split_is_keyed_on_the_sport_key_not_the_competition_string(
        self, tmp_path
    ):
        """`event.league` is Kalshi's 'NCAA Football'; everything else here
        speaks sport keys. Mixing the two is the mismatch that silently
        disabled the parlay ladder's aliases for the desk's whole life."""
        from backend.kalshi.discovery import DiscoveredEvent
        from backend.runner import link_discovered_events
        from backend.store import db

        conn = db.init_db(tmp_path / "split2.db")
        try:
            split: dict = {}
            link_discovered_events(
                conn,
                [
                    DiscoveredEvent(
                        event_ticker="KXNCAAFGAME-TEST2",
                        series_ticker="KXNCAAFGAME",
                        league="NCAA Football",
                        sport_key=SPORT_KEY,
                        market_type="moneyline",
                        title="A vs B",
                        commence_ms=KICKOFF,
                        markets=(),
                    )
                ],
                now=KICKOFF,
                unmatched_by_sport=split,
            )
        finally:
            conn.close()

        assert "NCAA Football" not in split
        assert SPORT_KEY in split


class TestTheCounterReachesThePassLine:
    def test_the_pass_counts_field_exists_and_starts_empty(self):
        from backend.runner import PassCounts

        counts = PassCounts()
        assert counts.unmatched_by_sport == {}

    def test_an_empty_split_is_omitted_from_the_reported_dict(self):
        """`as_dict` reports non-zero fields only, so a quiet pass stays quiet."""
        from backend.runner import PassCounts

        assert "unmatched_by_sport" not in PassCounts().as_dict()

    def test_a_populated_split_is_reported(self):
        from backend.runner import PassCounts

        counts = PassCounts()
        counts.unmatched_by_sport["americanfootball_ncaaf"] = {NOT_CARRIED: 231}
        assert counts.as_dict()["unmatched_by_sport"] == {
            "americanfootball_ncaaf": {NOT_CARRIED: 231}
        }
