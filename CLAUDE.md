# CLAUDE.md

Spine for this repo. Deliberately short — detail lives in `.claude/skills/`,
loaded only when working in that area. At session start read, in this order:
`tasks/NEXT.md` (current state), `tasks/todo.md` (build log), then
`tasks/lessons.md`.

**All three are now small enough to read in full, and that is a guard, not a
promise.** As of 2026-08-17 `NEXT.md` and `lessons.md` were 456KB and 427KB —
both past the 262,144-byte ceiling at which the Read tool refuses a file
outright, so the instruction above had been impossible to obey and sessions
were silently reading only the head. The history was moved, **verbatim and
byte-for-byte**, into `tasks/archive/{next,lessons}-YYYY-MM-DD.md`; nothing was
summarised or deleted. `tasks/lessons.md` is now the newest lessons plus a
**pattern index** naming every lesson and its archive file — open the archive
file when a line sounds relevant. `tests/test_session_files_are_readable.py`
fails if either file crosses back over the limit. Add to the top; move the
bottom into the dated archive file rather than shortening it.

## What this is

A cockpit for betting sports on Kalshi. It compares Kalshi's prices against
devigged sportsbook consensus, surfaces opportunities where that consensus says
Kalshi is mispriced by more than the fee, and records everything so the edge can
be *measured* rather than assumed.

**There is one signal, not two.** Until 2026-08-10 this paragraph described a
second, in-house power-ratings model and said the tool surfaces where *both
agree*. That has never run. `backend/model/elo.py` is imported only by
`backend/model/backtest.py`, which is imported only by `tests/test_model.py` —
no production caller, on either instance. `model_probability` is `NULL` on every
row (`runner.py:684` does not pass it; `engine.py:58` defaults it to `None`),
and while `/api/ledger`'s `SELECT *` and one dbt staging view fetch the column,
both drop it: no suppression rule, sizing calculation, EV computation, gate
condition or API response consumes it. **Any claim that two signals must "agree"
describes a design, not the deployed system.**

The file:line citations are deliberate. This belief has now been wrong twice in
the same direction, and a future session can re-check a line number in thirty
seconds but cannot re-check an adjective.

**Do not read this as a reprieve, and the reason is arithmetic rather than
judgement.** As documented, the second signal was a *conjunction* — "where both
agree". A conjunction only ever removes rows from the surfaced set; it cannot
add one. Adding an AND-gate to a set that is already empty leaves it empty, so
the missing half **cannot** explain `actionable = 0` away. A different design
— blending a model probability into `fair_probability` to move the edge — could
shift rows either way, but that is a new decision, not the completion of an
existing one, and it would need its own ADR.

**`actionable` is no longer 0.** It genuinely was on 2026-08-10; it stopped
being 0 five days later. Re-audited **2026-08-23** on the gate's own predicate
(`r.suppressed_reason IS NULL AND r.reference_contracts > 0`, `gate.py:330`,
byte-identical in the instrument): **11 rows across 6 distinct games**, the
first written 2026-08-15T19:52:14Z, and **`suggested_contracts = 0` on every
one** — evidence at the fixed reference profile only (ADR 0015 §3), unbuyable
at the deployed bankroll and never rendered as a card. **The previous version
of this paragraph said 3 rows, all `anchored_on_sharp = 0`; that is no longer
the whole population — 4 of 11 are sharp-anchored**, three WNBA claims from
2026-08-20 devigged off Pinnacle, Betfair Exchange and Matchbook. So ADR
0021's soft-fallback reason no longer covers every row. **It has not been
refuted, and the re-audit did not take the measurement that would**: sharp
anchoring was **73.0%** of the pinned record (ADR 0021 §8, 1,141 of 1,564),
so 4 of 11 is *under*-representation rather than a new phenomenon, and a
sharp anchor selects **at most three books** (`devig.py:289`,
`selected = sharp or usable`) — a thinner fair value, not a better one. The
separating measurement is the one the 2026-08-16 audit named and nobody has
run: split the **unsuppressed** population by `anchored_on_sharp` and report
the `edge_tenths > 0` rate in each, clustered per game. **The verdict is
unchanged and rests on the two reasons that survive intact: 6 games against
the registered floor of 300, and the actionable predicate still carries no
multiplicity correction** while the runner re-evaluates ~100 candidates every
900s against a growing record. Treat 11 as *unseparated from zero*, not as a
result. No edit to the actionable predicate or to `devig.py` in the interval.
See `docs/measurements/2026-08-23-actionable-population-reaudit.md`.

