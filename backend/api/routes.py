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
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from ..config import (
    POSITION_FRACTION_OF_BANKROLL,
    REFERENCE_BANKROLL_DOLLARS,
    AppConfig,
    BuildInfo,
    ConfigError,
    GateConfig,
    ManualOrderConfig,
    OddsConfig,
    KalshiConfig,
    RiskConfig,
    StalenessConfig,
    assert_kalshi_quote_age_limits_agree,
    assert_odds_age_limits_agree,
    assert_risk_day_start_agrees,
    retired_settings_present,
)
from ..core.ev import breakeven_win_rate, edge_after_fees_tenths
from ..core.fees import combo_taker_fee
from ..core.prices import (
    PRICE_MAX,
    format_price,
    is_valid_price,
)
from ..core.sizing import size_position, verify_positive_after_fees
from .. import bets as bets_module
from .. import estimates as bet_estimates
from ..core.suppression import SuppressionConfig, gauntlet_view
from ..core.trust import TrustThresholds
from ..gate import (
    evaluate_gate,
    population_counts,
    recommendation_freshness,
)
from ..kalshi.candles import parse_chart_candle
from ..kalshi.orders import OrderPlacer, OrderRefused, OrderRequest
from ..list_filters import (
    MAX_WITHIN_HOURS,
    FilterRefused,
    ListFilter,
    parse_list_filter,
)
from ..kalshi.rest import KalshiRestClient, parse_position_fp
from ..kalshi.quotes import LiveQuote, LiveQuoteSource, QuoteUnavailable
# The shard reader is shared with the combination path rather than
# reimplemented: one parser for `balance_breakdown`, one place to be
# wrong about the venue's field names.
from ..store.combo_orders import read_shard_funds
from ..live import QuoteHub, sse
from ..logging_setup import configure_logging
from ..agents.base import AgentConfig
from ..notify.alerts import Alerter
from ..notify.discord import DiscordConfig
from ..odds.budget import CreditBudget
from ..odds.timing import (
    DEFAULT_DAY_START_UTC_HOUR,
    SLATE_WINDOW_MS,
    loop_idle_interval_ms_from_env,
    window_status,
)
from .. import hedge as held_parlays
from .. import parlays
from ..parlays import (
    COMBO_EXIT_CENSUS_BOOKS_NO_YES_BID,
    COMBO_EXIT_CENSUS_BOOKS_READ,
    COMBO_EXIT_CENSUS_SERIES,
    COMBO_EXIT_CENSUS_SHARD_BOOKS_READ,
    COMBO_EXIT_CENSUS_SHARD_SERIES,
    COMBO_EXIT_SHARD_YES_BID_BOOKS,
    COMBO_EXIT_SHARD_YES_BID_DATE,
    COMBO_EXIT_SHARD_YES_BID_SIZE_CONTRACTS,
    scouting_facts,
)
from ..portfolio_poll import log_poll_attempt, store_positions_snapshot
from ..runner import book_quotes_for_event
from ..settlement import open_position_dollars
from ..slate import DRIFT_WINDOW_MS, book_distribution, kalshi_drift
from ..store import db
from ..store import combo_orders as combo_store
from ..store import manual_orders as manual_store
from ..store import orders as orders_store
from ..store.manual_orders import (
    COMBO_MAX_CONTRACTS,
    MANUAL_ORDER_MAX_CONTRACTS,
    MANUAL_ORDER_MAX_SPEND_TENTHS,
)
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
from .schemas import (
    ManualOrderRequest,
    OrderPlacementRequest,
)
# `_decode_books_used` is unused here and imported on purpose: it is the
# re-export `tests/test_ledger_consensus_provenance.py` reaches through this
# namespace. `_serialise` is both used below and pinned the same way by
# `tests/test_trust_surfaces.py`.
from .serialise import _decode_books_used, _is_prop_market, _serialise
from .routers import (
    estimates as estimates_router,
    hedge as hedge_router,
    ledger as ledger_router,
    odds as odds_router,
    parlays as parlays_router,
    scout as scout_router,
    status as status_router,
)
# `_signal_cache` and `_signal_payload` are unused here and imported on
# purpose: `tests/test_clv_signal.py` clears the cache and builds payloads
# through this namespace. The name must be bound to the router's own dict,
# never a fresh one -- a copy here would leave the test clearing nothing
# while the route served a stale report. See `routers/status.py`.
from .routers.status import _signal_cache, _signal_payload

logger = logging.getLogger(__name__)

#: Socket timeout for the combo lookup client. Longer than `LiveQuoteSource`'s
#: 5s because this path is two REST calls, the first of which asks Kalshi to
#: MINT a market -- a slow answer there is still an answer, and giving up on it
#: leaves a real market created with no `parlay_lookups` row naming it. Shorter
#: than `rest.DEFAULT_TIMEOUT_S` (30s) because a person is waiting with a thumb
#: on a button.
COMBO_LOOKUP_TIMEOUT_S = 15.0


def recorder_fields(last_ms, now_ms: int) -> dict:
    """`/api/health`'s `recorder` block, as a pure function.

    Module level and not a closure **because the empty case was otherwise
    untestable**. The first version of this lived inside `create_app` and its
    test went through the demo app, whose seeded database always has quotes --
    so the `None` branch never ran and the test passed with the branch
    deliberately broken. A guard that cannot be made to fail is decoration; see
    `tasks/lessons.md`.

    An empty table is "never written", which is `None` in BOTH fields. Not 0 --
    that is 1970, and it would render as an age of fifty-six years rather than
    as the absence of a measurement.
    """
    if last_ms is None:
        return {"last_write_ms": None, "age_ms": None}
    return {"last_write_ms": int(last_ms), "age_ms": max(0, now_ms - int(last_ms))}


