"""Is the desk present at the moment Joe actually bets? The registered analyzer.

Implements §3 through §7 of
`docs/measurements/2026-09-03-presence-at-the-moment-of-a-bet-registration.md`
and its Amendment 1 (§B.6, E0–E7) over four `inspect_live_db.py --json`
captures, and nothing else. It runs on the dev machine against files; it never
opens the live database.

    python scripts/analyse_bet_presence.py \
        --fills   h4-balance-spans.json \
        --visits  visit-freshness.json  \
        --manual  manual-orders-audit.json \
        --combos  combo-bids-tail.json

Committed before the four reads were taken, as §11.3 requires, and amended
blind (Amendment 1) after the first run refused above the line where the first
distance is computed. Every constant here is the registration's; changing one
is an amendment, not a tweak.

The structural refusal of §6.2 is a hard branch: below `S_MIN` sittings or
`D_MIN` budget days this prints `SAMPLE NOT REACHED` and **does not compute**
`K`, any band count, any distance or any p-value. That is not a display
choice. A number that exists but is "not reported" gets read. Per E5 the
§2.4 exclusion is applied to the population *before* the floor is evaluated.

What this does not establish
----------------------------
- **Causation, in either direction.** Presence is co-occurrence of a fill
  timestamp with a heartbeat interval. §9.1.
- **Anything about bets placed off Kalshi**, which `fills` cannot see.
- **Anything about money.** Only `filled_ms`, `is_taker`, `source` and — as
  a join key only, never printed, never grouped by (Amendment 1 §B.3) —
  `ticker` are read from the fills section; `price_tenths`, `count` and
  `fee_actual` sit in the same rows and are never touched (§9.10). The
  prohibition is in `_fill_from_row`, which names the columns it reads.
- **A rate.** `n = 1` operator, one window. §9.8.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

# --- Registered constants. Every one traces to a section of the registration.
# §2.2 names 2026-09-04T00:00:00Z five times and printed `1788652800000` beside
# it once; that integer is 2026-09-06. Amendment 1 §A: the date is authoritative.
W_END_MS = 1_788_480_000_000  # §2.2  2026-09-04T00:00:00Z
SITTING_GAP_MS = 3_600_000  # §3.1
B5_MS = 300_000  # §4  DEFAULT_ATTENTION_TTL_MS
B30_MS = 1_800_000  # §4
S_MIN = 8  # §0.2
D_MIN = 5  # §3.3
ALPHA = 0.005  # §6.1  0.02 family-wise over four tests
PERM_DRAWS = 10_000  # §5.2
PERM_SEED = 20_260_903  # §5.2
PERM_MIN_ADMISSIBLE = 4  # §5.2
DAY_MS = 86_400_000
BUDGET_DAY_START_HOUR = 10  # §3.3  credits-day's 10:00Z boundary
SKEW_MS = 60_000  # C6
SENSITIVITY_GAPS_MS = (1_800_000, 7_200_000)  # §3.1  30 and 120 minutes, no verdict
DESCRIPTIVE_EDGES_MIN = (0, 5, 30, 60, 180)  # §4  descriptive, no verdict
SHIFT_DAYS = tuple(d for d in range(-14, 15) if d != 0)  # §5.2

UNRESOLVED_EXCLUSION = "UNRESOLVED — EXCLUSION UNEXECUTABLE"


def _iso(ms: Optional[int]) -> Optional[str]:
    if ms is None:
        return None
    return (
        datetime.fromtimestamp(ms / 1000, timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


# ---------------------------------------------------------------------------
# Reading the captures
# ---------------------------------------------------------------------------


class CaptureError(RuntimeError):
    """A capture is not admissible evidence. Refuse, do not substitute."""


def load_sections(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    sections = data.get("sections")
    if not isinstance(sections, list):
        raise CaptureError(f"{path}: no 'sections' list; is this --json output?")
    return sections


def find_section(
    sections: Sequence[dict[str, Any]], prefix: str
) -> Optional[dict[str, Any]]:
    for s in sections:
        if str(s.get("title", "")).startswith(prefix):
            return s
    return None


def section_starting(sections: Sequence[dict[str, Any]], prefix: str) -> dict[str, Any]:
    s = find_section(sections, prefix)
    if s is None:
        titles = [x.get("title") for x in sections]
        raise CaptureError(f"no section titled {prefix!r}; have {titles}")
    return s


def col(section: dict[str, Any], name: str) -> int:
    columns = section["columns"]
    if name not in columns:
        raise CaptureError(f"section {section['title']!r} has no column {name!r}")
    return columns.index(name)


def require_not_truncated(section: dict[str, Any]) -> None:
    """C3 / E0. A truncated population is a population cut by a row cap."""
    if section.get("truncated"):
        raise CaptureError(
            f"C3: section {section['title']!r} is TRUNCATED at row cap "
            f"{section.get('row_cap')}; re-run with a higher --limit"
        )


def capture_taken_ms(path: Path) -> tuple[int, str]:
    """When the capture was taken, and which clock says so. E0.

    Prefers the capture's own `generated_at_ms` -- the inspector stamps it
    from the server clock since 2026-09-04 -- and falls back to the file's
    mtime only when the key is absent. The first result (§4) had to rest E0
    on mtimes and git chronology because the captures carried no stamp;
    the returned source string is printed so a reader can see which one
    E0 stood on.
    """
    try:
        stamp = json.loads(path.read_text(encoding="utf-8")).get("generated_at_ms")
    except (OSError, ValueError, AttributeError):
        stamp = None
    if isinstance(stamp, int) and not isinstance(stamp, bool):
        return stamp, "generated_at_ms"
    return int(os.path.getmtime(path) * 1000), "mtime"


@dataclass(frozen=True)
class Fill:
    filled_ms: int
    is_taker: Optional[int]
    source: Optional[str]
    # Amendment 1 §B.3: a join key and nothing else. Compared for equality
    # against a set read from the ORDER tables; never printed, never grouped by.
    ticker: Optional[str]


def _fill_from_row(section: dict[str, Any], row: Sequence[Any]) -> Fill:
    """The only columns this analysis may read. §9.10 as amended."""
    taker = row[col(section, "is_taker")]
    return Fill(
        filled_ms=int(row[col(section, "filled_ms")]),
        is_taker=None if taker is None else int(taker),
        source=row[col(section, "source")],
        ticker=row[col(section, "ticker")],
    )


def read_fills(path: Path) -> list[Fill]:
    sections = load_sections(path)
    c = section_starting(sections, "C. fills since study start")
    require_not_truncated(c)
    return [_fill_from_row(c, r) for r in c["rows"]]


@dataclass(frozen=True)
class Visit:
    start_ms: int
    end_ms: int


def read_visits(path: Path) -> tuple[list[Visit], int, int]:
    """Visits, `W_start`, and the visit gap the inspector clustered with.

    `W_start = MIN(seen_ms)` is the first visit's first stamp — true only when
    `--since` preceded every heartbeat (C2), which the caller asserts by
    passing a `--since` before schema v21. The inspector's "visit window"
    section carries `--since` itself, not MIN(seen_ms), so it is not used.
    """
    sections = load_sections(path)
    per_visit = section_starting(sections, "desk_attention visits since")
    require_not_truncated(per_visit)
    if not per_visit["rows"]:
        raise CaptureError("visit-freshness returned no visits; no W_start exists")
    s_i, e_i = col(per_visit, "start_ms"), col(per_visit, "end_ms")
    visits = sorted(
        (Visit(int(r[s_i]), int(r[e_i])) for r in per_visit["rows"]),
        key=lambda v: v.start_ms,
    )
    summary = section_starting(sections, "visit-freshness summary")
    gap_ms = None
    for r in summary["rows"]:
        if r[0] == "visit_gap_ms":
            gap_ms = int(r[1])
    if gap_ms is None:
        raise CaptureError("visit-freshness summary carries no visit_gap_ms")
    return visits, visits[0].start_ms, gap_ms


@dataclass(frozen=True)
class DeskOrder:
    """One desk-placed combo order, on the order side only. E2/E3."""

    placed_ms: int
    dry_run: int
    status: Optional[str]
    cancelled_ms: Optional[int]
    cancel_reduced_by: Optional[float]
    count: Optional[float]
    ticker: Optional[str]

    @property
    def cleared_by_venue(self) -> bool:
        """E3: the venue's own cancel reply says the whole quantity was resting."""
        return (
            self.status == "cancelled"
            and self.cancelled_ms is not None
            and self.cancel_reduced_by is not None
            and self.count is not None
            and float(self.cancel_reduced_by) == float(self.count)
        )


