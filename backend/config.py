"""Configuration, loaded from the environment.

Every threshold and credential comes from here — nothing is hardcoded at a call
site. `.env.example` is the documented contract; on Fly these are secrets and
never touch a file.

Two rules this module enforces rather than documents:

- **A missing credential raises at load, not at first use.** A tool that starts
  cleanly and then fails on the first order is worse than one that refuses to
  start.
- **Unreadable is not zero.** A malformed numeric setting raises rather than
  falling back to a default, because a silently-defaulted risk cap is how you
  discover your exposure limit was 0 (refuse everything) or unset (refuse
  nothing) at the worst possible moment.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class ConfigError(RuntimeError):
    """Raised when configuration is missing or unusable."""


def _require(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise ConfigError(
            f"{key} is not set. Copy .env.example to .env and fill it in, or "
            f"set it with `fly secrets set {key}=...` on a deployed instance."
        )
    return value


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _int(key: str, default: int) -> int:
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key}={raw!r} is not an integer.") from exc


def _int_or_none(key: str) -> Optional[int]:
    """An integer setting whose absence is meaningful, not a zero.

    Unset means "no ceiling of our own"; `0` would mean "refuse every call".
    Collapsing those two into one value is the failure this repo keeps
    rediscovering -- see `tasks/lessons.md` on the zero that means "no
    measurement" passing every threshold.
    """
    raw = os.getenv(key, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key}={raw!r} is not an integer.") from exc


def _float(key: str, default: float) -> float:
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key}={raw!r} is not a number.") from exc


def _int_announced(key: str, default: int, *, minimum: int = 1) -> int:
    """An integer setting that **announces and falls back** instead of raising.

    The deliberate opposite of `_int`, and the exception to this module's own
    "unreadable is not zero" rule. That rule protects settings where a
    substituted value is dangerous -- a risk cap, a credential. These are
    polling cadences, where the default is safe and a raise is not: they are
    loaded by `scripts/run_loop.py`, which `docker/entrypoint.sh` supervises
    with `wait -n`, so a `ConfigError` here is a container crash loop clearable
    only with `flyctl secrets unset` -- a laptop job, and this tool is operated
    from a phone. That is exactly the composition `RETIRED_SETTINGS` records:
    "refuse to start on bad config" times "recovery needs flyctl" equals "the
    operator cannot recover from their only device".

    So nothing is guessed silently. A bad value is logged at ERROR, names the
    default it is falling back to, and the setting simply is not read.
    """
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.error(
            "%s=%r is not an integer and is not read; using the default %d.",
            key, raw, default,
        )
        return default
    if value < minimum:
        logger.error(
            "%s=%d is below the minimum %d and is not read; using the default "
            "%d.", key, value, minimum, default,
        )
        return default
    return value


def _bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{key}={raw!r} is not a boolean.")


@dataclass(frozen=True)
class KalshiConfig:
    api_key: str
    private_key_path: Path
    rest_url: str
    ws_url: str

    @classmethod
    def load(cls) -> "KalshiConfig":
        path = Path(_require("KALSHI_PRIVATE_KEY_PATH")).expanduser()
        if not path.exists():
            raise ConfigError(
                f"KALSHI_PRIVATE_KEY_PATH points at {path}, which does not exist. "
                "The key must be an RSA PEM (not ED25519) and should live "
                "outside the repo."
            )
        return cls(
            api_key=_require("KALSHI_API_KEY"),
            private_key_path=path,
            rest_url=_optional(
                "KALSHI_REST_URL", "https://api.elections.kalshi.com/trade-api/v2"
            ),
            ws_url=_optional(
                "KALSHI_WS_URL", "wss://api.elections.kalshi.com/trade-api/ws/v2"
            ),
        )


def configured_day_start_utc_hour() -> int:
    """The **one** env read of `ODDS_BUDGET_DAY_START_UTC_HOUR`, validated.

    Three different days are cut on this hour -- the odds credit budget
    (`odds/budget.py`), the risk day the daily-loss kill switch measures
    (`settlement.risk_day_start_ms`) and the Anthropic call budget
    (`agents/budget.py`) -- and every one of them has a signature that defaults
    to `odds.timing.DEFAULT_DAY_START_UTC_HOUR` when a caller forgets. A second
    parse of the same variable would drift from this one silently, which is the
    failure the whole family of `assert_*_agree` checks exists to prevent, so
    both `OddsConfig` constructors and `AgentBudget.from_config` come here.

    Raises rather than clamping an out-of-range hour, per
    `clamping-is-for-values-you-trust`: an hour is a value being *validated*,
    not one being trusted, and `hour=25` silently becoming 23 would move the
    kill switch's day by two hours with nothing saying so.
    """
    hour = _int("ODDS_BUDGET_DAY_START_UTC_HOUR", 10)
    if not 0 <= hour <= 23:
        raise ConfigError(
            f"ODDS_BUDGET_DAY_START_UTC_HOUR={hour} must be 0-23."
        )
    return hour


@dataclass(frozen=True)
class OddsConfig:
    api_key: str
    base_url: str
    daily_credit_budget: int
    regions: list[str]
    markets: list[str]
    # Our own monthly ceiling, distinct from the plan's. `None` means uncapped
    # by us -- the provider's `x-requests-remaining` is still authoritative and
    # still refuses. It exists because the daily cap bounds a month only if you
    # multiply it out, which nothing did, and because the historical endpoints
    # cost 10x per call: a backfill can spend a month inside one day without any
    # daily cap objecting. Defaults to None so an unconfigured deployment keeps
    # exactly the behaviour it had.
    monthly_credit_budget: Optional[int] = None
    # The hour the daily credit budget rolls over, UTC. Not midnight: UTC
    # midnight is 5pm PT, the middle of the US evening slate, so it splits one
    # night's games across two budget days. See `odds/timing.py`.
    budget_day_start_utc_hour: int = 10

    @classmethod
    def load(cls) -> "OddsConfig":
        hour = configured_day_start_utc_hour()
        return cls(
            api_key=_require("ODDS_API_KEY"),
            base_url=_optional("ODDS_API_BASE_URL", "https://api.the-odds-api.com/v4"),
            daily_credit_budget=_int("ODDS_DAILY_CREDIT_BUDGET", 16),
            monthly_credit_budget=_int_or_none("ODDS_MONTHLY_CREDIT_BUDGET"),
            regions=[r for r in _optional("ODDS_REGIONS", "us,eu").split(",") if r],
            markets=[
                m for m in _optional("ODDS_MARKETS", "h2h,spreads,totals").split(",") if m
            ],
            budget_day_start_utc_hour=hour,
        )

    @classmethod
    def load_without_credentials(cls) -> "OddsConfig":
        """Everything except the key, for readers that never call the API.

        The cockpit renders the sweep schedule and the actionable window, both
        of which are properties of the *plan* -- what a call costs, how many the
        day affords, when the budget rolls. None of that needs the credential,
        and the demo instance deliberately holds none. Requiring the key to
        render a timetable would either take the demo down or put a credential
        on a public deploy, and both are worse than an empty string here.
        """
        return cls(
            api_key="",
            base_url=_optional("ODDS_API_BASE_URL", "https://api.the-odds-api.com/v4"),
            daily_credit_budget=_int("ODDS_DAILY_CREDIT_BUDGET", 16),
            monthly_credit_budget=_int_or_none("ODDS_MONTHLY_CREDIT_BUDGET"),
            regions=[r for r in _optional("ODDS_REGIONS", "us,eu").split(",") if r],
            markets=[
                m for m in _optional("ODDS_MARKETS", "h2h,spreads,totals").split(",") if m
            ],
            # Validated here too. Until 2026-08-11 this constructor read the
            # variable raw while `load` validated it, so the demo instance --
            # and every reader that never calls the API -- would have accepted
            # `hour=99` and cut its day at a `datetime.replace` that raises far
            # from here.
            budget_day_start_utc_hour=configured_day_start_utc_hour(),
        )

    @property
    def credits_per_sweep_per_sport(self) -> int:
        """The Odds API charges markets x regions per /odds call."""
        return len(self.markets) * len(self.regions)


# The risk profile the **evidence record** is scored against, fixed in code.
#
# Not configurable, and that is the point. `suggested_contracts` is a statement
# about what the operator may buy, so it moves with the deposit; the gate's
# `actionable` counter was defined on it, so the deposit decided what counted as
# evidence. At a $100 bankroll against the deployed caps that counter is
# confined to the far wings -- quarter-Kelly on the edges this tool finds sizes
# below one contract across the 50c band -- so the 300-game floor could not
# realistically increment, and what evidence did accumulate would come only from
# the prices this project has the most reason to distrust. The Gate screen would
# go on saying "0 of 300, keep recording" without naming the cause.
#
# These are the values the live record was accumulated under, so scoring the
# counter against them changes nothing about the rows already written and stops
# a future deposit change from silently rewriting what the record means. See
# `docs/adr/0015`.
# Settings that were removed, and what a reader needs to know instead.
#
# **Announced, never enforced, and the reason is the recovery path.** The first
# version of this raised `ConfigError` on a retired setting — which is this
# repo's own preference ("a tool that starts cleanly and then fails on the first
# order is worse than one that refuses to start"), and it was wrong *here*.
#
# `RiskConfig.load()` is called by `create_app`, which uvicorn runs at boot,
# which `docker/entrypoint.sh` supervises with `wait -n`. So a raise is a
# container crash loop — and it lands **after** `scripts/migrate_db.py` has
# already moved the volume forward, so rolling the image back does not recover
# it either: the old code refuses a newer schema. The only fix would be
# `flyctl secrets unset`, and flyctl is a laptop job while this tool is operated
# from a phone.
#
# That composition is the failure this repo keeps recording: two locally
# reasonable rules — "refuse to start on stale config" and "recovery needs
# flyctl" — multiplying into "the operator cannot recover from their only
# device". A guard whose failure mode is unrecoverable by the person it protects
# is not a safety property.
#
# So it is loud instead: an ERROR on every config load, and a field on
# `/api/health`, which is the one diagnostic reachable from a phone. Nothing is
# substituted and nothing is guessed — the value is simply not read, and that is
# stated wherever anyone would look.
RETIRED_SETTINGS: dict[str, str] = {
    "MIN_ORDER_CONTRACTS": (
        "It existed to stop small orders paying the per-order fee rounding "
        "penalty, but core.sizing already prices every candidate at the fee a "
        "SINGLE contract would pay -- the most expensive per-contract fee any "
        "size pays -- so a positive Kelly fraction already implies the order is "
        "+EV at whatever size it produces. The minimum refused positive-EV "
        "orders rather than preventing negative-EV ones, and below roughly a "
        "$250 bankroll it closed the 50c band this strategy trades, leaving "
        "only the far wings where an edge is least believable. See ADR 0015. "
        "Remove the variable."
    ),
}


def retired_settings_present() -> dict[str, str]:
    """Retired settings currently set in the environment, with their reasons.

    Empty is the healthy state. Read by `RiskConfig.load` for the log line and
    by `/api/health` so the state is visible without shell access.
    """
    return {
        name: detail
        for name, detail in RETIRED_SETTINGS.items()
        if os.getenv(name, "").strip()
    }


REFERENCE_BANKROLL_DOLLARS = 1000.0
REFERENCE_MAX_POSITION_DOLLARS = 100.0
REFERENCE_MAX_EXPOSURE_DOLLARS = 400.0
REFERENCE_MAX_DAILY_LOSS_DOLLARS = 100.0


@dataclass(frozen=True)
class RiskConfig:
    """Caps. All dollars here are converted to integer tenths at the boundary.

    **`bankroll_dollars` is the running balance, not a weekly top-up.** "$100 a
    week" is a flow and every cap here is a stock; entering the flow makes each
    cap four or five times looser than it reads by the end of the month. Update
    it as the balance moves.
    """

    bankroll_dollars: float = 1000.0
    kelly_fraction: float = 0.25
    max_order_contracts: int = 50
    max_position_dollars: float = 100.0
    max_exposure_dollars: float = 400.0
    max_daily_loss_dollars: float = 100.0

    @classmethod
    def load(cls) -> "RiskConfig":
        # A removed setting still sitting in an environment must not be silently
        # ignored -- but see `retired_settings_present` for why this **logs**
        # rather than raising. It is announced, not enforced.
        for name, detail in retired_settings_present().items():
            logger.error("retired setting %s is set and is not read. %s", name, detail)
        return cls(
            bankroll_dollars=_float("BANKROLL_DOLLARS", 1000.0),
            kelly_fraction=_float("KELLY_FRACTION", 0.25),
            max_order_contracts=_int("MAX_ORDER_CONTRACTS", 50),
            max_position_dollars=_float("MAX_POSITION_DOLLARS", 100.0),
            max_exposure_dollars=_float("MAX_EXPOSURE_DOLLARS", 400.0),
            max_daily_loss_dollars=_float("MAX_DAILY_LOSS_DOLLARS", 100.0),
        )

    def reference(self) -> "RiskConfig":
        """This strategy's risk profile with the **deposit** taken out of it.

        Used for one thing: deciding whether a candidate counts toward the
        gate's 300-game floor. The question that floor asks is "has this system
        demonstrated it can pick?", and how much money is in the account is not
        part of the answer — it decides how much you may buy, not whether the
        pick was good.

        The four dollar quantities are replaced; `kelly_fraction` and
        `max_order_contracts` are **kept**, deliberately. Those are strategy
        parameters rather than facts about the account, so changing one *should*
        move the counter — and `strategy_config_version` records which version
        each row was written under, so the two regimes can be told apart
        afterwards. A deposit is not recorded anywhere and would not be.
        """
        return replace(
            self,
            bankroll_dollars=REFERENCE_BANKROLL_DOLLARS,
            max_position_dollars=REFERENCE_MAX_POSITION_DOLLARS,
            max_exposure_dollars=REFERENCE_MAX_EXPOSURE_DOLLARS,
            max_daily_loss_dollars=REFERENCE_MAX_DAILY_LOSS_DOLLARS,
        )


@dataclass(frozen=True)
class StalenessConfig:
    """The freshness contract, enforced server-side on the order endpoint.

    An opportunity outside either bound is not bettable. This is not a warning
    the user can click past — the API refuses it independently of whatever the
    UI decided to render.
    """

    max_odds_age_s: int = 900
    max_kalshi_quote_age_s: int = 30

    @classmethod
    def load(cls) -> "StalenessConfig":
        return cls(
            max_odds_age_s=_int("MAX_ODDS_AGE_S", 900),
            max_kalshi_quote_age_s=_int("MAX_KALSHI_QUOTE_AGE_S", 30),
        )


class StalenessLimitsDisagree(RuntimeError):
    """Two limits on one quantity, and they have stopped agreeing."""


def assert_odds_age_limits_agree(
    *, suppression_max_odds_age_ms: int, staleness: StalenessConfig
) -> None:
    """Fail at startup if the two odds-age limits have diverged. ADR 0019 §6.

    **There are two limits on one quantity and nothing joined them.**
    `SuppressionConfig.max_odds_age_ms` is a hardcoded `900_000` that never
    reads the environment; `MAX_ODDS_AGE_S` is read here and consumed by
    `gate.py`, `live.py` and `routes.py`. They agree at the defaults, so the
    divergence only appears once someone sets the Fly value -- at which point
    the suppression check and the odds sweep keep 15 minutes while the order
    gate, the Board's `actionable` flag and the phone's window banner all move.

    **Why this is a runtime assertion and deliberately not a test.** A test
    compares one hardcoded default against another hardcoded default and passes
    green forever, because the divergence is created by a deployed environment
    value that a test never sees. That is a verification method that lies, and
    this repo has a file of them. The check has to run where the env does.

    Raising rather than warning, per `clamping-is-for-values-you-trust`: the
    failure this prevents is silent by construction, so a log line nobody reads
    is not a control. A deployment whose freshness limits disagree should not
    start.
    """
    expected_ms = staleness.max_odds_age_s * 1000
    if suppression_max_odds_age_ms != expected_ms:
        raise StalenessLimitsDisagree(
            f"MAX_ODDS_AGE_S={staleness.max_odds_age_s}s implies "
            f"{expected_ms}ms, but SuppressionConfig.max_odds_age_ms is "
            f"{suppression_max_odds_age_ms}ms. These bound the same quantity: "
            f"the suppression check and the odds sweep would keep "
            f"{suppression_max_odds_age_ms / 60000:.1f}min while the order "
            f"gate and the window banner move to "
            f"{expected_ms / 60000:.1f}min. Change both or neither -- "
            f"see ADR 0019 section 6."
        )


def assert_kalshi_quote_age_limits_agree(
    *, suppression_max_kalshi_quote_age_ms: int, staleness: StalenessConfig
) -> None:
    """Fail at startup if the two Kalshi-quote-age limits have diverged.

    **The odds-age defect of ADR 0019 section 6, with the other field.** That
    section fixed `max_odds_age_ms` against `MAX_ODDS_AGE_S` and left its twin
    one line above it untouched: `SuppressionConfig.max_kalshi_quote_age_ms` is
    a hardcoded `30_000` that never reads the environment, while
    `MAX_KALSHI_QUOTE_AGE_S` is read here and consumed by `gate.py:746`,
    `routes.py:1938` and `scripts/run_loop.py:243`. They agree at the defaults,
    so the divergence only appears once someone sets the Fly value -- at which
    point the suppression check keeps 30 seconds while the order gate, the
    Board's `price_is_current` flag and the fast-cadence startup check all move.

    **This one is worse than the odds-age case, and measurably so.** Verified by
    construction before the guard was written: with `MAX_KALSHI_QUOTE_AGE_S=5`,
    a 12-second-old quote is `suppressed_reason IS NULL` -- *actionable*, on the
    Board, in the evidence record -- and the order endpoint refuses it. The
    screen offers a bet the server will not take, and neither side logs a
    disagreement. Tightening the env value is the direction an operator would
    reach for after a bad fill, so it is also the likely direction.

    **Why this is a runtime assertion and deliberately not a test**, unchanged
    from the odds-age twin: a test compares one hardcoded default against
    another hardcoded default and passes green forever, because the divergence
    is created by a deployed environment value that a test never sees. That is a
    verification method that lies, and this repo has a file of them. The check
    has to run where the env does.

    Raising rather than warning, per `clamping-is-for-values-you-trust`: the
    failure this prevents is silent by construction, so a log line nobody reads
    is not a control. A deployment whose freshness limits disagree should not
    start.
    """
    expected_ms = staleness.max_kalshi_quote_age_s * 1000
    if suppression_max_kalshi_quote_age_ms != expected_ms:
        raise StalenessLimitsDisagree(
            f"MAX_KALSHI_QUOTE_AGE_S={staleness.max_kalshi_quote_age_s}s "
            f"implies {expected_ms}ms, but "
            f"SuppressionConfig.max_kalshi_quote_age_ms is "
            f"{suppression_max_kalshi_quote_age_ms}ms. These bound the same "
            f"quantity: the suppression check would keep "
            f"{suppression_max_kalshi_quote_age_ms / 1000:.0f}s while the "
            f"order gate, the Board's price_is_current flag and the "
            f"fast-cadence startup check move to {expected_ms / 1000:.0f}s. "
            f"Change both or neither -- see ADR 0019 section 6."
        )


class RiskDayDisagrees(RuntimeError):
    """Two definitions of "today" for the kill switch, in two processes."""


def assert_risk_day_start_agrees(
    *, default_day_start_hour: int, odds: OddsConfig
) -> None:
    """Fail at startup if any risk-day call site could still default. ADR 0024.

    **The third member of the `assert_*_agree` family, and the first one that
    spans two processes.** `settlement.daily_realised_pnl_dollars`,
    `live.QuoteHub` and `agents.AgentBudget` all take `day_start_hour` as a
    keyword with `odds.timing.DEFAULT_DAY_START_UTC_HOUR` as its default.
    `api/routes.py:1546` passes `OddsConfig.budget_day_start_utc_hour`;
    `runner.py` did not, so the runner's kill-switch day came from the hardcoded
    constant and the order endpoint's from the environment. They agree today
    only because `ODDS_BUDGET_DAY_START_UTC_HOUR` is unset on live and both
    resolve to 10 -- the divergence is one `fly secrets set` away and nothing
    downstream can see it, because each process computes a day boundary that is
    internally consistent and never compares it with the other's.

    So this does not compare two call sites against each other. It compares the
    **default** against the **configured** value, which is the only check that
    still holds after a future call site is added and forgets the argument:
    while those two are equal, a forgotten argument is harmless; the moment they
    differ, every defaulting site is on a different day from every configured
    one. That makes the guard survive the fix rather than only certifying it.

    **Which way each divergence fails, because they are not symmetric.** A
    *later* day start means less of the day's realised P&L is counted as
    "today", so `size_position`'s `max_daily_loss_dollars` engages **less** --
    the permissive direction.

    - configured **later** than the default (e.g. 14 vs 10): the *order
      endpoint* is the permissive one. It would admit an order the runner had
      already sized against a fuller day of losses.
    - configured **earlier** than the default (e.g. 6 vs 10): the *runner* is
      the permissive one, and this is the sharper case -- it is the same shape
      as `assert_kalshi_quote_age_limits_agree`, where the screen offers a bet
      the server then refuses. The card is sized, surfaced and recorded; the
      endpoint applies a fuller day of losses and declines.

    Both directions raise. An assertion that fired only on the permissive one
    would leave the other silent, and "silent" is the entire defect.

    **Why this is a runtime assertion and deliberately not a test**, unchanged
    from its two twins: the divergence is created by a deployed environment
    value that a test never sees, so a test comparing one hardcoded default
    against another passes green forever. That is a verification method that
    lies, and this repo has a file of them. The check has to run where the env
    does -- which is why it is wired into `api/routes.py` *and*
    `scripts/run_loop.py`, the two processes that hold the two definitions.

    Raising rather than warning, per `clamping-is-for-values-you-trust`: a log
    line nobody reads is not a control on a money path, and the failure this
    prevents is silent by construction.
    """
    if odds.budget_day_start_utc_hour != default_day_start_hour:
        looser = (
            "the order endpoint"
            if odds.budget_day_start_utc_hour > default_day_start_hour
            else "the runner"
        )
        raise RiskDayDisagrees(
            f"ODDS_BUDGET_DAY_START_UTC_HOUR="
            f"{odds.budget_day_start_utc_hour} but "
            f"odds.timing.DEFAULT_DAY_START_UTC_HOUR is "
            f"{default_day_start_hour}. Every risk-day signature defaults to "
            f"the constant, so any call site that omits `day_start_hour` now "
            f"measures the daily-loss kill switch over a different day from "
            f"the ones that pass it -- and {looser} would be the permissive "
            f"side, counting less of today's realised P&L as today's. Pass the "
            f"configured hour at every site and change the constant to match, "
            f"or change neither -- see docs/adr/0024."
        )


@dataclass(frozen=True)
class MarketResultConfig:
    """How hard `backend/market_results.py` chases an outcome, and for how long.

    All three are here rather than as module constants because they are the
    knobs a *live* pass would need turned, and the only alternative on a
    deployed instance is a code change plus a deploy. Being honest about what
    that buys: these move with `fly secrets set`, which is still flyctl and
    still a laptop. It removes the build-and-deploy, not the laptop. Nothing in
    this dataclass can be changed from a phone, and nothing here can take the
    instance down either -- see `_int_announced`.

    **`max_age_after_commence_s` bounds coverage, so it costs something.** A
    market whose game commenced longer ago than this is dropped from the queue
    permanently: a settlement that genuinely lands on day eight is never
    recorded, and the row stays NULL. That is the price of not spending ~96
    requests a day forever on an event that will never settle -- one is already
    in the capture, `closed` with no result roughly six months after its
    scheduled expiration. Dropped markets are counted (`abandoned_total`) and
    the oldest is named on every pass, so the population is visible rather than
    silently truncated, and widening the window brings them straight back --
    abandonment is a query-time age bound, not a flag written to any row.
    """

    min_age_after_commence_s: int = 2 * 60 * 60
    max_age_after_commence_s: int = 7 * 24 * 60 * 60
    # `None` means "ask about every event with anything outstanding", which is
    # the behaviour the pass shipped with. Not 0 -- that would mean "ask about
    # nothing", and collapsing those two is the confusion `_int_or_none` exists
    # to prevent one field up.
    max_events_per_pass: Optional[int] = None

    @classmethod
    def load(cls) -> "MarketResultConfig":
        defaults = cls()
        min_age = _int_announced(
            "MARKET_RESULT_MIN_AGE_S", defaults.min_age_after_commence_s
        )
        max_age = _int_announced(
            "MARKET_RESULT_MAX_AGE_S", defaults.max_age_after_commence_s
        )
        if max_age <= min_age:
            logger.error(
                "MARKET_RESULT_MAX_AGE_S=%d is not above MARKET_RESULT_MIN_AGE_S"
                "=%d, which would leave nothing to ask about and abandon every "
                "market. Neither is read; using the defaults %d and %d.",
                max_age, min_age, defaults.min_age_after_commence_s,
                defaults.max_age_after_commence_s,
            )
            min_age = defaults.min_age_after_commence_s
            max_age = defaults.max_age_after_commence_s

        raw_cap = os.getenv("MARKET_RESULT_MAX_EVENTS_PER_PASS", "").strip()
        cap: Optional[int] = None
        if raw_cap:
            cap = _int_announced("MARKET_RESULT_MAX_EVENTS_PER_PASS", 0)
            if cap <= 0:
                logger.error(
                    "MARKET_RESULT_MAX_EVENTS_PER_PASS=%r is not a positive "
                    "integer and is not read; the pass stays uncapped. Unset "
                    "means uncapped; 0 would mean 'ask about nothing'.",
                    raw_cap,
                )
                cap = None
        return cls(
            min_age_after_commence_s=min_age,
            max_age_after_commence_s=max_age,
            max_events_per_pass=cap,
        )

    @property
    def min_age_after_commence_ms(self) -> int:
        return self.min_age_after_commence_s * 1000

    @property
    def max_age_after_commence_ms(self) -> int:
        return self.max_age_after_commence_s * 1000


@dataclass(frozen=True)
class GateConfig:
    """The live-money gate. Locked by default, and locked is the safe state."""

    live_trading_enabled: bool = False
    min_scored_recommendations: int = 300

    @classmethod
    def load(cls) -> "GateConfig":
        return cls(
            live_trading_enabled=_bool("LIVE_TRADING_ENABLED", False),
            min_scored_recommendations=_int("LIVE_GATE_MIN_SCORED_RECOMMENDATIONS", 300),
        )


@dataclass(frozen=True)
class AppConfig:
    instance_mode: str = "demo"
    auth_token: Optional[str] = None
    cockpit_base_url: str = "http://localhost:3000"
    db_path: Path = field(default_factory=lambda: Path("data/cockpit.db"))
    # The dbt/DuckDB warehouse. Separate from db_path on purpose: SQLite is the
    # live operational store and this is the analytics snapshot, and the
    # Dashboards screen must never be able to write to either.
    warehouse_path: Path = field(default_factory=lambda: Path("data/warehouse.duckdb"))

    @classmethod
    def load(cls) -> "AppConfig":
        mode = _optional("INSTANCE_MODE", "demo").lower()
        if mode not in {"demo", "live"}:
            raise ConfigError(
                f"INSTANCE_MODE={mode!r} must be 'demo' or 'live'. Demo serves "
                "seeded data with no credentials and no execution path."
            )
        token = _optional("APP_AUTH_TOKEN") or None
        if mode == "live" and not token:
            raise ConfigError(
                "INSTANCE_MODE=live requires APP_AUTH_TOKEN. An unauthenticated "
                "instance holding real credentials is not an acceptable state. "
                "Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        return cls(
            instance_mode=mode,
            auth_token=token,
            cockpit_base_url=_optional("COCKPIT_BASE_URL", "http://localhost:3000"),
            db_path=Path(_optional("DB_PATH", "data/cockpit.db")),
            warehouse_path=Path(
                _optional("WAREHOUSE_PATH", "data/warehouse.duckdb")
            ),
        )

    @property
    def is_demo(self) -> bool:
        return self.instance_mode == "demo"
