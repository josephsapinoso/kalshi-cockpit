# The volume clock — 2026-09-01

**At 162 MB/day against 2.59 GB actually free, the volume fills on
2026-09-17.**

That is the deliverable sentence. Everything below is the arithmetic behind
it, the two things it is more urgent than, and the eight things it does not
establish.

Two of those come first, because they change what to do today rather than in
a fortnight:

- **The `VACUUM` repair expires within about a day, not a fortnight.** Under
  the rule this repo has recorded twice — `fly.live.toml:568-570`,
  `backend/store/retention.py:14-16`: *"`VACUUM` needs roughly the whole file
  free on the same filesystem"* — the margin today is **179.6 MB**, which is
  **0.55 days** at the measured rate. Tonight's slate (14 MLB fixtures from
  22:41Z, `sweep-log`) adds ~155 MiB. See §7.
- **`fly.live.toml:577` says *"measured growth 0 B/day"* and it is wrong by
  the whole quantity.** §8 shows exactly how that reading was produced, and
  the mechanism is reproducible rather than a slip: file growth is **zero for
  twenty hours a day**, so a short window taken outside the in-play burst
  reads 0 whatever the daily rate is.

## Instruments

Both live reads were taken 2026-09-01, ~16:30–16:43Z, over
`flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/…"`, which is
the only permitted way to run anything on that box.

| read | script | what it gives |
|---|---|---|
| the numerator | `scripts/inspect_live_db.py loop-rss -n 20000 --limit 20000 --json` | 3,904 per-pass lines from `/data/loop_rss.jsonl`, 3,196 of them carrying `db_kb` |
| the denominator | `scripts/inspect_live_disk.py --json --top 15` | the project's only `os.statvfs`, on `/data` |
| corroboration | `scripts/inspect_live_db.py db-sizes --json` | `page_count`, `freelist_count`, per-btree bytes |
| corroboration | `scripts/inspect_live_db.py prune-frontier --json` | whether `kalshi_quotes` retention is keeping up |
| corroboration | `scripts/inspect_live_db.py sweep-log -n 12 --json` | what the slate is, to date the burst |

**`db_kb` has never been differenced before.** `scripts/run_loop.py:339`
writes it once per pass and has since 2026-08-30; `inspect_live_db.py`'s
`loop-rss` renders it; nothing in the repo has ever subtracted two of them.
This is the first reading of that series as a series.

**The instrument checks out against an independent read.** The newest
`db_kb` sample is 2,356,584 KiB; `2,356,584 × 1024 = 2,413,142,016`, which is
byte-for-byte what `inspect_live_disk.py` reports for `/data/cockpit.db` and
what `db-sizes` reports as `page_count × page_size`. Three paths, one number.

## 1. The denominator: the real one, and how far the nominal one is out

```
statvfs /data                     bytes            note
  total (f_blocks x f_frsize)  5,248,090,112   4.888 GiB; `df -h` prints 4.9G
  free  (f_bavail x f_frsize)  2,592,702,464   <- THE DENOMINATOR
  used                         2,655,387,648   50.6%
  walked (8 regular files)     2,415,938,332
  unaccounted                    239,449,316   held by something walk cannot see
```

`f_bavail`, not `f_bfree`: the difference is the reserve only root may use and
the process that would hit ENOSPC does not run as root. That choice is
`inspect_live_disk.py:capacity`'s, and it is the conservative one.

**Against the nominal 5,000,000,000 every other figure in this repo divides
by** (`docs/measurements/2026-08-30-the-candidate-scan-index.md:153`,
`docs/adr/0086-…:103`, `tasks/NEXT.md:1518`, and six more):

|  | nominal method | statvfs | difference |
|---|---:|---:|---:|
| free space | 2,586,857,984 | 2,592,702,464 | **+5,844,480 (+0.23%)** |
| used | 48.26% | 50.60% | **+2.34 points** |

**The free-space figure is accidentally right, and the coincidence should not
be trusted twice.** The filesystem is 248,090,112 bytes *larger* than the
nominal 5 GB, and 239,449,316 bytes are unaccounted overhead — the two nearly
cancel. They are unrelated quantities: `unaccounted_bytes` is the walk-vs-`df`
gap that `inspect_live_disk.py`'s own docstring calls "the finding, not a
rounding", and it includes anything deleted-but-still-open. It has never been
read before today, so nothing establishes it is stable. **The percentage-used
figure is out by 2.3 points**, which is the half that matters to anything
indexed against a threshold.

