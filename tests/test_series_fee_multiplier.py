"""The fee split is series metadata, and Kalshi publishes it: `fee_multiplier`.

Fleet convening item 9. The 2026-08-14 attribution pinned the charged taker fee
to `ceil(k * C * P * (1-P))` at the $0.0001 grid with `k` splitting cleanly by
series -- MLB at ~0.035, ATP/WNBA at ~0.07 -- and ADR 0028 left *which
attribute carries the split* unresolved: sport, series, and a per-market
liquidity tier all fit 11 fills identically. The claim that `/series` metadata
settles it rested on one uncommitted live read, which is exactly the kind of
good news that gets more scrutiny, not less.

`tests/fixtures/series_fee_fields.json` (captured 2026-08-20) is that read,
committed: `fee_multiplier` is 0.5 on both MLB series and 1 on KXATPDOUBLES
and KXWNBAGAME. This file closes the loop by prediction: from the fixture's
multiplier and the deployed base coefficient alone, the charged fee on **all
11 attributed fills** must reproduce to $0.0001. No admissible-interval
argument, no fitting -- predict and compare.

What this does not establish
----------------------------
- **Nothing about the applied bar moving.** `TAKER_COEFFICIENT` stays 0.070
  in `core/fees.py` until an ADR moves it; this file supplies the durable
  source ADR 0028 said was missing, and the decision remains a decision.
- **Nothing about maker fees**, which these 11 fills never exercised, or
  about `fee_type` (`quadratic` vs `quadratic_with_maker_fees` varies across
  the four series and is not consumed here).
- **Nothing about series beyond the four captured**, or about the schedule
  not changing again -- the 2025-11 -> 2026-08 revision is the reason the
  guard exists.
- H4 (whether settlement carries its own fee) is untouched.
"""

from __future__ import annotations

import json
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

import pytest

from backend.core.fees import TAKER_COEFFICIENT

ROOT = Path(__file__).resolve().parents[1]
SERIES_FIXTURE = ROOT / "tests" / "fixtures" / "series_fee_fields.json"
# The operator's PRIVATE capture, under gitignored `data/` -- deliberately
# not in the repo, and (2026-08-20, Joe's ruling) never to be, sanitized or
# otherwise: this tool should anticipate operators other than its author,
# and a repo whose tests require the operator's account data cannot be
# handed to one. The fills half of this suite therefore runs ONLY on a
# machine holding the capture and skips loudly elsewhere; CI green means
# the fixture-side tests passed and the fills prediction was NOT exercised.
# (History: this path was once claimed to be "tracked in git" -- it never
# was, CI was red from the day the claim shipped, and a sanitized committed
# copy existed for ~90 minutes before the privacy ruling removed it.)
FILLS_CAPTURE = ROOT / "data" / "captures" / "portfolio_fills.json"

requires_private_capture = pytest.mark.skipif(
    not FILLS_CAPTURE.exists(),
    reason=(
        "data/captures/portfolio_fills.json is the operator's private fills "
        "capture and is never committed; the fee prediction runs only where "
        "it exists (regenerate with scripts/capture_fills_fixture.py)"
    ),
)

DECI_CENT = Decimal("0.0001")

#: The population, fixed by the attribution: taker fills in these four series.
FOUR_SERIES = ("KXMLBGAME", "KXMLBSPREAD", "KXATPDOUBLES", "KXWNBAGAME")


def _series_multipliers() -> dict[str, Decimal]:
    payloads = json.loads(SERIES_FIXTURE.read_text(encoding="utf-8"))["payloads"]
    out = {}
    for ticker, payload in payloads.items():
        series = payload.get("series", payload)
        out[ticker] = Decimal(str(series["fee_multiplier"]))
    return out


def _attributed_fills() -> list[dict]:
    fills = json.loads(FILLS_CAPTURE.read_text(encoding="utf-8"))["payload"]["fills"]
    return [
        f
        for f in fills
        if f["ticker"].split("-")[0] in FOUR_SERIES and f["is_taker"]
    ]


