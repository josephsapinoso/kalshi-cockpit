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

**Split again 2026-08-29, at 225,270 bytes — 86%, before writing anything.**
The 2026-08-26 and 2026-08-25 entries (9 of them) moved to
`archive/next-2026-08-29.md`, verbatim, leaving ~148KB here. This is the first
split taken on the rule rather than on the alarm: `wc -c` was read before the
session's entry existed, and the entries moved out before it was added.

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

**Test baseline: 5,474 passed / 10 xfailed in 18:49**, collected 2026-09-01
with **no code or test file edited after the run started** (documentation was
added under it — the measurement doc and these session files — and no code or
test file moved). **The +16 over 5,458 is accounted by COLLECTING both trees,
not by reasoning about a delta**: `tests/test_failure_journal_read_path.py` is
14 items, and `tests/test_inspect_live_db.py` collects **233 with the new
query registered and 231 without it** — `TestEveryWhitelistedQueryRunsAgainst
TheRealSchema` is parametrised over `QUERIES`, so adding one query adds two
items. Measured by removing the registration and re-collecting; it took twelve
seconds and is the only method that has ever worked on this line. `ruff` clean.

**Superseded: 5,243 passed / 10 xfailed in 11:54** on `a31d12c`, collected
2026-08-30 with **nothing edited after the run started** and the tree clean
throughout. That qualification is the point: the same 5,243 was collected on
the previous tree while `tasks/NEXT.md` was being edited under it, so this run
is the first unqualified confirmation of the number. The change between the
two trees was documentation only — no code or test file moved — which is why
the count is identical rather than merely close.

**Superseded: 4,984 passed / 10 xfailed** on `2b3baa3` — see the #35 entry
below for the delta. The line below was true of `f1c2b5f` and is kept because
its reasoning is what keeps this number honest:

**Superseded: 4,972 passed / 10 xfailed in 7:14**, measured 2026-08-28 on
the tree committed as the watchdog corrections, with nothing edited after the
run started. The **+13 over the previous 4,959 is fully accounted**: eight
`TestAWedgedPassIsBoundedAndRecorded` guards in `tests/test_scheduler.py`, four
`TestTheLadderReportsWhyItRefusedLegs` guards in `tests/test_pass_reporting.py`,
and one footer guard in `tests/test_heartbeat_threshold_arithmetic.py`. Both
intermediate runs were collected on their own trees (4,971 at the deadline
commit) rather than reasoned about. That triple — the number, the tree it was taken
on, and the fact that nothing moved after — is the qualification this line has
never carried, and its absence is the whole reason it kept being wrong.

**4,959 on `5436fc8` was correct about that tree** and is superseded, not
corrected. Two earlier runs this session are NOT this number: one read
`1 failed, 4962 passed` — a real finding, a structural probe that read the 600
characters after `alerter.parlay_cards(` and stopped seeing the staleness limit
once the ladder payload was bound to a name — and one was killed deliberately
because a fix landed under it.

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

**THEN INVOKE THE `partner` AGENT, BEFORE PLANNING ANYTHING.** It owns what
gets worked on, in what order, and by whom. **Until 2026-09-01 nothing in
this repo told a session to do that** -- `CLAUDE.md` did not mention the
partner at all and this box did not name it -- so every session re-derived
its own priorities from a 140KB file and worked one item. Joe asked why the
partner was not involved every session, which is how it was found. It is
now `CLAUDE.md` workflow step 0. Hand it the state (what is open, what
landed, what is blocked) and ask for a ranked list AND which items can run
as parallel lanes. Skip it only for a single errand Joe named himself.

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

## 2026-09-01 (latest) — open item 4 named an instrument that cannot see the failure it measures, and the good news I wrote off it was refused

**DEPLOYED `ad3efed`, verified** — `/api/health` `git_sha` reads
`ad3efed`, status ok, mode live, recorder writing 36s before the read.
`tasks/NEXT.md` was 80.7% before this entry was written, checked with `wc -c`
first per the rule at the top of this file. **It is 85.2% now — the next
session should split BEFORE writing, not after**, because 90% is the rule and
one more entry of this size crosses it.

**Read the measurement document before acting on any of this:**
`docs/measurements/2026-09-01-the-lock-failure-table-is-a-floor.md`.

**Suite: 5,474 passed / 10 xfailed in 18:49** on the final tree — see the
baseline paragraph at the top for how the +16 was accounted.

### The instrument: `loop_failures.jsonl` had a writer and no reader

Open item 4 read *"Watch whether `database is locked` recurs. `loop_failures`
is the instrument."* **It named the wrong artifact.**

`db.record_loop_failure_durably` has appended every pass failure to
`loop_failures.jsonl` since 2026-08-30, and its own docstring says why the
table is not enough: the failure ROW is a write, so a lock that kills a pass
can kill its own record. `grep -rn loop_failures.jsonl` over the repo returned
the writer (`scripts/run_loop.py:708`), tests of the writer, and **no consumer
anywhere** — not `inspect_live_db.py`, which is the only thing permitted to run
against the live box. For two days the durable half of the record was
unreachable from the place the question gets asked.

`inspect_live_db.py failure-journal` reads it now. Fourteen guards, every one
verified by disabling what it guards and watching it go red (ten mutations,
listed in the commits).

### What the first reading says

    22 journalled failures since 2026-08-30, all `database is locked`
     8 recorded on the shared connection
     0 recorded on a fresh connection
    14 recorded on neither  -> no `loop_failures` row at all

**The table held 8 of 22.** For this failure class, under lock contention, any
count taken off `loop_failures` is a **floor** — including every count this
file has quoted. Two scope limits: it is measured over the journal's ~2-day
life, not the table's, and it does not generalise past lock contention (a
`PassDeadlineExceeded` inserts fine).

**A reader querying the table by `pass_kind` sees a population with no quote
failures in it** — all 8 surviving rows are `full`, while 2 of the 22 were
quote passes and both are among the lost 14. At n = 2 that is consistent with
chance (Fisher two-sided **p = 0.52**) and is NOT evidence of a kind-specific
loss; it is one more instance of the floor.

### THE CLAIM THAT WAS REFUSED — read this before writing any before/after here

I wrote this up, and `measurement-skeptic` refused it before it entered the
record:

> Lock failures fell from 15.84% (16 of 101 full passes) to 0 of 30 in the
> 8.07 hours after ADR 0091 deployed, on the same hardware. P(0) = 0.006.

**It must not be written, hedged or not.** The fatal defect is one
subtraction:

    newest journalled failure   2026-08-31T11:01:00Z
    ADR 0091 deployed           2026-08-31T15:29:19Z   (Fly release 182)

**The quiet run starts 4.47 hours BEFORE the fix.** In full-pass walk lines it
is 50 passes — **14 on pre-fix code, 36 after** — so the deploy sits at
position 14 of 50 and nothing in the data locates the change at it. Run the
claim's own test on the pre-fix half and it "detects a fix" across an interval
in which nothing shipped. Both timestamps had been on my screen for an hour.

Four more defects, each independently disqualifying:

- **The outcome definition changed inside the window.** `badd88e` (ADR 0092),
  committed 17:20:15Z, is 1.85h into the post-fix window and covers ~27 of its
  30 attempts. It stopped a lock in the closing-line store from killing the
  pass — so that class was a failure in the baseline and cannot be one after.
- **The denominator premise was wrong.** The walk line is written after the
  **walk**, not after the pass (`scripts/run_loop.py:1368`, whose own adjacent
  comment says *"the second half of the pass can still die"*). So a post-walk
  failure leaves a walk line AND a journal line, and `attempts = successes +
  failures` double-counts it. `_q_walk_log`'s "does not establish" section
  already said this.
- **The unit is the burst, not the pass.** `Tempo.pass_kind` re-arms a full
  pass immediately when one fails, so the 22 failures are **13 independent
  bursts** (`consecutive_failures == 1`), mean 1.69, max 4. Passes-as-draws
  inflates significance by roughly an order of magnitude.
- **The window was cut where my 6,000-line read ran out**, which raised the
  baseline; and three further lock-relevant changes landed inside it
  (`7a3ded9`, `acb8233`, `07a89e2`/`5c7aaf5`).

**What may be said instead:** no `database is locked` failure has been
journalled since 2026-08-31T11:01:00Z — 50 consecutive full-pass walk lines
through 2026-09-01T00:39:19Z — and **the interval is not attributable to
anything.** No rate comparison between these windows is available.

### And the harness was teaching the overstatement, so it was fixed

The audit caught a real defect in what I had already deployed. Section 2 of
`failure-journal` printed *"'the database itself refuses writes' = a different,
worse fact"* with no record that:

- the reading is taken **after** a `rollback()` whose success is never written
  down, so "the shared connection was still holding the lock and refused the
  fresh one itself" is not excluded; and
- it **does not name the holder** — the poller, the API's per-request
  connections and `maybe_checkpoint` all produce it, so it is *consistent
  with* ADR 0091 and is not evidence for it.

Both are on the screen now, not just in the docstring, because the next session
reads the screen. And my own first write-up said *"14 of 14 lost lines say both
connections refused"* — **a tautology**: the 14 are selected by having no table
row, and journal-only is the only outcome that produces one. The query now
prints the three-way population tally and says which count may be quoted.

### Three lessons, all at the top of `tasks/lessons.md`, index updated in the same edit

1. **Find the change point before you name the cause.** The complement to the
   2026-08-30 lesson, which would not have caught this: that one says find the
   boundary from the data; this one says check the effect does not precede it.
2. **A group selected by an outcome cannot report a rate on that outcome.**
3. **A writer with no reader is an instrument that does not exist.** `grep -rn`
   for a reader of every artifact you write; `test_has_callers.py` covers the
   other direction only.

### Still open

1. **Open item 4 STAYS OPEN — but the instrument now works.** The next look
   must start **after `badd88e`** so one definition of "failure" covers it, and
   must count **bursts**, not passes. At the pre-fix burst rate (~0.39/h) a
   30-hour clean window expects ~11.7 bursts, which clears the ≥5 rule on the
   correct unit. Read it with `failure-journal`, not `pass-gaps` alone.
2. **Before crediting ADR 0091, attribute the holder.** Correlate the 22
   journal stamps against the portfolio poller's own start and finish times.
   Nothing else separates the poller from the API's connections or the
   checkpoint, and the ADR is currently un-attributed on live evidence.
3. **One boolean would close the biggest gap in the journal**: whether
   `record_loop_failure_durably`'s `rollback()` succeeded. It separates "the
   shared connection was still poisoned" from "someone else held the lock",
   and it is the single observation the diagnosis line is missing.
4. **`odds_snapshots` retention** — ADR 0086 bought headroom, not a bound.
5. **`user_not_found` on shard 3** and **Joe's shard allocation** — both his,
   both money-touching, both carried.
6. **`/api/*` responses carry neither framing header** — deliberate, not a
   hole (a JSON body has no surface to click), but it becomes one the day an
   `/api/*` route returns HTML. Recorded in the test file's own
   "does not establish" list.

---

## 2026-08-31 — the sweet spot reaches all three surfaces, and a second opinion convicted a four-month-old number

**DEPLOYED `11bd2c0`, verified** — `/api/health` `git_sha` reads
`11bd2c06b62f22b0bb4489bb1ab230bd461aa495`, status ok, mode live.

**Joe asked for `580deb6` and `11bd2c0` is what shipped, deliberately.** The
two differ in `tasks/NEXT.md` alone (`git diff --name-only 580deb6..HEAD`), so
every byte of application code is identical — and a Fly deploy ships the
**working tree**, not a named commit, so stamping `GIT_SHA=580deb6` would have
put a sha on `/api/health` naming a tree that did not ship. That is the exact
defect the `4fb95bb` commit fixed one entry below.

**The first dispatch, one turn earlier, was refused by the auto-mode
classifier** — tried once and reported, per the standing rule. Joe's explicit
"deploy 580deb6" cleared it on the retry. Nothing about the change was ever in
doubt; the block was the harness.

**Read on the live screen, not inferred from the deploy log.** `/slate` and
`/market/KXMLBGAME-26AUG311840SDCIN-CIN`, real rows, through the session
cookie:

    EVIDENCE 5/7 CHECKS · 1 NOT CHECKED
    sportsbook consensus 2042s old, limit 900s; Kalshi quote 134s old, limit 30s.

Three things that confirms and one that is new:

- The caveat renders in the score's own register, so 5/7 cannot be read alone.
- The prose sits at the row's caption size rather than body size.
- `READINGS DISAGREE BY 0.1 PTS` on the slate against devig readings of
  `58.08% – 58.21%` on the market screen — **0.13 pts, so the corrected figure
  is right on live data.** The old code would have printed 0.2.
- **New: the score names a failure no other element on the row does.** The
  StatusLine printed only the Kalshi quote's staleness; the consensus was
  **2042s against a 900s limit** — the limit that actually ends a row's life —
  and nothing said so until this line. That is the redundancy question from
  ADR 0093 answering in the useful direction on the first real screen.

**Suite: 5,458 passed / 10 xfailed in 12:21** on the final tree. The **+12
over 5,446 is `tests/test_frame_headers.py` entirely** — that file collects
exactly 12 items and no other test file changed.

