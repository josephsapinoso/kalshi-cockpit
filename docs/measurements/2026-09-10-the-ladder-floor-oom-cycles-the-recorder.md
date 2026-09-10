# The ladder scan floor OOM-cycles the recorder, and /hedge covers 0 of 1 live positions

Taken 2026-09-10 03:06–03:45Z on live (`4adf18f`, schema v36, machine
`7812601a239428`), read-only except for the HTTP probe described in §1, which
is what a browser does. Written before the fix shipped so the numbers cannot be
tuned to it; the post-deploy section is appended after the re-timing.

## What this establishes

- That after the v36 deploy (22:52Z 2026-09-09) the runner holds **1.10–1.23 GB
  RSS on every pass** where it held ~196 MB before, that the parlay candidate
  scan went from **~83 ms to 3,549–9,454 ms** over the same ~440 rows, and that
  the machine restarted **three times in five hours** (00:32Z, 01:04Z, 03:18Z),
  the last one caught in the kernel log as two OOM kills.
- That opening the parlay screen on this build can take the box down: the
  probe below preceded the 03:15Z kill by three minutes and the runner was the
  first process killed, not the API.
- That the one position `/hedge` watches is no longer at the venue, and the one
  position the venue holds is not on `/hedge`.

## What it does not establish

- The cost of `/api/window` and `/api/signal` on a healthy box. Both returned
  500 at 30 s during the probe and neither reads `fair_prices`; under 450 MB of
  page cache for a 5 GB file every read is disk-bound, so their standalone cost
  is unmeasured until the re-timing.
- Anything about the browser's own share (hydration, client polling). The MCP
  Chrome tab group carried no session cookie, and the timing below is the
  server's answer to the request a browser makes, not the paint.
- Whether the 00:32Z and 01:04Z restarts were OOM kills. The log buffer does not
  reach them; they are boot lines in `loop_rss.jsonl` with the pattern of the
  one that was caught.
- A rate. Three restarts in one evening is `G = 1`; it says nothing about how
  often an NFL Sunday would do it.

## 1. The probe — what a browser gets

Cookie minted from the local token (never printed), `httpx`, sequential, two
reps each, read timeout 180 s. Wall-clock from this machine, ~120 ms RTT.

```
/api/health                          200      161 ms
/api/odds/refreshable                200      343 ms
/api/hedge                           200      916 ms
/api/board?include_suppressed=false  200      305 ms min / 7,812 ms median
/api/window                          500   30,114 ms
/api/signal                          500   30,087 ms
/api/parlays                         500   30,083 ms
/api/slate                           500   31,595 ms
/parlays (SSR page)                  ReadTimeout at 180 s
```

The 30 s is Next's rewrite-proxy default `proxyTimeout` (`next.config.ts`
rewrites `/api/:path*` to uvicorn on loopback). Next answers `Internal Server
Error` and logs `Failed to proxy ... socket hang up`; **uvicorn keeps executing
the statement**, so each abandoned request goes on holding its memory behind a
client that has already left. The four pages are server-rendered with serial
awaits (`/parlays`: ladder → window → refreshable; `/slate`: four in a row), so
a page's time-to-first-byte is the sum of its backend calls.

## 2. The kill

```
03:12:12Z  Failed to proxy /api/parlays   socket hang up
03:13:26Z  Failed to proxy /api/slate     socket hang up
03:14:58Z  Health check 'health' on port 3000 has failed
03:15:05Z  Out of memory: Killed process 712 (python) anon-rss:1126076kB   <- scripts/run_loop.py
03:15:06Z  [entrypoint] CHAIN RUNNER exited -- the record has stopped growing. Restarting.
03:18:13Z  Out of memory: Killed process 672 (python) anon-rss:1884640kB   <- uvicorn
03:18:15Z  reboot: Restarting system
03:18:32Z  [entrypoint] starting chain runner (full=900s quote=15s)
```

Machine: `shared-cpu-2x`, 2,048 MB. Same machine id and volume after the
reboot; the recorder was writing again 30 s later.

## 3. The runner's own log — the attribution

`scripts/inspect_live_db.py loop-rss -n 40`, newest first, abridged. A row with
`produced_by NULL` and `rss_kb ~124000` is a boot.

