"""Discovery consumes the `/events` paginator lazily, and sees the same events.

`run_kalshi_pass` used to collect the whole open catalogue before classifying
any of it:

    raw_events = [e async for e in kalshi_client.events(with_nested_markets=True)]

`events()` is a lazy paginator; the comprehension defeated it and held every
page at once -- 11,160 events carrying 96,326 nested markets, to keep the ~510
that are priceable. Replayed at that scale on 2026-08-29 the list alone was
1,036MB RSS against a 2GB no-swap box, falling to 24MB the moment it was
dropped, with `tracemalloc` showing nothing retained. A transient peak that
glibc does not hand back is still the peak that gets the process killed.

**The dangerous half of the fix is not the memory, it is the equivalence.**
Classifying an event as it arrives means the events reach the same code in the
same order and nothing else changes -- and "nothing else" has to be proved,
because a discovery pass *observes* the events it rejects: four rejection
counters, the unknown-scope and unknown-league maps, and the per-series
no-commence warning all read events that are then discarded. Every one of those
observations is an aggregate over a stream, which is why streaming is
equivalent; this file is the assertion rather than the argument.

The first two tests are the important ones. The third is why the change was
made and the fourth is what stops it being quietly reverted.

WHAT THIS DOES NOT ESTABLISH
----------------------------
That the classification is *correct* -- `tests/test_discovery.py` owns that,
and both drivers run the same body, so it could not tell them apart. Nor does
the peak measured here predict RSS: `tracemalloc` counts Python allocations,
and the gap between that and what the allocator returns to the OS is the whole
reason the live figure was 1,036MB rather than 539MB.
"""

from __future__ import annotations

import asyncio
import json
import logging
import tracemalloc
from pathlib import Path

import pytest

