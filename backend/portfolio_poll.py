"""Mirror the venue's record of Joe's hand-placed bets, before Kalshi drops it.

Why this exists, and why it is urgent rather than nice
------------------------------------------------------
Both portfolio endpoints have now been observed to lose history.
`/portfolio/fills` retains roughly three months (measured 2026-08-10: empty on
an account whose settlements then reached back to 2025-11). And
`/portfolio/settlements` -- which the calibration registration originally
called "the safety net" at nine-plus months of reach -- returned 55 records on
2026-08-10 and **22 entirely different ones eight days later**, cursor empty,
one page. A poll that does not happen does not delay the record. It loses it.

This module is the first production caller of any portfolio endpoint in this
project's life. `balance()`, `positions()`, `fills()` and `settlements()` were
all built, tested against their envelopes, and called by nothing -- the
"built but never called" pattern `tasks/lessons.md` records. The calibration
registration (§7.6, as amended) is what finally supplies a caller.

What it writes, and what it refuses to write
--------------------------------------------
- `venue_settlements` -- one row per settled position, mirrored verbatim-ish:
  parsed into the repo's units, never summarised. `INSERT OR IGNORE` on the
  `(ticker, settled_ms)` key makes every poll idempotent.
- `fills` with `source = 'venue_hand'` -- **never** `'engine'`. The gate's
  `_fee_model_verified` counts engine fills only (ADR 0043), and that filter
  landed before this module existed precisely so switching this on cannot move
  a live-trading interlock in either direction.
- `venue_balance_snapshots` -- from `balance_dollars` (a dollar string,
  "20.6583"), **never** the `balance` integer beside it, which is whole cents
  and drops the 0.83c. Observed 2026-08-18, both fields side by side.
- `poll_log` -- one row per endpoint per attempt, **including failures**. Every
  retention tripwire in the registration is a gap between successive
  successful polls, and a failure that writes nothing is invisible: it reads
  exactly like a quiet week in which nothing was bet.

**`positions` is counted and not parsed.** The per-row shape has never been
observed on this account -- both reads returned an empty list -- and this repo
has been burned five separate times by parsers written against imagined wire
formats. The count lands in `poll_log.row_count`; the first non-empty payload
should be captured (`scripts/capture_fills_fixture.py` is the pattern) before
anyone writes a parser.

What this does NOT establish
-----------------------------
- **That the mirror is complete.** A position opened and closed entirely
  between polls, on an endpoint that drops history, is gone. The poll cadence
  bounds that window; it cannot close it.
- **That the fee model is right.** Since 2026-09-09 this module *does* compare
  the two -- `reconcile_fill_fees` alerts through `Alerter.check_fee` when a
  charge exceeds the prediction -- but the test is one-sided by design, so
  silence means "the venue did not charge more than this repo promises", NOT
  "the model is correct". It is knowingly 2.00x high on baseball (ADR 0058
  keeps the flat coefficient off the record-writing path) and refuted on
  combinations (ADR 0046), where a deliberate ceiling stands in for a model.
  Nothing here is a fit, and the comparison stays **off-gate**: ADR 0043's
  `source = 'engine'` filter means no `venue_hand` row can move the
  interlock in either direction, and this changes none of that.
- **Which estimate a position matches.** Matching is analysis (§7.3 of the
  registration), runs on read, and is deliberately not done at ingest: a
  matcher inside the poller would bake today's matching rule into the stored
  record.

Money is integer tenths of a cent. Quantities are REAL (fractional counts are
real: `0.27` and `11.27` are both in the live record). Unreadable resolves to
`None`, never `0` -- and a row whose money fields cannot be read is **skipped
and counted**, never written half-parsed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from .core.fees import (
    FEE_MATCH_TOLERANCE_DOLLARS,
    calculate_fee,
    combo_taker_fee,
)
from .core.prices import dollars_to_tenths
from .kalshi.discovery import parse_ms
from .kalshi.rest import KalshiRestClient, parse_position_fp
from .store import db as store_db

logger = logging.getLogger(__name__)

# The wire values `source` may take here. 'engine' is reserved for the order
# path and this module must never write it -- see ADR 0043.
VENUE_SOURCE = "venue_hand"

#: How long a `venue_positions` snapshot is kept. The writer deletes older
#: rows in the same transaction as the snapshot it just wrote, so the table
#: bounds itself whether or not the runner's slow pass -- where
#: `store/retention.py` runs -- is alive; that loop has been observed down
#: while this one was up. The only production reader (`bets.open_positions`)
#: takes the newest successful poll, so any window past
#: `bets.TONIGHT_STALE_AFTER_MS` (30 minutes) serves it; seven days keeps a
#: week of snapshots to diagnose against, at (positions held) x 288 rows a
#: day.
VENUE_POSITIONS_RETENTION_MS = 7 * 24 * 3600 * 1000


def _fractional_count(value: Any) -> Optional[float]:
    """A `*_count_fp` string ("11.27") to a float count. None when unreadable.

    Not `dollars_to_tenths`: this is a quantity, not money, and the schema's
    convention for quantities is REAL. Negative counts are refused the same way
    negative prices are -- a count is being validated, not trusted.
    """
    if value is None:
        return None
    try:
        as_decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not as_decimal.is_finite() or as_decimal < 0:
        return None
    return float(as_decimal)


@dataclass(frozen=True)
class ParsedSettlement:
    ticker: str
    event_ticker: Optional[str]
    market_result: Optional[str]
    settled_ms: int
    side: str
    contracts: float
    entry_price_tenths: Optional[int]
    fee_cost_tenths: Optional[int]


def parse_settlement(row: dict) -> Optional[ParsedSettlement]:
    """One `/portfolio/settlements` record into the repo's units.

    Returns None -- refusal, not zero -- when the row cannot carry a position:
    no ticker, no settled time, or a count pair that reads as neither side.
    Field names are the ones observed on this account 2026-08-18
    (`data/captures/portfolio_settlements.json`), not the docs' names.

    `revenue` and `value` are deliberately not read: both are the deprecated
    integer-cent legacy fields and both were 0 on every observed record.
    """
    ticker = row.get("ticker")
    settled_ms = parse_ms(row.get("settled_time"))
    if not ticker or settled_ms is None:
        return None

    yes_count = _fractional_count(row.get("yes_count_fp"))
    no_count = _fractional_count(row.get("no_count_fp"))
    if yes_count and yes_count > 0:
        side, contracts, cost_key = "yes", yes_count, "yes_total_cost_dollars"
    elif no_count and no_count > 0:
        side, contracts, cost_key = "no", no_count, "no_total_cost_dollars"
    else:
        # Both zero, or both unreadable. A settlement with no position on
        # either side is not a position; refuse rather than invent a side.
        return None

    # Average entry price: total cost over count, both from the venue. The
    # division happens in Decimal via the dollar string so a fractional count
    # cannot smuggle float error into a money figure.
    entry_price_tenths: Optional[int] = None
    try:
        total_cost = Decimal(str(row.get(cost_key)))
        if total_cost.is_finite() and total_cost >= 0 and contracts > 0:
            entry_price_tenths = dollars_to_tenths(
                total_cost / Decimal(str(contracts))
            )
    except (InvalidOperation, ValueError, TypeError):
        entry_price_tenths = None

    return ParsedSettlement(
        ticker=str(ticker),
        event_ticker=row.get("event_ticker"),
        market_result=row.get("market_result"),
        settled_ms=settled_ms,
        side=side,
        contracts=contracts,
        entry_price_tenths=entry_price_tenths,
        fee_cost_tenths=dollars_to_tenths(row.get("fee_cost")),
    )


@dataclass(frozen=True)
class ParsedFill:
    kalshi_fill_id: str
    ticker: str
    filled_ms: int
    count: float
    price_tenths: int
    is_taker: bool
    fee_actual: Optional[float]
    # The venue's own order id for the order this fill answered (D3,
    # 2026-08-22). Present on every fill in the 2026-08-18 capture and
    # DISCARDED until now — without it a portal-placed order's fill lands
    # labelled `venue_hand` with no join back to the manual_orders row that
    # caused it. Optional: a fill without one still records (refusing a real
    # fill over a missing join key is the wrong way round).
    venue_order_id: Optional[str] = None


def parse_fill(row: dict) -> Optional[ParsedFill]:
    """One `/portfolio/fills` record into the repo's units. None on refusal.

    The shape is the one observed on this account 2026-08-18 -- 25 fills,
    every field present on all 25 (`data/captures/portfolio_fills.json`). The
    price paid is `yes_price_dollars` or `no_price_dollars` **by the fill's own
    `side`**; reading the wrong one books a 1c fill as a 99c one.

    `fee_cost` stays in dollars (REAL) because `fills.fee_actual` is the
    column `_fee_model_verified` compares in dollars. It is the one money field
    in this module not stored in tenths, and that is the existing table's
    contract, not a new decision.
    """
    fill_id = row.get("fill_id")
    ticker = row.get("ticker")
    side = row.get("side")
    if not fill_id or not ticker or side not in ("yes", "no"):
        return None

    # `created_time` is ISO-8601 with microseconds; `ts` is whole seconds.
    # Prefer the precise one, fall back to the coarse one, refuse on neither.
    filled_ms = parse_ms(row.get("created_time"))
    if filled_ms is None:
        ts = row.get("ts")
        filled_ms = int(ts) * 1000 if isinstance(ts, int) and ts > 0 else None
    if filled_ms is None:
        return None

    count = _fractional_count(row.get("count_fp"))
    price_key = "yes_price_dollars" if side == "yes" else "no_price_dollars"
    price_tenths = dollars_to_tenths(row.get(price_key))
    is_taker = row.get("is_taker")
    if count is None or count <= 0 or price_tenths is None:
        return None
    if not isinstance(is_taker, bool):
        # The maker/taker flag is the one field the fee question turns on.
        # A guessed default here would poison the comparison it exists for.
        return None

    order_id = row.get("order_id")
    return ParsedFill(
        kalshi_fill_id=str(fill_id),
        ticker=str(ticker),
        filled_ms=filled_ms,
        count=count,
        price_tenths=price_tenths,
        is_taker=is_taker,
        fee_actual=_fee_dollars(row.get("fee_cost")),
        venue_order_id=str(order_id) if order_id else None,
    )


def _fee_dollars(value: Any) -> Optional[float]:
    """A `fee_cost` dollar string to a float, refusing garbage. None never 0."""
    if value is None:
        return None
    try:
        as_decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not as_decimal.is_finite() or as_decimal < 0:
        return None
    return float(as_decimal)


# ---------------------------------------------------------------------------
# Fee reconciliation: what the venue charged against what this repo predicts.
#
# **Every number in this section is DOLLARS, and that is the one thing most
# likely to be wrong here.** The repo's convention is integer tenths of a cent
# everywhere in the risk path (`core/prices.py`), and the fee is the documented
# exception: `parse_fill` keeps `fee_cost` in dollars because `fills.fee_actual`
# is the column `gate._fee_model_verified` compares in dollars,
# `core.fees.calculate_fee` returns dollars, and `Alerter.check_fee` renders
# `${predicted:.2f}`. Three dollar figures, no conversion anywhere. So every
# name below spells `_dollars`, because a tenths value passed into this
# comparison would be 1000x too large and would read as a mismatch on every
# fill rather than as a unit error.
# ---------------------------------------------------------------------------

#: A fill whose charge exceeds the prediction by more than this is a mismatch.
#: `core.fees.FEE_MATCH_TOLERANCE_DOLLARS` (1e-9), not a number chosen here --
#: the gate's own mismatch test uses it (`gate.py`,
#: `ABS(fee_actual - fee_predicted) > ?`), and two spellings of "the fee model
#: is wrong" would drift apart. It is float noise only and the constant's own
#: comment says why: both sides land on `FEE_GRID_DOLLARS` ($0.0001, measured,
#: and combos have been observed on a grid finer still), so a correct model
#: matches a charge exactly and the only thing to absorb is the round trip
#: through SQLite's REAL and Python's float. A tolerance wide enough to forgive
#: a rounding disagreement would forgive a 10% error on a one-contract fill,
#: where the fee is largest as a share of the stake.
FEE_UNDERCHARGE_TOLERANCE_DOLLARS = FEE_MATCH_TOLERANCE_DOLLARS


@dataclass(frozen=True)
class FeePrediction:
    """What this repo says a fill should have been charged, in dollars.

    `dollars` is `None` -- refusal, never 0 -- whenever no model in this repo
    claims to price the fill, and `refusal` then says which one in words. A
    zero prediction against a real charge would fire the alarm on exactly the
    rows nothing can predict.
    """

    dollars: Optional[float]
    model: Optional[str]
    refusal: Optional[str]


@dataclass(frozen=True)
class FeeReconciliation:
    """One mirrored fill beside the fee this repo predicted for it, in dollars.

    `predicted_dollars` is a **ceiling**, not a point estimate -- see
    `predict_fill_fee` -- so `undercharge_dollars` is the signed amount by
    which the venue exceeded what this repo is willing to promise. Negative is
    the normal, designed state.
    """

    kalshi_fill_id: str
    ticker: str
    model: str
    predicted_dollars: float
    actual_dollars: float

    @property
    def undercharge_dollars(self) -> float:
        return self.actual_dollars - self.predicted_dollars

    @property
    def is_mismatch(self) -> bool:
        return self.undercharge_dollars > FEE_UNDERCHARGE_TOLERANCE_DOLLARS


def predict_fill_fee(parsed: ParsedFill) -> FeePrediction:
    """The fee this repo predicts for one fill, in dollars. Never a guess.

    **Two functions, because the armed path prices two instruments.** A
    combination (`KXMVE*`) is priced by `core.fees.combo_taker_fee` -- the
    ADR 0073 hedge, `COMBO_TAKER_COEFFICIENT = 0.071` -- because that is the
    function the manual order path itself charges a combo order with
    (`api/routes.py`), and because `calculate_fee`'s model is *refuted* on
    combos (ADR 0046: every one of the 8 observed combo fills was charged
    strictly above `0.070 * C * P * (1-P)`). Everything else is priced by
    `core.fees.calculate_fee`, which returns `_model_a` alone -- the measured
    model, `ceil(k * C * P * (1-P))` onto $0.0001 per order. `_model_b` and
    `_model_a_pre_july_2026` are refuted and retained as evidence, and their
    own docstrings forbid pricing with them; `fee_candidates` says in words it
    is not for pricing.

    **No `fee_multiplier`.** ADR 0058 confines the venue's per-series field to
    record-writing callers, and `poll_fills` already writes
    `fills.fee_predicted` without it -- so on a non-baseball fill this
    reproduces the stored prediction exactly, and on a baseball one it
    overstates by exactly 2.00x, knowingly. That asymmetry is why the alarm
    below is one-sided.

    Refusals, each `None` with a reason rather than a number:

    - **A maker fill on a combination.** `combo_taker_fee` has no maker branch
      because no maker combo fill has ever been observed and ADR 0073 permits
      taker IOC buys only. Substituting the single-market maker coefficient
      would be a coefficient with no observation behind it.
    - **An untradeable price.** `calculate_fee` returns `None` at 0 or 1000
      tenths for the reason its docstring gives at length: a zero fee
      manufactures an edge.
    """
    from .estimates import classify_ticker  # deferred: `estimates` imports us

    _is_sports, _sport, is_multi_leg = classify_ticker(parsed.ticker)
    if is_multi_leg:
        if not parsed.is_taker:
            return FeePrediction(
                dollars=None,
                model=None,
                refusal=(
                    "a maker fill on a combination: no maker combo fill has "
                    "ever been observed and ADR 0073 permits taker IOC buys "
                    "only, so this repo has no coefficient to predict with"
                ),
            )
        dollars = combo_taker_fee(parsed.price_tenths, parsed.count)
        model = "combo_taker_ceiling_0071"
    else:
        dollars = calculate_fee(
            price_tenths=parsed.price_tenths,
            contracts=parsed.count,
            maker=not parsed.is_taker,
        )
        model = "model_a_deci"
    if dollars is None:
        return FeePrediction(
            dollars=None,
            model=None,
            refusal=(
                f"no fee is defined at price_tenths={parsed.price_tenths}: "
                f"0 and 1000 are settled outcomes, not quotes"
            ),
        )
    return FeePrediction(dollars=dollars, model=model, refusal=None)


def reconcile_fill(parsed: ParsedFill) -> Optional[FeeReconciliation]:
    """One fill against the model, or `None` when it cannot be reconciled.

    **A missing `fee_actual` refuses; it never reads as $0.00.** `parse_fill`
    resolves an absent or unreadable `fee_cost` to `None`, and a `None` read as
    zero against a positive prediction is a mismatch on every unpolled fill --
    the alarm would fire loudest exactly where it knows least. Same rule as
    everywhere else in this module: unreadable resolves to `None`, never `0`,
    and the caller refuses rather than substitutes.
    """
    if parsed.fee_actual is None:
        logger.warning(
            "fee reconciliation refused for fill %s (%s): the venue's "
            "fee_cost was absent or unreadable, and an unreadable charge is "
            "not a zero charge",
            parsed.kalshi_fill_id, parsed.ticker,
        )
        return None
    prediction = predict_fill_fee(parsed)
    if prediction.dollars is None or prediction.model is None:
        logger.warning(
            "fee reconciliation refused for fill %s (%s): %s",
            parsed.kalshi_fill_id, parsed.ticker, prediction.refusal,
        )
        return None
    return FeeReconciliation(
        kalshi_fill_id=parsed.kalshi_fill_id,
        ticker=parsed.ticker,
        model=prediction.model,
        predicted_dollars=prediction.dollars,
        actual_dollars=parsed.fee_actual,
    )


async def reconcile_fill_fees(
    alerter: Any,
    checks: list,
    *,
    now_ms: int,
) -> dict:
    """Alert once when the venue charged MORE than this repo promised.

    **This is the caller `Alerter.check_fee` did not have.** Its docstring
    justified having none by `ORDERS_ARE_DRY_RUNS = True`; that is still true
    of the engine path and stopped being true of the desk on 2026-08-26, and
    real hand-bet fills landed 2026-09-08 (ADR 0113). Fills exist, `fee_actual`
    is the venue's ground truth beside them, and until now nothing compared
    the two.

    **The test is one-sided -- `actual > predicted` -- and that is the whole
    design, not a weakened guard.** `calculate_fee`'s stated property on every
    path that is not record-writing is *never under, overstating by a known
    factor*: ADR 0058 keeps the flat 0.070 coefficient on baseball where the
    venue charges 0.035, so a two-sided test fires on **every** MLB hand fill,
    forever, by deliberate policy -- e.g. fill `R` of the 2026-08-14
    attribution (`KXMLBGAME` 1 @ 52c) was charged $0.0088 against a $0.0175
    prediction. An alarm that fires by construction on a known and accepted
    state is an alarm that gets muted, and a muted alarm is worse than none.
    What the one-sided test keeps is the event that actually matters: an
    **undercharge** means the schedule moved against us, the never-undercharge
    property is broken, and every EV figure in the system is optimistic by an
    unknown amount. That is the stop-the-line message the notifier already
    carries.

    On the whole observed record this is silent, and that is checked rather
    than hoped: `KXWNBAGAME` 1 @ 28c was charged $0.0142 against a $0.0142
    prediction (equal), the baseball rows are overstated 2.00x, and the
    combination fills sit under the ADR 0073 ceiling ($0.015930 charged
    against $0.0162). It is *not* silent under the flat coefficient on that
    same combo row -- $0.0159 predicted against $0.015930 charged is an
    undercharge -- which is why `predict_fill_fee` prices a combo with the
    ceiling the order path itself uses.

    **One alert, not one per fill.** `check_fee` is keyed per *day* in the
    `notifications` table ("a wrong fee model is wrong on every fill, and one
    alert saying 'stop the line' is the whole message"), so this calls it at
    most once per pass, with the largest undercharge -- and the day key does
    the rest across passes. Every mismatch is logged at ERROR regardless, so
    the count is never hidden by the dedupe.

    **Never runs inside the write transaction.** The alert performs a Discord
    round trip and `Alerter._claim` commits; both callers therefore commit the
    mirror before awaiting this, which is the rule
    `tests/test_poller_holds_no_lock_across_io.py` exists to keep.

    Absorbed like every other optional path here: alerting must never take
    down the loop that is recording evidence.
    """
    result = {"checked": len(checks), "mismatched": 0, "alerted": None}
    mismatched = [c for c in checks if c.is_mismatch]
    result["mismatched"] = len(mismatched)
    for check in mismatched:
        logger.error(
            "FEE MISMATCH on fill %s (%s): Kalshi charged $%.6f against a "
            "$%.6f prediction from %s -- an UNDERCHARGE of $%.6f, so the "
            "never-undercharge property of core/fees.py is broken",
            check.kalshi_fill_id, check.ticker, check.actual_dollars,
            check.predicted_dollars, check.model, check.undercharge_dollars,
        )
    if alerter is None or not mismatched:
        return result
    worst = max(mismatched, key=lambda c: c.undercharge_dollars)
    try:
        result["alerted"] = await alerter.check_fee(
            now_ms=now_ms,
            ticker=worst.ticker,
            # Dollars on both sides. See the unit note at the top of this
            # section: `fee_actual` is dollars, `calculate_fee` returns
            # dollars, and the notifier prints them as dollars.
            predicted=worst.predicted_dollars,
            actual=worst.actual_dollars,
        )
    except Exception as exc:  # noqa: BLE001 -- alerting never blinds the mirror
        logger.exception("fee mismatch alert failed: %s", exc)
        result["alerted"] = f"FAILED: {exc}"
    return result


def parse_balance_tenths(payload: dict) -> Optional[int]:
    """`balance_dollars` to tenths. **Never the `balance` integer.**

    Observed side by side on 2026-08-18: `balance` was 2065 while
    `balance_dollars` was "20.6583". The integer is whole cents and silently
    drops the 0.83c -- the deci-cent error CLAUDE.md opens with, in a wallet.
    """
    return dollars_to_tenths(payload.get("balance_dollars"))


def parse_portfolio_value_tenths(payload: dict) -> Optional[int]:
    """`portfolio_value`, accepted only at the one value whose unit is known.

    The field has been observed exactly once, as the integer `0`, with no
    `_dollars` twin beside it. Zero is zero in every candidate unit, so it is
    stored. **Any non-zero value is refused (None) until the unit is pinned**
    by an observation against a non-empty position list -- guessing cents by
    analogy with `balance` is exactly the convenient-column error, one field
    over. When this starts returning None on a real portfolio, that is the
    prompt to capture a payload and pin the unit, not to widen this function.
    """
    value = payload.get("portfolio_value")
    if value == 0:
        return 0
    return None


@dataclass(frozen=True)
class ParsedPosition:
    """One `/portfolio/positions` row: the wire's text verbatim, plus three
    derived columns that are `None` -- never 0 -- when unreadable.

    Unlike `ParsedFill` and `ParsedSettlement`, `parse_position` never
    refuses the whole row. The verbatim strings are the record of what the
    venue said, and they are worth keeping even when a derived value is not
    computable from them -- the next reader can check the derivation against
    the source without another capture. What IS refused is the derived
    figure, and `bets.open_positions` refuses its sum when any row's
    `exposure_tenths` is `None`, rather than summing the rest.
    """

    ticker: Optional[str]
    exchange_index: Optional[int]
    position_fp: Optional[str]
    market_exposure_dollars: Optional[str]
    total_traded_dollars: Optional[str]
    fees_paid_dollars: Optional[str]
    realized_pnl_dollars: Optional[str]
    last_updated_ts: Optional[str]
    #: REAL quantity, `abs(position_fp)`; the schema's convention for a count.
    contracts: Optional[float]
    #: 'yes' | 'no' from the sign of `position_fp`; None at zero or unreadable.
    side: Optional[str]
    #: Integer tenths of a cent: EXPOSURE AT COST, from
    #: `market_exposure_dollars`. Money in, before fees. Not market value.
    exposure_tenths: Optional[int]
    #: Why `exposure_tenths` is None, in words, when it is; None when it is
    #: not. Not a column -- the verbatim text is the stored diagnostic -- but
    #: the writer's log line says which refusal fired rather than "did not
    #: parse" for a value that parsed fine and failed the scale tripwire.
    exposure_refusal: Optional[str]


def _verbatim(value: Any) -> Optional[str]:
    """The wire value as text, exactly. A string is itself; anything else
    is its JSON so an integer, a bool and a nested object all survive
    unambiguously. `None` stays `None` -- an absent field is not `'null'`."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


def parse_position(row: dict) -> ParsedPosition:
    """One `/portfolio/positions` row into the mirror's columns.

    The shape is the one observed on this account 2026-08-30
    (`tests/test_rest.py::OBSERVED_POSITION_ROW`): `position_fp` a
    fixed-point string, signed by side; `market_exposure_dollars` and its
    three siblings six-decimal dollar strings; `last_updated_ts` ISO-8601;
    `exchange_index` an integer.

    - `contracts`/`side` come through `kalshi.rest.parse_position_fp`
      (Decimal; never `int()`, which misreads "22.88", never `float`
      first). The sign is the side per the venue's convention; the
      magnitude is the count.
    - `exposure_tenths` comes through `core.prices.dollars_to_tenths`, the
      wallet's one dollars-to-tenths spelling: `Decimal * 1000`,
      ROUND_HALF_UP to a whole tenth, so a fractional-contract exposure
      such as "7.641920" (7641.92 tenths) lands on the tenth grid within
      +-0.05 tenths. That helper also refuses a negative -- deliberately
      kept here: whether the venue signs a NO-side exposure has never been
      observed, and `abs()` would be a guess wearing a number.
    - **The unit of `market_exposure_dollars` is inferred from its suffix,
      not measured**, and the parser says so instead of pretending. The
      suffix was pinned on `balance_dollars` ("20.6583" beside `balance`
      2065, 2026-08-18) and on the fills' `*_price_dollars`; this field's
      magnitude has never been read against a known position. What stands in
      for the measurement is a tripwire: a contract cannot cost more than
      $1, so `exposure_tenths` may not exceed `abs(position_fp)` in dollars
      on the same grid -- the ceiling goes through the SAME
      `dollars_to_tenths`, so the two roundings are one rounding and the
      bound is monotone (a true $1 a contract lands equal, never above). A
      row that breaks it (a cents-with-decimals field would put 764192
      against a ceiling of 22880) has its `exposure_tenths` set to `None`
      and its `exposure_refusal` say why. The tripwire catches a scale
      error; it does not make the unit measured.

    Unreadable resolves to `None`, never 0, per column; the verbatim text is
    kept either way. This function establishes nothing about fees (whether
    the exposure includes them is untested), nothing about the unit beyond
    the bound above, and reads nothing from `event_positions`.
    """
    ticker = row.get("ticker")
    exchange_index = row.get("exchange_index")
    quantity = parse_position_fp(row.get("position_fp"))
    if quantity is None:
        contracts: Optional[float] = None
        side: Optional[str] = None
    else:
        contracts = float(abs(quantity))
        side = "yes" if quantity > 0 else "no" if quantity < 0 else None
    exposure_tenths = dollars_to_tenths(row.get("market_exposure_dollars"))
    exposure_refusal: Optional[str] = None
    if exposure_tenths is None:
        exposure_refusal = (
            "market_exposure_dollars did not parse as a non-negative "
            "dollar string"
        )
    elif quantity is not None:
        # `abs(quantity)` in "dollars" is the most a position of that many
        # contracts can have cost. Through the same helper as the exposure
        # itself, so the rounding is shared; None (non-finite, absurd) means
        # no ceiling can be stated and the tripwire does not fire.
        ceiling_tenths = dollars_to_tenths(abs(quantity))
        if ceiling_tenths is not None and exposure_tenths > ceiling_tenths:
            exposure_refusal = (
                f"market_exposure_dollars exceeds $1 a contract "
                f"({exposure_tenths} tenths against position_fp {quantity}, "
                f"ceiling {ceiling_tenths}): a scale error, not a stake"
            )
            exposure_tenths = None
    return ParsedPosition(
        ticker=str(ticker) if ticker is not None else None,
        exchange_index=(
            exchange_index
            if isinstance(exchange_index, int)
            and not isinstance(exchange_index, bool)
            else None
        ),
        position_fp=_verbatim(row.get("position_fp")),
        market_exposure_dollars=_verbatim(row.get("market_exposure_dollars")),
        total_traded_dollars=_verbatim(row.get("total_traded_dollars")),
        fees_paid_dollars=_verbatim(row.get("fees_paid_dollars")),
        realized_pnl_dollars=_verbatim(row.get("realized_pnl_dollars")),
        last_updated_ts=_verbatim(row.get("last_updated_ts")),
        contracts=contracts,
        side=side,
        exposure_tenths=exposure_tenths,
        exposure_refusal=exposure_refusal,
    )


def log_poll_attempt(
    conn: sqlite3.Connection,
    *,
    now_ms: int,
    endpoint: str,
    ok: bool,
    row_count: Optional[int] = None,
    error: Optional[str] = None,
) -> int:
    """Write the attempt; return the new `poll_log.id`, which a mirror row
    that came from this attempt must carry (`venue_positions.poll_log_id`)."""
    cursor = conn.execute(
        "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count, error) "
        "VALUES (?, ?, ?, ?, ?)",
        (now_ms, endpoint, 1 if ok else 0, row_count, error),
    )
    return int(cursor.lastrowid)


async def poll_portfolio(
    conn: sqlite3.Connection,
    client: KalshiRestClient,
    *,
    now_ms: int,
    alerter: Any = None,
) -> dict[str, Any]:
    """One pass over all four endpoints. Every attempt leaves a `poll_log` row.

    Endpoints are independent: a failure on one is logged and the rest still
    run, because the registration's tripwires are per-endpoint and a
    settlements outage must not blind the balance record.

    Returns a summary dict for the caller's log line. The summary is
    convenience; `poll_log` is the record.

    **Each step commits before the next network call, and that is a lock
    property rather than a durability one.** Until 2026-08-31 the four steps
    shared one transaction: `poll_settlements` INSERTs, which acquires SQLite's
    write lock, and nothing released it until the single commit **three Kalshi
    round trips later**. Every other writer landing in that window waited out
    `BUSY_TIMEOUT_MS` and raised -- `store_closing_line` on the scoring pass
    most often, which kills the whole pass and loses closing lines that cannot
    be re-observed.

    The comment below this block reasons carefully about **rollback scope**
    ("so a matcher failure cannot roll back the mirror") and says nothing about
    **lock duration**. They are different questions and only one had been asked.

    **Nothing that is relied upon becomes less atomic.** The four steps write
    independent records to different tables from different endpoints, each an
    `INSERT OR IGNORE`; a failure in one never made the rows already written
    wrong, and each endpoint's outcome is recorded in `poll_log` separately
    either way. The rule: **never hold a write transaction across an `await`
    that performs I/O** -- a lock is held in wall-clock time and an `await` is
    an unbounded amount of it.
    """
    summary: dict[str, Any] = {}

    # -- settlements: the primary statistic's inputs live here ---------------
    summary["settlements"] = await poll_settlements(conn, client, now_ms=now_ms)
    conn.commit()

    # -- fills: source='venue_hand', never 'engine' (ADR 0043) ---------------
    fee_checks: list = []
    summary["fills"] = await poll_fills(
        conn, client, now_ms=now_ms, fee_checks=fee_checks
    )
    conn.commit()
    # After that commit, never before: this awaits a Discord round trip and
    # `Alerter._claim` commits, so it may not run with the mirror's write lock
    # held. See `reconcile_fill_fees`.
    summary["fee_reconciliation"] = await reconcile_fill_fees(
        alerter, fee_checks, now_ms=now_ms
    )
    # And a commit AFTER it too, not only before. `reconcile_fill_fees`
    # is handed this same connection through `alerter_factory`, and
    # `Alerter._claim` INSERTs into `notifications` on it -- so the call
    # is a writer from this function's point of view even though the
    # write happens a layer down. `_claim` commits internally, which is
    # why this was invisible; the next statement is `await
    # poll_positions(...)`, a Kalshi round trip, and the invariant is that
    # no network await runs with a write unaccounted for.
    #
    # Found by enrolling `reconcile_fill_fees` in
    # `tests/test_poller_holds_no_lock_across_io.py`'s IO_CALLS on
    # 2026-09-09. The guard is a list, not a sweep, so it could only find
    # this once the name was added.
    conn.commit()

    # -- positions: counted in poll_log AND mirrored (schema v33) -----------
    summary["positions"] = await poll_positions(conn, client, now_ms=now_ms)
    conn.commit()

    # -- balance: dollars string, never the cents integer --------------------
    summary["balance"] = await poll_balance(conn, client, now_ms=now_ms)

    conn.commit()

    # -- the matcher: the reader for everything mirrored above ---------------
    # After the commit, so a matcher failure cannot roll back the mirror --
    # the record is the point and the join is derived from it, rerunnable on
    # the next cycle. Absorbed like the endpoints: the study's bookkeeping
    # must not take down the poller that feeds it.
    try:
        from .estimate_match import run_match_pass
        from .kalshi.quotes import LiveQuoteSource

        summary["match"] = await run_match_pass(
            conn, LiveQuoteSource(rest=client), now_ms=now_ms
        )
    except Exception as exc:  # noqa: BLE001 -- never blind the mirror
        logger.exception("estimate match pass failed: %s", exc)
        summary["match"] = f"FAILED: {exc}"
        # Every sibling endpoint's failure lands in poll_log; until 2026-08-29
        # this one landed only in a log line, and `flyctl logs` is lossy -- a
        # matcher throwing on every mirror for a week was invisible. The
        # commit is deliberate: this runs after the mirror's own commit above,
        # and a failure row left riding an open transaction until the next
        # fast cycle is a row a crash silently discards.
        log_poll_attempt(
            conn, now_ms=now_ms, endpoint="match", ok=False, error=repr(exc)
        )
        conn.commit()
    return summary


async def poll_settlements(
    conn: sqlite3.Connection,
    client: KalshiRestClient,
    *,
    now_ms: int,
) -> Any:
    """The settlements mirror alone, so it can run on the 5-minute cadence.

    Extracted from `poll_portfolio` for ADR 0064: the daily-loss kill
    switch's producer (`bets.venue_daily_realised_pnl_dollars`) reads this
    table and REFUSES when its freshest successful read is older than
    `bets.TONIGHT_STALE_AFTER_MS` (30 min = 6x this cadence). On the
    12-hour mirror clock alone that refusal would stand almost all day,
    and worse, a mirror read at 10am carries none of the evening's losses
    -- the false negative in the flattering direction, on the exact
    quantity that exists to stop the next bet. The registration argument
    is `poll_fills`'s, unchanged: §7.6 sets a floor on the mirror's
    completeness, and polling an unmetered venue endpoint more often can
    only make the mirror more complete.

    The caller commits; this function only writes, exactly as
    `poll_balance` does, so `poll_portfolio` can reuse it in its own
    transaction.
    """
    try:
        rows = await client.settlements(limit=200)
    except Exception as exc:  # noqa: BLE001 -- every failure must land in poll_log
        log_poll_attempt(
            conn, now_ms=now_ms, endpoint="settlements", ok=False,
            error=repr(exc),
        )
        return f"FAILED: {exc}"
    written = refused = 0
    for row in rows:
        parsed = parse_settlement(row)
        if parsed is None:
            refused += 1
            logger.warning("settlement refused, ticker=%s", row.get("ticker"))
            continue
        cursor = conn.execute(
            "INSERT OR IGNORE INTO venue_settlements "
            "(ticker, event_ticker, market_result, settled_ms, side, "
            " contracts, entry_price_tenths, fee_cost_tenths, "
            " position_first_seen_ms, position_time_source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                parsed.ticker, parsed.event_ticker, parsed.market_result,
                parsed.settled_ms, parsed.side, parsed.contracts,
                parsed.entry_price_tenths, parsed.fee_cost_tenths,
                now_ms, "poll_instant",
            ),
        )
        written += cursor.rowcount
    log_poll_attempt(
        conn, now_ms=now_ms, endpoint="settlements", ok=True,
        row_count=len(rows),
    )
    return {"seen": len(rows), "new": written, "refused": refused}


