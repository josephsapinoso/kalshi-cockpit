# Start prompt — paste this to open the next session

Written 2026-08-10. The session that shipped the deploy bundle, ran the joint
bound, **proved the joint bound could never have worked**, and found a real bug
in the suppression layer while doing it.

Everything below is the prompt. Paste it whole, or just say *"read start.md and
follow it"*.

---

Read `CLAUDE.md`, `tasks/NEXT.md` and `tasks/lessons.md` first. NEXT.md is the
actionable checklist; `todo.md` is just the build log. **The top section of
NEXT.md supersedes everything below it.**

## State

`main` is at `86e83e7`, pushed, in sync, tree clean, no worktrees. **1,890
tests**, ruff clean, `next build` clean.

**LIVE IS DEPLOYED and current.** Joe deployed the bundle at the end of last
session and it was verified independently, not by the workflow's assertions:

    unauth /api/{ledger,gate,orders,results}  401;  forged bearer 401
    health  instance_mode=live, live_trading_enabled=false,
            execution_available=false, retired_settings_set=[]

**You can read the live record programmatically, and now page it.** The live
`APP_AUTH_TOKEN` is on the `APP_AUTH_TOKEN=` line of `.env` (gitignored).
Form-POST `token` to `/session`, keep the cookie, then GET. **A whole-table pull
is: read `newest_id` from page 0, pass it back as `max_id` on every page, and
assert `len(set(ids)) == total`.** Verified working end to end — 1,549 rows,
1,549 distinct ids. Do not re-derive this. `scripts/run_joint_bound.py` has the
pull already written.

Six agents in `.claude/agents/`: **`partner`** (directs the fleet — *delegation
is its call*), **`measurement-skeptic`**, **`pre-registrar`**, **`sharp-bettor`**,
**`kalshi-platform`**, **`runtime-realist`**.

**Standing instructions from Joe, which override defaults:**

1. **Call `partner` first** and let it set the queue.
2. **Parallelise by default** — but **two concurrent lanes, never more.** Four
   burned the API session limit; `partner` set two as the cap and it held.
3. **`measurement-skeptic` audits anything before it enters the record**,
   especially good news. It earned its cost twice last session.
4. **Deploys are BATCHED**, and Joe runs them. The classifier blocks
   `gh workflow run Deploy` from a tool call and routing around it via the
   browser is off-limits. He runs:
   `! gh workflow run Deploy -f instance=live -f confirm_live=kalshi-cockpit`
5. **Don't ask permission to continue.** Do ask before money or a re-deploy.

## JOB ONE — the bug, and it needs an ADR before a line of code

**`edge_within_method_noise` cannot fire on the one input where the edge is
purely a devig-method artefact.**

One book quoting both outcomes of a two-way market at identical decimal odds
makes all four devig methods agree to ~1e-14, so `spread_tenths ≈ 1.4e-11` and
`suppression.py:231`'s `edge_tenths > spread_tenths` **passes for any positive
edge whatsoever.** The guard reads *"the methods agree, so this edge is
trustworthy"* when what happened is there was one book and nothing to disagree
about.

It produces `fair_probability = 0.49999999999999994` — a coin flip — on a game
the Kalshi book prices **84/16**. Measured over the whole table: **21 rows, 2
WNBA games, 1.4% of the record, all single-book, 0 unsuppressed, 8 fresh.**
Bounded, but live.

**`min_book_count = 2` is the single threshold between a fabricated fair and a
surfaced row**, and it has **no environment plumbing anywhere** — not `.env`,
`.env.example`, `fly.live.toml` or `config.py`. And `too_few_books` /
`no_market_width` fire on the *identical* condition (185 rows each over 1,000,
symmetric difference **0**), so they are **one guard counted twice, not defence
in depth.** Eight rows were fresh, fillable, +1.2c post-fee and stopped only by
that threshold — ids 979/980 are the worked example.

