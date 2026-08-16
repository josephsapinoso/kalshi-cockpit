"""Score the one-sided prop recovery against its registered decision rule.

    .venv\\Scripts\\python.exe scripts/analyze_prop_onesided.py dump1.json ...

Registered at
`docs/measurements/2026-08-16-preregistration-prop-onesided-recovery.md`.
Every threshold, exclusion and gate below is a **registered constant**, fixed
before any recovered price was computed, and deliberately not a flag with a
default -- a flag would let a later reader move the bar after seeing the
answer, which is the whole degree of freedom the registration exists to remove.

WHERE THE INPUT COMES FROM
--------------------------
The `--json` output of `inspect_live_db.py prop-rungs`, taken on the live box:

    flyctl ssh console -a kalshi-cockpit \\
      -C "python /app/scripts/inspect_live_db.py prop-rungs --json --limit 20000"

This file is a laptop `Tool`. It must **not** enter the image: it opens no
database, touches no order path, and does arithmetic the inspector is
explicitly forbidden from doing. That split is the point -- the inspector is
reviewed once and stays a reader, and every number a verdict rests on is
derived here, in the open, beside the rule it feeds.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **The validation set is not the application set.** Error is measured only
  where a book quoted BOTH sides on an alternate rung. The recovery would be
  applied where it did not. If a book goes one-sided precisely when it is least
  confident or widest, every error here is a floor. §7 of the registration says
  so and no output of this script may be read past it.
- **Nothing about whether the recovered rows contain an edge.** They are
  comparisons, not bets. Only CLV against Kalshi's own close answers that.
- **Nothing about fills.** Both sides of every comparison are stored quotes.
- **Nothing about the fee.** Props are baseball, charged `k = 0.035` and priced
  at `0.070`. That understatement is unchanged by anything here.
- **One sweep per fixture, one dump.** No second horizon, no persistence claim.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.devig import DevigError, consensus_devig  # noqa: E402
from backend.kalshi.props import norm  # noqa: E402
from backend.runner import PROP_SIDES, SHARP_BOOKS  # noqa: E402

# ---------------------------------------------------------------------------
# Registered constants. §5 of the registration. Not flags.
# ---------------------------------------------------------------------------

# Gate A: `recoverable / kept`. Below this the change is refused on size alone,
# whatever the accuracy turns out to be.
GATE_A_MIN_RATIO = 0.5

# Gate B needs this many Level-2 rungs before it may speak at all.
GATE_B_MIN_N = 30

# Percentage points of fair probability. `0.5` sits under the 0.63-point fee
# headroom (ADR 0027); `1.5` is the middle of the 1-2 point devig-method
# spread; `0.3` is tighter on the signed median because a systematic shading
# moves every recovered row the same way and does not average out.
ADOPT_MEDIAN_ABS = 0.5
ADOPT_P90_ABS = 1.5
ADOPT_SIGNED_ABS = 0.3
REFUSE_MEDIAN_ABS = 1.5
REFUSE_SIGNED_ABS = 0.5

# `CLAUDE.md`: read `n` before the effect size. No per-book number below this.
MIN_PER_BOOK_N = 5

# A per-book median absolute Level-1 error above this disqualifies that book
# from an ADOPT even when the pooled figure passes. A pooled number is not a
# finding until the parts agree.
PER_BOOK_MAX_ABS = 1.5

OVER, UNDER = PROP_SIDES


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------


class RefusedInput(Exception):
    """The dump cannot carry a verdict. Named, so it cannot read as 0 rows."""


@dataclass(frozen=True)
class Rung:
    """One `(event, book, base_market, feed, player, point)` from the dump."""

    event: str
    book: str
    base_market: str
    is_alternate: bool
    player: str
    point: float
    over: Optional[float]
    under: Optional[float]
    quote_rows: int

    @property
    def key(self) -> tuple[str, str, str, str, float]:
        """Identity ACROSS feeds is what §4.2 joins on; the feed is separate."""
        return (self.event, self.book, self.base_market, self.player, self.point)

    @property
    def player_key(self) -> tuple[str, str, str, str]:
        return (self.event, self.book, self.base_market, self.player)

    @property
    def rung_key(self) -> tuple[str, str, str, float, bool]:
        """Identity across BOOKS, for building a consensus at one rung.

        **The player is part of this key and leaving it out is not a
        simplification.** `runner.prop_quotes_for_event` groups on
        `(base_market, player_key, point)` for the reason its docstring gives:
        one market key's rows are every rung of every player in the game, so a
        key without the player builds one "consensus" over a hundred unrelated
        prices. Dropped here once already -- the smoke run silently devigged
        four different players into a single book-set.
        """
        return (
            self.event,
            self.base_market,
            self.player,
            self.point,
            self.is_alternate,
        )

    @property
    def two_sided(self) -> bool:
        return self.over is not None and self.under is not None


@dataclass
class Exclusions:
    """§3's exclusions, counted rather than absorbed.

    Every one of these is a number the result document must print. A count that
    is provably zero on real data is either dead code or mis-routed, and both
    are findings -- this project has already shipped one `unreadable` counter
    that was 0 of 81,420 while a third of the population went out under it.
    """

    no_side_priced: int = 0
    price_not_decimal_odds: int = 0
    duplicated_side: int = 0

    def total(self) -> int:
        return (
            self.no_side_priced
            + self.price_not_decimal_odds
            + self.duplicated_side
        )


def load_rungs(paths: Iterable[Path]) -> tuple[list[Rung], Exclusions]:
    """Parse one or more `prop-rungs --json` dumps into rungs.

    **A truncated dump is refused, not trimmed.** `ORDER BY` makes a capped
    dump the alphabetical front of the record, not a sample of it, so a verdict
    computed over one would be a verdict about bookmakers whose names sort
    early. The inspector sets the flag; this is what acts on it.
    """
    rungs: list[Rung] = []
    excluded = Exclusions()
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("query") != "prop-rungs":
            raise RefusedInput(
                f"{path}: this is a {payload.get('query')!r} dump, not prop-rungs"
            )
        for section in payload["sections"]:
            if section.get("truncated"):
                raise RefusedInput(
                    f"{path}: section {section['title']!r} was truncated at "
                    f"{section.get('row_cap')} rows. Re-take it per fixture "
                    f"(--odds-event-id) or with a higher --limit; a prefix of "
                    f"the record is not a sample of it."
                )
            columns = section["columns"]
            for row in section["rows"]:
                item = dict(zip(columns, row))
                over = item["over_price"]
                under = item["under_price"]

                if over is None and under is None:
                    # Cannot happen through the query as written -- a rung
                    # exists because a side was priced. Counted anyway: the
                    # branch being unreachable is itself worth reporting.
                    excluded.no_side_priced += 1
                    continue
                if any(p is not None and p <= 1.0 for p in (over, under)):
                    excluded.price_not_decimal_odds += 1
                    continue
                sides_present = (over is not None) + (under is not None)
                if item["quote_rows"] > sides_present:
                    excluded.duplicated_side += 1
                    continue

                rungs.append(
                    Rung(
                        event=item["odds_event_id"],
                        book=item["bookmaker"],
                        base_market=item["base_market"],
                        is_alternate=bool(item["is_alternate"]),
                        player=norm(item["player"]),
                        point=float(item["point"]),
                        over=over,
                        under=under,
                        quote_rows=item["quote_rows"],
                    )
                )
    return rungs, excluded


# ---------------------------------------------------------------------------
# §4.2 -- the recovery
# ---------------------------------------------------------------------------


def overround(over: float, under: float) -> float:
    """`V = 1/o_over + 1/o_under`, the book's whole book on this rung. > 1."""
    return 1.0 / over + 1.0 / under


