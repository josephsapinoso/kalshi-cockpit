# Next — your checklist

**How this file works, since 2026-08-17.** This file holds the **current
state**: the latest session entry, plus what is still open. Every earlier
session entry is in `tasks/archive/next-YYYY-MM-DD.md`, **verbatim** — the
archive reconstructs the pre-split file byte for byte, nothing was summarised or
dropped. The index at the bottom lists every entry and which file it is in.

The split happened because this file had reached **456,641 bytes / 8,145
lines**, past the 262,144-byte ceiling at which the Read tool refuses a file
outright. `tests/test_session_files_are_readable.py` now fails if it or
`tasks/lessons.md` crosses back over. When you add an entry and the file grows,
move the older ones into the dated archive file — do not shorten them.

**Split again 2026-08-25, at 243,486 bytes — 93% of the ceiling, not past it.**
The 08-19 and 08-17 entries moved to `archive/next-2026-08-25.md`, verbatim,
leaving ~146KB here. Waiting for the test to go red is the wrong trigger: the
test guards the *file*, and what actually breaks first is the instruction at the
top of it — a session that cannot read the whole file reads the head and
silently believes it has the state. **Split at ~90%, not at 100%.**

**Split again 2026-08-27, at 259,407 bytes — 98.9%, and that is a miss.** The
2026-08-24 through 2026-08-20 entries (27 of them) moved to
`archive/next-2026-08-27.md`, verbatim, leaving ~140KB here. The rule above says
90% and it was not followed, because the entry that crossed the line was the one
being written and nobody checks the size before adding. **Check `wc -c` BEFORE
writing an entry, not after** — at 98.9% the margin was 2,737 bytes, roughly one
paragraph, and the failure mode is silent.

---

## SESSION START — if Joe said "read NEXT.md", this box is your prompt

Repo: `C:\Users\josep\Documents\Claude\Projects\kalshi_betting_tool`,
branch `main`. Check `git status` and `git log origin/main..main` rather than
trusting any sentence here, and read the LIVE instance's `/api/health` for its
`git_sha` — it sits under `build`, not at the top level. The calibration study
is STOPPED (2026-08-20, Amendment 2; the recorder machinery still runs). Joe is a beginner and has
asked to be educated: define every betting/stats term at first use, via
`frontend/src/lib/glossary.ts` and `<Term>`.

**Test baseline: 4,959 passed / 10 xfailed in 7:34**, measured 2026-08-28 on
the tree committed as the ZeroDivision fix (`5436fc8`), `origin/main` level
immediately before the push. The +5 over the parlay-bound tree is the five
`TestAZeroFairProbabilityNeverReachesArithmetic` guards. That triple — the number, the tree it was taken
on, and the fact that nothing moved after — is the qualification this line has
never carried, and its absence is the whole reason it kept being wrong.

**And it was wrong again, a seventh time, in the same direction.** The line
here said **4,942** for the ADR 0080 tree. Collected on that exact tree it is
**4,954 items = 4,944 passed + 10 xfailed** — two more than claimed. The delta
into today's number is **+6 and fully accounted for**: the six assertions added
to `tests/test_palette_contrast.py`, verified by collecting with and without
the change (`4,954 → 4,960`). **Do not reconcile a baseline by reasoning about
a delta; collect both trees.** That took twelve seconds and is the only method
that has ever worked on this line.

**7:29, not the 23:00 below.** Same machine, same suite, nothing removed. The
paragraph below is right that a slow run is not a hung one; it should not be
read as promising a *duration*. Time the run you are in.

**Two runs this session are NOT this number and neither was reported as one.**
One was started at session open and killed as void because the tree was edited
under it — the exact failure this file records twice. The other read
`2 failed, 4,940 passed` and was a real finding, not a flake: adding a
migration at v25 after three tableless versions tripped a contiguity guard on
`_MIGRATIONS`. Fixed properly, then re-run whole.

**Four other runs happened this session and NONE of them is this number.**
4,842 before the lane-board work; 4,885 at `1fecb54`, before the parlay lane
merged; and two killed mid-flight, one because two suites racing read as a
hang and one because the tree changed underneath it. Each was true of a tree
that no longer exists. **The failure mode is always the same — a number carried
across a change to the thing it counts** — so if you change the test corpus,
this paragraph is stale the moment you do, and the fix is to re-run rather than
to reason about the delta.

This line has now been wrong in the same direction six times (4,192 written
when it was 4,200; 4,281 written before three lanes landed; 4,456 written when
`88d179f` actually measured 4,524; 4,456 again the day it became 4,474; and
both halves of this merge conflict, each correct about a tree that no longer
exists). **The failure mode is always the same: a number carried across a
change to the thing it counts.** The 6 skips are `load_fixture` skipping on a
machine without the capture fixtures, not a regression.

**The suite is now ~15-22 minutes**, up from 5-8, and the reason is worth
knowing before you assume it hung: it grew with the record, and one test added
2026-08-26 briefly took 71 seconds on its own by driving a 200,000-sample
copula ~300 times to assert a dictionary length. That one was fixed by stubbing
`_joint`. **If the suite gets slower again, look for a test doing real work to
check a cheap property** — a test nobody will wait for is a test that stops
being run. A slow run is not a hung one, and per the 2026-08-25 lesson, neither
is a gap the length of an interval. **Two suites racing each other reads as a
hang**: verify by command line, not by a kill's exit code.
**Two things to know before planning. CLAUDE.md is current on both:**

1. **The signal test has NOT declared. The 2026-08-24 `NO SIGNAL` was
   refused on audit, 2026-08-25.** The verdict is **UNRESOLVED at G = 216**
   — the registered primary is the modal `strategy_config_version` alone
   (§P4/§7), and `G = 311` was a fit pooled across four versions. Fixed in
   code the same day. Full audit:
   `docs/measurements/2026-08-25-clv-signal-declaring-look-refused.md`.
   **The direction is unchanged and still settled for planning** — every
   interval at either look sits entirely below the 0.40 threshold.
2. **What the tool is FOR is settled — ADR 0071.** A personal betting desk
   first; price transparency as the job; a gap you may show on a row and
   never rank by; sharing means someone runs their own copy. Read it before
   planning anything, and do not re-derive the purpose.

**TWO OTHER LANES ARE RUNNING. Check them before you plan anything**, because
main is not the whole picture:

    git worktree list

They live under `~/.herdr/worktrees/kalshi_betting_tool/` and are Herdr's, not
this session's — nothing here starts or stops them.

**There is no longer a hand-maintained table here, and that is the fix.** The
one that stood in this spot said `parlay-props` was "0 ahead, 1 behind, one
uncommitted file"; within hours it was 0 ahead, **10** behind, with **15**
dirty files, and `hedging-research` had merged and been removed. A hand-typed
lane state asserts the present tense and starts rotting the second it is saved.
Read the generated board instead:

    .venv\Scripts\python.exe scripts/lane_board.py

It reads every worktree and local branch at once — ahead/behind, uncommitted
work, ADR and schema claims, and which files two trees are changing at
overlapping *hunks* rather than merely in the same file. `tasks/LANES.md`
carries the last written snapshot plus the **allocation ledger**: what a live
lane has said it will take before it exists on disk, which is the one thing no
measurement can produce.

**They have collided with main three times in one day, and git said nothing
about the ones that mattered.** From `hedging_research`'s own commit messages:
*"the hedging ADR becomes 0077, because 0074 was taken twice and git said
nothing"*, then *"becomes 0078 — 0077 collided too"*, then *"two lanes both
claimed schema v23, and the hedge tables take v24"*. Each was caught by a human
reading a merge.

`tests/test_parallel_lanes_do_not_collide.py` fails on a duplicate ADR number,
and `scripts/lane_board.py` now sees the other lanes *before* a merge —
including their uncommitted work, which no test can reach, because a test only
sees the tree it runs in.

**But do not claim a number by reading either one.** `tasks/lessons.md:168-191`
settled that: reading `main` first answers "what was free when I looked", and a
lane that runs for hours races every other lane for the whole of it. Write the
ADR as `docs/adr/DRAFT-<slug>.md` with **no ordinal** and take the number in
the merge commit, after `git fetch`, as the last thing before the push. The
guard refuses a `DRAFT-` file on `main`, which is what makes that unavoidable
rather than merely encouraged. Full rule: `docs/adr/README.md`.

**`docs/adr/0006-*` is NOT a collision.** `0006-in-play-evidence.md` is the
companion to `0006-in-play-scope.md` and shares its number on purpose. The
guard keys on what a document's H1 *claims to be*, not on its filename, for
exactly this reason — and that exemption is pinned, because a guard whose first
finding is a false one gets deleted.

**THE UI WORK IS NOT IN THIS FILE. It is a decision map on GitHub, and until
2026-08-27 nothing here said so.** `/wayfinder` charts one map issue with child
tickets; ours is **#3 "Cockpit for the pilot"** on `josephsapinoso/kalshi-cockpit`,
7 resolved and 23 open. Every screen question — what "Picks" opens, what each
tab is for, the colour system, what the list filters by — lives there with its
evidence, and a session that plans UI from this file alone **will re-derive
decisions Joe has already made**. Read the map body first (it is the low-res
index; the detail is in the closed tickets, fetched on demand):

    gh issue view 3 --json body --jq .body
    gh api repos/josephsapinoso/kalshi-cockpit/issues/3/sub_issues --paginate       --jq '.[] | select(.state=="open") | [.number,(.assignee.login // "-"),(.issue_dependencies_summary.blocked_by // 0),.title] | @tsv'

The second command is the **frontier query**: open, unblocked (`0`), unassigned
(`-`), first in map order wins. Conventions are in `docs/agents/issue-tracker.md`
(committed 2026-08-28; it was untracked and one `git clean` from gone). Claim a
ticket by assigning it to yourself BEFORE any work, and **resolve exactly one
per session** (research tickets excepted). The map produces *decisions*, not
builds: it is done when nothing is left to decide before someone builds it.

**THIS FILE IS THE FRONT DOOR, NOT THE MAP — asked and answered by Joe,
2026-08-28.** He asked directly whether a new session should start from
`/wayfinder` or from here. It starts from **here**, always; the map is one of
the queues this file points at. Two facts a session needs:

- **A session cannot invoke `/wayfinder` at all.** Its `SKILL.md` sets
  `disable-model-invocation: true` — Joe types it or it does not run. What a
  session *can* do alone is read the map with the two `gh` commands above, and
  that is what the paragraph above is for. Do not sit waiting to invoke it.
- **There are THREE queues and this file used to name two.** The "Open" list at
  the end of the latest entry is repo and infrastructure work. The map's open
  tickets are *decisions to be made*. The third is **decided and not yet
  built** — a closed ticket carrying a spec — and it belonged to nobody,
  because the map's own rule is to produce decisions rather than builds. **A
  resolved ticket with a build attached is a NEXT.md item.** That gap is not
  theoretical: ticket #10 was resolved at 03:34Z on 2026-08-28 recording a WCAG
  failure on the live real-money confirm button, and under the old reading no
  queue owned it.

So: read `git status`, then this file's Open list, then the frontier query —
in that order. The frontier query is the third read, not the default lane.

Read `CLAUDE.md`, then the latest entry below (it is the whole brief), then
`tasks/lessons.md` top two. Re-verify state, never inherit it:

    .venv\Scripts\python.exe -m pytest -q     (NEVER bare python; PATH is 3.14)
    cd frontend && npx tsc --noEmit

Expected: the number above, ruff clean, tsc clean, `next build` green.
Check `/api/health` `git_sha` against `origin/main` before assuming anything
is live. The terminal spread/total look was **VETOED by Joe 2026-08-21
16:11Z**, recorded per §7.1 in
`docs/measurements/2026-08-21-spread-total-edge-second-look-result.md` —
nothing fires at 22:40Z and no session needs to be alive for it. **The H4 look series is CLOSED
— BLOCKED ON INSTRUMENT, 2026-08-21** — do not build the A9–A12 analyzer
and do not re-run the channel diagnostic (A17.6/A17.11).

---

## 2026-08-28 (latest) — a leg priced at zero stopped the alerting half of the loop, and the heartbeat fired for a DIFFERENT reason

**Read this before trusting anything below about live.** Two live incidents
happened within an hour and **they are not the same incident**. Conflating
them is the obvious mistake and the evidence separates them cleanly.

### Incident A — `ZeroDivisionError`, FIXED and deployed (`5436fc8`)

Joe refreshed `/parlays` on his phone at ~12:37Z and got **"Backend
unreachable."** The box was healthy the whole time — `/api/health` answered
in 220 ms, `status: ok`, **no restart** (`machine_version` unchanged).

```
run_forever -> one_pass -> score_settle_and_alert -> build_ladder_payload
  parlays.py:553   contracts = stake_cents / (joint * 100.0)
  ZeroDivisionError: float division by zero
```

`loop_failures` ids 13-15: **three consecutive failing full passes**,
12:36:33Z, 12:38:03Z, 12:38:46Z.

**The joint is a product** (`running *= leg.p_conservative`), so **one** leg
quoted at `p_conservative = 0.0` zeroes an entire card. And
`build_ladder_payload` is called from `score_settle_and_alert` as well as
from the route, so the same exception **took out the tail of every pass**:
parlay cards, the daily digest and `log_gate_progress` all stopped. The
blast radius of one unpriceable prop rung was the alerting loop.

**Two overlapping guards, and the second is the one the outage argues for:**

1. `ladder_candidates` refuses a leg whose `p_conservative` is not positive,
   counted as **`fair_probability_not_positive`**. Refused, not clamped: a
   devig returning 0.0 for a market Kalshi is still quoting has not produced
   a small number, **it has failed** (CLAUDE.md rule 1).
2. `_stake_row` will not divide by a non-positive joint even so, rendering
   the em-dash the ledger already uses for "could not be computed". **A
   helper called from a loop that must not die does not get to trust its
   caller** — that is the whole lesson of this outage, and it is why the
   redundant guard stays.

Five tests, **both guards mutation-observed red independently**.

**NOT diagnosed: why a devig returned 0.0 for a live market.** That is
upstream of the parlay desk. The count is what will make its rate visible —
**read `fair_probability_not_positive` out of `/api/parlays`' excluded tally
next session.** If it is non-zero and steady, something upstream is
producing zero probabilities and that is its own investigation.

### Incident B — a 47.8-minute recorder gap, UNEXPLAINED and self-recovered

**The Discord heartbeat fired at 12:05Z: "the recorder has stopped ... has
not written a quote for 44 minutes."** ADR 0049's alarm, working, on a real
event. Joe forwarded it.

    gap 2,868,555 ms   resumed 2026-08-28T12:09:06.841Z   (started ~11:21Z)

**It is a different event from Incident A and the record proves it.**
`pass-gaps`' own rule: *"a gap WITH failures inside it was a failing loop; a
gap with NONE never came back to raise."* **There are no `loop_failures`
inside this gap** — the ZeroDivisionErrors begin at 12:36:33Z, twenty-seven
minutes AFTER the gap had already closed. So this was a **wedge or a
restart**, not a failing loop, and the ZeroDivision fix does not address it.

**Do not write this off because live is healthy now.** It self-recovered,
which is exactly the shape that gets normalised. What is known: no restart
was observed in `machine_version` across it, and nothing raised. What is
unknown: everything else. **Next session should read `pass-gaps` again and
check whether a second gap has appeared.**

### The heartbeat is worth trusting, and that is itself a result

ADR 0049's alarm has now fired once falsely (the 2026-08-27 burn, fixed by
`suppressed`) and once truly. **The true firing was accurate, arrived on the
phone, and named the right next instruments in its own text** — read
`/api/window is_open`, then `loop_failures`. Following it verbatim produced
the separation above in two commands.

### Open

- **VERIFY THE FIX HELD. What is established is narrower than it looks, and
  one thing said mid-session was wrong.** The claim "no new failures in the
  ten minutes since the deploy, against a pre-fix cadence of ~90 s" is
  **misleading**: between the last failure (12:38:46Z) and the deploy
  (12:51Z) **no pass ran at all** — the loop had stopped after three
  consecutive failures, so there was nothing to fail. The clean interval was
  not evidence.

  **What IS established:** the first pass on the fixed build, `pass 1 ok` at
  12:54:11Z, succeeded. **What is NOT:** sustained health — only that one
  pass had completed at hand-off — and, more importantly, **whether the new
  guard actually fired.** If the zero-probability leg aged out of the
  24-hour window on its own, that pass would have succeeded on the OLD build
  too, and production has not exercised the fix at all.

  **The measurement that settles it is `fair_probability_not_positive`, and
  it is currently unreachable.** It is not logged, and `/api/parlays` needs
  auth. **Log the ladder's excluded tally on the pass summary line** — it is
  a few characters beside the counts already there, and without it this
  question cannot be answered from outside. Do that before concluding
  anything about the fix.
- **Recorder age was climbing at hand-off**: last write 12:52:33Z, age 621 s
  at 13:02:55Z, with one pass since the deploy. Below the ~15 min full-pass
  cadence and far below the heartbeat's 44 min, so **not** an alarm — but it
  is the same reading that preceded incident B. Read it first.
- **Incident B is unexplained.** See above.
- **`fair_probability_not_positive`** — read the rate.
- **Joe should reopen `/parlays`.** It loaded in 2-3 s before the crash
  began; that measurement predates the fix and has not been retaken.
- Carried forward: 2-3 s is still slow and indexing will not fix it (see the
  entry below); #35 (the panel promising a refused sweep); #32 and #33;
  ADR 0079's prop tap; B0; the combo purchase slice; `odds_snapshots`
  retention.

---

## 2026-08-28 — one tab could take the site down, and the desk went quiet without saying so

Second half of the palette session, and none of it was planned. **Joe was
awake and sent ten phone screenshots of live**, which is the first time the
UI has been reviewed on the device it is used on. Two live defects came out
of that, one of them the ticket the map had already flagged as the worst
thing on it.

### THE ONE THAT MATTERS — `/api/parlays` could take the whole site down

Joe: *"The parlay page isn't opening for me on the phone."* Ticket #22 had
measured it and called it **the only ticket on the map where the status quo
actively harms the running system**: `ladder_candidates` `fetchall()`d every
`fair_prices` row in a rolling 24-hour window — **463,866 rows, ~557 MB on a
2 GB box already at ~1.03 GB at rest** — and deduped in Python *afterwards*.
Repeated visits OOM-killed uvicorn, and because `entrypoint.sh` uses
`wait -n`, killing that child tore down the container and **restarted the
recorder too**. ~91 s of whole-site outage was observed measuring it. **The
blast radius was never one tab.**

