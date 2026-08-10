# Start prompt — paste this to open the next session

Written 2026-08-10, overnight. The session that found **ADR 0021 quotes a
fixture number as a fact about the record**, inverted the caller detector that
had been green while nine modules sat orphaned, and wrote **ADR 0022**.

Everything below is the prompt. Paste it whole, or just say *"read start.md and
follow it"*.

---

Read `CLAUDE.md`, `tasks/NEXT.md` and `tasks/lessons.md` first. NEXT.md is the
actionable checklist; `todo.md` is just the build log. **The top section of
NEXT.md supersedes everything below it.**

## FIRST — the previous version of this file was WRONG, and check before you trust it

The version of `start.md` you would have read yesterday led with *"the refutation
ADR is the critical path"*. **It had already been written and committed.** A
session read it, believed it, and would have re-derived a finished document.

The lesson is cheap and general: **`start.md` is a snapshot, `git log` is the
record.** Before acting on any "still to do" in this file, run
`git log --oneline -20` and `ls docs/adr/`. Thirty seconds, and it caught a
whole wasted lane.

## State

`main` at **`d00430d`**, **pushed, in sync**. **1,964 tests**, ruff clean,
`next build` clean, tree clean.

**Everything is committed and UNDEPLOYED — live is unchanged**, and the
undeployed set still carries the **Next.js middleware-bypass security patch**
(`frontend/package.json` 16.2.10 → 16.2.11). Live still runs the vulnerable
version.

State the blast radius accurately rather than dismissing or inflating it:
`frontend/src/middleware.ts` **does** guard `/api/*` (reachable through
`next.config.ts` rewrites), so the bypass is not cosmetic — but the FastAPI
backend returns 401 on those routes **independently**, which is the control
CLAUDE.md actually relies on and which was verified directly on live. Defence in
depth with the **outer** layer down, not an open door. Deploying closes it.

**The five Dependabot alerts are parked deliberately. Do not raise them as new.**
Four `postcss` and one `sharp`, all in `frontend/package-lock.json`. There are
**two `postcss` copies in the tree and ours is already patched**:

```
@tailwindcss/postcss@4.3.3  ->  postcss@8.5.26   OURS -- above every alert range
next@16.2.11                ->  postcss@8.4.31   next's pin -- below all four
next@16.2.11                ->  sharp@0.34.5     needs >= 0.35.0
```

Two reasons it stays parked, the second stronger: **not reachable** (`sharp` is
only invoked by `next/image`, and the single `next/image` string in `src/` is
`middleware.ts`'s matcher *excluding* `_next/image`; `postcss` CVEs need
attacker-controlled CSS and we author every line of ours), and **build-time, not
request-time** — both run during `next build`, never on the instance serving a
request. Re-verify with
`gh api repos/josephsapinoso/kalshi-cockpit/dependabot/alerts --paginate` and
`npm ls postcss sharp` in `frontend/`. **Do not take an untested minor bump on
the frontend of a real-money instance to "finish the job".**

**You can read the live record programmatically.** The live `APP_AUTH_TOKEN` is
on the `APP_AUTH_TOKEN=` line of `.env` (gitignored). Form-POST `token` to
`/session`, keep the cookie, then GET. Whole-table pull: read `newest_id` from
page 0, pass it back as `max_id` on every page, assert
`len(set(ids)) == total`. **Do not re-derive this** — `scripts/run_joint_bound.py`
and `scripts/run_clean_shortfall.py` both have it written.

Six agents in `.claude/agents/`: **`partner`** (directs the fleet — *delegation
is its call*), **`measurement-skeptic`**, **`pre-registrar`**, **`sharp-bettor`**,
**`kalshi-platform`**, **`runtime-realist`**.

**Standing instructions from Joe, which override defaults:**

1. **Call `partner` first** and let it set the queue.
2. **Parallelise by default** — but **two concurrent lanes, never more.**
3. **`measurement-skeptic` audits anything before it enters the record**,
   especially good news. It earned its cost again overnight: it caught the
   drafter **over-claiming inside the paragraph that was correcting an
   over-claim** (see below).
4. **Deploys are BATCHED**, and Joe runs them:
   `! gh workflow run Deploy -f instance=live -f confirm_live=kalshi-cockpit`
5. **Don't ask permission to continue.** Do ask before money or a re-deploy.

## THE DECISION IS LIVE — ADR 0021 §8, and it is Joe's

The refutation is written (`docs/adr/0021-the-consensus-only-strategy-is-refuted.md`).
§8 lays out six options **unranked, with no recommendation made**, which was
deliberate. **`partner`'s position, stated as a position and not as the ADR's:
Option E first.**

