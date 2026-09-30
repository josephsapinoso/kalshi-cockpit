"""The line-shopping hint (#245): same opinion, the cheaper way round.

What this establishes
---------------------
On a captured two-way pair, the hint fires when the opposite route is cheaper
after `core/fees.py`'s fee, shows both asks and the depth at each, and is
silent on a soccer or NHL ticker, when the two quotes' read times differ, when
the event has a third (Tie) market, and when the league is missing. Its copy
says it cuts what you pay and carries no edge or profit claim. No sort in the
slate route or the page reads it.

The pair is `tests/fixtures/markets_batch_by_ticker.json`: BUF and LAR from
ONE `GET /markets?tickers=` response (one read, so one read time), captured
2026-09-29. LAR YES asks 57c; the same opinion is NO on BUF at 56c (BUF's
YES bid is 44c). The books are built from that payload's own fields, using
the venue identity that a YES ask's size is the NO bid's size.

What it does not establish
--------------------------
- That either route fills at the shown price: depth is the best ask only.
- That Kalshi's NFL tie rule ("resolve to $0.50 for each team", in
  `tests/fixtures/events_nfl_preseason.json`) is applied as written.
- What a voided game pays: fair_A + fair_B need not sum to 1 there.
"""

from __future__ import annotations

import inspect
import re

import pytest

from conftest import load_fixture

from backend import line_shop
from backend.core.prices import dollars_to_tenths
from backend.config import StalenessConfig
from backend.line_shop import BookRead, compute_hint, hints_for_slate
from backend.store import db

NFL = "americanfootball_nfl"
READ_MS = 1_790_000_000_000


NOW_MS = READ_MS + 1_000
STALENESS = StalenessConfig()


def _hint(**kw):
    kw.setdefault("now_ms", NOW_MS)
    kw.setdefault("max_age_ms", STALENESS.max_kalshi_quote_age_s * 1000)
    return compute_hint(**kw)


def _markets():
    payload = load_fixture("markets_batch_by_ticker.json")
    return {m["ticker"]: m for m in payload["response"]["markets"]}


def _book(market, read_ms=READ_MS, team=None, ticker=None):
    """A BookRead from a captured market object. A YES ask's size is the NO
    bid's size (Kalshi publishes bids; the asks are the complements)."""
    return BookRead(
        ticker=ticker or market["ticker"],
        yes_bid_tenths=dollars_to_tenths(market["yes_bid_dollars"]),
        yes_bid_qty=float(market["yes_bid_size_fp"]),
        no_bid_tenths=dollars_to_tenths(market["no_bid_dollars"]),
        no_bid_qty=float(market["yes_ask_size_fp"]),
        read_ms=read_ms,
        team=team,
    )


@pytest.fixture()
def pair():
    m = _markets()
    return (
        _book(m["KXNFLGAME-26OCT12BUFLAR-LAR"], team="Los Angeles R"),
        _book(m["KXNFLGAME-26OCT12BUFLAR-BUF"], team="Buffalo"),
    )


