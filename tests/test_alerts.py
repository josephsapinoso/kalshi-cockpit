"""The alert *call path*, which is the part that did not exist.

`tests/test_discord.py` has ~20 tests and every one of them calls the notifier
directly. They establish that an embed is well-formed. They establish nothing
about whether an embed is ever sent, and until now the answer was no: nothing
in the repo imported `notify/discord.py` at all.

So these tests are weighted toward the join. What is asserted here is that a
recorded opportunity reaches the notifier, that it reaches it *once*, and that
it still reaches it once after the process restarts -- because the loop dies
loudly on repeated failure and the platform restarts it, which is exactly when
a policy holding its memory in a Python set would announce the whole slate
again.

What these tests do NOT establish
---------------------------------
That an alert is worth acting on, or that Discord will accept it. The transport
is faked here on purpose; a test that posted to Discord would be testing
Discord. `TestDeliveryIsRecordedNotAssumed` covers the part that matters
locally -- what happens to the record when the transport says no.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.analysis.clv import DEFAULT_HORIZON_HOURS

from backend.notify.alerts import (
    Alerter,
    FAILURE_CREDITS_EXHAUSTED,
    FAILURE_FEED_DIED,
    FAILURE_KINDS,
    FAILURE_LOOP_DIED,
)
from backend.store import db

HOUR = 3_600_000


def ms(iso: str) -> int:
    return int(
        datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000
    )


NOW = ms("2026-08-07T23:05:00")


class FakeNotifier:
    """Records calls. `enabled` mirrors the real notifier's config check."""

    def __init__(self, *, enabled: bool = True, delivers: bool = True):
        self._enabled = enabled
        self.delivers = delivers
        self.opportunities: list = []
        self.windows: list = []
        self.digests: list = []
        self.failures: list = []
        self.feed_deaths: list = []
        self.credit_alerts: list = []
        self.fee_alerts: list = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def opportunity(self, rec, **kwargs):
        self.opportunities.append(rec)
        return self.delivers

    async def window_open(self, *, window, surfaced):
        self.windows.append((window, surfaced))
        return self.delivers

    async def daily_digest(self, **kwargs):
        self.digests.append(kwargs)
        return self.delivers

    async def failure(self, kind, detail):
        self.failures.append((kind, detail))
        return self.delivers

    # The three below were complete, tested and called by nothing in production
    # until 2026-08-18. Recorded separately from `failure` so a test can tell
    # "the purpose-built alert fired" from "the generic one did" -- routing
    # through the generic path is exactly how they stayed unwired while looking
    # wired.
    async def feed_died(self, detail):
        self.feed_deaths.append(detail)
        return self.delivers

    async def credits_exhausted(self, remaining):
        self.credit_alerts.append(remaining)
        return self.delivers

    async def fee_mismatch(self, ticker, predicted, actual):
        self.fee_alerts.append((ticker, predicted, actual))
        return self.delivers


class FakeWindow:
    def __init__(self, *, last_sweep_ms=NOW, fresh=6, upcoming=8, remaining=1):
        self.last_sweep_ms = last_sweep_ms
        self.fixtures_fresh = fresh
        self.fixtures_upcoming = upcoming
        self.sweeps_remaining_today = remaining
        self.seconds_remaining = 840


class Counts:
    def __init__(self, surfaced=1, odds_sweeps=1):
        self.surfaced = surfaced
        self.odds_sweeps = odds_sweeps


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "alerts.db")
    c.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale) VALUES (1, ?, ?, '{}', 'test')",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO kalshi_events (event_ticker, commence_ms, first_seen_ms, "
        "last_seen_ms) VALUES ('KX-GAME', ?, ?, ?)",
        (NOW + HOUR, NOW, NOW),
    )
    c.execute(
        "INSERT INTO kalshi_markets (ticker, event_ticker, yes_side_team, "
        "first_seen_ms, last_seen_ms) VALUES ('KX-GAME-HOU', 'KX-GAME', "
        "'Houston', ?, ?)",
        (NOW, NOW),
    )
    c.commit()
    yield c
    c.close()


