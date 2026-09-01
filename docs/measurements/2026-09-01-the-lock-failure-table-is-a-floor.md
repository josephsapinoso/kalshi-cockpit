# The `loop_failures` table is a floor, and the claim I wanted to make off it was refused

**Date:** 2026-09-01
**Instrument:** `scripts/inspect_live_db.py failure-journal`, built this session
**Live sha at the read:** `ad3efed`
**Audited by:** `measurement-skeptic`, before anything here entered the record

---

## 1. Why the instrument had to be built first

`tasks/NEXT.md` open item 4 read: *"Watch whether `database is locked` recurs.
`loop_failures` is the instrument."*

It named the wrong artifact. `backend/store/db.record_loop_failure_durably`
has appended every pass failure to `loop_failures.jsonl` on the data volume
since 2026-08-30, and its own docstring says why the table is not enough: a
pass that dies mid-transaction can leave the shared connection unable to
write, so the failure ROW fails with the same error as the failure. The
journal is the layer "no lock can refuse".

**Nothing read it.** `grep -rn loop_failures.jsonl` over the repo found the
writer (`scripts/run_loop.py:708`), tests of the writer, and no consumer on
any machine — not `inspect_live_db.py`, which is the only thing permitted to
run against the live box. So for two days the durable half of the record was
unreachable from the place the question gets asked.

`failure-journal` reads it. Eleven guards on the first pass, three more after
the audit, each verified by disabling what it guards and watching it go red.

---

## 2. What the reading says — the two claims that survived

### 2.1 The table lost 14 of 22, and the number is a census

Of **22 failures journalled since the durable recorder landed on 2026-08-30**,
**14 have no row in `loop_failures`**. All 22 are `OperationalError: database
is locked`, and the loss mechanism *is* that error refusing the insert — so
**for this failure class, under lock contention, any count taken off the table
is a floor.** Open item 4 named that table as the instrument.

Two limits on the sentence, both from the audit:

- **It is scoped to the journal's lifetime**, ~2 days. The table is older. The
  loss rate over the table's whole life is not measured here, and before
  `91a66f1` there was no fresh-connection fallback at all, so the earlier rate
  can only have been higher.
- **It is scoped to the condition.** A `PassDeadlineExceeded` or a `TypeError`
  inserts fine. This does not generalise beyond lock contention.

It is a census of a closed population, not a rate, so the burst
non-independence in §3 does not touch it.

### 2.2 The three outcomes, which is the population that may be quoted

    22 journalled
     8 recorded on the shared connection
     0 recorded on a fresh connection
    14 recorded on neither

For those 14, a write lock was held by something at the moment of recording,
so the stale-read-snapshot reading in `record_loop_failure_durably`'s docstring
does not describe them.

**Two things this does NOT establish, and the first is a mistake this document
exists partly to record.** The first write-up said *"14 of 14 lost lines say
both connections refused"*. That is a tautology: the 14 are **selected** by
having no table row, and `journal_only` is the only outcome that produces one.
A rate over a group defined by its own outcome is not a finding. The tally
above is the honest form, and it is now printed on the query's own screen.

Second: **it does not name the lock holder.** Anything holding the write lock
past `BUSY_TIMEOUT_MS = 5_000` produces this reading — the portfolio poller,
the API's per-request connections, `maybe_checkpoint`, `store_closing_line`.
So this is *consistent with* ADR 0091's poller diagnosis and is **not evidence
for it**. What would separate them is correlating the 22 stamps against the
poller's own start and finish times. That has not been done.

And the reading samples the wrong moment: the diagnosis describes the lock
state when the RECORD was attempted — after the pass raised, after the journal
append, and after a `rollback()` that swallows `sqlite3.Error` and never
records whether it worked. "The shared connection was still holding the lock
and refused the fresh one itself" is **not excluded**.

### 2.3 A reader querying the table by `pass_kind` sees a population with no quote failures in it

All 8 surviving rows are `pass_kind = full`; 2 of the 22 journalled failures
were quote passes, and both are among the 14 lost. At n = 2 this is entirely
consistent with chance (Fisher two-sided **p = 0.52**) and is **not** evidence
of a kind-specific loss mechanism. It is one more instance of §2.1.

---

## 3. The claim that was REFUSED, and why it is the useful half

I wanted to write this:

> Lock failures on full passes fell from 15.84% (16 of 101) to 0 of 30 in the
> 8.07 hours after ADR 0091 deployed, on the same hardware. Expected 4.75,
> observed 0, P(0) = 0.006.

**It must not be written, in any form, hedged or not.** Five defects, in
descending order of how fatal they are.

### 3.1 The quiet run starts BEFORE the fix

    newest journalled failure   2026-08-31T11:01:00Z
    ADR 0091 deployed           2026-08-31T15:29:19Z   (Fly release 182)

