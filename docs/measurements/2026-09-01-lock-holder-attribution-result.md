# RESULT — the poller held the lock, and its own cycles ran long to prove it

**Taken 2026-09-01 on live `228f716`, corrected and re-taken on `d325ed1`**,
to the rule fixed in
[`2026-09-01-lock-holder-attribution-registration.md`](2026-09-01-lock-holder-attribution-registration.md),
written before the join existed. Instrument: `inspect_live_db lock-attribution`.

**Audited by `measurement-skeptic` before entering the record** (CLAUDE.md
requires it when a result is good news). Verdict: ACCEPT WITH NAMED
CORRECTIONS, plus one required additional read. **All corrections are applied
below and the additional read was taken** — it is §3, and it is the part of
this document worth reading if you read nothing else.

## 1. The registered test

    n (bursts scored)             13
    k (offset <= W = 14 s)        13
    p0 = W / C                    0.0466      C = 300.415 s, observed median
    expected under H0             0.606
    two-sided exact binomial p    4.890e-18
    VERDICT                       POLLER IMPLICATED

`poll_log` spans the journal; 3,983 distinct cycles from 10,437 rows.

**The p-value is the instrument's own.** The first draft of this document said
`~6e-18`, computed off-instrument and 22% wrong, while the harness printed a
literal `0.000000` for a quantity near 5e-18. Both are fixed: the formatter is
now `:.3e` and a test pins it against ever formatting to zero again.

## 2. The offsets are a spike

All 13 bursts, in seconds after a poller cycle start:

    5.36  5.345  5.633  5.919  5.285  5.195  5.361
    5.283  5.285  5.340  5.331  5.520  5.279

Range **0.72 s**, all in [5.195, 5.919]. `BUSY_TIMEOUT_MS = 5_000`.

**Aliasing is excluded from the code, not assumed away.** The registration
argued the uniform null as an assumption; it can be argued from a constant.
`scheduler.JITTER = 0.15` multiplies every inter-pass sleep by
`1 + U(-0.15, +0.15)` — ±135 s of fresh uniform phase noise per full pass, ±2.25 s
per quote pass with ~20 per poller cycle. A 0.72 s phase relation cannot
survive 28 hours of that.

**The two stamps have no shared derivation.** `failed_ms` is `int(time.time()*1000)`
read in the synchronous `except` block with no `await` between the raise and
the stamp; `polled_ms` is `int(clock()*1000)` at the top of the poller's loop
body. Different call stacks, no rounding, no common grid.

## 3. THE FALSIFYING READ — and it could have gone the other way

The registration's §4 and §7 said the poller's cycle *end* is recorded nowhere,
and used that to rule out any exonerating verdict. **That was wrong, and it
removed the one check that could refute the mechanism.** The poller sleeps
*after* its cycle, so the gap to the next `poll_log` stamp is
`cycle_wall + 300 + overshoot` and bounds the cycle above — from the same table
open item 2 already names, in the words "start **and finish** times".

H1 predicts the poller could not have committed for ~5 s on a cycle that
produced a failure, so those cycles must run long. The alternative — a third
party holding the lock while merely phase-locked to the poller — predicts they
run normal. Measured:

    population median cycle            300.415 s
    burst-matched cycles     n = 13    median 315.628   min 252.429  max 330.416
    repeat-only cycles       n =  7    median 300.406   min 300.401  max 300.888

    excess over population median   burst +15.21 s    repeat-only -0.01 s
    cycles >= 305 s                 burst 12 of 13    repeat-only 0 of 7
    Fisher two-sided                p = 0.00010

**The poller's own cycles ran ~15.2 s long exactly on the cycles that produced
a burst, and ran to the median on the cycles that did not.** That is the
mechanism measured rather than inferred, and it is the check that would have
flipped this document to a refusal.

One burst matched a cycle of **252.429 s — short, not long**, the single
exception in 13. It is not explained here.

