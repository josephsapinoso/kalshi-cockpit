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

---

## 2026-08-17 (latest) — JOE'S THREE ITEMS, AND THE LANE THAT WAS BRIEFED WAS THE ONE THAT DID NOT EXIST

**`main` at `679e1b9`, pushed. 3,100 tests pass (+20), 10 xfailed, ruff clean,
`tsc --noEmit` clean — run on `main`, not inherited.** The hunt is still closed
(ADR 0038); nothing here reopens it, and nothing here searches for an edge.

Joe took on all three of his own items. `partner` sequenced them, then reordered
its own list mid-session when a subagent found something bigger than any of
them, then accepted two corrections to claims it had made. Its final answer was
**stop**, again, and it again declined to name a sixth item.

### THE BIGGEST THING WAS NOT ON THE LIST — ADR 0032 IS SOURCED FROM THE WRONG `G`

**There are two 300s in this project and ADR 0032 conflated them.** It turned
scheduled prop buying off, arguing props "cannot move the denominator". That is
true of **the gate's** floor — `gate.clustered_clv` clusters on
`event_links.odds_event_id` (ADR 0029), and a prop ladder inherits its game's
id, so it collapses onto the game.

**The CLV signal test's `G = 300` uses a different, registered key**, and
`backend/analysis/clv_signal.py:109-114` says so in writing, with numbers:
*"The cluster key is `COALESCE(m.event_ticker, r.ticker)` and it is NOT the
gate's key ... the two give 210 and 125 — a 68% difference — so a `G` quoted
without its key is meaningless."* Under it a prop ladder **is** its own cluster,
and the interim look measured the cost: **props supplied 81 of 199 clusters,
40.7% of `G`.**

**THE DECISION STANDS AND TURNING SCHEDULED PROPS BACK ON IS KILLED.** Props
were 260 of ~302 credits a cluster; restoring them buys faster accrual toward a
statistic `CLAUDE.md` forbids any roadmap from depending on. Only the sourcing
was wrong.

**What it costs is a misread that is predictable today.** The retired arm was
the *more negative* one — `prop −0.519` against `moneyline −0.082` — so the
pooled estimate now drifts **toward zero, toward what reads as good news, by
composition rather than evidence.** A future session taking the `G = 300` look
and seeing `beta` improve would be reading the intake, not the world. Written
in all three places that reader passes through: an annotation on the interim
look, a **non-amending** note on the registration (no rule changes), and a
sourcing annotation on ADR 0032.

**Direction only — the magnitude is not computable and the attempt is recorded
so it is not repeated.** Re-weighting the arms reconstructs nothing:
row-weighting gives −0.230, cluster-weighting −0.260, against a published pooled
−0.1412. That is not a defect. The pooled figure is one regression carrying the
`half_spread_tenths` control, not a mixture, so it is not required to lie
between its arms.

### 1. `ODDS_API_KEY` ROTATION — THE BLOCKER WAS NOT REAL. `docs/JOE-odds-key-rotation.md`

The handoff said this needs `flyctl` from a laptop and Joe works from a phone.
`.github/workflows/secrets.yml` genuinely cannot touch this key — its exclusion
is written, reasoned, and **stays untouched** — but `flyctl` is not the only
route. **Fly's secrets are settable from the web dashboard, which is a website.**
No laptop, no ADR, no widening of the workflow.

Sheet states what does **not** verify a rotation: `/api/health` returning 200
proves nothing, because the deployed API process never reads this key
(`routes.py:263` takes `load_without_credentials`; the only live reader is
`config.py:251`, reached only by `run_loop.py` on the live instance). **The
proof is a served `api_credits` row after the restart.**

**Not done and it is Joe's:** generating and installing the key. No session may
handle the value.

### 2. THE TIER — MEASURED, AUDITED, AND THE MEASUREMENT MOSTLY DIED

`docs/measurements/2026-08-17-odds-credit-run-rate.md`. All 111 `api_credits`
rows read off the live box. The first draft published **412 credits/day**;
`measurement-skeptic` killed it and was right on every count.

**The killer: `n = 0` rows exist under the running configuration.** Three
changes landed 2026-08-16, all ancestors of the deployed image, all *after* the
last recorded row — props off the schedule (`83432c1`), `ODDS_MARKETS` three
markets → `h2h` (`d4afa53`, so a sweep goes **6 → 2 credits**), cap 400 → 600
(`4600f87`). Machine environment read back to confirm. The formula predicts an
**8× drop**; that is arithmetic and is **not published as a rate.**