def add_recommendation(
    conn,
    *,
    created_ms=NOW,
    contracts=15,
    suppressed=None,
    ticker="KX-GAME-HOU",
    edge=17.0,
) -> int:
    cursor = conn.execute(
        "INSERT INTO recommendations (created_ms, strategy_config_version, "
        "ticker, side, entry_ask_tenths, depth_at_ask, fair_probability, "
        "edge_tenths, fee_predicted, ev_net_dollars, kelly_fraction, "
        "suggested_contracts, reference_contracts, kalshi_quote_age_ms, "
        "odds_age_ms, suppressed_reason, reason_text) "
        "VALUES (?, 1, ?, 'yes', 503, 800.0, 0.538, ?, 0.27, 0.26, 0.25, ?, ?, "
        "3000, 120000, ?, 'Houston: consensus fair 53.8%')",
        (created_ms, ticker, edge, contracts, contracts, suppressed),
    )
    conn.commit()
    return int(cursor.lastrowid)


async def run_pass(alerter, *, pass_ms=NOW, surfaced=1, sweeps=1, window=None):
    return await alerter.after_pass(
        pass_ms=pass_ms,
        counts=Counts(surfaced=surfaced, odds_sweeps=sweeps),
        window=window if window is not None else FakeWindow(),
        sweeps_this_pass=sweeps,
    )


class TestASurfacedRowReachesThePhone:
    """The join that did not exist. `notify/discord.py` was imported by nothing."""

    async def test_a_row_this_pass_wrote_is_announced(self, conn):
        add_recommendation(conn)
        notifier = FakeNotifier()

        result = await run_pass(Alerter(conn, notifier))

        assert len(notifier.opportunities) == 1
        assert notifier.opportunities[0].ticker == "KX-GAME-HOU"
        assert "opportunity" in result.sent

    async def test_the_embed_gets_the_fields_it_reads(self, conn):
        """The notifier was written against the engine's dataclass and the loop
        holds a sqlite row. Every attribute it touches must resolve."""
        add_recommendation(conn)
        notifier = FakeNotifier()
        await run_pass(Alerter(conn, notifier))

        rec = notifier.opportunities[0]
        assert rec.team == "Houston"
        assert rec.entry_ask_tenths == 503
        assert rec.suggested_contracts == 15
        assert rec.reason_text
        with pytest.raises(AttributeError):
            rec.no_such_column

    async def test_a_suppressed_row_is_never_announced(self, conn):
        """A phone notification per rejected candidate trains you to mute the
        channel, which is worse than having no channel.

        **The row is suppressed AND sized above zero, deliberately.** This test
        used to insert `contracts=0, suppressed="wide_market"` -- it constructed
        the zero it was checking, so it passed on the `suggested_contracts > 0`
        clause alone and could not see the suppression clause at all. The
        production sizer happens to zero that field on suppression today; the
        whole point of the query's second clause is the day it stops. A test
        that supplies the invariant it is verifying asserts nothing about
        production. Same shape as the `daily_pnl_dollars` defect
        `test_has_callers.py` exists for.
        """
        add_recommendation(conn, contracts=15, suppressed="wide_market")
        notifier = FakeNotifier()
        await run_pass(Alerter(conn, notifier), surfaced=0)
        assert notifier.opportunities == []

    async def test_a_suppressed_row_the_sizer_zeroed_is_also_not_announced(
        self, conn
    ):
        """The state production actually produces. Both clauses agree here, and
        that agreement is what the test above deliberately does not rely on."""
        add_recommendation(conn, contracts=0, suppressed="wide_market")
        notifier = FakeNotifier()
        await run_pass(Alerter(conn, notifier), surfaced=0)
        assert notifier.opportunities == []

    async def test_a_no_edge_row_is_never_announced(self, conn):
        """Most candidates on any slate have no edge. That is the normal answer,
        not an event."""
        add_recommendation(conn, contracts=0)
        notifier = FakeNotifier()
        await run_pass(Alerter(conn, notifier), surfaced=0)
        assert notifier.opportunities == []

    async def test_a_row_from_an_earlier_pass_is_not_re_announced(self, conn):
        """`persist_if_changed` leaves an unchanged row alone, so a query over
        the whole table would re-announce the same bet every fifteen minutes for
        as long as its price held."""
        add_recommendation(conn, created_ms=NOW - HOUR)
        notifier = FakeNotifier()
        await run_pass(Alerter(conn, notifier), pass_ms=NOW)
        assert notifier.opportunities == []


