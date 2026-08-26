"""Build the parlay desk's cards from fresh consensus legs.

ADR 0070. The cards are a *betting-desk* feature (ADR 0062): a structured way
to buy the venue's own combination product with the fair joint probability in
view — not an edge claim. ADR 0038's closed hunt is untouched: nothing here
computes an edge, sizes a bet, or feeds the gate.

**One pool, six cuts.** Until 2026-08-26 this module built three cards that
were not three products: Safe was the 3 likeliest legs, Middle was Safe plus
one, Lottery was the first 6 of the same ranking, and `prefer_spreads` was the
only structural difference in the whole ladder. A `Recipe` now carries the cut
— which direction to rank, which legs are eligible, how many to take — so a
card is a policy over the pool rather than a length.

**No recipe ranks by the consensus-vs-Kalshi gap, and none may** (ADR 0071
§2.5): `beta = -0.141` means ranking by that gap puts the least trustworthy
rows on top. Every ordering here is by probability or by the clock.

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
- **That the "Agreed" cut is safer.** Four devig methods landing close together
  says the *method choice* did not move this leg. It says nothing about whether
  the books were right, and agreement among four transformations of one input
  is not four pieces of evidence.
- **That the "Longshot" cut is priced well.** It is the same pool ranked the
  other way; `p_conservative` is min-of-four, so an underdog's chance is
  understated by construction and the card reads longer than it is.
- **Same-game combinations.** Selection takes at most one leg per fixture, so
  `CorrelationRefused` is structurally unreachable — deliberately. A same-game
  parlay needs a measured correlation this repo does not have (ADR 0012 §5).

Pure and deterministic: no DB, no network, no wall clock. The caller supplies
`now_ms` and every candidate; two calls with the same inputs build the same
cards (the copula is seeded, and ties break on `(commence_ms,
kalshi_market_ticker)` in both ranking directions).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from backend.core.correlation import Leg, joint_probability_all

#: The four devig methods, in the order `fair_prices` stores them.
METHODS = ("multiplicative", "additive", "power", "shin")

#: How far apart the four devig methods may land, in percentage points, for a
#: leg to count as "agreed".
#:
#: CLAUDE.md rule 2 uses the worst of four methods for any money decision
#: precisely because the spread between them is 1–2 points — larger than the
#: fee advantage this project was built to hunt. Two points is therefore the
#: width at which method choice stops being the biggest thing in the number.
#: It is a **selection** rule, not a suppression: the conservative headline is
#: still min-of-four on every card.
AGREEMENT_SPREAD_POINTS = 2.0

#: The "Next 3 hours" horizon — the phone-useful cut, "what can I still bet
#: on". Measured from the caller's `now_ms` against the sportsbook's
#: `commence_ms` (Kalshi's runs three hours late and is never read here).
SOON_HORIZON_MS = 3 * 3_600_000


@dataclass(frozen=True)
class Recipe:
    """One cut of the candidate pool, and the words that describe it.

    `pool_words` is what the refusal counts, in the reader's language. A card
    filtered to games starting within three hours that says "needs 2 fresh
    games and the slate has 0" names the wrong predicate — the slate may be
    full of fresh games that all start tomorrow. A refusal that names a
    predicate it did not apply is the failure `tasks/lessons.md` records twice.
    """

    key: str
    title: str
    #: One line, rendered on the card. Six cards on one screen need to say
    #: which is which without the reader deriving it from the legs.
    what_it_is: str
    min_legs: int
    max_legs: int
    #: Rank least-likely-first (Longshot). The tie-break stays in the same
    #: direction, so determinism holds either way.
    longest_first: bool = False
    #: Within a game, take the most likely *spread* rung when one exists.
    prefer_spreads: bool = False
    #: Only games commencing within this long of `now_ms`.
    starts_within_ms: Optional[int] = None
    #: Only legs whose four devig methods land within this many points.
    max_method_spread: Optional[float] = None
    pool_words: str = "fresh games"


#: The registered cards. `key` is the identity written to `parlay_lookups` and
#: used in the Discord dedupe key, so a key is never reused or repurposed —
#: `lottery`'s *title* changed on 2026-08-26 when Longshot arrived and made
#: "Lottery" the wrong name for the six likeliest legs, but its key did not,
#: because the lookup record has to stay comparable across the rename.
#:
#: Safe may build one short (2 legs) when the slate is thin; Middle and the
#: long ladder are exact — a six-leg card of four legs is a different product
#: than the one the card names.
CARD_SHAPES: tuple[Recipe, ...] = (
    Recipe(
        key="safe",
        title="Safe",
        what_it_is="the 3 likeliest games on the slate",
        min_legs=2,
        max_legs=3,
    ),
    Recipe(
        key="middle",
        title="Middle",
        what_it_is="the 4 likeliest games on the slate",
        min_legs=4,
        max_legs=4,
    ),
    Recipe(
        key="lottery",
        title="Long ladder",
        what_it_is=(
            "six legs, taking a spread rung over a plain win where one exists"
        ),
        min_legs=6,
        max_legs=6,
        prefer_spreads=True,
    ),
    Recipe(
        key="longshot",
        title="Longshot",
        what_it_is=(
            "the 3 least likely games on the slate — a long price by "
            "construction, not a signal"
        ),
        min_legs=2,
        max_legs=3,
        longest_first=True,
    ),
    Recipe(
        key="soon",
        title="Next 3 hours",
        what_it_is="the 3 likeliest games starting within three hours",
        min_legs=2,
        max_legs=3,
        starts_within_ms=SOON_HORIZON_MS,
        pool_words="fresh games starting within three hours",
    ),
    Recipe(
        key="agreed",
        title="Agreed",
        what_it_is=(
            "the 3 likeliest games where all four devig methods land within "
            "2 points of each other"
        ),
        min_legs=2,
        max_legs=3,
        max_method_spread=AGREEMENT_SPREAD_POINTS,
        pool_words="fresh games whose four devig methods agree",
    ),
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
    """One card. Exactly one of `legs` / `not_built_reason`."""

    key: str
    title: str
    what_it_is: str
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


def _sort_key(leg: CandidateLeg, *, longest_first: bool = False) -> tuple:
    # Highest probability first; ties break on kickoff then ticker so two runs
    # over the same rows build the same cards. `longest_first` flips only the
    # probability — the tie-break keeps its direction, so a Longshot card is
    # deterministic on the same terms every other card is.
    p = leg.p_conservative if longest_first else -leg.p_conservative
    return (p, leg.commence_ms, leg.kalshi_market_ticker)


def _methods_agree(leg: CandidateLeg, *, within_points: float) -> bool:
    """Do all four devig methods land inside `within_points` of each other?

    **A missing method refuses, it does not agree.** Three methods clustered
    tightly with the fourth absent is not agreement among four — and this is
    the same rule `_joint` applies when it returns `None` for a method rather
    than dropping the leg from that method's product. Unreadable resolves to a
    refusal, never to a convenient value (`tasks/lessons.md`).
    """
    ps = [leg.p_by_method.get(method) for method in METHODS]
    if any(p is None or not 0.0 < p < 1.0 for p in ps):
        return False
    return (max(ps) - min(ps)) * 100.0 <= within_points


def _correlation_leg(leg: CandidateLeg, probability: float) -> Leg:
    return Leg(
        label=leg.kalshi_market_ticker,
        probability=probability,
        event_key=leg.odds_event_id,
        league=leg.league,
        commence_ms=leg.commence_ms,
    )


def _joint_key(selected: Sequence[CandidateLeg]) -> tuple:
    """Every field `_joint` reads, so equal keys mean an equal joint.

    Deliberately not the ticker alone. Two cards selecting "the same legs"
    have to be the same legs *as `_joint` sees them* for a cached result to be
    the same answer, and a ticker is an identity the caller supplies rather
    than one this module can check.
    """
    return tuple(
        (
            leg.kalshi_market_ticker,
            leg.odds_event_id,
            leg.league,
            leg.commence_ms,
            leg.p_conservative,
            tuple(leg.p_by_method.get(method) for method in METHODS),
        )
        for leg in selected
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
    candidates: Sequence[CandidateLeg],
    *,
    prefer_spreads: bool,
    longest_first: bool = False,
) -> list[CandidateLeg]:
    """At most one leg per fixture — the structural same-game guard.

    `prefer_spreads` is the long ladder's cousin-style preference: within a
    game, take the most likely *spread* rung when one exists (the favorite
    covering a small margin — a longer price than the plain win), else the
    best moneyline. Every other card takes the game's leading leg outright,
    where "leading" follows `longest_first`.
    """
    by_game: dict[str, list[CandidateLeg]] = {}
    for leg in candidates:
        by_game.setdefault(leg.odds_event_id, []).append(leg)

    def key(leg: CandidateLeg) -> tuple:
        return _sort_key(leg, longest_first=longest_first)

    chosen: list[CandidateLeg] = []
    for legs in by_game.values():
        legs = sorted(legs, key=key)
        if prefer_spreads:
            spreads = [leg for leg in legs if leg.market == "spreads"]
            chosen.append(spreads[0] if spreads else legs[0])
        else:
            chosen.append(legs[0])
    return sorted(chosen, key=key)


def _pool_for(
    recipe: Recipe, usable: Sequence[CandidateLeg], *, now_ms: int
) -> list[CandidateLeg]:
    """The recipe's eligible legs, ranked, one per fixture.

    Filters first, then the one-leg-per-game guard — so a game whose leading
    leg is ineligible can still contribute its next one, rather than dropping
    out entirely because the cut happened to remove its best side.
    """
    pool: Sequence[CandidateLeg] = usable
    if recipe.starts_within_ms is not None:
        horizon_ms = now_ms + recipe.starts_within_ms
        pool = [leg for leg in pool if leg.commence_ms <= horizon_ms]
    if recipe.max_method_spread is not None:
        pool = [
            leg
            for leg in pool
            if _methods_agree(leg, within_points=recipe.max_method_spread)
        ]
    return _best_per_game(
        pool,
        prefer_spreads=recipe.prefer_spreads,
        longest_first=recipe.longest_first,
    )


def build_ladder(
    candidates: Sequence[CandidateLeg],
    *,
    max_odds_age_ms: int,
    now_ms: int,
) -> Ladder:
    """One card per registered recipe, from the fresh pre-game candidates.

    The caller owns the pre-game cut (a leg whose game has started can never
    be part of a buyable combo) and passes only YES sides it resolved. This
    function owns freshness, the one-leg-per-game guard, and the cuts.

    `now_ms` is the caller's clock, for the recipes that filter on kickoff.
    Passed in rather than read, so two calls over the same inputs build the
    same cards — the property the whole module is written around.
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

    # `_joint` runs a 200,000-sample copula five times (the headline plus one
    # per devig method), and six recipes over one pool routinely select the
    # SAME legs -- "Next 3 hours" is "Safe" whenever the whole slate is soon,
    # and "Agreed" is "Safe" whenever the methods agree on the leaders. The
    # function is pure, so those cost one build rather than three.
    #
    # **A bound on the common case, not the worst one.** Six genuinely
    # distinct leg sets still pay for six; nothing here caps the work, it only
    # stops paying twice for an identical answer.
    joints: dict[tuple, JointEstimate] = {}

    cards: list[Card] = []
    for recipe in CARD_SHAPES:
        pool = _pool_for(recipe, usable, now_ms=now_ms)
        if len(pool) < recipe.min_legs:
            cards.append(
                Card(
                    key=recipe.key,
                    title=recipe.title,
                    what_it_is=recipe.what_it_is,
                    not_built_reason=(
                        f"needs {recipe.min_legs} {recipe.pool_words} and the "
                        f"slate has {len(pool)}"
                    ),
                )
            )
            continue
        selected = tuple(pool[:recipe.max_legs])
        memo = _joint_key(selected)
        joint = joints.get(memo)
        if joint is None:
            joint = _joint(selected)
            joints[memo] = joint
        cards.append(
            Card(
                key=recipe.key,
                title=recipe.title,
                what_it_is=recipe.what_it_is,
                legs=selected,
                joint=joint,
            )
        )

    return Ladder(cards=tuple(cards), excluded=excluded)
