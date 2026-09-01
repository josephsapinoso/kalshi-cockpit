# RESULT — the portfolio poller is the `database is locked` holder

**Taken 2026-09-01 on live `228f716`**, to the rule fixed in
[`2026-09-01-lock-holder-attribution-registration.md`](2026-09-01-lock-holder-attribution-registration.md),
which was written and committed before the join existed. Instrument:
`inspect_live_db lock-attribution`.

## The registered test

    n (bursts scored)             13
    k (offset <= W = 14 s)        13
    p0 = W / C                    0.0466      C = 300.415 s, observed median cycle gap
    expected under H0             0.606
    two-sided exact binomial p    ~6e-18
    VERDICT                       POLLER IMPLICATED

Preconditions met: `poll_log` spans the journal window (2026-08-18T08:16:53Z ..
2026-09-01T02:51:06Z against 2026-08-30T07:08:53Z .. 2026-08-31T11:01:00Z),
3,983 distinct cycles from 10,437 rows.

## The offsets are a spike, not a spread — and that is the finding

Every one of the 13 bursts:

    5.36  5.345  5.633  5.919  5.285  5.195  5.361
    5.283  5.285  5.340  5.331  5.520  5.279        seconds

Range **0.72 s**, all in [5.195, 5.919]. `BUSY_TIMEOUT_MS = 5_000`
(`backend/store/db.py:83`).

So the mechanism is legible in the numbers, not merely consistent with them:

    cycle start          t = 0
    poller takes lock    t ~ 0.3 s      one Kalshi round trip, then its first INSERT
    victim blocks
    victim raises        t ~ 5.3 s      after the FULL busy timeout

**The internal control was not designed and is the best part of the reading.**
The nine non-burst repeats — the passes that failed again inside a burst — do
**not** cluster: 99.1, 50.2, 41.6, 30.8, 271.2, 6.5, 282.8, 5.3, 33.0 s. A
repeat fails whenever it happens to collide, so it is not on the poller's
clock; a burst's first failure is. Two of the nine land inside W, against 0.42
expected, which is unremarkable at that n and is not offered as anything.

## A secondary observation, NOT registered

The offsets also bound the pre-fix lock duration, which nothing had measured.

A victim arriving `t` seconds after the lock is taken raises at `t + 5` **only
if the lock is still held then**; otherwise it acquires the lock on release and
succeeds. Observed raises stop at 5.92 s, so the lock was held for roughly
**5.3–5.9 s** and the failing victims are those arriving within ~0.9 s of
acquisition. That is three Kalshi round trips at ~1.8 s each — the shape ADR
0091's own docstring describes.

**This is an inference from the registered statistic, not the registered
statistic.** It was not pre-specified, no threshold governs it, and it should
be treated as a hypothesis about magnitude rather than a measurement of one.

## What this establishes

That the portfolio poller's fast branch held SQLite's write lock at the moment
each `database is locked` burst was raised, on all 13 bursts in the record.
ADR 0091's argument was a rate — *"four to five a day fits 288 windows and does
not fit two"* — and this is the first evidence placing observed failures inside
observed poller windows.

## What this does NOT establish

- **That ADR 0091 worked.** Attribution and efficacy are different claims. All
  13 bursts predate the fix (newest 2026-08-31T11:01:00Z; the fix deployed
  15:29:19Z). Efficacy is open item 1.
- **That the poller is the only holder.** `maybe_checkpoint`, the API's
  per-request connections and `store_closing_line` raise the same error. This
  says the poller was holding the lock at these 13 moments; it does not
  partition any other failure between candidates, and there is no other
  failure in the record to partition.
- **Anything before 2026-08-30**, when the durable journal landed.
- **That the ~5.3 s spike will persist.** It is a pre-fix signature. Post-fix
  the four steps commit separately, so the same query is now a *falsification*
  instrument — see below.

## What it changes, and this is the useful part

**Open item 1 no longer has to wait for silence.** It was blocked on a quiet
window that contains thirteen process restarts, and a restart is this class's
own documented cure — so counting quiet hours could never separate the fix
from the restarts. It now has a positive instrument instead:

- If new lock bursts appear and still spike at ~5.3 s after a poller cycle,
  **ADR 0091 did not work** — one burst is enough to say so, because the
  signature is that sharp.
- If new bursts appear and do **not** sit on the poller's clock, the poller is
  no longer the holder and the remaining candidates are in play.
- Silence remains uninformative, exactly as before.

A one-sided instrument that can refute in one observation is worth more here
than a two-sided one that needs 713 clusters.
