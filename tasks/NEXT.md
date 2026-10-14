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

## 2026-10-14 (ninety-seventh session) — a housekeeping day: live already on `28b0c7a5` (Joe deployed, #393 closed); #383 waits on one tap from Joe; the two 10-13 card failures were #371's bug; D7 ticketed (#394)

- **State at start:** main clean at `28b0c7a5`, no PRs, zero dependabot alerts; live `build.git_sha` = `28b0c7a5` — Joe ran the live deploy himself (run 38514284062), so #386–#392 and #385 are live and #393 is closed.
- **Partner's call: almost nothing is executable today; end short, do not invent work (#196).** #347 stays deferred (saves nothing Joe sees; ~20 registry pins; sits beside the armed app).
- **#383 is built and deployed but unread:** `server_tool_steps` is NULL on all 20 rows 630–649, correctly — the newest agent call (649, 2026-10-13T20:04:35Z) predates the column's deploy (20:05Z), and none has run since. Closing it needs one card or leg-verdict tap from Joe before 2026-10-16 00:15Z, then `flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/inspect_live_db.py agent-spend --days 1"`. Commented on #383.
- **`agent_calls` 644/645 (two `game_script` `api_error`s at 2026-10-13 18:25Z) were ours and already fixed:** `game-script-card-refusals --limit 15` on live reads `TypeError: AsyncMessages.create() got an unexpected keyword argument 'output_format'` — #371, the 94th session's fix. `agent_calls` has no error column; the text lives in `game_script_cards.reason`, joined by `agent_call_id`, and no committed instrument reads it by id.
- **D7 ticketed as #394** (under #244, `owner:agent model:sonnet`): 14 `<h1>` with 5 class strings → one `PageTitle`. Polish; for the nightly routine or a UI session.
- **Not done, named:** the stale lane worktrees. Seven `.next/standalone/node_modules` junctions into main's `frontend/node_modules` were unlinked (main's untouched), but `git worktree remove` of the four locked `agent-*` worktrees and `rm` of three unregistered dirs (`agent-a6be…`, `agent-ae56…`, `lane-390`) plus a stray `.claude/worktrees/frontend/` were refused [Irreversible Local Destruction] by the classifier. **Then done on Joe's word ("You do it"):** all four removed, their merged branches deleted with `-d`, the stray dirs gone; `git worktree list` shows main only, main's `node_modules` intact.

### Still open

1. ~~#383~~ — CLOSED same session: Joe tapped the MIL–LAD Game 3 card; live id 650 carries `server_tool_steps = 6`.
2. #376 — 2026-10-18: re-read NFL card cost on the trimmed prompt, now with step counts; prediction ≈670K.
3. #384 — card tap token hold; blocked by #376.
4. #380 — Joe's question: rebuild a game's card at a different leg count.
5. #394 — one PageTitle style (D7); polish, Sonnet lane.
6. #210 — closes on the first `complete` convening whose board carries the Matchup tile.
7. #360 — college basketball into scope when Kalshi lists it; check 2026-11-01.
8. #361 — 2026-10-27: credit projection after an NBA week; warn Joe before 20,000.
9. #355 — Your bets split by leg count and same-game vs cross-sport; blocked by #331.
10. #347 — the backend no-op sweep and the routes nothing calls; deferred.
11. #337 — 2027-01-15: look B for P1 only.
12. #331 — 2026-11-01: the leg census by kind.
13. #151, #197, #267 — carried forward unchanged.

---

## 2026-10-13 (ninety-sixth session) — UI review: a UX/graphic designer and sharp-bettor read the demo renders, partner ranked them, seven layout lanes merged (#386–#392), on demo at `0ab7ae76`; live deploy refused by the classifier; three copy questions to Joe (#385)

