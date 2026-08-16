# Start prompt — paste this to open the next session

Rewritten **2026-08-16 ~01:20Z**. The session that **fixed the credit drain (it
was two defects, not one), shipped the Slate screen, and closed the non-sports
direction on cost after an audit reversed its own first result.**

Say *"read start.md and follow it"*, or paste this whole file.

---

Read `CLAUDE.md`, `tasks/NEXT.md` and `tasks/lessons.md`. NEXT.md is the
actionable checklist and **its top supersedes everything here**.

## ⏱ FIRST — one number is outstanding, and it is due ~17:30Z

**Everything is deployed and verified. Nothing is broken.** The single open item
is a *measurement*, not a defect.

The live planner is holding for a slot at **16:51Z–17:21Z covering 13 games**.
That firing should cost **6 + 20×13 = 266** credits of 400. After it lands:

```
flyctl ssh console -a kalshi-cockpit \
  -C "python /app/scripts/inspect_live_db.py credits-day --date 20260816"
```

- **~266** → the fix held. **Write that number into `.env.example` and
  `runner.py:1529-1535`**, which deliberately carry no per-slate figure right
  now. Reconcile it against the provider's own `x-requests-used`
  (`BudgetState.drift`) before publishing it — a cost derived from an assumed
  input is the assumption restated, which is how the last figure was wrong.
- **~390+** → the fix did not hold. Read `sweep-log` and start there.

`credits-day` **requires** `--date YYYYMMDD` and refuses to guess. The budget day
runs 10:00Z→10:00Z, so a sweep at 17:00Z on the 16th is `--date 20260816`.

**Then run this — it may halve the prop bill:**

```
flyctl ssh console -a kalshi-cockpit \
  -C "python /app/scripts/inspect_live_db.py prop-bookmakers"
```

Props are billed per market key **per region** and live runs `us,eu`. Nothing in
this repo establishes that a single EU book quotes an MLB player prop. If that
list is all US-facing, half of every 20-credit event buys nothing. **Do not drop
`eu` globally to fix it** — `SHARP_BOOKS` holds `betfair_ex_eu`/`betfair_ex_uk`,
so that silently converts the deployed strategy into ADR 0021 option B and voids
comparability with the entire existing record. Regions are per-endpoint; change
the prop call alone.

## WHAT SHIPPED, AND WHAT IT DOES NOT CLAIM

Five commits, all pushed, `origin/main` at **`2f91981`**. **2,689 tests pass, 10
`xfail(strict=True)`, ruff clean, `npm run build` clean.** Verified at the time
of writing, not inherited — **re-verify before trusting it:**

```
git log --oneline -6
git rev-list --count origin/main..HEAD
git status --short
.venv\Scripts\python.exe -m pytest -q
```

### `7b6cc2e` — the credit drain was **two** defects, and the second was worse

The handoff described one: props bought for all 27 pre-game fixtures instead of
the 4 the slot covered. Fixed — `covers_commence` is now the single definition of
"covered", `games_covered` is counted **through** it, and `FiringSweep` carries
its slot.

**The one underneath it decided the outcome.** `decide_sweeps` sized the whole
budget day on the *team* sweep cost (`remaining_today // 6`) with **no
representation of the per-event prop fetch that fires off the back of every
firing it authorises.** It authorised a 6-credit call that spent 384. Fixing only
27→4 would have left the next limit binding in silence — and the very next slot
on the live machine covers **13 games**, which is `6 + 20×13 = 266`. The planner
now reserves that before authorising, and names the refusal when it binds.

Four guards, each seen red by disabling it. One caught a one-character drift
(`<` for `<=`) the moment the count and the predicate were allowed to diverge.

### `e790ac3` — the Slate screen: edge is a column, not a gate

`/slate`, which **took Rejections' nav slot** (Joe's call; `/rejections` is still
served, exactly as `/builder` is). One flat list in kickoff order, every row
carrying facts the record already held and had never rendered: where Kalshi's ask
sits among per-book devigged fair values **with no sharp anchoring**, Kalshi's own
drift off `kalshi_quotes`' history, book disagreement, and capacity.

