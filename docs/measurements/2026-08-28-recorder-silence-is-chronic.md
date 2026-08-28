# The recorder's silence is chronic, not an incident — 2026-08-28

**Taken 2026-08-28 ~13:30Z against the live volume, read-only.** Live was at
`5436fc8` (`/api/health` `build.git_sha`), uptime 43.6 minutes, no restart since
the 12:52Z deploy.

`tasks/NEXT.md` records a 47.8-minute recorder gap on 2026-08-28 as **Incident
B — UNEXPLAINED and self-recovered**, and asks the next session to "read
`pass-gaps` again and check whether a second gap has appeared". It had, four
times on the same day, and the same shape goes back three days.

## What was measured

Every distinct `odds_sweep_log.pass_ms` since 2026-08-22T11:20Z, differenced,
holes over 1,200,000 ms reported. `odds_sweep_log` takes a row on **every**
pass, quote and full, whatever the sweep decision — the rows either side of
every gap below are `skipped` rows carrying a reason, so a hole is the loop not
running, not the loop deciding not to buy.

    2026-08-23T09:59:48Z -> 10:26:58Z    27.2 min
    2026-08-25T20:06:24Z -> 20:51:02Z    44.6 min
    2026-08-26T02:05:51Z -> 02:30:12Z    24.4 min
    2026-08-26T07:09:34Z -> 07:46:32Z    37.0 min
    2026-08-26T10:46:26Z -> 11:41:28Z    55.0 min
    2026-08-26T13:30:01Z -> 13:51:33Z    21.5 min
    2026-08-26T16:00:34Z -> 16:28:55Z    28.4 min
    2026-08-26T20:24:55Z -> 21:03:36Z    38.7 min
    2026-08-27T03:46:50Z -> 04:46:29Z    59.6 min
    2026-08-27T10:58:33Z -> 11:31:45Z    33.2 min
    2026-08-27T14:31:54Z -> 15:03:00Z    31.1 min
    2026-08-28T02:11:28Z -> 02:43:05Z    31.6 min
    2026-08-28T03:52:58Z -> 04:23:59Z    31.0 min
    2026-08-28T06:21:09Z -> 07:22:13Z    61.1 min
    2026-08-28T09:48:29Z -> 10:51:49Z    63.3 min
    2026-08-28T11:21:18Z -> 12:09:06Z    47.8 min

    total silence per day
    2026-08-23     27.2 min   1 gap
    2026-08-24      0         0
    2026-08-25     44.6 min   1 gap
    2026-08-26    204.9 min   6 gaps
    2026-08-27    124.0 min   3 gaps
    2026-08-28    234.9 min   5 gaps   (to 13:24Z)

**The recorder has been off for about three and a half hours a day since
2026-08-26.** One gap a day, twice, then six, three and five.

## The gaps are real silence, not a sparse sweep schedule

The obvious alternative — that ADR 0071 §2.6's hourly floor makes the loop buy
less often, so `odds_sweep_log` is legitimately sparser — is refused by a
second, independent table. `kalshi_quotes.observed_ms` inside each of the five
2026-08-28 gaps, against the 30 minutes either side of it:

    gap        30 min before    inside    30 min after
    31.6 min          41,951         0           7,476
    31.0 min           6,506         0          10,043
    61.1 min           4,190         0          11,679
    63.3 min          19,169         0          14,948
    47.8 min          14,948         0          14,518

Thousands to tens of thousands of rows on both edges and **exactly zero inside,
five times out of five**. The writer stopped; it did not slow down.

## And they are not failing passes

