"""How far does a season-old strikeout baseline carry? Registered 2026-08-17.

The information used here was obtained free of charge from and is copyrighted by
Retrosheet.

Registered in
`docs/measurements/2026-08-17-preregistration-pitcher-k-baseline-decay.md`.
**Nothing here decides anything that file does not already decide.** The
population, the `MIN_STARTS` floor, the primary statistic, its benchmark, the
price conversion and all four verdict branches are fixed there; this module is
an implementation of them, and a disagreement between the two is a bug in this
file.

WHY THE ANSWER MATTERS
----------------------
Retrosheet ends at 2025. Every parameter slice 2 hands to
`backend/model/strikeouts.py` is therefore at least a season old, and gets
staler through the year. If a season-old per-pitcher rate carries nothing the
league mean does not, slice 2 as designed is dead and a current-season source is
required -- which re-opens the MLBAM licence surface ADR 0035 narrowed.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about beating Kalshi.** It scores a parameter against the pitcher's
  own future, not a price against a market. Perfect parameters against a ladder
  Kalshi has already priced right is still zero edge.
- **Nothing about pitchers with no history.** A pair needs two qualifying
  seasons, so rookies are excluded by construction -- and they are exactly the
  starters a market is least sure about. Counted, not modelled.
- **It is optimistic about the deployed case.** The gap measured is one season.
  The live gap in August 2026 is one season plus five months.

    .venv\\Scripts\\python.exe scripts/measure_pitcher_k_decay.py --pitching-zip PATH
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

# --- §2 of the registration. Fixed there, restated here, changed in neither. ---
MIN_STARTS = 15
FIRST_SEASON = 2015
LAST_SEASON = 2025

# --- §4. The representative ladder the price conversion is priced over. -------
REPRESENTATIVE_RUNGS = (1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5)

# The registered bar. Not chosen for this test: it is the taker break-even
# advantage from ADR 0028, and a parameter error the size of the whole fee
# advantage cannot be spent on parameter noise.
FEE_BAR_POINTS = 1.75
TOO_STALE_POINTS = 5.0


class Season:
    """One pitcher's one season of starts. §3's unit."""

    __slots__ = ("bfp", "k", "starts")

    def __init__(self) -> None:
        self.bfp: list[int] = []
        self.k = 0
        self.starts = 0

    def add(self, bfp: int, k: int) -> None:
        self.bfp.append(bfp)
        self.k += k
        self.starts += 1

    @property
    def qualifies(self) -> bool:
        return self.starts >= MIN_STARTS

    @property
    def k_per_bf(self) -> float:
        return self.k / sum(self.bfp)

    @property
    def mean_bf(self) -> float:
        return statistics.fmean(self.bfp)

    @property
    def sd_bf(self) -> float:
        return statistics.stdev(self.bfp)


def load(zip_path: Path) -> dict[tuple[str, int], Season]:
    """§2's population, and nothing else.

    Every filter is applied here rather than downstream so that the population
    is one readable block. A row that cannot be read -- a blank `p_bfp`, an
    unparseable date -- is **dropped and counted**, never coerced to zero. The
    repo's rule: unreadable resolves to `None`, and a zero-batters-faced start
    would be a real-looking row that drags every rate down.
    """
    seasons: dict[tuple[str, int], Season] = defaultdict(Season)
    kept = skipped = 0
    # Split deliberately. The first run of this harness printed a single
    # `dropped` counter and it read as a data-quality problem in the
    # population: 6,143 unreadable rows. It is not -- almost all of them are
    # pre-1940 box scores with no `p_bfp` field at all, which the season filter
    # would have removed anyway. **Inside 2015-2025 the figure is 7.** A count
    # that spans a population and its complement describes neither.
    dropped_in_window = dropped_outside = 0

    with zipfile.ZipFile(zip_path) as archive:
        with archive.open("pitching.csv") as handle:
            reader = csv.DictReader(
                io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
            )
            for row in reader:
                if row.get("stattype") != "value":
                    skipped += 1
                    continue
                if row.get("gametype") != "regular":
                    skipped += 1
                    continue
                if row.get("p_gs") != "1":
                    skipped += 1
                    continue
                # The season is parsed first and on its own, so that a row
                # dropped for an unreadable `p_bfp` can be attributed to inside
                # or outside the window rather than to the pile.
                try:
                    season = int(row["date"][:4])
                except (ValueError, TypeError, KeyError):
                    dropped_outside += 1
                    continue
                in_window = FIRST_SEASON <= season <= LAST_SEASON
                try:
                    bfp = int(row["p_bfp"])
                    strikeouts = int(row["p_k"])
                    if bfp <= 0:
                        raise ValueError("a start with no batters faced")
                except (ValueError, TypeError, KeyError):
                    if in_window:
                        dropped_in_window += 1
                    else:
                        dropped_outside += 1
                    continue
                if not in_window:
                    skipped += 1
                    continue
                seasons[(row["id"], season)].add(bfp, strikeouts)
                kept += 1

    total_in_window = kept + dropped_in_window
    print(
        f"starts in population {total_in_window:,}   kept {kept:,}   "
        f"UNREADABLE IN POPULATION {dropped_in_window:,} "
        f"({100 * dropped_in_window / max(total_in_window, 1):.3f}%)"
    )
    print(
        f"  outside the 2015-2025 window: {skipped:,} readable, "
        f"{dropped_outside:,} unreadable -- neither enters anything below"
    )
    return dict(seasons)


def ols(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Slope and intercept. Written out; this repo does not depend on scipy."""
    n = len(xs)
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else 0.0
    return slope, my - slope * mx


