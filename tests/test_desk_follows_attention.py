"""The odds feed follows attention over an hourly floor. ADR 0071 section 2.6.

WHY THIS EXISTS
---------------
`ODDS_DESK_WINDOW_UTC` bought a sweep every ten minutes for twelve hours a day
whether or not anyone had the site open. At the deployed `h2h,spreads` that is
**576 credits/day at two sports, ~17,300/month** against an 18,000 self-cap --
and at four sports, which NCAAF and NFL make imminent, **1,152/day and ~34,600
a month, past the whole 20,000 tier**. `fly.live.toml` recorded that as a
decision deferred to the day those sports landed.

Joe chose attention over a narrower fixed window and over a manual wake button,
and chose the two parameters here: a hard cap on attention-triggered credits,
and an idle floor of hourly for sports with a fixture inside twelve hours.

THE FAILURE THIS IS WRITTEN AGAINST
-----------------------------------
Not staleness. If attention reads absent while someone is looking, the slate is
stale for up to an hour and a person taps refresh. If it reads *present* while
nobody is, the feed buys at the ten-minute cadence around the clock -- the
2,304/day worst case. Every ceiling below exists for that direction, and the
tests are weighted to it.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **Nothing about the saving.** Every "attended hours" figure in the design is
  a guess about how long the page is actually open. `api_credits` summed per
  budget-day by trigger is the instrument; this suite proves the mechanism, not
  the arithmetic that motivated it.
- **Nothing about a browser.** Whether `Nav.tsx` actually stops stamping in a
  background tab is a browser behaviour, not decidable from Python.
  `test_desk_heartbeat_is_visibility_gated.py` reads the source; only a real
  browser proves it.
- **Nothing about the slot planner**, which still owns the pre-game window and
  is still the only trigger that buys props.
- **Nothing about whether fresher odds are better odds.** The desk re-prices a
  comparison; it cannot change what the comparison says.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.odds import attention
from backend.odds.budget import CreditBudget
from backend.odds.timing import (
    ATTENTION,
    DEFAULT_ATTENTION_DAILY_CREDITS,
    DESK,
    DESK_FLOOR_HORIZON_MS,
    DESK_FLOOR_INTERVAL_MS,
    attention_credits_spent_today,
    decide_sweeps,
    desk_floor_next_want_ms,
    desk_wants,
    window_status,
)
from backend.scheduler import JITTER, Tempo, sleep_until
from backend.store import db

MIN = 60_000
HOUR = 3_600_000
NOW = 1_787_680_800_000  # 2026-08-25T18:00:00Z
MAX_ODDS_AGE_MS = 900_000
REFRESH_MS = 600_000
SPORT = "baseball_mlb"


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "desk.db")
    yield c
    c.close()


@pytest.fixture
def budget(conn):
    return CreditBudget(conn, daily_budget=700)


def add_fixture(conn, *, commence_ms, sport_key=SPORT, odds_event_id="evt"):
    """One stored sportsbook fixture. Same shape as `test_sweep_timing.py`'s
    helper -- `odds_snapshots` rows are what `upcoming_fixtures_by_sport`
    reads, and there is no separate fixtures table."""
    for book in ("pinnacle", "draftkings"):
        for outcome in ("Home", "Away"):
            conn.execute(
                "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, "
                "sport_key, odds_event_id, commence_ms, home_team, away_team, "
                "bookmaker, market, outcome_name, price_decimal) "
                "VALUES (?, ?, ?, ?, ?, 'Home', 'Away', ?, 'h2h', ?, 2.0)",
                (
                    NOW - HOUR, NOW - HOUR, sport_key, odds_event_id,
                    commence_ms, book, outcome,
                ),
            )
    conn.commit()


#: Far enough back that the spend does not also *pace* the sport.
#:
#: These are real `/odds` rows, so they satisfy `_SERVED_SWEEP` and land in
#: `last_sweep_by_sport`. Written at `NOW` they made the sport freshly swept and
#: the desk held the credit for that reason instead of the slice -- every
#: assertion would then pass or fail for the wrong cause. Three hours is past
#: both cadences (ten minutes attended, one hour on the floor).
SPENT_AT = NOW - 3 * HOUR


def spend_the_slice(conn, *, credits, at_ms=SPENT_AT):
    """Fill the attention slice with `credits` worth of `trigger='attention'`."""
    for i in range(credits // 4):
        conn.execute(
            "INSERT INTO api_credits (called_ms, endpoint, sport_key, "
            "cost, trigger) VALUES (?, ?, ?, ?, ?)",
            (at_ms - i * MIN, f"/sports/{SPORT}/odds", SPORT, 4, ATTENTION),
        )
    conn.commit()


class TestTheCadenceDependsOnWhetherAnyoneIsLooking:
    """`desk_wants` as a pure function -- the whole trigger, stated in
    arguments."""

    SOON = {SPORT: [NOW + 6 * HOUR]}

    def test_attended_gets_the_refresh_cadence(self):
        wants = desk_wants(
            self.SOON, now_ms=NOW, attended=True,
            last_sweeps={SPORT: NOW - 5 * MIN}, refresh_interval_ms=REFRESH_MS,
        )
        assert wants == {SPORT: NOW - 5 * MIN + REFRESH_MS}

    def test_unattended_gets_the_hourly_floor(self):
        """The saving, in one assertion: the same sport, the same instant, the
        same last sweep — six times less often because nobody is looking."""
        wants = desk_wants(
            self.SOON, now_ms=NOW, attended=False,
            last_sweeps={SPORT: NOW - 5 * MIN}, refresh_interval_ms=REFRESH_MS,
        )
        assert wants == {SPORT: NOW - 5 * MIN + DESK_FLOOR_INTERVAL_MS}

    def test_a_configured_clock_window_still_counts_as_open(self):
        """`desk_window` is retained rather than deleted, so an operator can pin
        a window back on without a code change. Unset — which is what
        `fly.live.toml` now does — it contributes nothing."""
        wants = desk_wants(
            self.SOON, now_ms=NOW, attended=False,
            last_sweeps={SPORT: NOW - 5 * MIN}, refresh_interval_ms=REFRESH_MS,
            desk_window=(16, 4),  # NOW is 18:00Z, inside it
        )
        assert wants == {SPORT: NOW - 5 * MIN + REFRESH_MS}

    def test_a_sport_beyond_the_floor_horizon_is_absent_not_scheduled(self):
        """Absent, never a far-future timestamp.

        `window_status` takes `min()` of these values to tell a human when the
        feed will next look. A sentinel would silently win or lose that `min()`
        depending which sentinel was picked, and both are wrong in a way nothing
        would report.
        """
        far = {SPORT: [NOW + DESK_FLOOR_HORIZON_MS + MIN]}
        assert desk_wants(
            far, now_ms=NOW, attended=False, last_sweeps={},
            refresh_interval_ms=REFRESH_MS,
        ) == {}

    def test_attention_overrides_the_horizon(self):
        """Someone looking at a slate wants it priced, and the tool does not get
        to decide their fixture is too far away to be interesting."""
        far = {SPORT: [NOW + DESK_FLOOR_HORIZON_MS + MIN]}
        assert desk_wants(
            far, now_ms=NOW, attended=True, last_sweeps={},
            refresh_interval_ms=REFRESH_MS,
        ) == {SPORT: NOW}

    def test_an_unswept_sport_is_wanted_now(self):
        assert desk_wants(
            self.SOON, now_ms=NOW, attended=False, last_sweeps={},
            refresh_interval_ms=REFRESH_MS,
        ) == {SPORT: NOW}

    def test_an_unswept_sport_is_refused_on_the_quote_cadence(self):
        """The hazard `allow_bootstrap` is written against, reached by a new
        route.

        The cadence is measured from the last *served* sweep, so a sport with
        none has nothing pacing it and every pass wants it — once per 15s pass
        until the budget is gone. Slice 1 of this lane widened that: a *failing*
        sport no longer moves `last_sweeps` either, so a 401 would retry every
        15s rather than every ten minutes.

        Mutation observed red: drop the `allow_bootstrap` guard in `desk_wants`.
        """
        assert desk_wants(
            self.SOON, now_ms=NOW, attended=True, last_sweeps={},
            refresh_interval_ms=REFRESH_MS, allow_bootstrap=False,
        ) == {}

    def test_a_paced_sport_still_re_buys_on_the_quote_cadence(self):
        """The guard above must not turn the fast cadence off. A sport with a
        served sweep is paced by it, which is the property that made the rolling
        refresh safe to put on the 15s pass in the first place."""
        assert desk_wants(
            self.SOON, now_ms=NOW, attended=True,
            last_sweeps={SPORT: NOW - HOUR}, refresh_interval_ms=REFRESH_MS,
            allow_bootstrap=False,
        ) == {SPORT: NOW}


class TestTheTriggerFires:
    def test_an_attended_desk_buys_at_the_refresh_cadence(self, conn, budget):
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        attention.stamp(conn, now_ms=NOW)
        decision = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=4, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert [f.trigger for f in decision.fire] == [ATTENTION]
        assert "someone has the desk open" in decision.fire[0].detail

    def test_an_unattended_desk_buys_on_the_floor(self, conn, budget):
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        decision = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=4, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert [f.trigger for f in decision.fire] == [DESK]
        assert "hourly floor" in decision.fire[0].detail

    def test_a_stale_stamp_does_not_hold_the_desk_open(self, conn, budget):
        """The tail, bounded. Someone who closed the tab an hour ago is not
        looking, and the desk must not keep paying the attended cadence for
        them."""
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        attention.stamp(conn, now_ms=NOW - HOUR)
        decision = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=4, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert [f.trigger for f in decision.fire] == [DESK]


class TestTheAttentionSliceIsAHardCeiling:
    """Joe's answer, 2026-08-25: cap attention-triggered credits.

    The `visibilityState` check in `Nav.tsx` is the brace; this is the belt. A
    guard that a browser bug can defeat must never be the only thing between a
    design and its worst case.
    """

    # `SPENT_AT` and the filling of the slice moved to module scope on
    # 2026-08-28, unchanged: `window_status` needs the same setup, and a second
    # copy of it is how the two drift apart.

    def _spend_the_slice(self, conn, *, credits):
        spend_the_slice(conn, credits=credits)

    def test_the_counter_reads_only_attention_rows(self, conn):
        """Floor buys stamp `trigger` NULL like every planner firing, so they
        are not in the slice and must not be counted into it."""
        self._spend_the_slice(conn, credits=40)
        conn.execute(
            "INSERT INTO api_credits (called_ms, endpoint, sport_key, cost) "
            "VALUES (?, ?, ?, ?)",
            (NOW, f"/sports/{SPORT}/odds", SPORT, 4),
        )
        conn.commit()
        assert attention_credits_spent_today(conn, since_ms=NOW - 6 * HOUR) == 40

    def test_past_the_slice_the_attended_cadence_is_refused_by_name(
        self, conn, budget
    ):
        """Mutation observed red: remove the `attention_spent + cost >` guard —
        a tab left open buys all day at the ten-minute cadence."""
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        attention.stamp(conn, now_ms=NOW)
        self._spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        decision = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=4, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert decision.fire == ()
        assert "attention slice" in decision.detail

    def test_the_floor_is_not_charged_to_the_slice(self, conn, budget):
        """**This is what makes the cap safe to set low.** Past the slice the
        slate stops re-buying every ten minutes and keeps buying every hour, so
        it never goes fully dark — which is the difference between a ceiling and
        an off switch.

        Mutation observed red: charge floor buys to the slice too — a day that
        exhausts the slice then goes dark until the budget day rolls over.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        self._spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        # No stamp: nobody is looking, so this is the floor's buy.
        decision = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=4, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert [f.trigger for f in decision.fire] == [DESK]

    def test_the_refusal_says_the_floor_still_runs(self, conn, budget):
        """A refusal that reads as "the feed is off" would send someone to raise
        the cap. Naming what survives is what makes the ceiling legible."""
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        attention.stamp(conn, now_ms=NOW)
        self._spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        decision = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=4, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert "hourly floor still runs" in decision.detail


