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

So: three counters in this repo name a global state and can each be allocated
twice — `SCHEMA_VERSION`, the ADR ordinal, and any migration step number. Read
`main` before taking one, every time, and write down which you took.

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

## 2026-08-25 — A monitor that names a cause it cannot observe sends you to one place

The off-box heartbeat alarmed: *"the recording loop has not written a quote for
35 minutes. **It is alive and stuck**, which is the state that keeps every check
green while the record stops accumulating."* Every number in that sentence was
measured. The clause in bold was not measured by anything — the check reads one
field, `recorder.age_ms`, and at least three states produce a large one: a
wedged pass, a run of passes failing before the heartbeat write, and a container
that restarted without the record catching up.

The alarm had been written while thinking about one of those, and it named it.
So the first thing anyone reading it does is go looking for a wedge.

**The pattern: a monitor may report the thing it measured and the states
consistent with it, and must not pick one.** The test is mechanical — for every
noun in the alert text, ask which field it was read from. If there is no field,
it is a hypothesis wearing a measurement's clothes. This is the same failure as
*a refusal that names its own predicate describes a symptom, not a cause*, one
layer out: there the component knew too little and said it precisely; here the
monitor knew too little and said more than it knew.

**The half worth carrying is what made it undiagnosable.** The gap was real —
2,678 seconds where the widest healthy gap that day was 1,001s against a
1,035s ceiling — and *which* of the three it was could not be established
afterwards, because the only record of why a pass stops was
`LoopState.consecutive_failures` in memory, and the container had restarted and
taken its logs with it. **Ask of any in-memory diagnostic: does this survive the
event it exists to explain?** A counter that dies with the process cannot
explain a process dying, and that is precisely when it is wanted.

What separates the states is an asymmetric record: `loop_failures` is written on
the failure path **only**. Rows inside a silence mean the loop was failing; no
rows mean nothing came back to raise. Had it also logged successes, "no rows"
would have meant nothing again — **the silence is the signal, so do not fill
it in.**

## 2026-08-25 — Dedupe is not a rate limit, and the difference is who supplies the churn

Parlay cards push to Discord keyed on `card_key` + sorted leg tickers, so a card
whose legs have not moved is dropped by `UNIQUE (kind, key)`. That is correct
change-detection and I reasoned from it that the push was self-limiting: no
change, no message.

It is not, and the reason was upstream of everything I was looking at.
Legs are filtered on `odds_age_now_ms <= max_odds_age_ms`, and **odds are swept
per sport on independent clocks**. So a sport's legs enter the pool when it is
swept and leave it when they cross 900s — and because ranking is by probability,
whichever sport is currently fresh takes the top slots. Measured on live: the
`safe` card was three MLB legs at 22:41:43Z and three WNBA legs at 22:45:10Z.
The **entire composition swapped sport in under four minutes**, and every push
was correct by the dedupe rule. (Kickoffs churn it too — `ladder_candidates`
takes pre-game fixtures only — but that is the slow half.)

**The pattern: deduplication bounds repetition, never volume.** It answers "have
I said this before?" and is silent on "how often does the world hand me
something new to say?" Whenever a dedupe key is doing the work of a ceiling, go
and find what makes the key turn over, and count it — the answer is a property
of the upstream data, not of the notifier. Here the turnover rate was the
fixture list, one file away and never asked.

The generalisation past notifications: **a cache key, an idempotency key and a
dedupe key all collapse identical work and none of them bounds distinct work.**
If the cost of the distinct case matters — a phone buzzing, a credit spent, a
copula run — the ceiling is a separate mechanism and has to be built as one.

## 2026-08-25 — A total is not a breakdown, and two spot checks cannot see a flip-flop

I claimed three different things about one number moving 118 → 121, and the
first two were wrong.

**First**: "the cards are re-pushing" — from `total_ever`, which counts *every*
notification kind. A total can tell you something moved and never which thing.

**Second**, after checking: "so it must be another kind" — reasoned from a
comparison of two `/api/parlays` pulls 26 minutes apart whose dedupe keys were
byte-identical. Therefore stable, therefore not the cards.

**Measured**: it *was* the cards, and their keys had changed completely — MLB at
22:41, WNBA at 22:45. My two pulls sat either side of a flip and back, and both
happened to land on WNBA.

Two patterns, and the second is the sharper one.

**A total cannot answer a question about composition.** The fix was one query
grouping by kind, which existed nowhere because `/api/health` had always been
enough for "is anything happening". The moment the question became "which
thing", the instrument was the wrong shape — and the wrong shape still returns
a number, which is what makes it dangerous.

**Sampling a value at two arbitrary times measures the endpoints, not the
path.** A quantity that oscillates reads as constant whenever your samples land
in the same phase, and nothing about the reading says so. For anything that can
change and change back, the evidence has to be the *event log* — every
transition, timestamped — not a before and an after. I had that log
(`notifications` carries a row per send) and used a spot check instead because
it was quicker to reach for.

## 2026-08-25 — Measure the cost of a thing you put on the fast path, before it is on the fast path

I moved the parlay-ladder build into the recording loop and argued it was free:
pure function, no network, no credit, and the dedupe drops the result anyway.
Three true statements, and the conclusion did not follow. `build_ladder` runs a
**200,000-sample Monte-Carlo copula per card, five times over** — the headline
plus one per devig method. Fifteen runs for three cards, ~400ms measured, on a
loop whose quote pass is budgeted 8s so a Kalshi quote can stay under 30s.

Two things worth keeping. **"Pure" is a statement about effects, not about
cost** — and the words that make something safe to call anywhere (no I/O, no
mutation, deterministic) are exactly the words that stop anyone asking what it
costs to call it. **And it would have degraded silently**:
`Tempo.observe_pass_duration` *warns* on an overrun rather than failing, so no
test would have gone red and the symptom would have been rows quietly expiring.

The fix was not optimisation. The ladder is a pure function of stored odds, so
between sweeps it rebuilds byte-identically — the 400ms was buying a
notification the dedupe then discarded. **When work on a fast path is expensive,
ask first what input it actually depends on and gate on that changing**; the
answer is usually a much slower clock than the loop's.

## 2026-08-25 — A gap the length of your own timer is a timer, not a fault

The live loop went silent for 15m34s and I wrote it up as a wedge: "the
recording loop stalled", in the commit message and in NEXT.md. Every figure I
quoted was correct. The mechanism was invented.

Two facts already in hand said so and I had not asked either of them. The pass
before the gap logged **`pass 130 ok`** — a hang does not log its own
completion. And the gap was **934s against a 900s slow interval with ±15%
jitter**: 900 × 1.038, dead centre of the band. The loop had simply observed the
window shut, taken its slow cadence, and slept.

The pattern: **before calling a silence a fault, divide it by every interval the
system sleeps on.** A duration that lands inside one of them is that timer until
proven otherwise, and the proof is cheap — the constant is in the source. This
generalises past loops: retry backoffs, cache TTLs, cron periods, connection
keepalives. Any of them produces a gap that looks exactly like a hang from the
outside, and each has a number you can check in seconds.

What made the wrong story sticky is worth naming, because it will recur: **the
symptom and the invented mechanism agreed perfectly.** A stalled loop and a
sleeping loop produce the identical observable — no writes, no logs, a stale
desk. Agreement between a symptom and a hypothesis is not evidence for the
hypothesis when a second hypothesis predicts the same symptom. The question that
separates them is never "does this fit" but "what would differ if it were the
other one" — here, one log line and one arithmetic check.

And the real defect was adjacent to the invented one and more interesting:
**a trigger evaluated inside a pass cannot fire while the loop is between
passes.** `decide_sweeps` asked "is anyone looking" correctly on every pass; the
signal was written by a different process into a table the sleeping loop never
read. A component can follow a signal faithfully and still be unreachable for
the length of its caller's sleep. When a design says "X now follows Y", check
what X's *scheduler* does with Y, not just what X does.

## 2026-08-25 — A refusal that names its own predicate describes a symptom, not a cause

The parlay desk said `needs 2 fresh games and the slate has 0`. Every word was
true. It is also what the screen says when twenty games are on, sixty-five sides
are matched, and the loop that would re-buy the prices is fifteen minutes into
a sleep nothing can wake — which is what was actually happening. The owner read it as "there is nothing on
tonight" and asked why the desk was empty.

The pattern: **a component that refuses correctly reports the predicate it
evaluated, and the predicate is always the last link in the chain.**
`build_ladder` counts *fresh* legs, so its refusal can only ever talk about
freshness; it cannot see that the fixtures exist, that the odds are 26 minutes
old, or that nothing is running to re-buy them. Each layer names its own input
and none of them names the fault. The result reads as a statement about the
world when it is a statement about one filter.

So: **a refusal is complete only when the screen also carries the state one
level up from the predicate.** Not inside the refusing function — it genuinely
does not know — but beside it, from whatever already publishes that state. Here
`/api/window` had every missing number the whole time (`fixtures_upcoming`,
`fixtures_fresh`, `last_sweep_ms`, `last_look_ms`) and the page simply never
asked for it.

The corollary, and it is the sharper half: **a promise about the future is only
as good as the thing that has to keep it.** `readNextWindow`'s `due_now` said a
buy was due and "the runner's next pass serves it, usually within a minute" —
computed from `next_sweep_ms <= now_ms`, which was true throughout the stall.
The screen was reasoning about *what was wanted* and speaking about *what would
happen*. Any sentence that predicts an action must be conditioned on the actor
still being alive, and there is usually a heartbeat field already on the wire to
condition it with.

## 2026-08-25 — The only thing left in a quiet log is not the thing that quietened it

The live loop stopped logging at 16:22:41Z. The log from that point on was
nothing but `New SSH session` lines, one every ten to twenty seconds, from a
polling watcher I had started. I read that and announced **"I caused this"** —
confidently, in those words, before checking a timestamp.

The watcher's first session was **16:28:32Z, six minutes after the loop went
quiet.** It could not have been the cause. The SSH lines dominated the log
because the loop had already gone silent and the loop is what writes everything
else; I had mistaken *what remained* for *what was responsible*. The actual
answer was that the odds had aged past `MAX_ODDS_AGE_S`, the window had closed,
the 15-second quote cadence had stopped by design, and the loop was idling on
its 900-second cadence. It woke on schedule.

**The pattern:** when a log goes quiet, whatever still appears in it becomes
100% of the visible traffic, and that share is an artefact of the silence rather
than evidence about it. Before blaming the survivor, get the two timestamps —
when the silence started, and when the suspect started — and check the order. It
costs one `grep`. Corollary for this repo specifically: a quiet log plus a
climbing `recorder.age_ms` is the documented outage signature, and it is also
what healthy idle looks like on the slow cadence. `/api/window`'s `is_open`
separates them in one read, and `run_loop.py`'s own docstring explains why.

**The louder half is the announcement.** This is the third time in one session
I have stated a cause before verifying it — sibling of *an access-control
finding names the layer it was read at*, which has the same remedy and which I
had written up that morning. Knowing the rule is not the same as pausing to
apply it. The tell is the feeling of having *found it*: a diagnosis that arrives
complete, with a culprit already attached, has usually skipped the step where it
could have been wrong.

---

## 2026-08-25 — Fixing a lie can move it rather than remove it

