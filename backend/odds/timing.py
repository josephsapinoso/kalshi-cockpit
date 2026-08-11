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
cadence is what closes that; see `docs/adr/0004-two-polling-cadences.md`. This
module still decides *when* the fifteen minutes happen and has no opinion about
the quote.

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
cents and the fee advantage is 0.38 points.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping, Optional, Sequence

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
DUE_WINDOW_MS = 30 * _MS_PER_MIN

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
SLATE_WINDOW_MS = DUE_WINDOW_MS

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


@dataclass(frozen=True)
class SweepSlot:
    """One planned sweep: a sport, and the kickoff cluster it is aimed at."""

    sport_key: str
    # The first kickoff of the cluster. The window closes before this.
    anchor_commence_ms: int
    # Games this slot makes bettable: kicking off after the window closes and
    # within `COVERAGE_MS` of the anchor.
    games_covered: int
    fire_from_ms: int
    fire_until_ms: int

    def is_due(self, now_ms: int) -> bool:
        return self.fire_from_ms <= now_ms <= self.fire_until_ms

    @property
    def minutes_before_kickoff(self) -> float:
        """Lead time at the *end* of the due window -- the tightest case."""
        return (self.anchor_commence_ms - self.fire_until_ms) / _MS_PER_MIN

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
            1 for c in future if fire_until <= c <= anchor + coverage_ms
        )
        slots.append(
            SweepSlot(
                sport_key=sport_key,
                anchor_commence_ms=anchor,
                games_covered=covered,
                fire_from_ms=fire_from,
                fire_until_ms=fire_until,
            )
        )
    return slots


def plan_sweep_slots(
    fixtures_by_sport: Mapping[str, Sequence[int]],
    *,
    now_ms: int,
    slots_available: int,
    max_odds_age_ms: int,
    last_sweep_ms_by_sport: Optional[Mapping[str, Optional[int]]] = None,
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

    A slot already served — an `/odds` call for that sport at or after its
    `fire_from_ms` — is dropped, so a pass twelve minutes after a successful
    sweep does not spend a second credit on the same cluster. That check reads
    from recorded spend rather than process memory, so a restart mid-window
    cannot double-spend.
    """
    served = last_sweep_ms_by_sport or {}

    candidates: list[SweepSlot] = []
    for sport_key, commences in fixtures_by_sport.items():
        for slot in slots_for_sport(
            sport_key,
            commences,
            now_ms=now_ms,
            max_odds_age_ms=max_odds_age_ms,
            due_window_ms=due_window_ms,
            horizon_ms=horizon_ms,
        ):
            last = served.get(sport_key)
            if last is not None and last >= slot.fire_from_ms:
                continue
            candidates.append(slot)

    candidates.sort(key=lambda s: (-s.games_covered, s.anchor_commence_ms))

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
_SERVED_SWEEP = "endpoint LIKE '%/odds' AND cost > 0"


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
            "next_sweep_ms": (
                self.next_slot.fire_from_ms if self.next_slot else None
            ),
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
) -> ActionableWindow:
    """The window, and the next planned sweep, from stored state alone.

    Shares `plan_sweep_slots` with the runner rather than reimplementing the
    schedule for display. A screen and a control that compute the same thing by
    two paths eventually disagree, and the one people act on is the screen.
    """
    state = budget.state(now_ms)
    remaining_sweeps = max(0, state.remaining_today // max(1, sweep_cost))
    start_ms = budget.day_start_ms(now_ms)

    ages = fixture_freshness(conn, now_ms=now_ms)
    fresh = [a for a in ages if a <= max_odds_age_ms]
    open_until = now_ms + (max_odds_age_ms - min(fresh)) if fresh else None

    slots = plan_sweep_slots(
        upcoming_fixtures_by_sport(conn, now_ms=now_ms, horizon_ms=horizon_ms),
        now_ms=now_ms,
        slots_available=remaining_sweeps,
        max_odds_age_ms=max_odds_age_ms,
        last_sweep_ms_by_sport=last_sweep_by_sport(conn, since_ms=start_ms),
        horizon_ms=horizon_ms,
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
        next_slot=slots[0] if slots else None,
        slots_planned=tuple(slots),
        sweeps_remaining_today=remaining_sweeps,
        spent_today=state.spent_today,
        daily_budget=state.daily_budget,
        budget_day_start_ms=start_ms,
        last_look_ms=int(look["pass_ms"]) if look else None,
        last_look_outcome=look["outcome"] if look else None,
        last_look_detail=look["detail"] if look else None,
    )


# ---------------------------------------------------------------------------
# The decision a pass actually makes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FiringSweep:
    """One sweep this pass will spend credits on."""

    sport_key: str
    cost: int
    trigger: str        # "scheduled" | "bootstrap"
    detail: str


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
) -> SweepDecision:
    """Whether to spend an odds credit on this pass, and on what.

    `in_scope` maps sport key -> soonest **Kalshi** kickoff, which is what
    discovery gives us. It is used only to rank bootstrap candidates and to
    apply the horizon; a constant three-hour offset does not change an ordering,
    and the offset is deliberately not subtracted anywhere -- see
    `tasks/lessons.md`. Every *timing* decision below anchors on the
    sportsbook's own kickoff instead.

    Two triggers, and they answer different questions:

    **Scheduled** — the pass has landed inside a planned slot, so the window it
    opens will sit just before a cluster of kickoffs. This is the normal path.

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
    """
    state = budget.state(now_ms)
    remaining = max(0, state.remaining_today // max(1, cost))
    start_ms = budget.day_start_ms(now_ms)
    last_sweeps = last_sweep_by_sport(conn, since_ms=start_ms)
    fixtures = upcoming_fixtures_by_sport(conn, now_ms=now_ms, horizon_ms=horizon_ms)

    slots = plan_sweep_slots(
        fixtures,
        now_ms=now_ms,
        slots_available=remaining,
        max_odds_age_ms=max_odds_age_ms,
        last_sweep_ms_by_sport=last_sweeps,
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

    bootstrap_candidates = sorted(
        (
            (commence, sport)
            for sport, commence in in_scope.items()
            if sport not in fixtures
            and sport not in last_sweeps
            and commence - now_ms <= horizon_ms
        )
    )
    if bootstrap_candidates:
        _, sport = bootstrap_candidates[0]
        firing.append(
            FiringSweep(
                sport_key=sport,
                cost=cost,
                trigger="bootstrap",
                detail=(
                    f"{sport} has no stored sportsbook fixtures, so nothing "
                    f"about it can be priced or scheduled"
                ),
            )
        )

    for slot in slots:
        if len(firing) >= remaining:
            break
        if not slot.is_due(now_ms):
            continue
        if any(f.sport_key == slot.sport_key for f in firing):
            continue
        firing.append(
            FiringSweep(
                sport_key=slot.sport_key,
                cost=cost,
                trigger="scheduled",
                detail=slot.reason,
            )
        )

    firing = firing[:remaining]

    if firing:
        detail = "; ".join(f"{f.sport_key} ({f.trigger}): {f.detail}" for f in firing)
    elif slots:
        nxt = slots[0]
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
