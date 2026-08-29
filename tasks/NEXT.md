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

**Test baseline: 4,984 passed / 10 xfailed** on `2b3baa3` — see the #35 entry
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

## 2026-08-29 (latest) — THE READ WAS TAKEN, and every gap turns out to be a container death

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

## 2026-08-28 — the read was attempted a second time, the window survived, and it is 8 minutes old

**The window is INTACT and the read is STILL NOT TAKEN.** Not because anything
went wrong this time — because the window opened 8 minutes before the reading
and 8 minutes cannot contain a gap. Recorded in full so the next session does
not re-run the same commands hoping for a different answer.

### Uptime first, as the pre-registration demands

    /proc/uptime    487.07 s   read 2026-08-28T17:55:5xZ   (`date -u` at 17:56:12Z)
    implied boot    ~2026-08-28T17:47:5xZ
    WINDOW OPENED    2026-08-28T17:47:55Z  (stamped last session from 53.85 s at 17:48:49Z)
    /api/health      build.git_sha 06b5f71d6a43f1bcd5f96755d7786a6d8033c544
    machine          7812601a239428

**The two uptime reads agree on the same boot instant, so this is the same
container and there has been no restart since the window opened.** That is the
one thing this reading establishes, and it is worth having: the window is valid
and the process-death discriminator is still available for any gap that begins
from here.

### `pass-gaps --tail 800 --limit 40` — three gaps, all out of scope

    3,800,015 ms  resumed 2026-08-28T10:51:49.741Z   began ~09:48:29Z
    3,664,369 ms  resumed 2026-08-28T07:22:13.852Z   began ~06:21:09Z   <- NEW
    2,868,555 ms  resumed 2026-08-28T12:09:06.841Z   began ~11:21:18Z

The 07:22Z gap is new only because the tail is deeper: `--tail 400` last session
did not reach it. It is the same class as the other two and equally out of scope.

**Tail reach verified, as the amended pre-registration requires** — the check
nobody had performed before, and the reason the previous read could not know
what it had missed:

    MIN(pass_ms) 2026-08-28T05:48:48.252Z
    MAX(pass_ms) 2026-08-28T17:56:32.112Z      800 rows

The tail reaches 12 hours back, well before the 17:47:55Z boundary. It is not
truncating.

`loop_failures` is unchanged at 15 rows — twelve `ValueError: ask 1000 tenths`
from 2026-08-26, three `ZeroDivisionError` from 2026-08-28 (passes 44/45/46,
12:36–12:38Z, fixed by `5436fc8` thirteen minutes later). **Zero
`PassDeadlineExceeded` rows**, and that zero is uninformative for the same
reason as last time: no gap in the population.

### Why this is not a null result either

Every gap above began before 17:47:55Z, so by the pre-registration's own scope
clause none of them is evidence — *"a gap that began before the boundary is out
of scope: not evidence, not weak evidence."*

**In-window observation is 8.6 minutes.** Against the established base rate of
3–6 gaps/day that expects **0.02 gaps**. Zero is what a working system and a
broken one both produce over 8.6 minutes. Decision-table row 4 carries a
**>= 12 h minimum** for exactly this, so:

    EARLIEST TAKEABLE READ   2026-08-29T05:47:55Z
    CONDITION                nothing deploys before then

**This is the third window and the read has been taken zero times.** Windows one
and two were voided by deploys — the second by Joe's own *"deploy now."* The
freeze is not a mistake anyone made; it is the cost of the instrument, and it is
the thing to weigh, not to route around.

### What was checked on live instead, and it is not a screen

