"""Closing paper positions against Kalshi's own settlement result.

Sibling of `backend/scoring.py`: both read a finished market off the exchange
and write what they learn into the record. This one answers *"did the position
close, and for how much"*; that one answers *"did we beat the closing line"*.
They are deliberately separate, and the reason is the section below.

What paper P&L does NOT establish
---------------------------------
**It is not evidence that this strategy has an edge, and it must never be used
as though it were.** The gate is built entirely on CLV. Three independent
reasons, any one of which is sufficient:

1. **It is contaminated by an assumption CLV does not make.** Every fill here is
   assumed (`store.orders.DEPTH_CAPPED_TAKER`), and the assumption is optimistic
   in the correlated direction: a real order fails to fill when the maker pulls,
   which is when the price was about to move, which is when the bet was good.
   CLV scores every recommendation whether or not it was bet, so it does not
   care whether a fill was real.
2. **It is the wrong statistic for the sample.** P&L is a win-rate measurement
   and needs on the order of a thousand observations; CLV needs ~300. A paper
   P&L that looks decisive at n=40 is noise wearing a dollar sign.
3. **It has none of the noise machinery.** No clustering by game, no
   always-valid bound, and it is not counted in
   `mart_multiple_comparisons`. The CLV path has all three because each was
   added after a specific way of being wrong.

The danger is not that this number is wrong. It is that it is *easier to read*
than the number beside it, and this repo has already recorded what happens when
a correct statistic sits next to a more legible contradicting one -- the legible
one is what gets acted on. So `gate.py` does not read `settlements`, and a test
asserts that rather than trusting anyone to remember.

What it IS for: releasing exposure, so `max_exposure_dollars` can bind on paper
before it ever guards real money; and catching gross errors -- an inverted side,
a mis-mapped result -- that CLV would take far longer to surface.

Reading the outcome
-------------------
Every field name and value here comes from `tests/fixtures/markets_settled.json`,
44 real markets captured before this module was written. Three of them would
have been got wrong by reasoning:

- **The query filter and the status field use different words.** `GET
  /markets?status=settled` returns markets whose `status` reads `finalized`, and
  `finalized` is rejected as a filter with HTTP 400. Matching `== "settled"`
  here would settle nothing, forever, and report it as "nothing has settled
  yet" -- which is also what a correct pass says on a quiet day.
- **`closed` is a durable third state**, not a step on the way. Two markets in
  the capture closed 2026-02-03 and still carry no result. Game over is not
  outcome known.
- **`result` is `""` when unknown, not null**, so `if not result` reads an
  active market as a settled one.

Anything unrecognised refuses and is counted. An unfamiliar `status` is exactly
the case the first finding proves this API can produce.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .core.fees import calculate_fee_cents

from .odds.timing import DEFAULT_DAY_START_UTC_HOUR, day_start_ms
from .store.orders import TERMINAL_STATUSES, exposure_contribution

logger = logging.getLogger(__name__)

# The only `status` that means the outcome is known. Measured, not documented:
# 42 of 42 markets returned by `status=settled` report `finalized`.
SETTLED_STATUS = "finalized"

# Statuses seen in the capture that mean "not yet". Listed explicitly so an
# unrecognised one is a refusal rather than falling into this branch -- the
# vocabulary here has already been shown to differ from the filter's.
UNRESOLVED_STATUSES = frozenset({"active", "closed", "initialized", "determined"})

# The two values `result` takes once known.
RESULTS = frozenset({"yes", "no"})

# `settlement_value_dollars` as it appears beside each result. The payload states
# the outcome twice and the two are cross-checked, because it costs nothing and
# it is the only independent reading available.
SETTLEMENT_VALUE = {"yes": "1.0000", "no": "0.0000"}


class SettlementRefused(Exception):
    """The payload could not be read as an outcome, so nothing was written.

    A refusal, never a default. Resolving an unreadable settlement would write a
    win or a loss that Kalshi did not report -- and unlike an unreadable price,
    which stops an order, an unreadable outcome would enter the permanent record.
    """


@dataclass(frozen=True)
class MarketOutcome:
    ticker: str
    result: str
    settled_ms: int


@dataclass
class SettlementCounts:
    positions_open: int = 0
    markets_queried: int = 0
    settled: int = 0
    still_unresolved: int = 0
    refused: int = 0
    # Positions whose P&L is not a whole number of cents. Only reachable on a
    # sub-cent price grid; see `position_pnl_cents`.
    skipped_sub_cent: int = 0
    errors: list[str] = field(default_factory=list)

    # Always reported, even at zero, for the reason `ScoringCounts` gives: a
    # pass that settled nothing and a pass that found nothing to settle need
    # different responses, and `settled: 0` alone cannot tell them apart.
    # `refused` is here because it is the number that means the wire format
    # moved, and that must never be invisible because it happens to be zero.
    ALWAYS_REPORT = (
        "positions_open",
        "settled",
        "still_unresolved",
        "refused",
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            k: v
            for k, v in self.__dict__.items()
            if v or k in self.ALWAYS_REPORT
        }


def _parse_ts(value: Any) -> Optional[int]:
    """Kalshi's ISO-8601 `settlement_ts` -> epoch ms, or `None`."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return int(
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            .astimezone(timezone.utc)
            .timestamp()
            * 1000
        )
    except ValueError:
        return None


