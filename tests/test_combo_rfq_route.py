"""`POST /api/parlays/rfq` -- asking makers what a combination costs.

What these tests establish: the route is auth-gated; it refuses a ticker this
desk has no record of minting rather than taking the legs from the request;
it records the ask BEFORE any quote arrives; it reads every quote before
withdrawing the RFQ, because withdrawing destroys the venue's copy; a book that was empty at the same instant is stored as NULL, not zero;
and nobody answering is a stated outcome rather than an error.

What they do not establish
--------------------------
- **Nothing about acceptance.** There is no accept path yet, by design, and
  no test here spends money or pretends to.
- **Nothing about how makers behave.** The fake answers instantly and always.
  How many makers quote, how fast, and how far apart is one live reading
  (n = 1) recorded in
  `docs/measurements/2026-09-17-a-combo-rfq-returns-a-real-takeable-price.md`.
- **Nothing about whether a quoted price is worth taking.** The route states
  the quote and the fair value and draws no conclusion; so do these tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db as store

HEADERS = {"Authorization": "Bearer secret-token"}
TICKER = "KXMVECROSSCATEGORY-SHARD1-TEST"
LEGS = [
    {"event_ticker": "E1", "market_ticker": "M1", "side": "yes"},
    {"event_ticker": "E2", "market_ticker": "M2", "side": "yes"},
]


def _pem(tmp_path: Path) -> Path:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    path = tmp_path / "key.pem"
    if not path.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    return path


class FakeApi:
    """Stands in for `KalshiRestClient`, recording the order of calls.

    `calls` is the point of this class: read-before-delete is a correctness
    property, not a style choice, and only the sequence proves it.
    """

    def __init__(self, *, quotes=None, book=None):
        self.calls: list[str] = []
        self._quotes = quotes if quotes is not None else []
        self._book = book if book is not None else {"yes_dollars": [], "no_dollars": []}
        self.deleted = False
        self.shard1 = "50.0000"

    async def orderbook(self, ticker, depth=10):
        self.calls.append("orderbook")
        return self._book

    async def get(self, path, **params):
        """`/portfolio/balance`, so the RFQ can size itself to the shard."""
        self.calls.append("balance")
        return {"balance_breakdown": [
            {"exchange_index": 0, "balance": "0.0065"},
            {"exchange_index": 1, "balance": self.shard1},
        ]}

    async def request(self, method, path, *, params=None, json_body=None):
        if method == "POST" and path.endswith("/rfqs"):
            self.calls.append("create")
            assert params == {"exchange_index": 1}, "the write must name the shard"
            return {"id": "rfq-test"}
        if method == "GET" and path.endswith("/quotes"):
            self.calls.append("read")
            # **Models the venue, not a convenience.** Deleting an RFQ drops
            # its quotes: measured 2026-09-17, a re-read after DELETE came
            # back empty. A fake that kept serving them would make
            # delete-before-read look harmless, which is exactly the bug the
            # ordering exists to prevent.
            return {"quotes": [] if self.deleted else self._quotes}
        if method == "DELETE":
            self.calls.append("delete")
            self.deleted = True
            return {}
        raise AssertionError(f"unexpected {method} {path}")


def _quote_row(quote_id: str, no_bid: str) -> dict:
    return {
        "id": quote_id,
        "rfq_id": "rfq-test",
        "creator_id": f"maker-{quote_id}",
        "market_ticker": TICKER,
        "no_bid_dollars": no_bid,
        "no_contracts_fp": "8.19",
        "status": "open",
        "created_ts": "2026-09-17T15:50:47.631646Z",
    }


@pytest.fixture()
def build(tmp_path, monkeypatch):
    def _build(*, quotes=None, book=None, seed_lookup=True):
        path = tmp_path / "t.db"
        conn = store.init_db(path)
        if seed_lookup:
            conn.execute(
                """
                INSERT INTO parlay_lookups (
                    requested_ms, card_key, stake_cents, status,
                    collection_ticker, minted_market_ticker, selected_legs,
                    fair_joint_conservative
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1_000, "safe", 500, "book_empty",
                    "KXMVECROSSCATEGORY-R", TICKER, json.dumps(LEGS), 0.57805,
                ),
            )
            conn.commit()
        conn.close()

        fake = FakeApi(quotes=quotes, book=book)
        monkeypatch.setattr(
            "backend.api.routes.KalshiRestClient", lambda config, client=None: fake
        )
        monkeypatch.setenv("KALSHI_API_KEY", "key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(_pem(tmp_path)))
        # The real wait is seconds; the fake answers instantly and the poll
        # loop would otherwise burn that wall-clock in every test.
        monkeypatch.setattr("backend.combo_rfq.QUOTE_WAIT_S", 0.05)
        monkeypatch.setattr("backend.combo_rfq.QUOTE_POLL_S", 0.01)

        app = create_app(
            AppConfig(instance_mode="live", auth_token="secret-token", db_path=path)
        )
        return app, fake, path
    return _build


async def _post(app, body, headers=HEADERS):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post("/api/parlays/rfq", json=body, headers=headers)


def _body(**kw):
    return {"market_ticker": TICKER, "target_cost_dollars": "5.0000", **kw}


class TestTheDoorIsGuarded:
    async def test_it_needs_auth(self, build):
        app, _, _ = build()
        assert (await _post(app, _body(), headers={})).status_code in (401, 403)

    async def test_a_ticker_this_desk_never_minted_is_refused(self, build):
        """The legs and fair value come from the record, never the request.

        Without this the screen could name any ticker and any legs, and the
        server would ask a maker to price whatever it was handed.
        """
        app, fake, _ = build(seed_lookup=False)
        response = await _post(app, _body())
        assert response.status_code == 404
        assert "no record of minting" in response.json()["detail"]
        assert fake.calls == [], "nothing may reach the venue on a refusal"

    async def test_a_zero_target_cost_is_refused_before_the_venue(self, build):
        app, fake, _ = build()
        response = await _post(app, _body(target_cost_dollars="0.0000"))
        assert response.status_code == 422
        assert fake.calls == []


class TestWhatComesBack:
    async def test_quotes_are_returned_cheapest_first(self, build):
        app, _, _ = build(
            quotes=[_quote_row("q1", "0.3690"), _quote_row("q2", "0.4070")]
        )
        body = (await _post(app, _body())).json()
        assert body["status"] == "quoted"
        assert [q["yes_ask_tenths"] for q in body["quotes"]] == [593, 631]

    async def test_the_fair_value_comes_from_the_recorded_lookup(self, build):
        app, _, _ = build(quotes=[_quote_row("q1", "0.4070")])
        body = (await _post(app, _body())).json()
        assert body["fair"]["conservative"] == pytest.approx(0.57805)

    async def test_an_empty_book_is_reported_as_null_not_zero(self, build):
        """NULL means the book had no ask. Zero would be a price."""
        app, _, _ = build(quotes=[_quote_row("q1", "0.4070")])
        body = (await _post(app, _body())).json()
        assert body["book_yes_ask_tenths"] is None
        assert "normal resting state" in body["words"]

    async def test_nobody_answering_is_stated_not_an_error(self, build):
        app, _, _ = build(quotes=[])
        response = await _post(app, _body())
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "no_quotes"
        assert body["quotes"] == []
        assert "not a verdict on the bet" in body["words"]

    async def test_the_words_never_call_a_quote_an_edge(self, build):
        """`beta = -0.141`: the quote-vs-fair gap may be shown, never sold.

        A screen that called this gap an edge would be ranking by the one
        number this repo has measured to be negative (ADR 0071 s2.5).
        """
        app, _, _ = build(
            quotes=[_quote_row("q1", "0.3690"), _quote_row("q2", "0.4070")]
        )
        words = (await _post(app, _body())).json()["words"].lower()
        for forbidden in ("edge", "cheap", "value bet", "good price", "worth it"):
            assert forbidden not in words, forbidden

    async def test_the_spread_between_makers_is_stated(self, build):
        app, _, _ = build(
            quotes=[_quote_row("q1", "0.3690"), _quote_row("q2", "0.4070")]
        )
        assert "3.8 cents apart" in (await _post(app, _body())).json()["words"]


class TestTheOrderOfOperations:
    async def test_the_rfq_is_left_standing_so_a_second_tap_can_take_it(
        self, build
    ):
        """**The default changed when the accept path landed.**

        Withdrawing an RFQ destroys the venue's copy of every quote, so a
        screen that shows a price and then asks Joe to confirm it must keep
        the request alive in between -- otherwise the thing he confirms no
        longer exists. The cost is one of the venue's 100 open RFQ slots.
        """
        app, fake, path = build(quotes=[_quote_row("q1", "0.4070")])
        await _post(app, _body())
        assert "delete" not in fake.calls, (
            "the RFQ was withdrawn, so the quote the screen is showing is "
            "already gone and the second tap cannot take it"
        )
        conn = store.open_db(path, read_only=True)
        row = conn.execute("SELECT deleted_ms FROM combo_rfqs").fetchone()
        conn.close()
        assert row["deleted_ms"] is None

    async def test_a_delete_before_the_read_loses_every_price(self, build):
        """Withdrawing destroys the venue's copy of every quote.

        Measured 2026-09-17: a re-read after DELETE returned zero. So the
        load-bearing order is READ-then-delete, enforced by the poll loop.
        The fake models that -- it serves nothing once deleted -- and the
        mutation that moves `delete_rfq` above the loop turns this red.

        **An earlier version of this test asserted that the disk WRITE
        happened before the delete and was green with the two swapped**: the
        quotes are already in memory by then, so that ordering guards
        nothing. The claim was corrected rather than the test weakened.
        """
        app, fake, path = build(quotes=[_quote_row("q1", "0.4070")])
        # `hold_open=False` is the path that still withdraws -- a price nobody
        # intends to take. The ordering guard lives here because this is the
        # only branch where a delete happens at all.
        import backend.combo_rfq as combo_rfq
        from backend.store import db as store_db

        conn = store_db.open_db(path)
        try:
            await combo_rfq.ask_market_to_price(
                conn, market_ticker=TICKER, target_cost_dollars="5.0000",
                now_ms=1_000, api=fake, hold_open=False,
            )
        finally:
            conn.close()

        assert "delete" in fake.calls
        assert fake.calls.index("read") < fake.calls.index("delete")

        conn = store.open_db(path, read_only=True)
        stored = conn.execute("SELECT COUNT(*) FROM combo_rfq_quotes").fetchone()[0]
        conn.close()
        assert stored == 1, "the quote must be on disk, not only in the response"

    async def test_the_ask_is_recorded_even_when_nobody_answers(self, build):
        app, _, path = build(quotes=[])
        await _post(app, _body())
        conn = store.open_db(path, read_only=True)
        row = conn.execute("SELECT * FROM combo_rfqs").fetchone()
        conn.close()
        assert row["status"] == "no_quotes"
        assert row["exchange_index"] == 1
        assert row["target_cost_dollars"] == "5.0000"
        # `deleted_ms` stays NULL now: the RFQ is held open for the second
        # tap. It is stamped only on the `hold_open=False` path.
        assert row["deleted_ms"] is None

    async def test_the_book_is_read_for_context_before_the_rfq_is_created(self, build):
        """Both numbers, same instant -- otherwise proving the two surfaces
        disagree needs a whole separate experiment."""
        app, fake, _ = build(quotes=[_quote_row("q1", "0.4070")])
        await _post(app, _body())
        assert fake.calls.index("orderbook") < fake.calls.index("create")


class TestTheAskFitsWhatIsOnTheShard:
    """**The bug Joe hit on 2026-09-17, and the fix he chose on 2026-09-18.**

    The route asked for a flat $5.00 regardless of his balance. On a 2.7c
    combination that is 173 contracts; he had $3.94 on the shard, and the
    accept was refused with `insufficient_balance` after 28 makers had
    already answered. A quote is all-or-nothing at the size asked for, so an
    unaffordable target is wasted on both sides.

    The first fix silently TRIMMED the target to 90% of the shard. That put
    two independent limits on one quantity -- the caller's figure and the
    shard -- swapping over at $5.5556 of balance **with no change in symptom**,
    because nothing printed the dollars either way. Issue #62, answered (A):
    Joe types the size, and the shard is a wall that says so before the
    makers are asked.
    """

    async def test_a_target_the_shard_cannot_pay_is_refused_not_trimmed(
        self, build
    ):
        app, fake, _ = build(quotes=[_quote_row("q1", "0.4070")])
        fake.shard1 = "3.9359"
        response = await _post(app, _body(target_cost_dollars="5.0000"))
        assert response.status_code == 400
        assert "create" not in fake.calls, (
            "the makers must not be asked for a price that cannot be taken"
        )

    async def test_the_refusal_names_the_number_he_can_ask_for(self, build):
        """A refusal he cannot act on is a dead end. 90% of $3.9359 is
        $3.54, and saying so turns one refusal into one re-type."""
        app, fake, _ = build(quotes=[_quote_row("q1", "0.4070")])
        fake.shard1 = "3.9359"
        detail = (await _post(app, _body(target_cost_dollars="5.0000"))).json()
        words = detail["detail"]
        assert "$3.54" in words
        assert "combinations shard" in words

    async def test_the_wall_is_the_headroom_not_the_whole_balance(self, build):
        """The fee is charged ON TOP of the contracts, so a target equal to
        the balance leaves nothing to pay it with -- which is the refusal
        this exists to prevent, arriving one step later."""
        app, fake, _ = build(quotes=[_quote_row("q1", "0.4070")])
        fake.shard1 = "5.0000"
        response = await _post(app, _body(target_cost_dollars="5.0000"))
        assert response.status_code == 400, (
            "$5.00 of a $5.00 shard leaves nothing for the fee"
        )

    async def test_an_affordable_target_is_left_alone(self, build):
        app, fake, _ = build(quotes=[_quote_row("q1", "0.4070")])
        fake.shard1 = "50.0000"
        body = (await _post(app, _body(target_cost_dollars="5.0000"))).json()
        assert body["target_cost_dollars"] == "5.0000"

    async def test_the_balance_is_read_before_the_rfq_is_created(self, build):
        """Refusing after the ask would be refusing nothing -- the makers'
        work is already spent by then, which is the whole failure."""
        app, fake, _ = build(quotes=[_quote_row("q1", "0.4070")])
        await _post(app, _body())
        assert fake.calls.index("balance") < fake.calls.index("create")

    async def test_an_unreadable_balance_leaves_the_target_standing(self, build):
        """Refusing to ask for a price over a balance we could not parse
        would be worse than asking for one he might not be able to take."""
        app, fake, _ = build(quotes=[_quote_row("q1", "0.4070")])

        async def boom(path, **params):
            fake.calls.append("balance")
            raise RuntimeError("no balance")

        fake.get = boom
        body = (await _post(app, _body(target_cost_dollars="5.0000"))).json()
        assert body["target_cost_dollars"] == "5.0000"
        assert body["status"] == "quoted"
class TestTheScreenCanShowBothSurfaces:
    """Issue #66. Neither surface dominates, so a screen reading one of them
    sometimes reports no price when there is one, and sometimes shows the
    worse of two. Measured 2026-09-17: the public book beat the RFQ on two of
    three held combinations and the RFQ was the only price on the third.
    """

    async def test_an_empty_book_renders_as_nothing_not_as_zero(self, build):
        app, _, _ = build(quotes=[_quote_row("q1", "0.4070")])
        body = (await _post(app, _body())).json()
        assert body["book_yes_ask_tenths"] is None
        assert body["book_ask_display"] is None

    async def test_a_book_with_an_ask_is_rendered_beside_the_quotes(self, build):
        """A resting NO bid IS the YES ask, through the derived-ask identity,
        and it is rendered by the same renderer as the maker's price -- a
        second formatter in TypeScript is how two surfaces start disagreeing
        about what 59.3c means on a market that ticks in deci-cents."""
        app, _, _ = build(
            quotes=[_quote_row("q1", "0.4070")],
            book={"yes_dollars": [], "no_dollars": [["0.4500", 10]]},
        )
        body = (await _post(app, _body())).json()
        assert body["book_yes_ask_tenths"] == 550
        assert body["book_ask_display"] == "55c per $1 contract"


class TestAQuoteCarriesItsAge:
    """Issue #67. A maker has about **three seconds** to stand behind a quote
    on a combination, against 30 elsewhere. A price with no age on it is a
    price the reader cannot tell is dead."""

    async def test_the_payload_says_when_the_prices_were_captured(self, build):
        app, _, _ = build(quotes=[_quote_row("q1", "0.4070")])
        body = (await _post(app, _body())).json()
        assert isinstance(body["asked_ms"], int)
        assert body["asked_ms"] > 1_700_000_000_000


class TestAQuoteSaysWhatLeavesTheAccount:
    """Issue #68, and #39's settled precedent on the singles ticket: the
    control that spends prints the dollars, fee included.

    What this does not establish: that Kalshi will charge exactly this. The
    coefficient (0.071) exceeds every implied k this repo has measured by
    construction, so the figure errs HIGH -- which is the safe direction for a
    cost shown before a tap, and the opposite of the rule for a hedge lock.
    """

    async def test_the_all_in_cost_is_the_price_plus_the_fee(self, build):
        """8.19 contracts at 59.3c is $4.86 of contracts and $5.00 all in.
        Fourteen cents on a five-dollar bet is the whole reason this is on
        the button rather than in a footnote."""
        app, _, _ = build(quotes=[_quote_row("q1", "0.4070")])
        quote = (await _post(app, _body())).json()["quotes"][0]
        assert quote["ask_display"] == "59.3c per $1 contract"
        assert quote["fee_tenths"] == 141
        assert quote["all_in_tenths"] == 4_998
        assert quote["all_in_display"] == "$5.00"

    async def test_the_fee_is_never_silently_dropped(self, build):
        """A quote whose size cannot be read has an unknown cost, and the
        button must say nothing rather than print the contracts alone --
        which would be a smaller, friendlier, wrong number."""
        row = _quote_row("q1", "0.4070")
        row["no_contracts_fp"] = None
        app, _, _ = build(quotes=[row])
        quote = (await _post(app, _body())).json()["quotes"][0]
        assert quote["contracts"] is None
        assert quote["all_in_tenths"] is None
        assert quote["all_in_display"] is None
        assert quote["fee_tenths"] is None

    async def test_the_all_in_figure_is_above_the_bare_contracts(self, build):
        """The direction is the claim: the fee is charged ON TOP of the
        contracts on a fee-inclusive target, so an all-in figure at or below
        the contract cost would be the fee going missing."""
        app, _, _ = build(quotes=[_quote_row("q1", "0.4070")])
        quote = (await _post(app, _body())).json()["quotes"][0]
        bare = round(quote["contracts"] * quote["yes_ask_tenths"])
        assert quote["all_in_tenths"] > bare
        assert quote["all_in_tenths"] - bare == quote["fee_tenths"]