Also: 2026-08-15 spent 390 against a **400 cap that was refusing calls**, so it
reports a ceiling. And the parts do not agree — sweep leg up 5×, prop leg down
28%, the pooled totals matched **by cancellation**, which the draft had cited as
evidence the mean was safe.

**What survives, config-independently: 18,896 ÷ 600 a day means the tier cannot
be exhausted before 2026-09-17**, covering any plausible renewal. **The renewal
date is recorded nowhere in this repo** — it is measurable, not guessable
(`remaining_reported` jumps back to 20,000 on the first call after the cycle
rolls).

**Two flags checked rather than inherited, and both failed.** `credits-day` has
**no** boundary defect — it returns 390 / 416, matching a hand re-bucket
exactly; the calendar-date error was in the draft that bypassed it. And
`fly.live.toml:156`'s **338 is correct**: the sentence says *"one cluster"*, and
338 + 78 = 416 exactly. **No correction is owed on either.**

### 3. THE COST METER — THE LANE AS BRIEFED WAS A NO-OP, AND THE PREMISE WAS MINE

I scoped it from *"every cost figure sits inside `suggested_contracts > 0`, so
rows sized to zero show an edge and no cost."* The guard is real. **The
conclusion is wrong:** `routes.py` builds `surfaced` under the same predicate,
`page.tsx` feeds `LiveBoard` nothing else, and `LiveBoard` is
`OpportunityCard`'s only call site — so the guard is **structurally true on
every card rendered**. Zero-sized rows never become cards; they are `SlateRow`s
already saying *"no edge after fees"* in English.

**Both bettor reviews independently ranked a different thing first, and it is a
real defect.** `LiveBoard` overwrites `suggested_contracts` with
`quote.contracts` and nothing else. `backend/live.py` computes that with the
same `size_position` the order endpoint uses, so it legitimately reaches 0 when
the price moves. The card then lost its cost block, **kept a `reason_text`
reading "Sized at 14."**, and stayed wrapped in `TicketTrigger` — tappable,
opening a ticket for a size the server had already decided to refuse.

Server-side re-validation is intact, so nothing could be bought. **A lying
screen, not a hole in the order path** — and this repo's named failure in the
dangerous direction. Fixed via `frontend/src/lib/liveSizing.ts`, a pure
predicate **executed under `node`** (same shape as `sweepTone.ts`), two
mutations red, both call sites pinned by guards observed red against the
pre-fix components.

**`sharp-bettor` did not defend its own proposal unchanged**, and the reason is
worth keeping: the fee curve is **flat at 1.7–1.8c across every price that
trades**, so a cost column cannot rank anything — which is what made partner's
cut correct. It argues the comparator belongs on the **ticket sheet**, at
commitment, not on a discovery board. **Not built. Verify it is not already
displayed before anyone does.**

### 4. TRACEBACKS WERE NEVER REDACTED

`CredentialRedactingFilter` rewrites `record.msg` and `record.args`. A traceback
is neither — `Formatter.format` renders it *after* every filter has run, and
`odds/client.py` calls `logger.exception` on the one path that has just issued a
request carrying the API key in its query string. Closed **by class** rather
than by enumerating which `httpx` exceptions leak: a
`CredentialRedactingFormatter` on every root handler, plus `exc_text` handling
in the filter. Redaction, not suppression — proved end to end through the real
`configure_logging`.

### 5. `fee_predicted` MEANS THREE THINGS — `tests/test_fee_predicted_is_not_aggregated.py`

Whole-order when sized, per-contract when refused, and the fee for an order
later suppressed. `partner` rejected documenting it: the failure is in the
**analysis** path, and a comment at the write site is not read at the moment the
mistake is made. Guard is green today by design — a tripwire for the day someone
sums it. Exemptions checked: `joint_bound.py` already binds it
`stored_fee_DO_NOT_USE`; `mart_fee_reconciliation` reads the **fills** lake
where the column has one meaning, and that exemption is pinned by its own test.

### 6. THE CREDIT INSPECTOR WAS BLIND TO THE CONFIG IT SPENDS UNDER

`_CREDIT_COLUMNS` did not select `markets` or `regions` — the two fields whose
product **is** the cost. Same shape as last session's `trigger` omission, and it
bit today: reading `cost` to infer the config works and is an *inference*.
Added and deployed **before** the 20:50Z window, so the first observation under
the new configuration is read rather than deduced.

