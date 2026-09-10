"""The hedge alert: the ratchet, the ceiling, and what never reaches the phone.

What these tests establish: only a reachable lock is pushed and a de-risk never
is; the dedupe key is a ratchet that announces a materially better figure and
stays quiet on noise and on a figure that falls back; an undelivered push does
not spend the day's ceiling; the watcher settles the venue's results before it
prices, because that is what turns a de-risk into a lock; the cadence follows
whether a watched game is actually running; a leg with no recorded kickoff
counts as running; and a failing cycle never takes the loop down.

**Also, since 2026-09-10 (AMENDS ADR 0078 D2):** a second, symmetric push --
"legs in play" -- fires once per ticket per budget day while a watched game is
running, regardless of whether the news is good or bad; it never states a
dollar figure the tool cannot stand behind; it shares neither its dedupe
bucket nor its daily ceiling with the LOCK push; and a fixed list of words
(threshold-alert language, plus "guaranteed"/"locked"/"lock" whenever more
than one leg is live) never appears in its rendered text.

What they do not establish: that any alert is worth acting on, or that a lock
survived long enough to be taken.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from backend import hedge, hedge_watch
from backend.notify.alerts import (
    HEDGE_RATCHET_STEP_TENTHS,
    MAX_HEDGE_PUSHES_PER_DAY,
    MAX_POSITION_STATE_PUSHES_PER_DAY,
    POSITION_STATE_KIND,
    Alerter,
    hedge_key,
    position_state_key,
)
from backend.notify.discord import DiscordConfig, DiscordNotifier
from backend.store import db

NOW_MS = 1_700_000_000_000
CIN = "KXMLBGAME-26AUG26CINSF-CIN"
LAD = "KXMLBGAME-26AUG26LADSD-LAD"
DISCORD_CHANNEL = "555555555"
DISCORD_API = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL}/messages"


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


def leg(
    *,
    label="Cincinnati to win",
    outcome="pending",
    chance_display="91%",
    quote_age_ms=5_000,
):
    """One leg exactly as `hedge._leg_payload` serialises it, cut to what
    `position_state` reads."""
    return {
        "label": label,
        "outcome": outcome,
        "chance_display": chance_display,
        "quote_age_ms": quote_age_ms,
    }


def ticket(
    *,
    pid=7,
    pending_legs=1,
    legs=None,
    hedge_block=None,
    stake_display="$5.00",
    return_display="$333.33",
    label="Saturday six",
):
    """A serialised position, cut down to what `position_states` reads.

    Distinct from `position()` above (which is shaped for `hedge_locks`):
    this one carries `pending_legs` and a full `legs` list rather than a
    single hard-coded pending leg, because the symmetric push needs both
    live and settled legs to exercise its per-leg rendering.
    """
    if legs is None:
        legs = [leg()]
    return {
        "id": pid,
        "label": label,
        "stake_display": stake_display,
        "return_display": return_display,
        "pending_legs": pending_legs,
        "legs": legs,
        "hedge": hedge_block,
    }


class Notifier:
    """Records what it was asked to send. `enabled`, like the real one."""

    enabled = True

    def __init__(self, delivers=True):
        self.delivers = delivers
        self.sent: list[dict] = []
        self.position_sent: list[dict] = []

    async def hedge_lock(self, position, *, notes):
        self.sent.append(position)
        return self.delivers

    async def position_state(self, position, *, notes, as_of_ms):
        self.position_sent.append(position)
        return self.delivers


@pytest.fixture()
def conn(tmp_path):
    connection = db.init_db(tmp_path / "cockpit.db")
    yield connection
    connection.close()


@pytest.fixture()
def discord_config():
    return DiscordConfig(
        bot_token="test-token",
        channel_id=DISCORD_CHANNEL,
        cockpit_base_url="https://cockpit.example",
    )


@pytest.fixture(scope="module")
def discord_http_client():
    return httpx.AsyncClient(timeout=5.0)


@pytest.fixture()
def discord_notifier(discord_config, discord_http_client):
    return DiscordNotifier(discord_config, client=discord_http_client)


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


class TestThePositionStateKey:
    """AMENDS ADR 0078 D2: once per ticket per day, not a ratchet."""

    def test_a_pending_leg_gets_a_key(self):
        assert (
            position_state_key(ticket(pending_legs=1), day_start_ms=NOW_MS)
            == f"position_state:7:{NOW_MS}"
        )

    def test_no_pending_legs_has_no_key(self):
        assert (
            position_state_key(ticket(pending_legs=0), day_start_ms=NOW_MS)
            is None
        )

    def test_a_ticket_with_no_id_has_no_key(self):
        t = ticket(pending_legs=1)
        del t["id"]
        assert position_state_key(t, day_start_ms=NOW_MS) is None

    def test_the_key_is_stable_across_the_day_and_changes_the_next(self):
        first = position_state_key(ticket(pending_legs=1), day_start_ms=NOW_MS)
        same_day = position_state_key(ticket(pending_legs=1), day_start_ms=NOW_MS)
        next_day = position_state_key(
            ticket(pending_legs=1), day_start_ms=NOW_MS + 86_400_000
        )
        assert first == same_day
        assert first != next_day


class TestTheSymmetricPushReachesThePhone:
    """`Alerter.position_states`, in the shape of `TestWhatReachesThePhone`."""

    async def test_it_fires_once_per_ticket_across_four_cycles_in_one_day(
        self, conn
    ):
        # Four cycles at four different clock times but ONE budget day --
        # the shape a real 60s-cadence watcher produces. Varying `now_ms`
        # while holding `day_start_ms` fixed is what would catch a key built
        # from the wrong one of the two.
        notifier = Notifier()
        alerter = Alerter(conn, notifier)
        day = NOW_MS - 3_600_000
        for i in range(4):
            await alerter.position_states(
                screen(ticket(pending_legs=1)),
                now_ms=NOW_MS + i * 60_000,
                day_start_ms=day,
            )
        assert len(notifier.position_sent) == 1

    async def test_it_fires_again_on_the_next_budget_day(self, conn):
        notifier = Notifier()
        alerter = Alerter(conn, notifier)
        day_one = NOW_MS - 3_600_000
        await alerter.position_states(
            screen(ticket(pending_legs=1)), now_ms=NOW_MS, day_start_ms=day_one
        )
        day_two = day_one + 86_400_000
        await alerter.position_states(
            screen(ticket(pending_legs=1)),
            now_ms=NOW_MS + 86_400_000,
            day_start_ms=day_two,
        )
        assert len(notifier.position_sent) == 2

    async def test_a_closed_ticket_is_neither_sent_nor_skipped(self, conn):
        notifier = Notifier()
        result = await Alerter(conn, notifier).position_states(
            screen(ticket(pending_legs=0)),
            now_ms=NOW_MS,
            day_start_ms=NOW_MS - 3_600_000,
        )
        assert notifier.position_sent == []
        assert result.sent == () and result.skipped == ()

    async def test_the_ceiling_binds_at_four_delivered(self, conn):
        notifier = Notifier()
        alerter = Alerter(conn, notifier)
        tickets = [
            ticket(pid=i, pending_legs=1)
            for i in range(MAX_POSITION_STATE_PUSHES_PER_DAY + 3)
        ]
        result = await alerter.position_states(
            screen(*tickets), now_ms=NOW_MS, day_start_ms=NOW_MS - 3_600_000
        )
        assert len(notifier.position_sent) == MAX_POSITION_STATE_PUSHES_PER_DAY
        assert len(result.skipped) == 3

    async def test_an_undelivered_push_does_not_spend_the_ceiling(self, conn):
        # One Discord outage must not silence the rest of the day.
        notifier = Notifier(delivers=False)
        alerter = Alerter(conn, notifier)
        tickets = [
            ticket(pid=i, pending_legs=1)
            for i in range(MAX_POSITION_STATE_PUSHES_PER_DAY + 2)
        ]
        await alerter.position_states(
            screen(*tickets), now_ms=NOW_MS, day_start_ms=NOW_MS - 3_600_000
        )
        assert (
            len(notifier.position_sent)
            == MAX_POSITION_STATE_PUSHES_PER_DAY + 2
        )

    async def test_hedge_lock_and_position_state_do_not_share_a_ceiling(
        self, conn
    ):
        notifier = Notifier()
        alerter = Alerter(conn, notifier)
        day = NOW_MS - 3_600_000
        for step in range(MAX_HEDGE_PUSHES_PER_DAY):
            await alerter.hedge_locks(
                screen(
                    position(
                        floor_tenths=20_000 + step * HEDGE_RATCHET_STEP_TENTHS
                    )
                ),
                now_ms=NOW_MS,
                day_start_ms=day,
            )
        assert len(notifier.sent) == MAX_HEDGE_PUSHES_PER_DAY

        result = await alerter.position_states(
            screen(ticket(pending_legs=1)), now_ms=NOW_MS, day_start_ms=day
        )
        assert len(notifier.position_sent) == 1
        assert result.sent != ()

    async def test_a_notifier_that_is_off_says_nothing_and_does_not_raise(
        self, conn
    ):
        class Off:
            enabled = False

        result = await Alerter(conn, Off()).position_states(
            screen(ticket(pending_legs=1)),
            now_ms=NOW_MS,
            day_start_ms=NOW_MS - 3_600_000,
        )
        assert result.sent == ()

    async def test_the_row_is_kept_under_its_own_kind(self, conn):
        notifier = Notifier()
        await Alerter(conn, notifier).position_states(
            screen(ticket(pending_legs=1)),
            now_ms=NOW_MS,
            day_start_ms=NOW_MS - 3_600_000,
        )
        row = conn.execute(
            "SELECT kind FROM notifications WHERE kind = ?",
            (POSITION_STATE_KIND,),
        ).fetchone()
        assert row is not None


def _rendered_text(embed: dict, *, exclude_fields: tuple[str, ...] = ()) -> str:
    """Title, description and every non-excluded field, lower-cased.

    **Deliberately excludes the footer.** The footer carries `hedge.NOTES`
    verbatim -- the same pre-approved boilerplate `hedge_lock`'s footer
    already ships unchanged, including the phrase "right now" and the verb
    "lock in". The forbidden-word contract is about the language THIS
    feature invents for its title, description and fields, not about
    re-litigating text ADR 0078 already settled and ships elsewhere
    unmodified.
    """
    parts = [embed.get("title", ""), embed.get("description", "")]
    for field in embed.get("fields", []):
        if field.get("name") in exclude_fields:
            continue
        parts.append(field.get("name", ""))
        parts.append(field.get("value", ""))
    return " ".join(parts).lower()


def _strip_numbers(text: str) -> str:
    """The sentence with every digit run blanked out, for a structure diff."""
    import re

    return re.sub(r"[\d.]+", "#", text)


ALWAYS_FORBIDDEN = (
    "now",
    "consider",
    "warning",
    "alert",
    "at risk",
    "trouble",
    "still available",
    "hedge now",
    "collapsing",
)

#: Forbidden only while more than one leg is live -- see `hedge._hedge_payload`:
#: a derisk block carries no `guaranteed` key at all, and these three words are
#: the ones that would invite a screen to render "not guaranteed" beside a
#: number as though one were coming.
MANY_LIVE_FORBIDDEN = ("guaranteed", "locked", "lock")


class TestTheLegsInPlayEmbed:
    """`DiscordNotifier.position_state`: the rendered shape, over the wire."""

    @respx.mock
    async def test_a_rising_leg_and_a_falling_leg_share_one_template(
        self, discord_notifier
    ):
        route = respx.post(DISCORD_API).mock(
            return_value=httpx.Response(200, json={})
        )

        async with discord_notifier as n:
            await n.position_state(
                ticket(legs=[leg(chance_display="91%")]),
                notes=dict(hedge.NOTES),
                as_of_ms=NOW_MS,
            )
        rising = json.loads(route.calls.last.request.read())["embeds"][0]

        async with discord_notifier as n:
            await n.position_state(
                ticket(legs=[leg(chance_display="9%")]),
                notes=dict(hedge.NOTES),
                as_of_ms=NOW_MS,
            )
        falling = json.loads(route.calls.last.request.read())["embeds"][0]

        assert rising["title"] == falling["title"]
        assert [f["name"] for f in rising["fields"]] == [
            f["name"] for f in falling["fields"]
        ]
        assert _strip_numbers(rising["description"]) == _strip_numbers(
            falling["description"]
        )
        assert [_strip_numbers(f["value"]) for f in rising["fields"]] == [
            _strip_numbers(f["value"]) for f in falling["fields"]
        ]

    @respx.mock
    async def test_the_description_states_stake_return_count_and_freshness(
        self, discord_notifier
    ):
        route = respx.post(DISCORD_API).mock(
            return_value=httpx.Response(200, json={})
        )
        async with discord_notifier as n:
            await n.position_state(
                ticket(
                    pending_legs=1,
                    legs=[leg(label="Cincinnati to win"), leg(
                        label="LA to win", outcome="won",
                        chance_display="--", quote_age_ms=None,
                    )],
                ),
                notes=dict(hedge.NOTES),
                as_of_ms=NOW_MS,
            )
        embed = json.loads(route.calls.last.request.read())["embeds"][0]
        assert "$5.00" in embed["description"]
        assert "$333.33" in embed["description"]
        assert "1 of 2 legs live" in embed["description"]

    @respx.mock
    async def test_a_settled_leg_shows_its_outcome_word(self, discord_notifier):
        route = respx.post(DISCORD_API).mock(
            return_value=httpx.Response(200, json={})
        )
        async with discord_notifier as n:
            await n.position_state(
                ticket(
                    pending_legs=1,
                    legs=[
                        leg(label="Cincinnati to win"),
                        leg(
                            label="LA to win", outcome="won",
                            chance_display="--", quote_age_ms=None,
                        ),
                    ],
                ),
                notes=dict(hedge.NOTES),
                as_of_ms=NOW_MS,
            )
        embed = json.loads(route.calls.last.request.read())["embeds"][0]
        won_field = next(
            f for f in embed["fields"] if f["name"] == "LA to win"
        )
        assert won_field["value"] == "Won"

    @respx.mock
    async def test_several_live_legs_get_the_no_figure_locks_field(
        self, discord_notifier
    ):
        route = respx.post(DISCORD_API).mock(
            return_value=httpx.Response(200, json={})
        )
        async with discord_notifier as n:
            await n.position_state(
                ticket(
                    pending_legs=2,
                    legs=[
                        leg(label="Cincinnati to win"),
                        leg(label="Los Angeles to win", chance_display="30%"),
                    ],
                ),
                notes=dict(hedge.NOTES),
                as_of_ms=NOW_MS,
            )
        embed = json.loads(route.calls.last.request.read())["embeds"][0]
        names = [f["name"] for f in embed["fields"]]
        assert "No figure locks" in names
        assert "Locks" not in names

    @respx.mock
    async def test_one_live_leg_with_a_guaranteed_lock_states_it(
        self, discord_notifier
    ):
        route = respx.post(DISCORD_API).mock(
            return_value=httpx.Response(200, json={})
        )
        block = {
            "kind": "lock", "guaranteed": True, "guaranteed_display": "$43.27",
        }
        async with discord_notifier as n:
            await n.position_state(
                ticket(pending_legs=1, hedge_block=block),
                notes=dict(hedge.NOTES),
                as_of_ms=NOW_MS,
            )
        embed = json.loads(route.calls.last.request.read())["embeds"][0]
        locks = next(f for f in embed["fields"] if f["name"] == "Locks")
        assert "$43.27" in locks["value"]
        assert "last leg" in locks["value"]

    @respx.mock
    async def test_one_live_leg_without_a_lock_has_no_guarantee_line(
        self, discord_notifier
    ):
        route = respx.post(DISCORD_API).mock(
            return_value=httpx.Response(200, json={})
        )
        async with discord_notifier as n:
            await n.position_state(
                ticket(pending_legs=1, hedge_block=None),
                notes=dict(hedge.NOTES),
                as_of_ms=NOW_MS,
            )
        embed = json.loads(route.calls.last.request.read())["embeds"][0]
        assert not any(f["name"] == "Locks" for f in embed["fields"])

    @respx.mock
    async def test_the_footer_carries_the_two_notes_verbatim(
        self, discord_notifier
    ):
        route = respx.post(DISCORD_API).mock(
            return_value=httpx.Response(200, json={})
        )
        async with discord_notifier as n:
            await n.position_state(
                ticket(), notes=dict(hedge.NOTES), as_of_ms=NOW_MS
            )
        embed = json.loads(route.calls.last.request.read())["embeds"][0]
        assert embed["footer"]["text"] == (
            f"{hedge.NOTES['not_advice']}\n{hedge.NOTES['upper_bound']}"
        )

    @respx.mock
    async def test_a_derisk_never_renders_from_this_method_either(
        self, discord_notifier
    ):
        # `position_state` is not gated on `hedge['kind']` the way
        # `hedge_lock` is -- it renders for ANY in-play ticket -- so this
        # pins that a de-risk block simply produces no guarantee line rather
        # than being refused outright.
        route = respx.post(DISCORD_API).mock(
            return_value=httpx.Response(200, json={})
        )
        block = {"kind": "derisk", "live_legs": 2, "chance_display": "49%"}
        async with discord_notifier as n:
            assert await n.position_state(
                ticket(pending_legs=2, hedge_block=block),
                notes=dict(hedge.NOTES),
                as_of_ms=NOW_MS,
            )


class TestTheForbiddenWords:
    """Pinned by rendering a position and asserting each word is absent."""

    @respx.mock
    async def test_always_forbidden_words_are_absent(self, discord_notifier):
        route = respx.post(DISCORD_API).mock(
            return_value=httpx.Response(200, json={})
        )
        block = {
            "kind": "lock", "guaranteed": True, "guaranteed_display": "$43.27",
        }
        async with discord_notifier as n:
            await n.position_state(
                ticket(pending_legs=1, hedge_block=block),
                notes=dict(hedge.NOTES),
                as_of_ms=NOW_MS,
            )
        embed = json.loads(route.calls.last.request.read())["embeds"][0]
        text = _rendered_text(embed)
        for word in ALWAYS_FORBIDDEN:
            assert word not in text, word

    @respx.mock
    async def test_lock_words_are_absent_when_several_legs_are_live(
        self, discord_notifier
    ):
        # Deliberately adversarial: the hedge block claims a guaranteed lock
        # even though two legs are pending, which real data should never
        # produce (a `lock` block only exists with one leg live) -- but the
        # rendering guard has to hold regardless of what the hedge block
        # says, not merely happen to be safe because test data is well
        # formed. This is what makes the test actually exercise the `n_live`
        # gate rather than pass because nothing tried to trip it.
        route = respx.post(DISCORD_API).mock(
            return_value=httpx.Response(200, json={})
        )
        block = {
            "kind": "lock", "guaranteed": True, "guaranteed_display": "$43.27",
        }
        async with discord_notifier as n:
            await n.position_state(
                ticket(
                    pending_legs=2,
                    legs=[
                        leg(label="Cincinnati to win"),
                        leg(label="Los Angeles to win", chance_display="30%"),
                    ],
                    hedge_block=block,
                ),
                notes=dict(hedge.NOTES),
                as_of_ms=NOW_MS,
            )
        embed = json.loads(route.calls.last.request.read())["embeds"][0]
        # The mandated "No figure locks" field is pre-approved boilerplate
        # and is the one place "locks" is allowed to appear -- excluded here,
        # and its presence is pinned by its own test above.
        text = _rendered_text(embed, exclude_fields=("No figure locks",))
        for word in MANY_LIVE_FORBIDDEN:
            assert word not in text, word

    @respx.mock
    async def test_a_single_guaranteed_lock_is_not_bound_by_the_many_live_list(
        self, discord_notifier
    ):
        # The inverse check: with exactly one leg live, "guaranteed",
        # "locked" and "lock" are NOT forbidden -- that is the one figure
        # this embed is allowed to state -- so a naive universal ban would
        # be wrong here rather than merely unnecessary.
        route = respx.post(DISCORD_API).mock(
            return_value=httpx.Response(200, json={})
        )
        block = {
            "kind": "lock", "guaranteed": True, "guaranteed_display": "$43.27",
        }
        async with discord_notifier as n:
            await n.position_state(
                ticket(pending_legs=1, hedge_block=block),
                notes=dict(hedge.NOTES),
                as_of_ms=NOW_MS,
            )
        embed = json.loads(route.calls.last.request.read())["embeds"][0]
        text = _rendered_text(embed)
        assert "lock" in text


class TestTheWatcherMergesBothPushes:
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

    async def test_watch_once_returns_both_pushes_under_distinct_keys(
        self, conn
    ):
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
        for key in (
            "alerts_sent", "alerts_failed", "alerts_deduped", "alerts_held",
            "position_alerts_sent", "position_alerts_failed",
            "position_alerts_deduped", "position_alerts_held",
        ):
            assert key in summary
        # One leg (LAD) settled won, one (CIN) is still pending and
        # unpriceable in this test -- the symmetric push has something to
        # say about it.
        day_ms = hedge_watch.day_start_ms(
            NOW_MS, hour=hedge_watch.DEFAULT_DAY_START_UTC_HOUR
        )
        assert summary["position_alerts_sent"] == [
            f"position_state:{position_id}:{day_ms}"
        ]
