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

## 2026-08-17 (latest) — THE INSTRUMENTS NOW DISAGREE WITH THE MACHINE OUT LOUD

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

### Still unverified — the one thing only Joe can check

**Nobody has seen the live `beta` strip rendered.** It is behind the session
cookie and no agent can hold one. `/api/signal` answers 401 on live (correct)
and 200 REFUSED on demo. Unchanged from last session.

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
