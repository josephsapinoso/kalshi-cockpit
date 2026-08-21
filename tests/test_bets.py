"""Joe's own record: the one registered formula, refusals, and honest totals.

Every row here is synthetic (the operator-data ruling: no account data enters
the repo, even sanitized). What this file establishes is the arithmetic and
the honesty contract of `backend/bets.py` and `GET /api/bets`; what it does
NOT establish is completeness of the mirror itself -- the poller's own tests
own that, and the screen states the gap in words.
"""

from __future__ import annotations

import httpx

from backend import bets
from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db

# Fixed instants on the 10:00Z day used everywhere else: NOW is mid-evening,
# ROLL is that day's start.
DAY_HOUR = 10
ROLL_MS = 1_786_615_200_000  # 2026-08-09T10:00:00Z, arbitrary but on-hour
NOW_MS = ROLL_MS + 10 * 3_600_000


def _fill(conn, *, ticker="KXT-A", filled_ms=None, count=2.0,
          price_tenths=400, source="venue_hand"):
    conn.execute(
        "INSERT INTO fills (ticker, filled_ms, count, price_tenths, is_taker, "
        "fee_predicted, fee_model_used, source) VALUES (?, ?, ?, ?, 1, 0.0, "
        "'model_a_deci', ?)",
        (ticker, NOW_MS - 3_600_000 if filled_ms is None else filled_ms,
         count, price_tenths, source),
    )
    conn.commit()


def _fills_poll(conn, *, polled_ms, ok=True):
    conn.execute(
        "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count) "
        "VALUES (?, 'fills', ?, 1)",
        (polled_ms, 1 if ok else 0),
    )
    conn.commit()


def _insert(conn, **overrides):
    row = {
        "ticker": "KXTEST-GAME",
        "event_ticker": "KXTEST",
        "market_result": "yes",
        "settled_ms": 1_000,
        "side": "yes",
        "contracts": 2.0,
        "entry_price_tenths": 400,
        "fee_cost_tenths": 20,
    }
    row.update(overrides)
    conn.execute(
        "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
        "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths) "
        "VALUES (:ticker, :event_ticker, :market_result, :settled_ms, :side, "
        ":contracts, :entry_price_tenths, :fee_cost_tenths)",
        row,
    )
    conn.commit()


