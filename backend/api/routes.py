"""FastAPI routes for the cockpit.

Two properties this layer must hold, both of which are security boundaries
rather than conveniences:

**Every mutating route requires auth, and the demo instance has no mutating
routes at all.** The demo and live instances run as separate processes from one
image. A public URL must not be one config bug away from the order path.

**Freshness and risk are re-validated server-side.** The Board greys out a
stale opportunity, but the API refuses it independently. Never trust that the
UI disabled a button -- a disabled button is a hint to a human, not a control.
"""

from __future__ import annotations

import logging
import secrets
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..analysis.marts import (
    WarehouseMissing,
    headline_verdicts,
    read_dashboards,
)
from ..config import AppConfig, GateConfig, OddsConfig, RiskConfig, StalenessConfig
from ..core.correlation import CorrelationRefused, Leg
from ..core.parlay import (
    ParlayQuote,
    american_to_decimal,
    decimal_to_american,
    kalshi_equivalent,
    value_parlay,
)
from ..core.prices import format_price, tenths_to_dollars
from ..core.teaser import find_wong_candidates
from ..engine import suppression_summary
from ..gate import clustered_clv, evaluate_gate, recommendation_freshness
from ..kalshi.orders import OrderPlacer, OrderRefused, OrderRequest
from ..odds.budget import CreditBudget
from ..odds.timing import window_status
from ..store import db

logger = logging.getLogger(__name__)


class OrderPlacementRequest(BaseModel):
    """What the ticket sends. Deliberately minimal.

    The client names a recommendation and a size; it does not send a price, a
    ticker or a side. Everything that determines what is actually bought is
    read server-side from the recommendation, so a tampered or stale client
    cannot buy a different market or a better price than the one recorded.
    """

    recommendation_id: int
    contracts: int = Field(gt=0, le=10_000)


class LegRequest(BaseModel):
    """One leg of a combination, as the Builder screen sends it."""

    label: str
    probability: float = Field(gt=0.0, lt=1.0)
    event_key: str
    league: str
    commence_ms: int

    def to_leg(self) -> Leg:
        return Leg(
            label=self.label,
            probability=self.probability,
            event_key=self.event_key,
            league=self.league,
            commence_ms=self.commence_ms,
        )


class CorrelationOverride(BaseModel):
    """A measured correlation for one specific pair.

    The only sanctioned way to price same-game legs. It is a required, explicit
    act by the caller rather than a default, because the sign varies by pair and
    a plausible guess here is worse than no number at all.
    """

    a: str
    b: str
    rho: float = Field(ge=-1.0, le=1.0)


class ParlayRequest(BaseModel):
    legs: list[LegRequest] = Field(min_length=2)
    offered_american: int
    correlation_overrides: list[CorrelationOverride] = Field(default_factory=list)
    kalshi_contracts_per_leg: int = Field(default=100, gt=0, le=1000)

    def overrides(self) -> Optional[dict[tuple[str, str], float]]:
        if not self.correlation_overrides:
            return None
        return {(o.a, o.b): o.rho for o in self.correlation_overrides}


