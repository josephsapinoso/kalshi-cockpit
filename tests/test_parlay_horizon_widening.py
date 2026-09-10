"""An empty `tonight` widens; a requested `tonight` does not.

WHY THIS EXISTS
---------------
Measured on live 2026-09-10: the `tonight` pool held one game and all seven
cards read "needs N fresh games and the slate has 1", while `tomorrow` built
six of seven from the same slate, the same markets and the same minute. 440 of
449 excluded legs were cut by `kickoff_outside_window` and 9 by staleness -- so
the empty screen was a clock problem, not a market-variety problem, and adding
totals or props would not have filled one of those cards.

`tonight` is still Joe's rule and still what is tried first. These tests pin the
two halves that keep the widening honest: it announces itself, and it never
overrides a window the caller actually named.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **Nothing about whether a widened card is a good bet.** Widening moves the
  pool's upper kickoff bound and nothing else; no leg is reordered and no
  consensus-vs-Kalshi gap is read (ADR 0071).
- **Nothing about the live slate.** These build their own pools.
"""

from __future__ import annotations

import httpx
import pytest

from backend import parlays as parlays_module
from backend.store import db as store
from tests.test_parlays_api import seed_game
from backend.api.routes import create_app
from backend.config import AppConfig
from backend.parlays import (
    DEFAULT_HORIZON,
    HORIZON_LADDER,
    build_ladder_payload_widening,
    end_of_desk_day_ms,
)


async def _get(app, path: str):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path)


@pytest.fixture
def empty_app(tmp_path):
    path = tmp_path / "widening.db"
    conn = store.init_db(path)
    conn.commit()
    conn.close()
    return create_app(AppConfig(instance_mode="demo", db_path=path))


@pytest.fixture
def tomorrow_only_app(tmp_path):
    """A slate where `tonight` builds nothing and `tomorrow` builds a card.

    This is the only bed that can tell the two route paths apart. On an empty
    pool every window refuses, so the widening returns `tonight` anyway and a
    route that widened when it must not would still LOOK correct -- which is
    how the first version of these tests passed a mutation that removed the
    guard entirely.
    """
    path = tmp_path / "tomorrow.db"
    conn = store.init_db(path)
    # Past tonight's rollover, inside tomorrow's. `seed_game` clamps its own
    # default into tonight, so the kickoff is passed explicitly.
    tomorrow = end_of_desk_day_ms(store.now_ms()) + 3_600_000
    computed = store.now_ms() - 30_000
    for i, (team, other) in enumerate(
        (("Reds", "Cubs"), ("Mets", "Pirates"), ("Rays", "Angels"))
    ):
        seed_game(
            conn,
            game=f"widen-{i}",
            team=team,
            other=other,
            p=0.74,
            computed_ms=computed,
            commence_ms=tomorrow,
        )
    conn.commit()
    conn.close()
    return create_app(AppConfig(instance_mode="demo", db_path=path))


def _payload(cards_built: bool, horizon: str) -> dict:
    """A minimal ladder payload, shaped like `build_ladder_payload`'s."""
    card = {"key": "safe", "title": "Safe"}
    if cards_built:
        card["legs"] = [{"label": "a leg"}]
    else:
        card["not_built_reason"] = "needs 2 fresh games and the slate has 1"
    return {
        "cards": [card],
        "excluded": {},
        "window": {"key": horizon, "words": f"words for {horizon}"},
    }


class _Recorder:
    """Stands in for `build_ladder_payload`, recording which windows it saw.

    Also records the `pool` it was handed each time. The widening loop reads
    the candidate pool once and filters it per window, so every call must
    receive the *same object* -- `pools` collects identities so a regression
    that went back to one scan per window shows up here as well as in
    `tests/test_ladder_scan_is_not_repeated.py`.
    """

    def __init__(self, builds: set[str]) -> None:
        self.builds = builds
        self.seen: list[str] = []
        self.pools: list[int] = []

    def __call__(self, conn, *, horizon: str, pool=None, **kwargs) -> dict:
        self.seen.append(horizon)
        self.pools.append(id(pool))
        return _payload(horizon in self.builds, horizon)


@pytest.fixture
def patched(monkeypatch):
    """Stubs both halves of the split.

    `candidate_pool` is stubbed because the loop now reads it before the first
    window, and these tests hand in `object()` as the connection: they are
    about the loop's control flow, and giving them a real database back would
    make them depend on a slate they do not seed.
    """

    def install(builds: set[str]) -> _Recorder:
        recorder = _Recorder(builds)
        monkeypatch.setattr(parlays_module, "build_ladder_payload", recorder)
        monkeypatch.setattr(
            parlays_module, "candidate_pool", lambda conn, **kw: _SENTINEL_POOL
        )
        return recorder

    return install


#: A stand-in pool. Identity is the only property these tests read.
_SENTINEL_POOL = object()


