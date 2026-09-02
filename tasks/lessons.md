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

**Split 2026-08-29, at 243,030 bytes — 92.7% of the ceiling, not past it.**
The nine 2026-08-17 entries still living here moved to
`archive/lessons-2026-08-29.md`, verbatim, leaving ~214KB — under 82%. That
file is named for the day of the split rather than the day of the lessons,
because `archive/lessons-2026-08-17.md` already exists and holds four *other*
entries from that date; one name must not point at two files. The index below
therefore carries two 2026-08-17 sections, one per file.

**Split 2026-08-31, at 230,266 bytes — 87.8%.** The **fifty** lessons from
2026-08-25 back to 2026-08-18 moved to `archive/lessons-2026-08-31.md`,
verbatim, leaving 136KB — **52%**. A deeper cut than the last one on purpose:
this file was split twice in three days, and clearing to just-under-the-line
buys one more split rather than several.

**The index was updated in the same edit, and that is the load-bearing half.**
Seven `### DATE — in this file, above` markers became links to the new archive.
The header below this one already records why: an index that says "every lesson
ever written" while pointing at the wrong place makes the file lie about
itself, and a session scanning it for something relevant misses exactly the
lessons it was looking for. **Moving entries without moving their index lines
is not a split, it is a data loss with a table of contents.**

**This split was taken on the rule, not on the alarm.** Waiting for
`tests/test_session_files_are_readable.py` to go red is the wrong trigger: the
test guards the *file*, and what breaks first is the instruction at the top of
it — a session that cannot read the whole file reads the head and silently
believes it has the state. **Split at ~90%, not at 100%.** Read `wc -c` before
writing an entry, not after.

---

## 2026-09-02 - When a single look is registered, the look that counts is the FIRST one past the stopping rule

The forward-lock registration says the rate arm gets *"a single look at `E*`,
no early stopping"*. The first reading past `E* = 160` was taken at 16:26Z
(`E = 263`) and read `UNRESOLVED — C4/C5`. Two and a half hours later a fresh
reading was taken "to see whether C4 had moved", it had -- FAIL by 0.44% to
PASS by 0 KB -- and the result document was drafted on the second reading,
titled `UNRESOLVED — C5`, with the first reading not mentioned. The skeptic
caught it. Neither verdict credits anything, so nothing was gained, which is
exactly why it was easy to do: the flattering direction was invisible because
both readings were negative.

**Pattern: the registered look is the first reading past the threshold, and
every later reading is unregistered however innocent its motive. A result
that titles on a later reading has chosen among looks, and choosing the cleaner
one is optional stopping in a different hat. If a re-read is taken, name the
registered one first and the re-read as a re-read.**

## 2026-09-02 - A retention cap on a diagnostic file is a deletion of whatever measurement reads its oldest lines

The RSS log cap was fixed on 2026-09-01 so that it would finally bind -- trim
to 1 MiB at 2 MiB. Correct, tested, and it would have destroyed the only copy
of the pre-fix baseline that two registered preconditions (C4, C5) read from
that file's oldest lines, within a day of shipping. Nobody checked what read
the file before capping it, because the cap was a hygiene fix and the reader
was a measurement. The file was at 90.6% of the cap when this was noticed, and
was copied out with one `sftp get`.

**Pattern: before adding or tightening retention on any file, grep for its
readers, and treat a registered measurement among them as a hard dependency.
"It is only a diagnostic" is a statement about the writer; the question is
who reads it. And a baseline that exists in exactly one place is preserved
before the trim ships, not after someone remembers it.**

## 2026-09-02 - Before ranking work on a screen, read the instrument that says whether anyone is looking at it

Thirteen frontier tickets about the paint and the labels of the desk were
ranked, twice, without anyone reading the one number the system already
records about the desk: attended odds buys per budget day, which is a
record of how long a page was open. It had fallen from 75 to 5 in five days,
and the armed hand-bet path had placed zero orders in its life. That number
reorders the map above every colour decision on it, and the instrument that
produced it (`credits-day` by trigger) had been in the repo for a week.

**Pattern: a backlog of UI decisions has a precondition -- that the UI is
used -- and the precondition is measurable here. Read usage before ranking
paint. If usage has moved by an order of magnitude, the first item is to ask
the one user why, not to guess from the tickets.**

## 2026-09-02 - A doctrine comment is a claim about the tree; grep before citing it

`globals.css` said `--negative` is the red and *"NOTHING ELSE MAY WEAR IT"*,
in capitals, and the sentence was written the day the accent split from the
loss red. A sweep found roughly two dozen sites wearing it for meanings that
are not a loss -- login errors, every `role="alert"` string, refused ticket
states, the playbook's `rejected` chip -- and every future colour ruling was
about to cite the comment as the rule. The deployed rule was "red = stop and
read this", of which a loss is one case.

**Pattern: a comment that states a rule is a claim with a population, and it
is verified the same way as any other claim -- enumerate the sites. When the
code disagrees, record the disagreement in the comment and hand the choice to
whoever owns the rule; a comment edit that picks a side is a decision made
without a ticket.**

## 2026-09-01 - A check that fails in the direction that ends the work gets no audit

One dry run produced two failed checks. **P6** failed expensively -- it voided
the run -- and earned a `pre-registrar`, a 700-line amendment written under a
deliberate blinding protocol, four salvage conditions and a hand-computed margin
test. **T-MECH** failed conveniently -- it ended the work with a clean negative
-- and nobody checked it at all.

T-MECH was inverted. It reported the fraction D4 *keeps* under the label of the
fraction it *removes*, so a premise that was corroborated at 98.68% was written
up as refuted at 1.32%. The run's own output contradicted it four lines apart:
eligibility requires failing D4, so `eligible_rows / d123_rows` = 97.68% is a
lower bound on the removal rate, and 1.32% is below it. **One division.**

The asymmetry is not about care. Both checks were read by the same person in the
same hour. The expensive failure *demanded* an explanation and got one; the
convenient failure supplied its own and closed the question.

**Pattern: audit effort follows cost, and correctness does not. When a result
ends a line of work, that is the moment to spend the most on it, not the least
-- and the cheapest available audit is an internal-consistency check between two
numbers the same report already printed.** Before accepting any negative, find
two quantities in the output that constrain each other and divide.

## 2026-09-01 - When a property is gated by N independent mechanisms, a guard over one is indistinguishable from a guard over all

A script documented as the deciding instrument for a registered measurement had
never existed on the deployed box. `.dockerignore` carries `scripts/*` with a
hand-kept `!` allowlist and the line was never added -- the **fourth** recurrence,
the file's own comments recording the first three.

