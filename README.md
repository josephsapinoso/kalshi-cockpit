# Kalshi Sports Betting Cockpit

Prices Kalshi's sports markets against devigged sportsbook consensus, and
surfaces a bet only when the edge survives fees, freshness, depth, and a set of
deliberate suspicion checks.

**It is a measurement instrument first.** Most of the engineering below exists
to stop it telling me what I want to hear.

> **Status: not betting.** Order placement is locked behind a gate that opens
> only when the paper record earns it — 300 recommendations scored on
> closing-line value, a positive result that survives the noise guard, and a
> fee model reconciled against real fills. It may never open. That is a
> legitimate outcome and the tool is built to report it plainly.

---

## The premise, stated honestly

Kalshi's advantage over a sportsbook is **cost, not information**.

|  | Must win |
|---|---|
| Sportsbook at −110 | 52.38% |
| Kalshi at 50c, taker | 52.00% |
| Kalshi at 50c, maker | 50.44% |

A bet held to settlement pays **one** fee; trading pays two. That is the whole
edge the venue offers — roughly 0.6 percentage points as a taker.

Everything else is against you. Kalshi prices sports to about 2c. An
independent census found 13 automated market makers there, nearly all quoting
under 200ms, with zero presence in non-sports markets. The venue lowers the
bar. It does not clear it.

### The finding that shaped the design

The public methodology for this (OddsJam, Unabated) treats sharp-book consensus
as fair and flags the *soft* book offering a better number. Applied to Kalshi
that can invert — Kalshi's vig is lower than any sportsbook's, so when Kalshi
looks 3c cheap against devigged Pinnacle, the likelier explanation is that
Pinnacle is stale.

Worse, I measured the spread between devig *methods*:

| Line shape | Spread between the four methods |
|---|---|
| Even MLB moneyline (3.2% hold) | **0.18 points** |
| Lopsided (1.11 / 7.50) | **2.03 points** |

On longshots, method choice alone can manufacture an edge three times larger
than the real one. Three rules follow, and they run through the whole codebase:

1. **A large apparent edge is a bug until proven otherwise.** Big numbers are
   suppressed and investigated, never surfaced.
2. **Use the worst of four devig methods** for any money decision.
3. **Validate against Kalshi's own closing line.** The question is whether I
   beat *Kalshi*; only Kalshi's close answers it.

---

## Architecture

```
Kalshi WebSocket ─┐
Kalshi REST ──────┼─→ SQLite (OLTP) ─→ Parquet ─→ DuckDB + dbt ─→ marts
The Odds API ─────┘        │                                        │
                           │                                        │
                    Board (live)                          Dashboards (truth)
```

Two paths on purpose: one optimised for freshness, one for correctness, with
the boundary made explicit rather than smeared. The Board reads live SQLite;
every analytical claim comes from the marts, where the measurement guards run
as dbt tests.

```
backend/
  kalshi/     auth, rate-limited REST, WebSocket with sequence-gap detection
  odds/       The Odds API client + a credit budget that refuses, not warns
  core/       prices, fees, devig, ev, sizing, suppression
  match/      deterministic linker + per-league alias overrides
  analysis/   clv, validate  ← the evidence layer
  engine.py   ingest → match → devig → EV → size → suppress
frontend/     Next.js 16, design system shared with my personal site
```

---

## The parts I'd want reviewed

### The measurement harness refuses to report noise

`analysis/validate.py` ports three guards, each of which exists because an
earlier version of the same measurement was wrong **in a way that flattered the
result**. That directionality is not chance: a bug making things look worse
gets chased down immediately, so the survivors are the encouraging ones.

Given 2,000 observations of pure noise across 8 powered tests:

```
  bucket         n   implied   actual      gap      P&L      CLV
  30-40c       235     0.350    0.294  (noise)    +0.08    -0.27

  No bucket is distinguishable from noise. That is a result, and
  the correct one to report when it is true.
```