def _widen(**kwargs) -> dict:
    return build_ladder_payload_widening(
        object(), now_ms=1_789_000_000_000, max_odds_age_ms=600_000, **kwargs
    )


class TestItStopsAtTheNarrowestWindowThatBuilds:
    def test_a_building_tonight_is_not_widened(self, patched) -> None:
        recorder = patched({"tonight"})
        payload = _widen()
        assert recorder.seen == ["tonight"], "it queried past a window that built"
        assert payload["window"]["key"] == "tonight"
        assert "widened_from" not in payload["window"]

    def test_an_empty_tonight_falls_to_tomorrow(self, patched) -> None:
        recorder = patched({"tomorrow", "48h"})
        payload = _widen()
        assert recorder.seen == ["tonight", "tomorrow"]
        assert payload["window"]["key"] == "tomorrow"

    def test_it_reaches_the_widest_window_when_it_must(self, patched) -> None:
        recorder = patched({"48h"})
        payload = _widen()
        assert recorder.seen == list(HORIZON_LADDER)
        assert payload["window"]["key"] == "48h"

    def test_every_window_is_filtered_from_one_pool(self, patched) -> None:
        """Three windows tried, one pool read. The scan is horizon-independent
        (`CandidatePool`), so re-reading it per window was work thrown away."""
        recorder = patched({"48h"})
        _widen()
        assert len(recorder.pools) == len(HORIZON_LADDER)
        assert len(set(recorder.pools)) == 1
        assert recorder.pools[0] == id(_SENTINEL_POOL)


class TestTheWideningAnnouncesItself:
    """A screen showing tomorrow under tonight's label would look right."""

    def test_it_names_the_window_it_gave_up_on(self, patched) -> None:
        patched({"tomorrow"})
        window = _widen()["window"]
        assert window["widened_from"] == DEFAULT_HORIZON

    def test_it_says_the_card_cannot_settle_tonight(self, patched) -> None:
        # Joe's rule is about SETTLEMENT -- "I'd want to see my parlays finish
        # out by the time the evening games end" -- so widening past it has to
        # say that, not merely that the window moved.
        patched({"tomorrow"})
        words = _widen()["window"]["widened_words"]
        assert "cannot settle tonight" in words

    def test_the_words_name_the_window_actually_used(self, patched) -> None:
        patched({"48h"})
        window = _widen()["window"]
        assert window["words"] in window["widened_words"]


class TestItNeverManufacturesACard:
    def test_all_windows_empty_returns_the_narrowest(self, patched) -> None:
        # The refusal Joe reads must be the honest one about tonight, not the
        # widest window's -- otherwise an empty desk blames the wrong clock.
        recorder = patched(set())
        payload = _widen()
        assert recorder.seen == list(HORIZON_LADDER)
        assert payload["window"]["key"] == DEFAULT_HORIZON
        assert "widened_from" not in payload["window"]
        assert payload["cards"][0]["not_built_reason"]

    def test_the_ladder_starts_at_the_default(self) -> None:
        assert HORIZON_LADDER[0] == DEFAULT_HORIZON


class TestTheRouteHonoursAnExplicitWindow:
    """Asking for `tonight` and being shown tomorrow is the same lie.

    An empty pool is the right bed for these: the question is which window the
    payload reports, and with nothing to build, a widening bug would still
    move `window.key` off `tonight`.
    """

    async def test_naming_a_window_does_not_widen(self, tomorrow_only_app) -> None:
        # The slate HAS cards one day out, so a route that ignored the
        # explicit window would serve them and look perfectly healthy.
        response = await _get(tomorrow_only_app, "/api/parlays?horizon=tonight")
        assert response.status_code == 200
        body = response.json()
        assert body["window"]["key"] == "tonight"
        assert "widened_from" not in body["window"]
        assert all(c.get("not_built_reason") for c in body["cards"]), (
            "an explicitly requested empty window served tomorrow's cards"
        )

    async def test_omitting_the_window_does_widen_on_that_same_slate(
        self, tomorrow_only_app
    ) -> None:
        # The other half of the pair: same database, no window named.
        body = (await _get(tomorrow_only_app, "/api/parlays")).json()
        assert body["window"]["key"] == "tomorrow"
        assert body["window"]["widened_from"] == "tonight"
        assert any(not c.get("not_built_reason") for c in body["cards"])

    async def test_an_unknown_window_is_still_a_422(self, empty_app) -> None:
        response = await _get(empty_app, "/api/parlays?horizon=next%20week")
        assert response.status_code == 422
        assert "not a window this desk carries" in response.json()["detail"]

    async def test_omitting_the_window_still_serves_a_ladder(self, empty_app) -> None:
        response = await _get(empty_app, "/api/parlays")
        assert response.status_code == 200
        assert "window" in response.json()
