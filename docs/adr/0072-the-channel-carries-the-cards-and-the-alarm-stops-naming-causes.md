# ADR 0072 — The channel carries the cards, and the alarm stops naming causes

- **Status:** Accepted
- **Date:** 2026-08-26
- **Supersedes:** nothing. Extends ADR 0071 (what the desk is for) and ADR 0049
  (the off-box watchdog).
- **Shipped:** `9f96b5f`, `b7e6f9f`. Live at `b7e6f9f`, schema v22.

## Context

Two unrelated things arrived in the same hour and turned out to share a shape.

A heartbeat alarm fired — *"the recording loop has not written a quote for 35
minutes. **It is alive and stuck.**"* And Joe asked for the Discord webhook to
carry the desk's parlay cards, with Kalshi buys if possible.

The shape they share: **both are a system telling its operator something, and in
both the honest content is narrower than what was being said.**

## Decision 1 — a monitor reports what it measured, not what it suspects

### The alarm was right that something was wrong

Established read-only before any edit:

| Claim | Evidence |
|---|---|
| Fired once, self-cleared | heartbeat runs 20:24Z ok, 20:41:37Z failed, 20:55Z ok |
| Not a restart | Fly releases 132 (19:01:40Z) and 133 (21:00:36Z) bracket it; no machine event between |
| Not a designed sleep | heartbeat stamped every pass (`runner.py:2493`); slow cadence 900s ±15% ⇒ **ceiling 1,035s ≈ 17.3 min** |
| A real hole | `odds_sweep_log` gap of **2,678s** ending 20:51:02Z; every other gap that day 842–1,001s |

So two or three passes never finished.

### It was wrong to say which

At least three states produce a large `recorder.age_ms`: a wedged pass, a run of
passes failing before the heartbeat write (`run_forever` tolerates five), and a
restart the record has not caught up with. The check reads **one field** and can
separate none of them.

**We therefore rule: alert text may contain only nouns traceable to a field the
check actually read.** The alarm now states the measurement and names the three
candidates. This is the same defect as ADR-less lesson *"a refusal that names its
own predicate describes a symptom"*, one layer out — there a component knew too
little and said it precisely; here a monitor knew too little and said more.

### And the reasoning behind its threshold had rotted

The 30-minute threshold was justified as "two missed full passes", because
"quote passes run far more often". That second clause **stopped being true when
ADR 0071 §2.6 made the odds feed follow attention** — the 15s cadence runs only
while the odds window is open, and a quiet night keeps it shut.

The number survives: 30 min is 1.74× the 17.3-minute ceiling, which is the
property that matters. The prose did not.
`tests/test_heartbeat_threshold_arithmetic.py` now pins the property against the
real `JITTER` constant, so the next cadence change fails a test rather than
silently invalidating a comment.

## Decision 2 — the failure record is asymmetric, and that is the design

**Which of the three states it was could not be established.**
`LoopState.consecutive_failures` and `last_error` live in memory; the container
had restarted and took its logs with it. *A counter that dies with the process
cannot explain a process dying, and that is exactly when it is wanted.*

`loop_failures` (schema v22) is written through a new `on_failure` hook on
`run_forever` — injected, not imported, so `scheduler.py` keeps its "testable
without a database" property.

**It records failures only, never successes.** This is the whole point:

    rows inside a silence   the loop was failing and retrying
    no rows in a silence    nothing came back to raise — wedged, or gone

A wedged pass never returns, so it *cannot* write here. Logging successes too
would restore the ambiguity, because "no rows" would stop meaning anything.
Liveness already has its own record in `meta.recorder_last_write_ms`.

A raising hook is swallowed and logged, like `sleep_until`'s `wake_when`
predicate: it runs where something has already gone wrong, and trading a
recording loop for a bookkeeping error is the wrong direction.

`scripts/inspect_live_db.py pass-gaps` joins the two — holes computed in SQLite,
failures printed beside them. Diagnosing this by hand meant pulling 400 rows and
diffing them locally, which is the smuggle-the-code-in-with-the-question drift
that file exists to replace.

**Explicitly not decided:** nothing times out a pass. `run_forever` still awaits
`do_pass()` bare. A timeout that cancels mid-write is a real cost to buy against
a fault now *legible*. Revisit when `loop_failures` shows a gap with no rows.

## Decision 3 — parlay cards push outbound only

Joe was asked directly and chose **push-only, no order path**. Recorded so it is
not re-proposed: **Kalshi buys from Discord are ruled out**, and this is
independent of the interlock (`ORDERS_ARE_DRY_RUNS`, ADR 0018) rather than
blocked by it.

`DiscordNotifier.parlay_card` renders a card from the exact `_serialise_card`
payload the screen uses. **No arithmetic anywhere in the path** — every money
string arrives pre-rendered (`parlays.py:288-290`), so the embed cannot drift
from `/parlays` by a rounding step, which it would within a week if it formatted
its own floats.

The four `parlays.NOTES` caveats travel **verbatim**. Two of them are the
difference between a number and money: the cost is fair value and not a quote,
and combos are enter-only.

