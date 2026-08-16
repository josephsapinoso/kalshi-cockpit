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

from backend.analysis.clv import DEFAULT_HORIZON_HOURS
from backend.config import GateConfig, StalenessConfig
from backend.gate import evaluate_gate, recommendation_freshness
from backend.kalshi.grid import parse_price_grid
from backend.kalshi.orders import (
    OrderPlacer,
    OrderRefused,
    OrderRequest,
)
from backend.store import db

DAY_MS = 86_400_000
ARMED = GateConfig(live_trading_enabled=True, min_scored_recommendations=300)

# The one market every scenario that is not about the CLV floor uses.
DEMO_TICKER = "KXNFLGAME-26AUG27KCBAL-KC"

# The grid every live game market carried on 2026-08-08 (1,426 of 1,426).
WHOLE_CENT = parse_price_grid(
    [{"start": "0.0000", "end": "1.0000", "step": "0.0100"}],
    structure="linear_cent",
)
# Kalshi's published half-cent structure. Shown beside the whole-cent one
# because the difference between them is the whole point of this section.
HALF_CENT = parse_price_grid(
    [{"start": "0.0000", "end": "1.0000", "step": "0.0050"}],
    structure="center_half_edge_half_cent",
)


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
    _market(conn, DEMO_TICKER, "E")
    _OPENED.append(conn)
    return conn


def _market(conn, ticker: str, event_ticker: str) -> int:
    """Register one market, loudly.

    Plain `INSERT`, and `first_seen_ms`/`last_seen_ms` supplied. This was
    `INSERT OR IGNORE` without them, and both columns are `NOT NULL`: SQLite
    ignored the constraint failure exactly as it ignores a duplicate key, so
    **`kalshi_markets` was empty for the whole script** and every recommendation
    pointed at a market that did not exist. Nothing complained -- the raw
    `sqlite3.connect` here does not enable `PRAGMA foreign_keys` -- and the only
    visible symptom was the gate's own footnote, "400 row(s) had no event ticker
    and were clustered by market instead". `tasks/lessons.md` carries this under
    `INSERT OR IGNORE will happily ignore your fixture`.

    **It also mints the `event_links` row and returns its id**, because since
    2026-08-16 the gate clusters on `event_links.odds_event_id` rather than on
    `kalshi_markets.event_ticker` (ADR 0029). Without the link every demo row
    lands on the fallback and that same footnote returns -- in a script whose
    whole purpose is to show the gate behaving as it does in production. One
    sportsbook fixture per demo game, which is what the demo means by a game.
    """
    now = int(time.time() * 1000)
    conn.execute(
        "INSERT INTO kalshi_markets (ticker, event_ticker, series_ticker, "
        "first_seen_ms, last_seen_ms) VALUES (?, ?, 'S', ?, ?)",
        (ticker, event_ticker, now, now),
    )
    conn.execute(
        "INSERT INTO event_links (kalshi_event_ticker, odds_event_id, league, "
        "method, commence_skew_ms, linked_ms) VALUES (?, ?, 'demo', 'demo', 0, ?)",
        (event_ticker, f"ODDS-{event_ticker}", now),
    )
    return int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])


