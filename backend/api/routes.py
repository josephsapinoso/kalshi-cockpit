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
import math
import secrets
from contextlib import asynccontextmanager
from statistics import NormalDist
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
    assert_kalshi_quote_age_limits_agree,
    assert_odds_age_limits_agree,
    retired_settings_present,
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
from ..core.prices import (
    format_price,
    format_probability,
    is_valid_price,
    tenths_to_dollars,
)
from ..core.sizing import size_position, verify_positive_after_fees
from ..core.suppression import SuppressionConfig
from ..core.teaser import find_wong_candidates
from ..engine import suppression_summary
from ..analysis.clv import DEFAULT_HORIZON_HOURS
from ..gate import (
    POPULATIONS,
    clustered_clv,
    evaluate_gate,
    live_ages,
    population_counts,
    recommendation_freshness,
)
from ..kalshi.orders import OrderPlacer, OrderRefused, OrderRequest
from ..kalshi.quotes import LiveQuote, LiveQuoteSource, QuoteUnavailable
from ..live import QuoteHub, sse
from ..logging_setup import configure_logging
from ..market_results import result_coverage
from ..agents.base import AgentConfig
from ..notify.discord import DiscordConfig
from ..odds.budget import CreditBudget
from ..odds.timing import SLATE_WINDOW_MS, window_status
from ..playbook import read_playbook
from ..settlement import daily_realised_pnl_dollars, open_position_dollars
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

    # Two limits on one quantity, checked where the environment actually is.
    # ADR 0019 section 6. Refuses to start rather than serve a window banner
    # that disagrees with what the runner schedules.
    assert_odds_age_limits_agree(
        suppression_max_odds_age_ms=thresholds.max_odds_age_ms,
        staleness=staleness,
    )
    # Its twin, one field up in the same dataclass, and the sharper of the two:
    # a diverged quote age puts a row on the Board as `actionable` that this
    # same process then refuses at the order endpoint.
    assert_kalshi_quote_age_limits_agree(
        suppression_max_kalshi_quote_age_ms=thresholds.max_kalshi_quote_age_ms,
        staleness=staleness,
    )

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
            app_config.db_path, risk=risk, staleness=staleness,
            # One roll hour for the risk day, shared with the order endpoint and
            # the odds budget. Two definitions of "today" in one process is how
            # the looser one wins in silence.
            day_start_hour=odds.budget_day_start_utc_hour,
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
            # Retired settings still present in this process's environment.
            # Empty is healthy.
            #
            # Here rather than only in the log because this is the one
            # diagnostic reachable from a phone, and because a stale setting is
            # exactly the thing whose *absence* of effect is invisible: the
            # value is not read, so nothing downstream misbehaves in a way
            # anyone would notice, and the operator goes on believing it still
            # does something. `config.RETIRED_SETTINGS` says why this must not
            # raise at boot instead.
            #
            # Read from the environment per request, like `agent_fleet_
            # configured` above and for the same reason: the question is "did
            # the secret I just unset take effect", which a value captured at
            # construction cannot answer.
            "retired_settings_set": sorted(retired_settings_present()),
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
            False,
            description=(
                "Include the rest of the slate: rejected candidates with their "
                "reasons, and the ones with no edge at all"
            ),
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

        **Which hundred rows, which is the other half of the bug above.** The
        paragraph about age fixed the *rendering* and left the *selection*
        exactly as it was: `ORDER BY suggested_contracts DESC, edge_tenths DESC
        LIMIT 100` over the whole table, with no clock in it. Recomputing the
        age of a row cannot help when the row should not have been fetched.

        With `suggested_contracts = 0` on essentially every row ever written,
        that ordering collapses to `edge_tenths DESC` across the entire history
        of the database — so the Board was the hundred largest apparent edges
        this instance has ever recorded, rendered as today's slate under "the
        rest of the slate", with no date on any of them. That is the selection
        this repo's first rule warns about: a large apparent edge is a bug until
        proven otherwise, and `suspicious_edge` rows sort straight to the top of
        it. The truncation is the sharp end — the ordinary rows are the ones
        `LIMIT` drops, so the sample is biased *by construction* toward the rows
        least likely to be real.

        So selection is now on the clock and never on the edge:

        - **The window** is `SLATE_WINDOW_MS` back from `anchor_ms`, the most
          recent freshness basis in the table. Anchored on the record rather
          than on `now` because a slate is a thing this instance recorded, not a
          thing the wall clock did: anchoring on `now` would blank the Board —
          and the demo — the moment the loop stopped, which is when the rows are
          most worth reading. The cost of that choice is that a dead loop shows
          its last slate, so `slate.is_current` and `slate.age_ms` say outright
          how old what you are looking at is.
        - **Within the window**, `suggested_contracts DESC` (a bettable row must
          never be the one `LIMIT` drops) then the freshness basis, newest
          first. `edge_tenths` no longer participates in selection at all; it
          only orders `surfaced`, which is a complete bucket rather than a
          truncated sample.
        - **Nothing is silently discarded.** `slate.in_window` is the whole
          window before `LIMIT`, `slate.returned` is what came back,
          `slate.truncated` says the two differ, and `slate.older_than_window`
          counts the history that was deliberately left off. An empty table
          (`anchor_ms = null`) and a stale slate (`is_current = false`) are
          different states and read differently.

        The window is applied twice on purpose. `_BASIS_SQL` restates
        `gate.live_ages`' basis in SQL as a *bound* on what to fetch; the
        decision is then re-made on `freshness_measured_from_ms`, which is
        `live_ages` itself. A half-written confirmation — a timestamp with a
        missing age — is newer in SQL and older to `live_ages`, and only the
        second reading may decide.
        """
        now = db.now_ms()
        anchor_row = conn.execute(
            f"SELECT MAX({_BASIS_SQL}) AS anchor_ms, COUNT(*) AS total "
            "FROM recommendations r"
        ).fetchone()
        anchor = None if anchor_row["anchor_ms"] is None else int(anchor_row["anchor_ms"])
        recorded_total = int(anchor_row["total"] or 0)
        since = None if anchor is None else anchor - SLATE_WINDOW_MS

        rows, in_window = [], 0
        if since is not None:
            # Full scan of `recommendations`: the basis is an expression over two
            # columns and no index covers it. The table is small (~1.5k rows on
            # the live instance after a year) and this is three reads a page
            # load, so an index would be a guess at a cost nobody has measured.
            in_window = int(
                conn.execute(
                    f"SELECT COUNT(*) AS n FROM recommendations r "
                    f"WHERE {_BASIS_SQL} >= ?",
                    (since,),
                ).fetchone()["n"]
            )
            rows = conn.execute(
                "SELECT r.*, m.title AS market_title, m.yes_side_team, "
                "e.title AS event_title, e.commence_ms "
                "FROM recommendations r "
                "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
                "LEFT JOIN kalshi_events e ON e.event_ticker = m.event_ticker "
                f"WHERE {_BASIS_SQL} >= ? "
                f"ORDER BY r.suggested_contracts DESC, {_BASIS_SQL} DESC, r.id DESC "
                "LIMIT ?",
                (since, limit),
            ).fetchall()

        surfaced, expired, suppressed, no_edge = [], [], [], []
        for row in rows:
            item = _serialise(row, now_ms=now, staleness=staleness)
            # The window, decided by `live_ages` rather than by the SQL that
            # fetched the row. See the docstring: the two can only disagree
            # towards *older*, and older means off the slate.
            if since is not None and item["freshness_measured_from_ms"] < since:
                continue
            if row["suggested_contracts"] > 0:
                (surfaced if item["actionable"] else expired).append(item)
            elif row["suppressed_reason"]:
                suppressed.append(item)
            else:
                no_edge.append(item)

        # Presentation order, stated for every bucket rather than inherited from
        # the query for some of them. `suppressed` and `no_edge` used to come
        # back in whatever order the ranking happened to leave them in, which on
        # the old query meant descending apparent edge -- the ranking this
        # endpoint no longer does anywhere.
        surfaced.sort(key=lambda r: (-r["suggested_contracts"], -r["edge_tenths"]))
        expired.sort(key=lambda r: r["created_ms"], reverse=True)
        suppressed.sort(key=lambda r: r["freshness_measured_from_ms"], reverse=True)
        no_edge.sort(key=lambda r: r["freshness_measured_from_ms"], reverse=True)
        returned = len(surfaced) + len(expired) + len(suppressed) + len(no_edge)

        return {
            "surfaced": surfaced,
            "expired": expired,
            "suppressed": suppressed if include_suppressed else [],
            # The rest of the slate, and the reason it is returned at all:
            # mispricing is a factor, not a filter. A board that shows only the
            # rows that survived every check cannot be read as evidence about
            # the checks -- and with zero actionable across ~200 decisions, the
            # rows that did not survive are the only content there is.
            #
            # **This relaxes nothing.** `suggested_contracts` is still 0 on
            # every row here, the suppression reasons are unchanged, and the
            # order endpoint re-derives all of it server-side. Suppression and
            # staleness stop governing what is *visible*; they keep governing
            # what is bettable.
            "no_edge": no_edge if include_suppressed else [],
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
            # **Which rows this is, and which rows it is not.** Every field here
            # exists so that the four lists above cannot be read as more than
            # they are. Without it a slate from last night and a slate from
            # ninety seconds ago render identically, which is the bug this
            # endpoint has now had twice.
            "slate": {
                # The most recent freshness basis in the table: when this
                # instance last decided anything. `None` means it never has.
                "anchor_ms": anchor,
                # How old that is. The number that says whether the list below
                # is a slate or a souvenir.
                "age_ms": None if anchor is None else max(0, now - anchor),
                "since_ms": since,
                "window_ms": SLATE_WINDOW_MS,
                # Whether the instance is still recording. False with rows
                # present is a different state from an empty table and needs a
                # different sentence on the page.
                "is_current": anchor is not None and now - anchor <= SLATE_WINDOW_MS,
                # The window before `limit`, and what survived it. A page that
                # cannot tell it is looking at a truncated slate cannot be read
                # as evidence about the slate.
                "in_window": in_window,
                "returned": returned,
                "truncated": in_window > len(rows),
                # The history deliberately left off. Stated rather than
                # implied: this is precisely the population the Board used to
                # rank by apparent edge and show as today.
                "recorded_total": recorded_total,
                "older_than_window": max(0, recorded_total - in_window),
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
        offset: int = Query(0, ge=0),
        max_id: Optional[int] = Query(None, ge=1),
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

        **The payload says whether it is a slice or the table.** `rows` is
        windowed by `LIMIT`, and until `total` was returned beside it there was
        no way to tell 1,000 rows from all of them -- so any count computed off
        the payload was a claim about the most recent `limit` rows wearing the
        label of a claim about the record. `SELECT COUNT(*)` is the cheapest
        arithmetic in this file and it converts an unanswerable question into a
        subtraction.

        **And whether it is horizon-mixed.** `horizons` counts the whole table
        by `clv_horizon_hours`, not the returned window, because that is the one
        breakdown a slice cannot be trusted to report: the legacy 1.0h rows are
        the *oldest* ones and `ORDER BY created_ms DESC` is precisely the window
        that hides them. `primary_horizon_hours` names the anchor the gate
        counts, so a reader does not have to know which key is the current one.

        **`offset` exists so the table can be read whole.** `limit` caps at
        1,000 against 1,535 rows -- and `engine.persist_if_changed` writes a row
        only when the ask or the fair *moved*, so rows-per-game tracks price
        volatility and the newest slice is weighted toward volatile,
        wide-disagreement games. That is the direction that **inflates** an
        apparent edge, which is why paging is a prerequisite for a decisive
        measurement rather than a convenience.

        **`max_id` is the load-bearing half of that, and `offset` alone is a
        trap.** `ORDER BY created_ms DESC` sorts newest first, so a row written
        *during* a multi-page pull lands on page 0 and pushes every later page
        along by one. The recorder writes ~500-600 rows a day in sweeps, and
        **[MEASURED on live, 2026-08-10] one `created_ms` on this table carries
        84 rows**, so a sweep landing mid-pull shifts the window by most of a
        page. This is not hypothetical and it is not rare; it is what an active
        slate does.

        Reproduced directly, 120 rows pulled in four pages of 30 with one
        84-row sweep landing between page 0 and page 1:

            unpinned            returned 120, distinct  90, duplicated 30,
                                and 84 original rows never returned
            pinned to max_id    returned 120, distinct 120, duplicated  0

        **The failure is silent.** `returned` is 30 on every page, the four
        pages sum to 120, and `total` agrees -- so every check the payload
        supports passes while a quarter of the pull is duplicates and 84 rows
        are simply absent. A consumer would report a whole-table measurement
        over a multiset that is not the table.

        So a whole-table pull reads `max_id` from the first page and passes it
        back on every subsequent page. `id` is `INTEGER PRIMARY KEY
        AUTOINCREMENT`, so `id <= max_id` names a fixed prefix of the table that
        later writes cannot enter: the snapshot is immutable by construction
        rather than by hoping the recorder is idle. **`total` is counted under
        the same pin**, so paging until `offset + returned == total` terminates
        on the snapshot and not on a target that keeps moving.

        **The ordering also gains `id DESC`, and that one is hardening rather
        than a fix.** Ties are the normal case here -- [MEASURED] the newest
        1,000 rows carry only **169 distinct `created_ms` values** and 960 of
        them tie with at least one other row -- and within a tie
        `ORDER BY created_ms DESC` alone leaves the order unspecified by SQL,
        resting on whichever plan the query planner picks. It was measured to
        page consistently on a static table today, so no corruption is being
        claimed; but adding the `fair_prices` join below already changed the
        plan (`USE TEMP B-TREE FOR RIGHT PART OF ORDER BY`), and a paging
        contract that depends on a plan staying put is one optimiser change
        from being wrong. `(created_ms DESC, id DESC)` is a **total** order, so
        it cannot be. It also makes the route honest about "newest first":
        under the old ordering the 84 rows of one sweep came back
        oldest-`id`-first inside a descending page.
        """
        rows = conn.execute(
            # **The four devig methods travel with the row, not just the one
            # used.** `fair_probability` is `p_conservative` -- the *lowest*
            # reading across methods for the side being bought
            # (`devig.conservative_probability`) -- which is a deliberate
            # downward bias on fair value, and a downward bias mechanically
            # produces `edge <= 0`. Without the other three, no consumer can
            # ask what that policy costs, and `actionable = 0` cannot be
            # separated into "Kalshi is sharp" and "we chose a low fair".
            #
            # Raw columns rather than a computed spread or a server-side
            # histogram, on purpose: deploys are batched, so anything baked in
            # here costs a release to re-cut, while raw rows are re-cut for
            # free in a tested local module.
            #
            # `p_conservative` is sent beside the other four although it should
            # equal `fair_probability` exactly -- that equality is the check
            # that the `fair_price_id` join landed on the right row, and a
            # consumer cannot make it if only one of the pair is present.
            #
            # LEFT JOIN, and the four are `None` when it misses. `fair_price_id`
            # is nullable and the four `p_*` columns are themselves nullable in
            # `fair_prices`, so a missing method is a real state -- and per this
            # repo's rule it resolves to `None`, never `0`. A `0.0` here would
            # be a fair probability of zero, which is a legitimate value, so the
            # two states would be indistinguishable.
            #
            # **`market_width`, `book_count` and `books_used` are named here
            # for the same reason, and they had to be named.** `SELECT r.*`
            # does not reach them: all three live on `fair_prices`, not on
            # `recommendations`, so the join alone put nothing in the result
            # set and `_serialise` could not have emitted them however it was
            # written. ADR 0021's closing section records that these three were
            # never observed over the whole 1,564-row record, which left two of
            # the brief's registered predicates unanswerable; this is the half
            # of the fix that lives in SQL.
            #
            # They answer a question the five `p_*` columns cannot.
            # `market_width` is the books' disagreement and `book_count` is how
            # many opinions survived `runner.SHARP_BOOKS` anchoring -- so
            # ADR 0021 §7.2's tautology reading ("we tested Kalshi against the
            # only references plausibly as sharp as Kalshi") is checkable from
            # the record rather than only from a fixture captured on a
            # different day. `books_used` names *which* books, which is the
            # part no count can recover.
            #
            # **`anchored_on_sharp` is the fourth, and it is the one that
            # decides whether that reading holds at all.** The anchoring is
            # `selected = sharp or usable` (`backend/core/devig.py:288-289`), so
            # on a row where **no** sharp book quoted it falls back silently to
            # the full book set -- and that row was compared against a *wide*
            # consensus, not against the sharp reference class. Whether that
            # ever happened is data, not code, and `book_count` cannot reveal
            # it: three sharp books and three soft ones both read `3`. Without
            # this column §7.2's central claim is unfalsifiable on the record.
            "SELECT r.*, "
            "       f.p_multiplicative, f.p_additive, f.p_power, f.p_shin, "
            "       f.p_conservative, "
            "       f.market_width, f.book_count, f.books_used, "
            "       f.anchored_on_sharp "
            "FROM recommendations r "
            "LEFT JOIN fair_prices f ON f.id = r.fair_price_id "
            "WHERE (? IS NULL OR r.id <= ?) "
            "ORDER BY r.created_ms DESC, r.id DESC LIMIT ? OFFSET ?",
            (max_id, max_id, limit, offset),
        ).fetchall()
        # Counted under the same pin as the rows, or paging to `total` never
        # terminates on an active slate: the target would grow while the pull
        # walks it. Unpinned, this is the whole table exactly as before.
        total = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM recommendations "
                "WHERE (? IS NULL OR id <= ?)",
                (max_id, max_id),
            ).fetchone()["n"]
        )
        # The newest id **in the table**, not in the page -- so a caller can
        # pin a snapshot from page 0 without having read the rows, and so a
        # pinned pull can still see that the table has moved on.
        newest_id = conn.execute(
            "SELECT MAX(id) AS m FROM recommendations"
        ).fetchone()["m"]
        # `null` for the unscored, keyed as a string because JSON object keys
        # are strings and `0.0` and `1.0` must stay distinguishable from each
        # other and from "not scored".
        horizons = {
            ("unscored" if r["h"] is None else f"{float(r['h']):g}"): int(r["n"])
            for r in conn.execute(
                "SELECT clv_horizon_hours AS h, COUNT(*) AS n "
                "FROM recommendations GROUP BY clv_horizon_hours"
            ).fetchall()
        }
        scored = clustered_clv(conn)

        return {
            "rows": [_serialise(r) for r in rows],
            "clv_scored": scored.n_clusters,
            "clv_scored_rows": scored.n_rows,
            "clv_required": gate.min_scored_recommendations,
            "gate_open": _gate_open(conn, gate),
            # Slice or table. `returned` is `len(rows)` and is sent anyway: the
            # comparison a reader needs is a one-glance one, and making them
            # count an array to make it is how the check stops being made.
            "total": total,
            "returned": len(rows),
            "limit": limit,
            # Echoed so a pull assembled from several pages can prove which
            # pages it holds. `total`, `returned` and `limit` alone cannot
            # distinguish "I fetched every page" from "I fetched page 0 twice".
            "offset": offset,
            # The pin in force on this response, echoed back rather than
            # assumed: `None` says the caller is reading a moving table and any
            # multi-page pull off it is unsound.
            "max_id": max_id,
            # The newest id in the table. Pass it back as `max_id` to pin a
            # snapshot. Under a pin it also reports how far the table has moved
            # since -- `newest_id > max_id` means rows arrived during the pull
            # and were correctly excluded, which is the check that the pin did
            # something rather than the check that it was unnecessary.
            "newest_id": newest_id,
            "horizons": horizons,
            "primary_horizon_hours": DEFAULT_HORIZON_HOURS,
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
        payload["bankroll_dollars"] = risk.bankroll_dollars
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
        #
        #    **And against the other two halves of the risk state, which this
        #    endpoint did not read until 2026-08-10.** `exposure` above was the
        #    only one of the three the sizer ever received; `current_position_
        #    dollars` and `daily_pnl_dollars` fell through to defaults of `0.0`,
        #    so the per-market cap and the daily loss limit were applied to a
        #    number nobody had measured. Driven end to end against 40 settled
        #    positions totalling -$20,000 realised, this route returned HTTP 200.
        #
        #    Read here, in the request, for the same reason `exposure` is: a
        #    control must read the state at the moment it decides. Both return
        #    `None` when unreadable and the sizer refuses on `None`, so a
        #    database this endpoint cannot interrogate stops the order instead of
        #    silently widening every cap.
        #
        #    `dry_run=ORDERS_ARE_DRY_RUNS` on both, matching `exposure`: an order
        #    is admitted against history of its own kind, and pooling paper with
        #    live would let fictional losses stop a real bet or -- worse -- a
        #    fictional profit hold the kill switch open.
        fair = freshness["fair_probability"]
        daily_pnl = daily_realised_pnl_dollars(
            conn,
            now_ms=db.now_ms(),
            dry_run=ORDERS_ARE_DRY_RUNS,
            # The configured hour, not the constant, so the risk day and the
            # odds budget day cannot diverge through `.env`.
            day_start_hour=odds.budget_day_start_utc_hour,
        )
        position = open_position_dollars(
            conn, quote.ticker, dry_run=ORDERS_ARE_DRY_RUNS
        )
        resized = size_position(
            side=side,
            ask_tenths=live_ask,
            fair_probability=fair,
            risk=risk,
            current_exposure_dollars=exposure,
            current_position_dollars=position,
            daily_pnl_dollars=daily_pnl,
        )
        moved = live_ask - recorded_ask
        # **A refusal and a zero are different answers and now say so.** They
        # shared one message, whose headline was "the price moved" -- true for
        # the zero, and a lie for every refusal the risk state produces. An
        # operator whose kill switch has engaged would have been told the market
        # moved against them and invited to try another price, which is the one
        # response that must not follow a loss limit. The reason string was
        # appended, so the information was present; it was behind a sentence
        # contradicting it, and this repo has recorded what happens when a
        # legible wrong number sits beside a correct one.
        if resized.refused:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"refusing to size this order ({resized.binding_constraint}): "
                    f"{resized.refusal_reason}"
                ),
            )
        if resized.contracts <= 0:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"the price moved. Recorded {format_price(recorded_ask)}, "
                    f"live {format_price(live_ask)} ({moved / 10:+.1f}c). At the "
                    f"live price this is {resized.contracts} contracts "
                    f"({resized.binding_constraint})"
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
        # No flat minimum here any more, and its removal is not a relaxation:
        # step 13 below re-evaluates *this* order at *this* size against the
        # real fee curve, which is the thing the minimum was a proxy for. The
        # proxy was price-independent and the quantity is not — measured, the
        # per-order rounding penalty it existed to prevent is 0.00c at 50c at
        # every size and at most 0.88c on a single contract in the 20c/80c band.
        # At a $100 bankroll the constant refused every order the tool could
        # produce, silently, by returning a plausible zero. See `core.sizing`.

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


