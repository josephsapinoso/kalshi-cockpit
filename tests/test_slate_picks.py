"""The "who's likely to win tonight" block on `/api/slate` (ADR 0067).

What these tests establish: the block ranks by `fair_probability` alone, one
entry per game, YES-side rows only; a stale consensus and an unpriced favorite
are counted out by name; the chance≠edge sentence travels with the payload;
and no edge-shaped key exists anywhere in the block.

What they do not establish: that the consensus chance is any good. The block
renders a stored, unscored column; nothing here scores it against an outcome.
"""

from __future__ import annotations

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db as store
from backend.store.db import now_ms


async def get(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, **kwargs)


def _pick_row(
    conn,
    *,
    ticker: str,
    created_ms: int,
    side: str = "yes",
    fair: float | None = 0.6,
    ask_tenths: int = 500,
    odds_age_ms: int = 2_000,
    quote_age_ms: int = 1_000,
    odds_event_id: str | None = None,
    market_type: str | None = None,
    player_name: str | None = None,
) -> None:
    """One recommendation shaped for the picks block, positioned in time.

    Ages are stored at write; the route adds elapsed wall-clock on top, so a
    row's *live* odds age is `odds_age_ms + (now - created_ms)` — staleness in
    these tests is controlled by `created_ms`, exactly as it is in production.

    `market_type` and `player_name` are the two columns the runner writes on
    a player prop (`runner.py:3322`); both stay NULL on a team market.
    """
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, first_seen_ms, "
        "last_seen_ms, market_type, player_name) VALUES (?, ?, ?, ?, ?)",
        (ticker, created_ms, created_ms, market_type, player_name),
    )
    link_id = None
    if odds_event_id is not None:
        event_ticker = f"EVT-{odds_event_id}"
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_events (event_ticker, first_seen_ms, "
            "last_seen_ms) VALUES (?, ?, ?)",
            (event_ticker, created_ms, created_ms),
        )
        conn.execute(
            "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, "
            "odds_event_id, league, method, commence_skew_ms, linked_ms) "
            "VALUES (?, ?, 'baseball_mlb', 'exact_alias_pair', 0, ?)",
            (event_ticker, odds_event_id, created_ms),
        )
        link_id = conn.execute(
            "SELECT id FROM event_links WHERE kalshi_event_ticker = ? "
            "AND odds_event_id = ?",
            (event_ticker, odds_event_id),
        ).fetchone()["id"]
    conn.execute(
        "INSERT INTO recommendations (created_ms, strategy_config_version, "
        "ticker, side, entry_ask_tenths, fair_probability, edge_tenths, "
        "fee_predicted, ev_net_dollars, kelly_fraction, suggested_contracts, "
        "reference_contracts, kalshi_quote_age_ms, odds_age_ms, link_id, "
        "suppressed_reason, reason_text) "
        "VALUES (?, 1, ?, ?, ?, ?, 1.0, 0.1, 0.0, 0.0, 0, 0, ?, ?, ?, "
        "NULL, 'test row')",
        (created_ms, ticker, side, ask_tenths, fair, quote_age_ms,
         odds_age_ms, link_id),
    )


@pytest.fixture
def build(tmp_path):
    """A factory: seed rows via `_pick_row`, get back the app."""
    def _build(seed):
        path = tmp_path / "picks.db"
        conn = store.init_db(path)
        conn.execute(
            "INSERT INTO strategy_configs (version, created_ms, "
            "effective_from_ms, config_json, rationale) "
            "VALUES (1, 0, 0, '{}', 'test')"
        )
        seed(conn)
        conn.commit()
        conn.close()
        return create_app(AppConfig(instance_mode="demo", db_path=path))
    return _build


