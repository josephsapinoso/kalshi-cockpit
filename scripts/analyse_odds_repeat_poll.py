"""Analysis for the repeat-poll capture. Reads files only -- SPENDS NOTHING.

Executes the analysis half of
`docs/measurements/2026-08-10-preregistration-odds-last-update-repeat-poll.md`.
Every threshold below is quoted from that document and **none may be changed
after a capture exists**. If a threshold here disagrees with the registration,
the registration wins and this file is the bug.

    .venv\\Scripts\\python.exe scripts/analyse_odds_repeat_poll.py <p1.json> ... <p4.json>

**Preconditions print BEFORE `S`, always** (§7). If any fails the verdict is
UNRESOLVED with the named reason, and `S` is still printed but labelled
`UNRESOLVED -- DOES NOT DECIDE`. That ordering is deliberate: a statistic read
before its preconditions is a statistic that will be quoted without them.

**The primary pair is poll 1 -> poll 3, BY INDEX** (~300 s), never by realised
interval. Selecting the pair closest to 300 s after the fact would be choosing a
cut from the data. The single registered substitution is 1 -> 4, and only when
PC2 (`N_adv >= 5`) fails on 1 -> 3.

## What this measurement cannot establish

- **Not "it measures our polling cadence."** The aggregator scrapes on its own
  schedule; our polls only sample it. The registered claim is the weaker,
  decidable one: `last_update` is **not a per-line reprice timestamp**.
- **Nothing about any league but the captured one**, or any date but the
  capture's own, or any book absent from that slate.
- **`S` has no confidence interval and none may be computed.** Under the
  hypothesis being tested the bookmakers may not be independent at all -- one
  scrape process may serve every book, in which case the effective `n` is 1 and
  thirty books are one observation. `sqrt(p(1-p)/n)` over the pairs would be
  roughly 3.8x too small even if they *were* independent. The design asks
  whether the signature is near-deterministic with thresholds fixed in advance;
  that is a weaker instrument, honestly labelled.
- **A mid-band `S` is permanently unresolvable by this instrument.** More
  credits buy correlated copies, not precision. §8 forbids buying more of the
  same design without a new registration.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.odds.client import OddsClient, OddsConfig  # noqa: E402

# --- Fixed by the registration. Do not tune. ---------------------------------

CONFIRM_AT = 0.90          # §7: CONFIRMED iff S >= 0.90
REFUTE_AT = 0.20           # §7: REFUTED   iff S <= 0.20
PC1_MIN_BOOKS = 20         # §7 PC1
PC2_MIN_ADV_BOOKS = 5      # §7 PC2, the repo's MIN_EXPECTED_PER_SIDE floor
PC3_MIN_ATTRITION = 0.80   # §5.4 / §7 PC3
PC4_MAX_DEFECT_RATE = 0.05  # §7 PC4
PC5_MIN_MOVERS = 5         # §7 PC5, the quiet-slate control
PRIMARY_PAIR = (1, 3)      # §5.2, BY INDEX
FALLBACK_PAIR = (1, 4)     # §5.2, the one registered substitution
EXPECTED_TOTAL_CREDITS = 24  # §7 PC6


@dataclass(frozen=True)
class Row:
    """One priced outcome in one poll, keyed as §5.3 specifies."""

    event_id: str
    bookmaker: str
    market: str
    outcome_name: str
    outcome_point: Optional[float]
    price_decimal: float
    price_token: str          # the ORIGINAL JSON literal, for the byte check
    book_updated_ms: Optional[int]

    @property
    def key(self) -> tuple[str, str, str, str]:
        # `outcome_point` is deliberately NOT in the key (§5.3): it is both an
        # identifier and a thing a book moves, so keying on it would record a
        # total moving 8.5 -> 9.0 as a row vanishing rather than a price
        # changing -- a real reprice removed from the denominator, which
        # flatters the hypothesis.
        return (self.event_id, self.bookmaker, self.market, self.outcome_name)

    @property
    def value(self) -> tuple[Optional[float], float]:
        return (self.outcome_point, self.price_decimal)


def load_poll(path: Path) -> dict[str, Any]:
    artefact = json.loads(path.read_text(encoding="utf-8"))
    for field in ("poll_index", "payload", "payload_raw_tokens", "fetched_ms"):
        if field not in artefact:
            raise SystemExit(f"{path.name}: missing '{field}'. Not a capture artefact.")
    return artefact


def project(artefact: dict[str, Any]) -> list[Row]:
    """Rows via the DEPLOYED parser (P5), with raw price tokens attached.

    `OddsClient._parse` is used rather than a bespoke walk so the population is
    the one the deployed `stale_odds` guard sees: `h2h_lay` excluded, market
    `last_update` preferred over bookmaker `last_update`. A parser written here
    would answer a question about a different set of rows -- which is precisely
    how a denominator of 335 got published where 320 was correct.
    """
    config = OddsConfig(
        api_key="", base_url="", daily_credit_budget=0,
        regions=list(artefact.get("regions") or []),
        markets=list(artefact.get("markets") or []),
    )
    client = OddsClient(config, budget=None)  # type: ignore[arg-type]
    quotes = client._parse(
        artefact["payload"],
        sport_key=artefact.get("sport_key", ""),
        fetched_ms=int(artefact["fetched_ms"]),
    )

    # Raw JSON price tokens, walked in parallel from the parse_float=str copy.
    tokens: dict[tuple[str, str, str, str, Any], str] = {}
    for event in artefact["payload_raw_tokens"]:
        for book in event.get("bookmakers") or []:
            for market in book.get("markets") or []:
                for out in market.get("outcomes") or []:
                    tokens[(
                        str(event.get("id")), str(book.get("key")),
                        str(market.get("key")), str(out.get("name")),
                        out.get("point"),
                    )] = str(out.get("price"))

    rows: list[Row] = []
    for q in quotes:
        token = tokens.get((
            q.odds_event_id, q.bookmaker, q.market, q.outcome_name,
            None if q.outcome_point is None else q.outcome_point,
        ))
        if token is None:
            # Fall back to a point-insensitive lookup before giving up, so a
            # float/str mismatch on the hook does not silently drop the row.
            candidates = [
                v for k, v in tokens.items()
                if k[:4] == (q.odds_event_id, q.bookmaker, q.market, q.outcome_name)
            ]
            token = candidates[0] if len(candidates) == 1 else ""
        rows.append(Row(
            event_id=q.odds_event_id, bookmaker=q.bookmaker, market=q.market,
            outcome_name=q.outcome_name, outcome_point=q.outcome_point,
            price_decimal=q.price_decimal, price_token=token,
            book_updated_ms=q.book_updated_ms,
        ))
    return rows


def by_pair(rows: list[Row]) -> dict[tuple[str, str], dict[tuple, Row]]:
    """(event, book) -> {row key: Row}. Degenerate keys are detectable here."""
    out: dict[tuple[str, str], dict[tuple, Row]] = defaultdict(dict)
    dupes: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        bucket = out[(row.event_id, row.bookmaker)]
        if row.key in bucket:
            dupes[(row.event_id, row.bookmaker)] += 1
        bucket[row.key] = row
    for pair in dupes:
        out[pair]["__degenerate__"] = None  # type: ignore[assignment]
    return out


@dataclass
class PairResult:
    n_poll_a_pairs: int = 0
    both: int = 0
    absent_1: int = 0
    absent_2: int = 0
    rowset_changed: int = 0
    key_degenerate: int = 0
    text_float_mismatch: int = 0
    regressed: int = 0
    cell_a: int = 0   # advanced & identical  -- confirming
    cell_b: int = 0   # advanced & changed    -- refuting
    cell_c: int = 0   # static  & identical
    cell_d: int = 0   # static  & changed     -- defect
    per_book: dict[str, list[int]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.per_book is None:
            self.per_book = defaultdict(lambda: [0, 0])  # [A_b, B_b]


def compare(rows_a: list[Row], rows_b: list[Row]) -> PairResult:
    """§5.4 and §5.5: classify every (book, event) pair, then fill the cells."""
    a, b = by_pair(rows_a), by_pair(rows_b)
    res = PairResult()
    res.n_poll_a_pairs = len(a)

    for pair, ka in a.items():
        if "__degenerate__" in ka:
            res.key_degenerate += 1
            continue
        kb = b.get(pair)
        if kb is None:
            res.absent_2 += 1
            continue
        if "__degenerate__" in kb:
            res.key_degenerate += 1
            continue

        shared = set(ka) & set(kb)
        if not shared:
            res.absent_2 += 1
            continue
        res.both += 1
        if set(ka) != set(kb):
            res.rowset_changed += 1

        # advanced / regressed: max stamp over the INTERSECTED key set only.
        stamps_a = [ka[k].book_updated_ms for k in shared
                    if ka[k].book_updated_ms is not None]
        stamps_b = [kb[k].book_updated_ms for k in shared
                    if kb[k].book_updated_ms is not None]
        if not stamps_a or not stamps_b:
            res.cell_c += 1
            continue
        advanced = max(stamps_b) > max(stamps_a)
        if max(stamps_b) < max(stamps_a):
            res.regressed += 1

        identical = all(ka[k].value == kb[k].value for k in shared)
        text_identical = all(
            ka[k].price_token == kb[k].price_token
            and ka[k].outcome_point == kb[k].outcome_point
            for k in shared
        )
        if identical != text_identical:
            res.text_float_mismatch += 1

        book = pair[1]
        if advanced and identical:
            res.cell_a += 1
            res.per_book[book][0] += 1
        elif advanced:
            res.cell_b += 1
            res.per_book[book][1] += 1
        elif identical:
            res.cell_c += 1
        else:
            res.cell_d += 1

    for pair in b:
        if pair not in a:
            res.absent_1 += 1
    return res


def statistic_s(res: PairResult) -> tuple[Optional[float], int, list[tuple[str, float]]]:
    """§6: the unweighted mean over bookmakers of s_b = A_b / (A_b + B_b).

    A MEAN OF BOOKMAKER-CLUSTERED OBSERVATIONS, not a proportion. Said out loud
    because the wrong null is the easy mistake here and it is the flattering one.
    """
    shares: list[tuple[str, float]] = []
    for book, (a_b, b_b) in sorted(res.per_book.items()):
        if a_b + b_b > 0:
            shares.append((book, a_b / (a_b + b_b)))
    if not shares:
        return None, 0, []
    return sum(s for _, s in shares) / len(shares), len(shares), shares


def movers_over_span(rows_first: list[Row], rows_last: list[Row]) -> int:
    """§6/§7 PC5: distinct books changing >=1 price anywhere over the full span.

    THE MOST IMPORTANT NUMBER IN THE DOCUMENT. On a frozen slate every advancing
    pair lands in the confirming cell and S = 1.0 is declared on data that could
    not have produced any other answer. That is this repo's own scar -- a
    control must be able to reach the confound it was built for.
    """
    first = {(r.event_id, r.bookmaker) + r.key[2:]: r.value for r in rows_first}
    moved: set[str] = set()
    for row in rows_last:
        k = (row.event_id, row.bookmaker) + row.key[2:]
        if k in first and first[k] != row.value:
            moved.add(row.bookmaker)
    return len(moved)


def s_strict(rows_first: list[Row], rows_last: list[Row], books: list[str]) -> float:
    """§6: share of the N_adv books with NO price change anywhere in the slate.

    Because ~27 of 30 books carry one stamp across every game, a stamp advance
    on game X may have been caused by that book repricing game Y. This excludes
    that by construction. REPORTED, NEVER DECISION-BEARING -- it can only
    strengthen wording, never upgrade, downgrade or create a verdict (§7).
    """
    if not books:
        return 0.0
    first = {(r.event_id, r.bookmaker) + r.key[2:]: r.value for r in rows_first}
    moved: set[str] = set()
    for row in rows_last:
        k = (row.event_id, row.bookmaker) + row.key[2:]
        if k in first and first[k] != row.value:
            moved.add(row.bookmaker)
    return sum(1 for b in books if b not in moved) / len(books)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Analyse a repeat-poll capture.")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)

    artefacts = sorted(
        (load_poll(p) for p in args.files), key=lambda a: a["poll_index"]
    )
    if len(artefacts) != 4:
        print(f"Expected 4 polls, got {len(artefacts)}. "
              "A partial capture issues no verdict (sec P1).")
        return 2

    rows = {a["poll_index"]: project(a) for a in artefacts}

    print("=" * 72)
    print("REPEAT POLL -- is `last_update` a per-line reprice timestamp?")
    print("registration: docs/measurements/"
          "2026-08-10-preregistration-odds-last-update-repeat-poll.md")
    print("=" * 72)
    for a in artefacts:
        print(f"  poll {a['poll_index']}  nominal T0+{a['nominal_offset_s']:4d}s"
              f"  realised +{a['realised_offset_s']:8.1f}s"
              f"  quotes {a['n_quotes_parsed']:5d}"
              f"  server remaining {a.get('x_requests_remaining')}")

    # --- the pair that decides, chosen by INDEX -------------------------------
    pair_idx = PRIMARY_PAIR
    res = compare(rows[pair_idx[0]], rows[pair_idx[1]])
    s, n_adv, shares = statistic_s(res)
    substituted = False
    if n_adv < PC2_MIN_ADV_BOOKS:
        substituted = True
        pair_idx = FALLBACK_PAIR
        res = compare(rows[pair_idx[0]], rows[pair_idx[1]])
        s, n_adv, shares = statistic_s(res)

    n_books = len({p[1] for p in by_pair(rows[pair_idx[0]])}
                  & {p[1] for p in by_pair(rows[pair_idx[1]])})
    movers = movers_over_span(rows[1], rows[4])
    total_spend = sum(a.get("cost_credits", 0) for a in artefacts)
    all_non_empty = all(a["n_quotes_parsed"] > 0 for a in artefacts)

    print(f"\ndeciding pair: poll {pair_idx[0]} -> {pair_idx[1]}"
          f"{'   (PC2 FALLBACK APPLIED)' if substituted else '   (PRIMARY)'}")

    # --- R, printed BEFORE S (§6) --------------------------------------------
    r_pair = (res.cell_a + res.cell_b) / res.both if res.both else 0.0
    print("\nR -- the advance rate, printed before S because if nothing "
          "advanced\n     the confirming cell was unreachable and S is a ratio "
          "over nothing")
    print(f"  pairs advancing / BOTH      {res.cell_a + res.cell_b} / {res.both}"
          f"  = {r_pair:.4f}")
    print(f"  books advancing / books     {n_adv} / {n_books}")

    print("\ncells (sec 5.5)")
    print(f"  A advanced & identical  {res.cell_a:5d}   <- confirming")
    print(f"  B advanced & changed    {res.cell_b:5d}   <- refuting")
    print(f"  C static   & identical  {res.cell_c:5d}   uninformative")
    print(f"  D static   & changed    {res.cell_d:5d}   <- defect: reprice, no advance")
    print(f"  attrition  BOTH {res.both}  ABSENT-1 {res.absent_1}  "
          f"ABSENT-2 {res.absent_2}  ROWSET-CHANGED {res.rowset_changed}")
    print(f"  integrity  regressed {res.regressed}  KEY-DEGENERATE "
          f"{res.key_degenerate}  TEXT_FLOAT_MISMATCH {res.text_float_mismatch}")

    # --- preconditions, ALL printed before the verdict (§7) ------------------
    checks: list[tuple[str, bool, str]] = [
        ("PC1 book coverage", n_books >= PC1_MIN_BOOKS,
         f"{n_books} books in both polls, need >= {PC1_MIN_BOOKS}"),
        ("PC2 confirming cell reachable", n_adv >= PC2_MIN_ADV_BOOKS,
         f"N_adv = {n_adv}, need >= {PC2_MIN_ADV_BOOKS}"),
        ("PC3 attrition", res.both >= PC3_MIN_ATTRITION * res.n_poll_a_pairs,
         f"BOTH {res.both} vs {PC3_MIN_ATTRITION:.0%} of {res.n_poll_a_pairs}"),
        ("PC4 integrity",
         (res.cell_d <= PC4_MAX_DEFECT_RATE * res.both
          and res.regressed <= PC4_MAX_DEFECT_RATE * res.both
          and res.key_degenerate == 0 and res.text_float_mismatch == 0),
         f"D {res.cell_d}, regressed {res.regressed}, degenerate "
         f"{res.key_degenerate}, text-float {res.text_float_mismatch}"),
        ("PC5 control reaches the confound", movers >= PC5_MIN_MOVERS,
         f"{movers} books moved a price over the full span, "
         f"need >= {PC5_MIN_MOVERS}"),
        ("PC6 the spend is real",
         all_non_empty and total_spend == EXPECTED_TOTAL_CREDITS,
         f"{total_spend} credits, all polls non-empty: {all_non_empty}"),
    ]

    print("\nPRECONDITIONS -- evaluated and printed BEFORE S (sec 7)")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:34s} {detail}")
    failed = [name for name, ok, _ in checks if not ok]

    # --- the statistic --------------------------------------------------------
    pooled = (res.cell_a / (res.cell_a + res.cell_b)
              if (res.cell_a + res.cell_b) else None)
    largest = max((c for _, c in
                   ((b, a_ + b_) for b, (a_, b_) in res.per_book.items())),
                  default=0)
    print("\nS -- bookmaker-clustered MEAN of within-book shares (sec 6)")
    print("     not a proportion; no standard error is computed anywhere")
    print(f"  S            {'n/a' if s is None else f'{s:.4f}'}   over N_adv = {n_adv} books")
    if pooled is not None:
        print(f"  pooled A/(A+B)  {pooled:.4f}   "
              f"(printed beside S: a pooled number is not a finding until the "
              f"parts agree)")
        denom = res.cell_a + res.cell_b
        print(f"  largest single book's share of the pooled denominator: "
              f"{largest}/{denom} = {largest / denom:.1%}"
              if denom else "")

    if failed:
        print("\n" + "=" * 72)
        print(f"VERDICT: UNRESOLVED -- {', '.join(failed)}")
        if "PC5 control reaches the confound" in failed:
            print("         QUIET SLATE. However high S is, 'no price changed' "
                  "carries no\n         information when nothing changed "
                  "anywhere.")
        print("S above is labelled UNRESOLVED -- DOES NOT DECIDE.")
        print("UNRESOLVED is a real answer, reported with the same prominence "
              "as the others.")
        print("=" * 72)
        return 0

    books_adv = [b for b, _ in shares]
    strict = s_strict(rows[1], rows[4], books_adv)
    print("\n" + "=" * 72)
    if s is not None and s >= CONFIRM_AT:
        print(f"VERDICT: CONFIRMED -- `last_update` is NOT a per-line reprice "
              f"timestamp.\n         S = {s:.4f} >= {CONFIRM_AT}")
        print(f"         S_strict = {strict:.4f}")
        if strict >= CONFIRM_AT:
            print("         S_strict >= 0.90: the stamp advanced with NO "
                  "observed reprice\n         anywhere. ADR 0020 may use the "
                  "strong wording.")
        else:
            print("         MANDATORY QUALIFIER: the confirmation rests on "
                  "pair-level identity;\n         the stamp is book-scoped, so "
                  "a reprice on another game in the same\n         slate cannot "
                  "be excluded as the cause of the advance. ADR 0020 is\n"
                  "         restricted to the claim that `odds_age_ms` is not a "
                  "per-line\n         freshness measure.")
    elif s is not None and s <= REFUTE_AT:
        print(f"VERDICT: REFUTED -- `last_update` tracks reprices.\n"
              f"         S = {s:.4f} <= {REFUTE_AT}")
    else:
        print(f"VERDICT: UNRESOLVED -- S = {s:.4f} lies between {REFUTE_AT} "
              f"and {CONFIRM_AT}.\n         Mid-band is PERMANENTLY unresolvable "
              "by this instrument; more\n         credits buy correlated copies, "
              "not precision (sec 8).")
    print("=" * 72)

    # --- the operational corollary: a count, not a test (§7) ------------------
    res900 = compare(rows[1], rows[4])
    _, n_adv900, _ = statistic_s(res900)
    books900 = len({p[1] for p in by_pair(rows[1])} & {p[1] for p in by_pair(rows[4])})
    ratio = n_adv900 / books900 if books900 else 0.0
    print(f"\nOPERATIONAL COROLLARY (a count, carries no alpha, cannot alter "
          f"the verdict)\n  books advancing within the deployed "
          f"MAX_ODDS_AGE_S = 900s window: "
          f"{n_adv900}/{books900} = {ratio:.4f}")
    print("  >= 0.90: nearly every book's stamp advances inside the window, so "
          "`stale_odds`\n           can seldom bind on book age and ADR 0020's "
          "remedy must address that."
          if ratio >= 0.90 else
          "  < 0.90: some books do not advance inside 900s, so the guard is not "
          "wholly\n          vacuous and the remedy must say which books it "
          "still protects.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
