# DRAFT — P5 terminates at UNRESOLVED — TEMPO-CONFOUNDED, and that is final

- **Status:** Proposed. Draft in a lane; the ordinal is taken in the merge
  commit, after `git fetch`, per `docs/adr/README.md`.
- **Date:** 2026-09-02
- **Ruling by:** the `partner` agent, 2026-09-02, on the two readings below.
- **Related:** ADR 0091 (the defect this study was raised to confirm);
  `docs/measurements/2026-09-01-forward-lock-instrument-registration.md` (P5,
  with Amendment 1); `docs/measurements/2026-09-02-forward-lock-instrument-result.md`
  (the registered result this ADR acts on); ADR 0016 (the habit of computing a
  cost before spending the time); ADR 0038 (a closure is a closure).

Every `scripts/inspect_live_db.py:NNNN` citation is to the repo copy at this
branch's HEAD, not diffed against `/app/scripts` on the live box.

## Context

P5 is the pre-registered forward instrument asking whether ADR 0091 closed the
`database is locked` symptom. Two readings were taken on 2026-09-02, both past
the registered `E* = 160`:

    registered look    16:26Z   E = 263   K = 0   H = 0   E_n = 1.0000
                       C1-C3 PASS   C6 PASS
                       C4 FAIL   median wal_kb post-T0 2,699 vs pre-fix q25 2,711   (-0.44%)
                       C5 FAIL   post-T0 73.92/h vs pre-fix 56.81/h                  (+30.1%)
                       VERDICT   UNRESOLVED — C4/C5

    unregistered       19:01Z   E = 294   K = 0   H = 0   E_n = 1.0000
    re-read            C1-C4 PASS   C6 PASS
                       C4 now 2,711 vs 2,711 — a FAIL by 12 KB became a PASS by 0 KB
                       C5 FAIL   post-T0 79.64/h vs pre-fix 56.81/h                  (+40.2%)
                       VERDICT   UNRESOLVED — C5

§6.2 registers the rate arm as *"a single look at `E*`, no early stopping"*
(registration lines 386-390), so the 16:26Z reading is P5's one registered
look and **UNRESOLVED — C4/C5** is its verdict; the result file carries that
in its title. The 19:01Z reading was taken to see which way the tempo was
moving and is not a P5 look. **This ADR's title names C5 rather than C4/C5
because C5 is the precondition that fails at both readings and is the one
moving away; C4 sat on its own threshold and crossed it on noise.**

The result file records the readings and the case against the verdict in
full. This ADR is about a different question, which the registration does not
cleanly answer: **what happens to P5 now.** The partner ruled on 2026-09-02
that no further look is taken and P5 terminates at the verdict above,
**final**, rather than at the 2026-09-15 backstop or at some later reading
that happens to pass. Three grounds, each checked against the registration's
text.

### Ground (a): the registered look has been taken, and §10's "next look" is a phrase, not a licence

§8's primary stop is `E* = 160` cumulative fast cycles (lines 482-487), and
§6.2 says what happens there: *"Rate arm — a single look at `E*`, no early
stopping. Its statistic is not a supermartingale under optional stopping and
may not be peeked at"* (lines 386-390). Collection for the rate arm ended when
`E` crossed 160, and **exactly one look was licensed** — the first reading
past it, 16:26Z. The wall-clock backstop (lines 496-500) is conditioned on
*"If `E*` is not reached by then"*; `E*` was reached thirteen days early, so
that clause never fires and its verdict name (INSUFFICIENT EXPOSURE) is not
this state's.

What actually needs a ruling is narrower than a gap in §8. §10's UNRESOLVED
row says the failed precondition is recorded *"so the next look starts from a
number rather than from scratch"* (line 585; Amendment 1 A3 left it
*"Unchanged"*, line 707). Read as an instruction, that phrase is a licence to
keep reading the rate arm until a precondition happens to pass — a licence
§6.2 does not grant and expressly refuses. Amendment 1 A6 already named §10 as
*"the section least protected by pre-registration and the one most likely to
be wrong"* (lines 758-760). **The conflict is resolved in §6.2's favour:** the
"next look" §10 imagines would be a second look at a statistic registered for
one, and the number it "starts from" is recorded in the result file for
whoever registers a successor — not for P5.

