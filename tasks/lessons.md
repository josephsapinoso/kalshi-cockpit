# Lessons

Dated, one lesson per entry. Written when something was got wrong, or when a
correction arrived. Reviewed at session start.

Two rules for this file, inherited from the previous project because they are
what made it useful rather than decorative:

- **Write the pattern, not the incident.** "PR #42 broke staging" ages out;
  "unreadable must never resolve to zero" doesn't.
- **A lesson earns its place by preventing a repeat.** If it would not have
  changed what someone did, it is a note, not a lesson.

A third rule, added 2026-08-17 for the reason the first lesson below records:

- **This file is an index plus the newest entries; the lessons themselves live
  in `tasks/archive/lessons-YYYY-MM-DD.md`.** Nothing has been distilled,
  reworded or dropped — the archive reconstructs the pre-split file byte for
  byte. Write new lessons here, at the top, and move them into the dated
  archive file when this one approaches the size budget.
- **The size budget is 262,144 bytes**, enforced by
  `tests/test_session_files_are_readable.py`. It is the point at which the Read
  tool refuses the file outright, which is how "read this at session start"
  became an instruction no session could obey.

---

## 2026-08-17 — A boundary borrowed from another subsystem answers a question it was never about, and the reasoning for borrowing it reads well

The Board's sweep strip warned *"the loop is alive and declining: nothing has
swept in 18.1h"* every morning. Its predicate:

```ts
sweptThisDay = last_sweep_ms >= budget_day_start_ms   // else amber
```

`budget_day_start_ms` is a **credits-accounting** boundary — 10:00Z, so a West
Coast extra-innings game settles into the day it belongs to. A sweep **window**
is **kickoff-derived** — 75 to 15 minutes before the first pitch of a cluster.
Nothing connects them. Between the boundary and the day's first window there is
**no window in which to spend**, so during that interval "nothing has swept" is
not an observation about the loop. It is arithmetic, rendered as a warning.
Measured on live rows: 6 of 6 budget days, 6.5 to 10.8 hours each.

**The component had already argued for the boundary, in writing, and the
argument was good.** Verbatim: *"'Since the budget day opened' is the boundary
rather than an invented number of hours: `budget_day_start_ms` is already on the
payload, the day's whole allowance is two sweeps, and a day with none of them
spent is a fact rather than a threshold somebody chose."* Every clause is true.
The conclusion does not follow. The paragraph is defending against the **wrong
failure mode** — inventing an arbitrary threshold — and in avoiding it reached
for the nearest quantity that was *not* arbitrary, without checking that it was
about the same thing. "Already on the payload" is a fact about plumbing and it
reads as a fact about meaning.

**The tell was available the whole time, in the system's own records.**
`odds_sweep_log` was writing *"no sweep: next slot is baseball_mlb at
20:50Z-21:50Z ... sweeping 75-15 min before first kickoff"* every ~15 minutes
throughout every amber period. The machine knew and said so on a cadence; the
screen the human reads disagreed. **When two instruments over one system
disagree, the interesting one is not the one that is wrong — it is that nobody
had put them side by side.**

**How to apply.**

- **A quantity has a subsystem, and crossing that line needs an argument that
  names both.** Before comparing X to Y, say out loud what each is *for*. Here:
  one is for counting money, the other is for catching a first pitch. Said
  aloud, the mismatch is immediate; left as two `_ms` integers on one payload,
  it is invisible.
- **"It is already on the payload" is not a reason to compare against it.**
  Availability is the weakest possible argument for correctness and it is
  disproportionately persuasive, because the alternative always costs a new
  field.
- **A guard that fires on a schedule is not a guard.** If a warning's on-period
  is predictable from a clock rather than from the system's state, it is
  reporting the clock. Measure the duty cycle against real rows before deciding
  whether a warning is noisy or right.
- **Fixing a false positive is where you introduce the false negative.** The
  natural repair — *no window open yet, therefore calm* — would have rendered a
  budget-exhausted day calm over a dead recorder, because slot planning is
  unfiltered by budget. A liveness guard may be noisy; it may not be silent. Ask
  what binds *after* the constraint you are removing is gone.

