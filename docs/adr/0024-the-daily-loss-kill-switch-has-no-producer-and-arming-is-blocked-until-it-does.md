# 0024 — The daily-loss kill switch has no producer, and arming is blocked until it does

**Date:** 2026-08-11
**Status:** Accepted. This ADR **makes** a decision: it adds a precondition to
arming and names two money-path defects as blockers.
**Owns:** the disposition of the four money-path findings below, and the arming
precondition that follows from the first two.
**Defers entirely** to **ADR 0018** on arming being a code change — this ADR
*adds a condition to* ADR 0018, it does not relax or replace it.
`LIVE_TRADING_ENABLED` and `ORDERS_ARE_DRY_RUNS` are untouched.
**Does not touch** ADR 0023 (A-versus-F), ADR 0017 (the maker path), or any
threshold value in any config file.

---

## 1. The decision

> **Arming real trading gains a precondition: the risk path must consume
> realised profit and loss, and a caller-level test must prove that it does.**
>
> Until that lands, `MAX_DAILY_LOSS_DOLLARS` is **not** a control, and no
> document, handoff or screen may describe it as one. The same applies to
> `MAX_POSITION_DOLLARS`, which is separately inert (§4).

**No threshold changes.** This is a wiring defect, not a calibration question.
Retuning a number that nothing reads would be the archetype of this repo's
"reaching a target by changing what is counted".

---

## 2. The evidence — execution, not inspection

This finding began as a grep-based census claim. **It did not enter the record
on the grep.** An audit lane drove the **real `POST /api/orders` route** end to
end via `httpx.ASGITransport`, at the verbatim `fly.live.toml` risk profile
(bankroll 100 / kelly 0.25 / position 10 / exposure 40 / daily-loss 10), against
a database seeded with **40 settled positions totalling minus $20,000 realised
loss**:

```
seeded realised PnL: -20,000.00 dollars across 40 settled positions
POST /api/orders -> HTTP 200
  contracts SENT: 2   limit 500   status dry_run
  size_position calls captured during the order: 1
    daily_pnl_dollars           = ABSENT, not supplied
    risk.max_daily_loss_dollars = 10.0
    -> guard test: 0.0 <= -10.0 is False
```

**The order was accepted with twenty thousand dollars of realised losses in the
database.**

**Mode-independence was tested, not assumed.** The obvious way for this claim to
be overstated is if the guard were dead only in dry-run. It is not:

```
ORDERS_ARE_DRY_RUNS=True   HTTP 200  kwargs=[ask_tenths, current_exposure_dollars, fair_probability, risk, side]
ORDERS_ARE_DRY_RUNS=False  HTTP 200  kwargs=[ask_tenths, current_exposure_dollars, fair_probability, risk, side]
IDENTICAL CALL SHAPE IN BOTH MODES: True
```

**The instrument was verified non-vacuous** — a whole-suite sweep of 1,285
sizer calls originating in `backend/` found exactly **one** with a non-zero
`daily_pnl_dollars`, and it came from `tests/test_engine.py:154`. So "zero from
production" is a measured negative, not a broken probe.

**The guard logic is correct and is not the defect.** Supplied directly it fires
exactly at the boundary: `-9.99` gives 8 contracts, `-10.00` refuses, `-20,000`
refuses. **Never write "the daily-loss guard is broken" bare.** The comparison
is right; nothing calls it with a real number.

**Positional smuggling excluded:** `size_position` is keyword-only
(`TypeError: takes 0 positional arguments`), so a name-based census cannot have
missed a positional pass.

---

## 3. The root cause is a rule this repo already wrote down

`CLAUDE.md`: **"Unreadable resolves to `None`, never `0`. Callers refuse rather
than substitute."**

`backend/core/sizing.py:125` declares `daily_pnl_dollars: float = 0.0`.

On a **loss limit**, a default of `0.0` means *"no information"* is silently
read as *"no losses"* — the maximally permissive value. The defect is not that
someone forgot an argument; it is that the signature made forgetting it
**safe-looking and silent**. Any fix that only supplies the argument leaves the
class open.