**Superseded: 5,446 passed / 10 xfailed in 10:56**, before the framing headers. The **+2
over 5,444 is the two wrapping guards** — one on the footer span, one on
`TrustNote`'s prose; the size bump moved no test, which is right for a
styling prop.

**Superseded: 5,445 passed / 10 xfailed in 12:31** on the tree with the panel
size and the FIRST wrapping fix — the one that did not move the number. The **+1 over 5,444 is the one new wrapping
guard**; the size bump moved no test, which is right for a styling prop.
The 5,444 below was the status-line tree:

**Suite: 5,444 passed / 10 xfailed in 10:39** on the tree with the status-line
fix. The **+7 over 5,437 is the new `tests/test_slate_status_line.py`
entirely**, collected rather than reasoned about: that file holds exactly 7
items and no other test file changed. The 5,437 below was the tree deployed as
`11bd2c0`:

**Suite: 5,437 passed / 10 xfailed in 11:50**, collected with no code or test
file edited after the run started (documentation was added under it — the ADR
and these session files — and no code or test file moved). **The +21 over
`badd88e`'s 5,416 is accounted by collecting both trees, not by reasoning about
a delta**: the two changed test files hold **75** items on this tree and **54**
on `badd88e`. `ruff` clean, `tsc` clean, `next build` green.

### Open item 1 is CLOSED — ADR 0093

ADR 0090's own closing line said it: *"Still open from Joe's own choice: the
SLATE ROW and MARKET DETAIL surfaces. He picked all three."* Both are built.
`/api/slate` and `/api/market/{ticker}` serve the same `trust` payload the
parlay card carries, from the same `score_trust`, and all three screens render
it through one extracted `components/TrustNote.tsx`.

**Verified on the wire, not by reading the diff**: the slate row and the market
screen for one ticker return byte-identical `trust` objects, and dropping
`trust_thresholds=` from either route turns tests red. That is the
built-but-never-called guard this repo has needed four times.

Two refusals worth knowing before touching it:

- **A row whose `fair_prices` join found nothing gets `trust: null`**, not a
  score on the four checks it still has inputs for. `book_count` is `NOT NULL`
  in that table, so `None` is the join's own tell, and scoring anyway publishes
  *"fewer than two devig methods solved"* — a claim about the devig when the
  truth is there was no fair price to read.
- **Thresholds without a clock raise.** Without `now_ms`/`staleness` both age
  checks read `unknown` and the row looks examined when nothing was measured.
  The Ledger passes neither and gets no key at all.

### THE FINDING — the dispersion strip has overstated disagreement by a fifth since it shipped

**Read this one even if you skip the rest.** Putting the score on the slate row
put a second rendering of one quantity beside an existing one. They disagreed:

    READINGS DISAGREE BY 0.6 PTS        four methods within 0.5 pts
    READINGS DISAGREE BY 8.4 PTS        four methods span 7.0 pts, over 2

`DispersionStrip`'s summary computed the width of the **padded axis**, not the
readings' span. `dispersion.ts` pads the domain by a tenth of the span at each
end so an extreme mark is not half-clipped, so the axis is exactly **1.2x** the
truth — and where books are joined it also contains the **book span**, so the
headline was not about the readings at all. The sentence one line below it,
computed from the marks, was right the whole time. Both errors overstate.

Fixed to the readings' own span, which is now the same quantity
`core.trust.method_spread_points` computes; `parlays._method_spread_points`
delegates to it, so the strip and the score cannot drift apart again.

**The lesson is how it was found, and it is at the top of `tasks/lessons.md`.**
A number cannot be checked against itself: nothing else on the screen claimed
that quantity, so every test about it compared it to its own derivation. **Two
numbers for one fact is normally a defect; here it was the only instrument.**

### The screen was opened, and it caught what tests could not — again

Per the 2026-08-31 lesson one entry below. Seeded a two-row demo DB, ran the
real production build against a local API, and read the pages. Two things no
source test saw:

1. The wrong dispersion figure above.
2. **`TrustNote` had no typography of its own.** On the parlay card it sat in
   an `11px` list item and looked right; on the slate row — same markup, same
   words, every test green — it rendered at body size, the loudest text on a
   row whose every other caption is `text-xs`. A component borrowing its weight
   from its host looks different on every screen it is reused on. It now sets
   its own size, at exactly what the card was already rendering, so the card is
   unchanged.

**390px: TAKEN, and it passes on both surfaces.** Done on live `b09ad5c` with
the real session cookie, against real rows.

**`resize_window` does not work here and reports success anyway** — after a
call to 390x844 the page still measured `innerWidth: 1045` (Chrome ignores it
on a maximised window). Do not trust its return value; measure `innerWidth`.

**What does work: a same-origin iframe.** Load any page on the live origin,
replace the document with a 390px-wide `<iframe src="/slate">`, and the frame
gets a genuine 390px viewport — real media queries, real layout, and the
session cookie flows because it is same-origin. Set the iframe tall (9000px)
and let the OUTER page scroll, or the frame clips and its own `scrollTo` will
not move. Measured, not eyeballed:

    viewport                          390
    documentElement.scrollWidth       375     <- no horizontal page scroll
    score spans found                 100
    score lines that wrapped            0     (max width 210px of 390)
    prose blocks overflowing            0
    /market/{ticker}: scrollWidth     375     prose 343px, 2 lines, no overflow

Three elements do extend past 390 and all three are in the **nav** — a
deliberately horizontally-scrolling strip, pre-existing and not this work.

**The status-line fix was observed at 390px on a real row**, which the desktop
read could not show because the window was open by then:

    Books last read 16 min ago — past the 15 min limit. Not
    actionable until the odds are refreshed.
    READINGS DISAGREE BY 0.1 PTS — tap for the ranges
    EVIDENCE 6/7 CHECKS · 1 NOT CHECKED
    sportsbook consensus 944s old, limit 900s.

**The score was the smallest text on the row, and Joe took the fix.** It
rendered at **9.6px**, 0.8px under the `READINGS DISAGREE BY` line directly
above it — it had inherited `text-[0.6rem]` from the parlay card, where six
legs share one `text-[11px]` list. The slate row now passes `size="panel"`
(12px), matching the gloss and status lines beside it; the card keeps
`compact`. Re-measured at 390px after deploying: score **12px**, prose 12px,
263px of 390, **0 of 100 wrapped**.

**And the re-measurement found the slate scrolling sideways on a phone —
`documentElement.scrollWidth` 428 against a 390px viewport. The first
diagnosis was wrong, and the correction is the part worth reading.**

The cause is a `suppressed_reason` joined from several codes with no spaces
(`stale_odds,too_few_books,no_market_width,...`), which reaches a line-breaker
as ONE token with no break opportunity in it. Two elements render that string
and neither could break it:

- the **refusal-summary footer's** code span — found first, fixed first, and
  it was genuinely missing `break-words` while the row-level span rendering
  the same string had carried it since it was written;
- **`TrustNote`'s own failure prose**, which embeds `suppressed_reason`
  verbatim — **this session's own element, and the one actually setting 428.**

**Fixing the footer and re-measuring is what found the second one.** The
number did not move: still 428, with every footer code now inside the column
at 351. Walking `scrollWidth > clientWidth` down the tree landed on
`TrustNote`'s span at **404 inside a 327px column**. A leaf-overflow scan had
missed it both times, because the span's own box is 327 wide — it is the
*text inside it* that overflows, so no element's `getBoundingClientRect()`
ever reported a right edge past 390.

Two things to carry, and the second is the method:

- **A fix that does not move the number has not been shown to work.** Fixing
  the footer, re-measuring, and finding 428 unchanged is what stopped a wrong
  diagnosis from shipping as a finished one.
- **Overflow does not always have an element you can find by its rect.**
  `getBoundingClientRect().right > viewport` finds a wide *box*; it cannot
  find text overflowing a correctly-sized box. Walk `scrollWidth >
  clientWidth` instead — that is what located it in one pass after two failed
  scans.

**CONFIRMED on live `39d6f92`, and this time the number moved:**

    documentElement.scrollWidth   375   (was 428)
    content overflowing its box     0   (scrollWidth > clientWidth, non-scrollers)
    score font                   12px   x100 rows, 0 wrapped
    longest multi-code reason      65 chars, right edge 351 of 390

**The qualification that matters is the last line.** The stressing data was on
the page this time — `insufficient_depth,too_few_books,no_market_width` was
rendered and fitted inside the column — so this is a clean read *of the
defect's own conditions*, which the earlier 375 was not. A layout check that
passes without the shape that breaks it has proven nothing.

Everything is deployed and verified: live is `39d6f92`, `/api/health` read
from the machine.

**It is data-dependent, which is why the earlier 390px read at 375 saw
nothing** — the same page, the same width, an hour apart, and no long
multi-code reason on the slate at the time. A layout measurement is a
measurement of *tonight's data* as much as of the CSS; one clean read is not a
clean bill.

**And one security finding, incidental to the method.** The live app sends
**no `X-Frame-Options` and no CSP `frame-ancestors`** — which is why the iframe
harness worked at all. Any site can frame the authed cockpit, including the
real-money confirm button. Not exploited here (same-origin, own browser), not
fixed, and filed as its own open item below.

### Also done

- **`tasks/lessons.md`'s pattern index was stale again, in the same way its own
  note warns about.** Newest section was 2026-08-26 with eight lines while the
  file held **64** unarchived lessons across six dates. Regenerated from the
  headings (a script, not a judgement). **An index not regenerated in the same
  edit as the entry is stale by one immediately and by dozens within a week.**
- `parlays.scouting_facts` is public, so the slate reads the scout state
  through the one correct join (fixture, not leg ticker) rather than a second
  reader that would disagree with the ladder.

### The status line now names the clock that binds — Joe's ask, same session

The row I flagged one turn earlier as "pre-existing and unexamined" is fixed.
`StatusLine` voices one warning by fixed priority, and the priority put the
**Kalshi quote** first and the **sportsbook consensus** second. That is
backwards, and the reason is not taste — it is `_live_ages`' own rule, written
out in full four hundred lines away:

> `actionable` is the ODDS clock, not both clocks. The order endpoint re-reads
> the Kalshi quote inside the request, so the recorded quote's age no longer
> decides whether an order is accepted.

So a stale quote means *the price printed here is a memory*; a stale consensus
means *the row is not actionable at all until a credit re-buys the books*.
Outside an odds window **both are stale on most rows**, so the old order voiced
the less binding of the two on exactly the rows where the difference decides
what to do — and the more binding one is the only one with an action attached.

Branches swapped, drift stays third. Verified on a rendered page against a row
seeded to the live shape (consensus 2042s / limit 900s, quote 134s / limit 30s):

    Books last read 35 min ago — past the 15 min limit. Not actionable until
    the odds are refreshed.
    EVIDENCE 5/7 CHECKS · 1 NOT CHECKED
    sportsbook consensus 2075s old, limit 900s; Kalshi quote 167s old, limit 30s.

The `quote 3m` column still renders in the negative colour, so the price
caveat is not lost — it is demoted, which is the whole intent.

