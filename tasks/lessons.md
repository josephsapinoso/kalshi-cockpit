# Lessons

Dated, one lesson per entry. Written when something was got wrong, or when a
correction arrived. Reviewed at session start.

- **Write the pattern, not the incident.** "PR #42 broke staging" ages out;
  "unreadable must never resolve to zero" doesn't.
- **A lesson earns its place by preventing a repeat.** If it would not have
  changed what someone did, it is a note, not a lesson.
- **This file is the newest lessons plus an index; the rest live in
  `tasks/archive/lessons-YYYY-MM-DD.md`, verbatim.** The budget is 262,144
  bytes (`tests/test_session_files_are_readable.py`). Split at ~90%, checked
  with `wc -c` before writing; cut on a date boundary; name the archive for the
  split date; move the index lines in the same edit; verify by md5. Every
  split so far: `tasks/archive/lessons-split-log.md`.

---

## 2026-09-17 (thirteenth) - Before extending an instrument, read what its tests FORBID it from emitting; a registered instrument's scope is a contract, and the obvious extension is the one that breaks it

Asked to make `combo-position-gaps` detect the inverse direction, the
obvious move is to add a section. It would have been wrong:
`tests/test_inspect_live_db.py:3706` pins that query to emit **zero**
`parlay_positions` columns, because a registered measurement computes a
statistic over that table and "a later convenience column cannot quietly
turn an operational instrument into an interim look." The lane read the
test first and built a **sibling query** instead. I would have extended it.

The general shape: **a test that asserts an absence is a scope contract,
and scope contracts are invisible to anyone who reads only the code the
feature lives in.** Before adding to any instrument that feeds a
registration, grep its tests for what they refuse, not just what they
require. The tell is a test class named for what the thing *cannot* do.

Two corollaries from the same round:

- **A fact with three possible causes needs three strings, not two.** A
  fill count is `None` because a dry run sent nothing, `None` because the
  venue's reply was unreadable, and `0` because a real order matched no
  one. Collapsing any pair loses the distinction that matters. "Unreadable
  resolves to `None`, never `0`" **cuts both ways** — reporting a real zero
  as "unknown" hides a fill that is known to be empty behind one that
  might not be.
- **A number that decays by design does not belong in a document sessions
  are told to trust.** The transacted-path count was corrected four times
  in nine days; each correction was a fresh number that guaranteed the
  next one. The fix is not a better number, it is naming the instrument
  and saying the figure is stale on sight (ADR 0162). The tell that it was
  structural rather than careless: the same count lived in **three** places
  in one file, one of them already contradicting another, so every past
  correction fixed a third of it.

## 2026-09-16 (twelfth) - A mutation that changes nothing reports the same green as a guard that is watching; the harness has to refuse the no-op, and a mutation that only ADDS to a pattern has not disabled it

Eleven mutations were run against a screen guard. Three came back wrong, and
all three would have been read as "guard verified" by a harness that only
applied a replacement and ran the tests:

- **Two literals matched zero times**, because the files are CRLF here and
  the mutation literals were written with `\n`. The edit applied nothing, the
  suite stayed green, and the only reason that was visible is that the
  harness asserts the literal occurs **exactly once** before writing. Without
  that assertion the report would have said the guard was verified while the
  file was never touched. The same fact that makes `Path.write_text` unsafe
  here makes a multi-line mutation literal unsafe: normalise the line endings
  to the file's own before matching.
- **One "neutered" regex still worked.** The mutation prepended two dead
  alternatives to an alternation and left the live ones in place, so the
  pattern matched exactly as before and the anti-vacuity test passed --
  correctly. Neutering an alternation means REPLACING it, not adding to it.
  A mutation that comes back green is a claim about the mutation first and
  the guard second (CLAUDE.md, Testing).

The general form: **a verification step that cannot distinguish "the
mutation did nothing" from "the guard caught it" verifies nothing.** Make the
no-op loud -- count the matches, fail on anything but one, and print the
md5 before and after so a restore that did not restore is visible too.

## 2026-09-16 (eleventh) - A median does not bound a tail, so a measurement of the centre cannot falsify a condition written about the worst case; and the regime you can measure cheaply is usually the one where the effect is known not to occur

A park carried a trigger: "unpark only if a route-latency read shows a desk
route over the 25 s read budget." A latency read on a warm box returned
medians of 75 ms to 1,727 ms, and the conclusion written was "the first
conjunct is measured false, delete the park." A skeptic pass refused it and
was right on every point.

Three failures, and they compound:

- **The budget fires on the slowest request; every number taken was a
  median of three.** The harness kept only median and min, so the run's
  actual maxima were unrecoverable after the fact. 0 events in 39 draws
  bounds the rate no tighter than 7.7% (rule of three) -- which is the
  honest summary, and it is not reassuring. **Record per-rep values in any
  harness whose result will be compared against a ceiling.**
- **The cheap regime was the wrong regime.** Warm is what a session can
  measure in a minute; the budget had only ever fired cold or after a cache
  eviction. The draft stated this in its own "does not establish" list and
  then let the conclusion range over a regime the measurement never touched.
  **When the caveat section and the conclusion disagree, the caveat is
  right.**
- **The search stopped at the first explanation.** Six recorded incidents
  were found, traced to a fixed defect, and the question felt closed. A
  second budget event -- a 503 on a different route, structural and
  unfixed -- was in this project's own memory and was never looked for,
  because one confirmed story is where looking stops.

Two corollaries worth their own line:

- **An incident count whose writer is best-effort under contention is
  censored in the direction that matters.** The unrecorded hits are the
  ones under hard load, which is when the ceiling is likeliest to be hit.
  Such a count is a floor biased low in exactly the worst conditions, and
  "no rows since the fix" is therefore not evidence of health.
- **A ratio is not banked just because it sits in an ADR.** The 3.37x cited
  as fact came from a rehearsal whose own ADR rejects its timing method and
  records the same query varying 3.04x on cache residency alone. What was
  banked was the qualitative finding beside it. **Before quoting a
  magnitude from a document, check whether that document trusts it.**

And the disposal itself was the tell: deleting a park is the one action the
condition's falsity would authorise, and also the only action a session can
take alone. `docs/measurements/2026-09-16-desk-route-latency-warm-box.md`,
ticket #51.

## 2026-09-16 (tenth) - A copy guard that pins a field by NAME pins the name, not the claim; and a correction trail that quotes the killed phrase re-triggers the guard while a line-wrapped one dodges it

Three ways a word-guard over user-facing copy lied this session, all on the
hedge screen's "lock" wording and the Discord push that repeated it:

- A rendered-output test that selects a field with
  `next(f for f in fields if f["name"] == "Locks")` pins the **name**. When
  the name changes the test goes red for the wrong reason; when the claim
  moves under a new name it stays green. Pair every by-name pin with a
  source-level word guard over the strings the builder emits.
- The docstring carried "capped at one
 * contract" past a guard that
  refused "capped at one contract" for a week. A guard over source text must
  either collapse whitespace before matching or scan at the token level.
- A correction-trail comment that quotes the killed phrase verbatim -- "this
  read 'lock available' until 2026-09-16" -- is caught by the same guard.
  Describe the old copy in a file the guard scans; never reproduce it.

## 2026-09-16 (ninth) - When a universal dies, a test on one surface certifies nothing about the others; enumerate every surface that carries the sentence and sweep for strays

"No way out of a combination except the outcome" was falsified on 2026-09-10.
The correction landed on the fallback paragraph and the price-lookup note,
and the only test asserted one word ("exit") in one of those files. The
checkbox six lines below the fallback -- the sentence Joe actually ticks to
spend money -- kept the dead claim for six days, and so did the parlay card,
two server-composed notes, and CLAUDE.md's own `/hedge` paragraph.

A fallback branch is the least-rendered place a correction can land, and a
comment saying "a fallback is where a falsified sentence survives longest"
was sitting directly above the surviving one.

Rules:

- **When a universal dies, grep both trees for every phrasing of it** -- the
  absolute ("only exit", "no way out", "cannot exit"), not just the sentence
  you remember -- and list every hit in the commit that kills it.
- **One test enumerates the surfaces and sweeps for strays**
  (`tests/test_combo_exit_copy_is_small_and_unmeasured_on_every_surface.py`,
  modelled on the soft-fallback surface test): the listed surfaces must
  carry the new truth, and any file containing the vocabulary outside a
  listed slice fails. A test that asserts one surface is a test of one
  surface.
- **State the size in words and no rate.** "Seen on two books, ten
  contracts each, and how often has never been measured" is what an
  existence proof supports; a digit invites a percentage.

## 2026-09-16 (eighth) - An unasked question decays into the measurement that produced it, because the measurement is the part a session can execute alone

The twenty-second session measured the sharp-anchor rate, found NCAAF spreads
and totals at about 30%, and filed open item **1** as:

> **The NCAAF anchor question is for Joe.** Nothing to build until he answers;
> the flag is already on the row.

One session later that item was gone. In its place: "run `sharp-anchor-census`
Saturday." The session after that -- mine -- inherited the new wording and
re-filed it the same way, and I then defended it to the partner agent as
correctly calendar-gated. It was not. The structural half of the finding
(`SHARP_BOOKS` has four members, `betfair_ex_uk` is unpurchased,
`betfair_ex_eu` quotes h2h only, and the devig runs per rung) is true on a
Wednesday. A live slate moves the percentage; it cannot remove the population.

**The question decayed into the measurement that produced it, twice, in three
sessions.** Nobody deleted it. It was replaced by the nearest thing a session
could do without waiting for a human -- and re-running an instrument always
looks like progress on the question the instrument first raised.

The structural reason it will happen again unless something changes: the
infrastructure queue **refills itself** (every measurement produces a successor
measurement, a cleanup, an index to price) while the decision queue only
refills when somebody writes a ticket. Checked 2026-09-16: map issue #3 has 37
sub-issues and every one is closed. One queue is self-replicating and the other
is structurally empty, so drift toward infrastructure is the default and no
individual session is at fault for it.

Three rules:

- **A measurement that produces a question for Joe opens a ticket in the same
  session, or the question does not exist.** A line in `tasks/NEXT.md` is not
  a durable home: the next session rewrites that list, and what survives a
  rewrite is whatever can be executed.
- **When an item says "ask Joe", check whether it still does.** If the wording
  has become "run X", read the entry it came from before accepting the new
  wording. `git log -p tasks/NEXT.md` is the instrument; the entry is verbatim
  in the archive.
- **A question is calendar-gated only if the ANSWER changes with the
  calendar.** More data almost always sharpens a number without changing the
  decision the number feeds, and "wait for the slate" is the most comfortable
  way to not ask.

Built the same day, later session: CLAUDE.md workflow step 7, the "Open a
ticket for Joe" recipe in `docs/agents/issue-tracker.md`, check 11 in the
measurement-skeptic's audit, and `tests/test_a_question_for_joe_has_a_ticket.py`,
which refuses a `Question for Joe:` marker with no number, refuses `#3` (the
map) as the number, and refuses any Still-open item that says *for Joe* /
*Joe's call* / *until he answers* with no ticket. Both mutations observed red
on the real file. The first rule above is now a contract, not a habit.

## 2026-09-16 (seventh) - A before/after measurement taken thirty minutes apart is a drift measurement; interleave the arms or do not compare them

Two instruments were written the same day for the same decision.
`measure_fair_price_window_index.py` times its arms **round-robin in one
process**, and its docstring says why: the identical query over the identical
data read 1,283 ms in one session and 3,904 ms in the next, purely on how much
of the file the page cache still held.

`rehearse_fair_price_window.py` -- written hours later, by the same reasoning,
to answer the harder question on live -- does not. It times every "before"
statement, runs `ANALYZE`, then times every "after" statement. On live that put
the two halves of each pair **thirty minutes apart**, on a box that was running
the recorder and had just had its cache scoured by three 208-second reads in
between.

It produced exactly the artefact you would predict: one arm came out 2.5x
slower "after", with its query plan **byte-identical**. Statistics cannot slow
a query down without changing its plan, so the number was about the clock, not
the change.

The rule was known, written down, and applied in the sibling file. It was lost
in the second instrument because that one is shaped like a *procedure* -- copy,
measure, change, measure, clean up -- and the procedure's natural order is
exactly the wrong order.

Three rules:

- **Pair the arms in time, not in narrative order.** "Before" and "after" are
  a story; a measurement needs them adjacent. If the change can be undone on
  the copy -- and `sqlite_stat1` can be dropped and rebuilt -- then interleave
  and take several rounds.
- **A plan-unchanged timing change is a fact about the environment.** Read it
  as a bug in the harness before reading it as a finding. It is one of the few
  places where "that cannot be right" is a sound first reaction.
- **When a second instrument answers the same question as a first, copy its
  caveats deliberately.** The gap here was not ignorance; the constraint was
  two files away in a docstring written the same day. Re-read the sibling's
  "what this does not establish" before trusting the new one.

And the outcome rule, which is the reason this entry is short on regret: **the
guard fired and was honoured.** The other rows were attractive -- a 322x win
already banked, a 3.37x further gain, the feared plan intact -- and that is
exactly the condition under which a flagged regression gets explained away.
Nothing shipped.

## 2026-09-16 (sixth) - A copy that restarts whenever its source is written cannot outlast the writer's cadence, and it reports the restart as progress

The v37 rehearsal copied the live database with `sqlite3.backup`, paced at
2,000 pages per 20 ms: 5.17 GB in 640 s. The same code was re-run on 2026-09-16
against 6.32 GB and never finished.

**SQLite restarts a backup from page 1 whenever the source is written through
another connection.** The recorder writes every ~900 s. This copy needed
~1,200 s. So every pass was thrown away and begun again, forever.

What makes it worth an entry is how it presented. There was no error, no
warning and no progress output. The destination's **mtime advanced the whole
time**, so every liveness check said "still working", while its **size sat
frozen** at 2,744,320,000 bytes -- the high-water mark of the best attempt --
for six minutes. The first two size readings were taken 20 s apart, showed no
change, and were dismissed as sampling noise; the third, three minutes later,
showed growth and "confirmed" it was fine. It was a restart cycle.

The v37 run did not succeed because the approach was sound. It succeeded
because 640 s happened to be less than 900 s, and nobody wrote down that the
margin was the load-bearing part.

Then killing it made a second mess. **`flyctl ssh console -C` does not take
the remote process with it when the client dies.** PID 722 kept looping on the
box; `rm` on the copy returned cleanly and `df` still showed the 2.7 GB gone
missing, because the surviving process held the unlinked file open. The volume
only reclaimed it after the process was killed through `/proc`.

Four rules:

- **Before copying a live database, ask what the writer does to the copier.**
  `sqlite3.backup` restarts; `VACUUM INTO` is one statement under one read
  transaction and cannot be restarted by a concurrent writer. The choice is
  not about speed.
- **A long operation with no progress output and no deadline cannot be
  distinguished from a hung one.** Both were added: a progress handler that
  prints bytes written every 30 s, and a wall-clock deadline that ABORTS. A
  guard that only exists to be hit once is still cheaper than the run it saves.
- **mtime is liveness, not progress.** A process rewriting the same region
  forever looks identical to one making headway. Measure the quantity that is
  supposed to grow, and sample it far enough apart that a plateau is not
  mistaken for jitter -- or better, have the program print its own progress.
- **A remote command needs a signal handler if it creates anything large.**
  `finally` does not run on SIGTERM. Trap SIGTERM/SIGHUP/SIGINT, delete what
  you made, and print the PID at startup so it can be reached from another
  shell when the signal never arrives.

A fifth, about the number rather than the mechanism: **`VACUUM INTO` compacts,
so the copy is defragmented and its scans are more sequential than live's.**
That understates the benefit of replacing a scan with a seek, which is the
conservative direction and the only reason it is acceptable. Say which way an
artefact pushes, every time.

## 2026-09-16 (fifth) - The planner can DECLINE an index; before pricing one, check which plan it actually picks -- and ask whether what is missing is statistics

An approved piece of work was "add an index on `fair_prices(computed_ms)` so a
`--since` bound becomes seekable". The reasoning behind it was correct at every
step: the query was an unbounded `GROUP BY` over a ten-million-row table, none
of the table's three indexes leads with `computed_ms`, so a bound added today
would filter after the scan. All true.

ADR 0141 requires an index to be bought on a timing, so the timing was taken
before the index was written. Modelled at live's shape, seven-day window,
round-robin:

    bounded, no index, no statistics      883.0 ms
    bounded, WITH the approved index      882.6 ms    <- 154 MB for nothing
    bounded, no index, after ANALYZE      258.9 ms    <- free

**The planner never chose the new index, in any arm.** It kept
`idx_fair_market_computed`, which leads with `market` and satisfies the
`GROUP BY` -- and once `sqlite_stat1` existed it ran that same index as a
SKIP-SCAN (`ANY(market) AND computed_ms>?`), because `market` has a handful of
distinct values. The bound was never waiting on an index. It was waiting on
table statistics, and **nothing in `backend/` has ever run `ANALYZE`**, so the
live planner has been choosing from built-in defaults since first boot.

The same run killed a second premise the same way: the sibling section's
`commence_ms` bound does not seek either, because a *different* covering index
(`idx_odds_window`, added for an unrelated query) wins the plan and applies
`commence_ms` -- its fourth column -- as a filter.

Four rules:

- **Before pricing an index, print the plan the query picks WITHOUT it, and
  check whether some other index already satisfies the shape.** "No index
  leads with this column" is a fact about the schema. "The planner will
  therefore use mine" is a guess about the optimiser, and it is the guess that
  was wrong. An index the planner declines is zero benefit at full price.
- **An absent bound and an absent `sqlite_stat1` produce the identical
  symptom.** Both read as `SCAN ... USING INDEX <something>`. Adding an index
  is the expensive remedy and running `ANALYZE` is the free one, and nothing in
  the plan line tells you which you need -- only trying both does. Check
  whether the database has ever been analysed BEFORE designing an index for it.
