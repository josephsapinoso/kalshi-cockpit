"""The live-money gate. Locked by default, and locked is the safe state.

Every condition here exists because the premise of this project is that the edge
is **unproven**. Kalshi's advantage is cost, not information; the venue lowers
the break-even bar from 52.38% to 51.75% and does not clear it for you. So the
gate does not ask "is this bet good?" — it asks "has this system demonstrated it
can tell?", and the answer is no until the record says otherwise.

Five conditions, and all must hold:

1. **≥300 scored recommendations.** Practitioner consensus is 200–300 minimum
   before closing-line value says anything, 500–1,000 before it predicts. An
   earlier draft of this project's own plan said ~50, which was wrong by an
   order of magnitude. Every recommendation is scored whether or not it was bet,
   which is what makes 300 reachable without 300 wagers.
2. **CLV positive and surviving the noise guard.** Positive mean CLV inside two
   standard errors is not evidence, and a gate that opened on it would be
   opening on noise.
3. **`fee_predicted == fee_actual` on every recorded fill.** The fee model is
   still a hedge between two disagreeing sources. A mismatch means every EV
   figure in the system is wrong by an unknown amount, so this is stop-the-line.
4. **Data fresh at the moment of the order.** Not when the page rendered.
5. **`LIVE_TRADING_ENABLED`.** A deliberate human act, separate from the
   evidence conditions, so satisfying the statistics does not by itself arm the
   system.

Why this is re-checked server-side
----------------------------------
The Board greys out a stale opportunity and disables the button. That is a hint
to a human, not a control. Anything reachable over HTTP is reachable by a stale
tab, a replayed request, or a mistake, so the order endpoint evaluates all five
conditions again against the database at the instant of the request.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Optional

from .config import GateConfig, StalenessConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Condition:
    name: str
    met: bool
    detail: str


@dataclass(frozen=True)
class GateDecision:
    conditions: tuple[Condition, ...]

    @property
    def open(self) -> bool:
        return all(condition.met for condition in self.conditions)

    @property
    def unmet(self) -> tuple[Condition, ...]:
        return tuple(c for c in self.conditions if not c.met)

    @property
    def reason(self) -> str:
        """Why it is locked, naming every unmet condition.

        All of them, not the first. "Fix this one thing" invites a loop of
        discovering the next one, and the distance from open is the useful
        information.
        """
        if self.open:
            return "All conditions met."
        return " | ".join(f"{c.name}: {c.detail}" for c in self.unmet)

    def to_dict(self) -> dict[str, Any]:
        return {
            "open": self.open,
            "conditions": [
                {"name": c.name, "met": c.met, "detail": c.detail}
                for c in self.conditions
            ],
            "reason": self.reason,
        }


def _clv_evidence(conn, minimum: int) -> tuple[Condition, Condition]:
    """Sample size and CLV significance, as two separate conditions.

    Separate because they fail for different reasons and are fixed in different
    ways: too few observations means keep recording, while a CLV inside the
    noise band means the strategy has not demonstrated anything yet.
    """
    row = conn.execute(
        """
        SELECT COUNT(*) AS n,
               AVG(clv_tenths) AS mean_tenths,
               -- Sample standard deviation, for the standard error below.
               CASE WHEN COUNT(*) > 1 THEN
                 (SUM(clv_tenths * clv_tenths) - COUNT(*) * AVG(clv_tenths) * AVG(clv_tenths))
                 / (COUNT(*) - 1)
               END AS variance
        FROM recommendations
        WHERE clv_scored_ms IS NOT NULL AND clv_tenths IS NOT NULL
        """
    ).fetchone()

    n = row["n"] or 0
    sample = Condition(
        name="scored_recommendations",
        met=n >= minimum,
        detail=(
            f"{n} of {minimum} scored on CLV"
            + ("" if n >= minimum else " — keep recording; every recommendation "
                                       "is scored whether or not it was bet")
        ),
    )

    mean = row["mean_tenths"]
    variance = row["variance"]
    if n < 2 or mean is None or variance is None or variance <= 0:
        return sample, Condition(
            name="clv_survives_noise_guard",
            met=False,
            detail=f"no variance estimate from {n} observation(s)",
        )

    stderr = math.sqrt(variance / n)
    # Two standard errors, computed from the observed spread. Positive-but-
    # inside-the-band is the case this exists to catch.
    distinguishable = mean > 2 * stderr
    return sample, Condition(
        name="clv_survives_noise_guard",
        met=distinguishable,
        detail=(
            f"mean CLV {mean / 10:+.2f}c, standard error {stderr / 10:.2f}c"
            + (
                " — clears two standard errors"
                if distinguishable
                else " — (noise): inside two standard errors of zero, so this "
                     "is not evidence of an edge"
            )
        ),
    )


def _fee_model_verified(conn) -> Condition:
    row = conn.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN ABS(fee_actual - fee_predicted) > 0.005
                        THEN 1 ELSE 0 END) AS mismatched
        FROM fills
        WHERE fee_actual IS NOT NULL
        """
    ).fetchone()

    total = row["total"] or 0
    mismatched = row["mismatched"] or 0

    if total == 0:
        # Not a pass. With no fills the model is an untested hedge between two
        # sources that disagree, and calling that "verified" would be the
        # convenient reading of an absence.
        return Condition(
            name="fee_model_verified",
            met=False,
            detail=(
                "no fills yet — the fee model is still an unresolved hedge "
                "between two disagreeing sources, charging the most expensive "
                "candidate. It cannot be verified without ground truth."
            ),
        )

    return Condition(
        name="fee_model_verified",
        met=mismatched == 0,
        detail=(
            f"model matches Kalshi on all {total} fills"
            if mismatched == 0
            else f"MISMATCH on {mismatched} of {total} fills — every EV figure "
                 f"in the system is wrong until core/fees.py is corrected"
        ),
    )


