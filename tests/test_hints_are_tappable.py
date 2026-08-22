"""A caveat that only exists on hover does not exist on a phone.

The 2026-08-22 review (A6) found the slate's column caveats and all six
signal-strip explanations living in `title=` attributes — including `soft
fallback`, the most consequential caveat in the product (all three
actionable rows ever written were soft fallbacks). `components/Hint.tsx` is
the fix: tap/click opens the sentence on both platforms, `title=` survives
as the desktop hover shortcut.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- Nothing about the popover's behaviour (Term.tsx's machinery, shared shape).
- Nothing about the sentences being correct — a wrong hint passes here.
- Coverage of every `title=` in the app; only the sites the review named.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SLATE = REPO / "frontend" / "src" / "app" / "slate" / "page.tsx"
STRIP = REPO / "frontend" / "src" / "components" / "SignalStrip.tsx"
HINT = REPO / "frontend" / "src" / "components" / "Hint.tsx"


class TestTheReviewedCaveatsOpenOnTap:
    def test_soft_fallback_is_a_hint_and_not_a_bare_title(self):
        """The sharpest case. Mutation observed red: revert the Anchor
        component's soft-fallback branch to a span with title=."""
        source = SLATE.read_text(encoding="utf-8")
        block = source.split("function Anchor", 1)[1]
        fallback = block.split("soft fallback", 1)[0]
        assert "<Hint" in fallback, (
            "the soft-fallback caveat is no longer tap-visible; a phone "
            "reader cannot open a title= attribute"
        )

    def test_the_slate_columns_use_hint_not_title_spans(self):
        source = SLATE.read_text(encoding="utf-8")
        for fn in ("function Books", "function Drift", "function Capacity", "function Width"):
            block = source.split(fn, 1)[1].split("\nfunction ", 1)[0]
            assert "<Hint" in block, f"{fn} lost its tappable hint"

    def test_the_signal_strip_stats_open_on_tap(self):
        source = STRIP.read_text(encoding="utf-8")
        stat = source.split("function Stat", 1)[1]
        assert "<Hint hint={title}>" in stat

    def test_hint_keeps_hover_as_the_desktop_shortcut(self):
        """Both platforms: the tap target still carries title= so desktop
        hover works without the tap."""
        source = HINT.read_text(encoding="utf-8")
        assert re.search(r"title=\{hint\}", source), (
            "Hint dropped its title= passthrough; desktop hover no longer "
            "shows the sentence"
        )