The last first-hand `df -h /data` before this was **2026-08-19** — 4.9 G,
3.2 G free, 32% — the reading taken after the extend that revealed the volume
and the filesystem had disagreed for three days
(`docs/adr/0054-…:124-137`). The 4.888 GiB above confirms that extend held.

## 2. The numerator: the cuts that had to come first

### The post-2026-08-30 cut

`db_kb` is null on the first 708 lines of the file and present from
**2026-08-30T01:52:32Z** — the field did not exist before that build. So the
cut is enforced by the instrument, not by a filter: there are no pre-2026-08-30
`db_kb` samples to include or exclude. A null is *"this row predates the
column"*, and it is dropped from the series, **never read as zero**. Zero rows
had exactly one of `db_kb`/`wal_kb` readable.

### The cut on the `db_kb` step, not the wall clock

`docs/measurements/2026-08-30-the-candidate-scan-index.md:116-126` records
what splitting on wall clock cost last time. Applied here, the series carries
**exactly one step**, and no negative delta anywhere (so no `VACUUM` ran in
the window):

```
2026-08-30T23:32:33Z  db_kb 2,034,808
2026-08-30T23:33:49Z  db_kb 2,181,760      +146,952 KiB = +143.51 MiB
```

That is `idx_odds_sport_commence`, measured at 150,302,720 bytes by the v31
deploy's own reading. Everything before it is a different regime; the boundary
is the index's own bytes, not a deploy timestamp.

### And a third cut, which the data forced

**`db_kb` is the main file only, and the WAL is on the same volume.** In the
pre-step window the WAL drains into the file — 42,938 KiB → 3,914 KiB across
2026-08-30T15:00–19:00Z — so tens of megabytes of "growth" in `db_kb` there
are a *move*, not an arrival. Every figure below is therefore taken on the
**footprint, `db_kb + wal_kb`**, and the db-only figure is printed beside it.
Post-step the two agree to 1.2 MiB over 41 hours, because the WAL now sits at
a p50 of 1,070 KiB — `maybe_checkpoint` works.

## 3. The measurement

**One clean 24-hour window**, anchored at 12:00Z so that *both* endpoints sit
inside a flat zone and the boundary choice cannot bias the total. It lies
entirely after the index step and entirely after the free-list drain, and it
contains exactly one growth episode:

```
2026-08-31T12:00:00Z -> 2026-09-01T12:00:00Z    24.075 h

  db file only     +156,960 KiB  =  153.28 MiB  =  160.73 MB/day
  db + WAL         +158,107 KiB  =  154.40 MiB  =  161.90 MB/day   <- headline
```

Endpoints snapped 11 s and 260 s from the anchors. **n = 1 day.**

### The anchor is not a degree of freedom, and here is the proof

12:00Z is an arbitrary choice, so it was swept. Every 24-hour window whose
start falls on an hour inside the post-burst flat zone — 15 of them, stepped
hourly from 2026-08-31T02:00Z — gives:

```
  n = 15 anchors     min 158.23    median 161.62    max 162.58   MB/day
  fill date          2026-09-18    2026-09-17       2026-09-17
```

**14 of the 15 land on 2026-09-17 and the fifteenth on 2026-09-18.** The
spread is 2.7% because both endpoints of every window sit inside a flat zone
21.5 and 14.7 hours wide, so shifting the anchor moves the window across
nothing. The headline 161.90 sits at the median. This is not evidence that
the *rate* is stable across days — it is one day, sliced fifteen ways — only
that the boundary choice inside that day carries no information.

### The parts, because a pooled number is not a finding until they agree

They emphatically do not agree, and the disagreement is the shape of the
answer rather than a defect in it. Hour by hour across that one day:

```
  2026-08-31T11..21   eleven hours   -0.18 .. +0.59 MiB each   +1,083 KiB   +0.68%
  2026-08-31T22        +34,915 KiB      34.10 MiB                           22.08%
  2026-08-31T23        +39,183 KiB      38.26 MiB                           24.78%
  2026-09-01T00        +55,172 KiB      53.88 MiB                           34.90%  <- largest
  2026-09-01T01        +28,064 KiB      27.41 MiB                           17.75%
  2026-09-01T02..12   eleven hours   -1.54 .. +2.02 MiB each     -310 KiB   -0.20%
                                                              -----------  -------
                                                              +158,107 KiB  100.0%
```