**One refinement, and it makes the fix cheaper.** The census said the parameter
has "no producer". That is wrong in a useful direction:
`backend/settlement.py:294` `settle_position` **does** write
`settlements.pnl_cents`. It is read only by `backend/analysis/clv.py:296` and
`backend/analysis/validate.py`, for reporting, and there is no `SUM` of it
anywhere. **The accurate statement is that a producer exists and no reader
connects it to the risk path. The fix is a query, not new instrumentation.**

---

## 4. The second defect — `max_position_dollars` is inert and dominated

`sizing.py:176` uses `risk.max_position_dollars - current_position_dollars`, and
`current_position_dollars` (`:124`, default `0.0`) is supplied by no production
caller either. Measured by repeated real orders on **one ticker** at the live
profile:

```
attempt  1: 2 @ 500t | cumulative 2 contracts = $1.00
attempt 20: 2 @ 500t | cumulative 40 contracts = $20.00 | exposure_before $19.76
attempt 35: 2 @ 500t | cumulative 70 contracts = $35.00 | exposure_before $35.36
attempt 39: HTTP 422 -- 0 contracts (max_exposure_dollars)

TOTAL on the single market: 76 contracts ~ $38.00
MAX_POSITION_DOLLARS = $10.00  ->  per-market cap exceeded: True
```

**Two corrections to the census, both against its own drama, and they are
recorded because the flattering-to-the-finding direction is the one to
distrust:**

1. The census said *"two orders on one market each receive the full $10."*
   **That is not what happens.** At the deployed $100 bankroll, **Kelly binds
   first** — `binding_constraint=kelly`, about $1.04 per order.
   `max_position_dollars` has **never been the binding constraint at the live
   profile**; it would bind at a $10,000 bankroll, at $9.88. The cap is not
   merely miscounted, it is currently **inert**.
2. The census **understated** the ceiling. It is not "$10 twice" — it is **$38
   on a single market against a $10 per-market cap**, bounded only by
   `max_exposure_dollars` at 4x the intended concentration. Exposure itself
   accumulates correctly ($0.00 to $35.36), so `max_position_dollars`
   contributes **nothing**.

The honest one-line statement: **one cap is inert and another is doing all the
work at 4x the intended per-market concentration.**

---

## 5. Two further findings, recorded WITH their limits so they are not upgraded

### 5.1 The order path is looser than suppression on depth — REACHABLE ONLY

`evaluate_suppression` is never called in the order route; the route re-applies
exactly **one** suppression threshold at order time, `edge_ceiling_tenths`
(`routes.py:1499`). The depth floor `min_depth_contracts = 10.0`
(`suppression.py:92`) is not among them.

```
depth= 5  size=3 : evaluate_suppression suppressed=True (insufficient_depth) | POST /api/orders HTTP 200, 2 sent
depth= 1  size=1 : suppressed=True (insufficient_depth)                      | HTTP 200, 1 sent
```

**And the gap is larger than "10 versus contracts".** `engine.py:192` checks
depth against `max(sizing_contracts, reference.contracts)`, and the reference
profile sizes far larger than the live one — at `fair = 0.58` the engine demands
**50** contracts of resting size and the order endpoint demands **6**.

> **REACHABLE ONLY. This is not an incident.** `orders` is empty; nothing has
> ever been transacted. The audit *forced* the thinned-book state directly and
> said so. Writing this up as a live bug is the failure mode `tasks/lessons.md`
> names.

### 5.2 The quantity plausibility bound — REACHABLE ONLY, and the obvious fix is near-worthless

`MAX_PLAUSIBLE_QUANTITY = 100_000_000` guards `orderbook.py:151,304` (WebSocket)
and is absent from `discovery.py:634-635` and from the `LiveQuote.depth_at_ask`
the order route reads. Confirmed by execution: a book claiming `1e18` resting
passes, `HTTP 200`.

> **Do not close this with a one-line copy of the constant.** Measured, on the
> units error the bound exists to catch (about 100x):
>
> ```
> real depth        10 -> misread     1,000  caught=False
> real depth       500 -> misread    50,000  caught=False
> real depth     5,000 -> misread   500,000  caught=False
> real depth 1,174,194 -> misread 117,419,400  caught=True
> ```
>
> The bound catches only absurdities already in the hundreds of millions. **The
> honest statement is that there is no plausibility bound on order-time depth on
> *either* path — the WebSocket bound is not a standard the REST path is falling
> short of.** Porting it buys a line of code and roughly no protection, while
> creating the belief that fillability is now defended.

