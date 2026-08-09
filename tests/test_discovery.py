"""Discovery tests, against the real captured payload.

The classifier decides which leagues are priceable at all, so a bug here does
not surface as an error — it surfaces as a league quietly missing from the
Board. These tests run against `events_sports_nested.json` rather than
invented events, so a Kalshi metadata change breaks them instead of silently
emptying the universe.
"""

from __future__ import annotations

import collections
import logging

import pytest

from conftest import load_fixture
from backend.kalshi.discovery import (
    CLASSIFIED_LEAGUES,
    EXCLUDED_SCOPES,
    FIXTURE_SCOPES,
    IN_SCOPE_LEAGUES,
    NON_FIXTURE_SCOPES,
    OUT_OF_SCOPE_LEAGUES,
    PERIOD_SCOPES,
    classify_series,
    coverage_by_league,
    discover_from_events,
    event_commence_ms,
    parse_ms,
)


@pytest.fixture(scope="module")
def events():
    return load_fixture("events_sports_nested.json")


@pytest.fixture(scope="module")
def preseason_capture():
    """`GET /events?series_ticker=KXNFLGAME`, captured 2026-08-09.

    A separate capture from `events_sports_nested.json` because that one -- a
    walk of the whole sports universe on 2026-08-06 -- contains no preseason
    market, which is exactly why every test in this file passed while the league
    classifier was dropping 48 events and 726 markets.
    See `scripts/capture_preseason_fixture.py`.
    """
    return load_fixture("events_nfl_preseason.json")


@pytest.fixture(scope="module")
def preseason_events(preseason_capture):
    return preseason_capture["events"]


def _leagues_in(events):
    return {
        ((e.get("product_metadata") or {}).get("competition") or "").strip()
        for e in events
    } - {""}


@pytest.fixture(scope="module")
def discovered(events):
    return discover_from_events(events)


class TestSeriesClassification:
    def test_game_series_are_recognised_as_game_level(self, events):
        for event in events:
            if (event.get("series_ticker") or "") == "KXMLBGAME":
                assert classify_series(event).is_game_level
                return
        pytest.fail("fixture has no KXMLBGAME event")

    def test_futures_series_are_not_game_level(self, events):
        """`KXNBA` is the championship winner -- one market, whole season."""
        for event in events:
            if (event.get("series_ticker") or "") == "KXNBA":
                assert not classify_series(event).is_game_level
                return
        pytest.fail("fixture has no KXNBA futures event")

    @pytest.mark.parametrize(
        "series,expected_type",
        [
            ("KXMLBGAME", "moneyline"),
            ("KXMLBSPREAD", "spread"),
            ("KXMLBTOTAL", "total"),
            ("KXWNBAGAME", "moneyline"),
        ],
    )
    def test_market_type_comes_from_the_series_suffix(
        self, events, series, expected_type
    ):
        for event in events:
            if (event.get("series_ticker") or "") == series:
                assert classify_series(event).market_type == expected_type
                return
        pytest.skip(f"fixture has no {series} event")

    def test_scope_is_read_from_metadata_not_inferred(self):
        """`competition_scope` is authoritative; the suffix is only a fallback."""
        event = {
            "series_ticker": "KXMLBGAME",
            "product_metadata": {
                "competition": "Pro Baseball",
                "competition_scope": "Season",
            },
        }
        assert not classify_series(event).is_game_level

    def test_an_unknown_league_is_out_of_scope_not_an_error(self):
        """No consensus to devig against means not priceable, not broken."""
        info = classify_series(
            {
                "series_ticker": "KXLOLGAME",
                "product_metadata": {
                    "competition": "League of Legends",
                    "competition_scope": "Game",
                },
            }
        )
        assert info.is_game_level
        assert info.sport_key is None
        assert not info.in_scope


class TestMetadataDrift:
    """Fail loudly when Kalshi uses a label we do not classify.

    This class exists because of a real bug. The first version of the
    classifier tested `scope == "game"` and spelled the leagues by guesswork
    ("Womens Pro Basketball", "College Football"). Kalshi actually emits
    `Spread`, `Point Total`, `Pro Basketball (W)`, `NCAA Football`. The effect
    was that **every spread and total, plus WNBA and NCAAF entirely, silently
    vanished from the universe** -- and the rest of this file passed anyway,
    because it only asserted that the things which *did* survive looked right.

    An exclusion must be a decision, never an accident.
    """

    def test_every_scope_in_the_fixture_is_explicitly_classified(self, events):
        scopes = {
            ((e.get("product_metadata") or {}).get("competition_scope") or "").lower()
            for e in events
        }
        known = FIXTURE_SCOPES | EXCLUDED_SCOPES | {""}
        unknown = scopes - known
        assert not unknown, (
            f"unclassified competition_scope value(s): {sorted(unknown)}. "
            f"Add each to FIXTURE_SCOPES (per-fixture, priceable), "
            f"NON_FIXTURE_SCOPES (futures/awards) or PERIOD_SCOPES "
            f"(per-fixture but sub-game). Leaving one unclassified silently "
            f"drops those markets."
        )

    def test_every_league_in_the_captures_is_explicitly_classified(
        self, events, preseason_events
    ):
        """The scope test's twin, on the axis that had no test at all.

        `competition_scope` had a drift test and an aggregated warning.
        `competition` had neither, and the same failure happened one value over:
        `IN_SCOPE_LEAGUES` says `"Pro Football"`, Kalshi spells preseason
        `"Pro Football Preseason"`, and 48 events / 726 markets left the universe
        without a warning, a counter or a red test.

        It runs over **both** captures on purpose. The 2026-08-06 walk contains
        no preseason market, so on that fixture alone this test would have been
        green throughout the bug -- which is this repo's lesson that a
        fixture-based test protects against the API changing, not against
        misreading it on day one.
        """
        leagues = _leagues_in(events) | _leagues_in(preseason_events)
        unknown = leagues - CLASSIFIED_LEAGUES
        assert not unknown, (
            f"unclassified competition value(s): {sorted(unknown)}. Add each to "
            f"IN_SCOPE_LEAGUES (with its Odds API sport key) or to "
            f"OUT_OF_SCOPE_LEAGUES (with the reason it is declined). Leaving one "
            f"unclassified silently drops every game-level market in it."
        )

    def test_the_two_league_maps_do_not_overlap(self):
        """A league cannot be both priced and declined.

        An overlap would make the answer depend on lookup order, and
        `sport_key` reads `IN_SCOPE_LEAGUES` while the warning reads both -- so
        the contradiction would resolve as "priced, and silently".
        """
        assert not (set(IN_SCOPE_LEAGUES) & set(OUT_OF_SCOPE_LEAGUES))
        assert CLASSIFIED_LEAGUES == set(IN_SCOPE_LEAGUES) | set(
            OUT_OF_SCOPE_LEAGUES
        )

    def test_every_declined_league_states_a_reason(self):
        """The map's whole value is the reason column.

        Without it, `OUT_OF_SCOPE_LEAGUES` is a mute list and adding a name to it
        becomes the cheapest way to silence the warning -- the reflex the module
        comment forbids. A reason has to cost something to write.
        """
        for league, reason in OUT_OF_SCOPE_LEAGUES.items():
            assert isinstance(reason, str)
            assert len(reason.split()) >= 8, (
                f"{league!r} is declined with a reason too short to be one: "
                f"{reason!r}"
            )

    def test_declining_a_league_does_not_change_what_is_priced(self):
        """`OUT_OF_SCOPE_LEAGUES` records a decision; it must not make one.

        The map is documentation plus a warning filter. If it ever fed
        `sport_key`, moving a league between the maps would silently change the
        population in the evidence record -- the failure ADR 0011 is about.
        """
        for league in OUT_OF_SCOPE_LEAGUES:
            info = classify_series(
                {
                    "series_ticker": "KXFAKEGAME",
                    "product_metadata": {
                        "competition": league,
                        "competition_scope": "Game",
                    },
                }
            )
            assert info.is_game_level, league
            assert info.sport_key is None, f"{league} acquired a sport key"
            assert not info.in_scope, league

    def test_spread_and_total_scopes_count_as_per_fixture(self):
        """The exact bug: spreads and totals resolve on one fixture."""
        assert "spread" in FIXTURE_SCOPES
        assert "point total" in FIXTURE_SCOPES

    def test_in_scope_league_names_match_what_kalshi_actually_sends(self, events):
        """Guards against tidying a league string into one Kalshi never emits.

        Any league we claim to support must appear verbatim in real data, or
        the mapping is aspirational and the league is silently absent.
        """
        seen = {
            (e.get("product_metadata") or {}).get("competition")
            for e in events
        }
        seen.discard(None)
        supported_and_present = seen & set(IN_SCOPE_LEAGUES)
        assert supported_and_present, (
            f"none of the configured leagues {sorted(IN_SCOPE_LEAGUES)} appear "
            f"in the captured data, which contains {sorted(seen)}. The mapping "
            f"keys must be Kalshi's exact spelling."
        )

    def test_wnba_and_ncaaf_are_reachable(self, events):
        """Both were dropped by a misspelled mapping key."""
        seen = {
            (e.get("product_metadata") or {}).get("competition") for e in events
        }
        for league in ("Pro Basketball (W)", "NCAA Football"):
            if league in seen:
                assert league in IN_SCOPE_LEAGUES, f"{league} present but unmapped"


