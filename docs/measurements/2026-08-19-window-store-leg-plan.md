# How to read the 15:21Z window — written at 13:55Z, before it opened

Registration for the test the 2026-08-19 ~12:15Z handoff left as THE job:
**did ADR 0054's retention window make `leg_store_ms` fall?**

Written before the window opened, deliberately. The handoff's own
`2026-08-19-quote-pass-leg-attribution.md` records three wrong attributions on
this one incident, every one of them from choosing the comparison after seeing
the numbers.

## The handoff named the wrong comparison, and here is why

The brief says to watch `leg_store_ms` on a **quote pass**. That test cannot
answer the question it is being asked, because **there is no before-side for
it**: every pre-ADR-0054 quote pass was uninstrumented and carries `took_s`
only. Comparing an instrumented after to an uninstrumented before is not a
comparison.

The **full pass** does have a before-side with legs — the two first-instrumented
passes this morning:

```
BEFORE   6.9M rows, full pass, NO prune    store 5997ms  (took_s 44.6)
                                           store 14030ms (took_s 54.9)
```

Those two are prune-free: ADR 0054 records full passes going 50s -> 87.3s
*once the prune was in them*, and `took_s` of 44.6 and 54.9 puts both before it.

So the isolating comparison is a **prune-free full pass at the reduced table
size** — and a full pass gets exactly that while a window is open, because
`runner.py:2102` skips retention on `window_open`. Same pass kind, same work,
same instrumentation, prune absent on both sides, table size the only thing
that moved.

## What has already been measured, and why it is not the answer

Four full passes captured 13:41-13:49Z, at ~4.95M rows, **with the prune
running**:

```
AFTER (with prune)  store 5416 / 10450 / 10225 / 11569 ms   took_s 80.6-126.1
```

Mean 9.4s against the before-pair's 10.0s. **This is not a result.** The
after-side carries a concurrent multi-million-row `DELETE` competing for the
same write lock, and the before-side does not, so a table-size saving and a
prune cost are added together with opposite signs and cannot be separated.
n = 2 on one side, and it spans 5997-14030 — a 2.3x spread within itself.

## The registered read

Take the **prune-free full passes** inside 15:21Z-16:21Z (`quotes_pruned: 0`)
and compare their `leg_store_ms` against the before-pair.

| outcome | verdict |
|---|---|
| every sample below 5997 | ADR 0054's latency half **holds** |
| any sample inside 5997-14030 | **UNRESOLVED** — the before-pair's own spread swallows it |
| every sample above 14030 | latency half **refuted** |

n on the before side is **2**. That is weak, it is all there is, and saying so
now is the point: the interval is wide enough that "unresolved" is the likely
honest answer, and it must not be reported as "no improvement" or as a win.

Report the spread, not a mean. ADR 0054's **disk** half stands on its own
measurement either way — 6.9M rows to 4.92M is not in dispute.

## A prediction that is not about the store leg

`scripts/run_loop.py` computes `window_status(...)` and assigns
`tempo.window_open` **after** the pass, in the post-pass block at line 543,
while `run_once(..., window_open=tempo.window_open)` at line 577 reads it
**before**. The value a pass gates its prune on is therefore the one computed
at the end of the *previous* pass.

So: **the first full pass after 15:21Z will still prune**, carrying ~80s of
delete into the first minutes of the window — the exact minutes the fast
cadence exists to protect. The gate then latches and later full passes skip it.

Falsifiable as stated: if the first full pass after 15:21Z reports
`quotes_pruned: 0`, this reading is wrong.

Bounded to one pass per window, so it is a defect to record, not an incident.
It is also **not** the same thing as the cadence lag — the loop can take up to
one slow interval (900s) to notice a window opened at all, because `interval()`
reads the same post-pass flag. That lag predates ADR 0054.