---

## 6. The meta-finding, and it is the most valuable thing here

`tests/test_ev_sizing.py:179 test_the_daily_loss_kill_switch_refuses` is
**GREEN**, and it supplies `daily_pnl_dollars = -100.0` **itself**.

It could never go red. The production question — *does anything supply this?* —
is not the question it asks. The guard is correct, the test is correct, and
together they certify **nothing** about the deployed system.

> **A test that constructs the parameter it is checking cannot detect that no
> caller constructs it.**

This is the **fifth** guard-that-cannot-fail found across two sessions, and it
is a *different* species from the previous four: those were vacuous assertions,
this one is a sound assertion over an input that production never produces.

**The remedy is structural and the instrument already exists.** Commit
`1c13b8f` added `tests/test_has_callers.py` with a `MUST_HAVE_CALLERS` registry,
verified by mutation — removing every production caller turned it red, and its
own first mutation attempt was caught as vacuous and redone. **That idea is
extended to parameters**: a test that fails when no production call site
supplies `daily_pnl_dollars`, and likewise `current_position_dollars`. The
existing logic tests stay — the pair then covers both *"the logic is right"* and
*"something reaches the logic"*.

---

## 7. What this ADR does NOT do

- **It does not claim any money was lost or any bad order was placed.** `orders`
  is empty, `LIVE_TRADING_ENABLED` is false, `ORDERS_ARE_DRY_RUNS` is `True`,
  and the gate stands at **0 of 300** games. **Nothing can trade today.** This
  is a blocker for arming, not an incident.
- **It does not say the guard logic is wrong.** §2: it fires exactly at the
  boundary when supplied.
- **It does not change a threshold.** Every risk value in `backend/config.py`,
  `.env.example`, `fly.live.toml` and `fly.demo.toml` is unchanged.
- **It does not arm, disarm, deploy, or authorise a deploy.** ADR 0018 stands
  and now has one more condition.
- **It does not upgrade §5.1 or §5.2 to incidents**, and §5.2 explicitly warns
  against the one-line fix.
- **It establishes nothing about whether an edge exists at Kalshi.** ADR 0021
  §1's forbidden sentence is forbidden here.
- **It does not diagnose the odds outage.** ADR 0020 stays reserved and
  unwritten.

## What this does NOT establish

- **No claim about the LIVE database.** Every probe ran against
  `tempfile.mkdtemp()` databases built by `build_armed_db` from
  `tests/test_quote_refresh.py`. The verdict is about **code**, and §2's mode
  test shows no config value can change it — a config value cannot add a keyword
  argument to a call site. Fly secrets were not visible to the audit and are not
  relied on.
- **§4's "$38 on one market" is a measured ceiling under the deployed profile**,
  not a general bound. At a different bankroll the binding constraint changes;
  the audit showed Kelly binding at $1.04 per order today.
- **§5.1 and §5.2 are reachable in code and have never occurred.** No order has
  been transacted through this system.
- **Counted assumptions: 1.** That `build_armed_db` reproduces the deployed
  schema and risk config faithfully enough for the call-shape question. The
  keyword-only signature makes the specific claim — no caller supplies the
  argument — robust to that assumption, since it is decided at the call site.

---

## ANNOTATION 2026-08-11 — the precondition in §1 is SATISFIED. Landed at `e0efe06`.

**§1's arming precondition is met.** This annotation records how, and what was
*not* fixed, so a future session does not read a closed item as open or an open
one as closed.

### A1. The kill switch now fires through the real route

The §2 probe, re-run against the fix, is the acceptance test — and the *pre-fix*
state was re-created as a mutation to prove the test is not vacuous:

```
mutation M1 (routes.py back to hardcoded zeros -- the pre-fix state)
  E  assert 200 == 422
  FAILED TestTheDailyLossLimitReachesTheOrderPath::test_twenty_thousand_dollars_of_realised_loss_refuses_the_order
  FAILED ::test_a_loss_exactly_on_the_limit_refuses

after the fix
  422 -- refusing to size this order (max_daily_loss_dollars):
         daily loss limit reached (-20000.00 vs -10.00). Kill switch engaged.
```

