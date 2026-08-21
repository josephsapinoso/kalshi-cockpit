"""Joe's own record, read off the venue's settlement mirror.

The betting-desk ruling (ADR 0062) made this the product's first job: the
tool is a desk Joe bets from, and until now his own settled bets had **zero
routes and zero screens** — the poller has mirrored `venue_settlements`
since 2026-08-18 (ADR 0044 §6) and nothing ever read it back to him.

One formula, taken verbatim from the calibration registration's Amendment A2
because it is the only settlement arithmetic this repo has ever registered:

    net = payout − cost − fee
    payout = contracts × $1 on a win, $0 on a loss
    cost   = contracts × entry_price_tenths

computed per row in integer tenths of a cent (`core/prices.py` conventions;
`Decimal` for the fractional-contract multiply, exactly as
`estimates.study_loss_dollars` does it). A row whose inputs cannot carry the
formula — an unreadable entry price or fee, a `market_result` that is
neither "yes" nor "no" (a void has no payout to invent), a malformed
contract count — returns **None, never 0**: callers must show it as
uncomputable and count it beside any sum, not fold it in as zero.

Why this module does not read `bet_estimates`: the estimate log is embargoed
forever (Amendment 2 stopped the study WITHOUT RESULT — its statistics stay
uncomputed), and A7's ruling is exactly the line this module walks:
`venue_settlements` is the wallet, not the log. Joe sees these numbers in
the Kalshi app already; nothing here may be attributed to logged estimates,
split into a study win rate, or scoped to the study population.

What this module does NOT establish
-----------------------------------
That the record is complete. It is the poller's mirror: positions settled
before the poller existed (2026-08-18), or while it was down, are absent,
and open positions are structurally absent — settlements are written only
after the venue settles. The screen must say so rather than present the
mirror as the account.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from .core.prices import format_price


def format_net_dollars(net_tenths: Optional[int]) -> Optional[str]:
    """A signed dollar string from integer tenths, or None for a refusal.

    Rendered here, not in the frontend: "the frontend uses the display
    string and never re-derives a price from the float" (`lib/api.ts`), and
    a net is money exactly like an ask is.  1180 -> "+$1.18",
    -820 -> "-$0.82", 0 -> "+$0.00" (a wash is a non-negative outcome).
    """
    if net_tenths is None:
        return None
    sign = "-" if net_tenths < 0 else "+"
    return f"{sign}${abs(net_tenths) / 1000:.2f}"


def settlement_net_tenths(row: Any) -> Optional[int]:
    """One settled position's net, in integer tenths of a cent, or None.

    None is a refusal ("unreadable resolves to None, never 0"): the row
    cannot carry the registered formula and must be excluded from — and
    counted beside — any sum built on this.
    """
    result = row["market_result"]
    if result not in ("yes", "no"):
        return None
    if row["entry_price_tenths"] is None or row["fee_cost_tenths"] is None:
        return None
    try:
        contracts = Decimal(str(row["contracts"]))
    except InvalidOperation:
        return None
    if not contracts.is_finite() or contracts < 0:
        return None
    cost = contracts * row["entry_price_tenths"]
    payout = contracts * 1000 if result == row["side"] else Decimal(0)
    net = payout - cost - Decimal(row["fee_cost_tenths"])
    # The multiply can leave a fraction of a tenth on fractional contracts;
    # int() would truncate toward zero, flattering losses. Round half away
    # from zero is Decimal's quantize default direction ROUND_HALF_EVEN --
    # good enough here because the sum is bookkeeping, not a gate, and the
    # per-row display carries the same rounding it sums.
    return int(net.quantize(Decimal(1)))


def bets_record(conn: sqlite3.Connection, *, limit: int = 200) -> dict:
    """The record and its honest totals, newest settlement first.

    `totals` is computed over the WHOLE table, not the returned window — a
    strip built off a `LIMIT` slice would wear the label of a claim about
    the record (the /api/ledger lesson). The table is one person's account;
    the full scan is cheap by construction. `net_tenths` sums ONLY
    computable rows and `uncomputable` says how many it excludes — a pooled
    number beside the count of what it does not cover, per the measurement
    rules. `wins`/`losses` count computable rows by whether the venue's
    result matched the held side.
    """
    rows = conn.execute(
        "SELECT ticker, event_ticker, market_result, settled_ms, side, "
        "contracts, entry_price_tenths, fee_cost_tenths, "
        "position_first_seen_ms, is_taker, n_fills_in_position "
        "FROM venue_settlements ORDER BY settled_ms DESC, id DESC"
    ).fetchall()

    bets: list[dict] = []
    net_sum = 0
    computable = 0
    uncomputable = 0
    wins = 0
    losses = 0
    for row in rows:
        net = settlement_net_tenths(row)
        won: Optional[bool] = None
        if row["market_result"] in ("yes", "no"):
            won = row["market_result"] == row["side"]
        if net is None:
            uncomputable += 1
        else:
            computable += 1
            net_sum += net
            if won:
                wins += 1
            else:
                losses += 1
        if len(bets) >= limit:
            continue
        bets.append(
            {
                "ticker": row["ticker"],
                "event_ticker": row["event_ticker"],
                "side": row["side"],
                "contracts": row["contracts"],
                "entry_price_tenths": row["entry_price_tenths"],
                "fee_cost_tenths": row["fee_cost_tenths"],
                "market_result": row["market_result"],
                "won": won,
                "net_tenths": net,
                "net_display": format_net_dollars(net),
                "entry_price_display": format_price(row["entry_price_tenths"]),
                "settled_ms": row["settled_ms"],
                "position_first_seen_ms": row["position_first_seen_ms"],
                "is_taker": row["is_taker"],
                "n_fills_in_position": row["n_fills_in_position"],
            }
        )
    return {
        "bets": bets,
        # The window vs the table, so a count computed off the payload cannot
        # wear the label of a claim about the record (the /api/ledger lesson).
        "total": len(rows),
        "returned": len(bets),
        "totals": {
            "net_tenths": net_sum,
            "net_display": format_net_dollars(net_sum),
            "computable": computable,
            "uncomputable": uncomputable,
            "wins": wins,
            "losses": losses,
        },
    }
