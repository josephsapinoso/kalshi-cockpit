# The 15:21Z window: the store leg is not the problem, and pricing is

Taken 2026-08-19 15:21-16:21Z on live (`c77c35b`), the `baseball_mlb` window the
previous handoff named as the test. Read against
`2026-08-19-window-store-leg-plan.md`, registered at 13:55Z before the window
opened.

**What this establishes.** That `leg_store_ms` on a quote pass came in *below*
the projection, that the table-size effect ADR 0054 predicted is not detectable,
and that `leg_price_ms` — never measured on a quote pass before — is now the
dominant leg and is what puts the pass over its 15s cadence.

**What it does not.** It does not explain *why* pricing costs 12-20s here
against ~3s on a closed-window pass. That is stated as an observation with a
correlate, not a cause. One window, one sport, one machine.

## The registered comparison: UNRESOLVED

Prune-free full passes, which is the isolating comparison the plan registered:

| when | rows | `quotes_pruned` | `leg_store_ms` |
|---|---|---|---|
| **before** 13:00-ish | 6.9M | 0 (pre-ADR 0054) | **5997** |
| **before** | 6.9M | 0 | **14030** |
| **after** 15:46:48 | ~4.9M | 0 | **9164** |
| **after** 16:03:01 | ~4.9M | 0 | **14345** |

The registered rule: *any sample inside 5997-14030 is UNRESOLVED*. 9164 is
inside it. **UNRESOLVED is the verdict**, and it is the one the plan said was
most likely, written down before the numbers existed.

So **ADR 0054's latency half is neither confirmed nor refuted**. The table lost
28% of its rows and the store leg did not detectably move. The disk half stands
on its own measurement and is not affected.

n = 2 on each side. It is not enough and no amount of reading it differently
makes it enough.

## The question the handoff asked, answered

`leg_store_ms` on **quote** passes during the window, n = 24:

```
2911 2999 3002 3112 3215 3674 3937 4277 4288 4290 4304 4488
4502 4502 4799 4838 5109 5160 6211 6699 6938 7900 8150 8775
median ~4.5s   range 2.9-8.8s
```

The handoff projected **8-12s** and called it "a projection with no margin".
The measurement is **roughly half that**, and only 2 of 24 samples reach 8s.

**The store leg is not what puts a quote pass over 15s.** That question is
closed.

## What is: the pricing leg, which nobody had measured on a quote pass

The same 24 quote passes, by leg:

| leg | typical | share |
|---|---|---|
| `leg_walk_ms` | **2.3s** | flat, ADR 0053 working exactly as designed |
| `leg_parse_ms` | <0.1s | never a factor |
| `leg_store_ms` | **4.5s** | half the projection |
| `leg_price_ms` | **12-20s** | **the pass** |

`took_s` ran **17-32s against a 15s cadence**, and the loop logged "a QUOTE
pass took 25.0s" over and over. That is the same overrun that took live down on
2026-08-19, with a different leg responsible.

**And the pricing leg tracks the window, not the table.** Full passes all
morning with the window shut:

```
window CLOSED  leg_price_ms  3129 2884 3467 2904 2668 3110 2678
window OPEN    leg_price_ms  20031  30086
```

A ~10x jump, while `markets_quoted` moved 5297 -> 5766 (+9%) and
`fair_prices_written` moved 30 -> 32. **The volume did not change; the window
did.**

The obvious reading is that pricing only has real work when there are fresh
odds to devig against, and a closed window has none — `dropped_no_books` is 60-65
of ~64 confirmable rows throughout. **That is a correlate and a plausible
mechanism, not a measurement**, and this file does not claim it. It is stated so
the next session tests it rather than rediscovering the correlation.

This is the fourth leg to be blamed on this one incident and the first three
were wrong. Time it before fixing it.

## The window gate has an off-by-one-pass, as predicted

The plan registered a falsifiable prediction: `run_loop.py` assigns
`tempo.window_open` *after* a pass and `run_once` reads it *before*, so the
first full pass after a window opens prunes on a stale flag.

```
15:21Z  window opens
15:32:14  full  took_s  94.3   quotes_pruned 40000   <- pruned anyway
15:46:48  full  took_s  51.2   quotes_pruned     0   <- gate latched
16:03:01  full  took_s  92.9   quotes_pruned     0
```

**Confirmed.** The stated falsifier — `quotes_pruned: 0` on that first pass —
did not occur.

Cost: one ~40s prune inside the first minutes of a window, once per window. The
`51.2` against the morning's `90-172` also confirms the gate itself works when
it does latch, which is the half ADR 0054 got right.

Not fixed here. The fix is to read `window_status` before the pass rather than
after, and that touches the cadence too — the loop can also take up to a full
900s to notice a window opened at all, for the same reason and with a larger
cost. One change, its own ADR.

## Health checks

Zero failures since the 15:30Z deploy, across a full open window with 25-30s
passes — against roughly three per hour before it. Confirmed directly on live at
Fly's own interval: **0 failures of 12** at 15s spacing over one reused
connection, where the same probe returned 5 of 10 that morning. See
`2026-08-19-health-flap-is-the-proxy-hop.md`.
