# 2026-09-18 - where the 6.48 GB is, and the VACUUM window runs on a filesystem nobody had read

Instruments, all committed scripts invoked by path over `flyctl ssh console`:
`inspect_live_db.py db-sizes --i-accept-the-cache-flush --json`,
`inspect_live_db.py loop-rss -n 20000 --limit 20000 --json`,
`inspect_live_disk.py --json` and `--root / --top 5 --json`.
Audited by `measurement-skeptic` before entering the record; two first-draft
claims were refuted and the corrections are kept in place rather than repaired.

`db-sizes` was run TWICE. The first run was piped through `tail` and the head of
the output - the file-level section and every large btree - was discarded. That is
the failure this project's own notes record for ssh output, and it cost a second
full-file walk that nothing else needed.

The body below is the text posted to issue #58 as Amendment 3, verbatim.

---

## Amendment 3, 2026-09-18 — the `db-sizes` run, and it moves the question twice

Joe asked for the real table split before picking a retention horizon. Measured
on live 2026-09-18 with `db-sizes`, `loop-rss` and `inspect_live_disk.py`, all
committed scripts by path. A `measurement-skeptic` pass audited every figure
below and refuted two of my first-draft claims; both corrections are kept here
rather than quietly repaired.

**Terms.** *Index*: a separate sorted copy of a few columns that lets the
database find rows without reading them all — costs disk, and costs a write on
every insert. *Free list*: pages a delete released inside the file, reusable by
the next insert but **not** returned to the operating system. *VACUUM*: the
rebuild that does return them.

### Where the 6.48 GB is

| family | table | indexes | total | share |
|---|---|---|---|---|
| **`odds_snapshots`** | 0.85 GB | **1.75 GB** | **2.60 GB** | **40.1%** |
| `fair_prices` | 1.74 GB | 0.72 GB | 2.46 GB | 37.9% |
| `kalshi_quotes` | 0.66 GB | 0.54 GB | 1.20 GB | 18.5% |
| everything else (118 btrees) | | | 0.22 GB | 3.4% |

Section B sums to within one 4,096-byte page of section A net of the free list,
so the census is complete.

**Two thirds of the `odds_snapshots` footprint is index, not data** — 851.7 MB
of rows under 1,747.3 MB of index, a ratio of 2.05x:

    idx_odds_sport_commence  558.9 MB     idx_odds_event_commence  248.8 MB
    idx_odds_event           479.6 MB     idx_odds_commence         84.8 MB
    idx_odds_window          375.2 MB

**Correction owed.** I said this refutes *"CLAUDE.md's 'two thirds is
`kalshi_quotes`'"*. **That sentence is not in CLAUDE.md and never has been** —
zero matches for `kalshi_quotes` or "two thirds" in the file or in any commit of
it. The only place it exists is `tasks/NEXT.md` asserting that CLAUDE.md says
it. What is true and measured: `kalshi_quotes` is **18.5%**, and its family has
been flat at ~1.2 GB for nine days while its writer inserts ~5,300 rows every
15 seconds. That is a measured statement that **its prune is working**.

### What a retention horizon buys — and it is not the lever

| horizon | rows deleted | pages freed |
|---|---|---|
| 90 days | **zero** | zero |
| 30 days (`fetched_ms`) | the oldest, thinnest slice | ≤~34 MB of table + its index entries, so **~100 MB of family pages** |

The database is **42 days old** (first commit 2026-08-07), and the vendor's
historical endpoints have never been called, so nothing older exists. The
30-day cut falls on 2026-08-19 — the date `backend/store/retention.py` recorded
the table at 33.6 MiB. That figure has no instrument behind it; it is a bare
docstring number with no method and no statement of whether it included
indexes. Treat ~100 MB as an order of magnitude, not a measurement.

**"A season" is undefined on this ticket and the answer depends on which
definition you mean.** As *row age* it deletes zero. As *"drop fixtures from a
completed season"* it is keyed on the fixture, not the row, and does not stay
at zero. Say which you mean, or the answer is to a different question.

### The constraint that decides the SHAPE of any rule

Eleven production readers take `MIN(commence_ms)` **per fixture over that
fixture's entire snapshot history** — the scorer (`scoring.py:172`), the ledger
(`routers/ledger.py:340`), the slate (`routes.py:1423`, `:4728`), the gate
(`gate.py:955`), parlays (`parlays.py:668`, `:2584`), scout
(`routers/scout.py:68`). **Deleting a still-referenced fixture's oldest rows
silently moves its recorded kickoff time.** `parlays.py:682-687` says the time
filter is deliberately absent for exactly that reason.

**So the safe shape is per-fixture, never per-row**: drop whole fixtures that
nothing links, via `event_links.odds_event_id` — the same escape hatch
`kalshi_quotes` uses through `recommendations.ticker`. A row-age rule is a data
corruption with no symptom.

### Cull-then-VACUUM: your understanding is right, plus one addition

