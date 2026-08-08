# Next — your checklist

## HANDOFF (2026-08-07, end of session)

**State:** live is recording AND scoring. Fly trial cap lifted (card added), loop
reached pass 2, `clv_scored: 8` — the first CLV observations in the project's
history. 846 tests, `dbt build` 11 nodes green. 34 of 41 audit items closed
(status and the open six are in `tasks/audit-2026-08-07.md`).

  demo  https://kalshi-cockpit-demo.fly.dev   (public, no credentials)
  live  https://kalshi-cockpit.fly.dev        (login: APP_AUTH_TOKEN)

### Pick these up first

1. **The odds sweeps fire at the wrong time of day.** `MAX_ODDS_AGE_S = 900`, so
   a pick is actionable for only **15 minutes** after a sweep. The free tier
   affords ~2 sweeps/day, so the whole system is actionable for ~30 minutes a
   day — and nothing chooses *when*. `plan_sweep` picks which SPORT by soonest
   kickoff, but the sweep fires on the first pass with budget available, and
   budget resets at UTC midnight. Today's went at 19:32Z because that is when a
   deploy happened.
   **They should fire close to kickoff**, when lines are sharpest and the
   15-minute window overlaps with when a human would actually bet. This is the
   single biggest lever on whether the Board is ever useful.

2. **Surface the window on the Board.** The user cannot currently tell when a
   pick is live. Needs: when the last sweep ran, when the next is due, and
   whether the 15-minute window is open right now. Without it the Board is
   either empty or showing rows nobody can act on, with no way to tell which.

3. **Wire up Discord.** `backend/notify/discord.py` is imported by NOTHING —
   verified by grep; the only hits are the word "discordant" in `backtest.py`.
   The user expects alerts for: a surfaced opportunity, how past picks scored,
   and "the window is open now". Third instance of the code-with-no-caller
   pattern (after `score_recommendations` and the agent fleet), so check
   `DiscordNotifier`'s tests actually exercise a call path before trusting them.

4. **Check the scored ratio.** Tonight: `rows_joined: 56, scored: 8,
   skipped_entry_after_close: 48`. 86% unscoreable because today's many
   redeploys wrote rows after the 1h closing line was observed. In steady state
   most rows should precede T-1h. **If it is still ~86% after a full day, the
   scored sample skews early and 300 games takes far longer than three weeks.**

### Running this in parallel

`docs/adr/0003-parallel-sessions-and-subagents.md` defines the file-ownership
lanes, the three integrator-only documents, and the shared state that no VCS
will protect — the odds budget (~16 credits/day, 6 a sweep), deploys, `data/`,
and the live instance. Workers use `Agent(isolation: "worktree")` and write
findings to `tasks/inbox/<lane>.md`.

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