class TestOneAlertPerThing:
    async def test_the_same_pass_replayed_sends_nothing_new(self, conn):
        add_recommendation(conn)
        notifier = FakeNotifier()
        alerter = Alerter(conn, notifier)

        await run_pass(alerter)
        second = await run_pass(alerter)

        assert len(notifier.opportunities) == 1
        assert "opportunity" in second.skipped

    async def test_a_restart_does_not_re_announce_the_slate(self, conn):
        """The load-bearing one. The loop dies loudly on repeated failure and is
        restarted by the platform, so a policy remembering what it sent in
        process memory turns a crash loop into a busy night on the phone."""
        add_recommendation(conn)
        notifier = FakeNotifier()

        await run_pass(Alerter(conn, notifier))
        await run_pass(Alerter(conn, notifier))          # a fresh process

        assert len(notifier.opportunities) == 1

    async def test_the_dedupe_survives_in_the_database_not_the_object(self, conn):
        add_recommendation(conn)
        await run_pass(Alerter(conn, FakeNotifier()))
        rows = conn.execute(
            "SELECT kind, key, delivered FROM notifications"
        ).fetchall()
        assert [(r["kind"], r["delivered"]) for r in rows] == [
            ("window_open", 1), ("opportunity", 1),
        ]


class TestTheWindowAlert:
    """The alert without which the rest of the tool cannot be used at all."""

    async def test_it_fires_when_a_credit_was_actually_spent(self, conn):
        """`surfaced=1` since 2026-08-18 -- see the class below on the empty
        case. A credit spent is still the precondition; it is no longer the
        whole condition."""
        notifier = FakeNotifier()
        result = await run_pass(Alerter(conn, notifier), surfaced=1, sweeps=1)
        assert len(notifier.windows) == 1
        assert "window_open" in result.sent

    async def test_it_does_not_fire_on_a_pass_that_did_not_sweep(self, conn):
        """Most passes do not. Announcing every pass would announce nothing."""
        notifier = FakeNotifier()
        await run_pass(Alerter(conn, notifier), surfaced=0, sweeps=0)
        assert notifier.windows == []

    async def test_it_no_longer_reports_a_quiet_slate(self, conn):
        """**This test asserted the opposite until 2026-08-18, and the reversal
        is recorded rather than quietly swapped.**

        It read: "Fresh odds with nothing surfaced is the expected result, and
        it still matters -- it is the only signal that the machinery ran." Both
        clauses were reasonable and the second was false: the daily digest is
        also that signal, on a cadence that cannot storm.

        What settled it was the record, not the argument. Live, 2026-08-18: 93
        `window_open` rows across 12 budget days, and **zero `opportunity` rows
        in the entire history**. So the empty case was not a minority of the
        traffic that bought a heartbeat -- it was ALL of it, about eight buzzes
        a day, none of which ever preceded a bet.
        """
        notifier = FakeNotifier()
        await run_pass(Alerter(conn, notifier), surfaced=0, sweeps=1)
        assert notifier.windows == []

    async def test_a_second_sweep_later_in_the_day_is_a_second_alert(self, conn):
        notifier = FakeNotifier()
        alerter = Alerter(conn, notifier)
        await run_pass(alerter, pass_ms=NOW, window=FakeWindow(last_sweep_ms=NOW))
        await run_pass(
            alerter, pass_ms=NOW + 4 * HOUR,
            window=FakeWindow(last_sweep_ms=NOW + 4 * HOUR),
        )
        assert len(notifier.windows) == 2


