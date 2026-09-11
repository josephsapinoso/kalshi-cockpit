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

## 2026-09-08 - A spine that records its own corrections inline grows without bound, and the corrected fact is the only part a session needs

`CLAUDE.md` reached 44KB, and 61% of it was one section narrating how each
of its facts had been wrong before — "this paragraph used to say", struck
defects, dated audits, a correction of a correction. Every trail was honest
and every one had a home already (an ADR, a `docs/measurements/` file, a
`timing.py` comment block). What a session needs from a spine is the
corrected fact and a citation; the trail is for the reader who doubts the
fact, and that reader can open the citation.

**The pattern:** when a correction lands in an always-loaded file, write the
corrected sentence and the pointer, and put the *how it was wrong* where the
pointer goes. If the file has no such destination, `docs/history/` is one.
Inline trails feel safe because deleting feels risky; the cost is paid on
every turn by every session, and it is the same cost that made `NEXT.md` and
this file unreadable at 456KB. The strike-marker test
(`tests/test_combo_book_depth_claims.py`) is the one caveat: a forbidden phrase
and the marker that licenses it leave together or the guard goes red.

## 2026-09-08 - "This route has no guard" is a claim about the whole dependency chain, not about the route body

An audit of `POST /api/parlays/bid` — armed, real money — found no `is_demo`
check anywhere in the handler and concluded the public instance was kept off
the order path only by the accident of having no credentials. That is
CLAUDE.md's named nightmare (*"a public URL must not be one config bug away
from the order path"*), so a guard was written.

**It was redundant.** `require_auth` refuses on `app_config.is_demo` before it
ever looks at a token, and the route carries
`dependencies=[Depends(require_auth)]`. Every mutating route was already
closed on the demo, structurally. The finding was produced by reading the
handler body and the module, and by grepping the route's own file for
`is_demo` — none of which can see a guard that arrives through a dependency,
a decorator, a middleware, or a base class.

**The tell was available and was not used:** the sibling path's guard was
found by grepping for its *symbol* (`_manual_reachable`), and the same search
for how THIS route is protected was never run. Asymmetry between two similar
paths is a hypothesis, not a finding — and the cheapest test of it is to make
the request and read the response, which is what eventually produced the
correction here, as a failing assertion on a string the guard did not write.

**So: before reporting a missing guard, execute the path.** A refusal you have
actually seen beats any amount of reading, and a guard's absence from the code
you looked at is not its absence from the system. Where an audit says
"unguarded", the write-up should name the request it made and the response it
got, not the greps it ran.

The corollary is about scope, not just method. A negative claim of the form
"nothing enforces X" quantifies over the whole program; the evidence gathered
was about one file. **A universal claim needs either an execution or a search
over the enforcement mechanism, not over the place you expected to find it.**

What survived the correction was worth keeping: the property (`the demo cannot
rest a bid`) is now pinned on the endpoint that spends money, rather than only
on the test for `require_auth`. Verified by deleting the demo branch and
watching three tests go red. A wrong diagnosis can still leave a right test
behind — but it must be re-attributed honestly, or the next reader inherits
the wrong reason.

---

## 2026-09-08 - A guard that reads the code but not the decisions is half a guard

A false claim about combination liquidity was corrected across the code and a
guard was shipped the same day to keep it corrected: five pinned files, a
forbidden-phrase list, a strike-marker allowance so a correction note may quote
what it replaced. Good guard.

**At the moment it shipped, the claim it existed to catch was still asserted as
fact in four ADRs it did not read** — including the one that decided how the
buy control behaves on a combination. All four could have sat there
indefinitely with CI green, and an ADR is precisely what the next session reads
to decide whether a question is settled.

Two separate mistakes, and the second is the more instructive:

**The scope stopped at the code.** Pinning is chosen file by file, and the
files that come to mind are the ones you just edited. Decision records are
where a wrong claim does the most damage per byte — they are cited *instead of*
re-measuring — and they are the least likely to be on a list assembled while
fixing a screen. Glob the directory rather than listing it, so a new document
is covered the day it is written.

**Only half the defect was guarded.** The depth figure and the entry/exit
conflation shipped in the same sentences and were corrected in the same pass,
but only the depth phrases entered `FORBIDDEN`. The unguarded half was the one
that had reached a screen. When a correction fixes two claims, both go in the
guard, or the guard certifies a document that is still wrong.

**The general form:** after writing a guard, ask *where else does this claim
live?* and answer it by searching the repo for the claim rather than by
recalling what you edited. The list of files you touched is a record of where
you already looked -- it is the worst possible source for where you have not.

**And state a guard's blind spot in the guard.** This one's strike-marker
window licenses the phrase near a correction note, so the one place a struck
claim can quietly return is beside its own correction — verified: re-inserting
the phrase into the corrected paragraph left the suite green. That is an
accepted cost, not a bug, but a cost nobody has written down is indistinguishable
from a cost nobody knows about.

---

## 2026-09-08 - Removing a brake server-side leaves it on the screen, and that direction of the mismatch is invisible

Every prior instance of this repo's "one predicate with two spellings" defect
ran the same way: a screen that promised buying which was not happening. So the
habit that grew around it was to check whether the screen **over**-promises.

The fourth instance ran the other way. Joe removed every ceiling on a hand bet
and `POST /api/manual-orders` obeyed the same day; `GET /api/manual/market/`
went on serving `authorised_contracts` from `min($3.00 spend cap, 10% of the
observed balance)`, and the buy button disabled Confirm above it. **The screen
kept braking after the server stopped** — 3 contracts offered against a route
that would take 250 — for thirteen days, on the only path that spends real
money.

**A removal is a two-sided change and only one side announces itself.** When a
server-side guard is deleted, the deletion is visible in the diff, the tests
and the ADR. The client-side *consumer* of that guard's output changes
nothing, compiles fine, and keeps enforcing the dead rule with no diff to
review. Nothing goes red, because the number it reads still exists — it has
merely stopped meaning what it meant.

So: **when you remove a bound, grep for who READS the number it produced**, not
only for who raised the exception. The exception has a name and is easy to
find; the derived quantity is usually an integer on a wire with a neutral name
like `authorised_contracts`, and the thing gating on it is in another language
in another directory.

And the failure is silent in the direction that matters least to a test suite
and most to the user: an over-restrictive screen throws no error, logs nothing,
and looks exactly like a working product. The only symptom is a person who
cannot do the thing he was told he could.

