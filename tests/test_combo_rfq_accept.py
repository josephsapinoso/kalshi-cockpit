"""Accepting an RFQ quote — the path that spends.

What these tests establish: nothing reaches the venue while the path is
unarmed; the price accepted is read from this desk's record and not from the
request; an already-accepted quote is refused rather than re-sent; an accept
whose response is lost is reported as an UNKNOWN and never retried; a 204 is
not treated as a fill; the maker's non-confirmation is a stated outcome
rather than an error; and the comments shipped on this path agree with the
arming flag.

What they do not establish
--------------------------
- **Nothing about `accepted_side`.** These tests pin that we send whatever
  `ACCEPT_SIDE_FOR_BUYING_YES` says. That constant was settled on 2026-09-17
  by a bounded $0.0043 probe, not here: the semantics are documented only on
  Kalshi's FIX page, and on the quote captured that day the two readings
  differed by 9x on the opposite contract. A green suite here is not evidence
  about it, and must never be cited as if it were.
  `docs/measurements/2026-09-17-accepted-side-names-the-makers-side.md`.
- **Nothing about fills.** This said "no acceptance has ever reached the
  venue" until 2026-09-18; two have, and the first went `accepted` ->
  `confirmed` -> `cancelled` with no fill. What a fill looks like is pinned
  by those measurements, not by any fake in this file.
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
import backend.hedge as hedge
from backend.kalshi.rfq import ACCEPT_SIDE_FOR_BUYING_YES, QuoteAcceptRefused, accept_quote
from backend.parlays import LookupRefused
from backend.store import combo_rfqs as store

class _FakeApiError(RuntimeError):
    """Stands in for `KalshiAPIError`: the refusal test reads `status_code`
    and `body`, which is exactly what the real class carries."""

    def __init__(self, status_code, body):
        super().__init__(f"HTTP {status_code}: {body}")
        self.status_code, self.body = status_code, body


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


class TestARefusalIsNotAnUnknown:
    """Joe hit `insufficient_balance` on 2026-09-17 and was told the
    acceptance might have gone through. It could not have.

    A 4xx carrying the venue's own reason is the exchange declining and
    nothing was placed. "It may still have reached Kalshi" belongs to a
    timeout or a dropped socket. Spending that warning on a clean refusal is
    how a safety message stops being read.
    """

    class _Refuses:
        def __init__(self, status, body):
            self.status, self.body, self.calls = status, body, []

        async def request(self, method, path, *, params=None, json_body=None):
            self.calls.append(method)
            if method == "PUT":
                raise _FakeApiError(self.status, self.body)
            return {"quotes": []}

    async def test_insufficient_balance_says_nothing_was_charged(self, conn):
        api = self._Refuses(400, '{"error":{"code":"insufficient_balance"}}')
        with pytest.raises(LookupRefused) as exc:
            await combo_rfq.accept_quote_for_joe(
                conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000, api=api,
                dry_run=False,
            )
        assert exc.value.status_code == 400
        assert "Nothing was placed and nothing was charged" in exc.value.detail
        assert "may still have reached" not in exc.value.detail
        assert "not enough money" in exc.value.detail

    async def test_an_expired_quote_says_ask_again(self, conn):
        api = self._Refuses(400, '{"error":{"code":"expired"}}')
        with pytest.raises(LookupRefused) as exc:
            await combo_rfq.accept_quote_for_joe(
                conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000, api=api,
                dry_run=False,
            )
        assert "Ask for a price again" in exc.value.detail
        assert "may still have reached" not in exc.value.detail

    async def test_a_timeout_IS_still_an_unknown(self, conn):
        """The cautious branch must survive: this is the case it is for."""
        class Times:
            calls = []
            async def request(self, method, path, *, params=None, json_body=None):
                raise RuntimeError("ReadTimeout")

        with pytest.raises(LookupRefused) as exc:
            await combo_rfq.accept_quote_for_joe(
                conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000, api=Times(),
                dry_run=False,
            )
        assert exc.value.status_code == 502
        assert "may still have reached Kalshi" in exc.value.detail

    async def test_a_5xx_is_an_unknown_not_a_refusal(self, conn):
        api = self._Refuses(503, "gateway")
        with pytest.raises(LookupRefused) as exc:
            await combo_rfq.accept_quote_for_joe(
                conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000, api=api,
                dry_run=False,
            )
        assert exc.value.status_code == 502
        assert "may still have reached Kalshi" in exc.value.detail
class TestTheShippedProseAgreesWithTheFlag:
    """A comment saying the money path is off, on a money path that is on.

    Both of these shipped, both were deployed, and both were still on the box
    a day after `RFQ_ACCEPTS_ARE_DRY_RUNS` was flipped to False: the accept
    route's docstring said "Disarmed until one measurement lands", and the
    RFQ component's module comment said "built, and switched off". This is
    the repo's named *justifications decay toward reassurance* pattern on the
    one surface where believing the comment costs money -- a reader of a
    comment here is deciding whether a tap spends.

    This does not try to read English. It pins the two exact sentences that
    state the arming state, keyed to the constant, so **flipping the flag
    without rewriting the prose fails here** -- in either direction.

    What it does not establish: nothing about any other comment in either
    file, and nothing about whether the sentences are *true*, only that they
    name the state the constant is actually in.
    """

    #: (path, phrase that is honest only while accepts are ARMED)
    ARMED_PROSE = (
        ("backend/api/routers/parlays.py", "**Armed since 2026-09-17**"),
        (
            "frontend/src/components/AskTheMarket.tsx",
            "**Taking a quote is built, and armed.**",
        ),
    )

    #: (path, phrase that is honest only while accepts are DRY RUNS)
    DISARMED_PROSE = (
        (
            "backend/api/routers/parlays.py",
            "**Disarmed until one measurement lands.**",
        ),
        (
            "frontend/src/components/AskTheMarket.tsx",
            "**Taking a quote is built, and switched off.**",
        ),
    )

    def _source(self, relative):
        path = Path(__file__).resolve().parents[1] / relative
        return path.read_bytes().decode("utf-8").replace("\r\n", "\n")

    def test_every_file_states_the_arming_state_the_constant_is_in(self):
        armed = not combo_rfq.RFQ_ACCEPTS_ARE_DRY_RUNS
        present, absent = (
            (self.ARMED_PROSE, self.DISARMED_PROSE)
            if armed
            else (self.DISARMED_PROSE, self.ARMED_PROSE)
        )
        for relative, phrase in present:
            assert phrase in self._source(relative), (
                f"{relative} no longer says {phrase!r}, but "
                f"RFQ_ACCEPTS_ARE_DRY_RUNS is {combo_rfq.RFQ_ACCEPTS_ARE_DRY_RUNS}. "
                "Flipping the flag means rewriting the prose on both surfaces."
            )
        for relative, phrase in absent:
            assert phrase not in self._source(relative), (
                f"{relative} still says {phrase!r}, which contradicts "
                f"RFQ_ACCEPTS_ARE_DRY_RUNS = {combo_rfq.RFQ_ACCEPTS_ARE_DRY_RUNS}."
            )

    def test_the_component_keeps_its_unarmed_branch(self):
        """The refusal copy is not dead code to delete when armed.

        It is what the screen renders if the flag is ever flipped back, and
        the armed state travels with the price rather than being compiled in.
        """
        source = self._source("frontend/src/components/AskTheMarket.tsx")
        assert "if (!armed)" in source
        assert "armed={value.accepts_are_armed}" in source
def _positions(conn):
    return conn.execute(
        "SELECT * FROM parlay_positions ORDER BY id"
    ).fetchall()


class TestAFillBecomesAWatchedPosition:
    """Issue #69. The newest armed door was the one the record could not see.

    Before this, `accept_quote_for_joe` wrote `combo_rfqs` rows and nothing
    else: a combination bought here produced no `parlay_positions` row, so
    `/hedge` could not watch it and `VenueCoverageBanner` reported the desk's
    own purchase back as a Kalshi holding nobody had recorded.

    What these do not establish
    ---------------------------
    - **Nothing about what Kalshi charged.** The stake written is the
      accepted quote's ask times its size, before fees. Whether an RFQ fills
      at its quoted price is measured at n = 1 and is not assumed here --
      which is exactly why the position resolves `as_recorded`.
    - **Nothing about a real venue.** The fake answers the statuses it is
      given; that `executed` is the only status Kalshi fills on is pinned by
      `QUOTE_FILLED_STATUSES` and the 2026-09-17 measurements, not here.
    """

    async def test_an_executed_accept_puts_the_combination_under_watch(self, conn):
        result = await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000,
            api=FakeApi(statuses=["executed"]), dry_run=False,
        )
        assert result["filled"] is True
        rows = _positions(conn)
        assert len(rows) == 1, "a filled accept must leave exactly one position"
        row = rows[0]
        assert result["position_id"] == row["id"]
        assert row["source"] == "kalshi_combo"
        assert row["combo_ticker"] == "KXMVE-X"
        assert row["status"] == "open"
        # 9 contracts at the 59.3c the screen showed, and $1.00 a contract back.
        assert row["stake_tenths"] == 5_337
        assert row["return_tenths"] == 9_000
        # Both halves of `/hedge`'s join key, from the one `now_ms`.
        assert row["placed_ms"] == 2_000

    async def test_the_legs_travel_with_it(self, conn):
        """A combination watched without all its legs is watched as if the
        missing ones could not lose."""
        await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000,
            api=FakeApi(statuses=["executed"]), dry_run=False,
        )
        legs = conn.execute(
            "SELECT * FROM parlay_position_legs ORDER BY leg_index"
        ).fetchall()
        assert [leg["ticker"] for leg in legs] == ["M1"]
        assert [leg["outcome"] for leg in legs] == ["pending"]

    async def test_a_maker_that_confirms_and_dies_leaves_no_position(self, conn):
        """`confirmed` is not a fill. The first live accept went
        `accepted` -> `confirmed` in 32ms and `cancelled` 1.7s later with no
        money moving; a position written on confirmation would have been a
        holding that never existed."""
        result = await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000,
            api=FakeApi(statuses=["confirmed", "cancelled"]), dry_run=False,
        )
        assert result["filled"] is False
        assert result["position_id"] is None
        assert _positions(conn) == []

    async def test_a_dry_run_leaves_no_position(self, conn):
        """Nothing was spent, so there is nothing to watch."""
        result = await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000,
            api=FakeApi(statuses=["executed"]), dry_run=True,
        )
        assert result["position_id"] is None
        assert _positions(conn) == []


class TestAFillThatCannotBeRecordedSaysSo:
    """`None` is never an error the caller may hide: it means the money moved
    and nothing is watching it."""

    async def _fill(self, conn):
        return await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000,
            api=FakeApi(statuses=["executed"]), dry_run=False,
        )

    async def test_an_unreadable_size_is_refused_not_guessed(self, conn):
        conn.execute("UPDATE combo_rfq_quotes SET contracts = NULL")
        conn.commit()
        result = await self._fill(conn)
        assert result["filled"] is True, "the trade still happened"
        assert result["position_id"] is None
        assert _positions(conn) == []

    async def test_a_size_that_cannot_be_a_holding_is_refused(self, conn):
        conn.execute("UPDATE combo_rfq_quotes SET contracts = 0")
        conn.commit()
        assert (await self._fill(conn))["position_id"] is None

    async def test_a_size_finer_than_a_tenth_is_refused_not_rounded(self, conn):
        """A settlement is a whole 1000 tenths a contract, so a size with more
        than two decimals cannot be reproduced in the unit the table stores.
        Same direction as `fractional_venue_fill_count` on the order path."""
        conn.execute("UPDATE combo_rfq_quotes SET contracts = 9.0005")
        conn.commit()
        assert (await self._fill(conn))["position_id"] is None

    async def test_unreadable_legs_are_refused(self, conn):
        conn.execute("UPDATE combo_rfqs SET selected_legs = 'not json'")
        conn.commit()
        assert (await self._fill(conn))["position_id"] is None

    async def test_the_trade_survives_a_bookkeeping_failure(self, conn):
        """The money is spent. A failure to write the books must not turn a
        completed purchase into an error that tells Joe nothing happened."""
        conn.execute("UPDATE combo_rfqs SET selected_legs = 'not json'")
        conn.commit()
        result = await self._fill(conn)
        assert result["filled"] is True
        assert result["status"] == "executed"

    async def test_the_trade_survives_a_raise_from_inside_the_writer(self, conn):
        """The branch above returns `None` politely; this one makes
        `record_position` *raise*, which is the case the broad `except` on
        `_record_accepted_position` exists for.

        A price of 1000 tenths is a dollar a contract, so the stake equals the
        return and `ticket_refusal` rejects the ticket as unwinnable. The
        trade still happened, and saying otherwise would send Joe looking for
        a position that is really there.
        """
        conn.execute("UPDATE combo_rfq_quotes SET yes_ask_tenths = 1000")
        conn.commit()
        result = await self._fill(conn)
        assert result["filled"] is True
        assert result["status"] == "executed"
        assert result["position_id"] is None
        assert "not on the watch list" in result["words"]
        assert _positions(conn) == []

    async def test_the_words_tell_him_it_is_not_being_watched(self, conn):
        """Silence would read exactly like a bet under watch."""
        conn.execute("UPDATE combo_rfq_quotes SET contracts = NULL")
        conn.commit()
        words = (await self._fill(conn))["words"]
        assert "not on the watch list" in words

    async def test_a_watched_fill_does_not_say_it_is_unwatched(self, conn):
        words = (await self._fill(conn))["words"]
        assert "not on the watch list" not in words


class TestTheHedgeScreenNamesWhereTheStakeCameFrom:
    """A position bought by RFQ has no `manual_orders` row **by
    construction**, and its join key is formed -- so without a reason of its
    own it would report `no_order_row`, which ADR 0160 Amendment 2 defines as
    a bookkeeping gap. That is the same conflation issue #56 removed, on a
    second path."""

    async def test_an_rfq_position_is_not_reported_as_a_gap(self, conn):
        await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000,
            api=FakeApi(statuses=["executed"]), dry_run=False,
        )
        rows = _positions(conn)
        bases = hedge.stake_bases(conn, rows)
        basis = bases[int(rows[0]["id"])]
        assert basis.reason == "rfq_accept"
        assert basis.basis == hedge.STAKE_BASIS_AS_RECORDED
        assert basis.stake_tenths == 5_337

    async def test_a_dry_run_acceptance_never_explains_a_stake(self, conn):
        """`accept_dry_run = 0` is part of the lookup: an unarmed tap records
        an intent, and an intent must not be able to name the source of money
        that was never spent."""
        await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000,
            api=FakeApi(statuses=["executed"]), dry_run=False,
        )
        conn.execute("UPDATE combo_rfq_quotes SET accept_dry_run = 1")
        conn.commit()
        rows = _positions(conn)
        basis = hedge.stake_bases(conn, rows)[int(rows[0]["id"])]
        assert basis.reason == "no_order_row"

    async def test_a_quote_that_never_executed_never_explains_a_stake(self, conn):
        await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000,
            api=FakeApi(statuses=["executed"]), dry_run=False,
        )
        conn.execute("UPDATE combo_rfq_quotes SET outcome_status = 'cancelled'")
        conn.commit()
        rows = _positions(conn)
        basis = hedge.stake_bases(conn, rows)[int(rows[0]["id"])]
        assert basis.reason == "no_order_row"

    async def test_a_position_with_no_acceptance_keeps_its_own_reason(self, conn):
        """The acceptance explains ONE position, not the screenful.

        `stake_bases` resolves every open position in one pass. A second
        combination on the same screen with no RFQ behind it must still read
        `no_order_row` -- a reason that spreads across the batch is how a
        stake gets explained by some other bet's fill, which is the failure
        `ambiguous_order_rows` exists for on the order side.
        """
        await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000,
            api=FakeApi(statuses=["executed"]), dry_run=False,
        )
        conn.execute(
            """
            INSERT INTO parlay_positions (
                created_ms, source, label, stake_tenths, return_tenths,
                placed_ms, status, combo_ticker
            ) VALUES (3000, 'kalshi_combo', 'other card', 500, 9000,
                      3000, 'open', 'KXMVE-OTHER')
            """
        )
        conn.commit()
        rows = _positions(conn)
        assert len(rows) == 2
        bases = hedge.stake_bases(conn, rows)
        reasons = {row["combo_ticker"]: bases[int(row["id"])].reason for row in rows}
        assert reasons == {"KXMVE-X": "rfq_accept", "KXMVE-OTHER": "no_order_row"}

    async def test_another_combinations_acceptance_does_not_answer_for_this_one(
        self, conn
    ):
        """The lookup is on `(ticker, accepted_ms)`, both halves. A quote on a
        different combination at the same instant must not explain this
        stake -- that is how a figure gets built on some other bet."""
        await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000,
            api=FakeApi(statuses=["executed"]), dry_run=False,
        )
        conn.execute("UPDATE combo_rfqs SET ticker = 'KXMVE-OTHER'")
        conn.commit()
        rows = _positions(conn)
        basis = hedge.stake_bases(conn, rows)[int(rows[0]["id"])]
        assert basis.reason == "no_order_row"
class TestTheStoredPriceFollowsTheQuote:
    """The accept reads its price from the DB, so the DB must hold the price
    the screen last showed.

    **The hazard, found by review on 2026-09-18.** `ask_market_to_price`
    holds the RFQ open by default and `create_rfq` reuses an open RFQ, so a
    second "Ask again" on the same combination returns the **same quote ids**
    -- and the venue's payload carries an `updated_ts` distinct from
    `created_ts`, i.e. a maker re-prices a quote in place. The store wrote
    `ON CONFLICT DO NOTHING`, so the screen would render the fresh price
    while the table -- the only copy `accept_quote_for_joe` reads -- kept the
    first. The accept call carries no price, so the venue charges its current
    number, and B = (ii) has no typed ceiling to bound the difference.

    What these do not establish: **that Kalshi does mutate a quote in place.**
    That is inferred from `updated_ts` on the captured payload and has not
    been measured live. These pin that the desk is safe either way.
    """

    def _requote(self, conn, *, yes_ask, no_bid, contracts=9.0,
                 yes_bid=None):
        store.record_quotes(
            conn,
            rfq_id=RFQ,
            quotes=[
                combo_rfq.RfqQuote(
                    quote_id=QUOTE,
                    rfq_id=RFQ,
                    maker_id="maker",
                    market_ticker="KXMVE-X",
                    yes_ask_tenths=yes_ask,
                    no_bid_tenths=no_bid,
                    yes_bid_tenths=yes_bid,
                    contracts=contracts,
                    status="open",
                    created_ts="ts",
                )
            ],
            captured_ms=5_000,
        )
        conn.commit()

    def test_a_requoted_price_replaces_the_stored_one(self, conn):
        assert store.quote_row(conn, rfq_id=RFQ, quote_id=QUOTE)["yes_ask_tenths"] == 593
        self._requote(conn, yes_ask=700, no_bid=300)
        row = store.quote_row(conn, rfq_id=RFQ, quote_id=QUOTE)
        assert row["yes_ask_tenths"] == 700, (
            "the accept would have been recorded at a price the screen no "
            "longer shows"
        )
        assert row["no_bid_tenths"] == 300
        assert row["captured_ms"] == 5_000

    def test_a_requoted_size_replaces_the_stored_one(self, conn):
        self._requote(conn, yes_ask=593, no_bid=407, contracts=4.5)
        assert store.quote_row(conn, rfq_id=RFQ, quote_id=QUOTE)["contracts"] == 4.5

    def test_one_quote_stays_one_row(self, conn):
        """The original reason for `DO NOTHING` still holds: a poll loop sees
        the same quote repeatedly and that is one quote, not many."""
        self._requote(conn, yes_ask=700, no_bid=300)
        self._requote(conn, yes_ask=700, no_bid=300)
        count = conn.execute(
            "SELECT COUNT(*) FROM combo_rfq_quotes WHERE rfq_id = ?", (RFQ,)
        ).fetchone()[0]
        assert count == 1

    async def test_an_accepted_quote_is_never_rewritten(self, conn):
        """The acceptance's own record is not a cache. A later poll that
        re-wrote it could move the price a trade was recorded at, after the
        trade."""
        await combo_rfq.accept_quote_for_joe(
            conn, rfq_id=RFQ, quote_id=QUOTE, now_ms=2_000,
            api=FakeApi(statuses=["executed"]), dry_run=False,
        )
        self._requote(conn, yes_ask=700, no_bid=300)
        row = store.quote_row(conn, rfq_id=RFQ, quote_id=QUOTE)
        assert row["yes_ask_tenths"] == 593
        assert row["accepted_ms"] == 2_000
        assert row["outcome_status"] == "executed"
