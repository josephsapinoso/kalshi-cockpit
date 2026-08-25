"""The registered CLV signal test, from a database connection to a verdict.

**This module moves code; it does not change a statistic.** Every expression in
it was lifted verbatim from two files that already ran the registered test by
hand:

| what | came from |
|---|---|
| `SQL_CLV_SIGNAL_PULL` | `scripts/inspect_live_db.py:_SQL_CLV_SIGNAL_PULL` |
| `observations`, `quote_disagrees`, `a82_counts` | `scripts/run_signal_test.py` |
| the section-by-section arithmetic in `build_report` | `scripts/run_signal_test.py:main` |

The arithmetic itself -- `beta`, the sandwich, the always-valid multiplier and
all four verdict branches -- stays where it was, in
`backend.analysis.signal_test`. This module hands it rows and packages what
comes back.

Why it exists
-------------
`beta` is the project's registered decision-bearing statistic, and until now it
could only be produced by a human running a script on a laptop against a dump
taken over `flyctl ssh`. The product therefore stated a conclusion whose
measured worth it stated nowhere. Lifting the extraction here lets
`GET /api/signal` serve the same number the harness prints, from the same code,
so the screen and the record **cannot** disagree -- and so the `G = 300` look
arrives on its own rather than by anyone remembering to take it.

**That is a deliberate reversal of a quarantine, recorded in ADR 0039.**
`backend/analysis/signal_test.py` was classified in `DISPOSITIONS` as off the
deployed machine, on the reasoning that "a rule that runs automatically on every
pass is a rule that gets re-read thousands of times". The always-valid
multiplier is precisely the construction that makes unlimited re-reading valid,
so continuous recomputation is safe **for the interval**; what the ADR actually
had to decide is that the *declaring* branches may fire without a human present.

What this module does not establish
-----------------------------------
- **Nothing on its own.** It is a transcription of a registered extraction plus
  a call into a registered estimator. A disagreement between this file and
  `docs/measurements/2026-08-09-preregistration-clv-signal-test.md` is a bug
  here.
- **Nothing at `G < 300`.** `SignalReport.verdict` is `UNRESOLVED` below the
  floor. That is a real answer and may not be reported as "no signal".
- **Nothing about a database it was not pointed at.** A demo instance whose
  seeded rows carry no `event_ticker` and no quotes produces a refusal, not a
  small number, and callers must render the refusal rather than the shape.
- **`beta_hat` alone is never a verdict.** Every field of `SignalReport` that a
  caller renders must carry `se_cluster`, `n_clusters` and the boundary beside
  it.
"""

from __future__ import annotations

import sqlite3
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from .signal_test import (
    MIN_CLUSTERS_TO_DECLARE,
    MIN_HALF_SPREAD_COVERAGE,
    Fit,
    Observation,
    SignalTestRefused,
    coverage,
    fit,
    verdict,
)

