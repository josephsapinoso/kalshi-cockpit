"""When the odds sweep fires, and whether a pick is bettable right now.

The behaviour under test is the answer to a question the project had never
asked: the free tier affords two sweeps a day, each opens a fifteen-minute
window, and until now those two windows landed wherever the process happened to
restart. On 2026-08-07 that was 19:32Z, because a deploy happened then.

What these tests do NOT establish
---------------------------------
That a window is worth opening. Every assertion here is about *timing* --
whether odds are fresh enough for a pick to survive `stale_odds`, and whether
the fifteen minutes sit before a kickoff. Whether anything appears in that
window is the question the whole project exists to answer and no test can
settle it.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.odds.budget import CreditBudget, sweep_cost
from backend.odds.timing import (
    CLUSTER_MS,
    DUE_WINDOW_MS,
    MIN_SLOT_SEPARATION_MS,
    ActionableWindow,
    cluster_kickoffs,
    day_start_ms,
    decide_sweeps,
    fixture_freshness,
    plan_sweep_slots,
    slots_for_sport,
    sweep_window_survives_interval,
    upcoming_fixtures_by_sport,
    window_status,
)
from backend.scheduler import JITTER
from backend.store import db

MIN = 60_000
HOUR = 3_600_000


def ms(iso: str) -> int:
    return int(
        datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000
    )


# 18:00Z on a summer Friday: mid-afternoon ET, hours before the evening slate.
NOW = ms("2026-08-07T18:00:00")
MAX_ODDS_AGE_MS = 900_000  # matches SuppressionConfig.max_odds_age_ms


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "timing.db")
    yield c
    c.close()


@pytest.fixture
def budget(conn):
    return CreditBudget(conn, daily_budget=16)


def add_fixture(
    conn,
    *,
    sport_key="baseball_mlb",
    odds_event_id="e1",
    commence_ms=NOW + HOUR,
    fetched_ms=NOW,
    book_updated_ms=None,
    bookmakers=("pinnacle", "draftkings"),
    market="h2h",
):
    """One stored sportsbook fixture, two books, both sides."""
    for book in bookmakers:
        for outcome in ("Home", "Away"):
            conn.execute(
                "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, "
                "sport_key, odds_event_id, commence_ms, home_team, away_team, "
                "bookmaker, market, outcome_name, price_decimal) "
                "VALUES (?, ?, ?, ?, ?, 'Home', 'Away', ?, ?, ?, 2.0)",
                (
                    fetched_ms, book_updated_ms, sport_key, odds_event_id,
                    commence_ms, book, market, outcome,
                ),
            )
    conn.commit()


class TestTheAnchorIsTheSportsbookClock:
    """Kalshi's `occurrence_datetime` runs exactly three hours late.

    A sweep scheduled twenty minutes before that field fires two hours and
    forty minutes into the game -- the same trap `scoring.py` documents for the
    closing line, where it would have produced a strong and entirely fake CLV
    signal. So the schedule reads kickoff times from `odds_snapshots`, which
    carries The Odds API's own `commence_ms`.
    """

    def test_kickoffs_come_from_stored_odds_not_from_kalshi_events(self, conn):
        true_kickoff = NOW + 2 * HOUR
        add_fixture(conn, commence_ms=true_kickoff)
        # The same game as Kalshi sees it: three hours late.
        conn.execute(
            "INSERT INTO kalshi_events (event_ticker, commence_ms, first_seen_ms, "
            "last_seen_ms) VALUES ('KX-GAME', ?, ?, ?)",
            (true_kickoff + 3 * HOUR, NOW, NOW),
        )
        conn.commit()

        fixtures = upcoming_fixtures_by_sport(conn, now_ms=NOW)
        assert fixtures == {"baseball_mlb": [true_kickoff]}

    def test_scheduling_against_kalshis_clock_would_fire_during_the_game(self):
        """States the bug as an invariant rather than trusting the read path.

        If the three-hour-late time were ever fed in, the window would open
        after the real first pitch. The assertion is on the arithmetic, so it
        fails whichever way the wrong number arrives.
        """
        real_kickoff = NOW + 2 * HOUR
        kalshi_says = real_kickoff + 3 * HOUR

        [good] = slots_for_sport(
            "baseball_mlb", [real_kickoff],
            now_ms=NOW, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        [bad] = slots_for_sport(
            "baseball_mlb", [kalshi_says],
            now_ms=NOW, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert good.fire_until_ms <= real_kickoff
        assert bad.fire_from_ms > real_kickoff  # the whole window is in-play


class TestTheWindowClosesBeforeTheFirstPitch:
    def test_the_last_moment_to_fire_is_exactly_one_window_before_kickoff(self):
        """Definitional, and chosen where the wrong implementations differ.

        Dropping the lead entirely gives `fire_until == kickoff`; using minutes
        where milliseconds are meant gives `kickoff - 900`. Only one answer
        leaves a pick surfaced at the last second of the window still pre-game.
        """
        kickoff = NOW + 2 * HOUR
        [slot] = slots_for_sport(
            "baseball_mlb", [kickoff],
            now_ms=NOW, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert slot.fire_until_ms == kickoff - MAX_ODDS_AGE_MS
        assert slot.fire_from_ms == kickoff - MAX_ODDS_AGE_MS - DUE_WINDOW_MS

    def test_the_lead_follows_the_staleness_limit_it_exists_to_serve(self):
        """One quantity, one source. A separately-written lead would drift."""
        kickoff = NOW + 5 * HOUR
        for age_ms in (300_000, 900_000, 1_800_000):
            [slot] = slots_for_sport(
                "baseball_mlb", [kickoff], now_ms=NOW, max_odds_age_ms=age_ms
            )
            assert kickoff - slot.fire_until_ms == age_ms

    def test_a_cluster_too_close_to_start_gets_no_slot(self):
        """Sweeping now would open a window that runs into the game."""
        assert slots_for_sport(
            "baseball_mlb", [NOW + 10 * MIN],
            now_ms=NOW, max_odds_age_ms=MAX_ODDS_AGE_MS,
        ) == []

    def test_a_game_beyond_the_horizon_gets_no_slot(self):
        assert slots_for_sport(
            "baseball_mlb", [NOW + 6 * 24 * HOUR],
            now_ms=NOW, max_odds_age_ms=MAX_ODDS_AGE_MS,
        ) == []


class TestClustering:
    def test_a_staggered_slate_is_one_cluster(self):
        base = NOW + 5 * HOUR
        assert cluster_kickoffs([base, base + 5 * MIN, base + 10 * MIN]) == [base]

    def test_blocks_further_apart_than_the_cluster_stay_separate(self):
        base = NOW + 5 * HOUR
        gap = CLUSTER_MS + MIN
        assert cluster_kickoffs([base, base + gap]) == [base, base + gap]

    def test_the_anchor_is_the_earliest_kickoff_not_the_middle(self):
        """Anchoring on the middle would put the cluster's first game in play.

        The discriminating case: three kickoffs, and only the earliest gives a
        window that closes before all three.
        """
        base = NOW + 5 * HOUR
        kickoffs = [base, base + 8 * MIN, base + 16 * MIN]
        [anchor] = cluster_kickoffs(kickoffs)
        assert anchor == base
        assert anchor != sorted(kickoffs)[1]


class TestSelectionPrefersTheBiggestCluster:
    """The behaviour change from `plan_sweep`, which ranked by soonest.

    Soonest is the wrong ranking when there are two calls a day: a sweep before
    one lonely afternoon game costs the same as one before eight evening games.
    """

    def test_the_busiest_cluster_wins_over_the_soonest(self):
        afternoon = NOW + 2 * HOUR
        evening = NOW + 6 * HOUR
        slots = plan_sweep_slots(
            {
                "baseball_mlb": [afternoon] + [evening + i * MIN for i in range(8)],
            },
            now_ms=NOW, slots_available=1, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert [s.anchor_commence_ms for s in slots] == [evening]
        assert slots[0].games_covered == 8

    def test_a_tie_goes_to_the_earlier_slot(self):
        """An earlier sweep leaves the later cluster schedulable. Not vice versa."""
        first = NOW + 3 * HOUR
        second = NOW + 9 * HOUR
        slots = plan_sweep_slots(
            {"baseball_mlb": [first, second]},
            now_ms=NOW, slots_available=1, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert slots[0].anchor_commence_ms == first

    def test_it_returns_no_more_than_the_budget_affords(self):
        starts = [NOW + (2 + 3 * i) * HOUR for i in range(5)]
        slots = plan_sweep_slots(
            {"baseball_mlb": starts},
            now_ms=NOW, slots_available=2, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert len(slots) == 2

    def test_two_slots_for_one_sport_are_never_adjacent(self):
        """Overlapping coverage spends the second call on the first call's games."""
        base = NOW + 3 * HOUR
        starts = [base + i * 25 * MIN for i in range(6)]
        slots = plan_sweep_slots(
            {"baseball_mlb": starts},
            now_ms=NOW, slots_available=2, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        if len(slots) == 2:
            gap = abs(
                slots[0].anchor_commence_ms - slots[1].anchor_commence_ms
            )
            assert gap >= MIN_SLOT_SEPARATION_MS

    def test_slots_come_back_in_chronological_order(self):
        slots = plan_sweep_slots(
            {
                "baseball_mlb": [NOW + 8 * HOUR] * 5 + [NOW + 3 * HOUR],
                "basketball_wnba": [NOW + 4 * HOUR] * 3,
            },
            now_ms=NOW, slots_available=3, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert [s.anchor_commence_ms for s in slots] == sorted(
            s.anchor_commence_ms for s in slots
        )


class TestAServedSlotIsNotSweptTwice:
    """Read back from recorded spend, so a restart mid-window cannot double-pay."""

    def test_a_sweep_inside_the_window_retires_the_slot(self):
        kickoff = NOW + 3 * HOUR
        [slot] = plan_sweep_slots(
            {"baseball_mlb": [kickoff]},
            now_ms=NOW, slots_available=1, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert plan_sweep_slots(
            {"baseball_mlb": [kickoff]},
            now_ms=NOW,
            slots_available=1,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
            last_sweep_ms_by_sport={"baseball_mlb": slot.fire_from_ms + MIN},
        ) == []

    def test_an_earlier_sweep_does_not_retire_a_later_slot(self):
        """Otherwise the morning's bootstrap would cancel the evening's window."""
        kickoff = NOW + 3 * HOUR
        [slot] = plan_sweep_slots(
            {"baseball_mlb": [kickoff]},
            now_ms=NOW, slots_available=1, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        still = plan_sweep_slots(
            {"baseball_mlb": [kickoff]},
            now_ms=NOW,
            slots_available=1,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
            last_sweep_ms_by_sport={"baseball_mlb": slot.fire_from_ms - MIN},
        )
        assert [s.anchor_commence_ms for s in still] == [kickoff]


class TestTheBudgetDayIsASportsDay:
    """UTC midnight is 5pm PT -- the middle of the slate it is metering."""

    def test_one_nights_games_share_one_budget_day(self):
        """The discriminating case: a calendar day splits these three."""
        first_pitch = ms("2026-08-07T23:05:00")   # 7:05pm ET
        west_coast = ms("2026-08-08T02:10:00")    # 7:10pm PT
        extra_innings = ms("2026-08-08T05:30:00")
        days = {day_start_ms(t) for t in (first_pitch, west_coast, extra_innings)}
        assert len(days) == 1

        calendar_days = {
            datetime.fromtimestamp(t / 1000, timezone.utc).date()
            for t in (first_pitch, west_coast, extra_innings)
        }
        assert len(calendar_days) == 2  # which is what made this worth changing

    def test_the_day_rolls_at_the_configured_hour(self):
        assert day_start_ms(ms("2026-08-07T09:59:00")) == ms("2026-08-06T10:00:00")
        assert day_start_ms(ms("2026-08-07T10:00:00")) == ms("2026-08-07T10:00:00")

    def test_the_budget_meters_against_the_same_day_the_schedule_uses(self, conn):
        """Two boundaries for one day is how "spent today" and "swept today"
        stop meaning the same thing."""
        b = CreditBudget(conn, daily_budget=16)
        assert b.day_start_ms(NOW) == day_start_ms(NOW, hour=b.day_start_hour)

    def test_spend_before_the_roll_belongs_to_the_previous_day(self, conn):
        b = CreditBudget(conn, daily_budget=16)
        b.record(called_ms=ms("2026-08-07T09:00:00"), endpoint="/odds", cost=12)
        assert b.state(ms("2026-08-07T11:00:00")).spent_today == 0


class TestTheDueWindowSurvivesTheLoopInterval:
    """Two limits on one quantity, in modules that do not import each other.

    A slot due for thirty minutes on a loop that wakes every forty is missed
    most days -- and a missed sweep is indistinguishable from a quiet slate,
    which is the failure this whole module exists to remove.
    """

    def test_the_shipped_default_interval_lands_inside_a_slot(self):
        assert sweep_window_survives_interval(900.0, jitter=JITTER)

    def test_an_interval_wider_than_the_window_is_rejected(self):
        assert not sweep_window_survives_interval(1800.0, jitter=JITTER)

    def test_the_boundary_accounts_for_jitter_not_just_the_nominal_interval(self):
        """At 27 minutes the nominal interval fits in a 30-minute window and the
        jittered worst case does not. A check that forgot jitter passes here."""
        interval = 27 * 60.0
        assert interval * 1000 < DUE_WINDOW_MS
        assert not sweep_window_survives_interval(interval, jitter=JITTER)


class TestDecidingOnOnePass:
    def test_it_fires_when_the_pass_lands_inside_a_slot(self, conn, budget):
        kickoff = NOW + 40 * MIN
        add_fixture(conn, commence_ms=kickoff)
        decision = decide_sweeps(
            conn,
            in_scope={"baseball_mlb": kickoff + 3 * HOUR},
            budget=budget, cost=6, now_ms=NOW, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert [f.sport_key for f in decision.fire] == ["baseball_mlb"]
        assert decision.fire[0].trigger == "scheduled"

    def test_it_holds_the_credit_when_kickoff_is_hours_away(self, conn, budget):
        """The whole point. `plan_sweep` fired here and burned the day's odds
        at whatever time the process happened to start."""
        kickoff = NOW + 6 * HOUR
        add_fixture(conn, commence_ms=kickoff)
        decision = decide_sweeps(
            conn,
            in_scope={"baseball_mlb": kickoff + 3 * HOUR},
            budget=budget, cost=6, now_ms=NOW, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert decision.fire == ()
        assert "next slot" in decision.detail

    def test_not_sweeping_always_says_why(self, conn, budget):
        """A pass that skips the sweep silently reads exactly like one that
        swept and found nothing."""
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        decision = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=6, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert decision.detail

    def test_an_exhausted_budget_refuses_and_names_the_spend(self, conn, budget):
        kickoff = NOW + 40 * MIN
        add_fixture(conn, commence_ms=kickoff)
        budget.record(called_ms=NOW - HOUR, endpoint="/odds", cost=12,
                      sport_key="basketball_wnba")
        decision = decide_sweeps(
            conn,
            in_scope={"baseball_mlb": kickoff + 3 * HOUR},
            budget=budget, cost=6, now_ms=NOW, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert decision.fire == ()
        assert "12 of 16" in decision.detail

    def test_a_sport_with_no_stored_fixtures_bootstraps(self, conn, budget):
        """Nothing to schedule against, and nothing priceable until we look."""
        decision = decide_sweeps(
            conn,
            in_scope={"baseball_mlb": NOW + 5 * HOUR},
            budget=budget, cost=6, now_ms=NOW, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert [f.trigger for f in decision.fire] == ["bootstrap"]

    def test_bootstrap_does_not_repeat_within_the_budget_day(self, conn, budget):
        """A sport the sportsbook does not cover would otherwise bootstrap on
        every pass and drain the day's credits in an hour."""
        budget.record(
            called_ms=NOW - HOUR, endpoint="/odds", cost=6,
            sport_key="baseball_mlb",
        )
        decision = decide_sweeps(
            conn,
            in_scope={"baseball_mlb": NOW + 5 * HOUR},
            budget=budget, cost=6, now_ms=NOW, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert decision.fire == ()

    def test_bootstrap_takes_one_sport_per_pass(self, conn, budget):
        decision = decide_sweeps(
            conn,
            in_scope={
                "baseball_mlb": NOW + 5 * HOUR,
                "basketball_wnba": NOW + 4 * HOUR,
                "americanfootball_nfl": NOW + 7 * HOUR,
            },
            budget=budget, cost=6, now_ms=NOW, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert len(decision.fire) == 1
        # The soonest Kalshi kickoff. A constant three-hour offset does not
        # change an ordering, which is the only thing that field is used for.
        assert decision.fire[0].sport_key == "basketball_wnba"

    def test_a_sport_beyond_the_horizon_does_not_bootstrap(self, conn, budget):
        decision = decide_sweeps(
            conn,
            in_scope={"americanfootball_nfl": NOW + 40 * 24 * HOUR},
            budget=budget, cost=6, now_ms=NOW, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert decision.fire == ()


class TestTheWindowIsMeasuredFromTheBooksOwnClock:
    """`stale_odds` reads the bookmaker's `last_update`, not our fetch time.

    A window computed from when we called would report fresh odds that
    suppression is about to reject -- the flattering direction, and the one that
    puts unbettable rows in front of someone holding a phone.
    """

    def test_a_book_stamped_half_an_hour_ago_is_not_fresh_now(self, conn):
        add_fixture(
            conn,
            commence_ms=NOW + 2 * HOUR,
            fetched_ms=NOW,                     # we just called
            book_updated_ms=NOW - 30 * MIN,     # the book did not just move
        )
        assert fixture_freshness(conn, now_ms=NOW) == [30 * MIN]

    def test_a_missing_book_timestamp_falls_back_to_our_fetch(self, conn):
        add_fixture(
            conn, commence_ms=NOW + 2 * HOUR,
            fetched_ms=NOW - 5 * MIN, book_updated_ms=None,
        )
        assert fixture_freshness(conn, now_ms=NOW) == [5 * MIN]

    def test_a_fixture_is_only_as_fresh_as_its_stalest_book(self, conn):
        add_fixture(
            conn, odds_event_id="e1", commence_ms=NOW + 2 * HOUR,
            fetched_ms=NOW, book_updated_ms=NOW - MIN, bookmakers=("pinnacle",),
        )
        conn.execute(
            "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, sport_key, "
            "odds_event_id, commence_ms, home_team, away_team, bookmaker, market, "
            "outcome_name, price_decimal) "
            "VALUES (?, ?, 'baseball_mlb', 'e1', ?, 'Home', 'Away', "
            "'draftkings', 'h2h', 'Home', 2.0)",
            (NOW, NOW - 20 * MIN, NOW + 2 * HOUR),
        )
        conn.commit()
        assert fixture_freshness(conn, now_ms=NOW) == [20 * MIN]

    def test_only_the_latest_sweep_counts_for_a_fixture(self, conn):
        """Mixing sweeps would pair a two-minute-old book with an hour-old one
        and call the disagreement consensus width."""
        add_fixture(
            conn, odds_event_id="e1", commence_ms=NOW + 2 * HOUR,
            fetched_ms=NOW - 2 * HOUR, book_updated_ms=NOW - 2 * HOUR,
        )
        add_fixture(
            conn, odds_event_id="e1", commence_ms=NOW + 2 * HOUR,
            fetched_ms=NOW, book_updated_ms=NOW - 3 * MIN,
        )
        assert fixture_freshness(conn, now_ms=NOW) == [3 * MIN]


class TestWindowStatus:
    def test_a_fresh_slate_reports_open_with_time_left(self, conn, budget):
        add_fixture(
            conn, commence_ms=NOW + 2 * HOUR,
            fetched_ms=NOW, book_updated_ms=NOW - 5 * MIN,
        )
        status = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=6,
        )
        assert status.is_open
        assert status.seconds_remaining == 600  # 15 min limit, 5 min elapsed

    def test_a_stale_slate_reports_closed(self, conn, budget):
        add_fixture(
            conn, commence_ms=NOW + 2 * HOUR,
            fetched_ms=NOW - HOUR, book_updated_ms=NOW - HOUR,
        )
        status = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=6,
        )
        assert not status.is_open
        assert status.seconds_remaining is None
        assert status.fixtures_upcoming == 1
        assert status.fixtures_fresh == 0

    def test_a_half_fresh_slate_is_counted_not_averaged(self, conn, budget):
        """"Open" is a property of each fixture's books, and a slate can be
        half stale -- one number for it would be a claim about neither."""
        add_fixture(
            conn, odds_event_id="fresh", commence_ms=NOW + 2 * HOUR,
            fetched_ms=NOW, book_updated_ms=NOW - MIN,
        )
        add_fixture(
            conn, odds_event_id="stale", commence_ms=NOW + 2 * HOUR,
            fetched_ms=NOW - HOUR, book_updated_ms=NOW - HOUR,
        )
        status = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=6,
        )
        assert (status.fixtures_upcoming, status.fixtures_fresh) == (2, 1)
        assert status.is_open

    def test_it_reports_the_next_sweep_the_runner_would_actually_make(
        self, conn, budget
    ):
        """The screen and the control share one planner. Two would disagree,
        and the screen is the one that gets believed."""
        kickoff = NOW + 5 * HOUR
        add_fixture(conn, commence_ms=kickoff)
        status = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=6,
        )
        assert status.next_slot is not None
        assert status.next_slot.fire_until_ms == kickoff - MAX_ODDS_AGE_MS
        assert status.sweeps_remaining_today == 2

    def test_it_serialises_without_promising_an_opportunity(self, conn, budget):
        add_fixture(conn, commence_ms=NOW + 2 * HOUR, book_updated_ms=NOW)
        payload = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=6,
        ).to_dict()
        assert payload["is_open"] is True
        assert "does not mean there is anything to bet" in payload["note"]


class TestCostIsUnchanged:
    def test_a_sweep_still_costs_markets_times_regions(self):
        assert sweep_cost(["h2h", "spreads", "totals"], ["us", "eu"]) == 6