def read_outcome(payload: dict) -> Optional[MarketOutcome]:
    """`GET /markets/{ticker}` -> an outcome, `None` if not settled yet.

    Raises `SettlementRefused` for every state that is neither. The three-way
    split is the point: "settled", "not yet", and "this payload does not mean
    what I expect" need different responses, and collapsing the third into
    either of the others is how a wire-format change becomes a silent wrong
    answer in a permanent record.
    """
    market = payload.get("market") if isinstance(payload.get("market"), dict) else payload
    ticker = market.get("ticker")
    if not ticker:
        raise SettlementRefused("payload carries no ticker")

    status = market.get("status")
    result = market.get("result")

    if status in UNRESOLVED_STATUSES:
        # `closed` lands here as well as `active`. A closed market whose result
        # has not been published is not a loss, and two in the capture have sat
        # that way for six months.
        if result in RESULTS:
            raise SettlementRefused(
                f"{ticker} is {status!r} but already carries result {result!r}. "
                f"Refusing: the two disagree about whether the outcome is known."
            )
        return None

    if status != SETTLED_STATUS:
        raise SettlementRefused(
            f"{ticker} has unrecognised status {status!r}. Refusing rather than "
            f"guessing -- this API returns 'finalized' for a filter spelled "
            f"'settled', so its vocabulary is not inferable."
        )

    if result not in RESULTS:
        raise SettlementRefused(
            f"{ticker} is {SETTLED_STATUS} but its result is {result!r}, which "
            f"is not one of {sorted(RESULTS)}. An unreadable outcome must not "
            f"resolve to a loss."
        )

    # Free cross-check. The payload states the outcome twice; if the two ever
    # disagree, one of them is being misread and neither should be trusted.
    value = market.get("settlement_value_dollars")
    if value is not None and value != SETTLEMENT_VALUE[result]:
        raise SettlementRefused(
            f"{ticker} reports result {result!r} against "
            f"settlement_value_dollars {value!r}, which should be "
            f"{SETTLEMENT_VALUE[result]!r}. The payload contradicts itself."
        )

    settled_ms = _parse_ts(market.get("settlement_ts"))
    if settled_ms is None:
        raise SettlementRefused(
            f"{ticker} is {SETTLED_STATUS} with result {result!r} but no "
            f"readable settlement_ts. Refusing rather than substituting "
            f"close_time or expiration_time -- the latter sat three days past "
            f"close on the captured sample, so it is not a settlement instant."
        )

    return MarketOutcome(ticker=ticker, result=result, settled_ms=settled_ms)


