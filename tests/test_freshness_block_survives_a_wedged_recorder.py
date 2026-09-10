"""The "why the desk is empty" block must not go silent as the outage worsens.

WHY THIS EXISTS
---------------
`Freshness` in `ParlayCards.tsx` exists because of a specific incident: on
2026-08-25 Joe read "needs 2 fresh games and the slate has 0" as "there is
nothing on tonight", while twenty fixtures sat upcoming and the recording loop
was wedged. The block supplies the half the card sentence cannot see.

It was gated on `ladder.excluded.stale_consensus > 0`. That count only sees
sides the candidate scan RETURNED and the freshness rule then refused -- and
the scan has its own floor, `now - max(8 * MAX_ODDS_AGE_S, 2h)`
(`_CANDIDATE_SCAN_FLOOR_MULTIPLE`, `_CANDIDATE_SCAN_MIN_MS`). A row older than
that is never selected, so it is never counted:

    recorder wedged under 2h    rows in-scan, refused    stale > 0    fires
    recorder wedged over 2h     rows out of scan         stale = 0    SILENT

So the block got quieter the longer the recorder stayed down, and was silent in
exactly the incident it was written for. `/api/window` is the second trigger
because it counts *fixtures*, not candidate rows.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about the live recorder.** These build their own pools; the live
  recorder's health is `/api/health` and `scripts/inspect_live_db.py sweep-log`.
- **Nothing about what the reader does next.** The exit line and the tap are
  `StaleOddsExit`, tested with the slate.
- **It does not test React.** There is no frontend test runner in this repo, so
  the component half is asserted against the source, which is how every other
  `.tsx` claim here is pinned. That catches a gate rewritten to the old
  predicate; it would not catch a rendering bug.
"""

from __future__ import annotations

import pathlib

import pytest

from backend.store import db as store
from backend.parlays import build_ladder_payload
from tests.test_parlays_api import seed_game

REPO = pathlib.Path(__file__).resolve().parents[1]
CARDS = REPO / "frontend" / "src" / "components" / "ParlayCards.tsx"

#: The scan floor at the deployed `MAX_ODDS_AGE_S`. A row older than this is
#: not "stale", it is invisible.
SCAN_FLOOR_MS = 2 * 3_600_000
MAX_ODDS_AGE_MS = 900_000


@pytest.fixture
def source() -> str:
    return CARDS.read_text(encoding="utf-8")


class TestTheCountGoesToZeroWhenTheOutageGetsWorse:
    """The server-side fact the gate was reading wrong."""

    def _payload(self, tmp_path, *, age_ms: int) -> dict:
        path = tmp_path / f"wedged-{age_ms}.db"
        conn = store.init_db(path)
        now = store.now_ms()
        for i, (team, other) in enumerate(
            (("Reds", "Cubs"), ("Mets", "Pirates"), ("Rays", "Angels"))
        ):
            seed_game(
                conn,
                game=f"wedged-{i}",
                team=team,
                other=other,
                p=0.74,
                computed_ms=now - age_ms,
                oldest_book_age_ms=age_ms,
            )
        conn.commit()
        return build_ladder_payload(
            conn, now_ms=now, max_odds_age_ms=MAX_ODDS_AGE_MS
        )

    def test_a_recently_wedged_recorder_counts_its_stale_sides(self, tmp_path):
        """Inside the scan floor: the rows are returned, then refused."""
        payload = self._payload(tmp_path, age_ms=SCAN_FLOOR_MS // 2)
        assert payload["excluded"].get("stale_consensus", 0) > 0
        assert any(c.get("not_built_reason") for c in payload["cards"])

    def test_a_long_wedged_recorder_counts_nothing_at_all(self, tmp_path):
        """Past the scan floor the same outage reports an EMPTY histogram.

        This is the whole defect in one assertion: the desk is more broken and
        the number the screen keyed on has gone DOWN, to zero.
        """
        payload = self._payload(tmp_path, age_ms=SCAN_FLOOR_MS * 2)
        assert payload["excluded"].get("stale_consensus", 0) == 0
        assert all(c.get("not_built_reason") for c in payload["cards"])

    def test_the_two_outages_differ_only_in_how_long(self, tmp_path):
        """Guards against the beds diverging: same seed, same rule, one clock."""
        recent = self._payload(tmp_path, age_ms=SCAN_FLOOR_MS // 2)
        long = self._payload(tmp_path, age_ms=SCAN_FLOOR_MS * 2)
        assert len(recent["cards"]) == len(long["cards"])
        assert recent["excluded"].get("stale_consensus", 0) > long["excluded"].get(
            "stale_consensus", 0
        )


class TestTheGateReadsFixturesAndNotOnlyRows:
    def test_it_does_not_return_null_on_a_zero_stale_count_alone(self, source):
        """The old gate, in words: `stale === 0` could not by itself hide the
        block, or the >2h outage renders nothing."""
        assert "if (stale === 0 || unbuilt === 0) return null;" not in source, (
            "the gate is back to counting candidate rows only, and goes silent "
            "once the recorder has been wedged past the candidate scan floor"
        )

    def test_the_second_trigger_counts_fixtures(self, source):
        """`/api/window` survives the rows dropping out of scan."""
        assert "actionable.fixtures_upcoming > 0" in source
        assert "actionable.fixtures_fresh === 0" in source

    def test_it_still_requires_a_card_to_have_been_lost(self, source):
        """The conjunction is not abandoned: a working screen stays quiet."""
        assert "if (unbuilt === 0) return null;" in source

    def test_it_stays_silent_without_a_timetable(self, source):
        """With no `/api/window`, an uncounted stale pool and an empty schedule
        are indistinguishable, and the block must not guess between them."""
        assert "if (stale === 0 && !nothingFresh) return null;" in source


class TestItDoesNotReportZeroRefusalsAsGoodNews:
    def test_the_refused_on_age_sentence_is_gated_on_a_nonzero_count(
        self, source
    ):
        """"all 0 candidate sides were refused on age" is both nonsense and
        flattering -- it reads as though nothing was dropped."""
        assert "} old — so all {stale} candidate side" in source, (
            "the stale-count sentence moved; re-check it is still gated"
        )
        assert ") : stale > 0 ? (" in source, (
            "the stale-count sentence is no longer gated on stale > 0, so the "
            "zero-count branch will render 'all 0 ... were refused on age'"
        )

    def test_the_zero_branch_explains_the_empty_left_out_line(self, source):
        """`Excluded` renders nothing when every count is zero, so this branch
        has to say why the absence is not reassurance."""
        # Fragments, not the whole sentence: JSX wraps prose across lines, so
        # a substring spanning a line break fails on formatting alone.
        assert "the count is zero because the prices never reached" in source
        assert "the shortlist, not because they passed" in source
        assert "no longer reads them at all" in source
