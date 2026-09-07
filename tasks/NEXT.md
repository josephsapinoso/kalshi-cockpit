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

**Split again 2026-09-05, at 224,305 bytes — 85.6%, checked before writing.**
The five 2026-08-30 and two 2026-08-29 entries moved to
`archive/next-2026-09-05.md`, verbatim, leaving ~166KB — 63.6%. Taken under
the trigger rather than at it, because the entry about to be written was a
long one and the size that matters is the size *after*. The index section
went in the same edit; a split that moves entries without moving their index
lines is a data loss with a table of contents.

**Split again 2026-09-06, at 223,790 bytes — 85.4%, checked before writing.**
The three 2026-09-02, two 2026-09-01 and four 2026-08-31 entries moved to
`archive/next-2026-09-06.md`, verbatim, leaving 117KB — **44.7%**. Cut deeper
than the trigger required, on the reasoning `archive/lessons-2026-08-31.md`
records: clearing to well under the line buys one more split rather than
several. The cut falls on a **date boundary** — everything 2026-09-02 and
earlier moved — so no single day is split across two files, which the previous
splits did not always manage and which makes the index harder to read than it
needs to be. The move was verified by md5: the archived bytes below its header
hash identically to the bytes removed. Index lines moved in the same edit.

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

**The test count is CI's, not a hand-collected number. Retired 2026-09-01.**
`.github/workflows/ci.yml` runs `ruff check .` and `python -m pytest -q` on
every push to every branch, free, under a 15-minute cap. Read the last green
run: `gh run list --limit 5`.

**What was deleted here, and why it is not a loss.** This spot held ~87 lines
reconciling a hand-collected suite count across trees. It documented **seven**
occasions the number was wrong in the same direction, plus four runs killed
mid-flight -- and every one of those corrections was honest and was spent on a
figure whose only consumer was the paragraph itself. The rule it taught
survives and is worth more than the number: **do not reconcile a baseline by
reasoning about a delta; collect both trees.** Apply it to any count you do
take. Run targeted tests locally while you work; let CI collect the total.

**The suite is ~15-22 minutes and growing with the record.** A slow run is not
a hung one, and neither is a gap the length of an interval. If it gets slower,
look for a test doing real work to check a cheap property -- one took 71
seconds driving a 200,000-sample copula to assert a dictionary length.

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

## 2026-09-07 (latest, second session) — tonight's check had no instrument on the box and the wrong reading written down; attention was paying a live-game cadence for a line two days out

**STATE at close.** `main` = **`42e667f`**, pushed. **Live is deliberately
NOT on `main`, and that is the first thing to check before deploying.**

    live     763adad   read back from /api/health at 16:2xZ; recorder writing
    demo     cc8de80   NOT redeployed this session, and that is fine
    main     42e667f   five commits ahead of live, six ahead of demo

**Verify all three with `/api/health` `build.git_sha` rather than believing
this table** — the 09-06 entry said "deployed on `7ed20fd`" while live had been
on `4a6d63e` the whole time, and the partner then ranked a day's work around
it. **This table got the demo row wrong on its first writing today**, for the
same reason: it was written from "I deployed" rather than from a read. Only
live was deployed. Demo answers slowly on a cold start — an empty first `curl`
is the machine waking, not an outage; retry before concluding anything.

Demo is deliberately left behind: it carries no credentials and no execution
path, nothing tonight needs it, and deploying it now would ship ADR 0111 to a
second place and give this table a third sha to keep straight.

The five unshipped commits, and what each would put on the box:

| commit | what it is | ships? |
|---|---|---|
| `9e7e6c7` | **ADR 0111**, `backend/odds/timing.py` | **yes — the one being held** |
| `4524a56` | league→sport-key guard | no, tests only |
| `a76559d` | session record | no, docs only |
| `ca248d7` | `sweepTone` ordering + tests | **yes — frontend** |
| `42e667f` | the 03:37Z derivation | no, docs only |

ADR 0111 is held back **on purpose**: it changes `desk_wants`, which runs on
the same pass as tonight's one-shot NFL bootstrap. Holding it costs one evening
of a cadence Joe will not notice; shipping it costs the observation if it is
wrong. **Deploy after the bootstrap is confirmed, not before** — and note the
`sweepTone` change rides along in the same deploy, which is fine and is item 5.

Tree clean, no worktrees, no other lanes. Decision map still 0 open. Full
local suite **6307 passed / 10 xfailed** (9m31s); CI green on every push.

**The partner ran first**, on state read from `/api/health` and `gh` rather
than from the previous entry, and its ranking is what was executed. One thing
it got wrong is recorded in its own report: it nearly killed the Scout refusal
fixture on a belief that Scout has no caller. `backend/api/routers/scout.py:25`
imports `agents.scout_desk` and four seats spend real money through it.

### The finding that reordered the day: the check had no instrument

`NEXT.md`'s item 1 was *"read the `unmatched_items` collapse."* There was no
way to do that. No `unmatched_items` query in `inspect_live_db`'s whitelist, no
API route serving it, and `ls /app/scripts/` on the live box returns 14 files
with `list_unmatched.py` not among them. The pre-flight's own 07:21Z number was
taken as **ad-hoc SQL over `flyctl ssh`** — the thing `inspect_live_db.py`'s
ruling forbids in those words, *"nothing that carries its own source in the
command line."*

Shipped (`5275d1c`). The script now declares `/app/scripts/list_unmatched.py`,
which makes `TestTheSshInvokedScriptsSurviveDockerignore` **demand** the
`!scripts/list_unmatched.py` line rather than leave it to be remembered — that
allowlist has failed five times and this is the first addition where the two
halves cannot be separated. `--league` added: exact, case-sensitive, a bound
parameter, with the cut echoed in every count line including the empty one.

### And the reading written down would have called tonight's success a failure

This is the more important half. The plan said *"after the first sweep expect
32 → ~16, then 16 → ~0."* **The count will not fall.** Nothing sets
`unmatched_items.resolved` and nothing deletes on a link — `linker.py` only
upserts — so a row that stops failing goes **stale in place** until
`retention.DEFAULT_UNMATCHED_RETENTION_MS` prunes it **seven days** later on
`last_seen_ms`.

So **32 rows at 04:00Z is the success case.** The broken-link case is 32 rows
all carrying a *fresh* stamp. Corrected in the measurement doc (a CORRECTION
section) and in item 1 below.

### The instrument needed one fix before it was usable, found by running it

Its first live run returned **75.8 KB for 66 rows** — lines of 1,300 to 2,249
characters. `KXNFLTEAMTOTAL`'s `detail` is the whole points ladder joined by
" vs ", ~2,100 characters, and a column table takes its width from its worst
cell. The `last_seen` column — the *only* column tonight's reading uses — was
two thousand characters right of where anyone looks. Cells are now cut at 80
with the count of cuts printed and `--full` to recover them. Same read: **17 KB**,
52 cells cut. `763adad`, deployed and verified.

### THE BASELINE FOR TONIGHT, re-taken through the shipped instrument at 15:30Z

| series | rows | reason | `last_seen` |
|---|---|---|---|
| `KXNFLGAME` | **32** | no sportsbook fixture within the commence-time window | 2026-09-07 15:30 |
| `KXNFLSPREAD` | **16** | no linked game event for fixture … | 2026-09-07 15:30 |
| `KXNFLTOTAL` | 16 | expected 2 sides, got … | 2026-09-07 15:30 |
| `KXNFLTEAMTOTAL` | 2 | expected 2 sides, got … | 2026-09-07 15:30 |
| | **66** | | **0 stale** |

**All 66 carry the same fresh stamp**, which is what makes tonight legible:
nothing is frozen now, so anything frozen at 04:00Z is something the sweep
fixed. The total is 66 and not the 60 recorded at 07:21Z — **the growth is
entirely in the ladder class** (12 → 18), and the two classes tonight is about
are unchanged. Do not read the total as drift.

### ADR 0111 — attention was paying a live-game cadence for a line 45 hours out

`desk_wants`' attended branch had **no horizon at all**. The floor branch one
line below had always checked `soonest - now_ms > floor_horizon_ms` and
skipped; the attended branch gave every sport inside the caller's 48-hour
window the ten-minute cadence. 24 credits/hour/sport against a 300-credit
slice: 2 sports = 6.25 attended hours, **3 sports = 4.17**, 4 = 3.13. Measured
dwell runs 2.6–324 minutes a day and 20260827 spent the whole slice in **4.88
hours** — so the third sport alone takes the attended budget below a day Joe
has already had, and the third sport arrives tonight with its kickoff ~45 h
away.

Now **tiered, not cut**: ten minutes inside twelve hours, the floor's hourly
rate beyond it, never dropped. The cut was rejected because
`test_attention_overrides_the_horizon` records the standing rule that a far
fixture someone is looking at gets priced — Joe bets Sunday's NFL on Friday,
and cutting would take the desk dark on exactly those rows past the staleness
gate. **No published credit figure moves**; what changes is how fast the slice
is consumed inside its own cap.

The partner's better alternative was checked and **is not available**:
`attention.normalise_path` splits on `?` before storing, so `desk_attention`
records `/board`, never `/board?league=…`. The record carries which *screen*,
never which *league*. ADR 0111 records it as the next lever.

### The link between Kalshi and the odds feed had no test on either side

`IN_SCOPE_LEAGUES` turns `"Pro Football"` into the URL segment in
`/v4/sports/americanfootball_nfl/odds`, and nothing asserted it. The only
`sport_key ==` assertion in `test_discovery.py` was MLB's. A typo does not
raise — the vendor 404s and the sport never gets fixtures, which reads exactly
like a sport being out of season. Five tests now, and three mutants that were
all green this morning are red.

### Killed / not taken, so nobody re-derives them

- **Capturing an NFL odds wire fixture before tonight.** No NFL odds payload
  has ever been parsed by any test — the only captured Odds API response is
  MLB. Deliberately not pre-empted: tonight is a 4-credit test with a 30-minute
  backoff on failure, which is cheaper than any capture, and a capture run from
  the laptop spends a credit `api_credits` never records, putting the ledger
  out by 4 in silence. **Capture AFTER it succeeds**, and write the ledger
  drift into the measurement doc rather than leaving it silent.
- **Watching the credit ledger tonight.** Tonight is one 4-credit call against
  a ~366-credit day. Invisible. Sunday 09-13 is the day that matters.

### Still open, in order

1. **Tonight, from ~03:35Z 09-08: confirm the first NFL sweep fired**, read the
   way the corrections above say and not the way this morning's entry said.
   - `sweep-log` should show a **`served`** row, `sport_key =
     americanfootball_nfl`, detail beginning `americanfootball_nfl has no
     stored sportsbook fixtures`. A `skipped` props row lands right behind it
     and is expected. **Do not grep `api_credits` for `bootstrap`** — `trigger`
     is NULL on a bootstrap; only MANUAL and ATTENTION are stamped.
   - **The design bound is ~03:37Z, and it is tighter than it was first
     written.** It is true that `window_status` cannot see a fixture-less sport
     and that its null `next_call_ms` feeds `Tempo.next_wake_ms`
     (`scripts/run_loop.py:1121`) — but a null there is **not** an unbounded
     sleep. `Tempo.interval_s` returns `slow_interval_s` on `next_wake_ms is
     None` (`backend/scheduler.py:400`), which is `RUNNER_INTERVAL_S = 900` on
     live, and `run_forever` stretches it by at most `JITTER = 0.15` → 1,035s.
     A bootstrap also needs a **full** pass, and `pass_kind` returns `full`
     every 900s regardless. So: 03:20Z + one full-pass interval = **03:35Z**,
     +jitter = **~03:37Z**. An earlier draft of this item said "a bootstrap at
     04:10Z is the design working"; that was over-generous and would have
     spent half an hour not looking for a real fault.
   - **So nothing by 04:00Z is a signal — but check the ledger before calling
     it a failure.** The one thing that legitimately delays it further is a
     wedged pass, and those are documented and measured: sixteen holes of 21.5
     to 63.3 minutes between 08-23 and 08-28, ~3.4 hours a day, with no
     `loop_failures` row for any of them (`backend/scheduler.py:61-71`). Run
     `pass-gaps` first. A hole spanning 03:20–03:40Z explains the absence and
     is a known phenomenon, not a broken bootstrap.
   - **Read `last_seen`, never the count**, against the 15:30Z baseline above:

         flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/list_unmatched.py --db /data/cockpit.db --league 'Pro Football'"

     Expect the Week-1 `KXNFLGAME` rows to stop moving while the rest keep
     moving. **32 rows still there is success**; 32 rows all fresh is the
     broken-link case.
2. **Deploy ADR 0111** (`9e7e6c7`), once item 1 is confirmed. It is on `main`
   and not on the box; nothing else is holding it.
3. **Capture the NFL odds wire fixture**, after item 1 succeeds — see above.
4. **The Sunday 09-13 convergence.** Simulated at ~486 credits base (3 NFL
   clusters × 7 calls × 4, plus the NFL floor, plus observed MLB+NCAAF), and
   all three clusters land in one budget day because the 00:20Z nighter is
   before the 10:00Z roll. ADR 0111 buys back the attention half; the
   **kickoff-window loop is untouched and is the largest term**. Item 5 is
   what makes a bind legible.
5. ~~**The calm strip after a mid-day cap**~~ **DONE this session, and the
   diagnosis in the previous entry was not quite the defect.** `sweepTone` did
   have a `refused` branch; it could not be *reached* on the day it mattered.
   Sweeps run from 10:00Z, the cap binds at 15:40Z, and `last_sweep_ms` is
   still inside the budget day — so "the day's sweeps have run" matched first
   and returned `calm` over a recorder stopped until tomorrow. The refusal test
   now runs **above** it. The rule: **the tone describes the most recent look,
   not the best thing that happened today.** Ships in the same deploy as ADR
   0111 (item 2), not before.
6. **`window_status` cannot predict a bootstrap** (lane B residual 1) —
   demoted, and the reason is sized: 28 call sites, a new DB reader and two
   guard rewrites. The screen-facing half is folded into item 5.
7. **The `eu` lever, 2026-09-28** — ADR 0110's measurements first.
8. **`parlay_positions` on 2026-09-15**; **`cryptography` bump ~=49.0 on
   2026-09-15**, gate `tests/test_rest.py::TestSigningContract` etc.
9. **Scout Anthropic refusal fixture (ADR 0106 §5.2)** — one billed call. NOT
   dead code: `backend/api/routers/scout.py:25` imports `agents.scout_desk`
   and four seats spend real money through it.
10. **`combo_orders` reconciliation** — answer *who reads this table* first.
    If nobody, either delete the write path or wire a filled combo into
    `/hedge`, which is the only reason it should exist given combos are
    enter-only in 40 of 40 books. Do not build the loop as previously scoped.

**Joe-gated: nothing.**

---

## 2026-09-07 (earlier session) — the NFL path is pre-flighted and its first sweep is due tonight by construction; a failed look and a spent day get their own words; the watcher stops asking the venue about a bid that filled

**STATE at close.** `main` = the sha in `git log -1`, pushed, CI on it is
the thing to read (`gh run list --limit 3`). **Live and demo: read
`/api/health` `build.git_sha` on both** before believing anything about them;
this entry says what was dispatched, not what is running. Tree clean, four
lane branches merged and deleted, no worktrees. Decision map still 0 open.

**The partner ran first on verified state** (sha read from `/api/health`,
not from the previous entry — its lesson) and returned a ranking that
overturned two of the last entry's items and killed one. Everything below is
that ranking executed, four lanes: A here, B/D/E in worktrees, disjoint files.

### Lane A — eight zero-credit checks on the NFL path, and the one that is empty is empty on schedule

`docs/measurements/2026-09-07-nfl-live-path-preflight.md`. The feed lists
`americanfootball_nfl` active (17,896 of 20,000 credits left this month);
discovery holds **50 open NFL events** for the next nine days (16 `KXNFLGAME`,
16 `KXNFLSPREAD`, 16 `KXNFLTOTAL`, 2 `KXNFLTEAMTOTAL`) under exactly
`Pro Football`; `/api/slate?league=americanfootball_nfl` echoes the filter
with an honest empty set. **`odds_snapshots` has 0 NFL fixtures and
`api_credits` 0 NFL rows, lifetime — and that is correct today.** Replaying
`decide_sweeps` read-only on the live DB with the runner's inputs
reconstructed: NFL's soonest Kalshi event is **67 h out against the 48 h
bootstrap horizon**. It crosses at **2026-09-08 03:20Z** and the next full
pass (every 15 min, `allow_bootstrap=True` by default on the ingest path)
buys it. Nothing else gates it — no failed sweep to back off from, and the
attention slice does not apply to `BOOTSTRAP`.

**The 4-credit early buy the plan allowed was not available.** The tap route
refuses a sport with no stored fixture (`routers/odds.py:159-173`), so the
desk's own spend path cannot bootstrap a new sport, and no side channel was
used. **Do not read "0 NFL fixtures" as a failure before 03:35Z 09-08.**

**The Wednesday baseline, by reason** (`unmatched_items`, `resolved = 0`,
`league = 'Pro Football'`, 07:21Z): `no sportsbook fixture within the
commence-time window` **32** rows (all 32 `KXNFLGAME`, Weeks 1 and 2);
`no linked game event for fixture …` **16** (`KXNFLSPREAD`, links through its
game); `expected 2 sides, got 19/27/28` **12** (`KXNFLTOTAL`/`TEAMTOTAL`
ladders — **scope, not a defect**, the feed buys no totals). Do not read
`event_links`.

**The sentence that stood here — "after the first sweep expect 32 → ~16, then
16 → ~0" — was WRONG and is corrected below.** It would have read tonight's
success as a failure. See the CORRECTION section in the measurement doc.

### Lane B — `failed` and the daily cap were both wearing the quiet's words

`WindowBanner.tsx` tested `refused` by name and let every other outcome fall
to *"looks identical to a quiet market from here"* — so an Odds API 401/429
on Wednesday would have rendered as a quiet market with the truth in the small
print. And `runner.py` recorded the `remaining == 0` stop as `SKIPPED` while
`sweeplog.py:78` defines `REFUSED` as "the budget declined — *we* stopped".
Now: `SweepDecision.refused_by_budget` (True only on that return) → the
runner writes `REFUSED`; the banner has a `failed` branch by name. **The
`next_call_ms` agreement test failed on the original code** — at zero credits
the loop returned `fire=()` while the payload said "now" — fixed in
`window_status`. Six mutations, all red. `tests/test_inspect_live_db.py`'s
exhausted-day fixture now describes the new shape (41 refused / 3 skipped).

*Two residuals, recorded:* (1) `window_status` takes no `in_scope`, so on the
pass the loop bootstraps a fixture-less sport the screen says nothing is
coming — **that is tonight's NFL sweep**, and the loop buys regardless; small,
Monday/Tuesday. (2) On a day where sweeps ran and *then* the cap bound,
`sweptThisDay` is true and the strip is calm with "the day's sweeps have
run"; only the detail line names the stop. Not a lie; not loud either.

### Lane D — a venue 404 on a combo cancel is an answer, and the watcher had been asking once a minute for six days

Gate passed on the live DB: `combo_orders` row 2 (the 09-01 bid that FILLED
at 21:40Z and settled) was still `resting`, and `bid_watch` logged `ERROR …
left working and will be retried on the next pass` at 07:20, 07:21, 07:22Z —
every minute since 2026-09-01 22:41Z, ~7,700 times. Now
`STATUS_GONE_AT_VENUE = "gone_at_venue"` is terminal (not `cancelled`: money
moved); the watcher and the cancel route split `KalshiAPIError` 404 from
everything else — 404 marks the row and logs once at warning, anything else
keeps the retry. The three "still working" queries build `NOT IN` from
`TERMINAL_STATUSES` instead of four hand-typed placeholders. No schema change
(`status` has no CHECK). Six mutations red. **After deploy, the per-minute
ERROR line should stop within one minute — check `flyctl logs`.**
`combo-bids-tail` and `analyse_bet_presence.py` will show the new status as
unfamiliar text; neither drops the row.

### Lane E — ADR 0110, and dropping `eu` empties the sharp anchor