This ruling therefore does not add a termination the registration lacked. It
reads the termination the registration already has, over a sentence in its
least-protected section that could be read the other way.

### Ground (b): C5 is moving away, the arithmetic is structural, and the driver is not established

`scripts/inspect_live_db.py` computes the two tempi at lines 2838-2839:

    post_tempo = lines_per_hour(t0, None)
    pre_tempo  = lines_per_hour(None, ADR_0091_DEPLOY_MS)

`lines_per_hour` (2828-2836) is `len(window) / span_h` over every
`loop_rss.jsonl` sample in the window. So `post_tempo` is a **cumulative mean
over a window that grows** with every pass the runner takes, and `pre_tempo`
is a mean over a **fixed** window ending at `ADR_0091_DEPLOY_MS`
(2026-08-31T15:29:19Z, line 2383). The registration wrote both that way on
purpose — *"Passes per hour after `T0`"* against *"the pre-fix figure"* (§7,
lines 468-470) — and the instrument implements it as registered; the ±25% is
two-sided in code (2840-2845) and pinned by
`tests/test_forward_lock_instrument.py::test_a_doubled_pass_tempo_also_fails_c5`.

    16:26Z   22.56 h post-T0   73.92/h   (+30.1%)
    19:01Z   25.15 h post-T0   79.64/h   (+40.2%)   ceiling 71.01/h

A cumulative mean rising that fast means the marginal rate in the 2.59 h
between the readings was about **129.5 lines/h — 2.3× the pre-fix tempo**
(the derivation reproduces the instrument's printed `n = 2002` to within a
line). From the 19:01Z state, coming back inside the ceiling takes roughly
fifteen hours at exactly the pre-fix tempo or seven at 40/h; a silence does
not move the mean, and the gap that would put it under the ceiling once one
line breaks it is 3.08 h.

**The driver is not established, and one candidate is the fix itself.** A
`loop_rss.jsonl` line is written once per pass (`run_loop.py:319-321`), so
lines/hour is set by `Tempo`'s choice of fast or slow interval
(`backend/scheduler.py:309-345`; `DEFAULT_FAST_INTERVAL_S = 15.0` at line 276;
`run_forever` sleeps *after* the pass) plus the pass's own duration. Three
candidates for why it rose, none separated:

1. **More fixtures in the fast window.** The tempo follows fixtures and
   attention (CLAUDE.md; ADR 0071 §2.6), and NCAAF and NFL enter the feed with
   no config change (`backend/kalshi/discovery.py:237-238`, as ADR 0095 §2
   records). An NFL Sunday is — as an estimate, not a measurement — a ~10-hour
   in-play window against MLB's ~4.
2. **The 2026-08-29 attention/floor fall-through** (CLAUDE.md's account of the
   `desk_wants` fix), which made an attended-but-slice-spent sport fall
   through to the floor instead of being skipped. That changed how often the
   runner has something to do, one day before the pre-fix window closes.
3. **ADR 0091's own fix shortening the pass.** The fix removed a write-lock
   hold across three Kalshi round trips from the poller, and the victim's pass
   duration includes whatever it waited on. On plausible numbers — a pass span
   falling from ~25 s to ~10 s on the 15 s fast interval — lines/hour goes
   from ~57 to ~89, which **brackets the observed 56.81 → 79.64**. If that is
   the driver, then **the treatment moved the covariate C5 controls for, and
   no post-fix arm can ever pass C5**: the precondition would be refusing the
   fix for working.

The separating read is not taken and is named so nobody thinks it was: the
fast-mode inter-line gap in `loop_rss.jsonl`, split by `kind` across
`ADR_0091_DEPLOY_MS`, would show whether the fast passes themselves got
shorter. Per-pass duration is observed in-process
(`tempo.observe_pass_duration`, `run_loop.py:1363-1368`) but is **not** a
field on the RSS line, so the read is an inter-line-gap read, not a lookup.
Whichever candidate it is, the calendar is adding sports rather than removing
them, and none of the three is a reason to expect the tempo to fall back.

