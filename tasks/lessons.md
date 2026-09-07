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

**Split 2026-09-05, at 229,412 bytes — 87.5%.** Every 2026-08-27 and
2026-08-26 lesson moved to `archive/lessons-2026-09-05.md`, verbatim, leaving
161KB — **61.5%**. Taken at 87.5% rather than at the 90% trigger, and on the
same reasoning the 2026-08-31 split records: clearing to just-under-the-line
buys one more split rather than several, and this file gained three lessons in
one session.

**The split was proved rather than assumed.** The archive's content was
reassembled with the two index lines restored and the result measured at
**229,412 bytes — the pre-split size exactly**. A split is a claim that
nothing was lost, and that claim is cheap to check and expensive to be wrong
about; the index lines moved in the same edit, because moving entries without
moving their index is a data loss with a table of contents.


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

## 2026-09-04 - An absence pin that greps for a literal name finds it in `__pycache__`, because CPython folds `"a" + "b"` at compile time

A test pinned that a deleted symbol appears nowhere under `tests/`. It failed
on a clean tree: the name was still in three `.pyc` files, and not because the
sources were stale — CPython constant-folds adjacent string literals, so the
pin's own `"an" + "AutomaticBuyIsComing"` was compiled into the bytecode of
the file asserting the name's absence. The pin was finding itself.

**Pattern: a guard that searches for a literal must not contain that literal
in a foldable form. Build the needle at run time (`"".join((...))`), and scope
the search to source suffixes rather than to a directory. A guard whose first
finding is itself gets deleted rather than believed.**

## 2026-09-04 - A rate limit is a pause, not a loss: an agent with a worktree resumes with its context

Three lanes died mid-task on a model limit. Two still had their worktrees and
`SendMessage` resumed both from exactly where they stopped, one of them
mid-edit with uncommitted work; only the third, which had not yet created a
worktree, had to start over. Re-running the two from scratch would have
repeated an hour of reading.

**Pattern: on a killed agent, check `git worktree list` before relaunching.
If the worktree exists, resume the agent and tell it to read `git status` and
`git diff` first rather than redoing finished work. Relaunch fresh only when
there is no tree to come back to.**

## 2026-09-04 - "The largest contributor" is a set until proven a singleton, and `max()` on a dict picks a member silently

A registered leave-one-day-out downgrade said to drop "the largest-contributing
budget day". Two days tied. `max(per_day, key=per_day.get)` returned the
earlier one by insertion order, whose removal left the verdict standing; the
other tied day held 3 of the 8 inside-visit sittings and dropping it did not
clear. The registered verdict was `UNRESOLVED — CONCENTRATION`, and the first
run printed `PRESENCE GAP REFUTED` with a leave-one-out line that read as a
pass. The audit caught it; nothing in the code or the fixtures could have,
because every fixture had one sitting per day, where the error vanishes.

**Pattern: a rule that names "the largest" of anything must say what happens
on a tie, and the conservative reading is to apply the rule under every tied
candidate. In code, never resolve a definite article with `max()` over a
mapping: take the maximum value, collect every key that attains it, and pin
the tie in a test whose tied members give different answers.**

## 2026-09-04 - A precondition written as the failure of one named mechanism does not fire when a different mechanism fails the same way