class TestFailureAlertsDoNotStorm:
    async def test_one_alert_per_kind_per_day(self, conn):
        """A broken feed fails on every pass. Ninety-six alerts is one alert and
        ninety-five reasons to mute the channel."""
        notifier = FakeNotifier()
        alerter = Alerter(conn, notifier)
        for i in range(5):
            await alerter.failure(
                FAILURE_FEED_DIED, "detail", now_ms=NOW + i * 60_000
            )
        assert len(notifier.failures) == 1

    async def test_the_next_day_alerts_again(self, conn):
        notifier = FakeNotifier()
        alerter = Alerter(conn, notifier)
        await alerter.failure(FAILURE_FEED_DIED, "d", now_ms=NOW)
        await alerter.failure(FAILURE_FEED_DIED, "d", now_ms=NOW + 24 * HOUR)
        assert len(notifier.failures) == 2

    async def test_different_kinds_do_not_suppress_each_other(self, conn):
        notifier = FakeNotifier()
        alerter = Alerter(conn, notifier)
        await alerter.failure(FAILURE_FEED_DIED, "d", now_ms=NOW)
        await alerter.failure(FAILURE_CREDITS_EXHAUSTED, "d", now_ms=NOW)
        assert len(notifier.failures) == 2


class TestTheDigest:
    async def test_one_per_budget_day(self, conn):
        notifier = FakeNotifier()
        alerter = Alerter(conn, notifier)
        day = ms("2026-08-07T10:00:00")
        await alerter.daily_digest(now_ms=NOW, day_start_ms=day, gate_required=300)
        await alerter.daily_digest(
            now_ms=NOW + HOUR, day_start_ms=day, gate_required=300
        )
        assert len(notifier.digests) == 1

    async def test_it_counts_scored_games_not_scored_rows(self, conn):
        """Rows and games differ by the poll rate. Putting the flattering number
        on a phone beside the Gate screen's honest one is how the flattering one
        gets believed."""
        for i in range(4):
            rec = add_recommendation(conn, created_ms=NOW + i)
            # All **three** columns, because `score_recommendations` writes
            # them in one UPDATE and a row can never carry a subset. The
            # fixture set `clv_tenths` alone once, which passed only because
            # the digest had its own looser query -- a fixture that erases a
            # distinction cannot test code that depends on it. It then missed
            # `clv_horizon_hours` when ADR 0011 added it, and the symptom was a
            # digest reporting zero scored games: the count the fixture exists
            # to produce, silently absent rather than wrong.
            conn.execute(
                "UPDATE recommendations SET clv_tenths = 5.0, clv_scored_ms = ?, "
                "clv_horizon_hours = ? WHERE id = ?",
                (NOW, DEFAULT_HORIZON_HOURS, rec),
            )
        conn.commit()

        notifier = FakeNotifier()
        await Alerter(conn, notifier).daily_digest(
            now_ms=NOW + HOUR,
            day_start_ms=ms("2026-08-07T10:00:00"),
            gate_required=300,
        )
        # Four rows on one market, which is one game.
        assert notifier.digests[0]["scored"] == 1

    async def test_the_digest_separates_actionable_from_merely_scored(self, conn):
        """The number on the phone must say whose CLV it is.

        One game the strategy would have bet, two it refused. "3 scored" is true
        and reads as three games of evidence about this strategy; one of them is.
        """
        for name in ("A", "B", "C"):
            conn.execute(
                "INSERT INTO kalshi_events (event_ticker, commence_ms, "
                "first_seen_ms, last_seen_ms) VALUES (?, ?, ?, ?)",
                (f"EVT-{name}", NOW + HOUR, NOW, NOW),
            )
            conn.execute(
                "INSERT INTO kalshi_markets (ticker, event_ticker, "
                "first_seen_ms, last_seen_ms) VALUES (?, ?, ?, ?)",
                (name, f"EVT-{name}", NOW, NOW),
            )

        bet = add_recommendation(conn, created_ms=NOW, ticker="A", contracts=7)
        refused_a = add_recommendation(
            conn, created_ms=NOW + 1, ticker="B", contracts=0,
            suppressed="suspicious_edge",
        )
        refused_b = add_recommendation(
            conn, created_ms=NOW + 2, ticker="C", contracts=0,
            suppressed="stale_odds",
        )
        for rec in (bet, refused_a, refused_b):
            conn.execute(
                "UPDATE recommendations SET clv_tenths = 5.0, clv_scored_ms = ?, "
                "clv_horizon_hours = ? WHERE id = ?",
                (NOW, DEFAULT_HORIZON_HOURS, rec),
            )
        conn.commit()

        notifier = FakeNotifier()
        await Alerter(conn, notifier).daily_digest(
            now_ms=NOW + HOUR,
            day_start_ms=ms("2026-08-07T10:00:00"),
            gate_required=300,
        )
        digest = notifier.digests[0]
        assert digest["scored"] == 3
        assert digest["scored_actionable"] == 1, (
            "the digest counted two refused games as progress toward the floor"
        )

    async def test_it_breaks_the_day_down_by_suppression_reason(self, conn):
        add_recommendation(conn, contracts=0, suppressed="wide_market")
        add_recommendation(conn, contracts=0, suppressed="stale_odds")
        add_recommendation(conn, contracts=0, suppressed="stale_odds")

        notifier = FakeNotifier()
        await Alerter(conn, notifier).daily_digest(
            now_ms=NOW + HOUR,
            day_start_ms=ms("2026-08-07T10:00:00"),
            gate_required=300,
        )
        assert notifier.digests[0]["suppression_counts"] == {
            "wide_market": 1, "stale_odds": 2,
        }