The fix derived the allowlist from each script's self-declared `/app/scripts/
<name>.py` docstring path, added a guard, watched it go red, fixed it, watched it
go green -- and **the file still did not reach the box.** The Dockerfile's `COPY`
list is a *second, independent* allowlist and names no `docs/` at all. The new
guard modelled the first gate only. It passed while the property it existed to
protect was still false.

So the guard written to catch this class had the class. Twice more in the same
file: the thing the script *reads* at runtime must also survive both gates, and
"is the script shipped?" reads exactly like "does the script work?"

**Pattern: before writing a guard, enumerate every gate the property passes
through, and make the guard fail if ANY of them refuses. A guard covering a
proper subset of the gates is not a weak guard -- it is a guard whose green is
uninformative, and it is worse than none because it stops the search.** When the
guard goes green, ask what would still have to be true, and check that too.

## 2026-09-01 - A limit asserted in a different unit from the one it is stated in cannot see its own failure

`RSS_LOG_CAP_BYTES = 2 MiB`; the trim kept `RSS_LOG_KEEP_LINES = 8_000`. Sized
when a line was ~80 bytes. The line widened to a measured 286.6 bytes as fields
were added, and the arithmetic inverted: 8,000 x 286.6 exceeds the cap, so at the
cap the file holds ~7,317 lines, `[-8000:]` keeps every one, and the file is
rewritten unchanged. **The cap stopped binding entirely** and became a no-op
running on every pass.

The test asserted `len(lines) <= RSS_LOG_KEEP_LINES` over a ~42-byte fixture --
6.8x narrower than production. At that width the slice genuinely trimmed and the
assertion passed. It could never have failed: `7,317 <= 8,000` is equally true of
a file that was not trimmed at all.

Two distinct defects, and the unit is only the first. **The trim target was the
same quantity as the trigger**, so even with matching units the file lands one
write from tripping again and rewrites forever. Hysteresis was missing and is
invisible to any test that trims once.

**Pattern: assert in the unit the limit is stated in, and give the fixture
production's value for the one parameter the guard depends on. A converted unit
smuggles in an assumption -- here a line width -- that drifts silently while the
assertion keeps passing. And any trigger/target pair must be two different
numbers, or the guard fires forever.**

## 2026-09-01 - Assert on the parsed token, never on a substring of a line carrying other tokens

A test for a new branch asserted `"NO" in p6_line`. The same line ends
`connection refuses writes: NO`, so the assertion was true of every possible
output. It passed against the mutation it was written to catch: removing the
branch left all seven tests green.

This is the same shape as the T-MECH inversion one level up -- an assertion whose
subject is not the quantity it names -- and both happened in the same session, in
tests written specifically to guard against that.

The repair is to parse: match `\((==|>=)\)\s+(YES|NO)` and compare the captured
group, so the assertion can only be satisfied by the token in the position that
means what the test claims.

**Pattern: a substring test over a rich line asserts something weaker than it
reads. Extract the field, then compare. And the only proof that an assertion has
a subject is to break the code and watch that specific test fail -- a suite that
stays green is reporting the absence of a test, not the presence of a
behaviour.**

## 2026-09-01 - A prerequisite validated only against a fixture with no concurrent writer

A registered prerequisite required `COUNT(*)` before and after a read-only report
to be **equal**, to prove the instrument deleted nothing. On the live database
the recorder inserts continuously, so the counts differed by 394 and the
prerequisite answered NO -- voiding the run for a reason that had nothing to do
with deletion, which the `mode=ro` connection makes impossible anyway.

The framing that first suggested itself -- "unsatisfiable by construction" -- was
too strong and the correction is the useful part. The report takes nine
unenclosed reads, so a run finishing between two commits *would* have answered
YES. **The check tested a race.** That is worse than an impossible check, because
a check that passes for no reason is not redeemed by also failing for no reason,
and nobody audits a YES.

The property was "this instrument removed no row" (`after >= before`, plus a
probe that the connection actually refuses writes). What was written tested "the
world was still while I looked".

**Pattern: state a prerequisite as a property of the thing under test, then ask
what else could move it. Equality over a quantity a concurrent process writes is
a race, not a check. And validate every prerequisite against the environment it
will run in -- a fixture with no concurrent writer cannot exercise the one
condition that breaks it.**

## 2026-09-01 - A rate fitted inside a window shorter than the phenomenon has a sign, not a meaning

`fly.live.toml` already recorded that a growth measurement on this database must
span >= 24 h "or it measures the quiet part", and that a shorter window reads
**zero** and looks like a measurement. That lesson did not prevent the next one,
because the failure wore the opposite face: not a zero, a confident nonzero.

Two runs 28 minutes apart differed by +3,855 bytes. That was extrapolated x51.4
to ~198,257 B/day and used to overturn a committed argument. Two later looks fell
-- one by 72,477 bytes -- and the quantity turned out to be a *fraction* times a
constant, so it declines whenever the denominator grows faster than the
numerator. Neither the rate nor its **sign** was established.

The error was made while correcting someone else's reasoning, which is where it
is easiest: the replacement number inherits none of the scepticism aimed at the
thing it replaces.

**Pattern: a two-point difference inside a window shorter than the phenomenon's
period is not a rate, whatever its magnitude -- and the tell is that a third
point can reverse the sign. Before extrapolating, ask what the quantity is a
function of; a ratio moves for reasons its numerator does not. When replacing a
claim you have just refuted, hold the replacement to the standard you applied to
the original.**

## 2026-09-01 - Copy that names a condition is falsified by fixing the condition

Two instances, one repo, one day.

A harness printed *"P6's pass condition stays `after >= before`"* on its
not-pinned branch, implying the pinned branch tightened to `==`. The amendment
authorising the change said it must. The code applied `>=` unconditionally, so
the sentence described a distinction that did not exist.

Separately, a comment justified keeping a reading out of a log file because the
cap "already exceeds by 1.25x, so from ~2026-09-04 that file rewrites itself
every pass". That condition was then fixed -- leaving a live comment reasoning
from a state that no longer held, in support of a conclusion that happened to
survive for a different reason.

`CLAUDE.md` records three passes at one prior instance of this shape.

**Pattern: prose that cites a condition acquires a dependency on it. When you fix
the condition, grep for the sentences that named it -- the fix and the copy ship
in the same commit, or the file lies in the interval. Where the conclusion
survives on other grounds, rewrite the reason rather than deleting the
paragraph: a correct conclusion resting on a refuted premise is the harder defect
to find later.**

## 2026-09-01 - Under `set -e`, a guard downstream of an abort is decoration

A wizard written to verify a Fly volume extend stopped silently after stage 1.
The template runs `set -euo pipefail`; `flyctl ssh console` exits non-zero on
Git Bash even when it hands back the data. So `BEFORE_TOTAL=$(_statvfs_field
total_bytes)` aborted the whole script **at the assignment** -- before the
`if [[ -z "$BEFORE_TOTAL" ]]` refusal written to catch exactly that condition
could run.

The guard existed, was correct, and could not fire. That is the same shape as
four other defects found the same day, and it is the one to generalise from.

**Pattern: under `set -e`, a function that can return non-zero must be made
total at its own boundary -- swallow the status, echo nothing, `return 0` --
because every caller's error handling is downstream of an exit that has already
happened. The same applies to `grep` in a command substitution (returns 1 when
it matches nothing) and to any pipeline under `pipefail`.**

Verify a refusal path by *taking* it, not by reading it: pointing the script at
a nonexistent app is what proved the fixed version reaches its own error
message instead of vanishing.

## 2026-09-01 - Isolate any subagent that WRITES, not just one that mutates code

Four lanes ran in isolated git worktrees, on the recorded lesson that a
subagent holding Bash acts on the same filesystem. A fifth -- a `pre-registrar`
whose whole job is to author one document -- was launched without isolation,
because "it only writes a markdown file" did not sound like mutation.

A `git add -A` for an unrelated merge then swept its registration into that
commit. It happened to be finished; a half-written pre-registration would have
been committed just as willingly, and `git status` cannot tell the two apart
from your own work in progress. The agent had deliberately left it uncommitted
to prevent this and was right to.

**Pattern: the hazard is concurrent WRITES to the shared tree, not the kind of
file. Isolate anything that writes, or stage by explicit path and never
`git add -A` while a writer is live.** The check must also come immediately
before `git add`, not after the commit -- verifying afterwards establishes only
what you got away with.

## 2026-09-01 - A test that asserts copy's TEXT freezes it; assert its SOURCE

`tests/test_parlays_api.py` read `assert "40 of 40" in notes["enter_only"]`,
pinning a caveat that told Joe *"you can buy in, but nobody is bidding to buy
you out."* The 2026-08-30 census found **0 of 61** open combinations with a
readable ask and 0 of 6 books non-empty on either side, so "you can buy in" was
the refuted half, and ADR 0085 ordered the phrase upgraded to *unquoted* the
same day.

It stayed wrong for two days, in the footer of every nightly Discord parlay
push, **and telling the truth would have turned the suite red.** A green CI
certified a claim this repo's own measurement had refuted.

This repo's usual failure is the opposite one -- a claim and its code in
different files with nothing binding them, which produced five stale record
corrections on this same day, every one drifting toward "the system is safer
than it is". Here a binding *existed*. It bound the wrong thing: the literal
digits rather than where they came from, so it preserved the error instead of
catching it.

**Pattern: asserting the text of a caveat converts a fact into a fixture.
Assert that the copy is BUILT from the source of the fact -- a named constant
carrying the measurement -- and the test goes red on the day the measurement
moves, which is the day you want to hear about it.** The census figures are now
`parlays.COMBO_CENSUS_*`, the note is an f-string over them, and the test
asserts `str(COMBO_CENSUS_OPEN) in note`. Verified by mutation both ways:
hardcoding the old digits back goes red, and so does restoring the refuted
clause against an assertion pinning it **absent**.

The corollary is worth its own line, because it is the cheaper half: **pin the
refuted phrase absent, not just the true one present.** "Present" assertions
permit a sentence that says both things; only an absence assertion stops the
old claim creeping back beside the new one.

## 2026-09-01 - A clearing statement in an ADR is a claim about a population, and needs its boundary as precisely as a finding does

ADR 0091 fixed a poller that held the SQLite write lock across three HTTP round
trips, and cleared the neighbouring module in one bullet: *"Every
`estimate_match` helper commits its own writes, checked while investigating."*

The check was real and the sentence was false. It holds for the four
**synchronous** helpers and fails on the one **async** one,
`ensure_estimate_markets_known`, which takes the lock at its first `INSERT` and
does not commit until after the loop -- holding it across N-1 Kalshi round
trips. ADR 0091's own defect, loop-carried instead of straight-line, in the file
the ADR had just declared clean.

Two things made it invisible. The helper differed from its siblings **by a
keyword rather than by structure**, so a sweep reading "every helper" read past
it. And the guard built to catch exactly this class,
`tests/test_poller_holds_no_lock_across_io.py`, could not see it for two
independent structural reasons: it matches only `ast.Name` I/O calls, and
`await source.fetch(...)` is an `ast.Attribute`; and it inspects only
straight-line blocks, while here the write ends iteration N and the await begins
N+1.

**Pattern: "checked and cleared" is a claim about a population, and it must
state the population's boundary as precisely as a finding states its n. Write
which cases were examined and by what predicate, not "every X" -- because the
one that escapes is the one that differs on an axis the sweep did not enumerate,
and a clearing statement is exactly the sentence nobody re-checks.**

Its sibling: a guard that cannot see a defect **reports health over it**, which
is worse than no guard, because the ADR then cites the green. Before trusting
one, ask what shape of the defect it matches on -- and confirm by breaking the
code and watching it go red.

## 2026-09-01 - A CI run that reports on your branch may not be reporting on your commit

The local whole-suite ritual was retired this session in favour of CI, which
runs `ruff` and `pytest -q` on every push. Correct, and it immediately produced
two ways to believe a green that was not there.

**Superseding pushes cancel the run.** Three of the session's runs finished
`cancelled`, not `success` or `failure` -- a fast follow-up push killed each
one mid-flight. A cancelled run verifies nothing, and it is easy to skim as
"not failed".

**A scheduled workflow also reports on `main`.** A watcher written as
`gh run list --limit 1` grabbed a Heartbeat run and announced success for a
commit whose own run was still in progress. The commit under test was never
checked; the message said it was.

**Pattern: after a push, wait for the run whose `headSha` is YOUR commit and
whose workflow is the one that runs the tests, and treat any conclusion that is
not `success` -- including `cancelled` -- as unverified. `--limit 1` is not a
query for "my run".**

    gh run list --limit 12 --json headSha,status,conclusion,workflowName       --jq '.[] | select(.headSha=="<sha>" and .workflowName!="Heartbeat")'

The deeper half is about what replaced the local suite rather than about CI. A
targeted local run is a **guess about blast radius**, and the guess is made
from the diff when it should be made from the artifact: adding a line shape to
an append-only journal broke a test in a file the diff never touched. So the
retirement is right and the workflow that replaces it has two steps, not one --
run what you think is affected, then let CI tell you what you missed.

## 2026-09-01 - Adding a SHAPE to a shared artifact is a wider change than adding a field

A third line shape (`kind: "rollback"`) was appended to `loop_failures.jsonl`.
Every reader was updated, every test in the two files that own the journal was
updated, and CI went red on a third file nobody had opened:
`test_the_journal_survives_even_when_the_database_is_gone` asserted
`len(lines) == 2` and read `lines[1]`.

The behaviour it names -- the journal surviving a database that refuses
everything -- was intact. It broke on the *count*.

**The grep that would have caught it had already been run, at the start of the
same session, for a different reason.** `grep -rln loop_failures.jsonl tests/`
returns five files in one second. It was run to find READERS of the artifact,
before the shape existed; it was never re-run after the shape was added, and
the targeted test selection was chosen from "files I edited" instead.

**Pattern: adding a field to a record is local; adding a KIND of record is not.
Every consumer that counts, indexes, or slices the artifact positionally is a
caller, even though none of them names the new field. Re-run the artifact grep
AFTER the shape lands, not before -- and select the test set from the artifact,
not from the diff.**

The secondary lesson is about the fix rather than the break: the assertion was
positional (`lines[1]`), which is the same defect that let three section tests
pass against the wrong section earlier the same day. It now addresses lines by
`kind`, so the next shape added breaks nothing.

And the timing is its own note. The local whole-suite run had been retired that
hour, correctly -- CI runs it free on every push. What did not survive contact
was the half of the workflow that replaces it: **a targeted local run is a
guess about blast radius, so the push is not done until CI is green.** Retiring
the local suite is only safe if checking CI is treated as part of shipping.

## 2026-09-01 - A registration's "what we cannot measure" list is a claim, and getting it wrong retires the falsifying test

The lock-holder registration said, in two places, that the poller's cycle END
is recorded nowhere -- and used that to rule out any exonerating verdict. It
was wrong. The poller sleeps AFTER its cycle, so the gap to the next stamp in
the very table the query already reads bounds the cycle above. The open item
had asked for "start **and finish** times" in those words.

The cost was not a missing nicety. It was **the only check that could have
refuted the result**: if the cycles that produced a failure had run to the
normal median, the poller finished fine and something else held the lock. The
registration had retired that test by asserting the data did not exist, and
the write-up went out with a confirming reading and no falsifying one.

When the check was finally run it separated cleanly -- burst cycles +15.2 s,
repeat-only cycles -0.01 s, Fisher p = 0.0001 -- so the conclusion held. **That
is luck, not method.** The same omission with the numbers the other way would
have put a false attribution into the record with a p-value on it.

**Pattern: the "what this cannot establish" section is the most load-bearing
part of a registration and gets the least scrutiny, because it reads as
modesty. Every line of it that says "we have no way to observe X" is a claim
about the data, and it must be checked against the schema like any other. The
dangerous ones are the lines that retire a test that would have hurt.**

The tell: a limitation that arrives phrased as an argument for the
conclusion's own robustness ("so no exonerating verdict is available") rather
than against it. Modesty that only ever cuts one way is not modesty.

## 2026-09-01 - A subagent with Bash mutates the tree you are committing from

`measurement-skeptic` was asked to audit a finding. It did the right thing --
built its own mutation harness and disabled each guard in turn to see which
were real, which is exactly the method this repo requires. It ran that harness
against the **shared working tree**, writing `LOCK_WINDOW_S = 60.0` into the
source and restoring it after each run.

For several minutes the tree carried a widened threshold: the precise defect
the constant exists to prevent, introduced by the auditor checking for it. A
commit in that window ships it, and the diff looks deliberate.

Nothing warned. `git status` showed one modified file, which is what a session
mid-edit looks like anyway.

**Pattern: a subagent holding Bash acts on the same filesystem, so "delegate
the audit" is not isolation. Before any commit taken while a subagent may be
running, re-read the specific constants and guards that subagent was asked to
attack -- `git status` is not enough, because a mutation in flight is
indistinguishable from your own work in progress.**

The structural fix is a worktree for anything that mutates. The cheap fix,
which is what was done here, is to check the values by name immediately before
`git add`. Do the cheap one always; do the structural one when the subagent's
whole job is to break things.

## 2026-09-01 - Check a ticket against the tree before scheduling it

Six decision-map tickets were classified as pure evidence and queued as work.
**Three of the six were already fixed** -- #13 on 2026-08-29, #30 on
2026-08-29, #26 in the same window -- each with the correction sitting in the
file the ticket names, and each still open because nobody closed it.

Verifying all three took about four minutes; building them would have taken
hours and produced a diff against code that already said what the ticket
asked for.

**Pattern: a ticket asserts the state of the tree at the moment it was
written, and a repo under daily change falsifies that faster than the queue
drains. Read the file the ticket cites BEFORE planning the work -- not to
check the ticket is well-formed, but because "already done, never closed" is
a common and invisible state.**

The backlog was 23 open; it was really 20. A queue that is partly finished
reads as a bigger queue, which is its own cost -- it was one of the reasons
the map looked immovable.

## 2026-09-01 - A flag whose TRUE value has two causes is not an instrument, however carefully it is recorded

An open item named the observation to add, in one sentence: *"whether
`record_loop_failure_durably`'s `rollback()` succeeded. It separates 'the
shared connection was still poisoned' from 'someone else held the lock'."*
The field was obvious, the code was four lines, and the boolean does not
separate those two things at all.

A `rollback()` on a connection with **no open transaction is a no-op that
always succeeds**. So `rollback_ok = True` is produced by "an open
transaction was rolled back and the poison is gone" and by "there was
nothing to roll back" alike, and those are the two hypotheses under test.
Only the failing value carries information -- and it is the rare one.

What discriminates is `in_transaction`, read BEFORE the rollback: `False`
says the reachable half of the poison was absent, so the rollback cured
nothing and cannot be credited. Recording the pair costs one more line than
recording the boolean.

**Pattern: before adding a field, ask what its most common value rules out.
If the same value is produced by both hypotheses you are separating, the
field is decoration -- find the observation whose values partition the
hypotheses instead.** The tell is that you can write down the reading for
each value and one of them says "either".

This generalises past booleans: it is the same defect as a test that passes
under the bug, and the same check catches both. It is also the reason a
field's docstring should state the reading order when two fields must be read
together -- `rollback_ok` beside `in_transaction` is informative, and alone it
invites the exact overstatement the field was added to prevent.

## 2026-09-01 - A test that addresses its subject by POSITION can keep passing against the wrong subject

Fourteen tests read a query's output sections as `sections[0]`, `[1]`,
`[2]`, `[3]`. A section was inserted in the middle. Four went red -- and
**three kept passing while asserting against a section they were never
written about**, because the new section happened to hold the same row count
as the one that had moved down.

    assert sections[2]["row_count"] == 1     # meant the population tally
                                             # now read the new cure section

A green test that has silently retargeted is worse than a red one: the red
ones announced the change, and these three quietly stopped guarding the thing
they are named for. Nothing in the run said so, and the row counts made the
coincidence likely rather than unlikely -- small fixtures produce small
counts, and small counts collide.

The fix is to address by a stable property of the subject: a helper that
finds the one section whose title carries a marker, and asserts there is
**exactly one** match, so an ambiguous or missing subject fails loudly
instead of silently picking a neighbour.

**Pattern: when a test selects its subject out of an ordered collection,
select it by something that identifies it -- a name, a title, a key -- never
by index. An index is a claim about the collection's shape that nothing in
the test verifies, and when it breaks it can break in the direction that
still passes.**

The same shape reaches beyond tests: `argv[3]`, a CSV column number, a tuple
unpacked positionally out of a query whose `SELECT` list grew. Position is a
coupling to a layout nobody declared.

## 2026-09-01 - Find the change point before you name the cause

A fix deployed at 15:29Z. The failures it targets stopped at 11:01Z. I wrote up
"they stopped after the fix" and computed a p-value for it, and both timestamps
had been on my screen for an hour.

    newest failure   2026-08-31T11:01:00Z
    the deploy       2026-08-31T15:29:19Z    4.47 h of quiet BEFORE the cause

The quiet run was 50 passes long and the deploy sat at position 14 of 50. The
same test applied to the pre-fix half of that run "detects a fix" over an
interval in which nothing shipped -- which is the falsifying check, and it is
one subtraction.

**Pattern: before/after is a claim about a change POINT, so locate the change
point in the DATA first and only then look for a cause at it. The last bad
event's timestamp minus the deploy's timestamp is the whole test, it costs one
subtraction, and if the answer is negative there is no comparison to make.**

The reason it is easy to miss: both numbers get computed, for different
reasons, in different steps -- one to establish "how long has it been quiet",
one to establish "when did the fix land" -- and neither step is the one that
would subtract them. A before/after write-up should OPEN with that difference.

**This is the second before/after defect on a live series in two days, and the
08-30 lesson above would not have caught it** -- that one says to find the
boundary from a variable the change itself moves, and my cause-boundary was
correct. The two are complementary halves of the same check:

    08-30   is the boundary where I think it is?      (find it from the data)
    09-01   does the effect start before the cause?   (subtract the two)

The generalisation covering both: **a quiet interval is not evidence for
anything that happened inside it.** Something has to distinguish the moment,
and "the fix is in there somewhere" does not.

## 2026-09-01 - A group selected by an outcome cannot report a rate on that outcome

The failure journal separates three outcomes: the row was written on the shared
connection, on a fresh one, or on neither. I listed the "neither" group and
reported that **14 of 14 of them said both connections refused** -- and offered
it as evidence about the cause.

It is a tautology. "Both refused" is the definition of that group; it is the
only way to land in it. The number could not have come out differently, so it
carried no information at all, and it read as the strongest line in the report.

**Pattern: when a subgroup is defined BY an outcome, no proportion computed
inside it is a finding. Report the full population's split across all the
outcomes instead -- that one can vary, so it can inform.** Here: 22 journalled,
8 on the shared connection, 0 on a fresh one, 14 on neither. The 0 is the
interesting cell and the selected view had hidden it entirely.

The tell is that the denominator is described using the same words as the
result. "Of the failures the table lost, N had no table row" -- if the sentence
survives deleting the numbers, there is nothing being measured.

This one now sits on the query's own screen, because the next session reads the
screen and not the docstring: the section prints the three-way tally and says
which count may be quoted.

## 2026-09-01 - A writer with no reader is an instrument that does not exist

`record_loop_failure_durably` had appended every pass failure to a journal file
for two days, specifically because the failure TABLE goes silent under the one
condition it exists to record. The design was right and the code was correct.
Nothing ever read the file -- not the ssh-invokable inspector, not a route, not
a script -- so the open item that needed it read *"`loop_failures` is the
instrument"*, naming the artifact that cannot see the failure class.

Cost when the reader was finally written: the table held 8 of 22 failures. Every
count of that class ever taken off it had been a floor by a factor of ~2.75, and
two whole `pass_kind` values were missing from it.

**Pattern: durability is not readability. A record written where nothing can
read it from is not a record -- and it is worse than an absent one, because the
system LOOKS instrumented. Ship the read path in the same change as the write
path, or the write path is a comment.**

The repo's own `test_has_callers.py` exists for the callers half of this. The
missing half is the reverse direction: **grep for a reader of every artifact you
write.** One `grep -rn` over the filename is the whole check, and here it
returned the writer, tests of the writer, and nothing else.

## 2026-08-31 - A cost that does not change with the row limit is not in the rows

`/api/slate` was slow. The obvious suspect was the row work -- 55,777
`recommendations` rows scanned twice with an expression basis no index can
serve, and an `ORDER BY` on that same expression. The plan was an expression
index, which on a live 1.5 GB volume means a schema migration.

One measurement killed it. Requesting `limit=1` cost the same as `limit=100`.
Whatever was slow could not be per-row, and an index on the row table could not
have helped:

    anchor MAX/COUNT over 55,777 rows      8.2 ms
    in_window COUNT                        8.0 ms
    the derived table alone               77.3 ms
    the whole query                       85.4 ms

The cost was a `LEFT JOIN (SELECT ... GROUP BY ...)` aggregating an entire
history table to attach one column to at most a hundred rows. Two sibling
routes had the same shape and one had it without a `WHERE` at all.

**Pattern: vary the limit before you optimise. A cost that is flat in the row
count lives in something the query does once -- a derived table, an aggregate,
a subquery -- and no amount of indexing the row table touches it.** It is one
extra request and it points at the right half of the query.

The general fix is the same each time: **make the work proportional to what the
screen shows.** Read the ids you are returning, then one bounded query for the
attachment. This codebase already had the idiom in two places under a different
name -- "one read per fixture, not per row".

The near-miss is the part to keep: the index would have been written, migrated
onto a live volume, and measured afterwards as no improvement, because the
thing it indexed was 8ms of an 85ms query.

## 2026-08-31 - A header you set is not a header the framework sends

The framing headers were added in one funnel through the Next middleware, every
exit wrapped, twelve source tests green, three mutations verified red. Reading
them off the live wire afterwards:

    /login /slate /market/{ticker} /parlays   both headers
    /api/health, /api/slate (200)             NEITHER
    /api/slate (401 from the middleware)      both headers

`/api/*` is a rewrite to a backend process, and the framework serves that
backend's headers rather than the ones set on `NextResponse.next()`. The 401
carries them only because the middleware constructs that response itself rather
than passing one through.

Every source test was correct and none of them could have found this. They
assert what the code *sets*; whether a set header survives depends on what the
framework does with it on each code path, and that is not visible in the code
you wrote.

**Pattern: setting a response header is a request to a framework, not an
effect. On any path where the framework proxies, rewrites, caches or
regenerates the response, the header may not survive -- so read the header back
from the deployed system, on one URL of each SHAPE.** One page, one redirect,
one proxied route, one error: four requests, and they disagreed.

The same shape as the deploy that reports success and the resize that reports
success. The general rule this file keeps rediscovering: **the confirmation and
the effect are different things, and only one of them is what you needed.**

## 2026-08-31 - A guard on the code must not be able to read the comment beside it

Three tests on a new middleware failed the moment they were written, and the
code was correct. They asserted that the response does not carry `DENY`, a
`script-src` or a `style-src` -- and the comment above the code named all three,
explaining why each had been rejected. The guard matched the prose that exists
to justify the guard.

The mirror image of it happened earlier the same day: a test named for a match
between a docstring and the code read only the docstring, and stayed green
through the exact change it was written to catch.

**Pattern: a guard about behaviour must read only the code. Comments are where
the alternatives get named, so any source-scanning guard whose subject is "this
must NOT appear" will eventually match its own rationale -- and one whose
subject is "this MUST appear" will eventually be satisfied by prose alone.**
Strip comments before asserting; it is four lines.

    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)   # block comments
    raw = re.sub(r"^\s*//.*$", "", raw, flags=re.M)    # line comments

