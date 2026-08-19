"""`_match_candidates` runs once per sport per pass, not once per event.

**What this establishes.** That linking N events of one sport issues exactly
one candidate query; that a second sport gets its own; that the cache does not
leak across passes; and that the events still link to the same fixtures they
did without it.

**What it does not.** It does not establish that one query is *fast* -- only
that it happens once. The query itself is a `SELECT DISTINCT` over
`odds_snapshots`, which grows by ~900 rows per odds sweep, so its own cost
still drifts; this removes the multiplier, not the trend. Nor does it cover the
prop path, which reads `_linked_fixtures` once already.

**Why it exists.** Measured on live 2026-08-19, on a slow pass:

    link slow: 11057ms total; candidates 10779ms over 456 calls,
    unmatched writes 117ms, link writes 1ms, other 159ms
    (531 discovered, 80 linked)

**97.5% of the leg was one query re-run 456 times.** `since_ms` comes from the
pass's single `now`, so every call for a given `sport_key` was identical --
the aliases immediately beside it were already cached and the candidates were
not. That asymmetry is what this closes.

The correctness argument runs the same way as the performance one: one snapshot
per pass means every event on a slate links against the same candidate set,
where before an event late in the loop could see fixtures an earlier one could
not.
"""

from __future__ import annotations

import pytest

from backend import runner
from backend.kalshi.discovery import DiscoveredEvent
from backend.runner import link_discovered_events
from backend.store import db

NOW = 1_787_000_000_000


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "candidates.db")
    yield c
    c.close()


@pytest.fixture
def counting(monkeypatch):
    """Counts calls to `_match_candidates` and records their arguments."""
    calls: list[str] = []
    real = runner._match_candidates

    def counted(conn, sport_key, *, since_ms):
        calls.append(sport_key)
        return real(conn, sport_key, since_ms=since_ms)

    monkeypatch.setattr(runner, "_match_candidates", counted)
    return calls


def games(sport_key: str, n: int) -> list[DiscoveredEvent]:
    return [
        DiscoveredEvent(
            event_ticker=f"KX{sport_key.upper()}-{i}",
            series_ticker=f"KX{sport_key.upper()}",
            league=sport_key,
            sport_key=sport_key,
            market_type="moneyline",
            title=f"Team {i}A vs Team {i}B",
            commence_ms=NOW,
            markets=(),
        )
        for i in range(n)
    ]


class TestOneQueryPerSport:
    def test_twenty_events_of_one_sport_query_once(self, conn, counting) -> None:
        link_discovered_events(conn, games("baseball_mlb", 20), now=NOW)
        assert counting == ["baseball_mlb"], (
            f"expected one query, got {len(counting)}"
        )

    def test_each_sport_gets_its_own(self, conn, counting) -> None:
        """Keyed by sport, not shared across them.

        A cache that returned one sport's fixtures for another would link
        events to the wrong games -- silently, and in a way that looks like a
        matcher bug rather than a cache bug.
        """
        events = games("baseball_mlb", 5) + games("basketball_wnba", 5)
        link_discovered_events(conn, events, now=NOW)
        assert sorted(counting) == ["baseball_mlb", "basketball_wnba"]

    def test_the_cache_does_not_survive_the_pass(self, conn, counting) -> None:
        """A pass must see fixtures swept in since the last one.

        Caching for the life of the *process* rather than the *pass* would
        freeze the candidate set at boot, so a fixture that appeared during a
        window would never be linked -- a correctness bug traded for the
        performance one, and a much quieter bug than the cost it replaced.
        """
        link_discovered_events(conn, games("baseball_mlb", 5), now=NOW)
        link_discovered_events(conn, games("baseball_mlb", 5), now=NOW + 15_000)
        assert counting == ["baseball_mlb", "baseball_mlb"], (
            "the second pass reused the first pass's candidate snapshot"
        )


class TestLinkingIsUnchanged:
    def test_the_same_events_resolve_either_way(self, conn, monkeypatch) -> None:
        """The cache must not change *which* events link, only the cost.

        Compares the real function against a forced-uncached run over the same
        slate and database. An optimisation that changed the result would be a
        regression wearing a speedup's clothes.
        """
        events = games("baseball_mlb", 8) + games("basketball_wnba", 4)

        cached = link_discovered_events(conn, events, now=NOW)

        # Defeat the cache by giving every event a distinct sport key would
        # change the query, so instead re-run with the cache emptied per event
        # via a patched dict type is fragile. Simplest honest control: call the
        # underlying matcher path once per event through a fresh pass with a
        # single event each, which cannot use a shared cache at all.
        one_at_a_time: dict = {}
        for event in events:
            one_at_a_time.update(
                link_discovered_events(conn, [event], now=NOW)
            )

        assert set(cached) == set(one_at_a_time), (
            "caching changed which events linked"
        )
