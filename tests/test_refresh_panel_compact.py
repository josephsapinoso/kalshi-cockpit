"""#392: a sentence every sport shares renders once in RefreshOddsPanel."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PANEL = (ROOT / "frontend/src/components/RefreshOddsPanel.tsx").read_text(
    encoding="utf-8"
)
BUTTON = (ROOT / "frontend/src/components/RefreshOddsButton.tsx").read_text(
    encoding="utf-8"
)
SENTENCE = "Buys a fresh price. It does not make a row bettable"


def _flat(s: str) -> str:
    return " ".join(s.split())


def test_a_sentence_shared_by_every_sport_renders_once():
    # The panel says it exactly once, outside the per-sport map.
    flat = _flat(PANEL)
    assert flat.count(SENTENCE) == 1
    assert flat.index(SENTENCE) < flat.index("cut.sports.map(")


def test_every_button_the_panel_lists_is_captionless():
    # Both RefreshOddsButton uses inside the sport loop must opt out,
    # or the sentence renders again under each sport / fixture.
    assert PANEL.count("<RefreshOddsButton") == 2
    assert PANEL.count("showCaption={false}") == 2


def test_a_lone_button_keeps_its_caption():
    assert _flat(BUTTON).count(SENTENCE) == 1
    assert "showCaption = true" in BUTTON