class TestTheScreenPredictsWhatTheLoopWillDo:
    """One predicate, two callers. The panel tells a human when to look."""

    def test_the_panel_predicts_the_attended_cadence(self, conn, budget):
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        attention.stamp(conn, now_ms=NOW)
        status = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=4,
        )
        assert status.next_call_ms == NOW

    def test_the_panel_predicts_the_floor(self, conn, budget):
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        conn.execute(
            "INSERT INTO api_credits (called_ms, endpoint, sport_key, cost) "
            "VALUES (?, ?, ?, ?)",
            (NOW - 10 * MIN, f"/sports/{SPORT}/odds", SPORT, 4),
        )
        conn.commit()
        status = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=4,
        )
        assert status.next_call_ms == NOW - 10 * MIN + DESK_FLOOR_INTERVAL_MS

    def test_the_desk_adds_nothing_when_it_wants_nothing(self, conn, budget):
        """A real state now, where a clock window always had a next hour: no
        sport is playing inside the floor's horizon and nobody is looking.

        `next_call_ms` is not `None` here and asserting that it was would have
        been wrong -- it merges the desk's answer with the *slot* planner's, and
        a fixture thirteen hours out still has a pre-game slot. What the desk
        must not do is pull that time earlier by inventing a buy it will not
        make. So the assertion is that the merged answer is exactly the slot's,
        which is the only way to say "the desk contributed nothing" without
        reaching inside the function.
        """
        add_fixture(conn, commence_ms=NOW + DESK_FLOOR_HORIZON_MS + HOUR)
        status = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=4,
        )
        assert status.next_slot is not None
        assert status.next_call_ms == status.next_slot.fire_from_ms