class TestTheRankingIsOneColumnDescending:
    async def test_picks_rank_by_fair_probability_alone(self, build):
        base = now_ms() - 60_000
        app = build(lambda conn: [
            _pick_row(conn, ticker="KXP-LOW", created_ms=base, fair=0.55),
            _pick_row(conn, ticker="KXP-TOP", created_ms=base + 1, fair=0.72),
            _pick_row(conn, ticker="KXP-MID", created_ms=base + 2, fair=0.61),
        ])
        picks = (await get(app, "/api/slate")).json()["picks"]
        assert [p["ticker"] for p in picks["ranked"]] == [
            "KXP-TOP", "KXP-MID", "KXP-LOW"
        ]

    async def test_one_pick_per_game_and_it_is_the_favorite(self, build):
        """Two linked markets are one game; the favorite side ranks, once."""
        base = now_ms() - 60_000
        app = build(lambda conn: [
            _pick_row(conn, ticker="KXG-FAV", created_ms=base, fair=0.62,
                      odds_event_id="game-1"),
            _pick_row(conn, ticker="KXG-DOG", created_ms=base + 1, fair=0.38,
                      odds_event_id="game-1"),
        ])
        picks = (await get(app, "/api/slate")).json()["picks"]
        assert [p["ticker"] for p in picks["ranked"]] == ["KXG-FAV"]

    async def test_the_freshest_row_per_ticker_is_the_one_that_speaks(
        self, build
    ):
        """The runner re-evaluates every pass; an older reading of the same
        market must not outrank the newer one."""
        base = now_ms() - 120_000
        app = build(lambda conn: [
            _pick_row(conn, ticker="KXF-1", created_ms=base, fair=0.90),
            _pick_row(conn, ticker="KXF-1", created_ms=base + 60_000,
                      fair=0.58),
        ])
        picks = (await get(app, "/api/slate")).json()["picks"]
        assert len(picks["ranked"]) == 1
        assert picks["ranked"][0]["fair_percent_display"] == "58%"


class TestWhatDoesNotRankIsCountedByName:
    async def test_a_stale_consensus_does_not_rank(self, build):
        """Live odds age is stored age plus elapsed time; 20 minutes of
        elapsed wall-clock puts this row past the 15-minute limit while it is
        still inside the slate window."""
        app = build(lambda conn: [
            _pick_row(conn, ticker="KXS-1", created_ms=now_ms() - 20 * 60_000,
                      fair=0.7),
        ])
        picks = (await get(app, "/api/slate")).json()["picks"]
        assert picks["ranked"] == []
        assert picks["not_ranked"]["stale_consensus"] == 1

    async def test_a_no_side_row_never_ranks(self, build):
        """On a NO row `team` names the YES side — the *opponent* of the
        pick — so ranking one would put the wrong name beside the chance.
        The game is counted out, not silently dropped."""
        base = now_ms() - 60_000
        app = build(lambda conn: [
            _pick_row(conn, ticker="KXN-1", created_ms=base, side="no",
                      fair=0.9),
        ])
        picks = (await get(app, "/api/slate")).json()["picks"]
        assert picks["ranked"] == []
        assert picks["not_ranked"]["favorite_unpriced"] == 1

    async def test_an_underdog_only_game_does_not_rank_as_a_likely_winner(
        self, build
    ):
        """A lone YES row at 40% prices the *underdog*; the favorite is the
        other team and no fresh row prices it. Ranking the 40% side under
        "likely winners" would be a lie of arithmetic."""
        base = now_ms() - 60_000
        app = build(lambda conn: [
            _pick_row(conn, ticker="KXU-1", created_ms=base, fair=0.40),
        ])
        picks = (await get(app, "/api/slate")).json()["picks"]
        assert picks["ranked"] == []
        assert picks["not_ranked"]["favorite_unpriced"] == 1