**Do not just patch it.** `suppressed_reason` is half the `actionable`
predicate, so changing when a suppression fires changes what the gate counts.
This repo already refused a cheaper version of exactly that move. Route through
`partner`, write the ADR (**0019** is next; 0018 is taken), then fix.

The float itself is diagnostic and worth keeping: nothing defaults to 0.5.
`power()` solves with `brentq`, lands one ULP high, and `min` across four
methods — three of them exact — **systematically selects the root-finder's error
floor**. The signature to grep for anywhere is `p_multiplicative == p_additive
== 0.5` with `p_power` one ULP below.

**Riding along, found and not acted on:** `SuppressionConfig.max_odds_age_ms =
900_000` (`suppression.py:40`) is hardcoded and does **not** read
`MAX_ODDS_AGE_S`, which is `900` in `fly.live.toml:128` and `.env` and feeds a
different object consumed by `gate.py`, `live.py` and `routes.py`. They agree
today; changing the env value moves the gate and the API but **not the runner's
suppression.**

## THE JOINT BOUND IS DEAD — do not re-run it, on any population

`docs/measurements/2026-08-10-joint-bound-result.md`. `measurement-skeptic`
verdict: **UNSUPPORTED as a decision-bearing reading.**

**Branch Z — the outcome that would have closed the central question — was
arithmetically unreachable before the data existed.** So `BRANCH N — NOT CLOSED`
is a consequence of the design, not an observation, and **it authorises nothing,
including the withdrawal of the plan to stop.**

- **The complementary-leg identity.** Every game has two complementary tickers,
  so at a zero fee `S_A + S_B` = market width + devig deficit. Over 312
  same-instant pairs: median +13.0, max +82.0 tenths. That caps
  `min(S_A,S_B)` at **4.10 points at the worst pair**, against Branch Z's
  requirement of `> 16.7 points on every row` — off 4x at the best pair, 25x at
  the median, **on any two-sided record.**
- **Amendment 1 made Branch Z and the reachability precondition mutually
  exclusive.** §5 registers δ=10.00 as *"certainly non-zero if the arithmetic
  works at all"*; A1 moved Branch Z above it, and `K` is monotone. **I
  authorised that amendment**, on the reasoning that rounding thresholds up is
  conservative — true against false closure, no protection against this.

The registration guards `K = 0` everywhere as a broken harness and **does not
guard `K ≈ N` everywhere.** It saturated: `K(16.70) = 984/1000` on P0 and
**100% on P1.**

## THE FINDING THAT SURVIVED, and it is whole-table

    unsuppressed rows                              614   in 59 games
      ...with a positive NET edge at the deployed fee  0
      largest clean NET edge                        −2.1 tenths (0.21c short)
    actionable rows anywhere in the table, ever        0

**614 matches `/api/gate`'s published `no_edge` exactly** — two code paths
agreeing. The largest clean net edge over all 1,549 rows is the **same** −2.1 as
over the 1,000-row slice, so the slice hid nothing at the top.

This is the direct empirical confirmation, over the complete table, of what the
fresh-odds registration deduced at §0.3 from a counter alone: *every unsuppressed
row already has a non-positive edge.* **And all 45 rows with a positive net edge
are suppressed** — zero unsuppressed, zero actionable, 8 games. The guards and
the edge computation agree about which rows are garbage. That is a coherence
result, it needed no bound, and it is better evidence than the instrument was
built to produce.

**The refutation ADR is still unwritten, and its argument changed.** It now rests
on the paragraph above, and that is **provisional in exactly the way an n=29 null
is provisional** — which is what the joint bound existed to escape and did not.
**Say so in its own named section or the ADR repeats the failure.** `partner`'s
standing requirement also holds: the honest finding is *"Kalshi is not mispriced
relative to a consensus it may itself lead"*, **never** *"no edge exists at
Kalshi"*.

## The 219 — a lead, and it must not be over-read

`unreadable_examples` shipped and paid for itself on its first call:

    KXMLBTOTAL-26AUG071840NYMPIT-3 .. -7

