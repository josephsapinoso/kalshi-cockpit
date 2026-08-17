"""Is `KXMLBHR` worth building? Scoped against ADR 0036. Registered 2026-08-17.

The information used here was obtained free of charge from and is copyrighted by
Retrosheet.

Registered in
`docs/measurements/2026-08-17-preregistration-home-run-ladder-scope.md`.
**Nothing here decides anything that file does not already decide.** The
population, the `MIN_PA` floor, the August 15 cut, the four forecasters, the
noise-decomposed primary statistic, the `1+` rung and all four verdict branches
are fixed there.

WHY THIS RUNS BEFORE ANY MODEL EXISTS
-------------------------------------
ADR 0036 killed pitcher-K on the parameter, not the model -- the ladder pricer
was correct and the rate could not be pinned. Its closing consequence says
`KXMLBHR` "inherits a harder parameter problem, not an easier one" and must be
scoped **before** it is started. So this asks the question that ended the last
build first, with no adapter, no lineup poll and no ladder pricer written.

§2 of the registration predicts the answer in advance and says why: the `1+`
price moves ~375 points per unit of rate error against ~243 for strikeouts,
while the rate itself is ~6x smaller, so the relative precision required is far
tighter. A 600-PA season carries ~0.0075 of binomial noise against a budget of
~0.0047. **A confirming result is therefore a prediction met, not a story fitted
afterwards.**

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about beating Kalshi.** Forecasters are scored against the batter's
  own future, never against a price.
- **Nothing about lineup slot.** Expected PA is a second parameter, deliberately
  excluded: if the rate alone fails the bar the slot cannot rescue it.
- **Nothing about the live rung set.** No `KXMLBHR` market exists in any local
  database or committed fixture; the `N+` shape is inferred from `KXMLBKS` and
  `KXMLBTB` where it is verified.
- **Nothing about batters with no prior season**, excluded by construction.

    .venv\\Scripts\\python.exe scripts/measure_home_run_ladder_scope.py --batting-zip PATH
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import statistics
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.model.strikeouts import distribution  # noqa: E402

FIRST_SEASON = 2015
LAST_SEASON = 2025

# §3 and §4. Fixed in the registration.
MIN_PA = 300
CUT = (8, 15)
MIN_PA_BEFORE = 200
MIN_PA_AFTER = 60

# §7. ADR 0028's bars. Not chosen for this test.
FEE_BAR_POINTS = 1.75
TOO_STALE_POINTS = 5.00


class Span:
    """Plate appearances and home runs over some set of games."""

    __slots__ = ("pa", "hr", "games")

    def __init__(self) -> None:
        self.pa = self.hr = self.games = 0

    def add(self, pa: int, hr: int) -> None:
        self.pa += pa
        self.hr += hr
        self.games += 1

    @property
    def rate(self) -> float:
        return self.hr / self.pa


def load(zip_path: Path) -> tuple[dict, dict, dict, list[int]]:
    """§3's population, split at §4's cut in one pass over 684MB.

    Returns `(full_season, before_cut, after_cut, pa_per_game)`, each keyed by
    `(batter, season)`. Unreadable rows are dropped and counted, never coerced.
    """
    full: dict[tuple[str, int], Span] = defaultdict(Span)
    before: dict[tuple[str, int], Span] = defaultdict(Span)
    after: dict[tuple[str, int], Span] = defaultdict(Span)
    pa_per_game: list[int] = []
    kept = dropped = 0

    with zipfile.ZipFile(zip_path) as archive, archive.open("batting.csv") as handle:
        for row in csv.DictReader(
            io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
        ):
            if row.get("stattype") != "value" or row.get("gametype") != "regular":
                continue
            date = row.get("date") or ""
            if len(date) != 8 or not (str(FIRST_SEASON) <= date[:4] <= str(LAST_SEASON)):
                continue
            try:
                pa, homers = int(row["b_pa"]), int(row["b_hr"])
                if pa < 0 or homers < 0:
                    raise ValueError
            except (ValueError, TypeError, KeyError):
                dropped += 1
                continue
            if pa == 0:
                # A pinch-runner or defensive replacement. Not unreadable and
                # not an error -- simply no plate appearance to contribute.
                continue
            key = (row["id"], int(date[:4]))
            full[key].add(pa, homers)
            if (int(date[4:6]), int(date[6:8])) < CUT:
                before[key].add(pa, homers)
            else:
                after[key].add(pa, homers)
            pa_per_game.append(pa)
            kept += 1

    print(f"batter-games in population {kept + dropped:,}   kept {kept:,}   "
          f"unreadable {dropped:,}")
    return dict(full), dict(before), dict(after), pa_per_game


def rmse(errors: list[float]) -> float:
    return math.sqrt(sum(e * e for e in errors) / len(errors))


def ols(xs: list[float], ys: list[float]) -> tuple[float, float]:
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else 0.0
    return slope, my - slope * mx


def closed_form_points(mean_pa: float, rate: float, error: float) -> float:
    """§6 method 1: `1 - (1-p)^PA` at the league mean PA, in points."""
    def p_at_least_one(p: float) -> float:
        return 1.0 - (1.0 - p) ** mean_pa
    return abs(p_at_least_one(rate + error) - p_at_least_one(rate)) * 100.0


def compound_points(
    mean_pa: float, sd_pa: float, rate: float, error: float
) -> Optional[tuple[float, float]]:
    """§6 method 2: the same compound binomial `strikeouts.py` implements.

    Returns `(1+ points, 2+ points)` or `None` if either distribution refuses.
    The module's docstring disclaims batters, and correctly -- about its
    discretised-normal *shape* over `PA ~ 4.2`, not about its algebra. §6 makes
    agreement with the closed form the condition for using it at all.
    """
    base = distribution(mean_pa, sd_pa, rate)
    bumped = distribution(mean_pa, sd_pa, rate + error)
    if base is None or bumped is None:
        return None
    return (
        abs(bumped.probability_over(0.5) - base.probability_over(0.5)) * 100.0,
        abs(bumped.probability_over(1.5) - base.probability_over(1.5)) * 100.0,
    )


def verdict(points_b: float, points_c: float) -> str:
    """§7's table, and only §7's table."""
    if points_c > TOO_STALE_POINTS:
        return "REFUTED, HARDER THAN PITCHER-K"
    if points_b > TOO_STALE_POINTS:
        return "REFUTED AS BUILDABLE"
    if points_b >= FEE_BAR_POINTS:
        return "MARGINAL"
    return "BUILD IT"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batting-zip", type=Path, required=True)
    args = parser.parse_args()

    full, before, after, pa_per_game = load(args.batting_zip)

    qualifying = {k: s for k, s in full.items() if s.pa >= MIN_PA}
    print(f"\nbatter-seasons {len(full):,}   qualifying at >={MIN_PA} PA "
          f"{len(qualifying):,}")
    by_season: dict[int, int] = defaultdict(int)
    for (_, season) in qualifying:
        by_season[season] += 1
    print("  qualifying per season: "
          + ", ".join(f"{y}:{by_season[y]}" for y in sorted(by_season)))

    rows = []
    excluded_no_prior = 0
    for key, span in qualifying.items():
        batter, season = key
        pre, post = before.get(key), after.get(key)
        if pre is None or post is None:
            continue
        if pre.pa < MIN_PA_BEFORE or post.pa < MIN_PA_AFTER:
            continue
        prior = qualifying.get((batter, season - 1))
        if prior is None:
            excluded_no_prior += 1
            continue
        rows.append(
            {
                "season": season,
                "A": prior.rate,
                "B": pre.rate,
                "T": post.rate,
                "pa_after": post.pa,
            }
        )

    if not rows:
        print("no pairs -- refusing to report a statistic over an empty set")
        return 1

    # §4's benchmark L: league season-to-date rate at the cut, per season.
    league_std: dict[int, float] = {}
    for season in range(FIRST_SEASON, LAST_SEASON + 1):
        pool = [s for (_, y), s in before.items() if y == season]
        if pool:
            league_std[season] = sum(s.hr for s in pool) / sum(s.pa for s in pool)
    for row in rows:
        row["L"] = league_std[row["season"]]

    print(f"\npairs {len(rows):,}   excluded for no qualifying prior season "
          f"{excluded_no_prior:,}")
    print(f"  median PA after the cut "
          f"{statistics.median([r['pa_after'] for r in rows]):.0f}")

    # §5: target noise, then the decomposition.
    noise = rmse([math.sqrt(r["T"] * (1 - r["T"]) / r["pa_after"]) for r in rows])

    ab_slope, _ = ols(
        [r["B"] - r["A"] for r in rows], [r["T"] - r["A"] for r in rows]
    )
    for row in rows:
        row["C"] = row["A"] + ab_slope * (row["B"] - row["A"])

    print(f"\n  target sampling noise {noise:.5f}  (subtracted below)")
    print(f"\n  {'forecaster':<38} {'raw RMSE':>9}  {'forecast err':>12}")
    decomposed: dict[str, float] = {}
    for key, name in (
        ("A", "A  prior season (Retrosheet only)"),
        ("B", "B  season-to-date (needs a feed)"),
        ("L", "L  league season-to-date"),
        ("C", "C  blend  [IN-SAMPLE, not a verdict]"),
    ):
        raw = rmse([r["T"] - r[key] for r in rows])
        decomposed[key] = math.sqrt(max(raw**2 - noise**2, 0.0))
        print(f"  {name:<38} {raw:>9.5f}  {decomposed[key]:>12.5f}")
    print(f"\n  in-sample blend weight on B: {ab_slope:.4f}")

    # §6: the league parameters, then both conversion methods.
    league_rate = statistics.fmean([r["T"] for r in rows])
    mean_pa = statistics.fmean(pa_per_game)
    sd_pa = statistics.stdev(pa_per_game)
    print(f"\n  league: hr_per_pa {league_rate:.5f}   mean_pa {mean_pa:.3f}   "
          f"sd_pa {sd_pa:.3f}")
    print(f"  §2 predicted the budget as d < 0.0047 for 1.75 points")

    print(f"\n  {'':<4} {'closed form 1+':>15} {'compound 1+':>13} "
          f"{'compound 2+':>13}")
    points: dict[str, float] = {}
    for key in ("A", "B", "L", "C"):
        closed = closed_form_points(mean_pa, league_rate, decomposed[key])
        comp = compound_points(mean_pa, sd_pa, league_rate, decomposed[key])
        points[key] = closed
        if comp is None:
            print(f"  {key:<4} {closed:>14.2f}p {'refused':>13}")
            continue
        print(f"  {key:<4} {closed:>14.2f}p {comp[0]:>12.2f}p {comp[1]:>12.2f}p")

    # §6: agreement is the condition for using the compound at all.
    check = compound_points(mean_pa, sd_pa, league_rate, decomposed["B"])
    if check is not None:
        gap = abs(check[0] - points["B"])
        verdict_word = "AGREE" if gap < 0.25 else "DISAGREE -- closed form governs"
        print(f"\n  §6 method check: closed form {points['B']:.2f}p vs compound "
              f"{check[0]:.2f}p -> {verdict_word}")

    print(f"\n  bars: fee {FEE_BAR_POINTS} pts, too-stale {TOO_STALE_POINTS} pts")
    print(f"  ADR 0036 for comparison: pitcher-K B 6.69p, C 6.09p at this cut")
    print(f"\n  VERDICT   {verdict(points['B'], points['C'])}")

    # The parts, before the aggregate is believed.
    grouped: dict[int, list] = defaultdict(list)
    for row in rows:
        grouped[row["season"]].append(row)
    print("\n  per-season (n, forecast err A, forecast err B):")
    for season in sorted(grouped):
        group = grouped[season]
        gn = rmse([math.sqrt(r["T"] * (1 - r["T"]) / r["pa_after"]) for r in group])
        ga = math.sqrt(max(rmse([r["T"] - r["A"] for r in group]) ** 2 - gn**2, 0.0))
        gb = math.sqrt(max(rmse([r["T"] - r["B"] for r in group]) ** 2 - gn**2, 0.0))
        print(f"    {season}  n={len(group):>3}   A {ga:.5f}   B {gb:.5f}   "
              f"-> {'B' if gb < ga else 'A'}")
    biggest = max(grouped.values(), key=len)
    print(f"    largest contributor {len(biggest)} of {len(rows)} "
          f"({100 * len(biggest) / len(rows):.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