### STILL OPEN, AND THE ORDER MATTERS

1. **Joe rotates `ODDS_API_KEY`** — and **not before tonight's 20:50Z window
   has been read.** `partner`'s call: if a rotation and the first clean
   run-rate observation land together, a refusal has two candidate causes and
   **both readings are lost.** Read the window, then rotate.
2. **Read the first post-cutover credit rows.** `markets`, `regions`, `cost`,
   `remaining_reported`, `used_reported`, `trigger` — the last should be NULL,
   and non-NULL means the manual tap fired for the first time in its life.
   The **2026-08-18T10:00Z** boundary closes the first full day under the new
   configuration.
3. **The tier renewal is Joe's, on the invoice.** He has the run rate he can
   have and the ceiling claim that does not depend on it.

### DROPPED — still a drop list, not a backlog

Everything on the previous list stands: the Board/footer gap, exercising the
manual-refresh path, the ~99 clusters to `G = 300`, anything reopening the hunt,
the sweep banner. **Added: turning scheduled props back on** — ADR 0032 stands
and its annotation says why the sourcing error does not reverse it.

### THE ONE HONEST CANDIDATE IF A NEXT SESSION NEEDS A SUBJECT

`partner`, unprompted, and explicitly **not** work for tonight and **not** a
hunting line: the only stated purpose in `CLAUDE.md` with no execution behind
it is that this become a public portfolio repo. It already *is* public. Whether
the record reads as *"we found out, and here is how"* rather than as an
abandoned trading bot is a real question with a real answer, and it is the kind
of thing nothing fails for skipping. It needs a different reviewer than any on
this session's list, and **whether it is worth a session at all is Joe's call.**

---

## 2026-08-17 — THE MORNING WARNING WAS ARITHMETIC, AND IT IS GONE FROM THE LIVE SCREEN

**`main` at `b0bd2ec`, pushed. 3,080 tests pass (+26), 10 xfailed, ruff clean,
`tsc --noEmit` clean — run on merged `main`, not inherited. Both instances
deployed and both report `git_sha b0bd2ec238dd310f0f2dcf00f9f9925d9e489aa0` from
`/api/health`, which equals HEAD.** The hunt is still closed (ADR 0038); nothing
here reopens it.

One lane, directed by `partner`, which explicitly did **not** walk back last
session's "stop" — its distinction was that this item arrived *measured* rather
than *found*, and refusing measured evidence to protect yesterday's stance is the
flattering-direction failure wearing discipline as a costume.

### The defect, and it was 6 of 6 days

The Board's amber strip — *"the loop is alive and declining: nothing has swept in
18.1h"* — compared `last_sweep_ms` against `budget_day_start_ms`. **Those are
different clocks.** The boundary is credits-accounting (10:00Z, so a West Coast
extra-innings game settles in the right day); a sweep window is kickoff-derived,
opening 75 minutes before a cluster's first pitch. Between them there is no
window in which to spend, so "nothing has swept" is arithmetic there, not an
observation.

Measured on live rows **before** anything was built, gap from the boundary to the
first row satisfying the full served-sweep predicate:

```
2026-08-12  17:00:11Z  7.00h      2026-08-15  16:27:03Z  6.45h
2026-08-13  16:47:55Z  6.80h      2026-08-16  17:06:36Z  7.11h
2026-08-14  17:39:58Z  7.67h      2026-08-17  no sweep at all as of 17:45Z
```

**Two quantities live in this record and must not be conflated.** That table is
the gap to the first *served row*. The predicate keys on gap to *window open*,
which is larger: on 2026-08-17 the first window opened at 20:50Z against a 10:00Z
boundary — **10.83 hours of amber**. My own interim brief "corrected" the
handoff's ~11h guess down to 6.5–7.7h and the correction was wrong, because it
measured the other quantity. The handoff was right.

**The machine already knew.** `odds_sweep_log` was writing *"no sweep: next slot
is baseball_mlb at 20:50Z-21:50Z ... sweeping 75-15 min before first kickoff"*
every ~15 minutes throughout. The scheduler's log was calm and correct while the
screen a human reads was amber.

### VERIFIED on live, seen not asserted

Live Board in Joe's own logged-in Chrome, 2026-08-17 ~18:10Z, in the exact state
that used to be amber:

```
looked 2m ago  ——  gap 19.1h  ——  swept 19.2h ago
No sweep window has opened yet today — the first is at 1:50 PM. The loop
looked 2m ago. Windows open 75 minutes before the first pitch of a cluster,
not when the budget day does, so nothing has swept yet and nothing is owed yet.
SKIPPED · no sweep: next slot is baseball_mlb at 20:50Z-21:50Z ...
```

