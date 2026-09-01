# PRE-REGISTRATION — did ADR 0091 close the `database is locked` symptom?

**Written 2026-09-01, before any post-deploy burst was read.** The deploy that
makes this measurable (`265bc9a`, carrying `ea4c1a3`) landed on live earlier
the same day. At the time of writing, no post-deploy `database is locked`
failure has been looked at, and this document fixes the population, the unit,
the band, the stopping rule and the decision rule so that none of them can be
chosen afterwards.

It exists because **a claim that ADR 0091 worked was already written and
refused once, this session.** The "quiet run" it rested on began 4.47 hours
*before* the fix deployed; the deploy sat at position 14 of 50 walk lines and
nothing in the data located the change at it. That refusal is the reason this
is registered in advance rather than assessed after.

It is the forward instrument §7 of
[`2026-09-01-lock-holder-attribution-result.md`](2026-09-01-lock-holder-attribution-result.md)
required before it is used, and it inherits that document's three corrections:
the band must be written down, the stopping rule must be written down, and a
burst after a **mirror** cycle does not refute ADR 0091.

---

## 0. THE POWER CHECK, WHICH COMES BEFORE EVERYTHING ELSE

**Can this measurement answer this question at the exposure available?**
Partly, and the part it cannot answer is named here rather than discovered
later.

### 0.1 The pre-fix rate, which sets everything

From the attribution measurement's own population: **13 bursts** over the
pre-fix journal window `2026-08-30T07:08:53Z .. 2026-08-31T15:29:19Z` (the ADR
0091 deploy, Fly release 182) — **32.34 hours**.

    fast poller cycles in that window   ~385   (32.34 h x 12/h, less mirrors)
    lambda_0                            13 / 385 = 0.0338 per fast cycle
    equivalently                        ~0.40 bursts/hour

The task brief's ~0.39/h is the same figure over a marginally wider
denominator. **The instrument recomputes `lambda_0` from `poll_log` at analysis
time; 0.0338 is the planning value, and the registered exposure below is
checked against it by precondition C6.**

### 0.2 What exposure is needed to credit the fix

The rate arm credits the fix by observing **zero** bursts over enough exposure
that zero is itself improbable under an unchanged rate.

    P(K = 0 | rate unchanged) = (1 - 0.0338)^E
    one-sided alpha = 0.005 requires E >= ln(0.005)/ln(1-0.0338) = 154.2

**Registered E\* = 160 fast poller cycles** — 154 rounded up with margin. At
300.415 s per cycle that is **13.35 hours of cumulative poller exposure**,
which is not the same thing as 13.35 hours of wall clock (§8).

### 0.3 The detectable effect, stated before committing

At `E* = 160`, the probability of reaching a verdict of FIX CONFIRMED is:

| true post-fix rate | reduction | P(declare) |
|---|---|---|
| 0                  | 100%      | 1.00  |
| 0.05 x lambda_0    | 95%       | 0.76  |
| 0.10 x lambda_0    | 90%       | 0.58  |
| 0.25 x lambda_0    | 75%       | 0.26  |
| 0.50 x lambda_0    | 50%       | 0.066 |

**80% power arrives only against a reduction of 96% or more.** Against a
halving of the rate this design has 6.6% power — it would return UNRESOLVED
almost every time, and an UNRESOLVED here must never be read as "the fix did
nothing".

**This is a match to the hypothesis, not a defect, and it is why the verdict
below is READY rather than UNDERPOWERED.** ADR 0091's mechanism predicts a
*near-total* elimination of fast-branch collisions: the write lock stops being
held across three Kalshi round trips and is held for one write burst instead,
so the fast branch's window shrinks by roughly its whole duration. A design
powered against a 96% reduction is powered against what the ADR actually
claims. A partial improvement is genuinely ambiguous evidence about that claim
and *should* return UNRESOLVED.

### 0.4 What a partial reduction would cost, computed now