class TestTheLoopActsOnAHeartbeatWithoutWaitingForItsSleep:
    """§2.6 told the FEED to follow attention. The LOOP was still on a clock.

    `decide_sweeps` asks `is_attended` on every pass and always did the right
    thing with the answer. But the cadence is chosen from what the *previous*
    pass observed, and with the window shut that is `slow_interval_s` -- so with
    nobody looking the loop went to sleep for 900s, and a heartbeat arriving one
    second later could not be acted on for another fourteen minutes.

    Measured on live 2026-08-25: a pass ended 16:49:33Z with the window shut,
    Joe opened the desk at ~16:58Z, and the loop fired
    `baseball_mlb (attention)` at 17:05:08Z -- the first second after the sleep
    ended, 934s later, which is 900s plus jitter. It was never stuck; it was
    asleep, and nothing could wake it.

    The pins are static because `run_loop.main()` has no caller but `__main__`
    (see `test_run_loop_attributes_resolve.py` for why that is the shape here).
    The behaviour itself is proved in `test_scheduler.py` and
    `test_desk_attention.py`; these check the two halves are joined.
    """

    def _source(self) -> str:
        return (
            Path(__file__).resolve().parents[1] / "scripts" / "run_loop.py"
        ).read_text(encoding="utf-8")

    def test_the_loop_hands_run_forever_a_wake_predicate(self):
        """Mutation observed red: drop `wake_when=wake_early` from the
        `run_forever` call and the loop is back on the clock with every other
        test still green."""
        source = self._source()
        assert "wake_when=wake_early" in source
        assert "def wake_early()" in source

    def test_the_predicate_watches_arrivals_not_attendance(self):
        """`is_attended` is true for the whole TTL, so a sleeping loop asking
        it would wake on every check for five minutes and then stop -- which is
        neither the cadence wanted nor a signal. Mutation observed red: swap
        `ArrivalWatch` for `is_attended` and the consuming tests in
        `test_desk_attention.py` no longer describe what the loop does."""
        block = self._source().split("def wake_early()", 1)[1].split(
            "\n    def ", 1
        )[0]
        assert "arrivals.arrived()" in block
        assert "is_attended" not in block

    def test_the_predicate_also_covers_a_tap(self):
        """`run_quote_pass` promises a tap is served within "at most one tick".
        That was true of the 15s cadence and false of the 900s one -- and a shut
        window is exactly when someone presses refresh."""
        block = self._source().split("def wake_early()", 1)[1].split(
            "\n    def ", 1
        )[0]
        assert "ondemand.take" in block