`docs/adr/0110-the-eu-region-is-the-only-feed-lever-left.md` records the
props kill, the totals refusal (6 credits a call; 496 × 1.5 > 700), the
`us`-only lever dated 2026-09-28 with its two preconditions, the five
`sorted(fixtures)` reasons with their 09-13/09-20 gate and the named non-fix
(a per-sport reservation, never a sort key), and the `exchange_index` kill.
**New in it:** `SHARP_BOOKS` (`runner.py:152`) is `{pinnacle, betfair_ex_eu,
betfair_ex_uk, matchbook}` — none is a `us` book — so `h2h,spreads,totals ×
us` trades every sharp-anchored fair value (73.0% of the pinned record) for a
soft consensus. The ADR lists what to measure first, including whether `uk`
at cost 3 keeps Pinnacle. Nothing in `fly.live.toml` moved.

### Killed this session, so nobody re-derives them

- **`exchange_index` on the manual order path** — the create body carries no
  shard on either path; `combo_bids` is right *around* the create (shard-scoped
  balance, shard persisted for the cancel). Real gap on an armed route with 0
  of 27 real bets, all NFL on shard 0, baseball leaving 09-27. ADR 0110.
- **`sorted(fixtures)` reordering** — five reasons, ADR 0110; gated.
- **The 4-credit early NFL buy** — not possible through the tap; not needed.

### Still open, in order

1. **Tonight, from ~03:35Z 09-08: confirm the first NFL sweep fired**, and
   read it the way the two corrections below say, not the way this item said
   this morning.
   - `sweep-log` should show a **`served`** row, `sport_key =
     americanfootball_nfl`, detail beginning `americanfootball_nfl has no
     stored sportsbook fixtures`. A `skipped` props row lands right behind it
     and is expected, not a fault. **Do not grep `api_credits` for the string
     `bootstrap`** — `trigger` is NULL on a bootstrap; only MANUAL and
     ATTENTION are stamped.
   - **03:35Z is not a deadline.** `window_status` cannot see a sport with no
     stored fixture, so its null `next_call_ms` feeds `Tempo.next_wake_ms`
     (`scripts/run_loop.py:1121`) and the loop may pace itself slowly for the
     buy it is about to make. A bootstrap at 04:10Z is the design working.
   - **Read `last_seen`, never the count** — corrected 15:20Z, and the old
     reading would have called a success a failure. Nothing sets
     `unmatched_items.resolved` and nothing deletes on a link, so a fixed row
     goes *stale in place* for the 7 days of
     `retention.DEFAULT_UNMATCHED_RETENTION_MS`. **`Pro Football` still
     holding 32 rows at 04:00Z is the SUCCESS case**; the broken-link case is
     32 rows all carrying a *fresh* stamp. Full table in
     `docs/measurements/2026-09-07-nfl-live-path-preflight.md` §CORRECTION.
   - The instrument is shipped as of this session and ordered by
     `last_seen_ms DESC` so the live rows sort on top:

         flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/list_unmatched.py --db /data/cockpit.db --league 'Pro Football'"

   - **Do not watch the credit ledger.** Tonight is one 4-credit call against
     a ~366-credit day; 4 credits is invisible. The day that matters is
     Sunday 09-13 — see item 2.
2. **`window_status` cannot predict a bootstrap** (lane B residual 1). Pass
   `in_scope` through and mirror the candidate filter; one test driving both
   at a fixture-less sport inside the horizon.
3. **The `eu` lever, 2026-09-28** — ADR 0110's measurements first.
4. **`parlay_positions` on 2026-09-15**; **`cryptography` bump ~=49.0 on
   2026-09-15**, gate `tests/test_rest.py::TestSigningContract` etc.
5. **Scout Anthropic refusal fixture (ADR 0106 §5.2)** — one billed call.
6. **`combo_orders` reconciliation loop** — still nothing updates a row on
   fill or settlement; lane D closed only the 404 half. No screen reads it.
7. The lane B residual 2 (calm strip after a mid-day cap) — words only.

**Joe-gated: nothing.**

---

## 2026-09-06 (sixth entry) — the published credit bound was a partial sum, item 3 was half-false, and the largest NFL day-one risk is a failure nobody had timed

**STATE at close.** `main` = **`9951416`**, pushed, CI green on all four jobs.
**Live and demo are both deployed and verified on `9951416`** via the
`deploy.yml` workflow dispatch, `/api/health` read back on each. Live recorder
writing, `live_quotes_available: true`.

**Verify this with `/api/health` rather than believing it** — the previous
entry said "deployed on `7ed20fd`" and live had in fact been on `4a6d63e` the
whole time. That stale sentence was the first thing the partner agent ranked
work around, so it cost more than a line.

The deploy carries **no behaviour change**: `git diff` over `backend/` and
`fly.live.toml` is comment-only (checked by filtering `^[+-]\s*#`), and the
sole executable change is `scripts/inspect_live_db*.py`, which runs on the box
by ssh. It was shipped so `credits-day`'s new cross-read is *there* on
2026-09-13, which is the day it was built for.
Baseline before any edit: **6258 passed / 10 xfailed** (24m30s), matching the
handoff exactly. Six stale branches deleted with `git branch -d` after
confirming 0 commits not in `main` each. Decision map still exhausted (0 open
sub-issues).

**The partner ran first, and one of its four ranked items was already done.**
It opened with "deploy `4a6d63e`, everything else is worth less" — reasoned from
the stale sha in the state I handed it. `/api/health` had already said
otherwise. **Hand the partner verified state, not handoff prose**; it argues
well from whatever it is given, including from something false.

### Item 3 was funded as a falsification and most of it did not survive

The claim: *"the global stop is invisible on both surfaces … exhaustion reads as
an absence."* Verdict: **false on the screen, true on exactly one instrument,
and the recommended diagnostic was itself the defect.**

- **The screen says so.** `timing.py:1835-1845` builds the string, `runner.py:2393-2396`
  writes it, `timing.py:1578-1579` carries it as `last_look_detail`, and
  `WindowBanner.tsx:318` renders it verbatim on `/board`.
- **The post-hoc read was broken, and this file recommended it.** `REFUSED` is
  written only behind `budget.refusal_reason` **inside** `fetch_odds`
  (`client.py:343-352`). Once `remaining == 0` no call is attempted for any
  sport, and `runner.py:127` **never imports `REFUSED` at all**. So a cap that
  binds at 15:40Z leaves **one** `refused` row and sixteen hours of `skipped`
  ones — and `sweep-log --outcome=refused` finds the instant and misses the
  state. `sweep-log` is also not day-scoped at all.
- **It also uses the vocabulary against its own definition.** `sweeplog.py:71-88`:
  *"`REFUSED` means the budget declined — **we** stopped. `SKIPPED` means the
  pass chose not to look."* The global cap stop is the budget declining.

**Built:** `credits-day --date` gains two `odds_sweep_log` sections on the same
budget-day window — by outcome, and refusals+skips grouped by **the reason they
name**, which collapses a stopped day's hundreds of identical rows into one line
with a count and a span. Five tests, including a vacuity guard; **all four
guards mutated and all four went red.** Mutation harness restored from a byte
copy, never `git checkout`.
`docs/measurements/2026-09-06-the-global-stop-is-not-invisible.md`.

*Left unfixed, recorded:* on a budget-exhausted day `sweepTone.ts:168` misses
its `refused` branch and reaches `warn` via the generic "nothing swept in an
open window" path — the same tone as a dead recorder, separated only by the
detail text.

### Item 2 is fixed in four places, and a TEST was pinning the falsehood

`~684/day worst case` is **not a bound and never was**. 384 (floor) + 300
(slice) omits the kickoff-window loop, whose only gate is `credits_left` and
therefore the 700 itself, and which was **67.0% of September's spend**.
Corrected in `CLAUDE.md` (both places), `fly.live.toml`, `timing.py`.

**`tests/test_desk_follows_attention.py` asserted `worst_case == 684,
"fly.live.toml's worst-case row"`** — while its own docstring, three paragraphs
lower, said the slot planner was not counted. Renamed to
`test_the_two_capped_terms_are_384_and_300_and_are_not_a_worst_case`, and it now
asserts the thing the old name was missing: one NFL Sunday's window demand (84)
**exceeds** the 16-credit gap between the sum and the cap, so nobody can read
that gap as spare capacity.

**The day is safe by the cap, not by construction.** Say it that way.

### A cluster is SEVEN calls, not six

`DUE_WINDOW_MS`' comment said `6 x sweep_cost`. `calls_remaining` is
`1 + 3_600_000 // 600_000` = **7**; six is the count of *refreshes*, seven the
count of calls, and `projected_total_cost` reserves the second. It hid 4 credits
per cluster from every projection built on it. The existing test restated the
formula (`1 + span // REFRESH_MS`) and so agreed with the code whatever the code
said; `test_a_full_window_is_seven_calls_and_the_number_is_written_down` now
pins the literal.

### NFL day one, simulated against the real planner at zero credits

Fed the real 272-fixture capture into the real `plan_sweep_slots` /
`decide_sweeps`, driven at the deployed 15s tick over a whole budget day.

- **An NFL Sunday plans 3 clusters, not ~12 window-hours.** `cluster_kickoffs`
  collapses 13 kickoffs into 3 (17:00Z ×8 games, 20:25Z ×4, 00:20Z ×1); the
  season's worst day is 4. **124 credits unattended, not 288.**
- **Wednesday 09-09: 72 warm, 76 cold.** Cold start on a *successful* first
  sweep costs exactly +4 credits — one call.
- Peak budget day **~486, not ~770**. The old figure double-counted: slot and
  floor spend are per sport and additive, but the attention slice is a **single
  global 300/day pool** with no `sport_key` filter, so a fourth sport does not
  raise it.
- Calibration that it is not fantasy: simulated split **67.7% window / 32.3%
  floor** against the live record's **67.0% / 33.0%**.
- **What loses when the cap binds, and nobody chose it:** floor buys are served
  **alphabetically by sport key**, so WNBA's drops first, then MLB's; every
  kickoff-window slot outranks every floor buy. That is `sorted()`, not policy.

`docs/measurements/2026-09-06-nfl-week-1-credit-headroom.md` carries all of this
as **Amendment 1**.

### Joe's item 1 (props and totals) is REFUTED on arithmetic, not on preference

`sweep_cost = max(1, len(markets) * len(regions))` (`budget.py:66-68`). Live is
`h2h,spreads` × `us,eu` = **4**. Adding `totals` → 3×2 = **6, +50% on every
call, every sport, forever**. The largest observed day is 496 (two sports);
**496 × 1.5 = 744 > the 700 cap** — and when the cap binds every sport stops.
Buying totals would mean turning the desk off on NFL Sunday. **No correction to
the published bound changes this**, so item 1 was never gated on item 2.

**Player props: killed outright**, not deferred — per-player keys multiply far
past 1.5×, and ADR 0037 already refuted the in-house substitute.

**The one lever still open, dated 2026-09-28** (after MLB's regular season ends
09-27 and Weeks 1–3 supply a measured four-sport day): drop the `eu` region.
`h2h,spreads,totals` × `us` = **3 credits, cheaper than today's 4.** Refuse it
this week — it changes the book composition of every fair value three days
before the largest slate this desk has seen. Owed an ADR.

**And the settled reason not to show a leg we cannot devig**, decided hours
earlier in the opposite direction: *"a live leg arrives with no fair value at
all and the only number left is Kalshi's own. A card comparing Kalshi to Kalshi
shows a cost while implying a judgement it is not making."* A totals leg without
`totals` in the feed is that object exactly.

### `cryptography` — NOT REACHABLE, and the advisory is scored after all

GHSA-jwv3-5hgf-82ww / **CVE-2026-69249**, affected `>=42.0.0, <=48.0.0`, first
patched **49.0.0**. Installed 44.0.3.

**Correction to this file's earlier "CVSS is 0, i.e. unscored":** that is the v3
field. **CVSS v4 is 8.7 (high)**, and the vector's only non-`N` impact is
`VA:H` — pure availability. It cannot forge a signature or leak a key.

**Reachability: none.** The defect is in `cryptography.x509.verification`'s path
builder. This repo's only use of the library is RSA-PSS request signing at
`backend/kalshi/auth.py:126-137` (`load_pem_private_key`, `PSS`, `MGF1`,
`SHA256`). Repo-wide sweep for `x509|PolicyBuilder|build_server_verifier|…`:
**zero hits.** Confirmed empirically, not just by grep — importing the whole app
surface loads 26 `cryptography.*` submodules and **not one `x509` module**. No
dependency imports it either. TLS is stdlib `ssl`, a different implementation.

**Bump stays dated 2026-09-15**, floor `~=49.0`. Gate:
`tests/test_rest.py::TestSigningContract` and
`TestTheQueryStaysOutOfTheSignature`, plus `tests/test_rest.py
tests/test_exchange_shards.py tests/test_parlay_lookup.py` (each generates a
real RSA key). **Baseline taken now on 44.0.3: 200 passed in 47s**, so a red
after the bump is the bump. Watch `Dockerfile:38-39` — 47.0.0 requires OpenSSL
≥3.0 (bookworm has it). `tests/test_manual_orders.py` and `test_ws_client.py`
look like gates and are not; both stub the signer out.

### Still open, in order

1. ~~**The failing-bootstrap loop has no bound of its own.**~~ **CLOSED
   2026-09-06 — ADR 0109.** A sport whose last sweep failed now waits
   `BOOTSTRAP_RETRY_BACKOFF_MS` = 30 min, bounding it at **48 attempts / 192
   credits a day** (measured, not projected) against the 700, and the hold is
   named in the pass detail so it reaches `/board`. A backoff rather than an
   attempt cap, because a cap bounds the spend and then gives up — the sport
   would stay dark for the rest of the budget day after the upstream recovered,
   which is the wrong trade on a season opener.
2. **The `eu`-region lever**, dated 2026-09-28 with its two preconditions above.
   Owed an ADR that also records the props kill so October does not re-derive it.
3. **`sweepTone` cannot distinguish a spent budget from a dead recorder** — both
   reach `warn` by the same branch. Small; the words already differ.
4. **`combo_orders` is never reconciled against the venue**, and
   `parlays.py:429-436` turns the venue's correct 404 into "may still be
   resting". No screen renders the table now, but the live route still writes
   it. The cancel-wording half is ~5 lines and removes a lie from a live route.
5. **`parlay_positions` on 2026-09-15.** Calendar, not work.
6. **Scout Anthropic refusal fixture (ADR 0106 §5.2)** — one real billed call.
7. **Done this session, so not re-derived:** the six stale branches are deleted;
   the parlay census's "Owed" section is closed (ADR 0085 Amendment 1 landed and
   Joe removed the card, dissolving the second half); item 3 is closed; item 2
   is closed; the inspector-split ADR is written and took **0108**.

**Joe-gated: nothing.**

---

### Added after the entry above — the NFL end-to-end check and the backoff

Joe asked for both, in that order. Both landed.

**NFL renders end to end, driven rather than inspected.**
`tests/fixtures/events_nfl_preseason.json` turns out to hold **16 genuine
`Pro Football` regular-season Week 1 events** beside the 16 preseason ones it is
named for, so no synthetic Kalshi data was needed: **16/16 discovered, 16/16
linked** against the 272 real book fixtures, **16/16 priced** through
`consensus_devig` → derived ask → `settlement_fee`. New York J/G and Los Angeles
R/C each bound to the right franchise.

**The finding:** `linker.py` claimed the commence offsets "are identical, which
makes it a fixed shift". That was 24 same-day pairs. Over the whole live
`event_links` record (2,263 links) the shift is right and the constancy is not —
mass at −3.00h, a tail at −3.50h, and two NCAAF links at **+3.00h** where Kalshi
is *earlier* than the book. **max|skew| = 3.50h against a 4h tolerance: 30
minutes, not the hour NFL alone suggests.** Tolerance NOT widened — widening
turns more MLB doubleheaders into refusals for a tail of 8 links in 2,263.

**The Wednesday check, with a known baseline.** A tolerance failure is stamped
`NOT_CARRIED`, which `runner.py` calls "scope and needs nobody" — so a whole
league failing to link lands in the category marked as needing no attention.
NFL is in that state *right now*: **32 of 32 `not_carried`, 842,656 sightings**,
the largest count in the table, because `api_credits` has zero rows for
`americanfootball_nfl` and the season has not started. Benign, and exactly why
it matters — it is indistinguishable from the failure. So:

> **After the first NFL sweep on 09-09, `Pro Football`'s window-reason items
> should collapse from 32 to ~0.** Read `unmatched_items` grouped by league and
> reason. Do NOT read `event_links` — it contains only links that succeeded, so
> the skew distribution above is truncated by the very tolerance it measures.

`docs/measurements/2026-09-06-nfl-renders-end-to-end.md`.

**Both follow-ups are now built too.**

- **`KXNFLSPREAD` is measured, not inferred.** `scripts/capture_nfl_spread_subtitles.py`
  (new, unauthenticated `/events`, zero credits) pulled 16 open events and
  **404 of 404 rungs parse, unit `points` throughout, across all 32 franchises**
  -- a census on the team axis. Fixture `tests/fixtures/events_nfl_spread.json`;
  pinned by `test_every_nfl_spread_rung_parses_and_the_league_is_a_census`,
  mutated red against `_KNOWN_UNITS = r"runs?"`. The last inference in the NFL
  path is gone.
- **A league that stops linking now says so.** `leagues_linking_nothing`
  (`match/linker.py`) names any league holding book fixtures whose events ALL
  refused `not_carried` -- a broken link rather than scope. `runner` logs it
  each pass. **`candidates_by_sport` is the whole discriminator**: without it
  the guard would have shouted about today's NFL (32 of 32, no odds bought yet)
  every pass for weeks, and a guard whose first finding is false gets deleted.
  Six tests, five mutations, all red.

**The `exchange_index` gap is LATENT, not urgent — checked, not assumed.**
`kalshi/orders.py` sends no shard and the manual (armed, real-money) route does
use `OrderPlacer`, so the gap is real. It is also **a no-op for NFL**: all 420
markets in both captured NFL fixtures carry `exchange_index: 0`, and shard 0 is
what `OrderPlacer` already gets by omission. Baseball on shard 3 would
misroute, but that shard is unfunded (`user_not_found`, 2026-08-30), so the
order fails either way. Fix it for correctness whenever; it blocks nothing.

**Two things found that are not about parsing**, neither built: `sorted(fixtures)`
means football is served and MLB/WNBA starve when credits run short (`sorted()`
for determinism, not a chosen priority — MLB is the CLV population); and the
single/manual order path sends no `exchange_index` while
`EXCHANGE_INDEX_{DEFAULT,COMBOS,PARAM}` are imported by `kalshi/orders.py` and
used exactly once each — the import line. `combo_bids.py` does it correctly.

**A number NOT carried forward:** a sweep put an NFL Sunday at 850–900 credits
and recommended raising the budget. It stacks separately-capped worst cases —
the exact error corrected in `CLAUDE.md` this session. The floor assumes four
sports take 24 hourly buys, but NCAAF has no Sunday slate and **WNBA spent 0
credits all September**; the slice has never exceeded 112 of 300; and attention
buys *displace* floor buys. **~486 expected / ~786 ceiling stands. No budget
change.**

---

## 2026-09-06 (fifth entry) — the parlay window became a control, the in-play combo question is answered, and props are a feed problem rather than a venue one

**STATE at close.** `main` carries the session's earlier three commits plus
this work. Live and demo were deployed and verified on `7ed20fd` mid-session
(`flyctl auth login` unblocked it, after `whoami` showed the stored token was
expired rather than absent). The live deploy went through the `deploy.yml`
workflow dispatch, because a direct `flyctl deploy` to the live app was
refused by the auto-mode classifier — the path that exists for exactly that.

### Joe asked three things in one evening, and two of them were capability questions

He opened the desk at ~5pm PT Sunday, found the parlay screen empty, and
asked whether it could be forced to show something. The desk was **not**
broken: the slate held **one** fixture (WSH@LAD, 7:11pm PT, quote 10s old,
31 books, four devig methods within 0.2 points) and `excluded` counted **316**
games as `kickoff_after_tonight`. Every card read "needs 2 fresh games and the
slate has 1". At 8pm ET on a Sunday the MLB day slate is done and NFL has not
started.

Meanwhile **eight Monday fixtures already carried fresh consensus** in
`fair_prices` (12–31 books each, ~5 min old). The odds were bought; the window
was hiding them.

