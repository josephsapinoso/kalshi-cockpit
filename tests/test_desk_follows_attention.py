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

from backend.odds import attention, ondemand
from backend.odds.budget import CreditBudget
from backend.odds.timing import (
    ATTENTION,
    DEFAULT_ATTENTION_DAILY_CREDITS,
    DESK,
    DESK_FLOOR_HORIZON_MS,
    DESK_FLOOR_INTERVAL_MS,
    _DAY_MS,
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


def pace_the_sport(conn, *, at_ms, sport_key=SPORT):
    """One served sweep with `trigger` NULL -- a floor or planner buy.

    **What separates the two cadences in a test, and the reason several of
    these fixtures have one.** Both cadences are measured from
    `last_sweep_by_sport`, so a sport with no served sweep at all is wanted
    *now* by either of them (`desk_wants`' bootstrap branch) and an assertion
    written over that state cannot tell ten minutes from an hour. A sweep ten
    minutes back is inside the floor's hour and exactly on the attended
    cadence, which is the one arrangement where the two answers differ.

    NULL `trigger` on purpose: `attention_credits_spent_today` filters on
    `'attention'`, so this paces the sport without also moving the slice.
    """
    conn.execute(
        "INSERT INTO api_credits (called_ms, endpoint, sport_key, cost) "
        "VALUES (?, ?, ?, ?)",
        (at_ms, f"/sports/{sport_key}/odds", sport_key, 4),
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
        a tab left open buys all day at the ten-minute cadence.

        `pace_the_sport` at ten minutes is what makes that mutation visible
        since the fall-through landed (2026-08-29): the sport is exactly due on
        the attended cadence and fifty minutes early on the floor's, so a
        working slice fires nothing and a defeated one fires immediately.
        Without it both cadences want the sport now and the assertion cannot
        tell them apart.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        attention.stamp(conn, now_ms=NOW)
        pace_the_sport(conn, at_ms=NOW - 10 * MIN)
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

    def test_the_refusal_names_a_floor_that_is_already_running(
        self, conn, budget
    ):
        """A refusal that reads as "the feed is off" would send someone to
        raise the cap, so naming what survives is what makes the ceiling
        legible. **This sentence has now been wrong in both directions, which
        is why it is asserted by its own words twice over.**

        It said *"the hourly floor still runs"* while the floor was displaced
        by the very attention that caused the refusal. That was corrected on
        the morning of 2026-08-29 to *"resumes once nobody is looking"* -- a
        condition that had to lift -- and the fall-through landed the same day
        and refuted that too: nothing has to lift, the floor runs while the
        page is open.

        `detail` is not a log line only. It reaches `/api/window` as
        `last_look_detail` and `WindowBanner` prints it verbatim on `/board`,
        so a stale reassurance here is a sentence on a screen someone is
        deciding a bet from.

        The second half is what makes this a claim about the world rather than
        about a string: the sentence says the floor carries the sport from
        here, and the loop is then asked -- same database, same spent slice,
        same heartbeat still live -- whether it does.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        attention.stamp(conn, now_ms=NOW)
        # Fifty minutes short of the floor's hour, so this pass refuses and
        # says so without anything firing behind the sentence.
        pace_the_sport(conn, at_ms=NOW - 10 * MIN)
        self._spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        decision = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=4, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert "attention slice" in decision.detail
        assert "the hourly floor carries it from here" in decision.detail
        # Both refuted sentences, asserted absent by their own words: a
        # rewording that reintroduces either promise fails here rather than
        # passing on a substring the new copy happens to share.
        assert "still runs" not in decision.detail
        assert "resumes once" not in decision.detail
        assert decision.fire == ()

        # ...and it carries it. Same database, same spent slice, the heartbeat
        # deliberately re-stamped so the desk is still attended: fifty minutes
        # on, the floor's hour is up and it buys.
        later = NOW + 50 * MIN
        attention.stamp(conn, now_ms=later)
        carried = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=4, now_ms=later,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert [f.trigger for f in carried.fire] == [DESK]

    def test_a_windowed_refusal_falls_through_on_the_same_terms(
        self, conn, budget
    ):
        """The same state with `ODDS_DESK_WINDOW_UTC` pinned back on, and the
        decision recorded rather than left to be re-derived: **a windowed pass
        falls through exactly as an attended one does.**

        The reason is that the perversity is identical under a window. Past the
        slice, a pinned window bought *less* than no window at all -- opening
        the desk's clock was what switched the floor off. And the budget
        argument is indifferent to which condition displaced the floor: the
        fall-through is paced by `DESK_FLOOR_INTERVAL_MS` off the same
        `last_sweep_by_sport` either way, so it is bounded at one buy per sport
        per hour whichever branch of `desk_wants` was refused.

        The previous version of this test pinned the opposite -- a refusal
        naming *"once the desk window closes"* as the condition to wait for.
        There is no condition to wait for now, which is why that sentence is
        asserted absent.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        # No heartbeat: unattended, and the window is what displaces the floor.
        pace_the_sport(conn, at_ms=NOW - 10 * MIN)
        self._spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        refused = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=4, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
            desk_window=(12, 22),  # NOW is 18:00Z
        )
        assert refused.fire == ()
        assert "the hourly floor carries it from here" in refused.detail
        assert "desk window closes" not in refused.detail

        # Fifty minutes on, still inside the pinned window, still nobody
        # looking: the floor's hour is up and it buys anyway.
        later = NOW + 50 * MIN
        carried = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=4, now_ms=later,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
            desk_window=(12, 22),
        )
        assert [f.trigger for f in carried.fire] == [DESK]


