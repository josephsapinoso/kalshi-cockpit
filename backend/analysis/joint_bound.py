"""The joint bound: how many recorded rows could ever have been actionable.

Implements `docs/measurements/2026-08-10-preregistration-joint-bound.md`, which
**governs**. Every constant, edge, population and output field here is fixed in
that document; nothing in this module may be re-chosen. Where a rule already
exists elsewhere in the repo it is **imported**, not restated -- `BUCKETS` from
`analysis.validate`, the fee models from `core.fees`, the effective price from
`core.ev` -- so that two paths cannot come to disagree.

The instrument, in one line: `S = ask_tenths - 1000 * fair_probability`, and
`K(delta) = #{rows : S < 10*delta}`. The primary's fee is **identically zero**
(registration §C3, verified exhaustively in `tests/test_joint_bound.py`), so the
primary bound is one subtraction and is invariant to order size.

What this does NOT establish
----------------------------
- **If the bound returns 0, the honest finding is "Kalshi is not mispriced
  relative to a consensus it may itself lead."** It is **NOT** "no edge exists
  at Kalshi." `tasks/lessons.md` already suspects Kalshi is the sharp side, in
  which case "Kalshi versus devigged sportsbook consensus" is close to empty
  **by construction** -- the comparison would be Kalshi against a lagging
  shadow of itself, and finding nothing there is a fact about the instrument's
  geometry, not about the venue. Any write-up containing the broader sentence
  is defective and must be corrected. (Registration §10, first bullet.)
- **The four devig methods and the two fee models are the whole space this
  bound covers, and that space is small.** A different fair-value source -- a
  power rating, a fifth devig method, a book this project does not subscribe to
  -- is outside it entirely.
- **A zero fee is not a realisable state.** The primary charges nothing at every
  price and every size. Nobody believes that. It is what makes a zero count
  strong and it is why `K` **may never be quoted as an estimate** of how many
  rows would be actionable under any real conditions.
- **`S` is the engine's own claim about a market, recomputed.** A distribution
  of claims is not evidence the claims are correct. Whether `fair_probability`
  is calibrated is a different question and is not asked here.
- **The record contains only the markets the recorder chose to look at**, and
  `persist_if_changed` writes only on movement, so the population is
  movement-weighted and downstream of discovery. A market never polled
  contributes no row and therefore cannot clear the bound. **This is the single
  most likely way the result is overturned.**
- **The bound is scoped to the rows examined** -- one August slate. The
  rule-of-three bound (`rule_of_three`) is the only statement it makes about a
  wider universe and it is weak.
- **`G` may be inflated** by the event-ticker key if spread or total rows enter
  the record, which makes the rule-of-three bound look tighter than it is.
"""

from __future__ import annotations

import inspect
import math
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from .. import gate
from ..core.ev import effective_price
from ..core.fees import fee_candidates
from ..core.prices import is_valid_price, tenths_to_dollars
from .validate import BUCKETS, MIN_EXPECTED_PER_SIDE

# ---------------------------------------------------------------------------
# Registered constants. Registration §2, §5, §6. None of these is a knob.
# ---------------------------------------------------------------------------

#: §2 / §P3. Outside this range the ask is a settled outcome, not a quote, and
#: `effective_price` **raises** rather than pricing it at a zero fee.
ASK_MIN_TENTHS = 10
ASK_MAX_TENTHS = 989

#: §5's delta ladder, as `(points, tenths)`. Five rungs as registered, plus the
#: sixth added by **Amendment 1 §A1** at 16.70 points. None of the original five
#: moves.
#:
#: The sixth exists because the committed ladder topped out at 10.0 while the
#: devig knob reaches 16.649 points **[COMPUTED FROM CODE -- §A1's sweep]**, so
#: Branch Z could have declared the central question CLOSED on a record whose
#: nearest row was 12 points short -- comfortably inside the reach of the knob
#: the bound exists to exhaust. That is a false closure in the flattering
#: direction, inside an instrument built specifically to resist one.
#:
#: The tenths column is registered beside the points column rather than derived
#: from it, and that is not fussiness: `10 * 0.18` is `1.7999999999999998` in
#: binary floating point, `10 * 2.03` is `20.299999999999997` and `10 * 16.70`
#: is `167.00000000000003`, so a threshold computed by multiplication would sit
#: a hair off the registered histogram edge and could move a row across a cell
#: boundary. The two columns are asserted equal in the test suite.
DELTA_LADDER: tuple[tuple[float, float], ...] = (
    (0.00, 0.0),
    (0.18, 1.8),
    (2.03, 20.3),
    (5.00, 50.0),
    (10.00, 100.0),
    (16.70, 167.0),
)

