"""`run_signal_test.py --through-clusters N`: the registered §7(1) cut (#226).

Registration §7(1) ends collection at "G = 1000 independent games scored at
horizon 0.0", counted on the modal `strategy_config_version` (§P4). The cut is
T* = the earliest `clv_scored_ms` at which N distinct modal-version clusters
have been scored; every row scored at or before T* is kept.

What this does not establish: nothing about `build_report`'s statistics (run
unchanged on the cut, and exercised only as a smoke), and nothing about the
live record -- every dump here is synthetic.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "run_signal_test_for_cut", REPO_ROOT / "scripts" / "run_signal_test.py"
)
rst = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rst
_spec.loader.exec_module(rst)

T0 = 1_700_000_000_000


def _row(i: int, cluster: str, scored_ms, version: int = 1) -> dict:
    return {
        "cluster_key": cluster,
        "id": i,
        "ticker": f"T{i}",
        "side": "yes",
        "created_ms": T0 - 10_000 + i,
        "market_type": "moneyline",
        "entry_ask_tenths": 500,
        "edge_tenths": (i * 7) % 40 - 10,
        "clv_tenths": (i * 13) % 50 - 20,
        "suppressed_reason": None,
        "reference_contracts": 5,
        "strategy_config_version": version,
        "clv_scored_ms": scored_ms,
        "yes_bid_tenths": 490,
        "no_bid_tenths": 500,
        "quote_observed_ms": T0 - 20_000,
        "half_spread_tenths": 5.0,
        "unclustered": 0,
    }


def _one_row_per_game(n_games: int) -> list[dict]:
    """Game k is scored at T0 + 1000*k, so T* for N is T0 + 1000*N."""
    return [_row(k, f"G{k}", T0 + 1000 * k) for k in range(1, n_games + 1)]


def _dump(path: Path, rows: list[dict], drop: tuple[str, ...] = ()) -> Path:
    cols = [c for c in rows[0] if c not in drop]
    payload = {
        "query": "clv-signal-pull",
        "sections": [{
            "title": "rows",
            "truncated": False,
            "columns": cols,
            "rows": [[r[c] for c in cols] for r in rows],
        }],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestTheCut:
    def test_the_nth_cluster_sets_t_star(self):
        cut = rst.cut_through_clusters(_one_row_per_game(10), 6)
        assert cut.t_star_ms == T0 + 6000
        assert cut.g_at_t_star == 6
        assert len(cut.rows) == 6
        assert cut.n_after == 4

    def test_a_scoring_batch_sharing_one_ms_is_not_split(self):
        rows = [_row(k, f"G{k}", T0 + 1000 * k) for k in range(1, 5)]
        # G5, G6, G7 are scored in one batch at the same millisecond.
        rows += [_row(10 + k, f"G{k}", T0 + 5000) for k in (5, 6, 7)]
        rows += [_row(20, "G8", T0 + 9000)]
        cut = rst.cut_through_clusters(rows, 5)
        assert cut.t_star_ms == T0 + 5000
        assert cut.g_at_t_star == 7, "the batch carries G past N and is kept whole"
        assert {r["cluster_key"] for r in cut.rows} == {f"G{k}" for k in range(1, 8)}

    def test_a_cluster_is_dated_by_its_earliest_score(self):
        rows = _one_row_per_game(6)
        rows.append(_row(99, "G1", T0 + 500_000))  # late second row of game 1
        cut = rst.cut_through_clusters(rows, 3)
        assert cut.t_star_ms == T0 + 3000
        assert cut.g_at_t_star == 3
        assert all(r["id"] != 99 for r in cut.rows)

    def test_null_clv_scored_ms_is_excluded_and_counted(self):
        rows = _one_row_per_game(5)
        rows += [_row(50, "GX", None), _row(51, "GY", None)]
        cut = rst.cut_through_clusters(rows, 3)
        assert cut.n_null_scored == 2
        assert all(r["clv_scored_ms"] is not None for r in cut.rows)
        assert "GX" not in {r["cluster_key"] for r in cut.rows}

    def test_fewer_than_n_clusters_refuses(self):
        with pytest.raises(rst.RefusedInput, match="not been reached"):
            rst.cut_through_clusters(_one_row_per_game(3), 4)

    def test_non_modal_versions_do_not_count_toward_n(self):
        rows = [_row(1, "G1", T0 + 1000, version=2),
                _row(2, "G2", T0 + 2000, version=2)]
        rows += [_row(10 + k, f"H{k}", T0 + 3000 + 1000 * k) for k in range(1, 6)]
        # Modal is v1 (5 rows vs 2). Its 3rd cluster is scored at T0 + 6000.
        cut = rst.cut_through_clusters(rows, 3)
        assert cut.t_star_ms == T0 + 6000
        assert cut.g_at_t_star == 3
        assert cut.modal_version == 1


class TestRefusals:
    def test_a_modal_version_that_changes_in_the_cut_refuses(self):
        # Full record: v1 has 5 rows, v2 has 4, so v1 is modal. Before T* (the
        # 3rd v1 cluster) v2 dominates, so the cut's modal would be v2.
        rows = [
            _row(1, "A1", T0 + 1000, version=2),
            _row(2, "A2", T0 + 1100, version=2),
            _row(3, "A3", T0 + 1200, version=2),
            _row(8, "A4", T0 + 1300, version=2),
            _row(4, "B1", T0 + 2000, version=1),
            _row(5, "B2", T0 + 3000, version=1),
            _row(6, "B3", T0 + 4000, version=1),
            _row(7, "B4", T0 + 5000, version=1),
            _row(9, "B5", T0 + 6000, version=1),
        ]
        with pytest.raises(rst.RefusedInput, match="differs from the full"):
            rst.cut_through_clusters(rows, 3)

    def test_a_dump_without_clv_scored_ms_refuses(self):
        rows = _one_row_per_game(5)
        for r in rows:
            del r["clv_scored_ms"]
        with pytest.raises(rst.RefusedInput, match="lacks"):
            rst.cut_through_clusters(rows, 3)

    def test_main_exits_nonzero_on_a_dump_without_the_column(self, tmp_path, capsys):
        path = _dump(tmp_path / "old.json", _one_row_per_game(5), drop=("clv_scored_ms",))
        assert rst.main([str(path), "--through-clusters", "3"]) != 0
        assert "clv_scored_ms" in capsys.readouterr().err

    def test_main_exits_nonzero_on_modal_mismatch(self, tmp_path, capsys):
        rows = [
            _row(1, "A1", T0 + 1000, version=2),
            _row(2, "A2", T0 + 1100, version=2),
            _row(3, "A3", T0 + 1200, version=2),
            _row(8, "A4", T0 + 1300, version=2),
            _row(4, "B1", T0 + 2000, version=1),
            _row(5, "B2", T0 + 3000, version=1),
            _row(6, "B3", T0 + 4000, version=1),
            _row(7, "B4", T0 + 5000, version=1),
            _row(9, "B5", T0 + 6000, version=1),
        ]
        path = _dump(tmp_path / "mm.json", rows)
        assert rst.main([str(path), "--through-clusters", "3"]) != 0
        assert "differs from the full" in capsys.readouterr().err


class TestMainPrintout:
    def test_prints_t_star_iso_actual_g_and_modal_equality(self, tmp_path, capsys):
        path = _dump(tmp_path / "ok.json", _one_row_per_game(12))
        rst.main([str(path), "--through-clusters", "8"])
        out = capsys.readouterr().out
        assert "T* " in out and "2023-11-14T22:13:28.000Z" in out  # T0 + 8000
        assert "actual G at T* (modal version; may exceed 8)  8" in out
        assert "(equal: True)" in out
        assert "rows kept / after T* / clv_scored_ms NULL   8 / 4 / 0" in out
        # build_report ran on the cut, not the dump
        assert "rows in dump                 8" in out

    def test_without_the_flag_the_whole_dump_is_analysed(self, tmp_path, capsys):
        path = _dump(tmp_path / "all.json", _one_row_per_game(12))
        rst.main([str(path)])
        out = capsys.readouterr().out
        assert "CUT" not in out
        assert "rows in dump                 12" in out
