"""The Under of a total or prop is a parlay leg: the NO of Kalshi's Over market.

Until 2026-09-14 every parlay leg was a Kalshi YES by construction, and the
ladder's prop arm dropped the Under row without a count. A "likeliest" card
built from Over rows alone leans to overs. Now a row whose outcome is
`Under` becomes a `CandidateLeg` with `side = "no"` on the same market the
Over row matched, its own `p_conservative` (the Under row's, never one minus
the Over's), and a label that says which way it goes. The side travels
through the wire (`serialise_leg`), the lookup echo, the venue's body
(`lookup_combo`) and into `parlay_lookups.selected_legs`, which is what a
recorded position and `/hedge` read.

What these establish: the pool emits both sides of a prop and a total; at
most one of them (one leg per fixture) reaches a card; the joint memo key
carries the side; the venue is asked for each leg's own side; and a venue
echo that flips a side is a mismatch, not a spelling.

What they do not establish: that any Kalshi collection accepts a mixed-side
card. The fixtures name `is_all_yes` collections; the first live lookup of a
card carrying a NO leg is the measurement, and a refusal there is a venue
fact to record, not a defect here.
"""

from __future__ import annotations

from dataclasses import replace

from backend.core.ladder import _best_per_game, _joint_key
from backend.kalshi.combos import echoed_legs, lookup_combo
from backend.parlays import _serialise_leg, ladder_candidates, leg_details_for
import pytest

from backend.store import db as store
from backend.store.db import now_ms
from tests.test_ladder import leg
from tests.test_parlays_api import seed_prop, seed_total


@pytest.fixture
def conn(tmp_path):
    c = store.init_db(tmp_path / "under.db")
    yield c
    c.close()


class TestThePoolEmitsBothSides:
    def test_a_prop_under_row_is_a_no_leg_on_the_over_market(self, conn):
        seed_prop(conn, game="g1", player="Anthony Kay", strike=5.5, p=0.55)
        conn.commit()
        legs, excluded = ladder_candidates(
            conn, now_ms=now_ms(), max_odds_age_ms=900_000
        )
        props = sorted((l.side, l) for l in legs if l.player)
        assert [side for side, _ in props] == ["no", "yes"]
        under, over = props[0][1], props[1][1]
        assert under.kalshi_market_ticker == over.kalshi_market_ticker
        assert under.label == "NO on Anthony Kay: 6+ strikeouts"
        assert over.label == "Anthony Kay: 6+ strikeouts"
        # The Under row's OWN consensus: seeded as 1 - p - 0.02.
        assert round(under.p_conservative, 2) == 0.43
        assert "prop_no_kalshi_rung" not in excluded, excluded

    def test_a_total_under_row_is_a_no_leg_with_kalshis_phrasing_turned(self, conn):
        seed_total(conn, game="g1", line=8.5, p=0.56)
        conn.commit()
        legs, _ = ladder_candidates(conn, now_ms=now_ms(), max_odds_age_ms=900_000)
        totals = {l.side: l for l in legs if l.market == "totals"}
        assert set(totals) == {"yes", "no"}
        assert totals["no"].label == "Under 8.5 runs scored"
        assert totals["yes"].label == "Over 8.5 runs scored"
        assert totals["no"].kalshi_market_ticker == totals["yes"].kalshi_market_ticker
        assert totals["no"].team is None and totals["no"].player is None

    def test_a_team_leg_is_always_yes(self, conn):
        from tests.test_parlays_api import seed_game

        seed_game(conn, game="g1", team="Alpha", other="Beta", computed_ms=now_ms())
        conn.commit()
        legs, _ = ladder_candidates(conn, now_ms=now_ms(), max_odds_age_ms=900_000)
        assert legs and all(l.side == "yes" for l in legs)

    def test_the_wire_carries_the_side(self, conn):
        seed_total(conn, game="g1", line=8.5, p=0.56)
        conn.commit()
        legs, _ = ladder_candidates(conn, now_ms=now_ms(), max_odds_age_ms=900_000)
        under = next(l for l in legs if l.side == "no")
        assert _serialise_leg(under)["side"] == "no"
        assert leg_details_for([under])[
            (under.kalshi_event_ticker, under.kalshi_market_ticker)
        ]["side"] == "no"


class TestOverAndUnderOfOneGameCannotBothBeTaken:
    def test_one_leg_per_fixture_holds_across_sides(self):
        over = replace(leg("g1", p=0.56, market="totals", point=8.5, ticker="T"), team=None)
        under = replace(over, side="no", p_conservative=0.42, label="Under 8.5 runs scored")
        kept = _best_per_game([over, under], prefer_spreads=False)
        assert len(kept) == 1
        assert kept[0].side == "yes"  # the likelier one