**No edge, no ranking, no button.** ADR 0038 closed the hunt; ADR 0071 §2.5
forbids ranking by the consensus-vs-Kalshi gap because `beta = -0.141` puts the
least trustworthy rows on top; `discord.py`'s module docstring already ruled out
tap-to-buy in a chat client. Cards go out in ladder order, which is a shape
(2–3 legs, 4, 6), not a judgement. The embed is coloured `--accent-2`, not the
palette's `COLOUR_OPPORTUNITY` green — green is "we found something", which this
is not.

### The dedupe key is the change detection

`notifications.UNIQUE (kind, key)` with key = `card_key` + **sorted** leg
tickers. No timestamp comparison, no threshold to tune, and it survives a
restart. That key is already the canonical card identity — it is what
`price_card_on_kalshi` compares for its drift check and what
`parlay_lookups.selected_legs` stores; any other definition would be a second
answer to "is this the same card".

Sorted because leg *order* is not part of a card: `build_ladder` orders by
`-p_conservative`, so two probabilities crossing would otherwise re-push an
identical parlay.

## Decision 4 — dedupe is not a rate limit, so the day gets a ceiling

**Found during the build, not in the plan.** `ladder_candidates` takes pre-game
fixtures only, so **every kickoff drops a game out of the pool**. If that game
was in a card, the leg set genuinely changes, the key genuinely changes, and the
push is *correct* by the dedupe rule. On a 14-fixture MLB night that is up to
fourteen correct notifications per rung.

**A dedupe key bounds repetition and never volume.** It answers "have I said this
before?" and is silent on how fast the world hands you something new to say —
and the turnover rate is a property of the upstream data, one file away.

`MAX_PARLAY_PUSHES_PER_DAY = 6` — two full ladders. Past it the day's pushes stop
and the screen still has everything; a desk that keeps buzzing manufactures
action, which ADR 0071 says this tool does not do. **Undelivered pushes do not
burn the ceiling**, so one Discord outage cannot silence the rest of the day.

## Decision 5 — the ladder is gated on sweeps, not on passes

The first commit rebuilt the ladder every pass, argued free because it is pure,
does no I/O and spends no credit. All true; the conclusion did not follow.
`build_ladder` runs a **200,000-sample Monte-Carlo copula per card, five times
over** — the headline plus one per devig method — **~400ms measured** for three
cards, on a loop whose quote pass is budgeted 8s (`QUOTE_PASS_DURATION_BUDGET_S`)
so a Kalshi quote can stay under 30s, and which already runs ~4.2s on live.

**"Pure" is a claim about effects, not about cost** — and the properties that
make something safe to call anywhere are the ones that stop anyone asking what
it costs. It would also have degraded *silently*: `Tempo.observe_pass_duration`
warns on an overrun rather than failing, so no test would have gone red.

Gated on `counts.odds_sweeps > 0 or kind == "full"`. A sweep is the only thing
that changes a fair value; the full pass bounds the wait when the pool changes
for the other reason. Between sweeps the ladder rebuilds byte-identically, so
the 400ms was buying a notification the dedupe then discarded.

## Not decided here

**The slash command**, which Joe also asked for. It is **not an extension of the
above — it is a new subsystem**, and wants its own ADR: a public HTTPS endpoint
(uvicorn binds loopback and is never published), Ed25519 verification of
`X-Signature-Ed25519` plus a crypto dependency, a Discord *application* rather
than a webhook (undoing the four-taps-on-a-phone property `discord.py:50-55` was
built around), and a new auth lane at `middleware.ts`, which today accepts only
the `cockpit_session` cookie. Note `requirements.txt:30` pins `discord.py~=2.4`
and **nothing imports it** — a dead dependency, not a latent bot.

## Consequences

- One more `notifications.kind`. No migration; `kind` is free text.
- Schema v22 for `loop_failures`. No migration step — a pure new table is
  created by `executescript`'s `CREATE TABLE IF NOT EXISTS` on an existing
  volume as well as a fresh one. Verified against a v21 database before deploy.
- `_post` still has **no 429 handling** (`discord.py:146-170`); a rate-limited
  post is absorbed as `delivered = 0`. Volume is ~8/day plus at most 6, nowhere
  near a bucket. Named so a future higher-volume trigger does not discover it by
  losing alerts.

## Verification

4,388 passed / 10 xfailed (baseline 4,333 re-measured at session start), ruff
clean. **Eleven mutations observed red** across the new guards.

The embed was rendered from the **real live `/api/parlays` payload**, not a
fixture — three built cards, WNBA and MLB legs. After deploy, **three pushes
landed at 22:41:43Z with `undelivered_last_24h` at 0**, so Discord accepts the
embed on the wire.

**One guard was written, mutated, observed GREEN and deleted** — a
`not_built_reason` check in `Alerter.parlay_cards` changed no answer, because an
unbuilt card serialises with no legs and `parlay_key` already returns `None`.
**One test was vacuous when first written** and is fixed with a vacuity guard
beside it.

## What this does not establish

- **That any card is worth buying.** No edge is claimed on this path and none
  was measured. `backend/core/ladder.py`'s docstring remains the authority.
- **Which state the 20:41Z gap was.** It is unrecoverable; the instrument exists
  so the *next* one is not.
- **That a wedged pass is survivable.** Only that it is now legible.
