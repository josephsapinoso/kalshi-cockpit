"""What the venue said it charged, on the permanent row.

Every price on `manual_orders` until this change was the ask the desk SENT:
`limit_price_tenths` is `OrderRequest.fill_price_tenths`, frozen by
`_insert_intent` before the request left the process. `record_outcome` then
stamped `status`, `kalshi_order_id` and `error_text` and dropped the venue's
own `fill_count`, `average_fill_price` and `average_fee_paid` on the floor.
Those three survive elsewhere only in `fills`, on a ~3-month retention window,
while this table is permanent.

The claims below are about the three new columns and nothing else: that a
filled order records what the venue reported, that the three ways of having
nothing to report stay NULL rather than zero, that the sub-tenth fee digit is
not thrown away, and that a failure to read any of it cannot cost the row its
status.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- Nothing about whether the venue's numbers are RIGHT. This records what came
  back; `docs/measurements/2026-09-10-preregistration-recorded-fill-vs-venue-
  charge.md` is the census that will compare them against what the desk sent,
  and it cannot run on rows that do not carry the venue side.
- Nothing about `/hedge`'s figure becoming exact. Two independent errors make
  it an upper bound and this closes one of them; the settlement charge (H4,
  ADR 0027) is untested and still open.
- Nothing that generalises the response shape. The fixture is the C0 probe's
  one ticker, one day, one series, and it is SYNTHETIC by the ADR 0035
  precedent -- the shape assertion below is what keeps it honest.
- Nothing about the engine path or `combo_orders`, whose own `record_outcome`
  is untouched.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from backend.core.prices import dollars_to_tenths
from backend.kalshi.grid import parse_price_grid
from backend.kalshi.orders import (
    STATUS_REJECTED,
    OrderOutcome,
    OrderPlacer,
    OrderRequest,
)
from backend.store import db
from backend.store import manual_orders as manual_store

REPO = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "create_order_responses.json"

TICKER = "KXNCAAFGAME-26SEP03EIUMINN-EIU"

LINEAR_CENT = parse_price_grid(
    [{"start": "0.0000", "end": "1.0000", "step": "0.0100"}],
    structure="linear_cent",
)

#: The three columns this module is about, in the order they are written.
VENUE_COLUMNS = (
    "venue_fill_count",
    "venue_avg_fill_price_tenths",
    "venue_avg_fee_dollars",
)


def _responses() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _request(price_tenths: int = 500) -> OrderRequest:
    return OrderRequest(
        ticker=TICKER,
        side="yes",
        action="buy",
        count=1,
        limit_price_tenths=price_tenths,
        price_grid=LINEAR_CENT,
        time_in_force="immediate_or_cancel",
    )


def _outcome_from(payload: dict, request: OrderRequest) -> OrderOutcome:
    """A live outcome, parsed from a captured payload by the real parser."""
    placer = OrderPlacer(dry_run=True)
    return placer._read_response(request, request.to_api_dict(), payload)


def _row(path, request: OrderRequest, outcome: OrderOutcome) -> sqlite3.Row:
    """Reserve an intent for `request`, stamp `outcome` on it, read it back."""
    conn = db.open_db(path)
    try:
        row_id = manual_store.reserve_manual_order(
            conn,
            request,
            dry_run=outcome.dry_run,
            submitted_ms=1_700_000_000_000,
            max_price_tenths=900,
        )
        manual_store.record_outcome(conn, row_id, outcome)
        return conn.execute(
            "SELECT * FROM manual_orders WHERE id = ?", (row_id,)
        ).fetchone()
    finally:
        conn.close()


@pytest.fixture
def path(tmp_path):
    conn = db.init_db(tmp_path / "cockpit.db")
    conn.close()
    return tmp_path / "cockpit.db"


class TestTheCapturedShapeCarriesWhatIsBeingStored:
    """The fixture is synthetic; this is the assertion that keeps it honest."""

    def test_the_filled_response_sends_a_count_string_and_two_dollar_strings(self):
        filled = _responses()["create_ioc_filled_201"]
        assert re.fullmatch(r"\d+\.\d{2}", filled["fill_count"]), (
            "V2 counts are fixed-point decimal STRINGS; an int here would mean "
            "the column type argument for REAL was made against a shape the "
            "venue does not send"
        )
        for key in ("average_fill_price", "average_fee_paid"):
            assert re.fullmatch(r"\d+\.\d{4}", filled[key]), (
                f"{key} is a 4dp dollar STRING -- 4dp is what puts a single "
                f"fill's price on the tenths grid and the fee below it"
            )

    def test_the_unfilled_response_carries_no_money_fields_at_all(self):
        """The zero-fill case is an ABSENCE of money, not a zero."""
        unfilled = _responses()["create_ioc_unfilled_201"]
        assert unfilled["fill_count"] == "0.00"
        assert "average_fill_price" not in unfilled
        assert "average_fee_paid" not in unfilled


class TestAFilledOrderRecordsWhatTheVenueReported:
    def test_the_venue_price_is_stored_in_tenths_on_the_same_scale_as_the_ask(
        self, path
    ):
        """Mutation observed red: drop `venue_avg_fill_price_tenths` from the
        UPDATE's column list -- the column reads None and this fails."""
        request = _request()
        row = _row(path, request, _outcome_from(
            _responses()["create_ioc_filled_201"], request
        ))
        # "0.0200" -> 20 tenths, exactly. 4dp IS tenths of a cent.
        assert row["venue_avg_fill_price_tenths"] == 20

    def test_the_fill_count_is_the_venue_count_and_not_the_requested_count(
        self, path
    ):
        request = _request()
        row = _row(path, request, _outcome_from(
            _responses()["create_ioc_filled_201"], request
        ))
        assert row["venue_fill_count"] == 1.0
        assert row["count"] == 1

    def test_the_sent_ask_and_the_venue_price_stay_separate_columns(self, path):
        """The whole point: one row now carries both, and they differ.

        `limit_price_tenths` is what the desk sent (500 tenths here, snapped);
        the venue reported 20. A record that kept only the first cannot say
        what was charged, which is why `/hedge`'s figure is an upper bound.
        """
        request = _request(price_tenths=500)
        row = _row(path, request, _outcome_from(
            _responses()["create_ioc_filled_201"], request
        ))
        assert row["limit_price_tenths"] == request.fill_price_tenths == 500
        assert row["venue_avg_fill_price_tenths"] == 20
        assert row["limit_price_tenths"] != row["venue_avg_fill_price_tenths"]

    def test_the_fee_keeps_the_digit_that_tenths_would_have_thrown_away(
        self, path
    ):
        """The fee is dollars, and this is why.

        "0.0014" is 1.4 tenths of a cent. Stored through `dollars_to_tenths`
        it would be `1` -- a 29% understatement of the only number on the row
        that says what the venue charged.
        """
        request = _request()
        row = _row(path, request, _outcome_from(
            _responses()["create_ioc_filled_201"], request
        ))
        assert row["venue_avg_fee_dollars"] == pytest.approx(0.0014)
        assert dollars_to_tenths("0.0014") == 1, (
            "if this ever stops being lossy the dollars exception can be "
            "revisited; until then the column type is load-bearing"
        )


