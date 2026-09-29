"""`backend/core/team_rest.py` -- rest before a game, from two start times (#201).

What these tests establish: the gap is measured in hours between start times
(a game across a UTC midnight is still a back-to-back); NFL Thursday after
Sunday is a short week and a bye is not; MLB carries `days_rest` alone; no
previous game is `None` on every field, never `0`.

What they do not establish: that rest predicts anything, or that the feed's
schedule is complete.
"""

from __future__ import annotations

from backend.core.team_rest import RestFacts, rest_facts

H = 3_600_000
D = 24 * H
# 2026-01-14 23:00Z: 6pm ET Wednesday.
T0 = 1_768_431_600_000


class TestHoursNotDates:
    def test_a_late_tip_across_utc_midnight_is_a_back_to_back(self):
        # Game 1 tips 23:30Z on the 14th, game 2 tips 00:30Z on the 16th:
        # calendar dates differ by TWO days, real gap is 25 hours.
        prev = T0 + H // 2
        this = prev + 25 * H
        f = rest_facts("basketball_nba", this, prev)
        assert f.back_to_back is True
        assert f.days_rest == 0

    def test_two_days_between_games_is_one_day_of_rest(self):
        f = rest_facts("icehockey_nhl", T0 + 2 * D, T0)
        assert f == RestFacts(days_rest=1, back_to_back=False, short_week=None)

    def test_thirty_five_hours_is_a_back_to_back_and_thirty_six_is_not(self):
        assert rest_facts("basketball_wnba", T0 + 35 * H, T0).back_to_back is True
        assert rest_facts("basketball_wnba", T0 + 36 * H, T0).back_to_back is False


class TestFootball:
    def test_thursday_after_sunday_is_a_short_week(self):
        f = rest_facts("americanfootball_nfl", T0 + 4 * D, T0)
        assert f.short_week is True
        assert f.days_rest == 3
        assert f.back_to_back is None

    def test_a_bye_is_not_a_short_week(self):
        f = rest_facts("americanfootball_nfl", T0 + 14 * D, T0)
        assert f.short_week is False
        assert f.days_rest == 13

    def test_ncaaf_reads_the_same(self):
        assert rest_facts("americanfootball_ncaaf", T0 + 5 * D, T0).short_week is True


class TestMlb:
    def test_mlb_has_days_of_rest_and_no_back_to_back_field(self):
        f = rest_facts("baseball_mlb", T0 + 1 * D, T0)
        assert f.days_rest == 0
        assert f.back_to_back is None
        assert f.short_week is None


class TestNoPreviousGame:
    def test_every_field_is_none_never_zero(self):
        for sport in (
            "basketball_nba", "icehockey_nhl", "americanfootball_nfl",
            "baseball_mlb",
        ):
            f = rest_facts(sport, T0, None)
            assert f == RestFacts(None, None, None), sport
            assert f.days_rest is None and f.days_rest != 0

    def test_a_previous_start_not_before_this_one_is_unknown_too(self):
        assert rest_facts("baseball_mlb", T0, T0) == RestFacts(None, None, None)