def create_app(
    config: Optional[AppConfig] = None,
    *,
    gate_config: Optional[GateConfig] = None,
    risk_config: Optional[RiskConfig] = None,
    staleness_config: Optional[StalenessConfig] = None,
    odds_config: Optional[OddsConfig] = None,
) -> FastAPI:
    """Build the app.

    Every config is injectable. `AppConfig` already was, but the other three
    were read straight from the ambient environment, so an API test's behaviour
    depended on the developer's `.env` -- a machine with
    `LIVE_TRADING_ENABLED=true` or a different staleness limit ran a different
    test suite, and CI and a laptop could disagree about whether the code works.

    Injecting them also makes the gate and risk settings visible at the call
    site rather than implicit, which matters for the one app in this repo that
    can place an order.
    """
    app_config = config or AppConfig.load()
    gate = gate_config or GateConfig.load()
    risk = risk_config or RiskConfig.load()
    staleness = staleness_config or StalenessConfig.load()
    # Without the credential: this app never calls The Odds API, and the demo
    # instance holds no key. See `OddsConfig.load_without_credentials`.
    odds = odds_config or OddsConfig.load_without_credentials()

    app = FastAPI(
        title="Kalshi Betting Cockpit",
        description=(
            "Compares Kalshi prices against devigged sportsbook consensus. "
            "Surfaces an opportunity only when the edge survives fees, "
            "freshness, depth, and the suspicion checks."
        ),
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[app_config.cockpit_base_url],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    def require_auth(
        authorization: Annotated[Optional[str], Header()] = None,
    ) -> None:
        """Auth on every mutating route.

        The demo instance carries no token and exposes no mutating routes, so
        this is only ever reached on the live instance.
        """
        if app_config.is_demo:
            raise HTTPException(
                status_code=403,
                detail="This is the demo instance. It holds no credentials and "
                       "has no execution path.",
            )
        expected = app_config.auth_token
        if not expected:
            raise HTTPException(status_code=503, detail="No auth token configured")
        supplied = (authorization or "").removeprefix("Bearer ").strip()
        # Constant-time: a timing side-channel on a bearer token is small but
        # free to avoid.
        if not supplied or not secrets.compare_digest(supplied, expected):
            raise HTTPException(status_code=401, detail="Unauthorized")

    def get_conn():
        """A read-only connection per request.

        `cross_thread=True` is required and is not a shortcut. FastAPI runs a
        sync dependency and a sync path operation on **two different** threadpool
        workers, so the connection opened here is used from another thread and
        sqlite3's same-thread guard rejects it:

            sqlite3.ProgrammingError: SQLite objects created in a thread can
            only be used in that same thread

        That failed roughly 60% of requests on the deployed demo while
        `/api/health` stayed green -- health goes through Next's rewrite proxy
        and never touches this dependency. It does not reproduce under light
        local load, because an idle threadpool tends to hand out the same
        worker twice.

        Safe here because the connection is per-request and read-only: created,
        used, and closed in sequence by one request, never shared between
        concurrent ones. The guard stays on everywhere else -- see
        `store.db.connect`.
        """
        conn = db.open_db(app_config.db_path, read_only=True, cross_thread=True)
        try:
            yield conn
        finally:
            conn.close()

    # -- read routes -------------------------------------------------------

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "instance_mode": app_config.instance_mode,
            "live_trading_enabled": gate.live_trading_enabled,
            # Stated plainly so the demo cannot be mistaken for the real thing.
            "execution_available": not app_config.is_demo and gate.live_trading_enabled,
        }

    @app.get("/api/board")
    def board(
        conn=Depends(get_conn),
        include_suppressed: bool = Query(
            False, description="Include rejected candidates and why"
        ),
        limit: int = Query(100, le=500),
    ) -> dict:
        """Ranked opportunities, split by whether they can still be acted on.

        Suppressed rows are available behind a flag with their reasons -- they
        are evidence, not noise, and hiding them entirely would make a
        miscalibrated rule invisible.

        **Age is recomputed here, not read off the row.** `recommendations`
        stores the quote ages *as at the moment the row was written*, so a row
        made three hours ago still says "quote 3s old". Ordering by
        `suggested_contracts` over the whole table with no clock in it put the
        best row this instance ever recorded permanently at the top of the
        Board, rendered as a live buy with a size and a cost. The order endpoint
        would have refused it -- it recomputes ages the same way -- so no money
        was at risk. What was at risk is the reader: a page that says "Buy 15"
        for something the server will not sell.

        So a sized row is `surfaced` only while both its ages are still inside
        the staleness contract, and `expired` otherwise. Expired rows are
        returned rather than dropped: "there is nothing to bet" and "there was
        something and the moment has passed" call for different responses, and
        a filter that discards what it rejects cannot be audited.
        """
        now = db.now_ms()
        rows = conn.execute(
            "SELECT r.*, m.title AS market_title, m.yes_side_team, "
            "e.title AS event_title, e.commence_ms "
            "FROM recommendations r "
            "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
            "LEFT JOIN kalshi_events e ON e.event_ticker = m.event_ticker "
            "ORDER BY r.suggested_contracts DESC, r.edge_tenths DESC LIMIT ?",
            (limit,),
        ).fetchall()

        surfaced, expired, suppressed, no_edge = [], [], [], []
        for row in rows:
            item = _serialise(row, now_ms=now, staleness=staleness)
            if row["suggested_contracts"] > 0:
                (surfaced if item["actionable"] else expired).append(item)
            elif row["suppressed_reason"]:
                suppressed.append(item)
            else:
                no_edge.append(item)

        expired.sort(key=lambda r: r["created_ms"], reverse=True)

        return {
            "surfaced": surfaced,
            "expired": expired,
            "suppressed": suppressed if include_suppressed else [],
            "counts": {
                "surfaced": len(surfaced),
                "expired": len(expired),
                "suppressed": len(suppressed),
                "no_edge": len(no_edge),
            },
            "staleness": {
                "max_kalshi_quote_age_s": staleness.max_kalshi_quote_age_s,
                "max_odds_age_s": staleness.max_odds_age_s,
            },
            # An empty Board is the expected state most of the time. Saying so
            # here stops it reading as a malfunction.
            "note": (
                "Most candidates have no edge. An empty board is the normal "
                "result, not a failure."
            ),
        }

    @app.get("/api/window")
    def window(conn=Depends(get_conn)) -> dict:
        """Whether a pick could be bettable right now, and when the next chance is.

        Without this the Board is unreadable in the one way that matters. The
        odds budget affords two sweeps a day and each makes the slate bettable
        for fifteen minutes, so for roughly 23.5 hours a day every row on the
        Board is a row nobody can act on -- and an empty Board, a Board full of
        expired rows, and a Board during the window all render identically.

        Computed by the same planner the runner spends credits with, not a
        second implementation of it. A screen and a control that derive the same
        schedule by two paths eventually disagree, and the screen is the one
        that gets believed.
        """
        return window_status(
            conn,
            budget=CreditBudget(
                conn,
                daily_budget=odds.daily_credit_budget,
                day_start_hour=odds.budget_day_start_utc_hour,
            ),
            now_ms=db.now_ms(),
            max_odds_age_ms=staleness.max_odds_age_s * 1000,
            sweep_cost=odds.credits_per_sweep_per_sport,
        ).to_dict()

    @app.get("/api/market/{ticker}")
    def market(ticker: str, conn=Depends(get_conn)) -> dict:
        row = conn.execute(
            "SELECT r.*, m.title AS market_title, m.yes_side_team, m.volume_24h, "
            "m.open_interest, e.title AS event_title, e.commence_ms "
            "FROM recommendations r "
            "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
            "LEFT JOIN kalshi_events e ON e.event_ticker = m.event_ticker "
            "WHERE r.ticker = ? ORDER BY r.created_ms DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"No data for {ticker}")

        detail = _serialise(row)
        detail["volume_24h"] = row["volume_24h"]
        detail["open_interest"] = row["open_interest"]
        return detail

    @app.get("/api/ledger")
    def ledger(
        conn=Depends(get_conn),
        limit: int = Query(200, le=1000),
    ) -> dict:
        """Every recommendation, surfaced or not.

        This is the evidence base: each row is scored on closing-line value
        whether or not it was bet, which is what makes 300 scored observations
        reachable without 300 wagers.

        Progress is reported in **independent games**, matching what the gate
        actually counts. Reporting rows here would put "412 of 300" on this page
        beside a Gate screen reading "9 of 300", and the flattering number is the
        one that gets believed. Both are returned so the ratio between them stays
        visible rather than being quietly folded away.
        """
        rows = conn.execute(
            "SELECT * FROM recommendations ORDER BY created_ms DESC LIMIT ?",
            (limit,),
        ).fetchall()
        scored = clustered_clv(conn)

        return {
            "rows": [_serialise(r) for r in rows],
            "clv_scored": scored.n_clusters,
            "clv_scored_rows": scored.n_rows,
            "clv_required": gate.min_scored_recommendations,
            "gate_open": _gate_open(conn, gate),
        }

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
        """
        payload = evaluate_gate(conn, gate).to_dict()
        payload["bankroll_dollars"] = risk.bankroll_dollars
        payload["note"] = (
            "Freshness is not shown here because it is a property of a single "
            "order at a single instant, not of the system. It is checked again "
            "when an order is placed."
        )
        return payload

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

    # -- builder -----------------------------------------------------------

    @app.post("/api/builder/parlay")
    def price_parlay(request: ParlayRequest) -> dict:
        """Price a sportsbook parlay against devigged consensus.

        A read-only calculation on numbers the caller supplies, so it needs no
        auth -- and it is available on the demo instance, where it is one of the
        more interesting things to show.

        Same-game legs return 422 with the refusal text rather than a number.
        """
        legs = tuple(l.to_leg() for l in request.legs)
        try:
            valuation = value_parlay(
                ParlayQuote(
                    legs=legs,
                    offered_decimal=american_to_decimal(request.offered_american),
                ),
                correlation_overrides=request.overrides(),
            )
        except CorrelationRefused as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        alternative = kalshi_equivalent(
            legs,
            contracts_per_leg=request.kalshi_contracts_per_leg,
            correlation_overrides=request.overrides(),
        )
        return {
            "fair_probability": valuation.fair_probability,
            "naive_probability": valuation.naive_probability,
            "independence_error_points": valuation.independence_error_points,
            "fair_american": decimal_to_american(valuation.fair_decimal),
            "offered_american": request.offered_american,
            "hold": valuation.hold,
            "ev_per_dollar": valuation.ev_per_dollar,
            "is_positive_ev": valuation.is_positive_ev,
            "correlation_was_supplied": valuation.correlation_was_supplied,
            "verdict": valuation.verdict,
            "kalshi_alternative": {
                "total_cost_dollars": alternative.total_cost_dollars,
                "total_fee_dollars": alternative.total_fee_dollars,
                "fee_share_of_stake": alternative.fee_share_of_stake,
                "expected_value_dollars": alternative.expected_value_dollars,
                "note": alternative.note,
            },
        }

    @app.get("/api/builder/wong-screen")
    def wong_screen(
        lines: str = Query(
            ...,
            description="Comma-separated team:line pairs, e.g. 'Chiefs:-8,Jets:2'",
        ),
        points: float = Query(6.0),
    ) -> dict:
        """Filter a slate to the legs inside the documented Wong windows.

        Deliberately strict. The entire effect lives in favourites of −7.5 to
        −8.5 and underdogs of +1.5 to +2.5 on a six-point teaser, and a screen
        that returned near-misses would defeat its own purpose.
        """
        board: list[tuple[str, float]] = []
        for pair in lines.split(","):
            team, _, raw = pair.partition(":")
            try:
                board.append((team.strip(), float(raw)))
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"{pair!r} is not 'team:line'",
                ) from exc

        candidates = find_wong_candidates(board, points=points)
        return {
            "points": points,
            "screened": [{"team": t, "line": l} for t, l in board],
            "candidates": [{"team": t, "line": l} for t, l in candidates],
            "note": (
                "Being in the window is necessary, not sufficient. Pricing the "
                "teaser needs an empirical margin distribution fitted per "
                "spread bucket; without one the Builder refuses rather than "
                "guessing."
            ),
        }

    # -- write routes ------------------------------------------------------

    @app.post("/api/orders", dependencies=[Depends(require_auth)])
    async def place_order(request: OrderPlacementRequest) -> dict:
        """Place an order, or refuse with the specific unmet condition.

        Everything the UI checked is checked again here, against the database,
        at this instant. A disabled button is a hint to a human; this is the
        control. The order of the checks is deliberate -- cheapest and most
        decisive first, so a locked gate never reaches price validation.

        This route opens its own connection rather than taking the shared
        `get_conn` dependency. Two reasons, and the second is the load-bearing
        one: a control must read the state at the moment it decides, not the
        state a dependency resolved earlier; and SQLite connections are bound to
        the thread that created them, so a connection opened by a sync
        dependency in the threadpool cannot be used by this async route.
        """
        conn = db.open_db(app_config.db_path, read_only=True)
        try:
            return await _place_order(conn, request)
        finally:
            conn.close()

    async def _place_order(conn, request: OrderPlacementRequest) -> dict:
        # 1. The recommendation must exist. An unreadable one is a refusal, not
        #    a reason to fall back on whatever the client sent.
        freshness = recommendation_freshness(conn, request.recommendation_id)
        if not freshness["found"]:
            raise HTTPException(
                status_code=404,
                detail=f"recommendation {request.recommendation_id} does not exist",
            )

        # 2. A suppressed recommendation is not bettable, whatever the client
        #    thinks. The suppression reason travels with the refusal.
        if freshness["suppressed_reason"]:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"recommendation {request.recommendation_id} was suppressed: "
                    f"{freshness['suppressed_reason']}. Suppressed candidates are "
                    f"recorded for measurement, not offered for execution."
                ),
            )

        # 3. The engine must have authorised a bet at all.
        #
        # `suppressed_reason` being NULL does NOT mean "bettable". The engine
        # records a row for every candidate it evaluates, and its "no edge"
        # state is `suggested_contracts = 0` with no suppression reason -- that
        # distinction is deliberate, so a rejected bet and a bet with no edge
        # stay separable in the record. Checking only `suppressed_reason` turned
        # this endpoint into "buy any market in the recommendations table": on
        # the seeded demo, three rows the engine scored at -6.0c, -3.5c and
        # -1.2c per contract were fully orderable at maximum size.
        authorised = freshness["suggested_contracts"] or 0
        if authorised <= 0:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"recommendation {request.recommendation_id} was sized at "
                    f"{authorised} contracts -- the engine found no edge worth "
                    f"betting after fees. A row with no suppression reason is "
                    f"not the same as a row worth acting on."
                ),
            )

        # 4. Freshness, recomputed from the clock rather than read off the row.
        quote_age = freshness["kalshi_quote_age_ms"]
        odds_age = freshness["odds_age_ms"]
        if quote_age is None or odds_age is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "quote age is unreadable for this recommendation. Refusing: "
                    "an age that cannot be determined is not a fresh one."
                ),
            )
        # A negative age means the row was written with a clock ahead of ours.
        # Without this the freshness gate fails *open*, and fails open harder
        # the further the clock is wrong.
        if quote_age < 0 or odds_age < 0:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"recommendation {request.recommendation_id} reports a "
                    f"negative age (quote {quote_age}ms, odds {odds_age}ms), "
                    f"which means it was written with a clock ahead of this "
                    f"one. Refusing: an age that cannot be trusted is not a "
                    f"fresh one."
                ),
            )

        # 4. The gate, including freshness for this specific order.
        decision = evaluate_gate(
            conn, gate,
            staleness=staleness,
            kalshi_quote_age_ms=freshness["kalshi_quote_age_ms"],
            odds_age_ms=freshness["odds_age_ms"],
        )
        if not decision.open:
            raise HTTPException(
                status_code=423,   # Locked
                detail={
                    "message": "The live gate is locked.",
                    "reason": decision.reason,
                    "conditions": decision.to_dict()["conditions"],
                },
            )

        # 6. Size, server-side. The client proposes; the server decides, and it
        #    never exceeds what the engine authorised for this recommendation.
        #    The edge, the fee and the depth check were all computed at the
        #    engine's size, so a larger order is not the bet that was evaluated.
        contracts = min(
            request.contracts, authorised, risk.max_order_contracts
        )
        if contracts < risk.min_order_contracts:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{contracts} contracts is below the {risk.min_order_contracts} "
                    f"minimum. Fees round up on the whole order, so several tiny "
                    f"orders cost proportionally far more than one."
                ),
            )

        # 7. Portfolio caps, re-checked here rather than trusted from sizing.
        #    `size_position` applies these when a recommendation is written, but
        #    that was minutes ago and against a different portfolio. Exposure is
        #    a property of the account now, not of the row.
        exposure = _current_exposure_dollars(conn)
        if exposure is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "current exposure is unreadable, so no cap can be applied. "
                    "Refusing -- 'cannot determine the budget' must never "
                    "resolve to 'unlimited'."
                ),
            )
        order_cost = contracts * (freshness["entry_ask_tenths"] / 1000.0)
        if exposure + order_cost > risk.max_exposure_dollars:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"this order would take total exposure to "
                    f"${exposure + order_cost:.2f}, past the "
                    f"${risk.max_exposure_dollars:.2f} cap "
                    f"(${exposure:.2f} outstanding). Per-order caps do not "
                    f"bound the portfolio -- twenty compliant orders are not a "
                    f"compliant position."
                ),
            )
        if order_cost > risk.max_position_dollars:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"${order_cost:.2f} exceeds the ${risk.max_position_dollars:.2f} "
                    f"per-position cap"
                ),
            )

        # 6. Build the order. `OrderRequest` validates in its constructor and
        #    refuses an off-grid price rather than clamping it.
        try:
            order = OrderRequest(
                ticker=freshness["ticker"],
                side=freshness["side"],
                action="buy",
                count=contracts,
                limit_price_tenths=freshness["entry_ask_tenths"],
                recommendation_id=request.recommendation_id,
            )
        except OrderRefused as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        placer = OrderPlacer(dry_run=True)
        outcome = await placer.place(order)

        return {
            "status": outcome.status,
            "dry_run": outcome.dry_run,
            "client_order_id": order.client_order_id,
            "ticker": order.ticker,
            "side": order.side,
            "contracts": order.count,
            "limit_price_cents": order.api_price,
            "worst_case_cost_dollars": order.worst_case_cost_dollars,
            # The exact bytes. A dry run is comparable to a live order field by
            # field precisely because this is the same string either way.
            "request_body": outcome.request_body,
            "note": (
                "Dry run. The gate is open but live placement is not armed in "
                "this build -- the request body above is exactly what would be "
                "sent, and the client_order_id makes a retry idempotent."
            ),
        }

    return app


def _current_exposure_dollars(conn) -> Optional[float]:
    """Money currently at risk across open orders, or None if unreadable.

    `None` is a refusal, never zero. An exposure that cannot be read and an
    exposure of zero look identical to a cap check, and only one of them is
    safe to act on.

    Counts orders that are live or filled and not yet settled. A dry run has
    committed nothing, so it does not count -- but it is also not written to
    the table, which is a separate gap recorded in `tasks/todo.md`.
    """
    try:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(o.count * o.limit_price_tenths / 1000.0), 0.0) AS at_risk
            FROM orders o
            WHERE o.dry_run = 0
              AND o.status IN ('pending', 'resting', 'filled')
            """
        ).fetchone()
    except Exception:                                   # noqa: BLE001
        logger.exception("could not read current exposure")
        return None
    if row is None or row["at_risk"] is None:
        return None
    return float(row["at_risk"])