class TestNothingToReportIsNullAndNeverZero:
    """A dry run, a rejection and a zero fill are three different states, and
    none of them is 'the venue charged nothing'."""

    async def test_a_dry_run_records_none_of_the_three(self, path):
        request = _request()
        outcome = await OrderPlacer(dry_run=True).place(request)
        row = _row(path, request, outcome)
        assert outcome.dry_run is True
        for column in VENUE_COLUMNS:
            assert row[column] is None, column

    def test_a_rejected_order_records_none_of_the_three(self, path):
        """A failed POST may still have reached Kalshi. What is certain is
        that no response was ever read, so there is nothing to write."""
        request = _request()
        outcome = OrderOutcome(
            request=request,
            status=STATUS_REJECTED,
            dry_run=False,
            request_body=request.to_api_dict(),
            error_text="connection reset",
        )
        row = _row(path, request, outcome)
        assert row["status"] == STATUS_REJECTED
        for column in VENUE_COLUMNS:
            assert row[column] is None, column

    def test_a_zero_fill_records_the_count_and_leaves_the_money_null(self, path):
        """The distinction this whole block exists for.

        An IOC that matched no one filled zero contracts -- a real, observed
        `0.0` -- and the venue quoted no price and charged no fee, which is
        different from a price of zero and a fee of zero.
        """
        request = _request()
        row = _row(path, request, _outcome_from(
            _responses()["create_ioc_unfilled_201"], request
        ))
        assert row["venue_fill_count"] == 0.0
        assert row["venue_avg_fill_price_tenths"] is None
        assert row["venue_avg_fee_dollars"] is None

    def test_a_resting_order_records_the_count_and_leaves_the_money_null(
        self, path
    ):
        request = _request()
        row = _row(path, request, _outcome_from(
            _responses()["create_gtc_resting_201"], request
        ))
        assert row["venue_fill_count"] == 0.0
        assert row["venue_avg_fill_price_tenths"] is None
        assert row["venue_avg_fee_dollars"] is None