Resolving "the rate halved" rather than "the rate collapsed" needs roughly 34
expected bursts under the null:

    E >= 34.0 / 0.0338 = ~1,010 fast cycles
      = ~84 hours cumulative poller exposure
      = about 3.5 days of uptime

**That is a separate registration and is not authorised here.** It is written
down so a future session does not discover the number after spending the time,
in the habit ADR 0016 established.

---

## 1. The claim under test, as something that can come back false

**H1 (rate arm), one-sided:** the rate of `database is locked` bursts per fast
poller cycle is **lower** after the deploy of `265bc9a` than the pre-fix rate
`lambda_0`.

**H2 (signature arm), one-sided:** among post-deploy bursts matched to a
**fast** poller cycle, the offset from that cycle's start falls in the band `B`
of §4 **more often** than a uniform-phase null predicts.

Both directions are declared here. Neither may be reported one-sided after
having been computed two-sided, or the reverse.

**The two arms do different jobs and only one of them can clear the fix.** H2
can convict — it can show the fast branch is still the trigger. H2 cannot
clear, for the same reason the attribution design could not: an absence of
in-band bursts is what its null predicts anyway. **H1 is the only arm that can
credit ADR 0091**, and it does so only through accumulated exposure with no
bursts in it. Any write-up that credits the fix on H2's silence is wrong.

### 1.1 Weakened quantifiers, on purpose

Three sentences that would otherwise be universals, corrected at registration
time where it costs nothing rather than at audit time where it costs the
finding:

- Not "every fast cycle writes a `poll_log` row" — a cycle whose own
  `log_poll_attempt` write is killed by the lock leaves no stamp. Exposure is a
  **floor**, and §9.5 states which way that biases each arm.
- Not "the mirror marker proves the process carries the fix" — it proves the
  process carries `ea4c1a3`. A rollback to older code would produce cycles with
  neither the marker nor the fix, which §2.3 handles explicitly.
- Not "the poller is the holder" — the attribution result implicated it, and §9
  keeps the alternatives that result did not separate.

---

## 2. The population, and the boundary

### 2.1 Where it starts, and why the boundary lives in the database

    T0 = MIN(polled_ms) FROM poll_log WHERE endpoint = 'mirror'

**`endpoint = 'mirror'` exists only in the code that carries both changes.** It
was added in `ea4c1a3` (merged as `56f4572`, deployed as `265bc9a`, confirmed
an ancestor by `git merge-base --is-ancestor`), and no earlier build writes
that value. So the first such row is a **durable, in-database deploy marker**,
and `T0` does not depend on reading a Fly release timestamp — which is the
class of external evidence the refused claim leaned on.

`poll_portfolio_forever` takes the mirror branch on its first cycle
unconditionally (`last_mirror is None`), so every process life that reaches the
poller under this build opens with a `mirror` row. The marker is written
**before** the mirror runs and committed immediately, so a cycle that dies
inside `poll_portfolio` still carries it.

### 2.2 The interval that is deliberately thrown away

ADR 0091 deployed `2026-08-31T15:29:19Z`. `T0` is roughly nineteen hours later.
**That interval is excluded from both arms** even though the fix was live in
it, for two reasons that are independent of any outcome inside it:

- Without the marker, a burst in that interval cannot be assigned to the fast
  branch rather than the mirror, which is precisely the split §7 of the
  attribution result requires.
- The mirror branch still carried an **uncured** lock defect until `ea4c1a3`
  (`ensure_estimate_markets_known` held the write lock across N-1 Kalshi round
  trips), so a mirror-matched burst there has a live alternative explanation
  that no longer exists after `T0`.

It may be reported as descriptive context. **It may not enter either arm and it
may not produce a verdict.** One boundary, used by both arms — mixing two
boundaries is exactly the freedom this document removes.

### 2.3 Which bursts count

