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
from backend.kalshi.rfq import RfqRefused, create_rfq, parse_quotes

FIXTURE = Path(__file__).parent / "fixtures" / "combo_rfq_quotes.json"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text())


class TestTheCapturedQuotes:
    """Pinned against the real wire payload, never a hand-built one."""

    def test_both_captured_quotes_parse(self):
        quotes = parse_quotes(_payload())
        assert len(quotes) == 2

    def test_a_makers_no_bid_is_the_price_joe_pays_for_yes(self):
        """The derived-ask identity, which is the whole point of this module.

        The book showed nothing. The maker's NO bid of $0.4070 IS an offer to
        sell YES at $0.5930, and reading only `yes_dollars` is what made this
        desk tell Joe the combination could not be bought.
        """
        cheapest = parse_quotes(_payload())[0]
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

        asks = [q.yes_ask_tenths for q in parse_quotes(payload)]
        assert asks == [593, 631], "expensive quote came back first"
        assert asks[-1] - asks[0] == 38  # 3.8 cents, the measured spread

    def test_the_quoted_size_survives(self):
        assert parse_quotes(_payload())[0].contracts == pytest.approx(8.19)

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
        assert parse_quotes(self._one(no_bid_dollars="0.0000")) == ()

    def test_a_full_dollar_no_bid_is_refused_too(self):
        assert parse_quotes(self._one(no_bid_dollars="1.0000")) == ()

    def test_an_unparseable_price_drops_the_row(self):
        assert parse_quotes(self._one(no_bid_dollars="not-a-price")) == ()
        assert parse_quotes(self._one(no_bid_dollars=None)) == ()

    def test_a_negative_price_drops_the_row(self):
        assert parse_quotes(self._one(no_bid_dollars="-0.4070")) == ()

    def test_a_centi_cent_price_is_refused_rather_than_rounded(self):
        """A combination ticks in hundredths of a cent at the edges.

        `dollars_to_tenths("0.0055")` rounds half-up to 6 tenths. On the money
        path that invents a price the venue never offered, so the row is
        dropped instead. This is the one behaviour that would look like a bug
        if you only read the happy path.
        """
        assert parse_quotes(self._one(no_bid_dollars="0.0055")) == ()
        # ...while an exactly-representable edge price still parses.
        kept = parse_quotes(self._one(no_bid_dollars="0.0050"))
        assert len(kept) == 1 and kept[0].no_bid_tenths == 5

    def test_a_missing_size_is_none_and_keeps_the_quote(self):
        """The price is the thing being read; an unreadable size is not fatal."""
        quotes = parse_quotes(self._one(no_contracts_fp="?"))
        assert len(quotes) == 1 and quotes[0].contracts is None


class TestTheRfqIdFilter:
    def test_quotes_for_another_rfq_are_not_ours(self):
        """`rfq_user_filter=self` returns every open RFQ's quotes, not one's.

        Without this filter a second RFQ open at the same moment would put
        another combination's price on this card.
        """
        payload = _payload()
        assert parse_quotes(payload, rfq_id="RFQ_REDACTED") != ()
        assert parse_quotes(payload, rfq_id="some-other-rfq") == ()


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

        rfq_id = await create_rfq(
            FakeApi(),
            market_ticker="KXMVECROSSCATEGORY-SHARD1-XYZ",
            collection_ticker="KXMVECROSSCATEGORY-R",
            legs=[{"event_ticker": "E", "market_ticker": "M", "side": "yes"}],
            target_cost_dollars="5.0000",
        )

        assert rfq_id == "rfq-1"
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