def _gate_open(conn, gate: GateConfig) -> bool:
    """One definition of open, shared by every caller.

    This used to be a second, independent implementation of the gate logic, and
    a looser one -- it never checked whether CLV survived the noise guard, so it
    would have reported open on a positive-but-indistinguishable record.
    """
    return evaluate_gate(conn, gate).open


def _live_ages(
    row,
    *,
    now_ms: Optional[int],
    staleness: Optional[StalenessConfig],
) -> dict:
    """Each stored age, moved forward to now, and whether both still pass.

    The reconstruction is the same one `gate.recommendation_freshness` performs
    for the order endpoint: the observation instant is `created_ms - stored_age`
    and the age is measured from there against the clock. Deliberately the same
    arithmetic, because a Board that computes freshness differently from the
    control that enforces it will eventually offer a row the server refuses.

    Returns `actionable: False` when there is no clock to measure against, and
    when an age is unreadable. An age that cannot be determined is not a fresh
    one -- the same refusal the order endpoint makes.
    """
    if now_ms is None or staleness is None:
        return {}

    elapsed = now_ms - row["created_ms"]

    def age_now(stored) -> Optional[int]:
        return None if stored is None else int(elapsed + stored)

    quote = age_now(row["kalshi_quote_age_ms"])
    odds = age_now(row["odds_age_ms"])
    actionable = (
        quote is not None
        and odds is not None
        and 0 <= quote <= staleness.max_kalshi_quote_age_s * 1000
        and 0 <= odds <= staleness.max_odds_age_s * 1000
    )
    return {
        "quote_age_now_ms": quote,
        "odds_age_now_ms": odds,
        "actionable": actionable,
    }


