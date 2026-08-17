"""How wrong is Kalshi's own `KXMLBHR 1+` price? Registered 2026-08-17.

The information used here was obtained free of charge from and is copyrighted by
Retrosheet.

Registered in
`docs/measurements/2026-08-17-preregistration-kalshi-hr-pricing-error.md`.
**Nothing here decides anything that file does not already decide.** The
population, the derived-ask rule, the three fixed `sigma_model` values and all
three verdict branches live there.

THE QUESTION THREE MEASUREMENTS DID NOT ASK
-------------------------------------------
Every prior harness scores a forecaster against the *player's own future*. None
looks at a price, so none can say whether there is money here: a model accurate
to 3.25 points is worthless if Kalshi is accurate to 1 point and valuable if
Kalshi is accurate to 8.

THE TRICK, AND WHY IT NEEDS NO OUTCOMES
---------------------------------------
Two independent estimates of one truth disagree with the combined variance of
both, so Kalshi's error can be recovered by subtracting a *previously measured*
model error from the observed disagreement:

    sigma_kalshi = sqrt( Var(P_model - ask) - sigma_model^2 )

`sigma_model` is an input from
`2026-08-17-home-run-ladder-scope-result.md` (4.04 points), fixed before this
file existed and not re-estimated here. The subtraction is conservative: the two
errors are positively correlated, which shrinks `Var(d)` and **understates**
`sigma_kalshi`.

WHY THE OBVIOUS CALIBRATION RUN IS REFUSED
------------------------------------------
515 settled markets come from **29 games**, against the 300-cluster floor this
project's own signal test requires. The 95% interval on a pooled 12.04% rate
spans about +/-3.6 points against a 1.75-point bar. A calibration run could only
return UNRESOLVED while producing a number that reads like a result, so it is not
run. §2 of the registration.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **No edge, in any branch.** `sigma_kalshi` is a spread, not a direction.
  Knowing Kalshi is noisy is worthless without knowing which side is wrong.
- **Nothing about the ~21% unmatched batters**, who skew to recent debuts.
- **Nothing beyond three dates.** 29 games in one August week.

    .venv\\Scripts\\python.exe scripts/measure_kalshi_hr_pricing_error.py \\
        --quotes CSV --batting-zip ZIP --biodata-zip ZIP
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import math
import statistics
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.kalshi.props import norm  # noqa: E402
from backend.store.db import derive_yes_ask  # noqa: E402

# §3. Measured before this file existed. An INPUT, never re-estimated here.
SIGMA_MODEL_PRIMARY = 4.04
SIGMA_MODEL_SENSITIVITY = (4.50, 5.00)

# §4. A lineup starter's plate appearances, and the qualifying prior season.
ASSUMED_PA = 4.2
BASELINE_SEASON = 2025
MIN_PA = 300

# §5. ADR 0028's bar.
FEE_BAR_POINTS = 1.75

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT",
     "NOV", "DEC"])}


def first_pitch_ms(event_ticker: str) -> Optional[int]:
    """`KXMLBHR-26AUG151310CWSDET` -> first pitch, in epoch ms.

    Derived from the ticker, **not** from `occurrence_datetime`, which this repo
    has measured to carry a 3-hour offset. `None` on anything unparseable -- a
    game whose clock cannot be read is one whose quotes cannot be classified as
    pre- or post-first-pitch, and guessing would silently admit in-play prices.
    """
    parts = event_ticker.split("-")
    if len(parts) < 2 or len(parts[1]) < 11:
        return None
    tag = parts[1]
    try:
        year, month, day = 2000 + int(tag[:2]), _MONTHS[tag[2:5]], int(tag[5:7])
        hour, minute = int(tag[7:9]), int(tag[9:11])
    except (ValueError, KeyError):
        return None
    # US/Eastern in August is UTC-4. Fixed rather than zone-aware because the
    # whole population is a three-day August window; a run over a season
    # boundary would need a real timezone and this would be wrong.
    eastern = dt.timezone(dt.timedelta(hours=-4))
    return int(dt.datetime(year, month, day, hour, minute,
                           tzinfo=eastern).timestamp() * 1000)


def baseline_rates(batting_zip: Path) -> dict[str, float]:
    """`{retrosheet_id: HR per PA}` for qualifying `BASELINE_SEASON` batters."""
    pa: dict[str, int] = defaultdict(int)
    hr: dict[str, int] = defaultdict(int)
    with zipfile.ZipFile(batting_zip) as archive, archive.open("batting.csv") as fh:
        for row in csv.DictReader(
            io.TextIOWrapper(fh, encoding="utf-8", errors="replace")
        ):
            if row.get("stattype") != "value" or row.get("gametype") != "regular":
                continue
            if (row.get("date") or "")[:4] != str(BASELINE_SEASON):
                continue
            try:
                plate, homers = int(row["b_pa"]), int(row["b_hr"])
            except (ValueError, TypeError, KeyError):
                continue
            pa[row["id"]] += plate
            hr[row["id"]] += homers
    return {i: hr[i] / pa[i] for i in pa if pa[i] >= MIN_PA}


def name_index(biodata_zip: Path) -> dict[str, list[str]]:
    """`{normalised name: [retrosheet_id, ...]}`. Ambiguity is preserved."""
    index: dict[str, list[str]] = defaultdict(list)
    with zipfile.ZipFile(biodata_zip) as archive, archive.open("biofile0.csv") as fh:
        for row in csv.DictReader(
            io.TextIOWrapper(fh, encoding="utf-8", errors="replace")
        ):
            full = (row.get("fullname") or "").strip()
            used = (
                f"{(row.get('usename') or '').strip()} "
                f"{(row.get('lastname') or '').strip()}"
            ).strip()
            for candidate in {full, used}:
                if candidate:
                    index[norm(candidate)].append(row["id"])
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quotes", type=Path, required=True)
    parser.add_argument("--batting-zip", type=Path, required=True)
    parser.add_argument("--biodata-zip", type=Path, required=True)
    args = parser.parse_args()

    rates = baseline_rates(args.batting_zip)
    names = name_index(args.biodata_zip)
    print(f"{BASELINE_SEASON} batters at >={MIN_PA} PA: {len(rates):,}")

    # Last strictly-pre-first-pitch quote per ticker. §4.
    latest: dict[str, dict] = {}
    meta: dict[str, dict] = {}
    no_clock = 0
    for row in csv.DictReader(open(args.quotes, encoding="utf-8")):
        start = first_pitch_ms(row["event_ticker"])
        if start is None:
            no_clock += 1
            continue
        observed = int(row["observed_ms"])
        if observed >= start:
            continue
        meta[row["ticker"]] = row
        best = latest.get(row["ticker"])
        if best is None or observed > int(best["observed_ms"]):
            latest[row["ticker"]] = row

    print(f"tickers with a pre-first-pitch quote: {len(latest):,}   "
          f"rows with no readable clock: {no_clock:,}")

    # §4's population, with every exclusion counted rather than absorbed.
    excluded = defaultdict(int)
    observations = []
    for ticker, row in latest.items():
        if row["result"] not in ("yes", "no"):
            excluded["unsettled"] += 1
            continue
        ids = names.get(norm(row["player_name"] or ""), [])
        if not ids:
            excluded["no name match"] += 1
            continue
        if len(ids) > 1:
            excluded["ambiguous name"] += 1
            continue
        rate = rates.get(ids[0])
        if rate is None:
            excluded[f"no qualifying {BASELINE_SEASON} season"] += 1
            continue
        try:
            no_bid = int(row["no_bid_tenths"])
        except (ValueError, TypeError):
            excluded["unreadable no_bid"] += 1
            continue
        ask = derive_yes_ask(no_bid)
        if ask is None or not 0 < ask < 1000:
            excluded["no derivable ask"] += 1
            continue
        model = 1.0 - (1.0 - rate) ** ASSUMED_PA
        observations.append(
            {
                "ticker": ticker,
                "date": row["event_ticker"].split("-")[1][:7],
                "player": row["player_name"],
                "model_pts": model * 100.0,
                "ask_pts": ask / 10.0,
                "d": model * 100.0 - ask / 10.0,
                "result": row["result"],
            }
        )

    print("\nexclusions:")
    for reason, count in sorted(excluded.items(), key=lambda kv: -kv[1]):
        print(f"  {reason:<32} {count:>4}")
    print(f"  {'ADMITTED':<32} {len(observations):>4}")

    if len(observations) < 30:
        print("\nrefusing: too few observations to report a variance")
        return 1

    ds = [o["d"] for o in observations]
    var_d = statistics.variance(ds)
    print("\n" + "=" * 70)
    print("DISAGREEMENT  d = model - derived ask, in points")
    print("=" * 70)
    print(f"  n {len(ds)}   mean {statistics.fmean(ds):+.2f}   "
          f"sd {math.sqrt(var_d):.2f}")
    ordered = sorted(ds)
    for label, q in (("p10", 0.10), ("p50", 0.50), ("p90", 0.90)):
        print(f"  {label} {ordered[int(q * (len(ordered) - 1))]:+.2f}")
    print(f"  mean |d| {statistics.fmean([abs(x) for x in ds]):.2f}")
    print(f"  model mean {statistics.fmean([o['model_pts'] for o in observations]):.2f}"
          f"   ask mean {statistics.fmean([o['ask_pts'] for o in observations]):.2f}")

    print("\n" + "=" * 70)
    print("§3 SUBTRACTION -- Kalshi's own error")
    print("=" * 70)
    verdicts = {}
    for sigma_model in (SIGMA_MODEL_PRIMARY, *SIGMA_MODEL_SENSITIVITY):
        sigma_kalshi = math.sqrt(max(var_d - sigma_model**2, 0.0))
        verdicts[sigma_model] = sigma_kalshi
        tag = "PRIMARY" if sigma_model == SIGMA_MODEL_PRIMARY else "sensitivity"
        flag = ">= bar" if sigma_kalshi >= FEE_BAR_POINTS else "< bar"
        print(f"  sigma_model {sigma_model:.2f} ({tag:<11}) -> "
              f"sigma_kalshi {sigma_kalshi:5.2f} pts   {flag}")

    # §5's table, and only §5's table.
    all_below = all(v < FEE_BAR_POINTS for v in verdicts.values())
    all_above = all(v >= FEE_BAR_POINTS for v in verdicts.values())
    if all_below:
        result = "NOTHING TO TRADE"
    elif all_above:
        result = "KALSHI IS LOOSE ENOUGH TO MATTER"
    else:
        result = "UNRESOLVED, SLOT-LIMITED"
    print(f"\n  bar {FEE_BAR_POINTS} pts")
    print(f"  VERDICT   {result}")

    # Parts, before the aggregate is believed.
    print("\n  per-date:")
    by_date = defaultdict(list)
    for obs in observations:
        by_date[obs["date"]].append(obs["d"])
    for date in sorted(by_date):
        group = by_date[date]
        print(f"    {date}  n={len(group):>3}  mean {statistics.fmean(group):+6.2f}  "
              f"sd {statistics.stdev(group):5.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