Rendered **muted grey, not amber** — confirmed on the pixels, not only the copy.
**Every fact is still on screen**; the gap chip still says 19.1h. It stopped
shouting without hiding anything. `first_window_open_ms` on the public
`/api/window` is `2026-08-17T18:52:57Z` against a `budget_day_start_ms` of
10:00:00Z, i.e. the two numbers are demonstrably not the same clock.

### `refused` is in the predicate and it is not optional

The obvious fix — *no window open yet, therefore calm* — is **worse than the
bug**. `slots_for_sport` is unfiltered by budget (its own docstring says so), so
a day whose credits died at 14:00Z still computes a 20:50Z window; the naive
predicate renders that calm over a recorder that is dead until tomorrow. That
trades a false positive for a **false negative on the failure the strip exists to
catch**. A liveness guard may be noisy; it may not be silent. `refused` is live,
not theoretical — two such rows exist.

### The predicate is now executed by a test, not read by one

Every other frontend guard here asserts on **source text**, which passes
unchanged on a predicate that has been exactly inverted — and a wrong verdict is
precisely what this defect was. The verdict moved to
`frontend/src/lib/sweepTone.ts` as a pure function; `tests/test_sweep_tone_predicate.py`
runs it under `node` against real recorded states, including three mutations
observed red. Wiring guards pin that `WindowBanner.tsx` actually calls it, so the
extraction cannot orphan itself.

### One claim of mine was wrong, and the mutation test is what said so

I asserted in `sweepTone.ts` that the `refused` clause **must precede** the
window clause and wrote a mutation to prove the ordering load-bearing. **It
refused to go red.** Both branches return `"warn"`; it is a disjunction, so
swapping them changes nothing. The real requirement is narrower — `refused` must
never be *gated behind* the window test, i.e. no early `return "calm"`. Comment
corrected, mutation rewritten to the shape that actually breaks. Recorded in ADR
0042 because a plausible ordering claim backed by a never-red test is exactly
what a future session preserves while refactoring around it.

### Found in passing: the manual exclusion has never fired

All-time, every `/odds` row with `cost > 0` has a NULL `trigger` — one group,
**n = 111**, 2026-08-07 to 2026-08-16. **Zero manual taps have ever been
recorded.** The exclusion stays (a hand tap proves the spend path, not the
scheduler) but it is test-covered only — this repo's "built but never called"
shape, now written down so it is not rediscovered as a finding. The copy change
explaining it to a reader was authorised and then **dropped**: a sentence about a
button nobody has pressed.

**Quote the predicate verbatim.** It is
`COALESCE(trigger, '') != 'manual'`, not `trigger != 'manual'`. My brief used the
paraphrase; under it, all 111 NULL rows fail and the banner would read "swept
never" for its whole life. The measurements used the real predicate and stand.

### The instrument was blind to its own predicate

`scripts/inspect_live_db.py`'s `_CREDIT_COLUMNS` did not select `trigger` — the
one clause deciding a served sweep. Fixed **first**, and the six-day table above
was re-run with it visible before the design was frozen. Same shape as the
`clv-coverage` failure that cost six days. The blind spot pointed the safe way (a
miscounted tap lengthens the gap), which is why this was a repair and not a
retraction — **say which way a blind spot points, always.**

### Not done, deliberately

`partner` capped this at one lane and closed the banner line permanently on
merge. No restyling, no new tones, no settings knob, no `trigger` backfill, no
second screen.

### THE DIRECTIVE IS STOP, AND IT WAS CHECKED RATHER THAN REMEMBERED

Asked at the end of this session what was next, `partner` answered **stop** —
not "stop for now", not "stop pending". It verified its own list before saying
so, on the grounds that saying *stop* from memory is the same failure as saying
*go* from memory: its one undischarged pre-commitment was the `scout.py` /
Historian quarantine, and that was already closed by ADR 0040 (reinforced by ADR
0022, and stated in `backend/playbook.py`'s module docstring where a session
actually hits it). Five items named across two sessions, five discharged. **It
declined to name a sixth.**

**Explicitly dropped — this is a drop list, not a wish list.** Do not pick these
up as "small wins":

- **The blank gap between the last Board card and the footer.** Cosmetic,
  undiagnosed, on a hard-closed line. *Undiagnosed is not a reason to diagnose
  it.*