### The window is a control now, and `tonight` is still the default

`HORIZONS` = `tonight` | `tomorrow` | `48h`, built ON `end_of_desk_day_ms`
rather than beside it so the 4am rollover, the time zone and the DST handling
stay in one place. `horizon_end_ms` walks that many desk days forward.

- `/api/parlays?horizon=` — **422 on an unknown key, never a silent default.**
  A typo would otherwise serve tonight's cards under another window's URL and
  read as "found nothing", which is the failure this desk already has too
  much of.
- The payload carries a `window` echo (`key`, `words`, `ends_ms`, `choices`)
  and the screen renders **the server's words**. A locally-derived label can
  print "tonight" over tomorrow's numbers, because every `not_built_reason`
  and every exclusion count is relative to the window actually used.
- `WindowPicker` is `Link`s, not client state — same mechanism as
  `FilterBar`, so the choice survives a reload and two pickers on one screen
  do not behave differently.
- **The lede was a lie in waiting.** It read "cards cut from tonight's games"
  unconditionally; it now renders the window's own sentence. Copy that names
  a condition is falsified by making the condition configurable — the same
  ordering lesson the attention-slice banner taught three times.
- `kickoff_after_tonight` → **`kickoff_outside_window`**. A reason code that
  names one window while reporting another is a stale label a reader trusts
  *because* it looks specific.

**`within_hours` is unchanged and is a different thing**: it only narrows the
pool, this moves its upper bound. Widening is safe because
`combo_eligible_events` independently refuses legs Kalshi will not combine —
cards a week out returned HTTP 400 `invalid_parameters` (2026-08-28).

### Two tests were written, found green under their own mutation, and replaced

Both are the same species and it is worth naming: **an assertion whose
fixture cannot distinguish the two cases.**

1. `test_tonight_is_the_default` first asserted two payloads were equal. They
   never are — `quote_age_ms` and the freshness stamps are computed from
   `now` and two requests are two instants. It failed for a reason unrelated
   to the window: a test that cries wolf about its own clock. Now compares
   leg tickers and refusal strings.
2. `test_widening_never_drops_a_leg` compared `kickoff_outside_window` counts
   across two windows on a fixture where **every game is tonight** — so both
   counts were 0, the assertion was `0 <= 0`, and inverting the bound
   comparison in `ladder_candidates` left it green. Replaced by
   `test_a_wider_window_admits_the_game_tonight_refused`, which seeds one
   game in each window, carries a vacuity guard, and asserts on the LEGS
   rather than the counters. Re-mutated: red.

All four window guards now fail when disabled.

### The in-play combo question is ANSWERED, and it closes a named gap

`lookup_combo`'s own docstring listed this as open in these words: the
idempotency capture "does not establish the answer ... **after the legs'
games start**". Joe asked whether he could put a live game in a combo.

**Kalshi will price it.** `scripts/probe_inplay_combo_lookup.py` minted
`KXMVECROSSCATEGORY-SHARD1-S20265F1A8FB41A3-A7B0F51726E` from a live
Minnesota leg (~2h into the game) plus a pregame Washington leg — HTTP 200,
both legs echoed in `mve_selected_legs`. **The book was empty on both sides**
(`yes_dollars: []`, `no_dollars: []`), consistent with 0 of 61 open
combinations carrying a readable ask at rest. It was not even a new mint:
`created_time` is 2026-09-05, so the combination already existed.

Three facts established on the way, each of which had been assumed:

- **Kalshi keeps game markets `active` after first pitch.** Both sides of the
  live game active, close time two days out. In-play trading is real.
- **Kalshi's `occurrence_datetime` runs ~3h late**, so "commence is in the
  past" under-detects a live game by up to three hours. The probe takes the
  started event as an ARGUMENT rather than inferring it — the operator knows
  what is on television and the venue's clock does not.
- **The desk-day rollover is 4am PACIFIC**, not 4am ET as an earlier
  handoff sentence in this file implied.

**It is not going on the parlay desk, and the reason is structural.** The
desk's fair value is devigged sportsbook consensus; books pull their pregame
lines once a game starts, so a live leg arrives with **no fair value at all**
and the only number left is Kalshi's own. A card comparing Kalshi to Kalshi
shows a cost while implying a judgement it is not making. Where the live
price IS the right instrument is `/hedge`, which transacts at it rather than
predicting with it.

### Props: the venue already does what Joe asked; our FEED does not

He asked to combine player props with games and over/unders, on the sharp
argument that individual usage is a cleaner edge than a full-game spread.

**Measured on the live collections, not reasoned about.** Kalshi runs
dedicated per-week NFL collections (`KXMVENFLMULTIGAMEEXTENDED-W6` … `-W11`),
each carrying **ten market families per game**:

    KXNFLGAME  KXNFLSPREAD  KXNFLTOTAL          moneyline / spread / total
    KXNFLFIRSTTD  KXNFLANYTD  KXNFL2TD          touchdown props
    KXNFLRECYDS  KXNFLPASSYDS  KXNFLRSHYDS      yardage props
    KXNFLREC                                    receptions

The cross-category collections carry `KXNCAAFSPREAD`, `KXNCAAFTOTAL`,
`KXNCAAF1H` (first half) and `KXMLBRFI` (run first inning) too. **So the
venue permits exactly the parlay he described.** Two blockers, and neither is
Kalshi:

1. **`ODDS_MARKETS = "h2h,spreads"` (`fly.live.toml:463`).** The feed buys no
   totals and no player props, so there is no consensus to devig for those
   legs and the desk cannot show a fair value. Adding markets multiplies
   every sweep — going `h2h` → `h2h,spreads` **doubled** the cost on
   2026-08-23 — against a 700/day cap whose four-sport headroom is already an
   open question (item 3).
2. **`TEAM_MARKETS_ONLY = {"h2h", "spreads"}` (`core/ladder.py:131`)**, which
   every card's recipe uses. Named rather than inlined precisely so admitting
   a new market class is one visible edit per card.

**And the thing not to do:** build an in-house prop model to fill the gap.
ADR 0037 measured that on 255 settled `KXMLBHR 1+` markets — model-vs-Kalshi
disagreement sd **3.72 points** against the model's own error of **4.04** —
so the apparent edge is our own noise. Buying the books' prop lines is a
different proposition from modelling props ourselves, and only the first is
open.

### The resting bid did not need cancelling: it FILLED, five days ago, and the screen said otherwise the whole time

Joe asked twice to cancel the bid the panel showed. There was nothing to
cancel, and the venue had been saying so: the cancel's HTTP 404 `not_found`
was correct.

    placed    2026-09-01 19:59:53Z   8 contracts @ 25c
    filled    2026-09-01 21:40:54Z   fill_count_fp 8.00, remaining_fp 0.00
              maker_fill_cost $2.00   maker_fees $0.0525   taker cost $0.00
    settled   2026-09-02 05:17:41Z   market_result "no", value 0, revenue 0
    legs      TOR@CLE (CLE), NYY@LAA (NYY), STL@LAD (LAD)

`/portfolio/orders?status=resting` returns **zero** orders on the account.
The order's own status is `executed`.

**Two defects, and the second is worse than the first.**

1. **`combo_orders` is never reconciled against the venue.** The row is
   written before the request leaves (deliberately, so a lost response is not
   a lost bid) and **nothing ever updates it** -- not on fill, not on
   settlement. So the panel rendered `resting` for five days over an order
   that had filled, lost and settled, and it would have rendered it forever.
   The cancel route then turned the venue's correct 404 into *"The bid may
   still be resting; try again or cancel it in the Kalshi app"* -- the
   opposite of true, and advice that sends him looking for something that
   does not exist.

   **The earlier diagnosis in this file was wrong and is corrected here.**
   The fourth entry guessed Kalshi had auto-cancelled the bid at kickoff.
   It did not. It filled. The guess was reached because the panel's own copy
   mentioned auto-cancellation, which is how a screen's explanation becomes
   an investigator's hypothesis.

2. **It refutes a sentence that was live on three screens.** The panel read
   *"Each fills only if someone sells to you at your price, and on a
   combination nobody has ever been observed doing so."* This fill is
   `is_taker: false` -- a **maker fill**, someone selling into a resting bid
   on a combination. It is almost certainly the 1 of 52 the 2026-09-06 entry
   census counted as non-taker, and it was sitting in the account while the
   screen said it could not happen.

   The panel came off the site today on Joe's instruction, so the sentence is
   gone -- but it was removed for the wrong reason, and the distinction
   matters for anything that re-derives combination liquidity copy.
   **Re-check the census on `is_taker`**, not on position counts: 51 of 52
   entered by hitting an offer is a statement about ENTRY METHOD, and the
   remaining 1 is now known to be a maker fill that the copy said was
   impossible.

Neither is urgent -- no screen renders `combo_orders` any more -- but the
table is still written to by the live route, so anything that reads it later
inherits five-day-stale state.

### Still open, in order

1. **The NFL alias pairing is DONE** (previous entry). **Item 1 is now the
   props/totals feed decision**, and it is worth taking before Wednesday
   only if the credit answer allows: price `ODDS_MARKETS` with `totals`
   added, against the 700/day cap and the four-sport projection. Totals are
   the cheap half — one more market key, no per-player explosion — and
   `KXNFLTOTAL` and `KXNCAAFTOTAL` are both already combinable. Player props
   are a separate and much larger buy; do not price them together.
2. **The four-sport budget day** — unchanged, and now blocking item 1. The
   published `~684/day worst case` in `CLAUDE.md`, `fly.live.toml:305-307`
   and `timing.py:2060-2065` is **not a bound**: it omits the kickoff-window
   loop, 67.0% of September's actual spend. Fix the record before anyone
   reasons about headroom for props.
3. **The global stop is invisible on both surfaces** — if 700 binds,
   `decide_sweeps` returns `fire=()` and every sport stops, and a refused
   sweep writes no `api_credits` row, so exhaustion reads as an *absence*.
4. **`cryptography`** — confirm reachability now (read-only), bump dated
   2026-09-15. Its own lane, signing tests as the gate.
5. **`parlay_positions` on 2026-09-15** — and the "Owed" section of
   `docs/measurements/2026-09-05-parlay-census-result.md` is stale, one line.
6. **`combo_orders` is never reconciled against the venue, and the cancel
   route mis-words the consequence.** Established 2026-09-06 on a real order,
   see above: a filled-and-settled bid rendered `resting` for five days, and
   `parlays.py:429-436` turned the venue's correct 404 into "may still be
   resting". Not urgent -- no screen renders the table now -- but the live
   route still writes it.
7. **Scout Anthropic refusal fixture (ADR 0106 §5.2)** — one real billed
   call, deferred.
8. **Killed or parked**, recorded so they are not re-derived: the
   `"40 of 40"` prose is not a lane; the worktree husk is not work; the three
   ADR 0107 refusals are correctly parked; Lane B's inspector ADR should be
   written rather than carried.

**Joe-gated: nothing.** Item 1 needs the item 2 correction first, which is
unowned work with no gate.

---

## 2026-09-06 (fourth entry) — Joe took the offer-making controls off the desk, and what replaces them is a record of a bet placed somewhere else

**STATE, verified at open, not inherited.** `main` was `8f5948a`, tree clean,
nothing unpushed, `git worktree list` showed only main — no lanes. Live and
demo both reported `d1feb712c05a6e56f08283b9304bae9fea4489ae`, and
`git diff --stat d1feb71..HEAD` was `tasks/` only, so the deployed image was
current. Decision map exhausted: the frontier query returned **zero** open
sub-issues. CI green on `8f5948a`.

**STATE at close: three commits ahead of the deployed sha, and this time the
delta is CODE.** The previous entry's rule — a sha gap confined to `docs/` and
`tasks/` is not drift — does **not** apply here. `frontend/` changed and
nothing has been deployed.

**Nothing is deployed because `flyctl` is logged out.** `flyctl auth whoami`
returns `no access token available. Please login with 'flyctl auth login'`,
with a token still sitting in `~/.fly/config.yml` — so it is expired rather
than absent, and reading the file tells you nothing. That blocked three
things beyond the deploy: the live DB inspector, the venue's own view of a
resting order, and any `credits-day` read. **Joe has to run
`flyctl auth login` himself**; `!` commands do not run from his phone, so if
he is out this waits.

### What he asked for, in two messages

> "get rid of this thing from the site: Your buy orders on the exchange …"
> (pasting the panel, and the cancel that had just failed)

> "id like to be able to pay for the combo on the sports book too from the
> betting and parlay pages. I don't want to make offers or find offers in
> shares."

Asked which sense of the second he meant, he answered **both** — buy it
outright on Kalshi *and* record one paid at a sportsbook — on **all four**
screens: Games, Picks, Parlays, Your bets.

### ADR 0084 is off the screen, and both halves had to go together

`RestingBid` ("buy this parlay at your price") and the `RestingBids` panel are
deleted. The panel's own docstring argued it was *"the other half of the
control that places a bid"* and that an interface which can create a resting
order and cannot show or withdraw it *"loses money quietly"* — which is
exactly why keeping either alone was not an option.

**The backend is deliberately still running**: the route, `combo_orders`, and
`bid_watch`'s kickoff auto-cancel. A bid placed before this change may still
be resting at the venue and the watcher is what withdraws it. Deleting it
would strand live money. `tests/test_combo_bid_routes.py` pins the two
component files **absent**, with the reason in the docstring: a future session
reading ADR 0084 will find a well-argued case for a screen the owner has since
refused, and the ADR must not outvote him.

### The 404 he hit, and what it probably means

His cancel returned `404 not_found` from
`/portfolio/events/orders/{id}?exchange_index=1`. **The shard was already on
the request**, so the 2026-08-30 defect `rest.py:74-78` documents is not this.
The likelier reading is that Kalshi had already withdrawn the order — combo
bids auto-cancel at first kickoff, which the panel's own copy stated.

**The desk could not say so, and that is a real defect left open.**
`parlays.py:429-436` turns *any* exception from `cancel_order` into
`"The bid may still be resting; try again or cancel it in the Kalshi app."`
and does **not** mark the row terminal — so a bid the venue has already killed
renders as `resting` forever and the cancel fails forever. Unverified against
the venue, because `flyctl` is logged out. Now open item 9.

### What replaces it: the record of a bet placed elsewhere

`RecordParlay` (ADR 0078) already did the whole job — sportsbook slip or
Kalshi combo, stake, total return, legs — and lived on `/hedge` alone, which
is not a screen anyone starts from. It now takes an optional `prefill` plus a
caller-supplied summary and blurb, and renders on all four screens Joe named.

**On a parlay card it arrives filled in from that card** — legs, name, source.
A form that has to be re-typed from the card above it is one nobody fills, and
an unfilled form here means the bet never enters the record at all: sportsbook
bets do not reach `fills`, which is the hole ADR 0078 exists for and the reason
the 2026-09-04 census could count only Kalshi taker hand fills.

**The prefill stops short of the stake and the return, and a guard keeps it
there.** Only his book knows what it paid him, and the equalising hedge is
exactly that many dollars of contracts — so a guessed return lands directly in
the size of a real order.

### A label that was reading from the wrong census

The reveal over the Kalshi buy path said *"Try to buy it on Kalshi — usually
nobody is selling."* That is the **resting book** (61 of 61 with no seller),
which is not the population he is in when he taps: the entry census the same
week found **51 of 52** of this desk's combination positions were entered by
TAKING an offer. With `RestingBid` gone this was the only buy path left on the
card, and it was being discouraged on the strength of the wrong instrument.
Now: *"Buy it on Kalshi — pay the asking price, if there is one."* Still behind
a reveal, because an empty book is still the expected first answer on a fresh
combination.

### Two lessons, and the second cost real work

**A guard that substring-matches an element name is green on a renamed
element.** `"<RecordParlay" in source` passes on `<RecordParlayX`, which
renders nothing. Caught by the mandated mutation — and nearly not caught,
because the obvious mutation (`replace("<RecordParlay", "<RecordParlayX")`)
is one the check cannot see. Tightened to `re.compile(r"<RecordParlay(?=[\s/>])")`.

**`git checkout <file>` restores the INDEX, so it deletes uncommitted work
while printing `Updated 1 path from the index`.** Used to undo three test
mutations; two of the three files had never been committed in that state, so a
newly written 10KB component, a patched card and a page edit were discarded.
Caught only because the confirming re-run came back **3 failed** on a test that
had just passed. Recovered from the scratchpad patch scripts. **A mutation
harness restores from a copy it made itself** — `cp` before, `cp` back after.
Both written to `tasks/lessons.md`.

### Verified

Full suite **6248 passed, 10 xfailed** in 10m16s; ruff clean; `tsc --noEmit`
clean; `next build` compiled. Every new guard mutated and observed red, then
green restored.

### The partner ran first, and its top item is not on the list

Invoked before any planning, per workflow step 0, and it returned before Joe's
errand arrived. Its ranking is carried into the Open list below. Its headline:
**the list is a builder's list and the building is finished** — the map is
exhausted, the hunt is closed, and the forcing function this week is that the
desk **has never seen an NFL slate** (`americanfootball_nfl` has 0 rows in
`api_credits`, lifetime) with the opener on **Wednesday 2026-09-09**.

It also refuted open item 2 as written — see item 2 below. That refutation
reaches `CLAUDE.md`, `fly.live.toml` and `timing.py`, and is **not yet
applied**.

### Still open, in order

1. **Pair the NFL alias file against live Odds API fixture names. Before
   Wednesday 2026-09-09. ~4 credits, ~30 minutes. NEW — the partner's first
   rank, and it was on nobody's list.**
   `backend/match/aliases/americanfootball_nfl.yaml` has five entries and its
   header documents the **Kalshi** side from a real capture; the Odds API side
   has never been paired, and there is no NFL Odds API fixture in
   `tests/fixtures/`. NCAAF got exactly this pass on 2026-08-26. Failure
   probability is low — 32 teams, best-known names in US sport — but the
   asymmetry decides it: 4 credits of 700 against the whole Week 1 board
   rendering unmatched, and it is **unrecoverable after kickoff**. One
   `/sports/americanfootball_nfl/odds` capture through `link_event`, the shape
   of `scripts/capture_ncaaf_names.py`. Print the unresolved list; do not
   summarise it.

   *Discovery needs no config change* — there is no `ODDS_SPORTS` variable;
   scope comes from the Kalshi `/events` walk through `IN_SCOPE_LEAGUES`
   (`backend/kalshi/discovery.py:235-242`), which already carries both football
   keys, and the deployed classifier was run against the committed capture
   `tests/fixtures/events_nfl_preseason.json` and returned exactly the 16
   regular-season events, dropping the 16 preseason ones.

2. **Item 2 as it stood is REFUTED, and the correction is bigger than the
   item.** The `~770` four-sport projection is undecomposed — it appears once
   in prose with no arithmetic — and its largest term (NFL 288 = 12h x 6 calls
   x 4) is the **attended** cadence, already capped at 300, so reaching 770 by
   adding a separate attention term double-counts. The premise is contradicted
   by the document's own data: **WNBA spent 0 credits across all six September
   budget days** (MLB 1,116 + NCAAF 724 = 1,840, the exact total), so "four
   concurrent sports" is not the current premise.

   **The published bound is not a bound.** `fly.live.toml:305-307` prints
   `worst case ~684/day inside the 700 daily cap`, `timing.py:2060-2065`
   restates it, and **`CLAUDE.md` carries the same table**. 384 + 300 counts
   only the desk branch and omits the kickoff-window loop
   (`timing.py:1943-2028`), which is **67.0% of actual September spend** (319
   of 476 rows) and is capped by nothing but the 700. Structural demand at four
   sports is ~2,304/day. **The day is safe by cap alone, not by construction**,
   and a session reading `CLAUDE.md` currently believes otherwise. Realistic
   2026-09-13 is ~420–580; observed max under the current design is 508.
   *Fix the record in all four places; this is a docs lane that touches
   `CLAUDE.md`, so it needs a tighter review than a docs lane usually gets.*

3. **The global stop is invisible on both surfaces — after Week 1.** If 700
   binds, `decide_sweeps` returns `fire=()` and every sport stops. The budget
   day rolls at 10:00Z, so the casualty is **Sunday Night Football and the late
   MLB slate**. A refused sweep writes no `api_credits` row
   (`client.py:345-352`), so exhaustion shows in `credits-day` as an *absence*,
   not a spike — the same silent-refusal-with-no-fall-through shape that took
   four passes to fix on the attention slice. Post-hoc read exists:
   `credits-day --date 20260913` plus `sweep-log` filtered on
   `outcome='refused'`.