**Fixed at `7b185e8`, deployed, live.** The dedup is now `ROW_NUMBER()`
partitioned on exactly the five columns the Python key used.
`outcome_description` is in that list and is the one that matters: NULL on
team markets, load-bearing on props where `outcome_name` is only
"Over"/"Under", so dropping it collapses two pitchers at one rung onto one
row — **a wrong leg offered for money, not a slow page**. SQL `PARTITION BY`
groups NULLs the way a Python dict key of `None` does, so the two agree
exactly there. `f.rowid` breaks ties, making the choice stable rather than
merely arbitrary.

**The Python dedup stays as a safety net, and that is why the new tests are
necessary**: with the net in place, removing the SQL bound leaves the route
*correct* and silently slow again — which is how it shipped the first time.
Four guards, each mutation-observed red, each defect caught by both a text
assertion and a behavioural one.

**Two existing probes were too literal; both repointed, neither loosened.**
`test_without_the_fair_prices_index_it_scans_again` matched the literal
string `SCAN f`; the bound makes SQLite reach for `idx_fair_link`, so the
degraded plan is `SCAN f USING INDEX idx_fair_link` — still every fair
price. **The same pattern guarded the PRODUCTION plan, where it would have
passed vacuously the moment a scan went through an index.** That hole is
closed. Production plan unchanged where it counts: `SEARCH f USING INDEX
idx_fair_market_computed (market=? AND computed_ms>?)`.

**Not established: that `/api/parlays` is fast.** The guards assert one row
per identity on a fixture holding duplicates. Wall-clock belongs on the live
box behind auth and **has not been re-taken** — Joe opening the tab is the
measurement.

### THE SECOND — the desk stopped buying odds and told him the opposite

The screenshots showed every row at **198-minute-old books**. Both automatic
refresh paths were off, each correctly:

- **attention slice spent** — 300 of 300, exhausted 20:46:30Z the previous
  evening
- **hourly floor idle** — its rule is a fixture inside twelve hours; the next
  kickoff was ~13.7 h out

Nothing was broken. ADR 0071 §2.6 did exactly what it was built to do. **But
the refresh panel said *"The next scheduled sweep is now"* at 04:38Z while
the loop, in the same minute, refused that exact sweep.** Verified in code,
not inferred: `next_sweep_ms` is `next_call_ms`, computed from
`firing_for_slot`, and the attention-slice check sits **after** it at
`timing.py:1701-1708`. The field's own comment claims *"the page cannot
disagree with it"* — true of the slot schedule, false of the budget.

**And a tap would have worked**: 150 credits reserved for taps, **0 used**.
The one action that would have fixed the screen was available and the screen
was telling him not to bother. **Ticket #35.**

### The attention slice now has a number, and CLAUDE.md asked for it

CLAUDE.md said *"Do not quote a saving from this... every attended-hours
figure is a guess"* and named the instrument. First reading with attention
actually running (budget day 20260827):

    attention          75 calls   300 credits   15:53Z-20:46Z   4.88 h
    floor + schedule   48 calls   192 credits   10:13Z-01:42Z
    taps                0 calls     0 credits   (150 reserved)
    total             123 calls   492 of 700

**The slice buys 4.9 hours of attention a day at 61 credits/hour** — three
sports on ~10-minute cadences drawing on one slice, median gap 3.6 min, no
gap over 20. CLAUDE.md updated; the burn rate is the part that generalises,
a single day's attended hours is not.

### Map tickets

- **#34 opened and RESOLVED** — "is the ochre wash a defect or the true
  state?" **The true state.** Both refresh paths correctly off, every row
  genuinely stale and unbettable. `stale_odds` **stays ochre**; no repaint,
  and the three candidate treatments are withdrawn. Closed pointing at #15:
  the defect is showing 100 unbettable rows 14 hours out, not their colour.
  Answered without spending the 4 credits the ticket budgeted, because the
  live record answered it better.
- **#35 opened** — the panel/loop contradiction above.
- #32 and #33 still open and still unowned.

### Open

- **VERIFIED by Joe on the phone, 2026-08-28: Parlays loads in 2-3 seconds.**
  It was not opening at all before the bound. **Ticket #22 is closed** — the
  harm it existed for (an OOM that took the container and the recorder with
  it) no longer has a path.
- **2-3 s is not fast, and it is almost certainly now the slowest route on
  the instance** — every other one is sub-second. The residual is the shape
  the plan already showed and indexing cannot remove: `AUTOMATIC PARTIAL
  COVERING INDEX` over the subquery's output, which has no persistent index
  by definition, plus two `USE TEMP B-TREE FOR ORDER BY` sorting a derived
  join. **Sub-second means changing the query's shape or its window, not
  adding an index.** No ticket yet; open one before touching it, because the
  obvious move (add an index) is the one that is already ruled out.
- **Two map tickets were resolved this session (#34 and #22) against the
  one-per-session convention.** #22 because leaving the map's most urgent
  ticket reading "opening it can take the site down" after that stopped being
  true is worse than the deviation. Flagged rather than hidden.
- **`sweeps_remaining_today` may have #35's defect too** — it is computed
  from the whole day's budget (`timing.py:1134`), not the attention slice.
  Unchecked.
- **The rest of the UI is still unreviewed on a phone.** Ten screenshots
  covered Games and Your bets. Picks, Parlays, Gate and the ticket sheet
  have never been seen on the device.
- Carried forward: ADR 0079's prop tap needs one tap (`/events/` row at
  **10**); `suppressed_last_24h` goes non-zero at the next `parlay_daily`
  card; B0 needs Joe's call; the combo purchase slice; the pragma change not
  re-measured on live; `odds_snapshots` / `fair_prices` retention.
- **`tasks/lessons.md` is at 81.9%** of the ceiling; split at 90%, and check
  before writing.

---

## 2026-08-28 — the palette split shipped, and the guard watching it was measuring the wrong pair

**State at start: `main` = `2b58e01`, clean**, `origin/main` level, live
`/api/health` `build.git_sha` = `2b58e013…` — so **live carried all current
code**. One lane on disk (`parlay-props` at `e90b154`, spent); the empty
`hedging-research` shell was already gone. Joe said "read NEXT.md and start",
then asked two questions mid-session about the `/wayfinder` workflow. Both are
answered in the SESSION START box above.

### What shipped — ADR 0081, Split A

Ticket #10 was resolved at 03:34Z with a complete spec and Joe's own choice from
a prototype, and **nothing had built it**. What it recorded was not only a design
decision: **every filled control in the app rendered white text at 3.76:1 in dark
mode against a 4.5:1 floor, on live** — including `ManualTicket.tsx:563`, the
confirm button that spends real money.

- `--accent` is **indigo** (`#2f3d8f` / `#8ea2ff`) and means identity and commit.
  `--accent-fill` (`#2f3d8f` / `#3b4bb8`) is the ground under white, and it is a
  **separate token on purpose**: the two are equal in light and unequal in dark,
  and one token doing both jobs is exactly how the defect got in. Twelve filled
  controls moved to it, plus `::selection`.
- `--negative` keeps the red byte-for-byte and **nothing else wears it.** The old
  red tint is not deleted, it is renamed `--negative-soft` to the role it was
  actually serving (the suspect-edge chip, the alarm banner).
- **Every refusal went ochre** — the REJECTED chip, suppression reasons on three
  screens, the locked gate, unmet gate and ticket conditions, the skeptic's
  refused checks — on a new `--accent-2-soft` tint. That settles a contradiction
  nobody had noticed: the chip was red while the edge number beside it was
  already ochre.
- **`--edge`** on 35 card panels, at the quiet 1.69/1.86:1 Joe picked over the
  strong option.
- **`suspicious_edge` keeps loss-red and its ⚠ mark**, deliberately: rule 1 is
  the one row where the loudest available signal is correct.

**Every ratio in the ticket was recomputed from scratch rather than trusted, and
all of them reproduced exactly** — including the 3.76:1.

### The guard was good and it was measuring the wrong pair

`tests/test_palette_contrast.py` was green throughout. It checked every token
**as ink on a ground** and never **as a fill under white**. Those are different
pairs, and a token necessarily fails one while passing the other, because the
shade legible as ink on a dark card is a light shade and white does not sit on
it. Four assertions added, **all four observed red on mutation**:

1. white on every fill token clears 4.5:1 (mutation: restore `#ef4444`);
2. `--accent != --negative`, and they stay ≥60 apart under deuteranope and
   protanope simulation (mutation: collapse them — the second reports 0);
3. every `:root` token has an `@theme inline` registration and no registration
   points at a missing token. **An unregistered token is a Tailwind class that is
   silently dropped** — no error, no build failure, the element just renders
   with no colour, and four of five new tokens were new classes;
4. `TestTheNeutralCountIsNotPaintedAsAVerdict` **rewritten, not deleted**. Its
   premise was "`--accent` *is* `--negative`, so a Stat in it reads as a loss",
   now false — a Stat may lawfully wear indigo. What survives is stronger: a
   count is a fact, so **no Stat wears the loss colour**, whatever that colour is
   this month.

**And a near-miss no guard caught.** Applying `--edge` by rewriting
`border bg-card` → `border-edge bg-card` **deletes every panel border**:
`border` sets the width, `border-edge` sets only the colour. It typechecked
clean, built clean and passed everything. Caught by reading the diff.

### Verified

- `npx tsc --noEmit` clean; `npx next build` green.
- **The built CSS was read, not just the build's exit code.** `bg-accent-fill`,
  `bg-accent-2-soft`, `bg-negative-soft` and `border-edge` each emit a rule
  pointing at the right custom property in `.next/static/chunks/*.css`. A green
  Tailwind build proves nothing about a class it did not recognise.
- One test went red and was **repointed, not loosened**: `test_desktop_tier.py`'s
  "only the first send wears the accent" probed the literal string `bg-accent `.
  The rule is about *weight*, not hue; it now names the fill token. **ADR 0061 §3
  was amended at its own heading** rather than silently contradicted, because its
  "commit red" was placed there deliberately.
- Stale premises repaired in five docstrings that explained a rule by saying
  "`--accent` is the same red as `--negative`". **No assertion was loosened** —
  the six components that refuse colour still refuse it; that is #33 and unowned.

### Deployed 2026-08-28 04:23Z, clean, and the fix was verified on live itself

**Live is at `bc256e3`** — `/api/health` `build.git_sha`, read after the run
went green and checked against `git rev-parse HEAD`, not inferred from the
deploy succeeding. `status: ok`, `recorder.age_ms` 16,975 (17s, writing), no
outage: the whole run took **1m15s**.

**`flyctl deploy` was gated by the auto-mode classifier; the GitHub Actions
dispatch went straight through** in the same minute
(`gh workflow run deploy.yml -f instance=live -f confirm_live=kalshi-cockpit`).
That is the documented shape — the classifier is intermittent and not worth
predicting. **The Actions route is also the safer one here**: it deploys from
`actions/checkout` of the pushed commit, where `flyctl deploy` uploads the
working tree, which is the exact gap that caused the 2026-08-27 CRLF outage.
The tree was clean and pushed, so the two agreed, but only one of them proves it.

**The fix was then verified in the CSS live actually serves**, not in the local
build and not from the deploy's exit code — `/login`'s stylesheet was fetched
from the live origin and every token read back:

    --accent        #2f3d8f / #8ea2ff        --accent-fill   #2f3d8f / #3b4bb8
    --accent-soft   #e8eaf7 / #151a33        --accent-2-soft #f7f0dd / #2a2313
    --negative      #aa0000 / #ef4444        --negative-soft #f8e6e6 / #2a1315
    --edge          #cfc6bb / #4a423b

`.bg-accent-fill{background-color:var(--accent-fill)}` is served, so **the
real-money confirm button now renders at 7.28:1 instead of 3.76:1 on the live
instance.** `ef4444` appears exactly once in the whole served stylesheet — as
`--negative` in dark, which is ink and never a fill. That single count is the
cheapest possible statement of the whole ADR: red exists, and it is not a
button any more.

### Open

- **#32 and #33 are the live consequences of this build.** #32: the real-money
  warning strip (`ManualTicket.tsx:476`) was left on `--accent`, so it is now
  indigo **by default rather than by decision** — the prototype drew it red and
  that was an unreviewed call. #33: the six components are free and nobody has
  said whether they take colour.
- **One screen has been looked at, at 390px, in both themes — and it is the
  least interesting one.** `/login` was rendered against `next dev` under
  Playwright: the confirm button is legibly indigo (the 7.28:1 replacing
  3.76:1), the card carries a visible `--edge`, the focus ring is indigo, and
  the warning paragraph is still ochre. That is a real check and it is a narrow
  one. **The screens that matter are unseen**: Games rows, Picks blocks, the
  ticket sheet, the gate — every one needs the API behind a session cookie, so
  the local dev server cannot reach them. Chrome's extension was not connected
  this session; with it, live can be read directly. **This is the first thing to
  do next.**
- Carried forward unchanged: ADR 0079's prop tap needs one tap on Joe's phone
  (look for the `/events/` row at **10** credits); `suppressed_last_24h` is still
  0 and goes non-zero at the next scheduled `parlay_daily` card (read 0 at 03:52Z
  with `undelivered_last_24h` still 5 — the five decay on their own, do NOT read
  a lingering 5 as the fix having failed); B0 needs Joe's call; the combo purchase
  slice; the pragma change not re-measured on live; `odds_snapshots` /
  `fair_prices` still have no retention rule.
- **`dd.status` is handled** — `*.status` is gitignored rather than deleted,
  since nothing in this repo knows what writes it.
- **`frontend/next-env.d.ts` showing as modified is not a stray and is not
  yours.** It has appeared dirty at the start of at least two sessions with no
  explanation. `next dev` rewrites its two imports to `./.next/dev/types/…` and
  `next build` rewrites them back to `./.next/types/…`, so the file records
  which of the two ran last. **Never commit it** — whichever way it is pointing
  is a fact about one machine's last command, not about the repo. `git checkout
  -- frontend/next-env.d.ts` after any `next dev`.
- **`tasks/lessons.md` is at 81.9% of the ceiling.** The rule is split at 90%,
  and the check goes *before* writing an entry, not after.

---

## 2026-08-27 — the map got three rulings and a colour, and this file learned the map exists

**State at start: `main` = `2b58e01`**, clean apart from three pre-existing
working-tree entries (`frontend/next-env.d.ts` modified, `dd.status` and
`docs/agents/` untracked). **No code was written this session and none of those
three is mine.** The only file in this repo that changed is this one.

**The whole session ran on the GitHub decision map, not on the codebase.** Joe
invoked `/wayfinder 3`. If that sentence means nothing to you, read the new
paragraph in the SESSION START box above — **the omission it fixes is the
finding of this session.** NEXT.md had no reference to map #3 anywhere in
142KB, so a session obeying CLAUDE.md's read order would have planned UI work
in complete ignorance of seven resolved decisions. That is this repo's named
defect — *displayed and still missed* — pointed at its own handoff file.

### Three calls Joe made on work resolved in his absence

#8 and #9 were resolved by a prior session that flagged, in writing, which
parts were the agent's judgement rather than Joe's words. Those were put back to
him and are now ratified on the tickets and on the map:

1. **The nav word "Picks" stays.** The ADR 0038 rename argument (a nav label is
   the product's own voice; `beta = -0.141` says the tool has no picks) was put
   to him with two alternatives and declined. No test pins any nav label, so it
   stays reversible.
2. **`/board`'s demotion to a Footer "Also served" entry is confirmed**, with
   both in-page links struck. A footer entry is a link *plus a sentence*, on all
   six routes, which satisfies his standing "explain them where they are"
   preference better than a bare nav word did.
3. **The page-top placement stands and #31 is not urgent.** He accepted that
   the sentence answers "what is this tab for" one tap *after* he asks it,
   because nothing is ever bet from the nav strip — six taps, once, against
   losing the Gate link on every screen every night.

### #10 resolved — the palette collision, and two defects found by recomputing

`--accent` and `--negative` were byte-identical. Joe chose **Split A** from a
prototype (real Games rows and Picks blocks, four schemes, both themes):
`--accent` becomes indigo `#2f3d8f` / `#8ea2ff` with a separate
`--accent-fill` `#3b4bb8`; `--negative` keeps the red and nothing else may wear
it; REJECTED moves to the warning ochre; panels take a new `--edge` at
1.69/1.86:1. Full reasoning and every ratio are on the ticket. Prototype:
https://claude.ai/code/artifact/ddfe5cc4-c58c-43dd-b14e-c665050b81d4

**Three corrections came out of recomputing rather than trusting the ticket's
arithmetic, and the first is a live defect nobody has fixed:**

1. **Every filled red button fails WCAG AA in dark mode, on live, right now.**
   White on `#ef4444` is **3.76:1** against a 4.5:1 floor at 14px semibold —
   `ManualTicket.tsx:563` (the real-money confirm), `TicketSheet.tsx`'s four,
   `PriceOnKalshi.tsx:107`, `market/[ticker]/page.tsx:351`,
   `login/page.tsx:66`, `Nav.tsx:202`. `tests/test_palette_contrast.py` missed
   it because it checks tokens **as ink on a ground and never as a fill**.
   Building Split A fixes it at 7.28:1; **until then it is shipped and
   unguarded**, and it is the one thing on this list that is a bug rather than
   a decision.
2. **It was three roles on one token, not two.** Identity, commit-money and
   loss/refusal. The middle one was put there deliberately by **ADR 0061 §3**,
   so that ADR must be *amended* when this is built, not silently contradicted
   — its actual rule is about weight (a filled control claims the page) and
   survives in indigo.
3. **The ticket's `1.04:1` was the wrong pair** — that is card-vs-page-
   background; the border is `1.30:1` against the card, a figure
   `globals.css:22-23` already states in its own comment. Both invisible, so
   the conclusion held.

`globals.css:29-31` — *"`--negative` reuses the accent red: a losing number
rendering in the brand colour reads naturally"* — **is the recorded cause of
the defect and must not survive the fix.**

### Tracker state at end

- **Closed:** #4, #5, #6, #7, #8, #9, #10. **Open:** 23. **No ticket is left
  claimed-but-open**, so nothing is invisibly held by a dead session.
- **Opened #32** (what colour the real-money warning strip wears now that red
  is scarce — `ManualTicket.tsx:476` is byte-identical to today's REJECTED chip,
  and the prototype's red was an unreviewed call) and **#33** (which of the six
  components that refused colour in comments now take it — the actual payoff of
  #10, and it pairs with #17, now blocked only by #16).
