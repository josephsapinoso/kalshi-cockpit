"""The pass record: append-only, written by the gestures, counted, never rated.

Slice B6 (2026-08-22). The record could hold 39 settled bets and zero
evidence Joe ever chose not to bet; `desk_passes` makes the decision the
unit. What these tests establish: the table only ever grows (no UPDATE or
DELETE path in the codebase), the lockout tap writes exactly one pass per
night, the per-market POST requires auth like every mutation, and the count
lands on the /bets payload.

WHAT THIS DOES NOT ESTABLISH
----------------------------
That the count is a census of restraint -- only taps are recorded, so it is
a floor. And nothing here (or anywhere) scores a pass against an outcome;
the append-only grep below is structural, the never-scored rule is enforced
by the absence of any join, which the payload-shape test pins as counts-only.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx

from backend import passes
from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db

REPO = Path(__file__).resolve().parents[1]

NOW_MS = 1_786_615_200_000 + 10 * 3_600_000  # mid-evening on a 10:00Z day


def _live_app(tmp_path):
    path = tmp_path / "p.db"
    conn = db.init_db(path)
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, "
        "effective_from_ms, config_json, rationale) "
        "VALUES (1, 0, 0, '{}', 'test')"
    )
    conn.commit()
    conn.close()
    app = create_app(
        AppConfig(instance_mode="live", auth_token="secret-token", db_path=path)
    )
    return app, path


async def _post(app, url, headers=None, json=None):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        return await client.post(url, headers=headers, json=json)


HEADERS = {"Authorization": "Bearer secret-token"}


class TestThePassRecordIsAppendOnly:
    def test_no_update_or_delete_path_exists_in_the_codebase(self):
        """A "no" that can be edited afterwards is a story, not a record.
        Grepped over every backend source file; the INSERT assertion is the
        anti-vacuity anchor -- a renamed table would otherwise make this
        test pass by finding nothing."""
        writes = []
        inserts = []
        for source_file in sorted((REPO / "backend").rglob("*.py")):
            text = source_file.read_text(encoding="utf-8")
            if re.search(r"(UPDATE|DELETE\s+FROM)\s+desk_passes", text):
                writes.append(source_file.name)
            if "INSERT INTO desk_passes" in text:
                inserts.append(source_file.name)
        assert not writes, (
            f"an UPDATE/DELETE on desk_passes appeared in {writes}; the "
            f"pass record is append-only by decision"
        )
        assert inserts, (
            "no INSERT INTO desk_passes found anywhere -- the scan is "
            "vacuous (renamed table?) and proves nothing"
        )

    def test_the_module_writes_and_counts(self, tmp_path):
        conn = db.init_db(tmp_path / "p.db")
        passes.record_pass(conn, now_ms=NOW_MS, scope="tonight")
        passes.record_pass(
            conn, now_ms=NOW_MS + 1, scope="KXTEST-GAME", reason="tired"
        )
        summary = passes.pass_summary(conn)
        assert summary == {"total": 2, "first_ms": NOW_MS}

    def test_an_empty_reason_is_null_not_empty_string(self, tmp_path):
        """"Said nothing" is one state, not two."""
        conn = db.init_db(tmp_path / "p.db")
        passes.record_pass(conn, now_ms=NOW_MS, scope="KXT", reason="   ")
        row = conn.execute("SELECT reason FROM desk_passes").fetchone()
        assert row["reason"] is None


class TestTheLockoutWritesAPass:
    async def test_engaging_records_one_pass_for_tonight(self, tmp_path):
        """One gesture, two records: the "not tonight" tap is the decision
        to pass the night and must not need a second tap to be counted.

        Mutation run, red and restored byte-identical (2026-08-22): the
        `record_pass` call removed from `/api/desk/lockout` -- this test
        fails on an empty table."""
        app, path = _live_app(tmp_path)
        response = await _post(app, "/api/desk/lockout", headers=HEADERS)
        assert response.status_code == 200
        conn = db.open_db(path, read_only=True)
        rows = conn.execute("SELECT scope, reason FROM desk_passes").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["scope"] == "tonight"
        assert rows[0]["reason"] is None

    async def test_a_second_tap_is_the_same_decision_not_a_second_pass(
        self, tmp_path
    ):
        """The lockout is idempotent; the pass count must be too, or the
        record inflates by nervous re-taps."""
        app, path = _live_app(tmp_path)
        await _post(app, "/api/desk/lockout", headers=HEADERS)
        await _post(app, "/api/desk/lockout", headers=HEADERS)
        # The deprecated name is the same gesture again.
        await _post(app, "/api/estimates/lockout", headers=HEADERS)
        conn = db.open_db(path, read_only=True)
        count = conn.execute("SELECT COUNT(*) AS n FROM desk_passes").fetchone()
        conn.close()
        assert count["n"] == 1


class TestThePerMarketPass:
    async def test_it_requires_auth_like_every_mutation(self, tmp_path):
        app, _ = _live_app(tmp_path)
        response = await _post(
            app, "/api/desk/pass", json={"ticker": "KXTEST-GAME"}
        )
        assert response.status_code == 401

    async def test_it_writes_the_ticker_scope_with_the_optional_reason(
        self, tmp_path
    ):
        app, path = _live_app(tmp_path)
        response = await _post(
            app,
            "/api/desk/pass",
            headers=HEADERS,
            json={"ticker": "kxtest-game", "reason": "line moved against me"},
        )
        assert response.status_code == 200
        assert response.json()["recorded"] is True
        conn = db.open_db(path, read_only=True)
        row = conn.execute("SELECT scope, reason FROM desk_passes").fetchone()
        conn.close()
        assert row["scope"] == "KXTEST-GAME"  # uppercased like every ticker
        assert row["reason"] == "line moved against me"

    async def test_the_reason_is_optional(self, tmp_path):
        app, path = _live_app(tmp_path)
        response = await _post(
            app, "/api/desk/pass", headers=HEADERS, json={"ticker": "KXT"}
        )
        assert response.status_code == 200
        conn = db.open_db(path, read_only=True)
        assert (
            conn.execute("SELECT reason FROM desk_passes").fetchone()["reason"]
            is None
        )
        conn.close()


class TestTheCountLandsOnTheBetsPayload:
    async def test_the_headline_numbers_are_served_as_counts_only(
        self, tmp_path
    ):
        """`passes` carries a total and a first-seen instant and nothing
        else -- no rate, no grade, no join against outcomes. The key-set pin
        is the never-scored rule's tripwire."""
        app, path = _live_app(tmp_path)
        await _post(app, "/api/desk/lockout", headers=HEADERS)
        await _post(
            app, "/api/desk/pass", headers=HEADERS, json={"ticker": "KXT"}
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            payload = (await client.get("/api/bets")).json()
        assert payload["passes"]["total"] == 2
        assert isinstance(payload["passes"]["first_ms"], int)
        assert set(payload["passes"]) == {"total", "first_ms"}
