"""Demo seeder tests.

The demo instance is the public face of this repo, so two things have to hold:
it must produce the *same* database every time (or screenshots and the live
demo drift apart), and it must present an honest picture of what the tool does
(mostly no edge).
"""

from __future__ import annotations

import pytest

from backend.seed_demo import DEFAULT_SEED, seed_all
from backend.store import db


@pytest.fixture
def seeded(tmp_path):
    path = tmp_path / "demo.db"
    counts = seed_all(path)
    return path, counts


class TestDeterminism:
    def test_reseeding_does_not_duplicate_rows(self, tmp_path):
        """Caught by looking at the rendered Board, not by a test.

        Restarting the demo server ran the seeder again and appended a second
        copy of every fixture -- the Board showed Houston twice and the counts
        read 18 for a nine-fixture slate.
        """
        path = tmp_path / "demo.db"
        first = seed_all(path)
        second = seed_all(path)
        assert first == second

        conn = db.open_db(path, read_only=True)
        n = conn.execute("SELECT COUNT(*) AS n FROM recommendations").fetchone()["n"]
        conn.close()
        assert n == first["recommendations"]

    def test_the_same_seed_produces_the_same_board(self, tmp_path):
        a, b = tmp_path / "a.db", tmp_path / "b.db"
        seed_all(a, seed=DEFAULT_SEED)
        seed_all(b, seed=DEFAULT_SEED)

        def board(path):
            conn = db.open_db(path, read_only=True)
            rows = conn.execute(
                "SELECT ticker, entry_ask_tenths, suggested_contracts, "
                "suppressed_reason FROM recommendations ORDER BY ticker"
            ).fetchall()
            conn.close()
            return [tuple(r) for r in rows]

        assert board(a) == board(b)


class TestReseedingOverAUsedDatabase:
    """The reset order has to match the foreign-key graph, not read like it.

    `seed_all` deleted `recommendations` before `orders`, and
    `orders.recommendation_id` references it. Every test here builds a fresh
    database and `seed_all` writes no orders of its own, so the broken order was
    unreachable from the suite: the only way to hit it was to run `seed_history`
    -- which writes 400 orders -- and then re-seed. That is exactly what
    refreshing a local demo does, and it failed on the first DELETE with
    `FOREIGN KEY constraint failed`.

    The general shape is this repo's: **a fixture that always starts from empty
    cannot test teardown.** The precondition that made the bug reachable was the
    one the fixture removes.
    """

    def test_it_reseeds_over_a_database_that_already_has_orders(self, tmp_path):
        from backend.seed_demo import seed_history

        path = tmp_path / "demo.db"
        seed_all(path)
        seed_history(path, n=25)

        conn = db.open_db(path)
        orders_before = conn.execute(
            "SELECT COUNT(*) AS n FROM orders"
        ).fetchone()["n"]
        conn.close()
        assert orders_before > 0, (
            "no orders were written, so this test cannot reach the defect it "
            "is about"
        )

        # The whole assertion: this call raised before the order was fixed.
        seed_all(path)

        conn = db.open_db(path)
        try:
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM orders"
            ).fetchone()["n"] == 0
            assert conn.execute(
                "SELECT COUNT(*) AS n FROM recommendations"
            ).fetchone()["n"] > 0
        finally:
            conn.close()


class TestHonestShape:
    """A demo showing a screen of profitable bets would misrepresent the tool."""

    def test_only_a_couple_of_opportunities_surface(self, seeded):
        _, counts = seeded
        assert 1 <= counts["surfaced"] <= 3

    def test_most_candidates_do_not_surface(self, seeded):
        _, counts = seeded
        assert counts["surfaced"] < counts["recommendations"] / 2

    def test_several_distinct_suppression_reasons_are_represented(self, seeded):
        """Each rule should be visible in the demo so a visitor can see what
        the safety layer actually does."""
        path, _ = seeded
        conn = db.open_db(path, read_only=True)
        reasons = {
            r["suppressed_reason"]
            for r in conn.execute(
                "SELECT DISTINCT suppressed_reason FROM recommendations "
                "WHERE suppressed_reason IS NOT NULL"
            )
        }
        conn.close()
        assert len(reasons) >= 3

    def test_the_suspicious_edge_rule_is_demonstrated(self, seeded):
        """The governing rule of the project deserves a visible example."""
        path, _ = seeded
        conn = db.open_db(path, read_only=True)
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM recommendations "
            "WHERE suppressed_reason LIKE '%suspicious_edge%'"
        ).fetchone()["n"]
        conn.close()
        assert n >= 1