class TestTheWholeWakePathOverARealDatabase:
    """The two halves joined, because the source pins cannot prove they fit.

    `test_scheduler.py` proves `sleep_until` ends early when a predicate says
    so; `test_desk_attention.py` proves `ArrivalWatch` reports an arrival once.
    Neither proves the loop wakes when the API stamps the table -- which is the
    whole claim, and the half that was missing on 2026-08-25.

    A fake clock, a real `sqlite3` connection, and the same composition
    `run_loop.wake_early` builds.
    """

    async def test_a_stamp_landing_mid_sleep_cuts_it_short(self, tmp_path):
        conn = db.init_db(tmp_path / "wake.db")
        try:
            watch = attention.ArrivalWatch(conn)
            slept = []

            async def sleep(seconds):
                slept.append(seconds)
                # The API process, stamping while the loop is under. Landing on
                # the third chunk rather than the first is what distinguishes
                # "woke because a heartbeat arrived" from "woke regardless".
                if len(slept) == 3:
                    attention.stamp(conn, now_ms=NOW)

            woke = await sleep_until(
                900.0, wake_when=watch.arrived, sleep=sleep, poll_s=5.0
            )
            assert woke is True
            assert len(slept) == 3, "woke on the chunk after the stamp landed"
            assert sum(slept) == 15.0, "15s, not the 900s the desk sat blank"
        finally:
            conn.close()

    async def test_no_stamp_means_the_full_slow_interval(self, tmp_path):
        """The other half of the claim: a quiet desk is not woken, so this
        cannot be a shorter cadence wearing a heartbeat's clothes."""
        conn = db.init_db(tmp_path / "quiet.db")
        try:
            watch = attention.ArrivalWatch(conn)
            slept = []

            async def sleep(seconds):
                slept.append(seconds)

            woke = await sleep_until(
                900.0, wake_when=watch.arrived, sleep=sleep, poll_s=5.0
            )
            assert woke is False
            assert sum(slept) == pytest.approx(900.0)
        finally:
            conn.close()


