"""The gate's fee condition counts engine fills, and only engine fills.

ADR 0043. `_fee_model_verified` asks whether `calculate_fee` matches what
Kalshi actually charged, over rows in `fills`. When that query was written the
table could only mean "orders this engine placed", so the restriction was
implicit in the table itself and nothing had to say it.

**Schema v10 broke that.** It added `source` precisely because `fills` was
about to hold a second kind of row: bets Joe places by hand in the Kalshi app,
polled back from `/portfolio/fills`. Those carry a real `fee_cost` from the
venue. Without an explicit filter, the first poll silently changes what a
live-trading interlock counts.

**What this establishes:** that a non-engine fill carrying `fee_actual` moves
neither `total` nor `met` on that condition.

**What it does not establish:** that hand-placed fills *should* be excluded
forever. ADR 0043 defers that question rather than settling it -- the
arithmetic does not care who placed the order. It is not settled here because
nobody yet knows which way it cuts: if those fills mismatch our model, the
MISMATCH branch becomes reachable and the gate gets *stricter*. A logging
feature may not roll that dice in either direction, so the reversible move was
taken first.

Nor does it establish anything about `ORDERS_ARE_DRY_RUNS`, the 300-game
condition, or any other gate input. None is touched.
"""

from __future__ import annotations

import pytest

from backend.gate import _fee_model_verified
from backend.store import db


ENGINE_FILL = (
    "INSERT INTO fills (kalshi_fill_id, ticker, filled_ms, count, price_tenths, "
    "is_taker, fee_actual, fee_predicted, fee_model_used, source) "
    "VALUES (?, 'T-1', 1, 1, 500, 1, ?, ?, 'model_a', 'engine')"
)
HAND_FILL = (
    "INSERT INTO fills (kalshi_fill_id, ticker, filled_ms, count, price_tenths, "
    "is_taker, fee_actual, fee_predicted, fee_model_used, source) "
    "VALUES (?, 'KXUFCFIGHT-BY-HAND', 1, 1, 500, 1, ?, ?, 'model_a', 'venue_hand')"
)


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "cockpit.db")
    yield c
    c.close()


class TestAHandPlacedFillDoesNotReachTheGate:
    def test_the_condition_starts_with_no_evidence(self, conn):
        """The pinned state, asserted so the tests below have a baseline."""
        condition = _fee_model_verified(conn)

        assert condition.met is False
        assert "no fills yet" in condition.detail

    def test_a_matching_hand_fill_does_not_flip_the_condition(self, conn):
        """The loosening direction, which is the one that matters.

        A hand fill whose fee our model predicts exactly would, unfiltered,
        turn "no evidence, so no" into "model matches Kalshi on all 1 fills"
        -- a gate condition moving to met as a side effect of switching on a
        poller. That is the failure this test exists to prevent.
        """
        conn.execute(HAND_FILL, ("hand-1", 0.0175, 0.0175))

        condition = _fee_model_verified(conn)

        assert condition.met is False, (
            "a bet placed by hand in the Kalshi app moved a live-trading gate"
        )
        assert "no fills yet" in condition.detail

    def test_a_mismatching_hand_fill_does_not_flip_it_either(self, conn):
        """The tightening direction. Excluded for the same reason.

        ADR 0043's argument is not "hand fills are bad evidence" -- it is that
        a logging feature must not decide a gate question in *either*
        direction. A test that only checked the loosening case would leave the
        other half of that claim unasserted.
        """
        conn.execute(HAND_FILL, ("hand-2", 0.9000, 0.0175))

        condition = _fee_model_verified(conn)

        assert condition.met is False
        assert "MISMATCH" not in condition.detail

    def test_an_engine_fill_still_counts(self, conn):
        """Otherwise the filter could be excluding everything and look right.

        The two tests above pass equally well against a query that counts
        nothing at all, which is exactly how a guard becomes decoration.
        """
        conn.execute(ENGINE_FILL, ("engine-1", 0.0175, 0.0175))

        condition = _fee_model_verified(conn)

        assert condition.met is True
        assert "all 1 fills" in condition.detail

    def test_a_hand_fill_beside_an_engine_fill_is_not_counted(self, conn):
        """The real shape once the poller runs: both kinds in one table."""
        conn.execute(ENGINE_FILL, ("engine-1", 0.0175, 0.0175))
        conn.execute(HAND_FILL, ("hand-1", 0.9000, 0.0175))

        condition = _fee_model_verified(conn)

        assert condition.met is True, (
            "the hand fill's mismatch reached the gate and made it stricter"
        )
        assert "all 1 fills" in condition.detail, (
            "the hand fill was counted in the denominator"
        )


class TestTheFilterIsAnAllowlist:
    """A third kind added tomorrow must be excluded until somebody decides.

    `source = 'engine'` rather than `source != 'venue_hand'`. The denylist form
    passes every test above and admits the next `source` value by omission --
    the same family as this repo's rule that unreadable resolves to `None`
    rather than `0`: when the meaning is unknown, refuse.
    """

    def test_a_source_nobody_has_ruled_on_is_refused_by_default(self, conn):
        """`backfill` is not in the CHECK today, so the CHECK is dropped here.

        Written against the query rather than the constraint on purpose. The
        schema's CHECK is a *second* guard and a good one, but it is not the
        one under test: it will be widened the day somebody adds a legitimate
        third source, and on that day the gate must still refuse by default.
        Testing through the CHECK would assert that the day never comes.
        """
        conn.execute("DROP TABLE fills")
        conn.execute(
            "CREATE TABLE fills ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  kalshi_fill_id TEXT UNIQUE, order_id INTEGER, ticker TEXT NOT NULL,"
            "  filled_ms INTEGER NOT NULL, count INTEGER NOT NULL,"
            "  price_tenths INTEGER NOT NULL, is_taker INTEGER NOT NULL,"
            "  fee_actual REAL, fee_predicted REAL NOT NULL,"
            "  fee_model_used TEXT NOT NULL,"
            "  source TEXT NOT NULL DEFAULT 'engine')"
        )
        conn.execute(
            "INSERT INTO fills (kalshi_fill_id, ticker, filled_ms, count, "
            "price_tenths, is_taker, fee_actual, fee_predicted, fee_model_used, "
            "source) VALUES ('b1', 'T-1', 1, 1, 500, 1, 0.0175, 0.0175, "
            "'model_a', 'backfill')"
        )

        condition = _fee_model_verified(conn)

        assert condition.met is False, (
            "a source nobody has ruled on was admitted to the gate by omission"
        )
