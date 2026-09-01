# ADR DRAFT — The volume alarm fires on free bytes, not on a projected date

- **Status:** Accepted. The ordinal is assigned at merge; 0094 is taken.
- **Date:** 2026-09-01
- **Related:** `docs/measurements/2026-09-01-the-volume-clock.md` (the
  measurement this responds to), ADR 0054 (the 2026-08-16 volume-full incident
  and the extend that followed it), and the sibling draft
  `DRAFT-fair-prices-is-downsampled-to-daily-behind-a-flag.md`, which is the
  *other* half and is deliberately not armed.

## 1. What is true, and why it needs an alarm rather than a fix

The live volume fills about **2026-09-17** at 161.40 MB/day against
**2,592,702,464 bytes** actually free. `auto_extend_size_limit = "5GB"`
(`fly.live.toml:607`) has already been reached, so the net that caught the
2026-08-16 incident **cannot fire again**. Past the last byte this is `ENOSPC`,
which is a hard down that a restart does not clear, and the recovery is a
manual `fly volumes extend` from a laptop.

**Nothing running inside the box can make that repair.** So the alarm is not a
step toward the fix; it *is* the whole intervention this lane can build. That
framing decides everything below: the only question worth optimising is whether
a person hears it early enough to be at a laptop.

## 2. The decision: fire on `statvfs` free bytes, never on a projected date

The obvious design is to alarm at the projected fill date, or at a `db_kb`
level, which is what the source measurement's own "Proposed alarm" section
sketches. **Both were rejected, and for the same reason.**

A projected date inherits every unknown in the rate that produced it, and that
rate is `n = 1 day`: one 24-hour window, one MLB evening slate, one growth
burst. §6 of the measurement says the line is a **floor rather than a centre** —
NCAAF and NFL enter the feed with no config change
(`backend/kalshi/discovery.py:237-238`) and an NFL Sunday is a ~10-hour in-play
window against MLB's ~4. An alarm keyed to a date computed from that rate is
silent for exactly as long as the rate is understated, which is the direction
the evidence says it is understated in.

A `db_kb` threshold has a second defect on top of that one: **it cannot fire on
anything else that lands on `/data`.** Not the WAL, not the free list, not
`loop_rss.jsonl`, not the 239 MB of filesystem overhead §1 of the measurement
found and could not attribute. The source document says so itself: *"This table
alarms on `db_kb` only."*

Free bytes have neither problem. `os.statvfs` is a measurement of the present,
the threshold is a comparison rather than a model, and every byte on the volume
is inside it whatever wrote it. **If the rate is wrong, the tier still fires at
the byte level it names**; only the English beside it ("about nine days") is
wrong, and it is wrong in the direction of firing too early.

The rate is still used, in one direction only: to *express* each threshold in
days so the choice of number can be argued with. Nothing branches on it.
`tests/test_volume_alarm.py::TestEachThresholdIsTheNumberOfDaysItClaims` pins
each constant to the number of days its comment claims, so the argument cannot
quietly stop matching the number.

## 3. The three thresholds, and what each is worth in days

At the measured 161.40 MB/day, with the second column net of the 184.04 MB a
burst's WAL needs (§4 of the measurement: 179,731 KiB observed at
2026-08-31T23:30:14Z, so the last ~184 MB is not available to `cockpit.db` at
all).

| tier | free bytes | raw days | days net of the WAL reserve | fires about |
|---|---:|---:|---:|---|
| `notice` | 1,600,000,000 | 9.91 | **8.77** | 2026-09-07 |
| `act` | 800,000,000 | 4.96 | **3.82** | 2026-09-12 |
| `critical` | 400,000,000 | 2.48 | **1.34** | 2026-09-15 |

- **`notice` assumes the reader is away.** The repair is a laptop command, so
  the useful question is not "how long until it breaks" but "how long until
  someone is next in front of a laptop". A week plus a day and a half is the
  honest answer to that. It is also the tier that fires early **if the rate
  doubles**: football arrives on the sports calendar rather than on a deploy,
  and a doubled rate reaches this level in half the nominal time while still
  leaving four days.
- **`act` is the last tier at which "extend it when convenient" is a true
  sentence.** Five days is about one football weekend plus the working days
  either side of it, and §6 names two ways the rate rises inside such a span
  and none by which it falls before the fill date.