class TestNflPreseasonIsExcludedByDecisionNotByOmission:
    """The league the map missed, pinned against a real capture.

    `IN_SCOPE_LEAGUES` says `"Pro Football"`. Kalshi spells NFL preseason
    `"Pro Football Preseason"`, which is a different string, so 48 events and
    726 markets were dropped from the universe with **no warning, no counter and
    no failing test** -- exactly the failure the comment four lines above
    `IN_SCOPE_LEAGUES` already recorded for `"Pro Basketball (W)"` and
    `"NCAA Football"`.

    Preseason stays out. What changes is that it is out *on purpose*: the reason
    is in `OUT_OF_SCOPE_LEAGUES`, and a league nobody has looked at is now as
    loud on this axis as an unrecognised scope has been on the other.

    Whether to trade it is Joe's call, not this file's. The tests below assert
    the current answer and the machinery around it, not that the answer is right.
    """

    def test_the_capture_contains_the_case_it_was_captured_for(
        self, preseason_capture, preseason_events
    ):
        """A truncated or out-of-season re-capture must fail here, loudly.

        `scripts/capture_preseason_fixture.py` re-run in November returns
        regular-season events only. That fixture would still parse, still be
        real, and would silently stop testing the thing it exists to test --
        which is how this fixture's older sibling stayed green through the bug.
        """
        assert preseason_capture["series_ticker"] == "KXNFLGAME"
        assert preseason_capture["captured_at"]
        assert len(preseason_events) >= 32, (
            f"{len(preseason_events)} events; the capture is short of the 32 "
            f"that KXNFLGAME returned on 2026-08-09"
        )
        by_league = collections.Counter(
            (e["product_metadata"] or {}).get("competition") for e in preseason_events
        )
        assert by_league["Pro Football Preseason"] >= 16, by_league
        assert by_league["Pro Football"] >= 16, by_league

    def test_one_series_ticker_carries_both_populations(self, preseason_events):
        """The fact that makes inclusion a schema problem, not a config flag.

        Preseason and the regular season share `KXNFLGAME` and both read
        `competition_scope == "Game"`. Neither the series nor the scope can tell
        them apart -- only `product_metadata.competition` does. The evidence
        record stores neither: `recommendations` keys on `ticker`, and the one
        league cut in the analysis path joins out through
        `kalshi_series.league`, which is **one row per series**. So a switch to
        including preseason would relabel both populations with a single value.
        """
        pairs = {
            (
                e.get("series_ticker"),
                (e["product_metadata"] or {}).get("competition"),
                (e["product_metadata"] or {}).get("competition_scope"),
            )
            for e in preseason_events
        }
        assert pairs == {
            ("KXNFLGAME", "Pro Football", "Game"),
            ("KXNFLGAME", "Pro Football Preseason", "Game"),
        }, sorted(pairs)

    def test_preseason_is_game_level_and_still_not_priced(self, preseason_events):
        """Not excluded as junk. Excluded as a population.

        The distinction matters: these are real per-fixture moneylines that the
        classifier recognises as game-level and declines anyway. Asserting only
        `not in_scope` would also pass if the scope filter had thrown them out
        for the wrong reason.
        """
        preseason = [
            e
            for e in preseason_events
            if (e["product_metadata"] or {}).get("competition")
            == "Pro Football Preseason"
        ]
        assert preseason
        for event in preseason:
            info = classify_series(event)
            assert info.is_game_level, event["event_ticker"]
            assert info.market_type == "moneyline"
            assert info.sport_key is None, "preseason acquired a sport key"
            assert not info.in_scope

    def test_discovery_keeps_the_regular_season_and_drops_preseason(
        self, preseason_events
    ):
        """The population boundary, asserted on the output rather than the map."""
        discovered = discover_from_events(preseason_events)
        assert {e.league for e in discovered} == {"Pro Football"}
        assert len(discovered) == 16

    def test_a_classified_league_warns_about_nothing(self, preseason_events, caplog):
        """The decision is recorded, so the log stops repeating it.

        Same rule as `PERIOD_SCOPES`: a warning naming an action item already
        answered is one readers learn to skip, and this line shares a stream with
        boot lines that three sessions could not read.
        """
        with caplog.at_level(logging.INFO, logger="backend.kalshi.discovery"):
            discover_from_events(preseason_events)

        assert not [
            r for r in caplog.records if "unclassified" in r.getMessage()
        ], [r.getMessage() for r in caplog.records]
        summaries = [
            r.getMessage() for r in caplog.records if "discovery:" in r.getMessage()
        ]
        # The count has to agree with the silence, or the two halves of the
        # reporting contradict each other and neither can be trusted.
        assert len(summaries) == 1
        assert "unknown_leagues=0" in summaries[0], summaries[0]

    def test_the_preseason_spelling_is_pinned_verbatim(self):
        """Guards the string itself, which is the whole bug.

        Tidying it to "NFL Preseason" or "Pro Football (Preseason)" would restore
        the silent drop and every other test here would stay green, because they
        all read the same constant.
        """
        assert "Pro Football Preseason" in OUT_OF_SCOPE_LEAGUES
        assert "Pro Football" in IN_SCOPE_LEAGUES


