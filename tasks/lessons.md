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

## 2026-09-23 (fourth) - Before widening a CHECK, look at who references the table; and a "the desk did it" flag can be its own column

- **A column-level CHECK in SQLite cannot be altered, only rebuilt.** If
  another table references this one by foreign key, the rebuild's
  `DROP TABLE` runs with `foreign_keys = ON`, inside the migration's
  transaction, where the pragma cannot be turned off. #143 wanted a third
  `closed_source` value on `parlay_positions`, which the legs table
  references. **Before planning a new CHECK value, grep `REFERENCES <table>`
  in `schema.sql`.** If it has children, add a nullable column instead: an
  `ADD COLUMN` step, the shape this runner already takes.

- **Keep "who established the fact" apart from "why the row moved."**
  Adding the reason column kept `closed_source` meaning what it already
  meant, and still left a desk close and a tap distinguishable.

## 2026-09-23 (third) - A field named for one meaning often carries several: filter on the codes the decision names, never on non-empty; and a figure told to the user is one they can act on

Two patterns from the fifty-first session, both caught in review before
merge.

- **"Suppressed" was one word for a dozen codes.** #79 asked Joe whether the
  parlay builder should refuse a leg the singles screen suppresses "as a
  probable bug", and named three codes. The lane refused any non-empty
  `suppressed_reason`. That field also carries `edge_within_method_noise`
  ("No edge"), which is on nearly every row, so merged as written it would
  have emptied the parlay screen. Its tests all passed because they seeded
  only `suspicious_edge`. **Before filtering on a reason field, list its
  vocabulary (`ALL_CHECK_NAMES`) and filter on the codes the decision
  named.** Add a test with the commonest harmless code, and check that it
  is kept.

- **A figure told to the user must pass the check that produced it.** The
  shard refusal printed the wall with `:.2f`. At 0.90 the example happened
  to round down; at 0.99 it printed "$3.90", which the same wall refuses.
  Floor any "the most you can ask for" figure. The test asks for exactly
  the printed figure and must pass.

## 2026-09-23 (second) - A SQL fragment copied from a sibling query carries that sibling's column meaning; and a lane's test count is read, not quoted

Two patterns from the fiftieth session, both caught while merging #137.

- **Before reusing a sibling query's expression, check that your column
  means the same thing as its column.** `scout-watch-log` labels a budget
  day with `(budget_day_ms + offset)`, which is correct because that
  column is already a day start. The lane copied it onto raw `called_ms`,
  where it moves the day boundary from 10:00Z to 14:00Z. Every test seeded
  calls at 11:00Z, where the right and wrong conventions agree, so all of
  them passed. **A test of a boundary needs a row on each side of it.**
  One test with 09:59Z and 10:01Z calls turns the mutation red.

- **Start a running-sum window on the boundary it sums over.** `now - n
  days` cuts the oldest day partway through. That day's total then looks
  whole but is only part of the day.

- **Count a lane's tests yourself.** The report said 10 and the file had 6.
  Nothing broke, but a count in a report is a claim like any other.

## 2026-09-23 - A claim about how a counter behaves across a restart is a claim about where it is stored; and a number spliced from a registration carries its errors with it

Two patterns from the forty-ninth session, which filled #118's result
document. Both were caught by `measurement-skeptic` before commit, not by
the session that wrote them.

- **Before writing that a restart resets a counter, or that a counter shows
  no gap, read the writer.** The skeleton said the 15:48Z deploy "restarted
  the runner, which resets `scout_watch_log.cycle_count`", and the filling
  session then read "126 counts over 125.01 intervals" as proof that no
  cycle was lost. Both claims were wrong: the counter is a database upsert
  (`cycle_count = cycle_count + 1`), so nothing resets it, and the day
  before showed 92 counts over 89.71 intervals across three restarts. A
  boot can *add* a count, so a lost cycle plus a boot cycle gives the same
  total. A count that matches the span is consistent with continuity, and
  that is all it shows.

- **A figure copied from a registration into its result is re-derived, not
  trusted.** The registration's "3.75 h of 24 (15.6%)" for the partial day
  was 4.25 h (17.7%): 10:00Z → 14:15Z. The skeleton copied it and the
  filled draft kept it. The registration is not edited, since it is the
  record of what was fixed in advance. The result says the number was
  wrong, and gives the right one beside it.

## 2026-09-22 (sixth) - An ordering recorded only in a ticket's prose is invisible to the board that dispatches from it; a scheduled task that must wake the machine depends on power-plan state its own XML does not show; and a result document written before its data is a registration one level down

Three patterns from the forty-eighth session, a short one taken twelve
hours before a one-shot read.

- **When Joe orders one ticket after another, encode it as the dependency
  edge the board reads, and write on the ticket the date the edge comes
  off.** Joe's (b) to #117 put #115 behind #58; it was recorded in a
  comment, and `board.py` — which reads
  `issue_dependencies_summary.blocked_by` and nothing else — listed #115
  READY under `owner:main` for three sessions. Prose on a ticket is read by
  a person once; an edge is read by the board every session. The
  auto-unblock date (10-06) is the same kind of decaying clause, so it goes
  on the ticket beside the edge as the instruction to remove it, not as a
  fact a later session must rediscover.

- **`WakeToRun=True` in a task's XML is a request, not a guarantee; the
  power plan decides whether wake timers are honoured, and it can differ
  by AC and DC.** The laptop arm for #118's T1 was rehearsed green with
  the machine awake, which proves nothing about 02:05 AM. `powercfg /query
  SCHEME_CURRENT SUB_SLEEP RTCWAKE` showed wake timers enabled on AC and
  disabled on battery; `HIBERNATEIDLE` showed hibernate after 15 minutes
  on AC. Neither is visible from `schtasks` or `Get-ScheduledTask`. **When
  an arm's failure mode is "the machine was asleep", read the power plan,
  not the task.** The finding went to Joe as one sentence — the fix was
  his to make and Arm A did not need it — rather than as a power-plan
  edit twelve hours before the window.

- **Write the result document's skeleton before any row of its data
  exists: every outcome branch with its consequence, the VOID checks
  first, every datum a slot.** A branch written after one is true reads as
  the finding; five branches written before any is true read as the
  partition, and a reader can check that it was applied rather than
  chosen. The skeleton also moves the "which read counts" and "which
  checks come first" decisions to the day before, when no read can
  flatter them. The marker guard
  (`tests/test_a_question_for_joe_has_a_ticket.py`) fired on a template
  line in the skeleton — the marker with a placeholder number — and the line was
  reworded: a skeleton is in the record from the moment it is committed
  and is held to the same rule as a result.

## 2026-09-22 (fifth) - A fixed-window reading nobody can attend is taken by two schedulers with different failure modes, and the rule for choosing among their reads is registered before any of them fires; an amendment's number is read from the file it amends

Two patterns from the forty-seventh session. The first is the session's
whole build; the second was caught by the `pre-registrar` before commit.

- **When a pre-registered window falls at an hour no session survives to,
  automate the read with two arms whose failure modes differ, rehearse
  both today on the same read-only path, and register in advance which of
  the several resulting reads counts.** T1 was 55 minutes at 02:00 PDT,
  `n = 1`, one slip landing at 02:00 PDT again. A GitHub cron is late, not
  absent (245-minute max gap on record), so it fires four times inside the
  window; a laptop task is punctual but sleeps; each covers the other's
  hole. Several reads then exist, and *choosing* among them after seeing
  them is the degree of freedom the registration exists to remove — so the
  rule (latest qualifying read; monotone counters make that the
  conservative one) went into the registration before the first fire. **A
  rehearsal is free only if the path is provably read-only**; check the
  route and the QueryDef cost class at file:line before calling it free.

- **An amendment's ordinal comes from the file it amends, not from the
  session's memory of other files.** "Amendment 3" was assigned because
  another registration in the same directory had Amendments 1 and 2; this
  one had none. A sequence with a gap reads as two lost amendments, which
  is exactly the quiet defect a registration must not carry. Grep the
  target file for `^## Amendment` before numbering, and say so in the
  brief to whoever writes it.

## 2026-09-22 (fourth) - A pass placed behind a liveness gate never runs on the population it is for; an invariant a sibling table got at birth may be structurally unavailable to the one you extend; and a new write ahead of a cycle's decision variable inherits that variable's default on failure

Three patterns from the forty-sixth session. The first was caught by
reading the gate before accepting the placement; the second by reading the
migration precedent before writing the column; the third by the runtime
review, after the tests were green.

- **Before placing a periodic pass behind an existing gate, ask what the
  gate is false for — that is usually the population the pass exists
  for.** `anything_in_progress` is true while an open position has a
  pending leg whose game has started; it is false once every leg has
  resolved, which is the common state of a combination the venue has
  settled. A close pass inside `watch_once` would therefore have closed
  settled rows only while some *other* ticket was live, and a quiet desk
  would have kept dead rows open indefinitely. The proposal read naturally
  ("settle, then close, then re-price") and was wrong for the rows that
  mattered. **Run the gate's predicate against the state the new pass is
  meant to act on before accepting the placement.**

- **A table-level CHECK cannot be added by `ALTER TABLE`, so an invariant
  a sibling table got at birth may be structurally unavailable to the
  table you are extending — state the asymmetry, or a later session will
  "fix" it with a rebuild on the live record.** `parlay_position_legs`
  carries `(outcome = 'pending') = (resolved_source IS NULL)` because it
  was created with it. `parlay_positions.closed_source` cannot have its
  twin: the column arrives by `ADD COLUMN`, only a column-level CHECK can
  ride it, and every row closed before the column would violate the
  invariant anyway. The writer enforces it instead. **When two tables
  share a pattern and one of them is being retrofitted, write down which
  guarantees the retrofit cannot carry and why**, in the ADR and beside
  the column, so the missing CHECK reads as a decision and not a gap.

- **A new statement placed ahead of a cycle's decision variable inherits
  that variable's default when it raises — and the default is usually
  "do nothing".** `busy = False; try: <new pass>; busy = gate(); if busy:
  watch_once()`. Green tests, correct behaviour, and one `database is
  locked` from the new write would have skipped the settle, the re-price
  and every push, then slept the idle interval while a game was live —
  hedge alerting silently off, into a log stream with ten minutes of
  retention. The tests could not see it because none of them made the new
  pass fail. **When adding a step before the line that decides what the
  rest of the cycle does, give it its own handler and write the test that
  makes it raise on the busy path.** The runtime review found this, not
  the suite; a unit suite tests the step, not what the step's failure
  does to its neighbours.

## 2026-09-22 (third) - Read a ticket's Done-when against the tree before dispatching it; a Must-not-touch can contain a file the change falsifies; a loose prefix turns a drift guard into a phantom-defect reporter; and the machine's clock is not the clock

Five patterns from the forty-fifth session. The first four were caught
before a lane started, by reading each ticket's executable line against
the current tree rather than trusting that last session wrote it. The
fifth was caught after the deploy, by a timestamp GitHub wrote.

