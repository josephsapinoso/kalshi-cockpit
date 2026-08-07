"""Closing-line value: scoring every recommendation against Kalshi's own close.

**Why CLV rather than profit.** Distinguishing a 52% win rate from 50% takes on
the order of a thousand bets. Whether you consistently got a better price than
the market settled on is visible far sooner -- still 200-300 observations, but
that is reachable. It is the fastest honest signal available.

**Why Kalshi's close and not the sportsbook's.** The question this project
actually asks is "do I beat *Kalshi*". Measuring against a sportsbook close
would answer a different question, and would be circular anyway, since the
sportsbook consensus is what generated the recommendation.

**Why every recommendation, bet or not.** A recommendation that was suppressed
still had a price and a fair estimate, so it can still be scored. Scoring only
placed bets would mean 300 observations requires 300 wagers; scoring everything
means the evidence accumulates from day one at no risk. It also lets a
suppression rule be evaluated: if rows rejected for `wide_market` turn out to
have had good CLV, that rule is costing money.

The horizon is a first-class parameter
--------------------------------------
`quote_before_close` reads a candlestick at a fixed interval *before* close,
never `last_price`. The last trade in a settled market usually happens after
the outcome is effectively known, so anything measured against it is
convergence, not edge.

Because the horizon is a choice, it is stored on every row. **Re-run at a
second horizon: if the result moves, it was convergence.** That check is only
possible because the horizon is a column rather than a constant.

The entry must precede the close
--------------------------------
A recommendation is only scoreable against a closing line observed **at or
after** the moment the recommendation was made. The runner records right up to
kickoff and the 1h line is read an hour before it, so without this rule every
late recommendation would be scored against a price that did not exist when the
decision was taken. Whether that flatters or punishes depends purely on which
way the market drifted in between — which puts drift directly into the number
that is supposed to detect edge.

The cost is stated rather than hidden: late recommendations go unscored at a
given horizon, so the scored sample skews early.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Sequence

from ..core.prices import PRICE_MAX, dollars_to_tenths
from ..store.db import now_ms

logger = logging.getLogger(__name__)

DEFAULT_HORIZON_HOURS = 1.0
# A second horizon, run alongside the first. If a finding survives one and not
# the other, it was convergence.
CONTROL_HORIZON_HOURS = 6.0


@dataclass(frozen=True)
class ClosingLine:
    ticker: str
    horizon_hours: float
    observed_ms: int
    yes_bid_tenths: Optional[int]
    yes_ask_tenths: Optional[int]

    @property
    def mid_tenths(self) -> Optional[float]:
        """Midpoint, used only as the CLV reference.

        A mid is not a tradeable price and must never be used to *enter* a
        position -- but as a reference for where the market settled it is the
        right measure, because using the ask would systematically flatter a
        buyer's CLV.
        """
        if self.yes_bid_tenths is None or self.yes_ask_tenths is None:
            return None
        return (self.yes_bid_tenths + self.yes_ask_tenths) / 2


def parse_candlestick(candle: dict) -> tuple[Optional[int], Optional[int]]:
    """Extract closing yes bid/ask from one candlestick, in tenths.

    Kalshi's candlestick payload nests open/high/low/close per side. Missing
    values return None rather than 0 -- a settled loser genuinely trades at 0,
    so a zero substituted for "unreadable" is indistinguishable from real data.
    """
    def _close(block) -> Optional[int]:
        if not isinstance(block, dict):
            return None
        value = block.get("close")
        if value is None:
            return None
        # Candlesticks quote whole cents on this endpoint.
        if isinstance(value, (int, float)) and float(value).is_integer():
            return int(value) * 10
        return dollars_to_tenths(value)

    return _close(candle.get("yes_bid")), _close(candle.get("yes_ask"))


def clv_tenths(entry_ask_tenths: int, closing_mid_tenths: float, side: str) -> float:
    """Closing-line value in tenths of a cent. Positive means you beat the close.

    `entry_ask_tenths` is the price paid **for the side actually taken**, not a
    YES-denominated price -- see `schema.sql` ("the price we would ACTUALLY
    pay: the derived ask") and `core/ev.py`, which computes edge against the
    probability of the side taken. `closing_mid_tenths` is a **YES** mid.

    So both sides are the same statement: what the position is worth at the
    close, minus what it cost.

    - YES: worth `close`, cost `a`            -> `close - a`
    - NO:  worth `1000 - close`, cost `a`     -> `(1000 - close) - a`

    A NO bought at 48c on a market closing at 52c YES is worth 48c: closing-line
    value exactly zero, not -4c.

    An earlier version returned `a - close` for the NO side, which is wrong by
    `1000 - 2a` -- up to a dollar, and zero only at exactly 50c. It was wrong in
    both directions at once: NO bets under 50c got a large spurious negative and
    NO bets over 50c a large spurious positive. Its sensitivity to `close` was
    correct, so nothing in the output looked wrong, and the test asserted the
    same mistake. This contaminated the gate, `mart_clv_by_bucket`,
    `mart_suppression_audit` and `horizons_agree` -- the entire primary evidence
    path.
    """
    if side == "yes":
        return closing_mid_tenths - entry_ask_tenths
    if side == "no":
        return (PRICE_MAX - closing_mid_tenths) - entry_ask_tenths
    raise ValueError(f"side must be 'yes' or 'no', got {side!r}")


def store_closing_line(conn, line: ClosingLine) -> int:
    """Persist a closing line. Idempotent per (ticker, horizon)."""
    conn.execute(
        "INSERT INTO closing_lines (ticker, horizon_hours, observed_ms, "
        "yes_bid_tenths, yes_ask_tenths) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(ticker, horizon_hours) DO UPDATE SET "
        "observed_ms = excluded.observed_ms, "
        "yes_bid_tenths = excluded.yes_bid_tenths, "
        "yes_ask_tenths = excluded.yes_ask_tenths",
        (
            line.ticker, line.horizon_hours, line.observed_ms,
            line.yes_bid_tenths, line.yes_ask_tenths,
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM closing_lines WHERE ticker = ? AND horizon_hours = ?",
        (line.ticker, line.horizon_hours),
    ).fetchone()
    return int(row["id"])


def score_recommendations(
    conn, *, horizon_hours: float = DEFAULT_HORIZON_HOURS, scored_ms: Optional[int] = None
) -> dict[str, int]:
    """Score every unscored recommendation that has a closing line.

    Scores **suppressed rows too**. They had a price and a fair estimate, so
    they carry information -- and scoring them is what makes a suppression rule
    auditable rather than an article of faith.
    """
    stamp = scored_ms if scored_ms is not None else now_ms()

    rows = conn.execute(
        "SELECT r.id, r.ticker, r.side, r.entry_ask_tenths, r.created_ms, "
        "c.id AS closing_id, c.observed_ms AS closing_observed_ms, "
        "c.yes_bid_tenths, c.yes_ask_tenths "
        "FROM recommendations r "
        "JOIN closing_lines c ON c.ticker = r.ticker "
        "WHERE r.clv_scored_ms IS NULL AND c.horizon_hours = ?",
        (horizon_hours,),
    ).fetchall()

    counts = {"scored": 0, "skipped_no_mid": 0, "skipped_entry_after_close": 0}

    for row in rows:
        # **The entry must precede the close it is scored against.**
        #
        # The closing line is read at `commence - horizon`, and the runner keeps
        # recording right up to kickoff, so at a 1h horizon every recommendation
        # made in the final hour would otherwise be scored against a price
        # observed *before it existed*. That is not merely meaningless: whether
        # it flatters or punishes depends entirely on which way the market
        # drifted in between, so it injects drift straight into the measurement
        # that is supposed to detect edge.
        #
        # Excluded rather than scored, and counted so the exclusion is visible.
        # Note the cost, because it is a real one: this systematically drops
        # *late* recommendations at this horizon, so the scored sample skews
        # early. They remain unscored and are candidates for a shorter horizon
        # rather than lost.
        if row["created_ms"] > row["closing_observed_ms"]:
            counts["skipped_entry_after_close"] += 1
            continue

        if row["yes_bid_tenths"] is None or row["yes_ask_tenths"] is None:
            counts["skipped_no_mid"] += 1
            continue
        mid = (row["yes_bid_tenths"] + row["yes_ask_tenths"]) / 2
        value = clv_tenths(row["entry_ask_tenths"], mid, row["side"])

        conn.execute(
            "UPDATE recommendations SET clv_tenths = ?, closing_line_id = ?, "
            "clv_scored_ms = ? WHERE id = ?",
            (value, row["closing_id"], stamp, row["id"]),
        )
        counts["scored"] += 1

    conn.commit()
    logger.info("CLV scoring at %.1fh horizon: %s", horizon_hours, counts)
    return counts


def load_observations(conn, *, group_by: str = "all") -> list:
    """Load scored recommendations as `validate.Observation` records.

    `group_by` picks the subgroup key for the pooling check -- `league`,
    `strategy_config_version`, or `all` for none. Pooling across the wrong axis
    is how Simpson's paradox hides.
    """
    from .validate import Observation

    group_sql = {
        "all": "'all'",
        "config": "CAST(r.strategy_config_version AS TEXT)",
        "league": "COALESCE(s.league, 'unknown')",
        "suppressed": "COALESCE(r.suppressed_reason, 'surfaced')",
    }.get(group_by, "'all'")

    rows = conn.execute(
        f"SELECT r.entry_ask_tenths, r.clv_tenths, {group_sql} AS grp, "
        "st.result AS settlement_result, st.pnl_cents, r.side "
        "FROM recommendations r "
        "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
        "LEFT JOIN kalshi_series s ON s.series_ticker = m.series_ticker "
        "LEFT JOIN settlements st ON st.ticker = r.ticker "
        "WHERE r.clv_scored_ms IS NOT NULL"
    ).fetchall()

    observations = []
    for row in rows:
        settled_win: Optional[bool] = None
        if row["settlement_result"] is not None:
            settled_win = row["settlement_result"] == row["side"]
        observations.append(
            Observation(
                entry_ask_tenths=row["entry_ask_tenths"],
                group=row["grp"],
                clv_tenths=row["clv_tenths"],
                settled_win=settled_win,
                pnl_cents=row["pnl_cents"],
            )
        )
    return observations


def horizons_agree(
    conn, *, primary: float = DEFAULT_HORIZON_HOURS, control: float = CONTROL_HORIZON_HOURS
) -> Optional[dict]:
    """Compare mean CLV at two horizons.

    **If the result moves between horizons, it was convergence rather than
    edge.** This is the check the previous project added `--hours-before` for,
    and it is the single cheapest way to catch a contaminated measurement.

    Returns None when either horizon lacks data -- an honest "cannot tell".
    """
    def _mean(horizon: float) -> Optional[tuple[float, int]]:
        row = conn.execute(
            "SELECT AVG(c.yes_bid_tenths + c.yes_ask_tenths) / 2.0 "
            "     - AVG(r.entry_ask_tenths) AS delta, COUNT(*) AS n "
            "FROM recommendations r JOIN closing_lines c ON c.ticker = r.ticker "
            "WHERE c.horizon_hours = ? AND c.yes_bid_tenths IS NOT NULL "
            "  AND c.yes_ask_tenths IS NOT NULL AND r.side = 'yes' "
            # Same rule as `score_recommendations`, and it matters more here:
            # this compares a 1h horizon against a 6h one, and the 6h line is
            # observed five hours earlier. Without this the two horizons would
            # include different populations of recommendations -- the longer one
            # excluding more of them -- so the "drift" being measured would be
            # partly a change in which rows were counted.
            "  AND r.created_ms <= c.observed_ms",
            (horizon,),
        ).fetchone()
        if not row or not row["n"]:
            return None
        return float(row["delta"] or 0.0), int(row["n"])

    a, b = _mean(primary), _mean(control)
    if a is None or b is None:
        return None

    drift = abs(a[0] - b[0])
    return {
        "primary_horizon_hours": primary,
        "primary_mean_tenths": a[0],
        "primary_n": a[1],
        "control_horizon_hours": control,
        "control_mean_tenths": b[0],
        "control_n": b[1],
        "drift_tenths": drift,
        # A tenth of a cent of drift per bet is already the same order as the
        # edge being hunted.
        "consistent": drift < 10.0,
        "note": (
            "Consistent across horizons."
            if drift < 10.0
            else "MOVES between horizons -- this is convergence, not edge."
        ),
    }
