"""The hedge alert: the ratchet, the ceiling, and what never reaches the phone.

What these tests establish: only a reachable lock is pushed and a de-risk never
is; the dedupe key is a ratchet that announces a materially better figure and
stays quiet on noise and on a figure that falls back; an undelivered push does
not spend the day's ceiling; the watcher settles the venue's results before it
prices, because that is what turns a de-risk into a lock; the cadence follows
whether a watched game is actually running; a leg with no recorded kickoff
counts as running; and a failing cycle never takes the loop down.

What they do not establish: that any alert is worth acting on, or that a lock
survived long enough to be taken.
"""

from __future__ import annotations

import asyncio

import pytest

from backend import hedge, hedge_watch
from backend.notify.alerts import (
    HEDGE_RATCHET_STEP_TENTHS,
    MAX_HEDGE_PUSHES_PER_DAY,
    Alerter,
    hedge_key,
)
from backend.store import db

NOW_MS = 1_700_000_000_000
CIN = "KXMLBGAME-26AUG26CINSF-CIN"
LAD = "KXMLBGAME-26AUG26LADSD-LAD"


def position(*, floor_tenths=20_000, kind="lock", guaranteed=True, pid=7):
    """A serialised ticket, cut down to what the alert path reads."""
    rung = {
        "contracts": 100,
        "cost_display": "$46.73",
        "fee_display": "$1.73",
        "if_leg_wins_display": "$43.27",
        "if_leg_loses_display": "$43.27",
        "floor_display": "$43.27",
        "floor_tenths": floor_tenths,
        "floor_is_a_gain": floor_tenths > 0,
        "fillable": True,
        "affordable": True,
    }
    block = {
        "refusal": None,
        "kind": kind,
        "ticker": CIN,
        "side": "no",
        "ask_display": "45c",
        "depth_at_ask": 500.0,
        "ladder": [rung],
    }
    if kind == "lock":
        block.update(
            {
                "equalising": rung,
                "best_available": rung,
                "guaranteed": guaranteed,
                "guaranteed_display": "$43.27",
                "full_hedge_is_out_of_reach": False,
            }
        )
    else:
        block.update({"live_legs": 2, "chance_display": "49%"})
    return {
        "id": pid,
        "label": "Saturday six",
        "stake_display": "$5.00",
        "return_display": "$333.33",
        "state": kind,
        "legs": [
            {"label": "Cincinnati to win", "outcome": "pending", "chance_display": "20%"}
        ],
        "hedge": block,
    }


def screen(*positions):
    return {
        "as_of_ms": NOW_MS,
        "positions": list(positions),
        "notes": dict(hedge.NOTES),
    }


class Notifier:
    """Records what it was asked to send. `enabled`, like the real one."""

    enabled = True

    def __init__(self, delivers=True):
        self.delivers = delivers
        self.sent: list[dict] = []

    async def hedge_lock(self, position, *, notes):
        self.sent.append(position)
        return self.delivers


@pytest.fixture()
def conn(tmp_path):
    connection = db.init_db(tmp_path / "cockpit.db")
    yield connection
    connection.close()


class TestTheRatchetKey:
    def test_a_lock_is_keyed_on_the_position_and_the_step(self):
        assert hedge_key(position(floor_tenths=23_000)) == "hedge_lock:7:4"

    def test_a_materially_better_figure_lands_in_a_new_bucket(self):
        first = hedge_key(position(floor_tenths=20_000))
        better = hedge_key(position(floor_tenths=20_000 + HEDGE_RATCHET_STEP_TENTHS))
        assert first != better

    def test_noise_around_a_level_stays_in_one_bucket(self):
        # The property a threshold would need tuning for, and this gets for
        # free: a figure wobbling by a few cents says nothing new.
        base = HEDGE_RATCHET_STEP_TENTHS * 4
        assert hedge_key(position(floor_tenths=base)) == hedge_key(
            position(floor_tenths=base + HEDGE_RATCHET_STEP_TENTHS - 1)
        )

    def test_it_ratchets_one_way_because_a_used_bucket_stays_used(self):
        # A figure that rises then falls back re-enters a bucket already
        # claimed, so `UNIQUE (kind, key)` keeps it quiet. Nothing codes this
        # direction; it falls out of the key.
        high = hedge_key(position(floor_tenths=50_000))
        back = hedge_key(position(floor_tenths=50_000 - 100))
        assert high != back
        again = hedge_key(position(floor_tenths=50_000 + 100))
        assert again == high

    def test_a_derisk_has_no_key(self):
        assert hedge_key(position(kind="derisk")) is None

    def test_an_unreachable_lock_has_no_key(self):
        assert hedge_key(position(guaranteed=False)) is None

    def test_a_floor_that_is_not_a_gain_has_no_key(self):
        assert hedge_key(position(floor_tenths=-1_000)) is None

    def test_a_ticket_with_no_hedge_block_has_no_key(self):
        assert hedge_key({"id": 1, "hedge": None}) is None

    def test_an_older_payload_without_the_raw_figure_has_no_key(self):
        # A key built from a rendered string would re-announce on a rounding
        # change, so the absence of `floor_tenths` is a refusal, not a fallback.
        stale = position()
        del stale["hedge"]["best_available"]["floor_tenths"]
        assert hedge_key(stale) is None