**Four hours carry 99.51% of the day. The largest single hour is 34.90%.** The
twenty quiet hours oscillate within ±1.6 MiB, which is WAL breathing, not
growth. On the db file alone those twenty hours are *exactly* zero — the same
integer, **2,199,624 KiB on 574 consecutive samples across 21.51 hours**
(2026-08-31T00:38:25Z → 22:08:55Z). Since the burst ended the file has held
**2,356,584 KiB on 414 consecutive samples across 14.74 hours**.

Dating the burst: `sweep-log` at 16:30Z reads *"next slot is baseball_mlb at
21:26Z-22:26Z for 14 game(s) from 22:41Z"*. The 2026-08-31 burst runs
22:08Z–01:45Z. **It is the in-play window.** That is a correlation with the
slate, not an attribution — see §9.

### Why the pooled figure is lower, and why it is the wrong one

Pooling the whole post-step window gives a different answer, and the reason is
arithmetic:

```
  A  pooled, 2026-08-30T23:33:49Z -> 2026-09-01T16:30:08Z   40.94 h
       +176,208 KiB = 172.08 MiB  =>  100.88 MiB/day = 105.78 MB/day
```

That window is **1.71 days long and contains one burst.** It ends at 16:30Z,
before 2026-09-01's burst has started. Spreading one episode over 1.71 days is
not a rate, it is a sampling artifact — the same failure as splitting on wall
clock, in a different costume. Reported here so the number is not
re-discovered and believed later.

Per-UTC-day, for completeness, on the footprint (the burst straddles midnight,
which is itself why the day is the wrong unit for the *parts* and the right one
for the *rate*):

```
  2026-08-30   0.43 h    +13.90 MiB    8.1% of the pooled total
  2026-08-31  24.00 h    +77.08 MiB   44.8%
  2026-09-01  16.51 h    +81.10 MiB   47.1%   <- largest, and a partial day
```

### The second day, which is excluded and which is quoted anyway

```
  2026-08-30T12:00Z -> 2026-08-31T12:00Z   24.105 h   (index step subtracted)
       db file only   +187,252 KiB = 182.86 MiB = 191.75 MB/day
       db + WAL       +144,434 KiB = 141.05 MiB = 147.90 MB/day
```

**This contradicts the premise of the exclusion in a way worth recording.**
The reason for dropping pre-2026-08-30 samples is the free-page one: while
the list was draining, reused pages made file-size deltas understate real
growth by ~4.5x (§11). That is true of *logical* growth and false of the
*file*. On the file this day reads **higher** (191.75 MB) than the clean one,
because the checkpoint deploy moved WAL bytes into it; on the footprint it
reads lower (147.90 MB). Either way it brackets rather than flatters. The
exclusion stands — that day contains a deploy, an index build and a WAL
migration — but **anyone expecting the excluded samples to be the optimistic
ones has the sign backwards.**

**Defensible range across every cut above: 148 – 192 MB/day.** The headline
161.90 sits inside it.

## 4. The clock

```
free (statvfs f_bavail)                  2,592,702,464 B = 2,592.70 MB
max wal_kb observed post-step              179,731 KiB   =   184.04 MB
```

| rate | basis | all free space | less WAL headroom |
|---|---|---|---|
| **161.90 MB/day** | **clean 24 h, db+WAL** | **16.01 d → 2026-09-17** | 14.88 d → 2026-09-16 |
| 160.73 MB/day | clean 24 h, db only | 16.13 d → 2026-09-17 | 14.98 d → 2026-09-16 |
| 191.75 MB/day | 2026-08-30 day, db only | 13.52 d → 2026-09-15 | 12.56 d → 2026-09-14 |
| 105.78 MB/day | pooled 40.9 h (artifact) | 24.51 d → 2026-09-26 | 22.77 d → 2026-09-24 |

**The sentence: at 162 MB/day against 2.59 GB actually free, the volume fills
on 2026-09-17.** The honest bracket is 2026-09-14 to 2026-09-26, and §6 says
why the early end is the one to plan against.

