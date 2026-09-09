# AMENDMENT AND RE-REGISTRATION — the `parlay_positions` falsifying check, written before its read date

**Written 2026-09-08. The read it amends is due 2026-09-15.** Every predicate,
unit, denominator, threshold, stopping rule, decision rule and consequence
below is fixed here, seven days before the check was to fire, so that none of
them can be chosen once the count is visible.

**No `parlay_positions` data was consulted in writing this.** Not the row
count, not the `source` split, not a single row. The only figure about that
table anywhere in this document is a *prior* one already committed to the
repo — `docs/measurements/2026-09-05-parlay-census-registration.md:57` records
`parlay_positions` / `parlay_position_legs` / `manual_orders` at **0 rows
each** — and it is cited only to date the observation window, not to
anticipate the answer. That figure is from 2026-09-05: it predates the 2026
NFL season opener (Wednesday 2026-09-09) entirely and therefore says nothing
about the window the original check was written to observe. It was not
re-read. Confirming the table today would have been unnecessary as well as
contaminating, so it was not done.

**Nothing here is evidence about edge.** ADR 0038 closed the hunt. This
document touches `parlay_positions`, `parlay_position_legs`, `fills` and the
frontend's entry form. It does not touch `recommendations`, `beta`, the
300-game gate, the 0.63-point cost headroom or the 51.75% break-even bar, and
no verdict below may be quoted in a sentence about any of them. Nothing under
`backend/odds/` is referenced, changed, or implicated; the 2026-09-14 odds
freeze is untouched.

---

## 0. The check being amended, transcribed verbatim

The original was set by the partner agent and lives in the session record
rather than in a registration document, which is itself part of the problem
(§9.1). Three statements of it exist. All three are quoted here so that a
later reader can check the amendment against the thing amended rather than
against a paraphrase of it.

**(a) As the partner first set it** — `tasks/lessons.md:687-690`:

> The partner set a check: read `parlay_positions` on **2026-09-09**, and if
> it is still 0 "after an NFL opening weekend", ADR 0078's `/hedge` route
> becomes a deletion candidate.

**(b) As re-dated 2026-09-06** — `tasks/archive/next-2026-09-08.md:1155-1163`:

> 3. **`parlay_positions` on ~~2026-09-09~~ 2026-09-15 — the falsifying check
>    the partner set. RE-DATED 2026-09-06, and the old date could not have
>    worked.** If it is still 0 after NFL Week 1, ADR 0078's route is a
>    candidate for deletion.

**(c) The fullest statement of what it was testing** —
`tasks/archive/next-2026-09-08.md:1609-1616`:

> If it is still 0 after NFL Week 1, the transcribe-it-yourself entry design
> is refuted — ADR 0078's route becomes a candidate for deletion, not
> decoration.

The live carrier is `tasks/NEXT.md:528` and `tasks/NEXT.md:682`
(*"`parlay_positions` on 2026-09-15"*), which is a calendar entry pointing at
(b) and (c).

**Two properties of the original, stated before amending it.** First, it is a
*good* check in shape: it names an event, it is dated from that event's end,
it commits to a consequence, and the 2026-09-06 re-dating fixed the one defect
anybody had found. Second, its consequence is a **deletion**, which is
irreversible in effect if not in git, and that raises the bar on everything
below.

---

## 1. What invalidated it, and when

**2026-09-08, unprompted, in Joe's own words.** Earlier work recorded him as
wanting both *"buy the combination outright on Kalshi at the ask"* and
*"record one he paid for at a sportsbook"* (ADR 0078 Context: *"**both**
Kalshi combos and sportsbook slips"*, from an AskUserQuestion answer dated
2026-08-26). He has now said that by **sportsbook** he meant **Kalshi's own
sportsbook**, not a third-party book. He does not want a control for logging
bets placed at another book at all. He wants to place bets — singles and
combos — on Kalshi through the cockpit directly.

That correction does two separate things, and they must not be run together:

1. It **removes one arm** of the population the check was to be read over.
   `source = 'sportsbook'` — the third-party-book case — is not a case Joe
   wants, so its count is not evidence about anything he would use.