def add(
    conn, *, clv_tenths, quote_age=1_000, odds_age=60_000, created_ms=None,
    game=None,
):
    """One scored recommendation, visible to the gate.

    Two columns here are not decoration and the script printed the opposite of
    its own narration without them:

    `clv_horizon_hours` — `gate.clustered_clv` filters `AND r.clv_horizon_hours
    = :horizon` bound to `DEFAULT_HORIZON_HOURS` (ADR 0011), and `NULL = 0.0` is
    NULL in SQL, not false. Omitting it dropped **every** row, so scenarios 2 and
    3 rendered identically to scenario 1's empty database while the prose beneath
    claimed "the sample size is satisfied". `backend/seed_demo.py` carries a
    comment warning about exactly this; it had been applied to `seed_history` and
    not here.

    `game` — the floor counts **independent games**, clustered since 2026-08-16
    on `event_links.odds_event_id` (ADR 0029; it was `kalshi_markets.event_ticker`,
    which is one per *series* per game, not one per game). Four hundred rows on
    one ticker is one cluster, so even with the horizon written the counter would
    have read "1 of 300". Each game gets its own market, event **and sportsbook
    fixture**, so 400 rows are 400 data points — which is what "400 scored bets"
    in the section title claims.

    `link_id` is resolved by subquery from the ticker rather than threaded in,
    so a demo row cannot end up unlinked by a caller forgetting to pass it. An
    unlinked row would still be *counted*, on the fallback key, which is exactly
    the kind of silent degradation this script exists to make visible.
    """
    ticker = DEMO_TICKER if game is None else f"KXNFLGAME-26AUG{game:04d}-A"
    if game is not None:
        _market(conn, ticker, f"E{game:04d}")
    conn.execute(
        """
        INSERT INTO recommendations (
            created_ms, ticker, strategy_config_version, side, entry_ask_tenths,
            fair_probability, edge_tenths, fee_predicted, ev_net_dollars,
            suggested_contracts, reference_contracts, kelly_fraction,
            kalshi_quote_age_ms,
            odds_age_ms, suppressed_reason, reason_text, clv_tenths,
            clv_scored_ms, clv_horizon_hours, link_id
        ) VALUES (?, ?, 1, 'yes', 503, 0.55, 20.0, 0.1,
                  0.5, 20, 20, 0.02, ?, ?, NULL, 'demo', ?, ?, ?,
                  (SELECT l.id FROM event_links l
                     JOIN kalshi_markets m
                       ON m.event_ticker = l.kalshi_event_ticker
                    WHERE m.ticker = ?))
        """,
        (
            created_ms or int(time.time() * 1000), ticker, quote_age, odds_age,
            clv_tenths, int(time.time() * 1000), DEFAULT_HORIZON_HOURS, ticker,
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
        add(conn, clv_tenths=(50.0 if i % 2 else -48.0), game=i)
    conn.commit()
    show(evaluate_gate(conn, ARMED))
    print("\n  This is the case a naive gate waves through. The sample size is")
    print("  satisfied and the mean is positive -- and the effect sits inside")
    print("  two standard errors of zero, so it is not evidence of anything.")

    rule("3. The same 400 bets with a consistent edge.")
    conn = fresh_db(root, "real")
    for i in range(400):
        add(conn, clv_tenths=20.0 + (1.0 if i % 2 else -1.0), game=i)
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

    rule("5. Prices snap to the MARKET'S grid, away from paying more.")
    print("  Kalshi publishes `price_ranges` per market and rejects anything")
    print("  off it. Whole cents are legal on every structure -- which is why")
    print("  flooring to a cent was never rejected, and simply never filled.\n")
    for grid, label in ((WHOLE_CENT, "linear_cent"), (HALF_CENT, "half-cent")):
        for side, tenths in (("yes", 505), ("no", 405)):
            built = OrderRequest(
                ticker="T", side=side, action="buy", count=1,
                limit_price_tenths=tenths, price_grid=grid,
            )
            print(
                f"  {label:<12} buy {side:<3} @ {tenths / 10:>5.1f}c  ->  "
                f"send {built.book_side} {built.api_price_dollars}  "
                f"(we pay {built.fill_price_tenths / 10:.1f}c)"
            )
    print("\n  On the half-cent grid the NO bet costs 40.5c. Flooring sent an")
    print("  offer to sell YES at 60c against a resting bid of 59.5c -- legal,")
    print("  recorded as a placed bet, and unfillable.\n")
    for tenths, action in ((9, "buy"), (999, "sell")):
        try:
            OrderRequest(
                ticker="T", side="yes", action=action, count=1,
                limit_price_tenths=tenths, price_grid=WHOLE_CENT,
            )
        except OrderRefused as exc:
            print(f"  {tenths} tenths, {action} -> OrderRefused")
            print(f"    {exc}\n")

    rule("6. A dry run. The body is exactly what would be sent.")
    order = OrderRequest(
        ticker="KXNFLGAME-26AUG27KCBAL-KC", side="yes", action="buy",
        count=20, limit_price_tenths=509, price_grid=WHOLE_CENT,
        recommendation_id=recent,
    )
    import asyncio

    outcome = asyncio.run(OrderPlacer().place(order))

    print(f"  status                {outcome.status}")
    print(
        f"  limit price sent      {order.api_price_dollars}  "
        f"(from 50.9c, snapped down)"
    )
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
