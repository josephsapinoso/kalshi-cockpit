"""#397: Your bets shows where the money went -- staked and net by price band
and by exact leg count, combinations only, descriptive, in a fixed order.

Every fixture is synthetic (round invented prices on made-up tickers); nothing
is, or may be, copied from the operator's record.

What this establishes
---------------------
- The bands' staked sum to `by_shape.staked_tenths` and their net sum to
  `sections.combo.net_tenths` (staked uses the cost term of
  `settlement_net_tenths`, over the same rows).
- Leg-count rows ascend by exact count and `ShapeStrip.tsx` never sorts.
- A too_few cell carries n, won, staked and net and no range; the strip
  prints no rate.
- Combinations with no leg list are their own counted row, never dropped.
- `EXPECTED_BUCKETS` is unchanged; no key says roi or return.

What it does NOT establish
--------------------------
That the page draws (`next build` and a browser say that), that the live
record has legs recorded for any particular combination, or that any band or
leg count means anything: this block is counts and sums, not a finding.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend import bets, hedge
from backend.store import db

REPO = Path(__file__).resolve().parents[1]
STRIP = REPO / "frontend" / "src" / "components" / "ShapeStrip.tsx"
PAGE = REPO / "frontend" / "src" / "app" / "bets" / "page.tsx"

_N = [0]


def _combo(conn, *, price, won, legs, contracts=2.0, fee=0, record=True):
    """One settled combination; `legs` positions-legs recorded when > 0."""
    _N[0] += 1
    n = _N[0]
    ticker = f"KXMVESYNTHETIC-SHARD1-S{n:016d}-AAAAAAAAAAA"
    conn.execute(
        "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
        "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths, "
        "position_first_seen_ms) VALUES (?, 'KXSYNTH', ?, ?, 'yes', ?, ?, ?, NULL)",
        (ticker, "yes" if won else "no", 1_000 + n, contracts, price, fee),
    )
    if legs > 0 and record:
        hedge.record_position(
            conn, now_ms=1_000 + n, source="kalshi_combo", label="synthetic",
            stake_tenths=1000, return_tenths=5000, combo_ticker=ticker,
            legs=[
                {"ticker": f"KXSYNTHLEG{n}-{i}", "event_ticker": f"KXSYNTHEV{n}",
                 "side": "yes", "label": f"leg {i}", "league": "Pro Baseball"}
                for i in range(legs)
            ],
        )
    conn.commit()
    return ticker


def _single(conn, *, price, won):
    _N[0] += 1
    n = _N[0]
    conn.execute(
        "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
        "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths, "
        "position_first_seen_ms) VALUES (?, 'KXSYNTH', ?, ?, 'yes', 1.0, ?, 0, NULL)",
        (f"KXSYNTHGAME-26JAN010000AAABBB-{n}", "yes" if won else "no",
         1_000 + n, price),
    )
    conn.commit()


def _record(tmp_path):
    conn = db.init_db(tmp_path / "shape.db")
    # under 10c: 2 legs lost, 4 legs lost
    _combo(conn, price=50, won=False, legs=2)
    _combo(conn, price=80, won=False, legs=4)
    # 10c to 25c: 3 legs won, 3 legs lost
    _combo(conn, price=200, won=True, legs=3, contracts=3.0, fee=7)
    _combo(conn, price=150, won=False, legs=3)
    # 25c to 50c: 2 legs won
    _combo(conn, price=400, won=True, legs=2)
    # 50c and up: no leg list, lost
    _combo(conn, price=600, won=False, legs=0)
    # no leg list again, won
    _combo(conn, price=300, won=True, legs=0)
    # a single must stay out
    _single(conn, price=500, won=True)
    return conn, bets.bets_record(conn)


class TestBandsReconcile:
    def test_staked_and_net_reconcile_to_the_parents(self, tmp_path):
        _conn, rec = _record(tmp_path)
        shape = rec["by_shape"]
        assert [b["label"] for b in shape["price_bands"]] == [
            label for _l, _h, label in bets.EXPECTED_BUCKETS
        ]
        band_staked = 0
        band_net = 0
        for b in shape["price_bands"]:
            band_staked += b["staked_tenths"]
            band_net += b["net_tenths"]
        assert band_staked + shape["unbanded"]["staked_tenths"] == shape["staked_tenths"]
        assert band_net + shape["unbanded"]["net_tenths"] == shape["net_tenths"]
        assert band_net == rec["sections"]["combo"]["net_tenths"]
        # Hand arithmetic: contracts x price, summed over combos only.
        # 2*50 + 2*80 + 3*200 + 2*150 + 2*400 + 2*600 + 2*300
        assert shape["staked_tenths"] == 100 + 160 + 600 + 300 + 800 + 1200 + 600
        assert shape["price_bands"][1]["staked_tenths"] == 600 + 300
        # The single is not in it.
        assert sum(b["n"] for b in shape["price_bands"]) == 7

    def test_an_uncomputable_combo_is_counted_not_summed_as_zero(self, tmp_path):
        conn = db.init_db(tmp_path / "u.db")
        _combo(conn, price=200, won=True, legs=2)
        _N[0] += 1
        conn.execute(
            "INSERT INTO venue_settlements (ticker, event_ticker, market_result, "
            "settled_ms, side, contracts, entry_price_tenths, fee_cost_tenths, "
            "position_first_seen_ms) VALUES (?, 'KXSYNTH', 'void', 5, 'yes', 1.0, "
            "300, 0, NULL)",
            (f"KXMVESYNTHETIC-SHARD1-S{_N[0]:016d}-AAAAAAAAAAA",),
        )
        conn.commit()
        shape = bets.bets_record(conn)["by_shape"]
        assert shape["uncomputable"] == 1
        assert shape["staked_tenths"] == 400


class TestLegCountsAscend:
    def test_exact_counts_ascending_with_no_bins(self, tmp_path):
        _conn, rec = _record(tmp_path)
        rows = rec["by_shape"]["leg_counts"]
        assert [r["legs"] for r in rows] == [2, 3, 4]
        by = {r["legs"]: r for r in rows}
        assert (by[2]["n"], by[2]["won"]) == (2, 1)
        assert (by[3]["n"], by[3]["won"]) == (2, 1)
        assert (by[4]["n"], by[4]["won"]) == (1, 0)

    def test_order_does_not_follow_results(self, tmp_path):
        conn = db.init_db(tmp_path / "o.db")
        # The 5-leg rows are the big winners; they must still come last.
        for _ in range(2):
            _combo(conn, price=100, won=True, legs=5, contracts=10.0)
        _combo(conn, price=100, won=False, legs=2)
        _combo(conn, price=100, won=False, legs=3)
        rows = bets.bets_record(conn)["by_shape"]["leg_counts"]
        assert [r["legs"] for r in rows] == [2, 3, 5]

    def test_the_strip_never_sorts(self):
        src = STRIP.read_text(encoding="utf-8")
        assert ".sort(" not in src
        assert ".toSorted(" not in src


class TestTooFewCells:
    def test_a_small_cell_has_counts_and_money_but_no_range(self, tmp_path):
        _conn, rec = _record(tmp_path)
        for cell in rec["by_shape"]["price_bands"] + rec["by_shape"]["leg_counts"]:
            assert cell["too_few"] is True
            assert cell["range_low"] is None and cell["range_high"] is None
            for key in ("n", "won", "staked_tenths", "net_tenths"):
                assert isinstance(cell[key], int)

    def test_the_strip_prints_no_range_or_rate_for_a_too_few_cell(self):
        src = STRIP.read_text(encoding="utf-8")
        # The range is only ever printed in the not-too_few branch.
        m = re.search(r"const expected = cell\.too_few\s*\?\s*\"([^\"]*)\"\s*:\s*`([^`]*)`", src)
        assert m, "too_few branch not found"
        assert "range" not in m.group(1) and "%" not in m.group(1)
        assert "range" in m.group(2)
        assert "too few to judge" in m.group(1)
        assert "%" not in src


class TestNoLegList:
    def test_combos_without_legs_are_their_own_row_and_counted(self, tmp_path):
        _conn, rec = _record(tmp_path)
        shape = rec["by_shape"]
        assert shape["no_leg_list"] == {
            "n": 2, "staked_tenths": 1200 + 600, "net_tenths": (-1200) + (
                2 * 1000 - 600
            ),
        }
        in_legs = 0
        for r in shape["leg_counts"]:
            in_legs += r["n"]
        # Nothing dropped: with a list plus without one is every combo.
        assert in_legs + shape["no_leg_list"]["n"] == rec["sections"]["combo"]["total"]

    def test_the_strip_prints_the_no_leg_list_row(self):
        src = STRIP.read_text(encoding="utf-8")
        assert "no leg list" in src and "data.no_leg_list.n" in src


class TestShapeOfTheBlock:
    def test_expected_buckets_unchanged(self):
        assert bets.EXPECTED_BUCKETS == (
            (1, 100, "under 10c"),
            (100, 250, "10c to 25c"),
            (250, 500, "25c to 50c"),
            (500, 1000, "50c and up"),
        )

    def test_no_key_says_roi_or_return_and_summary_is_untouched(self, tmp_path):
        _conn, rec = _record(tmp_path)

        def keys(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    yield k
                    yield from keys(v)
            elif isinstance(o, list):
                for v in o:
                    yield from keys(v)

        for k in keys(rec["by_shape"]):
            assert "roi" not in k and "return" not in k
        for k in keys(rec["summary"]):
            assert "net" not in k

    def test_page_mounts_the_strip_once(self):
        page = PAGE.read_text(encoding="utf-8")
        assert page.count("<ShapeStrip") == 1

    def test_strip_words(self):
        src = STRIP.read_text(encoding="utf-8").lower()
        for banned in ("unlucky", " due", "roi", "return on", "edge"):
            assert banned not in src
