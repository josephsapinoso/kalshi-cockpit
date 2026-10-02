"""The hand-bet path is a function now, and it can be called as one.

ADR 0192 §2.7 (S3, #266) moved `POST /api/manual-orders`'s body out of the
`create_app` closure into `backend/manual_order.place_manual_order`, taking a
connection, the venue port (`live_quotes`), the placer's REST port
(`combo_api`) and a clock. These tests call it directly, with no `TestClient`
and no app, which is the proof that the seam is real rather than a rename:
check 0 (reachability), check 4 (the structural ceilings) and check 13 (the
position written through `positions.record_order_fill`).

Check 13 runs the **armed** construction -- `MANUAL_ORDERS_ARE_DRY_RUNS` is
left at its deployed False -- against a fake REST client that answers with
the synthetic V2 create-order shape in `tests/fixtures/create_order_
responses.json` (transcribed from the C0 probe; see that file's provenance).
`conftest.py` still strips the credentials, so nothing here can reach Kalshi:
the only REST client in play is the one passed in.

What this does NOT establish: that the route adapter passes the right ports
(every TestClient suite over `/api/manual-orders` does), or anything about the
venue -- the fill is a fixture, and the clock is fixed.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend import manual_order
from backend.api.schemas import ManualOrderRequest
from backend.config import AppConfig, ManualOrderConfig, OddsConfig, RiskConfig
from backend.store import db
from backend.store import manual_orders as manual_store

from tests.test_combo_fill_is_watched_for_a_hedge import _seed_lookup
from tests.test_manual_orders import (
    COMBO_TICKER,
    ENABLED,
    StubQuotes,
    _base_db,
    _body,
    _payload,
)

FIXTURE = Path(__file__).parent / "fixtures" / "create_order_responses.json"
NOW_MS = 1_790_000_000_000


class FakeRest:
    """The placer's REST port. Answers the create-order POST with the
    captured filled-IOC shape, echoing the request's `client_order_id`."""

    def __init__(self):
        self.posts: list[tuple[str, dict]] = []

    async def post(self, path, *, json_body):
        self.posts.append((path, json_body))
        response = dict(
            json.loads(FIXTURE.read_text(encoding="utf-8"))["create_ioc_filled_201"]
        )
        response["client_order_id"] = json_body["client_order_id"]
        return response


async def _call(path, request, *, quotes=None, manual=ENABLED, rest=None):
    conn = db.open_db(path)
    try:
        return await manual_order.place_manual_order(
            conn,
            ManualOrderRequest(**request),
            app_config=AppConfig(
                instance_mode="live", auth_token="secret-token", db_path=path
            ),
            manual_config=manual,
            risk=RiskConfig.load(),
            odds=OddsConfig.load_without_credentials(),
            live_quotes=lambda: quotes or StubQuotes(),
            combo_api=lambda: rest,
            now_ms=lambda: NOW_MS,
        )
    finally:
        conn.close()


def _refusals(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT * FROM manual_order_refusals ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


class TestTheHandBetPathRunsWithoutAnApp:
    async def test_check_0_refuses_when_the_path_is_not_enabled(self, tmp_path):
        path = _base_db(tmp_path)

        with pytest.raises(HTTPException) as refused:
            await _call(
                path, _body(), manual=ManualOrderConfig(enabled=False)
            )

        assert refused.value.status_code == 403
        assert "MANUAL_ORDERS_ENABLED" in refused.value.detail
        (row,) = _refusals(path)
        assert row["check_number"] == 0
        # The injected clock, not the wall clock, stamps the record.
        assert row["created_ms"] == NOW_MS

    async def test_check_4_refuses_a_combination_without_the_acknowledgement(
        self, tmp_path
    ):
        path = _base_db(tmp_path)

        with pytest.raises(HTTPException) as refused:
            await _call(path, _body(ticker=COMBO_TICKER))

        assert refused.value.status_code == 422
        assert "need the acknowledgement" in refused.value.detail
        (row,) = _refusals(path)
        assert (row["check_number"], row["check_name"]) == (
            4, "structural_ceilings",
        )

    async def test_check_13_writes_the_fill_through_the_positions_module(
        self, tmp_path
    ):
        assert manual_store.MANUAL_ORDERS_ARE_DRY_RUNS is False, (
            "this test drives the armed construction; if the path is ever "
            "disarmed, it should say so rather than silently run dry"
        )
        path = _base_db(tmp_path)
        _seed_lookup(path)
        rest = FakeRest()

        body = await _call(
            path,
            _body(ticker=COMBO_TICKER, combo_acknowledged=True),
            quotes=StubQuotes(
                _payload(ticker=COMBO_TICKER, yes_ask_size=1000.0,
                         exchange_index=1)
            ),
            rest=rest,
        )

        assert len(rest.posts) == 1, "exactly one order left, through the port"
        assert body["status"] == "filled"
        assert body["dry_run"] is False
        assert body["hedge_position_id"] is not None, body["hedge_position_note"]
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            position = conn.execute(
                "SELECT * FROM parlay_positions WHERE id = ?",
                (body["hedge_position_id"],),
            ).fetchone()
        finally:
            conn.close()
        assert position["fill_source"] == "manual_order"
        assert position["fill_ref"] == body["manual_order_id"]
        assert position["placed_ms"] == NOW_MS