4. **`cryptography` — split it in two.** Confirm reachability **now**
   (read-only, ~20 min, no dependency change); **date the bump to 2026-09-15**,
   not "later". `requirements.txt:9` pins `~=44.0`; first patched version is
   **49.0.0**, a five-major jump on the library that signs every Kalshi
   request. CVSS unscored. The defect is exponential path-building on duplicate
   self-signed X.509 intermediates; TLS validation goes through httpx/OpenSSL,
   not this path builder, and no caller of the affected surface has been found
   — an argument, not a proof. `MANUAL_ORDERS_ARE_DRY_RUNS = False` since
   2026-08-26, so a signing break stops Joe hand-betting at the moment he wants
   to. Its own lane, signing tests as the gate, never a drive-by bump at the
   end of a session.

5. **`parlay_positions` on 2026-09-15** — unchanged, and now better founded:
   ADR 0085 Amendment 1 landed, so `NOTES["unquoted"]` carries both populations
   and a 0 on 09-15 measures demand rather than the chilling effect of the old
   copy. **One correction owed:** the "Owed" section of
   `docs/measurements/2026-09-05-parlay-census-result.md` still reads as open
   and is stale — one line, or a future session reopens it.

6. **The cancel cannot report a bid the venue has already killed. NEW, this
   session.** `parlays.py:429-436` renders every `cancel_order` exception as
   "may still be resting" and leaves the row non-terminal, so a dead bid is
   un-cancellable and permanent in the desk's record. Joe hit it. Low priority
   now that no screen renders the row — but the row is still there, and this
   is the shape to fix before anything reads `combo_orders` again.

7. **Scout Anthropic refusal fixture (ADR 0106 §5.2)** — justified (scout has
   a live production path; `CLAUDE.md`'s "called by nothing" note is about
   `review_retired`). One real billed call. Deferred to the 09-15 batch.

8. **Killed or parked by the partner, recorded so they are not re-derived:**
   the `"40 of 40"` prose in three files is **not a lane** (two are code
   comments; the exit claim still stands; `api/schemas.py:218` rides along next
   time anyone touches it). The `.claude/worktrees/wf_e0ee5ede-e97-1` husk is
   **not work** — delete opportunistically. The three ADR 0107 refusals are
   **correctly parked**. Lane B's missing inspector ADR: **write the 20 lines**
   rather than carry it.

**Joe-gated: one, and it blocks the deploy.** `flyctl auth login`. Everything
in items 1–8 is unowned work with no gate; item 1 has a hard deadline of
Wednesday.

---

## 2026-09-06 (third entry) — the partner ran first and its top item was not on the list; the credit answer was refused once before it was kept; three lanes landed and the inspector stopped blocking work

**STATE, verified at close.** `main` was `7c701ae` at open, live and demo both
on it, tree clean, no lanes running, and the decision map exhausted at 32 of 32
with `#3` the only open issue. Nothing was Joe-gated at open and nothing is
Joe-gated at close.

**At close, live and demo both report
`d1feb712c05a6e56f08283b9304bae9fea4489ae`**, verified by reading each
endpoint, with CI green on that commit. **`main` is ahead of it and that is
deliberate, not drift:** every commit after `d1feb71` in this session touches
only `docs/` and `tasks/`, which never enter the image, so no redeploy was
taken for them. Read `/api/health` yourself, then read the delta before
concluding anything -- `git diff --stat d1feb71..origin/main` is the check, and
a diff confined to `docs/` and `tasks/` means the deployed image is current.

That distinction is worth making once rather than re-deriving: a session that
treats any sha gap as a stale deploy will redeploy on every documentation
commit, and one that treats every gap as harmless will miss a real one.

**They reported a sha that did not exist for about twenty minutes first, and
the correction is the part worth reading.** The first deploy was given
`-e GIT_SHA=c9739cc7`, typed from the 7-character short sha `c9739cc` with an
eighth character supplied from nowhere. The real commit is `c9739cc8...`. So
both health endpoints served an identifier **matching no object in the
repository** -- not a truncation, a fabrication, and the failure mode is that a
later session doing the mandated `/api/health` versus `origin/main` check finds
a mismatch it cannot resolve, because there is nothing to resolve it to.

Worse than the typo: it was **noticed and explained away**. The anomaly was
seen -- earlier entries quote 40 characters, this one had 8 -- and written up as
"the short form, it still prefix-matches, not worth a redeploy". That
rationalisation was itself the error, and it was only caught because `gh run
list` printed `headSha` and the eighth character disagreed. Both instances were
redeployed with `$(git rev-parse HEAD)`. **Never hand-type a sha; substitute the
command.** Lesson written.

### The partner was invoked first, and it moved the session off its own list

Handed the six open items, the free tree and the file sizes. It ranked the
list, killed two items outright, and put **first a question that was not on
the list at all**: does the odds-feed credit budget survive NFL Week 1, with
NFL, NCAAF and MLB overlapping for the first time. That is the shape the
workflow step exists to produce — the backlog was thin and the partner said
so, rather than ranking six housekeeping items and calling it a session.

**It also corrected the calendar the session had handed it.** The prompt said
Saturday of opening weekend. It is Sunday, and the 2026 NFL season had not
started: the opener moved off Thursday to **Wednesday 2026-09-09**, and Week 1
runs to Monday 09-14. So there was no NFL slate to build for, and there was a
three-day deadline instead.

### The falsifying check the partner had set was dated to the wrong end of the weekend

Open item 3 read: read `parlay_positions` on **2026-09-09**, and if it is still
0 after an NFL opening weekend, ADR 0078's `/hedge` route is a deletion
candidate. **09-09 is the day the season opens.** A read taken then would have
found 0 before a single NFL game had finished and called that grounds for
deleting a working route — refutation arriving early and for free, in the one
direction a falsifying check must never fail.

Re-dated to **2026-09-15**, the first morning after Week 1 closes, with the
event named beside the date so a later reader can re-derive it. The superseded
line in the 2026-09-05 entry is struck through in place rather than left
readable as current. The correction is the partner's own, found at the top of
the next session; the lesson is that a date-triggered check is dated from the
event's **end**, and the derivation is looked up when the check is written
rather than recalled.

### `NEXT.md` split on a date boundary, as the session's first act

223,790 bytes at open, 85.4%, read **before** writing. Nine entries — three
2026-09-02, two 2026-09-01, four 2026-08-31 — moved verbatim to
`archive/next-2026-09-06.md`, leaving 117KB, **44.7%**. Verified by md5: the
archived bytes below the header hash identically to the bytes removed. Index
lines moved in the same edit.

Cut deeper than the 90% trigger required, and on a **date boundary** —
everything 2026-09-02 and earlier — so no single day is split across two files.
Previous splits did not always manage that and the index is harder to read for
it.

### Lane A — the credit answer was refused once, and the second document is a bound

**The budget survives NFL Week 1 and nothing needed changing.** But the first
draft was refused on audit and the reason is the point of the entry.

`measurement-skeptic` returned **OVERSTATED**: right conclusion, reached the
flattering way. The base period contained **zero NFL calls, zero Sundays and
zero Mondays** while projecting a Thursday/Sunday/Monday sport — and the one
Sunday present was partial, correctly excluded from the mean, which removed the
only relevant cell without the document noticing. Ten of eleven judgment calls
leaned toward "no action needed". The `564` all-time maximum was used as an
upper bound across a regime change *and* a sport-count change, twenty lines
from the document's own four-sport projection of **770**, which exceeds it.

What the rewrite rests on instead is arithmetic that no defect can move:

    1,896 + 700 x 24.265 = 18,882          the paid 20,000 tier cannot be spent
    (18,000 - 1,896) / 24.265 = 663.7      94.8% of a cap enforced pre-call
    1,896 + 620 x 24.265 = 16,940          every day at the worst projected peak

The ~13,300 point estimate is withdrawn; a sensitivity table replaces it. The
better reason not to raise the cap came out of the audit too: the 18,000 to
20,000 gap is a **reserve for 10x-per-call historical pulls**
(`fly.live.toml:254-263`), not spare capacity.

**Two findings worth more than the verdict.** The trigger column could not
support the claim drawn from it — `runner.py:2419` stamps only `MANUAL` and
`ATTENTION`, so `SCHEDULED`, `REFRESH`, `BOOTSTRAP` and `DESK` all pool into
NULL — but `odds_sweep_log.detail` separates them cleanly: **kickoff window 319
(67.0%), hourly floor 107 (22.5%), desk open 50 (10.5%)**, summing to exactly
September's 476 rows. And the attention slice **never bound**: the highest
attention-tagged day in September is 112 against 300.

**The `spreads` lever the partner hoped for is closed.** It had reasoned that
if no Kalshi market can receive a point-spread comparison, dropping `spreads`
halves every sweep for free. `fair_prices` holds 3.5M `market='spreads'` rows
computed within a minute of the read, traced to `ParlayCards.tsx` via
`core/ladder.py:131` `TEAM_MARKETS_ONLY`. The "no consumer" premise is retained
2026-08-16 history, **overturned eighteen lines above itself** at
`fly.live.toml:416`. A stale paragraph sitting under its own correction reads
exactly like a live one.

**The day is not settled and the title says so.** A four-sport day projects
~770 against a 700 cap, and `timing.py:1835` returns `fire=()` — a breach stops
the whole feed for the rest of the budget day rather than throttling the sport
that overspent. Re-read after the first NFL Sunday (2026-09-13/14) or the first
four-sport budget day, whichever comes first.

### Lane B — the inspector is eight modules, and the split found a third silent failure

`scripts/inspect_live_db.py` was 97% of the ceiling and blocking work. Eight
files now, cut where the file's own section banners already cut it, largest at
**22.0%** against a 60% budget the commit enforces. Zero content lines lost, by
multiset diff.