def position_pnl_cents(
    *,
    side: str,
    count: int,
    price_tenths: int,
    result: str,
    fee_multiplier: float = 1.0,
) -> Optional[int]:
    """Realised P&L for one settled position, in whole cents, net of fee.

    `None` when the answer is not a whole number of cents, which is reachable
    only on a sub-cent price grid. It is a refusal rather than a rounding: the
    column is integer cents and `CLAUDE.md` puts the whole risk path in tenths
    precisely because half a cent is half the edge being hunted. Rounding here
    would be a silent, biased error in the permanent record; refusing leaves the
    position open, which is visible and safe.

    Measured cost of that refusal today: **zero**. All 1,426 game markets walked
    on 2026-08-08 are `linear_cent`, so every price is a whole cent and the
    division is exact. It is stated as a measurement rather than assumed --
    a market's grid can change while it is open.

    One fee, not a round trip: a bet held to settlement pays only the entry fee.
    """
    won = side == result
    # Tenths of a cent throughout, per the money convention. A winning contract
    # returns 1000 and cost `price_tenths`; a losing one returns nothing.
    gross_tenths = count * (1000 - price_tenths) if won else -count * price_tenths
    if gross_tenths % 10:
        return None

    # ADR 0058: `fee_multiplier` is the venue's own per-series field, passed
    # only by the settlement pass -- the RECORD path. Guards never reach this
    # function, so the per-series rate cannot leak into a decision from here.
    fee_cents = calculate_fee_cents(price_tenths, count, fee_multiplier=fee_multiplier)
    if fee_cents is None:
        # An untradeable price has no defined fee, and a zero there would
        # overstate the result. Same refusal as `calculate_fee`'s own.
        return None
    return gross_tenths // 10 - fee_cents


