"""Does current-season data rescue the pitcher-K build? Registered 2026-08-17.

The information used here was obtained free of charge from and is copyrighted by
Retrosheet.

Registered in
`docs/measurements/2026-08-17-preregistration-in-season-vs-stale-baseline.md`.
**Nothing here decides anything that file does not already decide.** The
population, the three cuts, the four forecasters, the noise-decomposed primary
statistic and all four verdict branches are fixed there; a disagreement between
the two is a bug in this file.

WHY THE ANSWER MATTERS
----------------------
The previous measurement returned TOO STALE ALONE and its registered branch says
"a current-season blend is required". Acting on that means an MLBAM adapter and
the licence surface ADR 0035 narrowed. **That rests on the untested assumption
that current-season data is materially better.** If it is not, no feed rescues
anything and slice 2 as designed is dead -- which is far cheaper to learn here,
offline, than after an adapter, a cache, a poll schedule and a licence argument.

WHY THE PRIMARY IS NOT A RAW RMSE
---------------------------------
The target is rest-of-season over ~10 starts, ~230 batters faced, whose binomial
standard error is ~0.027 -- comparable to the entire forecast error being
tested. A raw RMSE would be dominated by noise in the target and would rank
every forecaster as equally bad, which is a way of concluding nothing while
appearing to measure. §5 of the registration therefore fixes the *decomposed*
error as primary, and the decomposition is conservative: the binomial form
understates real target variance, so it overstates forecast error, so a
favourable verdict cannot be an artifact of it.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about beating Kalshi.** Kalshi sees the same season-to-date data and
  more. A forecast that is accurate and universally known is worth nothing.
- **It is optimistic about forecaster B.** B is built from complete,
  retrospective data with no ingestion lag, no name-matching failure and no
  missing games. A live feed delivers a worse B than this.
- **Nothing about pitchers with no prior season**, excluded by construction.
- **Nothing about the blend C out of sample.** In-sample by construction and
  reported as an upper bound, never as a verdict.

    .venv\\Scripts\\python.exe scripts/measure_in_season_vs_stale.py --pitching-zip PATH
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

# §2. Fixed in the registration.
MIN_STARTS_BEFORE = 10
MIN_STARTS_AFTER = 5
MIN_STARTS_PRIOR_SEASON = 15

# §3. Primary first; the other two are pre-declared sensitivity and are reported
# whether or not they agree.
PRIMARY_CUT = (7, 31)
SENSITIVITY_CUTS = ((6, 15), (8, 15))

# §6. The registered bars, from ADR 0028. Not chosen for this test.
FEE_BAR_POINTS = 1.75
TOO_STALE_POINTS = 5.00
REPRESENTATIVE_RUNGS = (1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5)


class Start:
    __slots__ = ("month", "day", "bfp", "k")

    def __init__(self, month: int, day: int, bfp: int, k: int) -> None:
        self.month, self.day, self.bfp, self.k = month, day, bfp, k

    def before(self, cut: tuple[int, int]) -> bool:
        return (self.month, self.day) < cut


def load(zip_path: Path) -> dict[tuple[str, int], list[Start]]:
    """§2's population. Unreadable rows are dropped and counted, never coerced."""
    seasons: dict[tuple[str, int], list[Start]] = defaultdict(list)
    kept = dropped_in_window = 0

    with zipfile.ZipFile(zip_path) as archive, archive.open("pitching.csv") as handle:
        for row in csv.DictReader(
            io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
        ):
            if (
                row.get("stattype") != "value"
                or row.get("gametype") != "regular"
                or row.get("p_gs") != "1"
            ):
                continue
            date = row.get("date") or ""
            if len(date) != 8 or not (str(FIRST_SEASON) <= date[:4] <= str(LAST_SEASON)):
                continue
            try:
                bfp, strikeouts = int(row["p_bfp"]), int(row["p_k"])
                if bfp <= 0:
                    raise ValueError
            except (ValueError, TypeError, KeyError):
                dropped_in_window += 1
                continue
            seasons[(row["id"], int(date[:4]))].append(
                Start(int(date[4:6]), int(date[6:8]), bfp, strikeouts)
            )
            kept += 1

    print(f"starts in population {kept + dropped_in_window:,}   kept {kept:,}   "
          f"unreadable {dropped_in_window:,}")
    return dict(seasons)


def rate(starts: list[Start]) -> float:
    return sum(s.k for s in starts) / sum(s.bfp for s in starts)


def rmse(errors: list[float]) -> float:
    return math.sqrt(sum(e * e for e in errors) / len(errors))


def ols(xs: list[float], ys: list[float]) -> tuple[float, float]:
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else 0.0
    return slope, my - slope * mx


def price_points(
    league_bf: float, league_sd: float, league_rate: float, error: float
) -> Optional[tuple[float, float]]:
    """§6's conversion. `None` if either distribution refuses."""
    base = distribution(league_bf, league_sd, league_rate)
    bumped = distribution(league_bf, league_sd, league_rate + error)
    if base is None or bumped is None:
        return None
    moves = [
        abs(bumped.probability_over(s) - base.probability_over(s)) * 100.0
        for s in REPRESENTATIVE_RUNGS
    ]
    return statistics.fmean(moves), max(moves)


def verdict(err_a: float, err_b: float, points_b: float) -> str:
    """§6's table, and only §6's table."""
    if err_b >= err_a:
        return "NO FEED HELPS"
    if points_b > TOO_STALE_POINTS:
        return "NO FEED RESCUES IT"
    if points_b >= FEE_BAR_POINTS:
        return "MARGINAL -- the feed is a judgement call"
    return "BUILD THE FEED"