Every line in `/data/loop_failures.jsonl` (the **journal**, not the
`loop_failures` table) with:

    kind == "failure"                        (not diagnosis, not rollback)
    "database is locked" in error
    consecutive_failures == 1                (the unit, §3)
    matched cycle stamp >= T0                (§2.4)

**The journal and not the table, and the reason is the outcome itself.** The
table held 8 of 22 journalled failures, and the 14 it lost were lost *because*
a lock killed the row's own write. A table-derived population would be selected
on the dependent variable.

Exclusions, each independent of the offset:

| rule | why it does not reference the outcome |
|---|---|
| not a failure line | a diagnosis/rollback line is not a failure event |
| error lacks "database is locked" | a different failure class |
| `consecutive_failures != 1` | a repeat inside a burst, §3 |
| matched cycle stamp `< T0` | that cycle ran pre-marker code |
| `consecutive_failures` missing or non-integer | the field cannot be read |

The last row is an **UNCOUNTABLE** class. Its count is reported in the write-up
whatever the verdict; it is not silently dropped.

**A process life whose opening cycle carries no `mirror` row is running code
without `ea4c1a3`** (a rollback, or a redeploy of an older tree). Every cycle in
that life is excluded from both arms, and the excluded cycle count is reported.
That exclusion reads the code version, never the offset.

### 2.4 The burst that straddles the boundary

**A burst is assigned to the population by its MATCHED CYCLE's stamp, not by
its own `failed_ms`.** A failure stamped at or after `T0` whose newest preceding
`poll_log` cycle start is *before* `T0` belongs to a pre-marker cycle and is
**excluded**, and named individually in the write-up.

At most one burst can be in this class, because `T0` is itself a cycle start
and cycles are ~300 s apart. The rule references the code version of the cycle
the burst is being attributed to. It does not reference the offset.

---

## 3. The unit — the burst, not the pass

**A burst is one journal failure line with `consecutive_failures == 1`.** Two
people counting from the same file get the same integer.

`Tempo.pass_kind` re-arms a full pass the moment one fails, so the failures
inside a burst are one draw and not four. A prior look counted passes and was
wrong for this reason. The instrument lists every failure so the drop is
visible rather than assumed.

**Independence and clustering.** Two bursts are treated as independent draws
only if they are matched to different poller cycles. The clustering variable is
the **poller cycle stamp** (`poll_log.polled_ms`). Two bursts matched to the
*same* cycle stamp count as **one** burst in both arms, taking the earlier; the
collapse count is reported.

**The unit is deliberately identical to the attribution registration's, and is
not refined here.** `MAX_CONSECUTIVE_FAILURES = 5` kills the process, so a
sixth failure after the restart re-enters as `consecutive_failures == 1` and is
counted as a new burst even though it may be a continuation. That is a known
imperfection. It is kept because `lambda_0 = 13 bursts` was computed under this
exact definition, and changing the unit after seeing that number is the freedom
this document exists to remove. **The merge-adjacent case is reported
descriptively** — bursts within 300 s of a process restart, in both windows —
and has no threshold attached to it.

---

## 4. The cut — the band and the mirror/fast split, fixed in advance

### 4.1 The split, which gates the signature arm

For each burst, the matched cycle is **MIRROR** if any `poll_log` row shares
its `polled_ms` with `endpoint = 'mirror'`, and **FAST** otherwise.

- **FAST-matched bursts are the signature arm's population.** ADR 0091's
  frequency argument is about the fast branch, and only fast cycles test it.
- **MIRROR-matched bursts do not enter the signature arm.** They get their own
  verdict branch (§6.3, MIRROR RESIDUAL). After `T0` the mirror's own lock
  defect is fixed, so a mirror-matched burst is a **new** finding rather than
  the old one, and it does not bear on ADR 0091 either way.
- **A burst with no matched cycle, or one where precondition C1 fails, is
  UNCLASSIFIED.** It is excluded from the signature arm and **counted in full
  in the rate arm** — dropping it from the rate arm would be an exclusion that
  references how attributable the burst turned out to be.

