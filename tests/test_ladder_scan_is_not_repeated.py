"""A widening request reads the candidate pool once, not once per window.

WHY THIS EXISTS
---------------
`build_ladder_payload_widening` tries each window in `HORIZON_LADDER` until one
builds a card. Every window called `ladder_candidates`, and everything
`ladder_candidates` reads before it applies the window is **horizon-independent**:

- `CANDIDATE_SQL` binds `(floor_ms, floor_ms, now_ms)` and nothing else. The
  word `horizon` does not appear in the statement; the upper kickoff bound is
  applied in Python, after `fetchall()`.
- the `kalshi_markets` lookup runs once per distinct `kalshi_event_ticker` in
  the *unfiltered* result, so its count is a property of the scan, not of the
  window.
- `combo_eligible_events` takes `now_ms` only.

So a night that widened twice ran the byte-identical scan three times, plus the
per-event loop three times, and discarded two thirds of it -- against a read
budget (ADR 0135) that is cumulative across every statement in the request. The
windows are strictly nested (`tonight` <= `tomorrow` <= `48h`), so one scan
filtered three ways is provably equivalent, not approximately equivalent.

THE BED
-------
`tonight` empty and `tomorrow` building is the only bed that reaches the second
scan at all. On an empty database every window refuses, the loop still runs
three times, but so does the fixed code -- and a test that cannot tell the two
apart is the degenerate bed that let a mutation through on 2026-09-10.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about the 2026-09-10 cold-start 503.** That request returned
  `read_budget_exceeded` on a container minutes old against a 10M-row database,
  and there is no evidence the widening path ran at all. This removes work that
  is redundant on its own terms; it is not a fix for an unestablished cause.
- **Nothing about wall-clock time.** These beds hold three games. The claim
  under test is the number of statements, which is what the read budget counts.
- **Nothing about whether the widened window is the right one to show.**
  `test_parlay_horizon_widening.py` owns that.
"""

from __future__ import annotations

import pytest

from backend.store import db as store
from backend.parlays import (
    CANDIDATE_SQL,
    candidate_pool,
    ladder_candidates,
    HORIZON_LADDER,
    build_ladder_payload_widening,
    end_of_desk_day_ms,
)
from tests.test_parlays_api import seed_game

MAX_ODDS_AGE_MS = 600_000


class CountingConn:
    """Delegates to a real connection and records every statement.

    Deliberately a proxy rather than a `sqlite3` trace callback: the callback
    fires on the connection's own thread for *expanded* SQL, and the thing
    under test is how many times the caller reaches for `execute`.
    """

    def __init__(self, conn) -> None:
        self._conn = conn
        self.statements: list[str] = []

    def execute(self, sql, *args, **kwargs):
        self.statements.append(sql)
        return self._conn.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def count(self, needle: str) -> int:
        return sum(1 for sql in self.statements if needle in sql)


@pytest.fixture
def tomorrow_only_conn(tmp_path):
    """`tonight` builds nothing, `tomorrow` builds a card -- so the loop widens.

    Same shape as `test_parlay_horizon_widening.py`'s `tomorrow_only_app`, but
    handing back a connection rather than an app: the statement count is the
    subject here, and routing it through ASGI would add the route's own reads
    to the tally.
    """
    path = tmp_path / "scan.db"
    conn = store.init_db(path)
    tomorrow = end_of_desk_day_ms(store.now_ms()) + 3_600_000
    computed = store.now_ms() - 30_000
    for i, (team, other) in enumerate(
        (("Reds", "Cubs"), ("Mets", "Pirates"), ("Rays", "Angels"))
    ):
        seed_game(
            conn,
            game=f"scan-{i}",
            team=team,
            other=other,
            p=0.74,
            computed_ms=computed,
            commence_ms=tomorrow,
        )
    conn.commit()
    return CountingConn(conn)


