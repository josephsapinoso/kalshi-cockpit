# Next — your checklist

**How this file works.** This file holds the **current state**: the latest
session entry, plus what is still open. Every earlier session entry is in
`tasks/archive/next-YYYY-MM-DD.md`, **verbatim** — the archive reconstructs
the pre-split file byte for byte. The index at the bottom lists every entry
and which file it is in.

**Split at ~90% of 262,144 bytes, and read `wc -c` BEFORE writing an entry,**
**not after.** `tests/test_session_files_are_readable.py` guards the file; what
breaks first is the instruction to read it, because a session that cannot
read the whole file reads the head and silently believes it has the state.
Cut on a date boundary, name the archive for the split date, move the index
lines in the same edit (a split without them is a data loss with a table of
contents), and verify by md5. The seven splits so far and what each taught:
`tasks/archive/next-split-log.md`.

---

## SESSION START — if Joe said "read NEXT.md", this box is your prompt

Repo: `C:\Users\josep\Documents\Claude\Projects\kalshi_betting_tool`,
branch `main`. Check `git status` and `git log origin/main..main` rather than
trusting any sentence here, and read the LIVE instance's `/api/health` for its
`git_sha` — it sits under `build`, not at the top level. The calibration study
is STOPPED (2026-08-20, Amendment 2; the recorder machinery still runs). Joe is
a beginner and has asked to be educated: define every betting/stats term at
first use, via `frontend/src/lib/glossary.ts` and `<Term>`.

**The test count is CI's, not a hand-collected number.** `.github/workflows/ci.yml`
runs `ruff check .` and `python -m pytest -q` on every push, under a 15-minute
cap. Read the last green run: `gh run list --limit 5`. Run targeted tests
locally while you work; let CI collect the total. If you must take a count, do
not reconcile a baseline by reasoning about a delta — collect both trees. The
suite is ~15-22 minutes and growing with the record; a slow run is not a hung
one.

**READ THE DEPENDENCY ALERTS AT SESSION START — new 2026-09-09, ADR 0117.**
They were on none of the three queues, and two critical unauthenticated RCEs
sat on the public money box until a routine push happened to trigger a rescan:

    gh api repos/josephsapinoso/kalshi-cockpit/dependabot/alerts?state=open \
      --jq '.[] | [.number,.security_advisory.severity,.dependency.package.name] | @tsv'

**Do not read the alert summary git prints on push.** It is a snapshot taken
*before* the rescan that push triggers, so it describes the previous state.
Mine said "1 high" while the truth a second later was two criticals and a
high. And **do not trust an alert's own `state`**: alert #15 reports `fixed`
while `requirements.txt:9` still pins a version inside its vulnerable range,
because GitHub's dependency graph lost the package's resolved version.
**This query is therefore known-incomplete — it cannot see `cryptography` at
all.** Verify a fix by reading the version out of the running container, and
see open item 3 below.

**Two things to know before planning. CLAUDE.md is current on both:**

1. **The signal test has NOT declared.** The verdict is UNRESOLVED at
   `G = 216`, the floor is 713, the look is not coming, and every interval sits
   entirely below the 0.40 threshold — settled negative for planning.
2. **What the tool is FOR is settled — ADR 0071.** A personal betting desk
   first; price transparency as the job; a gap you may show on a row and
   never rank by; sharing means someone runs their own copy. Do not re-derive
   the purpose.

**Other lanes may be running; main is not the whole picture.** Read the
generated board, never a hand-typed lane table:

    git worktree list
    .venv\Scripts\python.exe scripts/lane_board.py

It reads every worktree and local branch — ahead/behind, uncommitted work, ADR
and schema claims, overlapping hunks. `tasks/LANES.md` carries the last written
snapshot plus the **allocation ledger**: what a live lane has said it will take
before it exists on disk. **Do not claim an ADR number or schema version by
reading either one** — write `docs/adr/DRAFT-<slug>.md` with no ordinal and
take the number in the merge commit after `git fetch`; the guard refuses a
`DRAFT-` file on `main`. Full rule: `docs/adr/README.md`. `docs/adr/0006-*`
sharing a number is deliberate, not a collision.

**The UI decisions live on GitHub, not here.** Map issue **#3 "Cockpit for the
pilot"** on `josephsapinoso/kalshi-cockpit` holds every screen decision Joe has
made, with evidence; a session that plans UI from this file alone will
re-derive them. Read the map body, then the frontier (open, unblocked `0`,
unassigned `-`, first in map order wins):

    gh issue view 3 --json body --jq .body
    gh api repos/josephsapinoso/kalshi-cockpit/issues/3/sub_issues --paginate \
      --jq '.[] | select(.state=="open") | [.number,(.assignee.login // "-"),(.issue_dependencies_summary.blocked_by // 0),.title] | @tsv'

Conventions: `docs/agents/issue-tracker.md`. Claim a ticket by assigning it to
yourself before any work; resolve one per session. The map produces
*decisions*, not builds. **The `/wayfinder` skill that drew the map is not
installed in this plugin version** — nothing can invoke it, and the map is
read with `gh` only.

**THIS FILE IS THE FRONT DOOR — Joe's answer, 2026-08-28.** Three queues: this
file's Open list (repo and infrastructure work), the map's open tickets
(decisions to make), and **decided-not-yet-built** — a closed ticket carrying a
spec is a NEXT.md item, and it belongs to nobody unless it is written here.
Read `git status`, then the Open list in the latest entry, then the frontier
query, in that order.

**THEN INVOKE THE `partner` AGENT, BEFORE PLANNING ANYTHING** — CLAUDE.md
workflow step 0. Hand it the state (what is open, what landed, what is blocked)
and ask for a ranked list AND which items can run as parallel lanes. Skip it
only for a single errand Joe named himself.

Read `CLAUDE.md`, then the latest entry below (it is the whole brief), then
`tasks/lessons.md` top two. Re-verify state, never inherit it:

    .venv\Scripts\python.exe -m pytest -q     (NEVER bare python; PATH is 3.14)
    cd frontend && npx tsc --noEmit

Expected: CI's count, ruff clean, tsc clean, `next build` green. Check
`/api/health` `git_sha` against `origin/main` before assuming anything is
live. The terminal spread/total look was **VETOED by Joe 2026-08-21 16:11Z**
(`docs/measurements/2026-08-21-spread-total-edge-second-look-result.md`) —
nothing fires at 22:40Z. **The H4 look series is CLOSED — BLOCKED ON
INSTRUMENT, 2026-08-21** — do not build the A9–A12 analyzer and do not re-run
the channel diagnostic (A17.6/A17.11).

## 2026-09-10 (sixth session) — the ladder floor was OOM-cycling the recorder; the fix shipped, and /hedge now says what it cannot see

**Found by measuring the thing the last entry said was slow, from the outside,
before touching it.** Item 0 said the 9-day floor scanned 6.5M rows and
`/api/parlays` paid it twice. It was worse: the scan's `ROW_NUMBER()` runs
under `temp_store = MEMORY`, so 6.5M rows became ~1 GB of resident memory in
BOTH processes, and the 2 GB box had restarted three times in five hours
before this session began. The partner's ranking and the sharp-bettor's craft
review both redirected the hedge-alert ask to coverage first, and the coverage
read was 0 of 1.

**STATE at close.** `main` = **`324a53f`** plus this entry, pushed; **CI green
on `324a53f` (run 34437142296)**; full suite on main before the docs commit:
**6845 passed, 10 xfailed, 0 failed** after one timezone fix. **Live =
`324a53f`, schema v37, machine `7812601a239428` unchanged** (deploy run
34437560202; migration `v36 -> v37` at boot in 172 s). Demo untouched. Odds
path untouched: the freeze to 10:00Z 2026-09-14 holds, and `credits-day` shows
no attention row during either probe — a server-side fetch of an SSR page does
not register attention, only the client's `/desk-attention` POST does.