#: Amendment 1 §A1's two verdict thresholds, in probability points. Both are
#: **rounded up** from the measured sweep, and that is not cosmetic: a threshold
#: the record must *exceed* to declare closure is made harder to clear by
#: rounding up, so the rounding runs against the declaration.
#:
#: `D_realistic` is the worst method spread over the region this project trades
#: (favourite <= 85%, overround <= 6%), measured 3.472. `D_swept` is the worst
#: anywhere in §A1's swept space, measured 16.649 -- and §A5 records that the
#: sweep is two-outcome, proportional-overround, favourite <= 99%, hold <= 20%,
#: so clearing it does **not** mean clearing every conceivable devig spread.
D_REALISTIC_POINTS = 3.5
D_SWEPT_POINTS = 16.7

#: §C4's ceiling on the whole fee-and-maker knob: 20 tenths in the middle band,
#: 10 in the wings, so **at most 2.0 points**. Printed beside `D*` because the
#: comparison is the strongest line in the artefact if Branch Z is declared --
#: a `D*` of 15 points would mean the fee model and the maker basis are not
#: merely set generous but arithmetically incapable of mattering.
KNOB_CEILING_POINTS = 2.0

#: §5's reachability rung. `K` at this delta must be non-zero or the harness is
#: treated as suspected defective and no branch is declared (§7).
REACHABILITY_DELTA_POINTS = 10.00

#: §5's shortfall histogram, eight cells, **left-open right-closed**, in tenths
#: of a cent. Three of the edges are the delta ladder, so the histogram and the
#: ladder are the same partition read two ways and cannot disagree.
SHORTFALL_CELLS: tuple[tuple[float, float], ...] = (
    (-math.inf, 0.0),
    (0.0, 10.0),
    (10.0, 20.3),
    (20.3, 50.0),
    (50.0, 100.0),
    (100.0, 200.0),
    (200.0, 400.0),
    (400.0, math.inf),
)

#: §5's Grid B, **imported** from `analysis.validate` rather than restated so it
#: cannot be re-chosen. Bucketing is on `entry_ask_tenths`, the derived ask, the
#: price actually paid -- never a mid.
GRID_B = BUCKETS

#: §5's maker band, the exact edges rather than ADR 0017 §1's rounded "18c-82c",
#: which would mislabel 14 prices. Inclusive on both ends.
MAKER_BAND_TENTHS = (173, 827)

#: §7's Branch M naming rule reads the repo's own small-cell rule.
MAKER_BAND_MIN_CLUSTERS = MIN_EXPECTED_PER_SIDE

#: §6's percentile set. Nine readouts, no others.
PERCENTILES = (1, 5, 10, 25, 50, 75, 90)

#: Lane A §3's three mechanical bankroll eras on `created_ms`. `BANKROLL_DOLLARS`
#: went 1000 -> 100 in `78b5790`; `boundary` rows are unassignable and are
#: retained and reported separately, never folded into either side.
BANKROLL_ERA_COMMIT_MS = 1786301578000
BANKROLL_ERA_SETTLED_MS = 1786308480000

#: §C4's exhaustive per-knob savings against the deployed basis (max fee model,
#: taker, N=1), in tenths of a cent per contract, as `(low, high, delta)` runs
#: over the 999 tradeable prices, inclusive on both ends. These are **asserted**
#: against `fee_candidates` rather than trusted: §S2 item 10 requires
#: `E1min - E1 == Delta(price)` to be printed as an executed check.
FEE_KNOB_DELTA_BANDS: tuple[tuple[int, int, float], ...] = (
    (1, 91, 10.0), (92, 172, 0.0), (173, 499, 10.0), (500, 500, 0.0),
    (501, 827, 10.0), (828, 908, 0.0), (909, 999, 10.0),
)
MAKER_KNOB_DELTA_BANDS: tuple[tuple[int, int, float], ...] = (
    (1, 172, 0.0), (173, 827, 10.0), (828, 999, 0.0),
)

#: The prices and sizes over which §C3's zero-fee fact is verified.
ZERO_FEE_SIZES = (1, 2, 5, 10, 50, 100, 500, 1000)

POPULATION_NAMES = ("P0", "P1", "P2", "P3")

#: §S1's mandatory label on any run that is not the whole table.
PROVISIONAL_PREFIX = "NEWEST-1,000 SLICE — PROVISIONAL — NOT A PROPERTY OF THE TABLE"


# ---------------------------------------------------------------------------
# §C3 -- the zero-fee fact, checkable rather than quoted
# ---------------------------------------------------------------------------