Deleting rows **never** shrinks the file; freed pages go to the free list.
Culling before the window shuts buys two things, not one: a smaller file after
the `VACUUM`, **and a smaller `VACUUM` requirement**, because the rebuild is
sized by the data that survives it. So culling widens the window as well as
using it. After it shuts, culling still stops growth but parks the instance at
20 GB. `PRAGMA auto_vacuum` cannot be switched on retroactively without a full
`VACUUM`, so it is not an escape.

**A `VACUUM` today, deleting nothing, returns *at least* 49.5 MB** — the free
list is 12,096 pages. That is a **floor, not the yield**: `db-sizes` sums
`pgsize` and not `dbstat.unused`, so every partially-filled page is charged at
full price and counted as zero reclaimable. `VACUUM` repacks at ~100% fill, and
`idx_quotes_ticker_time` (535 MB, random insert order, continuously pruned) and
the five `odds_snapshots` indexes are exactly that shape. **The real yield is
plausibly several hundred MB more and nobody has measured it.** One extra
column on the next `db-sizes` run settles it.

### THE FINDING THAT MOVES THE CLOCK — and it is the opposite of reassuring

The 11–27 day window rests on an assumption nobody tested: *"`VACUUM` needs
roughly the whole file free on the same filesystem."* Two things are now
measured and neither was in the arithmetic.

**1. There are two filesystems, and the tighter one was never looked at.**

    /data  free 13.74 GB   (the volume)
    /      free  7.87 GB   of 8.35 GB   (the container root)
    cockpit.db 6.48 GB

A plain `VACUUM` builds its temporary copy in `SQLITE_TMPDIR` / `TMPDIR` /
`/var/tmp` / `/tmp` unless `temp_store_directory` is set — **on this container
those are the root overlay, not the volume.** Root free is 7.87 GB against a
6.48 GB file: it fits today with **1.39 GB of margin**. At the measured growth
rate that margin is gone in **roughly 15 days** — tighter than either /data
clock, and it was not in anyone's arithmetic.

**2. The fix is a one-word change to the command, and it is available today.**
`VACUUM INTO '/data/cockpit-compacted.db'` writes to a path you choose, needs
exactly 1x the surviving data on *that* filesystem, and /data has 13.74 GB
free. It is also non-destructive — the original is untouched until you swap.
**Name `VACUUM INTO`, not `VACUUM`, in whatever gets built.**

The remaining unknown is whether the copy-back of a plain `VACUUM` in WAL mode
needs 1x, 2x or ~3x. At 2x the window is ~3 days; at 3x it is already shut.
`VACUUM INTO` makes that question moot, which is why it is the recommendation
rather than a footnote.

### The growth rate — reconciled, and the 137 was contaminated

Two instruments that share no code now agree, and the old figures are explained
rather than dismissed:

- `db_kb` from the pass log, whole surviving span (46.5 h): **82.5 MB/day**
  (82.3 on `db_kb + wal_kb`, so the WAL is not moving it).
- dbstat differencing against the 2026-09-09 read, like-for-like on the three
  indexes that existed at both ends: **76.6 MB/day**; whole file net of the two
  new index builds: **87.4 MB/day**. That window is 8.94 days and **contains an
  NFL Sunday and two Saturdays**, which the 46.5-hour window does not.

**The 137 MB/day figure was never wrong as a file slope — its window contained
624 MB of one-time index builds** (`idx_odds_event_commence` v39 and
`idx_odds_window` v41, both committed 2026-09-10, 248.8 + 375.2 MB) smeared
across it as if they were a rate. That is ~70 MB/day of the 157.

So: **~85–110 MB/day, floor 82.5.** Against 3.632 GB of /data headroom that is
**~38 days** — but the root-filesystem clock above is ~15 days, and it binds
first unless `VACUUM INTO` is used.

**I am not proposing that `CURRENT_GROWTH_RATE` be lowered.** `volume.py:50-72`
argues that leaving it high is the safe direction, and a rate that is too high
makes every disk tier fire early rather than late. That argument stands.

**And a plan in the record does not work:** `tasks/NEXT.md` and
`volume.py:69` both say the correction wants a multi-day slope "which
`inspect_live_db_loop.py`'s `db_kb` series can supply." It cannot —
`RSS_LOG_CAP_BYTES` is 2 MiB trimmed to 1 MiB, so the file holds 1–2 days and
can never reach a week. dbstat differencing is what supplies it.

### Two corrections to the record

- **"`kalshi_quotes` and `fair_prices` are pruned" is false about
  `fair_prices`, and you were handed it as an input to this decision.** Its
  downsample is registered, built, tested and **off**:
  `FairPriceDownsampleConfig.enabled` defaults `False`, `dry_run` defaults
  `True`, `fly.live.toml` sets neither. That is **not** an oversight and is
  **not** being reopened — the 2026-09-01 deciding run returned **NOT WORTH
  ARMING** (36,039,175 bytes freed against a 322,800,000 threshold; the rule
  reaches 4.0% of rows) and the verdict tracks the eligible *fraction*, which
  has not moved. What bounds `fair_prices` is ADR 0133's write-time dedup. The
  conclusion — `odds_snapshots` is the only unbounded table — survives, by a
  different fact.