### 4.2 The band

The pre-fix offsets were all in `[5.195, 5.919]` s, a range of 0.72 s, against
`BUSY_TIMEOUT_MS = 5_000`. The mechanism that produces that shape is a busy
wait of exactly 5.000 s begun at the poller's first `INSERT`, which is one
Kalshi round trip after the cycle start.

**Registered primary band:**

    B = [5.000, 8.000] seconds

- **Floor 5.000 s**, the busy timeout exactly. SQLite's busy handler returns
  `SQLITE_BUSY` only once the accumulated delay exceeds the timeout, so a raise
  cannot occur sooner than 5.000 s after the wait began.
- **Ceiling 8.000 s** = 5.000 + one Kalshi REST round trip bounded generously
  at 3.000 s, the same 3 s the attribution registration used. Widening the band
  makes "the signature persists" easier to declare — conservative **against**
  crediting the fix, which is the direction CLAUDE.md requires for good news.

**Reported beside it, never instead of it:** the count inside the pre-fix
empirical band `[5.195, 5.919]`. That is descriptive. The primary decides.

### 4.3 What offset exonerates, and the honest limit on it

- **Offset in `B` on a FAST cycle** — evidence the fast branch is still the
  trigger. Scored as a hit.
- **Offset > 8.000 s** — inconsistent with a 5 s busy wait begun at this
  cycle's first `INSERT`. Not a hit.
- **Offset < 5.000 s** — scored **SUB-TIMEOUT**, not a hit, and **not
  exonerating either.** It is inconsistent with a busy wait that *began at or
  after* this cycle start; it remains fully consistent with a wait that began
  during the *previous* cycle and expired early in this one. It is also the
  expected shape of the second mechanism the attribution result identified:
  `SQLITE_BUSY_SNAPSHOT` on a poisoned connection fails **instantly**, with no
  5 s to wait and no dependence on poller phase.

The exonerating pattern for the signature arm is therefore **dispersion**:
bursts occur, and their offsets do not concentrate in `B`. That is what the
e-value in §6.2 measures, and it is why a single scattered burst is not read as
either verdict.

---

## 5. The statistic, named as an estimator

**Rate arm.** A **proportion** — bursts per fast poller cycle, `K / E`, where
`E` is the count of distinct post-`T0` fast cycle stamps. Null:
`K ~ Binomial(E, lambda_0)`. `sqrt(p(1-p)/n)` is not used; the exact binomial
tail is, because `K` is expected near 0 and the normal approximation has no
standing there — CLAUDE.md requires at least 5 expected outcomes per side and
this design does not have them by construction.

**Signature arm.** A **proportion of FAST-matched bursts falling in a fixed
band**, against a uniform-phase null with `P(hit) = |B| / C`, where `C` is the
median observed cycle gap, recomputed from the data and not assumed to be 300.
Planning value: `3.000 / 300.415 = 0.00999`.

**The uniform null is argued from a constant, not assumed.**
`scheduler.JITTER = 0.15` multiplies every inter-pass sleep by
`1 + U(-0.15, +0.15)` — plus or minus 2.25 s of fresh uniform phase per quote
pass, roughly 20 per poller cycle. A phase relation narrower than a second does
not survive that.

**Neither arm pools the two.** They test different nulls on different
populations, and are reported separately with their own counts.

---

## 6. The decision rule, with the multiplicity already counted

### 6.1 The tests, counted

**Two tests.** One rate arm, one signature arm. Family-wise alpha **0.01** —
the same family alpha the attribution registration used, for the same reason:
this record has run many tests, and 0.05 on the n-th is not a 5% error rate.
Bonferroni: **alpha = 0.005 per arm.** Under pure noise at two tests and 0.005
each, the expected number of false findings is 0.01.

**The preconditions in §7 are refusals, not tests.** A precondition can only
convert a verdict into UNRESOLVED; it cannot manufacture a positive one. It
therefore adds nothing to the multiplicity count, and it makes the
fix-crediting direction strictly harder.