def maker_model_b_nonzero_cases(
    prices: Iterable[int] = range(1, 1000),
    sizes: Iterable[int] = ZERO_FEE_SIZES,
) -> list[tuple[int, int, float]]:
    """Every `(price, size)` where the stacked generous fee is **not** zero.

    Registration §C3 / §F2: `fee_candidates(p, N, maker=True)` returns
    `model_b_per_contract_nearest == 0.00` in all 7,992 cases, because Model B's
    maker multiplier is `0.06/4 = 0.015` and `0.015 * P(1-P) <= 0.00375`, which
    rounds half-up to zero cents **per contract** at every price.

    The whole primary bound rests on that. It is returned as a list rather than
    asserted here so the test suite can fail loudly with the offending cases
    named: if this is ever non-empty, `primary_shortfall_tenths` is wrong and
    the registration's §C3 must be amended before any count is produced.
    """
    sizes = tuple(sizes)
    return [
        (price, size, fee)
        for price in prices
        for size in sizes
        if (fee := fee_candidates(price, size, True)["model_b_per_contract_nearest"])
        != 0.0
    ]


# ---------------------------------------------------------------------------
# The row, and the populations of §2
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    """One ledger row, with every field the registration consumes.

    Unreadable resolves to `None`, never `0` -- so a missing ask or a missing
    fair excludes the row and is **counted**, rather than being substituted with
    a number that would silently enter a money quantity.
    """

    id: int
    ticker: str
    side: Optional[str]
    created_ms: Optional[int]
    ask_tenths: Optional[int]
    fair_probability: Optional[float]
    suppressed_reason: Optional[str]
    clv_horizon_hours: Optional[float] = None
    strategy_config_version: Optional[str] = None
    # Diagnostic only (§S2 item 11). These enter no quantity in the decision.
    stored_edge_tenths_DO_NOT_USE: Optional[float] = None
    stored_fee_DO_NOT_USE: Optional[float] = None
    # Confirmatory only. `None` is a real state (`devig.py:181`) and is dropped
    # and counted, never imputed.
    p_multiplicative: Optional[float] = None
    p_additive: Optional[float] = None
    p_power: Optional[float] = None
    p_shin: Optional[float] = None
    p_conservative: Optional[float] = None
    # Present only when the row was read from SQL rather than over HTTP.
    event_ticker: Optional[str] = None

    @classmethod
    def from_ledger_payload(cls, payload: dict) -> "Row":
        """Build from one `/api/ledger` row. §F8: the field is `ask_tenths`.

        Registering the payload's field name is not pedantry -- Lane A F2 records
        that a rename has silently emptied a filter in this repo four times.
        """
        return cls(
            id=payload["id"],
            ticker=payload.get("ticker") or "",
            side=payload.get("side"),
            created_ms=payload.get("created_ms"),
            ask_tenths=payload.get("ask_tenths"),
            fair_probability=payload.get("fair_probability"),
            suppressed_reason=payload.get("suppressed_reason"),
            clv_horizon_hours=payload.get("clv_horizon_hours"),
            strategy_config_version=payload.get("strategy_config_version"),
            stored_edge_tenths_DO_NOT_USE=payload.get("edge_tenths"),
            stored_fee_DO_NOT_USE=payload.get("fee_predicted"),
            p_multiplicative=payload.get("p_multiplicative"),
            p_additive=payload.get("p_additive"),
            p_power=payload.get("p_power"),
            p_shin=payload.get("p_shin"),
            p_conservative=payload.get("p_conservative"),
            event_ticker=payload.get("event_ticker"),
        )


def is_fresh(suppressed_reason: Optional[str]) -> bool:
    """Lane A §2's freshness predicate, in its **only permitted Python form**.

    ``"stale_odds" not in (row["suppressed_reason"] or "").split(",")``

    Exact token match on the split, no wildcard surface. Two live reasons, both
    of which have already bitten:

    - `suppressed_reason` is a **comma-joined composite** of every failing
      check, and Lane A §0.1 measured 27.8% of stale rows as composites. A
      predicate that tested the whole string for equality would call
      `"stale_odds,wide_market"` fresh.
    - The SQL sibling of this predicate uses `instr`, never `LIKE`: SQLite
      `LIKE` reads `_` as a single-character wildcard and **all fourteen**
      suppression codes contain underscores.

    A substring test is the other wrong shape and it fails the other way:
    `"stale_odds_upstream"` contains `"stale_odds"` and is a **different code**.
    """
    return "stale_odds" not in (suppressed_reason or "").split(",")


def is_unsuppressed(row: Row) -> bool:
    return row.suppressed_reason is None


def in_p0(row: Row) -> bool:
    """§2's P0: a tradeable ask and a non-NULL fair. The PRIMARY population."""
    if row.ask_tenths is None or row.fair_probability is None:
        return False
    return ASK_MIN_TENTHS <= row.ask_tenths <= ASK_MAX_TENTHS


def exclusion_reason(row: Row) -> Optional[str]:
    """Why a row is outside P0, or `None` if it is inside. §2's exclusion table.

    Both reasons are decidable from the row's own inputs, before any fair is
    compared to any ask, so neither can be activated in the direction of a
    smaller count after the data is read.
    """
    if row.ask_tenths is None or not (
        ASK_MIN_TENTHS <= row.ask_tenths <= ASK_MAX_TENTHS
    ):
        return "ask_outside_10_989"
    if row.fair_probability is None:
        return "fair_probability_null"
    return None