`_SERVED_SWEEP` counted a failed odds call as a served sweep, so a 401 moved the
sport's last-sweep stamp and the screen showed the odds as freshly bought. The
fix was right and it was not the end: with `last_sweep_ms` no longer advancing,
a failed look fell past `sweepTone`'s `refused` clause and — on a morning before
the first window opened — reached its final `return "calm"`. The strip would
have been quiet through a live outage, which is the exact 17-hour shape that
strip was built for, reached by a new route the same commit opened.

**The pattern:** a downstream consumer's correctness may depend on the bug. When
a value stops being written the way it was, ask what read it *because* of the
old behaviour — not just what read it. The tell here was that the fix removed a
signal (`last_sweep_ms` advancing) rather than correcting one, and anything
downstream that treated the presence of that signal as reassurance now gets
silence instead. Silence and reassurance are the same colour on a screen.

Both halves belong in one change. Shipping the backend fix alone would have
traded a lying clock for a quiet one and looked like progress in the diff.

---

## 2026-08-25 — A test fixture that spends is also a fixture that paces

The attention sub-ceiling's tests insert `api_credits` rows to exhaust the daily
slice. Those rows are real `/odds` rows, so they also satisfy `_SERVED_SWEEP` —
written at `NOW`, they made the sport *freshly swept*, and every assertion in the
class passed or failed because of pacing rather than because of the cap. The
suite was green on the ones that expected a refusal, for the wrong reason
entirely.

**The pattern:** when a fixture writes to a table more than one predicate reads,
it sets up more than one condition, and only one of them is the one under test.
Ask what *else* queries this table before choosing the timestamps. The tell is a
test that passes immediately on a code path that was never exercised — here, the
refusal branch was unreachable because the trigger never wanted the sweep in the
first place. Backdating the rows past both cadences separated the two.

Sibling of *a pooled number is not a finding until the parts agree*, one level
down: the fixture had two effects and only the intended one was being read.

---

## 2026-08-25 — A registered rule implemented as an optional parameter is not implemented

The CLV registration says in two places that when the record carries more than
one `strategy_config_version`, the primary analysis runs on the modal version
alone and `G` counts only those games. The code had it:
`build_report(rows, modal_config_only=False)`, a working branch with a test.
**No production caller passed it.** `GET /api/signal` took the default, and on
2026-08-24 the screen declared `NO SIGNAL` at `G = 311` when the registered
primary was `UNRESOLVED` at `G = 216` — 84 clusters below the floor, not 11
over it.

**The pattern:** a rule that offers no choice must not be expressed as a
parameter that offers one. A flag is a claim that the caller has information the
callee lacks; a registered rule is exactly the case where the caller has none,
because the rule was fixed before the caller existed. Wherever a `.md` under
`docs/measurements` says *must* and a function signature says `bool = False`,
the default is the deployed behaviour and the rule is decoration. Push it into
the callee and delete the parameter.

**Why the flag survived nine days of looking right.** It was *correct* at every
interim look, and the 2026-08-16 write-up says so out loud — the rule "was
**not** applied to the numbers above", run instead as a sensitivity, which is
permissible when nothing is being declared. A rule that only binds on the
declaring branch is invisible until the declaring branch fires, and the
declaring branch fires **once**. So the tell is not "is this wrong today" but
*"which branch has never executed, and what does it read?"* — the sibling of
2026-08-24's *a pin verifies the shape you saw, not the branch you rely on*, one
level up: there the unexercised branch was a wire format, here it was a
governance rule.

**And the same look carried the answer to whether it mattered.** `G` on the two
populations was `311` and `216`, on either side of the floor, printed in the
same run by the same harness — one flag apart. When a parameter changes which
side of a threshold you land on, it is not a parameter.

---

## 2026-08-25 — `G` is not evidence; leverage is

The declaring look reported `G = 311` clusters against a registered floor of
300, which reads as a comfortable sample. Effective clusters by inverse
Herfindahl on regression leverage: **4.26**. Two games carried half the slope,
one WNBA game carried 43.8% on its own, and 13.5% of rows carried 93.9% of the
estimate. Those rows had `edge_tenths` from **−718 to +373** — a consensus
calling fair ≈ 8c against an 82c ask, off fewer than two books.

**The pattern:** a cluster count is a count of *rows grouped*, not of
independent evidence, and for any least-squares estimate the honest denominator
is the leverage distribution — `sum(x_tilde^2)` per group, `x_tilde` being the
regressor residualised on the controls. Compute it and report the largest
share **on the same line as the estimate**. `G` and effective-`G` differ by two
orders of magnitude here, and nothing in the pipeline would have said so.

**The second half, which is the expensive one:** those extreme rows also
inflated `sd(edge_tenths)` from **10.90 to 40.98**, and since the minimum
detectable effect scales as `sigma_eps / (sigma_x * sqrt(G))`, they made the
test look four times more powerful than it is — MDE 0.078 against the
registration's predicted 0.42. **A power check that comes in far better than
pre-registered is a symptom, not a windfall.** The direction is the tell: an
assumption beaten by 4× on the regressor's own spread means the regressor
acquired mass the design never contemplated, and here that mass is what rule 1
calls a bug until proven otherwise. Read `sd(x)` against what was assumed
before believing the MDE, and if the regressor got wider, ask what got in.

---

## 2026-08-24 — An access-control finding names the layer it was read at

A subagent auditing the API reported `/api/ledger`, `/api/bets` and
`/api/results` as unauthenticated: it grepped for the `require_auth`
dependency, found none on those three, and concluded a stranger could read
the operator's whole betting record and bankroll. That was relayed to Joe as
a live privacy leak, with urgency, **before anyone checked**. It was false.
The gate is one layer up — `uvicorn` binds loopback and is never published,
`/api/*` is reachable only through Next's rewrite, and
`frontend/src/middleware.ts` runs *before* rewrites. Five unauthenticated
requests to the deployed URL settled it in one command: health 200, the
other four 401.

**The pattern:** authentication is a property of the whole request path, not
of the handler. Grepping a handler for its framework's auth dependency
answers "does *this framework's* dependency system gate this function" —
a far narrower question than "can a stranger read this", and the two come
apart the moment a gate lives in a proxy, a middleware, a network boundary
or a reverse proxy's config. So an access-control claim must state the layer
it was measured at, and a claim about the *deployed* system has exactly one
honest instrument: an unauthenticated request to the public hostname. That
costs seconds and source-reading cannot substitute for it at any length.

Two tells, both present here and both missed. First, **the code documented
its own posture and the finding did not mention it** — three route
docstrings (`routes.py:2285-2291`, `:2377-2382`, `:2414-2418`) explain the
middleware gate at length and give the reasons; a finding that contradicts a
docstring without engaging it has usually not read it. Second, **the archive
already carried the answer**: two 2026-08-09/10 entries record these exact
routes answering 401 unauthenticated, and a cookie opening them at 200. A
security regression is possible, but "it was always like this and you never
knew" is the rarer story than "you are looking at the wrong layer."

Sibling of *verification methods that lie*: there the instrument reported
health over broken code; here it reported breakage over healthy code. Same
remedy — measure the deployed thing, not a proxy for it.

**And the relaying is its own error.** An unverified alarm passed on as
urgent spends the operator's trust at the moment it most needs to be
spendable. A finding that says "your money is exposed right now" earns a
thirty-second check *before* it is spoken, not after — the asymmetry is
severe, because a false alarm costs credibility on every true one that
follows.

---

## 2026-08-24 — A baseline taken while you edit is not a baseline

The session-start suite was launched in the background and edits began before
it finished. It came back **10 failed, 4091 passed** against a NEXT.md that
promised 4,099 — which reads exactly like inheriting a broken tree, and the
first response was to go looking for what the last session left behind. Every
one of the ten was a *source-inspection* test (`test_pass_leg_timings`,
`test_retention`, `test_unmatched_...`) reading `backend/runner.py` — the file
being edited while they ran. Re-run afterwards, all ten passed. The eight
minutes saved by backgrounding cost more than that in a false diagnosis, and
`git stash` to check nearly lost the session's work.

**The pattern:** a test run measures the tree *as of each moment it reads a
file*, not as of when it started, so a long run overlapping edits produces
failures belonging to no commit that ever existed. Either let a baseline
finish before touching anything, or take it against a clean checkout. The tell
is a failure set clustered in tests that read source text rather than exercise
behaviour — those are the ones an editor can break mid-flight. Sibling of
"verification methods that lie": here the *instrument* was fine and the thing
it measured moved underneath it.

---

## 2026-08-24 — A pin verifies the shape you saw, not the branch you rely on

`price_card_on_kalshi`'s create POST had one captured payload — a brand-new
combination — and the desk's designed flow depends on the *other* branch: a
fresh combo's book is empty, the screen says "try again shortly", so the
second tap asks Kalshi about a combination that already exists. Nothing here
had ever observed that answer, and the two possibilities needed opposite code
(idempotent → retry freely; 409 → the market is permanently unpriceable and
each retry burns the weekly creation budget). A review caught it as PLAUSIBLE
*because a retry control was about to ship on top of it*. Measured: 200 with
the same `market_ticker`.

**The pattern:** when a feature's expected-first-answer routes users into a
branch, that branch is not an edge case and a fixture of the happy path does
not cover it. Ask which call the *design* makes second, and check whether
anything has ever seen its response. Descendant of 2026-08-23's
never-exercised-path lesson, one level in: there the endpoint had never been
called at all; here it had, but only down the arm nobody actually walks.

---

## 2026-08-23 — A wire format that was pinned but never exercised is a belief wearing a pin

`combos.lookup_combo` carried `POST .../{ticker}/lookup` since 2026-08-07,
with the path pinned in code and recorded in ADR 0012 — and the one
authorization to actually call it was never spent. The first real call, a
year of API churn later, returned a bare routing 404: Kalshi had deprecated
and removed the endpoint, and nothing in this repo could have noticed,
because a pin verifies that *we* still spell it the way we spelled it, not
that the counterparty still serves it. **The pattern:** a fixture or pin
earns trust only downstream of a captured exchange; for a call that has
never been made, the pin documents a plan, and the first live call is part
of the build, not an optional smoke. Sibling of "verification methods that
lie" — this is the never-exercised-path case.

---

## 2026-08-23 — A pinned fixture clock against a wall-clock instrument is a test with an expiry date

`test_prune_frontier_query.py` froze `NOW_MS = 2026-08-20T13:20Z` — with a
comment claiming the fixed value stopped the fixtures "drifting with the wall
clock" — while the query under test deliberately stamps its own
`datetime.now()`. Three days later five tests went red with no code change:
every seeded row had aged past the real cutoff. The comment had it exactly
backwards: when the code under test reads the wall clock, a *frozen* fixture
clock is the drift, and the fixtures must be seeded relative to the same
clock the code reads (or the code must accept its moment as a parameter).
**The pattern:** before pinning a test's "now", find where the code under
test gets its own — if they are different clocks, the test is green only
inside an expiry window, and it fails later on someone else's unrelated
diff. Sibling of "a stored number answers the question it was stored for";
this is the test-fixture case.

---

## 2026-08-23 — "The screen shows X" must come from the screen, not from the database that feeds it