def evaluate_gate(
    conn,
    gate: GateConfig,
    *,
    staleness: Optional[StalenessConfig] = None,
    kalshi_quote_age_ms: Optional[int] = None,
    odds_age_ms: Optional[int] = None,
) -> GateDecision:
    """Evaluate every condition. Freshness is only checked when ages are given.

    The Gate *screen* calls this without ages — it reports standing readiness.
    The order endpoint calls it with the ages of the specific quotes behind the
    specific order, because freshness is a property of one decision at one
    instant, not of the system.
    """
    sample, noise = _clv_evidence(conn, gate.min_scored_recommendations)

    conditions = [
        sample,
        noise,
        _fee_model_verified(conn),
        Condition(
            name="config_enabled",
            met=gate.live_trading_enabled,
            detail=(
                "LIVE_TRADING_ENABLED is on"
                if gate.live_trading_enabled
                else "LIVE_TRADING_ENABLED is off — arming is a deliberate human "
                     "act, kept separate from the evidence conditions"
            ),
        ),
    ]

    if kalshi_quote_age_ms is not None or odds_age_ms is not None:
        limits = staleness or StalenessConfig.load()
        quote_age = kalshi_quote_age_ms if kalshi_quote_age_ms is not None else 1 << 62
        book_age = odds_age_ms if odds_age_ms is not None else 1 << 62
        quote_ok = quote_age <= limits.max_kalshi_quote_age_s * 1000
        book_ok = book_age <= limits.max_odds_age_s * 1000
        conditions.append(
            Condition(
                name="data_fresh",
                met=quote_ok and book_ok,
                detail=(
                    f"Kalshi quote {quote_age / 1000:.0f}s old "
                    f"(limit {limits.max_kalshi_quote_age_s}s), "
                    f"odds {book_age / 1000:.0f}s old "
                    f"(limit {limits.max_odds_age_s}s)"
                ),
            )
        )

    return GateDecision(conditions=tuple(conditions))


def recommendation_freshness(conn, recommendation_id: int) -> dict[str, Any]:
    """Ages for one recommendation, measured **now** rather than when it was made.

    The subtlety that makes this function necessary: `recommendations` stores
    `kalshi_quote_age_ms` and `odds_age_ms` as ages *at the moment the
    recommendation was written*. Reading those columns straight out and
    comparing them to the staleness limits would pass forever — a recommendation
    made yesterday against a 3-second-old quote still says "3 seconds", and the
    freshness gate would wave through a day-old price.

    So the observation instant is reconstructed (`created_ms - stored_age`) and
    the age recomputed against the clock. A missing row or a missing age
    resolves to `None`, and the caller must refuse on it rather than substitute
    zero.
    """
    row = conn.execute(
        """
        SELECT id, ticker, created_ms, entry_ask_tenths, side,
               kalshi_quote_age_ms, odds_age_ms, suppressed_reason,
               suggested_contracts
        FROM recommendations WHERE id = ?
        """,
        (recommendation_id,),
    ).fetchone()

    if row is None:
        return {"found": False}

    now_ms = int(time.time() * 1000)
    elapsed = now_ms - row["created_ms"]

    def age_now(stored_age: Optional[int]) -> Optional[int]:
        if stored_age is None:
            return None
        return elapsed + stored_age

    return {
        "found": True,
        "ticker": row["ticker"],
        "side": row["side"],
        "entry_ask_tenths": row["entry_ask_tenths"],
        "suppressed_reason": row["suppressed_reason"],
        "suggested_contracts": row["suggested_contracts"],
        "created_ms": row["created_ms"],
        "kalshi_quote_age_ms": age_now(row["kalshi_quote_age_ms"]),
        "odds_age_ms": age_now(row["odds_age_ms"]),
    }
