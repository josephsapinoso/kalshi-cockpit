# The 15:21Z window: the store leg is not the problem, and the slow state is not the window

Taken 2026-08-19 15:21-16:56Z on live (`c77c35b`, then `d654ba8`), the
`baseball_mlb` window the previous handoff named as the test. Read against
`2026-08-19-window-store-leg-plan.md`, registered at 13:55Z before the window
opened.

**Read the CORRECTION section before acting on anything above it.** This file
was written in two passes and the second one refutes a reading in the first.
Both are kept, in order, because which claim survived contact is the point.

**What this establishes.** That `leg_store_ms` on a quote pass came in *below*
its projection and is not what puts the pass over its cadence; that ADR 0054's
predicted table-size effect is not detectable; that `leg_price_ms` was the
dominant leg during the slow state; that within pricing,
`link_discovered_events` is **92%** of the cost; and that the slow state
**disappeared across a process restart with the window still open**.

**What it does not.** It does not explain what makes the slow state appear or
go away. The first pass proposed the window and the second refuted it; no
replacement is offered, because uptime does not fit either. One window, one
sport, one machine.

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

## CORRECTION, 16:50Z — the window correlation does not survive

The section above is left as written because the correction is the useful part.
It was hedged (*"correlate and a plausible mechanism, not a measurement"*), and
the hedge was doing real work: **the correlate itself is now refuted.**

`leg_price_ms` was split into four phases and deployed at 16:34Z. Eleven
minutes of quote passes with the **same window still open**, on the same code
and the same database:

```
took_s     8.0 - 10.6   (was 17-32)
leg_price_ms   2167 - 2570   (was 12000-20000)
  setup      0ms
  link    2023 - 2423   <- 92% of pricing
  judge     20 -   51
  persist  118 -  156
```

Flat across the whole eleven minutes — **no climb**. The window did not close;
the passes simply stopped being slow.

So *"pricing is expensive while a window is open"* is **wrong as stated**. The
window was open for both readings. What changed between them is the process:
live was restarted by the 16:34Z deploy.

**And uptime alone does not explain it either**, which is why no replacement
theory is offered here. The 12-20s readings were taken **6-45 minutes** after
the 15:30Z restart; the 2.2s readings are 2-13 minutes after the 16:34Z one.
Those ranges overlap. Something reset that is not simply "time since boot", and
this file does not know what it is.

**What is now known, and it is the useful half:** in steady state the pass costs
8-10s against its 15s cadence with room to spare, and **`link_discovered_events`
is 92% of pricing**. If the slow state returns, the split will say which phase
it lands in — which is the whole reason it was instrumented rather than argued
about. Until it does, there is nothing to fix.

**Do not carry "pricing tracks the window" forward.** It was written here, in
this file, four hours before it was refuted, and it would have sent the next
session to read the sweep path.

## THE SLOW STATE RETURNED AT 16:48Z AND THE SPLIT NAMED IT: `link_discovered_events`

Fifteen minutes after the split shipped, the slow state came back on its own,
with the window unchanged and no deploy in between. The instrumentation
answered in one pass what four sessions of reasoning did not.

```
                took_s   walk   store   PRICE   link   judge  persist
16:47:27 fast      8.1   2298    3405    2274    2131     20      122
16:47:53 fast      9.8   2294    5136    2236    2094     20      122
16:48:34 SLOW     26.4   2333    3738   19139   17211    321     1606
16:49:16 SLOW     29.3   2294    3429   22637   20716    164     1755
16:49:54 SLOW     23.9   2561    4839   14959   12716    318     1923
```

**`leg_price_link_ms` is 90% of the slow pass**, and it moves **10x** — 2.1s to
20.7s — while every other leg stays where it was. `leg_walk_ms` does not move
at all (2.3s throughout). `leg_store_ms` does not move (3.4-5.1s both states).
`judge` and `persist` rise ~10x but are 0.3s and 1.9s at their worst, so
together they are under 10% of the excess.

**The input is identical.** `events_discovered` is 531 and `events_linked` is
81 in every row above, fast and slow. Same work, ten times the wall clock.

**The transition is abrupt, not a ramp** — one pass at 2.1s, the next at 17.2s,
41 seconds apart. That rules out the gradual-accumulation story the earlier
"uptime" guess assumed, and it is why the restart appeared to fix it: a restart
lands you in the fast state, and so does simply waiting.