def populations(rows: Sequence[Row]) -> dict[str, list[Row]]:
    """§2's four nested populations. All four are reported; the decision reads P0.

    P0 is the primary because **a bound is strongest over the widest
    population**. Restricting to fresh or unsuppressed rows would answer a
    narrower question and would be a choice made in the direction of a smaller
    count -- which §2 forbids activating after the fact.
    """
    p0 = [r for r in rows if in_p0(r)]
    p1 = [r for r in p0 if is_unsuppressed(r)]
    p2 = [r for r in p0 if is_fresh(r.suppressed_reason)]
    p3 = [r for r in p1 if is_fresh(r.suppressed_reason)]
    return {"P0": p0, "P1": p1, "P2": p2, "P3": p3}


def nesting_violations(pops: dict[str, list[Row]]) -> list[str]:
    """§2's invariant `P3 subset of P1, P2 subset of P0`, as executed checks.

    Returned rather than raised so §S2 item 2 can print it. A violation voids
    the run: `K` is monotone non-increasing along the nesting by construction,
    so a broken nesting means the populations are not what they are labelled.
    """
    ids = {name: {r.id for r in members} for name, members in pops.items()}
    checks = (("P1", "P0"), ("P2", "P0"), ("P3", "P1"), ("P3", "P2"))
    return [
        f"{inner} is not a subset of {outer} "
        f"({len(ids[inner] - ids[outer])} rows outside)"
        for inner, outer in checks
        if not ids[inner] <= ids[outer]
    ]


# ---------------------------------------------------------------------------
# §3 -- the cluster key
# ---------------------------------------------------------------------------

#: The SQL key `gate.clustered_clv` uses, mirrored here. It is inline SQL inside
#: that function and needs a database connection, so it cannot be imported --
#: but it can be **checked**, and it is, at import time, so that re-choosing the
#: key in `gate.py` breaks this harness loudly instead of silently splitting it
#: from the gate it is supposed to match.
_GATE_CLUSTER_KEY_SQL = "COALESCE(m.event_ticker, r.ticker)"

if _GATE_CLUSTER_KEY_SQL not in inspect.getsource(gate.clustered_clv):
    raise ImportError(
        "gate.clustered_clv no longer clusters on "
        f"{_GATE_CLUSTER_KEY_SQL!r}. Registration §3 fixes the joint bound's "
        "cluster key to the one the gate uses; they have diverged."
    )


def cluster_key(ticker: str, event_ticker: Optional[str] = None) -> Optional[str]:
    """§3's clustering variable: `COALESCE(event_ticker, <HTTP fallback>)`.

    Over HTTP only `ticker` is available, so the fallback is Lane A §4's:
    **split on `-`; if there are three or more segments drop the last;
    otherwise use the string unchanged.**

        KXMLBGAME-26AUG09DETSEA-SEA  ->  KXMLBGAME-26AUG09DETSEA
        KXATPMATCH-26AUG09FONSHE     ->  KXATPMATCH-26AUG09FONSHE

    **No fixed character count is chopped.** That was the previous project's
    bug, and it inflated `G` in the flattering direction -- a smaller cluster is
    a larger apparent count of independent games.

    Lane A §4's two defects carry over and are **printed, not corrected**: the
    event ticker carries the series prefix, so spread and total rows on one game
    would become up to three clusters; and the fallback cannot see a market
    whose stored `event_ticker` differs from its ticker prefix.
    """
    if event_ticker:
        return event_ticker
    if not ticker:
        return None
    segments = ticker.split("-")
    if len(segments) >= 3:
        return "-".join(segments[:-1])
    return ticker


def series_prefix(ticker: str) -> Optional[str]:
    """The series segment of a ticker -- `KXMLBGAME` -- or `None`."""
    if not ticker or "-" not in ticker:
        return None
    return ticker.split("-", 1)[0]


def event_suffix(ticker: str) -> Optional[str]:
    """The `<DATE+TEAMS>` segment, for Lane A §4 defect 1's integrity print."""
    if not ticker:
        return None
    segments = ticker.split("-")
    return segments[1] if len(segments) >= 2 else None


def cluster_count(rows: Iterable[Row]) -> int:
    """`G` -- distinct clusters. The unit for every reported rate.

    Printed beside `n_rows` always and everywhere: this repo shipped a gate that
    counted 400 rows on one ticker as 400 observations.
    """
    return len({k for r in rows if (k := cluster_key(r.ticker, r.event_ticker))})


def bankroll_era(created_ms: Optional[int]) -> str:
    """Lane A §3's three mechanical levels. `boundary` rows are unassignable."""
    if created_ms is None:
        return "unknown"
    if created_ms < BANKROLL_ERA_COMMIT_MS:
        return "pre"
    if created_ms < BANKROLL_ERA_SETTLED_MS:
        return "boundary"
    return "post"


