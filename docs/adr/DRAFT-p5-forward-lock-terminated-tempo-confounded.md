# DRAFT — P5 terminates at UNRESOLVED — TEMPO-CONFOUNDED, and that is final

- **Status:** Proposed. Draft in a lane; the ordinal is taken in the merge
  commit, after `git fetch`, per `docs/adr/README.md`.
- **Date:** 2026-09-02
- **Ruling by:** the `partner` agent, 2026-09-02, on the 19:01Z reading.
- **Related:** ADR 0091 (the defect this study was raised to confirm);
  `docs/measurements/2026-09-01-forward-lock-instrument-registration.md` (P5,
  with Amendment 1); `docs/measurements/2026-09-02-forward-lock-instrument-result.md`
  (the registered result this ADR acts on); ADR 0016 (the habit of computing a
  cost before spending the time); ADR 0038 (a closure is a closure).

## Context

P5 is the pre-registered forward instrument asking whether ADR 0091 closed the
`database is locked` symptom. It reached its registered exposure on
2026-09-02 and returned, on the registration's own decision rule:

    E        294 fast cycles     (E* = 160, reached)
    K        0 bursts            H = 0        E_n = 1.0000
    C1-C4    PASS                C6 PASS
    C5       FAIL   post-T0 79.64/h vs pre-fix 56.81/h, tolerance ±25%
    VERDICT  UNRESOLVED — TEMPO-CONFOUNDED   (registration §7, line 470)

The result file records the reading and the case against the verdict in full.
This ADR is about a different question, which the registration does not
answer: **what happens to P5 now.** §10's UNRESOLVED row says *"Open item 1
stays open, with `E`, `K` and the failed precondition recorded so the next look
starts from a number rather than from scratch"* (line 585; Amendment 1 A3 left
it *"Unchanged"*, line 707). Read literally, that keeps taking looks until one
of them passes C5. The partner ruled on 2026-09-02 that no further look is
taken and P5 terminates at the verdict above, **final**, rather than at the
2026-09-15 backstop or at some later reading that happens to pass. Three
grounds, each checked against the registration's text.

### Ground (a): the registration has no exit for this state, and that is the outcome the backstop exists to prevent

§8 defines three ways collection ends (lines 480-500): the primary stop,
`E* = 160` cumulative fast cycles (482-487); the event stop, `E_n >= 200`
(492-494); and the wall-clock backstop, which reads in full:

> **Wall-clock backstop: 2026-09-15T00:00Z.** If `E*` is not reached by then,
> the look is taken at whatever `E` stands at, the verdict is **UNRESOLVED —
> INSUFFICIENT EXPOSURE**, and `E` is recorded so the next look knows where it
> started. The backstop exists so collection cannot run until the answer is
> convenient. (lines 496-500)

**Its condition is "if `E*` is not reached by then." `E*` was reached** —
`E = 294` on 2026-09-02, thirteen days early. So the backstop's clause never
fires, its verdict name (INSUFFICIENT EXPOSURE) is the wrong one for this
state, and nothing else in §8 speaks to a precondition that fails and keeps
failing. §7 says what a failed C5 *means* — UNRESOLVED — TEMPO-CONFOUNDED
(line 470) — and §6.3 says how it is *reported* — *"never shortened to
UNRESOLVED alone"* (lines 418-420). Neither says when to stop reading it.

So without a ruling P5 sits UNRESOLVED indefinitely, re-read whenever someone
wonders, which is precisely the state §8's last sentence names as the thing
the backstop is for — arriving through a door §8 did not model. The
registration guarded against "not enough data yet, keep waiting"; it did not
guard against "enough data, incomparable arms, keep waiting". The second is
the same hazard with the same cure, and the cure has to be applied by hand
because the text does not apply it.

### Ground (b): C5 is moving away, and the arithmetic is structural rather than unlucky

`scripts/inspect_live_db.py` computes the two tempi at lines 2838-2839:

    post_tempo = lines_per_hour(t0, None)
    pre_tempo  = lines_per_hour(None, ADR_0091_DEPLOY_MS)

`lines_per_hour` (2828-2836) is `len(window) / span_h` over every
`loop_rss.jsonl` sample in the window. So `post_tempo` is a **cumulative mean
over a window that grows** with every pass the runner takes, and `pre_tempo`
is a mean over a **fixed** window ending at `ADR_0091_DEPLOY_MS`
(2026-08-31T15:29:19Z, line 2383). The registration wrote both that way on
purpose — *"Passes per hour after `T0`"* against *"the pre-fix figure"* (§7,
lines 468-470) — and the instrument implements it as registered.

