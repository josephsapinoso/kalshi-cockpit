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
    desk_wants,
    window_status,
)
from backend.scheduler import sleep_until
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

    #: Far enough back that the spend does not also *pace* the sport.
    #:
    #: These are real `/odds` rows, so they satisfy `_SERVED_SWEEP` and land in
    #: `last_sweep_by_sport`. Written at `NOW` they made the sport freshly swept
    #: and the desk held the credit for that reason instead of the slice --
    #: every assertion below passed or failed for the wrong cause. Three hours
    #: is past both cadences (ten minutes attended, one hour on the floor).
    SPENT_AT = NOW - 3 * HOUR

    def _spend_the_slice(self, conn, *, credits):
        for i in range(credits // 4):
            conn.execute(
                "INSERT INTO api_credits (called_ms, endpoint, sport_key, "
                "cost, trigger) VALUES (?, ?, ?, ?, ?)",
                (
                    self.SPENT_AT - i * MIN,
                    f"/sports/{SPORT}/odds",
                    SPORT,
                    4,
                    ATTENTION,
                ),
            )
        conn.commit()

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