Anything above or below claiming the count is 0 is **repetition of a
2026-08-10 measurement, not a measurement**. The intervening reads used
`clv-coverage`, which filters on `clv_scored_ms IS NOT NULL` while an
actionable row is written before commence — the class was outside the
denominator. `/api/gate` had the right number the whole time. See
`docs/measurements/2026-08-16-actionable-population-audit-result.md`.

What the 2026-08-10 correction changes is the *description*: the record must not
be written up as "the documented strategy produced zero actionable rows",
because that sentence credits a two-signal system that never existed. It is
**the
consensus-only strategy** that produced zero.

It runs hosted on Fly.io (not a laptop), is used from a phone, and is intended
to become a public portfolio repo.

## The consensus-only signal has been measured, and it is negative

**Read this before planning anything.** On 2026-08-16 `beta` — the CLV
pass-through coefficient, the project's registered decision-bearing statistic —
was computed for the first time:

```
beta_hat  -0.1412   se_cluster 0.0478   G = 199
always-valid interval  [-0.3342, +0.0517]
VERDICT   UNRESOLVED   (the registered floor is G = 300)
```

Both arms agree (moneyline −0.082, prop −0.519) and every interval computed lies
entirely below the registered NO-SIGNAL threshold of 0.40.
`docs/measurements/2026-08-16-clv-signal-test-interim-look.md`.

**UNRESOLVED is the formal verdict and may not be reported as "no signal."** The
registration forbids declaring below G = 300 and that look has not been taken.

**For planning, treat it as settled.** `beta` would have to rise **8.3 standard
errors** for the G = 300 outcome to be anything but NO SIGNAL. **Waiting for the
remaining ~101 clusters is not work.** The recorder keeps running because it
costs nothing and the look happens on its own; no roadmap may depend on it.

**The gate stays exactly where it is.** It is the live-trading interlock, it is
never lowered or bypassed, and "the gate will open" is not a step in any plan —
its 300 counts *actionable* games and the record has 2 in its whole life, both
soft-book fallbacks.

**~~What this frees.~~ That opinion was produced, and it is spent. The hunt is
closed — ADR 0038.** The paragraph here used to say "work that produces an
opinion is now the critical path". It was acted on: four registered measurements
in one day (ADR 0036, ADR 0037) built the opinion and refuted it, on the ground
that **our own model's error exceeds its disagreement with Kalshi**. Every
quadrant this instance can reach has now answered:

| quadrant | verdict | where |
|---|---|---|
| Consensus vs Kalshi's close | `beta = -0.141` | ADR 0021, 0034 |
| In-house model vs Kalshi's price | our error > the disagreement | ADR 0036, 0037 |
| `KXMVE` combos | **enter-only**: no YES bid on 40/40 books ever read, ≤18 units deep | ADR 0012 §5, E2/E3, 2026-08-18 |
| Speed / stale-quote pick-off | edge lives at ~400ms | predecessor |
| Cost headroom | a **discount, not a signal** | ADR 0027, 0028 |

**The combo row's reason was wrong, and the correction is recorded because the
conclusion is unchanged and that is exactly when a wrong reason survives.** This
row read *"zero volume, zero open interest"* until 2026-08-18. The script it
descends from (`scripts/analyse_combo_domination.py:71`) says these markets
"**mostly** carry zero volume and zero open interest"; the hedge was dropped
somewhere between the script and this file. And the hardened version was already
contradicted by this repo's own committed artifacts — non-zero `volume_fp` on
3 of 20 rows in `docs/measurements/2026-08-09-combo-e2-book-empty.json` and 3 of
9 in `-combo-e3-list-no-bid.json`, both produced by
`scripts/measure_combo_book_presence.py` on 2026-08-09. Roughly a fifth of
quoted combination markets have traded, in every run taken, and no run has
enough independent rows to narrow that.

**Do not read this as an in-season effect.** A 2026-08-18 run returned 2 of 11
and was briefly written up as one; Fisher two-sided against the 2026-08-09 runs
gives **p = 1.0**, its 11 rows collapse to about two independent groups by
shared legs, and it was 78% tennis — while MLB and WNBA were *already* in
season on 2026-08-09. The only sports absent from the original 2026-08-06
capture were NBA and NFL, so **`backend/kalshi/combos.py`'s calendar caveat is
untouched** and remains open.

What replaces the reason is stronger than what it replaces: **`yes_dollars` is
empty on 40/40 combination books this repo has ever read**, across three runs
on two dates. The list ask is the complement of a resting NO bid, not a quoted
offer. You can enter and you cannot exit. That, plus a combo fee model ADR 0012
§5 records as unverified, is why the quadrant still supplies no edge — an
enter-only market ≤18 units deep has nothing to multiply.

