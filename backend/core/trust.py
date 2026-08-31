"""The sweet spot: how much a number deserves to be acted on.

Joe asked for a score that decides yes or no on a bet, and chose, when the
options were put to him on 2026-08-31, **trust rather than edge**.

**That choice is what makes this module possible, and it is not a preference.**
A score containing the consensus-vs-Kalshi gap would rank the *least*
trustworthy rows highest: `beta = -0.141` with every interval below the
registered 0.40 threshold (ADR 0021, ADR 0034), so that term is measured
negatively predictive. Adding it would make the score worse by arithmetic.
Trust is a different quantity, and nothing in the record forbids measuring it.

WHAT THIS SAYS
--------------
*This number is worth acting on.* Nothing more. It is evidence quality, not
bet quality, and the distinction is the whole design:

    "9 books agree within 1.2 points and the quote is 20 seconds old"
        -> you can rely on the number
    "this bet will win"
        -> a claim this module does not make and cannot support

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That a high-trust bet wins.** Nothing here has been scored against an
  outcome. Doing so would be a new measurement needing its own registration.
- **That the checks are equally important.** They are counted equally because
  that is the only weighting that invents nothing (see below), not because
  anyone measured them to be equal.
- **That a full score means bet.** The desk informs a bet Joe is making anyway
  (ADR 0071); it does not manufacture action.

NO INVENTED THRESHOLDS, NO INVENTED WEIGHTS
-------------------------------------------
`lib/dispersion.ts` already sets the standard: *"the strip computes no
composite -- that would be a model, and it would need its own ADR."*
`agents/base.py` adds that an unfalsifiable estimate in a money path is worse
than none.

So every threshold here is **passed in from the config that already enforces
it elsewhere** -- `StalenessConfig`, `SuppressionConfig`, `ladder.
AGREEMENT_SPREAD_POINTS` -- and none is written down twice. `config.py`
already refuses to boot when two limits on one quantity disagree
(`StalenessLimitsDisagree`); this module joins that discipline rather than
becoming the second definition that drifts.

The score is a **count of checks passed**. Equal weighting is a choice, and it
is the only one that adds no unmeasured claim. "Not every check matters
equally" is answered by **naming every failure**, not by a weight vector --
which is the reasoning `SuppressionResult.reason` already carries in its own
docstring: *"All failures, not just the first: a row suppressed for staleness
that was also mis-matched needs both facts, and the second matters more."*

UNKNOWN IS NOT A PASS
---------------------
The third state is the one most likely to be quietly broken, and it always
breaks in the flattering direction. A prop the skeptic never ran
(`not_on_this_path`), a game with no scout briefing -- these are **not**
evidence of quality. Folding them into `pass` would make the least-examined
row score highest, which is the same failure mode as the `market_width = 0.0`
bug `suppression.py` records: *"the least-evidenced consensus in the system
cleared this check most easily."*

So `passed`, `known` and `total` are all reported and a caller may not
reconstruct one from the others by assuming.

BOUNDARY
--------
This module **writes nothing** and no interlock may read it. `gate.py` must
never import it -- the same boundary `manual_orders`, `combo_orders` and the
hedge tables each have. It is pure: primitives in, a result out, no database
and no clock of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Sequence

from .ladder import AGREEMENT_SPREAD_POINTS

#: The three states. `unknown` is not a pass and not a failure -- it is the
#: absence of a look, and it is reported separately so it cannot be mistaken
#: for either.
TrustState = Literal["pass", "fail", "unknown"]


@dataclass(frozen=True)
class TrustThresholds:
    """The five limits, gathered from the configs that already enforce them.

    **A container, not a source.** Every value is copied in from
    `StalenessConfig` or `SuppressionConfig` at the call site and nothing here
    carries a default — `from_configs` is the only way to build one, so there
    is no path by which this becomes a second place a limit is written down.

    It exists because threading five loose keyword arguments through four
    serialisation functions is how one of them silently gets the wrong value.
    """

    max_odds_age_s: int
    max_kalshi_quote_age_s: int
    min_book_count: int
    max_market_width: float
    min_depth_contracts: float

    @classmethod
    def from_configs(cls, staleness, suppression) -> "TrustThresholds":
        return cls(
            max_odds_age_s=staleness.max_odds_age_s,
            max_kalshi_quote_age_s=staleness.max_kalshi_quote_age_s,
            min_book_count=suppression.min_book_count,
            max_market_width=suppression.max_market_width,
            min_depth_contracts=suppression.min_depth_contracts,
        )


@dataclass(frozen=True)
class TrustCheck:
    """One criterion, its state, and the words that say why.

    Deliberately NOT `suppression.Check`, which is two-state and whose
    `passed=False` means *refuse this row*. Here a failure means *this is worth
    seeing before you act*, and the third state has no counterpart there. Two
    similar shapes with different meanings is worse than two shapes.
    """

    name: str
    state: TrustState
    detail: str


@dataclass(frozen=True)
class TrustScore:
    checks: tuple[TrustCheck, ...]

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.state == "pass")

    @property
    def known(self) -> int:
        """Checks that actually ran. The honest denominator."""
        return sum(1 for c in self.checks if c.state != "unknown")

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def unknown(self) -> int:
        return self.total - self.known

    @property
    def failures(self) -> tuple[TrustCheck, ...]:
        """Every failure, in declaration order -- never just the first.

        `SuppressionResult.reason` carries the reasoning: naming one failure
        hides the one that mattered more, and choosing WHICH to name would be
        the importance weight this module refuses to invent.
        """
        return tuple(c for c in self.checks if c.state == "fail")

    @property
    def unknowns(self) -> tuple[TrustCheck, ...]:
        return tuple(c for c in self.checks if c.state == "unknown")

    def as_payload(self) -> dict:
        """The wire shape. Counts and words -- never a bare number.

        `passed`, `known` and `total` all travel, because a screen that renders
        `passed/total` alone hides how many checks nobody ran, and a screen
        that renders `passed/known` alone hides that they exist. The three
        together are the only honest summary, and the caller is left to word
        it rather than being handed a phrase to trust.
        """
        return {
            "passed": self.passed,
            "known": self.known,
            "total": self.total,
            "checks": [
                {"name": c.name, "state": c.state, "detail": c.detail}
                for c in self.checks
            ],
        }


def _age_check(
    name: str, age_ms: Optional[int], limit_s: int, subject: str
) -> TrustCheck:
    """An age against a limit the desk already refuses on.

    `None` is `unknown`, never a pass: an unmeasurable age is exactly what
    `CandidateLeg.odds_age_now_ms` documents as refusing rather than passing as
    fresh, and this module must not be laxer than the ladder that feeds it.
    """
    if age_ms is None:
        return TrustCheck(name, "unknown", f"{subject} age could not be read")
    limit_ms = limit_s * 1000
    seconds = age_ms / 1000
    if age_ms <= limit_ms:
        return TrustCheck(name, "pass", f"{subject} {seconds:.0f}s old")
    return TrustCheck(
        name, "fail", f"{subject} {seconds:.0f}s old, limit {limit_s}s"
    )


def score_trust(
    *,
    max_odds_age_s: int,
    max_kalshi_quote_age_s: int,
    min_book_count: int,
    max_market_width: float,
    min_depth_contracts: float,
    odds_age_ms: Optional[int],
    quote_age_ms: Optional[int],
    book_count: Optional[int],
    market_width: Optional[float],
    method_spread_points: Optional[float],
    depth_at_ask: Optional[float],
    skeptic: str,
    suppressed_reason: Optional[str],
    scout: str,
    scout_flags: Sequence[dict],
) -> TrustScore:
    """Score one row. Every threshold arrives from its existing owner.

    The threshold arguments are required and have no defaults **on purpose**:
    a default here would be a second definition of a limit that already lives
    in `StalenessConfig`, `SuppressionConfig` or `ladder`, and the moment the
    real one moved this would keep scoring against the old number while every
    other surface refused against the new one.
    """
    checks: list[TrustCheck] = [
        _age_check("consensus_fresh", odds_age_ms, max_odds_age_s,
                   "sportsbook consensus"),
        _age_check("quote_fresh", quote_age_ms, max_kalshi_quote_age_s,
                   "Kalshi quote"),
    ]

    # --- how much evidence stands behind the number ------------------------
    if book_count is None:
        checks.append(TrustCheck("books", "unknown", "book count unreadable"))
    elif book_count >= min_book_count:
        checks.append(TrustCheck(
            "books", "pass", f"{book_count} books, need {min_book_count}"
        ))
    else:
        checks.append(TrustCheck(
            "books", "fail", f"{book_count} book(s), need {min_book_count}"
        ))

    # `None` FAILS rather than reads unknown, matching `suppression.py`: fewer
    # than two books contributed, so there was no second book to disagree with.
    # That is a measured absence of evidence, not an absence of measurement.
    if market_width is None:
        checks.append(TrustCheck(
            "books_agree", "fail",
            "no second book to disagree with, so the width is unmeasurable",
        ))
    elif market_width <= max_market_width:
        checks.append(TrustCheck(
            "books_agree", "pass",
            f"books disagree by {market_width * 100:.1f} pts",
        ))
    else:
        checks.append(TrustCheck(
            "books_agree", "fail",
            f"books disagree by {market_width * 100:.1f} pts, "
            f"limit {max_market_width * 100:.0f}",
        ))

    if method_spread_points is None:
        checks.append(TrustCheck(
            "methods_agree", "unknown",
            "fewer than two devig methods solved",
        ))
    elif method_spread_points <= AGREEMENT_SPREAD_POINTS:
        checks.append(TrustCheck(
            "methods_agree", "pass",
            f"four methods within {method_spread_points:.1f} pts",
        ))
    else:
        checks.append(TrustCheck(
            "methods_agree", "fail",
            f"four methods span {method_spread_points:.1f} pts, "
            f"over {AGREEMENT_SPREAD_POINTS:.0f}",
        ))

    # --- can you actually transact -----------------------------------------
    if depth_at_ask is None:
        checks.append(TrustCheck("depth", "unknown", "book depth unreadable"))
    elif depth_at_ask >= min_depth_contracts:
        checks.append(TrustCheck(
            "depth", "pass", f"{depth_at_ask:.0f} contracts at the ask"
        ))
    else:
        checks.append(TrustCheck(
            "depth", "fail",
            f"{depth_at_ask:.0f} at the ask, need {min_depth_contracts:.0f}",
        ))

    # --- what the other examiners said -------------------------------------
    #
    # `not_on_this_path` and `absent` are UNKNOWN, not pass. A spread rung the
    # skeptic never ran is not a spread rung that passed, and rendering it as
    # one is the flattering misreading `_serialise_leg` already refuses to make
    # in words.
    if skeptic == "checked" and not suppressed_reason:
        checks.append(TrustCheck("skeptic", "pass", "no checks raised"))
    elif skeptic == "checked":
        checks.append(TrustCheck("skeptic", "fail", suppressed_reason))
    elif skeptic == "not_on_this_path":
        checks.append(TrustCheck(
            "skeptic", "unknown", "the checks do not run on this path"
        ))
    else:
        checks.append(TrustCheck(
            "skeptic", "unknown", "the engine has not priced this market"
        ))

    # A scout flag is a thing to see before acting, which is a failure of this
    # score's question -- not a refusal of the bet. Joe's ruling: the Scout
    # gates eligibility and flags, and never moves the price.
    if scout == "briefed" and scout_flags:
        names = ", ".join(
            str(f.get("category")) for f in scout_flags if f.get("category")
        )
        checks.append(TrustCheck("scout", "fail", f"scout flags: {names}"))
    elif scout in ("briefed", "filed_nothing"):
        checks.append(TrustCheck("scout", "pass", "the scout desk saw nothing"))
    else:
        # absent / briefing / refused / failed -- nobody has a finished look.
        checks.append(TrustCheck("scout", "unknown", "no scout briefing"))

    return TrustScore(checks=tuple(checks))