Four ADRs: **0134** (the ladder scan keys on the confirmed stamp; v37 partial
index), **0135** (an abandoned request stops executing; `API_READ_BUDGET_MS`),
**0136** (the hedge screen says what it cannot see), **0137** (the phone says
which legs are live, on a schedule — amends ADR 0078 D2 on Joe's word). Six
lanes ran in parallel worktrees, all merged; worktrees and branches removed.

### THE HEADLINE: the box was dying every hour, and opening `/parlays` could kill it on demand

`docs/measurements/2026-09-10-the-ladder-floor-oom-cycles-the-recorder.md`.

Timed from outside with a minted read-only cookie (the MCP Chrome tab group
carried no session cookie, so no browser-side paint timing exists — say so if
you cite this): `/api/window`, `/api/signal`, `/api/parlays`, `/api/slate` all
**500 at exactly 30 s** (Next's rewrite-proxy timeout; uvicorn keeps executing
after Next hangs up, so abandoned queries pile up), `/parlays` unanswered at
180 s. Three minutes later the kernel killed the runner at **1.13 GB** and then
uvicorn at **1.88 GB**, and the machine rebooted. The runner's own log
(`loop-rss`) had carried the attribution since the v36 deploy at 22:52Z:
RSS **196 MB -> 1.10-1.23 GB** per pass, `candidate_ms` **83 -> 3,549-9,454**,
over the same ~440 rows; boot lines at 00:32Z, 01:04Z, 03:18Z; a
`PassDeadlineExceeded` at 23:33Z. Nobody had read that column.

**The fix, and why not the obvious one.** Narrowing the floor back was ruled
out by item 0 itself. The predicate now reads
`(f.computed_ms >= ? OR f.confirmed_ms >= ?)` — exact, because a confirmed
stamp is never older than its frozen one — served by a **partial** index
`idx_fair_market_confirmed ON fair_prices(market, confirmed_ms DESC) WHERE
confirmed_ms IS NOT NULL`, which holds **614 rows** on live. The plan is a
`MULTI-INDEX OR` with two seeks; with the index dropped the `computed_ms>?`
term vanishes and the existing plan test goes red. The 9-day constant is gone;
the floor is `max(8 x max_odds_age_ms, 2h)` again. Rehearsed in the container
on a paced copy: the index build reads the whole 10.1M-row table once,
**181.8 s cold**, so the boot health grace went **120 s -> 600 s** with the
measurement beside it in `fly.live.toml` (the container's image cannot
pre-build an index its code does not know). Live built it in 172 s.

**After, on the warm box:** `/api/parlays` **1.1 s**, `/api/slate` 0.6 s,
`/api/board` 0.27 s, `/api/hedge` 0.13 s, every SSR page under 2.2 s; the
runner at **189 MB, 72-75 ms** over 434 rows; zero OOM lines since. The
25-minute reading had `/api/window` at 20 s — that was the cold page cache
after the reboot and the 5 GB rehearsal copy, not a second defect: replayed on
live it is **0.95 s**, 0.91 of it one `GROUP BY` over `odds_snapshots`.

Two independent brakes shipped beside the query fix, on the partner's ruling
that their failure modes differ from the query's: the runner **builds the
ladder only when a card could be sent** (`Alerter.parlay_cards_could_send`,
so the change-alert debounce still advances on real builds), and every
per-request API connection carries a **25 s progress-handler budget** that
answers 503 `read_budget_exceeded` instead of piling up behind a proxy that
already gave up (`API_READ_BUDGET_MS`, under Next's 30 s).

### The hedge screen covered 0 of 1 live positions, and now says so

Read off live at 03:25Z: the venue held ONE open combination (17.74 contracts,
$9.69) bought in the Kalshi app, absent from `parlay_positions`; the one
recorded position (id 1, the $1.64 BOS/NYY/LAD combo) had **settled `no` at
01:40Z** in `venue_settlements` while still reading `open` with three
`pending` legs, because `resolve_from_venue` reads only `kalshi_markets.result`
and the venue had not finalized the leg markets (and the result pass runs
inside the full pass that kept dying). ADR 0136: `/api/hedge` now carries
`unrecorded_at_venue` (KXMVE tickers in the latest **ok** positions poll with
no open row — the membership-of-latest-complete-observation rule), per-position
`at_venue` and `venue_settlement`, and the screen renders the quote age beside
every leg price (it was in the payload and never drawn). No auto-close: which
leg lost is not knowable from the combo's settlement. Verified on live after
the deploy: position 1 renders `dead`, `at_venue: false`, settlement `no`, BOS
`lost`, NYY `won`, LAD `pending`; the venue list is `[]` because the $9.69
combo settled between 03:25Z and 04:41Z (`row_count 0`).

### The push Joe chose — ADR 0137, amending ADR 0078 D2

Asked which push he wanted, Joe chose the **symmetric "legs in play"
statement**: once per ticket per budget day when a watched game is in play,
every pending leg's venue bid with its quote age, "N of M legs live", the
sentence "No figure locks" when N > 1, the lock figure only when N = 1 and one
exists, `not_advice` and `upper_bound` verbatim, record order, the parlay
colour. **Identical template on a good day and a bad day** — the sharp-bettor's
argument that carried it: an alert that fires only on bad news is a nudge by
construction; one that fires on a schedule carries no information in its
arrival. Kind `position_state`, key `position_state:{id}:{day_start_ms}`, own
ceiling of 4/day, own counter. A forbidden-words test pins the transport. The
watcher spends nothing metered (existing test still green). **Not yet observed
firing on live** — no position was in play after the deploy.

The sharp-bettor's other findings, recorded for the next UI ticket, not built:
the de-risk headline (a joint built on the unmeasured 0.05/0.02 correlation
nudges) is the least defensible number on the page and should go; the
five-column ladder does not fit a phone at the moment of decision (contracts,
cost, worst case; the two branches behind a tap); no total exposure line; the
combo's own live quote and the absence of a resting YES bid are never shown.

### Verified by disabling

    Lane A runner gate       3 mutations   3 red (7 tests)
    Lane B v37 predicate     3 mutations   3 red   + one vacuous test rewritten before it could pass for nothing
    Lane C read budget       2 mutations   2 red
    Lane D coalesce          1 mutation    1 red
    Lane E1 coverage facts   5 mutations   5 red   + one isolation test added when a mutation showed two clauses untested apart
    Lane E2 the push         4 mutations   4 red

### Still open, in order

1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Untouched. One
   candidate for after the freeze, measured not decided: `window_status`'s
   `GROUP BY odds_event_id` over `odds_snapshots` costs ~0.9 s and is polled
   every 10 s by `RefreshWhenPriced` while a tab is open; a covering index
   would be the shape, and it needs its own re-timing.
2. **SUNDAY 2026-09-13 — a scheduled run, not a task to plan.** Unchanged.
3. **The boot health grace is 600 s.** Raised for v37 on a measurement; the
   file's own rule says raise rather than trim a migration to fit. Lower it
   only with a reason, not by reflex.
4. **`position_state` has not fired on live.** The first in-play watched
   position will tell; check `notifications WHERE kind = 'position_state'`
   after it, and that `hedge_lock` still fires separately.
5. **The combo fee-model reopen trigger** (n = 68) — unchanged, Joe-gated
   whether it gets a session; the partner asks that any session name the
   constant it could move before it starts.
6. **`fly.live.toml` growth-rate copy (old item 6) — ALREADY CORRECTED** in
   an earlier edit (`:668-670` records the 326.6 MB/day realisation). Closed.
7. **`pip-audit` pyarrow ignore** — trigger only, unchanged.
8. **The binned card** — do not rebuild, unchanged.

**Joe-gated: NOTHING.** The one question this session (which push) was
answered in-session.

### Lessons written

One, pattern-level: the cost of a scan is not its wall-clock — under
`temp_store = MEMORY` a window function turns rows read into resident memory,
so a floor widened for a correct reason is re-timed on live reading RSS beside
milliseconds before it ships; and an abandoned request is not a finished one.

**And one about my own procedure.** I measured the live site with a probe that
was, functionally, a user opening four tabs, and the box died three minutes
later. The probe was right to run and the death was going to happen at Joe's
next tap either way — but a measurement that can take the box down is one to
announce before running, and to run one route at a time.

## 2026-09-09 (fifth session) — the biggest table in the database is 99.7% duplicate rows, and the obvious fix would have emptied the ladder

**Found by running the partner's falsifying query instead of arguing.** The
partner ranked the whole backlog, then revised its own ranking mid-flight after
one trace, and named a single query that would kill its new thesis if it was
wrong. The query confirmed it instead. Nothing on the Open list produced this.

**STATE at close.** `main` = **`62191f4`**, four lanes merged, **full suite
green on main: 6779 passed, 10 xfailed, 0 skipped, exit 0** (13m18s). Live is
still on **`2126dde`** — *nothing from this session is deployed*, and the
schema change means that matters (see the deploy note below). Machine
`7812601a239428` unchanged. Demo untouched.

Two ADRs: **0132** (the settlement taker flag gets a writer), **0133** (a
consensus that has not moved is confirmed, not reinserted). **Amendment 2** to
the fair-prices downsample registration. Schema **v35 → v36**, migrated but
**not yet deployed**.

### THE HEADLINE: `fair_prices` re-inserts an unchanged consensus every ~15-20s

`write_fair_price` ended in an unconditional `INSERT` per outcome, and
`run_pricing_pass` is reached from **both** the 900s full pass and the **15s
quote** pass. So while a window is open the consensus is re-derived and
re-inserted every ~15-20s, against an odds feed on a ten-minute floor.

Measured read-only on live, key = the five-column row identity, payload = the
value columns, `computed_ms` and `oldest_book_age_ms` excluded:

    window A   3.98h   414 passes   199,506 transitions   99.73% unchanged
    window B   5.15h   420 passes   199,504 transitions   99.61% unchanged
    window C   2.01h   392 passes   199,488 transitions   99.75% unchanged

`h2h` and `spreads` agree to 2dp in every window; largest single key is
1.3-2.6% of all changes; **344 of 494 keys changed zero times in window A**.
`fair_prices` + its 2 indexes is 2.41 GB — **47.5% of the database**.

**Do not quote "72.3 passes/hour" — it describes none of the three windows.**
Per-window they run 104.0, 81.6 and 195.0/h; 72.3 was a day average including
idle hours at the 900s cadence. The 2.4x spread inside one day is the
informative part.

**Three windows are not `n = 3`.** The cluster is the **day**, so `G = 1`, and
494 keys are not 494 clusters — the registration fixes `link_id` as the cluster
and that view was never taken. **No inferential claim is available**, and this
says nothing about an NFL Sunday, when the window profile is what changes most.

### The fix that would have emptied the ladder, and the measurement that caught it

`odds_age_now_ms = (now - computed_ms) + oldest_book_age_ms`. Those telescope,
so freezing both preserves the sum exactly — the arithmetic is correct and it
made freezing look free. **It is free only while the books stand still.**

    book_updated_ms advanced on 19,643 of 19,689 consecutive observations
    whose PRICE DID NOT MOVE -- 99.8%, median +646s
    (price MOVED, book_updated SAME: exactly 0)
    odds refetch cadence: 28 distinct fetch instants in 6h, p50 gap 615s

The books get fresher every ten minutes without moving. A frozen
`oldest_book_age_ms` never learns that, reported staleness grows without bound,
and anything held past ~15 min is refused — ADR 0055's failure mode by another
route. So the row now carries **two pairs**, each internally consistent because
both members are stamped at one instant: `computed_ms`/`oldest_book_age_ms`
freeze at first appearance (what a `fair_price_id` join points at), and the new
nullable `confirmed_ms`/`confirmed_oldest_book_age_ms` move on every confirming
pass. `_live_age_ms` coalesces each column independently.

**The row identity is FIVE columns, not four.** On a prop `outcome_name` is
only "Over"/"Under" and the player lives in `outcome_description`; a
four-column key collides two players. The scan floor gained a third term
(9 days) because a confirmed row's `computed_ms` no longer bounds its freshness.

### Also landed

- **The disk alarm's prose promised twice the time the disk had.** The alarm
  **is** wired and live (`run_loop.py` is PID 710 in the container;
  `run_loop.py:1257 → volume.read_volume("/data") → check_volume`). But
  `REFERENCE_GROWTH_BYTES_PER_DAY` was 161.40 MB/day against a realised
  326.6 — NOTICE would have said ~9.9 days when the truth was ~4.9. Now one
  `CURRENT_GROWTH_RATE` carrying its own date and `n`; every duration derives
  from it, and a test fails if one is ever hand-typed back.
- **`venue_settlements.is_taker` had a schema, a reader, and no writer** — NULL
  on 90 of 90 rows. Now written from the fills join. Mixed-fill positions stay
  NULL, no-fill positions stay NULL, written flags are never overwritten.
- **Amendment 2: the constant stays pinned, DO NOT RAISE.** Raising
  `FAIR_PRICE_FAMILY_BYTES` re-scales a verdict computed from rows already
  inspected. The reopening bar is left behind falsifiable: the eligible
  fraction would have to reach **13.394%**; measured **4.005%**.
- **The arming ADR was never owed.** §6 authorises one only on `ELIGIBLE TO
  PROPOSE ARMING`; the deciding run returned `NOT WORTH ARMING`. Risk and
  dominance are corroboration, explicitly not load-bearing. The module stays in
  the tree — it carries the SQL §S1 is pinned to.

### Killed, refuted, or answered — do not re-open these

- **`clv_signal` vs `prune_quotes` is REFUTED.** They do know about each other:
  `retention.py:228` carries `AND ticker NOT IN (SELECT ticker FROM
  recommendations)`, and the module docstring names `clv_signal.py` as the one
  reader reaching past an hour. Live: **58,612 rows, oldest 32.9 days,
  `quote_mismatch` 0, `no_quote` 0, matched 100%.** A pruned quote would surface
  as `no_quote`, not `quote_mismatch` — different statistic.
- **Item 4's premise was wrong.** The fee alarm reads `ParsedFill.is_taker`, a
  bool the venue supplies and `parse_fill` refuses the fill without. Both
  2026-09-08 KXMVE fills are in `fills` with `is_taker = 1` and fees predicted
  exactly. Zero settlements lack a fill.
- **The dependency queue is clear.** Zero open Dependabot alerts;
  `cryptography 50.0.1` and `pyarrow 19.0.1` read out of the running container.
- **The decisions queue is empty.** All 32 sub-issues of map #3 are closed;
  only the map itself is open. There is no frontier ticket.
- **The `fair_prices` dry run exited with its output lost** — stdout was a pipe
  whose reader was gone. Not worth re-running: Amendment 2 makes that figure
  non-decision-bearing.

### Still open, in order

0. **THE LADDER SCAN FLOOR IS A LIVE PERFORMANCE REGRESSION I SHIPPED TODAY.**
   Measured on live after the v36 deploy, by binary search on the primary key
   (cheap and exact — do not full-scan this table):

       rows inside the NEW 9-day floor      6,561,382
       rows inside the OLD 2-hour floor           138   (post-dedupe)
       max_id                              10,109,064

   Lane G widened `ladder_candidates`' scan floor to
   `max(8 x max_odds_age_ms, _CANDIDATE_SCAN_DEDUPE_FLOOR_MS)` where the new
   term is **9 days** (`backend/parlays.py:406`), for a CORRECT reason: after
   the dedupe a confirmed row's `computed_ms` no longer bounds its freshness,
   so a long-held-but-fresh consensus would fall below a 2-hour floor and
   vanish from the ladder. **The reason is right and the fix overshot** — it
   pulled the entire pre-dedupe backlog into every scan.

   For scale: the flat-24h floor this repo already removed on 2026-08-30 was
   scanning **541,222 rows in 25,324.7 ms**. The window is now **12x that**.
   Pre-deploy the 2-hour floor held roughly 72,000 rows, so this is ~90x worse
   than yesterday. `/api/parlays` pays it TWICE per lookup tap.

   **It self-heals, slowly and only partly.** Pre-dedupe rows age past 9 days
   around **2026-09-18**, after which the window holds roughly 29,000 rows
   (9 days x ~3,200 real changes/day) — better than the old 72,000, so the
   long-run design is sound. The transition is the problem, and it is the
   window Joe is using the desk in.

   **Do not fix it by narrowing the floor back** — that reinstates the bug Lane
   G fixed and empties the ladder. The floor must key on the CONFIRMED stamp,
   not `computed_ms`: an index on `(market, confirmed_ms DESC)` with a matching
   predicate, or a single effective-timestamp column, or drop the time floor
   and take the latest row per key through `idx_fair_link`. Whichever, it must
   keep the index seek `tests/test_ladder_query_is_indexed.py` asserts by
   regex, and the query must stay a literal string.

1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Untouched this
   session and the partner ruled Lane G outside the freeze on three conditions,
   all met: no file under `backend/odds/`, not `backend/scheduler.py`, and a
   test proving pass cadence and count are unchanged. The freeze protects the
   **credit-convergence readout**; "dwell measurement" has no referent.
2. **SUNDAY 2026-09-13 — a scheduled run, not a task to plan.** Runner:
   `scripts/run_combo_exit_capture.py --slot cN`, exit **3** on refusal. Now
   confirmed from the registration: a slot may be retried **once within 10
   minutes**; missed by more than 30 minutes it is recorded **missing, not
   moved**, and the result reports four of five. *"The pool was thin, so we
   took another look later"* is prohibited by name. **Nothing schedules these —
   every slot is run by hand.** Arm C still has no per-slot command.
3. **DEPLOY IS OWED, AND IT CARRIES A SCHEMA MIGRATION.** Live is three
   sessions behind at `2126dde` and `main` is at v36 while live is v35. The
   dedupe cannot help the disk until it ships, and the v36 migration must be
   rehearsed in the container the way v35 was. **Nothing in this session has
   been observed running on live.**
4. **`manual_orders.py` reads `fair_prices.computed_ms` and I said it didn't.**
   NEW, and it is my error: I told the lane only `_live_age_ms` and the ladder
   query read that column. `backend/store/manual_orders.py` also reads it via
   `recommendations.fair_price_id`, to freeze a descriptive
   `submitted_ms - consensus_computed_ms` staleness figure on every hand-bet
   order. **Never a gate, never judged** — so not a money-path defect — but
   after v36 it will more often show *first appearance* than *last
   reconfirmation* and understate recency. Lane G found it and correctly left
   it alone.
5. **The combo fee-model reopen trigger HAS FIRED.** `n = 68` KXMVE fills
   across 17 distinct UTC days, no day more than 12% — so unlike `beta`, this
   one is not concentration-blocked. 67 of 68 are takers. Also unjudged: **36
   of 68 KXMVE fills are undercharges against zero of 34 non-KXMVE**, though 35
   of the 36 are sub-$0.0001 float dust and the last is the maker row the model
   refuses by design. Wants `measurement-skeptic` and `kalshi-platform`, not a
   lane.
6. **A second stale copy of the growth rate.** `fly.live.toml:654,660-661`
   reasons from the superseded 161.40 MB/day and concludes "mid-November". No
   Python constant can reach it. Flagged, not touched.
7. **One `pip-audit` ignore remains and it is NOT a deferred fix.** `pyarrow`
   `GHSA-rgxp-2hwp-jwgg` needs an Arrow **IPC file** read with pre-buffering
   and this repo only writes Parquet. **Trigger: anything starts reading
   `.arrow` or `.feather`.**
8. **The "last scored call" card is BINNED — Joe's word, 2026-09-09.** Not
   deferred. `worktree-agent-ab85969ab45aa6004` and its worktree are deleted.
   **The commit is `ab559e6` and stays recoverable from the object store until
   GC** (~90 days), which is the only reason binning it is cheap — it held a
   `DRAFT-the-last-scored-call-gets-a-caller.md`, `/estimate` page wiring, an
   `api.ts` client and `tests/test_last_scored_call_is_rendered.py`, 350
   insertions across 7 files.

   **Do not rebuild it.** The reason it could never work is a fact about the
   data, not a missing piece: `bet_estimates` holds exactly **one** row and it
   is `is_study_row = 1`, which `last_scored_call` must exclude — so the card
   renders empty forever. Verified again this session: `bet_estimates = 1` on
   live. The premise it was assigned on was already stale when it was written,
   ADR 0094 §11 having killed the log screen on Joe's word 2026-09-05.
   Reopening needs study rows that are not study rows, i.e. real scored calls.

   Two sibling worktree *directories* also resisted deletion (a process holds
   the handles); their branches are gone and git's registry is clean, so they
   are inert clutter.

**Joe-gated:** the parked branch (item 8), and whether item 5 gets a session.

### Lessons written

Three, all pattern-level: the column you exclude from a comparison key is where
the duplicates' real payload hides; mutating a constant tests nothing unless
every consumer actually derives from it; and a lane's green suite is a weaker
claim than main's, because this repo skips its integration guards off the
integration branch on purpose.

**And one about my own procedure.** I asserted "the only readers of
`computed_ms` are these two" from a grep, and a lane found a third. A grep over
one spelling of a column name is not a reader census — the third reader reached
it through a join on `fair_price_id`, which the grep could not see.

## 2026-09-09 (fourth session) — a live bet was invisible to the only screen that could exit it, and the wiring that fixed that killed the question a registration was asking

**Found by checking the one thing the last session shipped and never observed
working.** Not by planning, not from a queue. The reconciler that found it did
not exist at session start, and the second thing it found was a defect in
itself.

**STATE at close.** `main` = **`2126dde`**, pushed, **CI green**. Live is on
**`2126dde`** too — `main` and live are the same commit, machine
`7812601a239428` **unchanged across the deploy**, so no volume was replaced and
nothing was recreated from empty. Demo untouched.

Four ADRs: **0128** (Sunday's slot runner), **0129** (a combination records the
consensus), **0130** (what the manual hedge form is for), **0131** (the ticket
stops asking for a probability). **Amendments 1 and 2** to the parlay-positions
registration. Five lanes ran in parallel worktrees.

### THE HEADLINE: a real position, bought with real money, that `/hedge` had never heard of

`manual_orders` **id=4**: filled **2026-09-09 15:11:56Z**, `dry_run = 0`, 4
contracts at 41c — **$1.64 staked against a $4.00 return**, three MLB legs
(BOS 18:45Z, NYY 19:05Z, LAD 22:10Z). `parlay_positions` held **zero rows**.

A `KXMVE` combination is enter-only and `/hedge` is its only exit, so for hours
a live position existed that the exit screen could not see.

**ADR 0125 was not at fault and this is the load-bearing fact.** The wiring
that makes a filled combination write its own position row deployed at
**15:56:45Z** — 45 minutes *after* the fill. An orphan created in the gap.

Fixed: `parlay_positions` **id=1**, `created_ms` 1788976165253, written by
`scripts/backfill_orphan_combo_position.py` — **committed before it ran**, per
the amendment, so the exact arguments are in git rather than in a transcript.
`/hedge` was then confirmed rendering it end to end: three legs priced live at
66% / 69% / 72%, state `derisk`, correctly saying a hedge on one leg locks
nothing while three are live.

### The reconciler, and the defect it had on its first live run

`scripts/inspect_live_db.py combo-position-gaps` — **the only detector for a
write that is designed to fail silently.** `_record_combo_position` runs inside
a bare `except` so bookkeeping can never fail a purchase that already spent
money; that is correct and it stays, and its consequence is that the write can
fail with nothing raised, nothing logged to a screen, and no test covering the
live path.

**Its first live run reported three positions `OPEN AT VENUE -- UNWATCHED`.
Two had settled the day before.** It asked for the newest `venue_positions` row
*bearing each ticker* — but that table is an append-only poll record: a held
position is rewritten every cycle and a settled one simply stops being written.
**The absence is the event**, and the last present row reports whatever was true
when the position last existed. Silence read as exposure, inside the one column
written to catch silence read as health. Nine tests were green over it because
every fixture described a position that was still open.

Now asks membership of the most recent **successful** `positions` poll.
`ok = 1` is load-bearing and separately tested: taking a failed call as the
baseline makes every open position absent from it and reports the lot as
closed — an outage rendered as an all-clear.

### The registration the fix killed — Amendments 1 and 2

**The window is VOID; the registration survives.** §5's subject is Joe and its
verb is *records*. Since ADR 0125 deployed, a successful desk fill increments
`R` **mechanically**, and §8 makes `R >= 1` decisive on its own — so the check
now returns NOT REFUTED the moment the wiring works, carrying no information
about the form it was written to judge. **A question that cannot come back
negative is not a question.** Clean stretch: 18h 24m, `G` between 0 and 1.

P3 was **independently fatal** — its denominator script still does not exist
while the window has been open since 2026-09-08T21:33:05Z, and the "before"
clause exists precisely so the denominator cannot be tuned once the outcome is
visible. **The window could not have carried a verdict even had ADR 0125 never
shipped.**

**Joe killed the adoption successor** (Amendment 2). All three §8 branches are
marked VOID and unreachable with reasons; **2026-11-30 is not a date on which
anything happens and no calendar may carry it.** The deletion question is
**CLOSED, not deferred** — reopening needs a decision from Joe with a stated
reason, not a measurement. The arithmetic that justified the kill: `G = 30` by
the backstop needed 0.39 unwired sittings/day for 76 days against a measured
0.7–1.2/day from all sources, i.e. it was powered **only if a third to half of
his combination bets stayed outside the cockpit** — the branch where ADR 0113's
intent fails.

**Joe also dropped the provenance column**, and the registrar conceded its own
prior ruling rather than defending it: provenance never enters the hedge
arithmetic; a label does not fix a wrong stake, only annotates one; and A1.3.3
had **over-read the `resolved_source` precedent** — that column separates
evidence about an outcome the reader cannot re-derive, while a stake is a number
its writer knows he typed. What is given up, permanently: a hand-written and a
wiring-written row are now indistinguishable. **A2.7.4 binds harder than P3's
"before" clause** — a denominator can be rebuilt from `fills`, but **authorship
leaves no raw material**, so a column added later recovers attribution for
nothing written before it.

### The P(YES) field is gone — ADR 0131, superseding ADR 0065 §2

Joe: *"what is even the point of the (p)yes score entry? I don't need it. it
just gets in the way."*

**ADR 0065 already contained the argument.** Its §1 records that the red-team
position — *an unscored form is a speed bump a user learns to type through* —
lost on **one factual premise**: that `bet_clv()` had just given the number a
consumer on `/bets`. `backend/bets.py` never read `p_yes_bp`. Nothing did.

The masking went with it. Anchoring protection only buys something if the number
is later scored; protecting the integrity of a number nobody reads is cost with
no product.

**Schema v34 → v35, deployed and verified in the container** against a baseline
read taken before the deploy: `schema_version` 34 → **35**, `p_yes_bp NOT NULL`
→ **nullable**, and the four real values **`67, 2600, 33, 3390` identical**.
The column and the rows survive — deleting history to remove a form is a bigger
change than the one he asked for — and **NULL means "not asked", never 0**; a
zero would read as "he thought this had no chance", which on a money row is a
lie.

**Rehearsed in the container before the deploy, on those same four rows**:
forward, replayed, and reversed, with the old shape first proved to refuse NULL
so the migration had real work to do. A full DB copy was impossible (see the new
open item on volume space), so the rehearsal built the v34 shape from the
migration's own undo helper.

### Verified by disabling — 30 mutations across five lanes, and two were not decoration

    Lane A reconciler   4 mutations, 4 red   (+2 more on the exposure fix)
    Lane B slot runner  1 mutation,  3 red
    Lane C consensus    9 mutations, 9 red
    Lane E P(YES)      15 mutations, 15 red — one GREEN first
    the disclaimer      1 mutation,  1 red

**Lane E's green mutation is the finding.** The replay test for `INSERT OR
IGNORE` wound the version stamp back after a **completed** migration; by then
the temp table is gone, so a plain `INSERT` has nothing to collide with. The
state `OR IGNORE` exists for is a crash **between** the copy and the drop, and
no test reached it. A create-copy-drop-rename rebuild has several crash points
needing different guards, so *"run it twice"* tests the cheapest one.

### Also answered, closed, or corrected

- **NEXT.md item 6 is ANSWERED: a combination's settlement DOES reconcile.**
  `venue_settlements` carries **62 `KXMVE` rows of 90**, including both
  2026-09-08 combos with contracts, entry price and fee. Both **won**
  (`market_result = 'yes'`, entered at 37.5c and 23.8c). **n = 2 — that is
  plumbing confirmed and two bets landing, and it is not evidence of edge.**
- **Item 4 is DONE (ADR 0129).** A combination now records the consensus the
  desk computed and showed him, sourced from `priced_lookup_for`. Two judgement
  calls worth keeping: a **NO-side** combination is refused rather than
  complemented (worst-of-four is conservative in the direction taken, so
  `1 − joint` is anti-conservative and would invert rule 2 on a money row), and
  `hold` is **not** copied — it is a ratio against the ask at *lookup* while the
  row already carries the ask *paid*. `'combo_ticker'` is now a **closed
  historical set** with an AST test proving nothing writes it.
- **`.claude/agents/partner.md` was carrying a false fact** — it told every
  session that `scout.py` and the Historian were called by nothing. Scout is
  wired to `POST /api/scout/{ticker}`; the Historian was deleted by ADR 0106.
  The partner found this in its own brief and said so.
- **A dead duplicate route deleted**: `GET /api/estimates/markets` over the same
  `search_markets` that `/api/manual/search` serves and the picker calls.
- **Lane D′'s "last scored call" card is PARKED on a branch, deliberately not
  merged.** `bet_estimates` holds exactly **one** row and it is
  `is_study_row = 1`, which `last_scored_call` must exclude — so the card would
  render empty forever. The premise it was assigned on was stale: ADR 0094 §11
  killed the log screen on Joe's word 2026-09-05.

### Still open, in order

1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Untouched this
   session. Frozen: `backend/odds/{timing,budget,attention,ondemand,client,sweeplog}.py`
   plus the `window_status` bootstrap question. A deploy is not contamination;
   logic changes are. **Note the freeze protects the credit-convergence
   readout** (`docs/measurements/2026-09-08-nfl-sunday-credit-convergence.md`),
   not a "dwell measurement" — the registrar found that phrase has no referent
   in any registration.
2. **SUNDAY 2026-09-13 — a scheduled run, and it now has a runner.**
   `scripts/run_combo_exit_capture.py --slot c3` emits both registered
   invocations, Arm A then Arm D, and **refuses with a non-zero exit naming the
   blocking file** if any target output exists. Five slots
   (C1 15:30Z, C2 17:30Z, C3 20:00Z, C4 23:30Z, C5 00:45Z 09-14), no sixth
   capture, no slot moved beyond 30 minutes. **Arm C has no per-slot command in
   the registration at all** — Lane B checked and did not invent one; both NFL
   series returned 0 open rows midweek and a named `--series` with no rows
   aborts by design. **Nobody opens the cockpit UI to run any of it.** A null is
   not confirmation; the word "structurally" is forbidden.
3. **The volume grows at 2x its documented rate, and the extension bought
   about 46 days rather than a solution.** NEW, and this is the item most likely
   to be misread as closed because a number moved in the right direction.

   **Extended 10 -> 20 GB on 2026-09-09 on Joe's decision**, live, no restart:
   `/data` went 51% -> **27% used, 14 GiB free**. Taken because a `VACUUM` did
   not fit in the 4.7 GB then free, which is also why the v35 migration had to
   be rehearsed from the migration's own undo helper instead of a database copy.
   A `VACUUM` and a large-table rebuild are both possible now; neither was.

   **Deleting rows would not have helped and that is the part to remember.**
   `auto_vacuum = 0` on the live database, so freed pages go to a freelist and
   are reused — the file does not shrink. `PRAGMA incremental_vacuum` is
   unavailable (it needs `auto_vacuum` set at creation, and switching it on
   requires the full VACUUM that did not fit). The freelist held 31 MB, so
   there was no slack to recover either. **Deletion stops growth; only a VACUUM
   reclaims disk.**

   **Where the 5.07 GB is**, read 2026-09-09 ~19:49Z via `db-sizes`:

       fair_prices + its 2 indexes    2.41 GB   47.5%
       odds_snapshots + its 3         1.29 GB   25%
       kalshi_quotes + its 1          1.22 GB   24%
       everything else                0.15 GB    3%

   **The rate, and it is the finding.** `docs/measurements/2026-09-01-the-volume-clock.md`
   projected **160.23 MB/day** on the file. Realised across the 8.138 days
   between its read (2026-09-01 ~16:30Z, file 2,413,142,016) and 2026-09-09
   (5,070,802,944): **326.6 MB/day, 2.0x**. The family's *share* of growth held
   — 56.8% against a projected 64.4% — and the *rate* did not, because a
   composition measured over a 44.4-hour window was carried forward as a rate.
   **At the realised figure 14 GiB is ~46 days, i.e. mid-to-late October.**

   **Do not re-measure a rate from one window.** The pattern is in
   `tasks/lessons.md`'s neighbourhood already; this is its instance on disk.

   Still true and unchanged: **no instrument reports volume usage.**
   `backend/store/volume.py` and `tests/test_volume_alarm.py` exist and were
   NOT checked this session — whether an alarm is wired, and at what threshold,
   is an open question and the cheapest thing on this list to answer.

   **Two things owed, neither done:** an amendment to
   `docs/measurements/2026-09-01-preregistration-fair-prices-downsample.md`
   raising `FAIR_PRICE_FAMILY_BYTES` (deliberately NOT edited in code — it is
   pinned so the same eligible fraction cannot yield a different byte verdict
   on a different day; see the DO NOT UPDATE block at
   `fair_price_downsample.py:202`), and a decision on arming the downsampler at
   all. Arming needs its own ADR by its own config's terms, and its estimator
   is now a **floor**, understating by ~2.68x. The `fair_prices` dry run was
   started on live 2026-09-09 and had not finished after 20+ minutes; it is
   read-only, deletes nothing, and its figure is informational now that the
   disk pressure is gone.
4. **`is_taker = None` on the settled `KXMVE` rows.** NEW. The fee-alarm trigger
   the partner set last session (reopen the combo fee model when the alarm fires
   on a combo fill, or at `n >= 30`) may be **unable to fire** if takerness is
   unknown on exactly the rows it would judge. Not chased.
5. **One `pip-audit` ignore remains and it is NOT a deferred fix.** `pyarrow`
   `GHSA-rgxp-2hwp-jwgg`: the flaw needs an Arrow **IPC file** read with
   pre-buffering and this repo only writes Parquet. **Trigger: anything starts
   reading `.arrow` or `.feather`.** Also recorded, not blocking: pytest 8.4.2 /
   `PYSEC-2026-1845`, dev-only, deliberately outside the gate.
6. **A stale justification in `scripts/backfill_orphan_combo_position.py`** was
   fixed this session (it cited the provenance column as pending). Nothing
   pinned it, so nothing would have gone red. Recorded because it is the
   `justifications-decay-toward-reassurance` pattern arriving in a file written
   the same day as the lesson.

**Joe-gated: NOTHING.** Everything asked this session was answered within the
session: the orphan write, killing the adoption successor, dropping the
provenance column, and removing the P(YES) field.

### Lessons written

Four, all pattern-level: an append-only record reports the last state it saw
forever after that state ends; a decision that turned on a **named consumer**
must be re-opened when the consumer is never built, and nothing notices; a
replay test can pass through the crash point its guard is for; and a guard that
pins an ADR's **slug** breaks at the exact moment the ADR becomes citable — pin
the ordinal.

**And one about my own procedure.** Four lanes each ran their own files green
and I ran targeted suites on top; CI then failed twice on things **no lane could
see from inside its own worktree** — a written-down subcommand surface, and the
ADR numbering rule. Running the full suite before pushing a multi-lane merge is
not optional. A watcher polling `--limit 1` also reported the *Deploy* run's
result as CI's; filter by name.

## 2026-09-09 (third session) — the desk armed the entry and never armed the exit; and the census behind every combo warning had never read the shard he trades

**Two findings, both about the combination path, both found by looking rather
than by being told.** The exit gap (ADR 0125) came from the partner ranking it
above the whole backlog. The shard gap came from probing `/markets` to confirm
a ticker spelling — which is the second time this session that a routine
verification, not a plan, produced the thing worth knowing.

**STATE at close.** `main` = **`d27ca55`**, pushed, **CI green**
(`34377084002`, 9m4s). Session started at `579fadd`, clean.

**THE SCOPE CORRECTION IS LIVE, four days ahead of its deadline.** Deployed on
Joe's word, run `34381163045`. **`main` and live are the same commit**
(`6f30079`), machine `7812601a239428` **unchanged** — no volume replaced, no
credit fact inverted.

**Verified in the running container, not from the deploy output** — the SHA
cannot show that a *sentence* changed:

    COMBO_EXIT_CENSUS_SERIES        ('KXMVESPORTSMULTIGAMEEXTENDED', 'KXMVECROSSCATEGORY')
    COMBO_EXIT_CENSUS_SHARD_SERIES  KXMVECROSSCATEGORY-SHARD1
    COMBO_EXIT_CENSUS_SHARD_BOOKS_READ  0
    buy ticket scoped               True
    bid route  scoped               True

So Sunday's measurement will run against a screen that already names the
population its 40 books came from, which is what §12.4 required and why it was
not deferred to the result.

**DEPLOYED EARLIER on Joe's word ("deploy it"), and verified.** Live is on
**`8755de6`**, machine `7812601a239428` — **unchanged, so no volume was
replaced and no credit fact inverted.** Via `.github/workflows/deploy.yml`
(`34373441693`), which is the only way either instance ships.

**Verified IN THE RUNNING CONTAINER, not from the deploy output:**
`routes._record_combo_position`, `parlays.priced_lookup_for`,
`legs_for_position`, `leg_details_for`, `ws.FIRST_SEQ_MAX_PLAUSIBLE = 10000` —
**and that check 13 is actually wired into `create_app`'s source**, which is
the `alerter_factory` lesson (instance five of built-but-never-called) applied
at deploy time rather than discovered a session later.

Money doors re-read off `/api/health` after the deploy, **unchanged**:
`manual_orders` **false (ARMED)**, `combo_bids` true, `engine_orders` true,
`live_quotes_available` true, recorder writing 53s ago, 0 undelivered
notifications in 24h. `/api/hedge` answers 401 behind the session cookie as
before. **Demo was not deployed** and stays on `5664e24`; nothing here
concerns it.

`main` and live are now the same commit.

**Nothing this session touched the odds path** (frozen to 10:00Z 2026-09-14),
the gate, the hand-bet ceilings, or the disarmed bid path. No deploy, no
dependency bump, no billed Anthropic call. Everything touching the live box
was **read-only**: five `sqlite3 mode=ro` replays over `flyctl ssh`.

Three ADRs: **0125**, **0126**, **0127**. Four lanes ran in parallel.

Also checked at session start and worth keeping in the routine: **zero open
Dependabot alerts** (still blind to `cryptography`, which is 50.0.1 on the
box), and **the decisions queue is empty** — the only open issue in the repo
is the map itself, #3, every sub-issue closed.

### THE HEADLINE: `/hedge` had never heard of the positions it exists to exit

A `KXMVE` combination is **enter-only** — zero resting YES bids over 36 levels,
40 of 40 books. ADR 0078 and CLAUDE.md both say `/hedge` is *the only exit an
enter-only combination has*. `/hedge` watches `parlay_positions`.

**`POST /api/manual-orders` wrote zero rows to `parlay_positions`.** The only
writer was `POST /api/hedge/positions`, a separate tap on a separate screen Joe
had to remember. Read off live:

    manual_orders     3 rows, all real (dry_run = 0), all shard-1 combos
    parlay_positions  0 rows
    venue_positions   both filled combos, 2026-09-08 19:41Z until they settled

So for the entire life of both real positions, the exit screen did not know
they existed. **Not on any queue.** The partner found it, and ranked it above
everything that was on one.

**They have since settled, and that was established rather than assumed:**
`poll_log` id 20337 at 15:00Z reports `positions` `ok` with `row_count = 0`, so
the rows stopped because the positions closed and *not* because the poller
stopped. Silence-read-as-health, checked by reflex.

**Fixed, ADR 0125.** A filled combination now writes its own position row,
linked by `combo_ticker` + `parlay_lookup_id`. Both columns already existed in
`schema.sql`, were already accepted by the hedge route, and were **sent by
nobody**. Nothing had to be designed — `_record_lookup` had to stop throwing
away four fields (`side`, `label`, `league`, `commence_ms`) that were already
on the `CandidateLeg`.

Guarded against inventing a holding: dry runs, unfilled orders and
`unrecognised_response` record nothing; a part-fill is watched at the size the
**venue** reports, not the size requested; a partial leg list is refused
outright rather than watched as if the missing leg could not lose; and when the
fill lands but the position cannot be built, **the screen says so** rather than
going quiet. Bookkeeping can never fail a purchase that already spent money.

### The other three lanes

- **The websocket bootstrap frame is bounded — ADR 0126.** `_check_sequence`
  trusted the *first* `seq` on a connection at any value, then dropped every
  legitimate frame after it: silently, books still `valid`, receive-timeout
  still satisfied. **A test had enshrined this as intended behaviour**
  (`..._accepted_whatever_its_seq`, asserting `seq = 8_675_309` is fine). Now
  bounded at 10,000 with the boundary tested both sides. It corrupts the
  screen, never a fill — `live_quotes().fetch` is an independent REST call.
- **Arming the bid path now fails loudly — ADR 0127.** `KalshiRestClient.orders`
  is read by nothing, which is fine only while nothing rests. That is the
  `check_fee` argument exactly, and it expired in silence last time. So: not
  wired; instead a test that goes **red the day `COMBO_ORDERS_ARE_DRY_RUNS`
  flips** without a reconciler. A state converted into a trigger.
- **CLAUDE.md now admits two Measurement rules have no running
  implementation** (`clv.horizons_agree`, `validate.summarise` — ADR 0120).
  Not wired, deliberately; the signal is settled negative.

### Verified by disabling, because that is the only thing that counts

Six mutations against lane A. **Two found real weaknesses rather than
confirming the tests**, which is the whole reason for doing it:

    1  fill guard removed          1 red -> tests strengthened -> 3 red
    2  priced-only filter removed  1 red
    3  partial leg list allowed    1 red
    4  requested size not filled   1 red
    5  silent degradation          1 red
    6  leg detail not persisted    GREEN -> new end-to-end test -> red

**Mutation 6 was decoration**: nothing proved `_record_lookup` actually writes
the fields, only that `leg_details_for` computes them. **Mutation 1 exposed two
tests passing for the wrong reason** — a zero-size position is refused
downstream by the table's own CHECK, so "no row appeared" was true regardless
of the guard. Both now assert the distinguishing consequence instead.

Lane B reported 4 red and 1 red on its two mutations. Lane C went red on the
flag flip and green on restore.

`ruff` clean. **527 tests pass** across every suite the four lanes touch.

### REGISTERED, AND IT NEEDS JOE BEFORE SUNDAY

`docs/measurements/2026-09-09-preregistration-combo-exit-nfl-sunday.md`.

`COMBO_EXIT_CENSUS_BOOKS_READ = 40` is the evidence behind the warning Joe
reads before **every combo tap**, and `combos.py` still says in its own words
that it *"measures the calendar at least as much as the product"*. Sunday
**2026-09-13** is the first attended NFL regular-season Sunday and the next
chance is a week out — so it is registered now, before the data, rather than
sliced after it.

**Three things the registrar corrected or decided, which need reading:**

1. **The baseline is not all 2026-08-09.** It is 20 + 9 on 08-09 and **11 on
   2026-08-18**, in-season MLB/WNBA and 78% tennis by leg. The genuinely open
   clause is **NBA and NFL regular season**, not "in season".
2. **The design is powered in one direction only, and that is fixed in
   writing.** A universal claim dies to `k = 1`, so falsification needs no `n`;
   confirmation is unreachable at any plausible `n` (95% Wilson at `k = 0` is
   27.8% at `n = 10`, 6.0% pooled with the prior 40; under 5% needs 73 books).
   **The null may not be written up as confirmation**, and the word
   "structurally" is forbidden.
3. **`n` inflation was the live trap and it is closed.** Five captures × 40
   rows is not `n = 200`; the denominator is distinct tickers and `G_eff` is a
   required field.

**(A) JOE-GATED, and it is the only one:** the primary arm reaches NFL only
through *cross-game* legs — `DISCOVERY_SERIES` cannot see
`KXMVENFLSINGLEGAME` at all. Reading NFL single-game books on Sunday needs a
`scripts/`-only change landed before **2026-09-13 00:00Z**. Worth it or not?

**Operational, whoever runs it:** do **not** open the cockpit UI to take the
captures — a page-open registers attention and would contaminate the dwell
measurement the odds freeze exists to protect. Redirect stdout to a file per
capture or the scan denominator is lost.

### The partner killed three things, so nobody carries them again

- **The combo-aware fee model (old item 5) — ruled NO and CLOSED.** The premise
  was wrong about what is deployed: the armed path already calls
  `combo_taker_fee` at `COMBO_TAKER_COEFFICIENT = 0.071`, not `calculate_fee`
  at 0.070, and 0.071 covers all 8 observed charges where 0.070 undercharges 4.
  The residual is $0.000030 on a $0.0159 fee — 0.19%, inside ADR 0046's own
  band — while `TAKER_COEFFICIENT` is *deliberately* held at ~2× on MLB. And
  `n = 8`. **Replaced with a trigger:** reopen when the fee alarm fires on a
  combo fill, or at `n >= 30` with mean headroom under 0.071 turning negative
  in any single series. The alarm can pull this itself now.
- **Wiring `clv.horizons_agree` / `validate.summarise`** — a CLAUDE.md accuracy
  fix instead, done.
- **Wiring `KalshiRestClient.orders`** — a tripwire instead, done (ADR 0127).
- **The collections-cache rotation worry** — checked before raising:
  `invalidate_collections_cache` *is* called (`parlays.py:2172`), so a rotation
  self-heals on the second tap. Nuisance, not defect.

### Still open, in order

1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Unchanged and
   untouched this session. Frozen surface:
   `backend/odds/{timing,budget,attention,ondemand,client,sweeplog}.py` plus
   the `window_status` bootstrap question (`timing.py:1536`). A deploy is not
   contamination; logic changes are.
2. **SUNDAY 2026-09-13 — the run sheet. Registration complete, nothing
   captured.** Five slots, fixed clock, **no sixth capture** and no slot moved
   more than 30 minutes (a missed slot is recorded *missing* and the result
   says four of five — *"the pool was thin so we looked again later"* is
   prohibited by name):

       C1 15:30Z   C2 17:30Z   C3 20:00Z   C4 23:30Z   C5 00:45Z (09-14)

   **Two invocations per slot, deliberately separate** — folding them into one
   command would let an empty shard page abort Arm A's capture:

       Arm A (comparison)  --max-books 40                 default series
       Arm D (PRIMARY)     --max-books 25 --series KXMVECROSSCATEGORY-SHARD1

   Redirect stdout to a `.txt` per capture or the scan denominator is lost
   (the 2026-08-18 run hit this). ≤360 unmetered Kalshi calls for the day,
   **zero Odds credits**.

   **Three things that will otherwise be misread on the day:**
   - **Arm C is EXPECTED to abort.** Both NFL series returned 0 open rows
     midweek and a named `--series` with no rows aborts by design. Recorded
     now so an abort is not later read as a failure of the instrument.
   - **Nobody may open the cockpit UI to run any of this.** A page-open
     registers attention and contaminates the dwell measurement the odds
     freeze exists to protect. These are shell commands and no browser.
   - **A null is not confirmation** (§0). At `k = 0` the licensed sentence is
     only that the denominator grew and the bound narrowed. The word
     "structurally" is forbidden outright.

   **Also on Sunday, unrelated to the census:** it is the first real exercise
   of the combo-fill → `parlay_positions` wiring (ADR 0125). If he buys a
   combination, check a `parlay_positions` row appeared — not that the route
   returned 200.
3. **One `pip-audit` ignore remains and it is NOT a deferred fix.** `pyarrow`
   `GHSA-rgxp-2hwp-jwgg`, a known-bad match: the flaw needs an Arrow **IPC
   file** read with pre-buffering and this repo only writes Parquet.
   **Re-evaluate if anything starts reading `.arrow` or `.feather`** — that is
   the trigger. Also recorded, not blocking: pytest 8.4.2 / `PYSEC-2026-1845`,
   dev-only, deliberately outside the gate.
4. **The absent consensus column on every combo record.** `manual_orders`
   writes `consensus_absent_reason = 'combo_ticker'` for **100% of the bets
   placed through the tool**, while `parlay_lookups.hold` holds the desk's own
   headline number for the same ticket (0.170, 0.063, 0.209 on his three live
   lookups) and `PriceOnKalshi` renders it one component above. Whether that is
   honesty or a hole is a craft question — the partner assigned it to
   `sharp-bettor` and it was not reached this session. ADR 0125 "what this does
   not decide".
5. **ADR 0046's combo tripwire is live on the committed record** — the fixture
   fill is charged $0.00003 above the flat coefficient. Nothing in production
   consumes it. **Now covered by the trigger above rather than open work.**
6. **Nothing reconciles a combination's settlement.** `resolve_from_venue`
   settles leg markets; whether a minted `KXMVE` ticker settles its position
   automatically is unobserved. Surfaced by ADR 0125, not acted on.

**Joe-gated: NOTHING. All five answered and closed this session.**

- ~~**(E)** Deploy the scope correction before 2026-09-13 15:30Z?~~ **ANSWERED
  YES and DONE.** Live is on `6f30079`, both surfaces verified scoped **inside
  the container**. Four days ahead of the deadline.

Also answered and closed this session:

- ~~**(A)** The NFL single-game arm for the census?~~ **ANSWERED YES
  2026-09-09 and DONE.** `--series` on
  `scripts/measure_combo_book_presence.py`, repeatable, `scripts/`-only.
  `DISCOVERY_SERIES` is deliberately **not** moved — every book in the 40-row
  census came from those two and Arm A's comparability depends on it. The JSON
  now stamps `series_read` / `default_series`, and a named series returning no
  open rows **aborts** rather than reporting an empty rate. Both NFL series
  return HTTP 200 on `/series` with 0 open rows midweek, so the tickers are
  right and their availability on the day is the thing Arm C tests.

- ~~**(C)** Add a shard arm to Sunday?~~ **ANSWERED YES 2026-09-09 and DONE —
  Amendments 1 and 2, and it changed what the run is.**

  The finding: **`KXMVECROSSCATEGORY-SHARD1` is a separate series** not in
  `DISCOVERY_SERIES` (`series_ticker=KXMVECROSSCATEGORY` returns only
  non-shard tickers), and across all three recorded runs — 20 + 9 + 11 rows —
  **`SHARD1` tickers number zero**, while **every one of Joe's ~50 real
  combination fills is `KXMVECROSSCATEGORY-SHARD1-*`**. Not false; **narrower
  in scope than the screens imply, and the gap is where his money is.**

  **Arm D is now PRIMARY and Arm A is demoted to the comparison arm.** The
  registrar resolved the rank on §0's own arithmetic rather than by which
  population feels weightier: Arm A's *unique* contribution is comparability
  to 0-of-40, which feeds the branch already proved unable to conclude
  anything, while its *usable* contribution — falsification at `k = 1` — is
  not unique to it, because one resting YES level anywhere kills the universal
  sentence. **The rule, reusable: the headline goes to the arm whose
  population the claim is APPLIED to, not the arm whose population it was
  historically measured on.** Co-primary was refused — two headlines is two
  chances to pick the better one afterwards.

  `n = 25`, all five slots, **+140 unmetered Kalshi calls** (≤360 for the day
  with Arm A), zero Odds credits. **A separate invocation from Arm A at each
  slot**, because a `--series` with no open rows aborts by design and folding
  the shard into Arm A's command would let an empty shard page destroy Arm A's
  capture. Thin-day rule: ≥10 pooled distinct books → full scoring; 1–9 →
  ABORTED-THIN except the falsifying branch; 0 → the instrument aborts and
  that is reported, not retried.

  **The population is one literal series**, after enumeration: `SHARD2`,
  `SHARD3`, `KXMVESPORTSMULTIGAMEEXTENDED-SHARD1` and
  `KXMVENFLSINGLEGAME-SHARD1` all **404** on `/series`. That is today's
  answer, not a permanent one.

  **The constraint the registrar added unprompted, and it binds the
  write-up:** `markets_page` is newest-first and the page came back full, so
  Arm D samples the **newest slice** of shard 1, not a random sample — and
  newly minted combinations are plausibly *less* likely to carry a resting
  order, the direction that flatters a null. The null sentence is fixed in
  advance to say *"the newest N shard-1 combinations"*, with the age range in
  the result's **headline, not a footnote**. So "13 of 1,000" is a rate over
  the newest page, not over the series; the open shard population is ≥1,000
  and its true size is unmeasured.

- ~~**(D)** Does the buy-ticket copy need scoping before Sunday?~~ **RULED
  OWED and DONE the same day** (registration §12.4). The sentence *"every
  combination book this repo has ever read had no YES bid — 40 of 40"* is
  true and correctly sourced, and is read by someone tapping a shard-1
  combination those 40 books contain **zero** of. **No sourcing guard could
  catch it — not a digit is wrong**; what was wrong is the scope a reader
  supplies.

  Not deferred to Sunday, for a named reason: waiting leaves the screen making
  an unscoped claim *during* the measurement that scopes it, and in the
  ABORTED-THIN branch the correction never lands at all — **a caveat selected
  for being survivable.**

  **Both surfaces** (`combo_note` on the buy ticket, and the bid route's 422)
  now name the two series and say plainly that zero shard-1 books have been
  read, then stop — implying neither that the shard was measured nor that it
  differs. Correcting one and not the other reproduces the defect on the
  surface nobody looks at. **Sourced, never typed, and that is forced rather
  than tidy:** `KXMVECROSSCATEGORY-SHARD1` carries a digit and the existing
  guards refuse bare integers, so typing it would trip them or force someone
  to weaken one. New constants `COMBO_EXIT_CENSUS_SERIES`,
  `..._SHARD_SERIES`, `..._SHARD_BOOKS_READ`. **No behaviour changed** — no
  ceiling, no route logic, no order path.
- ~~**(B)** Deploy to live?~~ **ANSWERED YES 2026-09-09 and DONE.** Live is on
  `8755de6`, verified in the container. **Still unobserved: the wiring firing
  on a real fill.** Nothing has bought a combination through the desk since it
  shipped, so the first real exercise is Sunday — and the thing to check that
  day is that a fill leaves a `parlay_positions` row, not that the route
  returned 200.

**These letters are new this session.** The previous session's B, C and D are
answered, done and closed — **check `git log --oneline -1 -- <the file a
letter names>` before re-asking one**, because the letters restart every
session and a stale one reads as current.

## 2026-09-09 (second session) — the audit file is closed after 33 days, the money-path signer finally has a real test, and the fee alarm was wired the day its own excuse expired

**STATE at close.** `main` = **`f7607b6`** at session start, clean; this
session's work is one commit on top. Live and demo are on **`69ba254`** and
that is correct — `f7607b6` was docs-only, so nothing was owed a deploy.
**Nothing this session touched the odds path** (frozen to 10:00Z 2026-09-14),
the gate, the hand-bet ceilings, or the disarmed bid path. No deploy, no
dependency bump, no billed Anthropic call, nothing money-touching.

Read `/api/health` rather than believing this. At session start it said
`manual_orders` **false (ARMED)**, `combo_bids` true, `engine_orders` true,
`live_quotes_available` true.

Six ADRs: **0118**–0123, plus **Amendment 2 to 0117**.

### The headline: an alarm whose written excuse had expired

`Alerter.check_fee` compares a real fill's charged fee against `core/fees.py`.
**It had no caller from the day it was written**, and its docstring justified
that: no order had ever been placed, so there was no fill to reconcile.

**That stopped being true on 2026-09-08**, when the hand-bet path took real
fills. So fills existed and nothing compared their fee to anything, silently —
while `TAKER_COEFFICIENT` is knowingly held at 0.070 against nine observations
pinning k near 0.035. The alarm that would notice the schedule moving under
the armed money path was the one not wired.

It is wired now, in the fill-ingest path, and **no schema change was needed**:
`fills.fee_actual` was already the venue's ground truth. It is **one-sided —
it fires only when Kalshi charges MORE than predicted** — and that is the
decision, not an oversight: a two-sided test fires on every MLB hand fill
forever *by policy* (ADR 0058 keeps the flat coefficient while the venue
charges half), and an alarm that must be muted on day one is worse than none.
An undercharge is the event that matters — it means every EV figure is
optimistic. Silent on the entire observed record. ADR 0123.

**Three things fell out of it, and each is its own small finding:**

- `scripts/run_loop.py:1048` now passes the `alerter_factory`. Without that one
  line the reconciliation would have run and reached nobody — **instance five
  of "built but never called", in the same session that wrote an ADR about
  instances one to four.**
- The alert copy rendered `${predicted:.2f}`, turning a real
  $0.0142-vs-$0.0162 divergence into "predicted $0.01, charged $0.02" — the
  direction and the size deleted from a message whose subject is "stop the
  line". Now `.4f`.
- Enrolling `reconcile_fill_fees` in `IO_CALLS` immediately found a real
  ordering defect: the alarm shares the poller's connection, so
  `Alerter._claim`'s INSERT sat between it and `await poll_positions(...)`, a
  Kalshi round trip, with no commit between. `_claim` commits internally, which
  is exactly why it was invisible.

### `tasks/audit-2026-08-07.md` is CLOSED — all six, after 33 days

It stays **in place**, not archived: ADR 0116 says so because two registrations
and ADR 0003 cite it by item number. It now carries a dated all-closed header.

| item | verdict |
|---|---|
| 5 deci-cent asks | CLOSED — and it never needed the live order it was "blocked on" |
| 23 marts headline | CLOSED — ADR 0118 |
| 25 order path | CLOSED (prior session) |
| 27 vacuous skips | CLOSED — the regression used to produce a **green** run |
| 33 agent fleet | CLOSED **by deletion**, not by wiring — ADR 0106 removed it |
| 34 `ws.py` tests | CLOSED — and closing it found a live defect, ADR 0122 |

**Three of the six were stale toward MORE work than existed.** 5 was recorded
as blocked on a live order it no longer needs; 33 as needing a cost decision
for code that had been deleted; 34 as untested for symbols two test files
already cover. **An open-items list decays toward overstating the backlog**,
because closing an item needs someone to notice and nothing notices. Re-check
before planning against a list older than a few weeks.

### The rest, in one line each

- **The money-path signer has a real test.** `KalshiAuth._sign` authenticates
  real orders and its only coverage asserted the header was *truthy*. Now 23
  round-trip tests: **17 mutations of the signer, each turning them red, where
  the old test caught 1 of 17.** Plus a guard the module's own docstring asks
  for and the code never had — a non-RSA key now refuses at load with a named
  message instead of dying later inside `.sign()` looking like bad credentials.
- **`_resubscribe` deleted — and it was never instance five.** It was the
  *rejected branch* of a decision written three lines away in `_resync_all`'s
  docstring. Reconnect is handled two independent ways with four staleness
  catchers between a dead socket and the screen. ADR 0119.
- **A data frame with no `seq` is now a gap, not an exemption.** Writing the
  `_check_sequence` tests found the exemption was type-blind: an
  `orderbook_delta` without a `seq` would have passed the integrity check *and*
  been applied — a silently wrong orderbook, through the one branch that skips
  the check. ADR 0122.
- **`pip-audit` runs blocking in CI.** Dependabot showed one advisory; this
  shows **seven**. Green at rest via seven per-ID ignores, each commented, each
  a record of an open decision — and red on anything new. Pinned by a test so
  the list cannot grow quietly. ADR 0121.
- **The unreached-definition walk was read for the first time since 09-05** and
  all 55 entries triaged. ADR 0120.

### THE ONE THING TO TELL JOE

**The `cryptography` bump is 44 → 50, not 44 → 49 — six majors, not five.**
`GHSA-g6cj-pr64-35w5` (a PKCS#7 decrypt oracle) was introduced at 44.0.0 and is
not fixed until 50.0.0, so stopping at 49.0.0 clears alert #15 and leaves that
one standing. Everything written before today says five majors and 49.0.0.
ADR 0117 Amendment 2 corrects it. **It is now much safer to take**, because the
signing test that should sit in front of it exists.

### Deployed and verified, after the entry above was written

**Live is on `3bee615`**, machine `7812601a239428` (unchanged -- no volume
replaced). Money doors unchanged off `/api/health`: `manual_orders` **false
(ARMED)**, `combo_bids` true, `engine_orders` true. Verified **in the running
container**, not from the deploy output: the `alerter_factory` at
`run_loop.py:1063`, `reconcile_fill_fees`, `_SEQUENCED_DATA_FRAMES`, and the
RSA key-type refusal. `run_loop.py` is up and a full mirror cycle ran 1.5 min
after the deploy, all five endpoints ok.

**Then the shipped reconciliation was replayed over the stored hand fills**
(`scripts/replay_fee_reconciliation.py`, committed and read-only):
`docs/measurements/2026-09-09-fee-alarm-replayed-over-every-hand-fill.md`.

    window 2026-08-10 .. 2026-09-08, 21 days, 97 fills, 97 distinct orders
    0 of 22 informative rows would have alerted

**The denominator is 22, not 96, and the first draft of that document said
96.** 74 rows cannot fire at all: combos are priced by a ceiling that exceeds
every observed charge by construction, MLB carries ADR 0058's deliberate
2.00x. `measurement-skeptic` caught it, along with a claim that was simply
**wrong** -- "no fill has ever been charged more than the model predicts",
which is false because `calculate_fee` was not the model used on 64.6% of the
rows and its never-under property is *refuted* on combos (`core/fees.py:91`).
The document now carries a "what the first draft got wrong" section; read that
before quoting any number from it.

**The finding that is actually new** is independent of the alarm: on 21 taker
fills across 8 non-baseball series, the charge equals `ceil(0.070*C*P*(1-P))`
on the $0.0001 grid **exactly** -- an out-of-sample replication of k = 0.070,
and confirmation that a correct model matches a charge exactly rather than
approximately. Combinations carry only +1.4% mean headroom, an order of
magnitude less than anything else: if the ADR 0073 ceiling is ever crossed it
gets crossed there.

**Chased and closed, so nobody re-finds it:** the one `KXMLBGAME` row whose
charge matched its prediction looked like a counterexample to the baseball
0.035 split. It is a **maker** fill at k = 0.0177, about a quarter of the
taker rate. All 7 taker MLB rows sit at 0.035 as expected.

**Still unobserved: the alarm firing.** Nothing has made it fire against a
live fill, and by design nothing should until the schedule moves.

### Live is on `5664e24` and the signer was proved against the exchange

Deployed 2026-09-09 on Joe's word, machine `7812601a239428` (unchanged, no
volume replaced). **Verified in the running container, not from the deploy
output:** `cryptography` **50.0.1**, where the identical read returned
**44.0.3** minutes earlier, on OpenSSL **4.0.2**.

**Then Kalshi was made the judge.** One authenticated read-only
`GET /portfolio/balance` on shards 0 and 1, from inside the container, using
the app's own credentials borrowed off its child process: **the signature was
accepted on both.** That is the check nothing in this repo can perform, because
every test signs and verifies inside our own process -- only the exchange can
say the wire bytes are still right. No order, no write, no key printed.

Money doors re-read after the deploy, unchanged: `manual_orders` **false
(ARMED)**, `combo_bids` true, `engine_orders` true. Recorder writing.

**So the six `cryptography` advisories are closed ON THE BOX, not just in the
repo.** `main` and live are the same commit.

### Joe answered B, C and D on 2026-09-09 and all three are closed

**(D) The four stale remote branches are DELETED.** `origin` now carries only
`main`. The one named `fix/frontend-vulnerabilities` held `next` 16.3.1 -- the
version with the two critical unauthenticated RCEs -- on a public repo, under a
name that said the opposite of its contents.

**(C) `cryptography` is 44.0.3 -> 50.0.1. ADR 0124.** Six majors under the
RSA-PSS order signer, done with Joe at a screen as he required.

**The check that mattered was not the test suite**, because every test in this
repo signs and verifies inside one version and so cannot see the library
changing what it puts on the wire -- which is the failure that would reach
Kalshi as a 401 indistinguishable from bad credentials. So: sign under 44.0.3,
upgrade, verify **that same signature** under 50.0.1. It verifies; a fresh
50.0.1 signature verifies; a *different* message is still rejected, which is
what makes the first two mean anything. The throwaway key is generated in the
check; the real key was never read.

**The ignore list went from seven entries to one, by deletion not
suppression.** `pip-audit -r requirements.txt --strict` with **no ignores at
all** now reports exactly one finding: `pyarrow` `GHSA-rgxp-2hwp-jwgg`, the
verified-unreachable one. `TestThePipAuditIgnoreListIsPinned` went red on the
change by name before it was updated, which is the whole reason the list is
pinned.

**(B) SHOULD NEVER HAVE BEEN ASKED. It was already done on 2026-09-05.** See
item 6 below. Asking it cost a billed Anthropic call that reproduced the
existing capture exactly, and writing the "new" script overwrote the tracked
one (restored from `c2976ec`, unchanged). `TestNothingNewCanReachTheBilledPath`
caught the overwrite independently -- an unallowlisted `build_client` call site
-- which is the billed-path guard doing precisely its job.

### Still open, in order

1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Unchanged and
   untouched this session. Frozen surface:
   `backend/odds/{timing,budget,attention,ondemand,client,sweeplog}.py` plus
   the `window_status` bootstrap question (`timing.py:1536`). Sunday 09-13 is
   the only attended NFL Sunday this month and the freeze is what makes it a
   measurement. A deploy is not contamination; logic changes are.
2. ~~**The `cryptography` bump.**~~ **DONE 2026-09-09, 44 -> 50. ADR 0124.**
   Verified by cross-version signature check, not by the suite alone.
3. **One `pip-audit` ignore remains, and it is NOT a deferred fix.** It was
   seven on 2026-09-08. Six were `cryptography` and went with the bump; the
   seventh, `GHSA-m2h6-j472-rp4c`, was a false positive at 44.0.3 and is moot
   at 50.0.1 anyway.

   What is left is `pyarrow` `GHSA-rgxp-2hwp-jwgg`, a **known-bad match**: the
   flaw needs an Arrow **IPC file** read with pre-buffering and this repo only
   ever writes Parquet (`pq.write_table`, `backend/store/publish.py`).
   **Re-evaluate if anything starts reading `.arrow` or `.feather`** — that is
   the trigger, and it is the only thing that would turn this into a real
   deferred fix. The `pyarrow` 19 -> 23 bump itself is four majors on the
   publish path, touches no money path, and has not been asked for.

   Also recorded, not blocking: one **dev-only** finding, pytest 8.4.2 /
   `PYSEC-2026-1845`, fixed in 9.0.3. Dev dependencies are deliberately outside
   the gate (they do not ship), so this will never turn CI red on its own.
4. **The gap branch parks `_last_seq` at an unbounded observed `seq`.** One
   corrupt or wildly large `seq` and every legitimate frame afterwards looks
   like a reorder and is dropped **silently**. The reconnect saves it in
   practice (it resets `_last_seq = None`), so it is latent, not live. There is
   no plausibility bound on gap size. ADR 0122 "what this does not decide".
5. **ADR 0046's combo tripwire is live on the committed record.** The combo
   fill in `tests/fixtures/portfolio_fills_redacted.json` is charged $0.00003
   *above* what the deployed flat coefficient predicts. Nothing in production
   consumes that today. **A partner decision about a combo-aware fee model, not
   a patch.**
6. ~~**Scout Anthropic refusal fixture (ADR 0106 §5.2)**~~ **ALREADY DONE ON
   2026-09-05 — this entry was STALE and it cost a billed call to find out.**
   `tests/fixtures/anthropic_scout_captured.json` and
   `scripts/capture_agent_wire_fixture.py` landed in commit `c2976ec`, titled
   *"Joe's answers B, C and D: … one real Anthropic response is captured"*, and
   `tests/test_agent_wire_format.py::TestTheCapturedPayloadIsTheRealWire` has
   been driving it since. §5.2 is closed.

   **Read this before trusting any other line in the Joe-gated list.** On
   2026-09-09 a session re-asked (B), got a yes, and spent a second call that
   reproduced the 2026-09-05 result exactly — 25 content blocks there, 11 here,
   the same structural finding. Nothing was learned. The same session had just
   written *"an open-items list decays toward overstating the backlog; re-check
   before planning against a list older than a few weeks"* about the audit file,
   and did not apply it to the list two paragraphs below.
7. **What the reachability walk found and nobody has acted on** (ADR 0120): the
   CLV validation layer (`clv.horizons_agree`, `validate.summarise`) runs from
   nothing, so two CLAUDE.md measurement rules have no running implementation —
   mitigated, because the beta fits went through code that *is* reached and the
   signal is settled negative. `KalshiRestClient.orders` is read by nothing, so
   nothing reconciles against the venue's own view of resting orders — inert
   while the bid path is disarmed, a silent gap the day it is re-armed.

8. **Four stale remote branches, and one of them is actively misleading.**
   Found in the CI log of this session's own push, not by looking for them --
   nothing lists remote branches at session start and the lane board reads
   worktrees and local branches.

       fix/frontend-vulnerabilities   1 ahead,  794 behind
       docs/audit-stale-todo-items    2 ahead,  794 behind
       lane/frontend-wip              0 ahead, 1107 behind
       parlay_props                   0 ahead,  374 behind

   **`fix/frontend-vulnerabilities` is the one that matters.** Its single
   commit is *"deps: upgrade next to 16.3.1, clearing four vulnerable
   packages"* -- and **16.3.1 is the version carrying the two critical
   unauthenticated RCEs** that ADR 0117 patched by going to 16.3.3. So on a
   public repo there is a branch whose name says it fixes vulnerabilities and
   whose content reintroduces them. Anyone reading branch names would take it
   the wrong way round.

   The other two with commits are superseded: `docs/audit-stale-todo-items`
   prunes a `NEXT.md` that ADR 0116 has since cut differently. The two at
   `0 ahead` carry nothing unique and are free deletes.

   **DELETED 2026-09-09 on Joe's yes.** `origin` now carries only `main`.

**Killed this session, so nobody carries them again:**

- ~~The `_next/image` middleware exemption.~~ The optimizer is off, so the
  exemption is unreachable code behind a disabled endpoint and ADR 0117 already
  records that re-enabling restores both in one line. The config comment is
  enough.
- ~~The `eu` lever.~~ It said "nothing to build" for eight sessions. Gone.

**Joe-gated:**

- ~~**(B)** Authorise the one billed Anthropic call for the Scout fixture?~~
  **WITHDRAWN — it was answered and done on 2026-09-05** (`c2976ec`). See item
  6. **The lettering is reused every session**, so a stale `(B)` reads as
  current; check what a letter refers to before asking it again.
- ~~**(C)** approve `cryptography` 44 → 50?~~ **ANSWERED YES 2026-09-09 and
  DONE, with him at a screen as he required.** 50.0.1, verified by signing
  under 44 and verifying that signature under 50. ADR 0124.
- ~~**(D)** delete the four stale remote branches?~~ **ANSWERED YES 2026-09-09
  and DONE.** `origin` now carries only `main`.

---

## 2026-09-09 — two critical unauthenticated RCEs were live on the public box and are now patched; the effort dial is set; the month-old audit is down to two real items

**STATE at close.** `main` = **`69ba254`**, pushed. **Live and demo are both
on `69ba254`.** Live stayed on machine `7812601a239428` across both deploys,
so no volume was replaced and no credit fact inverted. Read `/api/health`
rather than believing this table.

    live     69ba254 verified by reading /api/health build.git_sha
    demo     69ba254 no longer deliberately behind — it ran the same
             vulnerable image with no auth token at all, so it was patched too

CI green on `6348a42` (`34307087087`) and on `88ac4ec` (`34307931989`).
The run on `be29fcb` was **cancelled** by the next push — see the lessons
entry on when that is permissible, because it is a bounded exception and not
a precedent.

Money doors **unchanged**, verified off `/api/health` after the deploy:
`manual_orders` **false (ARMED)**, `combo_bids` true (dry), `engine_orders`
true (dry). Nothing this session went near arming.

### THE FINDING: the image optimizer was outside the auth gate

`frontend/src/middleware.ts:160` reads
`matcher: ["/((?!_next/static|_next/image).*)"]`. `_next/image` is excluded
from the auth middleware. The comment above justifies the exclusion for
`_next/static`, which really is inert hashed assets. **`_next/image` is a
server-side image processor and it inherited the static-asset exemption by
sitting next to one in a regex.**

A routine push at 03:25:50Z triggered a GitHub rescan which opened three
alerts, **none of which was on any of the three queues**:

    #17  CRITICAL  cvss4 9.5  next 16.3.1   unauth RCE, Image Optimization API, AVIF
    #16  CRITICAL             next 16.3.1   unauth RCE, windows-hosted servers
    #18  HIGH      cvss4 8.9  sharp 0.35.3  libheif

Exposure was established **against the live box, not the source**: a gated
path 307s to `/login`, and `/_next/image` answers with the optimizer's own
validation strings to a request with no session cookie. `next.config.ts:8` is
`output: "standalone"` with `unoptimized` never set; `fly.live.toml:674`
publishes port 3000, which is Next itself, with uvicorn on loopback behind
it. Nothing sanitises ahead of the optimizer. `sharp` 0.35.3 with native
libvips was confirmed present in the running container.

**Patched: `next` 16.3.3, `sharp` 0.35.4.** No `overrides` needed — `next`
declares sharp at `^0.35.3`, which already admits 0.35.4, so the lock was
merely pinning an old resolution. `npx tsc --noEmit` clean, `npm run build`
green, and the fix verified by reading **16.3.3 and 0.35.4 out of the live
container**, not from the deploy output. ADR 0117.

**Two bounds kept deliberately. Reachable is established; EXPLOITABLE IS
NOT.** `remotePatterns` is empty so no remote fetch is possible;
`localPatterns` is `**` but no local path is known to return
attacker-influenced bytes, and whether one can be made to was not determined.
And #16 does not reach production — the container is Debian on Linux — it
reaches `next dev` on the Windows box. Same patch, so no time was spent
deciding.

### The instrument lied and that is its own finding

Alert #15 (`cryptography`) was marked **fixed** by the same rescan.
`requirements.txt:9` pins `cryptography~=44.0`, installed is 44.0.3, and the
advisory's vulnerable range is `>= 42.0.0, <= 48.0.0` with the fix in 49.0.0.
**The pin is inside the vulnerable range and nothing about it changed.**
GitHub says fixed; the pin says otherwise. Not resolved, not treated as true,
and it is why the other three fixes were verified in the container rather
than by watching an alert close. Bumping five majors on the RSA-PSS path that
signs real-money orders is **not** smuggled into a security patch — it is
open, item 3 below.

### Also landed

- **The effort dial is set** (previous item 3, closed). The key is `effort`
  in `.claude/agents/*.md`, values low|medium|high|xhigh|max; the Agent tool
  has **no** spawn-time effort parameter, and extended thinking always
  inherits and cannot be set per agent. Partner's assignment: `partner`,
  `measurement-skeptic`, `pre-registrar` **high**; `kalshi-platform`,
  `runtime-realist`, `sharp-bettor` **medium**. **None is low, and that is
  the finding** — all six are reviewers whose completion criterion is a
  judgement, so the Sonnet-for-lookup rule was never going to bite on them.
- **`lookup-scout` is new** — sonnet, effort low, Glob/Grep/Read/Bash, briefed
  to answer the literal question with a `file:line` and return nothing else.
  It is what `partner.md` already asked for and did not exist. **It does not
  load until the next session.**
- **`tests/test_agent_definitions_parse.py` is new, 36 tests**, and it exists
  because this session nearly shipped the exact defect it guards: the first
  draft of `lookup-scout.md` had an unquoted `: ` in its description, which
  makes the YAML unparseable. It reads as ordinary English and nothing would
  have reported it — the agent would simply not be there. Verified by
  disabling three ways (5 red, 2 red, 1 red), green on restore.

### Still open, in order

**Every claim here was read off an instrument this session unless it says
otherwise.**

1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Unchanged and
   untouched. Frozen surface:
   `backend/odds/{timing,budget,attention,ondemand,client,sweeplog}.py`, plus
   the `window_status` bootstrap question (`timing.py:1536`). Sunday 09-13 is
   the only attended NFL Sunday this month and the freeze is what makes it a
   measurement. A deploy is not contamination; logic changes are.
2. ~~**`_next/image` is still outside the auth matcher.**~~ **THE OPTIMIZER IS
   OFF, same session.** `frontend/next.config.ts` sets
   `images: { unoptimized: true }` (ADR 0117 Amendment 1), deployed to live
   and demo. **Verified by response, not by config**: an unauthenticated
   `GET /_next/image?url=%2Frobots.txt&w=63&q=75` returned **400** with the
   optimizer's own width validator before, and returns **404** after, on both
   instances. That validator string is the discriminating signal — it can
   only come from the optimizer.
   **The "zero usages" claim was checked because it is the flattering
   answer.** A first pass said `CrewAvatar.tsx` really imports `next/image`;
   reading the file shows it draws inline SVG and line 4 is a comment saying
   it deliberately avoids the pipeline. Two matches in the whole frontend,
   both non-usages.
   **What remains open: the exemption itself.** `middleware.ts:160` still
   excludes `_next/image` from the auth matcher, so re-enabling the optimizer
   restores the exposed endpoint *and* its exemption in one line. The config
   comment says so at the point of change.
3. **The `cryptography` pin, and a blind spot in the instrument.** `~=44.0`
   (installed 44.0.3) is inside a live advisory's vulnerable range
   (`>= 42.0.0, <= 48.0.0`, fixed in 49.0.0), and GitHub reports the alert
   **fixed**. Chased and settled 2026-09-09: `requirements.txt:9` is the only
   manifest naming it, `Dockerfile:37-39` installs from that file alone, #15
   is the only alert for the advisory, and the advisory has not changed since
   09-04. **The cause is that GitHub's dependency graph holds no resolved
   version for the package** — the SBOM carries two `cryptography` entries and
   both have an empty `versionInfo`. An advisory cannot match a node with no
   version.
   **So this is a monitoring failure, not a stale reading, and it is the worse
   of the two.** A stale alert self-corrects on the next scan; a package with
   no resolved version never matches an advisory again. `cryptography` is now
   **invisible to dependabot on this repo**, including for advisories not yet
   published — so the alerts query in the SESSION START box above will not
   catch the next one. Two separate pieces of work: fix the graph resolution
   (or add an independent check such as `pip-audit` in CI), and decide the
   bump. **Do not bump it as a chore** — 49.0.0 is five majors up on the
   RSA-PSS request signer, which `requirements.txt` marks "not optional, not
   swappable", and it is a change to take with a live signing test in front of
   you. ADR 0117.
4. **`tasks/audit-2026-08-07.md` cannot be archived — two items are live.**
   Re-checked all six this session; 5, 27, 33 and 34 are FIXED with
   citations. The two that survive:
   - **Item 23 — TOP OF THE NEXT SESSION'S LIST, AND THE DECISION IS ALREADY
     MADE, SO DO NOT RE-DERIVE IT.** `backend/analysis/marts.py:148-165` —
     `headline_verdicts` walks `MARTS` and appends every `status == "ok"`
     panel's verdict, and **never consults `missing_required_marts`**. So a
     per-bucket finding can headline the dashboard while the
     multiple-comparisons qualifier is absent entirely. `tests/test_marts.py:108`
     (`test_unavailable_panels_contribute_no_headline`) **enshrines it** — it
     builds a warehouse with no `mart_multiple_comparisons` at all and
     asserts the headline appears anyway. This is the repo's own "count your
     tests" rule being defeated by the dashboard that exists to enforce it.
     **The partner's ruling, 2026-09-09: SUPPRESS.** `headline_verdicts`
     returns nothing for a panel whose required marts are missing. An
     unqualified per-bucket finding headlining the dashboard is rule 1 — a
     large apparent edge with the multiple-comparisons qualifier *absent* is
     precisely the defect the mart was built to prevent, and "show it with a
     warning" is how warnings get read past. **Re-point the existing test to
     assert the headline is ABSENT; keep it, do not delete it**, and verify by
     restoring the old behaviour. Deferred only because it is a behaviour
     change to a reporting surface at the end of a session that had already
     deployed twice.
   - ~~**Item 25.**~~ **DONE, same session.**
     `tests/test_order_authorisation_guards.py` covers step 1 (404,
     `"does not exist"`) and step 3 (422, `"found no edge worth betting after
     fees"` and `"was sized at 0 contracts"`). Both pin the **status and a
     discriminating substring**, because a status code alone cannot say
     *which* guard fired — and both assert `quotes.calls == []`, since these
     refusals precede the live-quote refresh, which is a side effect only the
     intended guard produces. Fixtures reused from `test_quote_refresh.py`;
     no new harness. **Verified by disabling each guard separately**, which is
     the part that matters: with step 3 removed the request reaches
     `backend/core/ev.py:133` and dies on `contracts must be positive, got 0`
     — that is the shipped defect itself, a zero-authorised row travelling
     toward being priced as a real order. Step 1 stayed green throughout, so
     the step 3 test really does isolate step 3. `git diff backend/` empty
     after restore, checked independently.
     Out of scope, stated in the module docstring: a *negative*
     `suggested_contracts` (the guard's `<= 0` covers it, only `0` is
     exercised), other routes to a missing row than "never inserted", and the
     interaction of these guards with steps 4-7.
5. **`_resubscribe` (`backend/kalshi/ws.py:269`) is called by nothing** — not
   `run()`, not `_resync_all`, not any test. Found while re-checking audit
   item 34, and it is **instance five of "built but never called"**, this time
   on the WebSocket reconnect path.
   **Treat it as a live-behaviour question, not a tidiness one.** A
   resubscribe that never runs means a dropped socket silently stops
   delivering the markets it was watching, and the desk would show stale
   prices rather than an error. Nobody has checked whether reconnection is
   handled some other way (a fresh `run()`, a supervisor restart) or not
   handled at all. **Establish which before deleting it or writing it a
   caller** — deleting dead code that was covering a real gap would remove the
   evidence along with the symptom.
6. **Scout Anthropic refusal fixture (ADR 0106 §5.2)** — one **billed** call,
   Joe-gated. **Do not pre-build the harness**: a module with no caller is
   this repo's four-times-caught pattern, and building it "ready for him" is
   how it gets committed as a feature.
7. `eu` lever (2026-09-28) — nothing to build. Stop carrying it as open.

**Decided this session, so nobody re-derives them (ADR 0116 leftovers):**

- **Should the NEXT.md session index split? NO.** The file is under 20% of the
  ceiling. Revisit at 90%, which is the rule that already exists.
- **Do ADRs and measurements carry CLAUDE.md's inline-correction sediment?
  DROPPED, and the reason transfers.** The cut was justified by
  *always-loaded, every-turn* cost. An ADR is opened by exactly the reader who
  came for the trail. For them the sediment is the product. 118 ADRs plus 155
  measurements is a multi-session sweep to remove the one thing those files
  exist to carry.

**Joe-gated:**

- ~~**(A)** Fund shard 0?~~ **ANSWERED AND DONE — Joe funded shard 0 with
  $5.00, 2026-09-09.** Verified off the live box through the desk's own
  `LiveQuoteSource.shard_balance`, not taken on report:

      shard 0  Default (singles)   $5.0020   portfolio_value $0.00
      shard 1  Combos              $14.1714  portfolio_value $5.88
      shard 2, 3                   $0.0000

  **Single-market hand bets are now payable at the venue**, which was the
  whole blocker — check 9a's refusal on shard 0 should stop firing. **Nobody
  has yet placed one**, so that the refusal is gone is an inference from the
  balance, not an observation; the first single fill is what would confirm it.
  $5.00 is a real ceiling: at 50c a contract it is ten contracts, and **the
  binding limit on a single is now depth at the ask or this collateral, not
  any cap of ours.**
  Do not reconcile shard 1 against the old $22.24 figure without care — cash
  plus position value is $20.05 now, and the difference could be fills, fees,
  or a different basis in the older reading. **Not established, and not a
  P&L.**
- **(B)** Authorise the one billed Anthropic call for the Scout refusal
  fixture? Not covered by the standing combo-lookup authorisation. **Still
  unanswered.**

---

## 2026-09-08 (third session) — the fat was cut: CLAUDE.md is 20KB, six agents are gone, four task files are archived, seven lessons deduplicated

**STATE at close.** Committed on `main`, **not pushed** — CI has not run on
it. The six test files that read `CLAUDE.md` or pin its figures passed
locally (373 tests); the full suite was still running when Joe asked for a
fresh session, so **the first thing this commit needs is a green CI run**.
Live is unchanged (`789b86a`, nothing here touches the box). ADR 0116 is the
record; `docs/history/claude-md-2026-09-08.md` is the old spine verbatim.

**What moved, so nothing here surprises you:**

- `CLAUDE.md` 44KB → 20KB: rules and facts only, five sections where one
  26KB section was. Three stale `file:line` citations fixed; the "read
  surface" paragraph now says the first two fills went through the tool.
- Deleted: `.claude/agents/{graphic-designer,ui-designer,ux-designer,retail-bettor,tilt-prone-gambler,disciplined-gambler}.md`.
  Six project agents remain.
- Archived: `tasks/todo.md`, `PHONE.md`, both `*prompt*.md` → `tasks/archive/`.
  Session start reads this file then `tasks/lessons.md`; `todo.md` is no
  longer a read.
- This file: the split log left the header (`archive/next-split-log.md`),
  the three closed 2026-09-07/08 entries left (`archive/next-2026-09-08-second.md`,
  md5-verified), and the SESSION START box says `/wayfinder` is not installed.
- `tasks/lessons.md` 109KB → 96KB: preamble to three rules, seven duplicate
  lessons to `archive/lessons-2026-09-08-dedup.md`, one lesson added.
- `kalshi-api` SKILL.md: Fees section now states ADR 0028; `.agents/` mirror
  and the `.codex` toml path fixed.

### Still open, in order

1. ~~**Push and read CI.**~~ **DONE 2026-09-09.** Pushed `25ad5fb..6348a42`;
   CI run `34307087087` on `6348a42` completed **success**. The cut is
   verified and needs no fix-forward.
2. Everything in the entry below is unchanged and still the live brief; its
   `Still open` list is the queue. Item 1 there (the odds-path freeze to
   2026-09-14) is the one with a date on it.
3. ~~**Effort dial for subagents.**~~ **DONE 2026-09-09.** The key is `effort`
   in `.claude/agents/*.md`. All six carry one, `lookup-scout` is new, and
   `tests/test_agent_definitions_parse.py` guards the frontmatter. See the
   2026-09-09 entry — and note the answer to "set it low on the read-only
   agents" was **no**: none of the six is lookup-shaped.
4. ~~Not decided (ADR 0116 §what this does not decide).~~ **ALL THREE
   DECIDED 2026-09-09**, in the entry above: the index does not split, the six
   audit items are down to two live ones, and the ADR/measurement sediment
   sweep is dropped with its reasoning recorded.

**Joe-gated: nothing.**

---

## 2026-09-08 (second session) — the table took its first two rows, the brake Joe removed was still on the button, and the bid path is disarmed

**STATE at close.** `main` = **`789b86a`**, pushed. **Live is on `789b86a`**,
machine `7812601a239428` **unchanged** across every deploy today — check that
after any deploy, because a new machine gets an empty volume and every credit
fact inverts silently. Re-read `/api/health` rather than believing this table.

    live     789b86a verified 23:0xZ; recorder writing; mode live
    demo     cc8de80 deliberately behind, untouched today

**The live verification is now a READING, not an inference** — new this
session and the reason it matters is in ADR 0115. `/api/health` reports
`order_paths_dry_run` for all three money doors, so "is it armed on the box?"
no longer means reasoning about what a deployed sha contained:

    manual_orders   false   ARMED  — he pays the ask
    combo_bids      true    DRY    — disarmed on his word, ADR 0115
    engine_orders   true    DRY    — always has been

The field was **absent** on the previous build, so its presence is itself
proof the new image is serving rather than a cached answer. Use that trick on
any future switch.

Six commits landed and **all six are deployed**:

| sha | what |
|---|---|
| `ebbb809` | the exposure ceiling comes off the hand-bet path (ADR 0112 Amd 1) |
| `68cabc4` | the buy button agrees with the route (ADR 0114) |
| `272f328` | the `source` steer removed from seven surfaces (P2) |
| `a13e6b8` | four ADRs corrected; the depth guard now reads `docs/adr/` |
| `ac016fe` | the bid path's state established; an under-guarding audit retracted |
| `789b86a` | **the bid path is DISARMED** (ADR 0115); the switches reach `/api/health` |

Tree clean at close, no worktrees. Suite **6498 passed / 10 xfailed** as of
`ac016fe`; the last two commits added tests and removed none — **re-run it
rather than quoting this number**, which is the lesson this very session
wrote down.

### THE FINDING: `manual_orders` is no longer empty

Read off the live box with `inspect_live_db.py manual-orders-audit`, which is
structure-and-counts only by design:

    n_rows 2   real_orders 2   dry_runs 0   with_kalshi_order_id 2
    distinct_tickers 2         status: filled 2
    19:41:07Z and 19:42:07Z, 2026-09-08
    3 contracts and 4 contracts
    both KXMVE combinations, both on shard 1
    manual_order_refusals: 0 rows

**The table had never held a row of any kind in the 14 days it was armed.**
NEXT.md's previous entry named this as the thing that would be genuinely new,
and it happened within hours of ADR 0112 removing the four brakes and check 9a
naming the shard. **Item 2 of the previous Open list is struck.**

**ADR 0113's inference fired as written.** It replaced "he does not want to
transact here" with "the door had something wrong with it", and predicted that
fixing the door was what to try. Two fills and zero refusals, the same evening.
**Do not over-read it**: `n = 2`, one sitting, one evening. It is a census
count, not a test, and needs none — the interesting property is that the
number stopped being zero, which is a fact about the door and not an estimate
of anything.

**Both are on shard 1, which is the funded pocket** ($22.24 against $0.00 on
shard 0). So he bet the path his money was already in, which is exactly what
check 9a exists to tell him. **Whether to fund shard 0 is still Joe-gated and
still unanswered** — and note it is now a real constraint rather than a
hypothetical: singles remain unbuyable until he moves money.

### The brake he removed was still on the buy button

Found while checking whether ADR 0112's "no ceiling of ours bounds a hand bet"
was actually true on the deployed box. It was true of the route and **false of
the screen.**

`GET /api/manual/market/{ticker}` served `authorised_contracts` from
`min($3.00 spend cap, 10% of the observed balance)` — both removed by name —
and `ManualTicket.tsx` disables Confirm above that number. **On a 90c market it
authorised 3 contracts against a route that would take 250.**

Three consequences from the one root, and the second is the ugly one:

1. Two 422s on the money path said *"what bounds the BET is the $3.00 spend
   cap, checked below."* Nothing was checked below.
2. `authorised_contracts` was `None` when the balance had never been observed
   — rendered as a refusal. **`ebbb809` made POST accept that state, so this
   session's own earlier commit WIDENED the mismatch** it was part of closing.
3. The ticket called every bound *"your per-bet cap"*, by then the one thing
   none of them was.

**This is the repo's named failure a fourth time — one predicate with two
spellings — and the first time it ran this direction.** The three earlier
instances were a screen promising buying that was not happening. This one
refused betting that was permitted, on the only path that spends real money.

Fixed: the count is now the structural ceiling, the depth at the ask and what
the market's shard can pay for — the three bounds the POST route applies to
size, so the two agree by construction rather than by hand. `authorised_binding`
is new on the wire and the ticket says which one bit, in plain words, because
waiting for the book and moving money between shards are different remedies.
`ADR 0114`; take the ordinal in the merge
commit after `git fetch`.

**Two tests had preserved the error rather than catching it** — one asserted
`"spend cap"` PRESENT in the combination refusal, one asserted `"your per-bet
cap, not your typed amount"` present in the ticket. Both green every day the
copy was false; the same shape `backend/parlays.py:105-111` records about
`"40 of 40"`. Both re-pointed to pin the dead phrase absent, neither deleted.
Verified by disabling: restoring the old bound turns 5 of the 7 new tests red.

### Still open, in order

**Read the numbers here as dated, not current.** Every negative or numeric
claim below either carries the command that produced it or should be re-run
before it is believed — this session wrote that lesson after finding two
stale ones in the previous entry's list, and the list is not exempt from its
own rule.

1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Unchanged, and
   nothing this session went near it. Frozen surface:
   `backend/odds/{timing,budget,attention,ondemand,client,sweeplog}.py`. After
   10:00Z on 09-14: `credits-day --date 20260913`, `sweep-log`,
   `visit-freshness`, and split the mechanisms off `odds_sweep_log.detail`,
   **NOT** `api_credits.trigger`. A deploy is not contamination; logic changes
   are.
2. ~~`RecordParlay.tsx` defaults `source`.~~ **DONE, same session.** No
   default, not a flipped one: the initial state is `""`, `<option value="">
   Choose one</option>` is selectable rather than merely initial, the submit
   button is disabled without a choice AND `submit` refuses one (a form can be
   sent from the keyboard, and `""` reaches the server as a 422 he cannot act
   on). `ParlayCards.tsx` no longer hard-codes the value and its copy no
   longer calls a book slip the first-class path. **Precondition P2 is met**,
   and the window it gates is open — timestamp below, not "at this deploy",
   because by the time anyone reads this there will have been several.
   **The "no frontend test framework" risk was real and is now covered** —
   `tests/test_recording_a_bet_is_reachable.py` reads the source text, and one
   of its existing assertions had been *requiring* the steer (`assert 'source:
   "sportsbook"' in source`). Four guards now, all verified red by restoring
   the steer.
   **THE CLEAN WINDOW IS OPEN. It opened `2026-09-08T21:33:05Z`** — looked up
   from deploy run `34281066870`, per P4, and recorded in the registration's
   Appendix A with the machine id beside it. **Do not census before P1 and P3
   also hold**: P1 needs an accepted ADR recording the entry design (ADR 0113
   is the correction that motivated P1, not the design document it asks for)
   and P3's denominator script does not exist. Earliest legitimate deletion
   read is `G = 30` sittings after this timestamp, backstop 2026-11-30.
3. ~~The combo entry/exit conflation is still in four ADRs.~~ **DONE, same
   session.** `0073`, `0070` and `0075` (two places) carry correction notes
   quoting what they replaced; **none of their decisions moved**, because
   every one rested on the EXIT claim and only the entry reasoning was wrong.
   `0078` got an amendment saying it was audited and *survives* — its
   sentence named entry and exit separately and got both right — recorded so
   the next session does not re-audit it.
   **The guard now reads the decisions, not just the code.** `PINNED` globs
   `docs/adr/*.md`, so a new ADR is covered the day it is written, and
   `FORBIDDEN` gained the conflation itself (`"it is rarely live"`,
   `"3 of 20 and 3 of 9"`) — previously only the depth figure was guarded, so
   the half that reached a screen was unguarded. 132 tests. Both verified by
   planting the claim in an unmarked ADR.
   **One limitation found and written into the guard rather than left to be
   discovered:** a correction note's strike marker shields its own paragraph,
   so the one place a struck claim can quietly return is beside its own
   correction. Re-inserting the depth phrase into ADR 0070's corrected
   paragraph left the suite green. That is the accepted cost of keeping wrong
   text verbatim; narrowing the window already failed on CLAUDE.md's real
   shape.
4. ~~`FiveStepTest.tsx` names the retired Log tab.~~ **DONE, same session.**
   Now: *"Find the market from Games, open its buy ticket, and type your
   P(YES) before you look at the price"* — which is the path that exists, and
   the ticket really does mask the ask until the estimate is typed. The
   sentence about a form asking whether he had already opened Kalshi went with
   it: no such question exists. `ManualTicket.tsx:274` handles the anchored
   case by SAYING the number is anchored and recording it anyway.
5. **`window_status` cannot predict a bootstrap** — FROZEN until 09-14
   (`timing.py:1536`).
6. **The `eu` lever, 2026-09-28** — ADR 0110's measurements first; three of the
   four are free and takeable now. **Its `exchange_index` deferral is closed,
   2026-09-08.** That section named its own overturning condition — *"if the
   manual route is ever used on a non-zero shard, this section is where the
   work starts"* — and the condition fired: both of tonight's first-ever
   `manual_orders` rows are on **shard 1**. Two of its three killing facts are
   spent (the "0 of 27 real bets" is the stale-negative shape; the 420-market
   `exchange_index: 0` capture was of NFL SINGLES when the reachable case was
   always combinations), and the work was built independently hours earlier as
   check 9a. The ADR carries the correction. **Nothing to build; the `eu`
   decision itself is untouched and still dated.**
7. **Scout Anthropic refusal fixture (ADR 0106 §5.2)** — one billed call. NOT
   dead code: `routers/scout.py:25` imports `agents.scout_desk`.
8. **`combo_orders` — CLOSED. He said "disarm the bid path" and it is
   disarmed (ADR 0115).** The findings that produced the question are kept
   below because the reasoning behind a disarm is what a re-arm has to answer:

   - **Nothing is resting.** All five bids `combo_orders` has ever held are
     terminal: four `cancelled` ("the first leg has started"), one
     `gone_at_venue` (id 2, placed 09-01, resolved 09-07 — the venue had no
     order by that id, so it filled, was cancelled or settled; the desk does
     not know which and cannot without account data). **The previous entry's
     "a pre-09-06 bid may still rest" is resolved: none does.**
   - **Zero UI callers, confirmed.** No `.tsx` imports `placeComboBid`,
     `cancelComboBid` or `listComboBids`. The `api.ts` helpers, the
     `/parlay-bid` proxy route and its middleware entry all still exist.
   - **It is armed**: `COMBO_ORDERS_ARE_DRY_RUNS = False` since 2026-08-30,
     on Joe's own words *"the exchange is done. arm the switch."*
   - **It is NOT under-guarded, and an audit that said so was wrong.** The
     route has no `is_demo` check of its own, which looked like CLAUDE.md's
     "one config bug from the order path". It is not: `require_auth` refuses
     on `is_demo` before reading a token and the route depends on it. The
     arming discipline is *equivalent* to the hand-bet path's — mode plus a
     deliberate switch — the switch just being a constant rather than an env
     var, which `combo_orders.py` argues for in its own words. **A guard was
     written for this and reverted.** What survives is
     `TestTheDemoCannotRestABid`, which pins the property on the endpoint that
     spends money rather than only on `require_auth`'s own test; verified red
     by deleting the demo branch.

   **The question that was put to him, and his answer.** This
   endpoint exists to REST OFFERS, and on 2026-09-06 he asked for the
   offer-making controls to be removed — *"I don't want to make offers or find
   offers in shares"* — a ruling CLAUDE.md records as **still standing** as of
   2026-09-08. The UI was removed; the armed real-money endpoint was not.
   Three options were put to him — disarm, delete, or leave armed — and he
   chose **disarm**. Done, one line, in a commit of its own, the procedure the
   constant's own comment specified. The switch's interlock test went red on
   the flip exactly as it was written to, and the acknowledgement is in its
   docstring.
   `COMBO_ORDER_MAX_SPEND_TENTHS` ($3.00) is deliberately **not** touched: it
   binds nothing while the path is dry, and it is the ceiling that would apply
   on re-arming. Raising it while nobody is watching is how a removed cap
   comes back by accident.
9. **The decision map's third queue is two items, not nine.** A full audit of
   all 32 closed tickets against the tree finds 23 built, 7 decided as "no
   build", 2 genuine gaps — one of which is item 4 above. The "~9" was carried
   forward without re-measuring.

### What a next session should actually pick up

**Most of the list above is now frozen or closed, so read this before
planning.** Items 2, 3, 4 and 8 closed this session; 1 and 5 are frozen until
10:00Z on 2026-09-14 and must not be touched before then; 6 needs no build;
9 is exhausted. That leaves, in order:

1. **Nothing, deliberately, until 09-14** if the odds work is what you would
   have reached for. Sunday 09-13 is the only attended NFL Sunday this month
   and the freeze is what makes it a measurement.
2. **Item 7**, the Scout Anthropic refusal fixture — one **billed** call, so
   it needs Joe's yes under [[approved-actions]]; it is not covered by the
   standing combo-lookup authorisation.
3. **The first `manual_orders` census is NOT due.** Two rows on one evening is
   the finding; a third row is not a new one. ADR 0113 §6 forbids reading a
   count here without first showing the path was usable across the whole
   window, and the window is two days old.
4. **If nothing above applies, ask the partner rather than inventing work.**
   The backlog is genuinely short right now, and that is a fact about the
   project rather than a gap to fill.

**Joe-gated, two questions, both stated fully in the items above:**

- **(A)** Fund shard 0 so single-market bets work? Shard 1 (Combos) holds the
  money; shard 0 (Default) is at $0.00, so every single-market bet dies at the
  venue. Check 9a now names the pocket and the reallocation link rather than
  letting it read as a broken cockpit.
- ~~**(B)** `POST /api/parlays/bid`.~~ **ANSWERED: *"disarm the bid path."***
  `COMBO_ORDERS_ARE_DRY_RUNS = True`, ADR 0115. The route, table, watcher and
  cancel path all STAY — a dry run still writes the row and still says
  "Nothing was sent to the exchange" — and **deleting it was one of the three
  options and is not what he chose.** Do not finish the job by removing it as
  dead code.

### The pattern worth carrying (goes to `tasks/lessons.md`)

The previous entry's Open list had **two** items stale in the same way. Item 2
said "there is not one yet" about a thing that happened an hour later; item 9
said "~9 live items" about a queue drained to two. Neither was wrong when
first written; both were copied into a new entry without being re-read off the
instrument.

**A count or a "not yet" copied forward into a new session entry is an
assertion about the present tense made from a past reading.** This file already
learned it about lane tables — *"a hand-typed lane state asserts the present
tense and starts rotting the second it is saved"* — and the Open list was
exempt by nothing but habit. Every numeric or negative claim in a `Still open`
list should carry the command that produced it, or be re-run when the entry is
written.

---

# The session index

Every session entry ever written to this file, newest date first. Full text in
the linked archive file, unchanged.

### Split 2026-09-08 (second) — [`archive/next-2026-09-08-second.md`](archive/next-2026-09-08-second.md)

Taken for readability rather than size (ADR 0116): the three closed
entries from 2026-09-07 and the first 2026-09-08 session, each carrying a
`Still open` list the entry that stayed supersedes. Verified by md5
(`e8c041c54a1b0d17bb8b54908c8204d7`).

- 2026-09-08 — Joe corrected what the desk is FOR at the moment of a bet, and the four things stopping him turned out to be ours
- 2026-09-07 (second session) — tonight's check had no instrument on the box and the wrong reading written down; attention was paying a live-game cadence for a line two days out
- 2026-09-07 (earlier session) — the NFL path is pre-flighted and its first sweep is due tonight by construction; a failed look and a spent day get their own words; the watcher stops asking the venue about a bid that filled

### Split 2026-09-08 — [`archive/next-2026-09-08.md`](archive/next-2026-09-08.md)

Filed by the date of the split. The six 2026-09-06, one 2026-09-05, one
2026-09-04 and two 2026-09-03 entries that were still in `NEXT.md` when it
reached 205,381 bytes, 78.3% of the ceiling. Taken **under** the trigger
rather than at it, at Joe's instruction, before a fresh session started —
and cut deep, to 22.3%, so the next several sessions need not think about
it. The cut falls on a date boundary: everything 2026-09-06 and earlier
moved, and no single day is split across two files. Verified by md5: the
archived bytes below its header hash identically to the bytes removed
(`823e72d9643035f974168e24d26b440c`).

- 2026-09-06 (sixth entry) — the published credit bound was a partial sum, item 3 was half-false, and the largest NFL day-one risk is a failure nobody had timed
- 2026-09-06 (fifth entry) — the parlay window became a control, the in-play combo question is answered, and props are a feed problem rather than a venue one
- 2026-09-06 (fourth entry) — Joe took the offer-making controls off the desk, and what replaces them is a record of a bet placed somewhere else
- 2026-09-06 (third entry) — the partner ran first and its top item was not on the list; the credit answer was refused once before it was kept; three lanes landed and the inspector stopped blocking work
- 2026-09-06 (second entry) — Joe answered the four open questions; the combo note now carries BOTH censuses, ADR 0085 has Amendment 1, PRs #1/#2 are closed, and the shard-3 test and the key rotation are DROPPED on his word
- 2026-09-06 — the parlay census is TAKEN and ADR 0085 is REFUTED at the moment Joe buys; #24, Lane A2, the money-arm predicate, the agent wire fixture and Joe's four answers are all deployed; the inspector blocks work at 99.3%
- 2026-09-05 — the session Joe stopped is picked up: three finished lanes merged (ADR 0106, 0107, the routes split), and the one cross-lane break git could not see
- 2026-09-04 — six lanes landed (ADR 0104, 0102 Amd 1, the Read-ceiling guard); the presence measurement was registered, taken once, audited, and is UNRESOLVED — CONCENTRATION; the partner killed #11's log form; five questions for Joe
- 2026-09-03 (second entry) — the partner found the desk had not gone quiet and the /picks heal was switched off; three lanes landed (ADR 0101–0103); one question and one rotation for Joe
- 2026-09-03 (early) — the partner reordered the queue around a regression shipped the day before; three lanes landed; Joe answered the second batch

### Split 2026-09-06 — [`archive/next-2026-09-06.md`](archive/next-2026-09-06.md)

Filed by the date of the split. The three 2026-09-02, two 2026-09-01 and four
2026-08-31 entries that were still in `NEXT.md` when it reached 223,790 bytes,
85.4% of the ceiling. Taken before the session's entry was added rather than
after, and cut deeper than the trigger required so the cut falls on a date
boundary: everything 2026-09-02 and earlier moved, and no single day is split
across two files.

- 2026-09-02 — the partner ran first; P5 is terminated, #6 is built, and the desk went quiet
- 2026-09-02 — one deploy became nine commits, because the instrument was never on the box and then was wrong
- 2026-09-02 — four lanes landed, the volume had 16 days left, and a wizard died of the defect it was written to prevent
- 2026-09-01 — the lock holder is attributed, the partner had never been invoked, ticket #11 is resolved, and a $100 money stop turns out to be unable to fire
- 2026-09-01 — open item 4 named an instrument that cannot see the failure it measures, and the good news I wrote off it was refused
- 2026-08-31 — the sweet spot reaches all three surfaces, and a second opinion convicted a four-month-old number
- 2026-08-31 — the lock holder was found, and a wording rule lost to typography
- 2026-08-31 — the sweet spot, and the graph Joe asked for
- 2026-08-31 — the Scout reaches the parlay legs, and the budget says it can only flag them

### Split 2026-09-05 — [`archive/next-2026-09-05.md`](archive/next-2026-09-05.md)

Filed by the date of the split. The five 2026-08-30 and two 2026-08-29
entries that were still in `NEXT.md` when it reached 224,305 bytes, 85.6% of
the ceiling. Taken before this session's entry was added rather than after.

- 2026-08-30 — the deadline the screen promised had never once been kept
- 2026-08-30 — the desk placed its first real order, and the venue has no one to fill it
- 2026-08-30 — the WAL read was taken, it could not run, and the memory level halved
- 2026-08-30 — the positions payload was observed, a refusal became a record, and two lanes closed two backlog items
- 2026-08-30 — the hour-long silences are a poisoned connection, and the ticket takes dollars
- 2026-08-29 — the signal test could never have answered its own question, and twelve lanes landed
- 2026-08-29 — THE READ WAS TAKEN, and every gap turns out to be a container death

### Split 2026-09-01 — [`archive/next-2026-09-01.md`](archive/next-2026-09-01.md)

Filed by the date of the split. The seven 2026-08-28 entries that were
still in `NEXT.md` when it reached 85.6% of the ceiling. Taken before
the session's entry was added rather than after.

- 2026-08-28 — the read was attempted a second time, the window survived, and it is 8 minutes old
- 2026-08-28 — the pre-registered read was taken, and it was not a read
- 2026-08-28 — PRE-REGISTRATION: how to read tomorrow's gap, decided before the data exists
- 2026-08-28 — the unexplained gap was the sixteenth, and nothing on disk could have said so
- 2026-08-28 — a leg priced at zero stopped the alerting half of the loop, and the heartbeat fired for a DIFFERENT reason
- 2026-08-28 — one tab could take the site down, and the desk went quiet without saying so
- 2026-08-28 — the palette split shipped, and the guard watching it was measuring the wrong pair

### Split 2026-08-31 — [`archive/next-2026-08-31.md`](archive/next-2026-08-31.md)

Filed by the date of the split. The 2026-08-28 and 2026-08-27 entries that
were still in `NEXT.md` when it reached 87.3% of the ceiling. Taken before
the session's entry was added rather than after.

- 2026-08-27 — the map got three rulings and a colour, and this file learned the map exists
- 2026-08-27 — the alarm that watches for a silent death had been taught to fire every day, and the combo tests were all in the wrong branch
- 2026-08-27 — two lanes can be seen at once, and the tool that saw them told a human to delete sixteen projects
- 2026-08-27 — a cold open buys odds on the pass it woke
- 2026-08-27 — the parlay push stops being a race and becomes a schedule

### Split 2026-08-29 — [`archive/next-2026-08-29.md`](archive/next-2026-08-29.md)

Filed by the date of the split. The 2026-08-26 and 2026-08-25 entries that were
still in `NEXT.md` when it reached 86% of the readable-size ceiling. Taken at
86% rather than 98.9%, on the rule the previous split wrote.

- 2026-08-26 — three commits had no entry, and one of them raised the bet
- 2026-08-26 — the live box was OFF between visits, and five commits later the desk draws pictures
- 2026-08-26 (hedging lane) — the desk starts watching what Joe already holds, and a hedge turns out to need no model at all
- 2026-08-26 — the buy control reaches every card, and the ticket renders on a real book for the first time
- 2026-08-26 — one parlay generator becomes six, and the notifier is deliberately left behind
- 2026-08-26 — the alarm stops guessing, and the desk's cards reach the phone
- 2026-08-25 — the desk was empty because the loop was ASLEEP, and nothing could wake it
- 2026-08-25 (later) — the odds feed stops watching the clock and starts watching whether anyone is there
- 2026-08-25 — the declaring look is REFUSED, and §P4 turns out to have been an opt-in nobody opted into

### Split 2026-08-27 — [`archive/next-2026-08-27.md`](archive/next-2026-08-27.md)

Filed by the date of the split. The 2026-08-24 through 2026-08-20 entries
that were still in `NEXT.md` when it reached 98.9% of the readable-size
ceiling.

- 2026-08-24 (fifth session, close) — SUPERSEDED by the entry above: the screen's declaration did not survive audit
- 2026-08-24 (fifth session) — the purpose gets settled, and the feed is told to follow attention
- 2026-08-24 (fourth session) — the parlay desk earns a nav slot and every game names its sport
- 2026-08-24 (third session) — the desk is used for real, and a combo book is populated for the first time ever
- 2026-08-24 (second session) — all 14 review findings fixed, and the repeat tap turns out to be idempotent
- 2026-08-24 — code review of the parlay-desk session: 14 findings (ALL FIXED — see the entry above)
- 2026-08-23 (third session) — the parlay desk: three cards at fair value, spreads priced, and the combo's real cost one tap away
- 2026-08-23 (second session) — the desk presents fully: likely winners on the slate, five areas per game, Willy's seat
- 2026-08-23 — the desk window opens: the slate stops being stale 14 hours a day
- 2026-08-22 (third session) — the pass gets its caller, the probe gets cheap to start, and stale odds get an exit
- 2026-08-22 (second session) — the every-page review ships whole: kill list, glossary, real limits, and a manual door built dry
- 2026-08-22 ~13:15Z — the betting-desk list closes out: CLV on his own bets, then the ticket cleanup
- 2026-08-21 ~23:30Z — the landing screen stops claiming an edge, and the session hands off
- 2026-08-21 ~22:45Z — the refusal lands on real data, and the lockout gets the desk's name
- 2026-08-21 ~21:45Z — /bets ships, and the partner re-rules the refusal work by name
- 2026-08-21 ~20:30Z — the desk gets a token meter and a nav slot in one change, and the gold goes out
- 2026-08-21 ~18:30Z — Joe rules the purpose, the Skeptic retires, and the cost record gets honest
- 2026-08-21 ~16:45Z — the market screen joins the shell, and the desk scales to a real instrument panel
- 2026-08-21 ~15:30Z — the briefing becomes a cockpit, and the market screen serves the venue's facts
- 2026-08-21 ~06:30Z — the Scout desk is switched on, on Joe's word: a staff of two and a master, metered
- 2026-08-21 ~04:30Z — the replay gate passes exactly, and the ledger's null kickoff is fixed
- 2026-08-21 ~03:15Z — the H4 series closes on a measured reason: the channel diagnostic is BLIND on a denominator of 1
- 2026-08-21 ~02:00Z — h4-balance-spans ships with its guards red, and both deploys landed
- 2026-08-21 ~00:20Z — H4 Look 1 is taken and moves nothing, tomorrow's terminal spread look is armed, and one deploy waits on Joe
- 2026-08-20 ~21:35Z — the spread test is TAKEN: UNDERPOWERED both arms, and the partner's list is the open work
- 2026-08-20 ~19:45Z — the dropouts are diagnosed, the zero is verified, and the spread test is armed for 21:21Z
- 2026-08-20 ~17:00Z — the gate is measured, the product has a plan, and a slice is built but NOT deployed

### Split 2026-08-25 — [`archive/next-2026-08-25.md`](archive/next-2026-08-25.md)

Filed by the date of the split rather than of the entries, like the 08-18 file
below it: these are the 2026-08-19 and 2026-08-17 entries that were still in
`NEXT.md` when it reached 93% of the readable-size ceiling.

- 2026-08-19 ~23:20Z-00:30Z — THE FIXES HELD FOR 2H40M, NOT 12 HOURS; AND THE UNMATCHED QUEUE'S OBVIOUS FIX WAS AN OUTAGE
- 2026-08-19 ~16:20Z — THE 15:21Z TEST WAS TAKEN; THE STORE LEG IS INNOCENT, AND THE FLAPPING WAS NEVER THE BACKEND
- 2026-08-19 ~12:15Z — ADR 0053 HALF-HELD; THE COST MOVED TO THE STORE LEG, AND I GUESSED WRONG ABOUT IT FIRST
- 2026-08-19 ~02:30Z — LIVE HAS BEEN FLAPPING ALL DAY, I SAID IT WAS HEALTHY, AND THE CAUSE IS THE QUOTE PASS
- 2026-08-19 ~late — THE STRIP IS ON THE PHONE, BY JOE'S CALL
- 2026-08-19 ~mid — THE STRIP SAYS WHERE THE NUMBER CAME FROM, AND THE DEMO WAS DISAGREEING WITH ITSELF
- 2026-08-19 ~early — THE ALARM WAS WATCHED, AND THE CODES SPEAK ENGLISH ON FOUR SCREENS
- 2026-08-17 21:55Z — THE MEASUREMENT IS NOT DUE YET, AND THAT IS THE WHOLE SESSION
- 2026-08-17 — JOE'S THREE ITEMS, AND THE LANE THAT WAS BRIEFED WAS THE ONE THAT DID NOT EXIST
- 2026-08-17 — THE MORNING WARNING WAS ARITHMETIC, AND IT IS GONE FROM THE LIVE SCREEN
- 2026-08-17 — THE INSTRUMENTS NOW DISAGREE WITH THE MACHINE OUT LOUD
- 2026-08-17 — THE PRODUCT NOW STATES WHAT ITS CONCLUSION IS WORTH

### 2026-08-18 — [`archive/next-2026-08-18.md`](archive/next-2026-08-18.md)

- 2026-08-18 ~night — THE ALERTS LEAVE THE PHONE, AND THE FAILURE CHANNEL IS WIRED
- 2026-08-18 ~evening — THE DESKTOP TIER EXISTS, AND THE GREEN-ZERO DEFECT DIED FIRST
- 2026-08-18 ~16:30Z — THE TRIAGE IS DISCHARGED: THE STOP HAS A READER, THE BANKROLL IS DERIVED, AND THE COMBO FEES GOT THEIR REGISTERED LOOK
- 2026-08-18 11:10Z — THE STUDY IS OPEN, THE MACHINE MATCHES ITS COMMIT, AND THE PARTNER HAS SET THE ORDER
- 2026-08-18 08:50Z — THE ENTRY FORM EXISTS, AND THE DATABASE ITSELF NOW REFUSES TO EDIT AN ESTIMATE
- 2026-08-18 08:30Z — THE POLLER IS LIVE, AND JOE'S OWN RECORD IS NOW MIRRORED WHERE KALSHI CANNOT DELETE IT
- 2026-08-18 00:30Z — THE PUBLIC DEMO OVERSTATES SIZE BY 17x, AND THE ADR THAT CLOSED THAT HOLE CANNOT SEE IT

### 2026-08-17 — [`archive/next-2026-08-17.md`](archive/next-2026-08-17.md)

- 2026-08-17 (latest) — THE PRODUCT NOW STATES WHAT ITS CONCLUSION IS WORTH
- 2026-08-17 (later) — THE SCREEN WAS A VERSION BEHIND THE RECORD
- THE HUNT IS CLOSED. ADR 0038. READ THIS FIRST.
- THE WHOLE PROP-MODEL LINE IS CLOSED. ADR 0037.
- PITCHER-K IS REFUTED. THE MODEL WORKS; THE PARAMETERS CANNOT.
- 2026-08-17 (~00:30Z) — P1 WAS READING THE WRONG STATISTIC. NFL IS A SKIP. MLB PROPS REORDER TO PITCHER-K.

### 2026-08-16 — [`archive/next-2026-08-16.md`](archive/next-2026-08-16.md)

- 2026-08-16 (~22:40Z) — BETA IS MEASURED AND NEGATIVE. WE ARE OFF THE GATE. BUILD AN OPINION.
- 2026-08-16 (~21:05Z) — LIVE WENT DOWN FOR 54 MIN (VOLUME FULL). FIXED. AND THE FEE IS 2x TOO HIGH.
- 2026-08-16 (~19:20Z) — ⚠ `actionable` IS NO LONGER 0. AUDIT IT BEFORE ANYTHING ELSE.
- 2026-08-16 (~19:30Z) — PROPS ARE OFF THE SCHEDULE. THE FUNNEL IS SPEC'D. ONE DUMP STILL NEEDS A LAPTOP.
- 2026-08-16 (~18:20Z) — THE REFRESH IS DEPLOYED AND FIRING. TWO THINGS STILL NEED JOE'S HANDS.
- 2026-08-16 (~06:30Z) — THE TWO TOP ITEMS ARE UNCHANGED AND STILL WAIT ON THE 16:51Z SLATE
- 2026-08-16 (~03:00Z) — A DEPLOY IS OWED, AND ONE MEASUREMENT IS STILL DUE AT ~17:30Z
- THE CREDIT DEFECT IS FIXED IN THE REPO AND **NOT YET DEPLOYED**. Deploy is the first thing. *(SUPERSEDED: it was deployed and verified ~00:35Z.)*

### 2026-08-15 — [`archive/next-2026-08-15.md`](archive/next-2026-08-15.md)

- PROPS ARE RECORDING ON LIVE. One defect fixed, **one still open and it has a clock**. *(SUPERSEDED by the section above: the credit defect is fixed in the repo, pending deploy.)*
- PROPS ARE BUILT, ALL FOUR SLICES. **SUPERSEDED by the section above — they are now deployed and two defects were found in the first live pass.** Note its credit figures are the ones that turned out wrong.

### 2026-08-14 — [`archive/next-2026-08-14.md`](archive/next-2026-08-14.md)

- PROPS THROUGH THE EXISTING PIPELINE. **SUPERSEDED — all four slices are done; see the section above.** Kept for the constraints it records.
- PROPS ARE CHARGED THE BASEBALL RATE. H-SPORT survived a real falsification test.
- PROPS ARE REACHABLE, AND THE FEE COEFFICIENT IS THE GATE, NOT THE MARKET
- THE FEE HEDGE IS RETIRED. The break-even bar is 51.75%, and one published analysis is now stale.
- ROUND THREE IS RUN. The fee is NOT a venue constant, and the code is wrong on baseball.

### 2026-08-13 — [`archive/next-2026-08-13.md`](archive/next-2026-08-13.md)

- Q-W RAN AND ACTIVATED. Nothing is blocking the orders but Joe's clock.
- Q-W IS BUILT AND COMMITTED (superseded above; kept for the image finding)

### 2026-08-12 — [`archive/next-2026-08-12.md`](archive/next-2026-08-12.md)

- ADR 0020 IS WRITTEN. The reserved number is spent, and it opens nothing.

### 2026-08-11 — [`archive/next-2026-08-11.md`](archive/next-2026-08-11.md)

- THE CEILING ON RELAXING `stale_odds` IS 23 ROWS = 14 OPPORTUNITIES, AND NOTHING BEHIND IT IS A RUNWAY
- OPEN QUESTION FOR JOE: 85.8% of the $3.66 lands in a series with zero rows in the record
- ADR 0025: the `stale_odds` claim was OVERSTATED by ~10x, and its mechanism ran backwards
- ⏱ Time-sensitive, and it is free
- RESOLVED: `capture_odds_repeat_poll.py`'s P1 could not fail. Fixed at `39628e0`.
- The demo instance renders a healthy version of the screen that is empty on live

### 2026-08-10 — [`archive/next-2026-08-10.md`](archive/next-2026-08-10.md)

- `inspect_live_db.py` RUNS NOW, and answers ONE of the four questions it was queued for
- ADR 0021 §7: the dump is refused for the CLV test, and NOT ruled on for the other one
- CORRECTED: ADR 0021 §7.2 asserted something its own source had already refuted
- 2026-08-10 22:34:21Z — THE SWEEP SERVED. The latch is refuted, F4's prediction held.
- RESOLVED: the 21.5-hour odds gap had an empty denominator
- The documented phone health check cannot pass, and never could
- 2026-08-10, overnight — SIX DURABLE FACTS FROM TONIGHT'S LANES
- ⏱ 2026-08-10, evening — RUN THIS FIRST, THEN READ THE REST
- 2026-08-10, overnight — THE REFUTATION IS WRITTEN, AND IT QUOTES A FIXTURE AS A FACT
- ⚠ 2026-08-10 — READ THIS IF YOU ARE A PARALLEL SESSION
- 2026-08-10, end of session — ADR 0019 LANDED, AND THE REPORTED BUG WAS WRONG
- INFRASTRUCTURE INTERRUPT: Actions minutes, and the public flip
- 2026-08-10, end of session — THE BOUND FAILED, AND IT FOUND A REAL BUG
- 2026-08-10, mid-session — JOE: ONE COMMAND (still true; the ADR framing above supersedes)
- THE PLAN: one joint bound, then stop and write the refutation
- the edge test is REGISTERED, and it retracts a claim of mine
- `partner` re-triaged: calibration is the CONTROL for the edge test
- the power-ratings finding is AUDITED, and `no_edge` may be misnamed
- DEPLOYED, D1 is answered, and deploys are now BATCHED
- 2026-08-10, earlier — LIVE READ ACCESS IS UNBLOCKED
- half the documented strategy has never run, and the $5 buys a field name

### 2026-08-09 — [`archive/next-2026-08-09.md`](archive/next-2026-08-09.md)

- 2026-08-09, ~22:40Z — DEPLOYED, and `actionable` has been 0 for the whole record
- 2026-08-09, late — six lanes landed, and three audits refuted the prose over them
- 2026-08-09, ~19:30Z — the bankroll trap is fixed; the backfill cannot open the gate
- CLOSED 2026-08-09 — the 94% is withdrawn, and the replacement died too
- 2026-08-09, ~16:00Z — the gate freeze was an empty slate. DECIDED: accept.
- 2026-08-09, 06:00–09:00Z — five items closed, and one of them was Joe's
- DEPLOYED (2026-08-09, 05:36Z) — the budget stopped being the constraint
- Superseded (2026-08-09) — the 20K tier is bought; the key is not installed
- The gate is blocked by the odds budget, and the guards are fine
- READ FIRST (2026-08-09, later) — the log stream drops lines, and the number everyone quoted was a 10% sample
- READ FIRST (2026-08-09) — the gate's counter cannot grow, and it is arithmetic
- DEPLOYED (2026-08-09, ~03:17Z) — and `clv_scored` left zero
- HANDOFF (2026-08-09, ~00:10Z — the settlement path is built, nothing is deployed)

### 2026-08-08 — [`archive/next-2026-08-08.md`](archive/next-2026-08-08.md)

- HANDOFF (2026-08-08, evening — demo is deployed, live is one tap away)
- HANDOFF (2026-08-08, 14:4xZ — the sheet is merged, and running it found four more)
- HANDOFF (2026-08-08, overnight — three lanes, and CI was already red)
- HANDOFF (2026-08-08, 05:2xZ — deployed, and the demo found the bug for us)
- Joe's asks, 2026-08-08 — four of them; two are done
- HANDOFF (2026-08-08, later still — the price is live, and a review caught me)
- HANDOFF (2026-08-08, earlier — the 30-second window is fixed)
- HANDOFF (2026-08-08, earlier)

### 2026-08-07 — [`archive/next-2026-08-07.md`](archive/next-2026-08-07.md)

- 1. Blocked on you
- 1b. Found by deploying live
- 2. Fix before any real money
- 3. Ready to build (no blockers)
- 4. Verified working
- The honest status
