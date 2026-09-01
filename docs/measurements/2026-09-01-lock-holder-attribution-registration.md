# PRE-REGISTRATION — is the portfolio poller the `database is locked` holder?

**Written 2026-09-01, before the join was computed.** The inputs existed on
the live box at the time of writing and neither had been read against the
other. `tasks/NEXT.md` open item 2: *"Before crediting ADR 0091, attribute the
holder. Correlate the 22 journal stamps against the portfolio poller's own
start and finish times. Nothing else separates the poller from the API's
connections or the checkpoint, and the ADR is currently un-attributed on live
evidence."*

This document fixes the population, the unit, the statistic, the decision rule
and the refusal conditions **before** the numbers are produced, because there
are several defensible ways to slice this and the answer is visible in a
scatter plot the moment you draw one.

---

## 1. The claim under test

ADR 0091 changed `poll_portfolio_forever`'s fast branch so each of its four
steps commits before the next network call. Before it, all four shared one
transaction: the first INSERT took SQLite's write lock and nothing released it
until a commit **three Kalshi round trips later**. Every other writer landing
in that window waited out `BUSY_TIMEOUT_MS` (5,000 ms, `backend/store/db.py:83`)
and raised `database is locked`.

**The ADR's own frequency argument, from the code comment
(`backend/portfolio_poll.py`):** the 12-hour mirror branch had the identical
shape, but the fast branch runs every `BALANCE_INTERVAL_S = 300` s — 288 times
a day — and *"the observed failure rate (four to five a day) fits 288 windows
and does not fit two."*

That is an argument from a rate, not an attribution. **Nothing has yet placed a
single observed failure inside a single poller window.** This registration does
that.

## 2. Population

Every line in `/data/loop_failures.jsonl` that is a failure line (not a
`diagnosis` or `rollback` line) whose `error` contains `database is locked`.

At the time of writing that is **22 lines**, the oldest 2026-08-30T07:08:53Z
and the newest 2026-08-31T11:01:00Z.

**The journal, not the `loop_failures` table.** The table lost 14 of these 22
(`docs/measurements/2026-09-01-the-lock-failure-table-is-a-floor.md`), and the
lost ones are lost *because* of lock contention — precisely the population
under study. A table-derived population would be selected on the outcome.

**Every one of the 22 is pre-ADR-0091.** The fix deployed 2026-08-31T15:29:19Z
(Fly release 182); the newest failure is 11:01:00Z the same day. So this is an
attribution test on the defect's own population, not a before/after.

## 3. Unit — the burst, not the pass

`Tempo.pass_kind` re-arms a full pass immediately when one fails, so
consecutive failures are not independent draws. The unit is the **burst**: a
failure line with `consecutive_failures == 1`. Every other line is dropped.

This is the unit the 2026-08-25 audit imposed on the CLV look for the same
reason, and the 2026-09-01 entry re-imposed it on open item 1.

## 4. The statistic

For each burst at `failed_ms = t`:

    offset = t - max{ polled_ms in poll_log : polled_ms <= t }

in seconds. `poll_log.polled_ms` is the poller **cycle start**: `now_ms` is
computed once at the top of `poll_portfolio_forever`'s loop body and passed
down to every `log_poll_attempt` in that cycle, so all rows of one cycle carry
one stamp and **the cycle's duration is not recorded anywhere.** That is a
limitation of the instrument, not a choice made here, and §7 states what it
costs.

## 5. The window under H1, fixed now

The lock is taken at the first INSERT — after one Kalshi round trip — and held
until the commit after the last. A victim then waits `BUSY_TIMEOUT_MS` before
raising, and its `failed_ms` is stamped at the raise.

So a poller-caused failure has

    offset ∈ [ RTT₁ , RTT₁+RTT₂+RTT₃ + 5.0 s ]

**RTT is not measured on this box.** Bounding a Kalshi REST round trip at
3 s each (generous; a slower call makes the window wider and the test more
conservative in the convicting direction) gives the registered window

    W = [0, 14] seconds        ← fixed before looking

## 6. Decision rule

Let `k` = bursts with `offset ≤ 14 s`, `n` = total bursts, and `C` = the median
observed gap between consecutive distinct `poll_log.polled_ms` values (expected
≈ 300 s; **read from the data, not assumed**, and reported).

Null H0: bursts fall uniformly in the poller cycle, i.e. `k ~ Binomial(n, 14/C)`.

    two-sided exact binomial p < 0.01   →  POLLER IMPLICATED
    otherwise                           →  NOT ESTABLISHED

**0.01 rather than 0.05, deliberately.** This record has run many tests and
CLAUDE.md's measurement rules require counting them; a 0.05 threshold on the
n-th test of a corpus is not a 5% error rate.

## 7. What a null result does NOT mean — the refusal condition

**A non-significant result may not be reported as "the poller is exonerated",
and this is the clause most likely to be violated later.**

With `n ≈ 13` and `p0 = 14/300 = 0.047`, the expected count under H0 is
**0.61**. The test is powerful in one direction only: it can convict the
poller (k ≥ 4 gives p ≈ 0.0007) and it cannot clear it, because 13 bursts
cannot bound a 4.7% window away from zero.

So the permitted verdicts are exactly:

- **POLLER IMPLICATED** — k large, p < 0.01.
- **NOT ESTABLISHED** — anything else. ADR 0091 stays un-attributed on live
  evidence, which is the state open item 2 already records.

There is no "POLLER EXONERATED" outcome available from this design. Writing
one would need a different instrument — the cycle's *end* stamp, which §4 says
does not exist.

## 8. What else this does not establish

- **That the poller is the ONLY holder.** `maybe_checkpoint`, the API's
  per-request connections and `store_closing_line` all produce the same error,
  and a conviction here does not partition the 22 between them.
- **That ADR 0091 fixed anything.** Attribution and efficacy are different
  claims; efficacy is open item 1 and is separately blocked (see the
  2026-09-01 `NEXT.md` entry on the thirteen restarts inside its window).
- **Anything about `poll_log`'s completeness.** If the poller's own cycle
  died before its commit, that cycle leaves no stamp, and a burst near it
  would be scored against an earlier cycle — inflating its offset and biasing
  the test **against** H1. The coverage window and row count are reported.
- **Anything before 2026-08-30**, when the durable journal landed.

## 9. Stopping rule

One look, on the population frozen at §2. If the count has grown by the time
the join runs, the new lines are reported **separately** and the registered
verdict is taken on the 22.
