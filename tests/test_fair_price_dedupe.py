"""`write_fair_price` stops inserting a row for a consensus that has not
moved — ADR 0133.

Measured on live, three windows on 2026-09-09 (an MLB slate): 99.6-99.75% of
consecutive passes for one (link_id, market, outcome_name, outcome_point)
wrote a byte-for-byte identical row, and `fair_prices` plus its two indexes
were 47.5% of a 5.07 GB database. `run_pricing_pass` and `run_quote_pass` both
call `write_fair_price` every pass regardless of whether the odds moved
(`scripts/run_loop.py:1441`, `:1480`), so an unchanged consensus was being
re-recorded roughly every 15-20s.

**The identity is FIVE columns, not four.** `outcome_description` distinguishes
two players priced at the same line in the same game -- `outcome_name` alone
is only `"Over"`/`"Under"` on a prop -- and it must be part of the row's
IDENTITY, never compared as payload. An earlier draft of this change used a
four-column key (dropping `outcome_description`) and the 99.7% figure quoted
above was measured against that key, which scores two different players'
distinct rows as "changed" relative to each other -- so 99.7% is a FLOOR on
the true duplication rate with the five-column identity this file implements,
not a measurement of it.

WHAT THIS FILE DOES NOT ESTABLISH
----------------------------------
- **A duplication rate.** That is `docs/measurements/2026-09-09-*`, run
  against the live database. This is a correctness suite for the dedupe
  mechanism, on synthetic rows.
- **That the freshness gate is measured on live.** `_live_age_ms` and the
  scan-floor tests here are against synthetic rows too; ADR 0133 states what a
  single day's MLB slate does not establish about an NFL Sunday's window
  profile.
- **Anything about odds-buying decisions.** `write_fair_price` is reached only
  from the offline pricing/quote passes; nothing here touches `backend/odds/*`
  or `backend/scheduler.py`, and `TestTheFreezeIsRespected` below checks that
  mechanically rather than asserting it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import backend.runner as runner_mod
from backend.core.devig import consensus_devig
from backend.runner import write_fair_price
from backend.store import db

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "dedupe.db")
    yield c
    c.close()


@pytest.fixture
def link_id(conn) -> int:
    """One minimal linked event, satisfying `fair_prices.link_id`'s FK."""
    conn.execute(
        "INSERT INTO kalshi_events (event_ticker, title, first_seen_ms, "
        "last_seen_ms) VALUES ('KXTEST-DEDUPE', 'Test Event', 0, 0)"
    )
    conn.execute(
        "INSERT INTO event_links (kalshi_event_ticker, odds_event_id, "
        "league, method, commence_skew_ms, linked_ms) "
        "VALUES ('KXTEST-DEDUPE', 'oe-dedupe', 'baseball_mlb', 'test', 0, 0)"
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM event_links WHERE kalshi_event_ticker = 'KXTEST-DEDUPE'"
    ).fetchone()["id"]


def _consensus(book_a=(1.91, 2.05), book_b=(1.90, 2.06), outcomes=("Home", "Away")):
    """A real `DevigResult` + metadata, from two books priced apart.

    Real `consensus_devig`, not a hand-built `DevigResult` -- the dedupe
    comparison reads the actual method columns it produces, and a fake object
    could accidentally agree with itself in a way real devig arithmetic never
    would.
    """
    return consensus_devig(
        outcomes,
        {"book_a": list(book_a), "book_b": list(book_b)},
    )


def _row_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) n FROM fair_prices").fetchone()["n"]


