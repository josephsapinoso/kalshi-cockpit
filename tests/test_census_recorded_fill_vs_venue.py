"""The registered census harness prints what the registration permits and
nothing else, classifies rows by the rules fixed before the look, and
refuses on coverage.

`docs/measurements/2026-09-10-preregistration-recorded-fill-vs-venue-charge.md`
+ Amendment 1. Every rule below is quoted from there; none was chosen after
a number was seen (the live look had not been taken when these were
written). Mutations observed red: `n_sent_below` counting a
`side_convention_ambiguous` row; the fallback row entering `n_equal`; the
refusal branch never firing; `venue_avg_fee_dollars` added to the SELECT.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

from backend.store import db

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "census_recorded_fill_vs_venue.py"


def _load():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("census_harness", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


census = _load()


def _order(conn, *, oid, submitted_ms, ticker, side="yes", count=5, sent=450,
           dry_run=0, fill_count=None, avg_price=None, fee=None):
    conn.execute(
        "INSERT INTO manual_orders (client_order_id, kalshi_order_id, submitted_ms, "
        "ticker, side, action, count, limit_price_tenths, max_price_tenths, status, "
        "request_body_json, dry_run, venue_fill_count, venue_avg_fill_price_tenths, "
        "venue_avg_fee_dollars) VALUES (?, ?, ?, ?, ?, 'buy', ?, ?, ?, 'filled', "
        "'{}', ?, ?, ?, ?)",
        (f"c-{oid}", oid, submitted_ms, ticker, side, count, sent, sent, dry_run,
         fill_count, avg_price, fee),
    )


def _fill(conn, *, fill_id, order_id, ticker, count, price):
    conn.execute(
        "INSERT INTO fills (kalshi_fill_id, ticker, filled_ms, count, price_tenths, "
        "is_taker, fee_predicted, fee_model_used, venue_order_id, source) "
        "VALUES (?, ?, 1, ?, ?, 1, 0.0, 'test', ?, 'venue_hand')",
        (fill_id, ticker, count, price, order_id),
    )


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "census.db")
    yield c
    c.close()


def _seed(conn):
    """Seven rows, one of each shape the registration names."""
    # 1. fills-joined, single fill, equal.
    _order(conn, oid="o1", submitted_ms=1000, ticker="KXMVE-A", sent=450)
    _fill(conn, fill_id="f1", order_id="o1", ticker="KXMVE-A", count=5, price=450)
    # 2. fills-joined, two fills: count-weighted mean 455 against sent 450, diff -5.
    _order(conn, oid="o2", submitted_ms=2000, ticker="KXMLBGAME-B", sent=450)
    _fill(conn, fill_id="f2a", order_id="o2", ticker="KXMLBGAME-B", count=1, price=440)
    _fill(conn, fill_id="f2b", order_id="o2", ticker="KXMLBGAME-B", count=3, price=460)
    # 3. create-response fallback only: sent 300, venue 300 (equal, but fallback never enters H1).
    _order(conn, oid="o3", submitted_ms=3000, ticker="KXMVE-C", sent=300,
           fill_count=5.0, avg_price=300, fee=0.01)
    # 4. zero fill: the IOC matched no one.
    _order(conn, oid="o4", submitted_ms=4000, ticker="KXMVE-D", sent=300, fill_count=0.0)
    # 5. unknown: pre-v40 row, nothing joined.
    _order(conn, oid="o5", submitted_ms=5000, ticker="KXMVE-E", sent=300)
    # 6. side-convention artifact: sent 300 on NO, fills say 700.
    _order(conn, oid="o6", submitted_ms=6000, ticker="KXMLBGAME-F", side="no", sent=300)
    _fill(conn, fill_id="f6", order_id="o6", ticker="KXMLBGAME-F", count=5, price=700)
    # 7. both endpoints, disagreeing by 2 tenths.
    _order(conn, oid="o7", submitted_ms=7000, ticker="KXMVE-G", sent=400,
           fill_count=5.0, avg_price=402)
    _fill(conn, fill_id="f7", order_id="o7", ticker="KXMVE-G", count=5, price=400)
    # X1: a dry run is not in the population.
    _order(conn, oid="dry", submitted_ms=8000, ticker="KXMVE-H", sent=400, dry_run=1)
    conn.commit()


class TestThePopulationAndTheOrder:
    def test_dry_runs_are_out_and_rows_come_back_by_submitted_ms(self, conn):
        _seed(conn)
        rows = census.read_rows(conn)
        assert [r["submitted_ms"] for r in rows] == [1000, 2000, 3000, 4000, 5000, 6000, 7000]
        assert all(r["ticker"] != "KXMVE-H" for r in rows)

    def test_the_stratum_is_the_ticker_prefix(self):
        assert census.stratum("KXMVECROSSCATEGORY-SHARD1-X") == "S1"
        assert census.stratum("KXMLBGAME-26SEP15-X") == "S2"


class TestVIsChosenByTheRegisteredPrecedence:
    def test_fills_is_primary_and_the_mean_is_count_weighted(self, conn):
        _seed(conn)
        by = {r["submitted_ms"]: r for r in census.read_rows(conn)}
        assert by[2000]["venue_source"] == "fills"
        assert by[2000]["venue_tenths"] == 455.0  # (1*440 + 3*460) / 4
        assert by[2000]["sent_minus_venue_tenths"] == -5.0
        assert by[2000]["multi_fill"] == 1

    def test_the_create_response_is_only_a_fallback(self, conn):
        _seed(conn)
        by = {r["submitted_ms"]: r for r in census.read_rows(conn)}
        assert by[3000]["venue_source"] == "create_response"
        assert by[3000]["venue_tenths"] == 300.0
        assert by[7000]["venue_source"] == "fills", "fills wins when both exist"

    def test_zero_fill_and_unknown_are_told_apart(self, conn):
        _seed(conn)
        by = {r["submitted_ms"]: r for r in census.read_rows(conn)}
        assert by[4000]["venue_source"] == "zero_fill"
        assert by[5000]["venue_source"] == "unknown"
        assert by[4000]["venue_tenths"] is None and by[5000]["venue_tenths"] is None

    def test_the_two_endpoints_are_compared_at_one_tenth(self, conn):
        _seed(conn)
        by = {r["submitted_ms"]: r for r in census.read_rows(conn)}
        assert by[7000]["fills_venue_tenths"] == 400.0
        assert by[7000]["create_venue_tenths"] == 402
        assert by[7000]["endpoints_disagree"] == 1
        assert by[1000]["endpoints_disagree"] is None, "one source is not a disagreement"

    def test_exactly_one_tenth_apart_is_not_a_disagreement(self, conn):
        """A7.4: 'a disagreement of 1 tenth or less ... opens nothing'. At
        exactly 1 a `>=` slip would flag it; this is the anchor."""
        _order(conn, oid="o8", submitted_ms=9000, ticker="KXMVE-I", sent=400,
               fill_count=5.0, avg_price=401)
        _fill(conn, fill_id="f8", order_id="o8", ticker="KXMVE-I", count=5, price=400)
        conn.commit()
        by = {r["submitted_ms"]: r for r in census.read_rows(conn)}
        assert by[9000]["endpoints_disagree"] == 0


class TestTheSideConventionRuleIsTheRegisteredOne:
    def test_a_flipped_row_is_ambiguous_not_falsified(self):
        assert census.classify(300, 700) == "side_convention_ambiguous"

    def test_near_fifty_cents_is_undecidable(self):
        assert census.classify(500, 505) == "side_convention_undecidable"

    def test_everything_else_is_comparable(self):
        assert census.classify(450, 455) == "comparable"
        assert census.classify(300, 350) == "comparable"

    def test_the_tolerance_is_inclusive_at_exactly_ten_tenths(self):
        """A4.3 fixes `<= 10`. At exactly 10 the candidate errors (`<`)
        give a different answer, so this is the anchor."""
        assert census.classify(300, 710) == "side_convention_ambiguous"
        assert census.classify(300, 711) == "comparable"


class TestTheCountsAdmitOnlyWhatTheRegistrationAdmits:
    def test_h1_counts_are_fills_sourced_comparable_rows_only(self, conn):
        _seed(conn)
        rows = census.read_rows(conn)
        pooled = dict(zip(census.COUNT_COLUMNS, census.counts_for(rows, "pooled", 0)))
        assert pooled["n_rows"] == 7
        assert pooled["n_joined"] == 5  # o1 o2 o3 o6 o7
        assert pooled["unjoined_zero_fill"] == 1
        assert pooled["unjoined_unknown"] == 1
        assert pooled["n_source_fills"] == 4
        assert pooled["n_source_create_response"] == 1
        assert pooled["n_side_convention_ambiguous"] == 1
        # o1, o2, o7 are comparable and fills-sourced; o3 is fallback and
        # o6 is the artifact -- neither may reach an H1 count.
        assert pooled["n_comparable"] == 3
        assert pooled["n_equal"] == 2
        assert pooled["n_sent_above"] == 0
        assert pooled["n_sent_below"] == 1
        assert pooled["max_abs_sent_minus_venue_tenths"] == 5.0
        assert pooled["sum_abs_sent_minus_venue_tenths"] == 5.0
        assert pooled["n_both_endpoints"] == 1
        assert pooled["n_endpoints_disagree"] == 1

    def test_no_mean_and_no_rate_is_ever_a_column(self):
        for name in census.COUNT_COLUMNS + census.ROW_COLUMNS:
            assert "mean" not in name and "rate" not in name and "avg" not in name.replace(
                "create_venue", ""
            ), name


class TestTheRefusalBranch:
    def test_it_fires_when_unknown_exceeds_joined_and_prints_no_comparison(self, conn):
        _order(conn, oid="j", submitted_ms=1000, ticker="KXMVE-J", sent=450)
        _fill(conn, fill_id="fj", order_id="j", ticker="KXMVE-J", count=1, price=450)
        _order(conn, oid="u1", submitted_ms=2000, ticker="KXMVE-U1", sent=450)
        _order(conn, oid="u2", submitted_ms=3000, ticker="KXMVE-U2", sent=450)
        conn.commit()
        rows = census.read_rows(conn)
        assert census.refusal_fires(rows)
        secs = census.sections(rows, 0)
        titles = [s.title for s in secs]
        assert any("REFUSAL BRANCH" in t for t in titles)
        assert not any(t.startswith("D.") for t in titles), "no per-row comparison"
        c = next(s for s in secs if s.title.startswith("C."))
        assert "n_equal" not in c.columns and "n_sent_below" not in c.columns

    def test_it_does_not_fire_when_joined_covers(self, conn):
        _seed(conn)
        rows = census.read_rows(conn)
        assert not census.refusal_fires(rows)
        assert any(s.title.startswith("D.") for s in census.sections(rows, 0))


class TestTheForbiddenColumnsAreNotRead:
    FORBIDDEN = (
        "p_yes_bp", "venue_avg_fee_dollars", "venue_settlements", "settlements",
        "closing_lines", "clv_", "pnl", "realised", "bet_estimates",
    )

    @pytest.mark.parametrize("word", FORBIDDEN)
    def test_neither_statement_names_it(self, word):
        for sql in (census.SQL_POPULATION, census.SQL_FILLS_FOR):
            assert word not in sql, (word, sql)

    def test_the_fills_read_is_bounded_to_the_population(self):
        assert "WHERE venue_order_id IN ({placeholders})" in census.SQL_FILLS_FOR

    def test_the_row_table_is_ordered_by_submitted_ms_and_nothing_else(self):
        assert census.SQL_POPULATION.endswith("ORDER BY submitted_ms ASC, id ASC")


class TestTheScriptRunsEndToEnd:
    def test_it_prints_every_section_and_writes_nothing(self, tmp_path):
        import subprocess

        path = tmp_path / "e2e.db"
        c = db.init_db(path)
        _seed(c)
        before = c.execute("SELECT COUNT(*) FROM manual_orders").fetchone()[0]
        c.close()
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "--db", str(path)],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert r.returncode == 0, r.stderr
        for head in ("A. the population", "B. orders per ticker", "C. counts", "D. every row"):
            assert head in r.stdout, r.stdout
        assert "trigger_met_at_10" in r.stdout
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        assert c.execute("SELECT COUNT(*) FROM manual_orders").fetchone()[0] == before
        c.close()
