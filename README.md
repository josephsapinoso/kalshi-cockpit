# Kalshi Sports Betting Cockpit

Built to answer one question: **does Kalshi's lower fee structure leave an
exploitable edge in sports betting?**

**It answered. The answer is no.** Every line of attack this instance could
reach has been measured and closed
([ADR 0038](docs/adr/0038-the-edge-hunt-is-closed-and-the-record-is-the-product.md)).
The tool has never placed an order — `ORDERS_ARE_DRY_RUNS = True`
([`backend/store/orders.py:129`](backend/store/orders.py)).

**The record of how it answered is the deliverable**, not the cockpit.

---

## The verdict

| Where an edge could have been | Verdict | Record |
|---|---|---|
| Information vs sportsbook consensus | `beta = −0.141`, **negative** | [0021](docs/adr/0021-the-consensus-only-strategy-is-refuted.md), [0034](docs/adr/0034-the-a-versus-f-call-is-f-for-a-fortnight-against-the-annotation.md) |
| Information vs Kalshi's own prices | our model's error **exceeds** its disagreement with Kalshi | [0036](docs/adr/0036-pitcher-strikeouts-cannot-be-priced-from-public-rate-data.md), [0037](docs/adr/0037-the-in-house-prop-model-line-is-closed.md) |
| Venue structure (`KXMVE` combos) | zero volume, zero open interest | [0012 §5](docs/adr/0012-a-combo-price-is-read-not-created.md) |
| Speed (stale-quote pick-off) | edge lives at ~400ms; too fast to reach | predecessor project |
| Cost headroom | a **discount, not a signal** | [0027](docs/adr/0027-the-cost-headroom-is-an-upper-bound-pending-h4.md), [0028](docs/adr/0028-the-fee-hedge-is-retired-and-the-grid-is-deci-cent.md) |

That last row is why this is a closure and not a pause. **A cost advantage
multiplies an edge; it cannot create one** — and no quadrant supplied one to
multiply.

The headline statistic, computed 2026-08-16 — `beta` is realised closing-line
value per unit of claimed edge, so `beta = 0` means the edge number carries no
information:

```
beta_hat  -0.1412   se_cluster 0.0478   G = 199
always-valid interval  [-0.3342, +0.0517]
VERDICT   UNRESOLVED   (the registered floor is G = 300)
```

**UNRESOLVED is the formal verdict and is not reported here as "no signal"** —
the registration forbids declaring below `G = 300`, and that look has not been
taken. For planning it is settled: `beta` would have to rise **8.3 standard
errors** for the outcome to be anything else.

---

## Why you should believe it

The failure mode of a project like this is measuring until you get the answer
you wanted. Three things were built against that:

**Sixteen analyses were registered before their data was seen.**
[`docs/measurements/*preregistration*.md`](docs/measurements/) fixes the
question, population, statistic, decision rule, stopping rule, and *what result
would falsify the hypothesis* — committed before the query runs. **Two refuted a
prediction their own author had written down** in the same document
([ADR 0036](docs/adr/0036-pitcher-strikeouts-cannot-be-priced-from-public-rate-data.md),
[ADR 0037](docs/adr/0037-the-in-house-prop-model-line-is-closed.md)).

**The harness that killed the signal was built to validate it.**
[`signal_test.py`](backend/analysis/signal_test.py) is signal-agnostic — it
estimates `beta` for whatever the engine claims. It was written to prove the
consensus strategy worked, and it is what proved it doesn't.

**Thirty-eight decisions are recorded, including the reversals.**
[`docs/adr/`](docs/adr/) — the break-even bar moved twice, in both directions,
and the history is kept because the correction is load-bearing. Mistakes are
written up as transferable patterns in [`tasks/lessons.md`](tasks/lessons.md),
not as incidents.

---

## The premise, stated honestly

Kalshi's advantage over a sportsbook is **cost, not information**.

