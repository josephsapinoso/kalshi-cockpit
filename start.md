# Start prompt — paste this to open the next session

Written 2026-08-10, ~03:00Z. The session that got live read access, answered D1,
audited two of its own claims into retractions, and ended with a plan to
**finish the project rather than continue it.**

Everything below is the prompt. Paste it whole, or just say *"read start.md and
follow it"*.

---

Read `CLAUDE.md`, `tasks/NEXT.md` and `tasks/lessons.md` first. NEXT.md is the
actionable checklist; `todo.md` is just the build log. **The top section of
NEXT.md supersedes everything below it.**

## State

`main` is at `1ada3e6`, pushed, CI green on all three jobs. **1,776 tests**,
ruff clean, `next build` clean, tree clean, no worktrees.

**LIVE IS DEPLOYED on `ec53ba9`**, verified independently rather than by the
workflow's assertions. `main` is **6 commits ahead** — five docs and one
built-not-shipped feature. No migration ran: `SCHEMA_VERSION` 6 on both, and
`schema.sql`/`db.py` byte-identical.

    live   instance_mode=live, live_trading_enabled=false, retired_settings_set=[]
           /api/results /api/gate /api/ledger /api/orders all 401 unauthenticated
           forged bearer 401; six pages 307 -> /login

**You can read the live record programmatically.** Joe put the live
`APP_AUTH_TOKEN` on **line 68 of `.env`** (gitignored). Form-POST `token` to
`/session`, get a cookie, then GET any route. It works — do not re-derive this.

Six agents in `.claude/agents/`: **`partner`** (directs the fleet — *delegation
is its call*), **`measurement-skeptic`**, **`pre-registrar`**, **`sharp-bettor`**,
**`kalshi-platform`**, **`runtime-realist`**.

**Standing instructions from Joe, which override defaults:**

1. **Call `partner` first** and let it set the queue.
2. **Parallelise by default** — but budget the API session limit as a real
   constraint. Four concurrent lanes burned it mid-flight last session.
3. **`measurement-skeptic` audits anything before it enters the record**,
   especially good news.
4. **Deploys are BATCHED.** Do not ship one small route at a time — Joe was
   paying a wait-and-verify cycle for each. Three items are queued.
5. **Don't ask permission to continue.** Do ask before money or a re-deploy.

## THE PLAN — read this before planning anything

The project is close to a **delivered answer**, and the answer is probably *no*.
That is a result, not a failure. `CLAUDE.md` says the product is the record.

**Run one joint bound:**

> With every conservative choice this project makes set simultaneously to its
> most generous alternative — the loosest of four devig methods, the cheaper fee
> model, and the maker basis — **how many rows are actionable?**

If it returns 0, **the central question is closed** and per-knob attribution is a
footnote. Decompose per knob *only* conditional on a non-zero count.

**Why this and not more measurement.** A null at n=29 games is *provisional* —
someone will always ask whether more data would have changed it. The joint bound
is **not provisional**: if the ask sits above the most generous fair under the
cheapest fee on every row, then no method choice, no fee resolution and no
further sample of the same kind could have produced an actionable row. It
converts *"we didn't find one"* into *"one could not have been found here"*, and
**no future data can reverse it.** It is also deterministic, so it carries **no
alpha** — which matters against P(some cell clears from nothing) = **0.9993**.

**Then stop.** Refutation ADR, correct CLAUDE.md's premise section to what was
found, close every accumulation-justified line. Leave the recorder running
because it costs nothing, with no work planned against it.

**One line survives and rides free inside the same bound: the maker basis.**
Verified — at 50c the maker fee is exactly half the taker fee ($0.0100 vs
$0.0200); headroom **1.94 points against 0.38, i.e. 5.1x.** The only quantity
here where a positive finding is not power-precluded on its face. No mass in
18c–82c and it closes with everything else.

## Where the numbers stand, read from live

    populations   actionable 0    no_edge 614    suppressed 915   total 1529
    horizons      "0" 532    "1" 569    unscored 428
    per game      actionable 0g/0r   no_edge 20g/279r   suppressed 25g/253r
                  29 scored games, none actionable
    outcomes      recorded 1601 (no 1039, yes 562), pending 0, abandoned 0,
                  unreadable 219

**`actionable` has been 0 for the entire life of the record.** `abandoned 0`
means no outcome has ever been lost. A consistency check that holds:
279 + 253 = 532 = the horizon-`"0"` row count.

## The deploy bundle — three items, and Joe runs it

1. **`offset` on `/api/ledger`** — a prerequisite, not a convenience. The ledger
   returns the newest 1,000 of 1,529, and `persist_if_changed` writes only on
   price movement, so rows-per-game tracks **volatility** — the slice is
   weighted toward volatile wide-disagreement games, which is the direction that
   **inflates an apparent edge.**