- **Nothing re-runs a devig over historical rows.** `schema.sql:210-213` gives
  "the ability to re-run with a different method" as *the* reason for storing
  raw, and that capability has **no exerciser anywhere** in `backend/` or
  `scripts/`. Every devig call site is fed by the four newest-sweep readers.
  Stated because it bears on how much the old rows are worth; not a proposal to
  delete anything.

### On keeping the history off-box

You asked whether a personal Drive copy is worth it, and whether historical
analysis would help. **No, and the reason is Rule 3.** Validate against
Kalshi's own close — and Kalshi's candlesticks are perishable, measured at
**~80 days**, after which the market delists and its history goes with it
(ADR 0011 addendum, ADR 0016). A sportsbook snapshot older than that has
nothing left to be scored against. And the half you would archive is the
**repurchasable** one: The Odds API keeps snapshots back to 2020-06-06 on a
5-minute grid, permanently, at 10x credits.

`store/publish.py` already has export machinery (Parquet, zstd, 15 tables;
`odds_snapshots` is not among them and it has never run against live), so a
**one-off** is cheap if you want the option kept. A recurring job is not.

**One thing must be settled first:** ADR 0035 contradicts itself about The Odds
API's terms — `:122` asserts their data is something "we are not prohibited
from redistributing", `:186` lists their terms as "separate agreements and
**unexamined here**". Moving their data to a personal Drive is a redistribution
decision on an unread agreement.

---

## The question, re-lettered against the real numbers

**(a) Raise the auto-extend limit.** One config line. Buys time, changes
nothing structural — and note the volume is bound by *three* limits, not one:
the /data VACUUM window, the 20 GB auto-extend ceiling, and the root filesystem.
Raising the ceiling makes one of the other two bind at a new value.

**(b) Add the per-fixture retention rule now** (~80–90 days on fixtures nothing
links, justified on Rule 3 rather than on disk), and run `VACUUM INTO` while
the window is open. Deletes **zero rows today**; it is a steady-state policy,
not a remedy.

**(c) Both — my recommendation.** (b) alone does not move the disk this month;
(a) alone relaxes the bound that is not binding. Together they take the
time-sensitive action while the window is open and set the policy while it is
free.

**(d) Neither.** Defensible on the corrected clock — ~38 days on /data and ~15
on root — but the root number is the one I would not sit on.

---

**Not on this list, because it is not yours to decide:** dropping
`idx_odds_event` (479.6 MB). A plan-comparison drop-test found no production
statement uses it, but this repo has already removed an `odds_snapshots` index
for "changes no plan" and had to restore it — commit `2e66f36`, *"the plan was
never the cost."* **It needs a timing, not a plan comparison**, and it is a
one-time level against a rule that changes the slope. It stays off the sheet
until it has one.

---

## Addendum, 2026-09-18 — the 882 MB is NOT a deleted-but-still-open file

The `/data` walk has been short by ~882 MB in every reading, and the standing
explanation was a file unlinked while a process still held it open: its blocks
stay allocated, `statvfs` counts them, and `walk` cannot see it because it has
no directory entry. A container restart closes every handle, so a restart is a
free falsification — which is why it was queued against the next deploy rather
than paid for on its own.

**The deploy of `04a960c` happened. The number did not move.**

```
                       before            after          delta
unaccounted     882,346,650      882,346,308           −342
free         13,739,470,848   13,740,232,704       +762,144
cockpit.db    6,476,369,920    6,476,369,920              0
cockpit.db-shm    1,114,112           65,536     −1,048,576
```

**The `-shm` collapse is the control, and without it this result says
nothing.** SQLite rebuilds the shared-memory index file on the first connection
after every process exits; 1,114,112 → 65,536 is that rebuild. So the machine
really did stop and start — `git_sha` moved from `c8111a2` to `04a960c` and the
machine id and version are both new — and every file handle the old process
held was closed. A deleted-but-open file's blocks would have been reclaimed at
that moment.

They were not. **The hypothesis is refuted, not merely unsupported**, and the
~342-byte drift is noise on a live volume, not a partial reclaim.

**What it leaves.** The remaining candidates are things `walk` structurally
cannot reach rather than things it happened to miss: space consumed below the
mountpoint by the filesystem itself (ext4 metadata, journal, and the 5%
reserved-blocks default, which on 19.7 GiB is ~1.0 GiB and is the closest
single number to 841.5 MiB), or files under a path the walk does not descend.
**The reserved-block explanation is a candidate and nothing more here** — it
predicts a fixed quantity that never changes, which is consistent with two
readings nine days apart differing by 8,699 bytes, and it has not been checked
against `tune2fs`.

**What changes if it is the filesystem's own reserve:** nothing about the
clock. Reserved blocks were never available to `cockpit.db` in the first place,
so `free` already excludes them and the ~38-day `/data` estimate stands. What
dies is the idea that 882 MB might be *recoverable* — it is not, and the
container root, not `/data`, remains the binding constraint.