**4.47 hours of pre-fix code ran with zero failures before the deploy.** In
full-pass walk lines the quiet run is 50 passes, of which **14 ran on pre-fix
code and 36 after**. The deploy sits at position 14 of 50, and nothing in the
data locates the change at it.

Run the refused claim's own test on the pre-fix half and it "detects" a fix
across an interval in which no fix shipped. That is the falsifying test, and
it fails it.

Both numbers were on my screen an hour before I wrote the claim. I never
subtracted them.

### 3.2 The outcome definition changed inside the post-fix window

`badd88e` (ADR 0092) was committed **2026-08-31T17:20:15Z**, 1.85 h into the
post-fix window, covering ~27 of its 30 attempts. It moved the store inside
`run_scoring_pass`'s guard, so a `database is locked` on one closing line now
costs one line instead of the pass.

Before it, that lock produced a journalled failure. After it, it cannot. **The
two arms do not share a definition of the outcome, and the numerator was
redefined mid-window in the direction that produces the good news.**

### 3.3 The denominator premise was wrong

I claimed the walk line is written after the pass returns. It is written after
the **walk** — `scripts/run_loop.py:1368`, whose own adjacent comment says
*"After the walk, before scoring: ... the second half of the pass can still
die."* `score_settle_and_alert` runs afterwards and is full of DB writers.

So a failure has three outcomes, not two: pre-walk (no walk line), post-walk
(a walk line **and** a journal line), success (a walk line). `attempts =
successes + failures` double-counts every post-walk failure, and "succeeded
85" is not 85 successes — it is 85 passes that reached the walk.

`_q_walk_log`'s own "What this does not establish" already said this. I read
past it.

### 3.4 The unit is the burst, not the pass

`Tempo.pass_kind` re-arms a full pass immediately when one fails, because
`completed_full_pass` is on the success path only — so a failed full pass is
followed by another full pass at once. The 22 failures are **13 independent
bursts** (`consecutive_failures == 1`), mean size 1.69, max 4. Treating passes
as independent draws inflates significance by roughly an order of magnitude at
this burst size.

The burst count was exactly recoverable from a column I was already printing,
and I did not use it.

### 3.5 The window was cut where the data ran out, and the cut flattered it

The 6,000-line walk read starts at 2026-08-30T16:18:36Z. Four journalled
failures sit before it, and so do ~31 quiet passes. Extending the baseline to
what the file actually held lowers the pre-fix rate and weakens the result;
the cut I took raised it.

Three further lock-relevant changes landed inside the baseline window
(`7a3ded9` WAL checkpoint, `acb8233`, `07a89e2`/`5c7aaf5` candidate index), and
deploys restart the machine, which itself clears accumulated state and injects
an extra full pass at boot against a freshly-opened database. "The same
hardware" is true and irrelevant: the software changed at least four times
across the comparison.

---

## 4. What may be said

> No `database is locked` failure has been journalled since
> 2026-08-31T11:01:00Z — 50 consecutive full-pass walk lines through
> 2026-09-01T00:39:19Z, of which 14 ran on pre-fix code and 36 after ADR 0091
> deployed at 15:29:19Z. **The quiet run began 4.5 hours before the fix, so it
> cannot be attributed to it.** Three further changes affecting lock
> contention landed inside the comparison, and ADR 0092 — 1.85 h into the
> post-fix window — stopped a lock in the closing-line store from killing the
> pass at all, so 27 of the 36 post-fix attempts ran under a definition of
> "failure" that excludes a class the baseline counted. **No rate comparison
> between these windows is available.**

**Open item 4 stays open.** What changed is that the instrument now works.

---

## 5. What would settle it

1. **Let the record accumulate under one definition.** The next look must start
   after `badd88e` and use bursts, not passes, as the unit. At the pre-fix
   burst rate (~0.39/h) a 30-hour clean window expects ~11.7 bursts, which
   clears the ≥5 rule on the correct unit.
2. **Attribute the holder before crediting ADR 0091.** Correlate the 22 stamps
   against the poller's own start and finish times. Nothing else separates the
   poller from the API's connections or the checkpoint.
3. **Record whether the `rollback()` succeeded.** One boolean in the journal
   separates "the shared connection was still poisoned" from "someone else
   held the lock", and it is the single observation §2.2 is missing.

## What this document does not establish

- **That the lock failures have stopped.** It establishes that none has been
  journalled in 13.85 hours, and that the interval is not attributable.
- **Anything before 2026-08-30**, when the durable recorder landed.
- **That the journal is complete.** `_journal` swallows `OSError`, and a
  container that dies between passes writes neither journal nor row.
  `pass-gaps` is the instrument for that half; the pair is the reading.