| | |
|---|---|
| **A** | Stop the consensus-only line. Keep the recorder and the discipline. Costs nothing further. |
| **B** | Change the reference class — compare against a *wider* consensus. **Now properly testable at zero credits**, see below. |
| **C** | Invert the frame: Kalshi as the sharp reference against a softer venue. A genuinely new project (matching is the whole problem — 0.56% in the predecessor). |
| **D** | The maker path. ADR 0017 owns it, **proposed not accepted**, and needs the fee model resolved to mean anything. |
| **E** | **Resolve the fee model** — four real fills placed by hand. Already authorised. Small money, no code. |
| **F** | Keep recording, re-read at larger `n`. A **new registration**, never an amendment. |

**Why E first:** §7.4 says **every number in ADR 0021 moves if the fee model is
wrong**, and this account has **zero fills, ever**. It creates no edge; it is the
only thing that establishes whether the refutation is measuring what it thinks
it is. Run `scripts/capture_fills_fixture.py` **the moment trades fill, before
writing any parser.**

**Make the call in your own time. Nothing overnight assumed an answer.**

## What changed overnight

### 1. ADR 0021 §7.2 applied a fixture number to the record — annotated, not withdrawn

§7.2's *"discards a **median of 26 of 29** usable books"* is measured on
`tests/fixtures/odds_mlb_h2h_spreads_totals.json`, captured
**2026-08-07T13:49:22Z**. The record's odds observations run
**19:28:12Z → 08-09T23:35:18Z**. **0 of 1,564 rows** overlap; **minimum gap 5.647
hours.** Both directional checks err *toward* finding overlap; neither found any.

**The number is right and only its address is wrong** — `26 of 29` reproduces to
the digit through the production path on the fixture. The registration labelled
it correctly (`[MEASURED FROM DATA — tests/fixtures/…]`); **ADR 0021 dropped the
label.**

**Scope it honestly, because the exciting reading is the wrong one.** §7.2's
*argument* stands. What is unobserved is only the **magnitude**. §7.2 survives;
its number does not, and may be quoted only as *"measured on one MLB fixture
captured 5.65 hours before the record begins"* — never bare.