def rmse(errors: list[float]) -> float:
    return math.sqrt(sum(e * e for e in errors) / len(errors))


def price_error_points(
    league_bf: float, league_sd: float, league_rate: float, rate_error: float
) -> Optional[tuple[float, float]]:
    """§4's conversion: `(mean, max)` absolute ladder move, in points.

    Computed by perturbing the model, not by a hand coefficient. Returns `None`
    if either distribution refuses -- a conversion that silently substituted a
    default would put a verdict on the record with nothing behind it.
    """
    base = distribution(league_bf, league_sd, league_rate)
    bumped = distribution(league_bf, league_sd, league_rate + rate_error)
    if base is None or bumped is None:
        return None
    moves = [
        abs(bumped.probability_over(s) - base.probability_over(s)) * 100.0
        for s in REPRESENTATIVE_RUNGS
    ]
    return statistics.fmean(moves), max(moves)


def verdict(prior: float, league: float, price_points: float) -> str:
    """§4's table, and only §4's table."""
    if prior >= league:
        return "USELESS"
    if price_points > TOO_STALE_POINTS:
        return "TOO STALE ALONE"
    if price_points >= FEE_BAR_POINTS:
        return "MARGINAL"
    return "SUFFICIENT"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pitching-zip", type=Path, required=True)
    args = parser.parse_args()

    seasons = load(args.pitching_zip)
    qualifying = {key: s for key, s in seasons.items() if s.qualifies}

    print(f"\npitcher-seasons {len(seasons):,}   "
          f"qualifying at >={MIN_STARTS} starts {len(qualifying):,}")

    # League rate per season, over the qualifying population of that season.
    # §3: the benchmark forecast is season Y's league rate, so it is pooled the
    # same way -- total strikeouts over total batters faced, not a mean of
    # per-pitcher rates, which would weight a 15-start season like a 33-start one.
    league_rate: dict[int, float] = {}
    league_bf: dict[int, float] = {}
    league_sd: dict[int, float] = {}
    for season in range(FIRST_SEASON, LAST_SEASON + 1):
        members = [s for (_, y), s in qualifying.items() if y == season]
        if not members:
            continue
        league_rate[season] = sum(s.k for s in members) / sum(
            sum(s.bfp) for s in members
        )
        league_bf[season] = statistics.fmean([b for s in members for b in s.bfp])
        league_sd[season] = statistics.stdev([b for s in members for b in s.bfp])

    pairs = [
        (pid, y, qualifying[(pid, y)], qualifying[(pid, y + 1)])
        for (pid, y) in qualifying
        if (pid, y + 1) in qualifying
    ]
    if not pairs:
        print("no pairs -- refusing to report a statistic over an empty set")
        return 1

    print(f"pairs (qualified in Y and Y+1) {len(pairs):,}")

    # ----- the primary statistic and its benchmark, §3 ----------------------
    err_prior = [nxt.k_per_bf - cur.k_per_bf for _, _, cur, nxt in pairs]
    err_league = [nxt.k_per_bf - league_rate[y] for _, y, _, nxt in pairs]
    r_prior, r_league = rmse(err_prior), rmse(err_league)

    xs = [cur.k_per_bf for _, _, cur, _ in pairs]
    ys = [nxt.k_per_bf for _, _, _, nxt in pairs]
    slope, intercept = ols(xs, ys)
    r_shrunk = rmse([y - (slope * x + intercept) for x, y in zip(xs, ys)])

    print("\n" + "=" * 72)
    print("K_PER_BF -- PRIMARY")
    print("=" * 72)
    print(f"  RMSE_prior   {r_prior:.5f}     <- the registered primary")
    print(f"  RMSE_league  {r_league:.5f}     <- the do-nothing benchmark")
    print(f"  RMSE_shrunk  {r_shrunk:.5f}     (IN-SAMPLE -- describes the fit, "
          f"is not evidence for it)")
    print(f"  slope        {slope:.4f}       intercept {intercept:.5f}")
    print(f"  improvement over benchmark  "
          f"{100 * (1 - r_prior / r_league):+.1f}%")

    # ----- §3's other two parameters, reported not promoted ------------------
    for name, get in (("mean_bf", lambda s: s.mean_bf), ("sd_bf", lambda s: s.sd_bf)):
        e_prior = [get(nxt) - get(cur) for _, _, cur, nxt in pairs]
        pooled = {
            y: statistics.fmean([get(s) for (_, yy), s in qualifying.items() if yy == y])
            for y in league_rate
        }
        e_league = [get(nxt) - pooled[y] for _, y, _, nxt in pairs]
        print(f"\n{name.upper()}")
        print(f"  RMSE_prior {rmse(e_prior):.4f}   "
              f"RMSE_league {rmse(e_league):.4f}   "
              f"improvement {100 * (1 - rmse(e_prior) / rmse(e_league)):+.1f}%")

    # ----- the parts, before the aggregate is believed -----------------------
    # CLAUDE.md: a pooled number is not a finding until the parts agree, and the
    # largest contributor's share goes beside every aggregate.
    print("\n" + "=" * 72)
    print("PER-PAIR-YEAR. The pooled number above is not a finding until these "
          "agree.")
    print("=" * 72)
    print(f"  {'Y->Y+1':>10}  {'pairs':>6}  {'RMSE_prior':>11}  "
          f"{'RMSE_league':>12}  {'improve':>8}")
    by_year: dict[int, list] = defaultdict(list)
    for pid, y, cur, nxt in pairs:
        by_year[y].append((cur, nxt, y))
    for y in sorted(by_year):
        group = by_year[y]
        gp = rmse([n.k_per_bf - c.k_per_bf for c, n, _ in group])
        gl = rmse([n.k_per_bf - league_rate[yy] for _, n, yy in group])
        flag = "  <- 60-game season" if y == 2020 or y + 1 == 2020 else ""
        print(f"  {y}->{y + 1}  {len(group):>6}  {gp:>11.5f}  {gl:>12.5f}  "
              f"{100 * (1 - gp / gl):>7.1f}%{flag}")
    biggest = max(by_year.values(), key=len)
    print(f"\n  largest contributor: {len(biggest):,} of {len(pairs):,} pairs "
          f"({100 * len(biggest) / len(pairs):.1f}%)")

    # ----- §4: convert to the unit that decides ------------------------------
    ref_season = LAST_SEASON
    converted = price_error_points(
        league_bf[ref_season], league_sd[ref_season],
        league_rate[ref_season], r_prior,
    )
    if converted is None:
        print("\nrefused: the price conversion could not be computed")
        return 1
    mean_points, max_points = converted

    print("\n" + "=" * 72)
    print(f"§4 PRICE CONVERSION  (league {ref_season}: mean_bf "
          f"{league_bf[ref_season]:.2f}, sd_bf {league_sd[ref_season]:.2f}, "
          f"k_per_bf {league_rate[ref_season]:.4f})")
    print("=" * 72)
    print(f"  a {r_prior:.5f} rate error moves the ladder by")
    print(f"    mean across rungs  {mean_points:.2f} points   <- decides")
    print(f"    max  across rungs  {max_points:.2f} points   <- reported only")
    print(f"  registered bars: fee {FEE_BAR_POINTS} pts, "
          f"too-stale {TOO_STALE_POINTS} pts")
    print(f"\n  VERDICT   {verdict(r_prior, r_league, mean_points)}")

    # ----- §7: the exclusion that matters most -------------------------------
    unpaired = len(qualifying) - len({(p, y) for p, y, _, _ in pairs})
    print(f"\n§7 -- {unpaired:,} qualifying pitcher-seasons have no following "
          f"season in the population and are excluded by construction. A "
          f"starter with no history is the pitcher a market is least sure "
          f"about, and this measurement says nothing about him.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