def positions_awaiting_settlement(conn) -> list[dict[str, Any]]:
    """Orders that still hold capital and have no settlement row.

    The status filter is the exposure query's, by construction rather than by
    copy: a position is worth settling exactly when it is still counted, so the
    two must not be able to disagree about which orders those are.
    """
    placeholders = ", ".join("?" for _ in TERMINAL_STATUSES)
    rows = conn.execute(
        f"""
        SELECT o.id, o.ticker, o.side, o.count, o.limit_price_tenths,
               o.dry_run, o.fill_assumption, o.assumed_filled_count,
               o.response_body_json
        FROM orders o
        WHERE o.status NOT IN ({placeholders})
          AND NOT EXISTS (SELECT 1 FROM settlements s WHERE s.order_id = o.id)
        ORDER BY o.id
        """,
        TERMINAL_STATUSES,
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Reading the risk state back out
# ---------------------------------------------------------------------------
# `settle_position` above has written `settlements.pnl_cents` since ADR 0010 and
# **nothing summed it**. The two readers were `analysis/clv.py` and
# `analysis/validate.py`, both reporting after the fact; there was no `SUM` of
# that column anywhere in the repo. So `size_position`'s daily-loss kill switch
# -- correct code, tested at the boundary -- ran against a keyword argument
# whose default was `0.0` and which no production caller ever supplied. Measured
# 2026-08-10 by instrumenting the sizer across the whole suite: 1,358 calls, of
# which exactly one carried a non-zero `daily_pnl_dollars` and it came from a
# test. Driven end to end, `POST /api/orders` returned HTTP 200 on an account
# carrying 40 settled positions and -$20,000 of realised loss.
#
# The fix is a query, not new instrumentation. These are it.


def risk_day_start_ms(
    now_ms: int, *, hour: int = DEFAULT_DAY_START_UTC_HOUR
) -> int:
    """Start of the **risk** day containing `now_ms`.

    Deliberately `odds.timing.day_start_ms`, at the same 10:00Z roll as the odds
    budget, rather than UTC midnight. Two reasons, and the first is the one that
    decides it:

    **UTC midnight is 8pm ET, which is the middle of the US evening slate.** A
    loss limit that rolls there hands back a fresh allowance halfway through the
    session it exists to stop -- the kill switch disengages at the exact moment
    a bad night is still running. That is the maximally permissive failure, and
    it is the same argument `timing.DEFAULT_DAY_START_UTC_HOUR` already makes
    for the odds budget: 10:00Z is 6am ET / 3am PT, after even a West Coast
    extra-innings game has settled, so one night's losses stay in one bucket.

    **One definition of "day" in the repo.** `tasks/lessons.md`, 2026-08-07:
    two limits on one quantity, in modules that do not import each other, drift
    apart and the looser one wins in silence. A risk day and a budget day that
    disagreed by ten hours would put "how much have I lost today" and "how much
    have I spent today" on different clocks, and the screens that show them side
    by side would be quietly comparing different days.

    The hour is a parameter rather than a constant read here so a caller holding
    `OddsConfig.budget_day_start_utc_hour` can pass the *configured* value and
    the two cannot diverge through `.env`.

    **What this does not establish:** that 10:00Z is the right roll for a bettor
    in another timezone. It is right for the US sports calendar this tool trades
    and nothing else; it is one `ODDS_BUDGET_DAY_START_UTC_HOUR` away from being
    wrong for anyone else.
    """
    return day_start_ms(now_ms, hour=hour)


def daily_realised_pnl_dollars(
    conn,
    *,
    now_ms: int,
    dry_run: bool,
    day_start_hour: int = DEFAULT_DAY_START_UTC_HOUR,
) -> Optional[float]:
    """Realised P&L for the risk day, in dollars. Negative is a loss.

    `None`, never `0.0`, when it cannot be read. `CLAUDE.md`: *unreadable
    resolves to `None`, never `0`* -- and on a loss limit, `0.0` is the
    maximally permissive substitution available, because "no information" would
    read as "no losses" and the kill switch would never engage.

    An **empty** `settlements` table is not unreadable. Nothing has settled, so
    the realised P&L for the day genuinely is $0.00, and that is a measurement
    rather than an absence. The two are told apart here the way
    `current_exposure_dollars` tells them apart: a query that returns no rows is
    zero, a query that raises is `None`.

    **`dry_run` selects the population and the two are never pooled**, for the
    reason `store.orders.current_exposure_dollars` gives: a paper order sizes
    against paper history, a live order against live history. Pooling them would
    let fictional losses stop a real bet, or -- far worse -- let a fictional
    profit offset a real loss and hold the kill switch open.

    Sums the column rather than recomputing the arithmetic.
    `position_pnl_cents` already refused any position whose P&L is not a whole
    number of cents, so every row present here is exact and integer; dividing by
    100 at the end is the only float in the path.
    """
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(pnl_cents), 0) AS cents, COUNT(*) AS n "
            "FROM settlements WHERE dry_run = ? AND settled_ms >= ?",
            (1 if dry_run else 0, risk_day_start_ms(now_ms, hour=day_start_hour)),
        ).fetchone()
    except Exception:                                       # noqa: BLE001
        logger.exception("could not read the day's realised P&L")
        return None
    if row is None:
        # A `SELECT SUM(...)` always returns one row, so this is unreachable
        # through sqlite3 -- but a stub connection in a test is not sqlite3, and
        # "the reader returned nothing" must not become "$0.00 lost today".
        logger.error("the realised-P&L query returned no row at all")
        return None
    return int(row["cents"]) / 100.0


