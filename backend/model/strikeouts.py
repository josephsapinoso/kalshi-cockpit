"""One pitcher's strikeout distribution, and from it the whole Kalshi ladder.

Kalshi prices `KXMLBKS` as a ladder: `2+`, `3+`, `4+` ... `15+`, each a separate
binary market on the same start. A book quotes one line; Kalshi quotes fourteen.
**That is the opening this module exists to use.** Fourteen markets driven by one
underlying count cannot be independently mispriced -- they are fourteen readings
of a single distribution -- so a model that prices the *distribution* prices
every rung coherently, and any rung that disagrees with its neighbours is
disagreeing with arithmetic rather than with an opinion.

THE MODEL, AND WHY IT IS A COMPOUND
-----------------------------------
A start's strikeout count is two uncertainties stacked, not one:

    BF       how many batters he faces at all  -- how long he lasts
    K | BF   how many of those he strikes out  -- how good he is

    P(K = k) = SUM_bf  P(BF = bf) * Binomial(k; bf, p)

Collapsing that to a single Binomial at the *mean* BF understates the variance,
and it understates it in the direction that matters: the tails of the ladder are
exactly where a ladder's mispricing would live, because `10+` and `2+` are the
rungs whose prices are least anchored by volume. A model that is confidently
wrong at the tails would surface its largest apparent edges there. See
`tasks/lessons.md` -- a large apparent edge is a bug until proven otherwise.

The two inputs are supplied by the caller and neither is decided here. This
module is pure arithmetic on `(expected_bf, sd_bf, k_per_bf)`; where those
numbers come from is a separate, licence-constrained question answered by ADR
0035 and by whatever module ends up implementing it.

THE JOIN TO THE LADDER NEEDS NO ARITHMETIC
------------------------------------------
`backend/kalshi/props.py` establishes that Kalshi publishes `floor_strike` on
every prop market and it is already `N - 0.5` -- the `2+` market carries `1.5`.
So this module takes `floor_strike` directly and computes `P(K > floor_strike)`.
Nothing is added, nothing is rounded, and the `N+` -> `N - 0.5` conversion that
a reader would expect to find here is deliberately absent, because a computation
on a money path is a thing that can be wrong.

WHAT THIS MODULE DOES NOT ESTABLISH
-----------------------------------
- **Not that the parameters are right.** It is a function of its inputs. A
  perfect distribution around a wrong `k_per_bf` is a wrong price at every rung
  simultaneously, and it will look internally consistent while being so.
- **Not that a discretised normal is the right shape for `BF`.** It is symmetric
  and real starts are not: a blowup truncates a start at 12 batters while nothing
  extends one past ~30, so the true `BF` distribution is left-skewed. The normal
  is a stated placeholder, pinned by `TestMeanIsPreserved` so a replacement is
  checked against the same invariant rather than eyeballed.
- **Not that `K | BF` is Binomial.** It assumes each batter faced is an
  independent trial at a constant rate. Real starts have within-game drift
  (fatigue, third time through the order) and batter-quality variation across
  the lineup. Both add variance this understates.
- **Not that any resulting edge is tradeable.** No fee, no size, no depth and no
  suppression rule appears in this file. Those live downstream and the edge that
  survives them is a different number.
- **Nothing about batters.** The compound shape here is specific to a starter's
  workload being the dominant uncertainty. A batter ladder's `PA` is ~4 with a
  much tighter spread and is not this problem.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

# A start has never come close to either bound. The support is truncated rather
# than infinite so the pmf is a finite object that can be asserted about; the
# bounds are deliberately far outside anything real so that truncation never
# silently removes mass a caller cares about.
#
# 61 is the modern record for batters faced in a start; 0 is a pitcher who is
# announced and then scratched, which is a real outcome and must not be
# unreachable.
MIN_BATTERS_FACED = 0
MAX_BATTERS_FACED = 70

#: Total pmf mass may drift from 1 by at most this much before `distribution`
#: refuses. Loose enough for float summation over ~70 terms, tight enough that a
#: genuine normalisation bug cannot hide inside it.
MASS_TOLERANCE = 1e-9


@dataclass(frozen=True)
class StrikeoutDistribution:
    """The full pmf over strikeouts in one start, plus what produced it.

    `pmf[k]` is `P(K = k)`. The index *is* the strikeout count -- there is no
    offset -- so `pmf[0]` is the probability of a start with no strikeouts.

    The parameters are carried alongside the pmf on purpose. A probability that
    has been separated from the assumptions that produced it is the thing this
    repo has been burned by: `tasks/lessons.md` records that a bare number
    outlives its caveats, and a ladder priced off a stale `k_per_bf` looks
    exactly like a ladder priced off a fresh one.
    """

    pmf: tuple[float, ...]
    expected_bf: float
    sd_bf: float
    k_per_bf: float

    @property
    def mean(self) -> float:
        """Expected strikeouts. Equals `expected_bf * k_per_bf` by construction."""
        return sum(k * p for k, p in enumerate(self.pmf))

    def at_least(self, threshold: int) -> float:
        """`P(K >= threshold)`, the quantity a Kalshi `N+` market settles on.

        Prefer `probability_over` when you hold Kalshi's `floor_strike`: it takes
        the published number and needs no `N -> N - 0.5` step.
        """
        if threshold <= 0:
            return 1.0
        return sum(self.pmf[threshold:]) if threshold < len(self.pmf) else 0.0

    def probability_over(self, floor_strike: float) -> float:
        """`P(K > floor_strike)`, taking Kalshi's published strike as given.

        `floor_strike` is `1.5` on the `2+` market. Summing the mass strictly
        above it is the settlement rule stated arithmetically, with no rounding
        and no half-integer assumption -- a `floor_strike` Kalshi one day
        publishes as an integer would still be answered correctly.
        """
        return sum(p for k, p in enumerate(self.pmf) if k > floor_strike)


def batters_faced_pmf(
    expected_bf: float,
    sd_bf: float,
) -> Optional[tuple[float, ...]]:
    """A discretised, truncated normal over batters faced. `None` if unreadable.

    Indexed by batter count from `MIN_BATTERS_FACED`, and renormalised **after**
    truncation so the returned mass sums to 1 over the support that exists
    rather than over the support the normal wanted.

    Returns `None` -- never a default, never a point mass -- when the inputs
    cannot describe a start. A caller handed `None` must refuse to price, which
    is the repo's rule: unreadable resolves to `None`, never `0`.
    """
    if not _is_finite(expected_bf) or not _is_finite(sd_bf):
        return None
    if expected_bf <= 0 or expected_bf > MAX_BATTERS_FACED:
        return None
    if sd_bf <= 0:
        return None

    weights = [
        math.exp(-0.5 * ((bf - expected_bf) / sd_bf) ** 2)
        for bf in range(MIN_BATTERS_FACED, MAX_BATTERS_FACED + 1)
    ]
    total = sum(weights)
    if total <= 0:
        # `expected_bf` so far outside the support that every weight underflowed.
        # Refuse rather than return a uniform, which would be a confident lie.
        return None
    return tuple(w / total for w in weights)


def distribution(
    expected_bf: float,
    sd_bf: float,
    k_per_bf: float,
) -> Optional[StrikeoutDistribution]:
    """Compound the two uncertainties into one pmf over strikeouts.

    `k_per_bf` is strikeouts per batter faced -- **not** per inning and not per
    nine. A league-average starter sits near 0.22; the units are the most likely
    place for a caller to be wrong by a factor of four, so the bound below
    refuses anything outside `(0, 1)` and the caller states its own units.

    `None` on any unreadable input, including a `k_per_bf` at exactly 0 or 1: a
    pitcher who strikes out every batter or none is not a start, it is a
    parsing failure wearing a plausible number.
    """
    if not _is_finite(k_per_bf) or not 0 < k_per_bf < 1:
        return None

    bf_weights = batters_faced_pmf(expected_bf, sd_bf)
    if bf_weights is None:
        return None

    pmf = [0.0] * (MAX_BATTERS_FACED + 1)
    for offset, weight in enumerate(bf_weights):
        if weight == 0.0:
            continue
        bf = MIN_BATTERS_FACED + offset
        for k in range(bf + 1):
            pmf[k] += weight * _binomial_pmf(k, bf, k_per_bf)

    mass = sum(pmf)
    if not _is_finite(mass) or abs(mass - 1.0) > MASS_TOLERANCE:
        # The compound is a mixture of proper distributions and must sum to 1.
        # If it does not, something upstream is wrong in a way no downstream
        # consumer can detect, so it never leaves this function.
        return None

    return StrikeoutDistribution(
        pmf=tuple(pmf),
        expected_bf=expected_bf,
        sd_bf=sd_bf,
        k_per_bf=k_per_bf,
    )


def ladder_probabilities(
    dist: StrikeoutDistribution,
    floor_strikes: Sequence[float],
) -> tuple[float, ...]:
    """Price every rung of one Kalshi ladder from one distribution.

    Order is the caller's -- the returned tuple is positionally aligned with
    `floor_strikes`, not sorted -- so a caller holding markets in the order the
    API returned them can zip the two together without a second join.

    The result is monotone non-increasing in `floor_strike` by construction, and
    that is the property which makes the whole ladder one opinion rather than
    fourteen. `tests/test_strikeouts.py` pins it.
    """
    return tuple(dist.probability_over(strike) for strike in floor_strikes)


def _binomial_pmf(k: int, n: int, p: float) -> float:
    """`P(X = k)` for `X ~ Binomial(n, p)`.

    Written out rather than taken from `scipy`, which this repo does not depend
    on, and computed in log space.

    **The log space is headroom, not a fix for a bug that exists at `n = 70`.**
    An earlier version of this docstring claimed the direct form
    `comb(n, k) * p**k * (1-p)**(n-k)` overflows here. It does not: measured
    2026-08-17, the direct form is fine to `n = 1029` and first raises
    `OverflowError` at `n = 1030`, and at `n = 70, p = 0.22` the two forms agree
    to `5.5e-15` -- below `MASS_TOLERANCE`. **No test in
    `tests/test_strikeouts.py` can tell the two implementations apart**,
    confirmed by mutation, and that is recorded rather than papered over.

    It stays in log space anyway because it costs nothing and the safety is
    unconditional: `MAX_BATTERS_FACED` is a constant someone may raise, and a
    correctness property that depends on a bound elsewhere in the file is the
    kind that survives until the day it does not.
    """
    if k < 0 or k > n:
        return 0.0
    log_p = (
        math.lgamma(n + 1)
        - math.lgamma(k + 1)
        - math.lgamma(n - k + 1)
        + k * math.log(p)
        + (n - k) * math.log1p(-p)
    )
    return math.exp(log_p)


def _is_finite(value: float) -> bool:
    """`False` for `None`, `NaN`, and both infinities.

    `NaN` is the specific hazard: it propagates through every sum here without
    raising, so a pmf built from one would normalise, sum to `NaN`, and fail the
    mass check -- but only after the caller had already been handed the object
    in a different code path. Rejecting at the boundary is cheaper.
    """
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False