def primary_overrounds(rungs: Iterable[Rung]) -> dict[tuple[str, str, str, str], float]:
    """Median two-sided PRIMARY overround per `(event, book, market, player)`.

    Median rather than mean: a book with one mispriced rung on a ladder should
    not drag its whole margin estimate, and the count of contributing rungs is
    reported separately so a `V` resting on one observation is visible as such.

    **Primary only.** Estimating an alternate rung's margin from other
    alternate rungs would be circular -- the hypothesis under test is precisely
    that the alternate ladder inherits the primary's margin.
    """
    collected: dict[tuple[str, str, str, str], list[float]] = {}
    for rung in rungs:
        if rung.is_alternate or not rung.two_sided:
            continue
        collected.setdefault(rung.player_key, []).append(
            overround(rung.over, rung.under)
        )
    return {key: statistics.median(vs) for key, vs in collected.items()}


def recover_under(over: float, v: float) -> Optional[float]:
    """The Under price implied by an Over and the book's own overround.

    **`None`, never a clamp.** A non-positive implied Under means the Over
    alone already implies more than the book's whole book, so the assumption
    has failed on this rung -- and a clamped value would be a fabricated price
    entering a consensus that then reports a fair probability nobody quoted.
    """
    implied = v - 1.0 / over
    if implied <= 0.0:
        return None
    return 1.0 / implied


