"""The C0 probe's refusal logic, driven to every branch with no network.

Only the refusals are under test. The probes themselves cannot be tested
without the live venue, and the module docstring of the script says so; what
must never regress silently is the set of conditions under which the script
sends nothing at all.

Every assertion was verified by disabling the guard it defends and watching it
go red. The mutations are named on each class.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from probe_create_order import (  # noqa: E402
    MAX_FILL_ASK_TENTHS,
    SPEND_FLAG,
    fill_ask_refusal,
    refusal_reason,
)


def _reason(**overrides) -> str | None:
    """refusal_reason with every precondition satisfied, minus overrides."""
    kwargs = dict(
        acknowledged=True, instance_mode="live", kalshi_key_configured=True
    )
    kwargs.update(overrides)
    return refusal_reason(**kwargs)


class TestMissingFlagRefuses:
    """Mutation seen red: `if not acknowledged` inverted to `if acknowledged`."""

    def test_no_flag_refuses_even_on_live_with_a_key(self):
        assert _reason(acknowledged=False) is not None

    def test_the_refusal_names_the_flag(self):
        # The message is the operator's only clue which precondition failed.
        assert SPEND_FLAG in _reason(acknowledged=False)


class TestDemoInstanceRefuses:
    """Mutation seen red: `instance_mode != "live"` changed to `== "demo"`,
    which would let an unset/typo'd mode through -- the second test below is
    the one that catches that weakening."""

    def test_demo_refuses(self):
        assert _reason(instance_mode="demo") is not None

    def test_anything_that_is_not_live_refuses(self):
        # The default when INSTANCE_MODE is unset is "demo", but the guard
        # must be an allow-list on "live", not a deny-list on "demo": an
        # unrecognised mode is not a live instance.
        for mode in ("", "prod", "LIVE ", "Live-ish"):
            assert _reason(instance_mode=mode) is not None, mode


class TestMissingKeyRefuses:
    """Mutation seen red: `if not kalshi_key_configured` deleted."""

    def test_no_kalshi_key_refuses_even_on_live_with_the_flag(self):
        assert _reason(kalshi_key_configured=False) is not None


class TestAllPreconditionsMetProceeds:
    """Mutation seen red: final `return None` replaced with a reason string.

    The flag, live mode, and a loaded key together are sufficient -- a guard
    that also refuses the legitimate run is a different bug with the same
    green tests, unless this asserts the opposite direction.
    """

    def test_flag_plus_live_plus_key_is_not_refused(self):
        assert _reason() is None


class TestFillAskCapIsEnforced:
    """Mutation seen red: `>` changed to `>=`, and the None branch deleted."""

    def test_ask_above_ten_cents_refuses(self):
        assert fill_ask_refusal(MAX_FILL_ASK_TENTHS + 1) is not None

    def test_ask_at_exactly_ten_cents_is_allowed(self):
        # The cap is <= $0.10 + fee; 10.0c itself is inside the budget.
        assert fill_ask_refusal(MAX_FILL_ASK_TENTHS) is None

    def test_a_cheap_ask_is_allowed(self):
        assert fill_ask_refusal(10) is None

    def test_no_derived_ask_refuses_rather_than_defaults(self):
        # Unreadable resolves to a refusal, never to "cheap enough".
        assert fill_ask_refusal(None) is not None

    def test_the_cap_is_ten_cents(self):
        # 100 tenths = 10c. If this number moves, the runbook's stated worst
        # case moves with it and must be rewritten in the same commit.
        assert MAX_FILL_ASK_TENTHS == 100
