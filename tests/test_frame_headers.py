"""The cockpit refuses to be framed by anyone but itself.

Until 2026-08-31 the live instance sent neither `X-Frame-Options` nor a CSP
`frame-ancestors`, so any page on the internet could load the signed-in cockpit
in an invisible iframe, float a decoy over it, and collect a click the reader
could not see. Found incidentally: a same-origin iframe was being used to get a
true 390px viewport for a layout check, and it worked because nothing stopped
it.

**Server-side re-validation is not a defence against this one, and that is why
it matters here.** `POST /api/manual-orders` sends a real immediate-or-cancel
order to Kalshi (`MANUAL_ORDERS_ARE_DRY_RUNS = false` since 2026-08-26, ADR
0073); the bid and hedge paths sit beside it. A clickjacked click is a genuine
click from a genuine session, carrying a valid cookie and a fresh order token,
so every check the order path makes passes.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **That the deployed instance sends them.** These read the source. Confirm on
  live by reading the response headers after a deploy -- the session that added
  this did, and the read corrected a claim the source could not have:

      /login /slate /market/{ticker} /parlays  ->  both headers, 200
      /api/health, /api/slate (200)            ->  NEITHER header
      /api/slate (401 from the middleware)     ->  both headers

  **A successful `/api/*` response does not carry them.** That path is a
  rewrite to uvicorn, and Next serves the backend's own headers rather than the
  ones set on `NextResponse.next()`; the 401 carries them only because the
  middleware constructs that response itself. **The exposure is still closed**
  -- clickjacking needs a surface to click, and every HTML page has the header
  -- but the gap is real and would matter the day an `/api/*` route returns
  HTML. Not papered over in `next.config.ts`, because that would be a second
  place the policy is written and the two would drift.
- **That the app is protected against anything else.** This is not a content
  security policy. There is no `script-src` and no `style-src`, deliberately:
  those have a real chance of breaking a page, and shipping them inside a
  framing fix would make one deploy that cannot be reasoned about.
- **Anything about the Python backend.** `uvicorn` binds `127.0.0.1:8000`
  inside the container and is never published, so Next is the only public
  surface and the only place these belong.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIDDLEWARE = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "src"
    / "middleware.ts"
)


def _source() -> str:
    """The file with its COMMENTS STRIPPED.

    Every assertion here is about what the middleware sends, and the comments
    beside it discuss the alternatives by name -- `DENY`, `script-src`,
    `style-src`. Grepping the raw file made three of these tests fail on the
    prose that explains why those were rejected, which is the same defect as a
    test passing on prose: **a guard on the code must not be able to read the
    comment.**
    """
    raw = MIDDLEWARE.read_text(encoding="utf-8")
    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)   # block comments
    raw = re.sub(r"^\s*//.*$", "", raw, flags=re.M)    # line comments
    return raw


def _body() -> str:
    """The middleware function alone, comments already stripped."""
    source = _source()
    return source[source.index("export async function middleware("):]


class TestBothFramingHeadersAreSent:
    @pytest.mark.parametrize(
        "name,value",
        [
            ("Content-Security-Policy", "frame-ancestors 'self'"),
            ("X-Frame-Options", "SAMEORIGIN"),
        ],
    )
    def test_the_header_is_declared(self, name, value):
        """Both, deliberately: `frame-ancestors` supersedes `X-Frame-Options`
        and wins wherever both are understood, and the legacy one covers
        anything that does not implement CSP."""
        source = _source()
        assert name in source
        assert value in source

    def test_the_two_headers_agree(self):
        """They say the same thing, so they cannot disagree -- but only while
        nobody edits one of them.

        `SAMEORIGIN` is the `X-Frame-Options` spelling of `frame-ancestors
        'self'`. `DENY` beside `'self'` would be two different policies on one
        response, and which one applies would depend on the reader.
        """
        source = _source()
        if "frame-ancestors 'self'" in source:
            assert "DENY" not in source, (
                "X-Frame-Options: DENY contradicts frame-ancestors 'self'"
            )

    def test_self_rather_than_deny(self):
        """`'self'` blocks every attacker and costs nothing.

        An attacker cannot serve a page from this origin, so same-origin
        framing is not a way in. `DENY` would block only our own embedding --
        including the same-origin iframe that is the one known way to get a
        true phone viewport against an authed page (`tasks/NEXT.md`) -- and buy
        no security for it.
        """
        source = _source()
        assert "frame-ancestors 'self'" in source
        assert "frame-ancestors 'none'" not in source


class TestEveryExitCarriesThem:
    """Five return paths, and a header set on four of them is absent exactly
    where somebody later adds a sixth.

    The demo's ungated exit counts: it serves the public portfolio instance,
    which is the one an attacker can reach without a password at all.
    """

    def test_every_return_goes_through_the_funnel(self):
        """Mutation observed red: unwrap any single `withFrameHeaders(...)`.

        Counts `NextResponse` constructions against wrapped returns rather
        than asserting a number, so adding a sixth exit fails this until it is
        wrapped too.
        """
        body = _body()
        returns = re.findall(r"return\s+(\w+)", body)
        constructions = [r for r in returns if r == "NextResponse"]
        assert not constructions, (
            f"{len(constructions)} middleware exit(s) return a NextResponse "
            f"directly instead of through withFrameHeaders()"
        )

    def test_the_demo_exit_is_covered(self):
        """The ungated instance is the one reachable with no password."""
        body = _body()
        i = body.index("if (!secret)")
        assert "withFrameHeaders" in body[i:i + 120]

    def test_the_401_is_covered(self):
        """A JSON refusal is still a response a browser renders."""
        body = _body()
        i = body.index("Not authenticated")
        assert "withFrameHeaders" in body[max(0, i - 200):i]

    def test_the_funnel_sets_every_declared_header(self):
        """The list and the setter must not drift: a header added to
        `FRAME_HEADERS` that the funnel never iterates is a header nobody
        sends."""
        source = _source()
        i = source.index("function withFrameHeaders")
        j = source.index("}", source.index("{", i))
        assert "FRAME_HEADERS" in source[i:j]
        assert "headers.set" in source[i:j]


class TestItIsNotSecretlyAFullPolicy:
    """A framing fix that also ships a script policy is one deploy that cannot
    be reasoned about, and the page it breaks will be found by a user."""

    @pytest.mark.parametrize(
        "directive", ["script-src", "style-src", "default-src", "img-src"]
    )
    def test_no_other_csp_directive_rides_along(self, directive):
        assert directive not in _source(), (
            f"{directive} belongs to its own change, with its own verification"
        )