### 6.2 The record will be looked at more than once, so one arm is always-valid

The instrument is a CLI and the record grows. A fixed threshold re-evaluated on
every run is not one look; §7 of the attribution result already computed that a
single in-band burst at `p = 0.0024`, checked after each of the next 50 bursts,
gives a family-wise false-alarm rate near 11%.

**Signature arm — an always-valid e-value, so early stopping is licensed.** For
each FAST-matched burst, in time order, with `q = 0.5` as the registered
alternative (half of post-fix bursts still carry the signature — deliberately
not 1.0):

    p0   = |B| / C                     = 0.00999   (recomputed from the data)
    e_i  = q / p0             if hit   = 50.07
    e_i  = (1 - q) / (1 - p0) if miss  = 0.5050

    E_n  = product of e_i over FAST-matched bursts

Declare when `E_n >= 200`. By Ville's inequality the type-I error is at most
`1/200 = 0.005` **at any stopping time and under any number of looks.**

Consequences of that boundary, spelled out so nobody re-derives them:

    1 hit                E = 50.1     does not declare
    1 hit + 1 miss       E = 25.3     does not declare
    2 hits               E = 2,507    DECLARES

**Two in-band FAST-matched bursts declare; one does not.** That is the
arithmetic answer to §7's objection that one burst at ~5.3 s was too strong a
refutation.

**Rate arm — a single look at `E*`, no early stopping.** Its statistic is not a
supermartingale under optional stopping and may not be peeked at. The
instrument must **refuse to print a rate verdict** below `E*`, printing
`EXPOSURE NOT REACHED: <E> of 160 fast cycles` instead — the same structural
refusal `lock-attribution` section 1 already uses.

### 6.3 THE DECISION RULE, VERBATIM

> **Let `T0` be the earliest `poll_log.polled_ms` with `endpoint = 'mirror'`.
> Let `E` be the number of distinct `poll_log.polled_ms` values at or after
> `T0` carrying no `endpoint = 'mirror'` row (fast cycles). Let `K` be the
> number of bursts — journal lines with `kind = "failure"`, `"database is
> locked"` in `error`, and `consecutive_failures == 1` — whose matched cycle
> stamp is at or after `T0`, collapsing to one any bursts sharing a matched
> cycle. Let `H` be the number of those bursts whose matched cycle carries no
> `mirror` row and whose offset lies in `B = [5.000, 8.000]` seconds. Let
> `E_n` be the running product, over FAST-matched bursts in time order, of
> `0.5 / p0` for an in-band burst and `0.5 / (1 - p0)` for an out-of-band
> burst, where `p0 = 3.000 / C` and `C` is the median observed cycle gap.**
>
> **SIGNATURE PERSISTS — ADR 0091 DID NOT CLOSE THE SYMPTOM** if `E_n >= 200`.
> Declarable at any time, including before `E*`.
>
> **MIRROR RESIDUAL** if `K >= 2`, every burst in `K` is MIRROR-matched, and
> `H = 0`. A new finding about the mirror branch after `ea4c1a3`; it does not
> bear on ADR 0091 in either direction.
>
> **FIX CONFIRMED ON LIVE EVIDENCE** if `E >= 160`, `K = 0`, `E_n < 200`, and
> every precondition C1 to C6 of §7 holds. One-sided exact binomial
> `p = (1 - lambda_0)^E <= 0.005`.
>
> **UNRESOLVED** in every other case, including: `E >= 160` with `K > 0` and
> `E_n < 200`; `E < 160` at the §8 backstop date; and any failed precondition,
> in which case the verdict is reported as **UNRESOLVED — <name of the failed
> precondition>** and is never shortened to UNRESOLVED alone.
>
> **No verdict of any kind may be quoted before `E >= 160` except SIGNATURE
> PERSISTS, which is always-valid and is the sole exception.**