# ---------------------------------------------------------------------------
# §4.1 -- feasibility, reported FIRST
# ---------------------------------------------------------------------------


@dataclass
class Feasibility:
    kept: int = 0
    dropped: int = 0
    recoverable: int = 0
    unrecoverable: int = 0

    @property
    def ratio(self) -> Optional[float]:
        """`None` when nothing is kept -- a ratio with no denominator.

        Not `0.0` and not `inf`: "no two-sided alternate rung exists anywhere"
        is a different state from "the recovery adds nothing", and reporting
        the first as the second would put a verdict on an empty arm.
        """
        return self.recoverable / self.kept if self.kept else None


def feasibility(
    rungs: list[Rung], primaries: dict[tuple[str, str, str, str], float]
) -> tuple[Feasibility, dict[str, Feasibility], dict[str, Feasibility]]:
    """§4.1, pooled and split by bookmaker and by base market.

    The two splits exist because `CLAUDE.md` requires the parts beside the
    aggregate. They are returned rather than printed so the caller decides
    what a section looks like.
    """
    pooled = Feasibility()
    by_book: dict[str, Feasibility] = {}
    by_market: dict[str, Feasibility] = {}

    for rung in rungs:
        if not rung.is_alternate:
            continue
        targets = (
            pooled,
            by_book.setdefault(rung.book, Feasibility()),
            by_market.setdefault(rung.base_market, Feasibility()),
        )
        if rung.two_sided:
            for t in targets:
                t.kept += 1
            continue
        for t in targets:
            t.dropped += 1
        if rung.over is not None and rung.player_key in primaries:
            for t in targets:
                t.recoverable += 1
        else:
            for t in targets:
                t.unrecoverable += 1
    return pooled, by_book, by_market


# ---------------------------------------------------------------------------
# §4.3 -- Level 1, the mechanism error
# ---------------------------------------------------------------------------


@dataclass
class Errors:
    """A bag of signed percentage-point errors, summarised on demand."""

    values: list[float] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.values)

    def summary(self) -> Optional[dict[str, float]]:
        """`None` below the per-book floor, never a number computed from 2 rows."""
        if len(self.values) < MIN_PER_BOOK_N:
            return None
        absolute = sorted(abs(v) for v in self.values)
        return {
            "n": len(self.values),
            "median_signed": statistics.median(self.values),
            "median_abs": statistics.median(absolute),
            "p90_abs": _p90(absolute),
        }


