"""The combo quote says when it was read, against the desk's own threshold.

WHY THIS EXISTS
---------------
The desk has had a quote-staleness standard since ADR 0092:
`MAX_KALSHI_QUOTE_AGE_S` (30s, `backend/config.py`), rendered on the
single-market path as `quote_age_now_ms` / `price_is_current`
(`backend/api/serialise.py`).

The combination lookup shipped no clock at all -- and it is the only price
surface on this desk that has actually been transacted through. Worse, it is
rendered next to a fresh one: `<ManualTicket>` two elements below re-reads
Kalshi and shows a live ask, so the screen carried a stale verdict and a fresh
ask adjacent, with nothing saying which was which.

WHAT GOES STALE IS THE VERDICT, NOT THE PRICE PAID
--------------------------------------------------
`POST /api/manual-orders` re-fetches Kalshi at the tap and builds the order at
that live ask, refusing above the ceiling Joe types. So an old read here cannot
cause a surprising FILL. It causes a surprising REFUSAL, or a fill inside a
generous ceiling whose EV was never what the screen said. The fix therefore
RELABELS and never blocks -- disabling a buy control on age would be a new
ceiling on a hand bet, and ADR 0112 forbids it.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about how often a combo quote goes stale.** n = 1: one ticker went
  ask 302 -> 329 tenths, depth 2,928 -> 152, verdict "+0.3% EV. Rare" ->
  "-7.9% EV. Don't." in forty minutes. This is justified on cost asymmetry, not
  on frequency, and the copy claims no rate.
- **Nothing about the accuracy of the recorded fill price.** That is
  `docs/measurements/2026-09-10-preregistration-recorded-fill-vs-venue-charge.md`.
- **It does not test React.** There is no frontend test runner here, so the
  render half is asserted against source, as every other `.tsx` claim is.
"""

from __future__ import annotations

import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
PARLAYS = REPO / "backend" / "parlays.py"
ROUTER = REPO / "backend" / "api" / "routers" / "parlays.py"
SERIALISE = REPO / "backend" / "api" / "serialise.py"
API_TS = REPO / "frontend" / "src" / "lib" / "api.ts"
PRICE_TSX = REPO / "frontend" / "src" / "components" / "PriceOnKalshi.tsx"


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def quote_age_block() -> str:
    """Just the `QuoteAge` component, prose and all.

    The whole-file scan these started as was wrong in both directions: it
    matched this component's own docstring when looking for the buy control,
    and it matched unrelated copy elsewhere when looking for a rate claim.
    """
    source = read(PRICE_TSX)
    start = source.index("function QuoteAge(")
    return source[start : source.index("function Result(", start)]


def buy_control_jsx() -> str:
    """The rendered `<ManualTicket .../>`, not the prose that mentions it."""
    source = read(PRICE_TSX)
    start = source.index("<ManualTicket\n")
    return source[start : source.index("/>", start) + 2]


class TestTheStampTravelsWithThePrice:
    def test_the_priced_payload_carries_the_read_instant(self):
        """`now_ms` is the request's clock, and the book is read against it."""
        assert '"quoted_ms": now_ms,' in read(PARLAYS)

    def test_the_priced_payload_carries_the_threshold(self):
        """An age is not a verdict until something says what counts as current."""
        assert '"quote_max_age_ms": max_kalshi_quote_age_ms,' in read(PARLAYS)

    def test_the_threshold_is_passed_and_not_re_derived(self):
        """The SAME number `serialise.py` marks `price_is_current` against.

        Two surfaces each holding their own copy of a threshold is how they
        drift into calling different ages current -- the failure
        `backend/config.py`'s own cross-check exists to prevent one layer up.
        """
        assert (
            "max_kalshi_quote_age_ms=staleness.max_kalshi_quote_age_s * 1000"
            in read(ROUTER)
        )
        # And the single-market path still marks against that same field, so
        # this test fails if the standard itself is renamed out from under it.
        assert "staleness.max_kalshi_quote_age_s" in read(SERIALISE)

    def test_an_absent_threshold_marks_nothing(self):
        """Unreadable resolves to a refusal to claim, never to a default —
        so the parameter is optional and defaults to `None`, not to 30s."""
        assert "max_kalshi_quote_age_ms: Optional[int] = None," in read(PARLAYS)


class TestTheScreenShowsTheAgeAndMarksIt:
    def test_the_client_type_carries_both_fields(self):
        source = read(API_TS)
        assert "quoted_ms: number;" in source
        assert "quote_max_age_ms: number | null;" in source

    def test_the_age_ticks_rather_than_being_stamped_once(self):
        """An age rendered once stops being true while the reader looks at it,
        which is the exact failure this block exists to fix."""
        source = read(PRICE_TSX)
        assert "setInterval(tick, QUOTE_AGE_TICK_MS)" in source
        assert "clearInterval(timer)" in source, "the interval must be torn down"

    def test_a_null_threshold_marks_nothing(self):
        assert "maxAgeMs !== null && ageMs > maxAgeMs" in read(PRICE_TSX)

    def test_the_stale_words_say_the_verdict_moved_and_not_the_cost(self):
        """The copy must not imply he could be charged a stale price. He
        cannot -- the buy route re-reads Kalshi at the tap."""
        source = read(PRICE_TSX)
        assert "re-reads" in source and "charges the live price" in source
        assert "the verdict going out of" in source

    def test_the_stale_words_claim_no_frequency(self):
        """n = 1. The copy cites the one observation and does not generalise
        it into a rate — CLAUDE.md's measurement rules, and the mirror of the
        overstatement corrected on 2026-09-10.

        Scoped to `QuoteAge`, deliberately. The file's OTHER copy legitimately
        says "how often a bid is there is what Arm D measures", which is a
        statement that a rate is unknown rather than a claim about one.
        """
        block = quote_age_block()
        assert "One" in block and "combination went from" in block
        for forbidden in ("usually", "often", "typically", "most combinations"):
            assert forbidden not in block, (
                f"the stale-quote copy claims a rate ({forbidden!r}) that n = 1 "
                "cannot support"
            )


class TestItRelabelsAndNeverBlocks:
    def test_the_buy_control_is_not_gated_on_the_quote_age(self):
        """ADR 0112 removed all five ceilings on a hand bet, on Joe's word. A
        staleness check that disabled the buy would be a sixth."""
        # The buy renders unconditionally in the priced branch: no `stale &&`,
        # no `disabled=` on the element itself.
        buy = buy_control_jsx()
        assert "ticker={value.minted_market_ticker}" in buy, (
            "the buy control moved; re-scope this guard before trusting it"
        )
        assert "disabled" not in buy, (
            "the buy control grew a disabled prop — that is a new ceiling on a "
            "hand bet and ADR 0112 forbids it"
        )
        assert "stale" not in buy, "the buy control became conditional on staleness"


@pytest.mark.parametrize(
    "needle",
    [
        # The two facts the block is justified on, pinned in words so they
        # cannot be softened out of the comment while the code stays.
        "relabels and never blocks",
        "cannot produce a surprising",
    ],
)
def test_the_justification_stays_in_the_source(needle: str):
    assert needle in read(PRICE_TSX)