**This is not "unrecoverable," and the ADR does not say so.** The path back is
a sustained quiet period — on the order of a day at or below pre-fix tempo —
and the calendar is not offering one. There is a second clock, and it has been
handled: the pre-fix baseline lives only in `loop_rss.jsonl`, which trims from
2 MiB to the newest 1 MiB of whole lines (`scripts/run_loop.py:175-176`), and
**the pre-fix window survives the first trim only if it is itself larger than
1 MiB**. It is ≤ 2,567 lines ≈ 736 KB — under 1 MiB even at 400 B/line, a
30-45% margin — so it does not survive. Live `/data/loop_rss.jsonl` measured
**1,900,412 bytes at ~19:40Z, 90.6% of the cap**, so the trim was hours away
at the ruling, not the day the first draft of this ADR estimated. After it, C4
and C5 read NOT COMPUTED on the box, which the instrument treats as not-a-pass
(`inspect_live_db.py:2849-2856`).

**The baseline was preserved out of the repo**: `flyctl ssh sftp get
/data/loop_rss.jsonl` → `data/live-snapshots/loop_rss-2026-09-02T19Z.jsonl`
on the dev machine, 6,066 lines / 1,900,780 bytes, first line
2026-08-29T18:03Z, with `loop_failures.jsonl` beside it. `data/` is gitignored
because operator data never enters the repo, so the copy is local to that
machine. The loss is therefore **avertible and averted for the local copy;
the deployed instrument still loses it** — a fact about where the diagnostic
can be run from, not a door closing on the question.

### Ground (c): nothing consumes the formal verdict, and the strongest evidence is exactly the kind that must not be written as confirmation

Amendment 1 A4 already found, blind, that only FIX CONFIRMED still bought
anything — *"the right not to chase two suspects nobody has scheduled"* (lines
704, 717-719) — and that MIRROR RESIDUAL and UNRESOLVED *"buy nothing but a
recorded number"* (lines 715-717). It deliberately declined to rule on whether
the study was still worth the exposure, because answering that *"after seeing
a result is the contamination this document exists to prevent"* (lines
724-726).

The result is now seen, and it is the best case: `K = 0` across 263 and then
294 post-`T0` fast cycles, on an arm 30-40% busier than the one the pre-fix
rate was measured on, with `P(K = 0 | rate unchanged)` between 10⁻⁴ and 10⁻⁵
under the planning `lambda_0`. There is no reading of the same instrument that
would be *more* favourable to ADR 0091 than this one — subject to the result
file's own caveats that the journal has written nothing of any kind since
2026-08-31T11:01Z and that the instrument drops the UNCOUNTABLE class. And
the registration forbids crediting it, for reasons the result file gives in
its §3.2 and this ADR endorses: the tolerance was registered two-sided before
the data; §9.8 says a verdict does not generalise across tempo (lines
569-571); §6.1 says a precondition *"cannot manufacture a positive one"*
(lines 349-353); and ground (b)'s third candidate says the covariate may not
be controllable at all.

Put those together. Further readings can only produce:

- (i) the same verdict with a bigger `E`;
- (ii) NOT COMPUTED once the baseline rolls off the box;
- (iii) a FIX CONFIRMED that a later quiet window happens to license — a
  verdict *selected by the calendar*, the optional-stopping shape §6.2 built
  the e-value to avoid on the other arm and refused outright on this one; or
- (iv) **SIGNATURE PERSISTS**, the one verdict that convicts ADR 0091. It is
  always-valid, declarable at any `E`, tested before C1 and before the `E*`
  gate (`inspect_live_db.py:2869-2871`), exempt from C5, and two in-band
  FAST-matched bursts declare it (§6.4). **Terminating P5 forecloses it as a
  P5 verdict.** That is a real cost and it is named here rather than hidden
  in "nothing is consumed": the instrument stays deployed as a diagnostic, so
  a future in-band burst is still *visible* to anyone who runs it, but it
  will not be a P5 look and may not be written up as one.

None of (i)-(iii) is consumed by anything. ADR 0091 is a real defect fix with
or without this study, `badd88e` already made the victim loop survive the
next lock whatever holds it (Amendment 1 A1), and the §0.4 successor was
killed on 2026-09-01. The recorded number is recorded. (iv) is the price of
stopping, and it is paid knowingly.

## Decision

**P5 terminates now, at UNRESOLVED — TEMPO-CONFOUNDED, final.** The registered
look is the 16:26Z reading of 2026-09-02 (UNRESOLVED — C4/C5); the 19:01Z
re-read is evidence for ground (b) and nothing else; and
`docs/measurements/2026-09-02-forward-lock-instrument-result.md` is the file
§10 required. No reading taken after 19:01Z is a P5 look, and none may be
quoted as one.