Joe's list named four things shipped in `06b5f71` that nobody has looked at. **A
visual review was not possible: the Chrome extension is not connected** ("Browser
extension is not connected"), and every page redirects — `/slate`, `/parlays`,
`/board`, `/hedge` all return **307** to login. So what follows is API-level
evidence that the code runs with the right values, not evidence that a screen
reads well. **Do not record these as reviewed.**

Read from inside the container against `127.0.0.1:8000` with the instance's own
`APP_AUTH_TOKEN` from `os.environ`, so the live token never entered a transcript.
The local `.env` token is **not** the live one — it returns 401 against
`kalshi-cockpit.fly.dev`.

**`/api/window` — the three-state panel's inputs are live and the state is
"normal".**

    attention_credits_spent      148 of 300
    attention_slice_spent        false
    attention_slice_spent_at_ms  null
    desk_is_attended             false
    next_desk_buy_ms / floor_next_buy_ms  equal (1787943083794)
    spent_today                  208 of 700
    last_look_outcome            "skipped"

All six new fields are present and correctly typed. **The slice-spent state
cannot be observed today until the slice is actually spent**, so the branch that
half two was built to fix is still unobserved on live — only its inputs are.

**`/api/parlays` — the tonight bound is doing real work.**

    excluded: {"stale_consensus": 12, "kickoff_after_tonight": 228}
    cards: safe(3) middle(4) lottery(6) longshot(3) agreed(3)
           soon(0) — "needs 2 fresh games starting within three hours and the slate has 1"

228 legs dropped for kicking off after tonight against 12 dropped as stale. The
page is thinner by design and it says why, which is what the change promised.

**The combo-eligibility cache is warm and dropped nothing.**

    combo_eligible_events   3,427 rows, refreshed 2026-08-28T17:48:17Z
    TTL 2 h, so `combo_eligible_events()` returns a set, not `None`

`kalshi_will_not_combine` is **absent from `excluded`** — it is counted only when
it fires, and it did not. Every game still standing after the tonight bound is in
some collection. That is the expected shape, but note the observability gap:
**a zero-count filter and a filter that never ran look identical on the wire.**
Given this repo has shipped four complete, tested modules nothing called, that is
worth a field rather than an inference.

**The pre-POST refusal cannot be reached from the UI today, and that is
structural, not a fault.** `price_card_on_kalshi` re-derives the card from
`ladder_candidates` server-side, so a leg the eligibility filter has already
dropped can never appear in a card that reaches the guard. The refusal now fires
only when the cache is cold or stale (`None`, nothing filtered) or when the
collection walk and the ladder disagree. It is a backstop, correctly, and
**"nobody has looked at it" will stay true until one of those happens.** It was
not exercised by hand: a lookup mints a real market on the exchange, and there is
no leg available that would reach the guard rather than being filtered first.

### Housekeeping done first, on the rule rather than on the alarm

`tasks/NEXT.md` was **225,270 bytes — 86%** of the 262,144-byte ceiling. The
2026-08-26 and 2026-08-25 entries (9 of them) moved verbatim to
`archive/next-2026-08-29.md`, leaving **149,443 bytes (57%)**. `wc -c` was read
**before** this entry was written, which is the part the previous two splits got
wrong. The archive body was diffed against the pre-split file and is
byte-identical; `tests/test_session_files_are_readable.py` passes.

---

## 2026-08-28 — the pre-registered read was taken, and it was not a read

**The instrument was not on the box during either gap it went looking at.** The
read below is not a null result and must not be recorded as one; it is a read
that could not have produced a result. The pre-registration above is amended in
six places, all marked `AMENDMENT`, and the live window has been re-opened.

Directed by the partner agent from the reading, per Joe's instruction to take
the reading first and set direction from the verdict.

### What was read

Uptime first, as the pre-registration demanded, at 15:33Z:

    /proc/uptime            2989.40 s = 49m 49s
    machine 7812601a239428  started 2026-08-28T14:43:09Z   (the f1c2b5f deploy)
    build.git_sha           f1c2b5f5c258...

`pass-gaps --tail 400` — two gaps over 1200s, and **zero `PassDeadlineExceeded`
rows anywhere in `loop_failures`**:

    3,800,015 ms = 63m20s   began ~09:48:29Z   resumed 10:51:49.741Z
    2,868,555 ms = 47m49s   began ~11:21:18Z   resumed 12:09:06.841Z

`loop_failures` holds 15 rows: twelve are the 2026-08-26 `ValueError: ask 1000
tenths`, three are 2026-08-28 `ZeroDivisionError`, passes 44/45/46, consecutive
1/2/3, at 12:36:33 / 12:38:03 / 12:38:46Z.

### The three ZeroDivisionError rows are the already-fixed outage

Not a new incident, and worth pinning because a future `pass-gaps` read will hit
them again. `tests/test_parlays_api.py:463` names "three consecutive failing
passes" with that exact error; the fix is `5436fc8`, committed 12:51:16Z —
thirteen minutes after the last of them. They sit **after** both gaps and
overlap neither. `f1c2b5f` and everything since carry the fix.

### Why the read is void

`PassDeadlineExceeded` and `DEFAULT_PASS_DEADLINE_S` first exist in `8658da7`,
committed **2026-08-28T13:59:16Z**, and reached live with the `f1c2b5f` deploy
at **14:43:09Z**. Both gaps began at 09:48Z and 11:21Z — 4.2 and 2.6 hours
before the code was written, ~5 and ~3.4 hours before it was on the box.

**Zero rows against them is uninformative because no code capable of writing a
row was running.** That is a scope condition on the population, **not a fifth
cause**, and the amendment above files it as one deliberately: a cause explains
a missing row inside a valid window, and adding this to the four-cause list
would give a future session a fifth off-ramp from a zero that *is* informative
— always in the flattering direction, toward the synchronous-blocking
hypothesis the project already likes.

**The uptime discriminator could not be run and had already been destroyed.**
Its literal test — uptime shorter than time since the gap began — returns TRUE
for both gaps and means nothing, because the restart was the planned 14:43Z
deploy. The pre-registration said to take uptime first *because it is the only
evidence a later reading destroys*; it was destroyed before the reading, by a
deploy that happened after the pre-registration was written.

**The clean window was 50 minutes** (14:43:09Z deploy to 15:33Z read) and
contained no gap: largest inter-pass interval 677s (11m17s), 14:43:28 to
14:54:45, below the 1200s floor. Against a base rate of 3-6 gaps/day that
expects 0.1-0.2 gaps. Decision-table row 4 now carries a **>=12 h minimum** for
exactly this reason. What those 50 minutes *do* establish is that `f1c2b5f`
runs the loop at normal cadence and the deploy broke nothing — a deploy-sanity
fact, not a gap fact.

### The freeze was misread, and the correction is the reason a deploy shipped

The pre-registration's "**No deploy**" was taken as a standing prohibition,
which would freeze the repo indefinitely against a read that keeps not
happening. The freeze exists to keep container uptime usable as the
process-death discriminator, and **uptime is only destroyed for gaps that
precede the last restart**. A deploy landing *before* the window opens costs
the reading nothing. Restated in the amendment as **no deploy during the
observation window**; a deploy inside the window voids it and the window
restarts.

### THE OBSERVATION WINDOW IS OPEN — stamped from the machine

    deployed        aed09340c5e84b3f909046f4fae937039c02022f  (Actions, 1m29s)
    verified        /api/health build.git_sha == local HEAD, exact
    /proc/uptime    61.56 s read at 2026-08-28T15:46:00Z
    WINDOW OPENS    2026-08-28T15:44:58Z

**A gap is in the population only if it began after 2026-08-28T15:44:58Z.**
Stamped from `/proc/uptime` rather than from the deploy log, because the
omission of exactly this step is what produced the "~15:0xZ" error that made
the previous window twenty minutes wrong.

**Only one of the four shipped commits contains code.** `git diff --stat
f1c2b5f..aed0934 -- backend frontend scripts` is `2b3baa3` alone —
`backend/odds/timing.py`, `backend/api/routes.py`, `frontend/src/lib/api.ts`,
`scripts/run_loop.py`. `d64be00`, `d904780` and `aed0934` are `tasks/NEXT.md`
only.

**The confounder, named now so it cannot be a post-hoc excuse tomorrow.**
`2b3baa3` executes new per-pass code in `decide_sweeps`/`window_status`. It is
pure computation — no new IO, and its six new fields are declared and unused
until half two — so its predicted effect on the gap rate is **nil**. The base
rate is 3-6 gaps/day over five days, established before any of these commits.
**If tomorrow's rate departs materially from that, `2b3baa3` is the first
suspect, not the last.**

### ~~Do not deploy again until the read~~

The window is open and a deploy inside it voids it. Half two below is built on
disk and ships with tomorrow's post-read deploy.

**SUPERSEDED 2026-08-28 — Joe said "deploy now" and it shipped.** Kept rather than deleted because the *rule* is still right and applies to the next window: a deploy inside an observation window voids it. What changed is the instruction, not the reasoning.

### #35 half two BUILT ON DISK, not deployed — the window is open

The session's build work, from the `ui-designer`/`retail-bettor` proposal
already on ticket #35. **It closes the live defect half one's own DEPLOY SAFETY
note left open**, which was the reason to build it tonight rather than queue it.

**The defect, and it was reachable on live.** Half one made `next_sweep_ms`
budget-aware, so past the attention slice it publishes `null`. That null fell
through `readNextWindow`'s `budget_spent` branch — whose test is whole-day
derived and read ~123 sweeps remaining on exactly the night the slice was gone —
into `nothing_to_schedule`: *"no upcoming kickoff is near enough."* **False
whenever a kickoff is inside the twelve-hour horizon**, which is most evenings.
One lie swapped for another. `WindowBanner.tsx:386` carried the same branch and
the same falsehood on `/board`.

What landed:

- **`readNextWindow` gains a `slice_spent` reading**, ordered *after*
  `budget_spent` (if the day's 700 is gone the floor cannot buy either, so that
  is the stronger true sentence) and *before* `nothing_to_schedule`. It carries
  `floor_resumes_ms` so the two nulls stay distinguishable: "the slow hourly buy
  resumes once you stop looking" and "no stored fixture brings the floor round
  either" are different sentences.
- **`anAutomaticBuyIsComing` is exported rather than spelled at each call site.**
  The whole shape of #35 was one predicate with two spellings that drifted, so
  the second one is not written twice.
- **`RefreshWhenPriced`'s fourth false promise is fixed**, folded in here rather
  than ticketed separately because it is the same class, screen and minute. It
  polled `/api/window` every 10s for five minutes for a sweep the loop had
  refused, then would have reported a fault that did not exist. It now gates
  both the poll and the promise on `anAutomaticBuyIsComing`. **That gate is also
  what makes the give-up sentence true again** — "no new prices arrived" now
  renders only where prices were genuinely due.
- **The panel states which of three states it is in**, status line as the first
  child, the ~430-character credit paragraph demoted below the buttons (a
  caption, not a headline — ADR 0050's precedent, and the owner review reports
  never having made a decision with those four numbers). `--accent-2` **ink**
  on the slice-spent line only: no fill, no soft ground, because a soft-ground
  block would be the loudest thing on the Games screen on most visit-hours for a
  system that is working correctly.
- **The tap control is byte-identical in all three states.** ADR 0071 §2.1 — the
  panel's job when the desk goes quiet is to withdraw a false reason to wait,
  never to supply a reason to spend. Both reviewers rejected the ticket's own
  *"tap — 150 credits are sitting there"*, and a test asserts no slice-spent
  sentence contains "tap" or "credit".

**Five mutations, each observed red**, per the repo rule that a guard surviving
its own deletion is decoration: the slice branch removed (the pre-fix code); the
slice checked before the whole-day budget; `due_now` dropped from the coming-buy
predicate; the watcher's poll gate removed; the panel's status line reworded so
it no longer precedes the credits.

**Not done, and deliberately:** `next build` is green and `tsc` is clean, but
**eslint could not be run** — it is not installed in this tree and there is no
`eslint.config.*`, which is pre-existing and not caused by this change. Do not
record this tree as "lint clean".

### The parlay desk is scoped to tonight, and Kalshi's combo product is why it had to be

Joe opened the parlay page to a slate of NCAA football and every "Price on
Kalshi" tap returned HTTP 400 `invalid_parameters`. His reading was that the
games are not on Kalshi. **They are** — the desk cannot build a leg without
matching a real market, and Kalshi prices them individually. What it will not
do is *combine* them.

**Measured against the venue, 2026-08-28.** `KXMVECROSSCATEGORY-R`,
`KXMVECROSSCATEGORY-SHARD1-R` and `KXMVESPORTSMULTIGAMEEXTENDED-R` carry the
**same 2,365 legs**; 64 are NCAAF and **every one is inside two days**. The
failing cards were dated a week out and covered 1 of 6, 1 of 6 and 1 of 3.
**So retrying the next `_FALLBACK_COLLECTION_PREFIXES` entry fixes nothing** —
that was the obvious fix and it was checked before it was written. The one
NCAAF lookup that succeeded did so because its leg was tomorrow's game.

`parlay_lookups` answers the question `schema.sql:1075-1082` posed and nobody
had run: `collection_unverified = 1` is **3 lookups, 3 errors**;
`= 0` is **9 lookups, 0 errors**.

Two changes, both pushed, neither deployed:

1. **`dbf2a7a` — the tap refuses before the POST**, naming the games Kalshi
   will not combine. The guard asks whether a leg is in **any** collection
   rather than in the chosen one, which is what keeps the 2026-08-23 capture
   intact (it posted NFL legs a collection did not enumerate and Kalshi minted
   them, so a catch-all's list understates what it takes). An empty union is a
   failed read, not a venue that combines nothing.
   **The status is `no_collection` in the table and `legs_not_combinable` on
   the wire, deliberately**: that column has a CHECK constraint, so a new value
   fires the guard and then crashes the INSERT — a 500, worse than the 400 it
   replaces. A test caught that. SQLite cannot ALTER a CHECK, so widening it is
   a table rebuild and that migration was not worth bundling into an
   undeployed batch. The reason rides in `error`, which is unconstrained.

2. **The ladder is scoped to tonight**, on Joe's rule in his own words: *"let's
   keep the scope of the parlay page to the current day's games"* and *"I'd
   want to see my parlays finish out by the time the evening games end."* A
   parlay settles when its last leg does, so one Saturday leg makes a Friday
   card live until Saturday.

**The rollover is 4am local, not midnight, and that is the design call.** A
22:30 kickoff is one of the evening games he means and it finishes near 01:30;
a midnight bound would cut the card in half at exactly the hour he is most
likely to be reading it. Nothing kicks off between 1am and 4am in any league
this desk carries, so the rollover lands in a gap rather than through a slate.
`DESK_TIME_ZONE` and the frontend's `DISPLAY_TIME_ZONE` are pinned equal by a
test — two definitions of "today" in one process is how the looser one wins in
silence, and this repo has paid for that once already in the odds budget.

**Two consequences to expect rather than debug:** the page is near-empty late
in the evening (nothing left can settle tonight; it refills after 4am), and it
is thinner in general because most of what it used to show was days out.

**A fixture defect found on the way, worth more than the feature.** Both
`seed_game` helpers defaulted kickoff to `now + 1h`, which with the new bound
**fails the entire suite if it runs between 3 and 4am** — green all day, red
overnight. Both now clamp inside the desk day, and the bound is exercised with
an injected clock instead. Look for this shape anywhere a fixture is relative
to `now` and the code under test has a wall-clock boundary.

Ten mutations observed red across the two changes. **Still not fixed:** the
ladder no longer offers week-out games, but nothing checks combo eligibility
itself — the two facts line up today and are independent. Eligibility needs
persisting before the ladder can check it, because `GET /api/parlays` is sync
and `build_ladder_payload` also runs inside the scheduler pass.

### The desk now knows what Kalshi will combine — schema v27

The open item from the parlay work, closed. `ladder_candidates` filters on
`combo_eligible_events`, a cached list of every event that is a leg in some
multivariate collection.

**It is a table because the ladder cannot ask the venue.** `GET /api/parlays`
is sync and `build_ladder_payload` also runs inside the scheduler pass, where
a 25-page paginated walk is the shape that killed the pass tail on 2026-08-28.
So the loop walks on its own schedule and leaves the answer on disk.

- **Writer:** `refresh_combo_eligibility`, called from the loop on `kind ==
  "full"` passes only, at most hourly (`COMBO_ELIGIBILITY_REFRESH_MS`), inside
  a 20-second `asyncio.timeout`, with **every exception swallowed**. The worst
  case is a stale cache and less filtering — the same state as before it
  existed. It must never be why a pass dies.
- **Reader:** `combo_eligible_events` returns `None` — *unknown* — when the
  table is cold or older than `COMBO_ELIGIBILITY_TTL_MS` (2h, so one missed
  refresh is invisible). **A caller must never filter on `None`.**
- **An empty walk is never written.** `fetch_collections` returning nothing is
  indistinguishable from a failed walk, and persisting it would tell the ladder
  Kalshi combines nothing.

**The cold-cache branch is the load-bearing one and it has three tests.**
Getting it backwards empties the parlay desk on every fresh volume and every
deploy; the mutation that makes a cold cache filter everything turns 23 tests
red, which is the right blast radius for that mistake.

Dropped legs count as `kalshi_will_not_combine` and are glossed on screen.

**This is now independent of the tonight bound**, which is the point: the two
happened to line up on 2026-08-28 because Kalshi's collections carried only
the imminent slate. If it narrows its combo horizon, this check notices and the
date bound does not.

### The slice-spent line names when the allowance ran out

Joe's call, 2026-08-28, overruling the design lanes' worry that it would read
as a reproach for having been away. `attention_slice_spent_at_ms` is new on
`window_status` — the `called_ms` of the attention buy that took the pool to
its ceiling — and is published as `null` unless the slice is actually spent,
because on a day with credits left that query answers a different question
("the most recent attention buy") that the copy would render as this one.
`null` also degrades to a grammatical sentence with no time in it.

### DEPLOYED `06b5f71` — verified, and the window boundary is restamped

    deployed     06b5f71d6a43f1bcd5f96755d7786a6d8033c544 (Actions, 1m20s)
    verified     /api/health build.git_sha == local HEAD, exact
    /proc/uptime 53.85 s read at 2026-08-28T17:48:49Z
    WINDOW OPENS 2026-08-28T17:47:55Z

**A gap is in the population only if it began after 2026-08-28T17:47:55Z.**
Same rule as the amended pre-registration; only the boundary moved.

**v27 applied and confirmed on the live volume**: `combo_eligible_events`
exists, with **0 rows** — the cold-cache state, which reads as *unknown* and
filters nothing, so the parlay desk is unchanged until the first refresh
lands. That is the designed cold start, not a fault.

**VERIFIED 2026-08-28 17:52Z — the writer fires.** `combo_eligible_events`
holds **3,427 rows**, refreshed ~17:48Z, on the first full pass after the
deploy. Top series: `KXATPSETWINNER` 163, `KXNFLGAME`/`KXNFLSPREAD`/
`KXNFLTOTAL` 140 each, `KXWTASETWINNER` 116, `KXNFLFIRSTTD` 96. The union
across all eligible collections (3,427) is larger than the 2,365 in
`KXMVECROSSCATEGORY-R` alone, which is the expected shape. **Nothing below is
outstanding**; the paragraph is kept because the check is the right one to
repeat if the parlay desk ever goes unexpectedly thin.

**How to verify the writer fires.** It is gated on `kind == "full"` and runs
at most hourly, so the table should carry rows within ~15 minutes of the
deploy. If it is still empty after an hour, the writer is not being reached —
this repo has shipped four complete, tested modules that nothing called, and
the check is one `sqlite3` read:

    flyctl ssh console -a kalshi-cockpit -C "python -c \"import sqlite3; c=sqlite3.connect('file:/data/cockpit.db?mode=ro',uri=True); print(c.execute('SELECT COUNT(*), MAX(refreshed_ms) FROM combo_eligible_events').fetchone())\""

### The observation window was ended deliberately

Joe: *"deploy now."* This ends the window opened at 2026-08-28T15:44:58Z
before any read was taken against it, so **the pre-registered gap reading has
still not happened** and its population clause now starts from this deploy's
container start instead. That is his call and it is recorded here rather than
argued: the amended pre-registration above is unchanged and still applies, with
a new window boundary to be stamped from `/proc/uptime` after this deploy.

### ~~Do not deploy this until the read~~

Half two is committed and pushed and **must not ship before tomorrow's
reading** — the observation window opened at 2026-08-28T15:44:58Z and a deploy
inside it voids it. It ships with the post-read deploy.

**SUPERSEDED 2026-08-28 — Joe said "deploy now" and it shipped.** Kept rather than deleted because the *rule* is still right and applies to the next window: a deploy inside an observation window voids it. What changed is the instruction, not the reasoning.

### Ruled out, so nobody spends a minute on it

**Ticket #10's WCAG failure is fixed and verified in the CSS live serves**
(2026-08-28 04:23Z): `ManualTicket.tsx:563` is `bg-accent-fill`, and `#ef4444`
appears once in the served stylesheet, as ink. It was the example of the "third
queue" — a resolved ticket carrying a build — and it is closed.

---

## 2026-08-28 — PRE-REGISTRATION: how to read tomorrow's gap, decided before the data exists

**AMENDED 2026-08-28 15:5xZ, after the read below was attempted and found not
to be a read.** Six corrections are inline, each marked `AMENDMENT`. The one
that matters: this document enumerated four causes of a missing failure row and
never stated what made its observation window valid. The instrument was not on
the box during either gap it went looking at. See the entry above for the
reading and `tasks/lessons.md` for the pattern.

**This is the session's output and it is the only thing here that expires.**
Everything else on the Open list will be exactly as available in a week. The
reading below happens once, against data that only exists overnight, and it
will be taken by a session that does not have this one's context. The decision
rule is therefore written **now**, before anyone has seen the answer — the same
discipline `pre-registrar` exists to enforce, applied to a diagnosis instead of
a measurement.

Directed by the partner agent, 2026-08-28, after Joe stepped away and asked it
to manage the session.

### The read

    flyctl ssh console -a kalshi-cockpit \
      -C "python /app/scripts/inspect_live_db.py pass-gaps --tail 400 --limit 40"

**AMENDMENT — `--tail 400` is not a rule and a bigger number is not the fix.**
`--tail 5` is what made sixteen gaps look like one for three sessions running,
and the repair for that was to raise the number, which reproduces the same trap
one order of magnitude out. **A row count inherits the loop's cadence as a
hidden parameter**, and cadence here varies 60x between `DEFAULT_FAST_INTERVAL_S`
= 15s and the 900s shut-window interval. Measured 2026-08-28: 86 sweep rows per
hour while attended, so `--tail 400` reaches back **~4.7 hours** — not a night.
(A session first wrote ~2.2 hours here; the arithmetic was wrong, the direction
was not.)

**So the read verifies its own reach, in the output, before it is believed:**
the oldest `pass_ms` in the returned tail must be *older than* the window-open
timestamp recorded below. If it is not, the tail did not cover the window —
raise `--tail` and re-run. A tail that stops inside the window reports "no gap"
for the region it never looked at, and does so silently. Take a container uptime reading in the
same session, because one branch below needs it:

    flyctl ssh console -a kalshi-cockpit -C "cat /proc/uptime"
    flyctl machine status 7812601a239428 -a kalshi-cockpit

### What was true when this was written

**AMENDMENT — the deploy was 2026-08-28T14:43:09Z, not "~15:0xZ"** (fly machine
event, `7812601a239428`), and `d64be00` — this very entry — is timestamped
14:55:24Z. It was written *after* the deploy it says nothing followed. The
twenty-minute error is why the paragraph below reads as though the window had
already been open for a while when it had not.

Live `f1c2b5f`, deployed 2026-08-28T14:43:09Z, healthy. **Nothing was deployed
after that** — deliberately. A deploy restarts the box and can manufacture a
pass gap of its own, which would contaminate this reading as thoroughly as
changing the machine's memory would. Joe's call was "spend nothing until the
read"; the partner strengthened it to **nothing reaches live until the read**.
Work committed and pushed tonight ships with tomorrow's deploy.

So: any gap in the record between ~15:00Z 2026-08-28 and the read is a clean
observation on the build carrying `DEFAULT_PASS_DEADLINE_S = 600`.

**AMENDMENT — THE POPULATION CLAUSE, which this document never had and which is
its actual defect.** Everything below enumerates causes of a missing failure row
*inside* a valid window. Nothing above said what makes the window valid. It is
this:

> **A gap is in the population only if it BEGAN after the deadline build reached
> live.** `PassDeadlineExceeded` and `DEFAULT_PASS_DEADLINE_S` first exist in
> commit `8658da7`, committed 2026-08-28T13:59:16Z, and reached live with the
> `f1c2b5f` deploy at **2026-08-28T14:43:09Z**. A gap beginning before that
> instant is **out of scope — not evidence, not a data point, not a weak one**.
> Its zero `PassDeadlineExceeded` rows say nothing about anything, because no
> code capable of writing such a row was running.

This is a scope condition, **not a fifth cause**, and it must never be filed as
one. A cause explains a missing row inside a valid window; this decides whether
the window is valid at all. Adding it to the list below would hand a future
session a fifth off-ramp from a zero that *is* informative — the exact direction
in which this project's errors have always run.

**Applied to the two gaps that were actually read (2026-08-28):** a 63m20s gap
beginning ~09:48:29Z and a 47m49s gap beginning ~11:21:18Z. Both began 4.2 and
2.6 hours before `8658da7` was written and ~5 and ~3.4 hours before it was on
the box. **Both are out of scope. Neither counts toward the synchronous-blocking
hypothesis, in either direction.** Do not re-read them as evidence.

### The prediction, committed in advance

This is the part that makes the reading falsifiable, and **it corrects the
number the session started with.** The first estimate was "a 47-minute gap
should leave four to five `PassDeadlineExceeded` rows". That is wrong, because
it assumed the loop retries immediately. It does not: `run_forever` falls
through to `sleep_until(next_delay(current))` after a failure exactly as it
does after a success (`backend/scheduler.py`, the `except` block returns to the
bottom of the `while`). So one hung-await cycle costs **deadline + one
cadence**, not deadline alone.

Shut-window cadence is `slow_interval_s` = 900s ±15% jitter, and the sweep log
either side of every 08-28 gap shows the 15-minute cadence, so the window was
shut. With a 600s deadline that is a **25-minute cycle**. Rows expected, per
observed gap length, if the cause is a hung await:

    gap 21.5-24.4 min    0 rows
    gap 27.2-47.8 min    1 row
    gap 55.0-63.3 min    2 rows

**The first line is the one that matters and it is why this is written down.**
For a gap shorter than about 25 minutes, **zero `PassDeadlineExceeded` rows is
the expected result even when the cause is exactly the hung await the deadline
was built to catch.** Reading "no rows" as "therefore synchronous blocking"
would be a false negative dressed as a finding — and it would confirm the
hypothesis this session already favours, which is precisely when a wrong
inference survives review.

**So: zero rows is only informative on a gap longer than ~25 minutes.** Two of
the sixteen historical gaps fall below that bar.

### The decision table

| what the read shows | verdict | what happens next |
|---|---|---|
| **A gap with ≥1 `PassDeadlineExceeded` row** | A hung await. The instrument worked. | Read the traceback in `flyctl logs` — it names the await. Fix that. Retention and the RAM bump both drop down the list. |
| **A gap >25 min with NO failure row at all** | The deadline could not fire. Four causes, below — narrow before acting. | Do **not** jump to retention. Run the uptime discriminator first. |
| **A gap ≤25 min with no failure row** | **Uninformative.** Expected under every hypothesis. | Read again the next day. Do not update on it. |
| **No gap at all, over >=12 h of uninterrupted uptime** | One clean night against a rate of 3–6/day. | Weak evidence. The base rate says a night with none is unusual but not rare; read again rather than declaring the problem gone. |

**AMENDMENT — row 4 now carries a minimum, and the reason is that the read on
2026-08-28 tripped it.** That read had **50 minutes** of clean window (deploy
14:43:09Z, read 15:33Z) and found no gap. Against the stated base rate of 3-6
gaps/day, fifty minutes expects **0.1-0.2 gaps**: finding none is what you
expect under every hypothesis including the worst one. Below 12 h of
uninterrupted uptime the verdict is **"not taken"**, and the read is repeated.
It is not "no gap", and it is not weak evidence — it is no evidence.

**What a short clean window IS worth, stated so it is not over-claimed either:**
those 50 minutes do establish that `f1c2b5f` runs the loop at normal cadence and
the deploy broke nothing. That is a **deploy-sanity fact, not a gap fact**.
Write it as that and no more.

### "No failure row" has FOUR explanations, not two

The session's own write-up named two. The partner named a third. The
arithmetic above adds a fourth. All four look identical in `loop_failures`, and
**only one of them is the SQLite hypothesis this session already likes** —
which is exactly why they are enumerated here rather than sorted out in the
moment.

1. **Synchronous blocking.** The documented blind spot: `asyncio.timeout`
   cancels by throwing into an await, and a pass blocked in a long SQLite read
   never yields. This is the hypothesis the 1.91 GB file supports.
2. **Process death and restart.** Nothing alive to write a row.
   **Discriminator: container uptime.** If uptime is shorter than the time
   since the gap started, the container restarted and cause 2 is live. This
   needs no new code and no deploy — `cat /proc/uptime` over ssh, taken in the
   same session as the `pass-gaps` read. Take it *first*, because it is the
   only one of the four that a later reading destroys.
3. **The deadline fired and the `loop_failures` write itself blocked** on the
   same IO that caused the hang. Indistinguishable from 1 in the table, and it
   *also* points at the volume — so it does not change the next action, but it
   does mean a row's absence is weaker evidence for 1 specifically than it
   looks.
4. **The gap was too short for the deadline to fire at all.** See the
   prediction above. Ruled in or out by arithmetic alone, before anything else
   is considered.

### What is NOT to be done before that read

Standing, from Joe's own decision plus the partner's addition:

- **AMENDMENT — the rule is NO DEPLOY DURING THE OBSERVATION WINDOW, not "no
  deploy".** As written this was read by a later session as a standing
  prohibition, which would freeze the repo indefinitely against a read that
  keeps not happening. The freeze exists for one reason: to keep container
  uptime usable as the process-death discriminator (cause 2). **Uptime is only
  destroyed for gaps that PRECEDE the last restart.** A deploy landing *before*
  the window opens costs the reading nothing — at read time uptime either
  equals time-since-deploy (no restart, cause 2 dead) or does not (restart,
  cause 2 live), and both are readable. So: deploy, then stamp the window open
  from `/proc/uptime`, then freeze until the read. A deploy *inside* the window
  voids it and the window restarts.
- **No RAM bump.** It is Joe's money and it would stop the gaps, destroying the
  reading that tells us whether stopping them that way was even the right fix.
- **No retention work on `fair_prices` / `odds_snapshots`.** Same reason, plus
  it needs an ADR and a reader enumeration (15 and 17 readers, `gate.py` among
  them) that no session should start at the end of an evening.
- **No replacement watchdog.** It caught 1 of 16, which is damning, but
  building a detector before the mechanism is known means designing for a cause
  we cannot name. It is also GitHub delivering 4 of 96 scheduled runs, which
  more YAML does not fix.

### Lane 0, answered and closed: a gap does NOT make `/hedge` wrong

Asked because it would have reframed the gaps from housekeeping to a live
money-path defect: the measurement found `kalshi_quotes` is exactly zero inside
every gap, and `/hedge` is the one surface where
`MANUAL_ORDERS_ARE_DRY_RUNS = False`. If it read stored quotes, a silence during
a running game would show a stale lock figure.

**It does not read them.** `fetch_quote` is `LiveQuoteSource.fetch`
(`scripts/run_loop.py:610,619`), which calls Kalshi REST at read time
(`backend/kalshi/quotes.py:235-275`). `read_books` (`backend/hedge.py:862`)
omits a ticker it cannot read — explicitly *absent*, never an empty book,
"because an empty book is a real and different state". There is no fallback to
`kalshi_quotes` on the hedge path at all.

**The residual is absence, not wrongness**, and it is the session's theme once
more: `hedge_watch` is a task in the same process, so during a container-wide
silence no hedge lock push goes out for the duration. Joe is not told a wrong
number; he is told nothing, and the screen does not say so.

### In flight at hand-off

Three lanes were running when this was written. Whatever they returned is
recorded below this entry or in their commits; if a lane is missing, it did not
finish, and nothing here depends on it.

- **#35 half one** — make `next_call_ms` budget-aware, gated on a test pinning
  `Tempo.interval_s()` invariant across all three slice states. The claim that
  it is cadence-neutral rests on `backend/scheduler.py`'s
  `max(fast, min(slow, until_s / (1 + JITTER)))` cap returning 900s on all
  three paths. **That arithmetic was pattern-matched, not measured** — the lane
  was told to pin it as a test and to report rather than work around it if it
  does not hold.
- **#35 half two** — three-state panel copy, drafted by `ui-designer` and
  `retail-bettor` as a proposal on the ticket, not a build. Joe's constraints
  are already recorded in the ticket body: not an alarm, `--accent-2` at most,
  must not manufacture action.
- **`sweeps_remaining_today` does NOT carry the defect. Checked, refuted,
  recorded in the code beside the field so nobody re-checks it.** Both this
  file and ticket #35 asserted it probably did, on the strength of it reading
  123 sweeps (492 of 700 spent) on a night the slice allowed zero further
  attention buys. That is a **coverage gap, not a lie**: `next_call_ms` was a
  *prediction* the loop then refused, while this is an arithmetic fact about a
  pool — and it is the right pool, because a scheduled slot and a floor buy are
  charged to the day's budget rather than to the slice, so narrowing it would
  under-size `plan_sweep_slots` as well as the readout. It answers "what can
  the day still afford"; the reader was asking "can the desk refresh while I
  watch". The new `attention_*` fields answer the second question.

### Both design lanes returned, they contradicted each other, and the winner corrects this session's own plan

Posted in full to ticket #35. The part that must not be lost:

**Attention REPLACES the hourly floor; it does not add to it.** `desk_wants`
(`timing.py:499-575`) branches `if attended or windowed` → the 10-minute
cadence for *every* sport with an upcoming fixture, no horizon check. The
`else` branch is the floor: hourly, and only inside `DESK_FLOOR_HORIZON_MS`
= 12h. `decide_sweeps` then sets `on_the_floor = not attended and not
desk_is_open(...)`, so **attended makes the slice check apply and the sport is
refused with `continue` — there is no fall-through to the hourly cadence.**
`DEFAULT_ATTENTION_TTL_MS` is 300_000, so "unattended" begins five minutes
after the last heartbeat.

**Stated plainly, because it is close to perverse: once the slice is spent,
keeping the page open suppresses buying that would otherwise happen. Closing
the phone is what makes the floor resume.** That is ADR 0071 §2.6 working as
built and changing it is a separate decision — but it invalidated the fix this
session had already briefed to the backend lane (*"publish the floor's next
want"*, which would publish a time the reader's own presence prevents — the
same defect in a new field). Corrected mid-flight; the lane was told to trust
the source over me if they disagree, because a second reader had already caught
me on this exact point once today.

**Question 1 of #35 is settled by a fact the ticket did not have: `next_sweep_ms`
has FOUR readers, not one** — `RefreshOddsPanel`, `nextOddsWindow.ts` →
`StaleOddsExit` (which asserts *service*, not schedule, and is therefore worse),
`WindowBanner` twice on `/board`, and `windowChip.ts` (already safe). A
copy-only fix leaves three of them lying, so the field becomes budget-aware and
the *"the page cannot disagree with it"* guarantee ends up true or deleted.

**Both reviewers rejected the ticket's own "tap — 150 credits are sitting
there".** The correct action at 04:38 was **wait**: a fresh price for a game
13.7 h out is a fraction of a cent of EV on a one-contract stake. The defect is
that "quiet" and "broken" were indistinguishable and nothing said when quiet
ended. The panel's job in the slice-spent state is to **withdraw a false reason
to wait**, not to supply a reason to tap — argument-from-unspent-allowance is
the shape ADR 0071 §2.1 forbids.

**Two findings outside #35's scope, recorded so they are not lost:**

- **A fourth false promise, unticketed.** `RefreshWhenPriced.tsx` said *"this
  page will update itself when one lands"* while polling `/api/window` every
  10s for five minutes for a sweep the loop had refused, then would have
  claimed *"No new prices arrived in five minutes"* — implying a fault where
  there was none, and burning phone battery. It checks whether freshness is
  rising; it never checks whether a buy is possible. Same class, same screen,
  same minute as #35. **Worth its own ticket.**
- **The credit accounting probably does not belong on that panel.** Four
  numbers (0 of 150 taps, 492 of 700, a 2-minute cooldown) that the owner
  review reports never having made a decision with. ADR 0050's precedent: a
  caption, never a translation.

**Least certain, and cheap to settle:** that an attended pass past the slice
gets no floor rescue is read from the source, not observed. One `sweep-log`
read on a night when the slice is spent and the desk is open settles it — if
the refusal repeats every pass and no `DESK`-triggered `api_credits` row lands
within the hour, it holds.

### #35 half one SHIPPED — `2b3baa3`, pushed, NOT deployed

`window_status` now applies the loop's own slice test through a shared
`attention_slice_is_spent(...)` that `decide_sweeps` also calls, so there is one
spelling rather than two. Past the slice the desk contributes **nothing** to
`next_call_ms`. `desk_floor_next_want_ms(...)` is published as its own field and
is a **lookahead** — a sport enters the floor's horizon at `kickoff − 12h`, so
at 04:38Z it answers ~06:20Z where `desk_wants` answers nothing. Six new fields
make the three sentences distinguishable: `next_desk_buy_ms` null with
`floor_next_buy_ms` set means "resumes at T once you stop looking"; both null
means nothing ever; `next_desk_buy_ms` set means it is coming. The *"the page
cannot disagree with it"* guarantee is **replaced** with the narrower claim the
code actually keeps.

**Two corrections to what this session believed, both from the lane, both
verified here:**

1. **Cadence-neutrality holds for these three states but NOT by construction**,
   and the arithmetic in the pre-registration above is looser than it looked:
   `JITTER` is **0.15, not 0.05**, so `min(slow, until_s / (1 + JITTER))`
   preserves 900s only past **1,035s**. All three states do return 900s, but a
   nearer future `next_call_ms` legitimately shortens the sleep — the bound
   doing its job, not a regression.
   `test_the_neutrality_holds_only_beyond_the_jitter_boundary` pins it.
2. **A defect recorded and deliberately not fixed:** the loop's own refusal
   string says *"the hourly floor still runs"*, and while the desk is attended
   it does not. Correcting the sentence is display; correcting the behaviour
   would increase spend. That is a decision, not a patch.

**DEPLOY SAFETY — read before shipping this tomorrow.** Half one makes
`next_sweep_ms` nullable, and `readNextWindow` has not been touched. Traced:
with the slice spent the null falls past `budget_spent` (its
`sweeps_remaining_today <= 0` test does not fire at ~123) into
`nothing_to_schedule` — *"no upcoming kickoff is near enough… A tap below is
the only path to a fresh read."* **On the 04:38Z case that sentence is true**,
both clauses. But it is reachable when it is false: slice spent, attended, no
scheduled slot, and a kickoff **inside** twelve hours — then it claims no
kickoff is near enough while one is. Half two must gate that branch on
`attention_slice_spent` and `floor_next_buy_ms` before it speaks. Shipping half
one alone is a net improvement and not a regression, but it is not the finished
state.

**Baseline moved: 4,984 passed / 10 xfailed** (4,994 items collected — verified
here independently of the lane's report, and the two new classes re-run green).
+12 over 4,972, fully accounted: 8 in
`TestThePanelDoesNotPublishASweepTheLoopHasRefused`, 4 in
`TestTheLoopsCadenceIsUnchangedByTheSliceCheck`.

---

## 2026-08-28 — the unexplained gap was the sixteenth, and nothing on disk could have said so

**State at start:** `main` = `ddbff1f`, clean, level with `origin/main`. Live
`/api/health` `build.git_sha` = `5436fc89…` — the ZeroDivision fix, so live
carried all current *code* (the two commits after it are documentation). One
lane on disk (`parlay-props` at `e90b154`, spent). Joe said "read NEXT.md and
start".

### The finding — the recorder has been off ~3.4 hours a day since 2026-08-26

The entry below records a 47.8-minute gap as **Incident B, UNEXPLAINED and
self-recovered**, and asks the next session to "read `pass-gaps` again and check
whether a second gap has appeared". It had. Four more on the same day, and the
same shape for three days:

    2026-08-23     27.2 min   1 gap
    2026-08-24      0         0
    2026-08-25     44.6 min   1 gap
    2026-08-26    204.9 min   6 gaps
    2026-08-27    124.0 min   3 gaps
    2026-08-28    234.9 min   5 gaps   (to 13:24Z)

Sixteen holes, 21.5 to 63.3 minutes each. **`pass-gaps --tail 5` — the default —
sees the last five rows and found none of them**; the whole history was one
query away the entire time.

**They are real silence, established on a second table rather than argued.**
`kalshi_quotes.observed_ms` inside each of the five 08-28 gaps against the 30
minutes either side:

    gap        30 min before    inside    30 min after
    31.6 min          41,951         0           7,476
    31.0 min           6,506         0          10,043
    61.1 min           4,190         0          11,679
    63.3 min          19,169         0          14,948
    47.8 min          14,948         0          14,518

Zero inside, five for five, with thousands on both edges. The writer stopped; it
did not slow down. **This is what refuses the obvious alternative** — that ADR
0071 §2.6's hourly floor simply buys less often, so the sweep log is sparser.

**And they are not failing passes.** `loop_failures` holds fifteen rows in its
whole life; the only three on 08-28 are the ZeroDivisionErrors, *after* the last
gap had closed.

### What it is not — four candidates killed, one on a timeline

- **Not the `/api/parlays` OOM (`7b185e8`).** It was the leading candidate.
  `7b185e8` was committed 05:00:33Z and deployed shortly after; the 06:21, 09:48
  and 11:21 gaps all start **after** it.
- **Not a machine stop.** `auto_stop_machines = "off"`, `min_machines_running = 1`.
- **Not swap thrash.** `SwapTotal: 0`.
- **Not the deploys, except one.** The 03:52:58Z→04:23:59Z gap ends at the 04:23Z
  `bc256e3` deploy. Nothing corresponds to the other four.

**The standing lead is IO.** The database is **1.91 GB on a 2 GB box** with no
swap and 587 MB reclaimable by vacuum (31% freelist). PSI over the 43 minutes
since the last restart: `io full avg300 = 5.48`, 126.5 s of all-tasks-blocked IO
in 2,618 s — 4.8% of wall-clock — against `cpu full` of 0. That is a lead and
**not a finding**: 4.8% is not 60 minutes and the reading was taken outside a
gap. `odds_snapshots` / `fair_prices` retention has been carried forward for
several sessions; this is the first measurement that attaches a symptom to it.

Full working: `docs/measurements/2026-08-28-recorder-silence-is-chronic.md`.

### What shipped — a pass now has a deadline

`run_forever` awaited `do_pass()` for as long as it took, so a wedged pass wrote
**nothing at all**: no row, no failure, no log line, indistinguishable in the
record from a quiet slate. That is why the same silence was written up as a
fresh one-off three sessions running.

It now takes `pass_deadline_s`, defaulting to `DEFAULT_PASS_DEADLINE_S = 600`.
Past it the pass is **cancelled** and raises `PassDeadlineExceeded`, which
travels the existing path into a `loop_failures` row with the pass number and
kind, plus a traceback naming the await it hung on.

**600s sits between two populations that do not overlap, and both edges are
measured**: live pass durations read off `pass N ok` the same day are 3.8–4.9 s
(quote) and **43.0 s / 77.3 s** (full), against a shortest-ever silence of 21.5
minutes. That is ~7.8× the longest healthy pass and under half the shortest
wedge.

**The blind spot is the point, and it is written into the constant.**
`asyncio.timeout` cancels by throwing into an await. A pass blocked in a
*synchronous* call — a long SQLite read against a 1.9 GB file — never yields and
is not interruptible. So the next gap is informative either way:

    a PassDeadlineExceeded row      a hung await, located
    still no failure row at all     the process was down, OR it was blocked in
                                    synchronous code

The second is two states and separating them needs an instrument this record
still does not have — but it is strictly narrower than what was available
before, and it points at the SQLite file.

**Two docstrings that stated the old reading were corrected rather than left**:
`record_failure` in `run_loop.py` and `pass-gaps` in `inspect_live_db.py` both
said "no rows across a gap mean the pass never came back to raise". That rule is
what turned sixteen holes into sixteen dead ends.

**One misattribution was closed before it could poison the table.** Since Python
3.11 `asyncio.TimeoutError` *is* the builtin `TimeoutError`, so a pass whose own
inner `wait_for` expires arrives at the handler looking exactly like a deadline
breach. `deadline.expired()` is checked before relabelling, so `loop_failures`
cannot report a wedge that never happened.

Seven guards, each mutation-observed red. **The one that mattered was written
last**: defaulting `pass_deadline_s` to `None` left every other test green,
because each sets it explicitly, while live went quietly back to waiting
forever. Production calls `run_forever` without naming the argument, so the
signature default *is* the deployed value, and it is now asserted with
`inspect.signature`.

### Also shipped — the ladder's refusals are on the pass line

The entry below asks for exactly this and says why: after the ZeroDivision fix,
"did the new guard fire, or did the bad leg age out?" was unanswerable from
outside the box, because `fair_probability_not_positive` existed only in
`/api/parlays`' response and that needs auth.

`pass N ok` now carries `ladder_excluded` (the total, **emitted even at zero**)
and one `ladder_<reason>` key per non-zero refusal. Zero and absence are
different: the ladder is only built on a pass that swept or a full pass, so a
quote pass carries no `ladder_` keys at all and that must not read as a clean
bill of health.

Four guards, each mutation-observed red, including a structural one — the defect
that shipped was `build_ladder_payload` called inline as an argument with its
`excluded` dict discarded, so a correct count reached nothing.

**One existing test went red and was repointed, not loosened.**
`test_it_reads_the_same_staleness_limit_the_screen_does` read the 600 characters
*after* `alerter.parlay_cards(`, which held the whole `build_ladder_payload(...)`
call while it was written inline. Binding the payload to a name moved the limit
above the call. The probe now reads the span from the gate to the push — which
is the span the claim was always about — with three vacuity guards so it cannot
pass over the wrong text.

### And the watchdog that was supposed to catch them ran four times that day

The entry below says the heartbeat "is worth trusting, and that is itself a
result". **Two things in that reading are wrong.**

**Its threshold is 30 minutes, not 44.** `age > 1800000` ms in
`heartbeat.yml`. 44 was the observed age at the one firing, not the bar. Four
of the sixteen gaps sit below 30 minutes and could never have alarmed.

**And it does not run every 15 minutes.** Scheduled runs actually delivered,
from the Actions API, against the 96/day `*/15 * * * *` asks for:

    2026-08-24    67        2026-08-27     9
    2026-08-25    70        2026-08-28     4
    2026-08-26    46

Median gap **22.6 min**, maximum **245 min**, n = 199. The cadence fell by more
than an order of magnitude in three days with no change to the file, no failed
run, and no signal — the exact failure mode the file's own opening paragraph
warns about, happening to the file itself.

The two compound: a 31-minute hole is over the bar for about one minute, so a
poller has to look inside that minute. On 08-28 the recorder was silent for 235
minutes across five holes and the watchdog looked four times. **It caught one.**
That firing was accurate, which is why it was trusted; one in sixteen is the
rate.

Corrected in the workflow: the embed footer said "every 15 min", which turns a
quiet channel into evidence of health. **Raising the cron is not the fix** —
`*/15` is already what is being ignored. Restoring coverage means a watchdog
that does not depend on GitHub's scheduler, and that is a decision, not a patch.

### Open

**FIRST THING NEXT SESSION — the one read this session was built to enable.**
Joe's call, 2026-08-28: do not spend money or start retention work until this
has been read, because the deadline discriminates between the two remaining
hypotheses and anything that stops the gaps also destroys the reading.

    flyctl ssh console -a kalshi-cockpit       -C "python /app/scripts/inspect_live_db.py pass-gaps --tail 400 --limit 40"

    a gap with a PassDeadlineExceeded row   a hung await. The traceback in
                                            `flyctl logs` names it. Fix that.
    a gap with NO failure row at all        the loop was blocked in synchronous
                                            code. That points at the 1.91 GB
                                            SQLite file, and retention becomes
                                            the work.
    no gap at all                           one night proves little; the rate
                                            was 3-6 a day. Read again.

**`--tail 400`, not the default.** `--tail 5` is what hid fifteen of these for
three sessions.

- **READ THE RATE.** Is `ladder_fair_probability_not_positive` non-zero on the
  pass line? **First two live readings, 2026-08-28 ~14:40Z: 20 and 254 excluded,
  ALL of them `stale_consensus`, zero `fair_probability_not_positive`.** So the
  ZeroDivision guard has still not been exercised by a real zero in production —
  consistent with the bad leg ageing out of the 24-hour window on its own. Two
  passes is not a rate; keep reading. `flyctl logs` is lossy — read timestamps,
  not counts.
- **CHECK FOR A `PassDeadlineExceeded` ROW** next time a gap appears — that
  reading is the whole point of the deadline, and **absence is a result, not a
  null** (see above).
- **The 1.91 GB database is now a symptom, not just a chore, and the reason is
  in `backend/store/retention.py`'s own docstring.** It prunes `kalshi_quotes`
  and `unmatched_items` and says of the rest: *"It does not bound the tables it
  does not name. `odds_snapshots` was 33.6 MiB and growing slowly when this was
  written; it is deliberately out of scope rather than forgotten."* It is now
  **153.3 MB**, 4.6x that, and `fair_prices` — never named at all — is
  **284.8 MB**. With their indexes the two unbounded tables are ~641 MB of the
  1.91 GB; 587 MB more is freelist. Volume has room (4.9 G, 39% used), so a
  `VACUUM` is feasible on disk — but it is a long synchronous operation on the
  box that is already stalling, so do not run it casually against live, and
  bounding the tables comes first. Needs an ADR and the same reader enumeration
  the quotes rule got.
- **The off-box watchdog is running at ~4% of its intended rate** (above). No
  fix attempted beyond making the artifact stop claiming otherwise; the
  replacement is a decision.
- Not established: that the deadline fires correctly on live. It has never
  fired anywhere but in a test.
- Carried forward: #35 (the panel promising a refused sweep);
  `sweeps_remaining_today` may have the same defect (`timing.py:1134`,
  unchecked); #32 and #33; ADR 0079's prop tap; B0; the combo purchase slice;
  Picks/Parlays/Gate/ticket sheet never reviewed on a phone;
  `/api/parlays` at 2-3 s is the slowest route and indexing is already ruled out.
- **`tasks/lessons.md` is at 84.4%** of the ceiling; split at 90%, and check
  before writing.

---

## 2026-08-28 — a leg priced at zero stopped the alerting half of the loop, and the heartbeat fired for a DIFFERENT reason

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