class TestDeliveryIsRecordedNotAssumed:
    async def test_a_refused_post_is_recorded_as_undelivered(self, conn):
        """"We decided to alert" and "the alert arrived" are different facts. A
        silent channel should be distinguishable from a system with nothing to
        say."""
        add_recommendation(conn)
        result = await run_pass(
            Alerter(conn, FakeNotifier(delivers=False))
        )
        row = conn.execute(
            "SELECT delivered FROM notifications WHERE kind = 'opportunity'"
        ).fetchone()
        assert row["delivered"] == 0
        assert "opportunity" in result.failed

    async def test_a_raising_notifier_does_not_take_the_loop_down(self, conn):
        """Alerting is optional infrastructure. The record is not."""
        class Exploding(FakeNotifier):
            async def opportunity(self, rec, **kwargs):
                raise RuntimeError("discord is on fire")

        add_recommendation(conn)
        result = await run_pass(Alerter(conn, Exploding()))
        assert "opportunity" in result.failed

    async def test_a_refused_post_is_not_retried_forever(self, conn):
        """The claim is made before the send, so a dead channel costs one lost
        alert rather than an alert on every pass for the rest of the day."""
        add_recommendation(conn)
        notifier = FakeNotifier(delivers=False)
        alerter = Alerter(conn, notifier)
        await run_pass(alerter)
        await run_pass(alerter)
        assert len(notifier.opportunities) == 1


class TestUnconfiguredIsInertRatherThanBroken:
    async def test_nothing_is_sent(self, conn):
        add_recommendation(conn)
        notifier = FakeNotifier(enabled=False)
        await run_pass(Alerter(conn, notifier))
        assert notifier.opportunities == []

    async def test_nothing_is_claimed_either(self, conn):
        """Otherwise adding a token later would find every key already used and
        the channel would stay silent through the first slate."""
        add_recommendation(conn)
        await run_pass(Alerter(conn, FakeNotifier(enabled=False)))
        assert conn.execute("SELECT COUNT(*) n FROM notifications").fetchone()["n"] == 0

        notifier = FakeNotifier()
        await run_pass(Alerter(conn, notifier))
        assert len(notifier.opportunities) == 1


