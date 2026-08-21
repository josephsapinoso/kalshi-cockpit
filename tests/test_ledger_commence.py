"""`/api/ledger` rows carry the sportsbook's kickoff, or `None` -- never a fake.

Until 2026-08-21 the ledger SQL joined nothing that carries a start time, yet
`_serialise` emitted `commence_ms` anyway, so every row read `null` and a
consumer could not distinguish "the join was never attempted" from "the event
is unknown". Pre/post-commence bucketing on the registered evidence route --
the axis behind the clv-coverage denominator error -- silently returned
nothing.

The fix's trap, and what the third test guards: `kalshi_events.commence_ms`
stores `occurrence_datetime` raw, which on game series is the expected *end*,
about three hours late (ADR 0006). Joining it would have shipped a second
defect wearing the first one's fix. The route instead takes
`MIN(odds_snapshots.commence_ms)` per linked fixture -- the same definition
`backend/scoring.py:markets_awaiting_scoring` uses to decide when a closing
line exists, so the ledger's bucketing axis and the clv machinery agree.

**What these tests do not establish.** Nothing about rows already stored on
the live instance -- the deployed record was written before this change and
`link_id` is nullable, so old rows may still resolve to `None`. Nothing about
whether the linker matched the right fixture; `commence_skew_ms` on the link
is the evidence for that. And nothing about display: this is the wire value in
UTC milliseconds, not a rendered clock.
"""

from __future__ import annotations

import httpx
import pytest

from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db

_ODDS_COMMENCE_MS = 1_755_800_000_000
_THREE_HOURS_MS = 3 * 60 * 60 * 1000


async def get(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, **kwargs)


def _insert_snapshot(conn, *, odds_event_id: str, commence_ms: int) -> None:
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
        "commence_ms, home_team, away_team, bookmaker, market, outcome_name, "
        "price_decimal) "
        "VALUES (1000, 'baseball_mlb', ?, ?, 'Home', 'Away', 'pinnacle', "
        "'h2h', 'Home', 1.9)",
        (odds_event_id, commence_ms),
    )


def _insert_recommendation(conn, *, created_ms: int, link_id) -> None:
    ticker = f"KXTEST-{created_ms}"
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, first_seen_ms, "
        "last_seen_ms) VALUES (?, ?, ?)",
        (ticker, 1000, 1000),
    )
    conn.execute(
        "INSERT INTO recommendations (created_ms, strategy_config_version, "
        "ticker, link_id, side, entry_ask_tenths, fair_probability, "
        "edge_tenths, fee_predicted, ev_net_dollars, kelly_fraction, "
        "suggested_contracts, reference_contracts, kalshi_quote_age_ms, "
        "odds_age_ms, reason_text) "
        "VALUES (?, 1, ?, ?, 'yes', 500, 0.52, 5.0, 0.1, 0.2, 0.01, 0, 0, "
        "1000, 2000, 'test row')",
        (created_ms, ticker, link_id),
    )


@pytest.fixture
def commence_db(tmp_path):
    path = tmp_path / "commence.db"
    conn = db.init_db(path)
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
    )
    # The Kalshi event carries the trap value: `occurrence_datetime` stored
    # raw, three hours after the true start. If the route ever reads it, the
    # third test's equality breaks by exactly that offset.
    conn.execute(
        "INSERT INTO kalshi_events (event_ticker, first_seen_ms, last_seen_ms, "
        "commence_ms) VALUES ('KXTEST-EVENT', 1000, 1000, ?)",
        (_ODDS_COMMENCE_MS + _THREE_HOURS_MS,),
    )
    conn.execute(
        "INSERT INTO event_links (id, kalshi_event_ticker, odds_event_id, "
        "league, method, commence_skew_ms, linked_ms) "
        "VALUES (1, 'KXTEST-EVENT', 'odds-1', 'baseball_mlb', "
        "'exact_alias_pair', 0, 1000)"
    )
    # Two snapshots of the same fixture: a reschedule moved the stated start
    # later. The earlier one must win, because that is the scorer's definition.
    _insert_snapshot(conn, odds_event_id="odds-1", commence_ms=_ODDS_COMMENCE_MS)
    _insert_snapshot(
        conn, odds_event_id="odds-1", commence_ms=_ODDS_COMMENCE_MS + 600_000
    )
    _insert_recommendation(conn, created_ms=2000, link_id=1)
    _insert_recommendation(conn, created_ms=1000, link_id=None)
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def commence_app(commence_db):
    return create_app(AppConfig(instance_mode="demo", db_path=commence_db))


class TestTheLedgerCarriesTheSportsbookKickoff:
    async def test_a_linked_row_carries_a_real_commence(self, commence_app):
        rows = (await get(commence_app, "/api/ledger?limit=10")).json()["rows"]
        linked = next(r for r in rows if r["ticker"] == "KXTEST-2000")
        assert linked["commence_ms"] == _ODDS_COMMENCE_MS

    async def test_an_unlinked_row_resolves_to_none_never_a_substitute(
        self, commence_app
    ):
        """`link_id` is nullable and old rows predate the linker.

        "We do not know when this game starts" must not resolve to any number,
        per the repo rule that unreadable resolves to `None`, never `0`.
        """
        rows = (await get(commence_app, "/api/ledger?limit=10")).json()["rows"]
        unlinked = next(r for r in rows if r["ticker"] == "KXTEST-1000")
        assert unlinked["commence_ms"] is None

    async def test_the_clock_is_the_sportsbooks_not_kalshis(self, commence_app):
        """The fixture plants the ADR 0006 trap and this asserts it was refused.

        `kalshi_events.commence_ms` on this fixture is exactly three hours
        after the sportsbook's start -- the raw `occurrence_datetime` value.
        A route that joins it emits a number three hours into the game and
        this equality fails by exactly `_THREE_HOURS_MS`.
        """
        rows = (await get(commence_app, "/api/ledger?limit=10")).json()["rows"]
        linked = next(r for r in rows if r["ticker"] == "KXTEST-2000")
        assert linked["commence_ms"] != _ODDS_COMMENCE_MS + _THREE_HOURS_MS
        assert linked["commence_ms"] == _ODDS_COMMENCE_MS

    async def test_the_earliest_snapshot_wins_matching_the_scorer(
        self, commence_app
    ):
        """Two snapshots disagree by ten minutes; `MIN` must decide.

        Not a style choice: `markets_awaiting_scoring` takes
        `MIN(commence_ms)` per fixture, and the ledger bucketing axis must
        agree with the machinery that writes the clv fields or pre/post-close
        classification splits between the two.
        """
        rows = (await get(commence_app, "/api/ledger?limit=10")).json()["rows"]
        linked = next(r for r in rows if r["ticker"] == "KXTEST-2000")
        assert linked["commence_ms"] == _ODDS_COMMENCE_MS
