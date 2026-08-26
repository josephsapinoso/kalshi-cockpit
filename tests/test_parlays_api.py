"""`GET /api/parlays` — the parlay desk's ladder payload (ADR 0070).

What these tests establish: the endpoint serves three cards from fresh
`fair_prices` consensus at FAIR value with every money string worded
server-side; a pre-v20 row (no `oldest_book_age_ms`) is refused as
unmeasurable, never treated as fresh; a started game can never be a leg; the
four disclosure sentences travel in the payload; and no edge-shaped key
exists anywhere in it.

What they do not establish: that Kalshi would sell any card near fair value.
The quoted side of that comparison exists only via the lookup path.
"""

from __future__ import annotations

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db as store
from backend.store.db import now_ms

#: Key stems that would put an edge claim (or its reconstructible half) into
#: a payload that must not carry one. `edge_tenths = 1000 * (fair -
#: breakeven)`, so serving fair beside any of these hands the reader the
#: measured-negative edge by subtraction.
FORBIDDEN_STEMS = ("breakeven", "edge", "kelly", "ev_", "suggested")


async def get(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, **kwargs)


def seed_game(
    conn,
    *,
    game: str,
    team: str,
    other: str,
    p: float = 0.62,
    computed_ms: int,
    oldest_book_age_ms: int | None = 5_000,
    commence_ms: int | None = None,
    market_status: str = "active",
) -> None:
    """One linked game: a Kalshi moneyline market for `team`, an odds fixture,
    and a YES-side h2h fair row. Team names are spelled identically on both
    ends so the alias-free resolver matches them."""
    event_ticker = f"KXMLBGAME-{game}"
    ticker = f"{event_ticker}-{team[:6].upper().replace(' ', '')}"
    commence = commence_ms if commence_ms is not None else now_ms() + 3_600_000

    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events (event_ticker, title, "
        "first_seen_ms, last_seen_ms) VALUES (?, ?, 0, 0)",
        (event_ticker, f"{other} at {team}"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, "
        "yes_side_team, market_type, status, first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, ?, 'moneyline', ?, 0, 0)",
        (ticker, event_ticker, team, market_status),
    )
    conn.execute(
        "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, "
        "odds_event_id, league, method, commence_skew_ms, linked_ms) "
        # `event_links.league` holds Kalshi's COMPETITION string, not a
        # sport key -- measured on this repo's own database:
        # 'Pro Baseball', 'Pro Basketball (W)', 'Pro Football'. This
        # fixture used to write 'baseball_mlb' here, which made it
        # agree with a reader that believed the same wrong thing and
        # hid the alias bug for the life of the parlay desk. Seed what
        # production seeds.
        "VALUES (?, ?, 'Pro Baseball', 'exact_alias_pair', 0, 0)",
        (event_ticker, game),
    )
    link_id = conn.execute(
        "SELECT id FROM event_links WHERE kalshi_event_ticker = ?",
        (event_ticker,),
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
        "commence_ms, home_team, away_team, bookmaker, market, outcome_name, "
        "price_decimal) VALUES (?, 'baseball_mlb', ?, ?, ?, ?, 'pinnacle', "
        "'h2h', ?, 1.6)",
        (computed_ms, game, commence, team, other, team),
    )
    for outcome, prob in ((team, p), (other, 1 - p - 0.02)):
        conn.execute(
            "INSERT INTO fair_prices (computed_ms, link_id, market, "
            "outcome_name, p_multiplicative, p_additive, p_power, p_shin, "
            "p_conservative, book_count, books_used, anchored_on_sharp, "
            "oldest_book_age_ms) "
            "VALUES (?, ?, 'h2h', ?, ?, ?, ?, ?, ?, 3, '[]', 1, ?)",
            (
                computed_ms, link_id, outcome,
                prob + 0.02, prob + 0.01, prob + 0.015, prob + 0.005,
                prob, oldest_book_age_ms,
            ),
        )


@pytest.fixture
def build(tmp_path):
    def _build(seed):
        path = tmp_path / "parlays.db"
        conn = store.init_db(path)
        seed(conn)
        conn.commit()
        conn.close()
        return create_app(AppConfig(instance_mode="demo", db_path=path))
    return _build


def _fresh_slate(conn, n: int = 6, start_p: float = 0.74) -> None:
    base = now_ms() - 30_000
    for i in range(n):
        seed_game(
            conn,
            game=f"game-{i}",
            team=f"Team Alpha{i}",
            other=f"Team Beta{i}",
            p=start_p - i * 0.03,
            computed_ms=base,
        )


class TestTheLadderBuilds:
    async def test_six_fresh_games_fill_every_card(self, build):
        app = build(_fresh_slate)
        body = (await get(app, "/api/parlays")).json()
        by_key = {c["key"]: c for c in body["cards"]}
        assert len(by_key["safe"]["legs"]) == 3
        assert len(by_key["middle"]["legs"]) == 4
        assert len(by_key["lottery"]["legs"]) == 6
        assert len(by_key["longshot"]["legs"]) == 3
        assert len(by_key["soon"]["legs"]) == 3
        assert len(by_key["agreed"]["legs"]) == 3
        assert all(c["not_built_reason"] is None for c in body["cards"])

    async def test_the_wire_carries_every_registered_card(self, build):
        """The payload is the screen's whole source of truth for which cards
        exist -- `ParlayCards.tsx` maps over `cards` and knows nothing else."""
        from backend.core.ladder import CARD_SHAPES

        app = build(_fresh_slate)
        body = (await get(app, "/api/parlays")).json()
        assert [c["key"] for c in body["cards"]] == [r.key for r in CARD_SHAPES]

    async def test_every_card_says_what_it_is_built_or_not(self, build):
        """Six cards on one screen cannot be told apart from their legs, and a
        card that refused has no legs to be told apart by. Server-worded, like
        every other string on this payload (2026-08-26)."""
        app = build(lambda conn: _fresh_slate(conn, n=2))
        body = (await get(app, "/api/parlays")).json()
        unbuilt = [c for c in body["cards"] if c["not_built_reason"] is not None]
        built = [c for c in body["cards"] if c["not_built_reason"] is None]
        # Vacuity guard: this fixture has to contain both kinds to say anything.
        assert unbuilt and built
        assert all(c["what_it_is"] for c in body["cards"])

    async def test_each_leg_is_the_games_favorite_once(self, build):
        app = build(lambda conn: _fresh_slate(conn, n=3))
        body = (await get(app, "/api/parlays")).json()
        safe = next(c for c in body["cards"] if c["key"] == "safe")
        games = [l["event_title"] for l in safe["legs"]]
        assert len(games) == len(set(games))
        assert all(l["team"].startswith("Team Alpha") for l in safe["legs"])

    async def test_a_thin_slate_says_why_in_words(self, build):
        app = build(lambda conn: _fresh_slate(conn, n=2))
        body = (await get(app, "/api/parlays")).json()
        by_key = {c["key"]: c for c in body["cards"]}
        assert by_key["lottery"]["not_built_reason"] == (
            "needs 6 fresh games and the slate has 2"
        )
        assert by_key["lottery"]["legs"] == []

    async def test_money_strings_are_rendered_server_side(self, build):
        """The client does no money arithmetic: every stake preset arrives
        pre-priced, with the $5 default flagged."""
        app = build(lambda conn: _fresh_slate(conn, n=3))
        body = (await get(app, "/api/parlays")).json()
        safe = next(c for c in body["cards"] if c["key"] == "safe")
        stakes = safe["at_stakes"]
        assert [s["stake_display"] for s in stakes] == [
            "$1.00", "$5.00", "$10.00", "$20.00"
        ]
        assert [s["is_default"] for s in stakes] == [False, True, False, False]
        assert all("payout_display" in s for s in stakes)
        assert safe["joint"]["conservative_percent_display"].endswith("%")


class TestRefusals:
    async def test_an_unmeasurable_age_is_refused_and_counted(self, build):
        """Pre-v20 rows carry NULL `oldest_book_age_ms`; the honest reading
        is 'age unknown', never 'age zero'."""
        def seed(conn):
            _fresh_slate(conn, n=2)
            seed_game(
                conn, game="null-age", team="Team NullAge", other="Team X",
                p=0.9, computed_ms=now_ms() - 30_000, oldest_book_age_ms=None,
            )
        app = build(seed)
        body = (await get(app, "/api/parlays")).json()
        safe = next(c for c in body["cards"] if c["key"] == "safe")
        assert all(l["team"] != "Team NullAge" for l in safe["legs"])
        assert body["excluded"]["age_unmeasurable"] >= 1

    async def test_a_stale_consensus_is_refused_and_counted(self, build):
        def seed(conn):
            _fresh_slate(conn, n=2)
            seed_game(
                conn, game="stale", team="Team Stale", other="Team X",
                p=0.9, computed_ms=now_ms() - 3_600_000,
            )
        app = build(seed)
        body = (await get(app, "/api/parlays")).json()
        safe = next(c for c in body["cards"] if c["key"] == "safe")
        assert all(l["team"] != "Team Stale" for l in safe["legs"])
        assert body["excluded"]["stale_consensus"] >= 1

    async def test_a_started_game_can_never_be_a_leg(self, build):
        def seed(conn):
            _fresh_slate(conn, n=2)
            seed_game(
                conn, game="started", team="Team Started", other="Team X",
                p=0.9, computed_ms=now_ms() - 30_000,
                commence_ms=now_ms() - 60_000,
            )
        app = build(seed)
        body = (await get(app, "/api/parlays")).json()
        for card in body["cards"]:
            assert all(l["team"] != "Team Started" for l in card["legs"])

    async def test_a_finalized_market_is_refused(self, build):
        def seed(conn):
            _fresh_slate(conn, n=2)
            seed_game(
                conn, game="done", team="Team Done", other="Team X",
                p=0.9, computed_ms=now_ms() - 30_000,
                market_status="finalized",
            )
        app = build(seed)
        body = (await get(app, "/api/parlays")).json()
        safe = next(c for c in body["cards"] if c["key"] == "safe")
        assert all(l["team"] != "Team Done" for l in safe["legs"])
        assert body["excluded"]["market_closed"] >= 1


class TestHonesty:
    async def test_no_edge_shaped_key_anywhere_in_the_payload(self, build):
        """Fair% beside a breakeven reconstructs the measured-negative edge by
        subtraction; the ladder therefore carries no such key at any depth."""
        app = build(_fresh_slate)
        body = (await get(app, "/api/parlays")).json()

        def walk(node, path="$"):
            if isinstance(node, dict):
                for key, value in node.items():
                    lowered = key.lower()
                    for stem in FORBIDDEN_STEMS:
                        assert stem not in lowered, f"{path}.{key}"
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    walk(value, f"{path}[{i}]")

        walk(body)

    async def test_the_four_disclosure_sentences_travel_verbatim(self, build):
        app = build(lambda conn: None)
        body = (await get(app, "/api/parlays")).json()
        notes = body["notes"]
        assert set(notes) == {"chance", "fair_value", "enter_only", "fee"}
        assert "enter-only" in notes["enter_only"]
        assert "40 of 40" in notes["enter_only"]
        assert "unverified" in notes["fee"]
        assert "not an edge" in notes["chance"]
        assert "FAIR value" in notes["fair_value"]

    async def test_the_headline_carries_its_method_band(self, build):
        app = build(lambda conn: _fresh_slate(conn, n=3))
        body = (await get(app, "/api/parlays")).json()
        joint = next(c for c in body["cards"] if c["key"] == "safe")["joint"]
        assert joint["method_range_display"] is not None
        assert "–" in joint["method_range_display"]
        assert "correlation_note" in joint