- **ADR 0141 cuts both ways, and this is the first time it cut this way.**
  "Buy an index on a timing" has only ever been used to justify one. The same
  rule refuses one, and refusing is the harder direction to reach, because by
  then the work is approved, the schema version is reserved and the migration
  is the obvious next thing to type.
- **A cheaper remedy is not automatically the shippable one.** Statistics are a
  GLOBAL planner input, and the two hottest readers of that table earned their
  plans without any. The free fix has the wider blast radius, so it ships
  behind a rehearsal on a copy of the live file that diffs those plans, while
  the bound -- which is free AND local -- ships immediately.

## 2026-09-16 (fourth) - A merged lane is not a finished lane; do not remove a worktree until its agent has reported

Four lanes ran in parallel worktrees. Three had reported, so their worktrees
were removed and their branches deleted -- and the fourth's was removed in the
same sweep, because `git worktree list` showed it and `git log` showed its
commit already merged into `main`. Merged is not the same as done.

That lane was still running. From inside, its directory was wiped mid-run: the
working tree emptied, the worktree deregistered, and the branch ref it had
committed to deleted underneath it. It recovered -- the commit object lives in
the shared object store, so it recreated the ref and handed back correctly, and
`git merge-base --is-ancestor` confirmed afterwards that nothing was lost. It
also reported a full-suite run showing mass failures, which was not a
regression at all: that run was reading a filesystem being deleted around it.

Nothing was lost this time. What it cost was a scare and a misleading test
result, and both were avoidable by waiting for a notification that was already
coming.

Three rules:

- **The completion notification is the signal, not the merge.** An agent's
  commit appearing on `main` says its work is safe; it says nothing about
  whether the agent is still writing, still running tests, or about to write
  its report. Reap worktrees when the task-notification arrives.
- **`--force` on a worktree removal silences the one check that would have
  caught this.** Plain `git worktree remove` refuses a dirty tree, and a
  running agent's tree is usually dirty. Reach for `--force` only after the
  owner has reported.
- **A test result from an agent whose environment was being torn down is not
  evidence.** When a report carries both a clean run and a catastrophic one,
  the question is what changed underneath it -- not which result to believe.

## 2026-09-16 (first) - A bound you can read in the SQL is a hypothesis about the planner; EXPLAIN the before, the after, AND the no-flag case

ADR 0157, written the day before with care, recorded `prop-rungs` as having a
flag that looks like a bound and is not one, and named the fix: push
`(:event IS NULL OR odds_event_id = :event)` down into the CTE, called "safe
and population-preserving". It is population-preserving. It is also a
**complete no-op** -- the plan with it is byte-identical to the plan without
it, for a named fixture and for no flag:

    CO-ROUTINE latest
    SCAN odds_snapshots USING INDEX idx_odds_event_commence   <- still whole
    SCAN l
    SEARCH odds_snapshots USING INDEX idx_odds_event_commence (odds_event_id=?)

SQLite cannot know a bound parameter's nullity when it plans the statement, so
it must emit a plan correct for NULL, and that plan is a scan. Only a hard
equality seeks -- which means two statements, not one with a switch inside it.

**The second half is why nobody caught it.** That `SEARCH ... (odds_event_id=?)`
line is in the UNBOUNDED plan too. It comes from the join on
`l.odds_event_id`, not from the flag. Anyone checking "does `--odds-event-id`
bound this" sees a seek keyed on exactly the column they filtered by, and stops
looking. The evidence for the flag working and the evidence for it doing
nothing are the same line.

Three rules:

- **The baseline for a bound is the plan with NO flag, not the plan before your
  edit.** A bound that "adds a seek" has added nothing if the seek was already
  there. Print both and diff them.
- **`(:p IS NULL OR col = :p)` is a filter, never a bound.** It reads like one
  in every language most of us think in. If the optional case must also be
  cheap, that is two statements built from one template, and the template is
  what keeps them from drifting.
- **A fix named in an ADR is a hypothesis until someone runs it.** This one was
  reasoned from correct premises by a careful session and was wrong, and it was
  about to be implemented on that ADR's authority. Cite the ADR for the defect;
  measure the remedy yourself.

## 2026-09-16 (second) - When an input and its measurement both exist, read the measurement; the input can only flatter or frighten

A new query reported which bookmakers came back per sport, and its worst cell
was WNBA: one sweep, `matchbook` absent, `pinnacle` on 5 of 8 fixtures. That
was written up as "3 of 8 WNBA fixtures have no sharp anchor on spreads and
totals". The column that actually records the outcome,
`fair_prices.anchored_on_sharp`, says WNBA `h2h` is anchored on **every** row
and the worst cells in the table are NCAAF `spreads` and `totals` at about
30% -- which are also the **largest** cells in it. The draft led with the sport
whose unanchored cells hold 6 and 2 rows and missed the one holding 95.

The input could not have predicted the output, and the gaps run one way. A book
"present on spreads" means it quoted *some* spread line; the devig runs per
**rung** and admits a book only if it quoted *that* line two-sided in the same
sweep. Add books that fail the devig and games that have started, and presence
is a strict upper bound on anchoring -- never a lower one, never an estimate.

The instrument's own docstring said this, in the section headed "What this does
not establish", and the session that wrote the docstring is the session that
then ignored it.

Three rules:

- **If a column records the answer, the answer is that column.** Reasoning
  forward from inputs is for when there is no column. Ask "what does the code
  write down when this happens" before building the inference.
- **State the direction of every gap between a proxy and its measurement.** An
  upper bound and an estimate license different sentences, and "roughly
  indicates" hides which one you have. All four gaps here ran the same way,
  which is the only reason the proxy was worth keeping at all.
- **A "worst cell" chosen across several groups is a max statistic.** Report
  which groups were looked at, and check n: the worst-looking cell is
  disproportionately the smallest one, and here it held four rows.

## 2026-09-16 (third) - A dispatch whose branches return identical results cannot be guarded by a test that reads the results

Two SQL statements were introduced that return the same rows on purpose -- one
bounded, one not -- and a function chose between them. The tests for that
choice asserted on the returned rows, and the mutation (`use the unbounded
statement for both branches`) was measured **STILL GREEN**. It had to be: the
equivalence of the two statements is the thing the rest of the file proves, so
no assertion about rows can distinguish them.

The guard had to observe the *statement*, by capturing what the function handed
to `_fetch`. That felt like testing an implementation detail, and it is not:
once the outputs are proven equal, which statement runs is the entire remaining
behaviour, because the difference between them is cost.

Two rules:

- **Run the mutation before believing the test.** This test was written by
  someone who had just written the paragraph explaining why the two statements
  are equivalent, and still expected a row assertion to tell them apart.
- **When a choice is invisible in the output, the choice itself is the
  observable.** Otherwise the branch is decoration, and the next session
  deletes it as redundant -- correctly, on the evidence available to them.

## 2026-09-15 (ninth) - A comment that names future work becomes a phantom backlog item the moment that work ships

A partner pass over seven open NEXT.md items found three of them already
built. Two had been closed hours earlier by ADRs written the same day, and
one -- `parlay_position_legs.event_title` -- was closed by ADR 0153 and
schema v43 while its own source comment still said the step had not landed:

    Carried in the blob now; `parlay_position_legs` has no column for it
    yet, so `/hedge` still prints the label alone until that schema step
    lands (`tasks/NEXT.md`).

The column exists (`schema.sql:2483`), the migration runs
(`db.py:1059`), `/hedge` serves it (`hedge.py:1026`) and the screen draws
it (`HedgePositions.tsx:272`). Nothing was broken. What was broken is that
the comment pointed at `tasks/NEXT.md`, the queue is seeded from prose
like it, and the next session dutifully re-entered a finished task. Three
of seven items on a drained queue were phantoms; the cost is a whole
planning pass spent on work that does not exist, which is the most
expensive kind because it looks exactly like work that does.

This is the *inverse* of the shape already recorded here (a comment
asserting a property the code has lost). That one flatters the code; this
one flatters the backlog. Both are a description outliving the thing it
described, and in both the description is the only half anyone reads.

Three rules:

- **A comment that names a future task is a to-do with no owner and no
  expiry. The change that does the task must delete the sentence** -- grep
  the codebase for the feature's name, not just the file you edited. If
  the sentence cites `tasks/NEXT.md`, the NEXT.md item is its twin and
  both are struck in one edit.
- **Before planning a queue item, verify it at source.** Three greps
  settled all three tonight -- the symbol, the migration, the renderer.
  A summary of the backlog is not evidence about the backlog, and the item
  most worth checking is the one whose wording you inherited verbatim.
- **Prefer "here is where it landed" to "this is not done yet."** A
  comment recording a shipped fact with its file references stays true and
  costs the same to write; a comment recording an intention has to be
  maintained by someone who will never be told it came true.

## 2026-09-15 (eighth) - When a call changes what it SENDS, the row that records it is part of the change

ADR 0155 switched the odds feed from buying regions to naming ten
bookmakers, and got the arithmetic exactly right: `sweep_cost` billed
`markets x ceil(books/10)`, the vendor agreed, and the first live sweep
cost 3 instead of 6. The row recording it still wrote `regions = "us,eu"`,
because nothing in the change touched the writer. So the ledger said a
three-market, two-region call had cost 3 - and the table's own documented
rule turns that into 3 x 2 = 6.

Nothing was mis-billed; `cost` was right throughout, and the
reconciliation against `x-requests-used` never drifted. What broke was the
only column that says WHY the cost is what it is, which is the first
column anyone reads when a drift shows up. The instrument had the same
hole: `inspect_live_db_feed._CREDIT_COLUMNS` did not select the new field
and its comment still asserted `cost = markets x regions`, so the tool
built to catch config drift would have shown the misleading row and
nothing else.

This is the third instance in one day of one shape: a value and its
description drifting apart, with only the description ever read. The other
two were a comment asserting a property the function had lost in the same
commit that wrote it (ADR 0154), and CLAUDE.md's transacted-path counts
going six orders stale inside a day.

Three rules:

- **A change to what goes on the wire is not done until the recording
  matches.** Grep the writer, the schema comment and the inspector in the
  same change as the call. If the row cannot express the new thing, that is
  a migration, not a footnote.
- **When two fields become alternatives, say which is authoritative and
  what NULL means.** `bookmakers` NULL means "bought regions", not "bought
  no books"; without that sentence the next reader picks whichever column
  is populated and is right half the time.
- **Check the instrument in the same pass as the data.** A query whose
  column list predates the column is blind in exactly the place the change
  happened, and it reports confidently.

## 2026-09-15 (seventh) - A cost lever is proposed from the formula and must be validated against the data; the multiplier may be carrying something

`sweep_cost` is `len(markets) * len(regions)`, so when `ODDS_MARKETS` gained
`totals` and every call went 4 -> 6 credits against an unchanged cap, cutting
`ODDS_REGIONS` from `us,eu` to `us` was the obvious halving. It was offered
to Joe in those terms - "at the cost of the EU books in the consensus" - and
he approved it.

The check that had not been run: WHICH books `eu` carries. `SHARP_BOOKS` is
`{pinnacle, betfair_ex_eu, betfair_ex_uk, matchbook}`, `consensus_devig`
selects on it exclusively when any member is present, and all three sharps
the feed actually carries are EU-region; none is offered in `us`. So
`regions = "us"` makes `sharp = {}` on every row. Measured: 22,850 of the
last 40,000 `fair_prices` rows (57%) are `anchored_on_sharp = 1`, and the
cut takes that to zero. The lever would have deleted the sharp anchor - the
thing the desk exists to price against - to save three credits a call.

Two queries settled it and neither was expensive: one GROUP BY over
`odds_snapshots.bookmaker`, one over `fair_prices.anchored_on_sharp`. The
arithmetic that made the lever look free was visible in a single line of
source, which is exactly why nobody looked further.

Three rules:

- **Read what is on a knob before quoting its price.** A config value that
  appears in a cost formula as a plain multiplier is still a *selector* over
  real data. Name the rows it selects and count them before offering the cut.
- **An approval inherits the framing it was given.** When a check after the
  approval changes the size or the sign of the cost, the approval is void -
  take the corrected number back to him rather than shipping what he said
  yes to. He said yes to "lose the EU books", not to "lose the sharp anchor".
- **Look for the lever that keeps both before accepting the trade.** Here it
  was the vendor's `bookmakers` parameter, billed per group of ten - same
  halving, sharps intact. It was one documentation page away and the trade
  had already been framed as unavoidable.

## 2026-09-15 (sixth) - Fix every reader in the function, not the one whose symptom you saw; the card that would have shown the other one may be the card nobody taps

`2d8de82` fixed a wrong-side read this morning: `leg_facts` was keyed by
ticker and hardcoded the YES ask, so an Under leg printed the Over's price.
The fix added `no_ask_*` keys and `_ask_facts_for_side`. Three lines below
the repaired ask, a second reader in the same function was still keyed by
ticker with `side = 'yes'` hardcoded - the skeptic's verdict. It survived
the fix by eight hours and was found by a partner pass, not by the tests.

Two things hid it. The comment the fix itself added directly above the
surviving defect said "Both sides, one derivation each", asserting a
property the function did not have - a justification stale in the commit
that wrote it. And the only card anyone exercised was totals, which is
immune for an *unrelated* reason (`_price_totals_event` writes no
`recommendations` row at all), while props - which write a row per side, and
which had 0 taps in 77 lifetime lookups - was the card that would have shown
it. "It worked when we looked" measured which card was convenient.

The verdict half was also the flattering half: a YES row's mere existence
stamped `checked` on the Under, claiming twelve mechanical checks on a side
the skeptic never scored. The same function's docstring already forbids that
misreading in the other direction.

Three rules:

- **A wrong-side read is a class, not an incident. Grep the whole function
  for every read keyed by the thing that was wrong** - here, every `ticker`
  key and every literal `'yes'` - and fix them in one change. The second
  reader's symptom is identical to the first's and equally silent.
- **A test that names the side must exist for each reader.** The 2d8de82
  guard called `seed_total` and never `seed_prop`, so it pinned the arm that
  could not break and left the arm that could.
- **When a fix leaves a comment asserting the new property, check the
  comment's scope against the code under it.** "Both sides, one derivation
  each" was true of the eight lines above it and false of the twenty below.

## 2026-09-15 (fifth) - A write-up drifts toward the flattering sign; a count copied from the spine is a count nobody re-read

The registered fill-vs-venue census was taken today and its first draft
carried three errors, all found by the measurement-skeptic before entry
and none by the author. The stake being overstated makes the hedge figure
run *low*; the draft said *high* - the sign that reads as "the number Joe
sees is generous". The draft asserted a `parlay_positions.stake_tenths`
figure for the one non-zero row; the census never opens that table, and
the row predates the position recorder, so no such row exists - the claim
was reasoned from CLAUDE.md's "4 rows", which the same afternoon's read
found to be 10 open rows, as its "7 orders" was 13. And eleven equalities
were read as "a one-level book"; the registration's own A5 runs one way
(a one-level book produces equality) and the census read no book.

The shape: the prose around a measurement is written by someone who
already believes the result, so every ambiguity resolves toward the
reassuring reading, and every count it borrows from the spine is quoted,
not re-read. The spine's transacted-path block had been corrected four
times in a week and was still six orders stale, because Joe bets and
nothing tells the file.

Three rules:

- **Every sign in a write-up is derived, not remembered.** Write the
  formula the term enters (`W - S - Wq - fee`), put the error in, read the
  direction off. A direction stated from memory is the flattering one
  about half the time and nobody can tell which half.
- **A claim about a table the instrument did not open is not a finding.**
  If the harness reads `manual_orders` and `fills`, the write-up may not
  name `parlay_positions`; a sentence that crosses from the recording into
  the money path needs its own read.
- **Re-read a count before quoting it; CLAUDE.md is a cache with no
  invalidation.** Any count of Joe's transacted path is stale the moment
  he bets, and the instrument for each count is one line away
  (`manual-orders-audit`, `/api/hedge`, `notifications`). Quote the count
  with its table, its instrument and its date, and treat a count without
  a date as unread.

## 2026-09-15 (fourth) - EXISTS does not short-circuit for the rows that fail it; when one parameter value is fast and its sibling times out, the plan is walking the non-matches

The Games screen's NFL chip said "Backend unreachable" six times in five
minutes while the MLB chip answered at once. Same route, same statement,
one parameter. The league cut was `EXISTS (SELECT 1 FROM odds_snapshots o
WHERE o.odds_event_id = l.odds_event_id AND o.sport_key = ?)`, and
`sport_key` is in no index that leads with `odds_event_id`, so SQLite took
the index that leads with `sport_key` and, for every outer row whose
fixture is NOT in the asked-for league, read that league's entire slice of
a ten-million-row table before it could say no. The MLB chip was fast
because most rows match on the first probe; the NFL chip paid the full
walk ~350 times per statement, twice per request. Local, live-shaped: 73 ms
to 0.5 ms. Live: 25 s to under a second. The docstring beside it said
"an indexed SEARCH on `odds_event_id`", and the plan did say SEARCH.

The shape: "EXISTS stops at the first match" is true and is the wrong half
of the cost. The rows that FAIL an EXISTS are the ones that read the whole
group, and a filter's job is to make most rows fail. The tell is
asymmetry - one value of a parameter cheap, another ruinous, on one
statement.

Three rules:

- **When a group has one value of a column, read the group's first entry
  and compare; do not ask EXISTS to find it.** `(SELECT col FROM t WHERE
  key = ? ORDER BY <leading index column> LIMIT 1) = ?` touches one entry
  whichever way the answer goes.
- **A plan test pins the index AND the bound.** `SEARCH ... USING INDEX`
  says how the rows are reached, never how many; the `LIMIT 1` is what
  bounds it, and the v39 index note already paid for learning that once.
- **"Backend unreachable" is read from `read-incidents` first**, never
  from the screen. The row carries the path with its query string, which
  is the parameter that failed - the diagnosis was one column wide.

## 2026-09-15 (third) - A refusal carries its premise; before inheriting the refusal, re-read the premise against what the record now holds

