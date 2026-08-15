# Next — your checklist

## 2026-08-15 — PROPS ARE BUILT AND DEPLOYED, ALL FOUR SLICES. It is running; the next move is to read what it did.

`8febd24` (slices 2-3) and `1fb6850` (slice 4). 2,626 tests pass, 10
`xfail(strict=True)`, ruff clean. 21 mutations run, 20 killed, 1 recorded as
semantically equivalent.

**The chain is whole:** discovery admits the five MLB prop ladders and writes
`market_type = 'prop'` with a parsed player; a prop event inherits the link its
own moneyline event earned; a served team sweep buys the props for the same
fixtures; and pricing devigs one (player, line) at a time into `fair_prices`
with `outcome_description` and `outcome_point` populated. An offline end-to-end
test runs all of it on captured bytes, no network, no credits.

**NOTHING NEW IS SURFACED, and that is the expected result.** At the deployed
`TAKER_COEFFICIENT = 0.070` the scoping probe found zero prop rows clearing
against a real consensus. This slice records props so they can be scored on
**CLV against Kalshi's own close**, which is rule 3 and needs weeks of calendar
— which is the whole argument for building it before the fee question resolves.

**No config change is needed.** An earlier reading of this session said
`ODDS_DAILY_CREDIT_BUDGET` had to be raised; it does not. Live is **400/day and
13,000/month**, and two prop windows a day is ~324 and ~9,700. The free-tier 16
in `.env.example` *would* refuse every prop event, which is why the note there
now spells out both numbers. **The figure to watch is the monthly one** once a
second league's team sweeps return in the autumn.

### Three things the build found that were not in the plan

1. **`floor_strike` retired a computation.** Kalshi publishes an `N+` prop's
   floor as `N - 0.5`, which is exactly the `point` a sportsbook quotes for the
   same rung — 259 of 259 on the captured fixture, both series. So the join is
   an equality between two published numbers, the v8 migration is **one** column
   (`player_name`) rather than two, and there is no derived threshold for a
   second representation to disagree with. `tests/test_discovery.py` pins the
   identity, so a Kalshi change to `floor_strike` goes red instead of shifting
   every prop comparison by one rung.
2. **`competition_scope` on a prop is the statistic, not the fixture** —
   `"Strikeouts"`, `"Total Bases"`, one string per series. That is why the
   allowlist keys on the series ticker. Admitting props through `FIXTURE_SCOPES`
   would need one capture per series and would re-admit every other series
   Kalshi ever gives the same label. `PROP_SCOPES` holds **only the two values
   read from a payload**; the other three series' spellings are unknown and are
   not guessed.
3. **Two existing tests were built on invented series names that turned out to
   be real.** `KXMLBHIT` and `KXMLBHR` were the examples of an *unrecognised*
   scope, and seven tests went red the moment the allowlist claimed them. Now
   `KXMLBDOUBLES`/`KXMLBTRIPLES`, with the constraint written into the fixture's
   docstring.

### What is left, in order

1. ~~**One deploy from Joe.**~~ **DONE 2026-08-15.** Demo first
   (run `31900459254`, 2m6s, all checks green including `POST /api/orders` →
   403), then live (run `31900575709`, 48s). Live health reports
   `instance_mode: live`, `live_quotes_available: true`. **The v7→v8 migration
   ran**: `docker/entrypoint.sh` calls `scripts/migrate_db.py` under
   `set -euo pipefail` before uvicorn binds, so a failed migration would have
   killed the boot and the workflow's `/api/health` poll would have timed out.
   uvicorn answering is the proof, not the health payload — that endpoint
   touches no database by design. **The `player_name` column was not inspected
   on the live volume**, because reads are auth-gated and this session held no
   token; that check belongs to step 2 below.
2. **Read `odds_sweep_log` after the first live pass.** Every prop decision
   writes a row prefixed `props:` — served, or skipped with the reason. A budget
   refusal is the failure mode that looks exactly like success from every other
   screen.
3. **The one-sided alternate feeds.** 18 of 20 rungs in the captured payload
   have no two-sided book, and the live figure was 174 of 222. Recovering them
   means estimating a book's overround from its own two-sided primary and
   applying it to that book's one-sided alternates — **~4.6x the comparisons for
   zero extra credits**, and an assumption that needs `pre-registrar`, not a
   patch.
