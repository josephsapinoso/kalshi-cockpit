# The volume clock — 2026-09-01

**At 161 MB/day against 2.59 GB actually free, the volume fills on
2026-09-17.**

**Read the second half of that sentence before acting on the first: `n = 1
day`.** One 24-hour window, one MLB evening slate, one growth burst. The rate
is 161.40 MB/day on the db+WAL footprint and 160.23 on the file alone; the
free space is 2,592,702,464 bytes read by `statvfs`, not the nominal
5,000,000,000 the rest of this repo divides by. The method bracket is
2026-09-14 to 2026-09-26 and carries no day-to-day slate variance at all,
because there is only one day. §6 says why the early end is the one to plan
against.

Everything below is the arithmetic, and the twelve things it does not
establish (§9). Two of those come first, because they change what to do today
rather than in a fortnight:

- **`fly.live.toml:577` says *"measured growth 0 B/day"* and it is wrong by
  the whole quantity.** §8 gives a mechanism that would produce that reading,
  and the mechanism is reproducible rather than a slip: file growth is **zero
  for twenty hours a day**, so a window shorter than a day reads 0 whatever the
  daily rate is. It is not the only sufficient mechanism, and §8 says so.
- **The `VACUUM` escape hatch is narrower than the fill date and this document
  cannot say by how much.** The margin on `/data` is 179.6 MB — 0.56 days —
  *if* the repair needs whole-file headroom on `/data`. The temp-file reason
  for believing that is **refuted**: `/tmp` is a separate 8.35 GB filesystem
  with 7.87 GB free (§7). A WAL-mode reason survives and is untested. The
  option is worth 0.56 days of headroom either way, so this is a thing to note
  losing, not a repair. **§7, not this bullet, is the whole claim.**

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

**The free-space figure is accidentally right, and the coincidence has three
terms rather than two:**

```
  statvfs free - nominal free
    = (total - 5,000,000,000) - other files on /data - unaccounted
    = 248,090,112 - 2,796,316 - 239,449,316
    = +5,844,480                                       ✓
```

The filesystem is 248 MB *larger* than the nominal 5 GB and the overhead is
239 MB, so they nearly cancel — but they are unrelated quantities that move
independently, and neither had been read before today. **The percentage-used
figure is out by 2.3 points**, which is the half that matters to anything
indexed against a threshold.

**The 239 MB is not all mystery, and an earlier version of this document
treated it as if it were.** `used` is computed as `total - f_bavail * f_frsize`,
so **the root reserve is inside that 239 MB by construction** — §1 chooses
`f_bavail` precisely to exclude the reserve from *free*, which necessarily puts
it into *used*. A large part of the figure is therefore definitionally
immovable. The remainder is filesystem metadata (ext4 journal, inode tables)
and anything deleted-but-still-open, and nothing here separates them.

**Nothing else needs subtracting from the denominator, and here is the
number.** Everything on `/data` other than `cockpit.db` totals
`2,415,938,332 - 2,413,142,016 =` **2,796,316 bytes** across seven files.
`loop_rss.jsonl` adds ~377 KB/day and is hard-capped from ~2026-09-04 (§10);
`loop_walk.jsonl` is capped at ~880 KB. So the db+WAL numerator is the volume
numerator to within 0.1%, and the question is closed rather than left open.

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

**One clean 24-hour window**, anchored at 12:00Z so that both endpoints sit
inside a flat zone — which makes the anchor free for the db-only series and
nearly free for the footprint; the sweep below quantifies the difference. It
lies
entirely after the index step and entirely after the free-list drain, and it
contains exactly one growth episode:

```
2026-08-31T12:00:00Z -> 2026-09-01T12:00:00Z    24.075 h

  db file only     +156,960 KiB  =  153.28 MiB     over 24.075 h
  db + WAL         +158,107 KiB  =  154.40 MiB     over 24.075 h

  normalised to 24 h:   db file  160.23 MB/day
                        db + WAL 161.40 MB/day   <- headline
```

Endpoints snapped 11 s and 260 s from the anchors, so the window is 24.075 h
and the totals are divided by that rather than by 24 — an earlier version was
not normalised and read 161.90, which is 0.31% high and in the direction that
flatters urgency. **n = 1 day, one MLB evening slate, one burst.**

