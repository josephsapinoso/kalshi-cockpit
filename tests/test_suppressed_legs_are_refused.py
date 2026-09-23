"""A leg the singles screen suppresses as a probable bug must never become a
parlay leg -- #79, answered by Joe 2026-09-23 as (a) "refuse a suppressed leg
outright".

Until this ticket, `suppressed_reason` reached the parlay screen as
*display* only (`leg_facts`, after `build_ladder` had already chosen its
legs). CLAUDE.md rule 1 -- a large apparent edge is a bug until proven
otherwise -- was applied by the singles screen and nowhere else: a leg the
singles path hides as untrustworthy was still selected, priced, and
multiplied into a card's headline.

What these tests establish: `drop_suppressed_legs` runs BEFORE
`_best_per_game` chooses (via `build_ladder_payload`), so a suppressed leg's
game can still contribute its next-best, unsuppressed leg instead of
dropping out; and the drop is side-aware, so suppressing a prop or total's
Over never removes its Under, which is a different `recommendations` row
that may have passed every check.

What this does not establish: which of (b)/(c) a future ticket might want
instead -- Joe answered (a), and this only tests (a).
"""

from __future__ import annotations

import pytest

from backend.parlays import (
    build_ladder_payload,
    drop_suppressed_legs,
    end_of_desk_day_ms,
    ladder_candidates,
)
from backend.store import db as store
from backend.store.db import now_ms
from tests.test_parlays_api import seed_game, seed_prop, seed_total

MAX_AGE_MS = 900_000


@pytest.fixture
def conn(tmp_path):
    c = store.init_db(tmp_path / "suppressed.db")
    yield c
    c.close()


def _recommend(conn, ticker, side, reason):
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


def _all_legs(payload) -> list[dict]:
    return [leg for card in payload["cards"] for leg in card["legs"]]


class TestASuppressedLegNeverEntersACardAndTheNextLegTakesItsPlace:
    def test_a_suppressed_leg_never_enters_a_card_and_the_next_leg_in_its_game_does(
        self, conn
    ):
        t = now_ms()
        # Two h2h candidates in ONE game, so the same-game guard has a
        # real choice to make: Alpha at 0.68 would be `g1`'s leading leg
        # (highest `p_conservative`) absent suppression, Beta at 0.30 would
        # not.
        seed_game(conn, game="g1", team="Alpha", other="Beta", p=0.68, computed_ms=t)
        seed_game(conn, game="g1", team="Beta", other="Alpha", p=0.30, computed_ms=t)
        # A second, unrelated game so `safe` (min_legs=2) can build at all.
        seed_game(conn, game="g2", team="Gamma", other="Delta", p=0.55, computed_ms=t)
        conn.commit()

        legs, _ = ladder_candidates(conn, now_ms=t, max_odds_age_ms=MAX_AGE_MS)
        alpha = next(l for l in legs if l.team == "Alpha")
        assert alpha.p_conservative > 0.5  # sanity: Alpha is g1's leader

        _recommend(conn, alpha.kalshi_market_ticker, "yes", "suspicious_edge")
        conn.commit()

        payload = build_ladder_payload(conn, now_ms=t, max_odds_age_ms=MAX_AGE_MS)

        all_legs = _all_legs(payload)
        assert alpha.kalshi_market_ticker not in {l["ticker"] for l in all_legs}
        assert payload["excluded"]["suppressed_as_probable_bug"] >= 1

        # `g1` still contributes a leg -- Beta's, the next-best in that game
        # -- rather than dropping out because its leader was suppressed.
        beta_tickers = {
            l.kalshi_market_ticker
            for l in legs
            if l.odds_event_id == alpha.odds_event_id
        } - {alpha.kalshi_market_ticker}
        assert beta_tickers & {l["ticker"] for l in all_legs}

    def test_the_filter_runs_before_best_per_game_not_after(self, conn):
        """Mutation target: dropping `drop_suppressed_legs` from
        `build_ladder_payload` (or moving it after `build_ladder`) leaves
        Alpha's suppressed leg in the payload."""
        t = now_ms()
        seed_game(conn, game="g1", team="Alpha", other="Beta", p=0.68, computed_ms=t)
        seed_game(conn, game="g1", team="Beta", other="Alpha", p=0.30, computed_ms=t)
        seed_game(conn, game="g2", team="Gamma", other="Delta", p=0.55, computed_ms=t)
        conn.commit()
        legs, _ = ladder_candidates(conn, now_ms=t, max_odds_age_ms=MAX_AGE_MS)
        alpha = next(l for l in legs if l.team == "Alpha")
        _recommend(conn, alpha.kalshi_market_ticker, "yes", "suspicious_edge")
        conn.commit()

        kept, excluded = drop_suppressed_legs(conn, legs)
        assert alpha.kalshi_market_ticker not in {l.kalshi_market_ticker for l in kept}
        assert excluded["suppressed_as_probable_bug"] == 1