- **`critical` is one burst night.** Four hours of in-play carried 99.51% of the
  measured day and the largest single hour took 53.88 MiB, so at 1.34 days net
  of the reserve a single evening slate can take the rest.

**A fourth tier was considered and refused.** The measurement's own first
proposed row is "the `VACUUM` margin is gone" at about 2026-09-02. §7 shows that
option is worth 0.56 days of headroom, that its temp-file justification is
**refuted** (`/tmp` is a separate 8.35 GB filesystem with 7.87 GB free), and
that a WAL-mode justification survives untested — so the whole claim reduces to
*an option worth thirteen hours of runway may expire in thirteen hours*. Worth
recording that it is going; not worth a phone buzzing.

## 4. Where it is delivered, and why that is the existing channel

Through `Alerter` → `DiscordNotifier.failure`, the same path `check_feed` and
`check_credits` already use, called once per pass from `scripts/run_loop.py`
beside them. No new channel: `backend/notify/alerts.py` exists precisely because
the transport was complete and imported by nothing for the life of the project,
and a second delivery mechanism would be the same mistake with a fresh coat.

**Three kinds, one per tier**, all declared in `FAILURE_KINDS`. `_failure` keys
the dedupe on `kind:day`, so a single kind would send the first tier crossed and
then go silent for the rest of the day — **including on the day free space falls
from "a week left" to "one burst left"**. Escalation has to be able to speak.
The reverse direction is deliberately quiet: an extend that lifts free space
back over a threshold sends nothing, because the repair is the news and the
person who made it already knows.

**The message carries the command.** There is no in-process fix, so an alert
that only said "disk is low" would be a notification about a problem with no
stated remedy, on a phone, to someone who is away. It names
`fly volumes extend`, says auto-extend is already at its ceiling, and prints
both day-figures with the smaller one first.

## 5. Unreadable is `None`, and that is the load-bearing line

`read_volume` returns `None` when `statvfs` raises or does not exist, never a
substituted `0`. On this particular question a zero is not a benign default —
it is the **loudest** reading, so a blind alarm and a working one would look
identical from the phone, and the first real alert would arrive in a channel
already muted.

Two mechanisms enforce it rather than one comment:

1. `volume.classify` **raises** on `None` rather than returning a tier. A
   `classify(None)` returning `TIER_OK` would be blindness that reads as health;
   returning `TIER_CRITICAL` would be a permanent false alarm on every developer
   laptop (Windows has no `os.statvfs` at all).
2. `Alerter.check_volume` branches on `reading is None` explicitly, logs at
   WARNING that free space is *unknown, which is not the same as healthy*, and
   **writes no `notifications` row** — a claim with no delivery is exactly what
   `undelivered_last_24h` exists to catch.

## 6. Two things this deliberately does not do

**It does not delete anything, and it may never be wired to something that
does.** An automatic deletion fired by a disk alarm is a guard that goes off at
the worst possible moment: unattended, on a volume already in trouble, with
nobody reading the output. `backend/store/volume.py` contains no `DELETE`, no
`unlink` and no import of `fair_price_downsample`, and
`tests/test_volume_alarm.py::TestTheAlarmCannotDelete` asserts both over the
source — the same structural property `scripts/inspect_live_disk.py` already
holds.

**It does not add a field to the per-pass RSS log**, which is the obvious second
home for a free-byte series. §10 of the measurement is why: `RSS_LOG_KEEP_LINES`
× the observed 328.5-byte line already exceeds `RSS_LOG_CAP_BYTES` by 1.25×, so
from about 2026-09-04 that file reads ~2.6 MB, splits it and rewrites ~2.6 MB
**every pass** — ~7.0 GB/day of I/O on the very volume this alarm is about.
Widening the line makes it worse. The durable record is `notifications.detail`,
which carries the exact byte count on every tier claim at a cost of one row per
tier per day.

## 7. What this does not establish

- **That `ENOSPC` arrives when free reaches 0.** SQLite can fail to write with
  bytes still free — WAL extension, a temp file, an index build. The `critical`
  tier's 1.34 net days is the answer to that, not a proof against it.
- **That 161.40 MB/day is the rate.** `n = 1 day`. Every day-figure in §3 above
  moves with it; every byte threshold does not.
- **That anyone will act on it.** The alarm reaches a phone. It cannot extend a
  volume, and no code here pretends otherwise.
