"""NFL fixtures resolve without an alias file, and every franchise is covered.

Captured 2026-09-06 by `scripts/capture_team_names.py --league nfl` from a live
Kalshi slate and a live Odds API fixture list, reduced to names and kickoffs.
Wire-format tests load captured payloads, never hand-constructed ones (CLAUDE.md
conventions).

**Why this was taken.** `backend/match/aliases/americanfootball_nfl.yaml` had
five entries whose header documented the **Kalshi** side from a real capture --
the book side had never been paired against a live feed. The 2026 season opened
2026-09-09 and the pairing is unrecoverable afterwards: a Week 1 board that
renders unmatched is a board with no prices on the one weekend it matters.

**The answer is that the alias file is not needed, and this is a census rather
than a sample.** All 32 open `KXNFLGAME` events linked with NO alias file at
all, and all 32 franchises appear on both sides -- so there is no team left to
be surprised by. That is a stronger result than NCAAF's, where the file rescues
seven fixtures, and it is the expected one: 32 well-known franchises against
Kalshi's city-name convention, which the token-prefix rule resolves within a
single fixture's two teams.

**The one claim in the file that was refuted.** Its header called
`Washington: Washington Commanders` "a genuine override". It is not: the
baseline run links Washington's fixture with the alias file absent. All five
entries are documentation of the pattern, none is load-bearing, and the header
now says so.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That a linked fixture is a priced one.** Linking is name resolution. What
  a market costs, whether the book is two-sided and whether the devig succeeds
  are all downstream and untouched here.
- **That the capture covers the season.** It holds two weeks of Kalshi events
  (2026-09-10 to 2026-09-22 kickoffs). Every franchise appears in that window,
  which is what makes it a census over TEAMS -- it is not one over fixtures,
  and a mid-season Kalshi rename would not be caught by it.
- **That preseason is handled.** It is excluded, by production's own
  `classify_series`, because `KXNFLGAME` carries both populations under one
  series ticker. This says nothing about preseason names.
- **Anything about spreads, totals or props.** Names only.
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
    link_event,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SPORT_KEY = "americanfootball_nfl"

#: There are 32 NFL franchises. The number is the point of several assertions
#: below, so it is named once rather than repeated as a literal.
FRANCHISES = 32


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def kalshi_events() -> list[dict]:
    events = _load("nfl_names_kalshi.json")["events"]
    assert len(events) >= FRANCHISES, (
        f"the capture holds {len(events)} events; a shrunken fixture makes "
        f"every assertion below weaker without failing"
    )
    return events


@pytest.fixture(scope="module")
def book_candidates() -> list[MatchCandidate]:
    fixtures = _load("nfl_names_books.json")["fixtures"]
    assert len(fixtures) > 100, f"only {len(fixtures)} book fixtures captured"
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


class TestTheDeterministicRuleIsEnough:
    def test_every_captured_fixture_links_with_no_alias_file(
        self, kalshi_events, book_candidates
    ):
        """The headline, and the reason nothing was added to the YAML.

        Run with an EMPTY `TeamAliases`, not with the file on disk: the
        question is whether the deterministic token-prefix rule carries the
        league on its own. Asserting with the file loaded would pass either
        way and would tell nobody which half did the work.
        """
        linked = _linked(
            kalshi_events, book_candidates, TeamAliases(sport_key=SPORT_KEY)
        )
        unresolved = sorted(
            e["event_ticker"] for e in kalshi_events
            if e["event_ticker"] not in linked
        )
        # Named, never summarised. A count says "some Week 1 games will not
        # price"; the list says which, and is what an alias entry is derived
        # from.
        assert not unresolved, (
            f"{len(unresolved)} NFL fixtures do not resolve without aliases: "
            f"{unresolved}. Derive the entries with "
            f"`scripts/capture_team_names.py --league nfl`; do not guess them."
        )
        assert len(linked) == len(kalshi_events)


class TestTheCaptureIsACensusOverTeams:
    """Why "all fixtures linked" is a strong claim here and not a lucky slate.

    Thirty-two franchises, each appearing at least once in the captured
    window, means no NFL team is outside the population that just resolved.
    Without this, "32 of 32 linked" would be compatible with a slate that
    happened to omit the awkward names.
    """

    def test_all_thirty_two_franchises_appear_on_the_kalshi_side(
        self, kalshi_events
    ):
        names = {team for event in kalshi_events for team in event["teams"]}
        assert len(names) == FRANCHISES, (
            f"{len(names)} distinct Kalshi team names, expected {FRANCHISES}. "
            f"Fewer means the capture is not a census and the linking result "
            f"cannot be read as covering the league: {sorted(names)}"
        )

    def test_all_thirty_two_franchises_appear_on_the_book_side(self):
        fixtures = _load("nfl_names_books.json")["fixtures"]
        names = {
            fixture[side]
            for fixture in fixtures
            for side in ("home_team", "away_team")
            if fixture.get(side)
        }
        assert len(names) == FRANCHISES, (
            f"{len(names)} distinct book team names, expected {FRANCHISES}: "
            f"{sorted(names)}"
        )


class TestTheAliasFileIsDocumentationNotMachinery:
    """The opposite finding from NCAAF's, pinned so it is not mistaken.

    `test_ncaaf_names_resolve.py` asserts its alias file *rescues* fixtures.
    The NFL file rescues none, and that is the correct state rather than a
    defect. Someone reading the NCAAF test and copying its shape would
    otherwise "fix" this file by inventing entries, so what is pinned here is
    that the file parses and carries its own provenance -- the "rescues
    nothing" half is not assertable on this capture, for the reason recorded
    below.
    """

    def test_the_file_exists_and_parses(self):
        path = ALIAS_DIR / f"{SPORT_KEY}.yaml"
        assert path.exists()
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        assert raw.get("teams"), "the file parses but declares no teams"

    # **A test was deleted from here, and the deletion is the finding.**
    # `test_the_file_rescues_nothing_on_this_capture` asserted
    # `without == with_file` -- the linked set with an empty alias mapping
    # against the set with the file on disk. It passed, and it could not have
    # done anything else: an alias can only ADD a link, `without` is already
    # all 32 events, so the two sets are equal by arithmetic whatever the YAML
    # says. Mutating an entry to `Washington: Denver Broncos` left it green,
    # which is how it was caught.
    #
    # The property it was reaching for is real and is already established one
    # class up: `test_every_captured_fixture_links_with_no_alias_file` runs
    # the baseline with `TeamAliases(sport_key=...)` and passes, and a file
    # cannot rescue a fixture that resolves without it. Keeping both would
    # have left a test that can never fail sitting next to the one doing the
    # work -- and an unfalsifiable assertion is worse than an absent one,
    # because it reads as coverage.

    def test_the_header_says_when_it_was_derived_and_against_what(self):
        """The file must carry its own provenance, not a claim about itself.

        **This replaced a copy guard that failed on its own correction.** The
        first version forbade the phrase "genuine override", which the header
        had used about Washington and which the baseline run refutes. But the
        corrected header *quotes* the refuted phrase in order to record what
        was wrong -- so the guard tripped on the history rather than on the
        claim, exactly as the combo guard tripped on an `ADR 0012 s5`
        citation the same week. A guard whose first finding is a false one
        gets switched off.

        What is worth pinning is not the absence of a sentence but the
        presence of a source. An alias file's entries are only trustworthy if
        someone can see when they were paired and against what, and every
        wrong claim this file has carried was one nobody could date.
        """
        text = (ALIAS_DIR / f"{SPORT_KEY}.yaml").read_text(encoding="utf-8")

        assert "DERIVED AND VERIFIED" in text, (
            "the NFL alias header no longer states that it was derived from a "
            "live capture. Entries whose provenance is not on the file are "
            "indistinguishable from guesses, which is the failure "
            "`discovery.py:231-234` records for two whole leagues."
        )
        assert "capture_team_names.py --league nfl" in text, (
            "the header must name the instrument, so the pairing can be "
            "re-run rather than re-reasoned."
        )