Audited today: no session had ever read any live HTTP route except
`/api/health` — `curl` is not in the runtime image and the middleware 401s
everything else publicly. Every handoff sentence of the form "the slate
renders N rows" was therefore a *reconstruction* from the database plus a
mental model of the rendering code, stated in the grammar of an observation.
The reconstruction can be wrong everywhere the model is (serialisation,
staleness computed at read time, a route-level filter), and nothing in the
sentence marks which kind of claim it is. **The pattern:** when a claim is
about a served payload, verify it on the served payload; if the instrument to
do that does not exist, building it *is* the verification work, and until
then the sentence must say "the table holds X" rather than "the screen shows
X". Same family as "verification methods that lie" — this is the
whole-surface case. Fixed with `scripts/fetch_live_route.py` (GET-only,
allowlisted, loopback-hardcoded).

---

## 2026-08-21 — A field written after the spend is not a spend gate

`fly.live.toml` cited `surfaced == 0` as the reason the Anthropic bill was
zero. The live `agent_calls` table showed 24 metered Opus calls on 2026-08-16
— the whole daily cap in 4m22s — after which `surfaced` *still* read 0,
because the Skeptic blocked every row it billed for. The zero everyone read
as "no spend possible" was produced *by* the spend.

**The pattern:** if the guard's reassuring value is computed by the thing you
are paying for, it is a receipt, not a brake. A spend gate must be evaluated
before the money leaves — a config value, a budget check, a count of calls —
never a post-hoc field of the work product. This is the money-shaped case of
"verification methods that lie": the check reported safety because the
dangerous thing had already run and cleaned up after itself. ADR 0062 §3.

---

## 2026-08-21 — When a rule and its floor are defined over different units, the smaller unit's zero-information observations vote

The H4 span design (Amendment 1, A12.2) made every adjacent balance-snapshot
pair an observation, while the voting floor (A9.2) was defined over clusters
— and between the looks the record accrues roughly 4,000 adjacent pairs with
nothing in them (no settlement, prediction 0, delta 0). Read literally, those
empty pairs entered the voting population, so a floor meant to demand two
independent confirmations could have been met by arithmetic noise, and the
registration could have handed back a flattering terminal verdict from
nothing. Caught before any data was pulled; closed by dated amendment
(only spans containing a settlement become clusters and vote). The pattern:
whenever an aggregate rule is stated over one unit and its threshold over
another, enumerate what the denominator is actually made of — and ask
whether a row can satisfy the rule while carrying no information. Same
fortnight as the two-limits-on-one-quantity lesson; unit mismatch is the
sibling failure.

---

## 2026-08-20 — A stored number answers the question it was stored for, not the question you are asking now

Two triage calls in one session went wrong the same way: a betting slate was
counted from a captured artifact (which answers "what was captured", not
"what exists today" — the day happened to be the thinnest slate in the
14-day record), and a disk item was ranked on ADR 0054's growth numbers,
which were three fixes stale. Neither number was wrong when written; both
were wrong when reused. The pattern: before a stored number carries a
decision, ask what question it answered when it was taken and whether
anything between then and now could have changed the answer — and if the
current value is cheap to take (a schedule endpoint, a `df`), take it
instead of remembering it. Same family as "every number taken from a
degraded system describes the degradation"; this is the time-axis version.

---

## 2026-08-20 — Log redaction does not reach exceptions: raise_for_status prints the URL, key and all

`configure_logging()` exists precisely because the Odds API key rides in the
query string, and it was in place when a stale key 401'd the registered
spread sweep — and the key still landed in the transcript, because
`httpx.raise_for_status()` embeds the full request URL in its exception
message and a traceback goes to the terminal through a channel no logging
filter touches. The pattern: redaction applied at the logging layer only
covers the logging layer; every path that can carry a request URL to a
human — exception messages, tracebacks, assertion reprs — needs the secret
kept out of the URL (headers, not query params) or the error rebuilt
without it. When a vendor forces the key into the URL, no call to that
vendor may use raise_for_status or let its exceptions escape unredacted.

**Corrected 2026-08-20, second half of the day: the detection rule above
was itself wrong.** The sweep this lesson demanded, done by grepping for
`raise_for_status`, would have found nothing and declared victory — the
one vulnerable file (`scripts/probe_prop_dispersion.py`, since fixed)
contained no `raise_for_status` at all. The defect is *a query-param
credential reaching any escaping exception*, whatever raises it; so the
grep is for the credential entering `params=`/the URL (`apiKey`), and the
audit question at each hit is "can any exception leave this call site
carrying the URL?" — not "does it call raise_for_status". Sweep taken:
`backend/odds/client.py` was already correct, the probe script is fixed,
no other hit remains.

## 2026-08-20 — A claim about git state is verified with git, never asserted from prose

A test shipped with a docstring stating its data file was "tracked in git
despite living under the gitignored data/". It never was — the force-add
never happened, `git ls-files data/` was empty — so the suite passed only
on the one machine holding the file and CI was red from the moment it
landed. This is the second silent-git-no-op incident (the first: `git add
tasks/next.md` matching nothing); the family trait is that git's failure
mode for "the thing you meant didn't happen" is often *no output and exit
0*, so the follow-up check has to be affirmative: after any add/force-add,
`git ls-files <path>` must SHOW the file before any sentence claims it is
tracked. A docstring is where such a claim goes to stop being checked.

## 2026-08-20 — Two readers can share a word and not a definition, and the disagreement will be filed as a stale value

The cadence dropouts were handed off as a stale-flag bug because the pass log
said "window is open" while the sleep branch behaved as if it were closed.
Both readings were current and correct: the log line was the *slot* view
(kickoff arithmetic plus a recent sweep) and the flag was the *freshness*
view (oldest book stamp against the 900s limit) — one word, two quantities.
The previous incident in the same code genuinely was a stale flag, which is
exactly why the new one was pattern-matched to it. When a log line and a
control flag disagree, before asking WHEN each was read, ask WHAT each
measures; a vocabulary collision looks identical to a staleness bug from the
outside, and the fix for one is a no-op for the other.

## 2026-08-20 — A status that can only be stamped after an event must never be stamped by a clock alone

`estimate_match` wrote "he estimated and did not bet" the moment a 24-hour
window closed, against a candidate table whose rows exist only after
settlement. Absence of evidence was read as evidence of absence, permanently
and self-concealingly, on every market that settles slower than the window.
The pattern: before stamping any negative ("no X happened"), name the event
that would have MADE the evidence visible and require proof that the event
has occurred — here, the market's result being known AND an ingestion sweep
postdating that knowledge. Until both hold, "pending" is the honest state,
however old the row. Same family as "unreadable resolves to None, never 0":
a clock is not a observation.

## 2026-08-20 — Undo walks run in reverse, and a walk that happens to work forwards is a latent bug, not a working one

The migration tests undid versions in ASCENDING order and stayed green for
eleven versions — until v14 added a column to a table v10's undo rebuilds,
and undoing the rebuild first restored a shape the newer column-drop could
not find. The inverse of an ordered apply is the reverse-ordered undo, always;
an ascending undo is correct only while no later step touches what an earlier
step rebuilds, which is a property of the current contents, not of the code.
When writing any do/undo pair, state the order as part of the contract and
test it with steps that overlap, because the non-overlapping case passes by
accident.

## 2026-08-20 — Fixing a stale-flag read at one use site does not fix the flag; every other reader is still wrong

The window-gate fix moved the PRUNE's read of `window_open` to the moment of
use, and the measurement then caught the CADENCE — a different reader of the
same end-of-pass flag — sleeping 370s and 468s inside an open window. When a
value is discovered to be stale-at-read, grep for every reader of that value
before declaring the defect fixed; patching the reader that bit costs the
next reader its own incident. The measured dropouts are the open item; the
pattern is: the fix's scope is the FLAG, not the symptom.

## 2026-08-20 — A number that explains a mystery is captured and committed the day it is seen, or it is a rumour

The k=0.035/0.070 fee split sat "unresolved: sport, series, or liquidity
tier" for six days while the answer — `fee_multiplier` on the public
`/series` endpoint, 0.5 on MLB — had been seen once in a live read nobody
committed. Ten minutes of capture script turned it into a fixture that
predicts all 11 real fills to $0.0001. When a live read explains something,
the capture IS the finding; an uncommitted observation ages into an
unverifiable claim at the speed the venue changes.

---

## 2026-08-20 — When local and CI disagree, do not ask which to trust. Ask which one matches production, because the answer can be neither

Two tests passed locally and failed in CI with no code change between the runs.
The reflex reading is "CI is flaky" or "CI's environment is wrong". Both were
wrong. So was the opposite reflex.

The tests asserted a credit cost computed as `len(markets) * len(regions)`, both
read from the environment. Local `.env` gave 6. CI, which sets nothing, gave 2.

**The deciding question was not local-versus-CI. It was: what does the deployed
instance do?** `flyctl secrets list` showed one secret and `fly.toml` set neither
variable, so live takes the defaults — cost 2. CI was accidentally right, local
was wrong, and the tests had been asserting a number **no running instance
charges**, on every machine, since they were written.

Had the disagreement been resolved by picking a side, there was a 50% chance of
pinning the fiction permanently and a 100% chance of never learning that the
committed contract (`.env.example`) and the developer's `.env` had drifted
apart.

**The move: when two environments disagree about a value, go and read the value
off the thing that actually runs before changing either one.** A third
observation settles it; two never can.

### The corollary that made this invisible for so long

`conftest.py` already carried an autouse fixture deleting `ANTHROPIC_API_KEY`,
with a docstring naming the exact principle — *a test that depends on an input
it does not supply is measuring the environment*. The principle was written
down, understood, and applied to precisely one variable.

**A fixture that neutralises one ambient input is evidence about that input and
nothing else.** It reads, at a glance, as though the whole class is handled. When
you find such a guard, the useful question is not "is this correct?" but "what
else reaches the code by the same route that this one does not cover?" Here the
route was `load_dotenv()` at import, and everything in `.env` came through it.

### And the reason this was worth stopping for

The failure predated the session's actual job and could have been left. It could
not: a red CI is a broken instrument. The next day's window-gate verification
would have produced a red run that nobody could distinguish from new breakage,
because the baseline was already red. **Fix the instrument before you take the
measurement, even when the instrument is not the thing you were asked to work
on.**

---

## 2026-08-20 — "One source of truth" is a claim about the *clock* as much as the source. A flag written at the end of a step and read at the start of the next is already two clocks

A prune was supposed to be skipped while a betting window was open. It ran
anyway, for 94 seconds, inside a window that had been open for eleven minutes.

The gate was present and correct-looking. The loop assigned
`tempo.window_open = window.is_open` after each pass and handed that flag to the
prune at the start of the next one. There was exactly one place the window was
computed, so it passed every "single source of truth" reading.

**It was one source sampled at the wrong time, which is indistinguishable from
two sources at a glance and behaves identically.** The value was up to 900
seconds old by the time the decision used it.

The test that was supposed to prevent this asserted
`"window_open=tempo.window_open" in source`, with a docstring warning that "a
prune reading a different clock from the cadence could prune during exactly the
minutes the cadence had sped up for." The reasoning was right and the object was
wrong: the stored flag *was* the different clock. **A guard can name the correct
hazard and then pin the thing that causes it.** When a source-text guard exists,
check that the string it pins is the property the docstring describes, not
merely the code that happened to be there when it was written.