async def poll_fills(
    conn: sqlite3.Connection,
    client: KalshiRestClient,
    *,
    now_ms: int,
    fee_checks: Optional[list] = None,
) -> Any:
    """The fills alone, so they can run on the 5-minute cadence too.

    Extracted from `poll_portfolio` on the 2026-08-21 partner ruling: the
    landing screen's "tonight" strip reads this table, and on the 12-hour
    mirror alone it would say "no bets tonight" at 8pm off a 10am read --
    a false negative in the flattering direction, on the one screen whose
    purpose is to interrupt. **This is not an amendment to the registered
    cadence**: §7.6 sets a floor on the mirror's completeness, and polling
    an unmetered venue endpoint more often can only make the mirror more
    complete. **The matcher** stays on the registered 12-hour clock, and it
    is now the only thing that does: settlements joined this cadence with
    ADR 0064 (`poll_settlements`) and positions on 2026-08-29
    (`poll_positions`). The matcher is the one of the four that writes a
    registered variable, which is why it did not come with them.

    The caller commits; this function only writes, exactly as
    `poll_balance` does, so `poll_portfolio` can reuse it in its own
    transaction.

    **`fee_checks` is an out-parameter, and it is one on purpose.** When a list
    is given, every fill this call *newly stored* and could reconcile is
    appended to it as a `FeeReconciliation`; the caller then awaits
    `reconcile_fill_fees` **after committing**. It is not a return value
    because the returned dict is what the loop logs, and it is not an `await`
    in here because the alert is a Discord round trip and this function is
    holding SQLite's write lock -- the exact shape ADR 0091 removed and
    `tests/test_poller_holds_no_lock_across_io.py` pins. Newly stored rows
    only (`cursor.rowcount > 0`): the mirror re-reads the same 200 fills every
    five minutes, and reconciling them all again would make the alarm's
    workload proportional to the venue's retention rather than to what
    happened.
    """
    try:
        rows = await client.fills(limit=200)
    except Exception as exc:  # noqa: BLE001 -- every failure must land in poll_log
        log_poll_attempt(
            conn, now_ms=now_ms, endpoint="fills", ok=False, error=repr(exc)
        )
        return f"FAILED: {exc}"
    written = refused = 0
    for row in rows:
        parsed = parse_fill(row)
        if parsed is None:
            refused += 1
            logger.warning("fill refused, id=%s", row.get("fill_id"))
            continue
        predicted = calculate_fee(
            price_tenths=parsed.price_tenths,
            contracts=parsed.count,
            maker=not parsed.is_taker,
        )
        cursor = conn.execute(
            "INSERT OR IGNORE INTO fills "
            "(kalshi_fill_id, ticker, filled_ms, count, price_tenths, "
            " is_taker, fee_actual, fee_predicted, fee_model_used, source, "
            " venue_order_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                parsed.kalshi_fill_id, parsed.ticker, parsed.filled_ms,
                parsed.count, parsed.price_tenths,
                1 if parsed.is_taker else 0, parsed.fee_actual,
                predicted, "model_a_deci", VENUE_SOURCE,
                parsed.venue_order_id,
            ),
        )
        written += cursor.rowcount
        if fee_checks is not None and cursor.rowcount > 0:
            check = reconcile_fill(parsed)
            if check is not None:
                fee_checks.append(check)
    log_poll_attempt(
        conn, now_ms=now_ms, endpoint="fills", ok=True, row_count=len(rows)
    )
    return {"seen": len(rows), "new": written, "refused": refused}


