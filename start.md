# Start prompt — paste this to open the next session

Written 2026-08-09, end of the session that built the paper settlement path and
fixed the CLV horizon.

Everything below is the prompt. Paste it whole, or just say *"read start.md and
follow it"*.

---

Read CLAUDE.md, tasks/NEXT.md, and tasks/lessons.md first. NEXT.md is the
actionable checklist; todo.md is just the build log. The top of NEXT.md carries
this session's handoff in more detail.

## State

- `main` is `aa9474a`. 1,302 tests, ruff green, `dbt build` 11 nodes green, CI
  green on every push.
- **Demo is deployed on the current image and verified** — five pages 200,
  `instance_mode=demo`.
- **Live is still on `89bf56a`** and is thirteen commits behind. It carries two
  migrations it has never run: v3 → v4 → v5.

## The one thing outstanding: deploy live

The classifier blocks the live deploy from a session and blocks
`Ops -f instance=live` intermittently, so this needs Joe:

    Actions -> Deploy -> Run workflow -> live -> type kalshi-cockpit

**Use the browser URL, not the GitHub app.** Last time it dispatched *nothing* —
no run was created at all, which is worse than the previously-recorded failure
where `confirm_live` arrived empty and the guard stopped the job. Check a run
actually appears in `gh run list --workflow Deploy` before believing it went.

Demo cannot pre-test the migrations, and it is worth knowing why rather than
trusting the canary further than it goes: the entrypoint **seeds before it
migrates**, and `seed_all` calls `init_db`, which builds the database at the
current version. So `migrate_db.py` on demo is a no-op by construction. What
demo proves is that the image boots. Live's volume is the only real test of
v3 → v5, and what backs it is that the boot script was run against genuine v3
and v4 databases carrying rows, twice each, plus a subprocess test.

## Then verify these, in this order

1. **The two boot lines**, unobserved for three sessions:

       [migrate] /data/live.db migrated v3 -> v5
       INFO backend.api.routes: API starting: instance_mode=live

   They were unreadable because **98 of the 100 lines in the log buffer** were
   one repeated discovery warning. That is fixed; if they are still missing,
   something new is flooding the stream rather than the window being too small.

2. **`clv_scored` stops being 0.** This is the headline and the reason the
   horizon work happened. Live has joined 249 rows and scored **none**, on every
   pass, because the closing line was read an hour before kickoff and no
   recommendation can exist that early. The first non-zero `clv_scored` will be
   the first evidence this project has ever recorded.

   If it is still 0 after a full pass, read `clv_skipped_entry_after_close`
   before anything else — the composition may have moved again.

3. **The pass line now carries `skeptic_reviewed` / `skeptic_blocked` and
   `settle_*` keys.** All will be 0. That is honest: nothing has ever surfaced,
   so the fleet has nothing to review and there are no paper positions to
   settle. They print now rather than being inferred from `surfaced: 0`.

## What landed this session

- **ADR 0010 + `backend/settlement.py` + schema v4** — paper positions close
  against Kalshi's own `result`, and `max_exposure_dollars` binds in production
  for the first time, on paper, scoped so live and paper never pool.
- **ADR 0011 + schema v5** — the close is the last pre-game quote. Primary
  horizon 1.0 → 0.0, control 6.0 → 1.0, and `recommendations.clv_horizon_hours`
  so the column can never become a silent mixture.
- **The log flood and the missing fleet counters** — both were comments claiming
  a property the code one line away did not provide.

## Traps that bite, from this session specifically

- **Capture the payload before writing the parser, and point the capture at the
  states the code will branch on.** `?status=settled` returns markets whose
  `status` field reads `finalized`; matching `"settled"` would have settled
  nothing forever. 247 existing fixture markets were all `active` and could say
  nothing about it.
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
- **Never run `run_chain.py` or `run_loop.py` without `--no-odds`.** ~16 credits
  a day, shared with live.
- Don't take a subagent's headline claim as fact before it goes in
  `lessons.md`.

## Open, recorded rather than acted on

- **`ws.py` has still never opened a socket on live.** It cannot until a row
  surfaces.
- **Nothing has ever surfaced on live**, so the settlement pass, the agent
  fleet and the exposure cap all have nothing to act on yet. All three are
  wired and report zero honestly.
- **Exposure is fee-exclusive while the cap is spent fee-inclusive (~2%).**
  Re-costed while migrating for v4 and deliberately left open.
- Local `.env` has `DISCORD_BOT_TOKEN`/`DISCORD_CHANNEL_ID` but the code reads
  `DISCORD_WEBHOOK_URL`. Live is configured correctly; local runs only.
- Two items still need Joe and neither is urgent: **one combo price lookup**,
  and the **four fee-calibration trades** in the Kalshi app.
- Unbuilt screens: **Research** (Scout findings) and **Playbook** (lessons,
  config versions, proposals awaiting approval).
