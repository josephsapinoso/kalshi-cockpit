"""The live-money gate. Locked by default, and locked is the safe state.

Every condition here exists because the premise of this project is that the edge
is **unproven**. Kalshi's advantage is cost, not information; the venue lowers
the break-even bar from 52.38% to 51.75% and does not clear it for you. So the
gate does not ask "is this bet good?" — it asks "has this system demonstrated it
can tell?", and the answer is no until the record says otherwise.

Five conditions, and all must hold:

1. **≥300 scored *independent games*.** Practitioner consensus is 200–300
   minimum before closing-line value says anything, 500–1,000 before it
   predicts. An earlier draft of this project's own plan said ~50, which was
   wrong by an order of magnitude. Every recommendation is scored whether or not
   it was bet, which is what makes 300 reachable without 300 wagers — but the
   count is of *games*, not rows. The engine writes a fresh row on every pass,
   so one market polled thirty times is one observation recorded thirty times,
   and counting rows made the floor reachable from ~10 markets.
2. **CLV positive and surviving the noise guard.** Positive mean CLV inside two
   standard errors is not evidence, and a gate that opened on it would be
   opening on noise. The standard error is **cluster-robust**: rows are grouped
   by game before it is computed, because thirty rows scored against one closing
   line would otherwise shrink it by `sqrt(30)` for evidence that never grew.
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


@dataclass(frozen=True)
class ClusteredMean:
    """A mean and its standard error, computed over *clusters* of correlated rows.

    `n_rows` is how many recommendations were scored. `n_clusters` is how many
    independent things they say. Those are different numbers and the gap between
    them is the whole point of this dataclass — see `_cluster_robust_stderr`.
    """

    n_rows: int
    n_clusters: int
    mean_tenths: Optional[float]
    stderr_tenths: Optional[float]
    unclustered_rows: int = 0

    @property
    def distinguishable(self) -> bool:
        """Mean CLV clears two standard errors of zero, on the *clustered* error."""
        if self.mean_tenths is None or self.stderr_tenths is None:
            return False
        return self.mean_tenths > 2 * self.stderr_tenths


def _cluster_robust_stderr(
    clusters: list[tuple[int, float]],
) -> tuple[int, int, Optional[float], Optional[float]]:
    """Mean and cluster-robust standard error from `(k, sum_y)` per cluster.

    **Why this is not `sqrt(variance / n)`.**

    The engine writes a fresh recommendation row on every pass, so one market
    polled thirty times produces thirty rows. All thirty are scored against
    **one** closing line, so they are not thirty observations — they are one
    observation recorded thirty times. The classical standard error divides by
    `sqrt(n)` and therefore shrinks by `sqrt(30)` for evidence that has not
    grown at all. On the arming path for real money, an error understated by
    `sqrt(k)` is the difference between "locked" and "open".

    So the observations are clustered by game and the standard error is the
    usual sandwich estimator for a mean:

        Var(ybar) = G/(G-1) * sum_c ( sum_{i in c} (y_i - ybar) )^2 / N^2

    with `N` rows in `G` clusters. Two properties make this the right estimator
    rather than merely a more conservative one, and both are asserted as tests
    because each is fixed by definition rather than by judgement:

    - **Singleton clusters reproduce the classical result exactly.** With
      `G == N` the expression collapses to `s^2 / N`. Genuinely independent
      data is not penalised.
    - **Duplication changes nothing.** Replacing every observation with `k`
      identical copies leaves both the mean and the standard error bit-identical.
      That is the defect this replaces, stated as an invariant: the naive
      estimator returns `stderr / sqrt(k)` on that input.

    Returns `(n_rows, n_clusters, mean, stderr)`. Mean and stderr are `None`
    when fewer than two clusters exist — one cluster carries no information
    about between-cluster spread, and the caller refuses rather than
    substituting a number. See `tasks/lessons.md`.
    """
    n_rows = sum(k for k, _ in clusters)
    n_clusters = len(clusters)
    if n_rows == 0:
        return 0, 0, None, None

    mean = sum(total for _, total in clusters) / n_rows
    if n_clusters < 2:
        # One cluster is one observation. There is no between-cluster spread to
        # estimate, and a zero standard error would read as infinite confidence.
        return n_rows, n_clusters, mean, None

    # sum_{i in c} (y_i - ybar) == sum_y_c - k_c * ybar, so the per-row
    # deviations are never needed -- only each cluster's count and total.
    meat = sum((total - k * mean) ** 2 for k, total in clusters)
    variance = (n_clusters / (n_clusters - 1)) * meat / (n_rows * n_rows)
    if variance <= 0:
        return n_rows, n_clusters, mean, None
    return n_rows, n_clusters, mean, math.sqrt(variance)


def clustered_clv(conn) -> ClusteredMean:
    """Scored CLV, grouped into one cluster per game.

    The cluster key is the Kalshi **event** rather than the market ticker. A
    game's moneyline, spread and total all resolve from one final score and
    their closing lines move together, so counting them as three independent
    observations repeats the same mistake one level up. Both sides of a market
    likewise score against a single close.

    A market with no `event_ticker` falls back to its own ticker, which still
    collapses repeated polls of that market but cannot detect its correlation
    with siblings. That is a partial understatement rather than a silent one:
    the row count is carried on `unclustered_rows` and reported in the gate's
    detail string, because an unreported approximation in a money guard is
    indistinguishable from a correct one.
    """
    rows = conn.execute(
        """
        SELECT COALESCE(m.event_ticker, r.ticker) AS cluster_key,
               COUNT(*)             AS k,
               SUM(r.clv_tenths)    AS sum_y,
               SUM(CASE WHEN m.event_ticker IS NULL THEN 1 ELSE 0 END) AS orphans
        FROM recommendations r
        LEFT JOIN kalshi_markets m ON m.ticker = r.ticker
        WHERE r.clv_scored_ms IS NOT NULL AND r.clv_tenths IS NOT NULL
        GROUP BY cluster_key
        """
    ).fetchall()

    clusters = [(int(r["k"]), float(r["sum_y"])) for r in rows]
    n_rows, n_clusters, mean, stderr = _cluster_robust_stderr(clusters)
    return ClusteredMean(
        n_rows=n_rows,
        n_clusters=n_clusters,
        mean_tenths=mean,
        stderr_tenths=stderr,
        unclustered_rows=sum(int(r["orphans"]) for r in rows),
    )


def _clv_evidence(conn, minimum: int) -> tuple[Condition, Condition]:
    """Sample size and CLV significance, as two separate conditions.

    Separate because they fail for different reasons and are fixed in different
    ways: too few observations means keep recording, while a CLV inside the
    noise band means the strategy has not demonstrated anything yet.

    Both count **independent games**, not rows. The 300 floor comes from the
    practitioner benchmark for closing-line value, which is stated in bets — and
    a bet on a game you already bet is not a second data point about whether
    this system can pick.
    """
    stats = clustered_clv(conn)

    approximation = (
        f"; {stats.unclustered_rows} row(s) had no event ticker and were "
        f"clustered by market instead, which cannot see correlation between "
        f"a game's moneyline, spread and total"
        if stats.unclustered_rows
        else ""
    )

    met = stats.n_clusters >= minimum
    sample = Condition(
        name="scored_recommendations",
        met=met,
        detail=(
            f"{stats.n_clusters} of {minimum} independent games scored on CLV "
            f"({stats.n_rows} recommendation rows)"
            + (
                ""
                if met
                else " — keep recording; every recommendation is scored whether "
                     "or not it was bet, but repeated passes over the same game "
                     "score against one closing line and count once"
            )
            + approximation
        ),
    )

    if stats.mean_tenths is None or stats.stderr_tenths is None:
        return sample, Condition(
            name="clv_survives_noise_guard",
            met=False,
            detail=(
                f"no variance estimate from {stats.n_clusters} independent "
                f"game(s) across {stats.n_rows} row(s)"
            ),
        )

    # Two standard errors, computed from between-game spread. Positive-but-
    # inside-the-band is the case this exists to catch.
    distinguishable = stats.distinguishable
    return sample, Condition(
        name="clv_survives_noise_guard",
        met=distinguishable,
        detail=(
            f"mean CLV {stats.mean_tenths / 10:+.2f}c, standard error "
            f"{stats.stderr_tenths / 10:.2f}c across {stats.n_clusters} "
            f"independent games"
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
