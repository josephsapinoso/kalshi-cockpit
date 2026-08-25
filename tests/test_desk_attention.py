"""`backend/odds/attention.py`: the fact the odds feed will follow instead of
the clock.

The expensive failure here is a false **present**, not a false absent, and that
is what most of this file is about. If attention reads absent when someone is
looking, the slate is stale for up to an hour and the person taps refresh. If it
reads present when nobody is, the feed buys at the ten-minute cadence forever --
~1,152 credits/day at two sports and ~2,304 at four, against a 20,000/month
tier. So `None` must never become `0`, an empty table must never read as
attended, and a stale stamp must expire.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **Nothing about whether a human is reading the page.** A stamp is a claim by
  a browser that the tab is open and visible. A page left on a second monitor
  stamps identically. That is the honest limit of a heartbeat and it is why the
  design has a sub-ceiling as well as a TTL.
- **Nothing about the trigger.** No sweep is decided here; `odds/timing.py`
  owns that and has its own tests.
- **Nothing about the heartbeat arriving.** The client half is `Nav.tsx` and the
  route, and whether a browser actually posts is not decidable from Python.
- **Nothing about the saving.** `seen_at_least_once_since` is the instrument
  that would measure it. Running it on a fixture proves it counts, not that the
  page is open for any particular number of hours a day.
"""

from __future__ import annotations

import pytest

from backend.odds import attention
from backend.store import db

MIN = 60_000
NOW = 1_787_680_800_000  # 2026-08-25T18:00:00Z


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "attention.db")
    yield c
    c.close()


class TestAnEmptyRecordIsNotAttended:
    """The table ships empty on every deploy, so this is the state the live box
    is in the moment the change lands."""

    def test_last_seen_is_none_not_zero(self, conn):
        """Mutation observed red: `return int(row["seen_ms"] or 0)`.

        `0` is not merely untidy: every caller does `now_ms - seen`, and against
        `0` that is 56 years, which happens to be the safe answer here and would
        not be in any caller that compares the other way. The convention exists
        so the caller never has to know which direction it got lucky in.
        """
        assert attention.last_seen_ms(conn) is None

    def test_nobody_looking_means_not_attended(self, conn):
        assert attention.is_attended(conn, now_ms=NOW) is False


class TestTheTtlBoundsWhatOneVisitBuys:
    def test_a_fresh_stamp_is_attended(self, conn):
        attention.stamp(conn, now_ms=NOW)
        assert attention.is_attended(conn, now_ms=NOW) is True

    def test_a_stamp_inside_the_ttl_is_still_attended(self, conn):
        attention.stamp(conn, now_ms=NOW)
        assert attention.is_attended(conn, now_ms=NOW + 4 * MIN) is True

    def test_a_stamp_past_the_ttl_has_expired(self, conn):
        """The whole cost control. Mutation observed red: change `<=` to `>=`
        in `is_attended` — a closed tab then keeps buying forever, which is the
        1,152/day worst case with nobody watching."""
        attention.stamp(conn, now_ms=NOW)
        assert attention.is_attended(conn, now_ms=NOW + 6 * MIN) is False

    def test_the_boundary_is_inclusive(self, conn):
        """Exactly `ttl_ms` old is still attended. Stated because a
        half-open interval here and a closed one in the caller is the kind of
        disagreement that shows up as one extra sweep per visit and never gets
        attributed."""
        attention.stamp(conn, now_ms=NOW)
        ttl = attention.DEFAULT_ATTENTION_TTL_MS
        assert attention.is_attended(conn, now_ms=NOW + ttl) is True
        assert attention.is_attended(conn, now_ms=NOW + ttl + 1) is False

    def test_the_ttl_is_caller_overridable(self, conn):
        """The trigger passes its own, so the default must not be load-bearing
        in two places."""
        attention.stamp(conn, now_ms=NOW)
        assert attention.is_attended(conn, now_ms=NOW + 30 * MIN, ttl_ms=MIN) is False
        assert (
            attention.is_attended(conn, now_ms=NOW + 30 * MIN, ttl_ms=60 * MIN)
            is True
        )

    def test_the_latest_stamp_wins_not_the_first(self, conn):
        """`MAX(seen_ms)`, not `LIMIT 1` on insertion order. They agree while
        stamps arrive in order and disagree the moment anything backfills."""
        attention.stamp(conn, now_ms=NOW)
        attention.stamp(conn, now_ms=NOW + 20 * MIN)
        attention.stamp(conn, now_ms=NOW + 10 * MIN)
        assert attention.last_seen_ms(conn) == NOW + 20 * MIN
        assert attention.is_attended(conn, now_ms=NOW + 22 * MIN) is True


class TestTheRecordIsAppendOnly:
    """A single mutable row would answer the trigger and destroy the instrument."""

    def test_every_stamp_is_a_row(self, conn):
        """Mutation observed red: make `stamp` an UPSERT on a fixed id — the
        count collapses to 1 and the "how long is the page actually open"
        question becomes unanswerable from the record."""
        for i in range(5):
            attention.stamp(conn, now_ms=NOW + i * MIN)
        n = conn.execute("SELECT COUNT(*) AS n FROM desk_attention").fetchone()
        assert n["n"] == 5

    def test_the_instrument_counts_within_a_window(self, conn):
        attention.stamp(conn, now_ms=NOW - 90 * MIN)
        attention.stamp(conn, now_ms=NOW - 10 * MIN)
        attention.stamp(conn, now_ms=NOW)
        assert attention.seen_at_least_once_since(conn, since_ms=NOW - 60 * MIN) == 2

    def test_the_instrument_is_zero_rather_than_none_on_an_empty_record(self, conn):
        """A count genuinely is zero here — nothing was unreadable. This is the
        one place `0` is the honest answer, and it is worth pinning next to the
        tests that insist `None` elsewhere, so the distinction is deliberate
        rather than inconsistent."""
        assert attention.seen_at_least_once_since(conn, since_ms=0) == 0

    def test_the_instrument_is_not_wired_into_the_trigger(self):
        """It measures; it must not decide.

        The sweep path reads `is_attended` and nothing else. A counter that
        acquired a caller in `timing.py` would make the trigger depend on how
        often a browser happened to poll, which is a client detail.
        """
        from pathlib import Path

        timing = (
            Path(__file__).resolve().parents[1] / "backend" / "odds" / "timing.py"
        ).read_text(encoding="utf-8")
        assert "seen_at_least_once_since" not in timing


class TestAFutureStampDoesNotBuyForever:
    def test_a_stamp_ahead_of_now_reads_as_attended(self, conn):
        """Server clock moved backwards. Attended is the right reading — the
        stamp was written with the server's own clock — and the TTL still
        bounds it, so this cannot become an unbounded buy."""
        attention.stamp(conn, now_ms=NOW + 10 * MIN)
        assert attention.is_attended(conn, now_ms=NOW) is True
