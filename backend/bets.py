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

import logging
import sqlite3
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from .analysis.clv import DEFAULT_HORIZON_HOURS
from .analysis.clv import clv_tenths as _clv_tenths
from .core.prices import format_price
from .odds.timing import day_start_ms

logger = logging.getLogger(__name__)


# The staleness ceiling for the "tonight" strip: 6x the fills cadence
# (portfolio_poll.BALANCE_INTERVAL_S = 300s, which fills joined on the
# 2026-08-21 partner ruling) -- survives two failed polls, too tight for an
# evening of betting to hide inside. Past it the strip REFUSES (null, never
# 0): "no bets tonight" rendered off a stale mirror is a false negative in
# the flattering direction, on the one screen whose purpose is to interrupt.
TONIGHT_STALE_AFTER_MS = 30 * 60 * 1000


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


def format_clv_cents(clv: Optional[float]) -> Optional[str]:
    """A signed cents string for a per-bet CLV figure, or None for a refusal.

    Deliberately not `format_net_dollars`: CLV is a per-contract price
    difference in cents (what the position is worth at the close, minus what
    it cost), not a dollar sum -- rendering it as "+$0.05" would read as
    money moved rather than a price beaten. 23 -> "+2.3c", -5 -> "-0.5c".
    """
    if clv is None:
        return None
    sign = "-" if clv < 0 else "+"
    return f"{sign}{abs(clv) / 10:.1f}c"