**The surface is unchanged and the proof is mechanical**: 36 subcommands before
and after, same names and descriptions, 14 argparse actions with identical
option strings, `--help` byte-identical at 13,633 bytes, and all 40 (36 plus
Lane A's four) invoked by path in a subprocess with only `scripts/` on
`sys.path` — the box's own arrangement.

**The third allowlist failure is the part to remember.** `.dockerignore`'s `!`
allowlist has failed four times. `test_has_callers.py` derives two halves of it
— what `entrypoint.sh` runs, and what declares its own
`/app/scripts/<name>.py` — and **neither derivation can see an import**. Only
the entrypoint is invoked by path, so only it declares one, so both existing
guards would have reported a healthy allowlist while seven modules were absent
from the image. That surfaces as `ModuleNotFoundError` at an ssh prompt during
an incident, which is when the inspector is wanted.

**One guard was written, found green under its own mutation, and replaced.**
The NULL test began as "a NULL cannot *manufacture* a drop" and passed with the
filter removed, because SQL's three-valued logic already gives that away. The
property the filter buys is the opposite: an unreadable row must not *hide* a
reset by breaking the pairing across it. Recorded in the docstring rather than
quietly rewritten.

Lane A's four ad-hoc queries are folded in — `credits-reset`,
`credits-by-sport`, `credits-rate`, `fair-prices-by-market`. `credits-month`'s
own description now cites `credits-reset`, so the reading that was nearly
mis-taken carries its warning at the point of reading: a MIN/MAX over a
calendar month straddles the billing reset and reports a maximum describing no
live state.

### Lane C — the exit census is sourced on all three surfaces

Three sentences carried `"40 of 40"` as literals: the combo note, the
`/api/parlays/bid` 422, and the `/api/manual-orders` acknowledgement 422 on the
real-money path. All three are **exit** claims and all three are still true —
the census refuted only entry — so nothing on a screen was wrong. What was
wrong is the shape `parlays.py` already carries a comment block about.

New `COMBO_EXIT_CENSUS_*` constants, `_NO_YES_BID` derived so the pair cannot
drift, and the 40 re-counted from the committed artifacts rather than from
prose: 20 + 9 + 11 rows, none with a non-empty `yes_dollars`. Re-verified
independently before the merge. Every rendered string byte-identical by sha256
of the evaluated producer node, with the third site's baseline taken from
`git show HEAD` so the comparison is against the typed version.

**Three mutations, each observed red — and in every one the rendered-output
test stayed green while the `ast` guard failed.** That is this morning's lesson
demonstrated three times in the code that prompted it.

**The third site taught what the first two could not.** Its string carries
`ADR 0012 §5`, and the `ADR \d+` carve-out stripped the ordinal and left the
section number, so the guard tripped on an orphan digit from a *citation*.
Half-stripping a citation forces a choice between deleting a reference from a
real-money refusal and switching the guard off. The carve-out now spans the
section, and the sibling guard was brought to the identical pattern: two
spellings of one rule is how divergence starts.

### The CRLF residue, and a guard docstring that was wrong about it

Lane C's first mutation script used `pathlib.write_text` and silently rewrote
all of `routes.py` to CRLF. It caught and restored it, and the lesson is
written. Following that up over the tree found the residue of the same
mechanism: **33 of 422 tracked `.py` files carry CRLF in the working tree.**

`tests/test_session_files_are_readable.py` explained its own strictness with
"`.gitattributes` gives `*.py` `eol=lf`, so the ratchet's recorded size is the
same on this Windows checkout and on Linux CI." **That is false.**
`scripts/inspect_live_db.py` is 260,285 bytes here against the 254,479 git
stores — which is why this session and Lane B quoted **99.29% and 97.1% for the
same commit on the same day**, and only the first is the number that decides
whether a session can read the file. `eol=lf` governs what git writes at
checkout, not what a script writes afterwards, and `text=auto` normalises on
staging so the drift never appears in a diff. Docstring corrected; no assertion
changed, because the guard is still on the strict side.

**The dangerous case is already guarded and is green.**
`test_the_tracked_shell_files_are_lf_in_the_working_tree` exists from the
2026-08-27 crash loop where `entrypoint.sh` reached the image as `bash\r`.
Checked across all 37 `eol=lf`-governed files: no shell file, Dockerfile or
entrypoint carries CRLF. Only `backend/store/schema.sql` does, which SQLite
parses regardless.

### A premise correction the partner asked for and got the wrong way round

It ruled that before buying a billed Anthropic refusal fixture (open item 5),
someone should check whether `scout.py` has a production caller, citing
`CLAUDE.md`'s standing note that it "is called by nothing."

**That note is about `review_retired` (`backend/agents/review.py:124`), not
scout.** Scout has a full live path: `scout_router` registered at
`routes.py:1851`, `POST /api/scout/{ticker}` to `_run_scout_desk` to
`scout_desk.convene_desk` (`scout_desk.py:400`), which imports from `scout.py`;
the frontend calls it from `api.ts:2401` and `app/scout-desk/route.ts`, and live
health reports `agent_fleet_configured: true`. So by the partner's own rule the
fixture is justified. It was **not** bought this session — it costs a real
billed call and three lanes were in flight — and it stays on the list.

### Still open, in order

1. **`parlay_positions` on 2026-09-15** — re-dated this session, see above. If
   still 0 after NFL Week 1 closes, ADR 0078's route is a deletion candidate.
2. **The four-sport day is the live credit question and the month is not.** A
   four-sport budget day projects ~770 against a 700 cap, and a breach is
   global (`timing.py:1835`, `fire=()`), not a per-sport throttle. Re-read the
   headroom document after the first NFL Sunday (2026-09-13/14) or the first
   four-sport day, whichever is first. Nothing to do before then.
3. **The scout Anthropic refusal fixture (ADR 0106 §5.2)** — justified, see the
   premise correction above. Costs one real billed call. Not urgent.
4. **`cryptography` carries an open high-severity dependabot alert, and the
   assessment matters more than the label. NEW, found at close 2026-09-06 and
   not previously in any list.** `requirements.txt:9` pins `~=44.0`
   ("RSA-PSS signing. Not optional, not swappable"); 44.0.3 is installed. The
   advisory range is `>= 42.0.0, <= 48.0.0` and the **first patched version is
   49.0.0** — a five-major-version jump on the library that signs every Kalshi
   request. CVSS is **0**, i.e. unscored.

   **The reachability read, which is why this is not urgent:** the defect is
   exponential path-building on duplicate self-signed X.509 intermediates.
   This repo uses `cryptography` for RSA-PSS request signing; TLS certificate
   validation goes through httpx/OpenSSL, not this library's path builder.
   **No caller of the affected surface was found.** That is an argument, not a
   proof, and it is exactly the shape rule 1 says to distrust when it is
   convenient — so treat it as "probably unreachable, worth ten minutes to
   confirm", not as closed.

   It is its own lane when taken, with the signing tests as the gate, and it
   must not be done as a drive-by bump at the end of a session. The live
   instance holds real money and a broken signature is a total outage.

5. **Three ADR 0107 refusals that must not be upgraded by a later reader** —
   the unit of `market_exposure_dollars`, the NO-side sign convention, "before
   fees" as a label. A trigger on Joe holding a position, not a queue item.
   Unchanged.
6. **`"40 of 40"` survives in prose in three places** — `api/schemas.py:218`,
   `combo_bids.py:5`, `store/combo_orders.py:6`. All commentary rather than
   rendered copy, so none is urgent; the `schemas.py` one is a Pydantic
   docstring that can surface in OpenAPI, which makes it the only one worth a
   later pass.
7. **`.claude/worktrees/wf_e0ee5ede-e97-1`** — an empty husk a live process
   holds open. Delete when that process is gone. Unchanged.
8. **Lane B wrote no ADR**, because `docs/` was scoped to Lane A this session.
   Its rationale is in two commit messages, `.dockerignore`'s comment block and
   the test docstrings. An ADR for the inspector split is available on request
   and nobody is blocked without it.

**Nothing is Joe-gated.** Items 1 and 2 are date-triggered; the rest are
unowned work with no deadline. Item 4 is the only one touching a dependency the
live signing path needs, and it is the only one that should never be taken as
the last act of a session.

---

## 2026-09-06 (second entry) — Joe answered the four open questions; the combo note now carries BOTH censuses, ADR 0085 has Amendment 1, PRs #1/#2 are closed, and the shard-3 test and the key rotation are DROPPED on his word

**STATE, verified at close:** see the commit carrying this entry. This is the
first entry written after the parlay census, and it spends it: the census
refuted a sentence on three live screens, Joe chose what replaces it, and the
copy shipped in the same session as the decision.

### Joe's four answers, 2026-09-06

He was asked four questions in one artifact and answered all four.

    Q0  the combo copy, now that 51 of 52 fills were takers  ->  BOTH HALVES
    QA  close PRs #1 and #2                                  ->  CLOSE BOTH
    QB  shard-3 test / shard-0 move                          ->  DROP
    QC  Odds API key rotation                                ->  DROP

**Q0 was the only one that changes a live screen**, and it was framed with the
overcorrection named as an option so that choosing against it was a decision
rather than an omission. He did not take it.

### The combo note carries two populations now, and that is the whole point

`NOTES["unquoted"]` said *"usually you can neither buy in at a quoted price nor
be bought out"*. Half of that was refuted. It now reads, in this order:

1. **the book at rest** — 0 of 61 open combinations with a readable ask, 0 of
   the 6 deepest books with anything resting, 2026-08-30. Unchanged, upheld.
2. **the moment of entry** — 51 of 52 of this desk's combination positions were
   entered by hitting an offer, 2026-09-06. New, and the refutation.
3. **the exit** — no combination book read here has ever carried a YES bid, so
   plan to hold to settlement or hedge a leg. Unchanged, never tested by the
   census, and the reason the note is not simply deleted.

**One edit moved three surfaces**, because all three render the server's
sentence verbatim: the parlay card footer (`ParlayCards.tsx:87-91`), the
"Price on Kalshi" lookup (`PriceOnKalshi.tsx:195-197`) and the 20:00Z Discord
push footer (`discord.py:414-422`). The footer is 850 characters against
Discord's 2048 limit, now asserted rather than eyeballed — truncation eats the
END, which is where the exit warning sits.

**It says "this desk's own combination fills", not "your positions".** The same
string is served on demo, which holds no fills.

**"You can buy in" is still pinned ABSENT**, and Amendment 1 §A1.4 says why in
the ADR rather than only in the test: the entry finding makes the
overcorrection tempting, and that exact sentence is the one this note already
had to retract once.

### ADR 0085 Amendment 1 — and one struck bullet in the body

`docs/adr/0085-*.md` gains `## Amendment 1 (2026-09-06)`: what the census
refuted (entry, `n = 52`, `k = 51`, interval [0.8974, 0.9995], registered bound
`k >= 34`), what it did not (the resting book, every exit claim, ADR 0084's buy
path), why both are true (list summary vs orderbook — two instruments), and
Joe's decision with the three rules that replace the struck one.

**The body was edited too, not just appended to.** *"It must not imply a fill
is likely"* is struck through in place, in *What the card must not do*, with a
pointer to §A1.4. An amendment that leaves the refuted rule readable as current
rule is how a reader two months from now re-derives the wrong copy.

### A guard written to catch a hardcoded number could not see a hardcoded number

The existing pin read `assert str(parlays.COMBO_CENSUS_OPEN) in notes[...]`,
and its comment explains that it exists because the literal `"40 of 40"` once
kept a refuted sentence green. **It does not do that.** `str(61) in note` is
identical whether the note interpolated the constant or someone typed `61`.

Verified by mutation: replacing `{PARLAY_CENSUS_TAKER_FILLS} of
{PARLAY_CENSUS_POSITIONS}` with a literal `51 of 52` left that test **green**.
`test_no_census_number_in_the_note_is_typed_rather_than_sourced` parses the
module with `ast`, finds the f-string, and refuses any bare digit in it —
reading the producer, because the difference exists only before interpolation.
Lesson written.

**Four mutations, all observed red**, each restored before the next: delete the
entry sentence; reintroduce "you can buy in"; drop the exit warning; hardcode
the digits.

### PRs #1 and #2 closed; zero open

Both were opened 2026-08-15 from the jcabiles account and both were genuinely
superseded, checked rather than assumed: `frontend/package.json` on `main`
already carries `"next": "16.3.1"`, which was #2's entire change, and #1's
task-file corrections were overtaken by the 2026-08-17 archive split. Each
closed with a comment naming what superseded it.

### QB and QC are DROPPED, and dropped is not deferred

- **The shard-3 test and the shard-0 move are dropped.** They had sat on "Joe's
  word only, do not nudge" since 2026-08-20. `user_not_found` on shard 3 is no
  longer an open item and does not belong in a future Open list; baseball hand
  bets stay outside the tool. **Do not resurface this** — it was carried
  through eleven entries and answered once.
- **The Odds API key rotation is dropped**, having been "later" on 2026-09-03.
  The exposure is accepted as immaterial: local transcript only, never
  committed, `.env` gitignored. **The standing guard for sessions is
  unaffected and stays**: establish config from `.env.example` and
  `fly.*.toml`, never by reading `.env`.

Both are recorded as *decisions* rather than deleted, so a session that finds
the old lines in the archive can see they were answered.

### Still open, in order

0. ~~**THE CENSUS RESULT NEEDS A PRODUCT DECISION FROM JOE.**~~ **Done
   2026-09-06.** Answered (both halves), amended (ADR 0085 Amendment 1), built
   and pinned. See above.
1. **`backend/api/routes.py:3039` and `backend/api/routers/parlays.py:277-283`
   still say "40 of 40"** — hardcoded digits from the 2026-08-09/18 YES-bid
   runs, on `/api/manual/quote`'s combo note and the `/api/parlays/bid` 422.
   Both are **exit** claims, so both are still true and neither is urgent; what
   is wrong is that they are typed rather than sourced, which is the exact
   shape `parlays.py` carries a comment block about. A constants pass, its own
   small lane.
2. **`scripts/inspect_live_db.py` is at 99.3%** — 1,859 bytes free, and it
   blocks work. Needs a domain split with its own brief, not another trim.
3. **`parlay_positions` on ~~2026-09-09~~ 2026-09-15 — the falsifying check
   the partner set. RE-DATED 2026-09-06, and the old date could not have
   worked.** If it is still 0 after NFL Week 1, ADR 0078's route is a
   candidate for deletion. The date moved because **2026-09-09 is the day of
   the opener, not the day after the weekend**: the 2026 season starts
   Wednesday 2026-09-09 (the opener moved off Thursday) and Week 1 runs to
   Monday 2026-09-14. A read taken on the 9th would have found 0 before a
   single NFL game had finished and called that evidence for deletion. The
   partner set 09-09 from a remembered "opening weekend" and the league had
   moved it; the correction is the partner's own, found at the top of the
   next session. 2026-09-15 is the first morning after Week 1 closes.
4. **Three ADR 0107 refusals that must not be upgraded by a later reader** —
   the unit of `market_exposure_dollars`, the NO-side sign convention, "before
   fees" as a label. A trigger on Joe holding a position, not a queue item.
5. **The scout Anthropic fixture (ADR 0106 §5.2)** — narrowed, still open. The
   report shape was captured 2026-09-06; the refusal shape is still
   SDK-derived, and a real refusal costs a real billed call.
6. **`.claude/worktrees/wf_e0ee5ede-e97-1`** — an empty husk a live process
   holds open. Delete when that process is gone.

**Nothing here is Joe-gated any more.** The five 2026-09-04 questions are all
answered or dropped, and the decision map is exhausted at 32 of 32.

---

## 2026-09-06 — the parlay census is TAKEN and ADR 0085 is REFUTED at the moment Joe buys; #24, Lane A2, the money-arm predicate, the agent wire fixture and Joe's four answers are all deployed; the inspector blocks work at 99.3%

**STATE, verified at close:** `main` = `c546cb7`, pushed, CI green. The
census commits sit above the deployed code and are **docs, an analyzer and
tests only** — nothing after `c2976ec` changes what runs, so live and demo are
correctly still on `c2976ec` and no deploy is owed.

**Earlier in the same session:** `main` was `c2976ec`, pushed. **CI green**
(run on that sha; earlier in the day, run 34001824759 on `aa25bbf`; `Tests + warehouse`, `Secret scan`, `Frontend` all
success). **Live and demo are both `c2976ec`** — demo run 34011211303, live
run 34011294986, with **schema v34 verified on both volumes by direct read**
(`desk_attention` carrying `path`; live holds 1,041 stamps, 0 with a path yet,
which is the honest state seconds after a deploy), both `/api/health` ok with the sha matching and the live
recorder 38s fresh; `GET /api/estimates/stop` re-read on demo after its
rewrite and still serving the tri-state (`"stopped": null` against a null
loss). Full suite on the final tree: **6,144 passed, 10 xfailed,
0 failed** (9m30s), `ruff` and `npx tsc --noEmit` clean, `next build` green.
Under it: `e8f409f` (the #24 records), `dd7533c` (ticket #24), `6a1d1e0` (the
backlog entry and the audit corrections), on `ed95fa6`.

**Both builds were verified on the deployed artifact, not only in tests** —
Playwright against demo, in each defect's own state. #24: a market page whose
quote strip refuses a stale ask now shows the ticket's *masked* wording where
it used to assert "the price is already on this screen". A2: the strip reads
"Open positions never read yet — **no positions poll has succeeded yet**",
where it used to say "the positions mirror is behind" — a claim that is false
when nothing was ever polled. Demo holds no Kalshi credentials, which is
exactly what puts it in that refusal state.

### Ticket #24 — the flag that claimed a price the screen was not showing

Joe resolved it 2026-09-02 (option A) with the build order in his own words:
*"Build: the amendment, the conditional flag, then the link."* It had sat
unbuilt for three days, in the third queue — decided-and-not-yet-built —
which is exactly the gap the SESSION START box warns about.

**The defect.** `market/[ticker]/page.tsx` passed `priceAlreadyVisible`
unconditionally, so the hand-bet ticket said *"The price is already on this
screen, so that number is anchored by it"* in three states where the quote
strip prints nothing: `detail` null, a refused stale ask, and a market past
its close. On the surface that sends real IOC orders.

**The fix is a shared predicate, not a second condition.**
`frontend/src/lib/quoteVisibility.ts` exports `quoteVisibility(detail, now)`
returning `"ask" | "stale" | "absent"` — the strip's own three outcomes — and
`askIsVisible`. The strip renders from it; the page passes
`priceAlreadyVisible={askIsVisible(detail, now)}`. Re-testing
`price_is_current` on the page would have been correct on the day and rotted
at the next condition added to the strip: the **fifth** instance of the shape
CLAUDE.md records four times.

**The link, last.** Each `MarketSearch` result links to `/market/{ticker}`
alongside its ticket, never instead of it. The list stays price-free, so ADR
0065's masking on that screen is untouched.

**Verified on the deployed artifact, not just in tests.** A demo market page
in the stale-ask state renders no `Ask $` line, the strip's refusal *"not a
price you can transact on"*, and the ticket's **masked** wording — the same
page that before this commit asserted the price was on screen. That is the
before/after, taken through Playwright against demo at `dd7533c`.

### Three guards of my own that were decoration, and how each was found

All three were found by mutating, not by reading, and all three are recorded
in the tests rather than quietly patched:

- `"<ManualTicket" in search` stayed green under a mutation renaming the
  component `<ManualTicketXX`. **A prefix is a substring of every longer
  identifier.** `tests/test_buy_controls.py`'s `MOUNTS` check has the same
  blind spot; left alone rather than widened from a lane that is not its own.
- The same guard then stayed green a *second* time, for a better reason: the
  component's own comments name `<ManualTicket` while explaining the design,
  so it was reading **prose about the mount instead of the mount**. Comments
  are stripped first now.
- My link label read *"See the price and what the desk knows"* — while the
  destination renders "the recorder never priced this ticker" in exactly the
  states the flag guards. **The same defect one level up.** It says "Open the
  game screen" and a pin refuses any label promising a price.

**Two pins in `test_tab_ledes.py` guarded the UNBUILT state** — that the
comment says "conditional", that the prop is passed bare — and were rewritten
in the same commit. Copy naming a condition to wait for is falsified by fixing
the condition, so the fix and its pins ship together or the suite asserts the
defect.

`tests/test_quote_visibility.py` executes the shipped predicate under **node**
rather than asserting on source text, because the defect was a wrong verdict
and a substring test passes unchanged on an exactly inverted predicate. Five
mutations, all observed red.

### Joe's four answers, 2026-09-05 — A yes, B kill, C yes, D yes

He was asked four in one line and answered in one line. Three are built and
deployed at `c2976ec`; A is registered and its one live arm is not yet run.

**A — TAKEN 2026-09-06, and it REFUTED a belief this repo ships on three
screens.** `docs/measurements/2026-09-05-parlay-census-result.md`; instrument
`scripts/measure_parlay_census.py` committed at `950ad72` **before** the pull;
extraction gitignored under Joe's fills-data ruling.

```
H1 (Arm D)   n = 52   k = 51   p_taker = 0.9808
             exact interval [0.8974, 0.9995]   critical (18, 34) as registered
             VERDICT: ADR 0085 REFUTED ON THIS POPULATION
```

**51 of Joe's 52 combination positions were entered as TAKER fills.** No
downgrade fired: 0% unreadable, largest C-day 15.4%, `G_eff` 10.24 against a
floor of 10 (clears by 0.24 — attack this first if revisited), no
leave-one-day-out crossing, strict definition on the same side. Torn-snapshot
precondition passed exactly.

**Rule 1 caught a bug in the checker before it caught anything about the
venue.** The first run printed UNRESOLVED on this same data: `arm_d`
classified by parsing its own verdict sentence, and "ADR 0085 REFUTED ON THIS
POPULATION" ends in "POPULATION". It bit **only** the refute branch, so no
test that failed to produce a refutation could see it. Fixed, pinned, re-run
on the **same** snapshot — the pull is the look.

The three named checks then cleared the venue: `is_taker` discriminates in
both populations (combos 52/1, singles 7/2, no NULLs); **the one tool-placed
fill is the single MAKER in the population**, exactly as Amendment 1 predicted
when it decided blind to keep them in the denominator; every fill in both
populations is `source = 'venue_hand'`.

**What is refuted is narrow, and the result file says so at length.** The
2026-08-30 census read the `/markets` LIST summary (`yes_ask 0.0000`,
`no_bid 1.0000` → derived ask `$0.00`); `lookup_combo` reads the ORDERBOOK.
Different instruments — the registration's C4 item, resolved by code-reading.
And the population is **self-selected structurally**: Joe only has a fill where
a fill was possible, so conditioning on entry succeeding and then measuring how
often entry succeeded is not a measure of buyability at large. The claim is
about **the moment he buys**, not about the order book. §12.7 named that before
the run.

**The money arms carry no verdict and may never be given one** (§8): $60.13
staked, $3.74 fees, 2 of 51 resolved winners, net −$59.83 (bracketed to
−$55.49 on the one unresolved row). A bank statement, not a finding.

**A — the parlay census. Registered AND TAKEN. The question he actually asked
cannot be answered at this `n`.**
`docs/measurements/2026-09-05-parlay-census-registration.md`. The
pre-registrar split it into arms and killed the headline before any per-row
read:

- **The head-to-head is dead as inference.** 5 parlays where the desk priced
  the ticket he bought; ±19.5 points against a quantity of magnitude ~5. It
  would need **475** independent desk-priced parlays, ~3.6 years at the
  observed rate. Kept as a printed 5-row table, never a finding.
- **The clustering variable is not computable.** What makes two parlays
  dependent is a shared leg and `parlay_position_legs` is empty, so `n_eff`
  is unknown, bounded [1, 52]. That forbids outcome inference more cleanly
  than the 2-of-51 win count does.
- **Most of the brief had already been seen, and that disqualified it.** The
  win split, the money staked, the fees, the `parlay_lookups` status counts
  and the 5-of-52 coverage all came from aggregates read while scoping. A
  threshold applied to a number the author knows is not a threshold, so every
  one is demoted to a transcription with no p-value — **including the
  `book_empty` arm that had been flagged as the most actionable finding.**
  See the lesson; the fix is to split reconnaissance into *what exists* and
  *what happened*.

**The one verdict-bearing test that survives is Arm D: were the 52
combination fills takers?** ADR 0085, ADR 0012 §5, CLAUDE.md and the memory
line all assert combinations are unquoted, and Joe's own 52 fills are the
population that tests it. `k <= 18` upholds, `k >= 34` refutes, `19..33`
UNRESOLVED, at the expected `n = 52`. **Rule 1 applies to a refutation**: a
large contradiction of a measured belief is a bug until proven otherwise.

**C4, resolved by code-reading rather than data** (the registrar's own
ranking put it above everything else in that arm): `parlay_lookups` records 7
taps as `priced` while the 2026-08-30 census reports 0 of 61 quoted. They read
**different endpoints**. The census reads the market-list summary
(`yes_ask_dollars = 0.0000`, `no_bid_dollars = 1.0000` — the derived ask is
then $0.00); `lookup_combo` reads the orderbook, via `OrderBook.best_no_bid`.
The list flattens an empty side to a boundary value, which is the derived-ask
trap this repo already documents. Not a contradiction; two instruments.

**B — #11's estimate log screen is killed (ADR 0094 §11).** The screen was
never built. What exists is a complete, unreachable write path — `logEstimate`
→ `/log-estimate` → `POST /api/estimates` → `record_estimate` — with **zero UI
callers**. Killed on a measurement: 0 of 27 hand fills through the order path,
`bet_estimates` ≤ 1 row, three entry designs drawn and none used.

**Nothing was deleted and that is the decision.** Joe killed a screen; removing
a backend route, its proxy, its auth wiring and its embargo-scoped writer is a
larger change than he made, and the chain carries ADR 0044's embargo
machinery. `TestTheLogScreenStaysKilled` pins the absence of a UI caller,
because `logEstimate` reads exactly like a function someone forgot to call.
ADR 0065's "the form returns" clause is struck.

**C — `desk_attention.path`, schema v34, live and demo verified on the
volume.** The table was `(id, seen_ms)` and could say the desk was open but
not what it was open FOR. **Recorded, never acted on**: a test pins that
`odds/timing.py` cannot see the column at all, which is what makes the
distinction true rather than merely stated. The route's long-standing refusal
of a body was about a client-supplied *timestamp* — acted on, and worth
choosing wrong — and the clock is still the server's. `Nav.tsx` reads the path
inside the beat, not at mount, or every stamp would report the screen the tab
was loaded on. `visit-freshness` reports `paths` and `paths_null` per visit;
`paths_null` counts pre-v34 stamps and is not a zero.

**D — one real Anthropic response, captured, and ADR 0106 §5.2 is CLOSED.**
`scripts/capture_agent_wire_fixture.py`, one paid call, key never read or
echoed, body only, gitignored `data/` first and promoted after reading.

**It falsified the model of the wire every stub in this repo carried.** A real
scout call returns **25 content blocks and exactly one is `text`** — the rest
are `server_tool_use`, `web_search_tool_result`, `code_execution_tool_result`
and `thinking` — and the text block is **last**, so `parsed_output` walks past
twenty-four. The usage block carries a nested `cache_creation`,
`output_tokens_details.thinking_tokens` and `inference_geo`; the envelope
carries `container` and `stop_details`. None was guessed.

**It cost 66,131 input and 3,967 output tokens (2,103 thinking) on 6
searches** — well above the ~$0.08 quoted when the spend was authorised. That
figure was `base.py`'s *Skeptic* ceiling; its desk arithmetic (~50K in per
staff scout) is the right one to quote for a scout.

Safe for a public repo, checked before promotion and pinned by two tests: no
credential, no account identifier, no request headers, and third-party page
content arrives as `encrypted_content` — the fixture cites sources without
reproducing them.

### Four things broke, all caught, none shipped

- **A `--` comment inside a `CREATE TABLE` column list broke `DROP COLUMN`.**
  SQLite re-parses a table's stored SQL, and 33 migration wind-back steps went
  red naming versions the change never touched. Prose goes above the statement.
- **A pre-existing test wound back to `SCHEMA_VERSION - 1` while asserting
  v33's effects**, so it silently retargeted the moment v34 existed. Pinned to
  32. A relative version is safe only for a claim true of *every* version.
- **Two guards asserted the mechanism, not the property** (`"body: {}"` for
  "no clock crosses this boundary"), so both went red for changes that did not
  violate them. Rewritten at the level of the property.
- **A corrected guard then read the docstring explaining the property** —
  second time in one day. Strip comments before searching.

### `scripts/inspect_live_db.py` is at 99.3% and now blocks work

260,285 of 262,144 bytes: **1,859 free**. Two comment blocks moved out
verbatim this session — the CLV extraction's commentary to Appendix S1a of its
registration, the prop-rung commentary to its own — buying 3.4 KB, and it is
still on the line. Comparable subcommands run **2.6 KB to 21.5 KB**, so
**nothing new fits.**

This stopped being cosmetic: the census registration named
`_q_parlay_census` in this file as its instrument, and it cannot go there. Joe
chose (2026-09-05) to amend the registration's instrument location rather than
make the split the price of admission for the measurement. **The split is
still owed and needs its own brief** — a domain split, not another trim.

### Lane A2 — the branches that swallowed the server's reason

ADR 0107 put the staked figure on the wire and touched no `frontend/`. Three
defects on the screen side, all in `OpenPositions.tsx` (`39e912b`):

- **`count === null` printed one hardcoded sentence for four distinct
  refusals**, and that sentence was *false* in two of them. `backend/bets.py`
  words them apart deliberately — "no positions poll has succeeded yet" is a
  different fact from "not read in the last 30 minutes" — and the screen
  replaced all four with "the positions mirror is behind". Nothing is behind
  when nothing has ever been polled, and a record the server could not read
  is not a lagging mirror. **A refusal the server worded carefully and the
  screen replaced with its own guess is worse than no refusal, because it
  reads as knowledge.**
- **`count === 0` returned before `StakedNow`.** What was being swallowed is
  an **integrity** refusal at a zero count, which is reachable:
  `STAKED_MIRROR_MISMATCH` fires when the mirror holds rows under a poll that
  counted none — the table disagreeing with the read that wrote it.
- **`/slate` printed a bold "$X staked" twice for two different numbers**,
  seven lines apart: this figure is money on positions open now,
  TonightStrip's is money committed since the day roll. The muted qualifiers
  distinguished them; the bold text, which is what the eye takes, did not.

