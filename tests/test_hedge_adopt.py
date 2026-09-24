"""`POST /api/hedge/positions/adopt` -- one tap onto `/hedge`'s watch (#148).

`unrecorded_at_venue` tells Joe "Record it below" for a KXMVE combination the
venue holds that no open `parlay_positions` row is watching -- but
`RecordParlay.tsx` has no combination-ticker field, so that instruction could
not be followed. This route is the tap that follows it:
`hedge.adopt_venue_combo` builds the position from the latest complete
`positions` poll (contracts, exposure) and the venue's own market (the legs,
via `mve_legs`), the same source `ask_makers_to_buy_back` (#96) uses for a
position that recorded no lookup.

What these tests establish: adopting a polled KXMVE row writes `combo_ticker`
= the ticker, `stake_tenths` = the polled exposure, and legs read from a
CAPTURED market payload (`tests/fixtures/combo_lookup_response.json`, which
carries `mve_selected_legs`); a ticker outside the latest complete poll, one
an open position already claims, a non-KXMVE ticker, and a market with no
legs are each refused, before the legless case's venue call and before every
other case's venue call at all; `hedge_watch.py` and `portfolio_poll.py`
reference `adopt_venue_combo` nowhere, so nothing unattended calls it.

What they do not establish: that `venue_positions.exposure_tenths` equals
what Joe actually paid, fee included -- the ticket's own caveat, unchanged
here.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from backend import hedge
from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db as store

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "combo_lookup_response.json"
HEADERS = {"Authorization": "Bearer secret-token"}
NOW_MS = 1_700_000_000_000

_CAPTURED = json.loads(FIXTURE.read_text(encoding="utf-8"))
TICKER = _CAPTURED["market"]["ticker"]
LEGS = _CAPTURED["market"]["mve_selected_legs"]
LEG_TICKERS = [leg["market_ticker"] for leg in LEGS]


def _pem(tmp_path: Path) -> Path:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    path = tmp_path / "key.pem"
    if not path.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    return path


class FakeVenue:
    """The shared `KalshiRestClient`, recording every call it answers."""

    def __init__(self, *, market_payload=None, fail_get=False):
        self.calls: list[str] = []
        self.market_payload = (
            market_payload if market_payload is not None else _CAPTURED
        )
        self.fail_get = fail_get

    async def get(self, path, **params):
        self.calls.append(f"GET {path}")
        if self.fail_get:
            raise RuntimeError("Kalshi did not answer")
        return self.market_payload


def _poll(conn, *, polled_ms, ok=True, mirrored=1, row_count=0):
    cursor = conn.execute(
        "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count, mirrored) "
        "VALUES (?, 'positions', ?, ?, ?)",
        (polled_ms, 1 if ok else 0, row_count, mirrored),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _venue_row(
    conn, *, poll_log_id, polled_ms, ticker, contracts=8.22, exposure_tenths=6_340,
):
    conn.execute(
        "INSERT INTO venue_positions "
        "(poll_log_id, polled_ms, ticker, contracts, exposure_tenths) "
        "VALUES (?, ?, ?, ?, ?)",
        (poll_log_id, polled_ms, ticker, contracts, exposure_tenths),
    )
    conn.commit()


def _market_title(conn, *, ticker, title):
    conn.execute(
        "INSERT INTO kalshi_markets (ticker, first_seen_ms, last_seen_ms, title) "
        "VALUES (?, ?, ?, ?)",
        (ticker, NOW_MS, NOW_MS, title),
    )
    conn.commit()


def _seed_poll(conn, *, ticker=TICKER, contracts=8.22, exposure_tenths=6_340):
    poll_id = _poll(conn, polled_ms=NOW_MS)
    _venue_row(
        conn, poll_log_id=poll_id, polled_ms=NOW_MS, ticker=ticker,
        contracts=contracts, exposure_tenths=exposure_tenths,
    )
    return poll_id


@pytest.fixture()
def build(tmp_path, monkeypatch):
    def _build(*, venue=None):
        path = tmp_path / "t.db"
        conn = store.init_db(path)
        conn.close()

        fake = venue or FakeVenue()

        def _client(config, client=None):
            return fake

        monkeypatch.setattr("backend.api.routes.KalshiRestClient", _client)
        monkeypatch.setenv("KALSHI_API_KEY", "key")
        monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(_pem(tmp_path)))
        app = create_app(
            AppConfig(instance_mode="live", auth_token="secret-token", db_path=path)
        )
        return app, fake, path
    return _build


async def _adopt(app, ticker=TICKER, headers=HEADERS):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post(
            "/api/hedge/positions/adopt", json={"ticker": ticker}, headers=headers
        )


class TestAdoptingAPolledCombination:
    async def test_it_writes_combo_ticker_and_the_polled_stake(self, build):
        app, fake, path = build()
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            _seed_poll(conn, contracts=8.22, exposure_tenths=6_340)
        finally:
            conn.close()

        response = await _adopt(app)
        assert response.status_code == 200
        position_id = response.json()["position_id"]

        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM parlay_positions WHERE id = ?", (position_id,)
            ).fetchone()
            assert row["combo_ticker"] == TICKER
            assert row["source"] == "kalshi_combo"
            assert row["status"] == "open"
            assert row["stake_tenths"] == 6_340
            assert row["return_tenths"] == 8_220  # 8.22 contracts * 1000
            legs = conn.execute(
                "SELECT * FROM parlay_position_legs WHERE position_id = ? "
                "ORDER BY leg_index", (position_id,),
            ).fetchall()
            assert [leg["ticker"] for leg in legs] == LEG_TICKERS
            assert [leg["side"] for leg in legs] == [
                leg["side"] for leg in LEGS
            ]
        finally:
            conn.close()
        assert fake.calls == [f"GET /markets/{TICKER}"]

    async def test_leg_and_position_labels_use_kalshi_markets_titles(self, build):
        app, fake, path = build()
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            _seed_poll(conn)
            _market_title(conn, ticker=LEG_TICKERS[0], title="Tennessee to win")
            _market_title(conn, ticker=LEG_TICKERS[1], title="Buffalo to win")
        finally:
            conn.close()

        response = await _adopt(app)
        assert response.status_code == 200
        position_id = response.json()["position_id"]
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            position = conn.execute(
                "SELECT label FROM parlay_positions WHERE id = ?", (position_id,)
            ).fetchone()
            assert position["label"] == "Tennessee to win, Buffalo to win"
            legs = conn.execute(
                "SELECT label FROM parlay_position_legs WHERE position_id = ? "
                "ORDER BY leg_index", (position_id,),
            ).fetchall()
            assert [leg["label"] for leg in legs] == [
                "Tennessee to win", "Buffalo to win",
            ]
        finally:
            conn.close()

    async def test_a_partial_title_table_still_degrades_to_the_ticker(self, build):
        """Only one leg has a `kalshi_markets` title -- the OVERALL label
        degrades to the bare ticker (it cannot claim a title for the leg
        that has none), but that one leg's own label still uses its title."""
        app, fake, path = build()
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            _seed_poll(conn)
            _market_title(conn, ticker=LEG_TICKERS[0], title="Tennessee to win")
        finally:
            conn.close()

        response = await _adopt(app)
        position_id = response.json()["position_id"]
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            position = conn.execute(
                "SELECT label FROM parlay_positions WHERE id = ?", (position_id,)
            ).fetchone()
            assert position["label"] == TICKER
            legs = conn.execute(
                "SELECT label FROM parlay_position_legs WHERE position_id = ? "
                "ORDER BY leg_index", (position_id,),
            ).fetchall()
            assert legs[0]["label"] == "Tennessee to win"
            assert legs[1]["label"] == LEG_TICKERS[1]
        finally:
            conn.close()