**Corollary, from the same session:** the fix that removed the *last* ceiling
(`ebbb809`, the exposure cap) made the server accept an unobserved balance
while the read still returned `None` for it — so the mismatch was *widened by
a commit that was part of closing it*. A partial removal is a moment of
maximum divergence between the two spellings, not a step toward agreement.
Ship the consumer in the same commit as the guard, or the screen lies in the
interval — the same ordering rule `CLAUDE.md` already records for copy that
names a condition to wait for.

---

## 2026-09-08 - A count or a "not yet" copied into a new session entry is a present-tense claim from a past reading

Two items in one Open list were stale in the same way, and neither was wrong
when it was first written.

Item 2 said *"the first real `manual_orders` row is the finding, and there is
not one yet"*. Two rows landed about an hour later. Item 9 said the decision
map's third queue had *"~9 live items"*; an audit of all 32 closed tickets
against the tree found 23 built, 7 decided as no-build, and **2** genuine gaps.
The "~9" had been carried forward from an earlier entry that counted eleven,
across sessions that built almost all of them.

This file already learned the general form about lane tables — *"a hand-typed
lane state asserts the present tense and starts rotting the second it is
saved"* — but the `Still open` list was exempt from it by nothing but habit,
because it reads like a to-do list rather than like a measurement.

**It is a measurement.** "There is not one yet" is a claim about a table right
now. "~9 items" is a count. Both were true at some past instant and are
asserted in the present tense by being copied into a fresh, freshly-dated
entry — which is exactly the move that launders a stale reading into a current
one.

**So every numeric or negative claim in a handoff carries the command that
produced it, or gets re-run when the entry is written.** `n_rows 2` beside
`inspect_live_db.py manual-orders-audit` survives being read a week later,
because a reader can tell what it was and re-take it. "There is not one yet"
cannot be re-taken, cannot be dated by inspection, and is believed.

The cheap version of the discipline: when writing a `Still open` list, a claim
you cannot cite a command for is one you should either re-derive or write as
"as of <date>, unverified since".

---

## 2026-09-08 - A consumer that restates a predicate is not covered by the test that pins it

A script computing NFL credit demand published **116** where the answer was
**124**. It had reimplemented the due-window check as

    fire_from_ms <= now < fire_until_ms

against production's `SweepSlot.is_due`, which is `<=` on **both** ends. The
strict `<` drops the last refresh of every window: six calls counted where seven
are made.

`tests/test_sweep_timing.py::test_a_full_window_is_seven_calls_and_the_number_is
_written_down` exists **precisely** to stop a six being quoted, and it was green
the whole time. It guards the planner. The defect was in a consumer that
declined to call the planner's own predicate and wrote its own instead. **A test
that pins a rule protects the code that calls the rule, and nothing else.** The
fix is not a better test of `is_due`; it is calling `is_due`.

The tell was printed and not read. The script's banner derived
`7 calls per full window` from the constants and printed it eight lines above a
body reporting 18 window calls across 3 clusters. **When a program prints both a
derived quantity and a counted one, they are an assertion — make it one**, or
accept that nobody reads across.

**The second half is the one that would have caught it without any of the
above.** 124 was already in this repo, twice: in a measurement doc's amendment
and in that test's docstring. The new derivation contradicted both and was
written up without noticing. So: **a derivation that disagrees with a published
number must halt.** Not "investigate later" and not a footnote — reproducing a
figure is evidence, and silently replacing one destroys the record's ability to
tell drift from error. Grep the repo for the number before publishing it.

Related, from the same audit: the same script planned **once** at day start
where the production loop replans every pass. That is the general failure of
simulating a loop with a snapshot — state the loop recomputes must be
recomputed, or the simulation answers a question about a frozen world. It hid
six 5-cluster days out of 57.

## 2026-09-08 - A mechanism that relabels spend is not a saving

A credit ceiling was computed at 878 against a 700 cap, and the first instinct
was to call it loose because "attention is displaced by the schedule" — a real,
documented mechanism: when a kickoff-window slot satisfies the refresh cadence
first, the buy is recorded with a NULL trigger instead of `ATTENTION`.

That mechanism does not save a credit. Trace what it touches:

- The call happens either way, and it was **already counted** in the schedule's
  term. Displacement changes which term *claims* it, not whether it is made.
- The attention sub-cap counts only `ATTENTION`-stamped rows. So a displaced
  buy leaves the slice **unspent** — free to fund a different call in a later
  hour.
- Therefore under the only premise where the ceiling matters — the slice
  running out — displacement moves **exactly zero** off the total. It can even
  move the total up, by deferring slice consumption into hours that would
  otherwise have been quiet.

The pattern: **when a sub-cap is denominated in a label rather than in the
resource, a mechanism that changes labels changes what the sub-cap permits, not
what the resource spends.** Before crediting any such mechanism with headroom,
ask which of the two it caps. The same question applies to every quota this
repo keeps by `trigger`, and `trigger` is already known to be displaceable.

Corollary worth stating separately, because it is where the error entered:
**"this bound is loose" is a claim and needs its own derivation.** It was
asserted from the direction of the mechanism (displacement reduces attention,
attention is in the sum, so the sum is over-counted) without tracing the
accounting. Loose in which term, by how much, under what premise — or say the
bound is a bound.

## 2026-09-08 - A mutation that stays green has two readings, and only the code tells you which

The rule in `CLAUDE.md` is "every guard is verified by disabling it and
watching the test fail. If it stays green, it's decoration." That rule is
right and it is also **incomplete**, in a way that would have deleted a working
guard.

Verifying a new lay-price test, the obvious line was disabled:

    if market_key in EXCLUDED_MARKETS:   ->   if market_key in ():

The suite stayed green. Read literally, the rule says the test is decoration
and should go. It is not. `EXCLUDED_MARKETS` only chooses **which log message
is emitted**; the actual gate is the `PRICEABLE_MARKETS` whitelist one line
above, where anything unclassified is dropped by default. Adding `h2h_lay` to
that whitelist instead turned two tests red immediately -- the new NFL one and
the MLB one that had stood for a month.

So: **a green mutation means either the test is decoration or the mutation
missed the guard.** Those are different conclusions with opposite actions
(delete the test / re-aim the mutation), and nothing in the green result
distinguishes them. Only reading the code does.

The tell, in hindsight, is that the disabled line sat inside a branch that had
*already decided to `continue`*. A guard that is genuinely load-bearing is on
the path to the outcome; a line that only shapes a log message is downstream of
the decision. **Before concluding "decoration", check that the line you
disabled is actually what makes the difference** -- a name containing
EXCLUDED, DENY, FORBIDDEN or SKIP is a strong hint and not evidence.

