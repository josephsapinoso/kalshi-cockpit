"""#191: `/hedge` reads every watched leg's book in ONE batched venue request.

What these tests establish:
- `GET /markets?tickers=` is parsed from a **captured** response
  (`tests/fixtures/markets_batch_by_ticker.json`, 2026-09-29). A settled
  market comes back with `status: finalized`, and a ticker the venue has never
  heard of is omitted, so it is absent from the result: never an empty book.
- A market the caller did not ask for is dropped, and a renamed envelope
  raises instead of reading as "no books".
- `LiveQuoteSource.fetch_many` makes exactly one request per 100 tickers,
  with `limit` equal to the chunk, and folds every request failure into
  `QuoteUnavailable`.
- `build_payload` handed a batch reader makes one venue call for N watched
  tickers. This is the test that fails if the reads go back to one per
  ticker.
- Every production caller (the route, the watcher, `drive_hedge.py`) passes
  the batch reader, and the watcher threads it through to `build_payload`.

What they do not establish:
- That the batch read is faster on live. The prediction (1,803 ms warm median,
  down to roughly 300–450 ms) is recorded on #191 and is checked there after
  deploy.
- Whether one `tickers=` request costs one read token or one per ticker
  (`GET /account/endpoint_costs`, unread).
- Anything about a skip rule for closed legs. None was added: on 2026-09-29
  none of the 12 watched legs had started, so a skip would have saved nothing.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from backend import hedge
from backend.kalshi.quotes import (
    MAX_TICKERS_PER_READ,
    LiveQuoteSource,
    QuoteUnavailable,
    parse_markets_batch,
)
from backend.store import db

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = json.loads(
    (ROOT / "tests" / "fixtures" / "markets_batch_by_ticker.json").read_text("utf-8")
)
ASKED = FIXTURE["asked"]
OPEN_A, OPEN_B, SETTLED, MADE_UP = ASKED
NOW_MS = 1_790_700_000_000


class FakeRest:
    """Serves the captured batch response the way the venue did: only the
    asked tickers that exist come back, in the order the capture returned."""

    def __init__(self, *, fail: Exception | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.fail = fail

    async def get(self, path, **params):
        self.calls.append((path, params))
        if self.fail is not None:
            raise self.fail
        if path != "/markets":
            # A single-market read. Nothing in the capture matches a
            # malformed ticker, so the venue would 404 it.
            raise RuntimeError(f"404 for {path}")
        wanted = set(params["tickers"].split(","))
        markets = [
            m for m in FIXTURE["response"]["markets"] if m["ticker"] in wanted
        ]
        return {"markets": markets, "cursor": self.cursor}

    cursor = ""


class TestTheCapturedBatchResponse:
    def test_the_capture_is_what_the_parser_was_written_against(self):
        # If a re-capture changes these, the parser's premises changed too.
        assert FIXTURE["http_status"] == 200
        assert FIXTURE["returned_in_order"] == [OPEN_A, OPEN_B, SETTLED]
        assert FIXTURE["request"]["params"]["limit"] == len(ASKED)

    def test_every_asked_ticker_the_venue_knows_comes_back(self):
        quotes = parse_markets_batch(
            FIXTURE["response"], asked=ASKED, observed_ms=NOW_MS
        )
        assert set(quotes) == {OPEN_A, OPEN_B, SETTLED}

    def test_a_ticker_the_venue_never_heard_of_is_absent_not_empty(self):
        quotes = parse_markets_batch(
            FIXTURE["response"], asked=ASKED, observed_ms=NOW_MS
        )
        assert MADE_UP not in quotes

    def test_a_settled_market_keeps_its_terminal_status(self):
        quotes = parse_markets_batch(
            FIXTURE["response"], asked=ASKED, observed_ms=NOW_MS
        )
        assert quotes[SETTLED].status == "finalized"
        assert not quotes[SETTLED].tradeable
        assert quotes[OPEN_A].status == "active"

    def test_prices_parse_to_tenths_through_the_one_market_parser(self):
        raw = next(
            m for m in FIXTURE["response"]["markets"] if m["ticker"] == OPEN_A
        )
        quote = parse_markets_batch(
            FIXTURE["response"], asked=ASKED, observed_ms=NOW_MS
        )[OPEN_A]
        expected = round(float(raw["yes_bid_dollars"]) * 1000)
        assert quote.market.yes_bid_tenths == expected
        assert quote.observed_ms == NOW_MS

    def test_a_market_nobody_asked_for_is_dropped(self):
        quotes = parse_markets_batch(
            FIXTURE["response"], asked=[OPEN_A], observed_ms=NOW_MS
        )
        assert set(quotes) == {OPEN_A}

    def test_a_renamed_envelope_raises_rather_than_reading_as_no_books(self):
        with pytest.raises(QuoteUnavailable):
            parse_markets_batch(
                {"market_list": FIXTURE["response"]["markets"]},
                asked=ASKED,
                observed_ms=NOW_MS,
            )

    def test_markets_that_are_not_a_list_raise(self):
        with pytest.raises(QuoteUnavailable):
            parse_markets_batch(
                {"markets": {"ticker": OPEN_A}}, asked=ASKED, observed_ms=NOW_MS
            )


class TestFetchMany:
    async def test_up_to_a_hundred_tickers_is_one_request(self):
        rest = FakeRest()
        source = LiveQuoteSource(rest=rest)
        asked = ASKED + [f"KXFAKE-{i}" for i in range(MAX_TICKERS_PER_READ - 4)]
        assert len(asked) == MAX_TICKERS_PER_READ
        quotes = await source.fetch_many(asked, observed_ms=NOW_MS)
        assert len(rest.calls) == 1
        path, params = rest.calls[0]
        assert path == "/markets"
        assert params["tickers"].split(",") == asked
        assert params["limit"] == len(asked)
        assert set(quotes) == {OPEN_A, OPEN_B, SETTLED}

    async def test_a_hundred_and_one_tickers_is_two_requests(self):
        rest = FakeRest()
        source = LiveQuoteSource(rest=rest)
        asked = ASKED + [f"KXFAKE-{i}" for i in range(MAX_TICKERS_PER_READ - 3)]
        assert len(asked) == MAX_TICKERS_PER_READ + 1
        await source.fetch_many(asked, observed_ms=NOW_MS)
        assert len(rest.calls) == 2
        assert [p["limit"] for _, p in rest.calls] == [MAX_TICKERS_PER_READ, 1]

    async def test_a_repeated_ticker_is_asked_once(self):
        rest = FakeRest()
        await LiveQuoteSource(rest=rest).fetch_many(
            [OPEN_A, OPEN_A, OPEN_B], observed_ms=NOW_MS
        )
        assert rest.calls[0][1]["tickers"] == f"{OPEN_A},{OPEN_B}"

    async def test_no_tickers_is_no_request(self):
        rest = FakeRest()
        assert await LiveQuoteSource(rest=rest).fetch_many([], observed_ms=NOW_MS) == {}
        assert rest.calls == []

    async def test_a_malformed_ticker_never_enters_the_batch(self):
        # Hand-typed leg tickers are free text. One bad entry in the
        # comma-joined list must not be able to fail every leg's read.
        rest = FakeRest()
        junk = ["bad ticker", "KX,SPLIT", "lowercase-1"]
        quotes = await LiveQuoteSource(rest=rest).fetch_many(
            [OPEN_A, *junk, SETTLED], observed_ms=NOW_MS
        )
        batch = [p for path, p in rest.calls if path == "/markets"]
        assert len(batch) == 1
        assert batch[0]["tickers"].split(",") == [OPEN_A, SETTLED]
        singles = sorted(path for path, _ in rest.calls if path != "/markets")
        assert singles == sorted(f"/markets/{t}" for t in junk)
        assert set(quotes) == {OPEN_A, SETTLED}

    async def test_a_blank_ticker_is_not_read_at_all(self):
        rest = FakeRest()
        quotes = await LiveQuoteSource(rest=rest).fetch_many(
            ["", "   ", OPEN_B], observed_ms=NOW_MS
        )
        assert [path for path, _ in rest.calls] == ["/markets"]
        assert set(quotes) == {OPEN_B}

    async def test_a_paged_answer_that_drops_a_ticker_is_logged(self, caplog):
        rest = FakeRest()
        rest.cursor = "more"
        with caplog.at_level("WARNING"):
            await LiveQuoteSource(rest=rest).fetch_many(ASKED, observed_ms=NOW_MS)
        assert any("with a cursor" in r.getMessage() for r in caplog.records)

    async def test_a_failed_request_is_quote_unavailable(self):
        rest = FakeRest(fail=RuntimeError("the venue did not answer"))
        with pytest.raises(QuoteUnavailable):
            await LiveQuoteSource(rest=rest).fetch_many(ASKED, observed_ms=NOW_MS)


@pytest.fixture()
def conn(tmp_path):
    connection = db.init_db(tmp_path / "cockpit.db")
    yield connection
    connection.close()


def _record_all_four(conn):
    return hedge.record_position(
        conn,
        now_ms=NOW_MS,
        source="sportsbook",
        label="four legs",
        stake_tenths=5_000,
        return_tenths=100_000,
        legs=[
            {"ticker": t, "side": "yes", "label": f"leg {i}"}
            for i, t in enumerate(ASKED)
        ],
    )


class TestTheHedgeScreenReadsOnce:
    async def test_n_watched_tickers_cost_one_venue_call(self, conn):
        _record_all_four(conn)
        rest = FakeRest()
        payload = await hedge.build_payload(
            conn,
            now_ms=NOW_MS,
            max_quote_age_ms=30_000,
            spendable_tenths=None,
            fetch_quotes=LiveQuoteSource(rest=rest).fetch_many,
        )
        assert len(rest.calls) == 1
        assert set(rest.calls[0][1]["tickers"].split(",")) == set(ASKED)
        legs = {
            leg["ticker"]: leg for leg in payload["positions"][0]["legs"]
        }
        assert legs[OPEN_A]["priceable"] is True
        assert legs[SETTLED]["priceable"] is True
        assert legs[MADE_UP]["priceable"] is False

    async def test_a_failed_batch_leaves_every_leg_unpriced_and_does_not_raise(
        self, conn
    ):
        _record_all_four(conn)
        rest = FakeRest(fail=RuntimeError("down"))
        payload = await hedge.build_payload(
            conn,
            now_ms=NOW_MS,
            max_quote_age_ms=30_000,
            spendable_tenths=None,
            fetch_quotes=LiveQuoteSource(rest=rest).fetch_many,
        )
        assert len(rest.calls) == 1
        assert not any(
            leg["priceable"] for leg in payload["positions"][0]["legs"]
        )

    async def test_the_batch_reader_wins_over_a_single_reader(self):
        # A caller holding both must not fall back into the per-ticker loop.
        async def single(ticker, *, observed_ms):
            raise AssertionError("the per-ticker loop ran")

        rest = FakeRest()
        books = await hedge.read_books(
            ASKED,
            now_ms=NOW_MS,
            fetch_quote=single,
            fetch_quotes=LiveQuoteSource(rest=rest).fetch_many,
        )
        assert set(books) == {OPEN_A, OPEN_B, SETTLED}
        assert books[SETTLED].status == "finalized"

    async def test_no_reader_at_all_is_a_programming_error(self):
        with pytest.raises(TypeError):
            await hedge.read_books(ASKED, now_ms=NOW_MS)


class TestEveryProductionCallerPassesTheBatchReader:
    @pytest.mark.parametrize(
        "path",
        ["backend/api/routers/hedge.py", "scripts/run_loop.py", "scripts/drive_hedge.py"],
    )
    def test_the_caller_passes_fetch_quotes_and_never_fetch_quote(self, path):
        source = (ROOT / path).read_text("utf-8")
        assert re.search(r"\bfetch_quotes=\w[\w.()]*\.fetch_many\b", source)
        assert re.search(r"\bfetch_quote=", source) is None

    def test_the_watcher_threads_fetch_quotes_through_to_build_payload(self):
        tree = ast.parse((ROOT / "backend" / "hedge_watch.py").read_text("utf-8"))
        passed = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                if name in ("build_payload", "watch_once"):
                    kw = {k.arg: k.value for k in node.keywords}
                    value = kw.get("fetch_quotes")
                    passed[name] = isinstance(value, ast.Name) and value.id == "fetch_quotes"
        assert passed == {"build_payload": True, "watch_once": True}