class TestUnclassifiedLeaguesAreAnnouncedOncePerProcess:
    """The `competition` twin of the `competition_scope` warning.

    An unrecognised scope produced an aggregated warning, a per-pass counter and
    a red drift test. An unrecognised **league** produced none of the three: it
    was simply absent from the Board. That asymmetry is what let
    `"Pro Football Preseason"` cost 48 events and 726 markets in silence.

    The volume constraint is the same one that shaped its twin and is not
    negotiable. Discovery runs on every pass -- every ~22s on the quote cadence
    -- into a 100-line log buffer, and this repo has already put 962 lines into
    that buffer once and hidden its own boot lines. **A logging rate is a
    property of the caller, not of the code.** So: one line per process, never
    per pass, asserted by running the classifier repeatedly in one process and
    counting the lines.
    """

    def _events(self, ticker, league, n, scope="Game"):
        """`n` separate EVENTS in one series, in an unclassified league.

        Events rather than markets, for the reason recorded on the scope tests:
        `classify_series` runs once per event, so one event with twelve markets
        warns once no matter what the code does.
        """
        return [
            {
                "event_ticker": f"{ticker}-26AUG07-{i}",
                "series_ticker": ticker,
                "product_metadata": {
                    "competition": league,
                    "competition_scope": scope,
                },
                "markets": [
                    {"ticker": f"{ticker}-26AUG07-{i}-A", "yes_sub_title": "A"}
                ],
            }
            for i in range(n)
        ]

    def _lines(self, caplog):
        return [
            r.getMessage() for r in caplog.records if "unclassified" in r.getMessage()
        ]

    def test_an_unclassified_league_is_named(self, caplog):
        with caplog.at_level(logging.WARNING, logger="backend.kalshi.discovery"):
            discover_from_events(self._events("KXKORFGAME", "Korea K League 1", 4))

        lines = self._lines(caplog)
        assert len(lines) == 1, lines
        assert "'Korea K League 1'" in lines[0]
        assert "KXKORFGAME" in lines[0]

    def test_one_league_across_many_series_is_named_once(self, caplog):
        """Dedupe is per league, not per (series, league).

        Kalshi lists one league across a moneyline, a spread and a total series
        -- `KXNFLGAME`, `KXNFLSPREAD`, `KXNFLTOTAL` all carry
        `"Pro Football Preseason"`. A per-pair key would say the same thing three
        times and grow with every market type Kalshi ships.
        """
        events = [
            *self._events("KXFAKEGAME", "Fake League", 3),
            *self._events("KXFAKESPREAD", "Fake League", 3, scope="Spread"),
            *self._events("KXFAKETOTAL", "Fake League", 3, scope="Point Total"),
        ]
        with caplog.at_level(logging.WARNING, logger="backend.kalshi.discovery"):
            discover_from_events(events)

        lines = self._lines(caplog)
        assert len(lines) == 1, lines
        # All three series are still evidence of where it was seen.
        assert "KXFAKEGAME +2" in lines[0], lines[0]

    def test_the_line_count_does_not_grow_with_the_population(self, caplog):
        """The property the whole aggregation exists for.

        Live carries ~100 unclassified game-level leagues. A per-league line
        would be 100 records into a 100-line buffer on the first pass of every
        fresh process, and would take the `discovery:` summary behind it as
        collateral -- measured, on the scope axis, on 2026-08-09.
        """
        events = []
        for i in range(300):
            events.extend(self._events(f"KXL{i}GAME", f"League {i}", 2))

        with caplog.at_level(logging.WARNING, logger="backend.kalshi.discovery"):
            discover_from_events(events)

        lines = self._lines(caplog)
        assert len(lines) == 1, f"{len(lines)} lines for 300 unclassified leagues"
        assert "300 unclassified" in lines[0]
        # Named, but capped -- an action item running to hundreds is not one.
        assert "and 260 more" in lines[0], lines[0]

    def test_a_repeated_league_is_named_once_for_the_life_of_the_process(
        self, caplog
    ):
        """One line per process, never per pass. Discovery runs every ~22s.

        This is the assertion the task called for by name: run the classifier
        repeatedly in one process and count the lines. Re-warning per pass is
        what put 98 of the 100 lines in the live log buffer and buried
        `[migrate] ...` and `API starting: ...` so completely that neither could
        be read from production.
        """
        events = self._events("KXKORFGAME", "Korea K League 1", 4)
        with caplog.at_level(logging.WARNING, logger="backend.kalshi.discovery"):
            discover_from_events(events)
            first = len(self._lines(caplog))
            for _ in range(60):
                discover_from_events(events)
            after = len(self._lines(caplog))

        assert first == 1
        assert after == 1, f"{after - first} lines repeated across 60 later passes"

    def test_a_league_first_seen_on_a_later_pass_is_still_named(self, caplog):
        """Aggregation must not become "warn at boot and then go quiet".

        The guarantee is per league, not per process-start: a value nobody has
        named gets named on whichever pass first sees it. Kalshi lists preseason
        in late July and NCAAF in August -- a new league genuinely appears
        mid-process.
        """
        first = self._events("KXAGAME", "League A", 3)
        later = [*first, *self._events("KXBGAME", "League B", 3)]

        with caplog.at_level(logging.WARNING, logger="backend.kalshi.discovery"):
            discover_from_events(first)
            discover_from_events(later)

        lines = self._lines(caplog)
        assert len(lines) == 2, lines
        assert "'League A'" in lines[0] and "'League B'" not in lines[0]
        # The second line carries only what is new. Re-naming the first would
        # rebuild the per-pass repeat one aggregation level up.
        assert "'League B'" in lines[1]
        assert "'League A'" not in lines[1], lines[1]

    def test_a_league_with_no_game_level_markets_is_not_an_action_item(
        self, caplog
    ):
        """`House` and `Tesla Inc.` carry a `competition` too.

        352 distinct league strings live, ~100 of them with a game-level market.
        The question this warning asks is "should this league be devigged
        against?", which only exists where there is a fixture to price. Naming
        elections and equities is how the line becomes unreadable -- the failure
        the aggregation exists to prevent, arrived at from the other side.
        """
        events = [
            *self._events("KXHOUSE", "House", 3, scope="Season"),
            *self._events("KXNFLMVP", "Fantasy League", 3, scope="Awards"),
        ]
        with caplog.at_level(logging.INFO, logger="backend.kalshi.discovery"):
            discover_from_events(events)

        assert not self._lines(caplog), self._lines(caplog)
        summaries = [
            r.getMessage() for r in caplog.records if "discovery:" in r.getMessage()
        ]
        assert "unknown_leagues=0" in summaries[0], summaries[0]

    def test_the_count_still_reports_on_every_pass(self, caplog):
        """Silence must not read as "the problem went away".

        That worry is the whole reason a per-pass warning is tempting, and it is
        a real worry -- so the count carries it. If this number stopped being
        printed, deduplicating the line would be hiding the problem rather than
        quietening it.
        """
        events = self._events("KXKORFGAME", "Korea K League 1", 4)
        with caplog.at_level(logging.INFO, logger="backend.kalshi.discovery"):
            discover_from_events(events)
            discover_from_events(events)

        summaries = [
            r.getMessage() for r in caplog.records if "discovery:" in r.getMessage()
        ]
        assert len(summaries) == 2
        assert all("unknown_leagues=1" in m for m in summaries), summaries

    def test_the_count_is_the_current_pass_not_a_running_total(self, caplog):
        """The count is operational state, so it has to describe *now*.

        The naming is per process and the count is per pass, and the two are
        only safe together because the count can fall. A cumulative one would
        keep reporting a league Kalshi has stopped listing, and since the
        warning deliberately never repeats, that stale number would be the only
        thing left saying anything -- silence plus a wrong number is worse than
        either alone.

        This is the test that was missing when the guard was first broken to
        check it: removing the per-pass `clear()` left every other league test
        green, because none of them ran a pass that should have counted fewer.
        """
        unclassified = self._events("KXKORFGAME", "Korea K League 1", 3)
        classified = self._events("KXMLBGAME", "Pro Baseball", 3)
        with caplog.at_level(logging.INFO, logger="backend.kalshi.discovery"):
            discover_from_events(unclassified)
            discover_from_events(classified)

        summaries = [
            r.getMessage() for r in caplog.records if "discovery:" in r.getMessage()
        ]
        assert len(summaries) == 2, summaries
        assert "unknown_leagues=1" in summaries[0], summaries[0]
        assert "unknown_leagues=0" in summaries[1], summaries[1]

    def test_the_two_axes_are_reported_separately(self, caplog):
        """A reader must be able to tell which axis fired without parsing prose.

        The scope line says "unrecognised", this one says "unclassified", and the
        summary carries both counts. Merging the vocabularies would mean a grep
        for one silently matched the other.
        """
        events = [
            # Unclassified league, recognised scope.
            *self._events("KXKORFGAME", "Korea K League 1", 2),
            # Classified league, unrecognised scope.
            *self._events("KXMLBHIT", "Pro Baseball", 2, scope="Hits"),
        ]
        with caplog.at_level(logging.INFO, logger="backend.kalshi.discovery"):
            discover_from_events(events)

        leagues = self._lines(caplog)
        scopes = [
            r.getMessage() for r in caplog.records if "unrecognised" in r.getMessage()
        ]
        assert len(leagues) == 1, leagues
        assert len(scopes) == 1, scopes
        assert "'Korea K League 1'" in leagues[0]
        assert "'Korea K League 1'" not in scopes[0]
        assert "'Hits'" in scopes[0]
        assert "'Hits'" not in leagues[0]

        summary = [
            r.getMessage() for r in caplog.records if "discovery:" in r.getMessage()
        ][0]
        assert "unknown_scopes=1" in summary, summary
        assert "unknown_leagues=1" in summary, summary

    def test_an_unclassified_league_never_raises(self, caplog):
        """Discovery runs inside the supervised loop process.

        Nothing on this path may be fatal: a league Kalshi renames overnight has
        to announce and continue, because the thing that clears a crash-looping
        supervisor is a laptop and `flyctl`, and this tool is operated from a
        phone. An announcement is a guard; a crash is a laptop job.
        """
        hostile = [
            {"series_ticker": "KXXGAME", "product_metadata": {"competition": "Neŵ"}},
            {"series_ticker": "KXYGAME", "product_metadata": {"competition": "  "}},
            {"series_ticker": "", "product_metadata": {"competition": "No Series"}},
            {"series_ticker": "KXZGAME", "product_metadata": None},
            {"series_ticker": "KXWGAME"},
        ]
        with caplog.at_level(logging.WARNING, logger="backend.kalshi.discovery"):
            assert discover_from_events(hostile) == []
            # And the aggregated line still renders with an odd value in it.
            for line in self._lines(caplog):
                assert isinstance(line, str)


