"""A failed odds call must not present as freshly-bought odds. Schema v21.

THE DEFECT
----------
`odds/client.py` records the credit **before** checking the HTTP status. That
ordering is correct and is not what changed: some error classes still consume
credits, and undercounting spend is worse than overcounting it.

What was wrong is downstream. `_SERVED_SWEEP` (`odds/timing.py`) identified a
served sweep by endpoint and cost alone, so the row a 401 wrote satisfied it.
Therefore:

    1. `last_sweep_by_sport` moved that sport's stamp to now,
    2. `firing_for_slot` saw a sweep inside the refresh interval,
    3. the retry was **deferred a full ten minutes**, and
    4. `/api/window` reported the last sweep as seconds old.

An outage presented on the screen as *fresh data* — the one thing a freshness
clock exists to make impossible, done by the clock. Recorded 2026-08-17 in
`docs/JOE-odds-key-rotation.md:151-166` and left unfixed until 2026-08-25.

There was a second silence beside it. `odds_sweep_log` had four outcomes and
none of them could say "the upstream refused us": `refused` means *we* declined
on budget, `skipped` means the pass chose not to look, and `no_data` means the
call succeeded against an empty slate — a quiet night, the opposite of an
outage. So a failed call wrote no row in that table at all, and its only trace
was an `api_credits` row with NULL rate-limit headers, which is also what a
*successful* call looks like when the aggregator omits them. That module's own
docstring says it exists because "silence was indistinguishable from a system
that never looked". This was that case exactly.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about a transport failure.** `httpx.HTTPError` is raised before any
  row is written, costs no credits, and is a different path (`client.py`'s
  `except httpx.HTTPError`). These tests are about a call that *completed* and
  came back 4xx/5xx.
- **Nothing about the credit accounting.** A failed call still spends, still
  counts against the daily budget, and `test_odds.py` owns that claim. This
  file asserts only that spending and *succeeding* stopped sharing a row.
- **Nothing about recovery timing on the live box.** It proves the stamp does
  not move; whether the next pass actually re-buys depends on `decide_sweeps`
  and the budget, which `test_sweep_timing.py` owns.
- **Nothing about anyone noticing.** A `failed` row makes the outage legible.
  No alert reads it, exactly as the sweep-log module has always warned.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from backend.config import OddsConfig
from backend.odds.budget import CreditBudget
from backend.odds.client import OddsAPIError, OddsClient, QuotaExhausted
from backend.odds.sweeplog import FAILED, SERVED, record_sweep_outcome
from backend.odds.timing import last_sweep_by_sport
from backend.store import db

BASE = "https://api.test-odds.com/v4"
SPORT = "baseball_mlb"


def ms(iso: str) -> int:
    return int(
        datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000
    )


NOW = ms("2026-08-25T18:00:00")
DAY_START = ms("2026-08-25T00:00:00")


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "failed.db")
    yield c
    c.close()


@pytest.fixture
def budget(conn):
    return CreditBudget(conn, daily_budget=64)


@pytest.fixture
def odds_client(budget):
    config = OddsConfig(
        api_key="test-odds-key",
        base_url=BASE,
        daily_credit_budget=64,
        regions=["us"],
        markets=["h2h"],
    )
    return OddsClient(config, budget, client=httpx.AsyncClient(timeout=5.0))


def _sweep_log(conn) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT sport_key, outcome, detail, quotes_stored, failed_status "
            "FROM odds_sweep_log ORDER BY id"
        )
    ]


class TestAFailedCallDoesNotMoveTheFreshnessClock:
    """The defect itself, asserted through the predicate that carried it."""

    @respx.mock
    async def test_a_401_leaves_last_sweep_by_sport_empty(self, odds_client, conn):
        """The whole bug in one assertion.

        Mutation observed red: drop `AND COALESCE(http_status, 200) < 400` from
        `_SERVED_SWEEP` — the sport reappears here with a stamp of NOW, which is
        the ten-minute retry deferral.
        """
        respx.get(f"{BASE}/sports/{SPORT}/odds").mock(
            return_value=httpx.Response(401, text="unauthorised")
        )
        with pytest.raises(OddsAPIError):
            await odds_client.fetch_odds(SPORT, now_ms=NOW)

        assert last_sweep_by_sport(conn, since_ms=DAY_START) == {}

    @respx.mock
    async def test_the_credit_is_still_charged(self, odds_client, conn):
        """The ordering that caused the bug is deliberate and stays.

        Some error classes consume credits upstream, so a failed call that
        recorded nothing would understate spend in exactly the situation where
        the count matters most. The fix separates "spent" from "succeeded"; it
        does not stop recording the spend.
        """
        respx.get(f"{BASE}/sports/{SPORT}/odds").mock(
            return_value=httpx.Response(401, text="unauthorised")
        )
        with pytest.raises(OddsAPIError):
            await odds_client.fetch_odds(SPORT, now_ms=NOW)

        row = conn.execute(
            "SELECT cost, http_status FROM api_credits"
        ).fetchone()
        assert row["cost"] > 0
        assert row["http_status"] == 401

    @respx.mock
    async def test_a_429_is_recorded_the_same_way(self, odds_client, conn):
        """`QuotaExhausted` is a different exception and the same row shape.

        Mutation observed red: move the `record_sweep_outcome` call below the
        `if response.status_code == 429` branch — the 429 then raises first and
        writes no sweep-log row, which is the quota outage going silent.
        """
        respx.get(f"{BASE}/sports/{SPORT}/odds").mock(
            return_value=httpx.Response(429, text="slow down")
        )
        with pytest.raises(QuotaExhausted):
            await odds_client.fetch_odds(SPORT, now_ms=NOW)

        assert last_sweep_by_sport(conn, since_ms=DAY_START) == {}
        assert _sweep_log(conn)[0]["failed_status"] == 429

    @respx.mock
    async def test_a_successful_call_still_moves_the_clock(self, odds_client, conn):
        """The other half, and the one that makes the guard non-trivial.

        A predicate that excluded everything would pass every test above. This
        is the assertion that fails if `COALESCE(http_status, 200)` is written
        as, say, `http_status < 400` — which would silently exclude every
        pre-v21 row and every row where the status is genuinely unknown.
        """
        respx.get(f"{BASE}/sports/{SPORT}/odds").mock(
            return_value=httpx.Response(200, json=[])
        )
        await odds_client.fetch_odds(SPORT, now_ms=NOW)

        assert last_sweep_by_sport(conn, since_ms=DAY_START) == {SPORT: NOW}

    def test_a_pre_v21_row_still_counts_as_a_served_sweep(self, conn):
        """No backfill, so every row written before this column must count
        exactly as it did before. `COALESCE(..., 200)` is what buys that, and
        the rows it protects are the entire existing live record.

        Written by hand rather than through the client, because the point is a
        row with `http_status IS NULL` and no code path produces one any more.
        """
        conn.execute(
            "INSERT INTO api_credits (called_ms, endpoint, sport_key, cost) "
            "VALUES (?, ?, ?, ?)",
            (NOW, f"/sports/{SPORT}/odds", SPORT, 4),
        )
        conn.commit()
        assert last_sweep_by_sport(conn, since_ms=DAY_START) == {SPORT: NOW}


class TestTheOutageIsLegibleInTheSweepLog:
    """The second silence: a failed call used to write no row here at all."""

    @respx.mock
    async def test_a_failed_call_writes_a_failed_row(self, odds_client, conn):
        """Mutation observed red: delete the `record_sweep_outcome` call from
        `client.py`'s `>= 400` branch — the log goes empty and the outage is
        invisible again."""
        respx.get(f"{BASE}/sports/{SPORT}/odds").mock(
            return_value=httpx.Response(503, text="upstream down")
        )
        with pytest.raises(OddsAPIError):
            await odds_client.fetch_odds(SPORT, now_ms=NOW)

        rows = _sweep_log(conn)
        assert len(rows) == 1
        assert rows[0]["outcome"] == FAILED
        assert rows[0]["failed_status"] == 503
        assert rows[0]["sport_key"] == SPORT

    @respx.mock
    async def test_the_detail_names_the_status_and_says_the_credit_was_spent(
        self, odds_client, conn
    ):
        """`detail` is for a human and `failed_status` is for a query. Both,
        because "the key is dead" and "the aggregator is having a bad hour"
        need opposite responses and only the number separates them at scale."""
        respx.get(f"{BASE}/sports/{SPORT}/odds").mock(
            return_value=httpx.Response(401, text="unauthorised")
        )
        with pytest.raises(OddsAPIError):
            await odds_client.fetch_odds(SPORT, now_ms=NOW)

        detail = _sweep_log(conn)[0]["detail"]
        assert "401" in detail
        assert "credits were still charged" in detail

    def test_failed_status_is_refused_on_every_other_outcome(self, conn):
        """A status on a `served` row would say the call both worked and did
        not. The CHECK in `schema.sql` is the guarantee; this is the readable
        error beside it.

        Mutation observed red: delete the `failed_status is not None` guard in
        `record_sweep_outcome` — `sqlite3.IntegrityError` replaces `ValueError`,
        which is the constraint catching what the function should have.
        """
        with pytest.raises(ValueError, match="failed_status"):
            record_sweep_outcome(
                conn,
                pass_ms=NOW,
                outcome=SERVED,
                detail="quotes stored",
                quotes_stored=12,
                failed_status=401,
            )

    def test_failed_is_distinct_from_the_four_it_could_have_borrowed(self, conn):
        """The vocabulary gap, stated as a claim rather than a comment.

        `refused` = we declined on budget. `skipped` = the pass chose not to
        look. `no_data` = the call worked and the slate was empty. None of them
        means "the upstream refused us", and writing a failure as any of them
        would misdirect the only person who ever reads this table.
        """
        from backend.odds.sweeplog import NO_DATA, OUTCOMES, REFUSED, SKIPPED

        assert FAILED in OUTCOMES
        assert FAILED not in (SERVED, REFUSED, NO_DATA, SKIPPED)
        assert len(set(OUTCOMES)) == 5