class TestNoCredentialsNeeded:
    def test_seeding_touches_no_network_and_no_credentials(self, tmp_path):
        """The whole point: a stranger can clone this and see the cockpit."""
        import os

        saved = {
            k: os.environ.pop(k, None)
            for k in ("KALSHI_API_KEY", "KALSHI_PRIVATE_KEY_PATH", "ODDS_API_KEY")
        }
        try:
            counts = seed_all(tmp_path / "nocreds.db")
            assert counts["recommendations"] > 0
        finally:
            for key, value in saved.items():
                if value is not None:
                    os.environ[key] = value


class TestTheSeededSpendSurvivesTheBudgetDayRoll:
    """Both seeded sweeps must land in the same budget day, at every hour.

    The two sweeps are five hours apart and the budget day rolls at 10:00Z, so
    when the ages were measured from `now` the older one fell into *yesterday*
    for any seed run between 10:00Z and 15:00Z. The demo panel then showed
    6 of 16 credits spent beside two sweeps' worth of odds -- the contradiction
    the spend rows exist to prevent -- and
    `test_it_reports_the_remaining_budget_in_sweeps` went red for five hours a
    day. It was found by a suite run at 13:34Z after a dozen runs outside the
    window; CI had been passing on the hour it happened to be scheduled.

    Parameterised across the whole clock rather than spot-checked, because the
    defect is *only* visible in a five-hour band and a single sample is a coin
    flip about which side of it you land on.
    """

    @pytest.mark.parametrize("hour", range(24))
    def test_spent_today_is_both_sweeps_at_every_hour(self, tmp_path, hour):
        from datetime import datetime, timedelta, timezone

        from backend.odds.budget import CreditBudget

        when = datetime(2026, 8, 8, tzinfo=timezone.utc) + timedelta(
            hours=hour, minutes=30
        )
        path = tmp_path / f"h{hour}.db"
        counts = seed_all(path, now_ms=int(when.timestamp() * 1000))

        conn = db.open_db(path, read_only=True)
        try:
            spent = CreditBudget(conn, 16).state(int(when.timestamp() * 1000))
        finally:
            conn.close()

        assert spent.spent_today == 6 * counts["odds_sweeps"], (
            f"seeded at {hour:02d}:30Z, {counts['odds_sweeps']} sweeps recorded "
            f"but only {spent.spent_today} credits fall inside the budget day"
        )


class TestTheSeededHistoryActuallyLands:
    """`seed_history` reported 400 settlements while writing zero.

    The insert was `INSERT OR IGNORE`, which suppresses *every* constraint
    failure on the statement -- including the `NOT NULL` that says the row is
    incomplete. Schema v4 made `settlements.order_id` `NOT NULL`, so from that
    commit the seeder silently emptied `mart_calibration`, and the counter beside
    it went on saying 400. `tasks/lessons.md` already carries this exact failure
    under a different table.

    So the assertion is on the **rows**, never on the returned count: the count
    is the thing that lied.
    """

    def _seeded(self, tmp_path, n=25):
        """Slate first, then history — the order `backend.seed_demo` uses.

        `seed_history` alone raises on a foreign key: its recommendations
        reference a `strategy_configs` row that only `seed_all` writes. Worth
        stating, because calling it standalone looks reasonable and fails for a
        reason that has nothing to do with what is under test here.
        """
        from backend.seed_demo import seed_all, seed_history
        from backend.store import db

        path = tmp_path / "history.db"
        seed_all(path)
        reported = seed_history(path, n=n)
        return reported, db.open_db(path, read_only=True)

    def test_the_settlement_rows_exist_and_match_the_count(self, tmp_path):
        reported, conn = self._seeded(tmp_path)
        try:
            actual = conn.execute(
                "SELECT COUNT(*) AS n FROM settlements"
            ).fetchone()["n"]
            assert actual == reported["settlements"], (
                f"reported {reported['settlements']} settlements and wrote "
                f"{actual}"
            )
            assert actual > 0
        finally:
            conn.close()

    def test_every_settlement_points_at_a_real_order(self, tmp_path):
        """A settlement settles a position, and the join has to find it.

        `order_id` is a foreign key, and SQLite does not enforce one unless
        `PRAGMA foreign_keys` is on -- so the constraint alone is not the
        guarantee. Asserting the join is.
        """
        _, conn = self._seeded(tmp_path)
        try:
            orphans = conn.execute(
                "SELECT COUNT(*) AS n FROM settlements s "
                "LEFT JOIN orders o ON o.id = s.order_id WHERE o.id IS NULL"
            ).fetchone()["n"]
            assert orphans == 0
        finally:
            conn.close()

    def test_the_seeded_history_is_paper(self, tmp_path):
        """It is synthetic, so it must never be counted as live exposure or
        pooled into a live P&L."""
        _, conn = self._seeded(tmp_path)
        try:
            live = conn.execute(
                "SELECT COUNT(*) AS n FROM settlements WHERE dry_run = 0"
            ).fetchone()["n"]
            assert live == 0
        finally:
            conn.close()