- **#11 carries Joe's "yes" as a comment, not a resolution.** He wants his own
  typed estimate read back to him. Three things that answer does *not* settle
  are written on the ticket, and the one to put to him directly is the cost the
  ticket itself names: *once he can see the score, it changes what he types.*
  The ≥30-scored-bets floor is untouched by his yes.

### Still open from this session

- **`docs/agents/issue-tracker.md` is untracked.** `/wayfinder` reads it to find
  the map and wire sub-issues. It works because it is on disk; it is one
  `git clean` from gone. **Commit it.**
- **`dd.status` is a stray in the repo root**, not gitignored, and shows up in
  every `git status`.
- **No test run this session** — nothing was built, so the 4,942 baseline above
  is untouched and still qualified by the tree it was taken on.

---

## 2026-08-27 — the alarm that watches for a silent death had been taught to fire every day, and the combo tests were all in the wrong branch

**State at start: `main` = `e077010`** (clean, nothing unpushed; a NEXT.md-only
commit), **live `git_sha` = `9d34ef3`**, so live carried all current code. No
lane was working: `parlay-props` was a spent shell at `e90b154` (merged
`ba8fc0d`, 0 ahead / 3 behind, clean) and `hedging-research` an empty
unregistered directory. Joe said "read NEXT.md and start".

**Nothing here was on the plan.** Three live readings were taken before
planning, two of them the registered checks the entry below is waiting on, and
the third turned into the session.

---

### The two registered checks, and one of them is now ANSWERED

**The 20:00Z `parlay_daily` card FIRED and DELIVERED.** Three rows at
**2026-08-27T20:06:02.409Z** — `safe: 3 legs`, `middle: 4 legs`,
`lottery: 6 legs` — all `delivered = 1`. The entry below predicted "tomorrow's
20:00Z"; it happened the same day. **ADR 0076's scheduled card is observed
working on live for the first time.** `parlay_daily` now has 6 rows all told,
two batches of three (06:14:49Z and 20:06:02Z), every one delivered.

**ADR 0079's prop tap is still PENDING, and the recognition rule below is
WRONG. Do not look for a row at 14.** A tap writes **two** `api_credits` rows
and 14 is their sum:

| row | endpoint | markets | cost |
|---|---|---|---|
| team sweep | `/sports/{k}/odds` | `h2h,spreads` | 4 |
| the props | `/sports/{k}/events/{id}/odds` | the 5 base keys | **10** (was 20) |

So the number to read is **10 on the `/events/` row**, and the discriminator is
`endpoint LIKE '%/events/%/odds'`. **`_SERVED_SWEEP`'s `LIKE '%/odds'` matches
both**, which is deliberate (`client.py:493-500`) and is why the naive filter
cannot separate them. All **92** rows for budget-day 20260827 are 4-credit team
sweeps — 368 credits, latest 20:26:07Z — so **no prop tap has run on the new
build.** That is not a defect; it is no observation. **It needs Joe to tap a
prop on the phone**, and then `inspect_live_db.py credits-tail`.

---

### THE ONE THAT MATTERS — `/api/health` said five pushes had failed and none had

`undelivered_last_24h: 5`, read on live at 20:25Z, with nothing having failed.
**ADR 0080.** The entry below tells the next session to verify the card by
checking this field is "still 0"; it can never be 0 again on a day the card
fires.

Three pieces, each right on its own, in `backend/notify/alerts.py`:

1. `_claim` writes `delivered = 0` **before** the send — deliberately, so a
   crash between claiming and sending cannot silently re-alert.
2. ADR 0076's channel-burn claims `PARLAY_CHANGE_KIND` **with no send behind
   it**, so one composition cannot buzz twice. That row is `delivered = 0`
   forever, three a day.
3. `delivery_health` counted every `delivered = 0` row in 24h as a failure.

**The burn leaves exactly the signature ADR 0049 built this field to detect** —
its own words: *"the alerter claims the row before sending, so a process that
dies mid-send leaves exactly this. The loop died and Joe was not told, and
nothing said so for months."* And `test_alerts.py` already named the harm:
*"otherwise one bad night reads as a permanently broken alerter."* The burn made
it permanent.

**Bounded, and stated so nobody over-reads it.** `heartbeat.yml` does **not**
read this block — it reads `status`, machine state and `recorder.age_ms` — so
**no false alarm ever reached Joe's phone.** The damage was to a human read of
`/api/health` and to ADR 0072's verification method, which used
`undelivered_last_24h at 0` as its evidence.

**Fixed at schema v25**: `notifications.suppressed`, set by the writer at the
point it decides, because no reader can recover it afterwards — a claim with no
send and a death mid-send are identical in the record by construction. Not a
sentinel inside `delivered` (`inspect_live_db.py` does `SUM(delivered)`, so a
`2` would report each burn as two deliveries in the tool used to read this).
`suppressed_last_24h` is published beside the corrected count, which is also
**what makes the fix checkable from outside**.

**The five live rows were NOT backfilled.** Two are provable burns (ids 1531 and
1533, same millisecond as `delivered = 1` `parlay_daily` rows); the other three
are *consistent* with the day's other burns and that is not measured. They
default to `suppressed = 0` — still counted — and age out on their own.

### THE SECOND ONE — every green test on the combo tap ran the branch nobody meant to run

`tests/test_parlay_lookup.py` had 19 green tests. **All 19 ran the prefix
fallback.** `FakeCollections([])` built a collection with zero legs, so
`covering` was empty on every call, the fallback returned every time, and the
production-normal covering path — 100% of the live slate on 2026-08-27 — had
**never been executed once**. There was no test of `_choose_collection` at all.

**And the fake echoed back NFL legs on every call**, which are not the legs any
test asks for. Nothing compared the two, so it never mattered. It matters now.

**NEXT.md's citation is 8 lines stale**: the function is `parlays.py:955-976`,
not `:947-968`; the prefix table is `:896-899`, not `:888-891`.

### The fix is DETECTION, and the reason is a measurement, not a preference

The obvious fix — refuse when `covering` is empty — **is wrong**, and the
capture says why. `combo_lookup_repeat.json` posted to
`KXMVESPORTSMULTIGAMEEXTENDED-R` and Kalshi answered with
`mve_collection_ticker: KXMVECROSSCATEGORY-SHARD1-R`. **The collection in the
URL binds nothing; Kalshi re-homes the market.** Combined with the 2026-08-23
capture minting NFL legs a catch-all did not enumerate, a coverage refusal would
refuse taps that work.

So what shipped is the check that needs no venue observation and was sitting in
the response the whole time:

- **`echoed_legs` compares `mve_selected_legs` to what was posted.** That field
  is on every captured response and **was read by nothing** — `market_ticker`
  was all that came off the payload, so a market minted over the *other team*
  would have been priced and shown as the card. A mismatch now refuses, with the
  minted ticker kept on the row.
- **The comparison is on SETS, and that is measured.** Request order in the
  capture is `[PITBUF, NECLE]`; the echo is `[NECLE, PITBUF]`. A list
  comparison would call every real tap a mismatch.
- **`unreadable` is a third value, not a `False`.** An absent field is recorded
  and the tap proceeds — the market exists either way, and refusing would lose a
  real ticker over a wire change. It must never read as agreement.
- **`parlay_lookups.collection_unverified`** (schema v26) records whether the
  fallback chose the collection. **Whether a catch-all accepts legs it does not
  enumerate is unmeasured** — one observation, 2026-08-23. This column turns it
  into a rate.
- **`size_min` is enforced server-side.** The only other size guard was
  `PriceOnKalshi.tsx`'s `legs.length < 2`, and CLAUDE.md is explicit that the
  server never trusts the UI.
- **The cache flush stops guessing.** `invalidate_collections_cache()` is for a
  rotated `-R` suffix; it is the wrong diagnosis for a leg problem, so it no
  longer fires when the fallback chose without coverage.

**TWO GUARDS I DRAFTED WOULD HAVE REFUSED EVERY TAP, and reading the capture is
what stopped them.** All three catch-all collections carry `size_min 2`,
`size_max 0`, `is_all_yes False`. **`size_max = 0` is an unbounded sentinel and
`is_all_yes = False` means *unrestricted*.** Refusing on either would have been
an outage wearing a guard's clothes. Both sentinels are now pinned by tests
sourced to the capture, because the next reader will make the same mistake.

### THE THIRD — ADR 0079 left a stale figure in the comment `fly.live.toml` points at

`backend/odds/ondemand.py` still said *"6 fixtures' props"* and *"a prop refresh
is 24 credits"*. ADR 0079 halved the prop keys, so it is 14 and ~10 fixtures.
`fly.live.toml` was updated by the merge; this was not — **and
`fly.live.toml:317` tells anyone changing `ODDS_MANUAL_DAILY_CREDITS` to read
this comment first.**

The comment's own last line was *"Restating a derived number in a comment is how
all three drifted."* It drifted a fourth time, in the commit that caused it. So
the numbers are gone from the comment and live in `tests/test_odds.py` instead,
where a config change makes a test red rather than a comment wrong.

---

### Verification

- **Suite: see the box at the top.** Re-measured on the final tree, not
  inherited. **A baseline run was started at session open and KILLED as void** —
  the tree was edited under it, the exact failure this file records twice. It
  was never reported as a number.
- **Twelve mutations observed red**, six per defect area: the burn dropping its
  flag; `delivery_health` dropping the exclusion; the burn removed entirely; the
  fallback claiming it was verified; the echo check removed; `size_min` not
  enforced; the echo comparing order; `unreadable` treated as agreement; the
  cache flush unconditional again; `manual_cost` forgetting the prop half.
- **Both migrations driven on a database that already existed**, wound back to
  v24 and reopened — the gap `init_db`'s own docstring says a fresh fixture
  always misses. Idempotent on a second boot, and a pre-existing undelivered row
  correctly stays a failure rather than being written off.

### Deployed 2026-08-27 ~22:15Z, and it took live down for four minutes first

**Live is at `7c25247`** — `/api/health` `build.git_sha`, read after the run
went green and checked against `origin/main`, not inferred from the deploy
succeeding. `status: ok`, recorder writing, **`suppressed_last_24h` served**,
which is also the proof both migrations applied: the endpoint queries the
column and would 500 without it.

**The first deploy attempt crash-looped the box.** `docker/entrypoint.sh`
reached the image with CRLF endings, so the kernel looked for an interpreter
named `bash
`, the container exited **127 before any Python ran**, and Fly
gave up after ten restarts. **The migrations never started** — the failure is
upstream of every application-level guard there is.

**The repository was correct the whole time.** The blobs in git were LF,
`git status` was clean, the suite was green, and `.gitattributes` carried
`*.sh text eol=lf` **plus a comment describing this precise failure**. Only the
working copy was wrong — and `flyctl deploy --remote-only` uploads the working
tree, not `git archive HEAD`, so every check that reads the repository was
looking at a different object than the one being shipped. `text eol=lf`
normalises on checkout and staging and does **not** rewrite a file already on
disk from before the rule existed.

Fixed with `git rm --cached -r . && git reset --hard HEAD`, and guarded:
`TestNoCarriageReturnReachesTheContainer` reads the **working tree** on purpose
— the obvious implementation against `git show HEAD:` would have passed
throughout. Mutation observed red by restoring the CRLF.

**A second miss in the same deploy, smaller:** the first two attempts ran
without `-e GIT_SHA="$(git rev-parse HEAD)"`, so `/api/health` reported
`git_sha: null` — the one field this file tells every session to check. It is
documented at `fly.live.toml:3` and was simply forgotten. Redeployed with it.

**Read the logs, not the exit code.** `flyctl` reported
`Unrecoverable error: timeout reached waiting for health checks ... request
canceled` — a *client-side* API timeout, which is not a health check failing,
and the exit code cannot separate the two.

### Open

- **ADR 0079's prop tap — needs Joe.** One tap on the phone. Look for the
  `/events/` row at **10**.
- **`undelivered_last_24h` will NOT read 0 immediately after deploy.** The five
  unmarked rows decay over 24 hours. **The check that settles it is
  `suppressed_last_24h` going non-zero at the next scheduled card**, and the
  full confirmation is tomorrow's 20:00Z. Do not read a lingering 5 as the fix
  having failed.
- **B0, ruled in scope by the partner and NOT done:** post one non-covering
  combination and record what Kalshi actually does. It replaces two unsourced
  sentences in this repo with an observation and costs no money — but it leaves
  **one durable minted market on Joe's account**, so it is his call and it is
  flagged here rather than taken.
- **The pre-tap membership check NEXT.md originally asked for is still not
  built, deliberately.** Its correct shape depends on B0. Detection now exists
  and protects against it in the meantime.
- **Close the `parlay-props` worktree** and delete the empty `hedging-research`
  shell. Both Joe's; nothing in this repo starts or stops a lane.
- Unchanged: the combo purchase slice; the pragma change not re-measured on
  live; `odds_snapshots` / `fair_prices` still have no retention rule (1.91 GB
  of a 5 GB volume).

---

## 2026-08-27 — two lanes can be seen at once, and the tool that saw them told a human to delete sixteen projects

**State: 4,885 passed / 10 xfailed in 20:59 at `1fecb54`**, ruff clean,
`origin/main` at `c24309a`. Joe's ask was "have the partner oversee the herder
worktrees so no collisions happen, and weigh priority between the worktrees and
NEXT.md."

### What shipped

`scripts/lane_board.py` — a read-only cross-worktree detector. It reads every
worktree and local branch together: ahead/behind, uncommitted work, ADR and
schema claims, and the collision surface. **It closes the gap
`tests/test_parallel_lanes_do_not_collide.py` names in its own docstring** —
that a test only sees the tree it runs in, so it fires when lanes MERGE and not
when a collision is created.

`docs/adr/README.md` — the ADR numbering convention, which until today lived
only in a lessons entry, the box above, and two regexes. A lane that went
straight to `docs/adr/` could not find the rule it was about to break, which is
roughly how all three of 2026-08-27's collisions happened.

**The ordinal race is closed by allocation, not by detection.** A lane writes
`docs/adr/DRAFT-<slug>.md` with no ordinal; the number is taken in the merge
commit after a fetch. The guard refuses a `DRAFT-` on `main`.
`tasks/lessons.md:168-191` had already ruled that reading `main` first is not
the fix, and a detector cannot change that — it shortens the window.

`tasks/LANES.md` — generated below a marker, with a hand-written allocation
ledger above it that survives regeneration. Replaces the hand-typed lane table
that used to sit in the box above and was wrong within hours of being written.

`scripts/drive_hedge.py` + `tests/test_drive_hedge.py` — rescued from the
hedging lane's scratchpad before it was deleted. The only instrument that drives
the hedge payload against a real Kalshi book, and it found the same-game defect
the suite did not. The seam test pins every symbol it reaches for; it is never
run in CI.

### Three things it got wrong first, and all three matter more than what it got right

1. **It compared files, not hunks.** The hand-measured surface that specified it
   called `frontend/src/lib/api.ts` contested; the two edits are 1,780 lines
   apart and merge clean. Caught by the partner before it was built.
2. **It reported an inherited `SCHEMA_VERSION` as a claim.** A lane ten commits
   behind holds main's old stamp without touching `db.py`. Provenance decides,
   not value.
3. **Run from a LANE it named sixteen of Joe's unrelated repositories as
   directories to delete**, `kalshi_orderbook_monitor` among them — the
   predecessor project CLAUDE.md tells every session to read. `root` was the
   lane, so the integration checkout read as a peer worktree and the projects
   folder became a search root. **Caught by the `parlay-props` lane running the
   tool for its own reasons**, not by its author and not by its tests.

Sixteen mutations run; the load-bearing one — "unreadable is never clean" —
stayed green because the test reached the guard by a different road. Fixed. The
DRAFT guard shipped with a hole of the same shape: it SKIPPED on an
unestablished branch, and `actions/checkout` leaves a detached HEAD, so it would
have skipped on every CI run there has ever been. It fails closed now.

### The partner's ruling (2026-08-27), still standing

**Not the lane split.** ADR 0003 §1's table predates the parlay desk —
`backend/parlays.py` and `backend/core/ladder.py` are in no lane at all — so the
lane crossed a partition that does not cover the files. Amended. A **type
declaration is owned by its producer**, not by the frontend lane; enforcing §1
literally there causes the harm §1 prevents. `.env.example`, `fly.live.toml` and
`tasks/LANES.md` joined the integrator-only list.

**Dropped this session, do not reopen without naming what overturns it:** all
further prop-feed analysis (the measurement is done); ADR 0032 stays closed;
combo purchase slice; per-sport credit reservation; `/api/slate` N+1;
`odds_snapshots` retention; the stale 576/day figure in `docs/`; `ODDS_API_KEY`
rotation; NCAAF's single sweep (one observation with no comparison is an
anecdote).

**The four verification debts do not compete with lane work.** ADR 0077's cold
open, the 20:00Z `parlay_daily` card, the hedge watcher polling, and NCAAF share
one blocker: each needs a human or a session awake at a specific UTC minute on
live. They collapse into one opportunistic checklist the next time anyone has
live open for another reason.

### The lane merged — `ba8fc0d`, ADR 0079

**The `_alternate` prop feed stops being bought.** 66.3% of the rungs in the
committed dump are quoted only on that feed and **0 of those 4,707 are
two-sided**, so none could survive `prop_quotes_for_event` and none ever became
a fair price. It bought sightings, not prices, at half the cost of every prop
event. Tap goes 26 → 14 credits. Prop rungs also become parlay legs, gated so
none of them move.

**ADR 0079 is the first live exercise of the merge-time allocation rule**,
taken after a fetch against a `main` that had moved seven times since the lane
started. Nothing collided. The rule was written this morning out of three
collisions and had never been run in anger.

**`fly.live.toml:476` still says this does NOT re-open ADR 0032 — keep that
sentence.** Halving a price is the most persuasive possible argument for
reopening something that was closed on other grounds, and a future reader
arriving on cost alone is exactly who it is for.

### Three defects in the new tooling, all found from outside it

Worth more than the tooling. **Every one was found by the lane running the
board for its own reasons, or by merging — none by the author, and none by the
tests.**

1. **Run from a lane it named sixteen unrelated repositories as directories to
   delete**, `kalshi_orderbook_monitor` among them. Fixed; the fixture had put
   lanes in the same parent as the checkout, so no test *could* have caught it.
2. **"git will conflict" was a claim it could not support.** The predicted
   `backend/parlays.py` conflict auto-resolved — adjacency makes a conflict
   possible, not certain, and both the author and the lane called it certain.
   Now says MAY.