async def poll_positions(
    conn: sqlite3.Connection,
    client: KalshiRestClient,
    *,
    now_ms: int,
) -> Any:
    """The open positions, mirrored: counted in `poll_log` AND stored in
    `venue_positions`, on the 5-minute cadence.

    **Until schema v33 this counted and discarded.** The docstring here read
    *"Still COUNTED, NOT PARSED"* and the loop below it logged a warning that
    the per-row shape had *"never been captured"*. The shape was captured on
    2026-08-30 (`scripts/capture_positions_fixture.py`;
    `tests/test_rest.py::OBSERVED_POSITION_ROW` carries it), so from that day
    the warning was false and the discard was a choice. `bets.open_positions`
    meanwhile served "Open now: N" beside an unconditional refusal where the
    money figure belonged (ADR 0101 section 2.3, third reason). Now every row
    the venue returns is written through `parse_position`: the wire text
    verbatim, three derived columns that are NULL when unreadable, all stamped
    with the `poll_log` row this call just wrote -- so the count and the sum a
    reader takes from them come from ONE venue read with ONE stamp.

    **`poll_log.row_count` is written exactly as before**, from `len(rows)`,
    and stays the count the desk serves. A failed call leaves its `poll_log`
    row and writes nothing to the mirror; the previous snapshot stays the
    newest. After a successful write, rows older than
    `VENUE_POSITIONS_RETENTION_MS` are deleted in the same transaction -- the
    table bounds itself (see the constant for why not `store/retention.py`).

    Extracted from `poll_portfolio` (2026-08-29) for the reason `poll_fills`
    and `poll_settlements` were extracted before it: a consumer refuses on a
    stale read, and on the 12-hour mirror alone the refusal is the wrong one.
    Since 2026-08-26 Joe places real hand bets through `/api/manual-orders`
    one contract at a time, so a bet he just placed did not move the count for
    up to twelve hours -- and only ever *looked* fresh because this instance's
    containers keep restarting and `poll_portfolio_forever`'s first cycle is
    a full mirror; the freshness was the boot clock, not the poller.

    **This is not an amendment to the registered cadence, and the
    registration draws the line itself.** A1 sets `fills`, `settlements` and
    `positions` to 12 hours as a FLOOR on the mirror's completeness -- polling
    an unmetered venue endpoint more often can only make the mirror more
    complete -- and A7 separates an *operational clock* from an *analysis
    clock*, granting the operational one a 5-minute cadence in those words.
    A7's reason for keeping the two apart is an unbounded number of implicit
    looks at a stopping arm, and it does not reach here: **no registered
    statistic reads `positions` or `venue_positions`.** `MIRROR_INTERVAL_S`
    is untouched, and `run_match_pass` -- which does write a registered
    variable (`outcome_win`) -- stays on it.

    The caller commits; this function only writes, exactly as `poll_balance`
    does, so `poll_portfolio` can reuse it inside its own transaction. The
    one network `await` is the first statement, before any write, which is
    the property `tests/test_poller_holds_no_lock_across_io.py` guards in the
    callers.

    Returns `{"seen", "stored", "exposure_unreadable"}`: rows the venue
    returned, rows written (always equal -- a row is never refused whole), and
    rows whose `exposure_tenths` is NULL, which the reader will refuse to sum.
    The rows, the `mirrored` mark on the `poll_log` row and the prune are
    `store_positions_snapshot`'s, so the hand-bet path can keep its own read
    the same way through one call.
    """
    try:
        rows = await client.positions()
    except Exception as exc:  # noqa: BLE001 -- every failure must land in poll_log
        log_poll_attempt(
            conn, now_ms=now_ms, endpoint="positions", ok=False,
            error=repr(exc),
        )
        return f"FAILED: {exc}"
    poll_log_id = log_poll_attempt(
        conn, now_ms=now_ms, endpoint="positions", ok=True,
        row_count=len(rows),
    )
    return store_positions_snapshot(
        conn, poll_log_id=poll_log_id, now_ms=now_ms, rows=rows
    )


