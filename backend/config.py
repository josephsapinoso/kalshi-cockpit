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

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


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
        hour = _int("ODDS_BUDGET_DAY_START_UTC_HOUR", 10)
        if not 0 <= hour <= 23:
            raise ConfigError(
                f"ODDS_BUDGET_DAY_START_UTC_HOUR={hour} must be 0-23."
            )
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
            budget_day_start_utc_hour=_int("ODDS_BUDGET_DAY_START_UTC_HOUR", 10),
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
        # `MIN_ORDER_CONTRACTS` was removed, not renamed, and a removed setting
        # still sitting in someone's environment must not be silently ignored --
        # this one closed the 50c band -- where the strategy trades -- at any
        # bankroll under ~$250, and it did
        # it by returning a plausible zero.
        if os.getenv("MIN_ORDER_CONTRACTS", "").strip():
            raise ConfigError(
                "MIN_ORDER_CONTRACTS is set and is no longer read. It existed to "
                "stop small orders paying the per-order fee rounding penalty -- "
                "but `core.sizing` already prices every candidate at the fee a "
                "SINGLE contract would pay, which is the most expensive "
                "per-contract fee any size pays, so a positive Kelly fraction "
                "already implies the order is +EV at whatever size it produces. "
                "The minimum was refusing positive-EV orders, not preventing "
                "negative-EV ones. Below roughly a $250 bankroll it closed the 50c "
                "band entirely -- the band this strategy trades -- leaving only "
                "the far wings, where an edge is least believable. Remove the "
                "variable."
            )
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