### 6.4 What falsifies "ADR 0091 fixed it"

**Two post-deploy bursts, each matched to a cycle carrying no `mirror` row,
each with an offset in `[5.000, 8.000]` seconds.** That is `E_n = 2,507`
against the 200 boundary, and it says the fast branch is still the trigger of a
hold longer than the 5 s busy timeout, on cycles running the fixed code.

**What it still does not settle**, and §9.2 keeps this: it does not separate
the fast branch's *own transaction* from a checkpoint fired *by* its first
commit. Post-fix both sit at the same instant, and only the first is what ADR
0091 changed.

---

## 7. Preconditions — refusals that block a verdict

**C1 — `poll_log` spans the burst window.** `MIN(polled_ms) <= T0` and
`MAX(polled_ms)` at or after the newest scored burst. An offset measured
against a stamp hours away measures a hole in `poll_log`, not a lock.

**C2 — `T0` exists.** No `mirror` row means the build is not live, and the
correct output is "the instrument is not there", never "no bursts".

**C3 — restart coverage.** A restart is this failure class's own documented
cure, and post-fix process lives have been short. Let `A_pre` be the median
process age at which the 13 pre-fix bursts occurred, computed from
`loop_rss.jsonl`'s restart markers (`produced_by = None` on a process's first
sample; the poller runs as an `asyncio` task inside the chain runner's process,
so that marker is the poller's restart marker too). **The post-`T0` exposure
must contain at least 30 fast cycles at process age `>= A_pre`.** 30 is
`1 / lambda_0` — one pre-fix burst-equivalent of exposure in the aged regime.
If the pre-fix `loop_rss` lines have rolled off the capped file, `A_pre` falls
back to **2.0 hours**, fixed here, chosen as the largest round value below the
3.13 h longest observed post-fix process life so the precondition is reachable
rather than automatically failing.

**C4 — WAL comparability.** Lock duration plausibly grows with WAL size, and
restarts shrink it. **The median `wal_kb` over the post-`T0` exposure must be
at least the 25th percentile of `wal_kb` over the pre-fix window**, both from
`loop_rss.jsonl`. Otherwise the arms are not comparable and the verdict is
UNRESOLVED — WAL-CONFOUNDED.

**C5 — victim tempo comparability.** Fewer passes means fewer collisions
regardless of the fix. **Passes per hour after `T0`, counted as
`loop_rss.jsonl` lines per hour, must be within plus or minus 25% of the
pre-fix figure.** Otherwise UNRESOLVED — TEMPO-CONFOUNDED.

**C6 — `lambda_0` supports the registered `E*`.** `E* = 160` delivers
`p <= 0.005` only if `lambda_0 >= 0.03257`. If the instrument's recomputed
`lambda_0` is below that, `E*` is raised to `ln(0.005)/ln(1 - lambda_0)`,
rounded up, and the verdict stays UNRESOLVED until the raised figure is met.
**`E*` is never lowered.**

---

## 8. The stopping rule

**Primary, in a unit that survives restarts: `E* = 160` cumulative post-`T0`
fast poller cycles.** Not wall clock. Exposure accumulates across process
lives, so 13 restarts inside the window do not reset the count — which is
exactly the failure of a rule phrased as "wait until time T", given that the
longest uninterrupted process life since the fix was 3.13 h against the 13.35 h
of cumulative exposure `E*` requires.

`E` is computed as the count of distinct post-`T0` `poll_log.polled_ms` values
carrying no `mirror` row.

**Event stop:** the signature arm may declare at any moment `E_n >= 200`, and
collection ends there. That is legitimate only because the boundary is
always-valid; the rate arm has no early stop.

**Wall-clock backstop: 2026-09-15T00:00Z.** If `E*` is not reached by then, the
look is taken at whatever `E` stands at, the verdict is **UNRESOLVED —
INSUFFICIENT EXPOSURE**, and `E` is recorded so the next look knows where it
started. The backstop exists so collection cannot run until the answer is
convenient.