class TestAPlayerPropNeverRanksAsALikelyWinner:
    """Ticket #23, the bug half. A prop event inherits its game's
    `odds_event_id`, so the picks block groups a `KXMLBHIT` 1+ hit row with
    the game's moneyline and — before the exclusion — ranked whichever had
    the higher fair. #7 measured that at 131 of 192 anchor instants in the
    prop era; the numbers below are that shape (a hit prop at ~0.68 against
    a favorite at ~0.53). A home-run prop cannot reproduce it: its fair never
    reached 0.26."""

    async def test_the_prop_is_absent_and_the_game_ranks_off_its_team_row(
        self, build
    ):
        base = now_ms() - 60_000
        app = build(lambda conn: [
            _pick_row(conn, ticker="KXMLBGAME-26AUG151910SEAHOU-HOU",
                      created_ms=base, fair=0.530, odds_event_id="game-1"),
            _pick_row(conn, ticker="KXMLBHIT-26AUG151910SEAHOU-HOUYALVAREZ44-1",
                      created_ms=base + 1, fair=0.684, odds_event_id="game-1",
                      market_type="prop", player_name="Yordan Alvarez"),
        ])
        picks = (await get(app, "/api/slate")).json()["picks"]
        assert [p["ticker"] for p in picks["ranked"]] == [
            "KXMLBGAME-26AUG151910SEAHOU-HOU"
        ]
        assert picks["not_ranked"]["props_excluded"] == 1
        # The game is still a game: it ranked, so it is not counted out.
        assert picks["not_ranked"]["favorite_unpriced"] == 0

    async def test_a_prop_only_game_has_no_likely_winner(self, build):
        """With no team row in the window the game has no candidate in the
        team's own denomination — counted out as `favorite_unpriced`, and
        the prop counted as excluded; never ranked under the player's
        name."""
        base = now_ms() - 60_000
        app = build(lambda conn: [
            _pick_row(conn, ticker="KXMLBHIT-26AUG151910SEAHOU-HOUYALVAREZ44-1",
                      created_ms=base, fair=0.684, odds_event_id="game-1",
                      market_type="prop", player_name="Yordan Alvarez"),
        ])
        picks = (await get(app, "/api/slate")).json()["picks"]
        assert picks["ranked"] == []
        assert picks["not_ranked"]["props_excluded"] == 1
        assert picks["not_ranked"]["favorite_unpriced"] == 1

    async def test_either_recorded_column_alone_marks_a_prop(self, build):
        """`market_type = 'prop'` with an unreadable subtitle (NULL player)
        is still a prop; so is a player with no type. Neither branch of the
        predicate may be the only one that works, and the count is by
        distinct market — a re-evaluated prop is one market, not two."""
        base = now_ms() - 60_000
        app = build(lambda conn: [
            _pick_row(conn, ticker="KXMLBGAME-26AUG151910SEAHOU-HOU",
                      created_ms=base, fair=0.530, odds_event_id="game-1"),
            _pick_row(conn, ticker="KXMLBHIT-TYPE-ONLY", created_ms=base + 1,
                      fair=0.66, odds_event_id="game-1", market_type="prop"),
            _pick_row(conn, ticker="KXMLBHIT-PLAYER-ONLY", created_ms=base + 2,
                      fair=0.65, odds_event_id="game-1",
                      player_name="Yordan Alvarez"),
            _pick_row(conn, ticker="KXMLBHIT-PLAYER-ONLY", created_ms=base + 3,
                      fair=0.64, odds_event_id="game-1",
                      player_name="Yordan Alvarez"),
        ])
        picks = (await get(app, "/api/slate")).json()["picks"]
        assert [p["ticker"] for p in picks["ranked"]] == [
            "KXMLBGAME-26AUG151910SEAHOU-HOU"
        ]
        assert picks["not_ranked"]["props_excluded"] == 2


class TestTheBlockIsHonestAboutWhatItIsNot:
    async def test_the_note_is_the_registered_sentence(self, build):
        """Rendered verbatim by the screen, so server and page cannot
        disagree. Deleting the note on the server turns this red."""
        app = build(lambda conn: [
            _pick_row(conn, ticker="KXH-1", created_ms=now_ms() - 60_000),
        ])
        picks = (await get(app, "/api/slate")).json()["picks"]
        assert picks["note"] == (
            "Chance to win, by the books' consensus — not an edge. The "
            "price already charges for the chance: a 70% favorite costs "
            "about 70 cents, so a likely winner is not a profitable bet."
        )

    async def test_no_edge_shaped_key_exists_anywhere_in_the_block(
        self, build
    ):
        """Fair% beside break-even hands the reader the measured-negative
        edge by subtraction (`edge_tenths = 1000 × (fair − breakeven)`), so
        no key of that family may ever ride this block. Adding
        `breakeven_win_rate` to a pick turns this red."""
        app = build(lambda conn: [
            _pick_row(conn, ticker="KXK-1", created_ms=now_ms() - 60_000),
        ])
        picks = (await get(app, "/api/slate")).json()["picks"]
        forbidden = ("breakeven", "edge", "suggested", "kelly", "ev_", "stake")

        def walk(node, path=""):
            if isinstance(node, dict):
                for key, value in node.items():
                    for stem in forbidden:
                        assert stem not in key.lower(), (
                            f"{path}.{key} smuggles an edge-shaped field "
                            f"into the picks block"
                        )
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    walk(value, f"{path}[{i}]")

        walk(picks)

    async def test_a_stale_kalshi_quote_withholds_the_ask(self, build):
        """The chance can be current while the ask is not; an hours-old ask
        beside a live chance reads as a quote. Null, never a souvenir."""
        base = now_ms() - 5 * 60_000
        app = build(lambda conn: [
            # Stored quote age already past the 30s limit at write; elapsed
            # only adds to it. Odds age stays fresh so the row still ranks.
            _pick_row(conn, ticker="KXQ-1", created_ms=base, fair=0.66,
                      quote_age_ms=60_000, odds_age_ms=1_000),
        ])
        picks = (await get(app, "/api/slate")).json()["picks"]
        assert len(picks["ranked"]) == 1
        assert picks["ranked"][0]["ask_display"] is None
