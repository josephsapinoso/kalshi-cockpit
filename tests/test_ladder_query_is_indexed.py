"""The parlay ladder's fixture lookup must not scan two growing tables.

Measured on live 2026-08-26, after the recorder's own scan was fixed:
`/api/parlays` answered in **15 seconds** while every other route was
sub-second — so it was the route, not contention. `EXPLAIN QUERY PLAN` said
why:

    SCAN odds_snapshots USING INDEX idx_odds_event      <- every row, every call
    SCAN f                                              <- every fair price

`odds_snapshots` has **no retention rule at all** (`store/retention.py:53-55`,
deliberately out of scope), so the first of those grows forever.

THE FIX, IN TWO PARTS
---------------------
1. **The subquery is restricted to linked events.** The outer query
   inner-joins on `l.odds_event_id`, so an event absent from `event_links` was
   discarded anyway — the group was building rows to throw away.
2. **One index**: `(market, computed_ms DESC)` on `fair_prices`.

**A second index was written and then deleted the same hour, and that is worth
recording.** `(odds_event_id, commence_ms)` on `odds_snapshots` looked
necessary and changed no plan: the existing `idx_odds_event` already leads with
`odds_event_id`, which is all the equality needs. It would have cost write
amplification on the highest-volume table in the system to buy nothing. The
claim that "neither half works alone" was made before it was tested, and the
test below is what refuted it.

What IS true: the restriction is doing the work on `odds_snapshots`, and the
`fair_prices` index is doing the work on `f`. `TestEachHalfIsLoadBearing` pins
both, so neither is removed as redundant later.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That `/api/parlays` is now fast.** The plan is a precondition. The re-read
  has to happen on the live box, under load, split by whether a pass is
  running — the caveat that made the 17:00Z baseline misleading when it was
  taken in a quiet window.
- **That the residual cost is gone.** `AUTOMATIC PARTIAL COVERING INDEX` and
  the ORDER BY's temp b-tree both survive and are not removable by indexing:
  the first is SQLite indexing the SUBQUERY'S OUTPUT, which has no persistent
  index by definition, and the second sorts a derived join. What changed is
  how many rows reach them.
- **That the planner behaves identically at scale.** These fixtures are small.
  A seek on an indexed equality does not become a scan as rows grow, which is
  why the assertions are about scans and seeks rather than about cost.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import pytest

from backend.store import db

PARLAYS = Path(__file__).resolve().parents[1] / "backend" / "parlays.py"


def ladder_sql() -> str:
    """The query as `ladder_candidates` actually issues it.

    **Imported, not scraped, since 2026-08-30.** This used to regex the
    triple-quoted literal out of `conn.execute(...)` in the module source.
    That worked right up until the statement was lifted into `CANDIDATE_SQL`
    so an instrument could time the real thing on live -- at which point the
    regex matched nothing and thirteen tests failed with "could not find the
    ladder query". That is the good failure: a scraper cannot certify a plan
    for a statement it can no longer find. A hand-typed duplicate would have
    been the bad one, so the constant is imported rather than re-extracted.
    """
    from backend.parlays import CANDIDATE_SQL

    assert "FROM fair_prices f" in CANDIDATE_SQL, "the wrong statement"
    return CANDIDATE_SQL


def plan(conn, sql: str, params) -> list[str]:
    return [r["detail"] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params)]


@pytest.fixture
def conn():
    c = db.init_db(os.path.join(tempfile.mkdtemp(), "ladder.db"))
    yield c
    c.close()


class TestNeitherGrowingTableIsScanned:
    def test_odds_snapshots_is_searched_not_scanned(self, conn):
        """The table with no retention rule. It only ever gets bigger."""
        steps = plan(conn, ladder_sql(), (0, 0, 0))
        assert not any(s.startswith("SCAN odds_snapshots") for s in steps), (
            f"the ladder groups the whole snapshot history: {steps}"
        )
        assert any(
            "odds_snapshots" in s and "SEARCH" in s and "odds_event_id=?" in s
            for s in steps
        ), steps

    def test_fair_prices_is_searched_not_scanned(self, conn):
        """`SCAN f USING INDEX ...` counts as a scan.

        The pattern was a bare `SCAN f` until 2026-08-28, which would have
        passed VACUOUSLY the moment SQLite chose to scan `f` through an index
        rather than through the table -- exactly what the sibling test below
        now observes when the index is dropped. A guard for "every row is
        visited" must not be defeated by which index the visit goes through.
        """
        steps = plan(conn, ladder_sql(), (0, 0, 0))
        assert not any(re.fullmatch(r"SCAN f(?: USING .+)?", s) for s in steps), (
            f"every fair price ever computed is visited: {steps}"
        )
        assert any("market=?" in s and "computed_ms>?" in s for s in steps), steps
        # **The confirmed arm seeks too.** The OR's right-hand side
        # (`f.confirmed_ms >= ?`) must reach its own index rather than
        # falling back to a residual filter over rows the LEFT arm's index
        # already visited -- that would still be correct and would still be
        # a scan of `f` in cost, which this repo has already paid for once.
        assert any(
            "market=?" in s and "confirmed_ms>?" in s for s in steps
        ), steps
        # **Both arms run as one plan, not two separate scans SQLite unions
        # in Python.** `MULTI-INDEX OR` is SQLite's own name for seeking
        # each side of an OR on its own index and combining the rowid sets
        # -- the alternative it degrades to when only one side is indexed is
        # asserted directly by `TestTheConfirmedIndexIsLoadBearing` below.
        assert any("MULTI-INDEX OR" in s for s in steps), steps

    def test_the_restriction_is_present_in_the_query(self, conn):
        sql = ladder_sql()
        assert "odds_event_id IN (SELECT odds_event_id FROM event_links)" in sql


class TestTheRestrictionCannotChangeTheAnswer:
    def test_the_outer_join_already_required_a_link(self, conn):
        """Why the restriction is safe rather than a filter.

        The query inner-joins `event_links l ON l.id = f.link_id` and then
        `o.odds_event_id = l.odds_event_id`. Any snapshot event with no link
        could never survive that join, so removing it from the group changes
        nothing about the output.
        """
        sql = ladder_sql()
        assert "JOIN event_links l ON l.id = f.link_id" in sql
        assert "o.odds_event_id = l.odds_event_id" in sql

    def test_commence_ms_is_not_filtered_inside_the_group(self, conn):
        """The obvious further cut, refused on purpose.

        `MIN(commence_ms)` is the fixture's EARLIEST recorded start. Filtering
        rows before taking the MIN would let a rescheduled fixture through
        whose true earliest start is in the past — a silent wrong answer, in
        exchange for speed on a query that is now a seek anyway.
        """
        sql = ladder_sql()
        group = sql[sql.index("FROM odds_snapshots") : sql.index("GROUP BY")]
        assert "commence_ms >" not in group and "commence_ms>" not in group, (
            "a commence filter was pushed inside the GROUP BY; see the "
            "comment in backend/parlays.py for why that is not safe"
        )


class TestTheLadderIsBoundedInSql:
    """The route must not bring the whole window into the process.

    `ladder_candidates` used to `fetchall()` every `fair_prices` row in a
    rolling 24-hour window and dedupe in Python: **463,866 rows, ~557 MB on a
    2 GB box already at ~1.03 GB at rest** (ticket #22, reproduced by two
    agents independently). The route stalled past 30s healthy, repeated visits
    OOM-killed uvicorn, and because `docker/entrypoint.sh` uses `wait -n`,
    killing that child tore down the container and **restarted the recorder
    too**. About 91 seconds of whole-site outage was observed while measuring
    it. Joe hit it on his phone on 2026-08-28.

    The Python dedup is still there, on purpose, as a safety net. That is what
    makes these tests necessary: with the net in place the ROUTE stays correct
    if the SQL bound is removed, so nothing else in the suite would go red --
    it would just get slow again, silently, which is how it shipped the first
    time.

    **What these do not establish:** that `/api/parlays` is fast. They assert
    the query returns one row per identity on a fixture holding duplicates.
    Wall-clock belongs on the live box, and the ticket's numbers were taken
    there.
    """

    def test_the_window_function_is_in_the_query(self):
        sql = ladder_sql()
        assert "ROW_NUMBER() OVER" in sql, (
            "the ladder is unbounded again: every fair price in the window "
            "will be materialised in Python"
        )
        assert "WHERE rn = 1" in sql

    def test_the_partition_is_exactly_the_python_key(self):
        """Five columns, and `outcome_description` is the one that matters.

        It is NULL on team markets and load-bearing on props, where
        `outcome_name` is only "Over"/"Under". Drop it from the partition and
        two pitchers in one game quoted at the same rung collapse onto one
        row -- a wrong leg offered for money, not a slow page.
        """
        sql = ladder_sql()
        partition = sql[sql.index("PARTITION BY") : sql.index("ORDER BY f.computed_ms")]
        for column in (
            "f.link_id",
            "f.market",
            "f.outcome_name",
            "f.outcome_description",
            "f.outcome_point",
        ):
            assert column in partition, f"{column} left the partition: {partition}"

    def test_duplicates_never_reach_python(self, conn):
        """The behavioural half: three rows for one rung, one comes back."""
        _seed_one_rung(conn, computed_ms_values=(1_000, 2_000, 3_000))
        rows = conn.execute(ladder_sql(), (0, 0, 0)).fetchall()
        assert len(rows) == 1, (
            f"the query returned {len(rows)} rows for one identity; the "
            f"bound is not bounding"
        )
        assert rows[0]["computed_ms"] == 3_000, "the freshest row did not win"

    def test_two_players_at_one_rung_stay_two_rows(self, conn):
        """The partition's own trap, in behaviour rather than in text.

        Same game, same market, same strike, both "Over" -- separated only by
        `outcome_description`. If that column ever leaves the partition this
        returns 1 and the screen offers one pitcher's price for the other's
        bet.
        """
        _seed_one_rung(
            conn,
            computed_ms_values=(1_000,),
            descriptions=("Pitcher A", "Pitcher B"),
        )
        rows = conn.execute(ladder_sql(), (0, 0, 0)).fetchall()
        assert len(rows) == 2, (
            f"two players at one rung collapsed to {len(rows)} row(s)"
        )


class TestEachHalfIsLoadBearing:
    """Pinned so neither is removed as redundant later."""

    def test_without_the_fair_prices_index_it_scans_again(self):
        """A full scan of `f`, however SQLite spells it.

        This probed for the literal string `SCAN f` until 2026-08-28, and went
        red when the query gained its `ROW_NUMBER()` bound: dropping the index
        now yields `SCAN f USING INDEX idx_fair_link`, because the partition
        leads with `link_id` and SQLite reaches for that index instead. Still a
        full scan of every fair price, so the claim was intact and only the
        spelling was wrong -- `SCAN <table> USING INDEX` is a scan, and the
        word that separates it from a seek is SEARCH.
        """
        c = db.init_db(os.path.join(tempfile.mkdtemp(), "half.db"))
        try:
            c.execute("DROP INDEX IF EXISTS idx_fair_market_computed")
            steps = plan(c, ladder_sql(), (0, 0, 0))
        finally:
            c.close()
        assert any(re.fullmatch(r"SCAN f(?: USING .+)?", s) for s in steps), (
            f"the fair_prices index changes no plan, so it is decoration "
            f"with a write cost: {steps}"
        )

    def test_the_odds_seek_is_a_seek_whichever_index_serves_it(self):
        """**Rewritten 2026-09-10.** It used to assert that the seek came from
        `idx_odds_event` rather than a new index, on the since-refuted claim
        that `(odds_event_id, commence_ms)` was redundant. See
        `test_a_second_odds_index_must_carry_a_MEASUREMENT_not_a_plan_diff`.

        It was also passing for a reason that had nothing to do with its
        claim: `"idx_odds_event" in s` is a SUBSTRING test, and
        `idx_odds_event_commence` contains it. The test could not have failed
        no matter which of the two indexes the planner chose.

        The durable claim is the one kept here: the restriction to linked
        events is what turns this from a scan of the whole snapshot history
        into a seek. Which index serves the seek is the planner's business.
        """
        c = db.init_db(os.path.join(tempfile.mkdtemp(), "noidx.db"))
        try:
            steps = plan(c, ladder_sql(), (0, 0, 0))
        finally:
            c.close()
        assert not any(s.startswith("SCAN odds_snapshots") for s in steps), (
            f"the restriction to linked events stopped biting: {steps}"
        )
        assert any(
            "odds_snapshots" in s and "SEARCH" in s and "odds_event_id=?" in s
            for s in steps
        ), steps

    def test_a_second_odds_index_must_carry_a_MEASUREMENT_not_a_plan_diff(self):
        """**Inverted 2026-09-10, and the rule it enforces is stronger.**

        This used to assert `idx_odds_event_commence` did NOT exist, on the
        2026-08-26 finding that it "changed no plan": with it and without it,
        the step reads `SEARCH ... (odds_event_id=?)`. That observation was
        correct and the inference from it was not.

        **EXPLAIN QUERY PLAN reports the access method, never how many rows
        the method touches.** The subquery takes `MIN(commence_ms)` per event;
        under `idx_odds_event` — `(odds_event_id, market, fetched_ms DESC)` —
        `commence_ms` is absent from the index, so the minimum is only found
        by reading every row of the group and fetching the column from the
        table. ~1,400 rows per event on live. With `commence_ms` second, the
        minimum is the first entry.

        Measured on live 2026-09-10 while `/api/parlays` was answering 503
        `read_budget_exceeded` at 25 s: the candidate scan took 73,526 ms to
        return 494 rows, of which this subquery alone was 26,719 ms, with 848
        of 10,112,298 `fair_prices` rows inside the window. Locally at live's
        shape: 503.9 ms -> 167.5 ms.

        So the guard is not deleted, it is re-aimed. The original rule — do
        not pay write amplification on the highest-volume table for nothing —
        is intact. What changed is what counts as evidence of "nothing": a
        plan diff cannot show it, and a timing can.
        """
        schema = (
            Path(__file__).resolve().parents[1] / "backend" / "store" / "schema.sql"
        ).read_text(encoding="utf-8")
        assert "CREATE INDEX IF NOT EXISTS idx_odds_event_commence" in schema, (
            "the index is gone again; if it was removed on a plan diff, read "
            "this test's docstring first -- that argument was tried in 2026 "
            "and the timing refuted it"
        )
        # And the measurement that justifies it has to survive with it, or the
        # 2026-08-26 argument becomes available again and reads as sound.
        assert "never the number of rows" in schema
        assert "26,719 ms" in schema
        # The cost is still acknowledged, not waved away.
        assert "write-amplification objection stands" in schema

    def test_the_index_is_declared_in_the_schema(self):
        """It must reach the LIVE volume, which is an existing database.

        `init_db` applies `schema.sql` unconditionally after `migrate`, so a
        `CREATE INDEX IF NOT EXISTS` lands on an existing volume at next boot.
        """
        schema = (
            Path(__file__).resolve().parents[1] / "backend" / "store" / "schema.sql"
        ).read_text(encoding="utf-8")
        assert "CREATE INDEX IF NOT EXISTS idx_fair_market_computed" in schema
        assert "CREATE INDEX IF NOT EXISTS idx_fair_market_confirmed" in schema, (
            "the confirmed-stamp index must also reach a volume that "
            "already exists -- schema.sql alone never touches one"
        )


class TestTheConfirmedIndexIsLoadBearing:
    """`idx_fair_market_confirmed` is not decoration beside the OR.

    Dropping it does not merely lose the RIGHT arm's own seek -- it loses
    SQLite's `MULTI-INDEX OR` optimisation entirely, because that plan needs
    EVERY arm of the OR indexed to fire. What is left is a single seek on
    `idx_fair_market_computed` for the equality alone (`market=?`), with
    `computed_ms>?` demoted from an index bound to a residual row-by-row
    filter -- silently wider than the query looks, and exactly the shape
    measured live before this fix (6,561,382 rows through this index).
    """

    def test_without_the_confirmed_index_the_computed_seek_is_lost(self):
        """Mutation observed red with the index in place: see the sibling
        assertion in `TestNeitherGrowingTableIsScanned` above, which requires
        `computed_ms>?` to appear. Here the index is gone and the bound must
        be gone with it."""
        c = db.init_db(os.path.join(tempfile.mkdtemp(), "noconfirmed.db"))
        try:
            c.execute("DROP INDEX IF EXISTS idx_fair_market_confirmed")
            steps = plan(c, ladder_sql(), (0, 0, 0))
        finally:
            c.close()
        assert not any("computed_ms>?" in s for s in steps), (
            f"the computed_ms seek survived losing its OR partner, so the "
            f"partial index is not actually load-bearing: {steps}"
        )
        assert any(
            re.fullmatch(r"SEARCH f USING INDEX idx_fair_market_computed \(market=\?\)", s)
            for s in steps
        ), (
            f"expected the degraded plan -- an equality-only seek with no "
            f"computed_ms bound: {steps}"
        )


class TestTheQueryNamesEveryMarketALegMayComeFrom:
    """The literals in the SQL and the constants callers use must agree.

    The query has to stay a literal triple-quoted string, because it is
    `CANDIDATE_SQL` in `backend/parlays.py` -- `ladder_sql()` above reaches it
    with `from backend.parlays import CANDIDATE_SQL`, not a regex extraction,
    since 2026-08-30. The live constraint is that the market literals stay
    inline: interpolating them risks losing the `market=?` index seek that
    keeps this query off a full scan of `fair_prices`. So the market list is
    written twice, and this is what stops the two copies drifting: add a prop
    series to `PROP_SERIES` without adding it here and the pool would
    silently never contain it.
    """

    def test_the_sql_names_every_prop_market_key(self):
        from backend.odds.client import PROP_BASE_MARKETS

        sql = ladder_sql()
        for market in PROP_BASE_MARKETS:
            assert f"'{market}'" in sql, (
                f"{market} is bought and devigged but no leg can come from it"
            )

    def test_the_sql_names_both_team_markets(self):
        from backend.parlays import _TEAM_MARKETS

        sql = ladder_sql()
        for market in _TEAM_MARKETS:
            assert f"'{market}'" in sql

    def test_the_bought_prop_keys_and_the_kalshi_series_agree(self):
        """One Odds API market key per Kalshi prop series, both directions.

        A series in `PROP_SERIES` whose key is never bought produces Kalshi
        rungs with no consensus; a key bought with no series produces a
        consensus nothing can be matched to. Either way the credits are spent.
        """
        from backend.kalshi.props import PROP_SERIES
        from backend.odds.client import PROP_BASE_MARKETS

        assert set(PROP_SERIES.values()) == set(PROP_BASE_MARKETS)


def _seed_one_rung(
    conn,
    computed_ms_values=(1_000,),
    descriptions=(None,),
    market="pitcher_strikeouts",
):
    """One linked fixture, and a `fair_prices` row per (time, description).

    Written against the columns the ladder query actually selects, so a schema
    change that breaks the query breaks this too rather than silently seeding
    rows the query cannot see. `commence_ms` is far in the future because the
    query takes pre-game fixtures only (`o.commence_ms > ?`, passed `now`).
    """
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events "
        "(event_ticker, title, first_seen_ms, last_seen_ms) "
        "VALUES ('KXTEST-1', 'Test Event', 1, 1)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO event_links "
        "(id, kalshi_event_ticker, odds_event_id, league, method, "
        " commence_skew_ms, linked_ms) "
        "VALUES (1, 'KXTEST-1', 'oe-1', 'baseball_mlb', 'test', 0, 1)"
    )
    conn.execute(
        "INSERT INTO odds_snapshots "
        "(fetched_ms, sport_key, odds_event_id, commence_ms, home_team, "
        " away_team, bookmaker, market, outcome_name, price_decimal) "
        "VALUES (1, 'baseball_mlb', 'oe-1', 9223372036854, 'H', 'A', "
        "'pinnacle', ?, 'Over', 2.0)",
        (market,),
    )
    for computed_ms in computed_ms_values:
        for description in descriptions:
            conn.execute(
                "INSERT INTO fair_prices (computed_ms, link_id, market, "
                "outcome_name, outcome_description, outcome_point, "
                "p_multiplicative, p_additive, p_power, p_shin, "
                "p_conservative, book_count, books_used, anchored_on_sharp) "
                "VALUES (?, 1, ?, 'Over', ?, 5.5, 0.55, 0.54, 0.53, 0.56, "
                "0.52, 3, '[]', 0)",
                (computed_ms, market, description),
            )
    conn.commit()


class TestARefusedLegsKickoffIsSoughtNotGrouped:
    """`_commence_ms_for_tickers` (ADR 0138) must not regroup the whole
    snapshot history to answer for two tickers.

    Its first version LEFT JOINed `(SELECT ... FROM odds_snapshots GROUP BY
    odds_event_id)`, which SQLite plans as `MATERIALIZE o` over every row the
    table holds -- the plan `CANDIDATE_SQL` was measured at 15 s with. It ran
    on every refused tap. A correlated scalar subquery seeks `idx_odds_event`
    on the fixture instead.
    """

    def test_odds_snapshots_is_searched_not_scanned(self, conn):
        from backend.parlays import commence_for_tickers_sql

        steps = plan(conn, commence_for_tickers_sql(2), ("a", "b"))
        assert not any(s.startswith("SCAN odds_snapshots") for s in steps), (
            f"a refused tap groups the whole snapshot history: {steps}"
        )
        assert not any(s.startswith("MATERIALIZE") for s in steps), steps
        # The alias is `o`, so the step names the index, not the table.
        #
        # **Which index is not pinned, deliberately (2026-09-10).** This read
        # `SEARCH o USING INDEX idx_odds_event` until `idx_odds_event_commence`
        # was restored, and now reads `SEARCH o USING COVERING INDEX
        # idx_odds_event_commence` -- strictly better, because COVERING means
        # it stops touching the table at all. A guard that named the index
        # would have called that a regression. The claim is that this is a
        # seek on the event id, and it is the claim that is pinned.
        assert any(
            s.startswith("SEARCH o USING ")
            and "INDEX idx_odds_event" in s
            and "odds_event_id=?" in s
            for s in steps
        ), steps
        assert any(s.startswith("CORRELATED SCALAR SUBQUERY") for s in steps), steps

    def test_the_seek_answers_with_the_fixtures_earliest_start(self, conn):
        """Plan shape is not correctness: the value must be the fixture's
        MIN commence, per ticker, and an unlinked ticker must come back
        without an entry rather than as None-means-started."""
        from backend.parlays import _commence_ms_for_tickers

        _seed_one_rung(conn, (1,), (None,), market="h2h")
        conn.execute(
            "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
            "commence_ms, home_team, away_team, bookmaker, market, "
            "outcome_name, price_decimal) VALUES (2, 'baseball_mlb', 'oe-1', "
            "500, 'H', 'A', 'pinnacle', 'h2h', 'H', 2.0)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, title, "
            "first_seen_ms, last_seen_ms) VALUES ('KXTEST-1-H', 'KXTEST-1', "
            "'H?', 1, 1)"
        )
        conn.commit()
        found = _commence_ms_for_tickers(conn, ["KXTEST-1-H", "KXNOPE-1-Z"])
        assert found == {"KXTEST-1-H": 500}