class TestAnUnchangedPassConfirmsRatherThanInserts:
    """The core claim: a repeated payload updates one row, never adds a second."""

    def test_two_identical_passes_leave_one_row_per_outcome(self, conn, link_id):
        result, metadata = _consensus()
        ids1 = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=1_000, oldest_book_age_ms=500,
        )
        ids2 = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=2_000, oldest_book_age_ms=100,
        )
        assert ids1 == ids2, "an unchanged pass minted new row ids"
        assert _row_count(conn) == len(result.outcomes), (
            "a second identical pass inserted instead of confirming"
        )

    def test_computed_ms_and_oldest_book_age_ms_freeze_at_first_write(
        self, conn, link_id
    ):
        """The pair `recommendations.fair_price_id` points at must not move,
        or the record's "when did this consensus first appear" is lost."""
        result, metadata = _consensus()
        ids1 = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=1_000, oldest_book_age_ms=500,
        )
        write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=99_000, oldest_book_age_ms=1,
        )
        row = conn.execute(
            "SELECT computed_ms, oldest_book_age_ms FROM fair_prices WHERE id = ?",
            (ids1["Home"],),
        ).fetchone()
        assert row["computed_ms"] == 1_000
        assert row["oldest_book_age_ms"] == 500

    def test_the_confirmation_pair_moves_to_this_passes_instant(
        self, conn, link_id
    ):
        result, metadata = _consensus()
        ids1 = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=1_000, oldest_book_age_ms=500,
        )
        write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=99_000, oldest_book_age_ms=1,
        )
        row = conn.execute(
            "SELECT confirmed_ms, confirmed_oldest_book_age_ms FROM "
            "fair_prices WHERE id = ?",
            (ids1["Home"],),
        ).fetchone()
        assert row["confirmed_ms"] == 99_000
        assert row["confirmed_oldest_book_age_ms"] == 1

    def test_a_never_confirmed_row_carries_null_confirmation(self, conn, link_id):
        result, metadata = _consensus()
        ids1 = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=1_000, oldest_book_age_ms=500,
        )
        row = conn.execute(
            "SELECT confirmed_ms, confirmed_oldest_book_age_ms FROM "
            "fair_prices WHERE id = ?",
            (ids1["Home"],),
        ).fetchone()
        assert row["confirmed_ms"] is None
        assert row["confirmed_oldest_book_age_ms"] is None


class TestAChangedConsensusIsRecordedAsANewRow:
    """The guard must not be so eager it swallows a real price move."""

    def test_a_real_price_move_inserts_rather_than_confirms(self, conn, link_id):
        result1, metadata1 = _consensus(book_a=(1.91, 2.05), book_b=(1.90, 2.06))
        result2, metadata2 = _consensus(book_a=(1.80, 2.20), book_b=(1.79, 2.21))
        ids1 = write_fair_price(
            conn, link_id=link_id, devig_result=result1, metadata=metadata1,
            computed_ms=1_000, oldest_book_age_ms=500,
        )
        ids2 = write_fair_price(
            conn, link_id=link_id, devig_result=result2, metadata=metadata2,
            computed_ms=2_000, oldest_book_age_ms=100,
        )
        assert ids1 != ids2, "a real price move was confirmed instead of recorded"
        assert _row_count(conn) == 2 * len(result1.outcomes)

    def test_a_book_count_change_with_the_same_prices_is_recorded(
        self, conn, link_id
    ):
        """`book_count` is payload, not identity, and not derivable from the
        method columns alone -- a book dropping out and the consensus not
        moving (a coincidence, not a contradiction) must still be recorded."""
        result, metadata = _consensus()
        ids1 = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=1_000, oldest_book_age_ms=500,
        )
        changed = dict(metadata)
        changed["book_count"] = metadata["book_count"] + 1
        ids2 = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=changed,
            computed_ms=2_000, oldest_book_age_ms=100,
        )
        assert ids1 != ids2, "a real book_count change was silently confirmed"
        assert _row_count(conn) == 2 * len(result.outcomes)

    def test_dropping_book_count_from_the_payload_hides_a_real_change(
        self, conn, link_id, monkeypatch
    ):
        """Mutation guard, observed red without the fix.

        Simulates the exact failure `_FAIR_PRICE_PAYLOAD_COLUMNS` being
        DERIVED (never hand-typed) exists to prevent: shrink the comparison
        by one column and a real change in that column stops being detected.
        `test_a_book_count_change_with_the_same_prices_is_recorded` above is
        the same scenario with the guard intact; this is it disabled.
        """
        result, metadata = _consensus()
        ids1 = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=1_000, oldest_book_age_ms=500,
        )
        changed = dict(metadata)
        changed["book_count"] = metadata["book_count"] + 1

        trimmed = tuple(
            c for c in runner_mod._FAIR_PRICE_PAYLOAD_COLUMNS if c != "book_count"
        )
        monkeypatch.setattr(runner_mod, "_FAIR_PRICE_PAYLOAD_COLUMNS", trimmed)

        ids2 = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=changed,
            computed_ms=2_000, oldest_book_age_ms=100,
        )
        assert ids2 == ids1, "the mutation was supposed to hide the change"
        stored = conn.execute(
            "SELECT book_count FROM fair_prices WHERE id = ?", (ids1["Home"],)
        ).fetchone()
        assert stored["book_count"] == metadata["book_count"], (
            "a real book_count change was swallowed once the comparison "
            "no longer covered the column it changed in -- this is the "
            "failure mode `_FAIR_PRICE_PAYLOAD_COLUMNS` being DERIVED from "
            "the INSERT's own column list exists to prevent"
        )


