# Next — your checklist

## 2026-08-09, 06:00–07:30Z — three items closed, and one of them was Joe's

`main` is pushed and CI-green. **1,361 tests**, ruff clean. Nothing was
deployed, no order was placed, no gate was touched, no odds credit was spent.

### 1. One log line per pass, not two

`pricing pass:` was a strict subset of `pass N ok`, emitted ~4ms earlier from a
different module, at whatever rate the caller happened to run — 900s when it was
written, ~22s once the odds budget went 16 → 400. Deleted.

The recorded reason it was "not simply removable" — that `run_chain.py` would go
silent — **was wrong**: `run_chain.py` has always printed `counts.as_dict()` as
indented JSON. What the inline line did carry, and nothing else did, is a pass
that recorded fine and then died in scoring, where `run_forever` logs a traceback
saying where it broke and nothing about what had already been written. That job
moved to `counts_survive_a_late_failure` in `run_loop.py`, on the failure path
where it earns its place.

The claim that made the deletion safe is now an assertion instead of prose in a
handoff file: every field of `PassCounts.as_dict()` must survive into
`CombinedPass.as_dict()` unrenamed.

### 2. Exposure counts the fee — ADR 0008's gap 3, closed with no migration

Three ADRs deferred this on the grounds that it "needs a fee column on
`orders`". **It needed no column.** `count` and `limit_price_tenths` were
already stored and are exactly what `calculate_fee` takes. The real obstacle was
that exposure was a SQL `SUM` and the fee is a maximum across candidate models
with a per-order rounding step — not expressible in SQL. So the obstacle was the
duplicate implementation, restated as a schema problem.

`store.orders.exposure_contribution` is now the only expression of what an open
order commits, called by both the ticket's projection and the cap. Those were
previously two paths pinned together by a test. They agreed, and both left the
fee out — which is the one defect a two-paths-agree test is blind to. Lesson
written.

Ten contracts at 50c now read $5.20, not $5.00.

### 3. The combo lookup no longer needs Joe — the price was always readable

**This was item 4 on his list and it is off it.** The authorised
`POST .../lookup` is *unspent* and no longer on the critical path.

Kalshi's users mint provisional combination markets by tapping legs in the app —
about **700 a minute** — and `GET /markets` returns them carrying
`mve_selected_legs`, `mve_collection_ticker` and a live quote. Nothing has to be
created. The reason nobody had noticed: 5,000 consecutive open markets span
**6 minutes 48 seconds** of `created_time`, `/markets` is newest-first, and a
quote decays within ~2 minutes — so paging depth-first is guaranteed to find
nothing, and three separate walks did exactly that. The sample has to be
accumulated over *time*, polling the newest page.

**The control ran, and it is the finding.** Cross-game legs are near-independent,
so their true rho is 0:

    cross-game, TWO-SIDED, n=12    rho at bid -0.135   mid -0.033   ask +0.137
    cross-game, ask only,  n=168   rho at ask +0.243   sd 0.235   max +0.853

At the mid the method **returns the right answer**, bracketed almost symmetrically
by bid and ask at ±0.14. The ask-only population is refused — not because its
bias is large but because it has sd 0.235 and so cannot be subtracted off.

**No same-game correlation has been measured yet**, and that is the honest state:
4 same-game combinations appeared in 26 minutes, 1 inverted, and it was ask-only.
What exists now is a validated method, a known harvest rate, and no reason to
spend a write. `docs/adr/0012`, and the raw run in `docs/measurements/`.

Also corrected: `active_quoters` is `[]` on **all 14,240** published legs while
those same leg markets are two-sided with 21,247 contracts of open interest. It
is not a liquidity signal, and "0 of 13,806 legs quoted" said nothing about
whether a combination could be priced.

### Still open, unchanged

- **The four fee-calibration trades.** Joe's, pre-authorised, not done. Still a
  gate condition and still the binding constraint on it.
- **`gate progress (24h)`** needs a full day on the new budget. Untouched here.
- **`discovery:` on a quote pass** — proven by test, not yet observed on live.
  Needs an open odds window (next ~15:45Z).

---

## DEPLOYED (2026-08-09, 05:36Z) — the budget stopped being the constraint

Key installed (machine v22, 05:33Z) and `f1fb326` deployed (v23). Gate locked,
five pages 307, `/api/orders` 401. The first full pass on the new budget, beside
the last one on the old:

    old (05:34)  sweep_decision: no sweep: 12 of 16 credits spent
                 events_linked 10   fair_prices_written 20   recommendations  4
    new (05:36)  odds_sweeps 1      odds_quotes_stored 626
                 events_linked 16   fair_prices_written 32   recommendations 24

**A sweep fired on the first pass and 626 quotes landed.** Linked games up 60%,
priced games up 60%, six times the recommendations. `alerts_sent: window_open`.

And the window now *stays* open, which it almost never did: quote passes are
running every ~22s continuously rather than for 15 minutes twice a day. That is
the whole point of the change.

`gate progress` moved in the right direction within two passes:

    05:34  actionable=0  no_edge=161  suppressed=262
    05:36  actionable=0  no_edge=177  suppressed=270  (+suspicious_edge=2)

`no_edge` +16 is fresh odds producing honest "no bet here" answers on games that
previously had nothing to price against. **`actionable` is still 0** — that is
the real question and it now has a growing sample instead of a starved one.

`suspicious_edge=2` is new and is *not* an opportunity: it is CLAUDE.md's first
rule firing, two edges large enough to be a bug until proven otherwise.

### Log volume — the `discovery:` line is fixed; one duplicate remains

**Correction to the figure in the previous section: ~12,000 lines a day was
wrong, and wrong in the alarming direction.** It assumed the window stays open
all day. It does not. A sweep opens it for `MAX_ODDS_AGE_S` (900s) and then it
shuts: measured on live, the 05:36Z sweep produced quote passes from 05:38:44 to
05:51:14 — about 12.5 minutes, ~34 passes — and the next slot was 15:45Z, nine
hours later. At 10–20 sweeps a day that is roughly **400–800 quote passes, so
1,200–2,400 lines**, not 12,000.

The fix is still worth having and the reasoning behind it is unchanged. The
*size* of the problem was overstated by roughly 5x, by extrapolating a window
that had been open for the twenty minutes I happened to be watching. Reading a
rate off a burst is the same error as reading a population off a log buffer,
which this file already records from earlier the same day.

A quote pass emitted three lines every ~22s while the window is open, against a
100-line `flyctl logs` buffer. That still eroded the readability won hours
earlier by collapsing the 962-line scope burst — during exactly the windows when
something interesting is happening.

**`discovery:` is fixed.** It prints on every full pass — the heartbeat, so
silence still cannot mean "discovery did not run" — and on a quote pass only
when its numbers change. Both halves are needed and each is verified by
disabling it: change-detection alone reintroduces the exact ambiguity the
unconditional print existed to prevent.

The general shape, which is the part worth carrying: **a logging rate is a
property of the caller, not of the code.** This line was correct at 900s and a
flood at 22s without one character of it changing. The trigger was the odds
budget going 16 → 400 four hours earlier — a change in a different subsystem
entirely.

**Verification status, stated exactly.** Proven by test — 61 identical quote
passes produce one line, and disabling either half turns a different test red.
**Not yet observed on live**, because the window closed minutes after the deploy
and quote passes only run while it is open. The next window is ~15:45Z; the
check is that `discovery:` appears once per *full* pass and not once per quote
pass. Do not record this as confirmed until that has been read.

**Still duplicated, and not fixed:** `pricing pass:` is a strict subset of
`pass N ok`, emitted ~4ms earlier by a different module (`runner.py` vs the
scheduler in `run_loop.py`). In the loop it carries nothing the later line does
not. It is not simply removable, because `run_chain.py` emits no `pass ok` line
and would go silent. Worth ~4,000 lines/day if resolved; left alone rather than
guessed at.

---

## Superseded (2026-08-09) — the 20K tier is bought; the key is not installed

Two steps, in order, and step 1 is Joe's:

1. `bash scripts/setup_odds_key.sh` — the key never passes through an agent.
2. `gh workflow run Deploy -f instance=live -f confirm_live=kalshi-cockpit`

`main` carries `ODDS_DAILY_CREDIT_BUDGET = 400` (was 16) and
`ODDS_MONTHLY_CREDIT_BUDGET = 13000`. **Not deployed**, though approved: the live
machine has not restarted since 04:37Z, so the wizard has not run, and 400/day
against the old 500/month key would burn the free tier's remainder for nothing.

**400, not 645.** Spend is capped by the scheduler, not the budget:
`MIN_SLOT_SEPARATION_MS` gives each sport ≤12 useful slots/day, so six leagues
cannot exceed ~432/day whatever the budget says. 400 puts the *fixture schedule*
in charge, which is the state the scheduler was written for and has never been
in. The gap to 20,000 is deliberate headroom for a backfill.

**A guard that was missing.** `BudgetState.spent_this_month` had been computed
since the module was written and checked by nothing. Fine while every call cost
6 credits; not fine once the historical endpoints (10× per call) exist, since a
backfill can spend the month between two daily resets. `can_afford` now checks
three ceilings — the provider's, ours-per-month, ours-per-day — and unset means
uncapped, never 0.

### Candlestick retention: ~80 days, measured

`scripts/measure_candlestick_retention.py`, free, unauthenticated. Bars at every
age to 79 days; at 80+ the market is **gone**, not delisted — constructed
tickers 404 while the same construction resolves both sides at 5d and 60d.
Addendum on `docs/adr/0011`.

- **Scoring: unaffected.** And it refutes the open worry that some of the 190
  unscoreable rows had aged out — every one is inside the window, so the
  ordering rule is the whole explanation.
- **Backtest: this is the horizon.** ~80 days ≈ 1,200 MLB games, above the 300
  the gate needs. Costing and the rule it must not break are below.

---

## The gate is blocked by the odds budget, and the guards are fine

Instrumented in `8c37e44` and **answered on the first pass** (live, 04:38Z):

    gate progress (24h): actionable=0 of 300 needed, no_edge=161, suppressed=265;
    suppressed by: stale_odds=256, too_few_books=73, no_market_width=73,
                   edge_within_method_noise=4

426 rows in 24h. The worry that sent me looking — that a miscalibrated rule was
refusing everything and pinning the gate's counter at zero — is **refuted**, and
what replaced it is more useful.

**`stale_odds` is 256 of 265 suppressed rows (~97%), and it is structural, not a
bug.** The odds budget is 16 credits/day at 6 a sweep, so ~2 sweeps, each opening
a 15-minute window. A full pass runs every 900s regardless, so ~94% of passes
write rows whose sportsbook consensus has already aged past `MAX_ODDS_AGE_S`.
Those rows *should* be refused. This is the composition already recorded in
`tasks/lessons.md` under two-limits-on-one-quantity — the tool is actionable
about 30 minutes a day — now visible as a row count instead of an argument.

**And the rows that did have fresh odds answered `no_edge` 161 times and
`actionable` 0 times.** That is the honest no-edge result, on the population
where the engine was actually able to speak. It is the premise of the whole
project holding, not a fault:

> Kalshi's advantage is cost, not information. This tool exists to find out
> whether an edge is there — not to assume one. (CLAUDE.md)

### What this means for the gate, stated plainly

The 300-game floor is not reachable by waiting. The binding constraint is odds
credits, and it is upstream of everything: no credits → no fresh consensus → no
actionable row → no CLV → no gate. Three options, and none is free:

1. **Pay for odds.** A larger Odds API tier buys more sweeps, more windows, more
   rows with fresh consensus. This is the only one that changes the arithmetic
   rather than the accounting.
2. **Spend the existing budget better.** Two sweeps a day is a *scheduling*
   choice. Concentrating them on the densest slate window, or sweeping one sport
   rather than all, trades coverage for freshness. Cheap to try, bounded upside.
3. **Accept it and let the record accumulate slowly.** At 0 actionable rows a
   day the floor is never reached, so this is only honest if (2) moves the number
   off zero first.

**Do not "fix" this by relaxing `MAX_ODDS_AGE_S`.** A stale consensus priced
against a live Kalshi ask is exactly how a fabricated edge enters the record,
and the record is the product.

### Two readings of this line that would be wrong

- **The reason counts do not partition.** A row carries a comma-joined list and
  `suppression_summary` counts each name, so 256+73+73+4 sums above the 265 rows.
  Read them as "how often each rule fired", never as shares of a whole.
- **`too_few_books=73` and `no_market_width=73` are one population, not two.**
  Identical counts because they co-occur by construction: one book cannot
  disagree with itself, so a single-book consensus has no measurable width.
  `tasks/lessons.md` records that sharp-book anchoring *causes* the single-book
  case. Counting them as two distinct problems would double the apparent size of
  a small one.

Caveat on scope: one day, one slate, in August — MLB and NFL preseason, with
NBA, NHL and NCAAF out of season. A denser winter slate is a different
measurement and this should be re-read then.


## READ FIRST (2026-08-09, later) — the log stream drops lines, and the number everyone quoted was a 10% sample

The one cheap check the previous handoff asked for is **done, and the answer is
zero.** The per-process scope dedupe holds in production. Evidence, because a
count off `flyctl logs` cannot settle it on its own:

    03:17:05  94 warnings, all one timestamp, all from pass 1 of a fresh process
    03:30:46  pass 2 -- zero new warnings; the 94 had aged to 91 in the buffer

The buffer rolls forward and no warning carries a second timestamp. The dedupe
was never broken; a count taken from a lossy buffer just cannot distinguish
"re-emitted" from "still sitting there". **The timestamp is the discriminator,
not the count.**

### What the check turned up instead, which is larger

`unknown_scopes=962` prints on the same line as those 94 warnings. Two counts of
one quantity, disagreeing tenfold, printed together and never read against each
other. Measured against the live exchange
(`scripts/measure_unknown_scopes.py`, free, no odds credits):

| | Recorded in this file | Actually |
|---|---|---|
| unknown (series, scope) pairs | 94 | **962** |
| distinct scopes | — | **317** |
| in leagues we price | "none of them a sport" | **227 pairs, 56 scopes** |

**The exclusion is still correct** — every excluded scope in a priceable league
is a future, an award, or a period/prop market (`Extra Innings`, `YRFI/NRFI`,
`First 5 Innings Winner`, WNBA `1st Half Winner`, `Win Totals`, `Draft`). No
game-level moneyline, spread or total is being dropped. But that was true by
luck rather than by the reasoning on record, and the reassuring sentence came
from a sample nobody knew was a sample.

### Fly drops log lines. Absence is not evidence of non-emission