class TestPeriodMarketsAreExcludedByDecisionNotByOmission:
    """Quarter markets stay out, and the log stops saying so every boot.

    On 2026-08-09 the live instance warned, on every fresh process, about 12
    unrecognised `competition_scope` values -- all of them WNBA quarter markets
    in a league this project prices, which is precisely the shape the warning
    exists to surface. It was surfacing correctly and nobody had answered it.

    The answer is no, and it is a decision about the *reference price*, not
    about Kalshi: a 1st-quarter spread resolves on one fixture, but the
    consensus this project devigs against is game-level, so there is nothing to
    compare a quarter against. See docs/adr/0013.

    A warning that names an action item already decided is a warning readers
    learn to skip, and this one shares a log stream with two boot lines that
    three sessions could not read. So the decision is recorded in
    `PERIOD_SCOPES` and these markets stop being *unrecognised* -- while an
    unrecognised value must still be as loud as it ever was, which is what the
    last two tests here are for.
    """

    # Kalshi's exact spelling, from the live warning. Paired with the series
    # each was seen on, so a rename breaks the classification and the record of
    # what it was classified from at the same time.
    QUARTER_SCOPES = [
        ("1st Quarter Spread", "KXWNBA1QSPREAD"),
        ("1st Quarter Total", "KXWNBA1QTOTAL"),
        ("1st Quarter Winner", "KXWNBA1QWINNER"),
        ("2nd Quarter Spread", "KXWNBA2QSPREAD"),
        ("2nd Quarter Total", "KXWNBA2QTOTAL"),
        ("2nd Quarter Winner", "KXWNBA2QWINNER"),
        ("3rd Quarter Spread", "KXWNBA3QSPREAD"),
        ("3rd Quarter Total", "KXWNBA3QTOTAL"),
        ("3rd Quarter Winner", "KXWNBA3QWINNER"),
        ("4th Quarter Spread", "KXWNBA4QSPREAD"),
        ("4th Quarter Total", "KXWNBA4QTOTAL"),
        ("4th Quarter Winner", "KXWNBA4QWINNER"),
    ]

    def _event(self, series, scope, i=0):
        """One WNBA quarter event, in a league this project prices.

        The league matters: the warning only *names* scopes in a priceable
        league, so an out-of-scope one would assert against the counted-not-
        named branch and pass whatever the classification did.
        """
        return {
            "event_ticker": f"{series}-26AUG09LVNY-{i}",
            "series_ticker": series,
            "product_metadata": {
                "competition": "Pro Basketball (W)",
                "competition_scope": scope,
            },
            "markets": [
                {
                    "ticker": f"{series}-26AUG09LVNY-{i}-A",
                    "yes_sub_title": "Las Vegas",
                    "occurrence_datetime": "2026-08-09T23:00:00Z",
                }
            ],
        }

    def test_all_twelve_live_quarter_scopes_are_classified(self):
        unclassified = [
            scope
            for scope, _ in self.QUARTER_SCOPES
            if scope.lower() not in EXCLUDED_SCOPES
        ]
        assert not unclassified, unclassified

    def test_quarter_markets_are_not_game_level(self):
        """The exclusion itself, asserted on the classifier rather than the log.

        Note the ticker suffix says `SPREAD` and `TOTAL`, so `market_type`
        resolves and the suffix fallback would call these game-level. Only the
        scope keeps them out.
        """
        for scope, series in self.QUARTER_SCOPES:
            info = classify_series(self._event(series, scope))
            assert not info.is_game_level, f"{scope} classified as game-level"
            assert not info.in_scope, f"{scope} reached the priceable set"

    def test_quarter_scopes_are_not_priceable(self):
        """Classified as excluded, never as a fixture scope.

        `FIXTURE_SCOPES` is the priceable set. A quarter landing there would be
        devigged against a game-level consensus, which is not an error anything
        downstream can detect -- the numbers would simply be wrong.
        """
        for scope, _ in self.QUARTER_SCOPES:
            assert scope.lower() not in FIXTURE_SCOPES, scope

    def test_a_full_slate_of_quarter_markets_warns_about_nothing(self, caplog):
        """The line that reprinted every boot, now absent for a decided case."""
        events = [
            self._event(series, scope, i)
            for scope, series in self.QUARTER_SCOPES
            for i in range(3)
        ]
        with caplog.at_level(logging.INFO, logger="backend.kalshi.discovery"):
            discover_from_events(events)

        warnings = [r for r in caplog.records if "unrecognised" in r.getMessage()]
        assert not warnings, [r.getMessage() for r in warnings]
        summaries = [
            r.getMessage() for r in caplog.records if "discovery:" in r.getMessage()
        ]
        # The count has to agree with the silence, or the two halves of the
        # reporting contradict each other and neither can be trusted.
        assert len(summaries) == 1
        assert "unknown_scopes=0" in summaries[0], summaries[0]
        assert "not_game_level=36" in summaries[0], summaries[0]

    def test_a_scope_nobody_has_classified_still_warns(self, caplog):
        """The safety property, and the reason this change is allowed at all.

        Classifying the twelve must narrow the warning to "nobody has looked at
        this", never silence it. If this test goes green with the warning
        removed, the whole mechanism from `tasks/lessons.md` -- an exclusion is
        a decision, never an accident -- is gone.
        """
        events = [
            *(self._event("KXWNBA1QSPREAD", "1st Quarter Spread", i) for i in range(3)),
            *(self._event("KXWNBAREB", "Rebounds", i) for i in range(3)),
        ]
        with caplog.at_level(logging.WARNING, logger="backend.kalshi.discovery"):
            discover_from_events(events)

        messages = [
            r.getMessage() for r in caplog.records if "unrecognised" in r.getMessage()
        ]
        assert len(messages) == 1, messages
        assert "'Rebounds'" in messages[0]
        assert "KXWNBAREB" in messages[0]
        assert "1st Quarter Spread" not in messages[0], messages[0]

    def test_a_period_scope_kalshi_has_not_emitted_yet_still_warns(self, caplog):
        """Classified by exact value, not by pattern-matching "quarter".

        A substring rule would be the tempting shortcut and would swallow every
        period product Kalshi ever ships -- halves, innings, overtime, a 5th
        quarter -- turning one answered question into a standing blanket
        exemption. These four are the ones a `"quarter" in scope` test would
        wrongly accept or that sit closest to the ones accepted.
        """
        novel = ["1st Half Winner", "5th Quarter Winner", "Overtime Winner",
                 "1st Quarter Margin"]
        events = [
            self._event(f"KXWNBANEW{i}", scope, j)
            for i, scope in enumerate(novel)
            for j in range(2)
        ]
        with caplog.at_level(logging.WARNING, logger="backend.kalshi.discovery"):
            discover_from_events(events)

        messages = [
            r.getMessage() for r in caplog.records if "unrecognised" in r.getMessage()
        ]
        assert len(messages) == 1, messages
        for scope in novel:
            assert f"'{scope}'" in messages[0], f"{scope} was silently swallowed"

    def test_the_two_reasons_for_exclusion_are_kept_apart(self):
        """A future is not a fixture; a quarter is one and is still declined.

        Merging them would lose the only thing that tells a future reader which
        exclusions a period-level odds feed would reopen and which no data
        source can.
        """
        assert PERIOD_SCOPES
        assert not (PERIOD_SCOPES & NON_FIXTURE_SCOPES)
        assert EXCLUDED_SCOPES == PERIOD_SCOPES | NON_FIXTURE_SCOPES


