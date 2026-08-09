"""The deposit must not decide what counts as evidence.

**This file is the deliverable, not the config change it protects.** The defect
it exists to catch shipped as a one-line edit that looked obviously right:
`BANKROLL_DOLLARS` from 1000 to 100, matching the operator's real bankroll. What
that would have done, silently:

- Quarter-Kelly at $100 sizes below one contract across the 50c band -- the
  band this strategy trades -- so `suggested_contracts` is 0 on those rows.
- `gate.POPULATIONS["actionable"]` was defined on `suggested_contracts > 0`, so
  the `actionable` count would be confined to the far wings. Measured after the
  fact by `measurement-skeptic`: 204 of 999 asks survive, all of them at
  0.1-10.1c or 88.1-98.8c.
- The 300-game floor could therefore not realistically increment, and what did
  accumulate would be drawn entirely from the prices this project has the most
  reason to distrust -- the wings are where the fee is largest as a share of
  stake and where the devig methods disagree most. That is worse than an honest
  zero, because it produces evidence rather than silence.
- The Gate screen would go on reading "0 of 300, keep recording" -- a message
  that is true, unfalsifiable, and points at the wrong thing.

Nothing would have errored. No test was red. The counter would simply have
stopped being able to move, and the one screen that reports progress would have
described that as progress.

Two independent statements are asserted here, and the second is the one with
teeth:

1. At the **configured** bankroll -- whatever it is, read from config, not
   hardcoded -- an edge below `edge_ceiling_tenths` must produce a non-zero
   size. Without this the two limits on the edge do not intersect: at $100 the
   edge needed to reach the old 10-contract minimum was ~10 points at the 50c
   band, while anything above 4 points is suppressed as a suspected bug. There
   was no price on the board where an edge was simultaneously large enough to
   size and small enough to be believed.
2. `reference_contracts` -- the column the gate counts -- is **invariant to the
   bankroll**. That is what makes the record a property of the strategy rather
   than of the account.

Every assertion here was run against the pre-fix code and observed to fail. A
test written after a fix, never seen red, is decoration.

What this file does NOT establish: that any edge exists, that the gate should
open, or that a bet at $100 is a good idea. It establishes only that the size of
the deposit cannot silently switch off the measurement.
"""

from __future__ import annotations

import logging
import sqlite3

import pytest

from backend.config import (
    REFERENCE_BANKROLL_DOLLARS,
    RiskConfig,
    retired_settings_present,
)
from backend.core.ev import edge_after_fees_tenths, effective_price
from backend.core.sizing import size_position
from backend.core.suppression import SuppressionConfig
from backend.gate import POPULATIONS

# The bands this tool actually trades, plus both wings. 50c is where the fee is
# largest in absolute terms and where the strategy lives; the wings are where
# the per-order rounding penalty is real.
BANDS = [100, 200, 300, 500, 700, 800, 900]

# Bankrolls worth asserting over. $100 is Joe's real one, $1,000 is what the
# deployed config carried, and $30 is below anything reasonable -- included
# because a rule that holds at the plausible values and breaks just outside them
# is a rule nobody can rely on.
BANKROLLS = [30.0, 100.0, 250.0, 1000.0]

# The largest order the caps permit, and therefore the size at which the post-fee
# edge is largest. Kept in one place because `risk_at` and
# `fair_just_under_the_ceiling` must agree about it or the fixtures drift past
# the ceiling they are built to sit under.
MAX_ORDER_CONTRACTS = 50


def risk_at(bankroll: float) -> RiskConfig:
    """The deployed risk profile, scaled to `bankroll` at constant fractions.

    10% in one market, 40% at risk at once, 10% lost in a day. Those are the
    fractions the $1,000 profile used, and holding them constant is the point:
    lowering the bankroll alone leaves a position cap larger than the whole
    account and a daily loss limit that can only fire once the money is gone.
    """
    return RiskConfig(
        bankroll_dollars=bankroll,
        kelly_fraction=0.25,
        max_order_contracts=MAX_ORDER_CONTRACTS,
        max_position_dollars=bankroll * 0.10,
        max_exposure_dollars=bankroll * 0.40,
        max_daily_loss_dollars=bankroll * 0.10,
    )


def fair_just_under_the_ceiling(ask_tenths: int, ceiling_tenths: float) -> float:
    """A fair value whose post-fee edge sits just inside the suspicion ceiling.

    Deliberately *just* inside rather than comfortably inside. The failure being
    guarded against is a range that does not intersect, and an intersection is
    tested at its boundary or not at all -- a fat edge in the middle of the
    believable range passes under a broken implementation and a working one.

    **The edge grows with order size**, because the fee amortises, so the
    ceiling has to be cleared at the *largest* order the caps permit rather than
    at one contract. The first version of this helper anchored on one contract
    and built fixtures whose edge crossed the ceiling by the time they were
    sized -- the test then failed on its own fixture, correctly.

    The `max(...)` is the other half: the fair value must also exceed the
    one-contract effective price, or Kelly is zero and the row cannot size at
    all. Both bounds are live -- at 20c they differ by 3 points.
    """
    cheapest = effective_price(ask_tenths, contracts=MAX_ORDER_CONTRACTS)
    dearest = effective_price(ask_tenths, contracts=1)
    return min(0.999, max(dearest + 0.001, cheapest + (ceiling_tenths - 1.0) / 1000.0))


