"""Accepting an RFQ quote — the path that spends.

What these tests establish: nothing reaches the venue while the path is
unarmed; the price accepted is read from this desk's record and not from the
request; an already-accepted quote is refused rather than re-sent; an accept
whose response is lost is reported as an UNKNOWN and never retried; a 204 is
not treated as a fill; and the maker's non-confirmation is a stated outcome
rather than an error.

What they do not establish
--------------------------
- **Nothing about `accepted_side`.** These tests pin that we send whatever
  `ACCEPT_SIDE_FOR_BUYING_YES` says. Whether that constant is *right* is the
  open question the arming decision turns on: the semantics are documented
  only on Kalshi's FIX page, and on the quote captured 2026-09-17 the two
  readings differ by 9x on the opposite contract. A green suite here is not
  evidence about that, and must never be cited as if it were.
- **Nothing about fills.** No acceptance has ever reached the venue.
- **Nothing about what a non-confirmation looks like in reality.** Kalshi
  documents no terminal state for it; `cancelled` is the fake's guess as much
  as ours.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import backend.combo_rfq as combo_rfq
from backend.kalshi.rfq import ACCEPT_SIDE_FOR_BUYING_YES, QuoteAcceptRefused, accept_quote
from backend.parlays import LookupRefused
from backend.store import combo_rfqs as store

SCHEMA = Path(__file__).parent.parent / "backend" / "store" / "schema.sql"
RFQ = "rfq-1"
QUOTE = "q-1"


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA.read_text())
    store.record_rfq(
        c, rfq_id=RFQ, requested_ms=1_000, ticker="KXMVE-X",
        collection_ticker="KXMVECROSSCATEGORY-R",
        legs=[{"market_ticker": "M1", "side": "yes"}], exchange_index=1,
    )
    c.execute(
        """
        INSERT INTO combo_rfq_quotes (
            rfq_id, quote_id, captured_ms, maker_id,
            yes_ask_tenths, no_bid_tenths, contracts, status, created_ts
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (RFQ, QUOTE, 1_000, "maker", 593, 407, 9.0, "open", "ts"),
    )
    c.commit()
    yield c
    c.close()


class FakeApi:
    """Records what reached the venue, and what it answered."""

    def __init__(self, *, statuses=None, accept_raises=False):
        self.calls: list[tuple[str, str]] = []
        self._statuses = list(statuses or [])
        self._accept_raises = accept_raises

    async def request(self, method, path, *, params=None, json_body=None):
        self.calls.append((method, path))
        if method == "PUT":
            assert params == {"exchange_index": 1}, "accept must name the shard"
            self.sent_body = json_body
            if self._accept_raises:
                raise RuntimeError("connection reset")
            return {}
        if method == "GET":
            status = self._statuses.pop(0) if self._statuses else "accepted"
            return {"quotes": [{"id": QUOTE, "rfq_id": RFQ, "status": status}]}
        raise AssertionError(f"unexpected {method} {path}")


class TestNothingSpendsWhileUnarmed:
    def test_the_path_is_armed_and_that_was_a_decision(self):
        """**Armed 2026-09-17** (ADR 0165 Amendment 1, Joe's #61 answer (a)).

        This asserted `is True` until the probe settled what `accepted_side`
        means. It is inverted rather than deleted on purpose: the flag is the
        one line between a screen that shows prices and a screen that spends
        Joe's money, and a test that names it makes flipping it back a
        deliberate act rather than a silent one.
        """
        assert combo_rfq.RFQ_ACCEPTS_ARE_DRY_RUNS is False

    async def test_a_dry_run_is_still_honoured_when_asked_for(self):
        """The switch still works per-call, which is what the probe used."""
        assert "dry_run" in combo_rfq.accept_quote_for_joe.__code__.co_varnames

    async def test_a_dry_run_reaches_the_venue_not_at_all(self, conn):
        fake = FakeApi()
        result = await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000, api=fake,
            dry_run=True,
        )
        assert fake.calls == [], "a dry run must send nothing"
        assert result["dry_run"] is True
        assert result["filled"] is False
        assert "not armed" in result["words"]

    async def test_a_dry_run_still_records_the_intent(self, conn):
        """So an unarmed tap is visible in the record, not invisible."""
        await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000, api=FakeApi(),
            dry_run=True,
        )
        row = store.quote_row(conn, rfq_id=RFQ, quote_id=QUOTE)
        assert row["accepted_ms"] == 2_000
        assert row["accept_dry_run"] == 1
        assert row["expected_ask_tenths"] == 593


class TestThePriceComesFromTheRecord:
    async def test_the_accepted_price_is_the_one_that_was_shown(self, conn):
        """Not from the request, which carries no price at all (B = (ii)).

        The screen showed 59.3c because the maker bid 40.7c on NO. If the
        accept re-read the venue instead, a quote that moved between the two
        taps would be bought at a price Joe never saw.
        """
        result = await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000, api=FakeApi(),
            dry_run=True,
        )
        assert result["expected_ask_tenths"] == 593
        assert result["expected_ask_display"] == "59.3c per $1 contract"

    async def test_the_side_sent_is_the_one_for_buying_yes(self, conn):
        """Pins WHAT we send, not that it is correct — see the module note."""
        fake = FakeApi(statuses=["confirmed"])
        await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000, api=fake,
            dry_run=False,
        )
        assert fake.sent_body == {"accepted_side": ACCEPT_SIDE_FOR_BUYING_YES}

    async def test_a_quote_this_desk_never_captured_is_refused(self, conn):
        with pytest.raises(LookupRefused) as exc:
            await combo_rfq.accept_quote_for_joe(
                conn, rfq_id=RFQ, quote_id="never-seen", now_ms=2_000,
                api=FakeApi(), dry_run=True,
            )
        assert exc.value.status_code == 404


