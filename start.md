# Start prompt — paste this to open the next session

Rewritten **2026-08-15 ~20:15Z**. The session that **built all three remaining
props slices, deployed them, watched the first live pass, and found two defects
in it** — one fixed and shipped, one still open with a clock on it.

Say *"read start.md and follow it"*, or paste this whole file.

---

Read `CLAUDE.md`, `tasks/NEXT.md` and `tasks/lessons.md`. NEXT.md is the
actionable checklist and **its top supersedes everything here**.

## ⏱ FIRST — props are recording. **One defect is open and it re-fires at 10:00Z.**

**Verified on live at 20:10Z on 2026-08-15: 474 prop recommendation rows**, all
five series, 16,234 prop odds quotes, `events_linked` 79 → 92. The chain works
end to end. **Every row is suppressed and zero surfaced** — the predicted
result. Their `stale_odds` is literal (the sweep ran at 19:41:53Z), not evidence
about props.

**The open defect: the prop sweep drained the day’s credits in one pass.**

```
props: 27 pre-game fixtures, 67 Kalshi prop events, 10 market keys  -> 16,234 quotes
props <event>: 384 of 400 daily credits already spent, and the call costs 20  -> REFUSED
```

Two compounding errors. `fetch_and_store_props` buys for **every pre-game
fixture in the sweep (27)** rather than the fixtures the sweep was fired for
(**4**); and an event costs **20** credits, not 10, because live runs **two
regions**. Every remaining odds sweep that day is refused, team sweeps included,
so the moneyline record stops growing.

**It re-fires when the budget day rolls at 10:00Z.** Fix it first.

**Do not reflex-fix.** One region halves the cost and leaves 27-vs-4 in place; a
hard event cap picks an arbitrary number. `decide_sweeps` already knows which
fixtures a slot covers — `SweepSlot` carries `anchor_commence_ms` and
`games_covered`, and `/api/window`’s `slots_planned` shows both. **Then
re-derive the cost from a real sweep**, because the estimate that shipped
("~150 a slate") was an assumption restated, and it is wrong in
`.env.example` too.

## WHAT WAS BUILT, AND WHAT IT DOES NOT CLAIM

Seven commits, all pushed, `origin/main` level at **`7318c95`** or later:

- **`8febd24`** — slices 2–3. Discovery admits the five MLB prop ladders
  (`market_type = 'prop'`, parsed player); a prop event inherits the link its own
  moneyline event earned.
- **`1fb6850`** — slice 4. A served team sweep buys the props; pricing devigs one
  (player, line) at a time into `fair_prices`.
- **`9855ae9` / `e2930d7`** — NEXT.md and lessons.
- **`98b8697`** — gitignore the curl cookie jar. The phone check below writes a
  **live session cookie** to disk in a public repo, and every runbook only
  *told* the reader to delete it.
- **`7318c95`** — the untradeable-rung fix (below).

**2,629 tests pass, 10 `xfail(strict=True)`, ruff clean, 24 mutations run.**
Verified at the time of writing, not inherited. **Re-verify before trusting it:**

```
git log --oneline -6
git rev-list --count origin/main..HEAD
git status --short
.venv\Scripts\python.exe -m pytest -q
```

**NOTHING NEW IS SURFACED, AND THAT IS THE EXPECTED RESULT.** At the deployed
`TAKER_COEFFICIENT = 0.070` the scoping probe found **zero** prop rows clearing
against a real consensus. This build records props so they can be scored on
**CLV against Kalshi's own close** — rule 3 — which needs weeks of calendar. **A
session that reads "props are live" and starts hunting for prop bets has misread
it.**

### Three things the build found that were not in the plan

1. **`floor_strike` retired a computation.** Kalshi publishes an `N+` prop's
   floor as `N - 0.5`, which is exactly the `point` a sportsbook quotes for the
   same rung — **259 of 259** on the captured fixture, both series. The join is
   an equality between two published numbers. `tests/test_discovery.py` pins it,
   so a Kalshi change goes red instead of shifting every prop by one rung.