962 lines in ~90ms into a 100-line buffer: ~90% dropped, **including the
neighbouring `discovery:` summary**, which is unconditional, was verified to
emit locally, and is proven to have run by its own return value appearing one
line later. It still was not in the stream.

So **the two boot lines were never merely "pushed out"** — they were competing
with a 962-line burst, and any conclusion drawn from a line *not* appearing in
`flyctl logs` is unfounded.

Fixed in `f7adbad`: one aggregated warning per process, naming the 56 priceable
scopes and counting the other 261. **The first pass now emits 2 lines where it
emitted 963.** The `no occurrence_datetime` warning four lines away had the
identical undeduplicated shape, latent, and is deduped per series.

### Watch item, and it qualifies the previous handoff: 59 was a batch, not a rate

Three passes on the record now, and the CLV counter did not keep moving:

    03:17  pass 1  full   scored 59  skipped 190  rows_joined 249
    03:30  pass 2  quote  (CLV runs on full passes only)
    03:44  pass 3  full   scored  0  skipped 190  rows_joined 190  lines_stored 44

`rows_joined` fell by exactly 59 — the scored rows dropping out of the join.
What is left is the 190 permanent residue ADR 0011 predicted. **The 59 was the
backlog being scored retroactively in one step, and the full pass since scored
nothing new**, while storing 44 fresh closing lines.

That is not yet a fault, and it is not yet growth either. The pricing pass wrote
`recommendations: 1` and then `0`, with `unchanged_confirmed: 39/40` — the
dedupe stamping existing rows rather than writing new ones, which is correct and
means `created_ms` stays put. A row can only score if a *new* row is written
before its game's close, so the counter's growth rate is bounded by how often
the pass writes a genuinely new recommendation, not by how many lines are
stored.

So: `clv_scored` went from **structurally impossible** to **possible**, which is
the real win and stands. It has not yet been shown to *accumulate*. Read
`rows_joined` and `recommendations` together over a full day before believing
either story; if `rows_joined` stays pinned at 190, no new row is scoring.

### DEPLOYED and READ (2026-08-09, 04:07Z) — the burst hypothesis is confirmed

Live is on `e885bca`. One machine `started`, 1/1 checks, restarted in place on
the volume, gate locked, five pages 307, `/api/orders` 401 with and without a
forged bearer.

**The first pass is now 10 log lines. It was 963.** Three things never before
observed:

    [migrate] /data/cockpit.db already at schema v5      <- a reading, not an inference
    INFO backend.api.routes: API starting: instance_mode=live ...
    INFO backend.kalshi.discovery: discovery: 167 priceable events;
         unknown_scopes=962; rejected ...                <- first appearance ever

That third line is the confirmation. It is emitted in the **same millisecond**
as the aggregated warning, from code that never changed — so the reason it had
never arrived was the 962-line burst sitting in front of it, exactly as
diagnosed. The one warning now reads `317 unrecognised competition_scope
value(s) across 962 series ... (56 named, 261 counted)`.

Also: the live db is `/data/cockpit.db`, not `/data/live.db` as earlier notes in
this file said.

First pass on the new image: `recommendations: 4, suppressed: 4, surfaced: 0,
unchanged_confirmed: 36`, `clv_scored: 0`, `clv_rows_joined: 190`.

---

## READ FIRST (2026-08-09) — the gate's counter cannot grow, and it is arithmetic

Found while reading the live logs. **`clv_scored` has been 0 on every recent
pass, and it is not a transient.** Two passes on record:

    rows_joined: 228   scored: 0   skipped_entry_after_close: 228   (08-08)
    rows_joined: 249   scored: 0   skipped_entry_after_close: 249   (08-09)

The previous handoff flagged 228/228 as "worth a second look if it does not
move". It moved to 249/249.

**The composition, and neither number is wrong on its own:**

| Quantity | Where | Value |
|---|---|---|
| Sweep fires at | `odds/timing.py`, `fire_until = anchor - max_odds_age_ms` | kickoff − 15 min |
| ...through | `fire_from = fire_until - due_window_ms` | kickoff − 45 min |
| Closing line read at | `scoring.py`, `target_ms = commence - horizon` | kickoff − 60 min |
| Scoring requires | `clv.py`, `r.created_ms <= c.observed_ms` | entry before the close |

A recommendation cannot exist before its odds sweep, so the **earliest** any row
is created is kickoff − 45 min. The closing line is observed at kickoff − 60 min
(earlier still, by up to `WINDOW_MINUTES`). So `created_ms <= observed_ms` is
false for **every** row the scheduled sweep path produces, permanently.

The gate needs **300 scored games**. On this path it will never reach one.

**Why it was invisible, and why it is new.** Every counter reads healthy;
`rows_joined` is nonzero and `skipped_entry_after_close` is faithfully reported
— that counter was *added on purpose* so this case would be visible. It was
visible. Nobody multiplied it out. And an earlier run really did score 34 rows,
because before `odds/timing.py` landed the sweeps fired at arbitrary times, so
some rows happened to land more than an hour before kickoff. **The scheduler fix
— correct on its own terms, and the thing that made the tool actionable — closed
the last path by which anything could be scored.**

This is [[two-limits-on-one-quantity]] on the one number the gate is built from.

**`docs/adr/0011` decides it, and it is now implemented** (schema v5).

The close becomes the **last pre-game quote** (primary horizon 0, control 1.0h,
which is where the ~34 already-scored rows sit). Shortening it is also the
*conservative* direction, which was the surprise: a market sharpens toward
kickoff, so scoring against a price an hour out was measuring against a weaker
benchmark and would have flattered any result it ever produced.

All four pieces landed, and the two that mattered most were found by the
disable-check rather than by writing them:

1. `DEFAULT_HORIZON_HOURS = 0.0`, `CONTROL_HORIZON_HOURS = 1.0`. **Watch for
   truthiness** — `0.0` is falsy and this repo has a lesson about zeros that
   mean something. Grep every `if horizon` before trusting it.
2. Schema v5: `recommendations.clv_horizon_hours`, backfilled `1.0` where
   `clv_scored_ms IS NOT NULL`. Without it `clv_tenths` becomes a silent
   mixture of two regimes.
3. Tag the rows scored at 1.0h with `clv_horizon_hours = 1.0` and **leave
   them alone** (amended by Joe before it ran anywhere). The gate's filter
   already excludes them, so clearing them bought nothing and would have
   edited the one record that cannot be recreated.
4. The composition test: fail if `primary_horizon + WINDOW_MINUTES` reaches back
   past `max_odds_age_ms + due_window_ms` before kickoff. Express it as a
   relationship between the four constants, not as `assert horizon == 0.0` —
   pinning the value passes while someone widens the due window and rebuilds
   the same collision from the other side.

---

## DEPLOYED (2026-08-09, ~03:17Z) — and `clv_scored` left zero

Live is on the current image. `restarts=0`, one machine, volume attached, gate
locked, five pages 307 -> /login, `/api/orders` 401 with and without a forged
bearer. First pass on the new image:

    CLV scoring at 0.0h horizon: {'scored': 59, 'skipped_entry_after_close': 190,
                                  'rows_joined': 249}
    settlement pass: {'positions_open': 0, 'settled': 0, 'still_unresolved': 0,
                      'refused': 0}
    pricing pass: {... 'surfaced': 0, 'skeptic_reviewed': 0, 'skeptic_blocked': 0 ...}

**`scored` had been 0 for the project's entire life.** The evidence layer is
recording. The gate's binding constraint is no longer code — it is the four
fee-calibration trades, which need Joe.

**Still unobserved:** the `[migrate]` and `API starting` boot lines. v5 running
was confirmed by its effects, which is an inference. The first pass of a fresh
process still emits all 94 scope warnings at once and fills the 100-line buffer;
any *later* pass should be clean, and checking that is the first task next
session. See `start.md`.

---

## HANDOFF (2026-08-09, ~00:10Z — the settlement path is built, nothing is deployed)

**State:** 1,288 tests, ruff green, `dbt build` 11 nodes green, pushed. `main`
is `2353bd1`. **Both instances are still on `89bf56a`** — everything below is
local and unshipped.

### Demo is deployed and green. **Live is the one thing outstanding.**

    # from the browser -- the classifier blocks live from a session:
    # Actions -> Deploy -> Run workflow -> live -> type kalshi-cockpit

Demo went out on `2353bd1` and verified: five pages 200, `instance_mode=demo`,
and both boot lines readable —

    [migrate] /data/demo.db already at schema v4
    INFO backend.api.routes: API starting: instance_mode=demo ...

**What the canary did not prove, and cannot.** The entrypoint *seeds before it
migrates*, and `seed_all` calls `init_db`, which builds the database at the
current version and stamps it. So `migrate_db.py` on demo is a no-op **by
construction** — "already at v4" there means the seeder had just created it at
v4, not that a transition ran. Demo proves the image boots and that the schema
file and the v4 shape agree on a fresh database. It says nothing about v3 → v4.

Live's volume is the only real test of that, and it is the first non-additive
migration in this project. What backs it instead: the boot script was run twice
against a genuine v3 database carrying rows (migrated, then no-op, orders
preserved, index present), and `test_the_migration_step_actually_runs_on_a_real_
old_database` runs it as a subprocess against a database wound back one version.

**v4 rebuilds `settlements`.** The rebuild is idempotent at every crash point
and was verified by running `scripts/migrate_db.py` twice against a genuine v3
database, but it is the first migration in this project that is not purely
additive, so the canary matters more than usual.

Three things to read in the log once it lands. The first two are the claims
`start.md` asked me to verify and I could not — see why below:

    [migrate] /data/live.db migrated v3 -> v4
    INFO backend.api.routes: API starting: instance_mode=live
    backend.settlement: settlement pass: {'positions_open': 0, 'settled': 0, ...}

### Why claims 1 and 2 were unverifiable, which turned out to be a real defect

`flyctl logs` returns a line-bounded buffer, and **98 of the 100 lines in it were
one warning** — `unrecognised competition_scope`, 94 distinct series, not one of
them a sport (`KXFED`, `KXWMT`, AP polls, draft picks). A quote pass re-emits the
whole set every 15s while the window is open. The boot lines were pushed out
within seconds of every boot.

The dedupe was there and was being cleared at the top of every pass, by a fix
for "warned once at boot then went quiet". Both halves defended in prose, four
lines apart. Now: the warning names a developer action item **once per process**,
and `discovery:` prints `unknown_scopes=N` every pass, including at zero. The
live stream should be readable for the first time.

Claim 3 is answered: **the fleet has never run.** The live pass line reads
`'surfaced': 0` — and carried neither `skeptic_reviewed` nor `skeptic_blocked`,
because `ALWAYS_REPORT` omitted the two fields whose own comment says they are
"reported anyway". Fixed; they print now.

### What landed

- **ADR 0010** — the paper settlement path, six decisions, three of them
  measurement decisions. Written after the capture, not before.
- **`backend/settlement.py`** — reads Kalshi's `result`, writes one row per
  position, releases its capital. On the full pass only.
- **Schema v4** — `settlements` is per-position (`order_id`, `dry_run`,
  `fill_assumption`, `depth_at_order`, `UNIQUE (order_id)`); `orders` gains
  `fill_assumption` and `assumed_filled_count`.
- **`max_exposure_dollars` binds in production for the first time**, on paper.
  This reverses ADR 0008, and only settlement makes it safe. Paper and live are
  separate budgets, never pooled, so the first real order sees a clean one.
- **The migration framework stopped parsing SQL.** Five readers recovered index
  names from statement text; one is the boot script, under `set -e`. v4's
  `ALTER TABLE ... RENAME` would have exited 1 there. Verified by restoring the
  old parser and watching it happen.

### Two things worth your attention