class TestTheJointMemoKnowsTheSide:
    def test_yes_and_no_of_one_market_have_different_keys(self):
        """Mutation observed red: drop `leg.side` from `_joint_key` -- the
        Under of a market would be served the Over's cached joint."""
        over = replace(leg("g1", p=0.56, market="totals", point=8.5, ticker="T"), team=None)
        under = replace(over, side="no")
        assert _joint_key([over]) != _joint_key([under])


class _CapturingApi:
    def __init__(self):
        self.bodies = []

    async def request(self, method, path, json_body=None):
        self.bodies.append((method, path, json_body))
        return {"market_ticker": "KXMVE-X", "market": {"ticker": "KXMVE-X"}}


class TestTheVenueIsAskedForEachLegsOwnSide:
    async def test_lookup_combo_posts_per_leg_sides(self):
        api = _CapturingApi()
        await lookup_combo(
            api, "KXMVESPORTSMULTIGAMEEXTENDED-R",
            [("E1", "M1", "yes"), ("E2", "M2", "no"), ("E3", "M3")],
            side="yes", allow_market_creation=True,
        )
        (_, _, body), = api.bodies
        assert body["selected_markets"] == [
            {"event_ticker": "E1", "market_ticker": "M1", "side": "yes"},
            {"event_ticker": "E2", "market_ticker": "M2", "side": "no"},
            {"event_ticker": "E3", "market_ticker": "M3", "side": "yes"},
        ]

    def test_an_echo_that_flips_a_side_is_a_mismatch(self):
        """Mutation observed red: `_leg_sides` ignoring the third element
        makes the desk's NO leg compare as YES and the flip pass."""
        response = {"market": {"mve_selected_legs": [
            {"event_ticker": "E1", "market_ticker": "M1", "side": "yes"},
            {"event_ticker": "E2", "market_ticker": "M2", "side": "yes"},
        ]}}
        echo = echoed_legs([("E1", "M1", "yes"), ("E2", "M2", "no")], response)
        assert echo.is_mismatch
        assert "M2" in echo.detail

    def test_a_faithful_echo_matches(self):
        response = {"market": {"mve_selected_legs": [
            {"event_ticker": "E2", "market_ticker": "M2", "side": "no"},
            {"event_ticker": "E1", "market_ticker": "M1", "side": "yes"},
        ]}}
        echo = echoed_legs([("E1", "M1", "yes"), ("E2", "M2", "no")], response)
        assert echo.verdict == "match"


class TestAnUnderLegQuotesTheUnderSide:
    """The card's ask and depth on an Under leg are the NO side's.

    Until 2026-09-15 `leg_facts` was keyed by ticker and read the YES side
    for every leg, so an Under printed the Over's price and the Over's depth
    on its own row -- the wrong price, on the screen whose job is price
    transparency (ADR 0071). Mutation observed red: `_ask_facts_for_side`
    returning the YES triple for `"no"`.
    """

    def _quote(self, conn, ticker):
        # yes_bid 400 / qty 7  ->  NO ask = 600, depth 7
        # no_bid  450 / qty 12 -> YES ask = 550, depth 12
        conn.execute(
            "INSERT INTO kalshi_quotes (ticker, observed_ms, confirmed_ms, seq, "
            "source, yes_bid_tenths, yes_bid_qty, no_bid_tenths, no_bid_qty) "
            "VALUES (?, ?, ?, NULL, 'rest', 400, 7.0, 450, 12.0)",
            (ticker, now_ms(), now_ms()),
        )
        conn.commit()

    def test_over_and_under_of_one_market_print_different_asks(self, conn):
        from backend.parlays import leg_facts

        seed_total(conn, game="g1", line=8.5, p=0.56)
        conn.commit()
        legs, _ = ladder_candidates(conn, now_ms=now_ms(), max_odds_age_ms=900_000)
        totals = {l.side: l for l in legs if l.market == "totals"}
        ticker = totals["yes"].kalshi_market_ticker
        self._quote(conn, ticker)
        facts = leg_facts(conn, [ticker], now_ms=now_ms())[ticker]
        over = _serialise_leg(totals["yes"], facts)
        under = _serialise_leg(totals["no"], facts)
        assert (over["ask_display"], over["depth_at_ask"]) == ("55c", 12.0)
        assert (under["ask_display"], under["depth_at_ask"]) == ("60c", 7.0)
        assert over["ask_probability"] == 0.55
        assert under["ask_probability"] == 0.6

    def test_a_side_that_is_neither_is_refused_not_defaulted(self):
        from backend.parlays import _NO_FACTS, _ask_facts_for_side

        with pytest.raises(ValueError):
            _ask_facts_for_side(dict(_NO_FACTS), "maybe")


