# Kalshi Sports Betting Cockpit

Built to answer one question: **does Kalshi's lower fee structure leave an
exploitable edge in sports betting?**

**It answered. The answer is no.** Every line of attack this instance could
reach has been measured and closed
([ADR 0038](docs/adr/0038-the-edge-hunt-is-closed-and-the-record-is-the-product.md)).

**So it became something else: a personal betting desk**
([ADR 0071](docs/adr/0071-the-desk-serves-its-operator-and-a-copy-is-the-only-compliant-share.md)).
Its operator bets by hand whether or not the tool exists; the desk's job at the
moment of a bet is **price transparency** — what Kalshi charges against what the
sharp sportsbook consensus says the bet is worth — and a permanent record of
every bet placed through it. It does not manufacture action, and it does not
abstain on anyone's behalf. It runs hosted on Fly.io, from a phone and a desktop
equally, and it is a portfolio repo second.

What can touch money, and what cannot:

| Path | State | Record |
|---|---|---|
| The engine's own orders (`OrderPlacer`, behind the gate) | **dry** — has never placed an order. `ORDERS_ARE_DRY_RUNS = True`, [`backend/store/orders.py`](backend/store/orders.py) | — |
| Hand bets — immediate-or-cancel orders at the operator's tap | **armed and used** since 2026-09-08 | [0112](docs/adr/0112-the-caps-come-off-the-hand-bet-path.md), [0113](docs/adr/0113-the-desk-is-transacted-through-after-all.md) |
| Combinations — ask the market for a quote, take one | **armed** since 2026-09-17 | [0164](docs/adr/0164-a-combination-is-priced-by-asking-not-by-reading-its-book.md), [0165](docs/adr/0165-the-accept-path-is-armed-once-one-undocumented-field-was-measured.md) |
| Resting bids | **disarmed** — the operator pays the ask and does not make offers; re-arming is one line | [0115](docs/adr/0115-the-bid-path-is-disarmed-because-it-rests-offers.md) |

The gate never reads the hand-bet tables, so a hand bet cannot move the
interlock and arming the hand path did not arm the engine.

---

## The verdict

| Where an edge could have been | Verdict | Record |
|---|---|---|
| Information vs sportsbook consensus | `beta = −0.141`, **negative** | [0021](docs/adr/0021-the-consensus-only-strategy-is-refuted.md), [0034](docs/adr/0034-the-a-versus-f-call-is-f-for-a-fortnight-against-the-annotation.md) |
| Information vs Kalshi's own prices | our model's error **exceeds** its disagreement with Kalshi | [0036](docs/adr/0036-pitcher-strikeouts-cannot-be-priced-from-public-rate-data.md), [0037](docs/adr/0037-the-in-house-prop-model-line-is-closed.md) |
| Venue structure (`KXMVE` combos) | **reopened 2026-09-17** — a combination is priced by *asking* (RFQ), not by reading its book; see below | [0164](docs/adr/0164-a-combination-is-priced-by-asking-not-by-reading-its-book.md) |
| Speed (stale-quote pick-off) | edge lives at ~400ms; too fast to reach | predecessor project |
| Cost headroom | a **discount, not a signal** | [0027](docs/adr/0027-the-cost-headroom-is-an-upper-bound-pending-h4.md), [0028](docs/adr/0028-the-fee-hedge-is-retired-and-the-grid-is-deci-cent.md) |

**A cost advantage multiplies an edge; it cannot create one** — and no quadrant
supplied one to multiply.

`beta` is realised closing-line value per unit of claimed edge, so `beta = 0`
means the edge number carries no information. It has been computed twice:

```
2026-08-16  beta_hat -0.1412  se_cluster 0.0478  G = 199
            always-valid interval [-0.3342, +0.0517]
2026-08-25  beta_hat -0.0756  se_cluster 0.0246  G = 216   (modal config version only)
            always-valid interval [-0.1728, +0.0216]
VERDICT     UNRESOLVED
```

Every interval lies entirely below the registered no-signal threshold of 0.40,
and both arms (moneyline, prop) are negative. A pooled `G = 311` fit on
2026-08-25 was **refused** as a declaring look because it mixed strategy
versions the registration had fixed in advance
([record](docs/measurements/2026-08-25-clv-signal-declaring-look-refused.md)).