The §4 per-market cap was dead on the same mutation
(`test_a_position_the_engine_never_saw_shrinks_the_order_to_nothing`, `assert
200 == 422`) and is now live.

### A2. Four production call sites, found by instrumentation rather than grep

`size_position` was patched to log its caller frame and the whole suite run:
**1,358 calls**, four distinct production sites, **zero** with a non-zero
`current_position_dollars` before the fix.

| site | wired with |
|---|---|
| `backend/engine.py:123` (offer) | pass-through from `build_recommendation` |
| `backend/engine.py:142` (reference) | explicit `0.0` — a clean book **by definition**, now stated rather than defaulted |
| `backend/api/routes.py` step 9 | `daily_realised_pnl_dollars` + `open_position_dollars`, read in the request |
| `backend/live.py` `price_against` | `_RiskState`, read once per subscription cycle |

Producers are `backend/runner.py` (once per pass, per-ticker inside the loop)
and `backend/api/routes.py`.

### A3. §3's class is closed, not just the instance

`size_position` **no longer defaults** `daily_pnl_dollars` or
`current_position_dollars`. `None` means *unknown* and the sizer **refuses**
with a named binding constraint. Mutation `M3c`, restoring the `= 0.0` defaults,
goes red with `DID NOT RAISE TypeError`. That is CLAUDE.md's *"unreadable
resolves to `None`, never `0`"* enforced by the signature rather than by
discipline.

### A4. The guard against the fake fix, and the guard on that guard

**The obvious wrong fix here is to pass `0.0` at all four call sites.** It would
satisfy a naive caller test and change nothing. Two mutations pin it:

- **M9** — all four callers hardcode `0.0` →
  `test_at_least_one_caller_supplies_a_value_it_actually_measured` **red**.
- **M8** — the call-site scanner is made to match nothing →
  `TestTheParameterScannerIsNotVacuous` **red**.

M8 exists because ADR 0022 records a caller detector that **enumerated nothing**
and passed. A caller test that cannot tell "nobody calls this" from "my scanner
is broken" is the fifth guard-that-cannot-fail wearing a new hat. **16 mutations
in total, every one confirmed red.**

### A5. The risk day rolls at 10:00Z, not UTC midnight — a decision, recorded

`settlement.risk_day_start_ms` delegates to `odds.timing.day_start_ms`.

UTC midnight is 8pm ET — **the middle of the US evening slate**. A loss limit
rolling there hands back a fresh allowance halfway through the session it exists
to stop, which is the maximally permissive failure. 10:00Z is 6am ET, after even
a West Coast extra-innings game has settled. It is also **one** definition of
"today" in the process rather than two, and `create_app` threads
`OddsConfig.budget_day_start_utc_hour` into both the order route and `QuoteHub`
so `.env` cannot split them.

### A6. What is still NOT fixed

- **§5.1 (order-path depth floor) and §5.2 (quantity plausibility) are
  untouched.** Both remain REACHABLE ONLY, and §5.2's warning against the
  one-line fix still stands.
- **Nothing is armed and nothing is deployed.** `LIVE_TRADING_ENABLED` is false,
  `ORDERS_ARE_DRY_RUNS` is `True`, the gate is at 0 of 300, and **`e0efe06` is
  not on the live instance.** The kill switch is live *in the repo*. Until the
  batched deploy runs, the deployed instance still carries the §2 behaviour.
- **No threshold changed.** Every risk value in `backend/config.py`,
  `.env.example`, `fly.live.toml` and `fly.demo.toml` is as it was.

### A7. One process note that belongs in the record

The lane wrote to three files outside its assigned set — `backend/runner.py`,
`backend/seed_demo.py` and `scripts/rescore_fee_models.py` — and **was right to**:
the brief named `backend/api/live.py`, which does not exist (the SSE path is
`backend/live.py`), and `runner.py` is `build_recommendation`'s only production
caller, so leaving it would have refused every candidate on every slate.

`scripts/rescore_fee_models.py` is a **frozen measurement harness** and the edit
was checked before acceptance: it adds explicit `0.0` where the default *was*
`0.0`, so it is behaviour-preserving and
`docs/measurements/2026-08-10-fee-model-rescore-result.md` is unaffected. **It
was also required** — once the sizer lost its defaults, the unedited script
would have raised. Verified by reading the diff, not by taking the report.