Two readings on 2026-09-02:

    16:26Z   22.57 h post-T0   73.92/h   (+30.1%)
    19:01Z   25.15 h post-T0   79.64/h   (+40.2%)   ceiling 71.01/h

A cumulative mean rising that fast means the marginal rate in the 2.58 h
between them was about **130 lines/h — 2.3× the pre-fix tempo**. From where
the mean stood at 19:01Z, getting back inside the ceiling takes roughly
fifteen hours at exactly the pre-fix tempo, seven at 40/h, or three of total
silence — and every hour above 71/h moves those figures out again.

**The driver is what is in season.** The pass tempo follows fixtures and
attention (CLAUDE.md; ADR 0071 §2.6), NCAAF and NFL enter the feed with no
config change (`backend/kalshi/discovery.py:237-238`, as ADR 0095 §2 already
records), and an NFL Sunday is a ~10-hour in-play window against MLB's ~4. The
pre-fix baseline was measured on a late-August calendar; the post-`T0` arm is
being measured on a September one, and the calendar is adding sports, not
removing them.

**This is not "unrecoverable," and the ADR does not say so.** The path back is
a sustained quiet period — a day or more at or below pre-fix tempo — and the
calendar is not offering one. There is also a second clock, found while
writing the result file and recorded there in §4: the pre-fix baseline lives
only in `loop_rss.jsonl`, which now trims from 2 MiB to 1 MiB of newest lines
(`scripts/run_loop.py:175-176`), and the post-`T0` arm alone already exceeds
what a trim keeps. When the first trim fires — on the order of a day from the
19:01Z reading — C4 and C5 become NOT COMPUTED, which the instrument treats as
not-a-pass (`inspect_live_db.py:2849-2856`). A quiet period after that point
restores nothing, because there is no longer a baseline in the file to be
within 25% of.

### Ground (c): nothing consumes the formal verdict, and the strongest evidence is exactly the kind that must not be written as confirmation

Amendment 1 A4 already found, blind, that only FIX CONFIRMED still bought
anything — *"the right not to chase two suspects nobody has scheduled"* (lines
704, 717-719) — and that MIRROR RESIDUAL and UNRESOLVED *"buy nothing but a
recorded number"* (lines 715-717). It deliberately declined to rule on whether
the study was still worth the exposure, because answering that *"after seeing
a result is the contamination this document exists to prevent"* (lines
724-726).

The result is now seen, and it is the best case: `K = 0` across 294 post-`T0`
fast cycles, on an arm 40% busier than the one the pre-fix rate was measured
on, with `P(K = 0 | rate unchanged) ≈ 4 × 10⁻⁵` under the planning `lambda_0`.
There is no reading of the same instrument that would be *more* favourable to
ADR 0091 than this one. And the registration forbids crediting it, for reasons
the result file gives in its §3.2 and this ADR endorses: the tolerance was
registered two-sided before the data; §9.8 says a verdict does not generalise
across tempo (lines 569-571); and §6.1 says a precondition *"cannot
manufacture a positive one"* (lines 349-353).

Put those together. Further readings can only produce (i) the same verdict
with a bigger `E`, (ii) NOT COMPUTED once the baseline rolls off, or (iii) a
FIX CONFIRMED that a later quiet window happens to license — which would be a
verdict *selected by the calendar*, the optional-stopping shape §6.2 built the
e-value to avoid on the other arm. None of those is consumed by anything. ADR
0091 is a real defect fix with or without this study, `badd88e` already made
the victim loop survive the next lock whatever holds it (Amendment 1 A1), and
the §0.4 successor was killed on 2026-09-01. The recorded number is recorded.
There is nothing left for another look to buy.

## Decision

**P5 terminates now, at UNRESOLVED — TEMPO-CONFOUNDED, final.** The 19:01Z
reading of 2026-09-02 is its last registered look, and
`docs/measurements/2026-09-02-forward-lock-instrument-result.md` is the file
§10 required. No reading taken after it is a P5 look, and none may be quoted
as one.

Four things this ruling is explicit about, because each is the obvious next
move and each is refused:

1. **C5's tolerance is NOT amended.** The ±25% two-sided band stands in the
   registration (§7, lines 468-470) and in `C5_TEMPO_TOLERANCE`
   (`inspect_live_db.py:2397`). The observation that a *busier* victim is not
   the confound §7 feared is a **design note for the next comparability check
   anyone registers** — a one-sided lower bound may well be the right shape —
   and it goes into that registration, written blind, not into this one with
   +40% on the screen. Amending now would make the amendment the finding.