Related: [[a-count-that-exactly-equals-a-natural-subpopulation-is-a-bug-in-the-counter]],
[[an-alias-between-two-constants-is-a-bet-that-they-answer-the-same-question]],
[[a-risk-control-can-be-a-threshold-on-the-wrong-quantity-entirely]],
[[a-negative-claim-inherits-its-instruments-where-clause]].

---

## 2026-08-17 — An instrument that does not select the column its predicate turns on reports the absence of what it cannot see

`scripts/inspect_live_db.py` was used to measure how often the sweep banner's
amber state was structurally guaranteed. Its `_CREDIT_COLUMNS` was:

```python
"called_ms, endpoint, sport_key, cost, remaining_reported, used_reported"
```

The predicate under investigation was
`endpoint LIKE '%/odds' AND cost > 0 AND COALESCE(trigger, '') != 'manual'`.
**`trigger` — the only clause in dispute — was the one column not selected.** A
day whose only `/odds` rows were manual taps would have rendered in that output
exactly like a day that swept.

This is the `clv-coverage` failure again, and that one cost six days: it filtered
on `clv_scored_ms IS NOT NULL` while an actionable row is written *before*
commence, so the class under investigation sat outside the denominator, and
"actionable = 0" was repeated across sessions as a measurement when it was a
repetition of one older measurement.

**The direction of the error mattered and should be stated whenever this
happens.** A miscounted manual tap would have made the measured gaps *longer*,
never shorter — so the finding was conservative and survived the re-run. That is
why this was a ten-minute repair rather than a retraction, and knowing which way
an instrument's blind spot points is what tells you which of those two you are
in.

**A second trap, in the paraphrase.** An interim brief restated the predicate as
`trigger != 'manual'`, dropping the `COALESCE`. Scheduled sweeps are stamped
`NULL` deliberately, so under the paraphrase *every one of the 111 rows in the
record* fails the comparison and the banner would read "swept never" for its
entire life. The measurement was run with the real predicate and was unaffected,
but the paraphrase was on its way into a document.

**How to apply.**

- **Before trusting a query about a predicate, check the predicate's columns are
  in the SELECT.** Not in the WHERE — in the output, where a human can see what
  the filter did.
- **Quote a SQL predicate verbatim, never in prose.** `COALESCE(x,'') != 'v'`
  and `x != 'v'` differ on exactly the rows that are usually the majority, and
  the prose form is the one that gets copied forward.
- **Say which way a blind spot points.** "The instrument could not see X"
  is incomplete; "and X would have made the number larger" is what decides
  whether the finding stands.

Related: [[a-negative-claim-inherits-its-instruments-where-clause]],
[[the-census-must-apply-the-same-filter-the-storage-path-applies]],
[[a-count-that-exactly-equals-a-natural-subpopulation-is-a-bug-in-the-counter]],
[[a-ceiling-is-not-a-spend]].

---

## 2026-08-17 — A feature and the one path that invokes it are two deliverables, and only the second one ships

`/api/health` was given a `build` object so a single GET could answer *"which
commit is this machine running?"* — the field was designed against a real Fly
environment enumerated over ssh, validated (`GIT_SHA` refused unless 7–40 hex),
made to fail to `None` rather than `"unknown"`, and covered by tests observed
red under four named mutations. It was, by every check available in the repo,
finished.

`.github/workflows/deploy.yml` was still running `flyctl deploy` with no
`-e GIT_SHA`. That workflow is the **only** way either instance is deployed —
flyctl has no mobile client and the owner works from a phone. Every deploy would
have served `git_sha: null` while a green suite reported the feature present.

**The failure is not that the wiring was forgotten. It is that nothing could
have noticed.** Every test asked *"does `BuildInfo` read the environment
correctly?"* and none asked *"does anything set that environment?"* A unit test
of a config object is a statement about a function; it is silent about whether
the deployed process ever calls it, and the two questions read identically in a
green summary. This is `test_has_callers.py`'s premise applied to configuration
instead of code: **an env var with no writer is the same defect as a module with
no importer**, and only one of the two had a guard.

Two things make this worth writing down rather than just fixing:

- **It landed inside the fix for a verification gap.** The whole point of the
  build id was that "deployed and verified" had been asserted and been wrong
  before. Shipping it in a state where it reports `null` forever would have
  produced a *second* instrument that agrees with the record instead of with the
  machine — the failure it was built to detect, reproduced by its own delivery.
- **The safe direction was available and was taken.** `-e` is not inherited
  between deploys, so a forgotten flag yields `null`, never the *previous*
  deploy's commit presented as this one's. Design the degraded state before you
  need it: `null` says "I don't know", a stale sha says something false
  confidently.

**So: when a feature's value depends on a caller, the caller is part of the
feature, and the guard belongs on the caller.** Concretely — if the deliverable
is only meaningful in production, write the test against the *deployment
artefact* (the workflow file, the toml, the entrypoint), not only against the
function. `tests/test_build_identity.py::TestTheDeployPathActuallySetsIt` and
`tests/test_deployed_risk_caps_are_explicit.py` are both that shape, and the
second one exists because the same failure had already happened once with
`fly.demo.toml` silently inheriting six code defaults. Related:
`[[built-but-never-called]]`, and the `.env.example` lesson below — a file that
cannot disagree with reality cannot be evidence about it, and a test that never
looks at the deploy path is the same thing wearing a green tick.

---

## 2026-08-17 — A document that has outgrown its reader is unread, and it reads as compliance

`CLAUDE.md` opens by telling every session to read `tasks/todo.md` and
`tasks/lessons.md` at session start; `AGENTS.md` repeats it and adds
`tasks/NEXT.md`, claiming to do so "exactly as `CLAUDE.md` says". Measured this
morning, before anything was moved:

```
tasks/NEXT.md      456,641 bytes   8,145 lines
tasks/lessons.md   426,584 bytes   7,592 lines
Read tool ceiling  262,144 bytes
```

Both files were **past the point where the tool returns any content at all** —
not truncated, refused. The instruction had been impossible to obey for some
time, and no session reported that. Sessions coped by opening the head, which
produces exactly the behaviour of a session that read the file, and the two are
indistinguishable from outside.

**The second half of the shape: the instruction and its restatement had already
drifted apart**, and the drift pointed at the larger file. `CLAUDE.md` names two
files; `AGENTS.md` names three and says it is quoting. Neither statement was
checked against the sizes it was demanding, because a reading instruction is the
kind of sentence that is audited for *content* and never for *feasibility*.

**The pattern is this repo's own named defect, one level up.** `tasks/lessons.md`
carries *"code with no caller is not a feature, it is a plan"*, and
`tests/test_has_callers.py` exists to enforce it on `backend/`. A lesson nobody
can open is a lesson with no caller. The file's own second rule — *a lesson
earns its place by preventing a repeat* — had quietly stopped applying to most
of its own contents, because prevention requires being read, and 179 lessons
behind a refused read prevent nothing.

**The mechanism is append-only growth against a budget nobody owned.** Every
session had a local incentive to add and none to prune, and each addition was
individually correct. There is no line number for the defect; it is the sum. At
~875KB the two session-start files were **~219,000 tokens** against a 300–500K
session budget — the memory would have consumed most of the budget it exists to
protect, on the first tool call.

**How to apply.**

- **A document written for a stated reader has a size budget, and the budget is
  the reader's, not the writer's.** Before adding to a file that something is
  instructed to read, check what it costs that reader to read it. `wc -c` is one
  command, and the answer here had been decisive for days.
- **Where the reader is a tool with a hard limit, put a test on the limit — not
  a note in the prose.** A guard fires on the commit that crosses the line; a
  convention written at the top of a file is read by whoever is already reading
  the file, which is the population that does not need it.
- **Split, never distil.** Fitting a history under a limit by summarising it
  trades an unbounded loss — the one lesson that turns out to matter — against a
  bounded inconvenience, an extra file open. The archive keeps every byte and
  the top-level file keeps an index; the recovery cost is one `Read` on a dated
  file, and the index says which one.
