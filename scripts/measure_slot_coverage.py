"""How many of a day's games does the sweep schedule actually make bettable?

`backend/odds/timing.py` decides *when* to spend an odds credit: kickoffs are
clustered, each cluster becomes a candidate slot, and a sweep fires 45-15
minutes before the cluster's first kickoff so the fifteen-minute freshness
window closes before the first pitch. That is a rule about *timing*. Nobody had
measured what it buys in *games*.

A handoff note claimed the live gate "did not accumulate" because the scheduler
leaves most passes with stale odds, citing a ten-hour freeze in which no sweep
fired. That freeze contained **zero kickoffs** -- the first in-scope game that
day was at 16:15Z -- so it was evidence about the calendar, not about the
schedule. Measured properly, the same day's slate generated six slots covering
18 of its 19 games. The claim and its refutation were both one-off readings of
one slate, which is why this is a script and not a paragraph.

The number that matters is **distinct games**, not slots and not the sum of
`SweepSlot.games_covered`. Two slots over the same block of kickoffs cover
overlapping sets, and the live gate counts games -- a game priced twice is one
observation (`tasks/lessons.md`, "one observation recorded thirty times").
Coverage is therefore read off the *same* condition `slots_for_sport` uses when
it fills in `games_covered` -- `fire_until <= kickoff <= anchor + COVERAGE_MS`
-- applied per game and collected into a set.

Nothing here reimplements the schedule. `plan_sweep_slots` is imported and
called, because two implementations of one rule agree until the day they matter
and then the wrong one is the one on screen (`tasks/lessons.md`, "delete one of
the paths").

Kickoffs come from ESPN's public scoreboard API: no key, no auth, and
**critically no Odds API credits**. The odds budget is shared with the live
instance, so a measurement harness that spent one would be taking it out of the
thing being measured.

Run:

    .venv\\Scripts\\python.exe scripts\\measure_slot_coverage.py
    .venv\\Scripts\\python.exe scripts\\measure_slot_coverage.py --date 20261215

Re-run it on a winter slate. Every number below is a property of *one day's*
calendar; August is MLB plus WNBA, December is NFL plus NCAAF plus NBA plus NHL
across four sports whose slots do not compete for the same separation window.

What this does not establish
----------------------------
- **This is the ceiling, not the observed schedule.** The live runner plans
  from `upcoming_fixtures_by_sport`, which reads `odds_snapshots` -- so a sport
  that has never been swept has no stored fixtures, generates **no slots at
  all**, and contributes zero coverage however many games ESPN lists for it.
  This script hands `plan_sweep_slots` every league's fixtures unconditionally.
  The gap between this number and reality is the bootstrap problem, and it is
  measured by looking at the database, not here.
- **It does not establish that the budget affords these slots**, and it cannot
  see the deployed budget at all. Slot selection runs unconstrained
  (`UNCONSTRAINED_SLOTS`), so the answer is what the *schedule* offers. The
  repo default is 16 credits (two sweeps); the **live instance was measured at
  400** on 2026-08-09, which affords the six slots the August slate needs with
  ~11x to spare. Those two numbers disagree, so the line under the headline
  names which one it is quoting and refuses to call either "production's".
- **ESPN's schedule is not the sportsbook's.** A game ESPN lists may not be
  quoted by The Odds API at all -- different fixture universes, different
  postponement handling. A missed game here is missed *if* it was quotable.
- **A future date returns only what ESPN has published.** Measured 2026-08-09,
  `--date 20261215` returns 11 NHL and 2 NCAAF games and **zero NBA**, because
  the 2026-27 NBA schedule was not out yet. That is an empty answer, not a
  quiet slate, and the two are indistinguishable in the output. Re-run a
  forward-dated slate closer to the day before believing its shape.
- **It says nothing about whether a covered game is worth betting.** Coverage
  means odds fresh enough to survive `stale_odds`. Most windows open onto an
  empty Board, which is the expected result of the whole premise.
- **It does not model the fast quote cadence.** A row also needs a Kalshi quote
  under thirty seconds; that limit lives in `runner.run_quote_pass` and is not
  represented here (`tasks/lessons.md`, "two limits on one quantity").
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.kalshi.discovery import IN_SCOPE_LEAGUES, parse_ms  # noqa: E402
from backend.odds.budget import sweep_cost  # noqa: E402
from backend.odds.timing import (  # noqa: E402
    COVERAGE_MS,
    MIN_SLOT_SEPARATION_MS,
    SweepSlot,
    day_start_ms,
    plan_sweep_slots,
)

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
HTTP_TIMEOUT_S = 30.0

# The Odds API sport key -> ESPN's `sport/league` path. Keyed on the *same*
# strings `IN_SCOPE_LEAGUES` maps Kalshi's competition names onto, so a league
# added there without an ESPN path fails
# `test_every_in_scope_league_has_an_espn_scoreboard_path` rather than being
# silently absent from the slate -- which would read as "that sport had no
# games", the failure mode this whole harness exists to remove.
ESPN_SCOREBOARD_PATHS: dict[str, str] = {
    "baseball_mlb": "baseball/mlb",
    "americanfootball_nfl": "football/nfl",
    "americanfootball_ncaaf": "football/college-football",
    "basketball_nba": "basketball/nba",
    "basketball_wnba": "basketball/wnba",
    "icehockey_nhl": "hockey/nhl",
}

# What one `/odds` sweep costs, computed by the same function the runner passes
# to the budget rather than retyped as 6 -- The Odds API charges markets x
# regions, so this changes the moment `.env` does. Defaults mirror
# `backend/config.py` (`ODDS_MARKETS`, `ODDS_REGIONS`); the config itself is not
# imported because it calls `load_dotenv()` and a harness must not read a
# machine's secrets to print a schedule.
SWEEP_COST_CREDITS = sweep_cost(("h2h", "spreads", "totals"), ("us", "eu"))

# The repo *default* for `ODDS_DAILY_CREDIT_BUDGET` -- `backend/config.py` and
# `.env.example` both say 16. It is NOT the deployed value and must never be
# printed as one: the live instance is configured from its own environment and
# this process cannot see it.
#
# The deployed value is **400**, set in `fly.live.toml` and documented in
# `.env.example` six lines above the setting itself -- which stays at the free
# tier deliberately, because that file is the contract for a fresh clone and a
# default assuming a paid plan would drain someone's month on their first run.
#
# Corroborated independently by the instance: the window alert it emitted right
# after the 15:46Z sweep on 2026-08-09 read "65 sweep(s)" left, and
# 400 - 6 = 394, 394 // 6 = 65. Under 16 the same line reads 1, which is what it
# read the day before the change (1, then 0). A count the process computed about
# itself is the only kind this repo trusts about a deployed instance.
#
# Reading 16 off `config.py` and calling it "the deployed budget" understates
# production by 25x and inverts the conclusion -- it makes the budget look like
# the binding constraint when it has ~11x the headroom the slate needs.
DEFAULT_DAILY_CREDITS = 16
LIVE_DAILY_CREDITS = 400

# Matches `SuppressionConfig.max_odds_age_ms`. A slot's window is one of these
# wide and must close this long before the anchor kickoff.
MAX_ODDS_AGE_MS = 900_000

# Effectively unconstrained. Slot selection is greedy under a budget; passing a
# real budget here would measure the budget instead of the schedule, and the
# budget is reported separately.
UNCONSTRAINED_SLOTS = 1_000

_MS_PER_HOUR = 3_600_000

# Separations the sensitivity table walks, deployed value first.
SEPARATION_HOURS: tuple[float, ...] = (2.0, 1.5, 1.0, 0.5)


@dataclass(frozen=True)
class Game:
    """One fixture on the slate. Frozen so a covered *set* is a set of games."""

    sport_key: str
    commence_ms: int
    name: str

    @property
    def hhmm(self) -> str:
        return datetime.fromtimestamp(
            self.commence_ms / 1000, timezone.utc
        ).strftime("%H:%M")


@dataclass(frozen=True)
class Coverage:
    """What one separation setting bought: slots spent, distinct games reached."""

    slots: tuple[SweepSlot, ...]
    covered: frozenset[Game]

    @property
    def credits(self) -> int:
        return len(self.slots) * SWEEP_COST_CREDITS


def parse_scoreboard(sport_key: str, payload: Mapping) -> list[Game]:
    """ESPN's scoreboard payload to kickoffs.

    `date` on the event is the first pitch in ISO-8601 -- ESPN emits it without
    seconds (`2026-08-09T16:15Z`). An event whose date cannot be read is
    dropped and never defaulted, per the never-resolve-to-zero rule: a fixture
    silently placed at the epoch would sit before every slot and read as a
    permanent miss.
    """
    games: list[Game] = []
    for event in payload.get("events") or []:
        commence_ms = parse_ms(event.get("date"))
        if commence_ms is None:
            continue
        name = event.get("shortName") or event.get("name") or "(unnamed)"
        games.append(
            Game(sport_key=sport_key, commence_ms=commence_ms, name=str(name))
        )
    return games


def fetch_slate(
    date_yyyymmdd: str,
    *,
    sport_keys: Optional[Sequence[str]] = None,
    client: Optional[httpx.Client] = None,
) -> list[Game]:
    """Every in-scope league's kickoffs for one date, straight from ESPN.

    Unauthenticated and free. This never touches The Odds API; see the module
    docstring on why that is load-bearing rather than merely tidy.
    """
    keys = list(sport_keys or ESPN_SCOREBOARD_PATHS)
    owned = client is None
    client = client or httpx.Client(timeout=HTTP_TIMEOUT_S)
    try:
        games: list[Game] = []
        for sport_key in keys:
            path = ESPN_SCOREBOARD_PATHS[sport_key]
            response = client.get(
                f"{ESPN_BASE}/{path}/scoreboard", params={"dates": date_yyyymmdd}
            )
            response.raise_for_status()
            games.extend(parse_scoreboard(sport_key, response.json()))
        return games
    finally:
        if owned:
            client.close()


def measure_coverage(
    games: Iterable[Game],
    *,
    now_ms: int,
    min_separation_ms: int = MIN_SLOT_SEPARATION_MS,
    max_odds_age_ms: int = MAX_ODDS_AGE_MS,
    slots_available: int = UNCONSTRAINED_SLOTS,
) -> Coverage:
    """Plan the day's slots, then collect the **distinct** games they reach.

    The coverage condition is `SweepSlot`'s own -- a game is covered when it
    kicks off at or after the slot's window closes and within `COVERAGE_MS` of
    the slot's anchor. Collected into a set rather than summed, so a game two
    slots both reach counts once. Summing `games_covered` across slots
    double-counts exactly the overlap that a looser separation buys, which
    would make loosening look better than it is.
    """
    slate = list(games)
    fixtures: dict[str, list[int]] = {}
    for game in slate:
        fixtures.setdefault(game.sport_key, []).append(game.commence_ms)

    slots = plan_sweep_slots(
        fixtures,
        now_ms=now_ms,
        slots_available=slots_available,
        max_odds_age_ms=max_odds_age_ms,
        min_separation_ms=min_separation_ms,
    )

    covered: set[Game] = set()
    for slot in slots:
        for game in slate:
            if game.sport_key != slot.sport_key:
                continue
            if (
                slot.fire_until_ms
                <= game.commence_ms
                <= slot.anchor_commence_ms + COVERAGE_MS
            ):
                covered.add(game)

    return Coverage(slots=tuple(slots), covered=frozenset(covered))


def planning_anchor_ms(date_yyyymmdd: str) -> int:
    """The instant the day's schedule is planned from: that budget day's start.

    Not "now". Planning from the current instant answers "how many slots are
    *left*", which shrinks through the day and is unusable as a repeatable
    measurement -- run it at 23:00Z and the schedule looks empty because the
    games have started, not because the schedule is bad. Planning from
    `day_start_ms` answers "how many slots did this day *offer*", which is the
    same number whenever it is asked. Noon UTC is passed in only because
    `day_start_ms` rolls the budget day at 10:00Z; any hour after that on the
    requested date gives the identical anchor.
    """
    day = datetime.strptime(date_yyyymmdd, "%Y%m%d").replace(
        hour=12, tzinfo=timezone.utc
    )
    return day_start_ms(int(day.timestamp() * 1000))


def _hhmm(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%H:%M")


def _slate_breakdown(games: Sequence[Game]) -> str:
    counts: dict[str, int] = {}
    for game in games:
        counts[game.sport_key] = counts.get(game.sport_key, 0) + 1
    return ", ".join(
        f"{key.split('_')[-1]} {n}"
        for key, n in sorted(counts.items(), key=lambda kv: -kv[1])
    )


def report(games: Sequence[Game], *, date_yyyymmdd: str, now_ms: int) -> None:
    total = len(games)
    print(f"Planning from {_hhmm(now_ms)}Z on the budget day containing "
          f"{date_yyyymmdd} -- slots the day offered, not slots left from now.")
    if not total:
        print("Slate: 0 games. Nothing to schedule, and that is a fact about "
              "the calendar, not about the scheduler.")
        return

    print(f"Today's slate: {total} games ({_slate_breakdown(games)})")

    base = measure_coverage(games, now_ms=now_ms)
    print(
        f"Slots at the deployed "
        f"{MIN_SLOT_SEPARATION_MS // _MS_PER_HOUR}h separation: {len(base.slots)}"
        f"  ({base.credits} credits)"
    )
    configured = os.environ.get("ODDS_DAILY_CREDIT_BUDGET")
    if configured and configured.isdigit():
        cap, source = int(configured), "this environment"
    else:
        cap, source = DEFAULT_DAILY_CREDITS, "the repo default"
    verdict = (
        "affords them"
        if cap >= base.credits
        else f"buys only {cap // SWEEP_COST_CREDITS} of them"
    )
    print(
        f"  Budget: {cap} credits/day = {cap // SWEEP_COST_CREDITS} sweeps "
        f"({source}), which {verdict}."
    )
    if cap != LIVE_DAILY_CREDITS:
        print(
            f"  NOTE: live runs {LIVE_DAILY_CREDITS}/day "
            f"({LIVE_DAILY_CREDITS // SWEEP_COST_CREDITS} sweeps), per "
            f"fly.live.toml. Do not report the line above as production's."
        )
    for slot in base.slots:
        print(
            f"    {slot.sport_key:<22} fire {_hhmm(slot.fire_from_ms)}-"
            f"{_hhmm(slot.fire_until_ms)}Z  anchor {_hhmm(slot.anchor_commence_ms)}Z"
            f"  covers {slot.games_covered} game(s)"
        )

    print(f"Distinct games covered: {len(base.covered)} of {total}")

    missed = sorted(
        (g for g in games if g not in base.covered), key=lambda g: g.commence_ms
    )
    for game in missed:
        print(f"  MISSED  {game.sport_key:<22} {game.name:<14} {game.hhmm}Z")
    if not missed:
        print("  (nothing missed)")

    print()
    print("What loosening MIN_SLOT_SEPARATION_MS buys:")
    for hours in SEPARATION_HOURS:
        result = measure_coverage(
            games, now_ms=now_ms, min_separation_ms=int(hours * _MS_PER_HOUR)
        )
        extra_sweeps = len(result.slots) - len(base.slots)
        extra_games = len(result.covered) - len(base.covered)
        delta = (
            "  (deployed)"
            if int(hours * _MS_PER_HOUR) == MIN_SLOT_SEPARATION_MS
            else f"  ({extra_sweeps:+d} sweeps, {extra_games:+d} games)"
        )
        print(
            f"  separation {hours:>4}h -> {len(result.slots):2d} sweeps "
            f"({result.credits:3d} credits), {len(result.covered):2d} of "
            f"{total} games{delta}"
        )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--date",
        default=datetime.now(timezone.utc).strftime("%Y%m%d"),
        help="slate to measure, YYYYMMDD in UTC (default: today)",
    )
    parser.add_argument(
        "--sport",
        action="append",
        choices=sorted(ESPN_SCOREBOARD_PATHS),
        help="restrict to these Odds API sport keys (default: all in-scope)",
    )
    args = parser.parse_args(argv)

    print(
        f"Fetching {args.date} from ESPN (free, unauthenticated, zero odds "
        f"credits) ...",
        file=sys.stderr,
    )
    games = fetch_slate(args.date, sport_keys=args.sport)
    report(games, date_yyyymmdd=args.date, now_ms=planning_anchor_ms(args.date))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
