# Start prompt — paste this to open the next session

Written 2026-08-08, end of the session that wired up the agent fleet, made
placement idempotent, and deployed both instances on `89bf56a`.

Everything below is the prompt. Paste it whole, or just say *"read start.md and
follow it"*.

---

Read CLAUDE.md, tasks/NEXT.md, and tasks/lessons.md first. NEXT.md is the
actionable checklist; todo.md is just the build log. Start with the top handoff
in NEXT.md — it carries everything below in more detail.

Where the last session left off:

- main is `89bf56a`, 1,243 tests, ruff green, CI green on every push.
- **BOTH INSTANCES ARE DEPLOYED, on `89bf56a`** — for the first time in a
  while, live is not behind. demo https://kalshi-cockpit-demo.fly.dev, live
  https://kalshi-cockpit.fly.dev. Gate locked, `execution_available` false,
  restarts=0, one machine, volume attached.
- The v2 → v3 migration ran on the live volume. `ANTHROPIC_API_KEY` is set as
  a Fly secret and live reports `agent_fleet_configured: true`.
- Landed: the agent fleet wired to the pricing pass (reviews before it
  persists), idempotent order placement (ADR 0009), Ops hardening, the
  `agent_fleet_configured` health field, per-step migration coverage.

## Verify these first — three claims of mine that production has not shown me

1. **I never saw `[migrate] ... migrated v2 -> v3` in the live logs.** I
   inferred it from the runner executing passes, which is decisive — `open_db`
   refuses an unrecognised schema version, so a v2 database under v3 code
   would kill the runner — but it is an inference. The next boot should log
   `[migrate] /data/live.db already at schema v3`. Confirm that string.
2. **I never saw `INFO backend.api.routes: API starting: instance_mode=live`.**
   Proven on demo from identical code, not observed on live. `flyctl logs
   --no-tail` returns a short buffer and the boot had scrolled past. Any
   restart puts it at the top of the stream.
3. **The agent fleet has NEVER run on live.** `surfaced` has always been 0, so
   `skeptic_reviewed` is structurally 0 and the fleet has cost nothing. The
   tell is `skeptic_reviewed` / `skeptic_blocked` in the pricing-pass log line.

## Then pick this up: the paper settlement path

It is the last open item in NEXT.md section 2 and the prerequisite ADR 0008
named for making `max_exposure_dollars` bind before a live order exists.

**Do NOT treat this as plumbing. It is a measurement decision and it deserves
an ADR before code.** The hard parts, in the order they bite:

1. **Did the paper order fill?** A dry run never rests in the book, so "did it
   fill" has no observed answer. Assuming a fill at the limit flatters the
   record, and the record is the entire product — `tasks/lessons.md` already
   has the entry about a paper fill that live would have refused quietly
   poisoning the evidence. Whatever you choose, the assumption must be a
   stored, flagged column, so the record can be re-analysed under a different
   one later.
2. **What settles it?** Kalshi's own market result — `/markets/{ticker}`
   carries `result` and `status`. `backend/scoring.py` already runs a pass that
   fetches closing lines from candlesticks; a settlement pass is its sibling
   and costs no odds credits.
3. **`settlements` has no order reference.** The exposure query releases
   capital for every order on a ticker as soon as any settlement row for that
   ticker exists. Fine while there is one order per ticker and wrong the moment
   there are two. Either add the column (schema v4) or document the
   approximation loudly — do not leave it implicit.
4. **Should paper exposure count toward the cap?** ADR 0008 said no, and said
   why: nothing settles a paper position, so exposure could only ratchet up
   until the endpoint refused everything with no way to release it — a cap that
   can only close is an off switch. Settlement is what changes that argument.
   Re-decide it deliberately and write down which way and why.
5. **The trap: paper P&L must not become a second edge number competing with
   CLV.** The gate is built entirely on CLV. A paper P&L that looks like
   evidence, is easier to read, and has none of the noise discipline is exactly
   how the wrong number gets believed — see `lessons.md` on a correct statistic
   sitting beside a contradicting verdict. State in the module what paper P&L
   does **not** establish.
6. **`fills` is for real fills.** `fee_actual` cannot be measured from a paper
   fill, and that table's job is measuring `fee_predicted` against `fee_actual`.

## Constraints that bite

- The Odds API budget is ~16 credits/day and shared with the live instance.
  **Never run `run_chain.py` or `run_loop.py` without `--no-odds`.**
- **Deploying.** `gh workflow run Deploy -f instance=demo` works from the
  session. The **live** deploy is blocked by the permission classifier. The `!`
  prefix did not work either — it dispatched nothing, twice, and its output is
  not visible to Claude, so it cannot be diagnosed from inside. Use the
  browser: Actions → Deploy → Run workflow → `live` → type `kalshi-cockpit`.
  **Demo first as a canary, always** — it caught a crash loop this session that
  would have taken the live volume down.
- **When changing a shared data shape, grep outside `backend/`.**
  `_MIGRATIONS` became a dataclass, every reader in `backend/` was updated, and
  the one in `scripts/` — the only reader that runs at boot — was not. That is
  what crash-looped demo. `scripts/` is a boot path with no import-time
  coverage beyond a `--help` smoke test.
- **Verify every new guard by disabling it and watching the test fail.** Two of
  mine this session were wrong until I did, and one disable-check caught a test
  of my own that was passing through an exception path rather than the
  behaviour it claimed to test.
- Don't take a subagent's headline claim as fact before it goes in
  `lessons.md`.

## Open, recorded rather than acted on

- **`ws.py` has still never opened a socket on live.** It cannot until a row
  surfaces. Whether a genuinely empty real book looks identical to an
  unrecognised ticker is still unmeasured; one live subscription to an illiquid
  real market settles it at zero odds credits. Do **not** "fix" it by treating
  a missing key as an empty book.
- **Exposure is fee-exclusive while the cap is spent fee-inclusive (~2%).**
  Still judged not worth a migration — but if you are migrating for settlement
  anyway, that calculus changes.
- Local `.env` has `DISCORD_BOT_TOKEN`/`DISCORD_CHANNEL_ID` but the code reads
  `DISCORD_WEBHOOK_URL`. Live is configured correctly; local runs only.
- Two items still need Joe and neither is urgent: **one combo price lookup**,
  and the **four fee-calibration trades** in the Kalshi app.
