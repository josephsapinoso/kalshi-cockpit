# Todo

Session state. Read this first, alongside `tasks/lessons.md`.

Steps 1–11 are useful with **zero money at risk**. Step 12 is reachable only if
step 8 produces evidence.

---

## Done

### 1. Foundation ✅ (2026-08-06)

- [x] Repo scaffold — `backend/{kalshi,odds,core,model,match,store,analysis,agents,notify,api}`
- [x] `core/prices.py` — integer tenths, Decimal parsing, `complement`, probability bridge
- [x] `core/fees.py` — conservative max-of-models, `fee_candidates` for calibration
- [x] `kalshi/auth.py` — RSA-PSS signing, `signed_path` urlsplit idiom
- [x] `store/schema.sql` + `store/db.py` — full operational schema, version guard, derived asks
- [x] Tests: 76 passing. Two guards verified by disabling them and watching them fail
- [x] `.gitignore` + `.env.example` — secret hygiene from commit 1
- [x] `CLAUDE.md`, `tasks/lessons.md`, `pytest.ini`, `conftest.py`
- [x] venv on Python 3.11 + `requirements{,-dev}.txt`

---

### 2. Resolve the three day-one unknowns ✅ (2026-08-06)

- [x] **Query-string signing.** `scripts/verify_auth.py` settled it against the
      live API: signed **without** query → 200, **with** → 401. Kalshi signs the
      path only. `SIGN_QUERY_STRING = False`. **The handoff brief was wrong on
      this point** — see `tasks/lessons.md`.
- [x] **Full-vs-bare path.** Re-confirmed: full 200, bare 401.
- [x] **Game-level markets exist.** `scripts/capture_fixtures.py` walked 8,000
      events → 3,673 sports events. `KXMLBGAME` / `KXMLBSPREAD` / `KXMLBTOTAL`,
      `KXNFLGAME`, `KXNCAAFGAME`, `KXWNBAGAME` + spread + total, `KXCFLSPREAD`,
      many soccer leagues. Scope decision in `docs/adr/0001`.
- [x] Bonus: derived-ask identity verified on **2,145 real quotes, 0 violations**.
- [x] Bonus: matching key is `yes_sub_title` (plain team name), not ticker regex.
- [ ] Fee model: conservative hedge in place; calibration is task #4 and needs
      the order path, so it is not blocking.

---

## Next — the critical path

### 3. Kalshi ingest ✅ (2026-08-06)

- [x] `kalshi/rest.py` — async, shared client, min-interval rate limiter,
      429 + `Retry-After`, jittered retry, cursor pagination that **warns when
      truncated**. Raises rather than returning empty on failure.
- [x] `kalshi/orderbook.py` — book state with **sequence-gap detection**;
      raises `SequenceGap` and marks the book unquotable. Renamed level fields
      raise `MalformedBookMessage` naming what was tried, instead of yielding a
      silently empty book.
- [x] `kalshi/ws.py` — `orderbook_delta`, jittered reconnect, **application-level
      receive timeout**, per-ticker resubscribe on gap, `FeedDied` + `on_feed_down`
      so a dead feed is loud.
- [x] `kalshi/discovery.py` — classifies from `product_metadata`, commence time
      from `occurrence_datetime` (**not** `close_time`), sides from
      `yes_sub_title`. 24 priceable events across MLB/NFL/NCAAF/WNBA in the
      fixture, with moneyline + spread + total.
- [x] 162 tests passing, 1 skipped (WS fixture, below).

**Debt from this step:**

- [ ] **Capture a WebSocket fixture.** `tests/fixtures/ws_orderbook_payloads.json`
      does not exist, so the snapshot/delta field names in `orderbook.py`
      (`yes`/`no`, `price`/`delta`/`side`) are documentation-derived, not
      verified. The REST channel uses completely different names
      (`yes_bid_dollars`, `yes_bid_size_fp`), so assuming the two agree is
      exactly the previous project's mistake. The parser fails loudly on
      mismatch, which is correct but is not the same as being verified.
      `tests/test_orderbook.py::TestWireFormatIsUnverified` skips until it exists.