2. **No successor registration is opened.** §0.4's ~84-hour design was *"not
   authorised here"* (line 100) and was killed by the partner on 2026-09-01 on
   the ground that the harm is already mitigated — `badd88e` makes one lock
   error cost one closing line rather than the pass (`backend/scoring.py`,
   per Amendment 1 A1). A study whose positive branch buys only the right not
   to chase two unscheduled suspects does not earn a second run on a new
   calendar. If someone later wants the question reopened, ADR 0038's rule
   applies: name what this ADR got wrong and the measurement that shows it.

3. **This terminates at the *unflattering* verdict, and the reasoning is on
   the page so nobody reads "the partner killed a study" and reopens it.** The
   pattern this repo distrusts — and has caught in itself more than once — is
   stopping when the answer is convenient: the 2026-08-24 signal-test screen
   that declared on a pooled population, the "quiet run" for ADR 0091 that
   began before the fix deployed. §8's backstop exists for that pattern. This
   ruling is its inverse: it stops at the verdict that credits nothing, when
   the evidence on the table would have credited the fix under any rule chosen
   after the fact, and it refuses the amendment that would have turned that
   evidence into a declaration. Terminating here costs the flattering outcome;
   continuing would have been the way to reach it. That asymmetry is the
   whole reason the ruling is safe to make after seeing the data.

4. **§10's UNRESOLVED row is overridden, and that is an action-table change
   made after the result — named, not hidden.** Amendment 1 A6 warns that the
   action table *"keeps rotting while the registration waits"* and is *"the
   one section that becomes uncorrectable the moment a result is visible"*
   (lines 750-757). The defence is the same one Amendment 1 gave for itself:
   the change moves *"only in the direction of claiming less"* (line 748). It
   kills a look; it credits nothing; it changes no threshold, no population,
   no statistic and no decision rule. A post-hoc change that removes the
   possibility of a favourable verdict is the one kind that cannot be
   selection.

## Consequences

**Killed:**

- The P5 open item in `tasks/NEXT.md` (open item 1 of the 2026-09-02 entry's
  "Still open" list). It closes as UNRESOLVED — TEMPO-CONFOUNDED, not as done.
- Any re-read of `inspect_live_db.py forward-lock` **as a verdict source**.
  The subcommand still prints a `VERDICT` line, because removing it would be a
  code change to an instrument this ADR keeps; a reader who runs it after
  2026-09-02T19:01Z is reading a diagnostic, and the line it prints is not a
  P5 result. If that ever confuses someone, the fix is a one-line note in the
  section title citing this ADR, not a new look.
- The 2026-09-15 backstop as a date anyone waits for. Its clause never fired.

**Kept:**

- **The instrument itself**, `scripts/inspect_live_db.py forward-lock`, as a
  diagnostic. It is the only thing in the repo that splits bursts by matched
  cycle into MIRROR and FAST, ages a cycle against evidenced process liveness,
  and reads `wal_kb` and tempo out of `loop_rss.jsonl` with the
  `produced_by`-absent-versus-null distinction right. The next lock
  investigation, if there is one, starts from it. Nothing in it is deleted or
  disabled by this ADR.
- **ADR 0091, standing as a real defect fix that is neither credited nor
  refuted on this evidence.** Its own "What this does NOT establish" section
  said *"a fit is not a proof"* and named the retention prune and the
  `TRUNCATE` checkpoint as unexamined suspects. That is still exactly its
  status. It does **not** gain the "confirmed on live evidence" note §10's
  FIX CONFIRMED row would have given it, and any future sentence claiming the
  symptom is closed must cite something other than P5.
- **The registration, unamended.** Every threshold, the population, the unit,
  the band, the stopping rule and C5's tolerance are as registered. This ADR
  adds a termination the registration lacked; it changes nothing the
  registration fixed.
- **The observation about C5's direction**, as a design input to whoever next
  registers a comparability precondition: state which direction of difference
  is the confound, and whether the other direction is a refusal or merely a
  note.

**What this does not establish:**

- That the `database is locked` symptom is gone. `K = 0` over 25 hours of one
  tempo, through one failure hook, is a floor on nothing and a proof of
  nothing.
- That a quiet week in the calendar would not have passed C5. It might have.
  The ruling is that waiting for it would have been selecting the look by the
  answer, not that the answer would have been wrong.
- That the tolerance *should* have been one-sided. That is the design note,
  and it is a note.