class TestTheRegisteredFormula:
    """net = payout - cost - fee, in integer tenths, per Amendment A2."""

    def test_a_win_pays_a_dollar_a_contract(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _insert(conn)  # 2 contracts at 40.0c, 2.0c fee, won
        row = conn.execute("SELECT * FROM venue_settlements").fetchone()
        # payout 2000, cost 800, fee 20
        assert bets.settlement_net_tenths(row) == 1180

    def test_a_loss_pays_nothing_and_still_pays_the_fee(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _insert(conn, market_result="no")
        row = conn.execute("SELECT * FROM venue_settlements").fetchone()
        assert bets.settlement_net_tenths(row) == -820

    def test_a_void_refuses_rather_than_inventing_a_payout(self, tmp_path):
        """A `market_result` that is neither yes nor no has no registered
        payout. None, never 0 -- a settled scratch is not a wash of $0.00."""
        conn = db.init_db(tmp_path / "b.db")
        _insert(conn, market_result=None)
        row = conn.execute("SELECT * FROM venue_settlements").fetchone()
        assert bets.settlement_net_tenths(row) is None

    def test_unreadable_price_or_fee_refuses(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _insert(conn, entry_price_tenths=None)
        _insert(conn, fee_cost_tenths=None, settled_ms=2_000)
        for row in conn.execute("SELECT * FROM venue_settlements").fetchall():
            assert bets.settlement_net_tenths(row) is None


class TestTheTotalsAreHonest:
    def test_totals_cover_the_table_while_the_list_is_windowed(self, tmp_path):
        """The strip must be a claim about the record, not about the most
        recent `limit` rows wearing that label (the /api/ledger lesson)."""
        conn = db.init_db(tmp_path / "b.db")
        for i in range(3):
            _insert(conn, settled_ms=1_000 + i)
        record = bets.bets_record(conn, limit=2)
        assert record["returned"] == 2
        assert record["total"] == 3
        assert record["totals"]["computable"] == 3
        assert record["totals"]["net_tenths"] == 3 * 1180

    def test_an_uncomputable_row_is_counted_beside_the_sum_not_in_it(
        self, tmp_path
    ):
        conn = db.init_db(tmp_path / "b.db")
        _insert(conn)
        _insert(conn, market_result=None, settled_ms=2_000)
        record = bets.bets_record(conn)
        assert record["totals"]["net_tenths"] == 1180
        assert record["totals"]["computable"] == 1
        assert record["totals"]["uncomputable"] == 1
        # The refused row still appears in the record, with its refusal.
        refused = [b for b in record["bets"] if b["net_tenths"] is None]
        assert len(refused) == 1
        assert refused[0]["won"] is None

    def test_wins_and_losses_split_the_computable_rows(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _insert(conn)
        _insert(conn, market_result="no", settled_ms=2_000)
        totals = bets.bets_record(conn)["totals"]
        assert totals["wins"] == 1
        assert totals["losses"] == 1


class TestTheRoute:
    async def test_the_record_is_served_and_never_reads_the_estimate_log(
        self, tmp_path
    ):
        """The endpoint's embargo line: `venue_settlements` is the wallet,
        `bet_estimates` is the log, and the log is embargoed forever. The
        source-level guard is the module's SQL touching only the one table;
        this test pins the served shape and the empty-table honesty."""
        path = tmp_path / "b.db"
        conn = db.init_db(path)
        _insert(conn)
        conn.close()
        app = create_app(AppConfig(instance_mode="demo", db_path=path))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/api/bets")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["bets"][0]["net_tenths"] == 1180
        assert payload["bets"][0]["net_display"] == "+$1.18"
        assert payload["bets"][0]["entry_price_display"] == "40c"
        assert "bet_estimates" not in response.text

    async def test_an_empty_mirror_is_an_empty_list_not_an_error(self, tmp_path):
        path = tmp_path / "b.db"
        db.init_db(path).close()
        app = create_app(AppConfig(instance_mode="demo", db_path=path))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/api/bets")
        assert response.status_code == 200
        assert response.json() == {
            "bets": [],
            "total": 0,
            "returned": 0,
            "totals": {
                "net_tenths": 0,
                "net_display": "+$0.00",
                "computable": 0,
                "uncomputable": 0,
                "wins": 0,
                "losses": 0,
            },
        }


class TestTonightRefusesBeforeItFlatters:
    """The `tonight` strip contract (the 2026-08-21 partner ruling):
    unsigned, distinct-ticker count, whole-population stake, and NULL --
    never 0 -- off a stale mirror.

    Mutations run, each red and the file restored byte-identical:
    (1) staleness check removed from `tonight_activity` -- the stale test
    fails (it would report bets off a dead mirror); (2) `DISTINCT`
    dropped from the count -- the partial-fill test fails; (3) the
    `filled_ms >= ?` bound dropped -- the day-boundary test fails.
    """

    def _fresh(self, conn):
        _fills_poll(conn, polled_ms=NOW_MS - 60_000)

    def test_a_bet_is_a_distinct_ticker_not_a_fill_row(self, tmp_path):
        conn = db.init_db(tmp_path / "t.db")
        self._fresh(conn)
        _fill(conn, ticker="KXT-A", count=1.0)
        _fill(conn, ticker="KXT-A", count=1.0)  # partial fill, same decision
        _fill(conn, ticker="KXT-B", count=2.0)
        tonight = bets.tonight_activity(
            conn, now_ms=NOW_MS, day_start_hour=DAY_HOUR
        )
        assert tonight["bets"] == 2
        # 1x400 + 1x400 + 2x400 = 1600 tenths, unsigned
        assert tonight["staked_tenths"] == 1600
        assert tonight["staked_display"] == "$1.60"

    def test_engine_and_hand_fills_both_count(self, tmp_path):
        """No `source` filter, deliberately: ADR 0043's split keeps the
        fee-calibration population clean, but committed money is committed
        money whichever hand placed it."""
        conn = db.init_db(tmp_path / "t.db")
        self._fresh(conn)
        _fill(conn, ticker="KXT-A", source="venue_hand")
        _fill(conn, ticker="KXT-B", source="engine")
        tonight = bets.tonight_activity(
            conn, now_ms=NOW_MS, day_start_hour=DAY_HOUR
        )
        assert tonight["bets"] == 2

    def test_yesterdays_fills_are_outside_the_day(self, tmp_path):
        conn = db.init_db(tmp_path / "t.db")
        self._fresh(conn)
        _fill(conn, ticker="KXT-OLD", filled_ms=ROLL_MS - 1)
        _fill(conn, ticker="KXT-NEW", filled_ms=ROLL_MS)
        tonight = bets.tonight_activity(
            conn, now_ms=NOW_MS, day_start_hour=DAY_HOUR
        )
        assert tonight["bets"] == 1
        assert tonight["day_start_ms"] == ROLL_MS

    def test_a_stale_mirror_refuses_rather_than_reporting_zero(self, tmp_path):
        """Reporting "no bets tonight" off a 31-minute-old read is a false
        negative in the flattering direction, on the screen built to
        interrupt."""
        conn = db.init_db(tmp_path / "t.db")
        stale_ms = NOW_MS - bets.TONIGHT_STALE_AFTER_MS - 1
        _fills_poll(conn, polled_ms=stale_ms)
        _fill(conn, ticker="KXT-A")
        tonight = bets.tonight_activity(
            conn, now_ms=NOW_MS, day_start_hour=DAY_HOUR
        )
        assert tonight["bets"] is None
        assert tonight["staked_tenths"] is None
        assert tonight["staked_display"] is None
        assert tonight["as_of_ms"] == stale_ms  # the reader renders "since"

    def test_a_failed_poll_does_not_count_as_a_read(self, tmp_path):
        conn = db.init_db(tmp_path / "t.db")
        _fills_poll(conn, polled_ms=NOW_MS - 60_000, ok=False)
        tonight = bets.tonight_activity(
            conn, now_ms=NOW_MS, day_start_hour=DAY_HOUR
        )
        assert tonight["bets"] is None
        assert tonight["as_of_ms"] is None

    def test_a_fresh_empty_night_is_a_true_zero(self, tmp_path):
        conn = db.init_db(tmp_path / "t.db")
        self._fresh(conn)
        tonight = bets.tonight_activity(
            conn, now_ms=NOW_MS, day_start_hour=DAY_HOUR
        )
        assert tonight["bets"] == 0
        assert tonight["staked_tenths"] == 0


class TestTheSlateCarriesTonightBesideMoneyNotInsideIt:
    async def test_the_payload_shape(self, tmp_path):
        path = tmp_path / "t.db"
        conn = db.init_db(path)
        conn.execute(
            "INSERT INTO strategy_configs (version, created_ms, "
            "effective_from_ms, config_json, rationale) "
            "VALUES (1, 0, 0, '{}', 'test')"
        )
        conn.commit()
        conn.close()
        app = create_app(AppConfig(instance_mode="demo", db_path=path))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/api/slate")
        assert response.status_code == 200
        payload = response.json()
        tonight = payload["tonight"]
        # A sibling of `money`, never inside it: `money` has a contract
        # about never summing, and this is a different kind of number.
        assert payload["money"] is None or "bets" not in payload["money"]
        assert set(tonight) == {
            "day_start_ms", "as_of_ms", "bets", "staked_tenths",
            "staked_display", "lockout_until_ms",
        }
        # A fresh database has never polled fills: refusal, not zero.
        assert tonight["bets"] is None
        assert tonight["lockout_until_ms"] is None


class TestTheDeskLockout:
    async def test_the_desk_route_engages_and_the_old_route_agrees(
        self, tmp_path
    ):
        """Both routes write the one `self_lockouts` table, so they cannot
        come to disagree; the study-named route stays deprecated-but-working
        because a deployed frontend may still call it."""
        path = tmp_path / "t.db"
        conn = db.init_db(path)
        conn.execute(
            "INSERT INTO strategy_configs (version, created_ms, "
            "effective_from_ms, config_json, rationale) "
            "VALUES (1, 0, 0, '{}', 'test')"
        )
        conn.commit()
        conn.close()
        app = create_app(
            AppConfig(
                instance_mode="live", auth_token="secret-token", db_path=path
            )
        )
        headers = {"Authorization": "Bearer secret-token"}
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            desk = await client.post("/api/desk/lockout", headers=headers)
            assert desk.status_code == 200
            until = desk.json()["until_ms"]
            # Idempotent across BOTH names: the release instant is a
            # property of the clock, not of which route was tapped.
            old = await client.post("/api/estimates/lockout", headers=headers)
            assert old.status_code == 200
            assert old.json()["until_ms"] == until
            # And the slate reads it back in the tonight block.
            slate = await client.get("/api/slate")
            assert slate.json()["tonight"]["lockout_until_ms"] == until

    async def test_the_desk_route_requires_auth(self, tmp_path):
        path = tmp_path / "t.db"
        db.init_db(path).close()
        app = create_app(
            AppConfig(
                instance_mode="live", auth_token="secret-token", db_path=path
            )
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post("/api/desk/lockout")
        assert response.status_code == 401
