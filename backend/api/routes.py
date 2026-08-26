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

import asyncio
import json
import logging
import math
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from statistics import NormalDist
from typing import Annotated, Optional

import httpx
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
    POSITION_FRACTION_OF_BANKROLL,
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
from ..core.correlation import CorrelationRefused, Leg
from ..core.parlay import (
    ParlayQuote,
    american_to_decimal,
    decimal_to_american,
    kalshi_equivalent,
    value_parlay,
)
from ..core.ev import breakeven_win_rate, edge_after_fees_tenths
from ..core.fees import combo_taker_fee
from ..core.prices import (
    PRICE_MAX,
    format_price,
    format_probability,
    is_valid_price,
    tenths_to_dollars,
)
from ..core.sizing import size_position, verify_positive_after_fees
from .. import bets as bets_module
from .. import estimates as bet_estimates
from .. import passes as desk_passes
from ..core.suppression import SuppressionConfig, gauntlet_view
from ..core.teaser import find_wong_candidates
from ..engine import suppression_summary
from ..analysis.clv import DEFAULT_HORIZON_HOURS
from ..analysis.clv_signal import SignalReport, report_from_connection
from ..gate import (
    POPULATIONS,
    clustered_clv,
    evaluate_gate,
    live_ages,
    population_counts,
    recommendation_freshness,
)
from ..kalshi.candles import parse_chart_candle
from ..kalshi.orders import OrderPlacer, OrderRefused, OrderRequest
from ..kalshi.rest import KalshiRestClient
from ..kalshi.quotes import LiveQuote, LiveQuoteSource, QuoteUnavailable
from ..live import QuoteHub, sse
from ..logging_setup import configure_logging
from ..market_results import result_coverage
from ..agents.base import AgentConfig, build_client
from ..agents.budget import AgentBudget
from ..agents import scout_desk
from ..notify.alerts import Alerter
from ..notify.discord import DiscordConfig
from ..odds import attention, ondemand
from ..odds.budget import CreditBudget, sweep_cost
from ..odds.client import prop_market_keys
from ..odds.timing import (
    DEFAULT_DAY_START_UTC_HOUR,
    SLATE_WINDOW_MS,
    window_status,
)
from ..parlays import LookupRefused, build_ladder_payload, price_card_on_kalshi
from ..playbook import read_playbook
from ..runner import book_quotes_for_event
from ..settlement import open_position_dollars
from ..slate import DRIFT_WINDOW_MS, book_distribution, kalshi_drift
from ..store import db
from ..store import manual_orders as manual_store
from ..store.manual_orders import (
    COMBO_MAX_CONTRACTS,
    MANUAL_ORDER_MAX_CONTRACTS,
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


class DeskPassRequest(BaseModel):
    """One per-market pass: "I looked at this and chose not to bet it."

    `reason` is optional and stays optional (slice B6): a required reason is
    a toll on the correct boring action. The length caps are hygiene on a
    string that will be rendered back, not validation of the decision --
    a pass needs no justifying.
    """

    ticker: str = Field(min_length=1, max_length=80)
    reason: Optional[str] = Field(default=None, max_length=500)


class ManualOrderRequest(BaseModel):
    """What the manual ticket sends (ADR 0063). Everything is re-validated
    server-side; the two numbers the client DOES author — the price ceiling
    and the typed P(YES) — are the two the design requires it to author.

    `max_price_tenths` is a ceiling, never a target: the order is refused
    when the live ask exceeds it, and the limit actually sent is the ask
    (bounded by this), snapped to the market's own grid.

    `p_yes_bp` is ADR 0065's precondition — typed before the price is
    revealed, stored beside the order row, never in the stopped study's log.
    """

    ticker: str = Field(min_length=1, max_length=80)
    side: str = Field(pattern=r"^(yes|no)$")
    contracts: int = Field(gt=0, le=100)
    max_price_tenths: int = Field(ge=1, le=999)
    p_yes_bp: int = Field(ge=1, le=9999)
    idempotency_key: str = Field(
        min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
    )
    #: Required, and only meaningful, on a `KXMVE` combination ticker
    #: (ADR 0073). A FIELD rather than a client-side checkbox: the whole
    #: point is that the acknowledgement cannot be skipped by a client that
    #: forgets to render it, and a default of False means a client that has
    #: never heard of combos refuses them rather than buying one silently.
    combo_acknowledged: bool = False


class OddsRefreshRequest(BaseModel):
    """What the refresh button sends: a sport, and optionally one fixture.

    Both are validated against `odds_snapshots` in the handler rather than
    trusted, because this is the one authenticated route whose whole purpose is
    to spend money at a third party. A sport key that reaches `fetch_odds`
    unchecked is a paid request for a slate that does not exist.

    `odds_event_id` is what makes the request expensive -- the props endpoint is
    billed per event per market key per region, so naming a fixture turns a
    6-credit tap into a 26-credit one. It is one fixture, never a list: a list
    is how a tap becomes the 384-credit pass of 2026-08-15, and a person
    refreshing a screen is looking at one game.
    """

    sport_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    odds_event_id: Optional[str] = Field(
        default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
    )


class EstimateRequest(BaseModel):
    """What the bet-estimate form sends: §9.2's two typed fields plus the tap.

    `stated_probability_bp` is P(YES), always -- never "probability my side
    wins". The bounds mirror the schema CHECK so a bad value is refused with a
    422 the phone can render instead of an IntegrityError it cannot.
    """

    ticker: str = Field(min_length=1, max_length=80)
    stated_probability_bp: int = Field(ge=1, le=9999)
    # REQUIRED at the API, not just enforced by the form's disabled input.
    # "Never trust that the UI disabled a button" is this repo's own rule, and
    # the question must be answered BEFORE the number exists (§9.2) -- a
    # payload arriving without it answered is a payload that skipped the
    # ordering the study depends on. The schema column stays nullable because
    # §9.4 reserves the right to cut the field entirely.
    had_already_opened_kalshi: int = Field(ge=0, le=1)
    estimate_client_ms: Optional[int] = None


class EstimateRevisionRequest(BaseModel):
    """§7.4's correction path: a reason, and nothing editable."""

    reason: str = Field(min_length=1, max_length=500)


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


class ParlayLookupLeg(BaseModel):
    event_ticker: str
    market_ticker: str


class ParlayLookupRequest(BaseModel):
    """One "Price on Kalshi" tap (ADR 0070). The legs are echoed back so the
    server can refuse a card the slate has drifted away from -- a lookup
    mints a real market and must price the card the user actually saw."""

    card_key: str
    stake_cents: int = Field(default=500, gt=0, le=100_000)
    legs: list[ParlayLookupLeg] = Field(min_length=2)


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
                "e.title AS event_title, e.commence_ms, l.league "
                "FROM recommendations r "
                "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
                "LEFT JOIN kalshi_events e ON e.event_ticker = m.event_ticker "
                "LEFT JOIN event_links l ON l.id = r.link_id "
                f"WHERE {_BASIS_SQL} >= ? "
                f"ORDER BY r.suggested_contracts DESC, {_BASIS_SQL} DESC, r.id DESC "
                "LIMIT ?",
                (since, limit),
            ).fetchall()

        surfaced, expired, suppressed, no_edge = [], [], [], []
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
        anchor_row = conn.execute(
            f"SELECT MAX({_BASIS_SQL}) AS anchor_ms, COUNT(*) AS total "
            "FROM recommendations r"
        ).fetchone()
        anchor = None if anchor_row["anchor_ms"] is None else int(anchor_row["anchor_ms"])
        recorded_total = int(anchor_row["total"] or 0)
        since = None if anchor is None else anchor - SLATE_WINDOW_MS

        rows, in_window = [], 0
        if since is not None:
            in_window = int(
                conn.execute(
                    f"SELECT COUNT(*) AS n FROM recommendations r "
                    f"WHERE {_BASIS_SQL} >= ?",
                    (since,),
                ).fetchone()["n"]
            )
            rows = conn.execute(
                "SELECT r.*, m.title AS market_title, m.yes_side_team, "
                "       m.volume_24h, m.open_interest, "
                "       e.title AS event_title, e.commence_ms, "
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
                f"WHERE {_BASIS_SQL} >= ? "
                f"ORDER BY r.suggested_contracts DESC, {_BASIS_SQL} DESC, r.id DESC "
                "LIMIT ?",
                (since, limit),
            ).fetchall()

        # One `book_quotes_for_event` read per fixture, not per row. A slate has
        # roughly two rows per fixture (both sides of a moneyline), so caching
        # halves the reads -- and, more importantly, guarantees both sides of a
        # game are placed against the *same* stored sweep. Reading twice could
        # straddle a sweep boundary and put two rows of one game against two
        # different book sets, which would look like disagreement between the
        # sides rather than between the reads.
        book_cache: dict[str, object] = {}
        items, off_basis, with_books = [], 0, 0
        # Grouping key for the picks block below: the odds fixture, which the
        # serialised item deliberately does not carry. Falls back to the event
        # title so an unlinked row still groups with its own game rather than
        # forming a phantom one per row.
        picks_source: list[tuple[str, dict]] = []
        for row in rows:
            item = _serialise(row, now_ms=now, staleness=staleness)
            if since is not None and item["freshness_measured_from_ms"] < since:
                off_basis += 1
                continue
            picks_source.append(
                (row["odds_event_id"] or item["event_title"] or item["ticker"], item)
            )

            # Same fact and same refusal as the Board's: the link's sport key,
            # `None` on an unlinked row.
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
        items.sort(
            key=lambda r: (
                r["commence_ms"] is None,
                r["commence_ms"] or 0,
                -(r["edge_tenths"] or 0),
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
        freshest_yes: dict[str, tuple[str, dict]] = {}
        all_games: set[str] = set()
        for game_key, item in picks_source:
            all_games.add(game_key)
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

        return {
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
                "older_than_window": max(0, recorded_total - in_window),
            },
            "drift_window_ms": DRIFT_WINDOW_MS,
            # Read by the screen and printed there. It is the sentence that
            # stops every column on this page being read as a signal.
            "note": (
                "None of these factors has been scored against an outcome. "
                "They are recorded so they can be, and combined into nothing."
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
            desk_window=odds.desk_window_utc,
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
            "l.odds_event_id, "
            "o.commence_ms, o.home_team, o.away_team, o.sport_key "
            "FROM recommendations r "
            "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
            "LEFT JOIN kalshi_events e ON e.event_ticker = m.event_ticker "
            "LEFT JOIN fair_prices f ON f.id = r.fair_price_id "
            "LEFT JOIN event_links l ON l.id = r.link_id "
            "LEFT JOIN ( "
            "    SELECT odds_event_id, MIN(commence_ms) AS commence_ms, "
            "           home_team, away_team, sport_key "
            "    FROM odds_snapshots GROUP BY odds_event_id "
            ") o ON o.odds_event_id = l.odds_event_id "
            "WHERE r.ticker = ? ORDER BY r.created_ms DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"No data for {ticker}")

        # `now_ms`/`staleness` make the ages live rather than frozen at write
        # time: without them a 6pm quote still reads "30s ago" at 11pm, on the
        # one screen with no list of fresher rows beside it to give the lie.
        now = db.now_ms()
        detail = _serialise(row, now_ms=now, staleness=staleness)
        detail["volume_24h"] = row["volume_24h"]
        detail["open_interest"] = row["open_interest"]
        detail["close_ms"] = row["close_ms"]
        detail["market_status"] = row["market_status"]
        detail["home_team"] = row["home_team"]
        detail["away_team"] = row["away_team"]
        detail["league"] = row["sport_key"]
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

    def _resolve_scout_fixture(conn, ticker: str) -> Optional[dict]:
        """Who plays whom, from the linked sportsbook fixture. `None` if unlinked.

        Teams, league and start come from `odds_snapshots`, never from Kalshi:
        `kalshi_events.commence_ms` is the raw `occurrence_datetime`, ~3 hours
        late on game series (ADR 0006), and Kalshi titles do not carry a
        home/away split at all. A ticker with no linked fixture cannot be
        scouted -- the desk would not know which two clubs to cover -- and that
        refusal is honest rather than a guess from parsing a ticker string.
        """
        link = conn.execute(
            "SELECT l.odds_event_id, e.title AS event_title "
            "FROM recommendations r "
            "JOIN event_links l ON l.id = r.link_id "
            "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
            "LEFT JOIN kalshi_events e ON e.event_ticker = m.event_ticker "
            "WHERE r.ticker = ? "
            "ORDER BY r.created_ms DESC, r.id DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        if not link:
            return None
        # SQLite's bare-column rule: with a lone MIN() aggregate, the bare
        # columns come from the row that achieved the minimum -- the earliest
        # snapshot, whose team names are as good as any (they never change
        # within one fixture).
        fixture = conn.execute(
            "SELECT home_team, away_team, sport_key, "
            "       MIN(commence_ms) AS commence_ms "
            "FROM odds_snapshots WHERE odds_event_id = ?",
            (link["odds_event_id"],),
        ).fetchone()
        if not fixture or fixture["home_team"] is None:
            return None
        title = link["event_title"] or (
            f"{fixture['away_team']} at {fixture['home_team']}"
        )
        return {
            "event_title": title,
            "league": fixture["sport_key"],
            "home_team": fixture["home_team"],
            "away_team": fixture["away_team"],
            "commence_ms": fixture["commence_ms"],
        }

    # A `running` row older than this is reported as gone quiet: the process
    # that owned it cannot come back to finish it after a restart, and a row
    # that looks alive forever would pin the button in its spinner state.
    SCOUT_DESK_PATIENCE_MS = 15 * 60 * 1000

    async def _run_scout_desk(row_id: int, config: AgentConfig, fixture: dict,
                              ticker: str) -> None:
        """The background half of one convening. Owns its own connection.

        Runs on the API process's event loop after the POST has already
        returned 202, so nothing here may raise out: every failure ends in the
        row being marked `failed`, because a briefing that dies silently is
        indistinguishable from one still running.
        """
        conn = db.open_db(app_config.db_path)
        try:
            budget = AgentBudget.from_config(conn, config)
            client = build_client(config)
            commence_iso = (
                datetime.fromtimestamp(
                    fixture["commence_ms"] / 1000, tz=timezone.utc
                ).isoformat()
                if fixture["commence_ms"] is not None
                else None
            )
            result = await asyncio.wait_for(
                scout_desk.convene_desk(
                    client,
                    config,
                    budget,
                    ticker=ticker,
                    event_title=fixture["event_title"],
                    league=fixture["league"],
                    commence_iso=commence_iso,
                    home_team=fixture["home_team"],
                    away_team=fixture["away_team"],
                    now_ms=db.now_ms(),
                ),
                # The desk is three web-searching calls; the longest plausible
                # convening is minutes. Ten is a backstop, not a target.
                timeout=600,
            )
            staff_json = json.dumps(
                [
                    {
                        "role": note.role,
                        "team": note.team,
                        "report": (
                            None
                            if note.report is None
                            else note.report.model_dump()
                        ),
                    }
                    for note in result.staff
                ]
            ) if result.staff else None
            briefing_json = (
                result.briefing.model_dump_json()
                if result.briefing is not None
                else None
            )
            # NULL when the seat filed nothing — never `{}`. The absence
            # reason is logged at convening time and not stored: on read,
            # "predates the seat" and "filed nothing" render the same
            # honest words, and a stored reason would age into a claim
            # about a budget day long over. See ADR 0069.
            sharp_json = (
                result.sharp.model_dump_json()
                if result.sharp is not None
                else None
            )
            conn.execute(
                "UPDATE scout_briefings SET status = ?, completed_ms = ?, "
                "staff_json = ?, briefing_json = ?, sharp_json = ?, "
                "refusal_reason = ? WHERE id = ?",
                (
                    result.status,
                    db.now_ms(),
                    staff_json,
                    briefing_json,
                    sharp_json,
                    result.refusal_reason,
                    row_id,
                ),
            )
            conn.commit()
        except Exception:
            logger.exception("scout desk convening %d died", row_id)
            conn.execute(
                "UPDATE scout_briefings SET status = 'failed', "
                "completed_ms = ? WHERE id = ?",
                (db.now_ms(), row_id),
            )
            conn.commit()
        finally:
            conn.close()

    @app.post(
        "/api/scout/{ticker}",
        dependencies=[Depends(require_auth)],
        status_code=202,
    )
    async def send_scout_desk(ticker: str) -> dict:
        """Send the scout desk on one game. Four metered Anthropic calls.

        202 with a row id, never the briefing: the desk takes minutes and a
        phone must not hold a request open that long. The caller polls the GET.
        The answer is `accepted`, not `briefed` -- the same honesty rule as
        `/api/odds/refresh`.

        Auth is required because this route spends money (ADR 0060). The spend
        itself is bounded server-side by `AgentBudget` against the same
        `agent_calls` day the Skeptic draws from, so the cookie-holding client
        cannot raise the ceiling however many times it taps.
        """
        config = AgentConfig.from_env()
        if config is None:
            raise HTTPException(
                status_code=503,
                detail="No ANTHROPIC_API_KEY configured, so the desk cannot "
                       "be paid. This is a configuration state, not a refusal.",
            )
        write_conn = db.open_db(app_config.db_path)
        try:
            fixture = _resolve_scout_fixture(write_conn, ticker)
            if fixture is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"{ticker} has no linked sportsbook fixture, so the "
                           f"desk cannot tell which two clubs to cover. Only "
                           f"games the matcher linked can be scouted.",
                )
            now = db.now_ms()
            running = write_conn.execute(
                "SELECT id FROM scout_briefings WHERE ticker = ? "
                "AND status = 'running' AND requested_ms > ? LIMIT 1",
                (ticker, now - SCOUT_DESK_PATIENCE_MS),
            ).fetchone()
            if running:
                raise HTTPException(
                    status_code=409,
                    detail="The desk is already out on this game. One "
                           "convening at a time; poll for its briefing.",
                )
            # Refuse before writing anything, so a tap against an exhausted
            # day answers immediately and spends nothing -- the same check the
            # desk itself makes (searches worst case included, v17), done
            # early where the phone can see it.
            budget = AgentBudget.from_config(write_conn, config)
            reason = budget.refusal_reason(
                2,
                now,
                searches_worst_case=scout_desk.STAFF_PAIR_SEARCHES_WORST_CASE,
            )
            if reason is not None:
                raise HTTPException(status_code=429, detail=reason)
            cursor = write_conn.execute(
                "INSERT INTO scout_briefings (ticker, event_title, league, "
                "home_team, away_team, commence_ms, requested_ms, status, "
                "model) VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?)",
                (
                    ticker,
                    fixture["event_title"],
                    fixture["league"],
                    fixture["home_team"],
                    fixture["away_team"],
                    fixture["commence_ms"],
                    now,
                    config.model,
                ),
            )
            write_conn.commit()
            row_id = int(cursor.lastrowid)
        finally:
            write_conn.close()
        asyncio.create_task(_run_scout_desk(row_id, config, fixture, ticker))
        return {"accepted": True, "id": row_id}

    @app.get("/api/scout")
    def scout_desk_overview(conn=Depends(get_conn)) -> dict:
        """The desk's own screen: recent briefings, and today's metered spend.

        The spend block is the v17 token meter made phone-readable -- the one
        place Joe can see what the desk has cost TODAY before sending it
        again, in the three units that actually bill: calls, web searches,
        tokens. Counts, never dollars (`AgentSpendSummary` has the argument:
        the per-token rate in this repo is assumed, not invoiced).
        `calls_unmetered` is the number of today's calls whose usage never
        came back -- the sums do not cover them, and saying so beats a
        confident undercount. `spend` is None when no ANTHROPIC_API_KEY is
        configured (the demo): the desk does not exist there, and a row of
        zeroes would claim a meter where there is no account to meter.

        Briefing rows are summaries only -- status and identity, no
        `staff_json`/`briefing_json` -- because this screen answers "what has
        the desk done and what did it cost", and the briefing itself is read
        on the game's own screen via `GET /api/scout/{ticker}`.
        """
        rows = conn.execute(
            "SELECT id, ticker, event_title, league, home_team, away_team, "
            "commence_ms, requested_ms, completed_ms, status, refusal_reason, "
            "model, briefing_json IS NOT NULL AS has_briefing "
            "FROM scout_briefings ORDER BY requested_ms DESC, id DESC LIMIT 50"
        ).fetchall()
        now = db.now_ms()
        briefings = []
        for row in rows:
            gone_quiet = (
                row["status"] == "running"
                and now - row["requested_ms"] > SCOUT_DESK_PATIENCE_MS
            )
            briefings.append(
                {
                    "id": row["id"],
                    "ticker": row["ticker"],
                    "event_title": row["event_title"],
                    "league": row["league"],
                    "home_team": row["home_team"],
                    "away_team": row["away_team"],
                    "commence_ms": row["commence_ms"],
                    "requested_ms": row["requested_ms"],
                    "completed_ms": row["completed_ms"],
                    "status": row["status"],
                    "gone_quiet": gone_quiet,
                    "refusal_reason": row["refusal_reason"],
                    "has_briefing": bool(row["has_briefing"]),
                }
            )
        config = AgentConfig.from_env()
        spend = None
        if config is not None:
            summary = AgentBudget.from_config(conn, config).today_summary(now)
            spend = {
                "calls_today": summary.calls_today,
                "calls_daily_budget": summary.daily_budget,
                "searches_today": summary.searches_today,
                "searches_daily_budget": summary.searches_daily_budget,
                "tokens_today": summary.tokens_today,
                "tokens_daily_budget": summary.tokens_daily_budget,
                "calls_unmetered_today": summary.calls_unmetered_today,
                "day_start_ms": summary.day_start_ms,
            }
        return {"briefings": briefings, "spend": spend}

    @app.get("/api/scout/{ticker}")
    def scout_briefing(ticker: str, conn=Depends(get_conn)) -> dict:
        """The latest briefing for one game, or the honest absence of one.

        Public read: a briefing is sourced sports news, not operator data.
        `state: "never_sent"` and a `running` row are different facts; a
        `running` row past the patience window gains `gone_quiet: true`
        because the process that owned it cannot finish it after a restart.
        """
        row = conn.execute(
            "SELECT * FROM scout_briefings WHERE ticker = ? "
            "ORDER BY requested_ms DESC, id DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        if not row:
            return {"state": "never_sent"}
        gone_quiet = (
            row["status"] == "running"
            and db.now_ms() - row["requested_ms"] > SCOUT_DESK_PATIENCE_MS
        )
        return {
            "state": "sent",
            "id": row["id"],
            "status": row["status"],
            "gone_quiet": gone_quiet,
            "ticker": row["ticker"],
            "event_title": row["event_title"],
            "league": row["league"],
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "commence_ms": row["commence_ms"],
            "requested_ms": row["requested_ms"],
            "completed_ms": row["completed_ms"],
            "refusal_reason": row["refusal_reason"],
            "staff": json.loads(row["staff_json"]) if row["staff_json"] else None,
            "briefing": (
                json.loads(row["briefing_json"]) if row["briefing_json"] else None
            ),
            # Willy Balters' take (ADR 0069). `null` on a briefing that
            # predates the seat or where the seat filed nothing — the
            # screen renders the absence in words, never an empty card.
            "sharp": (
                json.loads(row["sharp_json"]) if row["sharp_json"] else None
            ),
            "model": row["model"],
        }

    @app.get("/api/bets")
    def bets(conn=Depends(get_conn), limit: int = Query(200, le=1000)) -> dict:
        """Joe's own settled bets, from the venue's settlement mirror.

        The first screen of the betting desk (ADR 0062, partner item 1):
        `venue_settlements` has been mirrored since 2026-08-18 and nothing
        ever read it back to him. Public read for the same reason the ledger
        is -- on live the middleware gates every route, and the demo's table
        is empty by construction (the poller needs credentials).

        Honesty contract, enforced in `backend/bets.py`: per-row net uses the
        one registered settlement formula (A2), a row that cannot carry it is
        None -- never 0 -- and the totals say how many rows they exclude.
        This endpoint never touches `bet_estimates`; the estimate log stays
        embargoed (Amendment 2 stopped the study without result).

        `open_positions` rides here as well as on the slate because /bets is
        the money-record screen and settled rows alone hide what is at risk
        right now -- the largest hole of the 2026-08-22 review.
        """
        payload = bets_module.bets_record(conn, limit=limit)
        now = db.now_ms()
        payload["open_positions"] = bets_module.open_positions(conn, now_ms=now)
        # The "not tonight" release, so /bets can render the same one-tap
        # control the slate carries (slice B5): the record screen with the
        # biggest red number in the product is where the impulse to chase
        # lives, and the control belongs beside it. Same table, same clock
        # as the slate's tonight block -- one source, two screens.
        payload["lockout_until_ms"] = bet_estimates.lockout_until(
            conn, now_ms=now
        )
        # The pass count (slice B6): the headline's unit becomes decisions,
        # not bets placed. Counts only, from `desk_passes` -- never joined
        # to outcomes, never rated.
        payload["passes"] = desk_passes.pass_summary(conn)
        return payload

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
            # **`commence_ms` is the sportsbook's clock, never Kalshi's.** Until
            # 2026-08-21 this route joined nothing that carries a start time,
            # yet `_serialise` emitted the key anyway, so every row read
            # `commence_ms: null` and a consumer could not distinguish "never
            # joined" from "event unknown". The join deliberately does NOT go
            # through `kalshi_events.commence_ms`: that column stores
            # `occurrence_datetime` raw, which on game series is the expected
            # *end* -- about three hours late (ADR 0006) -- and this route is
            # the registered evidence route, where pre/post-commence bucketing
            # is exactly the axis a three-hour error poisons. `MIN` over the
            # fixture's snapshots is the scorer's own definition
            # (`backend/scoring.py:markets_awaiting_scoring`), so the ledger's
            # bucketing axis and the machinery that writes the clv fields agree
            # on when a game started. LEFT JOINs, so a row with no link or no
            # snapshot resolves to `None`, never a substitute.
            "SELECT r.*, "
            "       f.p_multiplicative, f.p_additive, f.p_power, f.p_shin, "
            "       f.p_conservative, "
            "       f.market_width, f.book_count, f.books_used, "
            "       f.anchored_on_sharp, "
            "       o.commence_ms "
            "FROM recommendations r "
            "LEFT JOIN fair_prices f ON f.id = r.fair_price_id "
            "LEFT JOIN event_links l ON l.id = r.link_id "
            "LEFT JOIN ( "
            "    SELECT odds_event_id, MIN(commence_ms) AS commence_ms "
            "    FROM odds_snapshots GROUP BY odds_event_id "
            ") o ON o.odds_event_id = l.odds_event_id "
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

    # -- parlay desk (ADR 0070) --------------------------------------------

    @app.get("/api/parlays")
    def parlays(conn=Depends(get_conn)) -> dict:
        """The ladder: three parlay cards at FAIR value, worded server-side.

        A read of the same devigged consensus the slate serves, reshaped into
        the venue's own combination product -- a betting-desk feature (ADR
        0062), not an edge claim. Nothing here computes a breakeven, an EV, or
        a size (`tests/test_parlays_api.py` walks the keys); Kalshi's actual
        quote for a card is read only by the lookup path, off the minted
        market's order book, and is never blended into these numbers.

        Refuses in words, never by omission: a card the slate cannot fill
        carries `not_built_reason`, and every excluded leg is counted by
        reason in `excluded`.
        """
        now = db.now_ms()
        return build_ladder_payload(
            conn,
            now_ms=now,
            max_odds_age_ms=staleness.max_odds_age_s * 1000,
        )

    @app.post("/api/parlays/lookup", dependencies=[Depends(require_auth)])
    async def parlay_lookup(request: ParlayLookupRequest) -> dict:
        """Mint the card's combo on Kalshi and price it off its own book.

        Auth-gated: the POST creates a real market on the exchange (no money
        moves -- exactly what the app does when a user taps legs -- but it is
        an outward-facing write, and combo lookups are the one such write on
        the authorized-actions list). Synchronous: two REST calls, seconds.

        Refusals are words, never guesses: a drifted card is 409, a missing
        collection or an empty book comes back as a status the screen renders
        honestly, and every attempt -- priced, empty, refused, error -- is a
        `parlay_lookups` row.
        """
        try:
            api = combo_api()
        except ConfigError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"no Kalshi credentials on this instance: {exc}",
            ) from exc

        now = db.now_ms()
        # Its own writable connection, like every mutating route: `get_conn`
        # is deliberately read-only, and this route records a `parlay_lookups`
        # row for every outcome. Async route, one coroutine, one thread.
        write_conn = db.open_db(app_config.db_path)
        try:
            return await price_card_on_kalshi(
                write_conn,
                card_key=request.card_key,
                stake_cents=request.stake_cents,
                requested_legs=[
                    (l.event_ticker, l.market_ticker) for l in request.legs
                ],
                now_ms=now,
                max_odds_age_ms=staleness.max_odds_age_s * 1000,
                api=api,
            )
        except LookupRefused as exc:
            raise HTTPException(
                status_code=exc.status_code, detail=exc.detail
            ) from exc
        finally:
            write_conn.close()

    @app.get("/api/odds/refreshable")
    def refreshable(conn=Depends(get_conn)) -> dict:
        """What the refresh button may buy, and what each purchase costs.

        Its own route rather than fields on `/api/slate` or `/api/board`. Those
        two payloads are pinned by four tests that stop anything on them
        becoming a composite, and a fixture list keyed for *spending* has no
        business travelling beside rows keyed for *reading* -- they answer
        different questions and would gain each other's callers.

        **The costs come from the deployed market and region lists**, computed
        here through `sweep_cost`, which is the same function the planner
        reserves with and the client bills against. A screen that arithmetics
        its own `6` passes happily while the deployment says otherwise, which is
        exactly how the prop bill was estimated at ten a fixture and came in at
        twenty.

        Read-only and unauthenticated-in-itself: it names prices and fixtures,
        both of which are already on `/api/slate`. The spend is behind
        `POST /api/odds/refresh`, which requires the token.
        """
        now = db.now_ms()
        horizon_ms = 24 * 3_600_000
        rows = conn.execute(
            "SELECT DISTINCT o.sport_key, o.odds_event_id, o.commence_ms, "
            "o.home_team, o.away_team FROM odds_snapshots o "
            "WHERE o.commence_ms >= ? AND o.commence_ms <= ? "
            "ORDER BY o.commence_ms",
            (now, now + horizon_ms),
        ).fetchall()

        team_credits = sweep_cost(odds.markets, odds.regions)
        prop_credits = sweep_cost(prop_market_keys(), odds.regions)
        # The same construction the POST refuses with, never a second count.
        budget_state = CreditBudget(
            conn,
            daily_budget=odds.daily_credit_budget,
            monthly_budget=odds.monthly_credit_budget,
            day_start_hour=odds.budget_day_start_utc_hour,
        ).state(now)
        by_sport: dict[str, list[dict]] = {}
        for row in rows:
            by_sport.setdefault(row["sport_key"], []).append(
                {
                    "odds_event_id": row["odds_event_id"],
                    "commence_ms": row["commence_ms"],
                    # The books' own names, so the button and the row a person
                    # is looking at say the same thing. Kalshi's title would be
                    # a different string for the same game.
                    "title": f"{row['away_team']} at {row['home_team']}",
                }
            )

        return {
            "sports": [
                {
                    "sport_key": sport,
                    "team_credits": team_credits,
                    # What a *prop* tap costs in total: the fixture's props plus
                    # the team call that finds it. `fetch_and_store_props` is
                    # only ever reached from a served team sweep, so quoting the
                    # prop half alone would understate every tap.
                    "prop_credits": team_credits + prop_credits,
                    "fixtures": fixtures,
                }
                for sport, fixtures in sorted(by_sport.items())
            ],
            # Surfaced so a screen can say what it is protecting rather than
            # only reporting a refusal after the fact.
            "manual_daily_credits": ondemand.DEFAULT_MANUAL_DAILY_CREDITS,
            # The spend so far, through the same file and the same arithmetic
            # `submit` refuses against, so the panel can say "12 of 150 left"
            # instead of restating the ceiling. Over-counts by design: a tap is
            # counted when it is accepted, served or not.
            "manual_credits_spent_today": ondemand.manual_spent_today(
                ondemand.inbox_path(app_config.db_path),
                now,
                day_start_hour=odds.budget_day_start_utc_hour,
            ),
            # The whole day's budget beside the taps' slice of it. `remaining`
            # is `BudgetState.remaining_today` -- computed by the planner since
            # the beginning and exposed nowhere until now, which left the panel
            # quoting a constant where a person was deciding whether to spend.
            "day_credits_spent": budget_state.spent_today,
            "day_credits_budget": budget_state.daily_budget,
            "day_credits_remaining": budget_state.remaining_today,
            "cooldown_ms": ondemand.DEFAULT_COOLDOWN_MS,
            "note": (
                "A refresh buys a fresh price. It does not make a row bettable "
                "and cannot produce an edge that was not there."
            ),
        }

    # -- write routes ------------------------------------------------------

    @app.post("/api/odds/refresh", dependencies=[Depends(require_auth)])
    def refresh_odds(request: OddsRefreshRequest, conn=Depends(get_conn)) -> dict:
        """Buy fresh sportsbook odds now, because someone is looking at the screen.

        **Why a screen needs this at all.** `_live_ages` re-checks the stored
        consensus against *now* on every read, so `actionable` goes false
        `MAX_ODDS_AGE_S` after the sweep that priced the row -- whatever the row
        looked like when it was written. The rolling refresh (ADR 0030) holds
        that open across a planned kickoff cluster, which is the hour before
        first pitch and nothing else. Open the cockpit two hours out and the
        whole slate is struck through on a clock rather than on a price. This is
        the button that answers that, and it is the only path by which a person
        rather than the planner causes a credit to be spent.

        **It does not fetch anything.** This process opens the database
        read-only and is not the process that holds the odds client -- see
        `docker/entrypoint.sh`, which runs the API and the chain runner
        separately. The request is written to a file the runner reads on its
        ~15s cadence, so the answer here is *accepted*, never *served*. Saying
        "refreshed" in this response would be a claim about a call that has not
        been made yet and may still be refused on budget.

        Every ceiling is `ondemand.submit`'s, and the budget one is read through
        `CreditBudget` -- the same implementation the planner spends against,
        never a second count of the day.

        202, not 200: the work is accepted for later. A refusal is 200 with
        `accepted: false` and the reason in words, because a cooldown or a
        ceiling is a normal answer to a reasonable tap and a 4xx would have the
        UI render it as a fault.
        """
        now = db.now_ms()
        horizon_ms = 24 * 3_600_000
        fixtures = conn.execute(
            "SELECT DISTINCT odds_event_id FROM odds_snapshots "
            "WHERE sport_key = ? AND commence_ms >= ? AND commence_ms <= ?",
            (request.sport_key, now, now + horizon_ms),
        ).fetchall()
        known = {row["odds_event_id"] for row in fixtures}
        if not known:
            # Not 404. The sport may be perfectly real and simply have no
            # fixture inside the day -- refusing with the reason is more use on
            # a phone than a status code, and it is the same shape as every
            # other refusal this endpoint returns.
            return {
                "accepted": False,
                "detail": (
                    f"no {request.sport_key} fixture is stored inside the next "
                    f"24 hours, so a refresh would buy a slate with nothing to "
                    f"price against"
                ),
                "estimated_credits": 0,
                "retry_after_ms": 0,
            }
        if request.odds_event_id is not None and request.odds_event_id not in known:
            return {
                "accepted": False,
                "detail": (
                    f"fixture {request.odds_event_id} is not a stored upcoming "
                    f"{request.sport_key} game. Props are billed per fixture, "
                    f"so this refuses rather than paying to find out."
                ),
                "estimated_credits": 0,
                "retry_after_ms": 0,
            }

        cost = ondemand.manual_cost(
            team_cost=sweep_cost(odds.markets, odds.regions),
            prop_cost_per_event=sweep_cost(prop_market_keys(), odds.regions),
            odds_event_id=request.odds_event_id,
        )
        budget = CreditBudget(
            conn,
            daily_budget=odds.daily_credit_budget,
            monthly_budget=odds.monthly_credit_budget,
            day_start_hour=odds.budget_day_start_utc_hour,
        )
        submission = ondemand.submit(
            ondemand.inbox_path(app_config.db_path),
            sport_key=request.sport_key,
            odds_event_id=request.odds_event_id,
            now_ms=now,
            estimated_credits=cost,
            budget_refusal=budget.refusal_reason(cost, now),
            day_start_hour=odds.budget_day_start_utc_hour,
        )
        return {
            "accepted": submission.accepted,
            "detail": submission.detail,
            "estimated_credits": submission.estimated_credits,
            "retry_after_ms": submission.retry_after_ms,
        }

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

    # -- the calibration bet log (registration 2026-08-17, as amended) -------

    @app.get("/api/estimates/markets")
    def estimate_market_search(
        q: str = Query(default="", max_length=80), conn=Depends(get_conn)
    ) -> dict:
        """The one-tap picker's search. Serves no prices, by construction.

        `search_markets` selects no quote column, so this route cannot leak
        the number the anchoring tripwires exist to measure.
        """
        query = q.strip()
        if len(query) < 2:
            return {"markets": []}
        return {
            "markets": bet_estimates.search_markets(
                conn, query, now_ms=db.now_ms()
            )
        }

    @app.get("/api/estimates/recent")
    def estimate_recent(conn=Depends(get_conn)) -> dict:
        """The last few entries, embargo-safe columns only.

        What Joe typed is not embargoed from Joe; what the server captured at
        estimate time is, until the registered stop. The column list lives in
        `estimates._SAFE_COLUMNS` and the test suite asserts the quote never
        appears here.
        """
        return {"estimates": bet_estimates.recent_estimates(conn)}

    @app.get("/api/estimates/stop")
    def estimate_money_arm(conn=Depends(get_conn)) -> dict:
        """The money arm's position: "$X of $100", for the /estimate strip.

        Embargo-safe by A7's explicit ruling (and the partner's, 2026-08-18):
        §5 forbids aggregates over *the estimate log*; this is a sum over
        `venue_settlements` -- Joe's own money, visible in the Kalshi app
        regardless -- and reads no estimate row. The guard that IS real:
        nothing here may be attributed to logged bets, split into a win rate,
        or scoped to the study population. One wallet number, nothing else.

        `loss_dollars` and `stopped` are null when the record cannot carry
        the registered formula (no study start stamped, or an unreadable
        settlement row) -- unknown is a state, not a zero, and the strip
        renders it as such.
        """
        loss = bet_estimates.study_loss_dollars(conn)
        return {
            # The registration's terminal state (Amendment 2, 2026-08-20):
            # Joe stopped the study, without result. Distinct from `stopped`
            # below, which is the $100 money arm and never fired -- the strip
            # must not render "the $100 stop has fired" for an owner stop.
            "study_state": bet_estimates.STUDY_TERMINAL_STATE,
            "stopped_by_owner_ms": bet_estimates.STUDY_STOPPED_BY_OWNER_MS,
            "loss_dollars": loss,
            "ceiling_dollars": bet_estimates.STUDY_LOSS_CEILING_DOLLARS,
            "stopped": None
            if loss is None
            else loss >= bet_estimates.STUDY_LOSS_CEILING_DOLLARS,
            # The self-lockout's release instant, or null. On this payload
            # rather than a route of its own because the strip that renders
            # the money arm is the strip that renders this -- one fetch, one
            # state, no second poller.
            "lockout_until_ms": bet_estimates.lockout_until(
                conn, now_ms=db.now_ms()
            ),
        }

    @app.post("/api/desk/lockout", dependencies=[Depends(require_auth)])
    def engage_desk_lockout(conn=Depends(get_conn)) -> dict:
        """One tap of "not tonight", on the desk's own name (2026-08-21).

        The lockout outlived the study that named its old route: it writes
        the same append-only `self_lockouts` table, keyed to the same day
        roll, and since the study stopped its value is the render -- the
        landing screen shows the note from the version of Joe that decided,
        with the release time -- plus the record of every reach for it. It
        is honest about what it cannot do: nothing here stops a hand bet in
        the Kalshi app. No parameters, no disengage, no duration picker,
        for the reasons the original gives.

        **Engaging from unlocked also appends one `desk_passes` row** (scope
        'tonight', slice B6): the tap IS the decision to pass the night, and
        one gesture should not need a second one to be counted. Guarded on
        not-already-locked because the lockout is idempotent by design -- a
        second tap is the same decision, not a second one, and must not
        inflate the pass count. Verified by disabling: pass write removed ->
        the lockout-writes-a-pass test fails; restored -> green.
        """
        del conn  # the write path opens its own handle, below
        now = db.now_ms()
        write_conn = db.open_db(app_config.db_path)
        try:
            already_locked = (
                bet_estimates.lockout_until(write_conn, now_ms=now) is not None
            )
            until_ms = bet_estimates.engage_lockout(
                write_conn,
                now_ms=now,
                day_start_hour=odds.budget_day_start_utc_hour,
            )
            if not already_locked:
                desk_passes.record_pass(
                    write_conn, now_ms=now, scope="tonight"
                )
        finally:
            write_conn.close()
        return {"locked": True, "until_ms": until_ms}

    @app.post("/api/desk/pass", dependencies=[Depends(require_auth)])
    def record_desk_pass(
        request: DeskPassRequest, conn=Depends(get_conn)
    ) -> dict:
        """Append one per-market pass (slice B6). Auth like every mutation.

        Writes `desk_passes` with the ticker as scope, uppercased to match
        every other ticker write. **Deliberately no validation against
        discovery**: a pass on a market this tool never discovered is still
        a decision Joe made, and refusing to record a real "no" because our
        own discovery missed the market is the wrong way round (the
        `venue_settlements` argument exactly). Append-only -- there is no
        edit or delete route, and the record is never scored or rated.
        """
        del conn  # the write path opens its own handle, below
        write_conn = db.open_db(app_config.db_path)
        try:
            pass_id = desk_passes.record_pass(
                write_conn,
                now_ms=db.now_ms(),
                scope=request.ticker.strip().upper(),
                reason=request.reason,
            )
        finally:
            write_conn.close()
        return {"recorded": True, "id": pass_id}

    @app.post("/api/desk/attention", dependencies=[Depends(require_auth)])
    def record_desk_attention(conn=Depends(get_conn)) -> dict:
        """Someone has the desk open. Auth like every mutation.

        **This is the input the odds feed follows** (ADR 0071 §2.6). The fixed
        `ODDS_DESK_WINDOW_UTC` bought a sweep every ten minutes for twelve hours
        a day whether or not anyone was looking; a stamp here is what now tells
        `decide_sweeps` that the ten-minute cadence is worth paying for.

        **The time is the server's, never the caller's**, and the route takes no
        body at all rather than an optional one. A client-supplied timestamp is
        a number the caller chooses, and the only value worth choosing is a
        future one -- which would hold the desk open past its own TTL. There is
        nothing a body could carry that this route should trust.

        No rate limit, deliberately. The ceiling that matters is the attention
        daily credit slice in `odds/timing.py`, which sits where the money is
        actually spent; a limit here would be a second and weaker copy of it.
        See the route handler in `frontend/src/app/desk-attention/route.ts`,
        which carries the same argument at more length.
        """
        del conn  # the write path opens its own handle, below
        write_conn = db.open_db(app_config.db_path)
        try:
            attention.stamp(write_conn, now_ms=db.now_ms())
        finally:
            write_conn.close()
        return {"recorded": True}

    @app.post("/api/estimates/lockout", dependencies=[Depends(require_auth)])
    def engage_self_lockout(conn=Depends(get_conn)) -> dict:
        """One tap of "not tonight" (fleet convening item 10).

        **Deprecated name, working route** (2026-08-21): the lockout now
        belongs to the desk, not the stopped study -- new callers use
        `POST /api/desk/lockout`. This stays because a deployed frontend may
        still call it and both write the same table, so they cannot come to
        disagree. Delete only with a frontend audit in hand.

        Locks `POST /api/estimates` -- the action performed before every hand
        bet -- until the next day roll at the odds budget's own hour, via the
        same 423 shape the $100 stop uses. **No parameters and no disengage
        endpoint**, deliberately: a lockout with a duration picker is a
        negotiation, and one that can be cancelled is a speed bump. Tapping
        again is idempotent; the release instant is a property of the clock.

        The write needs a writable connection; `get_conn` serves the API's
        usual read-only handle, so this opens its own, exactly as
        `log_estimate` does for its write.

        The pass write mirrors `/api/desk/lockout` exactly (slice B6): a tap
        through the deprecated name is the same decision and must count the
        same, or the pass total would depend on which frontend build tapped.
        """
        now = db.now_ms()
        write_conn = db.open_db(app_config.db_path)
        try:
            already_locked = (
                bet_estimates.lockout_until(write_conn, now_ms=now) is not None
            )
            until_ms = bet_estimates.engage_lockout(
                write_conn,
                now_ms=now,
                day_start_hour=odds.budget_day_start_utc_hour,
            )
            if not already_locked:
                desk_passes.record_pass(
                    write_conn, now_ms=now, scope="tonight"
                )
        finally:
            write_conn.close()
        return {"locked": True, "until_ms": until_ms}

    @app.post("/api/estimates", dependencies=[Depends(require_auth)])
    async def log_estimate(request: EstimateRequest) -> dict:
        """Record one estimate: stamp it, capture the quote, say nothing back.

        The server fetches the market's book *at estimate time* and stores it
        for the anchoring tripwires (§7.7). **The response never carries it.**
        A quote that cannot be read is recorded as a reason string rather than
        blocking the write -- the estimate is the measurement and a transient
        network failure must not cost the row. The one refusal: a ticker
        Kalshi has permanently never heard of AND discovery has never seen,
        which can only be a typo, and an unjoinable row is worse than a retype.
        """
        # The $100 stop, checked server-side before anything else: a strip on
        # the phone is a hint to a human; this is the control. Only a
        # COMPUTABLE firing refuses -- `None` means the record cannot be read
        # (no study start, or an unreadable settlement row), and locking Joe
        # out of his own log on a broken read would punish the wrong party.
        # 423 Locked: nothing about the request is wrong; the resource is.
        # Guard verified 2026-08-18: predicate forced False -> the 423 test
        # fails; restored -> green.
        stop_conn = db.open_db(app_config.db_path, read_only=True)
        try:
            stop_loss = bet_estimates.study_loss_dollars(stop_conn)
            lockout_release = bet_estimates.lockout_until(
                stop_conn, now_ms=db.now_ms()
            )
        finally:
            stop_conn.close()
        if (
            stop_loss is not None
            and stop_loss >= bet_estimates.STUDY_LOSS_CEILING_DOLLARS
        ):
            raise HTTPException(
                status_code=423,
                detail=(
                    f"The $100 money arm has fired: cumulative realised loss "
                    f"since study start is ${stop_loss:.2f} "
                    f"(registration §5 arm 3, as amended by A2). The study "
                    f"is stopped and logging is closed, permanently."
                ),
            )
        # The self-lockout, second and server-side (fleet convening item 10):
        # a disabled button is a hint to a human; this is the control. Same
        # 423 shape as the stop -- nothing about the request is wrong, the
        # resource is locked, and it unlocks itself at the day roll.
        # Guard verified by disabling: predicate forced False -> the 423
        # lockout test fails; restored -> green.
        if lockout_release is not None:
            release_iso = datetime.fromtimestamp(
                lockout_release / 1000, timezone.utc
            ).strftime("%H:%M UTC on %Y-%m-%d")
            raise HTTPException(
                status_code=423,
                detail=(
                    f"You locked yourself out until {release_iso}. Nothing "
                    f"is wrong with the request; you asked not to be able to "
                    f"do this tonight, and there is no early unlock."
                ),
            )

        stamped = db.now_ms()
        ticker = request.ticker.strip().upper()
        yes_bid = yes_ask = observed = None
        unreadable: Optional[str] = None
        permanently_unknown = False
        try:
            quote = await live_quotes().fetch(ticker, observed_ms=stamped)
        except ConfigError as exc:
            unreadable = f"no Kalshi credentials at estimate time: {exc}"
        except QuoteUnavailable as exc:
            unreadable = str(exc)
            permanently_unknown = exc.permanent
        else:
            yes_bid = quote.market.yes_bid_tenths
            yes_ask = quote.ask_tenths("yes")
            observed = quote.observed_ms

        if permanently_unknown:
            conn = db.open_db(app_config.db_path, read_only=True)
            try:
                known = bet_estimates.market_context(conn, ticker) != (None, None)
                discovered = conn.execute(
                    "SELECT 1 FROM kalshi_markets WHERE ticker = ?", (ticker,)
                ).fetchone()
            finally:
                conn.close()
            if not discovered and not known:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Kalshi has never heard of {ticker!r} and neither "
                        f"has discovery. Check the ticker and retype it -- "
                        f"an estimate nothing can join to is not a record."
                    ),
                )

        row_id = await run_in_threadpool(
            _write_estimate,
            app_config.db_path,
            ticker=ticker,
            stated_probability_bp=request.stated_probability_bp,
            estimate_server_ms=stamped,
            had_already_opened_kalshi=request.had_already_opened_kalshi,
            estimate_client_ms=request.estimate_client_ms,
            server_yes_bid_tenths=yes_bid,
            server_yes_ask_tenths=yes_ask,
            server_quote_observed_ms=observed,
            server_quote_unreadable_reason=unreadable,
        )
        # Deliberately quote-free. Rendering the captured book here would hand
        # the anchoring reference to the person being measured (§7.7).
        return {
            "id": row_id,
            "ticker": ticker,
            "stated_probability_bp": request.stated_probability_bp,
            "estimate_server_ms": stamped,
        }

    @app.post(
        "/api/estimates/{estimate_id}/revise",
        dependencies=[Depends(require_auth)],
    )
    async def revise_estimate_route(
        estimate_id: int, request: EstimateRevisionRequest
    ) -> dict:
        """Flag an estimate as mistyped. Append-only; nothing is edited.

        The probability itself cannot be changed by anyone -- the schema
        trigger rejects the UPDATE below the route layer. This records the
        reason and sets the revised flag, which excludes the row (§2). The
        corrected estimate is a new row through `log_estimate`, with fresh
        clocks and a fresh quote.
        """
        done = await run_in_threadpool(
            _revise_estimate,
            app_config.db_path,
            estimate_id,
            reason=request.reason,
            revised_ms=db.now_ms(),
        )
        if not done:
            raise HTTPException(
                status_code=404, detail=f"no estimate with id {estimate_id}"
            )
        return {"revised": estimate_id}

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
        """
        return ticker.strip().upper().startswith("KXMVE")

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
        cap_dollars: float,
        *,
        ticker: str,
        side: str,
        ask_tenths: int,
        price_grid,
        hard_cap: int = MANUAL_ORDER_MAX_CONTRACTS,
    ) -> int:
        """The largest count whose fee-inclusive worst case fits the per-bet
        cap. Counted by construction rather than divided, because the fee
        rounds up on the whole order and a division would overstate by up to
        one contract in exactly the direction a cap must not err.

        `hard_cap` defaults to the path's own ceiling (ADR 0063: "first at a
        1-contract ceiling, raised only when observed `fee_actual` matches
        `fee_predicted` on real fills"), so the loop can never authorise a
        size the route would then refuse. Combination tickets are bounded to
        one contract on top of that, and priced through the hedged combo fee
        rather than `calculate_fee` -- ADR 0073, and ADR 0046's tripwire is
        why: on a combo the deployed model is known wrong in the optimistic
        direction, and a cap checked against an understated cost is not a
        cap.
        """
        combo = _is_combo(ticker)
        ceiling = min(hard_cap, COMBO_MAX_CONTRACTS if combo else hard_cap)
        authorised = 0
        for count in range(1, ceiling + 1):
            try:
                candidate = OrderRequest(
                    ticker=ticker,
                    side=side,
                    action="buy",
                    count=count,
                    limit_price_tenths=ask_tenths,
                    price_grid=price_grid,
                )
            except OrderRefused:
                break
            worst = _manual_worst_case_dollars(candidate, combo=combo)
            if worst is None or worst > cap_dollars:
                break
            authorised = count
        return authorised

    @app.get("/api/manual/market/{ticker}")
    async def manual_market(ticker: str, conn=Depends(get_conn)) -> dict:
        """The venue's live facts for ANY ticker, for the manual ticket (D1).

        The engine's `/api/market/{ticker}` is recommendation-scoped and
        404s on a ticker the engine never priced; a hand bettor's market is
        whatever the venue lists. This read is quote + book only — no fair
        value, no edge, no opinion (ADR 0062).

        The ask is served alongside `p_yes_required: true` so the client
        knows to mask it until the estimate is typed (ADR 0065) — but the
        MASKING is the client's courtesy; the server-side enforcement is the
        POST refusing without `p_yes_bp`.
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

        sides = {}
        for side in ("yes", "no"):
            ask = _tradeable_ask(quote.ask_tenths(side))
            depth = quote.depth_at_ask(side)
            authorised = None
            if (
                ask is not None
                and quote.price_grid is not None
                and risk_now is not None
                and risk_now.max_position_dollars is not None
            ):
                authorised = _manual_authorised_count(
                    risk_now.max_position_dollars,
                    ticker=quote.ticker,
                    side=side,
                    ask_tenths=ask,
                    price_grid=quote.price_grid,
                )
                if depth is not None:
                    authorised = min(authorised, int(depth))
            sides[side] = {
                "ask_tenths": ask,
                "ask_display": None if ask is None else format_price(ask),
                "depth_at_ask": depth,
                # "of N authorised" — the server's ceiling, never a client
                # sum. None means it could not be derived (no balance, no
                # grid, no ask), which the ticket renders as a refusal.
                "authorised_contracts": authorised,
            }

        return {
            "ticker": quote.ticker,
            "observed_ms": quote.observed_ms,
            "reachable": unreachable is None,
            "unreachable_reason": unreachable,
            "p_yes_required": True,
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
            "cooloff_until_ms": manual_store.cooloff_until_ms(conn, now_ms=now),
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
            "combo_note": (
                "Every combination book this repo has ever read had no YES "
                "bid — 40 of 40, across three runs on two dates. You can "
                "enter this and you cannot exit it: the only way out is the "
                "outcome. The fee is priced through a hedged coefficient "
                "because the measured model undercharges on combos, so the "
                "cost shown is a ceiling and not a quote."
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
        SELECT carries no quote column at all, so ADR 0065's masking survives
        the search screen: you cannot browse for an ask, type the number it
        put in your head, and call it your estimate.

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
        # 0.
        unreachable = _manual_reachable()
        if unreachable is not None:
            raise HTTPException(status_code=403, detail=unreachable)

        # 1.
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

        # 3.
        cooloff_release = manual_store.cooloff_until_ms(conn, now_ms=now)
        if cooloff_release is not None:
            raise HTTPException(
                status_code=423,
                detail=(
                    f"The buy control is resting after your last order. It "
                    f"unlocks in {max(0, cooloff_release - now) // 1000}s. "
                    f"No override — the cool-off is the safeguard, not a "
                    f"suggestion."
                ),
            )

        ticker = request.ticker.strip().upper()

        # 4.
        combo = _is_combo(ticker)
        if combo and not request.combo_acknowledged:
            raise HTTPException(
                status_code=422,
                detail=(
                    "combination (KXMVE) markets need the acknowledgement "
                    "before this door opens: every combination book this "
                    "repo has ever read had NO YES BID — 40 of 40, across "
                    "three runs on two dates — so you can enter and you "
                    "cannot exit (ADR 0012 §5). The fee model also "
                    "undercharges on combos (ADR 0046); a hedged coefficient "
                    "prices this order and it is not a measurement of what "
                    "Kalshi charges. Send `combo_acknowledged` only if that "
                    "is the bet you mean to make."
                ),
            )
        if combo and request.contracts > COMBO_MAX_CONTRACTS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"a combination order is capped at "
                    f"{COMBO_MAX_CONTRACTS} contract on this path (ADR "
                    f"0073), against an order for {request.contracts}. The "
                    f"cap is what keeps an error in the hedged combo fee "
                    f"costing a fraction of a cent instead of scaling."
                ),
            )
        if request.contracts > MANUAL_ORDER_MAX_CONTRACTS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"this path is armed at "
                    f"{MANUAL_ORDER_MAX_CONTRACTS} contract, against an "
                    f"order for {request.contracts}. Raising it is a code "
                    f"change and it waits on observed `fee_actual` matching "
                    f"`fee_predicted` on real fills (ADR 0063)."
                ),
            )

        # 5.
        daily_pnl = bets_module.venue_daily_realised_pnl_dollars(
            conn, now_ms=now, day_start_hour=odds.budget_day_start_utc_hour
        )
        if daily_pnl is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "today's realised P&L cannot be read (the venue mirror "
                    "is stale or unpolled), so the daily-loss switch cannot "
                    "be applied. Refusing — 'cannot read the losses' must "
                    "never resolve to 'no losses' (ADR 0064)."
                ),
            )

        # 6.
        risk_now = risk
        if risk.underived:
            risk_now = risk.with_observed_balance(db.latest_balance_tenths(conn))
        if (
            risk_now is None
            or risk_now.max_position_dollars is None
            or risk_now.max_exposure_dollars is None
            or risk_now.max_daily_loss_dollars is None
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "the account balance has never been observed, so no cap "
                    "can be derived. Refusing — 'cannot determine the "
                    "bankroll' must never resolve to a typed default."
                ),
            )
        if daily_pnl <= -abs(risk_now.max_daily_loss_dollars):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"the daily-loss switch has fired: ${daily_pnl:.2f} "
                    f"realised today against a "
                    f"${risk_now.max_daily_loss_dollars:.2f} line. No more "
                    f"buys today, through this door."
                ),
            )

        # 7.
        try:
            quote = await live_quotes().fetch(ticker, observed_ms=now)
        except ConfigError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except QuoteUnavailable as exc:
            raise HTTPException(
                status_code=404 if exc.permanent else 503, detail=str(exc)
            ) from exc
        ask = _tradeable_ask(quote.ask_tenths(request.side))
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
        worst_case = _manual_worst_case_dollars(order, combo=combo)
        if worst_case is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "the fee on this order could not be computed, so its "
                    "worst-case cost cannot be checked against your per-bet "
                    "cap. Refusing — an unreadable fee must never resolve to "
                    "no fee."
                ),
            )
        if worst_case > risk_now.max_position_dollars:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{request.contracts} contracts at {format_price(ask)} "
                    f"costs at most ${worst_case:.2f}, "
                    f"over the ${risk_now.max_position_dollars:.2f} per-bet "
                    f"cap derived from your balance."
                ),
            )

        # 10. A LIVE positions read, not the 12-hour mirror. The per-row
        #     shape has never been observed (portfolio_poll counts, it does
        #     not parse), so the guard is deliberately blunt: any row naming
        #     this ticker — or any row too unreadable to name one — refuses.
        try:
            position_rows = await live_quotes().portfolio_positions()
        except (ConfigError, QuoteUnavailable) as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"could not read your open positions, so 'this buy does "
                    f"not close an existing position' cannot be verified: "
                    f"{exc}. Kalshi nets — refusing rather than guessing."
                ),
            ) from exc
        for row in position_rows:
            row_ticker = row.get("ticker") if isinstance(row, dict) else None
            if row_ticker is None or row_ticker == ticker:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "you already hold a position this order could net "
                        "against (or a position row was unreadable). Kalshi "
                        "nets buys against opposite holdings, and this "
                        "record must not book a close as an open. Manage "
                        "the existing position in the Kalshi app first."
                    ),
                )

        # 11. ADR 0018's SECOND barrier, wired here rather than left for the
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

        submitted_ms = db.now_ms()
        try:
            row_id = await run_in_threadpool(
                _write_manual_intent,
                app_config.db_path,
                order,
                dry_run=placer.dry_run,
                submitted_ms=submitted_ms,
                max_exposure_dollars=risk_now.max_exposure_dollars,
                max_price_tenths=request.max_price_tenths,
                p_yes_bp=request.p_yes_bp,
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
        except ExposureCapExceeded as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
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

        body = {
            "status": outcome.status,
            "dry_run": outcome.dry_run,
            "manual_order_id": row_id,
            "client_order_id": order.client_order_id,
            "ticker": ticker,
            "side": request.side,
            "contracts": request.contracts,
            "p_yes_bp": request.p_yes_bp,
            "limit_price_display": format_price(order.fill_price_tenths),
            "max_price_display": format_price(request.max_price_tenths),
            # "at most", never "costs $X": MLB's k is half the coefficient
            # charged, so the point figure would overstate — and never a
            # payout figure, which would assume untested H4 (ADR 0027).
            "worst_case_cost_display": f"${worst_case:.2f}",
            "kalshi_order_id": outcome.kalshi_order_id,
            "error_text": outcome.error_text,
            "cooloff_until_ms": submitted_ms + manual_store.COOLOFF_MS,
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
    """
    f = report.fit
    return {
        "computed_ms": computed_ms,
        "cache_ttl_ms": SIGNAL_CACHE_TTL_MS,
        "available": f is not None,
        "refusal": report.refusal,
        "verdict": report.verdict,
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
            "n_rows": f.n_rows,
            "interval_lower": f.lower,
            "interval_upper": f.upper,
            "multiplier": f.multiplier,
        },
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
            "edge. UNRESOLVED below 300 clusters is a real answer and is NOT "
            "'no signal'. The cluster key is COALESCE(event_ticker, ticker), "
            "which is not the gate's ADR 0029 key; the two differ materially."
        ),
    }


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


def _write_estimate(db_path, **kwargs) -> int:
    """One estimate row, on its own writable connection in a worker thread.

    Same shape as `_write_intent` below, for the same reason: the connection
    is made inside the threadpool worker that uses it, and it is short-lived
    so the write lock is held for the smallest possible window.
    """
    conn = db.open_db(db_path)
    try:
        return bet_estimates.record_estimate(conn, **kwargs)
    finally:
        conn.close()


def _revise_estimate(db_path, estimate_id: int, *, reason: str, revised_ms: int) -> bool:
    conn = db.open_db(db_path)
    try:
        return bet_estimates.revise_estimate(
            conn, estimate_id, reason=reason, revised_ms=revised_ms
        )
    finally:
        conn.close()


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

    Verified against the demo: its best-sized row is +$0.0135 with a $0.4728
    deviation, which gives 0.464.

    **The review quoted 45.6%, off a $0.2619 expectation and a $7.4778
    deviation. Those were 17 contracts at a $1,000 bankroll no instance
    deploys** -- see ADR 0041's 2026-08-18 amendment. The ratio barely moves
    because both terms scale with size; what moved is which row is "best" once
    the deployed caps flatten every size to 1.
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