All five are **MLB totals**, and all five are thresholds of **one game**. Set
beside a whole-record measurement: series prefixes across all 1,549
recommendation rows are `KXMLBGAME` 1,131 and `KXWNBAGAME` 418 — **the
recommendation engine has never written a row about a total or a spread.**

So *if* the unreadable set is dominated by totals, the 219 is **not a leak in the
evidence path at all**: those markets are result-polled because discovery finds
them, and never bet.

**What is NOT established: that the other 214 are totals.** Five examples, one
event, and the route appears to return the first five rather than a sample. This
is [[a-true-measurement-licensed-a-false-conclusion]] waiting to happen — the
measurement is about five tickers and the conclusion on offer is about 219. Widen
`unreadable_examples` or census by series prefix first.

## Four lessons landed last session — read them, they are the product

In `tasks/lessons.md`:

- **A reachability guard has to run in both directions.** An instrument that
  cannot return its decision value is as broken as one that always returns it.
- **The guard that cannot fire on the input it was built for.** Near-zero
  dispersion makes any `effect > spread` threshold trivially true; and two codes
  firing on one condition are one guard — check row-sets, not names.
- **Tracing a number to code is only half the check.** An inequality is not a
  pin, an example is not an extremum, and **a document can supersede itself
  without renumbering the passage it supersedes** (ADR 0017 §1 Correction 1 vs
  its own Addendum A.2).
- **A pull can be incomplete while every check on it adds up.** `len(set(ids))
  == total` is the only check that catches it.

## Settled — do not re-derive or re-propose

- **One signal, not two.** `model_probability` is NULL on every row and no
  decision reads it. **Do not wire `elo.py` up to make the documentation true** —
  the documented design was a conjunction, and an AND-gate on an empty set leaves
  it empty.
- **Arming real trading is a code change** (ADR 0018). `ORDERS_ARE_DRY_RUNS` is a
  module constant with no env read.
- **The account has zero fills, ever.** Every field *inside* a fill is
  unobserved, including whether the fee is called `fee`. Run
  `scripts/capture_fills_fixture.py` the moment trades fill, **before** writing
  any parser.
- **The $5 buys less than claimed.** The two fee models agree at 163 of 999
  prices — including **exactly 50.0c** — and differ by exactly 1c/contract
  elsewhere.
- **There is no minimum order size.** `MIN_ORDER_CONTRACTS` was retired
  2026-08-09 and is in `config.RETIRED_SETTINGS`; ADR 0017 §1 Correction 1 says
  otherwise and is superseded by its own Addendum A.2. The maker figures are
  **1.38 points / 3.6x** at `N=1`.
- **Scout and Historian have no production caller.** Only `agents.review` is
  imported by production (`runner.py:61`). `partner` wants that named in the ADR.
- **Kalshi's `occurrence_datetime` runs exactly 3 hours late**, and it is
  recorded rather than corrected away.

## Traps

- **On live the Anthropic bill is held at zero by `surfaced == 0`**, not by a
  missing key — `agent_fleet_configured: true`. The spend switches itself on
  precisely when the project starts working. **Set a spend limit.**
- **`$CLAUDE_JOB_DIR/tmp` is not empty at session start.** A `git commit -F
  msg.txt` there picked up a stale file from a previous day and committed a
  correct diff under a totally unrelated message. Give scratch files
  task-specific names and check `git log -1 --format=%s` after any scripted
  commit.
- **A committed registration must never be edited in place.** One was rewritten
  last session — 561 insertions, 352 deletions — by the role that wrote the rule
  against it. Amendments are appended, superseded text marked in place and
  deleted never.
- **`?event_ticker=` ignores `limit` entirely** on Kalshi.
- **Never run `run_chain.py` or `run_loop.py` without `--no-odds`.**

## The decision that is Joe's

If the refutation stands, **continuing is not a smaller version of this project —
it is a different one**: liquidity provision, or Kalshi as the sharp reference
against another venue. That deserves a fresh decision with a clean record in
hand. **Make the call after the ADR is written**, not before.
