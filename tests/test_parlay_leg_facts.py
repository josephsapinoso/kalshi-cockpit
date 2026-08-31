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

import json
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

    #: One statement per fact family, and each is named so that adding a
    #: fourth is a decision rather than drift. It was 2 until 2026-08-30, when
    #: the scout state became a third — still one statement for the whole
    #: ladder, which is the property this guards.
    LADDER_STATEMENTS = ("kalshi_quotes", "recommendations", "scout_briefings")

    def test_the_whole_ladder_costs_a_fixed_number_of_queries_not_one_per_leg(
        self, conn
    ):
        """The scope that keeps this off the N+1 path.

        Facts are attached to the SELECTED legs — at most six per card across
        six cards — and read in one statement each. Enriching the ~200-row
        candidate pool per-row is the shape `/api/slate` is separately being
        cured of.

        **The count is fixed, not "small".** Asserting `<= n` would let this
        drift upward a query at a time, each one defensible; asserting the
        exact set means a new fact family has to come here and say what it is.
        20 legs would give 20+ statements if any of these went per-row, so the
        O(n) failure this exists for is still caught with room to spare.
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

        assert len(seen) == len(self.LADDER_STATEMENTS), (
            f"{len(seen)} statements for 20 legs — this must be O(1) in legs, "
            f"not O(n). Statements: {seen}"
        )
        for table in self.LADDER_STATEMENTS:
            assert any(table in s for s in seen), (
                f"no statement read {table}; the count is right but the "
                f"families are not the ones this test claims to cover"
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


class TestTheScoutStateRidesOnTheLegWithoutTouchingThePrice:
    """Joe's ruling, 2026-08-30: the Scout gates eligibility and FLAGS, and
    never moves the price. He chose that over letting it adjust fair value.

    **What this establishes.** That a briefing filed against ANY market on a
    fixture surfaces on every leg of that fixture; that the non-`clear` board
    states all become flags while `clear` does not; that a running, refused or
    failed briefing says so rather than reading as calm; and that none of it
    reaches a number.

    **What it does not.** That any briefing is any good, or that a flag should
    drop a leg. This slice makes the desk's knowledge visible per leg. Gating
    on it is a later decision, and at five convenings a day
    (`AGENT_MAX_SEARCHES_PER_DAY`, which binds before the call cap) it cannot
    be automatic for a six-card ladder.
    """

    @pytest.fixture
    def conn(self):
        path = os.path.join(tempfile.mkdtemp(), "scout_facts.db")
        c = db.init_db(path)
        yield c
        c.close()

    def _fixture(self, conn, *, event="EV1", tickers=("M1", "M2")):
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_events (event_ticker, title, "
            "first_seen_ms, last_seen_ms) VALUES (?, 'A at B', 0, 0)",
            (event,),
        )
        for t in tickers:
            conn.execute(
                "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, "
                "yes_side_team, market_type, status, first_seen_ms, "
                "last_seen_ms) VALUES (?, ?, 'T', 'moneyline', 'active', 0, 0)",
                (t, event),
            )
        conn.commit()

    def _briefing(self, conn, ticker, *, status="complete", board=None,
                  headline="Starter scratched", requested=1_000,
                  completed=2_000, briefing_json=...):
        if briefing_json is ...:
            briefing_json = json.dumps({
                "headline": headline,
                "board": board if board is not None else [],
                "assessment": "", "what_matters": [], "conflicts": [],
                "unanswered": [],
            })
        conn.execute(
            "INSERT INTO scout_briefings (ticker, event_title, league, "
            "home_team, away_team, requested_ms, completed_ms, status, "
            "briefing_json, model) VALUES (?, 'A at B', 'x', 'A', 'B', ?, ?, "
            "?, ?, 'm')",
            (ticker, requested, completed, status, briefing_json),
        )
        conn.commit()

    def test_a_briefing_on_one_market_reaches_every_leg_of_that_game(self, conn):
        """The join is the point of the whole design.

        `/api/scout/{ticker}` convenes the desk on whatever market was in front
        of Joe, but the briefing describes a FIXTURE. Keying leg to briefing by
        market ticker would show a game as unscouted while its own briefing sat
        in the table. Mutation observed red: join `b.ticker = m.ticker`.
        """
        self._fixture(conn, tickers=("M1", "M2"))
        self._briefing(conn, "M1")

        facts = parlays.leg_facts(conn, ["M2"], now_ms=10_000)["M2"]

        assert facts["scout"] == "briefed"
        assert facts["scout_headline"] == "Starter scratched"
        assert facts["scout_ticker"] == "M1", (
            "the card needs the ticker the briefing was actually filed against "
            "so it can link to it"
        )

    def test_a_briefing_on_another_game_does_not_leak_across(self, conn):
        self._fixture(conn, event="EV1", tickers=("M1",))
        self._fixture(conn, event="EV2", tickers=("N1",))
        self._briefing(conn, "M1")

        facts = parlays.leg_facts(conn, ["N1"], now_ms=10_000)["N1"]
        assert facts["scout"] == "absent"

    def test_every_non_clear_tile_becomes_a_flag_and_clear_does_not(self, conn):
        """`unconfirmed` and `stale_only` are absences, and they are flags.

        `BoardTile` has four states rather than a boolean because the first
        real briefing's most decision-relevant fact was a GAP -- weather
        unchecked. A card that flagged only findings would render that gap as
        calm, which is the misreading the four states exist to prevent.
        """
        self._fixture(conn, tickers=("M1",))
        self._briefing(conn, "M1", board=[
            {"category": "lineup", "state": "fresh", "note": "scratched"},
            {"category": "weather", "state": "unconfirmed", "note": "roof?"},
            {"category": "injury", "state": "stale_only", "note": "old note"},
            {"category": "venue", "state": "clear", "note": "nothing"},
        ])

        flags = parlays.leg_facts(
            conn, ["M1"], now_ms=10_000
        )["M1"]["scout_flags"]

        assert [f["category"] for f in flags] == ["lineup", "weather", "injury"]
        assert flags[1]["note"] == "roof?"

    def test_a_running_briefing_reads_as_briefing_not_as_absent(self, conn):
        self._fixture(conn, tickers=("M1",))
        conn.execute(
            "INSERT INTO scout_briefings (ticker, event_title, league, "
            "home_team, away_team, requested_ms, status, model) "
            "VALUES ('M1', 'A at B', 'x', 'A', 'B', 1000, 'running', 'm')"
        )
        conn.commit()

        facts = parlays.leg_facts(conn, ["M1"], now_ms=10_000)["M1"]
        assert facts["scout"] == "briefing"
        assert facts["scout_headline"] is None

    @pytest.mark.parametrize("status", ["failed", "refused"])
    def test_a_refusal_or_a_death_says_so(self, conn, status):
        """Neither may render as "nothing found".

        A ceiling turning the desk away and the desk finding a quiet game are
        opposite facts, and only one of them is information about the game.
        """
        self._fixture(conn, tickers=("M1",))
        self._briefing(conn, "M1", status=status, briefing_json=None)

        facts = parlays.leg_facts(conn, ["M1"], now_ms=10_000)["M1"]
        assert facts["scout"] == status

    def test_unreadable_content_refuses_rather_than_reading_as_quiet(self, conn):
        """Unreadable resolves to a refusal, never to a calm state.

        CLAUDE.md's convention is that unreadable resolves to `None` and
        callers refuse. The equivalent here is `failed`: a row marked complete
        whose JSON will not parse knows nothing, and "knows nothing" must not
        be spelled the same way as "found nothing".
        """
        self._fixture(conn, tickers=("M1",))
        self._briefing(conn, "M1", briefing_json="{not json")

        facts = parlays.leg_facts(conn, ["M1"], now_ms=10_000)["M1"]
        assert facts["scout"] == "failed"

    def test_a_complete_briefing_with_nothing_to_say_is_not_briefed(self, conn):
        """"The desk looked and found nothing" is its own state.

        Collapsing it into `briefed` puts a chip on a leg with no content
        behind it; collapsing it into `absent` claims nobody looked.
        """
        self._fixture(conn, tickers=("M1",))
        self._briefing(conn, "M1", headline="", board=[
            {"category": "venue", "state": "clear", "note": "nothing"},
        ])

        facts = parlays.leg_facts(conn, ["M1"], now_ms=10_000)["M1"]
        assert facts["scout"] == "filed_nothing"

    def test_the_newest_briefing_for_the_game_wins(self, conn):
        self._fixture(conn, tickers=("M1", "M2"))
        self._briefing(conn, "M1", headline="older", requested=1_000,
                       completed=1_500)
        self._briefing(conn, "M2", headline="newer", requested=9_000,
                       completed=9_500)

        facts = parlays.leg_facts(conn, ["M1"], now_ms=10_000)["M1"]
        assert facts["scout_headline"] == "newer"
        assert facts["scout_age_ms"] == 500

    def test_no_leg_is_handed_the_module_level_default_list(self, conn):
        """`dict(_NO_FACTS)` is a SHALLOW copy, and the default is mutable.

        **The first version of this test asserted a bug that cannot happen and
        claimed a mutation it had not run** -- removing the fresh-list line
        left it green, because `_scout_facts` builds its own dict with its own
        list and `update` replaces the entry. That claim is recorded here
        rather than quietly deleted: it is exactly ADR 0087's failure, one file
        later.

        What IS load-bearing is narrower and real. An unscouted leg gets
        `_NO_FACTS["scout_flags"]` **itself** unless a fresh list is
        substituted, so a single future `facts["scout_flags"].append(...)`
        would corrupt the module-level default for the life of the process --
        and every leg served afterwards would carry another game's warning.
        Mutation observed red: delete the `facts["scout_flags"] = []` line.
        """
        self._fixture(conn, event="EV1", tickers=("M1",))
        self._fixture(conn, event="EV2", tickers=("N1",))
        self._briefing(conn, "M1", board=[
            {"category": "lineup", "state": "fresh", "note": "scratched"},
        ])

        facts = parlays.leg_facts(conn, ["M1", "N1"], now_ms=10_000)

        assert len(facts["M1"]["scout_flags"]) == 1
        assert facts["N1"]["scout_flags"] == []
        assert facts["M1"]["scout_flags"] is not facts["N1"]["scout_flags"]
        for ticker in ("M1", "N1"):
            assert (
                facts[ticker]["scout_flags"]
                is not parlays._NO_FACTS["scout_flags"]
            ), (
                f"{ticker} was handed the module-level default list; one "
                f"in-place append would poison every leg served afterwards"
            )

    def test_no_scout_field_carries_a_number_that_could_feed_a_bet(self, conn):
        """The package's no-numbers rule, enforced at this boundary too.

        `scout_age_ms` is the one number and it is about the BRIEFING, not
        about the game -- how old the words are, which is exactly what a reader
        needs in order to discount them. Every field describing the fixture is
        a string.
        """
        self._fixture(conn, tickers=("M1",))
        self._briefing(conn, "M1", board=[
            {"category": "lineup", "state": "fresh", "note": "scratched"},
        ])

        facts = parlays.leg_facts(conn, ["M1"], now_ms=10_000)["M1"]
        assert isinstance(facts["scout_headline"], str)
        for flag in facts["scout_flags"]:
            for value in flag.values():
                assert isinstance(value, str), (
                    f"{value!r} is a number on a scout flag; the desk's output "
                    f"is prose by design and a number here could be priced"
                )


class TestTheScoutNeverReachesAPrice:
    """Joe's ruling made structural on the screen, not just in the docstring.

    He chose "gates eligibility and flags" over "adjusts the fair value", so
    the scout's words must sit BESIDE the numbers and never inside one. These
    are source assertions because the property is about what the component is
    allowed to do, and a render test would only show what it happens to do
    today.
    """

    def _source(self) -> str:
        return COMPONENT.read_text(encoding="utf-8")

    def test_no_scout_field_is_arithmetic_on_a_price(self):
        """The failure this forbids is a scout field inside a calculation.

        Mutation observed red: add `leg.p_conservative * leg.scout_flags.length`
        anywhere in the component.
        """
        source = self._source()
        for token in ("scout_flags.length *", "* leg.scout_flags",
                      "scout_age_ms *", "+ leg.scout_flags",
                      "scout_headline +"):
            assert token not in source, (
                f"{token!r} puts a scout value into arithmetic; the Scout "
                f"flags and never moves the price"
            )

    def test_the_scout_does_not_sort_anything(self):
        """ADR 0071 section 2.5: a per-row fact may be shown, never ranked by.

        The same rule that forbids ordering the ladder by the Kalshi gap
        applies to a scout flag, and for a sharper reason: with five convenings
        a day, ranking by scout state would rank by WHICH GAMES JOE HAPPENED TO
        TAP, not by anything about the bets.
        """
        source = self._source()
        for token in ("sort", "Sort"):
            for field in ("scout", "scout_flags", "scout_headline"):
                assert f"{token}({field}" not in source
                assert f".{token}((a, b) => a.{field}" not in source

    def test_absent_does_not_render_as_an_alarm(self):
        """Most legs will never have been scouted, so this is the common case.

        A screen that treated `absent` as a warning would be warning almost
        always, which trains the reader to ignore the one that matters.
        """
        source = self._source()
        assert 'No scout briefing on this game.' in source

    def test_a_refusal_is_not_worded_as_a_quiet_game(self):
        """A ceiling and a quiet game are opposite facts.

        Only one of them is information about the fixture, and collapsing them
        is the flattering direction: it turns "we never looked" into "nothing
        to worry about".
        """
        source = self._source()
        i = source.index('leg.scout === "refused"')
        j = source.index('leg.scout === "failed"')
        refused = source[i:j]
        assert "ceiling" in refused and "Nothing was looked at" in refused
        quiet = "had nothing to add"
        assert quiet not in refused, (
            "the refusal branch is worded like a quiet game"
        )

    def test_a_gap_is_shown_as_a_flag_not_hidden(self):
        """`unconfirmed` and `stale_only` are absences AND flags.

        The component must not filter tiles down to findings; the backend
        already dropped only `clear`, and re-filtering here would restore the
        exact misreading `BoardTile`'s four states exist to prevent.
        """
        source = self._source()
        i = source.index("function ScoutFlags")
        block = source[i:i + 1400]
        for token in ('"fresh"', "'fresh'"):
            assert token not in block, (
                "ScoutFlags filters by tile state; that hides gaps, which are "
                "the flags most worth seeing"
            )

    def test_a_scout_flag_is_not_coloured_like_a_loss(self):
        """The palette's red means "lose" (ADR 0081).

        A word about a lineup is not a verdict about money, and colouring it
        like one would make the screen claim something the desk did not.
        """
        source = self._source()
        i = source.index("function ScoutFlags")
        block = source[i:i + 1400]
        for token in ("text-red", "bg-red", "text-lose", "bg-lose",
                      "text-green", "bg-green"):
            assert token not in block, f"{token} colours a scout flag"


class TestTheLegCarriesItsReadingsAsNumbers:
    """`method_spread_display` summarises a distribution the payload withheld.

    The card told the reader the four devig methods disagree by N points and
    gave no way to see how. These keys are that distribution, shaped for
    `DispersionStrip` so the component receives them untouched.

    **What this establishes.** That the wire names match `DispersionMethods`
    exactly; that an unsolved method is `null` and PRESENT; that the ask is a
    probability or `None`, never 0; and that no forbidden stem enters.

    **What it does not.** Anything about whether the readings are right. They
    are provenance for a number the card already showed.
    """

    def test_the_key_names_match_the_component_contract_exactly(self):
        """A rename on either side draws an EMPTY strip -- no error, no blank.

        `dispersion()` reads `methods[key]` for each of its four names and
        `continue`s on anything not a number, so a misspelled key is silently
        four absent marks. That is the failure mode with no symptom, which is
        why the names are asserted rather than trusted.
        """
        out = parlays._serialise_leg(_leg())
        assert set(out["methods"]) == {
            "p_multiplicative",
            "p_additive",
            "p_power",
            "p_shin",
            "p_conservative",
        }

    def test_the_readings_are_the_legs_own_numbers(self):
        out = parlays._serialise_leg(_leg())
        assert out["methods"]["p_multiplicative"] == 0.60
        assert out["methods"]["p_shin"] == 0.58
        assert out["methods"]["p_conservative"] == 0.58

    def test_an_unsolved_method_is_null_and_present(self):
        """`null` and absent mean different things and both must survive.

        `dispersion.ts`: absent means the route never joined `fair_prices`;
        `null` means the join ran and that method did not solve. A parlay leg
        always comes from `fair_prices`, so every key is present -- a consumer
        can rely on that, and would be wrong to if the backend dropped nulls.

        Mutation observed red: emit only the solved methods.
        """
        out = parlays._serialise_leg(
            _leg(p_by_method={"multiplicative": 0.6, "additive": None,
                              "power": None, "shin": None})
        )
        assert "p_shin" in out["methods"], (
            "an unsolved method was dropped; absent means something else"
        )
        assert out["methods"]["p_shin"] is None
        assert out["methods"]["p_additive"] is None

    def test_the_ask_is_a_probability(self):
        facts = dict(parlays._NO_FACTS)
        facts["ask_tenths"] = 550
        out = parlays._serialise_leg(_leg(), facts)
        assert out["ask_probability"] == 0.55

    def test_an_unreadable_ask_is_none_never_zero(self):
        """A 0 ask is a free contract and a real price.

        Using it for "the book could not be read" is exactly the substitution
        CLAUDE.md's unreadable-resolves-to-None convention forbids -- and here
        it would put a neutral tick at the far left of the axis, which is the
        drawing that lies.
        """
        out = parlays._serialise_leg(_leg())
        assert out["ask_probability"] is None

    def test_no_new_key_carries_a_forbidden_stem(self):
        """The payload may not carry an edge claim or its reconstructible half.

        These keys are provenance, not an edge: the gap was already
        reconstructible from `fair_percent_display` and `ask_display`, and ADR
        0071 s2.5 permits the two prices side by side. What stays forbidden is
        ranking by it, which `test_parlays_api.py` owns.
        """
        forbidden = ("breakeven", "edge", "kelly", "ev_", "suggested")
        out = parlays._serialise_leg(_leg())
        for key in list(out) + list(out["methods"]):
            assert not any(stem in key for stem in forbidden), key


class TestTheOriginsTapObeysTheRulingItExtends:
    """The 2026-08-21 ruling took this drawing off the slate row; ADR 0068
    restored it on `/market` alone; Joe put it on the parlay card 2026-08-31.

    Source assertions, because these are properties about what the component
    is ALLOWED to do -- a render test only shows what it happens to do today.
    """

    def _source(self) -> str:
        return COMPONENT.read_text(encoding="utf-8")

    def test_it_reuses_the_component_rather_than_drawing_its_own_axis(self):
        """No new SVG. The three properties the ruling preserved come with the
        component; a hand-rolled copy would carry none of them."""
        source = self._source()
        i = source.index("function LegOrigins")
        block = source[i:i + 1800]
        assert "DispersionStrip" in block
        assert "<svg" not in block, (
            "LegOrigins draws its own axis; reuse the blessed component"
        )

    def test_it_passes_a_null_book_span(self):
        """A per-leg book span needs a per-book re-devig, refused as out of
        scope. Passing anything else would draw a population that was never
        computed."""
        source = self._source()
        i = source.index("function LegOrigins")
        block = source[i:i + 1800]
        assert "books={null}" in block

    def test_it_does_not_hand_the_strip_a_used_mark_or_a_colour(self):
        """Both were removed by the ruling and must not return by the side door.

        The `used` mark re-renders the discredited point estimate; a colour on
        the ask renders a verdict the desk is barred from making.
        """
        source = self._source()
        i = source.index("function LegOrigins")
        block = source[i:i + 1800]
        for token in ("used=", "text-red", "bg-red", "text-green", "bg-green",
                      "cheap", "expensive"):
            assert token not in block, f"{token} reintroduces a verdict"

    def test_the_legs_are_not_reordered(self):
        """ADR 0071 s2.5: a per-row fact may be shown, never ranked by.

        The card's own leg order is the ladder's; sorting them here by anything
        derived from the readings would be the ordering the ruling forbids.
        """
        source = self._source()
        i = source.index("function LegOrigins")
        block = source[i:i + 1800]
        assert ".sort(" not in block


class TestTheSweetSpotIsNeverRenderedBare:
    """The single most likely way this feature goes wrong.

    A lone "6/8" beside a bet reads to a beginner as "this is a 6-out-of-8
    bet" -- the edge claim the whole design avoids, and the measured signal
    points the other way (`beta = -0.141`). These are source assertions
    because the property is about what the component may do.
    """

    def _block(self) -> str:
        source = COMPONENT.read_text(encoding="utf-8")
        i = source.index("function TrustNote")
        return source[i:i + 2000]

    def test_the_number_carries_its_subject(self):
        """`evidence`, not `value`, `score`, `rating` or `quality of bet`."""
        block = self._block()
        assert "evidence" in block
        for banned in ("good bet", "rating", "grade"):
            assert banned not in block, banned

    def test_the_unknown_count_shares_the_scores_own_styled_span(self):
        """Words are not enough; the TYPOGRAPHY has to carry them too.

        Shipped 2026-08-31 with the count outside the styled span, rendering
        `EVIDENCE 7/7 CHECKS · 1 not checked` -- a loud perfect score with a
        lowercase footnote. Every wording test passed. A reader stops at 7/7.

        The fix is that the unknown lives inside the same
        `font-mono uppercase` span, so it cannot be skimmed past, and this
        asserts the nesting rather than the presence.

        Mutation observed red: move `{unknown > 0 && ...}` back outside the
        closing `</span>`.
        """
        block = self._block()
        i = block.index("evidence {trust.passed}/{trust.known} checks")
        j = block.index("</span>", i)
        assert "unknown > 0" in block[i:j], (
            "the unknown count is rendered outside the score's own span; it "
            "reads as a footnote to a perfect score"
        )

    def test_the_unknown_count_is_shown_not_folded_in(self):
        """`total - known` is how many checks nobody ran.

        Hiding it makes the least-examined leg look like the best one -- the
        same failure `suppression.py` records for a 0.0 market width.
        Mutation observed red: render `passed`/`total` and drop the unknowns.
        """
        block = self._block()
        assert "trust.total - trust.known" in block
        assert "not checked" in block

    def test_the_denominator_is_known_not_total(self):
        """Scoring against `total` silently counts an unknown as a miss, which
        is the opposite error and equally wrong: it punishes a row for a check
        nobody ran."""
        block = self._block()
        assert "{trust.passed}/{trust.known}" in block

    def test_every_failure_is_spelled_out(self):
        """Naming one hides the one that mattered more, and choosing which to
        name would be the importance weight the module refuses to invent."""
        block = self._block()
        assert 'state === "fail"' in block
        assert ".join(" in block

    def test_a_full_score_still_disclaims_the_bet(self):
        block = self._block()
        assert "not about whether the bet wins" in block

    def test_no_colour_and_no_sort(self):
        """Red means lose (ADR 0081); a failing evidence check is not a loss.
        And ADR 0071 s2.5 bars ranking by a per-row fact."""
        block = self._block()
        for token in ("text-red", "bg-red", "text-green", "bg-green",
                      "text-positive", "text-negative", ".sort("):
            assert token not in block, token