**The slate that produced it was never counted.** `sweep-log` gives 14 MLB
fixtures for *tonight*; nothing in the record says how many produced the
2026-08-31 burst. That gap is load-bearing twice — §7 scales the rate to
tonight and §6 scales it to an NFL Sunday — and neither scaling is anchored,
because the rate is per *calendar day* while the process is per *slate*.

### The anchor is not a degree of freedom, and here is the proof

**The claim an earlier version made here was stronger and was wrong.** "The
boundary choice cannot bias the total" is true of `db_kb`,
which is byte-identical for 574 samples around one anchor and 414 around the
other. It is **not** true of `db_kb + wal_kb`, which is the headline: the quiet
hours oscillate by up to ±1.6 MiB of WAL breathing, so each endpoint carries
that much slack — about ±2% on 154.40 MiB. Roughly 14 hours of feasible anchors
exist. The claim of zero boundary bias holds only for the db-only series.

So 12:00Z was swept. Every 24-hour window whose start falls on an hour inside
the post-burst flat zone — 15 of them, stepped hourly from 2026-08-31T02:00Z —
gives:

```
  n = 15 anchors     min 158.23    median 161.62    max 162.58   MB/day
  fill date          2026-09-18    2026-09-17       2026-09-17
```

**14 of the 15 land on 2026-09-17 and the fifteenth on 2026-09-18.** The
spread is 2.7%, which is the WAL slack named above and not a rate difference:
shifting the anchor moves the window across nothing but WAL breathing. The
headline sits near the median. **This is not evidence that the rate is stable
across days** — it is one day, sliced fifteen ways.

**One more check the largest sample gap demanded.** No gap in the series
exceeds 1,134 s, and at burst rates (~55 MiB/hour) a gap that size would carry
~17 MiB — enough to move "the largest hour is 34.90%". The five largest gaps
fall at 2026-09-01T13:50Z, 2026-08-31T20:29Z, 2026-09-01T02:51Z,
2026-08-30T00:09Z and 2026-08-29T23:18Z. **None is inside a burst**, so the
hourly decomposition carries no gap-attribution error.

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
       db file only   +187,252 KiB = 182.86 MiB   -> 190.91 MB/day
       db + WAL       +144,434 KiB = 141.05 MiB   -> 147.26 MB/day
```

**This contradicts the premise of the exclusion in a way worth recording.**
The reason for dropping pre-2026-08-30 samples is the free-page one: while
the list was draining, reused pages made file-size deltas understate real
growth by ~4.5x (§11). That is true of *logical* growth and false of the
*file*. On the file this day reads **higher** (190.91 MB) than the clean one,
because the checkpoint deploy moved WAL bytes into it; on the footprint it
reads lower (147.26 MB). Either way it brackets rather than flatters. The
exclusion stands — that day contains a deploy, an index build and a WAL
migration — but **anyone expecting the excluded samples to be the optimistic
ones has the sign backwards.**

**Defensible range across every cut above: 147 – 191 MB/day.** The headline
161.40 sits inside it. **It is method spread over ~2 days, one of them
contaminated — not sampling uncertainty, and not day-to-day slate variance,
which is unmeasured.**

## 4. The clock

```
free (statvfs f_bavail)                  2,592,702,464 B = 2,592.70 MB
max wal_kb observed post-step              179,731 KiB   =   184.04 MB
```

| rate | basis | all free space | less WAL headroom |
|---|---|---|---|
| **161.40 MB/day** | **clean 24 h, db+WAL** | **16.06 d → 2026-09-17** | 14.92 d → 2026-09-16 |
| 160.23 MB/day | clean 24 h, db only | 16.18 d → 2026-09-17 | 15.03 d → 2026-09-16 |
| 190.91 MB/day | 2026-08-30 day, db only | 13.58 d → 2026-09-15 | 12.62 d → 2026-09-14 |
| 105.78 MB/day | pooled 40.9 h (artifact) | 24.51 d → 2026-09-26 | 22.77 d → 2026-09-24 |

**Every date in this table is n = 1 day.** The spread across rows is *method*
spread over ~2 days of data, one of them contaminated. It carries no
information about day-to-day variance of the slate, which §6 says is the
dominant uncertainty.

**The sentence: at 161 MB/day against 2.59 GB actually free, the volume fills
on 2026-09-17 — on n = 1 day.** The honest bracket is 2026-09-14 to 2026-09-26, and §6 says
why the early end is the one to plan against.

"Less WAL headroom" reserves the largest WAL this record has seen:
**179,731 KiB at 2026-08-31T23:30:14Z** — inside the measured day's burst, on a
`TRUNCATE` checkpoint reporting `busy = 1`, i.e. a reader holding the log open.
Five of the six largest WAL samples fall in that same eight-minute stretch. So
the WAL genuinely does reach 175 MiB during a burst, the transient footprint is
that much above the sampled one, and the last ~184 MB of free space is not
available to `cockpit.db` — it is the space the writer needs to commit at all.
Both 24-hour endpoints sit in quiet zones where the WAL is ~1 MiB, so the spike
does not bias the rate.

## 5. What is growing — a composition, and deliberately not a rate

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

**One baseline, and it is dated from this document's own series.** The earlier
reading is the **pre-index** one at
`docs/measurements/2026-08-30-the-candidate-scan-index.md:162-178`, file
2,072,317,952 bytes. That file size is `db_kb = 2,023,748`, and the series here
holds exactly that value on 279 consecutive samples from **2026-08-30T21:14:29Z
to 23:10:29Z** — so the baseline is pinned to a 1.93-hour window without having
to trust an undated instrument run. **Interval: 44.4 ± 1.0 hours.**

That same document contains a *second*, post-index `db-sizes` run at `:150-153`
(total 2,251,366,400). The two differ by 179,048,448 bytes and by the whole v31
index build. **An earlier version of this section differenced some rows against
one and some against the other**, which broke the accounting identity it was
built on. Every row below is against the pre-index reading.

```
  fair_prices                +116,903,936
  idx_quotes_ticker_time      -46,399,488
  kalshi_quotes               -37,675,008
  odds_snapshots              +14,774,272
  idx_odds_event               +8,929,280
  idx_odds_commence            +1,564,672
  idx_odds_sport_commence    +159,178,752   the v31 build, not growth
  freelist                   ~+72,000,000
  ----------------------------------------
  subtotal                   +289,307,616
  residual                   ~+51,516,448   idx_fair_link and
                                            idx_fair_market_computed were not
                                            measured on 2026-08-30 at all
  ----------------------------------------
  file total                 +340,824,064   over 44.4 h
  less the index build       +181,645,312   organic