1. **I introduced a silent regression and caught it late.** v4's `NOT NULL
   order_id` turned `seed_demo`'s `INSERT OR IGNORE` into a no-op: zero
   settlements written, count of 400 returned, calibration mart quietly empty.
   The rule now in `lessons.md` is mechanical — when adding a `NOT NULL`, grep
   every `INSERT OR IGNORE INTO <table>` in the repo. I ran it; nothing else is
   affected.
2. **One disable-check stayed green and it was a real gap**, not a false alarm:
   `positions_awaiting_settlement` and the exposure query encode the same
   "which positions are open" rule, and only one had a test for the case v4
   exists for. Both covered now.

### Still open

- **The two boot lines are still unobserved.** They need a deploy; the flood
  that hid them is fixed.
- **No live instance has ever produced a surfaced row**, so the settlement pass
  will report `positions_open: 0` indefinitely and the fleet still costs
  nothing. Both are honest zeros, and both are now *printed* rather than
  inferred.
- **`ws.py` has still never opened a socket on live.** Unchanged.
- Exposure is fee-exclusive against a fee-inclusive cap (~2%). Re-costed while
  migrating and deliberately left open: adding a column is cheap, changing what
  `limit_price_tenths` means is not.
- Two things need Joe, neither urgent: **one combo price lookup**, and the
  **four fee-calibration trades**.

---

## HANDOFF (2026-08-08, evening — demo is deployed, live is one tap away)

**State:** 1,243 tests, ruff green, frontend builds, **pushed**, CI green on
every push. `main` is `883c8be`.

### THE ONE THING OUTSTANDING: deploy live

    ! gh workflow run Deploy -f instance=live -f confirm_live=kalshi-cockpit

Everything below is already on **demo** and verified there. Live is still on
`a567ee7` and healthy. The Claude Code classifier blocks the live deploy from
this session (it allowed the demo one), so it needs a human or the browser.

**It carries the v2 → v3 migration.** Two nullable columns on `orders`
(`idempotency_key`, `response_body_json`) plus a unique index. Expect
`[migrate] ... migrated v2 -> v3` in the logs — unlike the previous deploy,
where the absence of migration output was correct.

After it lands, three things to confirm:
`agent_fleet_configured: true` on `/api/health` (the secret is already set on
Fly), the `migrated v2 -> v3` line, and an `API starting: instance_mode=live`
line.

### The canary caught a crash loop, which is the headline

The first demo deploy **failed**, at Verify, with a 502 that was not a cold
start. `scripts/migrate_db.py` read `_MIGRATIONS` in a shape it no longer had:

    TypeError: '_Migration' object is not iterable

`_MIGRATIONS` gained a dataclass so v3 could carry an index as well as columns;
every reader inside `backend/` was updated and the one in `scripts/` — the only
reader that runs at boot — was not. **Straight to live, that is a crash loop on
the volume holding the evidence record.**

`test_has_callers.py` already asserted the migration runs before uvicorn *and*
survives `.dockerignore`. Both true, and it still crash-looped: a boot step
covered by assertions *about* it rather than by running it. Nothing executed
the script. It runs in a test now, as a subprocess, exactly as the entrypoint
invokes it, against a database wound back one version — verified by restoring
the bug and watching it fail with the same TypeError.

### Verified on demo, so the same image is proven to boot

    [migrate] /data/demo.db already at schema v3
    INFO backend.api.routes: API starting: instance_mode=demo ...

That second line **answers the logging question** that had been open since the
morning: timestamp, level, logger name, through the root logger. The API
process configures logging. It was unanswerable from outside before, because
uvicorn runs `--no-access-log` and the hub only speaks when something changes —
so a healthy API and a mute one produced identical log streams. `create_app`
now says one thing at boot, which is what makes the stream readable at all.

**What demo still cannot prove:** its database is reseeded every boot, so it
was *created* at v3 and never ran the v2 → v3 transition. Live's volume is at
v2 with real rows and will be the first real execution of that path. Backed by
`test_each_single_step_runs_on_a_database_one_version_behind`, which was added
after noticing that every migration test built a **v1** database — so 1 → 3 was
covered as a sweep and 2 → 3, the only transition production makes, was not.

### Also landed

- **The agent fleet is wired.** `backend/agents/review.py`. Reviews before
  persisting, surfaced rows only, thread-based async seam. It blocked a real
  row on its first live API call. See the closed item in section 2.
- **Two taps are one order.** ADR 0009.
- **`Ops` has no default instance.** It defaulted to `demo`, so a dropped input
  succeeded against the wrong box — worse than failing. The run summary now
  names the app and cross-checks `/api/health`.
- **`agent_fleet_configured` on `/api/health`**, because an unconfigured fleet
  is silent by design and was otherwise indistinguishable from a working one.
- `ANTHROPIC_API_KEY` **is set on Fly** (live), inert until the deploy.

### The agent fleet is wired up

`backend/agents/review.py`. The pass collects, reviews the surfaced rows in one
batch, applies verdicts, then persists — so there is no window in which an
unreviewed row is orderable. Details in the closed item in section 2.

Two things the design note in this file got wrong, both of which would have
shipped green: `asyncio.run` at the seam raises inside a running loop, which is
where production always calls it from; and the test suite was making live
Anthropic calls on any machine with the key in `.env`, so the same test called
Claude locally and skipped the review in CI. Both in `tasks/lessons.md`.

**It blocked a real row on its first live run** — see the item for what it
caught and why that was a fixture bug rather than a venue finding.

### Two taps are one order

`docs/adr/0009`. The client mints an idempotency key when the ticket **opens**,
so a double-tap and a retry after a dropped connection carry the same one; the
endpoint replays the first attempt's recorded response instead of placing a
second order. Required, not optional — an optional key protects only the callers
that remember it.

Three layers, and the ADR sets out what each covers that the others cannot: the
step-0 read (survives a stale row), the check inside `reserve_order`'s write
lock (survives concurrent taps), and the unique index (survives a writer that
does not go through `reserve_order`). Disabling each one turns a different test
red, which is how they were checked.

**Building it found a defect that would have crash-looped the live instance.**
`init_db` applied `schema.sql` *before* migrating. That is fine for as long as
migrations only add columns, and it breaks the moment the schema file declares
an index over one — `executescript` runs against existing databases too, and the
column is not there yet. A **fresh** database gets it from `CREATE TABLE`, so
every test written against one passes. `init_db` migrates first now, and the
migration tests were generalised to cover every version and every table rather
than hardcoding v2 and `recommendations`.

Gap 2 of ADR 0008 was already closed last session; gap 3 (exposure fee-exclusive
against a fee-inclusive cap, ~2%) stands and is still not worth a migration.

### Not started: the paper settlement path

The remaining backend item, and the prerequisite for `max_exposure_dollars`
binding on anything before a live order exists. It needs a settlement source
from Kalshi and a decision about whether a dry run is assumed to have filled,
which is a measurement question rather than a plumbing one — assuming a fill at
the limit flatters the record, and the record is the product.

---

## HANDOFF (2026-08-08, 14:4xZ — the sheet is merged, and running it found four more)

**State:** 1,206 tests, ruff green, seven pushes, **CI green on every one**.
`lane/frontend-wip` is verified and merged; the branch can be deleted.

### Both instances are deployed, on `a567ee7`

**Demo first as a canary, then live** — the ordering that paid for itself last
time. Demo verified before live was triggered.

    demo  https://kalshi-cockpit-demo.fly.dev   five pages 200 over 20
                                                requests, no error text,
                                                instance_mode=demo,
                                                /api/orders -> 403 with and
                                                without a forged bearer
    live  https://kalshi-cockpit.fly.dev        five pages 307 -> /login,
                                                /api/orders 401 with and
                                                without a forged bearer

    {"status":"ok","instance_mode":"live","live_trading_enabled":false,
     "execution_available":false,"notifications_configured":true,
     "live_quotes_available":true}

**The ticket sheet was tapped on the deployed demo**, not only locally: opens
at 320 and 390, fits both, returns **403**, focus stays inside the dialog.

**No migration ran, and that was checked rather than hoped.** `SCHEMA_VERSION`
is 2, the volume was already at 2, and the only `schema.sql` change since the
previous deploy was comment text on two existing `orders` columns — verified
from the diff before triggering. The price grid is not persisted at all, so
ADR 0007 needed nothing from the volume.

**The live deploy failed once, correctly.** `confirm_live` arrived empty from
the GitHub mobile web form and the guard stopped the job at step 3, before
flyctl. That is the safeguard working and the failure mode `tasks/PHONE.md`
already records: the mobile form is unreliable for workflows with inputs. Use
`gh workflow run Deploy -f instance=live -f confirm_live=kalshi-cockpit`.

**Still unobserved, and it needs the `Ops` workflow:** machine state, restart
count, and the log stream. Two things to look for in the logs, both of which
only production can show — that the migration was a **no-op**, and that
`backend.*` INFO lines now appear *at all*, which is the whole point of the
logging fix below.

### The lane is merged, and none of its defects were layout

The ticket sheet fit 320/390/430 on the first render. What was wrong was
behaviour, which is the argument for running a thing rather than reading it:

- **The focus trap opened at the moment the answer arrived.** Confirm unmounts
  when the response lands, focus falls to `<body>`, and the Tab handler only
  wraps from the first or last control *inside* the panel — so the next Tab
  walked into the page behind the veil.
- **A disabled Confirm named the wrong reason.** On an expired row it said
  "The token above is required", three paragraphs under its own note saying
  the consensus had aged out. Typing the token would have left the button
  exactly as dead. That is most rows, most of the day.
- **Close was a 59x26 target**, on a sheet whose docstring argues from thumbs.
- A **403** offered "Back", beside a sentence saying retrying will not help.

`scripts/check_ticket_sheet.py` is the new check and the reason all four were
found: it taps, waits out the entrance animation, measures, presses Confirm,
and measures the answer. `--fail-order` renders the offline state, which no
database can produce and is the only way to see the two-button action bar.

**Verified against three instances:** live with a locked gate (**423**, four
conditions), an expired-row instance, and demo (**403**). Also
`--fail-order` for the no-reply state.

### `check_mobile.py` could not see a whole class of defect, and now can

The Board read **"CONSENSUSKALSHI"** at 320px — a label needing 86px in a 69px
cell, painting over its neighbour. `grid-cols-3` is `repeat(3, minmax(0, 1fr))`
and the `0` lets a column shrink below its own content, so nothing overflowed:
same `scrollWidth` as a correct layout, same screenshot dimensions. The only
evidence was looking at the picture.

The script now also reports any leaf with visible overflow whose `scrollWidth`
exceeds its `clientWidth`. Across five pages and seven widths it found that
defect twice and nothing else. The card is two columns until `lg`, with the
edge spanning below — and the breakpoint is measured, not chosen: the Board
goes two-up at `sm`, so a card at 640px is *narrower* than one at 430px and
`sm:grid-cols-3` would have reintroduced it one breakpoint up.

### The deployed API process had no logging configuration at all

`docker/entrypoint.sh` runs `uvicorn backend.api.routes:create_app --factory`,
so `backend/main.py` — the only caller of `basicConfig` — has never run on a
deployed instance. Started that way, the root logger has no handler: **every
`backend.*` INFO record was discarded**, and what did come out went through
`lastResort` with no timestamp, level or logger name. The API is the process
that runs the quote hub, whose entire recent design is "a dead feed must be
visible".

The redaction filter added after a live credential reached a transcript was
therefore installed in the runner and not in the API. Nothing here puts a key
in a URL today, so what was lost was defence in depth rather than a key.

`create_app` calls `configure_logging()` now — the one seam every entry point
shares. Verified by disabling, and by re-running the exact entrypoint command.

### One observation, recorded rather than acted on

**`ws.py` has now been run in production shape**, which had not happened
before. Subscribing to a ticker the exchange does not recognise gets back a
snapshot carrying only `market_id` and `market_ticker` — no levels field on
either side — and the parser correctly raises rather than inventing an empty
book. What that does **not** settle is whether a real market with a genuinely
empty book looks the same. All 12 snapshots in the capture carry both sides
with levels, so the two cases are currently indistinguishable. One live
subscription to an illiquid real market would settle it, at zero odds credits.
Do not "fix" it by treating a missing key as an empty book — that is the
unreadable-resolves-to-zero failure the module exists to prevent.

### The exposure cap bounded each order and not the portfolio

`store.orders.reserve_order`. The endpoint read exposure on its read-only
handle, sized against it, then inserted on a different connection — so two
requests arriving together each sized as though the other did not exist. The
row and the cap check are now one transaction, with the check **after** the
insert, so the answer is a fact about the database rather than a prediction.

Two things worth carrying: the test is two real threads on two connections,
because `TestClient` never makes the hop and that is how the last concurrency
regression test in this repo passed against unfixed code; and **the docstring
I wrote first was wrong** — it credited `BEGIN IMMEDIATE`, and a deferred
`BEGIN` leaves the test green because the insert takes the write lock anyway.
What is load-bearing is the order of the two statements.

It still cannot fire in production. Dry runs consume none of the cap, which is
asserted as a test rather than left in prose.

### The README claimed the wire format was unverified

It has been verified since 2026-08-07, by the capture that found the parser
reading 0 of 257 frames. Three other numbers had drifted, and every one of
them understated the work. Also added: the demo link, the gate section, and
the two browser checks that cannot run in CI.

---

## HANDOFF (2026-08-08, overnight — three lanes, and CI was already red)

**State:** 1,201 tests, `dbt build` 11 nodes green, ruff green (newly wired),
tree clean, **pushed, and CI is green on all three jobs** — the first fully
green run in 37 pushes.

**Two tests turned out to be measurements of the environment**, both found in
the last hour and both now fixed: the demo seed contradicted itself between
10:00Z and 15:00Z (two sweeps five hours apart, a budget day rolling at
10:00Z), and an order-path assertion compared against the literal string
`odds 1800s old` while CI, being slower to build the fixture, produced
`1802s`. Neither was a flake to retry — the first was a real defect in the
demo, the second a test asserting machine speed. Both lessons are in
`tasks/lessons.md`; the general form is that a test depending on an input it
does not supply is measuring the environment, not the code. **Still not deployed** — the live instance is on the
image from before ADR 0007, so the next deploy carries the V2 order path, the
price-grid snap, and everything below. The order path is dry-run-only and the
gate is locked, so nothing here is urgent. **Deploying is your call; I did
not.**

Five things landed: the order record, the three CI follow-ups, the
`occurrence_datetime` measurement, a repair to CI that had to happen first,
and a cache breakpoint in the agent fleet that had never cached anything.

### Two lanes did not finish, and one has work worth keeping

Both were killed by a session limit mid-task, not by anything they hit.

- **`lane/frontend-wip` — the ticket bottom sheet, committed but NOT merged.**
  `TicketSheet.tsx` (962 lines), `TicketProvider.tsx`, and changes to
  `page.tsx` / `LiveBoard.tsx` / `lib/api.ts`. It died while running
  `check_mobile.py`, so **nothing has been rendered, measured at 320/390/430,
  or tapped against a locked gate** — and the gate refusal is the state this
  component will actually be in. Committed only so a worktree cleanup cannot
  delete it. Finish the verification before merging.
- **README** — nothing committed. Start it over.

### The agent fleet's prompt cache was a no-op

`agents/base.py` marked `HOUSE_CONTEXT` with `cache_control`, behind a comment
calling the savings "the whole reason to cache". Measured against
`claude-opus-5`: the block is **401 tokens** and the minimum cacheable prefix
is **512**. It had never produced an entry — no error, no warning,
`cache_creation_input_tokens: 0`.

Breakpoint moved to the last system block (738–985 tokens per agent).
`scripts/measure_agent_cache_prefix.py` re-measures and exits non-zero if any
agent falls under. It exists because the minimum is model-specific and **not
monotonic** — 512 on Claude Opus 5, 1024 on Opus 4.8, 4096 on Opus 4.6 — so
pointing `AGENT_MODEL` at an older model turns the cache off silently.

**The module is still called by nothing.** This fixes a path that has never
run. Wiring the fleet up is still open and is the largest thing left in
section 2 — see the note under that item for the design I did not build.

### Read this first — the secret scan was red on `main` and nobody had pushed

The `quoted` pattern added two commits earlier matches a quote followed by a PEM
header ending the line. `tasks/lessons.md` documents that exact case **by
reproducing it**, in a fenced code block. So the repair for a false negative
shipped a false positive onto the file explaining the false negative — third
consecutive turn of the same screw on one check.

The quote was never the distinguishing feature. **The next line is.** A quoted
header followed by a fence is a mention; one followed by forty characters of
base64 is a key. That one case is now two lines of awk, no path exclusion was
added, and `tasks/lessons.md` joins the two files asserted to stay clean —
because prose about leaked keys is a genuinely plausible place for one to be
pasted, and excluding it would make the most likely accident the least visible.

Verified by extracting the step and running it: clean tree 0, five planted
shapes each 1, both negatives 0.

### `orders` rows are written — and the framing in this file was wrong

`docs/adr/0008`. The item said the point was to give `max_exposure_dollars`
something to read. **It does not do that**, and that is worth saying plainly:
every order the running system places is a dry run, dry runs commit nothing, so
the cap still does not bind in production. It begins binding the day a live
order exists.

Counting paper orders instead would make it bind and would be worse — nothing
settles a paper position, so paper exposure could only ratchet up until the
endpoint refused everything with no way to release it. **A paper settlement path
is the prerequisite, not a change to the exposure query.**

What the change is actually for is the other two reasons, and the first is the
serious one:

- **`client_order_id` existed only in memory.** It is the idempotency key, and
  the failure it exists for is a POST that times out *after* Kalshi accepted it.
  Recording after the response loses the key in exactly that case. The row now
  goes in as `pending` **before** the request; a failed write refuses the order,
  a failed *outcome* write does not unwind it and is reported instead.
- **CLV and the fill priced different numbers.** `orders.recommendation_id` is
  the join that did not exist.

**And it surfaced two implementations of exposure.** `runner.py` summed `fills`
net of `settlements`, the endpoint summed live `orders`. Both had been on the
money path for the project's life and both returned `0.0` every time, so they
had never disagreed — and they answer different questions, so they would have
the moment a row was written. One deleted. `orders` wins: a resting order is
committed capital, and counting fills alone lets a hundred resting orders each
size against zero.

The surviving query enumerates the **terminal** statuses instead of the live
ones. The old list dropped `partially_filled` and `unrecognised_response` — the
status this project invented so an unreadable response could not be mistaken for
anything, valued at zero dollars by an allow-list.

13 guards verified by disabling. One stayed green: `PRAGMA busy_timeout = 5000`
is exactly CPython's own default, so the line was a literal no-op. Now an
explicit `timeout=` on `connect`, because there are two writer processes and the
value should be one we chose.

### `occurrence_datetime` is a shifted start. Story B is refuted

The open question in section 3 is closed, at zero odds credits.
`scripts/measure_occurrence_datetime.py`, capture in
`tests/fixtures/occurrence_datetime_probe.json`, full write-up was in
`tasks/inbox/research.md`.

The discriminator is a period series: an F5 market and a game market on the same
game must agree if the field is a start and differ by the period if it is an
end. Across 15 series pairs, **not one period market is earlier than its game
market**; 13 identical, 2 later. On one MLB game, nine market types — including
`KXMLBRFI` (resolves ~20 min in) and `KXMLBEXTRAS` (resolves at the end or
later) — carry the identical value, exactly +3.00h from the first pitch written
in words in each market's own `rules_primary`. Markets expiring hours apart
cannot share an expiry.

I re-derived the +3.00h from the committed capture myself rather than taking the
agent's word for it. Note the persisted evidence is thinner than the headline:
the fixture holds 15 period pairs and one anchored game, while the agent
measured 171 pairs and 189 fixtures live. The script re-derives the rest against
a free endpoint.

**Consequence for the code: change nothing.** The offset is not
game-length-dependent, so the fixed 4h tolerance in `match.linker` and
`core.suppression` is correct — that was the worry and the answer is no. But
`KXMLBF5` sits at **+5h** while `KXMLBF5SPREAD`, covering the identical five
innings, sits at +3h, so the extra two hours are per-series data entry. Nothing
in scope prices a period series today; the day one is priced, a 4h tolerance
drops every `KXMLBF5` market silently. Filed in section 2.

### CI follow-ups: all three done, one unverifiable until pushed

- `.gitignore` was missing `.p12` **and** `.pkcs8`; CI refused both.
- **ruff is wired, not dropped.** Its current default selects 413 rules and
  finds 513 violations here, which would have been red on the first push — the
  exact failure just removed. Selected `E4,E7,E9,F` (59 rules), excluded the 4
  codes accounting for all 32 findings, 55 rules active, **0** findings.
  Verified by planting an `F821` and watching it exit 1.
- Actions bumped off the retiring Node runtime: `checkout@v7`,
  `setup-python@v7`, `setup-node@v7`, `gitleaks-action@v3`, each confirmed by
  reading `action.yml` at that tag rather than guessing. **An Action cannot run
  locally, so this one is unverified until the first push** — watch that all
  four jobs still start.

Wiring ruff immediately caught eight F811s in the new test file: importing a
fixture by name makes every signature that takes it a redefinition. Split into
`build_armed_db` rather than silenced.

### What is still open, and what is new

The three gaps recorded in ADR 0008, all of which become real the day the gate
opens and none of which are worth building against an untestable live path now:
~~**placement is not idempotent**~~ (**done 2026-08-08, ADR 0009** — and the
"untestable" framing was wrong: the replay path never touches Kalshi, and
building it found a migration-ordering defect that would have crash-looped the
live instance), ~~**two concurrent requests can size against one exposure
reading**~~ (**done 2026-08-08**, `reserve_order`), and **exposure is
fee-exclusive while the cap is spent fee-inclusive** (~2%) — still open, still
not worth a migration.

---

## HANDOFF (2026-08-08, 05:2xZ — deployed, and the demo found the bug for us)

**Both instances are on the new image.** Demo verified, live verified, live
machine `started`, checks 1/1, **restarts 0**, volume attached.

    demo  https://kalshi-cockpit-demo.fly.dev   five pages 200, no error text,
                                                instance_mode=demo, forged
                                                bearer on /api/orders -> 403
    live  https://kalshi-cockpit.fly.dev        five pages 307 -> /login,
                                                /api/orders 401 with and
                                                without a forged bearer

    {"status":"ok","instance_mode":"live","live_trading_enabled":false,
     "execution_available":false,"notifications_configured":true,
     "live_quotes_available":true}

**The migration ran.** `unchanged_confirmed: 50` on the first pass is a v2
column doing its job, so the schema change reached the volume before uvicorn
opened it.

### The two-step deploy paid for itself on its first use

The demo crash-looped: `can't open file '/app/scripts/migrate_db.py'`, exit 2
under `set -e`, ten restarts, machine gone. `.dockerignore` denies `scripts/*`
and allowlists by hand; the allowlist named `run_loop.py` and nothing else,
because it was written when the entrypoint ran one script. **Live would have
taken the same crash loop on the volume holding the only copy of the record.**