def store_positions_snapshot(
    conn: sqlite3.Connection,
    *,
    poll_log_id: int,
    now_ms: int,
    rows: list,
) -> dict:
    """Keep the rows one successful `/portfolio/positions` read returned,
    under the `poll_log` row that recorded the read, and mark that row
    `mirrored = 1` -- all inside the caller's transaction, which the caller
    commits.

    **This is the seam between "the venue was asked" and "what it said was
    kept", and it exists as its own function because `poll_log` has two
    writers of positions reads and only one of them keeps rows.**
    **Both writers call this**, as of the ADR 0107 merge on 2026-09-05.
    `poll_positions` above is one. The other is `backend/api/routes.py::
    _stamp_positions_read` -- the hand-bet path's own read, check 10 of
    `POST /api/manual-orders` -- which logs through the same
    `log_poll_attempt` under the same endpoint name and now hands its rows
    here too. The lane that wrote this function could not make that edit
    (`routes.py` was another lane's file the same day) and the sentence above
    said "does not call this" for the length of one merge; the integrator made
    it and this is the corrected text rather than a rewrite of history.

    **The marker still matters and is not made redundant by that.** A reader
    taking "the newest successful positions poll" on the count alone cannot
    tell a stamp that kept nothing from a stamp that kept rows, and before the
    route's edit it would have found `row_count = N` with no rows under it for
    up to five minutes after every hand bet -- refusing the money figure at
    the one moment the desk is open. The mark is what lets
    `bets.open_positions` select the newest poll that KEPT its rows, and what
    keeps an empty snapshot (marked, zero rows -- the state the 2026-09-05
    capture found) apart from an unmarked stamp (zero rows, nothing kept),
    which no count can do. It is also what makes a *failed* read safe: that
    path keeps nothing and stays unmarked, pinned by
    `tests/test_manual_orders.py::TestTheLivePositionsReadIsStamped`.

    Every row goes through `parse_position`: the wire text verbatim, derived
    columns NULL when unreadable, never a row refused whole; a NULL
    `exposure_tenths` is logged with the parser's own reason. Rows older than
    `VENUE_POSITIONS_RETENTION_MS` are deleted afterwards, in the same
    transaction. `poll_log.row_count` is not touched here: the count is the
    logger's, the rows are this function's, and the marker is what says they
    belong to the same read.

    Returns `{"seen", "stored", "exposure_unreadable"}`.
    """
    unreadable = 0
    for row in rows:
        parsed = parse_position(row if isinstance(row, dict) else {})
        if parsed.exposure_tenths is None:
            unreadable += 1
            logger.warning(
                "positions: exposure at cost refused for %r -- %s "
                "(market_exposure_dollars=%r); stored verbatim with the "
                "derived column NULL, and the staked figure will refuse",
                parsed.ticker, parsed.exposure_refusal,
                parsed.market_exposure_dollars,
            )
        conn.execute(
            "INSERT INTO venue_positions "
            "(poll_log_id, polled_ms, ticker, exchange_index, position_fp, "
            " market_exposure_dollars, total_traded_dollars, fees_paid_dollars, "
            " realized_pnl_dollars, last_updated_ts, contracts, side, "
            " exposure_tenths) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                poll_log_id, now_ms, parsed.ticker, parsed.exchange_index,
                parsed.position_fp, parsed.market_exposure_dollars,
                parsed.total_traded_dollars, parsed.fees_paid_dollars,
                parsed.realized_pnl_dollars, parsed.last_updated_ts,
                parsed.contracts, parsed.side, parsed.exposure_tenths,
            ),
        )
    # After the rows, never before: the mark means "the rows under this id
    # are the read", and inside one transaction the order is a statement of
    # intent rather than a crash-safety measure.
    conn.execute(
        "UPDATE poll_log SET mirrored = 1 WHERE id = ?", (poll_log_id,)
    )
    conn.execute(
        "DELETE FROM venue_positions WHERE polled_ms < ?",
        (now_ms - VENUE_POSITIONS_RETENTION_MS,),
    )
    return {
        "seen": len(rows), "stored": len(rows), "exposure_unreadable": unreadable,
    }


