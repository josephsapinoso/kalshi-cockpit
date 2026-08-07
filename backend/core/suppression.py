"""Suppression: the layer that decides an apparent edge is a bug.

The governing rule of this project is that **a large apparent edge is a bug
until proven otherwise**. Kalshi prices sports to about 2c and the venue is
contested by market makers quoting under 200ms. A 6c edge sitting there
unclaimed is not an opportunity that thirteen professional firms overlooked;
it is a stale quote, a mis-joined fixture, or a market that means something
other than what we think it means.

So every candidate runs a gauntlet, and **every rejection is recorded with its
reason**. The suppression log is analysable data in its own right: a rule
firing constantly is either miscalibrated or catching a real upstream problem,
and both are findings. A filter that discards what it rejects can never be
audited -- which is how the previous project's discovery loop recorded
throttled markets as illiquid ones for the life of the project.

The checks are ordered cheapest-first, but **all of them run**. Short-circuiting
on the first failure would mean a row suppressed for staleness never reveals
that it was also mis-matched, and the second fact is the more important one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .prices import PRICE_MAX


@dataclass(frozen=True)
class SuppressionConfig:
    """Thresholds. All are deliberately conservative defaults.

    These are the flywheel's unit of change: every recommendation records the
    `strategy_config_version` that produced it, so the effect of loosening any
    one of these is measurable after the fact rather than a matter of opinion.
    """

    max_kalshi_quote_age_ms: int = 30_000
    max_odds_age_ms: int = 900_000            # 15 min

    # Must stay >= `match.linker.DEFAULT_COMMENCE_TOLERANCE_MS`, which is
    # asserted by `TestTheTwoCommenceLimitsAgree`. These are two limits on the
    # same quantity living in two modules, and the tighter one wins silently:
    # at 2h against the linker's 4h, every fixture the linker correctly matched
    # was then suppressed here, and a full live slate produced 76 recommendations
    # of which 76 were rejected for `commence_skew`.
    #
    # 4h because Kalshi's `occurrence_datetime` runs exactly 3 hours late --
    # measured across MLB and WNBA on 2026-08-07, and reproduced by every link
    # in that run carrying a skew of -179 or -180 min. A limit below the
    # systematic offset is not a risk control, it is an off switch.
    max_commence_skew_ms: int = 4 * 3_600_000  # 4 h

    # Probability points across books on the same outcome. Wide disagreement
    # means the "consensus" is not one.
    max_market_width: float = 0.06

    # Edge above this is treated as evidence of a defect, not an opportunity.
    # 40 tenths = 4c. Kalshi prices to ~2c, so 4c is already well outside what
    # the venue plausibly leaves lying around.
    edge_ceiling_tenths: float = 40.0

    # Minimum contracts that must be available at the quoted ask. An edge you
    # cannot fill is not an edge.
    min_depth_contracts: float = 10.0

    # Require at least this many books before trusting a consensus.
    min_book_count: int = 2


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str

    def __str__(self) -> str:
        return f"{'ok ' if self.passed else 'FAIL'} {self.name}: {self.detail}"


@dataclass(frozen=True)
class SuppressionResult:
    checks: tuple[Check, ...] = field(default_factory=tuple)

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if not c.passed)

    @property
    def suppressed(self) -> bool:
        return bool(self.failures)

    @property
    def reason(self) -> Optional[str]:
        """A single short code for the database, naming every failure.

        All failures, not just the first: a row suppressed for staleness that
        was *also* mis-matched needs both facts, and the second matters more.
        """
        if not self.failures:
            return None
        return ",".join(c.name for c in self.failures)

    @property
    def detail(self) -> str:
        return "; ".join(c.detail for c in self.failures)


def evaluate_suppression(
    *,
    config: SuppressionConfig,
    kalshi_quote_age_ms: int,
    odds_age_ms: int,
    commence_skew_ms: Optional[int],
    depth_at_ask: Optional[float],
    contracts: int,
    market_width: float,
    book_count: int,
    edge_tenths: float,
    method_spread_probability: float,
) -> SuppressionResult:
    """Run every check. Returns what failed and why.

    `edge_tenths` is the *post-fee* edge per contract, and
    `method_spread_probability` is the max-minus-min across devig methods for
    the side being bought.
    """
    checks: list[Check] = []

    # --- freshness --------------------------------------------------------
    # Enforced here AND again server-side on the order endpoint. The UI
    # disabling a button is not a control.
    checks.append(
        Check(
            "stale_kalshi_quote",
            kalshi_quote_age_ms <= config.max_kalshi_quote_age_ms,
            f"kalshi quote {kalshi_quote_age_ms / 1000:.1f}s old "
            f"(limit {config.max_kalshi_quote_age_ms / 1000:.0f}s)",
        )
    )
    checks.append(
        Check(
            "stale_odds",
            odds_age_ms <= config.max_odds_age_ms,
            f"book last moved {odds_age_ms / 60000:.1f}min ago "
            f"(limit {config.max_odds_age_ms / 60000:.0f}min)",
        )
    )

    # --- identity ---------------------------------------------------------
    # A large commence skew means we are comparing two different fixtures that
    # happen to share teams. That produces an "edge" from nothing.
    if commence_skew_ms is None:
        checks.append(
            Check("no_commence_time", False, "no commence time to compare")
        )
    else:
        checks.append(
            Check(
                "commence_skew",
                abs(commence_skew_ms) <= config.max_commence_skew_ms,
                f"start times differ by {abs(commence_skew_ms) / 60000:.0f}min "
                f"(limit {config.max_commence_skew_ms / 60000:.0f}min)",
            )
        )

    # --- fillability ------------------------------------------------------
    if depth_at_ask is None:
        checks.append(
            Check("no_depth", False, "no size quoted at the ask")
        )
    else:
        required = max(config.min_depth_contracts, float(contracts))
        checks.append(
            Check(
                "insufficient_depth",
                depth_at_ask >= required,
                f"{depth_at_ask:.0f} available at the ask, need {required:.0f}",
            )
        )

    # --- consensus quality ------------------------------------------------
    checks.append(
        Check(
            "too_few_books",
            book_count >= config.min_book_count,
            f"{book_count} book(s), need {config.min_book_count}",
        )
    )
    checks.append(
        Check(
            "wide_market",
            market_width <= config.max_market_width,
            f"books disagree by {market_width * 100:.1f} points "
            f"(limit {config.max_market_width * 100:.0f})",
        )
    )

    # --- the edge itself --------------------------------------------------
    # Measured on real lines: the four devig methods spread ~0.18 points on an
    # even moneyline and ~2.03 on a longshot. If they disagree by more than the
    # edge being claimed, the "edge" is a statement about method choice, not
    # about the market. This check falls directly out of that measurement.
    spread_tenths = method_spread_probability * PRICE_MAX
    checks.append(
        Check(
            "edge_within_method_noise",
            # A non-positive edge is simply not a bet -- sizing returns zero
            # contracts and the row reads "No edge." Firing a *suppression* on
            # it would bury the genuine diagnostics: most candidates on any
            # slate have no edge, so this code would dominate the suppression
            # summary and make it useless for spotting a miscalibrated rule.
            edge_tenths <= 0 or edge_tenths > spread_tenths,
            f"edge {edge_tenths:.1f} tenths does not exceed the "
            f"{spread_tenths:.1f}-tenth spread between devig methods",
        )
    )

    # A large edge is evidence of a defect. Kalshi prices to ~2c against 13
    # sub-200ms market makers; it does not leave 5c on the table.
    checks.append(
        Check(
            "suspicious_edge",
            edge_tenths <= config.edge_ceiling_tenths,
            f"edge {edge_tenths / 10:.1f}c exceeds the "
            f"{config.edge_ceiling_tenths / 10:.0f}c ceiling -- treat as a "
            f"data defect (stale quote, wrong fixture, or wrong market type) "
            f"until investigated",
        )
    )

    return SuppressionResult(checks=tuple(checks))
