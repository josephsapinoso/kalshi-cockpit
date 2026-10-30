"""#412: when the refresh panel sits on top (urgent), it is one line + one button.

Source-text pins (the panel is an async server component). They state what
this does not establish: that the slate page passes `compact` when
`refreshIsUrgent` -- that call site is another file.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PANEL = " ".join(
    (ROOT / "frontend/src/components/RefreshOddsPanel.tsx")
    .read_text(encoding="utf-8")
    .split()
)


def _main_return() -> str:
    return PANEL[PANEL.index("const detail = (") :]


def test_compact_prop_exists_and_defaults_off():
    assert "compact = false" in PANEL
    assert "compact?: boolean" in PANEL


def test_compact_puts_league_buttons_inside_a_disclosure_with_one_summary_button():
    tail = _main_return()
    assert "{compact ? (" in tail
    compact_branch = tail[tail.index("{compact ? (") :]
    assert compact_branch.index("<details") < compact_branch.index("<summary")
    assert compact_branch.index("<summary") < compact_branch.index("{detail}")
    assert compact_branch.index("{detail}") < compact_branch.index("</details>")
    # the per-league buttons live in `detail`, never beside the status line
    assert compact_branch.count("{detail}") == 1
    assert "Refresh prices" in compact_branch


def test_the_buttons_and_captions_are_only_reachable_through_detail():
    tail = _main_return()
    # Everything state-free (league buttons, shared sentence) is defined in
    # `detail`, before the return that wraps it.
    ret = tail.rindex("return (")
    assert "<RefreshOddsButton" not in tail[ret:]
    assert "cut.sports.map(" not in tail[ret:]


def test_general_note_is_not_under_a_league_heading():
    # Old shape: the credit note followed the last sport's <div> with no
    # heading of its own, so it read as WNBA's. It now has its own block.
    i = PANEL.index("{data.note}")
    before = PANEL[:i]
    last_div = before.rindex('<div className="mt-4 border-t pt-4">')
    last_h3 = before.rindex("<h3")
    assert last_div < last_h3
    assert 'All leagues</h3>' in PANEL[last_h3 : i]
    # and that heading is not the per-sport one
    assert "leagueLabel(sport.sport_key)" not in PANEL[last_h3:i]
