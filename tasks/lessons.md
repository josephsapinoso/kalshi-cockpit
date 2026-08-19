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
each is in the linked archive file, unchanged.

### 2026-08-17 — in this file, above

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
