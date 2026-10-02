"""#279: when every window builds nothing, the payload says why.

WHY THIS EXISTS
---------------
Observed 2026-10-02 04:17Z: every preset card read "needs N fresh games and
the slate has 0" while the real cause was odds 152-271 minutes old against a
900 s limit. The widening loop returned the `tonight` payload and dropped every
other window's counts, so nothing on the screen could name staleness.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about which legs qualify.** This is copy: the cards are still
  tonight's, and no window's selection rule moved.
- **Nothing about how often odds go stale.** No frequency is stated or tested.
"""

from __future__ import annotations

from pathlib import Path

from backend.parlays import HORIZON_LADDER, build_ladder_payload_widening
from backend.store import db as store
from tests.test_parlays_api import seed_game

REPO = Path(__file__).resolve().parents[1]
MAX_AGE_MS = 900_000


def _stale_db(tmp_path):
    conn = store.init_db(tmp_path / "empty_reason.db")
    for i, (team, other) in enumerate((("Reds", "Cubs"), ("Mets", "Pirates"))):
        seed_game(
            conn,
            game=f"stale-{i}",
            team=team,
            other=other,
            p=0.74,
            computed_ms=store.now_ms() - 3_600_000,
        )
    conn.commit()
    return conn


def test_empty_presets_name_stale_odds_when_odds_are_stale(tmp_path) -> None:
    conn = _stale_db(tmp_path)
    payload = build_ladder_payload_widening(
        conn, now_ms=store.now_ms(), max_odds_age_ms=MAX_AGE_MS
    )
    assert all(c.get("not_built_reason") for c in payload["cards"])
    empty = payload["all_windows_empty"]
    assert empty["stale_consensus"] >= 1
    assert empty["widest_key"] == HORIZON_LADDER[-1]
    assert empty["excluded"]["stale_consensus"] == empty["stale_consensus"]
    # The cards stay tonight's: copy only, no change to what qualifies.
    assert payload["window"]["key"] == HORIZON_LADDER[0]
    assert "widened_from" not in payload["window"]


def test_a_window_that_builds_carries_no_empty_reason(tmp_path) -> None:
    conn = store.init_db(tmp_path / "builds.db")
    now = store.now_ms()
    for i, (team, other) in enumerate(
        (("Reds", "Cubs"), ("Mets", "Pirates"), ("Rays", "Angels"))
    ):
        seed_game(
            conn, game=f"ok-{i}", team=team, other=other, p=0.74,
            computed_ms=now - 30_000,
        )
    conn.commit()
    payload = build_ladder_payload_widening(
        conn, now_ms=now, max_odds_age_ms=MAX_AGE_MS
    )
    assert any(not c.get("not_built_reason") for c in payload["cards"])
    assert "all_windows_empty" not in payload


def test_the_screen_renders_the_stale_odds_sentence() -> None:
    src = (
        REPO / "frontend" / "src" / "components" / "ParlayCards.tsx"
    ).read_text(encoding="utf-8")
    assert "ladder.all_windows_empty" in src
    assert "The sportsbook odds are stale" in src
    assert "empty.stale_consensus > 0" in src