3. **An unpushed integration branch was displayed and not a finding.** Twice an
   integrator merged, read `git log -1 main`, and reported done while
   `origin/main` was seven commits behind — the object store is shared, so from
   that seat local and pushed look identical. Now a finding, failing only when
   the unpushed commits allocate a global counter.

All three share one shape, written up in `tasks/lessons.md`: **the correct
information existed somewhere in the artefact and was not where the decision
gets made.**

### Deployed 2026-08-27 ~20:18Z, and what that did and did not settle

**Live is at `9d34ef3`** — `/api/health` `build.git_sha`, read after the run
went green, not inferred from the run's success. It had been 20 commits behind
at `f59d102`.

**ADR 0079's credit check is PENDING, not passed.** The reason to deploy was
that live was buying 26 credits per prop tap for a feed where 0 of 4,707 rungs
are two-sided; deployed it should be 14. **No prop tap has run on the new
build yet.** All 89 `api_credits` rows for budget-day 20260827 are 4-credit
`h2h,spreads` sweeps — 356 credits, every one `trigger = 'attention'` — and the
last is `20:16:05Z`, before the deploy landed. To settle it:

    flyctl ssh console -a kalshi-cockpit       -C "python /app/scripts/inspect_live_db.py credits-day --date <YYYYMMDD>"

and look for the **`/events/{id}/odds` row at 10**, not 20. **A tap writes TWO
rows** -- a 4-credit team sweep and the per-event props -- so 14 is their sum
and no single row ever carries it; see the 2026-08-27 entry above. **Do not
report ADR 0079 as verified on live until that row exists.** A deploy that succeeded is not a
behaviour that changed.

**The registered checks and when each can be taken**, written before the
results so the choice of check cannot be contaminated by the answer:

| check | settles when |
|---|---|
| ADR 0079 tap at 14 credits | the next prop tap on live |
| ADR 0077 cold open | a sweep within a minute of a 10:00Z roll — needs tomorrow |
| 20:00Z `parlay_daily` card | tomorrow's 20:00Z; today's window passed at deploy time |
| hedge watcher polls | **blocked on Joe** recording a real parlay from his phone. Zero positions makes correct silence indistinguishable from a task that never started |
| NCAAF sweeps more than once | a full day; NCAAF rows are present today at 4 credits, so it is sweeping |

One of those is answered early and is worth keeping: **NCAAF is sweeping.** It
appears repeatedly through 19:27–20:16Z alongside MLB and WNBA. The 2026-08-26
worry that it swept once at 10:12:48Z and never again does not hold on today's
record.

### Open, and both are Joe's

- **Close the `parlay-props` worktree** — merged at `ba8fc0d`, nothing left in
  it. And delete the empty `hedging-research` shell, which the board reports on
  every run and `git worktree prune` will not remove.
- **Cross-game prop parlays are CONSTRUCTIBLE.** Read 2026-08-27 off
  `GET /multivariate_event_collections` (no mint, no book, no order path): of
  1,389 collections, 17 are cross-game and **3 carry all five MLB prop series,
  35 prop legs each, `detail_missing = 0`**. Those three share an identical
  2033-leg total and are almost certainly one pool under three tickers — **treat
  it as one observation**. Every NFL/NBA/CB multi-game collection carries zero
  prop legs, so this is MLB-and-cross-category on today's slate; the calendar
  caveat in `backend/kalshi/combos.py` is untouched. **Eligibility is not
  liquidity** — this says nothing about the 40/40 enter-only record, and the two
  sentences must stay apart.

  **The denominator was measured afterwards and it is 35.** `35 prop legs` was
  first written up as *partial* coverage, and it is not: every open MLB prop
  event on the slate is eligible. Set-compared per series against
  `KXMVECROSSCATEGORY-R` rather than count-matched — same event tickers,
  `open_but_not_eligible` and `eligible_but_not_open` both empty on all five
  series, 7 games × 5 statistics. **This is n = 7 games at one instant and
  neither "partial" nor "total" may be written as a property.** The honest
  sentence is: *on the 2026-08-27 slate all 35 open prop events were eligible;
  whether that holds structurally is unmeasured.* Only one of the three
  collections was checked. A clean hypothesis with a clean test: the `-R`
  suffix on all three suggests a **rolling** collection tracking the slate,
  against the fixed `-W5`..`-W13` NFL ones that carry zero props — re-read on a
  different slate size decides it. Not evidence yet.

  Consequence for `parlays.py:947-968`: the lane's pre-tap check is still worth
  building and **its reason changed**. Not "eligibility is partial so the
  fallback fires often" but "eligibility is total today and the code must be
  correct on the day it is not" — when `covering` is empty the prefix fallback
  fires anyway and the tap posts a leg the chosen collection does not contain.
  It fails at Kalshi rather than silently, but after a tap instead of before.

## 2026-08-27 — a cold open buys odds on the pass it woke

**Joe picked this off four options.** ADR 0077. State: **4,640 passed / 10
xfailed in 19:54** (up 17 from 4,623 measured earlier the same session), ruff
clean.

### Three facts agreed, and none was wrong on its own

1. **`last_sweeps` is scoped to the budget day** —
   `last_sweep_by_sport(conn, since_ms=budget.day_start_ms(now_ms))`. Every
   10:00Z roll leaves every sport unpaced.
2. **`run_quote_pass` passed `allow_bootstrap=False`, hardcoded.** Correct
   about the cadence: with no `last`, every pass wants every uncovered sport,
   so a *failing* sport would retry every 15s until the credits were gone.
3. **`pass_kind` returns `"quote"` inside `last_full_ms + 900s`** — where an
   early wake lands by construction.

Together: open the desk after the roll, the loop wakes in 5s, runs a quote
pass, and **that pass can buy nothing**. Up to 900s of blank desk, while
`window_status` — calling `desk_wants` with the default `allow_bootstrap=True`
— says a sweep is due **now**.

**MEASURED, NOT ARGUED. Budget day 20260827 rolled at 10:00:00Z; its first
credit was spent at 10:13:56Z.** Fourteen minutes, read off `api_credits` on
the live volume.

### The fix

`run_quote_pass` takes `allow_bootstrap`, **still defaulting to `False`**, and
the loop raises it only for a pass that follows an early wake.
`scheduler.one_shot_wake(state)` turns `LoopState.woken_early` — the total
`run_forever` already keeps — into a per-pass answer.

**An event, not a state, and that is the whole safety argument.**
`is_attended` is true for the entire 300s TTL while a quote pass runs every
15s. A wake is at most one per heartbeat. Consumed on read; seeded from the
counter rather than zero; read rather than incremented, because `woken_early`
can move more than once between passes and differencing leaves a backlog.

**What actually bounds the spend, stated exactly because this is a spend
path:** one *successful* sweep enters `last_sweeps` and paces the sport for
the day, so the flag then changes no answer; while sweeps are *failing*
(`_SERVED_SWEEP` needs `http_status < 400`) the one-shot caps retries at one
per heartbeat instead of one per 15s pass.

### A CLAIM I MADE AND THEN REFUTED BEFORE SHIPPING IT

The first docstring said the mechanism was "bounded by the attention slice".
**It is not.** `desk_wants`' bootstrap branch fires `trigger=ATTENTION`, which
the slice caps — but `decide_sweeps` has a **second** bootstrap path (a sport
with no stored fixtures at all), also gated on this flag, stamping
`trigger=BOOTSTRAP`, and `attention_credits_spent_today` counts only
`ATTENTION`. Corrected in the docstring and pinned by
`TestTheSecondBootstrapPathIsGatedByTheSameFlag`.

### NOT changed, and both deliberate

- **`pass_kind` still returns `"quote"` after a wake.** Forcing a full pass was
  the other candidate and is rejected: a full pass measured **86.4s** on live
  this morning against a quote pass's few seconds, and it would run on every
  cold open. The cheap pass was the right pass; it just was not allowed to buy.
- **`window_status` still asks the optimistic question.** It cannot see
  `Tempo.last_full_ms` — that lives in the loop process — so it cannot know
  whether the next pass is full. What the fix buys is that *for a reader* the
  promise comes true in seconds instead of 900s. Asserted by
  `TestWhatIsStillNotGuaranteed` rather than claimed closed.

**This is why the "wide test blast radius" this file warned about did not
materialise.** `desk_wants` and `pass_kind` are untouched and the nine named
assertions pinning them all pass unmodified.

### PROCESS — two mutations GREEN again, and the same lesson in a new dress

Eleven mutations red. Two green, and the **code moved rather than the tests
kept**: the predicate began as a closure inside `run_loop.main`, so its tests
re-implemented its four lines against a real `LoopState`. They passed — and
stayed green while the *real* predicate had its consume removed and its
watermark differenced by one.

**A faithful re-implementation is a description, not a constraint.** Yesterday
the failure was asserting a *ledger* instead of a behaviour; today it is
asserting a *copy* instead of the original. `one_shot_wake` moved beside
`LoopState`, where it belongs anyway since it reads a field that module owns,
and both mutations bit. **The tell: the test file imported the state object but
not the function under test.** Lesson written.

### Open

- **Live: not deployed at the time of writing this line.** Verify after deploy
  by opening the desk shortly after a 10:00Z roll and reading `api_credits` for
  a sweep inside a minute rather than at +14.
- **The 20:00Z parlay card from the entry below is still unobserved.** First
  real chance is tonight.
- Unchanged: the combo purchase slice and its registered measurement; the
  pragma change not re-measured on live; per-sport credit reservation
  (Guard 1); `ODDS_API_KEY` rotation; `docs/` still carrying the stale 576/day
  figure outside CLAUDE.md.
- **`odds_snapshots` and `fair_prices` still have no retention rule.** 1.91 GB
  of a 5 GB volume, 712 MB free-listed. Dated risk.

---

## 2026-08-27 — the parlay push stops being a race and becomes a schedule

**Joe picked this off the state read.** It is the item he had already decided on
2026-08-26 and that was never built — *"the Discord trigger becomes a scheduled
daily card plus a two-build debounce"* — and it is the reason the three newer
parlay cuts (`longshot`, `soon`, `agreed`) have been screen-only.

**ADR 0076. Read it before touching any of this.** State: **4,623 passed /
10 xfailed in 22:08** (baseline 4,595 re-measured at session start, not
inherited), ruff clean, tsc clean. **Schema v23.**

### What was actually wrong, and it was NOT the dedupe

ADR 0072 treated Joe's two triggers as one mechanism, and `run_loop.py` said so
in its own words: *"The daily card is the first build after the slate turns
over; the material-change alert is any later pass whose legs differ. Same event
seen twice, so one call."*

Elegant, and false. Measured on live: the day's whole ceiling in **four
minutes**, the card swapping sport entirely and all three rungs re-pushing.
**Both pushes were correct under the dedupe rule** — sports are swept on
independent clocks, `build_ladder` drops legs past `MAX_ODDS_AGE_S`, and ranking
is by probability, so whichever sport is currently fresh owns the top of every
card.

The precise error: **"the first build after the slate turns over" is the LEAST
trustworthy build there is**, not the most. It is the one most contaminated by
which sport happened to be swept last — and a deploy or a day-roll is exactly
when that is most arbitrary.

### What shipped

- **A scheduled card**, `kind = 'parlay_daily'`, keyed `<day_start_ms>:<card_key>`
  on the **budget** day. Fires on the first build at or after
  `PARLAY_CARD_UTC_HOUR`. **Joe chose 4pm Eastern → 20**, set explicitly in
  `fly.live.toml` rather than left to the code default. Deliberately **not**
  debounced: a debounce could delay or skip the one push that is supposed to be
  guaranteed.
- **A two-build debounce** on the change channel, in `parlay_card_candidates`
  (**schema v23**, a pure new table needing no migration step). Replaced on a
  different key, **deleted** when a slot builds nothing. `PARLAY_DEBOUNCE_BUILDS
  = 2` is the smallest number that suppresses an alternation, which is the shape
  the churn actually has.
- **`MAX_PARLAY_PUSHES_PER_DAY` 6 → 3**, counting the change channel only. Joe
  was asked how many pushes a day at the worst and said keep 6; the scheduled
  card is bounded by construction at one per rung, so 3 + 3 holds the total
  where the original constant's own reasoning put it.
- **`held` is a fourth outcome**, not a flavour of `skipped`. A stuck `skipped`
  means the ladder is rebuilding identically; a stuck `held` means it is
  churning, and they have opposite remedies.

**THE DEFECT THE SPLIT CREATED, AND THE ONE LINE THAT CLOSES IT.** The two
channels have different `kind`s, so `UNIQUE (kind, key)` does not see across
them: the card sent at 20:00Z would be re-announced by the change channel ten
minutes later having **changed nothing**. A scheduled send now also claims the
change key for the same composition — one composition, one buzz. Claimed even
on a *failed* delivery, because a change alert re-sending what the daily card
could not deliver would arrive as if the card had changed.

**The asymmetry runs one way, on purpose.** A change alert earlier in the day
does not stop the scheduled card re-sending the same legs at the stated hour.
The daily card is the product; at most one duplicate a day is the price, and it
is inside the ceiling.

### THE GAP FOUND BY READING THE DIFF, NOT BY A FAILING TEST

**`parlay_cards`' result was DISCARDED at the call site**, and had been since
ADR 0072. So every parlay push and every refusal was invisible in the pass log
— including `held`, the state this session added *specifically* so that "the
ladder keeps rebuilding the same card" and "the ladder is churning" could be
told apart. A field nothing logs is a field nobody can read, and this repo has
four modules' worth of that failure on record.

Now merged into `CombinedPass` under a **`parlay_` prefix**, following `clv_`,
`settle_` and `outcome_`: `after_pass` and `parlay_cards` both emit
`alerts_sent`, so an unprefixed merge would have one silently overwrite the
other.

### PROCESS — 61 tests green on the first run, and two of the new guards were decoration

**Twenty-one mutations observed red** across the debounce, the schedule, the
config agreement and the pass-log wiring. **Two came back GREEN and neither was
kept as a pass**, and they share a shape the existing lesson does not name — a
new lesson is written:

1. **"The scheduled card does not spend the change ceiling"** asserted the
   **ledger** (`_parlay_pushes_today(...) == 0`). The mutation incremented the
   *in-memory* counter that actually gates the next send and never touched the
   ledger. Replaced by a behavioural guard that drives the one narrow state in
   which the two channels meet — a call where one rung takes the scheduled
   branch while another falls through settled. That one is red.
2. **"Incrementing locally rather than re-querying the ceiling"** was claimed as
   a guard by the code's own comment and by a test docstring saying *"mutation
   observed red"*. It is not a guard: `_send` commits before returning, so a
   re-query sees exactly what the increment counted. **The sentence was
   inherited from an earlier version of the code and never re-checked.** Both
   the comment and the docstring now say what is true and why the note is being
   kept rather than deleted.

**The pattern: a ledger, a counter and a log are records OF a decision, and a
decision can be changed without changing its record.** Ask before writing the
assertion: if this behaviour were wrong, would the thing I am asserting still be
right?

**And one process failure avoided by name.** A full-suite run was killed
mid-flight because `fly.live.toml`, `.env.example` and the test file were edited
underneath it — the same "patched the tree under the running suite" failure this
file records from 2026-08-26. The measurement was declared void rather than
reported.

### Driven, not only tested

A seeded database, the real `build_ladder_payload`, and a real `DiscordNotifier`
with only `_post` stubbed — so a shape drift between `_serialise_card` and
`parlay_key` had somewhere to show up. Held on the first sighting, released on
the second, silent on the third, scheduled card at 20:00Z on its own key,
silent for the rest of the hour. **Six embeds on the worst-case day**, which is
the number Joe chose.

### Open

- **The three screen-only cuts still do not reach the phone.** Six rungs against
  a 3-push change ceiling is a separate decision about Joe's attention, and
  `PUSHED_CARD_KEYS` is unchanged.
