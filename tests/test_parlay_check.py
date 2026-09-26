"""`POST /api/parlays/check` -- reading a friend's parlay (#166, #165).

What these tests establish: EVERY `KXMVE...` token in pasted text is
collected and classified as market-shaped, event-shaped or series-only; a
market-shaped token is used directly, an event-shaped one is resolved to its
one market via a second venue read, and a series-only one (or no token at
all) refuses before any venue call and before any row -- a real kalshi.com
combo URL names the SERIES first and the EVENT last, never the market, so
"first match wins" silently picked the wrong token and 404d (round-2 finding,
`docs/measurements/` -- kalshi-platform review). Also established: a leg
whose `exchange_index` is not Kalshi's combinations shard (1), or whose
`status` is not `active`, is answered with `rfq_available: false` and a named
reason, without touching `combo_rfq.py`/`kalshi/rfq.py`; a leg missing its own
`market_ticker` or `event_ticker` is refused by name before any row, the same
as a leg with no readable side; each leg's chance is looked up in the SAME
candidate pool the ladder itself scans, so a leg the pool cannot answer for
reads `chance: null` with WORDS (never a bare code, and never `0.0`) plus the
code beside it as `unknown_reason_code`; the joint is refused (not computed)
when a leg is unknown or when two legs share one game; the row this desk
writes (`card_key = "checked"`) is exactly what
`bets._chance_when_priced_by_ticker` and `combo_rfq._recorded_lookup` already
know how to read; the empty-book words never claim Kalshi just created the
market (this module never mints); a book with only sub-tenth interest says so
rather than "nothing is resting"; and the payload never carries a `verdict`
key or a key starting with `ev` (ADR 0046).

What they do not establish: anything about the RFQ/Take-It path itself (out
of this lane's scope), or about a screenshot upload (Joe's own answer put
that second, #166). Nor a captured fixture for `GET /markets?event_ticker=`
against a real KXMVE event -- none exists in `tests/fixtures/` at the time
this was written (see `TestEventShapedLinks`'s own note), so that shape is
asserted from `KalshiRestClient.markets_for_event`'s own documented envelope
and a captured PER-MARKET object (`combo_priced_markets.json`) is reused
inside it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend import bets
from backend import combo_rfq
from backend import parlay_check
from backend.core.ladder import UNUSABLE_REASONS, joint_for
from backend.parlays import (
    LookupRefused,
    candidate_pool,
    end_of_desk_day_ms,
    ladder_candidates,
)
from backend.store import db as store
from backend.store.db import now_ms

FIXTURES = Path(__file__).parent / "fixtures"
CAPTURED = json.loads(
    (FIXTURES / "combo_lookup_response.json").read_text(encoding="utf-8")
)
COMBO_PRICED_MARKETS = json.loads(
    (FIXTURES / "combo_priced_markets.json").read_text(encoding="utf-8")
)

MAX_ODDS_AGE_MS = 6 * 60 * 60 * 1000

# A book with a resting NO bid at 70.0c -> derived YES ask = 30.0c.
PRICED_BOOK = {"no_dollars": [["0.7000", "10.00"]], "yes_dollars": []}
EMPTY_BOOK = {"no_dollars": [], "yes_dollars": []}
# A NO level priced finer than a tenth of a cent: real interest, but not one
# `_parse_price` can carry as a tenth -- `OrderBook.has_unpriced_interest`
# reads exactly this.
SUB_TENTH_BOOK = {"no_dollars": [["0.0038", "500.00"]], "yes_dollars": []}


class FakeApi:
    """Stands in for the shared `KalshiRestClient`. Records every call so a
    refusal that must reach the venue never can be told apart from one that
    silently did.

    Two GET shapes are distinguished by path/params, the same way the real
    client's callers differ: `GET /markets/{ticker}` (a bare-ticker read) and
    `GET /markets?event_ticker=...` (an event's markets list, used only when
    the pasted text names an event, never a market, directly).
    """

    def __init__(self, *, market_payload=None, event_markets_payload=None,
                 book_payload=None, market_error=None,
                 event_markets_error=None, book_error=None):
        self.calls: list[tuple] = []
        self.market_payload = market_payload
        self.event_markets_payload = event_markets_payload
        self.book_payload = book_payload if book_payload is not None else PRICED_BOOK
        self.market_error = market_error
        self.event_markets_error = event_markets_error
        self.book_error = book_error

    async def get(self, path, **params):
        self.calls.append((path, params))
        if path == "/markets" and "event_ticker" in params:
            if self.event_markets_error is not None:
                raise self.event_markets_error
            return self.event_markets_payload
        if self.market_error is not None:
            raise self.market_error
        return self.market_payload

    async def orderbook(self, ticker, depth=10):
        self.calls.append(("orderbook", ticker))
        if self.book_error is not None:
            raise self.book_error
        return self.book_payload


def _market_payload(legs: list[dict], *,
                     collection="KXMVECROSSCATEGORY-SHARD1-R",
                     exchange_index=1, status="active") -> dict:
    """The singular `GET /markets/{ticker}` envelope, `{"market": {...}}`."""
    return {
        "market": {
            "mve_collection_ticker": collection,
            "mve_selected_legs": legs,
            "exchange_index": exchange_index,
            "status": status,
        }
    }


def _bare_market(legs: list[dict], *, ticker,
                  collection="KXMVECROSSCATEGORY-SHARD1-R",
                  exchange_index=1, status="active") -> dict:
    """One item of a `GET /markets?event_ticker=` list -- BARE, no `market`
    envelope, the same shape `combo_priced_markets.json` captures."""
    return {
        "ticker": ticker,
        "mve_collection_ticker": collection,
        "mve_selected_legs": legs,
        "exchange_index": exchange_index,
        "status": status,
    }


def _event_markets_payload(markets: list[dict]) -> dict:
    return {"markets": markets, "cursor": ""}


def _mk_ticker(tag: str, *, shard: str = "SHARD1") -> str:
    """A syntactically MARKET-shaped test ticker.

    A real Kalshi combo ticker ends `-S<hex>-<hex>` (module docstring's
    round-2 finding), so a fabricated test ticker needs a real-looking tail
    too -- otherwise `_classify_token` reads it as `event` or `series`
    instead of `market`, and every test using it would silently be
    exercising the wrong branch. `tag` must be hex digits only (0-9A-F).
    """
    return f"KXMVECROSSCATEGORY0-{shard}-S2026{tag}0-{tag}1"


def seed_game(conn, *, game, team, other, p, computed_ms, commence_ms=None):
    """One buyable moneyline leg (`team` to win) with a fresh consensus.

    Copied from `tests/test_parlay_lookup.py`'s own helper -- the seed a
    candidate-pool test over this schema always needs, not a second
    invention of it. `event_links.league` carries Kalshi's own competition
    string ('Pro Baseball'), not an odds-feed sport key, for the same reason
    that file's copy states.
    """
    event_ticker = f"KXMLBGAME-{game}"
    ticker = f"{event_ticker}-{team[:6].upper().replace(' ', '')}"
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events (event_ticker, title, "
        "first_seen_ms, last_seen_ms) VALUES (?, ?, 0, 0)",
        (event_ticker, f"{other} at {team}"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, title, "
        "yes_side_team, market_type, status, first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, ?, ?, 'moneyline', 'active', 0, 0)",
        (ticker, event_ticker, f"{team} to win", team),
    )
    conn.execute(
        "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, "
        "odds_event_id, league, method, commence_skew_ms, linked_ms) "
        "VALUES (?, ?, 'Pro Baseball', 'exact_alias_pair', 0, 0)",
        (event_ticker, game),
    )
    link_id = conn.execute(
        "SELECT id FROM event_links WHERE kalshi_event_ticker = ? "
        "AND odds_event_id = ?",
        (event_ticker, game),
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
        "commence_ms, home_team, away_team, bookmaker, market, outcome_name, "
        "price_decimal) VALUES (?, 'baseball_mlb', ?, ?, ?, ?, 'pinnacle', "
        "'h2h', ?, 1.6)",
        (computed_ms, game,
         commence_ms if commence_ms is not None
         else min(now_ms() + 3_600_000, end_of_desk_day_ms(now_ms()) - 60_000),
         team, other, team),
    )
    for outcome, prob in ((team, p), (other, 1 - p - 0.02)):
        conn.execute(
            "INSERT INTO fair_prices (computed_ms, link_id, market, "
            "outcome_name, p_multiplicative, p_additive, p_power, p_shin, "
            "p_conservative, book_count, books_used, anchored_on_sharp, "
            "oldest_book_age_ms) "
            "VALUES (?, ?, 'h2h', ?, ?, ?, ?, ?, ?, 3, '[]', 1, 5000)",
            (computed_ms, link_id, outcome,
             prob + 0.02, prob + 0.01, prob + 0.015, prob + 0.005, prob),
        )
    return ticker, event_ticker


def _two_leg_combo(conn, *, game_a, game_b, ticker, exchange_index=1,
                    status="active"):
    """Seeds two fresh, priceable legs and returns
    `(ticker, api_market_payload, t1, t2)` ready for `check_parlay_text`."""
    base = now_ms() - 30_000
    t1, e1 = seed_game(conn, game=f"{game_a}", team=f"Team {game_a}A",
                        other=f"Team {game_a}B", p=0.70, computed_ms=base)
    t2, e2 = seed_game(conn, game=f"{game_b}", team=f"Team {game_b}A",
                        other=f"Team {game_b}B", p=0.55, computed_ms=base)
    conn.commit()
    legs = [
        {"event_ticker": e1, "market_ticker": t1, "side": "yes"},
        {"event_ticker": e2, "market_ticker": t2, "side": "yes"},
    ]
    payload = _market_payload(
        legs, exchange_index=exchange_index, status=status
    )
    return ticker, payload, t1, t2


@pytest.fixture
def conn(tmp_path):
    path = tmp_path / "check.db"
    c = store.init_db(path)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Link/ticker parsing -- round-2 finding
# ---------------------------------------------------------------------------

#: The two measured real shapes.
REAL_URL = (
    "https://kalshi.com/markets/kxmvecrosscategory/mve-cross-category/"
    "kxmvecrosscategory-s2026338240a5999"
)
REAL_MARKET_TICKER = "KXMVECROSSCATEGORY0-SHARD1-S2026B3D8BDECEA6-930882E712B"


class TestMatchTicker:
    def test_the_real_url_resolves_to_its_event_not_its_series(self):
        assert parlay_check._match_ticker(REAL_URL) == (
            "event", "KXMVECROSSCATEGORY-S2026338240A5999"
        )

    def test_a_market_shaped_token_is_preferred_over_an_event_shaped_one(self):
        text = f"{REAL_URL} or maybe {REAL_MARKET_TICKER}"
        assert parlay_check._match_ticker(text) == ("market", REAL_MARKET_TICKER)

    def test_a_series_only_token_is_never_looked_up(self):
        assert parlay_check._match_ticker("kxmvecrosscategory") == (
            "series", "KXMVECROSSCATEGORY"
        )

    def test_no_token_at_all(self):
        assert parlay_check._match_ticker("nothing to see here") is None

    def test_trailing_punctuation_is_stripped(self):
        assert parlay_check._match_ticker(
            f"check this: {REAL_MARKET_TICKER}."
        ) == ("market", REAL_MARKET_TICKER)
        assert parlay_check._match_ticker(
            f"{REAL_MARKET_TICKER}__"
        ) == ("market", REAL_MARKET_TICKER)
        assert parlay_check._match_ticker(
            f"{REAL_MARKET_TICKER}--"
        ) == ("market", REAL_MARKET_TICKER)

    def test_extract_ticker_only_answers_for_a_market_shaped_token(self):
        # The legacy single-ticker helper: `None` on an event or series
        # match, since neither IS a market ticker.
        assert parlay_check.extract_ticker(REAL_MARKET_TICKER) == (
            REAL_MARKET_TICKER
        )
        assert parlay_check.extract_ticker(REAL_URL) is None
        assert parlay_check.extract_ticker("kxmvecrosscategory") is None
        assert parlay_check.extract_ticker("nothing here") is None


class TestSeriesOnlyRefusal:
    async def test_refuses_before_any_venue_call_and_writes_no_row(self, conn):
        api = FakeApi()
        with pytest.raises(LookupRefused) as excinfo:
            await parlay_check.check_parlay_text(
                conn, text="kxmvecrosscategory", now_ms=now_ms(), api=api,
                max_odds_age_ms=MAX_ODDS_AGE_MS,
            )
        assert excinfo.value.status_code == 422
        assert "combination" in excinfo.value.detail
        assert api.calls == []
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM parlay_lookups"
        ).fetchone()["n"]
        assert count == 0


class TestNoTickerInTheText:
    async def test_refuses_before_any_venue_call_and_writes_no_row(self, conn):
        api = FakeApi()
        with pytest.raises(LookupRefused) as excinfo:
            await parlay_check.check_parlay_text(
                conn, text="just some words, no ticker here",
                now_ms=now_ms(), api=api,
                max_odds_age_ms=MAX_ODDS_AGE_MS,
            )
        assert excinfo.value.status_code == 422
        assert api.calls == []
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM parlay_lookups"
        ).fetchone()["n"]
        assert count == 0


class TestEventShapedLinks:
    """The real URL shape: names the event, never the market. No committed
    fixture carries the exact `GET /markets?event_ticker=` envelope for a
    KXMVE event, so these tests build one from
    `KalshiRestClient.markets_for_event`'s own documented shape
    (`{"markets": [...], "cursor": ...}`), with one CAPTURED per-market
    object (`combo_priced_markets.json`) inside it."""

    def _one_captured_market(self, **overrides):
        market = dict(COMBO_PRICED_MARKETS["combos"][0])
        market.update(overrides)
        return market

    async def test_an_event_with_exactly_one_market_resolves_to_it(self, conn):
        base = now_ms() - 30_000
        t1, e1 = seed_game(conn, game="ev-a", team="Team EvA", other="Team EvB",
                            p=0.6, computed_ms=base)
        t2, e2 = seed_game(conn, game="ev-b", team="Team EvC", other="Team EvD",
                            p=0.55, computed_ms=base)
        conn.commit()
        market_ticker = "KXMVECROSSCATEGORY0-SHARD1-S2026AAAAAAAAAAA-BBBBBBBBBBB"
        legs = [
            {"event_ticker": e1, "market_ticker": t1, "side": "yes"},
            {"event_ticker": e2, "market_ticker": t2, "side": "yes"},
        ]
        market = self._one_captured_market(
            ticker=market_ticker, mve_selected_legs=legs,
            exchange_index=1, status="active",
        )
        api = FakeApi(
            event_markets_payload=_event_markets_payload([market]),
            book_payload=PRICED_BOOK,
        )
        result = await parlay_check.check_parlay_text(
            conn, text=REAL_URL, now_ms=now_ms(), api=api,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert result["minted_market_ticker"] == market_ticker
        assert result["status"] == "priced"
        assert ("/markets", {"event_ticker": "KXMVECROSSCATEGORY-S2026338240A5999"}) in api.calls

    async def test_an_event_with_two_markets_refuses(self, conn):
        market_a = self._one_captured_market(ticker="AAA")
        market_b = self._one_captured_market(ticker="BBB")
        api = FakeApi(
            event_markets_payload=_event_markets_payload([market_a, market_b]),
        )
        with pytest.raises(LookupRefused) as excinfo:
            await parlay_check.check_parlay_text(
                conn, text=REAL_URL, now_ms=now_ms(), api=api,
                max_odds_age_ms=MAX_ODDS_AGE_MS,
            )
        assert excinfo.value.status_code == 422
        assert "combination" in excinfo.value.detail
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM parlay_lookups"
        ).fetchone()["n"]
        assert count == 0

    async def test_an_event_with_zero_markets_refuses(self, conn):
        api = FakeApi(event_markets_payload=_event_markets_payload([]))
        with pytest.raises(LookupRefused) as excinfo:
            await parlay_check.check_parlay_text(
                conn, text=REAL_URL, now_ms=now_ms(), api=api,
                max_odds_age_ms=MAX_ODDS_AGE_MS,
            )
        assert excinfo.value.status_code == 422
        assert "combination" in excinfo.value.detail


class TestEveryLegInTheSyntheticPool:
    async def test_rows_and_prices_a_two_leg_combo(self, conn):
        ticker, payload, t1, t2 = _two_leg_combo(
            conn, game_a="a", game_b="b",
            ticker=_mk_ticker("AB01"),
        )
        api = FakeApi(market_payload=payload, book_payload=PRICED_BOOK)
        now = now_ms()
        result = await parlay_check.check_parlay_text(
            conn, text=f"my friend built this: {ticker}", now_ms=now,
            api=api, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )

        assert result["status"] == "priced"
        assert result["minted_market_ticker"] == ticker
        assert result["rfq_available"] is True
        assert result["rfq_unavailable_reason"] is None
        assert result["fair"]["no_joint_reason"] is None
        assert result["fair"]["conservative"] is not None

        row = conn.execute(
            "SELECT * FROM parlay_lookups WHERE minted_market_ticker = ?",
            (ticker,),
        ).fetchone()
        assert row["card_key"] == "checked"
        assert row["status"] == "priced"

        # The independent check: the SAME candidate pool, filtered to these
        # two tickers, fed through the SAME `joint_for` the module calls.
        pool = candidate_pool(conn, now_ms=now, max_odds_age_ms=MAX_ODDS_AGE_MS)
        pool = pool._replace(eligible_events=None)
        candidates, _ = ladder_candidates(
            conn, now_ms=now, max_odds_age_ms=MAX_ODDS_AGE_MS,
            horizon=parlay_check.WIDEST_HORIZON, pool=pool,
        )
        matched = [
            c for c in candidates
            if c.kalshi_market_ticker in (t1, t2) and c.side == "yes"
        ]
        assert len(matched) == 2
        expected = joint_for(matched)
        assert row["fair_joint_conservative"] == pytest.approx(
            expected.conservative
        )
        assert result["fair"]["conservative"] == pytest.approx(
            expected.conservative
        )

    async def test_a_labelled_leg_carries_the_title_on_file(self, conn):
        ticker, payload, t1, t2 = _two_leg_combo(
            conn, game_a="c", game_b="d",
            ticker=_mk_ticker("CD02"),
        )
        api = FakeApi(market_payload=payload, book_payload=PRICED_BOOK)
        result = await parlay_check.check_parlay_text(
            conn, text=ticker, now_ms=now_ms(), api=api,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        labels = {leg["market_ticker"]: leg["label"] for leg in result["legs"]}
        assert labels[t1] == "Team cA to win"


class TestRfqAvailability:
    async def test_true_on_shard_one_and_active(self, conn):
        ticker, payload, _, _ = _two_leg_combo(
            conn, game_a="m1", game_b="m2",
            ticker=_mk_ticker("1101"),
            exchange_index=1, status="active",
        )
        api = FakeApi(market_payload=payload, book_payload=PRICED_BOOK)
        result = await parlay_check.check_parlay_text(
            conn, text=ticker, now_ms=now_ms(), api=api,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert result["rfq_available"] is True
        assert result["rfq_unavailable_reason"] is None

    async def test_false_on_the_wrong_shard(self, conn):
        ticker, payload, _, _ = _two_leg_combo(
            conn, game_a="m3", game_b="m4",
            ticker=_mk_ticker("3303", shard="SHARD0"),
            exchange_index=0, status="active",
        )
        api = FakeApi(market_payload=payload, book_payload=PRICED_BOOK)
        result = await parlay_check.check_parlay_text(
            conn, text=ticker, now_ms=now_ms(), api=api,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert result["rfq_available"] is False
        assert "shard" in result["rfq_unavailable_reason"]
        # Legs and chances are still served -- only asking is unavailable.
        assert len(result["legs"]) == 2

    async def test_false_when_no_longer_trading(self, conn):
        ticker, payload, _, _ = _two_leg_combo(
            conn, game_a="m5", game_b="m6",
            ticker=_mk_ticker("5505"),
            exchange_index=1, status="closed",
        )
        api = FakeApi(market_payload=payload, book_payload=PRICED_BOOK)
        result = await parlay_check.check_parlay_text(
            conn, text=ticker, now_ms=now_ms(), api=api,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert result["rfq_available"] is False
        assert result["rfq_unavailable_reason"] == "this combination is no longer trading"
        assert len(result["legs"]) == 2

    async def test_shard_reason_wins_when_both_fail(self, conn):
        ticker, payload, _, _ = _two_leg_combo(
            conn, game_a="m7", game_b="m8",
            ticker=_mk_ticker("7707", shard="SHARD0"),
            exchange_index=0, status="closed",
        )
        api = FakeApi(market_payload=payload, book_payload=PRICED_BOOK)
        result = await parlay_check.check_parlay_text(
            conn, text=ticker, now_ms=now_ms(), api=api,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert result["rfq_available"] is False
        assert "shard" in result["rfq_unavailable_reason"]

    @pytest.mark.parametrize("book", [EMPTY_BOOK, SUB_TENTH_BOOK])
    async def test_an_empty_book_never_says_ask_where_asking_is_withheld(
        self, conn, book
    ):
        """First live check, 2026-09-26: a finalized combination's words
        ended "so ask instead" while the screen withheld the Ask button."""
        ticker, payload, _, _ = _two_leg_combo(
            conn, game_a="m9", game_b="m10",
            ticker=_mk_ticker("9909"),
            exchange_index=1, status="finalized",
        )
        api = FakeApi(market_payload=payload, book_payload=book)
        result = await parlay_check.check_parlay_text(
            conn, text=ticker, now_ms=now_ms(), api=api,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert result["status"] == "book_empty"
        assert "ask instead" not in result["words"].lower()
        assert "no longer trading" in result["words"]


class TestLegMissingFields:
    async def test_missing_market_ticker_refuses_before_any_row(self, conn):
        ticker = _mk_ticker("0A0A")
        legs = [{"event_ticker": "E1", "side": "yes"}]
        api = FakeApi(market_payload=_market_payload(legs))
        with pytest.raises(LookupRefused) as excinfo:
            await parlay_check.check_parlay_text(
                conn, text=ticker, now_ms=now_ms(), api=api,
                max_odds_age_ms=MAX_ODDS_AGE_MS,
            )
        assert excinfo.value.status_code == 422
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM parlay_lookups"
        ).fetchone()["n"]
        assert count == 0

    async def test_missing_event_ticker_refuses_before_any_row(self, conn):
        ticker = _mk_ticker("0B0B")
        legs = [{"market_ticker": "M1", "side": "yes"}]
        api = FakeApi(market_payload=_market_payload(legs))
        with pytest.raises(LookupRefused) as excinfo:
            await parlay_check.check_parlay_text(
                conn, text=ticker, now_ms=now_ms(), api=api,
                max_odds_age_ms=MAX_ODDS_AGE_MS,
            )
        assert excinfo.value.status_code == 422
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM parlay_lookups"
        ).fetchone()["n"]
        assert count == 0


class TestOneLegMissingFromThePool:
    async def test_the_missing_leg_reads_words_never_zero_or_a_bare_code(
        self, conn
    ):
        base = now_ms() - 30_000
        t1, e1 = seed_game(conn, game="game-e", team="Team Iota",
                            other="Team Kappa", p=0.65, computed_ms=base)
        conn.commit()
        ticker = _mk_ticker("EF03")
        missing_ticker = "KXMLBGAME-nonexistent-XXX"
        legs = [
            {"event_ticker": e1, "market_ticker": t1, "side": "yes"},
            {"event_ticker": "KXMLBGAME-nonexistent", "market_ticker":
             missing_ticker, "side": "yes"},
        ]
        api = FakeApi(market_payload=_market_payload(legs), book_payload=PRICED_BOOK)
        result = await parlay_check.check_parlay_text(
            conn, text=ticker, now_ms=now_ms(), api=api,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        by_ticker = {leg["market_ticker"]: leg for leg in result["legs"]}
        missing = by_ticker[missing_ticker]
        assert missing["chance"] is None
        assert missing["unknown_reason_code"] is not None
        # WORDS, not the bare code -- the round-2 fix.
        assert missing["unknown_reason"] != missing["unknown_reason_code"]
        assert missing["unknown_reason_code"] not in missing["unknown_reason"]
        assert by_ticker[t1]["chance"] is not None

        assert result["fair"]["conservative"] is None
        assert result["fair"]["no_joint_reason"] == "unknown_leg"

        row = conn.execute(
            "SELECT fair_joint_conservative FROM parlay_lookups "
            "WHERE minted_market_ticker = ?", (ticker,),
        ).fetchone()
        assert row["fair_joint_conservative"] is None

    def test_mutating_the_missing_leg_branch_to_zero_turns_this_red(self, conn):
        """Not a call into the module -- a static guard against the exact
        defect CLAUDE.md's "unreadable resolves to None, never 0" rule
        exists to catch. If `_missing_leg_reason`'s caller is ever edited so
        the `candidate is None` branch assigns `chance = 0.0`, this fails,
        and `test_the_missing_leg_reads_words_never_zero_or_a_bare_code`
        above would too -- this one just says so without needing the async
        plumbing."""
        source = Path(parlay_check.__file__).read_text(encoding="utf-8")
        branch = source[source.index("if candidate is None:"):]
        branch = branch[: branch.index("else:")]
        assert "chance = None" in branch
        assert "chance = 0.0" not in branch
        assert "chance = 0\n" not in branch


class TestReasonWords:
    def test_missing_leg_codes_map_to_sentences(self):
        for code in (
            parlay_check.REASON_GAME_STARTED,
            parlay_check.REASON_OUTSIDE_WINDOW,
            parlay_check.REASON_NOT_SERVED,
        ):
            words = parlay_check._reason_words(code)
            assert words != code
            assert isinstance(words, str) and words

    def test_unusable_reason_codes_map_through_the_shared_vocabulary(self):
        for code, words in UNUSABLE_REASONS.items():
            assert parlay_check._reason_words(code) == words

    def test_none_stays_none(self):
        assert parlay_check._reason_words(None) is None


class TestTwoLegsOnOneGame:
    async def test_same_odds_event_id_refuses_the_joint(self, conn):
        base = now_ms() - 30_000
        # Both calls share `game="game-f"`, so both land on the SAME
        # `event_links` row and the SAME `odds_event_id` -- the fact
        # `joint_for`'s same-game guard actually keys on -- while each still
        # gets its own buyable Kalshi market and its own ticker.
        t1, e1 = seed_game(conn, game="game-f", team="Team Lambda",
                            other="Team Mu", p=0.6, computed_ms=base)
        t2, e2 = seed_game(conn, game="game-f", team="Team Nu",
                            other="Team Xi", p=0.55, computed_ms=base)
        assert e1 == e2
        conn.commit()
        ticker = _mk_ticker("AC04")
        legs = [
            {"event_ticker": e1, "market_ticker": t1, "side": "yes"},
            {"event_ticker": e2, "market_ticker": t2, "side": "yes"},
        ]
        api = FakeApi(market_payload=_market_payload(legs), book_payload=PRICED_BOOK)
        result = await parlay_check.check_parlay_text(
            conn, text=ticker, now_ms=now_ms(), api=api,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert result["fair"]["conservative"] is None
        assert result["fair"]["no_joint_reason"] == "same_game"
        by_ticker = {leg["market_ticker"]: leg for leg in result["legs"]}
        assert by_ticker[t1]["chance"] is not None
        assert by_ticker[t2]["chance"] is not None


class TestTheRowReachesBetsAndComboRfq:
    async def test_chance_when_priced_and_recorded_lookup_both_read_it(
        self, conn
    ):
        base = now_ms() - 30_000
        t1, e1 = seed_game(conn, game="game-g", team="Team Omicron",
                            other="Team Pi", p=0.7, computed_ms=base)
        t2, e2 = seed_game(conn, game="game-h", team="Team Rho",
                            other="Team Sigma", p=0.6, computed_ms=base)
        conn.commit()
        ticker = _mk_ticker("AD05")
        legs = [
            {"event_ticker": e1, "market_ticker": t1, "side": "yes"},
            {"event_ticker": e2, "market_ticker": t2, "side": "yes"},
        ]
        api = FakeApi(market_payload=_market_payload(legs), book_payload=PRICED_BOOK)
        requested_ms = now_ms()
        result = await parlay_check.check_parlay_text(
            conn, text=ticker, now_ms=requested_ms, api=api,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert result["status"] == "priced"

        # `combo_rfq._recorded_lookup` -- the RFQ path's own reader of
        # exactly this table.
        recorded = combo_rfq._recorded_lookup(conn, ticker)
        assert recorded["card_key"] == "checked"
        assert recorded["fair_joint_conservative"] == pytest.approx(
            result["fair"]["conservative"]
        )

        # `bets._chance_when_priced_by_ticker` -- anchored on a fill AFTER
        # the check, the same shape #163 reads for a real combo fill.
        fill_ms = requested_ms + 5_000
        conn.execute(
            "INSERT INTO fills (ticker, filled_ms, count, price_tenths, "
            "is_taker, fee_predicted, fee_model_used, source) "
            "VALUES (?, ?, 2.0, 300, 1, 0.0, 'model_a_deci', 'venue_hand')",
            (ticker, fill_ms),
        )
        conn.commit()
        readings = bets._chance_when_priced_by_ticker(conn, [ticker])
        assert readings[ticker]["chance"] == pytest.approx(
            result["fair"]["conservative"]
        )


class TestNoVerdictAndNoEvKey:
    async def test_the_payload_carries_neither_at_any_depth(self, conn):
        ticker, payload, _, _ = _two_leg_combo(
            conn, game_a="i", game_b="j",
            ticker=_mk_ticker("AE06"),
        )
        api = FakeApi(market_payload=payload, book_payload=EMPTY_BOOK)
        result = await parlay_check.check_parlay_text(
            conn, text=ticker, now_ms=now_ms(), api=api,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert result["status"] == "book_empty"

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    assert key != "verdict", key
                    assert not key.startswith("ev"), key
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(result)


class TestBookEmptyWords:
    async def test_never_claims_kalshi_created_the_market(self, conn):
        ticker, payload, _, _ = _two_leg_combo(
            conn, game_a="be1", game_b="be2",
            ticker=_mk_ticker("BE01"),
        )
        api = FakeApi(market_payload=payload, book_payload=EMPTY_BOOK)
        result = await parlay_check.check_parlay_text(
            conn, text=ticker, now_ms=now_ms(), api=api,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert result["status"] == "book_empty"
        assert "created the market" not in result["words"]
        assert "Nothing is resting" in result["words"]

    async def test_sub_tenth_interest_says_so_and_records_the_detail(
        self, conn
    ):
        ticker, payload, _, _ = _two_leg_combo(
            conn, game_a="be3", game_b="be4",
            ticker=_mk_ticker("BE03"),
        )
        api = FakeApi(market_payload=payload, book_payload=SUB_TENTH_BOOK)
        result = await parlay_check.check_parlay_text(
            conn, text=ticker, now_ms=now_ms(), api=api,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert result["status"] == "book_empty"
        assert "finer than a tenth of a cent" in result["words"]
        assert "created the market" not in result["words"]
        assert "Nothing is resting" not in result["words"]

        row = conn.execute(
            "SELECT error FROM parlay_lookups WHERE minted_market_ticker = ?",
            (ticker,),
        ).fetchone()
        assert row["error"] is not None
        assert "no_levels=" in row["error"]


class TestBookReadFailure:
    async def test_records_an_error_row_with_the_ticker_then_502(self, conn):
        ticker, payload, _, _ = _two_leg_combo(
            conn, game_a="k", game_b="l",
            ticker=_mk_ticker("AF07"),
        )
        api = FakeApi(market_payload=payload, book_error=RuntimeError("timeout"))
        with pytest.raises(LookupRefused) as excinfo:
            await parlay_check.check_parlay_text(
                conn, text=ticker, now_ms=now_ms(), api=api,
                max_odds_age_ms=MAX_ODDS_AGE_MS,
            )
        assert excinfo.value.status_code == 502
        row = conn.execute(
            "SELECT status, minted_market_ticker FROM parlay_lookups "
            "WHERE minted_market_ticker = ?", (ticker,),
        ).fetchone()
        assert row["status"] == "error"
        assert row["minted_market_ticker"] == ticker


class TestALegWithNoReadableSideIsRefused:
    async def test_refused_by_name_no_row(self, conn):
        ticker = _mk_ticker("B008")
        legs = [
            {"event_ticker": "E1", "market_ticker": "M1", "side": "maybe"},
        ]
        api = FakeApi(market_payload=_market_payload(legs))
        with pytest.raises(LookupRefused) as excinfo:
            await parlay_check.check_parlay_text(
                conn, text=ticker, now_ms=now_ms(), api=api,
                max_odds_age_ms=MAX_ODDS_AGE_MS,
            )
        assert excinfo.value.status_code == 422
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM parlay_lookups"
        ).fetchone()["n"]
        assert count == 0