Two refusals stood between Joe and the over/under and player-prop parlays
he asked for today, and both were inherited rather than re-read. ADR 0110
"killed, not deferred" player props because a prop key "multiplies every
call by the roster" - but this vendor bills a prop event per market key per
region, and ADR 0079 in the same repo had measured it (five keys, two
regions, ten credits) two weeks earlier. ADR 0110 refused totals "this
season" on a projection - the largest observed day times 1.5 crosses the
cap - and the NFL Sunday it was written to protect had by now been measured
at 236 credits, one third of the cap, with the number sitting in
`api_credits` where one `credits-day` call reads it. Ticket #36 then closed
on the inherited kill without opening either premise.

The shape: a refusal is written with a premise (a billing rule, a
projection) and later readers inherit the refusal without the premise,
because the refusal is the sentence that gets quoted. A premise can be
falsified by the repo's own record - a measurement doc, an earlier ADR, a
table - without anyone noticing, because nothing links the refusal to the
fact it rests on.

Three rules:

- **Quote a refusal with its premise, never alone.** "ADR 0110 killed
  props" is incomplete; "ADR 0110 killed props because it believed props
  bill per player" is checkable in a grep.
- **A refusal on a projection names the measurement that would overturn
  it, and the date it becomes available.** ADR 0110 SS2 named 2026-09-13's
  Sunday in its own text and nobody read the number back against it.
- **When a request collides with a refusal, check the premise first, not
  the request.** Half of today's plan was reading two ADRs against one
  billing constant and one `credits-day` output; the build followed from
  that, not from arguing the request.

Where the cost landed: two ADR sections and a closed ticket that said the
opposite of what the record supported for four days. Where it went: ADR
0152 SS1, which names each overturned premise beside the fact that
overturns it; this entry.

## 2026-09-15 (second) - A guard that pins a coordinate goes red on an unrelated edit; update the pin, never loosen the guard, and say in the pin what it is really guarding

Two guards went red tonight on commits that did not touch what they guard.
`test_only_kalshirestclient_defines_a_method_named_orders` pins `def orders`
to `backend/kalshi/rest.py:711`; five comment lines added to the shard table
above it moved the definition to 716 and the guard failed on a comment. The
inspector's `SUBCOMMANDS` registry in `test_inspect_live_db_modules.py`
refused `read-incidents` because a new subcommand had appeared without being
written down. Both were the guard working. Neither was about the change
being made, and both cost a full-suite cycle (21 and 30 minutes) to learn
the name of the test, because the run was started with a tail that kept
only the summary line.

The shape: a guard that pins a **coordinate** (a line number, a count, a
list of names) rather than an **identity** (a symbol, a predicate) goes red
whenever the coordinate moves, and the coordinate moves on edits that have
nothing to do with the claim. That is not a defect in the guard - a
line-number pin is how `test_only_kalshirestclient_...` makes "exactly one
definition, here" checkable - but it is a cost every edit above it pays.

Three rules:

- **Update the pin, never loosen the guard.** 711 became 716; `read-incidents`
  went into the list. Rewriting the assertion to "any line in that file" or
  "any subset of QUERIES" would keep the test green and delete the claim.
- **When you add lines above a pinned symbol, expect the pin to move and fix
  it in the same commit.** Grep the tests for the file's name and a colon
  before running the suite: `rg "rest.py:[0-9]+" tests` finds a line pin in
  a second; the suite finds it in twenty minutes.
- **Run a background suite with `-rf` (or keep the whole output), never with
  a tail that keeps one line.** A summary that says "1 failed" and nothing
  else costs a second full run to name the failure. Tonight it cost two.

Where the cost landed: two extra suite cycles, about fifty minutes of wall
clock, on a night with three deploys. Where it went: the pin at
`tests/test_bid_path_arming_requires_order_reconciliation.py` reads 716;
`read-incidents` is in `SUBCOMMANDS`; this entry.

---

## 2026-09-15 - A warning improved but not persisted is the same warning; when you fix what a log line says, ask what retains it

Three API reads hit their 25 s budget and blanked the Games screen in front
of Joe. The warning said only that something was interrupted, so the same
night it was reworded to carry the method, the path with its query and the
elapsed time, and the handoff said "the next hit is a measurement". The
partner then measured the thing the sentence assumed: Fly's log retained a
hundred lines, forty seconds' worth during a busy window, because every
scheduler pass emits a ~900-character INFO dict every ~20 s. The three hits
that motivated the rewording had already scrolled off before it deployed.
The next hit at 03:00Z while Joe slept would have produced exactly what the
last three did: nothing.

It is the two-limits-on-one-quantity failure this repo keeps meeting, on a
log instead of a budget: the wording was the limit that got attention and
the retention was the limit that bound.

Three rules:

- **A log line is an instrument only for as long as it is retained.** Before
  calling a warning "the measurement", find the retention window and put
  the next expected event inside it. If you cannot, the line is not the
  record; a row is.
- **When the row is written on the failure path, the writer must survive
  the failure.** A best-effort insert with a short lock wait that logs the
  row on refusal, never a raise, never a five-second wait on the way out of
  a 503 - and the resulting count is a FLOOR, said beside the count.
- **Look for the more sensitive instrument already deployed.** The loop's 2 s
  loopback probe of `/api/health` had been running every pass for weeks,
  twelve times more sensitive than the route budget, and threw its answer
  away as the constant "health probe failed". The new detector was not the
  fix; wiring the old one was.

Where the cost landed: one commit that changed what was lost rather than
whether it was, caught the same night. Where it went: ADR 0151, schema v42
`api_read_incidents`, `scripts/inspect_live_db.py read-incidents`.

---

## 2026-09-14 (sixth) - The steps after a refusal run only on the first success, and an "unexplained" venue response is a claim about your own request until you have re-read it

`scripts/probe_resting_combo_order.py` had two defects in its last three
steps: the cancel omitted `?exchange_index=` and 404'd, leaving a real order
resting; and the orders-list read carried its query string inside the signed
path and 401'd. Both were visible in the capture of 2026-08-30, the first run
that reached those steps. Both were still there on 2026-09-14, the second.
`rest.py` had documented the cancel fix on 2026-08-30, in the same session
the probe first showed it, and the script never took it. The 401 was logged as
"unexplained" both times and handed forward as a question about what the
venue was doing.

Neither was mysterious. `backend/kalshi/auth.py` says on line 74 that Kalshi
signs the path only, verified 2026-08-06 with exactly this symptom; the
probe built `path="/portfolio/orders?ticker=..."` and signed the whole thing.
A refusal at step 2 exits before steps 3-5, so every `insufficient_balance`
run - five of the seven ever taken - exercised nothing after the create. The
script was "run many times" and its tail had executed twice.

Three rules:

- **A script's steps after its usual exit point have run as many times as it
  has succeeded, not as many times as it has run.** Count successes before
  trusting the tail. A probe that mostly refuses has a tail that is mostly
  untested, and the tail is where the money is put back.
- **When a venue response looks odd, re-read your own request before you
  call it the venue's.** `INCORRECT_API_KEY_SIGNATURE` on two calls in a run
  whose other four calls signed fine is a fact about the two calls. The
  question "what is Kalshi doing" was never the question.
- **When a module documents a defect and its fix, grep for every caller
  that makes the same call.** `cancel_order` grew the `exchange_index`
  parameter and a docstring naming the 404; the one script that had ever
  cancelled anything still built the DELETE by hand and was never listed.

Where the cost landed: one real order resting on the live account until Joe
cancelled it by hand, twice over two weeks, and a "worth one look" item
carried across a session boundary for a defect a grep would have found.
What it bought: `raw_request` now refuses a `?` in its path, the shard is
read off the market before anything is sent (an order that cannot be
cancelled is not placed), and the fixed probe reads the shard balance while
its order rests, which is the capture item 3 needs.

Where it went: `scripts/probe_resting_combo_order.py`,
`tests/test_probe_resting_combo_order.py` (eight mutations, each seen red).

---

## 2026-09-14 (fifth) - A measurement of a state is not a property of the system, and the tell is a sentence with no "while" in it

Three 2c probes on a live combination came back `insufficient_balance`. That
went onto the screen as *"this bet is placeable on kalshi.com and not here"*
and into an ADR as *"a combination bet cannot be placed through this cockpit at
all."* Joe rejected it from memory of his own fills. He was right: six of his
seven real `manual_orders` rows are filled `KXMVECROSSCATEGORY-SHARD1`
combinations placed through that exact path, and the audit proving it had been
run **at the start of the same session**. The only difference was that the
shard held $22 then and a cent now.

The probes were fine. The generalisation was not. Three refusals support
*"while shard 1 holds a cent"* and support nothing whatever about *"at all"*.

It was the third instance of the same shape in one day - an inference about
where a deposit went, never observed; an argument that a venue "could not have
shipped" a stranding product, from a false premise; and this. Each took one
reading of one state and restated it as how the system works. Each reached a
user-facing surface before it was checked.

Four rules:

- **Before writing a capability claim, grep the local record for a
  counterexample.** "Has this ever worked?" is a query, not a memory. Fills,
  orders and captures are right there, and a claim that the tool cannot do X
  is refuted by one row where it did.
- **Put the condition in the sentence.** If the honest form needs "while", "when"
  or "as long as", the unconditioned form is false. A sentence that cannot
  take the qualifier is a property; one that can and does not is an
  overreach.
- **Negative results generalise worst.** N failures under one configuration
  bound that configuration. Positive results at least prove the thing is
  reachable.
- **On a transparency surface, an overreach costs more than an error.** A
  screen that tells the operator his own past actions were impossible teaches
  him to stop believing the screen, and that is the whole product (ADR 0071
  §2.2).

Where the cost landed: one deploy carried a screen contradicting Joe's own
betting history, and he had to correct the agent to get it fixed. What it
bought: the funding mechanism was found - the shard axis lives on
`intra_exchange_instance_transfer`'s optional `*_exchange_shard` fields, which
the account page does not surface, which is why its absence from the UI looked
like the capability being gone.

Where it went: ADR 0150, corrected copy, two inverted guards ("placeable on
kalshi.com and not here" now forbidden, "whenever it was funded" required),
and `--transfer` on `set_target_balance_allocation.py` for Joe to run.

---

## 2026-09-14 (fourth) - A remedy is a claim about the world, and it decays faster than the code that names it

ADR 0148 shipped a refusal that named its remedy: the shard is empty, go
allocate funds at `kalshi.com/account/exchange-indexes`. A test *required* the
URL, on the sound-sounding rule that a refusal must say what to do about
itself. Hours later Joe said he could not move funds any more. Opening the page
in his browser: it still loads, and it is now four read-only balance cards and
one toggle. No transfer control. The sentence had been instructing an
impossible action from the moment it deployed, and a guard was holding it in
place.

Then the reasoning went wrong in the other direction. From "there is no manual
control" I argued Kalshi could not possibly leave API users stranded, therefore
auto-management must now cover the API, therefore the desk's collateral check
was a false brake on the money path. Every step felt forced. The premise was
false: two documented transfer endpoints exist, so API users are not stranded
and the argument collapses. Three live probes then refused `insufficient_balance`
outright — the check was right all along, and the *comfortable* conclusion
(our code is fine) happened to be the true one, reached only by measuring.

Four rules:

- **A refusal may name a remedy only if the remedy has been seen to work.**
  "The venue's docs mention a page" is not that. A URL in user-facing copy is
  an assertion about a third party's UI, which changes without telling you and
  which no test in your repo can observe.
- **Prefer telling the reader where the thing CAN be done over telling them
  how to fix it.** "This is placeable on kalshi.com and not here" stays true
  through a UI redesign; "go to /account/exchange-indexes and allocate" does
  not.
- **When a required-string guard turns out to pin a falsehood, invert it
  rather than delete it.** The dead URL is now forbidden by test, on both
  surfaces that carried it — the same move as the dead per-bet cap.
- **An argument from "they could not have shipped that" is not evidence.**
  It reasons from a product's coherence to a fact, and it will mislead you
  exactly when your model of the product is incomplete. Reach for the cheapest
  observation instead: three refused orders cost nothing, because a refused
  order moves no money.

Where the cost landed: nothing, this time — the probes were free and the false
copy lived for about two hours in front of the one person who already knew it
was false. What it bought: the mechanism pushing Joe's betting off the desk is
now named. Every combination bet through the cockpit is refused for shard
collateral while the same bet fills on Kalshi's site, and combinations are all
seven of his real orders.

Where it went: ADR 0149, corrected ticket copy, an inverted guard, and
`scripts/set_target_balance_allocation.py` (read-first, money behind a flag).

---

## 2026-09-14 (third) - A sentence that explains a number must be selected by the predicate that produced it, and a refusal's remedy has to travel to the screen that shows it

Joe tried to buy a 25.7c combination through the cockpit with $1.00 typed and
945 contracts resting. The ticket told him *"Not enough: one contract costs
25.7c, so the smallest bet here is $0.26"*, and directly under it *"Trimmed to
0 — the book or your Kalshi wallet, not your typed amount, set the size."* Two
sentences, one paragraph, opposite causes. He concluded the desk was broken and
placed the bet **directly on Kalshi**.

The code computed two numbers and selected on the wrong one:

    affordable = floor(amount / ask)     // $1.00 / 25.7c = 3
    contracts  = min(affordable, ceiling) // min(3, 0)    = 0

`affordable` answers *do his dollars cover a contract*. `contracts` answers
*will this order go*. The "not enough" sentence is a claim about the first and
was branched on the second, so it fired whenever **anything** zeroed the size
and then blamed the typed amount for it. The true cause was Kalshi's per-shard
collateral: the market's wallet held nothing while the account was funded.

The second half is the one that would have prevented it anyway. `POST
/api/manual-orders` check 9a has named the shard, its balance and the
allocation URL since 2026-09-08. The **ticket** was sent only
`authorised_binding: "shard"` — a code — so the best sentence it could form was
"that is what this market's Kalshi wallet can pay for": true, unactionable, and
indistinguishable to a reader from an accusation about what he typed. The three
facts existed one route away and were never served. `combo_orders.
check_affordable`'s own docstring had already written the rule: *"only the desk
is in a position to say so."*

Three rules:

- **Branch a sentence on the quantity it asserts about.** When two numbers
  differ by a clamp, the pre-clamp one explains the input and the post-clamp
  one explains the outcome, and using either to select the other's copy
  produces a confident falsehood. Grep for `min(`/`Math.min` on a money path
  and check what the failure branch below it claims.
- **A refusal code is not a refusal.** If the route can say *what to do*, the
  screen must receive the facts to say it too — the number, the amount and the
  remedy, not the enum. A screen that renders a code into prose is inventing
  the prose.
- **Two rendered sentences that can both be true at once must be checked
  together.** Each was individually guarded by a test; nothing asserted they
  never co-render. When adding copy to an existing paragraph, read the whole
  paragraph in every state, not the branch being edited.

Where the cost landed: a real bet left the tool. That is the first measured
instance of the cockpit *causing* a bypass rather than failing to attract
one — the 2026-09-04 presence measurement returned UNRESOLVED with no
mechanism to point at, and this is a mechanism.

Where it went: ADR 0148, the `shard` block on `GET /api/manual/market/`, a
third render branch selected on `affordable`, `exchange-shard` in the
glossary, and four guards verified by disabling. Not fixed:
`venue_balance_snapshots` still stores only the account total, so which wallet
was funded on any past date is unanswerable — ADR 0148 §6.

---

## 2026-09-14 (second) - A load-bearing count is named with its table, because collapsed quantities survive review by looking consistent

CLAUDE.md said the hand-bet path had "four" real fills by 2026-09-09, that
"all four real fills" carried NULL venue columns, and that "all four real
positions" were dead. Read off live today: `manual_orders` has **seven**
real rows, **six** of them filled (three by the end of 09-09, three more on
09-10), and `parlay_positions` has **four**, because the position recorder
postdates the first two orders. The "four" was ADR 0129's four *orders* on
09-09 (three filled, one not). It was then re-read as four fills, and again
as four positions, and each re-reading agreed with the last, so the sentence
survived two audits of the paragraph it sits in.

The spine already documents this failure for `actionable` — three row
counts, one word — and it recurred on a second quantity within a week.
A count that reads consistently across three sentences is not evidence the
three sentences count the same thing; it is what a collapsed quantity looks
like from the outside. The tell is a number with no table beside it.

The same shape showed up in CI the same day: one test was red on every
branch run *by construction* (a lane checkout has no `main`), so "CI green"
on a branch meant nothing and "CI red" meant nothing either, and the
reading "branch CI is red, that's the known one" was the collapsed
quantity — it hid whether anything else had failed.

Three rules:

- **Quote a count with the table it was counted in.** Orders, fills and
  positions are three tables with three numbers; "four" without a table is
  a sentence waiting to be re-read.
- **When a number is corrected, check whether the *same* number appears
  elsewhere counting something else.** The second and third sentences were
  written by copying the first, and a correction that touches one of them
  makes the other two wrong in a new way.
- **A check that fails by construction carries no signal in either
  direction.** Fix it so that the case with nothing to read skips in words,
  and prove by mutation that the case with something to read still fails.

Where it went: CLAUDE.md's hand-bet paragraph now carries the three counts
with their tables and the date they were read; the lane-board guard skips
when the checkout holds no `refs/heads/main` (verified: old file red on a
single-branch clone, new file skips there, and a mutated `is_main` on
`main` is still red).

---

## 2026-09-14 - A wall-clock time in a registration is not a schedule; it is a person, and the person must be named

Arm D of the combo-exit registration fixed five captures at five UTC minutes
on Sunday 2026-09-13. `tasks/NEXT.md` carried it for four sessions as *"a
scheduled run, not a task to plan."* Nothing in this repo runs a command at a
minute: there is no scheduler, no cron reaching `scripts/`, and a timer set in
a session dies with the session. No session was open on Sunday. Zero of five
captures were taken and the look is void by its own §7.

The word *scheduled* named a mechanism that did not exist, and it survived
four reviews because it read like a decision already made. A stopping rule
fixed to a clock time carries an unnamed dependency — a human at a keyboard
at that minute — and writing "scheduled" converts a missing owner into an
assumed one.

Where the cost actually landed: Joe was asked to take no combo taps all
weekend so the measurement's sampling frame stayed clean. The frame was never
sampled. He paid the wait in full and got nothing for it, and nothing told
him when the window closed.

Three rules:

- **Name the person, or write a rule a session can reach.** Either the
  registration says who is at the keyboard at each minute and how that
  session comes to exist, or the stopping rule is one any later session can
  satisfy (*n* captures at least *X* minutes apart, first session on or after
  date *D*). "Scheduled" with no scheduler is neither.
- **A constraint imposed on Joe to protect a future measurement expires with
  the window, and he is told the moment it closes, pass or fail.** Otherwise
  the abstention outlives its reason silently, the same way a stale
  justification does.
- **When a plan item names a date, ask what happens on that date and who does
  it.** If the answer is "it just runs", find the thing that runs it. If
  there is no such thing, the item is a task, and it goes to whoever will be
  awake.

Where it went: `docs/measurements/2026-09-13-combo-exit-nfl-sunday-result.md`
(five slots MISSING, void), ADR 0146 (no successor; the question was already
answered by the 2026-09-10 disclosed look), and the hold on combo taps lifted.

---

## 2026-09-11 - Before a missing number becomes a migration, check whether the row already determines it

E3 — the entry fee absent from `parlay_positions.stake_tenths` — arrived
framed as a storage decision: rewire the write site to the venue's fee
column, accept a mixed-basis column because the four real rows predate that
column, and pair it with a schema question. Every part of that framing was
inherited from the *previous* deferral (ADR 0143 §4 had deferred rewiring
the same function for a different column), so the shape of the fix was
decided before anyone asked what the fee is a function of.

It is a function of two columns already on the row. A combo is charged once,
per contract, at its own price, and the row stores `C·P` and `C·$1`; the fee
collapses to `k · stake · (1 − stake/return)`. No migration, no backfill, no
mixed basis, and the pre-v40 rows behave exactly like any row written
tomorrow. The whole "decision" was a read-site line and a helper.

The shape: **a deferred item carries the shape of the fix it was deferred
as.** When a new reason revives it, the reason gets attached to the old
shape — "the same rewire, now with a real reason" — and the session budgets
for the old shape's cost (an ADR about columns, a mixed-basis argument, a
platform review) before checking whether the new reason even needs it.