@dataclass
class ExclusionInputs:
    """Everything E0–E4 read from the order side. No fill enters here."""

    manual_real_rows: int
    manual_tickers: Optional[set[str]]  # None when section E is absent
    combo_orders: list[DeskOrder]
    combo_tail_truncated: bool
    combo_tail_whole_table: bool  # rows returned < requested


def _f(x: Any) -> Optional[float]:
    return None if x is None else float(x)


def read_exclusion_inputs(manual_path: Path, combos_path: Path) -> ExclusionInputs:
    m_sections = load_sections(manual_path)
    m = section_starting(m_sections, "A. the hand-bet census")
    if not m["rows"]:
        raise CaptureError("manual-orders-audit census section is empty")
    manual_real = int(m["rows"][0][col(m, "real_orders")])
    e = find_section(m_sections, "E. rows per ticker")
    manual_tickers: Optional[set[str]] = None
    if e is not None:
        t_i = col(e, "ticker")
        manual_tickers = {str(r[t_i]) for r in e["rows"]}

    c = section_starting(load_sections(combos_path), "combo_orders: last")
    orders = [
        DeskOrder(
            placed_ms=int(r[col(c, "placed_ms")]),
            dry_run=int(r[col(c, "dry_run")] or 0),
            status=r[col(c, "status")],
            cancelled_ms=(
                None if r[col(c, "cancelled_ms")] is None else int(r[col(c, "cancelled_ms")])
            ),
            cancel_reduced_by=_f(r[col(c, "cancel_reduced_by")]),
            count=_f(r[col(c, "count")]),
            ticker=r[col(c, "ticker")],
        )
        for r in c["rows"]
    ]
    cap = c.get("row_cap")
    whole = cap is not None and c["row_count"] < int(cap)
    return ExclusionInputs(
        manual_real_rows=manual_real,
        manual_tickers=manual_tickers,
        combo_orders=orders,
        combo_tail_truncated=bool(c.get("truncated")),
        combo_tail_whole_table=whole,
    )


