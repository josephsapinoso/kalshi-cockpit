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
2026-09-17, at 161.40 MB/day against 2,592,702,464 bytes free.

**It fires on free bytes, never on that date, and the reason is the date's own
caveat.** The rate is `n = 1 day` -- one 24-hour window, one MLB evening slate,
one growth burst -- and §6 of that document says the line is a **floor rather
than a centre**: NCAAF and NFL enter the feed with no config change
(`backend/kalshi/discovery.py:237-238`), and an NFL Sunday is a ~10-hour in-play
window against MLB's ~4. A projected date built on that rate inherits every one
of its unknowns. Free bytes inherit none of them: `statvfs` is a measurement of
the present, and the threshold is a comparison rather than a model.

The rate is still used, but only in one direction: to *express* a threshold in
days so the choice of number can be argued with. If the rate is wrong the
thresholds still fire at the free-byte level they name; only the sentence
"about nine days" is wrong, and it is wrong in the direction of firing too
early, because the measured rate is a floor.

What this does NOT establish
----------------------------
- **It does not establish that `ENOSPC` arrives when free reaches 0.** SQLite
  can fail to write with bytes still free -- WAL extension, a temp file, an
  index build. §4 of the volume clock reserves 184.04 MB for exactly that,
  because the WAL reached 179,731 KiB during the measured burst. Every
  threshold below is quoted twice for that reason: once on raw free space and
  once net of that reserve.
- **It does not measure a rate.** One `statvfs` is a level. The days-of-headroom
  figures are that level divided by a rate measured elsewhere, on one day.
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

#: The measured growth rate, 2026-09-01, on the `db_kb + wal_kb` footprint over
#: one clean 24-hour window. **`n = 1 day.`** Decimal MB, matching the source
#: document: 161.40 MB/day.
#:
#: Used only to translate a byte threshold into a number of days for the comment
#: beside it and for the alert copy. Nothing branches on it.
REFERENCE_GROWTH_BYTES_PER_DAY = 161_400_000

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

#: 9.91 days of raw headroom at the reference rate; **8.77 days** once
#: `WAL_RESERVE_BYTES` is taken out.
#:
#: Chosen so the alarm reaches a person who is *away*. The repair is a laptop
#: command, so the useful question is not "how long until it breaks" but "how
#: long until someone is next in front of a laptop", and a week plus a day and a
#: half of slack is the honest answer to that. It is also the tier that fires
#: **early if the rate doubles**: NCAAF and NFL enter the feed on the sports
#: calendar rather than on a deploy, and a doubled rate reaches this level in
#: half the nominal time while still leaving four days.
NOTICE_FREE_BYTES = 1_600_000_000

#: 4.96 days raw; **3.82 days** net of the WAL reserve.
#:
#: Below this the straight line stops being a comfort. §6 of the volume clock
#: names two ways the rate rises inside a five-day span and none by which it
#: falls before the fill date -- MLB's regular season ends after every date in
#: the table, and the postseason follows it. Five days is about one football
#: weekend plus the working days either side of it, so this is the last tier at
#: which "extend it when convenient" is still a true sentence.
ACT_FREE_BYTES = 800_000_000

#: 2.48 days raw; **1.34 days** net of the WAL reserve -- which is to say, one
#: burst night of actual runway.
#:
#: Four hours of in-play carried 99.51% of the measured day, the largest single
#: hour 34.90% (53.88 MiB). At this level a single evening slate can take the
#: rest, and the reserve is what stands between the last write and a hard down.
#: This is the tier that means: stop what you are doing and extend the volume.
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
        """Free bytes at the reference rate. **`n = 1 day`, and a floor.**"""
        return self.free_bytes / REFERENCE_GROWTH_BYTES_PER_DAY

    @property
    def days_of_headroom_net_of_wal(self) -> float:
        """The same, less the largest WAL the record has seen. Can be negative."""
        return (self.free_bytes - WAL_RESERVE_BYTES) / REFERENCE_GROWTH_BYTES_PER_DAY

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