class TestATeamLessLegCarriesItsGame:
    """A total's label names no game; `event_title` is where the game is.

    The card serialised it since ADR 0051 and drew it nowhere; on 2026-09-15
    the totals card showed three "Under 8.5 runs scored" rows Joe could not
    tell apart. The wire keeps carrying it, and the lookup blob a position
    is recorded from now carries it too.
    """

    def test_the_wire_and_the_lookup_blob_carry_the_event_title(self, conn):
        seed_total(conn, game="g1", line=8.5, p=0.56)
        conn.commit()
        legs, _ = ladder_candidates(conn, now_ms=now_ms(), max_odds_age_ms=900_000)
        under = next(l for l in legs if l.side == "no")
        assert under.team is None
        wire = _serialise_leg(under)
        assert wire["event_title"] and wire["event_title"] != under.label
        details = leg_details_for([under])[
            (under.kalshi_event_ticker, under.kalshi_market_ticker)
        ]
        assert details["event_title"] == wire["event_title"]


class TestAnUnderPropCarriesItsOwnVerdict:
    """The skeptic's verdict on an Under prop is the Under's, not the Over's.

    `2d8de82` made the ASK side-aware and left the VERDICT reader in the same
    function keyed by ticker with `side = 'yes'` hardcoded. A prop is the one
    market where that bites: `_price_prop_event` writes a `recommendations`
    row per side (`runner.py:2017`), while `_price_totals_event` writes none
    at all, so totals were immune for an unrelated reason and the surviving
    half stayed invisible. Two misreadings, both silent:

        the reason    the Under's row showed the OVER's `suppressed_reason`,
                      which `score_trust` also consumes
        the `checked` a YES row's mere existence stamped `checked` on a side
                      the skeptic had never scored -- a measurement that never
                      ran, reported as one that did

    Mutations observed red, one per test: `_verdict_facts_for_side` returning
    the YES pair for `"no"`; and the `(ticker, "no")` branch of `leg_facts`
    deleted.
    """

    def _recommend(self, conn, ticker, side, reason):
        conn.execute(
            "INSERT OR IGNORE INTO strategy_configs (version, created_ms, "
            "effective_from_ms, config_json, rationale) "
            "VALUES (1, ?, ?, '{}', 'test')",
            (now_ms(), now_ms()),
        )
        conn.execute(
            "INSERT INTO recommendations (created_ms, strategy_config_version, "
            "ticker, side, entry_ask_tenths, fair_probability, edge_tenths, "
            "fee_predicted, ev_net_dollars, kelly_fraction, suggested_contracts, "
            "kalshi_quote_age_ms, odds_age_ms, reason_text, suppressed_reason) "
            "VALUES (?, 1, ?, ?, 500, 0.5, 0.0, 0.0, 0.0, 0.0, 0, 0, 0, "
            "'No edge.', ?)",
            (now_ms(), ticker, side, reason),
        )
        conn.commit()

    def _sides(self, conn):
        legs, _ = ladder_candidates(conn, now_ms=now_ms(), max_odds_age_ms=900_000)
        return {l.side: l for l in legs if l.player}

    def test_each_side_of_a_prop_reports_its_own_suppression(self, conn):
        from backend.parlays import leg_facts

        seed_prop(conn, game="g1", player="Anthony Kay", strike=5.5, p=0.55)
        conn.commit()
        props = self._sides(conn)
        ticker = props["yes"].kalshi_market_ticker
        self._recommend(conn, ticker, "yes", "too_few_books")
        self._recommend(conn, ticker, "no", "stale_odds")
        facts = leg_facts(conn, [ticker], now_ms=now_ms())[ticker]
        over = _serialise_leg(props["yes"], facts)
        under = _serialise_leg(props["no"], facts)
        assert (over["skeptic"], over["suppressed_reason"]) == (
            "checked",
            "too_few_books",
        )
        assert (under["skeptic"], under["suppressed_reason"]) == (
            "checked",
            "stale_odds",
        )

    def test_a_side_the_skeptic_never_scored_is_absent_not_checked(self, conn):
        """The flattering half: `checked` claims twelve checks that never ran."""
        from backend.parlays import leg_facts

        seed_prop(conn, game="g1", player="Anthony Kay", strike=5.5, p=0.55)
        conn.commit()
        props = self._sides(conn)
        ticker = props["yes"].kalshi_market_ticker
        self._recommend(conn, ticker, "yes", None)
        facts = leg_facts(conn, [ticker], now_ms=now_ms())[ticker]
        assert _serialise_leg(props["yes"], facts)["skeptic"] == "checked"
        under = _serialise_leg(props["no"], facts)
        assert under["skeptic"] == "absent"
        assert under["suppressed_reason"] is None

    def test_a_side_that_is_neither_is_refused_not_defaulted(self):
        from backend.parlays import _NO_FACTS, _verdict_facts_for_side

        with pytest.raises(ValueError):
            _verdict_facts_for_side(dict(_NO_FACTS), "maybe")
