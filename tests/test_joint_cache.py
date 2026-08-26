"""The copula is computed once per distinct leg set, across requests.

Measured on live 2026-08-26 with a session cookie: `/api/parlays` answered in
**2.3 seconds warm**, on every load, against sub-second neighbours. That
crossed a stop-work trigger this project registered in advance —
`tasks/NEXT.md`: *"The stated stop-work trigger was 1s on `/api/parlays`; it
was not reached, so no payload cache was built."*

`_joint` runs a 200,000-sample Monte-Carlo copula five times per distinct leg
set. The memo that deduped it was a LOCAL dict, so six cards shared work within
one build and every HTTP request then started from nothing.

**The registered remedy was a payload cache; this is a memo instead, and the
difference is correctness rather than taste.** A payload cache has to guess an
expiry, and between refreshes it serves stale leg ages, a stale ask and a stale
freshness verdict — on a screen whose whole job is saying how old its inputs
are. `_joint_key` already carries every field `_joint` reads, and the copula is
seeded, so an equal key is an equal answer by construction. Nothing expires
because nothing can go stale.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That `/api/parlays` is now fast on live.** This measures the payload build
  in-process. The live route also pays SQLite reads on a contended box, and the
  cold column of that measurement (9.96s) is page-cache starvation, which is a
  separate fix.
- **That the cache is warm when it matters.** A fresh process starts empty, and
  the first request after a sweep changes every key. Both are correct: a new
  answer must be computed.
"""

from __future__ import annotations

import pytest

from backend.core import ladder
from backend.core.ladder import CandidateLeg, build_ladder


def _leg(i: int, *, p: float | None = None) -> CandidateLeg:
    return CandidateLeg(
        label=f"Team {i} to win",
        event_title=f"Away {i} at Team {i}",
        kalshi_event_ticker=f"KXMLBGAME-g{i}",
        kalshi_market_ticker=f"KXMLBGAME-g{i}-T",
        odds_event_id=f"g{i}",
        league="baseball_mlb",
        commence_ms=1_787_000_000_000 + i * 60_000,
        market="h2h",
        team=f"Team {i}",
        point=None,
        p_conservative=p if p is not None else 0.74 - i * 0.03,
        p_by_method={
            "multiplicative": 0.76 - i * 0.03,
            "additive": 0.75 - i * 0.03,
            "power": 0.755 - i * 0.03,
            "shin": 0.74 - i * 0.03,
        },
        odds_age_now_ms=30_000,
    )


# The cache is cleared for every test by `conftest.forget_computed_joints`.
# Not repeated here: two definitions of one guard is how they drift apart, and
# the global one is what protects the tests that do not know the cache exists —
# which is how `tests/test_ladder.py::TestJointMemo` went red when the cache
# was first hoisted out of `build_ladder`.


def _count_joint_calls(monkeypatch) -> list[int]:
    calls = [0]
    real = ladder._joint

    def counted(selected):
        calls[0] += 1
        return real(selected)

    monkeypatch.setattr(ladder, "_joint", counted)
    return calls


class TestTheCopulaIsNotRecomputedPerRequest:
    def test_a_second_build_of_the_same_slate_computes_no_joints(self, monkeypatch):
        """The defect, stated as a test.

        Two identical requests used to pay the full Monte-Carlo twice.
        """
        pool = [_leg(i) for i in range(6)]
        calls = _count_joint_calls(monkeypatch)

        build_ladder(pool, max_odds_age_ms=900_000, now_ms=1_787_000_000_000)
        first = calls[0]
        assert first > 0, "the fixture built no cards, so this proves nothing"

        build_ladder(pool, max_odds_age_ms=900_000, now_ms=1_787_000_000_000)
        assert calls[0] == first, (
            f"the second build recomputed {calls[0] - first} joint(s); the "
            f"memo is not surviving the call"
        )

    def test_six_cards_share_the_joints_they_agree_on(self, monkeypatch):
        """Six cuts of one pool routinely select the same legs."""
        pool = [_leg(i) for i in range(6)]
        calls = _count_joint_calls(monkeypatch)
        ladder_out = build_ladder(pool, max_odds_age_ms=900_000, now_ms=1_787_000_000_000)

        built = [c for c in ladder_out.cards if c.not_built_reason is None]
        assert len(built) > calls[0], (
            f"{len(built)} cards needed {calls[0]} joints — no sharing "
            f"happened, so the key is finer than the selection"
        )


