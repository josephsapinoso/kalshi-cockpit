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

# The number of contributing books below which `consensus_devig` reports
# `market_width = None`. This is **not** `SuppressionConfig.min_book_count`:
# it is `devig.py`'s own hardcoded `len(first_values) > 1`, and the two are
# equal today by coincidence rather than by construction. Named here so the
# invariant check below is written against the producer's rule, not against a
# threshold that is free to move. See ADR 0019.
_CONSENSUS_NEEDS_TWO_BOOKS = 2


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
    #
    # **This threshold has a SECOND job it was never justified for, and it is
    # now load-bearing: it is the only thing bounding a fabricated fair.** See
    # ADR 0019. The agreement-based guards -- method spread, market width, book
    # count -- are uniformly blind to correlated garbage, because placeholder
    # lines agree with each other perfectly. Two books quoting a symmetric
    # two-way line produce `fair = 0.5`, `market_width = 0.0` and a method
    # spread of ~1e-11, and pass every one of them.
    #
    # What stops such a row is the arithmetic here. At the deployed taker fee
    # (flat 20.0 tenths across this band) a fabricated 0.5 fair only clears
    # `0 < net_edge <= 40.0` when the ask sits in **[440, 479] tenths = 44.0c
    # to 47.9c** -- a 4.0c window in which the fabrication is nearly right
    # anyway. Raising the ceiling widens that window by 1c per 10 tenths.
    #
    # `TestTheCeilingBoundsFabricatedFairs` pins the property directly, because
    # the older `20.0 <= ceiling <= 60.0` assertion is an inequality, not a pin,
    # and stays green while the hole grows by half.
    edge_ceiling_tenths: float = 40.0

    # Minimum contracts that must be available at the quoted ask. An edge you
    # cannot fill is not an edge.
    min_depth_contracts: float = 10.0

    # Require at least this many books before trusting a consensus.
    min_book_count: int = 2