- **Exercising the manual-refresh path** to retire its zero-live-firings status.
  It spends credits, on a tier whose renewal is Joe's undecided call. The guard
  is test-covered; that is enough.
- **The ~99 clusters to `G = 300`.** Waiting is not work. **Do not schedule a
  session for it.** When it crosses, the look is a twenty-minute read against a
  pre-registered rule.
- **Anything reopening the hunt.** ADR 0038 requires naming which quadrant row is
  overturned and with what measurement. Nothing here does.

Every remaining open item is Joe's and every one touches money or credentials —
the cost-of-execution meter, the Odds tier renewal, the `ODDS_API_KEY` rotation.
Those are his by design. **A future session must not convert one into a lane to
give itself something to do.**

If more is wanted from this project the honest answer is that it needs a **new
signal**, not more work on this one. `backend/analysis/signal_test.py` is
signal-agnostic and would validate one on the same clock that refuted the last.
That is Joe's decision to fund, not a task to assign.

---

## 2026-08-17 — THE INSTRUMENTS NOW DISAGREE WITH THE MACHINE OUT LOUD

**`main` at `bdcd1fb`, pushed. 3,054 tests pass, 10 xfailed, ruff clean, `tsc
--noEmit` clean — run on merged `main`, not inherited. Both instances deployed
and both now report `git_sha bdcd1fbc2811b54784083fcdd29ea000d8cc77bf` from
`/api/health`.** The hunt is still closed (ADR 0038); nothing here reopens it.

A finishing session, run as one. No feature was added to the betting product.
Three of the project's own *instruments* were broken in the same direction —
**the record said one thing and the machine did another** — and all three are
now guarded by a test that was observed red first.

### Deployed first — `999857f` (the footer)

It was committed and pushed but on neither instance. **Proved by probe before
deploying:** the served HTML had `<nav>` (1 hit, the control, from the same
`layout.tsx`) and `<footer>` (0 hits). After deploy: footer 1, `/rejections`
and `/builder` 5 hits each, on both. This is the diffing technique that item 1
below exists to retire.

### 1. `/api/health` can name the commit it is running — ADR 0039's gap closed

Establishing that `999857f` was absent from both images cost a subagent **32
tool calls** of behavioural HTML diffing. `/api/health` now carries a `build`
object: `git_sha`, `image_ref`, `machine_version`, `machine_id`, `region`.

- **The Fly environment was enumerated on a real machine, not assumed** —
  `fly ssh console -a kalshi-cockpit-demo -C "env | grep ^FLY_"`.
  `FLY_RELEASE_VERSION` **does not exist**, and *no* Fly variable carries a
  commit: `FLY_IMAGE_REF` ends in a deployment ULID and `fly releases --json`
  reports `"Metadata": null` on every release.
- **The build-arg cache cost was never paid.** `fly deploy -e GIT_SHA=…` sets a
  *runtime* machine variable and touches zero Docker layers. It also fails in
  the safe direction: `-e` is not inherited, so a forgotten flag yields `null`,
  never the *previous* deploy's commit reported as this one's.
- Unreadable → `None`, never `"unknown"` — two machines both reporting
  `"unknown"` compare equal, which is the exact wrong answer.

**A defect survived the merge and it is this repo's own named one.** The field
was built, tested, and `.github/workflows/deploy.yml` — the *only* way either
instance is deployed, because flyctl has no mobile client — was left deploying
without the flag. Every deploy would have served `git_sha: null` under a green
suite. Fixed, plus the Verify step now reads the sha back and **fails the
deploy on a mismatch**, so "we deployed X" is falsifiable in one GET.
`tests/test_build_identity.py::TestTheDeployPathActuallySetsIt`, red against
the pre-fix workflow (2 failed), green after.

### 2. The public demo was sizing off a $1,000 bankroll nobody chose — ADR 0041

`fly.demo.toml` set **none** of the risk caps. It fell through to the dataclass
defaults at `backend/config.py:400-405` — **1000 / 100 / 400 / 100**, ten times
looser than live's 100 / 10 / 40 / 10, **on the public URL**, and no test
noticed. A previous session found this, wrote it into the record, and never put
it into the config.

All six are now explicit in both files. **Verified by probe, not by reading the
toml:** the public `/api/gate` now publishes `bankroll_dollars: 100.0`. Live
gained one line (`MAX_ORDER_CONTRACTS`, which it was also inheriting) at the
value it already had — an inheritance removed, not a behaviour changed. **No
live risk value changed.**