# A row's freshness basis, in SQL, for the row alias `r`.
#
# **A bound, never a decision.** `gate.live_ages` owns what instant a row is
# measured from, and `_live_ages` below reports it as
# `freshness_measured_from_ms`. This expression exists only so `/api/board` can
# ask SQLite for the current slate without reading the whole table, and it is
# deliberately the *loose* form: it takes any `last_confirmed_ms` at face value,
# where `live_ages` additionally requires both confirmed ages to be present.
#
# That asymmetry is the safe direction and is the reason it is written this way
# rather than mirrored exactly. A half-written confirmation is *newer* here and
# *older* there, so this over-selects and `live_ages` then removes the row --
# whereas an exact copy would be two implementations of one boundary, which is
# the failure `gate.live_ages` and `odds/timing._SERVED_SWEEP` were both written
# to end.
_BASIS_SQL = "MAX(r.created_ms, COALESCE(r.last_confirmed_ms, r.created_ms))"


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


# A week of betting at the rate this tool could ever support. Stated as a
# constant and sent with the probability it produces, so the screen cannot
# report the number against a different run length than the one it was
# computed for.
LOSING_RUN_BETS = 10


def _losing_run_probability(ev_dollars: float, sd_dollars: float) -> Optional[float]:
    """How often `LOSING_RUN_BETS` bets of this shape end down, edge and all.

    Normal approximation to the sum of ten independent bets, each with mean
    `ev_dollars` and deviation `sd_dollars`:
    ``P(sum < 0) = Phi(-sqrt(k) * mu / sigma)``.

    **`None` when there is no position**, never 0.5 and never 0. A row the
    engine did not size has no run to lose, and an unmeasurable probability
    that renders as a number is the failure this repo has recorded twice.

    Verified against the review's figure: the demo's best row is +$0.2619 with
    a $7.4778 deviation, which gives 0.456 -- the 46% quoted there.
    """
    if sd_dollars <= 0:
        return None
    return NormalDist().cdf(-math.sqrt(LOSING_RUN_BETS) * ev_dollars / sd_dollars)


