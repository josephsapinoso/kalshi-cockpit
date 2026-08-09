# Start prompt — paste this to open the next session

Written 2026-08-09, end of the session that built the paper settlement path,
fixed the CLV horizon, and deployed both instances.

Everything below is the prompt. Paste it whole, or just say *"read start.md and
follow it"*.

---

Read CLAUDE.md, tasks/NEXT.md, and tasks/lessons.md first. NEXT.md is the
actionable checklist; todo.md is just the build log.

## State — and the thing that finally happened

`main` is `7eae154`. 1,302 tests, ruff green, `dbt build` 11 nodes green, CI
green on every push. **Both instances are deployed on the current image**, live
included: `restarts=0`, one machine, volume attached, gate locked,
`execution_available: false`, five pages 307 → `/login`, `/api/orders` 401 with
and without a forged bearer.

The first live pass on the new image:

    CLV scoring at 0.0h horizon: {'scored': 59, 'skipped_entry_after_close': 190,
                                  'rows_joined': 249}

**`scored` has been 0 for the entire life of this project.** The evidence layer
is recording for the first time. The 190 skipped are the honest residue ADR 0011
predicted — rows created after their market's closing line was observed.

Also confirmed running: `settlement pass: {'positions_open': 0, 'settled': 0,
'still_unresolved': 0, 'refused': 0}`, and `skeptic_reviewed` /
`skeptic_blocked` now print in the pricing-pass line instead of being inferred
from `surfaced: 0`.

## Start here — deploy live, then read the boot lines

That check is **done. The dedupe holds; zero new warnings on the second pass.**
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

**`main` is `f7adbad` and live is still on `7eae154`.** So:

    gh workflow run Deploy -f instance=live -f confirm_live=kalshi-cockpit
    gh workflow run Ops -f instance=live -f action=logs

`[migrate] /data/live.db already at schema v5` and `API starting:
instance_mode=live` have been unobserved for three sessions, and nothing was
ever wrong with them. This is the first deploy whose boot lines have a fair
chance of surviving the stream. Also expect one aggregated warning naming ~56
scopes, and a `discovery:` line — which will be its first appearance ever.

I did not deploy live: it is on the list that needs asking, and Joe was away.

## Then: what actually moves the gate now

The gate needs four things. Two just changed status:

| Condition | State |
|---|---|
| ≥300 scored **games** | now growing — was structurally impossible |
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

- **The scored ratio.** 59 of 249 is the *backlog* being scored retroactively.
  New rows are created 45–15 min before kickoff and scored against a line at
  kickoff, so most should now score. If the ratio does not improve on fresh
  rows, the composition moved again — read `clv_skipped_entry_after_close`
  first.
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