# ---------------------------------------------------------------------------
# The CLV signal test's registered extraction.
# ---------------------------------------------------------------------------
#
# **This is §S1 of `docs/measurements/2026-08-09-preregistration-clv-signal-test.md`,
# as amended, and it is a transcription rather than a design.** Every clause
# below is fixed in that file. Nothing here chooses a population, a horizon or
# a cluster key; changing any of them is an amendment to the registration, made
# in the registration, dated, before the next look.
#
# Four amendments are folded in and each is load-bearing:
#
# **§A1 — the delimited `instr` predicate.** `suppressed_reason` is a
# comma-joined composite of *every* check that failed, so the registered
# `NOT IN ('stale_odds', ...)` matched neither literal on
# `'stale_odds,wide_market'` and **retained** the row it existed to drop.
# `instr` and not `LIKE`, because SQLite's `LIKE` treats `_` as a
# single-character wildcard and every code in this vocabulary contains one --
# `,staleXodds,` would match. The wrapping commas are required in both
# directions: without them a future `stale_odds_upstream` is silently excluded.
#
# **§A2 — only four codes are excluded**, not "the suppressed ones":
# `stale_odds`, `stale_kalshi_quote`, `no_commence_time`, `commence_skew`.
# Every other code is RETAINED, including `too_few_books`, `wide_market`,
# `edge_within_method_noise` and the `skeptic_*` family. Dropping the rows where
# the edge estimate is least reliable is a hypothesis about the answer, and
# `edge_within_method_noise` in particular removes a price-dependent interval
# from the *interior* of the regressor, which moves leverage to the tails in the
# flattering direction.
#
# **§A2.2 — the price bound `BETWEEN 10 AND 989`.** Without it a row outside
# Grid A/B's range enters the pooled `beta` and appears in no bucket, so the
# pooled number and the per-group view are computed on different populations,
# silently.
#
# **§F3 — horizon 0.0 only.** ADR 0011 left two horizons in the record and
# blending them averages two regimes.
#
# **The cluster key is `COALESCE(m.event_ticker, r.ticker)` and it is NOT the
# gate's key.** ADR 0029 clusters on `odds_event_id` so a prop ladder collapses
# onto its game; this registration predates that and clusters on the Kalshi
# event. On the current record the two give **210 and 125** -- a 68% difference
# -- so a `G` quoted without its key is meaningless. The registered one governs
# here because it is what the power check was computed against.
#
# **`half_spread_tenths` is the C2 confound, not a nicety.** `edge` and `clv`
# are both measured against the ask, so the half-spread enters both and induces
# a slope with no signal present. It is a *control*, and the mid is used only to
# recover it -- never as an entry price. Rows where it is NULL are dropped by
# the fit and counted, never imputed: that count is P1's numerator, and P1
# refuses the primary analysis below 0.90 coverage.
#
# **Copied here from `scripts/inspect_live_db.py` byte-for-byte, and the copy is
# held in place by a test rather than by care.** That script cannot import it:
# it runs as `python /app/scripts/...`, which puts `/app/scripts` on `sys.path`
# and not `/app`, so an import would pass in the suite and fail on the machine
# it exists to interrogate (`inspect_live_db.py:350-358`). That leaves two copies
# of one definition -- the drift `tasks/lessons.md` records -- so
# `tests/test_clv_signal.py` asserts the two strings are identical. If the
# registered extraction moves in one file and not the other, the suite goes red
# before an operator dump and the served endpoint can describe different
# populations under one name.
SQL_CLV_SIGNAL_PULL = (
    "SELECT COALESCE(m.event_ticker, r.ticker) AS cluster_key, "
    "r.id, r.ticker, r.side, r.created_ms, m.market_type, "
    "r.entry_ask_tenths, r.edge_tenths, r.clv_tenths, "
    "r.suppressed_reason, r.reference_contracts, r.strategy_config_version, "
    "q.yes_bid_tenths, q.no_bid_tenths, q.observed_ms AS quote_observed_ms, "
    "((1000 - q.no_bid_tenths) - q.yes_bid_tenths) / 2.0 AS half_spread_tenths, "
    "(m.event_ticker IS NULL) AS unclustered "
    "FROM recommendations r "
    "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
    "LEFT JOIN kalshi_quotes q ON q.id = ("
    "  SELECT q2.id FROM kalshi_quotes q2 "
    "  WHERE q2.ticker = r.ticker AND q2.observed_ms <= r.created_ms "
    "    AND q2.yes_bid_tenths IS NOT NULL AND q2.no_bid_tenths IS NOT NULL "
    "  ORDER BY q2.observed_ms DESC LIMIT 1) "
    "WHERE r.clv_scored_ms IS NOT NULL "
    "  AND r.clv_tenths IS NOT NULL "
    "  AND r.clv_horizon_hours = 0.0 "
    "  AND r.entry_ask_tenths BETWEEN 10 AND 989 "
    "  AND (r.suppressed_reason IS NULL "
    "       OR (instr(',' || r.suppressed_reason || ',', ',stale_odds,') = 0 "
    "       AND instr(',' || r.suppressed_reason || ',', ',stale_kalshi_quote,') = 0 "
    "       AND instr(',' || r.suppressed_reason || ',', ',no_commence_time,') = 0 "
    "       AND instr(',' || r.suppressed_reason || ',', ',commence_skew,') = 0)) "
    "ORDER BY r.id"
)

#: §A8.2: above this `quote_mismatch / total` the write-up **must state, in
#: those words**, that the control is attenuated and the residual bias in
#: `beta` runs positive. The harness prints the sentence itself rather than
#: trusting an author to remember it.
A82_MISMATCH_DISCLOSURE_THRESHOLD = 0.05


def pull_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """The registered §2 population, as plain dicts, straight off a connection.

    **No cap and no `LIMIT`, deliberately.** A capped pull is ordered by `id`,
    so it is the project's earliest recommendations rather than a sample, and a
    `beta` computed over one is a statement about the first N rows written under
    superseded strategy configs. `scripts/run_signal_test.py` refuses a
    truncated dump for exactly this reason; the in-process path removes the
    opportunity rather than re-checking for it.
    """
    cursor = conn.execute(SQL_CLV_SIGNAL_PULL)
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def observations(rows: Sequence[Mapping[str, Any]]) -> list[Observation]:
    """Rows to `Observation`s. Moved from `scripts/run_signal_test.py`."""
    return [
        Observation(
            cluster_key=str(r["cluster_key"]),
            edge_tenths=float(r["edge_tenths"]),
            clv_tenths=float(r["clv_tenths"]),
            half_spread_tenths=(
                None if r["half_spread_tenths"] is None
                else float(r["half_spread_tenths"])
            ),
        )
        for r in rows
    ]