`TestTheEntrypointRunsWhatItMustRunFirst` asserted the migration runs before
uvicorn and passed throughout — it was true, and the file it named was not in
the image. The allowlist is now derived from the entrypoint rather than
maintained by hand. See `tasks/lessons.md`.

**Also fixed before the live deploy: the diagnostic you were told to watch was
counting the wrong population.** `observe_pass_duration` ran on every pass and
always compared against the *fast* interval, so the first full pass — 167
events, 1,426 markets, 228 rows joined, 14.9s, healthy, window closed — raised
`passes_over_quote_budget`. Full passes happen every 900s forever, so that
counter would have been ~96 routine entries a day and could never have shown
the one condition it exists for. `kind` is now a required argument and full
passes get their own counter.

### Read this before believing the ticker is verified

**`ws.py` still has not opened a socket in production.** `live_quotes_available:
true` says the hub *loop* is running, which is exactly what it was changed to
mean — but `_one_cycle` returns early with `{"type": "idle"}` when no row is
bettable, and with `surfaced: 0` and the odds budget spent there have been no
bettable rows. So no WebSocket has been opened on the live instance, and the
things you asked me to watch for — reconnect loops, memory growth on a 1GB
machine — **cannot be observed yet.** They become observable the first time a
window opens with a surfaced row, not before.

### The gate's population — reported, not yet decided

Done as you specified: **both groups side by side, with `n` for each, before
anyone changes which one the floor counts.** `gate.clv_by_population` returns
`actionable` / `no_edge` / `suppressed` / `pooled`, the three matching the
digest's own framing so the two screens cannot describe the record differently.
The gate's `scored_recommendations` detail now carries
`actionable Ng/Nr, no_edge Ng/Nr, suppressed Ng/Nr` beside the aggregate, and
when nothing actionable has been scored it says so outright.

**The digest had the same defect and it is the one that reaches your phone.**
`_digest_stats` ran its own SQL with a comment saying it counted "the way the
gate counts it" — true, and the gate's way was the mixture. It now calls
`clv_by_population` rather than agreeing with it, per the repo's rule about
deleting one of two paths. The Discord embed reports the actionable count as
the headline with the pooled count beside it and the gap named.

Fixing it surfaced a fixture that could not have been real: a test set
`clv_tenths` without `clv_scored_ms`, which the digest's looser predicate
accepted and `score_recommendations` can never produce — it writes both in one
UPDATE.

**Decided (you said "decide for me"): the floor counts `actionable`.** Both CLV
conditions now read that population. `docs/adr/0005-the-gate-counts-actionable-
games.md` has the full reasoning; the short version is that it is a *safety*
change, not a relabelling — a systematic CLV among refused rows moves the
pooled mean rather than blunting it, and `suspicious_edge` rows are the
likeliest carriers, so pooled they could arm real money on evidence about bets
the strategy declines to make. It also moves the gate strictly further away in
both conditions: the actionable set is a subset, so the floor is harder to
reach, and `always_valid_multiplier` *grows* as `n` shrinks (9.84 at n=20
against 3.66 at n=300), so a small actionable sample clears a taller bar. A
money guard that changes should change in that direction.

It reads **0 of 300** and will for a while. The breakdown sits beside it.

**And it caught a test fixture arming the gate from refused rows.**
`test_quote_refresh.armed_db` built 400 scored games at
`suggested_contracts=0` — "no edge here", four hundred times — and that
satisfied the floor, so every order-path test below it ran through a gate
opened by evidence the strategy would never have acted on. A gate fixture has
to be built from the population the gate counts.

### What to look at, and when

The budget day rolls at **10:00Z**. Until then no sweep can fire (`24 of 16
credits spent since 10:00Z`), so the window stays closed, no quote passes run,
and `surfaced: 0` means nothing at all. After the first sweep of the new day:

- `surfaced` — this is the first time the sentence "still 0 after a full window
  with the fast cadence running is the honest no-edge result" can be true.
- `passes_over_quote_budget` — now genuinely means the fast cadence is failing.
  `full_passes_over_limit_in_window` is the structural one and is expected to
  be nonzero, roughly once per window.
- The socket. First time `ws.py` runs for real.

**One number to keep an eye on that nobody has flagged yet:** the CLV pass
joined 228 rows and scored **0**, all of them `skipped_entry_after_close`. That
is the documented cost of requiring the entry to precede the close, and the
earlier run had 34 scored, so the scored rows are simply not re-joined — but
228/228 skipped is worth a second look if it does not move once games settle.

---

## Joe's asks, 2026-08-08 — four of them; two are done

Raised in chat while the quote-refresh work was landing.

1. **~~Stream the prices. Make the Board a ticker.~~ — done.** *"I'm thinking
   about this like a stock ticker. Billy Walters would like it."* And the
   sharper version: *"it seems like you're doing a lot to manage prices at their
   very small window snapshot, so wouldn't it just be easier to stream the
   prices in?"*

   He was right about the Kalshi half. `backend/live.py` is the hub, and
   **`backend/kalshi/ws.py` finally has a caller** — it was the fifth module in
   this project to be complete, tested and invoked by nothing. Verified against
   the live exchange: real book state for `KXNCAAFGAME-26SEP19MSUND-ND` arrived
   over the socket and out through SSE, and the depth it reported (640.95 at the
   yes ask) matches `yes_ask_size_fp` from the REST capture — an independent
   confirmation of the crossover.

   What it does **not** do, and this is the part to keep saying out loud:

   - **It does not widen the actionable window.** The fair value comes from a
     devigged sportsbook consensus at ~16 credits a day, 6 a sweep. Streaming
     Kalshi gives a live ask against a fair value up to fifteen minutes old.
     The window is an odds-budget fact and no amount of Kalshi streaming
     touches it. The banner and the feed header both say so.
   - **It does not replace the order-time refresh.** A browser's price is a
     client-supplied price and the server must never trust one. `POST
     /api/orders` re-reads the book itself; streaming means the two usually
     agree.
   - **The browser is given no arithmetic.** Edge and size are recomputed *on
     the server* by the same functions the order endpoint calls. Shipping the
     fee curve to TypeScript so the client could subtract it would put two
     implementations of a money calculation one refresh apart.
   - **A stopped ticker must look stopped.** Heartbeat every 10s regardless,
     `down` pushed the instant the feed dies and repeated on every heartbeat,
     and a client-side timer that treats total silence as a fault.

   **Verified end to end**, including the thing most likely to be silently
   broken: SSE survives Next's `/api/*` rewrite unbuffered — frames arrive
   exactly one heartbeat apart through the proxy, not in bursts.

   Two things left on it, neither blocking:
   - The hub prices against `exposure = 0` rather than reading the portfolio per
     frame. Display-only, and the order endpoint applies the real exposure, but
     the size on a card can therefore exceed what the server would accept once
     fills are persisted.
   - On a market with no book activity the cards keep their recorded prices
     until the first frame arrives. Correct, and it means "LIVE" can sit above
     a recorded price for a few seconds after a restart.

2. **~~A Kalshi-platform specialist agent~~ — done, and it earned its keep
   immediately.** `.claude/agents/kalshi-platform.md`. *"so that agent can check
   against everything we're doing to make sure everything is copacetic."*

   Pointed at the quote-refresh commit it found a defect I had introduced and
   two more besides — see the handoff below. It needs a session restart to
   register as a subagent type; until then it can be run by handing the file to
   a general-purpose agent.

3. **Is in-play betting viable?** See the item in section 3 — it is the largest
   of the four and the one with a real chance of a "no". Note that the order
   path now **refuses a started game** (added in response to finding 1 below),
   so nothing can leak into the record while the question is open.

4. **Is Python the right language everywhere?** *"if some other code language
   base works better in some places use that instead — Rust, C++, whatever."*
   Worth answering with a measurement rather than an opinion, and the repo's own
   rule applies: measure the style rule before believing it. The starting
   position, to be checked rather than assumed:

   - Nothing here has been shown to be compute-bound. The devig solvers, the
     copula, Elo — all microseconds on a ~100-game slate. The analytical half
     already runs in C++ via DuckDB.
   - The measured costs are network and budget: Kalshi REST round trips, a
     ~500ms `httpx.AsyncClient` construction (fixed by sharing it, not by
     rewriting), and 16 odds credits a day.
   - The one place latency genuinely decides money is stale-quote picking at
     ~400ms — and `tasks/lessons.md` records that as measured and refuted. It
     is a co-location problem, not a language problem.

   So the honest task is: `took_s` is already logged per pass; instrument the
   stages inside it, find where the wall clock actually goes, and only then
   consider rewriting a specific stage. A finding of "nothing is
   compute-bound" is a real answer and should be written down as an ADR so it
   is not re-litigated.

---

## HANDOFF (2026-08-08, later still — the price is live, and a review caught me)

**State:** 1,064 tests, frontend builds, all five pages fit 320/390px, Board and
ticker verified by rendering them against the live exchange. **Not deployed** —
the earlier migration has not shipped either, so the next deploy carries both.

Three things landed: the order-time quote refresh, the streaming ticker, and the
fixes from the Kalshi-platform review of the first one.

