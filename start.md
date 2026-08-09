# Start prompt — paste this to open the next session

Written 2026-08-09 ~06:10Z, end of the session that made the log stream
readable, found the gate's real blocker, and installed the 20K odds tier.

Everything below is the prompt. Paste it whole, or just say *"read start.md and
follow it"*.

---

Read CLAUDE.md, tasks/NEXT.md, and tasks/lessons.md first. NEXT.md is the
actionable checklist; todo.md is just the build log.

## State

`main` is `e950c49`, live is on it (machine **v25**), tree clean, pushed, CI
green on every push. **1,328 tests**, ruff green. Gate locked,
`execution_available: false`, five pages 307 → `/login`, `/api/orders` 401 with
and without a forged bearer. Demo also current.

The 20K Odds API tier is installed and sweeping: `ODDS_DAILY_CREDIT_BUDGET` is
**400** (was 16) with a monthly ceiling of 13,000. The first pass on it fired a
sweep, stored 626 quotes, and took linked games 10 → 16 and recommendations
4 → 24.

## The one number that matters

    gh workflow run Ops -f instance=live -f action=logs

Find `gate progress (24h)`. Last read: `actionable=0 of 300 needed,
no_edge=177, suppressed=265`.

**`stale_odds` was ~97% of suppressions and that was the whole blocker** — the
free tier gave two 15-minute windows a day against a pass every 900s. It is
fixed. So over a day, one of two things is now true:

- **`actionable` starts growing.** The gate is accumulating for the first time.
  Next question becomes `clv_rows_joined`, still pinned at 190.
- **`actionable` stays 0 while `no_edge` climbs.** That is the project's answer,
  honestly obtained, and worth as much as a yes. Say so plainly rather than
  reaching for another knob. **Do not relax `MAX_ODDS_AGE_S` or a suppression
  threshold** — that is how a fabricated edge enters the record.

## One verification left open, and it needs the window

The `discovery:` line was quietened on the quote cadence (`5907787`): full
passes always print, quote passes only when the numbers change. **Proven by
test, not yet observed on live** — the window closed minutes after the deploy
and quote passes only run while it is open.

Next window was scheduled ~15:45Z. When one opens, check `discovery:` appears
once per *full* pass and not once per quote pass. Until then it is pending, not
confirmed.

## Work that does not need the window

If you are starting hours before 15:45Z, these are self-contained:

1. **`pricing pass:` duplicates `pass N ok`.** Strict subset, emitted ~4ms
   earlier from `runner.py` while the other comes from the scheduler in
   `run_loop.py`. Not simply removable: `run_chain.py` emits no `pass ok` line
   and would go silent. Worth ~a third of the remaining log volume.
2. **Exposure is fee-exclusive against a fee-inclusive cap** (~2%). Open and
   deliberately deferred; adding a column is cheap, changing what
   `limit_price_tenths` means is not.
3. **The Research and Playbook screens.** Never built. Scout findings with
   sources and timestamps; lessons, config versions, proposals awaiting
   approval.
4. **One combo price lookup** — `POST /multivariate_event_collections/{t}/
   lookup`, no money, yields a measured same-game correlation.
   `combos.lookup_combo` refuses without `allow_market_creation=True`. Joe
   authorised exactly one; it creates a market if the combination is new.

## Still blocked on Joe, and it is now the *second* constraint

The **four fee-calibration trades** — minimum-size orders at ~10c/30c/50c/80c in
the Kalshi app, a few dollars, read the true fee off `average_fee_paid`. He has
pre-authorised them; they have not happened. `fee_predicted == fee_actual` is a
gate condition and no amount of CLV moves it. Say so plainly rather than
building around it.

## Historical odds — assessed, bounded, not built

The tier includes historical odds. `scripts/measure_candlestick_retention.py`
measured the thing that gates it: **Kalshi keeps ~80 days**, then the market is
gone entirely, verified by constructing tickers directly. Addendum on ADR 0011.

So a backtest's horizon is ~80 days regardless of what the odds side offers —
~1,200 MLB games, above the gate's 300. Historical costs **10 × markets ×
regions**, so h2h-only is 20 credits a snapshot and the reserve affords ~380.
**Backtest rows must never count toward the gate's 300** — see the plan in
NEXT.md before building any of it.

## DEPLOYED (2026-08-09, 04:07Z) — and the boot lines were read, at last

Live is on `e885bca`. One machine `started`, 1/1 checks, same machine ID so it
restarted in place on the volume, gate locked, `execution_available: false`,
five pages 307 → `/login`, `/api/orders` 401 with and without a forged bearer.

