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
from dataclasses import dataclass, field
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

    @classmethod
    def load(cls) -> "OddsConfig":
        return cls(
            api_key=_require("ODDS_API_KEY"),
            base_url=_optional("ODDS_API_BASE_URL", "https://api.the-odds-api.com/v4"),
            daily_credit_budget=_int("ODDS_DAILY_CREDIT_BUDGET", 16),
            regions=[r for r in _optional("ODDS_REGIONS", "us,eu").split(",") if r],
            markets=[
                m for m in _optional("ODDS_MARKETS", "h2h,spreads,totals").split(",") if m
            ],
        )

    @property
    def credits_per_sweep_per_sport(self) -> int:
        """The Odds API charges markets x regions per /odds call."""
        return len(self.markets) * len(self.regions)


@dataclass(frozen=True)
class RiskConfig:
    """Caps. All dollars here are converted to integer tenths at the boundary."""

    bankroll_dollars: float = 1000.0
    kelly_fraction: float = 0.25
    max_order_contracts: int = 50
    max_position_dollars: float = 100.0
    max_exposure_dollars: float = 400.0
    max_daily_loss_dollars: float = 100.0
    min_order_contracts: int = 10

    @classmethod
    def load(cls) -> "RiskConfig":
        return cls(
            bankroll_dollars=_float("BANKROLL_DOLLARS", 1000.0),
            kelly_fraction=_float("KELLY_FRACTION", 0.25),
            max_order_contracts=_int("MAX_ORDER_CONTRACTS", 50),
            max_position_dollars=_float("MAX_POSITION_DOLLARS", 100.0),
            max_exposure_dollars=_float("MAX_EXPOSURE_DOLLARS", 400.0),
            max_daily_loss_dollars=_float("MAX_DAILY_LOSS_DOLLARS", 100.0),
            min_order_contracts=_int("MIN_ORDER_CONTRACTS", 10),
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
