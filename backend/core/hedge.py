"""Hedging a parlay you already hold — the arithmetic, and only the arithmetic.

ADR 0077. This module answers one question and refuses the other one.

**Answerable: what does hedging lock in?** You hold a ticket that returns `W` if
every leg wins. One leg is still live and every other leg has already won. You
buy `n` contracts of the *opposite* side of that leg at the derived ask `q`. Both
branches are then known, exactly, from two observed numbers:

    the leg wins    W - S - C(n)
    the leg loses   n * $1 - S - C(n)          C(n) = n*q + fee

They are equal at `n = W` contracts, and the guaranteed profit is
`W - S - W*q - fee`. There is no probability anywhere in that sentence. It is
algebra on a price you can see and a payout you were told.

**Not answerable: is now the moment?** The hedge price is the market's own
number. Nothing in this repo beats it — `beta = -0.141` says the consensus
signal runs the wrong way (ADR 0034), and ADR 0037 established that our own
model's error exceeds its disagreement with Kalshi. So this module reports what
is available and never what is coming, and no caller may present a lock as a
recommendation to take it.

Why the live Kalshi price is the whole input, and no model is fitted
--------------------------------------------------------------------
A hedge needs two things: how likely the leg still is, and what the other side
costs. **The Kalshi ask is both.** "San Francisco lead by two in the bottom of
the sixth" is exactly why the Cincinnati contract is at 20c — the score, the
inning and the base state are already in the price, priced by people with more
information than this repo can lawfully obtain. And unlike a fitted win
probability, it is the number the hedge actually transacts at, so there is no
translation step to be wrong in.

That is also why no MLB game-state feed is read. ADR 0035 §2 authorises exactly
two schedule endpoints from MLBAM and says in terms that per-game timer polling
is forbidden. This module needs neither.

What this module does NOT establish
-----------------------------------
- **That taking a lock is correct.** A guaranteed $12 is guaranteed; whether it
  beats holding a ticket worth more in expectation is a preference about
  variance, and this module has no opinion.
- **That the guarantee is exact.** Every figure here charges the *entry* fee
  only. Whether Kalshi also charges at settlement is H4, and H4 is untested
  (ADR 0027) — so a locked figure is an **upper bound**, and callers must say
  so.
- **Anything about a ticket with more than one leg still live.** `derisk` is
  branch arithmetic and a notional value, not a lock. Hedging one of four live
  legs locks nothing at all.
- **That a leg is hedgeable at size.** Depth is bounded from the book and the
  bound is reported; nothing here models what happens above it.

On rule 1, and where it does *not* apply
----------------------------------------
CLAUDE.md rule 1 is that a large apparent edge is a bug until proven otherwise.
It is applied here to the **book** — a hedge ask that would let you buy both
sides for less than a dollar is a crossed or stale book, and is refused — and it
is deliberately **not** applied to the size of the lock relative to the stake.

That distinction is the whole point of the feature. A $5 ticket returning $333
with one leg left at an even-money hedge locks about $161, which is 32x the
stake and entirely real: it is what hedging a longshot parlay looks like. A
suppression rule keyed on lock-to-stake would silence exactly the case this
module exists for. The invariant that catches a genuine bug is the one that
cannot be true of any real book, and that is the crossed-book test below.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence, Union

from .correlation import CorrelationRefused, Leg, joint_probability_all
from .fees import calculate_fee
from .prices import PRICE_MAX, format_price, is_valid_price

#: A contract settles at $1.00, which is `PRICE_MAX` tenths of a cent. Money in
#: this module is integer tenths of a cent throughout (CLAUDE.md), so a $5 stake
#: is 5_000 and a $333.33 return is 333_330.
SETTLEMENT_TENTHS = PRICE_MAX

#: Refusal reasons. Constants rather than literals so the screen, the notifier
#: and the tests share one vocabulary and a typo cannot open a second bucket --
#: the defect `notify/alerts.py:FAILURE_KINDS` records having had for the life
#: of the project.
NO_ASK = "no_ask"
NO_DEPTH = "no_depth"
STALE_QUOTE = "stale_quote"
MARKET_CLOSED = "market_closed"
CROSSED_BOOK = "crossed_book"
UNREADABLE_TICKET = "unreadable_ticket"
FEE_UNREADABLE = "fee_unreadable"
NOT_A_LOCK = "not_a_lock"

REFUSAL_REASONS = (
    NO_ASK,
    NO_DEPTH,
    STALE_QUOTE,
    MARKET_CLOSED,
    CROSSED_BOOK,
    UNREADABLE_TICKET,
    FEE_UNREADABLE,
    NOT_A_LOCK,
)

#: A market the venue is done with cannot be hedged. Same tuple as
#: `parlays._TERMINAL_STATUSES`, restated rather than imported because
#: `backend/parlays.py` reaches the database and this module must not.
TERMINAL_STATUSES = frozenset({"closed", "settled", "finalized", "determined"})

#: The widest decimal odds a typed ticket may claim, and the narrowest.
#:
#: This is input validation, not a market opinion. `return_tenths` is typed by
#: hand, and the failure that matters is a decimal point: $333.33 entered as
#: $33,333 turns a $161 lock into a $16,000 one, and every number downstream
#: would be arithmetically correct. 10,000x is far above any real parlay -- the
#: six-leg card that prompted ADR 0070 was 66.8x -- and 1.01x is below any
#: ticket worth recording.
MIN_DECIMAL_ODDS = 1.01
MAX_DECIMAL_ODDS = 10_000.0


@dataclass(frozen=True)
class Refusal:
    """Why no number is being reported. Never a number with a caveat attached.

    `reason` is one of `REFUSAL_REASONS`, for branching; `detail` is the
    sentence a person reads. Both, because ADR 0050 rules that a suppression
    code gets a caption and never a translation -- the code stays the code.
    """

    reason: str
    detail: str

    def as_dict(self) -> dict:
        return {"reason": self.reason, "detail": self.detail}


@dataclass(frozen=True)
class HedgeQuote:
    """The book on the side you would BUY to hedge, as observed.

    `side` is the side of the hedge, not the side of the leg: a YES leg is
    hedged by buying NO. `ask_tenths` is the **derived** ask
    (`1000 - opposing bid`) and arrives already refused to `None` by
    `store.db.derive_yes_ask` / `derive_no_ask` when there is nothing resting.
    It is re-tested here anyway, because a producer's guarantee is not a
    guarantee about the next producer somebody writes.

    `leg_ask_tenths` is the derived ask on the leg's OWN side, carried only so
    the crossed-book test can run. It is not priced against and is not shown as
    a cost.
    """

    ticker: str
    side: str
    ask_tenths: Optional[int]
    depth_at_ask: Optional[float]
    observed_ms: Optional[int]
    status: Optional[str] = None
    leg_ask_tenths: Optional[int] = None

    def refusal(self, *, now_ms: int, max_quote_age_ms: int) -> Optional[Refusal]:
        """The first reason this book cannot price a hedge, or `None`.

        Ordered cheapest-and-most-fundamental first, so the sentence a person
        reads names the thing that is actually wrong rather than a downstream
        symptom of it.
        """
        if self.status is not None and self.status.lower() in TERMINAL_STATUSES:
            return Refusal(
                MARKET_CLOSED,
                f"{self.ticker} is {self.status} — the venue is done with it, "
                "so there is nothing to buy.",
            )
        if not is_valid_price(self.ask_tenths):
            return Refusal(
                NO_ASK,
                "Nothing is resting on that side — nobody is offering to sell "
                "you the hedge at any price right now.",
            )
        if self.depth_at_ask is None or self.depth_at_ask <= 0:
            return Refusal(
                NO_DEPTH,
                "There is a price but no size behind it, so the hedge could "
                "not be filled.",
            )
        if self.observed_ms is None:
            return Refusal(
                STALE_QUOTE,
                "This quote has no observation time, so its age cannot be "
                "measured.",
            )
        age_ms = now_ms - self.observed_ms
        if age_ms > max_quote_age_ms:
            return Refusal(
                STALE_QUOTE,
                f"The quote is {age_ms / 1000:.0f}s old, past the "
                f"{max_quote_age_ms / 1000:.0f}s limit.",
            )
        if self.leg_ask_tenths is not None and is_valid_price(self.leg_ask_tenths):
            if int(self.ask_tenths) + int(self.leg_ask_tenths) <= SETTLEMENT_TENTHS:
                # Both sides for a dollar or less is free money, which is not a
                # thing a real book offers. CLAUDE.md rule 1: a large apparent
                # edge is a bug until proven otherwise.
                return Refusal(
                    CROSSED_BOOK,
                    f"Both sides quote at "
                    f"{format_price(self.leg_ask_tenths)} + "
                    f"{format_price(self.ask_tenths)}, a dollar or less "
                    "together. That is not a book anyone could offer, so it is "
                    "being read as bad data rather than as free money.",
                )
        return None


@dataclass(frozen=True)
class Rung:
    """One hedge size, fully costed. Every field is integer tenths of a cent.

    `if_leg_wins` and `if_leg_loses` are net of the **sunk stake**, so they are
    the two numbers a person actually cares about: what the whole ticket, plus
    this hedge, will have made. `floor` is the smaller of the two — the amount
    that is true whichever way the leg goes.
    """

    contracts: int
    cost_tenths: int
    fee_tenths: int
    if_leg_wins_tenths: int
    if_leg_loses_tenths: int
    floor_tenths: int
    fillable: bool
    affordable: bool


@dataclass(frozen=True)
class Lock:
    """A hedge on the last live leg of a ticket whose other legs have all won.

    `equalising` is the rung where both branches pay the same — the textbook
    hedge. `best_available` is the rung with the highest floor that is both
    fillable at the observed depth and affordable at the caller's cap; it is
    `None` when no rung is both, which is a real and common state on a $100
    bankroll against a three-figure payout.
    """

    quote: HedgeQuote
    stake_tenths: int
    return_tenths: int
    equalising: Rung
    best_available: Optional[Rung]
    ladder: tuple[Rung, ...]
    depth_contracts: int
    affordable_contracts: int

    @property
    def is_guaranteed_profit(self) -> bool:
        """Whether the best rung you could actually fill locks a gain.

        Deliberately reads `best_available`, not `equalising`: a lock you cannot
        buy is not a lock, and this is the predicate the alert fires on.
        """
        return (
            self.best_available is not None
            and self.best_available.floor_tenths > 0
        )


def _fee_tenths(price_tenths: int, contracts: int) -> Optional[int]:
    """The entry fee, in integer tenths of a cent, rounded UP.

    `calculate_fee` returns dollars on a $0.0001 grid, which is a tenth of a
    tenth-of-a-cent, so the conversion loses precision. It is taken in the
    conservative direction — never understate what a hedge costs.

    **No `fee_multiplier`.** ADR 0058 confines the per-series multiplier to
    record-writing callers; this is decision-bearing, so it charges the flat
    0.070 and overstates on baseball by a known factor rather than risking an
    understatement anywhere.

    `None` propagates: an unreadable fee must never resolve to zero, because a
    zero fee on a free contract manufactures a lock out of nothing.
    """
    fee_dollars = calculate_fee(price_tenths, contracts)
    if fee_dollars is None:
        return None
    return int(math.ceil(fee_dollars * SETTLEMENT_TENTHS - 1e-9))


def _rung(
    contracts: int,
    *,
    ask_tenths: int,
    stake_tenths: int,
    return_tenths: int,
    depth_contracts: int,
    affordable_contracts: int,
) -> Optional[Rung]:
    """Cost and both branches at one size, or `None` if the fee is unreadable."""
    if contracts <= 0:
        return None
    fee = _fee_tenths(ask_tenths, contracts)
    if fee is None:
        return None
    cost = contracts * int(ask_tenths) + fee
    if_wins = return_tenths - stake_tenths - cost
    if_loses = contracts * SETTLEMENT_TENTHS - stake_tenths - cost
    return Rung(
        contracts=contracts,
        cost_tenths=cost,
        fee_tenths=fee,
        if_leg_wins_tenths=if_wins,
        if_leg_loses_tenths=if_loses,
        floor_tenths=min(if_wins, if_loses),
        fillable=contracts <= depth_contracts,
        affordable=contracts <= affordable_contracts,
    )


def ticket_refusal(stake_tenths: int, return_tenths: int) -> Optional[Refusal]:
    """Whether a typed ticket is arithmetically usable at all.

    Separated from `hedge_lock` so the same validation runs on the record path
    at entry time, where a typo can still be corrected, rather than only at
    alert time when the game is in the sixth inning.
    """
    if stake_tenths <= 0 or return_tenths <= 0:
        return Refusal(
            UNREADABLE_TICKET,
            "A ticket needs a stake and a return, both above zero.",
        )
    if return_tenths <= stake_tenths:
        return Refusal(
            UNREADABLE_TICKET,
            "The return is not above the stake, so this ticket cannot win "
            "anything. Check the figures.",
        )
    odds = return_tenths / stake_tenths
    if not MIN_DECIMAL_ODDS <= odds <= MAX_DECIMAL_ODDS:
        return Refusal(
            UNREADABLE_TICKET,
            f"That is {odds:,.1f}x the stake, outside the {MIN_DECIMAL_ODDS}x "
            f"to {MAX_DECIMAL_ODDS:,.0f}x range a real ticket falls in. A "
            "misplaced decimal point is the usual cause.",
        )
    return None


def hedge_lock(
    *,
    stake_tenths: int,
    return_tenths: int,
    quote: HedgeQuote,
    now_ms: int,
    max_quote_age_ms: int,
    affordable_contracts: int,
) -> Union[Lock, Refusal]:
    """What hedging the last live leg locks in, or why it cannot be priced.

    Every other leg must already have WON. The caller establishes that; this
    function has no way to check it and does not pretend to.

    `affordable_contracts` is the caller's own cap — bankroll, exposure, or a
    per-bet limit. It bounds `best_available` and nothing else: `equalising` is
    reported whether or not it can be paid for, because "the full hedge is $333
    and you have $100" is the useful sentence, and hiding the rung would leave
    no way to say it.

    Returns a `Refusal` rather than raising. A refusal is a normal outcome here
    — most of the time there is no resting size on the other side of a game in
    progress — and a caller that has to catch an exception to render an empty
    state gets that wrong once and shows a zero.
    """
    bad_ticket = ticket_refusal(stake_tenths, return_tenths)
    if bad_ticket is not None:
        return bad_ticket

    refusal = quote.refusal(now_ms=now_ms, max_quote_age_ms=max_quote_age_ms)
    if refusal is not None:
        return refusal

    ask = int(quote.ask_tenths)  # validated by `quote.refusal`
    depth_contracts = int(math.floor(quote.depth_at_ask))
    affordable = max(0, int(affordable_contracts))

    # The floor rises while every extra contract still adds settlement value
    # (`n * 1000 <= W`) and falls once it does not, because cost keeps climbing
    # against a payoff that has stopped. So the maximum over the integers is at
    # one of the two contract counts either side of `W / 1000`, and the two are
    # simply evaluated rather than reasoned about.
    exact = return_tenths / SETTLEMENT_TENTHS
    candidates = {max(1, int(math.floor(exact))), max(1, int(math.ceil(exact)))}
    equalising = max(
        (
            r
            for r in (
                _rung(
                    n,
                    ask_tenths=ask,
                    stake_tenths=stake_tenths,
                    return_tenths=return_tenths,
                    depth_contracts=depth_contracts,
                    affordable_contracts=affordable,
                )
                for n in sorted(candidates)
            )
            if r is not None
        ),
        key=lambda r: r.floor_tenths,
        default=None,
    )
    if equalising is None:
        # `calculate_fee` refuses an untradeable price, which `quote.refusal`
        # has already ruled out -- so this is unreachable today and is here
        # because the alternative to a refusal is a cost with no fee in it.
        # Exercised by monkeypatching the fee, which is the only way to reach
        # it and therefore the only way to know it works.
        return Refusal(
            FEE_UNREADABLE,
            "The fee for that hedge could not be computed, so no cost can be "
            "stated. Nothing here will price a hedge as though it were free.",
        )

    reachable = min(depth_contracts, affordable, equalising.contracts)
    ladder = _ladder(
        equalising.contracts,
        reachable=reachable,
        ask_tenths=ask,
        stake_tenths=stake_tenths,
        return_tenths=return_tenths,
        depth_contracts=depth_contracts,
        affordable_contracts=affordable,
    )
    best = max(
        (r for r in ladder if r.fillable and r.affordable),
        key=lambda r: r.floor_tenths,
        default=None,
    )
    return Lock(
        quote=quote,
        stake_tenths=stake_tenths,
        return_tenths=return_tenths,
        equalising=equalising,
        best_available=best,
        ladder=ladder,
        depth_contracts=depth_contracts,
        affordable_contracts=affordable,
    )


def _ladder(
    equalising_contracts: int,
    *,
    reachable: int,
    ask_tenths: int,
    stake_tenths: int,
    return_tenths: int,
    depth_contracts: int,
    affordable_contracts: int,
) -> tuple[Rung, ...]:
    """A handful of sizes, always including the full hedge and the best reachable.

    Quarter, half and three-quarter rungs exist because a partial hedge is the
    realistic move on a small bankroll, and a screen that offers only "all or
    nothing" hides the choice actually available.
    """
    sizes = {equalising_contracts}
    for fraction in (0.25, 0.5, 0.75):
        sizes.add(max(1, int(round(equalising_contracts * fraction))))
    if reachable > 0:
        sizes.add(reachable)
    rungs = [
        _rung(
            n,
            ask_tenths=ask_tenths,
            stake_tenths=stake_tenths,
            return_tenths=return_tenths,
            depth_contracts=depth_contracts,
            affordable_contracts=affordable_contracts,
        )
        for n in sorted(sizes)
    ]
    return tuple(r for r in rungs if r is not None)


@dataclass(frozen=True)
class Derisk:
    """A ticket with more than one leg still live. **This is not a lock.**

    `if_leg_wins_tenths` on each rung is what you have spent, not what you have
    made: the ticket is still alive on the other legs, so the branch has no
    settled value. It is reported as a cost against a live position, and the
    screen must say so.

    `notional_value_tenths` is `return * P(all remaining legs win)` at the
    venue's own **bid** prices — the conservative side, and the only side anyone
    would pay you. It is notional because a parlay is atomic: no exchange will
    buy the ticket off you leg by leg, so this is what it is worth on paper and
    not what it could be realised for.
    """

    quote: HedgeQuote
    stake_tenths: int
    return_tenths: int
    live_legs: int
    joint_probability: Optional[float]
    notional_value_tenths: Optional[int]
    joint_refusal: Optional[Refusal]
    ladder: tuple[Rung, ...]


def derisk(
    *,
    stake_tenths: int,
    return_tenths: int,
    quote: HedgeQuote,
    live_legs: Sequence[Leg],
    now_ms: int,
    max_quote_age_ms: int,
    affordable_contracts: int,
) -> Union[Derisk, Refusal]:
    """Branch costs and a notional value for a ticket with several legs live.

    No lock is computed and none exists. Hedging one of four live legs changes
    the shape of the distribution and guarantees nothing, and this function
    exists so that fact has somewhere honest to be displayed instead of being
    approximated by a lock figure that would be wrong.

    A same-fixture pair propagates as a `joint_refusal` rather than an
    exception: ADR 0012 §5 records that 0 of 344 same-game joints were ever
    observed two-sided, so this repo has no measured same-game correlation and
    will not invent one. The per-leg prices still render; only the joint is
    withheld.
    """
    bad_ticket = ticket_refusal(stake_tenths, return_tenths)
    if bad_ticket is not None:
        return bad_ticket

    refusal = quote.refusal(now_ms=now_ms, max_quote_age_ms=max_quote_age_ms)
    if refusal is not None:
        return refusal

    ask = int(quote.ask_tenths)
    depth_contracts = int(math.floor(quote.depth_at_ask))
    affordable = max(0, int(affordable_contracts))
    exact = return_tenths / SETTLEMENT_TENTHS
    full = max(1, int(round(exact)))
    ladder = _ladder(
        full,
        reachable=min(depth_contracts, affordable, full),
        ask_tenths=ask,
        stake_tenths=stake_tenths,
        return_tenths=return_tenths,
        depth_contracts=depth_contracts,
        affordable_contracts=affordable,
    )

    joint: Optional[float] = None
    joint_refusal: Optional[Refusal] = None
    notional: Optional[int] = None
    if not live_legs:
        # The caller could not build the leg set -- in practice because at
        # least one live leg has no readable price. Saying so is the whole
        # difference between "the chance is unknown" and a silently absent
        # number that reads as zero.
        joint_refusal = Refusal(
            NO_ASK,
            "At least one live leg has no readable price, so the chance this "
            "ticket still wins cannot be stated.",
        )
    else:
        try:
            joint = joint_probability_all(list(live_legs))
        except CorrelationRefused as exc:
            joint_refusal = Refusal(NOT_A_LOCK, str(exc))
        else:
            notional = int(round(return_tenths * joint))

    return Derisk(
        quote=quote,
        stake_tenths=stake_tenths,
        return_tenths=return_tenths,
        live_legs=len(live_legs),
        joint_probability=joint,
        notional_value_tenths=notional,
        joint_refusal=joint_refusal,
        ladder=ladder,
    )