class TestCommenceTime:
    """The join key against the sportsbook feed."""

    def test_commence_comes_from_occurrence_datetime_not_close_time(self, events):
        """`close_time` can be days after the game -- Kalshi allows for
        postponements. Matching on it would mis-join every fixture."""
        event = next(e for e in events if e.get("series_ticker") == "KXMLBGAME")
        commence = event_commence_ms(event)
        close = parse_ms(event["markets"][0]["close_time"])
        assert commence is not None
        assert commence < close, "commence should precede close"
        assert close - commence > 24 * 3600 * 1000, (
            "expected close_time to be well after the game, proving they differ"
        )

    def test_missing_occurrence_time_returns_none_not_a_default(self):
        """A wrong start time silently joins the wrong fixture."""
        assert event_commence_ms({"markets": [{"close_time": "2026-08-13T00:20:00Z"}]}) is None

    def test_unparseable_timestamps_return_none(self):
        for bad in (None, "", "not-a-date", "2026-13-45"):
            assert parse_ms(bad) is None


class TestDiscovery:
    def test_finds_priceable_events(self, discovered):
        assert discovered, "no priceable events found in the fixture"

    def test_every_discovered_event_has_what_matching_needs(self, discovered):
        for event in discovered:
            assert event.commence_ms > 0
            assert event.sport_key in IN_SCOPE_LEAGUES.values()
            assert event.markets
            assert event.title

    def test_moneyline_events_name_exactly_two_sides(self, discovered):
        """Built from `yes_sub_title`, because `no_sub_title` repeats the YES
        side rather than naming the opponent."""
        moneylines = [e for e in discovered if e.market_type == "moneyline"]
        assert moneylines
        for event in moneylines:
            assert len(event.teams) == 2, f"{event.event_ticker}: {event.teams}"

    def test_out_of_scope_leagues_are_excluded(self, discovered):
        """Soccer and esports have game markets but no configured sport key."""
        assert all(e.sport_key for e in discovered)
        assert not any(e.series_ticker == "KXMLSGAME" for e in discovered)

    def test_futures_are_excluded(self, discovered):
        assert not any(e.series_ticker in {"KXNBA", "KXNFLMVP"} for e in discovered)

    def test_spread_and_total_markets_carry_their_line(self, discovered):
        priced = [e for e in discovered if e.market_type in ("spread", "total")]
        if not priced:
            pytest.skip("fixture has no spread/total events in scope")
        for event in priced:
            assert all(m.strike is not None for m in event.markets), (
                "a spread or total without a line cannot be matched to a book"
            )