```

**No per-day figure is given here, and that is deliberate.** A 44.4-hour window
contains a non-integer number of growth bursts and ends before 2026-09-01's, so
dividing any row by 1.85 days reproduces exactly the pooled artifact §3 refuses.
An earlier version of this section labelled the 44.4-hour file total "the
measured 162 MB/day"; over 44.4 hours it is 94.7 MB/day, which is the artifact,
not the headline. **This section is a composition. §3 is the rate.**

### The denominator of every share below, named because it has been misread

**The denominator is `181,645,312` bytes: organic file growth over the
44.4-hour composition window** — the file total `+340,824,064` less the v31
`idx_odds_sport_commence` build of `+159,178,752`. It is a **byte total over
that window**. It is **not** a per-day rate, it is **not** the headline
161.40 MB/day, and it shares no endpoint with the 24-hour window §3 measures.

Written out because the arithmetic invites exactly one wrong move: `fair_prices`
grew `+116,903,936` bytes, `116.9 / 161.40 = 72.4%`, and 72.4% is not 64.4%.
**Neither number is wrong; the division is.** It divides a **44.4-hour total**
by a **24-hour rate**, which is a category error and not a discrepancy — the
same shape as §3's pooled artifact, in a third costume. There is no free-list
reuse hiding in the gap either, and that can be shown rather than asserted: the
free list is itself one of the rows, at `+72,031,200`, and the five shares sum
to 100.0%. The composition is an exact accounting identity over one window.

**What a reader sizing a retention rule should carry is 103.9 MB/day**, and
here is the whole derivation, in one place, so nobody re-derives it wrong:

```
  fair_prices share of organic bytes   116,903,936 / 181,645,312  =  64.4%
  headline rate (§3, clean 24 h)                                     161.40 MB/day
  fair_prices, if the share holds      0.644 x 161.40             =  103.9 MB/day