**This closed an unactioned recommendation from 2026-08-09**, not a new idea. The
`sharp-bettor` review led with *"edge versus fee is being used as a filter where
it should be a sort"* and recorded Joe saying the same thing independently that
day. Treat that as a scheduling failure closed.

**The prohibitions are load-bearing and tested.** No composite — no score, rating
or confidence, because weighting unscored factors is a model needing its own ADR
(ADR 0021 §9), and both `test_slate.py` and `test_api.py` are tripwires for one
appearing. Nothing reaches `suggested_contracts`, suppression or the order path;
a test parses the money path's imports and turns red on one. Rows sort by kickoff
because **a ranking is a weighting**.

**Book-side line movement is deliberately absent.** A fixture is swept once or
twice a day; two samples cannot tell a move from the absence of one, and finer
resolution is 60 credits a call against 400/day. Dead on arithmetic, not
oversight. Kalshi-side drift at ~15s is a different thing and is shown.

**Nothing on that screen is scored against an outcome.** It is recorded so it
*can* be — the same argument that justified building props before the fee
question resolved.

### `9a4f15c` — non-sports is **dead on cost**, and the first run said otherwise

424 DEAD to 129 WORTH across 620 genuinely-non-sport series priced where the
control is priced. The registered falsifier fired.

**Read this one for the process.** The first run reported the opposite.
`measurement-skeptic` caught two instrument defects before publication, and both
are now lessons:

- **One-sided books were counted as settled outcomes.** Kalshi sends `"0.0000"`
  for a side nobody bids, never an absent field — so the `unreadable` counter was
  dead code (0 of 81,420) while **28,579 live markets, 35% of the arm**, were
  dropped under a label wrong for 99.5% of them, and dropped hardest exactly
  where books are thinnest.
- **No price was recorded**, so *tight* and *cheap* were one measurement. Control
  series price at **50.5c**; series verdicted WORTH price at **12.0c**.

**And the control is not a denominator:** 9 of its 19 series are MLB, per league
it runs 5.0 / 12.5 / 55.0 / 175.0, and dropping baseball moves it 10.0 → 35.0.

## THE THREE THINGS THAT DECIDE THIS PROJECT

Joe said on 2026-08-11: *"You seem to do so much testing instead of building."*
**Keep this at the top of every handoff until it stops being true.** This session
shipped a screen he can open on his phone, and the board is now:

| # | Question | State |
|---|---|---|
| 1 | **Is the staleness guard wrong?** | **ANSWERED 2026-08-11, opens no runway.** ADR 0020 / 0025. |
| 2 | **Is the fee coefficient 0.070 or 0.035?** At 0.035 the taker bar drops to **50.88%**. | **THE ONLY LIVE QUESTION.** Needs a second MLB window **on or after ~2026-09-04** and **one 1-contract fill**. Nine baseball fills pin `k` to `(0.03497, 0.03501]`. |
| 3 | **Is Kalshi simply the sharp side?** | **DEAD on power (2026-08-11)** — but the Slate's book-distribution column is the first thing in this product that *looks at* it per row. It is a display, not a test. |

**ADR 0023 expires 2026-08-31 (UTC) with default A** — 15 days. Nothing this
session moved item 2, and nothing may be written up as though it did.

## WHAT IS LEFT, IN ORDER

1. **The credit number at the top of this file.** Then `prop-bookmakers`.
2. **The one-sided alternate feeds.** 174 of 222 matched keys dropped for having
   no two-sided book — **~4.6× the comparisons for zero extra credits**, and an
   assumption that needs **`pre-registrar`**, not a patch.
3. **Score the first prop rows on CLV** once a slate settles. **Register the
   measurement before looking.** Props are baseball, charged `k = 0.035`, priced
   at 0.070 — understated by up to 2× on the fee component, deliberately.