async def poll_balance(
    conn: sqlite3.Connection,
    client: KalshiRestClient,
    *,
    now_ms: int,
) -> Any:
    """The balance alone: the 5-minute cadence, without the 12-hour mirror.

    Separated because the registration (§7.6 as amended) runs the two on
    different clocks -- the balance is what the stopping rule reads and what
    the operational display shows, while the mirror is the record. The caller
    commits; this function only writes, so `poll_portfolio` can reuse it
    inside its own transaction.
    """
    try:
        payload = await client.balance()
    except Exception as exc:  # noqa: BLE001 -- every failure must land in poll_log
        log_poll_attempt(
            conn, now_ms=now_ms, endpoint="balance", ok=False, error=repr(exc)
        )
        return f"FAILED: {exc}"
    balance_tenths = parse_balance_tenths(payload)
    conn.execute(
        "INSERT INTO venue_balance_snapshots "
        "(observed_ms, balance_tenths, portfolio_value_tenths) "
        "VALUES (?, ?, ?)",
        (now_ms, balance_tenths, parse_portfolio_value_tenths(payload)),
    )
    log_poll_attempt(conn, now_ms=now_ms, endpoint="balance", ok=True, row_count=1)
    _mark_study_start(conn, now_ms=now_ms, balance_tenths=balance_tenths)
    return {"balance_tenths": balance_tenths}