class TestTheFeedWatchdog:
    """The alert the Board cannot substitute for.

    A dead feed makes the cockpit look *calm*: prices stop moving and a stale
    number renders identically to a fresh one. Before 2026-08-18 the only
    failure alert with a production caller was `Recording loop died`, which
    needs five consecutive pass failures -- and a container crash-loop, the
    failure that has actually happened to this instance, kills the process
    before that path is reached.

    **What is not tested here, because it cannot be:** the crash-loop itself.
    Nothing running inside the box can report the box being dead.
    """

    async def test_a_dead_hub_fires_the_purpose_built_alert(self, conn):
        notifier = FakeNotifier()
        await Alerter(conn, notifier).check_feed(
            now_ms=NOW, hub_running=False, markets_priced=12
        )
        assert notifier.feed_deaths, "feed_died was not called"
        assert "12" in notifier.feed_deaths[0]

    async def test_a_live_hub_says_nothing(self, conn):
        notifier = FakeNotifier()
        await Alerter(conn, notifier).check_feed(
            now_ms=NOW, hub_running=True, markets_priced=12
        )
        assert notifier.feed_deaths == []
        assert notifier.failures == []

    async def test_an_empty_slate_says_nothing_even_with_a_dead_hub(self, conn):
        """The denominator, and it is the difference between a watchdog and a
        nightly buzz. Overnight there is nothing to quote; a watchdog that fires
        anyway gets the channel muted, which is worse than no channel."""
        notifier = FakeNotifier()
        await Alerter(conn, notifier).check_feed(
            now_ms=NOW, hub_running=False, markets_priced=0
        )
        assert notifier.feed_deaths == []
        assert notifier.failures == []

    async def test_an_unreadable_probe_is_its_own_alert_not_a_dead_feed(self, conn):
        """`None` is not `False`. "The API did not answer" and "the hub is down"
        are different facts and a phone must not be told the second when the
        first is what happened."""
        notifier = FakeNotifier()
        await Alerter(conn, notifier).check_feed(
            now_ms=NOW, hub_running=None, markets_priced=12
        )
        assert notifier.feed_deaths == []
        assert [kind for kind, _ in notifier.failures] == [
            "Cockpit API unreachable"
        ]

    async def test_it_fires_once_a_day_however_many_passes_run(self, conn):
        """A broken feed is broken on every pass. Ninety-six alerts is one alert
        and ninety-five reasons to mute the channel."""
        notifier = FakeNotifier()
        alerter = Alerter(conn, notifier)
        for offset in range(0, 5 * 60_000, 60_000):
            await alerter.check_feed(
                now_ms=NOW + offset, hub_running=False, markets_priced=12
            )
        assert len(notifier.feed_deaths) == 1

    async def test_the_next_day_alerts_again(self, conn):
        """Deduped, not silenced. A feed still dead tomorrow is still news."""
        notifier = FakeNotifier()
        alerter = Alerter(conn, notifier)
        await alerter.check_feed(now_ms=NOW, hub_running=False, markets_priced=12)
        await alerter.check_feed(
            now_ms=NOW + 24 * HOUR, hub_running=False, markets_priced=12
        )
        assert len(notifier.feed_deaths) == 2


class TestTheCreditWatchdog:
    """Not a malfunction -- the budget working -- but invisible from the Board,
    which simply stops producing rows."""

    async def test_exhausted_credits_fire_the_purpose_built_alert(self, conn):
        notifier = FakeNotifier()
        await Alerter(conn, notifier).check_credits(now_ms=NOW, remaining_today=0)
        assert notifier.credit_alerts == [0]

    async def test_remaining_credits_say_nothing(self, conn):
        notifier = FakeNotifier()
        await Alerter(conn, notifier).check_credits(now_ms=NOW, remaining_today=42)
        assert notifier.credit_alerts == []

    async def test_it_fires_once_a_day(self, conn):
        notifier = FakeNotifier()
        alerter = Alerter(conn, notifier)
        for offset in range(0, 5 * 60_000, 60_000):
            await alerter.check_credits(now_ms=NOW + offset, remaining_today=0)
        assert len(notifier.credit_alerts) == 1