**Amendment trigger.** If `C` (the median cycle gap) moves more than 10% from
300.415 s, or `BALANCE_INTERVAL_S` changes, the band and `p0` are recomputed
and the amendment is written into this file, dated, **before** the affected look
is taken.

---

## 9. What this cannot establish

Drafted before the run, and each line checked against the schema rather than
written as modesty. **The prior registration's §4 and §7 asserted that the
poller's cycle end is recorded nowhere and used it to rule out any exonerating
verdict; that was false, and it removed the only check that could have refuted
the mechanism.** Two entries below were candidates for the same mistake and are
corrected here instead of repeated.

1. **Bursts outside the chain runner's failure hook.** The journal is written
   only by that hook. Lock failures inside the poller itself, `bid_watch`,
   `hedge_watch` or the API process never appear in it. Both arms use the same
   instrument on both sides of `T0`, so the **comparison** is valid; the
   absolute rate is a floor and must be quoted as one.

2. **Whether the holder was the fast branch's own transaction or an automatic
   PASSIVE checkpoint fired by its commit.** SQLite logs nothing for the
   automatic checkpoint, and no field in `poll_log` or `loop_rss.jsonl` records
   it. **This is narrower than the attribution result's §6 caveat, and
   deliberately so:** the runner's *explicit* `TRUNCATE` checkpoint — the one
   ADR 0091 names as a suspect because it takes an exclusive lock — **is**
   observable, in `loop_rss.jsonl` as `wal_ckpt_mode`, `wal_ckpt_busy`,
   `wal_ckpt_log_frames` and `wal_ckpt_error`, and those fields **must be
   reported beside every scored burst.** Writing "we cannot tell whether a
   checkpoint did it" flatly would have been the dangerous kind of limitation:
   one that argues for its own conclusion's robustness while the schema already
   carries half the answer.

3. **Cycle duration is NOT unobservable, and this design uses it.** The poller
   sleeps *after* its cycle, so the gap to the next `poll_log` stamp is
   `cycle_wall + 300 + overshoot` and bounds the cycle above. The matched cycle
   span is reported beside every burst, as the attribution result's §3 did.
   What it cannot do is give per-endpoint timings: `poll_log` has columns
   `id, polled_ms, endpoint, ok, row_count, error` and **no duration column**,
   so "offset minus 5.000 s is the balance round trip" is an inference and the
   band's 8.000 s ceiling is a bound taken from the ADR, not a measurement.

4. **Retention-prune timing.** `prune_quotes` runs inside a full pass and is not
   separately stamped. A prune-caused burst can be **bounded** to a pass
   interval via `loop_rss.jsonl` line stamps, but not attributed. ADR 0091 names
   the prune as an unexamined suspect and this design does not close it.

5. **The exposure count `E` is a floor, and the direction of that bias is not
   the flattering one for both arms.** A cycle whose own `poll_log` write was
   killed by a lock leaves no stamp. For the **rate arm**, an undercounted `E`
   delays the declaration and overstates `K/E` — conservative against crediting
   the fix. For the **signature arm**, the same missing stamp causes a nearby
   burst to be scored against an *earlier* cycle, inflating its offset out of
   `B` and **losing a hit** — which biases the signature arm toward exonerating
   ADR 0091. That is the caveat cutting against this document's own
   conservatism, and it is stated because a caveat list written afterwards is
   selected to be survivable.

6. **That zero FAST-matched bursts means the fast branch never takes a long
   lock.** It means it did not hold one long enough to expire a 5,000 ms busy
   timeout during the scored exposure, in the chain runner's own writes.

7. **Anything about the `2026-08-31T15:29:19Z .. T0` interval**, excluded by
   §2.2, or anything before 2026-08-30 when the durable journal landed.

8. **That any verdict here generalises to a different `BALANCE_INTERVAL_S`, a
   different pass tempo, or a larger database.** All three are conditions of the
   window, not constants of the system.

