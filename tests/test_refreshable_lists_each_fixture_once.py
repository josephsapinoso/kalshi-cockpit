"""`/api/odds/refreshable` lists each fixture once per sport -- #159.

`frontend/src/components/RefreshOddsPanel.tsx:364` keys its fixture list on
`fixture.odds_event_id`. Session 59 (2026-09-25) hit React's "Encountered two
children with the same key" against live data: one `odds_event_id` appeared
twice under one sport's `fixtures` list.

The root cause: `backend/api/routers/odds.py`'s `refreshable` handler used to
run `SELECT DISTINCT sport_key, odds_event_id, commence_ms, home_team,
away_team FROM odds_snapshots WHERE commence_ms BETWEEN now AND now+24h`.
`DISTINCT` collapses identical rows, but `odds_snapshots` is written once per
(sweep, bookmaker, market, outcome) -- so if the SAME `odds_event_id`'s
`commence_ms` (a reschedule) or team-name spelling (a provider correction)
differs between two separate sweeps, and both sweeps' rows still land inside
the 24h horizon, `DISTINCT` keeps both as genuinely different rows and the
same `odds_event_id` is emitted twice.

This is the same shape `runner.book_quotes_for_event` already guards against
(`MAX(fetched_ms)` scopes a read to one sweep, `schema.sql:372`) -- the fix
here is the same pattern: pick the row from each event's own latest sweep,
never the union of every sweep ever stored inside the horizon.

WHAT THIS DOES NOT ESTABLISH
-----------------------------
- Nothing about two DIFFERENT Kalshi events mapping to one game (that is a
  Kalshi-side collision, not an Odds API duplicate, and would need its own
  fixture to reproduce).
- Nothing about the frontend's key or render; only the payload it is fed.
"""

from __future__ import annotations

import httpx
import pytest

from backend.config import AppConfig
from backend.store import db

HOUR = 3_600_000
MIN = 60_000


def add_snapshot(
    conn,
    *,
    sport_key="baseball_mlb",
    odds_event_id="e1",
    commence_ms,
    fetched_ms,
    home_team="Home",
    away_team="Away",
):
    """One sweep's worth of rows for one fixture (two books, two outcomes) --
    the same shape `odds_snapshots` is actually written in, so a dedupe fix
    tested against a single hand-built row would miss the real duplicate
    source (multiple market/bookmaker rows per sweep)."""
    for book in ("pinnacle", "draftkings"):
        for outcome in ("Home", "Away"):
            conn.execute(
                "INSERT INTO odds_snapshots (fetched_ms, book_updated_ms, "
                "sport_key, odds_event_id, commence_ms, home_team, away_team, "
                "bookmaker, market, outcome_name, price_decimal) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'h2h', ?, 2.0)",
                (
                    fetched_ms,
                    None,
                    sport_key,
                    odds_event_id,
                    commence_ms,
                    home_team,
                    away_team,
                    book,
                    outcome,
                ),
            )
    conn.commit()


@pytest.fixture
def app_db(tmp_path):
    return tmp_path / "api.db"


async def _get_refreshable(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return (await c.get("/api/odds/refreshable")).json()


def make_app(app_db):
    from backend.api.routes import create_app

    return create_app(AppConfig(instance_mode="live", db_path=app_db))


class TestEachFixtureIsListedOnce:
    async def test_two_sweeps_with_a_moved_kickoff_still_list_one_fixture(
        self, app_db
    ):
        """The exact shape session 59 hit: the same `odds_event_id` fetched
        twice, with `commence_ms` shifted between sweeps (a reschedule), and
        BOTH sweeps' commence times still inside the 24h horizon. A bare
        `SELECT DISTINCT` keeps both as two different rows; the fix must
        return exactly one, from the later sweep."""
        conn = db.init_db(app_db)
        now = db.now_ms()
        add_snapshot(
            conn,
            odds_event_id="e1",
            commence_ms=now + 3 * HOUR,
            fetched_ms=now - 2 * HOUR,
        )
        add_snapshot(
            conn,
            odds_event_id="e1",
            commence_ms=now + 3 * HOUR + 20 * MIN,
            fetched_ms=now - HOUR,
        )
        conn.close()

        app = make_app(app_db)
        payload = await _get_refreshable(app)
        [mlb] = payload["sports"]
        assert mlb["sport_key"] == "baseball_mlb"

        event_ids = [f["odds_event_id"] for f in mlb["fixtures"]]
        assert event_ids == ["e1"], (
            f"expected exactly one fixture for e1, got {event_ids!r} -- "
            "this is the React duplicate-key bug from #159"
        )
        # And it is the LATEST sweep's fixture info, not whichever sorted first.
        [fixture] = mlb["fixtures"]
        assert fixture["commence_ms"] == now + 3 * HOUR + 20 * MIN

    async def test_a_renamed_team_between_sweeps_still_lists_one_fixture(
        self, app_db
    ):
        """A provider correction to team-name spelling is the other way two
        sweeps of the same event stop being textually identical rows."""
        conn = db.init_db(app_db)
        now = db.now_ms()
        add_snapshot(
            conn,
            odds_event_id="e1",
            commence_ms=now + 3 * HOUR,
            fetched_ms=now - 2 * HOUR,
            home_team="LA Dodgers",
        )
        add_snapshot(
            conn,
            odds_event_id="e1",
            commence_ms=now + 3 * HOUR,
            fetched_ms=now - HOUR,
            home_team="Los Angeles Dodgers",
        )
        conn.close()

        app = make_app(app_db)
        payload = await _get_refreshable(app)
        [mlb] = payload["sports"]
        event_ids = [f["odds_event_id"] for f in mlb["fixtures"]]
        assert event_ids == ["e1"]

    async def test_two_different_fixtures_still_both_appear(self, app_db):
        """The fix must not collapse genuinely different games -- only
        repeats of the same `odds_event_id`."""
        conn = db.init_db(app_db)
        now = db.now_ms()
        add_snapshot(
            conn, odds_event_id="e1", commence_ms=now + 3 * HOUR, fetched_ms=now
        )
        add_snapshot(
            conn, odds_event_id="e2", commence_ms=now + 4 * HOUR, fetched_ms=now
        )
        conn.close()

        app = make_app(app_db)
        payload = await _get_refreshable(app)
        [mlb] = payload["sports"]
        assert sorted(f["odds_event_id"] for f in mlb["fixtures"]) == ["e1", "e2"]

    async def test_within_one_sweep_two_bookmaker_rows_still_list_once(
        self, app_db
    ):
        """The ordinary case `SELECT DISTINCT` already handled correctly --
        pinned here so the fix does not regress it back to per-row listing."""
        conn = db.init_db(app_db)
        now = db.now_ms()
        add_snapshot(
            conn, odds_event_id="e1", commence_ms=now + 3 * HOUR, fetched_ms=now
        )
        conn.close()

        app = make_app(app_db)
        payload = await _get_refreshable(app)
        [mlb] = payload["sports"]
        assert [f["odds_event_id"] for f in mlb["fixtures"]] == ["e1"]
