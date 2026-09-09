# Archive - `tasks/lessons.md` lessons removed as duplicates, 2026-09-08

**Verbatim.** Each lesson below was moved out of `tasks/lessons.md` unchanged
on 2026-09-08 (ADR 0116) because it duplicated another lesson, an archived
lesson, or a rule already in `CLAUDE.md`. The reason precedes each one. Where
two lessons were merged, the surviving one carries a dated merge note.

---

**Removed because:** duplicate of the 2026-09-03 lesson *A binder proposed from a remembered lesson is a hypothesis* (`archive/lessons-2026-09-08.md`).

## 2026-09-06 - An item written from the shape of a known lesson is a hypothesis, not a finding

A handoff carried: *"The global stop is invisible on both surfaces — a refused
sweep writes no `api_credits` row, so exhaustion reads as an absence"*, and
recommended diagnosing it with `sweep-log` filtered on `outcome='refused'`.

Funded as a falsification before a build. **The first half was false**: the
planner's refusal string reaches `/api/window` as `last_look_detail` and
`WindowBanner` renders it verbatim, so the screen says so in words. **The
recommended instrument was the actual defect**: `REFUSED` is written only
behind `budget.refusal_reason` inside `fetch_odds`, and once the cap binds no
call is attempted at all, so the filter finds the one pass that ran out and
misses the sixteen hours that follow.

The item had been written by pattern-matching onto a real lesson this repo
already knew — the attention slice's silent-refusal-with-no-fall-through, which
took four passes to fix. The shape fitted. It *felt* confirmed rather than
proposed, and the confidence came from the resemblance rather than from a
reading of the code.

