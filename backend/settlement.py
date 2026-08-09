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

from .store.orders import TERMINAL_STATUSES

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
    *, side: str, count: int, price_tenths: int, result: str
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

    fee_cents = calculate_fee_cents(price_tenths, count)
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


def settle_position(conn, row: dict, outcome: MarketOutcome, *, pnl_cents: int) -> None:
    """Write one settlement. Raises rather than swallowing a failed insert."""
    conn.execute(
        """
        INSERT INTO settlements (
            order_id, ticker, settled_ms, result, contracts, pnl_cents,
            dry_run, fill_assumption, depth_at_order
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        ),
    )
    conn.commit()


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

    for row in open_positions:
        outcome = outcomes.get(row["ticker"])
        if outcome is None:
            counts.still_unresolved += 1
            continue

        pnl = position_pnl_cents(
            side=row["side"],
            count=int(row["assumed_filled_count"] or row["count"]),
            price_tenths=int(row["limit_price_tenths"]),
            result=outcome.result,
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
            settle_position(conn, row, outcome, pnl_cents=pnl)
        except Exception as exc:                              # noqa: BLE001
            counts.errors.append(f"order {row['id']}: {exc}")
            logger.exception("could not write the settlement for order %s", row["id"])
            continue
        counts.settled += 1

    logger.info("settlement pass: %s", counts.as_dict())
    return counts
