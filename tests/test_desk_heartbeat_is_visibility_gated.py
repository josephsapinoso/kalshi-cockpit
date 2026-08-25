"""The heartbeat must not beat from a background tab.

`Nav.tsx` polls once a minute on every page, and as of 2026-08-25 that poll also
tells the backend someone has the desk open -- which is what the odds feed now
follows instead of a clock (ADR 0071 §2.6).

**`document.visibilityState === "visible"` is the single most load-bearing line
in that change**, and the arithmetic is why:

    fixed 12h window, 2 sports          576 credits/day   (what this replaces)
    attention, tab visible 24h          1,152/day
    attention, tab visible 24h, 4 sports  2,304/day       (tier is 20,000/month)

A backgrounded tab left open overnight is exactly the 1,152 case. Without the
guard the new design is *twice the price* of the one it replaces rather than a
fraction of it, and it would present as a slow drift in the credit line with
nothing naming it.

It is deliberately not the only control -- the backend's attention daily slice
is the hard ceiling and does not depend on any browser behaving. This is the
brace; that is the belt. But a control that can be defeated by a browser bug
must never be the only thing standing between a design and its worst case, and
equally a cheap client-side guard should not be left out because a server-side
one exists.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **Nothing about a real browser.** The assertions are over **source text** --
  this repo has no JS test runner (`frontend/package.json` has `dev`, `build`,
  `start`, `lint` and no test script). They prove the guard is written and that
  it precedes the call; they cannot prove a browser honours `visibilityState`,
  that the listener fires, or that a phone waking from sleep behaves. Only
  watching the credit line does that, which is why the slice exists.
- **Nothing about the cost.** Every "attended hours" figure above is a guess.
  `api_credits` summed per budget-day by trigger is the instrument.
- **Nothing about the backend.** `test_desk_follows_attention.py` owns what a
  stamp does once it lands.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAV = ROOT / "frontend" / "src" / "components" / "Nav.tsx"
API_TS = ROOT / "frontend" / "src" / "lib" / "api.ts"
ROUTE = ROOT / "frontend" / "src" / "app" / "desk-attention" / "route.ts"
MIDDLEWARE = ROOT / "frontend" / "src" / "middleware.ts"


def _beat() -> str:
    """Just the heartbeat effect's body, so a `visibilityState` mention
    somewhere else in the file cannot satisfy an assertion about this one."""
    source = NAV.read_text(encoding="utf-8")
    start = source.index("const beat = () => {")
    return source[start : source.index("}, []);", start)]


class TestTheGuardIsWrittenAndComesFirst:
    def test_the_beat_checks_visibility(self):
        """Mutation observed red: delete the `visibilityState` line — a
        backgrounded tab stamps once a minute forever."""
        assert 'document.visibilityState !== "visible"' in _beat()

    def test_the_check_precedes_the_call_rather_than_following_it(self):
        """Order is the whole guard here, unlike the `refused`/window pair in
        `sweepTone.ts` where swapping two lines changed nothing. A check after
        the call is not a check.

        Mutation observed red: move the `recordAttention()` line above the
        guard.
        """
        beat = _beat()
        assert beat.index("visibilityState") < beat.index("recordAttention")

    def test_it_returns_rather_than_merely_skipping_the_await(self):
        """`if (!visible) return;` and not `if (visible) { ... }` wrapped around
        more work — stated because the early return is what makes the guard
        readable at a glance in a file where every other effect does work
        unconditionally."""
        assert 'visibilityState !== "visible") return;' in _beat()


class TestReturningToTheTabIsImmediate:
    def test_a_visibilitychange_listener_rides_alongside_the_interval(self):
        """Coming back to the desk is when freshness matters most, and when a
        stale price is most likely to be read as a live one. Waiting up to a
        minute for the next interval tick would spend that whole minute showing
        prices nobody has refreshed.

        Mutation observed red: remove the `addEventListener` line.
        """
        beat = _beat()
        source = NAV.read_text(encoding="utf-8")
        assert 'addEventListener("visibilitychange", beat)' in source
        assert beat  # the effect exists to attach it to

    def test_the_listener_is_removed_on_unmount(self):
        """A listener that outlives its component keeps stamping from a page
        that is gone, which is the leak version of the bug the guard prevents."""
        source = NAV.read_text(encoding="utf-8")
        assert 'removeEventListener("visibilitychange", beat)' in source
        assert "clearInterval(timer)" in source


class TestTheFailureIsSwallowed:
    def test_the_beat_catches(self):
        """A missed heartbeat costs one delayed sweep and the next tick retries.
        Surfacing it would put an error in the chrome of every page for
        something the reader did not ask for and cannot act on."""
        assert ".catch(() => {})" in _beat()

    def test_the_client_reports_nothing_to_report(self):
        """`recordAttention` returns `Promise<void>`, unlike every other writer
        in `lib/api.ts`, which hand back `{recorded, detail}` so a component can
        say what did not happen. There is no component here."""
        api = API_TS.read_text(encoding="utf-8")
        start = api.index("export async function recordAttention(")
        signature = api[start : api.index("{", start)]
        assert "Promise<void>" in signature


class TestTheRouteIsGatedLikeEveryOtherMutation:
    def test_the_path_is_in_the_json_route_handlers_allowlist(self):
        """Without this, an expired session gets an HTML login page behind a
        200 — which `fetch` reads as success, so the heartbeat would silently
        succeed forever while stamping nothing."""
        assert '"/desk-attention"' in MIDDLEWARE.read_text(encoding="utf-8")

    def test_the_handler_holds_the_token_rather_than_the_browser(self):
        source = ROUTE.read_text(encoding="utf-8")
        assert "backendToken()" in source
        assert "relayToBackend(" in source

    def test_the_demo_refuses_rather_than_erroring(self):
        """The demo holds no credentials and buys no odds, so there is nothing
        for attention to drive."""
        assert "demoRefusal(" in ROUTE.read_text(encoding="utf-8")

    def test_no_client_timestamp_reaches_the_backend(self):
        """The stamp's time is the server's `now_ms`. A client-supplied one is
        a number the caller chooses, and the only value worth choosing is a
        future one — which would hold the desk open past its own TTL.

        Mutation observed red: forward a `seen_ms` from the request body.
        """
        source = ROUTE.read_text(encoding="utf-8")
        assert "body: {}" in source
        assert "seen_ms" not in source
        assert "readJsonBody" not in source
