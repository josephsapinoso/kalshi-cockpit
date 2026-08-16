"""Does the §A8.2 quote-join disagreement bias `gamma_hat`, and therefore `beta_hat`?

    .venv\\Scripts\\python.exe scripts/measure_quote_join_bias.py \\
        docs/measurements/2026-08-16-clv-signal-pull.json.gz

The 2026-08-16 interim look reported that **1,826 of 3,692 rows (49.5%)** carry a
joined quote whose derived ask disagrees with the stored `entry_ask_tenths`,
while **0** rows carry no quote at all. That was counted and explicitly not
explained. This harness asks whether it moves the headline number.

**It does not, because it is not real.** The 1,826 are exactly the 1,826
`side='no'` rows. `entry_ask_tenths` is the price paid for the side actually
taken (`backend/analysis/clv.py:151`), so the ask to compare it against is
`1000 - no_bid` on a YES row and `1000 - yes_bid` on a NO row; the original
check used the YES-side ask on every row and therefore flagged every NO row by
construction. Compared side-aware, the disagreement count on this record is
**0 of 3,692**, and every joined quote is stamped at exactly `created_ms`.
`scripts/run_signal_test.py:_quote_disagrees` is corrected.

The mechanism this was built to test
------------------------------------
`half_spread_tenths` is not a nicety, it is correction C2's control: `edge` and
`clv` are both measured against the ask, so the half-spread enters both and
induces a slope with no signal present. Had the join been recovering the control
from a different instant than the one the recommendation was priced from, the
control would be a mismeasured regressor -- which attenuates its own coefficient
and **transfers part of its effect onto any correlated regressor**, here
`edge_tenths`. The harness still prints every quantity that channel would need,
so the negative result is readable rather than asserted:

1. `ask_error` and the join staleness that would cause it, and
2. `corr(edge_tenths, half_spread_tenths)` -- with no correlation there is no
   channel for the error to reach `beta` at all.

The fits
--------
- **REGISTERED** -- the published fit, reproduced so the comparisons have a
  baseline computed by this file rather than quoted from a document.
- **YES / NO strata** -- the split the broken check was actually making. `side`
  is not a registered cut and this is a diagnostic; it is here because a
  reader who has been told "49.5% of rows are affected" needs to see what those
  rows are.
- **ALT CONTROL** -- refit with the half-spread rebuilt from the stored entry
  ask and the same-side bid, rather than from the quote's opposite bid.
  **It carries zero information and is printed labelled as a tautology.** It is
  algebraically identical to the registered control whenever `ask_error == 0`,
  which is the thing under test; on a YES row both reduce to
  `((1000-no_bid) - yes_bid)/2` and on a NO row both to
  `((1000-yes_bid) - no_bid)/2`. It reproduces the baseline to the last digit
  because it must, not because anything was corroborated.
- **FRESH-ONLY** -- rows whose joined quote is within `--fresh-ms` of
  `created_ms`. On this record that is every row, and for the same reason: see
  the staleness note below. Also a tautology here.

**So the table has three distinct fits, not five**, and mislabelling two
restatements as independent controls is exactly how a weak result reads as a
corroborated one.

Staleness is zero by construction, not by observation
-----------------------------------------------------
`created_ms` is not independently clocked. `run_once` (`runner.py:1911`) and
`run_quote_pass` (`runner.py:2043`) compute `stamp = now or now_ms()`, pass
`now=stamp` into `store_quotes_from_discovery` which inserts
`kalshi_quotes.observed_ms = now` (`runner.py:1842-1851`), then pass **the same
`stamp`** into `run_pricing_pass` which writes `created_ms`. They are the same
Python variable. `kalshi_quote_age_ms` is 0 on all 10,288 recommendations ever
written and `stale_kalshi_quote` has never fired once. A staleness distribution
printed by this harness describes the writer, and must not be read as evidence
about the record.

What this does not establish
----------------------------
- **It cannot change the registered verdict, in either direction.** The look is
  taken on data already seen, `side` is not a registered cut, and §6's verdict
  branches read the registered fit only. A diagnostic can downgrade confidence
  in a published number; it can never create a finding.
- **It does not clear the join in any strong sense.** `entry_ask_tenths` and the
  extraction's derived ask are both `1000 - opposite_bid` off the *same* stored
  row, so the identity is `1000 - b == 1000 - b`. The only live failure it could
  have caught is a pass that priced a ticker for which it stored no quote row.
  0/3692 is therefore a weak pass, not a strong one.
- **It says nothing about whether the quote read the book correctly.**
  `observed_ms` is our local REST-return clock, not a venue timestamp.
- **It does not make the harness §A8.2-compliant.**
  `backend/analysis/signal_test.py:coverage` still implements the superseded
  non-NULL-half-spread statistic and still calls itself "P1's statistic". Only
  `scripts/run_signal_test.py` reads `matched / total`.
- **It says nothing about the other 3,127 `stale_odds` rows** the registration
  excludes by name. Those are excluded upstream, in the extraction.
- **Nothing about tradeability, fees, or fill.** Same limits as the parent test.
- **`G` here is the registration's cluster key** `COALESCE(event_ticker,
  ticker)`, not ADR 0029's `odds_event_id`. A stratum's `G` is not comparable to
  the gate's count.
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.analysis.signal_test import (  # noqa: E402
    Observation,
    SignalTestRefused,
    coverage,
    fit,
)

PRICE_MAX = 1000

# Rows joined within this many milliseconds of `created_ms` cannot be badly
# mismeasured whatever the cause. One minute is the coarsest sweep cadence the
# recorder runs at, so a quote inside it is the same polling instant.
FRESH_MS = 60_000


def _read(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return fh.read()
    return path.read_text(encoding="utf-8")


def load(path: Path) -> list[dict[str, Any]]:
    """Rows from a `clv-signal-pull` dump, refusing a truncated one.

    Same refusal as `run_signal_test.py` and for the same reason: a capped dump
    is ordered by `id`, so it is the earliest recommendations rather than a
    sample.
    """
    payload = json.loads(_read(path))
    if payload.get("query") != "clv-signal-pull":
        raise SystemExit(
            f"{path}: this is a {payload.get('query')!r} dump, not clv-signal-pull"
        )
    rows: list[dict[str, Any]] = []
    for section in payload["sections"]:
        if section.get("truncated"):
            raise SystemExit(
                f"{path}: section {section['title']!r} was truncated. Re-take it "
                f"with a higher --limit; a prefix of the record is not a sample."
            )
        columns = section["columns"]
        rows.extend(dict(zip(columns, row)) for row in section["rows"])
    return rows


def opposite_bid(row: dict[str, Any]) -> Optional[int]:
    """The bid the row's own ask is derived from. YES ask needs the NO bid.

    The whole finding turns on this function existing. A side-blind version --
    always `no_bid_tenths` -- is what produced the phantom 1,826.
    """
    if (row.get("side") or "").lower() == "no":
        return row.get("yes_bid_tenths")
    return row.get("no_bid_tenths")


def same_side_bid(row: dict[str, Any]) -> Optional[int]:
    if (row.get("side") or "").lower() == "no":
        return row.get("no_bid_tenths")
    return row.get("yes_bid_tenths")


def ask_error(row: dict[str, Any]) -> Optional[int]:
    """Side-aware derived ask minus stored entry ask, in tenths. `None` if no quote.

    Signed deliberately. A symmetric error is a market that moved both ways
    between the quote and the write; a one-sided one is a systematic join
    defect, and those two have different remedies.
    """
    bid = opposite_bid(row)
    if bid is None or row.get("entry_ask_tenths") is None:
        return None
    return (PRICE_MAX - bid) - row["entry_ask_tenths"]


def ask_error_side_blind(row: dict[str, Any]) -> Optional[int]:
    """The original, broken comparison. Kept so the diagnosis is reproducible.

    This is not a fallback and must never be used for a number that goes
    anywhere. It exists so the harness can show that the count it reproduces is
    exactly the NO-row count.
    """
    if row.get("no_bid_tenths") is None or row.get("entry_ask_tenths") is None:
        return None
    return (PRICE_MAX - row["no_bid_tenths"]) - row["entry_ask_tenths"]


def staleness_ms(row: dict[str, Any]) -> Optional[int]:
    if row.get("quote_observed_ms") is None or row.get("created_ms") is None:
        return None
    return row["created_ms"] - row["quote_observed_ms"]


def _obs(rows: Sequence[dict[str, Any]], *, control: str) -> list[Observation]:
    """Observations under one of two controls.

    `registered` is the extraction's own `half_spread_tenths`. `alt` rebuilds it
    from the stored entry ask and the same-side bid. Neither imputes: a row that
    cannot supply the chosen control gets `None` and is dropped and counted by
    the harness, exactly as P1 requires.
    """
    out: list[Observation] = []
    for r in rows:
        if control == "registered":
            hs = r["half_spread_tenths"]
        elif control == "alt":
            bid = same_side_bid(r)
            if bid is None or r.get("entry_ask_tenths") is None:
                hs = None
            else:
                hs = (r["entry_ask_tenths"] - bid) / 2.0
        else:  # pragma: no cover - argument is closed
            raise ValueError(control)
        out.append(
            Observation(
                cluster_key=str(r["cluster_key"]),
                edge_tenths=float(r["edge_tenths"]),
                clv_tenths=float(r["clv_tenths"]),
                half_spread_tenths=None if hs is None else float(hs),
            )
        )
    return out


def _correlation(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) < 2:
        return float("nan")
    try:
        return statistics.correlation(xs, ys)
    except statistics.StatisticsError:
        return float("nan")


def _fit_line(label: str, obs: Sequence[Observation], *, total: int) -> None:
    """One row of the comparison table, or the reason there isn't one."""
    cov = coverage(obs)
    try:
        f = fit(obs)
    except SignalTestRefused as exc:
        print(f"  {label:<22} n={len(obs):5d}  REFUSED: {exc}")
        return
    print(
        f"  {label:<22} n={f.n_rows:5d} G={f.n_clusters:4d} "
        f"share={len(obs) / total:5.1%} cov={cov:.3f}  "
        f"beta={f.beta_hat:+.4f} se={f.se_cluster:.4f} "
        f"gamma={f.gamma_hat:+.4f}  "
        f"[{f.lower:+.4f}, {f.upper:+.4f}]"
    )


