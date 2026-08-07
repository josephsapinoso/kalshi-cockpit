"""Matching tests.

The failure this module guards against does not raise. A wrong join silently
produces an *edge*, because two prices for different questions are being
compared. The previous project's text matcher hit 0.56% and its hits were
wrong.

So the tests that matter most here are the ones asserting that ambiguous or
unresolvable input **refuses**. Coverage is a secondary concern; a matcher that
matches nothing is merely useless, while one that matches wrongly loses money
and corrupts the measurement record at the same time.

Kalshi team names in these tests are the real strings from the captured
payload ("Houston", "New York G"), not invented ones.
"""

from __future__ import annotations

import pytest

from backend.match.linker import (
    DEFAULT_COMMENCE_TOLERANCE_MS,
    OBSERVED_KALSHI_COMMENCE_OFFSET_MS,
    MatchCandidate,
    TeamAliases,
    link_event,
    load_aliases,
    normalise,
    record_link,
    record_unmatched,
)
from backend.store import db

NOW = 1_754_800_000_000  # arbitrary fixed epoch ms
HOUR = 3_600_000


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "match.db")
    yield c
    c.close()


@pytest.fixture
def nfl():
    return load_aliases("americanfootball_nfl")


@pytest.fixture
def no_aliases():
    return TeamAliases(sport_key="test")


def candidate(home, away, *, offset_ms=0, event_id="odds_1"):
    return MatchCandidate(
        odds_event_id=event_id,
        commence_ms=NOW + offset_ms,
        home_team=home,
        away_team=away,
    )


class TestNormalisation:
    @pytest.mark.parametrize(
        "a,b",
        [
            ("St. Louis", "St Louis"),
            ("Montréal", "Montreal"),
            ("  Houston  ", "houston"),
            ("Inter Miami CF", "Inter Miami"),
        ],
    )
    def test_equivalent_spellings_normalise_together(self, a, b):
        assert normalise(a) == normalise(b)

    def test_distinct_teams_do_not_collide(self):
        assert normalise("New York Giants") != normalise("New York Jets")


class TestTeamResolution:
    """Names resolve within one fixture's two teams, not a global roster."""

    def test_city_name_resolves_to_the_full_team_name(self, no_aliases):
        result = link_event(
            kalshi_event_ticker="KXMLBGAME-26AUG09HOUSD",
            kalshi_teams=["Houston", "San Diego"],
            kalshi_commence_ms=NOW,
            candidates=[candidate("San Diego Padres", "Houston Astros")],
            aliases=no_aliases,
        )
        assert result.matched

    def test_truncated_name_resolves_to_the_right_team(self, nfl):
        """The real string from the capture. "New York G" must become Giants
        and must not become Jets."""
        result = link_event(
            kalshi_event_ticker="KXNFLGAME-26SEP13DALNYG",
            kalshi_teams=["New York G", "Dallas"],
            kalshi_commence_ms=NOW,
            candidates=[candidate("New York Giants", "Dallas Cowboys")],
            aliases=nfl,
        )
        assert result.matched

    def test_truncated_name_does_not_match_the_other_city_team(self, nfl):
        """The dangerous case: Giants and Jets share a city and a stadium."""
        result = link_event(
            kalshi_event_ticker="KXNFLGAME-26SEP13DALNYG",
            kalshi_teams=["New York G", "Dallas"],
            kalshi_commence_ms=NOW,
            candidates=[candidate("New York Jets", "Dallas Cowboys")],
            aliases=nfl,
        )
        assert not result.matched

    def test_an_explicit_alias_resolves_a_name_the_prefix_rule_cannot(self):
        aliases = TeamAliases(
            sport_key="test", mapping={normalise("Cardinals"): normalise("St. Louis Cardinals")}
        )
        result = link_event(
            kalshi_event_ticker="E",
            kalshi_teams=["Cardinals", "Chicago"],
            kalshi_commence_ms=NOW,
            candidates=[candidate("St. Louis Cardinals", "Chicago Cubs")],
            aliases=aliases,
        )
        assert result.matched