# ---------------------------------------------------------------------------
# §2.4 as amended: E0–E4, executed on the order side
# ---------------------------------------------------------------------------


@dataclass
class Exclusion:
    n_desk_orders: int  # |O|
    n_cleared_by_venue: int
    n_residual: int  # |R|
    n_tickers: int  # |T|, printed as an integer only
    tickers: set[str] = field(default_factory=set, repr=False)  # never printed
    refusal: Optional[str] = None


def execute_exclusion(inputs: ExclusionInputs, w_end: int) -> Exclusion:
    if inputs.combo_tail_truncated or not inputs.combo_tail_whole_table:
        return Exclusion(0, 0, 0, 0, refusal="E0: the combo tail is not the whole table")
    tickers: set[str] = set()
    if inputs.manual_real_rows > 0:
        if inputs.manual_tickers is None:
            return Exclusion(0, 0, 0, 0, refusal="E1: manual_orders has real rows and section E is absent")
        tickers |= inputs.manual_tickers
    desk = [o for o in inputs.combo_orders if o.dry_run == 0 and o.placed_ms < w_end]
    cleared = [o for o in desk if o.cleared_by_venue]
    residual = [o for o in desk if not o.cleared_by_venue]
    for o in residual:
        if o.ticker is None:
            return Exclusion(0, 0, 0, 0, refusal="E4: a residual desk order has no ticker to attribute by")
        tickers.add(str(o.ticker))
    return Exclusion(
        n_desk_orders=len(desk),
        n_cleared_by_venue=len(cleared),
        n_residual=len(residual),
        n_tickers=len(tickers),
        tickers=tickers,
    )


