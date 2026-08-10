"""Census: how often does a book quote both sides of a two-way market equally?

Motivation. `edge_within_method_noise` compares the claimed edge against the
max-minus-min across the four devig methods. On a **symmetric** two-way line
every method returns exactly 0.5 -- multiplicative devig of a symmetric line is
`(1/o)/(2/o) = 0.5` for any `o` -- so the spread collapses to ~1e-11 tenths and
the guard passes for any positive edge. Two books doing this simultaneously
produce `fair = 0.5`, `market_width = 0.0`, `book_count = 2` and no suppression
at all. ADR 0019 rejects building a detector for that; this is the measurement
the rejection rests on.

Run:

    .venv\\Scripts\\python.exe scripts/census_symmetric_lines.py

Reads only `tests/fixtures/odds_mlb_h2h_spreads_totals.json`, a committed
verbatim Odds API capture. No network, no credentials, no cost.

================================ WHAT THIS DOES NOT ESTABLISH ================

**It does not measure the population where the defect was actually observed,
and the mismatch is not the league.** All 21 degenerate-fair rows in the live
record were **single-book WNBA**. Every event in this fixture carries **24-30
books**, so the capture contains **zero single-book markets** -- the census had
no opportunity whatsoever to observe the defect in the configuration where every
known instance lived. A rate over an interval containing none of the relevant
opportunities is not a low rate.

**It cannot contain a freshly-posted line.** Every quote is 0.2-2.1 minutes old
at capture and every game is 8.9-12.4 hours from first pitch: mature, actively
repriced, heavily contested same-day MLB. Placeholder lines, if they exist,
appear at *posting* time -- days out, thin books, low-liquidity leagues. None of
that is sampled.

**`n = 425` is not 425 independent observations.** It is 29 books x ~15 events
at ONE instant, and a large share of the quotes are exact cross-book duplicates
(the figure is printed below). If the behaviour is a property of a *book* --
which the hypothesis implies -- the effective `n` is the book count, and the
honest upper bound is an order of magnitude looser than the per-quote one. Both
bounds are printed; quote the per-book one when the claim is about books.

**A zero here is bounded, not proven.** `sqrt(p(1-p)/n)` is exactly 0 for a zero
count and is the wrong estimator. One-sided Clopper-Pearson upper limits are
printed instead, at both denominators.

**What it DOES establish, and why the zero is worth anything at all:** the
comparator is seen to fire. Symmetric quotes are found on spreads and totals in
the same capture, so a zero on h2h is a measured zero rather than a broken
detector. It is also uncontaminated by outcome -- observed hours before the
games resolved.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "odds_mlb_h2h_spreads_totals.json"

# Markets whose handicap the book CHOOSES, and therefore sets to centre the
# market. Symmetry is the designed output there, not an anomaly -- which is why
# they are the positive control rather than part of the finding.
BOOK_CHOOSES_THE_LINE = ("spreads", "totals")


def clopper_pearson_upper(n: int, confidence: float = 0.95) -> float:
    """One-sided upper limit for a rate given ZERO observed events.

    With 0 successes the exact limit is `1 - (1-confidence)**(1/n)`, which is
    the Rule of Three (`3/n`) done properly.
    """
    return 1.0 - (1.0 - confidence) ** (1.0 / n) if n else 1.0


def main() -> int:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    events = payload["events"]

    per_market: dict[str, list] = defaultdict(list)
    books_per_event: dict[str, set[str]] = defaultdict(set)
    h2h_cells: Counter = Counter()

    for event in events:
        for book in event.get("bookmakers", []):
            for market in book.get("markets", []):
                key = market.get("key")
                outcomes = market.get("outcomes", [])
                if len(outcomes) != 2:
                    continue
                a, b = (float(o["price"]) for o in outcomes)
                per_market[key].append((event["id"], book["key"], a, b))
                if key == "h2h":
                    books_per_event[event["id"]].add(book["key"])
                    names = tuple(o["name"] for o in outcomes)
                    prices = tuple(float(o["price"]) for o in outcomes)
                    ordered = tuple(sorted(zip(names, prices)))
                    h2h_cells[(event["id"], ordered)] += 1

    print(f"fixture      : {FIXTURE.relative_to(ROOT)}")
    print(f"captured_ms  : {payload.get('captured_ms')}")
    print(f"events       : {len(events)}")
    print()

    print(f"{'market':<10}{'n':>6}{'symmetric':>11}{'share':>9}{'min |diff|':>12}")
    print("-" * 48)
    for key in ("h2h", "h2h_lay", *BOOK_CHOOSES_THE_LINE):
        rows = per_market.get(key, [])
        if not rows:
            continue
        sym = [r for r in rows if r[2] == r[3]]
        lo = min(abs(r[2] - r[3]) for r in rows)
        print(f"{key:<10}{len(rows):>6}{len(sym):>11}"
              f"{len(sym) / len(rows):>9.2%}{lo:>12.3f}")

    h2h = per_market["h2h"]
    n_quotes = len(h2h)
    n_books = len({r[1] for r in h2h})
    n_cells = len(h2h_cells)
    duplicated = sum(c for c in h2h_cells.values() if c > 1)

    control = sum(
        1
        for key in BOOK_CHOOSES_THE_LINE
        for r in per_market.get(key, [])
        if r[2] == r[3]
    )

    print()
    print("--- why n is not the number of quotes ---")
    print(f"h2h quotes                         : {n_quotes}")
    print(f"distinct (event, price-pair) cells : {n_cells}")
    print(f"quotes that duplicate another book : {duplicated} "
          f"({duplicated / n_quotes:.1%})")
    print(f"distinct books quoting h2h         : {n_books}")

    counts = sorted(len(v) for v in books_per_event.values())
    print()
    print("--- the stratum this fixture CANNOT speak to ---")
    print(f"books per event: min {counts[0]}, max {counts[-1]}")
    print(f"events with a SINGLE book: "
          f"{sum(1 for c in counts if c == 1)} of {len(counts)}")
    print("  ...against 21 degenerate-fair rows in the live record, "
          "ALL single-book WNBA.")

    print()
    print("--- positive control: the comparator fires ---")
    print(f"symmetric quotes on spreads+totals : {control}")
    if control == 0:
        print("  *** STOP: the detector never fired anywhere. A zero on h2h")
        print("      cannot be told from a broken comparator. ***")
        return 1

    print()
    print("--- honest upper bounds on the symmetric-h2h rate (0 observed) ---")
    print(f"per quote (n={n_quotes:>3}) : "
          f"<= {clopper_pearson_upper(n_quotes):.2%}  (one-sided 95%)")
    print(f"per cell  (n={n_cells:>3}) : <= {clopper_pearson_upper(n_cells):.2%}")
    print(f"per BOOK  (n={n_books:>3}) : <= {clopper_pearson_upper(n_books):.2%}"
          "   <-- quote this one when the claim is about books")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