```

The middle line is an **assumption, not a measurement**: it holds only if the
composition is the same in the 24-hour window as in the 44.4-hour one, and
nothing here shows that. The consistency check is that the direct route agrees.
`116,903,936` over 1.85 days is `63.2 MB/day` — but that window is §3's pooled
artifact, understating by `161.40 / 98.2 = 1.644`, and `63.2 x 1.644 = 103.9`.
Two routes, one number, and both of them are the same `n = 1`.

**Do not read 117 MB/day anywhere.** It is the 44.4-hour total wearing a
per-day label.

As shares of the +181,645,312 organic bytes over the 44.4-hour window:

```
  fair_prices                +64.4%    116,903,936 / 181,645,312
  free list                  +39.7%    pages freed and not yet reused
  quote family               -46.3%    kalshi_quotes + idx_quotes_ticker_time
  odds family                +13.9%    excluding the new index
  residual                   +28.4%    two unmeasured fair_prices indexes
                             ------
                            +100.0%    an identity, not a corroboration
```

**One loose end, recorded rather than repaired.** The window is stated as
44.4 ± 1.0 hours, but the baseline is pinned to 2026-08-30T21:14:29Z–23:10:29Z
and the live read was taken at ~2026-09-01T16:30–16:40Z, which is
**42.5 ± 1.0 hours**. Nothing above moves: every share is a ratio of two byte
totals over the same window, and the recommended 103.9 MB/day is share x
headline rate, so the window's length does not enter either. The 4.5% would
only matter to a per-day figure taken *inside* this section, and this section
deliberately publishes none.

Two readings, and the second is the one that could move the clock on its own:

1. **`fair_prices` is the growth.** It is 64.4% of organic bytes by itself
   (over the 44.4-hour window — read the denominator note above before
   multiplying that by anything), it
   has **no retention rule**, and with `idx_fair_link` +
   `idx_fair_market_computed` its family is 899,887,104 bytes — **37.3% of the
   file**. `backend/store/retention.py` does mention it, at `:43` (*"`fair_prices`
   is keyed by `link_id`"*), three lines above the "What this does NOT do" list
   that names `odds_snapshots` as deliberately out of scope at `:53` and does
   not name `fair_prices` at all. That is worse than an oversight: the table was
   in the author's hand while the exclusions were being written, and it still
   got no rule and no exclusion. (`backend/store/retention.py` holds the only
   `DELETE FROM` statements under `backend/store/` — `:204`, `:239`, `:292` —
   though not the only ones in `backend/`; none of them touch `fair_prices`.)
2. **The free list is accumulating, not revolving, and nobody knows which it
   will do next.** It took 39.7% of the organic bytes in this window: pages
   freed by `kalshi_quotes` retention that inserts have **not** reused.
   `backend/store/retention.py:48-52` asserts the opposite behaviour — *"Freed
   pages are reused by subsequent inserts, so the growth stops even without
   one"*. If that assertion is right and the list saturates, **the rate falls
   passively and the fill date moves out, with nobody doing anything.** If the
   list keeps accumulating, the measured rate is what it is. This measurement
   cannot tell the two apart at n = 1 window, and it is the largest single
   uncertainty in the document — larger than the anchor, larger than the choice
   of series. §9 carries it.

`prune-frontier` shows the prune 26 minutes behind its own cutoff (frontier
2026-08-29T16:16:40Z, cutoff 16:43:10Z, backlog 50,259 rows of 4,825,853) — it
is keeping up **today**. The quote family gave back 84,074,496 bytes in this
window, and that give-back is what holds the net rate down.

**The free list is not drained, which is a two-day-old belief.**
`docs/measurements/2026-08-28-recorder-silence-is-chronic.md:94-99` read
587,354,112 bytes free-listed; the 2026-08-30 reading read 18.9 MB, from which
it follows that growth thereafter goes straight to the file. That was true on
2026-08-30. It stands at **90,931,200 bytes, 22,200 pages** today.

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
  books and more markets multiply the term that is already **103.9 MB/day** —
  64.4% of the headline rate, derived in §5. **That figure read 68 MB/day
  until 2026-09-01 and was wrong**: it was the same 64.4% applied to the
  pooled 105.78 MB/day, which §3 labels an artifact and §5 forbids dividing by.
  Applying a share measured over one window to a rate refused by the document
  is a way of importing an artifact through a multiplication.

What would move it the other way: a retention rule on `fair_prices`, a
`VACUUM` (§7), or an extend. None of the three is a code change this lane
made.

## 7. The `VACUUM` escape hatch, and why its size is unknown

**The rule, and what supports it.** `fly.live.toml:568-570` records *"a write
extends the WAL first, and `VACUUM` needs roughly the whole file free on the
same filesystem"*. `backend/store/retention.py:14-16` records a stricter
version, *"`VACUUM` needs roughly twice the free space it would have by then"*
— which read literally means 5.18 GB needed on a 4.888 GiB filesystem, i.e.
already impossible, so it is not usable as a requirement. **Neither is dated to
a test.** Two restatements of one belief forbid nothing more than one does, and
an earlier version of this document cited "recorded twice" as if it were
corroboration. It is not.

**If the rule holds, the margin is 0.55 days:**

```
  cockpit.db                    2,413,142,016
  free                          2,592,702,464
  margin                          179,560,448   = 179.6 MB