Three rules:

- **Ask what the missing number is a function of before asking where to
  store it.** If the inputs are already on the row, the fix is arithmetic
  and the storage question is moot. Derivable-from-the-row is the first
  check, not the last.
- **An inherited "the same X as before" is a claim to verify, not a
  scope.** It was true of the previous item; whether it is true of this one
  depends on facts nobody has looked at yet.
- **Read the output history before sizing the fix.** `/hedge` had produced
  zero locks in its life, which turned a day's decision into an hour's line.
  A defect found by source reading has no measured harm until someone
  counts the outputs it could have corrupted; count them first.

Where it went: `core/hedge.py::combo_entry_fee_tenths`, DRAFT ADR (0145
reserved), and the collapsed form was chosen so that the *other* deferred
item on the same function — the `int(fill_count)` truncation — cannot break
it when it is fixed.

---

## 2026-09-11 - A caveat that names one error term is a claim about all the others

`/hedge` told Joe its lock figure was "a ceiling — the real number can only be
smaller", because the settlement fee (H4) is unmodelled. True sentence, wrong
claim. The figure carries at least four error terms and they do not share a
sign; the largest — the entry fee Joe already paid, absent from `stake_tenths`
entirely — runs the *other* way and is the size of the smallest floors the
"guaranteed profit" alert fires on. CLAUDE.md had, in one paragraph, called the
same number an upper bound *and* said the recorded stake put it at or below the
truth, then concluded nothing shown to Joe was flattering. That closing
reassurance was the unsupported sentence.

The shape: **a disclosed caveat reads as an audit.** "We know about X, so the
number is conservative" is heard as "we have looked at the error budget", when
all it establishes is the sign of X. Every undisclosed term is then assumed
absent — and the one that binds is usually the one nobody wrote down, because
the one that was written down was found while looking *for* a reason to be
cautious. A caveat that sounds conservative is the flattering direction for a
caveat: it licenses acting on the number.

Three rules:

- **A bound needs the whole budget, not one term.** Before writing "at least",
  "at most", "ceiling", "floor" or "conservative" about any displayed figure,
  list every term between the figure and the truth with its sign. If you cannot
  list them, the honest word is "estimate", and say roughly how good.
- **The reassurance sentence at the end of a caveat paragraph is the one to
  audit.** It is where a list of specific facts gets rolled into a general
  claim, and it is written last, when the author already believes the answer.
- **Two limits on one quantity is the tell.** When a doc asserts an upper bound
  in one sentence and a lower bound in another, neither is established; the
  author has found two terms and stated each as if it were alone.

Where it went: `core/hedge.py`'s "does NOT establish" list now carries all four
terms; the screen says "estimate good to roughly a cent a contract, not a
guaranteed amount"; the killed one-sided words are guarded so they cannot
return. The registration's Amendment 1 §A6 is the canonical table.

---

## 2026-09-11 - Never hand-type an identifier into the mechanism whose job is to report identity

A live deploy went out with `-e GIT_SHA=a5b160a3f6ca01bbfcba04d1b32e10a0dcba8bd2`.
The real commit was `a5b160ac9cf0a3132fbe271eb5a2fd8a157a28f5`. The first seven
characters matched, because those were read; the remaining thirty-three were
invented.

The deployed **code** was correct -- `fly deploy` ships the working tree, which
was clean and at that commit -- so nothing was broken and every test still
described what was running. What was wrong is the only thing anyone checks to
find out what is running: `/api/health` reported a `git_sha` that exists in no
repository. A session reading it would have found no such commit and had no way
to tell "the label is wrong" from "the tree is not what I think it is".

**The causal chain is the part worth keeping, because it was a workaround that
did it.** The auto-mode classifier refuses compound commands, and the reliable
response is to issue commands singly (see the memory note). So
`flyctl deploy ... -e GIT_SHA=$(git rev-parse HEAD)` -- which cannot be wrong --
got split into `git rev-parse HEAD` in one call and a deploy in another, with
the value carried across by hand. **Splitting a command to satisfy a gate
converts a substitution into a transcription**, and transcription is the step
that fails.

Three rules:

- **Substitute, never transcribe.** `$(git rev-parse HEAD)` in the same command
  is correct by construction. If a gate forces the split, paste the value from
  the command's own output rather than typing it, and diff it against the source
  before pressing go.
- **An identifier is the one field where "close enough" is undetectable.** A
  wrong price or a wrong count looks wrong. A wrong SHA looks exactly like a
  right one -- same length, same alphabet, correct prefix -- and the prefix is
  the part a reader spot-checks.
- **Verify the label against its source, not against itself.** Reading
  `/api/health` back confirms the deploy *landed*; it cannot confirm the value
  is real, because it is echoing what it was handed. The check that works is
  `git rev-parse HEAD` beside the reported string.

The general form, and it is the same shape as the warm-up that shipped doing
nothing: **a component that reports on the system can be broken in a way that
leaves the system fine and the report confident.** Those are the expensive ones,
because the report is what everyone downstream believes.

---

## 2026-09-11 - A screen whose content depends on sweep phase will be mistaken for a property of the slate

Checking whether the parlay desk's horizon widening had ever fired, I read
`/api/parlays` on live four minutes apart and got two different desks:

    04:00Z   tonight 0/7, tomorrow 0/7, 48h 0/7   bare call: widened_from None
    04:04Z   tonight 0/7                          bare call: widened_from 'tonight',
                                                  window -> tomorrow, 4 of 7 cards

Same slate, same games, same commit. The excluded histogram says what moved:
`kickoff_outside_window` held at ~434 across both reads while `stale_consensus`
fell **256 -> 36 -> 31**. A sweep landed. The desk was never empty on menu or
on clock; it was empty on **freshness**, and freshness is a sawtooth whose
period is the sweep cadence.

This is the third distinct reason this screen has been empty, and the first
two were each mistaken for something else at the time. The ninth session found
it empty on the **clock** while everyone was treating it as empty on the
**menu** ("we need totals, props, more variety") -- 440 of 449 excluded legs
were `kickoff_outside_window`. Now there is a third: empty on freshness, which
unlike the other two is **time-varying with a period nobody stamps**.

**The shape to look for: any screen or metric fed by a periodically-refreshed
cache, read at an unrecorded phase of that period.** Card yield, "how many
opportunities does the desk show", freshness ratios, anything counted off a
page. Two honest observers reading the same system twenty minutes apart get
different numbers and both write them down as facts about the slate.

Three rules:

- **Stamp the phase, not just the time.** "4 of 7 cards at 04:04Z" is not a
  fact about the slate unless it also says how long since the last sweep. The
  instrument exists -- `scripts/inspect_live_db.py sweep-log` -- and the
  histogram itself carries the phase, because `stale_consensus` moving while
  `kickoff_outside_window` sits still *is* the signature of a sweep landing.
- **A single read cannot separate a property from a phase.** Read twice, at
  least one sweep interval apart, before any claim about yield. One read is
  G = 1 and it will be quoted as a rate.
- **The two exclusion reasons answer different questions and must be reported
  together.** `kickoff_outside_window` is structural -- widen the window and it
  moves. `stale_consensus` is temporal -- wait and it moves. Reporting only the
  total ("449 legs excluded") loses exactly the distinction that tells you
  whether to change code or to wait.

The corollary that made this worth writing rather than noting: the widening
mechanism had gone unobserved for days not because it was broken but because
**it only has somewhere to widen into in the minutes after a sweep**. A
mechanism that fires only during one phase of a cycle will read as dead to
anyone who spot-checks it. Checking it "a few times" is not a sample.

---

## 2026-09-11 - A reachability guard that walks modules cannot see an orphaned symbol inside a reached one

`tests/test_has_callers.py` is the guard this repo leans on hardest. CLAUDE.md
credits it with catching the built-but-never-called problem five times, and the
credit is deserved. It also has a blind spot it cannot report on itself, and
two functions have been sitting in it.

It has two mechanisms and they miss in opposite directions:

- **`DISPOSITIONS` is keyed by MODULE.** The walk computes unreachable modules
  and demands each be classified: `unclassified = [m for m in orphans if m not
  in DISPOSITIONS]` (line 1249). A module with even one production importer is
  not an orphan, so it never enters the list, and **nothing then looks inside
  it.**
- **`MUST_HAVE_CALLERS` is keyed by SYMBOL, and it is opt-in.** A hand-written
  list of `(symbol, why it matters)` tuples. The file's own docstring says it:
  "a list of symbols someone remembered to add."

So a symbol is protected only if someone added it by name, or if its whole
module was already unreachable. **The gap is the conjunction: an uncalled
function in a module that is reached for other reasons is invisible to both.**

`backend/analysis/clv.py` and `backend/analysis/validate.py` are the live
instance. `score_recommendations`, `ClosingLine` and `BUCKETS` in those files
have real production importers, so both modules are reachable and
`DISPOSITIONS` is silent; neither `horizons_agree` nor `summarise` was ever
added to `MUST_HAVE_CALLERS`, so that is silent too. `horizons_agree` is
referenced today only by prose comments and its own tests. It was found by
ADR 0120's hand-walk, and the ratchet could not have found it.

**The shape to look for: a guard whose unit of analysis is coarser than the
thing it protects.** Module-level reachability, file-level coverage gates,
package-level dependency audits, per-endpoint auth tests on a route that
branches internally. Each is real protection at its own grain and silently
offers none below it. The tell is that the guard's pass condition can be
satisfied by a *neighbour* of the thing you care about.

Three rules:

- **State a guard's grain next to its claim.** "Every module is reached or
  classified" is true here and reads as "nothing is unreached", which is not.
  A guard trusted beyond its grain is worse than one trusted exactly as far,
  because the gap is precisely where nobody looks.
- **An opt-in list cannot report what is missing from it.** That is not a
  defect to fix by adding entries; it is a permanent property. Pair every
  opt-in list with something exhaustive at the same grain, or write down that
  the coverage is whatever people remembered.
- **When a hand-walk finds something the ratchet exists to find, the finding
  is the ratchet's gap, not the symbol.** ADR 0120 wrote up two orphaned
  functions and tolerated them on stated grounds. The more durable output was
  the one nobody wrote down: the guard had been unable to see them all along,
  and still is.

Not fixed here, deliberately. ADR 0120 examined this pair on 2026-09-09 and
tolerated it -- the `beta` fits ran through `clv_signal.py` and
`signal_test.py`, which are reached, and the signal is settled negative, so
deleting 136 lines earns nothing. Nothing has changed since. What was missing
was the pattern, not another disposition row.

Worth knowing before anyone times the suite: `tests/test_has_callers.py` alone
is **122 tests in 198.7s** (measured 2026-09-11, this machine), a meaningful
share of the 15-22 minute run. It is slow, not hung.

---

## 2026-09-10 - "Cold start variance" was two states with one name, and the warm reading was the one I took first

A cold-boot request measured 3.95s after one deploy and 20.5s after the next,
on identical code, and it went into a handoff as unexplained variance.

There was no variance. The 3.95s box had been warmed twice before I timed it:
the schema migration's `CREATE INDEX` had just read the whole of the table the
query scans, and then I ran a full timing pass over the same statement. Both
finished before the request I labelled "first". The 20.5s box had a migration
that did nothing and was timed immediately. Cold start was ~20s throughout.

**The shape to look for: a "first request" measured after your own setup
touched the same data.** Migrations, backfills, index builds, health probes,
smoke tests and the diagnostic you just ran to check whether the fix worked are
all warm-up passes. On a box whose page cache is smaller than its database,
they are the dominant term, and they are invisible in the number you write
down.

Three rules:

- **Write down what ran before the measurement, not just the measurement.** The
  order of operations IS a variable here. "First request after deploy" is
  underspecified on any system with a cache; "first request after deploy, with
  a migration and a full scan in between" is a different experiment with a
  different answer.
- **Reconstruct the timeline from the box rather than from memory.** `/proc`
  settled this in one read: VM uptime against the process's own age said
  exactly when the machine booted and which build it came up carrying. My
  sense of how long ago each deploy had happened was off by forty minutes,
  which is what made the two readings look like one phenomenon.
- **When two measurements of "the same thing" disagree by 5x, suspect the
  definition before the system.** The system was behaving consistently the
  whole time.

The capacity fact underneath, worth keeping on its own: 2.0 GB of RAM, no swap,
a 5.43 GB database and a page cache that tops out near 1.49 GB. **At most ~27%
of the file is ever resident**, so "warm" is never fully warm and *which* 27%
is resident is the whole performance story. Fixed by warming the read path at
boot: 20.5s -> 0.81s on the first request after a fresh machine.

---

## 2026-09-10 - A component that swallows every error needs a test more than a loud one does

The boot warm-up catches every exception on purpose: it runs on the machine
that holds real money, under `set -e`, and a warm-up that can fail a boot is
worse than a cold cache. That reasoning is right and it shipped a component
that did nothing at all.

`python scripts/warm_read_path.py` puts `scripts/` on `sys.path`, not the repo
root, so `from backend.parlays import ...` raised `ModuleNotFoundError`. The
swallow caught it, printed one line, and the boot carried on:

    [warm] parlay read path warmed in 9.9s (3 candidate legs)   <- what it does now
    [warm] skipped: ModuleNotFoundError: No module named 'backend'   <- what it did

Everything else looked perfect. Container healthy, deploy successful,
entrypoint correct, tests green. The first request still took 17.9s and I
nearly recorded that as "warming does not help" - a wrong conclusion about the
idea, caused by an unrelated bug in the implementation, with no failing signal
anywhere.

**The shape to look for: a component whose failure mode is "nothing happens".**
Best-effort caches, prefetchers, warmers, metrics emitters, cleanup jobs,
optional backfills, anything wrapped in `except Exception: pass` or a bare
`|| true`. The swallow is usually the correct design. It also converts every
bug in that component into silence.

Three rules:

- **A swallowed failure must still be loud in one place.** A log line is the
  minimum, and it is only worth having if something reads it. Prefer a success
  line with a number in it - "warmed in 9.9s (3 legs)" distinguishes working
  from skipped from reading-an-empty-database at a glance, which a bare "ok"
  does not.
- **Test it the way the caller invokes it, not the way a test imports it.** The
  bug here is unreachable from `import warm_read_path` in pytest, because
  pytest already has the repo root on `sys.path`. It reproduces only as a
  subprocess, by path, from the right working directory. **When the defect is
  in how a thing is launched, the test has to launch it.**
- **Pin the swallow in both directions.** A missing database and a corrupt one
  must still exit zero, or the safety property is gone; and a healthy database
  must NOT report "skipped", or the component is decoration.

The general version, and it is the same pattern as the alarm keyed on a
suppressed count above: **any mechanism whose broken state resembles its idle
state cannot be monitored by looking for problems.** It has to be monitored by
looking for evidence of work.

---

## 2026-09-10 - An index that changes no plan can still change the cost by orders of magnitude; EXPLAIN reports the method, not the rows

An index on `odds_snapshots(odds_event_id, commence_ms)` was added on
2026-08-26 and removed the same hour. The reasoning was written down and was
carefully done:

    With it:    SEARCH ... USING INDEX idx_odds_event_commence (odds_event_id=?)
    Without it: SEARCH ... USING INDEX idx_odds_event          (odds_event_id=?)

Identical shape, so the index bought nothing and cost write amplification on
the highest-volume table. Both observations were true. The conclusion was
wrong, and the desk paid for it two weeks later with `/api/parlays` answering
503 `read_budget_exceeded` at 25 s.