"Less WAL headroom" reserves the largest WAL this record has seen. The WAL is
extended *before* the pages reach the file, so the last ~184 MB of free space
is not available to `cockpit.db` — it is the space the writer needs to be able
to commit at all.

## 5. What is growing, and what is holding it down

`db-sizes`, live, 2026-09-01T~16:40Z:

```
page_count 589,146   page_size 4,096   total 2,413,142,016
freelist_count 22,200   reclaimable_by_vacuum 90,931,200

fair_prices             646,230,016     kalshi_quotes           413,560,832
idx_quotes_ticker_time  352,309,248     odds_snapshots          259,162,112
idx_odds_sport_commence 159,178,752     idx_odds_event          145,350,656
idx_fair_link           133,218,304     idx_fair_market_computed 120,438,784
idx_odds_commence        26,656,768     recommendations          19,828,736
```

Differenced against the 2026-08-30 reading
(`docs/measurements/2026-08-30-the-candidate-scan-index.md:150-178`), over
~41 hours. **Directional only — see §9.**

```
  fair_prices              +116,903,936     ~ +68 MB/day
  kalshi_quotes             -37,675,008     ~ -22 MB/day   retention working
  idx_quotes_ticker_time    -46,399,488     ~ -27 MB/day   retention working
  odds_snapshots            +13,418,496     ~  +8 MB/day
  idx_odds_event             +8,048,640
  idx_odds_sport_commence    +8,876,032
  idx_odds_commence          +1,564,672
  freelist                  ~+72,000,000    ~ +42 MB/day   pages freed, not yet reused
  ------------------------------------------------------------------
  subtotal of the named     +136,768,480
  residual                  ~+25,007,136    idx_fair_link and
                                            idx_fair_market_computed were not
                                            measured on 2026-08-30 at all
  ------------------------------------------------------------------
  file total               +161,775,616     the measured 162 MB/day
```

Two readings of that table:

1. **`fair_prices` is the growth.** +117 MB while the whole file grew +162 MB,
   and it has **no retention rule and is not named in `retention.py` at all**
   (`backend/store/retention.py:46-55`, the module's own "What this does NOT
   do", names `odds_snapshots` as deliberately out of scope at `:53` and does
   not mention `fair_prices`). The only `DELETE FROM` statements in `backend/`
   are `retention.py:204` (`kalshi_quotes`), `:239` (`unmatched_items`) and
   `:292` (the legacy table). With
   `idx_fair_link` + `idx_fair_market_computed` its family is 900 MB, 37% of
   the file.
2. **The net rate is held down by `kalshi_quotes` retention, and that is a
   fragile arrangement.** Retention returned 84 MB of btree to the free list in
   41 hours; the free list rose 72 MB. `prune-frontier` shows the prune 26
   minutes behind its own cutoff (frontier 2026-08-29T16:16:40Z, cutoff
   16:43:10Z, backlog 50,259 rows of 4,825,853) — it is keeping up **today**.
   If it stops, the measured 162 MB/day becomes something nearer the gross
   insertion rate with nothing subtracted.

**The free list is not drained, and the belief that it was is two days out
of date.** `docs/measurements/2026-08-28-recorder-silence-is-chronic.md:94-99`
read 587,354,112 bytes free-listed; the 2026-08-30 reading read 18.9 MB, from
which it follows that growth thereafter goes straight to the file. That was
true on 2026-08-30 and is not true now. It stands at **90,931,200 bytes, 22,200
pages**, and it is revolving: retention refills it, inserts consume it. The
162 MB/day is already net of that.

## 6. The straight line, and what breaks it

**This is a straight-line extrapolation from a single 24-hour window, and the
line is a floor rather than a centre.** Stated plainly because the growth is
not driven by anything in this repo — it is driven by the sports calendar.

- **The burst is the in-play window.** Four hours a day today, because the
  slate is one MLB evening (14 fixtures). It is not a fixed cost.
- **NCAAF and NFL are arriving, and they enter without a config change.**
  `backend/kalshi/discovery.py:237-238` maps *"Pro Football"* and *"NCAA
  Football"* to their odds keys off Kalshi's own categories, so the feed
  widens as Kalshi lists the fixtures. `.env.example:209` already anticipates
  *"FOUR sports (NCAAF+NFL in September)"*. An NFL Sunday is a ~10-hour
  in-play window against MLB's ~4.
