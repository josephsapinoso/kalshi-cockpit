"""No deployed instance may silently size itself from a code default.

**What this establishes:** that every field of `RiskConfig` is written out in
both `fly.live.toml` and `fly.demo.toml`, that the values parse, and that the
public instance never sizes larger than the private one.

**What it does not establish:** that the numbers are *right*. It cannot -- a
cap is a judgement about a bankroll, and no test knows the balance. It only
establishes that the judgement was made here rather than inherited by accident
from a dataclass default written for a different bankroll.

Why it exists. `fly.demo.toml` set none of the four dollar caps, so the public
demo fell through to `RiskConfig`'s defaults -- 1000 / 100 / 400 / 100 against
live's 100 / 10 / 40 / 10, ten times looser on every one. A demo card reading
`Buy 17` was one contract at the deployed roll. Nothing was red: the divergence
lived entirely in the gap between two config files and no test compared them.

That is the same failure that produced the live instance's own caps. From
`fly.live.toml`: "At $1,000 these were 100 / 400 / 100 and were never stated
here, so they were inherited from the code defaults -- which meant that
lowering the bankroll alone would have left a position cap equal to 100% of it
... A safety system that cannot bind is worse than none, because it reassures."
The fix went into `fly.live.toml` and the record and never into `fly.demo.toml`.

The guard is derived from `RiskConfig`'s own fields rather than from a hand-
written list, so a seventh cap added tomorrow fails here until both files state
it. A hand-written list is how the first six got to six.
"""

from __future__ import annotations

import tomllib
from dataclasses import fields
from pathlib import Path

import pytest

from backend.config import RiskConfig


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_CONFIGS = {
    "fly.live.toml": REPO_ROOT / "fly.live.toml",
    "fly.demo.toml": REPO_ROOT / "fly.demo.toml",
}

# `RiskConfig.load` reads each field from its own name upper-cased. Pinned by
# `test_every_field_is_read_from_its_upper_cased_name` below, so this
# derivation cannot drift away from the loader in silence.
RISK_SETTINGS = [f.name.upper() for f in fields(RiskConfig)]

# Lower is tighter for these. `kelly_fraction` and `max_order_contracts` are
# also monotone this way, but they are strategy parameters rather than facts
# about the account and are compared only for presence.
DOLLAR_CAPS = [
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


class TestTheDerivationIsPinnedToTheLoader:
    """The list of required names comes from the dataclass, so prove it maps."""

    @pytest.mark.parametrize("field_", [f.name for f in fields(RiskConfig)])
    def test_every_field_is_read_from_its_upper_cased_name(self, field_, monkeypatch):
        default = getattr(RiskConfig(), field_)
        # An arbitrary different value of the same type.
        probe = type(default)(default) + type(default)(1)
        monkeypatch.setenv(field_.upper(), str(probe))

        assert getattr(RiskConfig.load(), field_) == probe, (
            f"RiskConfig.{field_} is not read from {field_.upper()}, so this "
            "module's derived list of required settings is wrong"
        )


class TestEveryCapIsStatedInEveryDeployedConfig:
    @pytest.mark.parametrize("config", sorted(DEPLOY_CONFIGS))
    @pytest.mark.parametrize("setting", RISK_SETTINGS)
    def test_the_setting_is_present(self, config, setting):
        env = deployed_env(config)

        assert setting in env, (
            f"{config} does not set {setting}, so that instance runs on the "
            f"code default ({getattr(RiskConfig(), setting.lower())}). A cap "
            "nobody chose is not a cap."
        )

    @pytest.mark.parametrize("config", sorted(DEPLOY_CONFIGS))
    @pytest.mark.parametrize("setting", RISK_SETTINGS)
    def test_the_value_parses_as_the_type_the_loader_expects(self, config, setting):
        """Fly requires `[env]` values to be strings; the loader converts."""
        raw = deployed_env(config)[setting]
        expected = type(getattr(RiskConfig(), setting.lower()))

        assert isinstance(raw, str), f"{config}: {setting} must be a quoted string"
        assert expected(raw) > 0, f"{config}: {setting}={raw} is not a usable cap"


class TestThePublicScreenNeverSizesLargerThanThePrivateOne:
    """The screen that overstates is the one strangers see.

    This project's thesis is that the flattering number does not stand. A demo
    that sizes above the live instance publishes a position this operator could
    not take, which is the flattering number in its purest form -- and it is
    the direction the bug actually went.

    Deliberate divergence is still allowed; only divergence *upward* is not.
    """

    @pytest.mark.parametrize("cap", DOLLAR_CAPS)
    def test_the_demo_cap_is_not_looser_than_the_live_one(self, cap, live_env, demo_env):
        assert float(demo_env[cap]) <= float(live_env[cap]), (
            f"the public demo runs {cap}={demo_env[cap]} against the live "
            f"instance's {live_env[cap]}"
        )


class TestThePositionCapBindsFirst:
    """The record says "three caps". There are four, and the bankroll is one.

    `size_position` computes `stake = kelly_used * bankroll_dollars` and then
    trims it, so the bankroll is not merely an input to sizing -- it is the
    outermost cap, and the three `MAX_*` settings are cuts taken out of it.
    Counting three is what let `BANKROLL_DOLLARS` be treated as a display
    setting the demo could leave unset.

    On a *single* order from a flat book the position cap always binds first at
    this bankroll: reaching the $40 exposure cap in one order needs a staked
    Kelly fraction above 0.40, i.e. a full Kelly above 1.6, which is not
    reachable. Exposure binds only by accumulation, at the fifth concurrent
    market. Both are real caps; they just bind in different situations, and a
    reading that treats them as interchangeable gets the demo's numbers wrong.
    """

    def test_the_bankroll_is_a_cap_and_not_only_an_input(self, live_env, demo_env):
        for env in (live_env, demo_env):
            bankroll = float(env["BANKROLL_DOLLARS"])
            assert float(env["MAX_POSITION_DOLLARS"]) <= bankroll
            assert float(env["MAX_DAILY_LOSS_DOLLARS"]) <= bankroll

    @pytest.mark.parametrize("config", sorted(DEPLOY_CONFIGS))
    def test_a_single_order_cannot_reach_the_exposure_cap(self, config):
        """So `max_position_dollars` is the one that binds an opening order."""
        env = deployed_env(config)
        most_a_single_order_can_stake = (
            float(env["KELLY_FRACTION"]) * float(env["BANKROLL_DOLLARS"])
        )

        assert float(env["MAX_POSITION_DOLLARS"]) < most_a_single_order_can_stake, (
            f"{config}: the position cap cannot bind, so it is decoration"
        )
        assert float(env["MAX_EXPOSURE_DOLLARS"]) > most_a_single_order_can_stake, (
            f"{config}: one order can exhaust the exposure cap"
        )