# Amendment A6's "written once on day 1" meta row. Joe declared the study open
# on 2026-08-18 (his ruling, delegated in-session: start now, top up as
# needed, the $100 cumulative-loss stop is the cap either way), so the first
# successful balance poll after this code lands stamps day 1. Idempotent:
# written exactly once, from the venue's own number, never from memory.
#
# A6 prints the value as "206583 tenths ($20.6583)". Those two cannot both be
# right -- $20.6583 is 20,658 tenths, and the poller's own live read on
# 2026-08-18 stored 20658 -- so the integer in A6 is the dollar string with
# its decimal point dropped, and the registered INTENT (the venue balance on
# day 1, in tenths) is what this writes. Recorded here so nobody "corrects"
# the stored value to the typo.
STUDY_START_MS_KEY = "calibration_study_start_ms"
STUDY_START_BALANCE_KEY = "balance_at_study_start_tenths"


def _mark_study_start(
    conn: sqlite3.Connection, *, now_ms: int, balance_tenths: Optional[int]
) -> None:
    """Stamp the study's day 1 on the first readable balance, exactly once.

    An unreadable balance must not stamp the start: `None` here means the
    venue could not be read, and a start marker with no balance beside it
    would make the A6 row a guess. The next successful poll stamps it.
    """
    if balance_tenths is None:
        return
    if store_db.get_meta(conn, STUDY_START_MS_KEY) is not None:
        return
    store_db._set_meta(conn, STUDY_START_MS_KEY, str(now_ms))
    store_db._set_meta(conn, STUDY_START_BALANCE_KEY, str(balance_tenths))
    logger.info(
        "calibration study day 1 stamped: start_ms=%d balance_tenths=%d",
        now_ms,
        balance_tenths,
    )