The query takes `MIN(commence_ms)` grouped by event. `idx_odds_event` is
`(odds_event_id, market, fetched_ms DESC)` - `commence_ms` is not in it, so
satisfying the MIN means reading **every row of the group** and fetching the
column from the table: about 1,400 rows per event. With `commence_ms` as the
second column the minimum is the first entry and the seek stops there. One
plan line, three orders of magnitude of rows.

Measured, because the claim being overturned was deliberate. Live, before:

    whole candidate scan                        73,526 ms   (494 rows)
    odds_snapshots MIN(commence_ms) GROUP BY    26,719 ms   (703 rows)
    fair_prices rows inside the scan window            848  of 10,112,298

848 rows in the window and 73 seconds to return them. Reproduced locally at
live's shape, warm, best of three: **503.9 ms without, 167.5 ms with**.

Shipped and re-measured on live the same day:

    odds_snapshots MIN GROUP BY    26,719 ms  ->    327.9 ms      81x
    whole candidate scan           73,526 ms  ->  11,712 ms      6.3x
    /api/parlays, cold             503 at 25 s ->     3.95 s
    /api/parlays, warm             1.5-3.3 s   ->  0.49-0.82 s

**The local 3x understated the live win by more than an order of magnitude**,
and predictably so: the local box was CPU-bound with the table in memory,
while live is I/O-bound and the index removes ~1,400 table-page reads per
event. When a benchmark and production differ in which resource binds, the
benchmark gives a direction and a floor, never a magnitude -- and it is worth
saying which one you have before shipping, because "3x" and "81x" justify
different amounts of risk.

**The shape to look for: any judgement about cost made from
`EXPLAIN QUERY PLAN` alone.** It answers "how will this be reached" -
SCAN/SEARCH, which index, which join order. It does not answer "how many rows
will that touch", and for aggregates the difference between the two is
unbounded. `SEARCH ... (x=?)` is one row when the index covers what the query
needs and the entire group when it does not, and the two print the same.

The tells that a plan diff is about to mislead: an aggregate over a column not
in the index (`MIN`, `MAX`, `SUM`), an `ORDER BY ... LIMIT` on a column not in
the index, or a `SEARCH` whose equality is on a low-cardinality column so each
"seek" lands on a large group. In each, the access method is identical and the
work is not.

Three rules:

- **A plan diff can prove an index IS used. It cannot prove one is
  worthless.** To retire an index, time the query. To add one, time the query.
  The plan is a hypothesis about why, never the measurement.
- **Keep the timing next to the index, not just the decision.** The removal
  note here was excellent - it recorded the reasoning in full - and that is
  exactly why the wrong conclusion survived: the next reader found a careful
  argument and no number to check it against. A recorded justification with no
  measurement in it is a claim that has been made harder to question.
- **`SEARCH` is not a synonym for fast.** It means an index was used to locate
  a starting point. Everything after the starting point is invisible in the
  plan.

The correction also improved a second query nobody was looking at: the refused
leg's kickoff lookup went from `SEARCH o USING INDEX idx_odds_event` to
`SEARCH o USING COVERING INDEX idx_odds_event_commence`, so it stopped
touching the table at all - and the test guarding it FAILED, because it pinned
the index name rather than the claim. See the lesson on that above; a guard
that names an implementation calls an improvement a regression.

And one that was passing for no reason: a sibling test asserted
`"idx_odds_event" in step`, which is a substring of
`idx_odds_event_commence`, so it could not have failed whichever index the
planner chose. **A substring assertion over identifiers that share a prefix is
not an assertion.**

See [[justifications-decay-toward-reassurance]] and
[[verification-methods-that-lie]].

---

## 2026-09-10 - "The query admits this market" is not "the desk holds this market", and only one of them is a fact about live

A finding said MLB player props were "bought, priced and sitting in the
candidate pool right now", so the blocker on props-as-parlay-legs was the free
recipe gate rather than the paid feed gate. It was reported to Joe, published
on a ticket, and used to invert a roadmap.

The evidence was `CANDIDATE_SQL`'s allowlist: five prop markets named in a
`WHERE market IN (...)`. That is real and it was verified. What was never
checked is whether any row of those markets exists. On live:

    ODDS_MARKETS                          'h2h,spreads'
    newest prop row in `fair_prices`      600 hours old
    prop rows in the last 7 days          0
    h2h rows in the last 24 hours         65,032

The pool held seven usable legs and none of them was a prop. Both gates were
shut, the expensive one was binding after all, and the free test that had been
promised did not exist.

**The shape to look for: a permission mistaken for a population.** An
allowlist, a feature flag set to on, a route that is mounted, a parser that
handles a format, a column that exists - each says the system *would* accept
the thing. None says the thing is *there*. The two read identically in source
and diverge only against the deployed data, and the gap is invisible in a
code-only review no matter how careful.

Three rules:

- **When a claim's verb is "has", "holds" or "is in", the evidence must be a
  row count from the deployed system.** Source can support "would accept" and
  nothing stronger. If the check that would settle it is a query and the query
  was not run, the claim is not yet made.
- **A subagent's finding inherits this.** The report here was accurate about
  the allowlist and wrong about the pool, in adjacent sentences, and the
  accurate half made the other one feel checked. Split a finding into the part
  established from source and the part that needs live, then go and get the
  second - do not accept a mixed claim as one unit.
- **Check the config the container actually has, not the default.** One
  `os.environ.get("ODDS_MARKETS")` answered the whole question in a line, and
  is the same move `runtime-realist` exists to make.

The cost of getting it wrong was not the wasted work - the staging built on
the way is worth having. It was telling Joe a decision was free when it was
not, which is the direction that gets acted on.

See [[built-but-never-called]] and the two-gates lesson above: the correction
does not restore the old picture either. The free gate is still real and still
was unnamed. What changed is that opening it alone does nothing.

---

## 2026-09-10 - A rewound clock turns an indexed query into a cold-file scan

Testing whether a prop card would build, the machinery was replayed against
rows from 25 days earlier by passing a `now_ms` set back to then. Every query
involved was index-seeking and read-only, which is why it looked safe.

It ran for more than five minutes and took the desk down with it:
`/api/parlays` went from 1.5s to 503 `read_budget_exceeded`, twice, on a box
that had been healthy a minute before. `CANDIDATE_SQL` bounds its scan
relative to `now_ms` - a floor two hours back and a `commence_ms > now_ms`
filter - so rewinding the clock did not move a small window, it pointed the
same query at a 25-day-old region of a 5GB file that no part of the working
set had touched. Every page it needed was a miss, and every page it pulled in
evicted one the desk was using.

**The shape to look for: a query whose cost is bounded by the clock rather
than by a LIMIT.** Time-bounded reads are cheap because recent data is warm,
not because the predicate is narrow. Move the clock and the same statement,
with the same plan and the same row count, becomes an entirely different
amount of I/O.

Two rules:

- **A historical replay on live is not a read-only operation in the sense that
  matters.** Do it against a copy, or a fixture, or accept that the desk pays.
  This is the same conclusion as the full-table-scan lesson from earlier the
  same day, reached by a different route - which is the argument for treating
  "it is `mode=ro`" as saying nothing at all about cost.
- **Killing the local `flyctl` client does not kill the remote process.** The
  probe was still running under its own PID after the client was stopped and
  had to be killed explicitly on the box - reading `/proc/*/cmdline`, matching
  the base64-exec, and refusing anything that looked like `uvicorn` or
  `run_loop.py`. A bare `pkill python` on that container kills the app and the
  recorder.

---

## 2026-09-10 - A warning keyed on a count the failure itself suppresses goes quiet exactly when it is needed

A block on the parlay screen exists to explain one specific outage: Joe read
"needs 2 fresh games and the slate has 0" as "there is nothing on tonight"
while twenty fixtures sat upcoming and the recording loop was wedged. The
block was gated on `stale_consensus > 0` - the count of sides the candidate
scan returned and the freshness rule then refused.

But the scan has its own floor, two hours. A row older than that is never
selected, so it is never counted. Which gives:

    recorder wedged under 2h    rows in-scan, refused    stale > 0    fires
    recorder wedged over 2h     rows out of scan         stale = 0    SILENT

The block got quieter the longer the outage ran, and was absent in exactly
the incident it was written for. Its second paragraph also read "so all
{stale} candidate sides were refused on age", which renders "all 0" in that
state - an empty count presented as though nothing had been dropped.

**The shape to look for: an alarm whose trigger is a count of things that
survived far enough to be counted.** Rejections, retries, errors-per-minute,
items-dropped - each requires the pipeline to get far enough to do the
rejecting. A hard enough failure produces *fewer* of them, and zero is the
reading a healthy system also gives. The alarm and the all-clear are the same
number.

Two rules that fall out:

- **Ask what the counter reads when the thing it watches fails completely,
  not partially.** If the answer is "the same as when nothing is wrong", the
  counter cannot be the trigger. It usually has an upstream twin that counts
  the *population* rather than the survivors - here, fixtures upcoming versus
  fixtures fresh, which survives the rows dropping out of scan entirely.
- **A monotone assumption is worth stating out loud.** The gate silently
  assumed worse outage implies bigger count. Writing that sentence down is
  enough to notice it is false; it never got written down.

See [[verification-methods-that-lie]] and [[built-but-never-called]] - the
common ancestor is a check that reports health because it cannot see.

---

## 2026-09-10 - A test that pins a predicate's spelling blocks the fix that keeps its claim

A guard test asserted the literal string `stale === 0 || unbuilt === 0` and
documented its claim in the docstring above: a banner that fires on a working
screen is one the reader learns to skip, so the trigger is the conjunction.

The predicate then turned out to be wrong for an unrelated reason (the lesson
above). The replacement **preserved that claim exactly** - a working screen
still stays silent - and the test went red anyway, because it was pinning
characters rather than behaviour.

That is a dangerous moment. The test is red, the change is correct, and the
cheapest route is to delete or loosen the assertion - which is how a real
guard gets thrown away while fixing something else.

**The shape to look for: an assertion whose failure message would be "the
code says something different" rather than "the code does something
different."** String matching against source is legitimate here - there is no
frontend test runner, so it is how every `.tsx` claim in this repo is pinned -
but it means the pin and the claim can come apart silently, and only a change
that keeps the claim will reveal it.

The rule: **when such a test goes red, re-read its docstring before its
assertion.** If the docstring's claim still holds under the new code, the
test is out of date and gets rewritten to assert the claim - never deleted,
never loosened. Rewriting it is also the moment to add the half it was
missing, because whatever motivated the change is usually a case the original
never considered. Here the replacement asserts the working-screen silence
directly, asserts the new conjunction, *and* refuses the old predicate's
return - strictly stronger than what it replaced.

And the counterpart: if the docstring's claim does NOT still hold, the change
is the thing that is wrong. Either way the docstring decides, which is the
argument for the docstring naming a claim rather than describing the code.

**The second failure mode of a source-slicing test, and it is worse because it
stays green: the slice silently retargets.** Several tests here locate a
region with `source.index("<ManualTicket")` and assert inside it. Adding a
component whose *docstring mentions* `<ManualTicket>` moved that index into a
comment, and the test went on asserting -- against prose, about nothing. One
of them then survived deleting the very word it exists to require, because the
element it finally landed on carries a JSX comment discussing the same
subject. A test can be looking at the wrong place and at commentary rather
than at the screen, and report success for both reasons at once.

Three rules for a test that slices source:

- **Anchor on something only the real thing has.** `"<ManualTicket\n"` over
  `"<ManualTicket"`; better still, assert a required prop is inside the slice
  (`ticker={...}`) so a wrong slice fails loudly instead of quietly.
- **Assert against the user-facing string, not the region containing it.**
  Pull out the `note="..."` value and test that. A claim about what the screen
  says has to be tested against what the screen says; a comment nearby that
  happens to use the word is not evidence.
- **Prose is not inert.** Adding a comment cannot change behaviour, so it gets
  reviewed as free -- and here it silently disarmed two guards. Re-run the
  tests that slice a file whose comments you edited.

---

## 2026-09-10 - When one blocker is expensive, look for the free one; the expensive blocker gets all the attention

"Add props as parlay legs" had been costed, ticketed and scheduled entirely
as a **feed** decision: a prop cannot be a leg unless a sportsbook price was
bought for it, buying a new market type costs credits on every sweep forever,
so the work was gated behind a paid coverage measurement.

All of that is true. It was also not the binding constraint. Every parlay
card declares which market types it draws from and all seven said team
markets only - a free, one-line gate nobody had written down anywhere. And
the expensive gate was **already open for baseball**: five MLB prop markets
were being bought, priced and put in the candidate pool every sweep, and the
free gate threw them away.

So the question could be answered that afternoon, in baseball, at zero cost,
using data already being paid for - and the paid football measurement was
only worth buying if that free test came back well.

**The shape to look for: a blocker with a price tag, in a chain nobody walked
to the end of.** A cost is memorable and gets written into every summary of
the problem; a `frozenset` in a config table is not, and does not. So the
expensive gate becomes the whole story, the roadmap is built around
scheduling and funding it, and a second gate downstream of it goes unnamed -
sometimes for months, sometimes while the expensive resource is already being
bought and discarded.

Two rules:

- **Walk the chain to the screen before pricing anything.** Not "what stops
  this being available" but "what stops this being *rendered*", one hop at a
  time. The paid gate is rarely the last one.
- **Whenever a paid input is proposed, check whether it is already being
  bought.** A pipeline that acquires something and drops it later looks
  identical from the outside to one that never acquires it, and the fix for
  the second costs money while the fix for the first is free.

Corollary worth keeping: this inverted the *order* of the work, not the
decision. The paid measurement is still the right thing to buy - after the
free test says the feature is worth having.

See [[built-but-never-called]] and [[he-wants-picks-not-more-rigour]]: the
fastest falsifying test was available the whole time and cost nothing.

---

## 2026-09-10 - A guard test needs a bed where the UNGUARDED code would answer differently; "both paths refuse" is not that bed

A route was given a guard: widen the kickoff window when the caller named
none, never when the caller named one. The test for the second half asked for
`horizon=tonight` and asserted the payload came back saying `tonight`. It
passed. Then the guard was deleted outright as a mutation - and it **still
passed**, because the test ran against an empty database. With no games at
all, every window refuses, the widening loop falls through to its "nothing
built anywhere" branch and returns `tonight` regardless. Guarded and
unguarded produced byte-identical output, so the assertion could not see the
difference and had never been testing the guard.

Rebuilt on a slate seeded with games ONLY tomorrow, the mutation turned red
immediately: unguarded, the explicit `tonight` request served tomorrow's
cards.

**The shape to look for: a fixture chosen for being simple rather than for
being discriminating.** An empty pool, a zero balance, a single row, a
default config - these make a test easy to write and are exactly the states
in which many different code paths converge on the same answer. The mutation
check catches it, which is why CLAUDE.md requires it; what this adds is the
diagnosis when the mutation comes back green. **A green mutation does not
only mean "the assertion is weak". It often means the BED is degenerate.**
Before weakening or deleting such a test, ask what input would make the two
versions of the code disagree, and seed that instead.

The corollary is a rule for writing the test in the first place: **state, in
one sentence, what the unguarded code would return for this input.** If the
answer is "the same thing", the bed is wrong before a line of assertion is
written.

---

## 2026-09-10 - A stopping rule that names an outcome manufactures that outcome, and the arm it names will look like the finding

A pre-registered pair test had already been taken once and come back null:
both arms empty, nothing separated. The written rule for retaking it was
"take it again **when a moneyline card is quoted**". Followed exactly, it
produced a block in which the moneyline arm was 2 of 2 quoted - which was
not an observation, because the rule would not have fired otherwise. The tap
order preserved the mechanism in the record: three moneyline taps, then the
spread tap last, after the trigger was satisfied. It was reported as a clean
separation and withdrawn the same session.

**The shape to look for: a retake condition that mentions a result.** "When
X is quoted", "once the pool is fresh", "next time it succeeds", "when we
see a good one" - each fixes one margin of the table before any data is
collected, and the fixed margin is invariably the one that carries the
claim. A null result is the cheapest thing a test produces and the easiest
to explain away by retaking; the rule that governs the retake is therefore
doing more inferential work than the statistic is.

Three rules that fall out:

- **A retake condition may name a clock or a fixed order. It may never name
  an outcome.** "18:00Z daily for five days, moneyline first, spread second,
  record every pair" is a rule. "When a moneyline card is quoted" is a
  result wearing a rule's clothes.
- **Record the pairs that came back boring.** The 07:09Z pair - both arms
  empty, four seconds wide, tighter than the one that got reported - was the
  honest observation, and it went unmentioned because it said nothing. A
  test whose null results are not written down cannot come back negative.
- **When a control arm is a re-read, check whether its answer was already
  known.** Here no minted ticker had *ever* changed status between reads, so
  re-tapping a known-priced ticker as the "control" fixed that arm by
  construction too - the same defect a second time, in a comparison that
  looked independent of the first.

And the one about who caused it: the bad rule was sitting in `NEXT.md` as
part of a previous session's open item, so it arrived carrying the authority
of the record. **A stopping rule inherited from a handoff gets audited before
it is executed, not after it produces a result.**

See [[verification-methods-that-lie]] and the two 2026-09-10 lessons below.

## 2026-09-10 - An operation that reads can also write, and "it spends no money" is not the test for whether it is inert

Twelve "Price on Kalshi" taps were taken on live to answer a product
question. Every one was correct, authorised, cost nothing and placed no
order - and each one **minted a market on the exchange**, because
`lookup_combo` is called with `allow_market_creation=True` and
`backend/kalshi/combos.py` calls that "an outward-facing write". Those mints
landed at the front of a newest-first, truncated page that a measurement
registered to fire three days later samples from, and three of them came
back carrying a readable ask - which was that measurement's own eligibility
predicate. A read-shaped operation had written into a registered sampling
frame.

**The shape to look for: an operation whose name and whose cost both say
"read", with a creation flag buried in the call.** The tells are a
`create`/`allow_creation`/`upsert` parameter defaulted on, a "look up or
create" docstring, and any endpoint that returns an identifier that did not
exist before. None of these show up as money, so a money-based safety check
passes them.