Four things this ruling is explicit about, because each is the obvious next
move and each is refused:

1. **C5's tolerance is NOT amended.** The ±25% two-sided band stands in the
   registration (§7, lines 468-470) and in `C5_TEMPO_TOLERANCE`
   (`inspect_live_db.py:2397`). The observation that a *busier* victim is not
   the confound §7 feared — and ground (b)'s sharper point that the fix may
   itself move the covariate — are **design notes for the next comparability
   check anyone registers**: state which direction of difference is the
   confound, and whether the treatment can move the covariate. They go into
   that registration, written blind, not into this one with +40% on the
   screen. Amending now would make the amendment the finding.

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
   continuing would have been the way to reach it.

4. **§10's UNRESOLVED row is read down, after the result, and that is a
   sighted change to the action table — named, not hidden.** Amendment 1 A6
   warns that the action table *"keeps rotting while the registration waits"*
   and *"becomes uncorrectable the moment a result is visible"* (lines
   750-757). **A6 is right about this change.** Amendment 1's own warrant was
   blindness — it was written before any post-`T0` burst was read (lines
   657-662) — and this ruling has no such warrant: it is made with both
   readings on the screen. The defence is therefore **not** Amendment 1's, and
   A5's "only in the direction of claiming less" (line 748) is a description
   of what that amendment did not touch, not a licence for this one. What
   makes this change survivable is narrower and is argued here rather than
   borrowed: it kills a look; it credits nothing; it changes no threshold, no
   population, no statistic and no decision rule; and it removes verdicts in
   **both** directions — the FIX CONFIRMED a calendar might have licensed
   *and* the SIGNATURE PERSISTS two in-band bursts would have declared. A
   sighted change that forecloses the favourable verdict and the unfavourable
   one alike, while leaving the instrument running so the unfavourable
   evidence stays visible, is not selection; it is stopping.

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
- SIGNATURE PERSISTS **as a P5 verdict** — ground (c)(iv). A future in-band
  burst is a new finding for a new registration, not a late P5 result.

**Kept:**

- **The instrument itself**, `scripts/inspect_live_db.py forward-lock`, as a
  diagnostic. It is the only thing in the repo that splits bursts by matched
  cycle into MIRROR and FAST, ages a cycle against evidenced process liveness,
  and reads `wal_kb` and tempo out of `loop_rss.jsonl` with the
  `produced_by`-absent-versus-null distinction right. The next lock
  investigation, if there is one, starts from it — and from the preserved
  `data/live-snapshots/loop_rss-2026-09-02T19Z.jsonl`, which is the only copy
  of the pre-fix baseline that will exist once the box trims. Nothing in the
  instrument is deleted or disabled by this ADR.
- **ADR 0091, standing as a real defect fix that is neither credited nor
  refuted on this evidence.** Its own "What this does NOT establish" section
  said *"a fit is not a proof"* and named the retention prune and the
  `TRUNCATE` checkpoint as unexamined suspects. That is still exactly its
  status. It does **not** gain the "confirmed on live evidence" note §10's
  FIX CONFIRMED row would have given it, and any future sentence claiming the
  symptom is closed must cite something other than P5.
- **The registration, unamended.** Every threshold, the population, the unit,
  the band, the stopping rule and C5's tolerance are as registered. This ADR
  reads §10's UNRESOLVED row in §6.2's favour; it changes nothing the
  registration fixed.
- **Two design inputs** for whoever next registers a comparability
  precondition: say which direction of difference is the confound and whether
  the other direction is a refusal or a note; and ask, before registering,
  whether the treatment can move the covariate — if it can, the precondition
  refuses the fix for working.

**What this does not establish:**

- That the `database is locked` symptom is gone. `K = 0` over ~25 hours of one
  tempo, through one failure hook that has written nothing of any kind since
  2026-08-31T11:01Z, is a floor on nothing and a proof of nothing.
- That a quiet week in the calendar would not have passed C5. It might have.
  The ruling is that waiting for it would have been selecting the look by the
  answer, not that the answer would have been wrong.
- That the tolerance *should* have been one-sided, or that the fix is what
  moved the tempo. Both are the design notes, and they are notes.
