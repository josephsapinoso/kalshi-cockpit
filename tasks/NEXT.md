# Next — your checklist

Tick these off as you go. `tasks/todo.md` is the build log; this is the
actionable list.

State as of 2026-08-07: **653 tests passing**, `dbt build` green (10 nodes),
Docker image builds, cockpit renders clean at 320/390/430px, live WebSocket
verified against real markets.

---

## 0. Do this first — rotate the Odds API key

- [ ] **Rotate `ODDS_API_KEY` at the-odds-api.com and update `.env`.** A live
      run on 2026-08-07 put the key into a terminal transcript: `httpx` logs
      full request URLs at INFO and The Odds API takes its key as a *query
      parameter*, so making a request was enough. Nothing logged it
      deliberately. The cause is fixed (`backend/logging_setup.py` redacts at
      the root logger, and pins httpx to WARNING), but the exposed key must be
      treated as compromised. See `tasks/lessons.md`.

---

## 1. Blocked on you

Four things I can't do without you. Each is a few minutes.
**All four are doable from your phone — see `tasks/PHONE.md` for the exact
taps.** Deployment used to need a laptop because `flyctl` has no mobile
client; `.github/workflows/deploy.yml` now runs it from a GitHub "Run workflow"
button.

- [ ] **Deploy the demo instance to Fly.** No credentials, no execution path,
      lowest risk — and it's the portfolio link. Needs your Fly account.
      `fly launch --config fly.demo.toml --no-deploy` then `fly deploy`.
- [ ] **Deploy the live instance.** Needs `fly secrets set` for
      `KALSHI_API_KEY`, the private key, `APP_AUTH_TOKEN`, `ODDS_API_KEY`,
      `DISCORD_WEBHOOK_URL`. Do the demo first.
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

**Set `ODDS_API_KEY` when convenient** — the odds path has never run live, so
every fair price so far is from seeded data.

---

## 2. Fix before any real money

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
- [ ] **Deci-cent asks can't fill.** Limit prices floor to whole cents, so a
      50.5c ask rests at 50c on the ~25% of markets that tick in half-cents.
      Safe for money, but it corrupts the paper record with orders that never
      fill. Needs checking against Kalshi's write API.
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
- [ ] **`mart_multiple_comparisons` undercounts tests** (only counts one mart's,
      ignores three other sources). Undercounting makes findings look *more*
      significant — the flattering direction.
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
- [ ] **Wire up the agent fleet.** `backend/agents/*` is imported by nothing —
      `skeptic.apply_verdict` is never called from the engine or the API. ~40
      green tests imply a safety layer that can't block anything.

~30 more findings are triaged in `tasks/audit-2026-08-07.md`.

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

- [ ] **Run it on a schedule.** The runner exists but nothing calls it
      repeatedly. This is what actually starts the three-week clock toward 300
      independent games. Needs a loop plus the live deploy.
- [ ] **CLV scoring pass.** `score_recommendations` exists and nothing invokes
      it; closing lines are never fetched from candlesticks, so no row will ever
      be scored. Without this the gate's counter stays at zero forever no matter
      how long the runner runs.

- [ ] **Research screen** — Scout findings with sources and timestamps, model-
      vs-market disagreements, steam moves.
- [ ] **Playbook screen** — lessons, config versions, proposed changes awaiting
      your approval. The flywheel's UI.
- [ ] **Ticket bottom sheet** on the Board — contracts, worst-case cost,
      predicted fee, resulting exposure. The order path behind it is built and
      gated.
- [ ] **README** — the portfolio piece. Architecture diagram, the OLTP→Parquet→
      DuckDB story, and an honest statement of what the tool does and does not
      establish.
- [ ] **GitHub Actions** — tests, `dbt build`, and secret scanning on push.
- [ ] **Write `orders` rows.** The endpoint currently dry-runs without
      persisting, so nothing accumulates exposure for the cap to read.

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