That last row is why this is a closure and not a pause: **a cost advantage
multiplies an edge, it cannot create one**, and no quadrant supplied one to
multiply. `backend/analysis/signal_test.py` remains signal-agnostic and would
validate a new signal on the same clock — but **no new hunting line is opened
here.** A proposal to reopen must name which row above it overturns, and with
what measurement. The recorder keeps running because it costs nothing.

**The premise, stated honestly:** Kalshi's advantage is cost, not information.
Prices are accurate to ~2c and sports is the most bot-contested corner of the
venue. The venue lowers the break-even bar from 52.38% to **51.75%** (taker)
or 50.44% (maker, at size). It does not clear that bar.

**This number has now moved twice, and the history is load-bearing.** It was
51.75%, corrected to 52.00% on 2026-08-10, and put back to 51.75% on 2026-08-14.
The correction was not wrong: `calculate_fee` genuinely charged the conservative
maximum across candidate models, so the applied bar genuinely was higher. **That
maximum has since been measured and the model it hedged against is refuted** —
Model B matches 0 of 11 real taker fills. Retiring it returns the applied bar to
what the published coefficient gives. Headroom is **0.63 points**, not 0.38.
See `docs/adr/0028-the-fee-hedge-is-retired-and-the-grid-is-deci-cent.md`.

**The bar the code applies still overstates the measured one, deliberately.**
Nine baseball fills pin `k` to `(0.03497, 0.03501]` — half the coefficient the
code charges — which would put the bar at **50.88%**. `TAKER_COEFFICIENT` stays
at 0.070 because *which* attribute carries that split is unresolved (sport,
series, and a per-market liquidity tier all fit identically) and every
observation of `k = 0.035` lies inside **four days**, on a venue whose schedule
demonstrably changed within the preceding six months. So: **50.88% true on
baseball, 51.75% applied, 52.38% at a sportsbook.**

**And 0.63 is an upper bound, not a point figure.** Both bars are computed
through `settlement_fee()`, a rename of `calculate_fee` asserting *"Settlement
is not a trade, so there is exactly one fee"*. That is H4, and **H4 is still
untested**. Settlement `fee_cost` matching the summed fill fees on 4 positions
is consistent with there being no settlement charge *and* with the field being
entry-only — separating them needs the account balance. A sportsbook's 52.38%
has no settlement fee to omit and Kalshi may, so the omission subtracts from the
0.63 and nothing subtracts from the 52.38. The gap to the 50.88% bar is robust;
the headroom is not. See
`docs/adr/0027-the-cost-headroom-is-an-upper-bound-pending-h4.md`.

This tool existed to find out whether an edge is there — not to assume one. **It
found out. The answer was no, and the record of how is the product** (ADR 0038).
This is a statement about what the **tool** may claim, and it reaches nothing
Joe does by hand: the gate guards `OrderPlacer`, and `ORDERS_ARE_DRY_RUNS = True`
(`backend/store/orders.py:129`) means the tool has never placed an order at all.
**Do not cite ADR 0018 for this** — it decides that arming is a code change, not
anything about Joe's discretion; see ADR 0038's sourcing correction.

## The three rules everything else follows from

1. **A large apparent edge is a bug until proven otherwise.** Big numbers get
   suppressed and investigated, never surfaced. The devig-method spread alone
   (1–2 percentage points) exceeds the fee advantage being hunted.
2. **Use the worst of four devig methods** for any money decision, so no edge
   survives that is an artifact of method choice.
3. **Validate against Kalshi's own closing line.** The question is whether you
   beat *Kalshi*; only Kalshi's close answers it.

## Measurement rules

These are not style preferences. Every one of them exists because an earlier
measurement was wrong in a way that flattered the result.

- **Read `n` before the effect size.** Require ≥5 expected outcomes on each
  side before a normal approximation is allowed to speak. The biggest gaps come
  from the smallest cells.
- **A pooled number is not a finding until the parts agree.** Always print the
  per-group view and the largest contributor's share beside any aggregate.
- **Bucket by the price you would actually pay** — the derived ask, never the
  mid. One bucket in the previous project showed a +25.4 point edge *and lost
  money* because it was bucketed on the mid but transacted at the ask.
- **The convenient column is usually contaminated.** `last_price` on a settled
  market has already converged on the outcome. State when a price was observed
  relative to when the outcome became known, and re-run at a second horizon.
- **Count your tests.** 1,190 category cells produce dozens of "significant"
  results by chance.
- **Every harness states what it does not establish**, in its module docstring.

## Conventions

- **Money is integer tenths of a cent** (`core/prices.py`), never float
  dollars, everywhere in the risk path. ~25% of Kalshi markets tick in
  deci-cents; whole cents misprice them by up to half a cent against a 4c edge.