- **No relief arrives first.** MLB's regular season has ended in the last days
  of September in every recent year — after every date in the table above —
  and the postseason follows it. Nothing in the calendar subtracts before the
  volume fills. This is the one input here not read off an instrument.
- **`fair_prices` is written per pass against a slate.** More fixtures, more
  books and more markets multiply the term that is already 68 MB/day.

What would move it the other way: a retention rule on `fair_prices`, a
`VACUUM` (§7), or an extend. None of the three is a code change this lane
made.

## 7. The repair expires before the volume does

`fly.live.toml:568-570` records the rule — *"a write extends the WAL first,
and `VACUUM` needs roughly the whole file free on the same filesystem"* — and
`backend/store/retention.py:14-16` states a stricter version, *"`VACUUM`
needs roughly twice the free space it would have by then"*. The `fly.live.toml`
rule is used below; the stricter one would close the window sooner.

```
  cockpit.db                    2,413,142,016
  free                          2,592,702,464
  margin                          179,560,448     = 179.6 MB
```

The file grows and the free space shrinks by the same bytes, so the margin
closes at **twice** the growth rate:

```
  179,560,448 / 2 = 89,780,224 B of growth  =  0.55 days at 161.90 MB/day
```

Relaxing it as far as it can honestly go — free ≥ the *compacted* size, i.e.
the file minus its free list, since the copy SQLite writes is smaller than the
original — the margin is 270,491,648 B, **0.84 days**. That is the most
generous reading available, not the conservative one.

**Either way it is inside one evening slate.** Tonight's burst is due to start
at 22:41Z and the last two were 153–155 MiB. `VACUUM` would reclaim 90.9 MB,
which is 0.56 days of headroom, so it is not a fix either — but it is an
option that stops existing tomorrow, and an option that expires should be
named before it does.

**Not verified here:** whether SQLite would place its `VACUUM` temp file on
`/data` at all, or on the container's root filesystem via `SQLITE_TMPDIR` /
`PRAGMA temp_store`. If it goes elsewhere the constraint is different and the
window is wider. The rule quoted above is this repo's own recorded belief and
it has not been tested against the deployed configuration. That test is cheap
and is not this measurement.

## 8. How "0 B/day" was produced, and why the mechanism will do it again

`fly.live.toml:577` currently states, in a deployed config file, *"measured
growth 0 B/day with retention deployed"*. It descends from
`docs/measurements/2026-08-19-the-prune-loses-to-the-writer.md:215-219`: the
same file size, 1546.4 MB, at **18:47:40Z and 18:59:20Z** — a 17-minute
window.

Map that clock onto the growth curve measured here. 18:00–19:00Z on
2026-08-31 moved **+406 KiB**, and 18:47–19:04Z lands squarely inside the
twenty-hour flat zone. **A 17-minute window at 18:47Z reads exactly zero at
any daily rate whatsoever**, including 162 MB/day and including 365 MB/day.

`tasks/archive/lessons-2026-08-31.md:942-949` already caught half of this —
"a flat file size is not a flat table", the free-list half. The other half is
new and is the more dangerous one: **the file is flat for most of the day even
when the free list is not absorbing anything.** The sampling window has to
span a burst, or the instrument returns zero and says nothing about it. A
window shorter than 24 hours cannot measure this quantity at all.

That is the pattern for `tasks/lessons.md`, and it generalises past disk: a
quantity driven by the sports calendar must be sampled over a whole calendar
day, because the quiet interval is longer than any convenient window.

## 8b. Counting the tests

Every defensible slice, and whether it is reported above:

| choice | options | taken | reported |
|---|---|---|---|
| what counts as the file | `db_kb`; `db_kb + wal_kb` | both | §3, both printed |
| window | pooled 40.9 h; clean 24 h; pre-drain 24 h; single episode | all four | §3 |
| anchor within the clean day | 15 hourly starts | all 15 | §3, swept |
| denominator | all free; less WAL headroom | both | §4 |

**Twenty-three numbers, four reported as candidate rates, one chosen — and
the choice was made before the anchor sweep was run, not after it.** The
sweep is a robustness check on a headline that was already fixed by the two
cuts in §2, not a search for the anchor that gave the best number. Nothing
was computed and dropped. The pooled 105.78 MB/day is reported *because* it
is the most flattering of the four and would otherwise be the one a later
session re-derived and believed.