def quote_disagrees(row: Mapping[str, Any]) -> bool:
    """§A8.2: the joined quote's derived ask differs from the stored entry ask.

    Counted separately from "no quote at all". A row with a quote that
    disagrees is not missing data -- it is a row whose control was recovered
    from a different observation than the one the recommendation was priced
    from, which is a different problem with a different remedy.

    **The comparison is side-dependent, and the first version of this function
    was not.** `entry_ask_tenths` is the price paid for the side actually taken
    (`backend/analysis/clv.py:151`), so the ask to compare it against is
    `1000 - no_bid` on a YES row and `1000 - yes_bid` on a NO row. Comparing
    every row against the YES-side ask flags **every NO row by construction**,
    and on the 2026-08-16 record it reported 1,826 disagreements that were
    exactly the 1,826 NO rows. The true count on that record is 0. See
    `docs/measurements/2026-08-16-quote-join-bias-result.md`.

    This is a diagnostic counter, not a branch of the decision rule: it does not
    touch the population, the model, the cluster key, the multiplier or any
    verdict branch, so correcting it is a bug fix and not an amendment.
    """
    side = (row.get("side") or "").lower()
    opposite_bid = row.get("yes_bid_tenths") if side == "no" else row.get("no_bid_tenths")
    if opposite_bid is None:
        return False
    return (1000 - opposite_bid) != row["entry_ask_tenths"]


def a82_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """§A8.2's three counts. Never two.

    | count | meaning | treatment |
    |---|---|---|
    | `matched` | a quote joined **and** the identity holds | the analysis population |
    | `quote_mismatch` | a quote joined and the identity **fails** | RETAINED, counted separately |
    | `no_quote` | the join returned nothing | dropped, never imputed |

    **`matched / total` is P1**, and the amendment calls that "a strictly tighter
    gate than the one registered". `backend.analysis.signal_test.coverage` is the
    superseded statistic -- it measures non-NULL half-spread, which cannot
    distinguish a control recovered from the wrong quote from one recovered from
    the right one. On the 2026-08-16 record the two disagreed by 0.4946 and the
    looser one is what the harness read.

    `quote_mismatch` rows are retained deliberately: excluding them would create
    an exclusion rate correlated with book activity, which is worse than the
    attenuation it removes.
    """
    matched = mismatch = no_quote = 0
    for row in rows:
        if row.get("half_spread_tenths") is None:
            no_quote += 1
        elif quote_disagrees(row):
            mismatch += 1
        else:
            matched += 1
    return {"matched": matched, "quote_mismatch": mismatch, "no_quote": no_quote}


@dataclass(frozen=True)
class GroupView:
    """One row of the per-group diagnostic. Downgrades only; never a finding.

    §A4: the per-group view can downgrade a verdict and can never create one.
    `market_type` is **not** a registered cut; it is carried because the repo
    rule requires the parts beside any aggregate, and the pooled figure on this
    record is not homogeneous.
    """

    name: str
    n_rows: int
    share: float
    n_clusters: Optional[int]
    beta_hat: Optional[float]
    refusal: Optional[str]


