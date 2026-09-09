"""Free bytes on the volume, and the thresholds worth waking someone for.

Why this exists
---------------
`auto_extend_size_limit = "5GB"` (`fly.live.toml:607`) has been reached, so the
net that caught the 2026-08-16 volume-full incident **cannot fire again**. Any
further growth ends in `ENOSPC` -- a hard down that a restart does not clear --
and the recovery is a manual `fly volumes extend` from a laptop. That is a
repair only a person can make, which makes an alarm the whole intervention:
nothing on this box can fix it, so the only thing worth building is the thing
that tells someone in time.

`docs/measurements/2026-09-01-the-volume-clock.md` puts the fill at about
2026-09-17, at 161.40 MB/day against 2,592,702,464 bytes free. That was
`n = 1 day` -- one 24-hour window, one MLB evening slate, one growth burst --
and §6 of that document says the line is a **floor rather than a centre**:
NCAAF and NFL enter the feed with no config change
(`backend/kalshi/discovery.py:237-238`), and an NFL Sunday is a ~10-hour
in-play window against MLB's ~4.

**That rate has already been superseded once, which is the reason this module
now has exactly one place to correct it rather than several.** Re-measured
2026-09-09 over `n = 8.138 days` on the live volume, the realised rate was
326.6 MB/day -- 2.0x the 2026-08-01 floor. `CURRENT_GROWTH_RATE` below is that
number, carrying its own measurement date and `n` so a future reader does not
have to trust a bare float. **When it next moves -- the `fair_prices`
write-dedupe landing in another lane is expected to cut it to roughly
142 MB/day by removing ~99.7% of that table's rows -- correcting it here is
the whole fix.** Every days-of-headroom figure this module computes and every
duration `notify/alerts.py` puts in front of Joe is derived from this one
constant at import time; none of them are typed twice.
`tests/test_volume_alarm.py::TestHeadroomDerivesFromOneConfiguredRate` pins
that derivation and fails if a duration is ever hand-typed back in instead.

**It fires on free bytes, never on a projected date, and the reason is the
rate's own caveat.** A projected date built on the rate inherits every one of
its unknowns. Free bytes inherit none of them: `statvfs` is a measurement of
the present, and the threshold is a comparison rather than a model.

The rate is still used, but only in one direction: to *express* a threshold in
days so the choice of number can be argued with. If the rate is wrong the
thresholds still fire at the free-byte level they name; only the stated
duration is wrong, and correcting `CURRENT_GROWTH_RATE` is what fixes it
everywhere it is quoted.

What this does NOT establish
----------------------------
- **It does not establish that `ENOSPC` arrives when free reaches 0.** SQLite
  can fail to write with bytes still free -- WAL extension, a temp file, an
  index build. §4 of the volume clock reserves 184.04 MB for exactly that,
  because the WAL reached 179,731 KiB during the measured burst. Every
  threshold below is quoted twice for that reason: once on raw free space and
  once net of that reserve.
- **It does not measure a rate.** One `statvfs` is a level. The days-of-headroom
  figures are that level divided by `CURRENT_GROWTH_RATE`, which is measured
  elsewhere and only configured here.
- **It says nothing about what to delete.** It reports; it never deletes, and
  nothing here is wired to anything that does. An automatic deletion fired by a
  disk alarm is a guard that goes off at the worst possible moment -- see
  `backend/store/fair_price_downsample.py`, which is deliberately not reachable
  from this module.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

#: The live volume's mount point (`fly.live.toml:556`).
DEFAULT_ROOT = "/data"


@dataclass(frozen=True)
class GrowthRate:
    """A growth-rate measurement, carrying the provenance that makes it
    arguable rather than a bare float.

    **This is the shape a correction takes.** `bytes_per_day` alone is a
    number nobody can audit; `measured_on` and `window_days` are what let a
    future reader ask "how many nights was that" before trusting it -- the
    same question §6 of the volume clock asks of the 2026-09-01 figure this
    one superseded.
    """

    bytes_per_day: float
    measured_on: str
    window_days: float
    note: str


#: The rate the module's whole day-of-headroom arithmetic runs on, and the
#: **one place** to correct it. Every duration this module computes, and every
#: duration `notify/alerts.py`'s volume-tier guidance states, is derived from
#: this constant at import time -- see `tier_headroom_days()` below and
#: `alerts._volume_tier_alerts()`. Changing the number here is the whole fix;
#: nothing else needs to change and nothing else should be hand-edited to
#: match it.
#:
#: Measured 2026-09-09 on the live volume's `db_kb + wal_kb` footprint over
#: `n = 8.138 days`: 326.6 MB/day, 2.0x the 2026-08-01 `n = 1` floor of
#: 161.40 MB/day (`docs/measurements/2026-09-01-the-volume-clock.md`), which
#: this supersedes. Expected to move again -- another lane's `fair_prices`
#: write-dedupe is projected to cut realised growth to roughly 142 MB/day by
#: removing ~99.7% of that table's rows -- and when it does, this is the only
#: line that needs editing.
CURRENT_GROWTH_RATE = GrowthRate(
    bytes_per_day=326_600_000.0,
    measured_on="2026-09-09",
    window_days=8.138,
    note=(
        "db_kb + wal_kb footprint, realised growth on the live volume; "
        "supersedes the 2026-09-01 n=1 measurement of 161.40 MB/day."
    ),
)

#: The largest WAL this record has ever seen: 179,731 KiB at
#: 2026-08-31T23:30:14Z, inside the measured burst, on a `TRUNCATE` checkpoint
#: reporting `busy = 1`. The last this many bytes of free space are not
#: available to `cockpit.db` -- they are the space the writer needs in order to
#: commit at all. Every threshold below is justified both ways.
WAL_RESERVE_BYTES = 179_731 * 1024  # 184,044,544

TIER_OK = "ok"
TIER_NOTICE = "notice"
TIER_ACT = "act"
TIER_CRITICAL = "critical"

#: Chosen so the alarm reaches a person who is *away*. The repair is a laptop
#: command, so the useful question is not "how long until it breaks" but "how
#: long until someone is next in front of a laptop". It is also the tier that
#: fires **early if the rate doubles**: NCAAF and NFL enter the feed on the
#: sports calendar rather than on a deploy.
#:
#: **The exact days-of-headroom this threshold buys are not restated here.**
#: They move every time `CURRENT_GROWTH_RATE` is corrected, and a number typed
#: beside this constant would go stale silently the next time that happens --
#: which is the defect this module was rebuilt to remove. Call
#: `tier_headroom_days()[TIER_NOTICE]` for the current `(raw, net)` figure, or
#: read the value `notify/alerts.py` puts in front of Joe, which is the same
#: computation.
NOTICE_FREE_BYTES = 1_600_000_000

#: Below this the straight line stops being a comfort. §6 of the volume clock
#: names two ways the rate rises inside a five-day span and none by which it
#: falls before the fill date -- MLB's regular season ends after every date in
#: the table, and the postseason follows it.
#:
#: See `tier_headroom_days()[TIER_ACT]` for the current days-of-headroom this
#: threshold buys; not restated here for the reason given beside
#: `NOTICE_FREE_BYTES`.
ACT_FREE_BYTES = 800_000_000

#: Four hours of in-play carried 99.51% of the measured 2026-09-01 burst day,
#: the largest single hour 34.90% (53.88 MiB) -- a fact about how bursty a
#: slate is, not about the configured rate, so it does not go stale when the
#: rate is corrected. At this level a single evening slate can take the rest,
#: and the reserve is what stands between the last write and a hard down.
#: This is the tier that means: stop what you are doing and extend the volume.
#:
#: See `tier_headroom_days()[TIER_CRITICAL]` for the current days-of-headroom
#: this threshold buys.
CRITICAL_FREE_BYTES = 400_000_000

#: Descending, because `classify` walks it and returns the first match. Kept as
#: one ordered tuple rather than a chain of `elif`s so that a tier added out of
#: order is a visible reordering rather than an unreachable branch.
TIERS: tuple[tuple[str, int], ...] = (
    (TIER_CRITICAL, CRITICAL_FREE_BYTES),
    (TIER_ACT, ACT_FREE_BYTES),
    (TIER_NOTICE, NOTICE_FREE_BYTES),
)

#: Loudest first. The alerter uses this to decide which single tier to send when
#: several are crossed at once.
TIER_SEVERITY = (TIER_CRITICAL, TIER_ACT, TIER_NOTICE, TIER_OK)


def tier_headroom_days(
    rate: GrowthRate = CURRENT_GROWTH_RATE,
) -> dict[str, tuple[float, float]]:
    """`{tier: (raw_days, net_of_wal_days)}` at `rate`, defaulting to the
    configured `CURRENT_GROWTH_RATE`.

    **This is the single source of every duration anyone states about the
    volume alarm.** `notify/alerts.py` builds its Discord copy by calling this
    -- not by having its own opinion of how many days a tier buys -- so a
    correction to `rate` reaches the phone without a second edit. The
    docstrings beside `NOTICE_FREE_BYTES`, `ACT_FREE_BYTES` and
    `CRITICAL_FREE_BYTES` point here rather than hand-typing a figure for the
    same reason.

    Takes `rate` as a parameter, rather than only reading the module constant,
    so the arithmetic itself -- "a threshold's headroom is the threshold
    divided by the rate, net figure minus the WAL reserve first" -- can be
    exercised at a rate other than today's and shown to hold generally. See
    `tests/test_volume_alarm.py::TestHeadroomDerivesFromOneConfiguredRate`.
    """
    return {
        tier: (
            threshold / rate.bytes_per_day,
            (threshold - WAL_RESERVE_BYTES) / rate.bytes_per_day,
        )
        for tier, threshold in TIERS
    }


@dataclass(frozen=True)
class VolumeReading:
    """One `statvfs`. A level, never a rate.

    There is no `VolumeReading` that means "unreadable": `read_volume` returns
    `None` for that, so a caller cannot accidentally hold an object whose
    `free_bytes` is a substituted zero. This repo's recurring defect is a
    missing measurement rendering as the number 0, and on this particular
    question a zero reads as *the worst possible state*, which is the one
    direction that looks like the alarm working while it is blind.
    """

    root: str
    total_bytes: int
    free_bytes: int

    @property
    def used_bytes(self) -> int:
        return self.total_bytes - self.free_bytes

    @property
    def used_pct(self) -> Optional[float]:
        if not self.total_bytes:
            return None
        return round(100.0 * self.used_bytes / self.total_bytes, 2)

    @property
    def days_of_headroom(self) -> float:
        """Free bytes at `CURRENT_GROWTH_RATE`. Moves when that constant does."""
        return self.free_bytes / CURRENT_GROWTH_RATE.bytes_per_day

    @property
    def days_of_headroom_net_of_wal(self) -> float:
        """The same, less the largest WAL the record has seen. Can be negative."""
        return (
            (self.free_bytes - WAL_RESERVE_BYTES) / CURRENT_GROWTH_RATE.bytes_per_day
        )

    def as_dict(self) -> dict:
        return {
            "root": self.root,
            "total_bytes": self.total_bytes,
            "free_bytes": self.free_bytes,
            "used_pct": self.used_pct,
            "days_of_headroom": round(self.days_of_headroom, 2),
        }


def read_volume(root: str = DEFAULT_ROOT) -> Optional[VolumeReading]:
    """Free space on the filesystem holding `root`, or `None` if it cannot be read.

    **`f_bavail`, not `f_bfree`**, and the reason is not stylistic: the
    difference is the reserve only root may use, and the process that would hit
    `ENOSPC` does not run as root (`Dockerfile` runs non-root). `f_bfree` would
    report space the writer cannot actually have, which is the flattering
    direction on the exact question of why a write failed. This is the same
    choice `scripts/inspect_live_disk.py:capacity` makes, and
    `tests/test_volume_alarm.py` pins the two expressions equal so they cannot
    drift into two answers.

    **`None` on any failure, never a substituted 0.** `os.statvfs` does not
    exist on Windows at all (this repo is developed on one) and raises `OSError`
    on a missing or unreadable path. A `0` here would render as "no free space",
    which fires the loudest alarm on a box that may be perfectly healthy -- and
    trains the reader to ignore the channel, which is the failure this whole
    module exists to avoid. Every caller must branch on `None` explicitly;
    `classify` refuses to accept it.
    """
    statvfs = getattr(os, "statvfs", None)
    if statvfs is None:
        logger.warning(
            "volume: os.statvfs is unavailable on this platform; free space on "
            "%s is UNKNOWN, not zero.", root,
        )
        return None
    try:
        st = statvfs(root)
    except OSError as exc:
        logger.warning(
            "volume: could not statvfs %s (%s); free space is UNKNOWN, not "
            "zero.", root, exc,
        )
        return None
    return VolumeReading(
        root=root,
        total_bytes=st.f_blocks * st.f_frsize,
        free_bytes=st.f_bavail * st.f_frsize,
    )


def classify(free_bytes: int) -> str:
    """Which tier `free_bytes` is in. Always one of the four `TIER_*` strings.

    **It refuses `None` rather than treating it as any tier**, including the
    critical one. An unreadable volume is not a full volume and it is not an
    empty one; it is an absent measurement, and the caller has to say what it
    does about that. Raising is what makes the refusal impossible to skip --
    a `classify(None)` that returned `TIER_OK` would be silent blindness and a
    `classify(None)` that returned `TIER_CRITICAL` would be a permanent false
    alarm on a laptop.
    """
    if free_bytes is None:
        raise TypeError(
            "classify() refuses None: an unreadable volume is not a tier. "
            "Branch on read_volume() returning None at the call site."
        )
    for tier, threshold in TIERS:
        if free_bytes < threshold:
            return tier
    return TIER_OK