- **An index of patterns is not a summary of them.** One line per lesson,
  phrased as the claim, is enough for a reader to know whether to open the
  entry. That is a *routing* artefact, and it is the only compression that does
  not destroy the thing being compressed.

**What this does not establish.** Nothing here says the lessons are good, or
that anyone acted on the ones they could read. It establishes one thing: a
session-start instruction that names a file larger than the reader's limit is
not an instruction, and it will not announce itself.

Related: [[code-with-no-caller-is-not-a-feature-it-is-a-plan]],
[[it-probably-fits-in-one-page-is-a-fact-you-can-just-measure]],
[[a-command-in-a-handoff-has-the-status-of-a-test-never-seen-red]],
[[six-built-never-called-modules-is-a-process-gap]].

---

# The pattern index

Every lesson ever written, newest date first, one line each. The full text of
each is in the linked archive file, unchanged.

### 2026-08-17 — in this file, above

- A boundary borrowed from another subsystem answers a question it was never about, and the reasoning for borrowing it reads well
- An instrument that does not select the column its predicate turns on reports the absence of what it cannot see
- A feature and the one path that invokes it are two deliverables, and only the second one ships
- A document that has outgrown its reader is unread, and it reads as compliance

### 2026-08-17 — [`archive/lessons-2026-08-17.md`](archive/lessons-2026-08-17.md)

- A ceiling is not a spend
- `.env.example` is a contract, not a configuration
- A collective noun is not a measurement
- An exclusion count describes the filter, not the world

### 2026-08-16 — [`archive/lessons-2026-08-16.md`](archive/lessons-2026-08-16.md)

- "X requires Y" is a necessary condition, and meeting it does not elect X
- A stopping rule may only be amended in the file that registered it
- A negative claim inherits its instrument's WHERE clause
- A diagnostic reachable only through the healthy path cannot diagnose the unhealthy one
- Docker builds from the working tree, so a byte-level write bypasses .gitattributes
- An absent environment variable means the default applies, not that the feature is off
- An alias between two constants is a bet that they answer the same question
- Two identifiers that are equal by construction render as a bug
- A defect written down beside a guard is not written down in it
- A probe's request parameters are part of its finding, and they do not travel with the sentence
- A ratio against a control assumes the control is one number
- "Unreadable" and "empty" are different, and the wire decides which one you get
- A new caller that makes an existing call is indistinguishable from the existing caller
- SQLite rewrites your CREATE TABLE text, so a comment above the last column can break the table
- A default is not the behaviour, because the caller may override it — and relaying to Joe is publication
- A count that exactly equals a natural subpopulation is a bug in the counter, not a finding about the data
- Calling a registered precondition "just a diagnostic" is how the precondition gets skipped
- An agreement forced by the writer looks exactly like a clean measurement

### 2026-08-15 — [`archive/lessons-2026-08-15.md`](archive/lessons-2026-08-15.md)

- A guard copied from a neighbouring path inherits its *assumptions*, not its safety
- A cost estimated from an assumed input is not an estimate, it is the assumption restated
- A test's *invented* example can turn out to be real, and it fails on the axis it was never about
- A mutation refuted a code comment, and the comment was the thing that had to change

### 2026-08-14 — [`archive/lessons-2026-08-14.md`](archive/lessons-2026-08-14.md)

- A cleanup that did not run is invisible; the next run then canonises the damage
- The money rule is `Decimal`; an *analysis* that reconciles money in floats invents findings

### 2026-08-13 — [`archive/lessons-2026-08-13.md`](archive/lessons-2026-08-13.md)

- A derived guard covers exactly the class it derives from, and the class it cannot see looks identical from outside

### 2026-08-11 — [`archive/lessons-2026-08-11.md`](archive/lessons-2026-08-11.md)

