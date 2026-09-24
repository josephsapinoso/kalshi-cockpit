"""The RFQ path: the surface a combination is actually bought on.

What these tests do not establish
---------------------------------
- **Nothing about whether a quote fills.** No acceptance has ever been
  attempted by this repo. A quote is an offer with a 3-second maker
  confirmation window behind it, and every test here stops before that.
- **Nothing about how many makers answer.** The fixture is one RFQ at one
  moment. `parse_quotes` is being pinned, not the market.
- **Nothing about exit.** Every row in the fixture is a maker's NO bid, i.e.
  someone selling Joe the YES side. Whether a sell-side RFQ draws bids is
  untested and is the question CLAUDE.md's "combinations are enter-only"
  actually turns on.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.core.prices import complement
from backend.combo_rfq import _words
from backend.kalshi.rfq import RfqRefused, create_rfq, open_rfq_for, parse_quotes


class _Err(RuntimeError):
    """Stands in for `KalshiAPIError`: carries `status_code` and `body`."""

    def __init__(self, status_code, body):
        super().__init__(f"HTTP {status_code}: {body}")
        self.status_code, self.body = status_code, body

FIXTURE = Path(__file__).parent / "fixtures" / "combo_rfq_quotes.json"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text())


class TestTheCapturedQuotes:
    """Pinned against the real wire payload, never a hand-built one."""

    def test_both_captured_quotes_parse(self):
        quotes = parse_quotes(_payload()).quotes
        assert len(quotes) == 2

    def test_a_makers_no_bid_is_the_price_joe_pays_for_yes(self):
        """The derived-ask identity, which is the whole point of this module.

        The book showed nothing. The maker's NO bid of $0.4070 IS an offer to
        sell YES at $0.5930, and reading only `yes_dollars` is what made this
        desk tell Joe the combination could not be bought.
        """
        cheapest = parse_quotes(_payload()).quotes[0]
        assert cheapest.no_bid_tenths == 407
        assert cheapest.yes_ask_tenths == 593
        assert cheapest.yes_ask_tenths == complement(cheapest.no_bid_tenths)

    def test_quotes_come_back_cheapest_first(self):
        """3.80 cents separated the makers, so the order is worth money.

        **Fed in the WRONG order deliberately.** The captured payload happens
        to arrive cheapest-first already, so asserting against it unmodified
        passed with the sort deleted -- the mutation was run and the test
        stayed green. A guard that cannot fail is decoration.
        """
        payload = _payload()
        payload["quotes"].reverse()
        assert [float(r["no_bid_dollars"]) for r in payload["quotes"]] == [0.369, 0.407]

        asks = [q.yes_ask_tenths for q in parse_quotes(payload).quotes]
        assert asks == [593, 631], "expensive quote came back first"
        assert asks[-1] - asks[0] == 38  # 3.8 cents, the measured spread

    def test_the_quoted_size_survives(self):
        assert parse_quotes(_payload()).quotes[0].contracts == pytest.approx(8.19)

    def test_the_fixture_carries_no_account_identifier(self):
        """This repo is public and operator data never enters it.

        The capture's own `redaction` note claims every id is a placeholder;
        this refuses the claim going stale. A real Kalshi id is a uuid or 64
        hex chars, and a placeholder is neither.
        """
        raw = FIXTURE.read_text()
        for row in _payload()["quotes"]:
            for key in ("rfq_creator_id", "rfq_creator_user_id",
                        "creator_id", "id", "rfq_id"):
                value = row[key]
                assert "REDACTED" in value, f"{key} looks unredacted: {value!r}"
        assert "0cff6ab6" not in raw
        assert "be73160d" not in raw


class TestRowsThatMustNotBecomePrices:
    """Unreadable resolves to None and the row is dropped, never to a zero."""

    def _one(self, **overrides) -> dict:
        row = dict(_payload()["quotes"][0])
        row.update(overrides)
        return {"quotes": [row]}

    def test_a_zero_no_bid_is_not_an_offer_to_sell_yes_at_a_dollar(self):
        """`complement(0)` is 1000, a settled outcome, not a price."""
        assert parse_quotes(self._one(no_bid_dollars="0.0000")).quotes == ()

    def test_a_full_dollar_no_bid_is_refused_too(self):
        assert parse_quotes(self._one(no_bid_dollars="1.0000")).quotes == ()

    def test_an_unparseable_price_drops_the_row(self):
        assert parse_quotes(self._one(no_bid_dollars="not-a-price")).quotes == ()
        assert parse_quotes(self._one(no_bid_dollars=None)).quotes == ()

    def test_a_negative_price_drops_the_row(self):
        assert parse_quotes(self._one(no_bid_dollars="-0.4070")).quotes == ()

    def test_a_centi_cent_price_is_refused_rather_than_rounded(self):
        """A combination ticks in hundredths of a cent at the edges.

        `dollars_to_tenths("0.0055")` rounds half-up to 6 tenths. On the money
        path that invents a price the venue never offered, so the row is
        dropped instead. This is the one behaviour that would look like a bug
        if you only read the happy path.
        """
        assert parse_quotes(self._one(no_bid_dollars="0.0055")).quotes == ()
        # ...while an exactly-representable edge price still parses.
        kept = parse_quotes(self._one(no_bid_dollars="0.0050")).quotes
        assert len(kept) == 1 and kept[0].no_bid_tenths == 5

    def test_a_missing_size_is_none_and_keeps_the_quote(self):
        """The price is the thing being read; an unreadable size is not fatal."""
        quotes = parse_quotes(self._one(no_contracts_fp="?")).quotes
        assert len(quotes) == 1 and quotes[0].contracts is None


class TestTheRfqIdFilter:
    def test_quotes_for_another_rfq_are_not_ours(self):
        """`rfq_user_filter=self` returns every open RFQ's quotes, not one's.

        Without this filter a second RFQ open at the same moment would put
        another combination's price on this card.
        """
        payload = _payload()
        assert parse_quotes(payload, rfq_id="RFQ_REDACTED").quotes != ()
        assert parse_quotes(payload, rfq_id="some-other-rfq").quotes == ()


class TestCreateRefusesBeforeItReachesTheVenue:
    """A malformed request is refused here, not discovered as a 404."""

    async def test_naming_neither_size_nor_target_cost_is_refused(self):
        with pytest.raises(RfqRefused, match="exactly one"):
            await create_rfq(
                None, market_ticker="T", collection_ticker="C",
                legs=[{"market_ticker": "L", "side": "yes"}],
            )

    async def test_naming_both_is_refused(self):
        with pytest.raises(RfqRefused, match="exactly one"):
            await create_rfq(
                None, market_ticker="T", collection_ticker="C",
                legs=[{"market_ticker": "L", "side": "yes"}],
                target_cost_dollars="5.0000", contracts=3,
            )

    async def test_no_legs_is_refused(self):
        with pytest.raises(RfqRefused, match="at least one leg"):
            await create_rfq(
                None, market_ticker="T", collection_ticker="C",
                legs=[], target_cost_dollars="5.0000",
            )


class TestTheWriteRoutesToTheCombinationShard:
    """Without `exchange_index=1` the create returns 404 `not_found`.

    Measured 2026-09-17, and `rest.py:78-84` recorded the same failure for a
    shard-1 cancel on 2026-08-30. This is the guard that keeps the afternoon
    from being spent twice.
    """

    async def test_create_sends_the_shard_and_both_required_fields(self):
        seen = {}

        class FakeApi:
            async def request(self, method, path, *, params=None, json_body=None):
                seen.update(method=method, path=path, params=params, body=json_body)
                return {"id": "rfq-1"}

        handle = await create_rfq(
            FakeApi(),
            market_ticker="KXMVECROSSCATEGORY-SHARD1-XYZ",
            collection_ticker="KXMVECROSSCATEGORY-R",
            legs=[{"event_ticker": "E", "market_ticker": "M", "side": "yes"}],
            target_cost_dollars="5.0000",
        )

        assert handle.rfq_id == "rfq-1"
        assert seen["method"] == "POST"
        assert seen["params"] == {"exchange_index": 1}
        # Both were omitted on the first live attempt and it 404'd.
        assert seen["body"]["market_ticker"] == "KXMVECROSSCATEGORY-SHARD1-XYZ"
        assert seen["body"]["rest_remainder"] is False
        # The mve fields are ADDITIONAL to market_ticker, not instead of it.
        assert seen["body"]["mve_collection_ticker"] == "KXMVECROSSCATEGORY-R"
        assert len(seen["body"]["mve_selected_legs"]) == 1

    async def test_rest_remainder_is_never_true(self):
        """Joe pays the ask and does not make offers (ADR 0115).

        `rest_remainder: true` would leave a resting order behind after the
        RFQ executes -- exactly the offer-making he had removed.
        """
        seen = {}

        class FakeApi:
            async def request(self, method, path, *, params=None, json_body=None):
                seen.update(body=json_body)
                return {"id": "rfq-1"}

        await create_rfq(
            FakeApi(), market_ticker="T", collection_ticker="C",
            legs=[{"market_ticker": "L", "side": "yes"}], contracts=1,
        )
        assert seen["body"]["rest_remainder"] is False

    async def test_a_venue_refusal_carries_the_venues_words(self):
        class FakeApi:
            async def request(self, *a, **k):
                raise RuntimeError("HTTP 404 not_found")

        with pytest.raises(RfqRefused, match="not_found"):
            await create_rfq(
                FakeApi(), market_ticker="T", collection_ticker="C",
                legs=[{"market_ticker": "L", "side": "yes"}],
                target_cost_dollars="5.0000",
            )

    async def test_a_response_with_no_id_is_refused_not_guessed(self):
        class FakeApi:
            async def request(self, *a, **k):
                return {"ok": True}

        with pytest.raises(RfqRefused, match="no RFQ id"):
            await create_rfq(
                FakeApi(), market_ticker="T", collection_ticker="C",
                legs=[{"market_ticker": "L", "side": "yes"}],
                target_cost_dollars="5.0000",
            )


class TestAskingTwiceAboutTheSameCombination:
    """**The bug Joe hit on 2026-09-17, and a consequence of `hold_open`.**

    This desk holds RFQs open so a second tap can accept a quote. Kalshi
    allows one live RFQ per market per requester and answers a second create
    with `409 already_exists` -- so simply asking again about the same
    combination failed, which is exactly what a reader does when the first
    answer scrolls away.

    The recovery reuses the open RFQ rather than deleting and recreating,
    because deleting destroys the quotes it is holding and those may be the
    ones on screen with a confirm pending.
    """

    class _Api:
        def __init__(self, *, open_id="rfq-open", ticker="T"):
            self.open_id, self.ticker, self.calls = open_id, ticker, []

        async def request(self, method, path, *, params=None, json_body=None):
            self.calls.append((method, path))
            if method == "POST":
                raise _Err(409, '{"error":{"code":"already_exists"}}')
            if method == "GET":
                return {"rfqs": [
                    {"id": "rfq-dead", "market_ticker": self.ticker,
                     "status": "closed", "creator_user_id": "US"},
                    # A stranger's open row on the SAME market -- #147: the
                    # market-wide list carries these, blank creator_user_id,
                    # and it must never be picked as ours.
                    {"id": "someone-elses-open", "market_ticker": self.ticker,
                     "status": "open", "creator_user_id": ""},
                    {"id": self.open_id, "market_ticker": self.ticker,
                     "status": "open", "creator_user_id": "US"},
                    {"id": "someone-elses", "market_ticker": "OTHER",
                     "status": "open", "creator_user_id": "US"},
                ]}
            raise AssertionError(method)

    async def test_it_reuses_the_open_rfq_instead_of_refusing(self):
        api = self._Api()
        got = await create_rfq(
            api, market_ticker="T", collection_ticker="C",
            legs=[{"market_ticker": "L", "side": "yes"}],
            target_cost_dollars="5.0000",
        )
        assert got.rfq_id == "rfq-open"
        assert not any(m == "DELETE" for m, _ in api.calls), (
            "deleting would destroy the quotes the open RFQ is holding"
        )

    async def test_it_does_not_pick_a_closed_one_or_another_market(self):
        api = self._Api(open_id="rfq-open", ticker="T")
        assert (await create_rfq(
            api, market_ticker="T", collection_ticker="C",
            legs=[{"market_ticker": "L", "side": "yes"}],
            target_cost_dollars="5.0000",
        )).rfq_id == "rfq-open"

    async def test_a_409_with_nothing_open_still_refuses(self):
        """Recovery is for the case it was written for, not a blanket retry."""
        class Empty(self._Api):
            async def request(self, method, path, *, params=None, json_body=None):
                self.calls.append((method, path))
                if method == "POST":
                    raise _Err(409, '{"error":{"code":"already_exists"}}')
                return {"rfqs": []}

        with pytest.raises(RfqRefused, match="already_exists"):
            await create_rfq(
                Empty(), market_ticker="T", collection_ticker="C",
                legs=[{"market_ticker": "L", "side": "yes"}], contracts=1,
            )

    async def test_a_different_409_is_not_swallowed(self):
        class Other(self._Api):
            async def request(self, method, path, *, params=None, json_body=None):
                raise _Err(409, '{"error":{"code":"market_closed"}}')

        with pytest.raises(RfqRefused, match="market_closed"):
            await create_rfq(
                Other(), market_ticker="T", collection_ticker="C",
                legs=[{"market_ticker": "L", "side": "yes"}], contracts=1,
            )


class TestAnOversizedOpenRfqIsReplacedNotReused:
    """**Found by verifying the reuse fix on live, 2026-09-17.**

    Reuse alone was not enough. Joe's balance fell during the session while
    three RFQs created at the old flat $5.00 target stayed open, quoting 173
    contracts against $3.94. Handing one of those back is a price that is
    guaranteed to be refused on accept -- worse than the 409 the reuse was
    added to avoid, because it looks like it worked.

    Replacing costs the quotes it is holding, which is why it is not the
    default: those quotes are only worthless when the size is unpayable.
    """

    class _Api:
        def __init__(self, existing_target):
            self.existing_target, self.calls = existing_target, []
            self.posts = 0

        async def request(self, method, path, *, params=None, json_body=None):
            self.calls.append(method)
            if method == "POST":
                self.posts += 1
                if self.posts == 1:
                    raise _Err(409, '{"error":{"code":"already_exists"}}')
                return {"id": "rfq-fresh"}
            if method == "GET":
                return {"rfqs": [{
                    "id": "rfq-stale", "market_ticker": "T", "status": "open",
                    "target_cost_dollars": self.existing_target,
                    "creator_user_id": "US",
                }]}
            if method == "DELETE":
                return {}
            raise AssertionError(method)

    async def _ask(self, api, target):
        return await create_rfq(
            api, market_ticker="T", collection_ticker="C",
            legs=[{"market_ticker": "L", "side": "yes"}],
            target_cost_dollars=target,
        )

    async def test_an_oversized_one_is_withdrawn_and_replaced(self):
        api = self._Api("5.0000")
        got = await self._ask(api, "3.5424")
        assert got.rfq_id == "rfq-fresh", "the stale oversized RFQ was handed back"
        assert "DELETE" in api.calls
        assert api.posts == 2, "no fresh RFQ was created"

    async def test_one_within_budget_is_still_reused(self):
        """Replacing destroys quotes, so it stays the exception."""
        api = self._Api("2.0000")
        got = await self._ask(api, "3.5424")
        assert got.rfq_id == "rfq-stale"
        assert "DELETE" not in api.calls

    async def test_an_equal_target_counts_as_reusable(self):
        api = self._Api("3.5424")
        assert (await self._ask(api, "3.5424")).rfq_id == "rfq-stale"
        assert "DELETE" not in api.calls

    async def test_an_unreadable_target_is_replaced_not_trusted(self):
        """A fresh RFQ costs one call; a stale one costs a refused trade."""
        api = self._Api("not-a-number")
        assert (await self._ask(api, "3.5424")).rfq_id == "rfq-fresh"
        assert "DELETE" in api.calls

    @pytest.mark.parametrize("size", [{"contracts": 1}, {"contracts_fp": "2.01"}])
    async def test_a_size_based_ask_is_refused_neither_reused_nor_deleted(self, size):
        """#96 defect 4. This test used to be `test_a_size_based_ask_still_
        reuses` and pinned the defect: `_is_reusable` answered True for a
        `contracts=` ask, so a sell-side ask sized to a holding would have
        silently reused the open $5 BUY RFQ and read quotes priced for it.
        Deleting is no better -- a Take-it tab may be holding that RFQ open.
        So a size-based ask that meets `already_exists` is refused, and the
        refusal names the reason."""
        api = self._Api("5.0000")
        with pytest.raises(RfqRefused, match="already open"):
            await create_rfq(
                api, market_ticker="T", collection_ticker="C",
                legs=[{"market_ticker": "L", "side": "yes"}], **size,
            )
        assert "DELETE" not in api.calls
        assert api.posts == 1, "a second create was attempted"
class TestAPriceTooFineToShowIsNotNobodyQuoting(object):
    """Issue #73. Two different facts that used to render as one sentence.

    A maker who quotes in hundredths of a cent is refused -- rightly, because
    rounding would print a price the venue never offered on the path that
    spends. But the screen then said "Nobody quoted this combination", which
    is false and hides an action he can take: the price is readable in the
    Kalshi app.

    What these do not establish
    ---------------------------
    - Nothing about how often a combination is quoted in centi-cents. The
      one live trade this repo has made was at 0.40c, one tick inside that
      region, which is why the branch exists; that is an existence proof and
      not a rate.
    - Nothing about whether such a quote would have filled.
    """

    def _one(self, **overrides) -> dict:
        row = dict(_payload()["quotes"][0])
        row.update(overrides)
        return {"quotes": [row]}

    def test_the_refusal_is_reported_by_id_and_by_reason(self):
        read = parse_quotes(self._one(no_bid_dollars="0.0055"))
        assert read.quotes == ()
        assert read.refused_finer_than_tenths == frozenset({"QUOTE_A_REDACTED"})
        assert read.refused_unreadable == frozenset()

    def test_an_unreadable_price_is_NOT_reported_as_too_fine(self):
        """The distinction is the whole point: one sends him to the app.

        A garbage price is not a price too precise to print, and telling him
        to go and look for it would send him after something that is not
        there.
        """
        read = parse_quotes(self._one(no_bid_dollars="not-a-price"))
        assert read.refused_finer_than_tenths == frozenset()
        assert read.refused_unreadable == frozenset({"QUOTE_A_REDACTED"})

    def test_a_settled_outcome_is_unreadable_not_too_fine(self):
        """`complement(0)` is 1000. Not an offer at all, precise or otherwise."""
        read = parse_quotes(self._one(no_bid_dollars="0.0000"))
        assert read.refused_finer_than_tenths == frozenset()
        assert read.refused_unreadable == frozenset({"QUOTE_A_REDACTED"})

    def test_a_representable_price_reports_no_refusal(self):
        read = parse_quotes(self._one(no_bid_dollars="0.0050"))
        assert len(read.quotes) == 1
        assert read.refused_finer_than_tenths == frozenset()
        assert read.refused_unreadable == frozenset()


class TestTheWordsForAPriceTooFineToShow(object):
    """What the reader is told. The sentence is the deliverable here."""

    def test_the_words_do_not_say_nobody_quoted(self):
        said = _words([], book_ask=None, refused_too_fine=1)
        assert "Nobody quoted" not in said
        assert "1 maker(s) answered" in said

    def test_the_words_say_where_the_price_can_be_read(self):
        """The actionable half. Without it this is just a nicer refusal."""
        said = _words([], book_ask=None, refused_too_fine=2)
        assert "Kalshi app" in said
        assert "tenth of a cent" in said

    def test_the_words_still_say_nothing_was_bought(self):
        """Every empty branch must close the loop on the money."""
        said = _words([], book_ask=None, refused_too_fine=1)
        assert "Nothing was bought and nothing is resting." in said

    def test_with_no_refusal_the_old_sentence_is_unchanged(self):
        """The `no_quotes` case is a real measurement and must not move."""
        said = _words([], book_ask=None, refused_too_fine=0)
        assert said.startswith("Nobody quoted this combination")

    def test_a_refusal_is_mentioned_even_when_there_IS_a_price(self):
        """The refused quote may have been the cheapest one.

        A centi-cent price near 0c would have sorted first, so a screen that
        shows a price and stays silent about the drop can be showing the
        second-best number without saying so.
        """
        priced = parse_quotes(_payload()).quotes
        said = _words(list(priced), book_ask=None, refused_too_fine=1)
        assert "2 maker(s) answered" in said
        assert "A further 1 priced finer than a tenth of a cent" in said
        assert "Kalshi app" in said
class TestTheSellSideIsKeptRatherThanDiscarded:
    """Issue #76 slice 1. The exit price existed on the wire and nowhere else.

    `parse_quotes` read `no_bid_dollars` and threw `yes_bid_dollars` away. An
    RFQ has no side field, so a maker answers with both of their bids and
    `yes_bid_dollars` is literally what they would pay Joe for the side he
    holds -- the exit. Measured 2026-09-17: 16 of 44 quotes carried a YES bid
    on 3 of 3 held positions, every one at the full size asked
    (`docs/measurements/2026-09-17-combinations-can-be-exited.md`), and that
    measurement had to be taken with a throwaway script because nothing the
    recorder kept could answer it.

    What these do not establish
    ---------------------------
    - **Nothing about a sell-side RFQ.** This desk has never fired one through
      the product. These pin that a YES bid arriving in a payload survives to
      `RfqQuote`; firing the request is #76 slice 3.
    - **Nothing about a quote that carries ONLY a YES bid.** Such a quote is
      still dropped, because `parse_quotes` requires a readable `no_bid` to
      derive `yes_ask_tenths`, which is `NOT NULL` on the row and non-optional
      on the dataclass. Relaxing that changes an invariant the armed accept
      path relies on and is deliberately left to slice 3 -- it is only needed
      once a sell-side RFQ is actually fired, and nothing fires one yet.
    - **Nothing about whether an exit is a GOOD exit.** Every best bid measured
      on 2026-09-17 sat below Joe's cost basis.
    """

    def _one(self, **overrides) -> dict:
        row = dict(_payload()["quotes"][0])
        row.update(overrides)
        return {"quotes": [row]}

    def test_a_real_yes_bid_survives_to_the_quote(self):
        read = parse_quotes(self._one(yes_bid_dollars="0.0760"))
        assert read.quotes[0].yes_bid_tenths == 76

    def test_it_is_not_the_complement_of_the_no_bid(self):
        """The two are different numbers, separated by the maker's spread.

        `yes_ask_tenths` is DERIVED -- `complement(no_bid)` -- because a YES
        and a NO settle together at $1.00. `yes_bid_tenths` is a bid on the
        YES side directly. Reading one as the other is the venue's
        most-repeated correction run backwards.
        """
        quote = parse_quotes(self._one(yes_bid_dollars="0.0760")).quotes[0]
        assert quote.no_bid_tenths == 407
        assert quote.yes_ask_tenths == 593
        assert quote.yes_bid_tenths == 76
        assert quote.yes_bid_tenths != complement(quote.no_bid_tenths)

    def test_the_captured_payload_has_no_usable_sell_side_and_reads_as_none(self):
        """Both real captures carry `yes_bid_dollars: "0.0000"`.

        `complement(0)` reasoning applies to the YES side too: a maker
        "bidding" a settled outcome is not offering to buy. It resolves to
        None, never to 0, because `0` would say the maker offered nothing at
        all for the side he holds -- a different and worse claim than "this
        maker did not quote that side".
        """
        for quote in parse_quotes(_payload()).quotes:
            assert quote.yes_bid_tenths is None

    def test_an_untradeable_sell_side_does_not_lose_the_buy_side(self):
        """The extra field must never cost a price Joe can act on."""
        read = parse_quotes(self._one(yes_bid_dollars="1.0000"))
        assert len(read.quotes) == 1
        assert read.quotes[0].yes_ask_tenths == 593
        assert read.quotes[0].yes_bid_tenths is None

    def test_an_absent_sell_side_is_none_and_keeps_the_quote(self):
        row = dict(_payload()["quotes"][0])
        row.pop("yes_bid_dollars")
        read = parse_quotes({"quotes": [row]})
        assert len(read.quotes) == 1 and read.quotes[0].yes_bid_tenths is None

    def test_a_centi_cent_sell_side_is_refused_without_counting_as_too_fine(self):
        """A maker declining to price the side he does NOT hold is not a
        failure to price the one he does.

        `refused_finer_than_tenths` drives a sentence about whether the desk
        could show him a price to BUY (ADR 0172). Folding the sell side into
        that count would make the screen say a maker could not be shown when
        the buy price is right there.
        """
        read = parse_quotes(self._one(yes_bid_dollars="0.0055"))
        assert len(read.quotes) == 1
        assert read.quotes[0].yes_bid_tenths is None
        assert read.refused_finer_than_tenths == frozenset()
        assert read.refused_unreadable == frozenset()
class TestTheHandleReportsTheTargetTheVenueHolds:
    """Issue #72. A reused RFQ was reported at the target Joe typed.

    `create_rfq` reuses an open RFQ whenever its target is at least the one
    wanted, and `ask_market_to_price` holds RFQs open so a second tap can
    accept a quote. So asking at $1.00 and then at $5.00 hands back the $1.00
    request -- with quotes sized for $1.00 -- while the payload said $5.00.

    What these do not establish
    ---------------------------
    - Nothing about how often Joe re-asks at a larger number. The path exists
      because RFQs are held open; how often it is walked is unmeasured.
    - Nothing about the Take-it button's figure, which was always honest: it
      is computed from the quote's own size, not from the target.
    """

    class _Api:
        """Refuses the create with `already_exists`, then serves the open one."""

        def __init__(self, existing_target):
            self.existing_target = existing_target
            self.calls: list[str] = []

        async def request(self, method, path, *, params=None, json_body=None):
            self.calls.append(method)
            if method == "POST":
                raise _Err(400, {"error": {"code": "already_exists"}})
            if method == "GET":
                return {"rfqs": [{
                    "id": "rfq-open", "status": "open",
                    "market_ticker": "T",
                    "target_cost_dollars": self.existing_target,
                    "creator_user_id": "US",
                }]}
            raise AssertionError(method)

    async def _ask(self, api, wanted):
        return await create_rfq(
            api, market_ticker="T", collection_ticker="C",
            legs=[{"market_ticker": "L", "side": "yes"}],
            target_cost_dollars=wanted,
        )

    async def test_a_reused_rfq_reports_the_venues_target_not_the_asked_one(self):
        """The defect, written as a test. $1.00 held, $5.00 asked."""
        got = await self._ask(self._Api("1.0000"), "5.0000")
        assert got.rfq_id == "rfq-open"
        assert got.target_cost_dollars == "1.0000", "it reported what we typed"
        assert got.reused is True

    async def test_a_fresh_rfq_reports_the_target_it_was_created_at(self):
        class Api:
            async def request(self, method, path, *, params=None, json_body=None):
                return {"id": "rfq-new"}

        got = await self._ask(Api(), "5.0000")
        assert got.rfq_id == "rfq-new"
        assert got.target_cost_dollars == "5.0000"
        assert got.reused is False

    async def test_a_contracts_ask_carries_no_dollar_target(self):
        """`contracts=` names no dollar figure, so None is the honest answer.

        Substituting the requested target here would be inventing one.
        """
        class Api:
            async def request(self, method, path, *, params=None, json_body=None):
                return {"id": "rfq-new"}

        got = await create_rfq(
            Api(), market_ticker="T", collection_ticker="C",
            legs=[{"market_ticker": "L", "side": "yes"}], contracts=3,
        )
        assert got.target_cost_dollars is None

    async def test_an_unreadable_venue_target_is_none_not_the_requested_one(self):
        """A field that reports the request when it cannot read the truth is
        the defect, not the fix."""
        got = await self._ask(self._Api(None), "5.0000")
        assert got.target_cost_dollars is None


class TestTheWordsSayWhenTheVenueWasAskedAtADifferentNumber:
    def test_a_smaller_held_target_is_said_before_any_price(self):
        said = _words([], book_ask=None, asked_at="1.0000", requested="5.0000")
        assert said.startswith("These quotes answer a request for $1.0000")
        assert "$5.0000 you asked for" in said

    def test_equal_targets_say_nothing(self):
        """Saying it unconditionally trains him to skip it -- ADR 0170 Amd 1."""
        said = _words([], book_ask=None, asked_at="5.0000", requested="5.0000")
        assert "answer a request for" not in said

    def test_an_unknown_held_target_says_nothing(self):
        assert "answer a request for" not in _words(
            [], book_ask=None, asked_at=None, requested="5.0000"
        )

    def test_it_is_said_even_when_makers_answered(self):
        """It changes what every price below it means, so it cannot be
        dropped on the branch that HAS prices."""
        priced = parse_quotes(_payload()).quotes
        said = _words(
            list(priced), book_ask=None, asked_at="1.0000", requested="5.0000"
        )
        assert said.startswith("These quotes answer a request for $1.0000")
        assert "2 maker(s) answered" in said


LIST_FIXTURE = Path(__file__).parent / "fixtures" / "combo_rfq_list_market_wide.json"


def _list_payload() -> dict:
    return json.loads(LIST_FIXTURE.read_text())


class TestOpenRfqForFiltersToOurOwnRow:
    """Issue #147. `GET /communications/rfqs?market_ticker=` is market-wide.

    Measured 2026-09-24 (#129's run, on a held combination): the list came
    back 100 rows, every requester's, `creator_id` blank on all of them.
    That run tried `rfq_user_filter=self` (the QUOTES endpoint's own param
    name) and it was silently ignored -- same 100 rows with or without it.
    Re-measured with the RFQS endpoint's own documented name,
    `user_filter=self`: it narrows 100 rows to 0 (no open RFQ of ours on
    that market at the time); `status=open` alone did not narrow anything
    observable. `open_rfq_for` now sends `user_filter=self&status=open` on
    every call (`test_the_server_side_filter_is_sent_on_every_call` below),
    and keeps a `creator_user_id` check as a second guard, because the
    narrowing was only ever observed emptying a list, never returning one of
    our own rows: n = 1 own row (a DIFFERENT, uncommitted capture, read back
    by id) carried a non-empty `creator_user_id`, the only one of 100 that
    did.

    `tests/fixtures/combo_rfq_list_market_wide.json` is the CAPTURED
    evidence (`scripts/capture_rfq_list.py`, read-only GET, no create/delete/
    accept) that the market-wide case looks exactly like this: every row's
    `creator_user_id` absent or blank. It is captured on a combination the
    account does NOT hold -- Joe's rule that no account data enters this
    repo, even sanitized, so the real held-combination capture from #129 is
    never committed -- and it is the None case by construction regardless:
    no RFQ of ours was open on the (unheld) ticker asked about either. So
    the "ours" case below is built from one of its own rows with
    `creator_user_id` overridden in the test, never hand-typed from scratch.

    What this does not establish
    -----------------------------
    That `creator_user_id` is always present on our own rows in the list, or
    that `user_filter=self` always narrows correctly -- one observation of
    each (the #129 capture and this file's capture respectively; neither is
    a rate).
    """

    class _Api:
        """Serves the captured list, whatever it is, for one market."""

        def __init__(self, payload: dict):
            self.payload = payload
            self.calls: list[tuple] = []

        async def request(self, method, path, *, params=None, json_body=None):
            self.calls.append((method, path, params))
            assert method == "GET"
            return {"rfqs": self.payload["rfqs"]}

    async def test_the_server_side_filter_is_sent_on_every_call(self):
        """`user_filter=self&status=open` narrowed 100 rows to 0 when
        measured (2026-09-24); this pins that it is actually sent, not just
        documented."""
        payload = _list_payload()
        api = self._Api(payload)

        await open_rfq_for(api, payload["requested_ticker"])

        assert len(api.calls) == 1
        _, _, params = api.calls[0]
        assert params["user_filter"] == "self"
        assert params["status"] == "open"
        assert params["market_ticker"] == payload["requested_ticker"]

    async def test_a_market_wide_list_with_no_creator_user_id_returns_none(self):
        """The captured case: every row blank or absent on the field.

        This is the exact defect the ticket names -- the venue-captured list
        has an open-looking row (some are `status: open`) with no
        `creator_user_id` at all, and `open_rfq_for` must not hand one back
        as ours.
        """
        payload = _list_payload()
        assert any(r.get("status") == "open" for r in payload["rfqs"]), (
            "fixture must contain at least one open-looking stranger's row "
            "for this test to mean anything"
        )
        ticker = payload["requested_ticker"]
        api = self._Api(payload)

        assert await open_rfq_for(api, ticker) is None

    async def test_a_row_with_our_creator_user_id_is_returned(self):
        """Built from a captured row with `creator_user_id` overridden --
        see the class docstring: the captures taken had no open RFQ of ours
        at the time, so this is the only way to build the "ours" case from
        real wire shape rather than a hand-typed row.
        """
        payload = _list_payload()
        rows = [dict(r) for r in payload["rfqs"]]
        assert rows, "fixture must carry at least one row"
        # TEST-ONLY override: the captured fixture has no row of ours (see
        # the class docstring). Take one real captured row and mark it ours.
        rows[0]["creator_user_id"] = "REDACTED-USER"
        rows[0]["status"] = "open"
        ticker = payload["requested_ticker"]
        api = self._Api({"rfqs": rows})

        result = await open_rfq_for(api, ticker)
        assert result is not None
        assert result["id"] == rows[0]["id"]
        assert result["creator_user_id"] == "REDACTED-USER"

    async def test_a_blank_creator_user_id_is_skipped_even_when_open(self):
        """Direct guard against the defect: blank must never be `truthy`."""
        payload = _list_payload()
        rows = [dict(r) for r in payload["rfqs"]]
        assert rows
        rows[0]["creator_user_id"] = ""
        rows[0]["status"] = "open"
        ticker = payload["requested_ticker"]
        api = self._Api({"rfqs": rows})

        assert await open_rfq_for(api, ticker) is None

    async def test_a_409_with_only_strangers_rows_is_refused_not_reused(self):
        """End to end through `create_rfq`: a 409 whose market-wide list is
        all strangers must refuse, never hand a stranger's id back."""
        payload = _list_payload()
        ticker = payload["requested_ticker"]

        class Api:
            async def request(self, method, path, *, params=None, json_body=None):
                if method == "POST":
                    raise _Err(409, '{"error":{"code":"already_exists"}}')
                assert method == "GET"
                return {"rfqs": payload["rfqs"]}

        with pytest.raises(RfqRefused, match="already open") as excinfo:
            await create_rfq(
                Api(), market_ticker=ticker, collection_ticker="C",
                legs=[{"market_ticker": "L", "side": "yes"}],
                target_cost_dollars="5.0000",
            )
        assert str(excinfo.value) == (
            "an RFQ is already open on this combination -- wait for it to "
            "close and ask again."
        )

    async def test_the_refusal_is_plain_language_not_the_raw_venue_code(self):
        """The venue's own `already_exists` code used to leak into the
        message Joe would see. This is the exact case: a 409 whose
        market-wide list carries only strangers, so `existing` comes back
        `None` and this is the code path that used to say
        'Kalshi would not create the RFQ: HTTP 409:
        {"error":{"code":"already_exists"}}' verbatim."""
        class Api:
            async def request(self, method, path, *, params=None, json_body=None):
                if method == "POST":
                    raise _Err(409, '{"error":{"code":"already_exists"}}')
                return {"rfqs": []}

        with pytest.raises(RfqRefused) as excinfo:
            await create_rfq(
                Api(), market_ticker="T", collection_ticker="C",
                legs=[{"market_ticker": "L", "side": "yes"}],
                target_cost_dollars="5.0000",
            )
        assert "already_exists" not in str(excinfo.value)
        assert "already open" in str(excinfo.value)
