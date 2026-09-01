"""The volume alarm: what it fires on, and what it refuses to guess.

The single most important test in this file is
`test_an_unreadable_volume_is_never_reported_as_zero_bytes_free`. On this
question a substituted `0` is not a benign default -- it is the *loudest*
reading, so a blind alarm and a working one would look identical from the
phone, and the first real alert would arrive in a channel already muted.

What these tests do NOT establish
---------------------------------
- **They do not exercise `os.statvfs`.** It does not exist on Windows, which is
  the laptop this repo is developed on, so `read_volume`'s success path is
  covered with a stub and its *absence* path is covered for real. What is
  pinned instead is the arithmetic -- that the expression matches
  `scripts/inspect_live_disk.py:capacity`, which is the reading taken by hand
  on the live box.
- **They do not establish that the thresholds are the right ones.** That is a
  judgement, argued in the constants' own comments and in
  `docs/adr/0095-the-volume-alarm-fires-on-free-bytes.md`. What is pinned here
  is that each threshold means the number of days it claims to mean, so the
  argument cannot quietly stop matching the number.
- **They do not establish that Discord will accept the embed.** The transport
  is faked, as in `tests/test_alerts.py`.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from backend.notify import discord
from backend.notify.alerts import (
    Alerter,
    FAILURE_KINDS,
    FAILURE_VOLUME_ACT,
    FAILURE_VOLUME_CRITICAL,
    FAILURE_VOLUME_NOTICE,
    VOLUME_TIER_ALERTS,
)
from backend.store import db, volume

DAY_MS = 86_400_000


def ms(iso: str) -> int:
    return int(
        datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000
    )


NOW = ms("2026-09-01T16:30:00")


class FakeNotifier:
    """Records `volume_filling` calls. `enabled` mirrors the real notifier."""

    def __init__(self, *, enabled: bool = True, delivers: bool = True):
        self._enabled = enabled
        self.delivers = delivers
        self.volume_alerts: list = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def volume_filling(self, title, **kwargs):
        self.volume_alerts.append((title, kwargs))
        return self.delivers


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "volume.db")
    yield c
    c.close()


def reading(free_bytes: int) -> volume.VolumeReading:
    return volume.VolumeReading(
        root="/data", total_bytes=5_248_090_112, free_bytes=free_bytes
    )


# ---------------------------------------------------------------------------
# The refusal. This is the one that matters.
# ---------------------------------------------------------------------------


class TestUnreadableIsNotZero:
    def test_an_unreadable_volume_is_never_reported_as_zero_bytes_free(self):
        """`read_volume` on a path that cannot be stat'd is `None`, not 0."""
        assert volume.read_volume("/no/such/path/anywhere") is None

    def test_a_platform_without_statvfs_reads_none_rather_than_zero(
        self, monkeypatch, tmp_path
    ):
        """Windows has no `os.statvfs` at all, and that is UNKNOWN, not full."""
        monkeypatch.delattr(volume.os, "statvfs", raising=False)
        assert volume.read_volume(str(tmp_path)) is None

    def test_classify_refuses_none_rather_than_calling_it_healthy(self):
        """A missing measurement is not a tier, and silently OK is the worst.

        `classify` raising is what makes the caller's `is None` branch
        impossible to skip. A `classify(None)` returning `TIER_OK` would be
        blindness that reads as health.
        """
        with pytest.raises(TypeError):
            volume.classify(None)

    async def test_an_unreadable_volume_claims_no_tier_and_sends_nothing(self, conn):
        notifier = FakeNotifier()
        sent = await Alerter(conn, notifier).check_volume(now_ms=NOW, reading=None)
        assert sent is None
        assert notifier.volume_alerts == []
        # And nothing was written to the ledger either: a claim with no send is
        # what `undelivered_last_24h` exists to catch, so an unreadable volume
        # must not leave one behind.
        assert conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# The thresholds mean what their comments say they mean.
# ---------------------------------------------------------------------------


