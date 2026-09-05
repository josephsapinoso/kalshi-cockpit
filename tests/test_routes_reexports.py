"""The names `backend/api/routes.py` re-exports after the split resolve to the
objects the moved code actually uses -- not to copies.

`docs/decisions/2026-09-04-routes-split-map.md` moved handlers out of
`routes.py` into `backend/api/routers/` and `backend/api/serialise.py`, and
left import shims behind for the names tests reach through the old namespace
(`_signal_cache`, `_signal_payload`, `_serialise`, `_decode_books_used`). A
shim that is spelled right but bound to a *fresh* object passes every existing
test: `tests/test_clv_signal.py` calls `_signal_cache.clear()` through
`backend.api.routes` and then seeds identical data on every path, so a copy of
the dict there would leave the test clearing nothing while the route served a
stale report, and nothing would go red. Observed 2026-09-05, by making
exactly that mutation and watching 47 of 47 pass. This is the pin that does
go red under it.

What it does NOT establish: that the moved handlers behave as before (the
route suites do), or that a monkeypatch on `backend.api.routes.KalshiRestClient`
reaches the moved parlay handlers (`tests/test_parlay_lookup.py` and
`tests/test_combo_bid_routes.py` do, and were verified by breaking the seam).
"""

from __future__ import annotations

from backend.api import routes, serialise
from backend.api.routers import status


class TestTheRoutesNamespaceStillResolvesWhatTestsPin:
    def test_the_signal_cache_is_the_routers_own_dict_not_a_copy(self) -> None:
        """`_signal_cache.clear()` through `routes` must empty what the route reads."""
        assert routes._signal_cache is status._signal_cache

    def test_the_signal_payload_is_the_routers_own_function(self) -> None:
        assert routes._signal_payload is status._signal_payload

    def test_the_serialiser_and_its_decoder_are_the_moved_functions(self) -> None:
        assert routes._serialise is serialise._serialise
        assert routes._decode_books_used is serialise._decode_books_used