- [ ] Re-run `capture_fixtures.py` without the page cap to settle whether
      NBA/NHL game series exist (both out of season in August).

### 4. Odds ingest ✅ (2026-08-06)

- [x] `odds/client.py` — The Odds API v4, decimal odds, raw per-book storage,
      **two ages** (our fetch + the book's own `last_update`), implausible
      prices dropped loudly.
- [x] `odds/budget.py` — credit accounting reconciled against
      `x-requests-remaining`; **refuses** rather than warns; `plan_sweep`
      orders by soonest kickoff and truncates to budget.

### 5. Matching ✅ (2026-08-06)

- [x] `match/linker.py` — resolves team names **within a single candidate
      fixture** rather than against a global roster, so `"New York G"` only has
      to be distinguishable from `"Dallas"`. Requires a bijection; **ambiguity
      refuses**. Doubleheaders refuse rather than guess.
- [x] `match/aliases/{americanfootball_nfl,baseball_mlb}.yaml` — short by
      design; a long alias file means the deterministic rule has stopped working.
- [x] Unmatched work queue with actionable reasons.

### 6. Devig + EV + sizing ✅ (2026-08-06)

- [x] `core/devig.py` — all four methods, consensus devigs **per book before
      averaging**, sharp-book anchoring, market width reported.
- [x] `core/ev.py` — always on the derived ask, net of the settlement fee (one
      fee, not a round trip), fee amortised into the effective price.
- [x] `core/sizing.py` — quarter-Kelly, caps that report which one bound,
      **refuses on unreadable exposure**, min order size zeroes rather than
      rounds up.
- [x] Verified end-to-end on a real MLB line: fair 0.4597 vs 48c ask → no bet.

**Two bugs found and fixed in this step, both recorded in `tasks/lessons.md`:**
Shin was returning bit-identical multiplicative (a redundant special case
short-circuited the solver), and the "devig spread is 1–2 points" claim turned
out to be true only for lopsided lines — it is 0.18 points on an even MLB
moneyline, 2.03 on a longshot.

- [x] `core/suppression.py` — freshness (both sides), commence agreement,
      depth at the quoted price, book count, market width, **edge-within-
      method-noise**, and the **edge ceiling**. All checks run (no
      short-circuit); every failure is named.
- [x] `backend/engine.py` — the full chain into `recommendations` rows.
      Suppressed candidates are **stored and scored**, not dropped. Every row
      carries `strategy_config_version`. `suppression_summary()` turns the
      reject log into evidence.

**Backend analytical pipeline is complete: 321 tests passing, 1 skipped.**

The `edge_within_method_noise` check is worth knowing about — it falls directly
out of the measured devig spread and refuses any edge smaller than the
disagreement between the four methods. On a longshot that threshold is ~20
tenths; on an even line ~2.

### 7. Cockpit ✅ (2026-08-06)

- [x] `seed_demo.py` — deterministic, credential-free, network-free. Shaped
      honestly: 2 surfaced / 4 suppressed / 3 no-edge on a nine-fixture slate.
- [x] `api/routes.py` + `main.py` — Board, Market, Ledger, Gate, Suppression.
      Demo instance has **no reachable execution path**; live requires a token.
- [x] Next.js 16 cockpit, `globals.css` ported verbatim from `personal-website`
      plus `--positive` / `--negative`. Board, Ledger, Gate pages. Dark mode
      verified. Freshness is colour-coded.
- [x] Verified by running it and taking screenshots, which found two bugs the
      tests could not (see `tasks/lessons.md`).

- [ ] **Mobile layout visually unverified.** The window resize reported success
      but the viewport did not reflow, so the phone rendering has not actually
      been seen. Stacking uses standard `sm:grid-cols-2`, so low risk — but
      unconfirmed, and this is a phone-first tool.

### 8. Recording + CLV + validate.py ✅ (2026-08-06) — the evidence layer

- [x] `analysis/clv.py` — scores **every** recommendation, suppressed included,
      against Kalshi's own close read from candlesticks at a fixed horizon.
      `horizons_agree()` runs a second horizon: if the result moves, it was
      convergence, not edge.
- [x] `analysis/validate.py` — noise guard with standard error **under the
      null**, pooling check partitioning into supported / contradicted /
      **unpowered**, edge-vs-money sign consistency at a 3c tolerance, and a
      "what this does not establish" section on every report.
- [x] Self-check passes: 2,000 pure-noise observations across 8 powered tests
      produce zero findings. One bucket showed a 5.6-point gap and still
      printed `(noise)`.

**386 tests passing, 1 skipped.**

### 9. Deploy — in progress (2026-08-06)

- [x] `Dockerfile` — three stages (node build → python deps → slim runtime),
      non-root, health check probing **both** ports. One image, two deploys.
- [x] `docker/entrypoint.sh` — starts both processes, waits for the backend to
      be healthy before starting Next, and uses `wait -n` so that **either**
      process dying takes the container down. The naive `uvicorn & exec node`
      pattern leaves a half-dead container serving frozen prices that look live.
- [x] `fly.demo.toml` — no volume, no credentials, seeds on boot, scales to
      zero. `fly.live.toml` — volume, secrets, **never** scales to zero
      (a stopped machine records no closing lines, and candlesticks age out).
- [x] `.dockerignore` verified to exclude `.env`, keys, and databases.
- [x] `notify/discord.py` — opportunities, digests, and failure alerts.
      **No order button**, deliberately; the embed deep-links to the cockpit.
- [x] `README.md` — the portfolio piece.
- [x] `docs/adr/0002-two-deploys-one-image.md`.
- [x] **Image builds and runs.** 1.33GB. Verified end to end in a container:
      health endpoint responds, the Board renders with data.
- [x] **Supervision verified by killing the backend inside the container.**
      Logged `BACKEND exited -- every price is now stale`, container exited,
      port stopped answering. No frozen prices served.

Two bugs found by building and running it, both in `tasks/lessons.md`:
a missing `frontend/public` (hand-written scaffold, so no `create-next-app`
default), and `wait -n` under `#!/bin/sh` — dash rejects it, so the container
tore itself down milliseconds after starting. That one would have presented on
Fly as a crash loop with nothing in the logs pointing at the cause.

- [ ] Not deployed to Fly. Needs `fly launch` for each app, a volume for live,
      and secrets set out of band (including the RSA key, base64-encoded into a
      secret and materialised to tmpfs — never baked into the image, never on
      the volume where a snapshot would carry it).

### 10. Lakehouse ✅ (2026-08-07)

- [x] `store/publish.py` — dated, immutable Parquet snapshots. Empty tables are
      written with their **declared** schema (`PRAGMA table_info`) rather than
      skipped, so `read_parquet('.../fills/**')` does not fail the whole dbt
      build while "no fills yet" is the normal state.
- [x] `warehouse/` dbt project on DuckDB reading the lake directly — no load
      step, no second copy.
- [x] Marts: `mart_clv_by_bucket`, `mart_calibration`,
      `mart_suppression_audit`, `mart_fee_reconciliation`,
      **`mart_multiple_comparisons`**.
- [x] 4 singular dbt tests expressing the measurement guards, so loosening one
      turns `dbt build` red instead of quietly adding a number to a dashboard.
- [x] `dbt build` green: 5 models, 4 tests, 10 nodes.

**The finding from this step.** Seeded history contains no edge by
construction, yet the 73c calibration bucket came back significant at −20.8
points. Every per-cell guard was correct; ten cells were tested and ~1 in 20
clears by chance. `mart_multiple_comparisons` now reports
*"NOT EVIDENCE: 1 finding from 10 tests. Pure chance produces this or more 37%
of the time."* Two lessons recorded — that one, and the follow-on where the
mart computed the right p-value and then wrote its verdict from a different
calculation.

- [ ] Dashboards screen in the cockpit, reading the marts.

### 11a. The Quant ✅ (2026-08-07)

- [x] `model/elo.py` — per-league ratings with home advantage, rest, travel,
      MOV damping, between-season regression, and Platt calibration that
      **refuses to fit below 50 observations**. Per-league presets: MLB gets
      K=4 and no margin-of-victory (one of 162 games says little, and an
      11-run blowout says almost nothing more than a 2-run win); NCAAF
      regresses hardest.
- [x] `model/margins.py` — empirical margin distributions preserving the NFL
      key-number spikes at 3/7/10/14, because a normal approximation smooths
      them away and makes the Wong teaser edge invisible. `default_distribution`
      is explicitly flagged **not empirical** so nothing mistakes a published
      standard deviation for data.
- [x] `model/backtest.py` — **walk-forward only**, scored against the closing
      line rather than accuracy, with a binomial noise band on the
      disagreement gap.

**The verdict machinery is the deliverable.** On a synthetic run the model hit
79.9% accuracy — and on its own disagreements scored 81.6% against the market's
83.8%, a −2.2 point gap inside the ±3.1 noise band. Reported as
*"No demonstrated edge. Use as a research flag only."* Matching the market is
not an edge, and the module says so rather than quoting the accuracy.

### 11b. The agent fleet ✅ (2026-08-07)

`claude-opus-5`, structured outputs, shared house context under a cache
breakpoint. Every agent degrades to "no opinion" on failure or refusal — a
Claude outage must not stop the loop recording evidence.

- [x] **Skeptic** — argues a flagged edge is a bug; rejection is the default.
      Attacks four lines the deterministic checks cannot: market mismatch
      (regulation vs overtime), fixture mismatch (doubleheaders, reserve
      sides), stale information, and structural illiquidity. **It can only
      ever add a suppression reason, never clear one** — an agent able to
      un-suppress would be a way to argue past the checks.
- [x] **Scout** — `web_search_20260209`, sourced and timestamped findings,
      flags anything already priced in. An empty report is a valid answer.
- [x] **Historian** — reads the *marts*, not raw outcomes, and is told to read
      `mart_multiple_comparisons` first. Proposals are inert diffs stored
      `accepted_by_user = NULL`.

**The safety is in the schemas, not the prompts.** No agent schema has a field
that could carry a probability, price, edge, or stake, and
`recommended_action` is `Literal['reject','investigate','proceed_with_caution']`
— "bet" is unrepresentable, not merely discouraged. `validate_proposals()`
backs the Historian's prompt with a deterministic gate that rejects any
proposal below 100 observations or when the period's findings are consistent
with chance.

### 11c. The Builder (parlay / correlation / teaser) ✅ (2026-08-07)

- [x] `core/correlation.py` — `Relationship` classification, Gaussian copula
      joint probabilities, `_nearest_positive_definite` repair for
      hand-supplied correlations that cannot all be true. **`SAME_GAME` is
      deliberately absent from `DEFAULT_CORRELATION`** and raises
      `CorrelationRefused`: the sign depends on the specific pair, so any
      default is a guess wearing a number. Demo shows why — the same two legs
      price at −29.2% / −10.7% / +0.2% hold across ρ = +0.35 / 0 / −0.20.
- [x] `core/parlay.py` — values the **book's** offer against devigged consensus,
      leading with the hold because that number generalises. `kalshi_equivalent`
      prices the separate-contracts alternative and states plainly that it is a
      different bet (independent settlement, a fee per leg).
- [x] `core/teaser.py` — Wong screen + valuation, with **two refusals**:
      non-empirical distribution, and one that would be dragged more than
      `MAX_TRANSLATION_POINTS` onto the game.
- [x] `model/synthetic.py` — synthetic margins for demos and tests, guarded on
      mean, sd, and the derived favourite win rate.
- [x] `scripts/demo_builder.py` — end-to-end demonstration.
- [x] 530 tests passing, 1 skipped.

**Three real bugs found and fixed in this step, all of the same family — wrong
in a plausible direction, invisible in the output:**

1. **`probability_cover` had an inverted sign convention**, and its test asserted
   the inverted claim, so the suite was green while every spread and teaser
   price was backwards. Under the old code an eight-point favourite covered its
   own −7.5 line 86.7% of the time; the correct answer is 50% by definition.
2. **The synthetic generator matched the mean and not the variance**, making an
   eight-point favourite win 96.9% of games and printing a Wong teaser at
   **+28.4% EV**. Fixed generator gives 71.6% and −16.9%, which is the honest
   modern answer: Wong-shaped, key numbers crossed, still priced through at
   −120.
3. **A league-wide margin fit cannot be translated onto one game** — it moves the
   key numbers to 11 and 15 and is then worse than the normal curve it replaced.
   `fit_by_spread` + `translation_points` + the refusal in `build_leg`.

See `tasks/lessons.md` for all three.

---

### 11d. Dashboards + Builder screens ✅ (2026-08-07)

- [x] `analysis/marts.py` — reads the DuckDB marts. **`unavailable` never
      collapses into `empty`**: a warehouse that was never built and one with
      nothing to report both produce zero rows, and on a dashboard both read as
      "nothing to worry about". Missing warehouse raises `WarehouseMissing`;
      `/api/dashboards` returns 503 with the two commands that fix it.
- [x] `/api/builder/parlay` — same-game legs return **422 carrying the refusal
      text**, not a number. `/api/builder/wong-screen` for the teaser screen.
      Both available on the demo instance; they compute on supplied numbers and
      touch no credentials.
- [x] Dashboards screen — multiple-comparisons panel renders **first** and is
      required, because it is what qualifies everything below it. Verdict
      strings are rendered verbatim and never converted to numbers; `(noise)`
      is deliberately muted so it does not draw the eye like a result.
- [x] Builder screen — leg editor, live same-game detection with a ρ override
      field, the hold as the headline number, and the Kalshi-alternative
      comparison.
- [x] 553 tests passing, 1 skipped. `next build` clean.

**Verified visually on the seeded demo:** nine of ten calibration buckets render
`(noise)`; the tenth shows `-20.8` at 73c — the known false positive from
no-edge data — and the panel above it already reads *"NOT EVIDENCE: 1 finding
from 10 tests. Pure chance produces this or more 37.0% of the time."* That is
the guard chain working end to end on the exact case that fooled it before.

---

## Next

### 13. Mobile layout ✅ (2026-08-07)

- [x] `scripts/check_mobile.py` — drives headless Chrome over CDP,
      sets the viewport with `Emulation.setDeviceMetricsOverride` (the only
      method that actually reflows), reports `scrollWidth` against it, names
      every overflowing element, and **exits non-zero**. `--shots` captures
      through the same session, so image and measurement cannot disagree.
- [x] **Found and fixed a real regression:** adding the Builder and Data nav
      links pushed the link row 39px past a 390px viewport. That widened the
      *document*, so every page lost its right edge — body copy cut
      mid-sentence — while the nav itself still looked fine. The row now
      carries `min-w-0 overflow-x-auto` with `shrink-0` items, so a sixth link
      degrades to a scroll rather than clipping every page behind it.
- [x] Clean at **320 / 390 / 430** px: `scrollWidth == viewport` on all five
      pages. Verified visually at 390 too.

Two verification methods lied first, in opposite directions — see
`tasks/lessons.md`. Worth running this before any nav or table change.

### 12. Execution path ✅ (2026-08-07)

- [x] `kalshi/orders.py` — `api_price_cents` rounds a buy **down** and a sell
      **up**, and **raises rather than clamps** off the 1–99 grid. Clamping is
      what turned a self-announcing `no_price=-390` rejection into a live buy at
      99c in the predecessor. `OrderRequest` validates in its constructor, so an
      invalid one cannot exist. `client_order_id` generated before the request,
      so a timeout-then-retry cannot double-fill.
- [x] Dry run is **the same code path** — identical body, identical id,
      identical row, just no POST. Not a parallel implementation that can drift.
- [x] `gate.py` — five conditions, all must hold. One shared `evaluate_gate`
      used by the Gate screen *and* the order endpoint, replacing a second
      looser implementation in `routes.py` that never checked the noise guard.
- [x] `/api/orders` re-validates everything server-side: recommendation exists,
      not suppressed, freshness **recomputed from the clock**, gate open, size
      within caps, price on-grid. Client sends only an id and a size — ticker,
      side and price are read from the record, so a tampered client cannot buy
      a different market or a better price.
- [x] `scripts/demo_execution.py`; 38 execution tests.

Three guards verified by disabling them: clamping would have placed live 1c and
99c orders; a gate checking only `n>=300 and mean>0` opens on pure noise; and
reading the stored quote age lets a day-old recommendation pass a 30-second
freshness limit forever.

### 11e. Kalshi combos — a corrected premise ✅ (2026-08-07)

**The user pointed out that Kalshi has a combo feature. It does, and this
project had asserted otherwise since step 1.**

- [x] `kalshi/combos.py` — 1,389 collections, 13,806 legs. Same-game
      (`KXMVENBASINGLEGAME`, 8,622 legs), multi-game, cross-sport,
      cross-category. Wire key is `multivariate_contracts`, **not** the
      path-shaped `multivariate_event_collections` — the wrong one returns `[]`
      with no error.
- [x] `core.correlation.implied_correlation` — **the payoff.** A same-game combo
      quote is a joint probability, so it inverts to the measured correlation
      the module otherwise refuses to guess. Quote 0.36 on legs 0.60/0.50
      implies ρ = +0.39 against the 0.30 of naive multiplication.
- [x] Fixtures captured read-only; `lookup_combo` refuses without
      `allow_market_creation=True` because POST .../lookup creates a market.
- [x] 20 combo tests; corrected the premise in `parlay.py`, `rest.py`,
      `CLAUDE.md`, `tasks/lessons.md`.

**Unknown and needs the user:** no combo *price* has been fetched — that needs
one POST that creates a market (no money moves). Liquidity showed 0 of 13,806
legs quoted, but measured 6 August with the NBA finished and the NFL in
preseason, so it measures the calendar. Combo fee structure unverified.

### Older backlog

- [ ] Dry-run path, then confirmed one-click behind the gate
- [ ] Gate opens on: ≥300 scored recs **and** positive CLV surviving the noise
      guard **and** `fee_predicted == fee_actual` on every fill **and** fresh data

---

## Open questions

- **Fee calibration is deadlocked by design.** Reading the real fee needs a
  real fill; the live gate blocks real fills. Break it deliberately with a few
  minimum-size orders at spread-out prices (~10c/30c/50c/80c) — a few dollars
  to close a year-old TODO. See task #4 and `tasks/lessons.md`.
- **The conservative fee model is expensive at the extremes.** Model B charges
  a flat 1c/contract from ~9c to ~91c, which is 10% of stake at 10c and
  suppresses essentially every longshot. Correct under uncertainty, but it
  means the Board may show very little until calibration lands.
- **Odds free tier cannot support "live".** 500 credits/month ≈ 16 calls/day.
  The staleness gate will refuse most bets until the $30–59 tier. That is the
  designed behaviour, not a bug.