---

## 10. What is built if it clears, what is killed if it does not

**This measurement is decision-relevant in all four branches, and the actions
differ.** If they did not, the honest thing would be to say so and not run it.

| verdict | what happens |
|---|---|
| FIX CONFIRMED | ADR 0091 gains a "confirmed on live evidence" note carrying `E`, `K` and the preconditions. `tasks/NEXT.md` open item 1 closes. The remaining named suspects — the retention prune and the `TRUNCATE` checkpoint — are **not** pursued. |
| SIGNATURE PERSISTS | ADR 0091 stands as a real defect fix and is recorded as **not the cause**. A successor registration opens on the next suspect. Priority moves to victim tolerance: `run_scoring_pass`'s `try/except` wraps the fetch and not the store, so one lock error still abandons every remaining market in the pass — that becomes the mitigation, since the holder is not closed. |
| MIRROR RESIDUAL | A new investigation into the mirror branch after `ea4c1a3`. ADR 0091 is neither credited nor refuted. |
| UNRESOLVED | Nothing is credited. Open item 1 stays open, with `E`, `K` and the failed precondition recorded so the next look starts from a number rather than from scratch. |

**The negative branch has a destination now, before the run.** Whatever the
verdict, **one** file is written:

    docs/measurements/<YYYY-MM-DD>-forward-lock-instrument-result.md

with the verdict in its H1 title. A single file for every branch is the point: a
registration whose negative branch has no address produces a negative result
that quietly never gets written.

---

## 11. Instruments

`scripts/inspect_live_db.py` is the only thing permitted to run against the live
box. The reads this registration needs:

- `lock-attribution` — the offsets and the matched-cycle spans.
- `failure-journal` — the journal population and the table's shortfall.
- `loop-rss` — restart markers, `wal_kb`, `wal_ckpt_*`, pass tempo.

**Three capabilities the instrument does not yet have**, named here so building
them is a build task against a fixed specification rather than a choice made
while looking at results:

1. A `T0` boundary. `lock-attribution` reads the whole journal and would pool
   pre- and post-deploy bursts.
2. The MIRROR/FAST split. Its cycle query is `SELECT DISTINCT polled_ms` with no
   `endpoint` join, so it cannot classify a matched cycle today.
3. The `E`, `E*` and `E_n` arithmetic of §6.3, and the refusal to print a rate
   verdict below `E*`.

Its docstring also still carries the corrected claim that cycle duration is
recorded nowhere, contradicting the code immediately below it; that sentence
should go when the split lands.

**Building those does not amend this registration.** If any of them cannot be
built as specified, the shortfall is written into the result document and the
affected arm reports UNRESOLVED.

---

## Provenance of this document — added 2026-09-01, immediately after commit

**It is pre-registered, and here is the check rather than the assurance.** This
file was committed in `feca481`, blob `f5328a0e0205f308229a489225f6b0f075a4a581`,
and pushed to `origin/main` **before any post-`T0` burst was read**. No
subcommand implementing §11 existed at that moment, so the arithmetic this
document fixes could not have been influenced by a result: the instrument had
to be built afterwards, which is the point.

**It landed in a commit about something else, and that is a defect in the
bookkeeping rather than in the registration.** `feca481` is the volume lane's
merge; a `git add -A` swept this file in alongside it. The agent that wrote it
had deliberately left it uncommitted to avoid exactly that, and was right to.
The registration property survives — a git object dated before the data — but
a reader looking for the registering commit will not find it by its message.
Hence this note, and the blob hash above, which is what actually pins the
content.

**The pattern, for `tasks/lessons.md`:** an agent that WRITES to the shared
tree is as hazardous to a commit as one that mutates code, and the isolation
rule was applied to four lanes here and not to this one. `git status` cannot
distinguish a subagent's half-written document from your own work in progress.
Isolate anything that writes, or stage by explicit path and never `-A` while a
writer is live.