```
iso                     kind  rss_kb    available_kb  candidate_rows  candidate_ms
2026-09-10T03:18:36Z    full  124284    1634900       NULL            NULL     <- boot (03:18Z)
2026-09-10T03:05:22Z    full  1139192   493816        434             4599
2026-09-10T02:39:44Z    full  1193740   457936        434             4720
2026-09-10T02:15:31Z    full  1213044   445248        435             4264
2026-09-10T01:20:24Z    full  1114024   566188        439             4489
2026-09-10T01:04:14Z    full  123920    1628376       NULL            NULL     <- boot (01:04Z)
2026-09-10T00:54:15Z    full  1194880   467952        439             5132
2026-09-10T00:32:41Z    full  124328    1640796       NULL            NULL     <- boot (00:32Z)
2026-09-10T00:22:01Z    full  1223456   437692        438             4404
2026-09-09T23:48:22Z    full  1223228   431744        442             8617
2026-09-09T23:22:50Z    full  1210916   445964        445             9454
2026-09-09T22:52:35Z    full  124416    1640992       NULL            NULL     <- boot: the v36 deploy
2026-09-09T22:51:58Z    quote 196484    1332600       445             83
2026-09-09T22:51:39Z    quote 196484    1348212       445             86
2026-09-09T22:49:35Z    quote 191984    1344148       445             80
```

Same ~440 candidate rows before and after. The scan's *result* did not change;
what it reads to produce it did. `loop_failures` #25 at 23:33Z:
`PassDeadlineExceeded: pass 2 ran past its 600s deadline` — the first full pass
after the deploy did not finish.

## 4. The mechanism

`CANDIDATE_SQL` (`backend/parlays.py`) predicates on `f.computed_ms >= ?`. Since
ADR 0133 an unchanged consensus is confirmed rather than reinserted, so
`computed_ms` freezes at first appearance and a confirmed row's freshness lives
in `confirmed_ms`, which the predicate cannot see. Lane G widened the floor to
nine days so such rows stay in scope — the reason was right. Measured by binary
search on the primary key the day before: **6,561,382 rows** inside the 9-day
floor against **138** inside the old 2-hour one.

Every one of those rows is read through `idx_fair_market_computed`, joined to
`event_links`/`kalshi_events`/the `odds_snapshots` group, and then
`ROW_NUMBER() OVER (PARTITION BY link_id, market, outcome_name,
outcome_description, outcome_point)` materialises the joined set — under
`PRAGMA temp_store = MEMORY` (`backend/store/db.py`), so the scanned-row count
becomes resident memory. That is the ~1 GB. It runs in the runner on every full
pass and every sweep pass (`scripts/run_loop.py`, for the parlay card), and in
uvicorn on `GET /api/parlays` and again on `POST /api/parlays/lookup`, each on
a fresh per-request connection with a 16 MB page cache.

With the runner resident at 1.2 GB, ~450 MB of page cache is left for a 5.07 GB
database. `/api/window`'s fixture query and `/api/signal`'s CLV report touch no
`fair_prices` row and still took 30 s: everything on the box was reading from
disk. That is why "fix the ladder query" is the right first move and is not, on
this evidence, the whole story — the re-timing decides.

## 5. The hedge screen's coverage — 0 of 1

Latest `positions` poll with `ok = 1` (id 20889, 03:25Z, `row_count 1`):

```
at the venue     KXMVECROSSCATEGORY-SHARD1-S2026DD606357A26-…   17.74 contracts  $9.686 exposure
on /hedge        KXMVECROSSCATEGORY-SHARD1-S2026FAD1B866580-…   position 1, status open, 3 legs pending
```

The recorded position is absent from the poll and `venue_settlements` carries
it: `market_result = 'no'`, settled 01:40Z. Its three leg markets all have
`kalshi_markets.result NULL` — the venue had not finalized the game markets and
the result pass runs inside the full pass that was being cancelled — so
`resolve_from_venue` (which reads that column alone) had nothing to read. The
venue position is a combination bought outside the desk; ADR 0125's writer only
sees `POST /api/manual-orders`. `parlay_position_legs` has no entry-price
column, so no "moved from" figure exists for any leg.

## 6. The rehearsal, before the deploy

Schema v37 (ADR 0134) adds a partial index and moves the predicate onto
`(computed_ms >= ? OR confirmed_ms >= ?)`. Rehearsed in the container on a
paced `sqlite3.backup` copy of the live file (5,174,534,144 bytes, 640 s to
copy at 2,000 pages per 20 ms; copy deleted afterwards, 14.01 GiB free before
and after):

