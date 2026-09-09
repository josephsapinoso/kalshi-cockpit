# CLAUDE.md

Spine for this repo. Deliberately short — detail lives in `.claude/skills/`,
`docs/adr/` and `docs/measurements/`, loaded only when working in that area.
At session start read `tasks/NEXT.md` (current state, front door) then
`tasks/lessons.md` (patterns), in that order. Both fit in one read, and
`tests/test_session_files_are_readable.py` fails if either crosses the Read
tool's 262,144-byte ceiling. Add to the top; move the bottom **verbatim** into
`tasks/archive/{next,lessons}-YYYY-MM-DD.md` rather than shortening it.

The spine as it stood before the 2026-09-08 cut, with every correction trail,
is `docs/history/claude-md-2026-09-08.md` (ADR 0116). What follows is the
corrected fact and where it came from, not how it got corrected.

## What this is

A cockpit for betting sports on Kalshi. It compares Kalshi's prices against
devigged sportsbook consensus, surfaces where that consensus says Kalshi is
mispriced by more than the fee, and records everything so the edge can be
*measured* rather than assumed. It runs hosted on Fly.io, is used from a phone
and a desktop equally, and is a public portfolio repo.

**There is one signal, not two.** The in-house power-ratings model has never
run: `backend/model/elo.py` is imported only by `backend/model/backtest.py`,
which is imported only by `tests/test_model.py`. `model_probability` is `NULL`
on every row (`runner.py:1698` and `:2143` build `Candidate` without it;
`engine.py:58` defaults it to `None`) and nothing consumes it. A second signal
was documented as a *conjunction* — "where both agree" — and a conjunction can
only remove rows, so its absence explains nothing. Blending a model probability
into `fair_probability` would be a new decision needing its own ADR.

**Three quantities circulate as `actionable` and they are not the same
number.** Say which one you mean: (1) the gate predicate's **row** count
(`r.suppressed_reason IS NULL AND r.reference_contracts > 0`, `backend/gate.py:330`),
(2) the Gate screen's **game** count, which the 300-game floor is measured
against, (3) `slate.actionable_total`, a lifetime row count served to the
slate. Re-audited 2026-09-01: 51 rows across 15 games, two WNBA games carrying
41% of the rows, `suggested_contracts = 0` on all 51, every `reason_text`
ending "No edge." Treat 15 against a floor of 300 as *unseparated from zero*;
the predicate carries no multiplicity correction while the runner re-evaluates
~100 candidates every 900s. Quote the game count, never the row count.
Do not count actionable rows with `clv-coverage` — it filters on
`clv_scored_ms IS NOT NULL` and actionable rows are written before commence;
`/api/gate` has the right number. Still unrun: split the unsuppressed
population by `anchored_on_sharp` (a sharp anchor selects at most three books,
`backend/core/devig.py:289`) and report the `edge_tenths > 0` rate in each,
clustered per game. `docs/measurements/2026-09-01-actionable-population-reaudit.md`.

## The signal is measured and negative

`beta` — the CLV pass-through coefficient, the registered decision-bearing
statistic — has been computed twice:

```
2026-08-16  beta_hat -0.1412  se_cluster 0.0478  G = 199
            always-valid interval [-0.3342, +0.0517]
2026-08-25  beta_hat -0.0756  se_cluster 0.0246  G = 216   (modal config version only)
            always-valid interval [-0.1728, +0.0216]
VERDICT     UNRESOLVED
```

Every interval lies entirely below the registered NO-SIGNAL threshold of 0.40
and both arms (moneyline, prop) are negative. **The primary runs on the modal
`strategy_config_version` only** (registration §P4); a pooled `G = 311` fit
was refused as a declaring look on 2026-08-25 and `build_report` now applies
§P4 itself. **`G_eff` is a required field on every fit**: `G = 311` is 4.26
effective clusters, WNBA is 95.6% of the leverage, and 93.9% of it sits in
`too_few_books`/`no_market_width` rows whose `edge_tenths` runs to −718 — rows
rule 1 says are bugs, not edges.

**UNRESOLVED is the formal verdict and may not be reported as "no signal."**
The registered floor is **G = 713** (Amendment 2, 2026-08-29) and that look has
not been taken. **It is not coming**: at the measured concentration `G_eff = 713`
needs ~52,000 nominal games against a stopping rule that ends 2027-02-15. No
roadmap may depend on the look or wait for it. Reopening the question needs a
successor registration with an `edge_tenths` exclusion fixed in advance. **For
planning, treat the signal as settled negative.**

`docs/measurements/2026-08-16-clv-signal-test-interim-look.md`,
`2026-08-25-clv-signal-declaring-look-refused.md`.

