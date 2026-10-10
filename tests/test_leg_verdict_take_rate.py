"""Every leg verdict says how often the verdicts have said take (#345).

A BASE RATE in counts ("says take on X of N"), never a percentage and never a
comparison of a verdict to an outcome (#320 forbids a scout-accuracy figure).

What this does not establish: that the counts are a good filter measure, or
that the line reads well at phone width (source assertions; no JS runner).
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routers import leg_verdicts as router
from backend.store import db as store

REPO = Path(__file__).resolve().parents[1]
COMPONENT = REPO / "frontend" / "src" / "components" / "LegVerdicts.tsx"
API = REPO / "frontend" / "src" / "lib" / "api.ts"


def _client(db_path):
    app = FastAPI()

    def get_conn():
        c = store.open_db(db_path)
        try:
            yield c
        finally:
            c.close()

    router.register(
        app,
        app_config=SimpleNamespace(db_path=db_path),
        get_conn=get_conn,
        require_auth=lambda: None,
    )
    return TestClient(app)


def _call(conn, agent, verdict):
    conn.execute(
        "INSERT INTO agent_calls (called_ms, agent, model, verdict) "
        "VALUES (?, ?, 'm', ?)",
        (store.now_ms(), agent, verdict),
    )


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "take_rate.db"
    store.init_db(p).close()
    return p


def _strip(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", src, flags=re.MULTILINE)


class TestALegVerdictShowsItsTakeRate:
    def test_the_payload_serves_take_and_judged_counts(self, db_path):
        conn = store.open_db(db_path)
        for v in ["take", "take", "take", "pass", None]:
            _call(conn, "leg_verdict", v)
        _call(conn, "leg_verdict", "over_length")  # not judged
        _call(conn, "scout", "take")  # another agent
        conn.commit()
        conn.close()
        body = _client(db_path).get(
            "/api/leg-verdicts", params={"leg": "T:yes"}
        ).json()
        assert body["take_rate"] == {"take": 3, "judged": 4}

    def test_an_empty_table_serves_zero_of_zero(self, db_path):
        body = _client(db_path).get("/api/leg-verdicts").json()
        assert body["take_rate"] == {"take": 0, "judged": 0}

    def test_the_component_prints_x_of_n(self):
        src = _strip(COMPONENT.read_text(encoding="utf-8"))
        assert re.search(
            r"says take on \{takeRate\.take\} of \{takeRate\.judged\}", src
        )
        # Absent is not zero: the line is gated on the field being present.
        assert re.search(r"\{takeRate && \(", src)
        # Counts, never a bare percentage.
        assert "%" not in re.search(r"says take on.*", src).group(0)
        assert "toFixed" not in src

    def test_the_client_parser_keeps_the_field(self):
        api = API.read_text(encoding="utf-8")
        start = api.index("function legVerdictBody")
        end = api.index("UNREADABLE_LEG_VERDICTS", start)
        assert "take_rate" in api[start:end]

    def test_the_count_is_one_bounded_aggregate(self, db_path):
        conn = store.open_db(db_path)
        plan = " ".join(
            str(tuple(r))
            for r in conn.execute("EXPLAIN QUERY PLAN " + router.TAKE_RATE_SQL)
        )
        conn.close()
        # Found 2026-10-10: a scan of agent_calls (no index on `agent`), no
        # temp b-tree; the table is ~3 rows per convening, so it is bounded.
        assert "agent_calls" in plan and "TEMP B-TREE" not in plan
