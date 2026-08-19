"""Factors beside a row, none of which is an edge.

The Board answers one question -- *did this clear the fee against a devigged
sharp consensus?* -- and the answer has been "no" on every row this instance has
ever written. ADR 0021 records that as a refutation of the consensus-only
strategy, and its §7.2 records the most plausible reason: the comparison is
anchored on `runner.SHARP_BOOKS`, so Kalshi is being tested against the only
references plausibly as sharp as Kalshi. A screen that shows only the output of
that one comparison cannot show anything else about a slate.

This module computes what the record already holds and has never rendered. Four
groups, and every one of them is a **fact already bought and stored** rather
than a new opinion:

- **Where Kalshi's price sits in the book distribution.** Bears directly on
  §7.2: if Kalshi is systematically inside the books rather than outside them,
  "no edge against consensus" is a statement about the instrument.
- **How Kalshi's own price has moved** since the slate window opened.
- **How far apart the books were** -- already on `fair_prices` and never shown.
- **How much could be got down** -- `volume_24h`, `open_interest`,
  `depth_at_ask`. `sharp-bettor` calls capacity the binding constraint on a
  winning bettor and this tool has never displayed it.

What this module does NOT do, and the prohibitions are the point
---------------------------------------------------------------
**It computes no composite.** No score, no rating, no weighted confidence. The
moment several factors are combined into one number, that number is a *model*
of which factors matter and by how much, and this project has measured none of
that. `CLAUDE.md` rule 1 is that a large apparent edge is a bug until proven
otherwise; a composite is a machine for manufacturing apparent edges out of
inputs nobody has scored. Facts need no pre-registration. Composites do.

**Nothing here reaches the money path.** No value computed in this module enters
`suggested_contracts`, `edge_tenths`, the suppression gauntlet, or
`POST /api/orders`. `engine.build_recommendation` does not import it and must
not: the order endpoint re-derives sizing and risk server-side, and a factor
that could move a size would need an ADR and a pre-registration first.

**None of it has been scored against an outcome.** Not one of these factors has
been tested for whether it predicts anything. They are displayed so that the
record accumulates them under a slate a human actually looked at, which is the
same argument that justified recording props before the fee question resolved:
record now, score when the calendar allows. Rule 3 stands -- the scoreboard is
closing-line value against Kalshi's own close, and none of this is that yet.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from typing import Optional, Sequence

from .core.devig import DevigError, devig
from .store.db import ask_for_side

logger = logging.getLogger(__name__)

#: How far back `kalshi_drift` looks for an earlier quote on the same ticker.
#: One hour: long enough that a pre-game line has plausibly moved, short enough
#: that the comparison is to today's market rather than to yesterday's opener.
DRIFT_WINDOW_MS = 60 * 60 * 1000


@dataclass(frozen=True)
class BookDistribution:
    """Where Kalshi's ask sits among the books' own fair values.

    **The comparison is deliberately unfair to Kalshi, and that is the only way
    it is safe.** `kalshi_probability` is derived from the *ask* -- the price
    that would actually leave the account, per `CLAUDE.md`'s bucketing rule --
    so it sits above Kalshi's own mid by half the spread. The book figures are
    **devigged fair values**, with the vig removed. So a book will look cheaper
    than Kalshi by roughly half a spread even where the two agree exactly, and
    `books_below` is therefore an **over**-count of the books that genuinely
    think Kalshi is expensive.

    That direction is chosen. The reading this screen exists to support is
    "Kalshi may be the sharp side" (ADR 0021 §7.2), and a bias that makes Kalshi
    look *worse* cannot manufacture that reading.

    `None` fields mean "could not be measured", never zero. A fixture with no
    stored book prices and a fixture where every book was unusable are both
    real states and neither is "no books disagreed".
    """

    #: Kalshi's derived ask for the row's side, as a probability.
    kalshi_probability: float
    #: Per-book conservative (worst-of-four) fair probability for the same
    #: outcome, sorted ascending. Empty when nothing was usable.
    book_probabilities: tuple[float, ...]
    #: Books whose fair value is BELOW what Kalshi charges -- i.e. books that
    #: price this outcome cheaper than Kalshi's ask. See the bias note above.
    books_below: int
    #: Books that could not be devigged (did not quote every outcome, or quoted
    #: a price the devig refuses). Reported rather than dropped: a distribution
    #: over 2 of 21 books is a different object from one over 21.
    books_unusable: int

    @property
    def book_count(self) -> int:
        return len(self.book_probabilities)

    @property
    def median_book_probability(self) -> Optional[float]:
        if not self.book_probabilities:
            return None
        return statistics.median(self.book_probabilities)

    @property
    def percentile(self) -> Optional[float]:
        """Fraction of usable books priced below Kalshi's ask, 0.0-1.0.

        `None` on an empty distribution rather than 0.0. A percentile of zero
        would read as "Kalshi is the cheapest venue here", which is precisely
        the flattering misreading of a measurement that did not happen.
        """
        if not self.book_probabilities:
            return None
        return self.books_below / len(self.book_probabilities)

    def as_dict(self) -> dict:
        return {
            "kalshi_probability": self.kalshi_probability,
            "book_count": self.book_count,
            "books_below": self.books_below,
            "books_unusable": self.books_unusable,
            "median_book_probability": self.median_book_probability,
            "min_book_probability": (
                self.book_probabilities[0] if self.book_probabilities else None
            ),
            "max_book_probability": (
                self.book_probabilities[-1] if self.book_probabilities else None
            ),
            "percentile": self.percentile,
        }


def book_distribution(
    *,
    outcomes: Sequence[str],
    quotes_by_book: dict[str, Sequence[float]],
    outcome_name: str,
    kalshi_ask_tenths: int,
    already_dropped: int = 0,
) -> Optional[BookDistribution]:
    """Devig every book separately and place Kalshi's ask among the results.

    **Every book is devigged on its own before anything is compared**, which is
    the same order `consensus_devig` uses and for the same reason: books carry
    different margins, so comparing raw prices would rank books by how much vig
    they charge rather than by what they think.

    **The worst of the four methods is taken per book**, matching `CLAUDE.md`
    rule 2 and the money path's `p_conservative`. Using the mean of the four
    here while the edge uses the minimum would put two different fair values on
    one screen under one word.

    Unlike `consensus_devig` this applies **no sharp-book anchoring**. That is
    the entire point: the anchoring is what ADR 0021 §7.2 says may have made the
    result a tautology, so the distribution this screen shows is over *every*
    usable book, and a reader can see how the anchored consensus sits inside it.

    `already_dropped` is books the caller removed before this was called.
    `runner.book_quotes_for_event` drops any book that did not quote every
    outcome, so without this the unusable count would report only the failures
    that happened *here* and read as a clean distribution over every book the
    fixture had. Two filters on one quantity, and the earlier one is silent --
    the shape `tasks/lessons.md` names as *two limits on one quantity, and the
    tighter one wins in silence*.

    Returns `None` when the outcome is not one this market quotes -- a caller
    must not receive a distribution computed for the other team.
    """
    if outcome_name not in outcomes:
        return None
    index = list(outcomes).index(outcome_name)

    probabilities: list[float] = []
    unusable = 0
    for book, odds in quotes_by_book.items():
        try:
            result = devig(outcomes, odds)
        except DevigError as exc:
            # A book that did not quote every leg is an ordinary operating
            # state, not a failure of the fixture. Counted, never silent.
            logger.debug("slate: skipping %s: %s", book, exc)
            unusable += 1
            continue
        methods = result.all_methods()
        probabilities.append(min(m[index] for m in methods.values()))

    probabilities.sort()
    kalshi_probability = kalshi_ask_tenths / 1000.0
    return BookDistribution(
        kalshi_probability=kalshi_probability,
        book_probabilities=tuple(probabilities),
        books_below=sum(1 for p in probabilities if p < kalshi_probability),
        books_unusable=unusable + already_dropped,
    )


def kalshi_drift(
    conn,
    ticker: str,
    side: str,
    *,
    now_ms: int,
    window_ms: int = DRIFT_WINDOW_MS,
) -> Optional[int]:
    """Change in the derived ask for `side` over `window_ms`, in tenths.

    Positive means the price you would pay has **risen**.

    **Read off `kalshi_quotes`, which is a real time series**, unlike the book
    side. Every production reader of this table collapses it to one instant with
    `ORDER BY observed_ms DESC LIMIT 1`; the history has been recorded since the
    table existed and has never been read back. Kalshi quotes arrive on the
    ~15-second quote cadence, so an hour is a genuine sequence of observations.

    **The book side deliberately has no counterpart to this.** A fixture is
    swept once or twice a day, so a "book line movement" computed from
    `odds_snapshots` would be a difference between two samples, which cannot
    distinguish a move from the absence of one. Finer resolution is the Odds API
    historical endpoint at 10 x markets x regions per call -- 60 credits against
    a 400/day budget. Not built, on arithmetic.

    `None` when there is no earlier quote in the window, or when either end is
    unreadable. Never 0, which would assert the price held steady.
    """
    since_ms = now_ms - window_ms
    rows = conn.execute(
        "SELECT observed_ms, yes_bid_tenths, no_bid_tenths FROM kalshi_quotes "
        "WHERE ticker = ? AND observed_ms >= ? "
        "ORDER BY observed_ms DESC",
        (ticker, since_ms),
    ).fetchall()
    # **The baseline is the quote that was standing when the window opened
    # (ADR 0055), and `confirmed_ms` is what makes that knowable.**
    #
    # Under a change log, a market that has not moved all hour has one row in
    # the window or none, so the old `len(rows) < 2` rule returned `None` --
    # blanking the column for exactly the markets whose drift is most
    # confidently zero.
    #
    # But a gap in the rows is ambiguous, and the ambiguity is the whole reason
    # this needs a second column. No row for an hour means either *the price
    # held* or *nobody was looking*, and those must not produce the same
    # answer: differencing across an outage would report a recorder gap as an
    # hour of movement. The pre-window row is a legitimate baseline only if it
    # was **still being confirmed** at the window edge.
    #
    # `COALESCE` for rows written before ADR 0055: their `confirmed_ms` is NULL
    # and `observed_ms` is the only thing known, which correctly disqualifies a
    # stale one.
    baseline = conn.execute(
        "SELECT observed_ms, yes_bid_tenths, no_bid_tenths FROM kalshi_quotes "
        "WHERE ticker = ? AND observed_ms < ? "
        "  AND COALESCE(confirmed_ms, observed_ms) >= ? "
        "ORDER BY observed_ms DESC LIMIT 1",
        (ticker, since_ms, since_ms),
    ).fetchone()
    if baseline is None:
        # Nothing was standing at the window edge that we know of. Two distinct
        # observations inside the window are then the most that can be claimed,
        # and one is not a series. This is the pre-ADR-0055 rule, kept for
        # exactly the case it was right about.
        if len(rows) < 2:
            return None
        baseline = rows[-1]
    elif not rows:
        # Confirmed across the window and never moved. That is a measured 0,
        # not an absent reading, and returning None here is what this change
        # exists to prevent.
        return 0 if ask_for_side(baseline, side) is not None else None

    latest = ask_for_side(rows[0], side)
    earliest = ask_for_side(baseline, side)
    if latest is None or earliest is None:
        # Unreadable resolves to None, never 0. A market with no bid on one
        # side has no derivable ask, and calling that "no movement" would put a
        # fabricated steadiness next to a real price.
        return None
    return latest - earliest
