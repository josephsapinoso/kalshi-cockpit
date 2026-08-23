"""*When* to spend an odds credit, and when a pick is actually bettable.

`budget.plan_sweep` answered "which sport?" and never answered "when?". The
sweep fired on the first pass that had budget, and budget reset at UTC midnight,
so on 2026-08-07 the day's odds landed at 19:32Z — because that is when a deploy
happened. Nothing chose it.

That matters more than it sounds. `MAX_ODDS_AGE_S` is 900, so a recommendation
is bettable for **fifteen minutes** after the sweep that priced it; outside that
`stale_odds` suppresses it. The free tier affords two sweeps a day. So the whole
system is actionable for about half an hour a day, and until now that half hour
landed wherever the process happened to restart.

**Fifteen minutes is the *odds* limit, and it is only the whole answer because
something else keeps the other one satisfied.** A row also needs a Kalshi quote
under thirty seconds, and on a single 900s cadence that made the real window
thirty seconds rather than fifteen minutes -- this module scheduled a window
nobody could use for 97% of its length. `runner.run_quote_pass` on the fast
cadence is what closes that; see `docs/adr/0004-two-polling-cadences.md`.

**And since 2026-08-16 the fifteen minutes is no longer the length of anything.**
The two paragraphs above describe a slot that bought odds *once*. A slot now
re-buys every `refresh_interval_ms` for as long as it is due, so the window it
opens is `DUE_WINDOW_MS` long -- sixty minutes, continuous -- rather than fifteen
minutes wherever the pass happened to land. `stale_odds` was 256 of 265
suppressions in 24h, and the cause was never the threshold: nothing re-bought.
The history above is kept because it is why the scheduling exists at all, but
read it as the state that was fixed, not as how this module now behaves. See
`docs/adr/0030-the-odds-refresh-rolls.md`.

This module decides *when* the window happens and how long it is held. It has no
opinion about the Kalshi quote.

What this module decides
------------------------
A sweep is worth spending when its fifteen-minute window sits **just before a
cluster of kickoffs**: lines are sharpest near the close, and it is also when a
human would be looking. So the day's kickoffs are clustered, each cluster
becomes a candidate slot, the best `k` are selected for the `k` sweeps the
budget still affords, and a pass fires only when it lands inside a selected
slot's due window.

Four properties this rests on, each of which was a bug in something else first:

**The anchor is the sportsbook's commence time, never Kalshi's.** Kalshi's
`occurrence_datetime` runs exactly three hours late (measured across MLB and
WNBA, 2026-08-07). A sweep scheduled "twenty minutes before kickoff" against
that field fires two hours and forty minutes *into* the game. This is the same
trap `scoring.py` documents for the closing line, and the same fix: anchor on
The Odds API's own `commence_ms`, which is what `odds_snapshots` stores.

**The window must close before the first pitch.** The minimum lead is one full
freshness window, so a pick that appears at the very end of the window is still
a pre-game bet. It is derived from `max_odds_age_ms` rather than written down
separately, because two numbers for one quantity drift apart and the tighter one
wins in silence.

**The due window must be wider than the gap between passes.** A slot that is due
for twenty minutes on a loop that wakes every twenty-five will be missed most
days, and a missed sweep looks exactly like a quiet slate. `due_window_ms` is
checked against the loop interval by `sweep_window_survives_interval`, which
`run_loop` calls at startup and refuses to run without.

**Re-planned from scratch every pass, with no stored state.** Which slots have
already been served is read back from `api_credits`, so a restart cannot
double-spend and cannot forget. The scheduler holds nothing that a crash could
lose.

What this does not establish
----------------------------
That the window is *useful*. It says odds are fresh enough for a pick to survive
`stale_odds`, nothing more. Most windows will open onto an empty Board, which is
the expected result of the whole premise — Kalshi prices sports to about two
cents and the cost headroom is 0.63 points, itself an upper bound pending H4.

What the rolling refresh changes is only which of two readings an empty Board
has. It used to mean either "the consensus said no" or "nobody looked", and
those need opposite responses. Now it means the first.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Collection, Iterable, Mapping, Optional, Sequence

from .sweeplog import last_sweep_outcome

logger = logging.getLogger(__name__)

_MS_PER_MIN = 60_000
_MS_PER_HOUR = 3_600_000

# Kickoffs closer together than this are one cluster and share a slot. Twenty
# minutes covers a staggered slate -- MLB first pitches land at :05, :10 and
# :20 past the hour -- without merging the 7pm and 10pm blocks.
CLUSTER_MS = 20 * _MS_PER_MIN

# How long a slot stays due. Must exceed the loop's worst-case gap between
# passes or the slot is missed; see `sweep_window_survives_interval`.
#
# **Sixty minutes, and it is now a duration rather than a deadline.** It was
# thirty, back when a slot fired once and the sweep it bought was good for
# `max_odds_age_ms` afterwards -- so the window a slot opened was fifteen
# minutes wherever inside those thirty the pass happened to land, and the rest
# of the due window bought nothing. Under `refresh_interval_ms` the slot re-buys
# odds for as long as it is due, so this constant now *is* the length of the
# open window, and widening it widens what the screen is actually usable for.
#
# Sixty rather than more, for two reasons that bound it from opposite sides.
# `MIN_SLOT_SEPARATION_MS` is two hours, so a wider window than that would let
# one sport's slots overlap and double-buy the same cluster. And the day is
# metered: a sixty-minute window at a ten-minute refresh is six calls, so a
# cluster costs `6 x sweep_cost` rather than `sweep_cost`. That multiplier is
# reserved for explicitly in `decide_sweeps` -- see `projected_total_cost` --
# because a rolling refresh that is planned as if it were a single call is the
# same defect the prop tail already caused once.
DUE_WINDOW_MS = 60 * _MS_PER_MIN


def refresh_interval_ms(max_odds_age_ms: int) -> int:
    """How long to let stored odds age before re-buying them, while a slot is due.

    **Derived from the staleness limit, never written down beside it.** The
    limit and the refresh cadence are one quantity seen from two ends: odds
    bought at `t` stop being bettable at `t + max_odds_age_ms`, so a refresh
    that fires at `t + max_odds_age_ms` re-opens the window exactly as it shuts
    and the Board blinks once a cycle. Two independent constants would drift,
    and the tighter one wins in silence -- which is the failure this module's
    docstring already records for `MAX_ODDS_AGE_S` against the Kalshi limit.

    Two thirds, so the refresh lands with a third of the window still unspent.
    That headroom absorbs the gap between passes: a refresh is only *considered*
    when a pass runs, so the true worst-case age is this plus one pass interval.
    At the deployed 900s limit that is 600s of refresh plus a 15s quote cadence
    = 615s, comfortably inside 900s. It would **not** be comfortable on the
    900s full-pass cadence alone (600 + 900 = 1500s, stale for two thirds of
    every cycle), which is precisely why `run_quote_pass` carries the odds leg
    and the full pass is not simply run more often.
    """
    return max_odds_age_ms * 2 // 3

# How far back "the current slate" reaches, measured from the most recent
# decision this instance recorded. `/api/board` selects on this; a row older
# than this is history, however large its edge.
#
# **The floor is the loop's worst-case gap between passes**, and that is the
# whole derivation. Every pass re-prices every candidate and either records a
# new row or stamps the existing one via `confirm_recommendation`, so a window
# shorter than one gap would drop rows off the Board between passes and put
# them back afterwards — a slate that flickers with the loop's cadence rather
# than with the market. `sweep_window_survives_interval` already proves
# `DUE_WINDOW_MS` exceeds that gap and `run_loop` refuses to start when it does
# not, so borrowing that number here inherits a check that already runs at
# startup instead of introducing a second, unchecked one.
#
# It is deliberately *not* `max_odds_age_ms`. That limit says when a row stops
# being bettable, which the Board already answers per row with
# `actionable` — and answering it twice, once as a filter, would delete the
# rejected rows that are the only evidence the page has on a slate with zero
# actionable.
#
# **Written down rather than aliased to `DUE_WINDOW_MS`, which it was until the
# rolling refresh.** The alias was sound while the two happened to want the same
# number, and it silently stopped being sound the moment `DUE_WINDOW_MS` became
# the length of the open window: widening the sweep schedule would have widened
# how far back the Board calls a row "current", so the page would have shown
# hour-old rows as this slate without anybody choosing that. The two quantities
# answer different questions and only ever agreed by coincidence.
#
# The floor argued for above is still the loop's worst-case gap, and it is still
# inherited rather than re-checked: `_SLATE_WINDOW_INHERITS_THE_STARTUP_CHECK`
# below ties this to the constant `run_loop` already proves at startup.
SLATE_WINDOW_MS = 30 * _MS_PER_MIN

# The startup check `run_loop` runs is `sweep_window_survives_interval`, and it
# proves `DUE_WINDOW_MS` exceeds the loop's worst-case gap between passes.
# `SLATE_WINDOW_MS` needs exactly that same floor and has no check of its own,
# so it borrows this one by staying inside the window that was proved. Asserted
# at import rather than in a test, because the failure it prevents is a Board
# that drops rows between passes -- which reads as a quiet slate, not as a bug.
_SLATE_WINDOW_INHERITS_THE_STARTUP_CHECK = SLATE_WINDOW_MS <= DUE_WINDOW_MS
assert _SLATE_WINDOW_INHERITS_THE_STARTUP_CHECK, (
    "SLATE_WINDOW_MS must stay inside DUE_WINDOW_MS so it inherits the "
    "worst-case-gap check that run_loop already runs at startup"
)

# Games kicking off within this far of the anchor are counted as covered by the
# slot. Three hours: a line that far out is a real price a human would bet, and
# it is the same sweep that produced it.
COVERAGE_MS = 3 * _MS_PER_HOUR

# Two slots for the same sport closer than this buy overlapping coverage. With
# only two sweeps a day, spending both on the same block of games wastes one.
MIN_SLOT_SEPARATION_MS = 2 * _MS_PER_HOUR

# Games beyond this are not worth pricing yet -- the line will move many times
# before it matters. Matches `plan_sweep`'s horizon.
DEFAULT_HORIZON_MS = 48 * _MS_PER_HOUR

# The budget day rolls at this UTC hour rather than at midnight. UTC midnight is
# 8pm ET / 5pm PT, which is the middle of the US evening slate: it splits one
# night's games across two budget buckets, so the second half of the slate
# competes with the next afternoon's. 10:00Z is 6am ET / 3am PT, after even a
# West Coast extra-innings game has finished.
DEFAULT_DAY_START_UTC_HOUR = 10


def day_start_ms(now_ms: int, *, hour: int = DEFAULT_DAY_START_UTC_HOUR) -> int:
    """Start of the budget day containing `now_ms`.

    Not the calendar day. The *month* boundary stays on the calendar, because
    that one belongs to The Odds API and reconciliation depends on agreeing
    with them; the daily cap is ours and should follow the sports calendar.
    """
    dt = datetime.fromtimestamp(now_ms / 1000, timezone.utc)
    start = dt.replace(hour=hour, minute=0, second=0, microsecond=0)
    if dt < start:
        # Before today's roll, so we are still inside yesterday's budget day.
        start -= timedelta(days=1)
    return int(start.timestamp() * 1000)


def covers_commence(
    commence_ms: int,
    *,
    fire_until_ms: int,
    anchor_commence_ms: int,
    coverage_ms: int = COVERAGE_MS,
) -> bool:
    """Does a sweep fired for this cluster make that kickoff bettable?

    **This is the one definition of "covered", and it has two callers on
    purpose.** `slots_for_sport` counts through it to produce
    `SweepSlot.games_covered`, and `runner.fetch_and_store_props` filters
    through `SweepSlot.covers` to decide which fixtures to buy props for. Those
    two answers must be the same answer: `/api/window` publishes the count as
    `slots_planned`, and a set that disagreed with its own published count is
    invisible from either side.

    They were not the same answer until 2026-08-15. The count lived here as an
    inline comprehension and the prop fetch had no notion of a slot at all, so
    it bought for every pre-game fixture in the slate -- 27 where the slot
    covered 4 -- and spent 384 of 400 daily credits in one pass. See
    `tasks/lessons.md`: prefer the codebase's named predicate over an inline
    re-expression, because the predicate *is* the assumption written down.
    """
    return fire_until_ms <= commence_ms <= anchor_commence_ms + coverage_ms


@dataclass(frozen=True)
class SweepSlot:
    """One planned sweep: a sport, and the kickoff cluster it is aimed at."""

    sport_key: str
    # The first kickoff of the cluster. The window closes before this.
    anchor_commence_ms: int
    # Games this slot makes bettable: kicking off after the window closes and
    # within `coverage_ms` of the anchor. Counted through `covers`, never
    # recomputed inline -- see `covers_commence`.
    games_covered: int
    fire_from_ms: int
    fire_until_ms: int
    # Stored rather than read from the module constant, so a slot planned under
    # a non-default coverage answers `covers` with the width it was planned at.
    coverage_ms: int = COVERAGE_MS

    def is_due(self, now_ms: int) -> bool:
        return self.fire_from_ms <= now_ms <= self.fire_until_ms

    def covers(self, commence_ms: int) -> bool:
        """Whether this slot makes a kickoff at `commence_ms` bettable."""
        return covers_commence(
            commence_ms,
            fire_until_ms=self.fire_until_ms,
            anchor_commence_ms=self.anchor_commence_ms,
            coverage_ms=self.coverage_ms,
        )

    @property
    def minutes_before_kickoff(self) -> float:
        """Lead time at the *end* of the due window -- the tightest case."""
        return (self.anchor_commence_ms - self.fire_until_ms) / _MS_PER_MIN

    def calls_remaining(self, now_ms: int, refresh_interval_ms: int) -> int:
        """How many `/odds` calls this slot still wants before it closes.

        **The number `decide_sweeps` reserves against, and the reason it must.**
        A slot used to cost one call, so planning could size the day as
        `remaining_today // cost` and be right. Under the rolling refresh a slot
        costs one call now plus one every `refresh_interval_ms` until
        `fire_until_ms`, and a planner that still charges it one authorises a
        window it cannot keep open -- opening the screen, spending the day's
        credits keeping it open for two clusters, and going dark for the third
        with no row anywhere saying why.

        This is the same defect the prop tail caused on 2026-08-15, in the same
        place, which is why the remedy is the same one: price the tail at
        planning time rather than discovering it at spend time.

        Counted from `now_ms` rather than from `fire_from_ms`, so a slot half
        spent reserves only what it still needs. Never below one: a slot that is
        due at all wants at least the call that opens it.
        """
        if refresh_interval_ms <= 0:
            return 1
        left = max(0, self.fire_until_ms - max(now_ms, self.fire_from_ms))
        return 1 + left // refresh_interval_ms

    @property
    def reason(self) -> str:
        return (
            f"{self.games_covered} game(s) from "
            f"{_hhmm(self.anchor_commence_ms)}Z, sweeping "
            f"{(self.anchor_commence_ms - self.fire_from_ms) / _MS_PER_MIN:.0f}"
            f"-{self.minutes_before_kickoff:.0f} min before first kickoff"
        )


def _hhmm(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%H:%M")


# What a firing is for. `SCHEDULED` opens a slot's window and is the only
# trigger that buys player props; `REFRESH` keeps an already-open window from
# shutting and buys nothing but the team sweep. `BOOTSTRAP` has no slot at all.
#
# **The props distinction is load-bearing, not tidiness.** Props are billed per
# event per market key per region -- 20 credits an event on the deployed config
# -- so re-buying them on every refresh would cost `20 x games x 6` a cluster
# where the team sweep costs 36. The live config sets no prop markets today, so
# this changes nothing that currently runs; it is written down because the day
# it does set them is not the day to discover this.
SCHEDULED = "scheduled"
REFRESH = "refresh"
BOOTSTRAP = "bootstrap"
# A person tapped refresh. Not a fourth way of scheduling -- the planner does
# not produce these and cannot predict them; `decide_sweeps` is handed them and
# charges the day for them. The string is also what lands in
# `api_credits.trigger`, and `_SERVED_SWEEP` excludes exactly this value, so the
# two must stay the same literal.
MANUAL = "manual"
# The desk is open and the slate should be priced, whether or not a kickoff
# cluster is imminent. Fired only inside the configured desk window
# (`OddsConfig.desk_window_utc`), paced by the same `refresh_interval_ms` as a
# slot's rolling refresh, and never buys props. Exists because the slot design
# alone targets the closing line: measured 2026-08-23, the slate spent 14 hours
# at 89% `stale_odds` refusals while the day's budget sat at 0 of 600 spent --
# the right record for the *evidence*, the wrong sole schedule for a betting
# desk (ADR 0062). Stamped NULL in `api_credits` like every planner firing, so
# `_SERVED_SWEEP` counts it and the cadence paces itself off recorded spend.
DESK = "desk"


def desk_window_contains(
    now_ms: int, *, start_hour: int, end_hour: int
) -> bool:
    """Whether `now_ms` falls inside the desk window's UTC hours.

    `start_hour > end_hour` is a window that crosses midnight (16-04 is
    16:00Z through 03:59Z). Equal hours are **no window, never all day**:
    an all-day desk at four sports is ~1150 credits/day against a 600 cap,
    so the misread that would quietly buy it is the one this refuses.
    """
    if start_hour == end_hour:
        return False
    hour = datetime.fromtimestamp(now_ms / 1000, timezone.utc).hour
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def next_desk_open_ms(now_ms: int, *, start_hour: int, end_hour: int) -> int:
    """The next instant the desk window is open; `now_ms` itself if open now."""
    if desk_window_contains(now_ms, start_hour=start_hour, end_hour=end_hour):
        return now_ms
    dt = datetime.fromtimestamp(now_ms / 1000, timezone.utc)
    cand = dt.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    if cand <= dt:
        cand += timedelta(days=1)
    return int(cand.timestamp() * 1000)


def firing_for_slot(
    slot: SweepSlot,
    *,
    now_ms: int,
    last_sweep_ms: Optional[int],
    refresh_interval_ms: int,
) -> Optional[str]:
    """What this slot wants right now: `SCHEDULED`, `REFRESH`, or nothing.

    **One predicate, two callers, on purpose.** `decide_sweeps` fires through
    it and `window_status` displays through it. Those two answers must be the
    same answer -- the window panel tells a human when to look, and a panel that
    computed "next sweep" by its own reasoning would eventually disagree with
    the loop, with no way to tell from the page which of them was wrong. This
    module's own `covers_commence` exists for exactly that reason, and this is
    the second instance of the same rule.

    `last_sweep_ms` is the sport's most recent served `/odds` call, or `None` if
    it has had none today. A sweep from *before* this slot opened does not count
    as having opened it: an earlier cluster's window, or a bootstrap, leaves a
    stamp that is hours old and says nothing about whether these kickoffs have
    been priced.
    """
    if not slot.is_due(now_ms):
        return None
    if last_sweep_ms is None or last_sweep_ms < slot.fire_from_ms:
        return SCHEDULED
    if now_ms - last_sweep_ms >= refresh_interval_ms:
        return REFRESH
    return None


def cluster_kickoffs(
    commence_ms: Iterable[int], *, cluster_ms: int = CLUSTER_MS
) -> list[int]:
    """Collapse kickoffs into cluster anchors, keeping the **earliest** of each.

    The earliest rather than the median, because the slot's whole promise is
    that the freshness window closes before the first pitch. Anchoring on the
    middle of a cluster would put the first game of it in play.
    """
    times = sorted(set(int(c) for c in commence_ms))
    anchors: list[int] = []
    for t in times:
        if not anchors or t - anchors[-1] > cluster_ms:
            anchors.append(t)
    return anchors


def slots_for_sport(
    sport_key: str,
    commence_ms: Sequence[int],
    *,
    now_ms: int,
    max_odds_age_ms: int,
    due_window_ms: int = DUE_WINDOW_MS,
    horizon_ms: int = DEFAULT_HORIZON_MS,
    coverage_ms: int = COVERAGE_MS,
    cluster_ms: int = CLUSTER_MS,
) -> list[SweepSlot]:
    """Every candidate slot for one sport, unfiltered by budget.

    The minimum lead is `max_odds_age_ms` — one whole freshness window — so a
    pick surfaced at the last second of the window is still a pre-game bet.
    """
    future = [int(c) for c in commence_ms if c >= now_ms]
    slots: list[SweepSlot] = []
    for anchor in cluster_kickoffs(future, cluster_ms=cluster_ms):
        if anchor - now_ms > horizon_ms:
            continue
        fire_until = anchor - max_odds_age_ms
        fire_from = fire_until - due_window_ms
        if fire_until < now_ms:
            # The moment to sweep for this cluster has passed. Sweeping now
            # would open a window that runs into the game.
            continue
        covered = sum(
            1
            for c in future
            if covers_commence(
                c,
                fire_until_ms=fire_until,
                anchor_commence_ms=anchor,
                coverage_ms=coverage_ms,
            )
        )
        slots.append(
            SweepSlot(
                sport_key=sport_key,
                anchor_commence_ms=anchor,
                games_covered=covered,
                fire_from_ms=fire_from,
                fire_until_ms=fire_until,
                coverage_ms=coverage_ms,
            )
        )
    return slots


def plan_sweep_slots(
    fixtures_by_sport: Mapping[str, Sequence[int]],
    *,
    now_ms: int,
    slots_available: int,
    max_odds_age_ms: int,
    due_window_ms: int = DUE_WINDOW_MS,
    horizon_ms: int = DEFAULT_HORIZON_MS,
    min_separation_ms: int = MIN_SLOT_SEPARATION_MS,
) -> list[SweepSlot]:
    """The `slots_available` best remaining sweeps, in chronological order.

    `fixtures_by_sport` maps sport key -> **sportsbook** kickoff times. Passing
    Kalshi's `occurrence_datetime` here schedules every sweep three hours into
    the game; see the module docstring.

    Selection is greedy on games covered, because the point of a sweep is how
    many games it makes bettable at once. Ties go to the earlier slot: an
    earlier sweep leaves the later cluster still schedulable, and the reverse
    does not.

    **A slot already served is no longer dropped, and that is the whole rolling
    refresh.** It used to be: an `/odds` call for that sport at or after
    `fire_from_ms` removed the slot for good, so a cluster got exactly one buy
    and the window it opened shut `max_odds_age_ms` later with the games still
    an hour away. Whether the slot now wants another call is a question about
    *when it was last served*, not about *whether it ever was, so it belongs to
    `firing_for_slot` and is asked by `decide_sweeps` at spend time. Planning
    answers only "is this cluster worth a window".

    That leaves this function with no use for `last_sweep_ms_by_sport`, which is
    why the parameter is gone rather than kept and ignored. The double-spend it
    used to prevent is prevented by `refresh_interval_ms` instead, and still
    from recorded spend rather than process memory, so a restart mid-window
    still cannot double-buy.

    **A slot that is already due outranks one that is not**, ahead of the games
    covered. Without that, a live window competing for the last affordable slot
    could lose to a bigger future cluster and go dark mid-flight -- spending
    credits to open a screen and then abandoning it, which is worse than either
    never opening it or keeping it open.
    """
    candidates: list[SweepSlot] = []
    for sport_key, commences in fixtures_by_sport.items():
        candidates.extend(
            slots_for_sport(
                sport_key,
                commences,
                now_ms=now_ms,
                max_odds_age_ms=max_odds_age_ms,
                due_window_ms=due_window_ms,
                horizon_ms=horizon_ms,
            )
        )

    candidates.sort(
        key=lambda s: (not s.is_due(now_ms), -s.games_covered, s.anchor_commence_ms)
    )

    chosen: list[SweepSlot] = []
    for slot in candidates:
        if len(chosen) >= slots_available:
            break
        if any(
            c.sport_key == slot.sport_key
            and abs(c.anchor_commence_ms - slot.anchor_commence_ms)
            < min_separation_ms
            for c in chosen
        ):
            continue
        chosen.append(slot)

    chosen.sort(key=lambda s: s.anchor_commence_ms)
    return chosen


# ---------------------------------------------------------------------------
# Reading the schedule back out of the database
# ---------------------------------------------------------------------------
# All of this is recomputed per call rather than cached. It is three indexed
# queries, and a cached schedule is a schedule that can be wrong after a
# restart -- which is exactly the state that produced a 19:32Z sweep.


def upcoming_fixtures_by_sport(
    conn, *, now_ms: int, horizon_ms: int = DEFAULT_HORIZON_MS
) -> dict[str, list[int]]:
    """Sportsbook kickoff times per sport, from stored odds.

    From `odds_snapshots` rather than `kalshi_events` for one reason, and it is
    the reason the whole module exists: Kalshi's commence time is three hours
    late, so scheduling against it aims every sweep at the third inning.

    A fixture stored days ago still carries a correct future kickoff, so this
    keeps working through a day on which no sweep has run yet -- which is
    precisely when the schedule is needed.
    """
    rows = conn.execute(
        "SELECT sport_key, commence_ms FROM ("
        "  SELECT DISTINCT sport_key, odds_event_id, commence_ms"
        "  FROM odds_snapshots WHERE commence_ms >= ? AND commence_ms <= ?"
        ")",
        (now_ms, now_ms + horizon_ms),
    ).fetchall()
    fixtures: dict[str, list[int]] = {}
    for row in rows:
        fixtures.setdefault(row["sport_key"], []).append(int(row["commence_ms"]))
    return fixtures


_DAY_MS = 24 * _MS_PER_HOUR


def first_window_open_of_day(
    conn,
    *,
    day_start_ms: int,
    max_odds_age_ms: int,
    due_window_ms: int = DUE_WINDOW_MS,
    horizon_ms: int = DEFAULT_HORIZON_MS,
    day_ms: int = _DAY_MS,
    desk_window: Optional[tuple[int, int]] = None,
) -> Optional[int]:
    """When the first sweep window of this budget day opens. `None` if none does.

    **This exists because two unrelated clocks were being compared.** The sweep
    banner asked "has anything swept since the budget day opened?" and treated
    `no` as a warning. But `budget_day_start_ms` is a *credits-accounting*
    boundary -- 10:00Z, chosen so a West Coast extra-innings game lands in the
    day it belongs to -- while sweep windows are *kickoff-derived*,
    `[anchor - max_odds_age_ms - due_window_ms, anchor - max_odds_age_ms]`.
    Nothing connects the two. Between the boundary and the day's first window
    there is no window in which to spend, so "nothing has swept" is not an
    observation about the loop; it is arithmetic, and it was rendered as an
    alarm. Measured on the live record, that state held on **6 of 6** budget days
    sampled (2026-08-12 .. 2026-08-17), for 6.5-10.8 hours each.

    Deliberately the *same* slot computation the scheduler spends credits with
    (`slots_for_sport`), read from `day_start_ms` rather than from `now`, so a
    window that opened and closed earlier today is still counted. Planning from
    `now` would forget it, and forgetting it is precisely how the 17-hour
    incident -- windows opened, passed, and nothing swept -- would be rendered
    calm by this fix. That is the failure this function must not cause.

    The result is clamped to `day_start_ms`: a window already open when the day
    rolled over opens, for this purpose, at the boundary. It is bounded to one
    day because the question is about *this* budget day; a slate that starts
    tomorrow correctly yields `None`, meaning no window is owed today.

    `None` is "no window opens today", never "unknown". The caller must not read
    it as reassurance on its own -- a loop that is not running at all is
    `last_look_ms` going stale, and that is a different field and a different
    tone.
    """
    fixtures = upcoming_fixtures_by_sport(
        conn, now_ms=day_start_ms, horizon_ms=horizon_ms
    )
    day_end_ms = day_start_ms + day_ms
    opens: list[int] = []
    for sport_key, commences in fixtures.items():
        for slot in slots_for_sport(
            sport_key,
            commences,
            now_ms=day_start_ms,
            max_odds_age_ms=max_odds_age_ms,
            due_window_ms=due_window_ms,
            horizon_ms=horizon_ms,
        ):
            opens_at = max(slot.fire_from_ms, day_start_ms)
            if opens_at < day_end_ms:
                opens.append(opens_at)
    if desk_window is not None and fixtures:
        start_hour, end_hour = desk_window
        if start_hour != end_hour:
            # The desk window is a window of this day like any slot's: it
            # counts only if it opens inside the day, and a day whose start
            # falls mid-window opens, for this purpose, at the boundary.
            desk_open = next_desk_open_ms(
                day_start_ms, start_hour=start_hour, end_hour=end_hour
            )
            if desk_open < day_end_ms:
                opens.append(desk_open)
    return min(opens) if opens else None


# What counts as a served sweep, for both readers of `api_credits` below.
#
# **One predicate, named once**, because the two queries used to disagree and
# the disagreement was the whole surface of a bug. `last_sweep_by_sport` filtered
# on neither endpoint nor cost while `_latest_sweep_row`, three lines away,
# filtered on the endpoint. Both looked reasonable in isolation.
#
# Each half is load-bearing in a different direction:
#
# `cost > 0` -- a row that spent no credits fetched no odds. Without it, any
# zero-cost row lands here as a sweep, and the obvious way to record a *refused*
# sweep is exactly such a row. That fix would have made the scheduler decline the
# sport it had just failed to sweep, permanently and silently, which is why the
# refusal is recorded in `odds_sweep_log` instead. This clause means it could not
# do damage even if someone wrote it here anyway.
#
# `LIKE '%/odds'` -- the historical endpoints charge `10 x markets x regions` for
# a *backfill*, which is spend but is not a sweep of the current board. Cost
# alone would let one of those suppress the day's live sweep for that sport.
#
# `LIKE '%/odds'` rather than `= '/odds'`, which is the bug this replaces:
# `client.py` records `/sports/{sport_key}/odds`, so the equality never matched a
# single production row. `seed_demo.py` writes the literal `/odds`, so the demo
# database matched and the live one did not -- the last-sweep age on the window
# panel read "never" on the instance and correct on the demo, for the project's
# life. That is the readout that would have shown odds fetching had stopped.
# `%` matches the empty string, so this predicate covers both spellings.
# `trigger != 'manual'` -- an on-demand refresh makes the identical request at
# the identical cost, so endpoint and cost cannot separate them. It has to be
# separated, and the direction is not symmetric: a tap counted as a sweep moves
# `last_sweep_by_sport` past `slot.fire_from_ms`, which turns the slot's opening
# `SCHEDULED` firing into a `REFRESH` -- and props ride the opening call only.
# One tap in the fifteen seconds before a window opened would cost that cluster
# its whole prop purchase, silently, for the day.
#
# `COALESCE` because the column is v9 and every row before it is a planner call.
# NULL means "nobody recorded", which for those rows is true and reads as a
# sweep, which is what they are. See migration v9.
_SERVED_SWEEP = (
    "endpoint LIKE '%/odds' AND cost > 0 AND COALESCE(trigger, '') != 'manual'"
)


def last_sweep_by_sport(conn, *, since_ms: int) -> dict[str, int]:
    """`sport_key -> most recent served /odds call`, within the budget day."""
    rows = conn.execute(
        "SELECT sport_key, MAX(called_ms) AS last_ms FROM api_credits "
        f"WHERE called_ms >= ? AND sport_key IS NOT NULL AND {_SERVED_SWEEP} "
        "GROUP BY sport_key",
        (since_ms,),
    ).fetchall()
    return {r["sport_key"]: int(r["last_ms"]) for r in rows}


def _latest_sweep_row(conn):
    return conn.execute(
        "SELECT called_ms, sport_key FROM api_credits "
        f"WHERE {_SERVED_SWEEP} ORDER BY called_ms DESC LIMIT 1"
    ).fetchone()


def fixture_freshness(
    conn, *, now_ms: int, market: str = "h2h"
) -> list[int]:
    """Age in ms of each upcoming fixture's consensus, oldest book first.

    One number per fixture, measured the way `runner.book_quotes_for_event`
    measures it: within that fixture's most recent sweep, the **oldest**
    contributing book, falling back to our fetch time when the book reported no
    `last_update`. A consensus is only as fresh as the stalest price in it.

    Approximate in one direction only: the runner drops books that do not quote
    every outcome before taking the oldest, and this does not, so a fixture can
    read slightly staler here than the suppression check will find it. Erring
    towards "closed" is the right direction for a window indicator.
    """
    rows = conn.execute(
        "WITH latest AS ("
        "  SELECT odds_event_id, MAX(fetched_ms) AS m FROM odds_snapshots"
        "  WHERE market = ? AND commence_ms >= ? GROUP BY odds_event_id"
        ") "
        "SELECT MIN(COALESCE(o.book_updated_ms, o.fetched_ms)) AS oldest_ms "
        "FROM odds_snapshots o JOIN latest l "
        "  ON o.odds_event_id = l.odds_event_id AND o.fetched_ms = l.m "
        "WHERE o.market = ? GROUP BY o.odds_event_id",
        (market, now_ms, market),
    ).fetchall()
    return sorted(now_ms - int(r["oldest_ms"]) for r in rows)


@dataclass(frozen=True)
class ActionableWindow:
    """Whether a pick could be bettable right now, and when the next chance is.

    `fixtures_fresh` is the honest headline. "The window is open" is not a
    property of the system, it is a property of each fixture's own books, and
    a slate can be half fresh. Counting them says so instead of averaging it
    away.
    """

    now_ms: int
    max_odds_age_ms: int
    fixtures_upcoming: int
    fixtures_fresh: int
    open_until_ms: Optional[int]
    last_sweep_ms: Optional[int]
    last_sweep_sport: Optional[str]
    next_slot: Optional[SweepSlot]
    slots_planned: tuple[SweepSlot, ...]
    # When the next `/odds` call is actually wanted, which since the rolling
    # refresh is no longer `next_slot.fire_from_ms`. A slot mid-window has a
    # `fire_from_ms` in the past, and publishing that as "next sweep" would put
    # a time on the page that has already been and gone -- the one readout a
    # human uses to decide when to look. Computed through `firing_for_slot`, the
    # same predicate the loop fires on, so the page cannot disagree with it.
    next_call_ms: Optional[int]
    refresh_interval_ms: int
    sweeps_remaining_today: int
    spent_today: int
    daily_budget: int
    budget_day_start_ms: int

    # The last time a pass decided anything at all about odds, and what it
    # decided. Distinct from `last_sweep_ms`, which is the last time one was
    # *served*: the gap between the two is exactly the state that went unnoticed
    # for 17 hours. `None` means this database has never recorded a pass looking,
    # which after a fresh deploy is the true state and is not the same as "it
    # looked and found nothing".
    last_look_ms: Optional[int] = None
    last_look_outcome: Optional[str] = None
    last_look_detail: Optional[str] = None

    # When this budget day's first sweep window opens. `None` means no window
    # opens today at all. Read `first_window_open_of_day` for why a *schedule*
    # time has to sit beside `budget_day_start_ms`: the boundary is an accounting
    # fact and the window is a kickoff fact, and asking the first to answer for
    # the second is what made the sweep banner fire every morning by arithmetic.
    first_window_open_ms: Optional[int] = None

    @property
    def is_open(self) -> bool:
        return self.fixtures_fresh > 0

    @property
    def seconds_remaining(self) -> Optional[int]:
        if not self.is_open or self.open_until_ms is None:
            return None
        return max(0, (self.open_until_ms - self.now_ms) // 1000)

    def to_dict(self) -> dict:
        return {
            "now_ms": self.now_ms,
            "is_open": self.is_open,
            "seconds_remaining": self.seconds_remaining,
            "open_until_ms": self.open_until_ms,
            "fixtures_upcoming": self.fixtures_upcoming,
            "fixtures_fresh": self.fixtures_fresh,
            "max_odds_age_s": self.max_odds_age_ms // 1000,
            "last_sweep_ms": self.last_sweep_ms,
            "last_sweep_sport": self.last_sweep_sport,
            "next_sweep_ms": self.next_call_ms,
            "refresh_interval_s": self.refresh_interval_ms // 1000,
            "next_sweep_sport": (
                self.next_slot.sport_key if self.next_slot else None
            ),
            "next_sweep_games": (
                self.next_slot.games_covered if self.next_slot else None
            ),
            "next_sweep_reason": (
                self.next_slot.reason if self.next_slot else None
            ),
            "slots_planned": [
                {
                    "sport_key": s.sport_key,
                    "fire_from_ms": s.fire_from_ms,
                    "fire_until_ms": s.fire_until_ms,
                    "anchor_commence_ms": s.anchor_commence_ms,
                    "games_covered": s.games_covered,
                }
                for s in self.slots_planned
            ],
            "sweeps_remaining_today": self.sweeps_remaining_today,
            "spent_today": self.spent_today,
            "daily_budget": self.daily_budget,
            "budget_day_start_ms": self.budget_day_start_ms,
            "last_look_ms": self.last_look_ms,
            "last_look_outcome": self.last_look_outcome,
            "last_look_detail": self.last_look_detail,
            "first_window_open_ms": self.first_window_open_ms,
            "note": (
                "Open means odds are fresh enough for a pick to survive the "
                "staleness check. It does not mean there is anything to bet -- "
                "most windows open onto an empty board, which is the expected "
                "result."
            ),
        }


def window_status(
    conn,
    *,
    budget,
    now_ms: int,
    max_odds_age_ms: int,
    sweep_cost: int,
    horizon_ms: int = DEFAULT_HORIZON_MS,
    desk_window: Optional[tuple[int, int]] = None,
) -> ActionableWindow:
    """The window, and the next planned sweep, from stored state alone.

    Shares `plan_sweep_slots` with the runner rather than reimplementing the
    schedule for display. A screen and a control that compute the same thing by
    two paths eventually disagree, and the one people act on is the screen.

    `desk_window` must be the same value the runner hands `decide_sweeps`
    (`OddsConfig.desk_window_utc`), for the same one-predicate-two-callers
    reason as `firing_for_slot`: `next_call_ms` is the screen's "when does the
    next window open", and a desk buy the loop will make is a call this
    display must predict.
    """
    state = budget.state(now_ms)
    remaining_sweeps = max(0, state.remaining_today // max(1, sweep_cost))
    start_ms = budget.day_start_ms(now_ms)

    ages = fixture_freshness(conn, now_ms=now_ms)
    fresh = [a for a in ages if a <= max_odds_age_ms]
    open_until = now_ms + (max_odds_age_ms - min(fresh)) if fresh else None

    fixtures_by_sport = upcoming_fixtures_by_sport(
        conn, now_ms=now_ms, horizon_ms=horizon_ms
    )
    slots = plan_sweep_slots(
        fixtures_by_sport,
        now_ms=now_ms,
        slots_available=remaining_sweeps,
        max_odds_age_ms=max_odds_age_ms,
        horizon_ms=horizon_ms,
    )
    refresh_ms = refresh_interval_ms(max_odds_age_ms)
    served = last_sweep_by_sport(conn, since_ms=start_ms)
    next_slot = slots[0] if slots else None
    next_call_ms: Optional[int] = None
    if next_slot is not None:
        last = served.get(next_slot.sport_key)
        if (
            firing_for_slot(
                next_slot,
                now_ms=now_ms,
                last_sweep_ms=last,
                refresh_interval_ms=refresh_ms,
            )
            is not None
        ):
            # Wanted right now. The next pass will serve it, so the honest
            # answer is "now" rather than a time in either direction.
            next_call_ms = now_ms
        elif last is not None and last >= next_slot.fire_from_ms:
            # Mid-window: the slot is open and simply not yet due to re-buy.
            next_call_ms = last + refresh_ms
        else:
            next_call_ms = next_slot.fire_from_ms

    if desk_window is not None and fixtures_by_sport:
        start_hour, end_hour = desk_window
        if start_hour != end_hour:
            if desk_window_contains(
                now_ms, start_hour=start_hour, end_hour=end_hour
            ):
                # The loop's desk pass will re-buy each sport once its last
                # served sweep ages past the refresh interval; the soonest of
                # those is the next call the desk wants.
                desk_next = min(
                    now_ms
                    if (last := served.get(sport)) is None
                    or now_ms - last >= refresh_ms
                    else last + refresh_ms
                    for sport in fixtures_by_sport
                )
            else:
                desk_next = next_desk_open_ms(
                    now_ms, start_hour=start_hour, end_hour=end_hour
                )
            next_call_ms = (
                desk_next
                if next_call_ms is None
                else min(next_call_ms, desk_next)
            )

    latest = _latest_sweep_row(conn)
    # Not the same question as `latest`, and the difference is the whole point:
    # `latest` is the last sweep that was *served*, this is the last time a pass
    # made any decision at all. A long gap in the first with a fresh second says
    # "the loop is alive and declining"; a gap in both says "the loop is not
    # running". Those need opposite responses and used to be one observation.
    look = last_sweep_outcome(conn)

    return ActionableWindow(
        now_ms=now_ms,
        max_odds_age_ms=max_odds_age_ms,
        fixtures_upcoming=len(ages),
        fixtures_fresh=len(fresh),
        open_until_ms=open_until,
        last_sweep_ms=int(latest["called_ms"]) if latest else None,
        last_sweep_sport=latest["sport_key"] if latest else None,
        next_slot=next_slot,
        slots_planned=tuple(slots),
        next_call_ms=next_call_ms,
        refresh_interval_ms=refresh_ms,
        sweeps_remaining_today=remaining_sweeps,
        spent_today=state.spent_today,
        daily_budget=state.daily_budget,
        budget_day_start_ms=start_ms,
        last_look_ms=int(look["pass_ms"]) if look else None,
        last_look_outcome=look["outcome"] if look else None,
        last_look_detail=look["detail"] if look else None,
        first_window_open_ms=first_window_open_of_day(
            conn,
            day_start_ms=start_ms,
            max_odds_age_ms=max_odds_age_ms,
            horizon_ms=horizon_ms,
            desk_window=desk_window,
        ),
    )


# ---------------------------------------------------------------------------
# The decision a pass actually makes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FiringSweep:
    """One sweep this pass will spend credits on."""

    sport_key: str
    # What the `/odds` call itself costs. Deliberately still the *team* sweep
    # cost and not the projected total: `runner.fetch_and_store_odds` probes
    # `budget.refusal_reason(firing.cost, ...)` immediately before making that
    # one call, so this number has to keep corresponding to that one call.
    cost: int
    trigger: str        # "scheduled" | "refresh" | "bootstrap" | "manual" | "desk"
    detail: str
    # The slot this firing was planned for, or None on a bootstrap -- which has
    # no cluster to aim at, by definition. Carried so the prop fetch can buy
    # for the fixtures the sweep was fired for rather than for the whole slate.
    slot: Optional[SweepSlot] = None
    # Team sweep plus the prop tail this firing is expected to trigger. The
    # planner reserves against this; nothing spends it directly.
    projected_total_cost: int = 0
    # Fixtures whose player props this firing should buy, named explicitly.
    #
    # Empty on every planned firing, where the fixture set is derived from
    # `slot.covers` -- the predicate that produced the slot's published
    # `games_covered`, so the buy and the reservation cannot disagree. A MANUAL
    # firing has no slot to derive from and names its one fixture here instead.
    #
    # **Naming them is what makes the prop buy safe.** `fetch_and_store_props`
    # refuses a firing with neither a slot nor a named set, because the
    # remaining option -- buy props for whatever the slate returned -- is what
    # spent 384 of 400 credits in a single pass on 2026-08-15.
    prop_event_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ManualRefresh:
    """One tap, as `decide_sweeps` needs to see it.

    Deliberately not `ondemand.RefreshRequest`, which is what the API writes and
    the runner reads. That type knows about files, TTLs and cooldowns; this
    module knows about credits and kickoffs, and it imports nothing from there.
    The runner converts between them, which is also the layer that can decide a
    request is too old to serve.
    """

    sport_key: str
    # `None` buys team lines only. Set additionally buys that one fixture's
    # player props, which is the expensive half.
    odds_event_id: Optional[str] = None


def _prop_ids(request: ManualRefresh) -> tuple[str, ...]:
    """The fixture set a tap authorises props for: exactly one, or none.

    Written once rather than inlined at its three call sites, because those
    three are a dedupe key, a cost decision and a spend instruction -- and the
    2026-08-15 outage is what happens when the set that is *reserved for* and
    the set that is *bought* stop being the same expression.
    """
    return (request.odds_event_id,) if request.odds_event_id else ()


@dataclass(frozen=True)
class SweepDecision:
    """What this pass decided about odds credits, including deciding nothing.

    `detail` is populated whether or not anything fires. A pass that skips the
    sweep and says nothing is indistinguishable from a pass that swept and found
    an empty slate, and the two need completely different responses.
    """

    fire: tuple[FiringSweep, ...]
    slots_planned: tuple[SweepSlot, ...]
    sweeps_remaining: int
    detail: str


def decide_sweeps(
    conn,
    *,
    in_scope: Mapping[str, int],
    budget,
    cost: int,
    now_ms: int,
    max_odds_age_ms: int,
    horizon_ms: int = DEFAULT_HORIZON_MS,
    prop_cost_per_event: int = 0,
    prop_sports: Collection[str] = (),
    allow_bootstrap: bool = True,
    manual: Sequence[ManualRefresh] = (),
    desk_window: Optional[tuple[int, int]] = None,
) -> SweepDecision:
    """Whether to spend an odds credit on this pass, and on what.

    `in_scope` maps sport key -> soonest **Kalshi** kickoff, which is what
    discovery gives us. It is used only to rank bootstrap candidates and to
    apply the horizon; a constant three-hour offset does not change an ordering,
    and the offset is deliberately not subtracted anywhere -- see
    `tasks/lessons.md`. Every *timing* decision below anchors on the
    sportsbook's own kickoff instead.

    Three triggers, and they answer different questions:

    **Scheduled** — the pass has landed inside a planned slot and that slot has
    not been bought yet, so this call *opens* its window. The normal path, and
    the only trigger that buys player props.

    **Refresh** — the slot is still due and its odds are older than
    `refresh_interval_ms`, so this call *keeps the window open*. This is the
    whole of option A: without it a cluster got one buy, the screen was usable
    for `max_odds_age_ms`, and every row priced afterwards was suppressed as
    `stale_odds` with the games still an hour away. `stale_odds` was 256 of 265
    suppressions in 24h on the live instance, and the cause was never the
    threshold -- it was that nothing re-bought.

    **Manual** — a person tapped refresh. Passed in via `manual`; this function
    never produces one and cannot predict one. It fires whatever the schedule
    thinks, because the schedule's answer is exactly what the tap disagrees
    with: a slate two hours from first pitch is correctly outside every planned
    slot and correctly struck through, and the person looking at it still wants
    a price.

    **What a tap must never do is take a window's opening call.** A manual
    firing gets `slot=None` and stamps `api_credits.trigger = 'manual'`, which
    `_SERVED_SWEEP` excludes -- so `last_sweep_by_sport` does not move and
    `firing_for_slot` still returns `SCHEDULED` when the slot opens. Without
    that, one tap in the seconds before a window opened would demote the
    opening call to a `REFRESH`, and **props ride the opening call only**.

    **Bootstrap** — a sport Kalshi lists has *no stored sportsbook fixtures at
    all*, so there is nothing to schedule against and nothing can be priced for
    it. Holding out for a good moment would mean recording no evidence for that
    sport at all today, and an empty record is a worse outcome than a
    badly-timed sweep. Capped at one sport per pass, and at one attempt per
    sport per budget day: a sport the sportsbook simply does not cover would
    otherwise bootstrap on every pass and drain the day's credits in an hour.

    The budget day comes from `budget.day_start_ms`, never recomputed here.
    "How much is left today" and "has this sport already been swept today" must
    mean the same day, and two implementations of one boundary is how they stop
    meaning that.

    **The planner prices the prop tail it authorises, and that is not
    decoration.** Until 2026-08-15 this function sized the whole day on the
    *team* sweep cost alone -- `remaining_today // cost`, with `cost` 6 -- while
    every scheduled firing also triggered `fetch_and_store_props`, billed
    per event per market key per region. It authorised a 6-credit call that
    spent 384. Restricting the prop fetch to the slot's own fixtures fixes the
    *symptom*; without this reservation the next limit binds in silence, because
    a three-hour coverage window on a full evening slate covers 12-15 games, not
    four, and `6 + 20x15` is 306 a firing.

    `prop_cost_per_event` is the caller's `sweep_cost(prop_markets, regions)`;
    `prop_sports` names the sports a prop ladder was actually discovered for, so
    a league with no ladder is not charged for one. The reservation uses
    `slot.games_covered`, which is an **upper bound** on the events the fetch
    will buy -- some covered fixtures have no Kalshi ladder, and the fetch drops
    any that started. Over-reserving refuses a sweep that would have fit; the
    error the other way is the outage this exists to prevent.

    **The refresh tail is reserved on the same principle as the prop tail**, via
    `SweepSlot.calls_remaining`. A slot no longer costs one call, and a planner
    that priced it at one would authorise windows it could not sustain: it would
    open the screen for the evening's first cluster, spend the day keeping it
    open, and leave the later clusters dark with nothing recording that the
    earlier ones had eaten them. Reserving the tail means a slot is either
    opened and held or not opened, never opened and abandoned.

    `allow_bootstrap` is `False` on the quote cadence. A bootstrap has no slot
    and therefore no refresh interval to pace it -- its only cap is one attempt
    per sport per budget day -- so on a 15s cadence it would fire once per pass
    for every uncovered sport until the day's sports were exhausted, within a
    couple of minutes of a restart. The full pass every 900s is where bootstrap
    belongs, and it is not time-critical by construction: a sport with no stored
    fixtures has nothing to be timely about.

    **Desk** -- the configured desk window is open, so every sport with stored
    upcoming fixtures is kept priced on the same `refresh_interval_ms` cadence
    a slot's rolling refresh uses, whether or not a kickoff cluster is near.
    `desk_window` is `(start_hour, end_hour)` UTC, `None` disables (the
    default, so the demo and every existing caller are unchanged). The slot
    design alone targets the closing line, which left the slate 89%
    `stale_odds` for ~14 hours a day with the budget untouched (measured
    2026-08-23); the desk trigger is what makes the screen a betting desk
    rather than only an evidence recorder (ADR 0062). Three deliberate bounds:

    - **A due slot owns its sport.** While a slot for the sport is due, the
      desk stands aside; the slot's own SCHEDULED/REFRESH logic fires on the
      identical cadence, and standing aside keeps the desk from ever taking a
      window's opening call (props ride the opening call only). A desk buy can
      land no later than `fire_from_ms`, so `firing_for_slot` still reads the
      slot as unopened and SCHEDULED survives.
    - **Never props.** A desk buy is the team sweep alone -- `cost`, not a
      projected tail -- so the worst case is arithmetic that can be stated in
      the deploy file: sports x `sweep_cost` x window hours x 6/hour. At the
      deployed 2 credits and a 12-hour window that is 288/day for two sports,
      576 for four, against a 600/day cap and a 20,000 monthly plan.
    - **Charged from the same `credits_left` as everything else**, refused by
      name when short. A second spend path beside the planner is the shape of
      every credit accident in this file's history.
    """
    state = budget.state(now_ms)
    remaining = max(0, state.remaining_today // max(1, cost))
    start_ms = budget.day_start_ms(now_ms)
    last_sweeps = last_sweep_by_sport(conn, since_ms=start_ms)
    fixtures = upcoming_fixtures_by_sport(conn, now_ms=now_ms, horizon_ms=horizon_ms)
    refresh_ms = refresh_interval_ms(max_odds_age_ms)

    slots = plan_sweep_slots(
        fixtures,
        now_ms=now_ms,
        slots_available=remaining,
        max_odds_age_ms=max_odds_age_ms,
        horizon_ms=horizon_ms,
    )

    if remaining == 0:
        return SweepDecision(
            fire=(),
            slots_planned=tuple(slots),
            sweeps_remaining=0,
            detail=(
                f"no sweep: {state.spent_today} of {state.daily_budget} credits "
                f"spent since {_hhmm(start_ms)}Z, which is not enough for "
                f"another {cost}-credit call"
            ),
        )

    firing: list[FiringSweep] = []
    # Credits, not sweeps. `remaining` above counts team calls and is what
    # `plan_sweep_slots` needs; this is what the day can actually afford once
    # the prop tail is counted, and the two must not be conflated.
    credits_left = state.remaining_today
    refused_for_cost: list[str] = []

    # Taps first, and **held out of the `remaining` truncation below**. That
    # truncation is a cap on how many *planned* sweeps one pass may open; a tap
    # is not planned, is already charged against `credits_left` here, and has a
    # person waiting on it. Dropping one silently to stay under a slot count
    # would be a refusal with no reader.
    manual_firing: list[FiringSweep] = []
    for request in manual:
        if any(
            f.sport_key == request.sport_key
            and f.prop_event_ids == _prop_ids(request)
            for f in manual_firing
        ):
            # The same tap twice in one pass. The cooldown in `ondemand.submit`
            # is what normally prevents this; deduping here as well means a
            # future caller that assembles the list differently cannot bill the
            # same request twice.
            continue
        prop_tail = (
            prop_cost_per_event
            if request.odds_event_id and request.sport_key in prop_sports
            else 0
        )
        total = cost + prop_tail
        if total > credits_left:
            refused_for_cost.append(
                f"{request.sport_key} refresh requested by hand cannot be "
                f"served: {total} credits"
                + (f" ({cost} sweep + {prop_tail} props)" if prop_tail else "")
                + f" and {credits_left} remain"
            )
            continue
        credits_left -= total
        manual_firing.append(
            FiringSweep(
                sport_key=request.sport_key,
                cost=cost,
                trigger=MANUAL,
                detail=(
                    f"refresh requested by hand"
                    + (
                        f", including player props for fixture "
                        f"{request.odds_event_id}"
                        if request.odds_event_id
                        else ""
                    )
                ),
                # No slot, deliberately. A tap is not an opening call and must
                # not be recorded as one -- see this function's docstring, and
                # `_SERVED_SWEEP`, which is the half that actually enforces it.
                slot=None,
                projected_total_cost=total,
                prop_event_ids=_prop_ids(request),
            )
        )

    bootstrap_candidates = sorted(
        (
            (commence, sport)
            for sport, commence in in_scope.items()
            if sport not in fixtures
            and sport not in last_sweeps
            # A tap on this pass is already buying this sport's slate, and a
            # bootstrap right behind it would buy the same thing again. The
            # `sport not in last_sweeps` clause cannot catch it: the tap's
            # credit row is `trigger = 'manual'`, which `_SERVED_SWEEP`
            # excludes by design.
            and not any(f.sport_key == sport for f in manual_firing)
            and commence - now_ms <= horizon_ms
        )
    ) if allow_bootstrap else []
    if bootstrap_candidates:
        _, sport = bootstrap_candidates[0]
        # No slot, so no props are bought and none is reserved. See
        # `runner.fetch_and_store_props`, which refuses on the same grounds.
        firing.append(
            FiringSweep(
                sport_key=sport,
                cost=cost,
                trigger=BOOTSTRAP,
                detail=(
                    f"{sport} has no stored sportsbook fixtures, so nothing "
                    f"about it can be priced or scheduled"
                ),
                slot=None,
                projected_total_cost=cost,
            )
        )
        credits_left -= cost

    for slot in slots:
        if len(firing) >= remaining:
            break
        # `manual_firing` included, so a slot is not bought a second time on a
        # pass a tap already bought it. What that costs is a 15-second delay to
        # the window's opening `SCHEDULED` call -- not its loss, because the
        # tap left `last_sweeps` untouched and `firing_for_slot` will still say
        # `SCHEDULED` on the next pass.
        if any(f.sport_key == slot.sport_key for f in (*manual_firing, *firing)):
            continue
        trigger = firing_for_slot(
            slot,
            now_ms=now_ms,
            last_sweep_ms=last_sweeps.get(slot.sport_key),
            refresh_interval_ms=refresh_ms,
        )
        if trigger is None:
            continue
        # Props ride the *opening* call only. A refresh re-buys the team lines
        # that keep the window alive and nothing else; see `SCHEDULED`.
        prop_tail = (
            prop_cost_per_event * slot.games_covered
            if trigger == SCHEDULED and slot.sport_key in prop_sports
            else 0
        )
        calls = slot.calls_remaining(now_ms, refresh_ms)
        projected = cost * calls + prop_tail
        # What *this* call spends, as against what the whole window will.
        opening = cost + prop_tail
        if opening > credits_left:
            # Refused, and named. A firing dropped for cost is a different state
            # from one that was never due, and the two read identically unless
            # this says so. The call count is named too: "needs 36 credits" on a
            # 6-credit sweep is otherwise unreadable, and the reader's next
            # question is always which of the two tails was responsible.
            refused_for_cost.append(
                f"{slot.sport_key} cannot afford even to open: {opening} credits "
                f"({cost} sweep"
                + (
                    f" + {prop_tail} props for {slot.games_covered} covered game(s)"
                    if prop_tail
                    else ""
                )
                + f") and {credits_left} remain"
            )
            continue
        # **The gate is one call, not the whole tail, and that asymmetry is
        # deliberate.** Reserving the tail is right; *refusing* on it is not.
        # Each call independently buys a usable `max_odds_age_ms` of window, so
        # a slot that can be held for twenty of its sixty minutes is strictly
        # better than a slot not opened -- and "not opened" is exactly the
        # all-day state this change exists to end. The prop tail refuses instead
        # because it is a 20x multiplier discovered at spend time that can empty
        # the day in one pass; a refresh tail is 6 credits paced ten minutes
        # apart and drains gradually, which `remaining == 0` already catches.
        #
        # So: hold the tail against other sports on this pass, spend one call,
        # and say plainly when the window is being opened short.
        held = min(projected, credits_left)
        credits_left -= held
        short_by = projected - held
        firing.append(
            FiringSweep(
                sport_key=slot.sport_key,
                cost=cost,
                trigger=trigger,
                detail=(
                    (
                        slot.reason
                        if trigger == SCHEDULED
                        else f"{slot.reason}; holding the window open"
                    )
                    + (
                        ""
                        if not short_by
                        else (
                            f"; NOTE the day is {short_by} credits short of "
                            f"holding this window to {_hhmm(slot.fire_until_ms)}Z, "
                            f"so it will shut early"
                        )
                    )
                ),
                slot=slot,
                projected_total_cost=projected,
            )
        )

    if desk_window is not None and desk_window_contains(
        now_ms, start_hour=desk_window[0], end_hour=desk_window[1]
    ):
        for sport_key in sorted(fixtures):
            if len(firing) >= remaining:
                break
            if any(
                f.sport_key == sport_key for f in (*manual_firing, *firing)
            ):
                continue
            if any(
                s.sport_key == sport_key and s.is_due(now_ms) for s in slots
            ):
                # The slot owns this sport while it is due -- see the
                # docstring. Firing here as well would double-buy the same
                # cadence and could take the opening call props ride on.
                continue
            last = last_sweeps.get(sport_key)
            if last is not None and now_ms - last < refresh_ms:
                continue
            if cost > credits_left:
                refused_for_cost.append(
                    f"{sport_key} desk refresh cannot be served: {cost} "
                    f"credits and {credits_left} remain"
                )
                continue
            credits_left -= cost
            firing.append(
                FiringSweep(
                    sport_key=sport_key,
                    cost=cost,
                    trigger=DESK,
                    detail=(
                        f"desk window "
                        f"{desk_window[0]:02d}:00Z-{desk_window[1]:02d}:00Z "
                        f"is open; re-buying so the slate stays priced "
                        f"between kickoff windows"
                    ),
                    # No slot and no props, by design: the desk buy is the
                    # team sweep alone, and `fetch_and_store_props` refuses a
                    # firing with neither a slot nor a named fixture set.
                    slot=None,
                    projected_total_cost=cost,
                )
            )

    # Taps are prepended after the cap, not before it: `remaining` bounds how
    # many planned sweeps a pass opens, and a tap is not one of those.
    #
    # **Belt-and-braces, and the record should say so rather than imply a guard
    # that fires.** `remaining` is `remaining_today // cost` and every manual
    # firing spends at least `cost` from that same pool, so
    # `len(manual_firing) <= remaining` holds by arithmetic and this slice could
    # never have truncated a tap. Capping them here as well was mutated in
    # deliberately and no test moved. Written this way because it states the
    # intent at the point a future reader changes the cap -- not because the cap
    # is currently capable of eating a tap.
    firing = [*manual_firing, *firing[:remaining]]

    if firing:
        detail = "; ".join(f"{f.sport_key} ({f.trigger}): {f.detail}" for f in firing)
        if refused_for_cost:
            detail += "; also refused: " + "; ".join(refused_for_cost)
    elif refused_for_cost:
        # Checked before `slots`, because a slot refused for cost IS a planned
        # slot: reporting "next slot is ..." here would describe a sweep that
        # was considered and declined as one that has not come round yet.
        detail = "no sweep: " + "; ".join(refused_for_cost)
    elif slots:
        nxt = slots[0]
        if nxt.is_due(now_ms):
            # Due but not fired, which under the rolling refresh means exactly
            # one thing: its odds are still inside `refresh_interval_ms`. Saying
            # "next slot is 18:00Z-19:00Z" at 18:30Z would describe an open
            # window as one that has not started, and that is the reading that
            # makes a working refresh look like a stalled scheduler.
            last = last_sweeps.get(nxt.sport_key)
            due_at = (last or now_ms) + refresh_ms
            detail = (
                f"no sweep: {nxt.sport_key}'s window is open and its odds are "
                f"{((now_ms - last) / 60000) if last else 0:.1f}min old; next "
                f"refresh at {_hhmm(due_at)}Z (every {refresh_ms // 60000}min "
                f"until {_hhmm(nxt.fire_until_ms)}Z)"
            )
        else:
            detail = (
                f"no sweep: next slot is {nxt.sport_key} at "
                f"{_hhmm(nxt.fire_from_ms)}Z-{_hhmm(nxt.fire_until_ms)}Z for "
                f"{nxt.reason}"
            )
    elif not fixtures:
        detail = (
            "no sweep: no stored sportsbook fixtures inside the horizon, and "
            "no sport is eligible to bootstrap"
        )
    else:
        detail = (
            "no sweep: every kickoff inside the horizon is either already "
            "served or too close to open a pre-game window"
        )

    if not firing and desk_window is not None and fixtures:
        start_hour, end_hour = desk_window
        if start_hour != end_hour and not desk_window_contains(
            now_ms, start_hour=start_hour, end_hour=end_hour
        ):
            # A closed desk is part of why nothing fired, and saying when it
            # reopens is the same honesty `window_status` gives the screen.
            detail += (
                f"; the desk window ({start_hour:02d}:00Z-{end_hour:02d}:00Z) "
                f"reopens at "
                f"{_hhmm(next_desk_open_ms(now_ms, start_hour=start_hour, end_hour=end_hour))}Z"
            )

    return SweepDecision(
        fire=tuple(firing),
        slots_planned=tuple(slots),
        sweeps_remaining=remaining,
        detail=detail,
    )


def sweep_window_survives_interval(
    interval_s: float, *, jitter: float, due_window_ms: int = DUE_WINDOW_MS
) -> bool:
    """Whether a loop on `interval_s` can be relied on to land inside a slot.

    Two limits on one quantity, in two modules that do not import each other:
    the slot is due for `due_window_ms`, and the loop looks every
    `interval_s * (1 + jitter)` in the worst case. If the second exceeds the
    first, sweeps are missed — and a missed sweep is indistinguishable from a
    quiet slate, which is the failure mode this whole file exists to remove.

    Checked at startup rather than asserted in a test alone, because the
    interval is a command-line argument and a test cannot see it.
    """
    worst_case_gap_ms = interval_s * (1.0 + jitter) * 1000.0
    return worst_case_gap_ms < due_window_ms