class TestAChangedLegIsANewAnswer:
    def test_a_moved_probability_is_recomputed(self, monkeypatch):
        """The cache must not outlive the number it was computed from.

        This is the property that makes a memo safe where a TTL cache is not:
        the key carries the inputs, so a sweep that moves a fair value produces
        a different key rather than a stale hit.
        """
        pool = [_leg(i) for i in range(6)]
        build_ladder(pool, max_odds_age_ms=900_000, now_ms=1_787_000_000_000)

        calls = _count_joint_calls(monkeypatch)
        moved = [_leg(0, p=0.71)] + [_leg(i) for i in range(1, 6)]
        build_ladder(moved, max_odds_age_ms=900_000, now_ms=1_787_000_000_000)
        assert calls[0] > 0, (
            "a leg's probability changed and the cached joint was served — the "
            "key does not cover every field `_joint` reads"
        )

    def test_the_cached_answer_equals_the_computed_one(self):
        """A cache that returns a different number is worse than none."""
        pool = [_leg(i) for i in range(4)]
        cached = build_ladder(pool, max_odds_age_ms=900_000, now_ms=1_787_000_000_000)
        ladder._JOINT_CACHE.clear()
        fresh = build_ladder(pool, max_odds_age_ms=900_000, now_ms=1_787_000_000_000)

        for a, b in zip(cached.cards, fresh.cards):
            if a.joint is None or b.joint is None:
                assert a.joint is b.joint is None
                continue
            assert a.joint.conservative == b.joint.conservative
            assert a.joint.by_method == b.joint.by_method


class TestTheCacheIsBounded:
    def test_it_does_not_grow_without_limit(self, monkeypatch):
        """It outlives the request, so unbounded is a leak wearing a cache's clothes.

        **`_joint` is stubbed, and that is the point of the test rather than a
        shortcut.** The property under test is eviction — a dictionary length —
        and the first version of this drove it through `build_ladder`, which
        ran a real 200,000-sample copula for every one of ~300 distinct pools.
        It took 71 seconds standalone and was the single slowest thing in the
        suite: minutes of Monte-Carlo to assert `len(cache) <= 256`, in a
        commit whose whole subject is not recomputing that copula.

        A test nobody will wait for is a test that stops being run.
        """
        monkeypatch.setattr(
            ladder,
            "_joint",
            lambda selected: ladder.JointEstimate(
                conservative=0.5,
                by_method={m: 0.5 for m in ladder.METHODS},
                naive_product=0.5,
                independence_error_points=0.0,
            ),
        )
        for batch in range(ladder._JOINT_CACHE_MAX + 40):
            ladder._cached_joint([_leg(0, p=0.70 - batch * 0.0001)])

        assert len(ladder._JOINT_CACHE) <= ladder._JOINT_CACHE_MAX, (
            f"cache holds {len(ladder._JOINT_CACHE)} entries against a stated "
            f"ceiling of {ladder._JOINT_CACHE_MAX}"
        )

    def test_asking_again_protects_an_entry_from_eviction(self, monkeypatch):
        """A hit must move the key to the back of the eviction queue.

        **The first version of this test was decoration and mutation proved
        it.** It re-asked for the hot key inside the fill loop, so the newest
        entry was always a cold one and the hot key survived whether eviction
        took the oldest or the newest — the assertion could not fail.

        The discriminating shape is: fill to the ceiling with the hot key as
        the OLDEST, then touch it once, then overflow by one. With
        `move_to_end` the touch rescues it; without, it is exactly what gets
        dropped, and a cache that evicts the key you keep asking for is a slow
        path with extra steps.
        """
        monkeypatch.setattr(
            ladder,
            "_joint",
            lambda selected: ladder.JointEstimate(
                conservative=0.5,
                by_method={m: 0.5 for m in ladder.METHODS},
                naive_product=0.5,
                independence_error_points=0.0,
            ),
        )
        hot = [_leg(0, p=0.9)]
        hot_key = ladder._joint_key(hot)

        ladder._cached_joint(hot)                       # oldest entry
        for batch in range(ladder._JOINT_CACHE_MAX - 1):
            ladder._cached_joint([_leg(0, p=0.70 - batch * 0.0001)])
        assert len(ladder._JOINT_CACHE) == ladder._JOINT_CACHE_MAX
        assert next(iter(ladder._JOINT_CACHE)) == hot_key, (
            "fixture wrong: the hot key is not the oldest, so this cannot "
            "distinguish LRU from insertion order"
        )

        ladder._cached_joint(hot)                       # the touch under test
        ladder._cached_joint([_leg(0, p=0.123)])        # one over the ceiling

        assert hot_key in ladder._JOINT_CACHE, (
            "the key that was just asked for was evicted — a hit is not "
            "moving it to the back of the queue"
        )