class TestAttentionAddsToTheFloorRatherThanReplacingIt:
    """**Looking at the desk must not make it staler than not looking at it.**

    Until 2026-08-29 it did. `desk_wants` branches on `attended or windowed`
    and hands every upcoming sport the ten-minute cadence; the slice check
    refused each one with `continue`, and there was no fall-through, so past
    the slice **keeping the page open suppressed the buying and closing it let
    the floor resume** five minutes later at `DEFAULT_ATTENTION_TTL_MS`. The
    moment Joe is staring at the screen is the moment he is about to bet, and
    that is the moment the design was switching the feed off.

    WHAT THESE ESTABLISH
    --------------------
    - A sport with a fixture inside the floor's horizon still gets its hourly
      buy while the page is open and the slice is spent.
    - The fall-through is the *floor's* cadence and not a rebate on the slice:
      spent means spent, and the ten minutes do not come back.
    - The worst-case day is unmoved, because the floor's own pacing bounds it.

    WHAT THEY DO NOT ESTABLISH
    --------------------------
    - Nothing about whether 300/day is the right slice, or 700/day the right
      cap. Both are `fly.live.toml`'s decisions and neither moves here.
    - Nothing about the schedule or the prop tail, which draw on the same 700
      and are outside every figure below. `credits_left` is what actually
      stops the day, and it is unchanged.
    - Nothing about a browser. Whether `Nav.tsx` stops stamping in a
      background tab is not decidable from Python.
    """

    def test_a_spent_slice_with_the_page_open_still_gets_the_hourly_floor_buy(
        self, conn, budget
    ):
        """**The claim, in one assertion.** Someone has the desk open, the
        slice is gone, and a fixture is six hours out -- well inside
        `DESK_FLOOR_HORIZON_MS`. The sport's last served sweep is an hour and a
        minute back, so the floor's hour is up.

        On main this fires nothing: `desk_wants` gives the sport the attended
        cadence, the slice refuses it, and the `continue` skips the sport with
        no floor left to fall to.

        `DESK` and not `ATTENTION` is half the claim -- the trigger is what
        keeps the buy off `api_credits.trigger = 'attention'`, so a
        fall-through neither spends the slice it was just refused by nor is
        counted into the next pass's refusal.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        attention.stamp(conn, now_ms=NOW)
        pace_the_sport(conn, at_ms=NOW - HOUR - MIN)
        spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)

        decision = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=4, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert [f.trigger for f in decision.fire] == [DESK]
        assert decision.fire[0].sport_key == SPORT
        assert "hourly floor" in decision.fire[0].detail
        # No refusal line beside a served sweep. A pass that both fires the
        # sport and reports it "cannot be served" is ticket #35's
        # screen-versus-loop contradiction in reverse, on the same surface.
        assert "cannot be served" not in decision.detail

    def test_the_fall_through_is_hourly_and_never_the_attended_cadence(
        self, conn, budget
    ):
        """**Spent means spent.** The guard against buying the slice back: a
        fall-through that used `refresh_interval_ms` would hand the tab its ten
        minutes again under a different trigger, and stamp them `DESK` so
        nothing counted them. That is the 2,304/day worst case the slice exists
        to prevent, wearing the floor's name.

        Same state as the test above at three instants off one served sweep.
        Ten and fifty-nine minutes on, the floor is not due and nothing fires;
        at sixty-one it does. A fall-through on the attended cadence fires at
        all three.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        served_at = NOW - 10 * MIN
        pace_the_sport(conn, at_ms=served_at)

        def fires_at(offset_ms):
            at = served_at + offset_ms
            # Re-stamped each time: the desk stays attended throughout, so
            # nothing here is the unattended floor path in disguise.
            attention.stamp(conn, now_ms=at)
            return [
                f.trigger
                for f in decide_sweeps(
                    conn, in_scope={}, budget=budget, cost=4, now_ms=at,
                    max_odds_age_ms=MAX_ODDS_AGE_MS,
                ).fire
            ]

        assert fires_at(10 * MIN) == [], "the attended cadence, refused"
        assert fires_at(59 * MIN) == [], "still inside the floor's hour"
        assert fires_at(61 * MIN) == [DESK], "the floor's hour, and it buys"

    def test_the_fall_through_is_not_charged_to_the_spent_slice(
        self, conn, budget
    ):
        """The other half of "spent means spent", read off the counter rather
        than off the trigger constant.

        A fall-through buy must leave `attention_credits_spent_today` where it
        found it. If it did not, the slice would run backwards on itself --
        every floor buy pushing the counter further past a ceiling it is
        already past, which is harmless today and would silently become a cap
        on the floor the moment anyone made the refusal depend on the overage.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        attention.stamp(conn, now_ms=NOW)
        pace_the_sport(conn, at_ms=NOW - HOUR - MIN)
        spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        start = NOW - 12 * HOUR

        before = attention_credits_spent_today(conn, since_ms=start)
        fired = decide_sweeps(
            conn, in_scope={}, budget=budget, cost=4, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        ).fire[0]
        # The trigger is what the runner stamps on the `api_credits` row, so
        # replaying it is what proves the counter would not move.
        conn.execute(
            "INSERT INTO api_credits (called_ms, endpoint, sport_key, cost, "
            "trigger) VALUES (?, ?, ?, ?, ?)",
            (
                NOW, f"/sports/{SPORT}/odds", SPORT, fired.cost,
                None if fired.trigger == DESK else fired.trigger,
            ),
        )
        conn.commit()
        assert attention_credits_spent_today(conn, since_ms=start) == before

    def test_the_worst_case_day_with_the_fall_through_stays_inside_the_cap(
        self,
    ):
        """**The budget argument, computed from the constants rather than
        quoted from the deploy file.**

        The fall-through raises actual spend towards a bound that is already
        published and cannot pass it, and the reason is arithmetic:

        - The floor's cadence is measured from `last_sweep_by_sport`, which
          counts attention buys too, so a sport takes **at most one
          floor-paced buy an hour** however many attended buys preceded it.
          At `DESK_FLOOR_INTERVAL_MS` that is 24 a day per sport.
        - The slice is its own ceiling: `attention_slice_is_spent` refuses once
          `spent + cost > attention_daily_credits`, so attention-triggered
          spend is **at most `attention_daily_credits`**, and a fall-through
          buy is stamped `DESK` and adds nothing to it.

        Four sports is the maximum `fly.live.toml` plans for (NCAAF and NFL
        entering scope beside MLB and WNBA), and the deployed sweep is 4
        credits (`h2h,spreads` x `us,eu`). The two bounds are additive and
        independent, which is what makes the sum a genuine ceiling.

        **What this does not count**, deliberately: the slot planner and the
        prop tail, which draw on the same 700 and are outside the published
        table too. They are bounded by `credits_left`, which refuses any desk
        buy the day cannot afford -- so 700 is enforced by construction
        whatever this arithmetic says.

        Mutation observed red: charge the floor at `refresh_interval_ms`
        instead (24 -> 144 buys a sport) and the worst case is 2,604.
        """
        sports = 4
        sweep = 4  # sweep_cost(["h2h", "spreads"], ["us", "eu"])
        daily_cap = 700  # ODDS_DAILY_CREDIT_BUDGET on live
        slice_cap = DEFAULT_ATTENTION_DAILY_CREDITS  # 300, and live agrees

        floor_buys_per_sport = _DAY_MS // DESK_FLOOR_INTERVAL_MS
        assert floor_buys_per_sport == 24

        floor_ceiling = floor_buys_per_sport * sports * sweep
        assert floor_ceiling == 384, "fly.live.toml's idle-floor row"
        assert slice_cap == 300, "fly.live.toml's attention row"

        worst_case = floor_ceiling + slice_cap
        assert worst_case == 684, "fly.live.toml's worst-case row"
        assert worst_case <= daily_cap
        # The tap reserve is a sub-ceiling *inside* the 700 rather than a
        # carve-out from it (`ondemand.DEFAULT_MANUAL_DAILY_CREDITS`), so it is
        # not subtracted here -- but the day cannot fund both in full, and
        # `credits_left` is what refuses the loser.
        assert worst_case + ondemand.DEFAULT_MANUAL_DAILY_CREDITS > daily_cap

    def test_the_day_cap_still_refuses_a_fall_through_it_cannot_afford(
        self, conn
    ):
        """`credits_left` is the hard stop, and the fall-through goes through
        it like every other spend path. A second route that skipped it is the
        shape of every credit accident in `timing.py`'s history.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        attention.stamp(conn, now_ms=NOW)
        pace_the_sport(conn, at_ms=NOW - HOUR - MIN)
        spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        # A day whose whole budget is the 300 already spent on attention.
        broke = CreditBudget(conn, daily_budget=DEFAULT_ATTENTION_DAILY_CREDITS)
        decision = decide_sweeps(
            conn, in_scope={}, budget=broke, cost=4, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert decision.fire == ()
        assert "credits" in decision.detail


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

    def test_a_spent_slice_takes_the_attended_cadence_out_of_the_next_call(
        self, conn, budget
    ):
        """The published contradiction, and the *shape* of the fix rather than
        its first draft.

        On 2026-08-28 this asserted `next_desk_buy_ms is None`, because past
        the slice the loop bought nothing at all while anyone was looking. The
        loop now falls through to the hourly floor, so `None` would be the same
        defect inverted -- a screen saying nothing is coming while the loop
        buys. What must never come back is the *ten-minute* answer.

        Mutation observed red: drop `and not slice_spent` from the `attended`
        argument in `window_status` so `desk_wants` takes the attended branch
        again -- the field reads `NOW` where the floor puts it fifty minutes
        out, and the panel is back to promising a sweep the loop has refused.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        attention.stamp(conn, now_ms=NOW)
        pace_the_sport(conn, at_ms=NOW - 10 * MIN)
        spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        status = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=4,
        )
        assert status.attention_slice_spent is True
        assert status.desk_is_attended is True
        # The floor's hour off the same served sweep, not the attended ten
        # minutes -- which would be `NOW`, and is the answer this must refuse.
        assert status.next_desk_buy_ms == NOW - 10 * MIN + DESK_FLOOR_INTERVAL_MS
        assert status.next_desk_buy_ms > NOW

    def test_the_screen_and_the_loop_give_the_same_answer_either_way(
        self, conn, budget
    ):
        """The invariant the ticket is about, asserted against the loop itself
        rather than against a remembered value.

        Mutation observed red: drop `and not slice_spent` from `window_status`
        -- the spent half then has `decide_sweeps` refusing while
        `window_status` publishes `NOW`.

        `pace_the_sport` is what gives the two cadences different answers here;
        without it the floor and the attended cadence both want the sport now
        and the two halves agree for the wrong reason.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        attention.stamp(conn, now_ms=NOW)
        pace_the_sport(conn, at_ms=NOW - 10 * MIN)

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

        # Past the slice: the loop refuses this pass and drops to the floor's
        # hour, and the panel must publish that hour rather than the ten
        # minutes it just lost -- or `None`, which would be the same
        # disagreement pointing the other way.
        spend_the_slice(conn, credits=DEFAULT_ATTENTION_DAILY_CREDITS)
        assert desk_firings() == []
        assert panel().next_desk_buy_ms == (
            NOW - 10 * MIN + DESK_FLOOR_INTERVAL_MS
        )

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
        inside the 300 default, the desk is reported on the attended cadence,
        and the field reads `NOW` instead of the floor's hour.
        """
        add_fixture(conn, commence_ms=NOW + 6 * HOUR)
        attention.stamp(conn, now_ms=NOW)
        pace_the_sport(conn, at_ms=NOW - 10 * MIN)
        spend_the_slice(conn, credits=40)
        status = window_status(
            conn, budget=budget, now_ms=NOW,
            max_odds_age_ms=MAX_ODDS_AGE_MS, sweep_cost=4,
            attention_daily_credits=40,
        )
        assert status.attention_daily_credits == 40
        assert status.attention_slice_spent is True
        assert status.next_desk_buy_ms == NOW - 10 * MIN + DESK_FLOOR_INTERVAL_MS


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