# ---------------------------------------------------------------------------
# §6 -- the shortfall, and the primary bound
# ---------------------------------------------------------------------------


def primary_shortfall_tenths(row: Row) -> float:
    """`S = entry_ask_tenths - 1000 * fair_probability`, in tenths of a cent.

    Positive `S` means the row is **short** by that many tenths. The zero fee of
    §C3 is already in it, which is why this is one subtraction and why it is
    invariant to order size: the stacked generous fee (cheapest model, maker
    basis) is identically zero at every price and every `N`, so the generous
    effective price **is** the raw ask.

    `1000` is `PRICE_MAX` in tenths of a cent, so the two terms are commensurate
    and `S` is a per-contract quantity in tenths.
    """
    if row.ask_tenths is None or row.fair_probability is None:
        raise ValueError(
            f"row {row.id} has no readable ask or fair; it is outside P0 and "
            f"must be excluded and counted, never priced."
        )
    return row.ask_tenths - 1000.0 * row.fair_probability


def primary_alt_shortfall_tenths(row: Row, basis: FeeBasis) -> float:
    """The primary's shortfall re-priced on one realisable fee basis.

    §7's Branch M needs `K` under **ALT-2 alone** with `fair + delta` standing in
    for the per-row `p_max` that the deployed payload does not carry:

        S_basis = 1000 * effective_price(ask, N, maker, model) - 1000 * fair

    and the ladder identity is unchanged -- the row clears at `delta` iff
    `S_basis < 10*delta`, because adding `delta` to the fair and subtracting
    `10*delta` from the shortfall are the same move.

    `primary_shortfall_tenths` is this function at the stacked generous basis,
    whose fee is identically zero (§C3), which is why the primary needs no
    basis argument at all. That identity is asserted in the test suite rather
    than assumed, because it is the one place the two paths could drift.
    """
    if row.ask_tenths is None or row.fair_probability is None:
        raise ValueError(
            f"row {row.id} has no readable ask or fair; it is outside P0."
        )
    price = basis_effective_price_dollars(basis, row.ask_tenths)
    return 1000.0 * price - 1000.0 * row.fair_probability


def delta_tenths(delta_points: float) -> float:
    """The registered tenths threshold for a ladder rung. §5's table, not a multiply."""
    for points, tenths in DELTA_LADDER:
        if points == delta_points:
            return tenths
    raise ValueError(
        f"delta {delta_points} is not on the §5 ladder "
        f"{[p for p, _ in DELTA_LADDER]}. No delta outside the ladder may be "
        f"introduced after the data is read."
    )


def clears_at(shortfall_tenths: float, delta_points: float) -> bool:
    """§6's identity: a row clears at delta points **iff** `S < 10*delta`."""
    return shortfall_tenths < delta_tenths(delta_points)


def k_at_delta(shortfalls: Iterable[float], delta_points: float) -> int:
    """`K(delta) = #{rows : S < 10*delta}`. A count over a census, no alpha."""
    threshold = delta_tenths(delta_points)
    return sum(1 for s in shortfalls if s < threshold)


def k_ladder(rows: Sequence[Row]) -> dict[float, tuple[int, int]]:
    """`K(delta)` and `G_K(delta)` at every rung, from one pass over the rows.

    `K(delta)` for **every** delta is a readout of one distribution, which is why
    no delta needs choosing and why the delta knob does not exist for the analyst
    (§C2's central design decision).
    """
    scored = [(primary_shortfall_tenths(r), r) for r in rows]
    out: dict[float, tuple[int, int]] = {}
    for points, tenths in DELTA_LADDER:
        clearing = [r for s, r in scored if s < tenths]
        out[points] = (len(clearing), cluster_count(clearing))
    return out


def d_star_points(shortfalls: Iterable[float]) -> Optional[float]:
    """`D* = min(S) / 10` -- the shortfall of the nearest row, in **points**.

    The same distribution as `K(delta)` read the other way round. The identity
    is exact and strict: since `K(delta) = #{S < 10*delta}`,

        K(delta) >= 1   <=>   min(S) < 10*delta   <=>   delta > D*

    so `D*` is the infimum of the delta ladder rungs that would clear a row, and
    `K` is its counting function. Both are computed and printed. **Which of the
    two is the registered primary estimand is a question for the registration,
    not for this module** -- naming one here would be choosing, and the choice
    belongs upstream of the analyst.

    `None` on an empty population: a minimum over nothing is not zero.
    """
    values = list(shortfalls)
    if not values:
        return None
    return min(values) / 10.0


#: Amendment 1 §A1's three verdicts. Exhaustive and mutually exclusive on `D*`.
BRANCH_N = "BRANCH N — NOT CLOSED"
Z_NARROW = "Z-NARROW — closed against realistic slates, NOT against lopsided or high-hold lines"
BRANCH_Z = "BRANCH Z — CLOSED"