## 9. What this does NOT establish

- **n = 1 day.** One 24-hour window, one MLB slate, one instrument. The
  second day available is contaminated by a deploy, an index build and a WAL
  migration, and it is quoted in §3 rather than averaged in. **A second clean
  day is one day of waiting and would double the evidence.**
- **It does not attribute the growth to any table.** §5's per-btree
  differences are taken against another session's `db-sizes` run whose minute
  is not recorded, over an interval known only to ~±1 hour, and two of the
  columns (`idx_fair_link`, `idx_fair_market_computed`) were not measured on
  the earlier date at all. The residual closes to ~25 MB, which is
  consistent with the reading and does not prove it. **Directional.**
- **It does not establish that the in-play window causes the burst.** The
  burst coincides with the MLB slate read off `sweep-log`. Two quantities that
  both move with the evening correlate whatever is driving the writes.
- **It does not establish that ENOSPC arrives when free reaches 0.** SQLite
  can fail to write with bytes still free — WAL extension, a temp file, an
  index build. `inspect_live_disk.py`'s own docstring says so. The dates in §4
  are the *latest* the volume can fill, not the earliest the box can break.
- **It says nothing about the 239 MB unaccounted.** Whether that is ext4
  journal and inode tables or a deleted-but-still-open file was not
  determined. It is charged to the filesystem either way, so the denominator
  is right regardless — but if it is a held-open file it could move, and
  nothing here would see it.
- **It cannot reach before 2026-08-30T01:52:32Z.** `db_kb` did not exist on
  the line. The 3,904-line file reaches back to 2026-08-29T18:03:10Z, but the
  first 708 of those lines carry no storage fields.
- **A straight line is what was drawn.** §6 says so and names what breaks it.
  No curvature was fitted and n = 1 could not support one.
- **Nothing about whether any of this should be repaired, or how.** This is a
  clock. The choice between an extend, a `fair_prices` retention rule and a
  `VACUUM` is a decision with its own trade-offs and belongs in an ADR.

## 10. The instrument's own reach — it truncates, and it has not yet

`RSS_LOG_CAP_BYTES = 2 * 1024 * 1024` at `scripts/run_loop.py:148`.
`scripts/run_loop.py:393-397`:

```python
if path.stat().st_size > RSS_LOG_CAP_BYTES:
    tail = path.read_text(...).splitlines()[-RSS_LOG_KEEP_LINES:]
    path.write_text("\n".join(tail) + "\n", ...)
```

**It truncates — keeps the newest lines and drops the old ones silently — and
it has not fired.** `/data/loop_rss.jsonl` is **1,107,464 bytes of the
2,097,152 cap**, 3,904 lines, oldest 2026-08-29T18:03:10Z, and that oldest
line is byte-identical to the first line of the committed
`docs/measurements/2026-08-30-loop-rss-samples.jsonl`. The series is complete
since the file began. **The history supports the claim.**

**Two forward-looking facts, and the second is a defect.**

1. The file grows ~377 KB/day at the current 65.0 s mean cadence, so it
   **reaches the cap around 2026-09-04** — three days from now. After that the
   reach is the newest 8,000 lines, ≈ **6.0 days**.
2. **`RSS_LOG_KEEP_LINES` and `RSS_LOG_CAP_BYTES` are inconsistent at the
   current line width, and the trim will never converge.** The docstring
   assumes ~80 bytes/line; the line gained eleven fields on 2026-08-29/30 and
   a reconstructed current line is **366 bytes**. `8,000 × 366 = 2,928,000`
   bytes, which is 1.40x the 2,097,152 cap. So from ~2026-09-04 the file is
   *always* over the cap: every pass reads ~2.9 MB, splits it, keeps 8,000
   lines and rewrites ~2.9 MB — ~5.9 MB of I/O per pass, ~7.8 GB/day, on the
   volume this document is about and against the WAL for the same disk. The
   log stays bounded (the line count converges even though the byte count does
   not), so this is a cost, not a leak. `WALK_LOG_*` has the same shape and is
   safe: ~110 bytes × 8,000 = 880,000, inside the cap.