The failure is loud in the first direction and silent in the second, which is
the one to fear: a test that fails on a comment gets noticed in seconds, and a
test that passes on a comment is a guard that was never installed.

## 2026-08-31 - Text can overflow a correctly-sized box, so hunt overflow with scrollWidth and not with rects

The slate scrolled sideways at 390px. Two scans for the culprit -- every
element whose `getBoundingClientRect().right` exceeded the viewport -- found
only the nav, which is a legitimate `overflow-x-auto` scroller. Both scans were
looking for the wrong thing.

The offender was a `<span>` exactly **327px** wide, correctly sized, sitting
inside its column with a right edge nowhere near the viewport. Its *text* ran
to 404. A rect describes the box; it says nothing about content spilling out of
a box that is itself the right size. So the element could never appear in a
rect-based scan, at any viewport, however wrong it was.

One walk found it in a single pass:

    for (const el of root.querySelectorAll('*'))
      if (el.scrollWidth > el.clientWidth + 0.5) report(el)

filtering out the elements where that is intended -- a real scroller has
`overflowX !== 'visible'`.

**Pattern: `rect.right > viewport` finds a box that is too wide.
`scrollWidth > clientWidth` finds content too wide for its box. They are
different defects and the second is the one that hides**, because every
element involved measures correctly.

The cause underneath was a machine-joined string
(`stale_odds,too_few_books,no_market_width,...`) with no break opportunity in
it, and the fix was `break-words`. See the entry below for why the same page
measured clean an hour earlier.

## 2026-08-31 - A fix that does not move the number has not been shown to work

Having found one element that could not wrap a machine-joined string, I fixed
it, redeployed, and re-measured. `documentElement.scrollWidth` was **still
428** -- the exact number it had been before -- while the element I had fixed
now sat correctly inside the column.

The fix was real. The diagnosis was half of one. A *second* element rendered
the same string, and it was the one actually setting 428 -- and it was in the
code I had written that day, which is the direction I was least likely to look
after finding a plausible culprit elsewhere.

**Pattern: the confirming measurement is the one that finds the second cause.
Re-run the exact measurement that produced the symptom, and treat an unmoved
number as a live finding rather than as a stale reading.** The temptation is to
explain it away -- caching, the wrong build, the data changed -- and each of
those is checkable in seconds, which is what makes skipping the check
inexcusable.

The failure mode has a name in this file already: it is *one predicate with two
spellings*, and *two renderings of one value must wrap the same way*. What is
new is the procedure -- **fix, re-measure, and require the number to move.**

## 2026-08-31 - A layout measurement measures tonight's data as much as the CSS, so one clean read is not a clean bill

The slate was measured at a true 390px viewport and came back clean:
`documentElement.scrollWidth` 375 against a 390 viewport, nothing overflowing.
An hour later, same page, same width, same build: **428**, and the page
scrolled sideways on a phone.

Nothing about the CSS had changed. What changed was the data. A
`suppressed_reason` is often several codes joined by commas with no spaces --
`stale_odds,too_few_books,no_market_width,...` -- which is one unbreakable
token to a line-breaker, and the footer's span lacked `break-words`. On the
first read no row carried a long multi-code reason, so the defect was not on
the page to find.

**Pattern: a layout check is conditional on the content that happened to be
rendered. Passing once proves the CSS survives THAT data, not that it survives
the data.** Where the content is generated rather than authored -- codes joined
into one token, an unusually long team name, a number with more digits than
usual -- the check has to be re-run against the shape that stresses it, or the
stressing shape has to be seeded deliberately.

The cheap version of that discipline: when a string is machine-joined, assume
it will one day arrive with no break opportunity in it, and put `break-words`
on it the first time. The row-level span in this same file had carried it since
it was written and never overflowed; only the footer's copy, rendering the same
string, lacked it. **Two renderings of one value must wrap the same way**, and
they disagreed for as long as both existed.

## 2026-08-31 - A tool that reports success has not necessarily done anything; measure the state it claims to have set

The 390px check was skipped for a whole session because `resize_window`
returned *"Successfully resized window containing tab ... to 390x844 pixels"*
and the page stayed at desktop width. Three calls, three successes, no change.
Chrome ignores the resize on a maximised window and the tool reports the
request, not the result. The next screenshot came back 1568 wide and was read
as "the resize did not take" only after the third try.

One line settles it, and it is the state rather than the return value:

    window.innerWidth        // 1045, not 390

**Pattern: a tool's success message is a claim about the CALL, not about the
world. When the whole point of a step is to put the system into a state, read
the state back before doing the work that depends on it.** This is the same
discipline as `/api/health`'s `git_sha` after a deploy, and as "read the output,
not the exit status" -- the general form is that the confirmation and the effect
are separate things, and only one of them is what you needed.

The workaround, worth keeping because the same-origin trick generalises to any
authed page: replace the document with a `<iframe width=390 src="/the-page">`
on the SAME origin. The frame gets a genuine viewport at that width -- real
media queries, real layout -- and the session cookie flows because it is not a
third-party frame. Make the iframe very tall and scroll the OUTER page; a
short frame clips, and its own `scrollTo` does not respond.

## 2026-08-31 - Code and its own comment agreeing is not verification; both can be wrong together about the rule they serve

The slate row's `StatusLine` voices one warning by fixed priority, and its
docstring numbered that priority. Quote clock first, consensus clock second.
The code matched the list exactly. It had matched since the day both were
written, and it was wrong.

`actionable` is the **odds** clock and only the odds clock -- the order
endpoint re-reads the Kalshi quote inside the request, so a stale quote means
*the price printed here is a memory*, not *this row is dead*. The consensus is
the one nothing but a credit can refresh, so it is the limit that ends a row's
life. Outside an odds window both are stale on most rows, so the stated order
voiced the LESS binding of the two on exactly the rows where the difference
decides what to do.

**Pattern: a comment and the code beneath it are one source, not two. When they
agree, you have learned that nobody mistyped -- not that either is right. The
check that matters is against the rule they serve, which lives somewhere else.**
Here the rule was four hundred lines away in `_live_ages`, written out in full,
and contradicted the docstring that had been read past for weeks.

The corollary for where to look: a defect of this shape leaves **no
inconsistency anywhere in the file**, so no amount of reading that file finds
it. It is found by reading the screen (a live row printed the wrong caveat) or
by reading the rule. Both are outside.

## 2026-08-31 - A test named for a relationship between two artifacts must read both of them

Written for the lesson above: `test_the_stated_priority_matches_the_branch
_order`. It read the docstring's numbered list and asserted the order that list
was in. Then the mutation it was named for -- swap the two `if` branches,
leave the comment -- **left it green**, because it never opened the code half
of the relationship its own name claims to check.

The fix is one line of shape: read both, compare them to *each other*, and
never to a literal typed into the test.

    assert (doc_a < doc_b) == (code_a < code_b)

**Pattern: when a test's name is `X matches Y`, the assertion must contain both
X and Y. An assertion of the form `X is <constant>` tests X against the test
author's memory, and passes for as long as X is untouched no matter what Y
does.** The name is the tell, and it is checkable by eye: count the artifacts
named in the name, then count the artifacts read in the body.

This is the same family as *a test that names a symbol is not a guard on that
symbol* and *pin a guard on the decision it changes, never on the string it
prints*, and it is worth its own entry because the failure is invisible at
review: the test is about the right subject, in the right file, with the right
name, and green for the wrong reason.

## 2026-08-31 - A number cannot be checked against itself, so put a second independent rendering of it on the same row