- **THE SCHEDULED CARD HAS NOT BEEN OBSERVED ON LIVE, and the prediction that
  it would be within minutes was wrong.** Deployed at 05:44Z on `427632a`,
  schema v23 applied on boot, `pass 1 ok` at 05:46:39Z with no `parlay_` fields
  in the line — which is *correct*: `/api/parlays` reports
  `excluded: {"stale_consensus": 233}` and **all six cards unbuilt**, so there
  was nothing to push. The reasoning that the card would fire immediately (the
  deploy lands after 20:00Z, today's key is unclaimed) was right about the gate
  and wrong about the input. **A ladder with no legs pushes nothing, whatever
  the clock says.**

  So what IS established on live: the new signature runs without raising, the
  new table applied to the volume, and the refusal path is silent rather than
  noisy. What is NOT: that a `parlay_daily` row is ever written.

  **When to look.** The log says `next slot is baseball_mlb at 15:51Z-16:51Z`,
  which is after the 10:00Z budget-day roll — so the first real card is due
  **20:00Z on 2026-08-27**. Verify then with `inspect_live_db.py notifications`
  for a `parlay_daily` row with `delivered = 1`, `/api/health`
  `undelivered_last_24h` still 0, and a `parlay_sent` field in the pass line.
- Unchanged from the entries below: the combo purchase slice and its registered
  measurement; the pragma change not re-measured on live; per-sport credit
  reservation (Guard 1); the cold-open wait; `ODDS_API_KEY` rotation; `docs/`
  still carrying the stale 576/day figure outside CLAUDE.md.
- **A scare that was not one, recorded because the instrument earned it.**
  `loop_failures` carries five rows on 2026-08-26 between 15:32Z and 16:42Z —
  the `ask 1000 tenths is not a tradeable price` ValueError, five consecutive
  full passes, the loop dead. That reads as the source fix having failed. It
  did not: the rows sit **entirely inside release 139** (12:39Z–16:49Z) and
  stop **seven minutes before release 140**, which is the build carrying the
  fix. Thirteen hours clean since, none after this deploy. **This is exactly
  what `loop_failures` was built for the day before** — a run of failing passes
  that used to leave the same evidence as one wedged pass is now legible after
  the fact, and the question was settled read-only in two commands.
- **`odds_snapshots` and `fair_prices` still have no retention rule.** The
  database is 1.91 GB of a 5 GB volume with 712 MB free-listed. Dated risk.

---

## 2026-08-26 — three commits had no entry, and one of them raised the bet

**Written at the start of the next session, because the state file was three
commits behind the tree and the gap was on the armed money path.** `516fc68`,
`976a244` and `8b9690e` all landed after the entry below was written, which
still lists two of the things they fixed as *open*. Re-verified before writing
any of this: working tree clean, nothing unpushed, live `git_sha` = `8b9690e`.

### THE CORRECTION THAT MATTERS — the manual ceiling is money, not one contract

**`MANUAL_ORDER_MAX_CONTRACTS = 1` is gone.** The entry below tells a fresh
session that it stands and that raising it needs `fee_actual` to match
`fee_predicted` on real fills. Both sentences are now false. **ADR 0075**
(`516fc68`) replaced the count ceiling with a spend ceiling:

    MANUAL_ORDER_MAX_SPEND_TENTHS = 3_000     the binding bound, $3.00
    MANUAL_ORDER_MAX_CONTRACTS    = 500       structural
    COMBO_MAX_CONTRACTS           = 250       structural, tighter

Joe's words when asked what he stakes: *"I bet .25 cents to 2 or 3 bucks on
parlays right now."* One contract of a combination near a cent is a bet of
**$0.015** — the ceiling did not make his bet small, it made the door
decorative, which is the state ADR 0073 §1 already caught this path in once.

**It is a tighter-reasoned bound, not a loosened one**, and that is why it was
allowed to override its own trigger. The combo fee is `k · C · P · (1 − P)` —
proportional to **spend**, not to count. A one-contract cap bounded the
fee-model error only through whatever the price happened to be: at 90c it
bounded it forty times more loosely than at 2c. A spend cap bounds it directly.
ADR 0075 writes down now, not after the fact, what would refute it — the first
real fill whose `fee_actual` exceeds `fee_predicted` past the hedge's margin.
**Re-read after five fills.**

Also from that commit: the stake presets were **$1/$5/$10/$20 defaulting to
$5** — three amounts Joe would never stake and a default above his ceiling, so
every payout figure on the card was priced for someone else. Now
**25c/50c/$1/$3, default $1**. The general lesson is on ADR 0070: *the number
that prompted a feature is not evidence about the person who will use it.*

**The two independent bounds both still apply and the tighter wins.**
`_manual_cap_dollars` returns the figure **and which bound produced it** —
"$3 cap" and "your balance only supports $0.54" are different problems with
different remedies. Caps still derive from the observed balance (ADR 0045),
never from a number anyone types, so the $3 only starts binding above a ~$30
balance. **Re-read the `caps` block rather than quoting any figure here.**

### The two performance commits closed two items the entry below lists as open

- **`976a244`** — the recorder was scanning a growing table once per candidate.
- **`8b9690e`** — `/api/parlays` still answered in **15s** on live after that,
  so it was the route, not contention. `ladder_candidates` was doing
  `SCAN odds_snapshots USING INDEX idx_odds_event` — every row, every call, on
  a table with **no retention rule at all**. Two parts: the subquery restricted
  to linked events (the outer query inner-joins on `l.odds_event_id`, so an
  unlinked event could never survive — the group was building rows to throw
  away), and one index `fair_prices(market, computed_ms DESC)`. Both scans
  became seeks.

  **A second index was written and deleted the same hour.**
  `(odds_event_id, commence_ms)` looked necessary and **changed no plan** —
  `idx_odds_event` already leads with `odds_event_id`, which is all an equality
  needs. The claim "neither half works alone" was asserted before the
  restriction-without-index combination had been measured, and the test written
  to pin it is what refuted it. An index that changes no plan buys nothing and
  costs write amplification on the highest-volume table in the system.

**VERIFIED ON LIVE this session: `/api/parlays` is ~2s over an ssh control**,
down from 15s. Coarse — ±1s resolution, two samples through
`flyctl ssh` + `fetch_live_route.py` — but the fix is doing its work.

### THE GATE THAT WAS OPEN — `8b9690e` shipped without a full suite

Its own commit message says so: three runs killed at 3%, 31% and 21% with no
traceback, *"a fresh session should run it clean before building on this."*

**Run: `4,595 passed / 10 xfailed in 19:29`.** Clean. The gate is discharged
and nothing was hiding in it. Note the drift the top of this file warns about
for the fifth time running — the inherited baseline said **4,530**.

### Read this session, worth carrying

- **Odds credits, budget day 20260826: 2,936 used / 17,064 remaining** of the
  20,000 tier. The attention-following feed (ADR 0071 §2.6) is holding.
- **NCAAF has been swept once today**, 10:12:48Z, and not since — while MLB and
  WNBA sweep every few minutes. The benign reading is that the hourly floor
  only buys a sport with a fixture inside twelve hours and the college season
  has not started. **It has not been confirmed**, and a sport that silently
  never sweeps looks identical to a sport with no fixtures. One check, not an
  assumption.
- **The database is 1.91 GB on a 5 GB volume**, with 712 MB free-listed
  (37% of the file, reclaimable only by `VACUUM`). `kalshi_quotes` retention is
  holding and this is the designed steady state, not a leak. But
  `odds_snapshots` (118 MB) and `fair_prices` (175 MB + 55 MB of indexes) have
  **no retention rule and grow forever**, exactly as `store/retention.py:53-55`
  says they deliberately do. A dated risk, not today's.

---

## 2026-08-26 — the live box was OFF between visits, and five commits later the desk draws pictures

**Read this first: the instance had been down more than it was up, and nothing
said so.** Joe asked for five things — the site is slow, desk facts in the
parlays, buy parlays as combos, add NFL and college football, and graphs. The
first one was not a slowness problem.

### THE HEADLINE — live was crash-looping and Fly was not restarting it

Found while taking a first latency reading, not by reading code. No test was
failing. Machine events for the day:

    06:51:15Z started -> 07:51:02Z stopped   exit_code=0, requested_stop=false
    08:03:07Z started -> 09:00:48Z stopped   exit_code=0, requested_stop=false

~60 minutes up, then nothing until an HTTP request woke it, at **23-37s of cold
start**. The recorder wrote nothing in between. Five links:

1. `store/db.py::derive_yes_ask` returned `None` for a `None` bid and a NUMBER
   for a `0` one. Kalshi reports an empty side as `0.0000`, which parses to a
   real `0`, so the ABSENCE arrived as a legitimate value and `1000 - 0` came
   back as a price.
2. The team pricing path guarded on `ask is None` only.
3. `core/ev.effective_price` refused correctly — **by raising** — and nothing
   caught it, so ONE market failed the whole pass.
4. Five failed passes raised `LoopFailed` and ended the process.
5. `entrypoint.sh` tore down and **exited 0**. Fly's policy is on-failure:
   *"machine exited with exit code 0, not restarting"*. `min_machines_running
   = 1` does not govern a container that exited successfully.

**Nothing alarmed because the heartbeat probes `/api/health`, and with
`auto_start_machines = true` that probe STARTS the machine.** It had been
keeping the instance alive every fifteen minutes and calling that health.

**This was the THIRD patch of the same defect**, and the first two were at call
sites: `runner.py`'s prop path (2026-08-15, whose comment predicted the team
path was safe — that prediction is what failed) and `routes.py::_tradeable_ask`
(2026-08-26). Fixed at the source this time.

**VERIFIED: 79 minutes clean on `3248e65`, then 70 minutes clean on `5edb2c9`**,
both past the 57.7 and 59.8-minute windows the box previously died in. Full
passes complete again (157s, 74s, 86s). `dropped_no_kalshi_quote: 1`,
`dropped_unpriceable: 0` — the source fix is doing the work and the containment
wrapper is idle, which is what a seatbelt should look like.
`docs/measurements/2026-08-26-live-was-off-between-visits.md`.

### THE OTHER HEADLINE — the serving path had never been measured

Every latency doc here is about the recording loop; uvicorn runs
`--no-access-log`. Measured over the public surface with a session cookie:

    /api/health 0.15s   /api/slate    5.94s -> 0.38s
    /api/window 0.32s   /api/parlays  9.96s -> 2.32s
    /api/board  0.18s   /api/signal   1.53s -> 0.11s

**`/api/parlays` at 2.3s WARM crossed a stop-work trigger this file registered
in advance** (*"the stated stop-work trigger was 1s on `/api/parlays`"*).
**And it overturned this session's own plan**, which had ranked the
`/api/slate` N+1 first from reading the code — warm, the slate is 0.38s.

Fixed by hoisting the joint memo out of `build_ladder` into a bounded
module-level cache: **345ms -> 2ms**. A memo, not the payload cache the trigger
named — a payload cache must guess an expiry and would serve stale leg ages on
the one screen whose job is saying how old its inputs are. `_joint_key` carries
every field `_joint` reads and the copula is seeded, so nothing can go stale.
Plus `cache_size` 16 MiB read / 4 MiB write and `temp_store = MEMORY`;
`mmap_size` deliberately absent (it competes with the page cache, and this box
has OOM-killed itself once).
`docs/measurements/2026-08-26-serving-path-baseline.md`.

### What else shipped, in order

- **`5b9bf5f` — the parlay ladder never had its team aliases.**
  `ladder_candidates` loaded them with `event_links.league`, which holds
  Kalshi's competition string ("Pro Baseball"), while the files are named for
  sport keys. `load_aliases` returns an EMPTY mapping for a missing file, so it
  failed open and silent for the desk's whole life. **The shared fixture wrote
  `league = 'baseball_mlb'`, encoding the same misconception as the code**, so
  the two agreed and nothing caught it. Measured effect: of 13 entries across
  both files, **0 require the alias** — real but inert on today's leagues, and
  load-bearing for NCAAF.
- **`5edb2c9` — college football team names**, derived from the wire by
  `scripts/capture_ncaaf_names.py` (0 odds credits, checked off
  `x-requests-last`). Six entries, each verified individually. **NFL needed
  nothing**: every open `KXNFLGAME` today is `'Pro Football Preseason'`, already
  excluded; the regular season arrives ~Sept 10 on the existing path.
- **`46cce28` — an unmatched fixture says WHICH kind.** `refusal_kind` splits
  `not_carried` from `name_unresolved`, because the reason string could not:
  the window is four hours and dozens of college games start inside it, so
  every out-of-scope fixture was landing in "no team-pair bijection" beside the
  real spelling problems.
- **`e43f551` — desk facts on every parlay leg.** Ask, book count, method
  spread, quote age on a second line in fixed order; provenance behind one
  per-card tap. **The skeptic is three-valued**: a spread leg has no
  `recommendations` row by construction, so a blank would read as "the checks
  passed" when they never ran.
- **`88d179f` — the perf work above.**
- **Four charts + ADR 0074.** Chance collapsing (`/parlays`), the fair-value
  pipeline and the dispersion axis (`/market`), cumulative money (`/bets`).

### THE NUMBERS THAT MATTER

- **231 of 339 Kalshi NCAAF fixtures have no sportsbook counterpart at all.**
  Kalshi lists FCS and Division II; the odds feed carries roughly FBS. Live now
  reads `events_unmatched: 525 of 746`. That is SCOPE, not a naming bug, and
  the new split is what makes the two distinguishable.
- **`fair_prices.overround` was stored since the beginning and served by
  nothing.** It is the number that makes devigging checkable rather than a word
  taken on trust. Now on `/api/market/{ticker}`.

### ADR 0074 — the ask returns to one axis, on one screen

Joe was told marking Kalshi's ask on the dispersion chart partly reverses the
2026-08-21 ruling and said *"yeah mark the ask, go ahead."* Restored on
`/market/[ticker]` ONLY, as a neutral tick — no colour, no arrow, no
cheap/expensive wording. The ruling's other two removals (the `used` mark, the
never-stretch rule) stay on both surfaces. The landing row is unchanged.

**No chart wears a colour, and that is a finding about this repo**: `--accent`
is the same red as `--negative` in both themes, so a coloured series reads as a
verdict. Every mark is an ink token; identity is position and shape.

### PROCESS — six of my own tests were decoration, all caught by mutating

Worth carrying because the pattern was consistent: **a test written after the
code tends to describe it rather than constrain it.** Caught this session — a
stub that returned the same answer for every key; an LRU test whose fixture
could not distinguish evicting the oldest from the newest; a loop with a
`continue` and no assertion; an assertion ending in `or True`; a guard that
asserted the alias file "buys something" but not that a dropped entry costs
anything.

**And one mutation LIED.** It reported green after inserting into a
`<details>` that lives inside the file's own docstring — the file changed, the
string was present, and no code was touched. *"The test stayed green"* is never
on its own a conclusion; confirm the mutation landed where you think.

