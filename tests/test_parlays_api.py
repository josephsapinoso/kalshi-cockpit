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

from pathlib import Path

import httpx
import pytest

from backend import parlays
from backend.core.ladder import _best_per_game, build_ladder
from backend.parlays import end_of_desk_day_ms, ladder_candidates
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
    # **Clamped inside the desk day, or this fixture makes the whole suite
    # clock-fragile.** `ladder_candidates` now drops a leg kicking off after
    # `end_of_desk_day_ms`, so a bare `now + 1h` default silently empties every
    # ladder when the suite runs in the hour before the 4am rollover. The
    # fixture means "a game in tonight's slate"; it now says so at every hour
    # of the day. The bound itself is exercised deliberately, with an injected
    # clock, by `TestTheDeskIsScopedToTonight`.
    commence = (
        commence_ms
        if commence_ms is not None
        else min(now_ms() + 3_600_000, end_of_desk_day_ms(now_ms()) - 60_000)
    )

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


def seed_prop(
    conn,
    *,
    game: str,
    player: str,
    strike: float,
    p: float,
    market: str = "pitcher_strikeouts",
    kalshi_player: str | None = None,
    title: str | None = None,
    book_point: float | None = None,
    oldest_book_age_ms: int | None = 5_000,
    commence_ms: int | None = None,
) -> None:
    """One linked MLB prop rung: a Kalshi ladder market and its consensus row.

    The prop EVENT is its own Kalshi event and links separately, but it
    inherits the GAME's `odds_event_id` -- that inheritance is what
    `link_prop_event` produces in production, and it is the property the
    one-leg-per-fixture guard depends on, so the fixture reproduces it rather
    than inventing a fresh id.

    `book_point` defaults to `strike` because they are one number by identity;
    passing them apart is how a test asks whether anything derives one from
    the other.
    """
    # **One prop event per game PER STATISTIC, holding every player** -- not
    # one per player. Measured on `tests/fixtures/events_mlb_props_nested.json`:
    # `KXMLBTB-26AUG151310CWSDET` carries 66 markets across 18 distinct
    # players, and batters' total-base rungs cluster on 0.5/1.5/2.5, so one
    # `link_id` covers many players sharing a line. Seeding an event per
    # player instead would give each its own `link_id` and make the dedupe
    # key look unnecessary -- the fixture has to reproduce the collision the
    # key exists to prevent, or the test certifies nothing.
    prop_event = f"KXMLB-{game}-{market}"
    ticker = f"{prop_event}-{player[:6].upper().replace(' ', '')}-{strike}"
    # **Clamped inside the desk day, or this fixture makes the whole suite
    # clock-fragile.** `ladder_candidates` now drops a leg kicking off after
    # `end_of_desk_day_ms`, so a bare `now + 1h` default silently empties every
    # ladder when the suite runs in the hour before the 4am rollover. The
    # fixture means "a game in tonight's slate"; it now says so at every hour
    # of the day. The bound itself is exercised deliberately, with an injected
    # clock, by `TestTheDeskIsScopedToTonight`.
    commence = (
        commence_ms
        if commence_ms is not None
        else min(now_ms() + 3_600_000, end_of_desk_day_ms(now_ms()) - 60_000)
    )
    point = strike if book_point is None else book_point
    shown = kalshi_player or player
    computed_ms = now_ms()

    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events (event_ticker, title, "
        "first_seen_ms, last_seen_ms) VALUES (?, ?, 0, 0)",
        (prop_event, "Chicago WS vs Detroit: Strikeouts"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, title, "
        "player_name, market_type, strike, status, first_seen_ms, "
        "last_seen_ms) VALUES (?, ?, ?, ?, 'prop', ?, 'active', 0, 0)",
        (
            ticker,
            prop_event,
            title or f"{shown}: {int(strike + 0.5)}+ strikeouts?",
            shown,
            strike,
        ),
    )
    conn.execute(
        "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, "
        "odds_event_id, league, method, commence_skew_ms, linked_ms) "
        "VALUES (?, ?, 'Pro Baseball', 'prop_fixture_segment', 0, 0)",
        (prop_event, game),
    )
    link_id = conn.execute(
        "SELECT id FROM event_links WHERE kalshi_event_ticker = ?",
        (prop_event,),
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
        "commence_ms, home_team, away_team, bookmaker, market, outcome_name, "
        "outcome_description, outcome_point, price_decimal) "
        "VALUES (?, 'baseball_mlb', ?, ?, 'Detroit', 'Chicago WS', 'pinnacle', "
        "?, 'Over', ?, ?, 1.8)",
        (computed_ms, game, commence, market, player, point),
    )
    for outcome, prob in (("Over", p), ("Under", 1 - p - 0.02)):
        conn.execute(
            "INSERT INTO fair_prices (computed_ms, link_id, market, "
            "outcome_name, outcome_description, outcome_point, "
            "p_multiplicative, p_additive, p_power, p_shin, "
            "p_conservative, book_count, books_used, anchored_on_sharp, "
            "oldest_book_age_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 3, '[]', 1, ?)",
            (
                computed_ms, link_id, market, outcome, player, point,
                prob + 0.02, prob + 0.01, prob + 0.015, prob + 0.005,
                prob, oldest_book_age_ms,
            ),
        )


@pytest.fixture
def conn(tmp_path):
    """A bare initialised DB, for tests reading the pool rather than the API."""
    c = store.init_db(tmp_path / "pool.db")
    yield c
    c.close()


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
        pre-priced, with exactly one flagged as the default.

        **Re-pointed 2026-08-26, not weakened.** This asserted the literal
        amounts `$1/$5/$10/$20`, which made a change to WHICH stakes are
        offered indistinguishable from a break in the no-arithmetic rule it
        exists to protect. The presets moved to Joe's own range that day; the
        property did not. It now reads the constant, so the amounts are pinned
        once, by `TestTheStakePresetsAreTheOperatorsOwnRange`.
        """
        app = build(lambda conn: _fresh_slate(conn, n=3))
        body = (await get(app, "/api/parlays")).json()
        safe = next(c for c in body["cards"] if c["key"] == "safe")
        stakes = safe["at_stakes"]
        assert [s["stake_cents"] for s in stakes] == list(
            parlays.STAKE_PRESETS_CENTS
        )
        assert all(s["stake_display"].startswith("$") for s in stakes)
        assert sum(s["is_default"] for s in stakes) == 1
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


class TestTheStakePresetsAreTheOperatorsOwnRange:
    """Re-sized 2026-08-26 from someone else's bet to Joe's.

    They were $1/$5/$10/$20 defaulting to $5, framed by ADR 0070 §2.7 around
    the cousin's $4.99 ticket — the bet that prompted the desk, but not a bet
    Joe has ever placed. Asked directly, in his words: *"I bet .25 cents to 2
    or 3 bucks on parlays right now."*

    Three of the four were amounts he would never stake and the default sat
    above his ceiling, so every payout figure on the card was priced for
    somebody else's bet. ADR 0071 §2.1 is why that matters: the desk informs
    bets that are happening anyway, and a stake row he would not choose
    informs nothing.

    **This is a display range, not a limit** — nothing here caps an order.
    """

    #: His stated range, in cents. The presets must lie inside it, and the
    #: ends must be reachable: a range whose extremes cannot be selected is a
    #: narrower range than the one he gave.
    LOW, HIGH = 25, 300

    def test_every_preset_is_inside_the_range_he_named(self):
        for cents in parlays.STAKE_PRESETS_CENTS:
            assert self.LOW <= cents <= self.HIGH, (
                f"${cents / 100:.2f} is outside the 25c-$3 range Joe stated; "
                f"a preset he would not choose prices a bet he would not place"
            )

    def test_both_ends_of_his_range_are_offered(self):
        """Not merely 'inside' — the extremes must be selectable."""
        assert min(parlays.STAKE_PRESETS_CENTS) == self.LOW
        assert max(parlays.STAKE_PRESETS_CENTS) == self.HIGH

    def test_the_default_is_one_he_would_actually_pick(self):
        assert parlays.DEFAULT_STAKE_CENTS in parlays.STAKE_PRESETS_CENTS
        assert self.LOW <= parlays.DEFAULT_STAKE_CENTS <= self.HIGH

    def test_the_presets_are_distinct_and_ascending(self):
        """Two rows priced the same is a row wasted on a screen with four."""
        presets = list(parlays.STAKE_PRESETS_CENTS)
        assert presets == sorted(presets)
        assert len(set(presets)) == len(presets)

    async def test_the_served_rows_match_the_constant(self, build):
        """The payload must not carry a stake the constant does not name."""
        app = build(lambda conn: _fresh_slate(conn, n=4))
        body = (await get(app, "/api/parlays")).json()
        built = [c for c in body["cards"] if c["joint"] is not None]
        assert built, "fixture built no cards"
        for card in built:
            served = [row["stake_cents"] for row in card["at_stakes"]]
            assert served == list(parlays.STAKE_PRESETS_CENTS)
            assert sum(row["is_default"] for row in card["at_stakes"]) == 1


class TestAZeroFairProbabilityNeverReachesArithmetic:
    """The live outage of 2026-08-28, in two halves.

    `/api/parlays` rendered "Backend unreachable" on the phone and the
    scheduler logged three consecutive failing passes, all
    `ZeroDivisionError: float division by zero` at
    `_stake_row`'s `contracts = stake_cents / (joint * 100.0)`.

    The joint is a PRODUCT over legs (`running *= leg.p_conservative`), so a
    single leg quoted at 0.0 zeroes the whole card. And because
    `build_ladder_payload` is called from `score_settle_and_alert` as well as
    from the route, the same exception took out the tail of every pass with
    it -- parlay cards, the daily digest and `log_gate_progress` all stopped.
    **One unpriceable leg stopped the alerting half of the loop.**

    Two guards, deliberately overlapping, because the second is the one the
    outage argues for: the leg is refused upstream so no such card is ever
    built, AND the division cannot happen even if one is. A shared helper
    called from a loop that must not die does not get to trust its caller.

    **What this does not establish:** why a devig returned 0.0 for a market
    Kalshi was still quoting. That is upstream of the parlay desk and is not
    diagnosed here -- the refusal is counted so the rate becomes visible
    rather than silent.
    """

    def test_a_zero_probability_leg_is_refused_and_counted(self, conn):
        seed_prop(conn, game="g1", player="Anthony Kay", strike=5.5, p=0.0)
        conn.commit()
        legs, excluded = ladder_candidates(
            conn, now_ms=now_ms(), max_odds_age_ms=900_000
        )
        assert [l for l in legs if l.player] == [], (
            "a leg with no fair probability entered the pool; the joint is a "
            "product, so it takes every card it touches to zero"
        )
        assert excluded.get("fair_probability_not_positive") == 1, excluded

    def test_a_healthy_leg_beside_it_still_enters(self, conn):
        """The refusal is per row, not per fixture.

        Written because the cheap implementation -- bailing on the whole
        event when one rung is unreadable -- would pass the test above and
        silently empty the pool on a slate with one bad row in it.
        """
        seed_prop(conn, game="g1", player="Anthony Kay", strike=5.5, p=0.0)
        seed_prop(conn, game="g1", player="Tarik Skubal", strike=5.5, p=0.61)
        conn.commit()
        legs, excluded = ladder_candidates(
            conn, now_ms=now_ms(), max_odds_age_ms=900_000
        )
        assert [l.player for l in legs if l.player] == ["Tarik Skubal"]
        assert excluded.get("fair_probability_not_positive") == 1, excluded

    def test_the_stake_row_refuses_a_zero_joint_rather_than_dividing(self):
        """The backstop, called directly.

        This is the exact call that raised on live. It must not raise, and it
        must not invent a contract count -- a fabricated payout on a card
        nobody can price is CLAUDE.md rule 1's failure, not a rounding
        nicety.
        """
        row = parlays._stake_row(500, 0.0)
        assert row["contracts_display"] == "\u2014"
        assert row["payout_display"] == "\u2014"
        assert row["stake_display"] == "$5.00"

    def test_a_negative_joint_is_refused_too(self):
        """`<= 0`, not `== 0`. A negative probability is more broken than a
        zero one and would otherwise render a negative payout."""
        row = parlays._stake_row(500, -0.2)
        assert row["contracts_display"] == "\u2014"

    def test_an_ordinary_joint_still_computes(self):
        """The guard must not swallow the normal path."""
        row = parlays._stake_row(500, 0.25)
        assert row["contracts_display"] != "\u2014"
        assert row["payout_display"] != "\u2014"


class TestPropLegsEnterThePool:
    """MLB player-prop rungs as parlay candidates.

    These read `ladder_candidates` (the pool) rather than `/api/parlays` (the
    cards) on purpose: every registered recipe is gated to the two team
    markets, so a prop reaches the pool and no card. That separation is the
    design, not a gap -- see `TestRecipesAreGatedToTheirMarkets` in
    `test_ladder.py` for why an ungated pool rewrites every card.
    """

    def test_two_players_at_one_rung_are_distinct_candidates(self, conn):
        """The defect the `outcome_description` key exists to prevent.

        Keyed on (link, market, outcome, point) alone -- the shape this had
        before props entered -- two pitchers in one game quoted at the same
        rung produce the identical key `(1, 'pitcher_strikeouts', 'Over', 5.5)`
        and `setdefault` silently keeps whichever row arrived first. The card
        would look entirely normal and be missing half the slate's players.
        """
        seed_prop(conn, game="g1", player="Anthony Kay", strike=5.5, p=0.55)
        seed_prop(conn, game="g1", player="Tarik Skubal", strike=5.5, p=0.61)
        conn.commit()

        legs, _ = ladder_candidates(conn, now_ms=now_ms(), max_odds_age_ms=900_000)
        players = sorted(l.player for l in legs if l.player)
        assert players == ["Anthony Kay", "Tarik Skubal"], players

    def test_a_prop_leg_carries_no_team_and_kalshis_own_label(self, conn):
        seed_prop(conn, game="g1", player="Anthony Kay", strike=5.5, p=0.55)
        conn.commit()
        legs, _ = ladder_candidates(conn, now_ms=now_ms(), max_odds_age_ms=900_000)
        leg = next(l for l in legs if l.player)
        assert leg.team is None, "a prop has no team and the player is not one"
        assert leg.player == "Anthony Kay"
        assert leg.label == "Anthony Kay: 6+ strikeouts", leg.label
        assert leg.point == 5.5
        assert leg.market == "pitcher_strikeouts"

    def test_the_under_side_is_skipped_without_a_count(self, conn):
        """Kalshi sells the rung as YES = Over; the Under is that market's NO.

        Skipped the way the +S spread side is -- structurally not a candidate,
        so counting it would inflate every refusal tally on every pass.
        """
        seed_prop(conn, game="g1", player="Anthony Kay", strike=5.5, p=0.55)
        conn.commit()
        legs, excluded = ladder_candidates(
            conn, now_ms=now_ms(), max_odds_age_ms=900_000
        )
        assert len([l for l in legs if l.player]) == 1
        assert "prop_no_kalshi_rung" not in excluded, excluded

    def test_an_accented_player_joins_through_the_shared_fold(self, conn):
        """Kalshi spells him with accents, the books do not.

        `norm` is imported from `kalshi.props`, not reimplemented, so this
        inherits the fold rather than needing a second copy of it.
        """
        seed_prop(
            conn, game="g1", player="Jose Ramirez", strike=1.5, p=0.44,
            kalshi_player="Jos\u00e9 Ram\u00edrez",
            market="batter_total_bases",
            title="Jos\u00e9 Ram\u00edrez: 2+ total bases?",
        )
        conn.commit()
        legs, _ = ladder_candidates(conn, now_ms=now_ms(), max_odds_age_ms=900_000)
        assert [l.player for l in legs if l.player] == ["Jos\u00e9 Ram\u00edrez"]

    def test_the_strike_is_never_derived(self, conn):
        """`floor_strike` and the book's point are one number, not two.

        A rung published at 6.0 must not match a consensus computed at 5.5.
        Any `+ 0.5` in the join would make this pass, and would be a second
        definition of what a rung is.
        """
        seed_prop(
            conn, game="g1", player="Anthony Kay", strike=6.0, p=0.55,
            book_point=5.5,
        )
        conn.commit()
        legs, excluded = ladder_candidates(
            conn, now_ms=now_ms(), max_odds_age_ms=900_000
        )
        assert not [l for l in legs if l.player]
        assert excluded.get("prop_no_kalshi_rung") == 1, excluded

    def test_a_prop_row_with_unmeasurable_age_is_refused(self, conn):
        """ADR 0070 s2.6 reaches the prop path, and is not re-implemented.

        A pre-v20 row has no `oldest_book_age_ms`; its live age cannot be
        computed, and the leg is refused rather than aged zero.
        """
        seed_prop(
            conn, game="g1", player="Anthony Kay", strike=5.5, p=0.55,
            oldest_book_age_ms=None,
        )
        conn.commit()
        legs, _ = ladder_candidates(
            conn, now_ms=now_ms(), max_odds_age_ms=900_000
        )
        # The pool carries it with an unmeasurable age; `build_ladder` is
        # where that refuses. Asserted at the layer the guard lives on rather
        # than the layer the row appears on -- a test that checked only the
        # pool would pass even if the refusal were deleted.
        leg = next(l for l in legs if l.player)
        assert leg.odds_age_now_ms is None, "must be None, never aged zero"

        ladder = build_ladder(legs, max_odds_age_ms=900_000, now_ms=now_ms())
        assert ladder.excluded.get("age_unmeasurable") == 1, ladder.excluded

    def test_a_prop_and_its_own_game_never_share_a_card(self, conn):
        """The safety property the whole design rests on.

        A prop event inherits its game's `odds_event_id` by construction, and
        `_best_per_game` takes one leg per `odds_event_id` -- so a prop and its
        own game's moneyline cannot both be selected, and `CorrelationRefused`
        stays structurally unreachable rather than handled.
        """
        seed_game(conn, game="g1", team="Detroit", other="Chicago WS",
                  computed_ms=now_ms())
        seed_prop(conn, game="g1", player="Anthony Kay", strike=5.5, p=0.99)
        conn.commit()

        legs, _ = ladder_candidates(conn, now_ms=now_ms(), max_odds_age_ms=900_000)
        assert len({l.odds_event_id for l in legs}) == 1
        chosen = _best_per_game(legs, prefer_spreads=False, longest_first=False)
        assert len(chosen) == 1, [l.label for l in chosen]


class TestTheDeskIsScopedToTonight:
    """Joe, 2026-08-28: "let's keep the scope of the parlay page to the
    current day's games" and "I'd want to see my parlays finish out by the
    time the evening games end."

    A parlay settles when its LAST leg does, so one Saturday leg on a Friday
    card means the whole ticket is live until Saturday. Scoping the ladder is
    the only way that rule can hold, because the ladder is what picks legs.

    Every case here injects `now_ms` rather than reading the clock. The
    boundary is a wall-clock hour, so a test that used the real time would
    exercise a different branch depending on when the suite ran -- and would
    pass all day and fail at 3am.

    WHAT THIS DOES NOT ESTABLISH
    ----------------------------
    - Nothing about Kalshi accepting the resulting card. The bound happens to
      keep the desk inside what the venue combines (its collections carry only
      the imminent slate) but that is a coincidence of two independent facts,
      not a guarantee; `TestKalshiWillNotCombineEveryMarketItTrades` in
      `test_parlay_lookup.py` owns the refusal that does not assume it.
    - Nothing about the evening being a good time to bet, or these legs being
      worth combining.
    """

    #: Friday 2026-08-28, 15:00 Pacific. Chosen because it is an ordinary
    #: afternoon: the whole evening slate is still ahead and the rollover is
    #: 13 hours out, so nothing here is riding on a boundary by accident.
    FRIDAY_3PM_PT = 1787954400000

    def test_the_rollover_is_4am_not_midnight(self):
        """**The hour is the product decision, so it gets its own case.** A
        22:30 kickoff is one of the evening games Joe means, and it finishes
        near 01:30. Rolling at midnight would drop it from the card at exactly
        the hour he is most likely to be looking at one.
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(parlays.DESK_TIME_ZONE)
        cutoff = parlays.end_of_desk_day_ms(self.FRIDAY_3PM_PT)
        local = datetime.fromtimestamp(cutoff / 1000, tz)
        assert (local.hour, local.minute) == (4, 0)
        assert local.date().isoformat() == "2026-08-29"

    def test_after_midnight_is_still_the_same_slate(self):
        """00:30 Saturday is Friday night, not Saturday. The cutoff must not
        jump a whole day just because the calendar did -- that is the
        discontinuity the 4am rollover exists to remove."""
        half_past_midnight = self.FRIDAY_3PM_PT + int(9.5 * 3_600_000)
        assert parlays.end_of_desk_day_ms(
            half_past_midnight
        ) == parlays.end_of_desk_day_ms(self.FRIDAY_3PM_PT)

    def test_a_game_after_the_rollover_is_dropped_and_counted(self, tmp_path):
        """The reported bug, reduced: a card whose legs are days out.

        Counted rather than silently omitted, because a thin page has to be
        able to say why it is thin -- this module refuses in words, never by
        omission.
        """
        conn = store.init_db(tmp_path / "tonight.db")
        now = self.FRIDAY_3PM_PT
        tonight = now + 4 * 3_600_000
        next_week = now + 7 * 24 * 3_600_000
        seed_game(conn, game="tonight", team="Team A", other="Team B",
                  p=0.7, computed_ms=now - 30_000, commence_ms=tonight)
        seed_game(conn, game="sept", team="Team C", other="Team D",
                  p=0.7, computed_ms=now - 30_000, commence_ms=next_week)
        conn.commit()

        legs, excluded = ladder_candidates(conn, now_ms=now)

        assert {l.commence_ms for l in legs} == {tonight}
        assert excluded.get("kickoff_after_tonight", 0) > 0

    def test_the_last_game_of_the_night_survives(self, tmp_path):
        """The case a midnight bound would break, asserted directly: a 22:30
        kickoff is in tonight's slate and must stay on the card."""
        conn = store.init_db(tmp_path / "late.db")
        now = self.FRIDAY_3PM_PT
        late = now + int(7.5 * 3_600_000)  # 22:30 Pacific
        seed_game(conn, game="late", team="Team A", other="Team B",
                  p=0.7, computed_ms=now - 30_000, commence_ms=late)
        conn.commit()

        legs, excluded = ladder_candidates(conn, now_ms=now)

        # The count, not a literal list: how many sides of one game survive
        # the OTHER filters is not this test's claim. Its claim is that the
        # 22:30 kickoff is not the thing that removed them.
        assert legs, "the last game of the night was dropped entirely"
        assert {l.commence_ms for l in legs} == {late}
        assert "kickoff_after_tonight" not in excluded

    def test_the_two_clocks_are_the_same_clock(self):
        """`DESK_TIME_ZONE` scopes the card; `DISPLAY_TIME_ZONE` captions it.
        Two definitions of "today" in one process is how the looser one wins
        in silence -- this repo has paid for that once already, in the odds
        budget's day boundary."""
        api_ts = (
            Path(__file__).resolve().parents[1]
            / "frontend" / "src" / "lib" / "api.ts"
        ).read_text(encoding="utf-8")
        assert (
            f'export const DISPLAY_TIME_ZONE = "{parlays.DESK_TIME_ZONE}"'
            in api_ts
        )

    def test_the_screen_has_words_for_the_new_refusal(self):
        """An unglossed reason code renders as a raw identifier on a money
        screen. `ParlayCards` maps every code this function can emit."""
        src = (
            Path(__file__).resolve().parents[1]
            / "frontend" / "src" / "components" / "ParlayCards.tsx"
        ).read_text(encoding="utf-8")
        assert "kickoff_after_tonight:" in src


class TestTheDeskKnowsWhatKalshiWillCombine:
    """Kalshi trades far more games than it will combine, and the desk had no
    way to know which.

    Measured 2026-08-28: `KXMVECROSSCATEGORY-R`, `-SHARD1-R` and
    `KXMVESPORTSMULTIGAMEEXTENDED-R` carry the SAME 2,365 legs. A card whose
    legs are outside that list returns HTTP 400 `invalid_parameters` after the
    tap -- real markets, individually priceable, that the venue will not
    parlay.

    The ladder cannot ask Kalshi: `GET /api/parlays` is sync and
    `build_ladder_payload` also runs inside the scheduler pass, where a
    paginated walk is the shape that killed the pass tail that morning. So the
    walk happens on the loop's schedule and leaves its answer in
    `combo_eligible_events`.

    **The load-bearing property is what happens when the cache is COLD**, and
    it gets three cases below, because getting it wrong empties the parlay desk
    on every fresh volume and every deploy.

    WHAT THIS DOES NOT ESTABLISH
    ----------------------------
    - Nothing about the walk itself; `fetch_collections` is `test_combos.py`'s.
    - Nothing about Kalshi accepting a card whose legs ARE all eligible. The
      enumerated list is known to understate what a catch-all accepts, which is
      why `price_card_on_kalshi` still refuses on its own terms rather than
      trusting this.
    """

    NOW = 1787954400000  # Friday 2026-08-28 15:00 PT, as elsewhere in this file

    def _seeded(self, tmp_path, name="elig.db"):
        conn = store.init_db(tmp_path / name)
        seed_game(conn, game="g0", team="Team A", other="Team B",
                  p=0.7, computed_ms=self.NOW - 30_000,
                  commence_ms=self.NOW + 3_600_000)
        conn.commit()
        return conn

    def test_a_cold_cache_filters_nothing(self, tmp_path):
        """**The outage this guard could have caused.** An empty table is a
        walk that has not happened, not a venue that combines nothing. If this
        ever returns zero legs, every fresh deploy shows an empty parlay desk
        until the first refresh lands."""
        conn = self._seeded(tmp_path)
        assert parlays.combo_eligible_events(conn, now_ms=self.NOW) is None
        legs, excluded = ladder_candidates(conn, now_ms=self.NOW)
        assert legs
        assert "kalshi_will_not_combine" not in excluded

    def test_a_stale_cache_filters_nothing(self, tmp_path):
        """Older than the TTL is the same state as never written. A list from
        yesterday describes yesterday's slate, and filtering today's games on
        it would drop all of them."""
        conn = self._seeded(tmp_path)
        old = self.NOW - parlays.COMBO_ELIGIBILITY_TTL_MS - 1
        parlays.store_combo_eligibility(conn, {"KXOTHER-1"}, now_ms=old)
        assert parlays.combo_eligible_events(conn, now_ms=self.NOW) is None
        legs, _ = ladder_candidates(conn, now_ms=self.NOW)
        assert legs

    def test_an_empty_refresh_is_never_written(self, tmp_path):
        """A walk that returns nothing is indistinguishable from a walk that
        failed, so it must not overwrite a good list with an empty one."""
        conn = self._seeded(tmp_path)
        parlays.store_combo_eligibility(conn, {"KXKEEP-1"}, now_ms=self.NOW)
        assert parlays.store_combo_eligibility(conn, set(), now_ms=self.NOW) == 0
        assert parlays.combo_eligible_events(
            conn, now_ms=self.NOW
        ) == {"KXKEEP-1"}

    def test_a_fresh_cache_drops_what_kalshi_will_not_combine(self, tmp_path):
        """The reported bug, reduced to one leg."""
        conn = self._seeded(tmp_path)
        parlays.store_combo_eligibility(
            conn, {"KXSOMETHING-ELSE"}, now_ms=self.NOW
        )
        legs, excluded = ladder_candidates(conn, now_ms=self.NOW)
        assert legs == []
        assert excluded.get("kalshi_will_not_combine", 0) > 0

    def test_a_fresh_cache_keeps_what_it_will(self, tmp_path):
        """The other half, so the test above cannot pass by dropping
        everything."""
        conn = self._seeded(tmp_path)
        ticker = conn.execute(
            "SELECT kalshi_event_ticker FROM event_links LIMIT 1"
        ).fetchone()["kalshi_event_ticker"]
        parlays.store_combo_eligibility(conn, {ticker}, now_ms=self.NOW)
        legs, excluded = ladder_candidates(conn, now_ms=self.NOW)
        assert legs
        assert "kalshi_will_not_combine" not in excluded

    def test_the_refresh_is_due_when_cold_and_hourly_after(self, tmp_path):
        """At most one walk an hour, inside a two-hour TTL, so a single failed
        refresh never changes what the desk shows."""
        conn = self._seeded(tmp_path)
        assert parlays.combo_eligibility_is_due(conn, now_ms=self.NOW)
        parlays.store_combo_eligibility(conn, {"KXA-1"}, now_ms=self.NOW)
        assert not parlays.combo_eligibility_is_due(conn, now_ms=self.NOW)
        assert not parlays.combo_eligibility_is_due(
            conn, now_ms=self.NOW + parlays.COMBO_ELIGIBILITY_REFRESH_MS - 1
        )
        assert parlays.combo_eligibility_is_due(
            conn, now_ms=self.NOW + parlays.COMBO_ELIGIBILITY_REFRESH_MS
        )
        assert (
            parlays.COMBO_ELIGIBILITY_REFRESH_MS
            < parlays.COMBO_ELIGIBILITY_TTL_MS
        ), "one missed refresh must not expire the cache"

    async def test_a_failing_walk_never_raises_into_the_pass(self, tmp_path):
        """**The property that matters more than the feature.** This runs
        inside `score_settle_and_alert`, and on 2026-08-28 one arithmetic bug
        there stopped the daily digest, the parlay cards and
        `log_gate_progress` together. A network walk is a likelier thing to
        throw than that was."""
        conn = self._seeded(tmp_path)

        class Boom:
            pass

        async def explode(api, max_pages=25):
            raise RuntimeError("the venue is down")

        import backend.parlays as mod
        original = mod.fetch_collections
        mod.fetch_collections = explode
        try:
            got = await mod.refresh_combo_eligibility(
                conn, Boom(), now_ms=self.NOW
            )
        finally:
            mod.fetch_collections = original
        assert got is None
        # And the cache is untouched rather than emptied.
        assert mod.combo_eligible_events(conn, now_ms=self.NOW) is None

    def test_the_loop_bounds_the_walk_and_gates_it_on_full_passes(self):
        """Source pin. The timeout and the `kind == "full"` gate are the two
        things standing between a slow venue and a wedged pass, and neither is
        visible from the function under test."""
        src = (
            Path(__file__).resolve().parents[1] / "scripts" / "run_loop.py"
        ).read_text(encoding="utf-8")
        assert 'if kind == "full" and combo_eligibility_is_due(' in src
        gate = src.index("combo_eligibility_is_due(conn, now_ms=stamp)")
        assert "asyncio.timeout(20)" in src[gate:gate + 600]

    def test_the_screen_has_words_for_the_new_refusal(self):
        src = (
            Path(__file__).resolve().parents[1]
            / "frontend" / "src" / "components" / "ParlayCards.tsx"
        ).read_text(encoding="utf-8")
        assert "kalshi_will_not_combine:" in src


class TestTheScanIsNeverTighterThanTheFreshnessRule:
    """The candidate scan's floor is derived from `max_odds_age_ms`, not set
    beside it.

    **Why this exists.** The floor was a flat 24 hours, and on live that meant
    reading 541,222 `fair_prices` rows, joining each, sorting them all through
    a temp B-tree, and keeping 350 -- 25.3 seconds, measured by
    `inspect_live_db parlay-candidates-timing` on 2026-08-30, while
    `/api/board` answered in ~2s.

    Narrowing a scan is only safe while it stays wider than the rule that
    discards rows downstream. That is what these assert: the relationship,
    not the constant. A future session raising `MAX_ODDS_AGE_S` past two hours
    must not silently start dropping legs the ladder would have accepted.

    **What this does not establish:** that the scan is fast. It is a
    relationship between two numbers; the wall time is a live reading.
    """

    def test_the_scan_window_always_covers_the_freshness_window(self):
        from backend.parlays import (
            _CANDIDATE_SCAN_FLOOR_MULTIPLE,
            _CANDIDATE_SCAN_MIN_MS,
        )

        # Every plausible deployed value, including ones far past today's.
        for max_age_ms in (0, 900_000, 3_600_000, 7_200_000, 86_400_000):
            horizon = max(
                _CANDIDATE_SCAN_FLOOR_MULTIPLE * max_age_ms,
                _CANDIDATE_SCAN_MIN_MS,
            )
            assert horizon >= max_age_ms, (
                f"a {max_age_ms}ms freshness rule would be scanned over only "
                f"{horizon}ms -- legs the ladder accepts would never be read"
            )

    def test_the_multiple_leaves_room_to_count_what_went_stale(self):
        """The scan must outlive the freshness rule, not merely match it.

        At exactly 1x, a row that had just gone stale would never enter the
        scan, `excluded['stale_consensus']` would read 0, and an empty ladder
        would say "the slate has 0 fresh games" with nothing saying where they
        went. That is a refusal naming a predicate it did not apply.
        """
        from backend.parlays import _CANDIDATE_SCAN_FLOOR_MULTIPLE

        assert _CANDIDATE_SCAN_FLOOR_MULTIPLE > 1


class TestThePriceToBeatIsServedAndIsBreakEven:
    """The card's headline number for a bet placed somewhere else (ADR 0085).

    **Why this exists.** 61 of 61 open combinations on Kalshi carried no quoted
    ask on 2026-08-30, 0 had any liquidity, and 1 had ever traded. The desk
    prices a parlay far more reliably than it can buy one, so the number that
    travels is the price a sportsbook must offer to match the consensus.

    **What this establishes.** That the conversion is right in both directions
    around even money; that an unrepresentable probability refuses rather than
    clamping; and that the figure is served rendered, like every other money
    string on this desk.

    **What it does not establish.** That the odds are attainable, that a
    sportsbook will offer them, or that the parlay is worth betting. It is
    break-even: at exactly this price the bet is fair and its expected profit
    is zero.
    """

    def test_a_longshot_converts_to_plus_money(self):
        from backend.parlays import american_odds

        # The live card on 2026-08-30: 20.1% joint across three legs.
        assert american_odds(0.201) == 398

    def test_a_favourite_converts_to_minus_money(self):
        from backend.parlays import american_odds

        assert american_odds(0.666) == -199

    def test_even_money_is_plus_one_hundred(self):
        from backend.parlays import american_odds

        assert american_odds(0.5) == 100

    def test_a_certainty_has_no_odds_and_refuses(self):
        """`None`, never a clamped number.

        A probability of 0 or 1 has no odds. Rendering one anyway would put a
        figure on the card that no book could ever quote.
        """
        from backend.parlays import american_odds

        assert american_odds(0.0) is None
        assert american_odds(1.0) is None
        assert american_odds(1.5) is None

    async def test_the_card_serves_it_rendered_with_its_sign(self, build):
        app = build(_fresh_slate)
        body = (await get(app, "/api/parlays")).json()
        built = [c for c in body["cards"] if c["joint"]]
        assert built, "the fixture built no card"
        for card in built:
            shown = card["joint"]["price_to_beat_display"]
            assert shown is not None
            assert shown[0] in "+-", "American odds carry their sign"
            assert shown[1:].isdigit()


class TestTheSweetSpotReachesTheWire:
    """The score on a real leg through the real route, not a unit fixture.

    `trust.py` was correct in isolation before any of this existed, which is
    exactly the state four modules in this repo were in when nothing called
    them. These assertions are the caller.
    """

    async def test_every_leg_carries_a_trust_score(self, build):
        app = build(_fresh_slate)
        body = (await get(app, "/api/parlays")).json()
        legs = [leg for card in body["cards"] for leg in card["legs"]]
        assert legs, "no legs to score"
        for leg in legs:
            assert leg["trust"] is not None, (
                "the route supplied no thresholds, so the score silently "
                "declined to compute -- which is the wiring failure this "
                "test exists to catch"
            )
            assert set(leg["trust"]) == {"passed", "known", "total", "checks"}

    async def test_the_three_counts_all_travel(self, build):
        """`passed/total` alone hides how many checks nobody ran; `passed/known`
        alone hides that they exist. The screen needs all three to word it."""
        app = build(_fresh_slate)
        body = (await get(app, "/api/parlays")).json()
        leg = next(leg for card in body["cards"] for leg in card["legs"])
        t = leg["trust"]
        assert t["total"] >= t["known"] >= t["passed"]
        assert t["total"] == len(t["checks"])

    async def test_the_score_is_thresholded_by_the_engines_own_config(
        self, build
    ):
        """Not by a default baked into the scorer.

        The route builds `TrustThresholds` from the same `SuppressionConfig`
        the engine judged the row against, so a limit cannot mean one thing to
        the gauntlet and another to this score.
        """
        app = build(_fresh_slate)
        body = (await get(app, "/api/parlays")).json()
        leg = next(leg for card in body["cards"] for leg in card["legs"])
        names = {c["name"] for c in leg["trust"]["checks"]}
        assert names == {
            "consensus_fresh", "quote_fresh", "books", "books_agree",
            "methods_agree", "depth", "skeptic", "scout",
        }

    async def test_no_check_state_is_invented(self, build):
        app = build(_fresh_slate)
        body = (await get(app, "/api/parlays")).json()
        for card in body["cards"]:
            for leg in card["legs"]:
                for check in leg["trust"]["checks"]:
                    assert check["state"] in ("pass", "fail", "unknown")
                    assert isinstance(check["detail"], str) and check["detail"]

    async def test_an_unscouted_leg_scores_unknown_not_pass(self, build):
        """The seeded slate has no scout briefings, so every leg proves it.

        This is the flattering direction and the one worth catching on the
        wire as well as in the unit: a leg nobody scouted must not score as a
        leg the scout cleared.
        """
        app = build(_fresh_slate)
        body = (await get(app, "/api/parlays")).json()
        for card in body["cards"]:
            for leg in card["legs"]:
                scout = next(
                    c for c in leg["trust"]["checks"] if c["name"] == "scout"
                )
                assert scout["state"] == "unknown", scout
