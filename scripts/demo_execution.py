"""Demonstrate the execution path: the gate, its refusals, and a dry run.

Run:  python -m scripts.demo_execution

Deterministic and offline. Builds throwaway databases in a temp directory, so
nothing here touches the real store, Kalshi, or money.
"""

from __future__ import annotations

import sqlite3
import tempfile
import time
from pathlib import Path

from backend.config import GateConfig, StalenessConfig
from backend.gate import evaluate_gate, recommendation_freshness
from backend.kalshi.orders import (
    OrderPlacer,
    OrderRefused,
    OrderRequest,
    api_price_cents,
)
from backend.store import db

DAY_MS = 86_400_000
ARMED = GateConfig(live_trading_enabled=True, min_scored_recommendations=300)


def rule(title: str) -> None:
    print(f"\n{'=' * 76}\n{title}\n{'=' * 76}")


# Every connection opened, so they can all be closed before the temp directory
# is removed. Windows refuses to unlink a file that still has an open handle.
_OPENED: list[sqlite3.Connection] = []


def fresh_db(root: Path, name: str) -> sqlite3.Connection:
    path = root / f"{name}.db"
    db.init_db(path).close()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, series_ticker) "
        "VALUES ('KXNFLGAME-26AUG27KCBAL-KC', 'E', 'S')"
    )
    _OPENED.append(conn)
    return conn


def add(conn, *, clv_tenths, quote_age=1_000, odds_age=60_000, created_ms=None):
    conn.execute(
        """
        INSERT INTO recommendations (
            created_ms, ticker, strategy_config_version, side, entry_ask_tenths,
            fair_probability, edge_tenths, fee_predicted, ev_net_dollars,
            suggested_contracts, kelly_fraction, kalshi_quote_age_ms,
            odds_age_ms, suppressed_reason, reason_text, clv_tenths, clv_scored_ms
        ) VALUES (?, 'KXNFLGAME-26AUG27KCBAL-KC', 1, 'yes', 503, 0.55, 20.0, 0.1,
                  0.5, 20, 0.02, ?, ?, NULL, 'demo', ?, ?)
        """,
        (
            created_ms or int(time.time() * 1000), quote_age, odds_age,
            clv_tenths, int(time.time() * 1000),
        ),
    )
    return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


def show(decision) -> None:
    print(f"  GATE: {'OPEN' if decision.open else 'LOCKED'}")
    for condition in decision.conditions:
        mark = "PASS" if condition.met else "FAIL"
        print(f"    [{mark}] {condition.name}")
        print(f"           {condition.detail}")


def main(root: Path) -> None:
    rule("1. An empty record. Locked on every evidence condition.")
    conn = fresh_db(root, "empty")
    show(evaluate_gate(conn, ARMED))
    print("\n  Note the fee condition. No fills is NOT a pass -- with no ground")
    print("  truth the fee model is an untested hedge between two sources that")
    print("  disagree, and calling that 'verified' is the convenient reading of")
    print("  an absence.")

    rule("2. 400 scored bets, positive mean CLV -- and still locked.")
    conn = fresh_db(root, "noisy")
    for i in range(400):
        add(conn, clv_tenths=(50.0 if i % 2 else -48.0))
    conn.commit()
    show(evaluate_gate(conn, ARMED))
    print("\n  This is the case a naive gate waves through. The sample size is")
    print("  satisfied and the mean is positive -- and the effect sits inside")
    print("  two standard errors of zero, so it is not evidence of anything.")

    rule("3. The same 400 bets with a consistent edge.")
    conn = fresh_db(root, "real")
    for i in range(400):
        add(conn, clv_tenths=20.0 + (1.0 if i % 2 else -1.0))
    conn.commit()
    show(evaluate_gate(conn, ARMED))
    print("\n  Evidence conditions clear. Fees still block it, and they should:")
    print("  no fill has ever tested the fee model.")

    rule("4. Freshness is recomputed, not read off the row.")
    conn = fresh_db(root, "stale")
    recent = add(conn, clv_tenths=10.0, quote_age=3_000)
    old = add(
        conn, clv_tenths=10.0, quote_age=3_000,
        created_ms=int(time.time() * 1000) - DAY_MS,
    )
    conn.commit()
    for label, rid in (("made just now", recent), ("made a day ago", old)):
        state = recommendation_freshness(conn, rid)
        print(
            f"  {label:<16} stored quote age 3.0s -> actual "
            f"{state['kalshi_quote_age_ms'] / 1000:>9,.0f}s"
        )
    print("\n  Both rows store 'quote was 3 seconds old'. Reading that column")
    print("  straight out would let the day-old one pass a 30-second limit")
    print("  forever. The observation instant is reconstructed instead.")

    decision = evaluate_gate(
        conn, ARMED,
        staleness=StalenessConfig(max_kalshi_quote_age_s=30, max_odds_age_s=900),
        kalshi_quote_age_ms=recommendation_freshness(conn, old)["kalshi_quote_age_ms"],
        odds_age_ms=60_000,
    )
    fresh = next(c for c in decision.conditions if c.name == "data_fresh")
    print(f"\n  [{'PASS' if fresh.met else 'FAIL'}] data_fresh -- {fresh.detail}")

    rule("5. Price rounding: away from paying more, and refuse off-grid.")
    for tenths, action in ((509, "buy"), (501, "sell"), (500, "buy")):
        print(f"  {tenths} tenths, {action:<4} -> {api_price_cents(tenths, action)}c")
    for tenths, action in ((9, "buy"), (999, "sell")):
        try:
            api_price_cents(tenths, action)
        except OrderRefused as exc:
            print(f"\n  {tenths} tenths, {action} -> OrderRefused")
            print(f"    {exc}")

    rule("6. A dry run. The body is exactly what would be sent.")
    order = OrderRequest(
        ticker="KXNFLGAME-26AUG27KCBAL-KC", side="yes", action="buy",
        count=20, limit_price_tenths=509, recommendation_id=recent,
    )
    import asyncio

    outcome = asyncio.run(OrderPlacer().place(order))

    print(f"  status                {outcome.status}")
    print(f"  limit price sent      {order.api_price}c  (from 50.9c, rounded down)")
    print(f"  worst-case cost       ${order.worst_case_cost_dollars:.2f}")
    print(f"  client_order_id       {order.client_order_id}")
    print(f"\n  body: {outcome.request_body_json}")
    print("\n  The client_order_id is generated before the request, so a")
    print("  timeout-then-retry cannot double-fill: Kalshi recognises the")
    print("  repeat and returns the original order. A live order takes this")
    print("  same path and builds this same body -- dry run is not a parallel")
    print("  implementation that can drift.")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        try:
            main(Path(tmp))
        finally:
            for connection in _OPENED:
                connection.close()
    print()