class TestTheSeededFairValueIsTheOneItPointsAt:
    """**`fair_probability` and the joined `p_conservative` are the same
    number, and on the demo they were not.**

    In production they cannot come apart: `runner.py` devigs once and passes
    the *same* `DevigResult` both to `write_fair_price` and to
    `build_recommendation` (`runner.py:936`). The seeder used to run a second,
    single-pair `devig()` over `scenario.odds` and price the recommendation
    from that, while `fair_price_id` pointed at the multi-book consensus -- so
    all 11 seeded rows disagreed with their own fair price, by up to 0.35
    probability points, in both directions.

    It cost nothing while no screen read both. It became visible the moment one
    rendered the four devig methods beside the fair value and their minimum
    contradicted it -- on the public demo, which is the portfolio piece.

    **What this does not establish.** That the consensus is *correct*, or that
    production really holds the invariant -- this reads the seeded database
    only. `p_conservative` being the minimum of the four methods is asserted
    separately below, because "they match" and "they match the right thing" are
    different claims and a seeder that wrote one number into both columns would
    pass the first.
    """

    def _joined(self, path):
        conn = db.open_db(path, read_only=True)
        try:
            return conn.execute(
                "SELECT r.ticker, r.fair_probability, f.p_conservative, "
                "       f.p_multiplicative, f.p_additive, f.p_power, f.p_shin "
                "FROM recommendations r "
                "JOIN fair_prices f ON f.id = r.fair_price_id"
            ).fetchall()
        finally:
            conn.close()

    def test_the_join_finds_rows_at_all(self, seeded):
        """The anchor. Every assertion below is vacuous over an empty set, and
        a seeder that stopped writing `fair_price_id` would satisfy them all."""
        path, _ = seeded
        rows = self._joined(path)
        assert len(rows) >= 9, len(rows)

    def test_no_row_disagrees_with_its_own_fair_price(self, seeded):
        path, _ = seeded
        offenders = [
            (r["ticker"], r["fair_probability"], r["p_conservative"])
            for r in self._joined(path)
            if abs(r["fair_probability"] - r["p_conservative"]) > 1e-9
        ]
        assert not offenders, (
            "These seeded rows carry a `fair_probability` that is not the "
            "`p_conservative` of the `fair_prices` row they point at, which "
            f"production cannot produce: {offenders}"
        )

    def test_the_conservative_reading_is_the_lowest_of_the_four_methods(
        self, seeded
    ):
        """Otherwise the test above passes on a seeder that wrote one invented
        number into both columns, which is the shape it is meant to catch."""
        for r in self._joined(seeded[0]):
            methods = [
                r["p_multiplicative"], r["p_additive"], r["p_power"], r["p_shin"]
            ]
            present = [m for m in methods if m is not None]
            assert present, r["ticker"]
            assert abs(r["p_conservative"] - min(present)) < 1e-9, r["ticker"]

    def test_the_four_methods_are_not_all_the_same_number(self, seeded):
        """A dispersion strip over four identical values shows nothing, and a
        seeder that collapsed them would make the screen look broken while
        every assertion above stayed green."""
        spreads = [
            max(vals) - min(vals)
            for r in self._joined(seeded[0])
            for vals in [[
                v for v in (
                    r["p_multiplicative"], r["p_additive"],
                    r["p_power"], r["p_shin"],
                ) if v is not None
            ]]
        ]
        assert spreads, "no rows"
        assert max(spreads) > 1e-6, (
            "Every seeded row has four identical devig readings, so the "
            "method-dispersion strip renders as a single point on the demo."
        )