2. **`competition_scope` on a prop is the statistic, not the fixture** —
   `"Strikeouts"`, `"Total Bases"`, one string per series. That is why
   `kalshi/props.PROP_SERIES` keys on the **series ticker**. `PROP_SCOPES` holds
   only the two values read from a payload; the other three series' spellings
   are unknown and **must not be guessed**.
3. **Two existing tests were built on invented series names that turned out to be
   real.** See `tasks/lessons.md`, 2026-08-15.

## THE THREE THINGS THAT DECIDE THIS PROJECT

Joe said on 2026-08-11: *"You seem to do so much testing instead of building."*
**Keep this at the top of every handoff until it stops being true.** The props
build was the answer to it. The board is now:

| # | Question | State |
|---|---|---|
| 1 | **Is the staleness guard wrong?** | **ANSWERED 2026-08-11 and it opens no runway.** ADR 0020 / 0025. `actionable` stays 0. |
| 2 | **Is the fee coefficient 0.070 or 0.035?** At 0.035 the taker bar drops to **50.88%**. | **THE ONLY LIVE QUESTION.** Needs a second MLB observation window, **≥3–4 weeks after 2026-08-14** — so **on or after ~2026-09-04** — and **one 1-contract fill**. Nine baseball fills already pin `k` to `(0.03497, 0.03501]`. |
| 3 | **Is Kalshi simply the sharp side?** | **DEAD — closed 2026-08-11 on power.** |

**Item 2 is the gate on the whole strategy, props included** — props are
baseball, so whatever that window says about `k` applies to all of it. Every
prop row now being recorded is priced at 0.070 and is therefore understated by
up to a factor of two on the fee component, **deliberately**.

## WHAT IS LEFT, IN ORDER

1. **The credit defect at the top of this file.** It is the only thing
   blocking props from recording properly, and it re-fires at 10:00Z.
2. **Re-read `sweep-log` and `credits-day` after the first clean slate** and
   write the *measured* per-slate cost into `.env.example`, replacing the
   estimate that was wrong.
3. **The one-sided alternate feeds.** 174 of 222 matched keys dropped for having
   no two-sided book. Recovering them means estimating a book's overround from
   its own two-sided primary and applying it to that book's one-sided
   alternates — **~4.6× the comparisons for zero extra credits**, and an
   assumption that needs **`pre-registrar`**, not a patch.
4. **Score the first prop rows on CLV** once a slate settles. **Register the
   measurement before looking.**
5. **The settlement `fee_cost` capture** for the five round-three positions —
   the only direct test of **H4**, which the 0.63-point headroom rests on. The
   fills endpoint has a measured retention bound of **~3 months from
   2026-08-14**, so this has a real clock.

## GOVERNANCE — Joe's ruling, not a convention you may relax

`flyctl ssh console` against `kalshi-cockpit` may **only invoke a committed,
reviewed script by path.** No inline code, no `python -c`, no base64, no
filesystem browsing, no interactive session. **The allowlist does not enforce
this** — a permission pattern matches a command prefix and cannot see inside
`-C "..."`. Three sessions wrote this rule and two drifted from it within the
hour. Assume you will too.

**Three of forty-three `scripts/*.py` are in the image**, and `.dockerignore`
decides, not `Dockerfile` — `run_loop.py`, `migrate_db.py` and
**`inspect_live_db.py`** (`.dockerignore:77-80`).

**An earlier draft of this file said `inspect_live_db.py` was not on the
machine. It was wrong, and it was inherited rather than checked** — the previous
`start.md` said "two of forty-two" from a time before that script shipped, and
the number was copied forward. This file's own first trap says a snapshot is not
the record. Read `.dockerignore` before repeating a count from here.

**That script is the sanctioned way to ask the live database a question**, and
it is how you read the `props:` rows:

