"""What Joe still holds lives at the top of /bets, and /hedge points there (#240).

Joe's answer to #234 (A), 2026-09-30: an "Open (N)" section at the top of
`/bets` renders what `/hedge` rendered, the *Your bets* tab carries a count of
open positions, `/hedge` redirects to `/bets#open`, and the footer stops
saying "Hedging".

WHAT THIS ESTABLISHES
----------------------
(i)   `/bets` renders `<HedgePositions` off `fetchHedge`, inside
      `id="open"`, and that section's source precedes the settled list
      (`SECTIONS.map`) and the net strip.
(ii)  The heading's N is computed from the positions array with the same
      liveness predicate `HedgePositions` partitions on, and an unreadable
      fetch renders no number (never 0).
(iii) `/hedge` is a redirect to `/bets#open` and renders no screen itself.
(iv)  `Nav.tsx` carries the badge on the `/bets` link only, computed from
      `fetchHedge` with that same predicate, hides at zero/unknown, and still
      has exactly four links.
(v)   No footer entry is labelled or pointed at "Hedging"/`/hedge`; the
      "Open now: N positions" line in `OpenPositions.tsx` links to
      `/bets#open`.

WHAT THIS DOES NOT ESTABLISH
-----------------------------
- Rendering: source text only, no DOM, no browser. Whether the badge fits at
  320px or the hash scrolls to the section was not measured here.
- That the live count matches the count the venue reports; the two are
  different quantities (`OpenPositions` is the venue's positions, N is the
  desk's tickets with a pending leg).

MUTATIONS, each observed red
----------------------------
  1. move the open section below the `SECTIONS.map` list -> (i) order test.
  2. drop the `<HedgePositions` mount from /bets -> (i) reuse test.
  3. change the heading to print `openCount ?? 0` -> (ii).
  4. make /hedge render a page again (no redirect) -> (iii).
  5. drop the `venue_settlement === null` term from Nav's count -> (iv).
  6. add a fifth entry to `LINKS` -> (iv) four-links test.
  7. put the "Hedging" entry back in the footer -> (v).
  8. point "Open now" at something else -> (v).
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"
BETS = SRC / "app" / "bets" / "page.tsx"
HEDGE = SRC / "app" / "hedge" / "page.tsx"
NAV = SRC / "components" / "Nav.tsx"
FOOTER = SRC / "components" / "Footer.tsx"
OPEN_POSITIONS = SRC / "components" / "OpenPositions.tsx"

LIVE = re.compile(
    r"position\.pending_legs\s*>\s*0\s*&&\s*position\.venue_settlement\s*===\s*null"
)


def code(path: Path) -> str:
    """Source with comments stripped, whitespace collapsed."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"\{\s*\}", "", text)
    text = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", text)


class TestTheOpenSectionIsOnYourBets:
    def test_the_section_reuses_hedge_positions_off_the_hedge_fetch(self):
        src = code(BETS)
        assert 'import HedgePositions from "@/components/HedgePositions"' in src
        assert "fetchHedge()" in src
        assert re.search(r"<HedgePositions\s", src)
        section = src[src.index('<section id="open"'):]
        section = section[: section.index("</section>")]
        assert "<HedgePositions" in section

    def test_the_open_section_precedes_the_net_strip_and_the_settled_list(self):
        src = code(BETS)
        open_at = src.index('<section id="open"')
        assert open_at < src.index('className="hud rounded-2xl')
        assert open_at < src.index("SECTIONS.map(")

    def test_the_count_uses_the_live_predicate_and_never_prints_a_false_zero(self):
        src = code(BETS)
        assert LIVE.search(src), "N is not the live-position count"
        assert "hedge === null ? null" in src
        heading = src[src.index("<h2") :]
        heading = heading[: heading.index("</h2>")]
        assert "openCount === null" in heading
        assert "?? 0" not in heading and "|| 0" not in heading


class TestHedgeRedirects:
    def test_hedge_is_a_redirect_to_bets_open(self):
        src = code(HEDGE)
        assert 'import { redirect } from "next/navigation"' in src
        assert 'redirect("/bets#open")' in src

    def test_hedge_renders_no_screen_of_its_own(self):
        src = code(HEDGE)
        assert "HedgePositions" not in src
        assert "fetchHedge" not in src
        assert "<" not in re.sub(r"\S*import[^;]*;", "", src).replace("never", "")


class TestTheNavBadge:
    def test_the_nav_still_has_exactly_four_links(self):
        text = NAV.read_text(encoding="utf-8")
        links = text[text.index("const LINKS = [") :]
        links = links[: links.index("];")]
        assert len(re.findall(r'href:\s*"', links)) == 4

    def test_the_badge_counts_live_positions_from_the_hedge_read(self):
        src = code(NAV)
        assert "fetchHedge()" in src
        assert LIVE.search(src), "the badge is not the live-position count"

    def test_the_badge_rides_the_bets_link_only_and_hides_at_zero_or_unknown(self):
        src = code(NAV)
        assert (
            '{link.href === "/bets" && openCount !== null && openCount > 0 && ('
            in src
        )
        assert src.count("data-open-badge") == 1


class TestNoFooterLinkSaysHedging:
    def test_the_footer_has_no_hedging_entry(self):
        text = FOOTER.read_text(encoding="utf-8")
        block = text[text.index("const SECONDARY = [") :]
        block = block[: block.index("];")]
        block = re.sub(r"^\s*//.*$", "", block, flags=re.MULTILINE)
        assert "Hedging" not in block
        assert "/hedge" not in block

    def test_open_now_links_to_the_open_section(self):
        src = code(OPEN_POSITIONS)
        assert re.search(r'<a href="/bets#open"[^>]*> Open now: ', src)
