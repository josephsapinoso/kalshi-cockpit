"""Alternate lines: stored under their own keys, priced at one exact line (#305).

Fixture: `tests/fixtures/odds_ncaaf_alternate_lines.json` is a REAL per-event
capture (BYU @ TCU, 2026-10-03, request envelope under `request`). Tests that
need a case the capture lacks derive it from the capture and say
**synthetic** in their docstring.

What this does not establish: that the devigged chance is *right*, only that
the pairing, dropping, worst-of-four and isolation rules hold.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from backend.alt_lines import (
    NO_ALTERNATE_FETCH,
    NO_BOOK_AT_LINE,
    NO_TWO_SIDED_BOOK,
    alt_line_chance,
)
from backend.core.devig import devig
from backend.odds.client import (
    ALT_TEAM_MARKETS,
    PRICEABLE_MARKETS,
    OddsClient,
    OddsQuote,
    store_quotes,
)
from backend.runner import spread_quotes_for_event, totals_quotes_for_event
from backend.store import db

FIXTURE = Path(__file__).parent / "fixtures" / "odds_ncaaf_alternate_lines.json"
EVENT_ID = "b58c0d24e66471e6095c0a5f9afb7ce3"
FETCH_MS = 1_790_000_000_000
NOW_MS = FETCH_MS + 60_000
BYU, TCU = "BYU Cougars", "TCU Horned Frogs"


def _capture() -> dict:
    return json.loads(FIXTURE.read_text("utf-8"))["response"]


def _parse(event: dict) -> list[OddsQuote]:
    # `_parse` reads nothing off the instance.
    client = OddsClient.__new__(OddsClient)
    return client._parse([event], sport_key="americanfootball_ncaaf", fetched_ms=FETCH_MS)


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "alt.db")
    yield c
    c.close()


@pytest.fixture
def stored(conn):
    quotes = _parse(_capture())
    store_quotes(conn, quotes)
    conn.commit()
    return quotes


def _book_prices(market: str, a_name: str, a_pt: float, b_name: str, b_pt: float):
    """{book: [price_a, price_b]} read straight off the capture."""
    per: dict[str, dict] = {}
    for b in _capture()["bookmakers"]:
        for m in b["markets"]:
            if m["key"] != market:
                continue
            for o in m["outcomes"]:
                if (o["name"], o["point"]) == (a_name, a_pt):
                    per.setdefault(b["key"], {})["a"] = o["price"]
                if (o["name"], o["point"]) == (b_name, b_pt):
                    per.setdefault(b["key"], {})["b"] = o["price"]
    return {k: [v["a"], v["b"]] for k, v in per.items() if len(v) == 2}


def _expected_worst(prices: dict[str, list[float]]) -> float:
    """Independent re-derivation: per-book devig, average each method, min."""
    results = [devig(["a", "b"], p) for p in prices.values()]
    return min(
        sum(r.all_methods()[m][0] for r in results) / len(results)
        for m in ("multiplicative", "additive", "power", "shin")
    )


class TestStorage:
    def test_alternate_team_keys_are_classified_and_stored(self, conn, stored):
        """The real per-event response is stored, under the vendor keys only."""
        assert ALT_TEAM_MARKETS == {"alternate_spreads", "alternate_totals"}
        assert ALT_TEAM_MARKETS <= PRICEABLE_MARKETS
        assert stored, "the parser dropped the whole alternate response"
        markets = {
            r["market"]
            for r in conn.execute("SELECT DISTINCT market FROM odds_snapshots")
        }
        assert markets == {"alternate_spreads", "alternate_totals"}
        assert conn.execute(
            "SELECT COUNT(*) c FROM odds_snapshots WHERE market IN ('spreads','totals')"
        ).fetchone()["c"] == 0
        # Every outcome in the capture came through, line included -- except
        # the three price-1.0 quotes (a book offering "certain" at an extreme
        # line), which the parser drops by its existing rule; the pairing then
        # leaves that line one-sided and `alt_lines` drops the book.
        n_outcomes = sum(
            sum(1 for o in m["outcomes"] if o["price"] > 1.0)
            for b in _capture()["bookmakers"]
            for m in b["markets"]
        )
        assert len(stored) == n_outcomes
        assert all(q.outcome_point is not None for q in stored)

    def test_alt_rows_do_not_reach_main_line_reads(self, conn, stored):
        """A stored alternate fetch is invisible to the main spreads/totals reads.

        Second half is SYNTHETIC: a real main-line fetch for the same event is
        written EARLIER than the alternate fetch. If alternate rows were filed
        as `spreads`/`totals`, MAX(fetched_ms) would select the alternate sweep
        and the main line would vanish (or be mispaired).
        """
        assert spread_quotes_for_event(conn, EVENT_ID, now=NOW_MS) == []
        assert totals_quotes_for_event(conn, EVENT_ID, now=NOW_MS) == []

        main = [
            OddsQuote(
                fetched_ms=FETCH_MS - 600_000, book_updated_ms=FETCH_MS - 600_000,
                sport_key="americanfootball_ncaaf", odds_event_id=EVENT_ID,
                commence_ms=FETCH_MS + 3_600_000, home_team=TCU, away_team=BYU,
                bookmaker="pinnacle", market="spreads", outcome_name=name,
                outcome_description=None, outcome_point=pt, price_decimal=1.95,
            )
            for name, pt in ((BYU, -3.5), (TCU, 3.5))
        ]
        store_quotes(conn, main)
        conn.commit()
        lines = spread_quotes_for_event(conn, EVENT_ID, now=NOW_MS)
        assert len(lines) == 1
        assert lines[0].points == {BYU: -3.5, TCU: 3.5}


class TestPricing:
    def test_alt_spread_pairs_by_complementary_point(self, stored, conn):
        """BYU -6.5 pairs with TCU +6.5 at every one of the six books."""
        got = alt_line_chance(conn, EVENT_ID, "spreads", BYU, -6.5, NOW_MS)
        assert got.reason is None
        assert got.books_used == (
            "betmgm", "bovada", "draftkings", "fanatics", "fanduel", "pinnacle",
        )
        assert got.books_dropped == {}
        want = _expected_worst(_book_prices("alternate_spreads", BYU, -6.5, TCU, 6.5))
        assert got.chance == pytest.approx(want)
        # The other side of the same line is the complement, not a copy.
        other = alt_line_chance(conn, EVENT_ID, "spreads", TCU, 6.5, NOW_MS)
        assert other.chance + got.chance == pytest.approx(1.0, abs=0.02)
        assert other.chance != pytest.approx(got.chance)

    def test_one_sided_alt_book_is_dropped_and_counted(self, conn):
        """SYNTHETIC variant: the capture is two-sided everywhere, so strip
        TCU +6.5 from fanduel and BYU -6.5 from bovada to make each one-sided."""
        event = copy.deepcopy(_capture())
        for b in event["bookmakers"]:
            for m in b["markets"]:
                if m["key"] != "alternate_spreads":
                    continue
                drop = {"fanduel": (TCU, 6.5), "bovada": (BYU, -6.5)}.get(b["key"])
                if drop:
                    m["outcomes"] = [
                        o for o in m["outcomes"] if (o["name"], o["point"]) != drop
                    ]
        store_quotes(conn, _parse(event))
        conn.commit()
        got = alt_line_chance(conn, EVENT_ID, "spreads", BYU, -6.5, NOW_MS)
        assert got.one_sided_count == 2
        assert got.books_dropped == {"fanduel": "one_sided", "bovada": "one_sided"}
        assert got.books_used == ("betmgm", "draftkings", "fanatics", "pinnacle")
        want = _expected_worst(
            {
                k: v
                for k, v in _book_prices(
                    "alternate_spreads", BYU, -6.5, TCU, 6.5
                ).items()
                if k in got.books_used
            }
        )
        assert got.chance == pytest.approx(want)

    def test_alt_total_uses_worst_of_four(self, stored, conn):
        """Over 51.5: the chance is the lowest method's, each book devigged first."""
        got = alt_line_chance(conn, EVENT_ID, "totals", "Over", 51.5, NOW_MS)
        assert got.reason is None
        assert got.books_used == ("betmgm", "draftkings", "fanatics", "fanduel")
        prices = _book_prices("alternate_totals", "Over", 51.5, "Under", 51.5)
        results = [devig(["o", "u"], p) for p in prices.values()]
        per_method = {
            m: sum(r.all_methods()[m][0] for r in results) / len(results)
            for m in ("multiplicative", "additive", "power", "shin")
        }
        assert got.chance == pytest.approx(min(per_method.values()))
        # The guard is not decoration: the four methods genuinely differ here,
        # so picking one would give a different number.
        assert max(per_method.values()) - min(per_method.values()) > 1e-6
        assert got.chance < max(per_method.values())

    def test_age_is_the_stalest_used_books_update(self, stored, conn):
        got = alt_line_chance(conn, EVENT_ID, "spreads", BYU, -6.5, NOW_MS)
        # Bovada's 18:53:17Z update is the oldest of the six in the capture.
        from datetime import datetime, timezone

        bovada_ms = int(
            datetime(2026, 10, 3, 18, 53, 17, tzinfo=timezone.utc).timestamp() * 1000
        )
        assert got.age_ms == NOW_MS - bovada_ms

    def test_no_usable_book_is_none_not_zero(self, stored, conn):
        """No fetch, no book at the line, and only-one-sided each give None + reason."""
        nothing = alt_line_chance(conn, "no-such-event", "spreads", BYU, -6.5, NOW_MS)
        assert nothing.chance is None and nothing.reason == NO_ALTERNATE_FETCH

        absent = alt_line_chance(conn, EVENT_ID, "totals", "Over", 12.25, NOW_MS)
        assert absent.chance is None and absent.reason == NO_BOOK_AT_LINE

        # SYNTHETIC: delete every Under at 45.5 so each book is one-sided.
        conn.execute(
            "DELETE FROM odds_snapshots WHERE market = 'alternate_totals' "
            "AND outcome_name = 'Under' AND outcome_point = 45.5"
        )
        conn.commit()
        lone = alt_line_chance(conn, EVENT_ID, "totals", "Over", 45.5, NOW_MS)
        assert lone.chance is None
        assert lone.reason == NO_TWO_SIDED_BOOK
        assert lone.one_sided_count == 4

        # Unsupported market / side: also None, never a number.
        assert alt_line_chance(conn, EVENT_ID, "h2h", BYU, 0.0, NOW_MS).chance is None
        assert alt_line_chance(conn, EVENT_ID, "totals", BYU, 45.5, NOW_MS).chance is None