2. **The four per-method probabilities on the ledger payload**, joined via
   `recommendations.fair_price_id`. Raw data out; recount in a tested local
   module, because batched deploys make baked-in analysis cost a release to
   re-cut.
3. **`unreadable_examples`** — already built, `4473641`.

**Do NOT expose `kalshi_markets.result`.** No reader, calibration is dead at this
`n`, and a field added for a consumer that does not exist is how this repo got
four built-never-called modules. The data accrues free; the analysis waits for
`n`.

Joe deploys — **the classifier blocks `gh workflow run Deploy` from a tool call,
and routing around it via the browser is off-limits.** He runs:
`! gh workflow run Deploy -f instance=live -f confirm_live=kalshi-cockpit`

## READ THIS — three claims died last session, two of them mine

**Every one ran in the flattering direction.** That is not coincidence: a
flattering reading terminates the search early because it feels like an answer.

- **"`no_edge` may be a sizing artifact" — RETRACTED.** Measured: at the $1,000
  reference profile the smallest edge that sizes to one contract is 0.6–1.0
  *tenths of a cent*. The floor is nil, so every unsuppressed row genuinely has
  a non-positive edge. There is no hidden population.
- **"Calibration separates sharp-Kalshi from our-fair-too-low" — REFUTED.**
  `4p(1-p)/gap²` at two SE: the 0.38-point headroom needs **69,252 games**, 2.0
  points needs 2,500, a gross 5-point miss needs 400. The record has **29**.
  Underpowered by four orders of magnitude, permanently.
- **"The devig conservatism eats 3–5x the headroom" — INVERTED.** The "1–2
  points" was the *longshot* end. `core/suppression.py:217-220`: **0.18 points
  at 50c, 2.03 at a longshot**, and the guard's cost is about half the spread —
  so **~0.24x** the headroom where this strategy trades.

The two lessons are in `tasks/lessons.md`: **"unblocked is a scheduling
property, not an evidentiary one"** and **"a number quoted from your own
project's prose is an assumed number until you have found the code behind it."**

## Settled — do not re-derive or re-propose

- **CLAUDE.md now says one signal, not two.** `model_probability` is NULL on
  every row and no decision reads it; `elo.py` has no production caller. **Do
  not wire it up to make the documentation true** — the documented design was a
  *conjunction*, and adding an AND-gate to an empty set leaves it empty, so the
  missing half cannot explain `actionable = 0` away. Arithmetic, not judgement.
- **Arming real trading is a code change** (ADR 0018). `ORDERS_ARE_DRY_RUNS` is a
  module constant with no env read. `LIVE_TRADING_ENABLED` moves no money.
- **The account has zero fills, ever.** The envelope is measured; every field
  *inside* a fill is unobserved, including whether the fee is called `fee`. Run
  `scripts/capture_fills_fixture.py` the moment trades fill, **before** writing
  any parser.
- **The $5 buys less than claimed.** The two fee models agree at 163 of 999
  prices — including **exactly 50.0c** — and differ by exactly 1c/contract
  elsewhere. It is quantised to a whole cent, not a smooth 0.38 points.
- **The 219 unreadable — deferred, not investigated.** 802 settled markets parse
  100% readable; the "Kalshi finalizes before publishing `result`" hypothesis is
  **refuted**. `abandoned_total: 0` makes this 12% missing from a *future*
  sample, not a leak.

## Traps from this session specifically

- **Subagent lanes die mid-edit.** Four were killed at once by a session limit;
  one had already edited three tracked files and added a test. **`git status`
  first** after any lane failure, review each partial diff on its merits, and
  expect to finish by hand — the partial work was good and discarding it would
  have cost more.
- **"Read-only" is not a scope boundary.** Name the environment as its own
  sentence and explicitly offer *"stop and say so"*, or an agent's only path to
  a complete answer runs through production.
- **On live, the Anthropic bill is held at zero by `surfaced == 0`, not by the
  absence of a key** — `agent_fleet_configured: true`. The spend switches itself
  on precisely when the project starts working. Set a spend limit.
- **Do not persist `binding_constraint`** the cheap way: it writes into
  `suppressed_reason`, which is half the `actionable` predicate. That changes
  what the gate counts to make a measurement easier.
- **`?event_ticker=` ignores `limit` entirely** on Kalshi.
- **Never run `run_chain.py` or `run_loop.py` without `--no-odds`.**

## The decision that is Joe's, and its timing

If the joint bound returns 0, **continuing is not a smaller version of this
project — it is a different one**: liquidity provision, or Kalshi as the sharp
reference against another venue. That deserves a fresh decision with a clean
record in hand, not a drift out of an ambiguous one.

**Make that call after the refutation is written.** Cost to get there: the
three-item bundle, one deterministic module, one skeptic pass. **Days, and no
money.**