The general form, which is what to carry: **for any cached decision input, ask
what can change between the write and the read.** If anything can, the cache is
a second clock and the "one source" property is not what protects you.

### And the second half: when a handoff names one way a gate fails, look for a second way inside the same function

The stale flag was the *reported* fault, and a fix that re-read the window at
the top of the pass would have closed it. Reading the function showed a second
route the handoff had not named: the pass fires the odds sweep and *then*
prunes, and the sweep is what opens the window. So a pass that opens a window
prunes inside the first ~40–94s of it — every time — and no pre-pass read can
see that. It was plausibly the more common of the two, because the passes that
fire sweeps are exactly the passes that prune.

**A fix aimed at the reported instance would have shipped, tested green, and
left the dominant case running.** Before fixing a gate, read the whole function
the gate sits in and ask what else changes the gated condition between the read
and the use. Fix the read *at the use*, not at the top.

### Corollary: check the loop's own noise before adding a bound to it

The sleep bound added here divides by `1 + JITTER` because the sleep is jittered
±15% downstream. Without that, a 900s bound stretches to 1035s and overshoots
the thing it was bounding by 135 seconds — the fix would have been mostly
inert, and its unit test would have passed, because the test would have measured
the bound and not the sleep. **When you bound a value that something else
perturbs later, the bound has to survive the perturbation. Test the number that
actually gets used, not the number you computed.**

---

## 2026-08-20 — A job that only runs when a gate is open looks exactly like a job that has died. Poll the thing that says it ran, not the thing it changes

A backlog drain was watched by polling its row count every ten minutes. It went
791,955 -> 651,955 -> 491,955 -> 331,955 and then **sat at 331,955 for an
hour**. Seven consecutive identical readings. Everything else on the box was
healthy — passes running, other counters climbing — which made it look like the
drain specifically had died.

It had not. The drain runs only on full passes and only while no betting window
is open, and a `basketball_wnba` window had opened. It resumed the moment the
window closed and finished in two passes.

**The row count cannot distinguish "did not run" from "ran and was skipped" from
"ran and found nothing".** Those are three different situations needing three
different responses, and the metric being watched collapsed all of them into
"the number did not change".

**The pattern: poll the record of the attempt, not the state it mutates.** The
thing that separated the three was `legacy_unmatched_pruned` on the pass line —
present-and-zero means it ran and was skipped, absent means it never ran at all.
That distinction is the same one `ALWAYS_REPORT` already exists for in this
repo, applied one level out, and it only worked because the field had been added
**before** the watch started. It had been computed and never reported, which is
this project's recurring defect and would have made the hour unreadable.

The corollary is about watch windows: **a poller whose interval is shorter than
the gate's period will spend most of its life looking at a paused system.** The
gate here has a period of hours; the poll was ten minutes. Seven of eight
readings were guaranteed uninformative before it started, and the watch expired
six minutes before the job finished. Size the window against the *gate*, not
against how often the number could in principle move — or watch the log line
instead and stop guessing.

---

## 2026-08-19 — A schema change costs its time at boot, under a health check that does not wait; and rehearse the migration before writing it

A table needed collapsing: 788,944 rows carrying 1,376 distinct work items. The
migration was designed, built, tested, and verified by breaking each of its
eleven guards. Then the cost was rehearsed against live, which took two minutes
and made all of it waste:

```
COUNT(*)  over 788,944 rows        1.6 s
GROUP BY  over the same rows     229.4 s        <- 143x
DROP TABLE (181,154 pages)       217.6 s
```

**Migrations run at boot, before the server binds.** So that step was a four-to-
eight minute startup on a platform whose health check gives seconds — and the
version stamp is written only after the step succeeds, so a machine killed
part-way re-runs it from the top. The "fix" was a crash loop on the one volume
that cannot be recreated.

**The pattern: a query's cost and a migration's cost are the same number in
different units.** Ad hoc, 229 s is a slow afternoon. At boot it is an outage,
and one that repeats. Nothing about the SQL says which it is; the *caller* does.
Ask where the statement runs before asking how long it takes, and rehearse the
expensive statement against production-sized data **before** building the thing
that contains it. Eleven verified guards on a design that cannot ship are still
eleven guards on a design that cannot ship.

The corollary is about what to do with a number you distrust. These timings came
off a box concurrently serving traffic, so they overstate a quiet boot by an
unknown factor — the same "a number from a loaded system describes the load"
trap this file records one entry above. The response was **not** to go and
re-measure on a quiet box. It was to pick a design that is O(1) at boot whether
the disk is fast or slow, so the uncertain number stops being load-bearing.
**When a measurement is uncertain and a design exists that does not depend on
it, that design is the answer to the uncertainty.**

---

## 2026-08-19 — `GROUP BY` treats NULLs as equal; a `UNIQUE` index treats them as distinct. A guard written on the all-NULL case cannot see the difference

A table was given a unique index over five columns, two of them nullable, using
`COALESCE(col, '')` so that NULLs would collide instead of inserting afresh — the
whole point of the change. A migration copied the old rows in with a matching
`GROUP BY ... COALESCE(...)`.

The mutation test for the `GROUP BY`'s `COALESCE` **stayed green**. The test
seeded 500 rows all with a NULL league and asserted one row came out, which it
did with or without the `COALESCE` — because SQL's `GROUP BY` already treats
NULLs as one group. It is only the `UNIQUE` index that treats them as distinct.
The two clauses were written to look alike and they are governed by opposite
rules.

The `COALESCE` is load-bearing only where NULL **and** `''` both occur. Then the
bare grouping emits two rows for one item, the index collapses them, and
`INSERT OR IGNORE` swallows the rejection — so the step reports success while
silently discarding the smaller group.

**Two patterns, and the second is the general one.**

- Concretely: **SQL's NULL semantics differ between `GROUP BY` and `UNIQUE`**,
  and code that restates one clause as the other is exactly where that bites.
- Generally: **a mutation test that seeds only the common case tests only the
  common case.** The guard was written from the data live actually holds
  (`league` is a name or `None`, never `''`), which is the natural thing to do
  and is why it could not fail. Seeding the case that distinguishes the two
  implementations is a different act from seeding the case that occurs.

Found only because the mutation harness was run and one of eleven came back
green. The rule "every guard is verified by disabling it and watching the test
fail" earned its place here in a single run.

---

## 2026-08-19 — Do not diagnose a resource-starved machine by consuming that resource; and a process that is *stuck* looks nothing like a process that is slow

Live was short of memory, so its memory was sampled — by opening an
`flyctl ssh console` roughly every forty-five seconds for half an hour, on a box
with **54 MB free**. Each session spawns a process. The instance's own log for
that period is mostly `New SSH session` lines, and the loop stalled a few
minutes into the densest run of it.

**The general shape: an instrument that consumes the scarce resource is part of
the experiment.** This is the same error as a heavy query on the box whose
latency is being measured — which the same session had already identified and
avoided, in SQL, before doing it again over SSH. Recognising the pattern in one
form does not transfer to the next form on its own; the question to ask is *what
does this measurement cost the thing being measured*, not *is this a query*.

**Prefer instruments the system already pays for.** The pass lines the loop
emits and `/api/health` (one keyed read) cost nothing extra and, unlike an SSH
session, produce numbers a later session can re-derive. Every figure in the
day's measurements was eventually recomputed from log lines for exactly this
reason, and they were better numbers.

**The corollary about honesty:** once the instrument is inside the experiment,
the contamination is **not separable after the fact**. The correct write-up is
the size of the doubt, not a verdict — and when picking the window to argue over
("it did not recover in the three minutes after I stopped"), pick it before
seeing which window flatters you. It recovered in four.

### The second half: `D` state is a different failure from slowness

The loop appeared dead — nothing written for seventeen minutes against a
fifteen-second cadence — and it was not. It was one pass, `took_s` **114.7** for
work that normally costs 67s, blocked in

```
state=D (disk sleep)   wchan=folio_wait_bit_common
```

**`D` is uninterruptible sleep in the kernel, and it is worth learning to read**
because it discriminates where timing cannot. It is not a lock, not the network,
and not slow code: it is the process waiting on a page. Three timing-based
theories had been argued over this incident and none of them could have
distinguished these; one `/proc` read did, instantly.

The cheap discriminators, none of which need instrumentation shipped to
production:

    /proc/<pid>/status   State:  R running, S sleeping, D uninterruptible IO
    /proc/<pid>/wchan    what the kernel is waiting on, by name
    /proc/meminfo        MemAvailable and Cached, together

**And "the process is alive" is not "the work is happening."** The machine was
up, the health check passed, and the API answered every request throughout —
because the API is a *different process*. A liveness signal that does not come
from the component doing the work will report health for a component that has
stopped. `recorder.age_ms` was the field that told the truth, and it exists
because an earlier session asked exactly this question.

---

## 2026-08-19 — A read-only handle to a WAL database reports the last checkpoint and calls it the present; and "the file stopped growing" is not "the table stopped growing"

Live row counts were read over `flyctl ssh console` with

```python
sqlite3.connect('file:/data/cockpit.db?mode=ro', uri=True)
```

and were **749 seconds stale**, on a table taking ~6,000 inserts every 25
seconds. A read-only connection cannot create the `-shm` file it needs to read
the write-ahead log, so it silently serves the last checkpoint. There is no
error, no warning, and no way to tell from the result. 51.6 MB of committed
writes were invisible.

**The general shape: a read handle that cannot see the newest writes fails by
returning an older truth, not by failing.** `mode=ro` is the safe-looking
choice, which is exactly why it gets picked for a production box, and the safety
it buys is on the write side while the cost lands on the read side. Any
read-only path to live — a replica, a snapshot, a cached view, a follower — has
this shape.

**What caught it was a constant, not a contradiction.** Two reads eleven minutes
apart returned byte-identical counts *and* an identical file size. A number that
does not move when it must move is as strong a signal as a number that is
obviously wrong, and it is much easier to miss, because "the same answer twice"
reads as confirmation. **Take the second reading in order to disagree with the
first.** If it cannot disagree, it is not a second reading.

**The check is one line and belongs beside every such query:**

```
now_ms - MAX(observed_ms)   ->   lag_s
```

Compare the newest row against the wall clock before believing any aggregate
over the table. This is the same rule as *"state when a price was observed
relative to when the outcome became known"*, applied to the reader rather than
to the data.

**And the paired trap: a flat file size is not a flat table.** The same
database was reported as 1546.4 MB across 24 minutes while its row count
climbed, because ~25% of the file is freelist being reused. A retention change
had been recorded as working on the evidence that "the DB file has stopped
growing" — which was true, and did not mean what it was read to mean. Deleted
pages go on the freelist and get refilled, so file size is bounded long after
row count stops being. **Size on disk and rows in a table answer different
questions; a claim about retention needs the one it is actually about.**

**The corollary that made it worth chasing rather than shrugging at:** the
correction moved every figure in the *unfavourable* direction — the table was
larger and the write rate higher than reported. A stale reader flatters, because
the thing being measured was smaller in the past. That is the same direction as
every other measurement error this project has caught, and it is why "the number
looked fine" is not a reason to skip the check.

The durable fix was to stop reading the database at all. Write rate, prune rate
and pass timings were all recomputed from the pass lines the loop already emits,
which have no such failure mode — and which, unlike an SSH session, are the same
numbers a future session can re-derive.