class TestTheParsersRefuseRatherThanRecordAPlausibleNumber:
    def test_a_zero_price_is_refused_because_zero_is_a_settled_outcome(self):
        """Mutation observed red: drop the `is_valid_price` arm from
        `_venue_price_tenths` -- "0.0000" is recorded as 0 tenths, which reads
        as a contract that settled worthless rather than as an absence."""
        assert manual_store._venue_price_tenths("0.0000") is None

    def test_a_price_at_or_above_a_dollar_is_refused(self):
        assert manual_store._venue_price_tenths("1.0000") is None
        assert manual_store._venue_price_tenths("1.5000") is None

    def test_a_negative_price_is_refused(self):
        assert manual_store._venue_price_tenths("-0.2000") is None

    def test_an_unparseable_price_is_refused(self):
        for value in (None, "", "nan", "Infinity", "banana", object()):
            assert manual_store._venue_price_tenths(value) is None, value

    def test_a_tradeable_price_is_kept(self):
        """The refusals above are only worth something if the accept works."""
        assert manual_store._venue_price_tenths("0.0200") == 20
        assert manual_store._venue_price_tenths("0.9990") == 999

    def test_a_single_fill_price_converts_without_rounding(self):
        """4dp IS tenths of a cent, so every price the venue can quote for one
        fill lands on the grid and nothing is lost."""
        for tenths in (1, 20, 205, 500, 999):
            assert manual_store._venue_price_tenths(
                f"{tenths / 1000:.4f}"
            ) == tenths

    def test_an_averaged_price_between_two_tenths_is_rounded_not_refused(self):
        """**The one place this column is not exact**, and it is a rounding
        rather than a refusal.

        `average_fill_price` is volume-weighted across several fills, so it
        can land between tenths even though no single fill can. Half a tenth
        is a twentieth of a cent; refusing the row over it would discard the
        venue's answer to keep a purity the column never claimed. The
        docstring says so rather than leaving it to be discovered.
        """
        assert manual_store._venue_price_tenths("0.2005") == 201
        assert manual_store._venue_price_tenths("0.2004") == 200

    def test_a_negative_fee_is_refused(self):
        """Mutation observed red: drop the `< 0` arm from `_venue_fee_dollars`
        -- a negative fee is recorded as a rebate the venue does not pay."""
        assert manual_store._venue_fee_dollars("-0.0100") is None

    def test_a_non_finite_fee_is_refused(self):
        """`Decimal("nan")` and `Decimal("Infinity")` CONSTRUCT, so the
        try/except alone never sees them -- `core/prices` was caught by
        exactly this."""
        for value in ("nan", "Infinity", "-Infinity"):
            assert manual_store._venue_fee_dollars(value) is None, value

    def test_a_zero_fee_is_kept_because_the_venue_can_charge_zero(self):
        """Not every zero is an absence. A fee of zero is a thing that can
        happen on a fill; a PRICE of zero is not."""
        assert manual_store._venue_fee_dollars("0.0000") == 0.0

    def test_a_negative_fill_count_is_refused(self):
        """Mutation observed red: drop the `< 0` arm from `_venue_count`."""
        assert manual_store._venue_count(-1.0) is None

    def test_a_non_finite_fill_count_is_refused(self):
        """Mutation observed red: drop `math.isfinite` from `_venue_count` --
        a NaN reaches the column and every later comparison against it is
        false, silently."""
        assert manual_store._venue_count(float("nan")) is None
        assert manual_store._venue_count(float("inf")) is None

    def test_a_fractional_fill_count_survives(self):
        """REAL, not INTEGER: the venue supports fractional contracts to 0.01
        and an int column would truncate 0.41 to 0."""
        assert manual_store._venue_count(0.41) == 0.41


