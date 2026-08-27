"""`scripts/drive_hedge.py` must not rot silently between the runs that matter.

WHY THIS EXISTS
---------------
The driver is the only instrument that exercises the hedge payload against a
real Kalshi book, and it found a defect a 4,800-test suite did not. But it runs
by hand, occasionally, and needs credentials -- so a rename in `backend.hedge`
would break it *silently*, and the breakage would be discovered at exactly the
moment someone needed it and had a live game running.

These assert the seam, not the behaviour: that every symbol the driver reaches
for still exists, and that the one non-obvious calling convention it depends on
has not changed underneath it.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about the driver working.** It is never run here: no credentials,
  no network, no venue. A green file means the names resolve.
- **Nothing about the payload being right.** `tests/test_hedge_*.py` own that.
- **Nothing about signatures beyond existence.** A function that kept its name
  and changed its arguments passes this and still breaks the driver.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import drive_hedge  # noqa: E402

from backend import hedge  # noqa: E402
from backend.kalshi.rest import KalshiRestClient  # noqa: E402
from backend.store import db  # noqa: E402


class TestTheDriverStillReachesRealSymbols:
    def test_the_hedge_functions_it_calls_exist(self):
        """Mutation observed red: rename any one of these in `backend/hedge.py`.

        Without this the rename is green everywhere and the driver dies the
        next time someone reaches for it mid-game.
        """
        for name in ("record_position", "legs_for", "resolve_leg", "build_payload"):
            assert hasattr(hedge, name), f"backend.hedge.{name} is gone"

    def test_the_store_functions_it_calls_exist(self):
        for name in ("init_db", "now_ms", "latest_balance_tenths"):
            assert hasattr(db, name), f"backend.store.db.{name} is gone"

    def test_the_alert_key_it_prints_exists(self):
        from backend.notify import alerts

        assert hasattr(alerts, "hedge_key")

    def test_the_quote_source_it_opens_and_closes_exists(self):
        from backend.kalshi.quotes import LiveQuoteSource

        assert hasattr(LiveQuoteSource, "fetch")
        assert hasattr(LiveQuoteSource, "aclose")


class TestTheCallingConventionHasNotMovedUnderIt:
    def test_events_is_an_async_generator_not_a_coroutine(self):
        """Trap 1 in the driver's docstring, pinned.

        `await api.events(...)` raises "object async_generator can't be used in
        'await' expression". The driver uses `async for`. If `events` ever
        becomes a coroutine returning a list, the driver breaks in a way whose
        error message points at the wrong thing -- and the person reading it
        will be mid-game.

        Mutation observed red: make `events` a plain `async def` returning a
        list.
        """
        assert inspect.isasyncgenfunction(KalshiRestClient.events)


class TestTheDriverIsImportableWithoutItsEnvironment:
    def test_importing_it_needs_no_env_vars(self):
        """It was written in a worktree that deliberately held no `.env`, so it
        read REPO / MAIN_CHECKOUT / SCRATCH from the environment and raised
        `KeyError` at import without them.

        Mutation observed red: restore `os.environ["REPO"]` at module level.
        The import above fails during collection and takes this whole file with
        it.
        """
        assert drive_hedge.ROOT.is_dir()
        assert drive_hedge.MAIN.is_dir()
        assert drive_hedge.SCRATCH.is_dir()

    def test_it_states_that_it_is_not_end_to_end_over_http(self):
        """The one claim most likely to be over-quoted from it. Mutation
        observed red: delete the sentence."""
        doc = drive_hedge.__doc__ or ""
        assert "not end-to-end over HTTP" in doc.replace("**", "")
        assert "fetch_live_route" in doc
