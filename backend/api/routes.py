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

import json
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ..analysis.marts import (
    WarehouseMissing,
    headline_verdicts,
    read_dashboards,
)
from ..config import (
    AppConfig,
    ConfigError,
    GateConfig,
    OddsConfig,
    RiskConfig,
    StalenessConfig,
)
from ..core.correlation import CorrelationRefused, Leg
from ..core.parlay import (
    ParlayQuote,
    american_to_decimal,
    decimal_to_american,
    kalshi_equivalent,
    value_parlay,
)
from ..core.ev import edge_after_fees_tenths
from ..core.prices import format_price, is_valid_price, tenths_to_dollars
from ..core.sizing import size_position, verify_positive_after_fees
from ..core.suppression import SuppressionConfig
from ..core.teaser import find_wong_candidates
from ..engine import suppression_summary
from ..gate import (
    clustered_clv,
    evaluate_gate,
    live_ages,
    recommendation_freshness,
)
from ..kalshi.orders import OrderPlacer, OrderRefused, OrderRequest
from ..kalshi.quotes import LiveQuote, LiveQuoteSource, QuoteUnavailable
from ..live import QuoteHub, sse
from ..logging_setup import configure_logging
from ..agents.base import AgentConfig
from ..notify.discord import DiscordConfig
from ..odds.budget import CreditBudget
from ..odds.timing import window_status
from ..store import db
from ..store.orders import (
    DuplicateOrder,
    ExposureCapExceeded,
    ORDERS_ARE_DRY_RUNS,
    current_exposure_dollars,
    find_by_idempotency_key,
    order_exposure_dollars,
    record_outcome,
    record_response,
    reserve_order,
)

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
    # **Required, not optional, and that is the decision.** An optional
    # idempotency key is a guard that fires only when the client remembers it,
    # which is the shape of a check that cannot fail. Making it required is what
    # turns "two taps are two orders" from a property of the client into a
    # property of the endpoint.
    #
    # The charset is restricted because this string is a database key and is
    # echoed in refusals; a UUID from `crypto.randomUUID()` satisfies it, and so
    # does anything a script would reasonably generate.
    idempotency_key: str = Field(
        min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
    )


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
    suppression_config: Optional[SuppressionConfig] = None,
    quote_source: Optional[LiveQuoteSource] = None,
    quote_hub: Optional[QuoteHub] = None,
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

    `quote_source` reads a market's book at the instant an order is decided.
    Left `None` it is built lazily from `KalshiConfig` on first use, because the
    demo instance holds no Kalshi credentials and must still boot -- both
    deploys run this function from one image.
    """
    # Logging is configured **here**, because this function is the only thing
    # every entry point has in common. `docker/entrypoint.sh` runs
    # `uvicorn backend.api.routes:create_app --factory`, so `backend/main.py`
    # -- which was the only place that called `basicConfig` -- is not executed
    # in production at all.
    #
    # The deployed API process therefore had **no logging configuration**.
    # Measured by starting it exactly as the entrypoint does: every `backend.*`
    # INFO record was dropped on the floor (the root logger has no handler, so
    # nothing below WARNING is emitted at all), and the records that did appear
    # went through Python's `lastResort` handler -- no timestamp, no level, no
    # logger name. `malformed book message: ...` reached Fly's log stream as a
    # bare sentence with nothing marking it as an error or saying where it came
    # from. The hub's whole "a dead feed must be visible" story is logged from
    # this process.
    #
    # It also means the redaction filter this repo added after leaking a live
    # credential was installed in the runner and not in the API. Nothing in the
    # API puts a key in a URL today, so this is defence that had quietly
    # stopped being in place rather than a leak -- which is exactly the state
    # it is worth catching in.
    #
    # Idempotent: `basicConfig` is a no-op once the root has a handler, and the
    # filters are added only if an instance is not already attached.
    configure_logging()

    app_config = config or AppConfig.load()
    gate = gate_config or GateConfig.load()
    risk = risk_config or RiskConfig.load()
    staleness = staleness_config or StalenessConfig.load()
    # Without the credential: this app never calls The Odds API, and the demo
    # instance holds no key. See `OddsConfig.load_without_credentials`.
    odds = odds_config or OddsConfig.load_without_credentials()
    # The same thresholds the engine judged the candidate against. The order
    # path re-applies the edge ceiling at the live price, so this must be the
    # engine's config rather than a second set of numbers that agrees today.
    #
    # Not named `suppression`: there is a route function by that name below, and
    # `def` in the same closure would rebind it -- which it silently did, so the
    # ceiling check read `edge_ceiling_tenths` off a FastAPI handler.
    thresholds = suppression_config or SuppressionConfig()

    # **The line that makes the line above provable.**
    #
    # `configure_logging()` was added here because the deployed API process had
    # no root handler at all -- the entrypoint runs uvicorn's factory, so
    # `backend/main.py` never executes. Verifying that fix in production turned
    # out to be impossible from the outside: uvicorn runs with `--no-access-log`,
    # the quote hub only speaks when something changes, and a steady-state log
    # window therefore contains *nothing* from this process whether logging
    # works or not. An hour of live logs answered the question either way.
    #
    # Absence of evidence read as evidence of absence is how the original defect
    # survived; a second silent process is not an improvement on the first. So
    # the API says one thing on every boot, at INFO, through the root logger it
    # has just configured. If this line is in the stream, logging reached this
    # process -- and if it is not, that is now a finding rather than a shrug.
    #
    # Nothing secret: every field here is already served publicly by
    # `/api/health`.
    logger.info(
        "API starting: instance_mode=%s live_trading_enabled=%s db=%s",
        app_config.instance_mode,
        gate.live_trading_enabled,
        app_config.db_path,
    )

    # One quote source per app, built on the first order rather than at boot.
    # Held in a dict rather than a closure variable so the lifespan and the
    # route see the same object without `nonlocal` gymnastics.
    quotes: dict[str, LiveQuoteSource] = {}
    if quote_source is not None:
        quotes["source"] = quote_source

    def live_quotes() -> LiveQuoteSource:
        if "source" not in quotes:
            quotes["source"] = LiveQuoteSource()
        return quotes["source"]

    # The ticker. Live instance only: it holds a Kalshi socket open, and the
    # demo deploy carries no credentials by design.
    hub: Optional[QuoteHub] = quote_hub
    if hub is None and not app_config.is_demo:
        hub = QuoteHub(
            app_config.db_path, risk=risk, staleness=staleness
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if hub is not None:
            await hub.start()
        yield
        if hub is not None:
            await hub.stop()
        # An injected source belongs to whoever injected it, but closing it here
        # anyway is right: the app is the only thing that used it, and leaking an
        # open httpx client per app in a test suite is how a run ends in
        # unclosed-socket warnings nobody reads.
        source = quotes.pop("source", None)
        if source is not None:
            await source.aclose()

    app = FastAPI(
        title="Kalshi Betting Cockpit",
        description=(
            "Compares Kalshi prices against devigged sportsbook consensus. "
            "Surfaces an opportunity only when the edge survives fees, "
            "freshness, depth, and the suspicion checks."
        ),
        version="0.1.0",
        lifespan=lifespan,
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
            # A boolean, never the credential. Setting a Fly secret from a
            # phone has no feedback of its own -- the loop logs `discord=on` at
            # startup and Fly's log tail has usually rolled past it by the time
            # anyone looks. Without this, "I set the secret" and "the secret is
            # in effect" are indistinguishable, and the failure is silence,
            # which is exactly what a working alerter also looks like on a quiet
            # night.
            "notifications_configured": DiscordConfig.from_env() is not None,
            # Whether `/api/stream/quotes` will do anything. The Board opens the
            # stream only when this is true, so the demo shows a static page
            # rather than an EventSource reconnect loop against a 503 -- which
            # is what a browser does with a failing stream, forever, silently.
            #
            # `is_running`, not `hub is not None`. The latter is a claim about
            # construction: a hub whose loop had died still satisfied it, and a
            # dead hub serves empty snapshots and heartbeats that read as a
            # quiet market. Health must report the thing running, not the object
            # existing.
            "live_quotes_available": hub is not None and hub.is_running,
            # A boolean, never the credential -- for exactly the reason given
            # above `notifications_configured`, which this mirrors. Setting a
            # Fly secret from a phone has no feedback of its own, and the
            # failure mode here is worse than Discord's: an unconfigured fleet
            # is **silent by design**. `AgentConfig.from_env()` returns None
            # without a key and every row comes back unreviewed, which is also
            # exactly what a working Skeptic looks like on a slate with nothing
            # surfaced -- and nothing has ever surfaced. Without this line,
            # "the key is set" and "the process can see the key" are
            # indistinguishable from outside, forever.
            #
            # Read from the environment on each request rather than cached at
            # boot: the answer this is asked for is "did the secret I just set
            # take effect", and a value captured at construction would answer a
            # question about the previous process.
            "agent_fleet_configured": AgentConfig.from_env() is not None,
        }

    @app.get("/api/stream/quotes")
    async def stream_quotes():
        """Live Kalshi prices, pushed. **A display, not a control.**

        Every frame here is derived and discarded: nothing on this path writes
        to `recommendations`, and `POST /api/orders` re-reads the book itself
        rather than trusting anything a browser was sent. Streaming makes the
        two usually agree; it does not make one able to stand in for the other.

        Not authenticated at this layer, and that is deliberate rather than an
        oversight: uvicorn binds loopback and is never published, so `/api/*` is
        reachable only through Next's rewrite, and the middleware cookie gate
        runs *before* rewrites. This is the same posture as `/api/board`, which
        carries the same prices.

        The heartbeat is the load-bearing part. A ticker that silently stops
        looks exactly like a market that went quiet, and the reader cannot tell
        which -- so a frame goes out on a fixed interval whether or not anything
        moved, and a dead feed is broadcast as an event rather than logged.
        """
        if hub is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "This instance holds no Kalshi credentials, so there is no "
                    "live feed to stream. The Board's prices are the recorded "
                    "ones and their age is shown on each card."
                ),
            )

        async def frames():
            async for event in hub.subscribe():
                yield sse(event)

        return StreamingResponse(
            frames(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                # nginx and several Fly-adjacent proxies buffer by default,
                # which turns a ticker into a page that updates in bursts every
                # few kilobytes -- indistinguishable from a laggy feed.
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

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

        So a sized row is `surfaced` while the server would still accept it and
        `expired` otherwise. Expired rows are returned rather than dropped:
        "there is nothing to bet" and "there was something and the moment has
        passed" call for different responses, and a filter that discards what it
        rejects cannot be audited.

        **What "would still accept it" means changed with the order-time quote
        refresh.** The endpoint re-reads Kalshi before pricing, so a row whose
        *recorded* quote has aged out is still orderable — at whatever the book
        says then. Splitting on both clocks would strike through most of the
        window's rows as expired while the server sold them, so the split is on
        the odds clock and `price_stale` counts the rows whose displayed price
        is older than the quote limit.
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
                # Bettable, but the price on the card is older than the quote
                # limit and will be re-read at order time. Counted rather than
                # folded into either bucket: "this price is current" and "this
                # bet is live" stopped being the same statement.
                "price_stale": sum(
                    1 for r in surfaced if not r.get("price_is_current")
                ),
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
                monthly_budget=odds.monthly_credit_budget,
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

        Everything the UI checked is checked again here, against the database
        *and against Kalshi*, at this instant. A disabled button is a hint to a
        human; this is the control. The order of the checks is deliberate --
        cheapest and most decisive first, so a locked gate never reaches price
        validation and never spends an API request.

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

    async def _refresh_quote(ticker: str) -> tuple[LiveQuote, int]:
        """The market's book now, and how old that observation is.

        Raises `HTTPException` rather than returning a sentinel, because there
        is no value this can return that means "I could not read the price" and
        is safe to price an order from. 503, not 422: nothing about the order is
        wrong, the exchange could not be read, and the two call for opposite
        responses from whoever is holding the phone.
        """
        observed = db.now_ms()
        try:
            quote = await live_quotes().fetch(ticker, observed_ms=observed)
        except ConfigError as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"no Kalshi credentials, so the recorded price cannot be "
                    f"re-checked before ordering: {exc}"
                ),
            ) from exc
        except QuoteUnavailable as exc:
            raise HTTPException(
                # 503 invites a retry and 422 does not, which is the whole
                # distinction: a dropped connection is worth tapping again and
                # a ticker the exchange has never heard of is not. Served as
                # 503, the second would have a person retrying forever.
                status_code=422 if exc.permanent else 503,
                detail=(
                    f"{exc} Refusing rather than falling back on the recorded "
                    f"price -- a price nobody could re-read is not a price."
                ),
            ) from exc
        return quote, quote.age_ms(db.now_ms())

    async def _place_order(conn, request: OrderPlacementRequest) -> dict:
        # 0. **Have we already answered this exact intent?**
        #
        #    Before everything, and the ordering is load-bearing rather than an
        #    optimisation. The failure this exists for is a tap whose response
        #    was lost -- a dropped connection on a train, a double-tap, a retry.
        #    By the time that second request arrives the recorded quote is
        #    usually past its 30-second limit, so *every* check below would
        #    refuse it with "the price moved" -- answering the one request that
        #    must be answered with what happened the first time.
        #
        #    This read cannot be the guarantee; two taps landing together both
        #    miss it. `reserve_order` re-checks inside its write lock and the
        #    UNIQUE index sits behind that. This is the cheap path and the one
        #    that survives staleness.
        replay = find_by_idempotency_key(conn, request.idempotency_key)
        if replay is not None:
            return _replay(replay)

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

        # 4. The ages on the record must be readable and must not come from a
        #    clock ahead of ours. Free, and it reads only the row -- so it runs
        #    before anything that costs a request.
        recorded_quote_age = freshness["kalshi_quote_age_ms"]
        odds_age = freshness["odds_age_ms"]
        if recorded_quote_age is None or odds_age is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "quote age is unreadable for this recommendation. Refusing: "
                    "an age that cannot be determined is not a fresh one."
                ),
            )
        # Without this the freshness gate fails *open*, and fails open harder
        # the further the clock is wrong.
        if recorded_quote_age < 0 or odds_age < 0:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"recommendation {request.recommendation_id} reports a "
                    f"negative age (quote {recorded_quote_age}ms, odds "
                    f"{odds_age}ms), which means it was written with a clock "
                    f"ahead of this one. Refusing: an age that cannot be "
                    f"trusted is not a fresh one."
                ),
            )

        # 5. The gate's standing conditions, before spending a Kalshi request.
        #    Same function as below and as the Gate screen, called without ages
        #    -- which is exactly what `evaluate_gate` documents that shape to
        #    mean. It is not a second, looser gate: every condition it checks is
        #    re-checked in step 8 alongside freshness, so this can only ever
        #    refuse earlier, never permit something the full check would not.
        #
        #    First among the free checks because it is the most decisive. With
        #    no evidence the gate is locked and will stay locked, so "the live
        #    gate is locked" is the answer worth giving even when the row also
        #    has some other problem.
        standing = evaluate_gate(conn, gate)
        if not standing.open:
            raise HTTPException(
                status_code=423,   # Locked
                detail={
                    "message": "The live gate is locked.",
                    "reason": standing.reason,
                    "conditions": standing.to_dict()["conditions"],
                },
            )

        # 6. The game must not have started. Free, reads only the record, and it
        #    goes before the network call.
        #
        #    **The runner already refuses to record a started game** -- measured
        #    on one live pass, 36 of 104 rows were in-progress, with edges
        #    running -200.3 to +67.7 tenths against -39.2 to -17.7 for the
        #    pre-game rows on the same slate. What it does not do is retract a
        #    row it wrote *before* kickoff. That row keeps its size and stays
        #    inside the 900s odds window for a quarter of an hour after the ball
        #    is in the air, and re-reading Kalshi at order time makes it worse
        #    rather than better: the ask is now a live in-play price and the
        #    fair value beside it is a pre-game consensus, so the "edge" is two
        #    different questions subtracted from each other.
        #
        #    The clock is **the sportsbook's**. Kalshi's `occurrence_datetime`
        #    runs three hours late and would wave the whole first half through.
        commence_ms = freshness["commence_ms"]
        if commence_ms is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"recommendation {request.recommendation_id} has no linked "
                    f"sportsbook fixture, so there is no kickoff to check it "
                    f"against. Refusing: 'we cannot tell whether this game has "
                    f"started' must not resolve to 'it has not'."
                ),
            )
        if commence_ms <= db.now_ms():
            raise HTTPException(
                status_code=422,
                detail=(
                    f"this game started at {commence_ms}. The fair value on the "
                    f"record is a pre-game consensus and the Kalshi price is now "
                    f"an in-play one; the difference between them is not an edge. "
                    f"In-play is a different product and this tool does not "
                    f"price it."
                ),
            )

        # 7. Re-read the price from Kalshi. **The recorded ask is provenance
        #    from here on, not the price of anything.**
        #
        #    Confirmation (`engine.confirm_recommendation`) narrows the gap
        #    between "this was true fifteen seconds ago" and "this is true now"
        #    to the quote-pass interval. It cannot close it, and fifteen seconds
        #    is not nothing on a venue quoted by sub-200ms market makers. So the
        #    order is priced, sized and capped against a quote observed inside
        #    this request, and the recorded one is reported beside it so a move
        #    is visible rather than absorbed.
        quote, live_quote_age = await _refresh_quote(freshness["ticker"])
        if not quote.tradeable:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{quote.ticker} is {quote.status!r}, not tradeable. The "
                    f"recommendation was written while it was open; that is a "
                    f"fact about the past, not an offer."
                ),
            )

        side = freshness["side"]
        recorded_ask = freshness["entry_ask_tenths"]
        live_ask = quote.ask_tenths(side)
        # `is_valid_price`, not `is None`, and the difference is the whole
        # check. **Kalshi sends `"0.0000"` for an absent bid, never a missing
        # key** -- 38 of 245 markets in the nested capture carry
        # `yes_bid_dollars == "0.0000"`. So a one-sided book parses cleanly to
        # `0` and derives an ask of `1000`, and a `None` test never fires on the
        # case it was written for: a guard that cannot fire, which is the shape
        # this repo keeps re-finding. 1000 is not a price, it is a settled
        # outcome, and here it means nobody is offering this side at all.
        if not is_valid_price(live_ask):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{quote.ticker} has no {side} offer right now"
                    + (
                        " -- the opposing bid is unreadable"
                        if live_ask is None
                        else " -- nothing is resting on the other side, so there "
                             "is nothing to lift"
                    )
                    + f". Refusing rather than falling back on the recorded "
                      f"{format_price(recorded_ask)}."
                ),
            )

        # 7. Freshness, judged on the quote we just took rather than the one on
        #    the row. That is the point of step 6: the Kalshi half of the
        #    comparison is now seconds old by construction, so what binds is the
        #    sportsbook consensus -- which this endpoint cannot refresh, because
        #    the credit budget affords about sixteen calls a day.
        decision = evaluate_gate(
            conn, gate,
            staleness=staleness,
            kalshi_quote_age_ms=live_quote_age,
            odds_age_ms=odds_age,
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

        # 8. Exposure **now**, not when the row was written. This is what makes
        #    step 9 a real risk control rather than a re-run of the engine's
        #    arithmetic: the sizer applies the position and exposure caps
        #    against the portfolio as it stands at this instant.
        # The population this order will join, not a different one. Sizing
        # against live exposure and then reserving against paper (or the
        # reverse) would admit an order the cap was never applied to.
        exposure = current_exposure_dollars(conn, dry_run=ORDERS_ARE_DRY_RUNS)
        if exposure is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "current exposure is unreadable, so no cap can be applied. "
                    "Refusing -- 'cannot determine the budget' must never "
                    "resolve to 'unlimited'."
                ),
            )

        # 9. Re-size at the live ask, through the engine's own sizer.
        #
        #    A price that moved does not merely change what the order costs, it
        #    changes how big the order should be: quarter-Kelly at a 5c edge is
        #    a different number from quarter-Kelly at 3c, and buying the old
        #    size at the new price is over-betting the edge that actually
        #    exists. Calling `size_position` rather than inventing a
        #    "how far may a price move" threshold means there is one definition
        #    of how big a bet is, and a price that has moved far enough to erase
        #    the edge returns zero contracts without anyone choosing a tolerance.
        fair = freshness["fair_probability"]
        resized = size_position(
            side=side,
            ask_tenths=live_ask,
            fair_probability=fair,
            risk=risk,
            current_exposure_dollars=exposure,
        )
        moved = live_ask - recorded_ask
        if resized.refused or resized.contracts <= 0:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"the price moved. Recorded {format_price(recorded_ask)}, "
                    f"live {format_price(live_ask)} ({moved / 10:+.1f}c). At the "
                    f"live price this is {resized.contracts} contracts "
                    f"({resized.binding_constraint})"
                    + (f": {resized.refusal_reason}" if resized.refusal_reason else "")
                    + ". The bet that was evaluated is not the bet on offer."
                ),
            )

        # 10. Size, server-side. The client proposes; the server decides, and it
        #     never exceeds what the engine authorised for this recommendation.
        #     `authorised` still binds even when the price *improved* and the
        #     sizer would now allow more -- a better price is not a mandate to
        #     bet bigger than the decision that was recorded and will be scored.
        contracts = min(
            request.contracts, authorised, resized.contracts, risk.max_order_contracts
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

        # 11. Fillability, at the live book. The engine checked depth when the
        #     row was written; that book is gone. `None` refuses -- "no size
        #     quoted" and "size unreadable" are both reasons not to send an
        #     order that would rest unfilled and poison the paper record with a
        #     fill that never happened.
        depth = quote.depth_at_ask(side)
        if depth is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"no size is quoted at the {side} ask on {quote.ticker} "
                    f"right now. An edge you cannot fill is not an edge."
                ),
            )
        if depth < contracts:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{depth:.0f} contracts rest at {format_price(live_ask)} and "
                    f"this order is {contracts}. Refusing: an edge you cannot "
                    f"fill is not an edge, and a partial fill records an entry "
                    f"price the record cannot reproduce."
                ),
            )
        # Stated rather than implied, because the check above is weaker than it
        # reads. Depth is a snapshot one round trip old, and the order is a
        # plain GTC limit -- no `time_in_force`, no cancel path in this repo --
        # so a bid lifted in between leaves a resting remainder. The refusal
        # bounds the size against the book we saw; it does not make the fill
        # atomic, and nothing here can.
        if depth < contracts * 2:
            logger.info(
                "%s: %.0f resting against a %d-contract order -- thin enough "
                "that a fill is not assured",
                quote.ticker, depth, contracts,
            )

        # 12. **A large apparent edge is a bug until proven otherwise**, and the
        #     price having just moved in our favour is not an exception to that
        #     -- it is the most likely way to produce one.
        #
        #     Re-sizing at the live ask is one-sided by construction: an adverse
        #     move shrinks the order to zero and refuses, while a favourable move
        #     simply buys more, up to what the engine authorised. On a venue
        #     quoted to ~2c by sub-200ms market makers, an ask that has fallen
        #     six cents since the row was written is not six cents of found
        #     money. It is thirteen professional firms deciding this side is
        #     worse, and we are the last to know.
        #
        #     `suppression.edge_ceiling_tenths` catches exactly this at
        #     recommendation time and was not being applied at order time, so
        #     the refresh had opened a path where the one number the whole
        #     project treats as a defect signal was instead acted on.
        live_edge = edge_after_fees_tenths(
            ask_tenths=live_ask,
            contracts=contracts,
            fair_probability=fair,
        )
        if live_edge > thresholds.edge_ceiling_tenths:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"the live price implies a {live_edge / 10:.1f}c edge, past "
                    f"the {thresholds.edge_ceiling_tenths / 10:.0f}c ceiling. "
                    f"Recorded {format_price(recorded_ask)}, live "
                    f"{format_price(live_ask)} ({moved / 10:+.1f}c). Treat this "
                    f"as a data defect -- a stale fixture, a settled leg, or "
                    f"news this side has not priced -- until investigated. A "
                    f"price that moved this far in our favour is the most likely "
                    f"way to manufacture an edge, not to find one."
                ),
            )

        # 13. The whole-order EV, at the live price and the final size. Sizing
        #     amortises the fee per contract; this re-evaluates the actual
        #     order, which is where a marginal bet turns negative.
        if not verify_positive_after_fees(
            side=side,
            ask_tenths=live_ask,
            contracts=contracts,
            fair_probability=fair,
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{contracts} contracts at {format_price(live_ask)} is not "
                    f"+EV once the whole-order fee is applied against a fair "
                    f"value of {format_price(int(round(fair * 1000)))}."
                ),
            )

        # The portfolio caps used to be re-checked here, against the recorded
        # ask, because `size_position` had last seen them "minutes ago and
        # against a different portfolio". Step 9 removed that reason: the sizer
        # now runs *in this request*, at the live ask, against the exposure read
        # four lines above it, and it bounds `contracts * effective_price` --
        # which is fee-inclusive and therefore strictly above the raw
        # `contracts * ask` this used to compare. So the re-check could no
        # longer fire on any input, and a guard that cannot fire is
        # indistinguishable from one that is working.
        #
        # Deleted rather than left beside the sizer, per `tasks/lessons.md`:
        # don't test that two paths agree, delete one of the paths. The caps are
        # verified *at order time* by
        # `TestTheCapsStillBindThroughTheSizer` -- which is the claim that
        # matters and the one the duplicate was standing in for.

        # 13. Build the order. `OrderRequest` validates in its constructor and
        #     refuses an off-grid price rather than clamping it.
        #
        #     The grid comes off the **live** payload, not the recorded row: a
        #     market's price structure can change while it is open, and a grid
        #     cached at recommendation time is exactly as stale as the price
        #     beside it. If it could not be read we refuse, because the
        #     alternative -- assuming whole cents -- is what turned a 50.5c ask
        #     into a bid at 50c that rests forever and never fills.
        if quote.price_grid is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "the live payload for this market carried no readable "
                    "price grid, so we do not know which limit prices the "
                    "exchange will accept. Refusing rather than assuming whole "
                    "cents."
                ),
            )
        try:
            order = OrderRequest(
                ticker=freshness["ticker"],
                side=side,
                action="buy",
                count=contracts,
                limit_price_tenths=live_ask,
                price_grid=quote.price_grid,
                recommendation_id=request.recommendation_id,
            )
        except OrderRefused as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        placer = OrderPlacer(dry_run=ORDERS_ARE_DRY_RUNS)

        # 14. **Write it down before sending it.**
        #
        #     `client_order_id` is the idempotency key, and it is worth nothing
        #     unless it is durable before the request leaves this process. The
        #     failure it exists for is a POST that times out *after* Kalshi
        #     accepted it: there is an order in the book, no response in hand,
        #     and the only safe retry is the same id. Recording after the
        #     response loses the key in exactly the case it was invented for.
        #
        #     It also closes the smaller gap that made this item worth doing:
        #     CLV scores off `entry_ask_tenths` and the order goes out at the
        #     live ask, so the price the gate's evidence is built on and the
        #     price we would actually pay were different numbers with nothing
        #     joining them. `orders.recommendation_id` is that join.
        #
        #     A separate, writable connection, opened in a worker thread. The
        #     decision above is made against a read-only handle on purpose --
        #     the API cannot corrupt the evidence record while deciding -- and
        #     that property is worth keeping, so only the recording step opens
        #     a writer. `sqlite3` blocks, and `busy_timeout` means it may block
        #     for seconds while the runner is mid-pass, which must not stall
        #     the event loop and the SSE ticker riding on it.
        submitted_ms = db.now_ms()
        try:
            order_row_id = await run_in_threadpool(
                _write_intent,
                app_config.db_path,
                order,
                dry_run=placer.dry_run,
                submitted_ms=submitted_ms,
                max_exposure_dollars=risk.max_exposure_dollars,
                idempotency_key=request.idempotency_key,
            )
        except DuplicateOrder as exc:
            # Two taps landed together: both missed the read at step 0, and the
            # second one blocked at `BEGIN IMMEDIATE` until the first had
            # written its row. Nothing was sent and nothing was rolled back that
            # mattered -- this is the mechanism working, so it answers with the
            # first attempt's outcome exactly as a later duplicate would.
            logger.info(
                "duplicate order for %s on key %s; replaying row %d",
                order.ticker, request.idempotency_key, exc.row["id"],
            )
            return _replay(exc.row)
        except ExposureCapExceeded as exc:
            # A risk refusal, not a storage failure, and the row was rolled
            # back rather than left pending. 422 rather than 503: retrying
            # changes nothing until a position closes, and 503 invites exactly
            # the retry that would arrive while the portfolio is still full.
            logger.warning("refusing %s: %s", order.ticker, exc)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:                        # noqa: BLE001
            logger.exception(
                "refusing to place %s: the order could not be recorded first",
                order.ticker,
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    f"the order was not sent, because it could not be written "
                    f"down first: {exc}. An order this system cannot record is "
                    f"one it cannot reconcile, cancel or score, and the "
                    f"evidence record is the product. Refusing is the safe "
                    f"direction -- nothing has been committed."
                ),
            ) from exc

        outcome = await placer.place(order)

        # 15. Stamp the row with what came back. This one must **not** unwind
        #     the order: by now the request has gone, and on a live order the
        #     money has moved whatever this connection does. The row is already
        #     on disk in `pending` carrying the idempotency key, which is
        #     precisely the state reconciliation reads. So it is reported
        #     rather than raised.
        outcome_recorded = True
        try:
            await run_in_threadpool(
                _write_outcome, app_config.db_path, order_row_id, outcome
            )
        except Exception:                               # noqa: BLE001
            outcome_recorded = False
            logger.exception(
                "order row %d for %s was placed (%s) and could not be updated. "
                "It stays 'pending' -- reconcile against client_order_id=%s.",
                order_row_id, order.ticker, outcome.status, order.client_order_id,
            )

        order_contribution = order_exposure_dollars(order)

        body = {
            "status": outcome.status,
            "dry_run": outcome.dry_run,
            "order_id": order_row_id,
            "client_order_id": order.client_order_id,
            "ticker": order.ticker,
            "side": order.side,
            "contracts": order.count,
            # Both the YES-book price actually sent and what it costs on our
            # side. V2 quotes everything from the YES leg, so for a NO bet the
            # number in the request body is the complement of the price we pay
            # -- reporting only one of them would put a 59.5c figure on a
            # ticket for a 40.5c bet.
            "book_side": order.book_side,
            "limit_price_dollars": order.api_price_dollars,
            "limit_price_tenths": order.api_price_tenths,
            "fill_price_tenths": order.fill_price_tenths,
            "fill_price_display": format_price(order.fill_price_tenths),
            "price_grid": order.price_grid.describe(),
            "worst_case_cost_dollars": order.worst_case_cost_dollars,
            # Both prices, always -- including when they agree. A response that
            # reported the move only when there was one would leave the reader
            # unable to tell "the price held" from "nobody looked".
            "quote": {
                "recorded_ask_tenths": recorded_ask,
                "recorded_ask_display": format_price(recorded_ask),
                "live_ask_tenths": live_ask,
                "live_ask_display": format_price(live_ask),
                "moved_tenths": moved,
                "observed_ms": quote.observed_ms,
                "age_ms": live_quote_age,
                "depth_at_ask": depth,
                "authorised_contracts": authorised,
                "resized_contracts": resized.contracts,
                "binding_constraint": resized.binding_constraint,
                "note": (
                    "Priced at the live ask. The recorded ask is provenance: "
                    "it is what the decision was made against and what CLV "
                    "will be scored on."
                ),
            },
            # What the caps were measured against, and what this order would
            # make of them. `resulting_exposure_dollars` counts *this* order,
            # which on a dry run is a hypothetical and says so rather than
            # letting a ticket imply money has been committed.
            #
            # `exposure_before_dollars` is the number `size_position` above
            # actually used, not a re-read -- a second read would be a second
            # path to disagree with the first.
            "exposure_before_dollars": exposure,
            # `null` rather than the bare `exposure` if the contribution cannot
            # be read. Falling back to the before-figure would render a ticket
            # saying this order costs nothing, which is the one reading a
            # person would act on without hesitating.
            "resulting_exposure_dollars": (
                None if order_contribution is None else exposure + order_contribution
            ),
            "resulting_exposure_is_hypothetical": outcome.dry_run,
            "max_exposure_dollars": risk.max_exposure_dollars,
            # The exact bytes. A dry run is comparable to a live order field by
            # field precisely because this is the same string either way.
            "request_body": outcome.request_body,
            "recorded": {
                "order_id": order_row_id,
                "outcome_recorded": outcome_recorded,
                "note": (
                    "Recorded before the request was made, so the "
                    "client_order_id survives a lost response."
                    if outcome_recorded
                    else
                    f"The order was placed and the row could not be updated. "
                    f"It is still 'pending' -- reconcile "
                    f"client_order_id={order.client_order_id} against Kalshi "
                    f"before assuming it did not happen."
                ),
            },
            "note": (
                "Dry run. The gate is open but live placement is not armed in "
                "this build -- the request body above is exactly what would be "
                "sent, and the client_order_id makes a retry idempotent."
            ),
            "replayed": False,
        }

        # 16. Store the answer, so a duplicate tap is given this one rather
        #     than placing a second order.
        #
        #     Reported, never raised, for the same reason as step 15: the
        #     request has gone. What is lost if this fails is only the *replay*
        #     -- a later duplicate finds the row with a NULL response and
        #     refuses, which is the safe direction and is what a row we never
        #     answered actually means.
        try:
            await run_in_threadpool(
                _write_response, app_config.db_path, order_row_id, body
            )
        except Exception:                               # noqa: BLE001
            logger.exception(
                "order row %d for %s could not store its response. A duplicate "
                "tap on key %s will refuse rather than replay.",
                order_row_id, order.ticker, request.idempotency_key,
            )
            body["recorded"]["response_stored"] = False
        else:
            body["recorded"]["response_stored"] = True

        return body

    return app


def _replay(row) -> dict:
    """Answer a duplicate tap with what the first one was told.

    Returned verbatim from `response_body_json` rather than rebuilt from the
    columns. Rebuilding would be a second implementation of the response shape,
    free to drift from the first -- and it would drift *silently*, because the
    only thing that renders it is a duplicate tap, which is by definition the
    path nobody exercises by hand.

    One field is added: `replayed`. The record must not claim a second order was
    placed, and a byte-identical response would say exactly that.

    A `NULL` response means the first attempt was recorded and never answered --
    the process died between reserving the row and replying, so an order may be
    resting on the exchange under that row's `client_order_id`. **That is not
    safe to retry**, and it refuses rather than re-sending: this is
    unreadable-must-never-resolve-to-zero applied to an open position.
    """
    stored = row["response_body_json"]
    if stored is None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"an order for this idempotency key was recorded as row "
                f"{row['id']} and never answered, so whether it reached the "
                f"exchange is unknown. Refusing to send a second one. "
                f"Reconcile client_order_id={row['client_order_id']} against "
                f"Kalshi before trying again; a new key would place a second "
                f"order on top of an unknown first."
            ),
        )
    try:
        body = json.loads(stored)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                f"an order for this idempotency key exists as row {row['id']} "
                f"and its stored response could not be read back, so it cannot "
                f"be replayed. Refusing to send a second one."
            ),
        ) from exc
    body["replayed"] = True
    body["replay_note"] = (
        "This is the answer the first request was given. No second order was "
        "sent -- the key you supplied had already been used."
    )
    return body


def _write_intent(
    db_path,
    order: OrderRequest,
    *,
    dry_run: bool,
    submitted_ms: int,
    max_exposure_dollars: float,
    idempotency_key: str,
) -> int:
    """Record the order on its own writable connection. Runs in a worker thread.

    Opened and closed here rather than shared, for the reason the order route
    already gives about its read-only handle: a connection is bound to the
    thread that made it, and this one is made inside the threadpool worker that
    uses it. Short-lived is also what keeps the write lock held for the
    smallest possible window while the runner is writing a pass.

    `reserve_order` rather than `record_intent`, so the cap is applied to the
    portfolio *including* this order, inside the transaction that writes it.
    The exposure the sizer used at step 8 was read on the read-only handle and
    is a snapshot; two requests can share one. This is where that stops
    mattering.
    """
    conn = db.open_db(db_path)
    try:
        return reserve_order(
            conn,
            order,
            dry_run=dry_run,
            submitted_ms=submitted_ms,
            max_exposure_dollars=max_exposure_dollars,
            idempotency_key=idempotency_key,
        )
    finally:
        conn.close()


def _write_response(db_path, order_row_id: int, body: dict) -> None:
    """Store the answer, so a duplicate tap can be given the same one."""
    conn = db.open_db(db_path)
    try:
        record_response(conn, order_row_id, json.dumps(body, sort_keys=True))
    finally:
        conn.close()


def _write_outcome(db_path, order_row_id: int, outcome) -> None:
    """Stamp the placed order with its result. Runs in a worker thread."""
    conn = db.open_db(db_path)
    try:
        record_outcome(conn, order_row_id, outcome)
    finally:
        conn.close()


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

    **The reconstruction is `gate.live_ages`, not a copy of it.** This used to
    restate the arithmetic beside a comment promising it matched the order
    endpoint's, which is the shape this repo keeps getting caught by: two paths
    that agree until one of them learns something. It learned something --
    `last_confirmed_ms` moves the instant a row is measured from -- and a Board
    still measuring from `created_ms` would strike through rows the server would
    happily sell.

    Returns `actionable: False` when there is no clock to measure against, and
    when an age is unreadable. An age that cannot be determined is not a fresh
    one -- the same refusal the order endpoint makes.

    **`actionable` is the odds clock, not both clocks.** The order endpoint
    re-reads the Kalshi quote inside the request (`kalshi/quotes.py`), so the
    recorded quote's age no longer decides whether an order is accepted --
    which makes a row struck through for a stale *quote* a row the server would
    happily sell. That is the two-screens-disagree failure with the conservative
    sign, and it is not harmless: between thirty seconds and fifteen minutes
    after a pass, which is most of the window, every sized row was being buried
    under "the moment has passed".

    What the recorded quote age still decides is whether the **price on the
    card** is the price you would pay, which is a different claim and gets its
    own field. Both are sent, because a page that showed only the first would
    offer a sized bet at a number the order will not honour.
    """
    if now_ms is None or staleness is None:
        return {}

    ages = live_ages(row, now_ms=now_ms)
    quote, odds = ages.quote_age_ms, ages.odds_age_ms
    readable = quote is not None and odds is not None and quote >= 0 and odds >= 0
    return {
        "quote_age_now_ms": quote,
        "odds_age_now_ms": odds,
        # The consensus cannot be refreshed without spending a credit, so this
        # is the limit that actually ends a row's life.
        "actionable": readable and odds <= staleness.max_odds_age_s * 1000,
        # The Kalshi half. False means "orderable, but expect the price to move
        # under you" -- not "expired".
        "price_is_current": readable and quote <= staleness.max_kalshi_quote_age_s * 1000,
        # Surfaced so the Board can say *why* a row is still live. A price
        # re-checked fifteen seconds ago and a price nobody has looked at since
        # it was written are different claims, and only one should reassure.
        "freshness_confirmed": ages.confirmed,
        "freshness_measured_from_ms": ages.measured_from_ms,
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