---

## 2026-08-19 — An error message names the hop it was thrown on, not the hop that is broken; and a fix is not a fix until it is measured after deploying

Live's health check flapped for days. Three sessions blamed CPU saturation from
long passes. It was two proxy hops each defaulting to a 5-second keep-alive
against a 15-second check, so the pooled connection was always dead when reused
— nothing to do with load at all.

**What ruled the standing explanation out was reconstructing *when*, not
measuring harder.** Pass start times were derived from `took_s` and the pass
line's own timestamp; two of the three failures then fell in gaps where **no
pass was running**. A theory about load has to survive the machine being idle,
and checking that cost one derivation over data already in hand. Do it before
building any instrument.

**The convenient signal pointed at the wrong component and it read as
evidence.** The app log said `Failed to proxy http://127.0.0.1:8000/api/health`.
That names the backend, so the backend's keep-alive was raised and shipped. The
next deploy still failed at exactly the same rate. The error was thrown by the
client of the failing hop, and it named *its own* upstream — which was a real
second instance of the same bug and not the one the platform was tripping on.
**An error message tells you where something was noticed, not where it lives.**
When a request crosses N hops, enumerate all N before fixing any.

**And the disproof was already in hand and pointed the other way.** The backend
answered 50 of 50 direct probes, worst case 1.6s, while IO pressure on the box
hit 90%. A component that answers every request under the load you are blaming
is not the component failing. That observation was made *before* the wrong fix
shipped, and was not weighed against it, because the error message felt more
specific than the measurement.

**The general shape: a fix is a hypothesis, and deploying it is the
experiment.** The wrong fix was tested on demo after deploying, at the deploy's
own check interval, over one reused connection — which is the only reason two
hops were ever found instead of one. Had it gone straight to live on a green
`flyctl checks list`, it would have read as fixed: a single sample against a bug
that fails every *other* request looks healthy half the time.

So: **re-run the exact measurement that exposed the bug, on the deployed
artifact, before believing it or shipping it further.** Not the platform's
green tick, not a curl that happened to succeed — the measurement that failed,
reproduced.

---

## 2026-08-19 — A performance number expires when the thing it measured grows, and a benchmark that "isolates" a cost usually removes the cost

Three attributions of one slow pass were wrong, in three consecutive sessions,
each confident and each cheap to refute. The third was mine. What they share is
worth more than any of the answers.

**A measurement of a write is a measurement of the table it wrote into.** The
inserts were timed at 0.17s and ruled out — correctly, at 279k rows. That
number was then carried forward in a handoff as a settled fact and used to
argue the writes could not be the problem. By then the table held 6.9M rows
behind a 476 MiB index and the same work cost 6.0s, then 14.0s. Nothing was
dishonest; the number simply had an expiry date that nobody wrote on it.

**So: when a measurement's subject grows, record the size it was taken at, in
the same sentence.** "Inserts cost 0.17s" is a trap. "Inserts cost 0.17s at
279k rows" invites the next reader to check whether that still holds, and takes
about four seconds to do.

**A benchmark that isolates a leg usually isolates it from the thing that makes
it slow.** I timed the store leg on the live box at 0.02s and concluded it was
free. It was 0.02s because I had pointed it at an empty database in tmpfs —
neither the real index nor the real volume. The isolation that made the
benchmark clean is exactly what removed the cost. A local run against a
same-sized table got closer (0.445s) and was still off by 13x, because it had a
fast SSD.

**The general form: before trusting a micro-benchmark, name what it does not
contain, and ask whether the answer lives there.** For a write, that list is
index size, page cache pressure and fsync — and on a 1 GiB shared box, all
three are the answer.

**Subtraction is not measurement; it inherits every error in its terms.** I
took an observed 23.6s pass, subtracted a 2.55s walk and a 0.02s store, and
concluded pricing was ~21s. Pricing was 2.8s. *Both* terms were wrong, and in
the direction that made the story coherent — which is what made it convincing.
The 23.6s was one sample taken sixteen minutes after a boot; the next was 9.7s.

**`n` before the effect size is already rule one in `CLAUDE.md`, and it catches
all three of these.** It is written there as a rule about statistics, and every
one of these failures was an engineer's timing measurement rather than a
statistic. The rule does not care about the distinction; the sessions that
skipped it did.

**What actually ended it: instrument the thing rather than reason about it.**
The pass now reports `leg_walk_ms / leg_parse_ms / leg_store_ms /
leg_price_ms`, always, including zero. It cost one small change and one deploy,
and the first pass afterwards settled in a single line what three sessions of
inference had got wrong. The tell that this was overdue was there the whole
time: three different people had needed the same number and none could read it.

**When you are about to argue about where time goes, the argument is the
signal. Log the legs and stop arguing.**

---

## 2026-08-19 — `flyctl volumes list` and `df` disagreed for three days, and the optimistic one is the one you type

The live volume filled on 2026-08-16. Three days later `flyctl volumes list`
reported the volume as **3 GB** while `df -h /data` on the machine reported the
filesystem as **2.0 G**. A previous extend had grown the volume and never grown
the filesystem, so the incident happened against a gigabyte less than anyone
believed was there — and every check that would have caught it was a check
nobody ran, because the convenient command said 3 GB.

**The pattern: a resize is two operations, and the control plane only reports
the first.** Provisioning the block device and growing the filesystem on it are
separate, and the tool that provisions is the tool that reports.

**So verify capacity from inside the machine, never from the control plane.**
`df -h /data` over `flyctl ssh console`, and do it *after* every extend rather
than trusting the success message. The extend that fixed this did take — 4.9 G
— which is exactly why the failed one was invisible: they print the same thing.

This generalises past volumes. Wherever a provisioning API and a running system
can disagree about the same quantity, the running system is the one holding the
money.
## 2026-08-19 — "I checked and it was fine" is not monitoring, and the alarm you built is not evidence until you read the channel

I spent a whole session reporting the live instance healthy. It was down 71
times out of 302 probes in one half-hour window, including **18 unbroken
minutes**. My evidence was `curl` — three or four calls, all of which happened
to land between the failures. The alarms had been firing into Discord all day
and I never looked, because the alarm I was waiting on was the *test* one I had
triggered myself.

Three things to carry:

**A handful of probes cannot see an intermittent fault, and the failure mode is
always the flattering one.** If a service is down half the time, four spot
checks miss it 6% of the time — and I ran fewer than four, spread across hours,
each one immediately after an action I wanted to have worked. When the question
is "is this reliable", the instrument has to be a *rate*: poll on a fixed
cadence, count, and report both numbers. One 200 is evidence about one moment
and nothing else.

**A monitoring channel you built is not monitoring until someone reads it.**
The heartbeat did its job perfectly from the hour it shipped. Nine real alarms
reached the phone. The gap was entirely on the reading end, and it stayed open
because I treated the channel as *delivered* once the test embed returned 204 —
proving the pipe, then never opening the other end. Check the channel's actual
contents before reporting on the health of the thing it watches.

**The platform's own verdict outranks yours.** `flyctl checks list` said
`critical` while my `curl` said 200 in 0.14s, minutes apart. Both were true.
Fly probes every 15 s with a 5 s timeout and had been watching all day; I had
not. When a platform-level check disagrees with a hand probe, the hand probe is
the one with the small sample.


## 2026-08-19 — Attribute cost by measuring the parts, because the expensive-looking part usually is not

A quote pass that should take under 15 s was taking 27, then 36, then 52, then
77. I proposed two fixes in a row, confidently, and both were aimed at the wrong
thing:

- **"It is the 7,148 inserts per pass."** Measured against the real schema and
  indexes at 279,000 rows: **0.17 s** for ~14,000 statements. Two orders of
  magnitude too small.
- **"It is parsing 11,000 events."** Measured on the captured fixture and
  scaled: **0.46 s**. Also too small.

The residual — the HTTP walk, ~56 paginated pages of nested markets fetched
every 15 seconds — was the whole cost, and it was the part I had not suspected
because it *looks* like one line of code.

What generalises:

- **Volume is not cost.** "Seven thousand inserts" is a big-sounding number and
  a rounding error; "one paginated fetch" is a small-sounding phrase and 56
  round trips. Count round trips and bytes, not statements.
- **Measure before proposing, not after being asked to build.** I told Joe a
  fix twice before checking, and both would have shipped work that changed
  nothing. The measurement that settled it took four minutes.
- **And measure the replacement too.** The obvious fix — fetch each of the ~70
  linked events individually instead of paginating — is **worse**: it is more
  requests than pages, against a shared minimum-interval rate limiter that
  serialises them, so concurrency buys nothing. That was caught by reading
  `_RateLimiter` before writing the code, and it would have survived every test
  I would have written for it.

A fourth, about the shape of the failure: **an intermittent fault usually has a
schedule.** This one tracked the betting window — the fast cadence only runs
while a window is open, so the box melted during games and recovered between
them. Finding the schedule turned "randomly unreliable" into "predictably
unreliable for the next 13 hours", which is the difference between an emergency
and a piece of planned work.


## 2026-08-19 — A screenshot proves what the tab context says it does, not what the picture looks like

The browser tool's `navigate` reported **success** on a host the extension was
not permitted for, and the tab did not move. It kept the previous page. So the
screenshot taken immediately afterwards was a fully-rendered, entirely plausible
picture **of a different site** — one that looked exactly like what was being
looked for, because the previous page was the same application on its other
instance.

Every line of output said the navigation had happened. The only contradicting
signal was the `Tab Context` footer still naming the old URL.

**Read the tab context, not the picture.** A screenshot is evidence about
whatever the tab is showing; it carries no evidence about *which page that is*.
Where two deployments of one app differ only by hostname — a demo and a live
instance from one image, which is this project's whole deployment model — the
picture cannot distinguish them and will never look wrong.

The near-miss: this session was one step from writing up a demo screenshot as a
verification of live.

The general rule, which is the same one this repo keeps arriving at from other
directions: **when a tool reports success, find the independent signal that says
what it actually did.** `flyctl logs` is lossy, so read `/api/health`'s
`git_sha`. A grep-based caller check proves a name is present, not that it
resolves. `navigate` returning OK proves a request was made, not that a page was
loaded. In each case the confirming evidence and the reported success come from
the same source, and that is exactly the case where the report is worthless.

A second, smaller trap in the same episode: **a diagnosis is only as good as the
state it was taken in.** Before the extension was restarted, both hosts failed,
and the conclusion written down was "so it is not a per-site permission" — a
real inference from a broken tool. After the restart one host worked and the
other did not, which is precisely a per-site permission. Re-run the
discriminating test after any environment change, and treat conclusions drawn
during an outage as provisional.


## 2026-08-19 — Two columns that must be equal are not checked by anyone, and rendering both is what finds them

The pattern: a value is written into two places by construction — a computed
number and the row it points at — and a comment somewhere says they must agree.
**Nobody ever runs the comparison, because no consumer needs both columns at
once.** The disagreement is then free to exist for as long as the two columns
stay on separate screens.