# ---------------------------------------------------------------------------
# §2 population, §3 sittings
# ---------------------------------------------------------------------------


@dataclass
class Population:
    taker_in_window: list[int]  # filled_ms, sorted
    maker_in_window: list[int]
    unclassifiable: int = 0  # pre-W_start hand fills
    after_window: int = 0
    engine: int = 0
    excluded_by_ticker: int = 0  # E4, both is_taker values
    other_source: dict[str, int] = field(default_factory=dict)


def classify(
    fills: Sequence[Fill], w_start: int, w_end: int, excluded_tickers: set[str]
) -> Population:
    pop = Population(taker_in_window=[], maker_in_window=[])
    for f in fills:
        if f.source == "engine":
            pop.engine += 1
            continue
        if f.source != "venue_hand":
            key = "NULL" if f.source is None else str(f.source)
            pop.other_source[key] = pop.other_source.get(key, 0) + 1
            continue
        if f.filled_ms < w_start:
            pop.unclassifiable += 1
            continue
        if f.filled_ms >= w_end:
            pop.after_window += 1
            continue
        if f.ticker is not None and str(f.ticker) in excluded_tickers:
            pop.excluded_by_ticker += 1  # E4/E5: before sittings are formed
            continue
        if f.is_taker == 1:
            pop.taker_in_window.append(f.filled_ms)
        else:
            pop.maker_in_window.append(f.filled_ms)
    pop.taker_in_window.sort()
    pop.maker_in_window.sort()
    return pop


def sittings(fill_ms: Sequence[int], gap_ms: int = SITTING_GAP_MS) -> list[list[int]]:
    """Maximal runs with no gap over `gap_ms`. Timed at the first fill. §3.1."""
    runs: list[list[int]] = []
    for ms in sorted(fill_ms):
        if runs and ms - runs[-1][-1] <= gap_ms:
            runs[-1].append(ms)
        else:
            runs.append([ms])
    return runs


def budget_day(ms: int) -> int:
    """Integer index of the 10:00Z-bounded budget day containing `ms`. §3.3."""
    return (ms - BUDGET_DAY_START_HOUR * 3_600_000) // DAY_MS


# ---------------------------------------------------------------------------
# §4 the cut
# ---------------------------------------------------------------------------


def present(ms: int, visits: Sequence[Visit], band_ms: int) -> bool:
    return any(v.start_ms - band_ms <= ms <= v.end_ms + band_ms for v in visits)


def distance_ms(ms: int, visits: Sequence[Visit]) -> int:
    """Distance to the nearest visit interval; 0 when strictly inside one."""
    best: Optional[int] = None
    for v in visits:
        if v.start_ms <= ms <= v.end_ms:
            return 0
        d = v.start_ms - ms if ms < v.start_ms else ms - v.end_ms
        best = d if best is None else min(best, d)
    if best is None:
        raise CaptureError("no visits to measure distance against")
    return best


def within_skew_of_edge(ms: int, visits: Sequence[Visit], band_ms: int) -> bool:
    """C6: would a `|skew| <= 60 s` shift move this sitting across the band?"""
    for v in visits:
        for edge in (v.start_ms - band_ms, v.end_ms + band_ms):
            if abs(ms - edge) <= SKEW_MS:
                return True
    return False


# ---------------------------------------------------------------------------
# §5 statistics — exact tails only, never a normal approximation
# ---------------------------------------------------------------------------


def binom_pmf(k: int, n: int, p: float) -> float:
    return math.comb(n, k) * (p**k) * ((1 - p) ** (n - k))


