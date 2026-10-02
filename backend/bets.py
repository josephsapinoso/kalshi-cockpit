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

**#161: the chance the desk showed him at the moment he priced the parlay.**
Every combination row carries `chance_when_priced`, the LATEST reading at or
before the anchor from either of two sources — `parlay_lookups
.fair_joint_conservative` from a lookup with `status IN ('priced',
'book_empty')`, or `combo_rfqs.fair_joint` from a maker price-ask (ADR
0164) — that minted or named the row's ticker, where the anchor is
`MIN(fills.filled_ms)` for that ticker — and `chance_priced_before_fill_ms`,
the anchor minus that reading's `requested_ms`. **#163 correction**: a KXMVE
book is empty by design between RFQs (ADR 0164), so most real lookups come
back `book_empty`, not `priced`, and #161's `status = 'priced'`-only read
undercounted; a `combo_rfqs` row also freezes the desk's chance the same way
and #161 never read that table either. This is a per-row fact (ADR 0071: a
per-row fact is transparency, an ordering is a claim), not a score: it
answers "what did the desk's consensus say when I bought this", never "was
this a good parlay". Built as one batched query over every combo ticker on
the WHOLE table (never one query per row, matching the `totals`/`sections`
discipline above), and counted, never averaged or summed, in
`sections["combo"]["chance_carried"]`.

