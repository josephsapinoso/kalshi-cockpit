"""#432 C and D: Your bets gives each population of combinations a total line
with wins expected at the prices paid and a range, the off-desk view its own
price bands, and beside each total how much of what the winners paid came
from the biggest few.

Every fixture is synthetic (invented prices on made-up tickers); nothing is
copied from the operator's record.

What this establishes
---------------------
- `total` is `expected_block` over the whole population, with staked and net,
  and reconciles to the price bands.
- The off-desk view's bands count off-desk combinations only.
- `top_winners`: the top 1/3/5 shares of the winners' positive net, only where
  that many winners exist, and the net had the top three lost.
- The strip renders the total, the top-winners line and the glossary term.

What it does NOT establish
--------------------------
That any share is large or small in a way that means anything, or that the
page draws (`next build` and a browser say that).
"""

from __future__ import annotations

from pathlib import Path

from backend import bets
from backend.store import db
from tests.test_bets_off_desk_splits import _build, _off_desk, _on_desk, NFL_A, NFL_B

REPO = Path(__file__).resolve().parents[1]
STRIP = REPO / "frontend" / "src" / "components" / "ShapeStrip.tsx"
GLOSSARY = REPO / "frontend" / "src" / "lib" / "glossary.ts"


class TestEachPopulationHasATotal:
    def test_the_total_reconciles_to_the_bands(self, tmp_path):
        shape = bets.bets_record(_build(tmp_path))["by_shape"]
        for view in (shape, shape["off_desk"]):
            total = view["total"]
            assert total["n"] == sum(b["n"] for b in view["price_bands"])
            assert total["won"] == sum(b["won"] for b in view["price_bands"])
            assert total["staked_tenths"] == sum(
                b["staked_tenths"] for b in view["price_bands"]
            ) + view["unbanded"]["staked_tenths"]
            assert {"expected", "too_few", "range_low", "range_high"} <= set(total)

    def test_the_off_desk_bands_are_off_desk_only(self, tmp_path):
        """Mutation observed red: serve the whole record's bands in `off_desk`."""
        shape = bets.bets_record(_build(tmp_path))["by_shape"]
        assert shape["off_desk"]["total"]["n"] < shape["total"]["n"]
        # 6 + 1 + 1 off the desk with legs, plus the one with no legs at all.
        assert shape["off_desk"]["total"]["n"] == 9
        assert sum(b["n"] for b in shape["off_desk"]["price_bands"]) == 9

    def test_the_range_count_includes_the_total(self, tmp_path):
        record = bets.bets_record(_build(tmp_path))
        everything = bets.count_ranges(record)
        without = {**record, "by_shape": {**record["by_shape"], "total": None}}
        assert bets.count_ranges(without) == everything - 1

    def test_the_off_desk_range_count_reads_the_off_desk_total(self, tmp_path):
        record = bets.bets_record(_build(tmp_path))
        shape = record["by_shape"]
        off = bets.count_ranges(record, "off_desk")
        ranged = {**shape["off_desk"]["total"], "range_low": 1, "range_high": 2}
        forced = {**record, "by_shape": {**shape, "off_desk": {**shape["off_desk"], "total": ranged}}}
        had = 1 if shape["off_desk"]["total"]["range_low"] is not None else 0
        assert bets.count_ranges(forced, "off_desk") == off + 1 - had

    def test_an_off_grid_price_stays_out_of_the_expected_line(self, tmp_path):
        """`expected_block` takes 1..999 only; the total's n/won/expected are
        the grid rows', and `unbanded` says how many sat off it."""
        conn = db.init_db(tmp_path / "grid.db")
        _off_desk(conn, price=500, won=True, events=[NFL_A, NFL_B])
        _off_desk(conn, price=1200, won=True, events=[NFL_A, NFL_B])
        off = bets.bets_record(conn)["by_shape"]["off_desk"]
        assert off["unbanded"]["n"] == 1
        assert (off["total"]["n"], off["total"]["won"], off["total"]["expected"]) == (1, 1, 0.5)