class TestTheIdentityIsFiveColumns:
    """`outcome_description` must be identity, not payload -- a prop rung.

    On a prop, `outcome_name` is only `"Over"`/`"Under"`; the player and the
    line are what make two rows distinguishable. `backend/parlays.py`'s
    `CANDIDATE_SQL` already partitions on all five columns
    (`f.link_id, f.market, f.outcome_name, f.outcome_description,
    f.outcome_point`) and the registered row identity in
    `docs/measurements/2026-09-01-preregistration-fair-prices-downsample.md`
    (D4) does too.
    """

    def test_two_players_at_one_rung_get_two_rows_not_one(self, conn, link_id):
        result, metadata = _consensus(outcomes=("Over", "Under"))
        idsA = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=1_000, market="pitcher_strikeouts",
            outcome_description="Pitcher A", outcome_point=5.5,
            oldest_book_age_ms=100,
        )
        idsB = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=1_100, market="pitcher_strikeouts",
            outcome_description="Pitcher B", outcome_point=5.5,
            oldest_book_age_ms=100,
        )
        assert idsA["Over"] != idsB["Over"], (
            "two different players at the same rung collapsed onto one row"
        )
        assert _row_count(conn) == 2 * len(result.outcomes)

    def test_reconfirming_one_player_does_not_touch_the_others_row(
        self, conn, link_id
    ):
        result, metadata = _consensus(outcomes=("Over", "Under"))
        idsA1 = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=1_000, market="pitcher_strikeouts",
            outcome_description="Pitcher A", outcome_point=5.5,
            oldest_book_age_ms=100,
        )
        idsB = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=1_100, market="pitcher_strikeouts",
            outcome_description="Pitcher B", outcome_point=5.5,
            oldest_book_age_ms=100,
        )
        idsA2 = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=2_000, market="pitcher_strikeouts",
            outcome_description="Pitcher A", outcome_point=5.5,
            oldest_book_age_ms=50,
        )
        assert idsA2 == idsA1, "confirming A minted a new row instead of A's own"
        assert _row_count(conn) == 2 * len(result.outcomes), (
            "confirming A inserted a third row instead of updating A's"
        )
        b_row = conn.execute(
            "SELECT confirmed_ms FROM fair_prices WHERE id = ?",
            (idsB["Over"],),
        ).fetchone()
        assert b_row["confirmed_ms"] is None, "B's row was touched by A's confirm"

    def test_a_four_column_key_would_collide_the_two_players(
        self, conn, link_id, monkeypatch
    ):
        """Mutation guard, observed red without `outcome_description` in the
        identity. An earlier draft of this change used exactly this
        four-column key; this is what it did to two players at one rung."""
        trimmed = tuple(
            c for c in runner_mod._FAIR_PRICE_KEY_COLUMNS
            if c != "outcome_description"
        )
        monkeypatch.setattr(runner_mod, "_FAIR_PRICE_KEY_COLUMNS", trimmed)
        # The payload comparison must also drop it, or it stays compared
        # twice (once as a phantom key, once as payload) -- recompute exactly
        # as the module does, from the (mutated) key.
        repayload = tuple(
            c for c in runner_mod._FAIR_PRICE_INSERT_COLUMNS
            if c not in trimmed and c not in runner_mod._FAIR_PRICE_FROZEN_COLUMNS
        )
        monkeypatch.setattr(runner_mod, "_FAIR_PRICE_PAYLOAD_COLUMNS", repayload)

        result, metadata = _consensus(outcomes=("Over", "Under"))
        idsA1 = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=1_000, market="pitcher_strikeouts",
            outcome_description="Pitcher A", outcome_point=5.5,
            oldest_book_age_ms=100,
        )
        write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=1_100, market="pitcher_strikeouts",
            outcome_description="Pitcher B", outcome_point=5.5,
            oldest_book_age_ms=100,
        )
        idsA2 = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=2_000, market="pitcher_strikeouts",
            outcome_description="Pitcher A", outcome_point=5.5,
            oldest_book_age_ms=50,
        )
        # With description out of the identity, re-pricing A finds B's more
        # recent row, sees a payload mismatch (the description itself), and
        # inserts a THIRD row rather than confirming A's own.
        assert idsA2 != idsA1, (
            "the mutation was supposed to make A's re-confirm collide with B"
        )
        assert _row_count(conn) == 3 * len(result.outcomes), (
            "expected the four-column key to mint a spurious third row"
        )


