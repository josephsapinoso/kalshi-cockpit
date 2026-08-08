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