class TestTheFixtureCarriesTheSplit:
    def test_all_four_series_are_captured_with_a_multiplier(self):
        multipliers = _series_multipliers()
        assert set(multipliers) == set(FOUR_SERIES)

    def test_the_multipliers_are_the_measured_split(self):
        """0.5 on the k~=0.035 group, 1 on the k~=0.070 group. If a re-capture
        ever changes these, the schedule moved again and the fee model needs
        re-attribution BEFORE this assertion is updated -- updating the number
        to match a new fixture without re-running the fills prediction is
        exactly the not-noticing ADR 0028 warns about."""
        multipliers = _series_multipliers()
        assert multipliers["KXMLBGAME"] == Decimal("0.5")
        assert multipliers["KXMLBSPREAD"] == Decimal("0.5")
        assert multipliers["KXATPDOUBLES"] == Decimal("1")
        assert multipliers["KXWNBAGAME"] == Decimal("1")


@requires_private_capture
class TestTheMultiplierPredictsEveryFill:
    """The verification the convening required: all 11, to $0.0001, from the
    fixture and the deployed base coefficient alone.

    Mutation observed red: swap the two multiplier groups in a copy of the
    fixture (0.5 <-> 1) -- every MLB prediction doubles and every ATP/WNBA
    prediction halves, and `test_all_eleven_reproduce_exactly` fails on all
    11 rows.
    """

    def test_the_population_is_exactly_the_eleven(self):
        fills = _attributed_fills()
        assert len(fills) == 11
        assert len({f["order_id"] for f in fills}) == 11, (
            "a multi-fill order appeared; the per-order ceiling must group "
            "before predicting"
        )

    def test_all_eleven_reproduce_exactly(self):
        multipliers = _series_multipliers()
        base = Decimal(str(TAKER_COEFFICIENT))
        for fill in _attributed_fills():
            series = fill["ticker"].split("-")[0]
            k = base * multipliers[series]
            contracts = Decimal(fill["count_fp"])
            # The YES price regardless of taken side: P(1-P) is symmetric in
            # the complement, so the side cannot flip the fee -- the same
            # reading `reconcile_observed_fees.py` uses.
            price = Decimal(fill["yes_price_dollars"])
            predicted = (k * contracts * price * (Decimal(1) - price)).quantize(
                DECI_CENT, rounding=ROUND_CEILING
            )
            charged = Decimal(fill["fee_cost"]).quantize(DECI_CENT)
            assert predicted == charged, (
                f"{fill['ticker']}: predicted {predicted} != charged "
                f"{charged} (k = {base} x {multipliers[series]}, C = "
                f"{contracts}, P = {price})"
            )

    def test_the_base_coefficient_is_the_deployed_one(self):
        """The prediction ties the fixture to `core/fees.py`'s coefficient,
        not to a constant restated here -- two spellings of the fee base is
        the drift `assert_*_agree` guards exist for elsewhere."""
        assert Decimal(str(TAKER_COEFFICIENT)) == Decimal("0.07")


class TestTheCaptureIsReplayableNotAssumed:
    def test_the_fixture_names_its_endpoint_and_instant(self):
        payload = json.loads(SERIES_FIXTURE.read_text(encoding="utf-8"))
        assert payload["endpoint"] == "/series/{ticker}"
        assert payload["captured_at"].startswith("2026-")

    @requires_private_capture
    def test_the_capture_is_the_shape_the_predictions_consume(self):
        """Where the private capture exists, it must be readable and carry
        the consumed fields -- a malformed capture must fail here, by name,
        rather than inside a prediction assertion. Where it does not exist,
        the skip reason on the class says what is NOT being verified; a
        skip is the honest state for data the repo deliberately excludes
        (2026-08-20 ruling: operator account data never enters the repo,
        sanitized or otherwise)."""
        fills = json.loads(FILLS_CAPTURE.read_text(encoding="utf-8"))[
            "payload"
        ]["fills"]
        assert fills, "capture holds no fills"
        for field in ("ticker", "is_taker", "order_id", "count_fp",
                      "yes_price_dollars", "fee_cost"):
            assert field in fills[0], field