class TestItFiresWhenTheOtherRouteIsCheaper:
    def test_yes_lar_at_57_is_beaten_by_no_buf_at_56(self, pair):
        lar, buf = pair
        hint = _hint(league=NFL, own=lar, own_side="yes", other=buf)
        assert hint is not None
        assert hint["cheaper"]["ticker"].endswith("-BUF")
        assert hint["cheaper"]["side"] == "no"
        assert hint["cheaper"]["ask_tenths"] == 560
        assert hint["current"]["side"] == "yes"
        assert hint["current"]["ask_tenths"] == 570

    def test_depth_is_shown_at_each_ask(self, pair):
        lar, buf = pair
        hint = _hint(league=NFL, own=lar, own_side="yes", other=buf)
        # NO BUF's ask is 1 - BUF's YES bid, sized by that bid; YES LAR's ask
        # is sized by LAR's NO bid (the captured yes_ask_size_fp).
        assert hint["cheaper"]["depth"] == 3.19
        assert hint["current"]["depth"] == 215.0
        assert "3.19 contracts at that ask" in hint["copy"]
        assert "215 at that ask" in hint["copy"]
        assert "56c" in hint["copy"] and "57c" in hint["copy"]

    def test_the_comparison_is_after_fees_not_raw_asks(self, pair, monkeypatch):
        """A fee that swallows the 1c gap must silence the hint: the test that
        the comparison goes through `calculate_fee` rather than the asks."""
        lar, buf = pair
        monkeypatch.setattr(
            line_shop,
            "calculate_fee",
            lambda price, contracts, **k: 0.0 if price == 570 else 5.0,
        )
        assert _hint(league=NFL, own=lar, own_side="yes", other=buf) is None

    def test_silent_when_this_row_is_already_the_cheaper_route(self, pair):
        lar, buf = pair
        # Row = NO BUF at 56c; the other route is YES LAR at 57c. Dearer.
        assert _hint(league=NFL, own=buf, own_side="no", other=lar) is None

    def test_silent_when_the_two_routes_cost_the_same(self, pair):
        """BUF YES (46c) vs NO LAR (46c) is the same price: no hint."""
        lar, buf = pair
        assert _hint(league=NFL, own=buf, own_side="yes", other=lar) is None

    def test_silent_when_a_side_has_no_price(self, pair):
        lar, buf = pair
        empty = BookRead(buf.ticker, None, None, buf.no_bid_tenths, buf.no_bid_qty, READ_MS)
        assert _hint(league=NFL, own=lar, own_side="yes", other=empty) is None
        nodepth = BookRead(buf.ticker, buf.yes_bid_tenths, 0.0, buf.no_bid_tenths, buf.no_bid_qty, READ_MS)
        assert _hint(league=NFL, own=lar, own_side="yes", other=nodepth) is None


class TestItNeverFiresOffItsLeagues:
    @pytest.mark.parametrize(
        "suffix,league",
        [
            ("KXEPLGAME-26OCT12BUFLAR", "soccer_epl"),
            ("KXEPLGAME-26OCT12BUFLAR", "Pro Soccer"),
            ("KXMLSGAME-26OCT12BUFLAR", None),
            ("KXNHLGAME-26OCT12BUFLAR", "icehockey_nhl"),
            ("KXNHLGAME-26OCT12BUFLAR", "Pro Hockey"),
        ],
    )
    def test_soccer_and_nhl_tickers_are_refused(self, pair, suffix, league):
        lar, buf = pair
        a = BookRead(f"{suffix}-LAR", *[getattr(lar, f) for f in ("yes_bid_tenths", "yes_bid_qty", "no_bid_tenths", "no_bid_qty", "read_ms")])
        b = BookRead(f"{suffix}-BUF", *[getattr(buf, f) for f in ("yes_bid_tenths", "yes_bid_qty", "no_bid_tenths", "no_bid_qty", "read_ms")])
        assert _hint(league=league, own=a, own_side="yes", other=b) is None

    @pytest.mark.parametrize("series", ["KXEPLGAME", "KXMLSGAME", "KXNHLGAME"])
    def test_a_soccer_or_nhl_ticker_is_refused_even_under_an_allowed_league(
        self, pair, series
    ):
        """The ticker gate is its own guard: a wrong league string on the row
        must not let a soccer or NHL ticker through."""
        lar, buf = pair
        a = BookRead(f"{series}-26OCT12BUFLAR-LAR", lar.yes_bid_tenths, lar.yes_bid_qty, lar.no_bid_tenths, lar.no_bid_qty, READ_MS)
        b = BookRead(f"{series}-26OCT12BUFLAR-BUF", buf.yes_bid_tenths, buf.yes_bid_qty, buf.no_bid_tenths, buf.no_bid_qty, READ_MS)
        assert _hint(league=NFL, own=a, own_side="yes", other=b) is None

    def test_an_allowed_ticker_with_an_nhl_or_missing_league_is_refused(self, pair):
        lar, buf = pair
        for league in ("icehockey_nhl", "Pro Hockey", "soccer_epl", "", None):
            assert _hint(league=league, own=lar, own_side="yes", other=buf) is None

    def test_every_allowed_league_fires_in_both_vocabularies(self, pair):
        lar, buf = pair
        for league in (NFL, "Pro Football", "americanfootball_ncaaf", "NCAA Football"):
            assert _hint(league=league, own=lar, own_side="yes", other=buf)

    def test_the_allowlists_are_exactly_the_five_leagues(self):
        assert line_shop.ALLOWED_SPORT_KEYS == {
            "baseball_mlb",
            "basketball_nba",
            "basketball_wnba",
            "americanfootball_ncaaf",
            "americanfootball_nfl",
        }
        assert not any("NHL" in s or "EPL" in s for s in line_shop.ALLOWED_SERIES)


