# Start prompt — paste this to open the next session

Written 2026-08-09, ~22:40Z. The session that ran seven lanes in parallel, had
four of its own documents audited, deployed live twice, and then read a number
off the deployed instance that reframes the project: **`actionable` has been 0
for the entire life of the record.**

Everything below is the prompt. Paste it whole, or just say *"read start.md and
follow it"*.

---

Read CLAUDE.md, tasks/NEXT.md and tasks/lessons.md first. NEXT.md is the
actionable checklist; todo.md is just the build log.

## State

`main` is at `1002028`, pushed, **CI green on all three jobs**. 1,753 tests,
ruff clean, `next build` clean, tree clean, no worktrees, no stale branches.

**LIVE IS DEPLOYED on `1002028`** (~22:35Z) and verified independently rather
than by the workflow's own assertions. Demo went first as the canary.

    live   instance_mode=live, live_trading_enabled=false,
           retired_settings_set=[], six pages 307 -> /login,
           /api/orders 401 with and without a forged bearer,
           /api/ledger and /api/gate 401 unauthenticated

No migration ran, and that was checked before triggering: `SCHEMA_VERSION` is 6
on both commits and every `schema.sql` change since is comment text.

Six agents in `.claude/agents/`: **`partner`** (directs the fleet — *delegation
is its call*), **`measurement-skeptic`**, **`pre-registrar`**, **`sharp-bettor`**,
**`kalshi-platform`**, **`runtime-realist`**.

**Standing instructions from Joe, which override defaults:**

1. **Call `partner` first** and let it set the queue.
2. **Parallelise by default** — worktree lanes. Seven ran this session.
3. **`measurement-skeptic` audits anything before it enters the record**,
   especially good news.
4. **Before shipping anything that runs at boot on live, ask what clears it if
   it fails.** flyctl is a laptop job; Joe works from a phone.
5. **Don't ask permission to continue.** Do ask before money or a re-deploy.

## THE FINDING — read this before planning anything

`/api/gate` now exposes `populations`, which nothing could reach before. Over
the **whole table, at every horizon, since the record began**:

    actionable      0
    no_edge       594
    suppressed    868
    total rows   1462

    predicate: actionable = suppressed_reason IS NULL AND reference_contracts > 0

**Zero rows, ever, in 1,462.** The strategy has never once produced a row it
would have bet at the fixed $1,000 reference bankroll. **G = 0 against a floor
of 300, and the numerator has never been anything else.**

With ADR 0016 — a 1,200-game backfill has a 95% ceiling of 35 — **the gate is
not reachable by accumulating more of the same.** That is CLAUDE.md's premise
returning the answer it warned was likely. **Do not engineer around it.**
Relaxing a threshold to make `actionable` non-zero manufactures the evidence the
gate exists to demand.

The live question is no longer *does the strategy have CLV*. It is **is the bar
right, or is the strategy?** Two cheap things bear on it, in NEXT.md as items 1
and 2.

## The record is 39% legacy, and the ledger's default view is a slice

    horizons:  "0": 476   "1": 569   unscored: 417     total: 1462

569 rows carry the 1.0h anchor that v5 tags and never re-scores. Any CLV number
that does not filter the horizon mixes two regimes at 2.2x, **biased upward**
because a 1h line is the weaker benchmark. And `total: 1462` against
`limit: 1000` means the default window is the newest rows, size-biased toward
games that generated many rows.

**Three URLs, from a phone, after signing in once at `/login`:**
`/api/ledger?limit=1` for `horizons`; `/api/gate` for `populations`;
`/api/ledger?limit=1000` for `total` vs `returned`.

## READ THIS — the pattern behind every correction, four sessions running

Four documents were audited. **The arithmetic reproduced exactly in every one** —
power tables, Wilson intervals, fee rows — and the conclusions were still wrong,
because the numbers from *outside* the code were assumed and unlabelled.

The specimen: a correct covariance identity, a correct multiplication, and a
spurious-slope estimate of **0.16 that was off by ~230x**, because one factor was
a guess. It was called "the largest finding in this document" and made a
*blocking* prerequisite. A measurement of the adjacent quantity sat unused in
`docs/adr/0006`.

Internal consistency cannot catch this — the error is upstream of every operation
performed, and surviving the check makes a document read as *more* rigorous.

**Label every number computed from code / measured from data / assumed, and count
the third kind.** Two corollaries: **a grid is not a sample**, and **prefer a
bound to a point estimate on a small support** — `sd <= 2.5` forced by a
two-point support closed the half-spread question permanently where `sd = 0.27`
would only have moved it.

## What the lanes landed

- **The half-spread confound is dead.** 219 games / 78,047 market-minutes: the
  pre-game half-spread takes **exactly two values, 5 and 10 tenths, 99.71% at
  5**. It returns the moment the recorder writes **spreads or totals** — those
  live-quote at sd 47.2 and 22.8.
- **The signal test is pre-registered and says WAIT** (G=300). Amendment 1 fixed
  four defects including a registered SQL predicate that did not exclude what it
  claimed — `suppressed_reason` is comma-joined, and **27.8% of live stale rows
  carry a composite reason**, so the bug was real and material.
- **Candles and derived asks agree 51/51.** ADR 0016 Phase 0 can proceed under
  three conditions; the identity **fails at the boundary**, where an empty book
  publishes `yes_ask = 1000` and unhandled fabricates a 1c ask.
- **`kalshi_markets.result` is written and live**, residue bounded. Calibration
  now has inputs and **zero readers** — building that consumer is NEXT.md item 3
  and is the one evidence line the 0-actionable wall does not block.

## Traps from this session specifically

- **A worktree copy satisfied the has-no-caller detector** — 132 `.py` files from
  other branches were in the walk, so a symbol whose only caller lived on an
  unmerged branch passed on `main`.
- **A guard can stay green because a *stricter* guard downstream catches your
  deformation.** Break per guard, not per function. And a "break" that is the
  original expression rewritten is a faulty break, not a passing guard.
- **The falsy-`0.0` trap is still live bait** — a horizon key written `not r["h"]`
  collapses the current close into "unscored".
- **Closing a bundled audit item ticks the parts that were skipped.**
- **Before widening a population, find the column that marks which one a row came
  from.** If there isn't one, widening is not a config change.
- **`?event_ticker=` ignores `limit` entirely** on Kalshi.
- **The classifier blocks `gh workflow run Deploy` from a Bash tool call**, and
  also blocks reading `gh run list --workflow=Deploy`. Joe runs the deploy with
  `! gh workflow run Deploy -f instance=live -f confirm_live=kalshi-cockpit`.
  Do not route around the block via the browser.
- **Never run `run_chain.py` or `run_loop.py` without `--no-odds`.**