### The review found a defect I introduced, and it was the repo's own first rule

**Re-sizing at the live ask is one-sided.** An adverse move shrinks the order to
zero and refuses; a *favourable* move just buys more, up to what the engine
authorised. `size_position` is monotonic in price, so the re-derivation had a
refusal branch in one direction and none in the other — and the direction with
none is the one *"a large apparent edge is a bug until proven otherwise"* exists
for. An ask that fell six cents since the row was written is not six cents of
found money.

Fixed: `suppression.edge_ceiling_tenths` now runs at order time against the live
edge, using the engine's own config rather than a second constant.

**And the runner's in-play drop only covers rows it has not written yet.** A row
recorded ten minutes before kickoff keeps its size and stays inside the 900s
odds window well into the first quarter — and the refresh makes that worse, not
better, because the ask becomes a live in-play price while the fair value beside
it is a pre-game consensus. Measured in-play edges ran −200 to +68 tenths.
`recommendation_freshness` now carries the **sportsbook's** kickoff (joined
through `link_id`, never `kalshi_events.commence_ms`, which runs three hours
late) and the order path refuses a started game.

Three smaller ones, all from the same review:

- **Kalshi sends `"0.0000"`, not a missing field**, so the `live_ask is None`
  branch could never fire on a real one-sided book and the refusal that reached
  the screen said *"the price moved. Recorded 45c, live 100c"*. Now
  `is_valid_price`, with a message about there being no offer.
- The depth refusal claimed a fill guarantee the order does not have — plain GTC
  limit, no `time_in_force`, no cancel path anywhere in the repo. Reworded, and
  the thinness is logged.
- A 404 for an unknown ticker was served as 503, telling whoever is holding the
  phone to retry something that will never work.

**Still open from that review, recorded rather than fixed:**

- **The CLV price and the fill price are now different numbers.** CLV scores off
  `entry_ask_tenths`; the order goes out at the live ask. Nothing joins them
  because `orders` is still never written. The gate that arms real money is
  built entirely on CLV, so its evidence base and its executed bets would
  describe different prices. This is an argument for persisting orders *before*
  anything is armed, not after.
- **`_current_exposure_dollars` always returns `0.0`** for the same reason, so
  `max_exposure_dollars` does not currently bind in production even though it
  binds in the tests.
- One assumption still strictly unverified: no fixture ties `yes_ask_size_fp` to
  an orderbook NO-bid quantity *directly*. One call closes it —
  `GET /markets/{ticker}/orderbook`, compare the NO side's quantity against
  `yes_ask_size_fp`.

### Found while deciding whether to deploy — fixed, and it was the same shape

The hub's loop had no `except` around it, and `_load_subscriptions` opens the
database. `open_db` refuses an unrecognised schema version, **which is exactly
the state on the first boot after this deploy's migration** if the API comes up
before the runner has migrated. The task would have died, nothing would have
restarted it, and `/api/health` would have gone on reporting the ticker
available — because that checked `hub is not None`, a claim about construction.

A dead hub still answers `/api/stream/quotes` with snapshots and heartbeats,
both empty, which renders as a quiet market. That is the exact failure a ticker
introduces and the one the heartbeat exists to prevent, arriving through the
door nobody was watching.

Now: the cycle is wrapped, the failure is broadcast as `down` rather than only
logged, the loop retries, and health reports `is_running`.

### What to look at once it is live

- `live_quotes_available` on `/api/health` says whether the ticker is running —
  the loop, not the object. If it is `false` on the live instance, the hub died
  and the log has the reason.
- The feed header on the Board: `LIVE`, `FEED DOWN`, `FEED SILENT`, `NO LIVE
  ROWS`. `NO LIVE ROWS` is the expected state for most of the day.