- **Matching live was argued, not copied.** A rounder $1,000 photographs
  better and at $100 most demo cards read `Buy 1` — which is exactly the
  argument *for*: `Buy 1` is what the system actually produces, and a portfolio
  piece whose thesis is "the record is the product" cannot open by overstating
  its own size.
- **The bankroll is the fourth cap and the outermost one.** `size_position`
  computes `stake = kelly_used * bankroll` and only *then* trims. Counting three
  is precisely what let `fly.demo.toml` omit it unnoticed.
  `MAX_POSITION_DOLLARS` binds an **opening** order; `MAX_EXPOSURE_DOLLARS`
  binds by **accumulation** at the fifth concurrent market. Both are real, in
  different situations.
- The guard derives its required list from `RiskConfig`'s own fields, so a
  seventh cap fails the suite until both tomls state it — a hand-written list is
  how the first six got to six. A companion test forbids the demo being
  *looser* than live; deliberate divergence downward is still allowed.

### 3. The two files every session is ordered to read could not be opened

`tasks/NEXT.md` was **456,641 bytes**, `tasks/lessons.md` **418,992**. The Read
tool refuses above **262,144**. CLAUDE.md's opening line has instructed every
session to read both, and that has been impossible; sessions coped by reading
the head. ~875KB ≈ **219,000 tokens** — roughly half a session budget before any
work started. **A lessons file nobody can read is indistinguishable from not
having one**: this repo's "built but never called" defect, pointed at its own
memory.

Split into 22 dated shards under `tasks/archive/`. **Nothing was distilled,
reworded or dropped** — the shards reconstruct both originals to an identical
sha256, and independently re-checked here: **179 lesson headings in the archive,
179 in `git show 999857f:tasks/lessons.md`**. `NEXT.md` → 17KB, `lessons.md` →
19KB, both now a pattern index over the archive.
`tests/test_session_files_are_readable.py` observed red on both files first.

Found in passing: `CLAUDE.md` and `AGENTS.md` had **already drifted** about
which files to read, and `AGENTS.md` claimed to be quoting `CLAUDE.md`
"exactly". Both corrected. A reading instruction gets audited for content and
never for feasibility.

### 4. ADR 0038's open pre-commitment is discharged — ADR 0040

0038 is Accepted and committed in writing that *"the quarantined
`backend/agents/` orphans (ADR 0022) are now either wired or deleted"*. It had
not happened.

**The sentence naming the set was wrong, and executing it literally would have
deleted live production code.** `backend/agents/` holds seven files, not two:

| module | status | edge |
|---|---|---|
| `base.py` | **live** | `backend/api/routes.py:82` |
| `review.py` | **live** | `backend/runner.py:70` |
| `budget.py`, `skeptic.py` | **live** | via `review.py` |
| `__init__.py` | **live** | parent package of `base` |
| `scout.py`, `historian.py` | orphan | only a dockerignored script + tests |

Re-grepped independently before merging. `agent_fleet_configured` in
`/api/health` reads `AgentConfig.from_env()` — i.e. the `ANTHROPIC_API_KEY`
env var, `backend/agents/base.py:128` — and never touches the directory; it is
why `base.py` can never be deleted, and is *not* evidence about scout.

**Decision: amend, not delete.** Deletion was tested on a scratch commit and
`test_the_unmetered_callers_are_exactly_the_quarantined_ones` collapses to
`assert unmetered == set()` — vacuous in both directions. Scout and Historian
are the only members that mechanism has ever had, so deleting them turns a real
guard into decoration. Also: *"they spend credits per pass"* is false — nothing
calls them, so they spend zero. Quarantine is **why** the bill is zero.

**Found unlooked-for: the Historian's revival condition already fired and no
test noticed.** It cited ADR 0021 §8 Option F; ADR 0034 took Option F; the
check only verifies `revive_if` is a non-empty string. Both revival conditions
rewritten to conditions that are unfired and still reachable post-0038.

### The pattern this session kept hitting

**Three of the four items were briefed with a sentence that turned out to be
false**, each in the direction of *the record flattering the machine*: lane C's
brief named the wrong set; lane A found `CLAUDE.md`/`AGENTS.md` already drifted;
the build-id feature shipped with its own deploy path not calling it. That is
now **four sessions running.** Open the set before predicating over it.

### VERIFIED — the live `beta` strip renders, and every guard held