4. **The settlement `fee_cost` capture** for the five round-three positions — the
   only direct test of **H4**, which the 0.63-point headroom rests on. Fills
   endpoint retention ~3 months from 2026-08-14.
5. **The Scout — TABLED BY JOE on 2026-08-16. Do not start it unasked.**

### The Scout, recorded so nobody re-derives the cost

`backend/agents/scout.py` does injuries, lineups, weather, rest/travel and venue
with sources and timestamps, and refuses to emit a number by schema. ADR 0022
quarantines it, and its recorded revival condition — *"a strategy is adopted that
needs qualitative context, and the Anthropic spend it implies is budgeted"* — **is
now met** by the Slate screen. Joe has still tabled it.

Wiring it turns **two** tests red, independently and by design. The second
(`BILLED_PATH_CALL_SITES`) **cannot be satisfied by editing a list**: it requires
giving Scout a **batch budget** the way `review_surfaced` has one, because the
meter is per-caller by a deliberate design decision, not per-call. Plus an ADR
citing 0022, and an on-demand trigger so cost scales with attention. Half a
session, and real Anthropic spend (~$0.35–$2.01 a saturated day at the deployed
24-call ceiling, on `.env.example`'s own **[ASSUMED, uncited]** price).

The Slate's desk bubble already renders the Scout saying it has not looked. That
is the honest state and it costs nothing.

## GOVERNANCE — Joe's ruling, not a convention you may relax

`flyctl ssh console` against `kalshi-cockpit` may **only invoke a committed,
reviewed script by path.** No inline code, no `python -c`, no base64, no
filesystem browsing, no interactive session. **The allowlist does not enforce
this** — a permission pattern matches a command prefix and cannot see inside
`-C "..."`. Four sessions have now written this rule and two drifted from it
within the hour. Assume you will too.

**Three of forty-seven `scripts/*.py` are in the image**, and `.dockerignore`
decides, not `Dockerfile` — `run_loop.py`, `migrate_db.py`, `inspect_live_db.py`
(`.dockerignore:77-80`). *(47 counted 2026-08-16, not carried forward. A previous
draft of this file inherited "two of forty-two" from a time before
`inspect_live_db.py` shipped and was wrong for two sessions. **Count it; do not
copy it.**)* `census_non_sports_spread.py` is **not** in the image and
must not be; it is a laptop `Tool`.

`inspect_live_db.py` query names: `sweep-log`, `credits-tail`,
`credits-day --date YYYYMMDD`, `credits-month`, `series`, `kalshi-quotes-band`,
and **`prop-bookmakers`** (new this session).

**Deploying is a phone button:**

```
gh workflow run deploy.yml -f instance=demo
gh workflow run deploy.yml -f instance=live -f confirm_live=kalshi-cockpit
```

Both instances were deployed and verified on 2026-08-16 (~00:35Z). The typed
confirmation is the guard against a mis-tap; it is not optional.

**Ask before money or a deploy. Do not ask permission to continue** — Joe leaves
8-hour unattended stretches. **Every push publishes to the world immediately.**

## SETTLED — do not re-derive or re-propose

- **One signal, not two.** `elo.py` has no production caller. **Do NOT wire it up.**
- **The non-sports direction is closed on cost.** Run 2 is the run. **Do not
  re-run it for a better number** — a further look is a **new registration**. What
  would overturn it is listed in §9 of the result document.
- **Nothing on the Slate may become a composite.** No score, no rating, no
  weighted confidence. Two tests enforce it.
- **ADR 0025** — the `stale_odds` re-opening is refused. 23 rows / 9 clusters.
  **Never write "844 of 935" as rows in play.**
- **`ALL_CHECK_NAMES` has 12 entries, not 14.**
- **`TAKER_COEFFICIENT` stays at 0.070** until item 2 resolves. `core/fees.py` is
  untouched by everything above and must stay that way.
- **The coefficient is not one number across the record** — baseball 0.035,
  WNBA/ATP/PGA 0.070, disjoint at a ratio floor of 1.999×. **Never write "the fee
  is 0.035".** Every low observation lies inside five days.
- **H4 is UNTESTED**, not pending and not confirmed. ADR 0027.
- **A-versus-F is owned by ADR 0023**, deferral stands, expiry 2026-08-31, default **A**.
- **`KXMLBGAME` cannot fill a sub-20c pre-game band.** Dead on reachability.
- **AVAILABILITY IS NOT FILLABILITY.** Every band number is a stored quote.
- **Kalshi's `occurrence_datetime` runs exactly 3 hours late.**
- **`?event_ticker=` ignores `limit`** on Kalshi. **Never paginate `/markets`.**
- **Never run `run_chain.py` or `run_loop.py` without `--no-odds`** locally.
- **`ruff format --check` reports ~153 files, pre-existing and enforced nowhere —
  do not "fix" it.**
- **The five Dependabot alerts are parked deliberately** — build-time only.
- **`AGENTS.md` is a nine-line pointer to `CLAUDE.md` and must stay one.** It was
  a stale *copy* carrying 52.00% where CLAUDE.md said 51.75%. Never re-expand it.

## TRAPS

- **`start.md` is a snapshot; `git log` is the record.**
- **A ratio against a control assumes the control is one number.** The non-sports
  control spanned 35× across four leagues and was 47% MLB. Report a
  denominator's *dispersion and composition*, and jackknife it by whatever
  natural groups it contains, before dividing anything by it.
- **"Unreadable" and "empty" are decided by the wire, not by your rule.** A
  counter provably zero on real data is either dead or mis-routed, and both are
  findings. Choose a test anchor where the candidate readings *disagree*.
- **A cost model that prices one call but not the call it triggers will
  authorise a 6-credit request that spends 266.** Two limits on one quantity,
  and the tighter one wins in silence.
- **A guard copied from a neighbouring path inherits its assumptions, not its
  safety.** Prefer the codebase's named predicate over an inline re-expression.
- **A raise inside a per-item loop nested in a per-slate loop fails the slate.**
- **A fixture that always starts from empty cannot test teardown.** `seed_all`'s
  reset order was wrong for the life of the project and unreachable from the
  suite for exactly that reason.
- **A subagent's confident claim is the one to re-run yourself.** `partner` cited
  `tasks/prior-art.md:44-46` for an RFQ census. **That file does not exist.** The
  claim was fabricated and nearly became the justification for a whole lane.
- **`git add tasks/next.md` matches nothing and says nothing.** Git tracks
  `NEXT.md`. **Run `git status --short` after any hand-typed `git add`.**
- **`docs/measurements/data/` is gitignored** (`.gitignore:33` matches `data/` at
  any depth). `git add` there stages nothing, silently. Put evidence artifacts
  directly in `docs/measurements/`, as the large pulls already are.
- **A placeholder drawn from the production namespace is a prediction.**
- **`flyctl logs` is lossy** — ~90% of a burst is dropped.
- **A background job reported stopped may still be running.** Check `ps`.
- **Two lanes in one working tree fight over git. Add by explicit path, never
  `git add -A`.**
- **A status word in a handoff may be a human's summary, not an instrument's
  output.** Grep the named instrument for the literal token.

## Standing instructions from Joe

1. **Call `partner` first** and let it set the queue. **Delegation is its call.**
   Its output is **not** exempt from the fabrication trap above.
2. **Parallelise by default — two concurrent lanes, never more.**
3. **`measurement-skeptic` audits anything before it enters the record**,
   especially good news, and especially a kill. **It earned its place this
   session by reversing a published-in-draft result.**
4. **Deploys are batched and Joe runs them.**
5. **Don't ask permission to continue. Do ask before money or a deploy.**
6. **Say unprompted when the session should end.** Target 300–500K tokens.
7. **Watch the build-to-measure ratio and say so when it is wrong.**
