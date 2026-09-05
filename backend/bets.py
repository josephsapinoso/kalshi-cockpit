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

Two kinds of bet, separated and never averaged (ticket #21, Joe's 21A,
2026-09-03): a combination market (`KXMVE*`, the venue's parlays) and a single
game are not the same kind of bet, and on the live record the combos are the
majority. `bets_record` classifies every row by ticker through
`estimates.classify_ticker` -- the one `KXMVE` prefix check this repo has,
reused rather than respelled -- and serves a per-kind section with its own
count and its own net SUM. A sum is the per-group view the measurement rules
ask for; **no average, win rate, hit rate, streak or trend is computed for
either section or for the whole**, and that stays until thirty scored bets
exist with the per-group view beside them.

What this module does NOT establish
-----------------------------------
That the record is complete. It is the poller's mirror: the settlements
endpoint drops history, so anything the venue dropped before the poller read
it is gone, and positions settled while the poller was down are absent. The
record's own first settlement is served (`first_settled_ms`) so the screen
can state its first day from the data rather than from a date typed into the
page. Open positions are structurally absent — settlements are written only
after the venue settles — which is also why an unsettled combination bet is
not here at all: it reaches this table only when the venue settles it.
"""

from __future__ import annotations

import logging
import sqlite3
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from .analysis.clv import DEFAULT_HORIZON_HOURS
from .analysis.clv import clv_tenths as _clv_tenths
from .core.prices import format_price
from .estimates import classify_ticker
from .odds.timing import day_start_ms

logger = logging.getLogger(__name__)

# The two kinds a settled position can be, by ticker. `combo` is the venue's
# multi-leg market (`KXMVE*`); everything else -- a moneyline, a spread, a
# prop, a non-sports market bet by hand -- is `single`. The word is "single"
# rather than "game" because a hand bet on a non-sports market is not a game
# and is still one market with one result.
KIND_SINGLE = "single"
KIND_COMBO = "combo"

# Why a combination bet carries this reason instead of `no_closing_line`:
# combos are excluded from discovery (`kalshi/combos.py`; `rest.py` drops
# `KXMVE` from `/markets`), so no `closing_lines` row can ever exist for one.
# That is not "the close has not been read yet" -- it is "there is no close
# to read" -- and the screen must not render fifty rows of the former.
CLV_REFUSAL_COMBO = "combo_unscorable"


def bet_kind(ticker: str) -> str:
    """`combo` for a multi-leg market, `single` otherwise, from the ticker.

    Delegates to `estimates.classify_ticker` so the `KXMVE` prefix is spelled
    in exactly one place in this repo; a second prefix check here would be
    the two-spellings defect CLAUDE.md records under the window banner.
    """
    _is_sports, _sport, is_multi_leg = classify_ticker(ticker)
    return KIND_COMBO if is_multi_leg else KIND_SINGLE


# The staleness ceiling for the "tonight" strip: 6x the fills cadence
# (portfolio_poll.BALANCE_INTERVAL_S = 300s, which fills joined on the
# 2026-08-21 partner ruling) -- survives two failed polls, too tight for an
# evening of betting to hide inside. Past it the strip REFUSES (null, never
# 0): "no bets tonight" rendered off a stale mirror is a false negative in
# the flattering direction, on the one screen whose purpose is to interrupt.
TONIGHT_STALE_AFTER_MS = 30 * 60 * 1000

# The words served for "staked now" on the open-positions strip when the
# mirror cannot produce it, rendered server-side like every other refusal.
# **Until schema v33 there was one constant here and it was unconditional**
# (`STAKED_NOW_REFUSAL`, ADR 0101 section 2.3): the poller counted the
# venue's position rows and discarded them, so no honest figure existed.
# `venue_positions` now holds the venue's own per-position exposure at cost,
# and each sentence below names ONE state in which that figure is genuinely
# unreadable, so the screen can say which. None of them is "the number is
# zero"; a refusal is always words, never $0.00.
STAKED_NEVER_POLLED = "no positions poll has succeeded yet"
# A positions read HAS been logged and none has kept its rows: every
# `poll_log` row is from before v33, or is the hand-bet path's own stamp
# (`routes.py::_stamp_positions_read` logs the read and keeps no rows). The
# poller's next successful poll is the first one the figure can come from.
# Neither the count nor the money is served off a bare row -- they wear one
# stamp or none -- so this is words with no clock, and distinct from
# "never polled" because it is not true that the venue was never asked.
STAKED_NOT_MIRRORED = "no positions poll has kept its rows yet"
# The same 30-minute bound and the same words the value's stale refusal
# uses: one clock for both figures on this line.
STAKED_NOT_READ = "not read in the last 30 minutes"
# The newest MIRRORED poll counted N rows and the mirror holds M under its
# stamp. Since the marker (`poll_log.mirrored`, v33) this is an integrity
# refusal, not an expected state: the rows and the mark are written in one
# transaction, and the writer's seven-day prune cannot reach a poll the
# thirty-minute staleness bound would still serve.
#
# **It is no longer how a second writer shows up, and the second writer is
# live, not hypothetical.** `routes.py::_stamp_positions_read` logs a
# positions read on every hand bet, with a real `row_count`, and keeps no
# rows. Before the marker this reader selected that stamp as the newest
# successful poll, counted N against 0 rows, and refused here for up to five
# minutes after every bet -- silent when Joe held nothing (0 = 0), firing
# exactly when he did. The marker keeps that stamp out of the selection, so
# what reaches this sentence now is a hand-edited table or a writer that set
# the mark without the rows. Either way the count and the money figure would
# come from different reads, and that is refused, not averaged.
STAKED_MIRROR_MISMATCH = (
    "the poll counted {count} positions and the mirror holds {rows} rows "
    "for it; refusing to sum a different read"
)
# One row's `exposure_tenths` is NULL (the venue's string did not parse, was
# negative on a side whose sign convention is unobserved, or exceeded $1 a
# contract -- the scale tripwire in `parse_position`, because the field's
# unit is inferred from a suffix and never measured). A sum over the rest is
# a false low, so the whole figure refuses.
STAKED_ROW_UNREADABLE = (
    "a position's exposure at cost did not parse; refusing to sum the rest"
)
STAKED_RECORD_UNREADABLE = "the open-positions record could not be read"


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

    **Two kinds, two sections (21A).** Every row carries `kind`
    (`bet_kind`), and `sections` carries one block per kind over the WHOLE
    table -- `total`, `net_tenths`/`net_display`, `computable`,
    `uncomputable` -- so the screen can head each list with its own count and
    its own sum. The whole-record `totals` is unchanged and still covers both.
    A per-kind sum beside the pooled one is the "print the parts beside the
    aggregate" rule; a per-kind *rate* would be the banned aggregate, and none
    is computed.

    **`clv_coverage` counts single-game rows only, and says so.** A `KXMVE`
    ticker cannot have a `closing_lines` partner (combos are excluded from
    discovery), so counting fifty combos among the refusals would report
    "scored on 1 of 77" for a record in which 50 rows were never scorable.
    `population` names the cut and `denominator` is the singles count, so the
    line reads "scored on N of {singles}". A combo row's
    `clv_refusal_reason` is `combo_unscorable`, distinct from
    `no_closing_line`, and is not counted in `refusals`.

    `first_settled_ms` is `MIN(settled_ms)` over the table, `None` when it is
    empty -- the record's own first day, so the page never has to type one.
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
    # Per-kind blocks over the WHOLE table, same discipline as `totals`.
    sections: dict[str, dict[str, int]] = {
        kind: {"total": 0, "net_tenths": 0, "computable": 0, "uncomputable": 0}
        for kind in (KIND_SINGLE, KIND_COMBO)
    }
    first_settled_ms: Optional[int] = None
    for row in rows:
        kind = bet_kind(row["ticker"])
        section = sections[kind]
        section["total"] += 1
        if first_settled_ms is None or row["settled_ms"] < first_settled_ms:
            first_settled_ms = row["settled_ms"]
        net = settlement_net_tenths(row)
        won: Optional[bool] = None
        if row["market_result"] in ("yes", "no"):
            won = row["market_result"] == row["side"]
        if net is None:
            uncomputable += 1
            section["uncomputable"] += 1
        else:
            computable += 1
            net_sum += net
            section["computable"] += 1
            section["net_tenths"] += net
            if won:
                wins += 1
            else:
                losses += 1
        if kind == KIND_COMBO:
            # Structurally unscorable: not a refusal to count among the
            # singles' refusals, and never rendered as "close not read yet".
            clv, clv_refusal_reason = None, CLV_REFUSAL_COMBO
        else:
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
                "kind": kind,
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
        # The record's own first day. None on an empty table, never 0 -- a
        # 1970 date is a claim about history the mirror does not have.
        "first_settled_ms": first_settled_ms,
        # One block per kind, whole-table, each with its own count and its
        # own SUM. `sections["single"]["total"] + sections["combo"]["total"]
        # == total` by construction; the test pins it.
        "sections": {
            kind: {
                **block,
                "net_display": format_net_dollars(block["net_tenths"]),
            }
            for kind, block in sections.items()
        },
        # "CLV scored on N of {denominator}": the denominator the per-bet
        # numbers never had, and since 21A it is the SINGLES count -- a combo
        # has no close to be scored against, so it is neither scored nor a
        # refusal. Counts only -- no value of any scored CLV is combined here
        # (the no-aggregate constraint stands until n >= 30).
        "clv_coverage": {
            "population": KIND_SINGLE,
            "denominator": sections[KIND_SINGLE]["total"],
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


# **The open-positions COUNT is on `TONIGHT_STALE_AFTER_MS` and has no
# constant of its own.** It had one until 2026-08-29 --
# `POSITIONS_STALE_AFTER_MS = 26h`, "two mirror cycles plus two hours of
# grace" -- and the comment beside it was right about its own premise and
# wrong about what to do: a 30-minute bound against a 12-hour poller would
# indeed have refused essentially always, so the bound was widened to fit the
# poller. The poller was the thing to fix. `portfolio_poll.poll_positions`
# now rides the 5-minute cadence, so 30 minutes is the same 6x-cadence bound
# `tonight_activity` and the daily-loss kill switch already use, and the
# count's refusal stops being furniture in BOTH directions: a 26h ceiling on
# a 5-minute poller would serve a count from yesterday evening as "open
# now", which is the false negative in the flattering direction pointed at
# what is at risk.
#
# One bound, shared, rather than a fourth spelling of "recently" -- ADR 0064's
# rule, applied to the constant it was written about.


def open_positions(conn: sqlite3.Connection, *, now_ms: int) -> dict:
    """What is open at the venue right now: a count, the money on it at cost,
    and the venue's portfolio value -- each refusing in words before it
    flatters.

    **What changed at schema v33, and why the docstring says so.** Until then
    this paragraph said there was *"no per-position mirror table to read"*
    and that `poll_positions` *"counts rows and parses none"* -- true, and the
    third of ADR 0101 section 2.3's reasons the staked figure was refused
    unconditionally. The per-row shape was captured 2026-08-30
    (`tests/test_rest.py::OBSERVED_POSITION_ROW`), `venue_positions` now
    holds every row the poller fetches, and the figure is served from it.
    The two reasons that named `fills` are unchanged and still true; they no
    longer matter, because nothing here reads `fills`.

    - **`count`** -- `poll_log.row_count` of the newest successful
      'positions' poll **that kept its rows** (`poll_log.mirrored = 1`): the
      number of `market_positions` rows the venue returned under
      `count_filter=position`, its own non-zero cut (`rest.positions()`), so
      the count means "open now" rather than "ever traded". **What changed
      in the selection, and why.** Until the marker this took the newest
      successful positions poll of any kind, and `poll_log` has a second
      writer: `routes.py::_stamp_positions_read` logs the hand-bet path's own
      positions read on every bet, with a real `row_count`, and keeps no
      rows. That stamp was the newest poll for up to five minutes after every
      hand bet, so the count was served off it and the money figure refused
      with a mismatch -- "Open now: 2" beside a refusal sentence, the exact
      state this figure exists to replace, at the one moment ADR 0105 says
      the desk is open, and silent whenever Joe held nothing (0 = 0). Now the
      bare stamp is simply not selected. Nothing is lost by that: the route
      takes its read BEFORE the order is sent, so its count is the poller's
      last count anyway, and the poller's next poll lands inside five minutes.
      The route should keep its rows through
      `portfolio_poll.store_positions_snapshot`; that edit is `routes.py`'s
      and was deferred to the integrator.
    - **`staked_tenths`/`staked_display`/`staked_refusal`** -- the money Joe
      has put on those positions, **at cost**: the venue's own
      `market_exposure_dollars` per row, in integer tenths of a cent
      (`venue_positions.exposure_tenths`), added up over the rows stamped
      with THAT poll. Money in, before fees. It is not market value, nothing
      marks it to market, and it needs no live quote -- which is why it
      cannot go stale on its own clock. Unsigned, never summed with cash.
    - **`value_tenths`/`value_display`/`value_refusal`** -- unchanged: the
      newest snapshot's `portfolio_value_tenths`, the venue's `portfolio_value`
      from the balance payload, whose unit is pinned only at zero
      (`parse_portfolio_value_tenths`) so any non-zero value refuses with its
      reason.

    **The count and the staked figure come from ONE read and wear ONE stamp,
    `count_as_of_ms`.** The staked rows are selected by the `poll_log` id of
    the very poll whose `row_count` is the count, so the two cannot describe
    different instants; the payload deliberately has no `staked_as_of_ms`,
    because a second stamp for the same read would invite the divergence
    `tests/test_open_positions_stamp.py` exists to forbid. **The value keeps
    its own stamp** (`value_as_of_ms`): a shared cadence is not a shared read,
    and a failed positions poll leaves this stamp behind while the balance's
    moves on -- exactly the divergence a single stamp would hide.

    **One staleness bound, `TONIGHT_STALE_AFTER_MS`.** Past it the count AND
    the staked figure refuse to `None` with `count_as_of_ms` kept, so the
    reader renders "not read since HH:MM" -- never 0, which would report
    "nothing at risk" off a dead poller, the false negative in the flattering
    direction.

    **An empty-but-fresh snapshot is count 0 and $0.00, and that is not the
    false negative `OpenPositions.tsx` guards against.** That guard is about
    `$0.00` beside a NON-ZERO count -- a money figure invented while the
    count says there is money. Here both come from the same successful read
    of the same endpoint seconds ago: the venue said it holds nothing, and
    the count says the same thing in the same breath. The 2026-09-05 capture
    found exactly this state on the live account.

    **The staked figure refuses in words in five states, each a genuinely
    unreadable one, none of them "the number is zero":** no successful poll
    (`STAKED_NEVER_POLLED`); a successful poll but none that kept its rows
    (`STAKED_NOT_MIRRORED` -- rows from before v33, or only the hand-bet
    path's stamp; the count is not served off a bare row either, so the two
    wear one stamp or none); the newest mirrored one is stale
    (`STAKED_NOT_READ`); the mirror holds a different number of rows than
    that poll counted (`STAKED_MIRROR_MISMATCH` -- an integrity failure now,
    since the marker keeps the second writer out of the selection); any row's
    `exposure_tenths` is NULL (`STAKED_ROW_UNREADABLE` -- a partial sum is a
    false low, so the whole figure refuses rather than summing the rest).

    `count_age_ms`/`value_age_ms` are each read's age against the SAME
    `now_ms` the staleness bounds use, so the reader never has to subtract a
    server millisecond from a browser one. `None` where the matching `as_of`
    is `None`: an unread figure has no age, and 0 would say "just read".

    **NO live P&L, no mark-to-market, and never summed with cash** --
    TonightStrip's unsigned rule. Refusal words are rendered server-side,
    matching the display-string convention.

    What this does not establish: the unit of `market_exposure_dollars`
    (inferred from its suffix, bounded by `parse_position`'s $1-a-contract
    tripwire, measured by nothing -- a first non-empty snapshot against a
    known position is the measurement); whether it includes fees (the wire
    carries `fees_paid_dollars` beside it; nothing here tests the relation);
    and anything about `event_positions`, which the poller does not read.
    """
    payload: dict = {
        "count": None,
        "count_as_of_ms": None,
        "count_age_ms": None,
        "value_tenths": None,
        "value_display": None,
        "value_as_of_ms": None,
        "value_age_ms": None,
        "value_refusal": None,
        "staked_tenths": None,
        "staked_display": None,
        "staked_refusal": None,
    }
    try:
        # The newest successful poll THAT KEPT ITS ROWS. `mirrored = 1` is
        # what keeps the hand-bet path's bare stamp (a real count, no rows)
        # from being selected here and refusing the figure for five minutes
        # after every bet -- see the `count` bullet above.
        count_row = conn.execute(
            "SELECT id, polled_ms, row_count FROM poll_log "
            "WHERE endpoint = 'positions' AND ok = 1 AND mirrored = 1 "
            "ORDER BY polled_ms DESC, id DESC LIMIT 1"
        ).fetchone()
        # Consulted only to choose words when nothing is mirrored: a read
        # that kept no rows is not "never polled", and the sentence must not
        # say the venue was never asked when it was.
        any_success = (
            conn.execute(
                "SELECT 1 FROM poll_log "
                "WHERE endpoint = 'positions' AND ok = 1 LIMIT 1"
            ).fetchone()
            if count_row is None
            else None
        )
        value_row = conn.execute(
            "SELECT observed_ms, portfolio_value_tenths "
            "FROM venue_balance_snapshots "
            "ORDER BY observed_ms DESC, id DESC LIMIT 1"
        ).fetchone()
        # The rows of THAT poll and no other: keyed by its id, never by
        # "the newest rows", which after a failed poll would be the same
        # rows and after a second writer might not be.
        mirror_rows = (
            conn.execute(
                "SELECT exposure_tenths FROM venue_positions "
                "WHERE poll_log_id = ?",
                (count_row["id"],),
            ).fetchall()
            if count_row is not None
            else []
        )
    except Exception:                                       # noqa: BLE001
        logger.exception("could not read the open-positions record")
        payload["staked_refusal"] = STAKED_RECORD_UNREADABLE
        return payload

    if count_row is None:
        payload["staked_refusal"] = (
            STAKED_NOT_MIRRORED if any_success is not None
            else STAKED_NEVER_POLLED
        )
    else:
        polled_ms = count_row["polled_ms"]
        row_count = count_row["row_count"]
        payload["count_as_of_ms"] = polled_ms
        payload["count_age_ms"] = max(0, now_ms - polled_ms)
        if now_ms - polled_ms > TONIGHT_STALE_AFTER_MS:
            payload["staked_refusal"] = STAKED_NOT_READ
        elif row_count is None:
            payload["staked_refusal"] = STAKED_RECORD_UNREADABLE
        else:
            payload["count"] = int(row_count)
            if len(mirror_rows) != int(row_count):
                payload["staked_refusal"] = STAKED_MIRROR_MISMATCH.format(
                    count=int(row_count), rows=len(mirror_rows)
                )
            elif any(r["exposure_tenths"] is None for r in mirror_rows):
                payload["staked_refusal"] = STAKED_ROW_UNREADABLE
            else:
                staked = 0
                for r in mirror_rows:
                    staked += int(r["exposure_tenths"])
                payload["staked_tenths"] = staked
                payload["staked_display"] = f"${staked / 1000:.2f}"

    if value_row is not None:
        payload["value_as_of_ms"] = value_row["observed_ms"]
        payload["value_age_ms"] = max(0, now_ms - value_row["observed_ms"])
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