**The gate stays exactly where it is.** It is the live-trading interlock, it is
never lowered or bypassed, and "the gate will open" is not a step in any plan —
its 300 counts *actionable* games and the record has 2 in its whole life, both
soft-book fallbacks.

## The hunt is closed — ADR 0038

Every quadrant this instance can reach has answered:

| quadrant | verdict | where |
|---|---|---|
| Consensus vs Kalshi's close | `beta = -0.141` | ADR 0021, 0034 |
| In-house model vs Kalshi's price | our error > the disagreement | ADR 0036, 0037 |
| `KXMVE` combos | **exit-only problem** — see below | ADR 0012 §5, E2/E3 |
| Speed / stale-quote pick-off | edge lives at ~400ms | predecessor |
| Cost headroom | a **discount, not a signal** | ADR 0027, 0028 |

**A cost advantage multiplies an edge, it cannot create one**, and no quadrant
supplied one to multiply. `backend/analysis/signal_test.py` is signal-agnostic
and would validate a new signal on the same clock, but no new hunting line is
open. A proposal to reopen must name which row it overturns, and with what
measurement. This bounds what the **tool** may claim; it reaches nothing Joe
does by hand.

**Combinations are enter-only.** `yes_dollars` is empty on 40 of 40 KXMVE books
this repo has read (three runs, two dates, pinned by
`tests/test_combo_book_depth_claims.py`); 33 of those 40 carried a resting NO
bid, and a resting NO bid *is* the ask you buy at. Zero resting YES bids over
36 levels: you can enter and may not be able to exit at size, which is why
combination orders are held to a tighter ceiling and why ADR 0078's hedge
exists. About a fifth of quoted combos have ever traded; the sample cannot
narrow that, and `backend/kalshi/combos.py`'s calendar caveat (no NBA/NFL in
the captures) is still open.

**The cost bars.** Kalshi's advantage is cost, not information: prices are
accurate to ~2c and sports is the most bot-contested corner of the venue.

    50.88%   true taker bar on baseball (nine fills pin k to (0.03497, 0.03501])
    51.75%   applied — TAKER_COEFFICIENT stays 0.070 because which attribute
             carries the split (sport, series, liquidity tier) is unresolved and
             every k = 0.035 observation sits inside four days
    50.44%   maker, at size
    52.38%   a sportsbook

Headroom against a sportsbook is **0.63 points, and that is an upper bound**:
both bars run through `settlement_fee()`, which asserts there is no settlement
charge (H4), and H4 is untested. ADR 0027, 0028.

## What the recorder costs

The LLM fleet is free — the runner imports `review_retired`
(`backend/agents/review.py:124`), which refuses every row. **The odds feed is
not.** It follows attention over an hourly floor (ADR 0071 §2.6): ten-minute
cadence while a page is open, hourly otherwise for a sport with a fixture
inside twelve hours, and the attended cadence is tiered by horizon
(ADR 0111 — ten minutes inside twelve hours, hourly beyond, never dropped).

    idle floor, 4 sports         ~384/day
    attention, capped            <=300/day   ODDS_ATTENTION_DAILY_CREDITS
    kickoff windows              UNCAPPED    clusters x 7 calls x 4 credits
    the only real ceiling         700/day    ODDS_DAILY_CREDIT_BUDGET

**The day is safe by the cap, not by construction.** The kickoff-window loop
(its only gate is `credits_left`, `backend/odds/timing.py:2381`) was 67% of
September's spend. When the 700 binds, `decide_sweeps` returns `fire=()` and
**every** sport stops until the next 10:00Z boundary. A full 60-minute window
is **seven** calls (28 credits a cluster); an NFL Sunday plans 3 clusters, the
season's worst 4 (`tests/test_sweep_timing.py` pins the seven).

The slice is a **ceiling, not an off switch**: past it a sport falls through to
the floor's hourly timetable, stamped `DESK`, and floor and slice are
separately capped and additive. Its worst case is a tab left open all day.
`trigger = 'attention'` in `api_credits` is a **lower bound** on attention
buying (a kickoff slot can satisfy the cadence first), and a counter that emits
on a cadence while a condition holds measures the condition's **duration**, not
its occurrences — attention buys measure dwell. Instruments:
`scripts/inspect_live_db.py credits-day`, `visit-freshness`, `sweep-log`.

**Do not read a stale slate as a broken recorder: check `sweep-log` for a
refusal before diagnosing anything.** And copy that names a condition to wait
for is falsified by fixing the condition, so the fix and the copy ship
together or the screen lies in the interval
(`test_no_screen_still_tells_him_that_closing_the_page_buys_more`).
`docs/measurements/2026-09-03-desk-dwell-and-the-watcher-off-switch.md`.