def verdict(d_star: Optional[float]) -> Optional[str]:
    """§A1's branch, from `D*` alone. Three outcomes, not two.

        D* <= 3.5             BRANCH N   -- not closed
        3.5 < D* <= 16.7      Z-NARROW   -- the confirmatory becomes
                                            decision-bearing and the ADR waits
        D* > 16.7             BRANCH Z   -- closed

    `None` on an empty population: a verdict over no rows is not a verdict.

    The partition is stated on `D*` because that is how §A1 writes it, and
    `D*` is exhaustive on the real line while the `K(16.70) = 0` phrasing leaves
    the single point `D* == 16.7` ambiguous. Where the two readings differ -- at
    exactly that point, and nowhere else -- this returns the **narrower**
    verdict, which is the direction §A6 registers: *the failure mode of this
    amendment is more UNRESOLVED, never a false declaration*.
    """
    if d_star is None:
        return None
    if d_star <= D_REALISTIC_POINTS:
        return BRANCH_N
    if d_star <= D_SWEPT_POINTS:
        return Z_NARROW
    return BRANCH_Z


def k_ladder_monotonicity_violations(ladder: dict[float, tuple[int, int]]) -> list[str]:
    """`K` must be non-decreasing in delta. §S2 item 10 prints this as executed."""
    rungs = [points for points, _ in DELTA_LADDER if points in ladder]
    return [
        f"K({lo:.2f}) = {ladder[lo][0]} > K({hi:.2f}) = {ladder[hi][0]}"
        for lo, hi in zip(rungs, rungs[1:])
        if ladder[lo][0] > ladder[hi][0]
    ]


def population_monotonicity_violations(
    ladders: dict[str, dict[float, tuple[int, int]]],
) -> list[str]:
    """`K` must be non-increasing along `P3 subset of P1, P2 subset of P0`."""
    checks = (("P1", "P0"), ("P2", "P0"), ("P3", "P1"), ("P3", "P2"))
    violations = []
    for inner, outer in checks:
        if inner not in ladders or outer not in ladders:
            continue
        for points, _ in DELTA_LADDER:
            k_in = ladders[inner].get(points, (0, 0))[0]
            k_out = ladders[outer].get(points, (0, 0))[0]
            if k_in > k_out:
                violations.append(
                    f"K({points:.2f}) on {inner} = {k_in} exceeds {outer} = {k_out}"
                )
    return violations


# ---------------------------------------------------------------------------
# §5 -- the exact bound's three alternatives. A UNION, never a stack.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeeBasis:
    """One realisable fee state. `partner`'s constraint 1, made structural.

    Stacking the cheaper-fee knob onto the maker knob is permitted for the
    **dominating** bound and **FORBIDDEN** for the exact one -- they are
    *alternatives*, not additions, and §C4 measures the stacking premium at up
    to a full cent per contract beyond the better alternative. Reporting the
    stack as the exact bound would be a fabrication of exactly that size.

    So the stack is not merely undone here, it is **unconstructible**: this
    class refuses to exist in the stacked configuration. The primary bound never
    builds a `FeeBasis` at all -- its fee is the literal zero of §C3 -- so the
    two code paths cannot leak into one another.
    """

    name: str
    fee_model: str  # "max" (calculate_fee) | "cheapest" (min of candidates)
    maker: bool
    contracts: int

    def __post_init__(self) -> None:
        if self.fee_model not in ("max", "cheapest"):
            raise ValueError(f"unknown fee model {self.fee_model!r}")
        if self.contracts <= 0:
            raise ValueError(f"contracts must be positive, got {self.contracts}")
        if self.fee_model == "cheapest" and self.maker:
            raise ValueError(
                "the cheapest fee model on the maker basis is the STACK, which "
                "registration §5 forbids for the exact bound. The stack is the "
                "primary's generous basis and is a literal zero fee (§C3); it "
                "has no FeeBasis and must not acquire one."
            )


#: §5's `N` for ALT-2, as **superseded by Amendment 1 §A2**. The committed body
#: set 10, citing ADR 0017 Correction 1's "the smallest order this software can
#: send is 10 contracts". **That premise was retired on 2026-08-09** --
#: `sizing.py:15` says "There is no minimum order size", `MIN_ORDER_CONTRACTS`
#: is in `config.RETIRED_SETTINGS`, and ADR 0017's own Addendum A.2 records the
#: removal. So ALT-2 is `N = 1`, matching `sizing.py:156`'s unconditional
#: `effective_price(ask_tenths, contracts=1)`, and `N = 10` is printed beside it
#: as the labelled non-decision-bearing secondary -- the exact inverse of §5.
#:
#: The direction of that error was the flattering one: at 50c the maker saving
#: is 10.0 tenths at `N=1` and 15.0 at `N=10`, so the retired premise inflated
#: **Branch M**, the one branch that could still produce a positive result.
ALT_2_CONTRACTS = 1
ALT_2_SECONDARY_CONTRACTS = 10

