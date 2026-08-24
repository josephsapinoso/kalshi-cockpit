"""The pass control: the frontend caller `POST /api/desk/pass` never had.

ADR 0066. The endpoint was complete and tested with no caller; these tests
pin the caller's load-bearing properties as **source text**, in the
`test_board_screen.py` idiom, because this repo has no JS test runner:

- the control lives on the market screen and asks no confirm question (the
  no-confirm rule is documented at TonightStrip/NotTonight: "a dialog gives
  the impulse a veto", and a pass is the safe direction);
- it never paints itself in the money colour (`bg-accent` is red, and red
  is money -- ADR 0061 SS3);
- the `/pass` Next route handler is named in middleware's
  `JSON_ROUTE_HANDLERS`, so an expired session gets JSON 401 rather than an
  HTML login page behind a 200 that a `fetch` reads as success.

WHAT THIS DOES NOT ESTABLISH
----------------------------
These are string searches over source, not renders: they cannot prove a
class reaches the DOM, that the pill is tappable at 390px, or that the
route handler actually forwards -- only opening the page does that. The
scout-desk route handler this one copies has no test coverage of its own,
so there was no behavioural harness to mirror; the backend behaviour these
calls land on is owned by tests/test_desk_passes.py.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
PASS_CONTROL = FRONTEND / "components" / "PassControl.tsx"
PASS_ROUTE = FRONTEND / "app" / "pass" / "route.ts"
MIDDLEWARE = FRONTEND / "middleware.ts"
MARKET_PAGE = FRONTEND / "app" / "market" / "[ticker]" / "page.tsx"
API_TS = FRONTEND / "lib" / "api.ts"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def code(path: Path) -> str:
    """The file with its comments removed.

    The assertions about what a component *does* must not be satisfied or
    broken by a docstring naming the thing it deliberately avoids -- this
    repo's components carry long comments naming exactly those.
    """
    text = re.sub(r"/\*.*?\*/", "", source(path), flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


def block(text: str, opener: str, closer: str) -> str:
    """The text between `opener` and the next `closer`. Raises if absent."""
    assert opener in text, f"{opener!r} is not in the file this test reads"
    rest = text.split(opener, 1)[1]
    assert closer in rest, f"{opener!r} is not closed by {closer!r}"
    return rest.split(closer, 1)[0]


class TestThePassControlIsWiredAndCalm:
    def test_the_files_this_module_reads_are_the_ones_it_thinks_they_are(
        self,
    ):
        """A capture-style anchor against vacuous string searches.

        If the component is renamed or the handler moves, this says so
        instead of letting every assertion below pass over its absence.
        """
        assert "export default function PassControl(" in source(PASS_CONTROL)
        assert "recordPass" in source(PASS_CONTROL)
        assert "export async function recordPass(" in source(API_TS)
        assert "/api/desk/pass" in source(PASS_ROUTE)

    def test_the_market_screen_renders_it(self):
        """The endpoint had no caller; the market page is the caller now
        (ADR 0066 SS2 -- and SS3 rejects the slate row, so no other screen
        should grow one without reopening that ADR)."""
        page = code(MARKET_PAGE)
        assert "<PassControl" in page

    def test_it_asks_no_confirm_question(self):
        """No-confirm is load-bearing, not an omission: a dialog gives the
        impulse a veto, and a pass is the direction that needs one least."""
        assert "confirm(" not in code(PASS_CONTROL)

    def test_it_never_wears_the_money_colour(self):
        """`bg-accent` is red and red is money (ADR 0061 SS3). The pass is
        the calm alternative and must stay visually secondary to it."""
        assert "bg-accent" not in code(PASS_CONTROL)

    def test_the_route_handler_is_named_as_a_json_route(self):
        """Without this line an expired session gets the login page as HTML
        behind a 200, which `recordPass` would surface as a JSON parse
        failure rather than 'sign in again'."""
        handlers = block(
            code(MIDDLEWARE), "const JSON_ROUTE_HANDLERS", "]);"
        )
        assert '"/pass"' in handlers

    def test_the_handler_holds_the_token_and_the_browser_does_not(self):
        """The `/scout-desk` pattern: session cookie in, bearer token out.
        The component must reach the backend only through `/pass`.

        **Assertion updated 2026-08-24** (code review, the token-proxy
        duplication finding). This read `"APP_AUTH_TOKEN" in route` and
        `"Bearer" in route`; both moved into `lib/proxy.ts` when the seven
        hand-copied handlers were put on shared mechanics. The claim is
        unchanged and still enforced — the handler obtains the token
        server-side and the browser never sees it — so the assertion follows
        the indirection rather than being dropped. `test_token_proxy_routes.py`
        pins that `backendToken()`/`relayToBackend` are the only way to get
        one, for every handler in the family.
        """
        route = code(PASS_ROUTE)
        assert "backendToken()" in route
        assert "relayToBackend(" in route
        # The token is obtained server-side and never inlined into the client.
        assert "APP_AUTH_TOKEN" not in code(PASS_CONTROL)
        # The client never names the backend route; the handler owns it.
        assert "/api/desk/pass" in route
        assert "/api/desk/pass" not in code(PASS_CONTROL)