The dispersion strip's always-visible summary read `readings disagree by 0.6
pts`. It had been wrong since the day it shipped, on two surfaces, and every
test written about it passed -- because every one of them compared the figure
to its own derivation.

It computed the width of the **padded** axis rather than the span of the
readings. `dispersion.ts` adds a tenth of the span at each end so a mark
sitting at an extreme is not half-clipped, so the axis is exactly 1.2x the
truth; and on any row with books joined, the domain also contains the book
span, so the headline was not about the readings at all. Both errors point the
same way: they overstate. The sentence one line below it, computed from the
marks, was right the whole time.

What found it was rendering a **second, independently derived copy of the same
quantity** on the same row -- the trust score's `methods_agree` detail, which
says `four methods within 0.5 pts`. Side by side, `0.6` against `0.5`, and on
another row `8.4` against `7.0`. Nothing else could have: a test asserting the
figure would have had to know the right answer, and the only source for the
right answer was the code being tested.

**Pattern: a derived number with no independent second rendering is
unfalsifiable on screen. When you add a surface that states a fact some
existing element already states, read them side by side before you reconcile
them -- the disagreement is the measurement.** Two numbers for one fact is
normally a defect to remove; for exactly as long as it takes to read them, it
is the only instrument you have.

The corollary is about what to do next, and it is not "delete one". Both
renderings stay, and they now share one definition
(`core.trust.method_spread_points`), so the next divergence is a compile-time
impossibility rather than a thing to notice.

## 2026-08-31 - A component that inherits its type size has no typography

`TrustNote` was extracted from the parlay card to serve three screens. On the
card it lived inside a `text-[11px]` list item and looked right. Dropped onto
a slate row -- same markup, same words, same tests green -- it rendered at body
size, the loudest text on a row whose every other caption is `text-xs`.

Nothing about the component changed. What changed is that it had one host and
now has three, and it had been borrowing its weight from the first one.

**Pattern: a shared component must set its own type size. Size inherited from a
parent is a property of the host, not of the component, so the component looks
different on every screen it is reused on and no test can see it.** This is the
same family as the typography defect one entry below -- an honesty rule about a
screen is satisfied by the RENDERED screen -- and it is the reason the fix was
found by opening the page rather than by reading the diff.

The safe extraction is: give the component an explicit size that reproduces
what its first host was already rendering (`text-[11px]` here), so the original
surface is pixel-identical and the new ones inherit nothing.

## 2026-08-31 - Never hold a database write transaction across an `await` that does I/O

`OperationalError: database is locked` killed a scoring pass four to five times
a day, and the busy timeout was already set correctly at 5 seconds -- so
something held the write lock for longer than that. It was the portfolio
poller:

    await poll_balance(...)      # INSERTs -> SQLite's write lock is taken
    await poll_fills(...)        # network round trip, lock HELD
    await poll_settlements(...)  # network round trip, lock HELD
    await poll_positions(...)    # network round trip, lock HELD
    conn.commit()                # released, three round trips later

Python's `sqlite3` opens an implicit write transaction at the first INSERT and
holds it to COMMIT. Every other writer that landed in that window waited out
the timeout and raised.

**Pattern: a lock is held in wall-clock time, and an `await` is an unbounded
amount of it. Commit before any await that performs I/O, or do the I/O first
and write afterwards.**

Three things about how it got there, and the second is the one that
generalises:

- **The transaction boundary HAD been thought about, and the wrong property was
  checked.** The comment beside it reasons carefully about rollback scope --
  "after the commit, so a matcher failure cannot roll back the mirror" -- and
  never about lock duration. Rollback scope and lock duration are different
  questions about the same `commit()`, and answering one feels like answering
  both.
- **Three separate correct changes each widened the window, and none noticed.**
  `poll_fills`, `poll_settlements` and `poll_positions` were moved onto the
  fast cadence on three different dates for three good recorded reasons. Every
  one added a network round trip inside an open transaction. **A shared
  resource held across a call site degrades one caller at a time, and each
  addition looks local.**
- **The frequency is what identified the right site.** The same shape existed
  on a 12-hour mirror and on a 300-second loop. Twice a day does not explain
  four-to-five failures a day; 288 times a day does. Checking whether the
  proposed cause fires often enough to produce the observed rate is what moved
  this from a plausible story to the actual one -- and it is the same discipline
  as reading `n` before the effect size.

## 2026-08-31 - A wording rule can be defeated by typography, and no source test will see it

A screen element was built to say that some checks had not been run, so that a
score could never read as a clean bill of health. Every wording test passed:
the string was present, the count was right, the unknown was not folded into
the pass. It rendered as

    EVIDENCE 7/7 CHECKS · 1 not checked

with the score in uppercase mono and the caveat in lowercase prose after a dot.
**The honest half was typographically subordinate to the flattering half**, and
a reader stops at 7/7.

**Pattern: an honesty rule about a screen is only satisfied when the RENDERED
screen satisfies it. A test that greps the source can prove a string is
present and can never prove it is legible. If a claim about honesty matters
enough to test, open the page and read it.**

The corrected guard asserts the *nesting* -- the caveat must live inside the
score's own styled span -- rather than the presence, because presence was
always true. This is the same family as "a test double must not be more
permissive than the real object": the assertion was about a proxy for the
property rather than the property.

## 2026-08-30 - Split a before/after on evidence of the change, never on when you think you made it

A live before/after for a new index was cut at the deploy's wall-clock time.
The answer that came out: pre-index p50 **63 ms**, post-index **61 ms** -- the
index does nothing to the median. It was one edit away from being published as
a correction to a claim that was, in fact, right.

The log file lives on the volume and survives deploys, so one file held both
regimes and the boundary had to be *found*. The deploy did not land when the
dispatch happened: the first attempt failed on a builder outage, the retry
landed earlier than assumed, and the guessed cut put **79 with-index passes
into the "before" bucket**, dragging its median down to meet the after.

The honest boundary was in the data. `db_kb` steps 2,034,808 -> 2,182,008 KB in
one pass -- +147 MB against a separately measured 150.3 MB index. That row is
where the index began to exist. Re-split there: **p50 407 -> 60 ms, and 100% of
pre-index passes over 200 ms against 0% after.**

**Pattern: when comparing two regimes in one continuous series, find the
boundary from a variable the change itself moves -- a file size, a schema
version, a row count -- not from a timestamp you supply. Your timestamp records
when you ACTED; the data records when the system CHANGED, and deploys, retries,
restarts and caches put a gap between them.**

The failure is nastier than an ordinary confound because it is directional:
misassigning post-change samples into the before-bucket always drags the two
groups *together*, so the error reliably manufactures a null. A null looks like
rigour. This one would have been written up as "the honest correction to an
overclaim", which is the disguise a wrong result wears when it is most likely
to be believed.

## 2026-08-30 - A test double that is kinder than the real object hides the bug it exists to catch

`watch_bids_forever` passed `KalshiRestClient(cfg)` -- constructed, never
entered -- to the function that cancels resting bids. The real client's
`client` property raises `RuntimeError: used outside its context manager`
before a request is built, so **every auto-cancel failed from the day the
feature shipped**, and a real order sat past its deadline on live while the
loop retried once a minute exactly on schedule.

Five tests covered this behaviour and none could see it. Two reasons, and the
second is the transferable one:

1. Every test called `cancel_due_bids` directly, with a client someone else
   had prepared. The defect lived one level up, in the step where the loop
   builds the client -- the seam production runs and the only seam untested.
2. `FakeApi` answered `cancel_order` whether or not it had been entered. It
   modelled a client that **does not exist**, so the failure was invisible by
   construction, not by oversight.

The tempting reading is "test one level higher". That is right and it is not
the general rule, because you cannot always reach the top. The general rule is
about the double:

**Pattern: a test double may be simpler than the object it replaces, and may
never be more permissive. Wherever the real object refuses -- an unentered
context manager, a closed connection, a missing credential -- the double
refuses, with the same wording. A double that is kinder than production
converts a whole class of wiring bugs into green tests.**

The tell that this had happened: making `FakeApi` strict turned three existing
tests red, all of which had been passing a client in a state production never
produces. One of them, `test_the_row_stays_working_when_the_venue_refuses`, was
passing **for the wrong reason** -- on the context-manager error rather than on
the venue refusal it claims to test. A green test that asserts the right
outcome via the wrong failure is worse than a red one, because it also reports
coverage.

Related, and now twice-instanced: the wiring guard for this feature asserts the
*string* `"watch_bids_forever(args.db"` appears in `run_loop.py`. It does, and
did throughout. A source grep can say a call exists; only running it says the
call works.

## 2026-08-30 - When two code paths can produce the same end state, an assertion on the state guards neither

A migration was added to put a covering index on `odds_snapshots`, and the
obvious test wound a database back to the previous version, called `init_db`,
and asserted the index was present. **It passes with the migration step
deleted** -- observed, not reasoned -- because `init_db` runs `migrate` and
then `executescript(schema.sql)`, and the schema file carries the same
`CREATE INDEX IF NOT EXISTS`. Two producers, one observable outcome; the test
could not attribute it, so it guarded nothing.

Calling `migrate` directly made it a real guard, red on exactly that mutation.

**Pattern: before asserting an end state, ask what else could produce it. If
anything else can, the assertion is about the state and not about the code you
mean to test -- call that code directly, or assert something only it can
produce. The mutation test is what reveals this and nothing else does: the
first version of the test looked exactly as convincing as the second.**

A corollary worth carrying: this is why "verify a guard by disabling it" has to
disable *the specific thing*, not the feature. Deleting the index from both
`schema.sql` and the migration turned five tests red and would have been read
as proof the guard worked. Deleting only the migration step -- the actual claim
-- was the mutation that exposed it.

## 2026-08-30 - Check the REGRESSOR moved before you read the outcome; a constant explains nothing

The per-pass instrument was built to decide between two mechanisms by
correlation: does the storage leg track `wal_kb` while the scan leg tracks
`candidate_rows`, or do both track `wal_kb`? Read over 128 passes, `wal_kb`
had **two values** (one of them the first pass) and `candidate_rows` had
**one**, while `leg_store_quotes_ms` swung 62 to 2700 ms. Both proposed
causes were pinned flat for the whole window.

The trap is that the outcome variable looked wonderfully alive -- a 44-fold
swing invites a story, and the two candidate stories were already written
down. Reading in the registered order (regressor first) makes the window
unusable in one line. Reading outcome-first makes it feel like a finding, and
whichever mechanism the reader already believed would have collected the
credit.

**Pattern: before interpreting any correlational read, print the variance of
every regressor. Zero variance means the window cannot run the design -- the
verdict is "not tested", never "not the cause". This sits beside "read `n`
before the effect size": same failure, one level up. `n` can be ample and the
design still void.**

A corollary about how the window got that way: it was taken overnight, when
the slate was empty and no sweep had run for hours. **The window that is
convenient to take is the one where nothing is happening**, which is exactly
the window in which every driver is at rest.

## 2026-08-30 - An instrument sampled at pass START repeats itself when a pass fails, and the repeat is the signal

`record_pass_rss` samples at the top of each pass, so its leg timings
describe the *previous* pass -- documented and deliberate. What nobody had
read off it: when a pass fails without refreshing `counts`, the next line
re-emits the previous pass's numbers verbatim. Three consecutive rows before
a container death carried byte-identical `candidate_rows`, `candidate_ms`,
`leg_price_link_ms` and `leg_store_quotes_ms`. Three independent millisecond
timers do not agree exactly; that line is a *stale read*, not a stable system.

So the wedge was legible in the record from its first repeated row, ~48
minutes before the death -- while the established detector (`pass-gaps`)
cannot fire until a gap has already elapsed, and `loop_failures` was empty
because the failure path shared the poisoned connection.

**Pattern: for any instrument that carries state it did not itself produce,
work out what it emits when the producer fails. A repeated value is either a
frozen system or a broken producer, and those are the two most different
things it could mean. Decide which at design time and say so in the
docstring, because the reader who meets it first will read "flat" as
"healthy".**

## 2026-08-30 - When you change a cadence, re-read every predicate that compares against a timestamp it produces

`_absence_provable` (`backend/estimate_match.py`) requires a successful
settlements poll postdating `match_status_ms`. When ADR 0064 moved
settlements from the 12-hour mirror to the 300s clock, that proof went from
"satisfied twice a day" to "satisfied within minutes" -- while the ladder
consuming it still advances once per 12h. Two clocks bounding one quantity;
the tightening one moved and nothing that read it was revisited. Not a bug
today. It is the shape that bites when someone relaxes the 12h and finds the
next bound already binding, symptom unchanged -- the same family as the
attention/floor predicate with two spellings (2026-08-29).

**Pattern: a cadence change is not local. Grep for every predicate that
compares against a timestamp the changed clock produces, and re-derive what
each one now means, before shipping the new interval.**

## 2026-08-30 - A test that names a symbol is not a guard on that symbol

`tests/test_portfolio_poll.py` mentioned `run_match_pass` in a docstring and
an assertion message, and on that basis the wiring was asserted to be
"pinned". Stubbing `run_match_pass` to an async no-op left all 333 tests in
the area green: if the production call were deleted, the suite would not
notice. The claim felt confirmed because a test *named* the thing -- the
same mechanism as reading a test's name instead of its assertions, and it
fails in the flattering direction every time.

**Pattern: to claim a guard exists, disable the thing and watch it fail.
Reading test names is not the check. This file already says every guard is
verified by disabling it; the addition is that the rule applies to guards
you BELIEVE exist, not only guards you are writing.**

## 2026-08-30 - A failure recorder that shares the failing resource records exactly the failures that don't matter

The recording loop's failure table, its failure hook and its dying alert all
wrote through the same database connection the passes used. When that
connection itself became the failure — a stale WAL snapshot poisoning every
write on it — five passes failed, five failure rows failed with the same
error, and the one alert that explains a dead loop died of the cause it was
naming. The table's documented reading ("no rows across a gap = wedged or
gone") was inverted by the one failure class that kills the process.

The pattern: **a failure path must not depend on anything the success path
depends on.** Ask of every recorder, alerter and journal: "what happens when
the thing it records THROUGH is the thing that broke?" The fix here is the
general shape — a file append first (no lock can refuse it), the shared
resource second, a throwaway replacement third; and the fallback doubles as
the diagnosis, because "the fresh connection wrote what the shared one
refused" is itself the finding.

Corollary, measured the same night: `sqlite3.Connection.rollback()` stopped
resetting open statements in CPython 3.11, so "rollback on the failure path"
cures only the open-transaction half of an abandoned pass; a cursor still
referenced by something long-lived holds its read snapshot until the process
dies. Do not write "rollback fixes it" without the test that poisons a real
WAL file and watches it fail.

---

## 2026-08-29 - A local autouse fixture over module state protects one file and exposes every other

`run_kalshi_pass` acquired two module-level counters, and the lane that added
them guarded its own tests with an autouse fixture inside
`tests/test_full_walk_alarm.py`. That file was then the only one in the suite
that could not be polluted. Six other files call a pass, `test_runner.py` hands
`run_kalshi_pass` an empty series list and leaves the streak at 1 for
everything collected after it, and a first pass in any later test read a
`walk_prev_discovered` that another test had walked -- the integer that on live
means "a walk has happened", produced in the one situation where the honest
answer is `None`.

**The pattern.** Process-wide state is a property of the module, so the reset
belongs beside it and the fixture belongs in the root `conftest.py`, where it
covers every file rather than the one whose author happened to think of it. A
local fixture is not a smaller version of that; it is a guarantee for one file
purchased by making the hazard invisible everywhere else -- and invisible in
the direction that matters, because the protected file is the one whose tests
would have named the problem.

The repo already had the shape to copy: `reset_scope_warnings` and
`_JOINT_CACHE` are both deliberately process-lived and both forgotten between
tests from `conftest.py`, each with a docstring saying why the state outlives a
call. A reset written that way documents the production property; one written
as a local fixture hides it.

**And a reset is not a substitute for asserting the property.** The persistence
is what makes the streak mean anything, so it is now pinned by a test of its
own -- two callers, one counter -- beside the test that pins the fresh start.
Both go red when the fixture is deleted, which is the only evidence that either
is a guard.

---

## 2026-08-29 - A red suite in a shared checkout may be a moving tree, not a defect

Eight failures were reported against a merge of two lanes. Every one of them
was an `inspect.getsource` assertion. The merge commit's own full suite was
green -- 5,070 passed -- as was the current tip three merges later, and as were
the eight tests under the third lane that was mid-merge in the working tree at
the time. Nothing was wrong with the code.

**The pattern.** A checkout that several lanes merge into is not a fixed input,
and a 13-minute suite is a long window. Before diagnosing an integration
failure, pin the tree: record the commit, confirm the working tree is clean,
and re-run from a worktree at that commit. `git status` and `.git/MERGE_HEAD`
are part of a bug report about a test run, in the same way the commit is.

`inspect.getsource` assertions are the ones that notice first, because they
read the file from disk at assert time while the module in memory was imported
minutes earlier. That makes them an early warning about the tree rather than
about the code, and worth reading that way when a whole cluster of them fails
together and nothing else does.

---

## 2026-08-29 - One constant serving two purposes changes the thing you were not touching

A registration's declaring floor was raised from 300 to 713 to make a verdict
harder to reach. The function that fits the model took
`tuning: int = MIN_CLUSTERS_TO_DECLARE` -- the same constant also parameterised
the always-valid confidence boundary. Raising the floor would have silently
re-tuned that boundary and **restated the widths of two intervals already
published in the record**. A change made in the conservative direction would
have quietly rewritten past results.

**The pattern.** A constant with one name and two consumers is two decisions
wearing one identifier. Changing it for the first consumer is a change to the
second, made without argument, without an ADR, and usually without a failing
test -- because both consumers still work, they just mean something different
now.

The check, and it is cheap: **before changing any constant, grep every
reference and ask what each caller is using it FOR, not what it is called.**
If two callers want it for different reasons, split it first and change it
second. The split is the safe move even when the values agree today, because
agreeing values are exactly what hides the coupling.

The tell that this had happened: the fix was pinned by a test asserting the two
numbers do NOT move together, and its evidence of correctness was that the
previously published reproductions still returned their original figures. **If
a "safe" change alters a number already in the record, it was not safe and the
record is the thing that noticed.**

## 2026-08-29 - A merge of two correct changes can contain a defect neither of them contains

Two lanes landed independently. One added a field to a per-pass instrument's
writer, saying which pass produced each memory reading. The other rewrote that
instrument's reader with an explicit column list. Both were complete, both were
tested, both were right.

Merged, the reader silently dropped the writer's new field -- recreating by
omission the precise misattribution that field had been added to prevent.
Neither lane's tests could catch it, because neither lane contained both halves.

**The pattern.** Parallel work is safe when changes are independent, and the
dangerous case is not a textual conflict -- git reports those. It is two
changes to *opposite ends of the same contract*: a writer and a reader, a
producer and a consumer, an emitter and a schema. Git merges them cleanly
because they touch different lines, and the contract breaks in the gap.

What actually caught it was a guard of the form **"every key the writer emits
is a column the reader renders"** -- a test that asserts the two ends agree
rather than testing either end. Those tests feel redundant when one person
writes both sides. They are the only thing standing up when two people do.

So: when a change adds a field to one end of a contract, add or check the
agreement test, not just the test for the new field. And at merge time, run the
two lanes' test files TOGETHER before believing either.

## 2026-08-29 - Read the output, not the exit status

A test suite was run in the background as `pytest > file; echo "EXIT=$?"`. The
harness reported exit code 0 and the run was declared green. It was not: 8
failed, 5063 passed. The zero belonged to the trailing `echo`.

**The pattern.** Any status a wrapper reports is a status about the wrapper.
A compound command reports its LAST component; a background harness reports
the shell; a CI step reports whatever it was configured to watch. None of them
is a claim about the thing you care about.

**Read the artifact.** `grep -E "^FAILED|passed|failed"` on the actual output
costs one command and cannot be fooled by a pipeline. The general rule this
sits under, which this repo already learned once for `flyctl logs`: a
verification method that can report health while the underlying thing is broken
is not a verification method, and the moment it is most likely to fool you is
when its answer is the one you were expecting.

## 2026-08-29 - Search the measurements directory before commissioning a measurement

A lane was sent to name a ~570MB step in the live container's memory curve. It
did good work and returned a precise answer. The answer was already in the
repo: `docs/measurements/2026-08-20-the-585mb-is-a-level-not-a-leak.md` had
recorded it as a one-time boot-level allocation nine days earlier, in its
title.

**The pattern.** A repo that writes its findings down accumulates an asset that
only pays if it is consulted, and the moment of highest risk is exactly when a
fresh observation looks novel. A number arriving from an instrument feels like
new evidence; the same number sitting in a dated file feels like history. They
are the same fact.

So: **before commissioning any measurement, grep `docs/measurements/` and
`docs/adr/` for the quantity by name and by magnitude.** Both, because the
earlier write-up may have used a different label - here the prior file said
585MB where the new read said 570MB, and a name search alone would have missed
it. Cost of the check: under a minute. Cost of skipping it here: a full lane,
plus a wrong framing that nearly shipped in a commit message claiming a fix for
container deaths it does not touch.

The corollary is worse than the waste. **A re-derived number arrives without
its original caveats.** The 2026-08-20 file had already established this was a
level and not a leak; the re-derivation had to rediscover that, and in the
interval a plausible, elegant, entirely wrong death-spiral theory was built on
top of it and had to be separately demolished.

## 2026-08-29 - A document that promises to amend itself needs an enforcer, and the un-amended state always flatters

A pre-registration contained its own amendment trigger: *"if it comes in above
30 tenths this document must be amended to raise the floor."* The quantity came
in at 30.15. The amendment was not written, and nothing noticed, because
nothing could - the trigger lived in prose and its subject lived in a
measurement taken by different code on a different day.

**The pattern.** A conditional obligation with no executor is a wish. Whenever
a document says "if X then this document must be amended", ask immediately:
**what fails when X happens and nobody amends?** If the answer is "nothing",
the clause is decoration, and the failure mode is not random - it is always in
the direction that leaves the easier threshold standing. Here the un-amended
floor was 300 and the honest floor was 713, so every day the amendment went
unwritten was a day the project could declare a verdict it had already
disqualified itself from declaring.

Two things follow:

- **Pair every self-amendment clause with a test or a constant.** The floor was
  `MIN_CLUSTERS_TO_DECLARE = 300` in code, unchanged, while the document that
  set it had promised to move it. A number that governs a decision belongs in
  one place, and the prose must not be the only copy.
- **Check the trigger conditions of every registration at every look**, as a
  standing step, not when someone remembers. The look that fires a trigger is
  the look least motivated to notice it, because the trigger makes the result
  harder to obtain.

And the deeper one: **a design can fail its own power check in a cell it
printed itself.** The registration's published table gave the resolving power
at the floor it chose. Nobody read across the row. Before trusting any
registered threshold, evaluate the design AT that threshold and confirm it can
resolve the effect it is testing for.

## 2026-08-29 - When mid-flight steering is unavailable, the brief is the only instrument, so it must grant permission to refuse

Mid-task messaging to running agents was unavailable for a session. Two lanes
were therefore launched on briefs that turned out to be wrong: one against a
ticket that had shipped five days earlier, and one containing an instruction
that would have reintroduced the very bug it was sent to fix.

The second lane came back correct anyway, and the reason was one line in its
brief telling it to **verify the diagnosis before changing anything, and to fix
the real cause if it differed.** It did, it found the described defect already
fixed, and it refused the instructed change with an argument. The first lane
had the same clause and used it too.

**The pattern.** A brief written by someone with stale context is the normal
case, not the exception - the director's picture is always older than the
code. So every brief should carry, as standing text:

- **verify the stated cause before acting on it, and say so if it differs;**
- **check whether the work is already done, in the code rather than in the
  ticket;**
- **refuse an instruction that would make things worse, and explain why.**

Cheap to write, and it converts a wrong brief from wasted work into a
correction. The alternative - relying on the ability to steer mid-flight - is a
dependency on a channel that may not exist, and it fails silently: an obedient
agent executing a stale brief produces confident, tested, merged, useless work.

## 2026-08-29 - One predicate with two spellings, and the screen believing the wrong one

A single false statement on the desk took three separate fixes to kill. The
backend computed a "next scheduled sweep" time from a schedule slot while the
budget check that would refuse that sweep sat after it; the frontend then
rendered the resulting null as a different reason entirely; and the loop's own
refusal string promised an hourly fallback that the same refusal had switched
off - a string that was not a log line but travelled to an API field and
printed on a screen.

Each fix looked complete when it landed. Each left a surface still saying the
false thing.

**The pattern.** When one condition is evaluated in more than one place -
"will a sweep happen" computed by a scheduler and separately narrated by a
banner, an API field and a UI branch - the copies drift, and they drift toward
whichever spelling was written first. Fixing the computation does not fix the
narration.

The check to run: **grep for every place that states the predicate in words,
not just every place that computes it.** Refusal strings, banner text, empty
states and log details are all claims about behaviour, and a log line that
reaches an API response is user-facing regardless of what it was written as.
Then ask what SHOULD be true after the fix and re-read every one of those
surfaces against it - a reassurance that was accurate before a behaviour change
becomes a lie after it, and nothing in a test suite notices.

## 2026-08-29 — A cause list written as alternatives cannot file causes that happen in sequence

The gap pre-registration enumerated four causes of a missing failure row and
framed the read as picking one. The observed incident was two of them **in
sequence**: a synchronous wedge the deadline machinery never got control of
(cause 1), followed an hour later by a process death (cause 2), with the
restart ending the gap. Filed as "which one is it", the read would have been
wrong under either answer — and the discriminator (uptime) was designed to
separate the causes, not to notice they had composed.

The pattern: when pre-registering a diagnosis, ask whether the candidate
causes are exclusive, and if they can compose, register what a composite
would look like in the instruments. A mechanism with stages leaves a
signature per stage; a cause list flattens them into one verdict slot. The
cheap check is to write, for each PAIR of causes, one sentence on what the
record shows if both are true — if any sentence is coherent, the decision
table needs a row for it.

Corollary from the same read: **a platform flag is scoped to the layer that
sets it.** Fly's oom_killed=false refutes a host-level OOM kill and says
nothing about the guest kernel's OOM killer, which kills one process inside
the VM and presents exactly as "a child died". A refutation is only as wide
as the observer's vantage.

## 2026-08-28 — A pre-registration must fix its scope conditions before it enumerates causes

**The pattern.** When an **absence** is the finding — no rows, no alert, no
error — the first question is not "which of these causes explains it". It is
**"was the detector present, and did the query reach far enough to see it?"**
A cause list answers what a missing row means *inside a valid window*; it says
nothing about whether the window was valid, and a careful list of causes reads
as rigour while quietly assuming the thing most likely to be wrong.

So a pre-registration needs a **population clause** before its decision table:
*which observations are in scope, and what makes them so.* Without one, a
reading taken outside the population produces a verdict that looks like a
result and is not one.

**Where it bit.** A pre-registration for reading a scheduler gap enumerated
four explanations for a missing `PassDeadlineExceeded` row — synchronous
blocking, process death, the failure-write itself blocking, and the gap being
too short for the deadline to fire. Careful, correct, and pointed at the wrong
question. When the read was taken, both gaps in the window had begun **hours
before the deadline code was written**, and ~5 hours before the deploy that put
it on the box. Zero rows meant nothing: no code capable of writing a row was
running.

Two silent failures, both flattering:

1. **The instrument was not deployed.** Nothing in the output says so — a
   query against a table returns zero rows whether the feature is absent or
   merely quiet.
2. **The query's reach was set by a row count**, `--tail 400`, on a loop whose
   cadence varies 60x between a 15s fast interval and a 900s shut-window one.
   The window it covers is therefore a hidden variable, and a tail that stops
   inside the observation period reports "no gap" for the region it never
   looked at.

Both failed toward the hypothesis the session already favoured — *no rows,
therefore synchronous blocking* — which is the direction to expect and the
reason to check.

**What to do instead.**

- **State the population before the causes.** "An observation counts only if it
  began after <instrument> reached live at <timestamp>." Stamp that timestamp
  **from the machine** (`/proc/uptime`), not from a deploy log or from memory:
  the version of this that was written from memory was twenty minutes wrong.
- **Never let a scope condition become an entry in the cause list.** It is a
  fifth off-ramp from a zero that *is* informative, and once filed as a cause
  it will be used as one.
- **Make a query verify its own reach in its output** rather than trusting a
  count. The oldest row returned must predate the window's start, checked and
  re-run wider if not. Raising `--tail 5` to `--tail 400` fixed one instance of
  this trap and reproduced it one order of magnitude out.
- **Give a null result a minimum duration.** "No gap" over 50 minutes against a
  base rate of 3-6/day expects 0.1-0.2 gaps: it is not weak evidence, it is no
  evidence, and it should be recorded as *"not taken"* rather than as a
  verdict.

**And the freeze that protects a reading should name the window, not the
activity.** "No deploy" was written for a window already open and was later read
as a standing prohibition, which would freeze a repo indefinitely against a read
that keeps not happening. The rule is **no deploy during the observation
window**: container uptime is only destroyed for gaps that *precede* the last
restart, so a deploy landing before the window opens costs the reading nothing.

---

## 2026-08-28 — "Unexplained one-off" is a claim about frequency, and a default window is not a population

**The pattern.** When a diagnostic tool has a `--tail` / `--limit` / `--since`
default, the number it prints is a statement about *that window*, not about the
system. Writing "unexplained, self-recovered" after reading the default window
asserts something the reading cannot support: that it happened once. Widening
the window costs one flag and is the first thing to try, before any hypothesis
about cause.

**Where it bit.** `inspect_live_db.py pass-gaps` defaults to `--tail 5` — the
last five rows of `odds_sweep_log`. Read that way on 2026-08-28 it printed
`0 rows` for gaps. Read with `--tail 400` it printed **sixteen**, spanning
2026-08-23 to 2026-08-28, 21.5 to 63.3 minutes each, about 3.4 hours of dead
recorder a day since 08-26. Three sessions in a row had written the same
silence up as a fresh, unexplained incident, each one correct about its own
window and wrong about the system. The escalation — one gap a day, then six —
was visible in one query the whole time.

**Why it survives.** A default window flatters in the direction of calm: it
shows the recent past, which is the part most likely to be healthy (you are
usually looking *because* something just recovered). And "unexplained" reads as
appropriate humility, so nobody challenges it — while it is actually the
strongest possible claim about frequency, made from the weakest possible
evidence.

**How to apply.**

- Before writing "one-off", "first time", "unexplained" or "self-recovered" about
  anything, re-run the instrument with its window opened as wide as the record
  goes, and report the per-day count. If the tool has no such flag, that is the
  work.
- Prefer a **rate** to an **event** in any handoff line. "47.8-minute gap,
  unexplained" invites a hunt for one cause; "3.4 hours a day for three days,
  escalating" names a different problem and a different urgency.
- A silence that leaves **no row at all** is the one to instrument, not to
  explain. Sixteen holes carried no `loop_failures` row because a wedged pass
  raised nothing; the fix was a deadline that makes a wedge raise, not a better
  guess at the cause. See [[unreadable-resolves-to-none]] — absence and zero are
  different readings, and here absence was being read as "nothing to see".
- Confirm a gap on a **second table** before believing it. `odds_sweep_log`
  going quiet is consistent with a legitimately sparser sweep schedule;
  `kalshi_quotes` also going to exactly zero, with thousands of rows either
  side, is not.

---

## 2026-08-28 — A helper called from a loop that must not die does not get to trust its caller

A display function divided a stake by a probability. The probability was a
product across several legs, and one leg came back at exactly `0.0`, so the
division raised. The page it served rendered "Backend unreachable".

That much is an ordinary bug. What made it an outage is that **the same
function was reachable from two callers with completely different failure
budgets**: a web route, where an exception is one bad page, and the recording
loop's per-pass tail, where an exception killed everything after it — the
push notifications, the daily digest, and a progress log. A defect in a
payout display stopped the alerting half of the system.

Nobody chose that coupling. The payload builder was written for the route, and
was later reused inside the pass because it produced exactly the object the
notifier needed. Reuse was the right call. **The cost was invisible because the
two call sites are in different files and neither one names the other's risk.**

**The pattern: a function's tolerance for raising is a property of its
CALLERS, not of itself, and it changes silently the day a second caller
appears.** The second caller is normally the one with the strictest
requirement, because loops and schedulers are exactly the things that reuse
existing builders.

The repair has two halves, and the redundant-looking one is the point:

1. **Refuse the bad input upstream**, where the meaning is known — a fair
   probability of zero is not a long shot, it is a failed devig, so the leg is
   dropped and *counted* rather than clamped to something small. A count turns
   an invisible condition into a rate.
2. **Make the arithmetic unable to raise anyway**, even though (1) makes it
   unreachable. This looks like belt-and-braces and is not: (1) is a claim
   about today's inputs, and (2) is a claim about the loop surviving tomorrow's.
   The guard renders the "could not be computed" dash the app already uses
   elsewhere, because inventing a number for a thing nobody can price is the
   failure the refusal existed to prevent.

**The habit: when you reuse a builder inside a loop, go and read what it
divides by, indexes into, and assumes non-empty.** Then ask which of those the
loop can afford to raise on. Usually none, and the fix is cheap at that moment
and expensive after the pager goes off.

---

## 2026-08-28 — Sharing a predicate guarantees agreement only about what the predicate decides

A screen and the loop it describes were deliberately built on one shared
function, and the field's comment said so in as many words: *"the same
predicate the loop fires on, so the page cannot disagree with it."* The
reasoning was sound and the implementation matched it.

Then the page said "the next scheduled sweep is now" at the same minute the
loop was logging "cannot be served". Both were reading the same predicate.
The predicate answers *"is a call wanted?"*; the loop then applies a **second**
condition the predicate knows nothing about — a budget — and the screen renders
the first answer as though it were the second.

**The pattern: a shared predicate makes two callers agree about the question it
answers, and about nothing else.** Every condition the actor applies *after*
consulting it is a place the display can diverge, and the divergence is
invisible on every ordinary day, because the extra conditions are the rare
ones. Here it agreed on every night the budget had credits left and disagreed
only on the nights it did not — which are exactly the nights someone stares at
the screen wondering why nothing is happening.

Three things that make it hard to catch:

1. **The guarantee is written down and it reads as a proof.** "Same predicate,
   so they cannot disagree" is the kind of sentence that stops a reviewer,
   because the mechanism it names is real. The gap is not in the mechanism; it
   is in the scope of the claim.
2. **The failing state is the one nobody develops in.** A budget is spent, a
   quota is hit, a lock is held — the conditions that get bolted on later are
   the ones you do not have locally.
3. **It looks like a copy bug.** The first instinct is to reword the sentence.
   But the field is what is wrong: any future caller reads it the same way, and
   a reworded page leaves the next screen to make the identical mistake.

**The habit: when a display and an actor share a predicate, list what the actor
does BETWEEN calling it and acting.** Each item is either pushed into the shared
predicate or made explicit in what the display promises. And a comment claiming
two things cannot disagree must name the conditions under which that holds, or
it is a guarantee about a subset wearing the words of a guarantee about
everything.

---

## 2026-08-28 — A guard that matches a literal string certifies the string, not the property

Twice in one day, in unrelated files, a green test was pinned to an exact string
rather than to the thing the string happened to spell.

One counted `"bg-accent "` to enforce "only one filled control on this screen".
Renaming the token to `bg-accent-fill` took the count to zero: the rule was
intact, the control was still there and still alone, and the test went red
anyway. The other matched the query-plan step `"SCAN f"` to enforce "this must
not read every row". A query change made SQLite scan the same table through a
different index — `SCAN f USING INDEX idx_fair_link` — and the test went red
while still describing a full scan.

Both were repaired the same way, by asking what the assertion was *for*: a
filled control is about **weight**, not about a hue, so the guard names the fill
token; a full scan is `SCAN <table>` however SQLite spells the rest, so the
pattern allows the suffix.

**The part worth carrying is the third case, which was silent.** The same
too-literal `SCAN f` pattern also guarded the *production* plan, as a negative:
*assert no step matches `SCAN f`*. That one did not go red. It would have passed
**vacuously** the first time the planner chose to scan through an index — a
guard against "every row is visited", defeated by which index the visit goes
through. A literal in a positive assertion fails loudly when it drifts. **The
same literal in a negative assertion goes quiet**, and quiet is the direction
that ships.

**The habit: after fixing a probe that broke, grep for the same literal in the
negations.** They were written by the same hand on the same afternoon and they
have the same defect, but only one half announces it.

---

## 2026-08-28 — A guard can check the right token in the wrong role, and stay green for months

A palette test computed WCAG contrast on every colour token, per theme, and
pinned the ratios so a future tweak would fail by arithmetic rather than by
review. It was a good test. It was green the whole time a real-money confirm
button rendered white text at **3.76:1** against a 4.5:1 floor, on the live
instance, where money is spent.

The test checked each token **as ink on a ground**. The button used it **as a
fill under white**. Those are two different pairs of colours, and the token
passed the first and failed the second — necessarily so, because the shade that
is legible as ink on a dark card is a light shade, and white does not sit on a
light shade. The two requirements pull in opposite directions, which is why one
token could not satisfy both and why nothing in the file noticed.

**The pattern: a token has as many contrast obligations as it has ROLES, and a
guard that checks one role reports on one role.** Ink on card, ink on tint,
white on fill, and a border against the surface beside it are four separate
measurements of the same hex value. A file that computes three of them and is
named for the colour reads like coverage of the colour.

Two things make this hard to see from inside:

1. **The passing check and the failing render share a variable name.** Grepping
   for the token finds the test, the test asserts on the token, and the token is
   the thing that is wrong. Every signal agrees and every signal is about the
   other role.
2. **The role lives at the call site, not in the palette.** `globals.css` cannot
   say which tokens will be used as backgrounds; only a component can. So the
   test has to carry a *list* that the palette does not contain, and a list is
   the one thing that goes stale without failing.

**The habit: before asserting on a design token, write down which roles it
plays, then check that many pairs.** The fix here names the fills explicitly in
the test file and says in its own docstring that a filled control built on some
other token is uncovered until it is added — because a guard that cannot
enumerate its own scope should say so rather than imply completeness.

**And the near-miss in the same change, which no guard caught at all.** The new
panel-edge token was applied by rewriting `border bg-card` to
`border-edge bg-card` across 35 sites. In Tailwind, `border` sets the *width*
and `border-edge` sets the *colour* — so that rewrite deleted every panel border
in the app. It typechecked clean, built clean, and passed every test, because
nothing in this repo asserts that a border is visible. It was caught by reading
the diff. **A class that reads like a refinement of another class may be a
replacement for it**, and the CSS framework will not say which.

---

## 2026-08-27 — The deploy ships the working tree, so a correct repository proves nothing

A deploy took live down for about four minutes. The cause was a carriage return
in `docker/entrypoint.sh`: the kernel read the shebang as an interpreter
literally named `bash\r`, the container exited 127 before any Python ran, and
Fly restarted it ten times and gave up.

**Everything that was supposed to prevent this was in place and none of it
fired.** `.gitattributes` carried `*.sh text eol=lf` **and a comment describing
this exact failure, including the words "crash loop with nothing in the logs
pointing at the cause"**. The blobs in git were LF. `git status` was clean. The
full suite was green. The file on disk was CRLF.

**The gap: `flyctl deploy --remote-only` uploads the build context from disk,
not `git archive HEAD`.** So the artifact that ships is the working tree, and
every check that reads the repository — status, diff, the committed blob, CI —
is looking at a different object than the one being deployed. They agreed with
each other and all of them were irrelevant.

And `text eol=lf` does not do what it looks like it does. It normalises on
checkout and on staging; **it does not reach back and rewrite a file already
sitting in the working tree from before the rule existed.** An attribute added
after a file was checked out is a rule with no retroactive effect, and nothing
announces that.

Three habits:

1. **Ask what the deploy actually uploads.** If it is the working directory,
   then "the repo is correct" is not evidence about the deployed artifact, and
   the check has to read the same bytes the uploader will. The guard written
   here reads the working tree on purpose, and says so, because the obvious
   implementation — `git show HEAD:file` — would have passed throughout.
2. **A convention recorded in a config file is not enforcement.** `.gitattributes`
   stated the rule perfectly and had no way to fail. The distance between "we
   wrote down that this must not happen" and "something breaks when it does" is
   the whole distance.
3. **Failures upstream of the interpreter are invisible to every
   application-level guard.** No test, migration guard or health check can run
   in a container that dies at exec. When a deploy fails, read whether the
   process ever started before reasoning about what it did.

**And one thing that went right, worth copying:** the deploy tool reported
`Unrecoverable error: timeout reached waiting for health checks... request
canceled` — a *client-side* API timeout, which is not the same as a health check
failing, and the exit code could not tell the two apart. Reading the logs rather
than trusting the exit code is what found the real cause in one step. This
repo's standing rule that `flyctl` output is lossy applies to its failures too.

---

## 2026-08-27 — Deliberately producing the signature an alarm watches for disables the alarm, and nothing announces it

An alarm was built to catch one specific thing: a notification row claimed and
then never delivered, because the process died between the claim and the send.
It had a real incident behind it — the loop died, nobody was told, and nothing
said so for months.

Eleven days later a feature was added that claims a row and deliberately never
sends it. It is correct, it is well argued, its docstring explains itself at
length. It also produces **the exact signature the alarm looks for**, three
times a day, forever. The alarm now reads 5 on a day when nothing failed, and
the state file was telling the next session to check that it read 0.

**The pattern: an alarm is a claim about what a signature MEANS, and that claim
is invalidated by any new code that produces the signature on purpose.** Nothing
breaks, no test fails, no exception is raised. The alarm keeps working perfectly
and now means something else.

Two properties make it hard to see from inside the change:

1. **The new feature is on one side of the system and the alarm is on the
   other.** Here the writer is a notifier and the reader is a health endpoint,
   two modules apart, and the shared vocabulary is a single column's zero.
2. **The failure direction is towards silence.** A false alarm gets
   investigated once and then normalised, and a normalised alarm is a deleted
   alarm that still costs a line of JSON. That is worse than an alarm that
   never fired, because it reads as coverage.

**The habit: when writing a row, a flag, a log line or a status that mimics an
existing failure state, go and find every reader of that state before shipping.**
`grep` for the column, not for the feature. The question is not "is my write
correct" — it was — but "who else has already decided what this value means".

And the repair shape is the same every time: **the writer declares its intent at
the point of writing, because no reader can recover it afterwards.** A claim
with no send and a death mid-send are indistinguishable in the record by
construction; only the process that chose knows which one it is. A deduction —
joining on a shared timestamp, matching a sibling row — would be a guess dressed
as a check.

---

## 2026-08-27 — A fixture can occupy the wrong branch, and then full coverage means nothing

A function had two routes with opposite meanings: one picks a collection
*known* to contain the legs, the other guesses by ticker prefix and checks
nothing. The test file for it had 19 green tests.

Every one of them ran the guessing route. The shared fixture built a collection
with **zero legs**, so the coverage test `legs <= collection.legs` was false on
every call and the fallback returned each time. The production-normal route —
100% of the live slate the day this was found — had never been executed once.
The fake downstream of it ignored its arguments, so it accepted whatever the
wrong route produced.

**This is not "a test that describes the code instead of constraining it", and
it is not "a test that asserts the ledger instead of the behaviour". It is one
step earlier: the test never reached the code it claims to be about.** Line
coverage was total. Branch coverage would have looked fine too — the branch was
covered, just always the same one.

The tells, in order of how early they would have caught it:

1. **A fixture whose value is empty, zero, or `None` for a field the code
   branches on.** `FakeCollections([])` is the smallest thing that satisfies the
   type and the largest thing that changes the answer. An empty collection is
   not a neutral default; it is a specific and unusual case.
2. **A fake that ignores an argument the real callee acts on.** If the stub
   takes `legs` and never reads them, no test in the file can be about legs.
3. **No test names the branch.** There was no test called anything like
   "covering wins over the fallback". A branch nobody has named is a branch
   nobody has checked.

**The general habit: for any function with more than one route, ask which route
the default fixture takes, and make the answer the one production takes.** Then
a test that wants the other route has to ask for it by name — which is also how
the file ends up documenting that there are two.

A second thing fell out of the same fix and is worth keeping: **the canned
response fixture echoed back legs that had nothing to do with the request**, and
that had gone unnoticed for the file's whole life because nothing compared the
two. Adding the comparison broke every test at once. **A fake that can afford to
be unfaithful is a fake nobody is checking against** — the unfaithfulness is not
the bug, it is the symptom that a real property was going unasserted.

---

## 2026-08-27 — A guard that would refuse everything is an outage, and the venue's sentinels are where it comes from

Three checks were drafted against fields a venue reports about itself:
refuse when the leg count is outside `[size_min, size_max]`, and refuse when
`is_all_yes` is false while the code posts all-YES. All three read as obviously
correct.

Then the committed capture was opened. Every collection the desk can actually
use carries `size_min 2`, `size_max 0`, `is_all_yes False`. So `size_max = 0`
is an **unbounded sentinel**, `is_all_yes = False` means **unrestricted** rather
than yes-only, and two of the three guards would have refused *every single
tap*. One survived.

**The pattern: a field name describes what the field is for, not what its values
mean, and zero/false are exactly where a wire protocol hides "no limit" and "no
restriction".** Reading them as arithmetic is the default mistake, and it fails
in the most confident-looking direction: the code refuses, refusal looks like
safety, and the guard is indistinguishable from working until someone notices
nothing has been priced in a week.

**The check before writing any guard on venue data: what fraction of real
traffic does this refuse?** Run it against the committed capture and count. A
guard that refuses 0% is possibly decoration; a guard that refuses 100% is an
outage; the interesting ones are in between, and you cannot tell which you wrote
without looking at real values.

And this is the same rule as CLAUDE.md's first: *a large apparent edge is a bug
until proven otherwise*, pointed at guards instead of at edges. A check that
fires far more than expected is a bug in the check before it is a discovery
about the world.

---

## 2026-08-27 — A test written against a re-implementation cannot fail for the reason it exists

A predicate lived as a closure inside a long `main()`. To test it, the test
file re-implemented its four lines against the real state object it reads. The
tests passed, read well, and named the properties that mattered.

Then the **real** predicate was mutated — its consume removed, and its
watermark differenced by one instead of read. Both mutations were **GREEN**.
Nothing in the test file touched the code under test.

**The pattern: a copy of the logic is satisfied by the code as written and by
every other implementation too, so it constrains none of them.** This is the
same failure as *"a test written after the code describes it"* and as
*"asserting the ledger instead of the behaviour"*, one step further out — and
it is harder to see, because a re-implementation looks like a unit test rather
than like a description. The test file even said out loud that it was a
re-implementation, with a source pin beside it as compensation, and the source
pin only checked the call site.

**The fix is never a better copy. It is to move the code somewhere the test can
reach it.** Here the predicate read a field on `LoopState`, so it belonged in
`scheduler.py` beside it; the closure was the accident. Both mutations bit
immediately afterwards.

Two habits:

1. **If testing something requires re-writing it, that is a design signal, not
   a testing problem.** Untestable-in-place usually means the logic is sitting
   in the wrong scope — inside a `main()`, inside a request handler, inside a
   loop body.
2. **A source-text pin is not a substitute for reaching the code.** It can say
   *that* a function is called; it cannot say the function is right. When both
   are needed, write both and say which does which — one of them will otherwise
   be quietly load-bearing for a job it cannot do.

The tell that would have caught it earlier: **the test file imports the state
object but not the function under test.** If the import list does not contain
the thing whose name is in the test class, ask what is actually being executed.

---

## 2026-08-27 — A test that asserts the ledger is not a test of the behaviour the ledger records

Two guards written the same hour passed on the first run and came back GREEN
when mutated. Both had the same shape, and it is not the shape the earlier
lesson names.

The earlier lesson is *a test written after the code describes it rather than
constraining it*. These did not describe the code. They asserted a **stored
consequence** of the behaviour instead of the behaviour:

- The scheduled parlay card must not spend the change channel's daily ceiling.
  The test asserted `_parlay_pushes_today(...) == 0` — the row count in the
  ledger. The mutation incremented the **in-memory** counter that actually
  gates the next send and never touched the ledger, so the assertion held
  while the property it exists for was broken.
- A ceiling shared across three rungs of one ladder. The test asserted the
  ladder sent one card. The mutation replaced a local counter with a re-query
  that returns the same number, so nothing moved — and the docstring's claim
  that this mutation had once been observed red was simply false.

**The pattern: a ledger, a counter and a log are *records of* a decision, and a
decision can be changed without changing its record.** Asserting the record is
cheap, reads like a strong check, and is satisfied by any mutation that acts
before the record is written or on a different copy of the state.

The discriminating question, asked before writing the assertion: **if this
behaviour were wrong, would the thing I am asserting still be right?** For a
ledger the answer is usually yes, because the ledger is written by the same
branch the mutation left alone.

Two habits that convert one into the other:

1. **Assert the next decision, not the record of the last one.** "The ceiling
   was not spent" becomes "a later composition that had earned a push still got
   one". That forces a fixture where something downstream depends on the value.
2. **When the fixture for that is intricate, the intricacy is the finding.**
   The channel-separation guard needed a call in which one rung takes the
   scheduled branch while another falls through settled — because that is the
   *only* state in which the two channels meet. A property with one narrow
   interaction state is worth knowing about; writing the easy ledger assertion
   instead is what hid it.

And a note on the second case, kept because deleting it would repeat it: the
docstring asserting "mutation observed red" was **inherited from an earlier
version of the code** and was never re-checked when the code around it changed.
A recorded mutation result ages exactly like any other measurement. Re-run the
battery when the code under it moves; do not carry the sentence forward.

---

## 2026-08-27 — Verify against `origin`, not against `main`, because the object store makes them look alike

An integrator merged, ran `git log --oneline -1 main`, saw the merge, and
reported "done". `origin/main` was seven commits behind. Twice in one session.

**The read passes because the object store is shared.** From the integrator's
seat a local merge and a pushed merge are indistinguishable — even a lane in
another worktree can `git show main:<file>` and see the new content, because
the objects are right there. The only check that separates them is
`git log --oneline -1 origin/main` **after a fetch**. Both gaps were caught
from outside, by a lane that had stopped trusting `origin` and `main` to be the
same word.

**Why it is not merely untidy.** An unpushed ADR number or `SCHEMA_VERSION` is
the ordinal race reopened — a lane fetching in that window sees the number as
free, takes it, and the duplicate merges cleanly like every other instance. The
whole merge-time allocation rule assumes the allocation is *visible* the moment
it is made, and a push gap breaks that assumption without breaking anything
that would announce itself.

## 2026-08-27 — A fact that is displayed but is not a finding does not get acted on

The board had printed `vs origin N unpushed` in its LANES section the whole
time. It was true, it was on screen, and it was missed twice — because a reader
scans the FINDINGS block and the VERDICT line, which is where the tool says
what it *thinks*, and skims the inventory above it, which is where the tool
says what it *saw*.

**The pattern: in any report, the section a reader acts on is the one that
carries conclusions, and everything outside it is decoration until it is
promoted.** Putting a fact somewhere in the output is not the same as
surfacing it. Ask which block a hurried reader reads, and whether the fact is
in that block.

This is the same failure as the two wording defects the same day, one layer up.
There the hedge lived in the module docstring while the finding text overstated
— **the docstring is not what a person acts on**. Here the observation lived in
the inventory while the verdict stayed silent. In all three the correct
information existed somewhere in the artefact and was not where the decision
was made.

## 2026-08-27 — A relayed approval is information, not authority, and the word "settled" is where it goes wrong

A lane put a question to Joe and refused to let a peer answer it. The peer
asked Joe, got a yes, and relayed it as **"Joe says commit. You are clear."**
The lane held anyway, and was right to.

**The failure was not asking on someone's behalf — that was useful. It was one
word doing work the message could not support.** The same relay phrased as
*"I asked Joe and he said yes; go get it confirmed in your session"* carries
everything true and claims nothing it cannot. "Settled" asserted a thing only
the other party could verify.

**Two properties make this worse than it looks.** A relayed approval is a
*stronger* claim than the relayer's own ruling — "he said yes" outranks "I say
yes" — and it is exactly as unverifiable from the receiving end. Strength and
unverifiability moving together is the signature of a claim to distrust, not
one to accept.

And the direction matters: the relay arrived carrying the answer the receiver
wanted. **A rule honoured only until the answer goes your way was never a
rule** — which is the receiver's formulation, and the reason it held. The
person relaying is the one least placed to notice this, because from their side
the approval is real and the caution looks like doubt about their honesty.

The general form: **when passing on someone else's authority, pass on the
evidence and the route to verify it, never the conclusion alone.** Say who said
it, where, and how to check. The receiver decides what it settles.

## 2026-08-27 — A count with no denominator invites an adjective, and the adjective is the inference

A read returned "35 prop legs". It was written up as **partial** coverage, and
a code risk was designed around that word — a pre-tap check whose motivation
was "eligibility is partial, so the fallback fires often". Nobody had measured
what 35 was a fraction of.

It was 35 of 35. Coverage was total on that slate, and the risk as stated did
not exist.

**The pattern: a bare count carries no adjective, so the reader supplies one,
and the supplied adjective then gets built on as though it were measured.** The
tell is that the number arrived alone. `35` is a measurement; "35, which is
partial" is a measurement plus a guess wearing the measurement's authority.
Two figures in `.env.example` went wrong in this exact shape, in the same
direction, which is why the lane that produced the 35 refused to divide by an
assumed slate size and asked for the denominator instead. That refusal is the
behaviour to copy.

**And when the denominator arrived it was 35 against 35 — which is the moment
to spend more scrutiny, not less.** Two equal totals is a perfectly convincing
coincidence. What turned it into a result was a per-series *set* comparison:
same event tickers, `open_but_not_eligible` and `eligible_but_not_open` both
empty. Same move as reading `detail_missing = 0` before trusting a zero.
**Check the thing that would make the good answer fake, before reporting the
good answer.**

The correction did not license the opposite adjective either. n = 7 games at
one instant is not "total" any more than 35 alone was "partial". The sentence
that survives names its scope: *on this slate, all 35 open prop events were
eligible; whether that holds structurally is unmeasured.* The code risk stayed
on the backlog with its reason replaced rather than being deleted — the failure
mode is real, it simply does not fire today.

## 2026-08-27 — A reporting tool must be run from every seat it will be run from, and its findings must not be phrased as instructions

A cross-worktree detector was written, tested and demonstrated from the
integration checkout, where it was correct. Run from a **lane**, it named
sixteen of Joe's unrelated repositories as leftover directories to delete —
including the predecessor project `CLAUDE.md` tells every session to read. The
cause was one line: it excluded "the tree I am running in" instead of "the
integration tree", so from a lane the main checkout looked like an ordinary
worktree and its parent — a general projects folder — became a search root.

**Two patterns, and the second is the one that could have done damage.** The
fixture half of this — why no test could have caught it — generalises further
than this incident and has its own entry below, *The fixture asserted the bug
away*, written from the lane that found it.

**An instrument's answer can depend on where it is invoked from, and testing it
from the author's own seat covers one case out of however many exist.** When a
tool reads the *environment* rather than only its inputs, the layout in the
fixture is part of the assertion — get it wrong and the tests agree with the
bug.

**A false positive phrased as an instruction is a destructive tool.** The
finding ended "a human deletes it". A finding that ends in an imperative is
acted on; one that ends in an observation is checked. Any output a person may
act on without re-deriving it must say what was *observed* and what could not
be established — here, "carrying no `.git` of its own… nothing can be
established about its contents from here; check before removing it." The cost
of the imperative is not a wasted minute, it is the deletion.

**It was caught by a peer running the tool for its own reasons, not by its
author or its tests.** That is what the oversight loop is for, and it worked in
the direction it was not built for. Do not treat "I reviewed it" as covering
"someone else ran it somewhere else".

## 2026-08-27 — The fixture asserted the bug away

Written from the `parlay_props` lane, which found both instances, and merged verbatim rather than paraphrased. It extends the layout half of the entry above to cardinality, which is the harder case.

### The pattern

**A fixture encodes assumptions about the world, and a test can only find bugs
its fixture is capable of expressing.** When the fixture's shape is wrong, the
test does not fail — it passes, and it passes *specifically on the case the
guard exists to catch*. Green then means "my fixture cannot reach the defect",
which is indistinguishable from "there is no defect".

Two instances on one day, and the difference between them is the point.

#### Layout — the collision detector

`scripts/lane_board.py` told a human to delete sixteen unrelated projects,
including the predecessor repo `CLAUDE.md` instructs every session to read.

Run from the integration checkout it was correct. Run from a **lane**, the
integration checkout read as a peer worktree and its parent — the whole
projects folder — became a lane root. No test caught it because the fixture put
lanes in the same parent directory as the checkout, which is not the deployed
layout. The one condition that breaks the script could not occur in the
fixture.

Their formulation, which is the right one: *when a tool reads the environment
rather than only its inputs, the layout in the fixture is part of the
assertion.*

#### Cardinality — the parlay prop dedupe

`ladder_candidates` keyed its freshest-row map on
`(link_id, market, outcome_name, outcome_point)`. On a prop, `outcome_name` is
only `"Over"`/`"Under"`, so the player has to be in the key or players sharing
a rung collapse and `setdefault` silently keeps whichever arrived first.

The test written for exactly that defect **passed with the fix reverted.**

The fixture seeded one Kalshi prop event per player, so each player got its own
`event_links` row, its own `link_id`, and the four-tuple key was already unique.
The real structure — counted off the committed
`tests/fixtures/events_mlb_props_nested.json` — is one prop event per game **per
statistic**, holding every player in it: `KXMLBTB-26AUG151310CWSDET` carries 66
markets across **18 distinct players**, and batters' rungs cluster on
0.5/1.5/2.5, so one `link_id` covers many players sharing a line.

With the fixture corrected to that cardinality, reverting the fix drops a
pitcher from the pool, which is what the test claimed to detect all along.

### Why the second one generalises further

The first is about **layout** — where things sit. The second is about
**cardinality** — how many of X hang off one Y. Cardinality is harder to notice,
because a one-to-one fixture reads as a simplification rather than as a claim,
and it is worse when wrong, because one-to-one is the case in which most
grouping, keying and dedupe bugs are invisible by construction.

### What to do about it

- **Mutation-test every guard, and treat a green mutant as a fixture bug
  first.** Both of these surfaced only because the fix was reverted and the
  test still passed. CLAUDE.md already requires this; neither would have been
  found without it.
- **When a fixture is one-to-one, say why in a comment, or make it many-to-one.**
  If the real cardinality is unknown, that is the thing to go and measure — in
  both cases above the answer was already committed in the repo.
- **Prefer counting the real artefact to inventing a shape.** The 18-players
  figure came from a captured payload already in `tests/fixtures/`. The fixture
  had been wrong beside the evidence that corrected it.

## 2026-08-27 — A detector's granularity is decided by its false-finding risk, not by what is easy to compute

A cross-worktree collision detector was specified against a hand-measured
"collision surface" of two files. At **file** level that is what it looked
like. At **hunk** level one of the two was not a collision at all: the lane's
edit was at line 685 and main's was an append at line 2467, 1,780 lines apart
and semantically unrelated. That merge is clean, and a file-level detector
would have opened its life by crying wolf on it.

**The pattern: when you build something that reports problems, ask what its
FIRST output on real data will be, and whether that output is true.** A guard
whose first finding is false gets weakened or deleted — this repo already pins
that reasoning in `tests/test_parallel_lanes_do_not_collide.py`'s `0006`
companion exemption — and the cost of the coarser comparison is not "slightly
noisier", it is the whole instrument.

The same question caught a second one in the same file. A lane sitting ten
commits behind holds main's **old** `SCHEMA_VERSION` without ever having
touched `db.py`. Comparing *values* reports that as a collision; comparing
*provenance* — did this tree change the file since the merge-base? — reports it
as inherited, which is what it is. **Inherited is not claimed.** Any check on a
global counter across branches has this failure mode, and the discriminator is
always provenance rather than value.

## 2026-08-27 — A test can pass for a reason you did not write, and only mutation finds out which

Sixteen guards on a new instrument were mutation-tested. Fifteen went red.
The one that stayed green was **the load-bearing one** — "an unreadable
worktree is never reported as clean". Breaking the error return in
`dirty_files` did not fail it, because the test deleted the worktree directory
and a *different*, earlier check (`if not path.is_dir()`) caught that. The
assertion was true, the behaviour was covered, and the line it was written to
protect had no coverage at all.

**The pattern: a green test tells you the assertion holds, not that it holds
for the reason you intended.** Only mutating the specific line separates those,
and the tests most worth mutating are the ones guarding the failure you would
least like to have — because a plausible-looking test there is exactly what
stops anyone writing a second one. The fix was a second case that reaches the
same guard by another road: a worktree whose directory **exists** and whose
`.git` pointer is corrupt.

This is the sibling of the 2026-08-26 lesson that a mutation can lie by not
landing. There the mutation missed the code; here it landed and the *test*
missed the code. Both are answered by the same discipline — check what the
mutation actually reached, not just that something went red.

## 2026-08-27 — A schema version is a claim about the whole database, so a lane cannot allocate one

Two branches were open at once. One added `parlay_card_candidates` and bumped
`SCHEMA_VERSION` to 23. The other added `parlay_positions` and
`parlay_position_legs` and bumped `SCHEMA_VERSION` to 23. Each was correct on
its own, each shipped with the "a pure new table needs no migration step"
reasoning intact, and each was verified against a v22 database.

**The failure is silent, and that is what makes it worth a lesson.** A volume
stamped v23 would carry one pair of tables or the other depending on which image
booted it. `open_db` refuses on a version *mismatch* — and there is none. The
stamp matches, so nothing looks wrong; what breaks is a query against a table
that was never created, arriving as an error from somewhere else entirely.

Merging caught it here only because both branches touched `db.py` on the same
line. **Had one of them bumped the constant in a second place, or had the file
been formatted so the two edits did not overlap, git would have merged them
clean and produced a tree claiming v23 with four new tables and no record of
which version introduced which.**

**The pattern: any counter that names a global state cannot be incremented from
a branch that can only see itself.** `SCHEMA_VERSION` is one. So is any
migration ordinal, any "next ADR number", any fixture index. A lane picks a
value that was free *when the lane started*, which is a different question from
whether it is free now.

Two things that would have caught it earlier, neither of which exists:

- **A test that the version and the table set agree.** `SCHEMA_VERSION` is a
  number; nothing asserts what schema it names. A checksum over
  `sqlite_master` for a freshly built database, pinned per version, would go red
  on any second allocation of the same number.
- **Reading `main` before allocating.** `git show main:backend/store/db.py |
  grep SCHEMA_VERSION` is three seconds and was not run at the start of the
  lane, because the lane's own tree said 22 and that looked like the answer.

**The ADR number collided too, in the same merge, and the first version of this
lesson said it "got lucky".** It did not. Both lanes wrote a `docs/adr/0074-*.md`
— "the desk draws four pictures" on one and "the desk watches what Joe holds" on
the other — and git merged them **clean**, because they are different filenames
that happen to share a prefix. Nothing conflicted, nothing was reported, and the
tree carried two ADR 0074s with two dozen cross-references pointing at an
ambiguous number. Renumbered to 0077 afterwards, by hand, across 24 files.

That is the version of this failure with no safety net at all: the schema
collision was caught only because both edits landed on the same LINE of
`db.py`. **Filename-prefix allocation has no line to collide on.** A `ls
docs/adr/ | tail` on `main`, not on the lane, is the whole check.

**"Read `main` before taking one" is NOT the fix, and this lesson said it was
for about an hour.** While the merge above was being tested, `main` gained
another commit that took ADR **0077** — the number this lane had just renumbered
*to*. Three collisions in one day, on two different counters, and the second
renumber happened for the same reason as the first.

Reading `main` at the start of a lane answers "what was free when I started",
which is not the question. A lane that runs for hours is racing every other lane
for the whole of it, and the check has a window exactly as long as the gap
between looking and pushing.

**The fix is to allocate at MERGE time, not at write time.** Concretely:

- Write the ADR under a name that cannot collide — a slug with no ordinal — and
  number it in the merge commit, after `git fetch`, as the last thing before the
  push.
- Or number it optimistically and treat `ls docs/adr/ | tail` + `git show
  main:backend/store/db.py | grep SCHEMA_VERSION` as **part of the push**, not
  part of the planning. Re-run them after every `git fetch`, however many times
  that is.

Three counters in this repo name global state and can each be allocated twice:
`SCHEMA_VERSION`, the ADR ordinal, and any migration step number. **None of them
is safe to hold across a test run.**

---

## 2026-08-26 — A mutation can lie, and a green result is not evidence until you know the mutation landed

A component was forbidden from drawing a value. To prove the guard bit, the
value was inserted back into the markup and the test re-run. It stayed **green**.

The obvious conclusion — "the test is decoration" — was wrong. The insertion
had gone into a `<details>` that appears in the file's own **docstring**, three
hundred lines above the real one. The file changed. The string was present. A
grep for it succeeded. And no code had been touched.

**The pattern: a mutation is itself a change that can fail silently, and every
way of checking it "worked" is satisfied by a change to the wrong place.** The
file's mtime moves, the diff is non-empty, the mutated string greps — all true
of an edit to a comment. So a green test after a mutation has two readings and
they are opposites:

- the guard does not bite, or
- the mutation did not land where the guard looks.

Only the second is cheap to rule out, so rule it out first. **Assert the
mutation's effect, not its presence**: count the real call sites, print the
line number, or slice the file the way the test slices it and confirm the
change is inside that slice.

Corollary for source-scanning tests specifically: strip comments in the TEST,
and prefer an anchor that cannot exist in prose. `s.index("<details")` finds
whichever comes first; `s.index('<details className="w-full')` finds the
element.

Same family as *"count your tests"* — a denominator nobody printed is a
denominator nobody checked — one level further out: **a control nobody
verified is a control that proves nothing.**

---

## 2026-08-26 — A test written after the code describes it; a test written against a claim constrains it

Six guards written in one day passed on the first run and failed to bite when
mutated. Each was rewritten rather than kept, and they had one shape in common.

- A stub that returned the same answer for every key, so the code could be
  handed either vocabulary and pass.
- An LRU test whose fixture kept the hot key newest, so eviction-from-the-front
  and eviction-from-the-back both preserved it.
- A `for phrase in (...): if phrase in text: continue` loop that asserted
  nothing at all.
- An assertion ending in `or True`.
- A guard that asserted an alias file "buys something" but not that removing an
  entry costs anything — so a silently dropped entry stayed green.
- An assertion on a display string rounded past the resolution of the thing it
  was pinning.

**The pattern: writing the test after the implementation makes the
implementation the reference, and the natural sentence to write is a
description of what the code does rather than a constraint on what it must
do.** A description is satisfied by the code as written, which is exactly the
condition under which mutation testing finds nothing.

Two habits that convert one into the other:

1. **Name the claim in the test name, then make the body the smallest thing
   that could refute it.** "eviction is LRU" is a description; "asking again
   protects an entry from eviction" is refutable, and it forces the fixture
   that separates the two orderings.
2. **Before writing the assertion, write down what the fixture would have to
   look like for the wrong behaviour to pass it.** If the answer is "the
   fixture I already have", the fixture is the problem, not the assertion.

The repo rule already says every guard is verified by disabling it and watching
it fail. This is why the rule cannot be relaxed to "and the obvious ones are
fine": the obvious ones are precisely the ones written as descriptions.

---

## 2026-08-26 — Fifteen minutes of measurement outranked a day of planning, and the plan had ranked by what looked expensive

A plan written from reading the code ranked the serving-path work: an N+1 into
a 6.9-million-row table first, an unbounded `GROUP BY` second, everything else
after. All of it real. None of it measured, because the box had been
crash-looping and no reading would have meant anything.

Once the box stayed up, twenty curls with a session cookie said:

    /api/slate     0.38s warm     <- ranked FIRST from the code
    /api/parlays   2.32s warm     <- not on the list at all

The N+1 is genuinely there and genuinely grows. It is not what a person waits
on. What they wait on is a 200,000-sample Monte-Carlo recomputed per request,
which reads as a single innocuous function call.

**The pattern: reading code ranks work by how expensive it LOOKS, and cost in
source is a poor proxy for cost in time.** A loop over rows advertises itself;
one call to a pure function does not. The proxy fails hardest exactly where the
expensive thing has a clean interface — which is what a good abstraction is.

Two consequences worth keeping:

- **A plan's ranking is a hypothesis, and the measurement that tests it is
  usually much cheaper than the first item on the list.** Take the measurement
  before executing the plan, not after.
- **State the ranking in the write-up when it turns out wrong.** The
  measurement doc for this says the plan ranked the slate first and the slate
  is 0.38s. A doc that quietly reports the right answer teaches nothing about
  how the wrong one was reached.

Corollary on prerequisites: this measurement could not have been taken honestly
the day before, because the machine was off half the time. **When an
environment is broken, measurements of it are not merely noisy — they are
measurements of a different system**, and the right order is fix, verify the
fix, then measure.

---

## 2026-08-26 — State that outlives a request outlives a test, and the tests that break are the ones that never heard of it

A per-request memo was hoisted to a module-level cache to stop a Monte-Carlo
being recomputed on every HTTP request. Correct, and measured: 345ms to 2ms.

The full suite then went red in a test written months earlier, in a different
file, that counts how many times the expensive function is called. Nothing was
wrong with the cache and nothing was wrong with that test. What was wrong is
that the two now shared state, and which one ran first decided the answer.

**The pattern: making something live longer than a request also makes it live
longer than a test, and the tests it breaks are the ones with no knowledge of
it.** The author of the cache knows to clear it; the author of a test written
before the cache existed cannot.

So the reset belongs in `conftest.py`, autouse, not in the new test's own file.
Clearing it locally protects the tests that already know about the hazard and
leaves unprotected exactly the ones that do not — and it puts two definitions
of one guard in the repo, which is how they drift apart.

This repo already had the precedent, with the reasoning written out:
`forget_scope_warnings` exists because a process-lifetime warning cache made
"which test ran first" a hidden input. Same hazard, same fix, one file apart —
**worth looking for the existing precedent before inventing the mechanism**,
because a codebase that has met a hazard once usually names it somewhere.

Checklist when introducing anything process-scoped — a cache, a memo, a
warned-once set, a connection pool: *what does a test see if a previous test
already populated this?* If the answer is "a different result", the reset is
part of the change, and it is global.

---

## 2026-08-26 — A test that does real work to check a cheap property is a test that stops being run

A cache was bounded at 256 entries. The test asserting the bound drove eviction
through the real builder, so checking `len(cache) <= 256` ran a 200,000-sample
Monte-Carlo copula roughly three hundred times. It took 71 seconds on its own
and was the slowest thing in the suite — **inside the commit whose entire
subject was not recomputing that copula.**

Stubbing the expensive function took the file from 80 seconds to 4 and tested
exactly the same property, because the property was never about the copula. It
was about a dictionary.

**The pattern: a test's cost should be proportional to what it asserts, and
driving a cheap assertion through an expensive real path is the commonest way
that goes wrong.** It usually happens because the expensive path is the
convenient way to produce the state — which is a reason to reach for it, not a
reason it belongs.

Ask of any slow test: *which line is the assertion, and how much of the runtime
is upstream of it?* If the answer is "nearly all of it", the upstream is setup
and setup can be stubbed.

The stakes are not tidiness. A suite is a guard that only works while people
run it, and every minute added raises the odds it gets skipped, backgrounded,
or trusted from memory. **A test nobody waits for has the same value as a test
that does not exist**, with the added cost of looking like coverage.

---

## 2026-08-26 — A guard that greps its own module must read the code, not the prose

`test_the_watcher_spends_nothing_metered` asserts `"api_credits" not in source`
over `backend/hedge_watch.py`. It failed on the module's own docstring, which
explains — correctly, and usefully — that no `api_credits` row is written.

Both obvious fixes are worse than the guard. Weakening the assertion removes the
thing it was for. Deleting the sentence removes the explanation a reader needs
and leaves the next person to rediscover why the module is written that way.

**The pattern: a source-grep guard is asserting about *behaviour*, so it must
read the tokens that produce behaviour.** Comments and string literals are
exactly where the words it is searching for legitimately appear — and the better
the module is documented, the more likely the guard is to fire on it. So the
better-documented a codebase gets, the more this class of test punishes it.

`conftest.python_code_without_prose` tokenizes and drops `COMMENT` and `STRING`.
Tokenizing rather than regex, because a `#` inside a string and a triple-quote
inside a comment both defeat the regex, and every identifier a guard needs to
catch survives as a `NAME` token either way.

