"""A parlay leg carries the provenance behind its number, and claims nothing more.

Until 2026-08-26 a leg served `fair_percent_display` and nothing else. That one
number stands in for three separate choices — which devig method, which books,
and how far the field spreads — and the slate row has shown all three since
ADR 0051 while the parlay card, which offers money decisions, showed none.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That the facts make a card a good bet.** They are provenance. Nothing here
  is scored against an outcome and the server combines none of them.
- **That the unanchored book distribution is served.** It is not:
  `book_count` and `books_used` come off the `fair_prices` row already read,
  while the full min/median/max across every usable book needs a per-book
  re-devig per leg. Deliberately out of v1 and stated so nobody assumes it.
- **Anything about ordering.** `test_parlays_api.py` owns the rule that the
  ladder never ranks by the Kalshi gap.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend import parlays  # noqa: E402
from backend.core.ladder import CandidateLeg  # noqa: E402
from backend.store import db  # noqa: E402

COMPONENT = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "src"
    / "components"
    / "ParlayCards.tsx"
)


def _leg(**over) -> CandidateLeg:
    base = dict(
        label="St. Louis to win",
        event_title="Chicago at St. Louis",
        kalshi_event_ticker="KXMLBGAME-x",
        kalshi_market_ticker="KXMLBGAME-x-STL",
        odds_event_id="g1",
        league="baseball_mlb",
        commence_ms=1_787_000_000_000,
        market="h2h",
        team="St. Louis Cardinals",
        point=None,
        p_conservative=0.58,
        p_by_method={
            "multiplicative": 0.60,
            "additive": 0.59,
            "power": 0.595,
            "shin": 0.58,
        },
        odds_age_now_ms=35_000,
        market_width=0.031,
        book_count=9,
        books_used_json='["pinnacle", "betfair_ex_uk", "matchbook"]',
        anchored_on_sharp=True,
    )
    base.update(over)
    return CandidateLeg(**base)


class TestTheLegCarriesItsProvenance:
    def test_the_four_devig_readings_become_a_spread_not_four_numbers(self):
        """The same figure `DispersionStrip` shows as its summary line."""
        out = parlays._serialise_leg(_leg())
        assert out["method_spread_display"] == "2.0 pts"

    def test_one_solvable_reading_is_not_perfect_agreement(self):
        """`None`, never `0.0 pts`.

        One reading is one reading. Rendering it as zero spread asserts the
        methods agreed, which is the opposite of what happened.
        """
        out = parlays._serialise_leg(
            _leg(p_by_method={"multiplicative": 0.6, "additive": None,
                              "power": None, "shin": None})
        )
        assert out["method_spread_display"] is None

    def test_the_books_and_the_width_ride_along(self):
        out = parlays._serialise_leg(_leg())
        assert out["book_count"] == 9
        assert out["books_used"] == ["pinnacle", "betfair_ex_uk", "matchbook"]
        assert out["market_width_display"] == "3.1 pts"

    def test_an_unreadable_fact_is_none_never_zero(self):
        """CLAUDE.md: unreadable resolves to None, never 0.

        A book count of 0 reads as "no consensus"; a width of 0 reads as
        "every book agreed exactly". Both are claims, and neither is what an
        absent column means.
        """
        out = parlays._serialise_leg(
            _leg(book_count=None, market_width=None, books_used_json=None)
        )
        assert out["book_count"] is None
        assert out["market_width_display"] is None
        assert out["books_used"] == []


class TestTheSkepticIsThreeValued:
    def test_a_spread_leg_says_the_checks_did_not_run(self):
        """ADR 0070 keeps spread rows off the recommendations path entirely.

        A blank here would read as "the checks passed" — the flattering
        misreading of a measurement that never happened.
        """
        out = parlays._serialise_leg(_leg(market="spreads", point=-1.5))
        assert out["skeptic"] == "not_on_this_path"

    def test_an_unpriced_moneyline_says_absent(self):
        out = parlays._serialise_leg(_leg())
        assert out["skeptic"] == "absent"

    def test_a_priced_leg_carries_the_verdict_verbatim(self):
        """The code is the fact (ADR 0050); a translation is a second definition."""
        facts = dict(parlays._NO_FACTS)
        facts["skeptic"] = "checked"
        facts["suppressed_reason"] = "stale_odds"
        out = parlays._serialise_leg(_leg(), facts)
        assert out["skeptic"] == "checked"
        assert out["suppressed_reason"] == "stale_odds"

    def test_a_prop_leg_says_absent_not_off_the_path(self):
        """Props ARE on the recommendations path; spreads are the exception.

        `_price_prop_event` pushes a `Candidate` per side through
        `_priced_or_counted` (`runner.py:1554-1575`) exactly as the moneyline
        path does, while the spread path `continue`s before it
        (`runner.py:1882-1884`).

        This guards the tempting generalisation: widening the rule below from
        `market == "spreads"` to `market != "h2h"` would stamp
        `not_on_this_path` on prop legs the skeptic genuinely did check. That
        is the same flattering misreading as a blank, pointing the other way —
        a measurement that happened, reported as one that never ran.
        """
        for market in (
            "pitcher_strikeouts",
            "batter_total_bases",
            "batter_hits",
            "batter_home_runs",
            "batter_rbis",
        ):
            out = parlays._serialise_leg(
                _leg(market=market, team=None, point=5.5, player="Anthony Kay")
            )
            assert out["skeptic"] == "absent", market

    def test_a_priced_prop_leg_carries_the_verdict(self):
        """The other direction: a real verdict on a prop must survive."""
        facts = dict(parlays._NO_FACTS)
        facts["skeptic"] = "checked"
        facts["suppressed_reason"] = "too_few_books"
        out = parlays._serialise_leg(
            _leg(market="pitcher_strikeouts", team=None, point=5.5,
                 player="Anthony Kay"),
            facts,
        )
        assert out["skeptic"] == "checked"
        assert out["suppressed_reason"] == "too_few_books"

    def test_a_priced_spread_leg_keeps_its_verdict(self):
        """`not_on_this_path` applies only when there is genuinely no row.

        If a spread ticker ever does get priced, the real verdict must win over
        the structural excuse.
        """
        facts = dict(parlays._NO_FACTS)
        facts["skeptic"] = "checked"
        out = parlays._serialise_leg(_leg(market="spreads"), facts)
        assert out["skeptic"] == "checked"


class TestTheAskIsReadNotInvented:
    @pytest.fixture
    def conn(self):
        path = os.path.join(tempfile.mkdtemp(), "facts.db")
        c = db.init_db(path)
        yield c
        c.close()

    def _quote(self, conn, ticker, *, no_bid, no_qty, observed, confirmed=None):
        # `kalshi_quotes` has a foreign key to `kalshi_markets`, so the market
        # has to exist first. Discovered by the test failing, which is the FK
        # doing its job.
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_events (event_ticker, title, "
            "first_seen_ms, last_seen_ms) VALUES ('EV', 'A at B', 0, 0)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, "
            "yes_side_team, market_type, status, first_seen_ms, last_seen_ms) "
            "VALUES (?, 'EV', 'T', 'moneyline', 'active', 0, 0)",
            (ticker,),
        )
        conn.execute(
            "INSERT INTO kalshi_quotes (ticker, observed_ms, confirmed_ms, seq, "
            "source, yes_bid_tenths, yes_bid_qty, no_bid_tenths, no_bid_qty) "
            "VALUES (?, ?, ?, NULL, 'rest', 400, 10.0, ?, ?)",
            (ticker, observed, confirmed or observed, no_bid, no_qty),
        )
        conn.commit()

    def test_a_two_sided_book_gives_the_derived_ask_and_its_depth(self, conn):
        now = db.now_ms()
        self._quote(conn, "T1", no_bid=606, no_qty=184.0, observed=now - 4000)
        facts = parlays.leg_facts(conn, ["T1"], now_ms=now)["T1"]
        assert facts["ask_tenths"] == 394
        assert facts["ask_display"] == "39.4c"
        assert facts["depth_at_ask"] == 184.0

    def test_a_one_sided_book_has_no_ask_rather_than_a_free_one(self, conn):
        """The defect that took the recorder down, one layer out.

        Asks are derived, so an absent NO bid — which the venue reports as
        `0.0000`, a real zero — would hand back 1000 tenths. `ask_for_side`
        refuses both endpoints, and this pins that the parlay screen inherits
        the refusal rather than re-deriving one.
        """
        now = db.now_ms()
        self._quote(conn, "T2", no_bid=0, no_qty=0.0, observed=now - 4000)
        facts = parlays.leg_facts(conn, ["T2"], now_ms=now)["T2"]
        assert facts["ask_tenths"] is None
        assert facts["ask_display"] is None

    def test_an_unchanged_quote_is_current_not_stale(self, conn):
        """ADR 0055 writes a row only when the price MOVES.

        So `observed_ms` is when it last changed, and a quote confirmed since
        is current however old that is. Ageing from `observed_ms` would make a
        steady market look abandoned.
        """
        now = db.now_ms()
        self._quote(
            conn, "T3", no_bid=500, no_qty=5.0,
            observed=now - 600_000, confirmed=now - 1_000,
        )
        assert parlays.leg_facts(conn, ["T3"], now_ms=now)["T3"]["quote_age_ms"] == 1000

    def test_a_ticker_with_no_quote_reads_absent(self, conn):
        facts = parlays.leg_facts(conn, ["NOPE"], now_ms=db.now_ms())["NOPE"]
        assert facts["ask_display"] is None
        assert facts["quote_age_ms"] is None

    def test_the_whole_ladder_costs_two_queries_not_one_per_leg(self, conn):
        """The scope that keeps this off the N+1 path.

        Facts are attached to the SELECTED legs — at most six per card across
        six cards — and read in one statement each. Enriching the ~200-row
        candidate pool per-row is the shape `/api/slate` is separately being
        cured of.
        """
        now = db.now_ms()
        tickers = [f"T{i}" for i in range(20)]
        for t in tickers:
            self._quote(conn, t, no_bid=500, no_qty=1.0, observed=now)

        # `sqlite3.Connection.execute` is read-only and cannot be monkeypatched,
        # so the count comes from the driver's own trace hook — which also
        # counts statements this test could not otherwise see.
        seen: list[str] = []
        conn.set_trace_callback(seen.append)
        try:
            parlays.leg_facts(conn, tickers, now_ms=now)
        finally:
            conn.set_trace_callback(None)

        assert len(seen) == 2, (
            f"{len(seen)} statements for 20 legs — this must be O(1) in legs, "
            f"not O(n). Statements: {seen}"
        )


class TestTheScreenKeepsItsHonesty:
    def _source(self) -> str:
        return COMPONENT.read_text(encoding="utf-8")

    def test_a_missing_fact_renders_an_em_dash_rather_than_vanishing(self):
        """Fixed order is the design: a reader compares by position.

        Omitting a fact shifts the other three and destroys the scan, and it
        makes "unreadable" indistinguishable from "not applicable".
        """
        source = self._source()
        em_dash = chr(0x2014)
        assert f'const MISSING = "{em_dash}"' in source, (
            "no em-dash constant; a missing fact will vanish and shift the row"
        )
        assert source.count("MISSING") >= 5, (
            f"only {source.count('MISSING')} uses of MISSING — each of the "
            f"four facts needs its own fallback, plus the declaration"
        )

    def test_sharp_anchoring_is_never_worded_as_better(self):
        """A sharp anchor selects at most three books (CLAUDE.md).

        It is a THINNER fair value, not a better one, and the screen must not
        imply otherwise.
        """
        source = self._source().lower()
        start = source.find("leg.anchored_on_sharp === true")
        assert start != -1, "the sharp-anchoring branch moved"
        window = source[start:][:400]

        # Not a bare word ban: the honest wording says "not a BETTER one", so
        # forbidding the word would fail the sentence that gets it right. What
        # must be absent is a positive CLAIM, and what must be present is the
        # reason it is not one.
        for phrase in ("stronger", "more reliable", "more trustworthy", "best"):
            assert phrase not in window, f"sharp anchoring worded as {phrase!r}"
        assert "thinner" in window, "the thinness caveat is missing"
        assert "at most three" in window, "the arithmetic behind it is missing"

    def test_the_spread_leg_says_the_checks_did_not_run(self):
        source = self._source()
        assert "not_on_this_path" in source
        assert "did not run here" in source

    def test_the_suppression_code_renders_verbatim(self):
        """ADR 0050: the code is the fact; a translation is a second definition."""
        assert "{leg.suppressed_reason}" in self._source()

    def test_no_edge_or_breakeven_word_enters_the_leg_block(self):
        source = self._source().lower()
        for word in ("breakeven", "break-even", "edge_tenths", "expected value"):
            assert word not in source, f"{word!r} appeared on the parlay screen"