class TestWhatReachesThePhone:
    async def test_a_reachable_lock_is_pushed(self, conn):
        notifier = Notifier()
        result = await Alerter(conn, notifier).hedge_locks(
            screen(position()), now_ms=NOW_MS, day_start_ms=NOW_MS - 3_600_000
        )
        assert len(notifier.sent) == 1
        assert len(result.sent) == 1

    async def test_a_derisk_is_neither_sent_nor_skipped(self, conn):
        # Counting it as skipped would inflate `alerts_deduped` with rows that
        # were never deduped -- the distinction ADR 0072 drew for a screen-only
        # parlay card.
        notifier = Notifier()
        result = await Alerter(conn, notifier).hedge_locks(
            screen(position(kind="derisk")),
            now_ms=NOW_MS,
            day_start_ms=NOW_MS - 3_600_000,
        )
        assert notifier.sent == []
        assert result.sent == () and result.skipped == ()

    async def test_a_lock_nobody_could_buy_is_not_a_lock(self, conn):
        notifier = Notifier()
        await Alerter(conn, notifier).hedge_locks(
            screen(position(guaranteed=False)),
            now_ms=NOW_MS,
            day_start_ms=NOW_MS - 3_600_000,
        )
        assert notifier.sent == []

    async def test_the_same_figure_is_said_once(self, conn):
        notifier = Notifier()
        alerter = Alerter(conn, notifier)
        for _ in range(4):
            await alerter.hedge_locks(
                screen(position()), now_ms=NOW_MS, day_start_ms=NOW_MS - 3_600_000
            )
        assert len(notifier.sent) == 1

    async def test_a_better_figure_is_said_again(self, conn):
        notifier = Notifier()
        alerter = Alerter(conn, notifier)
        await alerter.hedge_locks(
            screen(position(floor_tenths=20_000)),
            now_ms=NOW_MS,
            day_start_ms=NOW_MS - 3_600_000,
        )
        await alerter.hedge_locks(
            screen(position(floor_tenths=40_000)),
            now_ms=NOW_MS,
            day_start_ms=NOW_MS - 3_600_000,
        )
        assert len(notifier.sent) == 2

    async def test_the_day_has_a_ceiling(self, conn):
        notifier = Notifier()
        alerter = Alerter(conn, notifier)
        for step in range(MAX_HEDGE_PUSHES_PER_DAY + 3):
            await alerter.hedge_locks(
                screen(
                    position(
                        floor_tenths=20_000 + step * HEDGE_RATCHET_STEP_TENTHS
                    )
                ),
                now_ms=NOW_MS,
                day_start_ms=NOW_MS - 3_600_000,
            )
        assert len(notifier.sent) == MAX_HEDGE_PUSHES_PER_DAY

    async def test_an_undelivered_push_does_not_spend_the_ceiling(self, conn):
        # One Discord outage must not silence the rest of the day (ADR 0072 §4).
        notifier = Notifier(delivers=False)
        alerter = Alerter(conn, notifier)
        for step in range(MAX_HEDGE_PUSHES_PER_DAY + 2):
            await alerter.hedge_locks(
                screen(
                    position(
                        floor_tenths=20_000 + step * HEDGE_RATCHET_STEP_TENTHS
                    )
                ),
                now_ms=NOW_MS,
                day_start_ms=NOW_MS - 3_600_000,
            )
        assert len(notifier.sent) == MAX_HEDGE_PUSHES_PER_DAY + 2

    async def test_the_ceiling_binds_inside_one_screen_too(self, conn):
        # Several tickets locking at once is one call, so the DB count cannot
        # bound them -- only the in-loop counter can. A version of this that
        # sent one position per call left that increment untested.
        notifier = Notifier()
        tickets = [
            position(
                pid=i, floor_tenths=20_000 + i * HEDGE_RATCHET_STEP_TENTHS
            )
            for i in range(MAX_HEDGE_PUSHES_PER_DAY + 3)
        ]
        result = await Alerter(conn, notifier).hedge_locks(
            screen(*tickets), now_ms=NOW_MS, day_start_ms=NOW_MS - 3_600_000
        )
        assert len(notifier.sent) == MAX_HEDGE_PUSHES_PER_DAY
        assert len(result.skipped) == 3

    async def test_an_undelivered_push_inside_one_screen_keeps_the_day(self, conn):
        notifier = Notifier(delivers=False)
        tickets = [
            position(
                pid=i, floor_tenths=20_000 + i * HEDGE_RATCHET_STEP_TENTHS
            )
            for i in range(MAX_HEDGE_PUSHES_PER_DAY + 3)
        ]
        await Alerter(conn, notifier).hedge_locks(
            screen(*tickets), now_ms=NOW_MS, day_start_ms=NOW_MS - 3_600_000
        )
        # Every one was attempted: an outage must not silence the day.
        assert len(notifier.sent) == MAX_HEDGE_PUSHES_PER_DAY + 3

    async def test_a_notifier_that_is_off_says_nothing_and_does_not_raise(self, conn):
        class Off:
            enabled = False

        result = await Alerter(conn, Off()).hedge_locks(
            screen(position()), now_ms=NOW_MS, day_start_ms=NOW_MS - 3_600_000
        )
        assert result.sent == ()