def open_position_dollars(conn, ticker: str, *, dry_run: bool) -> Optional[float]:
    """Money currently committed to **one** ticker, fee included, or `None`.

    The per-market twin of `store.orders.current_exposure_dollars`, and the
    input `size_position`'s `max_position_dollars` cap was missing. Measured
    consequence of its absence: 76 contracts and ~$38.00 accumulated on a single
    ticker against a $10 `max_position_dollars`, stopped only when the $40
    portfolio-wide `max_exposure_dollars` finally bound.

    **Built on `positions_awaiting_settlement` rather than on a second query**,
    which is the point. That function already returns exactly the orders that
    still hold capital, and its status filter is the exposure query's *by
    construction* -- so "which orders count towards the position cap" and "which
    orders count towards the exposure cap" cannot come to disagree, which is the
    failure `current_exposure_dollars` was written to end. The dollar value of
    each row comes from `exposure_contribution`, the project's only arithmetic
    for what an open order commits.

    `None` if any contributing row is unreadable, for the reason the portfolio
    sum gives: skipping it would report a smaller position than the truth and
    hand the next order room it does not have.
    """
    try:
        rows = positions_awaiting_settlement(conn)
    except Exception:                                       # noqa: BLE001
        logger.exception("could not read the open positions for %s", ticker)
        return None

    total = 0.0
    for row in rows:
        if row["ticker"] != ticker or bool(row["dry_run"]) != dry_run:
            continue
        contribution = exposure_contribution(row["count"], row["limit_price_tenths"])
        if contribution is None:
            logger.error(
                "order %s on %s has no usable price, so the position on that "
                "ticker cannot be summed. Refusing rather than treating an "
                "unreadable order as a free position.",
                row["id"], ticker,
            )
            return None
        total += contribution
    return total


def _depth_at_order(row: dict) -> Optional[float]:
    """The resting size that justified assuming the fill, if it was recorded.

    Recovered from the stored response rather than a column of its own, because
    the response is already kept verbatim and a second copy could drift from it.
    `None` when absent, which is honest -- an order placed before the response
    was stored has no observed depth, and inventing one would be inventing the
    evidence for the fill assumption.
    """
    raw = row.get("response_body_json")
    if not raw:
        return None
    try:
        depth = json.loads(raw).get("quote", {}).get("depth_at_ask")
    except (ValueError, AttributeError):
        return None
    return float(depth) if isinstance(depth, (int, float)) else None