class TestTheCandidateScanRunsOncePerRequest:
    def test_a_widening_request_scans_once(self, tomorrow_only_conn):
        """The claim. Unfixed, this is one scan per window tried."""
        payload = build_ladder_payload_widening(
            tomorrow_only_conn,
            now_ms=store.now_ms(),
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        # The bed has to actually reach the second window, or the count of one
        # is trivially satisfied and this test is measuring nothing.
        assert payload["window"]["widened_from"] == HORIZON_LADDER[0]
        assert tomorrow_only_conn.count("p_conservative") == 1

    def test_the_per_event_loop_does_not_repeat_either(self, tomorrow_only_conn):
        """`markets_by_event` is keyed off the unfiltered scan, so its whole
        loop is horizon-independent too -- and it is N statements, not one."""
        build_ladder_payload_widening(
            tomorrow_only_conn,
            now_ms=store.now_ms(),
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        # Three seeded games, three distinct event tickers, one read each.
        assert tomorrow_only_conn.count("FROM kalshi_markets WHERE event_ticker") == 3

    def test_the_scan_statement_is_the_module_constant(self, tomorrow_only_conn):
        """Pins the needle above to `CANDIDATE_SQL` itself, so a rename of the
        column this test greps for cannot silently turn the count into zero."""
        build_ladder_payload_widening(
            tomorrow_only_conn,
            now_ms=store.now_ms(),
            max_odds_age_ms=MAX_ODDS_AGE_MS,
        )
        assert tomorrow_only_conn.statements.count(CANDIDATE_SQL) == 1
        assert "p_conservative" in CANDIDATE_SQL


class TestAPoolIsRefusedForTheWrongClock:
    """A shared object gets passed one function further than intended.

    A pool built for a different minute, or under a different freshness rule,
    would answer confidently for the wrong one -- and the wrongness never
    reaches the screen as an error, because the cards would look right. So the
    refusal is the guard, and these are what make it more than decoration.
    """

    def _pool(self, conn):
        return candidate_pool(
            conn, now_ms=store.now_ms(), max_odds_age_ms=MAX_ODDS_AGE_MS
        )

    def test_a_pool_from_another_minute_is_refused(self, tomorrow_only_conn):
        pool = self._pool(tomorrow_only_conn)
        with pytest.raises(ValueError, match="candidate pool was built for"):
            ladder_candidates(
                tomorrow_only_conn,
                now_ms=pool.now_ms + 60_000,
                max_odds_age_ms=MAX_ODDS_AGE_MS,
                pool=pool,
            )

    def test_a_pool_under_another_freshness_rule_is_refused(
        self, tomorrow_only_conn
    ):
        """`max_odds_age_ms` sets the scan floor, so a pool built under a
        tighter rule can be missing rows the looser caller would have kept."""
        pool = self._pool(tomorrow_only_conn)
        with pytest.raises(ValueError, match="candidate pool was built for"):
            ladder_candidates(
                tomorrow_only_conn,
                now_ms=pool.now_ms,
                max_odds_age_ms=MAX_ODDS_AGE_MS * 2,
                pool=pool,
            )

    def test_the_matching_pool_is_accepted(self, tomorrow_only_conn):
        """The other half of the guard: it must not refuse the legitimate
        reuse the widening loop depends on."""
        pool = self._pool(tomorrow_only_conn)
        before = len(tomorrow_only_conn.statements)
        legs, _ = ladder_candidates(
            tomorrow_only_conn,
            now_ms=pool.now_ms,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
            horizon="tomorrow",
            pool=pool,
        )
        assert legs, "the bed should build legs one day out"
        assert tomorrow_only_conn.count("p_conservative") == 1
        # And it read nothing further: the whole point of passing a pool.
        assert len(tomorrow_only_conn.statements) == before


class TestOneScanAnswersEveryWindowTheSameWay:
    def test_the_widened_payload_matches_an_explicitly_named_window(
        self, tmp_path
    ):
        """The safety property behind the dedup: filtering one scan three ways
        must give what three scans gave. If the pool were rebuilt per window
        this would be tautological; with it shared, it is the real check that
        the window is still applied per call and not baked into the pool."""
        from backend.parlays import build_ladder_payload

        path = tmp_path / "equiv.db"
        conn = store.init_db(path)
        tomorrow = end_of_desk_day_ms(store.now_ms()) + 3_600_000
        computed = store.now_ms() - 30_000
        for i, (team, other) in enumerate(
            (("Reds", "Cubs"), ("Mets", "Pirates"), ("Rays", "Angels"))
        ):
            seed_game(
                conn,
                game=f"eq-{i}",
                team=team,
                other=other,
                p=0.74,
                computed_ms=computed,
                commence_ms=tomorrow,
            )
        conn.commit()
        now = store.now_ms()

        widened = build_ladder_payload_widening(
            conn, now_ms=now, max_odds_age_ms=MAX_ODDS_AGE_MS
        )
        named = build_ladder_payload(
            conn,
            now_ms=now,
            max_odds_age_ms=MAX_ODDS_AGE_MS,
            horizon=widened["window"]["key"],
        )
        assert [c.get("key") for c in widened["cards"]] == [
            c.get("key") for c in named["cards"]
        ]
        assert [c.get("not_built_reason") for c in widened["cards"]] == [
            c.get("not_built_reason") for c in named["cards"]
        ]
        assert widened["excluded"] == named["excluded"]
