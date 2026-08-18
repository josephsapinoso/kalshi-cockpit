"""The dollar caps are derived, never typed -- and nothing may type them back.

**What this establishes** (rewritten for ADR 0045; the original file asserted
the exact opposite): that the four dollar quantities are absent from both
deploy configs and ignored by the loader even when set; that the two strategy
parameters which ARE still typed are stated in both configs and read from
their names; and that the derivation's fractions preserve the binding
structure the typed profiles had -- the position cap binds an opening order,
the exposure cap binds only by accumulation.

**What it does not establish:** that the fractions are *right* -- 10/40/10 is
a judgement carried over from both prior profiles -- or that any instance has
a balance observation to derive from. An empty `venue_balance_snapshots`
refuses to size, and that refusal is `core.sizing`'s test surface, not this
file's.

History, because this file has now asserted both directions and the reversal
must not look like drift. The original version existed because `fly.demo.toml`
omitted the caps and silently sized at the $1,000 dataclass defaults -- "a cap
nobody chose is not a cap." The fix it enforced (type every cap in every
config) then produced the next defect: the typed `BANKROLL_DOLLARS = "100"`
sat against a real ~$20.66 balance for a week, every Board size ~4.8x
inflated, and nothing was red. A typed cap and an omitted cap fail the same
way -- the number nobody is maintaining wins -- so ADR 0045 removed the typing
entirely: the bankroll comes from the venue's own balance record and the caps
are fixed fractions of it. What this file now guards is the retirement
staying retired.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from backend.config import (
    DAILY_LOSS_FRACTION_OF_BANKROLL,
    EXPOSURE_FRACTION_OF_BANKROLL,
    POSITION_FRACTION_OF_BANKROLL,
    RiskConfig,
    retired_settings_present,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_CONFIGS = {
    "fly.live.toml": REPO_ROOT / "fly.live.toml",
    "fly.demo.toml": REPO_ROOT / "fly.demo.toml",
}

# The two the loader still reads from the environment: judgements about the
# strategy, not facts about the account.
STRATEGY_SETTINGS = ["KELLY_FRACTION", "MAX_ORDER_CONTRACTS"]

# The four the loader must never read again.
RETIRED_DOLLAR_CAPS = [
    "BANKROLL_DOLLARS",
    "MAX_POSITION_DOLLARS",
    "MAX_EXPOSURE_DOLLARS",
    "MAX_DAILY_LOSS_DOLLARS",
]


def deployed_env(name: str) -> dict:
    return tomllib.loads(DEPLOY_CONFIGS[name].read_text(encoding="utf-8"))["env"]


@pytest.fixture(scope="module")
def live_env():
    return deployed_env("fly.live.toml")


@pytest.fixture(scope="module")
def demo_env():
    return deployed_env("fly.demo.toml")


class TestTheDollarCapsStayRetired:
    """A typed dollar cap must be inert wherever it reappears."""

    @pytest.mark.parametrize("setting", RETIRED_DOLLAR_CAPS)
    def test_the_loader_ignores_the_setting_even_when_set(self, setting, monkeypatch):
        """Set in the environment, the value must not reach the config.

        `load()` returns the dollar fields as None -- underived -- and
        `size_position` refuses an underived config, so a resurrected env var
        cannot silently size anything.
        """
        monkeypatch.setenv(setting, "123.45")

        assert getattr(RiskConfig.load(), setting.lower()) is None, (
            f"RiskConfig.load() read {setting} from the environment. The "
            "dollar quantities are derived from the observed balance "
            "(ADR 0045); a typed value is a stale claim and must be inert."
        )

    @pytest.mark.parametrize("setting", RETIRED_DOLLAR_CAPS)
    def test_a_set_value_is_announced_as_retired(self, setting, monkeypatch):
        monkeypatch.setenv(setting, "123.45")

        assert setting in retired_settings_present(), (
            f"{setting} is set but not announced. An ignored setting that is "
            "also silent is indistinguishable from one that works."
        )

    @pytest.mark.parametrize("config", sorted(DEPLOY_CONFIGS))
    @pytest.mark.parametrize("setting", RETIRED_DOLLAR_CAPS)
    def test_the_setting_is_absent_from_the_deploy_config(self, config, setting):
        assert setting not in deployed_env(config), (
            f"{config} sets {setting}, which is retired (ADR 0045): it is "
            "announced at ERROR on every config load and never read, so the "
            "value is a claim the deploy does not honour."
        )


class TestTheStrategyParametersAreStillExplicit:
    """What is still typed must still be typed everywhere, and still read."""

    @pytest.mark.parametrize("config", sorted(DEPLOY_CONFIGS))
    @pytest.mark.parametrize("setting", STRATEGY_SETTINGS)
    def test_the_setting_is_present(self, config, setting):
        env = deployed_env(config)

        assert setting in env, (
            f"{config} does not set {setting}, so that instance runs on the "
            f"code default ({getattr(RiskConfig(), setting.lower())}). A "
            "strategy parameter nobody chose is not a judgement."
        )

    @pytest.mark.parametrize("config", sorted(DEPLOY_CONFIGS))
    @pytest.mark.parametrize("setting", STRATEGY_SETTINGS)
    def test_the_value_parses_as_the_type_the_loader_expects(self, config, setting):
        """Fly requires `[env]` values to be strings; the loader converts."""
        raw = deployed_env(config)[setting]
        expected = type(getattr(RiskConfig(), setting.lower()))

        assert isinstance(raw, str), f"{config}: {setting} must be a quoted string"
        assert expected(raw) > 0, f"{config}: {setting}={raw} is not usable"

    @pytest.mark.parametrize("setting", STRATEGY_SETTINGS)
    def test_the_loader_reads_the_setting_from_its_name(self, setting, monkeypatch):
        field = setting.lower()
        default = getattr(RiskConfig(), field)
        probe = type(default)(default) + type(default)(1)
        monkeypatch.setenv(setting, str(probe))

        assert getattr(RiskConfig.load(), field) == probe, (
            f"RiskConfig.{field} is not read from {setting}, so this module's "
            "list of required settings is wrong"
        )


class TestThePublicScreenNeverSizesLargerThanThePrivateOne:
    """The screen that overstates is the one strangers see.

    With the dollar caps derived by one shared rule, upward divergence can no
    longer live in the dollar values -- only in the strategy parameters, so
    those are what is compared. Deliberate divergence is still allowed; only
    divergence *upward* is not.
    """

    @pytest.mark.parametrize("setting", STRATEGY_SETTINGS)
    def test_the_demo_parameter_is_not_looser_than_the_live_one(
        self, setting, live_env, demo_env
    ):
        assert float(demo_env[setting]) <= float(live_env[setting]), (
            f"the public demo runs {setting}={demo_env[setting]} against the "
            f"live instance's {live_env[setting]}"
        )


class TestTheFractionsPreserveTheBindingStructure:
    """The typed profiles' shape, now carried by the fractions.

    On a single order from a flat book the position cap must bind before the
    exposure cap: a single order stakes at most `kelly_fraction` of the
    bankroll (full Kelly is clamped at 1.0 by `full_kelly_fraction`'s
    construction only in the limit; in practice quarter-Kelly), so the
    position fraction must sit below the deployed Kelly fraction and the
    exposure fraction above it. Both caps are real; they bind in different
    situations, and a derivation that flipped their order would change what
    every refusal message means.
    """

    @pytest.mark.parametrize("config", sorted(DEPLOY_CONFIGS))
    def test_a_single_order_cannot_reach_the_exposure_cap(self, config):
        kelly = float(deployed_env(config)["KELLY_FRACTION"])

        assert POSITION_FRACTION_OF_BANKROLL < kelly, (
            f"{config}: the position fraction "
            f"({POSITION_FRACTION_OF_BANKROLL}) cannot bind under "
            f"KELLY_FRACTION={kelly}, so it is decoration"
        )
        assert EXPOSURE_FRACTION_OF_BANKROLL > kelly, (
            f"{config}: one order can exhaust the exposure fraction "
            f"({EXPOSURE_FRACTION_OF_BANKROLL}) under KELLY_FRACTION={kelly}"
        )

    def test_every_cap_stays_inside_the_bankroll(self):
        for fraction in (
            POSITION_FRACTION_OF_BANKROLL,
            EXPOSURE_FRACTION_OF_BANKROLL,
            DAILY_LOSS_FRACTION_OF_BANKROLL,
        ):
            assert 0 < fraction <= 1.0, (
                f"a cap fraction of {fraction} is outside the bankroll -- a "
                "cap that cannot bind is worse than none, because it reassures"
            )