class TestTheEmbedRefusesWhatThePolicyRefuses:
    """The transport guards the same condition the policy does.

    Not redundancy: a transport that renders an unlocked "lock" is one that
    will eventually be called by something that forgot to check.
    """

    async def test_a_derisk_never_renders(self):
        from backend.notify.discord import DiscordConfig, DiscordNotifier

        notifier = DiscordNotifier(
            DiscordConfig(cockpit_base_url="http://x", webhook_url="http://y")
        )
        assert (
            await notifier.hedge_lock(
                position(kind="derisk"), notes=dict(hedge.NOTES)
            )
            is False
        )

    async def test_an_unreachable_lock_never_renders(self):
        from backend.notify.discord import DiscordConfig, DiscordNotifier

        notifier = DiscordNotifier(
            DiscordConfig(cockpit_base_url="http://x", webhook_url="http://y")
        )
        assert (
            await notifier.hedge_lock(
                position(guaranteed=False), notes=dict(hedge.NOTES)
            )
            is False
        )


class TestTheWatcher:
    def _ticket(self, conn, *, commence_ms=None):
        return hedge.record_position(
            conn,
            now_ms=NOW_MS,
            source="sportsbook",
            label="Saturday six",
            stake_tenths=5_000,
            return_tenths=100_000,
            legs=[
                {
                    "ticker": CIN,
                    "side": "yes",
                    "label": "Cincinnati to win",
                    "commence_ms": commence_ms,
                },
                {
                    "ticker": LAD,
                    "side": "yes",
                    "label": "Los Angeles to win",
                    "commence_ms": commence_ms,
                },
            ],
        )

    def test_a_started_game_is_in_progress(self, conn):
        self._ticket(conn, commence_ms=NOW_MS - 1)
        assert hedge_watch.anything_in_progress(conn, now_ms=NOW_MS) is True

    def test_tomorrow_night_is_not(self, conn):
        self._ticket(conn, commence_ms=NOW_MS + 86_400_000)
        assert hedge_watch.anything_in_progress(conn, now_ms=NOW_MS) is False

    def test_an_unknown_kickoff_counts_as_running(self, conn):
        # An unknown start must not resolve to "not yet" -- that would sleep
        # through the entire game rather than fail loudly.
        self._ticket(conn, commence_ms=None)
        assert hedge_watch.anything_in_progress(conn, now_ms=NOW_MS) is True

    def test_a_settled_ticket_is_not_watched(self, conn):
        position_id = self._ticket(conn, commence_ms=NOW_MS - 1)
        hedge.close_position(
            conn, position_id=position_id, now_ms=NOW_MS, status="settled"
        )
        assert hedge_watch.anything_in_progress(conn, now_ms=NOW_MS) is False

    async def test_it_settles_the_venues_results_before_it_prices(self, conn):
        """The ordering that turns a de-risk into a lock.

        A leg the venue called ten minutes ago and nobody has read is the
        difference between "several legs live" and "one leg live".
        """
        position_id = self._ticket(conn, commence_ms=NOW_MS - 1)
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_series (series_ticker, title, "
            "first_seen_ms, last_seen_ms) VALUES ('S', 's', ?, ?)",
            (NOW_MS, NOW_MS),
        )
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_events (event_ticker, series_ticker, "
            "title, first_seen_ms, last_seen_ms) VALUES ('E', 'S', 'e', ?, ?)",
            (NOW_MS, NOW_MS),
        )
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, event_ticker, series_ticker, "
            "market_type, title, result, first_seen_ms, last_seen_ms) "
            "VALUES (?, 'E', 'S', 'binary', 't', 'yes', ?, ?)",
            (LAD, NOW_MS, NOW_MS),
        )
        conn.commit()

        async def fetch(ticker, *, observed_ms):
            raise RuntimeError("no venue in this test")

        summary = await hedge_watch.watch_once(
            conn,
            Alerter(conn, Notifier()),
            now_ms=NOW_MS,
            max_quote_age_ms=30_000,
            fetch_quote=fetch,
        )
        assert summary["legs_settled"] == 1
        legs = hedge.legs_for(conn, position_id)
        assert legs[1]["outcome"] == "won"
        assert legs[1]["resolved_source"] == "venue"

    async def test_a_failing_cycle_never_takes_the_loop_down(self, tmp_path):
        path = tmp_path / "cockpit.db"
        connection = db.init_db(path)
        try:
            # Without a live ticket `busy` is False and the cycle body never
            # runs, so the try/except this test is about is never entered. The
            # first version of this test was exactly that shape and a mutation
            # removing the guard stayed GREEN.
            self._ticket(connection, commence_ms=NOW_MS - 1)
        finally:
            connection.close()

        slept: list[float] = []

        async def sleep(seconds):
            slept.append(seconds)

        def exploding_factory(_conn):
            raise_on = Notifier()

            class Boom(Alerter):
                async def hedge_locks(self, *a, **k):
                    raise RuntimeError("the venue melted")

            return Boom(_conn, raise_on)

        async def fetch(ticker, *, observed_ms):
            raise RuntimeError("nothing answers")

        await hedge_watch.watch_hedges_forever(
            path,
            exploding_factory,
            fetch_quote=fetch,
            max_quote_age_ms=30_000,
            sleep=sleep,
            clock=lambda: NOW_MS / 1000,
            max_cycles=3,
        )
        assert len(slept) == 3

    async def test_the_cadence_follows_whether_anything_is_running(self, tmp_path):
        path = tmp_path / "cockpit.db"
        connection = db.init_db(path)
        connection.close()

        slept: list[float] = []

        async def sleep(seconds):
            slept.append(seconds)

        async def fetch(ticker, *, observed_ms):
            raise RuntimeError("nothing answers")

        await hedge_watch.watch_hedges_forever(
            path,
            lambda c: Alerter(c, Notifier()),
            fetch_quote=fetch,
            max_quote_age_ms=30_000,
            sleep=sleep,
            clock=lambda: NOW_MS / 1000,
            max_cycles=1,
        )
        # Nothing recorded, so nothing to watch: the idle cadence.
        assert slept == [hedge_watch.IDLE_INTERVAL_S]

        working = db.connect(path)
        try:
            self._ticket(working, commence_ms=NOW_MS - 1)
        finally:
            working.close()

        slept.clear()
        await hedge_watch.watch_hedges_forever(
            path,
            lambda c: Alerter(c, Notifier()),
            fetch_quote=fetch,
            max_quote_age_ms=30_000,
            sleep=sleep,
            clock=lambda: NOW_MS / 1000,
            max_cycles=1,
        )
        assert slept == [hedge_watch.WATCH_INTERVAL_S]