2. It **changes the entry design under test.** The check's own words are that
   a 0 refutes *"the transcribe-it-yourself entry design"*. If Joe buys the
   combination through the cockpit, entry is not transcription: the
   `parlay_positions` schema already carries `combo_ticker` (*"the minted
   `KXMVE` ticker, on a combo bought through this desk"*) and
   `parlay_lookup_id` for exactly that path (`backend/store/schema.sql`).
   A count of hand-typed rows would then be measuring a design that is being
   replaced, and reporting the verdict as if it were about the feature.

**This also meets ADR 0105 §5's own overturning condition.** That ADR decides
*"the desk is a read surface"* and names two things that would overturn it,
the second being **"Joe saying so."** He has said so, about transacting. This
document does not decide what follows — see §11 — but it may not pretend the
premise is intact either.

---

## 2. The defect this creates in the 2026-09-15 read, stated exactly

A reading of 0 on 2026-09-15 is **over-determined**. It cannot separate:

- **(a)** hedging or watching a held position is unwanted;
- **(b)** logging a bet placed at *someone else's* book is unwanted;
- **(c)** the form's default steered him away from the one case he would have
  used.

Under the original rule a 0 deletes ADR 0078's route. That deletion would be
unsafe, because (b) and (c) are live explanations that have nothing to do with
whether the feature is wanted.

**(c) is not a hypothetical, and it is worse than "a default".** Every entry
point to `parlay_positions` that has ever existed presented the third-party
book as the case, for the whole observation window:

| surface | file:line | what it presents |
|---|---|---|
| the form itself | `frontend/src/components/RecordParlay.tsx:69-70` | `useState(prefill?.source ?? "sportsbook")` — the default |
| the same form's select | `RecordParlay.tsx:156-157` | `"A sportsbook slip"` is the **first** option; `"A Kalshi combo"` is second |
| `/parlays` (the only prefilled site) | `frontend/src/components/ParlayCards.tsx:257-261` | `summary="I placed this at a sportsbook"` **and** an explicit `prefill={{ source: "sportsbook", … }}` |
| `/bets` | `frontend/src/app/bets/page.tsx:219` | no prefill → the default; blurb reads *"Paid for a bet at a sportsbook, or a combination on Kalshi?"* |
| `/picks` | `frontend/src/app/picks/page.tsx:308` | as above |
| `/slate` | `frontend/src/app/slate/page.tsx:448` | as above |
| `/hedge` | `frontend/src/app/hedge/page.tsx:61` | `<RecordParlay />` — no prefill → the default |

So the steer is a default, an option ordering, a summary line and a blurb, on
seven surfaces, in the same direction. The one surface that carries a Kalshi
combination card — `/parlays` — is the one that *hard-codes* `sportsbook` and
titles itself *"I placed this at a sportsbook"*.

**And the schema says this is backwards in its own comment**
(`backend/store/schema.sql:2033-2036`):

> Where the ticket lives. `kalshi_combo` can be hedged AND is the case that
> most needs it: combos are enter-only in 40 of 40 books this repo has read,
> so a hedge on a leg market is the only exit that exists.

There is therefore no window in which the `kalshi_combo` arm was presented
neutrally, let alone favourably. Its exposure is not merely low — it was
**structurally suppressed by the instrument** for the entire duration of the
observation.

---

## 3. THE POWER CHECK, WHICH COMES BEFORE THE RE-CUT

Before deciding *how* to amend, the question is whether any cut of a
2026-09-15 read can answer anything. Three separate arithmetic problems, in
ascending order of how fatal they are.

### 3.1 The window in which a clean reading was even possible is zero days

`git log` on the entry form:

```
ee76e16  2026-09-06  Paying for a combination at a book is now recordable from the four screens he bets from
17bcb10  2026-08-26  The hedge screen, the watcher and the alert — and driving it found the defect
```

The form has existed for **13 days** as of writing, of which **11** had it
reachable from `/hedge` alone and **2** from the four betting screens. In
every one of those 13 days the default was `"sportsbook"`. The number of days
on which a user was presented a neutral choice of `source` is **0**.

### 3.2 There is no denominator, and for one arm there can never be one

The original rule is a bare count with no exposure base. A 0 is uninformative
unless the number of *opportunities* is known: if Joe placed no parlays at all
during Week 1, a 0 is guaranteed and measures nothing about the entry design.
The check never named an opportunity count.

One is available for the Kalshi arm, and it needs no new code and no read of
`parlay_positions`. `backend/parlays.py:129-131` carries the committed census
constants:

```
PARLAY_CENSUS_DATE      = "2026-09-06"
PARLAY_CENSUS_POSITIONS = 52
PARLAY_CENSUS_TAKER_FILLS = 51
```

51 of 52 combination positions were entered as **taker fills**, which means
they are visible in `fills` without Joe typing anything. Over the census
window (`2026-08-18T00:00Z` → `2026-09-05T00:00Z`, 18.0 days, that
registration §4.1) that is **≈2.9 combination positions per day, observed by
the venue rather than by the operator.**

For the third-party arm no denominator exists and none will be built.
`fills` cannot see a sportsbook slip — ADR 0105 §4 says so in those words,
and it is the reason ADR 0078 exists at all. **That arm is permanently
unmeasurable at any `n`**, and no amendment can rescue it.

### 3.3 The unit is the sitting, not the row, and that is where `n` collapses

Two combination tickets bought in one sitting are not two independent chances
to fill in a form: if he did not bother typing, he did not bother for both.
The clustering variable is therefore the **sitting**, defined as in
`docs/measurements/2026-09-04-presence-at-the-moment-of-a-bet-result.md`,
which counted **27 Kalshi taker hand fills across 12 sittings and 7 budget
days** over 2026-08-25 → 2026-09-04 (10 days) — ≈**1.2 sittings/day**, and
that is an upper bound on sittings-*containing-a-combination*, because not
every sitting held one.

Reconciling the two committed counts (52 positions / 18 days against 27 fills
/ 10 days) is not attempted here: they are different populations over
different windows, and forcing them to agree would be exactly the tidying this
repo keeps correcting. Take the cluster rate as a range: **0.7 to 1.2
qualifying sittings per day.**

### 3.4 The detectable effect, computed now

The estimand is a proportion (§6), and at an observed zero the default
`sqrt(p(1-p)/n)` returns **0** — a standard error of zero on a count of zero,
which is the exact trap CLAUDE.md's estimator rule warns about. The correct
one-sided 95% upper bound at `R = 0` successes in `G` clusters is the rule of
three, `3/G`:

| `G` (sittings) | 95% upper bound on per-sitting adoption | days at 1.2/day | days at 0.7/day |
|---|---|---|---|
| 5 | 0.60 | 4 | 7 |
| 10 | 0.30 | 8 | 14 |
| 15 | 0.20 | 13 | 21 |
| **30** | **0.10** | **25** | **43** |
| 60 | 0.05 | 50 | 86 |

**The verdict of the power check:** at a 2026-09-15 read the clean exposure is
`G = 0` by §3.1, so the detectable effect is undefined; and even counting the
contaminated days generously, 13 days at 0.7–1.2 sittings/day is `G ≈ 9–16`,
whose upper bound is 0.19–0.33. A 0 there is consistent with Joe adopting the
form a third of the time. **That is not a refutation of anything**, and firing
a deletion on it would be the same failure mode the 2026-09-06 lesson names:
making refutation arrive early and for free.

---

## 4. Why splitting by `source` does not rescue the read

The obvious amendment — split the population by `source` and let the decision
rule speak only to `kalshi_combo` — is **rejected**, and the reason is §2
rather than §3.

Splitting removes the (b) confound and leaves (c) untouched. The
`kalshi_combo` cell's exposure was suppressed by the instrument on all seven
surfaces for all 13 days, and the one surface that could have fed it
hard-coded the other value. A count of 0 in that cell is fully explained by
the form. Re-cutting a contaminated window is not a fix; it is a smaller
version of the same claim.

The honest amendment is therefore **not a re-cut. It is a postponement**, and
the deletion clause is **vacated rather than deferred** — vacated, because the
window it would have read is void and no later read can retroactively clean
it.

---

## 5. The claim under test, in the successor, as something that can come back false

**Primary claim (one-sided, direction fixed here):** over a clean window, the
per-sitting rate at which Joe records a Kalshi combination he holds, using
whatever entry surface exists after §7's preconditions are met, is **greater
than zero.**

The null is that it is zero. The direction is one-sided: the successor tests
whether adoption is *at or near zero*, because that is the only reading that
could justify killing the design. A two-sided framing here would be a
pretence — nobody is going to act on "adoption is unexpectedly high".

### 5.1 Weakened quantifiers, on purpose

The original said the design is "refuted". This registration will not carry
that word without a bound attached. What a clean `R = 0` at `G = 30`
establishes is *"per-sitting adoption is below 0.10 with 95% confidence"* —
not "never", not "structurally", not "by construction". Likewise §2's table
says the steer ran on **seven surfaces over 13 days**, which is checkable,
rather than "the form always steered him", which is not.

---

## 6. The statistic, named as an estimator

A **proportion**: `R / G`, where `G` is the number of qualifying sittings in
the clean window and `R` is the number of those sittings in which at least one
`parlay_positions` row with `source = 'kalshi_combo'` was created.

- The unit of observation is the **sitting**. The clustering variable is the
  sitting. Two rows in one sitting count once.
- At `R = 0` the interval is the one-sided 95% rule-of-three bound `3/G`.
  At `R >= 1` it is Clopper–Pearson exact, two-sided 95%, reported but not
  tested (§8 makes `R >= 1` decisive on its own).
- `sqrt(p(1-p)/G)` is **forbidden** in this analysis. It returns 0 at `R = 0`
  and would report a zero-width interval around zero.

---

## 7. Preconditions — what must hold before a clean window can open

None of these is optional and none may be waived by a later session on the
grounds that time has passed.

- **P1 — the entry design is settled by an ADR.** Joe's 2026-09-08 correction
  says he wants to place singles and combinations on Kalshi through the
  cockpit. Until an accepted ADR records what the entry path is, "the
  transcribe-it-yourself entry design" is not the design under test and there
  is nothing to measure adoption *of*. See §11.
- **P2 — the steer is removed, in both directions.** All seven rows of §2's
  table. The fix is **not** to flip the default to `"kalshi_combo"`: that is
  the same defect mirrored, and it would make a non-zero count as
  uninterpretable as the zero was. The fix is **no default** — an unselected
  required control that refuses submission until the operator chooses — plus
  removing `ParlayCards.tsx`'s hard-coded `source: "sportsbook"` and its
  `"I placed this at a sportsbook"` summary. If P1's ADR removes the manual
  form entirely, P2 is satisfied vacuously and this registration is void
  (§10).
- **P3 — the denominator is instrumented before the window opens.** A named,
  committed script that emits `G` (qualifying sittings) from `fills`, using
  the sitting definition in the 2026-09-04 presence result, over an arbitrary
  date range. It must be written and committed **before** the window opens,
  not after the count is wanted.
- **P4 — the window is dated from the deploy of P2, and from a looked-up
  date.** Per `tasks/lessons.md`'s 2026-09-06 lesson: the event is *"the
  deploy that lands P2"*, the window opens at that deploy's timestamp, and the
  date is derived from it rather than recalled.

**A sitting qualifies if** it contains at least one Kalshi taker fill on a
`KXMVE` combination ticker, per P3's script. The qualification predicate
references `fills` only. **It does not reference `parlay_positions`**, which
is the outcome — an exclusion or inclusion rule that touched the outcome would
be the finding rather than a rule about the population.

---

## 8. THE DECISION RULE, VERBATIM

> **The deletion clause set on 2026-09-09/2026-09-15 is VACATED, not
> deferred.** It does not fire on 2026-09-15 and it does not fire on any later
> date under its own terms. No count of `parlay_positions` taken over the
> window 2026-08-26 to 2026-09-15 — zero or otherwise — may be cited as
> evidence that ADR 0078's route, screen, watcher or tables are unwanted, and
> no session may delete, disable, unlink or stop deploying `/hedge`,
> `backend/api/routers/hedge.py`, `backend/core/hedge.py`, the hedge watcher
> task, `parlay_positions` or `parlay_position_legs` on the strength of it.
>
> **One reading is permitted on or after 2026-09-15 and it carries no
> verdict.** It is `SELECT source, COUNT(*) FROM parlay_positions GROUP BY
> source`, optionally also restricted to `created_ms >=` the 2026-09-06
> four-screen deploy. It is a **census**. Its only permitted use is as a
> planning value for `n` in the successor registration's power check. It may
> not be used to set any threshold, to choose any boundary, to select any
> population, or in any sentence about whether hedging is wanted. Because it
> carries no verdict it is not a look, and it does not consume the successor's
> one-look budget.
>
> **A deletion decision on ADR 0078's route requires a successor
> registration**, which may not be written until P1–P4 in §7 all hold, and
> which must then observe a window that opens at the P2 deploy and closes at
> **`G = 30` qualifying sittings** or **2026-11-30**, whichever comes first.
> The record is read **once**, at that close, by P3's committed script.
>
> At the close, with `R` = the number of qualifying sittings containing at
> least one `parlay_positions` row with `source = 'kalshi_combo'`:
>
> - **`G >= 30` and `R = 0` → REFUTED.** Per-sitting adoption is below 0.10
>   (one-sided 95%, rule of three). The *entry design* is refuted. What is
>   killed is the manual entry form on all surfaces. **The route, the
>   watcher, the arithmetic and the two tables are not killed by this
>   verdict** — they are re-pointed at whatever entry P1's ADR chose. If P1's
>   ADR chose no automatic entry, deletion becomes a live option and requires
>   its own decision record; it is not authorised here.
> - **`G >= 30` and `R >= 1` → NOT REFUTED.** One real row from Joe's own tap
>   is enough, on the precedent ADR 0105 §5 sets for `manual_orders` in its
>   own words. Deletion is off the table under this registration and the
>   successor question becomes whether the *watcher* is acted on, which is a
>   different registration with a different unit.
> - **`G < 30` at 2026-11-30 → UNDERPOWERED.** No verdict, no deletion, and
>   the absence of data may not be reported as the finding. It is written up
>   regardless, at the location in §10.
>
> **`source = 'sportsbook'` never carries a verdict, at any `n`, in this
> registration or its successor.** `fills` cannot see a third-party slip, so
> that arm has no denominator and can never have one. Its count is reported as
> a bare number and nothing is decided on it.

### 8.1 The multiplicity, counted

**One test, one arm, one look.** The `sportsbook` arm is reported and not
tested; the `kalshi_combo` arm carries the single verdict; the record is read
once, at a stopping point defined on the denominator rather than the outcome.
At one test at the 5% level, pure noise produces 0.05 false findings. **No
correction is applied and none is needed** — which is only true because the
count above is fixed here rather than after.

**The always-valid question, answered.** CLAUDE.md's 13.7% figure applies to a
threshold re-evaluated against an accumulating database. `parlay_positions` is
exactly such a database and anyone can `SELECT COUNT(*)` from it at any time,
so the hazard is real. It is handled by construction rather than by a
boundary: the verdict fires at a **stopping point defined on `G`**, which is
computed from `fills` and is independent of the outcome, and interim looks are
permitted only as verdict-free censuses. A session that wants to peek may
peek; it may not decide.

---

## 9. Two defects in the original that this amendment also fixes

### 9.1 It was a calendar entry, not a registration

The original lived in `tasks/NEXT.md` and its archive. CLAUDE.md's own rule is
that a pre-registration that lives only in a conversation has not been
pre-registered; a check that lives only in a session handoff is one step
better and still not a document. The consequence showed: the date was wrong
for two session entries and was caught by a session reading the calendar, not
by anything structural.

### 9.2 It bundled two decisions behind one count

*"The transcribe-it-yourself entry design is refuted"* and *"ADR 0078's route
becomes a candidate for deletion"* are two claims joined by an em-dash, and
the count can only speak to the first. The route is the **exit** for a
position; the form is the **entry** for a record of one. ADR 0078 Decision 1
is explicit that hedging a leg market is the only exit an enter-only
combination has, and Joe's 2026-09-08 correction says he intends to create
*more* such positions through the cockpit. Refuting the entry design is an
argument for changing the entry, not for removing the exit. §8 separates them.

**And this is the honest answer to CLAUDE.md's decision-relevance test.** For
the *form*, the measurement is decision-relevant: a clean `R = 0` kills it and
an `R >= 1` keeps it. For the *route*, it is not — the route survives either
verdict under §8, so on the route the plan proceeds either way. That is a
finding about the original plan and it is cheaper to say now than after the
run.

---

## 10. Where the negative result gets written, and what happens in each direction

- **The census taken on or after 2026-09-15** is written up at
  `docs/measurements/2026-09-15-parlay-positions-census.md`, whatever it says,
  including if it is 0 on both arms. It carries the sentence *"this is a
  census and carries no verdict"* in its first paragraph.
- **The successor's verdict**, whichever of the three it is, is written up at
  `docs/measurements/<close-date>-parlay-entry-adoption-result.md`. The
  UNDERPOWERED branch gets the same file and the same prominence as the other
  two; it is not a footnote in a NEXT.md entry.
- **If this registration is voided** by P1's ADR removing the manual form
  (§7, P2), that voiding is recorded as an amendment appended to *this* file,
  dated, with the ADR named — not by deleting the file.
- **Built if it clears (`R >= 1`)**: nothing new is funded by that alone; the
  form stays and the next question is the watcher's, which needs its own
  registration.
- **Killed if it does not (`R = 0` at `G >= 30`)**: the manual entry form on
  all seven surfaces of §2's table.
- **Untouched in every branch**: `/hedge`, the watcher, `core/hedge.py`, both
  tables, and the `gate.py` boundary that forbids reading either of them
  (ADR 0078 §4).

---

## 11. The ordering dependency, and which must come first

Three things are in flight and the order matters, because two of them restart
the clock on the third.

1. **P1 first — the entry-design ADR.** Joe's correction reopens ADR 0105 §3
   by ADR 0105 §5's own terms, and it decides what `source` even means going
   forward. A suggested slug, **with no ordinal taken**, is
   `docs/adr/DRAFT-joe-places-bets-through-the-cockpit.md`; ordinals are taken
   at merge after `git fetch` per `docs/adr/README.md`, and a guard refuses
   `DRAFT-` files on main. **This document does not write that ADR and does
   not decide its content.** It only records that the measurement cannot be
   re-registered until it exists, because P1 determines whether P2 is a form
   change or a form removal.
2. **P2 second — the form.** `RecordParlay.tsx:69-70`'s default must come off
   `"sportsbook"`, along with the six other steers in §2's table. **No code is
   changed by this document**; the change is named as a precondition, not
   made.
3. **The clean window third, and it starts at P2's deploy.** This is the part
   that must be said plainly: **flipping the default restarts the clock.** Any
   behavioural reading taken across the flip pools two different instruments
   and is uninterpretable, so the window opens at the deploy and nothing
   before it counts.

**The corollary, said against the temptation to protect the window:** do not
delay the flip in order to preserve continuity of observation. The window
being observed is already void by §3.1 and §4 — there is nothing left to
protect, and every day the steer stays up is a day the schema's own
*"the case that most needs it"* is the second option behind a wrong default.
The flip should ship as soon as P1 tells it what to become.

---

## 12. What this measurement does NOT establish

Drafted now, before the run, per CLAUDE.md's harness rule, because caveats
written afterwards are selected to be survivable.

- **That hedging is unwanted, or wanted.** Every version of this check
  measures **entry** — whether a record of a held ticket exists. The value of
  the hedge arithmetic itself is untested here and would remain untested at
  `G = 300`. A ticket must be recorded before the watcher can run, so entry is
  a *prerequisite* for demand, never a measurement of it.
- **That `/hedge` is unused.** The page renders the form and can be visited
  without writing a row. `desk_attention` cannot help: its schema comment
  (corrected 2026-09-04) says the row count measures **dwell, not use**, and
  it is `(id, seen_ms)` — it cannot distinguish a reader from a tab left open
  (`docs/measurements/2026-09-03-desk-dwell-and-the-watcher-off-switch.md`).
- **Anything about bets Joe places at a third-party book.** `fills` cannot see
  them, there is no denominator, and the `sportsbook` arm is unmeasurable at
  any `n` — permanently, not pending instrumentation.
- **That a non-zero count is adoption.** A row could be a test row written by
  a session, a demo-instance row, or a mis-tap. The successor must establish
  provenance per row before counting it toward `R`; a row whose provenance
  cannot be established is excluded, and that exclusion rule is fixed here
  rather than at read time.
- **That the exposure rate generalises.** ≈2.9 combination positions/day and
  0.7–1.2 sittings/day are measured over 2026-08-18 → 2026-09-05, an
  MLB/WNBA window, before the NFL season opened. NFL may move both in either
  direction and **no direction is predicted here.** If the realised rate is
  far from the planning value, `G = 30` is still the floor and the date
  backstop still governs; the planning value is not re-fitted after the fact.
- **That the sitting is independent of the outcome.** The stopping rule
  assumes that whether a sitting contains a combination fill does not depend
  on whether he later typed it into the form. That assumption is stated, not
  verified, and it is the most likely place this design is wrong.
- **That deletion is the right consequence even under a clean refutation.**
  §8 separates the form from the route deliberately, and §9.2 gives the
  reason.
- **Anything about edge, `beta`, the gate's 300-game floor, the 0.63-point
  cost headroom, the 51.75% break-even bar, or `recommendations`.** ADR 0038
  is untouched. `gate.py` may never read `parlay_positions` or
  `parlay_position_legs` (ADR 0078 §4) and nothing here changes that.
- **That the 0 already in the record means anything.** The
  `parlay_positions = 0` at `2026-09-05-parlay-census-registration.md:57` is
  cited in this document to date a window and for no other purpose. It
  predates the season opener and it predates the four-screen deploy by one
  day.

---

## 13. Corrections made to the proposed amendment, recorded because the reasons recur

- **"Split by `source` and let the rule speak only to `kalshi_combo`" was
  proposed and is rejected** (§4). It fixes confound (b) and leaves confound
  (c) exactly where it was. The general shape: *re-cutting a contaminated
  window produces a narrower claim from the same bad data, and the narrowing
  reads as rigour.*
- **"Default the form to `kalshi_combo`" is rejected** (§7, P2). It is the
  same steer pointed the other way, and it would make a subsequent non-zero
  count as uninterpretable as the zero was. No default.
- **"Read something on 09-15 because the date exists" is rejected as a
  verdict-bearing act and permitted only as a census** (§8). A date is not a
  reason.
- **The word "refuted" is not used without a numeric bound attached** (§5.1).

---

## Provenance

- The original check: `tasks/lessons.md:687-690`;
  `tasks/archive/next-2026-09-08.md:1155-1163`, `:1609-1616`;
  `tasks/NEXT.md:528`, `:682`.
- The invalidating correction: Joe, 2026-09-08, unprompted, relayed to this
  agent by the launching session. It is reported as his answer, not as a
  sentence he typed here, and is cited as such — the same convention ADR 0105
  §2 uses for ticket #11's resolving comment.
- The steer: `frontend/src/components/RecordParlay.tsx:69-70`, `:156-157`;
  `frontend/src/components/ParlayCards.tsx:257-261`;
  `frontend/src/app/{bets,picks,slate}/page.tsx`; `frontend/src/app/hedge/page.tsx:61`.
- The schema's own priority: `backend/store/schema.sql:2033-2036`.
- Exposure rates: `backend/parlays.py:129-131` (committed census constants);
  `docs/measurements/2026-09-05-parlay-census-registration.md` §4.1 (the
  window); `docs/measurements/2026-09-04-presence-at-the-moment-of-a-bet-result.md`
  (27 fills / 12 sittings / 7 budget days, and the sitting definition).
- Precedent for "one real row reopens it": ADR 0105 §5.
- Precedent for dating a check from an event's end: `tasks/lessons.md`,
  2026-09-06 lesson.
- The route this protects: ADR 0078, Decision 1 and §4.
- **Not consulted:** `parlay_positions` and `parlay_position_legs`, at any
  point, by any read.

**Verdict on this registration: READY for the census; POSTPONED for the
verdict.** The deletion clause is vacated, the successor is
precondition-gated, and the earliest legitimate deletion read is
`G = 30` sittings after the P2 deploy — 25 to 43 days at the measured rate —
with a hard backstop of 2026-11-30 that returns UNDERPOWERED rather than a
finding.


---

## Appendix A — P2's code has landed (2026-09-08, same day)

**This is a status note on a precondition, not an amendment.** Nothing in the
registration above is changed by it: no statistic, no cut, no decision rule and
no stopping rule moves. It is here because P4 dates the window from *"the
deploy that lands P2"*, and a future session needs to know the code exists
without re-deriving which commit it was in.

**All seven surfaces of §2's table are addressed:**

| § 2 row | what it was | what it is |
|---|---|---|
| the form's default | `useState(prefill?.source ?? "sportsbook")` | `?? ""` — no default, not a flipped one |
| the select | `"A sportsbook slip"` first | `<option value="">Choose one</option>` first and **selected**; neither real option is preselected |
| `/parlays` | `summary="I placed this at a sportsbook"` + hard-coded `source: "sportsbook"` | `summary="Record a ticket you already hold"`, and the prefill carries no `source` at all |
| `/bets`, `/picks`, `/slate` | blurb *"Paid for a bet at a sportsbook, or a combination on Kalshi?"* | *"Already paid for a bet the desk cannot see?"* — names neither venue |
| `/hedge` | no prefill → the default | no prefill → no default |

**The blurb was deliberately not reordered.** Putting Kalshi first was the
first attempt and was reverted within the same change: §7 rejects flipping the
default because *"that is the same defect mirrored"*, and the identical
argument applies to a sentence that names two venues in an order. The neutral
form names neither.

**Submission is refused rather than defaulted.** The button is disabled while
`source === ""` and `submit` returns early with *"Choose where this ticket is
— a Kalshi combo or a sportsbook slip."* Both halves are needed: a form can be
sent from the keyboard, and `schemas.py` requires the field against a
two-value pattern, so an empty string would reach the server as a 422 the
reader cannot act on.

**What is guarded.** `tests/test_recording_a_bet_is_reachable.py` gained
`TestTheSourceQuestionIsNotAnsweredForHim` (three assertions) and its existing
`test_the_card_hands_over_its_own_legs` was **inverted** — it had been
*requiring* `source: "sportsbook"` in the prefill, so the steer was pinned in
place by the suite and would have survived any attempt to remove it. All four
verified red by restoring the steer.

The prefill assertion reads the `prefill={{…}}` block rather than the file,
because the comment above the control quotes the removed line to say what it
replaced; a guard refusing the quotation would forbid explaining the fix.

**THE WINDOW IS OPEN. It opened at `2026-09-08T21:33:05Z`.**

P4 requires the timestamp to be looked up from the deploy that ships the code
rather than recalled or predicted, so it is:

    deploy run   34281066870        gh run view 34281066870 --json updatedAt
    head sha     a13e6b8
    finished     2026-09-08T21:33:05Z
    verified     /api/health build.git_sha == a13e6b8, machine 7812601a239428

The machine id is recorded beside it because a NEW machine gets an empty
volume, and a census of a table on a fresh volume would read zero for a reason
that has nothing to do with the question. It is unchanged across this deploy.

The paragraph this replaces said the window was not yet open and instructed
whoever deployed to fill the timestamp in. That happened in the same session,
which is the only reason this is a lookup and not a reconstruction.

**P1 and P3 are still open** and P2 does not advance either. P1 needs an
accepted ADR recording the entry design; ADR 0113 records that Joe wants to
place singles and combinations through the cockpit, which is the *correction*
that motivated P1, not the design document P1 asks for. P3's denominator
script does not exist.


---

# AMENDMENT 1, 2026-09-09 — the wiring changed the estimand, and the window is void

**Written 2026-09-09, before the write it authorises and before any count is
taken over the window it closes.** It is appended to this file rather than
replacing anything in it, per §10's rule that a voiding is recorded as an
appended amendment and not by editing the record away. **Nothing above this
line has been changed.** Appendix A's timestamps stand exactly as written.

It rules on four questions put by the executing session and it does four
things: it authorises one hand write under a pre-declared exclusion (A1.2), it
**voids the observation window opened at `2026-09-08T21:33:05Z`** (A1.3), it
records that P3 was violated independently of that (A1.4), and it permits a
named operational read that is not the §8 census (A1.5).

**What it does not touch.** §8's vacating of the deletion clause stands in
full and is not weakened by anything here — no session may delete, disable,
unlink or stop deploying `/hedge`, `backend/api/routers/hedge.py`,
`backend/core/hedge.py`, the hedge watcher, `parlay_positions` or
`parlay_position_legs` on the strength of any count, and voiding the window
makes that *more* binding rather than less. Nothing here is evidence about
edge; ADR 0038 is untouched; `gate.py` still may not read either table
(ADR 0078 §4); nothing under `backend/odds/` is implicated.

## A1.1 The facts that forced it, dated and sourced

1. **A real combination filled inside the window.** `manual_orders` id=4,
   `dry_run = 0`, 4 contracts at 41c ($1.64), three MLB legs (BOS 18:45Z,
   NYY 19:05Z, LAD 22:10Z), filled **2026-09-09T15:11:56Z**. Open on the venue
   at 17:15Z.
2. **ADR 0125 deployed at 2026-09-09T15:56:45Z**, 45 minutes after that fill.
   It wires `_record_combo_position` (`backend/api/routes.py:4174`) into the
   hand-bet path so that a filled non-dry-run combination writes its own
   `parlay_positions` row with `source = "kalshi_combo"`
   (`backend/api/routes.py:4231`).
3. **The fill is therefore an orphan by 45 minutes**: `parlay_positions` holds
   no row for it, and the deployed code would have written one had the fill
   landed later. It is a gap artifact, not a failure of the wiring.
4. **`parlay_positions` was read on live on 2026-09-09 and holds 0 rows.**
   That read is recorded here as an interim census under §8's *"a session that
   wants to peek may peek; it may not decide"*. It carried no verdict, set no
   threshold, chose no boundary and selected no population. It is logged
   because an unrecorded look is the thing that rots, not because it changed
   anything. See A1.6 for what it does to the 2026-09-15 census.
5. **The writers of the outcome table are exactly two**, asserted over source
   on this date: one `INSERT INTO parlay_positions` at `backend/hedge.py:334`,
   reached from `backend/api/routers/hedge.py:73` (`POST /api/hedge/positions`)
   and from `backend/api/routes.py:4228` (the hand-bet path). §6's statistic
   cannot be fed by any third surface, so there is no escape hatch by choosing
   a different route.

## A1.2 RULING 1 — the orphan row MAY be written, under a pre-declared exclusion

**Permitted.** The authority is §12's provenance clause, which was fixed in
advance and reads: *"The successor must establish provenance per row before
counting it toward `R`; a row whose provenance cannot be established is
excluded, and that exclusion rule is fixed here rather than at read time."*

A row written by an agent session is not an act of recording by Joe. Its
provenance is establishable **if and only if it is declared before it exists**,
which is what this section does. The exclusion turns on *authorship*, which is
independent of the outcome's value; it does not turn on what the count is.

### A1.2.1 The row, identified before it is written

Named by facts known now, because the row id is not knowable until after the
write:

- the `parlay_positions` row created from `manual_orders` id=4,
- `source = 'kalshi_combo'`, `parlay_lookup_id = 41`,
- `combo_ticker` = the minted `KXMVE` ticker **as transcribed from
  `manual_orders` id=4**, never typed from memory,
- `stake_tenths = 1640`, `return_tenths = 4000`,
- `created_ms` between the commit of this amendment and 2026-09-10T00:00:00Z.

### A1.2.2 Both exclusions, and why the second one is the necessary one

- **The row is excluded from `R`.** It is not Joe recording anything.
- **The sitting containing `manual_orders` id=4's fill is excluded from `G`.**
  This is the exclusion that actually matters and it must not be dropped as
  fussiness. Writing the row puts the position on `/hedge`, which removes Joe's
  occasion to record it himself. Leaving the sitting in the denominator while
  the intervention has destroyed its chance of contributing to the numerator
  would bias `R/G` **downward** — toward REFUTED, toward killing the form.
  The exclusion is outcome-independent (it fires on "an agent intervened in
  this sitting", known before any count) and it costs one unit against a floor
  of 30.
- This exclusion **survives the voiding in A1.3** and is stated separately from
  it on purpose. The fill at 15:11:56Z sits in the pre-ADR-0125 stretch of the
  window, which is the only stretch a future session could argue is salvageable.
  If anyone makes that argument, this sitting is still out.

### A1.2.3 The form of the write

- **No figure may be hand-composed.** No hand-written `INSERT`. The write runs
  through a **committed** one-shot script that calls
  `parlays.priced_lookup_for`, `parlays.legs_for_position` and
  `hedge.record_position` with every value derived from `manual_orders` id=4
  and `parlay_lookups` id=41 — the same values `_record_combo_position` would
  have derived. It is committed before it runs, so the exact arguments are in
  git rather than in a transcript.
- **`legs_for_position` returning `None` aborts the write.** A partial leg list
  is refused outright (ADR 0125), and this amendment does not relax that.
- **One field is deliberately overridden, and it is the provenance marker.**
  `_record_combo_position` writes the note *"Recorded automatically from the
  hand-bet path"*, which would be **false** for this row. The note must instead
  read, in substance and with these facts present:

  > Recorded by hand on 2026-09-09 by an agent session under Amendment 1 of
  > docs/measurements/2026-09-08-parlay-positions-check-amendment-registration.md,
  > replaying ADR 0125's `_record_combo_position` against manual_orders id=4,
  > which filled at 15:11:56Z — 45 minutes before that wiring deployed at
  > 15:56:45Z. This is NOT an act of recording by Joe. Excluded from R, and
  > its sitting excluded from G, by that amendment.

- **After the write**, the resulting `parlay_positions.id` and its `created_ms`
  are appended to this amendment as a one-line factual note. Not optional: the
  identification in A1.2.1 is by description until that line exists.
- **This ruling authorises nothing money-touching.** It moves no money, reaches
  no venue, and writes a table `gate.py` may never read. Whether the live write
  is *permitted to execute* is a permission-system and operator question and
  this amendment does not answer it or license working around it.

### A1.2.4 What the write buys, stated without inflation

Three legs pending means ADR 0078 gives no figure and says so. The screen
becomes load-bearing only once two legs have resolved and one is live —
roughly **22:15Z to 01:10Z** on 2026-09-09. The exposure is a **$1.64 stake
against a $4.00 return**, and the hedge it would inform is a fraction of that.

**The write is permitted because §12 pre-registered the exclusion that makes it
harmless, not because the cost of blindness is large.** It is not large. Had
the exclusion not been fixed in advance, the correct ruling would have been to
take the blindness.

## A1.3 RULING 2 — the estimand is superseded and the window is VOID

**The registration is not void; its observation window is.** §7's voiding
trigger is *"If P1's ADR removes the manual form entirely"*, and ADR 0125 did
not remove it — its Consequences say in terms that *"`POST
/api/hedge/positions` and `RecordParlay.tsx` stay"*. So this document stands,
§8's vacated deletion clause stands, and §12's caveats stand. What dies is the
window and the primary claim's measurability in its present wording.

### A1.3.1 Why the claim as written can no longer come back negative

§5's primary claim has **Joe** as its subject and **records** as its verb.
Since `2026-09-09T15:56:45Z`, a qualifying sitting containing a successful
combination fill through the desk increments `R` **mechanically, with no act by
Joe at all**. Under §8's decision rule, `R >= 1` is decisive on its own and
returns NOT REFUTED. So from the deploy forward the registration returns NOT
REFUTED as soon as the wiring works — a verdict fully determined by the
instrument and carrying no information about the thing being measured.

A question that cannot come back negative is not a question. The claim is
**superseded**, not merely confounded, and no re-cut of this window fixes it —
the same reasoning §4 already used to reject re-cutting.

### A1.3.2 The window is pooled across two instruments, by §11's own logic

§11.3 says the P2 flip restarts the clock because *"any behavioural reading
taken across the flip pools two different instruments and is uninterpretable"*.
ADR 0125 is a larger instrument change than the flip: it does not change the
steer, it changes the outcome-generating process. The window ran clean for
**18 hours 24 minutes** (2026-09-08T21:33:05Z to 2026-09-09T15:56:45Z), which
at §3.3's measured 0.7–1.2 sittings/day is `G` between 0 and 1. There is
nothing there to preserve.

**Ruled: the window opened at `2026-09-08T21:33:05Z` is closed and void as of
`2026-09-09T15:56:45Z`. No count taken over it may be cited for any purpose.
P4's clock is reset and a new window may not open until A1.4's preconditions
hold.**

### A1.3.3 The successor's estimand, re-scoped — and the schema consequence

A successor is recoverable, but only with a redefined population and an
enforced provenance column. Both are fixed here so they cannot be chosen later.

**The population becomes the *unwired* sitting.** A sitting qualifies if it
contains at least one Kalshi taker fill on a `KXMVE` combination ticker **for
which no filled, non-dry-run `manual_orders` row exists** — i.e. a combination
Joe holds that the desk did not buy for him and therefore did not wire. The
predicate is computed from **`fills` and `manual_orders` only**. It does
**not** reference `parlay_positions`. This is load-bearing: the obvious
denominator — "sittings whose fill produced no row" — reads the outcome table,
and an inclusion rule that touches the dependent variable is the finding rather
than a rule about the population.

**Provenance must become a column, and `note` will not do.** The wiring's
distinguishing sentence lives in free text, and `POST /api/hedge/positions`
accepts `note`, `combo_ticker` and `parlay_lookup_id` straight from the request
(`backend/api/schemas.py:308-310`). A manual row can therefore be made
byte-identical to a wired one. Text is not a discriminator.

What is owed, if a successor is to be measurable at all, is a column on
`parlay_positions` — shape suggested, not mandated:

    entry_path TEXT NOT NULL
        CHECK (entry_path IN ('manual_form', 'hand_bet_wiring', 'unknown'))

with three properties, each of which has a precedent in this repo:

- **Set by the writer, never accepted from the request.** The precedent is
  `parlay_position_legs.resolved_source`, whose route comment already says a
  client that could claim `venue` *"would erase the distinction the moment
  somebody found it convenient"*. Same defect, same fix, same file.
- **Pre-column rows take `'unknown'`, and `'unknown'` is never counted toward
  `R`** — it is excluded by §12's provenance clause. Unreadable resolves to
  `None`, never to a guess.
- **Pinned by a test verified red** by having the manual route claim
  `'hand_bet_wiring'`.

**Lane C should be told this before it touches `schema.sql`.** Without the
column the re-scoped claim is unmeasurable, and adding it later cannot recover
provenance for rows already written.

**No successor window opens on the strength of this section.** A1.4 gates it.

## A1.4 RULING 3 — P3 was violated independently; P1 is not satisfied

### A1.4.1 P3's violation is fatal to the window, not a recordable deviation

§7 P3 says the denominator script *"must be written and committed **before**
the window opens, not after the count is wanted"*, and the script does not
exist (Appendix A, `:659`). That is a precondition, not a preference, and its
stated purpose — the denominator rule cannot be tuned once the outcome is
visible — is defeated exactly by writing it afterwards.

**Stated so it cannot be missed: the window was already unable to carry a
verdict before ADR 0125 shipped.** A future session that repairs only the
estimand problem and reopens the same window would be reopening a window that
independently breaches P3. Both defects must be cured.

### A1.4.2 Reusing another registration's constant is sufficient for the gap and for nothing else

`scripts/analyse_bet_presence.py:56` (`SITTING_GAP_MS = 3_600_000`) and `:378`
(`sittings()`) were committed for a different registration, for a different
question, before this one was asked. That is a **strong** form of
pre-commitment for the parameter they carry: the gap could not have been chosen
to flatter this outcome. **The gap and the run-forming algorithm are
satisfied**, and P3's script **should import them rather than copy them** — a
copy can drift, and the import makes the shared provenance visible.

**Everything else P3 needs is uncommitted, and each choice moves `G`:**

- the qualification predicate — which fills count: `is_taker = 1`, and *which
  literal `KXMVE` series*. The sibling registration
  (`2026-09-09-preregistration-combo-exit-nfl-sunday.md`, Amendment 2) spent an
  entire amendment on exactly this scope error. P3 must name the literal
  series predicate rather than "a `KXMVE` ticker";
- the boundary rule for a sitting straddling the window's open;
- the attribution instant for a sitting (`sittings()` times it at the first
  fill; that must be stated, not inherited by accident);
- the de-duplication rule for several fills of one `manual_orders` row —
  a part-filled IOC is one purchase, not several;
- the exclusion of demo-instance and session-test fills;
- the unwired predicate of A1.3.3.

**Ruled: P3 needs its own committed script. It may import
`analyse_bet_presence.SITTING_GAP_MS` and `sittings`; it may not inherit
anything else by reference.**

### A1.4.3 P1 is not satisfied, and what is owed is narrower than a full entry-design ADR

- **ADR 0113** records Joe's correction, which is the motivation for P1 rather
  than the design P1 asks for. This document already said so at `:657`.
- **ADR 0114** decides that the buy button agrees with the order route. It says
  nothing about entry into `parlay_positions`.
- **ADR 0125** genuinely decides part of it — *"Buying a combination through
  the desk is now sufficient to have it watched. No second tap"* — and it
  decides that the manual form survives. That is partial satisfaction.

What none of the three settles is **what the manual form is now for**: the
residual population of holdings the wiring cannot reach. That set is (i) combos
bought in the Kalshi app rather than through the desk, (ii) sportsbook slips,
which §8 makes permanently unmeasurable at any `n`, and (iii) wiring failures —
`_record_combo_position` returning `None` or raising into the swallowing
`except` at `backend/api/routes.py:3850-3866`.

**Ruled: P1 is owed, and what it owes is a decision on that residual
population — whether the desk intends to serve it or drop it.** P1 and P3 are
now the same question from two sides: until the residual population is decided,
P3 cannot define its denominator.

## A1.5 RULING 4 — the reconciler is permitted, under a declared name

**Permitted, and it would have been permitted even had A1.3 not voided the
window.** §8's governing sentence is *"A session that wants to peek may peek;
it may not decide"*, and §8 handles the always-valid hazard **by construction
rather than by a boundary**: the stopping point is defined on `G`, computed
from `fills`, independent of the outcome. An extra look therefore cannot move
the threshold, and the formal multiplicity cost of this read is **zero**.

The operational case is stronger than the measurement case is weak.
`_record_combo_position` runs inside a `try/except Exception` that swallows
every failure by design (`backend/api/routes.py:3850-3866`) — correct, since
bookkeeping must never fail a purchase that has already spent money — which
means the write can fail **silently**. A silent failure leaves Joe holding an
unwatched enter-only position. This walk is the only detector that failure mode
has, and a real-money operational blind spot outranks a measurement concern
that is nil.

**Declared here so it can never be mistaken for the §8 read:**

- **Name and scope.** A committed read-only subcommand of
  `scripts/inspect_live_db.py`, declared here **before** it is pointed at live.
  It walks filled non-dry-run `manual_orders` combination rows and lists those
  with no `parlay_positions` row.
- **It reports a join gap, per order. It may not report a rate.** Forbidden
  outputs, named so the discipline is checkable rather than intended:
  no `COUNT(*)` of `parlay_positions`, no `GROUP BY source`, no `R`, no `G`, no
  sitting grouping, no proportion, no interval, no per-day figure.
- **Its module docstring carries the harness rule's paragraph**, naming that it
  is not the §8 census, that it carries no verdict on `R/G`, and that a gap it
  reports is not evidence about adoption.
- **Every invocation prints a line saying so** in its own output. A future
  reader finds the disclaimer in the artifact, not only in the source.
- **Ordering.** It is the correct instrument for A1.2 as well: commit this
  amendment, commit the reconciler, run it against live, then write the orphan.
  Discovering the orphan set by walking beats asserting it from memory.

## A1.6 The successor's power, computed now rather than after

Applied to A1.3.3's re-scoped population, because a re-scope that cannot reach
its own floor should be killed rather than registered.

§8's floor is `G = 30` with a hard backstop of **2026-11-30**. A window
reopened on, say, 2026-09-15 has **76 days**, so it needs a sustained
**0.39 unwired qualifying sittings per day**. §3.3's measured total is
**0.7–1.2 qualifying sittings/day**, all sources. So the successor reaches its
floor only if **roughly a third to more than half of Joe's combination sittings
stay outside the cockpit** for the whole window.

**That is the branch in which ADR 0113's stated intent fails.** The successor is
powered only when the desk is not doing the thing it was just built to do, and
underpowered exactly when it works. **No direction is predicted here and none
may be read into this.** The arithmetic is stated so that P1's ADR makes its
choice knowing it: if the desk intends to capture combination buying, the
successor should be **killed**, not re-scoped, and the manual form kept on the
`/hedge` argument (§9.2 — the route is the exit, the form is entry for a record
of one) rather than on an adoption count it can never earn.

**Recommendation, for P1's ADR to accept or reject: KILL the adoption
successor; keep the form.** Not decided here — P1 decides — but registered here
so the decision is not made silently by a window that quietly never fills.

### A1.6.1 The 2026-09-15 census is discharged, not skipped

§8's census had exactly one permitted use: *"a planning value for `n` in the
successor registration's power check"*. Under A1.3.3 the successor's `n` is a
count of unwired sittings from `fills` and `manual_orders`, not a count of
`parlay_positions` rows, so that use has lapsed. §10 nonetheless owes the
document, because a promised destination that goes unwritten is the failure
mode §10 exists to prevent.

**`docs/measurements/2026-09-15-parlay-positions-census.md` is still written on
or after 2026-09-15.** It records A1.1's `0` and the 2026-09-09 look that
produced it, records that its planning purpose lapsed and why, carries the
sentence *"this is a census and carries no verdict"* in its first paragraph,
and stops there.

## A1.7 What this amendment does not change

§8's vacating of the deletion clause; §12's caveat list, every item of which
still holds; §6's estimator and its prohibition on `sqrt(p(1-p)/G)`; §3's power
arithmetic; §4's rejection of the `source` re-cut; §7 P2, which is satisfied and
deployed (Appendix A); Appendix A's deploy timestamps, run id, head sha and
machine id; ADR 0125, which is correct and is not criticised here — it fixed a
real hole in the exit path and the measurement was collateral.

## A1.8 What this amendment does not establish

- **That the wiring works.** It has written zero rows. A1.1's `0` is consistent
  with a correct wiring that has had no post-deploy fill and with a wiring that
  fails silently every time; A1.5's reconciler is what separates them, and it
  has not been run.
- **That hedging is wanted, or unwanted.** Unchanged from §12: every version of
  this check measures entry, and entry is a prerequisite for demand rather than
  a measurement of it.
- **That the orphan write is representative of anything.** It is one row, in one
  sitting, both excluded. It is bookkeeping, not evidence, and it may not appear
  in any sentence about adoption.
- **That `G = 30` is reachable.** A1.6 gives the arithmetic and predicts no
  direction. If the realised unwired rate is far from the planning value, the
  floor is not re-fitted after the fact.
- **Anything about edge, `beta`, the gate's 300-game floor, the 0.63-point cost
  headroom, the 51.75% bar or `recommendations`.**

**This amendment is not in force until it is committed.** The A1.2 write must
not be executed before the commit that lands this text — an authorisation that
exists only in a session transcript has not been registered, which is the same
defect §9.1 records against the original check.

## A1.9 Status note — A1.5's reconciler already exists in the working tree

**A status note on a condition, not a new ruling.** Nothing in A1.1–A1.8 moves.
Recorded because A1.5 declares the instrument and a future reader needs to know
it was checked against the declaration rather than assumed to comply.

`scripts/inspect_live_db_parlays.py` (uncommitted at the time of this
amendment, alongside a `scripts/inspect_live_db.py` subcommand registration and
`tests/test_inspect_live_db.py`) carries `_SQL_COMBO_POSITION_GAPS` and
`_q_combo_position_gaps`. Audited against A1.5's four conditions:

| A1.5 condition | status |
|---|---|
| reports a join gap per order, no rate | **met.** `parlay_positions` appears only inside `NOT EXISTS`; no `COUNT(*)`, no `GROUP BY source`, no proportion, no sitting grouping |
| module docstring carries the harness paragraph | **met**, and it names the §8 read explicitly: *"this is not it and must never be recorded as it"* |
| committed before it is pointed at live | **NOT met** — it is uncommitted. A1.5 requires the commit first |
| every invocation says so in its own output | **NOT met** — the disclaimer is in the docstring only. The two `_fetch` titles do not carry it |

**Two things are owed before it runs against live**, and both are small:

1. Commit it.
2. Carry the disclaimer into the printed output, not only the source — one line
   on the gaps section's title or a preamble line above it, saying it is not
   the §8 read and carries no verdict on `R / G`. The reason is A1.5's own: a
   future reader finds the artifact, not the module.

Three design choices in it are **better than A1.5 asked for** and are recorded
so a later edit does not undo them as surplus:

- it includes `partially_filled`, not only `filled` — a part-fill bought
  contracts, and ADR 0125 watches a part-fill at the venue's size;
- it reports `unrecognised_response` **separately and does not count it as a
  gap**. *"We do not know whether money moved"* and *"money moved and nothing
  is watching it"* are different states and collapsing them would hide the
  uncertain one inside the certain one;
- it joins `venue_positions` so `OPEN AT VENUE -- UNWATCHED` separates the
  operational alarm from closed history.

**It matches on `p.combo_ticker = m.ticker`.** That is the correct key and it
is worth naming: it does not match on `source`, so a row A1.2 writes will close
the gap for `manual_orders` id=4 on the next run. That is the intended
behaviour of a reconciler and it is **not** an interaction with `R` — the
query emits no `parlay_positions` row and A1.2's exclusions are what keep that
row out of the statistic.

---

## A1.10 The write happened — the factual line A1.2.3 requires

**`parlay_positions.id = 1`, `created_ms = 1788976165253`
(2026-09-09T17:49:25.253Z).** Until this line existed the row was identified in
A1.2.1 only by description; it is now identified by id.

Written by `scripts/backfill_orphan_combo_position.py`, committed at `d349872`
**before** it ran, per A1.2.3's requirement that the exact arguments live in
git rather than in a transcript. Executed against `/data/cockpit.db` on machine
`7812601a239428` — a `--dry-run` first, which printed the same figures and
wrote nothing, then `--commit`.

The values, all derived and none typed:

    lookup_id        41          (parlay_lookups, status 'priced')
    label            'safe'      (lookup.card_key)
    stake_tenths     1640        (4 contracts x 410 tenths)
    return_tenths    4000        (4 contracts x $1.00)
    legs             3           LAABOS-BOS, COLNYY-NYY, CINLAD-LAD, all 'yes'

`stake_tenths = 1640` equals `venue_positions.exposure_tenths` for this ticker,
read independently from the venue's own poll — the cross-check that the row
describes the position actually held.

**`legs_for_position` reported `labels_are_tickers = True`.** The leg names in
this row are market tickers rather than team names, because the combination was
priced before the desk began recording leg labels. That is ADR 0125's honest
degradation and inventing names was refused; it is recorded here so a reader of
`/hedge` does not mistake it for a rendering fault.

**Both exclusions stand and are restated because this line is where a future
reader lands:** this row is excluded from `R`, and the sitting containing the
`manual_orders` id=4 fill is excluded from `G`. The second is the load-bearing
one — writing the row removed Joe's occasion to record it himself, and leaving
that sitting in the denominator would bias `R/G` downward, toward killing the
form.

### A1.10.1 What the reconciler found, and one thing it got wrong first

The 2026-09-09 read logged in A1.1 returned **three** rows, not one, and its
`exposure` column called all three `OPEN AT VENUE -- UNWATCHED`. Two of them —
`manual_orders` id=1 and id=2 — settled on 2026-09-08.

The query had asked for the newest `venue_positions` row **bearing that
ticker**. But that table is an append-only poll record: a held position is
rewritten every cycle and a settled one is simply not written again. The
absence is the event, and the last present row therefore reports whatever was
true when the position last existed. Silence read as exposure, inside the one
column written to catch silence read as health.

Corrected at `55990c5` to ask whether the ticker appears in the most recent
**successful** `positions` poll, with `ok = 1` load-bearing and separately
tested: taking a failed call as the baseline would make every open position
absent from it and report the lot as closed, turning an outage into an
all-clear. The corrected read returns **one** genuinely open unwatched
position, id=4, and two settled — which agrees with the independent `poll_log`
evidence already on the record that the 09-08 pair closed.

**This is recorded rather than quietly fixed** because the first reading was
taken against live and is what A1.1 logs. Anyone re-reading A1.1's census must
use the corrected instrument.


---

# AMENDMENT 2, 2026-09-09 — Joe killed the adoption successor, and the entry design is now settled by argument rather than by a count

**Appended, not edited in.** §10's rule, the same one Amendment 1 followed.
**Nothing above this line has been changed** — not §8's text, not Appendix A's
timestamps, not Amendment 1. What changes is the **status** of several clauses
above, and every one of them is named below rather than left to be inferred.

## A2.0 The decision and its authority

Joe, 2026-09-09, in answer to Amendment 1 §A1.6's recommendation. His words,
verbatim and complete:

> **"kill the adoption successor"**

That is the authority. It is a **decision**, not a measurement, and it is
exactly the shape Amendment 1 asked for: A1.6 registered the arithmetic showing
the successor is powered only in the branch where the desk fails at its own
stated purpose, and put the choice to P1's owner rather than letting a window
quietly never fill. The choice was made in the open, before any window
accumulated, and it is recorded here in one line so no later session
reconstructs it as a drift.

**This section does not reopen it.** No count, no `n`, and no later reading may
be offered as grounds to revisit; see A2.3 for what reopening actually requires.

## A2.1 The successor will not be written, and what that does to the claim

**There is no successor registration. There is no `G = 30` window, no `R`, no
`G`, no `R / G`, and no path to a REFUTED verdict on the entry design.** §7's
preconditions P1–P4 no longer gate anything, because the thing they gated does
not exist.

Said as plainly as the coordinator asked for, and with the quantifier weakened
to what is actually true:

> **The manual entry form is not refuted, and it will not be refuted by this
> registration or by any successor to it — because the only instrument that
> could refute it has been killed by decision rather than exhausted by data.**

Three readings that must not be taken from that sentence:

- It is **not** "not yet refuted". Nothing is pending. There is no future date
  on which a verdict arrives.
- It is **not** "the form is vindicated". No adoption evidence exists in either
  direction; §3.1 established the clean exposure was `G = 0` before any of this,
  and it stayed there. **Absence of a refutation is not a finding.**
- It is **not** "the form can never be questioned by any design ever". A
  materially different design — a different estimand, a different unit, a
  different instrument — could bear on it later. **This amendment forecloses
  this lineage, not the subject.** See A2.9.

## A2.2 §8's three branches — status of each, stated so none reads as live

§8's decision rule is quoted verbatim above and stays quoted verbatim; its
branches are **unreachable**, not pending. A future session finding §8's
REFUTED branch and not this amendment would believe a deletion rule is armed
and waiting. It is not. Branch by branch:

| §8 branch | status after 2026-09-09 |
|---|---|
| `G >= 30` and `R = 0` → **REFUTED** | **VOID — unreachable.** No window accumulates `G`, no committed script computes it (P3 was never written), and the antecedent `G >= 30` can therefore never be satisfied. **This branch may not be cited as a live deletion rule, or as a rule that would have fired.** |
| `G >= 30` and `R >= 1` → **NOT REFUTED** | **VOID — unreachable**, on the same antecedent. The form's survival rests on A2.6 and on the ADR at A2.9, **not** on this branch having been met. |
| `G < 30` at 2026-11-30 → **UNDERPOWERED** | **VOID — and it does not fire on 2026-11-30 either.** There is no window to be underpowered. **2026-11-30 is not a date on which anything happens** and no calendar entry may carry it. |
| *"`source = 'sportsbook'` never carries a verdict, at any `n`"* | **STANDS.** It was never conditional on a successor. `fills` cannot see a third-party slip; that arm has no denominator and can never have one. |
| §8's **vacating of the deletion clause** | **STANDS, and is strengthened** — see A2.3. |
| §8's **census permission** | discharged; see A2.4. |

**The single sentence a future session needs:** *no count of `parlay_positions`,
taken on any date, over any window, may be cited as evidence about whether the
entry form or the hedge route is wanted.* That was true under §8 for one window;
it is now true without a window, because the measurement route is abandoned.

## A2.3 The deletion question is CLOSED, not deferred

§8 vacated the deletion clause and forbade any session from deleting,
disabling, unlinking or ceasing to deploy `/hedge`,
`backend/api/routers/hedge.py`, `backend/core/hedge.py`, the hedge watcher,
`parlay_positions` or `parlay_position_legs` **on the strength of any count**.
That prohibition stands in full.

**It is now CLOSED rather than DEFERRED, and the distinction is load-bearing.**
"Deferred" would mean a verdict is coming and the question is parked until it
arrives. No verdict is coming. Leaving the word "deferred" in the record would
create a standing expectation that some future count settles this, which is the
precise misreading A2.2 exists to prevent.

**What reopening requires, stated exactly:**

- **A new decision from Joe, with a stated reason, in his own words.** This is
  the form ADR 0105 §5 already uses for its own overturning condition — *"Joe
  saying so"* — and it is the form his kill instruction took.
- **Not a measurement.** A count, a rate, a census, a low usage number, a quiet
  observation that a table looks empty: **none of these reopens it**, and a
  session that proposes one has proposed the route that was abandoned.
- **Not the passage of time.** No date reopens it. A calendar entry is not a
  reason (§13's own correction: *"a date is not a reason"*).
- **A reopening that does happen is recorded as an ADR**, so the reason is in
  the record rather than in a session.

## A2.4 The 2026-09-15 census is NOT owed — discharged, with its figure already in the record

A1.6.1 kept `docs/measurements/2026-09-15-parlay-positions-census.md` owed
under §10's rule that a promised destination must not go unwritten. **That
obligation is discharged and the document is not owed.**

The reasoning, because "we decided not to write it" is exactly the shape of the
failure §10 guards against and this must be shown not to be it:

- §10's rule protects an unwritten **number**, not an unwritten **filename**.
  The failure mode it names is a negative result that quietly never gets
  written. **That number is written**: A1.1 item 4 records `parlay_positions`
  read on live on 2026-09-09 holding **0 rows**, dated, sourced, in a committed
  file, with its status as a verdict-free interim census recorded beside it.
- §8 gave the census exactly one permitted use — *"a planning value for `n` in
  the successor registration's power check"*. There is no successor and no
  power check. **The use has lapsed; the figure has not.**
- A separate document would therefore restate a figure already in the record,
  under a heading implying a measurement programme that no longer exists. That
  is worse than not writing it.

**One correction that must be carried, or the record misleads.** The executing
session made Amendment 1 §A1.2's authorised write, so `parlay_positions` on live
is **no longer 0** — it holds `id = 1` (A1.10). A1.1's `0` stands as a **dated
observation of 2026-09-09 taken before that write**, and may not be quoted as a
current count. The row it gained is the A1.2 row, excluded from `R` and its
sitting from `G` — an exclusion that now protects nothing, because there is no
`R`, and which is left standing anyway so the row's authorship stays legible
(A2.7.3).

**Two different figures on the same page, not to be conflated.** A1.1's `0` is
a count of `parlay_positions` rows. A1.10.1's `three` is the number of orphaned
`manual_orders` combinations the reconciler's gap query returned — the
complement, and on its first uncorrected reading at that. They count different
things in opposite directions, and A1.10.1's own instruction governs the second:
anyone re-reading it must use the corrected instrument (`55990c5`), which
returns one genuinely open unwatched position and two settled.

## A2.5 P4 and the window — nothing here revives it

The window opened at `2026-09-08T21:33:05Z` was closed and voided as of
`2026-09-09T15:56:45Z` by Amendment 1 §A1.3.2, on two independent grounds: the
estimand was superseded by ADR 0125's wiring, and P3's denominator script was
never committed before the window opened (§A1.4.1).

**Nothing in Amendment 2 revives it, shortens it, extends it or reinterprets
it.** P4's clock is not restarted, because there is nothing to time. Appendix
A's deploy record — run `34281066870`, head sha `a13e6b8`, finished
`2026-09-08T21:33:05Z`, machine `7812601a239428` — stays in the file as the
factual record of the P2 deploy, and **as nothing else**. It is no longer the
start of anything.

## A2.6 What is NOT killed — the clause a future session will misread

Killed: **the adoption successor registration, and only that.** It was never
written and now never will be.

**Not killed, in terms:**

- **`/hedge`** — the route, the screen, the watcher, the arithmetic.
- **`backend/api/routers/hedge.py`, `backend/core/hedge.py`, `backend/hedge.py`.**
- **`parlay_positions` and `parlay_position_legs`**, both tables, and every row
  in them.
- **`POST /api/hedge/positions` and `RecordParlay.tsx`** — the manual entry
  form, on all seven surfaces of §2's table, in the no-default form P2 shipped.
- **ADR 0078 Decision 1**, which stands untouched: a `KXMVE` combination is
  enter-only, and hedging a leg market is the only exit it has. Joe is buying
  more of them through the desk — the first two fills landed 2026-09-08 and a
  third on 2026-09-09 — so the exit is **more** load-bearing than when ADR 0078
  was written, not less.
- **ADR 0125's wiring**, which is correct and is not criticised anywhere in this
  registration. It fixed a real hole in the exit path; the measurement was
  collateral damage, and that trade was the right way round.
- **`gate.py`'s boundary** (ADR 0078 §4, ADR 0063): it still never reads either
  table, and nothing here changes that.

§9.2's separation is what makes this coherent and it is worth restating once:
**the route is the exit for a position; the form is the entry for a record of
one.** An argument about the form was never an argument about the route.

## A2.7 The provenance column is DROPPED — Joe's decision, recorded

Amendment 1 §A1.3.3 required a provenance column on `parlay_positions`. Joe,
2026-09-09, in answer to that requirement. His words, verbatim and complete:

> **"drop the provenance column"**

**A1.3.3's requirement is withdrawn on the operator's decision.** It is not
deferred, not conditional, not owed to any queue. This section records the call
and its consequence; it does not re-argue it, and no later session may cite the
paragraphs below as grounds to revisit it.

### A2.7.1 What is given up, stated once

**A hand-written row and a wiring-written row are indistinguishable in
`parlay_positions`, permanently, and anyone who later wants to separate them
cannot do so retroactively.** The two writers — `POST /api/hedge/positions`
(`backend/api/routers/hedge.py:73`) and ADR 0125's path
(`backend/api/routes.py:4228`) — reach one `INSERT` at `backend/hedge.py:334`,
and every field that might have carried the distinction (`note`,
`combo_ticker`, `parlay_lookup_id`) is accepted from the request on the manual
route (`backend/api/schemas.py:308-310`).

The loss is not "hard to reconstruct". **The discriminating fact is never
written down**, so there is nothing from which to reconstruct it. That is
different in kind from a derived quantity, and A2.7.4 turns on the difference.

### A2.7.2 Why that is affordable — and where the case I made was overstated

The coordinator's reading, checked rather than adopted: *attribution only ever
mattered for `R`, `R` is dead, and `/hedge` sizes off stake, return and legs
rather than off who recorded the row.* **That reading is correct, and my
A1.3.3 operational case was weaker than I stated it.** Three concessions, made
specifically rather than generally:

1. **Provenance does not enter the hedge arithmetic.** The equalising hedge is
   computed from `stake_tenths`, `return_tenths` and the legs. A column would
   have changed no number `/hedge` computes.
2. **A label does not fix a wrong stake; it only annotates one.** And at the
   moment `/hedge` matters — a position minutes to hours old, watched while the
   game runs — **the reader of the row is the person who typed it.** The column
   would tell the operator something about his own row that he already knows.
3. **The `resolved_source` precedent I cited is not parallel, and I over-read
   it.** That column separates evidence about an *outcome* the reader cannot
   re-derive: whether a leg won, from `kalshi_markets.result` against Joe's
   word. A stake is a number its writer knows he typed. Citing an adjacent
   column because it is adjacent is the tidier story, and it is the thing this
   registration is supposed to catch.

**The residual, so the record is not falsely reassuring in the other direction
either.** The case that genuinely survives is a **reader who is not the
writer** — an agent-written row, or any row read long after the fact. Today
that population is exactly one row, and it is named (A2.7.3). Coverage is
therefore complete now, and thin only under the growth condition in A2.7.4.

### A2.7.3 What replaces the column — a written record naming the row by id

**This is the thing a future session will need, and it lives in the amendment
rather than in the schema.** Say it here explicitly:

> **`parlay_positions.id = 1`, `created_ms = 1788976165253`
> (2026-09-09T17:49:25.253Z), was written by an agent session and not by Joe.**

It is recorded in A1.10 with its derived values, its `venue_positions`
cross-check and the script and commit (`d349872`) that wrote it, and its own
`note` column denies Joe's authorship in terms — *"This is NOT an act of
recording by Joe."*

**A written record identifying a specific row by id is what replaces the
column.** The threat model changed with the successor, and that is why prose is
now sufficient where A1.3.3 said it was not: A1.3.3 argued **forgeability** —
that a hand row could be *made* to look wired — which matters when a statistic
is being defended against selection. With no statistic, the threat is not an
adversary but an honest reader who cannot tell. **A row id in a committed file
answers that, and does not get lost.**

### A2.7.4 The reopening condition, and why it is stricter than P3's

**If a future registration ever needs to count `parlay_positions` rows by
author, it must add the column BEFORE its window opens.** This is the same
"before" clause A1.4.1 ruled fatal for P3, named here while the reason is
fresh — and it binds harder:

- **P3's breach was curable in principle.** A denominator is computed from
  `fills`, the raw material survives, and a script written late can still be
  run over data written earlier. What P3 lost was the guarantee that the rule
  was not tuned to the outcome.
- **This one is not curable at all.** Authorship leaves no raw material.
  **A column added later recovers attribution for nothing written before it**,
  so the rows accumulated in the meantime are permanently unattributable and
  would have to be excluded wholesale — which, for a table whose whole history
  predates the column, means excluding the history.

So: **not a rule that can be broken and written up as a deviation.** Any such
registration starts its window at the migration, not before it.

**And the growth condition, which is the honest limit on A2.7.3.** The prose
mechanism works because agent-written rows are exceptional — one, today. If
backfills or agent writes stop being exceptional, a per-row prose record rots,
and the answer at that point is the column plus a window that starts there, not
a longer list of ids in a measurement document.

### A2.7.5 One justification this decision makes stale

`scripts/backfill_orphan_combo_position.py`'s docstring says *"Amendment 1
A1.3.3 rules that provenance must become a **column** ... That column does not
exist yet."* **That now cites a withdrawn requirement**, and "does not exist
yet" reads as pending when it is dropped. Per `tasks/lessons.md`'s pattern that
justifications decay toward reassurance, it should be re-based on A2.7 when the
file is next touched. Recorded, not urgent: the script has run once and is not
on any path.

## A2.8 The holes this kill leaves, named rather than tidied

The kill is the right decision and A1.6's arithmetic is why. It is still a
trade, and these are the things given up. None of them is an argument to
reopen A2.0.

1. **The form can no longer be removed on evidence.** Its only death is now
   Joe's word (A2.3). It survives by default, carrying real maintenance cost —
   seven surfaces, the no-default control, `schemas.py`'s validation, and
   `tests/test_recording_a_bet_is_reachable.py`'s guards. **A feature that can
   only be killed by decision tends not to be killed.** That is the trade, made
   knowingly.
2. **The residual population's size is unknown, and its recording behaviour is
   now unmeasurable by choice.** The census constants say 51 of 52 combination
   positions over 18 days were venue taker fills, and the cockpit's first fills
   were 2026-09-08 — so historically nearly all of Joe's combinations were
   bought outside the desk. Whether that persists decides whether the form is
   load-bearing or nearly dead, and **we have chosen not to know.**
   **Partially mitigated, and only partially:** `combo-position-gaps` and the
   latest successful `positions` poll can show that a `KXMVE` position exists
   at the venue with no `manual_orders` row — i.e. that the population is
   non-empty. **They cannot show whether Joe records one**, because that
   quantity is `R`, and `R` is what was killed. The population is observable;
   the behaviour is not.
3. **P2's justification is now stale, and stale justifications are a named
   pattern here.** The no-default form was built so a window would be clean.
   That window is void and no successor will open. **The no-default control is
   still right** — on its own terms, that the instrument must not answer the
   operator's question for him — but any comment or test docstring justifying
   it by the measurement now points at a dead programme. It should be re-based
   on the UX argument when next touched. A2.7.5 records a second instance of
   the same decay, from a different cause, on the same day.
4. **Not a new hole, and named so it is not double-counted:** the value of the
   hedge arithmetic itself remains untested. §12 already said so — it *"would
   remain untested at `G = 300`"* — so the kill takes nothing away here. Entry
   was always a prerequisite for demand rather than a measurement of it.

## A2.9 What Amendment 2 does not decide

- **What the form is for.** That is P1's question, it survives the kill, and it
  is answered by a separate document —
  `docs/adr/0130-the-manual-hedge-form-is-for-what-the-wiring-cannot-reach.md`,
  which takes its ordinal at merge. **This amendment records that P1 is no
  longer a measurement precondition and is now a standing justification
  requirement**, and nothing more.
- **Whether adoption or calibration is worth measuring by some other design.**
  A materially different estimand, unit or instrument is not foreclosed. What is
  foreclosed is this lineage: this registration, its §8 branches, and any
  successor to it. A new design starts from a new registration and its own power
  check, inherits nothing from here except §12's caveats, and — if it needs
  authorship — is bound by A2.7.4.
- **Nothing is owed on the provenance column.** A2.7 records it **dropped on
  Joe's decision**, not deferred and not queued. There is no half-obligation,
  no owner, and no follow-up ticket; a session that finds A1.3.3's requirement
  and not A2.7 has read half the record.
- **Anything about the disarmed bid path** (ADR 0115), which rests offers and is
  untouched by every clause here.
- **Anything about edge, `beta`, the gate's 300-game floor, the 0.63-point cost
  headroom, the 51.75% bar or `recommendations`.** ADR 0038 stands. `gate.py`
  still may not read either table.

**This amendment is not in force until it is committed**, on the same terms
Amendment 1 closed with: an authorisation that lives only in a session
transcript has not been registered, which is §9.1's defect against the original
check.
