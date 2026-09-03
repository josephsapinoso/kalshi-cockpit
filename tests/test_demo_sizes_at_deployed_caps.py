"""The public demo must render the size its own pinned profile produces.

**What this establishes:** that every money figure `/api/board` serves for the
seeded demo -- contracts and stake -- is exactly what `size_position` returns
under `seed_demo.DEMO_RISK`, that DEMO_RISK's strategy parameters and
`fly.demo.toml` cannot drift apart, and that its dollar caps follow the same
ADR 0045 derivation fractions the live instance applies to its observed
balance. Since ADR 0045 the toml states no dollar caps at all -- they are
retired everywhere -- so the demo's profile is pinned in code and checked for
internal consistency instead of against config text.

**What it does not establish:** that the caps are *right*, that the browser
paints the number legibly, or anything about the live instance. It asserts on
the payload the card is built from, which is the closest a Python test gets to
"what a stranger sees"; the pixels still need eyes.

Why it exists
-------------
`backend/seed_demo.py` built its recommendations with a bare `RiskConfig()` --
the dataclass defaults, a **$1,000** bankroll. No instance deploys that. On the
row the demo served on 2026-08-18 the public card read `Buy 17` / `$8.85` where
the deployed caps give **1 contract / $0.52**. Seventeen times, on the URL that
is the portfolio piece, and every design judgement made against that screen was
made against numbers nobody will ever see.

**Why the existing guard could not catch it, which is the part worth keeping.**
`tests/test_deployed_risk_caps_are_explicit.py` was written *about this class of
bug*. Its own Context says the failure was that "the tests exercised the loader,
never the deployment". Every assertion it then shipped is about the text of the
two toml files or about `RiskConfig.load()`. Not one touches what the demo
renders, so all of them stayed green through a 17x error. Naming a failure mode
does not move you up an abstraction level; only asserting one level up does.

**A cap check would not have caught it either, and this is the trap.** $8.85
fits *under* the deployed `MAX_POSITION_DOLLARS = 10`. The constraint that
actually bound was Kelly off the bankroll. So "no card exceeds the position
cap" passes on the bug, and the assertion has to be an exact recomputation
rather than a bound.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from backend.api.routes import create_app
from backend.config import AppConfig, RiskConfig
from backend.core.prices import tenths_to_dollars
from backend.core.sizing import size_position
from backend.seed_demo import DEMO_RISK, seed_all

from tests.test_api import get


REPO_ROOT = Path(__file__).resolve().parents[1]
FLY_DEMO = REPO_ROOT / "fly.demo.toml"

# A clean book. The demo database holds no orders and no settlements, so all
# three are genuinely zero -- stated rather than defaulted, because the sizer
# has no defaults and an omission here would be indistinguishable from the
# production omission that let a -$20,000 account place an order.
CLEAN_BOOK = {
    "current_exposure_dollars": 0.0,
    "current_position_dollars": 0.0,
    "daily_pnl_dollars": 0.0,
}


def demo_env() -> dict:
    return tomllib.loads(FLY_DEMO.read_text(encoding="utf-8"))["env"]


# `/api/board` returns the rows in four **top-level** buckets, and a card is
# drawn from any of them. (`payload["slate"]` is the window metadata beside
# them -- anchor, ages, counts -- not the rows.) Flattened here rather than
# reaching for `surfaced` alone, so a row that moves between buckets does not
# quietly fall out of the guard.
BUCKETS = ("surfaced", "expired", "sized_to_zero", "suppressed", "no_edge")


def rendered_rows(payload) -> list:
    return [row for bucket in BUCKETS for row in payload[bucket]]


def unsuppressed(rows) -> list:
    """Rows whose rendered size *is* the sizer's output.

    A suppressed row carries `suggested_contracts = 0` by decree -- `engine.py`
    zeroes it whatever the sizer said -- so recomputing the sizer on one and
    demanding it match would assert the suppression rule, not the caps. Those
    rows are still checked against the cap bound below; only the exact
    recomputation excludes them.
    """
    return [row for row in rows if row["suppressed_reason"] is None]


def sized(row, risk: RiskConfig):
    """What the sizer returns for a rendered row under `risk`."""
    return size_position(
        side=row["side"],
        ask_tenths=row["ask_tenths"],
        fair_probability=row["fair_probability"],
        risk=risk,
        **CLEAN_BOOK,
    )


@pytest.fixture(scope="module")
def demo_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("demo-sizes") / "demo.db"
    seed_all(path)
    return path


@pytest.fixture
def demo_app(demo_db):
    return create_app(AppConfig(instance_mode="demo", db_path=demo_db))


class TestTheSeededCapsAreTheDeployedOnes:
    """The demo profile is pinned in code; pin what CAN still drift.

    Since ADR 0045 the toml carries no dollar caps -- deriving them from an
    observed balance is the rule, and the demo holds no account to observe.
    What must still agree: the two strategy parameters the toml does state,
    and the derivation fractions themselves, so the synthetic profile
    embodies the same judgement (10% / 40% / 10%) the live instance applies
    to its real balance.
    """

    @pytest.mark.parametrize(
        "field_", ["kelly_fraction", "max_order_contracts"]
    )
    def test_the_strategy_parameters_match_the_deployed_ones(self, field_):
        seeded = getattr(DEMO_RISK, field_)
        deployed = type(seeded)(demo_env()[field_.upper()])

        assert seeded == deployed, (
            f"seed_demo.DEMO_RISK.{field_} is {seeded} but fly.demo.toml "
            f"deploys {deployed}. The public demo would size at a "
            "configuration nothing runs."
        )

    def test_the_dollar_caps_follow_the_derivation_fractions(self):
        """DEMO_RISK must be what ADR 0045 would derive from its bankroll.

        `with_observed_balance` is the production derivation; feeding it the
        demo bankroll must reproduce the pinned profile exactly. A hand-typed
        cap that drifts from the fractions would make the public screen imply
        a risk judgement no instance runs.
        """
        derived = DEMO_RISK.with_observed_balance(
            int(DEMO_RISK.bankroll_dollars * 1000)
        )
        assert derived == DEMO_RISK, (
            f"DEMO_RISK is {DEMO_RISK} but ADR 0045 derives {derived} from "
            "the same bankroll"
        )

    def test_the_retired_caps_are_not_in_the_toml(self):
        for name in (
            "BANKROLL_DOLLARS",
            "MAX_POSITION_DOLLARS",
            "MAX_EXPOSURE_DOLLARS",
            "MAX_DAILY_LOSS_DOLLARS",
        ):
            assert name not in demo_env(), (
                f"fly.demo.toml sets {name}, which is retired (ADR 0045): it "
                "is announced at ERROR and never read, so the value is a "
                "claim the deploy does not honour"
            )

    def test_the_restated_caps_are_not_just_the_dataclass_defaults(self):
        """That the restating is doing work -- and only that.

        **This does not catch a revert, and the first draft of it claimed to.**
        Checked by putting `risk = RiskConfig()` back: this assertion stayed
        green, because the constant still exists and still differs; nothing
        here observes whether the seeder *uses* it. The two rendered checks
        below are what failed, and they are the guard. Kept anyway for the one
        thing it does establish -- that `DEMO_RISK` is not a synonym for the
        defaults, so `test_the_seeded_caps_match_the_deployed_ones` above is
        not comparing two identical things and passing for free.

        If `RiskConfig`'s defaults are ever changed to match the deployment,
        this goes vacuous. Delete it then; do not weaken it.
        """
        assert DEMO_RISK != RiskConfig(), (
            "DEMO_RISK is the dataclass defaults, so restating them proved "
            "nothing"
        )


class TestEveryRenderedSizeIsTheOneTheDeployedCapsProduce:
    """Asserted on `/api/board`'s payload, not on config text or the loader."""

    async def test_the_rendered_contract_count_is_recomputable_from_the_toml(
        self, demo_app
    ):
        risk = DEMO_RISK
        rows = unsuppressed(
            rendered_rows(
                (await get(demo_app, "/api/board?include_suppressed=true")).json()
            )
        )
        assert rows, "the seeded demo served no rows, so nothing was checked"

        for row in rows:
            expected = sized(row, risk)

            assert row["suggested_contracts"] == expected.contracts, (
                f"{row['ticker']}: the public demo renders "
                f"{row['suggested_contracts']} contracts where the deployed "
                f"caps give {expected.contracts}"
            )

    async def test_the_rendered_stake_is_recomputable_from_the_toml(self, demo_app):
        """Contracts and dollars are two renderings, and both are on the card.

        **`stake_dollars` names two different quantities and they are not the
        same number.** `SizingResult.stake_dollars` is `contracts * price`
        where `price` already charges a single contract's fee
        (`sizing.py:241`), while the payload's `stake_dollars` is the bare
        `ask * contracts` and puts the fee into `total_cost_dollars`
        (`routes.py:2850`, `:3011`). On the demo's NFL row that is $0.65
        against $0.63. So the rendered figure is checked against the ask times
        the **recomputed** contract count -- which still fails on the bug, and
        does not depend on guessing which of the two a field name means.
        """
        risk = DEMO_RISK
        rows = unsuppressed(
            rendered_rows(
                (await get(demo_app, "/api/board?include_suppressed=true")).json()
            )
        )
        assert rows

        for row in rows:
            expected = sized(row, risk)

            deployed_stake = tenths_to_dollars(row["ask_tenths"] * expected.contracts)

            assert row["stake_dollars"] == pytest.approx(deployed_stake), (
                f"{row['ticker']}: the card reads ${row['stake_dollars']:.2f} "
                f"where the deployed caps give ${deployed_stake:.2f}"
            )

    async def test_no_rendered_card_stakes_more_than_the_position_cap(self, demo_app):
        """A bound, kept beside the exact checks and not instead of them.

        This one alone would have passed on the 17x bug -- $8.85 is under the
        $10 position cap -- which is why it is third and why this says so. It
        earns its place against a different failure: a sizer change that breaks
        the cap for every configuration at once, where a recomputation would
        agree with itself and stay green.
        """
        risk = DEMO_RISK
        rows = rendered_rows(
            (await get(demo_app, "/api/board?include_suppressed=true")).json()
        )
        assert rows

        for row in rows:
            assert row["stake_dollars"] <= risk.max_position_dollars + 1e-9, (
                f"{row['ticker']} stakes ${row['stake_dollars']:.2f} against a "
                f"${risk.max_position_dollars:.2f} position cap"
            )


class TestTheSlateCanTellTheTwoConfigurationsApart:
    """Without this, the checks above could be green on a slate of zeroes.

    Every assertion in this module compares a rendered number against a
    recomputation. If no row on the demo slate happens to size differently at
    $1,000 than at the deployed $100, all of them pass under either
    configuration and the module is decoration. So the discriminating power is
    asserted directly rather than assumed.
    """

    async def test_at_least_one_surfaced_row_sizes_differently_at_the_defaults(
        self, demo_app
    ):
        rows = unsuppressed(rendered_rows((await get(demo_app, "/api/board")).json()))
        assert rows, "the seeded demo surfaced no rows"

        differing = [
            row
            for row in rows
            if sized(row, RiskConfig()).contracts != sized(row, DEMO_RISK).contracts
        ]

        assert differing, (
            "no surfaced row sizes differently at the $1,000 dataclass "
            "defaults than at the deployed $100, so this module cannot tell "
            "the two configurations apart on this slate"
        )