## What is armed and what is not

- **Engine path: dry.** `ORDERS_ARE_DRY_RUNS = True` (`backend/store/orders.py:129`).
  The gate guards `OrderPlacer` on this path and it has never placed an order.
- **Hand-bet path: armed, and used.** `MANUAL_ORDERS_ARE_DRY_RUNS = False`
  (`backend/store/manual_orders.py`) since 2026-08-26; `POST /api/manual-orders`
  sends real immediate-or-cancel orders at Joe's tap with his own typed
  estimate. First two real fills 2026-09-08 (KXMVE combos, shard 1, ADR 0113).
  The five brakes are gone (ADR 0112) and **no ceiling of ours bounds a hand
  bet**; what remains is the desk lockout, idempotency, the KXMVE
  acknowledgement, the price ceiling, depth at the ask, the netting guard, the
  shard collateral check (the venue's rule) and reserve-then-check. The buy
  button agrees with the route as of ADR 0114.
- **Bid path: disarmed.** `POST /api/parlays/bid` rests an offer; it was
  disarmed 2026-09-08 on Joe's word (ADR 0115) because he pays the ask and
  does not make offers. Route, table, watcher and cancel path stay and a dry
  run records the intent; re-arming is one line. **Do not remove it as dead
  code.**
- **`backend/gate.py` never reads `manual_orders`, `parlay_positions` or
  `parlay_position_legs`** (ADR 0063), so a hand bet cannot move the interlock
  and arming the hand path did not arm the engine. Do not cite ADR 0018 for
  this; it decides that arming is a code change, nothing about discretion.

## What it is for — ADR 0071

Settled with Joe 2026-08-24, in his own answers. Read the ADR before planning.

- **A personal betting desk first**, a portfolio repo second, a hunting
  instrument not at all. Joe bets by hand whether or not this exists; the desk
  informs and records bets that are happening anyway. It does not manufacture
  action and does not abstain on his behalf.
- **Its job at the moment of a bet is price transparency** — what Kalshi
  charges against what the sharp consensus says it is worth.
- **A per-row fact is transparency; an ordering is a claim.** The
  consensus-vs-Kalshi gap may be *shown* on a row and must never be *ranked
  by*: `beta = -0.141` means ranking by it puts the least trustworthy rows at
  the top.
- **Sharing means someone runs their own copy.** Kalshi's Developer Agreement
  §3.1 forbids sharing API-derived data with third parties, so a hosted
  instance friends can visit is non-compliant. Do not design for hypothetical
  operators beyond ADR 0071 §2.4.

Between 2026-08-25 and 2026-09-04, 0 of Joe's 27 Kalshi taker fills went
through the tool's armed order path, and his presence on the desk at the
moment of a bet measured UNRESOLVED — CONCENTRATION, which funds nothing and
kills nothing (`docs/measurements/2026-09-04-presence-at-the-moment-of-a-bet-result.md`).
The first two fills through the tool landed 2026-09-08.

**`/hedge` watches what Joe already holds — ADR 0078.** It records a parlay he
placed, reads its legs' live Kalshi prices while the game runs, and says what
hedging the endangered leg would do — the only exit an enter-only combo has.
No model, no tokens, no credits (asserted over the source of `core/hedge.py`,
`hedge.py`, `hedge_watch.py`); no `recommendations` row and no gate read. With
one leg live the lock is exact and is pushed to the phone; with several there
is no figure and the screen says so. Neither claims the price will get worse
if he waits.

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

The helpers that would automate the "re-run at a second horizon" and "the
parts agree" rules above — `clv.horizons_agree` and `validate.summarise` —
exist but are reached by nothing (ADR 0120's reachability walk: every
referrer is a test or `backend/model/backtest.py`, itself reached by
nothing). Mitigated, not fixed: the `beta` fits that settled the signal ran
through `analysis/clv_signal.py` and `analysis/signal_test.py`, which *are*
reached, and the signal is settled negative. The two rules above are still
the standard a human analysis is held to — they just have no running
enforcement today.

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
stays green, it's decoration — or the mutation missed the guard; run it against
the pre-fix code too. Never weaken an assertion to make a test pass.

## Security

This repo is public and the live instance holds real money.

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

0. **Invoke the `partner` agent at session start, before planning anything.**
   It owns what gets worked on, in what order, and by whom; this session
   executes and Joe oversees. Give it the state (what is open, what landed,
   what is blocked) and ask for a ranked list plus which items can run as
   parallel lanes. **Skip it only for a single-item errand Joe named
   himself.**
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
