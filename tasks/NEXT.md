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

---

## SESSION START — if Joe said "read NEXT.md", this box is your prompt

Repo: `C:\Users\josep\Documents\Claude\Projects\kalshi_betting_tool`,
branch `main`. Check `git status` and `git log origin/main..main` rather than
trusting any sentence here, and read the LIVE instance's `/api/health` for its
`git_sha` — it sits under `build`, not at the top level. The calibration study
is STOPPED (2026-08-20, Amendment 2; the recorder machinery still runs). Joe is a beginner and has
asked to be educated: define every betting/stats term at first use, via
`frontend/src/lib/glossary.ts` and `<Term>`.

**Test baseline: UNMEASURED on this tree, and that is the honest state as of
the merge below.** The hedging lane measured **4,828 passed / 6 skipped / 10
xfailed in 17:00** on its own merge; that tree did not contain the eight
collision guards in `tests/test_parallel_lanes_do_not_collide.py`, and the
tree that did measured 4,648. **Neither number is this one.** Re-run and
replace this paragraph with a figure and a duration.

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

## 2026-08-27 (latest) — a cold open buys odds on the pass it woke

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

## 2026-08-24 (fifth session, close) — SUPERSEDED by the entry above: the screen's declaration did not survive audit

**Nothing below is retracted — it is an accurate record of what the screen
said, and its instruction to run a `measurement-skeptic` pass before writing
anything is what caught the defect. Read it for the three questions it names;
they were all answered on 2026-08-25 and two of them were answered wrongly by
this entry's own reasoning. The verdict `NO SIGNAL at 311 of 300` is REFUSED.**

**Observed on the live screen at ~2026-08-24 21:4xZ, immediately after
deploying `1bdc33b`. It is recorded here and NOWHERE ELSE. Nothing has been
written to CLAUDE.md, no ADR, no measurement doc — deliberately.**

    SIGNAL TEST   NO SIGNAL    311 of 300 games    measured 1s ago
    beta  -0.0766   se 0.0215   interval [-0.1545, +0.0013]
    rows  14,616
    by market type, diagnostic only:
      moneyline  -0.0677 · 230g · 91%
      prop       -0.5192 ·  81g ·  9%

The instrument's own words on the page: *"The record has reached the
registered floor of 300 games, so this verdict is a declaring one. It was
fixed in advance in
`docs/measurements/2026-08-09-preregistration-clv-signal-test.md`."*

**Why this matters more than anything else in this file.** CLAUDE.md still
says the verdict is **UNRESOLVED at G = 199** and that it *"may not be
reported as no signal"* below the registered floor of 300. G is now **311**.
The project's central pre-registered question has answered, on a rule fixed
before the data was seen. That is the question this whole tool was built to
settle.

**DO NOT write it into the record without a `measurement-skeptic` pass
first.** This repo's own rule is that a result entering the record gets
audited, and "good news arrives as a formal declaration" is the case most
worth checking. Three things to put to it, none of which this session did:

1. **`beta` moved from −0.1412 to −0.0766 while G went 199 → 311.** The
   direction is toward zero. Explain the move before quoting the number.
2. **The arms disagree by a factor of 7.7** — moneyline −0.0677 (230 games)
   against prop −0.5192 (81 games). The pooled-number rule says print the
   parts and the largest contributor's share beside any aggregate; the
   screen does, and the parts do not obviously agree.
3. **The interval [−0.1545, +0.0013] includes zero.** The registered
   NO-SIGNAL threshold is 0.40 and −0.0766 is far below it, so the verdict
   follows the registration — but "the interval excludes the threshold" and
   "the effect is distinguishable from zero" are different claims and only
   the first is being made.

**Also unwritten:** whether crossing the floor changes anything operationally.
It should not — ADR 0038 already closed the hunt on other grounds, and
CLAUDE.md already said to treat the outcome as settled for planning. The
gate's 300-*actionable*-game interlock is a different counter and is
untouched. But that reasoning has not been written down, and a future session
finding "NO SIGNAL, declared" will want it.

---

## 2026-08-24 (fifth session) — the purpose gets settled, and the feed is told to follow attention

Seventeen questions to Joe over five rounds (the `grilling` skill), every
answer his, recorded as **ADR 0071**. Read that ADR before planning
anything — it settles what this tool is *for* after ADR 0038 closed the
hunt, which is the question every session has been re-deriving badly.

**State: 4,192 passed / 10 xfailed** (+23 over the 4,169 baseline, which was
re-measured at session start rather than inherited), ruff clean. **Lane 3 is
shipped; lanes 1 and 2 are not started.** Nothing is committed — check
`git status` before assuming otherwise.

**The settled direction, in one paragraph.** The tool is a **personal
betting desk first**, a portfolio repo second, and a hunting instrument not
at all. Joe bets by hand whether or not it exists, so its job is to inform
and record bets that are happening anyway — specifically **price
transparency**: what Kalshi charges against what the sharp consensus says
it is worth. Not nagging, not abstaining on his behalf. Sharing means
**someone runs their own copy**, because Kalshi's Developer Agreement §3.1
forbids sharing API-derived data with third parties without written
authorization — a hosted instance friends can visit is non-compliant, a
friend's own instance on their own key is the permitted case.

**Three lanes, approved, none started:**

1. **The bill.** Replace the fixed 12-hour `ODDS_DESK_WINDOW_UTC` with a
   frontend heartbeat over a slow hourly floor (~576 credits/day today).
   Folded in: the 2026-08-17 defect where a failed odds call resets the
   freshness clock, so an outage presents on screen as *fresh* data — same
   code, and the new design would inherit a lying clock.
2. **Transparency — DONE, both halves.**
   - The fair-value parlay payout is restyled so an estimate cannot read as a
     quote (ADR 0071 §2.8, 5 guards mutation-red).
   - **Every slate row now reads `50.7c ask · 54.2% fair`** — two plain
     numbers, no sign, no arrow, no tone class. No backend work was needed:
     both display strings were already on every row (`routes.py:5062,5070`).

   **It cost `breakeven_win_rate` its place on the row, and Joe approved the
   swap 2026-08-24.** The two cannot share a row — `edge_tenths ≡ 1000 ×
   (fair − breakeven)` (`test_api.py:1264-1310`), so fair beside break-even
   hands back the edge the 2026-08-21 ruling deleted.
   `TestBreakevenShipsAloneOnTheScreen` became
   `TestFairAndBreakevenNeverShareTheRow`: same property, inverted direction,
   dated docstring. **`breakeven_win_rate` left the component, not the wire** —
   `test_api.py::TestBreakevenShipsAlone` still requires it on the payload.

   Three things that fell out, all shipped:
   - **A latent column-shift bug is fixed.** The break-even span was
     conditional, so a row with no tradeable price dropped a grid child and
     shifted every column from `Books` rightward one track left at xl. The
     fair cell is unconditional and pinned as such.
   - **The footer had to say the gap is not profit.** Two numbers side by side
     invite a subtraction whose remainder is not money — a fee sits between
     them, and this project measured the remainder and it did not pay. Prose,
     no per-row figure. It is also where `Term k="breakeven"` now lives; the
     slate row had been its only renderer, and the glossary's orphan rule
     ("use it or delete it") caught that within a minute of the swap.
   - **The visible label is `fair`, not `consensus fair`** — the longer label
     wrapped to three lines in the 5rem track on all eleven rows. Full phrase
     is in the popover, and it matches `SlateRow.tsx` on the Board.

   **Do not rank by the gap** — `beta = -0.141` means ranking by it puts
   the least trustworthy rows on top; ADR 0071 §2.5.

   Verified: overflow gate green at 390/768/1280/1440/1920 against a seeded
   local build, screenshot eyeballed at 1280. **A stale `next start` served
   the old build once and the first "pass" was against it** — caught by
   checking `EADDRINUSE` in the log and diffing the served HTML, the same trap
   recorded on 2026-08-22.
3. **Cheap corrections — DONE this session.** `AGENT_MODEL =
   "claude-sonnet-5"` set explicitly in `fly.live.toml`;
   `KALSHI_PUBLIC_READ_ONLY` shipped with 23 tests and five guards
   mutation-verified red; all four stale-number sites corrected.

**Lane 1's plan is written and is the next session's brief** (a Plan agent
worked it read-only). Seven slices, and **take them in order — slice 1 must
ship first**, because slices 3–5 read the same predicate the defect
corrupts. Two things in it need Joe:

- **The new design's worst case is worse than what it replaces.** One tab
  left visible for 24h buys **1,152 credits/day — double today's 576** and
  past the 20,000 plan. The `document.visibilityState` check in `Nav.tsx` is
  therefore the single most load-bearing guard in the change, and slice 6
  (an attention sub-ceiling, modelled on `ondemand`'s manual slice) is the
  belt to its braces. Recommended, not yet approved.
- **The saving is an assumption until measured.** Every "attended hours" row
  in the plan's table is a guess about how long Joe actually has the page
  open. Ship with the instrument named — `api_credits` summed per budget-day
  on the live volume — not with the saving claimed.

Three corrections the plan found that this session did not: `run_loop.py:460`
calls `window_status` **without** `desk_window`, so the loop's own cadence
already ignores the desk; the desk trigger is the one place the module's own
"one predicate, two callers" rule was never applied (it is two hand-synced
inline `if`s at `timing.py:1409` and `:931`); and a failed odds call writes
**no `odds_sweep_log` row at all**, so the failure is visible only as a
credit row with NULL headers.

**The defect, located** (it was recorded on 2026-08-17 and never fixed):
`backend/odds/client.py:324-334` records the credit before the status check
at `:336-339` — correct, and it must stay. The lie is that the resulting row
satisfies `_SERVED_SWEEP` (`timing.py:707-709`), so a 401 moves that sport's
last-sweep stamp to now and **defers the retry ten minutes**. Fix: a nullable
`api_credits.http_status` (schema v21) and `AND COALESCE(http_status, 200) <
400`, which leaves every pre-v21 row counting exactly as it does today.
Evidence: `docs/JOE-odds-key-rotation.md:151-166`.

**Two corrections to the record, both in ADR 0071:**

- **CLAUDE.md's "the recorder keeps running because it costs nothing" is
  false** on the odds axis — ~576 credits/day, ~17,300/month against an
  18,000 self-cap. True of the LLM fleet only. The spine paragraph needs
  editing.
- **A privacy leak was reported to Joe and then withdrawn.** A subagent
  called `/api/ledger`, `/api/bets`, `/api/results` unauthenticated; they
  are not. Verified against live: health 200, all four others **401**. The
  gate is `frontend/src/middleware.ts`, which runs before Next's rewrites,
  and uvicorn binds loopback. Lesson written.

**Facts worth carrying:** the **search cap binds before the call cap** (60
searches ÷ 12 worst-case = 5 convenings/day, vs 24 calls ÷ 4 = 6), so
`fly.live.toml:289`'s "the money control" comment names the wrong cap. The
Odds API's **free 500-credit tier includes Pinnacle, Betfair Exchange and
Matchbook** — the exact three books `runner.py:150` devigs from — and
excludes DraftKings/FanDuel; the paid 20K tier is $30/month. Pinnacle closed
direct public API access 2025-07-23, so every route to them is a reseller.

---

## 2026-08-24 (fourth session) — the parlay desk earns a nav slot and every game names its sport

Two UI changes on Joe's direct asks, both committed, pushed, and live
(machine version 126, deployed ~20:56Z; verify `/api/health` `git_sha`
against `origin/main` at `aef8b5b`):

- **Nav swap (`1d88aba`)**: `/parlays` took Evidence's nav slot — nav is
  now Games · Picks · Parlays · Your bets · Gate · Playbook, budget still
  six. `/ledger` ("Evidence") moved to the footer beside Estimates. The
  reasoning is in `Nav.tsx`'s slot comment and `Footer.tsx`'s row comment;
  `test_every_screen_is_reachable.py` still pins budget and reachability.
- **League tags (`aef8b5b`)**: Joe reported he can't tell which sport a
  game is. `event_links.league` (the odds feed's sport key) now travels on
  `/api/slate`, `/api/board`, and the picks block; new
  `frontend/src/components/LeagueTag.tsx` renders it through `leagueLabel`
  beside every game name on Games, Picks, Likely winners, and each parlay
  leg (legs already carried the key). `None` on an unlinked row renders
  nothing — never a guess from the ticker prefix. Full suite passed
  (4,169 + 10 xfailed), tsc clean.

Nothing new is open from this session. The prior entry below is still the
live brief for the parlay-desk watch items.

---

## 2026-08-24 (third session) — the desk is used for real, and a combo book is populated for the first time ever

Joe used `/parlays` and "Price on Kalshi" for real and placed bets in the
Kalshi app. Live at `3d0240e` (the review fixes were deployed first). All
four watch-after-deploy items are answered, read off the live DB
(read-only, over ssh):

- **Every tap wrote a `parlay_lookups` row** — 4 rows: `safe` twice
  (~03:54Z and ~18:19Z), `middle` and `lottery` once each.
- **The `safe` card returned `priced` — the FIRST populated combination
  book this repo has ever read** (every prior read: 40/40 empty, both
  sides). At 03:54Z: NO bid 599 tenths, depth **501**, derived YES ask
  40.1c vs `fair_joint_conservative` 38.7%, hold 3.4%. By 18:19Z the
  maker had repriced: depth 59, ask 42.4c, hold 7.2%. So a maker DOES
  arrive on minted cross-category combos — `book_empty` is a first
  answer, not a permanent one. **Enter-only is NOT refuted**: the price
  is still the complement of a resting NO bid; no YES bid was observed.
- **Idempotency held in production**: the 18:19Z repeat tap returned the
  same `minted_market_ticker` as 03:54Z — 14.5h and one deploy apart,
  beyond the seconds-apart bound the capture pinned.
- `middle` and `lottery`: `book_empty`, the expected first answer.
- Fills mirrored via the poller with `source='venue_hand'`; on every
  combo fill `fee_actual` matched the `model_a_deci` prediction — live
  observations consistent with the standard formula at 0.070 on KXMVE,
  where ADR 0012 §5 records the combo fee model as unverified. Two of
  the combos bet have no lookup row (built in the Kalshi app directly).
  Amounts/prices stay out of the repo per the operator-data ruling.

**Open:** settlements for these positions land on `/bets` after the 12h
mirror pass — first real end-to-end check of the combo settlement path.

---

## 2026-08-24 (second session) — all 14 review findings fixed, and the repeat tap turns out to be idempotent

**The list below is DONE — all 10 main findings and all 4 cut-by-cap
items.** State: **4,169 passed / 10 xfailed** (+70 over the 4,099 baseline),
ruff clean, tsc clean, `next build` green, overflow gate green at
390/768/1280/1440/1920. **Not yet committed or deployed when this entry was
written — check `git log` and `/api/health` `git_sha` before trusting any of
it as live.**

**The one measurement this session took.** Finding 7 asked what Kalshi
answers when the SAME combination is looked up twice — never observed, and
it had become load-bearing, because finding 2's fix adds a retry button that
makes the second tap one press away. `scripts/capture_combo_repeat_lookup.py`
(new) ran it live: **200 with the same `market_ticker` and the same
envelope — IDEMPOTENT.** So the retry is safe, `price_card_on_kalshi` needs
no already-exists branch, and repeat taps do not burn the 5,000/week
creation budget. Captured to `tests/fixtures/combo_lookup_repeat.json`, and
**bounded as captured**: one collection (`KXMVESPORTSMULTIGAMEEXTENDED-R`),
one NFL leg pair, two calls seconds apart. It says nothing about a third
call, concurrent taps, a started game, or another collection scope. Had it
come back 409, the retry button would have been wrong to ship.

**Fixed, by finding:**

1–2. **The frozen card and the dead ends.** `lookupParlay` now wraps its
fetch and guards the ok-path `response.json()` (`refreshOdds`'s pattern); a
transport failure says the market *may already have been created* rather
than inviting a blind retry. `PriceOnKalshi` catches too, and every
non-final state offers "Ask Kalshi again" — a priced answer deliberately
does not, and the retry never wears `bg-accent`. New
`tests/test_parlay_screen.py` (8 source-text tests).
3. **Post-mint failures recorded.** The order-book fetch moved inside its
own try/except; a failure writes an `error` row **carrying the minted
ticker** and the 502 names it, so a real market can never be lost off the
audit table.
4. **The depth-blind payout is gone** — CLAUDE.md rule 1 on a payout. Was
"$5.00 → ~333 contracts → $333.33" against 18 resting; now `min(wanted,
depth)`, with cost shown and words when the stake is capped. **The test that
pinned `~333` as "the cousin's arithmetic" was INVERTED with a dated
docstring.** `depth is None` is unreachable from the route (`_parse_levels`
drops zero-size levels, so a derived ask always has size) — kept as a typed
guard, documented as such, and tested by direct call rather than pretending
the route reaches it.
5. **Collections cache failure modes.** Cold-cache failure is a recorded row
and a 502, not a bare 500; an empty result is **never cached** (unreadable ≠
"the venue has none"); a failed lookup invalidates, so the rotating `-R`
suffix can no longer mean an hour of 502s.
6. **`sorted(served)`**, not `list`.
8. **Unknown spread units counted apart.** New `dropped_unknown_spread_unit`
on `PassCounts`, in `ALWAYS_REPORT` even at zero, fed by
`spreads.unrecognised_spread_unit`. NHL "goals" entering scope no longer
looks identical to a quiet night while `h2h,spreads` keeps paying doubled
credits.
9. **The spread join identity lives once** — `spreads.spread_book_point` and
`spreads.spread_margin_agrees`, imported by both the runner and the parlay
reader. The ladder now performs the margin-vs-strike cross-check it was
missing, so a subtitle-drifted market can no longer match a stale fair row.
10. **One shared Kalshi client**, lazy, `LiveQuoteSource`'s pattern, closed
in the lifespan. `COMBO_LOOKUP_TIMEOUT_S = 15.0` (longer than the quote
source's 5s — the first call mints; shorter than REST's 30s — a person is
waiting).

**Cut-by-cap items, all four done:** `_CANDIDATE_SCAN_FLOOR_MS` (24h, wider
of it and `max_odds_age_ms`, so it can never bind before the freshness rule)
on the twice-per-tap `fair_prices` scan; `lib/proxy.ts` shares the seven handlers'
mechanics while **each keeps its own refusal words** (they say different
things about what did not happen) — `/refresh-odds` deliberately keeps its
own relay because its caller reads a typed `OddsRefreshResult`, pinned with
its reason in `tests/test_token_proxy_routes.py` (39 tests); `best_yes_ask`
and `format_price`/`format_probability` replace the hand-rolled copies
(`format_probability`'s docstring names the exact rounding drift `_percent`
was causing); `POPULATED_BOOK` now derives from the **captured** envelope
with a shape assertion — no populated combo book has ever existed to
capture, which is why it is built rather than loaded.

**Mutation-verified red, file restored byte-identical each time:** the depth
cap, the empty-collections cache write, the cache invalidation call, the
sorted legs, the post-mint error row, the unknown-unit counter, the shared
client, and the way back to `idle`.

**One existing test's assertion was updated, not dropped:**
`test_pass_control.py`'s "the handler holds the token" read `APP_AUTH_TOKEN`
in the route source; that moved into `lib/proxy.ts`, so it now follows the
indirection with a dated docstring. The claim is unchanged.

**Two lessons written:** a baseline taken while you edit is not a baseline
(10 phantom failures cost a false diagnosis this session); a pin verifies
the shape you saw, not the branch you rely on (finding 7).

**Watch after deploy:** first real "Price on Kalshi" tap — `book_empty` is
still the expected first answer, and the retry is now one tap. Confirm a
`parlay_lookups` row per tap and that a repeat tap returns the same
`minted_market_ticker`. Watch `dropped_unknown_spread_unit` in the pass line
when NCAAF/NFL land.

---

## 2026-08-24 — code review of the parlay-desk session: 14 findings (ALL FIXED — see the entry above)

`/code-review` over `e4e7166..9f09952` (the parlay-desk commits): 45 raw
candidates → 16 verified after dedup → **14 survived** (12 CONFIRMED, 2
PLAUSIBLE), 2 refuted (event-loop blocking matches the accepted sync-SQLite
baseline at `routes.py:3185-3189`; the spread dog-side skip is deliberate and
redundant). **Nothing is fixed yet — this list IS the next session's work.**
Line numbers are as of `9f09952`.

**Fix first — user-facing dead ends and broken contracts:**

1. **Frozen card on network failure** — `frontend/src/lib/api.ts:759`:
   `lookupParlay` has no try/catch around fetch and an unguarded
   `response.json()`; `PriceOnKalshi.tsx` `tap()` doesn't catch either. A
   dropped connection leaves "Asking Kalshi…" forever (button unmounts, no
   retry) while the backend may already have minted the market. Sibling
   `refreshOdds` catches both cases — copy its pattern.
2. **No way back to `idle`** — `PriceOnKalshi.tsx:55`: no state transitions
   back, so the *designed* second tap after `book_empty` ("Try again
   shortly" — the expected first answer on a fresh combo) is impossible
   without a page reload. Same dead-end after a 409 drift refusal.
3. **Post-mint failures unrecorded** — `backend/parlays.py:535`: the
   orderbook fetch after `lookup_combo` mints sits outside the try/except —
   an httpx timeout/429/5xx there returns a raw 500 and **no
   `parlay_lookups` row**, losing the minted ticker from the audit table
   whose docstring promises every outcome is a row.
4. **Depth-blind payout / rule-1 violation** — `backend/parlays.py:590`:
   `contracts = stake/ask` renders "$5.00 → ~333 contracts → $333.33"
   beside "about 18 contracts resting". Only the resting size is buyable on
   an enter-only book, and a stale lone NO bid produces exactly the giant
   apparent edge CLAUDE.md rule 1 says to suppress, shown as a payout.
5. **Collections cache failure modes** — `backend/parlays.py:489`:
   cold-cache `fetch_collections` error escapes as an unrecorded 500; a
   transiently-empty result is cached the full hour; a failed lookup never
   invalidates despite the `-R` ticker rotation NEXT.md already records —
   up to an hour of 502s with no recovery short of restart.

**Fix while in there — cheap and confirmed:**

6. **Nondeterministic leg order** — `backend/parlays.py:488`:
   `legs = list(served)` from a set; order POSTed to Kalshi and recorded in
   `selected_legs` varies across processes. One-word fix: `sorted(served)`.
7. **Repeat-tap wire shape unverified (PLAUSIBLE)** —
   `backend/kalshi/combos.py:414`: the create POST was captured once, on a
   brand-new combo; no already-exists handling, yet the designed second tap
   hits exactly that case. If Kalshi answers 409/400 the combo becomes
   permanently unpriceable and each retry burns the 5,000/week budget.
   Capture the repeat-call payload (combo lookups are pre-authorised).
8. **Spread unit whitelist (PLAUSIBLE)** — `backend/kalshi/spreads.py:38`:
   regex pins `runs?|points?`; NHL "goals"/soccer entering seasonal scope
   → silently zero spread supply while `h2h,spreads` keeps paying doubled
   credits. At minimum add a unit-unrecognized counter distinct from
   `dropped_unresolved_outcome`.
9. **Spread join identity duplicated** — `backend/parlays.py:184` vs
   `runner.py:1032`: strike↔point identity implemented twice; the
   margin-vs-strike cross-check exists only in the runner, so the ladder
   can match a subtitle-drifted market to a stale fair row until freshness
   ages it out. Centralize the identity next to the regex in `spreads.py`.
10. **Per-tap Kalshi client** — `backend/api/routes.py:2552`:
    `KalshiConfig.load()` + PEM re-parse + fresh `httpx.AsyncClient` per
    request, against "one shared AsyncClient" — ~500ms per tap, port-
    exhaustion risk. Follow `LiveQuoteSource`'s lazy shared client
    (`quotes.py:206-242`).

**Cut by the 10-finding cap, all CONFIRMED — a follow-up cleanup pass:**
the unbounded `fair_prices` scan in `ladder_candidates`
(`backend/parlays.py:102-123`, no `computed_ms` floor on a never-pruned
~6.9M-row table, paid twice per tap); the 7th hand-copied token-proxy route
(`frontend/src/app/parlay-lookup/route.ts` + `middleware.ts:50` allowlist);
hand-rolled `1000 - best_no_bid` and three display-format duplications
(`parlays.py:565/597/613/615` vs `OrderBook.best_yes_ask`,
`core.prices.format_price`, `_percent`); hand-constructed `POPULATED_BOOK`
wire payload (`tests/test_parlay_lookup.py:228` — the captured-fixtures
rule names MLBAM as its only exception).

Full verifier transcripts died overnight once and were re-verified by
direct inspection 2026-08-24; verdicts above are from that pass.

---

## 2026-08-23 (third session) — the parlay desk: three cards at fair value, spreads priced, and the combo's real cost one tap away

Joe's direction, with a screenshot: his cousin-in-law hit a Kalshi 6-leg
combo ($4.99 → $333.33, six cross-game spread legs) and he wants the
cockpit to produce good parlays like it. He chose the heavy options by
AskUserQuestion: **spreads now, auto-fetch the real combo price via
`lookup_combo`, ladder of three cards**. ADR **0070**; commits `9caf361`
(Slice A), `e4e7166` (B), `d123623` (C). Schema **v20**. State at close:
**4,099 passed / 10 xfailed**, ruff clean, tsc clean, `next build` green,
overflow gate green at all five widths. **NOT yet deployed when this
entry was first written — check `/api/health` `git_sha` before trusting
anything below as live.**

- **Slice A — `/parlays` (ADR 0070).** `backend/core/ladder.py` (pure:
  one leg per fixture so `CorrelationRefused` is structurally
  unreachable; conservative headline joint + per-method band; staleness
  = stalest leg; unbuildable cards say why), `GET /api/parlays`
  (server-worded money strings at preset stakes $1/$5/$10/$20 — the
  no-client-arithmetic rule; key-walk bans every edge-shaped stem,
  mutation red), v20 `fair_prices.oldest_book_age_ms` (NULL refuses,
  never age zero — mutation red), `parlay_lookups` table, `/parlays`
  page + footer link (the delete-commit question answered: Joe asked
  for the screen by name) + slate contextual link + 5 glossary terms.
- **Slice B — spreads.** Kalshi spread markets were ALREADY discovered
  and quoted every 15s; what was missing was the link (every spread
  event failed `link_event` "expected 2 sides, got N" every pass — they
  now inherit their game's link by fixture segment,
  `spread_fixture_segment`), the odds (`fly.live.toml` `ODDS_MARKETS =
  "h2h,spreads"`; sweep 2→4 credits; desk window 576/day ~17,300/mo, so
  **daily cap 600→700 and monthly self-cap 13,000→18,000** — inside the
  paid 20,000 tier; at 4 sports even that breaks, warning updated), and
  the devig path (`_price_spread_event`: one devig per rung, two-sided
  complementary books only, **`fair_prices` only — no recommendations**,
  keeping spreads off the gate/board/evidence record). One subtitle
  parser (`backend/kalshi/spreads.py`), pinned on the captured fixture,
  margin cross-checked against `floor_strike`.
- **Slice C — "Price on Kalshi".** The first combo lookup this repo ever
  spent found ADR 0012's pinned endpoint DEAD (routing 404; lesson
  written). Current wire: `POST /multivariate_event_collections/{t}`
  with a `side` per leg; response + minted market's book captured as
  fixtures (2026-08-23, first ever). **A fresh combo's book is EMPTY on
  both sides** — the endpoint's honest-refusal branch is the expected
  first answer. `POST /api/parlays/lookup` (auth; drifted card → 409
  before touching the exchange, mutation red; prices off the ORDER BOOK
  as 1000 − best NO bid, never the list row; every outcome writes a
  `parlay_lookups` row), `PriceOnKalshi.tsx` (the screen's one
  `bg-accent` control), `/parlay-lookup` token-holding route handler.
  `combos.py` moved out of ADR 0022's quarantine — the tripwire fired
  exactly as designed — into MUST_HAVE_CALLERS.

**Honesty rails, all pinned by tests:** no edge/EV/kelly/breakeven key in
any parlay payload (ADR 0038/0046 untouched — no combo EV through
`calculate_fee`, fee sentence travels verbatim); enter-only warning on
every card (40/40 books); fair-value-is-not-a-quote sentence; the
2026-08-21 spread/total *edge look* veto is untouched (this is ingestion
for card pricing, no registered look, no edge computed).

**Watch after deploy:** first real pass with `h2h,spreads` — confirm
`fair_prices` rows with `market='spreads'` and non-null
`oldest_book_age_ms`, spread events linking as `spread_fixture_segment`
and leaving `unmatched_items`, and `credits-day` near the 576/day
arithmetic. First real "Price on Kalshi" tap on a live card: expect
`book_empty` first (the captured reality); a second tap moments later may
find the quoter arrived. The lookup collections cache is per-process
(1h). The `-R` suffix on collection tickers rotates — the fallback is
prefix-matched, not pinned.

---

## 2026-08-23 (second session) — the desk presents fully: likely winners on the slate, five areas per game, Willy's seat

Joe, frustrated ("nothing bettable almost at all... what the hell man?"),
then the reframe that unlocked the build: **"I just want to see what are
good-chance picks and everything is rejected."** Live reads confirmed the
board's emptiness is the measured finding, not a defect (90 of 100
candidates no-edge; Kalshi within ~0.1c of the sharps). His direction,
approved by plan: the picks question is a *different* question from edge,
and the desk becomes fully visible — **"I don't want to hover over every
game anymore"** — five areas: skeptic, willy balters, scout, team
specialist, consensus, plus the site explaining why sport factors aren't
computed here. Plan:
`C:\Users\josep\.claude\plans\nothing-is-bettable-in-lexical-gray.md`.
ADRs **0067 / 0068 / 0069**. State at close: see the verification block
below; schema **v19**.

- **Slice A — "Likely winners tonight" (`f265ef1`, ADR 0067).**
  `/api/slate` gains a `picks` block: one entry per game, the consensus
  favorite, ranked by `fair_probability` alone (one stored unscored column
  — a sort, never a composite; the rows below still order by kickoff).
  YES-side rows only (a NO row's `team` names the opponent); freshest row
  per ticker; stale consensus and unpriced favorites **counted out by
  name**; stale Kalshi quote withholds the ask. The chance≠edge note
  travels in the payload and renders verbatim; a key-walk test bans any
  edge-shaped field in the block. `GoodChancePicks.tsx` on the landing
  slate: game links only, no ticket, no `bg-accent`, no streak tally.
  Three mutations verified red. Glossary +3 (`favorite`, `priced_in`,
  `consensus_chance`).
- **Slices B+C — the five-panel market screen (ADR 0068).** Anchored nav
  (Consensus · Skeptic · Scout · Specialists · Willy), everything fully
  present. `/api/market/{ticker}` joins `fair_prices`, serves `books` +
  `kalshi_drift_tenths` (slate's own helpers) and a `gauntlet` block —
  `suppression.gauntlet_view()` reconstructs all 12 checks' verdicts from
  `suppressed_reason` (fail-only checks report `not_taken`; `sizing:`
  passes through; unknown codes surface), served with `judged_ms`.
  **Deliberately no `breakeven_win_rate` on this route** — fair% renders
  here now, and the pair reconstructs the edge by subtraction.
  `ConsensusPanel.tsx` (fair% side-named, book distribution, soft-fallback
  warning, drift, and the standing explainer: sport factors are already in
  the sharp line — ADR 0036/0037 as product copy, source-pinned).
  `SkepticPanel.tsx` (free — the retired LLM Skeptic stays retired; codes
  verbatim + gloss captions + as-of line). ScoutDesk: master's read and
  staff filings OUT of `<details>` (exactly one `<details>` left — the
  spend meter — pinned by count, mutation red); specialists get their own
  section, every state in words, two-column at xl.
- **Slice D — Willy Balters' seat (ADR 0069, schema v19).**
  `backend/agents/pro_bettor.py`: a Walters-*style* fiction (name pinned
  both ends, "Billy Walters" turns tests red), fourth metered call after
  the master settles, **no tools** (source-pinned over the call block,
  mutation red), `SharpTake` all-strings (walker test, mutation red).
  `status` semantics unchanged — the seat is additive; unaffordable/failed
  = `sharp_absent_reason`, honest words on screen. v19 adds
  `scout_briefings.sharp_json` (NULL never `{}`); GET serves `sharp`.
  Send captions now say **four** metered calls. Budget: 4 calls /
  worst-case 12 searches per convening → **5 full convenings/day**
  (searches bind), ~$0.50–0.70 each at list prices.

**Verified before close:** full pytest green (see below), ruff clean, tsc
clean, `next build` green, overflow gate green at 390/768/1280/1440/1920
including `--market-ticker`, picks block confirmed on the seeded demo
(6 ranked, exclusions counted) and rendered server-side on `/`.

**Watch after deploy:** the picks block's staleness exclusion uses live
odds age vs `max_odds_age_s` — outside the desk window whole slates will
correctly rank nothing and say why; if Joe reports "picks always empty",
check `/api/window` first, not the block. Willy's first real take is
unreviewed — read it critically, same as the desk's first briefing.

---

## 2026-08-23 — the desk window opens: the slate stops being stale 14 hours a day

Work list was empty; the partner audited live and reordered everything: **the
screen was 89% `stale_odds` refusals (63/71 rows, median odds age 13.7h) with
0 of 600 daily credits spent**, because the scheduler only sweeps 75–15 min
before kickoff clusters. Four slices shipped (one main-tree + two worktree
lanes + one census correction). State: **4,001 passed / 10 xfailed** locally
(3,996 + the 5 prune-frontier fixes), ruff clean, tsc clean. Commits
`b22f471`..`b9e4b3a` pushed; live deploy dispatched (run 32652551993) —
**verify `/api/health` `git_sha == b9e4b3a` before trusting this entry**.

- **Slice 1 — the desk window (`b22f471`).** New `DESK` trigger in
  `decide_sweeps`: inside `ODDS_DESK_WINDOW_UTC` (live `16-04`, **Joe's
  answer 2026-08-23** for when he actually looks: 9am–9pm PT), every sport
  with stored upcoming fixtures re-buys on the existing 10-min refresh
  cadence. A due slot owns its sport (SCHEDULED + prop ride preserved,
  pinned incl. the refused-slot case); desk buys never carry props; same
  `credits_left`, refused by name. `window_status` predicts desk buys in
  `next_call_ms` and `first_window_open_ms`, so the stale-exit UI is honest
  with zero frontend change. Cost: **288/day at 2 sports, ~8,600/mo** vs
  caps 600/day, 13,000/mo. **At 4 sports it BREAKS the 13,000 monthly
  self-cap (~17,300)** — recorded in `fly.live.toml` as a decision for when
  NCAAF/NFL land. Three guards mutation-red. Watch after deploy:
  `odds_snapshots` growth (retention deliberately excludes it, ADR 0054;
  desk sweeps ~4× its write rate; the live volume was at auto-extend limit
  per ADR 0002's correction) — check `db-sizes` in a few days.
- **Slice 2 — the CLAUDE.md actionable paragraph corrected (`eb312a1`),
  and the skeptic inverted the draft.** Live census: **11 rows / 6 games /
  `suggested_contracts = 0` on all / 4 sharp-anchored**. First draft said
  the soft-fallback reason was dead; measurement-skeptic FAILED it on 8
  defects — 4/11 (36%) against a **73% base rate** is sharp
  UNDER-representation, evidence *consistent with* ADR 0021. Spine
  paragraph now carries the base rate, the thin-consensus twin
  (`devig.py:289` selects ≤3 sharp books), and the still-unrun separating
  measurement (unsuppressed split by `anchored_on_sharp`).
  `docs/measurements/2026-08-23-actionable-population-reaudit.md`.
- **Slice 3 — live routes are readable (`c374486`/merge `fb440cf`).**
  `scripts/fetch_live_route.py`: GET-only structurally (AST-pinned),
  8-path allowlist, loopback-hardcoded, in the ssh image via
  `.dockerignore` negation + `SSH_INVOKED_SCRIPTS`. Usage: `flyctl ssh
  console -a kalshi-cockpit -C "python /app/scripts/fetch_live_route.py
  /api/slate"`. Until now NO session had ever read any live route but
  `/api/health` — every "the screen shows X" was a DB reconstruction
  (lesson written).
- **Slice 4 — `unmatched_items` reader (`ab8509c`/merge `a66354a`).**
  `scripts/list_unmatched.py`, read-only (mode=ro pinned red), before NCAAF
  fills the queue. **Falsifiable prediction standing:** first
  `americanfootball_ncaaf` row in `api_credits` ~**2026-08-25** (48h
  bootstrap horizon before the 08-27 kickoffs); if 08-26 passes without
  one, the horizon is NOT the explanation — investigate.
- **Also:** 5 pre-existing test failures fixed (`b9e4b3a`) — the
  prune-frontier fixture froze NOW_MS while the query stamps real
  `datetime.now()`; went red by pure wall-clock 3 days after writing.
  Lesson: a pinned fixture clock against a wall-clock instrument is a test
  with an expiry date. **The prior session's "3,937 passed" was true when
  written and silently false today** — same family as the stale stored
  number.

**Killed/deferred by the partner ruling (do not re-derive):** NCAAF alias
file (premature — 48h horizon explains zero NCAAF calls); `no_edge`
mislabel (real, bounded, behind these); manual-ticket fixture render
(arming is behind funding; balance $2.533). Loose facts carried: unexplained
live machine restart 2026-08-23T03:42Z; `portfolio_poll` warns the
positions row shape was never captured.

**VERIFIED ON LIVE, ~17:25Z, on the served payloads (a first):**
`/api/health` `git_sha == b9e4b3a`, `instance_mode: live`. `/api/window`
read through the new fetcher: `fixtures_fresh: 21 of 21`, last sweep 37s
old, `spent_today: 6`, next refresh +10 min — and **WNBA was bought with no
due slot** (its kickoff slot opens 19:25Z), which is the DESK trigger
observed working, not inferred. `/api/slate` served **59 rows, zero
`suppressed_reason` of any kind** — against 63-of-71 `stale_odds` the same
morning. Still worth checking in a few days: `credits-day` matches the
~288/day arithmetic, and `db-sizes` for `odds_snapshots` growth.

---

## 2026-08-22 (third session) — the pass gets its caller, the probe gets cheap to start, and stale odds get an exit

Session start found the work list empty; the partner convened and ruled
(three lanes), and Joe added a fourth live: his slate read `stale_odds × 33`
as a letdown and he approved the exit slice by AskUserQuestion. He also
asked whether staleness should *weigh less* — answered in session: it is a
validity check, not a quality factor (a stale comparison's biggest "edges"
are the line moves we missed — rule #1), and the fix is a fresh read, not a
softer bar. Four lanes ran in parallel (three worktrees + one read-only
agent); merged clean; **state: 3,937 passed / 10 xfailed** (+42), ruff
clean, tsc clean, `next build` green. Plan:
`C:\Users\josep\.claude\plans\read-tasks-next-md-and-start-reactive-pearl.md`.

**Shipped, by lane:**

- **A — the Pass control lands on the market screen (ADR 0066).**
  `POST /api/desk/pass` had no caller anywhere in `frontend/` — the
  four-time-repeated pattern at route level. Now: `app/pass/route.ts`
  (token held server-side), `"/pass"` in `JSON_ROUTE_HANDLERS`,
  `recordPass()` in `lib/api.ts`, and `PassControl.tsx` on
  `/market/[ticker]` below the ManualTicket — bordered pill, no confirm
  (a dialog gives the impulse a veto), reason optional-and-collapsed,
  never `bg-accent`, Hint says it records a decision and blocks nothing.
  **The per-row slate Pass is REJECTED and ADR 0066 records why** (390px
  geometry forces a full-width bar under every row; tap-cheap passes turn
  the decisions headline into noise; night+market is the complete ladder)
  — do not re-propose it. Six source-grep tests; five mutations red plus
  the existing `{total, first_ms}` tripwire re-verified red.
- **B — the C0 probe suggests its own candidates, sending nothing.**
  `probe_create_order.py --suggest` walks `/events` discovery (never
  `/markets`), prints three copy-paste commands for markets with side ask
  in (1c, 10c] and resting depth; AST-based test proves the suggest branch
  cannot reach the send path (mutation red). Runbook got a ten-line phone
  quickstart. A live run already produced three real candidates — all
  NCAAF longshots at 2c, worst case ~$0.02+fee.
- **D — stale odds get an exit on the slate.** Beside the stale count in
  the refusal disclosure: when the next scheduled odds window opens
  (`lib/nextOddsWindow.ts` reading `/api/window.next_sweep_ms` —
  `timing.py`'s own `window_status()`, one predicate two callers; five
  honest states incl. due-now/budget-spent/unknown-refuses-in-words), the
  existing `RefreshOddsButton` with its credit cost named before the tap
  (a caller, not a gate — server gates untouched), and a `<Term k="stale">`
  glossary entry: stale is a clock verdict, not a quality one. Matching is
  split-exact so `stale_kalshi_quote` (which no odds refresh fixes) never
  gets a lying button. 17 tests, 8 mutations red.
- **C — the manual door's read side verified on live, read-only**
  (runtime-realist, loopback over `flyctl ssh`; zero POSTs). Both answers
  YES: `GET /api/manual/market/{ticker}` serves real uncached venue facts
  (`authorised_contracts` arithmetic checked: 23 at a 1c ask under the
  $0.2555 cap), and the pass-aware `/bets` is the shipped bundle
  (`43 bets · 0 passes` server-rendered on live). Three facts that bound
  the arming decision, for Joe below.

**FOR JOE:**

1. **The C0 probe now starts itself**: run
   `.venv\Scripts\python.exe scripts\probe_create_order.py --suggest`
   (sends nothing, names three candidates + exact commands), then the real
   command from the runbook's new quickstart.
2. **Before arming, know this (Lane C):** the venue balance is **$2.56**,
   so the derived per-bet cap is $0.26 — armed, the confirm button would
   be dead on everything but sub-25c longshots until you fund the account.
   Also: the reachable-path ticket UI has never rendered on live (flag
   false routes every response to "blocked"), and the flag reads at boot
   only (a Fly env change forces the restart anyway).

**Continuation, same session (~14:30Z) — every loose thread closed:**

- **$2.56 is current, not stale**: latest `venue_balance_snapshots` row was
  150s old on the 5-min cadence, still 2555 tenths. The funding fact above
  stands as a fact about the account, not about the poller.
- **The KXMVE GET answered** (one loopback call): `/api/manual/market/`
  serves a combo ticker 200 with no combo-specific warning, but the book
  itself is the guard in practice — YES ask 0c, depth 0.0 both sides (the
  enter-only shape the record describes), so `authorised_contracts` is 0
  and no ticket could confirm. The POST's 422 stays the structural guard.
  Cosmetic gap (GET doesn't *name* the POST refusal) noted, not fixed.
- **Lane D's overflow gate ran for real** — the first "pass" was against a
  stale leftover server from Lane A's run (EADDRINUSE caught it). Against
  the merged build with refused rows seeded: **1280 FAILED, pre-existing
  on de931ec** — the name link ('Philadelphia', 90px) painted over the ask
  column's 80px `minmax(0,1fr)` track. Fixed with `truncate` (`995dbfd`,
  the `min-w-0` was already there for exactly this), gate re-run **green
  at all five widths**, 390 screenshot eyeballed (Lane D's
  nothing-to-schedule branch renders honestly on the stale demo).
- Worktrees and their branches fully deleted; `995dbfd` deployed and
  verified on live.

**Continuation 2 (~04:10Z next UTC day) — the C0 probe is TAKEN.** Joe ran
`--suggest`, then authorized the spend by pasting the command in session;
the session executed it with the confirmation ticker on stdin
(`INSTANCE_MODE=live` set explicitly for the one invocation — the
prerequisite refusal fired first on the demo default, as designed).
Statuses **201 / 409 / 201 / 201+200** — full detail in the runbook's new
Result section (`docs/runbooks/c0-create-order-probe.md`). The 409
(`order_already_exists`) is the observed idempotency refusal. The fill paid
`average_fee_paid 0.0014` on 2c×1, which `calculate_fee(20,1)` predicts
exactly at the full 0.070 coefficient — first non-MLB fill, consistent with
the series-attribute reading of the baseball split, pinning nothing beyond
this cell (the runbook pre-registered that caution). Capture LOCAL only
(SHA in the runbook); synthetic fixtures + shape tests shipped
(`tests/fixtures/create_order_responses.json`,
`tests/test_create_order_response_shapes.py`, 10 tests, resting-default
mutation verified red); `_read_response`'s "never been observed" docstring
corrected. The create response is FLAT — no `order` wrapper.

**Open: the arming decision is now genuinely Joe's** — the probe
precondition (ADR 0063) is discharged. Before arming matters: fund the
account (the $2.56 balance caps every bet at $0.26).

---

## 2026-08-22 (second session) — the every-page review ships whole: kill list, glossary, real limits, and a manual door built dry

Joe asked for an every-page UI review "with Claude and Chrome" plus two
requirements: tooltips that teach a novice every term, and **purchasing from
the portal instead of the Kalshi app**. All 14 screens were screenshotted
live in Chrome; the partner convened six agents over the evidence and ruled;
Joe approved the plan by AskUserQuestion (buy path as ruled, all four kill
items, C0 probe greenlit — he runs it himself). Full plan:
`C:\Users\josep\.claude\plans\enumerated-noodling-simon.md`. Mid-session Joe
also corrected the record: **he is NOT phone-first — equally desktop**;
memory updated, every slice designed and verified for both.

**State: 3,895 passed / 10 xfailed** (+58 over baseline), ruff clean, tsc
clean, `next build` green. ADRs 0063 (manual path separate, never feeds the
gate), 0064 (daily loss reads `venue_settlements`, refuses on stale), 0065
(P(YES) is the ticket's precondition; `/estimate` form retired).

**Shipped, by lane:**

- **A-lane (screens).** Kill list: `/builder` deleted, `/rejections` folded
  into the Slate's disclosure, `/scout` index absorbed (meter now a
  disclosure in ScoutDesk), `/estimate` is record-only under "Estimates",
  `/bets` took Scout's nav slot, `/slate`+`/dashboards` moved to the
  reachability EXEMPT list with reasons. Landing leads with games (panel
  demoted behind `lib/refreshUrgency.ts`, node-tested; SignalStrip below
  rows; 4 stats → 2; heading now "Games"). Board's schedule/refresh fold
  into `<details>`, SignalStrip below the cards. `lib/tickerLabel.ts` keeps
  ticker tails; `lib/leagueLabel.ts` says MLB not baseball_mlb; gate
  conditions got plain headlines. `components/Hint.tsx` makes every
  hover-only caveat tap-visible (soft fallback above all). Glossary 14 → 22
  terms (contract, consensus, devig, settled, bankroll, depth, exposure,
  quarter-Kelly, fill, W/L, net; three orphans deleted; `stake` no longer
  instructs "$2, every time"), TicketSheet fully termed, and
  `tests/test_glossary_coverage.py` pins coverage four ways. Kalshi deep
  links exist (`lib/kalshiLink.ts`, scheme verified in a browser).
- **B-lane (limits).** Daily loss reads the venue mirror and refuses on
  stale (ADR 0064; settlements joined the 5-min poll cadence). Caps render
  always as server display strings with `caps_basis`; the slate says "your
  cap is Xc a bet" + the deposit line. Open positions surface on slate and
  /bets (count on the 12h clock, portfolio value on the 5-min clock, each
  with its own staleness refusal, never summed). Scope sentences rewritten.
  /bets gains Not-tonight, "CLV scored on N of M", and the decisions
  headline over the new append-only `desk_passes`.
- **D-lane (the manual door, DRY).** `manual_orders` table +
  `MANUAL_ORDERS_ARE_DRY_RUNS = True` + `POST /api/manual-orders` with
  twelve unwaivable server-side checks (demo refuses on mode regardless of
  the `MANUAL_ORDERS_ENABLED` flag — false in both fly tomls; lockout and
  10-min cooloff 423s; KXMVE refused; daily-loss over the mirror;
  balance-derived caps; ceiling refused never repriced; depth; fee-inclusive
  worst case; live positions read refusing anything unprovably non-netting;
  IOC only). `GET /api/manual/market/{ticker}` serves any ticker's live
  facts + "authorises N". The ManualTicket on the market screen asks P(YES)
  with the ask masked before revealing anything (pinned by source test).
  Migration **v18** adds `fills.venue_order_id` (the join back to manual
  orders). `gate.py` never reads `manual_orders` — pinned.

**FOR JOE — the two things only you can do:**

1. **Run the C0 probe** (before the manual path can ever arm):
   `.venv\Scripts\python.exe scripts\probe_create_order.py
   --i-am-joe-and-this-spends-money --ticker <TICKER> --side yes` on a
   market with an ask ≤10c. Worst case under $0.14. Runbook:
   `docs/runbooks/c0-create-order-probe.md`. The capture stays local
   (operator data); fixtures get hand-written from the shape.
2. **Decide when to arm**: after the probe, arming = set
   `MANUAL_ORDERS_ENABLED=true` on live AND flip
   `MANUAL_ORDERS_ARE_DRY_RUNS` in a commit (ADR 0063; starts at a
   1-contract ceiling).

**Open:** the per-row "Pass" affordance on the slate (B6 left it for a
design pass); `docs/measurements` has nothing new (no measurements were
taken — this was build work under standing rulings).

---

## 2026-08-22 ~13:15Z — the betting-desk list closes out: CLV on his own bets, then the ticket cleanup

**Both remaining items on the 2026-08-21 partner ruling's work list are DONE.**
That closes the list started 2026-08-21 (refusal-on-real-data, strip the
landing screen, CLV on his own bets, ticket cleanup) — all four shipped.
State: **3,837 passed / 10 xfailed** (net +12 over the 3,825 session-start
baseline: +13 new CLV tests, −1 test deleted with the dead code it pinned),
ruff clean, tsc clean, `next build` green. Two commits (`3067bf2`, `84fbbea`),
**neither deployed** — live needs a deploy to carry this.

- **CLV lands on his own bets (`3067bf2`).** `backend/scoring.py`'s
  `markets_awaiting_scoring` unions in `venue_settlements`, gated on a
  `kalshi_markets` discovery row and an `event_links` match, stopping once
  any `closing_lines` row exists for the ticker (no `clv_scored_ms` to flip,
  so this is the only stop-predicate available). Most hand-bet tickers
  refuse structurally at the join — expected, per the ruling.
  `backend/bets.py:bet_clv()` reads it back on request: LEFT JOIN
  `closing_lines` at the primary horizon, the exact `clv.clv_tenths()`
  convention, and the entry-before-close rule via `position_first_seen_ms`
  (NULL refuses, never treated as "before everything"). Four refusal
  reasons, each named: `no_closing_line`, `unreadable_close`,
  `entry_time_unknown`, `entry_after_close`. `/bets` renders per-row only —
  your price, the close, the difference — **no average, no hit rate**,
  checked by a source-grep test (`test_module_computes_no_aggregate_clv`)
  so the constraint can't quietly regress.
- **The ticket cleanup (`84fbbea`), janitorial, one slice, nav-swap clause
  dropped** (Scout already took the sixth slot). Removed the `!actionable`
  branch on `TicketSheet`/`TicketProvider` that a 2026-08-18 finding proved
  structurally unreachable — `TicketTrigger` is the sheet's sole opener,
  passes no override, and every row it opens already arrived actionable
  (`board.surfaced` is `routes.py`'s actionable-only partition). Renamed
  `/ledger`'s nav label and page heading from "Ledger" to "Evidence" — now
  that `/bets` is Joe's real settled-bet record, the old name on the
  engine's evidence page was the exact "one word, two screens" confusion
  the 2026-08-20 nav convening fixed for three other nouns and explicitly
  left this one alone for. Route and function names (`/ledger`,
  `fetchLedger`) untouched, matching `/board`'s "Picks" precedent.

**Deployed 2026-08-22 ~13:40Z**: `ed05307` verified live (`/api/health`
`git_sha` matches, `instance_mode: live`). **The two invoice numbers (ADR
0062 §4) are DROPPED, not open** — Joe declined to pull them, 2026-08-22
("let's just drop that"); do not carry them as work or ask again.

**Next session starts here.** Nothing is queued by name — the explicit work
list is empty for the first time since 2026-08-21. Check the partner's
"later, maybe" lists (2026-08-21 review + ADR 0061) for anything worth
promoting, or wait for Joe's direction. The footer parity note stands
(6-and-6, at the bound — the next footer addition must answer the
delete-commit question, not land there by default).

---

## 2026-08-21 ~23:30Z — the landing screen stops claiming an edge, and the session hands off

**"Strip the landing screen" is DONE** — the last slice this session ships.
State: **3,825 passed / 10 xfailed**, ruff clean, tsc clean, build green,
overflow gate green at 390/768/1280/1440/1920, deployed (verify
`/api/health` `git_sha` against `origin/main` — the deploy was dispatched
at the end of this entry's session).

- **The edge point estimate is off the slate rows** (`+X.Xc`, tone, mark
  — all gone). The Board (`/board`) is the edge-finder feature and still
  renders it through `EDGE_TONE_CLASS`; the landing screen now leads with
  ask, break-even, books, freshness. Page docstring names the ruling.
- **`DispersionStrip` is a range behind a tap**: summary shows the spread
  in points on every width (the ADR 0052 phone reader still sees the
  magnitude untapped); the tap reveals the two ranges and the caveat. The
  ask is no longer drawn against the readings (direction claim) and the
  `used` mark is gone (the point estimate one layer down). The geometry
  lib is untouched; its tests still run.
- **`Width` stands alone** — its warning ink compared against the edge,
  which is no longer shown, so the comparison went with it.
- **Two pins inverted with dated docstrings** citing the ruling:
  `test_board_screen.py` now bans `edge_cents`/`edgeTone` from the slate
  page (mutation verified red: re-adding `row.edge_cents` fails it);
  `test_dispersion_strip.py` now bans `d.kalshi` from the component.

**NEXT SESSION STARTS HERE — CLV on his own bets** (the ruling's
re-scope, `docs/reviews/2026-08-21-items-2-3-ruling.md`). Scoped this
session, ready to build:

1. **Union into `backend/scoring.py` `markets_awaiting_scoring`**: a
   second SELECT over `venue_settlements` v JOIN `kalshi_markets` m ON
   m.ticker = v.ticker JOIN `event_links` l ON l.kalshi_event_ticker =
   m.event_ticker JOIN the same MIN(commence) odds subquery — so closes
   get captured for his markets. Stop-predicate: NOT EXISTS a
   `closing_lines` row for the ticker (else refetched every pass
   forever). Most hand-bet tickers will refuse structurally (no link) —
   that is expected and honest; the partner said so.
2. **`/api/bets` computes per-bet CLV on read** (like the matcher: on
   read, not at ingest — no new columns): LEFT JOIN `closing_lines` at
   `DEFAULT_HORIZON_HOURS`, then the EXACT existing convention —
   `backend/analysis/clv.py:clv_tenths(entry_price_tenths, close_mid,
   side)` (close mid = (yes_bid+yes_ask)/2; entry is already
   side-denominated in both tables). Apply the same entry-before-close
   exclusion using `position_first_seen_ms` (NULL → refuse; a bet placed
   after the close observation must not be scored against it —
   `clv.py:234` has the argument).
3. **Render per-bet rows ONLY on `/bets`**: your price, Kalshi's close,
   the difference — server-rendered display strings. **NO average, NO
   hit rate, NO "you beat the close X% of the time"** until n ≥ 30 with
   the per-group view printed beside it — the partner's hard constraint,
   on the most ego-loaded quantity in the product.

Then the last item: **ticket cleanup** — `TicketSheet`/`TicketProvider`
dead-code removal + "Ledger" rename, janitorial, one slice. The nav-swap
clause is dropped (Scout holds the sixth slot).

**Still open from before:** footer parity (6-and-6, at the bound);
partner's "later, maybe" lists (2026-08-21 review + ADR 0061); the Fly
invoice and first Anthropic invoice remain the two unpulled numbers
(ADR 0062 §4).

---

## 2026-08-21 ~22:45Z — the refusal lands on real data, and the lockout gets the desk's name

**"The refusal on real data + the desk lockout" is DONE, built exactly to
the ruling** (`docs/reviews/2026-08-21-items-2-3-ruling.md`). State:
**3,825 passed / 10 xfailed**, ruff clean, tsc clean, build green, overflow
gate green at all five widths.

- **Fills joined the 5-minute cadence.** `poll_fills` extracted from
  `poll_portfolio` and called beside `poll_balance` in the forever loop.
  NOT a registration amendment — §7.6 sets a completeness floor and the
  comment says so; settlements, positions and the matcher stay on the
  registered 12h clock. Without this the strip would read "no bets
  tonight" at 8pm off a 10am mirror — the false negative in the
  flattering direction the ruling called disqualifying.
- **`/api/slate` gained `tonight`**, a SIBLING of `money` (whose contract
  is never-sum): distinct-ticker count and unsigned stake since the day
  roll, from `bets.tonight_activity` — no `source` filter (committed
  money is committed money, ADR 0043's split is for fee calibration), day
  rolls at the odds budget's hour, and **null — never 0 — when the fills
  mirror is stale** (`TONIGHT_STALE_AFTER_MS` = 30 min = 6× cadence).
  `lockout_until_ms` rides the same key: one fetch, one state. Three
  guards mutation-verified red (staleness dropped, DISTINCT dropped, day
  bound dropped), file restored byte-identical each time.
- **`POST /api/desk/lockout`** — the lockout outlived the study that
  named it. Same `self_lockouts` table, same clock-derived release, no
  disengage, no picker; `/api/estimates/lockout` stays deprecated-but-
  working (a deployed frontend may still call it; both write one table so
  they cannot disagree — the test proves the release instant agrees
  across both names). `frontend/src/app/lockout/route.ts` repointed.
- **The landing screen** renders the strip beside the money line
  (`TonightStrip.tsx`): "N markets · $X.XX staked tonight, your own
  fills", stale → "not read since HH:MM — which is not the same as no
  bets", plus the one-tap "Not tonight". Locked → a banner that keeps
  the slate visible, has NO show-anyway, names the release time, and
  admits it cannot stop a bet in the Kalshi app. No engagement counter.

**The work list, by name, unchanged in order:** strip the landing screen
(NEXT — edge point estimate off the slate rows; DispersionStrip becomes a
range behind a tap, no direction, no `used` mark; note
`tests/test_dispersion_strip.py` pins "off this scale" and ADR 0052's
on-the-phone spirit — update those tests with dated docstrings citing the
ruling, keep the `<DispersionStrip` callsite pin satisfied); then CLV on
his own bets (re-scoped: per-bet rows, NO aggregate below n ≥ 30); then
the ticket cleanup (nav-swap clause dropped).

**Still open from before:** footer parity (6-and-6, at the bound);
partner's "later, maybe" lists.

---

## 2026-08-21 ~21:45Z — /bets ships, and the partner re-rules the refusal work by name

**"His own record" is DONE** (the top item of the betting-desk list): the
poller has mirrored `venue_settlements` since 2026-08-18 and nothing had
ever read it back to him. `backend/bets.py` computes per-settlement net via
the ONE registered settlement formula (A2: payout − cost − fee, integer
tenths, `Decimal` multiply) — a void or unreadable price/fee is **None,
never $0.00**, and the totals count what they exclude. Totals cover the
whole table while the list is windowed (the /api/ledger lesson).
`GET /api/bets` + `/bets` page (net strip, W/L, per-position rows linking
to market screens, the mirror caveat in words), linked from the footer —
nav is deliberately not decided here. Money display strings render
server-side (`format_net_dollars`), per `lib/api.ts`'s no-arithmetic rule.
The embargo line: this never touches `bet_estimates` (Amendment 2 stopped
the study without result; A7 rules the wallet outside the embargo).
State: **3,816 passed / 10 xfailed**, ruff clean, tsc clean, build green,
overflow gate green at all five widths with `/bets` listed.

**The partner convened on the two refusal items and ruled — full text in
`docs/reviews/2026-08-21-items-2-3-ruling.md`.** The load-bearing calls:
tonight's count/stakes come from **fills, not settlements** (settlements
are the wrong clock and can only produce a net — the chase trigger this
repo already deleted twice); **fills join the 300s balance cadence** (the
12h mirror at 8pm renders "no bets tonight" while three are on — a false
negative on the interrupting screen; not an amendment, cadence is a floor);
the strip **refuses when stale** (as_of > 30 min → null, never 0); it lands
on **the landing screen only**, as a sibling `tonight` key beside `money`
(never inside it); the lockout **repoints to `POST /api/desk/lockout`,
render-only**, honest that it cannot stop a hand bet, no show-anyway, no
counter, old study routes left deprecated in place.

**The work list is now BY NAME (the numbering collided across entries —
the partner's call). In order:**
1. **The refusal on real data + the desk lockout** — build per the ruling
   doc, one slice (fills cadence, `tonight` payload, landing strip, banner,
   `/api/desk/lockout`).
2. **Strip the landing screen** — promoted: edge point estimate off,
   dispersion-as-range behind a tap, no direction, no `used` mark. Same
   file as the refusal work.
3. **CLV on his own bets** — demoted and re-scoped: per-bet rows only
   (your price, Kalshi's close, the difference), NO average or hit rate
   until n ≥ 30 with the per-group view beside it.
4. **Ticket cleanup, janitorial, last** — `TicketSheet`/`TicketProvider`
   dead-code removal + "Ledger" rename. The nav-swap clause is DROPPED
   (Scout took the sixth slot).

**Still open from before:** footer parity note (footer is now 6-and-6 with
nav — at the bound, so the next footer addition must answer the
delete-commit question); partner's "later, maybe" lists (2026-08-21 review
+ ADR 0061).

---

## 2026-08-21 ~20:30Z — the desk gets a token meter and a nav slot in one change, and the gold goes out

**The partner's betting-desk item 6 is done, all three clauses, one slice.**
It was flagged urgent because the meter is protecting Joe's fresh $20 — the
account had actually run dry (ADR 0062 §3). State: **3,807 passed / 10
xfailed** (+13), ruff clean, tsc clean, `next build` green, overflow gate
passes at 390/768/1280/1440/1920 with `/scout` on the page list.

**The meter (schema v17).** The 24-call cap counts calls; a staff scout's
call carries the web-search tool at `max_uses: 6`, so one convening could
spend 12 searches — billed per-search, results billed as input — inside
three perfectly-counted calls. Now:

- `agent_calls` gains `input_tokens` / `output_tokens` / `web_searches`
  (nullable, no backfill; migration 17). `structured_call` returns
  `StructuredCallOutcome` — parse AND the API's usage block, usage kept even
  on a safety refusal (still billed), `None` only when no response arrived;
  `settle` writes it. NULL usage rows are counted as `calls_unmetered_today`
  so the sums state what they miss.
- Two daily brakes in `AgentBudget`, evaluated over RECORDED usage **before**
  the next reserve — never a field the gated call will write (the
  receipt-not-a-brake lesson): `AGENT_MAX_SEARCHES_PER_DAY=60`,
  `AGENT_MAX_TOKENS_PER_DAY=500000` (defaults bind early, arithmetic in
  `.env.example`; also set in `fly.live.toml`). The desk states its staff
  pair's pre-known worst case (`STAFF_PAIR_SEARCHES_WORST_CASE = 12`) at
  both gates — `convene_desk` and the POST route's early refusal — from one
  module-level constant so they cannot drift.
- Mutation-verified red, file restored byte-identical each time: sum→count
  in `state()`, token check dropped, settle-usage dropped, and
  `searches_worst_case` dropped from the desk's `can_afford`.

**The screen and the slot.** `GET /api/scout` (public read) serves the last
50 convenings as summaries — never briefing bodies — plus today's spend in
the three units that bill: calls, searches, tokens. Counts, not dollars;
`spend: null` on a keyless instance (the demo), which is "no account to
meter", not an empty meter. New `/scout` page renders the meter above the
convening record and deliberately has **no send button** — the desk is sent
from a game's screen, because a desk sent from a list invites filling the
list. **Scout takes the nav's open sixth slot** (Log's retired one), placed
so Gate keeps its visible position at 390px and Playbook stays the link that
scrolls; `test_the_nav_budget_is_still_six` records the trade.

**The gold is out.** The `fresh` tile and the unpriced-finding chip wore
`accent-2` — the palette slot every other screen reserves for "do not trust
this" (test_palette_contrast.py) — to light the staff's own unfalsifiable
`likely_already_priced` guess as if it were an edge signal. Both are
neutral now: glyph, border and weight carry the state; the verdict strip
says "recent is not the same as unpriced". ScoutDesk's send copy now names
the searches and points at the Scout screen's running total.

**For the next session:** live needs a deploy to carry all of this (v17
migrates at boot via `scripts/migrate_db.py`; additive columns, safe on the
volume). The 08-18 session entries moved verbatim to
`tasks/archive/next-2026-08-18.md` (index updated); the 08-17-dated entries
still in this file share titles with archived ones but differ in text —
left untouched, resolve deliberately or not at all.

**The partner's remaining betting-desk list, renumbered:**
1. `/bets` — his own record from `venue_settlements` (embargo checked this
   session: Amendment 2 stopped the study without result, the estimate log
   stays embargoed forever, and A7 rules `venue_settlements` outside it —
   buildable so long as it never touches `bet_estimates`).
2. Refusal onto real data — tonight's count/stakes over `venue_settlements`
   with the lockout beside it, on the deciding screen.
3. Repoint the lockout off the stopped study's endpoint.
4. CLV on his own bets — union `venue_settlements.ticker` into
   `backend/scoring.py:97`.
5. Strip the landing screen — edge point estimate off; dispersion-as-range
   behind a tap, no direction, no `used` mark.
6. `TicketSheet`/`TicketProvider` unreachable-code removal; "Ledger" rename.

**Still open from before:** footer 5-and-5 parity note; partner's "later,
maybe" lists (2026-08-21 review + ADR 0061).

---

## 2026-08-21 ~18:30Z — Joe rules the purpose, the Skeptic retires, and the cost record gets honest

**The ruling, verbatim and now in ADR 0062 + agent memory:** *"I always
wanted this to be a betting desk. the edge-finder should have been a
feature, but not a determiner."* Preceded by "I don't care about 1-2 cent
diffs" — his position size makes the venue's whole cost advantage ~15
cents/bet. ADR 0038 closed the hunt on measurement; 0062 closes it on
purpose. Gate, dry-run constant, suppression rules, odds feed: untouched.

**Built this session (the partner's item 3, the one bleeding money):**

- **Scheduled Skeptic killed.** The partner's cost audit found `agent_calls`
  refuting `fly.live.toml`'s "surfaced=0 protects the bill": **24 Opus calls
  in 4m22s on 2026-08-16** (whole daily cap, four prop rows re-reviewed 6x),
  all blocked — so `surfaced` read 0 *after* the spend. `run_pricing_pass`
  now defaults to `review_retired` (refuses every surfaced row as
  `skeptic_unreviewed` / "retired (ADR 0062)", zero Anthropic calls;
  `review_surfaced` stays importable, opt-in only). Mutation-verified:
  restoring the old default turns `TestTheScheduledSkepticIsRetired` red.
  From now on `surfaced` is frozen at its historical values.
- **Four doc corrections**, all understating deployed reality:
  `fly.live.toml` spend-trap block rewritten with the refutation; sweep cost
  6→2 (h2h only); "400/day"→600; `.env.example` 400→600; ADR 0002 "$5/mo,
  1GB" gets a dated correction (live is 2GB, volume at auto-extend limit).
- **Lesson written:** a field computed after the spend is a receipt, not a
  brake — the money-shaped case of "verification methods that lie".
- **"The recorder costs nothing" is retired** (ADR 0062 §4): ~70 Odds
  credits/day measured, sole reason the $30/mo tier exists, plus 2GB
  always-on machine. Recorder keeps running (feeds Board + scout desk).

**Joe answered three of the open calls, same day (~16:10Z):**
- **The Anthropic account had actually run DRY** — "I ran out of API
  credits, so its a fresh new $20 i just deposited." This retroactively
  hardens ADR 0062 §3: the spend was not hypothetical, it emptied the
  account. The Skeptic retirement and the coming scout-desk token meter
  are protecting a fresh $20, so treat that meter (work item 6) as urgent.
- **The $30/mo Odds tier stays.** His call, recorded.
- **The 22:40Z look is VETOED** — result file committed, see SESSION START
  box. Fly invoice remains the one unpulled number.

**The partner's remaining betting-desk work list, in priority order** (full
reasoning in its 2026-08-21 ruling; each is a vertical slice):
1. `/bets` — his own record from `venue_settlements` (zero routes/screens
   today; check the ADR 0044 embargo release first).
2. Move the refusal onto real data — tonight's count/stakes over
   `venue_settlements` with the lockout beside it, on the deciding screen.
3. Repoint the lockout off the stopped study's endpoint.
4. CLV on his own bets — union `venue_settlements.ticker` into
   `backend/scoring.py:97`.
5. Strip the landing screen — edge point estimate off; dispersion-as-range
   behind a tap, no direction, no `used` mark.
6. Meter the scout desk by tokens/searches, THEN promote it to nav — same
   change, not sequential (its 24-call cap meters calls, not the up-to-12
   web searches per convening); neutralise the gold
   `likely_already_priced` tile in the same change.
7. `TicketSheet`/`TicketProvider` unreachable-code removal; nav swap;
   "Ledger" rename.

**Still open from before:** footer 5-and-5 parity note; partner's
"later, maybe" lists (2026-08-21 review + ADR 0061).

---

## 2026-08-21 ~16:45Z — the market screen joins the shell, and the desk scales to a real instrument panel

Joe saw the desktop render ("it's so small") and directed the process
himself: graphic-designer briefed first, then a partner convening with
ui-designer and ux-designer. **ADR 0061** records the outcome; the two
decisions that will be re-derived at full cost if lost:

- **Root cause:** the market page hardcoded `max-w-3xl` — narrower than its
  own Nav. It now imports `SHELL_WIDTH`, and `test_desktop_tier.py` bans
  `max-w-3xl` in shell surfaces alongside `max-w-5xl`.
- **The 24rem facts rail all three designers first assumed was killed on
  arithmetic** (main would be 856px → 122px tiles; the rail eats exactly
  the pixels that answer the complaint). Rule: a data band goes full shell
  width, prose caps at 65ch inside it; a rail must earn its content.

Also: tiles ~193px at xl (`xl:` variants only — container queries rejected
for breaking sub-xl byte-identity), six-across pinned; re-send buttons lose
`bg-accent` (red = money; pinned, mutation-verified both); quote strip takes
no size step (the ask never exceeds body size); ticker demoted below the
board; `check_mobile.py` gained `--market-ticker` (ADR 0047's own gate had
never measured this page) and passes at 390/768/1280/1440/1920 with the
real MIL ticker; ScoutDesk + market page joined `PROSE_FILES`.

State: **3,791 passed / 10 xfailed**, ruff clean, tsc clean, build green,
deployed (`9952a0f` verified on live). **Joe answered the look-at-it
question 2026-08-21 ~15:20Z: "6 tiles across one row is fine"** — the
six-across pin stands as built. He also re-sent the scouts post-board
(filed 15:17Z): the master's own tiles rendered correctly on live, and his
read correctly named the unchecked same-day lineups as the briefing's real
content. Session ended here at Joe's request; this entry is the handoff.

**Still open:** tonight's terminal spread/total look at 22:40Z (session
alive in band 22:35–22:45Z; replay gate PASSED 04:04Z); footer 5-and-5
parity note; partner's "later, maybe" lists (2026-08-21 review + ADR 0061).

---

## 2026-08-21 ~15:30Z — the briefing becomes a cockpit, and the market screen serves the venue's facts

Joe read the desk's first real briefing (Braves–Brewers, filed 14:03Z) and
gave three directions, verbatim in the memory file
`briefings-are-visual-first-and-sport-neutral.md`: visual like a cockpit,
sport-neutral, good on desktop AND phone. He then asked for the market
screen itself to be made more useful, "ask the partner to consult with the
relevant agents."

**The partner convened seven agents and ruled: render the venue's facts,
never the tool's opinion** — full direction + the explicitly-not-doing list
in `docs/reviews/2026-08-21-market-screen-direction.md`. All eight build-now
items are built, tested, mutation-verified where they guard money or
honesty:

- **The board**: the master scout fills six sport-neutral instrument tiles
  (fresh / stale_only / unconfirmed / clear), completed server-side
  (`complete_board` — missing→unconfirmed, duplicates→most-alarming,
  unearned clear→unconfirmed). Binary verdict strip, no counts — a count
  was the one number the schema forbids, manufactured client-side. Glyphs
  as primary channel; `clear` unlit; only `fresh` carries hue.
- **The market screen**: ScoutDesk above the fold, chart in a closed
  details with the history-not-a-quote caveat in its summary; header is
  `Away @ Home / YES = team / league · start · status` off the odds clock
  (never `kalshi_events.commence_ms`, ADR 0006); quote strip with LIVE ages
  (`_serialise` now gets `now_ms`/`staleness` — they were frozen at write
  time) and a stale ask refused outright; `close_ms`/`market_status`
  served so settled markets say so. NO line and candles toggle gone,
  ranges Today/All.
- `--border-strong` token added (dashed borders were 1.30:1 — invisible).

State: **3,789 passed / 10 xfailed**, ruff clean, tsc clean, `next build`
green. The first briefing predates the board; its screen shows a derived
board and says so. **The Braves game is worth re-sending to see the real
board** — and the fixture's fun wrinkle (a two-city series claim the scout
couldn't verify) is exactly what the unconfirmed state was built for.

**Still open:** tonight's terminal spread/total look at 22:40Z (band
22:35–22:45Z, session must be alive, replay gate PASSED at 04:04Z); the
footer 5-and-5 parity note; the partner's "later, maybe" list in the
review doc.

---

## 2026-08-21 ~06:30Z — the Scout desk is switched on, on Joe's word: a staff of two and a master, metered

**ADR 0060.** Joe asked for it by shape ("the master scout … a team report to
him … each knowing their own home teams player status, team statuses, weather
if they're playing at home … an expert opinion that would finally serve me at
my desk"). That is the decision ADR 0022 §4 recorded as not-yet-taken, now
taken by the person whose money it spends.

**What shipped, all tested:**

- `backend/agents/scout_desk.py` — one convening = two staff scouts (one per
  club; the home scout owns the venue/weather) + one master who synthesises
  their notes and may not add facts. Three metered calls via the existing
  `AgentBudget` against the same `agent_calls` day as the Skeptic (24/day →
  ≤8 briefings). Staff pair reserved before the first request; master reserved
  only after a note exists; a refusal spends zero. **No numeric field exists
  anywhere in `DeskBriefing`** — walked by test, not trusted to the prompt.
- `scout.py`'s unmetered solo `research()` is **deleted**, not wired; the
  module survives as the desk's schema home. Quarantine row removed from
  `test_has_callers.py`; `scout_desk.py` and `routes.py` allowlisted in
  `BILLED_PATH_CALL_SITES` with their meter named; the historian is now the
  set's only member.
- `scout_briefings` table (schema.sql, IF-NOT-EXISTS so no migration);
  `POST /api/scout/{ticker}` (auth, 202 accepted-never-briefed, 429 before
  writing on an exhausted day, 422 unlinked ticker, 503 no key, 409 already
  running) + public `GET /api/scout/{ticker}` with `gone_quiet` for a
  `running` row older than 15 min.
- Frontend: `/scout-desk` Next route handler holds the bearer server-side
  (same pattern and same widening statement as `/refresh-odds`; middleware
  names the path), `ScoutDesk.tsx` on the Market screen — send button says
  "three metered calls" before the tap, filed-nothing renders dark vs
  looked-found-nothing, refused/failed/gone-quiet all have words. Crew
  bubble's Scout line updated (still an admission; pinned test still holds).
- Mutation-verified guards: numeric field into the briefing schema, dropped
  budget pre-check, reserve-after-call — each red, file restored each time.

**Verification:** 3,782 passed / 10 xfailed (+17 new: 9 desk, 8 API, minus
the timezone guard that caught `ScoutDesk.tsx` rendering device-zone clocks
— fixed with `DISPLAY_TIME_ZONE`), ruff clean, tsc clean, `next build` green.

**What the desk does not do, so nobody re-litigates it:** no probability, no
price, no bet verdict — schemas make those unrepresentable; ADR 0038 is
untouched (§5 of ADR 0060 has the argument). The demo cannot send it (no key,
no token, both halves refuse independently).

**First real convening is the open question.** Nothing has run against a live
game. When Joe sends it, read the briefing critically: quality is unmeasured,
and the `likely_already_priced` flags are the honesty valve to check first.

**Still open, unchanged:** tonight's terminal spread/total look at 22:40Z
(band 22:35–22:45Z; a session must be alive in the band; replay gate already
passed at 04:04Z), and the footer 5-and-5 parity note.

---

## 2026-08-21 ~04:30Z — the replay gate passes exactly, and the ledger's null kickoff is fixed

State at close: tests **3,766 passed / 10 xfailed** (+4), ruff clean, tsc
clean, pushed through `6a23920`. **Live is current: deployed `1673331` at
04:17Z on Joe's word** (run 32446407696, dispatch went through in auto mode
first try; `/api/health` verified `git_sha` + `instance_mode: live`). That
deploy carried `d487d2d` (estimate-form demotion) and `6a23920` (below).
Nothing tonight's look needs is on live — the sweep is a local script.

**The free replay gate for tonight's look was run at 04:04Z and PASSES
exactly.** All five sharp edge values (−25.0, −3.5, −19.2, −15.3, −2.9
tenths), sharp counts 3/3 games and 2/2, both UNDERPOWERED verdicts, total
rows 3 and 4, and the full exclusion dict (incl. `outside_window: 16`)
match Amendment 1's registered gate evidence line for line. The rows
artifact is at
`docs/measurements/2026-08-21-spread-edge-rows-2026-08-21T040406Z.json`
(replay by-product; committed in `e8d4614` by a broad `git add -A` — kept,
since it is derived public-market data and doubles as the gate evidence). The band session should still
re-run the gate before the anchor — it is free and the registration says
before the anchor, not eighteen hours before.

**The `/api/ledger` `commence_ms` defect is FIXED (`6a23920`).** The route
now joins `r.link_id → event_links → MIN(odds_snapshots.commence_ms)` —
the scorer's own definition (`backend/scoring.py:markets_awaiting_scoring`)
— so the ledger's pre/post-commence axis agrees with the machinery that
writes the clv fields. The documented 3-hour trap was refused, not merely
avoided: `kalshi_events.commence_ms` is never touched, and a test plants
the raw `occurrence_datetime` value three hours late and asserts it does
not surface. Unlinked rows resolve to `None`, never a substitute. Four
guards, each verified red by mutation (MIN→MAX, the kalshi_events join,
COALESCE-to-0). Note for any consumer: rows written before the linker had
a `link_id` still read `None` — that is honest, not a regression.

**Open, in order:**

1. **Tonight's terminal spread/total look, 22:40:00Z** (band 22:35–22:45Z,
   4 credits, Joe's veto until the anchor). A session must be alive in the
   band or the look goes UNTAKEN — session timers cap at 1h and die with
   the session, so this needs Joe (or a session he starts) around 22:30Z.
   Every branch writes
   `docs/measurements/2026-08-21-spread-total-edge-second-look-result.md`.
2. The next deploy carries `d487d2d` + `6a23920` (no urgency).
3. The footer 5-and-5 parity note (a constraint on future nav work, not a
   task — `tests/test_every_screen_is_reachable.py` docstring).

---

## 2026-08-21 ~03:15Z — the H4 series closes on a measured reason: the channel diagnostic is BLIND on a denominator of 1

State at close: tests **3,762 passed / 10 xfailed**, ruff clean, tsc clean,
`next build` green, everything pushed. Live is on `349dca0` (deployed this
session, dispatch went through in auto mode first try) — commits after it
are docs/tasks-only except the estimate-form demotion (`d487d2d`), which is
UI + a scope guard and can ride the next deploy; nothing urgent needs it
live tonight.

**The partner convened, re-ruled, and the ruling is executed.** Its key
move: do NOT build the A9–A12 analyzer on schedule — the record suggested
the balance channel cannot see payouts — and instead register the cheapest
test of that (ADR 0059 is the generalised rule). The chain, all committed
in order: **Amendment 3** (`9693847`, pre-registrar: the A15 disclosure of
a partial unblinding, A16 closing the span/cluster voting defect it found
— ~4,000 empty snapshot pairs could have voted — and A17 registering the
channel diagnostic with all three verdicts' consequences fixed);
**analyzer** (`7c78a32`, before the data); **pull** 02:49:45Z (30m35s
after the amendment, one attempt, sections untruncated, SHA in the result
file, raw capture NOT committed per the operator-data ruling);
**three audits** by the measurement-skeptic (FAIL 11 → FAIL 9 → PASS,
chain kept in the record); **result** (`ca8c581`).

**The verdict: BLIND, on a covered-winner denominator of 1** —
`docs/measurements/2026-08-21-h4-channel-diagnostic-result.md`. Per the
consequences fixed before the pull: **Look 2 is written up early as
BLOCKED ON INSTRUMENT** (`2026-08-21-h4-settlement-fee-result.md`),
**Look 3 is cancelled, the series is closed**, the analyzer is never
built, ADR 0027 stands, H4 stays UNTESTED. Reopening has exactly one
door: A17.11's different-channel amendment (candidates named there).
**The audit's finding worth reading:** the pull's own fills section shows
the balance channel reconciling 15 of 16 fills to half a tenth, and a
+4950-tenth movement in the winner's own payout window 1h31m *before*
settlement — the registered tolerance cannot credit it, and the pull
cannot separate "paid early at position close" from "position closed, no
credit due". That is why BLIND extends to no claim about the venue.

Also this session, all committed and pushed: **`h4-balance-spans`
shipped** (`349dca0`, six window-mutation guards red — it fed the
diagnostic its one registered pull and now stays unused); **README's
combo row corrected** (`5aa39ef`, the public repo carried a refuted
reason); **the stopped study's form demoted** (`d487d2d`: Log's nav slot
retired, `/estimate` reachable from the footer with the terminal banner,
and `classify_positions` now bounds the study window on the right at the
owner stop — guard red both ways); **ADR 0059** (`45735e4`); the
unit-mismatch lesson (`6a8092e`).

**TONIGHT'S HANDOFF — the terminal spread/total look, 22:40:00Z:**

1. Registration: `2026-08-21-preregistration-spread-total-edge-second-look.md`
   (+ its Amendment 1). Band **22:35:00–22:45:00Z**, 4 credits, floors 8
   sharp rows / 3 games per arm, NO pooling with look 1.
2. **Joe holds a veto until the anchor.** A veto before the sweep spends
   nothing and is recorded as VETOED; after a successful sweep there is
   no veto — the look is the look.
3. Before the anchor, run the free replay gate:
   `.venv\Scripts\python.exe scripts\measure_spread_edge.py --replay
   docs\measurements\2026-08-20-spread-sweep-raw-2026-08-20T212616Z.json`
   — it must reproduce look 1's numbers exactly or the anchor is not
   taken (INSTRUMENT FAULT).
4. Inside the band, run the sweep. **Every branch — including VETOED and
   UNTAKEN (band lapses, vendor closed, 401) — writes**
   `docs/measurements/2026-08-21-spread-total-edge-second-look-result.md`.
5. Session timers cap at 1h and die with the session; if no session is
   alive in the band, the look goes UNTAKEN and that too is written up.

**TWO QUESTIONS FOR JOE — ANSWERED 2026-08-21 (~03:45Z), verbatim:**

1. How many open Kalshi positions right now? — **"1"**
2. Are you still placing bets? — **"here and there. not much. just some
   fun parlays."**

So the drying-up branch did NOT fire: winners will still trickle in,
occasionally, mostly KXMVE combos (multi-leg, so outside the stopped
study's scope anyway). This changes nothing already decided — the H4
series stays closed on its own ground (BLOCKED ON INSTRUMENT), the
recorder keeps running because it costs nothing — but a future partner
triage should know the account is quiet-but-alive, not dead.

**Still open, in order:** the `/api/ledger` `commence_ms` defect (partner
ranked it last, "droppable without guilt"; the 3-hour-offset trap is
documented in the 2026-08-20 entry below), and the footer's 5-and-5
parity note (the next screen the nav sheds must answer the delete-commit
question, not land in the footer by default —
`tests/test_every_screen_is_reachable.py` docstring).

---

## 2026-08-21 ~02:00Z — h4-balance-spans ships with its guards red, and both deploys landed

State: tests **3,745 passed / 10 xfailed** (+6 new guards, +2 parametrized
whitelist tests), ruff clean. Pushed `349dca0`; live deploy dispatched (run
32438057600 — the dispatch went through in auto mode this time, first try).

**Open item 1 (the waiting deploy) closed itself before this session acted:**
live was already on `aee4b5a` at 01:47Z, so Joe ran the dispatch. The only
commit live then lacked was `30f1c2e`, docs-only.

**Open item 2 is DONE: `h4-balance-spans` shipped (`349dca0`).** Amendment 1
A12.3's instrument: sections A–D as `h4-settlement-balance` but filtered only
by each table's own clock ≥ study start — no ±900s `EXISTS` window, because
the span design has no window — plus section E, the **whole**
`venue_settlements` table (P_j sums every settlement inside a span,
pre-study included; a study filter there would silently zero prediction
terms). No join, no delta, same discipline. Six window-mutation guards in
`TestH4SpansAreUnwindowedAndUnjoined`, **each verified red**: `>=`→`>`,
study filter dropped, `EXISTS` window re-added to balance or fills, poll
endpoint filter dropped, E gaining a study filter. File restored
byte-identical after each mutation. **A12.4's fallback cap on Look 2 is
discharged.**

**What Look 2 still needs before the 2026-09-03 pull, and it is the next
H4 work:** the analyzer change (A9 seven-branch aggregate tree, A10 E7 +
positive-control gate, A11 early-credit scan, A12 span pairing/residuals)
committed **before** the data exists, as Look 1's was (`4dbd3e2`). Nothing
about it is blocked; the registration specifies it.

**Still open, unchanged:** the `/api/ledger` `commence_ms` defect (item 3
below, low urgency, 3-hour-offset trap documented), and the terminal
spread/total look at 22:40Z tonight (armed; Joe holds the veto).

---

## 2026-08-21 ~00:20Z — H4 Look 1 is taken and moves nothing, tomorrow's terminal spread look is armed, and one deploy waits on Joe

State at close: tests **3,737 passed / 10 xfailed**, ruff clean, tsc clean,
CI green on `883c884`+; live on `1539f76` — **one deploy behind, see the
first open item**. The partner convened at session start and set the list;
all six items are done or armed.

**H4 Look 1 is TAKEN and recorded** —
`docs/measurements/2026-08-20-h4-settlement-fee-result.md` (`883c884`).
Chain, in order: registration `4e0a025` (23:13Z), analyzer pre-committed
`4dbd3e2` (23:29Z), pull 23:44:23Z, two measurement-skeptic audits (first
draft FAILED on six defects, second on one — the record carries the
corrections). Verdict per kind: single-kind UNDERPOWERED (1 cluster),
combo-kind **S1 UNTESTABLE (W = 0)**. **H4 stays untested, ADR 0027
unchanged, no U2 figure is a bound** — the pull's own positive control (a
$5.00 predicted credit, observed $0.00) shows the balance channel did not
respond inside ±900s, which is E6's structural blindness: a flat balance
passes "stopped moving" whether the credit settled or never came.
**Amendment 1 (`9bc9dad`) now governs Looks 2–3**: total seven-branch
aggregate tree (A9), E7 + a positive-control gate (A10), the early-credit
scan (A11), span-based windows replacing ±900s (A12, with a registered
fallback: if the `h4-balance-spans` query has not shipped by 2026-09-03,
Look 2 runs the old design **capped at UNDECIDABLE-COVERAGE on winning
clusters**), and the consequence of each §6.1 answer (A13 — no answer
changes any verdict). The raw pull is operator data: NOT committed, held at
`data/captures/h4_look1_pull_2026-08-20T234423Z.json`, SHA-256 in the
result file. **One tension flagged for Joe in the result file:** the
cluster table carries derived position facts (tickers, counts, win/loss);
if he rules even derived aggregates out, the table moves private.

**The terminal spread/total look is armed for 2026-08-21 22:40:00Z** (band
22:35–22:45Z, 4 credits, **Joe holds a veto until the anchor**).
Registration `5f890b5` + Amendment 1 `5438d9b`: the replay gate first
FAILED by its letter (row counts 3/4 vs 11/12) because its premise
conflated matched with sharp-anchored games; the pre-registrar ruled the
premise wrong and the instrument right — all five edge values, sharp
counts, games and verdicts reproduce exactly, all 16 dropped rows non-sharp
— and restated the gate stricter. The instrument
(`scripts/measure_spread_edge.py`) carries the three permitted edits:
per-game commence window [taken_at+15m, +12h] with counters, 08-21
filenames, the new registration name. Floors unchanged (8 sharp rows / 3
games per arm); NO pooling with look 1; totals arm registered as
more-likely-than-not UNDERPOWERED again. Every branch — including VETOED
and UNTAKEN — writes
`docs/measurements/2026-08-21-spread-total-edge-second-look-result.md`.

**§6.1 QUESTION PENDING FOR JOE (H4):** did you deposit, withdraw, or
transfer money in/out of Kalshi around **2026-08-18 14:51–14:56 UTC
(~7:51–7:56 AM PT Tue)**, or anywhere on 08-18/08-19? Answer goes into the
result file dated; per A13 no answer changes any verdict, so no urgency.

**Open items, in order:**

1. **Live is one deploy behind.** `6cef368` makes the phone's estimate page
   tell the truth about Amendment 2 (study stopped by owner; it currently
   renders "$X of $100" as if live). My live dispatch was blocked by the
   permission classifier (tried once, per rule). Joe: GitHub app → Actions
   → Deploy → Run workflow → instance `live`, type `kalshi-cockpit`. Or a
   future session tries the dispatch once again.
2. **`h4-balance-spans` whitelisted query** (A12) — ship before 2026-09-03
   or Look 2 self-caps. Code-change-sized; the registration specifies it.
3. **The `/api/ledger` `commence_ms` defect** (below, 2026-08-20 entry) —
   unchanged, low urgency, 3-hour-offset trap documented.
4. **Analyzer E1–E6 had zero test coverage at look time** — fixed same day
   (`tests/test_analyze_h4_look.py`, 15 tests, two guards mutation-red),
   noted here because the first result draft *claimed* coverage that did
   not exist and the skeptic caught it. Pattern already in lessons.md
   (git-state claims; this is the test-state twin).

Also this session: the probe key-leak fix + corrected lesson (`450557a`),
the secret-scan false positive on the test's own fake key (`5a047b8`,
nothing real, nothing rotated), four findings recorded (`8358c9b`: ADR 0058
observation note, ADR 0054 5GB-ceiling amendment + fly.live.toml correction,
ledger defect filed), housekeeping (`1202d6e`: two discharged bullets
struck, v16 watch killed as unreachable, stored-number lesson written).

---

## 2026-08-20 ~21:35Z — the spread test is TAKEN: UNDERPOWERED both arms, and the partner's list is the open work

**The registered spread/total test ran at 21:26:16Z**, inside the window, 70
min before first pitch, 4 credits.
`docs/measurements/2026-08-20-spread-total-edge-result.md` + raw/rows
artifacts beside it. **Verdict per the registered floor: UNDERPOWERED on
both arms** (3 sharp-anchored spread rows, 2 totals, against a floor of 8) —
no pass, no fail, the ADR 0038 quadrant row unchanged. All 5 sharp rows were
negative at the charged fee; that is a description under an UNDERPOWERED
verdict, not a finding, and the result doc says so. A second look on a
fuller slate (≥5 games, ~1.7 sharp rows/game observed) is a NEW
authorization, not a continuation — the convening bought one sweep.

**Protocol notes worth keeping:** the first attempt 401'd on a stale local
`ODDS_API_KEY` (no spend); Joe fixed `.env` and the sweep ran five minutes
later. The 401 traceback printed the dead key into the transcript —
`raise_for_status` embeds the URL — and the instrument now fails with the
status alone (`095c1e9`, lessons.md has the pattern; other capture scripts
still share it and are owed a sweep). The new key sits on a 20K/month plan
per the vendor counter (1336 used), which changes the credit arithmetic
whenever a bigger look is authorized.

**ADR 0058 landed (partner-approved, `e6ba046`):** the per-series fee
(`fee_multiplier` 0.5 MLB) corrects **settled PnL only**
(`settlement.py:244`). Guards stay on 0.070 — a cost correction cannot
create an edge. `fills.fee_predicted` is excluded because
`_fee_model_verified` (`gate.py:738-748`) reads it and correcting it would
decide ADR 0043's open hand-fills question permissively as a side effect;
`recommendations.fee_predicted` is excluded because engine.py computes it
and the gate's edge from one EV object. **Not yet implemented** — the
implementing commit must add a fee-regime marker to `settlements` (or
append its SHA to the ADR as the basis boundary) and the ADR 0058 tripwire
test.

**The partner's execution list is DONE, all four items** (~21:45Z):
(1) ADR 0058 implemented in `3b572c5` — migration **v16** adds
`settlements.fee_model_used` (NULL = pre-v16 flat regime), the settlement
pass reads `/series/{ticker}` live and tags every row
(`series_mult_0.5:override_unchecked` / `flat_0.070:series_unread`), fees
take keyword-only `fee_multiplier` refusing outside (0,1], both tripwire
halves armed and mutation-red; suite 3,718 passed. **NOT yet deployed —
deploy after the 22:21Z window closes, before WNBA 22:45Z if possible.**
*(Done 22:26Z: live is on `1539f76`, healthy, v16 ran at boot. The first
`h4-settlement-balance` pull works on live: 13 post-study settlements, a
flat balance beside the 08-18/19 cluster then $8.31 on 08-20, ZERO fills
inside any window -- no fill confound -- and every balance poll ok=1. The
H4 subtraction itself is NOT taken: it needs a pre-registration first,
and the pre-registrar owns that. ~~The next session should also watch the
first settlement row written under v16 for its `fee_model_used` tag --
that is the implementation's one live observable.~~ **Watch KILLED by the
partner 2026-08-20: the `settlements` table is fed from `orders`, and no
order has ever been placed (`ORDERS_ARE_DRY_RUNS = True`), so the row this
watch waits for is unreachable — it would idle forever.**)*
(2) ADR 0027 carries the dated denominator correction (`e3986fb`).
(3) `h4-settlement-balance` shipped (`a02e8d2`), four sections, no join,
three guards mutation-red — run it after the deploy for the H4 read and
the ADR 0027 re-derivation. (4) `orders()` logged as the fifth zero-caller
instance (memory + ADR 0027 correction, grep-verified). Killed by the
partner, do not revive: per-series fee on any guard path, stale-book devig
exclusion, generic UX polish, anything gated on H4 or beta.

**Joe decided: the calibration study is STOPPED** (~22:05Z, "just scrap
it. I am a newbie bettor."). Amendment 2 on the registration records the
terminal state — STOPPED WITHOUT RESULT, nothing scored, machinery kept
(`ed9dd03`). Follow-up for a future partner triage, not urgent: whether
the phone UI's estimate form should come out now that nothing consumes
it — a form feeding a stopped study is quiet misdirection.

Also open, unchanged: the two `parse_portfolio_value_tenths` defect notes
(portfolio_poll.py:252-266) — the partner re-examined them 2026-08-20 and
ruled them NOT H4 blockers — and the `fee_multiplier_override` field no
backend code reads (ADR 0058 hole 2; observation note appended to the ADR:
absent from 24/24 events in the one committed sweep).

New open item, found 2026-08-20 (code-change-sized, no ADR; low urgency —
no frontend consumer reads it — but it sits on the registered evidence
route): **every `/api/ledger` row carries `commence_ms: null`.** The route
(`backend/api/routes.py:1260`, SQL ~1404-1412) joins only `fair_prices`,
never `kalshi_events`, yet `_serialise` (`routes.py:3563`) emits the key
anyway — the exact null-pretending-the-join-was-attempted anti-pattern the
same function's `methods` block was built to avoid. A consumer cannot
distinguish "never joined" from "event unknown", and pre/post-commence
bucketing (the axis behind the clv-coverage denominator error) silently
returns nothing. **Trap for the fixer:** `kalshi_events.commence_ms` stores
the RAW `occurrence_datetime`, which runs exactly 3 hours late (ADR 0006;
the −3h correction lives in `scripts/inspect_live_db.py:1141-1148`) —
adding the join without deciding the offset ships a second defect.

---

## 2026-08-20 ~19:45Z — the dropouts are diagnosed, the zero is verified, and the spread test is armed for 21:21Z

State when this was written: tests 3,675 passed / 10 xfailed, tsc clean, live
on `faa46b9` (deployed ~19:20Z via the dispatch, which went through in auto
mode this time). The 21:21Z–22:21Z MLB window had not yet opened; the session
timer is armed to fire `measure_spread_edge.py` at ~21:26Z.

**The top open item is closed: both mid-window cadence dropouts are one
mechanism, and nothing is broken.**
`docs/measurements/2026-08-20-cadence-dropouts-are-the-freshness-floor.md`,
with two committed retrospective pulls beside it. Short version: a new book in
the feed, `everygame`, sat on all 9 MLB fixtures with a `last_update` stamp
~13 minutes behind each sweep, so every fixture's oldest-book age crossed the
900s limit ~2 minutes after the sweep, `is_open` correctly flipped False, and
the cadence correctly took ADR 0057's bounded sleep to the next refresh.
Dropout 2's "468s matches nothing cleanly" matched to 3 seconds once the
bound was computed from the actual 16:16:37.974 sweep instead of the nominal
minute. Two corrections recorded: the flag was NOT stale (the handoff's
hypothesis is refuted — `interval_s()` runs after the assignment), and the
in-pass "window is open" lines are `decide_sweeps`' *slot* view, a different
quantity sharing a word with the freshness flag. **No code change was made
and none should be made without an ADR**: excluding stale books from the
consensus alters the devig population (rule 2), and the alternative —
accepting that the effective window is `900s − laggard_lag` — costs only
passes that would (on the likely, unverified branch) have confirmed
suppressed rows. The sliver closed the same evening: `book-rows`
(`481d772`, deployed) shows everygame two-sided on all 9 fixtures in both
sweeps, so it contributed to the runner's consensus, `odds_age_ms` read
>900s alongside the window flag, and **the sleeps cost zero live coverage**
— every row was suppressed `stale_odds` throughout. §4 of the doc has the
rows.

**CI was red from ~14:30Z to ~20:00Z and the cause predates this session.**
`tests/test_series_fee_multiplier.py` (convening item 9) read the raw fills
capture under a docstring claiming it was "tracked in git"; it never was
(`data/` is gitignored, the force-add never happened), so the suite passed
only on Joe's machine and failed in CI on every push since it landed. Fixed
in `9eb699f`: `scripts/sanitize_fills_capture.py` derives a committed
fixture carrying exactly the six consumed fields with pseudonymous
`order_id`s — the raw capture's account-linked identifiers (order/trade/
fill ids, subaccount_number) stay out of the public repo, and every
retained value was already public row-by-row in the 2026-08-14 attribution
doc. **Superseded ~21:05Z by Joe's ruling: operator account data never enters
the repo, sanitized or otherwise — anticipate operators other than the
author.** The fixture and sanitizer are removed (`fc88a31`); the fills
prediction now runs only where the private capture exists and skips loudly
elsewhere (verified both ways: 3 passed/4 skipped without, 7 passed with).
Open sliver, Joe's call if he ever wants it: the sanitized fixture lives on
in public git history (9eb699f..2aebfaf), and the same values sit in the
committed 2026-08-14 attribution doc — a history rewrite is pointless
without redacting those docs too, so nothing was rewritten.

**The suspicious zero is verified benign, row by row.** New whitelisted
`estimate-match-status` query, run against live: all 35 positions are
`out_of_scope` and correctly so — 12 combos (multi-leg), 23 singles of which
22 pre-date the study start and the one post-study single is
`KXEARNINGSMENTIONKLAR` (not sports). `position_unlogged = 0` is real: no
sports single-leg venue position exists inside the study window at all. The
one `bet_estimates` row has `match_status` NULL, which is the designed
"pending" state (24h window open or result not yet known), not a fault.

**The ~585 MB question has its first observation, and it is a level, not a
leak.** `docs/measurements/2026-08-20-the-585mb-is-a-level-not-a-leak.md`,
raw samples committed. New read-only `/proc` reader
(`scripts/inspect_live_proc.py`, `a41f20e`, deployed) sampled the loop's RSS
every 45s across three full passes on the freshly booted box: the first full
pass builds ~583 MiB within a minute of boot, the level is dead flat between
passes (17 min), and passes 2 and 3 moved it +61 then −55 MiB — a breathing
band, no monotonic growth. Consistent with the `raw_events` materialisation
suspect but does not name it (RSS is a size, not an inventory). Not urgent
at 2 GB; the number to carry is ~644 MiB as the loop's per-pass ceiling.
CI is green again as of `a41f20e`.

**Tooling shipped for both** (`faa46b9`): `window-freshness --at <ISO|ms>`
(fixture ages per the production measure, then per-book stamps, stalest
first — the retrospective instrument for any future "why did the window
close" question) and `estimate-match-status` (the §7.5 coverage cells).
Four guards mutation-verified red. The mutation-testing byte-restore gotcha
bit again — `write_text` on Windows rewrote every line ending; restored from
the byte copy, which is why the backup rule exists.

---

## 2026-08-20 ~17:00Z — the gate is measured, the product has a plan, and a slice is built but NOT deployed

**The window-gate fix passed its measurement. All four registered observations,
plus the 12-hour stability watch, separately.**
`docs/measurements/2026-08-20-window-gate-observations-result.md`; the durable
evidence is the committed sweep-log pull beside it. Headlines: first pass
**+6.9s** after the 15:26Z open (pre-fix worst case 900s); 3 in-window full
passes all `quotes_pruned: 0` against a backlog proven live by the **8,148-row
prune 45 seconds after the close**; 0 early wakes all day; 0 restarts since the
03:54Z deploy.

**The top open item is new: two mid-window cadence dropouts, same signature.**
15:28:50→15:34:54 (370s) and 16:18:49→16:26:34 (468s) — healthy quote pass,
total log silence, healthy quote pass, pass numbers consecutive, every in-pass
decision reading `window is open`. The first dropout's arithmetic lands exactly
on the bounded-sleep branch (369.7 × 1.15 = the 15:36:00 refresh), which only
runs when `tempo.window_open` is False — **the cadence still reads the flag
assigned at the END of the previous pass**, the same staleness family fix 1
cured at the prune. Cost: ~14 min of a 60-min window. Unexplained; do not
force-fit the second dropout (468s matches nothing cleanly). Start at
`scripts/run_loop.py`'s end-of-pass `tempo.window_open = window.is_open`
assignment and what it evaluates against.

**The fleet convened (Joe called it) and the plan is recorded:**
`docs/reviews/2026-08-20-fleet-convening.md`. Ten items, blast-radius first.
Items 1–3 are BUILT, tested, and green locally — **not deployed**:

- **Item 1** — `estimate_match` no longer stamps "he did not bet" on evidence
  of nothing. Amendment 2 (A10–A12) is in the registration *before* the code;
  schema **v14** adds `match_status_ms`; the absence proof is
  window-closed ∧ result-known ∧ settlements-poll-postdates-knowing;
  `absence_pending` rows stay matchable; the A12 repair pass is **self-running
  and self-extinguishing** inside `run_match_pass` (pre-amendment stamps are
  `unmatched_no_position` + NULL ms). Three guards mutation-verified red.
  **After deploying, read the `A12 repair pass:` log line and reconcile its
  counts** — that is the repair's one observable.
- **Item 2** — `/gate` now says its caps cannot see hand bets (they are
  structural: `settlements.order_id` NOT NULL → orders only).
- **Item 3** — `/` now lands on the **Slate** (re-export, so the two routes
  cannot drift); the Board moved to `/board`; nav reads **Games / Picks /
  Log / Ledger**; `/slate` still served, linked from the Footer. Five python
  test files followed the Board to its new path.

Also this session: migration-undo order in `tests/test_store.py` corrected to
descending (it was right only while no later migration touched a rebuilt
table), and `migrate()` skips a column-add on a mid-migration-missing table
(v11 drops `bet_estimates` for schema.sql to rebuild in the same boot).

**Superseded the same evening — the deploys happened and the plan is nearly
done.** Live is on `99e10c3` (four deploys today: 03:54Z the gate fix, then
items 1–3, then 4–6+10, then 7), migrations v13→v14→v15 ran clean, and the
A12 repair found **zero falsely-stamped rows** — the bug was fixed before it
bit the live data. Items **1–7, 9, 10 of the convening plan are BUILT AND
DEPLOYED**; item 8 (the registered spread/total test,
`docs/measurements/2026-08-20-preregistration-spread-total-edge.md`) has its
instrument shaken down free (`scripts/measure_spread_edge.py`, `--replay`
mode) and fires inside the 21:21Z window.

**The finding of the day is item 9:** Kalshi's public `/series` metadata
carries `fee_multiplier` — 0.5 on both MLB series, 1 on ATP/WNBA — captured
as `tests/fixtures/series_fee_fields.json` and verified by predicting **all
11 attributed fills to $0.0001** (`tests/test_series_fee_multiplier.py`).
That is the durable source ADR 0028 said was missing; moving
`TAKER_COEFFICIENT` or making the fee model read per-series is now an
ADR-sized decision with evidence, not a guess.

**One suspicious zero to verify next session:** the first `classify_positions`
pass stamped all 35 venue positions `out_of_scope`, 0 `position_unlogged`.
The benign explanation checks out locally — every post-study-start fill in
the committed capture is a KXMVE combo (multi-leg → out of §2's population)
— but the live table's later settlements were not directly inspected.
Add a whitelisted `inspect_live_db.py` query for `estimate_match_status`
at the next natural deploy and read the composition; a zero in the
denominator's most interesting cell is checked, never believed.

Also still open, unchanged: the two mid-window cadence dropouts (top item,
above), the ~585 MB holder, `unmatched_events` growth. Nothing below this
line is newer than 2026-08-20 03:00Z.

---

**THE JOB IS DONE AND UNVERIFIED. Your job is the verification.**
*(Superseded 17:00Z — the verification above is taken. Kept for the
correction it carries about the second prune route.)* The window
gate was fixed in two commits on 2026-08-20 (~03:30-04:00Z) and deployed to live
before the betting window opened. **ADR 0057.** Nothing about it has been seen
running.

- `6b0b7ee` — the prune asks whether a window is open **at the prune**.
- `a1d0242` — a closed-window sleep is **bounded by the next window-open time**.

**The correction worth carrying forward:** the handoff described fault 1 as a
stale flag, which was the measured incident and was real. Reading the function
showed a **second** route it had not named — `run_once` fires the odds sweep and
*then* prunes, and the sweep is what opens the window, so a full pass that opens
a window prunes inside the first ~40-94s of it every time. A fix that read the
window at the top of the pass would have shipped green and left the likely
*dominant* case running. The gate is now read at the use, not at the top.

**READ THE REGISTRATION BEFORE LOOKING AT ANY LOG.**
`docs/measurements/2026-08-20-window-gate-plan.md`, written before the code
changed. Four observations are registered against the `baseball_mlb`
15:26Z-16:26Z window; do not choose new ones after seeing the output.

    1. no `quotes_pruned` > 0 on any pass stamped 15:26Z-16:26Z   (falsifies fix 1)
    2. first pass after 15:26Z within ~17s of it, not up to 900s  (falsifies fix 2)
    3. `window_open` latches true within one pass of 15:26Z
    4. passes stay ~900s apart BEFORE 15:26Z, except 2-4 in the last ~15 min

**Observation 4 is the one that catches this fix going wrong**, and it is the
one that will look like a bug if you have not read the registration. Two to four
extra quote passes in the quarter-hour before a window are *designed*: the sleep
bound recomputes and converges. More than that, or early wakes with no window
coming, means the "already due" spin guard has failed and it is burning Kalshi
requests — see ADR 0057.

**The null result to watch for.** If no window opens at 15:26Z at all — empty
slate, or the odds budget is spent — then observations 1-3 have no denominator
and this is **untested, not confirmed**. Check `next_sweep_ms` and
`sweeps_remaining_today` on `/api/health` before reading a quiet window as a
pass. `tempo.next_wake_ms` is now published in the loop's exit-state line and in
`as_dict`, which is how an early wake is told apart from a random one.

**The 12-hour stability watch rides on the same deploy and is a SEPARATE
observation.** It must not be reported as evidence for either fix.

**CI was red and is green again, and it was never the window gate.** An email
alert at ~04:15Z flagged `Tests + warehouse` failing. The identical two failures
were already on `0d18825` and `82b47c6`, both pre-session, so the gate commits
did not cause it. Fixed in `82cd2aa`; run 32331675208 is green on all three
jobs. **Live was not redeployed** — CI runs on push, Deploy is dispatch-only, so
the box has been on `5656133` and untouched since 03:54Z.

**The finding underneath it is worth more than the fix, and it touches config
rather than tests.** `credits_per_sweep_per_sport` is
`len(markets) * len(regions)`, read from the environment via `load_dotenv()`, so
the tests were measuring whichever `.env` the machine held. The values they
passed under **run on no instance**: `flyctl secrets list` shows `ODDS_API_KEY`
alone and `fly.toml` sets neither variable, so **live takes the `h2h` default and
a sweep costs 2, not 6**. CI was accidentally right. `conftest.py` now pins both
variables to the `.env.example` contract.

**The `.env` divergence is reconciled.** Joe's local `.env` carried
`ODDS_MARKETS=h2h,spreads,totals` against `.env.example`'s `h2h`; he chose to
match the contract, and it was changed on 2026-08-20. Laptop, CI and live now
all compute a sweep at **2 credits**. Nothing was committed — `.env` is
gitignored, which is exactly why the drift was invisible for the life of the
project. `conftest.py` pins both variables regardless, so tests do not depend on
it either way.

**Live sets neither variable**, so its values are the *defaults*: `flyctl secrets
list` shows `ODDS_API_KEY` alone. Absence is the config, and that is the part
that is easy to misread as "unset means unused".

Everything else below is open and none of it is urgent.

### Live state at 03:00Z 2026-08-20, verified not inherited

`8efc706`, 2 GB, healthy. Both instances current, nothing unpushed.

```
quote passes     3.0-3.2s        MemAvailable   951 MB
full passes      33-114s         page cache     1.0 GB
IO pressure      avg60 0.00      disk           1.9G/4.9G, 39%
link slow / OOM  0               unmatched_items 494 rows
```

**Two numbers that look like faults and are not.** Meet them before you
investigate them:

- **`recorder.age_ms` of 637,514.** The window was closed, so the loop is on its
  900s slow cadence and runs *no quote passes at all*; age climbs toward 900s
  and resets. Verified against the log — last pass 02:50:05, read at 03:00:28.
  **Check whether a window is open before reading a high age as a fault.** Third
  session to meet this.
- **`MemFree` of 69 MB** (23:19Z reading). Linux spends spare RAM on page cache.
  **Read `MemAvailable`, never `MemFree`** — the naive read says "69 MB left" and
  reopens a closed investigation.

**ADR 0055 is correct as well as fast, checked 23:19Z.**
`dropped_no_kalshi_quote` is **0** — absent from the pass line and not in
`runner.py`'s `ALWAYS_REPORT`, so absent means zero, read in the code rather than
assumed. `suppressed` was 8 beside 20 recommendations on a sweep pass, so the
pipeline decides rather than sleeps. **The live Board itself was NOT read** —
`/api/slate` is 401 and Chrome is still blocked on the live host.

**A CORRECTION LANDED AT 22:10Z AND IT IS THE MOST IMPORTANT THING TO READ.**
`2026-08-19-the-prune-loses-to-the-writer.md` claimed the prune *"cannot win at
any schedule"*, ceiling 3.84M rows/day. **That was the memory starvation
measured a second way and written up as an independent finding.** The 40,000-row
prune was not a config limit; `budget_s` buys as many batches as fit, and the
20s batch cost was the symptom. With memory the same prune clears **440,000** in
one pass and the table shrinks **11.2M rows/day**. The file is marked superseded
in part; ADR 0055 stands on its *second* premise (84.5% of writes carried no
information) and its first must not be cited onward.

**The pattern, which is the actual lesson: every number taken from a degraded
system describes the degradation.** Three numbers were taken off a box minutes
from an OOM kill and only one was suspected of being a symptom.

**Still open, in the order they are worth doing.**

- ~~**`unmatched_events` is the next table with this shape.**~~ **DISCHARGED
  by ADR 0056 — the table was drained and dropped, verified absent from live
  `sqlite_master`/`dbstat` on 2026-08-20.** This bullet outlived its fix and
  cost a recon agent to re-eliminate; deleted as work, not tidying.
- ~~**What holds the ~585 MB is still unverified**~~ **MEASURED 2026-08-20:
  it is a level, not a leak** —
  `docs/measurements/2026-08-20-the-585mb-is-a-level-not-a-leak.md`. Killed
  by the partner as a line of work; the number to carry is ~644 MiB per-pass
  ceiling on a 2 GB box.
- **The 84.5% dedup is a property of the slate, not of Kalshi.** College
  football and NFL are 57% of today's markets at 98-99% unchanged; today's
  baseball runs 51-74%. As sports come into season the saving falls. Re-measure
  when NFL/NBA start rather than assuming.

**Do not re-derive these; they were eliminated by measurement today.**
`priceable_series` (`kalshi_events` holds 1,590 rows; `leg_series_ms` reads **0**
on live), the WAL (flat at 51.6 MB), and the store leg's `upsert` half
(**38-44ms** against `quotes` at 82-193ms — the split in `0c609de` answered the
question it was built for).

**Deploying works and needs two flags.** `gh workflow run deploy.yml -f
instance=live -f confirm_live=kalshi-cockpit` — the guard rejects the dispatch
without the second. In auto mode the classifier blocks live deploys, `flyctl
machine restart` and `flyctl scale`; Joe switches to manual on request. Say it
once and ask.

Also open, and now measured rather than suspected:

- **ADR 0054's latency half is UNRESOLVED**, by its own registered rule. The
  table lost 28% of its rows and the prune-free store leg did not move
  (before 5997/14030 at 6.9M, after 9164/14345 at 4.9M — n=2 a side). Do not
  write it up as confirmed *or* refuted. The **disk** half stands — the DB
  file is flat at 1546.4 MB — but **that is not evidence the table stopped
  growing**, and it was read that way. ~25% of the file is freelist being
  reused, so the row count can climb behind a flat file size. Size on disk and
  rows in a table answer different questions. **The +6.4M/day this used to
  quote is superseded** — after 2 GB and ADR 0055 the table *shrinks* 11.2M/day
  (written 2.25M, pruned 13.47M). See the CORRECTION at the foot of
  `2026-08-19-the-prune-loses-to-the-writer.md`.

**Health check flapping: the keep-alive fix is sound and live has failed
checks again anyway.** Both are true and the order matters. The fix was two
hops each defaulting to a 5s keep-alive against a 15s check —
`KEEP_ALIVE_TIMEOUT=50000` for Next and `--timeout-keep-alive 75` for uvicorn,
in `docker/entrypoint.sh` — measured at 0 failures of 12 where it had been 5 of
10. `docs/measurements/2026-08-19-health-flap-is-the-proxy-hop.md`.

**The sentence that used to sit here — "no Fly check failure since the 15:30Z
deploy" — stopped being true at 18:36Z**, and it is corrected rather than
deleted because the correction is the useful part. Seven failures fell between
18:36Z and 18:52Z and were followed at 18:59:16Z by an OOM kill. That is the box
dying, not the keep-alive regressing. **Do not re-open the keep-alive fix on
this evidence, and do not re-attribute it to CPU or long passes either** — the
backend answered 50 of 50 probes while IO pressure hit 90%.

The general shape, which is why it is worth the space: **a verified fix stays
verified for the failure it was measured against, and the same symptom can
return for a different reason.** A green measurement is not a standing
guarantee, and "we already fixed that" is how the second cause gets missed.
records the wrong fix that shipped first and why its reasoning read as sound.

Everything else is done and none of it is urgent: ADR 0047's plan is fully
discharged (gloss = ADR 0050, strip = ADR 0051, phone = ADR 0052), and ADR 0038
closed the hunt. `VACUUM` is **not** wanted: 25.2% of the file is freelist and
those pages are what is keeping it flat.

STOP AND ASK JOE: money-touching beyond standing approvals. Pushing and
deploying were both pre-approved on 2026-08-18. **The live deploy is blocked by
the auto-mode classifier** — demo goes through, live does not; Joe switched to
manual mode on request and it then worked. Say it once and ask, do not retry.
`gh workflow run` is NOT blanket-blocked: the heartbeat dispatch went through
where the live `deploy.yml` dispatch did not.

GOTCHAS, each of which bit: Bash heredocs eat backticks/backslashes — long
content via the Write tool, commit messages via `git commit -F <file>`. **Assert
your edit changed something**; a `str.replace` that matches nothing returns the
input silently, and it happened three times this session. **Mixed line endings**
— `frontend/src/lib/*.ts` is LF, `app/*/page.tsx` is CRLF; `docker/entrypoint.sh`
is LF. Anything touching `bet_estimates` goes in `schema.sql`, never a
migration. `git checkout <file>` wipes uncommitted edits — back up with a byte
copy before disabling a guard to verify it (lessons.md, top). Run `date -u`
before acting on any deadline sentence — a deploy took 40 minutes this session
and the window opened during it. `flyctl ssh console -C` works fine but always
exits `Error: The handle is invalid.` on Windows; ignore it, the output above it
is real.

Delete this box when its job is taken — a stale session-start box is a
handoff claiming work that is already done.

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