class TestItRefusesTwoReads:
    def test_different_read_times_show_no_hint(self, pair):
        lar, buf = pair
        later = BookRead(buf.ticker, buf.yes_bid_tenths, buf.yes_bid_qty, buf.no_bid_tenths, buf.no_bid_qty, READ_MS + 1)
        assert _hint(league=NFL, own=lar, own_side="yes", other=later) is None

    def test_an_unknown_read_time_is_not_equal_to_another(self, pair):
        lar, buf = pair
        unread = BookRead(buf.ticker, buf.yes_bid_tenths, buf.yes_bid_qty, buf.no_bid_tenths, buf.no_bid_qty, None)
        both = BookRead(lar.ticker, lar.yes_bid_tenths, lar.yes_bid_qty, lar.no_bid_tenths, lar.no_bid_qty, None)
        assert _hint(league=NFL, own=both, own_side="yes", other=unread) is None


class TestItRefusesAStaleRead:
    def test_equal_read_times_older_than_the_limit_show_no_hint(self, pair):
        lar, buf = pair
        limit = STALENESS.max_kalshi_quote_age_s * 1000
        assert _hint(league=NFL, own=lar, own_side="yes", other=buf, now_ms=READ_MS + limit) is not None
        assert (
            _hint(league=NFL, own=lar, own_side="yes", other=buf, now_ms=READ_MS + limit + 1)
            is None
        )


class TestTheCopyClaimsNothing:
    def test_it_says_it_cuts_what_you_pay_and_creates_no_edge(self, pair):
        lar, buf = pair
        copy = _hint(league=NFL, own=lar, own_side="yes", other=buf)["copy"]
        assert line_shop.DISCLAIMER == "This cuts what you pay. It does not create an edge."
        assert line_shop.DISCLAIMER in copy

    def test_no_edge_or_profit_claim_outside_the_disclaimer(self, pair):
        lar, buf = pair
        copy = _hint(league=NFL, own=lar, own_side="yes", other=buf)["copy"]
        rest = copy.replace(line_shop.DISCLAIMER, "").lower()
        for word in (
            "edge", "profit", "win ", "beat", "guarantee", "free", "arbitrage",
            "value", "+ev", "mispric", "bargain", "sharp", "advantage", "lock",
        ):
            assert word not in rest, word


