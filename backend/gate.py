"""The live-money gate. Locked by default, and locked is the safe state.

Every condition here exists because the premise of this project is that the edge
is **unproven**. Kalshi's advantage is cost, not information; the venue lowers
the break-even bar from 52.38% to 52.00% and does not clear it for you. So the
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
2. **CLV positive and surviving the noise guard.** A positive mean CLV inside
   the noise band is not evidence, and a gate that opened on it would be opening
   on noise. Two corrections apply, and they compound:

   - The standard error is **cluster-robust**: rows are grouped by game before
     it is computed, because thirty rows scored against one closing line would
     otherwise shrink it by `sqrt(30)` for evidence that never grew.
   - The boundary is **always-valid**, not two standard errors. This function is
     re-evaluated on every request against a growing record, and under a
     zero-edge process a running two-standard-error test crosses eventually with
     probability 1 — measured at 13.7% within 100 looks. See
     `always_valid_multiplier`.
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
from .core.fees import FEE_MATCH_TOLERANCE_DOLLARS

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


# Level for the always-valid bound below. 0.05 is the conventional choice and is
# the one the 300-observation floor was reasoned about under.
ALWAYS_VALID_ALPHA = 0.05


def always_valid_multiplier(
    n_clusters: int, *, tuning: int, alpha: float = ALWAYS_VALID_ALPHA
) -> float:
    """Standard errors required to clear zero, valid at **every** sample size.

    **The problem this solves.** `evaluate_gate` runs on every request against a
    database that grows all day. A fixed-sample threshold of two standard errors
    is a statement about *one* pre-registered look. Under a true zero-edge
    process the running z-score wanders, and the probability that it *ever*
    crosses 2 tends to 1 — so a gate that re-checks continuously and opens the
    first time the test passes will eventually open on nothing. This is the
    multiple-comparisons lesson (`tasks/lessons.md`, 2026-08-07) applied along
    the time axis instead of across buckets, on the path that arms real money.

    **The fix.** A confidence sequence: a boundary that holds simultaneously for
    all `n`, so looking whenever you like costs nothing. This is the Robbins
    normal-mixture boundary,

        P( exists n : |S_n| >= sqrt( (n+m) * (ln((n+m)/m) + 2*ln(1/alpha)) ) ) <= alpha

    divided through by `n` to put it on the mean. `m` is the mixture parameter,
    setting the scale over which the boundary is efficient; it is tied to the
    pre-registered floor (300 games) so the bound is near its best across the
    range the gate actually operates in. Measured, with `m = 300`:

        n:     20     100     300    1000    2464    5000   100000
        mult:  9.84    5.01    3.66    3.11    3.04    3.07     3.44

    Note the multiplier is *not* minimised at `n == m` — it bottoms out near
    `n ≈ 8m` and then climbs like `sqrt(log n)`. It never approaches 2 at any
    sample size, which is the property that matters: there is no `n` at which
    this quietly degrades into the fixed-sample rule.

    **The price, stated plainly.** At the floor the multiplier is 3.66 rather
    than 2, so unlimited peeking costs about 1.8x the effect size. On simulated
    zero-edge data looked at 100 times, the fixed-sample rule fires on 13.7% of
    sequences and this bound on 0%. That is the honest cost of being allowed to
    look continuously, and it is much cheaper than a gate that opens on nothing.

    **What this does not establish.** The boundary assumes the clustered
    observations are independent across games and identically distributed. It
    does not correct for the *strategy* changing between looks — a config
    version bump makes the sequence a different sequence, which
    `strategy_config_version` records but this function does not read.
    """
    if n_clusters < 1:
        raise ValueError("n_clusters must be at least 1")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    if tuning < 1:
        raise ValueError("tuning must be at least 1")

    total = n_clusters + tuning
    radicand = (total / n_clusters) * (
        math.log(total / tuning) + 2.0 * math.log(1.0 / alpha)
    )
    return math.sqrt(radicand)


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

    def multiplier(self, tuning: int, alpha: float = ALWAYS_VALID_ALPHA) -> Optional[float]:
        """How many standard errors this evaluation has to clear.

        Not 2. See `always_valid_multiplier` — the gate is evaluated on every
        request against a growing database, and a fixed-sample threshold is not
        valid under repeated looks.
        """
        if self.n_clusters < 2:
            return None
        return always_valid_multiplier(self.n_clusters, tuning=tuning, alpha=alpha)

    def threshold_tenths(self, tuning: int, alpha: float = ALWAYS_VALID_ALPHA) -> Optional[float]:
        """The always-valid boundary, in tenths of a cent."""
        m = self.multiplier(tuning, alpha)
        if m is None or self.stderr_tenths is None:
            return None
        return m * self.stderr_tenths

    def distinguishable(self, tuning: int, alpha: float = ALWAYS_VALID_ALPHA) -> bool:
        """Mean CLV clears the always-valid boundary, on the *clustered* error."""
        threshold = self.threshold_tenths(tuning, alpha)
        if self.mean_tenths is None or threshold is None:
            return False
        return self.mean_tenths > threshold


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


# The three populations a scored row can belong to, as SQL predicates.
#
# These are the same three the Discord digest already reports -- surfaced,
# no edge, suppressed -- so the gate and the digest cannot describe the record
# differently.
#
#   actionable  the strategy would have bet this. Not suppressed, and sized to
#               at least one contract.
#   no_edge     nothing to bet. Not suppressed, sized to zero. This is the
#               normal answer on most of a slate and is *not* a rejection:
#               `tasks/lessons.md`, "no result and rejected are different
#               outcomes".
#   suppressed  considered and refused, with a reason.
#
# `POPULATIONS` is exhaustive and mutually exclusive by construction --
# `suppressed_reason IS NULL` splits on `suggested_contracts > 0`, and its
# complement is the third. A test asserts the parts sum to the pooled row count,
# because a population split that quietly drops rows is worse than no split.
POPULATIONS: dict[str, str] = {
    "actionable": "r.suppressed_reason IS NULL AND r.suggested_contracts > 0",
    "no_edge": "r.suppressed_reason IS NULL AND r.suggested_contracts <= 0",
    "suppressed": "r.suppressed_reason IS NOT NULL",
}


def clustered_clv(conn, population: Optional[str] = None) -> ClusteredMean:
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

    `population` selects one of `POPULATIONS`; `None` pools all three, which is
    what this function did unconditionally and what made the gate's headline
    number a mixture. **The pooled number is not the strategy's CLV.** It is the
    closing-line behaviour of every Kalshi market this instance happened to
    poll, including the rows the strategy explicitly refused, and the first live
    digest read `16 / 300` almost entirely from those. Callers wanting a claim
    about *this strategy* want `"actionable"`.
    """
    predicate = ""
    if population is not None:
        if population not in POPULATIONS:
            # Refuse rather than silently pooling. A typo that fell through to
            # "all" would report the mixture under a group's name, which is the
            # exact confusion this parameter exists to end.
            raise ValueError(
                f"unknown population {population!r}; "
                f"expected one of {sorted(POPULATIONS)}"
            )
        predicate = f"AND {POPULATIONS[population]}"

    rows = conn.execute(
        f"""
        SELECT COALESCE(m.event_ticker, r.ticker) AS cluster_key,
               COUNT(*)             AS k,
               SUM(r.clv_tenths)    AS sum_y,
               SUM(CASE WHEN m.event_ticker IS NULL THEN 1 ELSE 0 END) AS orphans
        FROM recommendations r
        LEFT JOIN kalshi_markets m ON m.ticker = r.ticker
        WHERE r.clv_scored_ms IS NOT NULL AND r.clv_tenths IS NOT NULL
        {predicate}
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


def clv_by_population(conn) -> dict[str, ClusteredMean]:
    """Every population's CLV, side by side, plus the pooled mixture.

    **A pooled number is not a finding until the parts agree** — the repo's own
    measurement rule, and the reason this exists. The gate's headline has always
    been the pooled figure, which on the live record is drawn overwhelmingly
    from rows the strategy rejected. Dilution toward zero would merely be
    conservative; a *systematic* CLV in the suppressed group moves the pooled
    mean instead of blunting it, and `suspicious_edge` rows are exactly the
    population most likely to carry one.

    Note that `n` here is independent games per group, and the groups do **not**
    partition the games — one game can contribute an actionable row and a
    suppressed row, so the per-group cluster counts can sum to more than the
    pooled count. Only the *row* counts partition, which is what the
    reconciliation test asserts.
    """
    grouped = {name: clustered_clv(conn, name) for name in POPULATIONS}
    grouped["pooled"] = clustered_clv(conn)
    return grouped


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
    groups = clv_by_population(conn)
    stats = groups["pooled"]

    approximation = (
        f"; {stats.unclustered_rows} row(s) had no event ticker and were "
        f"clustered by market instead, which cannot see correlation between "
        f"a game's moneyline, spread and total"
        if stats.unclustered_rows
        else ""
    )

    # The composition, beside the aggregate, always. The first live digest read
    # "16 / 300" from a pool with no filter on `suppressed_reason`, so the label
    # said "our edge" and the number described the closing-line behaviour of any
    # market this instance happened to poll. Printing the parts is what makes
    # the mixture visible without yet changing which population the floor
    # counts -- that decision needs these numbers first.
    composition = "; " + ", ".join(
        f"{name} {groups[name].n_clusters}g/{groups[name].n_rows}r"
        for name in POPULATIONS
    )
    actionable = groups["actionable"]
    if actionable.n_rows == 0 and stats.n_rows > 0:
        composition += (
            " — none of this is actionable: every scored row was refused or had "
            "no edge, so this number is not a measurement of the strategy"
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
            + composition
            + approximation
        ),
    )

    threshold = stats.threshold_tenths(minimum)
    if stats.mean_tenths is None or stats.stderr_tenths is None or threshold is None:
        return sample, Condition(
            name="clv_survives_noise_guard",
            met=False,
            detail=(
                f"no variance estimate from {stats.n_clusters} independent "
                f"game(s) across {stats.n_rows} row(s)"
            ),
        )

    # The boundary is always-valid rather than fixed-sample: this function runs
    # on every request against a growing record, and under a zero-edge process a
    # running two-standard-error test crosses eventually with probability 1.
    distinguishable = stats.distinguishable(minimum)
    multiplier = stats.multiplier(minimum) or 0.0
    return sample, Condition(
        name="clv_survives_noise_guard",
        met=distinguishable,
        detail=(
            f"mean CLV {stats.mean_tenths / 10:+.2f}c, standard error "
            f"{stats.stderr_tenths / 10:.2f}c across {stats.n_clusters} "
            f"independent games; needs {stats.threshold_tenths(minimum) / 10:.2f}c "
            f"to clear the always-valid bound ({multiplier:.2f} standard errors, "
            f"not 2, because the gate is re-evaluated on every request)"
            + (
                " — clears it"
                if distinguishable
                else " — (noise): inside the bound, so this is not evidence of "
                     "an edge"
            )
        ),
    )


def _fee_model_verified(conn) -> Condition:
    row = conn.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN ABS(fee_actual - fee_predicted) > ?
                        THEN 1 ELSE 0 END) AS mismatched
        FROM fills
        WHERE fee_actual IS NOT NULL
        """,
        (FEE_MATCH_TOLERANCE_DOLLARS,),
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


@dataclass(frozen=True)
class LiveAges:
    """How old a recommendation's two inputs are **now**, and what said so.

    `confirmed` is carried rather than inferred because the two bases mean
    different things to a reader: an unconfirmed row is as old as its decision,
    a confirmed one is as old as the last time that decision was re-derived.
    """

    quote_age_ms: Optional[int]
    odds_age_ms: Optional[int]
    measured_from_ms: int
    confirmed: bool


def _optional_column(row, name: str) -> Optional[int]:
    """A column that may not exist on this row, as `None` rather than an error.

    `recommendation_freshness` names its columns and the API selects `r.*`, but
    tests and older callers build rows by hand. A missing column is the same
    state as a NULL one -- never confirmed -- and both fall back to `created_ms`.
    """
    try:
        keys = row.keys()
    except AttributeError:
        keys = row.keys() if isinstance(row, dict) else ()
    if name not in keys:
        return None
    value = row[name]
    return None if value is None else int(value)


def live_ages(row, *, now_ms: int) -> LiveAges:
    """Both stored ages, moved forward to `now_ms`. **The only implementation.**

    The subtlety that makes this necessary: `recommendations` stores
    `kalshi_quote_age_ms` and `odds_age_ms` as ages *at the moment the row was
    written*. Reading those columns straight out and comparing them to the
    staleness limits passes forever -- a recommendation made yesterday against a
    3-second-old quote still says "3 seconds". So the observation instant is
    reconstructed and the age is measured against the clock.

    **A confirmation replaces the basis, and replaces both halves of it.** When
    `persist_if_changed` re-derives an identical decision it stamps the row with
    that pass's instant and *both* of that pass's ages, so freshness is measured
    from the last time the numbers were checked rather than from the first time
    they were written. Taking the confirmation's quote age while leaving the
    odds age on `created_ms` would be the tempting half-fix and the dangerous
    one: the odds are the fifteen-minute limit, and a row confirmed every twenty
    seconds would then stay bettable indefinitely on a consensus that had aged
    out hours ago. Either both ages come from the confirmation or neither does.

    An incomplete confirmation -- a timestamp with a missing age -- falls back to
    `created_ms` rather than substituting. Refusing to trust a half-written
    confirmation is the same rule as refusing an unreadable price.

    A `None` age means unreadable, and the caller must refuse on it rather than
    treat it as fresh. See `tasks/lessons.md`.
    """
    basis = int(row["created_ms"])
    quote_stored = _optional_column(row, "kalshi_quote_age_ms")
    odds_stored = _optional_column(row, "odds_age_ms")
    confirmed = False

    confirmed_ms = _optional_column(row, "last_confirmed_ms")
    confirmed_quote = _optional_column(row, "last_confirmed_quote_age_ms")
    confirmed_odds = _optional_column(row, "last_confirmed_odds_age_ms")
    if (
        confirmed_ms is not None
        and confirmed_quote is not None
        and confirmed_odds is not None
        # A confirmation before the decision is not a confirmation. It would
        # move the basis backwards and make the row look older, which is the
        # safe direction but still a state nothing should produce.
        and confirmed_ms >= basis
    ):
        basis, quote_stored, odds_stored = confirmed_ms, confirmed_quote, confirmed_odds
        confirmed = True

    elapsed = now_ms - basis
    return LiveAges(
        quote_age_ms=None if quote_stored is None else int(elapsed + quote_stored),
        odds_age_ms=None if odds_stored is None else int(elapsed + odds_stored),
        measured_from_ms=basis,
        confirmed=confirmed,
    )


def recommendation_freshness(conn, recommendation_id: int) -> dict[str, Any]:
    """Ages for one recommendation, measured **now** rather than when it was made.

    A thin read around `live_ages`, which owns the reconstruction and is shared
    with the Board. Two paths computing freshness by separate arithmetic is how
    a screen comes to offer a row the server refuses, and this function is the
    server half of exactly that pair.

    A missing row or a missing age resolves to `None`, and the caller must
    refuse on it rather than substitute zero.
    """
    row = conn.execute(
        """
        SELECT r.id, r.ticker, r.created_ms, r.entry_ask_tenths, r.side,
               r.fair_probability, r.kalshi_quote_age_ms, r.odds_age_ms,
               r.suppressed_reason, r.suggested_contracts, r.link_id,
               r.last_confirmed_ms, r.last_confirmed_quote_age_ms,
               r.last_confirmed_odds_age_ms,
               (SELECT MIN(o.commence_ms)
                  FROM odds_snapshots o
                  JOIN event_links l ON l.odds_event_id = o.odds_event_id
                 WHERE l.id = r.link_id) AS commence_ms
        FROM recommendations r WHERE r.id = ?
        """,
        (recommendation_id,),
    ).fetchone()

    if row is None:
        return {"found": False}

    ages = live_ages(row, now_ms=int(time.time() * 1000))

    return {
        "found": True,
        "ticker": row["ticker"],
        "side": row["side"],
        "entry_ask_tenths": row["entry_ask_tenths"],
        # The consensus this decision was made against. Carried because the
        # order path re-derives size and EV at a *live* ask and needs the fair
        # value that ask is being compared to -- re-devigging at order time
        # would need a fresh odds sweep, which the credit budget does not
        # afford. See `kalshi.quotes`.
        "fair_probability": row["fair_probability"],
        "suppressed_reason": row["suppressed_reason"],
        "suggested_contracts": row["suggested_contracts"],
        "created_ms": row["created_ms"],
        # **The sportsbook's kickoff, joined through the link, never Kalshi's.**
        # `kalshi_events.commence_ms` runs exactly three hours late, so reading
        # it here would call the seventh inning "not started" -- the offset that
        # has already been a silent off switch twice in this repo.
        #
        # Carried because the order path needs it and nothing else was passing
        # it: the runner refuses to *record* a started game, but a row written
        # ten minutes before kickoff keeps `suggested_contracts > 0` and stays
        # inside the 900s odds window well into the first quarter. `None` when
        # the row has no link or no stored fixture, and the caller refuses on it
        # rather than assuming the game is still ahead.
        "commence_ms": row["commence_ms"],
        "kalshi_quote_age_ms": ages.quote_age_ms,
        "odds_age_ms": ages.odds_age_ms,
        # Which instant the ages were measured from, and whether it was a
        # re-derivation. "Stale because nobody looked again" and "stale because
        # the odds aged out" are different problems with different fixes.
        "measured_from_ms": ages.measured_from_ms,
        "confirmed": ages.confirmed,
    }