class TestTheConfiguredBankrollCanStillProduceABet:
    """The test whose absence let a one-line config edit disable the record."""

    @pytest.mark.parametrize("bankroll", BANKROLLS)
    @pytest.mark.parametrize("ask_tenths", BANDS)
    def test_a_believable_edge_sizes_to_at_least_one_contract(
        self, bankroll, ask_tenths
    ):
        """Some edge below the suspicion ceiling must be bettable.

        If no edge satisfies both "large enough to size" and "small enough to
        believe", the tool cannot act at this bankroll and nothing says so. That
        is two limits on one quantity, and the tighter one wins in silence.
        """
        thresholds = SuppressionConfig()
        fair = fair_just_under_the_ceiling(ask_tenths, thresholds.edge_ceiling_tenths)

        result = size_position(
            side="yes",
            ask_tenths=ask_tenths,
            fair_probability=fair,
            risk=risk_at(bankroll),
            current_exposure_dollars=0.0,
        )

        edge = edge_after_fees_tenths(
            ask_tenths=ask_tenths,
            contracts=max(1, result.contracts),
            fair_probability=fair,
        )
        assert edge <= thresholds.edge_ceiling_tenths, (
            "the fixture must sit inside the believable range, or this test is "
            "asserting that an edge the system would suppress can be sized"
        )
        assert not result.refused, result.refusal_reason
        assert result.contracts >= 1, (
            f"at a ${bankroll:.0f} bankroll, a {edge / 10:.1f}c edge at "
            f"{ask_tenths / 10:.0f}c sizes to zero while the suspicion ceiling "
            f"is {thresholds.edge_ceiling_tenths / 10:.0f}c. The range of edges "
            f"large enough to size and the range small enough to believe do not "
            f"intersect, so nothing on the board is bettable and no screen says "
            f"why."
        )


class TestTheRecordIsInvariantToTheDeposit:
    """`reference_contracts` is what the gate counts, and it must not move."""

    @pytest.mark.parametrize("ask_tenths", BANDS)
    def test_the_reference_sizing_is_identical_at_every_bankroll(self, ask_tenths):
        """Bit-identical, not merely similar.

        `reference()` replaces the four dollar quantities with constants, so two
        configs differing only in bankroll must produce the same reference
        sizing. "Close enough" would let the counter drift with the deposit,
        which is the entire defect.
        """
        fair = fair_just_under_the_ceiling(ask_tenths, SuppressionConfig().edge_ceiling_tenths)
        sizes = {
            bankroll: size_position(
                side="yes",
                ask_tenths=ask_tenths,
                fair_probability=fair,
                risk=risk_at(bankroll).reference(),
                current_exposure_dollars=0.0,
            ).contracts
            for bankroll in BANKROLLS
        }
        assert len(set(sizes.values())) == 1, (
            f"the reference sizing moved with the deposit: {sizes}. The gate "
            f"counts this number, so a deposit change would rewrite what the "
            f"evidence record means."
        )

    @pytest.mark.parametrize("bankroll", BANKROLLS)
    def test_reference_uses_the_fixed_profile_not_the_configured_one(self, bankroll):
        reference = risk_at(bankroll).reference()
        assert reference.bankroll_dollars == REFERENCE_BANKROLL_DOLLARS
        assert reference.max_position_dollars == 100.0
        assert reference.max_exposure_dollars == 400.0
        assert reference.max_daily_loss_dollars == 100.0

    def test_strategy_parameters_are_carried_through_not_replaced(self):
        """Kelly and the order cap are strategy choices, not facts about money.

        Changing one *should* move the counter -- and `strategy_config_version`
        records which version wrote each row, so the two regimes can be told
        apart afterwards. A deposit is recorded nowhere and could not be.
        """
        configured = RiskConfig(
            bankroll_dollars=100.0, kelly_fraction=0.10, max_order_contracts=7,
            max_position_dollars=10.0, max_exposure_dollars=40.0,
            max_daily_loss_dollars=10.0,
        )
        reference = configured.reference()
        assert reference.kelly_fraction == 0.10
        assert reference.max_order_contracts == 7