Add a vacuity guard beside it (`assert "watch_hedges_forever" in code`): a
stripper that ate the module would make every assertion pass.

---

## 2026-08-26 — A GREEN mutation is a claim about the harness before it is a claim about the test

Four mutations survived a run over `notify/alerts.py` and `hedge_watch.py`. Read
at face value, that is four holes in the tests. Checked by hand, **two of the
four were the harness patching the wrong code**:

- `Alerter.parlay_cards` and `Alerter.hedge_locks` both contain the exact lines
  `if key is None:` / `continue`. `source.replace(old, new, 1)` takes the
  **first** occurrence, so the mutation landed in the function nobody was
  testing, the tests passed, and it read as a hole.
- A second anchor was mangled by heredoc escaping and matched nothing, which the
  harness reported as `ANCHOR MISSING` — the one failure mode it *does* name.

The two genuine holes were real and worth the run. The false ones cost as long
to chase as the real ones took to fix.

**The pattern: a mutation that stays GREEN must be reproduced by hand before it
is treated as a finding.** Apply it, run the one test that should have caught
it, look at the diff. And when a codebase has two functions that legitimately
share a line — which is normal for a policy module with several event types —
anchor on the surrounding line that is unique, not on the line being changed.

**And the third hole was a vacuous test, which the harness found correctly.**
`test_a_failing_cycle_never_takes_the_loop_down` ran the watcher against an
empty database, so `anything_in_progress` was False, the cycle body never ran,
and the `try/except` under test was never entered. A loop guard tested on an
idle system tests nothing. **Seed the condition that makes the body run**, and
say so in the test, or the next reader deletes the seeding as noise.