def bet_clv(row: Any) -> tuple[Optional[float], Optional[str]]:
    """One bet's closing-line value, and why it refuses when it does.

    Mirrors `analysis.clv.score_recommendations`'s convention exactly:
    `close_mid = (yes_bid + yes_ask) / 2`, `entry_price_tenths` is already
    side-denominated (the price actually paid for the side held, same
    convention as `recommendations.entry_ask_tenths`), and the entry must
    precede the close it is scored against -- a bet placed after the close
    was observed would be scored against a price that predates the decision,
    which puts market drift into a number meant to detect edge rather than
    it. `position_first_seen_ms` carries that instant here (`venue_settlements`
    has no `created_ms`); NULL means the poller never caught the fill landing,
    which must refuse, not be treated as "before everything".

    Returns `(None, reason)` on every refusal, never a substituted number --
    `reason` is `"no_closing_line"` (most hand-bet tickers, structurally: no
    discovery row, no link, or the game hasn't been scored yet),
    `"unreadable_close"` (a line was stored but a side was unreadable, or the
    entry price itself is), `"entry_time_unknown"`, or `"entry_after_close"`.
    `(value, None)` is the only scored case.
    """
    if row["closing_observed_ms"] is None:
        return None, "no_closing_line"
    if row["yes_bid_tenths"] is None or row["yes_ask_tenths"] is None:
        return None, "unreadable_close"
    if row["entry_price_tenths"] is None:
        return None, "unreadable_close"
    if row["position_first_seen_ms"] is None:
        return None, "entry_time_unknown"
    if row["position_first_seen_ms"] > row["closing_observed_ms"]:
        return None, "entry_after_close"
    mid = (row["yes_bid_tenths"] + row["yes_ask_tenths"]) / 2
    return _clv_tenths(row["entry_price_tenths"], mid, row["side"]), None


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

    Each returned bet also carries its own closing-line value (`bet_clv`),
    read against the primary horizon `scoring.py` fills for
    `venue_settlements` tickers same as it does for recommendations. Per-bet
    only, by the partner's hard constraint on the most ego-loaded quantity in
    the product: **no average, no hit rate, no "you beat the close X% of the
    time" anywhere in this module** until n >= 30 with the per-group view
    printed beside it. Nothing here computes one.
    """
    rows = conn.execute(
        "SELECT v.ticker, v.event_ticker, v.market_result, v.settled_ms, v.side, "
        "v.contracts, v.entry_price_tenths, v.fee_cost_tenths, "
        "v.position_first_seen_ms, v.is_taker, v.n_fills_in_position, "
        "c.observed_ms AS closing_observed_ms, "
        "c.yes_bid_tenths, c.yes_ask_tenths "
        "FROM venue_settlements v "
        "LEFT JOIN closing_lines c "
        "  ON c.ticker = v.ticker AND c.horizon_hours = ? "
        "ORDER BY v.settled_ms DESC, v.id DESC",
        (DEFAULT_HORIZON_HOURS,),
    ).fetchall()

    bets: list[dict] = []
    net_sum = 0
    computable = 0
    uncomputable = 0
    wins = 0
    losses = 0
    # CLV coverage over the WHOLE table, like `totals`: "scored on N of
    # {total}" is a claim about the record, and computing it off the windowed
    # list would let the newest `limit` rows wear that label. A **count of
    # scored rows is not an aggregate of CLV values** -- the hard constraint
    # above bans averaging the measurements, not counting how many exist --
    # and the refusals are counted by reason so unmeasured never renders
    # identically to bad (the recurring zero-that-means-no-measurement).
    clv_scored = 0
    clv_refusals: dict[str, int] = {}
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
        clv, clv_refusal_reason = bet_clv(row)
        if clv is not None:
            clv_scored += 1
        else:
            clv_refusals[clv_refusal_reason] = (
                clv_refusals.get(clv_refusal_reason, 0) + 1
            )
        if len(bets) >= limit:
            continue
        close_mid_tenths: Optional[float] = None
        if row["yes_bid_tenths"] is not None and row["yes_ask_tenths"] is not None:
            close_mid_tenths = (row["yes_bid_tenths"] + row["yes_ask_tenths"]) / 2
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
                "clv_tenths": clv,
                "clv_display": format_clv_cents(clv),
                "clv_refusal_reason": clv_refusal_reason,
                "close_mid_tenths": close_mid_tenths,
                "close_display": (
                    format_price(int(round(close_mid_tenths)))
                    if close_mid_tenths is not None
                    else None
                ),
            }
        )
    return {
        "bets": bets,
        # The window vs the table, so a count computed off the payload cannot
        # wear the label of a claim about the record (the /api/ledger lesson).
        "total": len(rows),
        "returned": len(bets),
        # "CLV scored on N of {total}": the denominator the per-bet numbers
        # never had. Counts only -- no value of any scored CLV is combined
        # here (the no-aggregate constraint stands until n >= 30).
        "clv_coverage": {
            "scored": clv_scored,
            "refusals": clv_refusals,
        },
        "totals": {
            "net_tenths": net_sum,
            "net_display": format_net_dollars(net_sum),
            "computable": computable,
            "uncomputable": uncomputable,
            "wins": wins,
            "losses": losses,
        },
    }


def tonight_activity(
    conn: sqlite3.Connection, *, now_ms: int, day_start_hour: int
) -> dict:
    """What Joe has already committed tonight, from the fills mirror.

    The 2026-08-21 partner ruling (docs/reviews/2026-08-21-items-2-3-ruling
    .md), compressed: **fills, not settlements** (a settlement lands when the
    game ends -- the wrong clock -- and can only produce a net, which is the
    chase trigger this repo has deleted twice); a "bet" is a **distinct
    ticker** (a partial fill is not a second decision); stake is
    **SUM(count x price_tenths)** -- money at risk on a binary; **no
    `source` filter**, deliberately: ADR 0043's engine/venue_hand split
    keeps the fee-calibration population clean, but "how much have I
    committed tonight" is not that question and both are money committed.
    The day rolls at the same hour the odds budget, the risk day and the
    lockout use -- a third definition of tomorrow is how the looser one
    wins in silence.

    `bets`/`staked_*` are **null when the mirror is stale** (`as_of_ms`
    absent or older than `TONIGHT_STALE_AFTER_MS`): the reader renders
    "not read since HH:MM", never 0.
    """
    start_ms = day_start_ms(now_ms, hour=day_start_hour)
    as_of_row = conn.execute(
        "SELECT MAX(polled_ms) AS ms FROM poll_log "
        "WHERE endpoint = 'fills' AND ok = 1"
    ).fetchone()
    as_of = as_of_row["ms"] if as_of_row is not None else None
    payload: dict = {
        "day_start_ms": start_ms,
        "as_of_ms": as_of,
        "bets": None,
        "staked_tenths": None,
        "staked_display": None,
    }
    if as_of is None or now_ms - as_of > TONIGHT_STALE_AFTER_MS:
        return payload
    row = conn.execute(
        "SELECT COUNT(DISTINCT ticker) AS markets, "
        "COALESCE(SUM(count * price_tenths), 0) AS staked "
        "FROM fills WHERE filled_ms >= ?",
        (start_ms,),
    ).fetchone()
    staked_tenths = int(round(row["staked"]))
    payload["bets"] = int(row["markets"])
    payload["staked_tenths"] = staked_tenths
    # Unsigned on purpose: this is commitment, not performance. The signed
    # number lives on /bets, after settlement, where it is a record and not
    # a scoreboard.
    payload["staked_display"] = f"${staked_tenths / 1000:.2f}"
    return payload


# The staleness ceiling for the open-positions COUNT. Its producer is the
# 12-hour mirror clock (`portfolio_poll.MIRROR_INTERVAL_S` -- positions are
# polled only on the full mirror, NOT on the 5-minute balance cadence), so
# `TONIGHT_STALE_AFTER_MS` must NOT be reused here: a 30-minute bound against
# a 12-hour poller would refuse essentially always and the refusal would be
# furniture. 26h = two mirror cycles plus two hours of grace -- one failed
# mirror poll does not flap the screen; a second consecutive failure refuses.
POSITIONS_STALE_AFTER_MS = 26 * 3600 * 1000


def open_positions(conn: sqlite3.Connection, *, now_ms: int) -> dict:
    """What is open at the venue right now, from the only two things mirrored.

    The largest hole the 2026-08-22 review found: Joe could not see what was
    at risk on any screen. There is **no per-position mirror table** to read
    -- `portfolio_poll` counts the `/portfolio/positions` rows and refuses to
    parse them (the per-row shape has never been observed on this account;
    five parsers in this repo's history were written against imagined wire
    formats). So this serves exactly what the record carries, and says so:

    - **`count`** -- `poll_log.row_count` of the newest successful
      'positions' poll: the number of `market_positions` rows the venue
      returned, counted and not parsed. Whether the venue includes settled
      or zero-count rows in that list is unobserved; the count is "position
      rows at the venue", not a parsed claim about each one.
    - **`value_tenths`/`value_display`** -- the newest snapshot's
      `portfolio_value_tenths`, the venue's own `portfolio_value` from the
      balance payload (5-minute cadence). Its unit is pinned only at zero
      (`parse_portfolio_value_tenths`), so any non-zero value is stored as
      NULL and refuses here with its reason -- the honest state until a
      non-empty payload pins the unit. Whether it includes fees is equally
      unobserved; nothing here claims it.

    Two staleness clocks because the two producers run on two cadences: the
    count against `POSITIONS_STALE_AFTER_MS` (12h poller), the value against
    `TONIGHT_STALE_AFTER_MS` (5-minute balance cadence). Stale refuses to
    `None` with the `as_of` kept, so the reader renders "not read since
    HH:MM" -- never 0, which would report "nothing at risk" off a dead
    poller, the false negative in the flattering direction.

    **NO live P&L, no mark-to-market, and never summed with cash** --
    TonightStrip's unsigned rule. The refusal words are rendered server-side
    (`value_refusal`), matching the display-string convention.
    """
    payload: dict = {
        "count": None,
        "count_as_of_ms": None,
        "value_tenths": None,
        "value_display": None,
        "value_as_of_ms": None,
        "value_refusal": None,
    }
    try:
        count_row = conn.execute(
            "SELECT polled_ms, row_count FROM poll_log "
            "WHERE endpoint = 'positions' AND ok = 1 "
            "ORDER BY polled_ms DESC LIMIT 1"
        ).fetchone()
        value_row = conn.execute(
            "SELECT observed_ms, portfolio_value_tenths "
            "FROM venue_balance_snapshots "
            "ORDER BY observed_ms DESC, id DESC LIMIT 1"
        ).fetchone()
    except Exception:                                       # noqa: BLE001
        logger.exception("could not read the open-positions record")
        return payload

    if count_row is not None:
        payload["count_as_of_ms"] = count_row["polled_ms"]
        if (
            now_ms - count_row["polled_ms"] <= POSITIONS_STALE_AFTER_MS
            and count_row["row_count"] is not None
        ):
            payload["count"] = int(count_row["row_count"])

    if value_row is not None:
        payload["value_as_of_ms"] = value_row["observed_ms"]
        if now_ms - value_row["observed_ms"] > TONIGHT_STALE_AFTER_MS:
            payload["value_refusal"] = "not read in the last 30 minutes"
        elif value_row["portfolio_value_tenths"] is None:
            # The newest snapshot is fresh and the stored value is NULL:
            # `parse_portfolio_value_tenths` refused it, which for any open
            # position is the expected state until the unit is pinned.
            payload["value_refusal"] = (
                "the venue reported a value whose unit has never been "
                "pinned; refusing to guess"
            )
        else:
            payload["value_tenths"] = value_row["portfolio_value_tenths"]
            payload["value_display"] = (
                f"${value_row['portfolio_value_tenths'] / 1000:.2f}"
            )
    else:
        payload["value_refusal"] = "never observed"
    return payload


def venue_daily_realised_pnl_dollars(
    conn: sqlite3.Connection, *, now_ms: int, day_start_hour: int
) -> Optional[float]:
    """The risk day's realised P&L off the venue's own record, or a refusal.

    ADR 0064: wherever money is gated, daily realised P&L is computed from
    `venue_settlements` -- the venue's record of every bet however placed --
    not from the engine-path `settlements` table, which is written only by a
    sweep over `orders` and has therefore been empty for the project's whole
    life (`ORDERS_ARE_DRY_RUNS = True` since birth). A kill switch reading
    that table returns $0.00 forever as a genuine measurement over the wrong
    population.

    Negative is a loss, in dollars, because that is the unit
    `core/sizing.py`'s `daily_pnl_dollars` compares. The day is the risk
    day: the same `day_start_ms` roll hour `tonight_activity`, the odds
    budget and `settlement.risk_day_start_ms` all share -- callers pass the
    *configured* hour so a third definition of "today" cannot appear here.

    **Staleness refuses, it never zeroes.** If the settlements mirror's
    freshest successful read (`poll_log`, endpoint 'settlements', ok = 1) is
    absent or older than `TONIGHT_STALE_AFTER_MS`, this returns `None` and
    the sizer's existing `None`-refusal stops the order. A stale mirror at
    8pm otherwise reports "no losses today" while the evening's settlements
    sit unread -- the false negative in the flattering direction, on the
    exact quantity that exists to stop the next bet.

    Rows that cannot carry the registered formula (`settlement_net_tenths`)
    split two ways, and the split is stated because it differs from
    `bets_record`'s display convention in one direction only:

    - a **void** (`market_result` neither "yes" nor "no") is EXCLUDED and
      counted in the log, exactly as `bets_record` excludes-and-counts it: a
      void has no registered payout, and refusing the whole day's figure for
      a scratched market would turn one venue quirk into a standing order
      block.
    - an **unreadable money field on a decided row** (a "yes"/"no" result
      whose entry price, fee, or count cannot be read) refuses the WHOLE
      figure (`None`). Excluding it, as the display does beside an explicit
      count, has no beside-the-number here -- the sizer receives one float,
      so a silently dropped loss would understate the day in the flattering
      direction.

    No `dry_run` split, deliberately: the engine function pools paper with
    paper and live with live, but the venue's record has no paper rows --
    everything in it is Joe's money -- and when the engine someday places
    real orders the venue settles them into this same mirror, so reading
    only the mirror is what makes a double count impossible (ADR 0064 §3).

    What this does NOT establish: that the mirror is complete. A freshly
    polled mirror still lacks positions settled while the poller was down or
    before it existed (2026-08-18), and open losing positions are
    structurally absent because their loss is not yet realised. Freshness
    bounds the staleness of the record; it is not a completeness proof.
    """
    try:
        as_of_row = conn.execute(
            "SELECT MAX(polled_ms) AS ms FROM poll_log "
            "WHERE endpoint = 'settlements' AND ok = 1"
        ).fetchone()
        as_of = as_of_row["ms"] if as_of_row is not None else None
        if as_of is None or now_ms - as_of > TONIGHT_STALE_AFTER_MS:
            return None
        rows = conn.execute(
            "SELECT ticker, market_result, side, contracts, "
            "entry_price_tenths, fee_cost_tenths "
            "FROM venue_settlements WHERE settled_ms >= ?",
            (day_start_ms(now_ms, hour=day_start_hour),),
        ).fetchall()
    except Exception:                                       # noqa: BLE001
        logger.exception("could not read the venue settlements mirror")
        return None

    net_sum = 0
    voids = 0
    for row in rows:
        net = settlement_net_tenths(row)
        if net is None:
            if row["market_result"] in ("yes", "no"):
                logger.error(
                    "venue settlement on %s is decided but unreadable; the "
                    "day's P&L cannot be summed. Refusing rather than "
                    "dropping a possible loss.", row["ticker"],
                )
                return None
            voids += 1
            continue
        net_sum += net
    if voids:
        logger.info(
            "daily realised P&L excludes %d void settlement(s) with no "
            "registered payout", voids,
        )
    return net_sum / 1000.0