**#168: "not priced on the desk" was false for a parlay the desk had in fact
looked at.** The outside-parlay check (#166, `parlay_lookups.card_key =
'outside'`) can write a row with `status IN ('priced', 'book_empty')` and a
NULL `fair_joint_conservative` -- the desk read the parlay and could not
produce one number for the whole thing (a leg with no desk reading, or two
legs on one game). Before this, such a row was invisible to
`chance_when_priced` (it never carries a chance) and the row rendered
identically to a parlay never checked at all. Every combo row now also
carries `checked_without_chance`: true when such a row exists at or before
the anchor AND no qualifying reading (one with a real joint chance) exists.
A reading with a chance always wins -- this flag is consulted only once
`chance_when_priced` has already come back `None`. It is a per-row fact,
never counted toward `chance_carried` (that count is chance coverage, and
this row carries no chance to be covered by).

**#287: the summary never pools the kinds, and its one "expected" line is
parlays'.** `summary` carries wins and losses PER KIND and no pooled count
(the pooled `totals.wins`/`losses` stay on the payload for old readers; the
screen does not render them). Under combinations only, it answers "at the
prices you paid, about N were expected to win; K did": N is the sum of the
entry prices (a 25c entry is a 25% chance by the price itself), recomputed
live from the rows every request -- never a stored constant -- and the range
is N plus or minus two standard deviations of that sum, `sqrt(sum p(1-p))`.
It is a statement about the price paid, never about skill or edge: it
carries no return or ROI figure and no word that grades the run. A cell
(overall or one price bucket) whose expected wins OR expected losses are
under 5 is `too_few` and carries no range -- the measurement rules' >= 5 each
side before a normal approximation may speak. Singles get counts only until
`SINGLES_SUMMARY_FLOOR` (30) computable bets exist, and past it the same
line, same rules. Rows that cannot carry it (a void, an unreadable or
out-of-range entry price) are counted in `excluded_from_expected`, never
zero-filled.

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
import math
import sqlite3
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from .analysis.clv import DEFAULT_HORIZON_HOURS
from .analysis.clv import clv_tenths as _clv_tenths
from .core.prices import format_price
from .estimates import classify_ticker
from .odds.timing import day_start_ms
from .pick_sources import (
    PICK_SOURCE_LABELS,
    PICK_SOURCES,
    UNTAGGED,
    open_combo_tickers,
    pick_source_payload,
    pick_sources_for,
)

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

# #161's two refusal reasons for `chance_when_priced`. Singles carry neither
# -- pinned to `None` alongside the chance itself, never one of these words.
CHANCE_REFUSAL_NO_FILL = "no_fill_row"
CHANCE_REFUSAL_NOT_PRICED = "not_priced_on_desk"


# #287: the thirty-scored-bets floor this module's docstrings have held since
# 21A, now a named constant. Below it a single-game section shows counts only.
SINGLES_SUMMARY_FLOOR = 30

# #287: a cell's normal approximation may speak only when it expects at least
# this many wins AND this many losses (CLAUDE.md measurement rules).
MIN_EXPECTED_EACH_SIDE = 5

# #287: price buckets for the expected-wins breakdown, in tenths of a cent of
# the price PAID (never a mid), half-open [low, high). Edges are plain
# round prices so the labels can be read aloud.
EXPECTED_BUCKETS: tuple[tuple[int, int, str], ...] = (
    (1, 100, "under 10c"),
    (100, 250, "10c to 25c"),
    (250, 500, "25c to 50c"),
    (500, 1000, "50c and up"),
)


def bet_kind(ticker: str) -> str:
    """`combo` for a multi-leg market, `single` otherwise, from the ticker.

    Delegates to `estimates.classify_ticker` so the `KXMVE` prefix is spelled
    in exactly one place in this repo; a second prefix check here would be
    the two-spellings defect CLAUDE.md records under the window banner.
    """
    _is_sports, _sport, is_multi_leg = classify_ticker(ticker)
    return KIND_COMBO if is_multi_leg else KIND_SINGLE


def _chance_when_priced_by_ticker(
    conn: sqlite3.Connection, tickers: list[str]
) -> dict[str, dict[str, Any]]:
    """The desk's chance for each combo ticker at the moment he priced it.

    One batched query over every ticker passed in, never one query per row
    (the ticket's own rule, matching the `totals`/`sections` whole-table
    discipline elsewhere in this module). For each ticker:

    - `anchor_ms` is `MIN(fills.filled_ms)` for that ticker, or `None` when
      `fills` holds no row for it (a fill was never recorded, so there is no
      instant to anchor a reading against).
    - `requested_ms`/`chance` come from the LATEST reading at or before the
      anchor across TWO sources (#163 -- #161 read only the first one and
      undercounted, since a KXMVE book is empty by design between RFQs, ADR
      0164, so most real lookups land `book_empty`, not `priced`):

        * `parlay_lookups` rows with `status IN ('priced', 'book_empty')`,
          a non-NULL `fair_joint_conservative`, and `minted_market_ticker =
          ticker`; `refused` and `error` stay out -- no market was minted
          (`refused`) or the read failed (`error`), so neither carries a
          chance to show him.
        * `combo_rfqs` rows with a non-NULL `fair_joint` and `ticker =
          ticker` -- a maker price-ask freezes the desk's chance the same
          way a lookup does. No `purpose` filter is needed: a sell-side
          (`'exit'`) ask fired after he already holds the position is
          necessarily after the fill, so the `requested_ms <= anchor_ms`
          bound already excludes it.

      Both arms require `requested_ms <= anchor_ms` in their own JOIN, so a
      reading taken after the anchor is excluded by construction, not
      filtered after the fact. The two arms are UNIONed with a
      `source_rank` (0 for `parlay_lookups`, 1 for `combo_rfqs`) and picked
      by `ROW_NUMBER() OVER (... ORDER BY requested_ms DESC, source_rank
      ASC, id DESC)` per ticker -- latest timestamp wins; on a tie at the
      same millisecond the `parlay_lookups` reading wins (deterministic,
      not because one source is more trustworthy); a further tie (same
      source, same millisecond) falls back to the row's own `id DESC`,
      mirroring `parlays.priced_lookup_for`'s own tiebreak (that function is
      read-only reference here; this module does not import it, since it
      answers "the newest priced lookup for a ticker" and this needs "the
      newest qualifying reading AT OR BEFORE an anchor across two tables", a
      different query).

    - `has_null_joint` (#168): whether a `parlay_lookups` row exists with
      `status IN ('priced', 'book_empty')`, `fair_joint_conservative IS
      NULL`, `minted_market_ticker = ticker`, and `requested_ms <=
      anchor_ms`. Such a row is written by the outside-parlay check (#166,
      `card_key = 'outside'`) when the desk looked at the parlay and could
      not produce one number for the whole thing -- a leg with no desk
      reading, or two legs on one game. It never enters `readings` (that
      CTE requires a non-NULL joint), so it can never win the latest-reading
      pick and can never suppress a real chance a later query might have
      shown; it is computed as a separate existence flag, checked only when
      `chance` came back `None`. A reading with a chance always wins.

    A ticker with no entry in the returned dict never occurs -- every ticker
    passed in gets a row, `chance` and `requested_ms` `None` when nothing
    qualified. Callers read `anchor_ms is None` as "no fill row" and
    `chance is None` (with `anchor_ms` present) as "not priced on the desk"
    -- refined further by `has_null_joint` into "checked, no chance for the
    whole parlay" vs plain "not priced on the desk".
    """
    if not tickers:
        return {}
    placeholders = ",".join("?" for _ in tickers)
    sql = f"""
        WITH anchors AS (
            SELECT ticker, MIN(filled_ms) AS anchor_ms
            FROM fills
            WHERE ticker IN ({placeholders})
            GROUP BY ticker
        ),
        readings AS (
            SELECT
                a.ticker AS ticker,
                l.requested_ms AS requested_ms,
                l.fair_joint_conservative AS chance,
                0 AS source_rank,
                l.id AS row_id
            FROM parlay_lookups l
            JOIN anchors a ON a.ticker = l.minted_market_ticker
            WHERE l.status IN ('priced', 'book_empty')
              AND l.fair_joint_conservative IS NOT NULL
              AND l.requested_ms <= a.anchor_ms
            UNION ALL
            SELECT
                a.ticker AS ticker,
                r.requested_ms AS requested_ms,
                r.fair_joint AS chance,
                1 AS source_rank,
                r.id AS row_id
            FROM combo_rfqs r
            JOIN anchors a ON a.ticker = r.ticker
            WHERE r.fair_joint IS NOT NULL
              AND r.requested_ms <= a.anchor_ms
        ),
        ranked AS (
            SELECT
                ticker,
                requested_ms,
                chance,
                ROW_NUMBER() OVER (
                    PARTITION BY ticker
                    ORDER BY requested_ms DESC, source_rank ASC, row_id DESC
                ) AS rn
            FROM readings
        ),
        null_joint AS (
            SELECT DISTINCT a.ticker AS ticker
            FROM parlay_lookups l
            JOIN anchors a ON a.ticker = l.minted_market_ticker
            WHERE l.status IN ('priced', 'book_empty')
              AND l.fair_joint_conservative IS NULL
              AND l.requested_ms <= a.anchor_ms
        )
        SELECT
            anchors.ticker AS ticker,
            anchors.anchor_ms AS anchor_ms,
            ranked.requested_ms AS requested_ms,
            ranked.chance AS chance,
            CASE WHEN null_joint.ticker IS NOT NULL THEN 1 ELSE 0 END
                AS has_null_joint
        FROM anchors
        LEFT JOIN ranked ON ranked.ticker = anchors.ticker AND ranked.rn = 1
        LEFT JOIN null_joint ON null_joint.ticker = anchors.ticker
    """
    out: dict[str, dict[str, Any]] = {
        ticker: {
            "anchor_ms": None, "requested_ms": None, "chance": None,
            "has_null_joint": False,
        }
        for ticker in tickers
    }
    for row in conn.execute(sql, tickers).fetchall():
        out[row["ticker"]] = {
            "anchor_ms": row["anchor_ms"],
            "requested_ms": row["requested_ms"],
            "chance": row["chance"],
            "has_null_joint": bool(row["has_null_joint"]),
        }
    return out


def _legs_by_ticker(
    conn: sqlite3.Connection, tickers: list[str]
) -> dict[str, list[dict[str, str]]]:
    """Each combo ticker's legs, in words, where they can be READ (#254).

    Two sources, tried in order, both keyed by the combo's own ticker:

    1. `parlay_position_legs` through `parlay_positions.combo_ticker` -- the
       legs Joe's recorded position carries (newest position for the ticker,
       `leg_index` order kept).
    2. `parlay_lookups.selected_legs` through `minted_market_ticker`, newest
       row that parses, read by `parlays.legs_for_position` (which returns
       `None`, never a shorter list, for an unreadable blob).

    **Never a guess.** A ticker appears in the result only when EVERY leg of
    its chosen source has a non-blank label that is not merely the leg's own
    market ticker (a pre-2026-09-09 lookup blob has no label and stands the
    ticker in; a ticker is not words). One unreadable leg drops the whole
    combination from the result -- a shorter list would read as the whole
    bet -- and the screen renders "Combination bet".

    Cost: two `IN (...)` reads bounded by the returned window (<= `limit`
    tickers), no per-row query. Neither `parlay_positions.combo_ticker` nor
    `parlay_lookups.minted_market_ticker` is indexed, so each read scans its
    table once; both are small beside `fills`/`venue_settlements`, and
    `_chance_when_priced_by_ticker` already scans `parlay_lookups` the same
    way on every request.
    """
    out: dict[str, list[dict[str, str]]] = {}
    if not tickers:
        return out
    marks = ",".join("?" for _ in tickers)

    def _readable(label: Any, ticker: Any) -> bool:
        return (
            isinstance(label, str)
            and label.strip() != ""
            and label.strip() != (ticker or "")
        )

    by_combo: dict[str, list[Any]] = {}
    for r in conn.execute(
        "SELECT p.combo_ticker AS combo, p.id AS pid, l.ticker AS ticker, "
        "l.side AS side, l.label AS label, l.outcome AS outcome "
        "FROM parlay_positions p "
        "JOIN parlay_position_legs l ON l.position_id = p.id "
        f"WHERE p.combo_ticker IN ({marks}) "
        "ORDER BY p.combo_ticker, p.id DESC, l.leg_index",
        tickers,
    ).fetchall():
        by_combo.setdefault(r["combo"], []).append(r)
    for combo, rows_ in by_combo.items():
        newest = rows_[0]["pid"]
        legs = [r for r in rows_ if r["pid"] == newest]
        if all(_readable(r["label"], r["ticker"]) for r in legs):
            out[combo] = [
                {
                    "label": r["label"].strip(),
                    "side": r["side"],
                    "ticker": r["ticker"],
                    "recorded_outcome": r["outcome"],
                }
                for r in legs
            ]

    missing = [t for t in tickers if t not in out]
    if missing:
        from .parlays import legs_for_position

        marks = ",".join("?" for _ in missing)
        seen: set[str] = set()
        for r in conn.execute(
            "SELECT minted_market_ticker AS combo, selected_legs "
            "FROM parlay_lookups "
            f"WHERE minted_market_ticker IN ({marks}) "
            "AND status IN ('priced', 'book_empty') "
            "ORDER BY requested_ms DESC, id DESC",
            missing,
        ).fetchall():
            if r["combo"] in seen:
                continue
            parsed = legs_for_position(r["selected_legs"])
            if parsed is None:
                continue
            # A missing label comes back as the leg's own ticker, which
            # `_readable` refuses, so the ticker-as-label case needs no
            # separate check on `labels_are_tickers`.
            if not all(_readable(g["label"], g["ticker"]) for g in parsed.legs):
                continue
            seen.add(r["combo"])
            out[r["combo"]] = [
                {
                    "label": str(leg["label"]).strip(),
                    "side": leg["side"],
                    "ticker": leg["ticker"],
                    "recorded_outcome": None,
                }
                for leg in parsed.legs
            ]
    return _with_leg_results(conn, out)


def leg_result(
    recorded_outcome: Optional[str], market_result: Optional[str], side: Any
) -> Optional[str]:
    """One leg's own result: "won" | "lost" | "void", or None when unread.

    #294. Two sources, both ALREADY on this instance -- nothing here asks
    Kalshi anything, so a page load never re-reads the venue:

    1. the desk's own record, `parlay_position_legs.outcome`, where it has
       left 'pending' (the `hedge` resolver wrote it once, from the venue or
       by hand; it is the only source that can say "void");
    2. `kalshi_markets.result`, which `market_results.py` writes once, at
       `finalized`, for every market discovery has seen -- compared with the
       leg's side exactly as `hedge.resolve_from_venue` does.

    **None is not "lost".** A leg whose market was never discovered, or
    whose result has not been read, is unread, and the screen says so.
    """
    if recorded_outcome in ("won", "lost", "void"):
        return recorded_outcome
    result = market_result.strip().lower() if isinstance(market_result, str) else ""
    if result not in ("yes", "no") or side not in ("yes", "no"):
        return None
    return "won" if result == side else "lost"


def _with_leg_results(
    conn: sqlite3.Connection, out: dict[str, list[dict[str, Any]]]
) -> dict[str, list[dict[str, Any]]]:
    """Attach `result` to every leg: one batched `kalshi_markets` read.

    Every leg gets the same key and the same vocabulary, so no leg is
    singled out on the payload (#294: no losing-leg highlight, no tally).
    """
    tickers = sorted({
        leg["ticker"] for legs in out.values() for leg in legs if leg.get("ticker")
    })
    results: dict[str, Any] = {}
    if tickers:
        marks = ",".join("?" for _ in tickers)
        results = {
            r["ticker"]: r["result"]
            for r in conn.execute(
                f"SELECT ticker, result FROM kalshi_markets WHERE ticker IN ({marks})",
                tickers,
            ).fetchall()
        }
    for legs in out.values():
        for leg in legs:
            leg["result"] = leg_result(
                leg.pop("recorded_outcome", None),
                results.get(leg.get("ticker")),
                leg["side"],
            )
    return out


def _titles_by_ticker(
    conn: sqlite3.Connection, tickers: list[str]
) -> dict[str, str]:
    """Kalshi's own market title for each single, where discovery holds one.

    One batched read over the returned window. A missing or blank title is
    simply absent (the screen then falls back to what the ticker says).
    """
    if not tickers:
        return {}
    marks = ",".join("?" for _ in tickers)
    return {
        r["ticker"]: r["title"].strip()
        for r in conn.execute(
            f"SELECT ticker, title FROM kalshi_markets WHERE ticker IN ({marks})",
            tickers,
        ).fetchall()
        if isinstance(r["title"], str) and r["title"].strip()
    }


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
# (`manual_order.py::_stamp_positions_read` logs the read and keeps no rows). The
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
# live, not hypothetical.** `manual_order.py::_stamp_positions_read` logs a
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


def expected_block(cells: list[tuple[int, bool]]) -> dict[str, Any]:
    """Expected wins at the prices paid, what happened, and a range.

    `cells` is one `(entry_price_tenths, won)` per bet, entry price in
    1..999. Expected wins = total of prices / 1000; variance = total of
    p(1 - p).
    The range is expected +/- 2 sd, rounded outward to whole bets and
    clamped to [0, n] -- about 19 runs in 20 land inside it IF the prices
    were fair. `too_few` (and no range) when expected wins or expected
    losses is under `MIN_EXPECTED_EACH_SIDE`.
    """
    n = len(cells)
    # Plain accumulation, not the builtin: `test_bets_chance_when_bought`
    # greps this file for the builtin's call token to police the chance
    # column, and a different quantity (entry prices) is added here.
    won = 0
    price_total = 0
    spread_total = 0
    for price, w in cells:
        won += 1 if w else 0
        price_total += price
        spread_total += price * (1000 - price)
    expected = price_total / 1000
    block: dict[str, Any] = {
        "n": n,
        "won": won,
        "expected": round(expected, 1),
        "too_few": True,
        "range_low": None,
        "range_high": None,
    }
    if expected >= MIN_EXPECTED_EACH_SIDE and n - expected >= MIN_EXPECTED_EACH_SIDE:
        variance = spread_total / 1_000_000
        sd = variance ** 0.5
        block["too_few"] = False
        block["range_low"] = max(0, math.floor(expected - 2 * sd))
        block["range_high"] = min(n, math.ceil(expected + 2 * sd))
    return block


def _expected_summary(cells: list[tuple[int, bool]]) -> dict[str, Any]:
    """The overall block plus one block per price bucket (empty ones kept,
    so the screen's rows do not move with the data)."""
    return {
        **expected_block(cells),
        "buckets": [
            {
                "label": label,
                **expected_block([c for c in cells if low <= c[0] < high]),
            }
            for low, high, label in EXPECTED_BUCKETS
        ],
    }


def bets_summary(
    wins_losses: dict[str, tuple[int, int]],
    cells: dict[str, list[tuple[int, bool]]],
    excluded: dict[str, int],
) -> dict[str, dict[str, Any]]:
    """Per-kind W/L and the expected-at-the-price line. Never pooled: the
    returned dict has exactly the two kinds and nothing that spans them.
    Combinations always carry the line; singles only from the floor."""
    out: dict[str, dict[str, Any]] = {}
    for kind in (KIND_SINGLE, KIND_COMBO):
        wins, losses = wins_losses[kind]
        computable = wins + losses
        meets_floor = kind == KIND_COMBO or computable >= SINGLES_SUMMARY_FLOOR
        out[kind] = {
            "wins": wins,
            "losses": losses,
            "computable": computable,
            "floor": SINGLES_SUMMARY_FLOOR if kind == KIND_SINGLE else None,
            "counts_only": not meets_floor,
            "excluded_from_expected": excluded[kind],
            "expected": _expected_summary(cells[kind]) if meets_floor else None,
        }
    return out


def by_source_summary(
    rows: list[tuple[str, Optional[str], bool, Optional[int]]],
) -> dict[str, list[dict[str, Any]]]:
    """Per kind, one block per pick source Joe tagged (v63), in the FIXED
    order of `PICK_SOURCES` with `untagged` last -- never sorted by any
    result, because an ordering is a claim (ADR 0071 §2.5).

    `rows` is one `(kind, source_or_None, won, entry_price_tenths)` per
    computable settled bet. A source with no settled bet of that kind is
    left out rather than shown as zeros. Combinations carry the
    expected-vs-won line (`expected_block`, so `too_few` and no range below
    5 expected each side); singles carry it only once that source alone
    reaches `SINGLES_SUMMARY_FLOOR`, the kinds' own rule. Never pooled
    across kinds, and no rate is computed.
    """
    order = (*PICK_SOURCES, UNTAGGED)
    out: dict[str, list[dict[str, Any]]] = {}
    for kind in (KIND_SINGLE, KIND_COMBO):
        blocks: list[dict[str, Any]] = []
        for source in order:
            mine = [
                r for r in rows
                if r[0] == kind and (r[1] or UNTAGGED) == source
            ]
            if not mine:
                continue
            wins = 0
            for r in mine:
                wins += 1 if r[2] else 0
            cells = [
                (r[3], r[2]) for r in mine
                if isinstance(r[3], int) and 1 <= r[3] <= 999
            ]
            speaks = kind == KIND_COMBO or len(mine) >= SINGLES_SUMMARY_FLOOR
            blocks.append({
                "source": source,
                "label": PICK_SOURCE_LABELS.get(source, "Not tagged yet"),
                "wins": wins,
                "losses": len(mine) - wins,
                "expected": expected_block(cells) if speaks else None,
            })
        out[kind] = blocks
    return out


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

    # #161: one batched read for every combo ticker on the WHOLE table,
    # never one query per row -- the same discipline `totals`/`sections`
    # already hold this module to.
    combo_tickers = sorted({
        row["ticker"] for row in rows if bet_kind(row["ticker"]) == KIND_COMBO
    })
    chance_by_ticker = _chance_when_priced_by_ticker(conn, combo_tickers)
    # #254: legs in words and single titles, bounded by the returned window.
    window = rows[:limit]
    legs_by_ticker = _legs_by_ticker(
        conn,
        sorted({r["ticker"] for r in window if bet_kind(r["ticker"]) == KIND_COMBO}),
    )
    titles_by_ticker = _titles_by_ticker(
        conn,
        sorted({r["ticker"] for r in window if bet_kind(r["ticker"]) == KIND_SINGLE}),
    )

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
    # `chance_carried` is #161's coverage COUNT -- rows with a non-None
    # `chance_when_priced` -- never a sum or an average of the values it
    # counts; it sits on both blocks for a uniform shape but is only ever
    # incremented on the combo section, since a single carries no chance.
    sections: dict[str, dict[str, int]] = {
        kind: {
            "total": 0, "net_tenths": 0, "computable": 0, "uncomputable": 0,
            "chance_carried": 0,
        }
        for kind in (KIND_SINGLE, KIND_COMBO)
    }
    # #287: per-kind W/L and the (price paid, won) cells behind the expected
    # line, over the WHOLE table. Rows that cannot carry a probability are
    # counted in `expected_excluded`, never zero-filled.
    kind_wl = {KIND_SINGLE: [0, 0], KIND_COMBO: [0, 0]}
    expected_cells: dict[str, list[tuple[int, bool]]] = {
        KIND_SINGLE: [], KIND_COMBO: [],
    }
    expected_excluded = {KIND_SINGLE: 0, KIND_COMBO: 0}
    first_settled_ms: Optional[int] = None
    # v63: Joe's own tag per ticker, over the WHOLE table like `totals`.
    tags = pick_sources_for(conn, [r["ticker"] for r in rows])
    source_rows: list[tuple[str, Optional[str], bool, Optional[int]]] = []
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
                kind_wl[kind][0] += 1
            else:
                losses += 1
                kind_wl[kind][1] += 1
            price = row["entry_price_tenths"]
            source_rows.append(
                (kind, tags.get(row["ticker"]), bool(won), price)
            )
            if isinstance(price, int) and 1 <= price <= 999:
                expected_cells[kind].append((price, bool(won)))
            else:
                expected_excluded[kind] += 1
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
        # #161: the desk's chance for a combo at the moment it was priced.
        # Singles carry all three keys as `None` -- pinned, per the ticket,
        # rather than omitted -- so the frontend type need not special-case
        # a missing key. #168 adds a fourth, `checked_without_chance`: pinned
        # `False` (never `None`) for a single, since it is a plain fact ("was
        # this ticker checked and refused a joint chance") rather than one of
        # the three chance fields, and a single is never checked this way at
        # all.
        chance_when_priced: Optional[float] = None
        chance_priced_before_fill_ms: Optional[int] = None
        chance_refusal_reason: Optional[str] = None
        checked_without_chance = False
        if kind == KIND_COMBO:
            info = chance_by_ticker.get(row["ticker"])
            if info is None or info["anchor_ms"] is None:
                chance_refusal_reason = CHANCE_REFUSAL_NO_FILL
            elif info["chance"] is None:
                chance_refusal_reason = CHANCE_REFUSAL_NOT_PRICED
                # #168: a reading with a chance always wins over this flag --
                # it is only ever considered once `chance` itself came back
                # `None`. `has_null_joint` is an EXISTENCE check ("was there
                # ever a qualifying check with no joint"), independent of
                # which reading `readings`/`ranked` picked, since a NULL
                # joint never enters that CTE and so never wins the
                # latest-reading tiebreak.
                checked_without_chance = bool(info["has_null_joint"])
            else:
                chance_when_priced = info["chance"]
                chance_priced_before_fill_ms = (
                    info["anchor_ms"] - info["requested_ms"]
                )
                section["chance_carried"] += 1
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
                "chance_when_priced": chance_when_priced,
                "chance_priced_before_fill_ms": chance_priced_before_fill_ms,
                "chance_refusal_reason": chance_refusal_reason,
                "checked_without_chance": checked_without_chance,
                # #254: a combination's legs in words (None when any leg is
                # unreadable -- never a partial list) and a single's title.
                "legs": (
                    legs_by_ticker.get(row["ticker"])
                    if kind == KIND_COMBO else None
                ),
                "market_title": (
                    titles_by_ticker.get(row["ticker"])
                    if kind == KIND_SINGLE else None
                ),
                # v63: Joe's tag, None when untagged -- never `own`.
                "pick_source": tags.get(row["ticker"]),
            }
        )
    record: dict[str, Any] = {
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
    # #287: an empty mirror has nothing to summarise, so the key is absent
    # rather than a block of zeros (a zero would be a claim).
    if rows:
        record["summary"] = bets_summary(
            {k: (v[0], v[1]) for k, v in kind_wl.items()},
            expected_cells,
            expected_excluded,
        )
        record["by_source"] = by_source_summary(source_rows)
    # v63: what the chips need, for the settled window AND every open
    # recorded combination (the Open section above the settled list).
    record["pick_sources"] = pick_source_payload(
        conn, [b["ticker"] for b in bets] + open_combo_tickers(conn)
    )
    return record


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
      writer: `manual_order.py::_stamp_positions_read` logs the hand-bet path's own
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
