"""Discovery tests, against the real captured payload.

The classifier decides which leagues are priceable at all, so a bug here does
not surface as an error — it surfaces as a league quietly missing from the
Board. These tests run against `events_sports_nested.json` rather than
invented events, so a Kalshi metadata change breaks them instead of silently
emptying the universe.
"""

from __future__ import annotations

import logging

import pytest

from conftest import load_fixture
from backend.kalshi.discovery import (
    FIXTURE_SCOPES,
    IN_SCOPE_LEAGUES,
    NON_FIXTURE_SCOPES,
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
        known = FIXTURE_SCOPES | NON_FIXTURE_SCOPES | {""}
        unknown = scopes - known
        assert not unknown, (
            f"unclassified competition_scope value(s): {sorted(unknown)}. "
            f"Add each to FIXTURE_SCOPES (per-fixture, priceable) or "
            f"NON_FIXTURE_SCOPES (futures/awards). Leaving one unclassified "
            f"silently drops those markets."
        )

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