class TestEachThresholdIsTheNumberOfDaysItClaims:
    """The comments beside the constants are the justification; pin them.

    Measured rate 161.40 MB/day, `n = 1 day`
    (`docs/measurements/2026-09-01-the-volume-clock.md` section 3).
    """

    def test_notice_is_about_ten_days_raw_and_nine_net_of_the_wal_reserve(self):
        r = reading(volume.NOTICE_FREE_BYTES)
        assert round(r.days_of_headroom, 2) == 9.91
        assert round(r.days_of_headroom_net_of_wal, 2) == 8.77

    def test_act_is_about_five_days_raw_and_under_four_net_of_the_wal_reserve(self):
        r = reading(volume.ACT_FREE_BYTES)
        assert round(r.days_of_headroom, 2) == 4.96
        assert round(r.days_of_headroom_net_of_wal, 2) == 3.82

    def test_critical_leaves_about_one_burst_night_once_the_wal_is_reserved(self):
        r = reading(volume.CRITICAL_FREE_BYTES)
        assert round(r.days_of_headroom, 2) == 2.48
        assert round(r.days_of_headroom_net_of_wal, 2) == 1.34

    def test_the_live_reading_of_2026_09_01_is_still_above_every_tier(self):
        """2,592,702,464 bytes free is 16.06 days and alarms nothing yet."""
        r = reading(2_592_702_464)
        assert volume.classify(r.free_bytes) == volume.TIER_OK
        assert round(r.days_of_headroom, 2) == 16.06

    def test_the_wal_reserve_is_the_largest_wal_the_record_has_seen(self):
        """179,731 KiB at 2026-08-31T23:30:14Z, inside the measured burst."""
        assert volume.WAL_RESERVE_BYTES == 179_731 * 1024
        # And the transport's own copy of it, in decimal MB, is the same
        # number. Two spellings, one figure.
        assert round(volume.WAL_RESERVE_BYTES / 1_000_000, 2) == discord.WAL_RESERVE_MB

    def test_the_tiers_are_ordered_loudest_first_so_the_walk_is_reachable(self):
        thresholds = [t for _, t in volume.TIERS]
        assert thresholds == sorted(thresholds)
        for tier, _ in volume.TIERS:
            assert tier in volume.TIER_SEVERITY


class TestClassifyPutsEachReadingInOneTier:
    @pytest.mark.parametrize(
        "free,expected",
        [
            (volume.CRITICAL_FREE_BYTES - 1, volume.TIER_CRITICAL),
            (0, volume.TIER_CRITICAL),
            (volume.CRITICAL_FREE_BYTES, volume.TIER_ACT),
            (volume.ACT_FREE_BYTES - 1, volume.TIER_ACT),
            (volume.ACT_FREE_BYTES, volume.TIER_NOTICE),
            (volume.NOTICE_FREE_BYTES - 1, volume.TIER_NOTICE),
            (volume.NOTICE_FREE_BYTES, volume.TIER_OK),
            (5_000_000_000, volume.TIER_OK),
        ],
    )
    def test_the_boundary_belongs_to_the_quieter_tier(self, free, expected):
        assert volume.classify(free) == expected


# ---------------------------------------------------------------------------
# Delivery: it reaches the same channel every other failure reaches.
# ---------------------------------------------------------------------------


class TestTheAlarmReachesThePhone:
    async def test_a_healthy_volume_sends_nothing(self, conn):
        notifier = FakeNotifier()
        sent = await Alerter(conn, notifier).check_volume(
            now_ms=NOW, reading=reading(2_592_702_464)
        )
        assert sent is None
        assert notifier.volume_alerts == []

    async def test_crossing_the_notice_threshold_sends_one_alert(self, conn):
        notifier = FakeNotifier()
        sent = await Alerter(conn, notifier).check_volume(
            now_ms=NOW, reading=reading(volume.NOTICE_FREE_BYTES - 1)
        )
        assert sent is True
        assert len(notifier.volume_alerts) == 1
        title, kwargs = notifier.volume_alerts[0]
        assert title == FAILURE_VOLUME_NOTICE
        assert kwargs["free_bytes"] == volume.NOTICE_FREE_BYTES - 1

    async def test_the_same_tier_twice_in_one_day_sends_once(self, conn):
        notifier = FakeNotifier()
        alerter = Alerter(conn, notifier)
        await alerter.check_volume(now_ms=NOW, reading=reading(1_500_000_000))
        await alerter.check_volume(now_ms=NOW + 900_000, reading=reading(1_400_000_000))
        assert len(notifier.volume_alerts) == 1

    async def test_the_same_tier_speaks_again_the_next_day(self, conn):
        notifier = FakeNotifier()
        alerter = Alerter(conn, notifier)
        await alerter.check_volume(now_ms=NOW, reading=reading(1_500_000_000))
        await alerter.check_volume(now_ms=NOW + DAY_MS, reading=reading(1_400_000_000))
        assert len(notifier.volume_alerts) == 2

    async def test_escalation_can_speak_on_a_day_that_already_alerted(self, conn):
        """The whole reason each tier is its own kind.

        A single kind would key on `kind:day`, send the first tier crossed and
        then go silent -- including on the day free space falls from "a week
        left" to "one burst left".
        """
        notifier = FakeNotifier()
        alerter = Alerter(conn, notifier)
        await alerter.check_volume(now_ms=NOW, reading=reading(1_500_000_000))
        await alerter.check_volume(now_ms=NOW + 1, reading=reading(700_000_000))
        await alerter.check_volume(now_ms=NOW + 2, reading=reading(300_000_000))
        assert [t for t, _ in notifier.volume_alerts] == [
            FAILURE_VOLUME_NOTICE,
            FAILURE_VOLUME_ACT,
            FAILURE_VOLUME_CRITICAL,
        ]

    async def test_a_disabled_notifier_makes_no_claim(self, conn):
        notifier = FakeNotifier(enabled=False)
        sent = await Alerter(conn, notifier).check_volume(
            now_ms=NOW, reading=reading(100)
        )
        assert sent is None
        assert conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 0

    async def test_the_byte_count_is_recorded_where_a_later_read_can_find_it(
        self, conn
    ):
        """`notifications.detail` is the instrument, and it is deliberate.

        The per-pass RSS log is the obvious other home for a free-byte series
        and section 10 of the volume clock is why it must not go there.
        """
        notifier = FakeNotifier()
        await Alerter(conn, notifier).check_volume(
            now_ms=NOW, reading=reading(1_234_567_890)
        )
        detail = conn.execute(
            "SELECT detail FROM notifications WHERE kind = 'failure'"
        ).fetchone()[0]
        assert "1234567890" in detail
        assert "/data" in detail