def cap_display(dollars: Optional[float]) -> Optional[str]:
    """A derived cap as Joe reads it: cents below a dollar, dollars above.

    `format_price(256)` gives "25.6c" -- the deci-cent house rendering -- which
    is right for a per-bet cap on a $2.56 bankroll; the same function applied
    to a $10.24 exposure cap would print "1024c", so above a dollar this
    switches to the dollar string. Server-side because the frontend's contract
    (`lib/api.ts`) is that money display strings are rendered here, never
    re-derived from a float in a second place.

    `None` in, `None` out: an underivable cap is a refusal to state a number,
    and the caller renders the refusal words instead.
    """
    if dollars is None:
        return None
    tenths = int(round(dollars * 1000))
    if tenths < 1000:
        return format_price(tenths)
    return f"${tenths / 1000:.2f}"


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
    manual_order_config: Optional[ManualOrderConfig] = None,
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
    # The third of the family, and the only one whose two sides live in two
    # processes: this one's `day_start_hour` below and at :1546 is configured,
    # while `runner.py` and every other risk-day signature default to the
    # constant. The loop asserts the same thing at `scripts/run_loop.py`.
    assert_risk_day_start_agrees(
        default_day_start_hour=DEFAULT_DAY_START_UTC_HOUR, odds=odds,
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

    # One Kalshi REST client for the combo lookup path, built on the first tap
    # and shared after -- `LiveQuoteSource`'s pattern, for its reason. Building
    # one per request cost a `KalshiConfig.load()`, a PEM re-parse and a fresh
    # `httpx.AsyncClient` (~500ms, almost all SSL context setup) on every tap,
    # against the "one shared AsyncClient, not one per call" convention; the
    # discarded sockets are also a port-exhaustion risk under any repeat use.
    #
    # Lazy for the same reason the quote source is: `create_app` runs on the
    # demo deploy too, which holds no Kalshi credentials, and an eager build
    # would take the public demo down to support a route it does not expose.
    combo_clients: dict[str, tuple] = {}

    def combo_api():
        """The shared REST client for `/api/parlays/lookup`. Raises
        `ConfigError` on a keyless instance, which the route words as a 503."""
        if "api" not in combo_clients:
            config = KalshiConfig.load()
            http = httpx.AsyncClient(timeout=COMBO_LOOKUP_TIMEOUT_S)
            combo_clients["api"] = (KalshiRestClient(config, client=http), http)
        return combo_clients["api"][0]

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
        # Same reasoning for the combo lookup client. This one owns its httpx
        # client outright (it was handed in, so `KalshiRestClient.aclose` will
        # not close it), which is why the socket is closed here by name.
        held = combo_clients.pop("api", None)
        if held is not None:
            await held[1].aclose()

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

    @app.exception_handler(sqlite3.OperationalError)
    async def _sqlite_operational_error(
        request: Request, exc: sqlite3.OperationalError
    ) -> JSONResponse:
        """The read-budget abort becomes a 503; every other `OperationalError`
        is left alone.

        `store.db.connect`'s progress handler raises exactly this exception
        with the message "interrupted" when a statement outruns
        `api_read_budget_ms` -- see that module and
        `docs/adr/0135-an-abandoned-request-stops-executing.md`. Anything
        else with this type (a locked database, a malformed statement) is a
        real bug, not an abandoned-request defence, so it is re-raised to fall
        through to Starlette's normal 500 handling rather than being
        misreported as a budget hit.
        """
        if "interrupted" not in str(exc):
            raise exc
        logger.warning(
            "API read connection hit its %sms budget and was interrupted",
            app_config.api_read_budget_ms,
        )
        return JSONResponse(
            status_code=503,
            content={
                "error": "read_budget_exceeded",
                "budget_ms": app_config.api_read_budget_ms,
                "detail": (
                    "the query ran past the API read budget and was stopped "
                    "so the request could not pile up behind a proxy that had "
                    "already given up"
                ),
            },
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

        `statement_budget_ms` bounds this connection to `AppConfig.api_read_budget_ms`
        (default 25s, under Next's 30s rewrite-proxy timeout). Past it SQLite
        raises `sqlite3.OperationalError: interrupted`, which the app-level
        handler below turns into a 503 naming the cause -- see
        `store.db.connect` for why the budget is per-connection and
        `docs/adr/0135-an-abandoned-request-stops-executing.md` for the
        incident this closes.
        """
        conn = db.open_db(
            app_config.db_path,
            read_only=True,
            cross_thread=True,
            statement_budget_ms=app_config.api_read_budget_ms,
        )
        try:
            yield conn
        finally:
            conn.close()

    def _notification_health():
        """Delivery stats for `/api/health`, or `None` if they cannot be read.

        Opens its own short-lived read-only connection rather than taking the
        `get_conn` dependency, because `/api/health` deliberately has no
        database dependency at all -- it must answer while the volume is
        unmountable, which is precisely when someone is reading it.
        """
        try:
            conn = db.open_db(
                app_config.db_path, read_only=True, cross_thread=True
            )
            try:
                return Alerter(conn, None).delivery_health(now_ms=db.now_ms())
            finally:
                conn.close()
        except Exception:                                      # noqa: BLE001
            logger.warning("notification health unreadable", exc_info=True)
            return None

    def _recorder_health():
        """When the loop last wrote a quote, and how long ago. `None` if
        unreadable -- same containment as `_notification_health`, and for the
        same reason: this endpoint is the liveness probe, so it must not be
        able to 500 because a SELECT did."""
        try:
            conn = db.open_db(
                app_config.db_path, read_only=True, cross_thread=True
            )
            try:
                # **`ORDER BY id DESC LIMIT 1`, never `MAX(observed_ms)`.**
                # `id` is `INTEGER PRIMARY KEY AUTOINCREMENT`, i.e. the rowid,
                # so this stops after one row. Measured on a synthetic table of
                # 3,000,000 rows with this exact schema and index:
                #
                #     MAX(observed_ms)           323.7 ms
                #     ORDER BY id DESC LIMIT 1     0.116 ms
                #
                # **Measured, because the query plan says the opposite.**
                # `EXPLAIN QUERY PLAN` reports `SEARCH ... USING COVERING INDEX
                # idx_quotes_ticker_time` for the MAX and a bare `SCAN` for the
                # LIMIT form, which reads as the MAX being the optimised one.
                # It is not: `observed_ms` is the *second* column of that index
                # so the aggregate walks the whole covering index, linearly,
                # while the `SCAN` terminates on its first row. A plan is a
                # shape, not a cost.
                #
                # This shipped to live in a08c1a9 and took the instance down
                # inside four minutes. `/api/health` is hit by Fly's check, by
                # Next's proxy and by the loop's own probe; the table grows by
                # ~6,700 rows every pass, so the walk was already past the
                # probe's 2s timeout and uvicorn stopped answering on loopback.
                # The irony is exact: the field added so an external watchdog
                # could tell the box was dead is what killed it.
                #
                # **A keyed `meta` lookup, not the newest quote row (ADR
                # 0055).** "Newest row in `kalshi_quotes`" was exact while every
                # pass wrote ~6,000 of them. Under a change log it is not: a
                # slate where nothing moved writes no row, and so does a dead
                # recorder. The two need opposite responses and that query
                # returns the same answer for both.
                #
                # It is also cheaper than the thing it replaces, which matters
                # on this endpoint above all others -- see the incident above.
                # `ORDER BY id DESC LIMIT 1` was already O(1); a primary-key
                # lookup on a four-row table is no worse.
                last_ms = db.recorder_last_write_ms(conn)
            finally:
                conn.close()
        except Exception:                                      # noqa: BLE001
            logger.warning("recorder health unreadable", exc_info=True)
            return None
        return recorder_fields(last_ms, db.now_ms())

    # -- read routes -------------------------------------------------------

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "instance_mode": app_config.instance_mode,
            "live_trading_enabled": gate.live_trading_enabled,
            # Stated plainly so the demo cannot be mistaken for the real thing.
            "execution_available": not app_config.is_demo and gate.live_trading_enabled,
            # **The two money doors' switches, readable from outside.** Both
            # are compile-time constants with no env override -- deliberately,
            # so arming is a commit rather than something nudgeable at 2am --
            # which until now made "is it armed on live?" answerable only by
            # inferring it from a deployed sha. That is an inference about
            # what a commit contained, not an observation of the running
            # process, and `tasks/lessons.md` has a standing entry about
            # verification methods that report health without looking.
            #
            # Added 2026-09-08, when the bid path was disarmed on Joe's word
            # (ADR 0115) and the obvious next question -- "is it actually
            # disarmed on the box?" -- had no direct answer.
            #
            # `True` here means DRY: the row is recorded and nothing is sent.
            "order_paths_dry_run": {
                "manual_orders": manual_store.MANUAL_ORDERS_ARE_DRY_RUNS,
                "combo_bids": combo_store.COMBO_ORDERS_ARE_DRY_RUNS,
                "engine_orders": orders_store.ORDERS_ARE_DRY_RUNS,
            },
            # A boolean, never the credential. Setting a Fly secret from a
            # phone has no feedback of its own -- the loop logs `discord=on` at
            # startup and Fly's log tail has usually rolled past it by the time
            # anyone looks. Without this, "I set the secret" and "the secret is
            # in effect" are indistinguishable, and the failure is silence,
            # which is exactly what a working alerter also looks like on a quiet
            # night.
            "notifications_configured": DiscordConfig.from_env() is not None,
            # **What the line above cannot tell you.** It reports that a string
            # is non-empty. Revoke the webhook and `_post` logs a WARNING,
            # returns False, and that boolean stays `true` -- so a broken
            # alerter and a quiet slate read identically, which is the same
            # shape as the dead feed that makes the Board look calm.
            #
            # Not hypothetical. Queried on the live volume 2026-08-18: one
            # `failure` row in the whole record, `delivered = 0`. The loop died,
            # the alert was claimed, nothing reached the phone, and nothing said
            # so. `last_delivered_ms` is `null` when nothing has ever landed --
            # never 0, which is 1970 and would render as a delivery.
            #
            # Wrapped so it can never take health down with it: this is the
            # liveness probe `docker/entrypoint.sh` and the external heartbeat
            # both read, and a route that 500s because a SELECT failed would
            # turn a reporting gap into an outage. Unreadable resolves to
            # `None`, and the caller can tell that from a real answer.
            "notifications": _notification_health(),
            # **How long since the recording loop last wrote anything.** The
            # field an external watchdog needs and could not get.
            #
            # `entrypoint.sh` supervises uvicorn and the loop with `wait -n`, so
            # a loop that *exits* takes the container down and the outage is
            # visible from outside. A loop that is alive and **stuck** -- a
            # wedged socket, a blocked write -- keeps this endpoint green
            # forever while the record stops accumulating, and a stopped
            # recorder looks exactly like a quiet night. Freshness is the only
            # thing separating "running" from "running and doing its job".
            #
            # **`kalshi_quotes` is the right table for this and the wrong one
            # for the feed**, and the distinction cost a review round. It is
            # written ONLY by `runner.store_quotes_from_discovery`, at
            # `source = 'rest'`, on every pass -- `QuoteHub` writes nothing to
            # it. So its age is blind to the WebSocket (that is
            # `live_quotes_available`, above) and is exactly a measure of this
            # loop's own pulse, which is what something off-box wants.
            #
            # Ages, not just timestamps, because the consumer is a shell script
            # and clock arithmetic in bash is how an off-by-1000 ships.
            "recorder": _recorder_health(),
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
            # Which build is answering. Every sub-field is null when the
            # platform did not supply it -- never `"unknown"`, because two
            # machines both reporting `"unknown"` compare equal and that is the
            # exact wrong answer.
            #
            # This exists because the alternative is inference, and the
            # inference has been wrong twice in the direction that flatters:
            # proving commit `999857f` was absent from both deployed images
            # took 32 tool calls of behavioural HTML diffing, and the 52.00%
            # fee copy served live for three days after the correction landed
            # in git, while the record said "deployed and verified".
            #
            # `git_sha` is null unless the deploy passed
            # `-e GIT_SHA="$(git rev-parse HEAD)"`. Fly's own environment
            # carries no commit -- verified on a live machine, see
            # `config.BuildInfo` -- so `image_ref` is the field that pins the
            # deploy when the SHA is absent: its ULID is the `ImageRef` in
            # `fly releases --json`.
            #
            # Read per request, like `agent_fleet_configured` above and for the
            # same reason: the question is "is what I just deployed what is
            # running", which a value captured in `create_app` cannot answer.
            "build": BuildInfo.from_env().as_dict(),
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
          `slate.off_basis` counts the rows the second reading below put back
          outside the window, `slate.truncated` says `in_window` and `returned`
          differ, and `slate.older_than_window` counts the history that was
          deliberately left off. An empty table (`anchor_ms = null`) and a stale
          slate (`is_current = false`) are different states and read
          differently.

          That claim was false when it was written. `truncated` compared
          `in_window` against `len(rows)` — the rows *fetched*, before the
          `live_ages` re-decision below dropped any of them — so a row dropped
          there was counted in `in_window`, absent from every returned bucket,
          and set nothing. It vanished, and the page printed no sentence about
          it, which is the same defect as the truncation nobody was told about
          in a smaller frame. The comparison is now against `returned` and the
          drops are counted in their own field, because folding them into
          truncation would say `LIMIT` did something `LIMIT` did not do.

        - **`slate.actionable_total` is the finding this screen exists to
          report.** Windowing the selection was right and it cost the Board its
          only statement about the whole record: "Bettable now: 0" now reads as
          a quiet half-hour rather than as zero actionable across the life of
          the database, which is what it has been. It comes from
          `gate.population_counts` over `since_ms = 0` rather than a count
          written here, so the number on the Board and the number the gate
          admits evidence on cannot drift — they are one predicate.

        **Five buckets since 25C, not four.** The unsized, unrefused rows used
        to be one bucket, `no_edge`, captioned "no edge after fees" -- and
        every row the gate has ever counted actionable (51 rows, 15 games at
        the 2026-09-01 re-audit) sat in it, because the gate counts at the
        fixed $1,000 reference profile and quarter-Kelly at the observed
        balance sized each of them to zero. `sized_to_zero` is that
        population, split out on the same column the gate reads
        (`reference_contracts > 0`); `no_edge` keeps the rows with no bet at
        either bankroll. `population_counts` is not forked for it -- the
        Board buckets downstream of the row, and a test pins that the two
        counts agree on one fixture so they cannot drift apart silently.

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
                # `f.outcome_name` is the team (or Over/Under) the row's OWN
                # side pays on -- `runner.py` binds `fair_price_id` per side
                # -- and it is what `_serialise` emits as `side_outcome`. The
                # Board was the one slate surface without this join, so its
                # NO rows carried only `yes_side_team`: the opponent of the
                # side being priced. Ticket #6.
                "SELECT r.*, m.title AS market_title, m.yes_side_team, "
                "e.title AS event_title, e.commence_ms, l.league, "
                "f.outcome_name "
                "FROM recommendations r "
                "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
                "LEFT JOIN kalshi_events e ON e.event_ticker = m.event_ticker "
                "LEFT JOIN event_links l ON l.id = r.link_id "
                "LEFT JOIN fair_prices f ON f.id = r.fair_price_id "
                f"WHERE {_BASIS_SQL} >= ? "
                f"ORDER BY r.suggested_contracts DESC, {_BASIS_SQL} DESC, r.id DESC "
                "LIMIT ?",
                (since, limit),
            ).fetchall()

        surfaced, expired, suppressed, sized_to_zero, no_edge = [], [], [], [], []
        # Rows the SQL window admitted and `live_ages` put back outside it.
        # Counted rather than dropped on the floor: `in_window` is computed from
        # the SQL basis and therefore includes these, so without this number the
        # response asserts a window size it does not return the contents of.
        off_basis = 0
        for row in rows:
            item = _serialise(row, now_ms=now, staleness=staleness)
            # The window, decided by `live_ages` rather than by the SQL that
            # fetched the row. See the docstring: the two can only disagree
            # towards *older*, and older means off the slate.
            if since is not None and item["freshness_measured_from_ms"] < since:
                off_basis += 1
                continue
            # Which sport this game is, from the link's own record (the odds
            # feed's sport key, e.g. `baseball_mlb`). `None` on an unlinked
            # row, never a guess -- the screen shows nothing rather than a
            # league nothing recorded.
            item["league"] = row["league"]
            if row["suggested_contracts"] > 0:
                (surfaced if item["actionable"] else expired).append(item)
            elif row["suppressed_reason"]:
                suppressed.append(item)
            elif (row["reference_contracts"] or 0) > 0:
                # **Counted by the gate, unbuyable at the deposit** -- ticket
                # #25, Joe's 25C. Nothing refused this row and the strategy
                # had a bet at the fixed $1,000 reference profile
                # (`gate.POPULATIONS["actionable"]`, ADR 0015 §3); what is
                # zero is quarter-Kelly at the *observed* balance. Every row
                # the gate has ever counted actionable had this shape, and
                # until this branch existed the Board filed all of them under
                # `no_edge` -- captioned "no edge after fees" two inches
                # below a headline counting them. Suppression outranks
                # sizing (the `elif` above), and a row that sizes to one
                # contract after a top-up leaves this bucket by the first
                # branch on its own.
                #
                # `or 0`: a NULL `reference_contracts` is a pre-v6 row that
                # escaped the backfill, and the gate's own predicate puts a
                # NULL in `no_edge` rather than `actionable`. Same here, for
                # the same reason -- an unreadable size must not count as a
                # bet.
                sized_to_zero.append(item)
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
        # Newest first, like `no_edge` -- and deliberately NOT by
        # `reference_contracts` or `edge_tenths`. A per-row fact is
        # transparency; an ordering is a claim (ADR 0071 §2.5), and ranking
        # these by their reference size would rank them by the edge that
        # produced it.
        sized_to_zero.sort(key=lambda r: r["freshness_measured_from_ms"], reverse=True)
        no_edge.sort(key=lambda r: r["freshness_measured_from_ms"], reverse=True)
        returned = (
            len(surfaced)
            + len(expired)
            + len(suppressed)
            + len(sized_to_zero)
            + len(no_edge)
        )

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
            #
            # **`no_edge` now means what its caption says.** Since 25C the
            # rows the gate counts at its reference profile and the deposit
            # sizes to zero are in `sized_to_zero`, so a row here has
            # `reference_contracts` of 0 (or NULL) -- the strategy had no
            # bet at *any* bankroll it sizes for.
            "no_edge": no_edge if include_suppressed else [],
            # Same flag as `suppressed` and `no_edge`, same reason: it is the
            # rest of the slate. `suggested_contracts` is 0 on every row here
            # -- that is the bucket's definition -- so returning it offers
            # nothing to buy.
            "sized_to_zero": sized_to_zero if include_suppressed else [],
            "counts": {
                "surfaced": len(surfaced),
                "expired": len(expired),
                "suppressed": len(suppressed),
                "sized_to_zero": len(sized_to_zero),
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
                # Inside the window by the stored timestamp and outside it by
                # the age that was actually measured. Its own field, not folded
                # into `truncated`: `LIMIT` and the `live_ages` re-decision drop
                # rows for unrelated reasons and call for different sentences.
                "off_basis": off_basis,
                # Against `returned`, not `len(rows)`. See the docstring: the
                # old comparison let a row be counted in `in_window`, be absent
                # from every bucket, and set nothing.
                "truncated": in_window > returned,
                # The history deliberately left off. Stated rather than
                # implied: this is precisely the population the Board used to
                # rank by apparent edge and show as today.
                "recorded_total": recorded_total,
                # Rows in the whole table the strategy would have bet, on the
                # gate's own predicate. Zero for the project's life, which is
                # the finding — and it is not derivable from anything else in
                # this payload, all of which describes one slate.
                "actionable_total": population_counts(conn, 0)["actionable"],
                # The bankroll `reference_contracts` -- and therefore
                # `actionable_total` -- is sized at. Sent so the SIZED TO ZERO
                # caption can print the figure the gate actually uses rather
                # than a `$1,000` typed into the page, which would go on
                # reading as the reference on the day the constant moved.
                "reference_bankroll_dollars": REFERENCE_BANKROLL_DOLLARS,
                "older_than_window": max(0, recorded_total - in_window),
            },
            # An empty Board is the expected state most of the time. Saying so
            # here stops it reading as a malfunction.
            "note": (
                "Most candidates have no edge. An empty board is the normal "
                "result, not a failure."
            ),
        }

    @app.get("/api/slate")
    def slate(
        conn=Depends(get_conn),
        limit: int = Query(100, le=500),
        league: Optional[str] = Query(
            None,
            description=(
                "Cut to one league, by the odds feed's sport key "
                "(`baseball_mlb`). An unknown key is a 422, never ignored."
            ),
        ),
        within_hours: Optional[int] = Query(
            None,
            ge=1,
            le=MAX_WITHIN_HOURS,
            description=(
                "Cut to games kicking off between now and this many hours "
                "out, on the sportsbook's clock. A row with no known kickoff "
                "is left out: it cannot say it starts within the window."
            ),
        ),
    ) -> dict:
        """The whole slate, with the factors the record already holds.

        **Edge is a column here, not a gate.** `/api/board` splits the slate on
        whether a row cleared the fee against a devigged sharp consensus, and
        that has been "no" on every row this instance has written. ADR 0021
        records the refutation; its §7.2 records the most plausible reason,
        which is that the comparison is anchored on `runner.SHARP_BOOKS` and is
        therefore Kalshi against the only references plausibly as sharp as
        Kalshi. A screen showing only that comparison's verdict cannot show
        that.

        So this returns **one flat list, ordered by kickoff**, with every row
        carrying the same factors and no bucketing by verdict. The suppression
        reason travels with each row; it is information about the row rather
        than a reason to hide it.

        Four groups of factors, all of them **already stored and never
        rendered** -- see `backend/slate.py` for what each does not establish:

        - `books`: Kalshi's ask placed among per-book devigged fair values, with
          **no sharp anchoring**, so a reader can see where the anchored
          consensus sits inside the full distribution.
        - `kalshi_drift_tenths`: how the price you would pay has moved over the
          last hour, off `kalshi_quotes`' own history.
        - `market_width` / `book_count` / `anchored_on_sharp`: joined from
          `fair_prices`, which only `/api/ledger` has ever selected.
        - `volume_24h` / `open_interest` / `depth_at_ask`: capacity, which
          `sharp-bettor` calls the binding constraint on a winning bettor and
          which no screen in this product has ever shown.

        **Nothing here is an edge and nothing here is scored.** No factor below
        has been tested against an outcome, none of them enters
        `suggested_contracts`, and this endpoint computes no composite of them.
        `POST /api/orders` re-derives sizing, staleness and risk server-side and
        does not read this route. The honest reading of this screen is *"here is
        everything the record knows about tonight"*, not *"here is what to
        bet"*.

        Selection reuses the Board's window and its two-stage basis check
        verbatim, so the two screens describe the same slate. A row this
        endpoint shows and the Board does not would be a second definition of
        "tonight".
        """
        now = db.now_ms()
        # The two list cuts (ticket #15, Joe's option A): league and kickoff
        # window, parsed once for both this route and `/api/parlays` so the
        # two lists cannot accept different vocabularies. `None` when neither
        # parameter is set, and in that case NOTHING below changes -- the
        # unfiltered payload is byte-identical to the one this route served
        # before the parameters existed, and `tests/test_list_filters.py`
        # pins that. An unknown value is a 422, never a silently whole list
        # under a heading that says it was cut.
        try:
            list_filter = parse_list_filter(league, within_hours, now_ms=now)
        except FilterRefused as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        # The cut as SQL, applied BEFORE `LIMIT` so a league that the
        # unfiltered list's `suggested_contracts DESC, LIMIT 100` would have
        # dropped is reachable through the filter -- the whole point of a cut
        # is to reach rows the full list could not fit. Both predicates go
        # through the row's linked odds fixture: the league is
        # `odds_snapshots.sport_key` (the ladder's own column, and the one
        # vocabulary `leagueLabel` renders -- `event_links.league` holds
        # Kalshi's "Pro Baseball" and is not what the parameter names), and
        # the kickoff is `MIN(commence_ms)` per fixture, the same definition
        # the `kickoffs` read below and the sort key use, so a row is never
        # cut on a different clock from the one it prints. Both are indexed
        # SEARCHes on `odds_event_id`, one per row in the window -- not the
        # derived table over every fixture this query was cured of.
        filter_sql, filter_params = _slate_filter_sql(list_filter)
        anchor_row = conn.execute(
            f"SELECT MAX({_BASIS_SQL}) AS anchor_ms, COUNT(*) AS total "
            "FROM recommendations r"
        ).fetchone()
        anchor = None if anchor_row["anchor_ms"] is None else int(anchor_row["anchor_ms"])
        recorded_total = int(anchor_row["total"] or 0)
        since = None if anchor is None else anchor - SLATE_WINDOW_MS

        rows, in_window = [], 0
        # The window's whole population, before any cut. `in_window` below
        # is the cut population when a filter is set (so `truncated` compares
        # like with like), and this is what `older_than_window` and the
        # filter's `hidden` count are measured against.
        in_window_all = 0
        if since is not None:
            in_window_all = int(
                conn.execute(
                    f"SELECT COUNT(*) AS n FROM recommendations r "
                    f"WHERE {_BASIS_SQL} >= ?",
                    (since,),
                ).fetchone()["n"]
            )
            in_window = in_window_all
            if list_filter is not None:
                in_window = int(
                    conn.execute(
                        f"SELECT COUNT(*) AS n FROM recommendations r "
                        "LEFT JOIN event_links l ON l.id = r.link_id "
                        f"WHERE {_BASIS_SQL} >= ?{filter_sql}",
                        (since, *filter_params),
                    ).fetchone()["n"]
                )
            rows = conn.execute(
                # **The kickoff is the sportsbook's clock, never Kalshi's.**
                # Until 2026-08-29 this selected `e.commence_ms`, which stores
                # `occurrence_datetime` raw -- about three hours late on game
                # series (ADR 0006). Every row on this screen printed a 19:05
                # first pitch as 22:05, while `/api/market/{ticker}` one tap
                # away printed it correctly off the linked fixture, so the
                # product disagreed with itself on the one field that answers
                # "do I still have time to act". Ticket #26.
                #
                # The join is the same one `/api/market/{ticker}`,
                # `/api/ledger` and `_resolve_scout_fixture` already take, and
                # `MIN` per fixture is the scorer's own definition
                # (`backend/scoring.py:markets_awaiting_scoring`) -- so the
                # list, the detail screen and the clv machinery agree on when a
                # game started. Not `OBSERVED_KALSHI_COMMENCE_OFFSET_MS`: the
                # offset was 14 of 18 MLB pairs, so four fixtures in that
                # measurement would have been corrected to the wrong minute,
                # and a hardcoded shift becomes a silent lie the day Kalshi
                # fixes the field.
                #
                # LEFT JOINed, so an unlinked row resolves to `None` and the
                # column renders as `--:--` rather than a confident wrong time.
                # The sort below reads this same value, so the printed order
                # and the printed times cannot disagree.
                #
                # **The kickoff is NOT joined here any more, and that is a
                # measured change rather than a tidy-up.** This query used to
                # carry a derived table aggregating `odds_snapshots` for every
                # linked fixture, and it was restricted to linked fixtures
                # precisely because grouping the whole history was worse. Both
                # are unbounded by what the screen shows: on a live-shaped
                # database (55,777 recommendations, 199,500 snapshots) the
                # derived table alone measured **77.3ms of an 85.4ms query**,
                # and it cost that on `limit=1` exactly as on `limit=100`.
                #
                # The kickoff for the rows actually returned is read after
                # this, in ONE bounded query -- the same "one read per fixture,
                # not per row" shape `book_quotes_for_event` and
                # `scouting_facts` already use here. Same value, same source,
                # same `MIN` per fixture; what changes is that the work is now
                # proportional to the slate rather than to the record.
                "SELECT r.*, m.title AS market_title, m.yes_side_team, "
                "       m.volume_24h, m.open_interest, "
                "       m.market_type, m.player_name, "
                "       e.title AS event_title, "
                "       f.p_multiplicative, f.p_additive, f.p_power, f.p_shin, "
                "       f.p_conservative, "
                "       f.market_width, f.book_count, f.books_used, "
                "       f.anchored_on_sharp, f.outcome_name, "
                "       l.odds_event_id, l.league "
                "FROM recommendations r "
                "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
                "LEFT JOIN kalshi_events e ON e.event_ticker = m.event_ticker "
                "LEFT JOIN fair_prices f ON f.id = r.fair_price_id "
                "LEFT JOIN event_links l ON l.id = r.link_id "
                f"WHERE {_BASIS_SQL} >= ?{filter_sql} "
                f"ORDER BY r.suggested_contracts DESC, {_BASIS_SQL} DESC, r.id DESC "
                "LIMIT ?",
                (since, *filter_params, limit),
            ).fetchall()

        # One `book_quotes_for_event` read per fixture, not per row. A slate has
        # roughly two rows per fixture (both sides of a moneyline), so caching
        # halves the reads -- and, more importantly, guarantees both sides of a
        # game are placed against the *same* stored sweep. Reading twice could
        # straddle a sweep boundary and put two rows of one game against two
        # different book sets, which would look like disagreement between the
        # sides rather than between the reads.
        book_cache: dict[str, object] = {}
        # **One scout read for the whole slate, before the loop.** The scout
        # state feeds the sweet spot's last check, and the join is through the
        # fixture rather than the row's own ticker (`parlays.scouting_facts`
        # owns that reasoning). Read per row it would be a hundred queries on
        # the path `/api/slate` was separately cured of; read here it is one.
        #
        # Empty on an empty slate, and `scouting_facts` returns a key for every
        # ticker asked about -- so a missing entry below cannot mean "we forgot
        # to ask", only "there is no such row".
        # **Every returned row's kickoff, in one query bounded by the slate.**
        # Replaces a derived table that aggregated `odds_snapshots` for every
        # linked fixture on every request -- 77.3ms of an 85.4ms query on a
        # live-shaped database, and the same cost at `limit=1` as at
        # `limit=100`.
        #
        # `MIN(commence_ms)` per fixture is unchanged, and it is deliberately
        # the same definition `/api/market/{ticker}`, `/api/ledger` and
        # `backend/scoring.py:markets_awaiting_scoring` take -- the whole point
        # of ticket #26 was that the list and the detail screen must not
        # disagree about when a game starts. Moving the read must not move the
        # number, and `tests/test_slate_kickoff_matches_detail.py` is what says
        # it did not.
        #
        # The sportsbook's clock, never `kalshi_events.commence_ms`, which
        # stores `occurrence_datetime` raw -- about three hours late on game
        # series (ADR 0006).
        fixture_ids = sorted(
            {row["odds_event_id"] for row in rows if row["odds_event_id"]}
        )
        kickoffs: dict[str, int] = {}
        if fixture_ids:
            marks = ",".join("?" * len(fixture_ids))
            kickoffs = {
                r["odds_event_id"]: r["commence_ms"]
                for r in conn.execute(
                    f"SELECT odds_event_id, MIN(commence_ms) AS commence_ms "
                    f"FROM odds_snapshots WHERE odds_event_id IN ({marks}) "
                    f"GROUP BY odds_event_id",
                    fixture_ids,
                ).fetchall()
            }

        scouting = scouting_facts(
            conn, [row["ticker"] for row in rows], now_ms=now
        )
        # Built from the configs that already enforce these limits, so the
        # slate refuses on the same numbers the parlay card and the engine do.
        # `thresholds` is the SuppressionConfig; `staleness` the clocks.
        slate_trust = TrustThresholds.from_configs(staleness, thresholds)
        items, off_basis, with_books = [], 0, 0
        # Grouping key for the picks block below: the odds fixture, which the
        # serialised item deliberately does not carry. Falls back to the event
        # title so an unlinked row still groups with its own game rather than
        # forming a phantom one per row. The third element is whether the row
        # is a player prop, read from `kalshi_markets` here because the
        # serialised item deliberately carries neither `market_type` nor
        # `player_name` (ticket #7) and the picks block must not learn it from
        # the ticker string.
        picks_source: list[tuple[str, dict, bool]] = []
        for row in rows:
            item = _serialise(
                row,
                now_ms=now,
                staleness=staleness,
                trust_thresholds=slate_trust,
                scout=scouting.get(row["ticker"]),
            )
            if since is not None and item["freshness_measured_from_ms"] < since:
                off_basis += 1
                continue
            picks_source.append(
                (
                    row["odds_event_id"] or item["event_title"] or item["ticker"],
                    item,
                    _is_prop_market(row),
                )
            )

            # Same fact and same refusal as the Board's: the link's sport key,
            # `None` on an unlinked row.
            # `None` on an unlinked row, exactly as the LEFT JOIN resolved
            # it -- the column renders as `--:--` rather than a confident wrong
            # time, and the sort below puts unknown kickoffs last.
            item["commence_ms"] = kickoffs.get(row["odds_event_id"])
            item["league"] = row["league"]
            item["volume_24h"] = row["volume_24h"]
            item["open_interest"] = row["open_interest"]
            item["kalshi_drift_tenths"] = kalshi_drift(
                conn, row["ticker"], row["side"], now_ms=now
            )
            # **Break-even at this price, and deliberately nothing beside it**
            # (fleet convening item 6). `edge_tenths` is exactly
            # `1000 x (fair_probability - breakeven)`, so rendering fair next
            # to this number would hand the reader the measured-negative edge
            # by subtraction to the last decimal -- the identity the convening
            # adjudicated. Taker at one contract, because that is the trade
            # Joe actually makes by hand; the taker fee makes the rate
            # size-independent anyway (see `breakeven_win_rate`'s table).
            # `None` when the ask is not a tradeable price -- the function
            # refuses 0 and 1000 rather than pricing a settled outcome, and
            # this route passes the refusal through rather than guessing.
            try:
                item["breakeven_win_rate"] = breakeven_win_rate(
                    row["entry_ask_tenths"], 1
                )
            except (ValueError, TypeError):
                item["breakeven_win_rate"] = None
            item["books"] = None

            odds_event_id = row["odds_event_id"]
            outcome_name = row["outcome_name"]
            ask = row["entry_ask_tenths"]
            if odds_event_id and outcome_name and ask is not None:
                if odds_event_id not in book_cache:
                    book_cache[odds_event_id] = book_quotes_for_event(
                        conn, odds_event_id, now=now
                    )
                books = book_cache[odds_event_id]
                if books is not None:
                    dist = book_distribution(
                        outcomes=books.outcomes,
                        quotes_by_book=books.quotes_by_book,
                        outcome_name=outcome_name,
                        kalshi_ask_tenths=ask,
                        already_dropped=len(books.books_dropped),
                    )
                    if dist is not None:
                        item["books"] = dist.as_dict()
                        with_books += 1
            items.append(item)

        # Kickoff order, because the decision this screen serves is "what is
        # about to start and what do I know about it". The Board orders by
        # size then freshness, which is the right order for "what can I bet
        # right now" and the wrong one for reading a slate end to end.
        #
        # `commence_ms` is nullable, so unknown kickoffs sort last rather than
        # first: a row with no kickoff is the least decidable thing here and
        # putting it at the top would give it the most attention.
        #
        # **This is the same value the row prints**, which is the whole reason
        # the fix above had to be in the SELECT rather than at render time: a
        # display corrected in the frontend while this sorted the raw Kalshi
        # field would order rows against their own printed times. The offset is
        # not a constant shift either -- 4 of the 18 MLB pairs measured for
        # `OBSERVED_KALSHI_COMMENCE_OFFSET_MS` did not carry it -- so an
        # uncorrected sort genuinely reorders a mixed slate rather than merely
        # translating it.
        # **The third key is the TICKER and may not be `edge_tenths`.** It was
        # `-(edge_tenths or 0)` until 2026-09-01, and that is the one ordering
        # the decision map rules out of scope: `beta = -0.141` means ranking by
        # the Kalshi-vs-consensus gap puts the least trustworthy rows first.
        #
        # It was not a rare tiebreak. Both sides of a moneyline carry a
        # byte-identical `commence_ms`, so this key decided which side of EVERY
        # game printed first -- and the side printed first was the
        # higher-apparent-edge one. The row renders neither `side` nor
        # `event_title`, so a reader could not see which side they were being
        # shown, let alone that it had been chosen for them on that quantity.
        #
        # The "it is only a tiebreak inside a pair, not a ranking of the
        # screen" reading was available and is refused: a key that orders every
        # pair orders half the comparisons anyone makes on this screen.
        #
        # `ticker` is deterministic, unique per row, and carries no claim --
        # which is the whole requirement. A stable order matters here because
        # an unstable one makes two reads of the same slate disagree.
        items.sort(
            key=lambda r: (
                r["commence_ms"] is None,
                r["commence_ms"] or 0,
                r["ticker"],
            )
        )

        # **Who's likely to win tonight** (ADR 0067). One entry per game: the
        # side the devigged consensus makes the favorite, ranked by
        # `fair_probability` alone -- one stored, unscored column, which is why
        # this is a sort and not the composite `backend/slate.py` forbids.
        # YES-side rows only: on a NO row `team` names the *yes* side (the
        # opponent of the pick), and a picks list that renames sides inside a
        # route is the kind of derivation that goes wrong silently. Freshest
        # row per ticker, then the max-fair fresh side per game; a game whose
        # consensus is stale, or whose favorite side carries no fresh YES row,
        # is counted out by name rather than dropped -- "no pick" and "no
        # measurement" are different facts.
        #
        # **No breakeven, edge, or size key may appear in this block.** Fair%
        # beside break-even hands the reader the measured-negative edge by
        # subtraction to the last decimal (the fleet-convening identity), so
        # the two never share a block; `tests/test_slate_picks.py` walks the
        # keys and pins it.
        #
        # **A player prop never ranks here** (ticket #23, the bug half). A
        # prop event inherits its game's `odds_event_id`, so without this a
        # `KXMLBHIT` 1+ hit row at 0.68 outranks the game's own moneyline
        # favorite at 0.53 and is printed as the game's likely winner under
        # the player's name -- `team` on a prop holds "<player>: 1+" (#7).
        # Replayed over the stored record that happened at 131 of 192
        # anchor instants in the prop era, in 16 of the 17 games that held
        # both. Excluded here, server-side, where a client filter cannot
        # reach; counted by distinct market rather than dropped, on the
        # same principle as `favorite_unpriced`. The game itself still
        # ranks off its team rows.
        freshest_yes: dict[str, tuple[str, dict]] = {}
        all_games: set[str] = set()
        prop_markets_excluded: set[str] = set()
        for game_key, item, is_prop in picks_source:
            all_games.add(game_key)
            if is_prop:
                prop_markets_excluded.add(item["ticker"])
                continue
            if item["side"] != "yes" or item["fair_probability"] is None:
                continue
            held = freshest_yes.get(item["ticker"])
            if (
                held is None
                or item["freshness_measured_from_ms"]
                > held[1]["freshness_measured_from_ms"]
            ):
                freshest_yes[item["ticker"]] = (game_key, item)
        by_game: dict[str, list[dict]] = {}
        for game_key, item in freshest_yes.values():
            by_game.setdefault(game_key, []).append(item)
        max_odds_age_ms = staleness.max_odds_age_s * 1000
        ranked, stale_games = [], 0
        # A game whose rows are all NO-side (or carry no fair value) has no
        # candidate for "which team wins" in the team's own denomination --
        # counted, never silently dropped.
        favorite_unpriced = len(all_games - set(by_game.keys()))
        for candidates in by_game.values():
            fresh = [
                c for c in candidates
                if c["odds_age_now_ms"] is not None
                and c["odds_age_now_ms"] <= max_odds_age_ms
            ]
            if not fresh:
                stale_games += 1
                continue
            best = max(fresh, key=lambda c: c["fair_probability"])
            if best["fair_probability"] < 0.5:
                # The favorite is the *other* team, and no fresh YES row
                # prices it -- ranking the underdog as "likely to win" would
                # be a lie of arithmetic.
                favorite_unpriced += 1
                continue
            ranked.append(
                (
                    best["fair_probability"],
                    {
                        "ticker": best["ticker"],
                        "event_title": best["event_title"],
                        "team": best["team"],
                        # Which sport, so two "Sparks vs Aces"-shaped names
                        # never leave the reader guessing the league. Not an
                        # edge-shaped key; `test_slate_picks` walks the rest.
                        "league": best["league"],
                        "side": best["side"],
                        "commence_ms": best["commence_ms"],
                        "fair_percent_display": best["fair_percent_display"],
                        # The ask is only served while it is a current price;
                        # an hours-old ask beside a live chance reads as a
                        # quote.
                        "ask_display": (
                            best["ask_display"]
                            if best["price_is_current"]
                            else None
                        ),
                        "anchored_on_sharp": best["anchored_on_sharp"],
                    },
                )
            )
        ranked.sort(key=lambda pair: -pair[0])
        picks = {
            "ranked": [pick for _, pick in ranked],
            "not_ranked": {
                "stale_consensus": stale_games,
                "favorite_unpriced": favorite_unpriced,
                # Distinct player-prop MARKETS in the window, not games: a
                # prop's game is still counted above, under whichever of the
                # two game counts its team rows earn it.
                "props_excluded": len(prop_markets_excluded),
            },
            "note": (
                "Chance to win, by the books' consensus — not an edge. The "
                "price already charges for the chance: a 70% favorite costs "
                "about 70 cents, so a likely winner is not a profitable bet."
            ),
        }

        # **Cash and open positions, separately, never summed** (fleet
        # convening item 5, permitted by the calibration registration's A7:
        # a live balance display reads the venue's own record, not the
        # estimate log, so the embargo does not touch it). The snapshot is
        # the operational clock's -- the analysis clock still reads one row
        # per day, exactly as A7 separates them. The caps are the deployed
        # ones Joe's own balance derives (ADR 0045); the $100 study ceiling
        # is deliberately NOT here, because "cash against $100" reads as
        # budget remaining to a reader holding $8. No field on this payload
        # sums the two numbers or signs a P&L.
        snapshot = conn.execute(
            "SELECT observed_ms, balance_tenths, portfolio_value_tenths "
            "FROM venue_balance_snapshots ORDER BY observed_ms DESC LIMIT 1"
        ).fetchone()
        # The caps, derived AT REQUEST TIME from the venue's observed balance
        # -- the exact pattern the order endpoint uses at its step 8a and
        # /api/gate uses for `bankroll_dollars`. The module-level `risk` off
        # `create_app` is underived by construction (every dollar cap on it
        # is None since ADR 0045), so it must never feed this payload
        # directly: it did until 2026-08-22, and "your daily-loss line is
        # $X" had silently rendered nothing on live the whole time.
        balance_tenths = (
            None if snapshot is None else snapshot["balance_tenths"]
        )
        derived_risk = (
            risk.with_observed_balance(db.latest_balance_tenths(conn))
            if risk.underived
            else risk
        )
        if not risk.underived:
            # A directly-injected config (tests, tools) carries explicit
            # dollars with no balance behind them; say so rather than
            # inventing an observation.
            caps_basis = {
                "balance_display": None,
                "observed_ms": None,
                "refusal": "caps injected by configuration; no observed balance",
            }
        elif balance_tenths is not None:
            caps_basis = {
                "balance_display": f"${balance_tenths / 1000:.2f}",
                "observed_ms": snapshot["observed_ms"],
                "refusal": None,
            }
        else:
            # Never omitted silently: the screen renders these words rather
            # than rendering nothing, which is the defect this block fixes.
            caps_basis = {
                "balance_display": None,
                "observed_ms": None,
                "refusal": "balance unobserved",
            }
        money = {
            "observed_ms": None if snapshot is None else snapshot["observed_ms"],
            "cash_tenths": balance_tenths,
            "cash_display": (
                None
                if balance_tenths is None
                else f"${balance_tenths / 1000:.2f}"
            ),
            "open_positions_tenths": (
                None if snapshot is None else snapshot["portfolio_value_tenths"]
            ),
            # Kept as a float for a deployed frontend one version behind;
            # the display strings beside it are what the screen renders now.
            "daily_line_dollars": (
                None if derived_risk is None
                else derived_risk.max_daily_loss_dollars
            ),
            "daily_line_display": cap_display(
                None if derived_risk is None
                else derived_risk.max_daily_loss_dollars
            ),
            "per_bet_cap_display": cap_display(
                None if derived_risk is None
                else derived_risk.max_position_dollars
            ),
            "exposure_cap_display": cap_display(
                None if derived_risk is None
                else derived_risk.max_exposure_dollars
            ),
            # The deposit arithmetic, server-side: one contract at 50c costs
            # $0.50 and the per-bet cap is POSITION_FRACTION_OF_BANKROLL of
            # the balance, so the balance that admits one such contract is
            # 0.50 / fraction. True whatever the balance is -- it is the
            # sentence that tells Joe what a deposit would buy, so it is
            # served even while the balance is unobserved.
            "deposit_for_50c_display": (
                f"${0.50 / POSITION_FRACTION_OF_BANKROLL:.2f}"
            ),
            "caps_basis": caps_basis,
        }

        # **Tonight's commitment, a SIBLING of `money`, never inside it**
        # (2026-08-21 partner ruling, docs/reviews/2026-08-21-items-2-3-
        # ruling.md): `money`'s contract is about never summing cash and
        # positions; this is a different kind of number -- unsigned count
        # and stake from the fills mirror since the day roll, null (never 0)
        # when the mirror is stale. The lockout release rides here for the
        # reason the study payload gave: the strip that renders tonight is
        # the strip that renders the lockout -- one fetch, one state.
        now = db.now_ms()
        tonight = bets_module.tonight_activity(
            conn, now_ms=now, day_start_hour=odds.budget_day_start_utc_hour
        )
        tonight["lockout_until_ms"] = bet_estimates.lockout_until(
            conn, now_ms=now
        )

        payload = {
            "rows": items,
            "picks": picks,
            "money": money,
            "tonight": tonight,
            # What is open at the venue right now -- a SIBLING of `money`
            # for `tonight`'s reason: `money`'s contract is about never
            # summing cash and positions, and this block's own contract
            # (counted-not-parsed, unit-unpinned value, two staleness
            # clocks) lives in `bets.open_positions`'s docstring.
            "open_positions": bets_module.open_positions(conn, now_ms=now),
            "counts": {
                "returned": len(items),
                # Rows for which a book distribution could actually be
                # computed. Its own number because "no book disagreed with
                # Kalshi" and "no book price was stored" render identically on
                # a screen and are completely different facts -- the repo's
                # recurring *zero that means "no measurement"*.
                "with_book_distribution": with_books,
                "surfaced": sum(
                    1 for r in items
                    if r["suggested_contracts"] > 0 and r["actionable"]
                ),
            },
            "staleness": {
                "max_kalshi_quote_age_s": staleness.max_kalshi_quote_age_s,
                "max_odds_age_s": staleness.max_odds_age_s,
            },
            "slate": {
                "anchor_ms": anchor,
                "age_ms": None if anchor is None else max(0, now - anchor),
                "since_ms": since,
                "window_ms": SLATE_WINDOW_MS,
                "is_current": anchor is not None and now - anchor <= SLATE_WINDOW_MS,
                "in_window": in_window,
                "returned": len(items),
                "off_basis": off_basis,
                "truncated": in_window > len(items),
                "recorded_total": recorded_total,
                "actionable_total": population_counts(conn, 0)["actionable"],
                "older_than_window": max(0, recorded_total - in_window_all),
            },
            "drift_window_ms": DRIFT_WINDOW_MS,
            # Read by the screen and printed there. It is the sentence that
            # stops every column on this page being read as a signal.
            "note": (
                "None of these factors has been scored against an outcome. "
                "They are recorded so they can be, and combined into nothing."
            ),
        }
        # The cut, echoed, ONLY when one was applied: the key is absent
        # rather than `null` on the unfiltered read so that payload stays
        # byte-identical to the pre-#15 one. `hidden` is the window's rows
        # the cut removed, so a short list under a filter reads as cut
        # rather than as a quiet night.
        if list_filter is not None:
            payload["filter"] = list_filter.as_dict(
                hidden=max(0, in_window_all - in_window)
            )
        return payload

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
            desk_window=odds.desk_window_utc,
            # Threaded for the same reason `desk_window` is: the loop applies
            # the attention slice after `desk_wants`, so without this the panel
            # would publish a call the loop refuses. Ticket #35.
            attention_daily_credits=odds.attention_daily_credits,
            # The loop's own idle cadence, read from the environment the
            # entrypoint started it from. The screen judges a silence in
            # `last_look_ms` against this rather than against a constant
            # written for the fast cadence -- which called a sleeping loop
            # a fault on 8 of 26 measured cold opens and switched off the
            # self-heal on exactly the opens it exists for.
            loop_idle_interval_ms=loop_idle_interval_ms_from_env(),
        ).to_dict()

    @app.get("/api/market/{ticker}")
    def market(ticker: str, conn=Depends(get_conn)) -> dict:
        # The clock is the linked odds fixture's, never `kalshi_events` --
        # that column is `occurrence_datetime` raw, ~3h late on game series
        # (ADR 0006). `/api/ledger` was moved off it on 2026-08-21 and this
        # route follows: a "starts at" line computed from the Kalshi field
        # would be wrong by the length of the game's first half.
        # `f.*` joined since ADR 0068: the Consensus panel renders the four
        # devig readings, the anchored book set and the width on this screen,
        # and `_serialise`'s key-presence rule fills `methods`/`consensus`
        # once the columns are simply selected.
        row = conn.execute(
            "SELECT r.*, m.title AS market_title, m.yes_side_team, m.volume_24h, "
            "m.open_interest, m.close_ms, m.status AS market_status, "
            "e.title AS event_title, "
            "f.p_multiplicative, f.p_additive, f.p_power, f.p_shin, "
            "f.p_conservative, f.market_width, f.book_count, f.books_used, "
            # The sum of the books' RAW implied probabilities, before
            # the vig is removed. Stored since the beginning and served
            # by nothing -- and it is the one number that makes the
            # bookmaker's cut visible to a beginner: 104.8% quoted means
            # 4.8 points of margin, which is what devigging removes.
            "f.overround, "
            "f.anchored_on_sharp, f.outcome_name, "
            "l.odds_event_id "
            "FROM recommendations r "
            "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
            "LEFT JOIN kalshi_events e ON e.event_ticker = m.event_ticker "
            "LEFT JOIN fair_prices f ON f.id = r.fair_price_id "
            "LEFT JOIN event_links l ON l.id = r.link_id "
            "WHERE r.ticker = ? ORDER BY r.created_ms DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"No data for {ticker}")

        # **The fixture, read for THIS row only.** This was a derived table
        # grouping `odds_snapshots` with no `WHERE` at all -- the whole
        # snapshot history aggregated to answer a question about one market.
        # The slate's version was at least restricted to linked fixtures and
        # still measured 77.3ms of an 85.4ms query on a live-shaped database;
        # this one had no restriction.
        #
        # `MIN(commence_ms)` with bare columns beside it is unchanged, and the
        # bare-column rule is the point: with a lone `MIN()` aggregate SQLite
        # takes the bare columns from the row that achieved the minimum. Same
        # value, same definition as the slate, `/api/ledger` and the scorer --
        # ticket #26 exists because those must not disagree.
        fixture = None
        if row["odds_event_id"]:
            fixture = conn.execute(
                "SELECT MIN(commence_ms) AS commence_ms, home_team, away_team, "
                "       sport_key "
                "FROM odds_snapshots WHERE odds_event_id = ?",
                (row["odds_event_id"],),
            ).fetchone()
            # An `odds_event_id` with no snapshots aggregates to a row of
            # NULLs rather than to no row, so the emptiness has to be read off
            # the value: `None` here means unlinked or unrecorded, and the
            # screen says so rather than printing a confident wrong time.
            if fixture is not None and fixture["commence_ms"] is None:
                fixture = None

        # `now_ms`/`staleness` make the ages live rather than frozen at write
        # time: without them a 6pm quote still reads "30s ago" at 11pm, on the
        # one screen with no list of fresher rows beside it to give the lie.
        now = db.now_ms()
        # The sweet spot on this screen too (ADR 0090's open item; Joe chose
        # all three surfaces). One ticker, so `scouting_facts` is one query
        # with a single-element IN clause -- the same fixture join the ladder
        # takes, rather than a second way of asking whether this game has been
        # scouted.
        detail = _serialise(
            row,
            now_ms=now,
            staleness=staleness,
            trust_thresholds=TrustThresholds.from_configs(
                staleness, thresholds
            ),
            scout=scouting_facts(conn, [ticker], now_ms=now).get(ticker),
        )
        detail["volume_24h"] = row["volume_24h"]
        detail["open_interest"] = row["open_interest"]
        detail["close_ms"] = row["close_ms"]
        detail["market_status"] = row["market_status"]
        detail["commence_ms"] = fixture["commence_ms"] if fixture else None
        detail["home_team"] = fixture["home_team"] if fixture else None
        detail["away_team"] = fixture["away_team"] if fixture else None
        detail["league"] = fixture["sport_key"] if fixture else None
        # The books' raw implied probabilities summed, before devigging. A
        # fair coin market quoted with no margin sums to 1.0; anything above
        # is the bookmaker's cut, and that difference is precisely what the
        # four devig methods remove. `None` when the row predates the column
        # or the devig could not report it -- never 1.0, which would assert a
        # margin-free book.
        detail["overround"] = row["overround"]

        # The full book distribution, exactly as the slate computes it --
        # same helpers, same refusals (`None` when nothing usable is stored,
        # never an empty shape pretending a measurement happened).
        detail["books"] = None
        odds_event_id = row["odds_event_id"]
        outcome_name = row["outcome_name"]
        ask = row["entry_ask_tenths"]
        if odds_event_id and outcome_name and ask is not None:
            quotes = book_quotes_for_event(conn, odds_event_id, now=now)
            if quotes is not None:
                dist = book_distribution(
                    outcomes=quotes.outcomes,
                    quotes_by_book=quotes.quotes_by_book,
                    outcome_name=outcome_name,
                    kalshi_ask_tenths=ask,
                    already_dropped=len(quotes.books_dropped),
                )
                if dist is not None:
                    detail["books"] = dist.as_dict()
        detail["kalshi_drift_tenths"] = kalshi_drift(
            conn, row["ticker"], row["side"], now_ms=now
        )
        detail["drift_window_ms"] = DRIFT_WINDOW_MS

        # The Skeptic panel's board (ADR 0068): every check's verdict,
        # reconstructed from the stored reason. `judged_ms` is the basis the
        # verdicts are facts about -- the screen must caption it, because
        # "passed at 19:02" and "passes now" are different claims.
        detail["gauntlet"] = gauntlet_view(row["suppressed_reason"])
        detail["gauntlet"]["judged_ms"] = detail.get(
            "freshness_measured_from_ms"
        )
        return detail

    # Handlers that moved out from here under the Read-tool ceiling. Each
    # `register()` receives exactly the closure locals its handlers read, by
    # keyword, and is called where the handlers used to sit so the route
    # registration order is unchanged. See `backend/api/routers/__init__.py`.
    scout_router.register(
        app, app_config=app_config, get_conn=get_conn, require_auth=require_auth,
    )

    ledger_router.register(app, gate=gate, get_conn=get_conn)

    status_router.register(
        app, app_config=app_config, gate=gate, risk=risk, get_conn=get_conn,
    )

    parlays_router.register(
        app,
        app_config=app_config,
        staleness=staleness,
        thresholds=thresholds,
        combo_api=combo_api,
        get_conn=get_conn,
        require_auth=require_auth,
    )

    hedge_router.register(
        app,
        app_config=app_config,
        staleness=staleness,
        live_quotes=live_quotes,
        get_conn=get_conn,
        require_auth=require_auth,
    )

    odds_router.register(
        app, app_config=app_config, odds=odds, get_conn=get_conn,
        require_auth=require_auth,
    )

    # -- price history for the market chart ---------------------------------

    @app.get("/api/market/{ticker}/candles")
    async def market_candles(
        ticker: str, range: str = Query(default="1w"), conn=Depends(get_conn)
    ) -> dict:
        """Kalshi's own candlesticks for one market, shaped for the chart.

        History, not a quote: `price` OHLC is the traded price, and nothing
        here feeds sizing, the order path, or any measurement. Unreadable
        fields arrive as null, never 0 -- a candle in which nothing traded is
        a gap on the chart, not a bar at zero.

        The range names mirror Kalshi's own app. Interval choices keep every
        answer under ~1,500 bars: a day at 1-minute candles, a week and a
        month at hourly, everything at daily capped at 90 days.
        """
        spans = {
            # (period_interval minutes, lookback seconds)
            "1d": (1, 24 * 3600),
            "1w": (60, 7 * 24 * 3600),
            "1m": (60, 30 * 24 * 3600),
            "all": (1440, 90 * 24 * 3600),
        }
        if range not in spans:
            raise HTTPException(
                status_code=422,
                detail=f"range must be one of {sorted(spans)}, got {range!r}",
            )
        interval, lookback_s = spans[range]

        row = conn.execute(
            "SELECT series_ticker, title, close_ms FROM kalshi_markets "
            "WHERE ticker = ?",
            (ticker,),
        ).fetchone()
        # An undiscovered market still has a series: the ticker's first
        # hyphen-segment IS the series ticker on every observed market.
        series = (row["series_ticker"] if row and row["series_ticker"] else None) \
            or ticker.split("-", 1)[0]

        # Anchor the window on the market's close, not on "now": a game that
        # finished yesterday has no candles in the last 24 hours, so a
        # now-anchored 1D window rendered every settled market as a blank
        # chart (measured live by kalshi-platform on 2026-08-18 -- 0 candles
        # now-anchored vs 6 close-anchored on a market 1.5 days done).
        now_s = db.now_ms() // 1000
        close_s = (row["close_ms"] // 1000) if row and row["close_ms"] else None
        end_ts = min(now_s, close_s) if close_s else now_s
        try:
            raw = await live_quotes().history(
                series,
                ticker,
                start_ts=end_ts - lookback_s,
                end_ts=end_ts,
                period_interval=interval,
            )
        except ConfigError as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    "This instance holds no Kalshi credentials, so price "
                    f"history cannot be read: {exc}"
                ),
            ) from exc
        except QuoteUnavailable as exc:
            raise HTTPException(
                status_code=422 if exc.permanent else 503, detail=str(exc)
            ) from exc

        candles = []
        dropped = 0
        for entry in raw:
            parsed = parse_chart_candle(entry)
            if parsed is None:
                dropped += 1
            else:
                candles.append(parsed)
        return {
            "ticker": ticker,
            "title": row["title"] if row else None,
            "range": range,
            "period_minutes": interval,
            "candles": candles,
            "dropped_unreadable": dropped,
        }

    estimates_router.register(
        app,
        app_config=app_config,
        odds=odds,
        live_quotes=live_quotes,
        get_conn=get_conn,
        require_auth=require_auth,
    )

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
        #
        # **The check stays; what supplies the DIAGNOSIS moved, 2026-08-26.**
        # `derive_yes_ask` now applies `is_valid_price` itself, because the
        # same rule had been patched at three call sites and the fourth one
        # nobody patched took the live recorder down. That makes this guard
        # belt-and-braces -- and it collapses `live_ask` to `None` in both
        # cases, so the two sentences below can no longer be told apart from
        # the derived value. They are told apart from the INPUT instead: a
        # readable opposing bid means the book is genuinely one-sided, an
        # unreadable one means the field could not be parsed.
        if not is_valid_price(live_ask):
            opposing_bid = quote.opposing_bid_tenths(side)
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{quote.ticker} has no {side} offer right now"
                    + (
                        " -- the opposing bid is unreadable"
                        if opposing_bid is None
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
        # 8a. Derive the dollar caps from the venue's observed balance, at
        #     this instant (ADR 0045). `risk` off `create_app` is underived
        #     by construction -- `RiskConfig.load()` carries no dollars -- so
        #     an unobserved balance refuses here rather than sizing from a
        #     stale typed number.
        #     A directly-injected config (tests, tools) carries explicit
        #     dollars and is trusted as-is -- clamp what you trust; refuse
        #     what you're validating.
        risk_now = risk
        if risk.underived:
            risk_now = risk.with_observed_balance(db.latest_balance_tenths(conn))
        if risk_now is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "the account balance has never been observed "
                    "(`venue_balance_snapshots` is empty or its newest row is "
                    "unreadable), so no bankroll or cap can be derived. "
                    "Refusing -- 'cannot determine the bankroll' must never "
                    "resolve to a typed default."
                ),
            )

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
        #    `dry_run=ORDERS_ARE_DRY_RUNS` on the position read, matching
        #    `exposure`: an order is admitted against open-order history of its
        #    own kind. The daily P&L read takes no such split -- ADR 0064: it
        #    comes from `venue_settlements`, the venue's own record of every
        #    bet however placed, because the engine-path `settlements` table
        #    has never held the only bets that exist, and it refuses (`None`)
        #    when the mirror's freshest read is stale rather than reporting
        #    "no losses today" off a dead poller.
        fair = freshness["fair_probability"]
        daily_pnl = bets_module.venue_daily_realised_pnl_dollars(
            conn,
            now_ms=db.now_ms(),
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
            risk=risk_now,
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
            request.contracts, authorised, resized.contracts, risk_now.max_order_contracts
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

        # Inside a try since 2026-08-22: with the constant flipped and no REST
        # client wired, the constructor raises -- correctly (ADR 0018: arming
        # needs the client too) -- but from here it surfaced as an uncaught
        # 500 instead of a refusal that names the missing half.
        try:
            placer = OrderPlacer(dry_run=ORDERS_ARE_DRY_RUNS)
        except OrderRefused as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"live placement is half-armed: {exc} Arming is a code "
                    f"change (ADR 0018) and both halves move together."
                ),
            ) from exc

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
                max_exposure_dollars=risk_now.max_exposure_dollars,
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
            "max_exposure_dollars": risk_now.max_exposure_dollars,
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
            # Conditional since 2026-08-22: this string was hardcoded, so the
            # day the constant flips a live fill would still have rendered as
            # a dry run on the phone -- the one wrong reassurance an order
            # path can give.
            "note": (
                "Dry run. The gate is open but live placement is not armed in "
                "this build -- the request body above is exactly what would be "
                "sent, and the client_order_id makes a retry idempotent."
                if outcome.dry_run
                else (
                    "LIVE ORDER. The request body above was sent to Kalshi; "
                    "the client_order_id makes a retry idempotent."
                )
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

    # -- the manual order path (ADR 0063) -----------------------------------
    #
    # A SEPARATE door for Joe's own hand bets: separate route, separate
    # table, separate dry-run constant. Nothing here reads or writes
    # `recommendations`, `orders`, or anything `gate.py` counts — hand bets
    # must never move the interlock's populations. What it shares with the
    # engine path is imported by name (the live-quote read, the fee-inclusive
    # exposure arithmetic, the reserve-then-check transaction shape) so the
    # two paths cannot drift on arithmetic while staying separate on
    # population.

    manual_config = manual_order_config or ManualOrderConfig.load()

    def _manual_reachable() -> Optional[str]:
        """None when the path may answer, else the refusal text.

        BOTH halves are server-side (CLAUDE.md: a public URL must not be one
        config bug from the order path): the demo instance refuses on its
        mode regardless of any env leak, and live refuses until the flag is
        deliberately set.
        """
        if app_config.is_demo:
            return (
                "the manual order path does not exist on the demo instance, "
                "by construction."
            )
        if not manual_config.enabled:
            return (
                "the manual order path is not enabled on this instance "
                "(MANUAL_ORDERS_ENABLED). Enabling it is a deliberate act, "
                "not a default."
            )
        return None

    def _tradeable_ask(ask_tenths: Optional[int]) -> Optional[int]:
        """A derived ask, or `None` when it is not a price anyone can pay.

        Asks are derived — `yes_ask = 1000 - best_no_bid` — so an EMPTY book
        does not produce "no ask", it produces the endpoints: a missing NO bid
        reads as a resting bid of 100c and hands back a 0c YES ask. 0 and 1000
        are settled outcomes, not quotes (`is_valid_price` refuses both), and
        this is exactly the shape of every combination market on the venue
        right now: `no_bid_dollars = 1.0000`, depth 0.0, a YES ask that renders
        as **0c**.

        Observed on live 2026-08-26 while driving the ticket for the first
        time. The order path was already safe — `OrderRequest` refuses the
        price on the grid — but the SCREEN read "YES 0c", which is a free
        contract on the most illiquid product the venue lists, and CLAUDE.md
        rule 1 is that a large apparent edge is a bug until proven otherwise.
        The honest render is no ask at all, which the ticket already has words
        for.
        """
        if ask_tenths is None or not is_valid_price(ask_tenths):
            return None
        return ask_tenths

    def _is_combo(ticker: str) -> bool:
        """A combination (multivariate-event) market, by ticker prefix.

        One predicate, used by the read, the size ceiling, the fee choice and
        the refusal, so those four cannot disagree about what a combo is.
        `JUNK_PREFIX` in discovery uses the same prefix and is why no combo
        ever reaches `recommendations`.

        **Now five callers, and the fifth is why this delegates rather than
        spelling the prefix out.** `manual_orders.consensus_snapshot` has to
        answer the same question at intent-write time -- a combination has no
        devigged consensus at all -- and a second `startswith("KXMVE")` in the
        store would be two implementations of one boundary, which is the shape
        this repo keeps getting caught by.
        """
        return manual_store.is_combo_ticker(ticker)

    def _manual_worst_case_dollars(
        order: OrderRequest, *, combo: bool
    ) -> Optional[float]:
        """What this order costs if it fills completely, fee included.

        `OrderRequest.worst_case_cost_dollars` for everything but a combo.
        On a combo the same arithmetic runs through `combo_taker_fee`, whose
        coefficient sits above every combo charge this repo has observed
        (ADR 0073) -- because `calculate_fee` undercharged four of the eight
        combo fills on the record, and a per-bet cap checked against an
        understated cost is not a cap.

        The fee is taken at the larger of the sent and un-snapped prices, for
        the reason `worst_case_cost_dollars` gives: the curve peaks at 50c,
        so a snapped-down price understates a fee just below the peak.

        `None` when the fee is unreadable -- the caller refuses; it never
        substitutes zero.
        """
        if not combo:
            return order.worst_case_cost_dollars
        stake = order.count * order.fill_price_tenths / float(PRICE_MAX)
        sent = combo_taker_fee(order.fill_price_tenths, order.count)
        asked = combo_taker_fee(order.limit_price_tenths, order.count)
        if sent is None or asked is None:
            return None
        return stake + max(sent, asked)

    def _manual_authorised_count(
        *,
        ticker: str,
        side: str,
        ask_tenths: int,
        price_grid,
        depth: Optional[float],
        shard_available_tenths: Optional[int],
    ) -> tuple[Optional[int], str]:
        """The largest count the POST route would actually accept, and WHICH
        constraint produced it.

        **Rewritten 2026-09-08, and the rewrite is a bug fix on the money
        path.** This used to answer a different question: the largest count
        whose fee-inclusive worst case fit `_manual_cap_dollars`, which was
        `min($3.00 spend cap, 10% of the observed balance)`. Joe removed both
        of those by name (ADR 0112 and its Amendment 1) and the POST route
        obeyed the same day -- but this number is what `ManualTicket.tsx`
        disables the confirm button above, so **the brake he removed was still
        on the button.** On a 90c market `$3.00` is three contracts. The
        server would have taken two hundred.

        That is this repo's named failure -- *one predicate with two
        spellings, and the screen believing the wrong one* -- running in the
        direction it had not run before: the screen kept braking after the
        server stopped. The previous three instances were a screen that
        promised buying which was not happening; this one refused betting that
        was permitted, on the one path that spends real money.

        So the count is now built from the constraints the POST route actually
        applies to SIZE, and from nothing else:

        - **check 4**, the structural ceiling for this ticker class --
          `COMBO_MAX_CONTRACTS` on a combination, `MANUAL_ORDER_MAX_CONTRACTS`
          otherwise. Structural, not a bet ceiling.
        - **check 8**, the depth resting at the ask. An IOC for more than the
          book holds part-fills at best.
        - **check 9a**, what the market's own exchange shard can pay for.
          The VENUE's rule, not a cap of ours.
        - the price grid, via `OrderRequest` refusing an off-grid count.

        **What is deliberately NOT here: any ceiling of ours on the size of
        the bet.** There is none left. If one reappears in this function it
        is a restored brake and ADR 0112 §5 reserves that to Joe.

        Unreadable resolves to `None` and the caller refuses, never to a
        permissive default: an unreadable shard balance means POST would 502,
        so the ticket must not offer a count it cannot honour. `None` depth
        is `0` here for the same reason check 8 reads it that way.
        """
        combo = _is_combo(ticker)
        ceiling = COMBO_MAX_CONTRACTS if combo else MANUAL_ORDER_MAX_CONTRACTS
        binding = "structural"

        if shard_available_tenths is None:
            return (None, "shard_unreadable")

        # Depth is the count the book will actually fill. `None` means the
        # side is unquoted, which check 8 refuses as zero rather than reading
        # as "unlimited".
        depth_count = 0 if depth is None else int(depth)
        if depth_count < ceiling:
            ceiling, binding = depth_count, "depth"

        # Collateral, on the shard this market settles on. Check 9a compares
        # `count * limit_price_tenths` -- price only, no fee, because that is
        # what Kalshi holds as collateral -- so this mirrors it exactly rather
        # than being conservative by a fee it would not charge. A display that
        # is stricter than the route is the bug being fixed here.
        if ask_tenths > 0:
            affordable = shard_available_tenths // ask_tenths
            if affordable < ceiling:
                ceiling, binding = affordable, "shard"

        if ceiling <= 0:
            return (0, binding)

        # The grid still has the last word: a count that cannot be expressed
        # as an order is not authorised, whatever the three bounds above say.
        # Walked down from the ceiling rather than up from 1, because the
        # bounds have already done the work and the old loop's job was to
        # find where a MONEY cap bit -- which is exactly what no longer
        # exists.
        for count in range(ceiling, 0, -1):
            try:
                OrderRequest(
                    ticker=ticker,
                    side=side,
                    action="buy",
                    count=count,
                    limit_price_tenths=ask_tenths,
                    price_grid=price_grid,
                )
            except OrderRefused:
                continue
            return (count, binding if count == ceiling else "price_grid")
        return (0, "price_grid")

    @app.get("/api/manual/market/{ticker}")
    async def manual_market(ticker: str, conn=Depends(get_conn)) -> dict:
        """The venue's live facts for ANY ticker, for the manual ticket (D1).

        The engine's `/api/market/{ticker}` is recommendation-scoped and
        404s on a ticker the engine never priced; a hand bettor's market is
        whatever the venue lists. This read is quote + book only — no fair
        value, no edge, no opinion (ADR 0062).

        **The ask is served plainly, and no `p_yes_required` flag goes with
        it.** Until 2026-09-09 this payload carried `p_yes_required: true` and
        the client masked the ask until a probability was typed (ADR 0065 §2).
        Joe removed the field — it was friction, and the consumer ADR 0065
        named to justify the masking was never built — so there is nothing
        left to mask for, and a flag saying otherwise would be the screen
        enforcing a rule the route had dropped. See
        `docs/adr/0131.md`.
        """
        unreachable = _manual_reachable()
        now = db.now_ms()
        try:
            quote = await live_quotes().fetch(ticker.strip().upper(), observed_ms=now)
        except ConfigError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"no Kalshi credentials on this instance: {exc}",
            ) from exc
        except QuoteUnavailable as exc:
            raise HTTPException(
                status_code=404 if exc.permanent else 503, detail=str(exc)
            ) from exc

        risk_now = risk
        if risk.underived:
            risk_now = risk.with_observed_balance(db.latest_balance_tenths(conn))

        # **The shard's own balance, read once for both sides.** Check 9a of
        # the POST route refuses on this and it is the VENUE's rule, so the
        # ticket has to know it or the screen will offer a count the route
        # then refuses. It is read here rather than per side because the
        # collateral is the market's, not the side's.
        #
        # An unreadable shard is NOT resolved to a spendable one: `None`
        # travels into the count as a refusal, exactly as POST 502s on it.
        # A failed call is the same unknown as an unparsable payload, so it
        # is caught rather than allowed to 503 a read-only screen -- the
        # ticket still renders, with the ask, the depth and a stated reason
        # the count is missing.
        shard_available_tenths = None
        shard_index = quote.exchange_index
        if shard_index is not None:
            try:
                shard_payload = await live_quotes().shard_balance(
                    exchange_index=shard_index
                )
            except (QuoteUnavailable, ConfigError):
                shard_payload = None
            if shard_payload is not None:
                shard_available_tenths = read_shard_funds(
                    shard_payload, exchange_index=shard_index
                ).available_tenths

        sides = {}
        for side in ("yes", "no"):
            ask = _tradeable_ask(quote.ask_tenths(side))
            depth = quote.depth_at_ask(side)
            authorised = None
            binding = "no_ask"
            if ask is not None and quote.price_grid is not None:
                authorised, binding = _manual_authorised_count(
                    ticker=quote.ticker,
                    side=side,
                    ask_tenths=ask,
                    price_grid=quote.price_grid,
                    depth=depth,
                    shard_available_tenths=shard_available_tenths,
                )
            elif ask is not None:
                binding = "no_price_grid"
            sides[side] = {
                "ask_tenths": ask,
                "ask_display": None if ask is None else format_price(ask),
                "depth_at_ask": depth,
                # "of N authorised" — the server's ceiling, never a client
                # sum. `None` means it could not be derived, which the ticket
                # renders as a refusal.
                #
                # **No ceiling of ours is in this number any more** (ADR 0112
                # Amendment 1). It is the structural ceiling, the depth at the
                # ask and what the market's shard can pay for -- the three
                # bounds the POST route applies to size -- so the button and
                # the route agree by construction rather than by coincidence.
                "authorised_contracts": authorised,
                # WHICH of them produced it. `_manual_cap_dollars` carried the
                # same virtue for the caps it replaced and its docstring said
                # why: "a refusal that does not say which bound it hit sends
                # the reader to fix the wrong thing." A depth ceiling and a
                # collateral ceiling have completely different remedies -- wait
                # for the book, or move money between shards.
                "authorised_binding": binding,
            }

        return {
            "ticker": quote.ticker,
            "observed_ms": quote.observed_ms,
            "reachable": unreachable is None,
            "unreachable_reason": unreachable,
            "sides": sides,
            "price_grid": (
                None if quote.price_grid is None else quote.price_grid.describe()
            ),
            "caps": {
                "derived": risk_now is not None
                and risk_now.max_position_dollars is not None,
                "max_position_dollars": (
                    None if risk_now is None else risk_now.max_position_dollars
                ),
                "max_exposure_dollars": (
                    None if risk_now is None else risk_now.max_exposure_dollars
                ),
            },
            # Always `None` since 2026-09-08. The cool-off was removed on
            # Joe's word (0112-the-caps-come-off-the-hand-bet-path §1), and
            # this field is what `ManualTicket.tsx` gates the buy control on
            # client-side. Leaving it populated would have kept the brake
            # working on the screen while the server no longer enforced it --
            # the exact "one predicate with two spellings" failure this repo
            # has hit three times. The KEY stays so the wire shape and the
            # frontend type do not churn; only the answer changes.
            "cooloff_until_ms": None,
            # **The counter Joe kept when he removed the switch.** Answer 4 of
            # the 2026-09-08 interview: the desk still counts his Kalshi
            # losses, including the ones he places in the venue's own app,
            # because `venue_settlements` sees both. Nothing refuses on it —
            # it is shown, which is the job ADR 0071 names. `None` means the
            # venue mirror is stale or unpolled and is rendered as unknown,
            # never as zero: "cannot read the losses" must not read as "no
            # losses" even when nothing acts on the answer (ADR 0064).
            "venue_daily_pnl_dollars": bets_module.venue_daily_realised_pnl_dollars(
                conn, now_ms=now, day_start_hour=odds.budget_day_start_utc_hour
            ),
            "lockout_until_ms": bet_estimates.lockout_until(conn, now_ms=now),
            "dry_run": manual_store.MANUAL_ORDERS_ARE_DRY_RUNS,
            # The path's own size ceiling, served rather than mirrored: a
            # client that hardcodes it is a second definition of a constant
            # that exists to be raised deliberately (ADR 0063).
            "max_contracts": (
                min(MANUAL_ORDER_MAX_CONTRACTS, COMBO_MAX_CONTRACTS)
                if _is_combo(quote.ticker)
                else MANUAL_ORDER_MAX_CONTRACTS
            ),
            "is_combo": _is_combo(quote.ticker),
            # The sentence the ticket must show before a combo order, in the
            # server's words. Wording it here rather than in the client keeps
            # the screen and the 422 saying the same thing, and keeps the
            # measurement's own numbers in it.
            #
            # **The numbers are SOURCED from the exit census, not typed.**
            # They read "40 of 40" as literal digits until 2026-09-06, which
            # is the shape that let a refuted census sentence stay green for
            # eleven days (`backend/parlays.py`'s census comment block). The
            # claim itself is unchanged and still holds — the 2026-09-06
            # parlay census refuted the *entry* half, never this one — so
            # this is a binding fix, not a correction. The guard is
            # `tests/test_manual_orders.py::test_no_census_number_in_the_
            # combo_note_is_typed_rather_than_sourced`, which parses this
            # module rather than reading the rendered string, because
            # `str(40) in note` passes just as happily on a typed digit.
            # The SCOPE clause is required by the 2026-09-13 registration
            # §12.4 and lands before that run rather than after it. The
            # sentence above it is true and correctly sourced; what was wrong
            # is the scope a reader supplies while tapping a shard-1
            # combination, which those 40 books contain zero of. No sourcing
            # guard could catch it -- not a digit is wrong -- and waiting for
            # the measurement would leave the screen making an unscoped claim
            # during the run that scopes it.
            #
            # It says what was read and what was not, and stops. It must not
            # imply the shard WAS measured, and equally must not imply it is
            # DIFFERENT: nothing has been measured there either way, and
            # §11.3 forbids the screens hinting in either direction.
            # **Three clauses here were falsified on 2026-09-10 and are
            # gone.** "Every combination book this repo has ever read had no
            # YES bid" was a universal; "nothing is known either way about
            # that shard" was a claim of ignorance; "you cannot exit it: the
            # only way out is the outcome" was the conclusion drawn from
            # both. Two `KXMVECROSSCATEGORY-SHARD1` books were read that day
            # carrying resting YES bids, two-sided, and one existence proof
            # kills all three.
            #
            # **It ships before Sunday's measurement rather than after, and
            # that is the point.** The error ran in the CAUTIOUS direction --
            # Joe was told a combination was less exitable than it may be --
            # which is exactly why it would otherwise sit here for months.
            # A money surface does not get to keep a falsified sentence
            # while a rate is pending.
            #
            # **What replaces it says less, not more.** The census still
            # bounds what was systematically read; the shard sentence now
            # reports the two books instead of denying knowledge of them;
            # and the exit sentence gives the size, because "an exit exists"
            # without "it is this small" would trade one overstatement for
            # its mirror image. No rate: Arm D measures that on 2026-09-13
            # and §11.3 forbids the screens implying a frequency until it
            # does.
            "combo_note": (
                f"Across three runs on two dates, "
                f"{COMBO_EXIT_CENSUS_BOOKS_NO_YES_BID} of "
                f"{COMBO_EXIT_CENSUS_BOOKS_READ} combination books this repo "
                f"read carried no YES bid. All of them were "
                f"{' and '.join(COMBO_EXIT_CENSUS_SERIES)}, and "
                f"{COMBO_EXIT_CENSUS_SHARD_BOOKS_READ} were on "
                f"{COMBO_EXIT_CENSUS_SHARD_SERIES} — the shard this order "
                f"is on. That shard has since been seen quoted: on "
                f"{COMBO_EXIT_SHARD_YES_BID_DATE}, "
                f"{COMBO_EXIT_SHARD_YES_BID_BOOKS} of its books carried a "
                f"resting YES bid of "
                f"{COMBO_EXIT_SHARD_YES_BID_SIZE_CONTRACTS} contracts at a "
                f"single price. So an exit is not impossible — it is small, "
                f"and how often one is there has never been measured. Buy "
                f"this expecting to hold it to the outcome or to hedge a "
                f"leg, not to sell it back. The fee is "
                f"priced through a hedged coefficient because the measured "
                f"model undercharges on combos, so the cost shown is a "
                f"ceiling and not a quote."
                if _is_combo(quote.ticker)
                else None
            ),
        }

    @app.get("/api/manual/search")
    def manual_search(
        q: str = Query(default="", max_length=80), conn=Depends(get_conn)
    ) -> dict:
        """Find a market to hand-bet that no screen surfaced.

        The slate and the Picks board show what the recorder priced; a hand
        bettor's market is whatever the venue lists, which is why the ticket
        already reads ANY ticker (`/api/manual/market/{ticker}`) and why the
        only thing missing was a way to name one.

        **Serves no prices, by construction, and that is load-bearing rather
        than incidental.** It delegates to `estimates.search_markets`, whose
        SELECT carries no quote column at all. The reason has changed and the
        property has not: it used to keep ADR 0065's masking intact — no
        browsing for an ask, typing the number it put in your head, and
        calling it your estimate — and the ticket stopped asking for a
        probability on 2026-09-09 (ADR 0131). What keeps this list
        price-free now is that a price served here would carry no age, no
        currency judgement and no book beside it; `/api/manual/market` is
        where a quote gets its caveats.

        Reachability is checked here as well as on the order itself — not
        because a market list is dangerous, but because a search box that
        answers on an instance the buy control cannot reach is a door that
        leads nowhere, described as a door.

        Combination markets never appear: discovery excludes `KXMVE` from
        `kalshi_markets` outright, and a combo has no ticker until a parlay
        card mints one.
        """
        unreachable = _manual_reachable()
        if unreachable is not None:
            raise HTTPException(status_code=403, detail=unreachable)
        query = q.strip()
        if len(query) < 2:
            return {"markets": [], "query": query}
        return {
            "markets": bet_estimates.search_markets(
                conn, query, now_ms=db.now_ms()
            ),
            "query": query,
        }

    @app.post("/api/manual-orders", dependencies=[Depends(require_auth)])
    async def place_manual_order(
        request: ManualOrderRequest, conn=Depends(get_conn)
    ) -> dict:
        """A hand bet through the portal (ADR 0063). Every safeguard is
        server-side and none is waivable from the client:

        0.  reachability (live instance AND the explicit flag) — 403
        1.  idempotency replay — the first answer, again
        2.  the desk lockout — 423, same shape as the estimate route
        3.  the cool-off after the last completed purchase — 423
        4.  KXMVE bounds — 422 without `combo_acknowledged`, 422 above one
            contract (ADR 0073; enter-only book, ADR 0012 §5, and a hedged
            fee because ADR 0046's model undercharges there). The path's own
            1-contract ceiling (ADR 0063) is checked here too.
        5.  daily-loss kill switch over the venue's own record — 422
            (ADR 0064; None refuses, never zeroes)
        6.  caps derived from the observed balance — 422 when unobserved
        7.  live quote; ask over the typed ceiling — 422 ("the ask moved")
        8.  depth at the ask — 422
        9.  per-bet cap on the fee-inclusive worst case — 422 (the combo
            hedge prices a KXMVE order; an unreadable fee refuses)
        10. any existing venue position on this ticker — 422 (the wire's
            per-row position shape has never been observed, so holding
            ANYTHING here refuses; Kalshi nets, and a buy that closes a
            position must not be recorded as opening one)
        11. reserve-then-check under the write lock, in `manual_orders`
        12. place IOC at the ceiling-bounded ask via the shared OrderPlacer
        """
        # Every refusal below is recorded durably before it propagates
        # (schema v29, `manual_order_refusals`): reservation happens at
        # check 11, so until 2026-08-30 every earlier refusal left zero
        # trace and the desk could not say which of its own brakes fired.
        # `refusal_ctx` is the check pointer -- updated at the top of
        # each numbered check, so a raise mid-check is attributed to the
        # check that was running rather than parsed out of the message.
        refusal_ctx: dict = {"check": 0, "name": "reachability"}
        try:
            # 0.
            unreachable = _manual_reachable()
            if unreachable is not None:
                raise HTTPException(status_code=403, detail=unreachable)

            # 1.
            refusal_ctx.update(check=1, name="idempotency_replay")
            existing = manual_store.find_by_idempotency_key(
                conn, request.idempotency_key
            )
            if existing is not None:
                stored = manual_store.replay_response(existing)
                if stored is None:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"this idempotency key was used by an order whose "
                            f"outcome was never stored (row {existing['id']}, "
                            f"status {existing['status']!r}). Check the record "
                            f"before retrying with a fresh key — 'we do not know "
                            f"whether it went' must not resolve to 'it did not'."
                        ),
                    )
                stored["replayed"] = True
                return stored

            now = db.now_ms()

            # 2.
            refusal_ctx.update(check=2, name="desk_lockout")
            lockout_release = bet_estimates.lockout_until(conn, now_ms=now)
            if lockout_release is not None:
                release_iso = datetime.fromtimestamp(
                    lockout_release / 1000, timezone.utc
                ).strftime("%H:%M UTC on %Y-%m-%d")
                raise HTTPException(
                    status_code=423,
                    detail=(
                        f"You said not tonight. The desk is locked until "
                        f"{release_iso}, and there is no early unlock — that is "
                        f"the point."
                    ),
                )

            # 3. REMOVED 2026-09-08 on Joe's word --
            # `docs/adr/0112-the-caps-come-off-the-hand-bet-path.md` §1,
            # answer 3 ("none"). The 10-minute cool-off between completed
            # purchases is gone. He was told first what it would cost him: he
            # averages ~2.3 fills per sitting, so it was a brake that would
            # have fired on most sittings rather than a rare one.
            #
            # `manual_store.cooloff_until_ms` is deliberately NOT deleted. It
            # is a pure read over `manual_orders` with its own tests, it is
            # what a future session would have to rebuild to restore this, and
            # ADR §5 says restoring it needs Joe rather than a session's
            # judgement. An uncalled reader is cheap; a rebuilt brake he did
            # not ask for is not. `test_manual_orders.py` pins it uncalled
            # from this route so "built but never called" stays deliberate
            # here rather than becoming another instance of the pattern.
            #
            # The check NUMBERS below are unchanged. Renumbering would have
            # silently re-pointed every `manual_order_refusals.check` row
            # already on the live box, and the durable refusal record is
            # read by `inspect_live_db`; check 3 simply no longer occurs.

            ticker = request.ticker.strip().upper()

            # 4.
            refusal_ctx.update(check=4, name="structural_ceilings")
            combo = _is_combo(ticker)
            if combo and not request.combo_acknowledged:
                # The third of the three sentences carrying the exit census,
                # and the last one still typed. Sourced from
                # `parlays.COMBO_EXIT_CENSUS_*` on 2026-09-06 for the reason
                # the other two were: `str(40) in detail` cannot tell a typed
                # digit from a sourced one, so the digits could have outlived
                # the measurement with CI green.
                #
                # **And on 2026-09-10 the claim DID move, which is what that
                # sourcing was for.** "You can enter and you cannot exit" was
                # a universal, and two `KXMVECROSSCATEGORY-SHARD1` books were
                # read that day carrying resting YES bids. ADR 0085
                # Amendment 1 §A1.4 pins against SOFTENING an exit claim that
                # still holds; it does not require repeating one that has
                # been falsified, and this is a real-money refusal path where
                # a false sentence is worse than a weaker true one. The
                # replacement keeps the warning's force by naming the size --
                # the exit that exists is a dollar of it -- and still claims
                # no rate, which Arm D measures on 2026-09-13. Guarded by
                # `tests/test_manual_orders.py::test_no_census_number_in_the_
                # combo_acknowledgement_refusal_is_typed_rather_than_sourced`.
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"combination (KXMVE) markets need the acknowledgement "
                        f"before this door opens: "
                        f"{COMBO_EXIT_CENSUS_BOOKS_NO_YES_BID} of "
                        f"{COMBO_EXIT_CENSUS_BOOKS_READ} combination books "
                        f"this repo read across three runs on two dates had "
                        f"NO YES BID, and on "
                        f"{COMBO_EXIT_SHARD_YES_BID_DATE} the "
                        f"{COMBO_EXIT_SHARD_YES_BID_BOOKS} that did carry "
                        f"one held only "
                        f"{COMBO_EXIT_SHARD_YES_BID_SIZE_CONTRACTS} "
                        f"contracts at a single price — so you can enter, "
                        f"and getting out is small and unmeasured "
                        f"(ADR 0012 §5). The fee model also "
                        f"undercharges on combos (ADR 0046); a hedged coefficient "
                        f"prices this order and it is not a measurement of what "
                        f"Kalshi charges. Send `combo_acknowledged` only if that "
                        f"is the bet you mean to make."
                    ),
                )
            # **The STRUCTURAL ceilings, not the binding one.** What bounds the
            # bet is money (check 9); these stop a market priced at a tenth of a
            # cent turning a few dollars into a count that moves a thin book on
            # its own.
            #
            # **The reason this ceiling used to give was false, corrected
            # 2026-09-08.** It said "the deepest resting bid this repo has ever
            # measured on one was 18 units (ADR 0012 §5), so a far larger count
            # could not fill anyway." Three things were wrong with that. (1) ADR
            # 0012 carries no such figure; its only "18" is the denominator of
            # `same-game 17/18`, a rate the ADR itself withdraws. (2) The real
            # source is
            # `docs/measurements/2026-08-18-combo-book-presence-inseason-result.md`,
            # which says "the deepest resting order **here** was 18.00 units" —
            # scoped by that "here" to one run of 11 rows. Every copy downstream
            # dropped the word and promoted it to "ever measured". (3) Repo-wide
            # it is wrong by ~38x: the committed captures carry resting NO bids
            # of 683, 413, 369, 311, 309 and 300 units (E3 and E2, 2026-08-09),
            # and the NO bid is the side whose complement is the ask you buy at.
            #
            # So the count ceiling no longer claims a fill bound it cannot
            # support. What survives — and is the true, load-bearing claim — is
            # the EXIT: `yes_dollars` is empty on 40/40 books ever read, 36
            # levels, zero resting YES bids. That is why a combination is held
            # tighter than a single market. It is not that you cannot get in.
            if combo and request.contracts > COMBO_MAX_CONTRACTS:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"a combination order is capped at "
                        f"{COMBO_MAX_CONTRACTS} contracts on this path, against "
                        f"an order for {request.contracts}. The cap is a "
                        f"structural ceiling, not a measured fill limit: no "
                        f"combination book this tool has read has ever carried a "
                        f"resting YES bid (40 of 40), so a combination is easy "
                        f"to enter and may be impossible to exit at size. "
                        f"Nothing below bounds the SIZE of your bet except "
                        f"the depth resting at the ask and what your exchange "
                        f"shard can pay for — the venue's rule, not a cap of "
                        f"ours."
                    ),
                )
            if request.contracts > MANUAL_ORDER_MAX_CONTRACTS:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"this path is capped at {MANUAL_ORDER_MAX_CONTRACTS} "
                        f"contracts, against an order for {request.contracts}. "
                        f"That is a structural ceiling, not the bet size: "
                        f"no ceiling of ours bounds the bet at all any more. "
                        f"What is left is the depth resting at the ask and "
                        f"what your exchange shard can pay for."
                    ),
                )

            # 5. THE COUNTER STAYS; THE SWITCH IS REMOVED. Joe's answers 2 and
            # 4 together, 2026-09-08 --
            # `docs/adr/0112-the-caps-come-off-the-hand-bet-path.md` §1. He
            # removed the daily-loss KILL SWITCH and, in the same interview,
            # kept the desk counting his Kalshi losses including the ones he
            # places in the venue's own app. Those are not in tension: the
            # figure is information, and ADR 0071 makes information this
            # product's job. So the read stays and no longer refuses.
            #
            # It also no longer refuses when it cannot be read. That refusal
            # (ADR 0064, "'cannot read the losses' must never resolve to 'no
            # losses'") existed to protect the switch, and its own words say
            # so -- "so the daily-loss switch cannot be applied". With no
            # switch it guards nothing, and keeping it would refuse a bet Joe
            # has asked nothing to refuse. ADR 0064's rule is untouched
            # everywhere it still governs a decision; `None` still means
            # unreadable here and is never coerced to 0.
            refusal_ctx.update(check=5, name="daily_loss_counter")
            daily_pnl = bets_module.venue_daily_realised_pnl_dollars(
                conn, now_ms=now, day_start_hour=odds.budget_day_start_utc_hour
            )

            # 6. NARROWED, not removed, and the narrowing is the careful part.
            # This refused unless all three derived caps were available.
            # **All three are now gone** -- the per-bet cap (check 9) and the
            # daily-loss line (check 5) on 2026-09-08 under ADR 0112, and the
            # total-exposure ceiling later the same day under its Amendment 1,
            # when Joe removed the one brake he had not previously been asked
            # about: "remove the exposure ceiling too."
            #
            # So check 6 REFUSES NOTHING and is kept only to derive `risk_now`,
            # which the recorded row still carries. A bet placed with no brake
            # should stay legible later as "this was N times the ceiling that
            # used to exist", and that is impossible if the ceiling is never
            # computed. An unobserved balance no longer refuses: there is no
            # longer a guard whose precondition it was, and refusing on a
            # precondition for nothing is how a removed cap comes back by
            # accident.
            #
            # `orders.reserve_order` still caps the ENGINE. Same scoping as
            # ADR 0112 §3.
            refusal_ctx.update(check=6, name="derived_caps_for_the_record")
            risk_now = risk
            if risk.underived:
                risk_now = risk.with_observed_balance(db.latest_balance_tenths(conn))

            refusal_ctx.update(check=7, name="live_quote_and_ceiling")
            try:
                quote = await live_quotes().fetch(ticker, observed_ms=now)
            except ConfigError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except QuoteUnavailable as exc:
                raise HTTPException(
                    status_code=404 if exc.permanent else 503, detail=str(exc)
                ) from exc
            ask = _tradeable_ask(quote.ask_tenths(request.side))
            refusal_ctx["ask_tenths"] = ask
            if ask is None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"no live ask on the {request.side} side — there is no "
                        f"price to buy at. An empty book does not report 'no ask'; "
                        f"it reports the endpoint (a 0c or 100c derived ask), and "
                        f"neither is a price anyone can pay."
                    ),
                )
            if ask > request.max_price_tenths:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"the live ask is {format_price(ask)}, above your "
                        f"{format_price(request.max_price_tenths)} ceiling. "
                        f"Refused, never re-priced — raise the ceiling only if "
                        f"you still want it at the new price."
                    ),
                )
            if quote.price_grid is None:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "the live payload carried no readable price grid; "
                        "refusing rather than assuming whole cents."
                    ),
                )

            # 8.
            refusal_ctx.update(check=8, name="depth_at_ask")
            depth = quote.depth_at_ask(request.side)
            if depth is None or depth < request.contracts:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"only {0 if depth is None else int(depth)} contracts "
                        f"rest at the ask against an order for "
                        f"{request.contracts}. An IOC for more than the book "
                        f"holds part-fills at best."
                    ),
                )

            # 9. Build at the live ask (bounded by the ceiling above), IOC.
            refusal_ctx.update(check=9, name="per_bet_cap")
            try:
                order = OrderRequest(
                    ticker=ticker,
                    side=request.side,
                    action="buy",
                    count=request.contracts,
                    limit_price_tenths=ask,
                    price_grid=quote.price_grid,
                    time_in_force="immediate_or_cancel",
                )
            except OrderRefused as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

            # 9a. **WHICH POCKET THE MONEY IS IN.** Added 2026-09-08, after
            # Joe read his own allocation off Kalshi: shard 1 (Combos)
            # $22.24, shard 0 (Default) $0.00. Every single-market bet draws
            # on shard 0 and would have been refused by the VENUE with a bare
            # `insufficient_balance` -- which, against a $22 account, reads as
            # a broken cockpit rather than as "your money is in the other
            # pocket". The combination path solved this in ADR 0084 and the
            # reasoning was never carried across; `combo_orders.check_
            # affordable`'s docstring says it outright: only the desk is in a
            # position to say so.
            #
            # **This is not a brake and does not reinstate one.** ADR 0112
            # removed the desk's own ceilings; this refuses only what the
            # venue was always going to refuse, one round trip earlier and in
            # words that name the fix. Nothing here bounds a bet Kalshi would
            # have accepted.
            #
            # The shard is read off the MARKET (`quote.exchange_index`), never
            # inferred from the ticker prefix: Kalshi's docs call that field
            # the authoritative source of truth and say ticker formats move.
            # Unreadable refuses rather than defaulting to 0 -- 0 is a real
            # shard, and guessing it is how a "payable" order dies at the
            # venue after he has typed a price and confirmed.
            refusal_ctx.update(check=9, name="shard_collateral")
            shard = quote.exchange_index
            if shard is None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "this market does not say which exchange shard it "
                        "settles on, so the desk cannot tell whether you have "
                        "the collateral for it. Refusing rather than guessing "
                        "— Kalshi keeps money per shard and will not move it "
                        "for an order. Nothing was sent."
                    ),
                )
            try:
                shard_payload = await live_quotes().shard_balance(
                    exchange_index=shard
                )
            except QuoteUnavailable as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            funds = read_shard_funds(shard_payload, exchange_index=shard)
            if not funds.is_readable:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"the balance on exchange shard {shard} could not be "
                        f"read, so the desk cannot tell whether this bet is "
                        f"payable. Refusing — an unreadable balance must "
                        f"never resolve to a spendable one. Nothing was sent."
                    ),
                )
            cost_tenths = order.count * order.limit_price_tenths
            if funds.available_tenths < cost_tenths:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"this bet needs ${cost_tenths / 1000:.2f} on exchange "
                        f"shard {shard}, which holds "
                        f"${funds.available_tenths / 1000:.2f}. Kalshi keeps "
                        f"collateral per shard and will not move it for an "
                        f"order, so it has to be allocated there first "
                        f"(kalshi.com/account/exchange-indexes). This is the "
                        f"venue's rule, not a cap of yours. Nothing was sent."
                    ),
                )

            # **THE PER-BET CAP IS REMOVED.** Joe, 2026-09-08: "remove the cap.
            # i will decide." Both ceilings go, because both were caps on the
            # size of his bet and he was answering about both -- 10% of the
            # observed balance (ADR 0045) and `MANUAL_ORDER_MAX_SPEND_TENTHS`.
            # See `docs/adr/0112-the-caps-come-off-the-hand-bet-path.md`, and
            # §4 of it in particular: after this the cockpit will not stop him
            # at any size his Kalshi collateral can pay for. That is the
            # intended outcome and restoring it needs Joe, not a session.
            #
            # `worst_case` is still computed and still recorded, because the
            # number is the transparency ADR 0071 asks for even when nothing
            # acts on it -- and because a future census of what he actually
            # bet is unreadable without it.
            #
            # The unreadable-fee refusal went with the cap rather than
            # surviving it. Its own message said why it existed: "so its
            # worst-case cost cannot be checked against your per-bet cap."
            # With no cap it guarded nothing, and it would have refused a bet
            # on the strength of a bound that no longer exists. `None` is
            # still `None` here and is never read as zero -- it is recorded
            # as unknown, which is the honest value.
            worst_case = _manual_worst_case_dollars(order, combo=combo)

            # 10. A LIVE positions read, not the 12-hour mirror. The per-row
            refusal_ctx.update(check=10, name="netting_guard")
            #     shape was observed 2026-08-30 (`position_fp`, a fixed-point
            #     string, fractional — see `rest.positions()`), so the guard
            #     compares the quantity the venue reports instead of refusing on
            #     ticker alone: until then a market Joe had EXITED still refused
            #     re-entry, because the bare endpoint returns zero-quantity rows
            #     for every market ever traded. A row too unreadable to name a
            #     ticker, or naming this ticker with a quantity that will not
            #     parse, still refuses — unreadable resolves to a refusal, never
            #     to zero.
            #
            #     **And the read is stamped, because it is a real one.**
            #     `poll_log` means "the venue was asked and this is what it
            #     said", and this asked the venue — so throwing the observation
            #     away (which this route did until 2026-08-29) left the
            #     open-positions count claiming to be older than the newest read
            #     actually taken. What the stamp does NOT establish, and the
            #     reason it supplements `portfolio_poll.poll_positions` and never
            #     substitutes for it: it is taken BEFORE the order, so it does
            #     not include the bet being placed, and it fires only when Joe
            #     bets — a night with no taps leaves no row here at all. It is
            #     also not derived from anything local; a synthetic row would
            #     poison three registered tripwires and the daily-loss kill
            #     switch, which `odds/sweeplog.py` refuses for the same reason.
            positions_read_ms = db.now_ms()
            try:
                position_rows = await live_quotes().portfolio_positions()
            except (ConfigError, QuoteUnavailable) as exc:
                await _stamp_positions_read(
                    app_config.db_path,
                    now_ms=positions_read_ms,
                    ok=False,
                    error=repr(exc),
                )
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"could not read your open positions, so 'this buy does "
                        f"not close an existing position' cannot be verified: "
                        f"{exc}. Kalshi nets — refusing rather than guessing."
                    ),
                ) from exc
            await _stamp_positions_read(
                app_config.db_path,
                now_ms=positions_read_ms,
                ok=True,
                row_count=len(position_rows),
                rows=position_rows,
            )
            for row in position_rows:
                row_ticker = row.get("ticker") if isinstance(row, dict) else None
                if row_ticker is None:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "a position row came back too unreadable to name a "
                            "ticker, so 'this buy does not close an existing "
                            "position' cannot be verified. Refusing rather than "
                            "guessing."
                        ),
                    )
                if row_ticker != ticker:
                    continue
                quantity = parse_position_fp(row.get("position_fp"))
                if quantity is None:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "the venue reports a row for this market but its "
                            "quantity would not parse, so whether you already "
                            "hold a position here cannot be verified. Refusing "
                            "rather than guessing."
                        ),
                    )
                if quantity != 0:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "you already hold a position this order could net "
                            "against. Kalshi nets buys against opposite "
                            "holdings, and this record must not book a close as "
                            "an open. Manage the existing position in the "
                            "Kalshi app first."
                        ),
                    )

            # 11. ADR 0018's SECOND barrier, wired here rather than left for the
            refusal_ctx.update(check=11, name="placer_arming")
            #     arming commit to remember: `OrderPlacer.__init__` refuses when
            #     `dry_run` is False and no REST client was passed, so flipping
            #     the constant alone produces a 503 and not an order. The client
            #     is the app's one shared `KalshiRestClient` (`combo_api`), built
            #     on first use and closed in the lifespan — never a second one
            #     per request, which would cost a PEM re-parse and an SSL setup
            #     on the request that spends money.
            #
            #     Built ONLY when the path is armed. `combo_api()` calls
            #     `KalshiConfig.load()`, which raises on a keyless instance, and
            #     a dry run must keep working everywhere it works today.
            placer_rest = None
            if not manual_store.MANUAL_ORDERS_ARE_DRY_RUNS:
                try:
                    placer_rest = combo_api()
                except ConfigError as exc:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            f"the manual path is armed but this instance holds "
                            f"no Kalshi credentials: {exc}. Nothing was sent."
                        ),
                    ) from exc
            try:
                placer = OrderPlacer(
                    rest=placer_rest,
                    dry_run=manual_store.MANUAL_ORDERS_ARE_DRY_RUNS,
                )
            except OrderRefused as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

        except HTTPException as exc:
            # Forensics beside the refusal, never in its way: the
            # recorder runs on a throwaway connection, falls back to a
            # journal line, and swallows its own errors -- and even a
            # recorder that blows up entirely must leave the 4xx
            # standing, not convert it into a 500.
            try:
                await run_in_threadpool(
                    manual_store.record_refusal_durably,
                    app_config.db_path,
                    created_ms=db.now_ms(),
                    check_number=refusal_ctx["check"],
                    check_name=refusal_ctx["name"],
                    http_status=exc.status_code,
                    detail=str(exc.detail),
                    ticker=request.ticker.strip().upper(),
                    side=request.side,
                    requested_contracts=request.contracts,
                    max_price_tenths=request.max_price_tenths,
                    idempotency_key=request.idempotency_key,
                    ask_tenths=refusal_ctx.get("ask_tenths"),
                )
            except Exception:  # noqa: BLE001 -- the refusal outranks its record
                logger.exception("refusal recording raised; the 4xx stands")
            raise

        submitted_ms = db.now_ms()
        try:
            row_id = await run_in_threadpool(
                _write_manual_intent,
                app_config.db_path,
                order,
                dry_run=placer.dry_run,
                submitted_ms=submitted_ms,
                max_price_tenths=request.max_price_tenths,
                idempotency_key=request.idempotency_key,
            )
        except DuplicateOrder as exc:
            stored = manual_store.replay_response(exc.row)
            if stored is None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "a concurrent tap reserved this key and its outcome "
                        "is not stored yet. Nothing further was sent."
                    ),
                ) from exc
            stored["replayed"] = True
            return stored
        # The `ExposureCapExceeded` branch was removed 2026-09-08 with the cap
        # itself (ADR 0112 Amendment 1). `reserve_manual_order` cannot raise it
        # any more; `orders.reserve_order` still can, and `/api/orders` still
        # catches it.
        except Exception as exc:                        # noqa: BLE001
            raise HTTPException(
                status_code=503,
                detail=(
                    f"the order was not sent, because it could not be "
                    f"written down first: {exc}."
                ),
            ) from exc

        # 12.
        outcome = await placer.place(order)
        try:
            await run_in_threadpool(
                _write_manual_outcome, app_config.db_path, row_id, outcome
            )
        except Exception:                               # noqa: BLE001
            logger.exception(
                "manual order row %d for %s was placed (%s) and could not "
                "be updated; it stays pending.",
                row_id, ticker, outcome.status,
            )

        # 13. THE EXIT, WIRED TO THE ENTRY. A combination is enter-only, so
        # `/hedge` is the only way out of one -- and it watches
        # `parlay_positions`, which this path never wrote. Two real
        # combination fills landed on 2026-09-08 and that table was empty for
        # the entire life of both positions.
        #
        # Only on a real fill of a real order: a dry run bought nothing, and
        # `fill_count` is the quantity the VENUE says is held rather than the
        # quantity asked for, so a part-filled IOC is watched at its true
        # size. `unrecognised_response` deliberately records nothing -- the
        # quantity is unknown there, and a position invented at the requested
        # size would be a fabricated holding in the one table whose job is to
        # tell him what he owns.
        position_id = None
        position_note = None
        filled = outcome.fill_count
        if combo and not outcome.dry_run and filled is not None and filled > 0:
            try:
                position_id = await run_in_threadpool(
                    _record_combo_position,
                    app_config.db_path,
                    ticker=ticker,
                    contracts=int(filled),
                    fill_price_tenths=order.fill_price_tenths,
                    now_ms=db.now_ms(),
                    placed_ms=submitted_ms,
                )
            except Exception:                           # noqa: BLE001
                # Never into the order path: the money is already spent and a
                # bookkeeping failure must not report the purchase as failed.
                logger.exception(
                    "manual order row %d filled on combo %s and its hedge "
                    "position could not be recorded.", row_id, ticker,
                )
            if position_id is None:
                # Said out loud, on the screen. Silence here is the exact
                # failure being fixed -- he would believe the desk was
                # watching a position it had never heard of.
                position_note = (
                    "This combination is NOT being watched for a hedge — its "
                    "legs could not be recovered, so record it by hand on "
                    "/hedge. A combination is enter-only; the hedge is its "
                    "only exit."
                )
            else:
                position_note = (
                    "Recorded on /hedge as position "
                    f"{position_id} — its legs are being watched for a hedge."
                )

        body = {
            "status": outcome.status,
            "dry_run": outcome.dry_run,
            "manual_order_id": row_id,
            "client_order_id": order.client_order_id,
            "ticker": ticker,
            "side": request.side,
            "contracts": request.contracts,
            "limit_price_display": format_price(order.fill_price_tenths),
            "max_price_display": format_price(request.max_price_tenths),
            # "at most", never "costs $X": MLB's k is half the coefficient
            # charged, so the point figure would overstate — and never a
            # payout figure, which would assume untested H4 (ADR 0027).
            # `None` since 2026-09-08: the cap that used to refuse an
            # unreadable fee is gone (check 9), so this can now legitimately
            # be unknown and must say so rather than crash on the format or
            # print "$0.00", which would read as a free bet.
            "worst_case_cost_display": (
                "unknown — the fee on this order could not be computed"
                if worst_case is None
                else f"${worst_case:.2f}"
            ),
            "kalshi_order_id": outcome.kalshi_order_id,
            "error_text": outcome.error_text,
            # `None`, not a future timestamp: nothing rests after this order
            # any more, and a screen told to unlock at a time is a screen that
            # locks until then.
            "cooloff_until_ms": None,
            # Read at check 5 and carried here rather than discarded: the
            # switch is gone, the counting is not.
            "venue_daily_pnl_dollars": daily_pnl,
            # `None` on anything that is not a filled live combination.
            # `hedge_position_id` is None WITH a note when the fill happened
            # and the position could not be built -- the two must stay
            # separable, because "not a combo" and "a combo nothing is
            # watching" are opposite facts and only one of them is a problem.
            "hedge_position_id": position_id,
            "hedge_position_note": position_note,
            "note": (
                "Dry run — the manual path is not armed. Arming is a code "
                "change (ADR 0063); the C0 probe it waited on was taken "
                "2026-08-23. This is exactly the body a live order would "
                "send."
                if outcome.dry_run
                else (
                    "LIVE ORDER sent immediate-or-cancel. If the status is "
                    "unrecognised_response, the order MAY have been placed "
                    "— check the Kalshi app before retrying."
                )
            ),
            "replayed": False,
        }

        try:
            await run_in_threadpool(
                _write_manual_response, app_config.db_path, row_id, body
            )
        except Exception:                               # noqa: BLE001
            logger.exception(
                "manual order row %d could not store its response; a "
                "duplicate tap will refuse rather than replay.", row_id,
            )

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


async def _stamp_positions_read(
    db_path,
    *,
    now_ms: int,
    ok: bool,
    row_count: Optional[int] = None,
    rows: Optional[list] = None,
    error: Optional[str] = None,
) -> None:
    """Record step 10's live positions read in `poll_log`, and keep its rows.

    The read is real -- `live_quotes().portfolio_positions()` asks the venue --
    so `poll_log`'s own meaning ("the venue was asked and this is what it
    said") is satisfied by it and by nothing local. It is written through the
    same `log_poll_attempt` the poller uses, with the same endpoint name, so
    `bets.open_positions` and the registration's gap tripwires read one
    population and not two.

    **That sentence became wholly true on 2026-09-05 and was half-true
    before** (ADR 0107 sections 5 and 9). `poll_log` has two writers of
    positions reads. Until this edit only the poller kept the rows it counted,
    so a reader taking "the newest successful positions poll" would find this
    route's stamp carrying `row_count = N` with no rows under it, and refuse
    the money figure for up to five minutes after every hand bet -- at the one
    moment the desk is open. The rows now go to `store_positions_snapshot`
    inside the same transaction, which also sets `poll_log.mirrored = 1`, and
    `bets.open_positions` selects on that marker rather than on recency alone.

    `rows=None` is not the same as `rows=[]`. `None` means the caller is not
    offering any (a failed read; a caller written before this parameter
    existed) and nothing is mirrored; `[]` is the venue saying the account
    holds nothing, which is a real observation and is stored as a marked
    snapshot with zero rows. That distinction is the whole reason the marker
    exists -- no count can tell "kept nothing" from "kept, and there was
    nothing".

    **What it does NOT establish**, restated here because a reader who finds
    this row in the table will not have step 10's comment in front of them:

    - It is taken **before** the order is sent, so its `row_count` cannot
      include the bet being placed. A row stamped at 20:14 next to a fill at
      20:14 is the count as it was a moment earlier, not after.
    - It fires **only when Joe taps**. A night with no bets leaves no row
      here, so this can never be the thing that keeps the count fresh -- it
      supplements `portfolio_poll.poll_positions` and does not substitute for
      it. If the poller stops, the count goes stale exactly as it should.
    - Failures are stamped too, matching the poller's convention: a failure
      that writes nothing is invisible and reads like a quiet evening. A
      failed read keeps **nothing** and is left unmarked: the venue answered
      with an error, so there is no observation to mirror, and marking it
      would tell the reader rows were kept when none were.

    **Never blocks the order.** The stamp is bookkeeping about a read that
    already happened; losing it must not cost Joe a bet, so a write failure
    is logged and swallowed. The order path's own refusals are unaffected --
    this function is called after the read and never decides anything. That
    now covers the mirror too: if `store_positions_snapshot` raises, the whole
    write is lost together and the bet still goes through. Losing both is the
    right failure -- an unmarked stamp is a state `bets.open_positions`
    already knows how to refuse, while a marked stamp with no rows would be a
    lie it would believe.
    """
    def _write() -> None:
        conn = db.open_db(db_path)
        try:
            poll_log_id = log_poll_attempt(
                conn,
                now_ms=now_ms,
                endpoint="positions",
                ok=ok,
                row_count=row_count,
                error=error,
            )
            if ok and rows is not None:
                store_positions_snapshot(
                    conn, poll_log_id=poll_log_id, now_ms=now_ms, rows=rows
                )
            conn.commit()
        finally:
            conn.close()

    try:
        await run_in_threadpool(_write)
    except Exception:                                   # noqa: BLE001
        logger.exception(
            "the live positions read at %d could not be stamped in poll_log; "
            "the order path is unaffected", now_ms,
        )


def _write_manual_intent(db_path, order, **kwargs) -> int:
    """The manual row, reserved under its own write lock (ADR 0063)."""
    conn = db.open_db(db_path)
    try:
        return manual_store.reserve_manual_order(conn, order, **kwargs)
    finally:
        conn.close()


def _write_manual_outcome(db_path, row_id: int, outcome) -> None:
    conn = db.open_db(db_path)
    try:
        manual_store.record_outcome(conn, row_id, outcome)
    finally:
        conn.close()


def _write_manual_response(db_path, row_id: int, body: dict) -> None:
    conn = db.open_db(db_path)
    try:
        manual_store.record_response(
            conn, row_id, json.dumps(body, sort_keys=True)
        )
    finally:
        conn.close()


def _record_combo_position(
    db_path,
    *,
    ticker: str,
    contracts: int,
    fill_price_tenths: int,
    now_ms: int,
    placed_ms: int,
) -> Optional[int]:
    """Put a combination bought through the desk under `/hedge`'s watch.

    **The exit, wired to the entry.** A `KXMVE` combination is enter-only --
    `yes_dollars` empty on 40 of 40 books this repo has read, zero resting
    YES bids over 36 levels (ADR 0012 §5) -- so hedging a leg is the only way
    out of one, and `/hedge` can only watch what `parlay_positions` holds.
    Until 2026-09-09 the only writer of that table was `POST
    /api/hedge/positions`, a separate tap on a separate screen: the desk
    armed the entry and left the exit to Joe's memory. On 2026-09-08 it took
    two real combination fills and `parlay_positions` was empty for the whole
    life of both positions.

    Returns the new position id, or `None` when the position could not be
    built honestly. **`None` is never an error the caller may hide**: it
    means the money moved and nothing is watching it, which is exactly the
    state this function exists to end, so the caller says so on the screen.

    Nothing here may raise into the order path. The order is already placed
    and the money is already spent; a bookkeeping failure must not turn a
    successful purchase into a 500 that tells Joe nothing happened.
    """
    conn = db.open_db(db_path)
    try:
        lookup = parlays.priced_lookup_for(conn, ticker)
        if lookup is None:
            return None
        parsed = parlays.legs_for_position(lookup["selected_legs"])
        if parsed is None:
            return None
        # Stake is what he paid; return is what the venue pays a winning
        # contract, $1.00 each. Both in tenths of a cent, integer, per
        # CLAUDE.md -- and `return > stake` holds by construction because a
        # price is 1..999 tenths, which is what the table's CHECK requires.
        stake_tenths = contracts * fill_price_tenths
        return_tenths = contracts * 1000
        note = (
            "Recorded automatically from the hand-bet path: a combination is "
            "enter-only, so this is the only exit it has."
        )
        if parsed.labels_are_tickers:
            note += (
                " Leg names are market tickers -- this combination was priced "
                "before the desk began recording leg labels, and inventing "
                "them was refused."
            )
        return held_parlays.record_position(
            conn,
            now_ms=now_ms,
            source="kalshi_combo",
            label=lookup["card_key"] or ticker,
            stake_tenths=stake_tenths,
            return_tenths=return_tenths,
            legs=parsed.legs,
            placed_ms=placed_ms,
            combo_ticker=ticker,
            parlay_lookup_id=int(lookup["id"]),
            note=note,
        )
    finally:
        conn.close()


# A row's freshness basis, in SQL, for the row alias `r`.
#
# **A bound, never a decision.** `gate.live_ages` owns what instant a row is
# measured from, and `api/serialise._live_ages` reports it as
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


def _slate_filter_sql(list_filter: Optional[ListFilter]) -> tuple[str, list]:
    """The #15 cut as a SQL suffix for `/api/slate`'s two window queries.

    Empty when there is no cut, so the unfiltered statement is the one this
    route ran before the parameters existed. Both predicates assume the
    query has `event_links` aliased `l`, and both resolve through the row's
    linked odds fixture:

    - league: `EXISTS` a snapshot of that fixture under the requested
      `sport_key`. `odds_snapshots.sport_key` rather than `event_links
      .league`, because the parameter names the odds feed's key and the link
      stores Kalshi's competition string (see `backend/list_filters.py`).
    - kickoff: `MIN(commence_ms)` per fixture, `BETWEEN` the window's bounds.
      The same definition the route's `kickoffs` read and its sort key use,
      so the row is cut on the clock it prints. An unlinked row's subquery is
      `NULL`, and `NULL BETWEEN` is not true -- the refusal, in SQL.

    Each subquery is an indexed SEARCH on `odds_event_id`
    (`idx_odds_event`), one per row in the window, not a derived table over
    every fixture in the history.
    """
    if list_filter is None:
        return "", []
    sql, params = "", []
    if list_filter.league is not None:
        sql += (
            " AND EXISTS (SELECT 1 FROM odds_snapshots o "
            "WHERE o.odds_event_id = l.odds_event_id AND o.sport_key = ?)"
        )
        params.append(list_filter.league)
    if list_filter.kickoff_until_ms is not None:
        sql += (
            " AND (SELECT MIN(o.commence_ms) FROM odds_snapshots o "
            "WHERE o.odds_event_id = l.odds_event_id) BETWEEN ? AND ?"
        )
        params.extend([list_filter.kickoff_from_ms, list_filter.kickoff_until_ms])
    return sql, params