The presence registration's C4 said the exclusion was unexecutable "if the
inspector cannot emit the orders' `kalshi_order_id`s". The inspector emitted
them perfectly well; what it could not emit was the *fills* side of the join,
and C4's letter did not fire while its purpose did. The analyzer refused on
the purpose and the amendment re-worded C4 on the capability ("establish that
no fill descends from the order, or which fills may").

**Pattern: write a precondition on what must be established, never on the
route you expect to establish it by. A route-shaped precondition is "one
predicate, two spellings" inside a single document: the spelling in the rule
and the spelling in the mechanism drift the first time the mechanism is not
the one that fails.**

## 2026-09-04 - A date read off a local clock is a different date; every registered instant is UTC

A blind amendment declared four live captures inadmissible because they were
"taken 2026-09-03, before `W_end`". They were written at 01:13-01:14Z on
2026-09-04. The author was in America/Los_Angeles, where it was still the
evening of the 3rd. The registration's own integer for `W_end` had the same
class of defect in the other direction: `1788652800000` is 09-06, not the
09-04 the text names five times.

**Pattern: an instant in a registration is an epoch integer or an ISO string
with a `Z`, and a claim that a read was early or late is checked against the
file's own UTC write time, never against the day the author remembers it
being. When a date and its integer disagree, the one that was argued for
outranks the one transcribed from it — and both get written next to each
other so the next reader can see them disagree.**

## 2026-09-04 - A fixture set that only ever states the deployed value cannot detect a hardcoded copy of it

Every `sweepTone` fixture implied a 900 s cadence, so `2 * 900_000` and "two
intervals of the published cadence" were indistinguishable to the whole
suite, and a hardcoded second spelling of the stall threshold lived beside a
test file that executed the real function. The mutation that finally
separated them was a fixture with a cadence that was not 900.

**Pattern: when a value is meant to be a fact read from elsewhere, at least
one fixture must move it and at least one mutation must restore the literal.
A test that passes on both the fact and its frozen copy is testing neither.**

## 2026-09-04 - Match a source anchor against the file's own line ending; a normalising reader will tell you it exists when a byte reader cannot find it

Two lanes and the main session each lost a round to the same thing: a patch
or mutation anchor with `\n` newlines reported "not found" on text visibly
present, because the file was CRLF and the reader that had displayed it
(`read_text`, `sed`) had normalised. The diagnostic contradicted the failure
because the diagnostic used a different instrument.

**Pattern: before concluding an anchor moved, check the line ending of the
file it is being matched against. Read bytes, detect `\r\n`, match on the
normalised text, write back in the original convention. And when a check
disagrees with a failure, suspect the check's instrument before the anchor.**

## 2026-09-04 - The session scratchpad is shared across parallel lanes

Two lanes each wrote a `mutate.py` to the same scratchpad directory within
minutes of each other; the second overwrote the first mid-run. No damage
either time, because both scripts pointed at their own worktrees — but the
failure mode is a lane running another lane's mutation against its own tree
and reading the result as its own.

**Pattern: anything a lane writes to shared temp space carries a lane-unique
prefix. A generic filename in a shared directory is a race, and the race is
silent when it is lost.**

## 2026-09-03 - A counter that emits on a cadence while a condition holds measures the condition's duration, not its occurrences

Attention-tagged odds buys fell 75 → 5 a day over five days and were read as
"the desk went quiet" — Joe had stopped opening it. The buy fires every ten
minutes *while a page is open*, so the count is attended minutes, not visits.
Visits per day were flat (5–8); dwell swung from 3 minutes to 5 hours with no
trend. The interview's lead question ("why did you stop opening it?") was
built on the wrong unit, and the fix for the real behaviour (short opens on a
screen that did not heal) was already shipped and switched off.

**Pattern: before reading a count as "how often", ask what event increments
it. A heartbeat, a poll, a cadence buy, a log line per pass — each counts
time-under-condition, and dividing by days gives dwell, not frequency. Count
the distinct starts if you want occurrences, and print both when the
distinction changes the sentence.**

## 2026-09-03 - "One predicate, two spellings" is an architectural fault, not a run of incidents

Four times now the screen has believed a different spelling of a predicate
than the code that acts on it: `next_call_ms` said a sweep was due while the
slice check refused it (#35); the panel promised "the hourly floor still
runs" after the floor was displaced (08-29); "once you stop looking" survived
the fix of its condition (08-29); and the cold-open watcher was gated on
`anAutomaticBuyIsComing` computed from a server snapshot taken *before the
page's own heartbeat existed*, so it asked whether a buy was scheduled using
facts that predate the thing that schedules the buy (09-03, 8 of 26 live
opens). Each was fixed as a string.

**Pattern: a predicate the screen renders must be evaluated from the same
facts, at the same moment, as the action it describes. When a server render
decides a client behaviour whose cause is the client's own presence, the
decision is stale by construction and must be re-taken client-side from
fresh facts. And a threshold that names "normal" (180 s) must be derived
from the thing's actual cadence (900 s idle), published by the side that
owns the cadence — never a literal on the reading side.**

## 2026-09-03 - A binder proposed from a remembered lesson is a hypothesis, and it enters the record only after the check

The partner proposed `RUNNER_INTERVAL_S = 900` as what bound the `/picks`
heal, from a lesson it already knew about the full pass. It dispatched the
check instead of asserting it; `run_quote_pass` calls `run_pricing_pass`
itself, the heal completes in 3–13 s, and the real binder was a 180 s stall
threshold in the frontend. The right finding was bigger than the wrong one.

**Pattern: pattern-matching a symptom to a known lesson produces a candidate,
not a cause. Name the check that would falsify the candidate and run it
before the sentence is written anywhere a later session will read it as
fact. The lessons file is a source of hypotheses, and its authority is
exactly why an unchecked one is dangerous.**

## 2026-09-03 - A screen promoted into a slot inherits the slot's traffic, not the old screen's fixes

`/picks` took the nav word "Picks" from `/slate` (ADR 0098). `/slate` mounts
the cold-open self-heal (`RefreshWhenPriced`); `/picks` was written fresh
from the block it promotes and shipped without it. Every source pin on the
new page passed, because every pin was about what the page must not carry.
The measurement that would have caught it had been taken the same day
(21 of 45 cold opens with nothing fresh, the feed buying 3.3 s later) and
was read as #20's spec, not as a check on the screen being shipped.

**Pattern: when a screen takes over a slot, diff it against the screen it
displaced for every mounted behaviour, not only for the content moved.
The fixes on the old screen were fixes for that slot's traffic, and the
traffic moves with the word in the nav. And a measurement of the state a
user meets is a test of the screen they will meet it on -- read it against
the build in flight before filing it as a spec for a later one.**

## 2026-09-03 - A gate that mounts a self-heal only when the screen is empty stops healing the moment it has anything

`/slate` mounts its watcher only if every row is suppressed and one is
stale (`slateIsUnpricedByTheClock`, `every`). One unsuppressed row and the
page stops watching -- so it re-renders exactly when it has nothing to show
and freezes the moment it has something. The attention/floor perversity of
2026-08-29 had the same shape: the behaviour meant to help was conditioned
on the state in which it helps least. Not changed on the Slate here (its
stated reason, not reflowing a list under a reader, is real); `/picks`
gates on `some` and says why.

**Pattern: when a helpful behaviour is gated on the screen being empty or
broken, ask what happens on the partial state. "Only when nothing works"
is usually a proxy for "only when it is safe to move the page", and the
two come apart the moment one row succeeds.**

## 2026-09-02 - A link to a screen is a claim that the screen exists, and the claim is pinned or it rots

Ticket #28 was answered "deep-link the digest to `/picks`" and #29 "the
footer label for `/board` is Refusals". Neither `/picks` nor a footer entry
for `/board` existed: ticket #8 had decided both a week earlier, been
ratified by Joe, and never been built, and the two later tickets were
written against the decision rather than the tree. The one-line change
for #28 would have sent a push notification to a 404 at the freshest
moment of the night, and the old root link already landed on the screen
that carried the ranked list -- a working link replaced by a more specific
broken one.

**Pattern: any string that names a route -- a notification URL, a nav href,
a redirect -- is a claim about the app tree, and it is pinned by a test that
walks the tree (`served_routes()`), not by the ticket that asked for it.
And a decided ticket is a build owed to a queue; when the Queue C sweep
runs, enumerate EVERY closed decision ticket against the tree, not the ones
that look unbuilt.** #8 was missed by a sweep that named four others.

## 2026-09-02 - "Restore the guard" with `git checkout` restores the COMMIT, not your edit

Verifying a guard by disabling it: edit the code, run the test, watch it
fail, restore. The restore was `git checkout -- file`, which put back the
committed version -- and the fix under test was itself uncommitted, so the
fix vanished with the mutation and the tree showed only the new test. The
tests had passed a minute earlier against the fix, so the loss was invisible
until the diff stat was read.

**Pattern: disable-and-restore must restore to the state you are about to
commit, not to HEAD. Either commit the fix first and mutate on top, or
restore by reversing the exact mutation (`sed` back, or `git stash` /
`git diff` of the fix). Read the diff stat before committing a guard
verification; a file missing from it is the fix that was reverted.**

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

### 2026-09-07 — in this file, above
- A screen that names one failure lets every other failure wear the quiet's clothes

### 2026-09-06 — in this file, above
- Two true docstrings, one false conjunction
- A caveat loses to the variable name it sits under
- A test that restates the code's own formula agrees with the code whatever the code says
- An item written from the shape of a known lesson is a hypothesis, not a finding
- A guard that substring-matches an element name is green on a renamed element
- `git checkout <file>` restores the INDEX, so it deletes uncommitted work while looking like an undo
- A hand-typed sha is a fabricated sha, and noticing that it looks wrong is not the same as checking it
- A section truncated by `head` looks exactly like a section with no rows, because the header prints before the data
- A scripted edit meant to change a few bytes rewrites every line ending in the file, and a normal diff cannot show it
- A date-triggered falsifying check must be dated from the event's END, and from a looked-up calendar rather than a remembered one
- `assert str(CONSTANT) in text` passes just as happily on a typed digit, so it does not test that the text is sourced

### 2026-09-05 — in this file, above
- A stub that assigns over a property tests the assignment; the SDK's own parser is the only thing that runs the SDK's parsing
- An error handler ordered after a call that raises is not an ordering, it is dead code with a comment explaining it
- Audit each item of a list you were handed; "three of X" is a claim about all three
- Reading the aggregates to scope a measurement is what disqualifies them from being its result
- A `--` comment inside a CREATE TABLE column list breaks DROP COLUMN, and the failure names a table the change never touched
- When a guard asserts the mechanism instead of the property, the fix that changes the mechanism looks like a regression
- Run a new guard against the code before the fix; a green suite proves the test agrees with the fix, not that it would have caught the defect
- Test at the level the defect lives; a substring test cannot tell a mention in a live branch from a mention in a dead one
- A test that recompiles identical bytes once per case is a tax on every future run, and the fixture that fixes it is three lines
- A guard that greps for a component name finds the comment explaining the component, and a prefix is a substring of every longer identifier
- A link is a claim about its destination, and only the destination knows whether it can keep it
- A deadness grep scoped to the source directories misses the callers that matter most, because the loudest ones live outside them
- A clean merge is a statement about text; two lanes can each be right about a file and wrong about each other
- A "has a caller" check is only as deep as its walk, and a one-level walk is satisfied by a referrer that is itself dead

### 2026-09-04 — in this file, above
- An absence pin that greps for a literal name finds it in `__pycache__`, because CPython folds `"a" + "b"` at compile time
- A rate limit is a pause, not a loss: an agent with a worktree resumes with its context
- "The largest contributor" is a set until proven a singleton, and `max()` on a dict picks a member silently
- A precondition written as the failure of one named mechanism does not fire when a different mechanism fails the same way
- A date read off a local clock is a different date; every registered instant is UTC
- A fixture set that only ever states the deployed value cannot detect a hardcoded copy of it
- Match a source anchor against the file's own line ending; a normalising reader will tell you it exists when a byte reader cannot find it
- The session scratchpad is shared across parallel lanes

### 2026-09-03 — in this file, above
- A counter that emits on a cadence while a condition holds measures the condition's duration, not its occurrences
- "One predicate, two spellings" is an architectural fault, not a run of incidents
- A binder proposed from a remembered lesson is a hypothesis, and it enters the record only after the check
- A screen promoted into a slot inherits the slot's traffic, not the old screen's fixes
- A gate that mounts a self-heal only when the screen is empty stops healing the moment it has anything

### 2026-09-02 — in this file, above
- A link to a screen is a claim that the screen exists, and the claim is pinned or it rots
- "Restore the guard" with `git checkout` restores the COMMIT, not your edit
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