| | Must win |
|---|---|
| Sportsbook at −110 | 52.38% |
| Kalshi at 50c, taker — the bar this code applies | **51.75%** |
| Kalshi at 50c, taker — measured on baseball fills | 50.88% |
| Kalshi at 50c, maker, at size | 50.44% |

A bet held to settlement pays **one** fee; trading pays two. That is the whole
advantage — **0.63 points**, and an *upper bound* rather than a point estimate,
because it runs through `settlement_fee()`, whose one-fee assertion is
[still untested](docs/adr/0027-the-cost-headroom-is-an-upper-bound-pending-h4.md).
The applied bar deliberately overstates the measured one: nine baseball fills
pin the coefficient to half what the code charges, but *which* attribute carries
that split is unresolved, so the constant stays conservative.

Everything else is against you. Kalshi prices sports to about 2c, and a census
found **13 automated market makers** there, nearly all quoting under 200ms.

**The finding that shaped the design.** The public methodology (OddsJam,
Unabated) treats sharp-book consensus as fair and flags the *soft* book. Applied
to Kalshi that can invert — Kalshi's vig is lower than any sportsbook's, so when
Kalshi looks 3c cheap against devigged Pinnacle, the likelier explanation is
that **Pinnacle is stale**. Worse, the four devig methods agree to **0.18
points** on an even moneyline but spread **2.03 points** on a lopsided line — so
on longshots, method choice alone manufactures an edge three times larger than
the real one. Three rules follow, and run through the whole codebase:

1. **A large apparent edge is a bug until proven otherwise.** Big numbers are
   suppressed and investigated, never surfaced.
2. **Use the worst of four devig methods** for any money decision.
3. **Validate against Kalshi's own closing line.** The question is whether you
   beat *Kalshi*; only Kalshi's close answers it.

---

## Architecture

```
Kalshi WebSocket ─┐
Kalshi REST ──────┼─→ SQLite (OLTP) ─→ Parquet ─→ DuckDB + dbt ─→ marts
The Odds API ─────┘        │                                        │
                    Board (live)                          Dashboards (truth)
                           │
                    ticket → POST /api/orders → the gate → Kalshi
```

Two paths on purpose: one optimised for freshness, one for correctness, with the
boundary explicit rather than smeared. The Board reads live SQLite; every
analytical claim comes from the marts, where the measurement guards run as dbt
tests. Two processes in one image — API and recording loop — and either dying
takes the container down, because a half-dead container serving frozen prices
looks exactly like a quiet market.

`backend/kalshi/` REST + WebSocket with sequence-gap detection ·
`backend/odds/` client and a credit budget that refuses rather than warns ·
`backend/core/` prices, fees, devig, EV, sizing, suppression ·
`backend/match/` · `backend/analysis/` the evidence layer · `backend/gate.py` ·
`frontend/` Next.js 16.

---

## The parts worth reviewing

**The harness refuses to report noise.**
[`analysis/validate.py`](backend/analysis/validate.py) prints the literal string
`(noise)` instead of a number when a cell can't be distinguished from chance —
with the standard error computed **under the null**, not from the observed rate,
because the observed rate makes an extreme result look more certain precisely
*because* it is extreme. Findings partition into supported / contradicted /
**unpowered**; that third category exists because an earlier version marked
eight genuine buckets as artifacts purely for having small subgroups.
"Unresolved" and "refuted" are different claims. Every report ends with what it
does *not* establish.

**The gate counts games, not rows.** Five conditions stand between a ticket and
an order, in one implementation shared by the Gate screen, the recording loop
and the order endpoint. The loop writes a row per pass and every row for one
market scores against **one** closing line — so ten markets polled thirty times
once satisfied a floor written to mean 300 independent bets, shrinking the
standard error by √30 for evidence that never grew. The error is now
cluster-robust, clustered by game. And the threshold is **always-valid**,
because the gate is read continuously rather than once: on 1,200 pure-noise
sequences looked at 100 times each, the two-sigma rule fires on **13.7%**, the
Robbins mixture bound that replaced it on **0%**. It costs 3.66 standard errors
at the floor instead of 2, and the gate reports the multiplier it used. It
currently reads **2 of 300** — three actionable rows across two games in the
project's whole history, all soft-book fallbacks, which is
[unseparated from zero](docs/measurements/2026-08-16-actionable-population-audit-result.md).

