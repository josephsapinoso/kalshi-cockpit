"""The create-order response parser, against the shape the C0 probe observed.

Until 2026-08-23 `_read_response`'s docstring said "**This shape has never
been observed**" -- it was transcribed from Kalshi's OpenAPI spec and the
first live order would have been its first test. The C0 probe
(docs/runbooks/c0-create-order-probe.md) has now run: four probes against
KXNCAAFGAME-26SEP03EIUMINN-EIU on 2026-08-23, statuses 201/409/201/201+200,
capture held locally (SHA-256 69d72b12d91f...), never committed.

The fixture here is SYNTHETIC, hand-written from the observed shape -- the
ADR 0035 precedent, prescribed by the runbook because the raw capture is
operator data. That is a deliberate exception to the load_fixture rule that
wire fixtures must be captured payloads; the shape assertions below are what
keep the synthetic honest.

What this does not establish: one ticker, one day, one series. The shapes
may not generalise, the parser keeps refusing loudly on missing fields, and
one 409 observation is not a licence to retry blindly.
"""

import json
from pathlib import Path

from backend.core.fees import calculate_fee
from backend.kalshi.grid import parse_price_grid
from backend.kalshi.orders import (
    STATUS_FILLED,
    STATUS_RESTING,
    STATUS_UNFILLED,
    STATUS_UNRECOGNISED,
    OrderPlacer,
    OrderRequest,
)

FIXTURE = Path(__file__).parent / "fixtures" / "create_order_responses.json"

LINEAR_CENT = parse_price_grid(
    [{"start": "0.0000", "end": "1.0000", "step": "0.0100"}],
    structure="linear_cent",
)


def _responses() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _request(price_tenths: int = 20, tif: str = "immediate_or_cancel") -> OrderRequest:
    return OrderRequest(
        ticker="KXNCAAFGAME-26SEP03EIUMINN-EIU",
        side="yes",
        action="buy",
        count=1,
        limit_price_tenths=price_tenths,
        price_grid=LINEAR_CENT,
        time_in_force=tif,
    )


def _parse(payload: dict):
    placer = OrderPlacer(dry_run=True)
    request = _request()
    return placer._read_response(request, request.to_api_dict(), payload)


class TestTheObservedCreateShapeParses:
    def test_an_ioc_that_matched_no_one_is_unfilled(self):
        outcome = _parse(_responses()["create_ioc_unfilled_201"])
        assert outcome.status == STATUS_UNFILLED
        assert outcome.kalshi_order_id is not None
        assert outcome.fill_count == 0.0
        assert outcome.remaining_count == 0.0
        assert outcome.error_text is None

    def test_a_filled_ioc_carries_its_measured_price_and_fee(self):
        outcome = _parse(_responses()["create_ioc_filled_201"])
        assert outcome.status == STATUS_FILLED
        assert outcome.average_fill_price_dollars == "0.0200"
        assert outcome.average_fee_paid_dollars == "0.0014"

    def test_a_gtc_with_remainder_is_resting(self):
        outcome = _parse(_responses()["create_gtc_resting_201"])
        assert outcome.status == STATUS_RESTING

    def test_a_missing_order_id_refuses_rather_than_guessing(self):
        payload = dict(_responses()["create_ioc_unfilled_201"])
        del payload["order_id"]
        outcome = _parse(payload)
        assert outcome.status == STATUS_UNRECOGNISED
        assert "client_order_id" in (outcome.error_text or "")


class TestTheFixtureStaysTrueToTheObservation:
    """Shape assertions -- what keeps a synthetic fixture honest (ADR 0035)."""

    def test_the_create_response_is_flat_with_no_order_wrapper(self):
        # The spec-transcription hazard this probe existed to catch: some
        # Kalshi endpoints wrap payloads ("market", "orderbook_fp"); the
        # observed create response does NOT wrap in "order".
        for key in ("create_ioc_unfilled_201", "create_ioc_filled_201",
                    "create_gtc_resting_201"):
            payload = _responses()[key]
            assert "order" not in payload
            assert "order_id" in payload

    def test_counts_are_fixed_point_decimal_strings(self):
        for key in ("create_ioc_unfilled_201", "create_ioc_filled_201",
                    "create_gtc_resting_201"):
            payload = _responses()[key]
            for field in ("fill_count", "remaining_count"):
                assert isinstance(payload[field], str)
                float(payload[field])  # parseable, or this raises

    def test_money_fields_are_dollar_strings_at_four_places(self):
        filled = _responses()["create_ioc_filled_201"]
        for field in ("average_fill_price", "average_fee_paid"):
            whole, dot, frac = filled[field].partition(".")
            assert dot == "." and len(frac) == 4

    def test_a_duplicate_client_order_id_conflicts_with_a_named_code(self):
        # Probe 2 re-POSTed probe 1's exact body and Kalshi answered 409.
        # One observation: recorded as the shape of the refusal, not as a
        # licence to retry blindly.
        body = _responses()["duplicate_client_order_id_409"]
        assert body["error"]["code"] == "order_already_exists"

    def test_a_cancel_reports_how_much_it_reduced(self):
        body = _responses()["cancel_200"]
        assert isinstance(body["reduced_by"], str)
        assert float(body["reduced_by"]) == 1.0


class TestTheFeeModelPredictedTheObservedFill:
    def test_the_twelfth_fill_matches_model_a_exactly(self):
        """The probe's 2c x 1 taker fill paid $0.0014 -- the first non-MLB
        fill this project has observed, and `calculate_fee` predicts it to
        the observed $0.0001 precision at the full 0.070 coefficient. One
        observation on one series: consistent with the series-attribute
        resolution of the baseball split, and pinning nothing beyond this
        cell."""
        observed = _responses()["create_ioc_filled_201"]["average_fee_paid"]
        assert calculate_fee(20, 1) == float(observed)