class TestAnAcceptIsNeverSentTwice:
    async def test_a_second_tap_is_refused_not_replayed(self, conn):
        """There is no idempotency key, so a retry is a second real trade.

        Kalshi assigns `client_order_id` after execution, unlike the order
        path where `OrderRequest` generates one up front. Nothing here can
        deduplicate, so nothing here may retry.
        """
        fake = FakeApi(statuses=["confirmed"])
        await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000, api=fake,
            dry_run=False,
        )
        before = len(fake.calls)
        with pytest.raises(LookupRefused) as exc:
            await combo_rfq.accept_quote_for_joe(
                conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=3_000, api=fake,
                dry_run=False,
            )
        assert exc.value.status_code == 409
        assert "second real trade" in exc.value.detail
        assert len(fake.calls) == before, "the second tap reached the venue"


class TestALostResponseIsAnUnknown:
    async def test_it_is_not_reported_as_a_failure(self, conn):
        """"It failed" and "we do not know" are different claims.

        The request may have reached Kalshi. Saying it failed would send Joe
        off to place the bet again.
        """
        fake = FakeApi(accept_raises=True)
        with pytest.raises(LookupRefused) as exc:
            await combo_rfq.accept_quote_for_joe(
                conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000, api=fake,
                dry_run=False,
            )
        assert "may still" in exc.value.detail
        assert "will not re-send" in exc.value.detail

    async def test_the_intent_survives_on_disk(self, conn):
        """The trail that makes the outcome recoverable by reading."""
        with pytest.raises(LookupRefused):
            await combo_rfq.accept_quote_for_joe(
                conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000,
                api=FakeApi(accept_raises=True), dry_run=False,
            )
        row = store.quote_row(conn, rfq_id=RFQ, quote_id=QUOTE)
        assert row["accepted_ms"] == 2_000
        assert row["accept_dry_run"] == 0
        assert row["outcome_status"] is None, (
            "an unobserved outcome must be NULL, never a guessed status"
        )


class TestTheOutcomeIsObservedNotAssumed:
    async def test_an_executed_quote_is_a_fill(self, conn):
        result = await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000,
            api=FakeApi(statuses=["executed"]), dry_run=False,
        )
        assert result["filled"] is True
        assert result["status"] == "executed"
        assert store.quote_row(conn, rfq_id=RFQ, quote_id=QUOTE)["outcome_status"] == "executed"

    async def test_a_CONFIRMED_quote_is_not_a_fill(self, conn, monkeypatch):
        """**Observed live on the first probe, 2026-09-17.**

        A quote went `accepted` -> `confirmed` in 32ms and then `cancelled`
        1.7s later, with no fill, no position change and no balance change.
        Confirmation is the maker agreeing; execution is a separate step with
        its own one-second timer and it can fail to happen afterwards.

        This test asserted the opposite until that probe ran. A screen built
        on it would have reported a completed trade that never completed.
        """
        monkeypatch.setattr(combo_rfq, "CONFIRM_WATCH_S", 0.05)
        monkeypatch.setattr(combo_rfq, "CONFIRM_POLL_S", 0.01)
        result = await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000,
            api=FakeApi(statuses=["confirmed"] * 20), dry_run=False,
        )
        assert result["filled"] is False, (
            "a confirmation was read as a fill; the venue can cancel after it"
        )
        assert "NOT yet known" in result["words"]

    async def test_a_cancelled_quote_is_not_a_fill_and_not_an_error(self, conn):
        """A maker has ~3s to stand behind a quote on a combination.

        Declining is normal. The words must not read as a fault at Joe's end.
        """
        result = await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000,
            api=FakeApi(statuses=["cancelled"]), dry_run=False,
        )
        assert result["filled"] is False
        assert "did not confirm" in result["words"]
        assert "nothing was bought" in result["words"]

    async def test_a_204_alone_is_never_a_fill(self, conn, monkeypatch):
        """The venue answers 204 on accept and the maker confirms afterwards.

        Reading that as success is the single most dangerous misreading on
        this path, so the watch is shortened here and the quote left sitting
        in `accepted` — the state that means "sent, not confirmed".
        """
        monkeypatch.setattr(combo_rfq, "CONFIRM_WATCH_S", 0.05)
        monkeypatch.setattr(combo_rfq, "CONFIRM_POLL_S", 0.01)
        result = await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000,
            api=FakeApi(statuses=["accepted"] * 20), dry_run=False,
        )
        assert result["filled"] is False
        assert result["status"] == "accepted"
        assert "NOT yet known" in result["words"]


class TestTheWireCall:
    async def test_an_unknown_side_is_refused_before_the_venue(self):
        fake = FakeApi()
        with pytest.raises(QuoteAcceptRefused):
            await accept_quote(
                fake, rfq_id=RFQ, quote_id=QUOTE, accepted_side="maybe",
                dry_run=False,
            )
        assert fake.calls == []

    async def test_it_uses_the_nested_path_not_the_deprecated_flat_one(self):
        """The flat `/communications/quotes/{id}/accept` is deprecated and
        documented as having worse rate limits."""
        fake = FakeApi()
        await accept_quote(
            fake, rfq_id=RFQ, quote_id=QUOTE, accepted_side="no", dry_run=False,
        )
        method, path = fake.calls[0]
        assert method == "PUT"
        assert path == f"/communications/rfqs/{RFQ}/quotes/{QUOTE}/accept"