class TestTheGuards:
    async def test_it_needs_auth(self, build):
        app, fake, _ = build()
        response = await _adopt(app, headers={})
        assert response.status_code in (401, 403)
        assert fake.calls == []

    async def test_a_ticker_outside_the_latest_complete_poll_is_404(self, build):
        """MUTATION: dropping the `venue_row is None` check turns this red --
        the route would try to price a ticker no poll ever named."""
        app, fake, path = build()
        conn = sqlite3.connect(path)
        try:
            _seed_poll(conn, ticker="KXMVE-SOMETHING-ELSE")
        finally:
            conn.close()
        response = await _adopt(app)
        assert response.status_code == 404
        assert "does not show" in response.json()["detail"]
        assert fake.calls == [], "the venue must not be asked about an unpolled ticker"

    async def test_no_complete_poll_at_all_is_also_404(self, build):
        """MUTATION: dropping the `poll is None` check turns this red."""
        app, fake, _ = build()
        response = await _adopt(app)
        assert response.status_code == 404
        assert "never been a complete read" in response.json()["detail"]
        assert fake.calls == []

    async def test_a_ticker_already_claimed_by_an_open_position_is_409(self, build):
        """MUTATION: dropping the already-open check turns this red -- the
        exposure this desk believes it is watching would double."""
        app, fake, path = build()
        conn = sqlite3.connect(path)
        try:
            _seed_poll(conn)
            hedge.record_position(
                conn,
                now_ms=NOW_MS,
                source="kalshi_combo",
                label="already watched",
                stake_tenths=1_000,
                return_tenths=2_000,
                legs=[{"ticker": LEG_TICKERS[0], "side": "yes", "label": "L1"}],
                combo_ticker=TICKER,
            )
            conn.commit()
        finally:
            conn.close()
        response = await _adopt(app)
        assert response.status_code == 409
        assert "already watched" in response.json()["detail"]
        assert fake.calls == []

    async def test_a_non_kxmve_ticker_is_422_and_never_reaches_the_poll_or_venue(
        self, build
    ):
        """MUTATION: dropping the `startswith('KXMVE')` check turns this red."""
        app, fake, path = build()
        conn = sqlite3.connect(path)
        try:
            _seed_poll(conn, ticker="KXMLBGAME-26AUG26CINSF-CIN")
        finally:
            conn.close()
        response = await _adopt(app, ticker="KXMLBGAME-26AUG26CINSF-CIN")
        assert response.status_code == 422
        assert "not a KXMVE" in response.json()["detail"]
        assert fake.calls == []

    async def test_a_market_with_no_legs_is_422_after_the_venue_call(self, build):
        """MUTATION: removing the `mve_legs` guard (or swallowing its
        `RfqRefused`) turns this red -- a position with no legs is refused
        by `record_position` too, but this must refuse first, with words
        naming the venue's payload, not a generic 'needs at least one leg'."""
        legless_payload = {"market": {"ticker": TICKER}}
        app, fake, path = build(venue=FakeVenue(market_payload=legless_payload))
        conn = sqlite3.connect(path)
        try:
            _seed_poll(conn)
        finally:
            conn.close()
        response = await _adopt(app)
        assert response.status_code == 422
        assert "no legs to watch" in response.json()["detail"]
        assert fake.calls == [f"GET /markets/{TICKER}"]

    async def test_an_unreadable_market_is_502(self, build):
        app, fake, path = build(venue=FakeVenue(fail_get=True))
        conn = sqlite3.connect(path)
        try:
            _seed_poll(conn)
        finally:
            conn.close()
        response = await _adopt(app)
        assert response.status_code == 502
        assert "could not be read" in response.json()["detail"]