### What this closes and what it opens

**Closed:** the walk (ADR 0053 works, 2.3s, never moves), the store leg
(ADR 0054's question, does not move), the devig loop, and the Skeptic. None of
them is the overrun. Four legs eliminated by measurement rather than argument.

**Open:** what makes `link_discovered_events` cost 20s for the same 531 events
it prices in 2.1s a minute earlier. It is not called with different input and
it is not the network — the walk is a separate leg and is flat. That leaves
something inside the call or under it, and this file does not name it, because
naming it is exactly the step that has been wrong four times on this incident.

**Start with `backend/runner.py`'s `link_discovered_events` and the queries it
runs per event.** `alias_cache` is built fresh per pass and passed in, so a
cold cache costs the same every pass and cannot explain a 10x swing between
adjacent passes. Time inside the call before changing it.

## 17:16Z — THE INNER TIMER FIRED, AND IT IS ONE QUERY RUN 456 TIMES

The conditional `link slow` report shipped at 17:04Z and fired twelve minutes
later, on the first slow pass after the restart:

```
link slow: 11057ms total; candidates 10779ms over 456 calls,
unmatched writes 117ms, link writes 1ms, other 159ms
(531 discovered, 80 linked)
```

**97.5% of the leg is `_match_candidates`, called 456 times.** The unmatched
writes — 450 rows a pass, the other standing suspect — are **117ms**, about 1%.
Link writes are 1ms. The remainder, which includes the whole prop path, is
159ms. Both suspects named in the handoff were testable and one of them was
wrong; the timer separated them in a single pass.

### Why it is 456 identical queries

`_match_candidates(conn, sport_key, since_ms=now - 86_400_000)` is called
**once per event**, and `since_ms` derives from the pass's single `now`. So its
arguments vary only by `sport_key`, of which a slate has a handful. The
`alias_cache` immediately beside it in the same loop was already memoised per
sport; the candidate query was not.

### And this explains the drift, which no previous theory did

The query is `SELECT DISTINCT odds_event_id, commence_ms, home_team, away_team
FROM odds_snapshots WHERE sport_key = ? AND commence_ms >= ?` — a distinct scan
over a table that grows by **~900 rows per odds sweep**, several sweeps an hour
while a window is open.

That is why the leg reads ~2.1s shortly after a restart and 11-20s later in a
window with **identical event counts**: the multiplier is constant at ~456 and
the per-call cost climbs with the table. It also explains why a restart appeared
to help and why "uptime" did not fit — what matters is how much has been swept
into `odds_snapshots` since, not how long the process has been up.

### The fix

Memoise per `(sport_key)` for the life of the pass, exactly as the aliases
beside it already are. `tests/test_candidate_cache.py` asserts one query per
sport, a separate entry per sport, that the cache does **not** survive the pass
(a process-scoped cache would freeze the fixture set at boot — a correctness bug
traded for a performance one, and a far quieter one), and that the same events
still link. Three breakages applied and watched go red.

**The correctness argument is independent of the speed one:** one snapshot per
pass means every event on a slate links against the same candidate set, where
before an event late in the loop could see fixtures an earlier one could not.

**Expect the leg to fall in both states, not just the slow one** — the fast
state's 2.1s is the same 456 calls against a smaller table. Verify on live
before believing it.

### Verified on live, 17:26-17:31Z (`a482fea`), 14 consecutive quote passes

```
                    link      price     store      took_s
before (fast)   2023-2423  2167-2570  3405-5359   8.1-10.6
after            251- 371   491-1177  3814-10001   6.8- 9.6
```

**`leg_price_link_ms` fell 2.1s -> 0.25s, about 8x**, and pricing fell with it
to ~0.59s. This is the *fast* state on both sides — the same 456 calls that
now number about five — so it is the multiplier being removed, exactly as
predicted, and not the slow state being avoided.

**The slow state has not been observed since and that is not evidence yet.**
Its arithmetic is 456 calls x ~24ms; at five calls the same per-call cost is
~0.12s, so it should not be reachable. But the conditions that produced it —
a window that has been sweeping into `odds_snapshots` for a while — have not
recurred since the deploy. **Confirm on the next open window**, by watching for
a `link slow` line that should now never fire.

`leg_store_ms` is now the largest leg at 3.8-10.0s. It was never the thing
pushing a pass over its cadence and still is not: `took_s` sits at 6.8-9.6s
against 15s.





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
