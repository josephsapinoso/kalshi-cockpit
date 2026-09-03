"""A screen the server answers and nothing links to is not shipped.

This repo's named defect is code that is complete, tested, and invoked by
nothing. `tests/test_has_callers.py` catches that for Python modules. This file
catches the same shape one layer up, where it is easier to miss because the
route *works*: visit the URL and the page renders perfectly, so nothing looks
broken. What is missing is the only thing that matters — a way to arrive.

**It was real, and it was hidden by a comment that read like a decision.**
`Nav.tsx` spends six links deliberately, and its own text said twice that
`/builder` and `/rejections` were "still served for anyone who wants it". They
were: with no inbound link anywhere in the application. The trade-off was
recorded honestly and the escape hatch it promised was never built. On a tool
operated from a phone, "type the URL" is not a route a real person takes.

Both pages were later deleted, and `Nav.tsx` went on claiming they were served
until 2026-08-29 -- the same sentence outliving the wiring twice, first as a
promise with no link and then as a claim with no page.

So the rule is not "every screen is in the nav" — the nav is a budget (four
links and a search button since decision-map #18, 2026-09-02; six before, and
the six were measured already scrolling at 390px). The rule is that every
screen is reachable from *somewhere*, and that where it lives is a choice
someone made rather than a slot nobody noticed.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about whether a page is worth keeping.** The remedy for a screen
  nobody wants is a delete commit, and this test is happy to be satisfied by a
  footer link on a page that should have gone. Watch for that.
- **Nothing about whether the link works.** It reads the source for an `href`.
  A route that 500s on load passes here.
- **Nothing about the rest of the app's navigation.** Only that each served
  page is named in one of the two link lists.
- **Nothing about what the nav looks like.** The 390px claims below are
  source pins on class names and on the ticket's own measurement, not a
  rendered layout; `scripts/check_mobile.py` against a running frontend is
  the instrument for that.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP = REPO_ROOT / "frontend" / "src" / "app"
NAV = REPO_ROOT / "frontend" / "src" / "components" / "Nav.tsx"
FOOTER = REPO_ROOT / "frontend" / "src" / "components" / "Footer.tsx"

#: Reached by a mechanism no `href` can express, so requiring one would be
#: noise rather than a check.
#:
#: - `/` is the nav's own logo link and every screen's home.
#: - `/login` is arrived at by being redirected there, unauthenticated, by
#:   `frontend/src/middleware.ts`. A link to it from a signed-in page is a
#:   link to a form the reader has already filled in.
#: - `/slate` is a byte-identical re-export of `/` kept for bookmarks
#:   (2026-08-22 review, Joe approved dropping its footer slot). A link to
#:   the page you are already on is furniture, not a route.
#: - `/dashboards` is a developer screen: it reads dbt marts that exist only
#:   after `backend.store.publish` + `dbt build`, and on the deployed box its
#:   only state is its own 503 explainer. It lost its footer slot in the
#:   2026-08-22 review (Joe approved); the developer who just built the
#:   warehouse types the URL, which for that reader is a route.
EXEMPT = {"/", "/login", "/slate", "/dashboards"}


def served_routes() -> set[str]:
    """Every route with a `page.tsx`, as the path a browser would ask for."""
    routes = set()
    for page in APP.rglob("page.tsx"):
        rel = page.parent.relative_to(APP).as_posix()
        routes.add("/" if rel == "." else f"/{rel}")
    return routes


def linked_routes(source: Path) -> set[str]:
    return set(re.findall(r'href:\s*"([^"]+)"', source.read_text(encoding="utf-8")))


def dynamically_linked(route: str) -> bool:
    """A `[param]` route cannot appear in Nav or Footer by its literal name --
    it is reached per-row, through a template link like
    `` href={`/market/${...}`} ``. Reachable here means some source file under
    `src/` builds an href from the route's static prefix. Mutation observed
    red: remove the slate row's `/market/` Link -- the route lands back in
    `orphaned` by name.
    """
    prefix = route.split("[", 1)[0]
    needle = f"href={{`{prefix}"
    return any(
        needle in p.read_text(encoding="utf-8")
        for p in (REPO_ROOT / "frontend" / "src").rglob("*.tsx")
    )


class TestEveryScreenCanBeArrivedAt:
    def test_no_served_page_is_reachable_only_by_typing_its_url(self):
        """The whole point. Mutation observed red: delete either entry from
        `Footer.tsx`'s `SECONDARY` -- that route reappears here by name."""
        reachable = linked_routes(NAV) | linked_routes(FOOTER) | EXEMPT
        orphaned = sorted(
            route
            for route in served_routes() - reachable
            if not ("[" in route and dynamically_linked(route))
        )
        assert not orphaned, (
            f"{orphaned} render fine and nothing in the application links to "
            f"them, so the only way to arrive is to type the URL -- which on a "
            f"phone is not a route anyone takes. Add each to Nav.tsx (spending "
            f"a link from a four-link budget, so something else comes out) or to "
            f"Footer.tsx, or delete the page. Leaving it served and unlinked is "
            f"the one option that is not a decision."
        )

    def test_no_screen_is_linked_from_both_lists(self):
        """One screen, one link. A route in both lists is a slot spent twice,
        and the footer's job is the screens the nav could NOT afford.
        Mutation observed red: add `/gate` back to `LINKS`."""
        assert not linked_routes(NAV) & linked_routes(FOOTER)

    def test_the_nav_is_four_links_and_the_four_are_named(self):
        """`Nav.tsx` argued for two weeks that six was the count at which the
        Gate keeps a visible slot at 390px. It was a comment; the ticket
        (#18) measured the row at 390px and found scrollWidth 424 against a
        clientWidth of 318 -- Playbook already off-screen, Gate off at 320.
        Joe's answer (option A, 2026-09-02): Gate and Playbook to the footer,
        search to the header. Four is the count now, and the four are the
        screens a bet is looked at or read back from on the day.

        The history: six went five on 2026-08-21 (Log's slot retired with the
        stopped calibration study), back to six the same day (Scout), Your
        bets took Scout's slot 2026-08-22, Parlays took Evidence's 2026-08-24,
        Picks moved from `/board` to `/picks` 2026-09-02 (#8).

        Mutation observed red: add `/gate` back to `LINKS` (five, and the
        set differs); remove `/bets` (three).
        """
        assert linked_routes(NAV) == {"/", "/picks", "/parlays", "/bets"}

    def test_the_footer_holds_exactly_the_screens_the_nav_shed(self):
        """A footer is where a screen goes when it is worth keeping and not
        worth a nav slot. Until 2026-09-02 this test bounded the footer at
        the nav's own length ("never MORE than the nav"), so that the next
        screen the nav shed had to answer the delete-commit question rather
        than land here by default. #18 retires that bound on purpose: Joe
        moved two screens down and the nav to four, so the footer is six
        against four and the old assertion would fail on his decision.

        What replaces it keeps the property the bound was for. The list is
        pinned entry by entry, so a screen cannot land here without being
        written into this test as a decision, with its date and its reason:

        - `/estimate`  the stopped study's record (form retired, ADR 0065)
        - `/hedge`     ADR 0078; empty until a ticket is recorded
        - `/ledger`    demoted 2026-08-24 when Parlays took its slot
        - `/board`     demoted 2026-09-02 as "Refusals" (#8, #29)
        - `/gate`      demoted 2026-09-02 (#18) -- read, never acted on
        - `/playbook`  demoted 2026-09-02 (#18) -- reference

        Mutation observed red: delete the `/playbook` entry from `SECONDARY`
        (and the reachability test above goes red with it, which is the
        point of having both)."""
        assert linked_routes(FOOTER) == {
            "/estimate", "/hedge", "/ledger", "/board", "/gate", "/playbook",
        }


