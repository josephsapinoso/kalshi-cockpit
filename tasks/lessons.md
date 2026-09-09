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
