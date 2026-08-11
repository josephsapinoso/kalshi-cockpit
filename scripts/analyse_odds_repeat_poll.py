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
- **Nothing here proves the capture happened.** Every artefact is a file; a file
  can be edited. PC6 asks the server's own credit delta precisely because the
  rest of this script would compute a clean `S` over four copies of one poll.

## `poll_index` is 1-based, on both sides

`scripts/capture_odds_repeat_poll.py:588` is
`for index, offset in enumerate(POLL_OFFSETS_S, start=1):` and `:648` writes
`"poll_index": index`. This file reads polls 1..4 (`PRIMARY_PAIR = (1, 3)`,
`FALLBACK_PAIR = (1, 4)`, `rows[1]` / `rows[4]` for the span), and
`_check_index_domain` refuses any artefact outside 1..4 rather than silently
comparing whatever it was handed. `tests/test_analyse_odds_repeat_poll.py`
re-derives the capture side's `start=` from its AST, so the two cannot drift.

## §8 and the partial capture -- resolved, not left ambiguous

This file used to read `if len(artefacts) != 4: return 2`, which refuses every
partial capture. §8 does not:

> A partial capture yields a verdict **only if polls 1 and 3 both exist** (the
> primary pair). Polls 1 and 4 alone yield a verdict only through the PC2
> fallback. Any other partial capture is **UNRESOLVED -- INCOMPLETE**.

So the gate is now `_select_deciding_pair`, which admits {1,3} and {1,4} and
refuses everything else with `UNRESOLVED -- INCOMPLETE` and exit 2. This is not
a loosening: **PC6 requires all four polls and a 24-credit delta, so a partial
capture can only ever reach UNRESOLVED.** What changes is that the reader gets
the preconditions, the cells and `S` printed with the named failure, instead of
a one-line refusal -- which is what §7 means by "`S` is still printed but
labelled UNRESOLVED -- DOES NOT DECIDE".

Two further refusals were added at the same gate, both exit 2, because both
would otherwise produce a *confident* number from nothing:

- **A repeated `poll_index`.** The old `{a["poll_index"]: ...}` comprehension
  silently kept the last one; handing the same file twice compared a poll with
  itself and yields `S = 1.0` -- CONFIRMED out of one poll.
- **An index outside 1..4.**

## Exit codes -- read these, not the prose

- `0` -- a verdict was issued. **CONFIRMED, REFUTED and UNRESOLVED all return
  0**: they are equally real answers (§7) and an exit code that punished
  UNRESOLVED would be a thumb on the scale. The verdict is the line beginning
  `VERDICT:`.
- `2` -- **no verdict issued**: a malformed or unusable artefact set.

## Amendment B, and the two things in it that bind this file

Appended to the registration before poll 1 (commit `0e9b310`).

- **§B1 retires the phrase "the strong wording."** This file used to print it,
  and it was defined nowhere -- not in the registration, not here, and not in
  ADR 0020, which does not exist. The `S_strict >= 0.90` branch now prints §B1's
  permitted paragraph verbatim and the list of readings it does **not** license.
- **§B2 records `s_strict`'s 1 -> 4 span as a registered deviation** from §6's
  natural reading, and says explicitly that this file is **not** to be altered
  to match §6: 1 -> 4 is the superset window, so `S_strict` is at most as high
  and the `>= 0.90` leg strictly harder to reach. **Do not "fix" it.** The span
  is now printed beside the value, which is what §B2 requires instead.

## Mutations this file's guards were checked against