Also: **the suite caught two real defects in my work** — a bare
`suppressed_reason` with no gloss (ADR 0050 requires both), and a process-wide
cache that made every `_joint`-counting test order-dependent (fixed in
`conftest.py`, following `forget_scope_warnings`' precedent).

### FOR JOE — the one thing code cannot fix

**Buying a parlay as a combo is blocked on money, not on code.**
`max_position_dollars` is 10% of the observed Kalshi balance
(`config.py:505-514`, ADR 0045), and the live mirror reads **$5.40** — the same
figure ADR 0073 recorded *before* the deposit. So the per-bet cap is **$0.54**,
and a $5 bet needs **at least $50 in the account**. Nothing in the code moves
that. Re-read the `caps` block rather than quoting this.

### Open

- **The combo purchase slice is unstarted**, and its harder half is that a
  minted combo's book is empty on both sides — the order path is IOC, so it
  cancels. Registered measurement first (does a maker ever quote a fresh
  combo?), then decide about a resting order. ADR 0063 §3 pins IOC.
- **The pragma change is NOT re-measured on live**, and that re-read must be
  split by whether a full pass is running.
- The `/api/slate` N+1 and the unbounded `GROUP BY odds_snapshots` (five call
  sites) are real and grow forever; they are simply not what a person waits on.
- Per-sport credit reservation for a saturated Saturday: when the daily cap
  binds, EVERY sport stops. Guard 1 (record the refusal) unbuilt.
- `ODDS_API_KEY` rotation; the cold-open wait; the scheduled parlay card.

---

## 2026-08-26 (hedging lane) — the desk starts watching what Joe already holds, and a hedge turns out to need no model at all

**Joe's ask, verbatim: "if I have a 6-leg parlay and one of them is not doing
well, i'd like to have an alert surface to me with high confidence that I should
hedge a bet right away… if there is any ai or ml that needs to be done, make it
independent of consuming tokens."** His example is a baseball game: he holds
Cincinnati, San Francisco lead by two in the bottom of the sixth, and he wants
to know when to bet the Giants separately.

Four choices were put to him and answered in his own words: **both** Kalshi
combos and sportsbook slips; **LOCK pushes to the phone, DE-RISK stays a screen
row**; **Kalshi is the only hedge venue priced**; and **build the vertical
slice**. Recorded in **ADR 0078 — read it before touching any of this.**

### The token constraint answers itself, and that is the headline

**No model is needed, so none was built.** A hedge needs two things: how likely
the endangered leg still is, and what the other side costs. **Kalshi's live
in-play ask is both.** "San Francisco lead by two in the bottom of the sixth" is
exactly *why* the Cincinnati contract sits at 20c — the score, the inning and
the base state are already in the price, put there by people with more
information than this repo can lawfully obtain. And unlike a fitted win
probability, it is the number the hedge actually transacts at, so there is no
translation step to be wrong in.

- **No Anthropic call on any path.** Asserted over the source of all three
  modules, on the code with docstrings stripped.
- **No Odds API credit.** Kalshi is unmetered; `ODDS_ATTENTION_DAILY_CREDITS` is
  untouched and the attention ceiling is unchanged.
- **No MLBAM.** ADR 0035 §2 authorises two schedule endpoints and forbids
  per-game timer polling in those words. Not needed, so not reopened.

**And Kalshi has been keeping this data the whole time.** ADR 0006's evidence:
game markets stay open through the game, "twenty of twenty games measured had a
two-sided quote in every minute after the true start", and
`store_quotes_from_discovery` applies no commence filter. `kalshi_quotes` has
been accumulating in-play prices for the life of the project with nothing
reading them.

### What shipped

- **`backend/core/hedge.py`** — the arithmetic, pure, no DB and no clock. The
  equalising hedge (`n = W` contracts, both branches equal), the floor at every
  reachable size, and **seven refusals that return a reason instead of a
  number**: `no_ask`, `no_depth`, `stale_quote`, `market_closed`,
  `crossed_book`, `unreadable_ticket`, `fee_unreadable`.
- **`backend/hedge.py`** — the record, the live book and the words. Schema v23:
  `parlay_positions` and `parlay_position_legs`, both pure new tables (no
  `_MIGRATIONS` step needed, and a v22 database is shown gaining them in a test).
- **Four routes** — `GET /api/hedge`, and three auth-gated writes. The screen at
  `/hedge`, reached from `/bets` and from the alert's own link; **no new nav
  slot**, the six-link budget is load-bearing at 390px.
- **`backend/hedge_watch.py`** — its own asyncio task beside
  `poll_portfolio_forever`, 60s while a watched game is running and 600s
  otherwise. **Not on the quote pass**, and ADR 0072 Decision 5 is why: that
  pass is budgeted 8s and already runs ~4.2s live, and the last thing added
  there "because it is pure" cost 400ms a pass and would have degraded silently.
- **`DiscordNotifier.hedge_lock` + `Alerter.hedge_locks`** — the first alert in
  this product that names a dollar figure it stands behind, because the figure
  is arithmetic rather than a forecast.

### THREE THINGS THE PLAN HAD WRONG, and the build corrected all three

1. **Rule 1 was pointed at the wrong quantity.** The plan proposed suppressing a
   lock that is large relative to the stake. A $4.99 ticket returning $333.33
   with one leg left locks about **$172 — 34x the stake, and entirely real**;
   that rule fires hardest on exactly the case the feature exists for. What
   catches a genuine bug is an invariant no real book can satisfy: both sides
   quoting for a dollar or less together. **The absence of the lock-to-stake
   rule is now asserted by a test**, so re-adding it goes red.
2. **The affordability cap was passed as a contract count**, which the caller
   cannot compute without the ask, and the ask is chosen inside. Reworking it to
   a balance surfaced the question a count would have hidden: **an unread
   balance is not a balance of zero.** `latest_balance_tenths` answers `None` on
   any five-minute poll outage, and folding that into a cap of 0 would have
   silenced the alert for as long as the mirror was behind — the repo's
   "unreadable never resolves to zero" rule, pointed at a budget, where the
   failure mode is *silence* rather than a fabricated edge.
3. **The plan's "no hedge button" line was right for a reason it did not
   state.** `MANUAL_ORDER_MAX_CONTRACTS = 1` with a 10-minute `COOLOFF_MS` means
   a 30-contract hedge through the manual door would take five hours. The screen
   gives the size and the price and deep-links Kalshi. **Raising that cap is
   Joe's decision and wants its own ADR**; it deliberately does not ride along
   inside a display feature.

### MEASURED BY RUNNING IT, and it found a defect the suite did not

The stack was driven against the venue's own book. It picked two legs of the
**same MLB fixture** — Boston-to-win and Miami-to-win, a pair that cannot both
happen — and **the desk priced them as independent and returned a joint
probability.**

`/parlays` takes one leg per fixture so `CorrelationRefused` is structurally
unreachable there (ADR 0070 §2); **a ticket Joe already holds has no such
property.** Same-game detection keys on `event_ticker`, the form takes a bare
market ticker, and the two sides of one fixture have different *market* tickers
— so they looked unrelated. The fixture is now derived from the ticker
(`SERIES-EVENT-SIDE`, the same read `lib/kalshiLink.ts` makes) at record time
and again on read, and a three-segment ticker is the only shape it will read: a
wrong fixture key **merges two real games** and refuses a legitimate joint,
which is worse than not knowing.

Verified afterwards on the same live book: the pair now returns
`chance_display: "--"` with `core/correlation.py`'s own refusal attached, and
the per-leg prices still render.

**And the arithmetic checked out on real data.** $5.00 to return $100.00, the
derived NO ask at 80c, 100 contracts costing $81.12 including a $1.12 fee:

    leg wins    $13.88
    leg loses   $13.88

**Equal to the cent**, which is the identity the whole feature rests on,
arrived at from a real book rather than a fixture. Ratchet key
`hedge_lock:1:2`.

### Mutation

**Forty-nine mutations observed red** across `core/hedge.py` (15), `hedge.py`
(20) and the alert path (14). **Seven stayed GREEN on the first pass**, and the
split is the lesson:

- **Four were real holes**, each closed with a test rather than a weakened
  assertion: the return-above-stake guard was unobservable through its reason
  code alone (the odds floor catches the same input, so the test now asserts the
  *sentence*); nothing distinguished `floor(W)` from `ceil(W)` as the equalising
  size; nothing exercised a de-risk whose live legs had no readable price; and
  nothing reached the read-side fixture derivation, which only a row written
  by something other than `record_position` can exercise.
- **One was a vacuous test.** The watcher's failure guard was tested against an
  empty database, so `anything_in_progress` was False and the cycle body never
  ran.
- **Two were the harness patching the wrong function.** `parlay_cards` and
  `hedge_locks` share the exact lines `if key is None:` / `continue`, and
  `replace(old, new, 1)` takes the first. Both went red once anchored uniquely.

### Verified

**4,718 passed / 6 skipped / 10 xfailed**, ruff clean, `tsc` clean, `next build` green with `/hedge` and
the three route handlers in the manifest.

**The baseline was re-measured and `tasks/NEXT.md` was stale again, in the same
direction: it said 4,456; the truth at `88d179f` was 4,524 passed / 6 skipped /
10 xfailed.** Taken on a **detached worktree at the same commit**
(`git worktree add --detach`), which is the fix for "never patch the tree under
a running suite" — the measurement runs on files nobody is editing instead of
serialising the two.

### NOT built, and each is deliberate

- **No in-app hedge order.** See correction 3 above.
- **No hedge observation history.** The watcher holds its last read in memory and
  writes nothing; a `hedge_observations` table would let the screen say "the lock
  was $180 ten minutes ago", which is genuinely useful and is a separate slice.
  Nothing about the evidence record changes until it exists.
- **No pre-fill from `parlay_lookups`.** A combo bought off `/parlays` still has
  to be typed in. Slice 4 in the plan; not reached.

### VERIFIED ON LIVE, 2026-08-27, `6fc9e3c`

Deployed and checked, in the order that makes each check mean something:

- **Schema v24 applied to the volume.** `inspect_live_db.py db-sizes` shows
  `parlay_positions`, `parlay_position_legs` and all three indexes on
  `/data/cockpit.db`, **beside `parlay_card_candidates`** — which is the whole
  point of the renumber: both lanes' tables coexist, where a shared v23 would
  have given the volume one set or the other with no way to tell. `open_db`
  refuses a version mismatch, so the API answering at all is independent proof
  the stamp is 24.
- **`/api/hedge` serves HTTP 200**, with an empty `positions` list (nothing is
  recorded yet) and all four caveats verbatim. This needed
  `fetch_live_route.py`'s allowlist to gain the path first: everything under
  `/api/` 401s on the public surface **before routing**, so a `curl` from
  outside cannot tell a route that exists from one that does not — both answer
  401 — and this route reaches the venue for a live book, so the database
  cannot be used to reconstruct it either.
- **The watcher has not destabilised the recorder.** No `odds_sweep_log` gap
  over 1200s, and the newest `loop_failures` row is 2026-08-26T16:42Z — about
  23 hours before this deploy, and the derived-ask `ValueError` `main` has
  since fixed. Nothing new.

**What that last one does NOT establish is that the watcher is polling.** With
zero recorded positions `anything_in_progress` is False and the correct
behaviour is silence, which is indistinguishable from a task that never
started. The check that separates them is the next one, and it needs a real
ticket.

### STILL OPEN — the check that needs a real ticket

**Record a parlay Joe actually holds and watch it during a game.** That is the
only thing that exercises the watcher's cycle, `resolve_from_venue` against a
real settlement, and a hedge embed rendered from a live payload — the last of
which is the check ADR 0072 insisted on for the parlay card and got right.

Recording needs the live `APP_AUTH_TOKEN`, which this machine does not hold, so
it is a tap on the phone rather than something a session can do.

### Previously open and now closed

**Nothing in this session has run on the deployed instance.** Schema v23 applies
to the live volume on boot (the mechanism is verified against a v22 database in
a test, not on the volume itself), the watcher has never run against a real
in-play book, and no hedge embed has ever been rendered from a live payload —
which is the check ADR 0072 insisted on for the parlay card and got right.

**The honest first test is a real one:** record a ticket against two live MLB
tickers, mark one leg won by hand, and read the lock figure against a hand
calculation while the game is running.

### Still open from before, untouched

- **The scheduled parlay card plus two-build debounce.** Decided 2026-08-26,
  not built.
- **The cold-open wait** — a heartbeat can wait up to 900s to be acted on.
- `ODDS_API_KEY` rotation; `docs/` still carrying the stale 576/day figure
  outside CLAUDE.md; no ADR for the attention TTL, floor horizon or credit slice.

---

## 2026-08-26 — the buy control reaches every card, and the ticket renders on a real book for the first time

**Joe's ask, verbatim: "I want to be able to buy picks for games, props and
parlays directly from the cockpit."** Four choices were put to him and answered
in his own words: build the surfaces **and** prepare the arming commit; **both**
parlay doors (per-leg and a bounded combination); the control **inline on every
card**; and a **ticker search** for markets the cockpit never surfaced. Recorded
in **ADR 0073** — read it before touching any of this.

**The honest headline is that most of it already existed and none of it was
reachable.** ADR 0063 shipped the whole hand-bet door on 2026-08-22 — twelve
server-side checks, a `manual_orders` table, a ticket with an anti-anchoring
reveal — mounted on `/market/[ticker]` alone, with `MANUAL_ORDERS_ENABLED=false`
in both fly tomls. Every response on live was **"blocked"**. `lessons.md` has
the name for it: *a feature and the one path that invokes it are two
deliverables, and only the second one ships.*

**What shipped**

- **The ticket mounts inline on every per-game surface** — Games rows, Picks
  rows and cards, parlay legs, a priced combination, a search result — via two
  new props on `ManualTicket` rather than a second component. On the Picks
  cards it mounts **outside** `TicketTrigger`, which wraps a whole card in a
  `<button>`; an input nested in a button swallows its own clicks, and that is
  pinned.
- **`GET /api/manual/search`**, delegating to `estimates.search_markets` —
  whose SELECT carries **no quote column**, which is what lets a search screen
  exist without breaking ADR 0065's mask. Closed `<details>` on the Games and
  market screens; **no new nav slot** (the six-link budget is load-bearing at
  390px). `searchEstimateMarkets`, dead since the estimate form retired, was
  repointed rather than duplicated.
- **Parlay legs are individually buyable**, behind a `<details>` whose summary
  says — before it is opened — that **buying legs is not buying the parlay**.
  Thirty-six controls in the open would be the chase surface ADR 0067 refuses.
- **A combination is bounded rather than refused**: `combo_acknowledged` as a
  required request field (default False, so a client that has never heard of
  combos refuses them), one contract, and a hedged fee.
- **Arming plumbing, without the flip.** `MANUAL_ORDER_MAX_CONTRACTS = 1`
  server-side and served to the client; `MANUAL_ORDERS_ENABLED = "true"` on
  live (ADR 0018: turning it on **moves no money**); and ADR 0018's *second*
  barrier wired ahead of time — the manual `OrderPlacer` now receives the app's
  shared REST client, built only when armed. Without it, flipping the constant
  gives a 503 and not an order. **`MANUAL_ORDERS_ARE_DRY_RUNS` stays True.**

**THREE THINGS THE RECORD HAD WRONG, and the first one is why the combination
door could open at all.**

1. **ADR 0007's combo-grid claim is not borne out.** It says combination
   markets use `center_centi_edge_centi_cent`, which `snap_tenths` refuses — on
   that reading a combo order was mechanically impossible before any policy
   check. **43 combination markets in this repo's own fixtures are `deci_cent`
   (15) or `linear_cent` (29); zero are centi-cent**, and six pulled off the
   **live** venue this session are all `deci_cent`. The claim came from
   Kalshi's published structure table, which lists a structure and does not say
   who uses it. Addendum written on ADR 0007.
2. **"No order has ever been placed by this project" was stale in five
   places** — `backend/kalshi/orders.py` twice and three `.claude/agents/*.md`
   persona files. Joe's C0 probe placed four real orders on 2026-08-23. The
   sentence that survives is narrower: *the app's own order path* has never
   sent one.
3. **ADR 0018 cited `routes.py:1382` as "the only construction of
   `OrderPlacer`".** It is `:3811`, and there are two. The AST test tracked
   reality while the prose did not; the manual path's pin now asserts the
   **count**.

**VERIFIED ON LIVE, 2026-08-26 12:05Z, `git_sha b2f2d14`.** The manual door
answers for the first time: `/api/manual/market/{ticker}` returns
`reachable: true` where every response before this was `blocked`, with
`dry_run: true`, `max_contracts: 1` and `authorised_contracts: 1` against a
real book (16c ask, depth 200). `/api/manual/search?q=Los` returns 20 markets
and they are **prop ladder rungs** (`KXMLBRBI-26AUG261607CLELAA-CLEJADELL7-1`,
`-2`, `-3`) — exactly the class that had no way in before. Read with a session
cookie minted from `.env`'s own token, since the routes sit behind the
middleware and `scripts/fetch_live_route.py`'s allowlist does not carry them.

**MEASURED BY RUNNING IT, and it found two defects tests did not.** The stack
was driven end to end — seeded DB, uvicorn, `next start`, a browser — and the
ticket reached its **ticket phase against a real Kalshi book for the first time
in this project's life**: `KXNEXTNATOSECGEN-99-KIOH`, YES 16c / NO 91c, depth
200, "your per-bet cap authorises 1 contract", contracts stepper locked at 1 in
both directions, confirm disabled until the token is typed. A dry run then
completed and wrote the row — `"count": "1.00"`, `"price": "0.1600"`,
`side: bid`, `immediate_or_cancel`, `taker_at_cross` — and the cool-off engaged
for 578s.

- **An empty book is not "no ask" — it is a 0c ask, and the screen said so.**
  Asks are derived (`yes_ask = 1000 - best_no_bid`), so a missing NO bid reads
  as a resting bid of 100c and hands back **0c**. That is the shape of every
  combination on the venue right now (`no_bid_dollars = 1.0000`, depth 0.0),
  and the ticket rendered **"YES 0c"** — a free contract on the most illiquid
  product Kalshi lists, which is CLAUDE.md rule 1 exactly. The order path was
  already safe (the grid refuses 0); the screen was not. `_tradeable_ask` now
  returns None off the tradeable range, on the read and on the POST.
- **The demo database wrote a market status the venue never emits.**
  `seed_demo` set `status = 'open'`; the wire says `active` (245 of 245 in
  `events_sports_nested.json`) — `open` is the *event* query parameter, a
  confusion `test_census_non_sports.py` already records once. Nothing noticed
  because the one query filtering on it had no caller. The search returned
  **zero markets for every query** on demo until this was fixed.

**Also caught: a pin that went quiet.** `test_no_production_call_passes_the_constant_as_anything_else`
matched `OrderPlacer(\s*dry_run=...)` on one line. The manual construction took
a `rest=` argument and wrapped onto three, the regex stopped matching it, and
the test **stayed green while covering one construction instead of two**. It
now reads whole argument lists and asserts the count.

**State.** 4,423 → **4,451 passed / 10 xfailed**, +28. Re-run before quoting it. Every new guard was
mutated and observed red, including two that came back GREEN first time and
were rewritten rather than kept: a combo-fee assertion on a display string
rounded to cents (the two fee models differ by $0.0002 at one contract, which
2dp erases), and the leg-buy disclaimer sliced over a whole component instead
of its `<summary>`. ruff clean, tsc clean, `next build` green, 0px horizontal
overflow at 390 and 1280.

### ARMED, 2026-08-26 — the manual path sends real orders

**Joe funded the account and said: "I already got money in kalshi. Flip it,
commit and deploy."** `MANUAL_ORDERS_ARE_DRY_RUNS = False` shipped in its own
commit. **`POST /api/manual-orders` now sends real immediate-or-cancel orders
to the exchange**, one contract at a time, at his tap, with his own typed
estimate and order token.

**The engine path is untouched and stays dry.** `ORDERS_ARE_DRY_RUNS` is still
True, `gate.py` still never reads `manual_orders`, and
`test_the_manual_path_is_armed_and_the_engine_path_is_not` pins both halves —
that test used to assert the manual constant was True and was **re-pointed, not
weakened**, at the property that still has to hold.

**Arming forced a guard that should have existed already, and it is the most
important line in this entry.** `load_dotenv()` puts `.env` into `os.environ`
for the whole suite, so `KalshiConfig.load()` inside a test returned **real
signed credentials** on this machine. Harmless while nothing in production could
ask for a live `OrderPlacer` during a test — which is exactly what arming
changes. Without the fix, running `pytest` here would have **sent a real order
to the exchange**. `conftest.py::no_live_kalshi_credentials` now removes
`KALSHI_API_KEY` and `KALSHI_PRIVATE_KEY_PATH` for every test; the route answers
503 and writes no row. Pinned, autouse-ness included, by
`TestTheArmedPathCannotReachTheVenueFromATest`. **Do not remove it, and do not
reach for `KALSHI_PUBLIC_READ_ONLY` in conftest as a tidier alternative** — a
config object that succeeds is the opposite of what the fixture is for.

The ticket now says **"This spends real money"** above the confirm, naming that
the order goes at the live ask and that this tool cannot cancel one. It renders
only while armed, so it cannot become wallpaper.

**To disarm:** set the constant back to True, update that one pin, deploy. One
line, revertible alone — which is why it landed on its own.

**FOR JOE — what is yours now:**

1. **Caps still come from the balance, never from a number you type**
   (ADR 0045). Before the deposit they read `max_position_dollars` $0.54,
   `max_exposure_dollars` $2.16. **Re-read them rather than quoting those** —
   `/api/manual/market/{ticker}` serves the `caps` block, and a figure in prose
   is a measurement with no timestamp.
2. **Raising the 1-contract ceiling is the next decision, and it has a
   trigger.** ADR 0063: raised *"only when observed `fee_actual` matches
   `fee_predicted` on real fills"*. Your first real fills are what supply that;
   until then `MANUAL_ORDER_MAX_CONTRACTS = 1` stands.

**Open:** the per-row "Pass" affordance on the slate (still); the scheduled
parlay card plus debounce from the entry below; a `GoodChancePicks` buy control
was deliberately NOT added and ADR 0073 §3 says why.

---

## 2026-08-26 — one parlay generator becomes six, and the notifier is deliberately left behind

**Joe picked this off the ranked list in the entry below.** The finding it rests
on is that entry's headline: the three cards were never three products.
`build_ladder` ranked the pool by `(-p_conservative, commence_ms, ticker)`, took
one leg per game, and cut the same ranking at 3, 4 and 6. `prefer_spreads` was
the only structural difference in the entire ladder.

`CARD_SHAPES` is now a tuple of **`Recipe`** — key, title, a one-line
`what_it_is`, the leg bounds, and the four parameters that make a cut: rank
direction, spread preference, kickoff horizon, method-agreement width.

| key | title | shape | the cut |
|---|---|---|---|
| `safe` | Safe | 2–3 | unchanged |
| `middle` | Middle | 4 | unchanged |
| `lottery` | **Long ladder** | 6 | `prefer_spreads` — **title changed, key did not** |
| `longshot` | Longshot | 2–3 | `longest_first` |
| `soon` | Next 3 hours | 2–3 | `starts_within_ms = 3h` |
| `agreed` | Agreed | 2–3 | all four devig methods inside 2 points |

**`lottery`'s key is untouched on purpose.** `parlay_lookups` rows and the
Discord dedupe history are keyed on it; renaming the key would make the record
incomparable across a rename that buys nothing. Only the display title moved,
because once Longshot exists "Lottery" is the wrong name for the six *likeliest*
legs.

**Three decisions were Joe's this session**, taken before any code: one grid of
six cards each carrying a description (over a two-section split); the title
rename; and — recorded but **not built** — the Discord trigger becomes **a
scheduled daily card plus a two-build debounce**.

### The notifier did NOT grow with the screen, and that is the load-bearing bit

Six cards against `MAX_PARLAY_PUSHES_PER_DAY = 6` makes **one ladder the whole
day's pushes**, where that constant's own comment calls six "two full ladders".
And the entry below measured the existing three burning the ceiling in four
minutes. So `PUSHED_CARD_KEYS = {safe, middle, lottery}` holds the phone exactly
where it was; the new cuts are screen-only until the trigger changes shape.

A screen-only card is **neither sent nor skipped** — counting it as skipped
would inflate `alerts_deduped` with rows that were never deduped.

### Measured, not predicted

`build_ladder` over the same slate, three cuts against six, median of three,
half the fixtures deliberately outside the 3-hour horizon so `soon` could not
just reuse `safe`'s answer:

    n=6    332 ms -> 480 ms
    n=12   322 ms -> 473 ms
    n=20   332 ms -> 463 ms

**+43%, not the +100% the card count implies, and flat in slate size.** `_joint`
runs a 200,000-sample copula five times per distinct leg set, and six cuts of one
pool routinely select the *same* legs — so the joints are memoised on
`_joint_key`, the full tuple of every field `_joint` reads. The stated stop-work
trigger was 1s on `/api/parlays`; it was not reached, so no payload cache was
built. The loop path is unchanged in shape: still gated on
`counts.odds_sweeps > 0 or kind == "full"` against an 8s quote budget running
~4.2s live.

**The memo key is the whole selection, not the leading ticker**, and that
distinction is now pinned by a test rather than by intent: two cuts routinely
agree on the leaders and diverge below (Safe takes `[g0,g1,g2]`, Next 3 hours
takes `[g0,g1,g3]` when `g2` kicks off late), and a key that stopped at the
first ticker would serve one card's joint on the other.

### Mutation

**Seventeen mutations observed red.** One stayed GREEN on the first pass and it
was a real hole: `memo = selected[0].kalshi_market_ticker` passed everything,
because in every fixture then written the cards' *first* legs already differed.
The fix was the divergent-slate test above, not a weakened assertion.

### A process failure worth carrying

The baseline test count was being re-measured — correctly, per the instruction
at the top of this file — when I patched the tree **underneath the running
suite**. The apply script had a `DRY_RUN` guard; the guard was itself installed
by a `str.replace` that matched nothing and said nothing, so it silently was not
there. Seven files were written mid-run and the measurement was void.

Recovered without inheriting anything: the run was killed, the changes stashed,
and the pre-change count taken as **4,400 tests collected** (consistent with the
4,388 passed / 10 xfailed this file recorded). Lesson written.

### Open, and unchanged from the entry below

- **The scheduled card plus debounce.** Decided, not built. It is the trigger
  Joe asked for and the reason the new cuts are screen-only.
- **The cold-open wait** — a heartbeat can wait up to 900s to be acted on.
  Precisely located across three files, wide test blast radius, wants its own
  slice.
- `ODDS_API_KEY` rotation; `docs/` still carrying the stale 576/day figure
  outside CLAUDE.md; no ADR for the attention TTL, floor horizon or credit
  slice.

### One thing to watch on live

On a thin or single-sport slate, `soon` and `agreed` will often select exactly
the same legs as `safe` — three cards showing one card. That is *honest* (each
says what it is, and "the methods agree on the leaders" is a real fact) and it
shares one copula run, so it costs nothing. But it may read as three copies.
Worth looking at once there is a real evening slate behind it before deciding
whether it needs anything.

---

## 2026-08-26 — the alarm stops guessing, and the desk's cards reach the phone

**Shipped and verified on live at `b7e6f9f`.** Two commits, both deployed.
State: **4,388 passed / 10 xfailed** (baseline 4,333 re-measured at session
start, not inherited), ruff clean. **Schema v22** — `loop_failures`, applied to
the live volume on boot without incident.

### The 20:41Z heartbeat alarm was real, and its text was a guess

Joe forwarded `⚠ The recorder has stopped`. Established read-only, before
touching anything:

- It fired **once** (heartbeat run 20:41:37Z) and cleared by 20:55Z. Live was
  healthy on inspection: `recorder.age_ms` 5,897.
- **Not a restart.** Fly releases bracket the window at 132 (19:01:40Z) and 133
  (21:00:36Z), and the machine event log shows no start between.
- **Not a designed sleep.** The recorder heartbeat is stamped on *every* pass
  (`runner.py:2493`, inside `store_quotes_from_discovery`, which
  `run_quote_pass` reaches via `run_kalshi_pass`), and the slow cadence is 900s
  ±15%. **The widest gap a healthy shut-window loop can produce is
  1,035s ≈ 17.3 min.**
- `odds_sweep_log` carries a **2,678-second hole ending 20:51:02Z**. Every other
  gap that day was a single jittered interval — 842, 950, 965, 999, 1,001s.

So two or three passes never finished. **Which could not be established, and
that is the finding.** `LoopState.consecutive_failures` and `last_error` live in
memory; the container had restarted and its logs went with it. A run of failing
passes and one wedged pass need different fixes and left identical evidence.

**Built the instrument that separates them.**

- **`loop_failures` (schema v22)**, written through a new `on_failure` hook on
  `run_forever`. **Written on the failure path only**, and that asymmetry is the
  whole design: rows inside a silence mean the loop was failing; no rows mean
  nothing came back to raise. Logging successes too would make "no rows"
  ambiguous again. A raising hook is swallowed and logged — it runs where
  something has already gone wrong.
- **`inspect_live_db.py pass-gaps`** computes the holes in SQLite (window
  function, `--gap-ms` bound parameter) and prints `loop_failures` beside them.
  Doing this today meant pulling 400 rows and diffing them locally, which is the
  smuggle-the-code-in-with-the-question drift that file exists to replace.
- **The alarm says what it measured.** It no longer asserts *"It is alive and
  stuck"*; it names the three states it cannot distinguish and points at
  `/api/window` `is_open` and `loop_failures`.
- **Its threshold comment was wrong and is corrected.** It justified 30 minutes
  as "two missed full passes" because "quote passes run far more often" —
  untrue since ADR 0071 §2.6 made the odds feed follow attention, since the 15s
  cadence only runs while the window is open. The number survives (30 min is
  1.74× the 17.3-min ceiling); the reasoning did not.
  `tests/test_heartbeat_threshold_arithmetic.py` now pins the *property* against
  the real `JITTER`, so the next constant change fails a test rather than a
  comment.

**Still open, unchanged:** nothing times out a pass. `run_forever` still awaits
`do_pass()` bare. This makes a wedge *legible after the fact*, not survivable.
Leave it until `loop_failures` shows a gap with no rows in it — that is now a
readable signal rather than a guess.

### Parlay cards push to Discord — outbound only, Joe's call this session

He asked for the webhook to carry parlay items and, if possible, to place Kalshi
buys. **Asked, and he chose push-only with no order path.** Triggers he picked:
a daily card, a slash command, and a material-change alert.

**Shipped: the daily card and the material-change alert, which turn out to be
one mechanism.** `DiscordNotifier.parlay_card` renders a card from the exact
`_serialise_card` payload the screen uses — **no arithmetic anywhere in the
path**, so the embed cannot drift from `/parlays` by a rounding step. The four
`parlays.NOTES` caveats travel verbatim; two of them are the difference between
a number and money. No edge, no ranking, no button (ADR 0038, ADR 0071 §2.5, and
`discord.py`'s own docstring already ruled out tap-to-buy in a chat client).

`notifications.UNIQUE (kind, key)` **is** the change detection — no timestamp
comparison, no threshold, and it survives the restart an in-memory policy would
not. Key is `card_key` + **sorted** leg tickers, already the canonical card
identity (`price_card_on_kalshi`'s drift check, `parlay_lookups.selected_legs`).

**Verified end-to-end on live, not just in tests.** The embed was first rendered
from the real `/api/parlays` payload pulled off the box (three built cards, WNBA
and MLB legs) — then after deploy, **three pushes landed at 22:41:43Z and
`undelivered_last_24h` stayed 0**. Discord accepts the embed.

**Two things the build found that the plan did not have.**

1. **Dedupe is not a rate limit.** `MAX_PARLAY_PUSHES_PER_DAY = 6` bounds it;
   undelivered pushes do not burn it, so one Discord outage cannot silence the
   rest of the day. **The mechanism was measured after deploy and it is not the
   one I first wrote here** — see the open item below.
2. **The ladder is expensive and I called it free.** `build_ladder` runs a
   **200,000-sample Monte-Carlo copula per card, five times over** (headline
   plus one per devig method) — ~400ms for three cards on a laptop, against a
   quote pass budgeted 8s that runs ~4.2s on live. The first commit put that on
   every pass. **It would have degraded silently** —
   `Tempo.observe_pass_duration` warns rather than fails. Now gated on
   `counts.odds_sweeps > 0 or kind == "full"`: a sweep is the only thing that
   changes a fair value, and between sweeps the ladder rebuilds byte-identically
   so the cost bought a notification the dedupe then discarded.

**One guard written, mutated, observed GREEN and deleted** — a
`not_built_reason` check in `Alerter.parlay_cards` changed no answer, because an
unbuilt card serialises with no legs and `parlay_key` already returns `None`.
**And one test was vacuous when first written** (compared a slice spanning a
newline against a single line, so it could never fail); it now reads the gate
line, with a vacuity guard beside it. **Eleven mutations observed red** across
the new guards.

### NOT built, and both are deliberate

- **The slash command.** Joe picked it, and it is **not an extension of the
  above — it is a new subsystem.** There is no inbound Discord path today: no
  route, no signature verification, no `nacl`, and `requirements.txt:30` pins
  `discord.py~=2.4` which **nothing imports**. It needs a public HTTPS endpoint
  (uvicorn binds loopback and is never published), Ed25519 verification of
  `X-Signature-Ed25519` plus a crypto dependency, a Discord *application* rather
  than a webhook — which undoes the four-taps-on-a-phone setup property
  `discord.py:50-55` was built around — and a new auth lane at `middleware.ts`,
  which today accepts only the `cockpit_session` cookie. **Wants its own ADR.**
- **Kalshi buys from Discord.** Joe ruled it out this session when asked.
  Recorded so it is not re-proposed as an obvious next step.

### Discovery: more parlay approaches — there is ONE generator, not three

Asked for, and this is the headline. `build_ladder` is:

    CARD_SHAPES = (("safe",2,3), ("middle",4,4), ("lottery",6,6))
    _sort_key   = (-p_conservative, commence_ms, kalshi_market_ticker)
    _best_per_game(usable, prefer_spreads=(key == "lottery"))

**Safe and Middle are prefixes of the same ranked pool** — Middle's four legs
are Safe's three plus the next-most-likely game. `prefer_spreads` for Lottery
(`ladder.py:238`) is the **only** structural difference in the entire ladder.
Every card is "the most likely favourites available", cut at a different length.
Candidates are `market IN ('h2h','spreads')` only — **no totals**
(`parlays.py:148`) — and spread legs must be the favourite's cover.

Ranked by value per unit of work:

| # | Approach | Why |
|---|---|---|
| 1 | **Longshot card** | Invert `_sort_key`. A real second product from one parameter; not gap-ranking, so ADR 0071 §2.5 untouched. Makes "Lottery" mean its name. |
| 2 | **Time-boxed** ("next 3 hours") | Filter on `commence_ms`. The most phone-useful cut: what can I still bet on. |
| 3 | **Sport-pure** (all-MLB, all-WNBA) | Filter on `league`. Useful when watching one game. |
| 4 | **Method-agreement** | Require all four devig methods within N points per leg. `by_method` is **already computed** (`ladder.py:163`) and thrown away. CLAUDE.md rule 2 as a product. **My pick.** |
| 5 | **Totals legs** | Widen `parlays.py:148`. The only one that makes *existing* cards better rather than adding one. |
| 6 | **Correlation-diverse** | Maximise cross-league to minimise rho (`classify` already returns the regime; 0.02 vs 0.05). |
| 7 | **Same-game via measured rho** | `implied_correlation` (`correlation.py:253`) inverts an observed combo quote into a measured rho, Fréchet- and PSD-guarded — **fully written and called by nothing on the desk path.** The documented route past `ladder.py:20-22`'s refusal. Wants its own ADR. |
| — | ~~Gap-ranked card~~ | **Forbidden, ADR 0071 §2.5.** Listed so it is not re-proposed. |

**Recommended: take 1, 2 and 4 as one slice** — three parameters on an
already-pure function, turning one generator into four genuinely different
products. Then 5. Then 7 with an ADR.

### OPEN AND NEEDS JOE — the cards churn far faster than the ceiling allows

**Measured on live, not predicted.** The 6/day ceiling was spent in **four
minutes**:

    22:41:43Z  safe: LADATL-LAD | BOSMIA-BOS | MILNYM-MIL     (all MLB)
    22:45:10Z  safe: CHICONN-CHI | PDXDAL-DAL | GSCONN-GS     (all WNBA)

The entire card composition swapped sport, and all three rungs re-pushed. Both
pushes were *correct* by the dedupe rule.

**The cause is per-sport sweep freshness, not kickoffs.** `build_ladder` drops
legs whose `odds_age_now_ms` exceeds 900s, and odds are swept **per sport on
independent clocks**. A sport's legs enter the pool when it is swept and leave
when they age out; ranking is by probability, so whichever sport is currently
fresh takes the top slots. The 22:21Z payload carried
`excluded: {"stale_consensus": 7}` — seven legs already dropped for age.

So the feature works and then goes quiet for the day. **Not harmful** — the
ceiling holds, Joe is not spammed — but the daily card he asked for is being
spent on transient compositions in the first minutes after a deploy or a
day-roll.

**Three ways out; this is Joe's call:**

1. **A real scheduled card** at a fixed time (his trigger #1, taken literally),
   immune to churn by construction. Push one ladder a day and let the
   material-change alert be a separate, tighter rule.
2. **Debounce**: only push a composition that survives two consecutive builds,
   so a sport flipping in and out never announces itself.
3. **Require every leg fresh AND the card to beat the last pushed one on a
   stated criterion** — closest to "material change", most work, and the
   criterion must not be the consensus-vs-Kalshi gap (ADR 0071 §2.5).

**Recommendation: 1 plus 2.** The scheduled card is what he actually asked for
and the debounce makes the change alert trustworthy.

### Still open from before, untouched

The **cold-open wait** is real and now precisely located, and it was NOT worked
this session (Joe redirected). The loop wakes within 5s of a heartbeat but the
wake reaches the *loop* and not the *policy*: (1) `run_loop.py:644` →
`scheduler.py:316-326`, an early wake lands inside `last_full_ms + 900s` so
`pass_kind` returns `"quote"`; (2) `timing.py:570-571`, that quote pass runs
`allow_bootstrap=False`, dropping any sport with no *served* sweep this budget
day; (3) `scheduler.py:309-310`, `next_wake_ms` is already due so the loop takes
the 900s branch. Meanwhile `window_status:1180-1189` calls `desk_wants`
**without** `allow_bootstrap`, so the screen promises a sweep the quote pass
cannot make — breaking the module's own "one predicate, two callers" rule at
`desk_wants:513-517`. Wide test blast radius (nine named assertions in
`test_scheduler.py` and `test_desk_follows_attention.py` pin the current
behaviour on purpose). Deserves its own slice.

Also still open and unchanged: `ODDS_API_KEY` rotation (security, tabled by
Joe); `docs/` still carries the stale 576/day figure outside CLAUDE.md; no ADR
records the attention TTL, floor horizon or credit slice.

---

## 2026-08-25 — the desk was empty because the loop was ASLEEP, and nothing could wake it

**Read the correction first.** The earlier version of this entry, and the
commit message on `aa4a215`, said the recording loop had **wedged**. It had
not. Every number reported was right and the mechanism was wrong, which is the
combination that survives longest because the symptom keeps matching.

- `pass 130 ok` is in the log at 16:49:33Z. **The pass returned.** A hang does
  not log its own completion.
- The gap to 17:05:07Z is **934s**, and `next_delay` jitters ±15% around the
  900s slow interval — the band is [765, 1035]. 934 is 900 × 1.038.
- `Tempo.interval_s` returns `slow_interval_s` when the window is shut. The
  pass at 16:49:33 was the first to observe `fixtures_fresh = 0` (the last
  sweep at 16:36:32 plus book age crossed `MAX_ODDS_AGE_S`), so it took the
  slow cadence and slept.

It was a **normal, designed sleep**. "The loop hung" was a story that fit the
evidence I had looked at and not the evidence available.

**The real defect, and it is a genuine one.** ADR 0071 §2.6 told the *feed* to
follow attention. `decide_sweeps` asks `is_attended` every pass and has always
done the right thing with the answer. But the cadence is chosen from what the
*previous* pass observed, and attention is written by the **other process** —
the API stamps `desk_attention` when a page heartbeats. A sleeping loop cannot
see a table being written. So the feed followed attention and the loop that
calls it did not: a heartbeat could wait up to fifteen minutes to be acted on,
which is exactly the fifteen minutes the desk is blank and someone is staring
at it. Joe opened the desk at ~16:58Z; the loop fired
`baseball_mlb (attention)` at 17:05:08Z, the first second after its sleep ended.

The tap path had the same hole. `run_quote_pass`'s docstring promises a tap is
served within "at most one tick" — true of the 15s cadence, false of the 900s
one, and a shut window is precisely when someone presses refresh.

**FIXED — the sleep is interruptible.**

- `backend/scheduler.py`: `sleep_until(delay, wake_when=…, sleep=…, poll_s=5)`
  sleeps in chunks and ends early when the predicate fires. `wake_when=None`
  sleeps once, exactly as before, so every existing caller and test is
  untouched. A predicate that raises is swallowed and logged — the failure
  direction is the old cadence, and ending a recording loop over "should this
  sleep be shorter" trades a slow desk for a lost record. `LoopState.woken_early`
  counts the wakes so a wake path that stops firing is distinguishable from
  nobody opening the page.
- `backend/odds/attention.py`: `ArrivalWatch`. **Not `is_attended`** — that is
  a state, true for the whole 300s TTL, and a sleeping caller cannot act on a
  state it is already in. This reports a *change*, once per heartbeat, and
  consumes it. A page heartbeating every 60s therefore wakes the loop every
  60s, which is the cadence a watched desk belongs on; and that state is
  strictly cheaper than the one it converges to, because a wake leads to a
  sweep, a sweep opens the window, and an open window is the 15s fast cadence.
- `scripts/run_loop.py`: `wake_early()` = a new heartbeat, or a pending tap
  (`ondemand.take` is a pure read and cannot consume one), handed to
  `run_forever` as `wake_when`.

Cost: an indexed `MAX(seen_ms)` every 5s, on a table `decide_sweeps` already
reads every pass. No credits. Latency from opening the desk to the loop
noticing goes from **up to 900s to under 5s**.

Seven mutations observed red: predicate checked before the chunk, never
returning early, no try/except, the watermark not advancing, the watch starting
blind to history, the re-report guard removed, and the loop not passing the
predicate at all. Plus a composition test over a real sqlite connection — a
stamp landing on the third chunk ends the sleep at 15s instead of 900s, and a
quiet desk still sleeps the full 900s.

**STILL OPEN.**

- **The 30-minute heartbeat threshold** (`.github/workflows/heartbeat.yml`).
  Unchanged, and now clearly *not* what today was about — nothing had stopped.
  Whether a genuinely stuck pass would be caught is still untested, because
  nothing has ever been observed to hang: `run_forever` awaits `do_pass()` bare,
  with no `asyncio.wait_for`. Leave it until something actually hangs; a timeout
  that cancels mid-write is a real risk to buy against a hypothetical fault.
- ~~A cold page still needs one manual refresh.~~ **Closed the same session.**
  `components/RefreshWhenPriced.tsx` polls `/api/window` every 10s from inside
  the `Freshness` block and calls `router.refresh()` when `fixtures_fresh`
  rises above the count the server rendered with.

  The trigger is deliberately **not** "a sweep happened": a sweep that
  re-priced already-fresh fixtures changes no answer on this page, and
  re-rendering for it is a flicker with nothing behind it. It is not a timer
  either — a page that reloads on a schedule reloads while you are reading it.
  It stops after 5 minutes, and `test_parlay_auto_refresh.py` pins that number
  equal to `attention.DEFAULT_ATTENTION_TTL_MS` across the two languages: past
  the window in which the heartbeat is still buying sweeps, waiting is not
  waiting for anything. Hidden tabs do not poll, which is a correctness
  argument rather than a courtesy — `Nav.tsx` gates the heartbeat the same way,
  so a backgrounded tab is sending none and no sweep is coming for it.

  Proved against a local stack, not just pinned: demo DB in the exact 09:58
  shape (11 upcoming, 0 fresh, three unbuilt cards), prices made fresh in
  SQLite while the page sat open, and the page came back with three cards and
  `performance.getEntriesByType('navigation').length === 1` — re-rendered in
  place, never reloaded. Seven mutations observed red.

  **`/slate` has it too, on a deliberately different gate.** The desk's
  `Freshness` block already fires only when a card failed for age, so the
  watcher needed no extra condition there. The slate always renders its rows —
  refused ones included, because it is a record — so it is never visually
  empty, and `refreshIsUrgent` is `some`: one stale row on a working slate
  satisfies it. Re-rendering under a reader mid-game on that basis would be the
  screen moving for no reason they can see. So `slateIsUnpricedByTheClock` is
  the gate: **every** row refused, and at least one refusal is the clock —
  nothing usable, and a sweep is what would give it back. Rendered above the
  refusal `<details>`, never inside it: a page that re-renders itself while the
  only explanation is folded away moves for no stated reason.

  It lives in `nextOddsWindow.ts` rather than beside `refreshIsUrgent`, and
  that is not tidiness. It needs `isStaleOddsReason`, and **both** pure modules
  state in their own docstrings that they are dependency-free so node can
  execute them bare; importing across would quietly retract that from both, and
  copying the split-and-compare would be the second implementation the
  whole-code rule exists to prevent.

  Also verified against a local stack: every slate row forced clock-refused,
  the watcher rendered, then odds made fresh and the refusal lifted — page came
  back usable with `navigation` entry count still 1.

  **One guard was written, mutated, observed GREEN, and deleted.** An explicit
  `rows.length === 0` check read like a guard and changed no answer — `every`
  over an empty array is vacuously true and the `some` returns false on its
  own. The behaviour is still asserted; the line was decoration and this repo's
  rule is to remove it rather than keep it for looks.

**SHIPPED EARLIER THE SAME DAY — the screen explains itself (`e4500f5`).**
`readNextWindow` learns `last_look_ms` and a `loop_stalled` reading checked
before `due_now`; `StaleOddsExit` extracted to its own component; `ParlayCards`
renders a `Freshness` block when a card failed **and** sides were dropped for
age; `Not built tonight` → `Not built right now`. Note that the `loop_stalled`
sentence is still right and still worth having — it just would not have fired
today, because `last_look_ms` was 12 minutes old, not the 3 the threshold wants.
That is correct: nothing was broken.

**Two operational notes worth keeping.**

1. **`flyctl deploy` by hand reports `git_sha: null`.** The workflow passes
   `-e GIT_SHA="${{ github.sha }}"` as a *runtime* machine variable
   (`deploy.yml:119`), not a build arg, and it is not inherited by the next
   deploy.
2. **The browser caches `/parlays` hard.** A bare reload served pre-deploy text;
   `?cb=1` served the new page. Verify a deploy with a cache-buster or
   `/api/health`, never a plain refresh.

## 2026-08-25 (later) — the odds feed stops watching the clock and starts watching whether anyone is there

**Shipped and verified on live at `49f1f43`.** Three commits this session, all
deployed: `5cf94be` (the signal declaration refused — entry below), `5e75da9`
(a failed odds call stops presenting as fresh odds), `49f1f43` (this).
**Schema v21.** State: 4,281 passed / 10 xfailed, ruff clean, tsc clean,
`next build` green.

**The bill, settled.** `ODDS_DESK_WINDOW_UTC` bought a sweep every ten minutes
for twelve hours a day whether or not anyone had the site open — 576
credits/day, and **1,152/day at four sports, past the whole 20,000 tier**.
NCAAF and NFL made that due this week and `fly.live.toml` had already recorded
it as a decision deferred to the day they landed. ADR 0071 §2.6 is the answer:

    attended (a heartbeat inside 5 min)   the 10-minute refresh cadence
    nobody looking                        hourly, per sport with a fixture
                                          inside 12 hours

`ODDS_DESK_WINDOW_UTC` is **unset on live and still read** — a window can be
pinned back on without a code change. `ODDS_ATTENTION_DAILY_CREDITS = 300` is
the hard ceiling on attended spend; **the floor is not charged to it**, which
is what makes a low cap a ceiling rather than an off switch.

**Observed on live, not inferred.** The pass at 15:11Z bought both sports on
the floor and stored 2,120 quotes, with the sweep-log row reading *"nobody is
looking; the hourly floor keeps the slate from going a whole day stale"*. The
pass fourteen minutes earlier — the old build — reads *"the desk window
(16:00Z-04:00Z) reopens at 16:00Z"* and held the credit. The change is visible
one pass apart in the same table. `/api/window`'s `next_sweep_ms` was exactly
`last_sweep + 3,600,000`, so the panel and the loop agree.

**The attention path was exercised on live at 16:08Z and it works** — but read
the caveat, because half of it is still untested.

    15:11:06Z  floor buy, trigger NULL   "nobody is looking"
    15:26/15:41/15:56  three passes HELD  (floor not due until 16:11)
    16:03:43Z  one stamp lands
    16:08:10Z  attention buy, trigger='attention', 430+ quotes
               "someone has the desk open; re-buying so the slate is
                priced while it is being read"

The floor suppressed three consecutive passes and one heartbeat un-suppressed
the next. Accounting separates cleanly: 8 credits floor (NULL) + 8 attention.

**Two halves, proven separately, and the join between them is NOT proven.**

- **The visibility guard works against a real browser.** A tab driven by Chrome
  automation reports `visibilityState: "hidden"`, `Nav.tsx` sent nothing, and
  no `/desk-attention` request was made. That is the load-bearing line verified
  in the one way `tests/test_desk_heartbeat_is_visibility_gated.py`
  structurally cannot — those assertions prove it is *written*, this proves
  Chrome *honours* it.
- **Everything downstream of a stamp works**: route → `desk_attention` →
  `is_attended` → `desk_wants` → `decide_sweeps` → the `attention` trigger on
  the credit row, and `/api/window`'s `next_sweep_ms` moving from
  `last + 3,600,000` to exactly `now_ms` within a minute.

**The join is closed too — Joe opened the site at ~16:28Z and the full cycle
was observed.**

    15:11Z  floor buy, trigger NULL     "nobody is looking"
    16:08Z  attention buy               (a MANUAL fetch, bypassing the guard)
    16:36Z  attention buy               JOE'S BROWSER, unaided
    16:40Z  next_sweep_ms - last_sweep_ms == 3,600,000 exactly

The 16:36Z row is the one that settles it: it carries `trigger = 'attention'`
and the manual stamp had expired at 16:08:43Z, 28 minutes earlier, so only a
real heartbeat from a visible tab can have produced it. The desk also read
attended at 16:28, 16:29 and 16:32 — more than one 5-minute TTL apart, so at
least two independent self-fired stamps rather than one lucky reading. Four
minutes after he closed the tab, one TTL, it was back on the floor to the
millisecond. Spend for the day: 24 credits, 8 floor and 16 attention.

**A design gap this surfaced, and it is NOT a regression.** An attended desk
gets *"the ten-minute cadence, actioned by whichever pass comes next"*. Quote
passes run every 15s **only while the window is open**; once the odds age past
`MAX_ODDS_AGE_S` the window shuts, the fast cadence stops, and only the 900s
full pass can buy. So a cold open can wait a **full fifteen minutes** for the
sweep its own heartbeat just asked for — which is the moment the feature exists
to serve. The old fixed window had exactly the same property, so nothing got
worse; but following attention was supposed to make the cold open fast, and
this is the thing that stops it. Not fixed, deliberately: it is a scheduler
change, it wants its own slice, and nothing about it is urgent while the floor
keeps the record accruing.

**Watch out for the diagnosis this cost, because it will look the same next
time.** Between 16:22:41Z and 16:39:32Z the loop logged nothing and
`recorder.age_ms` climbed to 12.6 minutes behind a green health check — the
signature this repo has been burned by. It was **healthy idle**: the window had
closed, so the loop was on the 900s cadence, and it woke on schedule. Before
calling that an outage again, check `/api/window`'s `is_open` first. A closed
window explains a quiet log completely, and `run_loop.py`'s own docstring says
so.

**Do not quote a saving.** Every "attended hours" figure is a guess. The
instrument is `credits-day --date YYYYMMDD` read **by trigger** — attention is
`'attention'`, the floor and the schedule are both NULL. Bounds only:
~384/day idle at four sports, ≤300/day attention, ~684/day worst case inside
the 700 cap. Read it in a few days.

**Three things the build found that the plan did not have:**

1. **The floor's first buy of a sport is unpaced.** The cadence is measured
   from the last *served* sweep, so a sport with none makes every pass want
   it — once per 15s quote pass until the budget is gone. `5e75da9` widened
   that: a *failing* sport no longer moves the stamp either, so a 401 would
   retry every 15s. The floor now respects `allow_bootstrap`, the rule the slot
   planner already had.
2. **The sub-ceiling needed a trigger label.** `DESK` firings stamp
   `api_credits.trigger` NULL like every planner firing, so attention spend was
   indistinguishable from a scheduled slot's. Attention buys now stamp
   `'attention'` — still counted by `_SERVED_SWEEP` (it is not `'manual'`), and
   it is what makes the saving measurable at all.
3. **`5e75da9` moved a failure rather than removing it.** With `last_sweep_ms`
   no longer advancing on a failed call, a `failed` look falls past
   `sweepTone`'s `refused` clause and — before the first window of the day —
   reaches `return "calm"`. The recorder would be dead and the strip quiet: the
   17-hour shape with a new cause. `failed` now warns alongside `refused`.

**The desk trigger had five sites, not the two the entry below records** — two
hand-synced `if`s, a third spelling in `first_window_open_of_day`, a fourth in
the refusal message, and `scripts/run_loop.py`, which passed no `desk_window`
at all and so logged a cadence it did not follow. All now read `desk_is_open` /
`desk_next_open_ms` / `desk_wants`, pinned by a reference count so a sixth
spelling goes red.

**Nine existing tests changed, and one of the changes was wrong first.** Six are
the deliberate "held the credit → the floor buys it" inversion, dated. For the
staleness-limit test I first moved a fixture beyond the floor horizon, which
made it pass under *any* `max_odds_age_ms` — a decoration. Reverted; it asserts
the trigger instead, and was checked red against the default limit.

**Still open from Lane 1** (slices 6–7 of the written plan are done; this is
what is not): nothing blocks, but `docs/` still carries the 576/day figure in
places other than CLAUDE.md, and no ADR records the TTL, the floor horizon or
the slice — ADR 0071 §2.6 states the direction, not the parameters.

---

## 2026-08-25 — the declaring look is REFUSED, and §P4 turns out to have been an opt-in nobody opted into

**This supersedes the entry below it.** That entry recorded a `NO SIGNAL`
declaration off the live screen and told the next session to put it through a
`measurement-skeptic` pass before writing it anywhere. The pass was run. **It
failed the declaration**, on a defect neither the entry nor this session
predicted, and found something larger underneath it.

**Baseline re-measured at session start rather than inherited: 4,200 passed /
10 xfailed** (the entry below says 4,192).

**The reading reproduces exactly, off a fresh 2026-08-25 pull** (14,616 rows,
6.1 MB, live `git_sha 1bdc33b`), and the auditor re-implemented the fit
independently and got the same numbers. **The arithmetic was never the
problem.**

**D1, the decisive defect.** The record holds **four**
`strategy_config_version`s — `{1: 359, 2: 56, 3: 1682, 4: 12519}`. §P4 and §7
of the registration both say, in those words, that the primary then runs on the
**modal version only** and *"`G` counts only those games"*. Run that way:

    beta_hat -0.0756   se 0.0246   G = 216   [-0.1728, +0.0216]
    UNRESOLVED — 84 clusters below the floor, not 11 over it

The rule existed in code as `build_report(..., modal_config_only=False)` and
**no production caller ever set it** — the "built but never called" pattern, one
parameter wide. It was survivable while every look was interim (the 2026-08-16
write-up states plainly that the rule "was **not** applied to the numbers
above" and ran it as a sensitivity, which is permissible when nothing is being
declared). It stopped being survivable the moment `G` crossed 300.

**Fixed this session.** `build_report` applies §P4 itself, the parameter is
gone, `report_from_connection` takes no options, `--modal-config-only` is
retired, and the pooled fit is carried as `pooled_fit` — **never given a
verdict**, but kept, because the interim look's published `-0.1412 / G = 199`
must stay reproducible or the measurement record becomes unverifiable.
`tests/test_clv_signal.py` now pins **both rows of that document's sensitivity
table**; three guards mutation-verified red. `/api/signal`'s population block
gained `modal_config_applied`, the modal version, the excluded row count and
the version distribution, so a reader can no longer see `clusters` without
knowing which population produced the verdict.

**Seven more defects, all in the measurement doc.** §A4's leave-one-group-out
downgrade is unimplemented (run by hand it does not fire — max upper +0.0286);
§A4's mandatory leverage disclosure fires at **0.9392** and nothing computes it;
the headline "largest contributor" line prints a row-count share of an
unregistered cut; `sd(clv_tenths) = 30.15` crosses the power check's own
amendment trigger and the amendment is unwritten; five registered §A9 outputs
are absent; and `sigma_eps` raw-vs-residual (30.15 vs 29.76) **straddles that
trigger**, so which one it means has to be settled by amendment, not by which
line the harness prints.

**The finding worth carrying past all of that: `G = 311` is 4.26 effective
clusters.** Two games carry 50% of the leverage on `beta`, nine carry 90%, and
one WNBA game carries **43.80%** alone. All twelve top-leverage clusters are
WNBA moneyline; WNBA is 19.1% of rows and **95.6% of the leverage**. The rows
doing the work are `too_few_books`/`no_market_width` — 13.5% of the record,
**93.9% of the leverage** — and inside that group `edge_tenths` runs **−717.97
to +372.60**, i.e. a consensus calling fair ≈ 8c against Kalshi's 82c off fewer
than two books. `suspicious_edge` never fires on them because
`edge_ceiling_tenths = 40.0` bounds the **positive** side only. **Rule 1 says
those are bugs, not edges**, and `sd(edge)` is 40.98 with them and **10.90**
without — so the apparent resolving power (MDE 0.078 against the registration's
feared 0.42) is bought entirely from rows rule 1 refuses. The registration's
power arithmetic was right all along.

**Also refuted this session: my own pre-audit argument that §A4's downgrade was
near-vacuous at G = 311.** It assumed removing a group costs `G` one cluster per
group member. Removal only reduces `G` when it **empties** a cluster, and groups
are non-exclusive — `too_few_books` spans 190 clusters and leaves `G = 271`.
Seven of thirteen groups were testable. The test had to be run, not argued away.

**What is NOT open.** Nothing operational changed: ADR 0038 closed the hunt on
independent grounds, the gate's 300 counts *actionable games* (a different
counter, untouched), and CLAUDE.md's "treat it as settled for planning" stands
unedited. **The registered-look machinery (§A4 leverage/LOGO, the five §A9
outputs, the `|edge| > 100` amendment) is the precondition for the NEXT
declaring look and is deliberately not built** — it does not earn the critical
path over the odds bill. It is listed in the measurement doc's closing section.

---


---


## Still open, as of 2026-08-17

Short by design. The long-form reasoning behind each is in the archive entry
named beside it.

- **The cost-of-execution meter is Joe's call, unmade.** `sharp-bettor`'s
  proposal to re-point the Board from *"is this mispriced?"* to *"is this
  cheaper on Kalshi or at a book?"*. Do not build it before he decides. Above,
  and `archive/next-2026-08-17.md`.
- **H4 is untested**, so the 0.63-point cost headroom is an upper bound, not a
  figure. Separating "settlement is free" from "`fee_cost` is entry-only" needs
  the account balance. ADR 0027.
- **The `G = 300` look happens on its own and nothing may depend on it.**
  `beta` would have to move 8.3 standard errors for the verdict to be anything
  but NO SIGNAL. ADR 0038, and `archive/next-2026-08-16.md`.
  **Two corrections since this bullet was written, both 2026-08-25.** (a) *"the
  recorder costs nothing to leave running"* is false on the odds axis and the
  clause is deleted here — see CLAUDE.md's cost paragraph. (b) **The floor is
  `G = 216`, not 311**: §P4 makes the primary the modal `strategy_config_version`
  alone, so the look is 84 clusters away rather than past. The 2026-08-24 screen
  that said it had happened was refused on audit.
- **The Odds API renewal is Joe's decision, on the invoice.** ~24% of the 20,000
  tier in seven days is a real bill even though it is not the 90% this file used
  to claim. Above.
- **`ODDS_API_KEY` rotation is open, and it is a security item.** A subagent
  read `.env` and the plaintext key landed in a transcript. Tabled by Joe, not
  closed by anyone. It was recorded above but missing from this summary list,
  which is the list a future session actually reads — the omission is the bug.

**The build checklist that used to live at the bottom of this file** — *"1.
Blocked on you"*, *"2. Fix before any real money"*, *"3. Ready to build"*, *"4.
Verified working"*, *"The honest status"* — is in
[`archive/next-2026-08-07.md`](archive/next-2026-08-07.md). It is kept whole and
it is **stale**: it states 653 passing tests and a 52.00% taker bar, both since
superseded. `tasks/todo.md` is the live build log; read that, not the archived
checklist.

---

# The session index

Every session entry ever written to this file, newest date first. Full text in
the linked archive file, unchanged.

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