class TestItIsNeverAnOrdering:
    def test_no_sort_in_the_routes_reads_it(self):
        from backend.api import routes

        source = inspect.getsource(routes)
        assert "line_shop" in source, "the hint is not wired into the route"
        for m in re.finditer(r"(\.sort\(|sorted\()(.*?)\n\s*\)\s*\n", source, re.S):
            assert "line_shop" not in m.group(2), m.group(0)
        # and no key function anywhere mentions it on one line
        for line in source.splitlines():
            if "sort" in line or "lambda" in line:
                assert "line_shop" not in line, line

    def test_the_slates_sort_key_is_untouched(self):
        from backend.api import routes

        source = inspect.getsource(routes)
        match = re.search(r"items\.sort\(\s*key=lambda r: \((.*?)\)\s*\)", source, re.S)
        assert match and "line_shop" not in match.group(1)

    def test_the_page_never_sorts_or_filters_on_it(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "frontend" / "src"
        for rel in ("app/slate/page.tsx", "components/LineShopHint.tsx"):
            text = (root / rel).read_text(encoding="utf8")
            for line in text.splitlines():
                if re.search(r"\.(sort|filter|toSorted)\(", line):
                    assert "line_shop" not in line, (rel, line)


@pytest.fixture()
def conn(tmp_path):
    c = db.init_db(tmp_path / "line_shop.db")
    now = READ_MS
    c.execute(
        "INSERT INTO kalshi_series (series_ticker, league, has_game_markets, "
        "first_seen_ms, last_seen_ms) VALUES ('KXNFLGAME', 'Pro Football', 1, ?, ?)",
        (now, now),
    )
    c.execute(
        "INSERT INTO kalshi_events (event_ticker, series_ticker, title, category, "
        "commence_ms, status, first_seen_ms, last_seen_ms) "
        "VALUES ('KXNFLGAME-26OCT12BUFLAR', 'KXNFLGAME', 'Bills at Rams', "
        "'Sports', ?, 'open', ?, ?)",
        (now + 3_600_000, now, now),
    )
    c.commit()
    try:
        yield c
    finally:
        c.close()


def _add_market(conn, ticker, team):
    conn.execute(
        "INSERT INTO kalshi_markets (ticker, event_ticker, series_ticker, title, "
        "yes_side_team, market_type, status, first_seen_ms, last_seen_ms) "
        "VALUES (?, 'KXNFLGAME-26OCT12BUFLAR', 'KXNFLGAME', ?, ?, 'moneyline', "
        "'active', ?, ?)",
        (ticker, team, team, READ_MS, READ_MS),
    )


def _add_quote(conn, book, confirmed_ms):
    conn.execute(
        "INSERT INTO kalshi_quotes (ticker, observed_ms, confirmed_ms, source, "
        "yes_bid_tenths, yes_bid_qty, no_bid_tenths, no_bid_qty) "
        "VALUES (?, ?, ?, 'rest', ?, ?, ?, ?)",
        (book.ticker, READ_MS, confirmed_ms, book.yes_bid_tenths, book.yes_bid_qty,
         book.no_bid_tenths, book.no_bid_qty),
    )


def _row(ticker, side="yes", league="Pro Football"):
    return {"ticker": ticker, "side": side, "league": league}


class TestTheSlateHelperReadsTheDatabase:
    def _seed(self, conn, pair, buf_confirmed=READ_MS):
        lar, buf = pair
        _add_market(conn, lar.ticker, "Los Angeles R")
        _add_market(conn, buf.ticker, "Buffalo")
        _add_quote(conn, lar, READ_MS)
        _add_quote(conn, buf, buf_confirmed)
        conn.commit()
        return lar, buf

    def _run(self, conn, rows, now_ms=NOW_MS):
        return hints_for_slate(conn, rows, now_ms, STALENESS)

    def test_fires_from_stored_quotes(self, conn, pair):
        lar, _ = self._seed(conn, pair)
        hint = self._run(conn, [_row(lar.ticker)])[(lar.ticker, "yes")]
        assert hint["cheaper"]["team"] == "Buffalo"

    def test_a_different_confirmation_instant_refuses(self, conn, pair):
        lar, _ = self._seed(conn, pair, buf_confirmed=READ_MS + 5_000)
        assert self._run(conn, [_row(lar.ticker)]) == {}

    def test_a_stale_read_refuses(self, conn, pair):
        lar, _ = self._seed(conn, pair)
        late = READ_MS + STALENESS.max_kalshi_quote_age_s * 1000 + 1
        assert self._run(conn, [_row(lar.ticker)], now_ms=late) == {}

    def test_a_third_market_in_the_event_refuses(self, conn, pair):
        lar, _ = self._seed(conn, pair)
        _add_market(conn, "KXNFLGAME-26OCT12BUFLAR-TIE", "Tie")
        conn.commit()
        assert self._run(conn, [_row(lar.ticker)]) == {}

    def test_an_inactive_market_refuses(self, conn, pair):
        lar, buf = self._seed(conn, pair)
        conn.execute("UPDATE kalshi_markets SET status = 'closed' WHERE ticker = ?", (buf.ticker,))
        conn.commit()
        assert self._run(conn, [_row(lar.ticker)]) == {}
        conn.execute("UPDATE kalshi_markets SET status = 'active' WHERE ticker = ?", (buf.ticker,))
        conn.execute("UPDATE kalshi_markets SET status = 'closed' WHERE ticker = ?", (lar.ticker,))
        conn.commit()
        assert self._run(conn, [_row(lar.ticker)]) == {}

    def test_a_market_with_no_quote_refuses(self, conn, pair):
        lar, buf = pair
        _add_market(conn, lar.ticker, "Los Angeles R")
        _add_market(conn, buf.ticker, "Buffalo")
        _add_quote(conn, lar, READ_MS)
        conn.commit()
        assert self._run(conn, [_row(lar.ticker)]) == {}

    def test_the_newest_quote_is_the_one_read(self, conn, pair):
        lar, buf = self._seed(conn, pair)
        # An older, different BUF quote must not be the one compared.
        conn.execute(
            "INSERT INTO kalshi_quotes (ticker, observed_ms, confirmed_ms, source, "
            "yes_bid_tenths, yes_bid_qty, no_bid_tenths, no_bid_qty) "
            "VALUES (?, ?, ?, 'rest', 100, 5, 100, 5)",
            (buf.ticker, READ_MS - 10_000, READ_MS - 10_000),
        )
        conn.commit()
        assert (lar.ticker, "yes") in self._run(conn, [_row(lar.ticker)])

    def test_a_disallowed_league_row_is_skipped(self, conn, pair):
        lar, _ = self._seed(conn, pair)
        assert self._run(conn, [_row(lar.ticker, league="Pro Hockey")]) == {}
        assert self._run(conn, []) == {}


class TestTheSlateHelperIsBatched:
    def test_query_count_does_not_grow_with_rows(self, conn, pair):
        lar, buf = pair
        _add_market(conn, lar.ticker, "Los Angeles R")
        _add_market(conn, buf.ticker, "Buffalo")
        _add_quote(conn, lar, READ_MS)
        _add_quote(conn, buf, READ_MS)
        conn.commit()
        seen = []
        conn.set_trace_callback(seen.append)
        rows = [_row(lar.ticker), _row(buf.ticker), _row(lar.ticker, "no"), _row(buf.ticker, "no")]
        hints_for_slate(conn, rows[:1], NOW_MS, STALENESS)
        one = len(seen)
        seen.clear()
        hints_for_slate(conn, rows * 25, NOW_MS, STALENESS)
        assert len(seen) == one == 2

    def test_the_route_loop_does_not_query_per_row(self):
        from backend.api import routes

        source = inspect.getsource(routes)
        assert "hint_for_row" not in source
        assert "line_shop.hints_for_slate(" in source


class TestTheNbaRuleResolvesOnTheWinner:
    """#255: NBA is allowed on the premise that an NBA game cannot tie.

    The premise is read off a captured `rules_primary`
    (`tests/fixtures/markets_nba_game_rules.json`, GET /markets?series_ticker=
    KXNBAGAME, 2026-09-30), not assumed. Establishes: the rule text of ONE event
    (OKC vs SAS, 2026-10-20) resolves on the winner with no tie or third
    outcome. Does NOT establish: that every KXNBAGAME event shares the wording,
    or how the venue settles an abandoned game beyond what the text says.
    """

    def _markets(self):
        doc = load_fixture("markets_nba_game_rules.json")
        assert doc["request"]["params"]["series_ticker"] == "KXNBAGAME"
        return doc["markets"]

    def test_each_market_resolves_yes_when_its_team_wins(self):
        markets = self._markets()
        assert len(markets) == 2
        for m in markets:
            rule = m["rules_primary"]
            assert re.search(r"\bwins the .+ game\b.*resolves to Yes", rule), rule

    def test_the_rule_names_no_tie_or_third_outcome(self):
        for m in self._markets():
            text = (m["rules_primary"] + " " + (m.get("rules_secondary") or "")).lower()
            for word in ("tie", "draw", "push", "neither"):
                assert not re.search(rf"\b{word}\b", text), (word, text)

    def test_the_two_markets_are_the_two_teams_so_one_side_must_win(self):
        a, b = self._markets()
        assert a["event_ticker"] == b["event_ticker"]
        assert a["yes_sub_title"] != b["yes_sub_title"]

    def test_nba_stays_allowed_only_because_the_rule_above_holds(self):
        assert "KXNBAGAME" in line_shop.ALLOWED_SERIES
        assert "basketball_nba" in line_shop.ALLOWED_SPORT_KEYS