def _p90(sorted_values: list[float]) -> float:
    """Nearest-rank 90th percentile.

    Nearest-rank rather than interpolated: on a small `n` an interpolated p90
    invents a value between two observations, and the bar it is compared
    against was set as "9 of 10 rungs are inside this", which is a rank
    statement.
    """
    if not sorted_values:
        raise ValueError("p90 of nothing")
    index = max(0, -(-len(sorted_values) * 9 // 10) - 1)
    return sorted_values[index]


def level_one(
    rungs: list[Rung], primaries: dict[tuple[str, str, str, str], float]
) -> tuple[dict[str, Errors], int]:
    """Hold out the Under on two-sided ALTERNATE rungs and recover it.

    Returns per-book errors and the count of rungs where §4.2 refused
    (`implied_under_hat <= 0`). That refusal count is reported: a recovery that
    is accurate on the rungs it can do and impossible on a third of them is not
    a usable recovery, and pooling only over the successes would hide it.
    """
    by_book: dict[str, Errors] = {}
    refused = 0
    for rung in rungs:
        if not rung.is_alternate or not rung.two_sided:
            continue
        v = primaries.get(rung.player_key)
        if v is None:
            continue
        under_hat = recover_under(rung.over, v)
        if under_hat is None:
            refused += 1
            continue
        p_true = (1.0 / rung.over) / overround(rung.over, rung.under)
        p_hat = (1.0 / rung.over) / overround(rung.over, under_hat)
        by_book.setdefault(rung.book, Errors()).values.append(
            100.0 * (p_hat - p_true)
        )
    return by_book, refused


# ---------------------------------------------------------------------------
# §4.4 -- Level 2, the consensus error. This is what the rule reads.
# ---------------------------------------------------------------------------


def level_two(
    rungs: list[Rung], primaries: dict[tuple[str, str, str, str], float]
) -> tuple[Errors, dict[str, int], int]:
    """Rebuild the consensus twice per rung: as quoted, and fully recovered.

    Every contributing book's Under is replaced, not just one. Replacing a
    single book would measure a blend of the recovery and the quotes it sits
    beside, and the deployed change would replace every one-sided book it could.

    Returns the errors, how many rungs each book contributed to, and the count
    of rungs dropped because a book's recovery refused. The composition map is
    what `CLAUDE.md`'s "print the largest contributor's share" is computed from.
    """
    grouped: dict[tuple[str, str, str, float, bool], list[Rung]] = {}
    for rung in rungs:
        if not rung.is_alternate or not rung.two_sided:
            continue
        grouped.setdefault(rung.rung_key, []).append(rung)

    errors = Errors()
    composition: dict[str, int] = {}
    dropped = 0
    for members in grouped.values():
        usable = [r for r in members if r.player_key in primaries]
        if len(usable) < 2:
            continue

        true_quotes: dict[str, list[float]] = {}
        hat_quotes: dict[str, list[float]] = {}
        refused_here = False
        for rung in usable:
            under_hat = recover_under(rung.over, primaries[rung.player_key])
            if under_hat is None:
                refused_here = True
                break
            true_quotes[rung.book] = [rung.over, rung.under]
            hat_quotes[rung.book] = [rung.over, under_hat]
        if refused_here:
            dropped += 1
            continue

        try:
            true_result, _ = consensus_devig(
                PROP_SIDES, true_quotes, sharp_books=SHARP_BOOKS
            )
            hat_result, _ = consensus_devig(
                PROP_SIDES, hat_quotes, sharp_books=SHARP_BOOKS
            )
        except DevigError:
            # A book set that cannot be devigged is a finding, not a crash --
            # and not a zero error either, which is what silently skipping it
            # into the pooled median would amount to.
            dropped += 1
            continue

        errors.values.append(
            100.0
            * (
                hat_result.conservative_probability(OVER)
                - true_result.conservative_probability(OVER)
            )
        )
        for book in true_quotes:
            composition[book] = composition.get(book, 0) + 1
    return errors, composition, dropped


# ---------------------------------------------------------------------------
# §5 -- the decision rule
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Verdict:
    gate_a: str
    gate_b: str
    failing_books: tuple[str, ...]
    note: str


def decide(
    pooled: Feasibility,
    level2: Errors,
    per_book: dict[str, Errors],
) -> Verdict:
    """Apply §5 exactly as registered, in the registered order.

    Gate A first and on its own: if the prize is not there, the accuracy
    numbers are still reported but carry no verdict. That ordering is part of
    the registration, not a presentational choice -- deciding on accuracy after
    seeing that the prize was small is how a marginal improvement gets adopted
    for reasons the document never sanctioned.
    """
    ratio = pooled.ratio
    if ratio is None:
        return Verdict(
            gate_a="UNMEASURABLE",
            gate_b="NOT REACHED",
            failing_books=(),
            note=(
                "no two-sided alternate rung exists, so there is no denominator "
                "and no held-out set. This is an absence of data, not a result."
            ),
        )
    if ratio < GATE_A_MIN_RATIO:
        return Verdict(
            gate_a="NOT WORTH IT",
            gate_b="NOT REACHED",
            failing_books=(),
            note=(
                f"recoverable/kept = {ratio:.3f} < {GATE_A_MIN_RATIO}. Refused "
                f"on size alone; accuracy below is reported and carries no "
                f"verdict."
            ),
        )

    summary = level2.summary()
    if summary is None or summary["n"] < GATE_B_MIN_N:
        n = len(level2)
        return Verdict(
            gate_a="PASS",
            gate_b="UNRESOLVED",
            failing_books=(),
            note=(
                f"n = {n} Level-2 rungs, below the registered floor of "
                f"{GATE_B_MIN_N}. Not enough rungs existed to decide -- a "
                f"failure of supply, not of the hypothesis, and the one case "
                f"§9 licenses a new registration for."
            ),
        )

    failing = tuple(
        sorted(
            book
            for book, errs in per_book.items()
            if (s := errs.summary()) is not None and s["median_abs"] > PER_BOOK_MAX_ABS
        )
    )

    if (
        summary["median_abs"] >= REFUSE_MEDIAN_ABS
        or abs(summary["median_signed"]) >= REFUSE_SIGNED_ABS
    ):
        return Verdict(
            gate_a="PASS",
            gate_b="REFUSE",
            failing_books=failing,
            note=(
                f"median |delta| = {summary['median_abs']:.3f} pt, median signed "
                f"= {summary['median_signed']:+.3f} pt. The recovery injects as "
                f"much error as the disagreement rule 2 already refuses to trade "
                f"through."
            ),
        )

    if (
        summary["median_abs"] <= ADOPT_MEDIAN_ABS
        and summary["p90_abs"] <= ADOPT_P90_ABS
        and abs(summary["median_signed"]) <= ADOPT_SIGNED_ABS
    ):
        if failing:
            return Verdict(
                gate_a="PASS",
                gate_b="ADOPT-PARTIAL",
                failing_books=failing,
                note=(
                    "the pooled bars pass but the parts do not agree. The "
                    "recovery applies only to the books not named above."
                ),
            )
        return Verdict(
            gate_a="PASS",
            gate_b="ADOPT",
            failing_books=(),
            note=(
                "every registered bar cleared, pooled and per book. Wiring it "
                "into `prop_quotes_for_event` is a separate commit."
            ),
        )

    return Verdict(
        gate_a="PASS",
        gate_b="UNRESOLVED",
        failing_books=failing,
        note=(
            "between the ADOPT and REFUSE bars with sufficient n. §9: the "
            "design was given its chance and did not clear a bar fixed before "
            "the data was seen, and no further look is licensed."
        ),
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _fmt_summary(summary: Optional[dict[str, float]], n: int) -> str:
    if summary is None:
        return f"n = {n}  INSUFFICIENT (floor is {MIN_PER_BOOK_N})"
    return (
        f"n = {summary['n']:<5d} median signed {summary['median_signed']:+7.3f}  "
        f"median |e| {summary['median_abs']:6.3f}  p90 |e| {summary['p90_abs']:6.3f}"
    )


def report(
    rungs: list[Rung],
    excluded: Exclusions,
    primaries: dict[tuple[str, str, str, str], float],
) -> tuple[str, Verdict]:
    pooled, by_book_feas, by_market_feas = feasibility(rungs, primaries)
    l1_by_book, l1_refused = level_one(rungs, primaries)
    l2, composition, l2_dropped = level_two(rungs, primaries)
    verdict = decide(pooled, l2, l1_by_book)

    out: list[str] = []
    out.append("# One-sided prop recovery")
    out.append(
        "# Registered: "
        "docs/measurements/2026-08-16-preregistration-prop-onesided-recovery.md"
    )
    out.append("")

    out.append("§3 population and exclusions")
    out.append("-" * 40)
    out.append(f"rungs admitted                 {len(rungs)}")
    out.append(f"excluded: no side priced       {excluded.no_side_priced}")
    out.append(f"excluded: price <= 1.0         {excluded.price_not_decimal_odds}")
    out.append(f"excluded: a side quoted twice  {excluded.duplicated_side}")
    out.append(f"two-sided primary estimates    {len(primaries)}")
    out.append("")

    out.append("§4.1 feasibility -- READ THIS BEFORE ANY ACCURACY NUMBER")
    out.append("-" * 40)
    ratio = pooled.ratio
    out.append(
        f"alternate rungs kept today     {pooled.kept}\n"
        f"alternate rungs dropped        {pooled.dropped}\n"
        f"  of which recoverable         {pooled.recoverable}\n"
        f"  of which unrecoverable       {pooled.unrecoverable}\n"
        f"recoverable / kept             "
        + ("n/a (no kept rungs)" if ratio is None else f"{ratio:.3f}")
    )
    out.append("")
    out.append("by bookmaker:")
    for book in sorted(by_book_feas):
        f = by_book_feas[book]
        r = f.ratio
        out.append(
            f"  {book:<18} kept {f.kept:<5d} dropped {f.dropped:<5d} "
            f"recoverable {f.recoverable:<5d} ratio "
            + ("n/a" if r is None else f"{r:.3f}")
        )
    out.append("by base market:")
    for market in sorted(by_market_feas):
        f = by_market_feas[market]
        r = f.ratio
        out.append(
            f"  {market:<26} kept {f.kept:<5d} dropped {f.dropped:<5d} "
            f"recoverable {f.recoverable:<5d} ratio "
            + ("n/a" if r is None else f"{r:.3f}")
        )
    out.append("")

    out.append("§4.3 Level 1 -- per-book mechanism error, percentage points")
    out.append("-" * 40)
    out.append(f"rungs where the recovery refused (implied under <= 0): {l1_refused}")
    total_l1 = sum(len(e) for e in l1_by_book.values())
    for book in sorted(l1_by_book):
        errs = l1_by_book[book]
        share = f"{100.0 * len(errs) / total_l1:.1f}%" if total_l1 else "n/a"
        out.append(
            f"  {book:<18} {_fmt_summary(errs.summary(), len(errs))}  "
            f"share {share}"
        )
    out.append("")

    out.append("§4.4 Level 2 -- consensus error, percentage points. THE RULE READS THIS")
    out.append("-" * 40)
    out.append(f"rungs dropped (recovery refused or undevigable): {l2_dropped}")
    out.append(f"  pooled            {_fmt_summary(l2.summary(), len(l2))}")
    if composition:
        top = max(composition, key=lambda b: composition[b])
        total = sum(composition.values())
        out.append(
            f"  largest contributor {top} at "
            f"{100.0 * composition[top] / total:.1f}% of book-appearances"
        )
        out.append(
            "  composition: "
            + ", ".join(f"{b}={composition[b]}" for b in sorted(composition))
        )
    out.append("")

    out.append("§5 verdict")
    out.append("-" * 40)
    out.append(f"Gate A (feasibility): {verdict.gate_a}")
    out.append(f"Gate B (accuracy):    {verdict.gate_b}")
    if verdict.failing_books:
        out.append(
            "books above the per-book bar: " + ", ".join(verdict.failing_books)
        )
    out.append(verdict.note)
    out.append("")
    out.append(
        "§7 stands over every line above: the error is measured only where a "
        "book chose to quote both sides, and applied where it did not."
    )
    return "\n".join(out), verdict


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="analyze_prop_onesided.py",
        description=(
            "Score the one-sided prop recovery against its registered rule. "
            "Input is one or more `inspect_live_db.py prop-rungs --json` dumps."
        ),
    )
    parser.add_argument("dumps", nargs="+", type=Path, help="prop-rungs JSON dumps")
    parser.add_argument(
        "--json", action="store_true", help="emit the verdict as JSON as well"
    )
    args = parser.parse_args(argv)

    # The section headings below are `§4.1`, `§4.4` and so on, because those
    # are the names the registration gives them and a result document that
    # cited different ones would be citing nothing. On a Windows console the
    # default cp1252 pipe turns every one of them into a replacement
    # character, so the encoding is set rather than the headings weakened.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        rungs, excluded = load_rungs(args.dumps)
    except RefusedInput as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    if not rungs:
        # Not a verdict. An empty region of a transcript reads as success.
        print("0 rungs admitted. Nothing to score, and this is not a REFUSE.")
        return 1

    primaries = primary_overrounds(rungs)
    text, verdict = report(rungs, excluded, primaries)
    print(text)
    if args.json:
        print(
            json.dumps(
                {
                    "gate_a": verdict.gate_a,
                    "gate_b": verdict.gate_b,
                    "failing_books": list(verdict.failing_books),
                    "note": verdict.note,
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
