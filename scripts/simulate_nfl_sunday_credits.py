"""What one NFL budget day asks the Odds API for. ZERO CREDITS -- reads a fixture.

    .venv\\Scripts\\python.exe scripts/simulate_nfl_sunday_credits.py
    .venv\\Scripts\\python.exe scripts/simulate_nfl_sunday_credits.py --all-days

Drives the **real** planner (`backend/odds/timing.plan_sweep_slots`) over the
**real** season schedule captured in `tests/fixtures/odds_nfl_h2h_spreads.json`,
and counts the calls one NFL budget day generates from the two scheduled
spenders: the kickoff-window loop and the hourly floor.

**This is a simulation of what the code will ASK FOR, not a measurement of what
a day costs.** It is exact about the planner's own arithmetic and silent about
everything the network does. Not modelled, and each one can only add: retries,
429s, a `fetch_odds` returning `[]` (which re-triggers bootstrap), partial
slates, flex-schedule changes after the capture date, and **attention** -- which
is a separate spender with its own 300-credit slice.

**Why the floor and the window interact rather than add.** The floor's cadence
is measured from `last_sweep_by_sport`, which counts *every* buy including the
window's. So an hour containing a window refresh takes no additional floor call.
Adding the two terms independently overstates the day; this walks the clock
instead.

**Why the budget day is 10:00Z-anchored and it matters here.** A Sunday-night
kickoff at 00:20Z lands on the *same* budget day as the 17:00Z games, so all of
that Sunday's clusters are charged against one 700-credit cap rather than split
across two. That is the "convergence" the whole question is about.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.odds.timing import (  # noqa: E402
    DESK_FLOOR_HORIZON_MS,
    DUE_WINDOW_MS,
    plan_sweep_slots,
    refresh_interval_ms,
)

FIXTURE = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "odds_nfl_h2h_spreads.json"
)
SPORT = "americanfootball_nfl"
MAX_ODDS_AGE_MS = 900_000  # MAX_ODDS_AGE_S = 900 on live
SWEEP_COST = 4  # len(ODDS_MARKETS=h2h,spreads) x len(ODDS_REGIONS=us,eu)
DAY_MS = 86_400_000
DAY_START_HOUR_MS = 10 * 3_600_000  # the budget day rolls at 10:00Z
HOUR_MS = 3_600_000
STEP_MS = 60_000


def _ms(iso: str) -> int:
    return int(dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def _iso(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%m-%d %H:%MZ")


def _budget_day(ms: int) -> int:
    return (ms - DAY_START_HOUR_MS) // DAY_MS


def kickoffs() -> list[int]:
    events = json.loads(FIXTURE.read_text(encoding="utf-8"))["events"]
    return sorted(_ms(e["commence_time"]) for e in events)


def simulate_day(day_index: int, season: list[int]) -> dict:
    """Walk one budget day a minute at a time and count the calls it asks for.

    Two spenders, in the order the loop applies them:

    1. **Window.** A planned slot is due between `fire_from_ms` and
       `fire_until_ms`; inside that hour it buys once on entry and again every
       `refresh_interval_ms`. That is 1 + 6 = 7 calls across a 60-minute window
       at the deployed 600s refresh.
    2. **Floor.** Otherwise, if a fixture is within `DESK_FLOOR_HORIZON_MS`, at
       most one call an hour -- and the hour is measured from the last buy of
       *any* kind, so a window refresh suppresses it.
    """
    start = day_index * DAY_MS + DAY_START_HOUR_MS
    end = start + DAY_MS

    refresh = refresh_interval_ms(MAX_ODDS_AGE_MS)
    last_buy: int | None = None
    window_calls = 0
    floor_calls = 0
    anchors: set[int] = set()

    for now in range(start, end, STEP_MS):
        upcoming = [k for k in season if k > now]
        if not upcoming:
            break

        # Replan every step, because `decide_sweeps` replans every pass. A
        # cluster suppressed by MIN_SLOT_SEPARATION_MS at 10:00Z becomes
        # servable once the competing slot's fire_until passes, and a single
        # up-front plan cannot see that -- it costs a whole cluster on some
        # days and it is not a rounding error.
        slots = plan_sweep_slots(
            {SPORT: season},
            now_ms=now,
            slots_available=999,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        # `is_due` is the production predicate and is called rather than
        # restated. Reimplementing it as `fire_from <= now < fire_until`
        # silently drops the seventh call, which is how this script first
        # published 116 against the 124 already in the record.
        in_window = next((s for s in slots if s.is_due(now)), None)
        if in_window is not None:
            anchors.add(in_window.anchor_commence_ms)
            # Buy on entry, then every refresh interval while the slot is due.
            if last_buy is None or now - last_buy >= refresh:
                window_calls += 1
                last_buy = now
            continue

        if upcoming[0] - now <= DESK_FLOOR_HORIZON_MS:
            if last_buy is None or now - last_buy >= HOUR_MS:
                floor_calls += 1
                last_buy = now

    calls = window_calls + floor_calls
    return {
        "anchors": len(anchors),
        "day": dt.datetime.fromtimestamp(start / 1000, dt.timezone.utc).strftime("%Y-%m-%d"),
        "weekday": dt.datetime.fromtimestamp(start / 1000, dt.timezone.utc).strftime("%a"),
        "games": sum(1 for k in season if start <= k < end),
        "slots": len(anchors),
        "window_calls": window_calls,
        "floor_calls": floor_calls,
        "calls": calls,
        "credits": calls * SWEEP_COST,
        "slot_detail": [_iso(a) for a in sorted(anchors)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate NFL budget-day credit load.")
    parser.add_argument("--all-days", action="store_true", help="every NFL budget day")
    parser.add_argument("--date", default="2026-09-13", help="one budget day, YYYY-MM-DD")
    args = parser.parse_args()

    season = kickoffs()
    print(
        f"window {DUE_WINDOW_MS // 60000}min, refresh "
        f"{refresh_interval_ms(MAX_ODDS_AGE_MS) // 1000}s -> "
        f"{DUE_WINDOW_MS // refresh_interval_ms(MAX_ODDS_AGE_MS) + 1} calls per full window; "
        f"floor horizon {DESK_FLOOR_HORIZON_MS // HOUR_MS}h; cost {SWEEP_COST}/call"
    )
    print()

    days = sorted({_budget_day(k) for k in season})
    if not args.all_days:
        want = _budget_day(_ms(f"{args.date}T12:00:00Z"))
        days = [d for d in days if d == want]
        if not days:
            print(f"no NFL fixtures on budget day {args.date}", file=sys.stderr)
            return 1

    rows = [simulate_day(d, season) for d in days]

    header = f"{'day':<12}{'dow':<5}{'games':>6}{'slots':>6}{'win':>5}{'floor':>6}{'calls':>6}{'credits':>8}"
    print(header)
    print("-" * len(header))
    for r in sorted(rows, key=lambda r: -r["credits"]) if args.all_days else rows:
        print(
            f"{r['day']:<12}{r['weekday']:<5}{r['games']:>6}{r['slots']:>6}"
            f"{r['window_calls']:>5}{r['floor_calls']:>6}{r['calls']:>6}{r['credits']:>8}"
        )

    if not args.all_days:
        print()
        for anchor in rows[0]["slot_detail"]:
            print(f"  cluster anchored on a kickoff at {anchor}")
    else:
        worst = max(rows, key=lambda r: r["credits"])
        print()
        print(f"season worst NFL budget day: {worst['day']} ({worst['weekday']}), "
              f"{worst['credits']} credits over {worst['calls']} calls")
        dist = collections.Counter(r["slots"] for r in rows)
        print(f"slot-count distribution: {dict(sorted(dist.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
