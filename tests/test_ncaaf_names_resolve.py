"""College football fixtures resolve, and every alias entry earns its place.

Captured 2026-08-26 by `scripts/capture_ncaaf_names.py` from a live Kalshi
slate (339 `KXNCAAFGAME` events) and a live Odds API fixture list (111
fixtures), reduced to names and kickoffs. Wire-format tests load captured
payloads, never hand-constructed ones (CLAUDE.md conventions) -- and the
capture is reduced rather than whole because a NAME test needs no price, and
because the full Kalshi payload was measured at 2.18 MB in a public repo.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That college football is priceable.** On this capture 231 of 339 Kalshi
  fixtures had no sportsbook counterpart at all: Kalshi lists FCS and Division
  II, the odds feed carries roughly FBS. Those drop whatever the alias file
  says, and this file asserts nothing about them.
- **That the alias file is complete.** One capture is one slate.
  `test_no_alias_entry_is_decoration` guards the other direction -- that
  nothing in the file is unnecessary -- which is the failure mode
  `americanfootball_nfl.yaml` already has (5 entries, 0 of them required).
- **That the ambiguous-prefix class is fixable here.** It is not, and
  `test_a_same_state_pair_still_refuses` pins that it stays refused, so nobody
  "fixes" it with a YAML entry that cannot work.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from backend.match.linker import (
    ALIAS_DIR,
    MatchCandidate,
    TeamAliases,
    _bijection,
    link_event,
    load_aliases,
    normalise,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SPORT_KEY = "americanfootball_ncaaf"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def kalshi_events() -> list[dict]:
    events = _load("ncaaf_names_kalshi.json")["events"]
    assert len(events) > 100, (
        f"the capture holds {len(events)} events; a shrunken fixture makes "
        f"every assertion below weaker without failing"
    )
    return events


@pytest.fixture(scope="module")
def book_candidates() -> list[MatchCandidate]:
    fixtures = _load("ncaaf_names_books.json")["fixtures"]
    assert len(fixtures) > 50, f"only {len(fixtures)} book fixtures captured"
    return [
        MatchCandidate(
            odds_event_id=f["id"],
            commence_ms=f["commence_ms"],
            home_team=f["home_team"],
            away_team=f["away_team"],
        )
        for f in fixtures
        if f.get("commence_ms") is not None
    ]


def _linked(events, candidates, aliases) -> set[str]:
    """Event tickers that resolve to a book fixture under these aliases."""
    out: set[str] = set()
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
        if result.matched:
            out.add(event["event_ticker"])
    return out


class TestTheAliasFileIsLoadBearing:
    def test_the_file_exists_and_parses(self):
        path = ALIAS_DIR / f"{SPORT_KEY}.yaml"
        assert path.exists(), (
            "no NCAAF alias file. `load_aliases` returns an EMPTY mapping for a "
            "missing file rather than raising, so its absence is silent -- "
            "which is the whole failure this file exists to prevent."
        )
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        assert raw.get("teams"), "the file parses but declares no teams"

    def test_the_aliases_link_fixtures_that_would_otherwise_be_refused(
        self, kalshi_events, book_candidates
    ):
        """The file must buy something, and the delta names what."""
        without = _linked(
            kalshi_events, book_candidates, TeamAliases(sport_key=SPORT_KEY)
        )
        with_file = _linked(kalshi_events, book_candidates, load_aliases(SPORT_KEY))

        assert without < with_file, (
            f"the alias file linked no additional fixture "
            f"({len(without)} without, {len(with_file)} with). Either the "
            f"entries are decoration or the capture no longer contains the "
            f"fixtures they were derived from."
        )

    #: Exactly which fixtures the alias file rescues on the captured slate.
    #: Seven, from six entries -- `Hawai'i` appears in two of them.
    RESCUED = frozenset(
        {
            "KXNCAAFGAME-26AUG29HAWSTAN",     # Hawai'i
            "KXNCAAFGAME-26SEP05UNLVHAW",     # Hawai'i again
            "KXNCAAFGAME-26AUG29NCSTUVA",     # North Carolina St.
            "KXNCAAFGAME-26SEP03ALBYBUFF",    # University at Albany
            "KXNCAAFGAME-26SEP04MIASTAN",     # Miami (FL)
            "KXNCAAFGAME-26SEP05HCURICE",     # Houston Christian
            "KXNCAAFGAME-26SEP05ULMMSST",     # Louisiana-Monroe
        }
    )

    def test_the_alias_file_rescues_exactly_these_fixtures(
        self, kalshi_events, book_candidates
    ):
        """A population count, not a direction.

        `test_the_aliases_link_fixtures_that_would_otherwise_be_refused` only
        asserts the file buys SOMETHING, and `test_no_alias_entry_is_decoration`
        only asserts nothing is surplus. Between them sits the case neither
        catches and the one most likely to happen: an entry silently DROPPED.
        Verified by mutation, 2026-08-26 -- deleting `Hawai'i` left every other
        assertion in this file green.

        Naming the set makes a lost entry a red test that says which fixture
        went with it. Same shape as CLAUDE.md's "count your tests": a
        denominator nobody printed is a denominator nobody checked.

        This pins the CAPTURED slate, deliberately. Re-running the capture
        replaces both the fixture and this set, together.
        """
        without = _linked(
            kalshi_events, book_candidates, TeamAliases(sport_key=SPORT_KEY)
        )
        with_file = _linked(kalshi_events, book_candidates, load_aliases(SPORT_KEY))
        rescued = with_file - without

        assert rescued == self.RESCUED, (
            f"the alias file no longer rescues the same fixtures. "
            f"lost: {sorted(self.RESCUED - rescued)}; "
            f"gained: {sorted(rescued - self.RESCUED)}. "
            f"An entry was dropped, or the capture was re-run without updating "
            f"RESCUED. Both are real changes; neither should be silent."
        )

    def test_no_alias_entry_is_decoration(self, kalshi_events, book_candidates):
        """Every entry, removed on its own, must cost at least one fixture.

        `americanfootball_nfl.yaml` is the cautionary case: 5 entries, and the
        token-prefix rule resolves all 5 without them. An alias file that does
        nothing still reads as though the matching problem were handled.
        """
        full = load_aliases(SPORT_KEY)
        baseline = _linked(kalshi_events, book_candidates, full)

        decorative: list[str] = []
        for key in list(full.mapping):
            reduced = TeamAliases(
                sport_key=SPORT_KEY,
                mapping={k: v for k, v in full.mapping.items() if k != key},
            )
            if _linked(kalshi_events, book_candidates, reduced) == baseline:
                decorative.append(key)

        assert not decorative, (
            f"these entries change nothing on the captured slate: "
            f"{decorative}. Delete them, or re-derive the file with "
            f"scripts/capture_ncaaf_names.py -- an entry kept 'just in case' "
            f"is how a short file becomes a long one."
        )


class TestTheResolverStillRefusesWhatItShould:
    def test_a_same_state_pair_still_refuses(self):
        """No alias can fix a name that is a prefix of both book teams.

        `Iowa` is a token-prefix of BOTH `Iowa Hawkeyes` and
        `Iowa State Cyclones`, so `_matches` is true twice and `_bijection`
        refuses as ambiguous. That refusal is correct -- it is the guard that
        stops one team's line pricing another team's market -- and adding an
        alias for the longer name does not help, because the short name still
        matches both.

        Pinned so nobody spends an afternoon adding YAML that cannot work.
        Verified 2026-08-26 on the real slate for Texas/Texas St.,
        Washington/Washington St., Iowa/Iowa St. and Florida/Florida Atlantic.
        """
        aliases = TeamAliases(
            sport_key=SPORT_KEY,
            mapping={normalise("Iowa St."): normalise("Iowa State Cyclones")},
        )
        candidate = MatchCandidate(
            odds_event_id="x",
            commence_ms=0,
            home_team="Iowa Hawkeyes",
            away_team="Iowa State Cyclones",
        )
        assert not _bijection(["Iowa", "Iowa St."], candidate, aliases), (
            "the ambiguous-prefix pair resolved. If the resolver changed, this "
            "test is the record of what it used to refuse and why -- re-read "
            "the reasoning before deleting it."
        )


class TestEveryInScopeLeagueHasBeenDecidedAbout:
    """A missing alias file must be a decision, not an accident.

    This is the general form of the defect that hid for the life of the parlay
    desk: `load_aliases` treats "no file" as "no overrides needed", which is
    correct behaviour and indistinguishable from "nobody has looked". Naming
    the leagues that genuinely need none turns the second case red.
    """

    #: Leagues carrying game-level markets where the deterministic rule has
    #: been checked and needs no help. Adding a key here is a claim; check it
    #: with a capture before making it.
    NEEDS_NO_OVERRIDES = frozenset(
        {"basketball_nba", "basketball_wnba", "icehockey_nhl"}
    )

    def test_each_in_scope_league_has_a_file_or_is_named_as_needing_none(self):
        from backend.kalshi.discovery import IN_SCOPE_LEAGUES

        unexplained = [
            sport_key
            for sport_key in sorted(set(IN_SCOPE_LEAGUES.values()))
            if not (ALIAS_DIR / f"{sport_key}.yaml").exists()
            and sport_key not in self.NEEDS_NO_OVERRIDES
        ]
        assert not unexplained, (
            f"{unexplained} are in scope with no alias file and no recorded "
            f"decision that they need none. `load_aliases` will return an "
            f"empty mapping and the league will resolve on prefix alone, "
            f"silently."
        )

    def test_the_needs_none_set_names_no_league_that_has_a_file(self):
        """The set and the directory must not both claim the same league."""
        both = [
            sport_key
            for sport_key in self.NEEDS_NO_OVERRIDES
            if (ALIAS_DIR / f"{sport_key}.yaml").exists()
        ]
        assert not both, (
            f"{both} have an alias file AND are listed as needing none. One of "
            f"the two is wrong and the reader cannot tell which."
        )