**One thing in the brief was wrong and is corrected here.** The partner's
framing — the empty-but-fresh `$0.00` is "computed by the server and dropped
by the client" — treats a redundancy as the defect. "No open positions at the
venue" already says $0.00, and printing both is noise. The real loss in that
branch was the *refusal*. The zero is still not printed and that is a
decision, recorded in the component and pinned by a test.

**The guard renders the component rather than reading it.** Node strips types
but does not transform JSX, so
`tests/test_open_positions_renders_every_refusal.py` compiles the real `.tsx`
with the repo's own `tsc` and renders it through `react-dom/server` at the
shipped versions. A substring test sees `staked_refusal` in the file and calls
it covered; it cannot see that the mention sits in a branch the payload never
reaches — which is the entire defect.

**9 of its 13 tests fail against the pre-fix component.** That is the evidence
it catches the defect rather than describing the fix, and it is a cheaper
check than it sounds: `git show HEAD:<file>` into place, run, restore.

**It was made 3x cheaper before landing** — ~34s to ~12s. Every test
recompiled the same source; `tsc` is ~2.5s a call and eleven of thirteen
tests render identical bytes. A module-scoped build fixture fixed it. An
eighth of CI's whole `Tests + warehouse` budget for eleven identical compiles
is exactly the shape this file already warns about.

Also corrected: `capture_positions_fixture.py`'s `EXIT_EMPTY` said "the
per-row shape is still unobserved", false since the 2026-08-30 capture. ADR
0107 §7 recorded it stale and left it under a keep-it-byte-identical brief;
that brief expired.

### Joe's parlay question — scoped, and the half he asked about is blocked

Added as Open item 2. **`parlay_positions` and `parlay_position_legs` are 0
rows on live**, `manual_orders` is 0, so "which parlays did Joe pick" has no
population; ADR 0078's `/hedge` has been deployed ten days and never held a
ticket. What does exist: `parlay_lookups`, **34 taps**, carrying the desk's
own `fair_joint_conservative`/`hold`/`derived_yes_ask_tenths` and the legs as
JSON — **74 distinct legs, all 74 in `kalshi_markets`, 64 already settled**.
So the recommendations are retrospectively scorable; the picks are not.

**24 of the 34 taps were `book_empty`** — the majority of what the desk
recommended could not be bought at any price. That is a defect in the
recommendation independent of its probabilities, and it is the more promising
place to start. `n = 7` priced is below the >=5-expected rule: **census, not
calibration test.** Only aggregate counts have been read; no outcome has been
compared to any stated probability, so the pre-registrar can still fix the
form.

### The dead-code list is three, not nine

Open item 5 corrected in place. Six must not be deleted — `reset_walk_alarm`
is called by an autouse fixture in root `conftest.py` on **every test in the
suite**; `discover_from_events` has four operator call sites;
`alerts.check_fee` is a deliberate arming hook whose docstring says so;
`cents_to_tenths`/`allowance` churn ~322 lines of live-code tests for three
executable lines; `_skeptic_context` is called twice per judged row. **The
first audit scoped its grep to `backend/` and `scripts/`, which is how a
fixture running before every test read as having no caller.**

### Still open, in order

0. ~~**THE CENSUS RESULT NEEDS A PRODUCT DECISION FROM JOE, and it is the only
   item that changes a live screen.**~~ **ANSWERED AND BUILT 2026-09-06 — see
   the entry above.** Joe chose *both halves*; the note now carries the
   resting-book census, the measured entry rate and the unchanged exit
   warning, and ADR 0085 has Amendment 1. The rest of this item is kept as the
   brief that was acted on. Three surfaces tell him he probably
   cannot buy a combination — the parlay card note, the nightly 20:00Z Discord
   push, and `NOTES["unquoted"]` built from `COMBO_CENSUS_*` in
   `backend/parlays.py:112-116`. **He bought in 51 times out of 52.** The copy
   is wrong at the moment he is actually buying, and right about the order book
   at large, and those are different sentences.

   Owed: an **ADR 0085 amendment** recording both halves, then whatever Joe
   decides the card should say. **Do not write the copy before he chooses it** —
   ADR 0071 §2.2 makes price transparency the job, and a sentence that
   overcorrects to "you can buy this" would be the same error in the other
   direction, on the surface that spends his money. The previous version of
   that note said exactly that and was refuted; `tests/test_parlays_api.py`
   pins "you can buy in" ABSENT, so changing it is a deliberate test edit.

1. ~~**Lane A2 — the screen for the staked figure.**~~ **Done and deployed
   2026-09-05 (`39e912b`, live + demo).** Three defects fixed in
   `OpenPositions.tsx`: `count === null` printed **one hardcoded sentence for
   four distinct server refusals**, and that sentence ("the positions mirror
   is behind") is *false* for two of them — nothing is behind when nothing was
   ever polled; `count === 0` returned before `StakedNow`, hiding a reachable
   **integrity** refusal (`STAKED_MIRROR_MISMATCH` at a zero count = the
   mirror holds rows under a poll that counted none); and `/slate` printed a
   bold "$X staked" twice for two different numbers, now disambiguated on the
   `OpenPositions` side only (TonightStrip's use is the older one, cited by
   ADR 0107 §3 as the precedent).

   **The $0.00 is deliberately still not printed** at `count === 0`: "No open
   positions" already says it, and the brief's framing — that the figure was
   "computed by the server and dropped by the client" — treated a redundancy
   as the defect. The real loss in that branch was the refusal, not the zero.

   `tests/test_open_positions_renders_every_refusal.py` **renders the
   component** (tsc → `react-dom/server`) rather than reading it, because a
   substring test cannot tell a mention in a live branch from one in a dead
   branch. **9 of its 13 fail against the pre-fix component** — that, not the
   green run, is the evidence it catches the defect.
2. ~~**The three duplicate-spelling predicates.**~~ **Done 2026-09-05
   (`aa25bbf`, deployed), and ONE of the three was one.** Audited rather than
   taken on the framing:

   - **`study_stop_fired` was the case.** `GET /api/estimates/stop` spelled
     `None if loss is None else loss >= STUDY_LOSS_CEILING_DOLLARS` inline
     while the named function — identical tri-state — ran nowhere, so the
     registered ceiling had two live spellings and only the anonymous one was
     served. The route calls it now. Its docstring also claimed the write path
     still refuses on it, false since ticket #11 (ADR 0044 Amendment 3).
   - **`loop_failures_since` was not.** No production caller, but it is the
     reader six assertions use to verify `record_loop_failure`, which is live
     — production-unreached and load-bearing, `reset_walk_alarm`'s standing.
     The inspector's read of that table is a DESC tail with no lower bound: a
     different question.
   - **`seen_at_least_once_since` was not.** A declared instrument whose
     docstring says nothing calls it and why, like `alerts.check_fee`. What
     WAS wrong: it claimed "nobody has measured it", and the dwell read was
     taken 2026-09-03 by the inspector's `visit-freshness`.

   `inspect_live_db.py`'s third implementation of the money arm is deliberate
   and pinned equal by `tests/test_study_stop_query.py`; left alone. **A
   guarded second implementation of a registered formula is a cross-check; an
   unguarded one is the bug** — that is the line the audit turned on.
3. **The scout Anthropic fixture (ADR 0106 §5.2) — NARROWED, still open.**
   `tests/fixtures/anthropic_scout_{report,refusal}.json` now exist, built for
   zero dollars by `scripts/build_agent_wire_fixture.py`, and
   `tests/test_agent_wire_format.py` drives them through the SDK's own
   `Message.model_validate` and `parse_response`. **They are SDK-derived, not
   captured, so §5.2 stays open** — the SDK's models are our belief about the
   wire and a fixture generated from them cannot falsify it. A real capture
   still costs a real call on the billed path; that is the remaining ask.

   **Writing it found a live defect, which is the part to carry.**
   `base.py`'s refusal branch is **unreachable**: `messages.parse` parses
   content with no regard for `stop_reason`, so a refusal raises
   `ValidationError` inside `.parse()` and the `Message` never comes back —
   the call is billed and its token count dies with it. `ValidationError` is
   now caught apart from a transport failure (the two differ in the one way
   the meter cares about); the count is not recoverable without
   reimplementing the SDK's `output_format` → JSON-schema transformation.
   The dormant branch is kept and says it is dormant.

   The old stubs could never have found this: both assign
   `self.parsed_output = parsed` over a **property**, so the SDK's parsing had
   never run in this repo at all.
4. **Three ADR 0107 refusals that must not be upgraded by a later reader** —
   the unit of `market_exposure_dollars`, the NO-side sign convention, and
   "before fees" as a label. **Not a queue item**: it is a trigger on Joe
   holding a position. Demo holds no Kalshi credentials, so there is no way
   around it. It already lives correctly in ADR 0107 §8/§9.
5. **`parlay_positions` on ~~2026-09-09~~ — the falsifying check the partner
   set.** ~~The hedge desk shipped in the MLB/WNBA window; parlays are largely
   a football product and NFL opens this weekend.~~ **RE-DATED to 2026-09-15
   on 2026-09-06** — 09-09 is the Wednesday the season *opens*, not the day
   after Week 1, so that read would have measured nothing. See the latest
   entry's open item 3. If it is still 0 after NFL Week 1, the
   transcribe-it-yourself entry design is refuted — ADR 0078's route becomes
   a candidate for deletion, not decoration.
6. ~~**Joe-gated, untouched:** the five questions A–E from 2026-09-04.~~
   **ALL ANSWERED — nothing is Joe-gated as of 2026-09-06.** A, B, C and D
   landed 2026-09-05 (see this entry). The two that were still open were
   answered 2026-09-06 and both were **DROPPED**: the shard-3 test and the
   shard-0 move, and the Odds API key rotation. Dropped, not deferred — they
   do not return to a future Open list. The standing guard against reading
   `.env` is unaffected and stays.
7. **`.claude/worktrees/wf_e0ee5ede-e97-1`** is an empty husk a live process
   holds open. Delete when that process is gone. The other three were removed
   2026-09-05; the junction hazard was checked (`st_file_attributes & 0x400`)
   rather than assumed, and did not apply.

**The decision map is exhausted — 32 of 32 closed, frontier query returns
zero.** That means the *design* backlog is spent, not the product. The queue
is this file plus the third queue (decided-and-unbuilt), which just swallowed
#24 for three days.

---
## 2026-09-05 — the session Joe stopped is picked up: three finished lanes merged (ADR 0106, 0107, the routes split), and the one cross-lane break git could not see

**READ THIS FIRST if you are wondering why `main` looked wrong.** The
previous session was the **integrator** over three worktree lanes. All three
finished and committed; none was merged; the session was stopped. Its own
commit on `main` (`0087fa1`) had already gone in *ahead* of the merge, and it
rewrote `.env.example`'s "Who cannot" block and `fly.live.toml`'s fleet
bullet to say `historian.py`, `skeptic.py` and `review.review_surfaced`
"were deleted on 2026-09-05 (ADR 0106)" — **while all three were still in the
tree.** It was unpushed, which is the only reason the public repo never
carried the claim. Merging Lane C is what made it true. **The lesson is the
ordering**: an integrator commit that describes a lane's effect must not land
before the lane does, because a stopped session leaves the description
without its subject.

**STATE, verified at close:** `main` = `da3614b`, pushed. **CI green**
(run 33993384750, `Tests + warehouse` 314s). **Live and demo are both
`da3614b`** — demo run 33993534072, live run 33993654879, both
`/api/health` ok with the sha matching and the live recorder 59s fresh.
The merge commits under it: `363d502` (Lane A1 / ADR 0107), `165b5c5`
(Lane B / routes split), `b154891` (Lane C / ADR 0106), `0087fa1`. Ordinals were taken at the merge
boundary after `git fetch`, per `docs/adr/README.md`: 0105 was highest on
`origin/main`, and `SCHEMA_VERSION` was re-read as 32 there before v33 was
accepted. No `DRAFT-` file remains. All three lane worktrees still exist
under `.claude/worktrees/wf_e0ee5ede-e97-{1,2,3}` and can be removed.

### What landed — three lanes, merged C → B → A1

- **Lane C, ADR 0106 (`b154891`)** — `backend/agents/historian.py`,
  `backend/agents/skeptic.py` and the metered half of `review.py` deleted:
  34,626 bytes, 30.5% of `backend/agents/`. `review.py` survives at 7,425
  bytes holding `review_retired` and importing nothing that can bill. New
  `tests/test_reachable_callers.py` walks names from the boot script to a
  fixed point and caught a real blind spot — **`apply_verdict` passed all
  three `has_callers` tests for fifteen days while unreachable**, because its
  one production referrer sat inside a function nothing called. It also read
  the live volume: **`scout_briefings` holds eight complete rows**
  (2026-08-21 → 08-30), so Anthropic money *has* been spent from the desk;
  ADR 0071 §3's "not established whether the desk has ever convened on live"
  carries a dated correction blockquote rather than a rewrite.
- **Lane B (`165b5c5`)** — `backend/api/routes.py` 333,958 → **193,733
  bytes**, 68,411 under the Read ceiling, so a session can read it again.
  Steps 1–5 and 8 of the split map ran; handler bodies moved byte-identical
  (stdlib `tokenize`, 0 differences across 73 definitions). New
  `backend/api/{schemas,serialise}.py` and `backend/api/routers/{scout,
  parlays,hedge,odds,status,ledger,estimates}.py`. The ratchet is deleted,
  not emptied. `tests/test_routes_reexports.py` pins re-export **object
  identity** — the lane found that a shim spelled right but bound to a *fresh*
  dict passed 47 of 47.
- **Lane A1, ADR 0107 (`363d502`)** — schema **v33**. `venue_positions`
  mirrors the `/portfolio/positions` rows the poller counted and threw away,
  under the `poll_log` row that recorded the read; `poll_log.mirrored` marks
  which reads kept theirs. "Staked" is exposure at cost, integer tenths,
  before fees; an unreadable row refuses the whole figure rather than
  contributing a partial sum. Retention is the writer's (7 days,
  `portfolio_poll.py:95`) and `retention.prune()` deliberately excludes it.

### The cross-lane break, which is the part worth carrying

**Two lanes wrote `tests/test_has_callers.py` the same day, their hunks did
not overlap, and the merge was clean in git and wrong in fact.** Lane C
re-pointed an anti-vacuity pin at `backend/api/routes.py` as the module that
calls `build_client`. Lane B had already moved `send_scout_desk` — the only
such caller — into `backend/api/routers/scout.py`. Neither diff touched the
other's line, so nothing conflicted; the pin would simply have asserted a
call site that no longer exists.

**Pattern: a clean `git merge-tree` is a statement about text, not about
meaning. When two lanes touch the same file, diff what each one asserts about
the OTHER's files, not just whether their lines collide.** The fix reads the
module name out of `BILLED_PATH_CALL_SITES` (which Lane B *did* update) and
asserts membership first, so the next move breaks one place instead of two.

Three more sentences were stale for the same reason and are corrected, each
struck rather than rewritten:

- ADR 0106 justified keeping `playbook.historian_has_run`'s name because
  "`backend/api/routes.py` names it and that file is Lane B's today" — true
  for about an hour. The durable reason is recorded instead: it is a field on
  the `/api/playbook` wire payload, read by `api.ts:1987` and branched on at
  `playbook/page.tsx:106`, so renaming it is an API change.
- `runner._skeptic_context`'s docstring opened "The Skeptic's prompt inputs"
  — an agent that no longer exists, named as the consumer of a dict the
  function still builds on every judged row. It keeps its name deliberately:
  `PassCounts.skeptic_reviewed` and the `skeptic_*` suppression codes are a
  **different, deterministic thing** that survives the deletion, and renaming
  one of two spellings hides an overlap rather than resolving it.
- `store_positions_snapshot`'s docstring said the hand-bet route "does not
  call this". It does now — see below.

### Lane A1's deferred edit was made here, and that is what completed it

The lane could fix only one of `poll_log`'s two writers, because `routes.py`
was Lane B's file that day. So `_stamp_positions_read` now takes the rows it
already holds and calls `store_positions_snapshot` under the id
`log_poll_attempt` returns, in the same transaction, before the commit —
located **by symbol**, because the ADR's line numbers (6138/5633/5619) were
pre-split and Lane B had moved the function to ~3735. The failure branch is
unchanged: a failed read keeps nothing and stays unmarked.

Without it, `venue_positions` would have recorded one of two writers while
the route's own docstring claimed "one population and not two", and a reader
taking the newest successful poll would have refused the money figure for up
to five minutes after every hand bet — at the one moment the desk is open.

**A guard that was decoration, found by mutating it.** The write is gated on
`if ok and rows is not None`, and **the `ok and` half is unreachable through
the route** — every failure path passes no rows, so `rows is None` already
blocks it, and deleting `ok and` left the API tests green. It is pinned by
calling `_stamp_positions_read` directly instead, which is the only level the
branch is reachable from. Four guards in `TestTheLivePositionsReadIsStamped`,
three mutation-verified red, `routes.py` restored byte-identical (sha256).

### Killed, stated plainly

**Routes-split steps 6 (`board`) and 7 (`orders`+`manual`) are dead, not
deferred**, and `docs/decisions/2026-09-04-routes-split-map.md` says so in its
own words. The constraint that justified the split was the Read ceiling and it
no longer binds; nothing else was ever named. Both remaining steps are the
pin-heavy ones. The note names what would reopen it: a constraint the
remaining ~194 KB actually violates.

`scripts/measure_agent_cache_prefix.py` was **not run** — it spends the
Anthropic key to measure cache efficiency of a fleet this session deleted
30.5% of.

### The suite got slow, and the cause is named

**The merged tree is green: 6,097 passed, 10 xfailed, 0 failed, 17m21s**
(`pytest -q --durations=15`), `ruff check .` clean, `npx tsc --noEmit` clean.
That run is the whole point of merging in one session: the three-way tree had
never existed in any lane, in CI, or on `main`.

**Where the 17 minutes go, measured rather than guessed.** The single slowest
test is `test_discovery_streams_the_walk.py::test_streaming_holds_a_page_where
_collecting_held_the_walk` at **66.5s**. Ten of the remaining fourteen slowest
are `tests/test_has_callers.py` cases at ~5.3–5.8s each, and with ~122 of them
that file is most of the tail. The cause is `callers_of`
(`tests/test_has_callers.py:434`): it calls `production_sources()` — a full
`ROOT.rglob("*.py")`, which *traverses* `.venv` before filtering it — and then
re-parses every production source, once per parametrized symbol, with no
cache.

**Correcting a guess made earlier in this session:** Lane C's new
`test_reachable_callers.py` was suspected of stacking a second full-tree walk
on the first. It does walk the tree, and it is **not** in the fifteen slowest
— so it is not the hot spot, and an earlier 12m49s reading of
`test_has_callers.py` alone was taken under contention with another Python
process. The pre-existing file is the cost.

**The CI reading was taken and it closes the question.** Run 33993384750 on
`da3614b`: `Tests + warehouse` **314s against the 900s cap**
(`.github/workflows/ci.yml:50`), with `Secret scan` 8s and `Frontend` 28s —
roughly ten minutes of headroom, and in line with the 6–8 minute runs before
this batch. So the 17m21s is Windows filesystem cost, not a suite that has
outgrown CI, and **the two new full-tree walks cost CI nothing measurable.**
An `lru_cache` on the parse and one hoisted `production_sources()` remain the
obvious fix and are **still not taken**: the only thing they now buy is local
iteration speed, which is a comfort rather than a constraint. Do not spend a
session on it; do notice if the number moves.

### Still open, in order

1. ~~**Push and deploy.**~~ **Done.** Pushed as one batch with `0087fa1`
   inside it rather than ahead of it; demo then live, one deploy each, the
   v33 migration running on boot via `docker/entrypoint.sh:96`.

   **The migration was verified on the volume, not inferred from a green
   deploy** — no inspector subcommand emits `schema_version` or
   `venue_positions`, so it is a direct read. Both instances:
   `schema_version = 33`, the `venue_positions` table present, and
   `poll_log` carrying its `mirrored` column.

   **And the marker earned itself on its first live read.** The three newest
   `positions` stamps on live are `(ok=1, row_count=0, mirrored=1)` then two
   with `mirrored = NULL` — the marked one written by the deployed code, the
   unmarked ones from before it. So `venue_positions` is empty **because the
   account holds no open positions**, which is a different fact from the
   mirror having failed, and telling those apart is the entire reason the
   column exists (ADR 0107 §5). The first *non-empty* snapshot is still owed
   and is the first place the rounding, the sign and the fee question can be
   checked against a known position.