The instance: `recommendations.fair_probability` and the `p_conservative` of the
`fair_prices` row its `fair_price_id` points at. The API serializer carries the
check *as a sentence* — "Should equal `fair_probability` exactly. Sent so a
consumer can check the join landed on the right row rather than assuming it" —
and no consumer had ever checked. On the seeded demo they disagreed on **11 of
11 rows**, in both directions, because the seeder devigged twice: once as a
multi-book consensus for `fair_prices`, once as a single pair for the
recommendation. Production devigs once and passes the same object to both, so
this could never have been found by reading production code.

Two things to carry:

- **A screen that puts two independently-derived numbers side by side is a
  test.** It found this in one glance after the columns had been apart for the
  life of the project. When adding any view that renders a derived value beside
  its inputs, expect it to surface a disagreement — and treat the disagreement
  as the finding, not as a rendering problem to smooth over.
- **An invariant stated in a comment is not enforced.** If a docstring says two
  columns must be equal, write the assertion in the same commit. The comment is
  where a future reader looks *after* the bug; the test is what stops them
  needing to.

And a corollary about seeded data specifically: **the demo is not exempt from
the invariants of the thing it demonstrates.** A seeder that reaches the same
tables by a shorter route will violate constraints production cannot, and the
demo is the instance anyone actually looks at.


## 2026-08-19 — A picture whose axis is set by its loudest number shows nothing about its quietest

Three separate calibration mistakes in one small chart, all found by looking at
the rendered page and none findable from the code:

**The scale was set by the wrong quantity.** The strip existed to show a
disagreement between four devig methods, routinely a tenth of a percentage point
wide. It also drew Kalshi's ask, which on any row with a real edge is 20+ points
away — so the axis spanned 26 points and the four readings the chart was *for*
collapsed into one pixel. **Ask what the picture is of, and let only that set
the domain.** Context that is far away belongs in a label, not in the scale. An
off-scale marker is then reported as off-scale, never clamped to an edge: a
marker pinned to the end of a scale it is not on is a drawing that lies.

**The legend was coarser than the drawing.** Three visibly distinct marks whose
labels all read `47.4%`. A reader cannot tell "the labels are rounded" from "the
chart is broken", and will pick the second. **A legend must resolve whatever the
drawing resolves** — the precision of the number and the precision of the
position are one decision, not two.

**A structural artifact read as a finding.** The chart's bar plotted each book's
*lowest* of four methods; its marks plotted *one* method averaged. So the marks
sit at or above the bar by construction, on nearly every row — and unlabelled
that reads as "the consensus is higher than every book", a claim about the
market. It is a fact about the statistic. **When two series on one axis are
different statistics, the label has to say which, because the reader will
otherwise interpret the offset as data.**

The general shape, and it is why "eyeball it at the real width" is not optional:
every one of these renders perfectly, passes every unit test of its geometry,
and is wrong on the screen. The node tests proved the axis was not inverted and
that every point landed in `[0,1]`. None of them could have said the axis was
measuring the wrong thing.


## 2026-08-18 — Find the render sites by scanning, not by remembering, and check that the guard's mutation is the one you meant

Three failures in one small change, and none of them was in the feature.

**The first: a component name is not a screen.** A plain-English caption was
added to `SlateRow` and `OpportunityCard` and called done. Both are *Board*
components. `/slate` renders the same field from its own markup, and so does
`/ledger` — so two of four sites were covered, and the one the user's phone
habit actually goes through was not. **A test written from the same list as the
change inherits the same blind spot.** The fix is to derive the list: scan the
whole source tree for the render, and require an entry in an `EXEMPT` map with a
reason for anything that renders it without the new treatment. That scan found
`/ledger` on its first run, which is a site no amount of re-reading the diff
would have surfaced.

The general shape: **when a change must apply everywhere a value appears, the
guard's job is to find the appearances — not to check the ones you already
found.** A per-file assertion is a list you wrote twice.

**The second: one column can carry two vocabularies.** `suppressed_reason`
holds the suppression check names *and* `sizing:{binding_constraint}` strings
written by a different module for a different reason. Pinning the new map to
`ALL_CHECK_NAMES` in both directions felt rigorous and would have shipped a
whole class of rows rendering bare. Before pinning a vocabulary, grep for every
writer of the column, not just the one that names it.

And a corollary that bit inside that: **the reachable subset is not the declared
set.** Only six of the twelve `binding_constraint` values can reach the column —
the rest sit on non-refused results and are shown elsewhere. The first version
of the pin demanded a sentence for `no_edge`, a state that cannot occur there,
because the regex matched the tail of `binding_constraint=`. A guard that
demands coverage of an unreachable state is the same error as one that misses a
reachable one, pointed the other way.

**The third, and the one worth carrying furthest: when a break-it-and-watch-it-
fail check comes back green, the mutation is a suspect too.** Two did here, and
they were different bugs:

- Counting occurrences of the field did not detect it being swapped for the
  gloss, because both components also reference it as a *condition*. The
  **guard** was decoration; it was rewritten to look for a rendering position.
- Removing one gloss call from `/ledger` left the other one, so the scan still
  saw the name. The **mutation** was too weak; the guard was fine.

Those need opposite responses, and "green" looks identical for both. So on a
green result, first prove the mutation reached the thing the test reads — then
decide whether the test is decoration. Skipping that step turns a weak mutation
into a false reassurance about a guard that was always fine, and a decoration
guard into one that ships.

A mechanical note that cost two cycles: **this repo has mixed line endings.**
`suppressionGloss.ts` is LF; `app/slate/page.tsx` and `app/ledger/page.tsx` are
CRLF. A byte-level mutation written with `\n` silently matches nothing in a CRLF
file, and `str.replace` returning the input unchanged is not an error. Every
mutation script must assert that the replacement actually applied before it
trusts the test result — otherwise "the guard is green" and "the mutation never
happened" are the same output.


## 2026-08-18 — A query plan is a shape, not a cost, and the monitoring you add is code that can take the box down

Two defects, one deploy, fifteen minutes of live serving 500. Both are the same
class: **a change made to observe the system became part of the system**, and
was held to a lower standard than the code it was watching.

**The first: `EXPLAIN QUERY PLAN` said the opposite of the truth.** A freshness
field on `/api/health` ran `SELECT MAX(observed_ms) FROM kalshi_quotes`. The
plan reports `SEARCH ... USING COVERING INDEX` for that and a bare `SCAN` for
`ORDER BY id DESC LIMIT 1`, which reads unambiguously as the MAX being the
optimised form. Measured on 3,000,000 synthetic rows with the same schema and
index:

    MAX(observed_ms)           323.7 ms      (linear in table size)
    ORDER BY id DESC LIMIT 1     0.116 ms    (constant)

`observed_ms` is the **second** column of `(ticker, observed_ms DESC)`, so the
aggregate walks the whole covering index; the `SCAN` terminates on its first
row. **Read the plan for shape and measure for cost.** The words SEARCH and
SCAN describe access strategy, not work done, and a LIMIT changes the second
without changing the first.

**The second: "the symbol is called" and "the call resolves" are different
facts.** `budget.remaining_today()` shipped to live; `remaining_today` is a
property on `BudgetState`, which `CreditBudget.state()` *returns*.
`test_has_callers.py` verified the call site existed — true, and useless,
because the call could not run. A grep-based caller check proves a **name** is
present, never that it **resolves**. Where a function has no caller but
`__main__`, nothing executes it and the deployed machine is the first thing to
try. An AST walk asserting every `obj.attr` exists on the bound class costs
nothing and closes it: `tests/test_run_loop_attributes_resolve.py`.

The general shape, which is what to carry:

- **Observability code is production code.** A health endpoint is called by the
  platform check, the frontend proxy and now the loop itself — three callers on
  a fast cadence, so it is the *most* hot path in the process, not an
  afterthought. A query that is fine in a report is not fine there. Both new
  blocks were correctly wrapped so they could not **500**; nothing stopped them
  from being **slow**, and for a liveness probe slow is the worse failure — it
  looks like death.
- **Ask what grows.** `kalshi_quotes` gains ~6,700 rows a pass. Any unbounded
  aggregate over a table that grows per-pass is a time bomb whose fuse is the
  record's own success.
- **The irony is the lesson.** The field added so an external watchdog could
  tell the box was dead is what killed the box. When adding monitoring, ask
  what happens when the thing you are measuring gets large — the failure mode
  of a monitor is that it participates.


## 2026-08-18 — An alert that cannot fire on the failure that happens is not coverage, and the count of alerts hides that

The pattern: a failure channel gets judged by how many alert types it defines.
The number that matters is different — **for each failure that has actually
occurred, is there an alert whose trigger condition that failure satisfies?**
Those two questions come apart badly, because the alerts get written against an
imagined taxonomy of failure and the real failures arrive in a shape nobody
enumerated.

The instance: three purpose-built failure alerts existed, complete and tested,
with **zero production callers** — every reference in the tree was a test. The
one that *was* wired fires inside `except LoopFailed`, which needs five
consecutive pass failures. The failure that actually happened to this instance
(volume full, 2026-08-16) crash-looped the *container*, killing the process
before that exception can be raised. Four alerts on paper, zero coverage of the
observed event.

Three things this generalises to:

- **Ask which process is alive at the moment of the failure.** A watchdog can
  only report a failure it outlives. A loop cannot alert on its own death; only
  something off-box can. Writing that down is the honest deliverable when the
  external piece is out of scope — an ADR that claims coverage it does not have
  is worse than the gap.
- **A watchdog needs a denominator or it gets muted.** "No data arriving" and
  "nothing to send" are the same observation at 3am. The clause that
  distinguishes them is the whole difference between an alarm and a nightly
  buzz, and a muted channel is strictly worse than no channel.
- **Check the writers before trusting a symptom.** The proposed in-process
  signal here was the age of the newest `kalshi_quotes` row, believed to reflect
  the WebSocket. That table is written only by the REST discovery pass; the hub
  writes nothing to it. The symptom was real and measured the wrong subsystem —
  which is the most expensive kind, because it produces a green watchdog.

A fourth, about constants: `FAILURE_KINDS` listed three strings, was referenced
by nothing, and **matched none of the kinds actually sent**. A constant nobody
reads cannot be wrong, so it was wrong for the life of the project. The fix is
not to correct it but to make something read it — here it became the allowlist
for a dedupe key, asserted at the send.


## 2026-08-18 — A default is a decision nobody made, and it is invisible from inside the running system

The pattern: a config loader that supplies a fallback turns "nobody chose a
value" into "the value is X" — and every downstream reader then behaves
correctly with respect to X. Nothing logs, nothing 500s, no test fails. The
defect only exists at the boundary where the value leaves the machine, and the
machine cannot see that boundary. **Grep the deploy files for a setting's name
before believing the deployed value is the one in the code.**

The instance: `COCKPIT_BASE_URL` was defaulted to `http://localhost:3000` in
`backend/config.py` and stated in neither fly config. Every Discord embed
therefore deep-linked to `localhost:3000`. On a phone that resolves to the
phone, so the alert arrived, looked correct, and its link went nowhere. Joe
read this as "the Discord webhook is broken"; the webhook was fine.

Three things make this class hard, and each is worth its own guard:

- **A self-constructing test cannot see it.** `tests/test_discord.py` passes
  `DiscordConfig(cockpit_base_url="https://cockpit.example")` in every case, so
  the default path was never executed. A test that supplies the value it is
  checking asserts nothing about production — the same shape recorded for
  `daily_pnl_dollars` and for `test_alerts.py:180`'s `contracts=0`.