# Every code `evaluate_suppression` can write into `suppressed_reason`.
#
# **This is part of the strategy config hash, and it has to be.** ADR 0019 and
# `runner.py`'s own rule -- *"everything the counted column depends on, and
# nothing else"* -- require that anything able to move `actionable` mints a new
# `strategy_config_version`. `actionable` is
# `suppressed_reason IS NULL AND reference_contracts > 0`, so the **set of
# checks** determines it exactly as much as the thresholds do.
#
# Only `SuppressionConfig.__dict__` was hashed before, which is a set of
# *field values*. Adding, removing or renaming a check changes no field, so it
# minted no version, so two check-vocabularies would have been pooled into one
# dataset with nothing recording the split. That is the same defect
# `measurement-skeptic` already found here once, when `kelly_fraction` was in
# the hash and `max_order_contracts` was not.
#
# Held as a declared constant rather than derived at runtime because the codes
# depend on which branch each input takes -- `no_depth` and
# `insufficient_depth` are mutually exclusive on any single call, so no one
# evaluation observes them all. `TestTheDeclaredVocabularyMatchesTheCode` reads
# the source and fails if this list drifts from the `Check(...)` names.
ALL_CHECK_NAMES: tuple[str, ...] = (
    "stale_kalshi_quote",
    "stale_odds",
    "no_commence_time",
    "commence_skew",
    "no_depth",
    "insufficient_depth",
    "too_few_books",
    "no_market_width",
    "wide_market",
    "inconsistent_consensus_metadata",
    "edge_within_method_noise",
    "suspicious_edge",
)


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
    market_width: Optional[float],
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
    # **The message used to read "book last moved {x}min ago". That was false**,
    # and the correction is wording only -- when this fires is unchanged. See
    # ADR 0020 (queued), which owns the remedy; this is the honest description of
    # what the number already is.
    #
    # `odds_age_ms` is measured from The Odds API's `last_update`, which is a
    # **scrape** timestamp, not a **reprice** timestamp. Measured on the captured
    # fixture (15 MLB events, 30 books, 440 book+event pairs):
    #
    #   320 of 320 pairs quoting MORE THAN ONE priceable market carry one
    #   identical stamp across every market they quote (258 of 258 of the
    #   three-market subset).
    #
    # **Counted over the 320, not over all 440**, because 120 pairs quote a
    # single priceable market and agreement with oneself is vacuous --
    # including them inflates the denominator with rows that could not have
    # disagreed. The unanimity is total either way; the honest number is the
    # smaller one.
    #
    # **Priceable markets only**, per PRICEABLE_MARKETS. Counting raw payload
    # keys would give 335, but `h2h_lay` is in EXCLUDED_MARKETS and is never
    # stored, so it cannot contribute to `odds_age_ms` and does not belong in a
    # denominator about it. Re-derive with `scripts/census_odds_stamps.py`.
    #
    # And 27 of 30 books carry exactly one distinct stamp across all fifteen
    # games, counting book- and market-level stamps together (29 of 30 on the
    # book-level stamp alone -- state which, the two differ). FanDuel reports
    # `13:49:00Z` for three markets on fifteen different games. No book reprices
    # fifteen moneylines, run lines and totals in the same second.
    #
    # The payload-level signature is the same fact seen whole: 19 distinct
    # stamps spanning 115s across 30 books, the latest landing 9s before our
    # fetch. That is a crawler working through a queue, not a market moving.
    #
    # So this measures **how long since the aggregator last polled the book**,
    # not how long since the line moved. A book that has not repriced in six
    # hours reads as perfectly fresh for as long as the aggregator keeps
    # scraping it. The guard still does real work -- it catches our own sweep
    # having gone stale -- but it is not the check its name implies.
    checks.append(
        Check(
            "stale_odds",
            odds_age_ms <= config.max_odds_age_ms,
            f"book last scraped {odds_age_ms / 60000:.1f}min ago "
            f"(limit {config.max_odds_age_ms / 60000:.0f}min); this is the "
            f"aggregator's poll time, not the last time the line moved",
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
    # `None` means the width could not be measured -- fewer than two books
    # contributed to the consensus -- and it must REFUSE, not pass. It used to
    # arrive as `0.0`, which reads as "every book agreed perfectly", so the
    # least-evidenced consensus in the system cleared this check most easily.
    # Distinct from `wide_market` so the suppression log says which happened:
    # "books disagree" and "there was no second book to disagree with" call for
    # different fixes.
    if market_width is None:
        checks.append(
            Check(
                "no_market_width",
                False,
                "fewer than two books in the consensus, so book disagreement "
                "could not be measured",
            )
        )
    else:
        checks.append(
            Check(
                "wide_market",
                market_width <= config.max_market_width,
                f"books disagree by {market_width * 100:.1f} points "
                f"(limit {config.max_market_width * 100:.0f})",
            )
        )

    # `too_few_books` and `no_market_width` fire on the identical condition
    # today -- 185 rows each over a 1,000-row sample, symmetric difference 0 --
    # and that reads as a case for merging them. It is not. **The equivalence
    # holds only at `min_book_count == 2`, and is coupled by nothing:**
    # `devig.py:312` hardcodes a literal `1` (`len(first_values) > 1`) while the
    # check above reads `config.min_book_count`, and the config object is not
    # even in scope inside `consensus_devig`. Set `min_book_count = 3` and a
    # two-book row fails `too_few_books` while its width is a real measured
    # float. Two limits on one quantity, currently equal by coincidence.
    #
    # So keep both codes -- they mean different things to a reader ("there was
    # no second book" vs "the books disagree") -- and assert the producer's
    # invariant instead, which is the thing that was previously only true by
    # accident. See ADR 0019.
    width_says_thin = market_width is None
    count_says_thin = book_count < _CONSENSUS_NEEDS_TWO_BOOKS
    checks.append(
        Check(
            "inconsistent_consensus_metadata",
            width_says_thin == count_says_thin,
            f"market_width is {'None' if width_says_thin else 'measured'} but "
            f"book_count is {book_count} -- the consensus producer reported a "
            f"width and a book count that cannot both be true",
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


# The three checks that fire only when their input is ABSENT. Each is one arm
# of an if/else above whose other arm evaluates the present value, so exactly
# one of each pair runs per evaluation -- which is why a full verdict board
# can be reconstructed from `suppressed_reason` alone (see `gauntlet_view`).
_FAIL_ONLY_TWIN: dict[str, str] = {
    "no_commence_time": "commence_skew",
    "no_depth": "insufficient_depth",
    "no_market_width": "wide_market",
}


def gauntlet_view(suppressed_reason: Optional[str]) -> dict:
    """The full pass/refused board for one stored row, from its reason alone.

    The Skeptic panel (ADR 0068) renders every check's verdict, not just the
    failures -- "ran and passed" is the reassurance the panel exists to give,
    and only the failures were ever stored. Reconstruction is exact because
    `evaluate_suppression` appends every check it runs and `reason` names
    every failure: a code absent from the reason either passed (it always
    runs) or was never taken (it is the absent-input arm of an if/else whose
    sibling ran instead -- `_FAIL_ONLY_TWIN`).

    Verdicts: ``refused`` (named in the reason), ``passed`` (runs on every
    evaluation, or the value-present arm whose fail-only twin did not fire),
    ``not_taken`` (the arm the branch did not take). ``sizing`` carries any
    ``sizing:``-prefixed refusal through verbatim (`engine.py` writes those
    when no check fired); ``unknown`` carries codes this build's vocabulary
    does not name, so a newer server's reason still renders rather than
    silently vanishing.

    What this does not establish: anything about *now*. The verdicts are
    facts about the moment the row was written -- the caller must serve the
    basis time beside them and the screen must caption it.
    """
    entries = [
        e.strip() for e in (suppressed_reason or "").split(",") if e.strip()
    ]
    sizing = [e for e in entries if e.startswith("sizing:")]
    codes = {e for e in entries if not e.startswith("sizing:")}
    unknown = sorted(codes - set(ALL_CHECK_NAMES))

    verdicts: list[dict] = []
    for name in ALL_CHECK_NAMES:
        if name in codes:
            verdict = "refused"
        elif name in _FAIL_ONLY_TWIN:
            # Fail-only: it either fired (named above) or never ran.
            verdict = "not_taken"
        elif name in {v for k, v in _FAIL_ONLY_TWIN.items() if k in codes}:
            # Its fail-only twin fired, so this arm of the branch never ran.
            verdict = "not_taken"
        else:
            verdict = "passed"
        verdicts.append({"code": name, "verdict": verdict})

    return {"checks": verdicts, "sizing": sizing, "unknown": unknown}
