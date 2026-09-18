"""The cockpit's login renews itself as it is used — issue #65, answer (A).

Source-reading tests, in the style of `test_ask_the_market_screen.py`: there
is no React or Edge-runtime test runner in this repo, so these pin what the
gate is written to do. The thing being protected is not a screen this time but
the shape of the session itself, where every failure mode is silent — a cookie
that stops renewing just logs Joe out one day, a month later, with nothing to
read.

What these do not establish
---------------------------
- **Nothing at runtime.** They do not execute `middleware.ts`, so they cannot
  prove a cookie is actually re-issued by a real request. They pin that the
  renewal is called, is conditional, shares its attributes with the login, and
  cannot take a request down with it.
- **Nothing about the arithmetic in `renewalDue`.** The 29-to-30-day window it
  produces is documented on the constant and is not executed here.
- **Nothing about iOS.** That the installed app keeps its own cookie jar —
  which is why this matters at all — was observed on 2026-09-17, not tested.
"""
from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).parent.parent / "frontend" / "src"
SESSION = FRONTEND / "lib" / "session.ts"
MIDDLEWARE = FRONTEND / "middleware.ts"
ROUTE = FRONTEND / "app" / "session" / "route.ts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestTheExpiryMoves:
    """Before this, the clock started at sign-in and did not move, however
    often Joe opened the app. The installed home-screen app has its own cookie
    jar and therefore its own clock, so it would have dropped him at the login
    page about a month after installing regardless of use."""

    def test_the_gate_renews_a_verified_session(self):
        source = _read(MIDDLEWARE)
        assert "renewalDue" in source
        assert "issueSession" in source, "the gate must be able to mint one"

    def test_the_renewal_sits_on_the_verified_branch_only(self):
        """An unauthenticated request must not be handed a fresh cookie, and a
        public path must not renew one either — `PUBLIC_PATHS` returns before
        the check, which is what keeps `/api/health` out of this."""
        source = _read(MIDDLEWARE)
        verified = source.index("if (await verifySession(")
        assert source.index("renewalDue(") > verified
        public = source.index("if (PUBLIC_PATHS.has(pathname))")
        assert public < verified


class TestItIsNotRenewedOnEveryRequest:
    """A `Set-Cookie` on every response is an HMAC per request and a header on
    every page, image and API call — on a box whose page-cache behaviour was
    the subject of ADR 0167 the day before. Once a day buys the property Joe
    asked for at one extra signature per device."""

    def test_a_named_interval_gates_the_renewal(self):
        assert "SESSION_RENEW_AFTER_S" in _read(SESSION)

    def test_the_interval_is_shorter_than_the_session_and_longer_than_nothing(self):
        source = _read(SESSION)
        match = re.search(
            r"SESSION_RENEW_AFTER_S = ([\d\s*60*24]+);", source
        )
        assert match, "the interval must be a named constant"
        renew = eval(match.group(1))  # noqa: S307 -- our own source, digits and *
        max_age = eval(
            re.search(r"SESSION_MAX_AGE_S = ([\d\s*60*24]+);", source).group(1)
        )  # noqa: S307
        assert 0 < renew < max_age, (
            "an interval of zero renews on every request; one at or above the "
            "session length never renews at all"
        )


class TestAKeptSessionIsNotAWeakerSession:
    """The renewal writes a cookie beside the login's. Two literals would be
    two places for `httpOnly` to drift, and a renewal that quietly dropped it
    would downgrade a session's security just by keeping it alive."""

    def test_both_writers_take_their_attributes_from_one_helper(self):
        assert "sessionCookie(" in _read(MIDDLEWARE)
        assert "sessionCookie(" in _read(ROUTE)

    def test_the_helper_still_sets_the_attributes_that_matter(self):
        source = _read(SESSION)
        block = source[source.index("export function sessionCookie") :]
        block = block[: block.index("\n}")]
        assert "httpOnly: true" in block
        assert 'sameSite: "lax"' in block
        assert "secure," in block
        assert 'path: "/"' in block

    def test_the_login_no_longer_carries_its_own_copy(self):
        """If it did, the two could disagree and nothing would say so."""
        source = _read(ROUTE)
        assert "httpOnly: true" not in source


class TestKeepingHimSignedInCannotCostHimTheRequest:
    def test_a_failed_renewal_is_swallowed(self):
        """The cookie he already holds is still valid. The worst case of doing
        nothing is that he signs in again a day later than he would have; the
        worst case of raising is that a bookkeeping convenience takes down the
        page he asked for."""
        source = _read(MIDDLEWARE)
        block = source[source.index("if (renewalDue(") :]
        block = block[: block.index("return response;")]
        assert "try {" in block
        assert "} catch {" in block

    def test_an_unreadable_cookie_renews_nothing_rather_than_guessing(self):
        """`renewalDue` returns false on anything it cannot parse, which is the
        existing behaviour and cannot lock anybody out. Unreadable resolves to
        the harmless branch, never to a plausible one."""
        source = _read(SESSION)
        block = source[source.index("export function renewalDue") :]
        block = block[: block.index("\n}")]
        assert block.count("return false;") >= 3