- Mutation testing belongs in its own worktree, not in the shared one
- Scoping `git add` leaves `git commit` binding, and the symptom is unchanged
- Evidence a decision already cites is not grounds to re-open it
- An instrument whose every branch points one way is uninformative, and that is a reason to re-price it, not to cancel it
- A count written into a handoff cannot include its own commit
- A test that constructs the parameter it is checking cannot detect that no caller constructs it
- A default on a guard input is a decision about what happens when nobody knows, and on a limit it is always the permissive one
- A readout verified on the demo instance can be structurally blind on the live one
- An observability fix that stops at the API boundary has not been made
- A demo that renders healthy beside a live instance that renders empty is an argument machine for the wrong conclusion
- The file-ownership map between parallel lanes is a design artefact, and getting it wrong is the director's error
- A verdict the instrument cannot emit was written into two handoffs as a result
- The exclusion outranks the copy, and it is the copy that gets cited
- A mutation that cannot change behaviour is a green light you awarded yourself
- Two rows that name the same outcome are not a pair, and pairing them halves nothing
- A lower bound rejects correctly; it is the acceptances that are unproven
- Two artefacts that agree on the number you check are how a pin swap goes unnoticed
- A registered decision rule can be logically defective, and pre-registration is exactly what stops you noticing
- The anchor where the error vanishes keeps getting chosen, and it looks like the natural place to measure
- Fixing how a wrong row is drawn leaves the query that chose it
- A "decisions already made" list is a cache with no invalidation
- Deployment cannot be inferred from commit times in this repo
- A repeated row is not an independent observation, and the denominator that flatters a claim is usually the row count

### 2026-08-10 — [`archive/lessons-2026-08-10.md`](archive/lessons-2026-08-10.md)

- "Unblocked" is a scheduling property, not an evidentiary one
- A number quoted from your own project's prose is an assumed number
- Tracing a number to code is only half the check
- A pull can be incomplete while every check on it adds up
- A reachability guard has to run in both directions
- The guard that cannot fire on the input it was built for
- Count guard families, not guards
- The false reassurance in a comment outlives the code it describes
- Six built-never-called modules is a process gap, not a run of bad luck
- CI cost is job count and trigger breadth, not job duration
- A scanner that only reads the current push leaves history unverified
- A borrowed number must overlap the population you spend it on, in *time*
- SQL written into a document is code, and unrun SQL is a guess
- An allowlist cannot report what is missing from it
- A detector's "production" must be the deployment's "production"
- The safety was an accident of the boot script, not a design
- An empty endpoint is not an empty account
- Reachability has two halves, and this project keeps checking one
- A measurement is not new until you have grepped for its own value
- A number produced by calling a function once is not a claim about a loop that calls it ninety-six times
- A permission grant is not the guarantee it is described as
- The cheapest fix for a mutation is a mutation already scheduled
- A control that swaps the data source still shares the estimator
- Read the coverage line, not the slot list
- Consecutive date buckets tile, and overlap is the safe direction
- A command in a handoff has the status of a test never seen red
- A fixed-sample threshold quoted for a design that peeks inflates its own power about threefold
- A measurement with no committed artifact is a rumour, and a handoff can promote it to a verdict in one line
- A subagent's confident negative is the one result you must re-run yourself
- "Routed separately" names no owner, and the wrong sentence stays where people read it
- An amended registration's body is not the registration, and the superseded sentence is the one that reads best
- The power of an instrument is not the power of the question, and the gap is invisible from inside the arithmetic
- The rule about other agents' confident negatives applies to your own, and you will not notice

### 2026-08-09 — [`archive/lessons-2026-08-09.md`](archive/lessons-2026-08-09.md)

- A comment before the last column breaks `DROP COLUMN`
- Three guards, three green disable-checks, three missing tests
- A fixture that omits a new column reports the code refusing
- The population was 962; the logs showed 94, and nobody compared the two
- The counter that decides the project was behind an auth wall
- Sampling the wrong pages proves absence with total conviction
- Run the control before believing the estimator
- Two paths pinned by a test agreed, and were both wrong
- The fourth wrong wire key, and the cheap test that finds all of them
- A frozen counter is not evidence of a stuck mechanism
- A guard written to prove a property the code cannot violate
- The control that cannot reach the confound it was built for
- Two clocks that never overlap, so the test cannot be run
- A risk control can be a threshold on the wrong quantity entirely
- A measurement can be switched off by a number that is not about measurement
- An enumeration is not a proof, and "every" is the word to distrust
- A schema comment is code that nothing executes
- A guard standing behind a stricter guard is decoration
- A once-only WRITE behind an unbounded READ is not once-only
- A break that is equivalent to the original proves nothing
- "It probably fits in one page" is a fact you can just measure
- A sample whose strata do not overlap the target proves nothing, at any `n`
- A term that is zero everywhere has an unobservable sign
- A defence built for one axis of a classifier is not a defence for the classifier
- Arithmetic that reproduces to the digit says nothing about its inputs
- "Read-only" is not a scope boundary; name the environment
- The census must apply the same filter the storage path applies