class TestTheCopyNamesTheRepairAPersonMustMake:
    """There is no in-process fix, so the message has to carry the command."""

    def test_every_tier_has_a_declared_failure_kind(self):
        for tier, (kind, guidance) in VOLUME_TIER_ALERTS.items():
            assert kind in FAILURE_KINDS, tier
            assert guidance.strip()

    def test_the_three_volume_kinds_are_declared_and_distinct(self):
        kinds = {
            FAILURE_VOLUME_NOTICE,
            FAILURE_VOLUME_ACT,
            FAILURE_VOLUME_CRITICAL,
        }
        assert len(kinds) == 3
        assert kinds <= set(FAILURE_KINDS)

    def test_the_alert_body_names_fly_volumes_extend(self):
        source = inspect.getsource(discord.DiscordNotifier.volume_filling)
        assert "fly volumes extend" in source
        assert "kalshi-cockpit" in source

    def test_the_alert_body_says_auto_extend_cannot_save_it(self):
        source = inspect.getsource(discord.DiscordNotifier.volume_filling)
        assert "ENOSPC" in source
        assert "5 GB limit" in source


class TestTheAlarmAndTheInspectorReadTheSameFreeBytes:
    """Two spellings of `f_bavail * f_frsize` would be two answers.

    `scripts/inspect_live_disk.py:capacity` is what was run by hand on the live
    box to produce 2,592,702,464; `volume.read_volume` is what the alarm fires
    on. If they ever disagree, the alarm is measuring something the measurement
    did not.
    """

    def test_both_use_f_bavail_rather_than_f_bfree(self):
        from scripts import inspect_live_disk

        for source in (
            inspect.getsource(inspect_live_disk.capacity),
            inspect.getsource(volume.read_volume),
        ):
            assert "f_bavail" in source
            assert "f_bfree" not in source.split('"""')[-1]

    def test_both_multiply_the_available_blocks_by_the_fragment_size(
        self, monkeypatch, tmp_path
    ):
        from scripts import inspect_live_disk

        class FakeStat:
            f_blocks = 1_281_272
            f_frsize = 4_096
            f_bavail = 632_984
            f_bfree = 700_000

        # `raising=False`: Windows has no `os.statvfs` to replace, which is
        # exactly why this test stubs it rather than calling the real one.
        monkeypatch.setattr(
            volume.os, "statvfs", lambda _root: FakeStat(), raising=False
        )
        monkeypatch.setattr(
            inspect_live_disk.os, "statvfs", lambda _root: FakeStat(), raising=False
        )
        mine = volume.read_volume(str(tmp_path))
        theirs = inspect_live_disk.capacity(str(tmp_path))
        assert mine is not None
        assert mine.free_bytes == theirs["free_bytes"]
        assert mine.total_bytes == theirs["total_bytes"]
        assert mine.used_bytes == theirs["used_bytes"]
        assert mine.used_pct == theirs["used_pct"]


class TestTheAlarmCannotDelete:
    """A disk alarm wired to a deletion is a guard that goes off at the worst
    possible moment. `backend/store/volume.py` must stay unable to reach one."""

    def test_the_volume_module_contains_no_deletion(self):
        source = inspect.getsource(volume)
        for forbidden in ("DELETE", "unlink", "remove(", "truncate", "rmtree"):
            assert forbidden not in source, forbidden

    def test_the_volume_module_does_not_import_the_downsample(self):
        source = inspect.getsource(volume)
        assert "fair_price_downsample" not in source.split('"""')[2]