```
flyctl ssh console -a kalshi-cockpit \
  -C "python /app/scripts/inspect_live_db.py sweep-log -n 12"
```

Read-only is enforced by the connection (`mode=ro`), the query names are a fixed
whitelist, and no SQL crosses the command line — which is exactly what the ssh
ruling requires. `sweep-log` prints counts by outcome and then the last N rows
in full, `detail` included. Other names: `credits-tail`, `credits-day`,
`credits-month`, `series`, `kalshi-quotes-band`.

**Deploying is a phone button, not a laptop step:**

```
gh workflow run deploy.yml -f instance=live -f confirm_live=kalshi-cockpit
```

or GitHub app → Actions → Deploy → Run workflow → instance `live` → type
`kalshi-cockpit`. The typed confirmation is the guard against a mis-tap; it is
not optional. The v7→v8 migration runs itself at boot, before anything opens the
database, and aborts the boot on failure.

**Ask before money or a deploy. Do not ask permission to continue** — Joe leaves
8-hour unattended stretches. **Every push publishes to the world immediately.**

## SETTLED — do not re-derive or re-propose

- **One signal, not two.** `elo.py` has no production caller. **Do NOT wire it up.**
- **ADR 0025** — the `stale_odds` re-opening is refused. 23 rows / 9 clusters.
  **Never write "844 of 935" as rows in play.**
- **`ALL_CHECK_NAMES` has 12 entries, not 14.**
- **`TAKER_COEFFICIENT` stays at 0.070** until item 2 resolves. `core/fees.py` is
  untouched by the props work and must stay that way.
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

## TRAPS

- **`start.md` is a snapshot; `git log` is the record.**
- **A guard copied from a neighbouring path inherits its assumptions, not its
  safety.** `if ask is None` was enough for moneylines because a game line
  never reaches 0 or 1000 while pre-game; a prop ladder reaches both every
  slate. Prefer the codebase's named predicate (`is_valid_price`) over an
  inline re-expression — the predicate *is* the assumption written down.
- **A raise inside a per-item loop nested in a per-slate loop fails the
  slate, not the item.** One untradeable rung aborted every moneyline row on
  the pass, and a failed full pass is *retried*.
- **A cost estimated from an assumed input is the assumption restated.**
  "~150 credits a slate" was 384 in one pass. State where each input was read
  from, and reconcile against one real run before publishing the number.
- **`git add tasks/next.md` matches nothing and says nothing.** Git tracks it as
  `tasks/NEXT.md`; Windows resolves both to one file and git does not. A
  two-file commit landed with one file this way. **Run `git status --short`
  after any hand-typed `git add`.**
- **A surviving mutation sometimes means the code is lying about itself, not
  that a test is missing.** One survived this session and the *comment* was the
  thing that had to change. Keep equivalent mutations, recorded; do not prune
  them to make the count clean.
- **A placeholder drawn from the production namespace is a prediction.**
  `KXMLBHIT` was an invented example until it wasn't.
- **`flyctl logs` is lossy** — ~90% of a burst is dropped by Fly's pipeline.
- **A background job reported stopped may still be running.** Check `ps`.
- **Two lanes in one working tree fight over git. Add by explicit path, never
  `git add -A`.**
- **A status word in a handoff may be a human's summary, not an instrument's
  output.** Grep the named instrument for the literal token.

## Standing instructions from Joe

1. **Call `partner` first** and let it set the queue. **Delegation is its call.**
   Its output is not exempt from rule 3.
2. **Parallelise by default — two concurrent lanes, never more.**
3. **`measurement-skeptic` audits anything before it enters the record**,
   especially good news, and especially a kill.
4. **Deploys are batched and Joe runs them.**
5. **Don't ask permission to continue. Do ask before money or a deploy.**
6. **Say unprompted when the session should end.** Target 300–500K tokens.
7. **Watch the build-to-measure ratio and say so when it is wrong.**