class TestTheGateIsDemotedNotRetired:
    """The cost #18 named and Joe accepted: the screen that says whether the
    engine may move money is a tap further away. Accepted on one ground -- it
    is read, not acted on -- and that ground holds only while the link still
    reads as the interlock. A footer entry that looked retired (renamed,
    softened, its number gone) is how a session that never read CLAUDE.md
    re-derives "the gate will open" as a step in a plan."""

    def _footer_entries(self) -> dict[str, tuple[str, str]]:
        text = FOOTER.read_text(encoding="utf-8")
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        text = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
        block = text[text.index("const SECONDARY = ["):]
        block = block[: block.index("];")]
        return {
            href: (label, blurb)
            for href, label, blurb in re.findall(
                r'href:\s*"([^"]+)",\s*label:\s*"([^"]+)",\s*blurb:\s*"([^"]*)"',
                block,
            )
        }

    def test_the_footer_link_is_still_called_gate(self):
        """Mutation observed red: relabel the entry "Engine"."""
        label, _ = self._footer_entries()["/gate"]
        assert label == "Gate"

    def test_the_footer_blurb_keeps_the_games_against_300(self):
        """Mutation observed red: drop "300" from the blurb."""
        _, blurb = self._footer_entries()["/gate"]
        assert "300" in blurb, blurb
        assert "not a control" in blurb, blurb

    def test_the_gate_screen_still_counts_games_against_300(self):
        """Nothing in #18 touches `/gate`'s page; this pins that nothing did.
        Mutation observed red: edit "300-game count" out of the page."""
        page = APP / "gate" / "page.tsx"
        assert "300-game count" in page.read_text(encoding="utf-8")