Required by CLAUDE.md ("every guard is verified by disabling it and watching the
test fail"). Each was applied to this file, `pytest tests/test_analyse_odds_repeat_poll.py -x`
run, and the file restored (`scratchpad/mutate.py`, driver kept out of the repo).
M1-M11 were re-run with `TestTheThresholdsAreStillTheRegisteredOnes` deselected,
because that class asserts the constants *as literals* and would go red for any
of them without proving that any **behaviour** is guarded; the results below are
the behavioural ones. **Mutations that stayed green are listed too, with why they
proved nothing** -- a pruned list is a claim that was never made.

| # | Mutation | Result |
|---:|---|---|
| M1 | `CONFIRM_AT` 0.90 -> 0.50 | RED |
| M2 | `REFUTE_AT` 0.20 -> 0.50 | RED -- **but green on the first pass.** No scenario placed `S` in (0.20, 0.50], so nothing distinguished the two thresholds. `test_unresolved_just_above_the_refutation_threshold` (S ~ 0.26) was added for it, and it pins the band with the literal `0.20` rather than `analyse.REFUTE_AT` -- a test that reads the constant moves its own goalposts when the constant is edited. |
| M3 | `PRIMARY_PAIR` (1,3) -> (1,2) | RED |
| M4 | `FALLBACK_PAIR` (1,4) -> (1,2) | RED |
| M5 | `PC1_MIN_BOOKS` 20 -> 0 | RED |
| M6 | `PC2_MIN_ADV_BOOKS` 5 -> 0 | RED |
| M7 | `PC3_MIN_ATTRITION` 0.80 -> 0.0 | RED |
| M8 | `PC4_MAX_DEFECT_RATE` 0.05 -> 1.0 | RED |
| M9 | PC4: drop the `text_float_mismatch == 0` conjunct | RED |
| M10 | PC4: drop the `key_degenerate == 0` conjunct | RED |
| M11 | `PC5_MIN_MOVERS` 5 -> 0 | RED |
| M12 | PC6: drop the `all_non_empty` conjunct | RED |
| M13 | `advanced` `>` -> `>=` (a static stamp reads as an advance) | RED |
| M14 | `identical` `all(...)` -> `any(...)` | RED |
| M15 | drop the duplicate-`poll_index` refusal | RED |
| M16 | restore `if len(artefacts) != 4: return 2` | RED |
| M17 | no-stamp pairs routed back into cell C instead of excluded | RED |
| M18 | put `outcome_point` back into `Row.key` (§5.3) | RED |
| M19 | drop the `sorted(..., key=poll_index)` | GREEN -- **proved nothing, and is recorded rather than pruned.** `rows` is a dict keyed by `poll_index` and every consumer indexes it by number, so file order reaches only the banner's print order, which no assertion reads. `TestOrderIndependence` therefore asserts a property that already holds by construction. Kept because the sort is what keeps the banner readable and because a future order-dependent consumer would make this guard load-bearing without anyone noticing. |
| M20 | `movers_over_span(rows[1], rows[4])` -> `(rows[1], rows[3])` | RED |
| M21 | drop the index-domain (1..4) refusal | RED |
| M22 | drop the ADR 0026 rival-hypothesis block | RED |
| M23 | `movers_deciding` collapsed onto the full-span `movers` | RED |
| M24 | `s_strict` span 1 -> 4 changed to the deciding pair (Amendment B §B2) | RED |
| M25 | restore the retired phrase "the strong wording" (Amendment B §B1) | RED |
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
N_POLLS = 4                # §5.1 / §8: exactly four calls, indexed 1..4
OFFSET_LAST_S = 900        # §5.1: poll 4 is T0 + 900 s. The `S_strict` span.

# Every field `main` dereferences with `[]`. Listed here so a malformed artefact
# is named at load time rather than raising a bare KeyError 200 lines later,
# where it would look like an analysis defect rather than a capture one.
REQUIRED_FIELDS = (
    "poll_index", "payload", "payload_raw_tokens", "fetched_ms",
    "nominal_offset_s", "realised_offset_s", "n_quotes_parsed",
)


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
    for field in REQUIRED_FIELDS:
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
    no_stamp: int = 0
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
            # NOT cell C. A pair with no `last_update` on either side is
            # *unreadable*, not *static*, and this file used to record it as
            # "static & identical" -- which is the substitution CLAUDE.md
            # forbids ("unreadable resolves to None, never 0"). Worse, it put a
            # reprice-with-no-stamp into the uninformative cell instead of the
            # defect cell D, hiding exactly the evidence PC4 exists to catch.
            # §S2 item 2 lists `book_updated_ms is None` under *exclusions,
            # counted*, so that is what it is: excluded from the 2x2, counted,
            # printed. A + B + C + D + no_stamp == BOTH.
            res.no_stamp += 1
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


def _check_index_domain(indices: list[int]) -> Optional[str]:
    """`poll_index` is 1-based (`capture_odds_repeat_poll.py:588,648`).

    A 0 here would mean the capture side had been changed to `enumerate(...)`
    without `start=1`, at which point `PRIMARY_PAIR = (1, 3)` would silently be
    comparing polls 2 and 4 -- a 600 s pair reported as the registered 300 s
    one. Refuse, do not renumber.
    """
    if len(set(indices)) != len(indices):
        return (f"repeated poll_index in {sorted(indices)}. Comparing a poll "
                "with itself yields S = 1.0 from one poll's data.")
    bad = [i for i in indices if not (1 <= i <= N_POLLS)]
    if bad:
        return (f"poll_index {bad} outside 1..{N_POLLS}. `poll_index` is "
                "1-based (capture_odds_repeat_poll.py:588).")
    return None


def _select_deciding_pair(
    available: set[int],
) -> tuple[Optional[tuple[int, int]], bool, str]:
    """§8's partial-capture rule, and nothing wider.

    Returns `(pair, substituted, reason)`; `pair is None` means
    UNRESOLVED -- INCOMPLETE. A partial capture reaching here still cannot be
    CONFIRMED or REFUTED: PC6 requires all four polls.
    """
    if set(PRIMARY_PAIR) <= available:
        return PRIMARY_PAIR, False, ""
    if set(FALLBACK_PAIR) <= available:
        return (FALLBACK_PAIR, True,
                "poll 3 absent -- sec 8 admits polls 1 and 4 alone through the "
                "PC2 fallback")
    return None, False, (
        f"have polls {sorted(available)}; sec 8 requires 1 and 3 (primary) or "
        "1 and 4 (PC2 fallback)")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Analyse a repeat-poll capture.")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)

    artefacts = sorted(
        (load_poll(p) for p in args.files), key=lambda a: a["poll_index"]
    )
    indices = [int(a["poll_index"]) for a in artefacts]
    domain_error = _check_index_domain(indices)
    if domain_error:
        print(f"REFUSED: {domain_error}")
        print("No verdict. Nothing was analysed.")
        return 2

    available = set(indices)
    complete = available == set(range(1, N_POLLS + 1))
    pair_idx, substituted, sub_reason = _select_deciding_pair(available)
    if pair_idx is None:
        print("=" * 72)
        print(f"VERDICT: UNRESOLVED -- INCOMPLETE. {sub_reason}")
        print("=" * 72)
        return 2

    rows = {a["poll_index"]: project(a) for a in artefacts}
    span_readable = {1, N_POLLS} <= available

    print("=" * 72)
    print("REPEAT POLL -- is `last_update` a per-line reprice timestamp?")
    print("registration: docs/measurements/"
          "2026-08-10-preregistration-odds-last-update-repeat-poll.md")
    print("=" * 72)
    # The frame, before the numbers (§S2 item 1). Amendment B §B1's permitted
    # wording names this slate by hand; printing what was actually captured
    # beside it is what makes a mismatch visible instead of assumed.
    first = artefacts[0]
    print(f"  captured frame  sport {first.get('sport_key')!r}  regions "
          f"{first.get('regions')}  markets {first.get('markets')}")
    for a in artefacts:
        print(f"  poll {a['poll_index']}  nominal T0+{a['nominal_offset_s']:4d}s"
              f"  realised +{a['realised_offset_s']:8.1f}s"
              f"  quotes {a['n_quotes_parsed']:5d}"
              f"  server remaining {a.get('x_requests_remaining')}")

    # --- the pair that decides, chosen by INDEX -------------------------------
    res = compare(rows[pair_idx[0]], rows[pair_idx[1]])
    s, n_adv, shares = statistic_s(res)
    if not substituted and n_adv < PC2_MIN_ADV_BOOKS and set(FALLBACK_PAIR) <= available:
        substituted = True
        sub_reason = f"N_adv = {n_adv} < {PC2_MIN_ADV_BOOKS} on the primary pair"
        pair_idx = FALLBACK_PAIR
        res = compare(rows[pair_idx[0]], rows[pair_idx[1]])
        s, n_adv, shares = statistic_s(res)

    n_books = len({p[1] for p in by_pair(rows[pair_idx[0]])}
                  & {p[1] for p in by_pair(rows[pair_idx[1]])})
    # `None`, not 0, when poll 4 is missing: an unmeasurable control must fail
    # PC5, never pass it by defaulting to a number.
    movers = movers_over_span(rows[1], rows[N_POLLS]) if span_readable else None
    # The same count restricted to the pair that actually decides. PC5 is and
    # stays evaluated on the full span (that is the registered threshold and it
    # is not being changed); this is printed beside it because the two can
    # disagree, and §7's own joint-reachability paragraph describes exactly the
    # world where they do -- movement confined to the 3 -> 4 leg satisfies PC5
    # while cell B was unreachable at the deciding 1 -> 3 interval. REPORTED,
    # NEVER GATING: no threshold is applied to it here and none may be added
    # after the data exists.
    movers_deciding = movers_over_span(rows[pair_idx[0]], rows[pair_idx[1]])
    total_spend = sum(a.get("cost_credits", 0) for a in artefacts)
    all_non_empty = all(a["n_quotes_parsed"] > 0 for a in artefacts)

    print(f"\ndeciding pair: poll {pair_idx[0]} -> {pair_idx[1]}"
          f"{'   (PC2 FALLBACK APPLIED)' if substituted else '   (PRIMARY)'}")
    if substituted:
        print(f"  substitution reason: {sub_reason}")
    if not complete:
        print(f"  PARTIAL CAPTURE -- polls present: {sorted(available)} "
              f"(sec 8). PC6 cannot pass; no CONFIRMED or REFUTED is available.")

    # --- the rival hypothesis, priced BEFORE the number (ADR 0026) -----------
    #
    # ADR 0026: every declaration branch names what else could have produced it,
    # and that naming is printed before the data rather than judged after it.
    # This block is printed on every run, whatever the verdict turns out to be.
    print("\nRIVAL HYPOTHESIS, PRICED BEFORE THE NUMBER (ADR 0026)")
    print("  REFUTED is CONDITIONAL. The rival lives in sec 5.1 of the")
    print("  registration, not sec 7: if the aggregator genuinely repriced most")
    print("  pairs inside the 300 s primary interval, S would fall below 0.20")
    print("  with `last_update` still not being a per-line reprice stamp -- a")
    print("  busy slate, not a tracking stamp. Sec 5.1 puts that at >= 80% of")
    print("  pairs and calls it entirely ordinary at 900 s, which is why 300 s")
    print("  was chosen; the prior points the other way and no threshold is")
    print("  attached to it here. The separating observable is the reprice rate")
    print("  at the deciding pair, (B + D) / BOTH, printed below. It is named")
    print("  now so it cannot be recruited afterwards, in either direction.")

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
    print(f"  excluded   NO-STAMP {res.no_stamp}   (unreadable, not static; "
          f"A+B+C+D+NO-STAMP = {res.cell_a + res.cell_b + res.cell_c + res.cell_d + res.no_stamp} = BOTH)")
    reprice_rate = (res.cell_b + res.cell_d) / res.both if res.both else 0.0
    print(f"  reprice rate at the deciding pair  (B + D) / BOTH = "
          f"{res.cell_b + res.cell_d} / {res.both} = {reprice_rate:.4f}"
          f"   <- the rival's separating observable, priced above")

    print("\nMOVERS -- the control (sec 6), printed before N_adv and S")
    print(f"  full span poll 1 -> {N_POLLS}       {movers} books   "
          f"<- PC5 is evaluated on THIS, and only this")
    print(f"  deciding pair {pair_idx[0]} -> {pair_idx[1]}       "
          f"{movers_deciding} books   <- REPORTED, NOT GATING")
    print("  Both are shown because they can disagree: PC5's span is 900s while "
          "the verdict\n  is decided at "
          f"{pair_idx[0]} -> {pair_idx[1]}, so PC5 can be satisfied entirely by "
          "movement outside the deciding\n  interval, leaving the refuting cell "
          "unreachable where it counts. No threshold\n  is applied to the "
          "restricted count and none may be added after the data.")

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
        ("PC5 control reaches the confound",
         movers is not None and movers >= PC5_MIN_MOVERS,
         (f"{movers} books moved a price over the full span, "
          f"need >= {PC5_MIN_MOVERS}") if movers is not None else
         (f"NOT EVALUABLE -- poll {N_POLLS} absent, so the full span cannot be "
          "read. An unmeasured control fails; it does not default to 0.")),
        ("PC6 the spend is real",
         complete and all_non_empty and total_spend == EXPECTED_TOTAL_CREDITS,
         f"{total_spend} credits over {len(artefacts)}/{N_POLLS} polls, "
         f"all non-empty: {all_non_empty}"),
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
    # ALWAYS the 1 -> 4 span, whatever the deciding pair is. This is a
    # deviation from the natural reading of §6 and it is **registered** --
    # Amendment B §B2 records it, calls it the more conservative of the two
    # readings (1 -> 4 is a superset window, so `moved` is at least as large,
    # `S_strict` at most as high, and the >= 0.90 leg harder to reach) and says
    # in terms that this file is not to be altered to match §6. Do not "fix"
    # this. The span is printed beside the value, as §B2 requires.
    strict = s_strict(rows[1], rows[N_POLLS], books_adv)
    print("\n" + "=" * 72)
    if s is not None and s >= CONFIRM_AT:
        print(f"VERDICT: CONFIRMED -- `last_update` is NOT a per-line reprice "
              f"timestamp.\n         S = {s:.4f} >= {CONFIRM_AT}")
        print(f"         S_strict = {strict:.4f}   span: poll 1 -> poll "
              f"{N_POLLS} (nominal {OFFSET_LAST_S}s), always (Amendment B sec B2)")
        if strict >= CONFIRM_AT:
            # The phrase "the strong wording" is RETIRED by Amendment B sec B1,
            # which was appended before poll 1 and which fixes the permitted
            # wording in advance. What follows is that paragraph, verbatim and
            # entire: "No wording beyond this is licensed by any value of
            # S_strict." It is printed rather than summarised precisely because
            # the previous version printed a phrase defined nowhere.
            print("         PERMITTED WORDING (Amendment B sec B1) -- this is "
                  "the WHOLE of what\n         this value of S_strict licenses, "
                  "and no wording beyond it:")
            print("           `last_update` is not a per-line reprice "
                  "timestamp. No price change\n           was observed anywhere "
                  "in the captured baseball_mlb / us,eu /\n           "
                  "h2h,spreads,totals slate between poll 1 and poll 4 (nominal "
                  "900 s),\n           for the bookmakers whose stamps "
                  "advanced. A reprice in a market,\n           region or sport "
                  "that was not requested remains an unexcluded cause\n         "
                  "  of the advance (sec 10) -- as does a price that moved and "
                  "moved back\n           between the two sampled instants "
                  "(sec 10).")
            print("         NOT licensed: 'no reprice occurred'; 'the books "
                  "were not repricing';\n         'the stamp is a scrape "
                  "clock'; 'the odds are stale'; 'our polling\n         "
                  "cadence'; or any claim about a sport, league, region, market "
                  "or\n         interval not captured. 'The strong wording' is "
                  "not a term of this\n         registration and may not be "
                  "used as one.")
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