def _quantiles(values: Sequence[float]) -> str:
    if not values:
        return "(none)"
    ordered = sorted(values)

    def at(p: float) -> float:
        return ordered[min(len(ordered) - 1, int(p * len(ordered)))]

    return (
        f"min {ordered[0]:+.0f}  p10 {at(0.10):+.0f}  p50 {at(0.50):+.0f}  "
        f"p90 {at(0.90):+.0f}  max {ordered[-1]:+.0f}"
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("dump", type=Path)
    parser.add_argument(
        "--fresh-ms",
        type=int,
        default=FRESH_MS,
        help=f"staleness bound for the FRESH-ONLY fit (default {FRESH_MS})",
    )
    args = parser.parse_args(argv)

    rows = load(args.dump)
    total = len(rows)

    print("# Quote-join bias: does the §A8.2 disagreement move beta_hat?")
    print("# DIAGNOSTIC ONLY. This cannot change the registered verdict.")
    print(f"# dump: {args.dump}")
    print()

    no_quote = [r for r in rows if r["half_spread_tenths"] is None]
    errors = {id(r): ask_error(r) for r in rows}
    blind = {id(r): ask_error_side_blind(r) for r in rows}
    agree = [r for r in rows if errors[id(r)] == 0]
    disagree = [r for r in rows if errors[id(r)] not in (0, None)]
    yes_rows = [r for r in rows if (r.get("side") or "").lower() == "yes"]
    no_rows = [r for r in rows if (r.get("side") or "").lower() == "no"]

    # 1. n before effect size. The strata sizes come before any beta.
    print("1. the population, and how it splits")
    print("-" * 78)
    print(f"  rows                          {total}")
    print(f"  rows with NO quote at all     {len(no_quote)}")
    print(f"  side=yes / side=no            {len(yes_rows)} / {len(no_rows)}")
    print(
        f"  quote AGREES (side-aware)     {len(agree)}  ({len(agree) / total:.1%})"
    )
    print(
        f"  quote DISAGREES (side-aware)  {len(disagree)}  ({len(disagree) / total:.1%})"
    )
    print()

    # 2. the diagnosis: what the reported 49.5% actually was
    print("2. the reported 49.5%, reproduced and identified")
    print("-" * 78)
    blind_disagree = [r for r in rows if blind[id(r)] not in (0, None)]
    print(f"  side-BLIND disagreement count {len(blind_disagree)}")
    print(f"  side='no' row count           {len(no_rows)}")
    same = {id(r) for r in blind_disagree} == {id(r) for r in no_rows}
    print(f"  are they the same rows?       {'YES, exactly' if same else 'NO'}")
    print("    entry_ask_tenths is the price paid for the side actually taken")
    print("    (backend/analysis/clv.py:151), so a NO row's ask derives from the")
    print("    YES bid. Comparing every row against 1000 - no_bid flags every NO")
    print("    row by construction. It was a defect in the check, not the data.")
    print()

    # 3. how badly the control is mismeasured, and in which direction
    print("3. the mismeasurement itself (tenths of a cent, signed, side-aware)")
    print("-" * 78)
    signed = [float(e) for e in errors.values() if e is not None]
    nonzero = [e for e in signed if e != 0]
    print(f"  ask_error, all rows           {_quantiles(signed)}")
    if nonzero:
        pos = sum(1 for e in nonzero if e > 0)
        print(f"  ask_error, disagreeing only   {_quantiles(nonzero)}")
        print(
            f"  sign balance (disagreeing)    {pos} above / {len(nonzero) - pos} below"
        )
        print(
            f"  mean |ask_error|              "
            f"{statistics.fmean(abs(e) for e in nonzero):.2f} tenths"
        )
    else:
        print("  ask_error, disagreeing only   (no disagreeing rows)")
    stale = [float(s) for s in (staleness_ms(r) for r in rows) if s is not None]
    print(f"  staleness ms, all rows        {_quantiles(stale)}")
    print(f"  distinct staleness values     {sorted({int(s) for s in stale})[:8]}")
    print()

    # 4. the channel. With no correlation the error cannot reach beta at all.
    print("4. the channel the error would have to travel through")
    print("-" * 78)
    reg = _obs(rows, control="registered")
    usable = [(o, r) for o, r in zip(reg, rows) if o.half_spread_tenths is not None]
    hs = [o.half_spread_tenths for o, _ in usable]
    edge = [o.edge_tenths for o, _ in usable]
    print(f"  corr(edge, half_spread)       {_correlation(edge, hs):+.4f}")
    print("    A mismeasured control biases a coefficient only through its")
    print("    correlation with that regressor.")
    err_usable = [errors[id(r)] for _, r in usable]
    if all(e is not None for e in err_usable):
        vals = [float(e) for e in err_usable]
        if len(set(vals)) > 1:
            print(f"  corr(edge, ask_error)         {_correlation(edge, vals):+.4f}")
        else:
            print(
                f"  corr(edge, ask_error)         undefined -- ask_error is "
                f"constant at {vals[0]:+.0f}, i.e. there is no error to correlate"
            )
    print()

    # 5. the fits, side by side
    print("5. the fits. Same estimator, five populations/controls")
    print("-" * 78)
    _fit_line("REGISTERED (baseline)", reg, total=total)
    _fit_line("  side=yes stratum", _obs(yes_rows, control="registered"), total=total)
    _fit_line("  side=no stratum", _obs(no_rows, control="registered"), total=total)
    _fit_line("ALT CONTROL (all rows)", _obs(rows, control="alt"), total=total)
    fresh = [
        r for r in rows if (s := staleness_ms(r)) is not None and 0 <= s <= args.fresh_ms
    ]
    _fit_line(
        f"FRESH <= {args.fresh_ms}ms", _obs(fresh, control="registered"), total=total
    )
    print()

    print("6. what this does not establish")
    print("-" * 78)
    for line in (
        "It cannot change the registered verdict. `side` is not a registered cut",
        "  and ALT CONTROL is not the registered control; §6 reads the",
        "  REGISTERED line only.",
        "It clears the JOIN, not the control. That the half-spread comes from the",
        "  quote the recommendation was priced from is established; whether that",
        "  quote read the book correctly is a different question.",
        "ALT CONTROL reproducing the baseline is arithmetic, not corroboration.",
        "Nothing about tradeability, fees or fill.",
    ):
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