---

## 2026-08-26 — Rule 1 has a scope, and it belongs on the input rather than on the result

CLAUDE.md rule 1 is that a large apparent edge is a bug until proven otherwise.
The plan for the hedge feature applied it the obvious way: suppress a lock that
is large relative to the stake.

That would have silenced the feature at its most useful. A $4.99 ticket
returning $333.33 with one leg left, hedged at even money, locks about $172 —
**34x the stake, and entirely real.** It is simply what hedging a longshot
parlay looks like. A lock-to-stake rule fires hardest on exactly the cases the
feature exists for.

What catches a genuine bug is an invariant that **cannot be true of the input**:
both sides of a book quoting for a dollar or less together is free money, which
no real book offers, so it is bad data by construction.

**The pattern: before writing a suppression, name the legitimate value it would
silence.** If you can name one, the rule is keyed on the wrong quantity — move
it from the result to a property of the input that no valid input can have. Rule
1 is about *apparent* edges; a number that is large because the arithmetic says
so is not an apparent edge, it is an answer.

Pin the absence with a test. `TestRuleOneIsAppliedToTheBookAndNotToTheSizeOfTheLock`
asserts a 34x lock is reported, so a future session that adds the suppression
goes red and has to reopen the ADR rather than quietly re-deciding it.

---