def binom_lower_tail(k: int, n: int, p: float) -> float:
    """P(K <= k | n, p)."""
    return sum(binom_pmf(i, n, p) for i in range(0, k + 1))


def binom_upper_tail(k: int, n: int, p: float) -> float:
    """P(K >= k | n, p)."""
    return sum(binom_pmf(i, n, p) for i in range(k, n + 1))


def admissible_shifts(ms: int, w_start: int, w_end: int) -> list[int]:
    return [d for d in SHIFT_DAYS if w_start <= ms + d * DAY_MS < w_end]


@dataclass(frozen=True)
class PermResult:
    feasible: bool
    p_value: Optional[float]
    min_admissible: int
    draws: int


def permutation_p(
    sitting_ms: Sequence[int],
    visits: Sequence[Visit],
    band_ms: int,
    w_start: int,
    w_end: int,
    k_obs: int,
) -> PermResult:
    """§5.2: independent per-sitting whole-day shift, seeded, one-sided upper."""
    adm = [admissible_shifts(ms, w_start, w_end) for ms in sitting_ms]
    min_adm = min((len(a) for a in adm), default=0)
    if min_adm < PERM_MIN_ADMISSIBLE:
        return PermResult(False, None, min_adm, 0)
    rng = random.Random(PERM_SEED)
    ge = 0
    for _ in range(PERM_DRAWS):
        k_star = 0
        for ms, choices in zip(sitting_ms, adm):
            shifted = ms + rng.choice(choices) * DAY_MS
            if present(shifted, visits, band_ms):
                k_star += 1
        if k_star >= k_obs:
            ge += 1
    return PermResult(True, (1 + ge) / (PERM_DRAWS + 1), min_adm, PERM_DRAWS)


def theta_wall(visits: Sequence[Visit], band_ms: int, w_start: int, w_end: int) -> float:
    """Halo-dilated attended share of wall clock. Descriptive only. §5.2, §9.4."""
    intervals = sorted(
        (max(w_start, v.start_ms - band_ms), min(w_end, v.end_ms + band_ms))
        for v in visits
    )
    covered = 0
    cur_s: Optional[int] = None
    cur_e: Optional[int] = None
    for s, e in intervals:
        if e <= s:
            continue
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                covered += cur_e - cur_s  # type: ignore[operator]
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        covered += cur_e - cur_s  # type: ignore[operator]
    return covered / (w_end - w_start)


# ---------------------------------------------------------------------------
# §6 the verdict
# ---------------------------------------------------------------------------


@dataclass
class ArmResult:
    band_ms: int
    k: int
    p_gap: float
    perm: PermResult
    theta_wall: float
    p_wall: float
    skew_sensitive: int  # sittings within 60 s of a band edge


def arm(
    sitting_ms: Sequence[int], visits: Sequence[Visit], band_ms: int, w_start: int, w_end: int
) -> ArmResult:
    s = len(sitting_ms)
    k = sum(1 for ms in sitting_ms if present(ms, visits, band_ms))
    tw = theta_wall(visits, band_ms, w_start, w_end)
    return ArmResult(
        band_ms=band_ms,
        k=k,
        p_gap=binom_lower_tail(k, s, 0.5),
        perm=permutation_p(sitting_ms, visits, band_ms, w_start, w_end, k),
        theta_wall=tw,
        p_wall=binom_upper_tail(k, s, tw),
        skew_sensitive=sum(1 for ms in sitting_ms if within_skew_of_edge(ms, visits, band_ms)),
    )


def primary_verdict(a: ArmResult) -> str:
    """§6.3 on one arm's numbers. Preconditions are applied by the caller."""
    gap = a.p_gap <= ALPHA
    presence = a.perm.feasible and a.perm.p_value is not None and a.perm.p_value <= ALPHA
    if gap and presence:
        return "PARTIAL PRESENCE"
    if gap:
        return "PRESENCE GAP SUPPORTED"
    if presence:
        return "PRESENCE GAP REFUTED"
    if not a.perm.feasible:
        return "UNRESOLVED — PERMUTATION INFEASIBLE"
    return "UNRESOLVED — NEITHER ARM CLEARED"