Corollary worth its own sentence: a whitelist and a denylist that both mention
the same key are not two guards. The whitelist is the guard. The denylist is
documentation with an `if` in front of it.

**Merged 2026-09-08 with its corollary:** run a new guard against the code *before* the fix as well. A green suite after the fix proves the test agrees with the fix, not that it would have caught the defect.

## 2026-09-08 - A capture script that reads the environment captures the laptop, not the deployment

A script was written to buy one NFL odds payload and commit it as a wire
fixture. The first draft read the request shape from the environment, with
live's values as defaults -- which reads as careful, and is the opposite.

`fly.live.toml` sets `ODDS_MARKETS = "h2h,spreads"`. This laptop's `.env`
carries `ODDS_MARKETS=h2h`, the older narrower shape. Loading `.env` for the
credential -- which the script must do -- would have picked that up too, bought
a **two**-credit payload instead of four, and produced a fixture of a request
**the recorder never makes**. Every test written against it would have passed,
and would have pinned a code path nobody runs.

The general shape: **a fixture's value comes entirely from being the bytes
production actually sees, so any parameter of the request must be pinned to
production's value, never inherited from wherever the capture happens to run.**
Config that is correctly environment-driven at runtime is exactly the config
that must be frozen at capture time, and those two facts feel contradictory
right up until a fixture is wrong.

What made it visible was a cost guard: the confirm flag names the price
(`--confirm-spend-4`) and the script refuses if the shape does not multiply to
it. That was written to stop *over*-spending. It caught an *under*-spend, which
is the more dangerous direction, because overspending announces itself on the
bill and underspending announces itself never. **Name the expected cost in the
flag; a shape that silently costs less is silently testing something else.**

## 2026-09-07 - "It might be slow" is not a tolerance; find the bound

An advisory agent noted, correctly, that `window_status` cannot see a
fixture-less sport, so its null `next_call_ms` feeds `Tempo.next_wake_ms` and
the loop "may pace itself slowly for the buy it is about to make." The
conclusion drawn from it was *"a bootstrap at 04:10Z is the design working"*,
and that sentence was written into the open item as an operational tolerance
before anyone read `Tempo.interval_s`.

It resolves to `slow_interval_s`. On live that is `RUNNER_INTERVAL_S = 900`,
stretched by at most `JITTER = 0.15`. A bootstrap also needs a *full* pass, and
`pass_kind` returns `full` every 900s regardless of the sleep. The real bound
is one full-pass interval: **03:37Z, not 04:10Z** — and the difference is
thirty-three minutes of not looking for a fault that would by then be real.

**Pattern: a null that means "unknown" is rarely a null that means
"unbounded".** When widening an alerting threshold because some mechanism
"might be slow", go and read what the slow path actually returns. Nearly always
there is a cap, a floor, or a second cadence that bounds it — and the widened
threshold is then not conservatism, it is a blind spot with a justification
attached.

The asymmetry is what makes this worth a lesson: a threshold that is too tight
costs one false alarm and a two-minute check. A threshold that is too loose
costs the window in which the fault was cheap to find, and it does so silently,
because nothing fires. **Loosening a threshold is the change that needs the
evidence, not tightening it.**

Corollary on where this came from: the reasoning was an agent's, it was
plausible, and it was *directionally* right — the loop genuinely does not
predict the buy. Directionally right is where this fails, because it survives
the sniff test that a wrong claim would not. Take the mechanism a helper names
and check the constant yourself before the number reaches a plan.

---

## 2026-09-07 - "Expect the count to fall" is a claim about a delete that may not exist

The plan for the first NFL sweep said: *"after the first sweep expect 32 -> ~16,
then 16 -> ~0."* Both numbers were wrong, and wrong in the direction that reads
a success as a failure -- for a week, which is how long it would have taken for
retention to make the sentence true by accident.

Nothing sets `unmatched_items.resolved` and nothing deletes a row when the work
item stops failing. `linker.py` only ever upserts. So a fixed row does not leave
the table: it stops being re-derived and sits at a frozen `last_seen_ms` until a
7-day retention window prunes it. The count after a successful fix is *identical*
to the count before it.

The observable was never the count. It was the **timestamp**: rows still failing
carry the newest pass's stamp, rows that were fixed carry the stamp of the last
pass that failed on them and never move again.

**Pattern: a predicted change in a count is a claim that some code path removes
rows, and that path has to be named.** Before writing "expect N to fall", find
the `DELETE`, the `resolved = 1`, or the filter that would drop the row -- and if
there is none, the count is not the instrument. Ask instead which column *does*
move, and write the expectation over that.

The tell is available cheaply and was never taken: `resolved` was documented as
"set by no code path" in the script's own docstring, in `retention.py`'s comment,
and in the schema. Three files said so and the plan still predicted a fall.

Corollary, because this is the shape that makes it dangerous: **an append-only
diagnostic table inverts the usual reading.** In a queue that deletes on success,
a shrinking count is good news. In one that does not, a *stable* count is good
news and a growing set of fresh stamps is the alarm. Which kind you are looking
at is a property of the writer, not of the table's name.

---

## 2026-09-07 - An instrument is not verified until it has been run against the real data once

`scripts/list_unmatched.py` had 16 passing tests, a `mode=ro` connection, an
explicit empty-queue sentence, and a refusal path that exits non-zero on an
unreadable database. It was careful code. Its first run against the live queue
returned **75.8 KB for 66 rows**.

One `KXNFLTEAMTOTAL` row's `detail` is the whole points ladder joined by " vs ",
about 2,100 characters. A column table takes its width from its worst cell, so
all 66 rows were padded to it -- and the `last_seen` column, the only column the
reading actually needed, ended up two thousand characters right of where anyone
looks.

No test could have caught it, because every test seeded a row whose fields were
the length the test author typed. The defect lives entirely in the *distribution*
of real values, and the distribution is the one thing a fixture does not carry.

**Pattern: tests establish that an instrument is correct; only a real run
establishes that it is usable.** Budget one live run before depending on an
instrument for a timed observation, and treat its output size and shape as part
of the result. "It passed its tests" and "it can be read at 03:40Z over ssh" are
different claims.

The fix generalises past this script: when a renderer's layout is derived from
its data, **one pathological row is a denial-of-service on every other row**.
Cap the cell, count the caps, and say the count -- eliding silently would have
traded an unreadable table for a misleadingly complete-looking one, which is
worse.

---

## 2026-09-07 - The check and the instrument for the check are two deliverables, and only one of them gets planned

