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

So the rule is not "every screen is in the nav" — the nav is a budget, and a
seventh link pushes the Gate off the row at 390px. The rule is that every
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
            f"a link from a six-link budget, so something else comes out) or to "
            f"Footer.tsx, or delete the page. Leaving it served and unlinked is "
            f"the one option that is not a decision."
        )

    def test_the_nav_budget_is_still_six(self):
        """`Nav.tsx` argues the count is load-bearing: a seventh link pushes the
        Gate -- the screen that says whether money can move -- off the row at
        390px. If that stops being true it should stop being true on purpose.

        It went five on purpose, 2026-08-21 (Log's slot retired with the
        stopped calibration study, Amendment 2), and back to six the same day
        on purpose: Scout took the open slot (betting-desk item 6, metered
        then promoted in one change), placed so Gate keeps a visible slot at
        390px and Playbook stays the link that scrolls. Your bets took
        Scout's slot 2026-08-22 (every-page review, Joe approved): the desk's
        index was absorbed into the game screens it is sent from, and a
        betting desk's own record outranks a diagnostic.

        Mutation observed red (as five): add a sixth entry to `LINKS`.
        The seventh is the one the budget refuses.
        """
        assert len(linked_routes(NAV)) == 6

    def test_the_footer_does_not_quietly_absorb_the_whole_app(self):
        """A footer is where a screen goes when it is worth keeping and not
        worth a nav slot. If it ever holds more than the nav does, the nav is no
        longer the answer to "what is this tool for" -- and a page nobody wants
        belongs in a delete commit, not in a list at the bottom.

        The bound moved from < to <= on 2026-08-21, when Log's retirement
        (study stopped) brought the footer to parity at 5-and-5. The rule
        this docstring states -- never MORE than the nav -- is the rule the
        assertion now enforces; parity is a deliberate, dated state, and the
        next screen the nav sheds must answer the delete-commit question
        rather than land here by default.

        `/board` was that next screen, 2026-09-02 (decision-map #8, ratified
        by Joe; #29 named it "Refusals"). It answered the question: the blurb
        could be written beside `/ledger`'s -- the same subject on the other
        clock, one window against the whole record -- so it is worth keeping
        and not worth the slot the ranked list took. Footer 4, nav 6; the
        bound is unchanged and the state is recorded here as a decision."""
        assert len(linked_routes(FOOTER)) <= len(linked_routes(NAV))
