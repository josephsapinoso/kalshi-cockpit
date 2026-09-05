"""The record's own status: suppression, gate, signal, results, playbook, marts.

Moved verbatim from `backend/api/routes.py` on 2026-09-04; see
`backend/api/routers/__init__.py` for the `register()` shape and why.

The `beta` cache travels with `/api/signal` and is module state here:
`_signal_cache` is one dict for the life of the process, and `routes.py`
re-exports it and `_signal_payload` because `tests/test_clv_signal.py` clears
the cache through that namespace between app instances. The re-export must
be this object, not a copy -- a fresh dict in `routes.py` would leave the
test clearing nothing while the route served a stale report.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException

from ...analysis.clv_signal import SignalReport, report_from_connection
from ...analysis.marts import WarehouseMissing, headline_verdicts, read_dashboards
from ...config import AppConfig, GateConfig, RiskConfig
from ...engine import suppression_summary
from ...gate import POPULATIONS, evaluate_gate, population_counts
from ...market_results import result_coverage
from ...playbook import read_playbook
from ...store import db

# ---------------------------------------------------------------------------
# `beta`, cached.
# ---------------------------------------------------------------------------
#
# **The cache is a cost control, not a correctness one.** The registered §S1
# extraction scans `recommendations` and runs one correlated subquery into
# `kalshi_quotes` per surviving row. `kalshi_quotes` is roughly two thirds of an
# 879 MiB file on the live volume, and Board and Slate are `force-dynamic`
# server components, so an uncached call would run that join on **every page
# load of the two most-visited screens** -- neither of which does any full-table
# work today (`/api/board` and `/api/slate` are a windowed `LIMIT` plus a
# `COUNT(*)`).
#
# 300 seconds, and the number is not arbitrary: `beta` moves only when the
# recorder scores a new CLV, which happens at most once per market close. A TTL
# far shorter than the interval between the inputs changing buys nothing and
# pays the join for it.
#
# **`computed_ms` ships in the payload and the screen must render its age.** A
# cached statistic that presents itself as current is the exact failure
# `tasks/lessons.md` records under verification methods that lie -- the number
# looks live, so nobody asks when it was taken.
SIGNAL_CACHE_TTL_MS = 300_000

_signal_cache: dict[str, object] = {}


def _cached_signal_report(conn) -> tuple[SignalReport, int]:
    """The registered report, recomputed at most every `SIGNAL_CACHE_TTL_MS`.

    Keyed on nothing: there is one population and one registered cut, so there
    is one answer. A refusal is cached on the same terms as a result -- on the
    demo instance the reason it refuses is structural (no `event_ticker`, no
    quotes) and will not resolve itself in five minutes, so re-running the join
    to be told the same thing is the worst of both.
    """
    now = db.now_ms()
    cached = _signal_cache.get("report")
    computed_ms = _signal_cache.get("computed_ms")
    if (
        isinstance(cached, SignalReport)
        and isinstance(computed_ms, int)
        and now - computed_ms < SIGNAL_CACHE_TTL_MS
    ):
        return cached, computed_ms
    report = report_from_connection(conn)
    _signal_cache["report"] = report
    _signal_cache["computed_ms"] = now
    return report, now


def _signal_payload(report: SignalReport, computed_ms: int) -> dict:
    """Serialise a `SignalReport` so a caller cannot read the effect first.

    Three rules are enforced by the *shape* rather than by the consumer's
    manners, because a consumer's manners are not testable:

    - **`estimate` is `None` unless a fit happened.** There is no key holding a
      bare `beta_hat` that a refused run could still populate.
    - **Nothing inside `estimate` is optional.** `se_cluster`, `n_clusters` and
      both interval limits travel with `beta_hat` or none of them do, so a
      screen physically cannot render the point estimate alone -- the one-number
      habit the always-valid multiplier exists to defeat.
    - **`verdict` is the registered string**, never a paraphrase. `UNRESOLVED`
      is a real answer and may not be presented as "no signal"; the payload
      carries `may_declare` so a renderer knows the difference without having to
      re-derive the floor.
    - **`g_eff` travels inside `estimate`**, beside `n_clusters` and not in a
      block of its own. Amendment 2 §B7 makes the effective cluster count a
      mandatory reportable, and a key a renderer can skip is a key that gets
      skipped: `G = 311` was 4.26 effective clusters on 2026-08-25, and the
      screen that declared on it had no way to say so.
    """
    f = report.fit
    return {
        "computed_ms": computed_ms,
        "cache_ttl_ms": SIGNAL_CACHE_TTL_MS,
        "available": f is not None,
        "refusal": report.refusal,
        "verdict": report.verdict,
        # §A4: what §6 alone returned, and the group that moved it. Both travel
        # so a downgrade is legible as a downgrade rather than as an UNRESOLVED
        # that looks like it came from the cluster floor.
        "section6_verdict": report.section6_verdict,
        "downgraded_by": report.downgraded_by,
        "may_declare": report.n_clusters >= report.clusters_to_declare,
        # Population before effect size. Always, and in this order.
        "population": {
            "rows": report.n_analysed,
            "clusters": report.n_clusters,
            "clusters_to_declare": report.clusters_to_declare,
            "clusters_remaining": report.clusters_remaining,
            "p1": report.p1,
            "p1_floor": report.p1_floor,
            "p1_passed": report.p1_passed,
            "matched": report.matched,
            "quote_mismatch": report.quote_mismatch,
            "no_quote": report.no_quote,
            "disclosure_required": report.disclosure_required,
            # §P4/§7: with more than one strategy_config_version in the record
            # the primary runs on the modal one and `G` counts only those games.
            # Carried on the wire because a reader who sees `clusters` without
            # it cannot tell which population produced the verdict -- which is
            # exactly how 2026-08-24's screen declared NO SIGNAL at G = 311 when
            # the registered primary was UNRESOLVED at G = 216.
            "modal_config_applied": report.modal_config_applied,
            "modal_config_version": report.modal_config_version,
            "non_modal_rows_excluded": report.n_non_modal_dropped,
            "strategy_config_versions": {
                str(k): v for k, v in report.strategy_config_versions.items()
            },
        },
        "estimate": None if f is None else {
            # The smallest resolvable effect comes before the effect, because
            # reading the effect first is how a small cell gets believed.
            "smallest_resolvable_beta": report.smallest_resolvable_beta,
            "beta_hat": f.beta_hat,
            "se_cluster": f.se_cluster,
            "n_clusters": f.n_clusters,
            # §B7's mandatory reportable, immediately after the count it
            # qualifies. `null` means the regressor has no residual variance,
            # which is not the same as zero and is not the same as `n_clusters`.
            "g_eff": f.g_eff,
            "largest_cluster_leverage_share": f.largest_cluster_leverage_share,
            "n_rows": f.n_rows,
            "interval_lower": f.lower,
            "interval_upper": f.upper,
            "multiplier": f.multiplier,
        },
        # §A4's downgrade table. Descriptive: it can lower a verdict and can
        # never raise one, and no row here is a finding.
        "a4_groups": [
            {
                "name": g.name,
                "rows": g.n_rows,
                "clusters": g.n_clusters,
                "leverage_share": g.leverage_share,
                "clusters_remaining": g.clusters_remaining,
                "testable": g.testable,
                "beta_hat": g.beta_hat,
                "interval_upper": g.upper,
                "refusal": g.refusal,
                "one_group_result": g.one_group_result,
            }
            for g in report.a4_groups
        ],
        # §A4: the per-group view can downgrade a verdict and can never create
        # one. `market_type` is not a registered cut; it is here because the
        # repo rule requires the parts beside any aggregate, and this pooled
        # figure is not homogeneous -- the two arms are -0.08 and -0.52.
        "by_market_type": [
            {
                "name": g.name,
                "rows": g.n_rows,
                "share": g.share,
                "clusters": g.n_clusters,
                "beta_hat": g.beta_hat,
                "refusal": g.refusal,
            }
            for g in report.by_market_type
        ],
        "registration": (
            "docs/measurements/2026-08-09-preregistration-clv-signal-test.md"
        ),
        "note": (
            "beta is tenths of realised closing-line value per tenth of claimed "
            "edge. UNRESOLVED below 713 clusters is a real answer and is NOT "
            "'no signal' -- Amendment 2 section B4 raised that floor from 300 "
            "on 2026-08-29 after the power check's own sigma trigger fired. "
            "g_eff is the effective cluster count and is a REPORTABLE, never a "
            "threshold: G = 311 was 4.26 effective clusters. The cluster key is "
            "COALESCE(event_ticker, ticker), which is not the gate's ADR 0029 "
            "key; the two differ materially."
        ),
    }


def register(
    app: FastAPI,
    *,
    app_config: AppConfig,
    gate: GateConfig,
    risk: RiskConfig,
    get_conn,
) -> None:
    """Attach the six status handlers to `app`, in their original order."""

    @app.get("/api/suppression")
    def suppression(conn=Depends(get_conn), since_ms: int = 0) -> dict:
        """How often each rule fired.

        A rule firing constantly is either miscalibrated or catching a real
        upstream problem. Both are findings.
        """
        return {"counts": suppression_summary(conn, since_ms)}

    @app.get("/api/gate")
    def gate_status(conn=Depends(get_conn)) -> dict:
        """Why execution is locked, stated as specific unmet conditions.

        Calls the same `evaluate_gate` the order endpoint uses, without the
        per-order freshness check -- this reports standing readiness, while an
        order is judged on the freshness of its own quotes. Sharing the function
        is the point: a screen and a control that compute "open" separately will
        eventually disagree, and the direction that matters is the screen saying
        open while the control is not.

        **`populations` is on this endpoint rather than an authenticated one of
        its own, and that is the decision.** `gate.population_counts` answers
        the question the conditions cannot: whether the `actionable` branch has
        ever been taken over the *whole* table, rather than over the
        scored-at-the-primary-horizon subset the conditions read. Until now it
        existed only as a `logger.info` line inside `log_gate_progress`, i.e.
        reachable only through `flyctl logs`, i.e. a laptop job -- and this tool
        is operated from a phone.

        **It is already an authenticated read on live**, which is the first
        thing to be clear about: `frontend/src/middleware.ts` matches every path
        but Next's static output, and answers an unauthenticated `/api/*` with a
        401. So on the live deployment this is reachable only after signing in
        at `/login`, and the session cookie is the only credential a phone
        browser can actually carry. `require_auth` would add a *second*,
        different one on top of it.

        Three reasons it goes here and not behind `require_auth`:

        - **A bearer token is not openable in a phone browser.** The whole
          defect being fixed is that the number was reachable only from a
          laptop. Putting it behind a header that neither the browser's address
          bar nor the Next proxy sends would move it from one unreachable place
          to another.
        - **It reveals strictly less than this endpoint already does.** The
          `scored_recommendations` condition's detail string already publishes
          the same three population names with their game and row counts, over
          the scored subset. This adds the un-scored denominator, which is the
          more conservative of the two numbers.
        - **`require_auth` 403s on the demo instance by design**, so an
          authenticated variant would be unavailable on the one deployment
          whose whole purpose is to be looked at.

        The counts are over the whole table (`since_ms=0`), not the 24h window
        `log_gate_progress` uses. That window answers "is this system producing
        anything today"; this endpoint is asked "has it *ever*", and a zero over
        all time is a much stronger statement than a zero over a quiet Sunday.
        """
        payload = evaluate_gate(conn, gate).to_dict()
        # Derived from the venue's observed balance, never typed (ADR 0045).
        # `null` when no balance has ever been observed -- the demo instance,
        # or a live volume the poller has not written yet.
        derived_risk = (
            risk.with_observed_balance(db.latest_balance_tenths(conn))
            if risk.underived
            else risk
        )
        payload["bankroll_dollars"] = (
            None if derived_risk is None else derived_risk.bankroll_dollars
        )
        payload["populations"] = {
            "since_ms": 0,
            "counts": population_counts(conn, 0),
            # What each name means, sent with the numbers. `no_edge` reading as
            # a rejection is the specific misreading this repo has already had
            # to correct once -- "no result and rejected are different
            # outcomes", `tasks/lessons.md`.
            "predicates": dict(POPULATIONS),
            "note": (
                "Counts of rows written, over the whole table and at every "
                "horizon -- not of rows scored. `actionable` is sized at the "
                "fixed reference bankroll, not the deployed one, so it is the "
                "only one of the three that can ever increment the gate's "
                "300-game floor."
            ),
        }
        payload["note"] = (
            "Freshness is not shown here because it is a property of a single "
            "order at a single instant, not of the system. It is checked again "
            "when an order is placed."
        )
        return payload

    @app.get("/api/signal")
    def signal_status(conn=Depends(get_conn)) -> dict:
        """`beta` -- what the product's own conclusion is worth, measured.

        The defect this closes: the cockpit stated a conclusion about whether
        the consensus signal works, and stated its measured worth **nowhere**.
        `beta` appeared zero times in `frontend/src` and could be produced only
        by a human running `scripts/run_signal_test.py` against a dump taken
        over `flyctl ssh` -- a laptop job, on a tool operated from a phone. Same
        shape as `/api/gate` and `/api/results` before them.

        **This computes nothing of its own.** It calls
        `backend.analysis.clv_signal.report_from_connection`, which is the same
        function `scripts/run_signal_test.py` prints, over the same registered
        §S1 extraction. A route that assembled the population itself would be a
        third implementation of the registration, and the whole reason that
        module exists is that there were already two.

        **Wiring the estimator into the deployed image reverses a quarantine,
        and that decision is ADR 0039**, not a side effect of this endpoint.
        `backend/analysis/signal_test.py` was classified off the machine on the
        reasoning that an automatically-running rule "gets re-read thousands of
        times". The always-valid multiplier is exactly the construction that
        makes unlimited re-reading valid, so the interval is unharmed; what the
        ADR decides is that the declaring branches may fire without a human in
        the room, which is the behaviour ADR 0038 wants -- the `G = 300` look
        arriving by construction rather than by anyone remembering to take it.

        **Unauthenticated, on the same three grounds as `/api/gate`:** the live
        deployment already 401s an unauthenticated `/api/*` at
        `frontend/src/middleware.ts`, a bearer token is not openable in a phone
        browser, and `require_auth` 403s on demo -- the one instance whose
        purpose is to be looked at. It reveals less than `/api/gate` already
        does; `/api/gate` publishes the population counts this is computed over.

        **A refusal is rendered, never rounded down to a small number.** On the
        demo instance the seeded history carries no `event_ticker` and no
        quotes, so every row joins to a NULL half-spread and the registered
        precondition P1 fails. The honest response there is `available: false`
        with the reason -- not `G = 420`, which is what a caller reading the
        cluster count off a refused report would put on the public screen, and
        which is a *larger* number than the live record's.
        """
        report, computed_ms = _cached_signal_report(conn)
        return _signal_payload(report, computed_ms)

    @app.get("/api/results")
    def market_results(conn=Depends(get_conn)) -> dict:
        """Is `kalshi_markets.result` being written, and is anything being lost?

        The market-result pass reported itself only through its counters on the
        merged pass line -- i.e. `flyctl logs`, i.e. a laptop. This tool is
        operated from a phone, so a pass that silently stopped writing was
        undetectable from the one device that is always to hand. That is the
        whole reason this endpoint exists; it adds no capability the pass does
        not already have, only a way to read it.

        **Why this is urgent rather than merely nice.** Outcomes are dropped
        permanently once a game is older than `max_age_after_commence_s` (unset
        on live, so the 7-day code default applies). The loss is *rolling*, not
        a cliff: a broken pass costs one day of outcomes per day, forever, and
        every one of those games is a row the calibration consumer can never
        score. `expiring_soon_total` is the number to act on -- what is about to
        be lost, rather than what already has been.

        Placed beside `/api/gate` rather than behind `require_auth`, for the
        reason set out at length there: on live, `middleware.ts` already answers
        an unauthenticated `/api/*` with a 401, and a bearer token is not
        something a phone browser can carry. A second credential on top would
        move the number from one unreachable place to another.

        It reveals less than `/api/gate` already does -- market counts and
        `yes`/`no` tallies over settled games, with no price, no position and no
        recommendation in it.

        Read `verdict` first, and read it *with* `recorded_total`. Zero recorded
        outcomes means "the pass has never worked" or "there has been nothing to
        record yet", and those need opposite responses; the verdict is derived
        from the same fields it is printed beside, so the two cannot disagree.
        """
        return result_coverage(conn, now=db.now_ms())

    @app.get("/api/playbook")
    def playbook(conn=Depends(get_conn), limit: int = 50) -> dict:
        """What rules were in force, and the evidence recorded under each.

        Reads the operational database, not the warehouse, so unlike
        `/api/dashboards` it cannot 503 on an unbuilt lakehouse -- the columns
        it needs are written by the same pass that writes a recommendation.

        The one thing it must never do is report an empty `lessons` list as
        "nothing to report". `historian_has_run` carries that distinction, and
        the screen is required to render it.
        """
        return read_playbook(conn, limit=max(1, min(int(limit), 200)))

    @app.get("/api/dashboards")
    def dashboards() -> dict:
        """The dbt marts, verdicts included.

        Returns 503 rather than an empty payload when the warehouse has not
        been built: an empty dashboard reads as "nothing to report", and only
        one of those two states needs someone to do something about it.
        """
        try:
            payload = read_dashboards(app_config.warehouse_path)
        except WarehouseMissing as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        payload["headlines"] = headline_verdicts(payload)
        return payload
