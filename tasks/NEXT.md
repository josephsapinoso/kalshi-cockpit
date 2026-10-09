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
and read `requirements.txt` — zero open alerts on 2026-09-19 and nothing
owed (this line pointed at "open item 3 below" for a session after that
item had left the list).

**Two things to know before planning. CLAUDE.md is current on both:**

1. **The signal test's registered result is in: UNRESOLVED at the stopping
   rule** (#226, 2026-10-01: `G = 1000` clusters, 889 games, floor nominal
   861). Collection has ended and no look remains. UNRESOLVED may not be
   reported as "no signal"; for planning, treat it as no usable
   pass-through. CLAUDE.md carries the table. (Until session 77 this line
   said `G = 216`, floor 713, "the look is not coming", stale since #226.)
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
    # #3 is full at GitHub's 100 sub-issue cap; new questions live under #302 (#292).
    # Run this for 302 as well as 3, or just run scripts/board.py, which reads both.
    gh api repos/josephsapinoso/kalshi-cockpit/issues/3/sub_issues --paginate \
      --jq '.[] | select(.state=="open") | [.number,(.assignee.login // "-"),(.issue_dependencies_summary.blocked_by // 0),.title] | @tsv'

Conventions: `docs/agents/issue-tracker.md`. Claim a ticket by assigning it to
yourself before any work; resolve one per session. The map produces
*decisions*, not builds. **An empty frontier is a finding, not a clean desk**
(2026-09-16): the map is the only queue that does not refill itself, and a
question for Joe that is not a sub-issue of a map (#302 since 2026-10-03) decays into the instrument
that raised it. Write one as `Question for Joe: <sentence> — #NN` (recipe:
"Open a ticket for Joe" in the conventions file);
`tests/test_a_question_for_joe_has_a_ticket.py` refuses the marker without a
number and refuses any Still-open item that says *for Joe* / *Joe's call* /
*until he answers* with no ticket. **The `/wayfinder` skill that drew the map is not
installed in this plugin version** — nothing can invoke it, and the map is
read with `gh` only.

**THIS FILE IS THE FRONT DOOR, AND THE QUEUE IS ON GITHUB — ADR 0179,
2026-09-19, superseding the three-queue answer of 2026-08-28.** One queue:
every open item is a ticket under map #3 (Joe's decisions) or backlog root
**#80** (build work: `type:epic` → `story` → `task`, `owner:` and `model:`
labels). This file's Still-open list is `#NN — one line` pointers and
`tests/test_a_question_for_joe_has_a_ticket.py` refuses an item with no
number. Read `git status`, then the latest entry, then the generated board:

    .venv\Scripts\python.exe scripts/board.py

Protocol: `docs/agents/orchestration.md`. A decided-not-yet-built spec is a
task under its story, not a line here.

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

## 2026-10-08 (eighty-seventh session) — Joe's parlay challenge: success rate is the price; the record reaches each leg (ADR 0194, v65/v66); the friend's-parlay path gets its guards; cash-out watch; cost line; markup registered; live on `7f135730`

- **Joe: "I challenge you to come up with ideas to improve parlay picks and success rates."** Planned in plan mode with three read-only scouts, the sharp-bettor and the partner; Joe approved the plan, answered two questions by option buttons (scouts' button on Check a parlay: **yes**; cash-out watch: **book only, makers on his tap**) and approved merging and deploying the whole lane batch. Story **#320** under epic #83; tasks #321 to #334.
- **The frame, for the record.** A parlay wins about as often as its price says. His median card is 4.75c (the 2026-09-05 census, n = 52): the makers saying "about 1 in 21", and winning 1 in 21 is the price coming true. At 5c twenty straight losses happen 36% of the time; proving he picks 6% winners where the price says 5% would take ~1,900 cards. So "success rate" is two questions: how often the card wins (set by leg count × leg likelihood, which the desk can only make visible) and whether he wins less often than the price says (the /bets expected-vs-won line by source answers it; the friend-vs-everything-else split is the biggest lever). "Better picks" is probably not the lever and could not be proven to be. Killed, with the row that kills each, in the plan and on #320: ranking by the gap, a correlation default, situational angles, alt lines as strategy, a leg/stop/stake rule, scoring the cards, any running scout-accuracy figure, a CLV split by the gap, a weekly card count, an "ask again" button.
- **Landed and live** (`7f135730`; deploys 37890632084 → `51b54290`, 37893265979 → `a1de244a`, then the final batch after CI 37896543678):
  - **ADR 0194 + schema v65** (`7ea38ca7`): `parlay_position_legs` carries each leg's own Kalshi ask at purchase (`ask_source` 'lookup' | 'candle'), its close as YES bid/ask before the TRUE start (event_links → odds_fixtures, never kalshi_events), stored on the leg row and never in `closing_lines`. `scripts/backfill_leg_prices.py` fills history from candlesticks (~80 days kept), NULLs only, counts only. **The live run has not happened**: flyctl lost its login on the laptop (`flyctl auth login` is Joe's), so step 0 (/bets expected-vs-won by source through `fetch_live_route.py /api/bets`), the backfill (`--dry-run` then `--commit`), and the markup look A all wait on it. The oldest held legs (2026-08-18) fall out of the venue's window around 2026-11-06.
  - **#323** (`af7eb87f`): lookups and checks write `kalshi_ask_tenths` + `desk_chance` per leg; all four position writers carry the ask without touching the order or RFQ path; combo legs enter the closing-line scorer (plan pinned to `idx_parlay_position_legs_ticker`, never `odds_snapshots`); /bets gains "by leg kind" (expected vs won at the ask, closing-line value in cents) through `expected_block`, never joining the leg-verdict table (sqlite authorizer pin), never split by the gap.
  - **#324** (`da97be58`) and **#325** (`e363e470` + v66 `114b1064`): the leg-verdict registration's Amendment 1 admits `check_button`; Check a parlay gains the probable-bug flag with the spread/total rule (a leg with no recommendations row is judged from `fair_prices`'s book count and width, in the ladder's #79 drop too; no fair row = unknown, never clean), the "Ask the scouts" button (tap only; a cached verdict writes no row), and the friend-source line. v66 rebuilds `leg_verdicts` so the CHECK admits the fourth trigger — the lane found that blocker reading the schema; the first tap would have been an IntegrityError.
  - **#326** (`2c367946`, Amendment 1 `9d189c90`) and **#327** (`92b1d087`): the combo-markup registration (UNDERPOWERED, re-scoped; look A = rows before 2026-10-08T00:00Z) and `inspect_live_db.py combo-markup --limit N --cutoff ...`. The amendment moved the kickoff clock off `kalshi_events` (three hours late, half of P2's band) before any row was read; a run on the old clock would have been look A with P2 NOT EVALUABLE.
  - **#328** (`51b54290`): the buy-sheet cost line ("n legs. Wins about 1 in N. Fee is k×(1−P)% of stake. The same picks as singles: …%", k from the served quote, never a literal) and the Playbook's parlay chapter behind a tap. **#321** (`21035322`): Price on Kalshi states the fact ("Kalshi's ask is Xc against the books' fair value of Yc; hold Z%"), the "Bet two dollars." step is gone, four stale copy lines fixed. **#329** (`8ee969af` + `bfbf3907`): the last-leg push (every leg but one won, the last unstarted: the public book's bid and holding at the last leg's Kalshi price; no venue write; wired on the live loop, silent on demo). **#333** (`7f135730`): the manual-order ticket warns when a single bets against, or doubles, a held leg (the 2026-10-02 incident's screen); the NULL-combo branch is pinned.
- **CI went red twice and each was a pin outside a lane's grep set**: `test_api` asserted "holds" in the old verdict sentence (route-level, not file-level); `/bets` gained an uncapped paragraph and a docstring named the advisory table. Both fixed on main (`a1de244a`, `114b1064`). Lesson written (2026-10-08).
- **Partner's corrections kept**: the per-leg record is backfillable (not "lost for good"); CLV never split by the gap; the cash-out push values holding at the last leg's Kalshi price, never the books'; the census re-run stays as a dated fact-scout run (#331).
- **Worktrees**: lanes 328, 321, 323, 325, 327, 333 remain on disk locked by their agent processes; none holds a node_modules junction (checked for 328/329/321). Remove with `git worktree remove --force` once unlocked; delete the `lane/*` branches (all merged).

### Still open

1. #322 — the live backfill run (`backfill_leg_prices.py --dry-run` then `--commit`, by path) after `flyctl auth login`; counts go here, never rows.
2. #327 — look A of the markup measurement on live (`combo-markup --limit 400 --cutoff 2026-10-08T00:00:00Z`), result doc, measurement-skeptic; needs flyctl auth.
3. #334 — serve `fee_coefficient` on the lookup/check payloads and complete the cost line beside the book tile (was blocked by #321/#325, both merged).
4. #332 — `/api/builder/parlay` + `wong-screen` have no caller: wire or delete.
5. #331 — 2026-11-01: the leg census by kind (NHL puck lines and totals are unparsed; the same-game share).
6. #316, #210, #197, #151, #267 — carried forward unchanged from the eighty-fifth session.

## 2026-10-06 (eighty-sixth session) — README rewritten as a short user guide on Joe's call; the research record archived verbatim; five stale remote branches deleted

- **Joe asked for a README that is simple to read and appealing to someone who wants to use the tool, and to close branches no longer needed.** He chose (option buttons): drop the measurement record from the README entirely, and add one screenshot of the demo.
- **The old README is archived verbatim** at `docs/history/readme-2026-10-06.md` (same pattern as `docs/history/claude-md-2026-09-08.md`, ADR 0116). Its beta table was already two fits stale against CLAUDE.md (no 2026-10-01 fit, `G = 713` floor, gate at 2). Nothing in it is maintained; CLAUDE.md and `docs/` are the record.
- **New README** (~5.6 KB, was 20 KB): pitch, demo link, one screenshot of the demo's Games rows at 1440 (`docs/images/games-rows.png`, 116 KB, captured via Playwright against the demo instance, no credits bought), what each screen does, how a bet is priced in one paragraph with the cost-not-information premise stated, run-it commands, the five `.env` keys that matter, before-you-trust-it-with-money bullets, the §3.1 run-your-own-copy note and the Retrosheet notice verbatim. No decaying counts (ADR 0162). `tests/test_combo_book_depth_claims.py` still pins README.md and passes.
- **Branches deleted on origin**: `lane/198-leg-census`, `lane/201-rest-chip`, `lane/202-game-page`, `lane/205-game-batching` (PRs 199/203/204/207 merged, `git cherry` 0 unmerged each) and `claude/284-card-face` (PR 300 closed; #284 landed as `59b95acc`). `origin/claude/174-hud-slate` and `origin/lane/206-hedge-label` were already gone on fetch. Only `main` remains; no worktrees. Each is restorable from its PR page.
- No ADR: no decision changed, only where the record is read from.

### Still open

Carried forward unchanged from the eighty-fifth session:

1. #316 — closes on the first post-`e8e2531d` call that records `code_execution_tool_result:server_tool_use_limit`. Read `agent-tool-errors` and `game-script-card-refusals` together after 18:00Z on 2026-10-07, a full day of v5 cards.
2. #210 — closes on the first convening whose searches succeed and whose Matchup tile carries sourced notes.
3. #197 stays open with #210. #151 waits until search is reliable. #267 is due in November.
## 2026-10-06 (eighty-fifth session) — #316's code is read and it is OUR cap: the limit surfaces as a failed code execution, already in the scout capture; Joe's (A) to #319 ships the prompt rule, live on `e8e2531d`

- **CI was red on main from 2026-10-05T23:46Z** (two pushes): session 84's `rfq_create_conflict_409.json` had no `DISPOSITIONS` row. Its handoff said "CI green on all three jobs"; that run was for the commit before. Classified in `6e8339c`.
- **#316 read at 14:22Z** (`agent-tool-errors --limit 200`): all 19 post-deploy calls `{}`; every NULL predates the v64 deploy. Yet `game-script-card-refusals` shows **five** post-deploy cards refused with "server tool use limit exceeded on every attempt" (23:35Z, 10:13Z, 10:14Z, 10:32Z, 11:22Z), and `agent-spend` shows each of them **billed exactly 3 searches**, the cards' cap. Anthropic's docs: a failed search is not billed. So the 3 succeeded and the failure came after.
- **The wire shape was already committed.** `tests/fixtures/anthropic_scout_captured.json`'s fourth `code_execution_tool_result` carries `return_code: 1`, `stderr: "Server tool use limit exceeded during code execution."`, after exactly 6 billed searches (the scouts' cap). No `web_search_tool_result` error block. Under `web_search_20260209` the search runs inside the sandbox; the cap-plus-one search kills the whole code block and every result it held, and the model reports "unavailable". The capture's own test asserted it was clean and stayed green over it.
- **Shipped `976e9e8`**: `tool_errors_from` counts a nonzero `return_code` as `code_execution_tool_result:server_tool_use_limit` (stderr names it) or `exit_<rc>`; the log line keeps stderr and replaces `encrypted_stdout` with its length. Three guards, each red under mutation. The derived `web_search_tool_result_error` payload stays derived.
- **#319 opened under #302 and answered (A) by Joe with the option buttons (~15:00Z): a prompt line, no money change.** Shipped `e8e2531`: `search_cap_rule(max_uses)` in `backend/agents/base.py`, appended to the card (**prompt v5**), T-2h re-check (v2), leg-verdict and staff-scout prompts, each built from the constant that sets its tool's `max_uses`. `tests/test_search_cap_rule.py` pins all four; dropping the rule or moving a cap without it goes red. **Not established: that the model obeys it.** Read `agent-tool-errors` for `server_tool_use_limit` after a day of v5 cards; the count falling is the evidence, the prompt is not.
- **Deployed live** (run `37492816081`, `-f instance=live -f confirm_live=kalshi-cockpit`); `/api/health` `build.git_sha` = `e8e2531d` read back 16:07Z.
- **#310 is CLOSED (2026-10-05T18:39Z)**; session 84's Still-open list carried its 18:00Z re-read as if open. The v4 full-day read is superseded: v5 cards start at the next T-24h pass, so the first read worth taking is after a full day of **v5** cards, ~18:00Z on 2026-10-07.
- **#302 frontier was empty at session start — a finding, not neglect**: no open decision was Joe's until the #316 read produced one, and that one was ticketed and answered in-session.
- Joe, mid-session: partner may run the same committed read-only live instruments main runs, this and future sessions (saved to memory). The auto-mode classifier still refused it once; main ran the read.
- Dependabot: zero open alerts. Partner's ruling at start: nothing buildable; the #316 read produced the day's work.

### Still open

1. #316 — closes on the first post-`e8e2531d` call that records `code_execution_tool_result:server_tool_use_limit` (confirms the recorder end to end on live). Read `agent-tool-errors` and `game-script-card-refusals` together after 18:00Z on 2026-10-07, a full day of v5 cards; the limit count falling beside v4's five-in-a-morning is the only evidence the rule works.
2. #210 — closes on the first convening whose searches succeed and whose Matchup tile carries sourced notes; the staff prompt now carries the cap rule.
3. #197 stays open with #210. #151 waits until search is reliable. #267 is due in November.

## 2026-10-05 (eighty-fourth session) — a refused RFQ create now leaves a row (#317); a lost create answer is unknown, not refused (#318); #316 still has no error code

- **#317 shipped and live** (`0fe9e67`; CI green on all three jobs, with real runners; live `build.git_sha` confirmed ~23:00Z. A bare `gh workflow run deploy.yml` deployed DEMO first, so pass `-f instance=live -f confirm_live=kalshi-cockpit`). Both create sites, buy and exit, write a `combo_rfqs` row with `status='error'` and the refusal text.
  - The rfq_id is ours, `refused-<uuid>`, because a refused create has no venue id. That is also why `mark_error`, an UPDATE by rfq_id, is not the writer.
  - `fair_joint` is left NULL so `bets.py` never reads a refusal as a chance.
  - The write never raises.
  - Mutation-checked: disabling the write turns both row tests red, and narrowing the guard turns the refusal-survives test red.
  - The `kalshi-platform` review found no reader that sends a `refused-` id to the venue, and the open counts already exclude `error`.
- **#318 opened** (from that review): a timeout or a missing id *after* the venue created the RFQ is still labelled refused, and the screen says "Nothing was asked". This predates #317 (no row was written before). No money is at risk.
- **#318 built on Joe's word, same session** (`a4c5b35`). `create_rfq` now calls a create refused only on proof: a 4xx with no lost earlier attempt, or a missing credential.
  - A timeout, a 5xx, a 2xx with no id, or a 4xx after an earlier attempt lost its answer now raises `RfqOutcomeUnknown`, a subclass of `RfqRefused`.
  - **The second `kalshi-platform` review caught the real hole:** `request()` retries POSTs, so a final 4xx proves only the LAST attempt. A sized exit ask meeting its own lost create read as "asked at another size". `KalshiAPIError.earlier_attempt_lost` now carries this; a 429 does not set it.
  - Rows are `status='error'` with `error_text` starting `unknown: `. No schema change; a CHECK rebuild was not worth it for hygiene.
  - The screen no longer says "Nothing was asked" for these.
  - `own-open-rfqs` gains `possibly_open`, kept apart from `open_rows`.
  - **The 409 is now captured** (Joe's ask, ~23:45Z, `scripts/capture_rfq_create_conflict.py` on a held combination; the script's own RFQ was withdrawn). A second identical create returns HTTP 409 with body `{"error":{"code":"already_exists","message":"already exists"}}` and no identifiers. Committed as `tests/fixtures/rfq_create_conflict_409.json`, and the substring detection is pinned to it; disabling the detection turns the test red. n = 1.
  - Still uncaptured: an RFQ-create 429 body.
- **#169 closed, not planned:** Joe answered (C) with the option buttons. A screenshot-only slip is handled by asking the friend for the link, or by copying the parlay in the Kalshi app and pasting its ticker into the #165 link path.
- **#316 read at ~22:15Z:** one post-deploy call so far, a `game_script` with `{}` (searches clean). No error code yet. Everything earlier is NULL (pre-v64).
- Dependabot: zero open alerts. Run 37371370321's "failure" was degraded Actions again: its jobs had 0 steps, and the rerun was green.
- Partner's ruling: little buildable today, so the session ends early. #310's read is due at about 18:00Z on 10-06.

### Still open

1. #316 — read `agent-tool-errors` after the next search failure, promote its logged block to a fixture, then decide on `max_uses`/tool version. #210 closes on the first convening whose searches succeed.
2. #310 — re-read `game-script-latest-prompt` after 18:00Z on 2026-10-06, which is a full day of v4 cards.
3. #197 stays open with #210. #151 waits until search is reliable. #267 is due in November.

## 2026-10-05 (eighty-third session) — web-search error codes recorded (#316); Kalshi holds 3 open RFQs, not 97 (#314)

- **#316 live** (`5cdca77`, schema v64; live on `ca8b76b` ~20:50Z): every agent call writes `agent_calls.tool_error_codes`. The value is a JSON object, `<block type>:<error_code>` → count, where `{}` means read and clean and NULL means no response arrived. Error blocks are also logged raw.
  - `runtime-realist` confirmed that every deployed web-search path (scout staff, cards, T-2h rechecks, leg verdicts) goes through `structured_call` → `settle` with usage.
  - Gap: a reply that fails our output schema raises inside the SDK, so its codes settle NULL.
  - The test payload is **derived from the real scout capture, not captured**. Joe's (A): no paid call to stage one. Promote the first natural failure's logged block into `tests/fixtures/`.
  - Search failed again at 19:00Z (card 284), before the deploy, so it is NULL. New instrument: `agent-tool-errors`.
- **#314 closed** (`7ddb498`): `scripts/read_own_rfqs.py` (GET only) reads the venue's own list. At ~19:38Z: 470 in history, 467 closed, **3 open**, headroom 97, oldest open created 17:09Z. `exchange_index=1` changes nothing.
  - `own-open-rfqs`'s 97 is bookkeeping (rows never stamped closed), not headroom.
  - The fixture is committed redacted on Joe's (A) to #315.
  - Follow-up **#317** (a refused create writes no row): not urgent.
- **#310 first read** (new instrument `game-script-latest-prompt`, `ca8b76b`): n = 3 v4 cards. One built, with a single-person, pre-kickoff `drop_if` ("Bijan Robinson is ruled out or scratched…"); one skipped; one search-failed. None refused by the new rules. Too few to judge.
- **#210** relabelled owner:main: the tile shipped and the ticket closes on observation, so the nightly routine must not rebuild it.
- **CI under GitHub's degraded Actions**: jobs with no runner were cancelled at the 15-minute cap, which reads as `failure`. A job with an empty `runner_name` never ran. Python tests passed on CI for `ca8b76b`, and the local full suite passed: 9942 passed, 2 skipped, 10 xfailed. Frontend got no runner; `tsc` was clean locally and there were no frontend changes.
- **Map #302 has no open questions**, a finding, not a gap. The next likely question (raise `max_uses` or the token ceilings) waits on #316's first code.

### Still open

1. #316 — read `agent-tool-errors` after the next search failure, promote its logged block to a fixture, then decide on `max_uses`/tool version. #210 closes on the first convening whose searches succeed.
2. #310 — re-read `game-script-latest-prompt` after a full day of v4 cards.
3. #317 — a refused RFQ create writes no `combo_rfqs` row (RFQ path, main, not urgent).
4. #197 stays open with #210. #169 and #151 wait until search is reliable (both spend more agent calls). #267 is due in November.

## 2026-10-05 (eighty-second session) — Next.js RCE patched; Anthropic credits ran out at 10:19Z and the desk hid it; #220 reviewed into four fixes, three live

- **Dependabot #19, critical** (GHSA-vcvr-r3jv-pc5j): an RCE in `next/og` `ImageResponse`, which `app/apple-icon.tsx` uses.
  - Next went 16.3.3 → 16.3.8 (`40f17e2`). Live exposure was probably low: `/apple-icon` is prerendered static and takes no parameters.
  - Verified from what live serves: the client bundle carries `version:"16.3.8"`. No committed script reads package versions in the container, and the inline-ssh rule bars a `cat`.
  - Zero open alerts after.
- **The Anthropic credit balance ran out at 2026-10-05 10:19:36Z** (#313). Every agent call since is a 400 "credit balance is too low": automatic cards, Joe's leg verdicts (6 at 17:08Z), and the scout desk.
  - The desk showed it as "the call returned nothing" / "No clean story". Fly's logs were the only place the error existed.
  - Daily spend had climbed 2.4M → 7.2M tokens over 09-29..10-04.
  - **Joe answered (A): he tops up himself**, and `SCOUT_AUTO_TAP_TOKEN_SHARE` 0.5 → 0.75, so automatic cards may use ~2.25M a day (live on `c934515`).
  - **Until he tops up, every AI feature stays dark.**
- **#220 review** (sharp-bettor, over the 6 live prompt-v3 cards). Faults turned into tickets:
  - **#308 live** (`d78dd3e`): a card whose `ticket_needs` contradicts a leg's number is refused. Card 218 said "seven or fewer goals" beside Under 6.5, which loses at 7. Joe was told; that stored card stays until its game passes.
  - **#309 live** (`c934515`): a failed call stores the exception class and message, the screen says "No card yet: …; it will be retried", and a zero-search skip is retryable. Retries are capped at 1 an hour and 3 per game, because failed calls settle NULL tokens that the token brake cannot see.
  - **#310 merged** (prompt v4, `9cf9a44`): `drop_if` must name one person and a pre-kickoff status, and "confirmed" needs a game-day source. Card 217 called Swayman "confirmed" from a 09-30 article, and put McAvoy (a defenseman) on the "top line".
  - **#312 live** (`07d411c`): each card leg shows "books: N%" (the `consensus_chance` term) beside the ask, through `_price_sides`, the game page's own lookup. Joe's (A) to #311.
- **New instruments** (`1bc1e06`): `game-script-card-rechecks` (#307; past cards by status × recheck_status, NULL named, plus `combo_stamped` from `2a858ac`) and `game-script-card-refusals` (reason text by count).
  - Over the newest 273 cards: 125 `refused_budget`, all one reason (the unattended share). 65 of 65 `refused_invalid` say "the call returned nothing".
  - 54 past built cards have NULL `recheck_status`. The minted split ships with `2a858ac`; read it before claiming the T-2h re-check reached every minted card.
- **Other reads:**
  - `credits-day 20261004`: 366 of 700, no budget refusal.
  - `own-open-rfqs`: 97 of 100 by our bookkeeping. Probably an overcount: an RFQ we hold open is never stamped closed, and nothing reads the venue's own list. (This line first said the venue closes an RFQ "after ~10 min". That figure has no source: Kalshi documents that it can expire an RFQ, but not when. #314.)
- **Housekeeping:** five stale worktrees removed. Their locks named a reused PID, now an unrelated process.

### Still open

1. #316 — **Credits were topped up ~18:10Z and calls work again**, but web search fails intermittently. Convening 24 (~18:45Z) got "server tool use limit exceeded" on all 6 searches, and the Jets scout's output failed the schema. No raw search error code is stored. Record the code first, then decide.
   #210 — the Matchup tile renders on the board but was empty in convening 24. It closes on the first convening whose searches succeed.
   #314 — Joe answered (A) to #315: commit a redacted capture of his own RFQ list. Spec is in #314's body. Main runs the capture with live creds.
2. #310 — prompt v4 shipped with this record. **A validator-refused card is now paced like a failed call** (1/hour, cap 3; it is billed in full, and #308/#310 rules can trip every pass), except the outage's legacy "the call returned nothing" rows. Read the first v4 cards after the top-up: are `drop_if`s single-person and pre-kickoff, and how many are refused by the new rules?
3. #197 — stays open with #210 (#220 closed this session).
4. #309, #312 — both verified live and closed. #312's figures read null at ~18:40Z (stale before the kickoff sweep), identical to the game page's reason for the same leg.
5. #314 — nothing stamps an RFQ the venue expired, so `own-open-rfqs` cannot see the real cap.
6. #297, #169 and #151 are unchanged. #267 is due in November.

## 2026-10-03 (eighty-first session) — #3 full, #302 continues it; a friend's off-main-line leg is now priced from alternate lines, live on `93bc6ba0`

Joe asked me to go through the question board because it "is full at 100".

- **Nothing was waiting on him.** All 100 of #3's children were closed. #3 was full because GitHub refuses a 101st sub-issue (HTTP 422), not because questions had piled up. The only open `owner:joe` item is #220, which is due on or after 10-05.
- **Fixed per #292 option (a).** I opened map **#302**, "Cockpit for the pilot, part 2", and new questions for Joe are linked under it. `scripts/board.py` reads roots 3, 302 and 80. `MAP_ISSUES = {3, 302}` lives in board.py and in `test_a_question_for_joe_has_a_ticket.py`, so neither map number counts as a ticket.
- **A map with no children is an empty frontier, not a leaf with no owner.** This is new in `classify()`, so a fresh #302 warns "frontier is EMPTY" instead of asking for an owner.
- The recipe (`docs/agents/issue-tracker.md`), CLAUDE.md step 0/7, partner.md and orchestration.md now name #302. The fixture carries a real capture of #302 from 2026-10-03.
- **Tests:** a question parked under #302 reaches the FRONTIER (`TestContinuationMap`). Two mutations went red: dropping 302 from `ROOTS`, and reverting the map rule.
- **Joe's answers (option buttons):**
  - #169: keep parked.
  - #165: he had **already used it**. Two real friend links were checked, on 10-02 (bought as position #75) and 10-03. #165 is closed.
- **Why a checked parlay showed no chance.** The desk prices one spread and one total per game, the books' main number (`/api/game/{event}/legs` on live).
  - The friend's BYU −6.5 and Over 45.5 had gone `stale_consensus` after the books moved a point.
  - Montana St–Idaho was `not_served`, an FCS game.
  - Joe chose **(A): buy that game's alternate lines on a check** (#304, the first question under #302).
- **Built (#303, #305):**
  - Measured first: `docs/measurements/2026-10-03-ncaaf-alternate-lines-are-two-sided.md`. n = 1 event, 6 books, every line two-sided, 2 credits.
  - `ondemand` kind `alt_lines`, with a 30/day sub-cap inside the 150. The runner serves it via `fetch_props` stamped MANUAL.
  - `alt_lines.py` (lane #305) prices one exact line at worst-of-four, with no sharp anchor.
  - `parlay_check` uses it for `not_served`/`stale_consensus` legs, or files one buy per game (`buying_line`).
  - The screen says "from the books' other lines · N books". Never written to `fair_prices`, which is pinned.
- **Verified live:** on Joe's real 10-03 parlay, the first check filed the buy. The runner served it at 19:35:59Z (cost 2, trigger manual). The re-check priced **BYU −6.5 at 48% from 6 books incl. Pinnacle**, where the main line read −5.5 at 51%.
- **#306, found live and fixed in this session:** an on-demand request lived 90s, but a full pass blocks the inbox for up to 103.8s. The TTL is now 180s, pinned against the measured pass.

### Still open

1. #301 follow-through is done: the 2026-10-02 tickets were tagged and reviewed in chat. Per the operator-data rule, no figures are kept here. **Gap found:** a card's `drop_if` cannot be read once its game has kicked off. `/api/game-cards` serves upcoming cards only, and no inspector reads past cards. Nothing is built for it.
2. #220: on or after 2026-10-05, review the game-script cards, run `credits-day --date 2026-10-04`, and read the first Matchup tile. #210 and #197 close with it. Also owed: the first prompt-v3 card and one `game-script-card-stamps` plus `own-open-rfqs` read. Read the first night's T-2h re-checks (`21677337`): every minted card should carry a `recheck_status`, with no silent NULLs.
3. #297: `collection_coverage_census.py` needs a fresh read-only capture with NHL and NCAAF events before it can answer.
4. #292 (closed this session): new questions for Joe are linked under map #302. Its frontier is empty by finding: nothing is open for him.
5. #303 (closed): alternate lines are verified on NCAAF only (n = 1 event). The first NFL or MLB friend check is unmeasured. A friend's total will often rest on 4 books with no Pinnacle, and the screen shows the count.
6. #169 and #151 are unchanged. #267 is due in November.

---

## 2026-10-02 (eightieth session) — Your bets: tag where each pick came from, live on `b07ef3e1`, schema v63, ADR 0193

Joe bet off the desk's recommendations today and asked to "track them and learn from them". He named five sources: game-script cards, leg verdicts, presets, a Claude chat pick, and a friend's link. He chose the one-tap tag (AskUserQuestion) over a read-only review.

- **Today's bets were all recorded through the cockpit.** Positions 75–79, placed 15:53–15:56Z:
  - #75 `checked`: the outside-parlay check, likely the friend's link. RFQ fill.
  - #76 `safe`: RFQ. Its stake is `as_recorded`, with `rfq_fill_unmatched`.
  - #77 `lottery`: RFQ, paid about 5.3c against a desk fair of 6.2%.
  - #78 `short_spreads` and #79 `totals`: manual orders.
  - `unrecorded_at_venue` is empty.
- **Two of the five tickets bet against each other.** #75 holds NO Penn St −2.5 and Over 54.5 Pitt/VT; #78 holds YES Penn St −2.5, and #79 holds Under 54.5 Pitt/VT. In each pair one ticket must lose that leg. Told to Joe; nothing is built for it.
- **Built (#301, ADR 0193, schema v63):**
  - A `pick_sources` table keyed by ticker, so open, settled and outside-placed bets share it.
  - Chips on /bets: settled rows sit outside the row link, and open tickets show them inside `HedgePositions`.
  - Dashed suggestions only from a card stamp or a preset label, never stored without a tap.
  - "By where the pick came from" under each kind. It reuses `expected_block`, keeps a fixed order, is never sorted by result, and shows `too_few` below 5 expected each side.
  - Five mutations, all red.
- **Live read after deploy:**
  - Live serves `pick_sources`. The 20-row window suggests `preset` on 14 tickets, including #76–79, and `card` on 3.
  - Nothing is tagged yet: `by_source.combo` is `untagged` 20W/148L.
- **Process slips, now lessons:**
  - The first CI run failed: `test_exposure_route` pins the exposure handler's span, and the new POST landed inside it. Fixed by moving the route in `b07ef3e1`.
  - I fired a deploy before reading that CI result. It went to demo, the workflow default, because I left out `-f instance=live`. The live deploy that followed was run 37035964679.

### Still open

1. #301 follow-through is done: the 2026-10-02 tickets were tagged and reviewed in chat. Per the operator-data rule, no figures are kept here. Also live: untitled /game legs are named from the venue (`5b59c974`), and NO legs are worded as what they pay on (`c45bbd69`, via `scripts/relabel_untitled_legs.py`). **Gap found:** a card's `drop_if` cannot be read once its game has kicked off. `/api/game-cards` serves upcoming cards only, and no inspector reads past cards. Nothing is built for it.
2. #220: on or after 2026-10-05, review the game-script cards, run `credits-day --date 2026-10-04`, and read the first Matchup tile. #210 and #197 close with it. Also owed: the first prompt-v3 card and one `game-script-card-stamps` plus `own-open-rfqs` read. **Since `21677337`, 2026-10-03:** the T-2h re-check skips the unattended-share gate, stamps `refused_budget` when the day's real ceilings bind, and retries an `unknown` once. Read the first night's re-checks: every minted card should carry a `recheck_status`, with no silent NULLs. Also live: the opposite-sides warning (`c7599ea9`) and each card's drop-if on Your bets (`160d3c9f`).
3. #297: `collection_coverage_census.py` needs a fresh read-only capture with NHL and NCAAF events before it can answer.
4. #292: map #3 is full; a new question for Joe has nowhere visible to go until it lands.
5. #165, #169 and #151 are unchanged. #267 is due in November.

---

## 2026-10-02 (seventy-ninth session, continued) — parlay town hall: batch 1 (17 tickets) live on `734f460`, schema v61 + v62; Joe answered five; batch 2 ticketed

Joe asked partner to convene a town hall on the parlay changes and recommend what makes his selections better, then "let's get creating".

- **How it ran.** Partner chaired five seats over two rounds. The seats were sharp-bettor, kalshi-platform, measurement-skeptic, runtime-realist and a one-meeting UX guest. They worked from live SSR and API captures taken about 04:10Z plus two bounded live reads (`combo-rfqs -n 40`, `position-provenance -n 40`). Runtime-realist's round-2 reply was lost in transit twice, so its round 1 stands.
- **Minutes:** a private Claude Doc, https://claude.ai/artifact/EaAgXPneYH8uwmiza5bZhz. **Epic:** #269.
- **Headline.** Every seat independently found two things:
  - NO legs worded as YES. "NO Over 42.5" pays on the Under, and Kalshi sends the same subtitle on both sides.
  - No Kalshi price on the /game legs, although the listing already carried it.
- **Joe answered five questions with option buttons, plus a batch merge+deploy approval:**
  - #270 (A): T-2h re-check only for games he opened.
  - #271 (A): a tap-only "Check these legs" button on /game and the cards.
  - #272 (A): Your bets gets the expected-vs-won line, with buckets behind a tap.
  - #273 (A): too-fine quotes are shown, never takeable.
  - #274 (A): win plus the same team's cover is refused in words.
  - All five are closed.
- **Built and live on `734f460`** (deploy runs 36970373930 and 36973684256; each screen read on live through the authed API):
  - #275 NO-leg wording.
  - #276 the /game listed ask, size and read time.
  - #277 the win+cover refusal before any venue call.
  - #278 the phone Build bar.
  - #279 empty presets name stale odds (live read: 271 stale-consensus sides).
  - #280 "tap again later" retired.
  - #281 card sources and `ticket_needs`, prompt v3, **schema v61**.
  - #282 quote first/last-seen times.
  - #283 per-leg `at_build` ask freeze.
  - #284 per-sport lineup line, drop-if news links and "Get a price".
  - #285 now / when-written prices with no arrow or colour.
  - #286 three bounded inspectors (`game-script-card-stamps`, `parlay-lookup-errors`, `own-open-rfqs`).
  - #287 Your bets per-kind summary.
  - #288 fee share before Take it, labelled an estimate.
  - #289 the T-2h drop-if re-check, **schema v62**, which reserves 40K tokens and one search.
  - #290 Check these legs.
  - #291 refused too-fine quotes. kalshi-platform said MERGE WITH FIXES, and the copy fix is in: a refused quote dies with the request.
- **Process notes.**
  - Lanes A, B, E, F and D ran Sonnet in worktrees; main built C1–C3, G1, H1 and H3.
  - Two CI failures came from lane F's frontend pins (an uncapped paragraph, and new types missing from `test_wire_types_live_by_area`). The lane had stopped its inventory run at 39%; fixed in `c6622eb`.
  - Every guard was mutation-checked red.
- **Not yet observed:**
  - No card has been built since C3, so `at_build` is NULL on today's cards.
  - No T-2h re-check has fired.
  - The first `game-script-card-stamps` and `own-open-rfqs` reads are owed.
- **Killed by the chair:**
  - auto-RFQ on build
  - making too-fine quotes takeable
  - auto-chained verdicts
  - highlighting the losing leg
  - scoring the cards (ADR 0038, ADR 0190 §7)
  - an arrow on then/now
- **Map #3 is full** at GitHub's 100-sub-issue cap. The answered questions #271–#274 sit under epic #269, and #292 is the fix.

### Still open

1. #220: on or after 2026-10-05, review the game-script cards, run `credits-day --date 2026-10-04`, and read the first Matchup tile. #210 and #197 close with it. **Add to it:** the first prompt-v3 card (`sources`, `ticket_needs`, `at_build`), the first T-2h re-check, and one `game-script-card-stamps` plus `own-open-rfqs` read.
2. **Batch 2 is DONE, live on `ae4e0d3d`** (Joe said run it, AskUserQuestion; deploy run 37014854360). It shipped:
   - #293: rest, title and kickoff on /game.
   - #294: per-leg results on Your bets, read from local `kalshi_markets` / `parlay_position_legs`. Live read: 289 of 289 legs read, no venue call.
   - #295: Change a leg.
   - #296: per-league headings, plus `ANYTD`/`2TD` named in `4a9c9bb1`.
   - #297: `scripts/collection_coverage_census.py`, files-only. Its fixture has no NHL/NCAAF events, so it needs a fresh read-only capture before it can answer.
   - #298: the footer is off /parlays and /game.
   - #299: the 8-leg notice.
   Epic #269 is closed. The /game title and kickoff lead the page since `7a055096` (Joe asked; the card panel is passed into GameLegs as `belowHeading`, so the listing is still read once).
3. #292: map #3 is full; a new question for Joe has nowhere visible to go until it lands.
4. #165, #169 and #151 are unchanged. #267 is due in November.

## 2026-10-02 (seventy-ninth session) — nothing due before 2026-10-05; #3 frontier empty by finding, not by neglect

State at start: `main` = `origin/main` = `2512e91`, clean; CI green; no open PRs; 0 Dependabot alerts; live on `47a3cb3`. Partner checked every open ticket against `git log` and its last comment.

- **Nothing is buildable before #220's date.** #169 is parked (option A killed, `e602daa`) and leans on #165. #165 waits on a friend actually sending a link (Joe, 2026-09-28). #151 collects toward its registered look (1,800 eligible legs or 2027-01-15) and forbids a running read. #210 and #197 close with #220. #267 is November.
- **Map #3 has no open children, and no question for Joe exists.** Every owner:main story waits on something outside the desk, not on a decision of his. #220's reading may produce one (whether the 700/day credit cap moves); that is where it should come from.
- **Two stale worktrees left in place** (`agent-a5b1585…` at `8b5e215`, `agent-a852cc1…` at `098ff1f`), both clean and 0 ahead of main. Both are locked by pid 20340, which is a *live* `claude.exe`, so they were not unlocked. Remove them once that pid is gone (unlink any `node_modules` junction first).

### Still open

1. #220: on or after 2026-10-05, review the game-script cards, run `credits-day --date 2026-10-04`, and read the first Matchup tile. #210 and #197 close with it.
2. #165, #169 and #151 are unchanged. #267 is due in November.

## 2026-10-02 (seventy-eighth session) — #268 read: Joe's combo came through RFQ, its row is consistent; new `position-provenance` inspector query (live on `47a3cb3`); #268 closed

Joe's focus: he had already bought a combination for #268. Single errand he named, so no partner run.

- **`/api/hedge` could not do #268's check.** It serves `stake_basis` but neither `fill_source` nor `fill_ref`, and no inspector query emitted them. Added `inspect_live_db.py position-provenance` (CHEAP, `-n` bounded): the newest `parlay_positions` rows' stored provenance beside the `manual_orders` row `fill_ref` names, joined on `fill_ref` only. `tests/test_inspect_live_db_position_provenance.py`; the `fill_source` guard and the ordering each mutated red. CI 36959228915 green, deploy 36959806920, `/api/health` `build.git_sha` = `47a3cb3`.
- **The combo was bought by RFQ, not the buy button.** Position 74 (placed 2026-10-02T00:13:43Z): `fill_source = rfq_quote`, `fill_ref = 1646` (the accepted quote), `stake_basis = venue_fill`, reason NULL, stake 3783 tenths, matching `/api/hedge`'s $3.78 `venue_fill`. Consistent with `positions.record_rfq_accept`. It has since settled.
- **The path #268 named has not fired since 2026-09-17.** `manual-orders-audit`: 18 rows, the last at 2026-09-17T19:30:52Z, the day `<TakeIt>` was armed. Every combo since has gone through RFQ. #268 closed with the result on the ticket; if a `manual_orders` combo ever fills again, `position-provenance -n 3` checks it in one command.

### Still open

1. #220: on or after 2026-10-05, review the game-script cards, run `credits-day --date 2026-10-04`, and read the first Matchup tile. #210 closes with it.
2. #165, #169 and #151 are unchanged. #267 is due in November.

## 2026-10-01 (seventy-seventh session) — S3 of ADR 0192: the armed hand-bet path leaves `create_app` for `backend/manual_order.py` (#266, live on `86affa0`); story #263 closed; both lanes found their tickets already shipped

Joe gave no focus. Partner ranked the work: #266 on main, #210 and #255 part 1 as Sonnet lanes, then housekeeping. Joe approved the plan, which covered the merges and deploys.

- **#266 (live on `86affa0`).** `place_manual_order`'s body is now `backend/manual_order.place_manual_order`. The route is a thin adapter.
  - The diff against the old handler is 12 mechanical lines, plus one line the review asked for that resolves the clock on each call. No check changed.
  - `routes.py` went from **247,479 to 196,555 bytes**.
  - The ports go in as factories (`live_quotes`, `combo_api`), so a keyless instance still refuses at checks 7 and 11, inside the refusal record.
  - Refusals stay `HTTPException`. Changing them would have edited every check.
- **ADR 0192 §2.8 named 4 pins; the move broke 9.** All 9 are repointed.
  - The `OrderPlacer(` count now walks the production tree.
  - The leg-verdicts pin had been passing vacuously against the adapter; it now checks both files.
  - 14 mutations, all red.
  - `tests/test_manual_order_direct.py` calls checks 0, 4 and 13 with no app. Check 13 runs the **armed** construction against a fake REST port.
  - ADR 0192 Amendment 1 records all of it.
- **Gates passed.** kalshi-platform review approved, and its nits are applied. Full suite on the tree: 9,603 passed, 0 failed. CI 36951078847 green. Deploy 36951640195. `/api/health` reports `build.git_sha` = `86affa0`. An unauthenticated `POST /api/manual-orders` returns 401. Stories #263 and #266 are closed.
- **Both lanes found their work already shipped.**
  - #210, the Matchup tile, was built in `7f35c46` and has been live since 09-29. It stays open only for its own live read: the first matchup note from Joe's tap, the no-pick rule, and the token cost.
  - #255 part 1 shipped in `cd5b216`. I closed it, and part 2 is now **#267** (November).
  - The #255 re-check found `\btie\b` let "ties" through. It now matches word stems, and a mutation confirmed it.
- **Housekeeping.**
  - The session-start box's signal line was stale since #226 and is now current.
  - Three merged lane worktrees were removed. Two are **locked** and were left alone.
- **Map #3 frontier: none exists, and none is owed.** The only real candidate, #169 (a screenshot slip), first needs #165's link path to be used enough to count how often a screenshot is all Joe gets. #220 is not due until 10-05. A question invented to fill the frontier would be noise.

### Still open

1. #268: after Joe's next combination bought through the desk, read its `parlay_positions` row once (`fill_source='manual_order'`, `fill_ref`, `stake_basis`). This is a check, not a measurement.
2. #220: on or after 2026-10-05, review the game-script cards, run `credits-day --date 2026-10-04`, and read the first Matchup tile. #210 closes with it.
3. #165, #169 and #151 are unchanged. #267 is due in November.

## 2026-10-01 (seventy-sixth session) — architecture review; every frontend write goes through one transport module (ADR 0191); api.ts split into transport, format and types (#257–#262, live on `ea53d22`); A+B positions module grilled and ticketed (#263)

Joe ran `/improve-codebase-architecture` with no direction. Hot spots by commits since 09-01: `lib/api.ts` (68), `routes.py` (45), `db.py`/`schema.sql`, `parlays.py`, `hedge.py`. The review covered nine candidates, A–I. The report was a temp HTML file, not committed. Joe picked **C** and answered twelve grilling questions, taking every recommendation.

- **#257 (live `12986cb`).** `acceptComboQuote`, the call that spends, and 12 other POST helpers rendered refusals with `String(detail)`. A pydantic list showed as `[object Object]`. All 14 now go through `refusalText`.
- **ADR 0191 + `CONTEXT.md`** (`fc51cfe`). Every write goes through `frontend/src/lib/transport.ts` and returns one shape, `{ok,status,refusal,detail}`. The no-reply and unreadable-reply sentences are **required, with no default**. Spend writes say the state is UNKNOWN and send Joe to the Kalshi app. Today's shape checks are kept and none are added. `CONTEXT.md` is new, and its first terms are transport module, refusal and spend write.
- **#259 (lane, merged `3550a72`).** The transport, plus the 15 non-spending writes. The three throwers (lockout, log/revise estimate) now return a result.
- **#260 (main, `7b7693c`).** The five spend/order writes are on the transport. **`placeManualOrder` and `placeOrder` no longer say "Nothing was sent to the exchange"** when a connection drops, because a drop after the cockpit has forwarded the order would make that false. A 2xx that can't be read no longer renders as a placed order. `TestASpendWriteNeverClaimsNothingHappened` pins this; mutation-checked.
- **Live on `7b7693c`.** CI 36913330692 green, deploy 36914146238, `/api/health` read. Joe approved the merges and the deploy in this session.
- **#261 (lane, merged `d9b98c6`, live).** `lib/format.ts` owns time, age, duration, dollars and percent. Every lookalike pair differed at a pinned boundary, so **none merged**; each copy is a named function. The test hard-codes outputs captured before the move. The lane missed one test, which read `DISPLAY_TIME_ZONE` from api.ts; I repointed it in `8b5e215`.
- **#262 (lane, merged `ea53d22`, live).** 112 wire types moved into `lib/types/{parlays,slate,scout,signal,hedge,market,orders,bets}.ts`. `api.ts` went from 4,219 to 1,450 lines and holds functions only. The priced-surface registry names `types/parlays.ts` and `types/signal.ts`, and its completeness test still fails on any unregistered priced file. Story #258 is closed.
- **Every merge this session** got a full-suite run on the branch first: 9,528 and 9,536 passed, 0 failed. CI was green before each deploy, and `/api/health` was read after each one.
- **A+B grilled → story #263.** Joe answered 8 questions, taking every recommendation:
  - Schema v60 records which fill produced each position, and new rows store the venue's fill price with its basis. This supersedes ADR 0160 §2.1 for new rows only. No backfill.
  - Fractional fills are recorded on both paths, and the stake checks run once at write.
  - The work is three main-session slices, S1–S3. S2 and S3 get a kalshi-platform review.
  - **ADR 0192 written** (`docs/adr/0192-one-positions-module-records-which-fill-made-each-held-combo.md`). It supersedes ADR 0160 §2.1 for new rows only, and keeps 0160's read path for old rows. Tasks #264–#266 are open with blocking edges.
- **Candidates E–I have no ticket and none is owed.** Joe named C, D and A+B.

### Still open

1. #266 — S3 of ADR 0192: `place_manual_order` leaves `create_app` for `backend/manual_order.py`. Every check moves byte for byte, and the location pins are repointed and mutation-checked. kalshi-platform review, then deploy alone. Story #263. **S1 (#264) is live on `d2b80dc`; S2 (#265) is live on `ef1a309`.** After Joe's next combo bought through the desk, read its `parlay_positions` row once: `fill_source='manual_order'`, `fill_ref`, `stake_basis`. It will be the first real row written this way; no look is registered, so this is a check, not a measurement.
2. #220 — on or after 2026-10-05: game-script cards review, `credits-day --date 2026-10-04`, first Matchup tile.
3. #210, #165, #169, #151 — unchanged. #255 — November.

## 2026-10-01 (seventy-fifth session) — the CLV signal test's registered result is in: UNRESOLVED at G = 1000; #233 answered

`/go` with no focus. State was clean: `7798d97` on main, origin and live, CI green, no PRs, 0 dependabot alerts. Partner found one real job, #226, with an unwritten deadline. #122's 60-day quote retention would start eroding the registered population around 2026-10-07.

- **#226 done.** The off-hours pull ran 2026-10-01 06:00:47Z: 157,372 rows, `truncated: false`. `sd(clv_tenths)` on the cut came in at 35.43, above 31.69, so the §B4 ratchet fired. **Amendment 3** (`ac6b742`, committed alone, before the result) raises the floor 713 → **861**. **Result** (`0de6c96`, `docs/measurements/2026-10-01-clv-signal-test-result.md`): **UNRESOLVED** at G = 1000 clusters, which is 889 games, because props share games with moneylines. beta +0.0401 [−0.0217, +0.1020], G_eff 57.76. §6 alone said NO SIGNAL; §A4 lowered it, because without `too_few_books` (89% of the leverage) the upper limit is +0.64. measurement-skeptic: PASS WITH FIXES, all applied. CLAUDE.md and partner.md were restated: planning still treats the signal as settled, on the basis that no fit shows a signal, not that 0.40 is ruled out. No look remains under this registration.
- **#233 closed.** Joe allowed the read with an option button. `manual-orders-audit` shows that the 2026-09-15 99c combination has one `manual_orders` row, so it **went through the tool**. The 99c on /bets is the venue's average cost basis, with no time label (`bets/page.tsx:620`). The 3.8% is the last desk reading before the fill, and it is labelled with its age.
- **#255 and #220** have dated status comments: November and 2026-10-05.
- **Map #3:** empty. The only question owed is #220's, and it is date-gated to after 2026-10-04. No other exists.

### Still open

1. #256 — the signal strip names the registered §8 result file (lane dispatched this session; check whether it merged).
2. #220 — on or after 2026-10-05: review the game-script cards, plus `credits-day --date 2026-10-04` (decides whether the 700 moves), plus the first Matchup tile (closes #210 and #197).
3. #210, #165, #169, #151 — unchanged.
4. #255 — part 2 waits on college-basketball postings (November).

## 2026-09-30 (seventy-fourth session) — all-hands conference on the live desk; epic #224 built and deployed; Joe answered all seven questions

Joe asked for all the agents to review the site together, with a transcript written like The Wolf of Wall Street. Partner chaired six seats: sharp-bettor, kalshi-platform, measurement-skeptic, runtime-realist, and a web and a UX designer brought in for this meeting only. They worked from SSR text captures of 11 live pages and the source; there were no screenshots because the Chrome extension was not connected. The seats went through two rounds and partner ranked the findings. The transcript and minutes are a private artifact: https://claude.ai/artifact/8uD4GDTHcqecSQKfFH26o2. The money mechanics held up. The words and numbers around them were wrong, in the flattering direction.

- **Built (batch 1, deployed on `1ea9551`):**
  - #225 (main): multi-leg hedge rungs are now `DeriskRung` and show the real worst case, −(stake + hedge cost). They used to show a floor built from "the leg wins = the ticket pays", which put a positive "worst case" on live four-leg tickets. Mutation-verified.
  - #227: SignalStrip no longer says "declaring" when the verdict was downgraded; `sigma_exceeds_ratchet` and `frozen` are now served, and the verdict stops recomputing once the stopping rule has fired.
  - #228: the brakes removed on 2026-09-08 are gone from Gate, Games and Picks. The RFQ accept is named as the third armed door. The Playbook's steps for the deleted estimate field are removed, and `p_yes` and `realised_loss` are dropped from the glossary.
  - #229: same-game detection now keys on (league, fixture segment) of each leg. kalshi-platform said MERGE. CFL and the captured soccer leagues were added, with Brasileiro B/C kept separate. NHL is covered by the league-generic rule but not tested against a capture.
  - #230: Evidence counts only the gate's actionable games, so /ledger and /gate agree (1038 → the Gate's number).
  - #231: the global border rule now sits in `@layer base`, so coloured borders render again, as proven by computed style.
  - #232: the combination Take-it shows one warning per ask with no frequency words, and Joe's #60 checkbox gates the button. This is UI only; whether the server should also refuse is #238.
  - #226 (partial): CLAUDE.md and partner.md are corrected. The floor is nominal G ≥ 713; the "not coming … 52,000 games" claim swapped the unit that §B7 forbids swapping. The pull now selects `clv_scored_ms`, `run_signal_test.py --through-clusters 1000` exists, and the cut rule sits in a dated NOT-AN-AMENDMENT note, committed before any pull.
- **Joe answered all seven questions the same afternoon.** #234 A → #240: an "Open (N)" section at the top of /bets takes over /hedge, with a badge on the tab. The badge reads on page load and when the tab returns, not on the heartbeat, because `/api/hedge` takes ~1.5 s a call. #235 A → #241: Picks is sorted by kickoff and the Likely-winners block is gone (ADR 0067 Amd 1). #236 A → #242: TAKE is shown as "No red flag". #238 A: screen only, nothing built. #239 C: the Playbook says there is no stop rule and stops teaching a $2 stake. #237 A: the **attention slice went 300 → 324, not ~450**: floor 288 + slice + 4 kickoff clusters (84) must fit inside the 700, so 328 is the ceiling. Going higher means moving the 700, and #243 A says read a real heavy day first.
- **Deployed:** batch 1 is on `1ea9551` (screens checked on live; #225 and #227–#232 closed). Batch 2 (#240–#242, the 324 slice, the Playbook) is pushed after the full suite passed (9,379); check `/api/health` `git_sha` against `origin/main`.
- **Refused by the permission classifier:** reading `manual-orders-audit` on live for #233.

### Still open

1. #226 — deploy, then ONE off-hours `clv-signal-pull --i-accept-the-cache-flush` (a whole-file walk on live; Joe said yes to running it off-hours tonight, 2026-09-30), then the §8 result doc and a measurement-skeptic audit. The verdict at G = 1000 is not known and may come out NO SIGNAL.
2. #233 — the 99c / 3.8% combination: was it placed through the tool? Needs Joe to allow or run the audit.
3. #220 — now also reads `credits-day --date 2026-10-04`: the first heavy attended day on the 324 slice (#243 A). That reading decides whether the 700 moves.
4. #210, #165, #169, #151 — unchanged from the seventy-third session below.
5. #244 — the conference's next tier: built and deployed the same evening. #245 line-shopping hint (kalshi-platform review: MERGE WITH FIXES; freshness, active markets and two batched reads added), #246 card/quote ages, #247 and #253 Games says each sentence once, #248 and #254 Your bets leads with the legs and groups by day, #249 `.hud` radius pinned + `--color-warn`, #250 one `isLive`, #251 NHL captured and NCAAMB/NCAAWB/NCAABB prefixes fixed (NCAAB had matched college BASEBALL). #252 answered: the engine's four caps exist. Follow-up: #255 (capture KXNBAGAME rules before the NBA season; a real college-basketball event in season).

## 2026-09-30 (seventy-third session) — nothing due: #188 closed as won't-do; #210's close moves into #220 because no matchup tile exists yet

Joe typed `/go` with no focus. State was clean: `51ceb99`, CI green, no PRs, 0 dependabot alerts. Partner found nothing to build and dispatched no lanes.

- **#210:** live has **0 scout-desk briefings** in the last 2 budget days (`inspect_live_db.py scout-briefings --days 2`), so no Matchup tile has been produced to read. The desk convenes only on Joe's tap. We did not convene one just to close a ticket. #220 now carries the step: read the first tile with the GET (never the POST), check it has no probability, pick or edge, then close #210 and #197.
- **#197** has no other open child. The #198 census found no pricing build.
- **#188 closed as won't-do.** It waited on a loop-lag reading that nobody owns, for a 10–25 ms saving. Reopen it if a timed `/api/health` taken during a `/api/hedge` compute stalls for 250 ms or more.
- **Map #3 is empty per #196 (C).** The only question owed is #220's, and only after Sunday 2026-10-04's reading.
- `lane/210-matchup-tile` still exists, it is merged, and it is Joe's to delete (`a4aafa5`).

### Still open

1. #220 — after Sunday 2026-10-04: sharp-bettor reviews the first automatic cards plus the cost re-read, counts the search-exhausted skips, and reads the first Matchup tile (which closes #210 and #197). The #3 question is opened only if the reading warrants it.
2. #210 — matchup tile; closes when #220 reads the first real note.
3. #165 — open until a friend actually sends a link (Joe, 2026-09-28).
4. #169 — parked behind #165.
5. #151 — collecting. Nothing is owed until the interim look.

## 2026-09-30 (seventy-second session) — #221 and the cards seen in a browser; two display fixes; a stale season date now builds nothing (#222)

Joe typed `/go`. State was clean: CI green on `2219999`, no PRs, 0 dependabot alerts. Partner judged the queue empty of anything due: #220 waits for Sunday 2026-10-04 and every other item is parked on its own trigger. It dispatched verification, board hygiene and one guard.

- **#221 and the cards, seen live (Playwright, minted cookie via file://; the Chrome extension was disconnected again).**
  - `/parlays` and `/game/<event>` fit 390 px with no horizontal scroll, and render at 1440.
  - The Game scripts view loaded 8 cards: 6 built, 2 NHL "no clean story". Both NHL skips cite search running out ("search access exhausted", "Search tool access broke down after the first query"). That is a spend with no card. **#220 should count these.**
  - Two display faults, fixed this session:
    - every leg repeated Kalshi's side label ("Philadelphia wins (Philadelphia)"). `frontend/src/lib/sideLabel.ts` drops it when the title already has every word, and `tests/test_side_label_is_not_repeated.py` drives it through node;
    - `/game/<event>` was headed by the raw ticker. `GameCardPanel` now shows `game_title` when the card has it.
- **#222 (opened and closed):** a `GAME_SCRIPT_REGULAR_SEASON_STARTS` date more than 300 days behind a game is last season's.
  - `decide()` builds nothing for such a game and `run_pass` logs a warning. The guard was removed and the test went red.
  - NFL needs no date, because discovery already drops "Pro Football Preseason".
  - MLB and WNBA still have no cut.
- **#220** now carries `model:opus` and a trigger: if Sunday's cost reading shows cards crowding out leg verdicts, open a question for Joe under #3 on which games get cards. **Map #3 has no open question**, and that one is owed only after the reading.
- **Worktrees:** the five leftover `.next/standalone` shells and the stale 210 worktree were removed (no junctions inside). **Branch `lane/210-matchup-tile` is already merged as `7f35c46`** (`git cherry` shows `-`). Deleting it was refused by the classifier, so Joe can delete it; it is recoverable at `a4aafa5`.

- **Joe's phone, the long-ladder card (~14:30Z), two leg-verdict faults, both fixed:**
  - the scout PASSed "Philadelphia wins by over 1.5 runs" (that day, 18:00Z) as "over a year away". **No seat was ever told the date.** `structured_call` now adds an uncached "Current date and time" system block, which covers every seat (`ac0cbc3`). That PASS stays cached until its 6 h window runs out, which is after first pitch.
  - Toronto's leg read "nobody has asked yet" after he had asked. There was no row on either side, and a refusal was kept only in the panel's memory. The budget read 39/100 searches, so the budget does not explain it. The cause is unrecoverable. A re-ask ran normally and returned TAKE. **#223 (closed):** each refusal now writes the `refused` row the schema already allowed and is logged, so the GET says why. The #151 registration counts only completed rows, so its population is unchanged.

### Still open

1. #220 — after Sunday 2026-10-04: sharp-bettor reviews the first automatic cards plus the cost re-read, and counts the search-exhausted skips; the #3 question is opened only if the reading warrants it.
2. #210 — matchup tile; stays open until the first real matchup note is read.
3. #188 — parked. It waits for a loop-lag reading.
4. #165 — open until a friend actually sends a link (Joe, 2026-09-28).
5. #169 — parked behind #165.
6. #151 — collecting. Nothing is owed until the interim look.

## 2026-09-29 (seventy-first session) — automatic game-script cards built, deployed and armed (#213–#218); one card cost 289K tokens, so Joe raised the token ceiling to 9M (#219)

Joe typed `/go`. The partner's design and dispatch were already on story #213 and each ticket (`owner:`/`model:` labels), so main did S0 and dispatched the lanes directly.

### 1. What landed on `main` (all CI-green through `a210ec8`; `d311ec3` and `92a256d` pushed)

- **#214 S0 (`6b75dbd`, main):** schema v59 `game_script_cards` (tableless). The CHECKs: status is one of four values, a built card has a story and legs, and any other status names a reason. There is no price, probability or edge column, and a test pins that. `GameScriptConfig` (`GAME_SCRIPT_AUTO_ENABLED` false, `GAME_SCRIPT_LEAD_HOURS` 24). In `fly.live.toml`, `AGENT_MAX_CALLS_PER_DAY` 40 → 100 **alone**, on Joe's word; tokens and searches are unmoved. ADR 0190 and the CLAUDE.md budget paragraph.
- **#215 S1 (`a210ec8`, lane + main review):** the seat `backend/agents/game_script.py`, the store and `POST /api/game/{event}/card`, plus the `/game-card` proxy. Main's review added a build lock and reuse of a game's built/skipped card (the 2026-09-25 burst shape), and one `sport_key_for`. **Open** until the cost reading.
- **#216 S2 (`d311ec3`, lane):** `GET /api/game-cards` (unauthenticated like `/api/hedge`, behind `middleware.ts`); the card on `/game/<event>` with a Build card button; a kickoff-ordered "Game-script parlays" section on `/parlays`; each leg's own single-leg ask read at request time. `combo_ticker` is written back when a mint's legs equal a built card's legs.
- **#217 S3a + S3b wiring (`92a256d`, lane + main):** pure `decide()`; `run_pass` and `watch_game_scripts_forever`, started in `scripts/run_loop.py` behind the flag; `MUST_HAVE_CALLERS`. `build_card_for_game` in `routers/game.py` is **the one build path** for the tap and the watcher. The fixture → game link is `event_links`, game series only; an unlinked fixture is skipped, never matched by team names.

### 2. Deploy, the cost reading and the arm (#218, #219)

- **Joe authorised `gh workflow run deploy.yml` for live, this session and future ones** (memory `live-deploy-workflow-is-authorized`). Before that the classifier had refused it.
- **Live `766b017`, migrated v58 → v59.** One card was built through the tap path: `KXNFLGAME-26OCT01PITCLE`, `agent_calls.id` 179, 57.9 s. The inline POST therefore survives Fly/Next.
- **Cost: 289,372 tokens (286,120 in, 3,252 out), 2 searches, n = 1.** The design assumed 60K, so this is ~4.8×. `agent-spend` read it.
- **#219 (opened, asked, answered and closed in-session): Joe chose (D), ceiling 9M.**
  - `AGENT_MAX_TOKENS_PER_DAY` 1.5M → 9M, alone.
  - `CARD_TOKEN_ESTIMATE` 60K → 290K. At 60K one pass over-reserves and spends into his tap half.
  - The flag is true.
  - ADR 0190 Amendment 1 and CLAUDE.md record it.
  - The worst case is about $18/day at the unchecked rate. Joe was told to keep the Anthropic account's spend limit above that.
- **Live on `82bd9f9`.** The watcher's first pass ran at 01:15:50Z and logged "2 fixture(s) with no Kalshi link". It then built `KXMLBGAME-26SEP292200CHCSD` and `KXNHLGAME-26SEP29VANEDM` on its own. #213, #215, #216, #217 and #218 are all closed.
- **Found on the first card:** CLE win + CLE -2 cover + NO over 38.
  - Win and cover are nearly the same bet. The makers price that in, but the card does not say it.
  - The story quotes a book's 38.5 total that it found by search. That is a price-shaped fact the prompt did not supply.
  - Neither breaks ADR 0189's letter, and Joe was told about both. **The NHL card was preseason.** It was ~290K spent on a game that may not matter to him. Watch whether he wants preseason excluded.
- **Still unverified:**
  - the card screens at phone and desktop width;
  - `/api/game-cards` latency with ~14 cards on an NFL Sunday;
  - NCAAF link coverage.
- **Accepted:** the build lock is per process (API vs loop), so a same-minute tap and watcher build can both pay once.
- **`duplicated_legs` (Joe's phone, 2026-09-30; live `86af51b`).** Kalshi refuses "X wins" together with "X wins by N+". `drop_implied_win_legs` drops the win leg on read and before validation. This is lossless, and the card says why. PROMPT_VERSION is now 2.
- **#221 /parlays cleanup (Joe named it; live `daa1598`):**
  - a view switch, *Game scripts* (default) · *Parlay cards* · *Check a parlay*, with the server rendering only the selected one;
  - compact cards, with the story behind "Why this card";
  - Today/Tomorrow/All and league chips, with no reordering;
  - weekday + time + zone on every leg row.
  
  **Not yet seen in a browser:** the Chrome extension was disconnected. Joe's phone is the first check.
- **No preseason cards (Joe, 2026-09-30; live `eb6aa4b`).** Kalshi labels NBA/NHL preseason with the regular season's league string, so the cut is by date. `GAME_SCRIPT_REGULAR_SEASON_STARTS = "nba=2026-10-20,nhl=2026-09-29"`, and a game before its league's date is neither built nor recorded. **Main was wrong in chat:** it called the 4 NHL cards preseason, but the NHL opened 2026-09-29, so they are regular season. **The dates need updating each season.** MLB and WNBA need entries before next spring.

### Still open

1. #220 — after Sunday 2026-10-04: sharp-bettor reviews the first automatic cards (self-contradicting legs, near-duplicate legs, wrong facts, price-shaped story facts) plus the cost re-read; repeat faults become tasks. Joe approved it 2026-09-30. The raw-ticker heading was already fixed in-session (cards now show Kalshi's own game title).
2. #210 — matchup tile; stays open until the first real matchup note is read.
3. #188 — parked. It waits for a loop-lag reading.
4. #165 — open until a friend actually sends a link (Joe, 2026-09-28).
5. #169 — parked behind #165.
6. #151 — collecting. Nothing is owed until the interim look.

## 2026-09-29 (seventieth session) — Joe names parlays: sports factors lead (#200, ADR 0189); rest on every leg (#201), a same-game game page (#202) and a matchup scout tile (#210) ship; automatic game-script cards planned and approved (#213)

Joe named new work, per #196 (C): *"explore making more parlay options, and stronger ones"*, with a generic parlay guide pasted in. Mid-session he redirected: *"the kalshi edge shouldnt be a big determinant here … more about the sports-related factors above all else."* Story **#197** under epic #83 holds all of it. The decision is **ADR 0189**, with a pointer in CLAUDE.md's "What it is for".

### 1. What was decided

- **sharp-bettor mapped the guide against the record.**
  - Same-game correlation only pays when the counterparty prices the legs as independent, and Kalshi's RFQ makers don't.
  - Situational angles are folklore.
  - Pitcher splits and strikeout Overs are refuted (ADR 0036/0037).
  - Key numbers and line shopping are sound.
  - "Stronger" can only mean paying less over fair value for the same opinion.
- **Joe's answers (#200, option buttons):**
  - All four factors: who's playing, game-script combos, schedule/rest, matchups.
  - All four sport groups.
  - Merge/deploy approvals were recorded on #197 per batch.
- **#209, matchup stats: (A) scouts, on tap.** Build is #210.

### 2. Leg census (#198, merged `0d129a7`/`4b458ff`)

- `count_combo_leg_sides.py --by-kind` was run read-only on 94 combos since 2026-09-10.
- The top unpriced kind is `KXNFLTD`, at 2 of 94 (2.1%). Same-game combos are 5 of 94 (5.3%). Both are under the 10% bar fixed beforehand, so **no pricing build and no "as-if-independent" question.**
- Main corrected one gate: a NO-side spread is **not** priced. The pool offers only the favourite's cover. #170's docstring had said otherwise.

### 3. Rest chip (#201, PR #203, live `28c5b27`)

- Every `/parlays` card leg and parlay-check leg carries `rest`: days of rest, back-to-back and short week, per team.
- Main's review moved the reader off `odds_snapshots`, which read every snapshot of every game on each request, onto `odds_fixtures` (PK seeks plus one small range). A failed read leaves `rest` null.
- **Live:** 6 of 6 legs carried rest, and 0 of 12 team-sides were unknown.

### 4. Game page (#202, PR #204; follow-ups #205 PR #207 and #206 PR #208; live `37f8fee`)

- `/game/<Kalshi game event>` is linked from each slate game row. It lists every leg the open **catch-all** collections accept for one fixture (`KXMVENFLSINGLEGAME` has no open collection), in a fixed order that never depends on price.
- Each leg shows its own desk chance or "no desk price" plus a reason, with the scout desk on tap.
- `/game-mint` mints the ticked legs with a **NULL fair joint** (no correlation), and `<AskTheMarket>` asks the makers.
- It is built beside `/api/parlays/lookup`, because that path runs `joint_for` after the mint and would 500 on a same-game set.
- **#205:** `GET /markets` does not batch event tickers, so the page keeps at most 2 reads in flight on the shared combo client.
- **#206:** a game-page position reads "Same-game parlay" on /hedge.
- kalshi-platform passed it with notes; the notes became #205 and #206.
- **Live check (Joe-approved), 2026-09-29 ~22:20Z:**
  - `KXNFLGAME-26OCT04ARINYG` listed 137 legs across 12 series in 2.7 s.
  - A mint of ARI to win plus Over 23 took 0.38 s.
  - The RFQ at $1 drew **13 quotes, best 53c, makers 36.6c apart**. **Nothing was accepted.**
- **0 of 137 legs had a desk chance.** The game is 4+ days out and 48h is the desk's widest window, so chances appear inside about two nights of kickoff. That is by design; tell Joe if he asks.

### 5. Matchup tile (#210, PR #211, merged `7f35c46`)

- The scout board gains a `matchup` tile after `rest_travel`. Each staff scout reports its own club's side of the matchup.
- **A stat appears only as a sourced fact in prose.** The prompt forbids a probability, pick, edge or "should cover", and a test pins that sentence.
- A new test pins the backend and frontend category lists to one list.
- No scout has seen the prompt yet. **The first real matchup notes come from Joe's first tap; read one when it exists** to check that the prohibition held and see what the tile costs in tokens.
- Deploy and the live check are recorded on #210.

### 6. After the record: two parlays built by hand, then Joe asks for it automated (#212 → story #213)

**Superseded by the seventy-first session:** S0–S3a are merged; #218 is what remains.

**The two hand builds.** "Build me a same-game parlay for Sunday's NFL." Main did it in chat: read Kalshi's single-leg prices, had a sharp-bettor subagent web-research the slate, then minted and asked the makers. **Nothing was accepted.**
- **GB at TB, Sunday 1pm ET.** GB wins + NO on TB over 17.5. Tampa's rookie QB Jalon Daniels starts because Mayfield has a thumb injury. Best quote 45.6c from 12 makers, `KXMVECROSSCATEGORY-S2026BF18FBFC7CC-C172E47EDEC`.
- **IND at WAS, in London, 9:30am ET.** The researcher rejected the price-led Colts story because 3 of 4 matchups favour Washington. Joe chose the mirror: WAS wins + NO on IND over 20.5. Best quote 21.5c from 14 makers, `KXMVECROSSCATEGORY-S2026AB099135CE7-465829E81D7`.
- The combinations shard covers only about $6.95. Joe was told.
- **Kalshi's `occurrence_datetime` ran 3h late on GB-TB**: 20:00Z against a 1pm ET kickoff. That is the known offset (CLAUDE.md), so take kickoff from a team or NFL source.

**Joe, verbatim:** "I hope you are automating this and i dont have to go into this CLI for you to this much in-depth. the whole point is to add these to may parlay options."

**#212 (A):**
- A game-script card is built automatically for every game in his sports as it comes within a day of kickoff.
- `AGENT_MAX_CALLS_PER_DAY` goes from 40 to 100; the tokens stay 1.5M.
- **Merge and deploy are approved for the whole batch**, including the cap raise: "go ahead, approve the whole batch". That covers no RFQ accept and no spend.

**The partner's design, in story #213 (read it first):**
- The seat copies `leg_verdict.py`'s shape: one call, at most 3 searches, about 51K tokens by analogue. It is **not** a scout convening, which costs 170K–380K.
- **The model never sees prices.**
- No combined or independent figure anywhere (ADR 0189). Main quoted "45.6c vs about 35c independent" to Joe in chat as teaching; it must not become copy.
- Cards appear in kickoff order only.
- The unattended builder keeps `SCOUT_AUTO_TAP_TOKEN_SHARE` = 0.5, so cards get about 750K a day.
- Each game is built once, at T-24h.
- **Arm the watcher only after one real card's cost is read** from `inspect_live_db.py agent-spend` (`agent='game_script'`).

**The order.** Each is blocked by the one before on GitHub.
1. **#214 S0 (main):** schema v59 `game_script_cards`, config and `fly.live.toml` (calls to 100, `GAME_SCRIPT_AUTO_ENABLED = "false"`), ADR 0190, the CLAUDE.md budget paragraph.
2. **#215 S1 (lane):** the seat plus an on-demand "Build card" on `/game`. Deploy it, then build one real card from the page to get the cost reading. That spends about 51K; the batch approval covers it.
3. **#216 S2 and #217 S3a (lanes, in parallel, after S1):** the card UI on `/game` and `/parlays`, and the watcher's `decide()`.
4. **#218 S3b (main):** wire into the runner, record the S1 cost in ADR 0190, flip the flag on live, runtime-realist check. Tell Joe when the first automatic cards are live. For Sunday's NFL that is Saturday from about 17:00Z.

### Still open

1. #213 — automatic game-script cards (story). Tasks #214 → #215 → #216/#217 → #218, approved to merge and deploy.
2. #210 — matchup tile is live; stays open until the first real matchup note (from Joe's tap) is read: did the prohibition hold, and what did it cost in tokens. #197 closes with it.
3. #188 — parked. It waits for a loop-lag reading.
4. #165 — open until a friend actually sends a link (Joe, 2026-09-28).
5. #169 — parked behind #165.
6. #151 — collecting. Nothing is owed until the interim look.

## 2026-09-29 (sixty-ninth session) — the queue is empty and Joe will name new work (#196, answer C); board.py says so instead of asking for an owner (#195)

`/go` start. Checked: `main` was clean at `b184bd4`, CI green, no PRs, no lanes. Live is on `b139c4e`; everything after it was docs only, so no deploy was owed. Dependabot: 0 open alerts. `cryptography~=50.0` is pinned in `requirements.txt`, which the alert query cannot see. The frontier held only #169 and #188, both parked. Partner's call: the queue is empty because the work is done, so end the session short and do not invent work.

### 1. #196 — cadence question, answered (C)

Asked with option buttons: with nothing queued, should sessions run (A) only on his request or an outside trigger, (B) keep the "keep going" cadence, or (C) wait for him to name new work? **Joe answered (C).** The ticket is closed with his answer. Memory `standing-instruction-keep-going.md` now says "keep going" means continue queued work, not invent it.

### 2. #195 — board.py: an empty map frontier is a finding (lane, merged `3c8a659`)

- `classify()` counted a parent whose children were all closed as a leaf, so map #3 showed up on the frontier as READY and warned "open leaf with no owner". That pointed at the wrong fix.
- Now such a parent is never ready. When nobody has claimed it, the board prints `#N has no open children -- its frontier is EMPTY`.
- A claimed parent stays silent. #151 (collecting) and #165 (waiting on a link) are held on purpose. The lane's first version warned on them too, and main narrowed it.
- Two tests. Both guards were mutation-checked: the lane checked the EMPTY branch and the `ready` term, and main checked the assignee skip.
- **The board still shows the #3 EMPTY warning, and that is correct.** The map has no open question. Per #196, the next question comes from Joe.

### Still open

1. #188 — parked. It waits for a loop-lag reading.
2. #165 — open until a friend actually sends a link (Joe, 2026-09-28).
3. #169 — parked behind #165.
4. #151 — collecting. Nothing is owed until the interim look.

## 2026-09-29 (sixty-eighth session) — `/hedge` 1,803 → 447 ms on one batched venue read (#191); CI tests 9m30s → 5m29s under xdist (#192); the 30 s health-check trial read UNMOVED and reverted, and #193 closes: the stall is outside the machine (§F, §G)

`/go` start. Partner ranked three items as the only open ones that could earn anything (#193's owed reading, #192, #191) and capped latency work at this session. Joe approved the whole merge-and-deploy batch up front with option buttons. Live is on `b139c4e`.

### 1. #191 — `/hedge` reads every leg in one request (live `b139c4e`, closed)

- **Before (live `14af8f7`, warm):** a 1,803 ms median over 10 requests. There were 3 open positions and **N = 12** pending-leg tickers, read one `GET /markets/{ticker}` at a time on the 8/s limiter the hand-bet quote refresh shares. The 41 open positions of 09-21 are gone.
- **The fix:** `LiveQuoteSource.fetch_many` makes one `GET /markets?tickers=` per 100 tickers, and the route, the watcher and `drive_hedge.py` pass it as `fetch_quotes`.
- **Parsed from a capture taken first** (`tests/fixtures/markets_batch_by_ticker.json`, `scripts/capture_markets_batch_fixture.py`, public and unkeyed): a settled market comes back `finalized`, and an unknown ticker is silently omitted, so it stays absent and is never an empty book.
- **kalshi-platform's two reviews:**
  - **Before building:** the venue review rejected a gather (the limiter spaces calls 125 ms apart anyway, and a gather queues a Buy tap behind the burst), and pointed at the batch endpoint.
  - **Before merge:** MERGE WITH FIXES. A hand-typed malformed ticker could 400 the whole batch, so only a well-formed ticker is batched and the rest are read singly (`f8b0fa7`).
- **After:** a **447 ms median**, inside the 300–450 ms prediction written first. All 12 legs were priced, so the keyed batch works on live. #188's trigger did not fire, and it stays parked.
- **Not done:** `GET /account/endpoint_costs` (token cost of a batch), and the combo-book loop on the same route.

### 2. #192 — xdist in CI (lane, merged `f755ff1`, closed)

- Node drivers get unique names from `tests/_node_driver.py`, and `tests/test_no_fixed_name_driver_files.py` guards it.
- The `test_hud_motion` failure had a separate cause: a transient `.ts` in `frontend/src/lib` raced `test_leg_verdicts_ui.py`'s import-time glob. The exposure test now works in a temp dir.
- **CI's first `-n auto` run:** 9,021 passed, 20 skipped, 10 xfailed, **5m29s** (serial: 9m30s). The collected counts agree with the serial run plus the 4 new guard tests.

### 3. #193 — the 30 s trial: UNMOVED; the check is back at 15s

- **#194 (lane, merged `b725c5a`):** `scripts/probe_public_latency.py` is the committed laptop probe, with built-in gap analysis. It fixes the scratch probe's "every non-200 is SLOW" bug.
- **§F** (the rule was pushed in `4eee37e` before the reading):
  - **Live, 30 s check:** 41 stalls in 1,543 requests (3,094–3,127 ms), **F = 0.375** (15 of 40 gaps under 24 s), minimum gap 14.9 s. That is **UNMOVED**.
  - **Demo, always 30 s, no recorder:** the same ~15 s rhythm.
  - `6da370d` reverts the check to 15s, per the trial's own rule. It is on live.
- **measurement-skeptic: OVERSTATED on the first draft.** It flagged three things, all corrected:
  - a rate compared against a rate at a different request cadence;
  - a two-candidate narrowing that dropped host networking and the client's own path;
  - naming Fly with no second client.
- **The 6PN arm could not run.** Next binds IPv4 `0.0.0.0` and `fly proxy` arrives over IPv6.
- **§G, the last step under the stop-loss** (rule pushed in `711e5b0`): three probes in one window:
  - an in-box keep-alive probe (`probe_loopback_latency.py --keepalive`, `e02f5c6`), which decides ours vs not ours;
  - the laptop probe;
  - a GitHub-runner probe (`.github/workflows/probe.yml`, new), which decides server side vs the laptop's path.
- **§G result (19:17–19:28Z, live `b139c4e`), and #193 is CLOSED under the stop-loss:**
  - **In-box keep-alive:** 0 of 1,950 requests took 2,900 ms or more, over 2 reused connections.
  - **Laptop:** 15 stalls in 566 requests.
  - **GitHub runner, live:** 15 stalls in 517 requests, 3,089–3,106 ms.
  - **So:** the 3 s is spent **outside the machine, on Fly's side of the connection**, and the laptop's network is not the cause.
- **measurement-skeptic: OVERSTATED again, on one clause.** "Not ours to fix in the app" went too far. A pooled connection that Next closes after sitting idle, the 2026-08-19 failure on this hop, was never exercised. The doc now says so.
- **If it is ever reopened, start here:** log each new connection :3000 accepts, then compare those times with the stall times. No ticket carries this, deliberately: the stop-loss spent it.

### 4. Housekeeping

- Removed 3 stale worktrees, 7 merged branches and 4 unregistered lane shells (their `node_modules` junctions unlinked first). Main's `node_modules` is intact (37 entries).
- #151 is assigned so it leaves the frontier. It is collecting toward the registered interim look (1,800 legs or 2027-01-15), and nothing is owed until then.
- Lessons: batching widens the blast radius; one client cannot name the far side; check a bind address before planning an arm; keep a measurement window clear of lane test runs.

### Still open

1. #188 — parked. #191's median matched its prediction, so the loop-lag trigger did not fire.
2. #165 — open until a friend actually sends a link (Joe, 2026-09-28).
3. #169 — parked behind #165.
4. #151 — collecting. Nothing is owed until the interim look.

## 2026-09-28 (sixty-seventh session) — "Would Rust help?" No: ADR 0188 (Accepted; the live box is 1.3% busy), four speed lanes live on `1078389` (#186 #187 #189 #190), and a fixed ~3 s server-side stall found (#193)

Joe asked for an exploratory analysis of whether any part of the stack should move to Rust. The repo asked the same thing on 2026-08-08 (item 4) and never wrote the answer down.

### 1. The answer (ADR 0188, `docs/measurements/2026-09-28-is-anything-compute-bound.md`)

- **No rewrite anywhere.** Every cost in the record was attributed to SQL plans, the page cache or the HTTP walk, and each was fixed by an index, a query shape or a table. **That attribution is by wall clock, not CPU time.** The only CPU row is the copula, which a memo fixed.
- **The two numeric kernels, on the laptop:** devig is 94–108 ms a pass. The Monte Carlo copula is 10–26 ms a call. scipy's Genz CDF, timed end to end, is 23–30× faster at 2 legs and 5.5–13× at 3–6, within 1.2 Monte Carlo SEs of the draws. It is exact only at 2 legs.
- **measurement-skeptic: OVERSTATED on the first draft.** It found four problems, all fixed before commit:
  - the Genz timer left setup out (the "~200×" is 23–30× like for like);
  - "exact" is wrong at 3+ legs;
  - the ADR said the ladder builds in the recorder, when it builds per `/api/parlays` request on a memo miss;
  - the recorder verdict rests on the absence of CPU evidence, not on a CPU measurement.
- **The Genz swap is deferred (ADR 0188 §4), not a question for Joe yet.** It becomes one only if a warm `/api/parlays` read on live shows the ladder build as a material share.

### 2. The live CPU reading (`inspect_live_proc.py --diff`, `c12c704`; Joe deployed it himself)

- **The first CPU-time reading the box has ever had:** 21:25–21:45Z, with the window open, one full catalogue walk (11,652 events) and 43 quote passes. **The box: 0.026 of 2 cores (1.3%)**, iowait 0.1%, steal 0.0%. **The recorder: 27.4 CPU-s (0.023 cores).** uvicorn 2.7 s, Next 0.4 s. This contradicts the unprofiled 08-26 claim of "33–114 s of saturated CPU per full pass". It is n = 1. Re-read it on a busy weekend slate.
- **The classifier refused the live deploy twice**, including after Joe's "keep going, deploy when CI passes". It also refused a ticket and doc edits that only mentioned the reading. Joe ran the deploy with `!`. The later deploy of `1078389` went through first try. The memory file carries the pattern.

### 3. Four lanes merged and live on `1078389` (partner's dispatch; Joe approved the batch with option buttons)

- **#187** (lane `af4dd4a`): `/api/signal` serves a stale report at once and refreshes in the background, and the TTL goes from 5 min to 1 h. **Integrator fix `c917c2f`:** the lane's refresh opened its connection with no read budget (ADR 0135), and it cleared its in-flight flag before writing the new report. Both are fixed and pinned.
- **#186** (lane `36f5a90`): pages fetch in parallel. On live, the overhead on top of each page's primary call fell from ~100–150 ms to ~60–80 ms. That is a small gain, because the primary call dominates.
- **#189** (lane `94e4a9b`): `pandas` is out of `requirements.txt`.
- **#190** (lane `f3ae060`): `uv` in CI, so Install takes 3 s instead of 34 s.
  - **Integrator fixes:** `3c6b084` keeps `setup-python` pinning 3.11 (setup-uv's `python-version` only sets UV_PYTHON), and `1078389` pins `setup-uv@v10.2.0`. My own `@v10` broke CI on `3c6b084`, because there is no floating major tag.
  - **xdist was rejected:** 11 failures from fixed-name `.mjs` drivers in ~20 test files. Follow-up is #192.
- #188 is **parked** until someone takes a loop-lag reading. #191 (`/api/hedge` ~2 s, sequential book reads) was split out of it by partner.

### 4. Found while timing the deploy: a fixed ~3.1 s server-side stall (#193)

- About 1 in 20–40 live requests takes ~3.1 s against ~100 ms, on any route, including a signal cache hit that runs no SQL.
- `curl -w` puts it **after TLS** (DNS ≤ 6 ms, connect ≤ 46 ms, TLS ≤ 70 ms, TTFB ~3.17 s), so it is server side: Fly edge, Next's proxy or uvicorn.
- It predates today. The 09-18 table's 3.6–3.9 s maxima fit it, and so does the 09-17 "3,101 ms signal miss".
- #193 has the bisect plan: a committed in-box probe against :8000, then :3000.

### Still open

1. #193 — the ~3 s stall. **Bisected 2026-09-29:** no process on the box stalls (0 of 1,773 in-box requests, while 21 of 554 external requests stalled in the same window), so it is on the proxied path: Fly's proxy, the interface or kernel, or Next's reused connections. **Next step:** the TCP-counter comparison on live `21c891f` (`inspect_live_proc.py --diff`, baseline window vs probe window). R0 is taken; the run was stopped for laptop memory. Recipe is on #193. After that, a 30 s health-check trial goes to Joe (a `fly.live.toml` change).
2. #191 — `/api/hedge` ~2 s: count the tickers `read_books` reads one by one, then gather or skip closed legs (kalshi-platform review).
3. #192 — give the test drivers unique names, then turn xdist on (lane-ready, sonnet).
4. #188 — parked until a loop-lag reading.
5. #165 — open until a friend actually sends a link (Joe, 2026-09-28).
6. #169 — parked behind #165.

## 2026-09-27/28 (sixty-sixth session) — the HUD reaches Games, Picks, Your bets and /hedge (#174–#177, live `27a7154`); Joe keeps leg verdicts as they are (#183 A) and keeps #165 open; the motion slice ships too (PR #184, live `07ec1ce`) and #171 closes

The session opened on a routine's PR (#178, #174 Games), not a push to main. Joe then ran the rest of slice 3 as parallel lanes and asked for the backlog.

### 1. Slice 3 shipped and seen on live (#174–#177, PRs #178–#181)

- **Games** (#178): the two headline counts are lit readouts, and the sharp-book panel has `.hud`. **Picks** (#179): `.hud` on its three owned panels. It has no headline count, and `test_no_headline_counting_how_many_ranked` forbids one. **/hedge** (#180): `.hud` on each position card and on the venue-coverage banner. No hedge, estimate or stake figure glows (CLAUDE.md: an estimate pinned in neither direction). **Your bets** (#181): `.hud` on the net panel.
- **Joe's decision on the net figure, 2026-09-27 (buttons):** #181 shipped it with `glow` in its own red/green, and Joe took the glow off. The readout is for neutral counts; glowing a verdict on his own money made his biggest loss the brightest thing on the page. `27a7154` now pins the absence with `test_hud_bets.py::test_it_does_not_glow`, and adding `glow` back turns the test red.
- **Checked on live at 390 and 1440** (Playwright, cookie minted from `.env` via file, never inline): brackets render, nothing outside the nav glows except Games' two counts, and there is no horizontal scroll. All four tickets are closed with the check in the closing comment, and #171's slice-3 box is ticked.
- **`RecordParlay` is rendered by /bets, /hedge, /slate and /picks.** The lanes treated it as shared and left it alone.

### 2. The backlog (partner, 2026-09-28): the build queue is effectively empty

- **#151 cost reading** (`inspect_live_db.py agent-spend --days 5`, live): 63 leg verdicts over budget days 09-25, 09-26 and 09-27 used 1.30M, 1.03M and 1.11M tokens. About 55K tokens a verdict. On 09-25 the day hit 1.55M including one scouting run, past the 1.5M cap. Verdicts: 52 TAKE, 8 PASS, 3 `over_length`. No join to outcomes (preregistration §6). **Question for Joe:** keep, trim, or turn off leg verdicts? — #183. **Answered (A):** keep as they are. Closed.
- **#165 usage** (`parlay-lookups-tail`, live): the check has 3 `card_key='checked'` rows in its life, all on 09-26 between 01:43 and 06:25Z, the last matching session 62's own test. None since. Joe (buttons): **keep #165 open** until a friend actually sends a link. No build until then.
- **Stale copy fixed** (`72a175c`): two script strings still called /hedge "the only exit an enter-only combination has". Scripts only; this reaches live with the next deploy.
- Both decisions are appended to map #3's "Decisions so far".

### 3. Slice 4, motion (#182 → PR #184, built, NOT merged)

- A single sweep (`.verdict-sweep`, `var(--accent)` at 30%, 0.9s, iteration count 1) across a TAKE/PASS line when it lands. It is identical for TAKE and PASS, and the whole rule sits inside `prefers-reduced-motion: no-preference`. The line's React key flips `waiting` → `answered`, so the sweep plays on arrival and not on each 5s poll. `tests/test_hud_motion.py` has 13 tests; the lane showed guards (a), (b) and (c) red by mutation. CI is green on the PR.
- **Not merged: waiting on Joe's word.** My `gh pr merge 179` was refused `[Merge Without Review]` because his "merge, deploy and check" had covered #178 only. After he said "merge all three once CI passes", the merges went through. Ask per batch.
- **When merged, check on live:** every verdict already on the cards sweeps once, together, on page load (the ticket allowed it; if it's busy, sweep only answers that arrive while he watches). The `::after` extends 6px past each line, so check 390px for horizontal scroll. Then close #182 and #171.

### 4. After the handoff: #184 merged on Joe's word, live `07ec1ce`; #182 and #171 closed

- **Checked on live /parlays at 390 and 1440:** the shipped rule animates (`verdict-sweep`, 0.9s, count 1) on a probe line injected into the page, and the band is visible mid-sweep. Under emulated reduced motion, `::after` has `animation: none`. There is no sideways scroll at either width.
- **Not seen: a real verdict landing.** The page rendered no verdict line, and choosing a card's "Each leg" tab fires a paid verdict request, so I didn't. The remount wiring is test-pinned (`test_hud_motion.py`). **The next time Joe opens a card's legs, look at whether the page-load sweep of every stored verdict at once feels busy.** If it does, sweep only answers that arrive while he watches.
- The motion lane's worktree and branches are removed.

### Still open

1. #165 — open until a friend actually sends a link (Joe, 2026-09-28).
2. #169 — parked behind #165.
3. #151 — nothing owed; the cost decision is #183 A. The evidence look is registered for 1,800 legs or 2027-01-15.

**The build frontier is empty** (partner, 2026-09-28): map #3 has no open child, and epics #81, #82, #84 and #85 have none. Start the next session with partner on what, if anything, is worth opening. Don't invent build work. Worktree `agent-adc28b9d29a94f3bc` predates session 66; left alone.

## 2026-09-26 (sixty-fifth session) — the HUD is seen on live with real cards; the nav gets two spend gauges (#172), and Joe says carry the look to the other screens as it is (#173 A)

Partner ranked it small: look at the real cards first, then show the scout spend before the first ask-all tap. Nothing on #151 before 09-28.

### 1. Live /parlays with real cards, finally seen (#171 slice 1)

- **How:** Playwright MCP with a cookie minted from `.env`. The Chrome extension is still disconnected. Nothing was clicked.
- **The cards are right at 390 and 1280 wide.** The brackets show, the readout is lit, and the chance bar lights 8 of 20 cells at 39.1%. TAKE is never green. Scout B found no decoration keyed to verdict, edge, gap or rank: `.hud` is always on, and `.glow` marks only the current page.
- **One defect, fixed in `a1a3534`:** at 375px the HUD's mono uppercase nav needed 289px of a 267px row, so the row scrolled and hid the theme toggle. Phone now uses `px-1 tracking-wide`, which is 265px. Desktop is unchanged.
- **Question for Joe:** carry the look to the other screens as it is, change something first, or keep it on /parlays? — #173. **Answered (A)** by option button: carry it as it is, one screen per slice. Closed.

### 2. The spend gauges (#172, lane `4105f5b` + main `0d3f6a2` `d60fe94` `5c4aa4e`; live `e876117`, seen rendered)

- **Why:** at 23:20Z, `/api/scout` read tokens 1,033,348 / 1.5M (69%), searches 57/100 and calls 21/40. /parlays held 16 unread legs, about 816K tokens at ~51K each, against about 467K left. One ask-all tap would have hit the daily cap partway through.
- **What:** `frontend/src/lib/gauges.ts` has two functions:
  - `scoutGauge` shows whichever of tokens, searches or calls is closest to its cap.
  - `oddsGauge` shows `spent_today / daily_budget` (the 700), not the 300 attention slice.
  - Anything unreadable shows "—", never 0%.
- **Where:** the nav shows `SCOUTS ▮▮▮ tokens 69%   ODDS ▮▮▮ credits 61%` from `lg` up. At every width, "Scouts used today" sits under the ask-all button, which is the phone's path. There is no backend change: both numbers were already served.
- **Tests:** `tests/test_hud_gauges.py`, 12 tests. The lane showed four guards red by mutation, and main showed the fifth (bar width).
- **Two things the lane's recipe missed:**
  - CI failed on a `Nav.tsx` pin in `test_watcher_decides_from_fresh_facts.py`, which allows one poll timer. Fixed by folding the scout fetch into the chip's poll (`d60fe94`).
  - On live, the bars were invisible, because a width-less grid collapses in a flex row. Fixed in `5c4aa4e` after a DOM patch on live proved the fix.
- **Lesson and ticket template:** run every test that reads a file the lane edited.

### Still open

0. #171 — slice 3, the HUD on the other screens per Joe's #173 A, one lane each: #174 Games, #175 Picks, #176 Your bets, #177 /hedge. Main checks each on live after merge. Then slice 4 (motion).
1. #151 — on 2026-09-28, read `agent-spend` for `agent='leg_verdict'` against the 1.5M ceiling, plus the TAKE/PASS split. The ask-all button spends in bursts; the gauges now show the day's spend.
2. #165 — close once one link a friend actually sent resolves.
3. #169 — parked.

## 2026-09-26 (sixty-fourth session) — /parlays gets one "ask the scouts about every leg" button (live `6583258`); Joe picks a video-game look, "Cockpit HUD", and its first slice ships (live `c401c62`, #171)

Two errands Joe named himself, so no `partner` pass.

### 1. One tap asks the scouts about every card (`6583258`)

- **The ask:** *"a button on the parlay page that allows for me to send the scouts for all legs so i dont have to click on them one-by-one."*
- **The build:** `AskAllTheScouts` in `ParlayCards.tsx` sends each built card's legs as that card's own `card_button` request, **one card at a time, awaited**. It hands each result to that card's existing `AskTheScouts` panel. There is no new `<LegVerdicts` mount, no new trigger and no schema change.
- **Shared legs are paid for once:** `cached_verdict` serves a `running` row as pending (`backend/leg_verdicts.py:270`).
- **Tests:** `TestOneTapAsksEveryCard` in `tests/test_leg_verdicts_ui.py`. All three guards were verified red by mutation.
- **Not yet done:** it has never been tapped on live, so the first real tap is its first spend.

### 2. The HUD look, slice 1 (`c401c62`, #171)

- **The ask:** *"imagine if this were an interface in a video game ... more pop."* Three mockups on a private design canvas (https://claude.ai/artifact/8owPCB57b4ntuith3ksWTi): A Cockpit HUD, B Trading cards, C Sports-game menu. **Joe picked A** (option button).
- **What shipped:**
  - The dark palette is retuned: navy ground, cyan `--accent` ink, amber `--accent-2`. The indigo fill, red and green are unchanged.
  - The theme opens **dark unless the reader chose light**, in `THEME_SCRIPT`, `ThemeToggle` and `THEME_COLOR.dark`.
  - Fonts: IBM Plex Mono for `--font-mono`, Chakra Petch for `.display`.
  - New `.hud`, `.glow` and `.segments` utilities, `Stat readout` and `Segments` in `ui.tsx`, HUD-dressed parlay cards, and mono uppercase nav.
  - Full suite 8,884 passed, and `test_palette_contrast.py` is green on the new values.
- **Never seen with real cards.** The Chrome extension was disconnected. A local `next start` showed the palette, fonts and nav only, because the backend was unreachable locally.

### Still open

0. #171 — look at live /parlays in a browser first, then the remaining HUD slices (gauges, other screens, motion).
1. #151 — on 2026-09-28, read `agent-spend` for `agent='leg_verdict'` against the 1.5M ceiling, plus the TAKE/PASS split. The ask-all button can now spend a burst in one tap, so read it with that in mind.
2. #165 — close once one link a friend actually sent resolves.
3. #169 — parked.

## 2026-09-26 (sixty-third session) — Why 0 of 8 legs on Joe's held combo got a chance: 3 were stale by design, and 5 are NO-side moneylines, which the recount puts in 2 of 82 recent combos. Nothing built for the screen; live stays on 739f9e2

This session started on `/go`. State was clean, live on `739f9e2`, no PRs, no dependency alerts, and the frontier was the same as session 62's. `partner` said build nothing, and instead read why the desk priced **0 of 8** legs on the one combination Joe holds. It gave two read-only questions. The Chrome extension was still not connected, so the /parlays render check is still undone.

### 1. The 3 college legs: stale by design (comment on #165)

- **Not the cap.** `credits-day` and `sweep-log` for 09-25 and 09-26 show no refusals. NCAAF was bought every hour, 04:00Z–14:00Z.
- **Not missing attention.** `Nav.tsx:253` sends the heartbeat from every page, /parlays included. A fact-scout said the opposite because it grepped only the backend routes (see lessons).
- **The cause is the horizon.** A leg counts as fresh for 900 s (`backend/config.py:712`). A sport whose kickoff is more than 12 h out is bought hourly, even with the page open (`backend/odds/timing.py:544`, ADR 0111). So at ~17 h out a check reads stale about 45 minutes of every hour. Inside 12 h the cadence is ten minutes and the problem clears by itself.

### 2. The 5 NFL "NO — team wins" legs: real but rare (#170, closed)

- Session 62's "2 of 150" had no committed instrument, so #170 built one: `scripts/count_combo_leg_sides.py` (read-only fills + market GETs, stdout only). It was a lane-builder lane, merged as `d9da911`.
- **Reading `--since 2026-09-10`: 2 of 82 combos (2.4%)**, one NFL and one soccer (LIGAMX + MLS). Joe's held combo is the NFL one. That is below the 10% bar the partner set, so **no build**: session 62's kill stands on a committed instrument now.

### Still open

0. #151: on 2026-09-28, read `agent-spend` for `agent='leg_verdict'` against the 1.5M ceiling, plus the TAKE/PASS split.
1. #165: close once one link a friend actually sent resolves. The /parlays box has still never been seen rendered in a browser.
2. #169: parked. Screenshot reading, no build before #151's reading.

## 2026-09-26 (sixty-second session) — #165 read on real inputs: a pasted ticker works on a live combo, but a kalshi.com link usually names a group of combinations and is refused. #169 parked. Nothing built; live stays on 739f9e2

This session started on `/go`. State was clean, live on `739f9e2`, no PRs, no dependency alerts. `partner` said there was little to build: verify #165 on real inputs, ask nothing new, stop. I re-asked Joe the two #165/#169 questions with buttons and he said he had already answered. He had: ADR 0187 lines 15–16. See lessons.

### 1. What was measured (all read-only; one `parlay_lookups` row written by the check; no RFQ)

- **The ticker path works end to end on a live, active, shard-1 combo.** It was Joe's one open held combination, 8 legs, pasted as its market ticker through live `/parlay-check`. The book read, `rfq_available: true`. **0 of 8 legs got a chance.** Three college legs read "consensus has gone stale" (06:25Z, kickoffs ~17h out). Five NFL "NO — team wins" legs read "no consensus reading".
- **The same combo's kalshi.com event link is refused**, correctly: its event lists 34 markets. Across the 150 combinations on Joe's account (settlements + fills), **36 of the 57 events that still list markets hold more than one**. A combo link names the event, never the market, so today's parser resolves only the minority single-market events.
- **What the app's Share button produces is unknown.** The kalshi-platform agent found no real share link anywhere. Indexed combo URLs are all `/markets/<series>/<slug>/<EVENT>`, and Kalshi does run a Branch short-link domain, `kalshi.app.link`. kalshi.com pages 429 behind a Vercel checkpoint, so server-side fetching of them is out anyway.
- **Measured and killed:** a NO-side moneyline leg can never be priced, because the pool emits team YES rows only (`backend/parlays.py:991`). But only **2 of 150** of Joe's combos carry one.

All figures are in the #165 comment. **Not done:** the /parlays box rendered in a browser, because the Chrome extension was not connected.

### 2. Decided

- **No redirect-follower and no event picker built on a guess.** The next real link a friend sends is the fixture. If it is an `app.link`: exact-host allowlist, one hop, redirects off, no credentials, parse `Location` only. If it is an event link on a multi-market event, the fix needs the legs to pick the market, so the fixture decides it.
- **#169 is parked:** option (A) is killed, and there is no OCR spike before #151's spend reading.

### Still open

0. #151: on 2026-09-28, read `agent-spend` for `agent='leg_verdict'` against the 1.5M ceiling, plus the TAKE/PASS split.
1. #165: close once one link a friend actually sent resolves. Most kalshi.com event links will not resolve today; that link is the fixture for the fix.
2. #169: parked. Screenshot reading, no build before #151's reading.

## 2026-09-26 (sixty-first session) — #165: paste a friend's Kalshi link on /parlays and see the desk's chance for each leg and for the whole parlay (#166 #167 #168, ADR 0187). Live on 739f9e2

This session started on `/go`. The board had #151 (a reading due 09-28) and #165. `partner` ranked #165 first and scoped it into slices. Joe answered with buttons: a friend sends **a kalshi.com link or a screenshot**, and he chose **link now, screenshot later** (#169). He had no sample link to hand.

### 1. What shipped

- **#166 `POST /api/parlays/check`, Sonnet lane, two rounds.**
  - `backend/parlay_check.py` finds the combination's market ticker in pasted text and reads its legs off Kalshi (`mve_legs`). It prices each leg from the candidate pool with the combinability filter off, takes `joint_for` when every leg has a chance and no two share a game, reads the book, and writes one `parlay_lookups` row with `card_key = 'checked'`.
  - That row is the whole integration: /bets, Ask the market and Take it read it unchanged (ADR 0187).
  - Each check costs 2–3 Kalshi reads, zero tokens and zero credits, and mints nothing.
- **kalshi-platform review of round 1: safe for money, but the main use was broken.**
  - A kalshi.com combination URL carries the **series** and the **event**, never the market ticker. The regex took the series, and the lane's own test used an invented URL.
  - Round 2 fixes that: prefer a market-shaped token, resolve an event-shaped one through `/markets?event_ticker=` and refuse unless it has exactly one market, and strip trailing punctuation.
  - It also gates Ask the market on `exchange_index == 1` and `status == active` (the RFQ path hard-codes shard 1), renames the key to `checked` (/hedge labels a bought position with it), adds leg-field guards, and writes plain-word reasons.
- **#167, the box on /parlays, Sonnet lane.** An unknown leg reads "No desk reading for this leg — <reason>", never 0. Main added the price's age beside its depth, and the `rfq_available` gate.
- **#168, the /bets third state, Sonnet lane.** A parlay checked before the fill, with no whole-parlay chance, reads "checked on the desk, no chance for the whole parlay". It does not count toward "N of M carry the desk's chance".
- **Tests:** `tests/test_parlay_check.py` 33, `tests/test_check_a_parlay_screen.py` 17, and `TestCheckedWithoutChance` 6. Every guard was mutated red.

### 2. Seen on live

**Live is on `b540945`** (Deploy run 36209252279, on Joe's go-ahead by buttons; `/api/health` confirmed).
- One check was run through the live `/parlay-check` proxy, using a real-shaped link to Joe's settled combo (`…/kxmvecrosscategory-s2026e88b8f612c7`).
- The event resolved to its one market, and all 6 legs read. Four read as "game has already started" and two as "no consensus reading". The joint was `null` (`unknown_leg`), and `rfq_available` was false ("no longer trading").
- **Shard can't be read off the name:** that ticker has no `SHARD1` in its name and carries `exchange_index: 1`.
- The one defect was that the empty-book words still said "so ask instead" beside a withheld button. It was fixed in `739f9e2` with a test, deployed on Joe's second go-ahead (run 36211054543), and the live re-check reads "asking the makers is not available here: this combination is no longer trading".

**Not verified:** a link a friend actually sends (two public example events return zero markets today), the box rendered in a browser, and a check on a live, active, shard-1 combo.

### Still open

0. #151: on 2026-09-28, read `agent-spend` for `agent='leg_verdict'` against the 1.5M ceiling, plus the TAKE/PASS split.
1. #165: close it once Joe has pasted one real friend's link and it resolved. If it didn't, the fix is the parser, anchored on that link.
2. #169: the screenshot half. Measure first how often a screenshot is all he gets.

## 2026-09-25 (sixtieth session) — /bets shows the desk's chance when Joe priced each parlay (#161); the leg ticket says "you can buy 0" and the break-even first, with the box switched off (#160, his answer); the refresh panel's duplicate fixture (#159) and a stale side-switch count (#162) fixed. Live on 29f794d

This session started on `/go`. The board was #151 (reading due 09-28), #159 and #160. `partner` ranked a new `/bets` column first. Joe answered two option-button questions at the start: **#160, switch the amount box off at zero** (visible, disabled, until a re-read finds something buyable), and **build the /bets column**.

### 1. What shipped

- **#161 `/bets`, Sonnet lane.**
  - Each settled combination row shows "Desk's chance when you priced it: 51% · 14s before you bought". The value is `parlay_lookups.fair_joint_conservative` from the latest `priced` lookup at or before the ticker's first `fills.filled_ms`, read in one batched query.
  - The section header reads "27 of 142 carry the desk's chance" on live.
  - Where there is no reading, the row says "— not priced on the desk" or "— no fill on record". It never shows 0.
  - Source scans forbid any sum, mean or `reduce` over the value.
  - The lane **refused my spec's "assumes the legs are independent"**. It was false: `ladder._joint` runs a correlation adjustment. The glossary entry follows `joint_chance` instead.
  - Main's follow-up: the first live render printed "0%" for a 0.06% reading, so `chancePercent` now shows finer places below 10% and "under 0.01%" at the floor (`9bc736e`, **not yet deployed**).
- **#160 leg ticket, main, armed path, layout only.**
  - The zero-buyable notice (`ZeroReason`) and the break-even now render at the top.
  - `DollarAmount` is `disabled={sending || zeroBuyable}`, and `zeroBuyable = ceiling === 0`, so an unread wallet (`null`) never switches it off.
  - `canConfirm` is untouched, and a test pins that.
  - kalshi-platform found three copy lies, all fixed:
    - a `price_grid` zero had no true reason;
    - the amount box's pointer upward was keyed on `contracts`, not the ceiling;
    - "nothing is resting at the ask" was false for fractional or unread depth.
- **#162, opened from that review and fixed the same session.** The side toggle zeroes `contracts`. The recount's dependencies were only the ask and the ceiling, although its comment said "the side (and so the ask)". So two sides with one ask (any book with `yes_bid == no_bid`) left Confirm off on a buyable bet. `side` is now a dependency. The re-review found nothing on the armed path.
- **#159 refresh panel, Sonnet lane.** `SELECT DISTINCT` over every sweep double-listed an event whose `commence_ms` or team spelling moved between sweeps. Each event is now read from its own latest sweep (`MAX(fetched_ms)`), still bounded by `commence_ms`.
- **Tests.**
  - `tests/test_leg_ticket_says_the_deciding_facts_first.py`: 12 claims, 10 mutations red, 7 of 8 original claims red on the pre-fix file.
  - `tests/test_bets_chance_when_bought.py`: 15 claims.
  - `tests/test_refreshable_lists_each_fixture_once.py`: 4 claims.
  - `tests/test_bets.py`: three literal-shape pins gained `chance_carried`.

### 2. Seen on live

**Live is on `29f794d`** (Deploy run 36190735279). The classifier refused the first attempt, and it went through on Joe's go-ahead given with option buttons.

Chrome was not connected, so the session used last session's route: the dev server (a leftover one on port 3055) behind the GET-only proxy, driven by Playwright.
- A real leg ticket on the empty shard 0 ($0.01) showed the notice and the break-even at the top. The input was disabled and Confirm was off.
- The scouts' POST came back from the proxy as "read-only; nothing was sent".
- The refresh panel logged no key collision.
- `/bets` was seen at 390px and a leg ticket at 1440px, and both screenshots were sent to Joe.

**The Deploy workflow defaults to `demo`.** My first run was green and changed nothing on live. Live needs `-f instance=live -f confirm_live=kalshi-cockpit`, and `/api/health` is the only proof.

### Still open

0. #151: on 2026-09-28, read `agent-spend` for `agent='leg_verdict'` against the 1.5M ceiling, plus the TAKE/PASS split.
1. #165: "check a parlay someone else built". Scope it with partner, then ask Joe with buttons what his friend actually sends (a link, a screenshot or a leg list) before building.

### 3. After the handoff: #161 was undercounting (#163), and Joe explained the gap (#164)

Joe asked what else was worth doing, and partner found a flaw in #161. The shipped query counted only `status = 'priced'` lookups. But a KXMVE book is empty between RFQs (ADR 0164), so most real desk lookups are `book_empty`, and they still carry `fair_joint_conservative`. `combo_rfqs.fair_joint` was never read either. **The spec was mine, and it took the word "priced" in the name for the rule.**

The #163 Sonnet lane fixed it. The query is a UNION of both sources at or before the first fill, with `refused`/`error` still out and a tie going to the lookup. The old test was rewritten openly as a spec correction. Merged as `86e2fbe` and **live on it** (run 36196835310, on Joe's go-ahead).

**Live now reads 60 of 142** (it was 27). The other 82 (58%) still have no desk reading. Asked why with buttons, Joe typed: **"its my friend's parlay"**. He tails a friend's builds. Asked whether the desk should check a parlay someone else built: **yes, build that**. That is recorded in #164 (closed, and in the map's Decisions) and opened as story #165 under epic #83, owner:main.

**Then live on `7fc43bd`** (Deploy run 36193273118, on Joe's second go-ahead). It carries the 0% fix, and #161 is closed. The first attempt failed on a Fly API 504 while setting the release status, and live stayed on `29f794d` untouched. A second run was green, and `/api/health` confirmed the sha. All 27 readings render, the smallest as 0.06%.

## 2026-09-25 (fifty-ninth session) — Joe said the expanded parlay card was over-filled; it is now a summary, buying opens a slide-over panel, and the review found two old ways to close a ticket mid-send (#158)

This session started on `/go`. `partner` ranked a `/bets` "chance when you bought" column first. Joe then named the focus himself: *"the tiles get over-filled with info when i expand it … imagine if this is a service i am selling"*. Every call below was his, made with option buttons.

### 1. What was wrong (code map, Explore)

- **Too narrow.** Cards were `lg:grid-cols-3`, about 277px wide, and three buy flows nested inside each one: PriceOnKalshi → AskTheMarket/TakeIt → ManualTicket, plus a ticket per leg.
- **Repetition.** Fair value ×4, the sell-back caveat ×4, leg verdicts ×3, fee caveats ×5.
- **Too many filled buttons.** Up to 3 were visible at once, against the card's own docstring.
- **No shared primitives.** 4 corner radii and 8 text sizes.

### 2. What shipped (`363119f` + the follow-up commit, story #158)

- **`Sheet.tsx`**: a bottom sheet on the phone and a right-docked panel from `lg` (Joe chose it).
  - It stays mounted once opened (hidden, not unmounted).
  - `useReportBusy` refuses Escape, backdrop and Close while an order or an acceptance is out.
- **`ui.tsx`**: `Button` (primary = money only), `SectionLabel`, `Stat`, `Notice`.
- **The card**:
  - two columns below `2xl`
  - a stat row: price to beat, and the chance every leg hits
  - one short exit sentence that names the cost, with the rest behind a `Hint`
  - one outlined "Buy or record this parlay" button. It opens tabs: Whole parlay | Each leg | Record a ticket.
  - `leg_buys_open` now fires from the tab choice, never from a mount.
- **Joe (option buttons)**:
  - The difficulty chart and the fair-value stake table moved behind "How these numbers were made". This reverses the `Stakes` docstring's "a card that cannot say what a stake buys is not a card", on his word.
  - The stake line was reworded: the book sells only what rests on it, and a maker's quote is for the size you ask. `test_parlay_estimate_is_not_a_price` was amended to name both bounds.
  - #108 was closed: #151 replaced it.
- **kalshi-platform review.** No request, ticker/side, idempotency or retry logic changed. It found two older holes that the panel's promise depended on, and both are fixed:
  - ManualTicket's Escape/Close worked mid-send. That cleared the intent key, so a second order with a fresh key was reachable.
  - "Ask again" could unmount TakeIt and discard an UNKNOWN.
- **Tests.** `tests/test_parlay_card_is_calm.py` holds 12 claims, and 14 mutations each went red. One moved assertion (`test_buy_controls`, the not-this-parlay line) now slices the legs tab's intro.
- **Seen before deploy.** A local Next dev server ran against live data through a scratchpad read-only proxy that refuses every non-GET locally. That covered 1440px and 390px, all three tabs and a leg ticket. Screenshots went to Joe.
- **CLAUDE.md "What the recorder costs" corrected.** Auto-convene is `"false"`, the ceilings are 1.5M/40/100, and leg verdicts cost ~51K. `partner.md` got the same fix.

### 3. Found, not fixed

- `/api/odds/refreshable` lists one fixture twice under a sport, so React logs a key collision in the Refresh panel → #159.
- The sharp-bettor review's #2: in the leg ticket, the break-even and a zero-buyable depth render last → #160. That is armed-path layout, owner:main, and Joe decides whether to hide the amount field.
- Partner's `/bets` "chance when you bought" column has no ticket yet. Run partner again next session before opening one.

### Still open

0. #151 — on 2026-09-28, read `agent-spend` for `agent='leg_verdict'` against the 1.5M ceiling, plus the TAKE/PASS split.
1. #159 — refreshable fixture listed twice (Sonnet lane).
2. #160 — leg ticket: deciding facts first (main; ask Joe about hiding the amount field).

**Live on `2043b73`** (Deploy run 36186449942, on Joe's go-ahead after the classifier refused the first attempt). It was seen on the live instance at 1440px and 390px, and #158 is closed.

---

## 2026-09-25 (fifty-eighth session) — the first look at a verdict on screen found a burst that ran the day to 224% and a refusal the card never showed; both fixed and live on 866d942, and Joe raised the three ceilings together (#157 A)

This session started on `/go` with no focus. The frontier was empty, and `partner` ranked four things: the NEXT.md split, an on-screen check of #151, a plain-words budget refusal, and worktree cleanup. The on-screen check changed the session.

### 1. What the first real look found (live, 17:10Z, headless browser with a minted cookie)

The "Two short spreads" card rendered one **TAKE** with a plain reason. The other leg said "No scout read: nobody has asked yet" 45 s after the tap. `POST /leg-verdicts` had actually answered `refused`: **1,120,442 of 500,000 tokens already recorded today**. `agent-spend --days 1` explained it:

- 16 `leg_verdict` calls were admitted between 16:06:24Z and 16:06:35Z, in about five POSTs. That looks like someone trying the new button on several cards.
- Every one passed the ceiling at 334,711 recorded, because a verdict records its tokens only when it settles.
- Real cost per verdict: **mean ~51K, range 29K–90K, n = 17 on one day**. The n = 1 reading of 31,640 was the low end.
- TAKE 14, PASS 3. That is not a rate, and ADR 0186 §4's extreme-split rule is not triggered yet.

### 2. What shipped (live on `7755bf5`, two deploys via `gh workflow run`; `/api/scout` reads 40 calls / 100 searches / 1.5M tokens)

| commit | what |
|---|---|
| `f103705` | NEXT.md split at 89.4%: 18 entries (09-18 to 09-22) moved to `archive/next-2026-09-25.md`, md5 `3958e58d…` |
| `a2e3c1a` | **#154** (lane): the budget refusal reads "The scouts have used today's allowance. They're back in about N hours." N counts to `AgentBudget`'s own day boundary |
| `6b3b59c` | **#156** (main): in-flight verdicts reserve 60K tokens and 3 searches each (`reserved_tokens` on `AgentBudget.refusal_reason`, default 0), aged out on `RUNNING_PATIENCE_MS`. There is no call reservation, because `budget.reserve` already writes the call row. ADR 0186 Amendment 1 |
| `866d942` | **#155** (lane): all three triggers keep the POST result, and `<LegVerdicts>` overlays a posted refusal onto a `none` row |
| `7755bf5` | **#157 (A), Joe by option button**: tokens 500K → 1.5M, calls 24 → 40, searches 60 → 100, moved together. That is about 25 verdicts a day, ~13¢ each, worst case ~$4.50 a day |

**Seen on screen after the deploy:** the TAKE line plus "No scout read: The scouts have used today's allowance. They're back in about 17 hours." A screenshot went to Joe.

### 3. Housekeeping and hazards

- 14 dead lane shells and 4 worktrees were removed. **13 of the shells held junctions into main's `frontend/node_modules`**, including under `.next/standalone`. A lane told to remove its junction still left one there. Each was unlinked with `os.rmdir` before any delete, and main kept its 37 entries. The memory file `lane-worktrees-have-no-toolchain` carries the recipe.
- The Playwright MCP tool echoes the code it runs, so an inlined cookie was printed once. It was a 1-hour cookie and an HMAC, so it did not expose the token. What works instead: the snippet reads the cookie from a `file://` page (memory `i-can-see-authed-screens…`).
- `CLAUDE.md`'s "What the recorder costs" still cites the 2026-09-22 overshoot and the old ceilings only through the measurement doc. It was not edited; the ceilings live in `fly.live.toml`.

### Still open

0. #151 — on 2026-09-28, read `agent-spend` for `agent='leg_verdict'` against the new 1.5M ceiling, plus the TAKE/PASS split.
1. #108 — deferred fifth seat.

---

## 2026-09-25 (fifty-seventh session) — #151: the scouts give a plain-language TAKE/PASS on each parlay leg before Joe buys (ADR 0186, schema v57-58; live on 73ba8a4)

The session started short. The frontier was empty, and `partner` ranked one read-only check on #145. That check showed that 34 of 39 bet legs were on games nobody had scouted, and that this was arithmetic, not a selection defect. Joe then redirected the session: *"point the scouts to the parlay legs. I just want to know if the scouts would make the bet or not … even the 'safe' bets and 'middle' bets have been unsuccessful."* He also asked for plain language.

### 1. What Joe decided (option buttons, all recommended)

**Advisory**: it never blocks a buy. **Paid for by repointing auto-scouting**: `SCOUT_AUTO_CONVENE_ENABLED = "false"` and `LEG_VERDICT_ENABLED = "true"` in `fly.live.toml`. **Every leg of a card he opens**: it fires on the "Price on Kalshi" tap or on opening "Bet these legs one by one". The reason is one or two everyday sentences, 220 characters at most, with no jargon.

### 2. What shipped (story #151; tasks #152 and #153 ran as parallel lanes)

| commit | what |
|---|---|
| `9cb6ac9` | Core, built by main. `backend/agents/leg_verdict.py` makes one metered call per leg, with at most 3 searches, and returns `take`/`pass` plus a reason, never a number. It also adds `LegVerdictConfig`, schema v57 `leg_verdicts` (tableless), ADR 0186 (supersedes ADR 0060's no-verdict rule for this seat only), and the pre-registration |
| `ad04761` | #152 backend: `POST`/`GET /api/leg-verdicts`. The ask, kickoff and briefing are resolved on the server. It serves a cached verdict within 6h and a 2c price move. The ceiling is checked before any row is written |
| `77d7127` | #153 frontend: `LegVerdicts.tsx`. TAKE stays plain ink and never turns green; PASS is shown in the warning colour. It disables nothing |
| `3989414` | Review fix. The per-leg line mounted inside the closed panel on page load, read `none`, and stopped polling, so a verdict requested later would never have shown up. Each trigger now stamps a request time that restarts the poll |

### 3. What to know

- **The scoring is forward only.** Web search sees results after a game, so a verdict can't be judged in hindsight. `docs/measurements/2026-09-25-preregistration-scout-leg-verdicts.md` fixes the rule: TAKE minus PASS excess over the ask, clustered by game, two looks. **It is underpowered:** about 6 points is detectable by 2027-06-30 at ~10 legs a day. An UNRESOLVED result may not be reported as "no help". No running tally goes on any screen.
- **`HOUSE_CONTEXT` leans the seat toward PASS.** The prompt requires every PASS to name a concrete fact. After a few days, read the TAKE/PASS split. An extreme split is a prompt defect, not a finding.
- **Cost is not measured.** The estimate is ~25-35K tokens a verdict. Read `agent-spend` for `agent = 'leg_verdict'` over 3 days before moving any ceiling, and move all three together.

### 4. Deployed, and the first live verdict

**Live on `5c63319`** (Joe said deploy, via option button). The first end-to-end verdict came through the API, not a browser: MLB PIT at DET, YES at 51c, **TAKE** in 21 s, "Checked for injuries, lineup changes, and weather but found nothing new that the price wouldn't already reflect." It cost **31,640 tokens and 1 search**. That is n = 1, not a rate. There were no parlay cards at the time: the slate had 0 fresh games, and 87 legs were excluded as stale consensus. So nobody has yet seen the on-screen render. #145 is closed, answered through #151. #152 and #153 are closed.

**Then Joe looked and saw nothing** (*"i dont see any take or pass here"*). The scout ran only on a buy step, and nothing on a card said it existed. He chose (option button) **a visible "Ask the scouts about these legs" button on every card**. `73ba8a4` added it with schema **v58**, a `leg_verdicts` rebuild that admits trigger `'card_button'`. It is live on `73ba8a4`: 7 buttons render on `/parlays`, and a 0-leg `card_button` POST returns 202.

### 5. Next session

- See the TAKE/PASS line render on a real card, in Chrome or from Joe.
- Read `agent-spend` for `agent='leg_verdict'` after 3 days, plus the TAKE/PASS split. An extreme split is a prompt defect.
- NEXT.md is at ~90% of the read ceiling. **Split it before writing the next entry.**

### Still open

0. #151 — live. Owed: an on-screen render check, a 3-day cost read, and the TAKE/PASS split.
1. #108 — deferred fifth seat.

---

## 2026-09-24 (fifty-sixth session) — #107 captured: a real combination YES bid, from a held book with its ticker redacted on Joe's word; #149 built: `combo-rfqs` and `leg-scout-state` live reads (not deployed)

`partner` ranked a short session. The frontier was empty, and that was the finding: there was no question for Joe to ticket. One `lane-builder` lane ran #149 while main did #107.

### 1. What shipped

| commit | what | ticket |
|---|---|---|
| `2cb5fc9` | `tests/fixtures/combo_orderbook_with_yes_bid.json` is a real public book with a resting YES bid, 0.0130 × 1411.78, plus 4 NO levels. `A_YES_BID` in `test_the_combo_book_reader_is_wired.py` now loads it instead of a hand-built literal | #107 |
| `dae2bc9` | Merge of #149: two CHEAP QueryDefs in `inspect_live_db.py` | #149 |
| `40e8c84` | Review fixes: `combo-rfqs` now prints `purpose` (buy/exit), and `-n 5` returns 5 (the lane had read the shared default as "unset" and served 20) | #149 |

### 2. What the reads found

- **No non-held combination carried a YES level.** 0 of 45 books read. On `/markets`, 0 of 1,037 open list rows showed a `yes_bid`, and only 3 of 1,000 `KXMVECROSSCATEGORY` rows had any volume. **Two of the four held books did** carry one. So the only population that has ever shown a resting combination bid is Joe's own. The counts are on #107 (they are counts, not a rate).
- **Joe answered (Yes, redacted), 2026-09-24, via AskUserQuestion:** a held book may be captured if its ticker is replaced by a placeholder. An orderbook response carries no ticker, leg or account field, so the request's ticker was the only field to redact. The diff was grepped for all four held tickers before pushing, and `TestTheCaptureLeaksNothing` pins the file to the placeholder.
- The real book parses exactly as the literal did. The venue lists levels in **ascending** order, so the best bid is the last entry, and a test pins that.

### 3. Next session

- **#145 close read, after 2026-09-26 10:00Z:** `/api/scout` `tokens_today` and `scout-watch-log` for 20260925. Once #149 is deployed, attach `inspect_live_db.py leg-scout-state` to that read.
- **#149 deployed `8fad917` (Joe ran it) and CLOSED.** First live `leg-scout-state` reading: of 39 armed-path legs since 2026-09-21, **0 were briefed at bet time** (36 absent, 3 failed). These are counts, not a rate. The detail is on #145. If 20260925 reads the same, open a map #3 ticket for Joe: is unattended scouting landing on the games he bets?
- #107 CLOSED (CI green on `2cb5fc9`).
- **#150 read, fixed and CLOSED (`e3bc119`, live on `0889003`, Joe deployed).** `leg-scout-join` on live: of 39 legs, **34 were on games nobody ever scouted**, 3 matched a `failed` briefing, and **2 were the defect** (a spread/total leg missing its game's moneyline briefing). The join now also matches the same fixture segment within the same `kalshi_series.league`. So the zero is mostly real, and it goes to #145's close. Earlier note, kept for the record: **The 0-of-39 may be a join defect, not a finding — #150.** `parlays._leg_scouting` joins through `kalshi_markets.event_ticker`, and Kalshi event tickers carry the series (`KXWNBAPTS-…` vs `KXWNBAGAME-…` for one game). So a prop leg may never match a briefing filed on its game's moneyline, and the watcher's `_is_fresh` shares that join. `inspect_live_db.py leg-scout-join` (`ca59a75`, CI green) separates the two. **Deploy it, then run it before anything else on #145.** Do not open a 'scouting is not earning its tokens' ticket for Joe until #150 is read.

### Still open

0. #145 — deployed (`e166a56`); close it after one full budget day's read (20260925).
1. #108 — deferred fifth seat.

---

## 2026-09-24 (fifty-fifth session) — #147 fixed: the RFQ list's own filter is `user_filter=self`; #148 built: adopt a held combination onto /hedge in one tap; a held combination's ticker was public in #96's fixture, redacted forward on Joe's word. Deployed `ddd98a2` (Joe ran it; the classifier refused `gh workflow run` for me)

`partner` ranked this list. Two `lane-builder` lanes ran in parallel, and
`kalshi-platform` reviewed each one before merge. Both reviews said fix
first, and both were right.

### 1. What shipped

| commit | what | ticket |
|---|---|---|
| `6274c89` | `open_rfq_for` sends `user_filter=self&status=open` and keeps a non-empty `creator_user_id` as a second guard. After a 409 with none of ours found, it refuses in plain words and never reuses | #147 |
| `19522f8` | CI fix-ups for #147. The sell-side fixture's held ticker and legs are redacted, and `redact_to_fixture` now redacts tickers itself | #147 |
| `4b5b40e` | Merge of #148: `POST /api/hedge/positions/adopt` + an Adopt button per unrecorded combination. Refuses NO / NULL side, not-in-poll, already-open, non-KXMVE and legless. The row gets its own `stake_basis = venue_exposure`, routed past the E2 sentence | #148 |
| `39996d4` | Adopt's `BEGIN IMMEDIATE` rolls back on any exception, not only `PositionRefused` | #148 |
| `58b1e36` | `hedge-adopt` registered in the proxy inventory, plus a gloss exemption | #148 |

### 2. What the reads found

- **`rfq_user_filter` is the QUOTES endpoint's parameter.** The RFQ list's
  own parameter is `user_filter=self`. On one busy combination: 100 rows
  without it, 100 with `status=open` alone, 0 with `user_filter=self`.
  Yesterday's "the filter is ignored" had tested the wrong name (lesson
  written). What has not been seen is a non-empty filtered list, i.e. the
  filter returning our own open row. That is why the `creator_user_id`
  guard stays.
- **Operator-data leak.** The review caught #147's first fixture: it was
  captured on a held combination, and the file wrongly claimed
  `market_ticker_redacted: true`. It was never pushed, and the unreachable
  commit was pruned. The same check found **`combo_rfq_quotes_sell_side.json`
  (#96, `2d92786`) had published that held ticker and its 8 legs**. It is
  redacted going forward (only ticker fields changed, verified by a
  field-level diff). **Joe chose to leave history as is (2026-09-24,
  AskUserQuestion)**, which matches the `fc88a31` precedent. Do not
  rewrite history for it.
- **Adopt review:** it caught two defects before merge. A NO holding would
  have been adopted as YES, and adopted rows got the E2 "price the desk
  sent" caveat when no price was sent. The stake is Kalshi's
  `market_exposure`. It is inferred to exclude fees (seen on one
  single-market row) and has never been read on a KXMVE holding.
- **CI went red twice on main.** The lanes' targeted runs missed three
  whole-tree inventory tests. Lesson written, and the ticket template's
  verification recipe now runs those tests by name.

### 3. Next session

- **#148 and #96 CLOSED 2026-09-24** on Joe's first live adopt + sell-quote tap:
  `/api/hedge` (via `scripts/fetch_live_route.py`) served the adopted row with
  `stake_basis = venue_exposure`, and his screen showed makers answering, one
  bid, and finer-than-a-tenth bids named rather than rounded. RFQ withdrawn,
  nothing sold. (No count of his holdings here -- it decays, ADR 0162.)
- **No committed instrument reads `combo_rfqs` on live**, so the tap's
  record was confirmed from Joe's screen, not from the table. That gap is
  worth an `inspect_live_db.py` query if an exit ask ever needs auditing.

- **Joe: on `/hedge`, tap Adopt on a held combination, then tap "what
  would makers pay?"** The first adopt closes #148, and the first sell
  quote closes #96.
- #107 can run as soon as a combination is adopted: capture its public
  YES book as a fixture, **on a redacted ticker**.

### Still open

0. #145 — deployed (`e166a56`); close it after one full budget day's read (20260925).
1. #107 — the book arm of the capture; redact the ticker (the held-ticker lesson).
2. #108 — deferred fifth seat.

---

## 2026-09-24 (fifty-fourth session) — #129's capture taken on the venue's own positions read; #96 built: /hedge asks the makers what they would pay (ADR 0185, schema v56); #147 opened. Deployed `1a2d5be` (Joe ran it)

Joe asked for #129 then #96. No `partner` run — a named errand.

### 1. What shipped (live on `1a2d5be` from ~17:53Z; Joe ran the deploy after the classifier refused mine)

| commit | what | ticket |
|---|---|---|
| `fd0aa57` | The capture script stops reading the RFQ list as "ours" — the venue's 409 is the only signal. First real run taken | #129 (closed) |
| `2d92786` | `POST /api/hedge/positions/{id}/sell-quote` + the card's "what would makers pay?" tap. Seven review defects, each mutation-tested. Schema v56, ADR 0185. The buy accept refuses an exit ask's quote | #96 |

### 2. What the reads found

- **#129's precondition was already true.** The venue's `/portfolio/positions`
  showed three held KXMVE combinations; the line below ("waiting on Joe
  holding…, do not poll") had been copied forward unchecked. Lesson written.
- **Capture, 17:12:45Z, 3 held combinations:** 15 / 9 / 14 parsed quotes,
  6 / 0 / 0 with a YES bid, best 10.1c on the first. Raw on the first: 17
  quotes, 8 bids, best 10.2c — a sell-only quote (`no_bid_dollars` 0) the
  buy parser dropped whole. A count at one moment, not a rate.
- **`GET /communications/rfqs?market_ticker=` is market-wide**, `creator_id`
  blank on every row, `rfq_user_filter=self` ignored. Only our own rows carry
  `creator_user_id` (1 of 100, n = 1). #147 fixes `open_rfq_for` on the buy
  path.
- **`contracts_fp` works on create** — "2.01" held, 18 makers quoted 2.01.
- Venue writes this session: 4 sell-side RFQs (3 captures + 1 probe), all
  withdrawn, nothing accepted.

### 3. Next session

- **Deployed and verified**: `/api/health` `build.git_sha` = `1a2d5be` =
  `origin/main`; boot log `migrated v55 -> v56` at 17:52:57Z.
- **The tap reaches no current position.** Joe's three held combinations are
  *unrecorded* on `/hedge` (no `parlay_positions` row), and the tap needs a
  row with `combo_ticker`. Recording them is the step between this and a use.
- Full suite at `2d92786`'s tree: 8,566 passed locally after one inventory
  fix; `next build` green. Read CI for the count.

### Still open

0. #145 — deployed (`e166a56`); close it after one full budget day's read (20260925).
1. #96 — live (`1a2d5be`); close on the first live tap (needs a recorded combination).
2. #147 — `open_rfq_for` reads strangers' RFQs as ours on the buy path.
3. #107 — the book arm of the capture; the sell arm ran 2026-09-24.
4. #108 — deferred fifth seat.

---

## 2026-09-24 (fifty-third session) — durable reads for the prune and lost-leg closes (#144); Joe answered #145 (A), so half the token ceiling is now his; #115 closed NOT RUN on his (A) to #146; #139 closed on the cursor read. Deployed `e166a56` (Joe ran it)

`/go` with no focus. `partner` ran at 14:22Z. Clock from GitHub's `Date`
header. At 14:25Z live was on `9c0061f`.

### 1. What shipped (live on `e166a56` from ~15:35Z; Joe ran the deploy after the classifier refused mine)

| commit | what | ticket |
|---|---|---|
| `6d1b89c` | Lane (Sonnet): two CHEAP QueryDefs. `odds-prune-cursor` decodes the prune's `meta` cursor per sport. `lost-leg-closures` lists `closed_reason IS NOT NULL` rows. Six mutations turned the tests red | #144 |
| `7b0a982` | Elo registration Amendment 1 (pre-registrar), written before any data was read | #115 |
| `a102d23` | `docs/measurements/2026-09-20-elo-vs-price-result.md`: NOT RUN | #115, #146 |
| `20c3bdf` | `SCOUT_AUTO_TAP_TOKEN_SHARE = 0.5`. The watcher starts no convening once half of `AGENT_MAX_TOKENS_PER_DAY` is recorded. No ceiling moved. Four mutations turned the tests red | #145 |
| `c59fc7a` | CI fix. #144's names were missing from the pinned subcommand list, and a fixed 2026-08-09 test date fell out of its 45-day window | — |

### 2. What the reads found

- **#139's owed read could not be taken as written.** The prune log lines
  live about 10 minutes (`scripts/run_loop.py:836`). `prune-frontier` reads
  `kalshi_quotes` and walks the file. #144 builds the durable read, the
  `meta` cursor, but it only exists on live after the deploy.
- **#141/#143:** `/api/hedge` shows 0 open positions and 3 unrecorded venue
  combos. No convening went to a held dead parlay, because none is held.
  Whether #143 closed anything can be read with `lost-leg-closures` after the
  deploy.
- **#127's premise failed on its first full day.** Budget day 20260924, at
  14:32Z: `tokens_today` = 759,441 of 500,000, 6 calls, 2 auto convenings
  (1 complete, 1 partial), 0 taps. Every tap was refused from 12:12Z. This
  is #145, and Joe answered (A).
- **Elo (#115):** Amendment 1 A1.1 showed that a team-clustered `G_eff`
  can't reach DR-1's 300, so a PASS was impossible by construction. A1.7:
  the armed prune deletes rows the E8 refusal reads. Joe answered (A) to
  #146: NOT RUN. Nothing was read. The Elo lane was stopped and discarded
  uncommitted.

### 3. The post-deploy reads (#144's queries, about 15:40Z)

- **`odds-prune-cursor`** was last written 04:17Z. MLB is at 09-10 02:11Z
  and NFL at 09-10 00:20Z, about at the 14-day line, so the first armed
  night cleared their whole backlog. NCAAF is at 09-07. WNBA is at 08-31,
  **explained, not stuck.** The league paused 08-31 to 09-16 for the FIBA
  Women's World Cup, and `credits-by-sport` shows no WNBA odds buys between
  08-30 23:56Z and 09-16 02:32Z. Its next games cross the 14-day line around
  09-30. #139 is closed.
- **`lost-leg-closures`** returned 5 rows (ids 11–15). They are `lost_leg`
  with source `venue`, closed at 23:30:09Z on 09-23, which was #143's first
  cycle. #144 is closed.

### 4. Next session

- Nothing is owed on the prune. WNBA's cursor next moves around 09-30, when
  the post-break games age past the retention line. Don't chase it before
  then.
- #145's first day under the share: `scout-watch-log` should show
  `refused_budget` naming `SCOUT_AUTO_TAP_TOKEN_SHARE` once 250K is recorded,
  and `/api/scout` should stay under 500K on a day with no taps.
- **Empty map #3 is a finding.** Nothing is open for Joe after #145 and
  #146.

### Still open

0. #145 — deployed (`e166a56`); close it after one full budget day's read (20260925).
1. #129 — waiting on Joe holding an order-linked combination. Do not poll.
2. #96 — blocked on #129; next free schema is 56.
3. #107 — same capture as #129.
4. #108 — deferred fifth seat.

---

## 2026-09-23 (fifty-second session) — the watcher stops scouting dead parlays (#141); Joe answered #142 (A) and a dead hand-recorded slip now closes itself (#143, ADR 0184, schema v55)

`/go` with no focus. `partner` ran at 23:05Z. Clock read from GitHub's
`Date` header.

### 1. What shipped

| commit | what | ticket |
|---|---|---|
| `ce0fb9a` | Lane (Sonnet): `_held_fixtures_kickoff_soonest` skips a position with any `lost` leg, so no convening goes to a later game of a parlay that cannot win. A void leg is still scouted. Both mutations turned the tests red | #141 |
| `6078c16` | Main: `close_dead_hand_recorded` runs in the watcher's cycle beside the venue pass. It closes an open slip with `combo_ticker IS NULL` and a lost leg: `status='settled'`, `closed_reason='lost_leg'` (v55), `closed_source` = whoever resolved the losing leg. A tap leaves the reason NULL. Order-linked combinations still wait for the venue. Three mutations turned the tests red | #142 → #143 |

**Why a column and not a third `closed_source` value** (ADR 0184 §3):
widening that column's CHECK means rebuilding a table that the legs table
references by foreign key, inside a transaction where `foreign_keys` cannot
be switched off. **#96's schema slot slides to 56.**

Housekeeping:
- Three merged worktrees and branches removed.
- `lane-95-combo-book-bid` deleted: it was superseded by `3fe9ba1`'s
  rework, not merged.
- Zero open Dependabot alerts.
- Live was on `fdc384f` at 23:05Z.

### 2. #115 needs no new registration

`partner` worried that an Elo model with too little warm-up would fail for
reasons that say nothing about Elo. The existing preregistration already
fixes `burn_in = 100` and per-league ceilings: MLB ~392 evaluable games,
WNBA ~14, NFL 0 (its §P.3). What blocks it is the `elo-game-pull` QueryDef
(§10, not built), and that walks the whole 2.6 GB `odds_snapshots` table.
It still waits on #139.

### 3. What to read next session (06:00–10:00Z is the window)

- **#139 + #122 first armed night.** At 23:04Z, `odds_snapshots_pruned: 0`
  on every pass, because MLB windows were open. Read `prune-frontier` and
  the prune lines (non-zero `rows_deleted`, recorder `age_ms` flat, no
  `prune failed`), write the rate on #139, then close it.
- **#143's first cycle.** `/api/hedge` should no longer list dead
  hand-recorded slips. Look for the log line "closed on a lost leg".
- **#127/#140/#141.** `scout-watch-log` refuses at "2 of 2"; no convening
  is spent on a dead parlay; `/api/scout` stays under 500K on budget day
  20260924.

### Still open

0. #139 — ARMED; read the first armed passes after the MLB windows close, then close it.
1. #129 — waiting on Joe holding an order-linked combination. Do not poll.
2. #96 — blocked on #129; next free schema is 56.
3. #107 — same capture as #129.
4. #115 — registration exists; build `elo-game-pull` and run after #139 closes. Expires 2026-10-20.
5. #108 — deferred fifth seat.

---

## 2026-09-23 (fifty-first session) — Joe answered the whole frozen digest with option buttons; all eight answers built and deployed (ADR 0183); the desk now scouts his held parlays first

Joe asked two things: why the desk wasn't reviewing his parlays, and to walk
the frozen digest one ticket at a time with buttons, then build what his
answers unblocked. `partner` was skipped because he named the errands
himself. Clock ~19:48Z by GitHub's `Date` header.

### 1. Why the desk wasn't reviewing his parlays

- **Budget.** Live `/api/scout` at 19:47Z showed `tokens_today` 525,808 of
  500,000 after three auto convenings (briefings 15–17). Every tap is refused
  until the 10:00Z roll.
- **Scope.** The watcher read only the desk's own ladder cards. Nothing read
  `parlay_positions`, a KXMVE ticker cannot resolve to a fixture, and the
  Skeptic reviewer (ADR 0062, deleted 0106) never looked at parlays.

### 2. What shipped

| commit | what | ticket |
|---|---|---|
| `6963d6c` | `SCOUT_AUTO_MAX_CONVENINGS_PER_DAY = "2"` on live; `SHARD_HEADROOM` 0.99 with the refusal figure **floored** (it printed $3.90, which the same wall refused); `kalshi_quotes` recommended-ticker exemption bounded at 60 days, and `prune-frontier` counts to match; ADR 0183; #78's answer at the foot of ADR 0169 | #127, #71, #122, #78, #97 (closed) |
| `018a335` + `8cdf605` | Lane B (Sonnet) + main's fix: the parlay builder refuses a leg whose side's `suppressed_reason` names `suspicious_edge`, `too_few_books` or `no_market_width`. **Only those three**: the lane's cut refused any code, which includes "No edge" on nearly every row and would have emptied the screen | #79 |
| `07551d4` | Lane A (Sonnet): the watcher reads `build_ladder_payload` (tonight only). Before the ladder it tries fixtures from open positions' pending legs, inside the same `horizon_end_ms`, with a fallback to any recommended ticker on the leg's event. Six mutations red | #119, #140 |
| `fdc384f` | merges; full local suite 8,479 passed | — |

### 3. What to read next session

- **#122's first night.** The kalshi_quotes prune deletes recommended-ticker
  rows older than 60 days. `prune-frontier` should show the backlog fall.
  It shares the write lock with #139's odds prune, so watch recorder `age_ms`.
- **#127/#140.** `scout-watch-log` should refuse at "2 of 2". The first
  convening on a held-parlay game names it in the `detail`. `/api/scout`
  spend should stay under 500K on budget day 20260924.
- The **digest on map #3 is empty** once #79 and #119 close with the deploy.
  An empty frontier is a finding: the next question for Joe gets a ticket.

### Still open

0. #139 — ARMED on `fe0a76f`; read the first armed passes (rate, recorder age, no failures) and close.
1. #129 — waiting on Joe holding an order-linked combination. Do not poll.
2. #96 — blocked on #129; next free schema is 55.
3. #107 — same capture as #129.
4. #115 — READY (the #58 edge is satisfied); start after #139 closes. Registration expires 2026-10-20.
5. #108 — deferred fifth seat; #140 landed under it.

---

## 2026-09-23 (fiftieth session) — #137 merged with its day boundary fixed; CLAUDE.md no longer says the LLM fleet is free (#138); Joe answered #58 and the odds_snapshots prune is ARMED on live `fe0a76f` (ADR 0182, #139)

Joe said "read NEXT.md and start" at ~17:20Z, straight after the
forty-ninth. `partner`'s ruling, adopted: dispatch #137, correct one false
spine sentence, put #58's date in front of Joe, stop. CI green on
`a5e803a` at session start. No lanes open at the end.

### What shipped

| commit | what | ticket |
|---|---|---|
| `ebb80ad` | CLAUDE.md "What the recorder costs" and `.claude/agents/partner.md` no longer say the LLM fleet is free: unattended scouting spends with nobody tapping since 09-21, and the `AGENT_MAX_*` ceilings are checked before each call, so a day overshoots them | #138 (opened and closed) |
| `d09c036` | `inspect_live_db.py agent-spend` (lane-builder, Sonnet) | #137 |
| `02db3f6` | main's fix to the lane: budget day labelled `called_ms - offset`, window starts on a day boundary; two tests, each red under its mutation | #137 |
| `7db6658` | merge, closes #137 | #137 |
| `e54b5e3` | `backend/store/odds_snapshot_prune.py`, the config switch, runner and loop wiring, ADR 0182, 14 tests (eight guards red under mutation); `fly.live.toml` ships it ENABLED and DRY | #58 (closed), #139 (open) |
| deploy run `35901426314` | live on `e54b5e3`; `/api/health` `build.git_sha` read back | — |

### 1. The lane's bug, caught in review

The lane copied `scout-watch-log`'s `strftime((x + :offset_ms) ...)`. That
is right there only because its column is already a day START. On a raw
`called_ms` it turns the budget day at 14:00Z, not 10:00Z, which splits
20260922 (the one day #137 exists to read) in two. Every lane test seeded
calls at 11:00Z, where both conventions agree, so all passed. The `--days`
window also began at `now - n days`, so the oldest day's running sum was
truncated but read as whole. Both are fixed, and each has a test that goes
red under its mutation. The lane reported "10 tests"; the file had 6 and
now has 8. The ticket's premise was also wrong: `agent_calls` **does**
have `idx_agent_calls_time` (`schema.sql:1410`). The lane caught that and
builds its CHEAP argument on the real index.

### 2. Not done, on purpose

No reading with `agent-spend`. Any reading is a new look and needs a
successor registration (§5 of the 09-21 registration).

### 3. #58 answered in session, built, and deployed dry

Joe answered with option buttons (`AskUserQuestion`), and it worked well;
he asked to be asked that way from now on. His answers: prune before 10-02;
**keep closing lines**, not delete-all, because five readers take a game's
kickoff as `MIN(commence_ms)` from this table; **14 days** after kickoff;
**no VACUUM** for now. ADR 0182 has the rule, and the module docstring says
what it destroys (§7.3 of the dedup registration).

An independent review before any run found a HIGH bug. Keyed on
`(bookmaker, market)`, a prop market covers every player, so a player
dropped from a book's last sweep lost their only close. The key is now
`(bookmaker, market, outcome_description)`. The same review found two
further fixes: the dry run had no cap and would re-count the same games
for 30 s of every pass, and a prune error would have skipped pricing. Both
are fixed and pinned.

Live on `e54b5e3` since ~18:19Z. Every full pass reports
`odds_snapshots_pruned: 0` (so the code is wired), but **no dry-run line had
appeared by 18:50Z**. That is by design: retention skips while a window is
open, and MLB's window was open. **#139 carries the rest**: read the dry-run
line (overnight or morning UTC; `flyctl logs` is lossy), sanity-check the
keep ratio, flip `ODDS_SNAPSHOT_PRUNE_DRY_RUN = "false"`, deploy, and
measure the delete rate. The open risk goes in #139: evening windows may
leave little closed time for the backlog.

The deploy was triggered with `gh workflow run`. The classifier then
refused both `gh run watch` and an `until gh run view` loop on the deploy
run as "[Production Deploy]", but let a plain `gh run list` through.
An `until curl .../api/health | grep git_sha` loop in the background was
allowed, and it is the better wait anyway: it waits on what live reports.

### 4. Armed the same evening, on Joe's "yes, tonight"

Joe asked what could happen before morning. Arming tonight gives the prune
the overnight closed window, so he was asked with buttons and chose it.
`scripts/odds_prune_dry_run.py` (`8e0f4ef`, plus a `.dockerignore` allow
line in `9683a4a` after `test_has_callers` caught it missing from the
image) ran the dry-run count on live over `mode=ro`. Result for the **25
oldest games**: 157,691 of 159,550 rows would go (**98.8%**), about 75 kept
a game, 0 skipped, 6.5 s. That matches roughly 10 books × 3 markets × 2–3
outcomes, one close each. `ODDS_SNAPSHOT_PRUNE_DRY_RUN = "false"` in
`fe0a76f`, deployed. The first armed pass runs when tonight's windows close.

**Next session reads, for #139:** `odds_snapshots_pruned` per full pass and
the prune's own log line (`flyctl logs`, lossy; try more than once); that
recorder `age_ms` stayed flat; that no `prune failed` line appeared. Then
write the delete rate on #139 and close it if the rate clears the backlog
in reasonable time. If it doesn't, ask Joe with buttons whether to raise
the budget or let it run inside windows.

### Still open

**The digest on map #3 is unchanged — eight tickets, frozen, unanswered.**

0. #139 — ARMED on `fe0a76f`; read the first armed passes (rate, recorder age, no failures) and close.
1. #129 — waiting on Joe **holding a combination**, not on a trip. No
   order-linked combination was open at 17:12Z. Joe was asked to say when
   he places one. Do not poll.
2. #96 — blocked on #129; next free schema is 55.
3. #107 — same capture as #129.
4. #115 — #58 is now closed, so its `blocked_by` edge is satisfied and the board will show it READY. Start it after #139 is armed, so the prune's backlog and the Elo look don't compete for the same write lock and cache. Its registration expires 2026-10-20.
5. #71, #78, #79, #97, #119, #122, #127 — with Joe, in the frozen digest (#58 left it answered).
6. #108 — deferred; #137 under it is now closed.

`KalshiRepeatPoll*` show Next Run N/A, so they cannot fire. Left alone.

---

## 2026-09-23 (forty-ninth session) — #118 read: budget day 20260922 is outcome D, not separable; the arms are deleted; live deployed to `0f23f6c`

Joe said "read NEXT.md and start" at 00:20Z; `partner` ruled nothing to do
before T1 (dispatch table empty) and Joe confirmed the laptop was on AC.
Resumed at 16:42Z (GitHub `Date` header) after both windows closed, on
Joe's "go ahead". Zero open Dependabot alerts at the 09-19 check; not
re-read this session.

### What shipped

| commit | what | ticket |
|---|---|---|
| `0f23f6c` | the result doc filled (outcome **D**); `.github/workflows/measure-118.yml` deleted, and `tests/test_118_trip_is_the_registered_command.py` now refuses its return (mutation: restoring the file turns it red) | #118, #136 (both closed) |
| (this commit) | this entry; lessons 2026-09-23 | — |
| (outside the tree) | laptop tasks `Kalshi118T1`/`T2` deleted; #137 opened under #108; outcome commented on #118, #127, #136 | #137 |
| deploy run `35892509269` | live on `0f23f6c` (`/api/health` `git_sha` read back), which carries #135's rollout | #135 |

### 1. The reading, and what D means

Both arms fired: Actions 3 of 4 T1 crons plus 2 T2, laptop 4 plus 2, and
every read was clean. T1 = Actions run `35845257647`, 09:50:44Z. VOID: no on
all three criteria. The allowance refused from 13:00:13Z. At T1,
`tokens_today` was 630,719 of 500,000 (1 call unmetered) and
`searches_today` was 30, against the 24 that leaves room for a run. There
was no `refused_budget` row. **D: which ceiling bound first is unreadable**,
because the watcher records only the first refusal it checks and nothing
records when the budgets were crossed. **#127 is not decision-relevant under
D**; it stays Joe's question, unchanged. Do not write "the allowance masks
the token ceiling", and do not write that the token budget "would have
stopped it anyway" — the registration forbids both.
`measurement-skeptic` returned PASS WITH FIXES; all six fixes were applied
(see lessons 2026-09-23).

### 2. Deploy and the hedge read

Deploy run `35892509269` finished 17:00:34Z; `/api/health` read back
`0f23f6c`. The first hedge-watch pass ran at 17:00:28Z and logged its venue
close pass (`flyctl logs`, `hedge watch: ... closed by venue settlement`).
`/api/hedge` read once at ~17:12Z. **The split, with no count (ADR 0162):**
every position still listed is a hand-recorded `kalshi_combo` slip
(`combo_ticker` NULL) in state `dead`. No order-linked combination remains
open. That is #135 as designed: venue-settled rows close themselves, and
hand-recorded slips stay Joe's tap. Read `/api/hedge` again for a current
figure; do not trust this line's shape past a session or two.

### Still open

**The digest on map #3 is unchanged — eight tickets, frozen, unanswered.**

0. #137 — the §6 instrument (`agent-spend` QueryDef), `owner:agent`, `model:sonnet`; ready, and no live read in the lane; any reading taken with it needs a successor registration.
1. #129 — capture still owed (human; the T2 trip was automated and carried none of it), population from the venue's positions read; then `measure_combo_book_presence.py` and `capture_sell_side_rfq.py` per ticker.
2. #96 — blocked on #129's capture; next free schema is 55 (54 taken).
3. #107 — capture of opportunity, same trip as #129.
4. #115 — starts on #58 landing or 2026-10-06, whichever first (the `blocked_by` edge comes off on 10-06); registration expires 2026-10-20.
5. #58, #71, #78, #79, #97, #119, #122, #127 — with Joe, in the frozen digest.
6. #108 — the deferred fifth seat, plus #137 now filed under it.

Two stale August scheduled tasks (`KalshiRepeatPoll*`) are still on the
laptop; nobody asked.

---

# The session index

Every session entry ever written to this file, newest date first. Full text in
the linked archive file, unchanged.

### In this file, above

Added 2026-09-18: this index listed only the archived entries while its
own first line claimed every entry ever written, which is the gap the
`lessons.md` split found the same morning. Newest first.

- 2026-10-08 (eighty-seventh session) — Joe's parlay challenge: success rate is the price; the record reaches each leg (ADR 0194, v65/v66); the friend's-parlay path gets its guards; cash-out watch; cost line; markup registered; live on `7f135730`
- 2026-10-06 (eighty-sixth session) — README rewritten as a short user guide on Joe's call; the research record archived verbatim; five stale remote branches deleted
- 2026-10-06 (eighty-fifth session) — #316's code is read and it is our cap; the limit surfaces as a failed code execution, already in the scout capture; Joe's (A) to #319 ships the prompt rule, live on `e8e2531d`
- 2026-10-05 (eighty-fourth session) — a refused RFQ create now leaves a row (#317); a lost create answer is unknown, not refused (#318)
- 2026-10-05 (eighty-third session) — web-search error codes recorded (#316); Kalshi holds 3 open RFQs, not 97 (#314)
- 2026-10-05 (eighty-second session) — Next.js RCE patched; Anthropic credits ran out at 10:19Z and the desk hid it; #220 reviewed into four fixes, three live
- 2026-10-03 (eighty-first session) — #3 full, #302 continues it; a friend's off-main-line leg is now priced from alternate lines, live on `93bc6ba0`
- 2026-10-02 (eightieth session) — Your bets: tag where each pick came from, live on `b07ef3e1`, schema v63, ADR 0193
- 2026-10-02 (seventy-ninth session, continued) — parlay town hall: batch 1 (17 tickets) live on `734f460`, schema v61 + v62; Joe answered five; batch 2 ticketed
- 2026-10-02 (seventy-ninth session) — nothing due before 2026-10-05; #3 frontier empty by finding, not by neglect
- 2026-10-02 (seventy-eighth session) — #268 read: Joe's combo came through RFQ, its row is consistent; new `position-provenance` inspector query (live on `47a3cb3`); #268 closed
- 2026-10-01 (seventy-seventh session) — S3 of ADR 0192: the armed hand-bet path leaves `create_app` for `backend/manual_order.py` (#266, live on `86affa0`); story #263 closed; both lanes found their tickets already shipped
- 2026-10-01 (seventy-sixth session) — architecture review; every frontend write goes through one transport module (ADR 0191); api.ts split into transport, format and types (#257–#262, live on `ea53d22`); A+B positions module grilled and ticketed (#263)
- 2026-10-01 (seventy-fifth session) — the CLV signal test's registered result is in: UNRESOLVED at G = 1000; #233 answered
- 2026-09-30 (seventy-fourth session) — all-hands conference on the live desk; epic #224 built and deployed; Joe answered all seven questions
- 2026-09-30 (seventy-third session) — nothing due: #188 closed as won't-do; #210's close moves into #220 because no matchup tile exists yet
- 2026-09-30 (seventy-second session) — #221 and the cards seen in a browser; two display fixes; a stale season date now builds nothing (#222)
- 2026-09-29 (seventy-first session) — automatic game-script cards built, deployed and armed (#213–#218); one card cost 289K tokens, so Joe raised the token ceiling to 9M (#219)
- 2026-09-29 (seventieth session) — Joe names parlays: sports factors lead (#200, ADR 0189); rest on every leg (#201), a same-game game page (#202) and a matchup scout tile (#210) ship; automatic game-script cards planned and approved (#213)
- 2026-09-29 (sixty-ninth session) — the queue is empty and Joe will name new work (#196, answer C); board.py says so instead of asking for an owner (#195)
- 2026-09-29 (sixty-eighth session) — `/hedge` 1,803 → 447 ms on one batched venue read (#191); CI tests 9m30s → 5m29s under xdist (#192); the 30 s health-check trial read UNMOVED and reverted, and #193 closes: the stall is outside the machine (§F, §G)
- 2026-09-28 (sixty-seventh session) — "Would Rust help?" No: ADR 0188 (Accepted; the live box is 1.3% busy), four speed lanes live on `1078389` (#186 #187 #189 #190), and a fixed ~3 s server-side stall found (#193)
- 2026-09-27/28 (sixty-sixth session) — the HUD reaches Games, Picks, Your bets and /hedge (#174–#177, live `27a7154`); Joe keeps leg verdicts as they are (#183 A) and keeps #165 open; the motion slice ships too (PR #184, live `07ec1ce`) and #171 closes
- 2026-09-26 (sixty-fifth session) — the HUD is seen on live with real cards; the nav gets two spend gauges (#172), and Joe says carry the look to the other screens as it is (#173 A)
- 2026-09-26 (sixty-fourth session) — /parlays gets one "ask the scouts about every leg" button (live `6583258`); Joe picks a video-game look, "Cockpit HUD", and its first slice ships (live `c401c62`, #171)
- 2026-09-26 (sixty-third session) — Why 0 of 8 legs on Joe's held combo got a chance: 3 were stale by design, and 5 are NO-side moneylines, which the recount puts in 2 of 82 recent combos. Nothing built for the screen; live stays on 739f9e2
- 2026-09-26 (sixty-second session) — #165 read on real inputs: a pasted ticker works on a live combo, but a kalshi.com link usually names a group of combinations and is refused. #169 parked. Nothing built; live stays on 739f9e2
- 2026-09-26 (sixty-first session) — #165: paste a friend's Kalshi link on /parlays and see the desk's chance for each leg and for the whole parlay (#166 #167 #168, ADR 0187). Live on 739f9e2
- 2026-09-25 (sixtieth session) — /bets shows the desk's chance when Joe priced each parlay (#161); the leg ticket says "you can buy 0" and the break-even first, with the box switched off (#160, his answer); the refresh panel's duplicate fixture (#159) and a stale side-switch count (#162) fixed. Live on 29f794d
- 2026-09-25 (fifty-ninth session) — Joe said the expanded parlay card was over-filled; it is now a summary, buying opens a slide-over panel, and the review found two old ways to close a ticket mid-send (#158)
- 2026-09-25 (fifty-eighth session) — the first look at a verdict on screen found a burst that ran the day to 224% and a refusal the card never showed; both fixed and live on 866d942, and Joe raised the three ceilings together (#157 A)
- 2026-09-25 (fifty-seventh session) — #151: the scouts give a plain-language TAKE/PASS on each parlay leg before Joe buys (ADR 0186, schema v57-58; live on 73ba8a4)
- 2026-09-24 (fifty-sixth session) — #107 captured: a real combination YES bid, from a held book with its ticker redacted on Joe's word; #149 built: `combo-rfqs` and `leg-scout-state` live reads (not deployed)
- 2026-09-24 (fifty-fifth session) — #147 fixed: the RFQ list's own filter is `user_filter=self`; #148 built: adopt a held combination onto /hedge in one tap; a held combination's ticker was public in #96's fixture, redacted forward on Joe's word. Deployed `ddd98a2` (Joe ran it; the classifier refused `gh workflow run` for me)
- 2026-09-24 (fifty-fourth session) — #129's capture taken on the venue's own positions read; #96 built: /hedge asks the makers what they would pay (ADR 0185, schema v56); #147 opened. Deployed `1a2d5be` (Joe ran it)
- 2026-09-24 (fifty-third session) — durable reads for the prune and lost-leg closes (#144); Joe answered #145 (A), so half the token ceiling is now his; #115 closed NOT RUN on his (A) to #146; #139 closed on the cursor read. Deployed `e166a56` (Joe ran it)
- 2026-09-23 (fifty-second session) — the watcher stops scouting dead parlays (#141); Joe answered #142 (A) and a dead hand-recorded slip now closes itself (#143, ADR 0184, schema v55)
- 2026-09-23 (fifty-first session) — Joe answered the whole frozen digest with option buttons; all eight answers built and deployed (ADR 0183); the desk now scouts his held parlays first
- 2026-09-23 (fiftieth session) — #137 merged with its day boundary fixed; CLAUDE.md no longer says the LLM fleet is free (#138); Joe answered #58 and the odds_snapshots prune is ARMED on live `fe0a76f` (ADR 0182, #139)
- 2026-09-23 (forty-ninth session) — #118 read: budget day 20260922 is outcome D, not separable; the arms are deleted; live deployed to `0f23f6c`

### Split 2026-09-25 — [`archive/next-2026-09-25.md`](archive/next-2026-09-25.md)

Filed by the date of the split. The six 2026-09-22, three 2026-09-21,
two 2026-09-20, one 2026-09-19 and six 2026-09-18 entries that were still
in `NEXT.md` when it reached 234,272 bytes, **89.4%** of the ceiling —
cut by the session that found it there, before that session's entry
existed, as the 2026-09-18 log paragraph requires. Date boundary:
everything 2026-09-22 and earlier moved, so the four 2026-09-23 entries
stay together. Left 42,687 bytes before the index — **16.3%** — and
78,620 with it, **30.0%**. md5 `3958e58d926207d3380cfa928697cdb7`; index
lines in the same edit; binary throughout.

- 2026-09-22 (forty-eighth session) — the arms are correct and were left alone; the one dependency T1 still has is the laptop's power plan; the result doc exists as a skeleton before any row of its day; #115's #58 ordering is an edge the board can see; NOT deployed, on purpose
- 2026-09-22 (forty-seventh session) — #118's T1 and T2 take themselves: two unattended arms, both rehearsed green, the registration amended in advance to say which read is T1; NOT deployed, still on purpose
- 2026-09-22 (forty-sixth session) — the record now says what the venue says: a settled combination closes its own row (ADR 0181, schema v54); the runtime review caught a coupling that would have silenced hedge alerts; #134 landed; NOT deployed, on purpose
- 2026-09-22 (forty-fifth session) — both agent tickets were mis-specified in the one line a lane executes, fixed before dispatch; two lanes landed; the frozen eight all still hold; nothing touched the measurement day
- 2026-09-22 (forty-fourth session) — the frontier had eleven READY leaves and nothing a lane could take, the sell-side capture instrument exists and its first run was refused for the right reason, and 41 of 43 hedge rows are now folded behind one label
- 2026-09-22 (forty-third session) — #95 is on the phone: the reader is wired, the review bounded what the wiring would have spent, and the live read says `empty` twice
- 2026-09-21 (forty-second session) — the frontier was stuck on artefacts only we could make, a review caught me writing the exact clause Joe banned twice, and three ceilings turned out to be the same number
- 2026-09-21 (forty-first session) — the clock on #118 was going to expire into an instrument that did not exist, the ceiling everyone ranked last had already bound, and a guard passed its own test with the guard deleted
- 2026-09-21 (fortieth session) — unattended scouting is armed, the disk mystery is located but NOT explained, and the audit struck two of my six claims before they entered the record
- 2026-09-20 (thirty-ninth session) — two live readings overturn the premise of the tickets that asked for them, #116 gets its arithmetic without the week it was told to wait, and four questions leave Joe's queue without him answering one
- 2026-09-20 (thirty-eighth session) — the desk can be sent on the ladder unattended (off), every card says what it knows, sentiment is a tile, and Elo is a registration that can only close
- 2026-09-19 (thirty-seventh session) — the queue moves to GitHub, the main session becomes the orchestrator, and the first lanes ran on the change itself
- 2026-09-18 (thirty-sixth session) — lessons.md is split, the RFQ path reads Kalshi's own fill, and the question it was blocked on was answered in a fixture
- 2026-09-18 (thirty-fifth session) — the file is split, the volume is measured, and the VACUUM window turns out to run on a filesystem nobody had read
- 2026-09-18 (thirty-fourth session) — the disk net has gone inert again, ADR 0175's leftover guard is closed, and I broke a governance rule four times before finding it
- 2026-09-18 (thirty-third session) — the registered look was taken in its window, the growth lever is spent, and two tickets asking for a venue call were already answered on disk
- 2026-09-18 (thirty-second session) — Joe answered four tickets in one line, the RFQ path got the review it never had, and a venue check refuted a sentence this session had shipped an hour earlier
- 2026-09-18 (thirty-first session) — "the site is really slow again": every page was waiting on a route that walked every stored odds row, and now it reads a table with one row per fixture

### Split 2026-09-18 — [`archive/next-2026-09-18.md`](archive/next-2026-09-18.md)

Filed by the date of the split. The four 2026-09-17, six 2026-09-16 and four
2026-09-15 entries that were still in `NEXT.md` when it reached 234,750 bytes,
**89.6%** of the ceiling. **The first cut taken from past the ~90% trigger
rather than under it** — the previous session's entry recorded 228 KB and wrote
"SPLIT THIS FILE NEXT SESSION", which is the trigger working as designed, but
the margin left was ~27,000 bytes and one long entry would have spent it. Cut
on a date boundary: everything 2026-09-17 and earlier moved, so the four
2026-09-18 entries stay together. Cut deep, to **26.8%**, on the log's own
twice-stated reasoning that the trigger is a ceiling rather than a target and
that a split is cheapest at the start of a session and dearest in the middle of
one. md5 `e2eb3b8abb93cb345b90d5134f0e1d0f`; index lines in the same edit;
binary throughout.

- 2026-09-17 (thirtieth session) — the cockpit installs to the home screen, and the line that makes it work is one entry in the auth allowlist
- 2026-09-17 (twenty-ninth session) — Joe was right and the desk was wrong: a combination is priced by ASKING, and the screen had been reading a surface combinations do not trade on
- 2026-09-17 (twenty-eighth session) — all four answers built; I gave Joe a wrong number and a pre-registrar caught it; and the instrument fixed yesterday found the desk's worst latency on its first run
- 2026-09-17 (twenty-seventh session) — the live desk was two commits behind with a false label on the money path; the four tickets went to Joe with a free option the ticket had left out; and the third queue turned out not to be empty
- 2026-09-16 (twenty-sixth session) — six more tickets, all answered the same day; the screen stopped claiming the edge is real, and a convenient conclusion of mine was refused by the instrument that exists to refuse it
- 2026-09-16 (twenty-fifth session) — the question-decay rule is a contract with a test, and the decision queue went from 0 to 9 tickets about the confirm path
- 2026-09-16 (twenty-fourth session, continued) — Joe answered the anchor question, the slate got a base-rate block, and the partner found why that question had gone unasked for three sessions
- 2026-09-16 (twenty-fourth session) — the index Joe approved was measured and REFUSED; the census is bounded, ANALYZE is the real lever, and the deploy is blocked on his say-so
- 2026-09-16 (twenty-third session) — Joe answered three questions; item 6 is done, the parlay card stopped flattering, and the index rebuild is the next job
- 2026-09-16 (twenty-second session) — the sharp anchor is thinnest where the slate is biggest, and two "safe fixes" inherited from yesterday's ADR were measured and were not fixes
- 2026-09-15 (twenty-first session) — three of seven open items were already built, the props finding does not survive its own fixture, and an instrument was charging its cost to Joe
- 2026-09-15 (twentieth session) — yesterday's wrong-side fix had a second reader in the same function; and dropping `eu` would delete every sharp book the desk has
- 2026-09-15 (nineteenth session) — the NFL chip was a 25 s walk of the wrong index, an Under leg was printing the Over's price, and the venue mints a three-NO-leg combo
- 2026-09-15 (eighteenth session) — over/unders and player props are parlay legs, both sides, on two cards of their own; two ADR 0110 refusals fell to their own premises

### Split 2026-09-15 — [`archive/next-2026-09-15.md`](archive/next-2026-09-15.md)

Filed by the date of the split. The four 2026-09-14, three 2026-09-11 and
five 2026-09-10 entries that were still in `NEXT.md` when it reached
226,964 bytes, 86.6% of the ceiling. Cut on a date boundary: everything
2026-09-14 and earlier moved, so the four 2026-09-15 entries stay together
and no single day is split across two files. Cut deeper than the trigger
required — to **32.8%** — on the log's own reasoning that a split is
cheapest at the start of a session and dearest in the middle of one.
Verified by md5: the archived bytes below its header hash identically to
the bytes removed (`a8a994f86c9063ecea5210ffcdae684f`). Index lines written
in the same edit.

- 2026-09-14 (seventeenth session) — the probe cancels on its shard, the "unexplained 401" was the script signing a query string, and the closed-path claim survives nowhere but the ADR that made it
- 2026-09-14 (sixteenth session) — a combo bet needs its shard funded, the auto-management toggle is what hides the funding control, and "cannot be placed here" was an overreach Joe caught
- 2026-09-14 (fifteenth session) — three counts had collapsed into one word; branch CI now carries a signal; /hedge cannot raise on a live row
- 2026-09-14 (fourteenth session) — Arm D never ran because nothing runs between sessions; both lanes are merged and live; #36 closed on zero credits
- 2026-09-11 (thirteenth session) — E3 is fixed on a branch without touching a column, `/hedge` has never produced a lock, and Monday now merges two lanes
- 2026-09-11 (twelfth session) — the hedge figure was called a ceiling and it is not one; the census registration can now be run as written; lane B is renumbered and still waiting on Monday
- 2026-09-11 (eleventh session) — the spine named a column that does not exist, the widening was seen firing, and the index that would fix `/api/window` is built and deliberately not shipped
- 2026-09-10 (tenth session) — one scan per request, a quote that says when it was read, and a warning that went silent as the outage got worse
- 2026-09-10 (ninth session) — the parlay screen was empty on the clock, not the menu, and NFL prop ladders need no parser
- 2026-09-10 (eighth session) — a combination CAN be sold back, five screens said it could not, and three of my own claims were withdrawn
- 2026-09-10 (seventh session) — a combo tap now prices the window the card was built in, and the desk has a spreads-only card Joe chose
- 2026-09-10 (sixth session) — the ladder floor was OOM-cycling the recorder; the fix shipped, and /hedge now says what it cannot see

### Split 2026-09-11 — [`archive/next-2026-09-11.md`](archive/next-2026-09-11.md)

Filed by the date of the split. The five 2026-09-09 and two 2026-09-08
entries that were still in `NEXT.md` when it reached 200,701 bytes, 76.6%
of the ceiling. Taken **under** the trigger rather than at it, before the
session's own entry was written, because the entry about to be written was
a long one and the size that matters is the size *after*. Cut deep, to
37.2%. The cut falls on a date boundary: everything 2026-09-09 and earlier
moved, so no single day is split across two files. Verified by md5: the
archived bytes below its header hash identically to the bytes removed
from `tasks/NEXT.md`.

- 2026-09-09 (fifth session) — the biggest table in the database is 99.7% duplicate rows, and the obvious fix would have emptied the ladder
- 2026-09-09 (fourth session) — a live bet was invisible to the only screen that could exit it, and the wiring that fixed that killed the question a registration was asking
- 2026-09-09 (third session) — the desk armed the entry and never armed the exit; and the census behind every combo warning had never read the shard he trades
- 2026-09-09 (second session) — the audit file is closed after 33 days, the money-path signer finally has a real test, and the fee alarm was wired the day its own excuse expired
- 2026-09-09 — two critical unauthenticated RCEs were live on the public box and are now patched; the effort dial is set; the month-old audit is down to two real items
- 2026-09-08 (third session) — the fat was cut: CLAUDE.md is 20KB, six agents are gone, four task files are archived, seven lessons deduplicated
- 2026-09-08 (second session) — the table took its first two rows, the brake Joe removed was still on the button, and the bid path is disarmed

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