@dataclass(frozen=True)
class SignalReport:
    """Everything a caller needs to read `beta` honestly, and nothing less.

    Fields are ordered as §S1 registers the *output* order, and that order is
    the point: `n`, `G` and P1 come before any effect size. A caller that
    renders `beta_hat` without `se_cluster`, `n_clusters` and the boundary is
    doing the one-number thing the always-valid multiplier exists to defeat.
    """

    # 1. population -- before any effect size, always
    n_raw: int
    n_analysed: int
    n_clusters: int
    unclustered: int
    matched: int
    quote_mismatch: int
    no_quote: int
    p1: float
    p1_floor: float
    non_null_coverage: float
    strategy_config_versions: dict[Any, int]
    # §P4/§7 were applied: the record carried more than one
    # `strategy_config_version`, so the primary ran on the modal one alone and
    # `G` counts only those games. See `build_report`.
    modal_config_applied: bool
    modal_config_version: Optional[Any]
    n_non_modal_dropped: int
    # The fit across every config version, present only when §P4 fired. §P4's
    # "the others are reported separately". **It never carries a verdict** --
    # `verdict()` is not called on it at any `G`, because a second declaring
    # number is exactly how the wrong one gets quoted, which is what happened on
    # 2026-08-24. Kept rather than discarded so the published interim figure
    # stays reproducible from this code.
    pooled_fit: Optional[Fit]

    # preconditions
    p1_passed: bool
    disclosure_required: bool
    refusal: Optional[str]

    # 2. the C2 confound, measured
    sd_half_spread: Optional[float]
    sd_edge: Optional[float]
    sd_clv: Optional[float]
    implied_spurious_slope: Optional[float]

    # 3-5. resolving power, the estimate, the verdict
    fit: Optional[Fit]
    verdict: str
    clusters_to_declare: int

    # 6. diagnostic only
    by_market_type: tuple[GroupView, ...]

    @property
    def smallest_resolvable_beta(self) -> Optional[float]:
        """Printed *before* `beta_hat`. Reading the effect first is how a small
        cell gets believed."""
        if self.fit is None:
            return None
        return self.fit.multiplier * self.fit.se_cluster

    @property
    def clusters_remaining(self) -> int:
        """How many more clusters before a declaring look is permitted."""
        return max(0, self.clusters_to_declare - self.n_clusters)