**DEPLOYED `b09ad5c`, verified** — `/api/health` `git_sha` reads
`b09ad5c9e3bfd6b6f61b7cb0b8ee39a1cba24b0f`, status ok, recorder writing 14s
before the read. The first dispatch was refused by the classifier again (that
call bundled `git status` with it, against the standing "issue commands
singly" rule); the single dispatch went through.

**What the live screen could and could not show.** The odds window was OPEN at
the time of the read (`window open · fresh for 12m`), so the consensus was
fresh on every row and the odds branch correctly did not fire:

    Kalshi quote is 55s old — past the 30s limit, so the ask shown may already
    be gone.
    EVIDENCE 6/7 CHECKS · 1 NOT CHECKED
    Kalshi quote 55s old, limit 30s.

That is the **ordinary case confirmed intact** — a fresh-consensus row still
gets the quote caveat, and the trust line reads 6/7 rather than the 5/7 it
read when the consensus was also stale. **The both-stale case, which is the
one that changed, was verified on a local render against a row seeded to the
live shape, not on live** — reproducing it on live would mean waiting out the
window, and the branch that fires is not window-dependent. Stated rather than
glossed.

**`OpportunityCard` already had this right and always did** ("A stale quote is
no longer what makes a row unbettable"), so the slate was the only inverted
site. That is worth knowing: the correct behaviour had a precedent in the
codebase the whole time.

**Two lessons, both at the top of `tasks/lessons.md`, and the first is the one
to carry:**

- **Code and its own comment agreeing is not verification.** The docstring
  numbered the priority, the branches matched it exactly, and both had been
  wrong since they were written. A comment and the code beneath it are one
  source, not two; the check that matters is against the rule they serve,
  which lives somewhere else. A defect of this shape leaves **no inconsistency
  anywhere in the file**, so no amount of reading that file finds it.
- **A test named for a relationship must read both artifacts.** My first
  version of `test_the_stated_priority_matches_the_branch_order` read only the
  docstring and compared it to a literal — so the exact mutation it is named
  for (swap the branches, leave the comment) left it **green**. Caught by
  running the mutation. It now reads both and compares them to each other.

### The cockpit refuses to be framed — Joe's ask, same session

Found incidentally: the same-origin iframe used for the 390px read worked
because **nothing stopped it**. The live instance sent neither
`X-Frame-Options` nor a CSP `frame-ancestors`, so any page on the internet
could load the signed-in cockpit in an invisible frame, float a decoy over it,
and collect a click the reader could not see.

**Server-side re-validation is not a defence against this one**, which is what
makes it worth the deploy rather than a note: `POST /api/manual-orders` sends
a real immediate-or-cancel order (`MANUAL_ORDERS_ARE_DRY_RUNS = false` since
2026-08-26, ADR 0073), and a clickjacked click is a genuine click from a
genuine session — valid cookie, fresh order token, every check passes.

Set in `frontend/src/middleware.ts`, which runs **before** the `/api` rewrite.
Three decisions:

- **`'self'`, not `DENY`.** An attacker cannot serve a page from this origin,
  so same-origin framing is not a way in; `DENY` would block only our own
  embedding and buys no security for it. It also keeps the 390px harness
  working — the one known way to get a true phone viewport against an authed
  page, and `DENY` would have deleted that tool in exchange for nothing.
- **Both headers.** `frame-ancestors` supersedes `X-Frame-Options` where both
  are understood; the legacy one covers anything without CSP. They say the
  same thing and a test pins that they cannot disagree.
- **Not a full CSP, deliberately.** No `script-src`, no `style-src`. Those
  have a real chance of breaking a page, and shipping them inside a framing
  fix makes one deploy that cannot be reasoned about. A test refuses any other
  directive.

Applied through one funnel rather than at each `return`, because the
middleware has **five** exits — including the demo's ungated one, which is the
instance an attacker can reach with no password at all — and a header set on
four of them is absent exactly where somebody adds a sixth. The guard counts
bare `NextResponse` returns rather than asserting a number, so a sixth exit
fails it until it is wrapped.

**VERIFIED ON THE WIRE, and the read corrected a claim the source could not
have.** This entry first said one place covers "every page and every proxied
route". Reading the live headers says otherwise:

    /login /slate /market/{ticker} /parlays   both headers, 200
    /api/health, /api/slate (200)             NEITHER header
    /api/slate (401 from the middleware)      both headers

**A successful `/api/*` response does not carry them.** That path is a rewrite
to uvicorn and Next serves the backend's own headers, discarding the ones set
on `NextResponse.next()`; the 401 carries them only because the middleware
constructs that response itself.

**The exposure is closed anyway, and the reason is worth stating rather than
assuming.** Clickjacking needs a surface to click; a JSON body has none, and
every HTML page carries the header. So this is a gap in coverage, not an open
door — but it would become one the day an `/api/*` route returns HTML. Left
unpatched deliberately: fixing it in `next.config.ts` would put the policy in a
second place, and two places that must agree is the drift this repo keeps
recording. Written down in the test file's own "does not establish" list so
nobody re-derives it.

**And note which check found it.** The source tests were green and would have
stayed green forever; the header only reaches a browser if the framework
propagates it, and no amount of reading the middleware says whether it does.

**One thing the tests had to learn, and it is the third time today.** They
first grepped the raw file and three failed — on the *comments*, which discuss
`DENY`, `script-src` and `style-src` by name to explain why each was rejected.
A guard on the code must not be able to read the comment; `_source()` strips
comments before asserting.

### THE SITE WAS SLOW, AND IT WAS TWO THINGS — Joe's report, same session

**Read this before touching capacity or the slate query.**

#### 1. The recorder was starving the API — fixed by scaling

Joe said "the site is still slow". It was worse than slow: **`/api/slate` took
30.3 seconds and then 500'd**, while `/api/bets` answered in 324ms.

The live pass log said why in its own words:

    a QUOTE pass took 75.0s; with a 15s fast interval and 15% jitter the
    worst-case gap between confirmations is 92.3s, past the 30s Kalshi
    quote limit

A 75-second pass on a 15-second cadence means the recorder never stops, and on
`shared-cpu-1x` it shares that one core with the Python API and Next's SSR.
Everything queued behind it; the 500 was the Next proxy giving up
(`Failed to proxy ... socket hang up, ECONNRESET`), and `flyctl ssh` hung twice
on the same box.

**The season is what changed, not the code** — 663 events discovered, 7,838
markets quoted per pass. `CLAUDE.md` predicted exactly this when NCAAF and NFL
came into scope. **Not today's deploys**: `limit=5` failed identically, and
`/api/board` was slow without going near any of it.

**Scaled to `shared-cpu-2x`** (Joe's call, ~$11/month against ~$5.70). Same
workload, measured after:

    QUOTE pass      75.0s  ->  4.6s and 3.7s
    /api/health      343ms ->  105ms
    /api/bets        324ms ->  117ms
    /api/board     4,566ms ->  1,620ms
    /api/slate    30,311ms + 500  ->  200 (and see below)

`performance-1x` was NOT taken: a dedicated core is ~$31/month on an instance
whose bankroll is $100. **The trigger for spending it is written down** — if a
QUOTE pass again exceeds its cadence at 2x, shared CPU is credit-throttled and
this loop runs continuously rather than in bursts, and that is the moment.

#### 2. Three routes aggregated the whole snapshot history per request

Independent of capacity, and Joe approved fixing it. Measured on a
**live-shaped local database** (55,777 recommendations, 199,500 snapshots,
7,980 markets) rather than guessed:

    anchor MAX/COUNT over 55,777 recommendations      8.2 ms
    in_window COUNT                                   8.0 ms
    odds_snapshots derived table alone               77.3 ms   <- the cost
    full rows query (limit 100)                      85.4 ms

**The hypothesis going in was wrong and the measurement is what said so.** The
plan was an expression index on the basis (`MAX(created_ms, COALESCE(...))`),
because two full scans of 55,777 rows *looked* like the cost. They are 8ms.
Had I shipped the index I would have written a schema migration against a live
1.5 GB volume for nothing.

The real cost: a derived table aggregating `odds_snapshots` to get
`MIN(commence_ms)` per fixture — **unbounded by what the screen shows**, so
`limit=1` paid exactly what `limit=100` paid. `/api/market/{ticker}` was worse:
it grouped the entire table with **no `WHERE` at all**, to answer a question
about one market. `/api/ledger` had the same shape and was also 500ing.

All three now read the kickoff for the rows they actually return, in one
bounded query — the "one read per fixture, not per row" idiom
`book_quotes_for_event` and `scouting_facts` already use here:

    ledger page query          77.1 ms  ->   2.1 ms
    market detail fixture      86.8 ms  ->   0.1 ms
    /api/slate  limit=1       200    ms  ->  92    ms
    /api/slate  limit=100     301    ms  ->  134   ms

**`MIN(commence_ms)` per fixture is unchanged** — same value, same definition
the scorer uses, which is what ticket #26 exists to protect. The guard caught
a real slip while making the change: `item["league"] = row["league"]` appears
in both `/api/board` and `/api/slate`, so the first edit attached the kickoff
to the wrong route and `test_slate_kickoff_matches_detail.py` went red on the
list-vs-detail claim immediately.

#### Verified on live — `15fd50f`

Sampled from the browser with the session cookie, alternating both routes,
after one warming read (the first request following a deploy pages the
database back in and is not representative):

    /api/slate    p50  340ms   min 311   p90 534    0 errors
    /api/ledger   p50  372ms   min 343   p90 1,343  0 errors
    QUOTE passes  3.7 - 4.6s, eight consecutive

**The whole arc on `/api/slate`, one number per stage:**

    30,311ms + HTTP 500   before anything
       805ms  (p50)       after scaling to shared-cpu-2x
       340ms  (p50)       after bounding the aggregates

Four `socket hang up` lines remain in the log window, all timestamped before
this deploy. **Watch that count** — it is the honest instrument for whether
the proxy is still giving up on anything, and it should now stay at zero.

### Still open

1. ~~The slate row and market detail surfaces for the sweet spot.~~ **DONE —
   ADR 0093.**
2. ~~Deploy this.~~ **DONE — `11bd2c0` is live and verified on the screen.**
3. ~~The StatusLine names the less binding clock.~~ **FIXED and DEPLOYED (`b09ad5c`).**
4. **Watch whether `database is locked` recurs.** `loop_failures` is the
   instrument. If the rate holds, the two unexamined suspects are the retention
   prune over `kalshi_quotes` (451 MB) and the WAL `TRUNCATE` checkpoint.
5. **`odds_snapshots` retention** — ADR 0086 bought headroom, not a bound.
6. **`user_not_found` on shard 3** and **Joe's shard allocation** — both his,
   both money-touching, both carried.
7. ~~Read the phone.~~ **DONE — 390px verified on live, both surfaces**, with
   the same-origin iframe method recorded above. Reuse it; `resize_window` is
   a no-op that reports success.
8. ~~The cockpit can be framed.~~ **DONE — see the section below.**
9. ~~The sweet spot renders at 9.6px on the slate row, the smallest text
   there.~~ **DONE — Joe took it. The slate row passes `size="panel"` (12px),
   matching the gloss and status lines beside it.** The parlay card keeps
   `compact`: six legs share one `text-[11px]` list there, which is what
   compact was sized for.

---

## 2026-08-31 — the lock holder was found, and a wording rule lost to typography

**Live is on `badd88e`, verified** — health ok, recorder writing, no
post-boot errors. Suite **5,416 passed / 10 xfailed** on that tree.
`main` is level with it apart from session-file commits.

Deployed this session, each verified against `/api/health` `git_sha` rather
than assumed: `0d5b992` (sweet spot + provenance chart, ADR 0089/0090),
`c05cb1f` (the typography fix), `984cecc` (the lock holder, ADR 0091),
`badd88e` (the scoring pass survives a refused write, ADR 0092).
`tasks/NEXT.md` was split at **87.3%** BEFORE this entry was written — five
2026-08-27 entries to `archive/next-2026-08-31.md`, verbatim, verified moved
exactly once and named in the index. It is 68.4% now.

### Open item 8 is CLOSED — ADR 0091

`OperationalError: database is locked`, four to five a day, killing a scoring
pass and losing closing lines that cannot be re-observed. `BUSY_TIMEOUT_MS =
5_000` was already set and passed explicitly, so it was never a missing
timeout: **something held the write lock longer than five seconds.**

The portfolio poller:

    await poll_balance(...)      # INSERT -> SQLite's write lock is taken
    await poll_fills(...)        # network round trip, lock HELD
    await poll_settlements(...)  # network round trip, lock HELD
    await poll_positions(...)    # network round trip, lock HELD
    conn.commit()                # released, three round trips later

**The frequency is what found the right site.** The same shape exists on the
12-hour mirror and on the 300-second fast branch. The mirror was found first
and flagged as not fitting — twice a day cannot produce four-to-five failures
a day. 288 times a day can. Both fixed.

Worth carrying: `poll_fills`, `poll_settlements` and `poll_positions` were each
moved onto the fast cadence on three different dates for three good recorded
reasons (2026-08-21 ruling, ADR 0064, 2026-08-29). **Each widened the window
and none noticed**, because the transaction boundary was never the question
being asked — the comment beside it reasons carefully about *rollback scope*
and never about *lock duration*.

**NOT claimed: that the symptom is gone.** The frequency now fits where it did
not, and a fit is not a proof. If failures continue at this rate, the next
suspects are the retention prune over `kalshi_quotes` (451 MB) and the WAL
`TRUNCATE` checkpoint — neither examined. Checked and cleared: every
`estimate_match` helper commits its own writes, so nothing holds the lock
across the 300s sleep.

The guard checks the **shape** with `ast`, not a stopwatch, and **produced two
confident false findings before it was right** — a `while` header counted as a
write because something nested inside it wrote, and state carried across an
`if`/`else` so one branch was blamed for the other. Both recorded in its
docstring.

### The sweet spot shipped, then failed on the live screen — and the fix is a lesson

Checked the rendered page rather than trusting the tests, and found what they
could not see. A clean leg read:

    EVIDENCE 7/7 CHECKS · 1 not checked

Score in uppercase mono, caveat in lowercase prose. **The honest half was
typographically subordinate to the flattering half**, which is the exact
subordination ADR 0090 exists to prevent — defeated by styling, with every
wording test green. The unknown now lives inside the score's own span; the new
guard asserts the *nesting*, not the presence.

**The score is already doing real work.** The LONGSHOT card reads
`EVIDENCE 4/6 CHECKS · 2 not checked / 1 book(s), need 2; no second book to
disagree with` — the least-evidenced thing on the screen finally saying so.

### Still open

1. **The slate row and market detail surfaces** for the sweet spot. Joe chose
   all three; one is built. The module is surface-agnostic so they consume the
   same score rather than computing their own.
2. **Watch whether `database is locked` recurs.** `loop_failures` is the
   instrument and it already records them correctly. If the rate holds, see the
   two unexamined suspects above.
3. ~~`run_scoring_pass`'s `try/except` wraps the FETCH, not the store.~~
   **DONE — ADR 0092, on Joe's word.** The store is inside the guard the
   docstring already promised; a failure now costs one line rather than the
   pass. `lines_unstored` is its own counter (a 404 is history the venue no
   longer has; a failed store is history we held and dropped), and a
   `rollback()` runs before continuing, because a lock can refuse the COMMIT
   rather than the execute and an open transaction would fail every subsequent
   store. **Two of the four guards were decoration first** — see the ADR.
4. **`odds_snapshots` retention** — ADR 0086 bought headroom, not a bound.
5. **`user_not_found` on shard 3** and **Joe's shard allocation** — both his,
   both money-touching, both carried.
6. ~~`tasks/lessons.md` is 86.3% and will need its own split.~~ **DONE.**
   Split at 87.8%: fifty lessons, 2026-08-25 back to 2026-08-18, moved to
   `archive/lessons-2026-08-31.md` verbatim. Now **52%**, a deeper cut than the
   last one on purpose — the file was split twice in three days.
   **Seven index markers were flipped in the same edit**, which is the half
   that matters: moving entries without moving their index lines is a data loss
   with a table of contents. Both session files are now comfortable
   (`NEXT.md` 70%, `lessons.md` 52%).

---

## 2026-08-31 — the sweet spot, and the graph Joe asked for

**Live is on `0d5b992`, verified.** Suite **5,408 passed / 10 xfailed**,
collected on a frozen tree with the ADRs added after it finished.

Two things Joe chose from options put to him, both shipped:

**ADR 0089 — the provenance axis reaches the parlay card.** Each leg shows
where its number came from, behind a tap, reusing `DispersionStrip
variant="chart"` UNCHANGED so the three properties the 2026-08-21 ruling
preserved cannot drift. **This is a SECOND surface** for a chart that ruling
deleted from the slate row and ADR 0068 restored on `/market` alone — Joe's
choice is the authority, and the ADR exists so nobody later reads the ruling
and concludes the card is in breach.

**ADR 0090 — the sweet spot scores trust, not edge.** He asked for "the
overall score that determines a yes or no on what is a good bet"; put the
evidence, he chose trust. The exclusion of edge is arithmetic:
`beta = -0.141`, every interval below the registered 0.40 threshold, so a
composite containing the gap ranks the LEAST trustworthy rows highest.

`backend/core/trust.py` counts the desk's own existing refusal criteria —
**no invented thresholds** (every limit from the config that already enforces
it; NO argument has a default, because a default is a second definition),
**no invented weights** (a count, with EVERY failure named — picking one
"binding" constraint would smuggle in the importance weight, which is
`SuppressionResult.reason`'s own argument), and **unknown is never a pass**
(folding it in makes the least-examined row score highest, the same failure
`suppression.py` records for a 0.0 width; that mutation turns 12 tests red).

The screen never renders the number bare: a lone "6/8" beside a bet reads as
"a 6-out-of-8 bet". It reads `evidence 6/6 checks · 2 not checked`, names every
failure, and a clean row still says it is *not about whether the bet wins*.

**Wiring proven on the wire**: removing the route's threshold argument turns
five route tests red — the guard against the built-but-never-called failure
this repo has hit four times.

**Still open from Joe's own choice: the SLATE ROW and MARKET DETAIL surfaces.**
He picked all three. The module is surface-agnostic precisely so they consume
the same score rather than computing their own.

---

## 2026-08-31 — the Scout reaches the parlay legs, and the budget says it can only flag them

**Live is on `cd9e842` — the scout slice is DEPLOYED and verified.** Health
ok, six passes since boot, no post-boot errors, and `candidate_ms` holds at
**58-63 ms**, so the v31 index survives the deploy.

**Two readings I got wrong on the live box tonight, both corrected before they
reached this file, and both the same shape — a distribution read off the
convenient slice:**

- The recent `loop-rss` tail looked like passes 14-18 MINUTES apart. It was
  the boot region, which is mostly `kind=full`; full and quote passes run on
  different clocks. Over 2.4 h the real distribution is **30 quote + 10 full,
  median gap 19 s, min 16 s**. `pass-gaps` — the committed detector for
  exactly this — reported 0 gaps over its 1200 s threshold the whole time.
- The index before/after split on deploy wall-clock (see the previous entry).

**Read the instrument that exists before reading a tail by eye.**

### The Scout on the parlay legs — ADR 0088

Open item 3 from the previous entry, built as a first slice. Joe's ruling was
*"the Scout gates eligibility and flags, and never moves the price."* **The
flagging half is shipped. The gating half is arithmetically impossible and
that is the finding, not an excuse:**

    a briefing = 4 metered calls (2 staff, master, pro-bettor seat)
    AGENT_MAX_CALLS_PER_DAY    = 24  -> 6 convenings
    AGENT_MAX_SEARCHES_PER_DAY = 60  -> 5 convenings   <- binds first

**Five convenings a day**, against a ladder of six cards of up to six legs.
Scouting the legs of one card could spend the day. So automatic gating cannot
exist at this ceiling, and the ADR records the gap rather than shipping half
the ruling silently.

What the card does now: shows what the desk **already knows** about each leg's
game, read from `scout_briefings` rows that exist. **Zero calls, zero credits,
zero tokens.** Three properties, each pinned by a mutation observed red:

- **The join is by GAME, not by market.** `scout_briefings.ticker` is whichever
  market was in front of Joe when he convened the desk; a briefing describes a
  *fixture*. Joining leg-to-briefing by ticker showed a game as unscouted while
  its own briefing sat in the table. It runs through
  `kalshi_markets.event_ticker` (`idx_markets_event`).
- **Six states, because absence has three meanings.** `absent` (nobody looked
  — the ordinary case at five a day), `filed_nothing` (looked, nothing to say)
  and `refused` (a ceiling turned it away) are not interchangeable, and only
  the middle one is information about the game.
- **A gap is a flag.** Every tile that is not `clear` flags, including
  `unconfirmed` and `stale_only`. `BoardTile` has four states rather than a
  boolean because the first real briefing's most decision-relevant fact was a
  gap — the weather unchecked — and flagging findings alone renders that as
  calm.

Screen rules, asserted over the component source because they are about what it
is *allowed* to do: no scout value in arithmetic, none in a sort (ADR 0071
§2.5 — and here ranking by scout state would rank by *which games Joe happened
to tap*), and no colour, because the palette's red means lose (ADR 0081).

**`leg_facts` costs a third statement, still one for the whole ladder.** The
O(1)-in-legs guard now asserts the exact set of fact families rather than the
number 2, so a fourth has to come and say what it is.

### NOT built, and each is a decision rather than an oversight

- **Automatic gating or dropping a leg.** The ceiling forbids it.
- **A per-leg "send the desk" button.** The obvious next step, and it spends a
  fifth of the day's budget per tap — so it wants its own decision about what
  the screen says about the four remaining.
- **The graphs Joe asked for** (*"remember this is a cockpit"*). This slice
  ships words. Charting a field that is `absent` on most legs would be worse
  than saying so.

### A test in this change asserted a bug that cannot happen

The first shallow-copy guard claimed "mutation observed red" and stayed green
when the mutation was actually run — `_scout_facts` builds its own dict with
its own list, so the aliasing it described could not occur. **Exactly ADR
0087's failure, one file and one day later.** Rewritten to assert the
invariant that is load-bearing: no leg is handed `_NO_FACTS`'s own list, which
a single future in-place `append` would poison for the life of the process.
That version goes red.

### Open — pick up here

1. **Deploy the scout slice.** `main` is ahead of live by it.
2. **The per-leg convening button** — needs Joe's call on who may spend a fifth
   of a day's budget from a card, and what the screen says about the rest.
3. **The graphs.** Joe's cockpit ask, still unmet on this screen.
4. **`odds_snapshots` retention** — ADR 0086 changed the constant and left the
   growth term. `fair_prices` (529 MB) and `kalshi_quotes` (451 MB) are the two
   larger unretained btrees.
5. **`user_not_found` on shard 3** — carried. Blocks every baseball hand bet
   regardless of funding; the falsifying test is a few cents moved to shard 3.
6. **Joe's shard allocation** — carried. The 23:20Z auto-cancel returned $1.81
   to shard 1; shard 0 is ~$0.002 and shard 3 is $0.
7. **Time the v31 index build at boot.** The grace period went 40s → 120s to
   cover it and the deploy succeeded, so the build is bounded below the failure
   point — but the deploy log was never read for the actual duration.
8. **`OperationalError: database is locked` — SHARPENED 2026-08-31, and it is
   worse than the entry below said.** A fifth occurrence at 05:32:45Z gave the
   traceback the earlier four lacked:

       scoring.py:264   run_scoring_pass -> store_closing_line(conn, line)
       clv.py:183       conn.execute(INSERT INTO closing_lines ...)
       sqlite3.OperationalError: database is locked

   Three things follow, and the third is the one that changes its priority:

   - **`BUSY_TIMEOUT_MS = 5_000` is already set** on every connection, and
     `db.py` records that it is passed explicitly rather than inherited. So
     this is not a missing timeout — **something holds the write lock for over
     five seconds.** The WAL `TRUNCATE` checkpoint is the obvious suspect: on
     2026-08-31 a `wal_ckpt_error: database table is locked` landed at 00:56Z,
     one minute after the 00:55Z loop failure. Not established.
   - **`store_closing_line` commits per row inside a per-market, per-horizon
     loop**, so a scoring pass takes and releases the write lock once per
     closing line — many small windows for a slow holder to collide with.
   - **The `try/except` in that loop wraps only the FETCH, not the store**
     (`scoring.py:251` appends to `counts.errors` and continues). A lock error
     on the store therefore escapes `run_scoring_pass` and kills the whole
     pass, **abandoning every remaining market in the loop.** And
     `fly.live.toml` says why that matters: *"an unrecorded close is an
     observation lost forever, since candlesticks age out."*

   **So the earlier note that it "recovers each time" was right about the loop
   and wrong about the record.** The loop recovers; the closing lines that
   pass would have written do not. Each occurrence is potentially permanent
   evidence loss on the registered CLV record, ~4-5 times a day.

   Not fixed: the obvious candidates (widen the timeout, batch the commits,
   or catch-and-continue on the store) each change the scoring path and one of
   them would hide the contention rather than fix it. Wants a look, not a
   patch.

   *(original entry follows)* `OperationalError: database is locked` on FULL
   passes, four times in 24 h
   and NOT caused by anything shipped tonight: 2026-08-30 07:25Z, 09:10Z,
   22:13Z and 2026-08-31 00:55Z — three of the four predate the index
   (23:34Z). Each carries `consecutive_failures` 2-3, so the loop recovers.
   The same contention shows on the checkpoint beside it
   (`wal_ckpt_error: database table is locked`, 00:56Z), which is benign by
   design: a PASSIVE checkpoint that cannot get the lock retries next pass.
   `loop_failures` is recording them correctly, which is the part that works.
   **Nobody has looked at what holds the write lock during a full pass.**

---

## 2026-08-30 — the deadline the screen promised had never once been kept

**Live is on `9832834`, which is `main` and `origin/main`.** Deploys this
session, each verified against `/api/health` `git_sha` rather than assumed:
`99625ff` (last session's card work), `351f594` (the bid watcher), `9832834`
(the covering index, schema v31, verified on the live volume).

**One deploy failed first and it was NOT the change.** Fly's remote Depot
builder was unavailable — `error releasing builder: deadline_exceeded`, then
`failed to list workers: authentication handshake failed: EOF` — so the image
never built and the migration never ran. A straight re-dispatch succeeded.
**Read the log before diagnosing a failed deploy**; nothing about the schema
change was exercised by that failure.

**Splitting the two deploys earned its keep.** The money fix went out and was
verified on Joe's real order 25 minutes before the schema change even built.
Had they shipped together, the watcher fix would have sat undeployed behind a
builder outage that had nothing to do with it.

**Test baseline: 5,343 passed / 10 xfailed in 10:22** on the final tree, with
nothing edited after the run started and the tree clean throughout. **Every
step of the delta from the 5,243 that stood at session start was taken by
collecting BOTH trees, never by reasoning about it** — the rule this line has
been broken by seven times:

    5,243  a31d12c   (inherited, correct about that tree)
    5,332  99625ff   +89, the ten commits that were already committed
    5,340  + index   +7 new guards, +1 `[31]` case the migration harness
                      parametrises automatically -- found by diffing two
                      `--collect-only` runs, not by arithmetic
    5,343  + watcher +3 `TestTheWatcherDrivesARealCancel` guards

### The thing to read first: a live money promise was never kept

Joe's resting bid — 9 contracts at 20.1c, shard 1 — passed its 23:00:00Z
auto-cancel and stayed `resting`. The watcher was not dead. It ran at
23:00:16Z, 23:01:16Z and 23:02:16Z, once a minute exactly as designed, and
raised the same thing every pass:

    RuntimeError: KalshiRestClient used outside its context manager.

`run_loop.py` passed `lambda: KalshiRestClient(cfg)` — constructed, never
entered — so `cancel_order` raised before a request was built. **Every
auto-cancel had failed since ADR 0084 shipped the feature.**

**Fixed, deployed, and verified on the real order** — not on a test:

    status             cancelled
    cancelled_ms       2026-08-30T23:20:58.392Z
    cancel_reduced_by  9.0        <- all nine still working, none filled
    cancel_reason      the first leg has started

Two things contained it, both design rather than luck: the failure path leaves
the row working and **never** writes "cancelled" over a live order, so the
table stayed honest throughout; and `/api/parlays/bids/{id}/cancel` was
unaffected, because `combo_api()` passes an explicit `client=`. **The manual
cancel always worked. Only the unattended one did not.**

**Why five tests missed it, and this is the transferable part.** `FakeApi`
answered `cancel_order` whether or not it had been entered — it modelled a
client that does not exist, so the defect was invisible *by construction*.
Making it as strict as the real client turned three existing tests red, all of
which had been passing a client in a state production never produces, and one
of which — `test_the_row_stays_working_when_the_venue_refuses` — was passing
**for the wrong reason**, on the context-manager error rather than the venue
refusal it claims to test. ADR 0087; lesson at the top of `tasks/lessons.md`.

And the wiring guard asserts the *string* `"watch_bids_forever(args.db"`
appears in `run_loop.py`. It does, and did throughout. **A source grep can say
a call exists; only running it says the call works.** Second instance of a
pattern already in this file, first one that cost a feature its whole function.

### The covering index — ADR 0086, schema v31

Open item 1 from the last entry, built and shipped. `_match_candidates` had
`sport_key` in no index, so the plan seeked `idx_odds_commence` to the 24h
floor and scanned every sport forward, then sorted through a temp B-tree. On
live it reached 27.7s and failed the Fly health check at 22:06:03Z — which
read from outside as "the scout desk returned 500".

**The covering form, and the plans are the argument, not the stopwatch:**

    baseline  SEARCH ... USING INDEX idx_odds_commence  | USE TEMP B-TREE
    narrow    SEARCH ... USING INDEX (sport_key=? ...)  | USE TEMP B-TREE
    covering  SEARCH ... USING COVERING INDEX (sport_key=? AND commence_ms>?)

At 1.5M synthetic rows (520,160 past the floor, to keep 73 fixtures): read
**394ms → 0ms** warm, sweep write **3ms → 7ms** per 900 rows at n=15, index
52.8 MB. All three shapes return the same 73 fixtures, **compared as sets and
not as counts**. Instrument committed: `scripts/measure_odds_scan_index.py`,
which imports `runner.MATCH_CANDIDATE_SQL` rather than copying it.

**This is not the index refused on 2026-08-26.** That one changed no plan, the
refusal stands, and its own stated test — *does the plan change?* — is the one
applied here.

The grace period went 40s → 120s: `migrate_db.py` runs before uvicorn binds,
and this builds an index over a 244 MB table on a 2 GB box.

**The migration guard was written wrong first and the ADR says so.** Winding a
database back to v30, calling `init_db` and asserting the index is present
**passes with the v31 step deleted** — `init_db` runs `migrate` and then
`executescript(schema.sql)`, which carries the same
`CREATE INDEX IF NOT EXISTS`. Two producers, one observable state, so the
assertion attributed nothing. Calling `migrate` directly made it real.

### Closed without a code change: the combo maker fee

Open item 5. Kalshi's 2026-08-22 changelog does put the combo maker multiplier
at 0.5 against `MAKER_COEFFICIENT`'s implied 0.25 — and **it reaches nothing**:
`parlays.py` is fee-free by ADR 0046 with the caveat travelling beside the
number, `combo_orders.py` says in its own docstring that it does not price
fees, and `analysis/joint_bound.py` — the only `maker=True` caller in the repo
— has **no production caller**. Changing `MAKER_COEFFICIENT` would be wrong:
0.0175 is the single-market coefficient and is correct there. A combo branch
would need its own registered look, which ADR 0046's registration forbids
fitting from existing data.

### Also read this session

`db-sizes` on live, for anyone sizing a change against the volume
(2,072,317,952 bytes of 5 GB, 18.9 MB reclaimable):

    fair_prices             529,326,080     kalshi_quotes      451,235,840
    idx_quotes_ticker_time  398,708,736     odds_snapshots     244,387,840
    idx_odds_event          136,421,376     idx_odds_commence   25,092,096

**`flyctl ssh console -C` output is reliable here** — an earlier "it returns
nothing" read was a 120s timeout on a `dbstat` query over a 2 GB database, not
a lost stream. Give it 300s.

### OPEN — pick up here

1. ~~Read the real index size on live.~~ **DONE, and the index is verified
   working on live — `9832834`.** `idx_odds_sport_commence` is **150.3 MB**
   (the ADR's bracket of 136–244 MB held; the synthetic 52.8 MB understated it
   by 2.85x, in the direction the caveat named). The database is 2.25 GB, 45%
   of the volume. **`candidate_ms` p50 438 ms → 60.5 ms on live, 7.2x**,
   against the committed pre-index series (n=182). The synthetic model
   predicted the *before* to within 10%, which is why it is worth keeping.
   ~~The tail is unassessed at n=12.~~ **Re-read at n=102 over 1.7 hours, and
   the tail is closed:**

       no index    n=46    p50 407  p90 427  max 900   >200ms: 46 (100%)
       v31 index   n=102   p50  60  p90  67  max  78   >200ms:  0 (0%)

   **The split is on `db_kb`, not on the deploy clock, and that is not a
   detail.** `loop_rss.jsonl` survives deploys, so one file holds both regimes.
   Cutting at the wall-clock time I dispatched the deploy put 79 with-index
   passes into the "before" bucket and produced "pre-index p50 63 ms — the
   index does not move the median", which was one edit from being published as
   a correction to a claim that was right. The real boundary is `db_kb`
   stepping +147 MB at 23:34:56Z, against a separately measured 150.3 MB index.
   Lesson at the top of `tasks/lessons.md`.

   Still open on this item: **how long the index build actually took at boot**
   (the grace period went 40s → 120s to cover it, the deploy succeeded, the
   margin is unknown), and the committed series' p99 of 5,451 ms / max of
   11,202 ms — 1.7 hours has not run long enough to meet whatever produced
   those.

   Also still unmeasured: **how long the index build actually took at boot.**
   The grace period was raised 40s → 120s to cover it and the deploy succeeded,
   which bounds it below the failure point but leaves the margin unknown. The
   deploy log was never read for the duration.
2. **`odds_snapshots` still has no retention rule.** ADR 0086 changed the
   constant and left the growth term alone, and says so. `store/retention.py`
   already names this table as deliberately out of scope. `fair_prices`
   (529 MB) and `kalshi_quotes` (451 MB) are the two larger unretained btrees.
3. **Scout on the parlay legs** — carried from the last entry, unstarted.
   Joe's ruling in his words: the Scout **gates eligibility and flags** and
   **never moves the price**. He also asked for real graphs: *"remember this
   is a cockpit."*
4. **`user_not_found` on shard 3** — carried, unstarted. Blocks every baseball
   hand bet regardless of funding. Falsifying test is cheap: move a few cents
   to shard 3 and re-post.
5. **Joe's shard allocation** — carried. Shard 0 was down to $0.0020 and shard
   3 to $0 before tonight's cancel returned $1.81 to shard 1. Worth telling him
   before he tries a single-market hand bet.
6. ~~A sweep for the ADR 0087 pattern elsewhere.~~ **DONE. `bid_watch` was the
   only one, and the mechanism was checked per task rather than inferred from
   the absence of `factory()`:**

       portfolio-poll   gets the ENTERED `kalshi` from the outer `async with`
       hedge-watch      LiveQuoteSource._api() builds with `client=`, so the
                        guard is satisfied -- and that class is PROVEN working
                        on live through its other callers (the API's
                        `live_quotes()`, `/api/health` live_quotes_available)
       bid-watch        the unentered factory. Fixed, ADR 0087.

   **But the audit found a different thing, and it is the one to carry.** The
   empirical question — *has this unattended feature ever been observed doing
   its job on live?* — is what actually caught `bid_watch`, and one task still
   answers it badly:

       poll_log                  59 pages   portfolio-poll works, at length
       venue_balance_snapshots   17 pages   and succeeds
       parlay_positions           1 page    a handful of rows at most
       parlay_position_legs       1 page

   `watch_hedges_forever` gates its whole body on `anything_in_progress`, which
   needs a `parlay_positions` row. Joe has never recorded one, and no cycle has
   ever logged an alert or a settlement. **So `watch_once` — the hedge
   watcher's entire inner body — has almost certainly never executed in
   production.** That is not a defect and it is precisely the state `bid_watch`
   was silently broken in for its whole life: wired, tested, never exercised.

   **The cheap generalisation, NOT built and offered rather than assumed:**
   `/api/health` already reports `recorder.last_write_ms`. A sibling block
   naming each unattended feature and the last time it actually *did its job*
   (not merely ran) would have made tonight's defect visible in seconds instead
   of by accident. Worth a decision before it is worth code.

---

## 2026-08-30 — the desk placed its first real order, and the venue has no one to fill it

**Live is on `ab3447f`. `main` is ahead by the reshaped parlay card, ADR 0085
and the liquidity census — written, tested, NOT deployed.** Joe stopped the
session deliberately at this point; the next one ships them.

### What Joe hit, in the order he hit it

He could not price a parlay: every "Price on Kalshi" tap was refused *"the
slate has moved since this card was served"*, and refreshing restarted the
same race. Three separate defects were under that one symptom, and a fourth
turned up while fixing them.

**1. The WAL had no checkpoint caller.** Nothing in this repo had ever called
`wal_checkpoint`. Caught live 17:21-17:53Z: 16.6 -> 99.5 MB in 25 minutes,
monotone, pass cadence stretching 20s -> 2.6 min, `candidate_ms` 0.46s ->
36.6s, `/api/health` at 3.4s. A machine restart was the only thing that had
ever reset it (28 KB after, health 0.37s). Fixed: `store.db.checkpoint_wal`
plus `journal_size_limit = 0`, called once per pass from
`run_loop.maybe_checkpoint` — PASSIVE below 32 MiB, TRUNCATE above — with
`wal_ckpt_{mode,busy,log_frames,moved_frames,error}` on every `loop_rss` line.
`docs/measurements/2026-08-30-the-wal-episode-caught-live-and-what-it-does-
not-show.md`.

**VERIFIED WORKING and it settled a two-day-old question.** Live passes now
read `PASSIVE, busy 0` with the log oscillating at 1-4 MB. Because the WAL is
provably flat while `candidate_ms` still swings eightfold, **the WAL is not
the cause of the slowness** — the discrimination the 2026-08-29 read could not
run, because back then nothing ever checkpointed and both regressors were
constant.

**2. `/api/parlays` took over 30 seconds.** `parlay-candidates-timing` (new,
in `inspect_live_db.py`, times the statement the route runs via a
byte-identical copy pinned by a test) said why: **541,222 `fair_prices` rows
read, joined, sorted through a temp B-tree, to keep 350.** The scan floor was a
flat 24 hours while `build_ladder` discards anything older than 15 minutes. Now
a MULTIPLE of `max_odds_age_ms` (8x = 2 hours), so there is still one staleness
quantity and "the scan can never be tighter than the freshness rule" holds by
construction. **Measured after: 796.8 ms, 85,518 rows — 32x.** Route is
~0.6-1.8s warm, ~23s on the first call after a restart (cold page cache on a
2 GB db, not the query).

Eight, not four: at 4x `test_a_stale_consensus_is_refused_and_counted` went
red, because a row that just went stale must still ENTER the scan or
`excluded['stale_consensus']` reads 0 and an empty ladder says "0 fresh games"
with nothing explaining where they went.

**3. The parlay tap asked the wrong question.** `price_card_on_kalshi` rebuilt
the ladder and refused unless the desk would still *compose* the same card —
but the ladder re-ranks off the freshest consensus on every request, so one
quote pass between render and tap was enough, and the refusal told him to
refresh, which restarted the race. On the degraded box the window was shorter
than the time it takes to read a card. `resolve_requested_legs` now asks the
per-leg question instead — is each leg he tapped still one the desk would
serve — bounded because a lookup mints a real market: every leg in the current
candidate pool, one leg per fixture, count inside the card's recipe.

### The buy path (ADR 0084) — built, armed, and it works

Joe: *"I want to be able to select a combo straight from the cockpit… and have
the transaction be done directly through the cockpit."* The existing buy
control could not: it renders only when a price came back and sends an IOC at
the live ask, and a combination has no live ask.

Probed first (`scripts/probe_resting_combo_order.py`, under a cent): **a
combination DOES accept a resting GTC bid** — 201, `remaining_count 1.00`,
status `resting`, cancelled with `reduced_by 1.00`, nothing filled.

Three mechanics discovered, each now pinned by a test:

- **Kalshi shards its matching engines and collateral does not follow an order
  across them.** *"Programmatic traders must preallocate collateral on a given
  exchange shard before order placement."* A 2c bid was refused
  `insufficient_balance` against a $21.41 account whose combinations shard held
  $0.0100. Shard map: 0 = everything else incl. WNBA, 1 = Exotics/Combos,
  2 = Crypto, 3 = Sports (tennis + baseball only, moved 2026-08-24).
- **The cancel carries its shard as a QUERY parameter.** Without it, 404
  `not_found` for an order the list showed as `resting` that same second.
- **The query string stays OUT of the signature** (401 otherwise). The
  production client already did this; a test now pins it.

Then the first real bid 500'd in front of him: the path re-read
`GET /markets/{ticker}`, which **404s for a combination minted seconds
earlier** — the catalogue lags the mint while the orderbook endpoint answers
immediately, which is why the lookup path never noticed and the probe (using a
90-minute-old market) never hit it. The mint response already carries
`price_ranges`, `price_level_structure` and `exchange_index`; it is used now,
and `FakeApi.get` raises 404 on every catalogue read so a reintroduction fails
the whole file.

**Armed on his word** ("the exchange is done. arm the switch"), after verifying
shard 1 read $21.4100. `COMBO_ORDERS_ARE_DRY_RUNS = False` in a commit of its
own; three tests assert the armed state, that `ORDERS_ARE_DRY_RUNS` is still
True, and that `gate.py` cannot read `combo_orders`.

**His order rests right now:** 9 contracts at 20.1c, $1.81, shard 1,
`auto_cancel set 2026-08-30T23:00:00Z`, kalshi order
`01a05491-b3b0-727b-887c-e2313855b65a`. `combo-bids-tail` reports it.

### The finding that reframes the product — ADR 0085

Joe went looking for the order under **Positions** and found nothing, correctly:
a resting order is not a position. Then: *"is it possible to explore instead
existing parlays in Kalshi that are good potential… and buy them directly?"*

Measured before building it (`docs/measurements/2026-08-30-combination-
liquidity-census.md`): **61 open combination markets, 0 with a quoted ask, 0
with any liquidity, 1 that has ever traded (45 contracts), 0 of 6 books
non-empty.** The list rows show `no_bid_dollars = 1.0000` — the boundary, not
an offer; it derives to a YES ask of $0.00. Every field is correctly named, and
`measure_combo_book_presence.py` independently selected 0 eligible rows from
the same 61.

So ADR 0012 §5's "enter-only" understates it: combinations are **unquoted** —
usually no entry either. **A browse-and-buy board would be an empty screen.**

**ADR 0085: the parlay desk prices a bet it cannot place.** The card now leads
with the break-even price in American odds — *"What a sportsbook must pay to
match this: +398"* — with the words saying it is break-even and he needs better
than it. The Kalshi buy path is demoted behind a reveal labelled *"usually
nobody is selling"*, not removed: it works, and one combination has traded.

### A copy defect worth remembering

He read *"an offer standing, not a bet placed"* as having SOLD something —
in market language an offer is the sell side. He was buying. The words now lead
with BUY, state what winning pays ($1.00 a contract, so the payout is the
contract count in dollars), and say **Orders, not Positions** — which is
exactly where he looked. Five tests pin the wording, with no carve-out for the
file they guard.

### OPEN — pick up here

1. **The covering index on `odds_snapshots`, MEASURED AND READY.**
   `_match_candidates` (`runner.py:1036`) is
   `SELECT DISTINCT … WHERE sport_key = ? AND commence_ms >= ?` and
   **`sport_key` is in no index**, so it range-scans `idx_odds_commence` across
   every sport into a temp B-tree, over a table with ~1.5M rows, ~900 added per
   sweep, and **no retention rule at all**. It hit 27.7s at 22:07Z, the pass
   took 104s, the API's read connections starved, the **Fly health check on
   port 3000 failed at 22:06:03**, and `/api/market`, `/api/window` and
   `/api/scout` all returned socket-hang-up in the same minute — which Joe saw
   as "the scout desk returned 500". Not a Scout bug.
   Measured on 1.5M synthetic rows of the real shape:
   `none 442ms → narrow (sport_key, commence_ms) 303ms → covering
   (sport_key, commence_ms, odds_event_id, home_team, away_team) 62ms` — **7x,
   and only the covering form is worth having.** Needs a migration step (an
   index does not reach an existing db through `schema.sql`) and a note on
   write amplification, which this repo has refused an index over before.
2. **Scout on the parlay legs**, with human prose and instrument-panel visuals.
   Joe's design ruling, in his words: the Scout **gates eligibility and flags**
   — a leg with a scratched starter or a red flag gets dropped or warned — and
   **never moves the price**. He accepted this over letting it adjust the fair
   value. The Scout desk already works and produces exactly the sports content
   he asked for (verified on `KXWNBAGAME-26AUG30GSPDX-GS`: FIBA World Cup
   absences, an unresolved neck contusion, and an honest "the Portland scout
   filed nothing"). He also asked for real graphs, not just the leg-decay line:
   *"remember this is a cockpit."*
3. **`user_not_found` on shard 3.** Creating an order on a baseball market
   fails with *"Exchange user not found"* even with explicit routing and even
   though `/portfolio/balance?exchange_index=3` reads fine. Undocumented —
   the research agent found no REST error catalogue at all. Hypothesis (not
   established): a user record materialises on a shard at the first transfer
   into it. Falsifying test is cheap: move a few cents to shard 3 and re-post.
   **Blocks every baseball hand bet regardless of funding.**
4. **Joe's shard allocation is all-in on combos** — shard 0 is down to $0.0020,
   so WNBA and every other shard-0 market has nothing behind it, and shard 3 is
   $0. Worth telling him before he tries a single-market hand bet.
5. **Combo maker fee: Kalshi's 2026-08-22 changelog says the multiplier is
   0.5, not the standard 0.25.** Unreconciled with `core/fees.py`. Relevant to
   ADR 0046, which already holds the combination fee model unverified.

---

## 2026-08-30 — the WAL read was taken, it could not run, and the memory level halved

**Docs only — no code or test file changed. Live is on `91a66f1`, `main` is
five commits ahead of it. `tasks/NEXT.md` was 188,912 bytes (72%) and
`tasks/lessons.md` 218,194 (83%) read BEFORE writing, per the rule.**

### Thread 1 is READ, and the answer is "the design could not run"

`docs/measurements/2026-08-30-the-wal-curve-is-flat-and-the-rss-level-halved.md`,
raw series committed beside it as `2026-08-30-loop-rss-samples.jsonl` (893
rows, six boots). Window: the 04:03:30Z boot, **2.64 h, 128 passes, no
death**. Nothing was checkpointed, VACUUMed, indexed or deleted.

**Both registered regressors were constant, so neither row of the
discrimination can be selected:**

    wal_kb          two values in 128 rows: 4, then 18544 x127
    db_kb           one value: 1865420
    candidate_rows  one value: 162  (127 rows)
    leg_store_quotes_ms  n=127  min 62  p50 79  p90 97  max 2700

Verified independently of the instrument by `ls -la` twice, 45 s apart: both
files **byte-identical in size while both mtimes advance**. That is the WAL
being rewritten in place at a stable high-water mark — autocheckpointing
working, not stalled. **Do not record this as "the WAL is exonerated."** It is
untested. Two ways to get a window where `wal_kb` actually varies are in the
measurement's last section; neither is a checkpoint.

What *did* separate the storage leg was the kind of pass: `produced_by=full`
p50 439 ms (n=9) against `quote` p50 79 ms (n=118). Nine is a thin cell and
the direction is unsurprising; a lead, not a result.

**The WAL does not grow with uptime here.** Three boots carry the field and
the longest-running one has the smallest WAL (2.64 h → 18.1 MB; 1.60 h →
31.3 MB; 0.29 h → 21.9 MB). The pre-deploy 220 MiB cannot be reached by
extrapolating this rate — it is an episode, not this curve.

**And the WAL was flat at 31.3 MB across the whole 48-minute wedge** that
killed the 01:52Z boot. For that occurrence the wedge neither grew the WAL nor
followed WAL growth.

### Two questions that were open are now closed

**Guest OOM: refuted, for both recorded deaths.** `/data/last_teardown.log`
holds two records, both `CHAIN RUNNER exited` — 01:13:16Z with MemAvailable
1,610,212 kB and 03:28:31Z with 1,096,868 kB. `record_teardown` runs
`dmesg | tail -n 40` and in both records those 40 lines are still the *end of
the kernel boot sequence*, so the ring buffer had acquired nothing since boot
and no OOM kill was printed. The child is named, twice, and it is the chain
runner — the poisoned-connection diagnosis, not a kernel kill. **The 2026-08-29
"unresolved, not refuted" note on guest OOM can be closed.**

**The RSS level halved, and the control is eight minutes wide.** The 01:44:29Z
boot was a secrets restart of `c9ca0cd`; the 01:52:32Z boot was the `fe239d6`
deploy. Same hour, same slate, eight minutes apart: **652 MB against 341 MB.**
`0cfa849` ("the peak was the list, not the junk") is new in `fe239d6` and
absent from `c9ca0cd`, verified by `merge-base --is-ancestor`. Three numbers
agree: 2026-08-20 **named** the `raw_events` list as the suspect, `0cfa849`'s
replay **predicted** 1,036 MB held vs 24 MB dropped, and this window
**measured** ~650–745 MB → ~340 MB on the live box. It also reproduces
"a level, not a leak" on a second instrument: 128 MB until the first full
pass, then a step, then flat.

### A wedge detector that costs nothing, found in the data

The three rows before the 03:28:31Z death carry **byte-identical**
`candidate_rows`, `candidate_ms`, `leg_price_link_ms` and
`leg_store_quotes_ms`. The instrument samples at pass start, so a pass that
fails without refreshing `counts` makes the next line re-emit the previous
one. **A repeated line dates the wedge onset to the pass** — ~02:40:52Z, 48
minutes before the death — where `pass-gaps` cannot fire until a gap has
elapsed and `loop_failures` was empty because the failure path shared the
poisoned connection. Not built; recorded as a lesson and available to whoever
touches the watchdog.

### Also observed, not acted on

- Two attention-tagged sweeps fired overnight (05:14Z, 06:42Z). `/api/health`
  does not stamp attention — only the authed `POST /api/desk/attention` does —
  so this is a real client, not monitoring. Day total 456 of 700 credits, well
  inside the cap. Noted so nobody re-derives it as a leak.
- Two scan spikes with both regressors flat: 02:02:27Z `candidate_ms` 11202 /
  `leg_price_link_ms` 14881, and 02:09:13Z 5451 / 7201, `wal_kb` 25.6 MB and
  `candidate_rows` 163 on both. Write contention is the obvious third
  candidate and this window does not test it.

### Two lessons at the top of `tasks/lessons.md`

(1) Check the regressor moved before reading the outcome — a constant explains
nothing, and the convenient overnight window is the one where every driver is
at rest. (2) An instrument sampled at pass start repeats itself when the
producer fails, so "flat" and "broken" are the same line unless the docstring
says which.

### Open, carried forward

1. **Thread 1 is no longer waiting on uptime — it is waiting on a window where
   `wal_kb` varies.** Do not re-run it overnight; that is what made this one
   void. Still: no checkpoint, no VACUUM.
2. **Joe's question on the buy ticket is put and unanswered** — `manual_orders`
   still zero rows. Nothing gets built for it until he answers.
3. **Deploy decision is Joe's** — `main` is five commits ahead of live and
   carries the check-10 positions fix and the refusal recorder (v29). A deploy
   resets the WAL series, which item 1 no longer needs.
4. Items 3, 4 and 7 of the previous entry stand: watch `loop_failures.jsonl`
   after the next wedge; `fair_prices` 546 MB unbounded; `_absence_provable`
   two-clock shape.

---

## 2026-08-30 — the positions payload was observed, a refusal became a record, and two lanes closed two backlog items

**Committed on `main` through ADR 0083 (`a45d088`, `ffc50c1`, `977cc4d`,
`21da67e` + the ADR/session-files commit). Suite: 5243 passed / 10 xfailed in 10:49,
collected on this tree with ONE qualification stated rather than hidden:
`tasks/NEXT.md` (this file) was edited while the run was in flight. No code
or test file moved; the only tests that read this file
(`test_session_files_are_readable`, `test_parallel_lanes_do_not_collide`)
were re-run on the final tree and pass. The +35 over 5208 is the two lanes'
guards plus tonight's refusal/positions tests.
NOT DEPLOYED — live is on `91a66f1`; check `/api/health` `git_sha`.**

### Read this first

**Joe has NOT yet used the dollar buy ticket.** `manual_orders` is still
zero rows (verified via `manual-orders-audit` this session). He holds a
live position updated 02:01Z tonight — placed in the Kalshi app. His
feedback on the ticket, when it comes, outranks everything below.

### The positions payload was finally observed (A0) — and it convicted check 10

`scripts/capture_positions_fixture.py` (new, committed) captured
`/portfolio/positions` twice against production. The quantity field is
**`position_fp`, a fixed-point STRING, fractional** (`'22.88'` live); the
docs' `position` int does not exist on the wire. **The bare endpoint
returns zero-quantity rows for exited markets** — 2 bare vs 1 with
`count_filter=position`, the zero row a market exited three days earlier.
So until tonight, check 10 refused re-entry to any market Joe had ever
left, and "Open now: N" counted "ever traded". Fixed in `a45d088`:
`rest.positions()` now sends `count_filter=position`, paginates, and
raises on a renamed envelope instead of the `or []`; check 10 compares the
parsed quantity (zero passes — proven by mutation; unparseable refuses).
Captures live in gitignored `data/captures/`; the committed test row is
synthetic with observed field names/types (ADR 0035 precedent).

### A refused hand bet is a record now (schema v29, `21da67e`)

All ~23 pre-reservation refusal branches on `/api/manual-orders` wrote
nothing until tonight. New append-only `manual_order_refusals` table:
check number/name, the exact detail Joe saw, request values, live ask when
known. One try/except with a check pointer, not 23 edits. A recording
failure can never turn a 422 into a 500 (throwaway connection → journal
fallback `manual_order_refusals.jsonl` → route swallows recorder crashes).
`gate.py` never reads it (pinned). Read it on live with:

    flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/inspect_live_db.py manual-order-refusals"

**ADR 0083** records both decisions and the generalised rule: an armed
path records its own refusals durably; three instances of the
log-line-only pattern in three days (refused bet, failed match pass,
poisoned connection).

### Two lanes merged (worktree agents, disjoint files)

- **Item 4 closed** (`977cc4d`): `run_match_pass` is in `MUST_HAVE_CALLERS`;
  a mirror pass must carry the matcher's own summary (an async no-op stub
  went red where all 333 area tests had stayed green — the wiring was
  decoration before); matcher failures land in `poll_log`
  (`endpoint='match'`, own commit, proven red both ways).
  `MIRROR_INTERVAL_S` untouched per the standing ruling. Context read this
  session: `bet_estimates` has exactly 1 matched row ever, and
  `venue_settlements` has 27 rows (26 out_of_scope) — `outcome_win`'s
  population is n=1 and nothing reads the column; the fix protects the
  record, not a number anyone consumes.
- **Item 7 closed** (`ffc50c1`): `mart_suppression_audit` verdict floor is
  now the shared `min_scored_recommendations` var (300, like both
  siblings); sub-floor rows say "insufficient sample — displayed, not
  judged". Guard doubled (dbt + pytest source check, both proven red)
  because the demo lake has zero scored rows and a dbt-only guard is
  vacuously green in CI. ADR 0065 §3 amended in place: display gate never
  verdict gate; 63.2 points resolvable bias at G=30; `n` counts
  games/clusters.

### Also in the record

- Two lessons at the top of `tasks/lessons.md`: (1) a cadence change must
  re-derive every predicate comparing against a timestamp it produces —
  `_absence_provable` vs ADR 0064's 300s settlements clock is the live
  example; (2) a test that NAMES a symbol is not a guard on it — disable
  and watch it fail before claiming coverage.
- Live health verified at session start: recorder writing (8s age),
  `91a66f1` deployed 04:04Z, WAL curve recording from zero.

### Open, carried forward

1. **Deploy decision is Joe's** — everything above is committed, not
   deployed. Deploying restarts the container and RESETS the WAL series
   (thread 1); the read wants ~a day of uptime that started 04:04Z. If Joe
   is about to bet through the desk, the check-10 fix matters more than
   the WAL series (his one live position would have FALSE-REFUSED any
   re-entry ticket on that market; and note the netting guard now
   correctly refuses new buys on the market he entered at 02:01Z while he
   holds it).
2. **WAL read** (2026-08-29 item 2) — unchanged, needs uptime; do NOT
   checkpoint or VACUUM.
3. **Watch `loop_failures.jsonl` after the next wedge** — the traceback in
   it is the missing half of the poisoned-connection diagnosis.
4. `fair_prices` unbounded, 546MB — retention freeze LIFTED but fix the
   write rate first (`run_pricing_pass` re-inserts every 15s against odds
   refreshing 10–60 min); deferred deliberately, ~70MB/day against ~3GB
   free.
5. ADR 0065 §3 floor — CLOSED by item 7 above.
6. Refused-bet recording — CLOSED by v29 above.
7. `_absence_provable` two-clock shape — recorded as a lesson, no code
   change owed until someone touches the 12h ladder.

---

## 2026-08-30 — the hour-long silences are a poisoned connection, and the ticket takes dollars

**Committed on `main`. Suite: 5208 passed / 10 xfailed in 11:07, collected on
this exact tree with nothing edited after the run started. Deployed: check
`/api/health` `git_sha` rather than this sentence.**

### The Discord alerts are explained, and the explanation inverts a documented reading

Two heartbeat alerts fired (20:10/20:28 Pacific, 2026-08-29): no quote for
43/61 minutes. Diagnosis, taken while the evidence lived:
`docs/measurements/2026-08-30-the-wedge-is-a-poisoned-connection.md`. The
short form:

- A pass died between statements (the 600s deadline cancels mid-await;
  nothing on the failure path rolled back) and left a half-read cursor. With
  something long-lived still referencing it, the runner's shared connection
  kept a stale WAL read snapshot.
- The portfolio poller's own connection committed every 5 minutes through
  the whole wedge (13/13 in `poll_log`) — which is the discriminating fact:
  no held write lock can produce that split. This is SQLITE_BUSY_SNAPSHOT
  wearing the generic "database is locked" message; the busy timeout never
  runs.
- Every write on the poisoned connection then failed instantly: the next
  pass, `record_loop_failure` (five times — **`loop_failures` is empty
  across the exact window it exists to explain**), and the dying
  FAILURE_LOOP_DIED alert (`alerts.py _claim`, same error). Five strikes,
  `LoopFailed`, exit 1 at 03:28:32Z, entrypoint teardown, restart at
  03:28:53Z cured it. Not OOM. The same signature ran 00:28→01:13 on
  `c9ca0cd`, so it predates the deploy.

**What shipped:** `db.record_loop_failure_durably` — journal to
`/data/loop_failures.jsonl` FIRST (a file no lock can refuse, with the
traceback that otherwise lives in a ~10-minute log buffer), rollback second
(cures the open-transaction half; measured NOT to cure the referenced-cursor
half on 3.11), throwaway-connection fallback third — and the fallback is the
diagnosis: the journal states in words whether the connection or the
database refused. The dying alert got the same fallback.
`tests/test_poisoned_connection_is_cured.py` pins the mechanism against a
real WAL file, including the two negative results (refcount-freed cursors
do not poison; rollback alone does not cure).

**Not established:** what held the cursor reference. The journal's
tracebacks will name the failing await at the next occurrence. Next
occurrence still costs ~62 min of outage (5 strikes × 900s) before the
restart cures it — judged acceptable tonight over hacking a fast-death
path in; revisit if it recurs weekly.

### The WAL read (thread 1): no day accumulated, and the deaths are why

The curve reset at the 01:53Z deploy and again at the 03:28Z wedge-death
(`wal_kb: 4` on the fresh boot). Partial series from the 96 minutes that
ran: WAL 4KB → 26MB in ~15 min → 32MB by 02:40, flat through the wedge;
`leg_store_quotes_ms` stayed 128–825ms throughout — **no latency signal at
these sizes**. Recorder untouched — no checkpoint, no VACUUM. The read
needs a day the container has not yet survived; the poisoned-connection
death is currently the thing cutting the series short.

### The buy ticket takes dollars (thread 2 — Joe's ruling)

"Confusing. Let me just buy it and help me with putting in the amount in
dollars." Done in `ManualTicket.tsx`, client-side only (the route already
took `contracts` 1–1000, server-side caps unchanged):

- The contracts stepper is gone. The primary control is **"Amount, in
  dollars"**; the conversion is shown, not hidden: "Buys 11 contracts at
  43¢ each = $4.73, plus the fee. Whole contracts only, rounded down."
- Rounds DOWN, always — the tool never spends more than the typed number.
  Too small an amount names the smallest bet instead of buying 1.
- An untouched ticket starts at 0 contracts, so confirm is dead until an
  amount is typed (the old default silently made "1" optional).
- The per-bet cap names itself when it binds ("your per-bet cap, not your
  typed amount, set the size").
- Max price demoted to a `<details>` disclosure, default = live ask.
- Confirm button carries the cost: "Confirm — buy 11 YES for $4.73".
- Pinned in `tests/test_buy_controls.py::TestTheAmountIsTypedInDollars`.

The estimate-first step and order token are unchanged — server-enforced,
ADR 0065.

### Open, carried forward

The 2026-08-29 list below stands (WAL read is item 2 there, still waiting
on uptime). New: watch `loop_failures.jsonl` after the next wedge; the
traceback in it is the missing half of tonight's diagnosis.

---

## 2026-08-29 — the signal test could never have answered its own question, and twelve lanes landed

**Pushed `2d63da5..975385e`, 27 commits, suite 5186 passed / 0 failed, tree
clean, origin clean. NOT DEPLOYED — live is still on `c9ca0cd`.**

### Read this first if you read nothing else

**The CLV signal test was structurally incapable of resolving, and the
registration printed the proof itself on 2026-08-09.** At G = 300 the design's
MDE against the 0.40 threshold it tests is **0.6283**. That cell sat in the
published power table for months and nobody read across the row.

Amendment 2 (commit `81f67b2`) raises the floor to **G = 713** by the
registration's own formula — its trigger, *"if it comes in above 30 tenths this
document must be amended to raise the floor"*, had fired at
`sd(clv_tenths) = 30.15` and the amendment was never written. Reproduction is
exact against the published level table at sigma = 20, so it is the same
arithmetic, not a new one.

**Worse than a bigger number: nominal G may be the wrong unit.** At the measured
`G_eff = 4.26` the slope MDE is ~32, about eighty times the threshold. Holding
the observed concentration fixed, `G_eff = 713` wants ~**52,052 nominal games**,
about eleven years against a stopping rule ending 2027-02-15.

**So the declaring look is not coming.** CLAUDE.md used to say *"the recorder
keeps running and the look happens on its own"*. That sentence is gone. No
roadmap may depend on the look and none may wait for it. The way out, if the
question is ever worth reopening, is a successor registration with an
`edge_tenths` exclusion fixed in advance — this one never contemplated a
regressor running to minus 717.97 tenths.

None of this softens the verdict on the premise. Every interval at both looks
already sat entirely below 0.40 and both arms were negative.

### The near-miss worth carrying

`fit()` took `tuning: int = MIN_CLUSTERS_TO_DECLARE` — **one constant serving
two purposes.** Raising the floor to 713 would have silently re-tuned the
always-valid boundary and **restated the widths of the published 2026-08-16 and
2026-08-25 intervals**. A change ordered to make declaring *harder* would have
quietly rewritten two results already in the record. Split into
`BOUNDARY_TUNING = 300`, pinned apart by a test; the old reproductions still
return -0.1412 / G=199 and -0.0528 / G=86, which is the evidence it worked.

The same shape appeared again in the same file. Section A4's *testability*
threshold is also 300 and **deliberately stays there** — raising it leaves fewer
groups testable and downgrades rarer, the flattering direction. A blanket
300-to-713 substitution would have weakened the guard Amendment 2 had just
switched on.

### Joe asked for a performance-assessment system. Ruling: no dashboard.

- **"Am I winning?" is unanswerable at any n, permanently.** He bets at varying
  prices, so break-even runs 30.9% at 30c to 70.9% at 70c and a pooled win rate
  **has no null hypothesis**. Net P&L does have one and needs ~3,854 bets,
  ~10,000 given he looks daily — 3.5 to 27 years at his real rate.
- **Calibration is the one verdict-bearing statistic**, floor G = 300 clusters,
  one to three years out.
- **The useful panels have no statistics in them** and work from bet one: fee
  per dollar staked, cadence, session length, stake sequence, fill rate.
- The record is **one 4096-byte page — single-digit rows, zero not excluded.**

Registration committed as `18bb1fd`, written against genuinely virgin data:
`p_yes_bp` is NOT NULL on every armed bet since 2026-08-26 and **had never been
read by anything**.

**What shipped instead of a screen:** schema v28 freezes the consensus fair
value, book count, anchoring and clock into `manual_orders` at intent-write
time. Snapshot, deliberately **not** a foreign key — `fair_prices` is 546MB,
30% of the database, and **unnamed in `retention.py`**. Every bet placed before
this landed is unanalysable forever. Plus `manual-orders-audit`, the first
whitelisted query to touch that table, its firewall asserted over the SQL
strings rather than left in prose.

### The container deaths: theory killed, real lead found

**The "wrong walk" death spiral does not exist.** For the 30-minute window to
empty, the loop must be silent for more than 1800s, but `slow_interval_s` is
900s, so the next pass after any such gap is *necessarily* a full pass, which
refills `last_seen_ms` before returning. Entry condition unreachable.

**The 570MB figure was already in the repo**, as
`docs/measurements/2026-08-20-the-585mb-is-a-level-not-a-leak.md`, nine days
before this session re-derived it. It is a one-time boot level plus a 25-106MB
per-full-pass excursion, not 570MB every 15s. Compounding errors: cadence is
~22.6s not 15s; full passes take 137.7s not 43-77s. The headline load figure
was off by ~15x.

**The real lead: a 220 MiB write-ahead log that has never reset**, ~55x
SQLite's default. It is the only candidate explaining both storage legs blowing
out while `leg_walk_ms` stays narrow. Caught live: at 19:44:20Z a sweep wrote
2,210 rows to `odds_snapshots`; the next two quote passes took **200s and 176s**
against a normal ~8s. The deadline has never fired — 0 rows in the 15
`loop_failures` ever recorded — and `sqlite3.Connection.execute` never yields,
so cancellation is ruled out. No ~60-minute constant exists in code.

**Instrument shipped, intervention deliberately NOT.** `loop_rss.jsonl` now
carries `wal_kb`, `db_kb`, `candidate_rows`, `candidate_ms`,
`leg_price_link_ms`, `leg_store_quotes_ms`. **Do not checkpoint, VACUUM, index
or delete until the series is read.** The discrimination: if
`leg_store_quotes_ms` tracks `wal_kb` while `leg_price_link_ms` tracks
`candidate_rows`, both mechanisms are real and additive; if both track `wal_kb`
and `candidate_rows` is flat, the WAL is the whole story.

### Also landed

- **The desk stopped punishing attention.** Once the slice was spent, an open
  page *suppressed* the hourly floor buy, and closing the tab was what let it
  resume. Attention replaced the floor rather than adding to it.
- **Kickoff clock**: slate rows were 180 minutes late against the detail
  screen. Fixed by the join, not by `OBSERVED_KALSHI_COMMENCE_OFFSET_MS` — that
  constant matched only 14 of 18 MLB pairs and stays applied to nothing.
- **Four money-path falsehoods**, including `/gate` claiming hand bets "fire no
  check" when twelve server-side checks have run since 2026-08-26, and
  `tests/test_scope_sentences.py` **asserting the false sentence must stay**.
- **Positions count off the 12-hour mirror** onto the shared 5-minute clock.
  Not an amendment: A1 sets a completeness floor, A7 splits the operational
  clock from the analysis clock. +288 Kalshi calls/day, rate-limited not billed.
- **Full-walk alarm**: a quote pass taking the full walk is now loud. `None`
  and `[]` take the same branch and are not the same input.
- **RAM bump KILLED** — refuted, not deferred.
- **Ticket #35 was already shipped** five days earlier.

### Open, in priority order

1. ~~Deploy.~~ **DONE 2026-08-30T01:53Z at Joe's call.** `fe239d6` is live and
   `/api/health` reports that sha. Schema v28 applied -- proven functionally by
   `manual-orders-audit` running, since it selects the new columns. The
   per-pass instrument is writing `wal_kb`, `db_kb`, `candidate_rows`,
   `candidate_ms`, `leg_price_link_ms`, `leg_store_quotes_ms`, and the reader
   parses the old rows beside the new ones as designed.

   **Two findings the deploy produced, both bigger than the deploy.**

   **(a) `manual_orders` has ZERO rows. Not thin -- empty.** No hand bet has
   ever been placed through the desk, in the four days since
   `MANUAL_ORDERS_ARE_DRY_RUNS = False` on 2026-08-26. `first_submitted_ms` is
   NULL. Meanwhile `venue_settlements` and `fills` carry real rows tagged
   `venue_hand` -- so Joe bets, in the Kalshi app, not through this. The armed
   buy path is built-but-never-called at the USER level rather than the code
   level, which is the same defect this repo has been caught by four times
   wearing different clothes. It also settles the dashboard question: there was
   never anything to put on a screen.

   **(b) The restart reset the WAL, and that is the measurement's baseline.**
   It was 220MiB before the deploy and is 14.4MiB minutes after it, with
   `wal_kb: 4` on the first pass. So the 220MiB is growth over uptime, and
   every container death has been silently resetting it. That is consistent
   with the WAL being a CAUSE of the slowdown that precedes a death rather
   than a symptom of it -- and it means the clean curve from ~0 is now being
   recorded for the first time. **Do not checkpoint or VACUUM.** Let it grow
   and read `wal_kb` against `leg_store_quotes_ms`.
2. **Read the WAL series** once deployed, then intervene.
3. ~~`ODDS_API_KEY` rotation~~ — **DONE 2026-08-30T01:44Z, verified.** Joe
   rotated at the vendor (which kills the old key on regeneration) and ran
   `scripts/setup_odds_key.sh`. Proof chain, because "it completed" is not a
   result: the wizard probes before it writes and aborts on any non-200, so a
   stored key that returned 200 cannot have been the revoked one; the machine
   restarted at 01:44:43Z; and a real odds call at **01:45:03Z** bought
   `baseball_mlb` for 4 credits with 15,528 remaining. `flyctl secrets list`
   reads **Deployed**, not Staged. Live stayed on `c9ca0cd` — a secret change
   restarts the current image and does not deploy.
   **Note `/api/health` proves nothing here**: the API process never reads this
   key (`load_without_credentials`), only the runner does.
4. `run_match_pass` has one production caller, inside the 12-hour mirror, and
   writes `outcome_win`, a registered variable. Latent regression, own decision.
5. `fair_prices` unbounded, 546MB, unnamed in `retention.py`.
6. A refused hand bet writes nothing — the desk cannot count how often its own
   brakes fired.
7. `ADR 0065` section 3's `n >= 30` floor resolves only a 63-point calibration
   bias. Safe as a display gate, catastrophic if mistaken for a verdict gate.

## 2026-08-29 — THE READ WAS TAKEN, and every gap turns out to be a container death

**Third window, first read.** Taken 2026-08-29 ~17:16-17:25Z, in the
pre-registered order, on a window that ran ~21 hours with no deploy
(`/api/health` `git_sha`, `image_ref`, `machine_version`, `machine_id` all
byte-identical to the 06b5f71 stamp). The result is decision-table row 2, and
the discriminator did not just narrow the cause list — it reframed what a
"pass gap" is.

### The read, verbatim

    /proc/uptime      8985.28 s   read ~17:17Z  ->  container boot ~14:47Z
    pass-gaps --tail 800:
      2,659,642 ms (44m20s)  began ~10:33:54Z  resumed 11:18:13.838Z
      2,618,007 ms (43m38s)  began ~14:03:34Z  resumed 14:47:11.972Z
    loop_failures     unchanged, 15 rows, ZERO PassDeadlineExceeded ever
    machine events    exit_code=1, oom_killed=false, requested_stop=false
                      at 14:46:52Z; restarts started 11:17:54Z and 14:46:53Z

Both gaps began after the 17:47:55Z boundary with the deadline build running
throughout. Both are >25 min, so zero rows is informative. Tail reach was not
re-verified against the boundary this time because the same 800-row tail was
verified yesterday at 12 hours' reach and the cadence has not changed.

### The finding: both gaps END at a container restart

Gap A resumed 19 seconds after the 11:17:54Z machine start; gap B resumed 19
seconds after the 14:46:53Z start. `exit_code=1` is the entrypoint's
`shutdown 1` — `wait -n` returned because a **child process died** — and
`requested_stop=false` rules out a deploy or a stop. The "resumed" pass is not
the loop recovering; it is a **fresh container's first pass**, cold-open buy
and all.

**And the cold-open signature generalises backwards.** All three of
yesterday's out-of-scope gaps (resumed 10:51:49, 07:22:13, 12:09:06 on 08-28)
have `api_credits` buys at the exact resume second — the same signature
today's two proven restarts carry. Fly retains only ~5 machine events so the
historical restarts cannot be confirmed from the platform, but the working
model is now: **a "pass gap" is a wedge that ends in a process death and a
platform restart, not a stall that clears.** The 2026-08-26 lesson that a
LoopFailed exit left the machine STOPPED for hours is the same class seen
before the exit-code fix made the restart automatic.

### The refined timeline, and the constants in it

The gap as measured UNDERSTATES the incident. Quote-pass cadence (15-20s)
actually stops at **10:17:21Z / 13:47:20Z** — the measured gap starts at a
single later row:

    cadence stops          10:17:21       13:47:20
    (~16.2 min silence, then ONE completed pass writes a 'skipped' row)
    lone row               10:33:54       14:03:33
    (~44 min silence, then a child dies)
    container exit         ~11:17:53      14:46:52
    cold-open resume       11:18:13       14:47:11

    stall -> lone row      ~975 s         ~973 s
    lone row -> death      ~2,640 s       ~2,599 s
    stall -> death         60m33s         59m32s

Three near-constants across two independent incidents. ~975s is close to the
Linux TCP retransmission death (`tcp_retries2=15`, ~925s nominal) —
**hypothesis, not finding**. The ~60-minute stall-to-death is the most
suspicious constant and matches nothing named yet. Both stall onsets sit
~14.7 min after an hourly floor buy (10:02:27, 13:32:42) — i.e. at the next
full-pass boundary after the floor-buy pass.

### What zero deadline rows now means

Per the instrument's own registered interpretation (`scheduler.py:91`): a
recurring gap with no `PassDeadlineExceeded` row is **evidence for a blocking
synchronous cause and against a hung await**. Two in-scope gaps of 16 and 44
minutes, deadline 600s, zero rows. The 44-min wedge is 4.4 deadlines deep.
**`BUSY_TIMEOUT_MS = 5000`** (`store/db.py`) means a SQLite lock wait raises
in 5s and cannot be the wedge. What blocks synchronously for 16-44 minutes on
this box is unnamed.

### The child is unnamed, and the RAM refutation has a hole

`flyctl logs` reaches back only ~10 minutes; the entrypoint's "BACKEND exited
/ CHAIN RUNNER exited / FRONTEND exited" line from 14:46:52Z is gone. The
partner ruled the RAM bump refuted by `oom_killed=false` — **that flag is
host-level and cannot see the guest kernel's OOM killer**, which kills a
single process inside the VM, which is exactly "a child died, exit 1".
Measured 2.5h after boot: 2GB total, no swap, **the chain runner at 714MB
RSS** (biggest process, biggest OOM target), MemFree 109MB, page cache 677MB
against a 1.91GB database, sustained IO pressure (full avg300 3.8%). `dmesg`
is wiped by the reboot that ends every incident, so guest-OOM is undecidable
retroactively. **Unresolved, not refuted.**

### The instrument for next time — a deploy is allowed now

The window is consumed by its own success; the freeze is over. What decides
the next incident in one read, both trivially small:

1. **The entrypoint persists its teardown line** — which child, exit status,
   timestamp — to `/data/last_teardown.txt` before `shutdown 1`, plus the tail
   of `dmesg` so a guest OOM kill is caught. Today it echoes to stdout that
   evaporates in minutes.
2. **The runner logs its own RSS per pass** (one `/proc/self/status` read) so
   the growth curve to 714MB-and-beyond is on disk.

Neither is a fix. Naming the child converts the next ~60-minute incident from
a hypothesis menu into a diagnosis.

**SHIPPED AND VERIFIED ON LIVE, same session.** `c9ca0cd`, deployed via
Actions, `/api/health` `git_sha` == local HEAD exact. `record_teardown` in
the entrypoint (all three death branches, before `shutdown 1`, appending to
`/data/last_teardown.log` with the dmesg tail that decides the guest-OOM
question) and `record_pass_rss` in `run_loop.py` (one line per pass at pass
START, `/data/loop_rss.jsonl`, 2MB cap). Four mutations observed red,
including the deleted-call-site one only a caller guard catches. First pass
after boot wrote its line on the live volume: `rss_kb 130964` — **131MB fresh
against 714MB at 2.5h yesterday, so the growth curve is already the lead
suspect's fingerprint.** `last_teardown.log` does not exist yet, correctly:
no death since the deploy. The next gap names its child on its own.

Full suite on this tree: **5036 passed / 10 xfailed**, collected on `c9ca0cd`
with nothing edited after the run started.

### Partner rulings this session (directed in parallel, per Joe)

- RAM bump: HOLDS (see the hole above — revisit only with guest-OOM evidence).
- Retention: eligible but **do not start** until the child is named.
- Watchdog rebuild: still dropped.
- `ODDS_API_KEY` rotation: **put in front of Joe** — it is one message, it has
  been open since a subagent read `.env`, and a secrets change restarts the
  machine, which no longer costs a window.
- The pattern for `lessons.md`: the pre-registration enumerated four causes
  **as alternatives**, and the observed incident is two of them **in
  sequence** (a wedge the deadline never got control of, then a process
  death). A cause list written as "which one" cannot file that shape.

### The live review — API yesterday, real screens today

Chrome connected; reviewed authed as Joe. **The 390px pass was NOT taken**:
`resize_window` moves the OS window but the renderer stays 1568px wide, so
narrow-viewport review needs devtools emulation or a phone. Still open.

- **/slate**: three-state refresh panel correct in the attending state —
  status line first ("window open · fresh for Nm"), credit paragraph demoted
  to a caption, tap buttons uniform. **Attention buying visibly followed my
  open tab** (the panel said so and `api_credits` agrees) — the tab was closed
  after review to stop the burn.
- **/parlays**: six cards render, all scoped to tonight, joint chances with
  method spans, multiply-down charts, honest enter-only copy. Yesterday's API
  read plus today's screens closes the "nobody has looked" item for these
  two pages.
- **/board**: healthy — bettable 0 stated as normal, the signal strip
  correctly says UNRESOLVED 276/300 ("not the same as no signal; 24 to go"),
  and the look line carries a "gap 8m" chip.
- **Quirk (small ticket)**: client-side navigation FROM the 404 page leaves
  the 404 rendered while the URL changes (found via /picks then nav "Picks");
  a hard load of /board is fine.
- **Flag**: the slate's "Open now: 1 position · $0.00 at risk · as of
  7:47 AM" stamp is the container boot time — 2.7h stale on a money line,
  apparently refreshed only at boot. Worth one look at where that timestamp
  comes from.

---

# The session index

Every session entry ever written to this file, newest date first. Full text in
the linked archive file, unchanged.

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