class TestRefusal:
    """Ambiguity refuses. This is the whole point of the module."""

    def test_both_sides_matching_one_team_refuses(self, no_aliases):
        """Names too coarse to tell the teams apart is exactly when a wrong
        join looks like a right one."""
        result = link_event(
            kalshi_event_ticker="E",
            kalshi_teams=["New York", "New York"],
            kalshi_commence_ms=NOW,
            candidates=[candidate("New York Giants", "New York Jets")],
            aliases=no_aliases,
        )
        assert not result.matched

    def test_two_fixtures_with_the_same_teams_refuse(self, no_aliases):
        """A doubleheader. Guessing prices one game off the other's line."""
        result = link_event(
            kalshi_event_ticker="E",
            kalshi_teams=["Houston", "San Diego"],
            kalshi_commence_ms=NOW,
            candidates=[
                candidate("San Diego Padres", "Houston Astros", event_id="g1"),
                candidate("San Diego Padres", "Houston Astros",
                          offset_ms=HOUR, event_id="g2"),
            ],
            aliases=no_aliases,
        )
        assert not result.matched
        assert "ambiguous" in result.reason

    def test_no_fixture_in_the_time_window_refuses(self, no_aliases):
        result = link_event(
            kalshi_event_ticker="E",
            kalshi_teams=["Houston", "San Diego"],
            kalshi_commence_ms=NOW,
            candidates=[candidate("San Diego Padres", "Houston Astros",
                                  offset_ms=48 * HOUR)],
            aliases=no_aliases,
        )
        assert not result.matched
        assert "window" in result.reason

    def test_unrelated_teams_refuse(self, no_aliases):
        """The 0.56% failure: same fixture window, different question."""
        result = link_event(
            kalshi_event_ticker="E",
            kalshi_teams=["Houston", "San Diego"],
            kalshi_commence_ms=NOW,
            candidates=[candidate("Boston Red Sox", "New York Yankees")],
            aliases=no_aliases,
        )
        assert not result.matched
        assert "bijection" in result.reason

    def test_a_three_way_market_refuses(self, no_aliases):
        """Soccer draws. A three-outcome market is not a two-team moneyline."""
        result = link_event(
            kalshi_event_ticker="E",
            kalshi_teams=["Portland", "Tijuana", "Draw"],
            kalshi_commence_ms=NOW,
            candidates=[candidate("Club Tijuana", "Portland Timbers")],
            aliases=no_aliases,
        )
        assert not result.matched

    def test_refusal_reasons_are_actionable(self, no_aliases):
        """The reason lands in a work queue a human reads. It must say what
        was compared, not just that it failed."""
        result = link_event(
            kalshi_event_ticker="E",
            kalshi_teams=["Houston", "San Diego"],
            kalshi_commence_ms=NOW,
            candidates=[candidate("Boston Red Sox", "New York Yankees")],
            aliases=no_aliases,
        )
        assert "Houston" in result.reason
        assert "Boston Red Sox" in result.reason


class TestCommenceWindow:
    def test_small_skew_is_tolerated(self, no_aliases):
        """The two sources disagree by minutes on scheduled starts."""
        result = link_event(
            kalshi_event_ticker="E",
            kalshi_teams=["Houston", "San Diego"],
            kalshi_commence_ms=NOW,
            candidates=[candidate("San Diego Padres", "Houston Astros",
                                  offset_ms=10 * 60_000)],
            aliases=no_aliases,
        )
        assert result.matched
        assert result.commence_skew_ms == 10 * 60_000

    def test_a_doubleheader_is_never_matched_to_the_wrong_game(self, no_aliases):
        """MLB plays two games between the same teams a few hours apart.

        This replaces `test_the_default_window_is_tight_enough_for_doubleheaders`,
        which asserted `DEFAULT_COMMENCE_TOLERANCE_MS <= 3h`. That was a *proxy*
        for safety, and the proxy turned out to be both wrong and harmful:
        Kalshi's `occurrence_datetime` runs exactly 3 hours late (measured
        2026-08-07 across MLB and WNBA), so a 2-hour window rejected every
        correct link, and a live slate produced zero recommendations.

        Worse, a tight window is not even the thing that keeps doubleheaders
        safe. With a +3h shift, game one's Kalshi time lands right on game two's
        true start — so a narrow window is exactly what would confidently pick
        the wrong game. What actually protects this is the ambiguity refusal,
        which is what the test now asserts directly.

        The rule this follows: when a test guards a property via a proxy, assert
        the property.
        """
        result = link_event(
            kalshi_event_ticker="E",
            kalshi_teams=["Houston", "San Diego"],
            kalshi_commence_ms=NOW,
            candidates=[
                candidate("San Diego Padres", "Houston Astros", offset_ms=0),
                candidate("San Diego Padres", "Houston Astros",
                          offset_ms=3 * HOUR),
            ],
            aliases=no_aliases,
        )
        assert not result.matched, "picked one game of a doubleheader"
        assert "ambiguous" in result.reason

    def test_the_window_is_wide_enough_for_the_observed_kalshi_offset(self):
        """A link that cannot survive the measured offset links nothing at all."""
        assert DEFAULT_COMMENCE_TOLERANCE_MS > OBSERVED_KALSHI_COMMENCE_OFFSET_MS

    def test_skew_is_kept_as_evidence(self, conn, no_aliases):
        """A large skew is a different fixture sharing teams -- only visible
        after the fact if the number was kept."""
        result = link_event(
            kalshi_event_ticker="E",
            kalshi_teams=["Houston", "San Diego"],
            kalshi_commence_ms=NOW,
            candidates=[candidate("San Diego Padres", "Houston Astros",
                                  offset_ms=90 * 60_000)],
            aliases=no_aliases,
        )
        conn.execute(
            "INSERT INTO kalshi_events (event_ticker, first_seen_ms, last_seen_ms) "
            "VALUES ('E', 0, 0)"
        )
        record_link(conn, result, league="Pro Baseball", linked_ms=NOW)
        row = conn.execute("SELECT commence_skew_ms FROM event_links").fetchone()
        assert row["commence_skew_ms"] == 90 * 60_000