def run_cut(
    seasons: dict[tuple[str, int], list[Start]],
    cut: tuple[int, int],
    label: str,
) -> None:
    prior_ok = {
        key for key, starts in seasons.items() if len(starts) >= MIN_STARTS_PRIOR_SEASON
    }

    rows = []
    excluded_no_prior = 0
    for (pid, season), starts in seasons.items():
        before = [s for s in starts if s.before(cut)]
        after = [s for s in starts if not s.before(cut)]
        if len(before) < MIN_STARTS_BEFORE or len(after) < MIN_STARTS_AFTER:
            continue
        if (pid, season - 1) not in prior_ok:
            excluded_no_prior += 1
            continue
        rows.append(
            {
                "season": season,
                "A": rate(seasons[(pid, season - 1)]),
                "B": rate(before),
                "T": rate(after),
                "bf_after": sum(s.bfp for s in after),
                "starts_after": len(after),
            }
        )

    print("\n" + "=" * 74)
    print(f"CUT {cut[0]:02d}-{cut[1]:02d}   ({label})")
    print("=" * 74)
    if not rows:
        print("  no qualifying pitcher-seasons -- refusing to report a statistic")
        return

    # §4's benchmark L: the league season-to-date rate at the cut, per season.
    league_std: dict[int, float] = {}
    for season in range(FIRST_SEASON, LAST_SEASON + 1):
        pool = [
            s
            for (_, y), starts in seasons.items()
            if y == season
            for s in starts
            if s.before(cut)
        ]
        if pool:
            league_std[season] = rate(pool)
    for row in rows:
        row["L"] = league_std[row["season"]]

    print(f"  pairs {len(rows):,}   excluded for no qualifying prior season "
          f"{excluded_no_prior:,}")
    median_starts = statistics.median([r["starts_after"] for r in rows])
    median_bf = statistics.median([r["bf_after"] for r in rows])
    print(f"  median starts after the cut {median_starts:.0f}   "
          f"median BF after {median_bf:.0f}")

    # §5: target noise, then the decomposition.
    noise = rmse(
        [math.sqrt(r["T"] * (1 - r["T"]) / r["bf_after"]) for r in rows]
    )

    # §4's C, in-sample and descriptive only.
    slope_b, intercept_b = ols([r["B"] for r in rows], [r["T"] for r in rows])
    ab_slope, _ = ols(
        [r["B"] - r["A"] for r in rows], [r["T"] - r["A"] for r in rows]
    )
    for row in rows:
        row["C"] = row["A"] + ab_slope * (row["B"] - row["A"])

    print(f"\n  target sampling noise {noise:.5f}  "
          f"(subtracted from every raw RMSE below)")
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

    print(f"\n  in-sample blend weight on B: {ab_slope:.4f}   "
          f"(OLS of T-A on B-A)")
    print(f"  OLS of T on B alone: slope {slope_b:.4f} "
          f"intercept {intercept_b:.5f}")

    # §6's conversion, at the league parameters of the last full season.
    ref = [s for (_, y), starts in seasons.items() if y == LAST_SEASON for s in starts]
    league_bf = statistics.fmean([s.bfp for s in ref])
    league_sd = statistics.stdev([s.bfp for s in ref])
    league_rate = rate(ref)

    print(f"\n  price conversion at league {LAST_SEASON}: mean_bf {league_bf:.2f}, "
          f"sd_bf {league_sd:.2f}, k_per_bf {league_rate:.4f}")
    points: dict[str, float] = {}
    for key in ("A", "B", "L", "C"):
        converted = price_points(league_bf, league_sd, league_rate, decomposed[key])
        if converted is None:
            print(f"    {key}: refused")
            continue
        points[key] = converted[0]
        print(f"    {key}  {converted[0]:>5.2f} points mean   "
              f"({converted[1]:>5.2f} max)")

    print(f"\n  bars: fee {FEE_BAR_POINTS} pts, too-stale {TOO_STALE_POINTS} pts")
    print(f"  VERDICT   {verdict(decomposed['A'], decomposed['B'], points['B'])}")

    # The parts, before the aggregate is believed.
    by_season: dict[int, list] = defaultdict(list)
    for row in rows:
        by_season[row["season"]].append(row)
    print(f"\n  per-season (n, forecast err A, forecast err B):")
    for season in sorted(by_season):
        group = by_season[season]
        gn = rmse([math.sqrt(r["T"] * (1 - r["T"]) / r["bf_after"]) for r in group])
        ga = math.sqrt(max(rmse([r["T"] - r["A"] for r in group]) ** 2 - gn**2, 0.0))
        gb = math.sqrt(max(rmse([r["T"] - r["B"] for r in group]) ** 2 - gn**2, 0.0))
        better = "B" if gb < ga else "A"
        print(f"    {season}  n={len(group):>3}   A {ga:.5f}   B {gb:.5f}   "
              f"-> {better}")
    biggest = max(by_season.values(), key=len)
    print(f"    largest contributor {len(biggest)} of {len(rows)} "
          f"({100 * len(biggest) / len(rows):.1f}%)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pitching-zip", type=Path, required=True)
    args = parser.parse_args()

    seasons = load(args.pitching_zip)
    run_cut(seasons, PRIMARY_CUT, "PRIMARY -- registered")
    for cut in SENSITIVITY_CUTS:
        run_cut(seasons, cut, "pre-declared sensitivity, reported either way")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