- **A refusal nobody has watched fail is decoration.** The fix copies the
  `APP_AUTH_TOKEN` live boot refusal, and that refusal had guarded live since
  it was written with **no test exercising it** — the whole repo contained no
  `AppConfig.load()` under `pytest.raises`. Copying a guard is a good moment to
  check the original earns its place.
- **The host fix alone would have shipped a bug that survives its own fix.**
  The link was `/?focus=<ticker>` and no file in the frontend reads a `focus`
  param. A correct host plus a dead param loads the Board and silently ignores
  the ticker — which looks fixed. **When repairing a URL, verify the path as
  well as the origin.**

The narrow fix is `tests/test_deployed_urls_are_explicit.py`. The general one
is the enumerate-and-classify inversion this repo already argues for elsewhere:
walk `backend/config.py` for every `_optional(NAME, default)` and require each
name to be stated in both `[env]` blocks or listed in an explicit
defaults-are-the-decision table. `test_deployed_risk_caps_are_explicit.py`
applied that reasoning to money in 2026-08-17 and to nothing else; the identical
hole was open on every other setting the whole time.


## 2026-08-18 — A guard written against one cause leaves the other causes uncovered, and the symptom is identical

The pattern: a quantity can be forced into the same user-visible state by more
than one rule. A guard written when *one* of those rules misfired protects that
rule alone — and when another rule produces the identical symptom, every test
stays green, because the tests were written against the cause and not the
symptom.

The instance: "is this row's edge money?" has two independent "no" paths —
`suppressed_reason` set, and `suggested_contracts == 0` (the sizer refused;
below ~$250 bankroll that is the *modal* row, not a corner case). `edgeTone`
guarded the first and its `Pick<>` signature structurally could not see the
second, so zero-contract rows fell through to the sign test and rendered
`text-positive`. 3,322 tests passed throughout; `tests/test_board_screen.py`
even documented the blind spot in prose while its four guards all checked
`suppressed_reason` ordering.

The rule: **when a screen state means "refuse", enumerate every rule that can
demand it and test the state against the full cross-product of causes — not
against the rule that happened to misfire first.** The fix's test runs the real
function over `{edge sign} x {suppression} x {contracts=0}` via node and
asserts no cell renders as money.

---

## 2026-08-18 — `git checkout <file>` is a destroyer of uncommitted work, and guard-verification is exactly when you reach for it

The pattern: verifying a guard means disabling it, watching the test fail,
and restoring it. The natural restore is `git checkout <file>` — and if the
file also carries *other* uncommitted edits from the same session, the
checkout silently wipes them back to HEAD. It happened here mid-session: the
423 guard was force-disabled with `sed`, verified red, and restored with
`git checkout` — which also discarded two uncommitted route additions in the
same file, with no error and no diff left to notice.

The rule: **before disabling a guard in a file with uncommitted changes,
copy the file aside (`file.bak`) and restore by moving the copy back — never
by git.** Or commit first and verify after, so git's baseline is the state
you want back. The failure is silent in exactly the situation that invites
it, because guard verification feels like a read-only detour and is actually
a write.

## 2026-08-18 — The screen you verify against may be rendering a configuration nothing deploys, and a test that reads config text cannot tell you

A UI change was verified the careful way: not just unit tests, but opened in a
real browser against the real payload, and the element was seen on screen. The
card read **`Buy 17`, `$8.85 total cost`**. Every design judgement of that
session — what is prominent, what a figure is worth, whether a control earns its
height — was made against those numbers.

**No deployed configuration produces them.** `backend/seed_demo.py:405` is
`risk = RiskConfig()` — bare dataclass defaults, a $1,000 bankroll — and the
seeder never calls `.load()`. Running the real `size_position` on the same row
under the deployed caps returns **1 contract, $0.52**. The public demo, which is
the portfolio piece, overstates by **17x**.

**The visual check was not wrong. It was answering a different question than the
one it appeared to answer** — "does this render?" rather than "does this render
what a user will see". Both feel like verification and only one of them is about
the deployed system.

**The second half is worse, and it is the part that generalises.** An ADR had
already been written about exactly this class of bug. Its Context says the
failure was *"`RiskConfig` was well tested, and the tests exercised the loader,
never the deployment."* Every assertion it then shipped was about **the text of
the config files** or **the loader**. Not one touched what the demo renders. It
committed the error it had just diagnosed, one level up, and its status is
Accepted — so the hole reads as closed to everyone who comes after.

**Naming a failure mode does not inoculate you against it.** The abstraction
level you are checking at is itself a choice, and writing an eloquent paragraph
about the previous level does not automatically move you up one.

**How to apply.**

- **Ask what produced the numbers on the screen you are looking at**, before
  reasoning about them. A seeder, a fixture and a deployment are three different
  configurations, and a demo exists precisely to be *unlike* production.
- **A test that asserts on config text or on a loader has not tested the
  deployment.** Make the assertion on the rendered output — the size the card
  shows, the string the user reads — and disable it to watch it fail.
- **When an ADR claims to close a class of bug, check its assertions against its
  own diagnosis**, not against its conclusion. The two can disagree, and an
  Accepted status hides that from everyone downstream.
- **"How wrong is it?" is a separate measurement from "is it wrong?"** Both were
  available here for one command each, and only the first had been taken. Do not
  publish a multiple you inferred from a cap when you can compute it from the
  real function — the constraint that actually bound was Kelly, not the cap the
  estimate assumed.

Related: [[a-guard-that-is-structurally-always-true-reads-exactly-like-a-guard-that-fires]],
[[built-but-never-called]], [[verification-methods-that-lie]].

---

## 2026-08-18 — Hand a reviewer your hypothesis and require it to be refutable, then let it win

A visual-design reviewer was briefed with a specific suspicion: two CSS tokens
held the same hex, so the colour meaning "this is the action" was the colour
meaning "this is bad". The brief named the tokens, the files, and the reasoning
— and added one sentence: *"Do not assume it is a defect because you found it."*

It came back and **refuted the hypothesis.** Keep them identical: two reds a few
degrees apart read as one colour to the eye and as a rendering bug to anyone who
notices, and both meanings are unwelcome news, so nothing is lost by sharing.
The real defect was the *third* meaning the same token carried — and that one had
a measured contrast failure behind it, which the original suspicion did not.

The refutation was worth more than the hypothesis. Without the licence to refuse,
the likely outcome is a reviewer that finds a way to agree with the brief — and
agreement between a briefer and the agent they briefed is **correlation with the
brief, not evidence about the world.**

**How to apply.**

- **Put the hypothesis in the brief, with its evidence, and explicitly permit
  "no".** Withholding it produces a vaguer review; including it without the
  licence produces an echo.
- **Ask for the verdict plus a reason, and require a measurement where one is
  possible.** "Keep it, because X" is a finding. "Yes, that's a problem" is not.
- **Treat a subagent's agreement with your framing as the weakest signal in its
  report**, and its disagreement as the strongest.

Related: [[scrutiny-was-spent-asymmetrically]],
[[delegation-is-the-partners-call]].

---

## 2026-08-17 — A handoff written the night before states tomorrow in the past tense, and "the deadline has passed" is a claim that creates work

A session prompt opened with *"The budget day closed at 2026-08-18T10:00:00Z"*
and built the entire session on it: one measurement, then a decision by Joe. It
was **2026-08-17T21:49Z**. The window had **twelve hours** left to run.

Nothing was wrong with the reasoning downstream of it. `tasks/NEXT.md` was
correct and said the figure *"arrives when the budget day closes at
2026-08-18T10:00:00Z"* — future tense, accurate. The prompt derived from it
converted a deadline the author was writing *toward* into one they were writing
*after*, which is what happens when a handoff is composed hours before the thing
it describes.

**The whole check was `date -u`.** It cost one command and it was the difference
between a real measurement tomorrow and a fabricated one tonight — because the
command would have *run*. `credits-day` on an open window returns rows and a
total quite happily. It has no idea the day is not over. **The instrument does
not refuse a premature read; it answers it,** and the answer is a partial-day
figure that looks exactly like a daily one once it is written into a document.

**This is the "check the claims that create work" lesson pointed at time.** A
stated deadline is a claim with the same shape as *"X is broken"*: it arrives
with authority, it is boring to verify, and believing it buys the reader an
immediate task. Here it would have bought a published run rate off a half-day.

**How to apply.**

- **Run `date -u` before acting on any handoff that says a window closed, a job
  finished, or a period elapsed.** One command, and this repo's clocks are
  budget days on a 10:00Z boundary, not calendar dates — the two disagree for
  ten hours out of every twenty-four.
- **Ask whether the tool would refuse a premature read.** Most will not.
  Anything that aggregates over a window will happily aggregate over a partial
  one and label it with the window's name.
- **Handoffs are written before the future they describe.** Treat every past
  tense in one as the author's *intent* about a time that had not yet arrived,
  and re-check the ones that gate work.
- **When the premise fails, say the session is not due rather than finding
  something adjacent to do.** The correct output of a not-yet-due measurement is
  the measurement, later.

Related: [[open-the-set-before-predicating-over-it]],
[[scrutiny-was-spent-asymmetrically]].

---

## 2026-08-17 — Scrutiny was spent asymmetrically, and the unguarded direction was the one that created work

In one session a director agent produced three checkable claims. It verified
the one that **flattered its own thesis** — that props supplied 81 of 199
clusters, which made its headline finding real — and did not open the two that
**created work**: a claimed `credits-day` boundary defect (the tool was
correct, and defaults to the right boundary) and a claimed contradiction
between a recorded "338" and a measured 416 (the sentence says *"one cluster"*;
338 + 78 = 416 exactly). Both were wrong. Both would have spent a session.

**The standard framing of this failure is the wrong way round here.** The
warning everyone carries is *"be extra sceptical of good news"*, and it was
obeyed — the flattering number was the one that got checked. What went
unguarded was the opposite direction: a claim that something is *broken* is
also a claim, it also arrives with a motive, and its motive is that finding
defects feels like diligence. **A false positive that manufactures a lane is
not the safe direction; it is the expensive one**, and it wears the costume of
rigour so it draws no scrutiny at all.

The same session then did it a third time on the same axis: a lane was scoped
from a guard that turned out to be structurally unreachable — the entry below
this one.

**How to apply.**

- **Check the claims that create work as hard as the ones that flatter you.**
  Before opening a lane on "X is broken", open X. It is usually one command.
- **Ask what a claim buys its author.** "This is a defect" buys a task. That is
  a motive, and motives are what scepticism is for, whichever direction they
  point.
- **When you hand someone a brief, name which sentences you verified and which
  you inferred.** A director reasoning from an implementer's unverified
  sentence produces confident, wrong direction — and the implementer is the
  only one who knows which were which.
- **Two agents agreeing is not verification if one briefed the other.** The
  correlation is the brief, not the world.

Related: [[open-the-set-before-predicating-over-it]],
[[a-guard-that-is-structurally-always-true-reads-exactly-like-a-guard-that-fires]],
[[say-which-way-a-blind-spot-points]].

---

## 2026-08-17 — A guard that is structurally always true reads exactly like a guard that fires, and "this condition is checked" is not evidence the condition varies