class TestOutcomePointNullSemantics:
    """`outcome_point` (and `outcome_description`) are NULL on every team
    market. `col = ?` never matches a bound NULL in SQL; `col IS ?` does."""

    def test_moneyline_dedupe_works_despite_null_outcome_point(
        self, conn, link_id
    ):
        result, metadata = _consensus(outcomes=("Home", "Away"))
        ids1 = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=1_000, market="h2h", oldest_book_age_ms=500,
        )
        ids2 = write_fair_price(
            conn, link_id=link_id, devig_result=result, metadata=metadata,
            computed_ms=2_000, market="h2h", oldest_book_age_ms=100,
        )
        assert ids1 == ids2, (
            "a NULL outcome_point (and outcome_description) prevented "
            "dedupe from finding a moneyline row's own previous write -- "
            "check the lookup uses IS, not ="
        )
        assert _row_count(conn) == len(result.outcomes)


class TestTheComparisonKeyCannotDriftFromTheInsert:
    def test_the_insert_columns_partition_exactly_into_key_payload_and_frozen(
        self,
    ):
        key = set(runner_mod._FAIR_PRICE_KEY_COLUMNS)
        frozen = set(runner_mod._FAIR_PRICE_FROZEN_COLUMNS)
        payload = set(runner_mod._FAIR_PRICE_PAYLOAD_COLUMNS)
        insert = set(runner_mod._FAIR_PRICE_INSERT_COLUMNS)
        assert key & frozen == set(), "a column is both identity and frozen"
        assert key & payload == set(), "a column is both identity and payload"
        assert frozen & payload == set(), "a column is both frozen and payload"
        assert key | frozen | payload == insert, (
            "the three partitions do not cover every INSERT column"
        )

    def test_five_key_two_frozen_ten_payload(self):
        """The exact split, pinned as a number so a silent column addition to
        one bucket without the others is visible in a diff."""
        assert len(runner_mod._FAIR_PRICE_KEY_COLUMNS) == 5
        assert len(runner_mod._FAIR_PRICE_FROZEN_COLUMNS) == 2
        assert len(runner_mod._FAIR_PRICE_PAYLOAD_COLUMNS) == 10
        assert len(runner_mod._FAIR_PRICE_INSERT_COLUMNS) == 17


class TestTheFreezeIsRespected:
    """The odds path is frozen until 10:00Z 2026-09-14 to protect a
    credit-convergence readout (partner ruling, three conditions). This
    checks condition 1 mechanically: no file under `backend/odds/`, and not
    `backend/scheduler.py`, differs from this lane's merge-base with `main`.

    Best-effort: skips rather than fails when git cannot answer (a shallow
    clone with no local `main`, or no `.git` at all) -- the same posture
    `tests/test_parallel_lanes_do_not_collide.py` takes for the same reason,
    and for the same reason a SKIP here is not a pass: read the skip reason.
    """

    def _changed_files(self) -> list[str] | None:
        try:
            merge_base = subprocess.run(
                ["git", "--no-optional-locks", "merge-base", "HEAD", "main"],
                cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=15,
            )
            if merge_base.returncode != 0:
                return None
            base = merge_base.stdout.strip()
            diff = subprocess.run(
                ["git", "--no-optional-locks", "diff", "--name-only", base],
                cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=15,
            )
            if diff.returncode != 0:
                return None
            return [line for line in diff.stdout.splitlines() if line]
        except (OSError, subprocess.TimeoutExpired):
            return None

    def test_no_odds_file_and_no_scheduler_file_changed(self):
        changed = self._changed_files()
        if changed is None:
            pytest.skip("git could not establish a merge-base with main here")
        forbidden = [
            path for path in changed
            if path.startswith("backend/odds/") or path == "backend/scheduler.py"
        ]
        assert forbidden == [], (
            f"the odds-path freeze was crossed: {forbidden}"
        )