**Pattern: a diagnosis that matches a scar you already have is the one to check
hardest, not the one to trust.** Recognising the shape tells you where to look;
it is not evidence about what is there. Write such an item as a question with a
named check ("does `WindowBanner` print the budget string? read
`sweepTone.ts`"), not as a finding with a build attached — otherwise the build
gets funded on a resemblance and the real defect, one function away, stays.

---

**Removed because:** duplicate of the 2026-09-02 lesson *'Restore the guard' with `git checkout` restores the COMMIT, not your edit* (`archive/lessons-2026-09-08.md`).

## 2026-09-06 - `git checkout <file>` restores the INDEX, so it deletes uncommitted work while looking like an undo

Three files were mutated one at a time to prove a new guard could fail, and
each was "restored" afterwards with `git checkout <path>`. Two of the three
files had never been committed in that state. `git checkout` reverts to the
index, not to what was on disk a second earlier, so it silently discarded a
newly written 10KB component, a patched card and a page edit -- and reported
`Updated 1 path from the index` for each, which reads like success.

It was caught only because the final re-run of the suite came back **3 failed**
on a test that had just passed, which is the one signal that could not be
explained away. Had the mutations been of already-committed files, nothing
would have been lost and the habit would have survived to do damage later.

**Pattern: never use a VCS command to undo an edit to work the VCS has not
seen.** A mutation harness must restore from a copy it made itself --
`cp file bak` before, `cp bak file` after -- because that restores the bytes
that were actually there. The VCS restores the bytes it knows about, and the
gap between those two is precisely the work in progress.

The general form: **an undo whose source of truth is not the thing you
changed is not an undo.** Same family as reading a health endpoint that
reports a sha somebody typed.

---

**Removed because:** merged into *When a guard asserts the mechanism instead of the property* (an instance of it).

## 2026-09-06 - `assert str(CONSTANT) in text` passes just as happily on a typed digit, so it does not test that the text is sourced

`backend/parlays.py` builds a disclosure sentence from named census constants,
and its guard read `assert str(parlays.COMBO_CENSUS_OPEN) in notes["unquoted"]`.
The comment above it says why: an earlier version pinned the literal `"40 of
40"`, the census refuted that count, and the test kept the refuted sentence
green. Sourcing the assertion from the constant was the fix.

**It does not do what it says.** `str(61) in note` is true whether the note
interpolated `{COMBO_CENSUS_OPEN}` or someone typed `61` — the two produce
identical bytes, and the assertion only ever sees the bytes. Verified by
mutation: replacing `{PARLAY_CENSUS_TAKER_FILLS} of {PARLAY_CENSUS_POSITIONS}`
with a literal `51 of 52` left that test **green**. The guard that was written
to stop a hardcoded number cannot see a hardcoded number.

The check that works reads the *source* rather than the output: parse the
module, find the f-string, and assert it contains no bare digit at all. That
distinguishes the two spellings because the difference exists only before
interpolation.

**The pattern: when a guard exists to constrain how a value was PRODUCED, it
must read the producer.** Any assertion on the product sees only the value, and
two productions that agree today are indistinguishable to it — which is exactly
the day the guard is asked to earn its place. Same family as the several
"asserted the mechanism, not the property" entries below, running the other
way: here the property was asserted where only the mechanism could tell them
apart.

---

**Removed because:** merged into *A mutation that stays green has two readings* (its corollary).

## 2026-09-05 - Run a new guard against the code before the fix; a green suite proves the test agrees with the fix, not that it would have caught the defect

Thirteen tests were written for a screen defect and all thirteen passed. That
established nothing on its own: a test written after a fix, by the person who
wrote the fix, tends to assert the shape of the fix. The check that mattered
took thirty seconds -- `git show HEAD:<file>` into place, run, restore -- and
**9 of the 13 failed**, which is the actual evidence. The 4 that passed were
the states already correct before the change, and knowing which 4 those are is
itself worth having: it says exactly how much of the file the new suite
defends.

**Pattern: for any guard written alongside a fix, run it against the
pre-fix code and record how many go red. A guard that passes on the broken
version is describing the implementation, not the requirement.** Mutation
testing is the same idea applied to one clause; this is it applied to the
whole change, and it is cheaper, because the "mutant" already exists in git.

The corollary about ordering: this is why writing the test first is usually
cheaper than justifying it afterwards -- but when the test comes second, the
pre-fix run is the substitute, and it is not optional.

**Removed because:** an incident (a slow fixture), not a pattern that would change a future session's judgement.

## 2026-09-05 - A test that recompiles identical bytes once per case is a tax on every future run, and the fixture that fixes it is three lines

A new file cost 34 seconds, of which roughly 30 were `tsc` compiling the same
unmodified source eleven times, once per test case. On a suite whose CI job
has a 900-second cap and currently uses 314, that is an eighth of the budget
bought for nothing. A module-scoped fixture that compiles once and hands out
the build directory took it to 12 seconds; the two cases that need a *mutated*
source still get their own build, which is the only variation that ever
existed.

**Pattern: when a test's setup is a pure function of files that do not change
between cases, it belongs in a fixture scoped to the widest thing that is
still constant -- and the time to notice is before the file lands, because
afterwards it is someone else's mystery slowdown.** This repo has already paid
for the lesson once, with a test spending 71 seconds on a 200,000-sample
copula to assert a dictionary length. Read `--durations` on any new file that
shells out.

**Removed because:** merged into *A guard that substring-matches an element name is green on a renamed element* (same defect, one day apart).

## 2026-09-05 - A guard that greps for a component name finds the comment explaining the component, and a prefix is a substring of every longer identifier

One pin — "this file still mounts the hand-bet ticket" — was written as
`"<ManualTicket" in source` and observed **green twice under mutations that
should have killed it**, for two unrelated reasons.

The first: renaming the mount to `<ManualTicketXX` leaves `<ManualTicket` in
the file as a prefix, so a substring test cannot see a component being
replaced by a differently-named one. The second is the more interesting, and
was only reached after fixing the first: the file's own comments name
`<ManualTicket` while explaining *why* the link sits beside it, so the guard
was reading prose about the mount rather than the mount. Both fixes are one
line — match an element boundary (`<Name[\s/>]`), and strip comments before
searching — and neither would have been found by reading the test.

**Pattern: a source-text guard must assert on the code with comments removed,
and must anchor identifiers at their boundaries. Documentation is the most
likely place for a guard's own needle to appear, because good code explains
the thing the guard is checking, in the same words.** The corollary is about
process rather than regex: the second failure was invisible until the first
was fixed, so **a mutation that goes green is not one finding, it is a
prompt to mutate again** — keep mutating the same guard until it goes red for
the reason you intended.

Two related shapes seen the same day, both worth recognising:

- **A mutation applied by `.replace(needle, repl, 1)` can land on a comment**
  rather than on the code, because the comment usually comes first. The
  mutation then "applies" (the text changed, the assertion that it changed
  passes) and proves nothing. Target the mutation at the syntax, including
  its indentation, not at the bare name.
- **A guard on the unbuilt state must be rewritten in the commit that builds
  it.** Two pins asserted that a comment said "conditional" and that a prop
  was passed bare -- both descriptions of work not yet done. Fixing the defect
  made the suite assert the defect. This is the same ordering lesson the
  window-copy fix recorded: copy that names a condition to wait for is
  falsified by fixing the condition, so the fix and its pins ship together.

**Removed because:** merged into *A deadness grep scoped to the source directories misses the callers that matter most* (same audit, same conclusion).

## 2026-09-05 - A "has a caller" check is only as deep as its walk, and a one-level walk is satisfied by a referrer that is itself dead

`skeptic.apply_verdict` sat on `MUST_HAVE_CALLERS` with a consequence string
naming "a safety layer that can block nothing", and passed all three caller
tests for fifteen days while nothing on the live machine could reach it. Its
one production referrer was `review._amend`, called only by
`review_surfaced`, which nothing had named since ADR 0062 put
`review_retired` on the pass default. The import closure did not catch it
either: `review.py` was imported for the retired reviewer, so the module was
reachable and the function inside it was not. Named, import-reachable, and
called are three different properties, and the guard measured the first two.

**Pattern: state a guard's depth in its own docstring, and when a symbol's
consequence string describes the exact failure the guard cannot see, that is
the moment to add the next level — here, a walk from the deployed entry
points to the symbol — not a comment. A guard whose blind spot is written
beside it and not tested for is decoration with a warning label. The
corollary for deletions: a module can be import-reachable and dead, so
"nothing imports it" is a sufficient reason to delete and never a necessary
one.**

---