# The registered cadence, §7.6 of the calibration registration as amended:
# the full mirror every 12 hours, the balance every 5 minutes -- with fills
# (2026-08-21 ruling), settlements (ADR 0064) and positions (2026-08-29)
# riding the 5-minute clock because their consumers refuse on a stale read;
# §7.6 is a floor, and polling an unmetered endpoint more often only raises
# completeness. Constants rather than configuration, deliberately -- the
# cadence is REGISTERED, and a knob invites the deployed value to drift from
# the protocol without anyone deciding it. Changing these is amending the
# registration, and should read like it.
#
# **Two intervals, and there will not be a third.** Every endpoint that left
# the mirror shares `BALANCE_INTERVAL_S` rather than naming its own
# "recently" -- a fourth definition is how the loosest one wins in silence,
# and `bets.TONIGHT_STALE_AFTER_MS` is the single staleness bound read
# against all of them at 6x this cadence. What is still on `MIRROR_INTERVAL_S`
# is `run_match_pass` alone, and it is there because it writes a registered
# variable (`outcome_win`) -- the analysis clock of amendment A7, not an
# oversight.
MIRROR_INTERVAL_S = 12 * 3600
BALANCE_INTERVAL_S = 300


async def poll_portfolio_forever(
    db_path,
    client: KalshiRestClient,
    *,
    mirror_interval_s: float = MIRROR_INTERVAL_S,
    balance_interval_s: float = BALANCE_INTERVAL_S,
    alerter_factory: Optional[Any] = None,
    sleep=asyncio.sleep,
    clock=time.time,
    max_cycles: Optional[int] = None,
) -> None:
    """The poller as a long-running task beside the chain runner.

    Every `balance_interval_s` it snapshots the balance; whenever
    `mirror_interval_s` has elapsed since the last full mirror it runs
    `poll_portfolio` instead, which includes the balance. The first cycle is a
    full mirror, so a restart re-anchors the record immediately rather than
    twelve hours later -- restarts are exactly when a gap is most likely to be
    open.

    **A failed cycle is logged and the loop continues.** The failure record is
    `poll_log`, written inside `poll_portfolio`/`poll_balance` themselves; the
    registration's gap tripwires are the detection mechanism for a poller that
    keeps failing, and they only work if the loop survives to keep attempting.
    The catch-all below is therefore not swallowing errors -- it is what makes
    the error record complete. Only `CancelledError` exits, because the caller
    cancelling the task is the one legitimate way this loop ends.

    **Own connection, on purpose.** The chain runner's connection is used
    sequentially by its pass; sharing it from a concurrent task would
    interleave two transactions on one handle. A second connection in the same
    process is what WAL is for, and every connection already carries the busy
    timeout.

    **`alerter_factory` is a factory rather than an `Alerter`, for the reason
    `hedge_watch.watch_hedges_forever` takes one** (`scripts/run_loop.py`
    passes it `lambda watch_conn: Alerter(watch_conn, discord)`): an `Alerter`
    binds a connection, and this task owns the only connection it may use --
    the loop's own connection is used sequentially by its pass, and a
    concurrent task on that handle would interleave two transactions. Given
    `None`, every fee mismatch is still computed and logged at ERROR; nothing
    reaches a phone.

    **It is unwired in production as this lands**, and that is a lane boundary
    rather than a decision: `scripts/run_loop.py` constructs the `Alerter` and
    starts this task, and the session that wrote this could not edit it. One
    line there -- `poll_portfolio_forever(args.db, kalshi,
    alerter_factory=lambda poll_conn: Alerter(poll_conn, discord))` -- is what
    puts the alarm on the phone. Until that line exists this is the
    "built but never called" pattern `tasks/lessons.md` records, deliberately
    and with the remedy named.

    `sleep`, `clock` and `max_cycles` exist for tests. Production callers pass
    none of them.
    """
    conn = store_db.connect(db_path)
    alerter = alerter_factory(conn) if alerter_factory is not None else None
    try:
        last_mirror: Optional[float] = None
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            cycles += 1
            now = clock()
            now_ms = int(now * 1000)
            try:
                if last_mirror is None or now - last_mirror >= mirror_interval_s:
                    # **Which branch ran, in the data.** Both branches write
                    # `poll_log` rows stamped with this cycle's `now_ms` and
                    # nothing in them said whether the cycle was a mirror or a
                    # fast one -- so `lock-attribution`, which groups bursts by
                    # `DISTINCT polled_ms`, could not tell the two apart. §7 of
                    # `docs/measurements/2026-09-01-lock-holder-attribution-
                    # result.md` needs exactly that split: a post-fix burst
                    # after a MIRROR cycle is explained by the matcher's own
                    # loop and would not refute ADR 0091, so a forward
                    # registration cannot state a decision rule until the split
                    # exists. `endpoint` is free-form TEXT; no schema change.
                    #
                    # A branch marker, not a poll attempt: `ok = 1` records
                    # that the branch was entered, `row_count` is NULL because
                    # nothing was counted, and no consumer reads
                    # `endpoint = 'mirror'` -- every existing query filters on
                    # one of the four endpoint names or on `ok = 0`.
                    #
                    # Written BEFORE the mirror and committed immediately, for
                    # two reasons. A cycle that dies inside `poll_portfolio`
                    # was still a mirror cycle and is exactly the cycle a burst
                    # may follow, so an after-marker would go missing where it
                    # is most needed; and the commit is what keeps this INSERT
                    # from holding the write lock across the mirror's first
                    # round trip, which is the rule this module already states.
                    log_poll_attempt(
                        conn, now_ms=now_ms, endpoint="mirror", ok=True
                    )
                    conn.commit()
                    summary = await poll_portfolio(
                        conn, client, now_ms=now_ms, alerter=alerter
                    )
                    last_mirror = now
                    logger.info("portfolio mirror: %s", summary)
                else:
                    # **Each step commits before the next network call.**
                    # This branch runs every `balance_interval_s` -- 300s, so
                    # 288 times a day -- and until 2026-08-31 all four shared
                    # one transaction: `poll_balance` INSERTs, taking SQLite's
                    # write lock, and nothing released it until the commit
                    # below, THREE Kalshi round trips later. Any other writer
                    # landing in that window waited out `BUSY_TIMEOUT_MS` and
                    # raised `database is locked` -- most often
                    # `store_closing_line` on the scoring pass, which kills the
                    # whole pass and loses closing lines that cannot be
                    # re-observed.
                    #
                    # **The frequency is why this branch is the one that
                    # mattered.** `poll_portfolio` above had the identical
                    # shape and was fixed with it, but the mirror runs twice a
                    # day; this runs every five minutes. The observed failure
                    # rate (four to five a day) fits 288 windows and does not
                    # fit two.
                    result = await poll_balance(conn, client, now_ms=now_ms)
                    conn.commit()
                    # Fills ride the balance cadence (2026-08-21 ruling) so
                    # the landing screen's "tonight" strip is at most minutes
                    # behind the venue, not hours. See `poll_fills` for why
                    # this is not a registration amendment. Settlements ride
                    # it too (ADR 0064): the daily-loss kill switch reads the
                    # mirror and refuses when it is older than 30 minutes, so
                    # on the 12-hour clock alone the order path would be
                    # refused nearly all day -- see `poll_settlements`.
                    fee_checks: list = []
                    fills_result = await poll_fills(
                        conn, client, now_ms=now_ms, fee_checks=fee_checks
                    )
                    conn.commit()
                    settle_result = await poll_settlements(
                        conn, client, now_ms=now_ms
                    )
                    conn.commit()
                    # Positions ride it too (2026-08-29): the open-positions
                    # count on the landing screen is this endpoint's newest
                    # successful poll, and a hand bet placed at 8pm did not
                    # appear on it until the next mirror -- see
                    # `poll_positions` for why this is not an amendment
                    # either, and why `run_match_pass` did not come with it.
                    positions_result = await poll_positions(
                        conn, client, now_ms=now_ms
                    )
                    conn.commit()
                    # After every commit in this branch, never between them:
                    # the alert is a Discord round trip and this loop may not
                    # hold SQLite's write lock across one. See
                    # `reconcile_fill_fees`.
                    fee_result = await reconcile_fill_fees(
                        alerter, fee_checks, now_ms=now_ms
                    )
                    logger.debug(
                        "balance snapshot: %s; fills: %s; settlements: %s; "
                        "positions: %s; fees: %s",
                        result, fills_result, settle_result, positions_result,
                        fee_result,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 -- see the docstring
                logger.exception("portfolio poll cycle failed; loop continues")
            await sleep(balance_interval_s)
    finally:
        conn.close()
