"""On `/hedge`, what the public order book says a held combination could be
sold back for right now -- five states that never collapse into each other
(#95, the 2026-09-21 review of this ticket's own body, v3).

READ THIS FIRST -- the claim these tests must not make
--------------------------------------------------------
Resting combination YES bids HAVE been observed at the venue (2026-09-17,
`docs/measurements/2026-09-17-combinations-can-be-exited.md`: 5.10c /
38,709 deep and 0.32c / 24,900 deep). What does not exist is a committed
capture of one in this repo -- 0 of 20 in `combo_orderbooks.json`, 0 of 1 in
`combo_lookup_orderbook.json`, 0 of 17 read live on 2026-09-21. That is a
fact about this repo's disk, not the venue, and nothing here writes it into a
docstring, a test name or a word of copy (four such clauses have been
written and withdrawn already; do not add a fifth). The "bid resting" and
"unpriced interest" tests below therefore use HAND-BUILT inputs, labelled as
shapes rather than captures -- #106's precedent
(`tests/test_orderbook_levels_are_parsed_individually.py`) -- and the "nothing
resting" tests use the one committed fixture that exists,
`tests/fixtures/combo_orderbooks.json`.

What this establishes
----------------------
- `hedge.combo_book_state` returns exactly one of five states for a held
  combination: `bid` (a priced YES level rests), `empty` (a read succeeded
  and nothing rests), `unpriced_interest` (a level rests finer than a tenth
  of a cent, per #106), `unreadable` (the read or the parse failed), and
  "not applicable" -- `combo_book is None` with `combo_book_reason` naming
  why (`no_ticket` for a hand-recorded slip, `no_reader_wired` when
  `build_payload` was called with `read_combo_book=None`, which is every
  caller until #128).
- A read failure is never reported as "nothing resting" (review D1) -- it is
  the `unreadable` state, distinct on the WIRE FIELD, not merely in rendered
  text.
- The absent-bid states never carry a `0` where `price_display` should be
  `None` (house rule, CLAUDE.md: "unreadable resolves to `None`, never `0`";
  `format_price(0)` legitimately renders `"0c"` for a settled market, so a
  `0` here would be indistinguishable from a real price).
- A level finer than a tenth of a cent (`"0.0038"`) is never rounded into a
  4-tenths bid -- it is `unpriced_interest`, per the parser `#106` shipped.
- `HedgePositions.tsx` renders all five states in words, through
  `frontend/src/lib/comboBookGloss.ts`, and never renders the literal text
  `"0c"` anywhere in the component.

What this does not establish
-----------------------------
- That any committed capture carries a resting combination bid. See above.
- Anything about the RFQ path (`POST /api/parlays/rfq*`) -- out of scope by
  the ticket body (D2, critical): nothing on `/hedge` may fire one.
- That `read_combo_book` is wired to anything live. It is `None` on every
  caller in this tree; wiring it is #128.
- Anything about how often each state occurs at the venue. Zero rate claims
  are made or implied anywhere in this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend import hedge
from backend.kalshi.rest import MalformedOrderbookResponse
from backend.store import db

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "combo_orderbooks.json"

NOW_MS = 1_700_000_000_000
TICKER = "KXMVE-COMBOBOOK-TEST"

# The frontend source-assertion tests for this ticket (#95, done-when items 2
# and 3) live in `tests/test_the_hedge_card_names_the_fallback_reason.py`,
# extended rather than duplicated here -- that file already carries `CARD`,
# the `collapsed()` helper and the whole source-assertion pattern for
# `HedgePositions.tsx`; see its `TestTheComboBookStates` class.


def snapshot(yes, no):
    """A hand-built orderbook envelope's inner payload -- the shape
    `KalshiRestClient.orderbook` returns, not a capture. See module
    docstring."""
    return {"yes_dollars": yes, "no_dollars": no}


def reader(payload_or_exc):
    """A `read_combo_book` stand-in: returns a fixed payload, or raises a
    fixed exception, regardless of the ticker asked for."""

    async def _read(ticker: str):
        if isinstance(payload_or_exc, BaseException):
            raise payload_or_exc
        return payload_or_exc

    return _read


class TestNotApplicable:
    """Two designed causes, both leaving `combo_book` absent -- never a
    fabricated read of a ticket that has no ticker, and never a lie that a
    reader ran when this instance holds none."""

    async def test_a_hand_recorded_slip_has_no_ticket_to_read(self):
        async def never_called(ticker):
            raise AssertionError("no read should be attempted with no ticket")

        combo_book, reason = await hedge.combo_book_state(
            None, read_combo_book=never_called, now_ms=NOW_MS
        )
        assert combo_book is None
        assert reason == hedge.COMBO_BOOK_REASON_NO_TICKET

    async def test_no_reader_wired_reads_nothing(self):
        combo_book, reason = await hedge.combo_book_state(
            TICKER, read_combo_book=None, now_ms=NOW_MS
        )
        assert combo_book is None
        assert reason == hedge.COMBO_BOOK_REASON_NO_READER_WIRED

    async def test_the_two_causes_never_share_a_reason(self):
        """A reader that would prove which cause fired if either read were
        silently collapsed into the other."""
        no_ticket = await hedge.combo_book_state(
            None,
            read_combo_book=lambda t: (_ for _ in ()).throw(
                AssertionError("read attempted with no ticket")
            ),
            now_ms=NOW_MS,
        )
        no_reader = await hedge.combo_book_state(
            TICKER, read_combo_book=None, now_ms=NOW_MS
        )
        assert no_ticket[1] != no_reader[1]


class TestABidResting:
    """Hand-built shape, not a capture -- see module docstring. Same 5.10c /
    38,709 figures the 2026-09-17 measurement observed at the venue, because
    they are a real number to build a test around, not a claim this repo
    captured them."""

    LEVELS = [["0.0510", "38709.00"]]

    async def test_the_state_is_bid_with_price_and_size(self):
        read = reader(snapshot(self.LEVELS, []))
        combo_book, reason = await hedge.combo_book_state(
            TICKER, read_combo_book=read, now_ms=NOW_MS
        )
        assert reason is None
        assert combo_book["state"] == hedge.COMBO_BOOK_BID
        assert combo_book["price_display"] == "5.1c"
        assert combo_book["size"] == pytest.approx(38709.0)
        assert combo_book["observed_ms"] == NOW_MS

    async def test_a_bid_takes_priority_over_unpriced_dust_on_the_same_book(
        self,
    ):
        """A priced level and an unpriceable one can rest on the same side at
        once (#106's own reproduction). The state names the priced one --
        Joe can sell into that price; the dust is not actionable."""
        read = reader(
            snapshot([["0.0510", "38709.00"], ["0.0004", "1.00"]], [])
        )
        combo_book, _ = await hedge.combo_book_state(
            TICKER, read_combo_book=read, now_ms=NOW_MS
        )
        assert combo_book["state"] == hedge.COMBO_BOOK_BID


class TestNothingResting:
    """The committed fixture -- 16 of its 20 rows carry a live NO side and an
    empty YES side. Reading one through the same path a resting bid would
    take."""

    async def test_an_empty_yes_side_is_reported_as_nothing_resting(self):
        import json

        rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
        empty_yes = next(
            r for r in rows if r["orderbook_fp"]["yes_dollars"] == []
        )
        read = reader(empty_yes["orderbook_fp"])
        combo_book, reason = await hedge.combo_book_state(
            empty_yes["ticker"], read_combo_book=read, now_ms=NOW_MS
        )
        assert reason is None
        assert combo_book["state"] == hedge.COMBO_BOOK_EMPTY
        assert combo_book["price_display"] is None
        assert combo_book["size"] is None

    async def test_the_no_side_being_priced_does_not_make_the_yes_side_a_bid(
        self,
    ):
        """The fixture's own shape -- a live NO side alongside an empty YES
        side -- is the case a lazy `book.yes_bids or book.no_bids` check
        would misreport."""
        read = reader(snapshot([], [["0.8120", "369.00"]]))
        combo_book, _ = await hedge.combo_book_state(
            TICKER, read_combo_book=read, now_ms=NOW_MS
        )
        assert combo_book["state"] == hedge.COMBO_BOOK_EMPTY


class TestUnpricedInterest:
    """A level finer than a tenth of a cent -- #106's guard, exercised here
    through the combo-book path rather than `OrderBook` directly."""

    async def test_dust_alone_is_unpriced_interest_not_empty(self):
        read = reader(snapshot([["0.0004", "1.00"]], []))
        combo_book, reason = await hedge.combo_book_state(
            TICKER, read_combo_book=read, now_ms=NOW_MS
        )
        assert reason is None
        assert combo_book["state"] == hedge.COMBO_BOOK_UNPRICED_INTEREST
        assert combo_book["price_display"] is None

    async def test_a_centi_cent_price_is_never_rounded_into_a_bid(self):
        """M3. `dollars_to_tenths` (HALF_UP) would carry `"0.0038"` to 4
        tenths -- a bid at "0.4c" that no maker offered, 5.3% above the real
        one (`core/prices.dollars_to_tenths_exact`'s own docstring). The
        combo-book path must stay on the exact/refusing reader, not fall
        back to the rounding one or to `MarketBook.yes_bid_tenths`."""
        read = reader(snapshot([["0.0038", "10.00"]], []))
        combo_book, _ = await hedge.combo_book_state(
            TICKER, read_combo_book=read, now_ms=NOW_MS
        )
        assert combo_book["state"] == hedge.COMBO_BOOK_UNPRICED_INTEREST
        assert combo_book["price_display"] != "0.4c"


class TestTheReadFailed:
    """The critical defect the review named (D1): a failed read is a state
    of its own, asserted on the WIRE FIELD -- never inferred from rendered
    text, which a collapsed implementation could still get right."""

    async def test_a_malformed_envelope_is_unreadable_not_empty(self):
        read = reader(MalformedOrderbookResponse("no orderbook_fp key"))
        combo_book, reason = await hedge.combo_book_state(
            TICKER, read_combo_book=read, now_ms=NOW_MS
        )
        assert reason is None
        assert combo_book["state"] == hedge.COMBO_BOOK_UNREADABLE
        assert combo_book["price_display"] is None
        assert combo_book["size"] is None

    async def test_a_malformed_level_is_unreadable_not_empty(self):
        """`OrderBook.apply_snapshot` itself raises `MalformedBookMessage` on
        a level it cannot parse at all -- an unparseable quantity, not
        merely a price it must refuse as too fine."""
        read = reader(snapshot([["0.0510", "not-a-number"]], []))
        combo_book, reason = await hedge.combo_book_state(
            TICKER, read_combo_book=read, now_ms=NOW_MS
        )
        assert reason is None
        assert combo_book["state"] == hedge.COMBO_BOOK_UNREADABLE

    async def test_a_transport_failure_is_unreadable_not_empty(self):
        read = reader(RuntimeError("connection reset"))
        combo_book, reason = await hedge.combo_book_state(
            TICKER, read_combo_book=read, now_ms=NOW_MS
        )
        assert reason is None
        assert combo_book["state"] == hedge.COMBO_BOOK_UNREADABLE

    async def test_it_never_raises_into_the_caller(self):
        read = reader(RuntimeError("everything is down"))
        combo_book, reason = await hedge.combo_book_state(
            TICKER, read_combo_book=read, now_ms=NOW_MS
        )
        assert combo_book is not None  # did not propagate; produced a state


class TestNeverAZero:
    """The house rule stated for this surface specifically: `format_price(0)`
    legitimately renders `"0c"`, so an absent price must be `None`, never a
    `0` that a renderer could format into an indistinguishable "0c"."""

    async def test_empty_carries_no_price(self):
        read = reader(snapshot([], []))
        combo_book, _ = await hedge.combo_book_state(
            TICKER, read_combo_book=read, now_ms=NOW_MS
        )
        assert combo_book["price_display"] is None

    async def test_unreadable_carries_no_price(self):
        read = reader(RuntimeError("boom"))
        combo_book, _ = await hedge.combo_book_state(
            TICKER, read_combo_book=read, now_ms=NOW_MS
        )
        assert combo_book["price_display"] is None

    async def test_unpriced_interest_carries_no_price(self):
        read = reader(snapshot([["0.0004", "1.00"]], []))
        combo_book, _ = await hedge.combo_book_state(
            TICKER, read_combo_book=read, now_ms=NOW_MS
        )
        assert combo_book["price_display"] is None


class TestBuildPayloadThreadsItThrough:
    """`build_payload`'s per-position `combo_book`/`combo_book_reason`, the
    thing the screen actually reads. `read_combo_book=None` by default
    (#95's own decision, not this lane's) -- everything below is what every
    caller in this tree sees today."""

    @pytest.fixture()
    def conn(self, tmp_path):
        connection = db.init_db(tmp_path / "cockpit.db")
        yield connection
        connection.close()

    def _record(self, conn, **kwargs):
        return hedge.record_position(
            conn,
            now_ms=NOW_MS,
            source=kwargs.pop("source", "kalshi_combo"),
            label=kwargs.pop("label", "Combo book test"),
            stake_tenths=kwargs.pop("stake_tenths", 5_000),
            return_tenths=kwargs.pop("return_tenths", 100_000),
            legs=kwargs.pop(
                "legs",
                [{"ticker": "KXMLBGAME-X", "side": "yes", "label": "X to win"}],
            ),
            **kwargs,
        )

    async def _payload(self, conn, **kwargs):
        return await hedge.build_payload(
            conn,
            now_ms=NOW_MS,
            max_quote_age_ms=30_000,
            spendable_tenths=10_000_000,
            fetch_quote=lambda ticker, observed_ms: (_ for _ in ()).throw(
                RuntimeError("no leg quotes needed for this test")
            ),
            **kwargs,
        )

    async def test_with_no_reader_every_combo_is_not_applicable(self, conn):
        self._record(conn, combo_ticker=TICKER)
        payload = await self._payload(conn)
        row = payload["positions"][0]
        assert row["combo_book"] is None
        assert row["combo_book_reason"] == hedge.COMBO_BOOK_REASON_NO_READER_WIRED

    async def test_a_sportsbook_slip_is_not_applicable_for_lack_of_a_ticket(
        self, conn
    ):
        self._record(conn, source="sportsbook", combo_ticker=None)

        async def should_not_be_called(ticker):
            raise AssertionError("a sportsbook slip has no ticker to read")

        payload = await self._payload(conn, read_combo_book=should_not_be_called)
        row = payload["positions"][0]
        assert row["combo_book"] is None
        assert row["combo_book_reason"] == hedge.COMBO_BOOK_REASON_NO_TICKET

    async def test_a_wired_reader_produces_a_real_state(self, conn):
        self._record(conn, combo_ticker=TICKER)

        async def read(ticker):
            assert ticker == TICKER
            return snapshot([["0.0510", "38709.00"]], [])

        payload = await self._payload(conn, read_combo_book=read)
        row = payload["positions"][0]
        assert row["combo_book"]["state"] == hedge.COMBO_BOOK_BID
        assert row["combo_book_reason"] is None