**+15.2 s is also the right magnitude for the wrong-sounding reason.** It is
not three slow round trips: the population median cycle of 300.415 s means a
whole cycle — four round trips and four writes — normally completes in ≤0.415 s.
It is the *victim* blocking the poller. The runner and the poller share one
event loop and there is no thread offload anywhere on the DB path, so a
blocking `sqlite3` busy-wait freezes the loop the poller needs to reach its
commit. On a `journal_only` burst the victim blocks 5 s on the shared
connection and 5 s again on the throwaway, synchronously — 5.3 + 5 + 5 ≈ 15.3.
**A deadlock, not a slow network call.**

The earlier draft's "three Kalshi round trips at ~1.8 s each" is deleted: the
document's own C refutes it.

## 4. The repeats are a control, and the first draft's reason was inverted

The nine non-burst repeats scatter: 99.1, 50.2, 41.6, 30.8, 271.2, 6.5, 282.8,
5.3, 33.0 s. The first draft said this was because "a repeat fails whenever it
happens to collide". That is backwards — a repeat failing by collision would
sit at 5.3 s too.

The correct reading is `record_loop_failure_durably`'s own docstring: **the
repeats fail by a second, different mechanism.** A pass that died
mid-transaction leaves the shared connection on a stale WAL read snapshot, and
the next write fails *instantly* with `SQLITE_BUSY_SNAPSHOT` — the busy timeout
never runs, so there is no 5 s to wait and no dependence on poller phase. Two
mechanisms, two clocks.

That also answers why the burst is the right unit at all: the first failure of
a burst is the collision; every later one is the poison.

**It makes a checkable prediction on the new `rollback` journal lines**:
`in_transaction = True` on repeats. Not yet observable — no lock failure has
been journalled since the field shipped.

## 5. What was measured, precisely

**"A poller cycle start" — not "the fast branch."** `poll_log.polled_ms` is
written identically by the fast branch, the twice-daily mirror, and the boot
cycle, and nothing in this query distinguishes them. ADR 0091's frequency
argument needs the fast branch; the data does not supply it.

This matters, because **the mirror branch still contains the uncured defect on
live**: `ensure_estimate_markets_known` (`backend/estimate_match.py:56-124`)
writes inside a loop whose next iteration begins with a network fetch and does
not commit until the end. Write lock held across N round trips, once per boot
and twice a day. ADR 0091 did not touch it.

**Scope: the journal is written only by the chain runner's failure hook.** Lock
failures inside the poller itself, `bid_watch`, `hedge_watch` or the API process
never appear. "All 13 bursts" means all 13 bursts *of the chain runner's
passes*.

## 6. What this does NOT establish

- **That ADR 0091 worked.** Attribution and efficacy are different claims. All
  13 bursts predate the fix.
- **That the poller is the only holder**, or that it was the poller's own
  transaction rather than an automatic WAL checkpoint fired by its commit.
  Both put the poller at the trigger; only the first is what ADR 0091 fixed,
  and this does not separate them.
- **A general pre-fix lock duration.** The 13 are selected *for* long holds;
  the median cycle is 0.415 s and only the tail can be hit. The honest
  statement is "on the 13 cycles that produced a failure the lock was held
  ≥5.2 s", not a population figure.
- **Anything before 2026-08-30**, when the durable journal landed.

## 7. The forward instrument — and it must be registered before it is used

The first draft said one post-fix burst at ~5.3 s would refute ADR 0091. **Too
strong on three counts**, all from the audit:

1. It is a threshold re-evaluated against a growing record. A single burst in a
   0.72 s band is p ≈ 0.0024; checked after each of the next 50 bursts, the
   family-wise false-alarm rate is ~11%.
2. "~5.3 s" is not a decision rule. The interval has to be written down.
3. **It misidentifies what would be refuted.** A post-fix burst after a
   *mirror* cycle is fully explained by `estimate_match.py:56-124`, which ADR
   0091 never touched.

So the honest forward statement is *"the poller-cycle-start signature
persists"*, and any second look must split mirror cycles from fast cycles
before naming an ADR. **The band, the tolerance and the stopping rule must be
registered before the first post-fix burst arrives**, not after.