```

The file grows and free shrinks by the same bytes, so the margin closes at
twice the growth rate: `179,560,448 / 2 = 89,780,224 B` = **0.56 days** at
161.40 MB/day. Against the most generous reading — free ≥ the *compacted* size,
since the copy is smaller than the original — it is 270,491,648 B, **0.84
days**. Both fall inside tonight's burst.

**But the temp-file reason for believing the rule is refuted, and this is a
measurement, not an argument.** `scripts/inspect_live_disk.py --root /tmp`,
taken live 2026-09-01:

```
  /tmp    total 8,350,298,112   free 7,873,089,536   used 5.71%
  /data   total 5,248,090,112   free 2,592,702,464   used 50.60%
```

**Different totals, so different filesystems.** SQLite's `VACUUM` builds its
temporary database in the temp directory — `SQLITE_TMPDIR`, then `TMPDIR`, then
`/var/tmp`, `/usr/tmp`, `/tmp` — and on this box that is 7.87 GB free on a
filesystem the database does not touch. **On the temp-file mechanism, `/data`
needs no headroom at all and there is no cliff.**

**A different mechanism survives and is untested.** The database is in WAL mode.
A `VACUUM` rewrites every page in one transaction, and in WAL mode those pages
go through `/data/cockpit.db-wal` before any checkpoint — so the WAL could
extend towards the size of the compacted database, ~2.32 GB, on `/data`. That
would make `fly.live.toml`'s rule right for a reason its author did not give.
**Nothing here tests it**, and the two mechanisms give opposite answers.

**Not established, and it is the document's own second-most-prominent claim:
that a `VACUUM` was ever possible on this box.** What would settle it is one
`flyctl ssh console` invocation reading `PRAGMA temp_store`, `SQLITE_TMPDIR`
and `TMPDIR` — a query `inspect_live_db.py` does not have and which would need
a deploy to reach the machine.

**And the prize is exactly the size of the margin, which is the whole point.**
`VACUUM` would reclaim 90,931,200 bytes — **0.56 days** of headroom at the
measured rate, against a margin of 89,780,224 bytes, also 0.56 days. So even on
the pessimistic reading the claim reduces to *an option worth thirteen hours of
runway may expire in thirteen hours.* Worth recording that it is going; not worth a plan.

## 8. A second mechanism sufficient to produce "0 B/day"

`fly.live.toml:577` states, in a deployed config file, *"measured growth
0 B/day with retention deployed"*, dated 2026-08-20. The nearest reading in the
record is `docs/measurements/2026-08-19-the-prune-loses-to-the-writer.md:215-219`:

```
18:47:40Z   cockpit.db 1546.4 MB   cockpit.db-wal 51.6 MB
18:59:20Z   cockpit.db 1546.4 MB   cockpit.db-wal 51.6 MB   (uptime 95 min)
```

**That window is 11 minutes 40 seconds.** An earlier version of this section
called it 17 minutes and quoted an end time of 19:04 that appears nowhere in
the source — the number was manufactured by this document's own arithmetic.
`tasks/archive/lessons-2026-08-31.md:942-949` describes what may be the same
episode as 24 minutes. Three figures for one window; the source's own two
timestamps are the only ones with a citation.

**The lineage from that reading to the config comment is an inference.** The
comment is dated 2026-08-20 and the document is 2026-08-19. Nothing shown ties
them together rather than to some other read on the 20th.

**Two sufficient mechanisms, and this measurement does not separate them.**

1. **Free-list reuse.** The source document states it in the same paragraph:
   *"the main file is flat because ~25% of it is freelist being reused."* §11
   shows the free-list backlog was still large in that era, which is the
   contemporaneous evidence for this one.
2. **The diurnal flat zone.** In the day measured here, 18:00–19:00Z moved
   **+406 KiB**, and the file is byte-identical for 21.51 hours around it. A
   twelve-minute window inside that zone reads zero at any daily rate.

Either alone accounts for the zero. Mechanism 2 is asserted from a shape
measured **twelve days later**, across an index build, a WAL-checkpoint
migration and a `fair_prices` table that has since grown 22% — so whether that
shape held on 2026-08-19 is exactly what is not shown. `tasks/archive/
lessons-2026-08-31.md:942-949` already carries mechanism 1 as *"a flat file
size is not a flat table"*.

**What survives all of that, and is the part worth keeping:** a quantity driven
by the sports calendar must be sampled over a whole calendar day. The quiet
interval here is longer than any convenient window, so a short sample returns
zero and says nothing about it — whichever mechanism is doing the flattening.
That is the pattern for `tasks/lessons.md`.

## 8b. Counting the tests

Every defensible slicing choice, whether it was taken, and whether it is
disclosed above:

| degree of freedom | options | disclosed |
|---|---|---|
| series: `db_kb` / `db_kb + wal_kb` | 2 | **yes** — both printed everywhere |
| window: clean day / prior day / pooled / per-UTC-day | 4 | **yes** — all four, artifact labelled |
| anchor hour inside the flat zone | ~14 feasible | **yes** — 15 swept, §3 |
| denominator: `f_bavail` / `f_bfree` / nominal 5e9 | 3 | **partial** — `f_bavail` and nominal; `f_bfree` never quantified |
| WAL reserve: none / max / p99 | 3 | **partial** — none and max |
| `VACUUM` rule: whole-file / compacted / `retention.py`'s | 3 | **yes** — two costed, the third shown to be unusable |
| index step subtracted from the prior day | 2 | **no** — only the subtracted version is printed |
| 2026-08-30 `db-sizes` baseline: pre- / post-index | 2 | **now yes** — an earlier version used both silently; §5 |

Roughly 150 nominal combinations; this document prints 8 rate figures and 5
clock rows. **Six of eight degrees of freedom are now disclosed. Two of the
gaps were not choices but errors** — the mixed baseline (§5) and the
un-normalised 24.075-hour divisor (§3) — and both are recorded rather than
quietly repaired.

The choice of headline was fixed by the two cuts in §2 **before** the anchor
sweep was run, so the sweep is a robustness check and not a search. Nothing was
computed and dropped. The pooled 105.78 MB/day is printed *because* it is the
most flattering of the four windows and would otherwise be the figure a later
session re-derived and believed.

## 9. What this does NOT establish

- **n = 1 day.** One 24-hour window, one MLB slate, one instrument. The
  second day available is contaminated by a deploy, an index build and a WAL
  migration, and it is quoted in §3 rather than averaged in. **A second clean
  day is one day of waiting and would double the evidence.**
- **It does not attribute the growth to any table.** §5's baseline is pinned
  to a 1.93-hour window by this document's own series, which is better than it
  was, but the interval is still 44.4 ± 1.0 h and two columns
  (`idx_fair_link`, `idx_fair_market_computed`) were not measured on the
  earlier date at all. **The residual is not a check**: it is defined as
  `file total - subtotal` and absorbs those two indexes plus schema overhead,
  so there is no arrangement of the numbers under which it would fail to
  close. §5 is a **composition, not a rate, and not a corroboration** of §3.
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
- **Whether the free list saturates, which could move the clock on its own.**
  §5 measures it *accumulating* at 39.7% of organic bytes, while
  `backend/store/retention.py:48-52` asserts freed pages are reused and "the
  growth stops even without" a `VACUUM`. If that assertion is right and the
  list saturates, **the rate falls passively and the date moves out with nobody
  doing anything.** This is the largest single uncertainty in the document and
  n = 1 window cannot resolve it. §6's "what would move it the other way" lists
  three deliberate actions and this is not one of them.
- **That a `VACUUM` was ever possible on this box.** §7's rule is an untested
  belief recorded in two comments; its temp-file justification is refuted by
  the `/tmp` measurement and a WAL-mode justification survives untested. The
  two give opposite answers.
- **How large the slate was on the measured day.** Recorded for tonight (14
  MLB fixtures) and not for 2026-08-31. The rate is per calendar day; the
  process is per slate; the slate count of the measured window is unknown, so
  neither §6's nor §7's scaling of it is anchored.
- **Reproducibility beyond the committed pull.** The 3,904-line series is
  committed beside this file as
  `docs/measurements/2026-09-01-loop-rss-samples.jsonl` so every number in §2,
  §3 and §10 can be re-derived, but **the differencing itself was ad hoc** —
  there is no harness in the repo and no test pinning any of it. §10 also
  means the live source file begins truncating around 2026-09-04, after which
  this window exists only in that committed artifact.
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
   reach is the newest 8,000 lines, ≈ **6.0 days** — and that is a pooled mean, since the flat zones run at ~130 s a
   sample against ~65 s overall, so the post-truncation reach is longer in
   quiet periods and shorter across a burst.
2. **`RSS_LOG_KEEP_LINES` and `RSS_LOG_CAP_BYTES` are inconsistent at the
   current line width, and the trim will never converge.** The docstring
   assumes ~80 bytes/line; the line gained eleven fields on 2026-08-29/30. The
   width is **observed, not reconstructed**:
   `(1,107,464 − 708 × 81.1) / 3,196 =` **328.5 bytes** for a post-`db_kb`
   line, while the newest shape reconstructs at 366 (the gap is that early
   post-`db_kb` lines omit the `wal_ckpt_*` keys rather than writing them as
   null). At the conservative end `8,000 × 328.5 = 2,628,352` bytes, **1.25x**
   the 2,097,152 cap; at the newest width, 1.40x. An earlier version used the
   366 reconstruction where an observation was in hand, overstating the defect
   by 11%; **the conclusion holds at either width.** So from ~2026-09-04 the
   file is *always* over the cap: every pass reads ~2.6 MB, splits it, keeps
   8,000 lines and rewrites ~2.6 MB — ~5.3 MB of I/O per pass, ~7.0 GB/day, on
   the
   volume this document is about and against the WAL for the same disk. The
   log stays bounded (the line count converges even though the byte count does
   not), so this is a cost, not a leak. `WALK_LOG_*` has the same shape and is
   safe: ~110 bytes × 8,000 = 880,000, inside the cap.

**The existing test cannot catch this, and the reason is the shape worth
carrying.** `tests/test_teardown_is_recorded.py:316-329`
(`test_the_cap_keeps_the_newest_lines`) fills the log with a **44-byte**
synthetic line and asserts `len(lines) <= RSS_LOG_KEEP_LINES`. At 44 bytes,
8,000 lines is 352,000 bytes and comfortably inside the cap, so the assertion
passes; at the observed 328.5 bytes it is 2.63 MB and the assertion still
passes,
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
- **`fly.live.toml:577` still says 0 B/day.** §8 names a second mechanism
  sufficient to produce that reading; the source document names a first. This
  measurement does not separate them, and the config comment is wrong either
  way.
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

**Every date below is n = 1 day and carries the §4 bracket** — read them as
±3 days on the method spread alone, and earlier still if NFL widens the slate.

```
  db_kb  >  2,444,260 KiB     the VACUUM margin is gone, IF §7's     ~2026-09-02
                              untested rule holds (15.5 d still left)
  db_kb  >  3,500,000 KiB     ~8.8 days of headroom left             ~2026-09-08
  db_kb  >  4,400,000 KiB     ~3.1 days; extend from a laptop now    ~2026-09-14
  db_kb  >  4,708,789 KiB     the 184 MB a burst's WAL needs is      ~2026-09-16
                              all that is left
  db_kb  >  4,888,520 KiB     free space is zero, and only if the    ~2026-09-17
                              WAL is empty at that instant
```

The fourth row is the one that matters more than the fifth: §4 reserves
184.04 MB because the WAL reached 179,731 KiB during the measured burst, so
`cockpit.db` cannot actually have the last 184 MB. The fifth row is the
arithmetic limit `(2,413,142,016 + 2,592,702,464) / 1024` and assumes a WAL of
zero, which no burst leaves.

**This table alarms on `db_kb` only**, so it cannot fire on WAL growth, on the
free list, or on anything else that lands on `/data`.

The first row is the one worth wiring, because it is the only threshold whose
*repair* is cheaper before it than after it. The last is arithmetic:
`(2,413,142,016 + 2,592,702,464) / 1024`.

A refinement the burst shape suggests: alarm on the **daily** delta rather
than the level — `db_kb` today minus `db_kb` 24 hours ago — because a rate
that doubles when NFL opens is visible a week before a level threshold
notices.
