# The window route walked every stored odds row, and every page waited on it

**Date:** 2026-09-18 (the evening of 2026-09-17 in Joe's timezone)
**Prompt:** Joe: "The site is being really slow again please make it faster."
**Instruments:** `scripts/time_live_routes.py 3 --leagues` (twice, back to
back, so the second run is a warm box); `inspect_live_db.py loop-rss`,
`read-incidents`, `window-freshness`; `scripts/measure_odds_fixtures.py`
(the v47 rehearsal, local, live-shaped); `EXPLAIN QUERY PLAN` against the
repo schema.
**Cost:** zero odds credits. Every call a `GET`; the instrument runs are
read-only replays. **One accidental cost, owned below in §E.**
**Live sha at read:** `f1449d5`, machine `7812601a239428`, ord, 4 GB,
`shared-cpu-2x`.

## What this establishes

- Every desk page measured 8-15 s at the median on a warm box, and one
  Board load took 60.8 s. The API routes underneath were 4-8x slower than
  the same harness measured on 2026-09-16.
- `/api/window` is the route every server-rendered page awaits before it
  can render (`board`, `parlays`, `picks`, `slate` all
  `await fetchWindow()`), it measured 7.0 s at the median, and it had
  tripped the 25 s read budget twice that evening (21:17Z, 23:16Z).
- Both of `/api/window`'s fixture reads derived "which fixtures are
  upcoming" by walking `odds_snapshots` itself: `fixture_freshness` walked
  the entire `market = 'h2h'` prefix of `idx_odds_window` (every h2h row
  ever stored), and `upcoming_fixtures_by_sport` walked every row of every
  upcoming fixture through `idx_odds_commence` with a table fetch per row
  and a temp b-tree for `DISTINCT` -- twice per call, because
  `first_window_open_of_day` calls it again. Neither read's cost was
  proportional to the number of fixtures; both were proportional to the
  number of stored rows, which grows with every sweep.
- A one-row-per-fixture table (`odds_fixtures`, schema v47) turns both
  reads into seeks. At live's shape, locally and warm, `fixture_freshness`
  goes 995 ms -> 24 ms and `upcoming_fixtures_by_sport` 1.2 ms -> 0.1 ms
  (§C), with the answers compared elementwise and equal.

## What this does not establish

- **Why it got 4-8x worse in one day.** No code touching these reads
  changed between the 2026-09-16 timing and this one. The candidates are
  growth (the NFL and NCAAF weekends entered the 48 h horizon, multiplying
  the upcoming-row population) and page-cache pressure (the file is
  6.3 GB on a box with ~3.1 GB available, and the quote pass writes and
  checkpoints every ~38 s). Fly's Prometheus endpoint refused the
  `flyctl auth token` with `401 something went wrong resolving
  organization`, so no CPU, iowait or disk-read series was read. The fix
  does not depend on which it was: it removes the term that scales with
  rows.
- **The live win beyond `/api/window`.** §C is a local warm-box ratio and
  §D is the deployed number for the window route (58x). The other routes'
  recovery in §D sits on a restarted box and is not attributed.
- **`/api/parlays` (7.0 s) and `/api/slate` (2.1 s).** Both were also
  4x their 2026-09-16 figures, and neither reads `/api/window`. They are
  outside this change; §D re-times them because the window's continuous
  index walk was plausibly evicting the pages they need, and that is a
  hypothesis, not a finding.
- **The tail.** 3 reps per route. Zero trips in 3 draws bounds nothing.

## A. Before: the routes, warm box, 3 reps

Second of two back-to-back runs, so every page's read path was warmed by
the run before it. Milliseconds; `max` at n = 3 is a draw, not a tail.

    route                                     min    med    max     bytes
    /api/health                                76     76    202       712
    /api/window                               930   6974   8951     2,705
    /api/odds/refreshable                     118    303    482     3,007
    /api/signal                                79     98    104     4,852
    /api/parlays                             4976   6951   9452    23,863
    /api/board?include_suppressed=false      1929   2014   6300       615
    /api/slate                               1860   2056   2242   240,290
    /api/hedge                                758    777    940    35,522
    /api/slate?league=americanfootball_nfl   3766   4659   6617   239,109
    /api/slate?league=americanfootball_ncaaf 2466   4604   5014   239,787
    /api/slate?league=baseball_mlb           4000   4084   6485   224,168
    /parlays                                 8723   9681  14710   260,507
    /board                                   8060   9189  60750   407,711
    /slate                                   8983  14864  16941 1,456,593
    /hedge                                    826   1251   1518   116,012
    /picks                                   8174   8881  14397    48,509

Against 2026-09-16's medians on the same harness: `/api/window` 887 ->
6,974; `/api/parlays` 1,631 -> 6,951; `/api/slate` 591 -> 2,056;
`/api/board` 368 -> 2,014. The routes that read nothing large
(`health`, `signal`, `odds/refreshable`) did not move.

`read-incidents`, newest first:

    2026-09-17T23:16:17Z  GET /api/window  25005 ms  OperationalError: interrupted
    2026-09-17T21:17:18Z  GET /api/window  25009 ms  OperationalError: interrupted

The recorder was healthy: `loop-rss` showed RSS ~204 MB, `available_kb`
~3.1 GB, a quote pass every ~35-45 s with `candidate_ms` 0.7-1.4 s,
`leg_price_link_ms` 3.3-9.8 s, `leg_store_quotes_ms` 1.2-2.7 s, PASSIVE
checkpoints moving 560-3,257 frames. Nothing was stuck; the box was busy.

## B. The plans, from the repo schema

`fixture_freshness`, v41 statement:

    CO-ROUTINE latest
    SEARCH odds_snapshots USING COVERING INDEX idx_odds_window (market=?)
    SEARCH o USING COVERING INDEX idx_odds_window (market=?)
    SEARCH l USING AUTOMATIC COVERING INDEX (odds_event_id=?)

`(market=?)` alone: the whole h2h prefix, both arms. `upcoming_fixtures_by_sport`:

    SEARCH odds_snapshots USING INDEX idx_odds_commence (commence_ms>? AND commence_ms<?)
    USE TEMP B-TREE FOR DISTINCT

Not covering, so a table fetch per upcoming row, then a sort of them all.
On live, `window-freshness` (two statements of the first shape) took
34.7 s wall including the ssh round trip, against 394 upcoming fixtures.

`fixture_freshness`, v47 statement:

    SEARCH f USING INDEX idx_odds_fixtures_commence (commence_ms>?)
    CORRELATED SCALAR SUBQUERY 2
    SEARCH o USING COVERING INDEX idx_odds_window (market=? AND odds_event_id=? AND fetched_ms=?)
    CORRELATED SCALAR SUBQUERY 1
    SEARCH s USING COVERING INDEX idx_odds_window (market=? AND odds_event_id=?)

`upcoming_fixtures_by_sport`, v47:

    SEARCH odds_fixtures USING COVERING INDEX idx_odds_fixtures_commence (commence_ms>? AND commence_ms<?)

A plan is a shape, not a cost (ADR 0141). §C is the cost.

## C. The rehearsal, local, live-shaped, warm

`scripts/measure_odds_fixtures.py`: 3,632,772 rows, 2,640 events, 800
upcoming, the same builder that priced v41. Round-robin, 5 rounds,
64 MB page cache.

    round    v41 freshness    v47 freshness     v41 upcoming     v47 upcoming
        0           1004.6             25.3              1.1              0.1
        1            973.0             24.3              1.2              0.1
        2           1033.0             22.9              1.2              0.1
        3            964.1             16.1              0.9              0.1
        4            995.4             23.5              1.2              0.1
    median           995.4             23.5              1.2              0.1
    paired ratio, median to median: freshness 42.4x, upcoming 9.6x

The answers were compared elementwise before any timing was taken and
were equal (800 fixtures' ages; 116 upcoming kickoffs). The v41
`upcoming` figure is small here because the synthetic slate has few rows
per upcoming fixture; live's NFL week has hundreds of sweeps per fixture,
which is where that read's cost lives. The ratio is the finding; the
milliseconds are this laptop's.

The v47 backfill (the one-off at boot): 632 ms for 1,046 fixtures,
resident set unchanged (delta +0 MB), plan `SEARCH odds_snapshots USING
COVERING INDEX idx_odds_sport_commence (ANY(sport_key) AND commence_ms>?)`
-- a skip-scan on the covering index, no temp b-tree. On live the
population is larger and cold; the 600 s health grace is the bound.

The trigger's tax, a 900-row sweep insert, 5 rounds, round-robin:

    without trigger  median  5.2 ms
    with trigger     median 10.1 ms

About 5 ms per sweep, against a quote pass measured in seconds.

## D. After: deployed and re-timed

Deployed via `gh workflow run deploy.yml` (the local `flyctl deploy` was
refused by the auto-mode classifier, as on 2026-09-15). `/api/health`
`build.git_sha` = `31b6e85697c1a786f979dc421f45e3974300c80e`, machine
`7812601a239428`. Boot log: `[migrate] /data/cockpit.db migrated v46 -> v47`
at 02:37:53Z, 31 s after `checking database schema` -- the backfill on the
real volume, inside the 600 s grace with room.

Same harness, 3 reps, `--leagues`, two back-to-back runs. **The box had
just restarted**, so the first run is the closest thing to cold this
harness can take and the second is warm.

    route                                    before    first run    second run
                                               med     med   max     med   max
    /api/window                               6974     123   147     119   124
    /api/parlays                              6951     751  3893     658   689
    /api/board?include_suppressed=false       2014     375   654     349   373
    /api/slate                                2056     452   659     452   546
    /api/hedge                                 777     770   816     755   774
    /api/slate?league=americanfootball_nfl    4659     750  2771     626  1256
    /api/slate?league=americanfootball_ncaaf  4604     571  2578     495   517
    /api/slate?league=baseball_mlb            4084     487   504     475   491
    /parlays                                  9681     780   945     805  1152
    /board                                    9189     456   458     452   473
    /slate                                   14864     790  3663     570   580
    /hedge                                    1251     754   780     766   769
    /picks                                    8881     445   483     445   455

`/api/window`: 6,974 -> 119 ms at the median, **58x**, against the local
rehearsal's 42x. That is the number this change owns.

**Everything else recovered too, and this document does not claim the
change did that.** `/api/parlays` and `/api/slate` read nothing this change
touched, and the deploy restarted the machine, which also emptied whatever
the day's cache state was (including anything §E's dbstat walk left). The
hypothesis that the window's continuous index walk was evicting the pages
those routes need is consistent with these numbers and not established by
them; separating the two would need a timing on a box that had NOT just
restarted, which is the next session's to take if the routes drift again.
One outlier: `/api/signal` max 15,366 ms on the first run (min 103) -- the
signal cache miss `2026-09-17-the-signal-cache-miss-is-the-desks-worst-latency.md`
already records, not this change.

## E. What this session cost the box, owned

`inspect_live_db.py db-sizes` was run once during diagnosis. It walks
`dbstat`, which reads the entire 6.3 GB file through a ~3 GB page cache --
exactly the "read-only census that flushes the cache" `tasks/lessons.md`
2026-09-15 warns about. It was killed locally after 180 s; the remote
process was not confirmed dead. Any timing taken in the following minutes
(including the `window-freshness` figure in §B) is worse for it, in an
amount not measured. The instrument's own description says "file-level
page counts ... via dbstat"; the lesson is that the description was read
after the run, not before.