def settle_position(
    conn,
    row: dict,
    outcome: MarketOutcome,
    *,
    pnl_cents: int,
    fee_model_used: Optional[str] = None,
) -> None:
    """Write one settlement. Raises rather than swallowing a failed insert.

    `fee_model_used` is ADR 0058's basis marker: which fee model computed the
    `pnl_cents` being written. NULL on every row written before the marker
    existed -- the honest value, and the boundary a cross-regime comparison
    must respect.
    """
    conn.execute(
        """
        INSERT INTO settlements (
            order_id, ticker, settled_ms, result, contracts, pnl_cents,
            dry_run, fill_assumption, depth_at_order, fee_model_used
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(row["id"]),
            row["ticker"],
            int(outcome.settled_ms),
            outcome.result,
            # The assumed count, not the ordered count. They are equal under the
            # only policy that exists, and reading the wrong one would be
            # invisible until the day they differ.
            int(row["assumed_filled_count"] or row["count"]),
            int(pnl_cents),
            int(row["dry_run"]),
            row["fill_assumption"],
            _depth_at_order(row),
            fee_model_used,
        ),
    )
    conn.commit()


def read_series_fee_multiplier(payload: dict) -> Optional[float]:
    """The venue's `fee_multiplier` off one `/series/{ticker}` payload.

    `None` on anything but a finite number in (0, 1] -- absent, unparseable,
    or outside the range the venue has ever published. Callers fall back to
    the flat model and SAY SO in `fee_model_used`, per the module rule that
    unreadable never resolves to a value.
    """
    block = payload.get("series", payload)
    value = block.get("fee_multiplier")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not 0 < float(value) <= 1:
        return None
    return float(value)


async def run_settlement_pass(conn, kalshi_client) -> SettlementCounts:
    """Close every open position whose market has settled.

    One `GET /markets/{ticker}` per distinct open ticker. Kalshi REST is
    unmetered and this spends no odds credits.

    **Takes no clock**, unlike every other pass in this project, and that is
    deliberate rather than an omission: the settlement instant is Kalshi's
    `settlement_ts`, observed. A `now` parameter here would be an invitation to
    stamp a row with our own time when the exchange's could not be read, which
    is the substitution `read_outcome` refuses.

    A failure on one market is recorded and the pass continues, for the reason
    the scoring pass gives: one market whose payload cannot be read must not
    stop the other thirty from closing, because a position left open holds
    exposure and looks identical to one nobody looked at.
    """
    counts = SettlementCounts()

    open_positions = positions_awaiting_settlement(conn)
    counts.positions_open = len(open_positions)
    if not open_positions:
        logger.info("settlement pass: %s", counts.as_dict())
        return counts

    # One request per ticker, not per position. Two positions on one market
    # share an outcome, and asking twice would invite them to disagree.
    outcomes: dict[str, Optional[MarketOutcome]] = {}
    for ticker in dict.fromkeys(p["ticker"] for p in open_positions):
        try:
            payload = await kalshi_client.get(f"/markets/{ticker}")
            counts.markets_queried += 1
            outcomes[ticker] = read_outcome(payload)
        except SettlementRefused as exc:
            counts.refused += 1
            counts.errors.append(f"{ticker}: {exc}")
            logger.error("settlement refused for %s: %s", ticker, exc)
        except Exception as exc:                              # noqa: BLE001
            counts.errors.append(f"{ticker}: {exc}")
            logger.warning("could not read %s for settlement: %s", ticker, exc)

    # ADR 0058: the venue's own per-series `fee_multiplier`, one unmetered
    # GET per distinct series per pass, read at settlement time rather than
    # cached across days because the schedule has changed before. A failed or
    # unreadable fetch falls back to the flat model AND SAYS SO in the row's
    # `fee_model_used` -- the record never guesses silently. The event-level
    # `fee_multiplier_override` (ADR 0058 hole 2) is NOT consulted here, and
    # the tag says that too.
    multipliers: dict[str, Optional[float]] = {}
    for series in dict.fromkeys(
        p["ticker"].split("-")[0] for p in open_positions
    ):
        try:
            payload = await kalshi_client.get(f"/series/{series}")
            multipliers[series] = read_series_fee_multiplier(payload)
        except Exception as exc:                              # noqa: BLE001
            multipliers[series] = None
            logger.warning("could not read /series/%s: %s", series, exc)

    for row in open_positions:
        outcome = outcomes.get(row["ticker"])
        if outcome is None:
            counts.still_unresolved += 1
            continue

        multiplier = multipliers.get(row["ticker"].split("-")[0])
        if multiplier is None:
            fee_multiplier = 1.0
            fee_model_used = "flat_0.070:series_unread"
        else:
            fee_multiplier = multiplier
            fee_model_used = f"series_mult_{multiplier:g}:override_unchecked"

        pnl = position_pnl_cents(
            side=row["side"],
            count=int(row["assumed_filled_count"] or row["count"]),
            price_tenths=int(row["limit_price_tenths"]),
            result=outcome.result,
            fee_multiplier=fee_multiplier,
        )
        if pnl is None:
            counts.skipped_sub_cent += 1
            logger.error(
                "order %s on %s settles to a P&L that is not a whole number of "
                "cents. Left open rather than rounded.",
                row["id"], row["ticker"],
            )
            continue

        try:
            settle_position(
                conn, row, outcome, pnl_cents=pnl, fee_model_used=fee_model_used
            )
        except Exception as exc:                              # noqa: BLE001
            counts.errors.append(f"order {row['id']}: {exc}")
            logger.exception("could not write the settlement for order %s", row["id"])
            continue
        counts.settled += 1

    logger.info("settlement pass: %s", counts.as_dict())
    return counts