class TestTheWatcherIsNotOnTheRecordersClock:
    def test_the_runner_starts_it_as_its_own_task(self):
        """ADR 0072 Decision 5: work added to the quote pass has a budget.

        Asserted over the source, because the failure mode is somebody moving
        this into `run_quote_pass` on the reasoning that it is cheap — which is
        exactly the reasoning that cost 400ms a pass last time.
        """
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        from conftest import python_code_without_prose

        loop_source = (root / "scripts" / "run_loop.py").read_text(encoding="utf-8")
        assert 'name="hedge-watch"' in loop_source
        assert "watch_hedges_forever" in loop_source

        runner = python_code_without_prose(root / "backend" / "runner.py")
        assert "hedge_watch" not in runner
        assert "watch_hedges_forever" not in runner
        assert "run_quote_pass" in runner

    def test_the_watcher_spends_nothing_metered(self):
        """Joe's constraint, made executable.

        Read off the CODE and not the prose. The first version of this failed
        on the module's own docstring, which explains that no `api_credits` row
        is written — and the two ways out of that are weakening the assertion
        or deleting the explanation, both worse than the guard.
        """
        from pathlib import Path

        from conftest import python_code_without_prose

        root = Path(__file__).resolve().parent.parent
        code = python_code_without_prose(root / "backend" / "hedge_watch.py")
        assert "api_credits" not in code
        assert "CreditBudget" not in code
        assert "fetch_odds" not in code
        assert "anthropic" not in code.lower()
        assert "structured_call" not in code
        # Vacuity guard: the stripper must not have eaten the module.
        assert "watch_hedges_forever" in code