class TestTheSearchIsAHeaderAffordance:
    """The other half of #18: search is reached from the header, on every
    page, rather than being a collapsed line at the foot of the longest one.
    It is the SAME search (`MarketSearch`, the one the Games and market
    screens host), mounted from a new place -- not a second implementation
    that could return a different list."""

    def _nav_code(self) -> str:
        text = NAV.read_text(encoding="utf-8")
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)

    def test_the_header_mounts_the_existing_search(self):
        """Mutation observed red: delete the `<MarketSearch` mount."""
        code = self._nav_code()
        assert 'import MarketSearch from "./MarketSearch"' in code
        assert "<MarketSearch" in code

    def test_the_search_is_closed_until_tapped(self):
        """Nothing is mounted until the button is pressed: the search opens a
        hand-bet ticket, and #8's count of taps from Picks to real money is
        about what a screen puts in front of him unasked. Mutation observed
        red: `useState(true)`, or drop the `searchOpen &&` guard."""
        code = self._nav_code()
        assert "useState(false)" in code.split("searchOpen", 1)[1].split(";", 1)[0]
        assert "{searchOpen && (" in code
        mount = code.index("<MarketSearch")
        assert code.rindex("{searchOpen && (", 0, mount) > code.rindex("</nav>", 0, mount)

    def test_the_search_closes_when_the_page_changes(self):
        """A layer that outlives the page it was opened on reads as part of
        the next one. Mutation observed red: remove the `[pathname]` effect."""
        code = self._nav_code()
        assert re.search(r"setSearchOpen\(false\);\s*\}, \[pathname\]\);", code), (
            "the search panel does not close on navigation"
        )

    def test_the_button_is_thumb_sized_at_390_and_outside_the_scrolling_row(self):
        """Every nav control must be hittable with a thumb at 390px. The
        button's box is the logo's 32px; its target is a pseudo-element grown
        to 44px, which only works OUTSIDE the `overflow-x-auto` row (inside,
        the overhang would become a vertical scrollbar). Mutation observed
        red: drop `before:-inset-1.5`, or move the button into the row."""
        code = self._nav_code()
        button = code[code.index('aria-label="Search markets"'):]
        button = button[: button.index("</button>")]
        assert "h-8 w-8" in button
        assert "before:absolute before:-inset-1.5" in button
        assert 'aria-expanded={searchOpen}' in button
        row = code.index("overflow-x-auto")
        assert code.index('aria-label="Search markets"') < row, (
            "the search button is inside the scrolling link row"
        )


class TestAMarketPageLightsGames:
    """`/market/[ticker]` lit nothing in the nav before 2026-09-02: the active
    test was `pathname === href`. A market page is a game's own screen, and
    Games is the screen that holds every game."""

    def test_the_active_predicate_covers_market_pages(self):
        """Mutation observed red: return `pathname === href` alone."""
        code = NAV.read_text(encoding="utf-8")
        body = code[code.index("function lights("):]
        body = body[: body.index("\n}")]
        assert 'pathname.startsWith("/market/")' in body
        assert 'href === "/"' in body

    def test_the_links_carry_aria_current(self):
        code = NAV.read_text(encoding="utf-8")
        assert 'aria-current={lights(link.href, pathname) ? "page" : undefined}' in code