4. **Score the first prop rows on CLV** once a slate has settled, and register
   the measurement *before* looking. Props are baseball, charged `k = 0.035`,
   priced here at 0.070 — so every prop edge on the record is understated by up
   to a factor of two on the fee component, deliberately.

**The fee window is still the gate on all of it.** The second MLB observation
window, >=3-4 weeks after 2026-08-14, one 1-contract fill. Nothing in this build
changed `TAKER_COEFFICIENT` and nothing in it should.


## Standing facts that outlive any one session

These are not tasks and they never get ticked. They are the things that cost a
session real time when it meets them cold.

- **The repository is public.** Every push publishes to the world immediately.
  Verified 2026-08-15: GitHub reports `visibility: PUBLIC`. Before committing a
  measurement, fixture, log capture or screenshot, ask whether it should be
  world-readable. Screenshots of the live cockpit are the sharp edge, because
  one live run away is a real position or a real bankroll.
- **GitHub push protection is on, and it is a guard rather than an obstacle.**
  A push carrying anything that looks like a credential is rejected. Do not
  bypass it. Stop, look at what tripped it, and rotate the secret if it is
  real. Nothing in the existing history trips it: GitHub's scan of the full
  history returned zero alerts, independently confirming the gitleaks audit.
- **The live instance holds real money, and its reads require authentication.**
  `frontend/src/middleware.ts` answers an unauthenticated `/api/*` with a 401,
  so every screen and every query against live needs a session from `/login`.
  `/api/health` is the exception and touches no database.
- **Deployment needs no laptop.** `.github/workflows/deploy.yml` is a
  `workflow_dispatch` button. Deploying live requires typing the app name into
  `confirm_live`, because a dropdown mis-tap on a phone is a plausible way to
  deploy the money instance by accident.

---

## Still open, and what each one is waiting on

Four things are unfinished. Three of them are waiting on time or on Joe rather
than on work, which is worth knowing before picking something up.

1. **The fee window — the gate on everything else.** A second MLB observation
   window needs one 1-contract fill, at least three to four weeks after
   2026-08-14, to settle which attribute carries the split between the charged
   coefficient and the measured one. `TAKER_COEFFICIENT` stays at 0.070 until
   then, deliberately overstating the bar. See
   `docs/adr/0027-the-cost-headroom-is-an-upper-bound-pending-h4.md` and
   `docs/adr/0028-the-fee-hedge-is-retired-and-the-grid-is-deci-cent.md`.
   **Waiting on the calendar.**
2. **The first props sweep log.** Every prop decision writes a row to
   `odds_sweep_log` prefixed `props:`, recording either that it was served or
   the reason it was skipped. A budget refusal is the failure mode that looks
   exactly like success from every other screen, so this is the one reading
   that cannot be skipped. **Waiting on Joe's login.**
3. **The one-sided alternate feeds.** Most rungs quote only one side and
   `consensus_devig` needs both; the live figure was 174 of 222 dropped.
   Recovering them means estimating a book's overround from its own two-sided
   primary and applying it to that book's one-sided alternates. That is roughly
   4.6 times the comparisons for zero extra credits, and it is an assumption
   that needs registering with `pre-registrar` before anyone writes code.
   **Waiting on a registered assumption.**
4. **Whether NBA and NHL game series exist.** `scripts/capture_fixtures.py`
   still caps at `MAX_PAGES = 40` and neither `KXNBA` nor `KXNHL` appears in
   `kalshi/discovery.py`. Partial evidence says the NBA product is real
   regardless: `kalshi/combos.py` carries `KXMVENBASINGLEGAME` with 8,622 legs.
   **Waiting on the seasons to open**, since a re-run today measures the
   off-season again.

---

## Where the history went

Every session note from 2026-08-08 through 2026-08-14 now lives in
`tasks/archive/NEXT-through-2026-08-14.md`. It was moved on 2026-08-15, when
this file had reached 6,229 lines and the live checklist at the top had
disappeared under months of commentary.

Nothing was deleted. Go there to recover the reasoning behind a decision, and
read it with its dates in mind — later sections in it routinely correct earlier
ones. Where the archive disagrees with `CLAUDE.md`, with `docs/adr/`, or with
this file, those win.
