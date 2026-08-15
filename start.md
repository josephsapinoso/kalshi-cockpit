# Start prompt — paste this to open the next session

Rewritten **2026-08-15 ~19:20Z**. The session that **built all three remaining
props slices, deployed them, and did not live to see the first prop row land**.

Say *"read start.md and follow it"*, or paste this whole file.

---

Read `CLAUDE.md`, `tasks/NEXT.md` and `tasks/lessons.md`. NEXT.md is the
actionable checklist and **its top supersedes everything here**.

## ⏱ FIRST — one thing is unverified, and it takes one command

**Props are built, pushed and deployed. Nobody has yet seen a prop row appear on
the live instance.** The deploy finished at ~19:12Z on 2026-08-15 and the next
MLB sweep was scheduled for ~19:21Z. The previous session's poller was still
returning `none` when the session ended.

**This is the first thing to check, and it is the only open thread.**

```
JAR=jar.txt
TOKEN=$(grep -m1 '^APP_AUTH_TOKEN=' .env | cut -d= -f2-)
curl -sS -o /dev/null -c "$JAR" -X POST -F "token=$TOKEN" -F "next=/" \
  https://kalshi-cockpit.fly.dev/session
curl -sS -b "$JAR" "https://kalshi-cockpit.fly.dev/api/ledger?limit=300"
```

**Look for tickers starting `KXMLBKS-`, `KXMLBTB-`, `KXMLBHIT-`, `KXMLBHR-` or
`KXMLBRBI-`.** Before this build the ledger held only `KXMLBGAME` and
`KXWNBAGAME`.

**Never echo `$TOKEN`, and delete `jar.txt` afterwards** — it is a live session
cookie for the money instance and the repo is public.

### If no prop rows have appeared

Three candidates, cheapest first. **Do not assume the code is wrong** — two of
the three are ordinary operating states:

1. **No sweep has fired yet.** `/api/window` reports `next_sweep_ms` and
   `next_sweep_reason`. Props are bought **only** on the branch where a team
   sweep is *served*, so no sweep means no props, correctly.
2. **The credit budget refused.** This is the failure that looks exactly like
   success from every other screen — health stays green, the Board renders, the
   record silently does not grow. Every prop decision writes a row to
   `odds_sweep_log` with a detail prefixed **`props:`**, served or skipped with
   the reason.
3. **No two-sided book at any rung.** 18 of 20 rungs in the captured payload had
   only an Over. A slate where every rung is one-sided produces zero
   `fair_prices` rows and is *not* a bug.

**Read the `props:` rows before forming a theory** — the command is under
GOVERNANCE below. The previous session's biggest single finding came from
capturing a payload instead of reasoning about one.

**State at 19:26Z on 2026-08-15, so you can tell progress from a stall.** The
deploy landed at ~19:12Z and the new code logged its first pass at **19:13:43Z**
(`odds_sweep_log` id 296, `skipped`, "next slot is baseball_mlb at 19:21Z–19:51Z").
**No sweep had been served since the deploy**, so the absence of prop rows at
that point was candidate 1 and nothing else. The last served sweep, id 291 at
**17:44:52Z**, predates the deploy and could not have bought props.

So: **the first sweep that can possibly buy props is the 19:21Z–19:51Z MLB
slot.** If `sweep-log` shows a `served` row after 19:21Z with **no** `props:` row
beside it, that is a real defect and the call site is `runner.fetch_and_store_props`.

## WHAT WAS BUILT, AND WHAT IT DOES NOT CLAIM

Four commits, all pushed, `origin/main` level at **`e2930d7`**:

- **`8febd24`** — slices 2–3. Discovery admits the five MLB prop ladders
  (`market_type = 'prop'`, parsed player); a prop event inherits the link its own
  moneyline event earned.
- **`1fb6850`** — slice 4. A served team sweep buys the props; pricing devigs one
  (player, line) at a time into `fair_prices`.
- **`9855ae9` / `e2930d7`** — NEXT.md and lessons.

**2,626 tests pass, 10 `xfail(strict=True)`, ruff clean, 21 mutations run.**
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

1. **Confirm prop rows landed** (top of this file).
2. **The one-sided alternate feeds.** 174 of 222 matched keys dropped for having
   no two-sided book. Recovering them means estimating a book's overround from
   its own two-sided primary and applying it to that book's one-sided
   alternates — **~4.6× the comparisons for zero extra credits**, and an
   assumption that needs **`pre-registrar`**, not a patch.
3. **Score the first prop rows on CLV** once a slate settles. **Register the
   measurement before looking.**
4. **The settlement `fee_cost` capture** for the five round-three positions —
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