def _decode_books_used(raw) -> Optional[list[str]]:
    """`fair_prices.books_used` (a JSON array in TEXT) -> a list, or `None`.

    **Never `[]` on failure.** An empty list is a real answer -- it says the
    consensus was built from no book at all, which would be a serious defect
    worth seeing -- so it cannot double as "this could not be read". Unreadable
    resolves to `None` and the caller refuses, per `tasks/lessons.md`.

    `None` in means the `LEFT JOIN` on `fair_prices` missed. Anything that is
    not a JSON array of strings means the column is corrupt, which has never
    been observed and would be a real finding rather than something to paper
    over with a default.
    """
    if raw is None:
        return None
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(decoded, list) or not all(isinstance(b, str) for b in decoded):
        return None
    return decoded


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
    contracts = row["suggested_contracts"] or 0
    fee = row["fee_predicted"] or 0.0
    # A binary contract settles at $1 or $0, so one contract's payoff has a
    # spread of exactly $1 and a standard deviation of sqrt(p(1-p)). The fee is
    # deterministic and adds no variance, so the position's deviation is just
    # that times the size. Reproduced against the demo's best row before
    # anything derived from it was rendered: 15 contracts at p=0.5385 gives
    # $7.478, against $0.262 expected -- 29 times the mean.
    fair = row["fair_probability"]
    sd = contracts * math.sqrt(max(0.0, fair * (1.0 - fair)))
    # Cost stays in integer tenths until the last step. `ask * contracts` is
    # exact; `tenths_to_dollars(ask) * contracts` is not.
    stake = tenths_to_dollars(ask * contracts)
    # **All four devig readings, when the caller joined them in.** Present only
    # on the Ledger, which is the one route that joins `fair_prices` through
    # `recommendations.fair_price_id`; the Board and the market detail select
    # from `recommendations` alone and get `{}` here rather than five null keys
    # pretending the join was attempted and empty.
    #
    # `row.keys()` rather than a parameter, matching how `yes_side_team` and
    # `event_title` are already handled: the shape of the row is what decides,
    # so a caller cannot ask for the fields and silently get nulls because its
    # query lacked the join.
    methods = (
        {
            "p_multiplicative": row["p_multiplicative"],
            "p_additive": row["p_additive"],
            "p_power": row["p_power"],
            "p_shin": row["p_shin"],
            # Should equal `fair_probability` exactly. Sent so a consumer can
            # check the join landed on the right `fair_prices` row rather than
            # assuming it.
            "p_conservative": row["p_conservative"],
        }
        if "p_conservative" in row.keys()
        else {}
    )
    # **How much consensus there was, and whose.** Same join, same route, same
    # presence rule as `methods` above -- these three live on `fair_prices` and
    # only the Ledger reaches them.
    #
    # ADR 0021's closing section records that these were *never observed* over
    # the whole 1,564-row record, so two of the predicates the measurement brief
    # registered went unanswered. The reason was never that the join was
    # missing: it has been there since the four devig readings were added. The
    # SELECT list simply named five `f.` columns and not eight, and this dict is
    # hand-built and named none of them. Both halves had to change.
    #
    # What they make answerable, which the five `p_*` columns cannot:
    #
    # - `book_count` is how many books survived `runner.SHARP_BOOKS` anchoring.
    #   ADR 0021 §7.2 argues the whole refutation may be a tautology -- Kalshi
    #   compared only against references as sharp as Kalshi -- and quotes a
    #   magnitude ("a median of 26 of 29 usable books discarded") measured on a
    #   *fixture captured 5.65 hours before the record's earliest odds
    #   observation*, overlapping it on zero of 1,564 rows. This column is what
    #   replaces that borrowed number with one measured on the record itself.
    # - `market_width` is the surviving books' disagreement, and it is the
    #   suppression input behind `too_few_books` / `no_market_width`.
    # - `books_used` names *which* books. No count recovers that, and "three
    #   books agreed" means something different when the three are two
    #   exchanges and Pinnacle.
    #
    # **`market_width = None` on a joined row is a real state, not a gap.** One
    # book cannot disagree with itself, so there is no width to report, and
    # `0.0` is simultaneously a legitimate reading (two books quoting
    # identically). `core/devig.py` splits them for exactly that reason and this
    # payload must not collapse them back -- see `tasks/lessons.md`, *the zero
    # that means "no measurement" passes every threshold*.
    #
    # **`book_count` is the join's own tell.** It is `NOT NULL` in
    # `fair_prices`, so `book_count is None` on a row where the key is present
    # means the `LEFT JOIN` missed and nothing else. That is what lets a
    # consumer read `market_width is None` as "unmeasurable" rather than as
    # "unjoined" without guessing.
    consensus = (
        {
            "market_width": row["market_width"],
            "book_count": row["book_count"],
            # Stored as a JSON array in a TEXT column; decoded here so a
            # consumer is not handed JSON inside JSON. `None` rather than `[]`
            # on anything unreadable -- an empty list is a claim that no book
            # was used, which is a different fact from "we could not tell".
            "books_used": _decode_books_used(row["books_used"]),
            # **Did the sharp anchoring actually bind on this row?**
            # `selected = sharp or usable`, so `False` means no sharp book
            # quoted and the fair value came from the *full* book set -- a wide
            # consensus wearing a sharp consensus's name.
            #
            # Stored as INTEGER 0/1 and surfaced as a real bool, because
            # `0` and `False` read identically in JSON while `None` must stay
            # distinct: the column is `NOT NULL DEFAULT 0` in `fair_prices`, so
            # `None` here means the LEFT JOIN missed and nothing else.
            "anchored_on_sharp": (
                None
                if row["anchored_on_sharp"] is None
                else bool(row["anchored_on_sharp"])
            ),
        }
        if "book_count" in row.keys()
        else {}
    )
    return {
        **live,
        **methods,
        **consensus,
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
        # The same number as a percentage, which is what it actually is. Kept
        # beside `fair_display` rather than replacing it because the ticker,
        # the ledger and any script reading this payload move at different
        # speeds -- but nothing on screen may render the `c` form any more.
        "fair_percent_display": format_probability(row["fair_probability"]),
        "edge_tenths": row["edge_tenths"],
        "edge_cents": row["edge_tenths"] / 10.0,
        "fee_predicted": row["fee_predicted"],
        "ev_net_dollars": row["ev_net_dollars"],
        "suggested_contracts": row["suggested_contracts"],
        # **The size the record counts, beside the size you may buy.** These are
        # two different questions and the payload used to answer only the first,
        # which made the second unanswerable from anywhere but a log line:
        # `gate.POPULATIONS` splits `actionable` on `reference_contracts`, so a
        # consumer holding only `suggested_contracts` cannot tell why a row was
        # or was not counted, and at the deployed $100 bankroll the two columns
        # genuinely differ on every row written since 78b5790. See ADR 0015.
        #
        # `None` is passed through rather than coerced to 0. A NULL here means a
        # row that predates schema v6 and escaped the backfill, which is a
        # different state from "the strategy had no bet", and the repo's rule is
        # that unreadable resolves to `None`, never `0`.
        "reference_contracts": row["reference_contracts"],
        "kelly_fraction": row["kelly_fraction"],
        "kalshi_quote_age_ms": row["kalshi_quote_age_ms"],
        "odds_age_ms": row["odds_age_ms"],
        "depth_at_ask": row["depth_at_ask"],
        "suppressed_reason": row["suppressed_reason"],
        "reason_text": row["reason_text"],
        "clv_tenths": row["clv_tenths"],
        # **Which anchor produced `clv_tenths`, carried rather than inferred.**
        #
        # `clv_tenths` is a bare number and nothing else in this payload says
        # what it was measured against, so without this a consumer counting
        # scored rows silently pools the current 0.0h anchor with the legacy
        # 1.0h one that migration v5 tags and deliberately never re-scores.
        # That mixture is not neutral: a 1h line is a weaker benchmark (a market
        # sharpens as the event approaches -- `analysis/clv.py`), so pooling
        # biases any resulting number in the **flattering** direction. It is
        # exactly how a reconnaissance pass counted 743 scored rows against the
        # 476 the gate reports at the primary horizon.
        #
        # `None` means unscored, and is distinct from any horizon value --
        # including 0.0, which is a legitimate anchor and must never be tested
        # for truthiness.
        "clv_horizon_hours": row["clv_horizon_hours"],
        # -- what it costs, and what it costs you when it loses ---------------
        #
        # The card showed `COST` as stake alone and `FEE` beside it with no
        # total anywhere, which understates what leaves the account by 3.6% at
        # 50c and 10% at 10c. Computed here and not in the browser: the fee
        # curve is an unresolved hedge between two disagreeing sources, and a
        # second implementation of it in TypeScript would be two money
        # calculations one refresh apart.
        "stake_dollars": stake,
        "total_cost_dollars": stake + fee,
        "sd_dollars": sd,
        # How often a run of `LOSING_RUN_BETS` bets this shape ends down, if the
        # edge is entirely real. The answer on the demo's best row is 46%, and
        # that is the number a beginner does not supply from memory: without it
        # a losing week reads as a broken tool or an invitation to double up.
        "losing_run_bets": LOSING_RUN_BETS,
        "losing_run_probability": _losing_run_probability(
            row["ev_net_dollars"], sd
        ),
    }
