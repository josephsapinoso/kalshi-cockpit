"""The shard balance the RFQ wall measures against, pinned to a shape (#75).

`read_shard_funds` gates money on the RFQ path since `523fbda`, and its
"dollars as a 4dp string" comment was an assertion with no captured payload
behind it. The alternative was not academic: Kalshi's TOP-LEVEL `balance` is an
integer in CENTS, and a cents reading of the breakdown would make
`available_tenths` 100x high and the shard wall would never fire at all.

The shape here was read off 72 real captured payloads held outside the repo
(`data/`, gitignored, operator data). They returned exactly one shape.

What these do not establish
---------------------------
- **Nothing from a real payload.** The fixture is SYNTHETIC by Joe's standing
  ruling that account data never enters this public repo, even sanitized --
  the same exception ADR 0035 makes for MLBAM, and for the same reason. These
  pin the shape; `docs/measurements/2026-09-18-the-shard-balance-is-dollars.md`
  carries what the real captures showed, without the figures.
- **Nothing about the venue changing its mind.** A shape held across 72
  payloads captured on one day in September 2026 is not a contract. If the
  cross-check in the measurement doc ever fails, this file is wrong and must
  be re-derived, not adjusted.
- **Nothing about whether the shard wall's 10% margin is the right margin.**
  That is a question for Joe and it is #71.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from backend.kalshi.rest import EXCHANGE_INDEX_COMBOS
from backend.store.combo_orders import read_shard_funds

FIXTURE = Path(__file__).parent / "fixtures" / "portfolio_balance_shape.json"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestTheShapeThatWasMeasured:
    """The two fields are in DIFFERENT units in the same payload."""

    def test_the_top_level_balance_is_an_integer(self):
        """Integer, and it is cents. It must never be read as a shard figure."""
        assert isinstance(_payload()["balance"], int)

    def test_every_breakdown_balance_is_a_four_decimal_dollar_string(self):
        for row in _payload()["balance_breakdown"]:
            raw = row["balance"]
            assert isinstance(raw, str), f"{raw!r} is not a string"
            assert re.fullmatch(r"\d+\.\d{4}", raw), f"{raw!r} is not 4dp dollars"

    def test_the_two_readings_cross_check_each_other(self):
        """This is what makes the units a measurement rather than a guess.

        Read the top level as cents and the rows as dollars and they agree.
        Under any other pairing they are ~100x apart, which is exactly the
        error that would have disarmed the shard wall.
        """
        payload = _payload()
        rows = sum(float(r["balance"]) for r in payload["balance_breakdown"])
        as_cents = payload["balance"] / 100.0
        assert abs(as_cents - rows) < 0.05, "the cents/dollars pairing disagrees"

        # ...and the pairing that would have been wrong is visibly wrong.
        rows_as_cents = rows / 100.0
        assert abs(as_cents - rows_as_cents) > 1.0, (
            "a cents reading of the breakdown is supposed to be ~100x off; "
            "if this fails the fixture's figures no longer separate the two"
        )


class TestTheShardFigureTheWallUses:
    def test_a_shard_balance_becomes_tenths_of_a_cent(self):
        """$0.0100 on shard 1 is 10 tenths of a cent."""
        funds = read_shard_funds(_payload(), exchange_index=EXCHANGE_INDEX_COMBOS)
        assert funds.available_tenths == 10

    def test_shard_zero_is_read_from_its_own_row(self):
        """$12.3400 -> 12,340 tenths. Wrong by 100x under a cents reading."""
        funds = read_shard_funds(_payload(), exchange_index=0)
        assert funds.available_tenths == 12_340

    def test_a_sub_tenth_balance_floors_rather_than_rounds_up(self):
        """4dp dollars is HUNDREDTHS of a cent -- finer than our unit.

        `$0.0105` is 10.5 tenths of a cent. `round` gives 10 here by
        half-to-even and 11 for `$0.0115`; either way it can report money the
        shard does not have, and a headroom check that rounds UP is a guard
        erring in the one direction this repo refuses. Floor always
        under-reports.

        Same centi-cent resolution ADR 0172 found on combination quotes. There
        the desk refuses the value outright, because it is a PRICE and a
        rounded price is a price the venue never offered. Here it floors,
        because it is a BALANCE and a ceiling on spending may be understated
        but never overstated.
        """
        payload = _payload()
        payload["balance_breakdown"][1]["balance"] = "0.0105"
        assert read_shard_funds(
            payload, exchange_index=EXCHANGE_INDEX_COMBOS
        ).available_tenths == 10

        payload["balance_breakdown"][1]["balance"] = "0.0115"
        assert read_shard_funds(
            payload, exchange_index=EXCHANGE_INDEX_COMBOS
        ).available_tenths == 11

    def test_an_unreadable_balance_is_none_not_zero(self):
        """A zero says the shard is empty, which is a fact. This is not it."""
        payload = _payload()
        payload["balance_breakdown"][1]["balance"] = "not-a-number"
        assert read_shard_funds(
            payload, exchange_index=EXCHANGE_INDEX_COMBOS
        ).available_tenths is None

    def test_a_missing_shard_row_is_none_not_zero(self):
        payload = _payload()
        payload["balance_breakdown"] = [
            r for r in payload["balance_breakdown"]
            if r["exchange_index"] != EXCHANGE_INDEX_COMBOS
        ]
        assert read_shard_funds(
            payload, exchange_index=EXCHANGE_INDEX_COMBOS
        ).available_tenths is None

    def test_the_top_level_integer_is_never_used_as_the_shard_figure(self):
        """The 100x bug, written as a test.

        A payload whose breakdown is absent must refuse, NOT fall back to the
        top-level integer -- which is cents, for the whole account, across
        every shard.
        """
        assert read_shard_funds(
            {"balance": 1234}, exchange_index=EXCHANGE_INDEX_COMBOS
        ).available_tenths is None