@dataclass
class Report:
    lines: list[str] = field(default_factory=list)
    verdict: str = ""

    def add(self, s: str = "") -> None:
        self.lines.append(s)


def analyse(
    fills: Sequence[Fill],
    visits: Sequence[Visit],
    w_start: int,
    inputs: ExclusionInputs,
    *,
    w_end: int = W_END_MS,
    visit_gap_ms: Optional[int] = None,
    captured_ms: Optional[Sequence[int]] = None,
) -> Report:
    rep = Report()
    rep.add("PRESENCE AT THE MOMENT OF A BET — registered analyzer (Amendment 1)")
    rep.add(f"window        [{_iso(w_start)}, {_iso(w_end)})  W_start = MIN(seen_ms)")
    rep.add(f"visits        {len(visits)}   (inspector visit gap {visit_gap_ms} ms)")

    # E0 — captures at or after W_end.
    if captured_ms is not None:
        earliest = min(captured_ms)
        rep.add(f"captures      earliest written {_iso(earliest)}")
        if earliest < w_end:
            rep.verdict = UNRESOLVED_EXCLUSION
            rep.add("E0: a capture predates W_end; the read was early.")
            rep.add(f"VERDICT   {rep.verdict}")
            return rep

    # E0–E4 — the exclusion, on the order side, before anything else.
    ex = execute_exclusion(inputs, w_end)
    rep.add()
    rep.add("§2.4 exclusion (Amendment 1, E0–E4)")
    rep.add(f"  manual_orders real rows      {inputs.manual_real_rows}")
    if ex.refusal:
        rep.verdict = UNRESOLVED_EXCLUSION
        rep.add(f"  {ex.refusal}")
        rep.add(f"VERDICT   {rep.verdict}")
        return rep
    rep.add(f"  |O| desk combo orders        {ex.n_desk_orders}   (dry_run = 0, placed before W_end)")
    rep.add(f"  CLEARED-BY-VENUE             {ex.n_cleared_by_venue}   (cancel_reduced_by == count)")
    rep.add(f"  |R| residual                 {ex.n_residual}")
    rep.add(f"  |T| tickers attributed       {ex.n_tickers}   (no element printed)")

    pop = classify(fills, w_start, w_end, ex.tickers)
    rep.add(f"  EXCLUDED-BY-TICKER fills     {pop.excluded_by_ticker}   (both is_taker values)")
    rep.add(f"  RESIDUAL CONTAMINATION BOUND |R| = {ex.n_residual} orders, "
            f"{pop.excluded_by_ticker} fills excluded")

    runs = sittings(pop.taker_in_window)
    first_fills = [r[0] for r in runs]
    s = len(runs)
    days = {budget_day(ms) for ms in first_fills}
    d = len(days)

    rep.add()
    rep.add("population (fills), post-exclusion")
    rep.add(f"  taker, in window             {len(pop.taker_in_window)}")
    rep.add(f"  maker, in window             {len(pop.maker_in_window)}   (descriptive only, §5.4)")
    rep.add(f"  UNCLASSIFIABLE (pre-W_start) {pop.unclassifiable}")
    rep.add(f"  after W_end                  {pop.after_window}")
    rep.add(f"  engine                       {pop.engine}")
    if pop.other_source:
        rep.add(f"  other source                 {pop.other_source}")
    rep.add()
    rep.add(f"S = {s} sittings at {SITTING_GAP_MS} ms   D = {d} budget days")
    for g in SENSITIVITY_GAPS_MS:
        rep.add(f"  S at gap {g // 60_000:>3} min           "
                f"{len(sittings(pop.taker_in_window, g))}   (sensitivity, no verdict)")

    # §6.2 — the structural refusal, evaluated after E0–E4 (E5).
    if s < S_MIN or d < D_MIN:
        rep.verdict = (
            "UNRESOLVED — TOO FEW SITTINGS" if s < S_MIN else "UNRESOLVED — TOO FEW DAYS"
        )
        rep.add()
        rep.add(f"SAMPLE NOT REACHED: S = {s} of {S_MIN}, D = {d} of {D_MIN}")
        rep.add(f"VERDICT   {rep.verdict}")
        rep.add("Below the floor the analyzer computes no statistic at all. §6.2.")
        return rep

    # Descriptives that carry no verdict. §5.4.
    rep.add()
    biggest = max(len(r) for r in runs)
    rep.add(f"fills per sitting             {[len(r) for r in runs]}   largest share "
            f"{biggest / len(pop.taker_in_window):.1%}")
    per_day: dict[int, int] = {}
    for ms in first_fills:
        per_day[budget_day(ms)] = per_day.get(budget_day(ms), 0) + 1
    top_day = max(per_day, key=per_day.get)  # type: ignore[arg-type]
    rep.add(f"sittings per budget day       {dict(sorted(per_day.items()))}   largest share "
            f"{per_day[top_day] / s:.1%}")
    dists_min = sorted(distance_ms(ms, visits) / 60_000 for ms in first_fills)
    rep.add(f"distance to nearest visit     {[round(x, 1) for x in dists_min]} min")
    buckets = [f"=0: {sum(1 for x in dists_min if x == 0)}"]
    for edge in DESCRIPTIVE_EDGES_MIN[1:]:
        buckets.append(f"<={edge}: {sum(1 for x in dists_min if x <= edge)}")
    last = DESCRIPTIVE_EDGES_MIN[-1]
    buckets.append(f">{last}: {sum(1 for x in dists_min if x > last)}")
    rep.add(f"cumulative counts (descriptive, no verdict)  {'  '.join(buckets)}")
    any_present_b5 = sum(1 for r in runs if any(present(ms, visits, B5_MS) for ms in r))
    rep.add(f"sittings with ANY fill present at B5   {any_present_b5} of {s}   "
            "(beside the first-fill primary)")
    if pop.maker_in_window:
        md = sorted(distance_ms(ms, visits) / 60_000 for ms in pop.maker_in_window)
        rep.add(f"maker fills, distance (min)   {[round(x, 1) for x in md]}   no verdict")

    # The four registered tests.
    a5 = arm(first_fills, visits, B5_MS, w_start, w_end)
    a30 = arm(first_fills, visits, B30_MS, w_start, w_end)
    rep.add()
    for label, a in (("B5  (primary)", a5), ("B30 (secondary)", a30)):
        rep.add(f"{label}  K = {a.k} of {s}")
        rep.add(f"    gap arm      p_gap  = P(K <= {a.k} | {s}, 0.5) = {a.p_gap:.4f}   alpha {ALPHA}")
        if a.perm.feasible:
            rep.add(f"    presence arm p_perm = {a.perm.p_value:.4f}   ({a.perm.draws} day-shift draws, "
                    f"min |Adm| = {a.perm.min_admissible}, seed {PERM_SEED})")
        else:
            rep.add(f"    presence arm PERMUTATION INFEASIBLE (min |Adm| = {a.perm.min_admissible} "
                    f"< {PERM_MIN_ADMISSIBLE})")
        rep.add(f"    theta_wall = {a.theta_wall:.4f}   P(K >= {a.k} | {s}, theta_wall) = "
                f"{a.p_wall:.4f}   (descriptive)")
        rep.add(f"    sittings within {SKEW_MS // 1000} s of a band edge: {a.skew_sensitive}")

    verdict = primary_verdict(a5)

    # §3.3 leave-one-day-out on the primary. "The largest-contributing budget
    # day" is a definite article over what may be a set: when several days tie
    # for the most sittings, every tied day is dropped in turn and the verdict
    # must survive each. Breaking the tie by dict order (the first version of
    # this block did) resolves a registered downgrade silently, and on the
    # 2026-09-04 look it resolved it in the flattering direction — the audit
    # caught it (measurement-skeptic, B1). Conservative by construction: a
    # downgrade that fires under any admissible reading fires.
    top_n = max(per_day.values())
    tied_days = sorted(d for d, n in per_day.items() if n == top_n)
    rep.add()
    if len(tied_days) > 1:
        rep.add(f"leave-one-day-out: {len(tied_days)} days tie for largest at {top_n} "
                f"sittings; each is dropped in turn and the verdict must survive all")
    flipped = False
    for day in tied_days:
        kept = [ms for ms in first_fills if budget_day(ms) != day]
        if not kept:
            rep.add(f"leave-one-day-out (drop day {day}): not computable, S would be 0")
            continue
        a5_loo = arm(kept, visits, B5_MS, w_start, w_end)
        loo_verdict = primary_verdict(a5_loo)
        rep.add(f"leave-one-day-out (drop day {day}, {per_day[day]} sittings): "
                f"K = {a5_loo.k} of {len(kept)}, p_gap {a5_loo.p_gap:.4f}, "
                f"p_perm {a5_loo.perm.p_value if a5_loo.perm.feasible else 'infeasible'} "
                f"-> {loo_verdict}")
        if loo_verdict != verdict:
            flipped = True
    if flipped and not verdict.startswith("UNRESOLVED"):
        verdict = "UNRESOLVED — CONCENTRATION"
        rep.add("§3.3: the verdict flips when a largest-contributing day is dropped; downgraded.")

    # C6 skew downgrade: only when a verdict exists and an edge case decides it.
    if not verdict.startswith("UNRESOLVED") and a5.skew_sensitive > 0:
        flip_changes = False
        for ms in first_fills:
            if within_skew_of_edge(ms, visits, B5_MS):
                base = present(ms, visits, B5_MS)
                k_alt = a5.k + (-1 if base else 1)
                if (binom_lower_tail(k_alt, s, 0.5) <= ALPHA) != (a5.p_gap <= ALPHA):
                    flip_changes = True
        if flip_changes:
            verdict = "UNRESOLVED — SKEW-SENSITIVE"
            rep.add("C6: a sitting within 60 s of a band edge decides the gap arm; downgraded.")

    rep.add()
    survives = primary_verdict(a30) == primary_verdict(a5)
    rep.add(f"B30 qualification: the primary verdict {'does' if survives else 'does NOT'} "
            "survive a 30-minute halo.")
    if verdict == "PRESENCE GAP SUPPORTED":
        rep.add("This verdict is WEAK by construction (§9.1): the instrument's blindness predicts it.")
    if verdict == "PRESENCE GAP REFUTED":
        rep.add("This verdict is STRONG by construction (§9.1): it survives a bias pushing the other way.")
    rep.verdict = verdict
    rep.add()
    rep.add(f"VERDICT   {verdict}")
    return rep


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--fills", required=True, type=Path, help="h4-balance-spans --json capture")
    ap.add_argument("--visits", required=True, type=Path,
                    help="visit-freshness --since 20260801 --json capture")
    ap.add_argument("--manual", required=True, type=Path, help="manual-orders-audit --json capture")
    ap.add_argument("--combos", required=True, type=Path, help="combo-bids-tail -n 500 --json capture")
    ap.add_argument("--w-end-ms", type=int, default=W_END_MS,
                    help="registered W_end; change ONLY under §8's single extension")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # em dashes on a cp1252 console
    try:
        fills = read_fills(args.fills)
        visits, w_start, gap_ms = read_visits(args.visits)
        inputs = read_exclusion_inputs(args.manual, args.combos)
        stamps = [
            (p, *capture_taken_ms(p))
            for p in (args.fills, args.visits, args.manual, args.combos)
        ]
        captured = [ms for _, ms, _ in stamps]
        rep = analyse(
            fills, visits, w_start, inputs,
            w_end=args.w_end_ms, visit_gap_ms=gap_ms, captured_ms=captured,
        )
    except CaptureError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    for p, ms, source in stamps:
        print(f"E0 capture time  {p.name}: {_iso(ms)}  from {source}")
    print("\n".join(rep.lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