from backend.kalshi import discovery
from backend.kalshi.discovery import (
    discover_from_event_stream,
    discover_from_events,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "events_sports_nested.json"


def _captured_events() -> list[dict]:
    """The real 2026-08-06 capture: 32 events, 245 nested markets."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


async def _drain(events: list[dict], **kwargs):
    async def source():
        for event in events:
            yield event

    return await discover_from_event_stream(source(), **kwargs)


class TestTheStreamSeesExactlyWhatTheListSaw:
    """The important test. Same events, same markets, same order."""

    def test_the_two_drivers_return_identical_results(self) -> None:
        collected = discover_from_events(
            _captured_events(), always_log_summary=False
        )
        streamed = asyncio.run(
            _drain(_captured_events(), always_log_summary=False)
        )

        assert collected, "the capture must yield priceable events at all"
        # `DiscoveredEvent` and `DiscoveredMarket` are frozen dataclasses, so
        # this compares every field of every market, and the list compares
        # order. Anything the filter reordered or dropped shows up here.
        assert streamed == collected

    def test_the_rejection_counts_are_identical(self, caplog) -> None:
        """The `discovery:` line is the record's view of what was thrown away.

        It carries the four rejection counters and the unknown-scope and
        unknown-league totals -- all of them computed from events that are then
        discarded. If streaming changed any of them it would change this line,
        silently, on a number the log is the only copy of.
        """
        discovery.reset_scope_warnings()
        with caplog.at_level(logging.INFO, logger="backend.kalshi.discovery"):
            discover_from_events(_captured_events())
            from_list = [
                r.getMessage()
                for r in caplog.records
                if r.getMessage().startswith("discovery:")
            ]

        caplog.clear()
        discovery.reset_scope_warnings()
        with caplog.at_level(logging.INFO, logger="backend.kalshi.discovery"):
            asyncio.run(_drain(_captured_events()))
            from_stream = [
                r.getMessage()
                for r in caplog.records
                if r.getMessage().startswith("discovery:")
            ]

        assert from_list, "the summary line must be emitted at all"
        assert from_stream == from_list


class TestThePeakIsWhatChanged:
    #: Copies of the 245-market capture needed to reach the live catalogue's
    #: 96,326 nested markets. This is the scale the finding was measured at.
    LIVE_SCALE_COPIES = 393

    #: `KalshiRestClient.paginate` reads `/events` 200 rows at a time, so a
    #: page is the floor a streaming consumer can hold.
    PAGE = 200

    def _pages(self, raw: list[str]):
        """Serialised events, in pages, parsed only when the page is reached.

        Deliberately not a pre-built list of dicts: the cost being measured is
        holding parsed pages, so the replay must parse lazily the way `httpx`
        does or the setup would dominate what it is measuring.
        """
        page: list[str] = []
        for _ in range(self.LIVE_SCALE_COPIES):
            for blob in raw:
                page.append(blob)
                if len(page) == self.PAGE:
                    yield page
                    page = []
        if page:
            yield page

    def test_streaming_holds_a_page_where_collecting_held_the_walk(
        self,
    ) -> None:
        raw = [json.dumps(e) for e in _captured_events()]
        logging.disable(logging.CRITICAL)
        try:
            tracemalloc.start()
            collected: list[dict] = []
            for page in self._pages(raw):
                collected.extend(json.loads(blob) for blob in page)
            from_list = discover_from_events(
                collected, always_log_summary=False
            )
            _, list_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            del collected

            async def stream():
                async def source():
                    for page in self._pages(raw):
                        for event in [json.loads(blob) for blob in page]:
                            yield event

                return await discover_from_event_stream(
                    source(), always_log_summary=False
                )

            tracemalloc.start()
            from_stream = asyncio.run(stream())
            _, stream_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        finally:
            logging.disable(logging.NOTSET)

        # Equivalence again, at scale, because a memory test that quietly
        # dropped rows would pass its own threshold most convincingly.
        assert from_stream == from_list

        # Measured 2026-08-29: 538.8MB collected, 75.1MB streamed. The bar is
        # set at half rather than at the observed 7.2x so it reports a
        # regression rather than allocator noise -- reinstating the list
        # comprehension puts this back over 500MB.
        assert stream_peak < list_peak / 2, (
            f"streaming peaked at {stream_peak / 1e6:.1f}MB against "
            f"{list_peak / 1e6:.1f}MB collected -- the walk is being held"
        )


class TestTheRunnerDoesNotCollectTheWalk:
    """The regression guard: the memory test above is slow and coarse.

    This one is exact. It asks when classification happens relative to
    fetching, which is the property the fix actually turns on -- and it is
    where the change would be undone, because `[e async for e in ...]` looks
    entirely innocent.
    """

    async def test_classification_starts_before_the_walk_finishes(
        self, tmp_path, monkeypatch
    ) -> None:
        from backend.runner import PassCounts, run_kalshi_pass
        from backend.store import db

        raw = _captured_events()

        class LazyKalshi:
            """Counts how many events it has handed over."""

            def __init__(self) -> None:
                self.yielded = 0

            async def events(self, **_: object):
                for event in raw:
                    self.yielded += 1
                    yield event

        kalshi = LazyKalshi()

        # How many events had been fetched at the moment each one was
        # classified. Collecting first makes every entry equal to the total.
        fetched_at_classify: list[int] = []
        real = discovery.classify_series

        def watched(event: dict):
            fetched_at_classify.append(kalshi.yielded)
            return real(event)

        monkeypatch.setattr(discovery, "classify_series", watched)

        conn = db.init_db(tmp_path / "lazy_walk.db")
        try:
            await run_kalshi_pass(
                conn, kalshi, now=1_787_000_000_000, counts=PassCounts()
            )
        finally:
            conn.close()

        assert fetched_at_classify, "nothing was classified at all"
        assert fetched_at_classify[0] == 1, (
            "the first event was classified after "
            f"{fetched_at_classify[0]} of {kalshi.yielded} had been fetched -- "
            "the walk is being collected before it is classified"
        )
        assert kalshi.yielded == len(raw), "the walk was truncated"


class TestTheJunkPrefixDoesNotDrift:
    """`KXMVE` is spelled out in four places, and they must agree.

    This change was proposed as "filter the junk at the point of arrival, using
    the same prefix test discovery already applies" -- which would have made a
    fifth copy, and would also have removed nothing: `events()` drops `KXMVE`
    at the wire before the runner ever sees it, so the 11,160 events the walk
    yields are all real. The filter was not the fix. But the near miss is worth
    a guard, because the copies are currently identical and nothing says so.

    Unifying them means moving a constant across the import graph and is a
    separate change. This is the cheap half: if one moves, this goes red.
    """

    def test_every_copy_of_the_prefix_is_the_same_string(self) -> None:
        import ast

        from backend.kalshi import rest

        assert rest.JUNK_PREFIX == discovery.JUNK_PREFIX

        # The two scripts hold their own copies and import neither module, so
        # they are read rather than imported -- both talk to the live API, and
        # a drift test must not be the thing that calls Kalshi.
        for script in ("capture_fixtures.py", "measure_unknown_scopes.py"):
            source = (ROOT / "scripts" / script).read_text(encoding="utf-8")
            tree = ast.parse(source)
            found = [
                node.value.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Constant)
                and any(
                    isinstance(t, ast.Name) and t.id == "JUNK_PREFIX"
                    for t in node.targets
                )
            ]
            assert found == [discovery.JUNK_PREFIX], (
                f"scripts/{script} defines JUNK_PREFIX as {found}, not "
                f"{discovery.JUNK_PREFIX!r}"
            )