class TestASuppressedOverDoesNotDropTheUnder:
    def test_a_suppressed_over_does_not_drop_the_under(self, conn):
        t = now_ms()
        seed_total(conn, game="g1", line=8.5, p=0.56)
        conn.commit()
        legs, _ = ladder_candidates(conn, now_ms=now_ms(), max_odds_age_ms=MAX_AGE_MS)
        over = next(l for l in legs if l.market == "totals" and l.side == "yes")
        under = next(l for l in legs if l.market == "totals" and l.side == "no")
        assert over.kalshi_market_ticker == under.kalshi_market_ticker

        _recommend(conn, over.kalshi_market_ticker, "yes", "suspicious_edge")
        conn.commit()

        kept, excluded = drop_suppressed_legs(conn, legs)
        kept_sides = {(l.kalshi_market_ticker, l.side) for l in kept}
        assert (over.kalshi_market_ticker, "yes") not in kept_sides
        assert (under.kalshi_market_ticker, "no") in kept_sides
        assert excluded["suppressed_as_probable_bug"] == 1

    def test_a_prop_over_suppressed_leaves_the_under_priceable(self, conn):
        """Mutation target: keying the drop by ticker alone (dropping
        `leg.side` from the filter) would remove the Under too."""
        seed_prop(conn, game="g1", player="Anthony Kay", strike=5.5, p=0.55)
        conn.commit()
        legs, _ = ladder_candidates(conn, now_ms=now_ms(), max_odds_age_ms=MAX_AGE_MS)
        over = next(l for l in legs if l.player and l.side == "yes")
        under = next(l for l in legs if l.player and l.side == "no")

        _recommend(conn, over.kalshi_market_ticker, "yes", "too_few_books")
        conn.commit()

        kept, _ = drop_suppressed_legs(conn, legs)
        assert over.kalshi_market_ticker not in {
            l.kalshi_market_ticker for l in kept if l.side == "yes"
        }
        assert under.kalshi_market_ticker in {
            l.kalshi_market_ticker for l in kept if l.side == "no"
        }


class TestAbsentIsNotSuppressed:
    """Matches the singles screen's own semantics: `leg_facts` reports
    `skeptic = "absent"` for a ticker+side with no `recommendations` row --
    never a suppression. A leg the engine has not scored yet is a
    measurement that has not run, not a bug the measurement caught.
    """

    def test_a_leg_with_no_recommendations_row_is_kept(self, conn):
        seed_game(
            conn, game="g1", team="Alpha", other="Beta", p=0.68,
            computed_ms=now_ms(),
        )
        conn.commit()
        legs, _ = ladder_candidates(
            conn, now_ms=now_ms(), max_odds_age_ms=MAX_AGE_MS
        )
        kept, excluded = drop_suppressed_legs(conn, legs)
        assert len(kept) == len(legs)
        assert excluded == {}