**Seen, on live, in Joe's own logged-in Chrome** (browser automation against his
session, 2026-08-17 ~10:15 PDT). This had stood unverified for two sessions
because the strip is behind the session cookie and no agent can hold one. It is
no longer an open claim.

```
SIGNAL TEST   UNRESOLVED   201 of 300 games              measured 5m ago
Not yet resolved — and that is not the same as no signal. ... 99 to go.
smallest resolvable +0.1911   beta -0.1403   se 0.0475
interval [-0.3314, +0.0509]   rows 3,780
by market type, diagnostic only:  moneyline -0.0809 · 120g · 67%
                                  prop      -0.5192 ·  81g · 33%
```

Every constraint the component's docstring names is honoured on the live screen:
`UNRESOLVED` is not rendered as "no signal" and carries the explicit sentence
saying so; `smallest_resolvable_beta` prints **before** the estimate; `beta`
never appears without `se` and the interval; the per-arm split is labelled
*diagnostic only* with each arm's share. And **`201`, not `420`** — it is
reading the live record, not the seeded demo database, which was the specific
failure `REFUSED` was invented to prevent.

**The numbers moved since the handoff, which is the recorder working:** `G`
199 → **201**, `beta_hat` −0.1412 → **−0.1403**, `se` 0.0478 → **0.0475**. The
G = 300 look still arrives on its own and nothing may depend on it.

The footer from `999857f` also renders — **ALSO SERVED · Rejections · Parlay
builder** — confirming the pages `Nav.tsx` called "still served" are now
reachable from the app.

**A note for the next session on where it is.** The strip is **not** at the top
of the page; it sits immediately above the cards (`frontend/src/app/page.tsx:219-228`),
deliberately — as a header it reads as a disclaimer nobody finishes, above the
cards it reads as a caption on them. Anyone told to "check the top of the Board"
will report it missing. It is also fetched with `.catch(() => null)` and
`SignalStrip` returns `null` for a null signal, so a genuine failure and a
mis-aimed look are the same picture from the top of the page.

---

## 2026-08-17 — THE PRODUCT NOW STATES WHAT ITS CONCLUSION IS WORTH

**`main` at `d5bd3fb`+, 2,992 tests pass, 10 xfailed, ruff clean, `tsc
--noEmit` clean — re-verified this session, not inherited. Demo at machine v18,
live still at v55 (the PRE-FIX image).** The hunt is still closed (ADR 0038) and
nothing here reopens it.

### Done — partner directive #1

**`GET /api/signal`, rendered above the cards on Board and Slate.** ADR 0039.

The extraction moved into `backend/analysis/clv_signal.py`; every expression was
lifted, not rewritten. **The reproduction was run before anything was built on
it**, which was the hard constraint: `git show HEAD:scripts/run_signal_test.py`
against the moved version, same dump, `diff` → nothing. `beta_hat -0.1412`,
`se_cluster 0.0478`, `G 199`. Then proved end to end by rebuilding a SQLite
database from the dump and asking the route — it returns the registered look.

- **`scripts/run_signal_test.py` is now a printer** over `build_report`. The
  harness an operator runs and the number the screen serves are one computation,
  not two that agree today.
- **The quarantine was reversed in the open.**
  `test_a_quarantined_module_has_not_been_wired_up_by_the_back_door` went red on
  the first import, which is what it is for. ADR 0039 records why: the
  quarantine's stated reason named the always-valid multiplier as the thing it
  protected, and the multiplier is what makes unlimited re-reading valid. **The
  `G = 300` look now arrives by construction rather than by discipline.**
- **31 new tests, both new guards observed red under a named mutation.** Nothing
  in the suite read `beta` before this. It could have drifted silently, which is
  exactly how `ev.py` was wrong for three days.
- **REFUSED is deliberately not UNRESOLVED**, and demo is why: its seeded
  history has no quotes to join, so a caller reading the cluster count off a
  refused report would publish **`G = 420`** on the public screen — a larger
  number than the live record's 199, off a database with no signal in it.

### Measured — the Odds API spend, and it was not what NEXT.md said

**1,104 credits used, 18,896 remaining**, since the tier was bought 2026-08-09.
Seven days, ~158/day, on pace for **~24% of the 20,000 tier — not 90%.** Source:
`inspect_live_db.py credits-tail` / `credits-month` on the live box, i.e. the
provider's own `x-requests-remaining`.