`loop_failures` holds fifteen rows in its whole life. The only three on
2026-08-28 are the `ZeroDivisionError`s at 12:36:33Z, 12:38:03Z and 12:38:46Z —
**after** the last gap had already closed at 12:09:06Z. Under `pass-gaps`' own
rule (*"a gap WITH failures inside it was a failing loop; a gap with NONE never
came back to raise"*), every gap on 08-27 and 08-28 is a wedge or a restart.
The 2026-08-26 16:00:34Z gap is the one exception: it contains the
`ValueError: ask 1000 tenths` series, so that one was a failing loop.

## What it is not

- **Not a machine stop.** `fly.live.toml` sets `auto_stop_machines = "off"`,
  `min_machines_running = 1`.
- **Not swap thrash.** `SwapTotal: 0`. There is no swap to thrash.
- **Not sustained CPU steal, when observed.** `/proc/stat` steal was 23 ticks
  over a 2,618-second uptime (0.009%), and PSI `cpu full` was 0. This is a
  reading taken *outside* a gap and says nothing about what happens inside one.
- **Not the `/api/parlays` OOM (`7b185e8`).** That fix was committed
  2026-08-28T05:00:33Z and deployed shortly after. Three of the five 08-28 gaps
  — 06:21, 09:48 and 11:21 — start after it. It was the leading candidate and
  the timeline refutes it.
- **Not the deploys, except one.** The 03:52:58Z→04:23:59Z gap ends at the
  04:23Z `bc256e3` deploy. No deploy corresponds to any of the other four.

## The standing lead: the database is 1.91 GB on a 2 GB box

`db-sizes`, same reading:

    page_count 466,355   page_size 4,096   total 1,910,190,080 bytes
    freelist_count 143,397   reclaimable_by_vacuum 587,354,112 bytes

    kalshi_quotes            341.9 MB     idx_quotes_ticker_time   289.6 MB
    fair_prices              284.8 MB     idx_fair_link             57.2 MB
    odds_snapshots           153.3 MB     idx_odds_event            83.4 MB

`MemTotal` is 2,015,876 kB and there is no swap, so the file cannot be cached
and every large read goes to the volume. PSI over the 43 minutes since the last
restart: `io full avg300 = 5.48`, total 126.5 s of *all-tasks-blocked* IO in
2,618 s of uptime — **4.8% of wall-clock spent with nothing able to run**,
against `cpu full` of 0. IO is the only pressure on this box.

That is a lead and **not a finding**: 4.8% is not 60 minutes, the reading was
taken outside a gap, and nothing here shows a causal path from a slow volume to
a loop that stops for an hour and then resumes.

`odds_snapshots` / `fair_prices` retention has been a carried-forward open item
in `NEXT.md` for several sessions. This is the first measurement that attaches a
symptom to it.

## The only off-box watchdog ran four times that day

`.github/workflows/heartbeat.yml` is the dead-man's switch, and the previous
session's entry called it "worth trusting, and that is itself a result". Two
things in that reading are wrong, and both are measurable.

**Its threshold is 30 minutes, not 44.** `age > 1800000` ms. The 44 minutes was
the *observed* age at the one firing, not the bar. Four of the sixteen gaps are
below 30 minutes and could never have alarmed.

**And it does not run every 15 minutes.** Scheduled runs actually delivered,
from the Actions API, against the 96/day `*/15 * * * *` asks for:

    2026-08-24    67        2026-08-27     9
    2026-08-25    70        2026-08-28     4
    2026-08-26    46

Median gap between runs **22.6 min**, maximum **245 min**, n = 199. The cadence
fell by more than an order of magnitude in three days with no change to the
file, no failed run, and no signal of any kind.

The two compound. A gap only exceeds the 30-minute bar for the part of its
length past 30 minutes, so a 31-minute hole is visible to a poller for about a
minute. On 2026-08-28 the recorder was silent for 235 minutes across five holes
and the watchdog looked four times. **It caught one.** That single true firing
was accurate and is what made the previous session trust it; one hit out of
sixteen is the rate.

Corrected in the workflow itself: the embed footer said "every 15 min", which
turns a quiet channel into evidence of health. Raising the cron is not the fix —
`*/15` is already what is being ignored.

## What this does not establish

- **Not the cause of any gap.** Wedge and restart are still both live, and the
  one instrument that separates them — Fly's machine event log — retains only
  the most recent deploy, so it cannot be asked about 06:21Z.
- **Not that the gaps are getting worse.** Three days is three points, 08-26 and
  08-28 are the two highest and 08-27 sits between them, and the record before
  08-23 was not examined.
- **Nothing about what Joe saw.** Every gap here is invisible on the screen
  except as odds ageing; the 44-minute heartbeat is the only one that ever
  reached a phone, and it fires on 3 of these 16.

## The instrument, built the same session

A wedged pass wrote **nothing at all** — no row, no failure, no log line — which
is why the same silence was recorded as a fresh, unexplained one-off three
sessions running. `run_forever` awaited `do_pass()` for as long as it took.

It now takes `pass_deadline_s`, defaulting to `DEFAULT_PASS_DEADLINE_S = 600`.
Past it the pass is cancelled and raises `PassDeadlineExceeded`, which travels
the existing failure path: `LoopState.last_error`, the `on_failure` hook, a
`loop_failures` row with the pass number and kind, and a logged traceback naming
the await it was blocked on.

600s sits between two populations that do not overlap, and both edges are
measured. Live pass durations read off `pass N ok` the same day: quote passes
3.8–4.9 s, full passes **43.0 s and 77.3 s**. The shortest silence ever observed
is 21.5 minutes. So the deadline is ~7.8× the longest healthy pass and under
half the shortest wedge — it cannot fire on a healthy pass, and it would have
fired on all sixteen holes above **if they were hung awaits**.

**That condition is the point, and it is why the next reading is informative
either way.** `asyncio.timeout` cancels by throwing into an await; a pass
blocked in a synchronous call never yields and is not interruptible. So:

    a gap that now carries a PassDeadlineExceeded row   a hung await, located
    a gap that still carries no failure row at all      the process was down,
                                                        or it was blocked in
                                                        synchronous code

The second is two states and separating them needs an instrument this record
still does not have. But it is a strictly narrower claim than the one available
before, and — given a 1.91 GB SQLite file, no swap, and `io full avg300 = 5.48`
— it points somewhere specific.

**One misattribution was closed before it could poison the table.** Since
Python 3.11 `asyncio.TimeoutError` *is* the builtin `TimeoutError`, so a pass
whose own inner `wait_for` expires — an odds call, a Kalshi call — arrives at
the handler looking exactly like a deadline breach. `deadline.expired()` is
checked before relabelling, so `loop_failures` cannot report a wedge that never
happened.

Seven guards, each mutation-observed red. The one that mattered most was the last
one written: defaulting `pass_deadline_s` to `None` left every other test green,
because each sets the deadline explicitly, while live quietly went back to
waiting forever. Production calls `run_forever` without naming the argument, so
the signature default *is* the deployed value, and it is now asserted.