The open item said: *"confirm the sweep fired; then the `unmatched_items`
collapse."* Written by a session that had just read those numbers, so the
reading was obviously possible. It was not: there is no `unmatched_items` query
in the inspector's whitelist, no API route serving it, and the script that reads
it was not in the image. The earlier session had got its numbers by smuggling
ad-hoc SQL over `flyctl ssh`, which the inspector's own ruling forbids in those
words -- and the item it wrote inherited the capability without inheriting the
means.

**Pattern: an item that names a reading must name the command that produces it,
and that command must be one that exists on the machine the reading happens on.**
"Check X" is not a plan; `flyctl ssh console -a … -C "…"` is. The gap is
invisible to the author precisely because they just did it -- by a route the
next session does not have, or should not take.

Two things make this recur here. A one-off route (ad-hoc SQL, a laptop-side
script, a browser session) leaves no trace in the plan that it was one-off. And
a **timed** observation converts the gap from an inconvenience into a miss: the
instrument has to be built, tested, committed, CI'd and deployed before the
event, and discovering the gap at the event means not taking it.

Corollary that is worth more than the lesson: the repo already had the fix for
the *class*. `TestTheSshInvokedScriptsSurviveDockerignore` derives the
`.dockerignore` allowlist from each script's own documented invocation, so a
script that declares `/app/scripts/<name>.py` **cannot** be absent from the
image without CI going red. The right response to "the instrument was missing"
was not to add the instrument; it was to add it *through the derivation*, so the
sixth occurrence is impossible rather than merely less likely.

---

## 2026-09-07 - A screen that names one failure lets every other failure wear the quiet's clothes

`WindowBanner` chose its headline by testing `last_look_outcome === "refused"`
by name and letting every other outcome fall through to the branch for "the
loop is alive and declining ... it looks identical to a quiet market from
here." The vocabulary had five outcomes. `failed` -- the upstream odds API
answering 4xx/5xx -- was added to it on 2026-08-25 with the sentence "none of
the other four could say this", and the banner was never taught it. So an
Odds API 401 on the first NFL slate would have rendered as a quiet market,
with the true reason in the small print two lines lower.

The global-cap stop was the same shape one layer down: `runner` recorded it as
`SKIPPED` ("the pass chose not to look") when the vocabulary's own comment
defines `REFUSED` as "the budget declined -- *we* stopped." The screen's
`refused` words were right for a spent day and never fired on one.

**Pattern: an if-chain that names the failures it knows and ends in a
reassuring default classifies every failure it does not know as
reassurance.** Adding an outcome to the vocabulary is not finished when the
writer can write it; it is finished when every reader has a branch for it, and
the test to write is the one that feeds the new outcome to each reader and
asserts it does not land in the default. The default branch should describe
the *absence of information*, never a specific benign world -- "nothing
swept and no reason recorded" is honest; "a quiet market" is a guess dressed
as a finding.

Corollary: grep for every reader of an enum when a member is added
(`last_look_outcome` had three: the tone predicate, the banner, the type), and
count the branches in each. A reader with fewer branches than the enum has
members has a default that is doing work nobody assigned it.

---

## 2026-09-06 - Two true docstrings, one false conjunction

`decide_sweeps` said bootstrap is *"capped at ... one attempt per sport per
budget day"*. `runner` said a failing sport *"never enters `last_sweeps` and
never starts pacing itself"*. Both were accurate, both were written
deliberately, and both were in files a reader would consult.

Their conjunction is the bug: the cap **is** `sport not in last_sweeps`, and
`last_sweeps` is built from a predicate requiring `http_status < 400` — so it
bound on success and not at all on failure. A failing sport retried every pass
all day: **700 credits in 2h54m**, uncapped by the attention slice because
bootstrap carries its own trigger.

The tell was sitting in the first docstring's own next clause — *"would
otherwise bootstrap on every pass and drain the day's credits in an hour"* —
which was not a description of the hazard avoided but an accurate description
of what still happened.

**Pattern: a bound stated in one file and undermined in another is invisible to
every reader of either.** Neither docstring is wrong; no review of either would
find it. What finds it is asking, of a stated cap, *what predicate implements
this, and what is that predicate's failure case* — because a cap keyed on a
success-only signal does not bind on failure, and failure is when a cap
matters.

Corollary for writing them: when a docstring names a hazard it is preventing,
state the mechanism, not just the outcome. "Capped at one attempt per day"
survives the mechanism changing underneath it; "capped by `last_sweeps`, which
only records successes" would have been self-refuting the day it was written.

---

## 2026-09-06 - A caveat loses to the variable name it sits under

`test_the_worst_case_day_with_the_fall_through_stays_inside_the_cap` computed
`384 + 300` and asserted `worst_case == 684, "fly.live.toml's worst-case row"`.
Its own docstring, three paragraphs further down, said: *"**What this does not
count**, deliberately: the slot planner and the prop tail, which draw on the
same 700."*

Both statements were true. The caveat was accurate, deliberate, and written by
someone who had thought about exactly this. And the number still propagated as
a worst case into `fly.live.toml`, into `timing.py`'s comment block, and into
`CLAUDE.md` — where a later session read it, reasoned about "16 credits of
headroom", and had to be corrected. The omitted term was **67.0% of actual
spend**: larger than either term that was counted.

**Pattern: when an identifier and its caveat disagree, the identifier wins.**
A name is read every time the value is used; a docstring is read once, by
whoever is editing the function. Anyone quoting the number downstream sees only
the name. So a caveat cannot make a misleading name safe — it can only record
that someone noticed.

The fix is to rename, not to explain harder. `capped_terms` invites the
question "what is uncapped?"; `worst_case` closes it. And where a partial sum
is genuinely worth computing, **assert what it is NOT**: the replacement test
now also asserts that one NFL Sunday's kickoff-window demand exceeds the gap
between the sum and the cap, so no reader can treat that gap as spare.

**Corollary for prose that quotes a number from code**: three files quoted 684
and none of them carried the caveat, because a caveat does not travel with a
figure. If a number is not safe to quote alone, it is not safe to publish.

---

## 2026-09-06 - A test that restates the code's own formula agrees with the code whatever the code says

`DUE_WINDOW_MS`' comment said *"a sixty-minute window at a ten-minute refresh
is six calls, so a cluster costs `6 x sweep_cost`"*. It is seven:
`calls_remaining` is `1 + left // refresh_interval_ms`, the opening call is the
`1`, and six is the count of *refreshes*. Every projection built on that
sentence understated each cluster by 4 credits.

The value was under test the whole time:

