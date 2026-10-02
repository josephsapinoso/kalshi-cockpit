"""#296: /game section headings are per league and never a raw series code.

Series codes come from captured payloads (`events_nhl_same_game.json`,
`combo_collections.json`), not from memory.
"""
import re
from pathlib import Path

from backend.game_builder import (
    LEAGUE_SERIES_LABELS,
    UNKNOWN_SERIES_LABEL,
    series_label,
)

FIX = Path(__file__).parent / "fixtures"


def _captured(prefix: str, fixture: str) -> set[str]:
    text = (FIX / fixture).read_text(encoding="utf-8")
    return set(re.findall(rf"{prefix}([A-Z0-9]+)-\d\d[A-Z]{{3}}\d\d", text))


def test_nhl_totals_are_goals_and_no_heading_is_a_raw_code():
    assert "goals" in series_label("KXNHL", "TOTAL").lower()
    assert "points" not in series_label("KXNHL", "TOTAL").lower()
    assert "goals" in series_label("KXNHL", "SPREAD").lower()
    # Basketball totals stay points.
    assert series_label("KXNBA", "TOTAL") == "Total points"

    captured = (
        {("KXNHL", k) for k in _captured("KXNHL", "events_nhl_same_game.json")}
        | {("KXNBA", k) for k in _captured("KXNBA", "combo_collections.json")}
        | {("KXNFL", k) for k in _captured("KXNFL", "combo_collections.json")}
    )
    assert ("KXNHL", "TOTAL") in captured and ("KXNBA", "PTS") in captured
    for prefix, kind in sorted(captured):
        label = series_label(prefix, kind)
        assert label != kind, (prefix, kind)
        assert not re.fullmatch(r"[A-Z0-9]+", label), (prefix, kind, label)

    # Unknown series get plain words for every league, not the code.
    for prefix in ("KXNHL", "KXNBA", "KXNFL"):
        assert series_label(prefix, "ZZQFOO") == UNKNOWN_SERIES_LABEL
        assert "ZZQFOO" not in series_label(prefix, "ZZQFOO")


def test_league_labels_only_name_captured_series():
    for prefix, labels in LEAGUE_SERIES_LABELS.items():
        fixture = (
            "events_nhl_same_game.json" if prefix == "KXNHL"
            else "combo_collections.json"
        )
        seen = _captured(prefix, fixture)
        assert set(labels) <= seen, (prefix, set(labels) - seen)


def test_the_captured_nfl_touchdown_series_are_named():
    """#296 follow-up: KXNFLANYTD / KXNFL2TD are the captured codes; the old
    generic key `TD` matched nothing, so they read as "Other markets"."""
    from backend.game_builder import UNKNOWN_SERIES_LABEL, series_label

    assert series_label("KXNFL", "ANYTD") == "Anytime touchdown"
    assert series_label("KXNFL", "2TD") != UNKNOWN_SERIES_LABEL
