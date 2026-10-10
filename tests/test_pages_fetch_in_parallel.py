"""Three pages cost their slowest fetch, not the sum -- #186, ADR 0188.

`slate`, `parlays` and `picks` `page.tsx` (`board` was deleted 2026-10-10, #342) each read one primary
resource and one or more secondary ones (a timetable, a signal strip, a
refresh panel). Before this ticket every secondary fetch was `await`ed one
after another, so a page's cost was the SUM of every call's latency; one
signal-cache miss alone runs 3.1-13.8s
(`docs/measurements/2026-09-17-the-signal-cache-miss-is-the-desks-worst-latency.md`)
and every page added its other calls on top of it.

The fix starts every fetch that does not need an earlier result before
awaiting any of them -- `const xPromise = fetchX().catch(() => null)` for a
secondary, invoked immediately and awaited later by variable name -- so the
literal text `await fetch<Name>(` appears in a page's function body only for
a fetch that is genuinely blocking: the primary read, or a `Promise.all` of
calls that have no dependency on each other (which this test also accepts,
since `Promise.all` runs them concurrently and the literal pattern this test
polices is `await fetch\\w+\\(`, not `await Promise.all\\(`).

WHAT THIS TEST DOES NOT ESTABLISH
----------------------------------
- Nothing about wall-clock latency. This is a source pin, like the repo's
  other frontend tests (no React test runner here) -- the concurrent start
  was exercised by hand against a local stack; that is not this file.
- Nothing about a page that gains a THIRD independent fetch staying correct
  by accident: it merely requires that whatever fetch calls exist, no two of
  them are both directly `await`ed in sequence without a comment naming why.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

PAGES = {
    "slate": REPO / "frontend" / "src" / "app" / "slate" / "page.tsx",
    "parlays": REPO / "frontend" / "src" / "app" / "parlays" / "page.tsx",
    "picks": REPO / "frontend" / "src" / "app" / "picks" / "page.tsx",
}

# A directly-awaited fetch call: `await fetchSomething(`. A secondary fetch
# started concurrently is invoked WITHOUT a leading `await` (it is assigned
# to a `...Promise` variable, or chained with `.catch(...)`, and awaited
# later by variable name -- so it never matches this pattern) and a
# `Promise.all([...])` wrapping several calls is one `await`, not several,
# so it also never matches this pattern per call.
BLOCKING_FETCH = re.compile(r"await\s+fetch\w+\(")


def _source(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert text, f"{path} is empty"
    return text


class TestNoPageAwaitsIndependentFetchesInSequence:
    def test_no_page_awaits_independent_fetches_in_sequence(self):
        """Each page's function body contains at most ONE literal
        `await fetch<Name>(` -- the primary read (or, on `board`, zero,
        because its two blocking reads run inside one `Promise.all`). Any
        second literal match means a secondary fetch is once again gated
        behind an earlier one's completion rather than started alongside it.

        Mutation observed red: restoring `parlays/page.tsx`'s pre-fix
        `const actionable = await fetchWindow().catch(() => null);` /
        `const refreshable = await fetchRefreshable().catch(() => null);`
        pair (two more literal matches) turns this red for that page."""
        for name, path in PAGES.items():
            source = _source(path)
            matches = BLOCKING_FETCH.findall(source)
            assert len(matches) <= 1, (
                f"{name}/page.tsx awaits {len(matches)} fetch calls "
                f"directly ({matches}) -- independent secondary fetches "
                "must be started before the primary is awaited, not "
                "chained after it."
            )

    def test_each_pages_secondary_fetches_are_started_before_the_primary_await(self):
        """A `...Promise` variable naming a secondary fetch must be
        DECLARED (i.e. the fetch call made) textually before the primary's
        blocking `await fetch<Name>(` line -- otherwise the "start together"
        property is cosmetic: the secondary would still not be in flight
        while the primary is pending.

        Mutation observed red: moving `const actionablePromise = ...` below
        `data = await fetchSlate(filter);` in `slate/page.tsx`."""
        for name, path in PAGES.items():
            source = _source(path)
            promise_starts = [
                m.start() for m in re.finditer(r"\w+Promise\s*=\s*fetch\w+\(", source)
            ]
            primary_awaits = [m.start() for m in BLOCKING_FETCH.finditer(source)]
            for primary_pos in primary_awaits:
                for promise_pos in promise_starts:
                    assert promise_pos < primary_pos, (
                        f"{name}/page.tsx: a secondary fetch's Promise is "
                        "declared after the primary's blocking await -- it "
                        "is not actually started concurrently."
                    )

    def test_each_secondary_fetch_still_carries_its_own_catch(self):
        """The ticket's first "keep exactly": a failed secondary read is
        drawn in words, never an error page. Every `...Promise = fetch...`
        assignment across the three pages must chain `.catch(() => null)`
        immediately, the same shape as before this ticket.

        Mutation observed red: dropping `.catch(() => null)` from
        `board/page.tsx`'s `signalPromise` line."""
        pattern = re.compile(r"\w+Promise\s*=\s*fetch\w+\([^)]*\)(\.catch\(\(\) => null\))?")
        for name, path in PAGES.items():
            source = _source(path)
            for m in pattern.finditer(source):
                assert m.group(1) is not None, (
                    f"{name}/page.tsx: {m.group(0)!r} has no "
                    "`.catch(() => null)` -- a failed secondary fetch would "
                    "throw into the page's primary catch instead of "
                    "degrading in words."
                )

    def test_slates_422_branch_still_comes_from_the_primary_fetch_throwing(self):
        """The ticket's second "keep exactly": the primary fetch's throw
        must still land in the page's `catch`, drawing the refusal bar
        (slate's 422 branch). Started-but-not-yet-awaited secondary
        promises must not be awaited BEFORE the primary, or a secondary
        rejection (already neutralised by its own `.catch`, but checked
        here structurally) could pre-empt the primary's error handling.

        Mutation observed red: reordering slate's body so
        `signal = await signalPromise;` runs before
        `data = await fetchSlate(filter);` inside the `try` block."""
        source = _source(PAGES["slate"])
        try_block = re.search(r"try\s*\{(.*?)\}\s*catch", source, re.DOTALL)
        assert try_block is not None, "slate/page.tsx has no try/catch around the primary fetch"
        body = try_block.group(1)
        primary_pos = body.index("data = await fetchSlate(filter)")
        for secondary in ("signal = await signalPromise", "actionable = await actionablePromise", "refreshable = await refreshablePromise"):
            secondary_pos = body.index(secondary)
            assert primary_pos < secondary_pos, (
                "slate/page.tsx: a secondary await runs before the primary "
                "fetch inside the try block -- the primary's throw must be "
                "the first thing that can send this page to its catch."
            )