class TestNothingUnattendedCallsIt:
    """`hedge_watch.py` runs `build_payload` every 60 s and `portfolio_poll.py`
    polls the venue on its own clock -- neither may fire a write a tap is
    meant to gate. MUTATION: adding a call from either file turns this red."""

    def test_hedge_watch_never_references_it(self):
        source = (REPO / "backend" / "hedge_watch.py").read_text(encoding="utf-8")
        assert "adopt_venue_combo" not in source

    def test_portfolio_poll_never_references_it(self):
        source = (REPO / "backend" / "portfolio_poll.py").read_text(encoding="utf-8")
        assert "adopt_venue_combo" not in source


class TestTheCapturedFixture:
    """CLAUDE.md: a wire-format test loads a captured payload, never a
    hand-constructed one. `combo_lookup_response.json`'s `market` key is
    exactly the shape `GET /markets/{ticker}` answers with (`market_single.
    json`'s `single` key pins the same envelope), and it already carries
    `mve_selected_legs` -- this test only asserts the fixture still has the
    shape the rest of this file assumes."""

    def test_the_fixture_is_a_kxmve_market_with_two_legs(self):
        assert TICKER.startswith("KXMVE")
        assert len(LEGS) == 2
        assert all(leg["side"] == "yes" for leg in LEGS)