class TestCoverage:
    def test_reports_per_league_totals(self, discovered):
        coverage = coverage_by_league(discovered)
        assert coverage
        for league, entry in coverage.items():
            assert entry["events"] > 0
            assert entry["markets"] >= entry["events"]
            assert entry["sport_key"]

    def test_mlb_is_present_with_moneyline_coverage(self, discovered):
        coverage = coverage_by_league(discovered)
        assert "Pro Baseball" in coverage
        assert "moneyline" in coverage["Pro Baseball"]["market_types"]


class TestUnknownScopeWarningsAreDeduplicated:
    """Deduplicated within a pass, and then across passes — in two steps.

    Kalshi carries the same `competition_scope` on every market in a series, so
    the original form emitted the identical line twelve times for a single
    series. That was fixed by deduplicating on `(series, scope)`, and the set was
    cleared at the top of every pass so a long-running runner could not warn once
    at boot and then go quiet.

    Both halves were individually defended in prose, and together they rebuilt
    the thing the dedupe existed to prevent. Measured on live 2026-08-08: **98 of
    the 100 lines in the log buffer** were this warning, and a quote pass
    re-emits the set every 15s while the window is open. It buried
    `[migrate] ...` and `API starting: ...` so completely that neither boot line
    could be read from production at all, which is what sent that session
    looking.

    The split that resolves it, and the reason the two concerns are tested
    separately below: the warning names a **developer action item** ("add it to
    FIXTURE_SCOPES"), which cannot change within a process and is worth saying
    once; the **count** is an operational state and is printed on every pass,
    including at zero. Silence never means "the problem went away" — a number
    says so. See `tasks/lessons.md` on rejection logs dominated by their majority
    case.

    **Corrected 2026-08-09, and the correction is why the class now has a burst
    test.** The docstring above used to add "94 distinct series, none of them
    sports (`KXFED`, `KXWMT`, AP polls, draft picks)". That population was read
    off `flyctl logs`. Measured against the live exchange instead
    (`scripts/measure_unknown_scopes.py`) it is **962 (series, scope) pairs over
    317 scopes**, and **227 of them are in leagues this project prices** — all
    futures, awards and period/prop markets, so nothing priceable is being
    dropped, but the reassuring sentence was drawn from a ~10% sample selected by
    which lines Fly's pipeline did not drop.

    So "one warning per pair, once per process" was still 962 lines inside 90ms:
    nine times the log buffer, and enough to lose neighbouring unrelated lines as
    collateral. One aggregated line per process now. The tests below therefore
    assert a **line count that does not grow with the population**, which is the
    property that was missing — every previous test used one or two series, the
    one regime in which the old code looked fine.
    """

    def _events(self, ticker, scope, n, league="Pro Baseball"):
        """`n` separate EVENTS in one series.

        Deliberately events and not markets: `classify_series` runs once per
        event, so a fixture with one event and twelve markets warns once no
        matter what the code does — my first version of this test did exactly
        that and passed with the deduplication removed. The live repeats were
        twelve fixtures sharing a series, which is the shape that actually
        produces the spam.

        `league` defaults to an in-scope one so the scope gets *named*. The
        warning only names scopes in leagues this project can devig against; a
        test that used "House" would assert against the counted-not-named branch
        without meaning to.
        """
        return [
            {
                "event_ticker": f"{ticker}-26AUG07-{i}",
                "series_ticker": ticker,
                "product_metadata": {
                    "competition": league,
                    "competition_scope": scope,
                },
                "markets": [
                    {"ticker": f"{ticker}-26AUG07-{i}-A", "yes_sub_title": "A"}
                ],
            }
            for i in range(n)
        ]

    def test_one_series_warns_once_not_once_per_event(self, caplog):
        events = self._events("KXMLBHIT", "Hits", 12)
        with caplog.at_level(logging.WARNING, logger="backend.kalshi.discovery"):
            discover_from_events(events)

        warnings = [r for r in caplog.records if "unrecognised" in r.getMessage()]
        assert len(warnings) == 1, f"{len(warnings)} warnings for one series"
        assert "KXMLBHIT" in warnings[0].getMessage()

    def test_distinct_scopes_are_all_named_in_one_line(self, caplog):
        """Deduplication must not swallow a genuinely new scope.

        It used to be one line per scope. Now it is one line naming every scope,
        which is the same guarantee against silence with a bounded line count —
        so this asserts on the *content*, and the test below asserts the count
        does not grow.
        """
        events = [
            *self._events("KXMLBHIT", "Hits", 5),
            *self._events("KXMLBHR", "Home Runs", 5),
        ]
        with caplog.at_level(logging.WARNING, logger="backend.kalshi.discovery"):
            discover_from_events(events)

        messages = [
            r.getMessage() for r in caplog.records if "unrecognised" in r.getMessage()
        ]
        assert len(messages) == 1, messages
        assert "KXMLBHIT" in messages[0]
        assert "KXMLBHR" in messages[0]
        assert "'Hits'" in messages[0]
        assert "'Home Runs'" in messages[0]

    def test_the_line_count_does_not_grow_with_the_population(self, caplog):
        """The property the old tests could not see, because they used n=2.

        Live carries 962 unknown (series, scope) pairs. Per-pair warning emitted
        962 lines into a 100-line buffer in ~90ms; ~90% were dropped by Fly and
        they took the neighbouring `discovery:` summary with them. One line is
        the fix, and "one" has to hold at 300 as firmly as it holds at 2 —
        asserting a small number here would pass against the code that caused
        the outage.
        """
        events = []
        for i in range(300):
            events.extend(self._events(f"KXPROP{i}", f"Scope {i}", 2))

        with caplog.at_level(logging.WARNING, logger="backend.kalshi.discovery"):
            discover_from_events(events)

        warnings = [r for r in caplog.records if "unrecognised" in r.getMessage()]
        assert len(warnings) == 1, (
            f"{len(warnings)} lines for 300 unknown scopes; the burst is back"
        )
        assert "300 unrecognised" in warnings[0].getMessage()

    def test_out_of_scope_leagues_are_counted_and_not_named(self, caplog):
        """A scope in a league we cannot devig is not an action item.

        `FIXTURE_SCOPES` only decides whether a *priceable* market gets priced.
        On live, 261 of the 317 unknown scopes are elections, esports and
        entertainment; naming them is what made the line unreadable and would
        make it unreadable again at one line instead of 962.
        """
        events = [
            *self._events("KXMLBHIT", "Hits", 2, league="Pro Baseball"),
            *self._events("KXHOUSE", "Election", 2, league="House"),
        ]
        with caplog.at_level(logging.WARNING, logger="backend.kalshi.discovery"):
            discover_from_events(events)

        message = [
            r.getMessage() for r in caplog.records if "unrecognised" in r.getMessage()
        ][0]
        assert "'Hits'" in message
        assert "KXMLBHIT" in message
        assert "Election" not in message, "an out-of-scope scope was named"
        assert "KXHOUSE" not in message
        assert "1 further scopes" in message, message

    def test_a_scope_first_seen_on_a_later_pass_is_still_named(self, caplog):
        """Aggregation must not become "warn at boot and then go quiet".

        That is the failure the per-pass clear was originally added for. The
        guarantee is per *pair*, not per process-start: a pair nobody has named
        gets named on whichever pass first sees it.
        """
        first = self._events("KXMLBHIT", "Hits", 3)
        later = [*first, *self._events("KXMLBSB", "Stolen Bases", 3)]

        with caplog.at_level(logging.WARNING, logger="backend.kalshi.discovery"):
            discover_from_events(first)
            discover_from_events(later)

        messages = [
            r.getMessage() for r in caplog.records if "unrecognised" in r.getMessage()
        ]
        assert len(messages) == 2, messages
        assert "KXMLBHIT" in messages[0] and "KXMLBSB" not in messages[0]
        # The second line carries only what is new. Re-naming the first pair
        # would rebuild the per-pass repeat one aggregation level up.
        assert "KXMLBSB" in messages[1]
        assert "KXMLBHIT" not in messages[1], messages[1]

    def test_a_repeated_scope_is_named_once_for_the_life_of_the_process(
        self, caplog
    ):
        """The second pass must not re-emit the same warning.

        This asserts the opposite of what it used to. Re-warning every pass was
        measured on live as 98 of the 100 lines in the log buffer — a quote pass
        runs every 15s while the window is open — and it buried the two boot
        lines (`[migrate] ...` and `API starting: ...`) so thoroughly that
        neither could be read from production at all.
        """
        events = self._events("KXMLBHIT", "Hits", 5)
        with caplog.at_level(logging.WARNING, logger="backend.kalshi.discovery"):
            discover_from_events(events)
            first = len([r for r in caplog.records if "unrecognised" in r.getMessage()])
            discover_from_events(events)
            discover_from_events(events)
            after = len([r for r in caplog.records if "unrecognised" in r.getMessage()])

        assert first == 1
        assert after == 1, f"{after - first} warnings repeated across later passes"

    def test_the_count_still_reports_on_every_pass(self, caplog):
        """Silence must not read as "the problem went away".

        That worry is the whole reason the old code re-warned every pass, and it
        was a real worry — so the count has to carry it. If this number stopped
        being printed, dropping the repeat warnings would genuinely have hidden
        the problem rather than merely quietened it.
        """
        events = self._events("KXMLBHIT", "Hits", 5)
        with caplog.at_level(logging.INFO, logger="backend.kalshi.discovery"):
            discover_from_events(events)
            discover_from_events(events)

        summaries = [
            r.getMessage() for r in caplog.records if "discovery:" in r.getMessage()
        ]
        assert len(summaries) == 2
        assert all("unknown_scopes=1" in m for m in summaries), summaries

    def test_a_pass_with_no_unknown_scopes_says_zero_rather_than_nothing(
        self, caplog
    ):
        """The pair that matters: 0 must be printed, not filtered out.

        A dropped zero puts the reader back where the warning stream left them —
        unable to tell "none found" from "not reported". This test and the one
        above have to disagree about the number and agree that it is present.
        """
        events = self._events("KXMLBGAME", "Game", 3)
        with caplog.at_level(logging.INFO, logger="backend.kalshi.discovery"):
            discover_from_events(events)

        summaries = [
            r.getMessage() for r in caplog.records if "discovery:" in r.getMessage()
        ]
        assert len(summaries) == 1
        assert "unknown_scopes=0" in summaries[0], summaries[0]

    def test_the_summary_survives_the_burst_that_precedes_it(self, caplog):
        """The line that got lost as collateral, asserted where it can be seen.

        On live 2026-08-09 the `discovery:` summary was emitted immediately after
        962 warning lines and never arrived — Fly dropped it along with ~90% of
        the burst. Nothing in the process was wrong, which is exactly why no test
        could have caught it: the defect was the *volume* of the neighbouring
        lines, and every fixture used two.

        A log pipeline cannot be asserted on from pytest. What can is the thing
        that made it survivable: the number of records emitted before the summary
        does not scale with the size of the population.
        """
        events = []
        for i in range(300):
            events.extend(self._events(f"KXPROP{i}", f"Scope {i}", 2))

        with caplog.at_level(logging.DEBUG, logger="backend.kalshi.discovery"):
            discover_from_events(events)

        emitted = [r for r in caplog.records if r.name == "backend.kalshi.discovery"]
        summaries = [r for r in emitted if "discovery:" in r.getMessage()]
        assert len(summaries) == 1
        assert "unknown_scopes=300" in summaries[0].getMessage()
        # One warning plus one summary. The old code emitted 301 here.
        assert len(emitted) <= 5, (
            f"{len(emitted)} records for one pass over 300 unknown scopes"
        )