A whole work item was scoped from this observation: *every cost figure on the
Board card sits inside `rec.suggested_contracts > 0`, so on rows sized to zero
the card shows an edge and no cost.* The guard is real, at two places in the
file, and the reading is the obvious one.

**There are no such cards.** `routes.py` builds the `surfaced` bucket under `if
row["suggested_contracts"] > 0`, `page.tsx` feeds `LiveBoard` nothing but
`board.surfaced`, and `LiveBoard` is `OpportunityCard`'s only call site. The
guard is **structurally true on every card the component renders**. Zero-sized
rows never become cards at all — they render as a one-line `SlateRow` that
already says *"no edge after fees"* in English. The proposed fix was a no-op on
the only screen it could reach.

**Two agents and I all read the guard correctly and all drew the wrong
conclusion**, because we answered *"does the component check this?"* and never
asked *"can anything that reaches the component fail the check?"* Those are
different questions, and only the second one is about behaviour. A defensive
guard on an invariant looks identical, in the file, to a guard on a live
distinction.

**The direction it points matters and it was the flattering one.** Believing
the guard fires invents a defect, and an invented defect justifies a build. It
manufactures work that will pass its own tests and change nothing on screen —
this repo's "built but never called" shape, arrived at from the opposite
end: not code with no caller, but a *fix* with no case.

**Two real things were underneath it, and neither was findable from the guard.**
Tracing the call path instead turned up a live defect — the streamed re-size
zeroes `suggested_contracts` and nothing else, so the card kept a stale *"Sized
at 14."* and stayed tappable — and a dual-meaning field, `fee_predicted`, that
is per-contract on a refused row and whole-order on a sized one.

**How to apply.**

- **Before scoping work from a conditional, enumerate what reaches it.** Walk
  from the component to its call sites to the payload that builds them. One
  grep for the field name in the serialiser usually settles it.
- **Ask "when is this false?" and answer with a row, not an argument.** If you
  cannot name a real input that fails the check, the check is an invariant and
  there is no behaviour to fix.
- **A guard's existence is evidence about its author's caution, not about the
  data.** Defensive code is written precisely where the author was unsure, which
  is often where the case cannot occur.
- **`runtime-realist` answers the question you ask it.** Asked *"does the Board
  render a fee number"* it correctly answered *"yes, inside these guards"* —
  accurate, and it did not settle whether the guards fire, because that was not
  the question. When the answer will scope a build, ask the reachability
  question explicitly.
- **The standing lesson is "grep for callers before believing a feature
  exists". Its inverse is now proven: grep for callers before believing a
  guard hides anything.** Same command, opposite belief, and both errors were
  found in this repo within a fortnight.

**A postscript, from the same session and the same shape.** A guard written
*for* this lesson then failed its own disabling check twice, and neither failure
was the code's:

- The first mutation injected `sum(fee_predicted)` in front of the first
  `from ` in a dbt model, which happened to be **inside a comment** — so the
  comment-stripper removed the mutation along with its host line and the test
  stayed green. A mutation that lands somewhere the guard deliberately ignores
  proves nothing, and it looks exactly like a guard that does not work.
- Before that, the guard itself reported a *correct, exempt* model as an
  offender, because that model names `stg_recommendations` once — in a comment
  reading *"See `stg_recommendations` for why `/` is wrong here."*

**In a repo whose files are more prose than code, any source scan that does not
strip comments is reading the documentation.** That cuts both ways: it produces
false positives against correct code, and it silently absorbs your mutations so
a real guard reports itself as decoration.

Related: [[open-the-set-before-predicating-over-it]],
[[built-but-never-called]],
[[a-feature-and-the-path-that-invokes-it-are-two-deliverables]].

---

## 2026-08-17 — A decision justified by a statistic computed under a *different definition* than the one the decision affects, and the codebase already had the difference written down

ADR 0032 turned scheduled prop buying off. Its whole case was that props "cannot
move the denominator": since ADR 0029 the gate clusters on
`event_links.odds_event_id`, a prop ladder inherits its game's id, so it
collapses onto the game and adds no cluster. **Every word of that is true.**

**It is true about the gate's 300. The project has two.** The CLV signal test's
`G = 300` is a different statistic with its own *registered* cluster key,
`COALESCE(m.event_ticker, r.ticker)`, under which a prop ladder **is** its own
cluster. Props were supplying **81 of 199 clusters — 40.7% of `G`.**

**The difference was not hidden. It was in a comment, in prose, with numbers**
(`backend/analysis/clv_signal.py:109-114`): *"The cluster key ... is NOT the
gate's key ... the two give 210 and 125 — a 68% difference — so a `G` quoted
without its key is meaningless."* Somebody wrote that sentence precisely so this
could not happen, and it happened anyway, because the ADR never asked which `G`
it meant. **A named quantity that exists twice in one system is not disambiguated
by being obvious to whoever defined it.**

**The consequence is worse than the error, and it is the reason this is a lesson.**
The retired arm was the *more negative* one (`prop −0.519` vs
`moneyline −0.082`). So the pooled estimate now drifts **toward zero — toward
what reads as good news — by composition rather than by evidence.** An error
that merely miscounts is cheap; this one manufactures a future false positive,
on a schedule, in the flattering direction, and it would arrive looking like the
thing the project spent months hunting.

**How to apply.**

- **Before citing a count as a reason, name the key it was counted under**, in
  the same sentence. `G = 199` is not a fact; `G = 199 under
  COALESCE(event_ticker, ticker)` is. If a project has two denominators, every
  unqualified use of one is a coin-flip.
- **Grep for the quantity's own definition before reasoning about it**, not just
  for its value. The 68% figure was one grep away and would have stopped the
  argument cold.
- **When a change alters what a running measurement is made of, write the
  expected drift down the day it happens** — direction, not magnitude — and put
  it where the *next reader of the result* will hit it, not only in the ADR that
  caused it. A composition change is invisible at the look; it has to be
  pre-announced or it is indistinguishable from a finding.
- **State the direction of the bias explicitly.** "Toward zero" is the same
  discipline as *say which way a blind spot points*: a drift toward good news is
  the one a future session will not question.
- **A wrong justification does not imply a wrong decision.** Annotate and keep
  the decision when the outcome is unchanged; reversing on sourcing alone would
  here have meant spending 86% of the credit bill to accelerate a statistic
  `CLAUDE.md` forbids any roadmap from depending on.

Related: [[a-boundary-borrowed-from-another-subsystem-answers-a-question-it-was-never-about]],
[[an-exclusion-count-describes-the-filter-not-the-world]],
[[say-which-way-a-blind-spot-points]],
[[open-the-set-before-predicating-over-it]].

---

## 2026-08-17 — An acceptance criterion carries implicit scope, and the person who sets it owns that scope

A lane was capped at a named deliverable list: backend field, banner predicate,
two fixtures, one ADR, one lessons line. The acceptance criterion attached to it
was stricter than the list — *"the fixtures must render opposite verdicts, and a
disabling mutation must go red; if the predicate cannot separate them it is not a
fix and the lane is abandoned."*

**That criterion was unsatisfiable within the deliverable list.** Every existing
frontend guard in this repo asserts on **source text**, because there is no
JavaScript test runner here. A substring assertion passes unchanged against a
predicate that has been exactly inverted, so it cannot render a verdict at all.
Meeting the criterion required extracting the predicate into a plain-TypeScript
module a test could execute — a file nobody had listed.

The implementer flagged it as possible scope they had taken. The director's
answer was that it was scope they had **set**: a criterion phrased as a test is a
build instruction in disguise, and under-specifying it does not transfer
ownership to whoever discovers what it costs.

**Why this is worth a lesson and not a shrug.** The failure mode it prevents is
the *quiet* one. An implementer who notices an unlisted requirement has two
cheap, wrong options — build it silently and be accused of scope creep later, or
satisfy the criterion's letter with a source-text assertion that is worthless
here. Both end with a green suite over an unverified claim, which is this repo's
most-repeated shape.

**How to apply.**

- **When you set an acceptance criterion, cost it against the tools that
  actually exist in the repo.** "Watch the test go red" presumes a runner that
  can express the assertion. Check that it can before making it the gate.
- **When you meet one and it forces unlisted work, name it and hand the
  ownership question back** rather than either absorbing it silently or
  weakening the criterion. It is one message and it settles the record.
- **A criterion is a stricter instrument than a deliverable list**, so where the
  two disagree the criterion wins — and that is exactly why the list is not a
  budget for it.

Related: [[a-feature-and-the-one-path-that-invokes-it-are-two-deliverables]],
[[the-file-ownership-map-between-parallel-lanes-is-a-design-artefact]],
[[a-mutation-that-cannot-change-behaviour-is-a-green-light-you-awarded-yourself]],
[[a-command-in-a-handoff-has-the-status-of-a-test-never-seen-red]].

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
each is in the linked archive file, unchanged; the sections marked *in this
file, above* are the ones not yet archived.

**Regenerated 2026-08-26.** This index had listed the five entries of
2026-08-17 as "in this file, above" and stopped there, while 61 later lessons
sat unindexed above it — so the line "every lesson ever written" was false of
its own file, and a session scanning the index for something relevant would
have missed every lesson written in the last nine days. The titles below are
the lessons' own headings, taken verbatim; keep it that way, so regenerating it
is a script and not a judgement.

### 2026-08-26 — in this file, above

- `load_dotenv()` makes the whole test suite a credential holder, and arming is what turns that into spending
- A source-scan pin measures what it can still match, and it goes quiet rather than red
- Pin a guard on the decision it changes, never on the string it prints
- A derived value inherits its source's absence as an extreme, not as a gap
- A fixture that writes a value the wire never emits is a defect with a delayed fuse
- Bytecode caching is keyed on (mtime, size), so a same-length edit can survive its own revert
- A feature behind an off flag has never rendered, and the first render is part of the build
- A guard installed by an unverified edit is not installed

### 2026-08-25 — in this file, above

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

### 2026-08-24 — in this file, above

- An access-control finding names the layer it was read at
- A baseline taken while you edit is not a baseline
- A pin verifies the shape you saw, not the branch you rely on

### 2026-08-23 — in this file, above

- A wire format that was pinned but never exercised is a belief wearing a pin
- A pinned fixture clock against a wall-clock instrument is a test with an expiry date
- "The screen shows X" must come from the screen, not from the database that feeds it

### 2026-08-21 — in this file, above

- A field written after the spend is not a spend gate
- When a rule and its floor are defined over different units, the smaller unit's zero-information observations vote

### 2026-08-20 — in this file, above

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

### 2026-08-19 — in this file, above

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

### 2026-08-18 — in this file, above

- Find the render sites by scanning, not by remembering, and check that the guard's mutation is the one you meant
- A query plan is a shape, not a cost, and the monitoring you add is code that can take the box down
- An alert that cannot fire on the failure that happens is not coverage, and the count of alerts hides that
- A default is a decision nobody made, and it is invisible from inside the running system
- A guard written against one cause leaves the other causes uncovered, and the symptom is identical
- `git checkout <file>` is a destroyer of uncommitted work, and guard-verification is exactly when you reach for it
- The screen you verify against may be rendering a configuration nothing deploys, and a test that reads config text cannot tell you
- Hand a reviewer your hypothesis and require it to be refutable, then let it win

### 2026-08-17 — in this file, above

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
