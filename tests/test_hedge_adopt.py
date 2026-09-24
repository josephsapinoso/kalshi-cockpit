"""`POST /api/hedge/positions/adopt` -- one tap onto `/hedge`'s watch (#148).

`unrecorded_at_venue` tells Joe "Record it below" for a KXMVE combination the
venue holds that no open `parlay_positions` row is watching -- but
`RecordParlay.tsx` has no combination-ticker field, so that instruction could
not be followed. This route is the tap that follows it:
`hedge.adopt_venue_combo` builds the position from the latest complete
`positions` poll (contracts, exposure, side) and the venue's own market (the
legs, via `mve_legs`), the same source `ask_makers_to_buy_back` (#96) uses
for a position that recorded no lookup.

What these tests establish: adopting a polled KXMVE row writes `combo_ticker`
= the ticker, `stake_tenths` = the polled exposure, and legs read from a
CAPTURED market payload (`tests/fixtures/combo_lookup_response.json` for the
happy path, `tests/fixtures/combo_priced_markets.json` for a real NO leg);
a ticker outside the latest complete poll, one an open position already
claims, a non-KXMVE ticker, a `side = 'no'` (or unreadable-side) holding, a
market with no legs, and a leg with no readable side are each refused, before
the legless/leg-side cases' venue call and before every other case's venue
call at all; `hedge_watch.py` and `portfolio_poll.py` reference
`adopt_venue_combo` nowhere, so nothing unattended calls it; a second adopt
racing the first across the venue-call `await` is refused, not a second open
position on the same ticker; the new `stake_basis = "venue_exposure"` routes
past the E2 caveat the way `venue_fill` does and the frontend gloss carries
its own honest sentence for it.

What they do not establish: that `venue_positions.exposure_tenths` equals
what Joe actually paid, fee included -- the ticket's own caveat, unchanged
here; nor anything about `market_exposure_dollars` after a partial sell of
the same holding, which has never been read on this instance.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import httpx
import pytest

from backend import hedge
from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db as store

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "combo_lookup_response.json"
NO_LEG_FIXTURE = REPO / "tests" / "fixtures" / "combo_priced_markets.json"
HEADERS = {"Authorization": "Bearer secret-token"}
NOW_MS = 1_700_000_000_000
# A neutral size, not a real holding Joe has ever carried (2026-09-24 review).
CONTRACTS = 7.35

_CAPTURED = json.loads(FIXTURE.read_text(encoding="utf-8"))
TICKER = _CAPTURED["market"]["ticker"]
LEGS = _CAPTURED["market"]["mve_selected_legs"]
LEG_TICKERS = [leg["market_ticker"] for leg in LEGS]

_NO_LEG_CAPTURE = json.loads(NO_LEG_FIXTURE.read_text(encoding="utf-8"))
_NO_LEG_COMBO = _NO_LEG_CAPTURE["combos"][0]
NO_LEG_TICKER = _NO_LEG_COMBO["ticker"]
NO_LEG_LEGS = _NO_LEG_COMBO["mve_selected_legs"]
NO_LEG_PAYLOAD = {"market": _NO_LEG_COMBO}


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
    """The shared `KalshiRestClient`, recording every call it answers.

    `on_get`, when given, runs synchronously just before `get()` returns --
    the hook the race test uses to simulate a second request finishing its
    own adopt while this one is still awaiting the venue's market.
    """

    def __init__(self, *, market_payload=None, fail_get=False, on_get=None):
        self.calls: list[str] = []
        self.market_payload = (
            market_payload if market_payload is not None else _CAPTURED
        )
        self.fail_get = fail_get
        self.on_get = on_get

    async def get(self, path, **params):
        self.calls.append(f"GET {path}")
        if self.fail_get:
            raise RuntimeError("Kalshi did not answer")
        if self.on_get is not None:
            self.on_get()
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
    conn, *, poll_log_id, polled_ms, ticker, contracts=CONTRACTS,
    exposure_tenths=6_340, side="yes",
):
    conn.execute(
        "INSERT INTO venue_positions "
        "(poll_log_id, polled_ms, ticker, contracts, exposure_tenths, side) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (poll_log_id, polled_ms, ticker, contracts, exposure_tenths, side),
    )
    conn.commit()


def _market_title(conn, *, ticker, title):
    conn.execute(
        "INSERT INTO kalshi_markets (ticker, first_seen_ms, last_seen_ms, title) "
        "VALUES (?, ?, ?, ?)",
        (ticker, NOW_MS, NOW_MS, title),
    )
    conn.commit()


def _seed_poll(
    conn, *, ticker=TICKER, contracts=CONTRACTS, exposure_tenths=6_340,
    side="yes",
):
    poll_id = _poll(conn, polled_ms=NOW_MS)
    _venue_row(
        conn, poll_log_id=poll_id, polled_ms=NOW_MS, ticker=ticker,
        contracts=contracts, exposure_tenths=exposure_tenths, side=side,
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
            _seed_poll(conn, contracts=CONTRACTS, exposure_tenths=6_340)
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
            assert row["return_tenths"] == 7_350  # 7.35 contracts * 1000
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

    async def test_the_stake_basis_is_venue_exposure_and_routed_past_e2(self, build):
        """kalshi-platform review #148, MUST FIX 2: an adopted row falls to
        `venue_exposure`, not `as_recorded`/`hand_recorded_position` -- it
        was never a price Joe or the desk typed. MUTATION: reverting
        `_is_adopted_position` (or its check in `stake_basis_for`) turns
        this red -- the reason goes back to `hand_recorded_position`."""
        app, fake, path = build()
        conn = sqlite3.connect(path)
        try:
            _seed_poll(conn)
        finally:
            conn.close()
        response = await _adopt(app)
        position_id = response.json()["position_id"]

        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            position = dict(
                conn.execute(
                    "SELECT * FROM parlay_positions WHERE id = ?", (position_id,)
                ).fetchone()
            )
        finally:
            conn.close()
        basis = hedge.stake_basis_for(position, None)
        assert basis.basis == hedge.STAKE_BASIS_VENUE_EXPOSURE
        assert basis.reason == "adopted_from_positions"
        assert basis.stake_tenths == position["stake_tenths"]

        # kalshi-platform review #148, MUST FIX 2, the E2-routing half:
        # `estimate_grain` must not name the sent-vs-charged gap on a row
        # that never had a sent price. MUTATION: reverting the
        # `estimate_grain` condition back to comparing only against
        # `STAKE_BASIS_VENUE_FILL` turns this red -- the E2 sentence
        # ("price the desk sent") would reappear on an adopted ticket.
        from backend.core.hedge import HedgeQuote, Lock, Rung

        resolved = hedge.position_at_basis(position, basis)
        rung = Rung(
            contracts=1, cost_tenths=200, fee_tenths=9,
            if_leg_wins_tenths=100, if_leg_loses_tenths=100,
            floor_tenths=100, fillable=True, affordable=True,
        )
        lock = Lock(
            quote=HedgeQuote(
                ticker="X", side="no", ask_tenths=500, depth_at_ask=10.0,
                observed_ms=NOW_MS, status="active", leg_ask_tenths=500,
            ),
            stake_tenths=resolved["stake_tenths"], return_tenths=1_000,
            equalising=rung, best_available=rung, ladder=(rung,),
            depth_contracts=10, affordable_contracts=10,
        )
        grain = hedge.estimate_grain(resolved, lock)
        assert "price the desk sent" not in grain
        assert "hedge fee here" in grain


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

    async def test_a_no_side_holding_is_refused_never_adopted_as_yes(self, build):
        """kalshi-platform review #148, MUST FIX 1: `portfolio_poll.
        parse_position` stores every holding's size as `abs(position_fp)`
        with `side` carrying the sign, so contracts/exposure alone cannot
        tell a NO holding from a YES one of the same size. MUTATION:
        dropping the `venue_row["side"] != "yes"` check turns this red --
        a NO holding would be adopted as if it were YES."""
        app, fake, path = build()
        conn = sqlite3.connect(path)
        try:
            _seed_poll(conn, side="no")
        finally:
            conn.close()
        response = await _adopt(app)
        assert response.status_code == 422
        assert "NO holding" in response.json()["detail"] or "no side" in response.json()["detail"].lower()
        assert fake.calls == [], "the venue must not be reached for a NO holding"
        conn = sqlite3.connect(path)
        try:
            assert conn.execute(
                "SELECT COUNT(*) FROM parlay_positions"
            ).fetchone()[0] == 0
        finally:
            conn.close()

    async def test_a_null_side_is_also_refused_not_guessed_yes(self, build):
        """The unreadable case: a poll row with no `side` at all must refuse
        the same way a `'no'` one does, never default to YES."""
        app, fake, path = build()
        conn = sqlite3.connect(path)
        try:
            _seed_poll(conn, side=None)
        finally:
            conn.close()
        response = await _adopt(app)
        assert response.status_code == 422
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

    async def test_a_leg_with_no_readable_side_is_refused_not_guessed_yes(self, build):
        """kalshi-platform review #148, MUST FIX 3: `leg.get("side") or
        "yes"` used to guess. MUTATION: reverting the leg-side check back to
        that guess turns this red -- the adopted leg's side silently becomes
        `"yes"` instead of refusing."""
        bad_payload = {
            "market": {
                "ticker": TICKER,
                "mve_collection_ticker": "KXMVE-SOMETHING-R",
                "mve_selected_legs": [
                    {"event_ticker": "E1", "market_ticker": "M1", "side": "maybe"},
                ],
            }
        }
        app, fake, path = build(venue=FakeVenue(market_payload=bad_payload))
        conn = sqlite3.connect(path)
        try:
            _seed_poll(conn)
        finally:
            conn.close()
        response = await _adopt(app)
        assert response.status_code == 422
        assert "no readable side" in response.json()["detail"]

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

    async def test_a_concurrent_adopt_wins_the_race_and_this_one_is_refused(
        self, build, tmp_path
    ):
        """kalshi-platform review #148, MUST FIX 5: the first already-open
        check runs before the `await` on the venue's market, so a second
        request for the same ticker can start during that await and finish
        first. Simulated here by inserting the competing OPEN position
        (as a second connection would) from inside the fake's `get()` --
        exactly the window between the cheap early check and the write.
        MUTATION: dropping the `BEGIN IMMEDIATE` recheck immediately before
        `record_position` turns this red -- two open positions land on one
        ticker instead of one 409."""
        path = tmp_path / "t.db"

        def race():
            racer = sqlite3.connect(path)
            try:
                hedge.record_position(
                    racer,
                    now_ms=NOW_MS,
                    source="kalshi_combo",
                    label="the racing request",
                    stake_tenths=1,
                    return_tenths=2,
                    legs=[{"ticker": LEG_TICKERS[0], "side": "yes", "label": "L"}],
                    combo_ticker=TICKER,
                )
                racer.commit()
            finally:
                racer.close()

        app, fake, real_path = build(venue=FakeVenue(on_get=race))
        assert real_path == path
        conn = sqlite3.connect(path)
        try:
            _seed_poll(conn)
        finally:
            conn.close()

        response = await _adopt(app)
        assert response.status_code == 409

        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT id, label FROM parlay_positions "
                "WHERE combo_ticker = ? AND status = 'open'", (TICKER,),
            ).fetchall()
            assert len(rows) == 1, "the race produced two open positions on one ticker"
            assert rows[0]["label"] == "the racing request"
        finally:
            conn.close()

    async def test_an_unexpected_failure_releases_the_write_lock(
        self, tmp_path, monkeypatch
    ):
        """`BEGIN IMMEDIATE` takes the database's write lock. A failure that is
        not a `PositionRefused` must still roll back, or every other writer on
        the box waits on a transaction nobody will close."""
        path = tmp_path / "t.db"
        conn = store.init_db(path)
        conn.row_factory = sqlite3.Row
        try:
            _seed_poll(conn)

            def boom(*args, **kwargs):
                raise sqlite3.OperationalError("disk I/O error")

            monkeypatch.setattr(hedge, "record_position", boom)
            with pytest.raises(sqlite3.OperationalError):
                await hedge.adopt_venue_combo(
                    conn, api=FakeVenue(), ticker=TICKER, now_ms=NOW_MS
                )
            assert not conn.in_transaction, "the write lock was left held"
        finally:
            conn.close()


class TestANoLeg:
    """kalshi-platform review #148, MUST FIX 4: a NO leg's label must not
    print the YES question bare. `tests/fixtures/combo_priced_markets.json`
    combo 0 is a CAPTURED three-leg market whose third leg
    (`KXWNBASPREAD-26AUG09LVNY-NY13`) is a real `side: "no"` leg -- exactly
    the shape `_record_combo_position`/`leg_details_for` have no convention
    for, because every leg they have ever recorded already carries a label
    chosen for the side bought."""

    async def test_a_no_leg_is_prefixed_and_a_yes_leg_is_not(self, build):
        app, fake, path = build(venue=FakeVenue(market_payload=NO_LEG_PAYLOAD))
        conn = sqlite3.connect(path)
        try:
            _seed_poll(conn, ticker=NO_LEG_TICKER)
        finally:
            conn.close()

        response = await _adopt(app, ticker=NO_LEG_TICKER)
        assert response.status_code == 200, response.json()
        position_id = response.json()["position_id"]

        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            legs = conn.execute(
                "SELECT ticker, side, label FROM parlay_position_legs "
                "WHERE position_id = ? ORDER BY leg_index", (position_id,),
            ).fetchall()
        finally:
            conn.close()
        assert [leg["side"] for leg in legs] == ["yes", "yes", "no"]
        no_leg = legs[2]
        assert no_leg["ticker"] == "KXWNBASPREAD-26AUG09LVNY-NY13"
        assert no_leg["label"].startswith("NO -- ")
        for leg in legs[:2]:
            assert not leg["label"].startswith("NO -- ")


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
    shape the rest of this file assumes. `combo_priced_markets.json` is the
    second capture, used only by `TestANoLeg` for its real NO leg."""

    def test_the_fixture_is_a_kxmve_market_with_two_legs(self):
        assert TICKER.startswith("KXMVE")
        assert len(LEGS) == 2
        assert all(leg["side"] == "yes" for leg in LEGS)

    def test_the_no_leg_fixture_carries_a_real_no_leg(self):
        assert NO_LEG_TICKER.startswith("KXMVE")
        assert len(NO_LEG_LEGS) == 3
        assert [leg["side"] for leg in NO_LEG_LEGS] == ["yes", "yes", "no"]


class TestTheFrontendGlossRendersHonestly:
    """kalshi-platform review #148, MUST FIX 2: the copy ships with the
    basis. `venue_exposure` must say the stake is Kalshi's REPORTED position
    cost (market exposure), inferred and fee-exclusive, not a measured fill
    -- and it must render something, unlike `venue_fill`'s silence, because
    an adopted stake was never checked against a fill the way a `venue_fill`
    one was."""

    GLOSS_TS = REPO / "frontend" / "src" / "lib" / "stakeBasisGloss.ts"
    NODE = __import__("shutil").which("node")

    def test_the_constant_and_note_are_declared(self):
        source = self.GLOSS_TS.read_text(encoding="utf-8")
        assert 'STAKE_BASIS_VENUE_EXPOSURE = "venue_exposure"' in source
        assert "STAKE_BASIS_VENUE_EXPOSURE_NOTE" in source

    def test_the_note_names_market_exposure_and_disclaims_a_measured_fill(self):
        source = self.GLOSS_TS.read_text(encoding="utf-8")
        block = source.split("STAKE_BASIS_VENUE_EXPOSURE_NOTE =", 1)[1]
        note = block.split('"', 2)[1]
        lowered = note.lower()
        assert "market exposure" in lowered or "position cost" in lowered
        assert "inferred" in lowered
        assert "not a measured fill" in lowered

    @pytest.mark.skipif(
        NODE is None,
        reason="node is not on PATH; skipped rather than xfailed.",
    )
    def test_venue_exposure_renders_its_own_line_never_null(self):
        driver = self.GLOSS_TS.parent / "_laneC_adopt_basis_driver.mjs"
        driver.write_text(
            'import { stakeBasisNote } from "./stakeBasisGloss.ts";\n'
            'console.log(JSON.stringify({'
            ' note: stakeBasisNote("venue_exposure", "adopted_from_positions") }));\n',
            encoding="utf-8",
        )
        try:
            out = subprocess.run(
                [self.NODE, "--experimental-strip-types", str(driver)],
                capture_output=True, text=True, encoding="utf-8", timeout=60,
                cwd=str(self.GLOSS_TS.parent),
            )
        finally:
            driver.unlink(missing_ok=True)
        assert out.returncode == 0, f"node failed:\n{out.stdout}\n{out.stderr}"
        note = json.loads(out.stdout.strip())["note"]
        assert note is not None
        assert "measured fill" in note.lower()