That 30–40c cell shows a **5.6-point gap** and still prints `(noise)`, because
the gap sits inside two standard errors computed *under the null*. Using the
observed rate instead would make an extreme result look more certain precisely
because it is extreme.

The pooling check partitions findings into supported / contradicted /
**unpowered** — the third category matters, because an earlier version marked
eight genuine buckets as artifacts purely for having small subgroups.
"Unresolved" and "refuted" are different claims.

Every report ends with what it does *not* establish.

### Suppression, and why rejects are kept

Nothing is dropped silently. A rejected candidate is stored with its reasons
and **still scored on closing-line value** — which makes 300 observations
reachable without 300 wagers, and makes each suppression rule auditable. If
rows rejected for `wide_market` turn out to have had good CLV, that rule is
costing money, and it is a query away.

One rule fell directly out of the measurement above: `edge_within_method_noise`
refuses any edge smaller than the disagreement between the four devig methods.
It tightens automatically on exactly the lines where the uncertainty is worst.

### Matching that refuses rather than guesses

A previous project's text matcher hit **0.56%** — and its hits were wrong,
pairing "who wins" against "over/under 3.5 goals" on the same fixture. A wrong
match doesn't error; it produces an *edge*, because you are comparing two
prices for different questions.

So team names resolve **within a single candidate fixture** rather than against
a global roster: `"New York G"` only has to be distinguishable from `"Dallas"`,
not from all 32 NFL teams. The match must be a bijection. A doubleheader
returns *"refusing rather than guessing which game this is"*.

### Failure modes designed against, not discovered

Each of these is a real incident from the predecessor project:

| Failure | Design response |
|---|---|
| Renamed API field emptied every order book, silently, for a year — while 305 synthetic tests passed | Wire-format tests load **captured** payloads; a missing levels field raises, naming what it looked for |
| Dropped WebSocket frames corrupted books permanently with no resync | Sequence-gap detection → book marked unquotable → automatic resubscribe |
| Ping/pong healthy while data silently stopped for 16 minutes | Application-level receive timeout. TCP liveness ≠ data flow |
| Clamping an out-of-range price turned a self-announcing API rejection into a live buy at 99c | Clamp what you trust; **refuse** what you're validating |
| Throttled markets recorded as illiquid ones | 429 handled with `Retry-After`; exhausted retries **raise** |

---

## Running it

No credentials needed. `seed_demo` generates a deterministic slate with no
network access and no execution path.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
python -m backend.main --seed-demo          # API on :8000
cd frontend && npm install && npm run dev   # cockpit on :3000
python -m pytest -q                         # 400 tests
```

The demo shows **2 surfaced, 4 suppressed, 3 no-edge** on a nine-fixture slate.
That shape is deliberate: a screen full of profitable opportunities would
misrepresent what this tool does.

---

## What this does not establish

- **Surviving the guards is necessary, not sufficient.** No edge has been
  demonstrated. The tool exists to find out.
- **CLV is not profit.** It is the fastest honest proxy, and it can be positive
  while an account shrinks.
- **The fee model is still hedged.** Kalshi's official schedule returns HTTP 429
  to automated fetches, and the secondary sources now disagree with each other
  — one says a 0.07 coefficient rounded up per order, another a ~0.06 sports
  multiplier rounded per contract. `calculate_fee` returns the **most
  expensive** candidate until real fills settle it.
- **The WebSocket wire format is unverified.** The parser fails loudly on a
  mismatch, which is correct but is not the same as tested.
- **NBA and NHL game markets are unconfirmed** — both out of season when the
  discovery sweep ran, and the sweep hit its page cap.

---

## Notes

Design system shared with [josephsapinoso.com](https://github.com/josephsapinoso/personal-website) —
same tokens, type scale, and component vocabulary, plus two semantic colours a
portfolio site doesn't need and a betting tool does.

Decisions are recorded in [`docs/adr/`](docs/adr/); things I got wrong are in
[`tasks/lessons.md`](tasks/lessons.md), written as patterns rather than
incidents.