- **Unreadable resolves to `None`, never `0`.** Callers refuse rather than
  substitute. See `tasks/lessons.md`.
- **Clamp what you trust; refuse what you're validating.**
- **Config via `.env`**, never hardcoded. `.env.example` is the contract.
- **Async** for all I/O. One shared `httpx.AsyncClient`, not one per call.
- **Wire-format tests load captured payloads** from `tests/fixtures/`, never
  hand-constructed ones. **One exception, and it is deliberate: MLBAM
  (`statsapi.mlb.com`) payloads are never committed**, because this repo is
  public and their terms permit "only individual, non-commercial, non-bulk use."
  MLB tests use synthetic payloads with a shape assertion. See ADR 0035 — the
  inconsistency is the decision, not a bug to fix.

## Testing

```
.venv\Scripts\python.exe -m pytest -q
```

`asyncio_mode = auto`, so async tests need no marker. Shared fixtures are in
`conftest.py` at the repo root (not `tests/`) because `backend` is imported as
a package from the root. Group with `class Test<Behaviour>`, and name tests
after the claim they make (`test_maker_is_one_quarter_of_taker`).

**Every guard is verified by disabling it and watching the test fail.** If it
stays green, it's decoration. Never weaken an assertion to make a test pass.

## Security

This repo is intended to go public and the live instance holds real money.

- The Kalshi private key is a Fly secret. Never read, echo, log, or commit it.
  If it ever appears in a transcript, it is compromised — rotate it.
- `.env`, `*.pem`, `*.key` are gitignored from the first commit.
- Every mutating route requires auth. The order endpoint re-validates staleness
  and risk caps **server-side** — never trust that the UI disabled a button.
- Demo and live run as separate deploys from one image. A public URL must not
  be one config bug away from the order path.

## Do not read these

They will burn a context window and tell you nothing you need:

- `../kalshi_orderbook_monitor/orderbook_data/**` — ~400MB of JSONL recordings.
- `../kalshi_orderbook_monitor/static/app.js` — 100KB vanilla JS, superseded.
- `../kalshi_orderbook_monitor/auto_trader.py`, `trading_server.py` — 86KB and
  90KB. Skim structure only; the strategies in them were measured and failed.
- `.venv/`, `node_modules/`, `warehouse/target/`.

To reference the previous project, read `.claude/skills/kalshi-api/SKILL.md`
first — it carries what was learned without the bulk.

## Do not rebuild these

Measured and refuted in the previous project. Re-litigating them costs days.

| Idea | Result |
|---|---|
| Stale-quote detection / picking off | Edge lives at ~400ms; a 60–180s detector is far too slow |
| "The NO side is systematically cheap" | Refuted on 66,686 settled markets — every price bucket negative |
| Kalshi↔Polymarket arbitrage | Text matching gives 0.56% match rate, and the matches are *wrong* |
| Pitcher-K priced from public rate data | Parameter noise is 6.09–8.47 points against a 1.75-point fee bar. The **in-sample optimal blend** of prior-season and season-to-date rates — an upper bound no implementation can beat — is still 3.5× the whole advantage. ADR 0036 |
| **Any in-house prop model from public rate data** | On 255 settled `KXMLBHR 1+` markets, the model-vs-Kalshi disagreement has sd **3.72 points** while the model's own error is **4.04** — so Kalshi's error is not detectable at all, and every apparent edge is our own noise. **Ask this question first**: comparing to the *price* needs no settlements and would have short-circuited three earlier measurements. ADR 0037 |

## Do not repeat this inference

`/markets` is ~99.8% `KXMVE` with no volume. That is a fact about **discovery
hygiene** — never paginate `/markets` — and it does **not** mean Kalshi has no
combo product. `KXMVE` is Multi-Variate Event: 1,389 collections and 13,806
legs, same-game and cross-game. This project asserted the opposite for eleven
build steps. See `backend/kalshi/combos.py` and `tasks/lessons.md`.

## Workflow

1. **Plan first** for anything non-trivial (3+ steps or an architectural
   choice). If something goes sideways, stop and re-plan rather than pushing.
2. **Vertical slices, not horizontal layers.** Each step ends demoable and
   verifiable, so a session can end anywhere without leaving a half-built
   layer.
3. **Offload research to subagents** to keep the main context clean. One task
   per subagent.
4. **Verify before done.** Never mark a task complete without proving it works.
   Would a staff engineer approve this?
5. **Capture lessons.** After any correction, write the *pattern* to
   `tasks/lessons.md` — not the incident.
6. **Record decisions** in `docs/adr/` so no future session re-derives them.