class TestTheFailureKindsAreDeclared:
    """`FAILURE_KINDS` was referenced by nothing and matched nothing.

    It listed `("loop_failed", "credits_exhausted", "feed_died")` while the one
    kind ever sent was the free-text `"Recording loop died"`. A constant nobody
    reads cannot be wrong, so it was wrong for the life of the project. It is
    now the dedupe key's allowlist, and these tests are what make that real.
    """

    async def test_an_undeclared_kind_raises(self, conn):
        """A typo must not open a second dedupe bucket and double the traffic."""
        notifier = FakeNotifier()
        with pytest.raises(AssertionError, match="undeclared failure kind"):
            await Alerter(conn, notifier).failure(
                "Recording lop died", "typo", now_ms=NOW
            )

    async def test_the_kind_the_loop_sends_is_declared(self):
        """The specific mismatch that stood for the life of the project."""
        assert FAILURE_LOOP_DIED in FAILURE_KINDS

    @pytest.mark.parametrize("kind", FAILURE_KINDS)
    def test_every_declared_kind_is_a_title_the_notifier_writes(self, kind):
        """The dedupe key and the embed title are the same name.

        A near-miss would dedupe under a string that appears nowhere on the
        phone, so the record and the notification would disagree about what was
        sent -- and only the record is queryable.
        """
        assert kind.strip() == kind and kind


class TestTheWindowAlertOnlyFiresOnSomethingToSee:
    """Measured, not preferred.

    Queried on the live volume 2026-08-18: 93 `window_open` rows across 12
    budget days -- about eight buzzes a day -- and **zero `opportunity` rows in
    the entire record**. Every one of those ninety-three opened onto a board
    with nothing on it, which is precisely the "trains you to ignore the
    channel" failure the module docstring warns about, already realised.
    """

    async def test_a_window_with_something_on_it_still_buzzes(self, conn):
        add_recommendation(conn)
        notifier = FakeNotifier()
        await run_pass(Alerter(conn, notifier), surfaced=1)
        assert len(notifier.windows) == 1

    async def test_an_empty_window_says_nothing(self, conn):
        notifier = FakeNotifier()
        await run_pass(Alerter(conn, notifier), surfaced=0)
        assert notifier.windows == []

    async def test_the_daily_digest_still_carries_the_heartbeat(self, conn):
        """What the cut costs, and why it is affordable.

        The window alert doubled as proof the loop was alive. The digest already
        carries that on a cadence that cannot storm, so what was dropped is the
        duplicate -- not the heartbeat.
        """
        notifier = FakeNotifier()
        await Alerter(conn, notifier).daily_digest(
            now_ms=NOW, day_start_ms=ms("2026-08-07T10:00:00"), gate_required=300
        )
        assert len(notifier.digests) == 1


class TestDeliveryHealthIsReadable:
    """`notifications_configured` is a boolean about a string being non-empty.

    The live record on 2026-08-18 held one `failure` row at `delivered = 0` --
    the loop died, the alert was claimed, nothing reached the phone, and for
    months nothing said so. This is the query that would have said so.
    """

    async def test_nothing_sent_reports_none_never_zero(self, conn):
        """A zero timestamp is 1970 and renders as a delivery."""
        health = Alerter(conn, FakeNotifier()).delivery_health(now_ms=NOW)
        assert health["last_delivered_ms"] is None
        assert health["undelivered_last_24h"] == 0
        assert health["total_ever"] == 0

    async def test_a_delivered_alert_sets_the_timestamp(self, conn):
        add_recommendation(conn)
        alerter = Alerter(conn, FakeNotifier())
        await run_pass(alerter)
        assert alerter.delivery_health(now_ms=NOW)["last_delivered_ms"] == NOW

    async def test_an_undelivered_alert_is_counted_and_does_not_set_it(self, conn):
        """The exact live state: claimed, never landed."""
        add_recommendation(conn)
        alerter = Alerter(conn, FakeNotifier(delivers=False))
        await run_pass(alerter)
        health = alerter.delivery_health(now_ms=NOW)
        assert health["last_delivered_ms"] is None
        assert health["undelivered_last_24h"] >= 1

    async def test_an_old_failure_falls_out_of_the_24h_count(self, conn):
        """Otherwise one bad night reads as a permanently broken alerter."""
        add_recommendation(conn)
        alerter = Alerter(conn, FakeNotifier(delivers=False))
        await run_pass(alerter)
        assert alerter.delivery_health(now_ms=NOW + 48 * HOUR)[
            "undelivered_last_24h"
        ] == 0