class TestTheNoCommenceWarningIsAlsoDeduplicated:
    """The same hazard, one branch away, that had never fired.

    `no occurrence_datetime` warns per *event* and was never deduplicated. It has
    emitted nothing on live, so it looks harmless — but it is one Kalshi
    data-entry day away from being the 962-line burst that made the log stream
    unreadable, and it sits four lines from the code that was fixed for exactly
    that. `tasks/lessons.md`: a comment explaining one instance of a hazard is
    evidence the hazard is understood, not evidence it has been handled
    everywhere.
    """

    def _events(self, ticker, n):
        """Game-level, in-scope league, and no `occurrence_datetime`."""
        return [
            {
                "event_ticker": f"{ticker}-26AUG07-{i}",
                "series_ticker": ticker,
                "product_metadata": {
                    "competition": "Pro Baseball",
                    "competition_scope": "Game",
                },
                "markets": [
                    {"ticker": f"{ticker}-26AUG07-{i}-A", "yes_sub_title": "A"}
                ],
            }
            for i in range(n)
        ]

    def test_one_series_warns_once_not_once_per_event(self, caplog):
        with caplog.at_level(logging.WARNING, logger="backend.kalshi.discovery"):
            discover_from_events(self._events("KXMLBGAME", 40))

        warnings = [
            r for r in caplog.records if "occurrence_datetime" in r.getMessage()
        ]
        assert len(warnings) == 1, f"{len(warnings)} lines for 40 events"
        assert "KXMLBGAME" in warnings[0].getMessage()

    def test_a_second_series_is_still_named(self, caplog):
        """Dedupe must not swallow a series nobody has reported."""
        with caplog.at_level(logging.WARNING, logger="backend.kalshi.discovery"):
            discover_from_events(
                [*self._events("KXMLBGAME", 3), *self._events("KXNFLGAME", 3)]
            )

        messages = [
            r.getMessage()
            for r in caplog.records
            if "occurrence_datetime" in r.getMessage()
        ]
        assert len(messages) == 2
        assert any("KXMLBGAME" in m for m in messages)
        assert any("KXNFLGAME" in m for m in messages)

    def test_a_later_pass_does_not_re_warn(self, caplog):
        events = self._events("KXMLBGAME", 3)
        with caplog.at_level(logging.WARNING, logger="backend.kalshi.discovery"):
            discover_from_events(events)
            discover_from_events(events)
            discover_from_events(events)

        warnings = [
            r for r in caplog.records if "occurrence_datetime" in r.getMessage()
        ]
        assert len(warnings) == 1, f"{len(warnings)} across three passes"

    def test_the_count_still_reports_on_every_pass(self, caplog):
        """Deduplicating the line must not make the condition invisible.

        `no_commence_time` on the `discovery:` line is what carries it, and it is
        the reason silencing the repeats is safe. If this stopped being printed,
        the dedupe above would be hiding the problem rather than quietening it.
        """
        events = self._events("KXMLBGAME", 3)
        with caplog.at_level(logging.INFO, logger="backend.kalshi.discovery"):
            discover_from_events(events)
            discover_from_events(events)

        summaries = [
            r.getMessage() for r in caplog.records if "discovery:" in r.getMessage()
        ]
        assert len(summaries) == 2
        assert all("no_commence_time=3" in m for m in summaries), summaries