def build_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    n_raw: Optional[int] = None,
) -> SignalReport:
    """Run the registered test over a §2 population and package the result.

    **Every expression here was moved from `scripts/run_signal_test.py:main`.**
    That script is now a printer over this function, so the harness an operator
    runs and the number `GET /api/signal` serves are the same computation rather
    than two implementations that happen to agree.

    A precondition failure returns a `SignalReport` with `fit=None` and a reason
    -- it does not raise. The caller decides whether that is an exit code or a
    rendered panel, and both have to say *why*, which a bare exception loses.

    §P4 IS APPLIED HERE, NOT BY THE CALLER
    --------------------------------------
    **This used to be a `modal_config_only` flag, defaulting to `False`, and
    production never set it. That is why the 2026-08-24 screen declared
    NO SIGNAL on a population the registration forbids as primary.**

    §P4 and §7 say the same thing in two places, and neither offers a choice:

    > §P4: "if it exceeds one, the primary analysis runs on the **modal version
    > only** and the others are reported separately."
    > §7: "A change of more than one version means the primary runs on the modal
    > version and **`G` counts only those games**."

    A registered rule implemented as an opt-in parameter is the repo's
    "built but never called" pattern in miniature: the branch existed, it was
    tested, and the one caller that mattered took the default. So the filter is
    unconditional and the caller has no say.

    It was survivable while every look was interim -- the 2026-08-16 write-up
    stated plainly that the rule "was **not** applied to the numbers above" and
    ran it as a sensitivity, which is permissible when nothing is being
    declared. It stops being survivable the moment `G` crosses 300, because
    then the pooled number is a *verdict* on a population that is not the
    primary. On the 2026-08-25 record the difference is
    `G = 311, NO SIGNAL` against `G = 216, UNRESOLVED`.

    **The non-modal rows are reported as their distribution, not as a second
    `beta`.** `strategy_config_versions` carries the whole mix, which is what
    "reported separately" needs; a second slope on the page is precisely how the
    wrong one gets quoted. `docs/measurements/2026-08-25-clv-signal-declaring-look-refused.md`
    """
    n_raw = len(rows) if n_raw is None else n_raw

    versions = Counter(r["strategy_config_version"] for r in rows)
    modal_version: Optional[Any] = None
    n_before = len(rows)
    pooled: Optional[Fit] = None
    if len(versions) > 1:
        # "The others are reported separately" -- so the pooled fit is computed
        # BEFORE the filter and carried, never discarded. Two reasons, and the
        # second is the one that decided it:
        #
        # 1. §P4 asks for it in those words.
        # 2. `docs/measurements/2026-08-16-clv-signal-test-interim-look.md`
        #    publishes `beta_hat = -0.1412, G = 199` off the committed dump, and
        #    a repo that can no longer reproduce a number in its own record has
        #    made that record unverifiable. `tests/test_clv_signal.py` pins it.
        #
        # It carries NO verdict, at any `G`. `verdict()` is never called on it
        # and `_signal_payload` files it away from `estimate`.
        try:
            pooled = fit(observations(rows))
        except SignalTestRefused:
            pooled = None
        modal_version = versions.most_common(1)[0][0]
        rows = [r for r in rows if r["strategy_config_version"] == modal_version]
    modal_config_applied = modal_version is not None
    n_non_modal_dropped = n_before - len(rows)

    obs = observations(rows)
    clusters = {o.cluster_key for o in obs}
    unclustered = sum(1 for r in rows if r.get("unclustered"))
    cov = coverage(obs)

    # §A8.2's three counts. Never two -- the amendment says so in those words,
    # and the reason is that "no quote at all" and "a quote that disagrees" are
    # different failures with different remedies, and P1 as originally
    # registered refused only the second.
    counts = a82_counts(rows)
    total = len(rows)
    matched_fraction = (counts["matched"] / total) if total else 0.0
    mismatch_fraction = (counts["quote_mismatch"] / total) if total else 0.0

    common = dict(
        n_raw=n_raw,
        n_analysed=total,
        n_clusters=len(clusters),
        unclustered=unclustered,
        matched=counts["matched"],
        quote_mismatch=counts["quote_mismatch"],
        no_quote=counts["no_quote"],
        p1=matched_fraction,
        p1_floor=MIN_HALF_SPREAD_COVERAGE,
        non_null_coverage=cov,
        strategy_config_versions=dict(sorted(versions.items())),
        modal_config_applied=modal_config_applied,
        modal_config_version=modal_version,
        n_non_modal_dropped=n_non_modal_dropped,
        pooled_fit=pooled,
        disclosure_required=mismatch_fraction > A82_MISMATCH_DISCLOSURE_THRESHOLD,
        clusters_to_declare=MIN_CLUSTERS_TO_DECLARE,
    )

    def refused(reason: str) -> SignalReport:
        return SignalReport(
            p1_passed=matched_fraction >= MIN_HALF_SPREAD_COVERAGE,
            refusal=reason,
            sd_half_spread=None,
            sd_edge=None,
            sd_clv=None,
            implied_spurious_slope=None,
            fit=None,
            # A refused run has no verdict, and "UNRESOLVED" is a verdict --
            # it is the answer at G < 300, which is a *completed* look. Saying
            # it here would report a took-place look that did not.
            verdict="REFUSED",
            by_market_type=(),
            **common,
        )

    if matched_fraction < MIN_HALF_SPREAD_COVERAGE:
        return refused(
            f"P1 FAILED: matched / total = {matched_fraction:.4f} is below the "
            f"registered floor {MIN_HALF_SPREAD_COVERAGE}. §A8.2 applies P1 to "
            f"`matched / total`, NOT to non-NULL half-spread coverage. Without "
            f"the half-spread control the C2 confound is left in place and the "
            f"slope is biased in the INFLATING direction."
        )

    try:
        f = fit(obs)
    except SignalTestRefused as exc:
        return refused(str(exc))

    usable = [o for o in obs if o.half_spread_tenths is not None]
    sd_half = statistics.pstdev([o.half_spread_tenths for o in usable])
    sd_edge = statistics.pstdev([o.edge_tenths for o in usable])
    sd_clv = statistics.pstdev([o.clv_tenths for o in usable])
    spurious = (sd_half**2 / sd_edge**2) if sd_edge else float("nan")

    by_type: dict[str, list[Observation]] = defaultdict(list)
    for row, o in zip(rows, obs):
        by_type[row.get("market_type") or "(none)"].append(o)
    groups: list[GroupView] = []
    for name, group in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        share = len(group) / len(obs)
        try:
            gf = fit(group)
        except SignalTestRefused as exc:
            groups.append(GroupView(name, len(group), share, None, None, str(exc)))
        else:
            groups.append(
                GroupView(name, len(group), share, gf.n_clusters, gf.beta_hat, None)
            )

    return SignalReport(
        p1_passed=True,
        refusal=None,
        sd_half_spread=sd_half,
        sd_edge=sd_edge,
        sd_clv=sd_clv,
        implied_spurious_slope=spurious,
        fit=f,
        verdict=verdict(f),
        by_market_type=tuple(groups),
        **common,
    )


def report_from_connection(conn: sqlite3.Connection) -> SignalReport:
    """`pull_rows` then `build_report`. The whole test, from a connection.

    This is the function `GET /api/signal` calls. It is a two-liner on purpose:
    a route that assembled the population itself would be a third
    implementation of §S1, and the reason this module exists is that there were
    already two.

    **It takes no options, deliberately.** It used to take `modal_config_only`
    and the route took the default, which is how §P4 came to be violated on a
    declaring look. `build_report` owns that rule now; see its docstring.
    """
    return build_report(pull_rows(conn))