#: §5's three alternatives. ALT-0 is Lane A §6's deployed baseline; ALT-1 is
#: Lane A §6's `E1min`; ALT-2 is the maker basis at `ALT_2_CONTRACTS`.
ALT_0 = FeeBasis(name="ALT-0", fee_model="max", maker=False, contracts=1)
ALT_1 = FeeBasis(name="ALT-1", fee_model="cheapest", maker=False, contracts=1)


def alt_2(contracts: int = ALT_2_CONTRACTS) -> FeeBasis:
    """ALT-2 at a stated order size. §5 fixes the size; this fixes nothing else.

    Parameterised on `N` deliberately. `N` is **not swept** -- a swept `N` is a
    knob and §5 forbids it -- so every call site passes either the registered
    size or the labelled non-decision-bearing secondary, and the name carries
    the size so no printed line can be read at the wrong one.
    """
    return FeeBasis(
        name=f"ALT-2 (N={contracts})", fee_model="max", maker=True, contracts=contracts
    )


ALT_2 = alt_2()

#: Printed beside ALT-2 and labelled non-decision-bearing (§S2 item 8 as
#: superseded by §A2: the two sizes swap roles).
ALT_2_SECONDARY = alt_2(ALT_2_SECONDARY_CONTRACTS)

#: The exact bound clears a row iff it clears under ALT-1 **or** ALT-2
#: individually.
EXACT_ALTERNATIVES = (ALT_1, ALT_2)


def basis_effective_price_dollars(basis: FeeBasis, ask_tenths: int) -> float:
    """Effective price per contract in dollars, under exactly one basis.

    `core.ev.effective_price` is used wherever it applies rather than
    reimplemented. The cheapest-model basis has no function in `core` -- the
    production path deliberately charges the maximum -- so it is built from
    `core.fees.fee_candidates` and `core.prices.tenths_to_dollars`, the same two
    pieces `effective_price` is built from, and never from a second formula.

    Raises on an untradeable price rather than pricing at a zero fee, which is
    `core.ev`'s rule and the reason it exists: an ask of 0 tenths at a 0.0 fee
    reports a breakeven win rate of 0% and an edge of +55c out of nothing.
    """
    if basis.fee_model == "max":
        return effective_price(ask_tenths, basis.contracts, maker=basis.maker)

    if not is_valid_price(ask_tenths):
        raise ValueError(
            f"ask {ask_tenths} tenths is not a tradeable price. Refusing rather "
            f"than pricing it at a zero fee, which fabricates an edge."
        )
    fee = min(fee_candidates(ask_tenths, basis.contracts, basis.maker).values())
    return tenths_to_dollars(ask_tenths) + fee / basis.contracts


def loosest_fair(row: Row) -> Optional[float]:
    """`max(p_mult, p_add, p_power, p_shin)`, or `None` if any is missing.

    A missing method is a real state (`devig.py:181` -- `p_shin` is NULL where
    the root-finder fell back), and `max` over three methods is a **different
    estimator** from `max` over four. So the row is dropped and counted, never
    imputed.
    """
    methods = (row.p_multiplicative, row.p_additive, row.p_power, row.p_shin)
    if any(m is None for m in methods):
        return None
    return max(methods)


def confirmatory_shortfall_tenths(row: Row, basis: FeeBasis) -> Optional[float]:
    """§6's `S_k = 1000*effective_price(...) - 1000*max(p_mult, p_add, p_power, p_shin)`.

    `None` when the row carries no per-method probabilities -- dropped and
    counted (§2), never imputed.
    """
    fair = loosest_fair(row)
    if fair is None or row.ask_tenths is None:
        return None
    return 1000.0 * basis_effective_price_dollars(basis, row.ask_tenths) - 1000.0 * fair


def exact_bound_clears(
    row: Row, alternatives: Sequence[FeeBasis] = EXACT_ALTERNATIVES
) -> Optional[bool]:
    """Does the exact bound clear this row? ALT-1 **or** ALT-2, individually.

    Each alternative is priced from its own `FeeBasis` in its own call; there is
    no code path in this module that combines two bases into one price, and
    `FeeBasis` refuses to be constructed in the stacked configuration. The union
    is taken over *results*, which cannot express a stack.
    """
    results = [confirmatory_shortfall_tenths(row, b) for b in alternatives]
    if any(s is None for s in results):
        return None
    return any(s < 0.0 for s in results)