The 90% figure was `ODDS_DAILY_CREDIT_BUDGET = 600` (`fly.live.toml:185`) × 31.
**A ceiling is not a spend** — see `tasks/lessons.md`; the cap is never
approached (158 against 600). The per-call cost was wrong the same way: config
arithmetic predicts 2 credits, every one of the last 111 `api_credits` rows says
**6**.

**What this does and does not settle.** It settles that the recorder is not
consuming a tier. It does not make ADR 0038's "costs nothing" true — ~24% of a
paid tier is a real bill, and **the renewal is still Joe's decision, on the
invoice.** But it is no longer an argument for stopping the recorder.

### Deployed — both instances, on Joe's explicit go

**live at machine v56, demo redeployed, both verified by probing rather than by
reading a green check.**

| check | live | demo |
|---|---|---|
| `/api/health` | 200 | 200 |
| `/api/signal` | **401** — the route exists, behind the session | 200 |
| parity with `/api/gate`, `/api/board` | identical 401 | — |
| the strip renders on Board **and** Slate | not verifiable from here | yes, in its refusal state |

Live carried the retracted 52.00% / 0.38-point copy and `Buy N` until this
deploy; both are now gone from the money instance.

**One prediction did not come true, and the honest version matters.** The demo
was expected to publish `G = 420` if a caller read the cluster count off a
refused report. On the deployed demo the registered §2 population is **empty —
0 rows** — so it refuses on P1 at 0/0, not at 420/420. The seeded history does
not reach the population at all. The refusal path protects either way, and the
guard earned its place, but "it would have shown 420" was a projection from the
seed code and not a measurement of the deployed database.

**Live will fit rather than refuse.** `clv-coverage` on the box reports 9,437
scored rows carrying CLV across 7 series, so the §2 subset is populated and `G`
is now above the 199 of 2026-08-16. **Nobody has yet seen the live strip
rendered** — it sits behind the session cookie and no agent can hold one. That
is the one unverified thing in this entry.

### Open — Joe's call

- **Rotate `ODDS_API_KEY`.** A subagent read `.env` and the plaintext key landed
  in its transcript on disk. Not the Kalshi key. By this repo's own standing
  rule that counts as compromised.

### Done — directive #2, and its premise was wrong

**The nav audit found a decision, not a defect — and then a real bug inside
it.** Committed, not yet deployed.

Directive #2 read: *"a screen that is served but unreachable is this repo's
named defect in UI form."* `Nav.tsx:8-27` says otherwise, in writing and with
reasons. **Six links is a budget**: a seventh pushes the Gate — the screen that
says whether money can move — off the row at 390px. `/builder` lost its slot
because it prices sportsbook parlays, cannot change a bet on this venue, and
for a beginner can change one in the wrong direction. `/rejections` lost its
slot on 2026-08-15 because Slate is a strict superset of it. Two recorded
trades, not two oversights.

**The bug is one layer in.** That comment says *twice* that the pages are
"still served for anyone who wants it" — and there was **no inbound link
anywhere in the application.** Not the nav, not a footer, not contextually. The
escape hatch it promised was never built, and on a phone "type the URL" is not
a route a real person takes. A served page with no link is unreachable in
practice however true it is that the server answers.

Fixed with a **footer**, not a seventh nav link — the budget argument is right
and the Gate keeps its slot. Each entry carries a one-line blurb, because a
bare link named "Builder" invites a beginner to open a parlay calculator
expecting a Kalshi feature.

**`tests/test_every_screen_is_reachable.py`** now fails if any page with a
`page.tsx` is named in neither link list, if the nav budget stops being six, or
if the footer grows larger than the nav. Observed red by deleting a footer
entry. **The remedy it does not enforce: a page worth neither slot belongs in a
delete commit, and the footer must not become the place decisions go to be
avoided.**

The lesson is the recurring one — `tasks/lessons.md`, *"a collective noun is not
a measurement"*. The directive named a set (`/rejections` and `/builder`) and
predicated a defect over all of it in one breath. Opening the file took a
minute and falsified the predicate while leaving a smaller true finding behind.

### Still undecided, do not build it

`sharp-bettor`'s cost-of-execution meter — re-pointing the Board from "is this
mispriced?" to "is this cheaper on Kalshi or at a book?". Joe's call, unmade.

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
- **The `G = 300` look happens on its own and nothing may depend on it.** The
  recorder keeps running because it costs nothing to leave running; `beta` would
  have to move 8.3 standard errors for the verdict to be anything but NO SIGNAL.
  ADR 0038, and `archive/next-2026-08-16.md`.
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