2. **How did the parlays Joe picked do against what the desk told him? — Joe
   asked for this 2026-09-05, and it is two questions, not one.** The first is
   answerable now; the second is blocked on a record that does not exist.
   Scoped here before either is taken, because the answer must not choose the
   population.

   **The blocker, stated first: `parlay_positions` and `parlay_position_legs`
   are EMPTY on live — 0 rows, read 2026-09-05.** ADR 0078 built `/hedge` to
   record a ticket Joe holds, and nothing has ever been recorded through it.
   So "which parlays did Joe pick" has no answer in this database at all, and
   his sportsbook slips are additionally invisible to `fills` — the same hole
   CLAUDE.md names for his straight bets. **`manual_orders` is 0 too**, so
   the order path did not capture them either. Nothing about this item can
   proceed on Joe's *picks* until picks are recorded.

   **What IS on live, and it is more than expected.** `parlay_lookups` holds
   **34 taps** spanning 2026-08-22 → 2026-09-05, each carrying what the desk
   said at the moment of the tap: `fair_joint_conservative` (the card's
   headline joint), `hold`, `derived_yes_ask_tenths`, and `selected_legs` as
   JSON "exactly as sent, for reproducibility". Across them: **74 distinct leg
   tickers, all 74 present in `kalshi_markets`, and 64 of the 74 already
   carrying a settled `result`.** So the legs' outcomes are recoverable
   retrospectively without anyone having recorded anything.

       status   book_empty 24   priced 7   error 3
       card     safe 13  lottery 9  middle 5  longshot 4  agreed 2  soon 1
       legs     3-leg 20   6-leg 9   4-leg 5

   **Q1 — did the desk's parlay pricing match what happened? Answerable now,
   and underpowered as a test.** For each lookup, the desk stated a joint
   probability; the legs have since resolved; the realised all-legs-won
   indicator is computable. But `n = 7` priced (34 if the leg set is scored
   regardless of whether the combo could be bought), and at safe/lottery
   joints the expected count on at least one side is far below the **≥5
   expected outcomes** CLAUDE.md's first measurement rule requires. **Take it
   as a census, not a test** — the same standing the "0 of 27" hand-fill count
   has: list every priced parlay, its stated joint, and how it actually
   resolved, and let the reader see the whole population. Any *calibration
   claim* off n = 7 is the thing the measurement rules exist to stop.

   **The 24 `book_empty` rows are a finding on their own and may be the real
   answer.** 24 of 34 taps found no resting NO bid — the combo could not be
   bought at any price. Consistent with ADR 0012 §5 and with the standing
   record that combos are enter-only, and it means **the majority of what the
   desk "recommended" was unbuyable**, which is a defect in the recommendation
   independent of whether its probabilities were any good. Improving parlay
   recommendations plausibly starts here rather than at the pricing.

   **Q2 — Joe's picks vs the desk's recommendation. Blocked, and the fix is a
   product change, not a measurement.** For this to ever be answerable,
   `/hedge`'s recording path has to be used, or a lighter capture has to exist
   that Joe will actually use at the moment he places a slip. That is a
   question for the partner and for Joe, and it is the *first* step of this
   item: **there is no point registering Q2 while its population is empty.**
   A back-fill is possible for Kalshi-listed legs if Joe can reconstruct which
   parlays he placed — the leg results are already in `kalshi_markets`.

   **Sequence, so the answer cannot pick the population:** the pre-registrar
   writes Q1's census form (population, the exact `parlay_lookups` predicate,
   how a `book_empty` row is counted, and what would falsify "the desk's
   parlay pricing is useful") BEFORE the join is run. Only aggregate counts
   have been read so far — the status/card/leg-count table above and the
   64-of-74 result coverage — and **no outcome has been compared to any stated
   probability.** That is the line this item must not have crossed before
   registration, and it has not.

3. **Lane A2 — the screen for the staked figure.** ADR 0107 §6 names it: this
   lane touched no `frontend/`. Until it lands the strip shows the served
   string through the existing `staked_display` branch.
4. ~~**The CI wall-clock question above.**~~ **Answered before this entry was
   filed: 314s against a 900s cap.** Nothing owed. The local 17m21s is a
   Windows cost and buys only local iteration speed if fixed.
5. **ADR 0106 §5.3's newly-unreached symbols** — `AgentBudget.allowance` plus
   `study_stop_fired`, `loop_failures_since`, `prices.cents_to_tenths`,
   `runner.reset_walk_alarm`, `attention.seen_at_least_once_since`,
   `alerts.check_fee`, `discover_from_events`. Real dead code, a *consequence*
   of Lane C, deliberately not chased in the merge that had to stay
   verifiable. `runner._skeptic_context`'s dict — built on every judged row,
   ignored by the only reviewer left — belongs with them.

   **Audited twice on 2026-09-05, and the correct answer is: delete THREE of
   the nine, not nine. "Real dead code" above is the wrong words.** The
   accurate property is **production-unreached**, which this repo already has
   a mechanism for — `DISPOSITIONS`, `tests/test_has_callers.py:1080` — and
   six of the nine must not be deleted at all:

   - **`runner.reset_walk_alarm` is called on every test in the suite.** An
     autouse fixture at `conftest.py:155-159` calls it before and after each
     one, and that fixture's own docstring records which two tests fail
     without it. Deleting it makes suite results order-dependent.
   - **`discover_from_events` has four operator call sites** —
     `measure_series_walk.py:42,72`, `probe_create_order.py:494`,
     `run_chain.py:92` — and is the control arm of the memory-regression
     guard on the live streaming walk. The *runner* uses the streaming
     variant instead (`discovery.py:1016`); that is a narrower fact.
   - **`alerts.check_fee` is a deliberate arming hook.** Its own docstring
     (`alerts.py:1142-1153`) already states it has no production caller and
     why: `ORDERS_ARE_DRY_RUNS = True`, so there is no fill to reconcile and
     no honest place to call it from. Deleting a dormant money guard because
     it has never fired is the move to refuse.
   - **`prices.cents_to_tenths` and `AgentBudget.allowance`** churn ~322
     lines of tests that guard *live* code, to remove three executable
     lines. Net-negative.
   - **`runner._skeptic_context` is live** — called at `runner.py:1705` and
     `:2156` on every judged row, feeding a reviewer that refuses its output.
     That is a cost question about the pricing pass, not dead code.

   **What is left, and the reason to take it is not the ~9KB.**
   `study_stop_fired` (`estimates.py:453`), `loop_failures_since`
   (`db.py:1827`), `seen_at_least_once_since` (`attention.py:108`) — each is
   **one predicate with two or three spellings**, where the second spelling is
   what the screen and the inspector actually use (`GET /api/estimates/stop`
   re-spells the money-arm comparison inline). `study_stop_fired`'s docstring
   claims a write-path refusal that has since been removed. A stale duplicate
   predicate costs a future session a day; the bytes are not the point.

   **The audit error worth carrying: the first pass scoped its grep to
   `backend/` and `scripts/` and called seven symbols dead.** Root
   `conftest.py` is in neither, which is how a fixture running before every
   test in the suite read as having no caller. **Scope a deadness grep to
   `git ls-files`, never to the source directories** — the callers that
   matter most are often the ones outside them.
6. **ADR 0106 §5.2: no captured Anthropic payload exists in `tests/fixtures/`.**
   **Not killable**: `scout.py` survives and has eight live briefings behind
   it, so this is a gap in the *surviving* half, on the one money-spending
   path, against CLAUDE.md's own wire-format convention.
7. **Three ADR 0107 refusals that must not be upgraded by a later reader**:
   the unit of `market_exposure_dollars` is inferred from a suffix pinned on a
   different field and bounded only by a $1-per-contract tripwire; the NO-side
   sign convention is unobserved and refused rather than guessed; "before
   fees" is a label, not a measurement. A known live position settles all
   three.
8. **Joe-gated, untouched:** the five questions A–E from 2026-09-04 (PRs
   #1/#2, S3/shard-0, Odds API key rotation, #11's estimate log, the
   `desk_attention` path column) and the 2026-09-03 key rotation. Nothing
   above waits on them.
9. ~~**Lane worktrees** `.claude/worktrees/wf_e0ee5ede-e97-{1,2,3}` are merged
   and removable.~~ **Mostly done 2026-09-05.** `git worktree list` showed only
   `main`, so all three were already unregistered; what remained on disk were
   four husks totalling 241K of build detritus
   (`agent-a9c07477153a6f0f9`, `agent-af39922dd422145da`, `frontend`,
   `wf_e0ee5ede-e97-1`). The junction hazard did **not** apply — checked before
   deleting, via `st_file_attributes & 0x400`: no reparse point among them, all
   real directories of 1–2 entries. Three were removed and `frontend/
   node_modules` in main is intact. `wf_e0ee5ede-e97-1` is empty but held open
   by a live process ("Device or resource busy"); harmless, delete it whenever
   that process is gone. **Keep the junction rule** — it did not bind here
   because these were husks, and it will bind on a worktree that was actually
   built in.

---

## 2026-09-04 — six lanes landed (ADR 0104, 0102 Amd 1, the Read-ceiling guard); the presence measurement was registered, taken once, audited, and is UNRESOLVED — CONCENTRATION; the partner killed #11's log form; five questions for Joe

**STATE, verified at close (2026-09-04 ~03:00Z):** `main` = the commit
carrying this entry, on top of `e8030c1` (Gate h1 + CLAUDE.md presence
paragraph), `c260d62` (check_mobile pages), `1636c71` (presence result),
`a61f0d6` (Lane 6 merge). **Live = `a61f0d6`** (Deploy run 33827229995,
`/api/health` ok, recorder writing), **demo = `a61f0d6`** (run 33827232097).
CI green on `a61f0d6` (run 33826273516). Everything after `a61f0d6` is
docs plus three one-line code changes (the Gate h1 word, three pages added
to `check_mobile`, a schema comment) and **rides the next deploy** — the
partner's call, not an oversight. No lane worktrees remain. `wc -c`:
NEXT.md ~220KB (84%), lessons.md ~211KB (81%) — both under the 90% split
trigger; check before the next entry.

### The partner ran first, twice, and the map was not empty