**UNRESOLVED is the formal verdict and is not reported here as "no signal."**
The registered floor is `G = 713` (raised from 300 on 2026-08-29 when measured
noise tripped the registration's own trigger), and that look has not been
taken. **It is not coming**: `G = 311` was only **4.26 effective clusters** —
one WNBA game carried 43.8% of the leverage — and at that concentration 713
effective games needs roughly 52,000 nominal ones before the stopping rule ends.
For planning, the signal is treated as settled negative. The effective count is
printed beside every `G` this repo produces; it is deliberately **not** a
threshold, because restating the floor in it after seeing that it is small
would be choosing an estimator from the answer.

### The combinations row, and why it reopened

Kalshi's combos (`KXMVE`, Multi-Variate Event) have an empty public book **by
design**: you request a quote, makers answer privately, you accept one, and the
trade prints afterwards. Every earlier combo measurement read a surface
combinations do not trade on. Measured 2026-09-17:

- One RFQ drew **three maker quotes in ~107ms** — best YES ask 59.3c against the
  card's own fair value of 57.8c
  ([record](docs/measurements/2026-09-17-a-combo-rfq-returns-a-real-takeable-price.md)).
- Sell-side RFQs on **3 of 3 held combinations** drew bids for the held side —
  16 of 44 quotes, every one at the full size asked
  ([record](docs/measurements/2026-09-17-combinations-can-be-exited.md)). Every
  best bid sat *below* cost basis: an exit existing is not an exit being good.
- Neither surface dominates — on two positions the public book beat the RFQ, on
  the third the RFQ was the only exit — so an exit check reads **both**.

Two venue facts, each of which cost a session: `accepted_side` names the
**maker's** side, so buying YES sends `"no"`, which was settled by one 0.4-cent
trade after the docs declined to say
([record](docs/measurements/2026-09-17-accepted-side-names-the-makers-side.md));
and a quote can go `accepted → confirmed → cancelled` with no fill, so **only
`executed` is a fill**.

---

## What the desk does

- **Slate and Board** — every Kalshi market it can match, beside devigged
  sportsbook consensus. The consensus-vs-Kalshi gap is **shown on a row and
  never ranked by**: with `beta` negative, sorting by it would put the least
  trustworthy rows at the top.
- **Hand orders** — immediate-or-cancel orders at the operator's tap, carrying
  their own typed estimate. Idempotency, a price ceiling, depth at the ask, a
  netting guard and the venue's shard collateral rule are checked server-side.
- **Ask the market / Take it** — fire a real RFQ on a combination, see the
  quotes (asking commits to nothing), accept one (that spends). **Nothing on
  this path retries, ever**: the venue has no idempotency key for an
  acceptance, so a lost response is recorded as UNKNOWN, not as a failure, and a
  second tap is a 409.
- **`/hedge`** watches parlays already held — reads each leg's live price while
  the game runs and says what hedging the endangered leg would do
  ([ADR 0078](docs/adr/0078-the-desk-watches-what-joe-holds-and-a-hedge-alert-says-only-what-it-measured.md)).
  The figure is an **estimate pinned in neither direction**: at least four error
  terms feed it, and they point both ways.
- **The scout desk** — LLM agents that brief a slate, now also convened
  unattended ([ADR 0180](docs/adr/0180-the-desk-is-sent-on-the-ladder-unattended.md)).
  They spend under a shared daily token budget whose ceilings are *brakes, not
  caps*: each is checked before the next call, so a day can overshoot by one call.
- **An odds feed that follows attention** — ten-minute cadence while a page is
  open, hourly otherwise, never dropped
  ([ADR 0111](docs/adr/0111-attention-tiers-the-cadence-rather-than-paying-a-live-game-rate-for-a-line-two-days-out.md)).
  A call buys ten named books for 3 credits
  ([ADR 0155](docs/adr/0155-named-books-replace-regions-and-halve-the-bill.md));
  a 700-credit daily cap is the only hard ceiling, and when it binds every sport
  stops until the next day's boundary.

Counts of bets placed and positions held are **deliberately not written here**:
they change every time the desk is used, so any number would be stale on sight
([ADR 0162](docs/adr/0162-the-spine-stops-carrying-decaying-counts.md)). They
are read from the live instance by `scripts/inspect_live_db.py`.

---

## Why you should believe it

The failure mode of a project like this is measuring until you get the answer
you wanted. Three things were built against that:

**Analyses are registered before their data is seen.**
[`docs/measurements/*preregistration*.md`](docs/measurements/) — 31 of them —
fix the question, population, statistic, decision rule, stopping rule, and
*what result would falsify the hypothesis*, committed before the query runs.
**Two refuted a prediction their own author had written down** in the same
document ([ADR 0036](docs/adr/0036-pitcher-strikeouts-cannot-be-priced-from-public-rate-data.md),
[ADR 0037](docs/adr/0037-the-in-house-prop-model-line-is-closed.md)).

**The harness that killed the signal was built to validate it.**
[`signal_test.py`](backend/analysis/signal_test.py) is signal-agnostic — it
estimates `beta` for whatever the engine claims. It was written to prove the
consensus strategy worked, and it is what proved it doesn't.

**184 decisions are recorded, including the reversals.**
[`docs/adr/`](docs/adr/) — the break-even bar moved twice, in both directions,
and the combinations verdict was overturned by its own later measurement. The
history is kept because the correction is load-bearing. Mistakes are written up
as transferable patterns in [`tasks/lessons.md`](tasks/lessons.md), not as
incidents.

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
                 Slate · Board · Parlays · Hedge          Dashboards (truth)
                           │
       hand order ─→ POST /api/manual-orders ─→ Kalshi         (armed)
       combo RFQ  ─→ POST /api/parlays/rfq[/accept] ─→ Kalshi  (armed)
       engine     ─→ POST /api/orders ─→ the gate ─→ Kalshi    (dry)
```

Two read paths on purpose: one optimised for freshness, one for correctness,
with the boundary explicit rather than smeared. The screens read live SQLite;
every analytical claim comes from the marts, where the measurement guards run as
dbt tests. Two processes in one image — API and recording loop — and either
dying takes the container down, because a half-dead container serving frozen
prices looks exactly like a quiet market. Demo and live run as separate deploys
from one image.

`backend/kalshi/` REST, WebSocket with sequence-gap detection, combos and RFQ ·
`backend/odds/` client, attention-driven sweep timing, and a credit budget that
refuses rather than warns · `backend/core/` prices, fees, devig, EV, sizing,
suppression, hedge arithmetic · `backend/agents/` the scout desk and its token
budget · `backend/match/` · `backend/analysis/` the evidence layer ·
`backend/gate.py` · `frontend/` Next.js 16, installable to a home screen.

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

**The gate counts games, not rows.** Five conditions stand between an engine
ticket and an order, in one implementation shared by the Gate screen, the
recording loop and the order endpoint. The loop writes a row per pass and every
row for one market scores against **one** closing line — so ten markets polled
thirty times once satisfied a floor written to mean 300 independent bets,
shrinking the standard error by √30 for evidence that never grew. The error is
now cluster-robust, clustered by game. And the threshold is **always-valid**,
because the gate is read continuously rather than once: on 1,200 pure-noise
sequences looked at 100 times each, the two-sigma rule fires on **13.7%**, the
Robbins mixture bound that replaced it on **0%**. As of the 2026-08 audits the
floor of 300 actionable games stood at **2**, both soft-book fallbacks, which is
[unseparated from zero](docs/measurements/2026-09-01-actionable-population-reaudit.md).
The gate is never lowered or bypassed, and it opening is not a step in any plan.

**The money path is built for a lost response.** An RFQ acceptance has no
idempotency key, so the intent row is written *before* the venue call, a second
tap is refused, a response that never arrives is recorded as UNKNOWN, and the
refusal screen is the only one in the app with no retry button. The position's
stake is resolved at read time to the venue's own reported fill where the link
is provable, and to the recorded figure *with a named reason* where it is not.

**Failure modes designed against, not discovered.** Each is a real incident from
the predecessor project:

| Failure | Design response |
|---|---|
| Renamed API field emptied every order book, silently, for a year — while 305 synthetic tests passed | Wire-format tests load **captured** payloads; a missing levels field raises, naming what it looked for |
| The same bug reproduced here: hand-written tests described a format the exchange does not send | A 269-frame capture replayed through the parser: **0 of 257 book frames parsed.** Capture the payload *before* writing the parser |
| Dropped frames corrupted books permanently with no resync | Sequence-gap detection → every book unquotable → automatic **reconnect** |
| Ping/pong healthy while data silently stopped for 16 minutes | Application-level receive timeout. TCP liveness ≠ data flow |
| Clamping an out-of-range price turned an API rejection into a live buy at 99c | Clamp what you trust; **refuse** what you're validating |
| A text matcher hit 0.56% and its hits were *wrong* — "who wins" paired against "over/under 3.5 goals" | Names resolve **within one candidate fixture**, not a global roster; the match must be a bijection; a doubleheader refuses |

Rejected candidates are never dropped silently: each is stored with its reasons
and **still scored on closing-line value**, which makes every suppression rule
auditable.

---

## Running it

Sharing this tool means running your own copy: Kalshi's Developer Agreement
forbids passing API-derived data to third parties, so a hosted instance for
friends would be non-compliant.

No credentials needed for the demo. `seed_demo` generates a deterministic slate
with no network access and no execution path.

**Live demo: [kalshi-cockpit-demo.fly.dev](https://kalshi-cockpit-demo.fly.dev)**
— synthetic data. Same image as the live instance, started with
`INSTANCE_MODE=demo`; the order routes answer 403 by construction rather than by
configuration.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
python -m backend.main --seed-demo          # API on :8000
cd frontend && npm install && npm run dev   # cockpit on :3000
python -m pytest -q                         # the suite; CI runs it with ruff on every push
```

Every guard is verified by disabling it and watching the test fail. If it stays
green, it's decoration.

---

## What this does not establish

- **The declaring look has not been taken and will not be.** The formal verdict
  on `beta` is UNRESOLVED; its floor of `G = 713` is out of reach at the
  measured concentration. The recorder keeps running; no conclusion above
  depends on it.
- **Nominal `G` may be the wrong unit and no floor written in it fixes that.**
  `G = 311` was 4.26 effective clusters.
- **"No edge" is scoped to this instance's reach.** The combinations row has
  already reopened once. Reopening another requires naming which row it
  overturns, and with what measurement.
- **Combinations can be exited, not profitably exited.** The sell-side result is
  n = 3 positions at one moment — not a rate — and no exit was accepted, so no
  exit fill is proven.
- **The hedge figure is not a bound.** Its error terms point both ways; calling
  it a floor, a ceiling or "conservative" would be the flattering error.
- **CLV is not profit.** It is the fastest honest proxy, and it can be positive
  while an account shrinks.
- **The cost headroom is an upper bound**, pending an untested assertion about
  settlement fees.

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
