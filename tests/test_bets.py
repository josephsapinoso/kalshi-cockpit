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
