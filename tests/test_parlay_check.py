"""`POST /api/parlays/check` -- reading a friend's parlay (#166, #165).

What these tests establish: the first `KXMVE...` token in pasted text
identifies the ticker (a bare token or one buried in a kalshi.com-style URL),
and no token at all refuses before any venue call and before any row; the
combination's legs come off the venue's own `GET /markets/{ticker}`
(`combo_lookup_response.json`, the same fixture `hedge.adopt_venue_combo`
reads); each leg's chance is looked up in the SAME candidate pool the ladder
itself scans, so a leg the pool cannot answer for reads `chance: null` with a
named reason and never `0.0`; the joint is refused (not computed) when a leg
is unknown or when two legs share one game; the row this desk writes
(`card_key = "outside"`) is exactly what `bets._chance_when_priced_by_ticker`
and `combo_rfq._recorded_lookup` already know how to read; and the payload
never carries a `verdict` key or a key starting with `ev` (ADR 0046).

What they do not establish: anything about the RFQ/Take-It path itself (out
of this lane's scope), or about a screenshot upload (Joe's own answer put
that second, #166).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend import bets
from backend import combo_rfq
from backend import parlay_check
from backend.core.ladder import joint_for
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

MAX_ODDS_AGE_MS = 6 * 60 * 60 * 1000

# A book with a resting NO bid at 70.0c -> derived YES ask = 30.0c.
PRICED_BOOK = {"no_dollars": [["0.7000", "10.00"]], "yes_dollars": []}
EMPTY_BOOK = {"no_dollars": [], "yes_dollars": []}


class FakeApi:
    """Stands in for the shared `KalshiRestClient`. Records every call so a
    refusal that must reach the venue never can be told apart from one that
    silently did."""

    def __init__(self, *, market_payload=None, book_payload=None,
                 market_error=None, book_error=None):
        self.calls: list[str] = []
        self.market_payload = market_payload
        self.book_payload = book_payload if book_payload is not None else PRICED_BOOK
        self.market_error = market_error
        self.book_error = book_error

    async def get(self, path, **params):
        self.calls.append(f"get:{path}")
        if self.market_error is not None:
            raise self.market_error
        return self.market_payload

    async def orderbook(self, ticker, depth=10):
        self.calls.append(f"orderbook:{ticker}")
        if self.book_error is not None:
            raise self.book_error
        return self.book_payload


def _market_payload(legs: list[dict], *,
                     collection="KXMVECROSSCATEGORY-SHARD1-R") -> dict:
    return {
        "market": {
            "mve_collection_ticker": collection,
            "mve_selected_legs": legs,
        }
    }


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


@pytest.fixture
def conn(tmp_path):
    path = tmp_path / "check.db"
    c = store.init_db(path)
    yield c
    c.close()


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

    def test_a_kalshi_com_style_url_is_parsed_to_its_ticker(self):
        text = (
            "check this out: https://kalshi.com/markets/"
            "kxmvecrosscategory0-shard1-s2026b3d8bdecea6?utm_source=sms"
        )
        assert parlay_check.extract_ticker(text) == (
            "KXMVECROSSCATEGORY0-SHARD1-S2026B3D8BDECEA6"
        )

    def test_a_bare_ticker_is_parsed_too(self):
        assert parlay_check.extract_ticker(
            "  KXMVECROSSCATEGORY0-SHARD1-ABC  "
        ) == "KXMVECROSSCATEGORY0-SHARD1-ABC"


class TestEveryLegInTheSyntheticPool:
    async def test_rows_and_prices_a_two_leg_combo(self, conn):
        base = now_ms() - 30_000
        t1, e1 = seed_game(conn, game="game-a", team="Team Alpha",
                            other="Team Beta", p=0.70, computed_ms=base)
        t2, e2 = seed_game(conn, game="game-b", team="Team Gamma",
                            other="Team Delta", p=0.55, computed_ms=base)
        conn.commit()

        ticker = "KXMVECROSSCATEGORY0-SHARD1-TESTABAB"
        legs = [
            {"event_ticker": e1, "market_ticker": t1, "side": "yes"},
            {"event_ticker": e2, "market_ticker": t2, "side": "yes"},
        ]
        api = FakeApi(
            market_payload=_market_payload(legs), book_payload=PRICED_BOOK
        )
        now = now_ms()
        result = await parlay_check.check_parlay_text(
            conn, text=f"my friend built this: {ticker}", now_ms=now,
            api=api, max_odds_age_ms=MAX_ODDS_AGE_MS,
        )

        assert result["status"] == "priced"
        assert result["minted_market_ticker"] == ticker
        assert result["fair"]["no_joint_reason"] is None
        assert result["fair"]["conservative"] is not None

        row = conn.execute(
            "SELECT * FROM parlay_lookups WHERE minted_market_ticker = ?",
            (ticker,),
        ).fetchone()
        assert row["card_key"] == "outside"
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
        base = now_ms() - 30_000
        t1, e1 = seed_game(conn, game="game-c", team="Team Epsilon",
                            other="Team Zeta", p=0.6, computed_ms=base)
        t2, e2 = seed_game(conn, game="game-d", team="Team Eta",
                            other="Team Theta", p=0.6, computed_ms=base)
        conn.commit()
        ticker = "KXMVECROSSCATEGORY0-SHARD1-TESTCDCD"
        legs = [
            {"event_ticker": e1, "market_ticker": t1, "side": "yes"},
            {"event_ticker": e2, "market_ticker": t2, "side": "yes"},
        ]
        api = FakeApi(market_payload=_market_payload(legs), book_payload=PRICED_BOOK)
        result = await parlay_check.check_parlay_text(
            conn, text=ticker, now_ms=now_ms(), api=api,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        labels = {leg["market_ticker"]: leg["label"] for leg in result["legs"]}
        assert labels[t1] == "Team Epsilon to win"


class TestOneLegMissingFromThePool:
    async def test_the_missing_leg_reads_null_never_zero(self, conn):
        base = now_ms() - 30_000
        t1, e1 = seed_game(conn, game="game-e", team="Team Iota",
                            other="Team Kappa", p=0.65, computed_ms=base)
        conn.commit()
        ticker = "KXMVECROSSCATEGORY0-SHARD1-TESTEFEF"
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
        assert by_ticker[missing_ticker]["chance"] is None
        assert by_ticker[missing_ticker]["unknown_reason"] is not None
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
        and `test_the_missing_leg_reads_null_never_zero` above would too --
        this one just says so without needing the async plumbing."""
        source = Path(parlay_check.__file__).read_text(encoding="utf-8")
        branch = source[source.index("if candidate is None:"):]
        branch = branch[: branch.index("else:")]
        assert "chance = None" in branch
        assert "chance = 0.0" not in branch
        assert "chance = 0\n" not in branch


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
        ticker = "KXMVECROSSCATEGORY0-SHARD1-TESTGHGH"
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
        ticker = "KXMVECROSSCATEGORY0-SHARD1-TESTIJIJ"
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
        assert recorded["card_key"] == "outside"
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
        base = now_ms() - 30_000
        t1, e1 = seed_game(conn, game="game-i", team="Team Tau",
                            other="Team Upsilon", p=0.7, computed_ms=base)
        t2, e2 = seed_game(conn, game="game-j", team="Team Phi",
                            other="Team Chi", p=0.6, computed_ms=base)
        conn.commit()
        ticker = "KXMVECROSSCATEGORY0-SHARD1-TESTKLKL"
        legs = [
            {"event_ticker": e1, "market_ticker": t1, "side": "yes"},
            {"event_ticker": e2, "market_ticker": t2, "side": "yes"},
        ]
        api = FakeApi(market_payload=_market_payload(legs), book_payload=EMPTY_BOOK)
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


class TestBookReadFailure:
    async def test_records_an_error_row_with_the_ticker_then_502(self, conn):
        base = now_ms() - 30_000
        t1, e1 = seed_game(conn, game="game-k", team="Team Psi",
                            other="Team Omega", p=0.6, computed_ms=base)
        t2, e2 = seed_game(conn, game="game-l", team="Team Alpha2",
                            other="Team Beta2", p=0.6, computed_ms=base)
        conn.commit()
        ticker = "KXMVECROSSCATEGORY0-SHARD1-TESTMNMN"
        legs = [
            {"event_ticker": e1, "market_ticker": t1, "side": "yes"},
            {"event_ticker": e2, "market_ticker": t2, "side": "yes"},
        ]
        api = FakeApi(
            market_payload=_market_payload(legs),
            book_error=RuntimeError("timeout"),
        )
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
        ticker = "KXMVECROSSCATEGORY0-SHARD1-TESTOPOP"
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