```python
span = slot.fire_until_ms - slot.fire_from_ms
assert slot.calls_remaining(slot.fire_from_ms, REFRESH_MS) == (1 + span // REFRESH_MS)
```

That assertion re-derives `calls_remaining` from `calls_remaining`. It passes
on 6, on 7, and on 700. It pins the *shape* of the formula and nothing about
its magnitude, so it could never contradict a wrong number quoted in a comment
a hundred lines above it.

**Pattern: an assertion written in terms of the code's own expression tests
that the expression is stable, not that it is right.** Both forms are worth
having, but only one of them can catch prose. Where a constant is quoted
anywhere a human reads — a comment, a deploy file, a budget projection — **pin
the literal value in a test as well**, and say in the docstring that the test
exists to make the comment fail with the code.

The tell is that the assertion contains the same operators as the
implementation. If you can derive the assertion by copy-pasting the function
body, it is a tautology with a fixture attached.

---

## 2026-09-06 - A guard that substring-matches an element name is green on a renamed element

A new test pinned that four screens still render a control Joe had asked for,
by asserting `"<RecordParlay" in source` for each file. It was then mutated to
prove it could fail. The mutation renamed the element to `<RecordParlayX` --
and the test **passed**, because the old name is a prefix of the new one.

The screen in that state rendered nothing: React treats an unknown capitalised
element as an undefined component. So the guard reported healthy over exactly
the failure it existed to catch, and would have gone on doing so for any
rename, any suffix, any typo that extends rather than shortens the name.

**Pattern: a containment check on an identifier is not an identity check.**
Any `"<Name" in source`, `"def foo" in source`, `grep NAME` guard passes on
`NameX`, `fooBar`, `NAME_OLD`. Where a guard asserts that a specific symbol is
present, assert its **boundary** too -- `re.search(r"<Name(?=[\s/>])", ...)`
for a JSX tag, `` for an identifier. The failure is silent and it is in the
flattering direction: the guard says yes.

**And this is why the mutation is not optional.** The rule in `CLAUDE.md` --
disable the guard and watch it fail -- caught this in one run. What nearly
defeated it is that the *first* mutation attempt was also badly chosen: a
lazy `s.replace("<RecordParlay", "<RecordParlayX")` is a plausible-looking
mutation that happens to be invisible to the very check under test. **A
mutation that leaves the asserted substring intact tests nothing.** Choose the
mutation by asking what the guard reads, then breaking that.

---

**Merged 2026-09-08 with the 2026-09-05 lesson on the same defect** (`<ManualTicket` surviving as a prefix of `<ManualTicketX`, and the needle found in the comment that explains the component): anchor the identifier boundary, and strip comments before matching, or the guard is green on exactly the rename it exists to catch.

## 2026-09-06 - A hand-typed sha is a fabricated sha, and noticing that it looks wrong is not the same as checking it

A deploy was given `-e GIT_SHA=c9739cc7`. The commit was `c9739cc8...`. The
eighth character was supplied from nowhere -- `git log --oneline` prints seven,
and one more was added to make it look like a longer prefix. Two live instances
then served, from `/api/health`, an identifier **matching no object in the
repository**.

The repo's own session-start ritual is to compare `/api/health`'s `git_sha`
against `origin/main` before believing anything is deployed. A truncated sha
still answers that question. A **wrong** one cannot: it does not match, and it
does not match anything else either, so the check fails with no way to tell a
bad deploy from a bad string.

**The anomaly was seen and rationalised, which is the part that generalises.**
The oddity was noticed at the time -- earlier entries quote 40 characters, this
one had 8 -- and reported as "the short form; it still prefix-matches; not
worth a redeploy to lengthen a string." Every clause of that was wrong, and it
was produced *because* the anomaly was noticed: the explanation was reached for
in order to dismiss the observation. It survived until `gh run list` happened
to print `headSha` beside it and the eighth character disagreed.

**Pattern one: never hand-type an identifier a command will emit.** Substitute
the command -- `-e GIT_SHA=$(git rev-parse HEAD)` -- so the value cannot be
approximated. Anything copied by eye from one representation (short sha, log
line, screenshot) into a field that will be compared for equality is a
fabrication waiting to happen, and shas are the worst case because every
character is equally meaningless to a reader and a wrong one is invisible.

**Pattern two, and it is the reusable half: an explanation produced to dismiss
an anomaly must be tested, not accepted.** "It is the short form" was a
hypothesis with a thirty-second check behind it (`git rev-parse`), and the
check was skipped precisely because the hypothesis felt sufficient. When you
catch yourself explaining away something that looks off, the explanation is a
prediction -- verify it. Same family as the entries about a guard that asserts
the product rather than the producer: a claim that closes an investigation is
the one most worth opening.

---

## 2026-09-06 - A section truncated by `head` looks exactly like a section with no rows, because the header prints before the data

A new inspector query prints two sections: what the odds feed BOUGHT, and what
the strategy CONSUMED. Its first live run was piped through `head -30` to keep
the output small. The pipe cut between the two, so section B rendered its title
and its column header and then stopped.

That was read as "`fair_prices` is empty on live" -- and acted on, as a
possible bug in code merged and deployed an hour earlier. A direct count then
reported **7,680,002 rows**. Re-running without the pipe printed section B in
full.

The truncation was indistinguishable from the finding because **a table header
is emitted before the rows it describes**, so "the query returned nothing" and
"the output was cut here" produce byte-identical prefixes. Every convention
that makes tabular output readable -- title, rule, column names, then data --
also makes an empty result and a severed one look the same.

**The tell was present and not read: the trailing `N rows` line.** Section A
ended with `13 rows`; section B ended with nothing at all. A renderer that
reports its own row count distinguishes the two cases, and that is the thing to
look for before believing an empty section.

**The pattern: when a tool's output is truncated by the reader's own pipe, the
absence it appears to show is the reader's, not the system's.** Before treating
"nothing came back" as data, confirm the output ended where the *program*
ended -- a terminal marker, a row count, an exit line -- rather than where the
pipe did. Same family as the `flyctl ssh` exit-code entry: judge by the output,
not by the frame around it.

It is worth a lesson rather than a note because of what it nearly caused. The
false reading contradicted a measurement taken hours earlier by another agent,
and the reflex was to doubt the measurement. **A contradiction between a fresh
read and a recorded one is a claim about the instrument at least as often as it
is a claim about the record**, and the cheap check is to re-take the fresh read
by a second route before revising anything.

---

## 2026-09-06 - A scripted edit meant to change a few bytes rewrites every line ending in the file, and a normal diff cannot show it