- ~~**The rewrite destination is read at Next's start, not at build**~~ —
  **wrong, corrected 2026-08-08.** It is read at **build**. `next build`
  evaluates `next.config.ts` and freezes the result into
  `.next/routes-manifest.json`:
  `"destination": "http://127.0.0.1:8000/api/:path*"`. Setting `API_ORIGIN` at
  runtime does not move it.
  **`API_ORIGIN` is read in two places at two different times**, which is the
  part that bites: `next.config.ts` (build, the browser's `/api/*` proxy) and
  `lib/api.ts` `BASE` (runtime, server-component fetches). Set it at runtime
  and the two halves point at *different backends* — server components render
  from one and the browser's POST goes to the other. Caught by exactly that:
  a demo instance's ticket reported `401 Not authorised` while the demo
  backend's own answer, one curl away, was `403 This is the demo instance`.
  The image is correct by coincidence — the Dockerfile's runtime
  `API_ORIGIN` is the same value as the build-time default, and both
  processes share a host. The conclusion stands and the mechanism was wrong;
  the danger is that the wrong mechanism suggests a fix that silently does
  nothing. To point the proxy elsewhere you must **rebuild**.

---

## HANDOFF (2026-08-08, earlier — the 30-second window is fixed)

**State:** 998 tests, `dbt build` 11 nodes green, frontend builds, all five
pages fit 320/390px. **Not yet deployed** — see "Deploying this" below, because
this one carries a schema migration and the boot order matters.

### What changed

The previous handoff's item 1 — *"the window is 30 seconds, not 15 minutes"* —
is done, by the two fixes it proposed as composing. They do compose, and neither
works alone.

**1. A second cadence.** `backend/runner.run_quote_pass` re-reads Kalshi,
re-prices against the odds already stored, and spends nothing. The loop now runs
a **full pass every 900s** and a **quote pass every 15s while the window is
open** (`backend/scheduler.Tempo`). Kalshi REST is unmetered; the 900s interval
was The Odds API's limit applied to a leg that never needed it.

**2. `last_confirmed_ms`.** A quote pass that re-derives an identical decision
stamps the existing row instead of writing a duplicate, so `persist_if_changed`
keeps the record clean *and* freshness stops measuring from `created_ms`. Three
new columns, all nullable: the instant, and **both** ages at that instant.

Measured on a simulated 930 seconds of passes (61 quote, 1 full) against a real
database with fake clients:

    recommendation rows      4        (not 248 — the dedupe still holds)
    confirmed                4/4
    quote age at the end     0.0s     (limit 30s)
    odds age at the end      1354s    (limit 900s — correctly expired)

That last line is the point as much as the others. **This does not widen the
window.** Fifteen minutes twice a day is `MAX_ODDS_AGE_S` and the credit budget,
and no amount of Kalshi polling changes it. What changes is that the fifteen
minutes are now usable throughout rather than for the first thirty seconds —
about 30 min/day of actionability instead of about 1.

Item 3 from the last handoff — **refresh the quote at order time** — is still
open and is still the real fix for execution. It closes the gap between "this
row was true 15 seconds ago" and "this row is true now", which confirmation
narrows and cannot close.

### Deploying this

**The migration must run before uvicorn.** `docker/entrypoint.sh` now does that
(`scripts/migrate_db.py`), and a test asserts the ordering. The reason it
matters: the API opens read-only and `open_db` refuses an unrecognised schema
version, so on the first boot after this change the live instance would 500 on
every page until the runner happened to call `init_db` — while `/api/health`
stayed green throughout, because it touches no database.

Verified against a synthetic v1 database with 128 rows: refused before, migrated
v1 → v2, 128 rows kept, all three columns present, second run a no-op.

`RUNNER_FAST_INTERVAL_S` defaults to 15. Do not raise it past 18 and do not
raise `MAX_KALSHI_QUOTE_AGE_S` — the loop refuses to start if the composed
worst-case gap exceeds the limit, and 30s is the right number for a venue quoted
by sub-200ms market makers.

### What to look at once it is live

- `pass` and `took_s` are now on every loop log line. If `took_s` on a quote
  pass approaches 8s the fast cadence stops keeping rows inside the limit;
  `Tempo.observe_pass_duration` logs a warning and counts it as
  `passes_over_quote_budget`.
- **`surfaced` should stop being structurally zero during a window.** It has
  always been 0, and part of that was that nothing could survive 30 seconds. If
  it is still 0 after a full window with the fast cadence running, that is the
  honest no-edge result rather than an artefact — which is the first time that
  sentence has been true.

---

## HANDOFF (2026-08-08, earlier)

**State:** 935 tests, `dbt build` 11 nodes green, **both instances deployed and
verified**. The four items from the last handoff are done — sweep timing, the
window on the Board, Discord wiring, and the scored-ratio investigation, which
turned up a defect rather than a transient.

First live pass on the new image:

    dropped_game_started: 9          the in-play guard firing on real data
    clv_scored: 34                   up from 8 at the start of the session
    sweep decision: no sweep -- 24 of 16 credits spent since 10:00Z

The odds budget for today was already spent by the old scheduler (plus 6 on a
local smoke test), so **the first sweep the new timing chooses will be after
10:00Z on the 8th.** That is the thing to look at first: whether it lands
20–45 minutes before a cluster of kickoffs rather than wherever the process
restarted.

`clv_scored` answers the last handoff's item 4. The 100%-unscoreable reading was
a transient: closing lines only exist for games that have started, so early in a
run every joined row is a late one. 34 rows are now scored and the count is
climbing.

  demo  https://kalshi-cockpit-demo.fly.dev   (public, no credentials)
  live  https://kalshi-cockpit.fly.dev        (login: APP_AUTH_TOKEN)

### ~~Pick this up first — the window is 30 seconds, not 15 minutes~~

**Done 2026-08-08.** Fixes 1 and 2 below are both implemented; see the handoff
at the top of this file. Fix 3 — refresh the quote at order time — is still
open. The original write-up is kept because it is the clearest statement of the
problem.

The premise of the last handoff was wrong and the fix exposed it. **Two limits
bound the actionable window and the tighter one decides it:**

    MAX_ODDS_AGE_S         900   the sportsbook consensus
    MAX_KALSHI_QUOTE_AGE_S  30   the price you would actually pay
    loop interval          900   how often a row is written

A row is bettable for **thirty seconds after each pass**, then the server
refuses it. Two sweeps a day, so the tool is actionable for about a minute a
day, not half an hour. Every document in this repo said fifteen minutes,
including this one. The Board now states it rather than hiding it — expired rows
are struck through and labelled — but stating a problem is not fixing it.

Three candidate fixes, cheapest first. They compose; the first two together are
probably enough.

1. **Poll Kalshi fast while the window is open.** Kalshi REST is unmetered — the
   15-minute interval exists for the odds budget alone. A short pass (Kalshi
   quotes + re-price only, no sweep) every ~20s during the ~15 minutes after a
   sweep would cost nothing and keep a row inside its 30s limit for the whole
   window. `run_ingest_pass` already separates the odds leg, so this is mostly
   scheduler work.
2. **An unchanged row goes stale even though the market has not moved.**
   `persist_if_changed` deliberately does not rewrite a row whose ask and fair
   are unchanged — correct for the record, wrong for freshness, because
   `recommendation_freshness` measures from `created_ms`. A `last_confirmed_ms`
   column, updated on every pass that re-derives the same numbers, separates
   "this observation is old" from "this price is old". Needs a schema column and
   a change in `gate.recommendation_freshness`; the record semantics do not
   change.
3. **Refresh the quote at order time.** The real fix for execution, and the
   biggest: the ticket sheet reads a live Kalshi quote before confirming. Also
   closes the "the price moved between recording and ordering" gap that (2)
   leaves open.

Do not raise `MAX_KALSHI_QUOTE_AGE_S`. 30s is the correct number for a venue
quoted by sub-200ms market makers; the poll rate is what is wrong.

### And read this before touching the gate

The first live Discord digest (2026-08-08 02:39Z, one budget day) says:

    Surfaced 0   Suppressed 319   No edge 201   Scored on CLV 16 / 300

    stale_odds                                × 196
    stale_odds,suspicious_edge                ×  66
    stale_odds,too_few_books,no_market_width  ×  16
    too_few_books,no_market_width             ×  11

**`stale_odds` is on 278 of 319 suppressions — 87%.** `tasks/lessons.md` already
has the rule this breaks: *"before adding something to a rejection log, ask what
fraction of inputs will trigger it. If the answer is 'most of them', it is a
state, not an exception, and logging it as an exception destroys the log's value
as a diagnostic."* That has now happened. The suppression summary is one code
and a long tail, so it can no longer surface a miscalibrated rule — which is the
only reason it exists. Stale odds are the *normal* condition for 23.5 hours a
day; they are a state.

**And the gate is counting the wrong population.** `clustered_clv` pools every
row with a `clv_tenths`, with no filter on `suppressed_reason` or
`suggested_contracts`. So "16 / 300" is 16 games of CLV drawn overwhelmingly
from rows the strategy explicitly *rejected*. That measures the closing-line
behaviour of "any Kalshi market we happened to poll", not of this strategy.

The dilution is conservative — it drags a real edge toward zero rather than
inventing one — so nothing unsafe has happened. It is still the wrong number
under a label that says "our edge", and the 66 `suspicious_edge` rows are
exactly the population most likely to carry a *systematic* CLV in one direction,
which would move the pooled mean rather than merely blunt it. The repo's own
rule: **a pooled number is not a finding until the parts agree, and the
per-group view goes beside every aggregate.**

The sharp version, and the reason this is item 2 rather than item 5: **rows
become eligible only when they are actionable, and nothing has been actionable
yet.** Surfaced is 0 and has always been 0. So the two findings are one finding
— the 30-second window starves the only population the gate should be measuring,
while the counter reads 16 because it is counting a different one. Fixing the
window is what makes the gate's number mean anything.

Do not simply add `WHERE suggested_contracts > 0`. That is the correct
population and it is currently empty, so the gate would read 0/300 forever and
the change would look like a regression. Report both groups first —
actionable and rejected, side by side, with n for each — then decide which one
the floor counts.

### Then

- [x] ~~**Turn on Discord**~~ — **done 2026-08-08 02:41Z.** `DISCORD_WEBHOOK_URL`
  is a repo secret and a Fly secret; live reports
  `notifications_configured: true`; the workflow posted a real message and
  Discord replied 204. `tasks/PHONE.md` item 4 has the steps if it ever needs
  redoing — and note the GitHub mobile *app* is unreliable for workflows with
  inputs, so use the browser URL or ask me.
  **The bug that made this necessary:** the code read
  `DISCORD_BOT_TOKEN`/`DISCORD_CHANNEL_ID` while `PHONE.md` had said
  `DISCORD_WEBHOOK_URL` since it was written, so following the documented phone
  path would have configured nothing and reported nothing wrong.

- **Watch the first scheduled sweep**, some time after 10:00Z on the 8th. The
  log line to look for is `sweep decision: <sport> (scheduled): N game(s) from
  HH:MMZ, sweeping 45-15 min before first kickoff`. A `bootstrap` trigger there
  would mean no sportsbook fixtures were stored, which is a different problem.
- **Decide what to do with the in-play rows already in the live record.** They
  cannot be scored and they inflate the Ledger and the suppression summary.
  Deleting rows from the live evidence database is your call, not mine.

### What changed this session

- `backend/odds/timing.py` — clusters the day's kickoffs, scores each cluster by
  games covered, and fires a sweep only in a 30-minute window before one.
  Anchored on the **sportsbook's** kickoff; Kalshi's runs 3h late. Budget day
  rolls at 10:00Z, not UTC midnight. `plan_sweep` deleted, not left beside it.
- `/api/window` + `WindowBanner` — open/closed, time left, next sweep and why,
  credits left. Same planner as the runner, not a second implementation.
- `/api/board` splits `surfaced` from `expired`, recomputing both ages with the
  arithmetic the order endpoint uses.
- `backend/notify/alerts.py` — the caller `discord.py` never had. Dedupe lives
  in a `notifications` table so a restart cannot re-announce the slate.
- `runner` drops fixtures whose game has started. 36 of 104 rows on a live pass
  were in-play, with edges spanning −200 to +68 tenths against −39 to −18 for
  the pre-game rows on the same slate.
- `tests/test_has_callers.py` — the orphaned-code grep from `lessons.md`, run by
  CI and parsed with `ast` rather than matched as text.

### Running this in parallel

`docs/adr/0003-parallel-sessions-and-subagents.md` defines the file-ownership
lanes, the three integrator-only documents, and the shared state that no VCS
will protect — the odds budget (~16 credits/day, 6 a sweep), deploys, `data/`,
and the live instance. Workers use `Agent(isolation: "worktree")` and write
findings to `tasks/inbox/<lane>.md`.

**One addition, learned the hard way:** running `scripts/run_loop.py` locally
spends from the same monthly odds quota as the live instance, and neither
instance's `api_credits` table can see the other's. One local smoke test cost 6
of ~500 monthly credits. Reconciliation against `x-requests-remaining` catches
the drift after the fact; nothing prevents it.

### Still waiting on the user (both pre-authorised)

- **Fee-calibration trades** — four minimum-size orders at ~10c/30c/50c/80c in
  the Kalshi app. Clears a gate condition and retires the conservative fee hedge
  that suppresses essentially every longshot.
- **One combo price lookup** — `POST .../lookup`, no money, yields a measured
  same-game correlation.

---


Tick these off as you go. `tasks/todo.md` is the build log; this is the
actionable list.

State as of 2026-08-07: **653 tests passing**, `dbt build` green (10 nodes),
Docker image builds, cockpit renders clean at 320/390/430px, live WebSocket
verified against real markets.

---

## 1. Blocked on you

Four things I can't do without you. Each is a few minutes.
**All four are doable from your phone — see `tasks/PHONE.md` for the exact
taps.** Deployment used to need a laptop because `flyctl` has no mobile
client; `.github/workflows/deploy.yml` now runs it from a GitHub "Run workflow"
button.

- [x] ~~**Deploy the demo instance to Fly**~~ — **done 2026-08-07.**
      **https://kalshi-cockpit-demo.fly.dev** — one machine in `ord`, scales to
      zero, no credentials, no execution path. Deployed via the `Deploy`
      workflow (`gh workflow run Deploy -f instance=demo`); `FLY_API_TOKEN` is
      set as a repo secret. Verified: all five pages 200 with no error text over
      20 consecutive requests, `/api/health` reports `instance_mode=demo`, and
      `POST /api/orders` with a forged bearer answers **403**.
      **The first deploy was broken and looked fine.** It served "Backend
      unreachable" on 9 of 15 requests while `/api/health` stayed green — the
      API's SQLite connection was thread-bound and FastAPI runs the sync
      dependency and the sync endpoint on different threadpool workers. 758
      local tests and a local container run all missed it, because an idle
      threadpool reuses one worker. See `tasks/lessons.md`.
      Added `.github/workflows/ops.yml` (read-only `logs`/`status`/`machines`)
      because there was otherwise no way to read the deployed instance's logs —
      `flyctl` has no mobile client and needs a token nobody holds locally.
- [x] ~~**Deploy the live instance**~~ — **done 2026-08-07.**
      **https://kalshi-cockpit.fly.dev** — 1GB machine in `ord`, volume
      `cockpit_data`, never scales to zero. Gate verified locked: all four
      conditions unmet, `live_trading_enabled=false`, `POST /api/orders` 401s
      with and without a forged token.
      **The record is now growing.** First pass: 184 events discovered, 32
      linked, 3,612 odds quotes, 1,549 markets quoted, **128 recommendations
      recorded, 0 surfaced**. 64 markets awaiting a closing line.
      Two blockers were found and fixed by pre-flighting the image, neither
      findable by any test: the private-key materialisation was documented in
      `fly.live.toml` and never implemented, and `scripts/` was excluded from
      the image so `run_loop.py` — the entrypoint's own process — was absent
      from the filesystem.
- [ ] **Say yes/no to one combo price lookup.** `POST .../lookup` returns a
      Kalshi combo's price but *creates a market on the exchange* if that
      combination is new. No money moves; it's what the app does every time you
      tap a leg. I've left it refusing by default. This is the only way to get
      a real combo quote and back out an implied same-game correlation.
- [ ] **Decide on fee-calibration trades.** The fee model is still a hedge
      between two sources that disagree, and it can only be settled by real
      fills. Four minimum-size orders at ~10c/30c/50c/80c would close a
      year-old open question for a few dollars. This is real money, so it's
      your call.

- [ ] **`ODDS_API_KEY` is exposed — rotation deliberately deferred
      (2026-08-07).** A live run put the key into a terminal transcript: httpx
      logs full request URLs at INFO and The Odds API takes its key as a *query
      parameter*, so making a request was enough. Nothing logged it
      deliberately. **The cause is fixed** —
      `backend/logging_setup.py` redacts at the root logger and pins httpx to
      WARNING — but the leaked value is still valid.
      Judged not worth rotating for now: it is a free-tier key, 500
      credits/month, no money and no account access attached, and Kalshi's
      credentials were never exposed (they sign headers, not URLs). The residual
      risk is someone draining the quota, which would silently stop the record
      accumulating once the live instance is running. Revisit if the odds path
      is ever put on a paid tier.

---

## 1b. Found by deploying live

- [x] ~~**The live cockpit is fully public**~~ — **done 2026-08-07.** A
      shared-token login now gates every page and every proxied API route on
      the live instance; the demo stays open, because it is the portfolio link.

      **Gated in Next, not in the backend.** uvicorn binds `127.0.0.1:8000` and
      is never published — `/api/*` is reachable only because `next.config.ts`
      rewrites it, and middleware runs *before* rewrites. So one gate covers
      pages and API together, and server components keep calling the backend
      over loopback with no token to thread through.

      **The cookie is not the token.** `APP_AUTH_TOKEN` authorises
      `POST /api/orders`; the cookie carries `<expiry>.<HMAC(token, expiry)>`,
      so a stolen cookie costs read access and cannot be replayed as order
      authority. Tampered signatures and expired cookies both 401.

      **The switch is the token's presence**, not `INSTANCE_MODE` — the backend
      already refuses to boot in live mode without `APP_AUTH_TOKEN`, so
      "live but unauthenticated" is unreachable rather than merely unlikely.

      Three traps caught by testing the built image rather than the dev server:
      `/api/health` must stay public or Fly's check fails and the machine
      crash-loops; `process.env` in middleware had to be verified as
      *runtime*-read, since the same image must gate with the token set and not
      without; and `NextResponse.redirect` built its URL from the container's
      bind address, which would have sent the browser to
      `https://0.0.0.0:3000/ledger` — now a relative `Location`.

---

## 2. Fix before any real money

- [x] ~~**`clv.py` does not require the entry to precede the close**~~ — **done
      2026-08-07** (audit item 11). The closing line is read at
      `commence - horizon` and the runner records right up to kickoff, so at a
      1h horizon every recommendation made in the final hour was scored against
      a quote observed **before the decision existed**. Whether that flatters or
      punishes depends purely on which way the market drifted in between, so it
      put drift straight into the number built to detect edge — and the live
      instance starts scoring tonight, so it was contaminating a record that
      cannot be repaired retroactively.
      Now `created_ms <= observed_ms`, in `score_recommendations` *and* in
      `horizons_agree`, where it matters more: the 6h line is observed five
      hours earlier, so without it the two horizons compared different
      populations and part of the measured "drift" was just a change in which
      rows were counted. Excluded rows are counted
      (`skipped_entry_after_close`) and stay unscored rather than consumed, so
      they remain candidates for a shorter horizon.
      **The cost is stated, not hidden:** late recommendations go unscored at a
      given horizon, so the scored sample skews early.
      Verified by disabling (4 red). Adding it also turned 5 `test_scoring`
      tests red, because their fixtures created recommendations *after* the
      closing line — the rule catching unrealistic test timing on its first run.


- [x] ~~**`devig.market_width` reports `0.0` for a single book**~~ — **done
      2026-08-07** (audit item 10). "No disagreement measurable" rendered as
      "perfect agreement", so the least-evidenced consensus in the system passed
      the width suppression most easily. Now `Optional[float]`: `None` when
      fewer than two books contributed, and suppression **refuses** on it under
      a distinct `no_market_width` code — "books disagree" and "there was no
      second book to disagree with" call for different fixes.
      A measured `0.0` (two books quoting identically) still passes, and that
      pair is the test that matters: if `None` and `0.0` ever behave the same
      again, the states have been collapsed back together.
      **The larger finding underneath it:** sharp anchoring *causes* the
      single-book case. Three books agreeing to within 3.1 points, one of them
      sharp, yields `book_count = 1` and no measurable width — the anchoring
      discards the agreement evidence, which was the strongest signal the line
      was trustworthy. `usable_book_count` is now reported so the log can tell
      "only one book quotes this" from "five did and we kept the sharp one".
      Both guards verified by disabling. It had been masked by
      `min_book_count = 2` catching the same rows — a working guard hiding a
      broken one.

These are open defects from the 2026-08-07 audit. Full detail with file:line in
`tasks/audit-2026-08-07.md`. Ordered by how much they'd distort a money
decision.

- [x] ~~**The gate's `n` counts non-independent observations**~~ — **done
      2026-08-07.** Rows are now clustered by **game** (`kalshi_markets.
      event_ticker`, not ticker — a game's moneyline, spread and total resolve
      from one final score) and the standard error is the cluster-robust
      sandwich estimator. The 300 floor counts independent games; the Ledger
      shows games over the floor with the row count beside it, so the two
      screens cannot disagree. Two anchors chosen so a wrong implementation
      differs: singleton clusters reproduce the classical `s²/n` exactly, and
      duplicating every observation `k` times leaves the standard error
      bit-identical (the old estimator returned `stderr/√k`). Verified by
      disabling it two ways — clustering by row turned 5 tests red, dropping the
      finite-cluster correction turned the other 2 red. **Found on the way:**
      the test helper's `INSERT OR IGNORE INTO kalshi_markets` had been silently
      inserting nothing since the file was written (`first_seen_ms` is `NOT
      NULL`), so every gate test's join matched nothing. Both in
      `tasks/lessons.md`.
- [x] ~~**Continuous monitoring with no peeking correction**~~ — **done
      2026-08-07.** The noise guard now uses an always-valid bound (Robbins
      normal mixture, `m` tied to the 300-game floor) instead of two standard
      errors. Measured on 1,200 pure-noise sequences looked at 100 times each:
      the old rule fires on **13.7%**, the new one on **0%**. The cost is stated
      rather than buried — 3.66 standard errors at the floor instead of 2, about
      1.8x the effect size, and the gate's detail string reports the multiplier
      it used. Verified by disabling it (returning 2.0) and watching the
      simulation and the boundary test go red. Compounds with the clustering fix
      above: both corrections apply to the same statistic.
- [x] ~~**`margins.fit()` destroys the published standard deviation on a thin
      sample**~~ — **done 2026-08-07.** `fit` no longer overwrites `sd` from a
      sample too thin to estimate it: `MIN_GAMES_FOR_SD = 30`, deliberately
      separate from `MIN_GAMES_FOR_EMPIRICAL = 200` because "can this sample
      show me the shape?" and "can it tell me the width?" are different
      questions. Below it the league's `PUBLISHED_SD` is kept and
      `sd_is_measured` says so. The count alone was never sufficient — 300
      identical margins clears n≥30 and still estimates zero — so the check is
      on the estimate too. `_normal_survival` now **raises** on a non-positive
      width instead of returning 1.0/0.0, and a zero-width distribution cannot
      be constructed at all. Verified by restoring the old `max(1, n-1)`
      computation and watching 4 tests go red.
- [x] ~~**`backtest.beats_close` contradicts its own verdict**~~ — **done
      2026-08-07.** Both now derive from one `PairedComparison`, so there is no
      second path to disagree with; the invariant *"`beats_close is True` iff
      the verdict claims an edge"* is asserted across twelve seeds, because the
      two paths agreed whenever the gap was large and diverged exactly on the
      marginal cases. It also respects `min_games` now — a 50-game backtest
      could previously report `True` beside a verdict saying "No verdict".
      **Fixed audit item 14 in the same change:** the noise band used
      `sqrt(0.25/n)`, the null for a *single* proportion, where the gap is a
      difference of two accuracies on the *same* games. Now McNemar's
      `sqrt(b+c)/n`. The two coincide at exactly 25% discordance — which is why
      it looked right — and above it the old form is too narrow, 1.55x too small
      at 60% discordance, in the direction that manufactures significance.
      Verified by restoring each old implementation in turn.
- [x] ~~**Refresh the Kalshi quote at order time**~~ — **done 2026-08-08.**
      Item 3 of the three window fixes, and the last of them.
      `POST /api/orders` now re-reads `GET /markets/{ticker}` inside the
      request and **prices, sizes and caps the order against what comes back**;
      the recorded ask is provenance from that point on. `backend/kalshi/
      quotes.py`; wire format pinned by `tests/fixtures/market_single.json`,
      which stores the same ticker as `/events` returns it beside the
      single-market payload so a rename in one and not the other fails a test.
      Size is re-derived through `size_position` rather than against a new
      "how far may a price move" threshold, so a price that erased the edge
      returns zero contracts without anyone choosing a tolerance — and a
      *better* price still cannot exceed what the engine authorised.
      **Two things fell out of it that were not in the plan.** The route's
      portfolio-cap re-check became unreachable — the sizer now applies the same
      caps at the same instant against the same exposure, at a fee-inclusive
      price strictly above the one the re-check compared — so it was deleted
      rather than left looking like protection, with the caps now verified *at
      order time* instead. And `/api/board` had to change: with the quote
      re-read at order time, a stale recorded quote no longer stops an order, so
      splitting `surfaced`/`expired` on both clocks was striking through
      everything between 30s and 15 minutes after a pass — nearly the whole
      window — while the server would have sold it. `actionable` is now the odds
      clock and `price_is_current` is the Kalshi one; the card says "still
      bettable, but this price was read 4m ago and will move".
      17 guards verified by disabling; two were decoration on the first pass and
      both were real defects rather than missing tests.
- [x] ~~**Deci-cent asks can't fill.**~~ — **done 2026-08-08.** Checking it
      against Kalshi's write API turned a rounding fix into an endpoint
      migration, and found a second defect on the way. `docs/adr/0007`.
      **Prices now snap to the market's own `price_ranges`**, which Kalshi
      documents as the source of truth and explicitly tells clients not to infer
      from `price_level_structure`. No default grid: unreadable resolves to
      `None` at ingest and the order path refuses, because assuming whole cents
      is the bug.
      **The order goes to `POST /portfolio/events/orders` (V2)**, because the
      legacy path takes integer cents and cannot express 50.5c at all. It is
      also absent from Kalshi's current API reference — we had been posting to a
      deprecated endpoint for the whole project, invisibly, because nothing has
      ever posted. V2 quotes the **YES leg only** (`bid`/`ask`), so buying NO at
      `p` is selling YES at `1 - p`; `time_in_force` and
      `self_trade_prevention_type` are required and were absent.
      **The response defect found in the same change:** V2 emits no `status`
      field, and the old parser read `response["order"]["status"]` defaulting to
      `"resting"` — so every live order would have been recorded as resting with
      a null order id. Status is now derived from the fill counts and an
      unreadable response is `unrecognised_response`, which nothing can mistake
      for success.
      **Measured before believing the size of it:**
      `scripts/capture_price_grids.py` walked the live exchange —
      **1,426 game markets, all `linear_cent`.** So this costs no fills today;
      the "~25%" is a fact about all Kalshi markets, not about the ones we
      price. That does **not** mean sub-cent game markets don't exist (60 of
      2,145 on 2026-08-06, and a market's grid can change while it is open).
      6 guards verified by disabling; one of them was decoration on the first
      pass — a redundant bound check — and was deleted rather than kept.
      1,139 tests.
      **Dividend:** the V2 response carries `average_fee_paid` per contract, so
      the fee-calibration trades will read the true fee out of the order
      response itself rather than needing a `/portfolio/fills` poll.
- [x] ~~**Calibration panel leaks the number it suppresses**~~ — **done
      2026-08-07.** It rendered `implied` and `actual` on every row, and
      `gap = actual - implied`, so the suppressed finding sat one subtraction
      away in two adjacent columns. Censoring now happens in the mart
      (`actual_display`, `pnl_display`, `beat_close_display`, `clv_display`),
      so the presentation layer never receives an uncensored result; raw
      columns stay for analysis. `implied` and `n` stay visible because neither
      is a result. The dbt test that was meant to catch this was a tautology
      (`(A∧B) ∧ ¬(A∧B)`) and now recomputes from raw inputs; a source guard
      stops the frontend rebinding a raw column. Both verified by
      re-introducing the leak and watching them fail. 7 noise cells, 0
      reconstructable.
- [x] ~~**`mart_multiple_comparisons` undercounts tests**~~ — **done
      2026-08-07.** It counted `mart_calibration` alone while
      `mart_clv_by_bucket` and `mart_suppression_audit` ran their own
      two-standard-error tests uncounted. Measured on the seeded no-edge
      history: 8 tests instead of 11 moves p from **0.401 to 0.311** — a 29%
      improvement in apparent significance bought by forgetting to count. The
      model that exists to catch multiplicity was committing it.
      Findings are read from each mart's **own published conclusion** rather
      than recomputed, because a counter that disagrees with the thing it counts
      is worse than no counter. Both directions count in the suppression audit —
      "REVIEW" and "protective" each cleared the bar; only "neutral" did not.
      `generate_series(0, 200)` replaced with a series to `n_findings - 1`, so
      the sum can no longer truncate (which pushed p toward 1 — the bug that
      hides findings sat one edit from the bug that invents them).
      `tests_by_source` is a column now and renders under the verdict, so the
      total is checkable rather than asserted. A new dbt test names the three
      sources independently and fails if one is dropped — verified by dropping
      `suppression_audit` and watching it go red. `dbt build` 11 nodes green.
      **Deliberately still not counted:** `gate.py`'s noise guard, which is
      multiplicity along the *time* axis and already carries its own
      always-valid bound (folding it in would apply two corrections to one
      test), and `validate.py`, which tests the same observations these marts
      do.
- [x] ~~**Capture an Odds API fixture**~~ — **done 2026-08-07.** The capture
      already existed (`tests/fixtures/odds_mlb_h2h_spreads_totals.json`, 15
      events, 30 books) and **no test loaded it**, so the wire format was still
      pinned only by hand-written payloads. A capture nothing reads is
      decoration. Eight tests now parse the real bytes, including a drift test
      asserting every market key present is explicitly classified.
      **Closed the `h2h_lay` SEV 1 in the same change:** the API returns
      `h2h_lay` from Betfair and Matchbook without being asked, and `_parse`
      stored any key it was given. Lay quotes are now dropped at ingest, so no
      downstream grouping can pool them. Measured on the fixture: back
      `2.24/1.79` sums to 1.00509, lay `2.28/1.81` sums to 0.99108 — devig
      removes an overround, and an underround gives it nothing to remove.
- [x] ~~**Wire up the agent fleet.**~~ — **done 2026-08-08.**
      `backend/agents/review.py` is the seam; `run_pricing_pass` collects,
      reviews the surfaced rows in one batch, applies verdicts, then persists.
      All four decisions below were implemented as designed. The
      `test_has_callers` exception is closed and `apply_verdict` /
      `review_surfaced` are ordinary entries in `MUST_HAVE_CALLERS`.

      **It has run against the real Anthropic API, which the design note said
      would not be possible.** The first end-to-end run surfaced a row and the
      Skeptic *blocked* it — correctly, and for a reason no deterministic check
      could have reached: the test fixture's market title still read "Houston
      vs San Diego Winner?" under an event titled "Pittsburgh vs New York M",
      so the contract being priced was not the fixture matched against the
      book. That is a fixture bug rather than a finding about the venue, and it
      is exactly the failure class in the Skeptic's own docstring (FIXTURE
      MISMATCH). Fixed in the fixture; the point is that the layer works.

      **The design note's decision 3 was wrong and would have shipped broken.**
      `asyncio.run` at the seam raises whenever the pass runs inside a loop —
      which is always, in production, because `run_once` and `run_quote_pass`
      are coroutines calling the sync pass directly. It passes every sync test.
      The batch now runs on a dedicated thread with its own loop, with a test
      that calls the pass the way the scheduler does. See `tasks/lessons.md`.

      **Also found: the suite was making live API calls on any machine with the
      key in `.env`.** `backend/config.py` calls `load_dotenv()` at import, so
      `AgentConfig.from_env()` saw the key in every test. The same test called
      Claude locally and skipped the review in CI — green both times, asserting
      different things. An autouse fixture in `conftest.py` now removes it for
      the whole suite, and the reviewer is a **parameter** on `run_pricing_pass`
      so the one leg that costs money is visible in the signature.

      Seven guards verified by disabling: the thread seam, the contracts
      zeroing, the right-hand text split, the per-candidate failure boundary,
      review-before-persist, the verdict/row alignment check, and the conftest
      key removal (verified with a deliberately invalid key, which produced a
      real 401 from `api.anthropic.com` — proof the request had left the box).
      One of them caught a weak test of my own: it was passing through the
      exception path rather than a real verdict.

      **Still needs `ANTHROPIC_API_KEY` as a Fly secret** before it does
      anything on the live instance. Without it the fleet is unconfigured and
      every row comes back untouched, which is the live behaviour today.

      **The original design note, kept because it is the clearest statement of
      why each decision is what it is** — four decisions, each of which took a
      while to arrive at:

      1. **Run the Skeptic only on rows that would be surfaced**
         (`suggested_contracts > 0`, no suppression reason). Not on every
         candidate: a live pass builds ~100 rows and ~all of them have no edge,
         so reviewing them all would spend real money to be told "no" a hundred
         times. It also means the cost today is **zero calls**, because
         surfaced has always been 0.
      2. **Review before persisting, not after.** `apply_verdict` folds into
         `suppressed_reason`, and if the row is already on disk there is a
         window — one Anthropic round trip — in which the order endpoint would
         sell an unreviewed row. So the pass has to collect its
         recommendations, review the surfaced ones in one async batch, apply
         verdicts, and only then persist. That is the restructure: the loop
         currently builds and persists in the same breath.
      3. **`run_pricing_pass` is sync and `structured_call` is async.** Either
         make the pass async (touches every caller and test) or run the batch
         through `asyncio.run` at the one seam. Prefer the seam.
         *(The seam was right; `asyncio.run` was not — see above.)*
      4. **A Skeptic outage must not stop the pass.** `structured_call`
         already returns `None` on failure and `apply_verdict` already treats
         `None` as "no opinion", so this falls out — but assert it, because
         the alternative is a slate that silently stops being recorded.

      Needs `ANTHROPIC_API_KEY` as a Fly secret before it does anything on the
      live instance; it is in `.env` locally and `AgentConfig.from_env()`
      returns `None` without it, which degrades to no commentary rather than
      failing.

      ~~**And it cannot be verified against real data.**~~ — **partly wrong,
      and worth keeping for the correction.** The claim was that zero surfaced
      rows means zero verdicts, so the wiring could only be proven against
      fixtures. True of the *live record*, and false of the wiring: a captured
      slate with one number nudged (the NO bid on one market, which sets the
      derived YES ask) surfaces a row, and that row went to the real API and
      came back blocked. What remains unverified is narrower and still worth
      saying in the module — **no live instance has ever produced a surfaced
      row, so this path has never run on data the tool found by itself.**

