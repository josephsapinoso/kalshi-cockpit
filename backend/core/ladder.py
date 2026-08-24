"""Build the parlay desk's ladder of three cards from fresh consensus legs.

ADR 0070. The cards are a *betting-desk* feature (ADR 0062): a structured way
to buy the venue's own combination product with the fair joint probability in
view — not an edge claim. ADR 0038's closed hunt is untouched: nothing here
computes an edge, sizes a bet, or feeds the gate.

WHAT THIS MODULE DOES NOT ESTABLISH
-----------------------------------
- **That any card is worth buying.** The fair joint is what the sportsbook
  consensus implies the combination is worth; Kalshi's quoted cost (read only
  by the lookup path, off the minted market's order book) decides the hold,
  and the measured record says combos are enter-only with an unverified fee
  model. The card carries those sentences; this module carries the arithmetic.
- **The true joint probability.** Each leg's headline is `p_conservative` —
  the LOWEST of four devig methods for that side. Multiplying N conservative
  legs compounds that bias N-fold, which is why the four per-method joints are
  computed beside the headline: their spread is the uncertainty band the
  single number hides.
- **Same-game combinations.** Selection takes at most one leg per fixture, so
  `CorrelationRefused` is structurally unreachable — deliberately. A same-game
  parlay needs a measured correlation this repo does not have (ADR 0012 §5).

Pure and deterministic: no DB, no network, no wall clock. The caller supplies
`now` and every candidate; two calls with the same inputs build the same cards
(the copula is seeded, and ties break on `(commence_ms, kalshi_market_ticker)`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from backend.core.correlation import Leg, joint_probability_all

#: The four devig methods, in the order `fair_prices` stores them.
METHODS = ("multiplicative", "additive", "power", "shin")

#: key -> (title, leg count). Safe may build one short (2 legs) when the slate
#: is thin; Middle and Lottery are exact — a "lottery" of four legs is a
#: different product than the one the card names.
CARD_SHAPES: tuple[tuple[str, str, int, int], ...] = (
    ("safe", "Safe", 2, 3),
    ("middle", "Middle", 4, 4),
    ("lottery", "Lottery", 6, 6),
)


@dataclass(frozen=True)
class CandidateLeg:
    """One buyable YES side, with its consensus and its freshness.

    `odds_age_now_ms` is the leg's LIVE consensus age — `(now - computed_ms)
    + oldest_book_age_ms` — and `None` means the row predates v20 and its true
    age is unmeasurable. An unmeasurable age refuses (excluded, counted),
    never passes as fresh.
    """

    label: str                    # e.g. "St. Louis to win" / "St. Louis wins by over 1.5 runs"
    event_title: str
    kalshi_event_ticker: str
    kalshi_market_ticker: str
    odds_event_id: str
    league: str
    commence_ms: int
    market: str                   # "h2h" | "spreads"
    team: str
    point: Optional[float]        # the spread rung; None on moneyline
    p_conservative: float
    p_by_method: Mapping[str, Optional[float]]
    odds_age_now_ms: Optional[int]


@dataclass(frozen=True)
class JointEstimate:
    """The card's chance of paying, stated four-and-a-half ways.

    `conservative` is the headline (each leg at its min-of-four).
    `by_method` holds the same copula joint with every leg priced by one
    method; `None` where any leg lacks that method's number — absence, never
    substitution. `naive_product` is the zero-correlation product of the
    conservative legs; `independence_error_points` is how much the same-day
    correlation nudge moved the joint, in percentage points.
    """

    conservative: float
    by_method: dict[str, Optional[float]]
    naive_product: float
    independence_error_points: float

    @property
    def fair_decimal(self) -> float:
        return 1.0 / self.conservative

    @property
    def method_range(self) -> tuple[Optional[float], Optional[float]]:
        known = [v for v in self.by_method.values() if v is not None]
        if not known:
            return (None, None)
        return (min(known), max(known))


@dataclass(frozen=True)
class Card:
    """One rung of the ladder. Exactly one of `legs` / `not_built_reason`."""

    key: str
    title: str
    legs: tuple[CandidateLeg, ...] = ()
    joint: Optional[JointEstimate] = None
    not_built_reason: Optional[str] = None

    def __post_init__(self) -> None:
        built = bool(self.legs)
        if built == (self.not_built_reason is not None):
            raise ValueError(
                f"card '{self.key}': a card has legs or a reason, never both "
                f"and never neither"
            )
        if built and self.joint is None:
            raise ValueError(f"card '{self.key}': built cards carry a joint")


@dataclass(frozen=True)
class Ladder:
    cards: tuple[Card, ...]
    #: Games whose only rows were refused, by reason — served in words so an
    #: empty card never silently shrinks the slate.
    excluded: dict[str, int] = field(default_factory=dict)


def _fresh(leg: CandidateLeg, max_odds_age_ms: int) -> bool:
    return leg.odds_age_now_ms is not None and leg.odds_age_now_ms <= max_odds_age_ms


def _sort_key(leg: CandidateLeg) -> tuple:
    # Highest probability first; ties break on kickoff then ticker so two runs
    # over the same rows build the same cards.
    return (-leg.p_conservative, leg.commence_ms, leg.kalshi_market_ticker)


def _correlation_leg(leg: CandidateLeg, probability: float) -> Leg:
    return Leg(
        label=leg.kalshi_market_ticker,
        probability=probability,
        event_key=leg.odds_event_id,
        league=leg.league,
        commence_ms=leg.commence_ms,
    )


def _joint(selected: Sequence[CandidateLeg]) -> JointEstimate:
    conservative_legs = [_correlation_leg(c, c.p_conservative) for c in selected]
    conservative = (
        joint_probability_all(conservative_legs)
        if len(conservative_legs) > 1
        else conservative_legs[0].probability
    )

    by_method: dict[str, Optional[float]] = {}
    for method in METHODS:
        ps = [c.p_by_method.get(method) for c in selected]
        if any(p is None or not 0.0 < p < 1.0 for p in ps):
            by_method[method] = None
            continue
        method_legs = [
            _correlation_leg(c, p) for c, p in zip(selected, ps)
        ]
        by_method[method] = (
            joint_probability_all(method_legs)
            if len(method_legs) > 1
            else method_legs[0].probability
        )

    naive = 1.0
    for c in selected:
        naive *= c.p_conservative

    return JointEstimate(
        conservative=conservative,
        by_method=by_method,
        naive_product=naive,
        independence_error_points=(naive - conservative) * 100.0,
    )


def _best_per_game(
    candidates: Sequence[CandidateLeg], *, prefer_spreads: bool
) -> list[CandidateLeg]:
    """At most one leg per fixture — the structural same-game guard.

    `prefer_spreads` is the Lottery's cousin-style preference: within a game,
    take the most likely *spread* rung when one exists (the favorite covering
    a small margin — a longer price than the plain win), else the best
    moneyline. Safe/Middle take the game's most likely leg outright.
    """
    by_game: dict[str, list[CandidateLeg]] = {}
    for leg in candidates:
        by_game.setdefault(leg.odds_event_id, []).append(leg)

    chosen: list[CandidateLeg] = []
    for legs in by_game.values():
        legs = sorted(legs, key=_sort_key)
        if prefer_spreads:
            spreads = [leg for leg in legs if leg.market == "spreads"]
            chosen.append(spreads[0] if spreads else legs[0])
        else:
            chosen.append(legs[0])
    return sorted(chosen, key=_sort_key)


def build_ladder(
    candidates: Sequence[CandidateLeg],
    *,
    max_odds_age_ms: int,
) -> Ladder:
    """Three cards from the fresh, pre-game, buyable candidates.

    The caller owns the pre-game cut (a leg whose game has started can never
    be part of a buyable combo) and passes only YES sides it resolved. This
    function owns freshness, the one-leg-per-game guard, and the shapes.
    """
    excluded: dict[str, int] = {}

    usable: list[CandidateLeg] = []
    for leg in candidates:
        if leg.odds_age_now_ms is None:
            excluded["age_unmeasurable"] = excluded.get("age_unmeasurable", 0) + 1
        elif not _fresh(leg, max_odds_age_ms):
            excluded["stale_consensus"] = excluded.get("stale_consensus", 0) + 1
        elif not 0.0 < leg.p_conservative < 1.0:
            excluded["not_a_probability"] = excluded.get("not_a_probability", 0) + 1
        else:
            usable.append(leg)

    cards: list[Card] = []
    for key, title, min_legs, max_legs in CARD_SHAPES:
        pool = _best_per_game(usable, prefer_spreads=(key == "lottery"))
        if len(pool) < min_legs:
            cards.append(
                Card(
                    key=key,
                    title=title,
                    not_built_reason=(
                        f"needs {min_legs} fresh games and the slate has "
                        f"{len(pool)}"
                    ),
                )
            )
            continue
        selected = tuple(pool[:max_legs])
        cards.append(Card(key=key, title=title, legs=selected, joint=_joint(selected)))

    return Ladder(cards=tuple(cards), excluded=excluded)