class TestThePanelDoesNotPublishASweepTheLoopHasRefused:
    """Ticket #35, and the defect is a mismatch of questions rather than a bug.

    `window_status` applied `desk_wants` and stopped; `decide_sweeps` applies
    the attention slice **after** `desk_wants` has said a call is wanted. So
    `next_call_ms` answered *"is a call wanted?"* and the screen rendered it as
    *"is a call coming?"* -- two questions that agree on every night the slice
    has credits and diverge on the nights it does not.

    Joe read `The next scheduled sweep is now` on 2026-08-28 at 04:38Z while
    the loop, at 04:38:25Z and again at 04:38:42Z, logged `desk refresh cannot
    be served: the attention slice is 300 credits a day and 300 are spent`.
    Same box, same minute, opposite answers, on the one readout a person uses
    to decide whether to wait.

    **What these do not establish:** nothing about whether 300/day is the right
    ceiling -- a budget decision with its own ticket -- and nothing about what
    the panel *says* in each state. These pin the facts it renders from.
    """

    def test_a_spent_slice_takes_the_desk_out_of_the_next_call(
        self, conn, budget
    ):
        """Mutation observed red: drop the `slice_spent and not on_the_floor`
        branch in `window_status` so `desk_wants` always speaks --
        `next_desk_buy_ms` comes back as `NOW` and `next_call_ms` with it,
        which is the published contradiction restored exactly.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        attention.stamp(conn, now_ms=NOW)
        spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        status = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=4,
        )
        assert status.attention_slice_spent is True
        assert status.desk_is_attended is True
        assert status.next_desk_buy_ms is None
        # The slot planner is untouched by the slice and still owns its own
        # window, so the merged answer is exactly the slot's -- the only way to
        # say "the desk contributed nothing" without reaching inside.
        assert status.next_slot is not None
        assert status.next_call_ms == status.next_slot.fire_from_ms

    def test_the_screen_and_the_loop_give_the_same_answer_either_way(
        self, conn, budget
    ):
        """The invariant the ticket is about, asserted against the loop itself
        rather than against a remembered value.

        Mutation observed red: same branch removed -- the spent half then has
        `decide_sweeps` firing nothing while `window_status` publishes `NOW`.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        attention.stamp(conn, now_ms=NOW)

        def desk_firings():
            decision = decide_sweeps(
                conn, in_scope={}, budget=budget, cost=4, now_ms=NOW,
                max_odds_age_ms=MAX_ODDS_AGE_MS,
            )
            return [f for f in decision.fire if f.trigger in (ATTENTION, DESK)]

        def panel():
            return window_status(
                conn, budget=budget, now_ms=NOW,
                max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=4,
            )

        # With credits: the loop buys now and the panel says so.
        assert [f.trigger for f in desk_firings()] == [ATTENTION]
        assert panel().next_desk_buy_ms == NOW

        # Past the slice: the loop refuses and the panel must stop promising.
        spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        assert desk_firings() == []
        assert panel().next_desk_buy_ms is None

    def test_the_slice_is_not_applied_where_the_loop_does_not_apply_it(
        self, conn, budget
    ):
        """`on_the_floor` sweeps are neither charged to the slice nor refused by
        it, and a panel that refused them would go dark most of a budget day
        early.

        Mutation observed red: drop `and not on_the_floor` from the
        `window_status` condition -- an idle desk with a spent slice reports no
        desk buy at all while `decide_sweeps` fires one.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        conn.execute(
            "INSERT INTO api_credits (called_ms, endpoint, sport_key, cost) "
            "VALUES (?, ?, ?, ?)",
            (NOW - 10 * MIN, f"/sports/{SPORT}/odds", SPORT, 4),
        )
        conn.commit()
        spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        # No stamp: nobody is looking, so this pass is on the floor.
        status = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=4,
        )
        assert status.attention_slice_spent is True
        assert status.desk_is_attended is False
        assert status.next_desk_buy_ms == (
            NOW - 10 * MIN + DESK_FLOOR_INTERVAL_MS
        )

    def test_the_floor_lookahead_says_when_the_slate_re_prices(
        self, conn, budget
    ):
        """**The most valuable line this lane produces**, and `desk_wants`
        cannot produce it. At 04:38Z the next kickoff was ~13.7h out, so the
        floor's horizon had not reached it and the desk wanted nothing *at that
        instant* -- while the honest sentence was "nothing re-prices these
        until about 06:20Z, when the first game comes inside twelve hours".

        Mutation observed red: compute the field from
        `desk_wants(attended=False)` instead of the lookahead -- the sport is
        outside the horizon, the map comes back empty, and the field goes
        `None`, which on the screen is "nothing re-prices these, ever".
        """
        kickoff = NOW + DESK_FLOOR_HORIZON_MS + HOUR
        add_fixture(conn, commence_ms=kickoff)
        attention.stamp(conn, now_ms=NOW)
        spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        status = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=4,
        )
        assert status.next_desk_buy_ms is None
        assert status.floor_next_buy_ms == kickoff - DESK_FLOOR_HORIZON_MS
        # Genuinely later than now, not a rounded-down "due now".
        assert status.floor_next_buy_ms > NOW

    def test_no_floor_at_all_is_a_different_answer_from_a_floor_later(
        self, conn, budget
    ):
        """Two `None`s that mean opposite things, which is why the fields are
        two. With no stored fixture the floor has nothing to come round to; the
        test above has a floor an hour and a bit away. A panel that could not
        tell them apart would write "nothing re-prices these" on both.

        Mutation observed red: default `floor_next` to `now_ms` instead of
        `None` -- the empty database then reports a floor buy due now.
        """
        attention.stamp(conn, now_ms=NOW)
        spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        status = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=4,
        )
        assert status.fixtures_upcoming == 0
        assert status.floor_next_buy_ms is None
        assert status.next_desk_buy_ms is None

    def test_the_floor_lookahead_agrees_with_desk_wants_today(self):
        """One predicate, two callers, across a lookahead: for a sport already
        inside the horizon the two must give the same instant, or the panel and
        the loop are back to disagreeing by a different route.

        Mutation observed red: drop the `max(now_ms, ...)` clamp on
        `eligible_ms` -- an unswept sport then reports the moment it entered the
        horizon, six hours in the past, instead of `now`.
        """
        fixtures = {SPORT: [NOW + 6 * HOUR]}
        paced = {SPORT: NOW - 10 * MIN}
        assert desk_floor_next_want_ms(
            fixtures, now_ms=NOW, last_sweeps=paced
        ) == desk_wants(
            fixtures, now_ms=NOW, attended=False, last_sweeps=paced,
            refresh_interval_ms=REFRESH_MS,
        )[SPORT]
        assert desk_floor_next_want_ms(
            fixtures, now_ms=NOW, last_sweeps={}
        ) == desk_wants(
            fixtures, now_ms=NOW, attended=False, last_sweeps={},
            refresh_interval_ms=REFRESH_MS,
        )[SPORT] == NOW

    def test_the_state_reaches_the_wire(self, conn, budget):
        """`to_dict` is the whole of what the panel can render from. A field on
        the dataclass that never serialises is a fix nobody can see.

        Mutation observed red: delete any one of the six keys from `to_dict` --
        this fails, and `test_demo_fidelity` fails alongside it if the
        TypeScript type is not updated with it.
        """
        kickoff = NOW + DESK_FLOOR_HORIZON_MS + HOUR
        add_fixture(conn, commence_ms=kickoff)
        attention.stamp(conn, now_ms=NOW)
        spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        payload = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=4,
        ).to_dict()
        assert payload["attention_credits_spent"] == (
            DEFAULT_ATTENTION_DAILY_CREDITS
        )
        assert payload["attention_daily_credits"] == (
            DEFAULT_ATTENTION_DAILY_CREDITS
        )
        assert payload["attention_slice_spent"] is True
        assert payload["desk_is_attended"] is True
        assert payload["next_desk_buy_ms"] is None
        assert payload["floor_next_buy_ms"] == kickoff - DESK_FLOOR_HORIZON_MS

    def test_the_ceiling_is_the_callers_and_not_a_constant(self, conn, budget):
        """`attention_daily_credits` is config (`OddsConfig`), threaded the way
        `desk_window` is. A `window_status` reading the module constant while
        the loop read `.env` would be the same defect one layer down.

        Mutation observed red: ignore the parameter and use
        `DEFAULT_ATTENTION_DAILY_CREDITS` -- 40 credits of spend is then well
        inside the 300 default and the desk is reported as buying now.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        attention.stamp(conn, now_ms=NOW)
        spend_the_slice(conn, credits=40)
        status = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=4,
            attention_daily_credits=40,
        )
        assert status.attention_daily_credits == 40
        assert status.attention_slice_spent is True
        assert status.next_desk_buy_ms is None