class TestTheSummaryIsQuietOnTheQuoteCadence:
    """The same line was right at 900s and a flood at 22s.

    `discovery:` printed unconditionally so that silence could not be mistaken
    for "discovery did not run". Correct, and sized for a pass every 900s — 96
    lines a day. Then the odds budget went 16 -> 400, the window stopped
    closing, and quote passes began running every ~22s: the identical line,
    bit-identical, ~3,900 times a day, in a 100-line log buffer.

    That is the 962-line scope burst reached from the other direction. Not a
    loop that forgot to deduplicate — a correct per-pass line meeting a cadence
    forty times faster than the one it was written for.

    Two halves, and the tests below exist because neither works alone:
    change-detection would restore the very ambiguity the unconditional print
    prevents, and the full-pass heartbeat is what rules it out.
    """

    def _events(self, n, scope="Game", league="Pro Baseball"):
        return [
            {
                "event_ticker": f"KXMLBGAME-26AUG07-{i}",
                "series_ticker": "KXMLBGAME",
                "product_metadata": {
                    "competition": league, "competition_scope": scope,
                },
                # `occurrence_datetime` lives on the *market*, not the event --
                # `event_commence_ms` walks `event["markets"]`. Putting it on
                # the event made every fixture here unpriceable, so the first
                # version of these tests asserted a changing `no_commence_time`
                # count and would have passed against a discovery leg that
                # found nothing at all.
                "markets": [{
                    "ticker": f"KXMLBGAME-26AUG07-{i}-A",
                    "yes_sub_title": "A",
                    "occurrence_datetime": "2026-08-07T18:00:00Z",
                }],
            }
            for i in range(n)
        ]

    def _summaries(self, caplog):
        return [
            r.getMessage() for r in caplog.records if "discovery:" in r.getMessage()
        ]

    def test_an_unchanged_quote_pass_says_nothing(self, caplog):
        events = self._events(3)
        with caplog.at_level(logging.INFO, logger="backend.kalshi.discovery"):
            discover_from_events(events, always_log_summary=False)
            for _ in range(60):
                discover_from_events(events, always_log_summary=False)

        # One line for the first pass — there was nothing to compare against —
        # and silence for the sixty identical ones behind it.
        assert len(self._summaries(caplog)) == 1, (
            f"{len(self._summaries(caplog))} lines for 61 identical quote passes"
        )

    def test_a_changed_quote_pass_speaks_immediately(self, caplog):
        """Quiet must not mean deaf. A change is the thing worth reading."""
        with caplog.at_level(logging.INFO, logger="backend.kalshi.discovery"):
            discover_from_events(self._events(3), always_log_summary=False)
            discover_from_events(self._events(3), always_log_summary=False)
            discover_from_events(self._events(5), always_log_summary=False)

        summaries = self._summaries(caplog)
        assert len(summaries) == 2, summaries
        assert "3 priceable events" in summaries[0]
        assert "5 priceable events" in summaries[1]

    def test_the_full_pass_prints_even_when_nothing_changed(self, caplog):
        """The heartbeat, and the reason change-detection is safe.

        Without this, a quiet stretch is indistinguishable from a dead
        discovery leg — which is exactly the failure the unconditional print was
        added for. A full pass runs every 900s, so the gap is bounded.
        """
        events = self._events(3)
        with caplog.at_level(logging.INFO, logger="backend.kalshi.discovery"):
            discover_from_events(events, always_log_summary=False)
            for _ in range(5):
                discover_from_events(events, always_log_summary=False)
            discover_from_events(events)          # full pass
            discover_from_events(events)          # full pass

        assert len(self._summaries(caplog)) == 3, (
            "the full pass stopped being a heartbeat"
        )

    def test_a_change_seen_only_by_a_full_pass_still_quietens_the_next_quote(
        self, caplog
    ):
        """The two paths share one memory, and must.

        If the full pass did not record what it printed, the next quote pass
        would compare against a stale summary and re-announce a change already
        on screen.
        """
        with caplog.at_level(logging.INFO, logger="backend.kalshi.discovery"):
            discover_from_events(self._events(3))                        # full
            discover_from_events(self._events(9))                        # full
            discover_from_events(self._events(9), always_log_summary=False)

        summaries = self._summaries(caplog)
        assert len(summaries) == 2, summaries
        assert "9 priceable events" in summaries[1]

    def test_the_default_stays_loud_for_one_shot_callers(self, caplog):
        """`run_chain.py` and the tests run one pass; quiet would be silent."""
        events = self._events(3)
        with caplog.at_level(logging.INFO, logger="backend.kalshi.discovery"):
            discover_from_events(events)
            discover_from_events(events)

        assert len(self._summaries(caplog)) == 2
