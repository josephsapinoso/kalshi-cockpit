# The candidate scan, three index shapes — 2026-08-30

Instrument: `scripts/measure_odds_scan_index.py`, which imports
`runner.MATCH_CANDIDATE_SQL` rather than transcribing it, so the statement
timed here is the statement the pricing pass executes. Live btree sizes read
the same day with `scripts/inspect_live_db.py db-sizes`.

Command:

    .venv\Scripts\python.exe scripts\measure_odds_scan_index.py --rows 1500000 --repeats 7

## What this establishes

The **ordering** of three index shapes for the candidate scan, the query plan
each produces, and what the winning shape costs to build and to write into.

## What this does NOT establish

- **It is not the live table.** 1.5M rows, four sports at 55/20/15/10, ~350
  fixtures spread over −30d to +14d, eight bookmakers, two markets — modelled
  on the live shape, not sampled from it. The *ordering* is what this supports.
  The absolute milliseconds belong to this machine, this page cache and this
  distribution.
- **It does not reproduce the 27.7 s.** That came off the live box under a pass
  competing with the API's read connections. Nothing here recreates that
  contention, so this understates both the problem and the win.
- **The write cost has no concurrent reader.** Real amplification on live
  competes for the same connections and the same 2 GB of RAM.
- **The index size understates live.** Synthetic team names and event ids are
  short and uniform; real ones are neither.
- **`n` is one machine and one build of SQLite.** A different SQLite could pick
  a different plan. `tests/test_candidate_scan_plan.py` is what would catch
  that, not this document.
- **It says nothing about retention.** The index changes the constant. The
  growth term is untouched.

## Plan, by index shape

Machine-independent, and reproduced identically at 20,000 rows and at 1.5M:

    baseline   SEARCH odds_snapshots USING INDEX idx_odds_commence (commence_ms>?)
               USE TEMP B-TREE FOR DISTINCT

    narrow     SEARCH odds_snapshots USING INDEX idx_probe (sport_key=? AND commence_ms>?)
               USE TEMP B-TREE FOR DISTINCT

    covering   SEARCH odds_snapshots USING COVERING INDEX idx_probe (sport_key=? AND commence_ms>?)

The narrow form restricts the seek and leaves both remaining costs standing: a
table fetch per surviving row for the three projected columns, and the sort.
The covering form removes both, and the `DISTINCT` becomes a walk in index
order. **A plan without `USE TEMP B-TREE` is a different algorithm, not a
faster one.**

## Timings — 1,500,000 rows, 266 MB file

520,160 rows sit at or after the 24-hour floor across all sports. That is the
scan the predicate cannot avoid, to keep **73 distinct fixtures**.

| shape | plan | read cold | read warm p50 (n=7) | sweep write p50, 900 rows (n=15) | index | build |
|---|---|---|---|---|---|---|
| baseline | index + temp B-tree | 443 ms | **394 ms** (345–442) | 3 ms (3–10) | — | — |
| narrow | index + temp B-tree | 276 ms | **283 ms** (213–323) | 4 ms (4–11) | 47.0 MB | 1.8 s |
| covering | covering index | 1 ms | **0 ms** (0–0) | 7 ms (6–22) | 52.8 MB | 3.0 s |

**All three return the same 73 fixtures, compared as sets and not as counts** —
the script refuses to report otherwise. An index that changes the answer is not
a faster index.

### Reading the three columns together

- **The narrow form buys 28% and the covering form buys the query.** 394 → 283
  is a constant-factor improvement on the same algorithm; 394 → 0 is the sort
  and the table fetches ceasing to happen. This is the whole argument for
  paying five columns instead of two.
- **The write roughly doubles and stays trivial**: 3 ms → 7 ms per 900-row
  sweep. Against a read that was costing 394 ms every pass, and 27.7 s on live
  under contention, +4 ms per sweep is not a trade that needs deliberating.
- **The 0 ms is a skip, not a cache artifact.** It holds on a freshly opened
  read-only connection (1 ms cold), and the mechanism is visible in the plan:
  with the projected columns in key order the engine seeks past each run of
  duplicates instead of reading 286,000 index entries to find 73 answers.

### One correction to how this was first measured

The write column originally read **10 / 13 / 4 ms** — one 900-row batch per
configuration — an ordering in which the configuration with the *extra* index
was the fastest. That is not a result, it is the spread, and it was `n = 1`.
Repeating fifteen times per configuration produced the coherent 3/4/7. **This
repo's own rule caught it: read `n` before the effect size.**

## THE LIVE RESULT — taken after the v31 deploy, same day

Everything above is synthetic. This section is the real box, and it exists
because the synthetic run is only worth what it predicts.

**Before**, from `docs/measurements/2026-08-30-loop-rss-samples.jsonl` — the
893-row series committed earlier the same day, `candidate_ms` present on 182
passes, `candidate_rows` p50 162:

    min 419   p50 438   p90 459   p99 5451   max 11202