~30 more findings are triaged in `tasks/audit-2026-08-07.md`.

- [x] ~~**The odds sweeps fire at the wrong time of day**~~ — **done 2026-08-08.**
      `backend/odds/timing.py`. See the handoff at the top of this file.
- [x] ~~**Surface the window on the Board**~~ — **done 2026-08-08.** And it
      immediately contradicted the page under it, which is how the 30-second
      window was found.
- [x] ~~**Wire up Discord**~~ — **done 2026-08-08.** `backend/notify/alerts.py`
      is the caller. Secrets still need setting on the live app.

---

## 3. Ready to build (no blockers)

- [x] ~~**The chain runner**~~ — **done 2026-08-07.** `backend/runner.py` joins
      discovery → odds sweep → link → devig → engine → `recommendations`.
      Nothing joined them before: `persist_recommendation` was called only by
      `seed_demo.py` and tests, `odds_snapshots` had a writer and no reader, and
      `fair_prices` had neither. **Verified against the live API**, not just
      fixtures: 175 events discovered, 19 linked, 2,746 odds quotes, 76
      recommendations recorded, **0 surfaced** — no edge, which is the expected
      and honest result. `scripts/run_chain.py` runs one pass; `--no-odds`
      spends no credits.
      Quotes ride on the `/events` payload (`yes_bid_dollars`,
      `yes_ask_size_fp`) rather than a second orderbook call — no extra request,
      and no second wire format to guess at.
      **Three defects found by running it live**, all in `tasks/lessons.md`:
      the credential leak above; Kalshi's `occurrence_datetime` running exactly
      3h late, which blocked *every* link; and the same offset then blocking
      every candidate at a second, unconnected limit in `suppression`.
      Still moneyline-only — spreads and totals are ingested and not yet priced.

- [x] ~~**Run it on a schedule**~~ — **done 2026-08-07.** `backend/scheduler.py`
      + `scripts/run_loop.py`. Jittered interval (default 900s), and it **dies
      loudly**: a transient failure is retried, but `MAX_CONSECUTIVE_FAILURES`
      in a row re-raises, killing the process, tripping `wait -n` in
      `entrypoint.sh` and taking the container down. A loop that swallowed its
      errors would leave the cockpit serving a record that had silently stopped
      growing, which reads as a quiet slate. Started by the entrypoint on
      **live only** — the demo holds no credentials. Smoke-tested live for two
      passes.
- [x] ~~**CLV scoring pass**~~ — **done 2026-08-07.** `backend/scoring.py`
      fetches closing lines from candlesticks and calls `score_recommendations`,
      which had existed since the evidence layer was built and had **never been
      called by anything** — so no row could ever be scored and the gate's
      counter was structurally pinned at zero.
      **The anchor is the sportsbook's commence time, not Kalshi's.** Kalshi's
      runs 3h late, so a "1h before close" reading against it lands *two hours
      into the game* — a quote from after the outcome is partly known, which
      would have produced a strong and entirely fake CLV signal in the one
      measurement this project exists to make. Lines are stored at both
      horizons for `horizons_agree`, but only the primary is scored, so
      `clv_tenths` is never a silent mixture. Four guards verified by disabling.

- [x] ~~**The record accumulates near-duplicate rows**~~ — **done 2026-08-07.**
      `engine.persist_if_changed` skips a row identical in derived ask *and*
      fair probability to the previous row for that `(ticker, side)`. Measured
      on a real two-pass run: 152 rows carried 77 distinct combinations, so half
      the record was repetition after two passes and would have been ~98% at 96
      passes a day.
      **Consecutive, not global** — a price moving 47 → 48 → 47 records three
      observations, because the return to 47 is a genuine second opportunity and
      global dedupe would thin the record exactly where the market is moving.
      Both directions verified by disabling: removing the check re-records an
      unchanged slate, and comparing against the oldest row instead of the
      latest swallows the return.
      Settled **before** live recording starts, deliberately: changing what gets
      recorded mid-stream puts two regimes in one dataset. The rule is part of
      the strategy config, so it mints a version and the record segments on it.

