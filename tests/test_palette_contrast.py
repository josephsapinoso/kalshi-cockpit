"""The warning ink is legible, in numbers rather than by eye.

`--accent-2` is the colour that carries every "do not trust this" message in
the app — DRY RUN, EXPIRED, the refused edge tone, "Demo instance", "Not a
live slate". At `#b3995d` on a white card it measured 2.75:1, below both the
4.5:1 WCAG AA floor for text and the 3:1 floor for UI, so the screen's
warnings were its faintest ink while the prices beside them were fully
legible. These tests pin the ratio itself, per theme block, so a future
palette tweak that regresses it fails by arithmetic rather than by review.

**What this does not establish.** Contrast is computed from the tokens in
`globals.css`, not from rendered pixels: it cannot see opacity suffixes
applied at the call site (`/70`), text over images, or whether a component
uses a token at all. And it checks only the tokens named here — a new token
introduced tomorrow is not covered until it is added.
"""

from __future__ import annotations

import re
from pathlib import Path

GLOBALS = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "src"
    / "app"
    / "globals.css"
)


def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_colour: str) -> float:
    r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def theme_block(source: str, opener: str) -> dict[str, str]:
    """The `--token: #hex` pairs inside one `{ ... }` block."""
    assert opener in source, f"{opener!r} is not in globals.css"
    body = source.split(opener, 1)[1].split("}", 1)[0]
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", body))


class TestTheWarningInkIsLegible:
    def test_accent_2_clears_aa_on_card_and_background_in_every_theme(self):
        css = GLOBALS.read_text(encoding="utf-8")
        blocks = {
            "light": theme_block(css, ":root {"),
            "dark (system)": theme_block(css, ':root:not([data-theme="light"]) {'),
            "dark (forced)": theme_block(css, ':root[data-theme="dark"] {'),
        }
        for name, tokens in blocks.items():
            for ground in ("--card", "--background"):
                ratio = contrast(tokens["--accent-2"], tokens[ground])
                assert ratio >= 4.5, (
                    f"--accent-2 on {ground} in the {name} theme is "
                    f"{ratio:.2f}:1, below the 4.5:1 text floor — the warning "
                    f"ink is the faintest thing on the page again."
                )

    def test_the_two_dark_blocks_agree(self):
        """"Forced dark" and "system dark" are one palette written twice; a
        token edited in one block and not the other is a theme-toggle bug."""
        css = GLOBALS.read_text(encoding="utf-8")
        system = theme_block(css, ':root:not([data-theme="light"]) {')
        forced = theme_block(css, ':root[data-theme="dark"] {')
        assert system == forced


class TestTheNeutralCountIsNotPaintedAsAVerdict:
    def test_no_stat_on_the_board_takes_the_accent_colour(self):
        """`--accent` is byte-identical to `--negative` in every theme block,
        so a Stat rendered in it reads as a loss. "Bettable now" — nightly
        value 0 — was the one Stat so painted."""
        for page_path in (
            GLOBALS.parent / "page.tsx",
            GLOBALS.parent / "slate" / "page.tsx",
        ):
            page = page_path.read_text(encoding="utf-8")
            for tag in re.findall(r"<Stat\b[^/>]*/>", page):
                assert "accent" not in tag, (
                    f"{page_path.name}: a Stat passes accent again: {tag}"
                )
            stat_body = page.split("function Stat(", 1)[1]
            assert "text-accent" not in stat_body.split("\n}", 1)[0]