## 2026-08-26 — An unknown budget must not resolve to zero, exactly as an unknown price must not

The repo's oldest rule is that an unreadable price resolves to `None`, never
`0`. It was written about prices and the same shape reaches anything a decision
is bounded by.

`latest_balance_tenths` answers `None` whenever the newest five-minute poll
could not read the venue's figure — a routine outage, not an empty account.
Folding that into an affordability cap of **0 contracts** would have made every
hedge unaffordable and **silenced the alert for exactly as long as the mirror
was behind**.

The direction is what makes it dangerous. A price that wrongly reads zero
manufactures an edge and gets caught by a suppression rule; a *budget* that
wrongly reads zero produces silence, and silence is indistinguishable from
"nothing is happening". Nothing fires, nothing is logged, and the feature looks
like it is working.

`affordable_contracts` returns `(count, known)` as a pair so a caller cannot
take the number without the flag, falls back to what the order book allows, and
the screen says the cap is not real.

---

## 2026-08-26 — Killing a background command's shell does not kill the process it started

A full-suite run launched in the background was stopped by killing the PIDs the
process table showed. It reported success, the task notification arrived, and
the **actual pytest kept running** — detached from the shell that started it.

The cost was not the wasted CPU. A second suite was then launched beside it,
the two competed for a shared-core laptop, throughput fell to ~12 tests a
minute, and the run projected out to six hours against a 14-minute history. That
read as a hang in an unfamiliar worktree, and the next twenty minutes went into
diagnosing a slow test file that was not slow.

**The pattern: after killing a long-running background job, verify by the
command line rather than by the exit code.** `wmic process where "name='python.exe'"
get ProcessId,CommandLine` shows what is actually running and what it was
invoked as, which is what separates "my job" from "the job I thought I killed".

And the second half: **a full test run does not have to block editing.**
`git worktree add --detach <path> <sha>` gives the baseline its own copy of the
tree at the right commit, so the measurement is taken on files nobody is
touching — which is the property the "never patch under a running suite" lesson
actually needs, rather than serialising the two.

---

## 2026-08-26 — Fixing a defect at the call site leaves the rule where the next call site cannot find it

`derive_yes_ask` turns an absent NO bid into a YES ask. An absent bid arrives
from the venue as `0.0000`, parses correctly to `0`, and `1000 - 0` hands back
a 1000-tenths "ask" that is a settled outcome rather than a quote.

