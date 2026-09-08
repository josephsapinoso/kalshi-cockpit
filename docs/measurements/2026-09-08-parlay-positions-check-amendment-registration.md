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

**The window is NOT open yet and no date is recorded here.** P4 requires the
timestamp to be looked up from the deploy that ships this code, not recalled
or predicted. At the time of writing the code is committed and not yet
deployed. **Whoever deploys it records the deploy timestamp here**, and the
window opens then.

**P1 and P3 are still open** and P2 does not advance either. P1 needs an
accepted ADR recording the entry design; ADR 0113 records that Joe wants to
place singles and combinations through the cockpit, which is the *correction*
that motivated P1, not the design document P1 asks for. P3's denominator
script does not exist.