- **Joe's focus: "any ui improvement"** — a UX + graphic designer evaluates the site and its navigation, consulting partner and sharp-bettor. Demo redeployed to main first (`36891cc5`, it was 11 behind), renders at 390/1440 via `check_mobile --shots`. Designer (general-purpose, role prompt) and `sharp-bettor` reviewed in parallel; `partner` merged them into 7 lanes, 3 questions, and rejections.
- **Rejected by partner on prior rulings — do not re-propose:** break-even beside fair on a row (ADR 0071 §2.2; subtraction hands Joe the measured-negative edge); refusal codes → friendly labels/tooltips (#16A, #31); bottom tab bar and moving Gate/Playbook under "More" (#18A); CLV-first on Your bets (#343; no instrument for hand-bet CLV); promoting "Open the ticket" to a filled button (ADR 0071: no manufactured action); market-page "other side" link and "you hold this" marker (3-way markets; a ~2s `/api/hedge` read, #191) — deferred.
- **Built (Sonnet lanes, merged on main):** #386 Games row is a card — kickoff/league/team/side, ask and fair at equal weight, diagnostics behind `Details`, bet + parlay actions inside the card, a failure every row shares stated once ("On every game below: …") via new `TrustNote hideDetails`, `width` hidden when null, no name truncation, stale quote age ochre with `· limit 30s` (never red: #10/#32); #387 Picks ask at the fair chance's weight, stale ask `text-muted` not `opacity-60`, shared quote age once in the header; #388 nav links ≥44px, freshness line on a phone; #389 `/game` heads with teams·league·kickoff (ticker only when the listing has no title — demo has none), "← Games" back link, market → its game, "Send the scouts" outline; #390 Parlays: games without a card are one list, each "Make a card →" to `/game` (no 3/5/8 buttons on /parlays — an NFL tap costs up to ~1M tokens), uppercase league tags; #391 a zero net is `$0.00` neutral ink, empty Open section one line; #392 the refresh panel's shared sentence once (`RefreshOddsButton showCaption`).
- **Pins moved, claims kept:** `test_desktop_tier` ScoutDesk filled accents 1 → 0 (stricter, same intent); `test_games_says_stale_once` age chip red → ochre; `test_bets_sections`/`test_hud_bets`/`test_your_bets_reads_like_bets` read through `netInk`/`netShown`. Two integration breaks the lanes' targeted recipes missed and CI caught: #391's helpers landed inside the colourless by-leg-kind slice (moved out); #386 drew its own `evidence {` line, which `test_trust_surfaces` refuses (now `TrustNote hideDetails`, mutation-verified).
- **Verification:** CI green on `0ab7ae76` (run 38479354470); demo deployed and `build.git_sha` verified; after-renders at 390/1440: no overflow on any page; Games phone page 12,184 → 11,468px (2× DPR) — demo's every-row staleness inflates it.
- **Not done, named:** **live deploy** — `gh workflow run deploy.yml -f instance=live -f confirm_live=kalshi-cockpit` was refused [Production Deploy] by the auto-mode classifier this session; live is still on `36891cc5` (#393). Wave 2 (one PageTitle style, D7) not started — it touches every page and should run alone. Four lane worktrees remain harness-locked under `.claude/worktrees/` (branches merged).
- **#385 answered A1 B1 C1 (Joe, same session), shipped `f9e2e18d`:** Games header keeps #9's one sentence and the server note moved into "How to read this"; Games keeps a one-line signal verdict linking to `/gate#signal-test`, where the full `SignalStrip` now renders; Parlays lede says "beside". CI green (run 38488042249); demo deployed and verified at `f9e2e18d`. Pinned by `tests/test_joes_385_copy_answers.py` + `tests/test_tab_ledes.py`, both guards mutation-checked.

### Still open

1. #393 — deploy `f9e2e18d` (the seven lanes + #385) to live; refused by the classifier this session.
2. #383 — read `server_tool_steps` back on live after Joe's next card or verdict tap, then close.
3. #376 — 2026-10-18: re-read NFL card cost on the trimmed prompt, now with step counts; prediction ≈670K.
4. #384 — card tap token hold; blocked by #376.
5. #380 — Joe's question: rebuild a game's card at a different leg count.
6. #210 — closes on the first `complete` convening whose board carries the Matchup tile.
8. #360 — college basketball into scope when Kalshi lists it; check 2026-11-01.
9. #361 — 2026-10-27: credit projection after an NBA week; warn Joe before 20,000.
10. #355 — Your bets split by leg count and same-game vs cross-sport; blocked by #331.
11. #347 — the backend no-op sweep and the routes nothing calls; deferred.
12. #337 — 2027-01-15: look B for P1 only.
13. #331 — 2026-11-01: the leg census by kind.
14. #151, #197, #267 — carried forward unchanged.

---

## 2026-10-13 (ninety-fifth session) — four builds live: each agent call records its server-tool steps (#383, schema v67), the NFL /game listing names every series (#381), the hand-tick refusal stops naming a cover nobody ticked (#382), and a yes-only leg's NO is offered as a single (#366)

- **No focus from Joe; `/go` start in plan mode.** State clean, live on `633444e`, no PRs. `partner` ranked the board: three builds today, one with a deadline (the step count before Thu 10-16 00:15Z SEA@DEN, so #376's 10-18 re-read can say which lever drives NFL card cost). Ticket hygiene: **#377 closed** (landed `418b75c9`, live); **#370 closed as a delivered finding and split** into **#383** (step count, built) and **#384** (token hold on a card tap, blocked by #376 — the hold's size is #376's output); #381 labelled `model:sonnet` and narrowed to labels only (dropping a same-count group would remove bettable legs).
- **#383 (main, `551980ba`):** `agent_calls.server_tool_steps` = the `server_tool_use` blocks in the returned `Message`, walked beside `tool_errors_from`; the create call is untouched (#371's lesson). NULL when no reply came back, never 0. Captured `anthropic_scout_captured.json` reads 10. `agent-spend` prints the column. Mutations (walk counts the wrong block type; settle writes 0 for no reply) both red. **Live migrated to v67, column read back via `agent-spend --days 1`: NULL on every row, all pre-deploy.** The first number arrives with Joe's next card/verdict tap; #383 stays open for that read.
- **#381 (Sonnet lane, `3a73be81`):** 50 NFL series gained Kalshi-worded labels from a new public capture (`tests/fixtures/series_nfl_live_game.json`, 69 series on SEA@DEN); 0 "Other markets" on the capture; `TestNflSeriesHaveWords` red when one label is removed. Not verified: which of the 69 the catch-all collection offers as legs.
- **#382 (Sonnet lane, `3089f993`, found by partner checking session 94's "Not done"):** a win implied by two team totals with no spread ticked was refused with "and its cover ... are both ticked" — a leg Joe never ticked. The win+cover sentence now fires only when that cover was ticked; else the general "already guaranteed" sentence. `GameLegs.tsx` comment corrected (`coverTickedFor` mirrors only win+cover).
- **#366 (main, `eb49b82d`):** `is_yes_only` is the combination collection's rule, so `allowed_sides` and the mint refusal keep it; the market itself trades NO. `/game` now prices and lists both sides and "Bet this one alone" loops both, still gated on that side's readable ask. **`kalshi-platform` review FAILED the first diff on one sentence** — the NO ticket said the desk had no price when the desk had never priced that side — and **PASSED after fix (a)** (`_price_sides(sides=("yes","no"))` for the listing only; the card path prices its own side). Its gap against the ticket wording: the test flags a game leg yes-only, not a captured prop, and the frontend pin is source text.
- **Dropped on purpose (partner):** general-case `coverTickedFor` greying (a TS copy of the score engine would drift; the server refuses in words); `KXMLBF5`/`KXMLBF3` in the implied-leg check (fails safe — `_score_predicate` returns None, never drops; no refusal observed; MLB ends in ~3 weeks; reopen only if a `duplicated_legs` refusal names one).
- **Verification:** targeted runs green (4,419 over schema/budget/instrument tests; 693 + 669 in the lanes; 658 over game_builder/GameLegs/game_script after #366), ruff and tsc clean; CI green on `edee0f13` and on `eb49b82d`. Live deployed on `edee0f13` (verified `build.git_sha`), then on `eb49b82d` (verified `build.git_sha`).
- **Not done, named:** stale worktree shells under `.claude/worktrees/` (two registered at 0 ahead, ~12 unregistered with one `.next/standalone/node_modules` junction each) — removal was refused by the auto-mode classifier as irreversible; left for Joe. No question for Joe owed (#380 is the one open).

### Still open

1. #383 — read `server_tool_steps` back on live after Joe's next card or verdict tap, then close.
2. #376 — 2026-10-18: re-read NFL card cost on the trimmed prompt, now with step counts; prediction ≈670K.
3. #384 — card tap token hold; blocked by #376.
4. #380 — Joe's question: rebuild a game's card at a different leg count.
5. #210 — closes on the first `complete` convening whose board carries the Matchup tile.
6. #360 — college basketball into scope when Kalshi lists it; check 2026-11-01.
7. #361 — 2026-10-27: credit projection after an NBA week; warn Joe before 20,000.
8. #355 — Your bets split by leg count and same-game vs cross-sport; blocked by #331.
9. #347 — the backend no-op sweep and the routes nothing calls; deferred.
10. #337 — 2027-01-15: look B for P1 only.
11. #331 — 2026-11-01: the leg census by kind.
12. #151, #197, #267 — carried forward unchanged.

## 2026-10-13 (ninety-fourth session) — two errands from Joe's phone: every agent call was dead since #371 (`output_format` on `create`), and a card could carry a leg its other legs guarantee; both fixed, live on `633444e`, Joe got a price

- **Every AI call raised TypeError since #371** (`576445c`). `structured_call` moved from `messages.parse` to `messages.create` and kept `output_format`, which only `parse` takes; cards, leg verdicts and scouts all failed before the network (nothing billed). The schema now rides in `output_config.format` beside `effort`. `TestTheRequestBindsToTheRealCreate` binds the sent kwargs to the SDK's real signature; red on the old code. Lesson in `tasks/lessons.md`.
- **`duplicated_legs` with three legs** (`633444e`). Kalshi refused Joe's 8-leg CLE–TB card: "Over 6.5 runs and Cleveland winning by 2+ already guarantee Cleveland scoring over 2.5". `drop_implied_win_legs` became `drop_implied_legs`: winner/spread/total/team-total legs, either side, read as conditions on the final score; a leg every score winning the others (on other events) also wins is dropped, losslessly. Rung number = whole score needed, checked on every captured strike. The /game hand-tick path still refuses in words (#274 A). Read back off live `/api/game-cards`: the card shows 7 legs, `CLE3` dropped; Joe tapped Get a price and got one.
- **Not done:** the /game screen's tick-time greying (`GameLegs.tsx coverTickedFor`) still mirrors only win+cover; the server refuses the general case in words before any venue call. First-five/first-three winner series (`KXMLBF5`, `KXMLBF3`) are not read by the check.

## 2026-10-13 (ninety-third session) — the master scout's output cap was why #210 never saw a `complete` convening: named and raised to 12,000 (#377, like #338 on the card); #376 has no trimmed reading yet and a 670K prediction; `usage.iterations` is beta-only on the pinned SDK and server-tool caching is already on (#370); seat sweep found no other cap bound

- **No focus from Joe; `/go` start in plan mode.** State clean, live on `bf26c721`, zero Dependabot alerts, no PRs, no lanes (three stale `worktree-agent-*` branches at `b6a45c5a`, 19 behind, deleted). `partner` ranked the board and read `agent-spend` on live itself; its one finding changed the night.
- **#210 was not waiting on the Matchup tile, it was waiting on a cap.** The master scout's call sent a bare `max_tokens=4000` with `effort="high"` (adaptive thinking draws on the same allowance). Live `agent_calls`: row 80 (09-23, 6 findings in) stopped at **exactly 4,000** output tokens and settled `filed_nothing`; row 86 (17 in) used 3,567; row 641 (10-12, 20 in) settled `filed_nothing` with NULL usage (pre-#371). Last 14 days: 8 taps, **0 `complete`**, 6 `failed`, 2 `partial`. #371 fixed the meter, not the cause. Opened **#377** under #197 (owner:agent, model:sonnet), built in a worktree lane (`418b75c9`): `MASTER_MAX_OUTPUT_TOKENS = 12_000` with the evidence beside it, the `DeskBriefing.board` description says "all eight" (it said seven; the Literal has eight members), three tests in `TestOutputCaps`; mutations to 4000 and to "seven" both red; `base.py`'s convening arithmetic fixed on main (`21aca8da`). Worst case +8K tokens a convening, ~0.2% of the 5M ceiling. **#210 still closes on Joe's next tap whose convening settles `complete`** — no convening was fired, it spends his budget.
- **Seat sweep (the new lesson's rule, `agent-spend --days 30`, n = 590 calls):** no other seat sits at its cap. `game_script` max 5,774 of 6000 (n = 174); `game_script_recheck` 864 of 1000 (n = 18, 86%, watch it); `pro_bettor` 968 of 3000; `leg_verdict` 2,609 against 2000 and the staff scouts 10,509 against 6000 — **those two loop over tools, so `max_tokens` binds per sampling step and recorded output exceeds it**; the master has no tools, one step, so its cap bound exactly. Table on #370.
- **#370 docs lookup (`claude-code-guide`, quotes on the ticket):** on the pinned `anthropic==0.120.2`, `usage.iterations` (per-sampling-step tokens) exists **only on the beta types** (`client.beta.messages`); the non-beta `Usage` we read has no such field. The docs do not state whether top-level `input_tokens` is the sum over iterations or the last one. Server-tool results **are already cached automatically between iterations** because the system prompt carries a `cache_control` marker; the meter sums cache reads at full weight by design, so Joe's bill is already partly relieved and the 5M ceiling is not. The two builds stay specced and unscheduled; route (b) for the step count is a beta call plus one column.
- **#376 reading:** neither 10-12 card counts (card 638 NFL 874,736 tokens at 19:05Z; card 643 NHL 272,136 at 23:20Z; both before the 23:28Z #374 deploy). Date stands. Prediction on the ticket: if cost scales with characters, a trimmed NFL card lands near **0.77 × 873K ≈ 670K**, still above the ~400K line, so the section-cut question for Joe is the likely outcome.
- **Verification:** lane ran 593 tests across 17 files green, ruff clean; main ran the scout-desk, budget and session-file tests (116 passed); CI green on `21aca8da` (the suite's count is CI's). **Live deployed and verified `build.git_sha = 21aca8da2087a4dc600a10f8df4957341032d6e6`, every route in `time_live_routes.py` 200 (`/hedge` 307 by design)**; demo deployed after live, same sha, `instance_mode = demo`. The agent ledger for the whole budget day 20261012 (`agent-spend --days 1`, read ~01:15Z): 14 calls, 1.83M of 5M tokens, 41 of 100 searches, no `call_error`, one unmetered row (641, the master, pre-#371), and no call at all after 23:20Z, so nothing has exercised the new cap yet.
- **Not done, named:** whether 12,000 is enough is unmeasured until a rich convening runs; `game_script_recheck` at 86% of its 1000 cap is noted, not raised; #370's two builds unscheduled; no question for Joe owed tonight (the empty #302 frontier is healthy: #376 and #361 produce the next two by design).

### Still open

1. #376 — 2026-10-18: re-read NFL card cost on the trimmed prompt; prediction ≈670K; if the median is still above ~400K, the section cut is a new question for Joe.
2. #210 — closes on the first `complete` convening whose board carries the Matchup tile; the cap that blocked it is fixed (#377, live).
3. #370 — card tap token hold; step count per card (beta `usage.iterations` or the content-block walk, plus a column); main, unscheduled.
4. #360 — college basketball into scope when Kalshi lists it; check date 2026-11-01.
5. #361 — 2026-10-27: credit projection after an NBA week; fit the caps; warn Joe before 20,000.
6. #366 — `/game` offers the single NO on a yes-only prop; unscheduled, main, `kalshi-platform` review required.
7. #355 — Your bets split by leg count and same-game vs cross-sport; blocked by #331.
8. #347 — the backend no-op sweep and the routes nothing calls; deferred.
9. #337 — 2027-01-15: look B for P1 only.
10. #331 — 2026-11-01: the leg census by kind.
11. #151, #197, #267 — carried forward unchanged.

## 2026-10-12 (ninety-second session) — NEXT.md split; an NFL card costs 0.5–1.1M tokens for what it reads (#370, Joe's A to #372 → #374, ADR 0190 Am 4); "books under" counts the anchored books (Joe's A to #373 → #375); key-number flag (#348); the demo /game refusal names no config (#369); the master scout can die silently on a billed call (#371)

- **No focus from Joe; `/go` start in plan mode.** State clean, live on `a2cd7961`, zero Dependabot alerts, no PRs, no lanes. `partner` ranked the board and read `agent-spend --days 3` on live itself. **NEXT.md was 232,027 bytes (88.5%) and was split first**, before anything else: 39 entries 2026-09-23..10-06 to `archive/next-2026-10-12.md` (md5 `9c2d318926dcba2fc88965694477a834`), 83,070 left (31.7%). The plan said 41; the script's count assertion caught it before a byte moved. The cut also removed the rule between the latest entry and the index, which `test_the_latest_entry_ends_at_a_rule_not_at_eof` caught on the first full run; restored.
- **Partner's finding, then corrected twice by measurement.** On NFL Sunday 10-11 nothing bound (4.48M/5M tokens, 61/100 searches, 0 refusals) but five game-script cards took 3.62M. Partner called it "NFL is 4× non-football"; `measurement-skeptic` refused the ratio (the comparator was unlabelled); `game-script-latest-prompt -n 25` then labelled every 10-10 card **ncaaf** (121K–227K), so "football" and "near kickoff" both fell away. Tonight's live listings through the real `build_prompt`: **NFL 921 legs / 233,022 chars; MLB 322 / 77,659; NHL 202 / 48,060; NCAAF 105 / 27,875.** That listing is re-presented on every internal step of the one call, steps are unrecorded, and a card tap holds no tokens (`game_script.py:600-615`). All on **#370**; CLAUDE.md's 178K line corrected (it was automatic cards a day out). Session 91's "the next cap to bind is searches" is dropped (lesson 2026-10-12).
- **Joe's answers (option buttons):** **#372 A** — the card reads five strikes per player-prop ladder, nearest the middle (built #374, `PROMPT_STRIKES_PER_LADDER = 5`, ADR 0190 Amendment 4). **Measured on tonight's live listing after merge: 233,022 → 179,865 chars, 23% off, not baseball-sized** — 105 of 150 live ladders hold ≤5 strikes, so the bulk is many players at few strikes; going further means cutting whole sections, which is a new question if **#376** (2026-10-18 re-read) says the cost is still 0.5M+. **#373 A** — "books under" counts the anchored books (built #375). Merge+deploy of both batches approved.
- **#375 needed main's hand:** the lane subset the one distribution the row, the strip and Willy read, which turned `tests/test_api.py`'s ADR 0021 §7.2 pin red (the slate's distribution is deliberately unanchored so the screen never shows the sharp consensus back to itself — a point #373's question did not carry to Joe; recorded on the ticket). Main serves two objects now: `books` unchanged and `books_anchored`; the row's figure reads the anchored one and falls back to `books`, so an unreadable subset still prints "books —" (#353). Mutation red on main.
- **Other lanes (Sonnet, worktrees):** **#348** `9dc5f78a` → `a9627f8d`: `backend/core/key_numbers.py`, `key_number` on `/game` spread legs and Check-a-parlay legs (NFL/NCAAF only), "on 3"/"crosses 3" in a `<Term>`, glossary **key number**; its new exported `KeyNumber` type tripped the types-file inventory (`test_wire_types_live_by_area.py`) and the HUD meta-test that runs it — fixed on main (`e53c59c2`). **#369** `8262eff1` → `fa5fb3c8`: the `/game` 503 on a keyless instance says "no Kalshi credentials on this instance" and logs the variable name instead of printing it. The Games rows' raw reason codes were NOT touched: Joe's 16A (2026-09-02, `slate/page.tsx:611-624`).
- **Reads, no build:** #210 — tonight's tap (BUF@LAR) filed two sourced `matchup` facts with no probability/pick/edge, but the **master scout settled `filed_nothing` with NULL usage on a call the vendor billed** (`structured_call`'s `ValidationError` path, `base.py:629-658`, returns no usage; #365 labelled the credit failure one path earlier) → **#371**, main. #210 stays open on the tile. "books —" was on 36/100 rows, every football and baseball row → #373. #368's Discord delivery: still no outage to verify it against.
- **Verification:** full suite on the batch-1 tree 10,118 passed, 2 failed (the inventory pin and its meta-test; fixed `e53c59c2`); full suite on the final tree: 10,127 passed, 1 failed (the same inventory pin, one commit before its fix); the fix's own tests green and CI green on `e53c59c2`; ruff, tsc and `next build --webpack` clean; CI green on `e53c59c2` and on `172b7344` (the refusal sentence gained its capital and full stop after the demo screenshot showed "instance Nothing"). **Live deployed and verified `build.git_sha = 172b734438704d28eb27a5253728cb89167af99f`, every route in `time_live_routes.py` 200 (`/hedge` 307 by design)**; demo deployed after live, same sha; its 390 screenshots: `/game` prints "No Kalshi credentials on this instance." and no variable name, Games rows print "0/1 books under" where they printed "books —".
- **Joe's errand after the handoff: #371 built on main (`bf26c721`), live and demo verified on it, CI green.** `structured_call` calls `messages.create` and runs the SDK's `parse_response` itself, so a billed reply that fails to parse settles `schema_mismatch` with its real tokens and a refusal settles `refusal` with its tokens (that branch ran for the first time); only a call that never returned settles NULL. Every test double now stubs `create` and dispatches on the schema title (`output_model_name`); the mismatch case is a captured `Message` cut in half (`tests/test_structured_call_keeps_usage.py`, 8 tests; mutations red twice). The scout board's partial sentence adds "or his answer did not parse". Not built: a per-row reason on the briefing for why the master filed nothing (needs a column).
- **Not done, named:** #370's two builds (a token hold on a card tap; the step count recorded from the response's content blocks, a schema change) are specced and unscheduled. The NFL listing has 11 "Other markets" groups (6–112 legs each) the card reads unlabelled — noted on #370, not chased. The trimmed prompt is 23% smaller, not half; #376 decides. No `count_tokens` was run (no local key): every prompt size here is characters. Real football/baseball rows printing "x/N books under" on live: read after the deploy, 100 of 100 rows print (88 from the anchored object, 12 unanchored), where 36 printed "books —" an hour earlier.

### Still open

1. #376 — 2026-10-18: re-read NFL card cost on the trimmed prompt; if the median is still above ~400K, the section cut is a new question for Joe.
2. #370 — card tap token hold; step count recorded per card (schema); main, unscheduled.
3. #371 — CLOSED after the handoff: built, live on `bf26c721`.
4. #210 — closes on the first `complete` convening whose board carries the Matchup tile (blocked by #371 in practice).
5. #360 — college basketball into scope when Kalshi lists it; check date 2026-11-01.
6. #361 — 2026-10-27: credit projection after an NBA week; fit the caps; warn Joe before 20,000.
7. #366 — `/game` offers the single NO on a yes-only prop; unscheduled, main, `kalshi-platform` review required.
8. #355 — Your bets split by leg count and same-game vs cross-sport; blocked by #331.
9. #347 — the backend no-op sweep and the routes nothing calls; deferred.
10. #337 — 2027-01-15: look B for P1 only.
11. #331 — 2026-11-01: the leg census by kind.
12. #151, #197, #267 — carried forward unchanged.

## 2026-10-11 (ninety-first session) — the Anthropic credit lapse found and labelled (#365; Joe's B to #367 → #368), every budget refusal names its cap and reset (#363), the combination cost line states the price (#354, PR #362), one definition of a book and one age on a Games row (#353), `check_mobile --game-event` (#364), #338 closed

- **No focus from Joe; `/go` start.** State clean, live on `cf46f995`, zero Dependabot alerts, one routine PR (#362 for #354). `partner` ranked the board and ran two committed live instruments itself (`agent-spend --days 2`, `game-script-card-refusals --limit 120`, ~14:40Z).
- **Partner's two findings that changed the plan:** (1) **#338 closed early**: the 5M token ceiling is independent of the per-call output cap, and the evidence already existed: 13 metered cards after the 6000 cap went live, 7 wrote 3,036–5,349 output tokens (cut off under the old 3000), 0 `max_tokens`/`json_invalid` refusals in the newest 120. Watch item: the largest card used 89% of 6000. (2) **The Anthropic account ran out of credit Sat 2026-10-10 23:50–23:55Z**: seven calls failed ("Your credit balance is too low…"), six scout-staff calls were settled `filed_nothing` (`scout_desk.py:489`), and calls worked again by 00:04Z. Session 90's 00:30Z verification missed it (lesson 2026-10-11).
- **The next cap to bind is searches, not tokens** (partner): a leg verdict reserves 3 searches, so 100/day stops verdicts at ~33/day while 5M tokens allows ~100; budget day 10-10 reached 78/100 searches against 3.16M/5M tokens. Not raised: copy first (#363), measure, then ask Joe.
- **Joe's answers (option buttons):** **#367 B** (he tops up the Anthropic balance by hand; build a phone alert → **#368**) and merge + deploy the whole lane batch.
- **Lanes (Sonnet, worktrees):** #354 PR #362 finished on `lane-354` (`ce7066de`: no fallback to the ladder card's older joint beside a fresh price; "books" is a glossary Term) → `22ce1978`. #363 `16931ef9` → `1d624f2e` (`plain_budget_refusal` in `routers/game.py` reuses #358's clock: "The scouts have used today's web-search allowance. They're back at 3:00 AM PT, in about 6 hours."; leg verdicts, Check a parlay, scout desk tap and served refusals). #353 `7ad665c5` → `c07049a7` (books-under figure only when its denominator equals the anchored book count, else "books —") and `4c29367c` → `ff757128` (TrustNote `hideAgeChecks` on the Games row only). #364 `b427a55b` → `fe8ec86a`. #365 `8c6516a4` → `e15c9b53` (`call_error` settles `api_error:credit`/`api_error`; `is_credit_exhausted` in `agents/base.py`; screens read scout state from `scout_briefings`, so no screen moved). #368 `98e8ed19` → `e29811a5` (`backend/notify/credit_alert.py`: a call settled `api_error:credit` claims one `notifications` row, kind `ai_credit`, key the budget day, and pushes through the existing Discord notifier; the refused card, leg verdict and scout row say "The AI account is out of credit. This is paused until it's topped up."; lane full suite 10,058 passed, 974 re-run on main). Every guard mutation-red in its lane. Real Discord delivery of `ai_credit` is unverified until the next outage.
- **Verification:** full suite on the merged tree of the first three lanes 10,065 passed, 0 failed (15:00); ruff, tsc and `next build --webpack` clean; the later two lanes' tests re-run on main (604 and 829 passed); CI green on `ff757128` and `e15c9b53`. **Live deployed and verified `build.git_sha = e15c9b53a7896d83905240fa4725f637f79bbbf1`**, status ok; every route in `time_live_routes.py` answered 200 (`/hedge` 307 to Your bets by design, #240). Demo deployed after live, same sha; its 390 Games screenshot shows "books —" and the quote age once, in the red chip. **#368 then deployed: live and demo verified on `a2cd7961fcef24b30b153acd483f56d598ed1c75`** (CI green, status ok, `notifications_configured: true` on the web process).
- **Not done, named:** #356's single-leg ticket still has no picture: the demo `/game` page has no Kalshi credentials or card, so `--game-event` proves the route fits, not the ticket. The demo `/game` page prints a raw config sentence naming `KALSHI_PRIVATE_KEY_PATH` on load (demo only, pre-existing). On live, "books —" will show on every row whose anchored set is smaller than its quoting set, possibly most rows; read it on a busy slate. `no_card_line` and the Odds API credit refusal keep their own wording (#363 report). Games rows print raw codes (`suspicious_edge`, `stale_kalshi_quote`) beside their plain sentences. `tasks/NEXT.md` is ~88% of its budget: split it before the next entry.

### Still open

1. #360 — college basketball into scope when Kalshi lists it; check date 2026-11-01.
2. #361 — 2026-10-27: credit projection after an NBA week; fit the caps; warn Joe before 20,000.
3. #366 — `/game` offers the single NO on a yes-only prop; unscheduled, main, `kalshi-platform` review required.
4. #355 — Your bets split by leg count and same-game vs cross-sport; blocked by #331.
5. #347 — the backend no-op sweep and the routes nothing calls; deferred.
6. #348 — key-number flag on NFL/NCAAF spread legs; reconsider next week.
7. #337 — 2027-01-15: look B for P1 only.
8. #331 — 2026-11-01: the leg census by kind.
9. #210, #151, #197, #267 — carried forward unchanged.

## 2026-10-10 (ninetieth session) — "more singles" and the cap that actually blocked him: token ceiling 5M (ADR 0190 Amendment 3), a leg can be bet alone on `/game` (#356), Games one row per market side in kickoff order (#357), Parlays lists tonight's games card or not (#358), #359 answered B

- **Joe's ask (2026-10-10 ~23:00Z):** "I want to see more singles and probably [Kalshi/maybe] increase my API cap", then a phone screenshot of the Parlays page printing `AGENT_MAX_TOKENS_PER_DAY 9000000 x (1 - SCOUT_AUTO_TAP_TOKEN_SHARE 0.75) = 2250000` on every NCAAF game: "whatever it is is blocking me fix it".
- **Which cap bound (measured first):** the odds feed was nowhere near its cap — `credits-month` 3,346 of the plan's 20,000 for 10-01..10; `credits-by-sport` 123–591 a day over 15 budget days against the 700, never bound; Kalshi reads cost nothing and `read-incidents` shows no throttling. The block was session 89's own 2.5M token ceiling, deployed ~20:00Z into a budget day that had already recorded **2,838,176 tokens by 16:31Z** (`agent-spend --days 2`, all the automatic watcher before it was switched off), so `AgentBudget` refused every call — his taps included — until the 10:00Z reset. **A ceiling lowered below the day's recorded spend is a lockout, not a cap** (lesson, and the rule in ADR 0190 Amendment 3: read `agent-spend --days 1` before moving any `AGENT_MAX_*` down).
- **Unblocked that night, two live deploys, on his "fix it":** `AGENT_MAX_TOKENS_PER_DAY` 2.5M → **5M** (`0931303a`); then `no_card_line` tells a watcher refusal (`is_unattended_refusal`, the two prefixes `game_script_watch.py` writes) from a tap the ceiling refused — the first says "Open the game and tap Build card", the second repeats the budget's plain sentence (`7b7e663b`, verified on live: 14 games listed, 0 config names). The stored reason still names the dial (`test_game_script_watch.py` pins it); the screen pin has the tap refusal as its positive control.
- **What bounds the singles he sees (live, 23:06Z Saturday):** `/api/slate` had 506 rows in its window = **128 tickers, every one repeated** (max 14 rows a ticker), and the screen's default LIMIT 100 ordered by the inert `suggested_contracts` showed an arbitrary slice; **every row was a moneyline** — spreads and totals write no `recommendations` row by ADR 0070; Picks hid 34 games and all 34 kick off 12 h+ out (hourly cadence beyond 12 h, ADR 0111 — by design, no build); tonight's 33 tickers were all current and actionable. `partner` ranked it (and corrected: "65 games" includes next week's NFL; tonight is ~38; the 100 of 506 are repeats, not singles): the singles were already on `/game/<event>` behind a two-leg parlay builder.
- **Lanes (Sonnet, worktrees, each full-suite green; merged as one batch on Joe's answer, suite on the merged tree 10,042 passed, tsc and `next build --webpack` clean):** #356 `8986151e` — every leg on `/game/<event>` mounts a "Bet this one alone" `ManualTicket` per allowed side on its own market; `kalshi-platform` **failed** the review on one case (a named side whose ask vanished between page load and tap opened the ticket on the other contract via `preferSide`'s fall-back, and `reread` did the same), fixed on main in `ManualTicket.tsx` (`ff92ef3c`: a named side with no ask blocks, a re-read never switches sides; three source pins) — the same latent fall-back had applied to the parlay-card and market-search callers. #357 `bb3ee416` — Games serves each (ticker, side) once, freshest row, kickoff order, counts on the deduplicated population; the per-ticker version broke `test_row_names_its_own_side` (YES and NO are two bets), so per side. #358 `a7c95466` — the Parlays list reads every in-scope game in the next 24 h from `kalshi_events`→`event_links`→`odds_fixtures` (three SEARCHes, plan pinned) with or without a card, and a ceiling refusal names the reset in Pacific time from the budget's own day-start hour.
- **Joe's answers (option buttons, within minutes):** merge + deploy the batch as one; **#359 B** — US leagues plus college basketball when Kalshi lists it, the $59 plan pre-approved (he purchases the day the projection crosses 20,000). Follow-ups: **#360** (NCAAB scope entry when listed; NCAAB is NOT in `IN_SCOPE_LEAGUES` — the partner's "it arrives in November" was wrong) and **#361** (dated 2026-10-27: credit projection after an NBA week; NBA puts the busiest Saturday at ~706–726 against 700 by an n = 15-day estimate).
- **Deploy:** CI green on `cf46f995` (run 38097930494); live deployed with the authorised form and verified `build.git_sha = cf46f995433c6134ddb2ebb0303e3410f5c17f6c`, status ok. Read on the new build (~00:30Z): `/api/game-cards` lists 20 games in 1.3 s (11 watcher refusals now worded as the tap, 1 built, **8 with no row at all** — the games the old list would not have shown), 0 config names; `/api/slate` 182 market-sides in the window, 100 returned, each (ticker, side) once, kickoff-ordered, 1.9 s warm (5.1 s on the first read — watch it on a Saturday slate, #357's own "not verified"). Picks ranked 0 with 25 `stale_consensus` at 00:30Z with nobody attending — the hourly floor, by design. Demo re-deployed after live (one at a time; run 38098442580).
- **Housekeeping:** `tasks/lessons.md` split at 233,027 bytes (88.9%) → 156,904 (59.9%); 29 lessons of 2026-09-16..19 in `tasks/archive/lessons-2026-10-10.md`, md5-verified, index lines moved, the missing 2026-10-10 index block added (`3a24a56c`). Memory: which cap binds before raising one.
- **Not done, named:** budget refusals on other screens (leg verdicts) still print the budget's bare sentence without the reset clock (#358 did the game-cards list only); `check_mobile.py` cannot visit `/game/<event>`, so #356 has no screenshot — add a `--game-event` option; a yes-only prop's single NO is never offered (platform note, not blocking).

### Still open

1. #354 — the combination cost line says what the price means; sonnet lane, ready.
2. #353 — Games row: "0/5 books under" beside "1 book(s), need 2", and the age said twice.
3. #360 — college basketball into scope the day Kalshi lists it (Joe's B to #359); main.
4. #361 — 2026-10-27: credit projection after an NBA week; fit the caps; warn Joe before 20,000.
5. #355 — Your bets split by leg count and same-game vs cross-sport; blocked by #331.
6. #347 — the backend no-op sweep and the routes nothing calls; deferred.
7. #348 — key-number flag on NFL/NCAAF spread legs; unscheduled.
8. #338 — after a full budget day on the 5M ceiling: `game-script-card-refusals` near zero `max_tokens`, then close.
9. #337 — 2027-01-15: look B for P1 only.
10. #331 — 2026-11-01: the leg census by kind.
11. #210, #151, #197, #267 — carried forward unchanged.

## 2026-10-10 (eighty-ninth session) — the desk through a professional bettor's eyes: ADR 0195; cards off, pushes off, ceiling 2.5M (#349–#351 A); four dead screens deleted (#342); the vig unit bug fixed (#341); Your bets leads with the record (#343); Games/Picks/Playbook copy (#344); verdict take rate (#345)

- **Joe's ask (2026-10-09):** evaluate the site as Billy Walters would, critique it, improve it, take away the useless stuff. `sharp-bettor` reviewed real screenshots of the demo (`scripts/check_mobile.py --shots`, 390 and 1440) through the lens of Walters's public record; `partner` ranked it, ran `agent-spend --days 14`, and argued back (not "costs more than you bet", the friend tag already exists, the dead-code sweep earns nothing); `measurement-skeptic` audited the spend aggregation before a number entered the record. The critique for Joe is a private page: https://claude.ai/artifact/4HotGhdwkRgUXrGHKKox7Q. Record: **ADR 0195**, ADR 0190 Amendment 2, ADR 0098 and ADR 0076 amendments.
- **Joe's answers, in-session with option buttons:** #349 **A** (automatic game-script cards off, tap only; `AGENT_MAX_TOKENS_PER_DAY` 9M → 2.5M), #350 **A** (parlay pushes off, ladder view kept; new `PARLAY_PUSHES_ENABLED`, both guards mutation-red), #351 **A** (delete `/board`, `/ledger`, `/estimate`, `/dashboards`), #352 **A** (the sharp-book base rate box stays folded at the foot of Games), and merge + live deploy as one batch. All four tickets closed with the letter.
- **The measurement (audited):** 39.47M tokens recorded over 2026-09-26..10-09, a floor (92 of 453 calls NULL usage); automatic cards 74.1%, leg verdicts 25.6%; since cards began a mean 3.35M a day (median 2.56M, range 1.51M–7.20M, 10 complete days); a built card median 178K (mean 200K, n = 105); excluding the 10-05 outage 100 of 154 card calls built a card, 30 were the model's own declines (~170K each). The wording Joe was asked with ("half the calls build nothing") overstated it; corrected on #349. Side finding on #338: on 10-04 the day passed the 4.5M unattended line because `CARD_TOKEN_ESTIMATE` (290K) sat under that day's 448K mean.
- **Defects verified on main and fixed:** `overround` is the margin (sum − 1) and `FairValueSteps` rendered it as the sum ("3.3% — not 100%", "−96.7 points"; the test pinned the wrong expression as source text); the engine's `reason_text` ("… Sized at 1.") rendered on `/market`; "not ranked" on a kickoff-ordered Picks; the Playbook drill pointing at the retired estimate log; "combined into nothing"; the "Record it below" anchor.
- **Lanes (Sonnet, worktrees, each full-suite green before hand-back):** #341 `62993d49`, #342 `c27d3573` (one conflict with #344 in `test_picks_screen.py`, resolved by dropping the Refusals pins), #343 `286a53d4`, #344 `d571f82c`, #345 `acf3ec3a`. Main: `ed76631d` (config, switch, ADRs, CLAUDE.md), `8f9a8fb7` (`last_ask_display` served for Picks, lesson, ledger). Full suite on the merged tree before #345: 10011 passed, 0 failed.
- **Deploy:** CI green on `8f9a8fb7` and on `4ff2e5df` (the final suite on that tree: 10016 passed, 0 failed). Live deployed with the authorised form and verified: `/api/health` `build.git_sha = 4ff2e5df318540c16f24431084daf07043601b60`, status ok. The demo deploy requested two seconds later was **cancelled by the workflow's concurrency rule**, not failed; re-run after live landed (run 38083158426). Re-read on the new build: `/market/<ticker>` ("103.3%", a positive margin, no "Sized at"), the footer (Gate · Playbook only), Your bets (opens on the strip).
- **Joe's four closed tickets, same evening ("learn from these losses too"; some his, some the desk's own cards).** The sharp-bettor's lesson is on his page (the stake, not the picks: $5 on a 5.5% six-leg cross-sport ticket against a ~$28 account is ~18% of bankroll where Walters's public unit rule is 1–3%; a price is a probability; each leg adds a margin; same-game legs are correlated and only the maker checked the price; tailing the desk is tailing a tout until its record is kept; one opinion sized three times; the only winner was a single; recognise "no exit"). No operator data entered the repo. Two tickets came out of it: **#354** (the combination cost line says what the price means: implied joint chance, leg count, cross-sport flag, fair chances multiplied beside the quote; sonnet) and **#355** (Your bets split by leg count and same-game vs cross-sport; main; blocked by #331). The record already tags `card` and `preset` as pick sources (ADR 0193), and #343's strip shows each source's expected-vs-actual, so "score the desk's picks" needs no new decision: Joe tags the tickets placed in the Kalshi app, which sit in `untagged` until he does.
- **Refused or deferred, with the reason (ADR 0195 §2):** merging Picks into Games; an `/ops` page; stake % on the ticket; a dollar spend line; per-leg CLV (after #331); the key-number flag (#348); cutting the scout desk / renaming Willy; the backend no-op sweep (#347, now also carrying #342's orphans).
- **Housekeeping:** `tasks/lessons.md` is ~228K of 262,144 — about 8K under the split line; split it before the next entry. `frontend/.next/dev/types` can hold stale generated route types after a deletion; delete `.next/dev` and `.next/types` before `tsc` on the main tree. #302's frontier is empty again (all four questions answered): a finding, not a clean desk.

### Still open

1. #354 — the combination cost line says what the price means (implied joint chance, leg count, cross-sport flag, fair chances multiplied beside the quote); sonnet lane, ready.
2. #353 — Games row: "0/5 books under" beside "1 book(s), need 2", and the age still said twice (chip + evidence line).
3. #355 — Your bets split by leg count and same-game vs cross-sport; blocked by #331.
4. #347 — the backend no-op sweep and the routes nothing calls (plus #342's frontend orphans); deferred, zero spend.
5. #348 — key-number flag on NFL/NCAAF spread legs; unscheduled, one feature at a time.
6. #338 — after a full budget day on the new ceiling: `game-script-card-refusals` near zero `max_tokens`, then close (moot while cards are tap-only; keep for the tap path).
7. #337 — 2027-01-15: look B for P1 only; step 1 is #336's live count.
8. #331 — 2026-11-01: the leg census by kind (per-leg CLV waits on it).
9. #210 — closes on the first scout convening with a sourced Matchup tile.
10. #151, #197, #267 — carried forward unchanged.

## 2026-10-09 (eighty-eighth session) — #316 closed by its live read; card output cap 3000→6000 (#338); builder routes deleted (#332); fee_coefficient served (#334); Joe's (C) withholds baseball singles (#339); live on `a6532df6`

- **/go, no focus from Joe.** Partner ranked: the overdue #316 read, then #332 and #334 as parallel Sonnet lanes, #336 folded into #337. Joe approved merge + live deploy of both lanes as one batch (option buttons) and answered #339 (C) mid-session.
- **Housekeeping.** Dependabot: 0 open. PR #335 (nightly routine) was an independent re-implementation of #333, already live; closed as superseded. Seven merged lane branches and their worktrees removed (none held a node_modules junction).
- **#316 closed by its live read** (`agent-tool-errors --limit 200`, `game-script-card-refusals --limit 200`, `agent-spend --days 3`, ~16:40Z): `code_execution_tool_result:server_tool_use_limit` recorded on 48 calls, so the recorder works end to end. Search-limit refusals: 3 cards, 201,143 of 5,982,430 metered card tokens over 10-07..10-09 (3.4%), under the partner's 20% bar, so no question for Joe on search.
- **#338, found in that read.** 17.6% of metered card tokens (1,055,000) bought no card. That is a lower bound, because 5 calls settled with NULL usage. On 10-09: 4 cards stopped with `stop_reason=max_tokens` and 5 with `json_invalid`, which `base.py:213` says is what a reply cut off at the cap looks like. The card call's cap is now `GAME_SCRIPT_MAX_OUTPUT_TOKENS = 6000` (`3834a7ce`, the scout staff's figure), pinned by a test that records the kwargs sent; mutation-checked. Also seen: the 2.25M unattended share refuses later cards daily (75 `refused_budget` in the newest 200), so every wasted card costs some later game its card. **Open until a later budget day shows `max_tokens` refusals near zero.**
- **#210** stays waiting: no scout convening since 10-05 (none in the 3-day spend).
- **#332** (`6c897097`): deleted, not wired. The `/api/builder/*` routes, `priceParlay`, `ParlayValuation`, `core/teaser.py`, `model/margins.py`, `model/synthetic.py` and `scripts/demo_builder.py` are gone; `TestTheBuilderRoutesStayDeleted` pins it. CI went red once: the priced-surface scan registered `types/parlays.ts` for `total_cost_dollars`, which left with `ParlayValuation`; unregistered in `a6532df6`. Lesson written.
- **#334** (`031fb065`): lookup and check payloads serve `fee_coefficient = float(COMBO_TAKER_COEFFICIENT)` (`core/fees.py:372`, the constant Take-it charges; identity-pinned across hedge/parlays/parlay_check). The cost line prefers it and now renders beside the book tile and on Check a parlay. kalshi-platform review said MERGE; 0.071 sits above every measured combo k, so the fee shown leans about 1% high, the safe direction.
- **#339** (Joe's (C), `21c6903d`): the review found that the singles comparison charged baseball singles at about 2× the measured rate (k ≈ 0.035 on nine fills), which flatters the parlay. A card with any KXMLB leg now withholds the singles clause. `ParlayCards` is the only provider of leg asks and goes through `singlesLegAsks`.
- **#336 closed into #337**: the cause is fixed on main (Amendment 2); the confirming live count is now mandatory step 1 of #337's "Before the run". The 336→337 blocker was removed.
- **#302 frontier**: #339 was opened and answered in-session; nothing else is waiting on Joe.

### Still open

1. #338 — after a full budget day on `a6532df6`: `game-script-card-refusals` shows `stop_reason=max_tokens` / `json_invalid` near zero, then close.
2. #337 — 2027-01-15: look B for P1 only; step 1 is #336's live count.
3. #331 — 2026-11-01: the leg census by kind.
4. #210 — closes on the first scout convening with a sourced Matchup tile.
5. #151, #197, #267 — carried forward unchanged.

## 2026-10-08 (eighty-seventh session) — Joe's parlay challenge: success rate is the price; the record reaches each leg (ADR 0194, v65/v66); the friend's-parlay path gets its guards; cash-out watch; cost line; markup registered; live on `7f135730`

- **Joe: "I challenge you to come up with ideas to improve parlay picks and success rates."** Planned in plan mode with three read-only scouts, the sharp-bettor and the partner; Joe approved the plan, answered two questions by option buttons (scouts' button on Check a parlay: **yes**; cash-out watch: **book only, makers on his tap**) and approved merging and deploying the whole lane batch. Story **#320** under epic #83; tasks #321 to #334.
- **The frame, for the record.** A parlay wins about as often as its price says. His median card is 4.75c (the 2026-09-05 census, n = 52): the makers saying "about 1 in 21", and winning 1 in 21 is the price coming true. At 5c twenty straight losses happen 36% of the time; proving he picks 6% winners where the price says 5% would take ~1,900 cards. So "success rate" is two questions: how often the card wins (set by leg count × leg likelihood, which the desk can only make visible) and whether he wins less often than the price says (the /bets expected-vs-won line by source answers it; the friend-vs-everything-else split is the biggest lever). "Better picks" is probably not the lever and could not be proven to be. Killed, with the row that kills each, in the plan and on #320: ranking by the gap, a correlation default, situational angles, alt lines as strategy, a leg/stop/stake rule, scoring the cards, any running scout-accuracy figure, a CLV split by the gap, a weekly card count, an "ask again" button.
- **Landed and live** (`7f135730`; deploys 37890632084 → `51b54290`, 37893265979 → `a1de244a`, then the final batch after CI 37896543678):
  - **ADR 0194 + schema v65** (`7ea38ca7`): `parlay_position_legs` carries each leg's own Kalshi ask at purchase (`ask_source` 'lookup' | 'candle'), its close as YES bid/ask before the TRUE start (event_links → odds_fixtures, never kalshi_events), stored on the leg row and never in `closing_lines`. `scripts/backfill_leg_prices.py` fills history from candlesticks (~80 days kept), NULLs only, counts only. **Run 2026-10-09 through the new `instrument.yml`** (flyctl had lost its login on the laptop and Joe was on his phone, so the reads now go through GitHub Actions with the deploy token; the log is public, so only counts-only instruments are listed, and the box's ssh shell holds no Kalshi key, so the script reads candlesticks unauthenticated, `c8604a98`). Two commit passes filled **446 leg asks**; closes had already been stored by the live scorer (#323); 49 legs have no purchase time (hand slips, adopted), 11 no bar left at the venue, 60 no link (NULL by design). Counts on #322.
  - **Step 0 is read** (run 37949516187): combos 228 settled, **39.1 expected to win at the prices paid, 34 won, range 29 to 50**; every price band inside its range (under 10c: 101 cards, 3.0 expected, 2 won; 10 to 25c: 62, 10.2, 10; 25 to 50c: 52, 17.1, 14; 50c+: 13, 8.8, 8). Singles 34, 13.3 expected, 12 won. **He wins at the price.** The by-source tags (since 2026-10-02) are all below the 5-expected floor, so the friend-vs-rest split cannot speak yet.
  - **#323** (`af7eb87f`): lookups and checks write `kalshi_ask_tenths` + `desk_chance` per leg; all four position writers carry the ask without touching the order or RFQ path; combo legs enter the closing-line scorer (plan pinned to `idx_parlay_position_legs_ticker`, never `odds_snapshots`); /bets gains "by leg kind" (expected vs won at the ask, closing-line value in cents) through `expected_block`, never joining the leg-verdict table (sqlite authorizer pin), never split by the gap.
  - **#324** (`da97be58`) and **#325** (`e363e470` + v66 `114b1064`): the leg-verdict registration's Amendment 1 admits `check_button`; Check a parlay gains the probable-bug flag with the spread/total rule (a leg with no recommendations row is judged from `fair_prices`'s book count and width, in the ladder's #79 drop too; no fair row = unknown, never clean), the "Ask the scouts" button (tap only; a cached verdict writes no row), and the friend-source line. v66 rebuilds `leg_verdicts` so the CHECK admits the fourth trigger — the lane found that blocker reading the schema; the first tap would have been an IntegrityError.
  - **#326** (`2c367946`, Amendment 1 `9d189c90`) and **#327** (`92b1d087`): the combo-markup registration (UNDERPOWERED, re-scoped; look A = rows before 2026-10-08T00:00Z) and `inspect_live_db.py combo-markup --limit N --cutoff ...`. The amendment moved the kickoff clock off `kalshi_events` (three hours late, half of P2's band) before any row was read; a run on the old clock would have been look A with P2 NOT EVALUABLE.
  - **#328** (`51b54290`): the buy-sheet cost line ("n legs. Wins about 1 in N. Fee is k×(1−P)% of stake. The same picks as singles: …%", k from the served quote, never a literal) and the Playbook's parlay chapter behind a tap. **#321** (`21035322`): Price on Kalshi states the fact ("Kalshi's ask is Xc against the books' fair value of Yc; hold Z%"), the "Bet two dollars." step is gone, four stale copy lines fixed. **#329** (`8ee969af` + `bfbf3907`): the last-leg push (every leg but one won, the last unstarted: the public book's bid and holding at the last leg's Kalshi price; no venue write; wired on the live loop, silent on demo). **#333** (`7f135730`): the manual-order ticket warns when a single bets against, or doubles, a held leg (the 2026-10-02 incident's screen); the NULL-combo branch is pinned.
- **CI went red twice and each was a pin outside a lane's grep set**: `test_api` asserted "holds" in the old verdict sentence (route-level, not file-level); `/bets` gained an uncapped paragraph and a docstring named the advisory table. Both fixed on main (`a1de244a`, `114b1064`). Lesson written (2026-10-08).
- **Partner's corrections kept**: the per-leg record is backfillable (not "lost for good"); CLV never split by the gap; the cash-out push values holding at the last leg's Kalshi price, never the books'; the census re-run stays as a dated fact-scout run (#331).
- **Look A of the markup measurement is in** (Joe ran it through the wizard after `flyctl auth login`; the first run crashed on tuple rows and printed nothing, fixed in `50bc36f6`). n = 69 asks on 19 days. P1's floor missed (only the 3-leg level had 20 asks on 10 days): no P1 test ran, look B owed (#337). P2 UNRESOLVED (kappa −0.05, t −0.36): no timing sentence either way. `g` reconstructed 0 of 69 because the rebuild handed the ladder today's `finalized` status for legs 2 to 22 days old (measurement-skeptic found it; Amendment 2; #336). The untested point slope against the conservative fair is negative (−0.087/leg), which runs AGAINST §10's stated bias (the draft had that backwards). The dispersion figure proposed for CLAUDE.md was withdrawn at audit: parts disagree with the pool five-fold.
- **Dependabot, read late in the session rather than at its start**: two high alerts on transitive frontend packages (`sharp` < 0.35.5, `source-map-js` < 1.2.2) fixed by `npm update` in the lockfile (`45a34645`); the API read 0 open after the rescan and the lockfile carries the patched versions (`npm ls`). Deployed with the batch after its CI.
- **Worktrees**: lanes 328, 321, 323, 325, 327, 333 remain on disk locked by their agent processes; none holds a node_modules junction (checked for 328/329/321). Remove with `git worktree remove --force` once unlocked; delete the `lane/*` branches (all merged).

### Still open

1. #336 — before look B: confirm on live, by a count over look A's leg tickers, that today's `finalized` status is what excluded every leg from the `g` rebuild (the fixture reproduces it; Amendment 2 fixes the rebuild to read the status as of the lookup). #337 — 2027-01-15: look B for P1 only. Look A itself is written: `docs/measurements/2026-10-09-combo-markup-look-a-result.md` (P1 floor missed, P2 UNRESOLVED, no number enters CLAUDE.md; audited by measurement-skeptic, twelve corrections applied, three of which changed the reading).
2. #334 — serve `fee_coefficient` on the lookup/check payloads and complete the cost line beside the book tile (was blocked by #321/#325, both merged).
3. #332 — `/api/builder/parlay` + `wong-screen` have no caller: wire or delete.
4. #331 — 2026-11-01: the leg census by kind (NHL puck lines and totals are unparsed; the same-game share).
5. #316, #210, #197, #151, #267 — carried forward unchanged from the eighty-fifth session.

---

# The session index

Every session entry ever written to this file, newest date first. Full text in
the linked archive file, unchanged.

### In this file, above

Added 2026-09-18: this index listed only the archived entries while its
own first line claimed every entry ever written, which is the gap the
`lessons.md` split found the same morning. Newest first.

- 2026-10-14 (ninety-seventh session) — housekeeping: live on `28b0c7a5` by Joe's deploy (#393 closed); #383 awaits a tap; 644/645 were #371; D7 ticketed (#394); worktree removal refused by the classifier
- 2026-10-13 (ninety-sixth session) — UI review by a designer and sharp-bettor, partner-ranked; seven layout lanes merged (#386–#392), on demo at `0ab7ae76`; live deploy refused by the classifier (#393); three copy questions to Joe (#385)
- 2026-10-13 (ninety-fifth session) — server-tool steps recorded per agent call (#383, v67); NFL series named (#381); the hand-tick refusal names only ticked legs (#382); a yes-only leg's NO offered as a single (#366, platform review PASS after one fix); #370 split, #377 closed; live on `eb49b82d`
- 2026-10-13 (ninety-fourth session) — every agent call dead since #371 (`output_format` on `create`) fixed; a card drops any leg its other legs guarantee (`drop_implied_legs`); live on `633444e`
- 2026-10-13 (ninety-third session) — the master scout's output cap (4000, bound exactly) named and raised to 12,000 (#377) so #210 can close; #376 no trimmed reading, prediction ≈670K; #370 docs lookup (`usage.iterations` beta-only, server-tool caching already on) and a seat sweep; live on `21aca8da`
- 2026-10-12 (ninety-second session) — NEXT.md split; an NFL card costs 0.5–1.1M tokens for what it reads (#370, #372 A → #374, ADR 0190 Am 4); "books under" counts the anchored books (#373 A → #375); key-number flag (#348); the demo /game refusal names no config (#369); the master scout settles with usage (#371, after the handoff); live on `bf26c721`
- 2026-10-11 (ninety-first session) — the Anthropic credit lapse found and labelled (#365; #367 B → #368); budget refusals name the cap and reset (#363); the combination cost line states the price (#354); one book and one age on a Games row (#353); `check_mobile --game-event` (#364); #338 closed
- 2026-10-10 (ninetieth session) — "more singles" and the cap that actually blocked him: token ceiling 5M (ADR 0190 Amendment 3); a leg can be bet alone on `/game` (#356); Games one row per market side (#357); Parlays lists tonight's games card or not (#358); #359 B
- 2026-10-10 (eighty-ninth session) — the desk through a professional bettor's eyes: ADR 0195; cards off, pushes off, ceiling 2.5M (#349–#351 A); four dead screens deleted (#342); the vig unit bug fixed (#341); Your bets leads with the record (#343); Games/Picks/Playbook copy (#344); verdict take rate (#345)
- 2026-10-09 (eighty-eighth session) — #316 closed by its live read; card output cap 3000→6000 (#338); builder routes deleted (#332); fee_coefficient served (#334); Joe's (C) withholds baseball singles (#339); live on `a6532df6`
- 2026-10-08 (eighty-seventh session) — Joe's parlay challenge: success rate is the price; the record reaches each leg (ADR 0194, v65/v66); the friend's-parlay path gets its guards; cash-out watch; cost line; markup registered; live on `7f135730`


### Split 2026-10-12 — [`archive/next-2026-10-12.md`](archive/next-2026-10-12.md)

Filed by the date of the split. The two 2026-10-06, three 2026-10-05, one
2026-10-03, four 2026-10-02, three 2026-10-01, three 2026-09-30, four
2026-09-29, one 2026-09-28, one 2026-09-27/28, five 2026-09-26, four
2026-09-25, four 2026-09-24 and four 2026-09-23 entries (39) that were still
in `NEXT.md` when it reached 232,027 bytes, **88.5%** of the ceiling — cut
by the session that found it there, before that session's entry existed.
Date boundary: everything 2026-10-06 and earlier moved, so the five
2026-10-08..10-11 entries stay together. Left 39,165 bytes before the
index — **14.9%** — and 82,227 with it, **31.4%**, before this section
was written. md5 `9c2d318926dcba2fc88965694477a834`; index lines in the
same edit; binary throughout.

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
