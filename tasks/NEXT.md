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

## 2026-09-09 (third session) — the desk armed the entry and never armed the exit; and the census behind every combo warning had never read the shard he trades

**Two findings, both about the combination path, both found by looking rather
than by being told.** The exit gap (ADR 0125) came from the partner ranking it
above the whole backlog. The shard gap came from probing `/markets` to confirm
a ticker spelling — which is the second time this session that a routine
verification, not a plan, produced the thing worth knowing.

**STATE at close.** `main` = **`d27ca55`**, pushed, **CI green**
(`34377084002`, 9m4s). Session started at `579fadd`, clean.

**A SECOND DEPLOY IS OWED, AND THIS ONE HAS A DEADLINE.** Live is on
**`8755de6`**; `d27ca55` carries the scope correction to the buy ticket and
the bid-route 422, which the registration (§12.4) requires to land **before
C1 at 15:30Z on 2026-09-13**. It is copy only — no ceiling, no route logic, no
order path — but it sits on a real-money surface, so it was not shipped
unasked. **If it is not deployed, Sunday's measurement runs while the screen
still makes the unscoped claim that measurement exists to scope.**

    d27ca55  scope correction + Amendments 1-2   NOT on live   deploy before 09-13 15:30Z
    6caf867  census provenance + tests           NOT on live   (docs/tests only)
    8755de6  combo fill -> hedge position        LIVE, verified in container

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

**Joe-gated — one open, and it has a Sunday deadline:**

- **(E) OPEN — deploy `d27ca55` to live before 2026-09-13 15:30Z?** The scope
  correction on the buy ticket and the bid 422. Copy only: no ceiling, no
  route logic, no order path, nothing money-touching. Left unshipped only
  because the string sits on a real-money surface. **Undeployed, Sunday's
  measurement runs while the screen still makes the unscoped claim that
  measurement exists to scope** — and the registration ruled the correction is
  owed *regardless* of what Sunday finds.

Answered and closed this session:

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
