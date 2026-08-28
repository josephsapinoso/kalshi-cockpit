"""The palette is legible and its colours mean one thing each, in numbers.

`--accent-2` is the colour that carries every "do not trust this" message in
the app — DRY RUN, EXPIRED, the refused edge tone, "Demo instance", "Not a
live slate". At `#b3995d` on a white card it measured 2.75:1, below both the
4.5:1 WCAG AA floor for text and the 3:1 floor for UI, so the screen's
warnings were its faintest ink while the prices beside them were fully
legible. These tests pin the ratio itself, per theme block, so a future
palette tweak that regresses it fails by arithmetic rather than by review.

**Assertions added 2026-08-28, because this file was green while a real-money
button failed AA on live.** White on `--accent` in dark mode was **3.76:1** —
the hand-bet confirm, the four ticket buttons, the nav tile, the login button.
The file did not catch it because it only ever checked a token **as ink on a
ground**, never **as a fill under white**. Those are different pairs, and the
second is the one every filled control actually renders. So:

- `TestAFillIsCheckedAsAFill` puts white on every token used as a
  full-strength background, and the paired ink on every soft ground.
- `TestOneColourMeansOneThing` pins `--accent != --negative`. They were
  byte-identical for the whole life of the project, which is what let
  identity, commit-money and loss share one hue and made the single loudest
  element on the Games screen the one row Joe must not bet. Ticket #10,
  ADR 0081.

**What this does not establish.** Contrast is computed from the tokens in
`globals.css`, not from rendered pixels: it cannot see opacity suffixes
applied at the call site (`/70`), text over images, or whether a component
uses a token at all. The fill check knows which tokens are fills because this
file *names* them — it does not read the components — so a filled control
built tomorrow on some other token is not covered until it is added here.
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


def _blocks(css: str) -> dict[str, dict[str, str]]:
    """All three theme blocks, named for the assertion message."""
    return {
        "light": theme_block(css, ":root {"),
        "dark (system)": theme_block(css, ':root:not([data-theme="light"]) {'),
        "dark (forced)": theme_block(css, ':root[data-theme="dark"] {'),
    }


def _rgb(hex_colour: str) -> tuple[float, float, float]:
    return tuple(float(int(hex_colour[i : i + 2], 16)) for i in (1, 3, 5))


def _deuteranope(hex_colour: str) -> tuple[float, float, float]:
    """Brettel-style approximation: the green cone's response is inferred
    from the other two rather than measured."""
    r, g, b = _rgb(hex_colour)
    return (
        0.625 * r + 0.375 * g,
        0.700 * r + 0.300 * g,
        0.300 * g + 0.700 * b,
    )


def _protanope(hex_colour: str) -> tuple[float, float, float]:
    r, g, b = _rgb(hex_colour)
    return (
        0.567 * r + 0.433 * g,
        0.558 * r + 0.442 * g,
        0.242 * g + 0.758 * b,
    )


def _distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


# Every token used as a FULL-STRENGTH background under white text. Named here
# rather than scraped from the components, because a scrape would silently
# cover nothing the day a class name changed shape.
WHITE_FILLS = ("--accent-fill",)

# Soft grounds and the ink that renders on them. A tint is only useful if the
# text on it is readable, and each of these pairs is a real call site.
SOFT_PAIRS = (
    ("--accent", "--accent-soft"),
    ("--accent-2", "--accent-2-soft"),
    ("--negative", "--negative-soft"),
)

WHITE = "#ffffff"


class TestTheWarningInkIsLegible:
    def test_accent_2_clears_aa_on_card_and_background_in_every_theme(self):
        css = GLOBALS.read_text(encoding="utf-8")
        for name, tokens in _blocks(css).items():
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


class TestAFillIsCheckedAsAFill:
    """The check that was missing while a real-money button shipped at 3.76:1.

    Ink-on-ground and white-on-fill are different pairs. `--accent` cleared
    every ink check in this file and failed as a fill, because in dark mode
    the legible ink shade is a light one and white does not sit on it. Two
    tokens is the fix; this is what stops them collapsing back into one.
    """

    def test_white_clears_aa_on_every_filled_token_in_every_theme(self):
        css = GLOBALS.read_text(encoding="utf-8")
        for name, tokens in _blocks(css).items():
            for token in WHITE_FILLS:
                assert token in tokens, f"{token} is missing from the {name} theme"
                ratio = contrast(WHITE, tokens[token])
                assert ratio >= 4.5, (
                    f"white on {token} in the {name} theme is {ratio:.2f}:1, "
                    f"below the 4.5:1 text floor — this is the exact shape of "
                    f"the defect that shipped the hand-bet confirm button at "
                    f"3.76:1 and was caught by no ink check."
                )

    def test_every_soft_ground_carries_its_own_ink(self):
        css = GLOBALS.read_text(encoding="utf-8")
        for name, tokens in _blocks(css).items():
            for ink, ground in SOFT_PAIRS:
                ratio = contrast(tokens[ink], tokens[ground])
                assert ratio >= 4.5, (
                    f"{ink} on {ground} in the {name} theme is {ratio:.2f}:1"
                )


class TestOneColourMeansOneThing:
    """`--accent` and `--negative` were byte-identical for the whole life of
    the project. That made identity, commit-money and loss one hue, so the
    single loudest element on the Games screen was the refused row — the one
    row Joe must not bet. Ticket #10 / ADR 0081 separated them; these refuse
    the merge back.
    """

    def test_the_brand_colour_is_not_the_loss_colour(self):
        css = GLOBALS.read_text(encoding="utf-8")
        for name, tokens in _blocks(css).items():
            assert tokens["--accent"] != tokens["--negative"], (
                f"--accent and --negative are both {tokens['--accent']} in the "
                f"{name} theme — every emphasis on the screen reads as 'this "
                f"is bad' again."
            )
            assert tokens["--accent-fill"] != tokens["--negative"]

    def test_they_stay_apart_to_a_colourblind_eye(self):
        """Colour is a channel roughly one man in twelve does not have in
        full. Separating the two tokens by hex is not enough if they collapse
        under simulation — which is the arithmetic that chose indigo over
        petrol and teal, and it has to hold against red too.

        **What this does not establish:** the simulation is a linear
        approximation, not a measurement of any real reader, and the 60 floor
        is a threshold this project chose rather than a published one. It
        catches a collapse; it does not certify a separation.
        """
        css = GLOBALS.read_text(encoding="utf-8")
        for name, tokens in _blocks(css).items():
            for sim in (_deuteranope, _protanope):
                gap = _distance(
                    sim(tokens["--accent"]), sim(tokens["--negative"])
                )
                assert gap >= 60, (
                    f"--accent and --negative are only {gap:.0f} apart under "
                    f"{sim.__name__} in the {name} theme"
                )


class TestEveryTokenIsReachableAsAClass:
    """A token defined and not registered is a class Tailwind silently drops.

    Tailwind v4 reads `@theme inline` to decide which utilities exist. A
    `--foo` in `:root` with no `--color-foo` beside it means `bg-foo` matches
    no rule: no error, no build failure, the element just renders with no
    colour. ADR 0081 added five tokens and four new classes, so this was one
    forgotten line away.

    **What this does not establish:** that any component uses the class, or
    that the built CSS contains it. It checks the registration, which is the
    step that fails silently — a class name misspelled at the call site still
    renders nothing and is not caught here.
    """

    def test_every_root_colour_token_has_a_theme_registration(self):
        css = GLOBALS.read_text(encoding="utf-8")
        registered = set(
            re.findall(r"--color-([\w-]+):\s*var\(--([\w-]+)\)", css)
        )
        mapped = {src for _, src in registered}
        for token in theme_block(css, ":root {"):
            name = token[2:]
            assert name in mapped, (
                f"{token} is defined in :root but never registered in "
                f"`@theme inline`, so `bg-{name}` / `text-{name}` match no "
                f"rule and render nothing — silently."
            )

    def test_no_registration_points_at_a_token_that_does_not_exist(self):
        css = GLOBALS.read_text(encoding="utf-8")
        tokens = set(theme_block(css, ":root {"))
        for alias, src in re.findall(
            r"--color-([\w-]+):\s*var\(--([\w-]+)\)", css
        ):
            if src.startswith("font-"):
                continue
            assert f"--{src}" in tokens, (
                f"--color-{alias} points at --{src}, which no theme block "
                f"defines"
            )


class TestTheNeutralCountIsNotPaintedAsAVerdict:
    def test_no_stat_on_the_board_takes_the_loss_colour(self):
        """A count is a fact, not a verdict.

        This test used to forbid `--accent` on a Stat, and its premise was
        that `--accent` *was* `--negative` — so "Bettable now", nightly value
        0, rendered as a loss. Ticket #10 made that premise false: `--accent`
        is indigo now and a Stat may lawfully wear it. What survives is the
        rule the two `Stat` comments were really about, and it is the stronger
        one: **no count is painted in the loss colour**, whatever the loss
        colour happens to be this month.
        """
        # The Board moved to /board on 2026-08-20; "/" is a re-export of the
        # Slate and defines no Stat. The claim follows the screens that do.
        for page_path in (
            GLOBALS.parent / "board" / "page.tsx",
            GLOBALS.parent / "slate" / "page.tsx",
        ):
            page = page_path.read_text(encoding="utf-8")
            for tag in re.findall(r"<Stat\b[^/>]*/>", page):
                assert "negative" not in tag, (
                    f"{page_path.name}: a Stat is painted as a loss: {tag}"
                )
            stat_body = page.split("function Stat(", 1)[1].split("\n}", 1)[0]
            assert "text-negative" not in stat_body