```
CREATE INDEX idx_fair_market_confirmed ... WHERE confirmed_ms IS NOT NULL   181.8 s, cold
rows the partial index holds                                                   614
rows inside the 2-hour floor under the new predicate                           442   (0.0 s)
plan   MULTI-INDEX OR
         SEARCH fair_prices USING INDEX idx_fair_market_computed  (market=? AND computed_ms>?)
         SEARCH fair_prices USING INDEX idx_fair_market_confirmed (market=? AND confirmed_ms>?)
```

442 against 6,561,382: the scan reads what it did before the v36 deploy (138
then, with a larger slate now) and the window function materialises hundreds
of rows, not millions. The 181.8 s is the whole table being read once to find
the 614 rows; it exceeds the 120 s boot health grace, the container's image
cannot pre-build an index its code does not know, so the grace was raised to
600 s for this deploy with the measurement written beside it in
`fly.live.toml`.

## 7. After the deploy — the re-timing

Live on `324a53f` (ADRs 0134–0137, schema v37), same machine, migrated
`v36 -> v37` at boot in **172 s** (04:33:16Z checking schema, 04:36:08Z
migrated; the 600 s grace held), health passing 04:36:41Z. Same script, same
reps, at ~04:39Z and ~04:45Z. Two readings, and the difference between them is the finding about
`/api/window`:

```
                              before (v36)        ~3 min after boot      ~9 min after boot
/api/health                    161 ms              136 ms                 131 ms
/api/odds/refreshable          343 ms              119 ms                 102 ms
/api/hedge                     916 ms              180 ms                 128 ms
/api/board                     7,812 ms            308 ms                 268 ms
/api/parlays                   500 at 30 s         1,157 ms               1,136 ms
/api/slate                     500 at 30 s         3,355 ms               584 ms
/api/signal                    500 at 30 s         8,508 ms (77 warm)     116 ms
/api/window                    500 at 30 s         20,033 ms              1,017 ms
/parlays  (SSR)                no answer at 180 s  2,169 ms               2,124 ms
/board    (SSR)                -                   1,366 ms               1,460 ms
/slate    (SSR)                -                   1,785 ms               1,825 ms
/hedge    (SSR)                -                   164 ms                 147 ms
/picks    (SSR)                -                   1,607 ms               1,493 ms
```

The first reading was taken on a box whose page cache had been emptied
by the reboot and by the 5 GB rehearsal copy; the second reading is the
steady state. `/api/window` at 20 s was the cold box, not a second defect:
replayed read-only on live with every statement timed, `window_status` takes
**0.95 s**, of which 0.91 s is one `GROUP BY odds_event_id` over
`odds_snapshots`; on the container's loopback the route answers in 1,061 and
1,077 ms, and from outside 995–1,083 ms across three singles. One second is
what it costs, and it is fetched by every server-rendered page and polled
every 10 s by `RefreshWhenPriced` while a tab is open. That query lives in
`backend/odds/timing.py`, frozen until 10:00Z 2026-09-14; a covering index is
the obvious candidate after the freeze and is not decided here.

## 8. The runner after the deploy

```
2026-09-10T04:36:27Z  full   boot        rss 124,312 KB
2026-09-10T04:38:48Z  quote  (first build, cold)  rss 189,404 KB   candidate_rows 434   candidate_ms 5,168
2026-09-10T04:40:15Z  quote                        rss 189,032 KB   434   72
2026-09-10T04:40:35Z  quote                        rss 189,028 KB   434   73
2026-09-10T04:41:16Z  quote                        rss 189,028 KB   434   74
2026-09-10T04:41:35Z  quote                        rss 189,060 KB   434   75
```

189 MB and 72–75 ms over the same 434 rows: the pre-v36 profile
(196 MB, 80–86 ms). The first build after boot read the index cold and took
5.2 s at the same RSS — the memory is fixed independently of the cache. Zero
`Out of memory` lines in the log since the deploy; the latest `positions`
poll at 04:41Z reports zero open positions at the venue, so the reconciliation
list on `/hedge` is correctly empty, and position 1 now renders
`state: dead`, `at_venue: false`, `venue_settlement: no` with BOS `lost`, NYY
`won` (the venue finalized both leg markets once the runner stopped dying),
LAD still `pending`.

## 9. What this closes and what it does not

Closes NEXT.md item 0 by the partner's standard — every route re-timed, RSS
read, no OOM — and not merely "the index is used". Does not close the
question of `/api/window`'s one second under a 10 s poll, nor anything about
the browser's own share, which was never measured.