class TestTheGateCountsTheReferenceColumn:
    """The predicate itself, because a comment about it is not a check."""

    def test_actionable_reads_reference_contracts_not_suggested_contracts(self):
        """Naming the column directly.

        Asserted on the SQL text because the failure this catches is someone
        restoring `suggested_contracts` here for tidiness -- which reads as a
        harmless simplification and re-couples the evidence floor to the
        deposit. The behavioural consequence is asserted in `test_gate.py`.
        """
        assert "reference_contracts" in POPULATIONS["actionable"]
        assert "suggested_contracts" not in POPULATIONS["actionable"]

    def test_an_unreadable_reference_size_is_not_actionable(self):
        """NULL must fall into `no_edge`, never `actionable`, and never nowhere.

        Run as SQL against real rows rather than matched as text. The textual
        version of this assertion was written first and was wrong in a way that
        looked right: `"IS NULL" not in POPULATIONS["actionable"]` fails on
        `suppressed_reason IS NULL`, which is a different column entirely. A
        predicate is a thing SQLite evaluates, so evaluate it.

        The v6 backfill leaves no NULLs behind, so this state cannot arise
        today. It is asserted because "unreadable resolves to something safe" is
        a rule this repo has broken four times, and the safe direction here is
        "not a bet".
        """
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE recommendations ("
            " id INTEGER PRIMARY KEY, suppressed_reason TEXT,"
            " suggested_contracts INTEGER, reference_contracts INTEGER)"
        )
        conn.executemany(
            "INSERT INTO recommendations "
            "(id, suppressed_reason, suggested_contracts, reference_contracts) "
            "VALUES (?, ?, ?, ?)",
            [
                # The row that matters: unreadable reference size, and a
                # *positive* suggested size, so a predicate that fell back to
                # the old column would call it actionable.
                (1, None, 12, None),
                (2, None, 0, 15),      # counted: the strategy had a bet here
                (3, None, 0, 0),       # no edge
                (4, "stale_odds", 0, 0),
            ],
        )

        def ids(population: str) -> set[int]:
            return {
                row["id"]
                for row in conn.execute(
                    "SELECT r.id FROM recommendations r "  # noqa: S608
                    f"WHERE {POPULATIONS[population]}"
                )
            }

        assert ids("actionable") == {2}
        assert ids("no_edge") == {1, 3}
        assert ids("suppressed") == {4}
        # Exhaustive and mutually exclusive, on the row that would break it.
        assert ids("actionable") | ids("no_edge") | ids("suppressed") == {1, 2, 3, 4}
        assert not ids("actionable") & ids("no_edge")


class TestTheRemovedSettingIsAnnouncedAndNeverFatal:
    """Loud, and specifically **not** a refusal to start.

    A removed setting still in an environment must not be silent: this one was
    load-bearing and wrong, and below roughly a $250 bankroll it closed the 50c
    band this strategy trades. Someone re-adding it after reading an old handoff
    must be told.

    The first version raised `ConfigError`, which is this repo's usual
    preference and was wrong *here*. `RiskConfig.load()` runs inside
    `create_app`; uvicorn runs that at boot; `docker/entrypoint.sh` supervises
    uvicorn with `wait -n`. So a raise is a container crash loop -- and it lands
    **after** `scripts/migrate_db.py` has already moved the volume forward, so
    an image rollback does not recover it either, because the old code refuses a
    newer schema. Only `flyctl secrets unset` would, and flyctl is a laptop job
    while this tool is operated from a phone.

    A guard whose failure mode is unrecoverable from the operator's only device
    is not a safety property. So this is announced in two places a phone can
    reach -- the log and `/api/health` -- and enforced in neither.
    """

    def test_a_retired_setting_does_not_stop_the_process_starting(self, monkeypatch):
        monkeypatch.setenv("MIN_ORDER_CONTRACTS", "10")
        risk = RiskConfig.load()
        # And it is genuinely not read -- no field silently absorbed it.
        assert not hasattr(risk, "min_order_contracts")

    def test_it_is_named_with_its_reason(self, monkeypatch):
        monkeypatch.setenv("MIN_ORDER_CONTRACTS", "10")
        present = retired_settings_present()
        assert "MIN_ORDER_CONTRACTS" in present
        assert "ADR 0015" in present["MIN_ORDER_CONTRACTS"]

    def test_it_is_logged_at_error_on_every_load(self, monkeypatch, caplog):
        """Every load, not once per process.

        A once-per-process line is invisible to anyone who did not catch the
        boot, and the live log stream is a lossy 100-line buffer -- this repo
        has already lost two boot lines to a burst that way.
        """
        monkeypatch.setenv("MIN_ORDER_CONTRACTS", "10")
        with caplog.at_level(logging.ERROR, logger="backend.config"):
            RiskConfig.load()
            RiskConfig.load()
        said = [r for r in caplog.records if "MIN_ORDER_CONTRACTS" in r.getMessage()]
        assert len(said) == 2

    def test_an_empty_value_is_not_a_setting(self, monkeypatch):
        """An unset variable that fly renders as `""` is not a stale setting."""
        monkeypatch.setenv("MIN_ORDER_CONTRACTS", "")
        assert retired_settings_present() == {}

    def test_nothing_retired_is_the_healthy_state(self, monkeypatch):
        monkeypatch.delenv("MIN_ORDER_CONTRACTS", raising=False)
        assert retired_settings_present() == {}