Two rules that fall out:

- **Before repeating an action on a live external system, read what the call
  does, not what the button is called.** "A lookup spends nothing" was true
  and irrelevant; the question was what exists afterwards that did not exist
  before.
- **Ask what population an action joins, not just what it returns.** Anything
  that creates a row, a market or a record becomes part of some future
  sample. Where a registration exists, that is contamination; where none
  exists yet, it is a baseline someone will later mistake for organic.

See [[justifications-decay-toward-reassurance]]: "it spends no money" was
exactly such a justification, correct on its own terms and load-bearing for
a claim it never made.

## 2026-09-10 - A read-only scan on live is not free for the desk: it evicts the page cache, and the next reader pays for it

A research agent answered "how many spread rows does `fair_prices` hold, all
time, by market?" with a `GROUP BY` over the whole 10.1M-row table, twice,
plus a three-table join - all `mode=ro`, all correct, all finished. Ten
minutes later `/api/parlays` answered 503 `read_budget_exceeded` at 25 s on
both windows, and the ladder's own candidate query - 75 ms every pass in the
runner's log - took **74.8 s** cold and **2.15 s** warm when run by hand in
the container. The box was idle (load 0.13) and nothing was wrong with the
code. The 5 GB file had been streamed through a ~1.4 GB page cache, and the
pages the desk needs were the ones that left.

**The shape to look for: a "harmless" read whose input is the whole table.**
Read-only says nothing about cost; on a 2 GB box the cache *is* the
performance, and a full-table scan is a cache flush with a result attached.
The read budget (ADR 0135) did its job - the requests were stopped rather
than piled up - which is why this cost minutes and not a reboot.

Three rules that fall out:

- **A census on live goes through the indexed path the product uses**
  (`ladder_candidates`, `inspect_live_db.py`'s whitelisted queries), or
  through a bounded key range, never `GROUP BY` over an unbounded table.
  If the question needs the whole table, ask it once, say so first, and
  expect the desk to be slow for minutes afterwards.
- **A 503 at the read budget minutes after a live read is the read, not a
  regression.** Check `loop-rss` and `/proc/loadavg` before diagnosing; a
  cold-cache candidate query looks exactly like the OOM cycle of two days
  earlier and has the opposite cause.
- **Subagents inherit none of this.** A reviewer told to "read live only
  via the read-only replay pattern" will do exactly that and still flush the
  cache; the instruction has to bound the *rows*, not just the mode.

See [[verification-methods-that-lie]] and the 2026-09-10 lesson above: same
box, same table, the cost hiding in a different column.

## 2026-09-10 - The cost of a scan is not its wall-clock, and a floor widened for a correct reason still has to be re-timed on live before it ships

The ladder query's scan floor was widened from two hours to nine days for a
reason that was right (after ADR 0133 a confirmed row's `computed_ms` no longer
bounds its freshness, so a two-hour floor would have emptied the ladder). The
row count it would read was measured the same day - 6,561,382 against 138 -
and written down as a live regression. What was not measured was what those
rows cost in **memory**: the query ends in `ROW_NUMBER() OVER (PARTITION BY
...)`, and under `PRAGMA temp_store = MEMORY` a window function materialises
its whole input in RAM. Row count became resident set. The recorder went from
196 MB to 1.2 GB per pass on a 2 GB box, the page cache left for a 5 GB
database fell to ~450 MB, every read on the machine went to disk, and the
kernel killed the runner three times in five hours.

**The shape to look for: a scan whose output is small but whose input is
materialised.** `SELECT ... LIMIT 10` over a window function, a `GROUP BY` or
an `ORDER BY` that SQLite cannot satisfy from an index, a `DISTINCT` over a
join - all of these read N rows and hold N rows, and `EXPLAIN QUERY PLAN`
shows the seek and says nothing about the hold. The wall-clock in the runner's
own log was 4.6 s, which reads as "slow but fine"; the RSS column beside it was
the finding, and it had been there since the deploy.

Two rules that fall out:

- **A floor, window or horizon that widens what a query reads is re-timed on
  live before it ships, and the timing reads RSS beside milliseconds.** The
  repo already had the instrument (`inspect_live_db.py loop-rss` carries
  `rss_kb` and `candidate_ms` on every pass); nobody read it between the deploy
  and the kill.
- **A predicate that cannot see the column freshness moved to is the defect;
  the floor is the symptom.** The fix was never "narrow the floor back" - it was
  to put `confirmed_ms` in the predicate with an index that serves it, at which
  point the floor returns to what it was and the question of how wide to make
  it goes away.

And the one about diagnosis: **an abandoned request is not a finished one.**
Next's proxy answers 500 at 30 s and the backend keeps executing; four routes
that "took 30 s" had in fact taken 30 s *so far*, and each was still holding
its memory when the next one arrived. A timeout observed at the client is a
lower bound on the server's cost, and it hides the pile-up that turns slow
into dead. See [[verification-methods-that-lie]].

## 2026-09-09 - The column you exclude from a comparison key is where the duplicates' real payload hides

`fair_prices` rows were measured 99.7% byte-identical to the row before them.
To see that at all, `oldest_book_age_ms` had to be **excluded** from the
comparison: it is an age, it increments every pass, and including it finds zero
duplicates and makes the whole idea look refuted. That exclusion was correct as
a measurement, and it is exactly what hid the hazard - **the excluded column
was the only thing the "duplicate" rows were carrying that was not duplicated.**

The freshness gate is `odds_age_now_ms = (now - computed_ms) + oldest_book_age_ms`.
Those two telescope: freeze both and the sum is preserved exactly, so freezing
them looked free, and the arithmetic proving it was correct. It is free only
while the books stand still. Measured on live: `book_updated_ms` advanced on
**19,643 of 19,689** consecutive observations whose price did **not** move -
99.8%, median 646s - so the books refresh every ten minutes without moving.
A frozen age never learns that, the reported staleness grows without bound, and
every row held past the freshness limit is refused. With 344 of 494 keys
unchanged across four hours, that empties the screen.

**The shape to look for: whenever rows are deduped, compressed or downsampled
on a comparison that excludes a column, ask what that column was for.** A
column excluded *because it always changes* is, by that same fact, the column
carrying the per-row information - and the rows you are about to stop writing
are the only place it lives.

Two corollaries, and the second is the more general one:

- **A pair of fields measured at one instant and combined by a reader must move
  together or not at all.** Updating one is strictly worse than updating
  neither: freezing both preserved the sum, freezing one and refreshing the
  other double-counts the elapsed time. The fix is a second pair, both members
  stamped at the confirm instant, so each pair stays internally consistent.
- **A valid proof about the arithmetic says nothing about whether its premise
  holds.** The telescoping argument was right; the conclusion drawn from it was
  wrong, because nobody had checked whether the books stood still. The
  measurement that settled it took one query.

See [[justifications-decay-toward-reassurance]]: same family, except this
justification was a theorem rather than a comment, which made it harder to
doubt rather than easier.

## 2026-09-09 - Mutating a constant tests nothing unless every consumer actually derives from it

The dedupe's row identity was meant to live in one tuple so the `INSERT` and
the lookup could not drift. The first draft built the `INSERT` from the tuple
and **hand-typed the lookup's `WHERE`**. So a mutation that dropped a column
from the tuple changed nothing the lookup did, the test stayed green, and the
guard reported itself verified.

**The tell: the mutation's blast radius was smaller than the constant's stated
scope.** A constant documented as "the single source of truth for X" is a claim
about its *consumers*, not about itself. The mutation only exercises the
consumers that really read it, and a hand-typed copy is invisible to the
mutation *precisely because* it is a copy - the one failure mode the constant
was introduced to prevent is the one its own guard cannot see.

So the check is not "does some test go red when I mutate this" but **"does
every named consumer change behaviour when I mutate this"** - enumerate them
and confirm each. And prefer *constructing* the second use from the constant
over asserting the two agree: a drift test catches divergence after it exists,
construction makes it unrepresentable.

This is [[built-but-never-called]] living inside a single function: the tuple
had a reader and a non-reader, and the non-reader was the one that mattered.

## 2026-09-09 - A lane's green suite is a weaker claim than main's, and this repo skips its integration guards off the integration branch on purpose

Four lanes each reported a green full suite: **6727 passed, 20 skipped**. The
same tree on `main` ran **6779 passed, 0 skipped**. One lane read its 20 skips
as an environment quirk of the Windows dev box - but both runs were on that
same box, so the difference was the *worktree*, not the environment.

`tests/test_parallel_lanes_do_not_collide.py` skips itself off the integration
branch deliberately, and its own comment says why: a `DRAFT-` ADR in a lane is
the correct state, so a silent green there *"would read as checked and fine"*.
The guards it holds are exactly the ones a merge needs - that no unnumbered ADR
reaches `main`, and that the schema version covers its migrations. **A lane
cannot run them by construction.**

So "full suite green" from inside a worktree means "green on everything that
agrees to run here", which is a different sentence. The count that can be
compared to a baseline is collected on the integration branch, after the merge.

And the method for taking that comparison matters too: **comparing collection
counts by copying a test file somewhere else is invalid.** Several files here
resolve fixtures relative to their own path and collect a different number when
moved - one reported 19 tests from `/tmp` and 154 in place. Check out the
baseline commit as a real worktree and collect there, then diff the node IDs;
that attributes every test to a file instead of leaving a remainder to explain.

Related: the previous session's lesson that CI failed twice on things no lane
could see from inside its own worktree. Same family - this names the mechanism.

## 2026-09-09 - An append-only record reports the last state it saw forever after that state ends, so "the newest row for X" cannot see X going away

`venue_positions` is a poll record: while a combination is held it is rewritten
every cycle, and when it settles it is not marked closed - it simply stops
being written. **The absence is the event.**

A reconciler asked for the newest `venue_positions` row *bearing each ticker*
and printed its contracts. On live it reported three combinations as
`OPEN AT VENUE -- UNWATCHED`. Two of them had settled the previous day. Their
newest row said "4 contracts, open" because that was true the last time they
existed, and it will keep saying so for as long as the table is kept.

**Silence read as exposure, inside the one column written to catch silence read
as health.** Nine tests were green over it, because every fixture described a
position that was still open - so no fixture could tell "held" from "last seen
held", which are the same row.

**The shape to look for: any table where a row's existence is the signal and
its absence is the other signal.** Poll records, heartbeat tables, presence
logs, subscription lists, `venue_positions`, anything mirrored from an
endpoint that returns "what is true now". For all of them, `ORDER BY id DESC
LIMIT 1` over a key answers a question nobody asked - *what did we last
believe* - and reads exactly like the question everyone wants, *what is true*.

The correct form asks about **membership of the latest complete observation**:
is this key present in the most recent successful poll? Two parts, and the
second is easy to miss:

- **The observation must be the latest COMPLETE one.** Take the latest poll
  including failures, and every key is absent from it whenever a call errors -
  turning an outage into an all-clear. `ok = 1` is load-bearing and deserves
  its own test, because the mutation that drops it makes everything look
  closed, which is the reassuring direction.
- **Name the column for what it holds.** `venue_contracts_latest` asserted a
  currency it never had; `contracts_when_last_seen` beside a `last_seen_ms`
  cannot mislead the same way. A name that overclaims is the defect surviving
  its own fix.

Related: [[verification-methods-that-lie]], and the sibling where the missing
thing is a caller rather than an absence, [[built-but-never-called]].

## 2026-09-09 - A decision that turned on a named consumer must be re-opened when the consumer is never built, and nothing notices that it was not

ADR 0065 gated the manual ticket behind a typed P(YES) and masked the ask until
it was entered. The ADR records that two reviewers disagreed, and that the
red-team position - *"an unscored form is a speed bump a user learns to type
through"* - **lost on exactly one factual premise**, quoted from its own §1:

> The premise changed on 2026-08-22: `bet_clv()` shipped, scoring Joe's own
> bets against Kalshi's close. **A pre-bet P(YES) now has a consumer** - it can
> sit beside the bet's CLV on `/bets`.

`backend/bets.py` never read `p_yes_bp`. Nothing ever did. Eighteen days and
four real bets later the field was still required, still masking the price, and
the operator's own verdict was *"it just gets in the way"* - which is the
red-team's sentence, arrived at from the other side.

**The failure is not that the consumer went unbuilt. It is that the decision
went on reading as settled.** An accepted ADR is evidence; nobody re-derives
one. So the argument that a reviewer *lost* stays lost, and the condition that
beat it is never checked again, because checking it is nobody's job and no test
can fail.

**The tell: a decision whose recorded reason is in the future tense.** "Now has
a consumer", "will be scored", "once the dashboard lands", "this unblocks X".
A premise about what will exist is a promise, and an ADR records promises with
exactly the same authority as facts. Rendered as prose a month later they are
indistinguishable.

**So when a decision rests on a future fact, the ADR must carry the check as a
trigger, not as a sentence** - the shape ADR 0127 used for the bid path: a test
that goes red the day the condition changes. Here that would have been a test
asserting `p_yes_bp` has a reader, red from the moment it was written, and the
gate would never have shipped ahead of its justification.

And the diagnostic that costs nothing: for any field a screen makes someone
fill in, **grep for who reads it.** A write with no reader is not a feature
with a missing half - it is a cost with no product, and the person paying it
is the one who cannot see the grep. See [[justifications-decay-toward-reassurance]]:
same family, except this justification was never true rather than becoming
false.
## 2026-09-09 - A replay test can pass through the crash point the guard is for, and then the guard is unverified while the test's name says otherwise

Schema v35 rebuilds `manual_orders` and copies its rows with `INSERT OR
IGNORE`, so an interrupted step can re-run from the top without duplicating a
primary key. The test written for it wound the version stamp back after a
completed migration and ran the step again, asserting the rows survived. It
passed. **It also passed with the `OR IGNORE` removed** - the mutation came
back green.

The reason is that a create-copy-drop-rename rebuild has several crash points
and they need different guards. After the RENAME the temp table does not
exist, so the replay creates it empty and a plain `INSERT` has nothing to
conflict with. The only state in which `OR IGNORE` does any work is a crash
*between* the copy and the drop, where the temp table is already populated -
and no test reached it, because winding back a version stamp does not
reproduce a half-finished step.

**So: when a step is idempotent at N distinct interruption points, "run it
twice" tests one of them, and usually the cheapest one.** The state has to be
constructed - here by executing the step's first two statements by hand and
then letting `migrate` run the whole step - rather than approximated by
re-invoking the runner.

Two things follow, and the second is the more general one:

- **The mutation is what found this, not review.** The claim "idempotent at
  every crash point" sat in a comment above a green test naming three of them.
  Reading the comment against the test would not have separated them; deleting
  the guard did, immediately. This is why the convention is to disable every
  guard rather than to argue it is covered.
- **A test whose name generalises past what it exercises is the same defect
  as a test named after the implementation** (see the 2026-09-09 lesson on
  `_check_sequence` below). `test_replaying_the_step...` sounded like it
  covered replay; it covered one replay. The tell is a name quantifying over
  a class - "every", "any", "replaying" - where the body constructs a single
  member of it.


## 2026-09-09 - A true sentence with the wrong scope cannot be caught by any guard that checks its facts, and a sourcing guard makes that harder to see rather than easier

The buy ticket and the bid route both said *"every combination book this repo
has ever read had no YES bid - 40 of 40, across three runs on two dates."*
Every word was true. The count was correct. Both numbers were `ast`-guarded
against being typed rather than sourced, precisely so a stale digit could not
survive a green suite - a guard this repo added after a refuted sentence lived
eleven days.

All 40 books came from two series. **Zero came from
`KXMVECROSSCATEGORY-SHARD1`, which is where every hand fill this desk has
taken lives.** Joe read the sentence while tapping a shard-1 combination.

**Nothing could have caught this, and the reason is structural.** A sourcing
guard asks *"is this number the number?"* The defect was not in the number. It
was in the population the reader supplies when the sentence does not name one -
and "every book this repo has ever read" invites exactly that, because it
sounds exhaustive while being a statement about the reader's own sampling.

**So the check that was missing is not about facts but about quantifiers: when
a screen states a count over a population, does it name the population?** A
count without a denominator's identity is an invitation to substitute the one
in front of you. The tell is a phrase like "every X we have seen" or "all
recorded Y" - true by construction, and therefore carrying no information about
what was *not* seen, which is the half the reader needs.

Two corollaries, both learned the hard way here:

- **The strongest guards make this failure less visible, not more.** Green
  sourcing tests, an `ast` parser, a constant with a comment block - the
  sentence looked like the most carefully defended string in the codebase.
  Defence-in-depth on the wrong axis reads as defence.
- **Fixing one surface is not fixing it.** The same sentence lived on the bid
  route's 422. Correcting the screen someone looks at and leaving the one
  nobody looks at reproduces the defect exactly where it will not be noticed;
  the tests here assert both surfaces in one file so neither can be quietly
  dropped.

And the scope clause must claim nothing extra. It says what was read and what
was not, and stops - **not** that the unread population differs, which no data
supports and which is the easier error to make while writing an honest caveat.

See [[justifications-decay-toward-reassurance]]: this is the same family, but
the sentence never decayed. It was narrow from the day it was written, and only
the reader's context made it mislead.

## 2026-09-09 - A test can enshrine the defect as intended behaviour, and then the guard's absence is *documented* rather than merely missing

`_check_sequence` trusted the first `seq` on a websocket connection at any
value, parked it as the cursor, and thereby dropped every legitimate frame
afterwards - silently, with no invalidation, no resync, and the receive-timeout
still satisfied because `_last_message_ms` is stamped before the frame is
judged. Silent permanent staleness, which is the worst failure this feed has.

**A test asserted that this was correct.**
`test_the_first_frame_on_a_connection_is_accepted_whatever_its_seq` passed
`seq = 8_675_309`, asserted it was accepted, and asserted the cursor moved
there. Green, named confidently, and pointing exactly the wrong way.

This is worse than an untested guard and it fails differently. An untested
guard is a gap: someone eventually notices nothing covers the case. A test that
pins the defect **answers the question before it is asked** - a session
checking "is the bootstrap frame handled?" finds a test whose name says yes,
and stops. The repo's own instruments then report health over the hole, which
is [[verification-methods-that-lie]] arriving through the test suite instead of
through a CLI.

**How it happens, and it is not carelessness.** The test was written from the
implementation rather than from a claim about the world. "The first frame is
accepted whatever its seq" is a true description of what the code does; it was
never a decision anybody made. Naming tests after the claim they make is this
repo's convention precisely because a name like that has to be *argued for* -
and nobody would argue for "whatever its seq" out loud.

**So: when a test's name is a restatement of the code's behaviour rather than a
claim about the world, treat it as unreviewed.** The tell is that you can
derive the name by reading the implementation. A real claim has a reason you
could put in a sentence beginning "because" - and if the sentence comes out as
"because that is what it does", there is nothing under it.

The corollary is about what to do on finding one: **invert it, do not delete
it.** The replacement here tests the bound from both sides - exactly at it
accepts, one past refuses - so the next reader can see that the boundary was
chosen rather than inherited. A deleted test leaves no evidence the question
was ever settled. See [[built-but-never-called]] for the sibling case where the
missing thing is a caller rather than a claim.

## 2026-09-09 - Arming an entry without arming its exit is a whole class of defect, and the linkage columns are usually already there

`POST /api/manual-orders` bought `KXMVE` combinations with real money and wrote
zero rows to `parlay_positions`. A combination is enter-only, `/hedge` is the
only exit it has, and `/hedge` watches that table - so on 2026-09-08 two real
positions existed for their entire life with the exit screen never having heard
of them.

**The parts were all built.** `parlay_positions.combo_ticker` and
`.parlay_lookup_id` were in `schema.sql`, accepted by the hedge route, and sent
by nobody. The legs were in `parlay_lookups`. Every field
`hedge.record_position` needed was on the `CandidateLeg` at lookup time and was
being dropped at the moment of persistence. Nothing had to be designed; four
fields had to stop being thrown away.

**That is the shape to look for.** Not "is this feature built" but **"is the
inverse of this action built, and does anything connect them?"** Entry and
exit, open and close, subscribe and unsubscribe, arm and reconcile, record and
resolve. Each pair tends to be built by a different session for a different
screen, and the join between them is the part nobody owns. Grepping for a
column's writers is the cheap version of the check: a column that `schema.sql`
declares, a route accepts, and no client sends is a join that was designed and
never completed.

**The related trap, which cost a test rewrite here.** Two tests asserting "no
position was recorded" passed under a mutation that removed the guard entirely
- because a zero-size position is refused *downstream* by the table's own
CHECK. They were green for a reason unrelated to the thing they named. A guard
verified by "the bad state did not appear" is weak whenever anything else also
prevents that state; assert the *distinguishing* consequence instead. Here that
was the user-facing note: with the guard, an unfilled order says nothing; with
it removed, it falsely warns that a combination he never bought is unwatched.

And the general rule that fell out: **when a fill cannot be recorded, say so on
the screen.** Silence after money moves reads as success. The failure branch
that quietly does nothing is the same defect in miniature - which is why
"could not record this" and "there was nothing to record" must be
distinguishable in the response, never both `null`.

## 2026-09-09 - Re-verify a question before asking it, not just a task before doing it - and never `Write` to a path without checking what is there

Two errors in one action, and they compound: a billed Anthropic call was spent
re-capturing a fixture that had been captured four days earlier, and the script
that captures it was overwritten in the process.

**Error one: the question was stale, not the answer.** `tasks/NEXT.md` carried
*"(B) Authorise the one billed Anthropic call for the Scout fixture? Still
unanswered."* It had been answered on 2026-09-05 and done: the fixture, the
script and a test class driving it all landed in commit `c2976ec`, whose
message reads *"Joe's answers B, C and D."* Joe was asked again, said yes
again, and the second call reproduced the first result exactly.

The mechanism that hid it is worth naming: **lettered question batches are
reused every session.** `(B)` in one session and `(B)` in the next are
different questions with the same label, so a stale entry does not look stale -
it looks like the current batch. A dated item announces its own age; a lettered
one does not.

**And the same session had already written the rule it broke.** Hours earlier
it audited a month-old open-items file, found three of six items stale in the
direction of *more work than exists*, and wrote: *"an open-items list decays
toward overstating the backlog, because closing an item requires someone to
notice, and nothing notices. Re-check before planning against a list older than
a few weeks."* Then it planned against the Joe-gated list two paragraphs below
without re-checking it.

**So the rule generalises further than it was written.** It is not "audit files
decay". It is: **every list of open things decays, including the one you are
about to act on, including the part of it that asks another person for
something.** Verifying a task before doing it is habitual; verifying a
*question* before asking it is not, and a question costs someone else's time
and sometimes their money. The check here was one `git log -- <path>`.

**Error two: `Write` to a path that already existed.** The capture script was
tracked, and a better version - it had a spend guard, a costed docstring and an
explicit "no loop, no retry" argument. Writing the file reported "updated", not
"created", and that word was the only warning. `git checkout` restored it, so
nothing was lost, but only because it was committed.

**Before `Write` to any path you did not create in this session, check whether
something is there** - `git ls-files <path>`, or read it. The Edit tool refuses
to touch a file it has not read; `Write` does not, and that asymmetry is the
whole trap. The habit that catches it: if you believe a file is new, prove it
before overwriting it, because the failure is silent and destroys the better
version of exactly the thing you were about to build.

Related: [[built-but-never-called]] for the sibling pattern (a claim that a
module has no caller decays the same way, and a grep settles it).

## 2026-09-09 - A justification decays into a lie, and the one most likely to is the one that explains why something is safe to leave undone

`Alerter.check_fee` compares a real fill's charged fee against `core/fees.py`.
It had no caller, and unlike most such cases it said why, clearly and
correctly:

> `ORDERS_ARE_DRY_RUNS = True` means this instance has never placed an order,
> so there is no fill to reconcile and no honest place to call it from.

That was true when written and it is **the best version of this mistake** - the
absence was deliberate, reasoned and documented, which is exactly what this
repo asks for. It still ended with fills going unreconciled in silence, because
on 2026-09-08 the hand-bet path was armed and real fills landed. **The
condition the excuse rested on changed, and the excuse did not.**

**The pattern: a comment that asserts a fact about the world is a claim with a
shelf life, and nothing expires it.** Code that is wrong gets a failing test.
Prose that has gone stale gets read and believed. Three separate instances
turned up in one session, all in the same direction - all reassuring:

- `check_fee`: "no order has ever been placed" - false for 40 hours.
- `OrderBook.is_quotable`: "the order endpoint checks this independently" - the
  endpoint does check independently, but **not through here**; the method has
  no production caller at all.
- `ws.py`'s header: a sequence gap "triggers an automatic
  unsubscribe/resubscribe for that one ticker" - wrong twice over, and the
  helper it described had just been deleted.

Each would have sent a reader looking in the wrong place, and the `is_quotable`
one nearly caused a real guard to be recorded as missing.

**So, two habits:**

1. **When you write a justification for leaving something undone, write down
   the condition that would end it** - not just the current state. "No order
   has ever been placed" is a state; "wire this the day any order path is
   armed" is a trigger. The second survives contact with the future.
2. **When you touch code near a claim, check the claim.** It costs one grep and
   it is the only mechanism that exists - there is no test for prose. The
   correction belongs at the point of the claim, dated, saying what it used to
   say; deleting the wrong sentence silently means the next reader cannot tell
   a corrected comment from one nobody ever checked.

The corollary is about which direction to distrust. All three of these erred
toward *reassurance* - "this is fine", "this is covered", "this is handled". A
stale comment claiming something is broken gets investigated and fixed. A stale
comment claiming something is safe gets believed and closes the question. See
[[verification-methods-that-lie]] and [[built-but-never-called]].

## 2026-09-09 - A helper with no caller may be the *losing side of a decision*, not an unrun feature, and only the neighbouring docstring tells them apart

This repo has caught four cases of "built but never called" - a complete,
tested module invoked by nothing, manufacturing the belief that a feature
exists. `KalshiWebSocket._resubscribe` was logged as the fifth, and it was
not one.

Grep found it the same way it found the other four: no caller in production,
none in tests, none via `getattr`, string dispatch or config. On that evidence
the two cases are indistinguishable, and both readings were available -
"delete the tidy-up" or "a dropped socket silently stops delivering prices".
The second was the one that mattered, because stale prices with no error is
the worst failure the feed has.

**What settled it was three lines away, in prose.** `_resync_all`'s docstring
says it reconnects *rather than* re-subscribing, deliberately, because whether
Kalshi answers a redundant subscribe with a fresh snapshot **has not been
observed**. So `_resubscribe` was the branch that docstring rejects, left in
the file after the decision went the other way. It was not a feature that
never ran; it was an argument that lost.

**The distinction, and it changes what you do:**

- **A module with no caller** is a capability the system believes it has and
  does not. Wire it or delete it, and either way something is wrong today.
- **A helper with no caller** may be a rejected alternative. Deleting it is
  right, but only after moving *why* it was rejected into the code that
  survived - otherwise the next session rebuilds it, having lost the one fact
  its correctness turns on.

So: **before acting on a no-caller finding, read the docstrings and comments
of its neighbours, not just its own.** A grep tells you nothing is calling it.
It cannot tell you whether that is a gap or a verdict.

The corollary is about how the finding was reached at all. Both of this
repo's caller-checks (`tests/test_has_callers.py`, `tests/test_reachable_callers.py`)
are **opt-in by symbol list**; the second explicitly declines to assert that
its unreached set is dead, because a walk that over-approximates reachability
cannot also be the authority on death. Instance five reached today not through
a gap in the greps but through a gap in **what is enrolled**. See
[[built-but-never-called]].

## 2026-09-09 - A test that `skip`s on missing input cannot tell a legitimately absent case from the regression it exists to catch

`tests/test_discovery.py` existed to catch a real historical bug: the
classifier dropping every spread and total. Two of its tests began

    if not priced:
        pytest.skip("fixture has no spread/total events in scope")

Simulating that exact bug - filtering every spread and total out of the
capture - produced **94 passed, 3 skipped, exit 0**. The file went green in
precisely the state it was built to detect, and the run *looked* healthy;
"skipped" is not a colour anyone reads as alarming.

**The error is treating a committed fixture as a runtime condition.** Whether
`tests/fixtures/events_sports_nested.json` contains spread events is a
**fact** - it is checked in, it does not change between runs, and it holds 6
spread and 6 total events that survive discovery. An empty result is therefore
always the code changing, never the input. Branching on it hands the
implementation a way to satisfy the test by producing nothing.

**So assert the precondition instead of skipping on it**, in its own named
test whose whole job is that the fixture still holds what the tests below
need - the pattern `tests/test_marts.py` already uses with the comment
*"Otherwise every assertion below passes vacuously."* After the change, the
same mutation gives **5 failed, 0 skipped**.

**The general rule: a `skip` is only legitimate when its condition is a
property of the *environment*, not of the thing under test.** "No credentials
on this machine" and "the capture file was never downloaded" are environment.
"The code under test produced nothing" is the result, and a test that skips on
its own result cannot fail. When you write `skip`, say out loud which of the
two it is; if it is the second, it is an `assert`.

## 2026-09-09 - `flyctl ssh console` starts a shell that does NOT carry the app's Fly secrets; the credentials live on the app's own child process

Reading a Kalshi balance off the live box by importing the desk's own code
over `flyctl ssh` failed four times with `ConfigError: KALSHI_PRIVATE_KEY_PATH
is not set`. The obvious readings - "the secret is unset", "the deploy is
broken", "credentials are gone" - were all wrong, and any of them would have
been an alarming and false thing to write down.

**Fly injects secrets into the process it starts, not into an ssh session, and
here not even into pid 1.** `docker/entrypoint.sh` forks, so `/proc/1/environ`
has nothing; the credentials sit on the child `python` process. The fix is to
find that process and borrow its environment:

    for p in /proc/[0-9]*; do
      tr '\0' '\n' < "$p/environ" 2>/dev/null | grep -q '^KALSHI_PRIVATE_KEY_PATH=' \
        && SRC="$p/environ" && break
    done

then export only the `KALSHI_*` lines, without echoing them, and run with
`PYTHONPATH=/app`. Export by prefix, never dump the whole environ - the point
is to use a credential, not to print one.

**The pattern, and it is the general one:** an environment is a property of a
*process*, not of a *machine*. "The variable is not set" from a shell you
started yourself says nothing about the process actually serving traffic. This
belongs beside every other entry in [[verification-methods-that-lie]], because
its failure mode is a confident false negative about production configuration
- exactly the shape most likely to get written into a handoff as a finding.

The secondary lesson is about when to stop. Four attempts went into shell
quoting before the question "is the app even pid 1?" got asked, and that
question was one cheap command that settled it immediately. **When a fix keeps
failing the same way, stop refining the mechanism and re-test the assumption
the mechanism rests on.**

## 2026-09-09 - A push may cancel an in-flight CI run only when the new tree strictly contains the cancelled commit, and a rule with a redundant clause is worse than no clause

A push cancelled a running CI job in order to ship an unauthenticated-RCE fix
about fifteen minutes sooner. That was the right call and it is also exactly
how [[wait-for-ci-before-pushing-again]] gets violated, because the reasoning
that justified it - "the new run tests a superset anyway" - is the same
sentence someone will say when it is false.

**So it is a bounded exception. One condition carries it, and it is checkable
before the push:**

**The new tree must be a strict superset of the cancelled commit's tree** -
the cancelled commit's content literally contained in what the new run will
check out, not "roughly the same work" and not "the same branch". When that
holds, nothing is lost, because the superset run checks everything the
cancelled run would have and more.

**The condition that is NOT required, written down because this session got it
wrong first:** it does not additionally matter whether the cancelled commit's
unique content is exercised by the suite. The first draft of this lesson
demanded that too, and the very next push violated it - cancelling a run whose
commit added a test file, which the suite obviously does exercise - while
being completely safe, because the superset run ran that same new test. A rule
with a redundant clause is worse than no clause: it gets broken in a safe case,
and then it gets ignored in an unsafe one.

Two separate cancellations happened this session and both were fine on the
superset test alone. Where the "is it exercised" question does belong is a
different one: **deciding whether local verification was sufficient.** The
frontend lockfile bump was checked by `tsc --noEmit` and `next build` locally,
and CI runs `ruff` and `pytest`, neither of which touches `frontend/` - so the
run that was cancelled was never the check that mattered for that change. That
is a reason to be relaxed about the wait, not a licence to cancel.

**The general shape:** when urgency argues for skipping a discipline, do not
skip it and do not obey it blindly. State the two or three conditions under
which skipping is safe, check them, and write them down - because the next
person will inherit the precedent whether or not you meant to set one. A
cancelled run still verifies nothing. What changes is whether anything needed
verifying.

## 2026-09-09 - An exemption list groups by syntax, not by kind, and the dangerous member is the one that merely looks like the safe ones

`frontend/src/middleware.ts:160` read
`matcher: ["/((?!_next/static|_next/image).*)"]`, and the comment above it
justified the exclusion honestly and correctly - for `_next/static`, which is
hashed build assets with nothing sensitive in them. `_next/image` sits inside
the same alternation, shares the same prefix, and is a server-side image
processor accepting attacker-controlled parameters. It was outside the auth
gate on a public instance in front of a real-money order path, and the
justification a reader would find written above it was true of its neighbour.

**The pattern:** an exclusion list is a claim about every member
independently, but it is *read* as a claim about the group, and the group is
formed by whatever the syntax happens to collect - a shared path prefix, a
regex alternation, a glob. When one member's rationale is written down, it
launders the others. So: when auditing an allowlist, denylist, matcher or
`ignore` file, **check each entry against the rationale separately, and treat
a shared prefix as zero evidence that two entries are the same kind of
thing.** The tell here was available for free: one is inert bytes on disk,
the other is code that runs on request. Nothing in the shape of the line says
so.

The corollary is about how the exemption was found. It was not found by
reading the file - it was found by making the request. A gated path answered
`307 -> /login`; `/_next/image` answered with the optimizer's own parameter
validation strings and no cookie was sent. That is the same method the
2026-09-08 lesson arrived at from the opposite direction, where reading a
route body produced a *false* claim of a missing guard. **Execute the path.
It settles both directions.**

## 2026-09-09 - A tool's summary of its own scan describes the state before the scan you just triggered, and its per-item verdict can be wrong in the safe-looking direction

A `git push` printed "GitHub found 1 vulnerability (1 high)". That number was
assembled before the rescan the push set off. A second later the truth was two
CRITICAL unauthenticated RCEs and one high, and the "1 high" it named had been
closed by the same rescan. Reading the alerts API instead of the push output
took one command and changed the session's whole ranking.

Worse, and the part that generalises: the closed alert was closed **wrongly**.
It reported `state: fixed` while the manifest still pinned a version squarely
inside the advisory's vulnerable range, unchanged by that push. So the
instrument was not merely stale, it was *affirmatively wrong about one item*.

**The pattern, and it is [[verification-methods-that-lie]] with a new member:**
a summary emitted *by* an action describes the state *before* that action's
effects, and a status field is a claim by the tool about the world rather than
a reading of the world. Neither is a measurement. **Verify a dependency fix by
reading the version out of the running artifact** - here, the versions were
read out of the live container over ssh, not inferred from the alert closing
or from the lockfile that produced the image. When one item in a feed is
demonstrably wrong, that is a fact about the feed, so raise scrutiny on the
items you *liked* the answer to as well.

## 2026-09-09 - A config value can be malformed in a way that reads as fluent English, and the artifact then does not exist rather than failing

A new agent definition's frontmatter carried
`description: ... not a planner: it does not judge, ...`. The unquoted `: `
terminates the YAML scalar and makes the whole mapping unparseable. The line
reads as an ordinary, well-punctuated sentence. Nothing warns. The agent
simply would not have been there when someone spawned it - a file present in
the tree, committed, reviewed, and inert.

That is exactly this repo's four-times-caught shape - four modules complete,
tested, imported by nothing, described in a handoff as features - reached by a
new route. The earlier instances were *code* with no caller. This is
*configuration* with no parser, and it is harder to see, because the failure
happens before anything runs and produces no symbol to grep for.

**The pattern:** whenever a file's correctness depends on a parser rather than
on a reader, add a test that parses it, and require the fields that matter
rather than only well-formedness. Prose punctuation inside a structured value
is the specific hazard: colons, quotes, leading `%` or `@`, anything a
serialisation format reserves. `tests/test_agent_definitions_parse.py` was
written for this and verified by planting the defect back, which is the only
way to know the guard is not decoration.

# The pattern index

Every lesson ever written, newest date first, one line each. The full text of
each is in the linked archive file, unchanged; the sections marked *in this
file, above* are the ones not yet archived. Regenerate it from the headings in
the same edit as the entry — an index that is not is stale by one entry
immediately and by dozens within a week.

### 2026-09-08 — [`archive/lessons-2026-09-11.md`](archive/lessons-2026-09-11.md)
- A spine that records its own corrections inline grows without bound, and the corrected fact is the only part a session needs
- "This route has no guard" is a claim about the whole dependency chain, not about the route body
- A guard that reads the code but not the decisions is half a guard
- Removing a brake server-side leaves it on the screen, and that direction of the mismatch is invisible
- A count or a "not yet" copied into a new session entry is a present-tense claim from a past reading
- A consumer that restates a predicate is not covered by the test that pins it
- A mechanism that relabels spend is not a saving
- A mutation that stays green has two readings, and only the code tells you which
- A capture script that reads the environment captures the laptop, not the deployment

### 2026-09-07 — [`archive/lessons-2026-09-11.md`](archive/lessons-2026-09-11.md)
- "It might be slow" is not a tolerance; find the bound
- "Expect the count to fall" is a claim about a delete that may not exist
- An instrument is not verified until it has been run against the real data once
- The check and the instrument for the check are two deliverables, and only one of them gets planned
- A screen that names one failure lets every other failure wear the quiet's clothes

### 2026-09-06 — [`archive/lessons-2026-09-11.md`](archive/lessons-2026-09-11.md)
- Two true docstrings, one false conjunction
- A caveat loses to the variable name it sits under
- A test that restates the code's own formula agrees with the code whatever the code says
- A guard that substring-matches an element name is green on a renamed element
- A hand-typed sha is a fabricated sha, and noticing that it looks wrong is not the same as checking it
- A section truncated by `head` looks exactly like a section with no rows, because the header prints before the data
- A scripted edit meant to change a few bytes rewrites every line ending in the file, and a normal diff cannot show it
- A date-triggered falsifying check must be dated from the event's END, and from a looked-up calendar rather than a remembered one

### 2026-09-05 — [`archive/lessons-2026-09-11.md`](archive/lessons-2026-09-11.md)
- A stub that assigns over a property tests the assignment; the SDK's own parser is the only thing that runs the SDK's parsing
- An error handler ordered after a call that raises is not an ordering, it is dead code with a comment explaining it
- Audit each item of a list you were handed; "three of X" is a claim about all three
- Reading the aggregates to scope a measurement is what disqualifies them from being its result
- A `--` comment inside a CREATE TABLE column list breaks DROP COLUMN, and the failure names a table the change never touched
- When a guard asserts the mechanism instead of the property, the fix that changes the mechanism looks like a regression
- Test at the level the defect lives; a substring test cannot tell a mention in a live branch from a mention in a dead one
- A link is a claim about its destination, and only the destination knows whether it can keep it
- A deadness grep scoped to the source directories misses the callers that matter most, because the loudest ones live outside them
- A clean merge is a statement about text; two lanes can each be right about a file and wrong about each other

### Removed as duplicates 2026-09-08 — [`archive/lessons-2026-09-08-dedup.md`](archive/lessons-2026-09-08-dedup.md)
- An item written from the shape of a known lesson is a hypothesis, not a finding
- `git checkout <file>` restores the INDEX, so it deletes uncommitted work while looking like an undo
- `assert str(CONSTANT) in text` passes just as happily on a typed digit, so it does not test that the text is sourced
- Run a new guard against the code before the fix; a green suite proves the test agrees with the fix, not that it would have caught the defect
- A test that recompiles identical bytes once per case is a tax on every future run, and the fixture that fixes it is three lines
- A guard that greps for a component name finds the comment explaining the component, and a prefix is a substring of every longer identifier
- A "has a caller" check is only as deep as its walk, and a one-level walk is satisfied by a referrer that is itself dead

### 2026-09-04 — [`archive/lessons-2026-09-08.md`](archive/lessons-2026-09-08.md)
- An absence pin that greps for a literal name finds it in `__pycache__`, because CPython folds `"a" + "b"` at compile time
- A rate limit is a pause, not a loss: an agent with a worktree resumes with its context
- "The largest contributor" is a set until proven a singleton, and `max()` on a dict picks a member silently
- A precondition written as the failure of one named mechanism does not fire when a different mechanism fails the same way
- A date read off a local clock is a different date; every registered instant is UTC
- A fixture set that only ever states the deployed value cannot detect a hardcoded copy of it
- Match a source anchor against the file's own line ending; a normalising reader will tell you it exists when a byte reader cannot find it
- The session scratchpad is shared across parallel lanes

### 2026-09-03 — [`archive/lessons-2026-09-08.md`](archive/lessons-2026-09-08.md)
- A counter that emits on a cadence while a condition holds measures the condition's duration, not its occurrences
- "One predicate, two spellings" is an architectural fault, not a run of incidents
- A binder proposed from a remembered lesson is a hypothesis, and it enters the record only after the check
- A screen promoted into a slot inherits the slot's traffic, not the old screen's fixes
- A gate that mounts a self-heal only when the screen is empty stops healing the moment it has anything

### 2026-09-02 — [`archive/lessons-2026-09-08.md`](archive/lessons-2026-09-08.md)
- A link to a screen is a claim that the screen exists, and the claim is pinned or it rots
- "Restore the guard" with `git checkout` restores the COMMIT, not your edit
- When a single look is registered, the look that counts is the FIRST one past the stopping rule
- A retention cap on a diagnostic file is a deletion of whatever measurement reads its oldest lines
- Before ranking work on a screen, read the instrument that says whether anyone is looking at it
- A doctrine comment is a claim about the tree; grep before citing it

### 2026-09-01 — [`archive/lessons-2026-09-08.md`](archive/lessons-2026-09-08.md)
- Under `set -e`, a guard downstream of an abort is decoration
- Isolate any subagent that WRITES, not just one that mutates code
- A test that asserts copy's TEXT freezes it; assert its SOURCE
- A clearing statement in an ADR is a claim about a population, and needs its boundary as precisely as a finding does
- A CI run that reports on your branch may not be reporting on your commit
- Adding a SHAPE to a shared artifact is a wider change than adding a field
- A registration's "what we cannot measure" list is a claim, and getting it wrong retires the falsifying test
- A subagent with Bash mutates the tree you are committing from
- Check a ticket against the tree before scheduling it
- A flag whose TRUE value has two causes is not an instrument, however carefully it is recorded
- A test that addresses its subject by POSITION can keep passing against the wrong subject
- Find the change point before you name the cause
- A group selected by an outcome cannot report a rate on that outcome
- A writer with no reader is an instrument that does not exist

### 2026-08-31 — [`archive/lessons-2026-09-08.md`](archive/lessons-2026-09-08.md)
- A cost that does not change with the row limit is not in the rows
- A header you set is not a header the framework sends
- A guard on the code must not be able to read the comment beside it
- Text can overflow a correctly-sized box, so hunt overflow with scrollWidth and not with rects
- A fix that does not move the number has not been shown to work
- A layout measurement measures tonight's data as much as the CSS, so one clean read is not a clean bill
- A tool that reports success has not necessarily done anything; measure the state it claims to have set
- Code and its own comment agreeing is not verification; both can be wrong together about the rule they serve
- A test named for a relationship between two artifacts must read both of them
- A number cannot be checked against itself, so put a second independent rendering of it on the same row
- A component that inherits its type size has no typography
- Never hold a database write transaction across an `await` that does I/O
- A wording rule can be defeated by typography, and no source test will see it

### 2026-08-30 — [`archive/lessons-2026-09-08.md`](archive/lessons-2026-09-08.md)
- Split a before/after on evidence of the change, never on when you think you made it
- A test double that is kinder than the real object hides the bug it exists to catch
- When two code paths can produce the same end state, an assertion on the state guards neither
- Check the REGRESSOR moved before you read the outcome; a constant explains nothing
- An instrument sampled at pass START repeats itself when a pass fails, and the repeat is the signal
- When you change a cadence, re-read every predicate that compares against a timestamp it produces
- A test that names a symbol is not a guard on that symbol
- A failure recorder that shares the failing resource records exactly the failures that don't matter

### 2026-08-29 — [`archive/lessons-2026-09-08.md`](archive/lessons-2026-09-08.md)
- A local autouse fixture over module state protects one file and exposes every other
- A red suite in a shared checkout may be a moving tree, not a defect
- One constant serving two purposes changes the thing you were not touching
- A merge of two correct changes can contain a defect neither of them contains
- Read the output, not the exit status
- Search the measurements directory before commissioning a measurement
- A document that promises to amend itself needs an enforcer, and the un-amended state always flatters
- When mid-flight steering is unavailable, the brief is the only instrument, so it must grant permission to refuse
- One predicate with two spellings, and the screen believing the wrong one
- A cause list written as alternatives cannot file causes that happen in sequence

### 2026-08-28 — [`archive/lessons-2026-09-08.md`](archive/lessons-2026-09-08.md)
- A pre-registration must fix its scope conditions before it enumerates causes
- "Unexplained one-off" is a claim about frequency, and a default window is not a population
- A helper called from a loop that must not die does not get to trust its caller
- Sharing a predicate guarantees agreement only about what the predicate decides
- A guard that matches a literal string certifies the string, not the property
- A guard can check the right token in the wrong role, and stay green for months

### 2026-08-27 — [`archive/lessons-2026-09-05.md`](archive/lessons-2026-09-05.md)
- The deploy ships the working tree, so a correct repository proves nothing
- Deliberately producing the signature an alarm watches for disables the alarm, and nothing announces it
- A fixture can occupy the wrong branch, and then full coverage means nothing
- A guard that would refuse everything is an outage, and the venue's sentinels are where it comes from
- A test written against a re-implementation cannot fail for the reason it exists
- A test that asserts the ledger is not a test of the behaviour the ledger records
- Verify against `origin`, not against `main`, because the object store makes them look alike
- A fact that is displayed but is not a finding does not get acted on
- A relayed approval is information, not authority, and the word "settled" is where it goes wrong
- A count with no denominator invites an adjective, and the adjective is the inference
- A reporting tool must be run from every seat it will be run from, and its findings must not be phrased as instructions
- The fixture asserted the bug away
- A detector's granularity is decided by its false-finding risk, not by what is easy to compute
- A test can pass for a reason you did not write, and only mutation finds out which
- A schema version is a claim about the whole database, so a lane cannot allocate one

### 2026-08-26 — [`archive/lessons-2026-09-05.md`](archive/lessons-2026-09-05.md)
- A mutation can lie, and a green result is not evidence until you know the mutation landed
- A test written after the code describes it; a test written against a claim constrains it
- Fifteen minutes of measurement outranked a day of planning, and the plan had ranked by what looked expensive
- State that outlives a request outlives a test, and the tests that break are the ones that never heard of it
- A test that does real work to check a cheap property is a test that stops being run
- A guard that greps its own module must read the code, not the prose
- A GREEN mutation is a claim about the harness before it is a claim about the test
- Rule 1 has a scope, and it belongs on the input rather than on the result
- An unknown budget must not resolve to zero, exactly as an unknown price must not
- Killing a background command's shell does not kill the process it started
- Fixing a defect at the call site leaves the rule where the next call site cannot find it
- A monitor that has to touch the thing it measures is reporting its own effect
- Exit 0 means "I finished", and a supervisor that tears down on a failure is not finished
- `load_dotenv()` makes the whole test suite a credential holder, and arming is what turns that into spending
- A source-scan pin measures what it can still match, and it goes quiet rather than red
- Pin a guard on the decision it changes, never on the string it prints
- A derived value inherits its source's absence as an extreme, not as a gap
- A fixture that writes a value the wire never emits is a defect with a delayed fuse
- Bytecode caching is keyed on (mtime, size), so a same-length edit can survive its own revert
- A feature behind an off flag has never rendered, and the first render is part of the build
- A guard installed by an unverified edit is not installed

### 2026-08-25 — [`archive/lessons-2026-08-31.md`](archive/lessons-2026-08-31.md)

- A monitor that names a cause it cannot observe sends you to one place
- Dedupe is not a rate limit, and the difference is who supplies the churn
- A total is not a breakdown, and two spot checks cannot see a flip-flop
- Measure the cost of a thing you put on the fast path, before it is on the fast path
- A gap the length of your own timer is a timer, not a fault
- A refusal that names its own predicate describes a symptom, not a cause
- The only thing left in a quiet log is not the thing that quietened it
- Fixing a lie can move it rather than remove it
- A test fixture that spends is also a fixture that paces
- A registered rule implemented as an optional parameter is not implemented
- `G` is not evidence; leverage is

### 2026-08-24 — [`archive/lessons-2026-08-31.md`](archive/lessons-2026-08-31.md)

- An access-control finding names the layer it was read at
- A baseline taken while you edit is not a baseline
- A pin verifies the shape you saw, not the branch you rely on

### 2026-08-23 — [`archive/lessons-2026-08-31.md`](archive/lessons-2026-08-31.md)

- A wire format that was pinned but never exercised is a belief wearing a pin
- A pinned fixture clock against a wall-clock instrument is a test with an expiry date
- "The screen shows X" must come from the screen, not from the database that feeds it

### 2026-08-21 — [`archive/lessons-2026-08-31.md`](archive/lessons-2026-08-31.md)

- A field written after the spend is not a spend gate
- When a rule and its floor are defined over different units, the smaller unit's zero-information observations vote

### 2026-08-20 — [`archive/lessons-2026-08-31.md`](archive/lessons-2026-08-31.md)

- A stored number answers the question it was stored for, not the question you are asking now
- Log redaction does not reach exceptions: raise_for_status prints the URL, key and all
- A claim about git state is verified with git, never asserted from prose
- Two readers can share a word and not a definition, and the disagreement will be filed as a stale value
- A status that can only be stamped after an event must never be stamped by a clock alone
- Undo walks run in reverse, and a walk that happens to work forwards is a latent bug, not a working one
- Fixing a stale-flag read at one use site does not fix the flag; every other reader is still wrong
- A number that explains a mystery is captured and committed the day it is seen, or it is a rumour
- When local and CI disagree, do not ask which to trust. Ask which one matches production, because the answer can be neither
- "One source of truth" is a claim about the *clock* as much as the source. A flag written at the end of a step and read at the start of the next is already two clocks
- A job that only runs when a gate is open looks exactly like a job that has died. Poll the thing that says it ran, not the thing it changes

### 2026-08-19 — [`archive/lessons-2026-08-31.md`](archive/lessons-2026-08-31.md)

- A schema change costs its time at boot, under a health check that does not wait; and rehearse the migration before writing it
- `GROUP BY` treats NULLs as equal; a `UNIQUE` index treats them as distinct. A guard written on the all-NULL case cannot see the difference
- Do not diagnose a resource-starved machine by consuming that resource; and a process that is *stuck* looks nothing like a process that is slow
- A read-only handle to a WAL database reports the last checkpoint and calls it the present; and "the file stopped growing" is not "the table stopped growing"
- An error message names the hop it was thrown on, not the hop that is broken; and a fix is not a fix until it is measured after deploying
- A performance number expires when the thing it measured grows, and a benchmark that "isolates" a cost usually removes the cost
- `flyctl volumes list` and `df` disagreed for three days, and the optimistic one is the one you type
- "I checked and it was fine" is not monitoring, and the alarm you built is not evidence until you read the channel
- Attribute cost by measuring the parts, because the expensive-looking part usually is not
- A screenshot proves what the tab context says it does, not what the picture looks like
- Two columns that must be equal are not checked by anyone, and rendering both is what finds them
- A picture whose axis is set by its loudest number shows nothing about its quietest

### 2026-08-18 — [`archive/lessons-2026-08-31.md`](archive/lessons-2026-08-31.md)

- Find the render sites by scanning, not by remembering, and check that the guard's mutation is the one you meant
- A query plan is a shape, not a cost, and the monitoring you add is code that can take the box down
- An alert that cannot fire on the failure that happens is not coverage, and the count of alerts hides that
- A default is a decision nobody made, and it is invisible from inside the running system
- A guard written against one cause leaves the other causes uncovered, and the symptom is identical
- `git checkout <file>` is a destroyer of uncommitted work, and guard-verification is exactly when you reach for it
- The screen you verify against may be rendering a configuration nothing deploys, and a test that reads config text cannot tell you
- Hand a reviewer your hypothesis and require it to be refutable, then let it win

### 2026-08-17 — [`archive/lessons-2026-08-29.md`](archive/lessons-2026-08-29.md)

- A handoff written the night before states tomorrow in the past tense, and "the deadline has passed" is a claim that creates work
- Scrutiny was spent asymmetrically, and the unguarded direction was the one that created work
- A guard that is structurally always true reads exactly like a guard that fires, and "this condition is checked" is not evidence the condition varies
- A decision justified by a statistic computed under a *different definition* than the one the decision affects, and the codebase already had the difference written down
- An acceptance criterion carries implicit scope, and the person who sets it owns that scope
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