- **A ticket written at the end of one session is not dispatchable at the
  start of the next until its Done-when has been run against the tree.**
  #132's recipe required a test file green whose line 98 pinned the exact
  literal the change removes, and that file was not in Lane owns. A lane
  either stalls or keeps a dead `=== 0` filter to satisfy the pin — and
  the second is a bug that the ticket's own regex Done-when would have
  passed. **Before dispatching, grep the tree for every literal the change
  removes and see which test pins it; that test is in Lane owns or the
  ticket is not ready.** This is the third ticket in a week wrong in its
  executable line (#124, #95, now #132) and the first caught before a lane
  ran.

- **A source-regex Done-when that names two fields passes while the
  change drops rows from the screen.** "The live predicate names both
  `pending_legs` and `venue_settlement`" is satisfied by editing one of
  two hand-written filters, after which a row can match neither and
  vanish. **When a partition is two filters, the spec is one predicate and
  its negation, and the Done-when pins the negation** — exhaustive and
  disjoint by construction is a property of the code shape, not of a
  regex over it.

- **A ticket's Must-not-touch list can contain a file whose comment the
  ticket's own change falsifies.** #132 broadened what `nothing_pending`
  means while `api.ts`, whose doc comment defined the old meaning, was
  forbidden. Same rule as the screen copy
  (`test_no_screen_still_tells_him_that_closing_the_page_buys_more`): the
  fix and the words ship together or the words lie in the interval.
  **When a change redefines a reason string, grep every comment that
  defines it, in every language in the repo, and put those lines in Lane
  owns.**

- **Do not plan anything against a clock window on the machine's own
  clock until it has agreed with a remote one.** The session's first
  `date -u` printed `07:40:58 UTC`; it was 14:40Z. Every clock statement
  in the plan ("the target day opens in ~2h", "nothing dated is due
  today") was seven hours wrong, and the deploy that was reasoned to land
  *before* the #118 measurement day landed six hours *into* it. It was
  caught only because GitHub stamped the deploy run at 15:48Z. Nothing was
  voided this time, because the VOID rule's deploy criterion is about a
  value changing, not a restart — but a registration with a "no deploy
  inside the day" criterion would have been void before the session knew
  what day it was. **At session start, read `curl -sI https://api.github.com`'s
  `Date` header beside `date -u`; if they disagree, the machine's one is
  the wrong one.** The same fixed-window discipline the #118 registration
  demands of the instrument (`spend.day_start_ms` must equal the day you
  meant) applies to the session's own sense of when it is.

- **A drift guard built on a constant prefix inherits every constant that
  shares the prefix.** `COMBO_BOOK_` collects the four state constants as
  well as the three reason constants, so a guard that compares that set
  to the `combo_book_reason` union is red on a clean tree — and a ticket
  that says "report drift, do not fix" then reports a defect that does
  not exist into the record. **State the prefix exactly, state the
  exclusion, and verify by hand that the sets match today before the
  ticket says they should.**

## 2026-09-22 (second) - A venue action takes its population from the venue at the moment it acts; a board's READY count can be eleven and dispatch nothing; and a dated count in a code comment decays like one in a doc

Four patterns from the forty-fourth session. The first cost nothing tonight
because the instrument was built to read the venue; it would have cost a
wrong RFQ if the operator's list had been trusted instead.

- **A mirror's "live" row is a fact about the mirror. An instrument that
  acts at the venue re-derives its population from the venue at the moment
  it acts.** `/api/hedge` at 03:55Z listed two positions with pending legs;
  the sell-side ask at 05:11Z was refused on both as *not held*, because
  Kalshi had finalized both combinations at 04:23Z and 04:33Z while the
  desk's legs -- resolved from the runner's market-results pass -- still
  read `pending`. The screen was right about the record and wrong about the
  world by one pass. **Pick tickers for a venue write off the venue's own
  positions read, never off a screen, and let the instrument refuse when
  the two disagree** -- that refusal is the measurement, not a failure.
  Same shape as `at_venue` (ADR 0136): the desk says what it cannot see.

- **`READY N` on the board counts open, unblocked, unassigned leaves and
  says nothing about who can take them.** Eleven READY tonight: eight
  `owner:joe`, three `owner:main` with a start date or an appointment,
  **zero `owner:agent`** -- the lane fleet had nothing to do and every
  session was collapsing into main doing everything. The fix was to write
  tickets (two landed under #82), not a board warning: four sessions of
  tooling was the pattern to break. **Read the owner split under
  FRONTIER before calling the frontier full.**

- **A count with a date in a source comment decays exactly as it does in a
  doc (ADR 0162), and a lane will write one.** The #130 lane put "41 of 43
  open positions live 2026-09-22" into `api.ts`'s type comment. It was true
  at 03:55Z and wrong by 05:11Z. Trimmed on merge to "most rows; re-read
  `/api/hedge`". **When reviewing a lane diff, grep it for a digit followed
  by a date before merging.**

- **A "decayed justification" claim is itself a claim; read the WHERE
  clause before ticketing it.** `partner` said `watched_tickers`' docstring
  ("bounded by how many tickets one person holds") had decayed to "ever
  held" because nothing auto-closes a position. Its SQL filters
  `l.outcome = 'pending'`, so the list is bounded by live legs regardless
  of `status`. No ticket was opened. The reviewer was right about the
  screen (`positions.map` over every open row) and wrong about the watcher,
  and the two claims arrived in one paragraph with equal confidence.

## 2026-09-22 - A new read on a request path inherits the old read's population or it drifts; and a tripwire on a shared symbol fires for whichever path reaches it first

Two patterns from wiring #95's reader (#128). The review caught the first;
a failing test caught the second.

- **When a new venue read joins a request path that already has one, hold
  it to the predicate the existing read uses, or the two populations drift
  apart on the same screen.** `/api/hedge` already read leg quotes for
  `DISTINCT` tickers with `outcome = 'pending'`. The new combination-book
  read was looped over `open_positions` -- `status = 'open'`, which on this
  desk means unclosed bookkeeping, not a live game: 43 rows open, 2 with a
  pending leg. Shipped as first written, every page load would have made 38
  venue reads in series for 36 books with nothing left to sell into, on an
  unauthenticated route under a 30 s proxy ceiling, on the same client and
  limiter the armed order path queues behind. I had filed that as "measure
  the latency on live, then decide"; the reviewer filed it as "guard before
  merge", because the states to degrade into already existed and the guard
  cost ten lines. **The check is mechanical: list every venue read the
  route already makes and the predicate on each; a new read with a looser
  predicate than its neighbours is the defect, before any timing is taken.**
  The second half of the same rule: **bound the wait, not just the count** --
  a per-read `wait_for` into an existing "unreadable" state is what keeps one
  hung ticker from taking the whole screen down.

- **A tripwire on a shared symbol proves nothing about the path you meant
  until every other path to that symbol is stubbed.** The demo test
  recorded `KalshiConfig.load` to prove the combination reader was never
  constructed on a keyless instance. It fired -- from the LEG quote path,
  whose lazily built `LiveQuoteSource` calls `load` itself and then dials
  the real venue with four retries a leg. The same unstubbed path made the
  timeout test measure a fifteen-second wait that had nothing to do with the
  timeout. Neither test was wrong about the wiring; both were wrong about
  what they were observing. **Before asserting "X was never called", grep
  for every caller of X the app under test can reach, and stub each one
  the test does not mean to exercise** -- the existing `quote_source=`
  injection on `create_app` was there for exactly this and three other test
  files already used it.

## 2026-09-21 (third) - A sample's negative result becomes a universal about the world in one sentence; a ladder's rungs can all be the same number; and an instrument that reports "today" cannot report yesterday

Five patterns from the orchestration session. The first one is mine and it is
the one that would have reached a screen.

- **A negative result from a sample gets written as a universal about the
  world, and the flattering direction is "this thing does not exist" - because
  absence licenses a smaller build.** #107's capture failed a third time, and I
  wrote *"across three attempts, a non-empty combination YES side has never
  been observed"* into a ticket comment **and** into a lane brief. It is false:
  `2026-09-17-combinations-can-be-exited.md:40-41` measured resting public-book
  YES bids of 5.10c/38,709 deep and 0.32c/24,900 deep. **The same comment
  contained its own counterexample two paragraphs later** - the careful version
  ("different population, not refuted") and the overreaching version were
  written side by side, and the overreaching one is what a lane transcribes
  into a docstring and from there into copy. The true claim was always
  narrower and was about **this repo's disk**: *no committed capture fixture
  carries one*. **When a sample comes back empty, write the sentence about the
  sample, and say where the sample was drawn from in the same sentence.** This
  was the fourth frequency clause about combination liquidity to be written and
  withdrawn (three earlier ones are catalogued in `parlays/page.tsx:95-127`)
  and the first caught before shipping - by a review, not by me.

- **When a decision is presented as a ladder, an effective ceiling is the raw
  cap MINUS the consumer's own reservation - and computing it without that
  makes two rungs look different when they are identical.** Joe was asked #116
  against *3 convenings -> searches at 5/day -> calls at 6/day -> tokens*. The
  5/day is `60 / 12` with the watcher's reserve left out:
  `scout_watch.py:198` holds back `STAFF_PAIR_SEARCHES_WORST_CASE * (1 +
  reserve_taps)` = 36, so it refuses above 24 used - **three convenings,
  identical to the allowance**, while tokens allow 2.9. Three rungs, one
  number. The 5/day figure was real but described a **tap**, which reserves
  only 12. **Read the consumer's reservation, not the config value, before
  ranking anything** - and when the rungs coincide, say the ordering question
  is unanswerable rather than sizing a sample for it.

- **An instrument that reports "today" cannot report yesterday, and a read
  window planned without that lands outside the population it means to read.**
  The #118 trip was planned for 09-23 10:30-14:00Z. `/api/scout` reports spend
  for the budget day containing *now*, and the day rolls at 10:00Z - so that
  snapshot describes 09-23 (thirty minutes old), not the 09-22 day being read.
  The whole token half would have collapsed to "not separable" **by
  construction**, and the write-up would have blamed the instrument. **Check
  which period an instrument's numbers cover against the period you mean to
  measure, at the moment you pick the clock time.** The fix was a second
  reading *inside* the target day, with a self-verifying pre-condition
  (`spend.day_start_ms` must equal the day you meant) so a mistimed trip voids
  itself instead of reporting.

- **A hunt that fails three times is usually sampling the wrong population,
  not running out of luck.** #107 sampled currently-quoted combinations at an
  arbitrary instant, three times, and found nothing - while the reading it was
  trying to reproduce came from a combination Joe had **just bought**, where
  ADR 0164 says a resting bid is residue of a recent print. The defect was the
  **trigger**, not the sample size: a calendar cannot find a residue. **Before
  scheduling a fourth attempt, ask what the successful observation had that the
  failures did not** - here, a live position, which is one call to check and
  which no amount of re-sampling would have supplied.

- **A "Done when" is the executable line, and a re-scope recorded anywhere else
  does not amend it.** Two ran into this in one session. #95 was re-scoped to
  absence-first in a review comment while its Done-when still demanded a test
  that the payload *attaches the resting YES bid* - unprovable, so a literal
  lane stalls or invents. #124's own profile comment said not to raise
  `timeout-minutes`, while its Done-when still said *"the workflow change is on
  main AND a CI run has completed green with the new configuration"* - so a
  literal lane does the one thing the ticket forbids. Both bodies were correct
  in prose and wrong in the one line an agent executes. **Rewrite the Done-when
  in the same action as the re-scope**, and generalising last session's lesson:
  its named test must be runnable - check the harness exists, not just the
  instrument. #95's said "a named frontend test" and **`frontend/` has no test
  runner at all**, so satisfying it literally meant standing up vitest.

---

## 2026-09-21 (second) - A deadline can expire into a missing instrument; a ruling recorded only as a ticket comment decays like a question recorded only as a line; and a guard with a backstop behind it tests green either way

Five patterns from the session that armed the record behind unattended
scouting. Three of them come from things that were already decided or already
measured and were invisible to the thing that reads the queue.

- **A ticket's "Done when" can name a reading no committed instrument can
  take, and nobody notices until the clock expires.** #118 shipped with a
  24-72h deadline for a reading of `trigger = 'auto'` rows by budget day.
  Three hours in, a grep found **zero readers of `scout_briefings` anywhere
  in `scripts/`** - no QueryDef in either registry named the table - and
  `flyctl ssh` may only run a committed script by path. The reading was
  BLOCKED ON INSTRUMENT from the moment the deadline was written, and a new
  QueryDef needs a deploy before it can be read on live, so discovering this
  at 14:15Z tomorrow would have meant building, deploying and reading late.
  **Check the instrument exists when the deadline is WRITTEN, not when it
  expires.** The same check catches the cheaper half: `/api/scout` serves
  briefings but its SELECT never reads `trigger`, so no served surface could
  separate an unattended convening from one Joe tapped - which is the entire
  purpose of the v51 column.

- **A ceiling that was ranked last is the one that binds, and the arithmetic
  that ranked it was ours.** The ladder put to Joe on #116 ran *3 convenings
  -> searches at 5/day -> calls at 6/day -> then tokens*. Measured on the
  first afternoon: the search figure was right to the decimal (5.0) and
  **tokens bound first**, at ~170K a convening against a 500K budget - 2.9 a
  day, tighter than the 3-convening brake he approved. He answered a question
  about the wrong brake. **When a decision is presented as a ladder, the
  cheapest check is to divide the budget by one observation of the unit cost,
  for every rung, before asking.** Nobody had ever measured a convening's
  token cost; the ranking was structural reasoning presented as arithmetic.

- **A partner's re-spec recorded only as a ticket comment decays exactly like
  a question for Joe recorded only as a NEXT.md line.** CLAUDE.md step 7 gave
  "ask Joe" a forcing function - a numbered sub-issue - because a line decays
  into the instrument that raised it. A ruling that changes a ticket's *scope
  or dependencies* has no such function. #107's 2026-09-20 comment said "#95
  ships the absence path first ... not yet executed"; a day later #95 was
  still `blocked:1` and invisible to the board, because `scripts/board.py`
  reads GitHub's `blocked_by` **edge**, not the comment thread. **A decision
  that changes what the queue shows must be written where the queue reads,
  in the same session it is made.**

- **A guard with a backstop behind it passes its own test either way, and
  only the mutation says so.** `record_watch_outcome` refuses an unknown
  outcome before touching the database. Its first test asserted "no row was
  written" - and stayed **green with the guard deleted**, because the table's
  own CHECK rejects the insert and the function's broad `except` swallows it.
  Identical observable, guard or no guard. **When a guard sits in front of a
  second mechanism that produces the same end state, the test must pin what
  the guard uniquely changes** - here, that the connection is never touched
  (a stub raising on `execute`) and the reason is logged at ERROR rather than
  appearing as a swallowed traceback. Same family as the 2026-09-18 lesson
  that a fake modelling the venue's good behaviour cannot test a guard
  against its bad behaviour.

- **A ceiling that refuses before it writes leaves the schema unable to
  answer the question the schema was given a column for.**
  `scout_briefings.refusal_reason`'s own comment says "which ceiling
  refused", and **none of the four ceilings that gate a convening writes it**:
  all three pre-flight paths return or raise before their `INSERT`, so a row
  reaches `status = 'refused'` only from inside a desk run already under way.
  This is the #71 shape (`SHARD_HEADROOM` refuses with a 400 and writes no
  row) and the `odds_sweep_log` shape (a refused sweep left no trace, and
  odds fetching ran 17+ hours behind a green health check) in a third place.
  **When adding a brake, ask where its refusal is written before asking
  whether it works** - and record it as its own table, because absence never
  borrows presence's representation: a synthetic row in the presence table
  gets counted by every reader that counts presence.



Seven patterns from the session that turned unattended scouting on and
diagnosed the disk. Five of them come from `measurement-skeptic` returning
**OVERSTATED - do not enter as written** on the first draft of the
measurement, before it was committed. The audit was right on every count
that mattered, and the corrections are worth more than the finding.

- **When a diagnosis has candidate locations, ask which instrument separates
  them at zero cost - and run that one first.** The handoff named `db-sizes`
  (`WALKS_THE_FILE`) as the next step for "what grew?". But two of the three
  candidate homes for the missing 1.22 GB were not inside the database at all
  (a WAL that could not checkpoint; a leftover `VACUUM INTO` copy), and
  `inspect_live_disk.py` separates all three for **nothing** - `statvfs`,
  `walk` and `stat`, never opening a file it lists. It killed both
  non-database hypotheses (the WAL was 3.4 MB against a 1.22 GB question)
  before one expensive page was read. The free read was also the
  **like-for-like** one: it is the instrument that produced the baseline file
  size being compared against, which `db-sizes` is not. **Order the
  instruments by cost before ordering them by how much you want the answer.**

- **Before spending a `WALKS_THE_FILE` read, grep the record for what the
  LAST one was asked to also collect.** `docs/measurements/2026-09-18-where-the-database-bytes-are.md:104-111`
  ends: *"One extra column on the next `db-sizes` run settles it"* - meaning
  `dbstat.unused`, which separates "rows were added" from "pages bloated".
  The next `db-sizes` run was 2026-09-21 and it went **without the column**.
  A whole-file walk was spent, the desk lost its page cache, and the question
  that walk had been queued to answer is still open - which is exactly why
  the diagnosis came back "two explanations, cannot separate them". **An
  expensive instrument accumulates a to-do list in the documents that last
  used it, and that list is not attached to the instrument.**

- **A cheap moment to spend a cache flush and a quiet moment are the same
  moment, so choosing the reading on cost is choosing it on the outcome.**
  The third file-size point was taken over 14.1 hours "ahead of the kickoff
  windows", got 26.7 MB/day against a flagged 580, and was written up as
  falsifying it. That window is Sunday evening into Monday morning - the
  quietest stretch of the football week - while the 580 window held the whole
  Saturday college slate and the whole Sunday NFL slate. Both growing tables
  are duty-cycled to game action by design (`kalshi_quotes` is a change log
  that writes only when a price moves, ADR 0055; `odds_snapshots` drops to
  the hourly floor unattended). **A 22x ratio is what a *stationary* recorder
  with that duty cycle predicts.** A re-measurement must be **phase-matched**
  to what it is re-measuring: same clock time on consecutive days, or a
  window holding exactly one of each weekday. Adjacent is not comparable.

- **Correcting someone else's comparator choice is itself a comparator
  choice, and it runs the same risk in the opposite direction.** The draft
  accused the previous session of quoting 580 against "the registered
  ~85-110 MB/day" - the smallest of three circulating quantities, which
  maximised the gap - and re-framed it as "1.8x" against
  `CURRENT_GROWTH_RATE = 326.6` (`backend/store/volume.py:149`), "the
  constant the system actually runs on". But 326.6 was measured **2026-09-09,
  before the dedup shipped**, and its own comment says it is expected to fall
  to ~142. So the draft picked the comparator that *minimised* the gap, while
  accusing its predecessor of picking the one that maximised it, **on a
  result that was good news.** Against the post-dedup expectation, 580 is
  ~4-7x and the predecessor was approximately right. **When a name covers
  three numbers, print all three with what each was measured on and when -
  do not pick one and call it "the" registered rate.** (CLAUDE.md's
  `actionable` rule, on a new quantity.)

- **A prune in perfect health and a broken prune look identical from outside,
  because a prune's instruments are scoped to the rows it is allowed to
  touch.** `kalshi_quotes` grew 0.80 GB in three days while `prune-frontier`
  reported `backlog_rows 0` and a frontier **54 seconds ahead of** the 3-day
  cutoff - flawless, and ~53 M rows deleted over its life. The growth is in
  the **exemption**: `retention.py:231` spares any quote whose ticker is in
  `recommendations`, that table has no `DELETE` anywhere, so the spared set
  is strictly monotonic and is now 26.2% of all rows. **When a table with a
  retention rule grows, measure the exempt population, not the prune's
  progress.**

- **Two mechanisms that predict the same observation are not a finding, and
  "the next reading will tell us" is only true if it can.** The draft argued
  the exemption set was too small to explain 0.80 GB (4.6 M rows needed
  against 3.04 M exempt, at the family's average 172 bytes/row) and concluded
  the season must also be contributing. Inverted, the exempt rows alone cover
  it at 263 bytes/row - a factor of only 1.53 - and page bloat in a
  continuously-pruned random-order index covers it completely and
  independently. The signature was in the draft's own numbers, reported as
  corroboration: index +79.3% against table +57.7%, and a freelist that
  quadrupled. Worse, the planned follow-up (`MAX(rowid)` differencing) is
  **blind to fragmentation**, so the stated decision rule - flat inserts plus
  rising bytes implies the exemption - names the fragmentation signature and
  reads it as the opposite. **Before writing "the next reading separates
  them", check that it separates them.**

- **A guard can be green because it cannot see the failure.**
  `tests/test_a_question_for_joe_has_a_ticket.py` passed on a measurement
  that raised a decision only Joe can make and carried **no ticket at all**.
  It refuses a `Question for Joe:` marker without a number; it cannot refuse
  a *missing* marker, so the omission that the rule exists to catch is
  precisely the one it is blind to. The audit caught it, not the suite.
  Related, same session and same shape: the standing "never hand-type a git
  sha" lesson was applied correctly on the deploy path and then violated in a
  **GitHub issue close comment** - permanent, public, and read by future
  sessions as fact. **Apply a lesson to every surface its hazard reaches, not
  to the one where it first burned you**; the tell is identical everywhere -
  a sha not pasted from a command's output in this session.

- **A test that picks its branch from the AMBIENT environment is a
  coincidence, not a guard - and "green here" proves nothing about there.**
  `_q_db_sizes` wraps its `dbstat` query in `try/except OperationalError`.
  This repo's dev `sqlite3` (3.45.1) has **no `dbstat` compiled in**; CI's
  interpreter and the deployed image both **do**. A lane wrote fallback
  tests that exercised the except branch "for real, with no monkeypatching
  needed" - true locally, false on CI - and **three tests went red on CI on
  a commit whose production code was correct and had already served a good
  live reading**. Two rules fall out. **Force the branch you claim to
  cover**: a connection subclass whose `execute` raises on the exact
  production statement (`sql.startswith(_SQL_DBSTAT)` - narrow, because a
  build without the vtab can still `CREATE TABLE dbstat`) makes both
  branches reachable from either interpreter, and where a path genuinely
  cannot be forced, assert only the invariant that holds on both. And
  **never write a guard that fails when the environment gains a
  capability** - the lane's `assert _real_dbstat_available() is False` was
  meant to flag a stale skip and instead turned more coverage into a red
  build. The related over-claim is worth naming too: the finding was
  reported as "the real branch has never been exercised, locally or in CI."
  Only the local half was true. **A capability absent on your machine is
  not absent everywhere - check the other machine before writing "never".**

- **A test of an interceptor must send the traffic the interceptor is aimed
  at - and the fix for an environment-coupled test can be environment-
  coupled in the same way.** Having diagnosed the above and written
  `_NoDbstatConnection` to FORCE the fallback, the test proving the
  interceptor works probed it with an ad-hoc `SELECT * FROM dbstat` while
  the interceptor was deliberately pinned to `_SQL_DBSTAT`. It never
  matched. Locally the probe raised anyway - this venv has no `dbstat` at
  all - so the test passed **without the interceptor ever running**, and CI
  returned `DID NOT RAISE`. **Two CI runs, ~20 minutes, to the same class of
  bug in the fix for that class of bug.** Three habits fall out, all cheap:
  drive the assertion from the **subject's own output** (read the emitted
  title to learn which branch ran, rather than re-probing the environment
  and assuming the two agree); **simulate the other environment locally**
  before pushing - here, a plain table named `dbstat` makes the success
  branch reachable on an interpreter that has no vtab, and that one probe
  would have caught both failures; and when a test passes, ask **which line
  would have failed if the thing under test were absent.**

- **Never put prose through `bash -c "..."`; backticks inside a
  double-quoted shell string are COMMAND SUBSTITUTION, and the loss is
  silent.** Twice in one session a Python one-liner that wrote Markdown was
  invoked as `python -c "..."`, and bash expanded every `` `backticked` ``
  term before Python ever saw the string. Both times the write "succeeded" -
  it printed `updated` - and every code-span in the result was **replaced by
  empty string**, leaving grammatical sentences with the identifiers missing:
  *"so `` `` 's real branch"*. The second occurrence also executed fragments
  of the file's own contents as commands, including a bare `flyctl`, an
  `unlink` and a `truncate`; they failed only because they had no operands.
  This repo already carries "heredocs mangle backslashes - use Write for
  regexes"; the same hazard reaches **any** shell-quoted content, and
  Markdown full of code spans is the most exposed thing there is. **Write
  prose with the Write or Edit tool, always.** The tell after the fact is a
  sentence that reads fine but has a gap where a name should be.

---

## 2026-09-20 (second) - A constant in the source beats a week of sampling; a plan shape is not a cost in either direction; and a Done-when can expire with nothing going red

Five patterns from the session that answered #116 without the week it had
been told to wait for, and timed two index changes on live.

- **Before scheduling a measurement, ask what BOUNDS the quantity, not what
  it usually is.** #116 asks how much unattended scouting costs a night. The
  previous session took one reading (9 fixtures), correctly said one reading
  is not a rate, built a 7-day series and parked the ticket behind "a deploy
  first and then a week". The binding number was a constant: `CARD_SHAPES`
  is nine fixed recipes whose `max_legs` sum to 30 at one leg per game, so a
  night's ladder can carry **at most 30 distinct fixtures, ever** - no
  sampling, and true of every future night as well as every past one. A
  sample describes the nights it saw; a structural ceiling describes all of
  them.

- **An instrument built to answer a question can measure the question next
  door, and its own docstring may already say so.** `ladder-fixtures` was
  built for #116 and counts fixtures with a fresh team-market leg - the
  candidate **pool**. The convener walks the ladder **payload's** distinct
  fixtures (`scout_watch.py:178`, the same `build_ladder_payload_widening`
  the route calls). The gap is an order of magnitude: 135 in the pool on
  2026-09-08 against 6 on the cards. The docstring said it plainly - "best
  read as a loose UPPER BOUND ... not the number the ladder actually built
  cards from" - and the handoff still carried it as the number Joe would be
  asked to fund against. **Open the line of code that CONSUMES the quantity
  you are funding, and check the instrument computes that one.** Reading the
  consumer also found that the watcher calls the *widening* builder, so
  "tonight's ladder" is tomorrow's games whenever tonight is empty - a
  property of the flag nothing in the ADR or the ticket stated.

- **"It scans the whole index" is not a cost claim, and a plan shape is not
  a stopwatch - in BOTH directions.** This record already carried `2e66f36`,
  where an index was dropped because a plan said it changed nothing and had
  to be restored: *"the plan was never the cost."* Tonight the mirror image.
  #87 added a `WHERE` to bound a `GROUP BY odds_snapshots` whose plan said
  SCAN, the plan afterwards said SEARCH, and the stopwatch on live found
  **no improvement at all** (489.3 ms bounded and cold against 423.5 ms
  unbounded and warm, row sets agreeing at 249). The reason: the aggregate
  rode a *covering* index shaped exactly for it, so the "whole-index scan"
  was one ordered pass collapsing 5.4 M entries into 1,292 groups, and
  replacing it with 930 seeks plus a scan of `event_links` is not cheaper.
  **A covering index makes a full pass cheap; 5.4 M rows over 1,292 groups
  is a ratio to check before calling an aggregate expensive.** (The fix was
  not reverted - it is correct and scales with the smaller table. What did
  not survive is the claim that it bought something.)

- **A ticket's Done-when can expire without anything going red.** #88 asked
  for a timing "run twice on live (before task 02 merges/deploys, and
  after)". #87 merged and deployed, the "before" became permanently
  unobtainable, and the ticket sat on the frontier looking runnable, because
  the board checks blockers and assignees and not whether a completion
  criterion is still *reachable*. A Done-when naming an **artifact** (a test,
  a file) keeps; one naming a **state of the world** has an expiry nobody
  wrote down. The re-spec was also the better measurement - both texts timed
  back to back on one connection beats a before/after across a deploy, which
  would confound the edit with a restart and a different cache.

- **Two registries can guard one surface from different files, and a
  ticket's named tests reach only one.** Adding a `QueryDef` to
  `scripts/inspect_live_db.py` must also be added to `SUBCOMMANDS` in
  `tests/test_inspect_live_db_modules.py`, which asserts in both directions
  so the list cannot rot into a subset. The failing file is not the file the
  query is registered in, so a targeted run of the ticket's own tests passes
  and CI does not. Both main and the Sonnet lane hit it independently in one
  evening. **When a change adds a NAME to a surface, grep the tests for an
  existing name on that surface before running anything** - the pin that
  will catch you is wherever that grep lands, not where you edited.

- **A merged lane is not a finished lane: removing its worktree while it is
  still running destroys whatever it is mid-way through.** Main merged
  `fbf8601`, applied the one fix the lane had been told to make, and removed
  the worktree - while the lane was part-way through a full-suite re-run of
  that same fix, which it had independently redone in its own tree. It lost
  the run and reported finding only an empty `.pytest_cache` where its
  worktree had been. Nothing was lost here because the work was a duplicate
  of main's, and that is luck, not design. **A lane's commit landing on main
  says its output arrived, not that the agent has stopped.** Wait for the
  hand-back, or tell it explicitly that the work is already on main and it
  should stop, before taking its tree away.

- **Before splitting a question into "his half" and "ours", re-read the
  ticket: the thing you were about to ship unasked may already be one of his
  lettered options.** The session's direction proposed shipping half of #79
  on the argument that *refusing* a suppressed parlay leg changes what Joe
  can bet while merely *marking* it does not, so the mark was ours to ship.
  #79 offers four options and **(b) is "carry the leg but mark the card"**,
  framed as a trade-off against (a). Shipping it would have chosen (b) for
  him and then asked him to choose. The reasoning was sound in general and
  wrong against this ticket, and only the body shows which. **A ticket that
  lists an option has already claimed it.**

---

## 2026-09-20 (first) - A lane is cut from where the session started, not from where main is; and an allowlist keyed on who names a symbol moves to whoever you hand the symbol to

Two patterns from the session that let the scout desk be sent unattended
(ADR 0180), plus two recurrences.

- **An Agent worktree is cut from the commit `main` was on when the
  session began.** Four lanes were spawned across the evening; every one
  started from the same commit, including the one spawned *after* main had
  committed the config class and schema column it depended on. The lane
  would have built against a tree where its inputs did not exist and
  reported green on tests it wrote against that tree. `git worktree list`
  shows the base beside every lane; read it after spawning. A brief that
  depends on a mid-session commit says so and tells the lane to
  `git merge` it first, and to grep for the symbol before building.

- **A billed-path allowlist keyed on which module *names* the symbol is
  moved by a factory argument.** The scanner allowlists modules that name
  `build_client`; the lane, told to "pass `build_client` as a factory",
  put the name in `scripts/run_loop.py`, and the only green fix on its
  side was to admit the whole loop script as a spender. The right fix was
  on the other side: default the factory at the site already allowlisted,
  and let the new caller pass nothing. **Whoever holds the name holds the
  ceiling's paperwork; design so the name stays where the meter is.** A
  lane executes the brief literally (2026-09-18 twenty-sixth), so this is
  a choice the brief should have made.

- **Two recurrences, recorded as such.** `git checkout <file>` to undo a
  mutation erased the uncommitted real work in the same file (the
  mutation-testing hazard already in this record); the later mutations
  restored from a `$TEMP` copy with `cmp` proving byte identity. And a
  test seeded a table with `INSERT OR IGNORE`, which swallowed a NOT NULL
  failure and left the table empty, so the test asserted `absent` for a
  game that had a briefing (2026-08-10, "`INSERT OR IGNORE` will happily
  ignore your fixture"). A lesson that recurs twice in six weeks is one the
  session start does not reach; both are now in the memory index as well.

---

## 2026-09-19 (first) - A queue that lives in prose is re-derived every session; a queue that lives in tickets is dispatched -- and a brief that names a sibling lane's deliverable as existing sends the lane to check

Two patterns from the session that moved the backlog onto GitHub (ADR 0179).

- **Where the queue lives decides what happens to it at session start.** For
  a month the Still-open list restated every item in full, and each session
  began by re-reading, re-judging and re-ordering it -- at the top model, in
  the main context -- before touching any of it. The decision queue had
  already shown the decay (2026-09-16 eighth): a question for Joe in prose
  became the instrument that raised it. The build queue decayed the same way
  with nothing going red, because a prose item has no owner, no model and no
  "done when", so the only thing a session can do with it is think about it
  again. A ticket has all three, and the cheapest agent that can prove the
  result takes it. **The test is whether an item can be handed to someone
  without the hander re-deriving it; if not, it is not on a queue, it is in
  a notebook.** The guard now refuses a Still-open item with no ticket
  number, for every item and not only Joe's.

- **A lane told that a sibling lane's file exists will either invent it or
  go and look; brief for the second.** Lane C's brief named `scripts/board.py`
  as "the generated frontier" while Lane B was still writing it. The lane
  checked the tree, found nothing, and wrote the doc against the frontier
  query that did exist, with a note saying so -- the right behaviour, and it
  cost a paragraph at merge. The cheaper version is to say in the brief which
  deliverables are *concurrent* and to write the pointer as the integrator's
  job. The wrong version, which this repo has paid for before, is a doc that
  describes a script from its spec: a citation to a file nobody has opened
  (2026-09-18 twenty-sixth, "a citation is a claim").

- **A full suite started before the lanes merged reports on a tree that no
  longer exists; re-run the named failures on the settled tree before fixing
  any of them.** Tonight's 33-minute run began on one tree and three lanes
  merged underneath it. It reported three failures. Re-run alone on the
  settled tree, one was real (a new fixture not classified in the captures
  table), one had been read mid-merge, and one was the walker's known
  flakiness while a worktree is being written (`test_has_callers.py:172`
  says so in its own comment). Fixing all three from the first report would
  have changed two things that were not broken. The rule for the integrator:
  the full suite is the LAST thing that runs, after the last merge, on a tree
  with no live worktrees — or its failures are re-run one by one before they
  are believed.

---

## 2026-09-18 (twenty-eighth) - A fake that models the venue's good behaviour cannot test the guard against its bad behaviour, and a fixture can exclude a case by arithmetic nobody wrote

Eight guards on the new RFQ fill path were disabled one at a time. Six went
red. **Two stayed green, and neither was decoration — the harness could not
reach them.**

**The first: the fake was doing the guard's job.** `read_venue_fill` calls
`/portfolio/fills?ticker=<combination>` and then re-checks each row's ticker
itself, because the venue's filter is trusted for what it returns and not for
what it leaves out. `FakeApi.fills` implemented the `ticker` parameter
faithfully — so with the re-check deleted, the fake still returned only
matching rows and the test passed. **A fake that always behaves correctly
makes every guard against incorrect behaviour untestable, and the suite
reports that as coverage.** The fix is a fake that can misbehave on request
(`honour_ticker=False`), and the misbehaviour is not hypothetical here:
`/portfolio/fills` answered zero to eight query shapes including `ticker=` on
2026-08-10, so what that parameter does on this endpoint has never been
established.

**The second: the fixture excluded the case for the wrong reason.** The test
for "a fill from an hour before this acceptance is not this bet" used the
file's `now_ms = 2_000`, so "an hour earlier" was an hour before the **epoch**
— a negative millisecond stamp. The guard compares against
`accepted_ms - 5s`; the mutation widened the floor to `0`; and the row was
*still* excluded, by `-3_598_000 >= 0` being false. The assertion passed
without the guard because arithmetic nobody wrote was doing the work.

**The general form: a mutation that stays green has three readings, not two.**
The guard is decoration; or the mutation missed it; or **the test bed cannot
express the state the guard refuses**. The third is the one that looks most
like the first and is the most expensive to misread, because the response to
"decoration" is to delete the guard. Before deleting, ask what in the bed —
the fake, the fixture's constants, the clock — is already refusing the input
on the guard's behalf.

---

## 2026-09-18 (twenty-seventh) - A docstring that says a thing has never been observed is a claim about a date, and other modules quote it as if it were about the world

`KalshiRestClient.fills` said, in bold: *"The per-fill wire shape has still
never been observed on this account."* It was measured empty on 2026-08-09 and
again on 2026-08-10, and the sentence was true when written. **A 33-fill
capture landed on 2026-08-18 — eight of them combinations — and the sentence
stayed there for eleven days.** `portfolio_poll.parse_fill` was written
against that capture, and `test_portfolio_poll.py` has been reconciling a fee
against one of those combination fills since ADR 0073, three modules away from
the paragraph asserting no such row had ever been seen.

**The cost was not the stale sentence. It was what quoted it.**
`combo_rfq.py` carried a comment saying whether a KXMVE fill reaches
`/portfolio/fills` at all, and under what ticker, was *unresolved by this
repo*; `tasks/NEXT.md` restated it as the reason a ticket had become a
measurement; and the session prompt restated it again. Three statements of a
blocked question, all downstream of one negative claim that had already been
falsified by a file in `tests/fixtures/`.

**A negative capability claim decays in the direction that blocks work, and
nothing goes red when it turns false.** A stale "this is safe to leave
undone" gets discovered when something breaks; a stale "we have never seen
one of these" is discovered only by someone who goes and looks, and everyone
downstream has a reason not to. The tell is the phrase *has never been* with
no date beside it, and the cheapest check is a `ls tests/fixtures` and a grep
for the parser: **before inheriting a "nobody knows", grep for the thing
nobody is supposed to have.**

Related, and not the same lesson: `[[justifications-decay-toward-reassurance]]`
covers a comment explaining why something is safe to leave undone. This is its
mirror — a comment explaining why something *cannot be done yet*, which
decays into a backlog item nobody re-examines.

---

## 2026-09-18 (twenty-sixth) - a check handed forward is a to-do, a citation is a claim, and a clock that counts free space has to name the filesystem

Seven patterns from the session that split this file's sibling, measured the
volume, and had three of its own claims refuted before they reached Joe.

- **A trigger that hands the work to the next session fires late by exactly one
  session.** The previous session read `wc -c`, recorded 87%, wrote **"SPLIT
  THIS FILE NEXT SESSION"** into its own entry — and then wrote the entry
  anyway. The rule says read the size *before* writing and cut if it is near;
  reading it, writing regardless, and leaving an instruction converts a check
  into a to-do, and the margin left was one long entry. This is harder to catch
  than a missed check, because the handoff *quotes the rule* and therefore reads
  as compliance. **The session that discovers the file is near the line is the
  session that cuts it**, and the cut goes in before that session's entry, not
  into its handoff.

- **A citation is a claim. Grep the cited file before repeating it, even when
  the person citing it is the one who wrote the file.** This session was told,
  as an instruction, that *"CLAUDE.md's 'two thirds of the file is
  `kalshi_quotes`' is STALE — don't quote it, measure it."* The instruction was
  right about the number and wrong about the location: **CLAUDE.md contains no
  occurrence of `kalshi_quotes` or "two thirds", in any commit.** The sentence
  exists only in `tasks/NEXT.md`, asserting that CLAUDE.md says it. This
  session then repeated the attribution back in its own report before checking.
  The cost of a false citation is a session sent to edit the wrong document, and
  the check is one `grep`.

- **"Pruned", "enabled", "handled", "wired up" name a capability, not a state.
  Name the flag and its deployed value, or do not use the word.**
  `tasks/NEXT.md` told Joe *"`kalshi_quotes` and `fair_prices` are pruned"* as
  an input to a decision he was being asked to make. `fair_prices` has a
  registered, built, tested downsample whose `enabled` defaults `False`, whose
  `dry_run` defaults `True`, and which `fly.live.toml` does not configure — so
  it has never removed a row on live, and `runner.py:381-386` says so in its own
  comment. The sentence that should have been there names the flag. **And the
  conclusion it supported survived by a different fact** — `odds_snapshots` is
  still the only unbounded table, but because the other two are bounded by
  *different mechanisms*, not because both are pruned. That is the third
  instance in a week of a justification decaying into being **right**, which
  reads as verified and is the hard case.

- **A comment justifying stored data is a claim about a capability, and it
  should be grepped for an exerciser exactly as a module is grepped for a
  caller.** `schema.sql:210-213` gives *"the ability to re-run with a different
  method"* as **the** reason `odds_snapshots` keeps raw rows rather than a
  consensus — the largest table in the file, 40% of the database. Nothing in
  `backend/` or `scripts/` re-runs a devig over historical rows; every devig
  call site is fed by a newest-sweep reader. This is "built but never called"
  applied to **data**, and it is worse than the code version: nobody notices,
  because the data is doing something (it exists) and the capability it exists
  for is never invoked.

- **A guard written as a ratio against file size changes meaning when you
  archive half the file.** `test_the_latest_entry_ends_at_a_rule_not_at_eof`
  asserts the parsed entry is under half the file, to catch a parser that ran
  to EOF. `tasks/NEXT.md` has exactly two `---` rules in it, so the parser had
  *always* over-read — swallowing every entry — and the test passed only
  because the archive index made up the other half. After the split it passed
  by **190 bytes**, and the next entry written failed it. The guard was right
  and had been green for the wrong reason for weeks. **When an archive moves
  bytes out of a file, re-run the guards that measure a part of that file
  against the whole of it** — the numerator did not move and the denominator
  did.

- **A two-point difference of a step function is a step, not a rate — and
  before quoting any slope, ask whether its window contains a one-time build.**
  The ~137 MB/day figure this project was planning against is a true file slope
  whose 8.94-day window **contained 624 MB of index construction** (two indexes
  created on 2026-09-10), smeared across it as though it were growth. Differencing
  the like-for-like subset — the table plus only the indexes that existed at both
  ends — gives 76.6 MB/day and needs no assumption about when the build landed.
  Separately, `db_kb` is flat between WAL checkpoints and while free-list pages
  are being consumed, so **79.4% of consecutive passes show zero growth** and both
  endpoints of a short slope can land anywhere inside a step. Two estimators that
  share no code agreeing is what made the answer trustworthy; neither alone was.

- **A clock that counts free space has to name the filesystem.** The volume
  question had been argued for three sessions on `/data`'s 13.74 GB. A plain
  `VACUUM` builds its temporary copy in `SQLITE_TMPDIR`/`TMPDIR`/`/tmp`, which
  on this container is **the root overlay, not the mounted volume** — 7.87 GB
  of 8.35 GB against a 6.48 GB file, a margin of 1.39 GB and about fifteen
  days. The tighter constraint was on a filesystem nobody had read, and the
  sanctioned instrument could already read it (`inspect_live_disk.py --root /`).
  The general form: **when a remedy needs space, find out where it writes
  before computing how long you have** — and prefer the variant that lets you
  choose (`VACUUM INTO '<path>'` needs 1x on a path you name, and is
  non-destructive).

- **A review commissioned before a build is worth more than the same review
  after it, and this is the measurement of that.** `kalshi-platform` was run on
  #76 slice 3's *design*, per Joe's instruction, before a line existed. It
  returned seven defects, three of which would have put a plausible-looking
  wrong number on a screen read mid-game: the field the design named
  (`target_cost_dollars`) is a spend budget the exchange converts to a contract
  count and is meaningless on a sell; the function the design would have hung
  the control off runs on a **60-second loop**, so the "read-only" screen would
  have fired ~1,440 venue writes a day into the bucket the armed order path
  shares; and two of the three measured exit prices are **below this repo's own
  price resolution**, where one surface refuses and the other rounds half-up.
  None of those is findable by reviewing a diff, because each is a property of
  the choice rather than of the code.

## 2026-09-18 (twenty-fifth) - A justification can decay into being RIGHT by accident, and an agent drifts from a convention it cannot be stopped from breaking

Four patterns from a session that closed ADR 0175's leftover guard and put the
volume question in front of Joe. The second is a repeat of an existing lesson
by the same mechanism, which is why it is here again.

- **A stale justification that still reaches a true conclusion is harder to
  catch than one that is plainly wrong.** `backend/store/volume.py`'s docstring
  opened with *"`auto_extend_size_limit = "5GB"` (`fly.live.toml:607`) has been
  reached, so the net cannot fire again"*. The value was wrong, the line number
  was wrong — and **the conclusion was still true**, by a different fact: the
  limit is `"20GB"` at `:858` and the volume had since grown to 20GB, so the
  limit equals the volume's own size. Anyone spot-checking the *claim* would
  have confirmed it and moved on. The existing lesson says a justification for
  leaving something undone goes stale silently; the sharper form is that it can
  go stale **into being right**, and then it reads as verified. **Check the
  cited value and the cited line, not just the sentence they support** — and
  when the conclusion survives with new grounds, rewrite the grounds rather
  than leaving a paragraph that was last true for another reason.

  **Second instance the same day, and it gives the searchable form: when you
  re-point production at a new data source, grep for the instruments that
  claim to MIRROR it.** `window-freshness` opened with *"the same shape as
  `fixture_freshness`, with ONE deliberate addition"* — true until v47 moved
  `fixture_freshness` onto `odds_fixtures` four days earlier, after which the
  one query whose purpose is "what would the window indicator have said" was
  answering with a method the indicator no longer used. A mirror is the one
  kind of code whose correctness is defined **elsewhere**, so nothing local
  goes red when the original moves, and the comment asserting the equivalence
  is what a reviewer checks instead of the SQL. The v47 change even named the
  old shape in its own docstring and still did not move the copy of it two
  directories away.

- **An unenforceable convention degrades to whatever the agent judges
  reasonable, and the agent cannot see itself doing it.** The standing rule is
  *"`ssh` may run only committed, reviewed scripts by path; no inline code, no
  filesystem browsing"*. I broke it four times in twenty minutes — `df -B1
  /data`, `ls -la /data`, and two attempts to base64-exec an ad-hoc script —
  each read-only, each "low-risk", which is precisely the judgement the rule
  exists to remove. **`tasks/archive/lessons-2026-08-10.md` records the agent
  that *proposed* this rule drifting from it inside the hour by the identical
  reasoning**, so this is the second recorded instance of the same failure and
  the first one's lesson did not prevent it. What did: reading a committed
  script's docstring, which is where the rule actually lives. **The remedy that
  generalises is to check whether a sanctioned instrument already exists before
  reaching for a shell** — `scripts/inspect_live_disk.py` did, and it was
  strictly better, reporting 882 MB of space charged to the filesystem and
  owned by no file the walk can see, which the inline `df` could not surface.
  A rule that no test can enforce needs the *recipe* written down, not the
  prohibition: this one now lives in the agent's own memory file, because the
  permission allowlist matches a command prefix and cannot see inside the
  quotes of `ssh console -C "..."`.

- **Measure the hole before you close it, or the fix reads as evidence of a
  bug that never happened.** Before writing the CHECK-constraint guard, the
  same comparison was run over all 40 migrations as a throwaway probe: **zero
  divergences on anything but column order.** So the guard closes a *route*,
  not a defect, and ADR 0176 says so in its own section. Without that pass the
  honest write-up is unavailable — a later session reading "we added a guard
  for migrated CHECKs" would reasonably infer a constraint had been wrong on
  the live volume, and would go looking. **The probe also decided the design:**
  those 12 order-only differences are why the comparison is a multiset of
  clauses rather than a string equality, and a guard that failed on all 12 on
  day one would have been weakened or deleted rather than heeded.

- **A durable venue rule written only in an ADR body is not written down.**
  *"On the RFQ path, read the FIX page before believing the REST reference is
  complete"* has fired twice on one endpoint in two days — `accepted_side`
  (which nearly bought the opposite contract at ~250x) and `rest_remainder` vs
  FIX tag 21015's "Allow partial fills". Both are in ADR 0169 and neither was
  here. **The next session touching the venue reads this file, not an ADR
  body**, and an ADR is a record of one decision rather than a place anyone
  greps for a standing caution. When a finding generalises past the decision
  that produced it, it goes in both.

ADR 0176, 0177, issue #58.

## 2026-09-18 (twenty-fourth) - A fresh database passes whatever the migration does, and a mutation pattern that matches twice patches the wrong one

Both from shipping a schema rebuild, and the second one had already happened
twice the same night before it was written down.

- **A test whose fixture is built from `schema.sql` cannot fail a migration.**
  Narrowing a CHECK inside a rebuild step - i.e. shipping a migration that
  produces a NARROWER constraint than the declared schema - left the whole
  suite green, because every fixture goes through `executescript` on
  `schema.sql` and never runs the rebuild at all. `init_db`'s own docstring
  already warns about this **for columns** ("a FRESH database gets every
  column from `CREATE TABLE`, so a fixture-built one passes whatever the
  migration does"); it arrives the same way on constraints, and the repo's
  `test_the_schema_file_and_the_migrations_agree` does not catch it because
  it compares migrated COLUMNS and INDEXES, and a CHECK is neither. **The
  shape to look for: a guard that enumerates one kind of schema object and is
  read as covering the schema.** Test a migration by winding a real database
  back and migrating it forward - a database that already exists is the only
  case production ever has. And note the sibling trap: **widening a
  constraint and REMOVING it look identical from inside**, since both make
  the new value insertable, so the test that separates them is the one that
  asserts a bad value is still refused.

- **A mutation pattern that matches N times patches one of N, and not the one
  you meant.** Three times in one session: a refusal branch that appeared in
  two places, a `return` that appeared in three, and a DDL helper whose CHECK
  line was shared with another table's. Each time the script reported
  "pattern matched N" only because it asserted a count first; without that
  assertion it would have silently mutated an unrelated line and reported the
  guard as verified. **A mutation harness must assert exactly one match
  before it writes**, and treat "matched 2" as a failed mutation rather than
  a near miss - a mutation applied somewhere else proves nothing about the
  guard it names.

ADR 0175.

## 2026-09-18 (twenty-third) - A fixture offset by a DURATION against a bound that is a ROLLOVER fails for a fixed slice of every day

A full local suite went 8,114 passed at 09:45Z. CI on the same commit failed at
10:10Z, in three tests, in a file the change had not touched. Both were right.

`ladder_candidates` bounds a leg's kickoff by `horizon_end_ms`, which is a
**rollover** - the 4am desk day - not a duration. The fixture seeded its game
at `now + 3_600_000`. Read at 2:45am desk time that is 3:45am, inside the
bound; read at 3:10am it is 4:10am, **past** the rollover, and both legs were
dropped as `kickoff_outside_window`. Walking the clock every ten minutes over
three days: the old expression was out of window **~0.8 hours per day**, and
its first offending sample was `2026-09-18 10:10Z` - the exact minute CI ran.

**The shape to look for: a fixture whose validity is a DURATION from `now`,
checked against a bound that is a WALL-CLOCK BOUNDARY.** The two agree almost
all day, which is what makes it survive review and every local run, and the
failure window is a fixed slice of the day rather than a flake - so it is
reproducible, and it reproduces on someone else's morning. Anchor the fixture
to the bound's own function (`min(now + d, horizon_end_ms(now) - margin)`)
rather than reimplementing the rule or hoping the offset is small enough. Two
sibling tests in this repo already did exactly that, which is how you can tell
the omission was local and not a missing convention.

And the corollary, because it is the part that costs time: **a green full suite
is evidence about the minute it ran.** When CI fails on a file the change did
not touch, check the clock before the diff - and check the failure on an older
commit, which settles authorship in one command.

## 2026-09-18 (twenty-second) - A stated blocker is an inference until it quotes the source; the answer is often already on disk; and a mutation that cannot change behaviour is not a weak test

From a session that took a registered look whose window was open at the time,
and shipped three tickets off the RFQ path. Five patterns, and the first two
each saved a piece of work that had been queued as expensive.

- **A handoff's stated blocker is an inference until it quotes the source.**
  `NEXT.md` said a registered measurement was blocked because "its Q1/Q2 are
  not implemented as whitelisted `QueryDef`s - that is the real blocker, not
  the clock". The registration contains no such requirement: its P4 asks for
  *"a single read-only session (`mode=ro`)"* with *"exactly `Q1` and `Q2`"*,
  and a harness printing extra sections would arguably violate it. The
  prerequisite was invented by an earlier session, and it deferred a
  **non-recurring dated window twice**. Same shape as the ticket that said
  "nobody has registered the dedup" when the dedup had shipped eight days
  earlier. **Before treating a handoff's blocker as real, open the document it
  names and find the sentence.** A blocker is the one claim in a handoff that
  nobody re-checks, because acting on it means NOT doing the work, and not
  doing work leaves no trace that argues back.

- **Before calling a third party to answer a question, grep the repo for a
  payload that already answers it.** Two tickets the same night each specified
  a fetch, and neither needed one. One asked for *"one authenticated
  `GET /portfolio/balance` captured into `tests/fixtures/`"* - and 72 real
  payloads with that body were already on disk under `data/`, captured days
  earlier by unrelated work, which answered it **more strongly** than a single
  fresh call could: the top-level `balance` is cents, each
  `balance_breakdown[].balance` is a 4dp dollar string, and the two agree with
  each other to 0.0065 dollars while disagreeing by ~100x under any other
  pairing. **One payload could not have settled that; the agreement between
  two fields in the same payload did.** The other ticket said an endpoint "is
  sitting unread" when a poller had been mirroring it into a table for weeks.
  The tell in both: a ticket that names a *fetch* rather than a *question* has
  usually not searched for the data.

- **A mutation that cannot change behaviour is not a weak test, and the
  difference is worth five minutes.** Substituting `0` for an unreadable price
  - the exact thing this file forbids - stayed green, and re-checking showed
  why: zero then failed a downstream `is_valid_price` and resolved back to
  `None`. The mutation was **behaviour-preserving by construction**. Treating
  it as a decorative test would have meant "fixing" a test that was fine and
  writing a false line into an ADR. **When a mutation stays green, ask whether
  the mutant is equivalent BEFORE concluding the test is decoration** - and
  record which of the two it was, because they call for opposite actions.

- **A mutation checked against a constant fake proves less than it looks.**
  Replacing `|=` with `=` on a set accumulated across a poll loop stayed green,
  because the fake returned the same row on every read and union and
  replacement agree there. The test asserted the loop polled twice and that the
  count was one - both true under the mutant. **To pin an ACCUMULATION,
  successive reads must differ.** The replacement serves a different row per
  poll, where replacing reports one and the truth is two. Related, and hit
  twice in one session: **a mutation pattern that matches N times patches one
  of N**, and which one is not the one you meant. Assert exactly one match
  before writing the file.

- **A content guard that scans whole files will match documentation of
  itself.** A new synthetic fixture cited a prior ADR by the third party's name
  to explain why it was synthetic, and the guard that refuses that third
  party's payloads - which greps fixture TEXT, not fixture payloads - fired on
  the sentence explaining the exemption. **And targeted tests are not the
  suite:** a new FILE in a watched directory trips repo-wide guards that no
  targeted selection runs, so adding a fixture, a migration or an ADR means
  running the guards that enumerate those directories, not only the tests near
  the change. CI caught it, which is the system working and is also a red main
  for eight minutes.

ADR 0172, 0173, 0169 (Amendment 2),
`docs/measurements/2026-09-18-fair-prices-dedup-effect-result.md`,
`2026-09-18-the-shard-balance-is-dollars.md`,
`2026-09-18-can-an-rfq-quote-partially-fill.md`.

## 2026-09-18 (twenty-first) - Check a money claim against a captured payload, not against the tests; and a threshold taken from the wrong clock cannot ever be false

Three patterns from reviewing an armed path, and the middle one is this
session's own defect, caught an hour after shipping it.

- **A green suite cannot check arithmetic the fake also believes.** The
  all-in cost printed on a button that spends was computed as
  `contracts x ask + fee`, and every test agreed because every test asked the
  same fake. The question a test cannot answer is whether the VENUE thinks
  the fee is already inside the number you asked for. The captured payload
  answered it in one line of arithmetic: solve each maker's quoted size
  against the requested target and see which fee assumption reproduces it
  (`8.19` and `7.72` exactly, with the fee in; `8.43` and `7.92` without).
  That confirmed the figure AND refuted the sentence written beside a
  different constant, which was being printed to the user. **Before shipping
  a money figure, find the captured payload that constrains it and solve
  backwards.** If no capture exists, that absence is the finding (it was:
  `/portfolio/balance` has no fixture and now gates money).

- **A threshold is a claim about a clock, and it must be the RIGHT clock.**
  A quote-age warning was set at three seconds because the venue documents a
  three-second window on combinations -- but that window is the maker's time
  to confirm AFTER an acceptance, not an unaccepted quote's shelf life. The
  same repo had measured those quotes still open forty seconds later. Worse,
  the age was taken from a timestamp stamped BEFORE a mandatory four-second
  wait, so the warning could not be false at first paint under any
  circumstances. **Two questions before any threshold ships: what does the
  number I am comparing to actually measure, and what is the smallest value
  the quantity can take?** If the answer to the second is above the
  threshold, the branch is unreachable in the useful direction and the
  warning is decoration that trains the reader to skip warnings.

- **"Seen twice" is the same thing only within one read.** A store deduped
  quotes with `ON CONFLICT DO NOTHING` because a poll loop sees one quote
  repeatedly. Correct inside a loop; wrong across two asks, because the
  request is held open, the venue reuses it, and a maker re-prices a quote
  **in place** under the same id. The screen then showed one price and the
  table -- the only copy the money path reads -- held another. **When an
  identifier is assigned by someone else, ask whether the thing behind it can
  change while the id does not.** The tell was already in the payload: an
  `updated_ts` distinct from `created_ts` is a vendor telling you the row
  mutates.

And one about verification: **a background pytest that rejects its own
arguments reports exit 0.** `-q --timeout=300` with no `pytest-timeout`
installed collected nothing, and the task notification said success. Grep the
output for `N passed`; absence of that line is a failed run, not a quiet one.
ADR 0169, 0170 (Amendment 1), 0171.

## 2026-09-18 (twentieth) - An index that makes a walk covering does not make it small; a read's cost should scale with its ANSWER, and a diagnostic that reads the whole file is a write to the cache

`/api/window` went from 0.9 s to 7 s in a day, tripped the 25 s budget twice,
and every server-rendered page waits on it. Nothing in the route had changed.
Three patterns, and the last one is the session's own.

- **A covering index removes the table fetch, not the walk.** v41 made
  `fixture_freshness` covering and bought 5x; the statement still walked
  every h2h row ever stored to find a few hundred upcoming fixtures, so its
  cost was proportional to the TABLE and grew with every sweep. The
  question to ask of any hot read is: what does the cost scale with, the
  answer or the data? If the data, no index fixes it -- the read needs a
  source whose size is the answer's (here, one row per fixture). **When a
  route's cost is proportional to history, the fix is a shape, not an
  index**, and the plan diff cannot show it (ADR 0141): `SEARCH ... USING
  COVERING INDEX (market=?)` is a seek in name and a scan in cost.
- **A derived table that any writer could forget is kept by the database,
  not by a writer.** `store_quotes` is one of three insert paths and the
  tests are the other ten. A trigger costs 5 ms a sweep and makes "a
  snapshot row without its fixture row" impossible rather than unlikely.
  The four modules this repo built and never called were all "the writer
  will keep it up to date".
- **Read what an instrument does BEFORE running it on the money box, not
  after it hangs.** `inspect_live_db.py db-sizes` says "via dbstat" in its
  own description; dbstat walks the whole 6.3 GB file through a 3 GB page
  cache. It was run to answer "which table is big" during a latency
  diagnosis -- i.e. the diagnosis consumed the resource under diagnosis
  (2026-08-19's lesson, repeated) and every timing taken after it is worse
  by an amount not measured. A read-only census is a write to the cache;
  the 2026-09-15 lesson said so and was in context. The rule that would
  have held: **a whitelisted query is safe to type, not free to run**;
  before any live instrument, read its `QueryDef` docstring and ask what
  it touches.

And two about the mutation run: a test that pins the ORDER of two
statements pins nothing when either order works (both were tried; the claim
was that both happen), and a plan matcher that knows a table's aliases but
not its bare name lets the alias-less arm through -- the exact arm the
change existed to remove. ADR 0167,
`docs/measurements/2026-09-18-the-window-route-walked-every-odds-row.md`.

## 2026-09-17 (nineteenth) - A resource the browser fetches WITHOUT the cookie is invisible to a cookie gate; and an `env()` safe-area term is 0 until something opts into it

Both from making the cockpit installable to a phone home screen. Both are the
same shape: a mechanism that is off, failing in a way that produces no error.

**A cookie gate only sees requests that carry the cookie.** A web app manifest
is fetched with credentials OMITTED unless its `<link>` carries
`crossorigin="use-credentials"`, so it arrives at an authenticated app looking
exactly like an anonymous stranger. Behind a middleware that redirects the
unauthenticated to `/login`, the manifest answers a 302 - and **iOS reports
nothing**. It silently degrades to installing a bookmark and screenshotting the
page for the icon. You would see a slightly wrong icon and conclude that was
the feature.

The rule: **before gating a path, ask how the browser asks for it.** Manifests,
some preload and prefetch requests, and anything fetched by a
`crossorigin`-less tag are in this class. An auth allowlist has to name them,
and the entry has to be the *exact* pathname the framework chose - here
`/apple-icon`, extensionless, with the cache-busting hash in the QUERY where an
exact-match `Set` cannot see it. `/apple-icon.png` would have matched nothing,
and matching nothing is the failure that looks like success.

**And a CSS `env(safe-area-inset-*)` is 0 unless the viewport declares
`viewport-fit=cover`.** `padding-bottom: max(0.75rem, env(safe-area-inset-bottom))`
had sat in `globals.css` since the ticket sheet was built, commented as keeping
the confirm button clear of the home indicator. Nothing in the app had ever
declared `cover`, so the term had always been zero and the class was a plain
`0.75rem`. The comment described a value that never existed.

The pattern is the one this file already carries about justifications decaying
into reassurance, with an extra edge: **a defensive expression that depends on
an opt-in somewhere else is not defending anything until you check the opt-in.**
`max()`, `clamp()` and `@supports` all hide this the same way - they still
compute, so nothing breaks and nothing tells you.

---

## 2026-09-17 (eighteenth) - Commit BEFORE you mutate, every time; and a venue that says no is not a venue that went quiet

Two things from the first hour of a live feature.

**The mutation hazard, hit again.** `git checkout -- <file>` to undo a
mutation reverts the file to the last COMMIT, which silently took two
finished, unc0mmitted fixes with it. `tasks/lessons.md` and the memory note
both already warn about this, and it still happened, because the mutation
loop is written fast and the `checkout` reads as "undo my mutation" rather
than "discard everything since the last commit". **The fix is mechanical, not
attentional: commit the work first, then mutate.** A wip commit costs nothing
and the amend tidies it. Do not rely on remembering.

**A refusal and an unknown are different, and conflating them destroys the
warning.** The accept path reported every failure as *"it may still have
reached Kalshi -- check the app"*. Joe then hit an HTTP 400
`insufficient_balance`: the exchange explicitly declined, nothing was placed,
and the desk told him to go and check. That warning exists for a timeout or a
dropped socket, where the request genuinely may have landed. Spending it on a
clean refusal is how a safety message becomes noise that gets skipped -- and
the same over-caution this repo keeps having to remove elsewhere.

**The rule:** a 4xx carrying the venue's own reason code is a decision and the
world is unchanged; a timeout, a 5xx or a dead connection is a question.
Only the second gets the cautious words. Unreadable still resolves to the
cautious branch, because the default when you cannot tell must stay careful.

**And the bug underneath it.** The RFQ asked for a flat $5.00 regardless of
the balance, which on a 2.7c combination is 173 contracts. A quote is
all-or-nothing at the size asked for, so the unaffordable target was refused
*after* 28 makers had answered. A size that ignores what the account can pay
wastes the counterparty's work as well as the user's tap.

---

## 2026-09-17 (seventeenth) - A state whose name sounds final is not evidence of the thing it sounds like; only the state that moves money is

The RFQ accept path shipped with `QUOTE_FILLED_STATUSES = (confirmed,
executed)`. The first live accept went `accepted` -> `confirmed` in **32
milliseconds** -- and then `cancelled` 1.7 seconds later, with no fill, no
position change and no balance change. The desk would have told Joe the trade
went through on a trade that never happened.

`confirmed` means the maker agreed. **Execution is a separate step about 1.1
seconds behind it**, and the quote can die in between. Only `executed` is a
fill. The 204 on the accept call is not one either.

**The pattern.** When a protocol hands you a lifecycle, find which state is
the one with the consequence and treat every earlier state as a promise.
`confirmed`, `accepted`, `acknowledged`, `200 OK` -- all of them *sound* like
completion and none of them is. Ask what would be different in the world if
the process stopped at this state: if the answer is "nothing", it is not the
finish line. Here the check was free and decisive -- the balance and
`/portfolio/fills` both said no money had moved while the status said
`confirmed`.

**The corollary that made this cheap.** The probe that found it was designed
so the wrong answer was affordable: one contract, on a market quoted 0.4c
against 99.6c, so the two hypotheses were ~250x apart and the downside was
about a dollar. A bounded probe answers a question a green test suite cannot
-- both readings of `accepted_side` are the code doing exactly what it was
told -- and it found a bug nobody was looking for as a side effect. Cost of
the whole exercise: **$0.0043**.

**And the discipline that kept it honest.** The first run also *withdrew* the
RFQ just before the cancellation, so withdrawal is a plausible cause. One
trial each way is not a controlled comparison, and the ADR and measurement
both say "not established" rather than telling a clean story. The product
stopped withdrawing on the weaker and true ground that there is no reason to.

---

## 2026-09-17 (sixteenth) - A census of the surface you happen to read is not a census of the mechanism; an empty book can mean "quoted elsewhere"

Joe was refused a combination buy because its order book was empty on both
sides. The desk's copy told him nobody would sell it. The venue prices
combinations by **RFQ** (`/communications/rfqs`): liquidity is summoned on
request and prints to the book afterwards, so an empty combo book is the
*resting* state, not an absence of sellers. Twenty-seven RFQs existed on that
exact ticker the same day, and 79 distinct combo tickers carried RFQs in one
25-minute window.

Every claim this repo built on the lit book inherited the error. `40 of 40
KXMVE books carry no resting YES bid` became **"combinations are enter-only"**
in CLAUDE.md -- a statement about *exit liquidity* resting on a measurement
that could only ever see one of the venue's two pricing surfaces. It was never
refuted; it was never supported. `POST /api/manual-orders` check 8 refuses on
`depth_at_ask`, which for a combination is testing a surface the trade does not
use.

**The pattern.** Before a census becomes a claim, ask what *other* surface
could carry the thing being counted, and say in the harness docstring which
surfaces were read and which were not. "We read the order book and found
nothing" licenses "the order book was empty" and nothing more. The tell here
was a paradox the record had already written down and filed as two
populations: *0 of 61 combos had an ask, yet 51 of 52 of Joe's fills were
takers.* A contradiction that gets an explanation instead of an investigation
is a mechanism nobody has looked for.

**Corollary, for delegated API work.** A subagent reported "27 RFQs on this
ticker" and the count was right, but the first re-check appeared to refute it
because `KalshiRestClient.get(path, **params)` takes **kwargs**, and
`get(path, params={...})` silently ships `?params={'limit': 100}` -- an ignored
filter returning an unfiltered page that looks like a valid answer. Confirm a
server-side filter was honoured (distinct values of the filtered field == 1)
before believing either the count or its refutation.

---

## 2026-09-17 (fifteenth) - A document that must describe a guarded format will quote it and then claim it did not; name the canonical file instead of restating the form

Twice in twenty-four hours, a registration wrote the `Question for Joe`
marker form with a placeholder where a ticket number belongs, and
`tests/test_a_question_for_joe_has_a_ticket.py` refused the file. The second
time the author **had been warned about the first in its own brief**, and
still produced this, one line apart:

    **The marker form is `Question for Joe: <one sentence> - #NN`** ...
    **This document deliberately does not write the marker**, with or
    without a placeholder

The claim and its refutation in the same paragraph. That is the tell that
this is structural rather than careless: **a document whose job is to
describe a format is under pressure to instantiate it**, and the author
believes the surrounding disclaimer neutralises the instance. It does not,
because a guard reads text and not intent.

Two conclusions, and the second is the one that generalises:

- **The rule is: never quote a guarded format; name the file that defines
  it.** "The marker form is the one `docs/agents/issue-tracker.md` defines
  under 'Open a ticket for Joe'" carries the same information, costs a
  reader one hop, and cannot trip the guard. A warning in a brief did not
  prevent the repeat; a rule that removes the need to quote does.
- **Do not relax the guard to admit an obvious template.** The temptation is
  strong the second time it fires, and it is exactly backwards: a guard that
  cannot distinguish a template from a real marker is correct not to try,
  because a template is how a real marker gets missed. A guard that fires
  twice on the same construct is working.

Corollary worth its own line: **a sentence asserting a property of the
document it sits in is not evidence of that property.** "This document does
not X" is a claim to check, not a fact, and is most likely to be false
precisely when someone felt the need to write it.

## 2026-09-17 (fourteenth) - A deploy verified at the moment it happened stops being true if anything merges after it; and "the executable queue is empty" is a claim about how many queues you read

Three failures this session, and the first two are the same shape: a state
that was true when written and false when read.

- **The previous session deployed, then merged two more commits, and its
  STATE block recorded the deploy.** Both statements were true when made.
  The result was a day of the live receipt labelling the contracts **sent**
  as `filled size` -- the exact defect the session had just fixed one figure
  to the left. CLAUDE.md's rule (a fix and its copy ship together, or the
  screen lies in the interval) is written as if the hazard lives inside one
  commit. It does not: **the interval that matters is between the last
  deploy and the last merge**, and nothing checks it. Diff the live sha
  against `main` at session start, and read what is in the gap -- a
  documentation-only gap is fine, and you cannot know which it is without
  looking.
- **An empty frontier proves nothing if you read two of three queues.** The
  front door names three; I read the Open list and the map's tickets, found
  four Joe-blocked tickets, and was one sentence from reporting the
  executable queue empty. The third queue -- decided-not-yet-built -- had
  three real items in it, one of them a specific spend Joe had explicitly
  authorised and nobody ran. **A closed ticket is evidence a decision was
  made, not evidence it was built**, and the two diverge silently because
  closing is what the decider does and building is what someone else does.
  The tell: a ticket closed with a comment that ratifies a *different*
  capability than the one it authorised.
- **A verification that scans zero things reports the same clean result as
  one that scans everything and finds nothing.** A chunk scan for new copy
  came back empty; the page it scanned had 307'd to `/login`, so it examined
  nothing at all. Same shape as the CRLF mutation literal that matched zero
  times. **Make the denominator part of the output** -- print how many
  things were examined, and treat zero as a failure of the instrument rather
  than a finding about the subject.

And one that is about deferral rather than staleness: **"fold this in next
time that file is touched" is a deletion with extra steps when nothing on
any queue touches that file.** The condition is not a schedule, it is a
hope. Either do it or record that it was declined -- the instrument gap here
had been carried on exactly that wording, and the configuration it measures
was about to change under every branch of an open decision, which would have
destroyed the only baseline worth having.

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

# The pattern index

Every lesson ever written, newest date first, one line each. The full text of
each is in the linked archive file, unchanged; the sections marked *in this
file, above* are the ones not yet archived. Regenerate it from the headings in
the same edit as the entry — an index that is not is stale by one entry
immediately and by dozens within a week.

### 2026-09-23 — in this file, above

- A field named for one meaning often carries several: filter on the codes the decision names, never on non-empty; and a figure told to the user is one they can act on
- A SQL fragment copied from a sibling query carries that sibling's column meaning; and a lane's test count is read, not quoted
- A claim about how a counter behaves across a restart is a claim about where it is stored; and a number spliced from a registration carries its errors with it

### 2026-09-22 — in this file, above

- An ordering recorded only in a ticket's prose is invisible to the board that dispatches from it; a scheduled task that must wake the machine depends on power-plan state its own XML does not show; and a result document written before its data is a registration one level down
- A fixed-window reading nobody can attend is taken by two schedulers with different failure modes, and the rule for choosing among their reads is registered before any of them fires; an amendment's number is read from the file it amends
- A pass placed behind a liveness gate never runs on the population it is for; an invariant a sibling table got at birth may be structurally unavailable to the one you extend; and a new write ahead of a cycle's decision variable inherits that variable's default on failure
- Read a ticket's Done-when against the tree before dispatching it; a Must-not-touch can contain a file the change falsifies; a loose prefix turns a drift guard into a phantom-defect reporter; and the machine's clock is not the clock
- A venue action takes its population from the venue at the moment it acts; a board's READY count can be eleven and dispatch nothing; and a dated count in a code comment decays like one in a doc
- A new read on a request path inherits the old read's population or it drifts; and a tripwire on a shared symbol fires for whichever path reaches it first

### 2026-09-21 — in this file, above

- A deadline can expire into a missing instrument; a ruling recorded only as a ticket comment decays like a question recorded only as a line; and a guard with a backstop behind it tests green either way
- A cheap reading and a quiet reading can be the same reading; correcting a comparator is itself a comparator choice; and an expensive instrument may already have a column queued onto it

### 2026-09-20 — in this file, above

- A constant in the source beats a week of sampling; a plan shape is not a cost in either direction; and a Done-when can expire with nothing going red
- A lane is cut from where the session started, not from where main is; and an allowlist keyed on who names a symbol moves to whoever you hand the symbol to

### 2026-09-19 — in this file, above

- A queue that lives in prose is re-derived every session; a queue that lives in tickets is dispatched -- and a brief that names a sibling lane's deliverable as existing sends the lane to check

### 2026-09-18 — in this file, above
- A fake that models the venue's good behaviour cannot test the guard against its bad behaviour, and a fixture can exclude a case by arithmetic nobody wrote
- A docstring that says a thing has never been observed is a claim about a date, and other modules quote it as if it were about the world
- a check handed forward is a to-do, a citation is a claim, and a clock that counts free space has to name the filesystem
- A justification can decay into being RIGHT by accident, and an agent drifts from a convention it cannot be stopped from breaking
- A fresh database passes whatever the migration does, and a mutation pattern that matches twice patches the wrong one
- A fixture offset by a DURATION against a bound that is a ROLLOVER fails for a fixed slice of every day
- A stated blocker is an inference until it quotes the source; the answer is often already on disk; and a mutation that cannot change behaviour is not a weak test
- Check a money claim against a captured payload, not against the tests; and a threshold taken from the wrong clock cannot ever be false
- An index that makes a walk covering does not make it small; a read's cost should scale with its ANSWER, and a diagnostic that reads the whole file is a write to the cache

### 2026-09-17 — in this file, above
- A resource the browser fetches WITHOUT the cookie is invisible to a cookie gate; and an `env()` safe-area term is 0 until something opts into it
- Commit BEFORE you mutate, every time; and a venue that says no is not a venue that went quiet
- A state whose name sounds final is not evidence of the thing it sounds like; only the state that moves money is
- A census of the surface you happen to read is not a census of the mechanism; an empty book can mean "quoted elsewhere"
- A document that must describe a guarded format will quote it and then claim it did not; name the canonical file instead of restating the form
- A deploy verified at the moment it happened stops being true if anything merges after it; and "the executable queue is empty" is a claim about how many queues you read
- Before extending an instrument, read what its tests FORBID it from emitting; a registered instrument's scope is a contract, and the obvious extension is the one that breaks it

### 2026-09-16 — in this file, above
- A mutation that changes nothing reports the same green as a guard that is watching; the harness has to refuse the no-op, and a mutation that only ADDS to a pattern has not disabled it
- A median does not bound a tail, so a measurement of the centre cannot falsify a condition written about the worst case; and the regime you can measure cheaply is usually the one where the effect is known not to occur
- A copy guard that pins a field by NAME pins the name, not the claim; and a correction trail that quotes the killed phrase re-triggers the guard while a line-wrapped one dodges it
- When a universal dies, a test on one surface certifies nothing about the others; enumerate every surface that carries the sentence and sweep for strays
- An unasked question decays into the measurement that produced it, because the measurement is the part a session can execute alone
- A before/after measurement taken thirty minutes apart is a drift measurement; interleave the arms or do not compare them
- A copy that restarts whenever its source is written cannot outlast the writer's cadence, and it reports the restart as progress
- The planner can DECLINE an index; before pricing one, check which plan it actually picks -- and ask whether what is missing is statistics
- A merged lane is not a finished lane; do not remove a worktree until its agent has reported
- A bound you can read in the SQL is a hypothesis about the planner; EXPLAIN the before, the after, AND the no-flag case
- When an input and its measurement both exist, read the measurement; the input can only flatter or frighten
- A dispatch whose branches return identical results cannot be guarded by a test that reads the results

### 2026-09-15 — [`archive/lessons-2026-09-18.md`](archive/lessons-2026-09-18.md)
- A comment that names future work becomes a phantom backlog item the moment that work ships
- When a call changes what it SENDS, the row that records it is part of the change
- A cost lever is proposed from the formula and must be validated against the data; the multiplier may be carrying something
- Fix every reader in the function, not the one whose symptom you saw; the card that would have shown the other one may be the card nobody taps
- A write-up drifts toward the flattering sign; a count copied from the spine is a count nobody re-read
- EXISTS does not short-circuit for the rows that fail it; when one parameter value is fast and its sibling times out, the plan is walking the non-matches
- A refusal carries its premise; before inheriting the refusal, re-read the premise against what the record now holds
- A guard that pins a coordinate goes red on an unrelated edit; update the pin, never loosen the guard, and say in the pin what it is really guarding
- A warning improved but not persisted is the same warning; when you fix what a log line says, ask what retains it

### 2026-09-14 — [`archive/lessons-2026-09-18.md`](archive/lessons-2026-09-18.md)
- The steps after a refusal run only on the first success, and an "unexplained" venue response is a claim about your own request until you have re-read it
- A measurement of a state is not a property of the system, and the tell is a sentence with no "while" in it
- A remedy is a claim about the world, and it decays faster than the code that names it
- A sentence that explains a number must be selected by the predicate that produced it, and a refusal's remedy has to travel to the screen that shows it
- A load-bearing count is named with its table, because collapsed quantities survive review by looking consistent
- A wall-clock time in a registration is not a schedule; it is a person, and the person must be named

### 2026-09-11 — [`archive/lessons-2026-09-18.md`](archive/lessons-2026-09-18.md)
- Before a missing number becomes a migration, check whether the row already determines it
- A caveat that names one error term is a claim about all the others
- Never hand-type an identifier into the mechanism whose job is to report identity
- A screen whose content depends on sweep phase will be mistaken for a property of the slate
- A reachability guard that walks modules cannot see an orphaned symbol inside a reached one

### 2026-09-10 — [`archive/lessons-2026-09-18.md`](archive/lessons-2026-09-18.md)
- "Cold start variance" was two states with one name, and the warm reading was the one I took first
- A component that swallows every error needs a test more than a loud one does
- An index that changes no plan can still change the cost by orders of magnitude; EXPLAIN reports the method, not the rows
- "The query admits this market" is not "the desk holds this market", and only one of them is a fact about live
- A rewound clock turns an indexed query into a cold-file scan
- A warning keyed on a count the failure itself suppresses goes quiet exactly when it is needed
- A test that pins a predicate's spelling blocks the fix that keeps its claim
- When one blocker is expensive, look for the free one; the expensive blocker gets all the attention
- A guard test needs a bed where the UNGUARDED code would answer differently; "both paths refuse" is not that bed
- A stopping rule that names an outcome manufactures that outcome, and the arm it names will look like the finding
- An operation that reads can also write, and "it spends no money" is not the test for whether it is inert
- A read-only scan on live is not free for the desk: it evicts the page cache, and the next reader pays for it
- The cost of a scan is not its wall-clock, and a floor widened for a correct reason still has to be re-timed on live before it ships

### 2026-09-09 — [`archive/lessons-2026-09-18.md`](archive/lessons-2026-09-18.md)
- The column you exclude from a comparison key is where the duplicates' real payload hides
- Mutating a constant tests nothing unless every consumer actually derives from it
- A lane's green suite is a weaker claim than main's, and this repo skips its integration guards off the integration branch on purpose
- An append-only record reports the last state it saw forever after that state ends, so "the newest row for X" cannot see X going away
- A decision that turned on a named consumer must be re-opened when the consumer is never built, and nothing notices that it was not
- A replay test can pass through the crash point the guard is for, and then the guard is unverified while the test's name says otherwise
- A true sentence with the wrong scope cannot be caught by any guard that checks its facts, and a sourcing guard makes that harder to see rather than easier
- A test can enshrine the defect as intended behaviour, and then the guard's absence is *documented* rather than merely missing
- Arming an entry without arming its exit is a whole class of defect, and the linkage columns are usually already there
- Re-verify a question before asking it, not just a task before doing it - and never `Write` to a path without checking what is there
- A justification decays into a lie, and the one most likely to is the one that explains why something is safe to leave undone
- A helper with no caller may be the *losing side of a decision*, not an unrun feature, and only the neighbouring docstring tells them apart
- A test that `skip`s on missing input cannot tell a legitimately absent case from the regression it exists to catch
- `flyctl ssh console` starts a shell that does NOT carry the app's Fly secrets; the credentials live on the app's own child process
- A push may cancel an in-flight CI run only when the new tree strictly contains the cancelled commit, and a rule with a redundant clause is worse than no clause
- An exemption list groups by syntax, not by kind, and the dangerous member is the one that merely looks like the safe ones
- A tool's summary of its own scan describes the state before the scan you just triggered, and its per-item verdict can be wrong in the safe-looking direction
- A config value can be malformed in a way that reads as fluent English, and the artifact then does not exist rather than failing

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