A three-line Python helper replaced one string in `backend/api/routes.py`:
`read_text()`, `.replace(old, new)`, `write_text()`. It changed the two bytes
it was asked to. It also silently rewrote **all 3,924 line endings in the file
from LF to CRLF**, because Python's text mode is symmetric: `read_text`
translates `\r\n` to `\n` on the way in, and `write_text` translates `\n` back
to the platform's ending on the way out. On Windows that is `\r\n` for every
line, whether or not the line was touched.

**The corruption is invisible where you would look for it.** `.gitattributes`
here is `* text=auto`, so git normalises on staging and `git diff --stat`
reported the honest 31 changed lines with no hint that 3,893 others had been
rewritten on disk. The only signal was a one-line warning git prints and a
session scrolls past. What catches it is a tool that reads bytes: `file` names
the terminators outright, and a `diff` against a copy taken before the edit is
exact.

This matters beyond tidiness in this repo: a CRLF that reaches the Linux
container makes `#!/usr/bin/bash\r` fail with "no such file or directory"
naming a file that plainly exists — the reason `.gitattributes` opens with a
comment about it.

**The pattern: a scripted edit's blast radius is the whole file, not the
region you matched.** Any transform that reads a file into a string and writes
the string back re-encodes everything — line endings, and equally a trailing
newline, a BOM, or an encoding guess. Do byte-level work for byte-level
intent: `read_bytes()` / `write_bytes()` with `bytes` patterns, which cannot
translate anything it was not asked to. And **read the target's endings before
writing to it** rather than assuming the repo is uniform — `tasks/lessons.md`
is CRLF in this working tree while `tasks/NEXT.md` is LF, so a helper that
"works" on one silently rewrites the other.

The same asymmetry is why this is worth a lesson rather than a note: the edit
that introduces it is the mutation step of *verifying a guard*, which is
otherwise the most careful thing a session does. Take a copy first, restore
from the copy rather than re-editing, and `diff` against it.

---

## 2026-09-06 - A date-triggered falsifying check must be dated from the event's END, and from a looked-up calendar rather than a remembered one

The partner set a check: read `parlay_positions` on **2026-09-09**, and if it
is still 0 "after an NFL opening weekend", ADR 0078's `/hedge` route becomes a
deletion candidate. It carried through two session entries unquestioned,
including one written by the session that was about to act on it.

**2026-09-09 is the Wednesday the season opens.** The 2026 opener moved off
its usual Thursday, and Week 1 does not close until Monday 2026-09-14. A read
on the 9th would have found 0 before a single NFL game had finished, and the
rule says a 0 kills the feature -- so the check as written was a scheduled
deletion of a working route on evidence that could not yet exist. It failed in
the one direction a falsifying check must never fail: it made refutation
arrive early and for free.

Two separate errors, and the second is the one that generalises:

- The date was set from the **start** of the window rather than the end. A
  check whose predicate is "still 0 *after* X" has exactly one correct date:
  the first day after X finishes.
- The date was set from a **remembered** calendar. "Opening weekend" is a
  phrase, not a date, and the league had moved the opener. The same session
  that acted on it also mis-stated the current day of the week in its own
  handoff prompt, from the same source: recall standing in for a lookup.

**The pattern: a pre-committed check names an EVENT; the date is derived from
that event's end, and the derivation is looked up at the moment the check is
written, not recalled.** Write the event beside the date so a later reader can
re-derive it -- "2026-09-15, the first morning after NFL Week 1 closes" can be
checked in thirty seconds and "2026-09-09" cannot. Same family as the
file:line citations in `CLAUDE.md`, and for the same stated reason: a future
session can re-check a reference cheaply and cannot re-check an adjective.

The cost of getting this wrong is asymmetric and that is why it earns a
lesson. A check dated too late merely waits. A check dated too early **fires**,
and a pre-registered rule is designed to be obeyed without re-litigation --
which is exactly what stops anyone noticing the date was wrong.

---

## 2026-09-05 - A stub that assigns over a property tests the assignment; the SDK's own parser is the only thing that runs the SDK's parsing

Two test files stubbed an LLM response with `self.parsed_output = parsed` on a
bare object. `parsed_output` on the real type is a **property** that walks the
message's content blocks for the first one carrying a parsed value. So the
property never ran, no content block was ever constructed, and the JSON was
never validated against our own output model -- the tests asserted that
production code can read an attribute the test had just set, and would have
passed against a client library whose parsing was completely broken.

Rebuilding the object the way the library builds it -- validate the wire dict
into the library's message model, then call the same parse helper the client
calls -- made three things run for the first time: the library's schema
validation of the envelope, its parsing of the payload against our model, and
the property. The first draft of the fixture was then **rejected** for
omitting a required counter nested two levels into the usage block, which is
exactly the class of error a hand-written stub carries forever.

**Pattern: when you stub a third-party response, construct it through the
library's own constructor or parser, never by setting attributes on a fake.
Anything computed -- a property, a validator, a discriminated union -- is
precisely what a hand-built stub skips, and it is precisely the part you did
not write and therefore cannot reason about.** The tell is a stub that assigns
to a name you never see assigned in the library's own source.

**And a fixture built from the library is not a capture, so say which you
have.** The library's models are a *belief* about the wire; a fixture derived
from them cannot falsify that belief, and if the library drifts from the
service the fixture drifts with it and every test stays green. It is a much
better stub and it is not evidence about the wire. Record the difference where
the fixture lives, or the next reader closes the gap on paper.

## 2026-09-05 - An error handler ordered after a call that raises is not an ordering, it is dead code with a comment explaining it

Production code read: call the client's parsing helper inside `try`, then
check the response's `stop_reason` for a safety refusal "before touching the
parsed output". The comment described a real hazard and a sensible order. The
order never happens. The helper parses every content block with no regard for
`stop_reason`, so a refusal -- whose content deliberately does not match the
schema -- raises inside the call, is caught by the broad `except` above, and
the refusal branch below is unreachable. The consequence landed on the meter:
the request succeeded and was billed, and the token counts live on the
response object that was never returned, so the row settles with no usage.

It was found by writing a test to what the comment claimed and watching it
fail.

**Pattern: a guard placed after a fallible call only guards if that call can
reach it. Before trusting an ordering comment, ask what the preceding line
does on the input the guard is for -- and when the guard's own input is the
thing that makes the preceding line throw, the guard is decoration.** The
fix is not always to move the guard: reproducing the library's request
transformation to get the object earlier would have been a second
implementation of the library. Catching the specific exception apart from the
generic one, and recording what is unrecoverable and why, is the honest floor.

