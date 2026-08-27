"""The token-holding Next route handlers, as a family.

**Why this file exists.** There are seven of these, and the seventh
(`/parlay-lookup`) was hand-copied from the sixth — flagged by the 2026-08-24
code review. Each holds `APP_AUTH_TOKEN` server-side because the browser
deliberately never carries it (`lib/session.ts` issues a cookie proving
knowledge of the token without carrying it). The copied mechanics — backend
origin, JSON body read, transport guard, upstream relay — now live in
`lib/proxy.ts`; each handler keeps its own refusal words, because those
differ per route and a reader needs them at the callsite.

The two properties worth pinning as a family, both of which a hand-copy can
silently get wrong:

1. **Every handler is in `middleware.ts`'s `JSON_ROUTE_HANDLERS`.** Omitted, an
   unauthenticated call gets an HTML login page behind a 200, which every
   `fetch` client in this repo reads as success. This is the failure the set
   exists to prevent and the one a copy-paste is most likely to skip.
2. **No handler re-derives the backend origin.** Seven copies of
   `process.env.API_ORIGIN ?? "http://127.0.0.1:8000"` is seven places for a
   deployment change to be missed in six of them.

**What this does not establish.** These are assertions over **source text** —
this repo has no JS test runner (`frontend/package.json` has `dev`, `build`,
`start`, `lint` and no test script). They do not execute a handler, so they
prove nothing about what a request actually returns, whether the middleware
runs in the deployed order, or that the refusal words are accurate. Only
exercising the deployed routes does that.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "app"
MIDDLEWARE = ROOT / "frontend" / "src" / "middleware.ts"
PROXY = ROOT / "frontend" / "src" / "lib" / "proxy.ts"

#: Every route handler that holds the bearer token. `/session` is excluded on
#: purpose: it ISSUES the cookie rather than spending it, so it is the one
#: handler that must be reachable unauthenticated.
TOKEN_HANDLERS = (
    "refresh-odds",
    "scout-desk",
    "log-estimate",
    "revise-estimate",
    "lockout",
    "pass",
    "parlay-lookup",
    "desk-attention",
    # ADR 0077 -- the held-parlay record. None of the three reaches a venue or
    # moves money; they are gated because every mutating route is.
    "hedge-position",
    "hedge-resolve",
    "hedge-close",
)


def _source(name: str) -> str:
    return (APP / name / "route.ts").read_text(encoding="utf-8")


def test_the_inventory_is_complete():
    """A new token-holding handler must join this list, or every assertion
    below silently stops covering it."""
    on_disk = {
        p.parent.name for p in APP.glob("*/route.ts")
    } - {"session"}
    assert on_disk == set(TOKEN_HANDLERS), (
        f"route handlers on disk {sorted(on_disk)} != the inventory "
        f"{sorted(TOKEN_HANDLERS)} -- add the new one to both this list and "
        f"middleware.ts's JSON_ROUTE_HANDLERS"
    )


class TestEveryHandlerIsGatedAsJson:
    @pytest.mark.parametrize("name", TOKEN_HANDLERS)
    def test_it_is_named_in_json_route_handlers(self, name):
        """Otherwise an unauthenticated call is redirected to an HTML login
        page behind a 200, which every `fetch` in this repo reads as
        success."""
        middleware = MIDDLEWARE.read_text(encoding="utf-8")
        block = middleware[middleware.index("JSON_ROUTE_HANDLERS = new Set([") :]
        block = block[: block.index("]);")]
        assert f'"/{name}"' in block


class TestTheMechanicsAreNotCopied:
    @pytest.mark.parametrize("name", TOKEN_HANDLERS)
    def test_the_backend_origin_is_not_re_derived(self, name):
        """One definition of where the backend is. Seven is six places for a
        deployment change to be missed."""
        assert "process.env.API_ORIGIN" not in _source(name), (
            f"/{name} re-derives the backend origin; import BACKEND from "
            f"lib/proxy.ts instead"
        )

    @pytest.mark.parametrize("name", TOKEN_HANDLERS)
    def test_the_token_is_read_through_the_shared_helper(self, name):
        assert "process.env.APP_AUTH_TOKEN" not in _source(name), (
            f"/{name} reads the token directly; use backendToken()"
        )

    def test_the_origin_is_defined_exactly_once(self):
        assert PROXY.read_text(encoding="utf-8").count(
            'process.env.API_ORIGIN'
        ) == 1


class TestEveryHandlerStillRefusesTheDemoInItsOwnWords:
    """The mechanics are shared; the words are not, and that is the point.

    A pass says "nothing was recorded", the scout desk says "nothing was sent
    and nothing was spent", a lookup says "nothing was created". Those are
    different promises about what did not happen, and collapsing them into one
    generic sentence would be a loss, not a simplification.
    """

    @pytest.mark.parametrize("name", TOKEN_HANDLERS)
    def test_it_refuses_a_credential_less_instance(self, name):
        source = _source(name)
        assert "if (!token)" in source
        assert "demo instance" in source or "demoRefusal" in source

    @pytest.mark.parametrize(
        "name,phrase",
        [
            ("pass", "Nothing was recorded"),
            ("scout-desk", "nothing was spent"),
            ("parlay-lookup", "Nothing was created"),
            ("lockout", "NOT locked out"),
            ("log-estimate", "NOT logged"),
            ("revise-estimate", "Nothing was revised"),
            ("refresh-odds", "No credits were spent"),
        ],
    )
    def test_a_transport_failure_says_what_did_not_happen(self, name, phrase):
        assert phrase in _source(name), (
            f"/{name} must say what did NOT happen when the backend is "
            f"unreachable -- that is the whole content of the message to "
            f"someone whose tap vanished"
        )


class TestRefreshOddsKeepsItsOwnRelay:
    """The deliberate exception, pinned so it is not "tidied" into the shared
    relay by a later pass.

    `lib/api.ts:refreshOdds` reads a typed `OddsRefreshResult`; answering its
    transport failure with the shared 502-and-`detail` would reach the screen
    as "no odds available", which is a different and much worse claim than
    "the request did not arrive".
    """

    def test_it_answers_a_transport_failure_with_the_typed_shape(self):
        source = _source("refresh-odds")
        assert "relayToBackend" not in source
        assert "estimated_credits: 0" in source
        assert "accepted: false" in source

    def test_the_reason_is_written_down_beside_it(self):
        assert re.search(
            r"does NOT use .lib/proxy\.ts", _source("refresh-odds")
        ), "the exception must carry its reason, or it reads as an oversight"