**After**, `loop-rss -n 12` on live at 00:02–00:06Z, `candidate_rows` 155, all
twelve values sorted:

    59 59 60 60 60 60 61 61 62 63 75 76     p50 60.5

**p50 438 ms → 60.5 ms, 7.2x.** The two largest (75, 76) are the two most
recent passes, which are also the two carrying a WAL checkpoint — one of them
a `TRUNCATE` at 74 MB with `wal_ckpt_busy = 1`. Noted, not explained: twelve
passes cannot separate a checkpoint effect from ordinary variation.

**The synthetic model predicted the "before" to within 10%** — 394 ms against
the live 438 ms — which is the strongest evidence available that the modelled
row count, sport mix and fixture spread were representative. That agreement was
not designed in; the synthetic figure was fixed before this series was read.

**The "after" is 61 ms, not the synthetic 0 ms, and the gap is expected.** Live
carries real strings in a 150 MB index rather than short uniform ones in a
52.8 MB index, on a shared-cpu-1x box, four minutes after a boot with a cold
page cache. The plan is the same; the constant is not.

### What the live read does NOT establish

- **The tail is unassessed.** n = 12 after, against a before-distribution whose
  p99 was 5,451 ms and whose max was 11,202. Twelve passes cannot see a tail
  that appeared in roughly one pass in a hundred. **The pathological case is
  not shown to be gone — only absent from a small sample.**
- **All twelve passes are within four minutes of a boot**, so the page cache is
  cold-to-warming. The steady-state figure could move in either direction.
- **`candidate_rows` differs slightly** (162 before, 155 after): a different
  slate, not a controlled variable. Too small to matter at this effect size,
  and named rather than hidden.
- **Nothing here isolates the index from the deploy.** The machine restarted,
  which resets the WAL and the page cache. The plan assertion in
  `tests/test_candidate_scan_plan.py` is what ties the improvement to the
  index; this series alone could not.

### The size prediction, scored

The ADR predicted the live index would land between `idx_odds_event`'s 136 MB
and the table's own 244 MB, and that the volume would go ~41% → ~46%:

    idx_odds_sport_commence   150,302,720   36,695 pages     <- actual
    idx_odds_event            137,302,016   33,521 pages
    odds_snapshots            245,743,616   59,996 pages
    database total          2,251,366,400   45% of the 5 GB volume

Both held. The synthetic estimate of 52.8 MB understated the real index by
**2.85x**, in the direction the caveat named — synthetic team names are short
and uniform where real ones are not. **The bracket was useful and the point
estimate was not**, which is the reason a bracket was published.

## Live sizes, for the write-amplification cost

Read 2026-08-30 from `/data/cockpit.db` — 2,072,317,952 bytes on a 5 GB volume,
18.9 MB reclaimable by VACUUM:

    odds_snapshots      244,387,840   59,665 pages   13 columns
    idx_odds_event      136,421,376   33,306 pages   TEXT, TEXT, INTEGER
    idx_odds_commence    25,092,096    6,126 pages   INTEGER

**The live index will exceed the synthetic 52.8 MB.** `idx_odds_event` is 56%
of its table with two TEXT columns; the new one has four. Expect it between
`idx_odds_event`'s 136 MB and something under the table's own 244 MB — that is
a bracket, not an estimate, and **the real figure is to be read with `db-sizes`
after the first boot on v31 and recorded here.** Even the top of the bracket
takes the volume from ~41% to ~46%.

For context on the same volume, the two larger unretained btrees:
`fair_prices` 529,326,080 and `kalshi_quotes` 451,235,840, plus
`idx_quotes_ticker_time` at 398,708,736.

## The objection this had to answer

`fly.live.toml`'s `[[vm]]` comment, written after the box OOM-killed its own
loop on 2026-08-19: *"A larger index eats a larger cache."*

It is the right objection and the answer is not "the index is small". It is
that **this index reduces the page traffic of the query it serves**. Today the
pass drags ~520,000 table rows through a page cache that measured 27–135 MB
against a 1.5 GB database; afterwards it walks a contiguous index range and
touches the table not at all. Resident bytes go up by the size of the index;
bytes moved per pass go down by orders of magnitude.

## Follow-ups this does not close

1. ~~Read the real index size on live.~~ **Done, above: 150.3 MB.**
2. **Time the index build on live.** Still not measured. The grace period was
   raised 40s -> 120s to cover it and the deploy succeeded, which bounds the
   build below the point where the health check would have failed -- but the
   deploy log was never read for the actual duration, so the margin is unknown.
3. **Re-read `candidate_ms` once the box has been up for hours.** All twelve
   after-samples are within four minutes of a boot, and the tail is unassessed
   at that n.
4. **`odds_snapshots` still has no retention rule.** `store/retention.py` says
   so in its own "what this does NOT do". This buys headroom, not a bound.