**The corollary about broad excepts.** `except Exception` around a call that
does two jobs -- transport and parsing -- collapses "we never spent anything"
and "we spent money and got something unusable" into one log line. Those are
different facts to anyone counting money. Split the handler by the distinction
that matters downstream, not by what is convenient to catch.

## 2026-09-05 - Audit each item of a list you were handed; "three of X" is a claim about all three

A brief named three symbols as instances of one defect -- a predicate with a
second, live spelling -- and recommended acting on all three. Checked
individually: one was the defect; one was production-unreached but is the
reader the test suite uses to observe a live writer; one was a declared
instrument whose own docstring records that nothing calls it and why. Acting
on the list as given would have deleted or "fixed" two things that were
already correct, and the wrongness was invisible from the list itself because
the list was a summary.

The same audit found what the summary had missed: two of the three carried a
*different* defect -- docstrings asserting states that had since changed --
which is worth more than the framing that led there.

**Pattern: a list of N instances is N claims. Verify each against the code
before acting on any, and expect the ones that fail verification to be
carrying some other defect instead -- whatever made them look like the pattern
usually is something.** Report which held and which did not, in the record,
because the next reader inherits the list and not the check.

**And the distinction that keeps recurring: a second implementation is a
cross-check when it is guarded and a bug when it is not.** The same repo held
a deliberate third spelling of the same formula -- in a script that imports
nothing from the package by design, with a test asserting the two agree on
every value including the refusals. That one is load-bearing. The unguarded
inline one, in the route that actually served the number, was the defect.
Count guards, not spellings.

## 2026-09-05 - Reading the aggregates to scope a measurement is what disqualifies them from being its result

A question was worth registering, so before writing the registration I read
the record to find out whether it could be answered at all: the row counts,
the win/loss split, the money staked, the fee total, the status breakdown, the
join coverage. All of it went into the brief, honestly labelled as already
seen. The pre-registrar then had to demote **every one of those quantities to
a transcription with no p-value**, because a threshold applied to a number the
author already knows is not a threshold. The single finding I had flagged as
most actionable was in that set and could no longer be tested at all.

The scoping was not wrong to do -- without it the registration would have
fixed a rule for a population that turned out not to exist. What was wrong was
the *order*: I read the outcome-bearing columns in the same pass as the
structural ones, when only the structural ones were needed to decide whether
the question was answerable.

**Pattern: split the pre-registration reconnaissance in two. What EXISTS --
table names, column names, row counts, date ranges, join cardinality, null
coverage -- is safe to read and is what tells you whether a question can be
asked. What HAPPENED -- outcomes, rates, sums, splits by result -- is the
measurement, and reading it to decide what to measure spends it.** If you need
a quantity from the second group to choose a rule, that is a sign the rule
should be chosen by someone who has not read it.

The corollary is about handing work to a registrar: **everything you put in
the brief, you have seen.** A brief is a disclosure, not a neutral summary. It
is better to write "I have not looked at the result column" and be right than
to paste a helpful table.

## 2026-09-05 - A `--` comment inside a CREATE TABLE column list breaks DROP COLUMN, and the failure names a table the change never touched

A new column arrived with its reasoning as a `--` comment between the other
columns, inside the parentheses. SQLite reconstructs a table's stored SQL text
when `ALTER TABLE ... DROP COLUMN` runs, and the comment survived into text
that no longer parses. **Thirty-three migration wind-back steps went red**,
including versions written years of commits before this change, with
`sqlite3.OperationalError: error in table desk_attention after drop column:
incomplete input`.

**Pattern: prose about a column goes ABOVE the `CREATE TABLE`, never inside
the parentheses, for any table a migration can drop a column from.** SQLite
stores the literal CREATE text and re-parses it, so a comment is not
decoration there -- it is data the engine has to survive. The tell that this
is what happened is a failure list far wider than the change: a schema file is
applied on every open, so one unparseable table breaks steps that have nothing
to do with it.

## 2026-09-05 - When a guard asserts the mechanism instead of the property, the fix that changes the mechanism looks like a regression

Two guards went red for changes that did not violate what they were protecting.

One asserted `"body: {}" in source` to mean *"no client-supplied clock reaches
the backend"*. The empty body was how that was true, not the rule itself, so
giving the route a body carrying an inert descriptive field broke the
assertion while the actual property was untouched. The other pinned that a
`priceAlreadyVisible` prop was passed bare, as a way of saying the flag was
unconditional -- and the fix was to make it conditional.