**Failure modes designed against, not discovered.** Each is a real incident from
the predecessor project:

| Failure | Design response |
|---|---|
| Renamed API field emptied every order book, silently, for a year — while 305 synthetic tests passed | Wire-format tests load **captured** payloads; a missing levels field raises, naming what it looked for |
| The same bug reproduced here: hand-written tests described a format the exchange does not send | A 269-frame capture replayed through the parser: **0 of 257 book frames parsed.** Capture the payload *before* writing the parser |
| Dropped frames corrupted books permanently with no resync | Sequence-gap detection → book unquotable → automatic resubscribe |
| Ping/pong healthy while data silently stopped for 16 minutes | Application-level receive timeout. TCP liveness ≠ data flow |
| Clamping an out-of-range price turned an API rejection into a live buy at 99c | Clamp what you trust; **refuse** what you're validating |
| A text matcher hit 0.56% and its hits were *wrong* — "who wins" paired against "over/under 3.5 goals" | Names resolve **within one candidate fixture**, not a global roster; the match must be a bijection; a doubleheader refuses |

Rejected candidates are never dropped silently: each is stored with its reasons
and **still scored on closing-line value**, which makes 300 observations
reachable without 300 wagers and every suppression rule auditable.

---

## Running it

No credentials needed. `seed_demo` generates a deterministic slate with no
network access and no execution path.

**Live demo: [kalshi-cockpit-demo.fly.dev](https://kalshi-cockpit-demo.fly.dev)**
— synthetic data. Same image as the live instance, started with
`INSTANCE_MODE=demo`; the order route answers 403 by construction rather than by
configuration.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
python -m backend.main --seed-demo          # API on :8000
cd frontend && npm install && npm run dev   # cockpit on :3000
python -m pytest -q                         # 2,959 tests, 10 xfailed
```

Every guard is verified by disabling it and watching the test fail. If it stays
green, it's decoration.

---

## What this does not establish

- **The `G = 300` look has not been taken.** The formal verdict is UNRESOLVED.
  The recorder keeps running because it costs nothing; no conclusion above
  depends on it.
- **"No edge" is scoped to this instance's reach.** Five quadrants were closed;
  a sixth may exist. Reopening requires naming which row it overturns, and with
  what measurement.
- **CLV is not profit.** It is the fastest honest proxy, and it can be positive
  while an account shrinks.
- **The cost headroom is an upper bound**, pending an untested assertion about
  settlement fees that needs the account balance to settle.
- **NBA and NHL game markets are unconfirmed** — both out of season when the
  discovery sweep ran.

---

## Attribution

**The information used here was obtained free of charge from and is copyrighted
by [Retrosheet](https://www.retrosheet.org/).** Retrosheet supplies the
historical baseball statistics behind every derived baseball number here, used
to estimate the parameters in
[`backend/model/strikeouts.py`](backend/model/strikeouts.py); its terms permit
commercial use and ask only for this notice. See
[ADR 0035](docs/adr/0035-mlb-stat-data-is-split-across-two-sources-on-licence-grounds.md)
for the split. That model's line of inquiry is closed by ADR 0036; the module
remains as the record of how it was tested.

Kalshi and The Odds API supply prices, under their own separate terms. Design
system shared with
[josephsapinoso.com](https://github.com/josephsapinoso/personal-website).

Decisions in [`docs/adr/`](docs/adr/) · measurements and registrations in
[`docs/measurements/`](docs/measurements/) · things I got wrong in
[`tasks/lessons.md`](tasks/lessons.md), written as patterns rather than
incidents.