**The existing test cannot catch this, and the reason is the shape worth
carrying.** `tests/test_teardown_is_recorded.py:316-329`
(`test_the_cap_keeps_the_newest_lines`) fills the log with a **44-byte**
synthetic line and asserts `len(lines) <= RSS_LOG_KEEP_LINES`. At 44 bytes,
8,000 lines is 352,000 bytes and comfortably inside the cap, so the assertion
passes; at the real 366 bytes it is 2.93 MB and the assertion still passes,
because **the test asserts a line count and the constant is a byte count.**
Disabling the trim would fail it — so it is a guard, not decoration — but no
mutation of the *line width* can fail it. A hand-constructed fixture is what
made the two units look interchangeable, which is the same reason this repo
requires wire-format tests to load captured payloads.

Not fixed here. The one-line repair is to derive the keep-count from the cap
and the observed line width, or to lower `RSS_LOG_KEEP_LINES` to ~5,000 —
which costs ~2.2 days of reach and would have made *this* measurement
impossible three days from now. Either way the test needs a second assertion
on `path.stat().st_size`, and a fixture line the width of a real one.

## 11. What contradicts the 7-to-60-day range

The range is real but neither end of it was a volume clock. **Neither end is
written down as a sentence anywhere in this repo** — both are derivations over
two `db-sizes` readings, which is why the gap between them was never
adjudicated.

The arithmetic both ends descend from, restated in one place:

```
  file size    2026-08-28   1,910,190,080     2026-08-30   2,072,317,952
               delta         +162,127,872     = 162.1 MB   over ~2 days
  free list    2026-08-28     587,354,112     2026-08-30   ~18.9 MB
               absorbed      -567,536,026     = 567.5 MB
  logical growth  162.1 + 567.5 = 729.7 MB  =  ~365 MB/day
  understatement factor            729.7 / 162.1  =  4.50x
```

- **The ~7.5-day end counted bytes that never touched free space.** It divides
  the nominal remaining 5,000 − 2,251 MB by that ~365 MB/day. But the absorbed
  pages were reused, not added — they were already inside the file and already
  charged to the volume, so they can never consume free space again. A clock
  built on the logical rate double-counts them. It was also a **one-off
  backlog**: the free list stands at 90.9 MB today and revolves.
- **The ~34-to-60-day end used file-size deltas taken while that same backlog
  was draining**, which suppressed them. `tasks/NEXT.md:1993-1996` carries the
  operative version — *"~70MB/day against ~3GB free"*, ≈43 days — and the
  measured rate is 2.3x it.
- **Both divided by the nominal 5,000,000,000** rather than `statvfs` (§1).
- **`fly.live.toml:577` still says 0 B/day** and §8 shows how.
- **The repo's free-list readings do not agree with each other.** 712 MB
  (37%) at `tasks/archive/next-2026-08-29.md:103` and 587 MB (31%) at
  `docs/measurements/2026-08-28-recorder-silence-is-chronic.md:94-99`, both at
  an identical stated file size of 1.91 GB, never reconciled. Neither is dated
  to an instrument run in the same place.

**The measured answer, 16 days, sits inside 7-to-60 and is much narrower than
it.** What genuinely contradicts the framing is not the number but the shape:
the range was read as spanning "this week's work" versus "a scheduled alarm",
and it is neither. It is **a fortnight for the fill and about a day for the
`VACUUM` option** (§7) — and the fortnight assumes a straight line through a
September that adds two football codes to the feed.

## Proposed alarm, since the instrument exists and nothing reads it

Not built here. `db_kb` is on every pass line already, so the threshold is a
comparison, not a new measurement.

```
  db_kb  >  2,444,260 KiB     the VACUUM margin is gone           ~2026-09-02
                              (15.5 days of headroom still left)
  db_kb  >  3,500,000 KiB     ~8.8 days of headroom left          ~2026-09-08
  db_kb  >  4,400,000 KiB     ~3.1 days; extend from a laptop now ~2026-09-14
  db_kb  >  4,888,520 KiB     free space is zero
```

The first row is the one worth wiring, because it is the only threshold whose
*repair* is cheaper before it than after it. The last is arithmetic:
`(2,413,142,016 + 2,592,702,464) / 1024`.

A refinement the burst shape suggests: alarm on the **daily** delta rather
than the level — `db_kb` today minus `db_kb` 24 hours ago — because a rate
that doubles when NFL opens is visible a week before a level threshold
notices.