class TestWorkQueue:
    """Unmatched must be visible. Silent drops look identical to nothing to do."""

    def test_unmatched_events_are_recorded(self, conn):
        record_unmatched(
            conn, observed_ms=NOW, side="kalshi", identifier="KXNFLGAME-X",
            league="Pro Football", detail="New York G vs Dallas",
            reason="no_counterpart",
        )
        row = conn.execute("SELECT * FROM unmatched_events").fetchone()
        assert row["identifier"] == "KXNFLGAME-X"
        assert row["resolved"] == 0
        assert "New York G" in row["detail"], "detail must carry the names to alias"

    def test_recording_a_link_from_an_unmatched_result_is_refused(self, conn, no_aliases):
        result = link_event(
            kalshi_event_ticker="E", kalshi_teams=["A", "B"],
            kalshi_commence_ms=NOW, candidates=[], aliases=no_aliases,
        )
        with pytest.raises(ValueError):
            record_link(conn, result, league="X", linked_ms=NOW)


class TestAliasFiles:
    def test_shipped_alias_files_load(self):
        for sport_key in ("americanfootball_nfl", "baseball_mlb"):
            aliases = load_aliases(sport_key)
            assert aliases.mapping, f"{sport_key} alias file loaded empty"

    def test_a_missing_alias_file_is_not_an_error(self):
        """Most leagues need no overrides at all."""
        assert load_aliases("nonexistent_league").mapping == {}

    def test_alias_files_stay_short(self):
        """A long alias file means the deterministic rule has stopped working
        and is being papered over one team at a time."""
        for sport_key in ("americanfootball_nfl", "baseball_mlb"):
            assert len(load_aliases(sport_key).mapping) < 15


class TestKalshiOccurrenceDatetimeRunsLate:
    """Kalshi's stated start time is 3 hours after the sportsbook's.

    Measured on a live slate (2026-08-07): 14 of 18 same-day MLB pairs and 6 of
    6 WNBA pairs at exactly +180 minutes. The two-sport agreement is what
    identifies it as a fixed shift rather than a duration -- WNBA games run
    about two hours and MLB about three, so an "expected outcome time" would
    differ between them.

    With the old 2-hour tolerance every link failed by an hour, and a full live
    slate produced zero recommendations.
    """

    def _fixture(self, commence_ms: int) -> MatchCandidate:
        return MatchCandidate(
            odds_event_id="odds-1",
            commence_ms=commence_ms,
            home_team="Pittsburgh Pirates",
            away_team="New York Mets",
        )

    def _link(self, candidates, *, kalshi_commence_ms):
        return link_event(
            kalshi_event_ticker="KXMLBGAME-26AUG071840NYMPIT",
            kalshi_teams=("New York M", "Pittsburgh"),
            kalshi_commence_ms=kalshi_commence_ms,
            candidates=candidates,
            aliases=load_aliases("baseball_mlb"),
        )

    def test_the_observed_offset_still_links(self):
        """The regression. This is the exact shape that failed live."""
        book_start = 1_786_142_460_000
        kalshi_start = book_start + OBSERVED_KALSHI_COMMENCE_OFFSET_MS

        result = self._link(
            [self._fixture(book_start)], kalshi_commence_ms=kalshi_start
        )
        assert result.matched, result.reason
        # The skew is kept rather than corrected away, so the offset stays
        # visible in the data and a change in it is detectable.
        assert result.commence_skew_ms == -OBSERVED_KALSHI_COMMENCE_OFFSET_MS

    def test_the_tolerance_still_excludes_a_genuinely_different_fixture(self):
        """Widening must not become 'match anything the same teams played'."""
        book_start = 1_786_142_460_000
        far = book_start + DEFAULT_COMMENCE_TOLERANCE_MS + 60_000

        result = self._link([self._fixture(book_start)], kalshi_commence_ms=far)
        assert not result.matched
        assert "commence-time window" in result.reason

    def test_a_doubleheader_inside_the_window_refuses_rather_than_guessing(self):
        """Why widening is safe, asserted rather than assumed.

        The offset makes this sharper, not softer: game one's shifted Kalshi
        time lands near game two's true start, so a *tight* window is what would
        silently pick the wrong game. A wide one sees both and refuses.
        """
        first = 1_786_142_460_000
        second = first + 4 * 3600 * 1000
        result = self._link(
            [self._fixture(first), MatchCandidate(
                odds_event_id="odds-2", commence_ms=second,
                home_team="Pittsburgh Pirates", away_team="New York Mets",
            )],
            kalshi_commence_ms=first + OBSERVED_KALSHI_COMMENCE_OFFSET_MS,
        )
        assert not result.matched
        assert "ambiguous" in result.reason
