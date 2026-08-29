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
from backend.analysis.clv import DEFAULT_HORIZON_HOURS
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
        "position_first_seen_ms": None,
    }
    row.update(overrides)
    conn.execute(
        "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
        "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths, "
        "position_first_seen_ms) "
        "VALUES (:ticker, :event_ticker, :market_result, :settled_ms, :side, "
        ":contracts, :entry_price_tenths, :fee_cost_tenths, "
        ":position_first_seen_ms)",
        row,
    )
    conn.commit()


def _market(conn, *, ticker="KXTEST-GAME"):
    """The discovery row `closing_lines` FKs against."""
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, first_seen_ms, last_seen_ms) "
        "VALUES (?, 0, 0)",
        (ticker,),
    )
    conn.commit()


def _closing_line(
    conn, *, ticker="KXTEST-GAME", horizon_hours=DEFAULT_HORIZON_HOURS,
    observed_ms=500, yes_bid_tenths=520, yes_ask_tenths=540,
):
    """A stored closing line. Caller must have inserted the market row first."""
    conn.execute(
        "INSERT INTO closing_lines (ticker, horizon_hours, observed_ms, "
        "yes_bid_tenths, yes_ask_tenths) VALUES (?, ?, ?, ?, ?)",
        (ticker, horizon_hours, observed_ms, yes_bid_tenths, yes_ask_tenths),
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


class TestPerBetCLV:
    """`bets.bet_clv` -- per-row only, no average or hit rate anywhere here
    (the partner's hard constraint, checked below by grepping the module).
    """

    def test_a_yes_bet_scores_against_the_close_mid(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _market(conn)
        _closing_line(conn, observed_ms=500, yes_bid_tenths=520, yes_ask_tenths=540)
        _insert(conn, side="yes", entry_price_tenths=480, position_first_seen_ms=100)
        record = bets.bets_record(conn)
        bet = record["bets"][0]
        # mid 530, bought at 480: +50 tenths = +5.0c
        assert bet["clv_tenths"] == 50.0
        assert bet["clv_display"] == "+5.0c"
        assert bet["clv_refusal_reason"] is None
        assert bet["close_mid_tenths"] == 530
        assert bet["close_display"] == "53c"

    def test_the_no_side_uses_the_complement(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _market(conn)
        _closing_line(conn, observed_ms=500, yes_bid_tenths=520, yes_ask_tenths=540)
        _insert(conn, side="no", entry_price_tenths=480, position_first_seen_ms=100)
        bet = bets.bets_record(conn)["bets"][0]
        # NO worth (1000-530)=470, bought at 480: -10 tenths
        assert bet["clv_tenths"] == -10.0
        assert bet["clv_display"] == "-1.0c"

    def test_no_closing_line_refuses(self, tmp_path):
        """The structural refusal the partner expected for most hand bets:
        no discovery row, no link, or the game just hasn't been scored yet."""
        conn = db.init_db(tmp_path / "b.db")
        _insert(conn, position_first_seen_ms=100)
        bet = bets.bets_record(conn)["bets"][0]
        assert bet["clv_tenths"] is None
        assert bet["clv_display"] is None
        assert bet["clv_refusal_reason"] == "no_closing_line"
        assert bet["close_mid_tenths"] is None

    def test_an_unreadable_close_refuses(self, tmp_path):
        conn = db.init_db(tmp_path / "b.db")
        _market(conn)
        _closing_line(conn, yes_bid_tenths=None, yes_ask_tenths=None)
        _insert(conn, position_first_seen_ms=100)
        bet = bets.bets_record(conn)["bets"][0]
        assert bet["clv_tenths"] is None
        assert bet["clv_refusal_reason"] == "unreadable_close"

    def test_an_unknown_entry_time_refuses(self, tmp_path):
        """`position_first_seen_ms` NULL means the poller never caught the
        fill landing -- refuse, don't treat it as 'before everything'."""
        conn = db.init_db(tmp_path / "b.db")
        _market(conn)
        _closing_line(conn, observed_ms=500)
        _insert(conn, position_first_seen_ms=None)
        bet = bets.bets_record(conn)["bets"][0]
        assert bet["clv_tenths"] is None
        assert bet["clv_refusal_reason"] == "entry_time_unknown"

    def test_an_entry_after_the_close_refuses(self, tmp_path):
        """Scoring an entry against a price observed before it existed would
        put market drift into a number meant to detect edge."""
        conn = db.init_db(tmp_path / "b.db")
        _market(conn)
        _closing_line(conn, observed_ms=500)
        _insert(conn, position_first_seen_ms=501)
        bet = bets.bets_record(conn)["bets"][0]
        assert bet["clv_tenths"] is None
        assert bet["clv_refusal_reason"] == "entry_after_close"

    def test_only_the_primary_horizon_is_read(self, tmp_path):
        """A line stored at the control horizon must not be picked up here --
        `scoring.py` scores `recommendations` at the primary horizon only,
        for the same reason: mixing horizons hides which anchor produced a
        number."""
        conn = db.init_db(tmp_path / "b.db")
        _market(conn)
        _closing_line(conn, horizon_hours=1.0, observed_ms=500)
        _insert(conn, position_first_seen_ms=100)
        bet = bets.bets_record(conn)["bets"][0]
        assert bet["clv_refusal_reason"] == "no_closing_line"

    def test_clv_coverage_counts_the_whole_table_not_the_window(self, tmp_path):
        """"Scored on N of {total}" is a claim about the record (slice B5).
        The scored row here is the OLDEST, so a coverage computed off the
        `limit=1` window -- which holds only the newest, refused row --
        would report 0 and the mutation below turns exactly that red.

        Mutation run, red and restored byte-identical (2026-08-22): the
        `bet_clv` call moved back below the `len(bets) >= limit` continue --
        this test fails with scored == 0."""
        conn = db.init_db(tmp_path / "b.db")
        _market(conn)
        _closing_line(conn, observed_ms=500)
        _insert(conn, settled_ms=1_000, position_first_seen_ms=100)  # scored
        _insert(conn, ticker="KXOTHER", settled_ms=2_000,
                position_first_seen_ms=100)  # newest; no line -> refused
        record = bets.bets_record(conn, limit=1)
        assert record["returned"] == 1
        assert record["bets"][0]["ticker"] == "KXOTHER"
        assert record["clv_coverage"]["scored"] == 1
        assert record["clv_coverage"]["refusals"] == {"no_closing_line": 1}

    def test_scored_and_refused_partition_the_record(self, tmp_path):
        """Every row is exactly one of scored or refused-with-reason, so
        unmeasured can never render identically to bad."""
        conn = db.init_db(tmp_path / "b.db")
        _market(conn)
        _closing_line(conn, observed_ms=500)
        _insert(conn, settled_ms=1_000, position_first_seen_ms=100)
        _insert(conn, settled_ms=2_000, position_first_seen_ms=None)
        _insert(conn, settled_ms=3_000, position_first_seen_ms=501)
        record = bets.bets_record(conn)
        coverage = record["clv_coverage"]
        assert coverage["scored"] + sum(coverage["refusals"].values()) == (
            record["total"]
        )
        assert coverage["refusals"] == {
            "entry_time_unknown": 1,
            "entry_after_close": 1,
        }

    def test_the_coverage_is_counts_only_no_clv_value_enters_it(self, tmp_path):
        """The no-aggregate constraint's edge: a count of measurements is
        allowed, any combination of their VALUES is not. The block must
        carry integers and reason counts, nothing float-valued."""
        conn = db.init_db(tmp_path / "b.db")
        _market(conn)
        _closing_line(conn, observed_ms=500)
        _insert(conn, position_first_seen_ms=100)
        coverage = bets.bets_record(conn)["clv_coverage"]
        assert set(coverage) == {"scored", "refusals"}
        assert isinstance(coverage["scored"], int)
        assert all(
            isinstance(v, int) for v in coverage["refusals"].values()
        )

    def test_module_computes_no_aggregate_clv(self):
        """The partner's hard constraint, checked at the source: no average,
        no hit rate, no beat-the-close rate anywhere in this module until
        n >= 30 with the per-group view beside it."""
        import inspect

        source = inspect.getsource(bets)
        for banned in ("mean_clv", "avg_clv", "beat_close_rate", "hit_rate"):
            assert banned not in source, f"{banned} found in backend/bets.py"


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
            "clv_coverage": {"scored": 0, "refusals": {}},
            "totals": {
                "net_tenths": 0,
                "net_display": "+$0.00",
                "computable": 0,
                "uncomputable": 0,
                "wins": 0,
                "losses": 0,
            },
            # A database that has never polled refuses everything, in words.
            "open_positions": {
                "count": None,
                "count_as_of_ms": None,
                # No read means no age. Never 0, which reads as "just now".
                "count_age_ms": None,
                "value_tenths": None,
                "value_display": None,
                "value_as_of_ms": None,
                "value_age_ms": None,
                "value_refusal": "never observed",
            },
            "lockout_until_ms": None,
            # No passes recorded is words on the screen, not a 1970 date.
            "passes": {"total": 0, "first_ms": None},
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


class TestOpenPositionsRefuseBeforeTheyFlatter:
    """`bets.open_positions` (slice B3, 2026-08-22): the count is the 12-hour
    positions poll's `row_count`, counted and never parsed; the value is the
    venue's own `portfolio_value`, whose unit is pinned only at zero. Stale
    or unpinned refuses to None with the words served -- "nothing at risk"
    off a dead poller is the false negative in the flattering direction.

    Mutation run, red and restored byte-identical (2026-08-22): the
    `POSITIONS_STALE_AFTER_MS` bound removed from the count read -- the
    stale-count test fails (a 27-hour-old count is served as current).
    """

    def _positions_poll(self, conn, *, polled_ms, row_count=3, ok=True):
        conn.execute(
            "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count) "
            "VALUES (?, 'positions', ?, ?)",
            (polled_ms, 1 if ok else 0, row_count),
        )
        conn.commit()

    def _snapshot(self, conn, *, observed_ms, value_tenths):
        conn.execute(
            "INSERT INTO venue_balance_snapshots "
            "(observed_ms, balance_tenths, portfolio_value_tenths) "
            "VALUES (?, 2560, ?)",
            (observed_ms, value_tenths),
        )
        conn.commit()

    def test_a_fresh_count_and_a_pinned_zero_value_are_served(self, tmp_path):
        conn = db.init_db(tmp_path / "p.db")
        self._positions_poll(conn, polled_ms=NOW_MS - 3_600_000, row_count=3)
        self._snapshot(conn, observed_ms=NOW_MS - 60_000, value_tenths=0)
        block = bets.open_positions(conn, now_ms=NOW_MS)
        assert block["count"] == 3
        assert block["count_as_of_ms"] == NOW_MS - 3_600_000
        assert block["value_tenths"] == 0
        assert block["value_display"] == "$0.00"
        assert block["value_refusal"] is None

    def test_a_stale_count_refuses_and_keeps_its_as_of(self, tmp_path):
        """27 hours is past the 26h bound (two 12h mirror cycles + grace):
        the count refuses, the clock stays so the screen can say 'since'."""
        conn = db.init_db(tmp_path / "p.db")
        stale = NOW_MS - bets.POSITIONS_STALE_AFTER_MS - 3_600_000
        self._positions_poll(conn, polled_ms=stale, row_count=3)
        block = bets.open_positions(conn, now_ms=NOW_MS)
        assert block["count"] is None
        assert block["count_as_of_ms"] == stale

    def test_a_failed_poll_is_not_a_read(self, tmp_path):
        conn = db.init_db(tmp_path / "p.db")
        self._positions_poll(conn, polled_ms=NOW_MS - 60_000, ok=False)
        block = bets.open_positions(conn, now_ms=NOW_MS)
        assert block["count"] is None
        assert block["count_as_of_ms"] is None

    def test_an_unpinned_value_refuses_with_its_reason_not_a_zero(
        self, tmp_path
    ):
        """The stored NULL means `parse_portfolio_value_tenths` refused a
        non-zero value (unit unpinned) -- the expected state whenever a
        position is actually open. Words, never $0.00."""
        conn = db.init_db(tmp_path / "p.db")
        self._snapshot(conn, observed_ms=NOW_MS - 60_000, value_tenths=None)
        block = bets.open_positions(conn, now_ms=NOW_MS)
        assert block["value_tenths"] is None
        assert block["value_display"] is None
        assert "unit" in block["value_refusal"]

    def test_a_stale_value_refuses_on_its_own_five_minute_clock(self, tmp_path):
        conn = db.init_db(tmp_path / "p.db")
        stale = NOW_MS - bets.TONIGHT_STALE_AFTER_MS - 1
        self._snapshot(conn, observed_ms=stale, value_tenths=0)
        block = bets.open_positions(conn, now_ms=NOW_MS)
        assert block["value_tenths"] is None
        assert "not read" in block["value_refusal"]
        assert block["value_as_of_ms"] == stale

    def test_the_block_never_sums_and_never_signs(self, tmp_path):
        """TonightStrip's unsigned rule, pinned: no net, no P&L, no
        mark-to-market, no field that could carry cash+positions."""
        conn = db.init_db(tmp_path / "p.db")
        self._positions_poll(conn, polled_ms=NOW_MS - 60_000)
        self._snapshot(conn, observed_ms=NOW_MS - 60_000, value_tenths=0)
        block = bets.open_positions(conn, now_ms=NOW_MS)
        assert set(block) == {
            "count", "count_as_of_ms", "count_age_ms", "value_tenths",
            "value_display", "value_as_of_ms", "value_age_ms",
            "value_refusal",
        }
        forbidden = {"total", "net", "pnl", "profit", "loss", "change",
                     "mark", "unrealised", "unrealized"}
        assert not (set(block) & forbidden)

    async def test_the_slate_serves_it_beside_money_not_inside(self, tmp_path):
        path = tmp_path / "p.db"
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
            payload = (await client.get("/api/slate")).json()
        assert "open_positions" in payload
        assert "count" not in (payload["money"] or {})


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