**Chased into all five homes it had reached:** `docs/adr/0021` (annotation),
`docs/adr/0019:522`, `tasks/lessons.md`, this file, `tasks/NEXT.md`, and the
registration (**Annotation B, appended** — the body carries no inline marker,
following Amendment A's precedent).

### 2. The skeptic caught the correction over-claiming — and it produced a field

The draft said sharp anchoring applies *"by construction"*. **False.** The code
is `selected = sharp or usable`: anchoring is *attempted* on every row, but
whether it **binds** is data. Where no sharp book quoted, the row was priced
against the **wide** consensus — the exact thing Option B proposes to test.

`anchored_on_sharp` **has been written on every row since the table existed and
read by nothing.** Without it §7.2's central claim is **unfalsifiable on the
record**. It is now on the `/api/ledger` payload, committed and undeployed.

### 3. Option B is testable at zero credits, and that is the newest fact here

`odds_snapshots` is **append-only and stores every book** (`schema.sql:189-207`,
one row per `(fetched_ms, bookmaker, market, outcome_name)` with
`price_decimal`). Sharp anchoring is a **read-time** filter
(`runner.py:658` → `devig.py:290-291`), **not a write-time discard.** The
schema comment states the intent verbatim: *"the moment we store only a
consensus we lose the ability to re-run with a different method."*

So the wide-consensus recompute over the **real** record needs **no Odds API
credits**. It needs one of: the `_serialise` widening in the next deploy
(committed, waiting), or one query on the volume.

**A fixture proxy for this was proposed and killed by `partner`** — running it
would have manufactured a second copy of the exact defect §7.2 was being
annotated for. Do not resurrect it.

### 4. The orphan count was six. It is NINE — ADR 0022

`tests/test_has_callers.py` was **inverted** from an opt-in allowlist to
**enumerate-and-classify**: an *unclassified* symbol now **fails**.

**All fifteen `MUST_HAVE_CALLERS` entries named symbols that already had
callers.** The list had never once been pointed at anything orphaned at the
time. Two structural holes, both in ADR 0022:

- **`scripts/` counted as a caller, but `.dockerignore` admits 2 of 34 scripts
  into the image.** Five of the nine were invisible for this reason alone. The
  clearest evidence: adding `build_leg` to the list turned the new shipping-caller
  check **red while the two older checks on the same symbol stayed green.**
- **Import counts as use.**

Classification — **`Tool`** (a human runs it, absence from the image is correct):
`backend/main.py`, `store/publish.py`, `analysis/joint_bound.py`,
`kalshi/combos.py`, `model/synthetic.py`. **`Quarantined`** (nobody runs it,
parked with a stated revival condition): `agents/scout.py`, `agents/historian.py`,
`model/elo.py`, `model/backtest.py`.

**Disposition is quarantine — do not wire, do not delete.** Wiring Scout and
Historian means live Anthropic calls, and the bill is held at zero by
`surfaced == 0`; turning on spend to decorate a refuted line is backwards.
Deletion is unrecoverable and Historian plausibly matters under Options B and F.
**`elo.py` specifically: do NOT wire it up** — the documented design was a
conjunction, and an AND-gate on an empty set leaves it empty.

Verified red in **three directions**, plus two permanent anti-vacuity guards —
green proves nothing here, since an enumeration that enumerates nothing passes
everything.

### 5. A landmine, recorded not fixed — and it is worse than it was briefed

`data/lake/` holds `recommendations` partitions named `dt=2026-08-0*` containing
**847 rows stamped 2025-07-23 → 2025-08-10** — demo seed data wearing the
record's directory names. `fair_prices` and `event_links` are **0 rows**.

**"Nothing reads it" is FALSE.** The dbt warehouse reads those partitions
directly (`stg_recommendations.sql:25`) and `/api/dashboards` reads the marts
built from them. **The reader is fully built.** The only thing between 2025 demo
data and a 2026-labelled screen is that `docker/entrypoint.sh` happens never to
invoke `publish` or `dbt build` — verified directly. **The safety is an accident
of the boot script, not a design.** ADR 0022 §6.

## The queue

1. **ADR 0020 — `stale_odds` reads a scrape clock.** Still the open ADR (the
   numbering runs 0019 → 0021 → 0022; **0020 stays reserved for it**).
   `odds_age_ms` comes from The Odds API `last_update`, a **scrape** timestamp:
   **320 of 320** book+event pairs quoting more than one priceable market share
   one stamp across every market they quote, and **27 of 30** books carry exactly
   one stamp across fifteen games. The false message is already fixed; the remedy
   has three live options.

   **`partner` deliberately deferred deciding this**, and the reason is worth
   keeping: the evidence that settles it — Joe's repeat poll — lands in hours,
   and choosing a remedy first inverts the order this repo keeps an agent to
   prevent. **Write it after the poll, not before.**

   **Quote 320 — not 440, not 335.** 120 pairs quote a single priceable market
   (vacuous); the 335 wrongly counted `h2h_lay`, which is never stored.
   Re-derive at zero credit cost with `scripts/census_odds_stamps.py`. And **do
   not say "it measures our polling cadence"** — the aggregator scrapes on its
   own schedule and we only sample it. The defensible claim is the weaker one:
   `last_update` is **not a per-line reprice timestamp**.

2. **Whatever Option Joe picks.** Do not start B, C, D or F speculatively — each
   is a different project with a different question, and §8 says so.

3. **The three queries neither agent could run** —
   `docs/measurements/2026-08-10-three-queries-the-agents-could-not-run.md`, with
   pre-stated expected outputs. **All six statements were executed against a
   seeded real schema before the document was committed**, which caught three
   defects that returned confident wrong numbers rather than errors — including a
   check reporting `unresolvable = 2 of 2` on a database where every row
   resolved. **All three need `flyctl`, which is a laptop job.** Q2 is one
   `_serialise` line from being phone-answerable; left undone deliberately, with
   the reason written down.

## Waiting on Joe

- **The deploy.** Batched and his alone:
  `! gh workflow run Deploy -f instance=live -f confirm_live=kalshi-cockpit`
  **Run `flyctl secrets list` first** — see the boot-failure warning below. It
  now carries: the Next.js middleware-bypass patch, and the `/api/ledger`
  widening (`market_width`, `book_count`, `books_used`, `anchored_on_sharp`)
  that converts §7.2 from extrapolation into an observation of the record.
- **24 Odds API credits** against 400/day. Four calls at **t0 / +60s / +300s /
  +900s**, checking whether `last_update` advances while prices are
  byte-identical. **The repeat poll is the primary purpose** — it converts the
  scrape-clock finding from inference to proof. **It must run during an active
  MLB slate** or the precondition returns UNRESOLVED — QUIET SLATE. The capture
  and analysis scripts are **already built and verified** (`f548bad`); no credit
  has been spent.
- **The §8 decision.** See above.

## BEFORE THE NEXT DEPLOY — a way to fail to boot

ADR 0019 §6 added `assert_odds_age_limits_agree`, called at startup by **both**
`create_app` and `run_loop`. It **raises** when
`SuppressionConfig.max_odds_age_ms` (hardcoded `900_000`) disagrees with
`MAX_ODDS_AGE_S`. Deliberate — the divergence it catches is silent, and a warning
nobody reads is not a control — but a mismatch now **stops the container instead
of quietly skewing the window.**

Checked and safe today: `fly.live.toml:128` = `"900"`, `.env.example:71` = `900`,
`fly.demo.toml` omits it and takes the `900` code default.

**Not checkable from this machine: whether a Fly *secret* sets `MAX_ODDS_AGE_S`.**
A secret overrides `[env]` invisibly. Run `flyctl secrets list` before deploying,
or the first symptom is a crash loop.

## Settled — do not re-derive or re-propose

- **The refutation is written.** ADR 0021. Do not rewrite it; annotate it.
- **One signal, not two.** `model_probability` is NULL on every row. Do not wire
  `elo.py` up.
- **The joint bound is dead on every population.** Branch Z was arithmetically
  unreachable before the data existed.
- **H3b is REFUTED** — `S_min = 2.0534` against `spread_at_min = 2.3191`, so
  *"the nearest is 0.21c short"* **is not writable**. Sign only: no "nearly
  clears", no "clearly misses", no multiple-of-noise figure, at any `n`. **Do not
  describe H3a as having answered H3b.**
- **The R3 ruling, stated answer-independently:** *a stop-the-line guard may only
  be predicated on a cut that at least one hypothesis's decision rule reads.*
  Grid D keeps its `DEGENERATE` banner and may not be cited in any conclusion.
- **Arming real trading is a code change** (ADR 0018).
- **There is no minimum order size.** `MIN_ORDER_CONTRACTS` was retired.
- **Kalshi's `occurrence_datetime` runs exactly 3 hours late**, recorded rather
  than corrected away.
- **The refutation ADR's denominator is `n_obs = 323` in `G = 59` clusters with a
  floor of `n_claims = 118`** — NOT the 29 scored games, which is the gate
  screen's CLV count and a different question. The honest claim is *"Kalshi is
  not mispriced relative to a consensus it may itself lead"*, **never** *"no edge
  exists at Kalshi"*.

## Traps

- **`start.md` is a snapshot; `git log` is the record.** See the top of this file.
- **On live the Anthropic bill is held at zero by `surfaced == 0`**, not by a
  missing key. The spend switches itself on precisely when the project starts
  working. **Set a spend limit.**
- **`$CLAUDE_JOB_DIR/tmp` is not empty at session start.** Give scratch files
  task-specific names and check `git log -1 --format=%s` after any scripted
  commit.
- **A committed registration must never be edited in place.** Amendments and
  annotations are **appended**; the body of this one carries no inline marker
  anywhere, and that precedent was followed rather than broken.
- **Two sessions in one working tree will fight over git.** Commit early, add by
  explicit path, **never `git add -A` while another session is live.** Two lanes
  ran concurrently overnight without colliding by owning disjoint file sets.
- **Every push publishes to the world immediately.** Screenshots of the live UI
  are the sharp edge. `.tmp_*` is gitignored.
- **Push protection is ON.** A rejected push is the guard working — stop, look,
  rotate if real. Do not bypass.
- **A `cancelled` CI run is not a broken build** — `ci.yml` has `concurrency`
  with `cancel-in-progress: true`. Judge CI by the run on your latest SHA.
- **`?event_ticker=` ignores `limit` entirely** on Kalshi.
- **Never run `run_chain.py` or `run_loop.py` without `--no-odds`.**

## Deferred, with reasons, so they are not rediscovered

- **`§S13` does not reproduce registration §10.** `run_clean_shortfall.py:1106`
  splits its **own `__doc__`** — 8 bullets against §10's 16. **The fix is to
  delete one of the two texts, not to test that they agree** (`lessons.md`, *a
  shared object cannot disagree with itself*): the harness should read §10 out of
  the registration at run time. Deferred because changing an instrument whose run
  is complete, without re-running it, is its own hazard.
- **The symbol-level orphan tail.** ADR 0022 §3.4 deliberately did **not**
  hand-write a table of it — that would reproduce the opt-in defect one level
  down. The symbol half got two *derived* checks instead, and all 15 entries
  pass, so it starts as a ratchet rather than a debt.
- **The `data/lake/` demo-data landmine.** Recorded, not fixed. ADR 0022 §6.
- **The vector-collapse remedy** — probably a no-op; the duplicate groups are
  recreational books discarded *before* the consensus exists.
- **`runner.py:989`** still passes `suppression.max_odds_age_ms` into the odds
  sweep. Safe *because of* the §6 assertion, not independently of it.