class TestTheLoopsCadenceIsUnchangedByTheSliceCheck:
    """`tempo.next_wake_ms = window.next_call_ms`, so this field paces the loop.

    The change is only safe if the sleep is unchanged, and that claim was
    pattern-matched off `scheduler.py` rather than run. These run it. Each case
    builds `Tempo` with the `next_call_ms` the state above produces,
    `window_open=False` because the odds are stale in every one of them, and a
    fixed clock.

    **The neutrality is real and it is conditional**, which is the part to
    carry away -- see the last test for the boundary.
    """

    SLOW = 900.0

    def _sleep_for(self, status):
        return Tempo(
            slow_interval_s=self.SLOW,
            next_wake_ms=status.next_call_ms,
            clock=lambda: NOW,
        ).interval_s()

    def test_with_credits_the_sleep_is_the_slow_interval(self, conn, budget):
        """The unchanged path: a desk buy is due now, `next_call_ms` is `NOW`,
        and `interval_s` takes the already-due branch.

        Mutation observed red: return `until_s` rather than `slow_interval_s`
        from that branch -- the sleep collapses to 0.0 and the loop spins.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        attention.stamp(conn, now_ms=NOW)
        status = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=4,
        )
        assert status.next_call_ms == NOW
        assert self._sleep_for(status) == pytest.approx(self.SLOW)

    def test_a_spent_slice_with_a_floor_later_keeps_the_slow_interval(
        self, conn, budget
    ):
        """The 04:38Z state. The desk drops out, the slot planner's own time is
        hours away, and `min(slow, until/(1 + JITTER))` returns the slow
        interval.

        Two mutations observed red, and the pair is the point: remove the slice
        branch from `window_status` (the pre-fix code) and `next_call_ms` is
        `NOW`, so the third assertion fails; compute `floor_next_buy_ms` from
        `desk_wants(attended=False)` and the first fails, because the sport is
        outside the horizon and there is no floor time to have.

        Deliberately **not** claimed: that publishing the floor into
        `next_call_ms` would be caught here. It would not -- the floor is an
        hour out in this fixture, still past the boundary, so the sleep would
        be 900s either way. `test_a_spent_slice_takes_the_desk_out_of_the_next
        _call` is what catches that, at a six-hour kickoff where the floor
        wants a buy now.
        """
        kickoff = NOW + DESK_FLOOR_HORIZON_MS + HOUR
        add_fixture(conn, commence_ms=kickoff)
        attention.stamp(conn, now_ms=NOW)
        spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        status = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=4,
        )
        assert status.floor_next_buy_ms is not None, "a floor time exists"
        assert status.next_call_ms is not None
        assert status.next_call_ms - NOW > self.SLOW * (1 + JITTER) * 1000
        assert self._sleep_for(status) == pytest.approx(self.SLOW)

    def test_a_spent_slice_with_nothing_due_keeps_the_slow_interval(
        self, conn, budget
    ):
        """Nothing stored, nothing planned: `next_call_ms` is `None` and
        `interval_s` falls to `slow_interval_s`.

        Mutation observed red: return `fast_interval_s` for a `None`
        `next_wake_ms` -- 15s against a shut window, which is the
        4,300-polls-a-day failure that branch exists to prevent.
        """
        attention.stamp(conn, now_ms=NOW)
        spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        status = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=4,
        )
        assert status.next_call_ms is None
        assert self._sleep_for(status) == pytest.approx(self.SLOW)

    def test_the_neutrality_holds_only_beyond_the_jitter_boundary(self):
        """**Say the boundary out loud rather than let the three cases above
        imply there is not one.**

        `interval_s` returns `min(slow, until_s / (1 + JITTER))`, so a *future*
        `next_call_ms` leaves the slow interval alone only once it is more than
        `slow * (1 + JITTER)` away -- 1,035s at the deployed 900s. Inside that
        the loop wakes early, which is what the bound is for and not a
        regression; it does mean "this change is cadence-neutral" is a claim
        about the states above, not about the field in general.

        Mutation observed red: drop the `(1 + JITTER)` divisor -- the second
        assertion then reads 600.0 instead of 521.7.
        """
        def sleep_with(next_wake_ms):
            return Tempo(
                slow_interval_s=self.SLOW,
                next_wake_ms=next_wake_ms,
                clock=lambda: NOW,
            ).interval_s()

        assert sleep_with(NOW + 1_100_000) == pytest.approx(self.SLOW)
        inside = sleep_with(NOW + 600_000)
        assert inside == pytest.approx(600.0 / (1 + JITTER))
        assert inside < self.SLOW
