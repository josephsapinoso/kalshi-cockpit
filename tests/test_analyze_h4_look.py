"""Every exclusion and classification branch of the H4 analyzer, made to fire.

Written after Look 1 recorded (the look's own numbers were verified by the
measurement-skeptic's independent hand re-derivation); these tests exist so
Look 2 does not run on decoration. Payloads are synthetic by necessity —
the real pull is operator account data and never enters the repo.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from analyze_h4_look import GAP_MS, STUDY_START_MS, analyze, clusters_of  # noqa: E402

BASE = STUDY_START_MS + 10 * 86_400_000  # far from the E5 study-start boundary


def _settlement(sid, ms, *, ticker="KXTEST-X", side="yes", result="no",
                contracts=10, fee=70):
    return {"id": sid, "ticker": ticker, "side": side, "contracts": contracts,
            "entry_price_tenths": 500, "fee_cost_tenths": fee,
            "market_result": result, "settled_ms": ms}


def _snapshot(ms, balance):
    return {"observed_ms": ms, "balance_tenths": balance,
            "portfolio_value_tenths": None}


def _payload(settlements, balance, fills=(), polls=None):
    if polls is None:
        polls = [{"polled_ms": b["observed_ms"], "ok": 1, "row_count": 1,
                  "error": None} for b in balance]
    sections = [
        ("A. settlements", settlements,
         ["id", "ticker", "side", "contracts", "entry_price_tenths",
          "fee_cost_tenths", "market_result", "settled_ms"]),
        ("B. balance", balance,
         ["observed_ms", "balance_tenths", "portfolio_value_tenths"]),
        ("C. fills", list(fills),
         ["id", "ticker", "filled_ms", "count", "price_tenths", "is_taker",
          "fee_actual", "source"]),
        ("D. polls", polls, ["polled_ms", "ok", "row_count", "error"]),
    ]
    return {"sections": [
        {"title": t, "columns": cols, "rows": [[r[c] for c in cols] for r in rows],
         "row_count": len(rows)}
        for t, rows, cols in sections
    ]}


def _clean(balance_step=0, **kw):
    """One winning single-settlement cluster with sane endpoints."""
    s = _settlement(1, BASE, side="yes", result="yes", **kw)
    balance = [_snapshot(BASE - 300_000, 10_000),
               _snapshot(BASE + 300_000, 10_000 + balance_step)]
    return [s], balance


class TestClustering:
    def test_gap_over_1800s_cuts_a_cluster(self):
        rows = [_settlement(1, BASE), _settlement(2, BASE + GAP_MS + 1)]
        assert len(clusters_of(rows)) == 2

    def test_gap_at_exactly_1800s_does_not_cut(self):
        rows = [_settlement(1, BASE), _settlement(2, BASE + GAP_MS)]
        assert len(clusters_of(rows)) == 1


class TestExclusionsFire:
    def test_e1_void_result_excludes_the_whole_cluster(self):
        settlements, balance = _clean()
        settlements.append(_settlement(2, BASE + 1000, result=None))
        out = analyze(_payload(settlements, balance))
        assert out["eligible_clusters"] == []
        assert len(out["excluded"]["E1"]) == 1

    def test_e2_a_fill_inside_the_interval_excludes(self):
        settlements, balance = _clean()
        fill = {"id": 9, "ticker": "KXTEST-X", "filled_ms": BASE + 100_000,
                "count": 1, "price_tenths": 500, "is_taker": 1,
                "fee_actual": 7, "source": "poll"}
        out = analyze(_payload(settlements, balance, fills=[fill]))
        assert out["eligible_clusters"] == []
        assert out["excluded"]["E2"][0]["fill_ids"] == [9]

    def test_e3_a_failed_poll_in_the_window_excludes(self):
        settlements, balance = _clean()
        polls = [{"polled_ms": BASE + 60_000, "ok": 0, "row_count": 0,
                  "error": "timeout"}]
        out = analyze(_payload(settlements, balance, polls=polls))
        assert out["eligible_clusters"] == []
        assert len(out["excluded"]["E3"]) == 1

    def test_e4_missing_endpoint_excludes(self):
        settlements, _ = _clean()
        out = analyze(_payload(settlements, [_snapshot(BASE - 300_000, 10_000)]))
        assert out["eligible_clusters"] == []
        assert len(out["excluded"]["E4"]) == 1

    def test_e4_null_balance_on_an_endpoint_excludes(self):
        settlements, balance = _clean()
        balance[1]["balance_tenths"] = None
        out = analyze(_payload(settlements, balance))
        assert out["eligible_clusters"] == []
        assert len(out["excluded"]["E4"]) == 1

    def test_e5_interval_reaching_before_study_start_excludes(self):
        s = _settlement(1, STUDY_START_MS + 60_000, result="yes")
        balance = [_snapshot(STUDY_START_MS - 100_000, 10_000),
                   _snapshot(s["settled_ms"] + 300_000, 10_000)]
        out = analyze(_payload([s], balance))
        assert out["eligible_clusters"] == []
        assert len(out["excluded"]["E5"]) == 1

    def test_e6_balance_still_moving_at_the_edge_excludes(self):
        settlements, balance = _clean()
        balance.append(_snapshot(BASE + 600_000, 12_345))
        out = analyze(_payload(settlements, balance))
        assert out["eligible_clusters"] == []
        assert len(out["excluded"]["E6"]) == 1


class TestClassification:
    def test_flat_balance_with_no_winners_is_no_charge(self):
        s = _settlement(1, BASE, side="yes", result="no")
        balance = [_snapshot(BASE - 300_000, 10_000),
                   _snapshot(BASE + 300_000, 10_000)]
        out = analyze(_payload([s], balance))
        cluster = out["eligible_clusters"][0]
        assert cluster["classification"] == "NO-CHARGE-AT-TOLERANCE"
        assert cluster["r_c_tenths"] == 0

    def test_full_payout_missing_is_banking_contaminated_by_rule_order(self):
        # Look 1's cluster 1: r_c = -P_c, rules 1 and 2 both match, order wins.
        settlements, balance = _clean(balance_step=0)
        out = analyze(_payload(settlements, balance))
        cluster = out["eligible_clusters"][0]
        assert cluster["r_c_tenths"] == -cluster["P_c_tenths"]
        assert cluster["classification"] == "BANKING-CONTAMINATED"

    def test_small_shortfall_is_a_charge(self):
        # 10 winning contracts, payout 10_000 tenths, credited 30 tenths short:
        # below both the banking bar (|r|=30 <= 50*10) and half the payout.
        settlements, balance = _clean(balance_step=10_000 - 30)
        out = analyze(_payload(settlements, balance))
        assert out["eligible_clusters"][0]["classification"] == "CHARGE"

    def test_a_charge_equal_to_the_entry_fee_is_flagged_ambiguous(self):
        settlements, balance = _clean(balance_step=10_000 - 70, fee=70)
        out = analyze(_payload(settlements, balance))
        assert out["eligible_clusters"][0]["classification"] == (
            "CHARGE/AMBIGUOUS-DEFERRED-ENTRY"
        )

    def test_an_unexplained_credit_is_an_anomaly_not_a_vote(self):
        settlements, balance = _clean(balance_step=10_000 + 30)
        out = analyze(_payload(settlements, balance))
        assert out["eligible_clusters"][0]["classification"] == "ANOMALY"

    def test_most_of_the_payout_missing_is_credit_channel(self):
        # Rule 2 is reachable only when losers dilute N: an all-winner cluster
        # has 0.5*P = 500*N, always past the 50*N banking bar. Here 5 winners
        # (P = 5_000) ride with a 195-contract loser (N = 200, banking bar
        # 10_000); r = -3_000 clears rule 1 and fires rule 2.
        winner = _settlement(1, BASE, side="yes", result="yes", contracts=5)
        loser = _settlement(2, BASE + 1000, side="yes", result="no",
                            contracts=195)
        balance = [_snapshot(BASE - 300_000, 10_000),
                   _snapshot(BASE + 1000 + 300_000, 10_000 + 2_000)]
        out = analyze(_payload([winner, loser], balance))
        assert out["eligible_clusters"][0]["classification"] == (
            "UNDECIDABLE-CREDIT-CHANNEL"
        )
