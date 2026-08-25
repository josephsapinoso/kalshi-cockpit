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
    COVERAGE_MS,
    DESK,
    DUE_WINDOW_MS,
    MIN_SLOT_SEPARATION_MS,
    REFRESH,
    SCHEDULED,
    ActionableWindow,
    cluster_kickoffs,
    day_start_ms,
    decide_sweeps,
    desk_window_contains,
    firing_for_slot,
    first_window_open_of_day,
    fixture_freshness,
    next_desk_open_ms,
    plan_sweep_slots,
    refresh_interval_ms,
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
# Derived, never written down as 600_000. Pinning the number here would be a
# second definition of the quantity `refresh_interval_ms` owns, and this file
# would then keep passing while the two disagreed.
REFRESH_MS = refresh_interval_ms(MAX_ODDS_AGE_MS)


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


class TestAServedSlotIsSweptAgainOnTheRefreshInterval:
    """The rolling refresh, stated as the rule it replaced.

    Until 2026-08-16 a served slot was retired: one buy per cluster, a window
    good for `max_odds_age_ms`, and every row priced afterwards suppressed as
    `stale_odds` with the games still an hour away. `firing_for_slot` now
    answers *when it was last served* rather than *whether it ever was*.

    Read back from recorded spend, so a restart mid-window still cannot
    double-pay: the interval is measured against `api_credits`, not memory.
    """

    def _slot(self):
        kickoff = NOW + 3 * HOUR
        [slot] = plan_sweep_slots(
            {"baseball_mlb": [kickoff]},
            now_ms=NOW, slots_available=1, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        return slot

    def test_a_slot_wants_its_first_call_when_nothing_has_been_served(self):
        slot = self._slot()
        assert firing_for_slot(
            slot, now_ms=slot.fire_from_ms + MIN, last_sweep_ms=None,
            refresh_interval_ms=REFRESH_MS,
        ) == SCHEDULED

    def test_a_sweep_just_served_does_not_buy_again(self):
        """The double-pay this replaces. One minute in, the odds are fresh."""
        slot = self._slot()
        served = slot.fire_from_ms + MIN
        assert firing_for_slot(
            slot, now_ms=served + MIN, last_sweep_ms=served,
            refresh_interval_ms=REFRESH_MS,
        ) is None

    def test_the_same_slot_buys_again_once_the_interval_has_passed(self):
        """The whole change. The old rule returned nothing here, for ever."""
        slot = self._slot()
        served = slot.fire_from_ms + MIN
        assert firing_for_slot(
            slot, now_ms=served + REFRESH_MS, last_sweep_ms=served,
            refresh_interval_ms=REFRESH_MS,
        ) == REFRESH

    def test_the_refresh_stops_when_the_slot_closes(self):
        """`fire_until_ms` is one whole freshness window before first pitch, so
        a refresh after it would price a game that has effectively started."""
        slot = self._slot()
        assert firing_for_slot(
            slot, now_ms=slot.fire_until_ms + MIN,
            last_sweep_ms=slot.fire_until_ms - REFRESH_MS,
            refresh_interval_ms=REFRESH_MS,
        ) is None

    def test_an_earlier_sweep_does_not_count_as_opening_this_slot(self):
        """Otherwise the morning's bootstrap would read as the evening's window
        already being open, and the cluster would never be priced at all."""
        slot = self._slot()
        assert firing_for_slot(
            slot, now_ms=slot.fire_from_ms + MIN,
            last_sweep_ms=slot.fire_from_ms - MIN,
            refresh_interval_ms=REFRESH_MS,
        ) == SCHEDULED

    def test_planning_no_longer_retires_a_served_slot(self):
        """The planner answers "is this cluster worth a window" and nothing else.
        Whether it wants a call *now* moved to `firing_for_slot`."""
        kickoff = NOW + 3 * HOUR
        twice = plan_sweep_slots(
            {"baseball_mlb": [kickoff]},
            now_ms=NOW, slots_available=1, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert [s.anchor_commence_ms for s in twice] == [kickoff]


class TestTheRefreshCadenceIsDerivedFromTheStalenessLimit:
    """Two constants for one quantity drift, and the tighter wins in silence."""

    def test_the_refresh_lands_before_the_odds_expire(self):
        assert refresh_interval_ms(MAX_ODDS_AGE_MS) < MAX_ODDS_AGE_MS

    def test_it_leaves_room_for_a_pass_to_notice(self):
        """A refresh only fires when a pass runs, so the true worst-case age is
        the interval plus one pass gap. The quote cadence is 15s; the headroom
        has to cover it and does, with a wide margin."""
        headroom_ms = MAX_ODDS_AGE_MS - refresh_interval_ms(MAX_ODDS_AGE_MS)
        assert headroom_ms > 15_000 * (1 + JITTER)

    def test_it_moves_with_the_limit_rather_than_being_pinned(self):
        assert refresh_interval_ms(2 * MAX_ODDS_AGE_MS) == 2 * refresh_interval_ms(
            MAX_ODDS_AGE_MS
        )


class TestThePlannerReservesTheWindowItOpens:
    """A slot costs one call plus one per interval, not one call."""

    def test_a_slot_counts_the_calls_left_before_it_closes(self):
        kickoff = NOW + 3 * HOUR
        [slot] = plan_sweep_slots(
            {"baseball_mlb": [kickoff]},
            now_ms=NOW, slots_available=1, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        span = slot.fire_until_ms - slot.fire_from_ms
        assert slot.calls_remaining(slot.fire_from_ms, REFRESH_MS) == (
            1 + span // REFRESH_MS
        )

    def test_a_slot_half_spent_reserves_only_what_it_still_needs(self):
        kickoff = NOW + 3 * HOUR
        [slot] = plan_sweep_slots(
            {"baseball_mlb": [kickoff]},
            now_ms=NOW, slots_available=1, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        early = slot.calls_remaining(slot.fire_from_ms, REFRESH_MS)
        late = slot.calls_remaining(slot.fire_until_ms, REFRESH_MS)
        assert late < early
        assert late == 1        # a due slot always wants at least the call now


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

    A slot due for `DUE_WINDOW_MS` on a loop that wakes less often is missed
    most days -- and a missed sweep is indistinguishable from a quiet slate,
    which is the failure this whole module exists to remove.

    **Every bound here is derived from `DUE_WINDOW_MS`, not written down.** They
    were literals against the old thirty-minute window, so widening it to sixty
    failed these tests for the one reason a test must never fail: the constant
    moved and the test had its own copy of it.
    """

    def test_the_shipped_default_interval_lands_inside_a_slot(self):
        assert sweep_window_survives_interval(900.0, jitter=JITTER)

    def test_an_interval_wider_than_the_window_is_rejected(self):
        too_slow = (DUE_WINDOW_MS / 1000) * 2
        assert not sweep_window_survives_interval(too_slow, jitter=JITTER)

    def test_the_boundary_accounts_for_jitter_not_just_the_nominal_interval(self):
        """An interval whose nominal value fits the window and whose jittered
        worst case does not. A check that forgot jitter passes here."""
        interval = (DUE_WINDOW_MS / 1000) * 0.95
        assert interval * 1000 < DUE_WINDOW_MS          # nominal fits
        assert interval * (1 + JITTER) * 1000 > DUE_WINDOW_MS   # jittered does not
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

    def test_it_holds_the_slot_credit_when_kickoff_is_hours_away(
        self, conn, budget
    ):
        """The whole point. `plan_sweep` fired here and burned the day's odds
        at whatever time the process happened to start.

        **Re-scoped 2026-08-25, and the claim is narrowed rather than dropped.**
        It asserted `decision.fire == ()`, which stopped being the right
        assertion when the desk gained an hourly floor: a sport playing in six
        hours is inside that floor's horizon, so *something* now fires here by
        design (ADR 0071 §2.6).

        What this test was ever about is the **slot planner** — that a kickoff
        six hours out does not open its pre-game window early. That is still
        exactly true and is what is asserted now. The floor is a different
        trigger with a different cadence (hourly, not the 30-minute slot) and a
        different job (keep the slate priced between clusters, not target the
        close), and conflating them is what would let a real regression in the
        slot planner hide behind a desk buy.
        """
        kickoff = NOW + 6 * HOUR
        add_fixture(conn, commence_ms=kickoff)
        decision = decide_sweeps(
            conn,
            in_scope={"baseball_mlb": kickoff + 3 * HOUR},
            budget=budget, cost=6, now_ms=NOW, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert [f.trigger for f in decision.fire] == [DESK]
        assert not any(f.trigger == SCHEDULED for f in decision.fire)
        assert decision.fire[0].slot is None
        # The slot is still planned and still not due. `detail` now describes
        # what fired rather than why nothing did — that is `decide_sweeps`'s
        # standing contract, not a change — so the slot's own state is read off
        # `slots_planned`, which is where it was always true.
        assert decision.slots_planned
        assert not any(s.is_due(NOW) for s in decision.slots_planned)

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


class TestTheDeskWindowKeepsTheSlatePriced:
    """Inside the configured desk window, a fixtured sport re-buys on the
    refresh cadence whether or not a kickoff cluster is imminent.

    The behaviour under test exists because the slot design alone targets the
    closing line: measured 2026-08-23, the slate spent ~14 hours at 89%
    `stale_odds` refusals while the day's budget sat at 0 of 600 spent. What
    these tests do NOT establish: that a priced slate contains anything worth
    betting -- the desk window re-prices the comparison, it cannot change what
    the comparison says.
    """

    # NOW is 18:00Z, inside 16-04 and outside 20-04.
    OPEN = (16, 4)
    CLOSED = (20, 4)

    def test_a_fixtured_sport_rebuys_inside_the_window(self, conn, budget):
        """Kickoff six hours out -- no slot is due -- and the desk fires
        anyway, as a desk buy, costing the team sweep alone."""
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        decision = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=6, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, desk_window=self.OPEN,
        )
        assert [f.trigger for f in decision.fire] == [DESK]
        assert decision.fire[0].sport_key == "baseball_mlb"
        assert decision.fire[0].projected_total_cost == 6
        assert decision.fire[0].prop_event_ids == ()

    def test_outside_the_window_the_floor_buys_and_the_reopen_is_named(
        self, conn, budget
    ):
        """**INVERTED 2026-08-25**, and the inversion is the lane's whole point.

        This asserted `decision.fire == ()` — outside the configured window the
        credit was held. It is now a floor buy, because a shut clock window is
        no longer the same fact as "nobody wants these odds": the desk follows
        attention over an hourly floor (ADR 0071 §2.6), and a sport playing in
        six hours is inside the floor's twelve-hour horizon.

        The reopen sentence is unchanged and still asserted. It is the honest
        thing to say while the window is shut, and the window is still a
        configured input even though it is no longer the only one.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        decision = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=6, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, desk_window=self.CLOSED,
        )
        assert [f.trigger for f in decision.fire] == [DESK]
        assert "hourly floor" in decision.fire[0].detail

    def test_a_shut_window_with_nothing_to_buy_still_names_the_reopen(
        self, conn, budget
    ):
        """The reopen sentence, kept — on the path where it is still reachable.

        It used to be asserted on the test above, which no longer reaches it:
        `decision.detail` describes what fired, and now something does. The
        sentence itself is not obsolete, because a shut window with every sport
        outside the floor's horizon is a real state and "nothing fired" needs
        its reason.
        """
        add_fixture(conn, commence_ms=NOW + 20 * HOUR)
        decision = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=6, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, desk_window=self.CLOSED,
        )
        assert decision.fire == ()
        assert "reopens at 20:00Z" in decision.detail

    def test_no_window_configured_still_gets_the_floor(self, conn, budget):
        """**INVERTED 2026-08-25.** Was "`None` is the default, so every
        existing caller is unchanged".

        That is no longer true and is no longer wanted: `fly.live.toml` unsets
        `ODDS_DESK_WINDOW_UTC` in this lane, so `None` is what the deployed
        instance now passes. If `None` still meant "hold the credit", unsetting
        the window would turn the feed off rather than hand it to attention.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        decision = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=6, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert [f.trigger for f in decision.fire] == [DESK]

    def test_a_sport_outside_the_floor_horizon_is_not_bought(self, conn, budget):
        """The floor's own bound, and the reason it is not "any upcoming
        fixture" (Joe's answer, 2026-08-25).

        A Sunday NFL slate must stop buying on Wednesday. At four sports the
        difference between a twelve-hour horizon and an unbounded one is paying
        an hourly rate for fixtures nobody will look at for days.
        """
        add_fixture(conn, commence_ms=NOW + 20 * HOUR)
        decision = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=6, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert decision.fire == ()

    def test_the_desk_paces_itself_on_the_refresh_interval(self, conn, budget):
        """A sweep younger than the interval holds; one at the interval
        re-buys. The cadence is the slot refresh's own, not a second one."""
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        budget.record(
            called_ms=NOW - REFRESH_MS + MIN, endpoint="/odds", cost=6,
            sport_key="baseball_mlb",
        )
        held = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=6, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, desk_window=self.OPEN,
        )
        assert held.fire == ()

        due = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=6, now_ms=NOW + MIN,
            max_odds_age_ms=MAX_ODDS_AGE_MS, desk_window=self.OPEN,
        )
        assert [f.trigger for f in due.fire] == [DESK]

    def test_a_due_slot_owns_its_sport(self, conn, budget):
        """Inside a slot's window the slot fires -- the desk stands aside, so
        one sport never buys twice on a pass and the opening call keeps its
        SCHEDULED trigger (props ride the opening call only)."""
        add_fixture(conn, commence_ms=NOW + 40 * MIN)
        decision = decide_sweeps(
            conn,
            in_scope={"baseball_mlb": NOW + 3 * HOUR},
            budget=budget, cost=6, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, desk_window=self.OPEN,
        )
        assert [f.trigger for f in decision.fire] == [SCHEDULED]

    def test_the_desk_stands_aside_even_when_the_slot_was_refused(
        self, conn, budget
    ):
        """The one case the stand-aside is not redundant with the
        already-firing check: a due slot refused for its prop cost. A desk
        buy here would land inside the due window, move `last_sweep` past
        `fire_from_ms`, and silently demote the opening SCHEDULED call --
        the refusal must stay a refusal, named, not be worked around."""
        add_fixture(conn, commence_ms=NOW + 40 * MIN)
        decision = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=6, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, desk_window=self.OPEN,
            prop_cost_per_event=20, prop_sports={"baseball_mlb"},
        )
        assert decision.fire == ()
        assert "cannot afford even to open" in decision.detail

    def test_a_desk_buy_does_not_demote_the_opening_call(self, conn, budget):
        """A desk buy can land no later than `fire_from_ms`, so when the slot
        opens, `firing_for_slot` still reads it as unopened: SCHEDULED, not
        REFRESH. This is the guarantee that lets the desk coexist with props
        riding the opening call."""
        kickoff = NOW + 40 * MIN
        add_fixture(conn, commence_ms=kickoff)
        fire_from = kickoff - MAX_ODDS_AGE_MS - DUE_WINDOW_MS
        budget.record(
            called_ms=fire_from - 5 * MIN, endpoint="/odds", cost=6,
            sport_key="baseball_mlb",
        )
        decision = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=6, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, desk_window=self.OPEN,
        )
        assert [f.trigger for f in decision.fire] == [SCHEDULED]

    def test_a_short_day_refuses_the_desk_buy_by_name(self, conn, budget):
        """A slot's reserved refresh tail can drain the pool below one call;
        the desk buy that loses to it is refused by name, not dropped. (With
        uniform costs the `remaining` cap binds first, so the reservation is
        the only honest way to reach this branch.)"""
        add_fixture(conn, commence_ms=NOW + 40 * MIN)
        add_fixture(
            conn, sport_key="basketball_wnba", odds_event_id="w1",
            commence_ms=NOW + 6 * HOUR,
        )
        decision = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=6, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, desk_window=self.OPEN,
        )
        assert [f.trigger for f in decision.fire] == [SCHEDULED]
        assert "basketball_wnba desk refresh cannot be served" in decision.detail

    def test_the_window_arithmetic_crosses_midnight(self):
        """16-04 is 16:00Z through 03:59Z; equal hours are no window, never
        all day -- the ambiguous spelling must not be the expensive one."""
        def at(hour):
            return ms(f"2026-08-07T{hour:02d}:30:00")

        assert desk_window_contains(at(18), start_hour=16, end_hour=4)
        assert desk_window_contains(at(2), start_hour=16, end_hour=4)
        assert not desk_window_contains(at(10), start_hour=16, end_hour=4)
        assert not desk_window_contains(at(18), start_hour=16, end_hour=16)
        # And the plain daytime window, both bounds.
        assert desk_window_contains(at(16), start_hour=16, end_hour=20)
        assert not desk_window_contains(at(20), start_hour=16, end_hour=20)

    def test_next_open_is_now_when_open_and_the_boundary_when_shut(self):
        assert next_desk_open_ms(NOW, start_hour=16, end_hour=4) == NOW
        assert next_desk_open_ms(
            NOW, start_hour=20, end_hour=4
        ) == ms("2026-08-07T20:00:00")
        # Already past today's start hour: the next opening is tomorrow's.
        assert next_desk_open_ms(
            NOW, start_hour=12, end_hour=14
        ) == ms("2026-08-08T12:00:00")

    def test_the_window_panel_predicts_the_desk_buy(self, conn, budget):
        """`next_call_ms` is the screen's "when does the next window open";
        a desk buy the loop will make must be a call the display predicts."""
        add_fixture(
            conn, commence_ms=NOW + 6 * HOUR,
            fetched_ms=NOW - HOUR, book_updated_ms=NOW - HOUR,
        )
        open_now = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=6,
            desk_window=self.OPEN,
        )
        assert open_now.next_call_ms == NOW

        shut = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=6,
            desk_window=self.CLOSED,
        )
        # **CHANGED 2026-08-25.** This asserted 20:00Z — the hour the shut
        # window reopened, which was the soonest thing the desk would do.
        # The floor is sooner: the kickoff is inside its twelve-hour horizon
        # and nothing has swept, so the desk wants this sport *now*, and the
        # panel has to say so or it would tell a human to wait four hours for a
        # buy the next pass will make.
        #
        # This is the one-predicate rule doing its job: `window_status` and
        # `decide_sweeps` both read `desk_wants`, so the panel could not have
        # kept the old answer while the loop changed its mind.
        assert shut.next_call_ms == NOW

    def test_the_desk_counts_as_a_window_of_the_day(self, conn, budget):
        """`first_window_open_ms` is the sweep banner's "nothing has swept yet
        is arithmetic, not an alarm" -- a desk day opens at the desk hour, not
        at the first kickoff-derived slot."""
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        start = day_start_ms(NOW)
        with_desk = first_window_open_of_day(
            conn, day_start_ms=start, max_odds_age_ms=MAX_ODDS_AGE_MS,
            desk_window=self.OPEN,
        )
        assert with_desk == ms("2026-08-07T16:00:00")
        without = first_window_open_of_day(
            conn, day_start_ms=start, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert without is not None and without > with_desk


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


class TestCoveredIsOneDefinition:
    """`games_covered` and `SweepSlot.covers` must be the same predicate.

    `/api/window` publishes the count as `slots_planned`; the prop fetch buys
    the set. Two implementations of "covered" would let the published number and
    the purchased set disagree, which is invisible from either side -- and it is
    the shape that produced the 2026-08-15 credit drain one level down.
    """

    def test_the_count_equals_the_predicate_over_the_same_slate(self, conn):
        anchor = NOW + 40 * MIN
        kickoffs = [
            anchor,
            anchor + 15 * MIN,
            anchor + COVERAGE_MS,             # last covered instant
            anchor + COVERAGE_MS + 1,         # first uncovered instant
            anchor + 12 * HOUR,
        ]
        slots = slots_for_sport(
            "baseball_mlb", kickoffs, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        slot = next(s for s in slots if s.anchor_commence_ms == anchor)

        counted_by_predicate = sum(1 for k in kickoffs if slot.covers(k))
        assert slot.games_covered == counted_by_predicate, (
            "the published count and the predicate disagree, so the set of "
            "fixtures bought will not be the set of fixtures reported"
        )

    def test_the_boundary_is_inclusive_on_both_ends(self, conn):
        """Named because an off-by-one here is a silently mis-sized purchase."""
        anchor = NOW + 40 * MIN
        slots = slots_for_sport(
            "baseball_mlb", [anchor], now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        slot = slots[0]
        assert slot.covers(slot.fire_until_ms)
        assert not slot.covers(slot.fire_until_ms - 1)
        assert slot.covers(anchor + COVERAGE_MS)
        assert not slot.covers(anchor + COVERAGE_MS + 1)


class TestThePlannerPricesThePropsItAuthorises:
    """The defect underneath the 2026-08-15 outage.

    `decide_sweeps` sized the whole budget day on the **team** sweep cost --
    `remaining_today // 6` -- while every scheduled firing also triggered a
    per-event prop fetch billed at ten market keys x two regions. It authorised
    a 6-credit call that spent 384.

    Restricting the prop fetch to the slot's own fixtures fixes the symptom.
    Without this reservation the next limit binds in silence: a three-hour
    coverage window on a full evening slate covers a dozen games, and
    `6 + 20x12` is 246 a firing.
    """

    def _slate(self, conn, *, anchor, n):
        for i in range(n):
            add_fixture(
                conn,
                odds_event_id=f"e{i}",
                commence_ms=anchor + i * MIN,
            )

    def test_a_sweep_whose_prop_tail_breaches_the_day_is_refused(self, conn):
        anchor = NOW + 40 * MIN
        self._slate(conn, anchor=anchor, n=12)
        budget = CreditBudget(conn, daily_budget=100)

        decision = decide_sweeps(
            conn,
            in_scope={"baseball_mlb": anchor + 3 * HOUR},
            budget=budget, cost=6, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
            prop_cost_per_event=20,
            prop_sports={"baseball_mlb"},
        )

        # 6 + 20*12 = 246 against 100 remaining.
        assert decision.fire == (), (
            "the planner authorised a sweep whose prop tail cannot be paid for"
        )
        assert "props" in decision.detail, (
            f"the refusal did not name the cost that bound: {decision.detail}"
        )

    def test_the_same_sweep_fires_when_the_day_can_afford_the_tail(self, conn):
        """The falsifier: the refusal above must be about cost, not coverage."""
        anchor = NOW + 40 * MIN
        self._slate(conn, anchor=anchor, n=12)
        budget = CreditBudget(conn, daily_budget=400)

        decision = decide_sweeps(
            conn,
            in_scope={"baseball_mlb": anchor + 3 * HOUR},
            budget=budget, cost=6, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
            prop_cost_per_event=20,
            prop_sports={"baseball_mlb"},
        )
        assert [f.sport_key for f in decision.fire] == ["baseball_mlb"]
        # Two tails now, not one: the props, and the calls that hold the window
        # open for the rest of the slot. Derived from the slot rather than
        # written as a literal -- a literal here is a second definition of
        # `calls_remaining` and would go stale the next time the window moved.
        slot = decision.fire[0].slot
        calls = slot.calls_remaining(NOW, REFRESH_MS)
        assert calls > 1, "a sixty-minute window that wants one call is not one"
        assert decision.fire[0].projected_total_cost == 6 * calls + 20 * 12

    def test_a_sport_with_no_ladder_is_not_charged_for_props(self, conn):
        """WNBA has no prop series, so reserving for one would starve it."""
        anchor = NOW + 40 * MIN
        self._slate(conn, anchor=anchor, n=12)
        budget = CreditBudget(conn, daily_budget=100)

        decision = decide_sweeps(
            conn,
            in_scope={"baseball_mlb": anchor + 3 * HOUR},
            budget=budget, cost=6, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
            prop_cost_per_event=20,
            prop_sports=set(),          # no ladder discovered anywhere
        )
        assert [f.sport_key for f in decision.fire] == ["baseball_mlb"]
        slot = decision.fire[0].slot
        assert decision.fire[0].projected_total_cost == 6 * slot.calls_remaining(
            NOW, REFRESH_MS
        ), "a sport with no ladder was charged for props it will never buy"

    def test_the_firing_carries_the_slot_it_was_planned_for(self, conn):
        """Without this the prop fetch has no fixture set and falls back to the
        whole slate, which is the defect itself."""
        anchor = NOW + 40 * MIN
        add_fixture(conn, commence_ms=anchor)
        budget = CreditBudget(conn, daily_budget=400)

        decision = decide_sweeps(
            conn,
            in_scope={"baseball_mlb": anchor + 3 * HOUR},
            budget=budget, cost=6, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        firing = decision.fire[0]
        assert firing.trigger == "scheduled"
        assert firing.slot is not None
        assert firing.slot.anchor_commence_ms == anchor

    def test_a_bootstrap_carries_no_slot(self, conn):
        """It has no cluster to aim at, which is what makes it a bootstrap."""
        budget = CreditBudget(conn, daily_budget=400)
        decision = decide_sweeps(
            conn,
            in_scope={"baseball_mlb": NOW + 2 * HOUR},
            budget=budget, cost=6, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        firing = decision.fire[0]
        assert firing.trigger == "bootstrap"
        assert firing.slot is None


class TestCostIsUnchanged:
    def test_a_sweep_still_costs_markets_times_regions(self):
        assert sweep_cost(["h2h", "spreads", "totals"], ["us", "eu"]) == 6


# A budget day, using the deployed boundary hour rather than a chosen one.
DAY_START = day_start_ms(ms("2026-08-17T18:00:00"))  # -> 2026-08-17T10:00:00Z


class TestTheFirstWindowOfTheBudgetDay:
    """`first_window_open_of_day` — the schedule fact the sweep banner needs.

    It exists because the banner was comparing `last_sweep_ms` against
    `budget_day_start_ms`, and those are different clocks: the boundary is a
    credits-accounting time, a window is kickoff-derived. Between them there is
    no window in which to spend, so "nothing has swept" was arithmetic rendered
    as a warning — on 6 of 6 live budget days sampled.
    """

    def test_it_reports_when_the_first_window_opens(self, conn):
        """A 22:05Z first pitch means a window from 20:50Z. The deployed case.

        These are the real numbers off the live box on 2026-08-17, which the
        scheduler itself wrote into `odds_sweep_log.detail` that morning.
        """
        add_fixture(conn, commence_ms=ms("2026-08-17T22:05:00"))
        assert first_window_open_of_day(
            conn, day_start_ms=DAY_START, max_odds_age_ms=MAX_ODDS_AGE_MS
        ) == ms("2026-08-17T20:50:00")

    def test_the_gap_from_the_boundary_is_not_small(self, conn):
        """The defect restated as a number, so it cannot quietly stop being true.

        Ten hours fifty minutes between the budget day opening and the first
        moment a sweep could be served. Every minute of it rendered amber.
        """
        add_fixture(conn, commence_ms=ms("2026-08-17T22:05:00"))
        opens = first_window_open_of_day(
            conn, day_start_ms=DAY_START, max_odds_age_ms=MAX_ODDS_AGE_MS
        )
        assert (opens - DAY_START) == 10 * HOUR + 50 * MIN

    def test_a_window_that_already_closed_today_still_counts(self, conn):
        """**The guard that keeps the fix from silencing the incident.**

        A cluster at 12:00Z opens its window at 10:45Z and closes it at 11:45Z.
        By 18:00Z that window is long gone — and a loop that swept nothing
        through it is exactly the 17-hour failure. Planning from `now` would
        return the *next* slot and the banner would report "no window yet",
        rendering the outage calm. Computing from the day boundary is what makes
        the past window visible.
        """
        add_fixture(conn, commence_ms=ms("2026-08-17T12:00:00"))
        assert first_window_open_of_day(
            conn, day_start_ms=DAY_START, max_odds_age_ms=MAX_ODDS_AGE_MS
        ) == ms("2026-08-17T10:45:00")

    def test_a_window_already_open_at_the_boundary_is_clamped_to_it(self, conn):
        """A 10:30Z kickoff wants a window from 09:15Z, before the day existed.

        Reporting 09:15Z would put a time on the screen belonging to yesterday's
        budget day. For this question the window opens when the day does.
        """
        add_fixture(conn, commence_ms=ms("2026-08-17T10:30:00"))
        assert first_window_open_of_day(
            conn, day_start_ms=DAY_START, max_odds_age_ms=MAX_ODDS_AGE_MS
        ) == DAY_START

    def test_it_takes_the_earliest_window_across_sports(self, conn):
        add_fixture(
            conn,
            sport_key="baseball_mlb",
            odds_event_id="mlb1",
            commence_ms=ms("2026-08-17T22:05:00"),
        )
        add_fixture(
            conn,
            sport_key="basketball_wnba",
            odds_event_id="wnba1",
            commence_ms=ms("2026-08-17T19:00:00"),
        )
        assert first_window_open_of_day(
            conn, day_start_ms=DAY_START, max_odds_age_ms=MAX_ODDS_AGE_MS
        ) == ms("2026-08-17T17:45:00")

    def test_a_slate_that_starts_tomorrow_opens_no_window_today(self, conn):
        """`None`, and the banner reads it as "nothing is owed today".

        Not as "unknown" and not as reassurance: a loop that is not running at
        all is `last_look_ms` going stale, a different field and a louder tone.
        """
        add_fixture(conn, commence_ms=ms("2026-08-18T22:05:00"))
        assert (
            first_window_open_of_day(
                conn, day_start_ms=DAY_START, max_odds_age_ms=MAX_ODDS_AGE_MS
            )
            is None
        )

    def test_an_empty_record_opens_no_window(self, conn):
        assert (
            first_window_open_of_day(
                conn, day_start_ms=DAY_START, max_odds_age_ms=MAX_ODDS_AGE_MS
            )
            is None
        )

    def test_it_is_on_the_window_payload(self, conn, budget):
        """The field has to reach the screen, not just exist.

        `backend/agents/` and four other modules in this repo were complete,
        tested and invoked by nothing; a computed value that never reaches
        `to_dict` is the same defect one layer down.
        """
        add_fixture(conn, commence_ms=ms("2026-08-17T22:05:00"))
        payload = window_status(
            conn,
            budget=budget,
            now_ms=ms("2026-08-17T18:00:00"),
            max_odds_age_ms=MAX_ODDS_AGE_MS,
            sweep_cost=6,
        ).to_dict()
        assert payload["first_window_open_ms"] == ms("2026-08-17T20:50:00")

    def test_the_boundary_and_the_window_are_different_numbers(self, conn, budget):
        """The whole premise, asserted rather than assumed.

        If these two ever coincide by construction the banner's old predicate
        would be correct again and this field would be dead weight. They do not:
        one is an accounting hour, the other is derived from a kickoff.
        """
        add_fixture(conn, commence_ms=ms("2026-08-17T22:05:00"))
        payload = window_status(
            conn,
            budget=budget,
            now_ms=ms("2026-08-17T18:00:00"),
            max_odds_age_ms=MAX_ODDS_AGE_MS,
            sweep_cost=6,
        ).to_dict()
        assert (
            payload["first_window_open_ms"] != payload["budget_day_start_ms"]
        )
