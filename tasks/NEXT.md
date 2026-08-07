# Next — your checklist

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

- [ ] **The gate's `n` counts non-independent observations.** Every engine pass
      writes a fresh row per market, and all rows for one ticker score against
      *one* closing line. That understates the standard error by roughly √k, so
      the 300-observation floor is reachable from ~10 markets polled 30 times.
      **This is the single largest lever on whether the money gate opens.**
- [ ] **Continuous monitoring with no peeking correction.** The gate re-runs on
      every request against a growing database, with no pre-registered `n`.
      Under a true zero-edge process, the chance the running z-score *ever*
      crosses 2 tends to 1. Needs an always-valid bound or a fixed cadence.
- [ ] **`margins.fit()` destroys the published standard deviation on a thin
      sample.** With n=1 it yields `sd = 0`, which makes a cover probability
      exactly 1.0 or 0.0 — a certainty, which in Kelly sizing is an unbounded
      bet.
- [ ] **`backtest.beats_close` contradicts its own verdict** — a bare boolean
      with no noise guard sitting beside a verdict that correctly says "inside
      the noise band."
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
- [ ] **Capture an Odds API fixture.** The wire format that supplies every fair
      probability is pinned only by a hand-written payload. One credit buys one.
      This is the exact gap that made the WebSocket path dead for weeks.
- [ ] **Wire up the agent fleet.** `backend/agents/*` is imported by nothing —
      `skeptic.apply_verdict` is never called from the engine or the API. ~40
      green tests imply a safety layer that can't block anything.

~30 more findings are triaged in `tasks/audit-2026-08-07.md`.

---

## 3. Ready to build (no blockers)

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