**The entire first pass is 10 log lines. It was 963.** Nothing is buried any
more, and three things that had never been observed are now on the record:

    [entrypoint] instance_mode=live db=/data/cockpit.db
    [migrate] /data/cockpit.db already at schema v5
    INFO backend.api.routes: API starting: instance_mode=live live_trading_enabled=False
    INFO run_loop: starting loop: full pass every 900s, quote pass every 15s ...
    WARNING backend.kalshi.discovery: 317 unrecognised competition_scope value(s)
        across 962 series ... (56 named, 261 counted)          <- one line, was 962
    INFO backend.kalshi.discovery: discovery: 167 priceable events;
        unknown_scopes=962; rejected ...                       <- FIRST TIME EVER
    ... sweep decision, pricing pass, CLV, scoring, settlement, pass 1 ok

- **`already at schema v5` is now a reading, not an inference.** It had only ever
  been argued from effects.
- **The `discovery:` summary appeared in production for the first time**, in the
  same millisecond as the warning that used to destroy it. That is the burst
  hypothesis confirmed by the fix: the line was always emitted and never arrived.
- The db path is `/data/cockpit.db`, not `/data/live.db` as older notes said.

First pass: `recommendations: 4, suppressed: 4, surfaced: 0, unchanged_confirmed:
36`, `clv_scored: 0`, `rows_joined: 190`. See the CLV watch item below — 190 is
the residue, and nothing new has scored yet.

## Start here — one reading, after a full day

The 20K key is installed and `f1fb326` is deployed (2026-08-09 05:36Z). The
budget is no longer the constraint: the first pass fired a sweep, stored 626
quotes, and took linked games 10 → 16 and recommendations 4 → 24. Detail at the
top of `tasks/NEXT.md`.

    gh workflow run Ops -f instance=live -f action=logs

**Read `gate progress (24h)`.** It moved `no_edge` 161 → 177 within two passes
and `actionable` is still 0. Over a full day, one of two things is true:

- **`actionable` starts growing.** The gate is finally accumulating and the next
  question is `clv_rows_joined`, still pinned at 190.
- **`actionable` stays 0 while `no_edge` climbs into the thousands.** That is the
  project's answer, honestly obtained, and it is worth as much as a yes. Say so
  plainly rather than reaching for another knob.

**Also check `stale_odds`.** It should stop dominating the suppression
breakdown. If it does not, the sweeps are firing but not landing where the
fixtures are, and `odds/timing.py` is the place to look.

**And watch the log volume** — quote passes now run every ~22s, ~12,000 lines a
day, so the 100-line buffer covers ~12 minutes. See the note in `NEXT.md`; the
`discovery:` line is the redundant one.

### Also answered this session: candlestick retention is ~80 days

`scripts/measure_candlestick_retention.py`, free. Every bucket to 79 days serves
bars; at 80+ the market is gone entirely — not delisted, *gone*, verified by
constructing tickers directly. Addendum on `docs/adr/0011`.

Nothing changes for scoring (80 days is far more than the path needs, and it
refutes the worry that some of the 190 unscoreable rows had aged out). It is the
binding horizon for a **historical-odds backtest**, which is the open idea: ~80
days is ~1,200 MLB games, still well above the gate's 300. Costing and the rule
it must not break (backtest rows must never count toward the 300) are in
`tasks/NEXT.md`. Not built — deliberately, pending this number, which is now in.

---

## The gate is blocked by odds credits — the finding that led to all of the above

Live is on `a133584` and answered this on its first pass (04:38Z):

    gate progress (24h): actionable=0 of 300 needed, no_edge=161, suppressed=265;
    suppressed by: stale_odds=256, too_few_books=73, no_market_width=73,
                   edge_within_method_noise=4

**No guard is miscalibrated.** `stale_odds` is ~97% of suppressions and is the
16-credit budget showing up as a row count: ~2 sweeps a day, 15 minutes each, and
a full pass every 900s regardless — so ~94% of rows are priced against a
consensus that has already aged out, and refusing them is correct.

**The rows that did have fresh odds said `no_edge` 161 times and `actionable`
0 times.** That is the premise of the project holding, not a fault.

So the 300-game floor is not reachable by waiting. The options are in
`tasks/NEXT.md` — pay for more odds credits, spend the existing budget better
(scheduling, not code), or accept that the record accumulates at zero. **Do not
relax `MAX_ODDS_AGE_S`**; that manufactures edges into the record.

This needs Joe's call, not more building.

## The check this file used to open with — done

**The dedupe holds; zero new warnings on the second pass.**
See the top of `tasks/NEXT.md` for the evidence and for what it turned up
instead, which was bigger than the check:

- The unknown-scope population is **962 pairs over 317 scopes**, not the 94 this
  file used to claim. The 94 was the ~10% of a 90ms burst that Fly's log
  pipeline did not drop. The exclusion is still correct — nothing priceable is
  being dropped — but the sentence "none of them a sport" was drawn from a
  sample nobody knew was a sample.
- **Fly drops log lines under a burst, and takes neighbours with it.** The
  `discovery:` summary has never appeared in production despite being
  unconditional and verified to emit locally. Absence in `flyctl logs` is not
  evidence a line was not emitted.
- Fixed in `f7adbad`: the first pass now emits **2 lines where it emitted 963**.

Both were verified against the deployed instance afterwards — see the top of
this file.

## Then: what actually moves the gate now

The gate needs four things. Two just changed status:

| Condition | State |
|---|---|
| ≥300 scored **games** | possible — was structurally impossible. **Not yet shown to accumulate**: the 59 was one retroactive batch and the next full pass scored 0. See NEXT.md. |
| positive CLV surviving the always-valid bound | measurable for the first time |
| `fee_predicted == fee_actual` on every fill | **blocked — needs real fills** |
| fresh data | fine |

So the binding constraint is no longer code. It is **the four fee-calibration
trades** — minimum-size orders at ~10c/30c/50c/80c in the Kalshi app, a few
dollars, which read the true fee off `average_fee_paid` in the V2 order
response. Joe has pre-authorised these; they have not happened. Until they do,
the gate cannot open however much CLV accumulates.

Worth telling him that plainly rather than building around it.

## Watch, over the next few days

- **The scored ratio.** 59 of 249 was the *backlog* being scored retroactively,
  and one step is all it has taken so far: the next full pass scored 0 and
  `rows_joined` fell to exactly the 190 residue. The binding quantity is
  `recommendations` — the pass writes 0–1 new rows and confirms ~40 existing
  ones, and only a *new* row can score. Read `rows_joined` and `recommendations`
  together; `rows_joined` pinned at 190 means nothing fresh is scoring.
- **`surfaced` is still 0**, and has always been. That is the honest no-edge
  result, not a fault. Everything downstream of it — the agent fleet, the
  settlement pass, the exposure cap, `ws.py` — is wired and idle for that one
  reason.
- **Candlestick retention.** Some of the 190 may be unscoreable because their
  candles aged out rather than because of the ordering rule. Nobody has measured
  Kalshi's retention window.

## Unbuilt, if there is time

- **Research screen** — Scout findings with sources and timestamps.
- **Playbook screen** — lessons, config versions, proposals awaiting approval.

## Traps that bite, from this session specifically

- **Capture the payload before writing the parser, and point the capture at the
  states the code will branch on.** `?status=settled` returns markets whose
  `status` field reads `finalized`; matching `"settled"` would have settled
  nothing forever. The 247 existing fixture markets were all `active` and could
  say nothing about it.
- **When adding a `NOT NULL` column, grep every `INSERT OR IGNORE INTO` that
  table.** v4 turned the demo seeder into a silent no-op — zero settlements
  written, count of 400 returned.
- **Do not put a comment immediately above the last column of a table.**
  `DROP COLUMN` rewrites the stored `CREATE TABLE` text and leaves the comment
  dangling. It turned 72 tests red.
- **A new column makes its own production writer untestable.** Three guards
  passed their disable-check because every fixture set the column by hand. Write
  the writer test, the exclusion test and the migration test *before* updating
  fixtures.
- **A demo deploy cannot test a migration.** The entrypoint seeds before it
  migrates, and `seed_all` calls `init_db`, which builds the database at the
  current version. Demo proves the image boots, nothing more.
- **Never run `run_chain.py` or `run_loop.py` without `--no-odds`.** ~16 credits
  a day, shared with live.

## Open, recorded rather than acted on

- **`ws.py` has still never opened a socket on live.** It cannot until a row
  surfaces.
- **Exposure is fee-exclusive while the cap is spent fee-inclusive (~2%).**
  Re-costed while migrating for v4 and deliberately left open.
- **In-play is still an open question** — Joe rejected closing it. The three
  guards stay on while it is open; reopening means designing the regime,
  starting with what replaces the closing line.
- Local `.env` has `DISCORD_BOT_TOKEN`/`DISCORD_CHANNEL_ID` but the code reads
  `DISCORD_WEBHOOK_URL`. Live is configured correctly; local runs only.
- **One combo price lookup** still needs Joe — `POST .../lookup`, no money,
  yields a measured same-game correlation.