def fee_knob_delta_violations() -> list[str]:
    """§S2 item 10: `E1min - E1 == Delta(price)` per §C4, executed over 999 prices.

    An **assertable invariant, not a hope** (§5). It is also an independent
    recomputation of Lane A §C1's table: if the two disagree, one of the two
    documents is describing a fee model the code does not implement.
    """
    return _band_violations(
        FEE_KNOB_DELTA_BANDS,
        lambda p: 1000.0
        * (
            basis_effective_price_dollars(ALT_0, p)
            - basis_effective_price_dollars(ALT_1, p)
        ),
        "fee knob",
    ) + _band_violations(
        MAKER_KNOB_DELTA_BANDS,
        lambda p: 1000.0
        * (
            basis_effective_price_dollars(ALT_0, p)
            - basis_effective_price_dollars(ALT_2, p)
        ),
        "maker knob",
    )


def _band_violations(bands, measure, label: str) -> list[str]:
    expected = {}
    for low, high, value in bands:
        for price in range(low, high + 1):
            expected[price] = value
    out = []
    for price in range(1, 1000):
        actual = round(measure(price), 6)
        if abs(actual - expected[price]) > 1e-6:
            out.append(f"{label} at {price}: expected {expected[price]}, got {actual}")
    return out


def p5_violations(rows: Iterable[Row], tolerance: float = 1e-9) -> list[str]:
    """§P5 / Lane B §C2: `p_conservative == min(four) == fair_probability`.

    Both are equalities the code should make **necessary**. If either fails
    anywhere the join is wrong, the design is void, and no statistic is computed.
    """
    out = []
    for row in rows:
        methods = (row.p_multiplicative, row.p_additive, row.p_power, row.p_shin)
        if row.p_conservative is None or any(m is None for m in methods):
            continue
        if abs(row.p_conservative - min(methods)) > tolerance:
            out.append(
                f"row {row.id}: p_conservative {row.p_conservative} != "
                f"min(four) {min(methods)}"
            )
        if (
            row.fair_probability is not None
            and abs(row.fair_probability - row.p_conservative) > tolerance
        ):
            out.append(
                f"row {row.id}: fair_probability {row.fair_probability} != "
                f"p_conservative {row.p_conservative}"
            )
    return out


# ---------------------------------------------------------------------------
# Descriptive readouts. §5's grids, §6's percentiles, the power check.
# ---------------------------------------------------------------------------


def shortfall_histogram(shortfalls: Iterable[float]) -> dict[tuple[float, float], int]:
    """§5's eight cells, **left-open right-closed**: `low < S <= high`."""
    counts = {cell: 0 for cell in SHORTFALL_CELLS}
    for value in shortfalls:
        for low, high in SHORTFALL_CELLS:
            if low < value <= high:
                counts[(low, high)] += 1
                break
    return counts


def percentile(sorted_values: Sequence[float], q: float) -> Optional[float]:
    """Nearest-rank percentile: `rank = ceil(q/100 * n)`, an observed value.

    Nearest rank rather than interpolation, on purpose. Every reported quantile
    is then an actual row's shortfall, so `p0` is exactly `min`, `p100` is
    exactly `max`, and no printed number describes a row that does not exist --
    which matters when the headline sentence names *the nearest row*.
    """
    n = len(sorted_values)
    if n == 0:
        return None
    if q <= 0:
        return sorted_values[0]
    if q >= 100:
        return sorted_values[-1]
    return sorted_values[max(0, math.ceil(q / 100.0 * n) - 1)]


def percentile_block(values: Iterable[float]) -> dict[str, Optional[float]]:
    """§6's fixed percentile set: min, p1, p5, p10, p25, p50, p75, p90, max."""
    ordered = sorted(values)
    block: dict[str, Optional[float]] = {"min": percentile(ordered, 0)}
    for q in PERCENTILES:
        block[f"p{q}"] = percentile(ordered, q)
    block["max"] = percentile(ordered, 100)
    return block


def grid_b_bucket(ask_tenths: int) -> Optional[tuple[int, int]]:
    """Grid B cell for an ask, on the **price actually paid**, never a mid.

    Left-closed right-open, matching `validate._bucket_of`, whose `BUCKETS` this
    reads. A bucket in the predecessor project showed a +25.4 point edge and
    lost $4.92 a market for exactly the mid-versus-ask reason.
    """
    for low, high in GRID_B:
        if low <= ask_tenths < high:
            return (low, high)
    return None


def in_maker_band(ask_tenths: int) -> bool:
    """§5's exact maker band `[173, 827]` tenths, inclusive."""
    low, high = MAKER_BAND_TENTHS
    return low <= ask_tenths <= high


def rule_of_three(n_clusters: int) -> Optional[float]:
    """The one-sided 95% upper bound on a per-game rate given zero events: `3/G`.

    The **only** inferential quantity in the registration. `sqrt(p(1-p)/n)` is
    correct for none of the others and must not appear in the output: there is
    no `p` and there is no sample. `n_rows` is uptime; `n_clusters` is evidence.
    """
    if n_clusters <= 0:
        return None
    return 3.0 / n_clusters