### 2026-08-08 — [`archive/lessons-2026-08-08.md`](archive/lessons-2026-08-08.md)

- Deduplicating the record made the record unusable
- A rate limit belonging to one dependency was applied to both
- The user-facing explanation of a limit outlives the limit
- Two guards passed their tests on the first run, and both were broken
- Re-deriving a decision at a new price is one-sided unless you say otherwise
- Kalshi sends "0.0000", not a missing field
- A ticker's failure mode is silence that looks like calm
- A test asserted the order of a command that was not in the image
- The counter you are told to watch was counting the other population
- A wrong value that is still legal never announces itself
- A guard that fails every time says exactly as much as one that never fails
- Two implementations of one money quantity, neither ever run
- An enumeration of the safe cases is a list you will forget to extend
- The value you already had is not a value you chose
- A guard tightened for a false negative fires on the file explaining it
- `occurrence_datetime` is a shifted start, and both stories had real evidence
- A green suite that depended on what time you ran it
- A component that only exists after a tap is invisible to every check you have
- One environment variable, two readers, two different times
- Sync code that is only ever called from a coroutine
- A secret in `.env` makes the test suite behave differently per machine
- The schema file runs against databases that already exist
- An optional safety parameter is a guard that cannot fail
- One signal asked to be both an alert and a status, and oscillated
- The counter you were told to watch was filtered out at zero
- A filter's vocabulary is not the field's vocabulary
- Adding a NOT NULL column silently disarms every `INSERT OR IGNORE`
- Recovering structure by parsing free text, in a boot path

### 2026-08-07 — [`archive/lessons-2026-08-07.md`](archive/lessons-2026-08-07.md)

- Every per-cell guard can pass and the conclusion still be wrong
- Computing the right statistic and then ignoring it
- A window resize is not a viewport change
- A true measurement licensed a false conclusion
- The WebSocket path was dead and 611 tests said otherwise
- Four audits, one failure shape
- One observation recorded thirty times is one observation
- An idle threadpool hides every thread-safety bug you have
- The zero that means "no measurement" passes every threshold
- Code with no caller is not a feature, it is a plan
- A live credential can leak with nobody logging it
- Two limits on one quantity, and the tighter one wins in silence
- A captured fixture that no test loads is decoration
- The null for one proportion is not the null for a difference
- A guard that routes around thin data into a fallback built from it
- A threshold that is valid once is not valid every time you look
- `INSERT OR IGNORE` will happily ignore your fixture
- Suppressing a conclusion is not suppressing the finding
- A budget that says *whether* and never *when*
- A stored age rendered as a current one
- Two populations in one record, told apart by dispersion
- A detector that counts prose about the bug as evidence against it

### 2026-08-06 — [`archive/lessons-2026-08-06.md`](archive/lessons-2026-08-06.md)

- Unreadable must never resolve to zero
- Clamping is for values you trust
- A test that passes on the bug is not a test
- The conservative fee model is a hedge with an expiry date
- A bashism under `#!/bin/sh` is a crash loop with no cause
- Two bugs that only a running app could show
- "No result" and "rejected" are different outcomes
- A redundant special case can silently delete a whole method
- The devig spread depends on line shape, and I had it wrong
- Test that the filter's *exclusions* are decisions
- Measure the style rule before believing it
- When a document and the live API disagree, the API wins
- Kalshi may be the sharp side, not the soft one
- CLV needs hundreds of bets, not dozens
- A sign convention agreed with its own test, and both were wrong
- Synthetic data that is right on the mean and wrong on the variance
- An empirical distribution cannot be slid sideways