class TestTheVenueReadCanNeverCostTheRowItsStatus:
    """By the time `record_outcome` runs the request has gone. A bookkeeping
    failure must never report a completed purchase as failed."""

    def test_a_raising_read_still_stamps_the_status(self, path, monkeypatch):
        """Mutation observed red: remove the `except Exception` from
        `venue_fill` -- `record_outcome` raises and a real fill is recorded
        as still pending."""
        def boom(outcome):
            raise RuntimeError("the venue read fell over")

        monkeypatch.setattr(manual_store, "_read_venue_fill", boom)
        request = _request()
        outcome = _outcome_from(_responses()["create_ioc_filled_201"], request)
        row = _row(path, request, outcome)
        assert row["status"] == outcome.status
        assert row["kalshi_order_id"] == outcome.kalshi_order_id
        for column in VENUE_COLUMNS:
            assert row[column] is None, column

    def test_a_teardown_is_not_relabelled_as_a_missing_fill(self, monkeypatch):
        """`BaseException` is deliberately not caught: a cancellation is the
        process dying, and hiding it in a data column loses the shutdown."""
        def interrupted(outcome):
            raise KeyboardInterrupt

        monkeypatch.setattr(manual_store, "_read_venue_fill", interrupted)
        request = _request()
        outcome = _outcome_from(_responses()["create_ioc_filled_201"], request)
        with pytest.raises(KeyboardInterrupt):
            manual_store.venue_fill(outcome)

    def test_the_read_happens_before_the_update_not_inside_it(self):
        """Read off the source: the derivation must not sit inside the `try`
        whose only declared failure is `sqlite3.Error`, or an unexpected
        exception from it would be reported as a database failure."""
        source = (
            REPO / "backend" / "store" / "manual_orders.py"
        ).read_text(encoding="utf-8")
        body = source[source.index("def record_outcome"):]
        assert body.index("venue_fill(outcome)") < body.index("try:")


class TestTheColumnsAreMigratedOntoAnExistingVolume:
    """`schema.sql` is applied with CREATE TABLE IF NOT EXISTS, so a column
    added there is invisible to every database already on disk."""

    def test_one_migration_step_adds_all_three(self):
        """Keyed on the column names, never on the version number: the
        version is a placeholder that is re-taken at merge, and a test that
        pinned it would have to be edited in the same breath."""
        steps = {
            version: {
                column for table, column, _ in step.columns
                if table == "manual_orders"
            }
            for version, step in db._MIGRATIONS.items()
        }
        owning = [v for v, columns in steps.items() if set(VENUE_COLUMNS) & columns]
        assert len(owning) == 1, (
            f"the three venue columns must be added by exactly one step, "
            f"found {owning}"
        )
        assert steps[owning[0]] == set(VENUE_COLUMNS)

    def test_the_declared_types_are_the_ones_the_units_argument_chose(self):
        """REAL for the count and the fee, INTEGER for the price. An INTEGER
        fee would round $0.0014 to $0.00."""
        declared = {
            column: kind
            for step in db._MIGRATIONS.values()
            for table, column, kind in step.columns
            if table == "manual_orders"
        }
        assert declared["venue_fill_count"] == "REAL"
        assert declared["venue_avg_fill_price_tenths"] == "INTEGER"
        assert declared["venue_avg_fee_dollars"] == "REAL"

    def test_a_fresh_database_has_all_three_nullable_with_no_default(self, path):
        conn = db.open_db(path)
        try:
            info = {
                row["name"]: row
                for row in conn.execute("PRAGMA table_info(manual_orders)")
            }
        finally:
            conn.close()
        for column in VENUE_COLUMNS:
            assert column in info, column
            assert info[column]["notnull"] == 0, column
            assert info[column]["dflt_value"] is None, column