def _serialise(
    row,
    *,
    now_ms: Optional[int] = None,
    staleness: Optional[StalenessConfig] = None,
) -> dict:
    """Row -> JSON, with prices rendered for display alongside the raw tenths.

    Both forms are sent deliberately: the frontend must never re-derive a price
    from a float, and a human reading the payload should be able to see `50.3c`
    without doing arithmetic.

    `kalshi_quote_age_ms` and `odds_age_ms` stay exactly as recorded, because on
    the Ledger they are a historical fact about the observation and must not
    move. Pass `now_ms` and `staleness` to add the *current* ages beside them
    under distinct names, which is what the Board needs and what the Ledger
    must not silently be given: one field name meaning "then" on one screen and
    "now" on another is how the two screens come to disagree.
    """
    ask = row["entry_ask_tenths"]
    live = _live_ages(row, now_ms=now_ms, staleness=staleness)
    return {
        **live,
        "id": row["id"],
        "ticker": row["ticker"],
        "created_ms": row["created_ms"],
        "strategy_config_version": row["strategy_config_version"],
        "side": row["side"],
        "team": row["yes_side_team"] if "yes_side_team" in row.keys() else None,
        "event_title": row["event_title"] if "event_title" in row.keys() else None,
        "commence_ms": row["commence_ms"] if "commence_ms" in row.keys() else None,
        "ask_tenths": ask,
        "ask_display": format_price(ask),
        "ask_dollars": tenths_to_dollars(ask),
        "fair_probability": row["fair_probability"],
        "fair_display": format_price(int(round(row["fair_probability"] * 1000))),
        "edge_tenths": row["edge_tenths"],
        "edge_cents": row["edge_tenths"] / 10.0,
        "fee_predicted": row["fee_predicted"],
        "ev_net_dollars": row["ev_net_dollars"],
        "suggested_contracts": row["suggested_contracts"],
        "kelly_fraction": row["kelly_fraction"],
        "kalshi_quote_age_ms": row["kalshi_quote_age_ms"],
        "odds_age_ms": row["odds_age_ms"],
        "depth_at_ask": row["depth_at_ask"],
        "suppressed_reason": row["suppressed_reason"],
        "reason_text": row["reason_text"],
        "clv_tenths": row["clv_tenths"],
    }