- [ ] **Is in-play betting viable? — measured, and the answer was NOT accepted.**
      `docs/adr/0006-in-play-scope.md` proposed closing it as out of scope;
      **Joe rejected that on 2026-08-08.** The question stays open. The
      measurements below were not disputed — they are kept in
      `docs/adr/0006-in-play-evidence.md` and should not be re-derived.

      **The three guards stay on while it is open**, and none of them came from
      the rejected ADR: the runner still drops started games, the order path
      still refuses one, and **no in-play row enters the evidence record**.
      Reopening the scope means designing the in-play regime — starting with
      what replaces the closing line — not letting rows in and separating the
      populations afterwards.

      All four questions were answered against the live exchange; **zero odds
      credits were spent** and no POST was made.

      **Joe was right about the product, and that is the part to say first.**
      Kalshi keeps the game market open in-play — `can_close_early: true`, and
      20 of 20 games measured (14 MLB, 6 WNBA) had a two-sided quote in *every*
      minute after the true start. In-play volume is **7.7x** (MLB) and
      **14.7x** (WNBA) the pre-game rate, and 98% of in-play minutes trade. The
      liquidity is real and it is where the action is.

      **It is out of scope because we cannot see it in time, not because it
      isn't there.** Two independent reasons, either sufficient:

      - **Cost.** Half-spread rises from 0.50c to 0.75c (MLB) / 0.89c (WNBA),
        and the mid moves ≥1c on ~half of in-play minutes against ~0.5%
        pre-game. Crossing plus 40s of unavoidable staleness is **1.34–2.28c
        against 0.38c of fee headroom** — 3.5x to 6x. Both leagues agree in
        direction and magnitude.
      - **Budget.** The Odds API refreshes in-play every 40s regardless of
        plan, so one league at the current market/region fan-out is ~7,020
        credits/day against a budget of 16. The realistic tier is $119/month,
        needing $31,316 of monthly notional to break even on the data bill
        alone.

      **And CLV has no in-play substitute that is the same statistic.**
      Settlement price is a win-rate measurement, which puts back the
      ~1,000-observation variance `clv.py` exists to avoid; entry-plus-delta is
      exactly what stale-quote picking optimises. Reopening needs a substitute
      argued *before* any row is recorded, plus a regime column, `closing_lines`
      keyed per recommendation rather than per `(ticker, horizon)`, and a gate
      that never pools the two regimes.

      Also from that work, unaffected by the rejection: `dropped_game_started`
      stays a **drop**, not a suppression — a
      suppression entry claims we considered it. Maker is *unreachable* rather
      than refuted: the headroom is 1.94 points there, but a resting order in a
      market moving ≥1c half the time is being adversely selected and this repo
      has **no cancel path at all**. Recorded as missing infrastructure, not as
      a measurement.

- [x] ~~**Verify what `occurrence_datetime` actually is.**~~ — **done
      2026-08-08, and it is a shifted start.** The expected-end story is
      refuted. `scripts/measure_occurrence_datetime.py`, capture in
      `tests/fixtures/occurrence_datetime_probe.json`, reasoning in
      `tasks/lessons.md`. Zero odds credits, no POST.
      **`match.linker` and `core.suppression` need no change** — the offset is a
      fixed +3h and is not game-length-dependent, so a fixed tolerance is right
      for a two-hour sport as much as a three-hour one. That was the worry and
      the answer is no.
      **The residual, which is real and new:** `KXMLBF5` carries **+5h** while
      `KXMLBF5SPREAD`, covering the identical five innings, carries +3h. The
      extra two hours are per-series data entry, not semantics — but the 4h
      tolerance is between the two, so the day this project prices a period
      series, every `KXMLBF5` market is dropped silently. Nothing in scope does
      today.

      What has to be answered before any of it is buildable, cheapest first:

      1. **Does Kalshi keep the game market open in-play, or list separate
         period markets?** One `/events` walk during a live game settles it —
         read `status` and `close_time` on a game whose kickoff has passed, and
         look for half/quarter series alongside `KX*GAME`. Free, no credentials
         beyond what is already exercised.
      2. **Can the odds side even follow?** The Odds API charges per call and
         the free tier is ~16 credits a day. In-play needs a refresh every
         minute or two per game, not twice a day, so this is a **paid-tier
         question, not a code question** — price it before building anything.
         If the answer is no, the honest result is "out of scope until the odds
         budget changes", recorded as such.
      3. **What replaces the closing line?** CLV is the only measurement this
         project trusts, and it anchors on a quote read before kickoff. An
         in-play bet has no such anchor — the natural substitute is the price
         at settlement or at the end of the period, and it is *not* obviously
         the same statistic. Nothing may enter the evidence record until this
         is settled, or the two populations pool into one number the way the
         in-play rows already nearly did.
      4. **Is the edge plausibly there?** In-play is where the venue's latency
         story is worst — this is the corner most contested by bots, and
         `tasks/lessons.md` already records that stale-quote picking lives at
         ~400ms. Expect the answer to be no, and design the check so a no is
         reportable.

      Do **not** simply remove the in-play drop to find out. That would put both
      populations in one record with nothing to tell them apart afterwards,
      which is the failure `tasks/lessons.md` names as "two populations in one
      record, told apart by dispersion".

- [ ] **Research screen** — Scout findings with sources and timestamps, model-
      vs-market disagreements, steam moves.
- [ ] **Playbook screen** — lessons, config versions, proposed changes awaiting
      your approval. The flywheel's UI.
- [x] ~~**Ticket bottom sheet** on the Board~~ — **done 2026-08-08.**
      `lane/frontend-wip` verified and merged. `TicketSheet.tsx`,
      `TicketProvider.tsx`, and the ticket trigger on the Board's live and
      expired cards; suppressed cards stay untappable, because a sheet with a
      permanently dead Confirm would suggest the decision is reversible.
      **It had never been rendered**, and no check in the repo could have
      rendered it: it mounts on a tap, so `check_mobile.py` never sees it, and
      it is `position: fixed`, so it cannot widen the `scrollWidth` that script
      decides on. `scripts/check_ticket_sheet.py` is the replacement — it taps,
      waits out the entrance animation, measures, presses Confirm, and measures
      the answer.
      **It fit 320/390/430 on the first render. The three defects were
      behavioural**, which is the part worth remembering: focus escaped to
      `<body>` the instant Confirm unmounted, so the trap opened exactly when
      the answer appeared; the line under a disabled Confirm asked for the
      token on rows whose consensus had aged out, where typing it changes
      nothing; and Close was a 59x26 target on a sheet that argues from thumbs.
      A fourth, same shape as the second: a 403 offered "Back" beside a
      sentence saying retrying will not help.
      Verified against three instances — live with a locked gate (**423, four
      conditions**), an expired-row instance (Confirm off, and now for the
      stated reason), and demo (**403**, the backend's own sentence verbatim).
      `--fail-order` renders the offline answer, the only way to see the
      two-button action bar at all; it fits 320 on one line each, which the
      component's own comment had flagged as the risk.
      **What it deliberately does not do:** no arithmetic on money, anywhere.
      Every figure is the server's, rendered as it arrived, and where a number
      is genuinely absent — the total before you confirm — it says so instead
      of multiplying. `worst_case_cost_dollars` on the board row would let that
      line be a number.
- [x] ~~**README** — the portfolio piece.~~ — **done 2026-08-08.** It already
      existed and had drifted, which is worse than missing: **"The WebSocket
      wire format is unverified"** had been false since 2026-08-07, and leaving
      it in hid the most instructive failure in the project behind an apology
      for not having looked. "Roughly 0.6 percentage points" sat two paragraphs
      below a table whose rows differ by 0.38. The test count and the demo
      slate were both stale.
      Added the live demo link (the thing a portfolio README most needs and did
      not have), a gate section carrying the two conditions whose earlier
      versions would have talked someone into a bet, the order path in the
      diagram, and the two browser checks that cannot run in CI.
      **Still missing, deliberately:** an architecture *diagram* rather than
      ASCII, and screenshots. Both want the deploy to be current first.
- [x] ~~**GitHub Actions** — tests, `dbt build`, and secret scanning on push.~~
      — **this line was wrong in both directions, 2026-08-08.** CI was built in
      the first commit and has been running pytest, `seed_demo` → `publish` →
      `dbt build`, and `next build` green throughout. This checklist said it did
      not exist.
      **And the part nobody was reading was red.** The secret scan failed on
      **36 consecutive pushes** since 2026-08-07 19:17Z, because it grepped for
      the *phrase* `BEGIN … PRIVATE KEY` and two files legitimately contain it —
      `docker/entrypoint.sh` validating a decoded key's format, and
      `tests/test_logging_redaction.py` proving the redactor strips a PEM block.
      It fired on the hygiene. A check that is always red carries no
      information: the run that finds a real key looks identical to the 36 that
      found a comment about one, and red becomes the resting state.
      Now matches **material**: a header alone on its line, a header followed by
      a base64 body, and a header immediately after a quote that then ends the
      line. That third one was added on merge — narrowing to material had
      dropped `KEY = """-----BEGIN RSA PRIVATE KEY-----`, which the broken
      pattern did catch. The `:!*.yml` exclusion is gone, so a key pasted into
      `warehouse/profiles.yml` is now scannable.
      **Verified by running the step, not by reading it:** extracted from the
      YAML and run under bash — clean tree exits 0, five planted shapes each
      exit 1 (own line, after a triple-quote in `.py`, escaped in `.json`,
      inside a `.yml`, and a tracked `.p12`). Random bodies, never key material.
      The exclusions are asserted against the two real files, so a future
      widening fails loudly instead of turning CI red again.
      Also note what gitleaks does **not** do: it scans only the commits in the
      push, never the tree and never history. A key committed last week and
      still present is invisible to it.

- [x] ~~**Three CI follow-ups**~~ — **done 2026-08-08.** `.gitignore` was
      missing `.pkcs8` as well as `.p12`. ruff is wired at 55 active rules with
      0 findings, chosen so it is green on the first push rather than red — its
      current default finds 513. Four actions bumped off the retiring Node
      runtime, the only one of the three that cannot be verified without a
      push. See the handoff at the top.
- [x] ~~**Write `orders` rows.**~~ — **done 2026-08-08.** `docs/adr/0008`. The
      description above was wrong about why it mattered: it does **not** make
      `max_exposure_dollars` bind, because every order is a dry run and dry runs
      commit nothing. What it does is make `client_order_id` durable before the
      request goes out, and join the CLV price to the executed one. It also
      turned up a second implementation of exposure. Handoff at the top.
- [x] ~~**A paper settlement path.**~~ — **done 2026-08-09.**
      `backend/settlement.py`, `docs/adr/0010`, schema v4. `settlements` gets
      its first writer, and `max_exposure_dollars` binds in production for the
      first time — on paper, scoped to the paper population so the first live
      order still sees a clean budget. That reverses ADR 0008's refusal, and
      only settlement makes it safe: exposure that can only ratchet up is a cap
      that can only close.
      **The capture came before the parser and the first finding would have
      broken everything silently:** `GET /markets?status=settled` returns
      markets whose `status` reads `finalized`, and `finalized` is rejected as
      a filter. `status == "settled"` matches zero markets forever and reports
      it as "nothing settled yet". Three more from the same 44 rows are in
      `tasks/lessons.md`.
      Paper P&L is walled off from the gate by construction, not by convention
      — `gate.py` does not read `settlements` and a test asserts it. The module
      docstring states what paper P&L does not establish.
      Eleven guards verified by disabling; one stayed green and was a real gap.
- [ ] **Make placement idempotent, before the gate opens.** Each request mints a
      fresh `client_order_id`, so two taps are two orders; the `UNIQUE`
      constraint stops a duplicate row and not a duplicate order. Costs nothing
      today because every order is a dry run. The shape: the client supplies the
      key, and the endpoint replays the recorded outcome instead of placing
      again. Deliberately not built yet — it is a new path on the money endpoint
      that nothing can exercise against live behaviour.
- [x] ~~**Serialise the exposure read with the insert.**~~ — **done
      2026-08-08.** `store.orders.reserve_order` writes the row and then checks
      the cap against the portfolio *including it*, in one transaction. The
      endpoint's own exposure read stays where it is and stays advisory: the
      sizer decides how big an order should be, the reservation decides whether
      the portfolio can hold it, and only the second has to be atomic.
      **The check runs after the insert, not before.** Reading and then
      deciding whether to write is the same race one level in; writing first
      and asking "what is the total now" makes the answer a fact rather than a
      prediction, and the rollback is exact — a refusal leaves nothing on disk,
      which matters because a stranded `pending` row counts as exposure by
      design.
      Verified by a real two-thread test on two connections, not `TestClient`,
      which drives the app through one portal and never makes the hop — the
      trap that made an earlier concurrency regression test in this repo pass
      against unfixed code.
      **And the docstring was wrong before it was tested.** It claimed
      `BEGIN IMMEDIATE` was what made it correct. Measured: a deferred `BEGIN`
      leaves the test green, because the insert is the first statement and
      takes the write lock anyway. What is load-bearing is the *order* of the
      two statements. `IMMEDIATE` stays for the next edit — the moment someone
      reads a daily-loss total before writing, deferred would read stale and
      fail on the upgrade — but it is documented as insurance rather than as
      the mechanism.
      **It still cannot fire in production**, and that is not a bug: dry runs
      are excluded from exposure, so the paper orders the running system places
      consume none of the cap. Asserted as a test rather than left in prose.

---

## 4. Verified working

So you know what's actually solid:

- **Live WebSocket** — 6/6 books populated from real MLB markets, derived-ask
  identity holds on every one, subscription registry complete, sequence gaps
  handled at the connection level.
- **Kalshi REST + auth** — signing verified against the live API; discovery
  pinned by drift tests over real captures.
- **Devig** — four methods, worst-of-four for money decisions, Shin verified
  not to degenerate.
- **Suppression + engine** — every candidate recorded, suppressed or not, with
  its config version.
- **Measurement** — noise guard under the null, pooling check, multiple-
  comparisons mart. On seeded no-edge data the dashboard correctly reads
  *"NOT EVIDENCE: 1 finding from 10 tests, 37% by chance."*
- **Builder** — parlays priced against devigged consensus; same-game legs
  refused rather than guessed; Wong teasers priced from bucketed empirical
  margins and correctly coming out negative at −120.
- **Combos** — 1,389 collections mapped; a combo quote inverts to an implied
  correlation.
- **Gate** — five conditions, one shared implementation, locked by default.
- **Cockpit** — Board, Builder, Dashboards, Ledger, Gate. Clean at 320px.

---

## The honest status

No bet has been placed and no edge has been demonstrated. The tool is built to
find out whether one exists, and every measurement in it is built to avoid
flattering the answer. The gate is locked and correctly reports that it has
zero scored recommendations, no verified fee model, and no evidence.

That's the expected state. The premise was always that Kalshi's advantage is
cost, not information — it lowers the break-even bar from 52.38% to ~52.00%
taker, and does not clear it for you.
