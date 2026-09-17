# ADR 0163 — Buy residency for the positions screen, and register the growth fix separately

- **Status:** accepted
- **Date:** 2026-09-17
- **Decider:** Joe, ticket #55, answer `55E`
- **Supersedes nothing.** Amends the sizing rationale in `fly.live.toml [[vm]]`,
  which is kept verbatim rather than rewritten.

## The decision

`fly.live.toml` `memory` goes **2gb -> 4gb**, and the non-destructive
`fair_prices` dedup gets **its own pre-registration** rather than a build.

Joe was offered five options and took `E`, which is `A` plus the registration.
The two halves are **complements, not alternatives**, and the reason is written
in this repo's own voice: the 2gb comment already said *"This buys headroom; it
does not fix the growth ... If this line ever needs raising again, that is the
thing to fix rather than this number."* It has needed raising again, for the
reason it named. Paying moves residency once; only the dedup touches the growth
term.

## Why

`/api/parlays` — the positions screen, the one he opens while a game is running
— returned 503 `read_budget_exceeded` in production on 2026-09-10.
`ladder_candidates` took **74.8 s against the 25 s ceiling** (ADR 0135).

Nothing was broken. The arithmetic:

    box RAM                      2 GB, no swap
    database                     5,070,802,944 B
    page cache ceiling          ~1.49 GB
    maximum residency           ~29%

Resident, the query is ~2 s. Not resident, 75. Two consequences follow from
that and both are in the code's own notes: **every restart is a coin flip on a
503 and every deploy is a restart**, and **any large read elsewhere evicts the
cache** — on 2026-09-10 a background analysis read a big table and his next tap
paid for it minutes later, which is why nobody connected the two at the time.

4 GB takes maximum residency from ~29% to ~69%.

## Why 4 GB and not 8

8 GB lands near the **~$31/month** that the `size` comment in the same block
already declined once as *"disproportionate"* against a **$100 deployed
bankroll**, and nothing has shown 4 GB insufficient. This is the same
discipline `shared-cpu-2x` was chosen under: buy the step that is measured, not
the step that feels safe. The trigger for revisiting is the same shape too — if
the 503 recurs at 4 GB, that is the moment to spend the difference.

**The bankroll figure is two weeks old and he has been betting since.** Re-read
the balance before repeating it in any future comparison.

## What this decision does NOT rest on

**The cold path has never been measured.** Every timing on the record is from a
warm box; the read budget has only ever fired cold or after an eviction. The
mechanism is arithmetic about residency, not an observed before/after, and this
ADR does not pretend otherwise.

**The slow query was not a `fair_prices` read.** It was `ladder_candidates`.
Shrinking `fair_prices` frees cache *for* it — that is the mechanism, and it is
plausible rather than demonstrated. Relax residency and something else may
bind: the plan, IOPS, or the 25 s ceiling itself.

Therefore: **re-measure after this lands and record whether residency actually
moved.** `scripts/time_live_routes.py` keeps per-rep maxima since 2026-09-17
(before that it discarded the tail, which is what made a previous session
mistake a median for a bound). A bigger box that did not help is a fact worth
having, and the change is reversible in one line.

## Why the dedup is a registration and not a build

The observation behind it — consecutive `fair_prices` rows for one key
value-identical at 99.73% / 99.61% / 99.75% — is real and is **not usable as a
premise**. Its own document says so: *recorded, not registered*; three windows
of **one MLB day**; the cluster **is** the day; **no threshold was named before
the rate was computed**; and its transition counting may not be correctly keyed.
Building off it would launder an unregistered observation into a fact, which is
the failure mode this repo has the most scar tissue about.

So the threshold that makes dedup worth doing is fixed **before** the rate is
re-measured, with a falsifier, a clustering floor over distinct days and sports,
and a stated guarantee about what remains reconstructible — that last being the
property that distinguishes it from the destructive option.

## The destructive downsample stays closed

Different thing, and it is not reopened here. It was measured, registered and
**declined** at §6 NOT WORTH ARMING when the `fair_prices` family was **0.90 GB**
against today's 2,409,955,328 B — **2.68x** growth — and that registration
**forbids raising its pinned constant after the fact**. Reopening it needs a
successor registration of its own, not an appeal to the new size.

## Consequences

- One `memory` line, plus a rationale block that keeps the 2gb reasoning
  verbatim beside it. No code change, no schema change, `SCHEMA_VERSION` stays
  44.
- A monthly bill rises by roughly $5–10. Read the exact figure off Fly's own
  calculator rather than trusting the per-GB rule this was estimated from.
- Reversible in one line if the 503 persists or residency does not move.
- The growth term is unaddressed until the dedup registration resolves, and
  this ADR does not claim otherwise.