Both are the same shape as the copy lesson already in this file (*"copy that
names a condition to wait for is falsified by fixing the condition"*), one
level down: a test can name a condition too.

**Pattern: write the assertion at the level of the property, not the
implementation that currently satisfies it. "No field named like a timestamp
appears" survives a body being added; "the body is empty" does not.** When a
guard goes red for a change that plainly does not violate its docstring, the
guard is the thing that was wrong -- fix it in the same commit and say so,
rather than contorting the change to keep a proxy green.

**And strip comments before searching, again.** The corrected version of the
first guard immediately found `now_ms` and "timestamp" in the route's own
docstring, which exists precisely to explain that neither value is forwarded.
That is the second time in one day that a guard read the prose about the
property instead of the property. Assume every literal you grep for appears in
the sentence explaining it.

**Merged 2026-09-08 with an instance:** `assert str(CONSTANT) in text` passes just as happily on a typed digit, so it does not test that the text is sourced from the constant. A guard on production copy must read the producer, not the number.

## 2026-09-05 - Test at the level the defect lives; a substring test cannot tell a mention in a live branch from a mention in a dead one

A component had three branches and two of them returned early, dropping a
field the server had carefully worded. Every source-text guard over that file
passed: the field is named in the file, so `"staked_refusal" in source` is
true, and it stays true no matter how many branches never reach it. **The
defect is not "is this field mentioned" but "does this payload produce this
sentence", and only one of those questions can be answered by reading text.**

The fix was to render the real component with real payloads. Node strips
TypeScript types but does **not** transform JSX, so the route is: compile the
`.tsx` with the repo's own `tsc --jsx react-jsx` into a temp directory, render
with `react-dom/server`, strip tags, assert on the text. Two mechanical
details that cost the most time and will again:

- **ESM resolves bare specifiers by walking up from the importing FILE, not
  from `cwd`.** A module compiled into a temp directory cannot see the
  project's `node_modules` however the subprocess is launched. Resolve the
  packages with `createRequire` against the real `package.json` and map them
  in a `registerHooks` resolve hook.
- **`tsc --moduleResolution bundler` emits extensionless relative imports**
  (`./lib/api`), which the bundler resolves and node does not. The same hook
  retries a relative, extensionless specifier with `.js`.

**Pattern: choose the test's level from where the defect can hide, not from
what is convenient to assert. If the bug is reachability, the test must
execute; if it is wording, text will do.** A stub is legitimate at this level
only when it replaces something that is not under test -- here a constant and
a type -- and never the component whose branches are the claim.

## 2026-09-05 - A link is a claim about its destination, and only the destination knows whether it can keep it

A search result was given a link to the game screen, labelled "See the price
and what the desk knows". The screen it points at renders "the recorder never
priced this ticker" when there is no detail row, and refuses the ask outright
when it is stale -- the two states the very same commit had just taught the
hand-bet ticket to stop lying about. The label reintroduced the defect one
level up, in the same change that fixed it, and was caught only by asking what
the destination looks like in its unhappy states.

**Pattern: label a link with where it goes, not with what it will show. The
linking surface cannot know the destination's state -- that is what makes it a
different screen -- so any label promising content is a claim the linker is not
entitled to make.** The tell is a label containing a noun the destination
renders conditionally: "see the price", "read the verdict", "view your
balance". Name the place instead and let it speak.

The general form is worth more than the instance: **a fix that removes a false
claim from one surface should be checked against every surface that points at
it**, because the claim tends to have been copied outward from the same
optimism.

## 2026-09-05 - A deadness grep scoped to the source directories misses the callers that matter most, because the loudest ones live outside them

Seven symbols were audited for deletion by grepping `backend/` and `scripts/`
and reporting which had no reference but their own definition. Seven came
back clean and were written up as "real dead code". One of them,
`runner.reset_walk_alarm`, is called by an **autouse fixture in the repo-root
`conftest.py`** -- before and after every test in the suite, with the
fixture's own docstring naming the two tests that fail without it. The grep
did not miss a subtle reference; it never looked at the file, because
`conftest.py` sits at the root and the scope was the two source trees.

Two more were wrong for reasons the same scope hid: a function whose only
callers are operator scripts read as dead from a runner-centric view, and a
deliberately dormant money guard whose own docstring already recorded that it
has no caller and why.

**Pattern: scope a deadness grep to `git ls-files`, never to the source
directories. The high-value callers of production code are disproportionately
the ones outside `backend/` -- root `conftest.py`, fixtures, operator scripts,
CI config -- and those are exactly the ones a "where is this used in the app"
instinct excludes.** Before proposing any deletion, run the search over every
tracked file and read each hit, and treat a symbol whose docstring explains
its own callerlessness as documented rather than dead.

**The naming half, which is the durable part: "dead" and
"production-unreached" are different properties and only one of them licenses
deletion.** A symbol can be unreachable from the deployed entry point and
still be load-bearing for the test suite, for an operator script, or as a
declared hook for a capability that is off today. This repo already has a
mechanism for the distinction -- `DISPOSITIONS` in
`tests/test_has_callers.py` -- so the honest output of an audit like this is a
disposition, not a delete list. Nine candidates went in; three survived, and
the six that did not were each rejected for a different reason.

**Merged 2026-09-08 with the depth half:** named, import-reachable and called are three properties, and a one-level "has a caller" walk is satisfied by a referrer that is itself dead. State a guard's walk depth.

## 2026-09-05 - A clean merge is a statement about text; two lanes can each be right about a file and wrong about each other

Two lanes edited one test file the same day. Their hunks were five lines
apart and did not overlap, so `git merge-tree` reported zero conflicts and
the merge was clean. It was also wrong: one lane had re-pointed an
anti-vacuity pin at the module it believed called a symbol, while the other
had already moved that call into a new module. Neither diff touched the
other's line, so there was nothing for git to notice, and the pin would have
asserted a call site that no longer existed -- passing or failing for a
reason unrelated to what it was written to guard.

**Pattern: git conflicts on lines, not on claims. When two lanes touch one
file, the question is not "do their hunks overlap" but "does either one
assert something about the other's files". Diff each lane against the other's
tree, not just against the base.** The three checks that would have caught
this in seconds: grep each lane's added lines for paths the other lane
created, renamed or emptied; run the merged tree's own guards rather than
each lane's; and prefer a pin that reads its target from a shared constant
over one that types the path twice, so a move breaks one place instead of
two.

**Corollary, and it is the cheaper half: a reason written about who owns a
file today expires today.** The same merge turned up three sentences of the
form "X keeps its name because file Y names it and Y is the other lane's this
session". Every one was false within the hour. A justification that names a
lane, a session or an afternoon is a scheduling note wearing a decision's
clothes -- write the reason that survives the merge, or the next reader
inherits a decision with no reason at all.

# The pattern index

Every lesson ever written, newest date first, one line each. The full text of
each is in the linked archive file, unchanged; the sections marked *in this
file, above* are the ones not yet archived. Regenerate it from the headings in
the same edit as the entry — an index that is not is stale by one entry
immediately and by dozens within a week.

### 2026-09-08 — in this file, above
- A spine that records its own corrections inline grows without bound, and the corrected fact is the only part a session needs
- "This route has no guard" is a claim about the whole dependency chain, not about the route body
- A guard that reads the code but not the decisions is half a guard
- Removing a brake server-side leaves it on the screen, and that direction of the mismatch is invisible
- A count or a "not yet" copied into a new session entry is a present-tense claim from a past reading
- A consumer that restates a predicate is not covered by the test that pins it
- A mechanism that relabels spend is not a saving
- A mutation that stays green has two readings, and only the code tells you which
- A capture script that reads the environment captures the laptop, not the deployment

### 2026-09-07 — in this file, above
- "It might be slow" is not a tolerance; find the bound
- "Expect the count to fall" is a claim about a delete that may not exist
- An instrument is not verified until it has been run against the real data once
- The check and the instrument for the check are two deliverables, and only one of them gets planned
- A screen that names one failure lets every other failure wear the quiet's clothes

### 2026-09-06 — in this file, above
- Two true docstrings, one false conjunction
- A caveat loses to the variable name it sits under
- A test that restates the code's own formula agrees with the code whatever the code says
- A guard that substring-matches an element name is green on a renamed element
- A hand-typed sha is a fabricated sha, and noticing that it looks wrong is not the same as checking it
- A section truncated by `head` looks exactly like a section with no rows, because the header prints before the data
- A scripted edit meant to change a few bytes rewrites every line ending in the file, and a normal diff cannot show it
- A date-triggered falsifying check must be dated from the event's END, and from a looked-up calendar rather than a remembered one

### 2026-09-05 — in this file, above
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