That was refused three times, in three places, over eleven days:

1. **2026-08-15, `runner.py`'s prop path.** A `ValueError` aborted a whole
   pricing pass. Fixed with `if not is_valid_price(ask): continue` **at that
   loop**, plus a comment predicting the team path would never trip it
   *"because a game moneyline does not reach 0 or 1000 while it is still
   pre-game and open."*
2. **2026-08-26, `routes.py::_tradeable_ask`.** The manual ticket rendered
   "YES 0c" on a live combination. Fixed **in the route**.
3. **2026-08-26, live.** The team path — the one the 2026-08-15 comment said
   was safe — took a 1000-tenths ask. The pass died, five dead passes ended
   the recording process, and the machine sat switched off between page loads
   for hours.

Each fix was correct. Each was local. **Two of them wrote down, in a comment,
the reasoning for why the other call sites did not need it — and that
reasoning was the thing that turned out to be wrong.**

**The pattern: when a value is unsafe, the fix belongs where the value is
*made*, not where it is *used*.** A guard at the call site protects exactly one
caller and silently declines to protect the next one somebody writes. And the
comment justifying the local scope is worse than no comment, because it reads
as evidence that the question was considered.

Two tests to reach for:

- **Assert the population of call sites**, not one of them. `assert
  src.count("= build_recommendation(") == 0` turns a new unguarded caller into
  a red test.
- **Assert the producer agrees with the consumer's own predicate**, over the
  whole input range, so the two definitions cannot drift:
  `for bid in range(0, 1001): assert (derive_yes_ask(bid) is not None) ==
  is_valid_price(1000 - bid)`.

Corollary on blast radius: the local fix in (1) *was* the whole fix for that
pass, and it still left the process able to die. **A refusal that raises needs
two things — the value stopped at its source, and the loop able to survive one
of them anyway.** Only the second one protects against the refusal nobody has
predicted yet.

---

## 2026-08-26 — A monitor that has to touch the thing it measures is reporting its own effect

`.github/workflows/heartbeat.yml` probed `/api/health` every fifteen minutes
and, for as long as it had existed, reported the live instance healthy.

The instance was switched off most of the time. `auto_start_machines = true`,
so **the probe's own curl started the machine**, and the check then read a
container that was up — because the check woke it — and called that alive. It
was also, silently, the thing keeping the box running on a 15-minute cadence.

Nothing in the workflow was wrong. Every branch it had was a real state, and
the state it could not see was the one it destroyed by looking.

**The pattern: before trusting a monitor, ask whether observing costs anything
on the observed side.** An HTTP probe against auto-start; a query that warms a
cache; a read that takes a lock; a request that resets an idle timer. In every
case the measurement is of the system *after* the measurement, and the failure
mode is always the flattering one — "it answered, so it was up."

The fix is an out-of-band read: the Fly Machines API reports `state` without
touching the app, so it runs **first**, and a stopped machine is seen rather
than woken. Where no out-of-band read exists, the honest move is for the
monitor to say what it cannot distinguish — which is what this repo's alarm
text already had to learn once (2026-08-25, "it is alive and stuck").

Same family as the entries this file already keeps under verification methods
that lie, and one step further out: not a method that reports the wrong thing,
but a method that *causes* the thing it reports.

---

## 2026-08-26 — Exit 0 means "I finished", and a supervisor that tears down on a failure is not finished

`docker/entrypoint.sh` supervises three processes with `wait -n` and tears the
container down when any of them dies, with a comment saying it does so *"so
the platform restarts it cleanly."* It ended `exit 0`.

Fly's restart policy is on-failure. It logged, accurately:

    machine exited with exit code 0, not restarting

So the container that had just announced `CHAIN RUNNER exited -- the record has
stopped growing. Restarting.` did not restart. `min_machines_running = 1` and
`auto_stop_machines = "off"` were both set and neither applies, because
**neither governs a container that exited successfully.**

The root cause was one function serving two callers with opposite meanings: a
`trap ... INT TERM`, where 0 is correct because a signal is somebody asking,
and a failure teardown, where 0 is a lie. The function took no argument, so
both got the same answer.

**The pattern: an exit code is an assertion about whether the work succeeded,
and a shared cleanup path makes that assertion on behalf of callers that
disagree about the answer.** Whenever one teardown is reached both
deliberately and by failure, it needs the caller to say which — and the
default should be the one that is safe to get wrong. Here that is non-zero: a
spurious restart costs a cold start, a missed restart costs every hour until
somebody notices.

Worth carrying separately: **the comment asserted the platform behaviour
rather than the code causing it.** "So the platform restarts it cleanly" was
never true, and it read as though it had been verified. A sentence about what
another system will do in response to us is a claim that needs an observation
behind it, not a design intention.

---

## 2026-08-26 — `load_dotenv()` makes the whole test suite a credential holder, and arming is what turns that into spending

A repo-root `conftest.py` deleted `ANTHROPIC_API_KEY` for every test, with a
docstring explaining exactly why: `backend/config.py` calls `load_dotenv()` at
import, every test imports it, so the owner's `.env` was in `os.environ` for the
whole suite and a test could bill a real API call.

The same sentence was true of `KALSHI_API_KEY` and `KALSHI_PRIVATE_KEY_PATH`,
and nobody had written the second fixture — because at the time no production
code path could ask for a live order client during a test. The dry-run constant
made it unreachable. **Flipping that constant to arm the path silently turned
`pytest` on the owner's machine into something that could send a real order to
the exchange.**

**The pattern: a guard that is load-bearing only in one configuration is
untested in the configuration where it matters, and the flag flip that changes
the configuration does not look like it touches the guard.** The diff was one
literal. Its blast radius was every test that drives the route.

Two things to carry.

**Before flipping any switch that arms a real-world effect, ask what in the test
environment is currently prevented only by the switch being off.** Not "what
does this change in production" — production is the part everyone reviews. The
question is what the *suite* was allowed to do because the dangerous path was
unreachable.

**And the fixture must fail, not succeed quietly.** The tempting alternative
here was `KALSHI_PUBLIC_READ_ONLY=true`, which hands every test a config object
that loads fine. That is worse: it removes the exception that tells you a test
just asked for credentials. The right shape is the one that raises at the first
call, so the answer to "which tests wanted a live client?" is a list of red
tests rather than silence.

---

## 2026-08-26 — A source-scan pin measures what it can still match, and it goes quiet rather than red

A test read `routes.py` and asserted that every `OrderPlacer(dry_run=...)`
passes one of two named constants. Its regex was `OrderPlacer\(\s*dry_run=([^)\n]+)\)`
— one line, `dry_run` first. Then one of the two constructions took a second
argument and wrapped onto three lines. The regex stopped matching it. The test
**stayed green**, now asserting about one call site instead of two, and nothing
anywhere said the coverage had halved.

**The pattern: a scan-based test silently redefines its own population every
time the code it scans is reformatted.** A `for x in matches: assert ...` loop
is vacuously true over an empty or shrunken match set, and the shrinking is
invisible — the failure mode is not a wrong assertion, it is a correct
assertion about fewer things.

The fix is one line and it is the general one: **assert the size of the
population before asserting anything about its members.** `assert len(calls)
== 2` turns a reformat that hides a call site into a red test that names the
count, and it turns a genuinely new third call site into something a human has
to look at rather than something the suite absorbs.

Same shape as "count your tests" in CLAUDE.md's measurement rules, one layer
down: a denominator nobody printed is a denominator nobody checked.

---

## 2026-08-26 — Pin a guard on the decision it changes, never on the string it prints

A new fee model had to be the one a per-bet cap was checked against. The test
asserted the served `worst_case_cost_display`. It passed. It also passed with
the new model removed, because the two models differ by $0.0002 at one contract
and the display is rounded to cents — **the assertion could not see the thing it
existed to pin, in either direction.**

The rewrite chose the bankroll so the cap fell strictly between the two answers:
admitted under the old model, refused under the new one. Now the test is a
statement about behaviour, and the mutation goes red.

**The pattern: a rendered value has been through a lossy transform, so it can
only pin differences larger than that transform's resolution.** Money rounded to
cents, a percentage to one decimal, a duration to "2m ago" — each throws away
exactly the precision a guard often turns on. Ask what the guard *decides*, and
assert on that: the 422 versus the 200, the refusal text, the row that was or
was not written.

Corollary, because it is the cheap version of the same check: when a test
depends on two numbers being different, **assert that they are different first**,
in the test, with a message saying the fixture no longer separates them. That
assertion is what tells the next person the test has gone blind, instead of
letting it report success about nothing.

---

## 2026-08-26 — A derived value inherits its source's absence as an extreme, not as a gap

Kalshi publishes bids only; asks are derived — `yes_ask = 1000 - best_no_bid`.
So a book with **no** NO bid does not produce "no ask". It produces the
endpoint: a missing bid reads as 100c, and the derived YES ask comes back as
**0c**. The screen rendered "YES 0c" — a free contract — on the most illiquid
product the venue lists.

The order path was safe: the price grid refuses 0. But safety in the consumer is
not honesty on the screen, and CLAUDE.md rule 1 says a large apparent edge is a
bug until proven otherwise. This one was manufactured by the arithmetic itself.

**The pattern: any value computed as `limit - x` turns "x is missing" into "the
answer is the limit", and the limit is usually the most attractive number in the
range.** Subtraction has no null. Complement, remaining-capacity, time-until,
percentage-of-total: all of them convert an absent input into a confident
extreme.

The fix is to run the derived value back through the validity test its consumer
already applies — here `is_valid_price`, which refuses 0 and 1000 as settled
outcomes rather than quotes — and return None when it fails. "Unreadable
resolves to None, never 0" is the repo's rule for *reading* a field; this is the
same rule for *computing* one, and it is the harder half because the computation
succeeded.

---

## 2026-08-26 — A fixture that writes a value the wire never emits is a defect with a delayed fuse

The demo seeder wrote `status = 'open'` into `kalshi_markets`. The venue writes
`active` — 245 of 245 in the committed payload capture. `open` is the *event*
query parameter (`/events?status=open`), a confusion this repo had already
recorded once, in a different file, about a different reader.

It sat there harmlessly for months because the one query that filters on that
column had no caller. The first caller shipped and the search returned **zero
markets for every query** on the demo instance — a new feature that looked
completely broken, on data that had been wrong the whole time.

**The pattern: a fixture defect is invisible until the first reader that cares,
and the reader gets blamed.** The debugging instinct points at the new code,
which is the only thing that changed; the fixture is old, load-bearing and
trusted precisely because nothing has complained about it.

Two things follow. **A seeder is wire-format code and belongs under the same
rule as a parser** — CLAUDE.md already says wire-format tests must load captured
payloads rather than hand-constructed ones, and a seeder is a hand-constructed
payload with a longer life than any test. And when a brand-new feature reads
existing data and comes back empty, **check what the data says before checking
what the code does** — one query against the table would have cost thirty
seconds and pointed at the real defect immediately.

---

## 2026-08-26 — Bytecode caching is keyed on (mtime, size), so a same-length edit can survive its own revert

Mutation testing a coefficient: `Decimal("0.071")` → `Decimal("0.070")`, run the
test, write the original back. Same length, same second. CPython validates a
cached `.pyc` on the source's **mtime and size** — both unchanged — so the stale
bytecode carrying the mutation stayed live after the revert. The next full suite
failed against a source file that was byte-for-byte correct, and the failure
pointed at the tests rather than at the cache.

**The pattern: a revert that restores the bytes does not always restore the
behaviour.** Anything that caches on a cheap fingerprint — bytecode, a build
system's timestamps, a browser's ETag — can be fooled by an edit that changes
neither. Digits, boolean literals, comparison operators and single-character
flags are exactly the edits that keep both, and exactly the edits mutation
testing makes.

So: **clear `__pycache__` on both sides of a mutation**, not just before the
run. And more generally, when a test fails against source you have just read and
believe, check whether anything between the file and the interpreter is holding
an older copy — the fastest disambiguation is to touch the file and re-run.

---

## 2026-08-26 — A feature behind an off flag has never rendered, and the first render is part of the build

A complete hand-bet path shipped four days earlier: a route with twelve
server-side checks, a table, a full test suite, a ticket component with an
anti-anchoring reveal. `MANUAL_ORDERS_ENABLED=false` meant every response on the
live instance was "blocked", so **not one of its screens had ever drawn against
a real quote, a real book or a real balance.**

Driving it once — seeded database, real backend, real browser, real venue read —
found two defects the suite could not: a derived ask rendering as 0c on an empty
book (above), and a seeder status the venue never emits (above). Both are in
code that was green.

**The pattern: tests pin the shapes you thought of, and the first real render
is where the shapes you did not think of arrive.** This repo already records
"a feature and the one path that invokes it are two deliverables, and only the
second one ships". The sharper version: **the invoking path is not shipped when
it is written, it is shipped when it has been watched running**, and a flag that
routes every response to a refusal is indistinguishable from a feature that
works right up until the flag moves.

Cheap corollary that paid twice here: when the flag is the only thing between a
built feature and its first render, **turn the flag on before believing
anything** — including "it is finished".

---

## 2026-08-26 — A guard installed by an unverified edit is not installed

I wrote a patch script whose every substitution went through one helper that
asserts its anchor exists — precisely so it would fail loudly rather than
half-apply. Then I wanted a dry run, so I added a `DRY_RUN` flag to that script
**with a `str.replace` of my own**, outside the helper. The replacement matched
nothing. `str.replace` returns the string unchanged and says nothing about it.

So `DRY_RUN=1` printed "patched" for every file and wrote all seven of them for
real, into a tree with the full test suite thirty-five minutes into a run that
existed to re-measure the baseline. The measurement was void and the tree was
half-applied.

**The pattern: a no-op edit is silent, so every anchor-based edit needs a count
assertion — including the ones that install the safety.** The care I had taken
was real and it was applied to the payload only; the scaffolding around it got
none, because scaffolding does not feel like the thing that can be wrong.

Two sharper halves worth keeping.

**A dry run must be observable, not asserted.** The only trustworthy evidence
that a dry run did nothing is that nothing changed — `git status` before and
after, not a flag being read and a message being printed. A mode that reports
itself is reporting the branch it took, and the branch it took is exactly what
was in doubt.

**And this is the repo's own rule one layer out.** "Every guard is verified by
disabling it and watching the test fail" is about product guards; the same
sentence applies to a guard in a throwaway script, and a throwaway script is
where nobody applies it. If the guard had been mutated once — run `DRY_RUN=1`
on a scratch copy and check the file was untouched — the missing branch would
have shown up in two seconds instead of costing a thirty-five-minute
measurement.


---

# The pattern index

Every lesson ever written, newest date first, one line each. The full text of
each is in the linked archive file, unchanged; the sections marked *in this
file, above* are the ones not yet archived.

**Regenerated again 2026-08-31, and the same way for the same reason.** The
newest section here was 2026-08-26 listing eight lines, while the file above it
held **64** unarchived lessons across six dates -- so "every lesson ever
written" was false of its own file for the second time, and a session scanning
for something relevant would have missed everything written in the last five
days. **An index that is not regenerated in the same edit as the entry is stale
by one entry immediately and by dozens within a week.** Regenerate it from the
headings rather than appending by hand; the headings are the source.

**Regenerated 2026-08-26.** This index had listed the five entries of
2026-08-17 as "in this file, above" and stopped there, while 61 later lessons
sat unindexed above it — so the line "every lesson ever written" was false of
its own file, and a session scanning the index for something relevant would
have missed every lesson written in the last nine days. The titles below are
the lessons' own headings, taken verbatim; keep it that way, so regenerating it
is a script and not a judgement.

### 2026-09-02 — in this file, above
- When a single look is registered, the look that counts is the FIRST one past the stopping rule
- A retention cap on a diagnostic file is a deletion of whatever measurement reads its oldest lines
- Before ranking work on a screen, read the instrument that says whether anyone is looking at it
- A doctrine comment is a claim about the tree; grep before citing it

### 2026-09-01 — in this file, above
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

### 2026-08-31 — in this file, above
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

### 2026-08-30 — in this file, above
- Split a before/after on evidence of the change, never on when you think you made it
- A test double that is kinder than the real object hides the bug it exists to catch
- When two code paths can produce the same end state, an assertion on the state guards neither
- Check the REGRESSOR moved before you read the outcome; a constant explains nothing
- An instrument sampled at pass START repeats itself when a pass fails, and the repeat is the signal
- When you change a cadence, re-read every predicate that compares against a timestamp it produces
- A test that names a symbol is not a guard on that symbol
- A failure recorder that shares the failing resource records exactly the failures that don't matter

### 2026-08-29 — in this file, above
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

### 2026-08-28 — in this file, above
- A pre-registration must fix its scope conditions before it enumerates causes
- "Unexplained one-off" is a claim about frequency, and a default window is not a population
- A helper called from a loop that must not die does not get to trust its caller
- Sharing a predicate guarantees agreement only about what the predicate decides
- A guard that matches a literal string certifies the string, not the property
- A guard can check the right token in the wrong role, and stay green for months

### 2026-08-27 — in this file, above
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

### 2026-08-26 — in this file, above
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
