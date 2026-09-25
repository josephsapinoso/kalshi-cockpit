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
*decisions*, not builds. **An empty frontier is a finding, not a clean desk**
(2026-09-16): the map is the only queue that does not refill itself, and a
question for Joe that is not a sub-issue of #3 decays into the instrument
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