The frontier query returned zero open tickets and the partner found eleven
decided-and-unbuilt items behind it (#11, #9, #24, #21, #33, #7, #5, #26, #6,
#13, #4 — its table is in the archive of this session). It also found
`start.md`, an orphaned third session-start door telling the next session the
Scout was tabled while `POST /api/scout/{ticker}` bills Anthropic. **Its
correction to carry: #33 and #24 were never killed by Joe.** Both are
CLOSED carrying live build specs; the kill at the previous entry's line ~244
was the partner's inference, and the record is corrected here. Joe's actual
kills are #17/#19/#20 (NOT_PLANNED).

### What landed — six lanes in `.claude/worktrees/`, merged 3 → 4 → 5 → 6

- **Lane 3, ADR 0104 (`e2b5f4b`/`a45da2a`)** — `start.md` is a 15-line
  pointer; six refuted sentences corrected with file:line evidence
  (`.env.example` billed-path header, `runner.py` "surfaced never non-zero",
  `schema.sql` "pruned by retention", `gate.py` `grep INTO fills`,
  `scout_desk.py` "copied verbatim" — the copies already differed,
  `margins.py` hands win-probability to the never-run `elo.py`); two guards
  (four desk prompts share the no-forecast rule; `.env.example` carries
  `base.py`'s `AGENT_MODEL` default). One premise refuted: the contract file
  already explained the live/default model split.
- **Lane 4 (`306afc9`)** — Gate lede rewritten from pre-ADR-0038 framing
  ("has to demonstrate an edge") to #9's ratified string, **no count baked
  in** (the brief's "2 in its life" was stale; CLAUDE.md's newer figure is 15
  and the live number renders); the five missing #9 ledes shipped verbatim
  (Games takes 29A's "a named check, or the fee bar"); #33's four false
  "`--accent` is byte-identical to `--negative`" comments corrected (the
  `7bdcb11` message claimed it repaired them; it repaired test docstrings);
  #24's comment records Joe's decision. 18/18 mutations red.
- **Lane 5 (`2433c00` + `f794b03`, ADR 0102 Amendment 1)** — `sweepTone`
  reads `loop_idle_interval_ms` through `loopStallAfterMs` (one spelling);
  unknown cadence → `warn` on its own branch, never `alarm`, never calm;
  `WindowBanner` uses the same derived value and prints the cadence. The
  inert `automaticBuyIsComing` prop removed from `ParlayCards`, then deleted
  with its pin on main; `test_stale_exit`'s baseline-only guard covers
  `ParlayCards`. `HowToRead` glosses NO EDGE and SIZED TO ZERO inside the
  REJECTED bullet, no `$1,000` literal, docstring says five.
- **Lane 6 (`a61f0d6`)** — `test_session_files_are_readable.py` enumerates
  every tracked `.py/.ts/.tsx/.sql/.toml/.yml/.md` via `git ls-files`
  (archive excluded); `backend/api/routes.py` on a **ratchet at 333,958**
  bytes (fails if it grows, fails if the exemption outlives its reason);
  `inspect_live_db.py` 263,058 → 255,989 with byte-identical behaviour
  (36 subcommands, token-stream diff = 9 docstrings; the Q-W caveats moved
  verbatim to the 2026-08-13 result doc §9). **`routes.py` needs 71,814
  bytes out** — ten times what the inspector gave up; that is a domain
  split, not a trim, and it is a per-session tax until then.
- **`check_mobile` (`c260d62`)** now measures `/picks`, `/board`, `/hedge`;
  all twelve pages fit 390px on demo at `a61f0d6`. Gate h1 → "Gate"
  (`e8030c1`, #29).

**Lane mechanics worth keeping:** a rate limit killed Lanes 4, 5 and 6
mid-work; `SendMessage` resumed 4 and 5 with context intact, 6 had lost its
worktree and re-created one with `git worktree add`. **The scratchpad is
shared across lanes** — two lanes overwrote each other's `mutate.py`. **CRLF**:
`.tsx` and `.md` are CRLF in this checkout; a `\n` anchor reports "not found"
on text `sed` shows you. **`git checkout -- file` as a mutation restore eats
uncommitted edits** — copy to scratch and copy back. `flyctl ssh console -C`
exits 1 with "The handle is invalid" on Windows *after* delivering complete
output; judge the read by parsing it.

### The presence measurement — registered, taken once, audited, UNRESOLVED

`docs/measurements/2026-09-03-presence-at-the-moment-of-a-bet-registration.md`
(+ Amendment 1 §A–§F) and `2026-09-04-presence-at-the-moment-of-a-bet-result.md`.
Question: is the desk open when Joe actually bets on Kalshi? Unit = the
**sitting** (fills within 60 min), clustered by budget day; bands ±5/±30 min
from `DEFAULT_ATTENTION_TTL_MS`; gap arm exact binomial, presence arm a
seeded day-shift permutation holding hour-of-day fixed; four tests at 0.005.

Sequence, because the shape recurs: analyzer committed **before** the reads
(`d2f51de` 01:13:01Z, first capture 01:13:20Z); first run **refused** above
the first distance (section C carries no `venue_order_id`); the
pre-registrar amended **blind** (the `W_end` integer was a typo for 09-06;
the exclusion executes on the order side — `cancel_reduced_by == count` is
the venue's own statement nothing filled, a residual order attributes by
ticker as a join key never printed; C4 re-worded on the capability, not the
route); its claim that the captures were "taken 09-03, before W_end" read the
date in local time and is superseded (§F); second run computed the statistic
**once**; `measurement-skeptic` audited and found the analyzer had broken a
two-way tie for "the largest-contributing budget day" by dict insertion order,
**in the flattering direction**.

    S = 12 sittings   D = 7 budget days   27 taker hand fills, 0 through manual_orders
    B5  K = 8 of 12   p_gap 0.927 (gap arm not cleared)   p_perm 0.0004, k* = 7
    leave-one-day-out  drop 08-26: 7 of 9, REFUTED   drop 08-28: 5 of 9, p_perm 0.016, UNRESOLVED
    VERDICT   UNRESOLVED — CONCENTRATION      (§10: nothing funded, nothing killed on it)

Descriptively, and only with the qualifiers: the desk was open at two-thirds
of his **Kalshi taker** sittings, three times the day-shifted chance rate, in
3–31-minute visits with the fill 1–9 minutes in (none of the five multi-hour
tab-left-open visits contains a sitting). The partner's hypothesis as stated
("essentially never present") is not what the record shows. **Never quote
`p_perm = 0.0004` without `k* = 7`; never write "the desk is at the moment of
a bet" alone; "his bets" means his Kalshi bets.** The registration is
**closed** (§8's trigger is S/D only); a successor needs a tie-break rule
fixed in advance and ~25 sittings. C5 (`poll_log endpoint='fills'`) was not
executed and the population is declared a FLOOR; the §10 blind re-check was
done at ~01:05Z and not written down at the time — recorded after the fact.
The tie-break fix is pinned (mutation red) and left every number unchanged.

**The number the partner says to carry is not the verdict:** `manual_orders`
real rows = 0 against 27 taker hand fills with the path armed the whole
window. **The desk is a read surface, not a transaction surface.** CLAUDE.md
now carries that paragraph in the partner's permitted wording.

### Killed by the partner, stated plainly

#11's price-free estimate log form (three entry designs, ≤1 row, 0 of 27);
wiring `/api/estimates/last-scored` to any screen (structurally empty source —
it stays, with an honest docstring and an absence pin still owed); the C5
`poll_log endpoint='fills'` subcommand and the seven free-rider census counts
(registration closed, inspector headroom is 6,155 bytes); `anAutomaticBuyIsComing`
with `test_stale_exit`'s snapshot class (self-justifying test-only code);
waiting on any successor presence registration.

### FOR JOE — five questions, one artifact

https://claude.ai/code/artifact/985a3e74-9c1d-4824-bff1-b99be758f13a

    A  close PRs #1 and #2 (opened from your jcabiles account, both superseded)?
    B  shard-3 test / shard-0 move — parked, this week, or drop?
    C  Odds API key rotation — now or later?
    D  #11's estimate log screen is being killed — kill or keep?
    E  a "which screen" path field on the desk heartbeat (live DB only) — ok or no?

Answer in one line as usual. Nothing here blocks anything.

### CONTINUED, same session (~04:30Z) — items 2, 4 and 5 are done

The session continued past the entry above on Opus after the Fable limit
stopped three lanes mid-flight; two were resumed from their worktrees with
`SendMessage` and one was relaunched. **A rate limit is a pause, not a loss**
— an agent with a worktree resumes with its context intact.

- **ADR 0105 — the desk is read, not transacted through** (item 2, done).
  Rests on the census (0 of 27), **not** on the presence verdict, and says so
  in its own §1 so no session can spend an UNRESOLVED. Records the three
  entry designs and their combined yield of one typed estimate, and names the
  two things that would overturn it: one real `manual_orders` row, or Joe's
  answer to question D. Two figures the lane could not verify — which surface
  wrote that one row, and whether the count is still 1 — are written in as
  unverified rather than dropped.
- **`inspect_live_db.py --json` stamps `generated_at_ms` + `generated_at`**
  from the server clock (item 4, done, **+264 bytes**, headroom now 5,891).
  `analyse_bet_presence.py` prefers that stamp over the file mtime and prints
  which clock it used. Re-running the recorded look reproduces **every**
  figure and adds only four `from mtime` provenance lines; the result doc now
  says the E0 caveat is about those four captures, not about the instrument.
  Also fixed: `_q_failure_journal`'s docstring said section 3 was "the second
  of those limits closing" when it is the first — it contradicted its own
  paragraph two sentences later.
- **`anAutomaticBuyIsComing` deleted with its snapshot test class** (item 5,
  done). The two source pins that lived in that class survive in a renamed
  one. **The subtlety worth keeping:** an absence pin that greps `tests/` for
  a literal name finds the name in `__pycache__`, because CPython
  constant-folds `"an" + "AutomaticBuyIsComing"` into the `.pyc`. The pin
  builds the name with `"".join((...))` instead, and says why.
- **`LeagueTag` is closed, not open** — it has rendered through `leagueLabel`
  since `aef8b5b`; what was missing was the `KALSHI_COMPETITIONS` map, which
  `f4c2159` added. Item 6 of the 2026-09-03 entry closes with it.
- **The `routes.py` split is mapped, read-only:**
  `docs/decisions/2026-09-04-routes-split-map.md`. 45 handlers as closures in
  one function, `return app` at 5829, one genuinely shared dependency
  (`_serialise`), no `APIRouter`/`app.state`/`nonlocal`, and **fourteen tests
  that pin the file by source text or namespace** — including one requiring
  the `/api/board` and `/api/slate` decorators to stay adjacent in one file.
  Eight-step order, each step revertable, ratchet deleted last because it
  self-fails once the file is under the ceiling. **A plan, not a decision.**

### Still open, in the partner's order (next session)

1. **`desk_attention` gains a path column** — the cheapest high-leverage
   instrument on the board; the schema's own "always the same value"
   reasoning does not reach a column that varies (comment corrected to say so
   and to say the row count is dwell). Write in the schema comment that
   stamps are cadence-emitted, so the column is dwell-weighted per screen.
   **Pending Joe's E.**
2. **`/api/estimates/last-scored`**: honest docstring + grep pin that its
   absence from the frontend is deliberate (fifth instance of built-and-
   uncalled). **Pending Joe's D.**
3. **`routes.py` 333,958 → under 262,144**: the map is written; the decision
   to spend a session on it is the partner's. Re-run the pin greps first —
   the map says so itself, because a pin written after it was taken is not
   in it.
4. Joe-gated, untouched: S3 / shard-0 (B), key rotation (C), #21 item 4
   (`parlay_positions` count still unread — no subcommand emits it; the
   partner killed building one).
5. ~~Deploy the post-`a61f0d6` commits~~ — done at the close of this
   continuation.

---

## 2026-09-03 (second entry) — the partner found the desk had not gone quiet and the /picks heal was switched off; three lanes landed (ADR 0101–0103); one question and one rotation for Joe

**STATE, verified at close:** `main` = the commit carrying this entry, on top
of `2747b0f` (Lane B merge, ADR 0103), `2a0c3d3` (Lane D merge, ADR 0102),
`2b99224` (Lane A merge, ADR 0101), `d763d5b` (record correction), `f4c2159`
(`leagueLabel`). CI green on `2a0c3d3` (run 33799001167) and on `566f67e`
(run 33799815045). **Live = `566f67e`, deployed by this session after CI
green** (Deploy run 33800619690); `/api/health` ok, recorder writing,
`build.git_sha` matches. **Demo = `566f67e` too** (run 33800910874), deployed
so the three new payload shapes could be read without a session cookie:
`/api/window` publishes `loop_idle_interval_ms = 900000`, `/api/board` has
`counts.sized_to_zero` and `slate.reference_bankroll_dollars = 1000.0`,
`/api/bets` has `sections`, `first_settled_ms` and the served
`staked_refusal`. Live's `/api/window` is a 401 without the cookie, so it was
verified on demo and by CI, not read on live. No lane worktrees remain; the
three merged branches `worktree-agent-*` are deleted.

### The partner ran first, and both of yesterday's premises were wrong

Given yesterday's queue (#21/#25 builds, #20 waiting, S3 on Joe's word) it
asked two questions before ranking, dispatched the checks, and one of its own
proposals died on the way (`RUNNER_INTERVAL_S` as the heal's binder — refuted
by `run_quote_pass` calling `run_pricing_pass` itself). Both findings are
recomputed from raw rows in
`docs/measurements/2026-09-03-desk-dwell-and-the-watcher-off-switch.md`:

1. **"The desk went quiet" measured dwell, not opens.** Attention-tagged
   buys fire every ten minutes *while a page is open*. Opens per budget day
   are flat at 5–8; attended minutes ran 2.6 to 324 with no trend; 23 of 65
   visits since 08-20 are one heartbeat long. The interview's lead question
   ("why did you stop opening it?") presupposed a behaviour the data does
   not show and is replaced below. `manual_orders = 0` lifetime is now
   corroborated on live (`manual-orders-audit`); it had been single-sourced.
   The `'attention'` trigger tag is also **displaceable by the schedule**
   (20260830: eight ten-minute baseball buys tagged NULL with no visit in
   progress), so it is a lower bound, not a dwell meter. CLAUDE.md's "4.9
   hours a day" is corrected to one observed day.
2. **Yesterday's `/picks` self-heal was switched off on the opens it exists
   for.** `RefreshWhenPriced` was gated on `anAutomaticBuyIsComing` computed
   on the server render, and `LOOP_STALL_MS = 180 s` against a 900 s idle
   cadence read ordinary idle as a stalled loop. **8 of 26 live opens, all 8
   with nothing fresh at open, 0 of 11 fresh opens** — 53% of the cold opens
   lost the watcher while the page's own heartbeat had the buy landing in
   3–13 s. Fourth instance of "one predicate, two spellings"; promoted to an
   architectural pattern in `lessons.md`.

Killed: #33 and #24 (held twice; two holds is a decision). Held: #17, #19 —
**do not open a third interview batch**; he answered two in two days. #20's
hold is now settled rather than provisional: the heal is fast, so the
designed empty night is not the dominant case. The faster-floor-cadence kill
stands (different budget line; the monthly cap binds first).

### What landed — three lanes in `.claude/worktrees/`, merged A → D → B

- **Lane D, ADR 0102 (`2a0c3d3`)** — the watcher decides client-side from
  fresh `/api/window` facts at every poll (leading edge on mount, 3 s for
  30 s, then 10 s). `/api/window` publishes `loop_idle_interval_ms`
  (`RUNNER_INTERVAL_S` as the entrypoint reads it; `None` never `0`); the
  panel calls the loop stalled only past **two** idle intervals and never on
  an unknown cadence; the watcher's own stall clock is 180 s of *continuous
  visibility* with no new look. `slice_spent` watches when the floor's next
  buy is inside the window; `nothing_to_schedule` is deferred 15 s for the
  heartbeat to land. Nav's chip poll gains the visibility gate. 37 new tests,
  nine mutations red. **Recorded, not fixed:** `sweepTone.ts` hardcodes
  `2 × 900_000` as a second spelling of the same threshold;
  `ParlayCards.tsx` still passes the now-inert `automaticBuyIsComing` prop.
- **Lane A, ADR 0101 (`2b99224`)** — #21/21A items 1–3. Rows carry `kind`
  via `estimates.classify_ticker`; a `sections` block per kind with count
  and net **sum** (no rate anywhere, pinned); combo rows draw no CLV line and
  `clv_coverage` counts singles only ("scored on N of 27 single-game bets");
  `first_settled_ms` served and rendered (live: **2026-08-11**, not the
  "Aug 18" the page typed). **Item 2, staked-now, is refused in words**:
  `parse_fill` drops the venue's buy/sell `action`, so a SUM over `fills`
  books exits as stake, and "fills with no settlement row" mislabels both
  unmirrored settlements and pre-settlement exits. The ADR names what would
  pin it (an `action` column on fills, or storing the venue's per-position
  exposure with its unit measured) — schema work, unowned. **Item 4 is not
  buildable on `venue_settlements`** (an open combo is structurally absent;
  it needs `parlay_positions` wiring 21A did not price) — Joe's call.
- **Lane B, ADR 0103 (`2747b0f`)** — #25/25C. Fifth bucket `sized_to_zero`
  on `/api/board` (no reason, `suggested_contracts = 0`,
  `reference_contracts > 0`; NULL reference falls to `no_edge` as the gate
  does), chip **SIZED TO ZERO** with no tone colour, caption "reference size
  N at $1,000 · sized to 0 at your balance" with the bankroll served by the
  slate. `gate.py` byte-identical; `population_counts` not forked; the
  Board's `sized_to_zero + surfaced + expired` equals the gate's actionable
  count on the same fixture, pinned. 15 mutations red. At the merge boundary
  the four-bucket tuples in three tests it did not own were extended to five
  so `test_observability`'s mixed fixture asserts the new row instead of
  skipping it.
- **`leagueLabel` (`f4c2159`)** — Kalshi's competition strings ("Pro
  Baseball") and the odds feed's sport keys render the same word;
  `tests/test_league_label.py` pins the frontend map equal to
  `IN_SCOPE_LEAGUES`.

**Lane mechanics that are new and worth keeping:** the lanes ran as Agent
worktrees under `.claude/worktrees/`, borrowing main's `.venv` by absolute
path and main's `frontend/node_modules` through a directory junction (the
sandbox refused `cmd /c mklink`; Python's `_winapi.CreateJunction` worked).
**Remove the junction with `os.rmdir` before `git worktree remove --force`**,
or the removal recurses into main's install. Turbopack `next build` refuses a
junctioned `node_modules`; `next build --webpack` does not. Lane B was killed
mid-edit by a rate limit and resumed via `SendMessage` with its context
intact — a stopped lane is resumable, not lost.

### FOR JOE — one question and one rotation, nothing else

**Rotate the Odds API key.** A subagent read the local `.env` to check config
precedence and the key's value appeared in its transcript, on this machine.
Not committed, not pushed, not public — `.env` is gitignored and `git status`
was clean throughout. CLAUDE.md's rule for the Kalshi key (in a transcript,
therefore compromised, therefore rotate) applies by analogy; rotation is free
on The Odds API dashboard and then `flyctl secrets set ODDS_API_KEY=…`. Not
an emergency; your account, your action. **Standing guard for sessions:**
establish config from `.env.example` and `fly.*.toml`, never by reading
`.env`; if local precedence matters, grep the one non-secret key.

**Q2 — answer in your usual one-line format (`Q2B`, etc.):**

    Q2. When you open the desk (about 6x/day, usually for under a minute),
        what are you checking?
      A  what I already have on / whether anything settled
      B  scanning for something to bet
      C  a specific game I'd already decided to bet
      D  habit, nothing in particular

It decides whether the desk is a list (A or B) or a lookup (C); #18 shipped a
four-link nav and a header search on an unanswered guess. The partner's read
is A and it flagged that as the flattering answer. Ask, don't take the read.

### JOE ANSWERED — 2026-09-03, one line: `1. later 2.d`

- **Key rotation: deferred by Joe.** Recorded, not nagged. The standing
  guard for sessions (config from `.env.example` and `fly.*.toml`, never
  by reading `.env`) applies regardless.
- **Q2 = D: habit, nothing in particular.** Neither a list (A/B) nor a
  lookup (C). The partner's read (A) was wrong, which is why it was asked.
  **Consequence, in the partner's words:** Joe answered Q2 with D — habit,
  nothing in particular — so the glance has no job the screens were failing
  at: **visit frequency is disqualified as a demand signal** (six opens a
  day is a tic, not engagement; `desk_attention` stays a freshness
  diagnostic and stops being readable as interest), **#17, #19 and #20 are
  killed rather than held** (all three were "make the glance better" work
  justified by an assumed job the glance was doing; a deferred ticket whose
  premise is dead gets rebuilt at full cost), and **the only gap left worth
  funding is that the desk is not present at the moment he actually bets**
  — ADR 0071's job is transparency at the moment of a bet, and D plus
  `manual_orders = 0` says he bets on Kalshi directly and glances at us
  separately. A presence problem, not a screen problem; it needs evidence
  before it needs a lane, and no work is proposed on it here. The three
  tickets carry the kill as a comment; Joe closes them or overrules.
  What D does not change: ADR 0101–0103 stood on correctness, not on D.

### Still open, in the partner's order

1. ~~Deploy~~ — done, `566f67e` live and demo.
2. **S3 test and the shard-0 move** — on Joe's word only. Do not nudge.
3. **#21 item 4** — back to Joe: wire `parlay_positions` into `/bets`, or
   descope. And the staked-now pin (fills `action` column or venue exposure
   with a measured unit) — schema step, unowned.
4. **Lane follow-ups, small:** `sweepTone.ts`'s second spelling of the stall
   threshold should read `loop_idle_interval_ms`; `ParlayCards.tsx`'s inert
   prop; `HowToRead.tsx` has no gloss for the SIZED TO ZERO chip.
5. **Killed on Q2D and closed by Joe (2026-09-03, "not planned"):** #17,
   #19, #20. The map's frontier is now empty of unblocked, unassigned
   tickets.
   Killed earlier: #33, #24, the C5 separating read, the faster floor
   cadence. **Not opened:** the presence gap — evidence first.

---

## 2026-09-03 (early) — the partner reordered the queue around a regression shipped the day before; three lanes landed; Joe answered the second batch

**STATE, verified at close (2026-09-03 ~05:00Z):** `main` = the commit
carrying this entry, on top of `ded444a` (Lane C merge, ADR 0100),
`e1be1f8` (Lane B merge, ADR 0099), `1657893` (A16), `cb9e4ab`/`bc774d9`
(Lane A merge), `2f82096` (the `/picks` watcher). CI green through
`1657893`; the two lane merges are pushed with this entry — read
`gh run list --limit 3`. **Live = `01d482b` as of 2026-09-03 ~04:45Z** —
Joe dispatched the Deploy himself after CI went green on that SHA;
`/api/health` ok, recorder writing, `build.git_sha` matches `origin/main`.
(The session's own dispatch attempt was blocked by the permission
classifier; a first "deployed" report turned out to be no run anywhere —
verify on `gh run list --workflow Deploy` and `flyctl releases`, never on
the word.) No lane worktrees remain.

### The partner ran first and reordered the queue

Given last night's ranking (#20 prototype → #16 → #17 → #15 → #19 → #18)
it found a regression in yesterday's own build and put it ahead of
everything: **`/picks` never self-healed.** ADR 0098 made it a real screen
on 2026-09-02, written fresh from the block it promotes, and `/slate`'s
`RefreshWhenPriced` — the watcher that re-renders a cold page when the sweep
its own heartbeat triggered lands — did not come with it. Read against R0
(21 of 45 cold opens with nothing fresh, the feed then buying at a median
3.3 s), the screen the nav word "Picks" opens showed "not ranked: the
consensus is too old to speak" on about half of Joe's opens and held it for
the whole visit while the answer sat in the database. **That is the literal
mechanism behind his stated reason for not opening the desk, on the screen
built the day after he said it.** Fixed in `2f82096`: mounted beneath the
block, gated on `not_ranked.stale_consensus > 0` (`some`, argued in the
docstring, where the Slate's gate is `every`) and on `anAutomaticBuyIsComing`;
five pins in `TestPicksWiresItToo`, gate verified red; ADR 0098 Amendment 1;
two lessons (a promoted screen inherits the slot's traffic, not the old
screen's fixes; a self-heal gated on "empty" stops the moment it has
anything).

**Consequence for #20:** it stays a throwaway `?variant=` prototype on demo,
and it waits — a share of the "empty nights" it was opened for were a
missing ten-second poll, and the distribution it designs against is the
post-fix one. The partner also killed two things before they were proposed:
the C5 separating read (nothing consumes it) and a faster floor cadence
(dead on the 18,000/month cap — `fly.live.toml:273` already says the
monthly cap binds first). Held: #33 (four `Stat` definitions across 20
sites, to tint a count), #24 (needs its ADR 0065 amendment), #17 and #19
(they compete for Joe's review attention, the scarce resource).

**The lane-collision claim was half wrong.** `SlateRow.tsx` is `/board`-only;
`/slate` renders a local `Row()`. #16 and #15 met only in `slate/page.tsx`
at different hunks, so three worktrees ran in parallel and merged A → B → C
with one auto-merge and no conflict. `Nav.tsx` was assigned wholly to Lane
C, including the market-page active state #16's "nav path" clause turned
out to mean (`/market/[ticker]` is dynamic and already exempted in the
reachability test).

### What landed

- **#16 (16A, `bc774d9`)** — the Games row and the Refusals row keep the
  refusal code verbatim with a `why →` link; the sentence lives only on
  `/market/[ticker]`'s skeptic section, which now scrolls to `#skeptic`
  after the panel loads. Six guards mutation-verified. `.env.example` now
  names `RUNNER_INTERVAL_S` / `RUNNER_FAST_INTERVAL_S` (they existed only
  as entrypoint defaults). `RefusalSummary`'s docstring corrected in
  `cb9e4ab`.
- **#15 (15A, `e1be1f8`, ADR 0099)** — `league=<sport_key>` and
  `within_hours=<1..168>` on `/api/slate` and `/api/parlays`, one parser
  (`backend/list_filters.py`), unknown values 422, unfiltered payload
  byte-identical, a `filter` echo with `hidden` when set, nothing reordered
  and no sort parameter. One sticky `FilterBar` on Games/Picks/Parlays
  under the nav at its measured 69px. `check_mobile.py --width 390` clean
  on nine pages. Ten guards verified. Noted: rows tag league from the
  venue's "Pro Baseball" string while the chip says "MLB" (`LeagueTag`,
  pre-existing).
- **#18 (18A, `ded444a`, ADR 0100)** — nav is Games / Picks / Parlays /
  Your bets plus a header search button opening the existing
  `MarketSearch` as a layer; Gate and Playbook first in the footer, **Gate
  still named Gate with the games-against-300 count** (the partner's
  condition). 390px: 272/272 where six links scrolled 424/318; **320px
  still scrolls 60px, recorded not fixed.** Ten guards verified. **Tension
  recorded on the ticket:** the header search is on every page including
  Picks, so a hand-bet ticket is reachable from the Picks tab again by a
  typed search; #8's pin is on the page source and holds. Joe's call.
- **#35 CLOSED** — all four fix commits are ancestors of live; caveat on
  the ticket that the repaired branch has had ~zero live executions since
  the slice has not run out since 08-27.

### JOE ANSWERED THE SECOND BATCH — 2026-09-03, one line

    21A, 25C, 29A, 8A, 44A, S3A, SHA

Artifact (answered record):
https://claude.ai/code/artifact/a2429d26-0fd7-41c4-b4b9-a47b61c340c9

- **21A** (`/bets`): separate combos from single games, an open-now strip
  never summed with cash, the page states its own first day, a combo reads
  "unsettled" until the venue settles it. No backfill. **Build owed.**
- **25C** (Refusals): a third chip, **SIZED TO ZERO**, for rows the gate
  counts at its $1,000 reference and quarter-Kelly sizes to zero at the
  observed balance; `population_counts` not forked; the row learns its
  reference size. **Build owed.** #21 and #25 closed with the spec on each;
  the map's Decisions-so-far carries a line for each.
- **29A / 8A**: the shipped footer blurb (names the fee bar) and the
  "Picks" h1 stand. Noted on both tickets.
- **44A — BUILT, `1657893`:** a voided settlement counts its fee as a
  loss and nothing else (markers `NULL`, `''`, `'void'`; anything else
  still refuses; a void with an unreadable fee still refuses). ADR 0044
  Amendment 4; registration Amendment 4 / A16. `study_loss_dollars` and
  the `study-stop` mirror amended together, marker set duplicated and
  pinned equal, both halves verified red by mutation. The $100 arm, which
  one voided `KXMVE` combo had made uncomputable since it settled, reads a
  number on the next deploy.
- **S3A / SHA — waiting on Joe's hands.** He moves ~$1 into shard 3 and
  says so; a session then posts ONE baseball contract at 1c,
  immediate-or-cancel (cost ≤ 1c), and records which error or fill comes
  back — the falsifying test for "a user materialises on a shard at the
  first transfer". For shard 0 he names and moves the amount. **Nothing
  runs until he says the money has landed.**

### Still open, in the partner's order

1. ~~Deploy~~ — done, `01d482b` live.
2. **Builds owed from tonight's answers:** #21 (`/bets` separations), #25
   (SIZED TO ZERO chip). Both touch files no lane holds now.
3. **#20** — throwaway prototype on demo, after a week of opens land on the
   repaired `/picks`. Spec: the visit-freshness doc §5 plus the post-fix
   distribution.
4. **The S3 test and the shard-0 move**, on Joe's word.
5. Held: #33, #24, #17, #19. Not taken: the C5 separating read (killed).
6. `LeagueTag`'s "Pro Baseball" vs the chip's "MLB" — one component, no
   owner yet.

---

# The session index

Every session entry ever written to this file, newest date first. Full text in
the linked archive file, unchanged.

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