class TestTopWinners:
    def test_shares_of_what_the_winners_paid(self):
        # Five winners netting 60, 20, 10, 6, 4 (sum 100), stakes of 10 each
        # and no fee, so each paid out 10 + its net.
        winners = [(10 + n, n) for n in (4, 60, 6, 20, 10)]
        block = bets.top_winners_block(winners, total_net_tenths=-50)
        assert block["winners"] == 5
        assert block["winners_net_tenths"] == 100
        # The top 5 of 5 would only repeat the total, so it is not served.
        assert [(s["top"], s["net_tenths"]) for s in block["shares"]] == [
            (1, 60), (3, 90),
        ]
        # Had the top three lost, each swings by its whole payout:
        # -50 - (60+10) - (20+10) - (10+10) = -170.
        assert block["net_if_top_lost_tenths"] == -170

    def test_the_fee_is_lost_too_when_a_winner_is_taken_out(self):
        """measurement-skeptic, #432: a loser still pays its fee, so taking a
        winner out removes its whole payout, stake + net + fee."""
        block = bets.top_winners_block(
            [(10 + 60 + 2, 60), (5 + 9 + 1, 9), (5 + 7 + 1, 7)], total_net_tenths=0
        )
        assert block["net_if_top_lost_tenths"] == -(72 + 15 + 13)

    def test_the_record_carries_the_fee_into_the_payout(self, tmp_path):
        """Mutation observed red: build the payout as stake + net in
        `leg_views`, leaving the fee out."""
        conn = db.init_db(tmp_path / "fee.db")
        tickers = [_off_desk(conn, price=100, won=True, events=[NFL_A, NFL_B]) for _ in range(3)]
        conn.execute(
            "UPDATE venue_settlements SET fee_cost_tenths = 7 WHERE ticker IN (?, ?, ?)",
            tickers,
        )
        conn.commit()
        top = bets.bets_record(conn)["by_shape"]["off_desk"]["top_winners"]
        total_net = bets.bets_record(conn)["by_shape"]["off_desk"]["total"]["net_tenths"]
        # Three winners at 10c, 2 contracts, fee 7: each paid out 2000 and
        # cost 200 + 7, so all three gone leaves -(207 * 3).
        assert top["net_if_top_lost_tenths"] == total_net - 3 * 2000
        assert top["net_if_top_lost_tenths"] == -3 * 207

    def test_only_shares_that_exist_are_served(self):
        block = bets.top_winners_block([(10, 30), (10, 5)], total_net_tenths=0)
        assert [s["top"] for s in block["shares"]] == [1]
        assert block["net_if_top_lost_tenths"] is None

    def test_no_winners_serves_no_share(self):
        block = bets.top_winners_block([], total_net_tenths=-40)
        assert block == {
            "winners": 0, "winners_net_tenths": 0, "shares": [],
            "removed": 3, "net_if_top_lost_tenths": None,
        }

    def test_a_win_that_netted_nothing_is_not_counted_as_paying(self):
        block = bets.top_winners_block([(10, 0), (10, 50)], total_net_tenths=0)
        assert block["winners"] == 1 and block["winners_net_tenths"] == 50

    def test_the_record_serves_it_on_both_populations(self, tmp_path):
        conn = db.init_db(tmp_path / "tw.db")
        for _ in range(3):
            _off_desk(conn, price=100, won=True, events=[NFL_A, NFL_B])
        _on_desk(conn, price=100, won=True, events=[NFL_A, NFL_B])
        shape = bets.bets_record(conn)["by_shape"]
        assert shape["top_winners"]["winners"] == 4
        assert shape["off_desk"]["top_winners"]["winners"] == 3
        assert shape["off_desk"]["top_winners"]["net_if_top_lost_tenths"] is not None


class TestTheStripShowsThem:
    def test_the_strip_renders_the_total_and_the_top_winners_line(self):
        text = STRIP.read_text(encoding="utf-8")
        assert "view.total" in text
        assert "top_winners" in text
        assert '<Term k="top_winners">' in text
        # The off-desk view reads its own bands when the payload has them.
        assert "view.price_bands" in text

    def test_the_term_is_in_the_glossary(self):
        assert "top_winners:" in GLOSSARY.read_text(encoding="utf-8")
