# Next — your checklist

## HANDOFF (2026-08-08, 05:2xZ — deployed, and the demo found the bug for us)

**Both instances are on the new image.** Demo verified, live verified, live
machine `started`, checks 1/1, **restarts 0**, volume attached.

    demo  https://kalshi-cockpit-demo.fly.dev   five pages 200, no error text,
                                                instance_mode=demo, forged
                                                bearer on /api/orders -> 403
    live  https://kalshi-cockpit.fly.dev        five pages 307 -> /login,
                                                /api/orders 401 with and
                                                without a forged bearer

    {"status":"ok","instance_mode":"live","live_trading_enabled":false,
     "execution_available":false,"notifications_configured":true,
     "live_quotes_available":true}

**The migration ran.** `unchanged_confirmed: 50` on the first pass is a v2
column doing its job, so the schema change reached the volume before uvicorn
opened it.

### The two-step deploy paid for itself on its first use

The demo crash-looped: `can't open file '/app/scripts/migrate_db.py'`, exit 2
under `set -e`, ten restarts, machine gone. `.dockerignore` denies `scripts/*`
and allowlists by hand; the allowlist named `run_loop.py` and nothing else,
because it was written when the entrypoint ran one script. **Live would have
taken the same crash loop on the volume holding the only copy of the record.**

`TestTheEntrypointRunsWhatItMustRunFirst` asserted the migration runs before
uvicorn and passed throughout — it was true, and the file it named was not in
the image. The allowlist is now derived from the entrypoint rather than
maintained by hand. See `tasks/lessons.md`.

**Also fixed before the live deploy: the diagnostic you were told to watch was
counting the wrong population.** `observe_pass_duration` ran on every pass and
always compared against the *fast* interval, so the first full pass — 167
events, 1,426 markets, 228 rows joined, 14.9s, healthy, window closed — raised
`passes_over_quote_budget`. Full passes happen every 900s forever, so that
counter would have been ~96 routine entries a day and could never have shown
the one condition it exists for. `kind` is now a required argument and full
passes get their own counter.

### Read this before believing the ticker is verified

**`ws.py` still has not opened a socket in production.** `live_quotes_available:
true` says the hub *loop* is running, which is exactly what it was changed to
mean — but `_one_cycle` returns early with `{"type": "idle"}` when no row is
bettable, and with `surfaced: 0` and the odds budget spent there have been no
bettable rows. So no WebSocket has been opened on the live instance, and the
things you asked me to watch for — reconnect loops, memory growth on a 1GB
machine — **cannot be observed yet.** They become observable the first time a
window opens with a surfaced row, not before.

### The gate's population — reported, not yet decided

Done as you specified: **both groups side by side, with `n` for each, before
anyone changes which one the floor counts.** `gate.clv_by_population` returns
`actionable` / `no_edge` / `suppressed` / `pooled`, the three matching the
digest's own framing so the two screens cannot describe the record differently.
The gate's `scored_recommendations` detail now carries
`actionable Ng/Nr, no_edge Ng/Nr, suppressed Ng/Nr` beside the aggregate, and
when nothing actionable has been scored it says so outright.

**The digest had the same defect and it is the one that reaches your phone.**
`_digest_stats` ran its own SQL with a comment saying it counted "the way the
gate counts it" — true, and the gate's way was the mixture. It now calls
`clv_by_population` rather than agreeing with it, per the repo's rule about
deleting one of two paths. The Discord embed reports the actionable count as
the headline with the pooled count beside it and the gap named.

Fixing it surfaced a fixture that could not have been real: a test set
`clv_tenths` without `clv_scored_ms`, which the digest's looser predicate
accepted and `score_recommendations` can never produce — it writes both in one
UPDATE.

**Decided (you said "decide for me"): the floor counts `actionable`.** Both CLV
conditions now read that population. `docs/adr/0005-the-gate-counts-actionable-
games.md` has the full reasoning; the short version is that it is a *safety*
change, not a relabelling — a systematic CLV among refused rows moves the
pooled mean rather than blunting it, and `suspicious_edge` rows are the
likeliest carriers, so pooled they could arm real money on evidence about bets
the strategy declines to make. It also moves the gate strictly further away in
both conditions: the actionable set is a subset, so the floor is harder to
reach, and `always_valid_multiplier` *grows* as `n` shrinks (9.84 at n=20
against 3.66 at n=300), so a small actionable sample clears a taller bar. A
money guard that changes should change in that direction.

It reads **0 of 300** and will for a while. The breakdown sits beside it.

**And it caught a test fixture arming the gate from refused rows.**
`test_quote_refresh.armed_db` built 400 scored games at
`suggested_contracts=0` — "no edge here", four hundred times — and that
satisfied the floor, so every order-path test below it ran through a gate
opened by evidence the strategy would never have acted on. A gate fixture has
to be built from the population the gate counts.

### What to look at, and when

The budget day rolls at **10:00Z**. Until then no sweep can fire (`24 of 16
credits spent since 10:00Z`), so the window stays closed, no quote passes run,
and `surfaced: 0` means nothing at all. After the first sweep of the new day:

- `surfaced` — this is the first time the sentence "still 0 after a full window
  with the fast cadence running is the honest no-edge result" can be true.
- `passes_over_quote_budget` — now genuinely means the fast cadence is failing.
  `full_passes_over_limit_in_window` is the structural one and is expected to
  be nonzero, roughly once per window.
- The socket. First time `ws.py` runs for real.

**One number to keep an eye on that nobody has flagged yet:** the CLV pass
joined 228 rows and scored **0**, all of them `skipped_entry_after_close`. That
is the documented cost of requiring the entry to precede the close, and the
earlier run had 34 scored, so the scored rows are simply not re-joined — but
228/228 skipped is worth a second look if it does not move once games settle.

---

## Joe's asks, 2026-08-08 — four of them; two are done

Raised in chat while the quote-refresh work was landing.

1. **~~Stream the prices. Make the Board a ticker.~~ — done.** *"I'm thinking
   about this like a stock ticker. Billy Walters would like it."* And the
   sharper version: *"it seems like you're doing a lot to manage prices at their
   very small window snapshot, so wouldn't it just be easier to stream the
   prices in?"*

   He was right about the Kalshi half. `backend/live.py` is the hub, and
   **`backend/kalshi/ws.py` finally has a caller** — it was the fifth module in
   this project to be complete, tested and invoked by nothing. Verified against
   the live exchange: real book state for `KXNCAAFGAME-26SEP19MSUND-ND` arrived
   over the socket and out through SSE, and the depth it reported (640.95 at the
   yes ask) matches `yes_ask_size_fp` from the REST capture — an independent
   confirmation of the crossover.

   What it does **not** do, and this is the part to keep saying out loud:

   - **It does not widen the actionable window.** The fair value comes from a
     devigged sportsbook consensus at ~16 credits a day, 6 a sweep. Streaming
     Kalshi gives a live ask against a fair value up to fifteen minutes old.
     The window is an odds-budget fact and no amount of Kalshi streaming
     touches it. The banner and the feed header both say so.
   - **It does not replace the order-time refresh.** A browser's price is a
     client-supplied price and the server must never trust one. `POST
     /api/orders` re-reads the book itself; streaming means the two usually
     agree.
   - **The browser is given no arithmetic.** Edge and size are recomputed *on
     the server* by the same functions the order endpoint calls. Shipping the
     fee curve to TypeScript so the client could subtract it would put two
     implementations of a money calculation one refresh apart.
   - **A stopped ticker must look stopped.** Heartbeat every 10s regardless,
     `down` pushed the instant the feed dies and repeated on every heartbeat,
     and a client-side timer that treats total silence as a fault.

   **Verified end to end**, including the thing most likely to be silently
   broken: SSE survives Next's `/api/*` rewrite unbuffered — frames arrive
   exactly one heartbeat apart through the proxy, not in bursts.

   Two things left on it, neither blocking:
   - The hub prices against `exposure = 0` rather than reading the portfolio per
     frame. Display-only, and the order endpoint applies the real exposure, but
     the size on a card can therefore exceed what the server would accept once
     fills are persisted.
   - On a market with no book activity the cards keep their recorded prices
     until the first frame arrives. Correct, and it means "LIVE" can sit above
     a recorded price for a few seconds after a restart.

2. **~~A Kalshi-platform specialist agent~~ — done, and it earned its keep
   immediately.** `.claude/agents/kalshi-platform.md`. *"so that agent can check
   against everything we're doing to make sure everything is copacetic."*

   Pointed at the quote-refresh commit it found a defect I had introduced and
   two more besides — see the handoff below. It needs a session restart to
   register as a subagent type; until then it can be run by handing the file to
   a general-purpose agent.

3. **Is in-play betting viable?** See the item in section 3 — it is the largest
   of the four and the one with a real chance of a "no". Note that the order
   path now **refuses a started game** (added in response to finding 1 below),
   so nothing can leak into the record while the question is open.

4. **Is Python the right language everywhere?** *"if some other code language
   base works better in some places use that instead — Rust, C++, whatever."*
   Worth answering with a measurement rather than an opinion, and the repo's own
   rule applies: measure the style rule before believing it. The starting
   position, to be checked rather than assumed:

   - Nothing here has been shown to be compute-bound. The devig solvers, the
     copula, Elo — all microseconds on a ~100-game slate. The analytical half
     already runs in C++ via DuckDB.
   - The measured costs are network and budget: Kalshi REST round trips, a
     ~500ms `httpx.AsyncClient` construction (fixed by sharing it, not by
     rewriting), and 16 odds credits a day.
   - The one place latency genuinely decides money is stale-quote picking at
     ~400ms — and `tasks/lessons.md` records that as measured and refuted. It
     is a co-location problem, not a language problem.

   So the honest task is: `took_s` is already logged per pass; instrument the
   stages inside it, find where the wall clock actually goes, and only then
   consider rewriting a specific stage. A finding of "nothing is
   compute-bound" is a real answer and should be written down as an ADR so it
   is not re-litigated.

---

## HANDOFF (2026-08-08, later still — the price is live, and a review caught me)

**State:** 1,064 tests, frontend builds, all five pages fit 320/390px, Board and
ticker verified by rendering them against the live exchange. **Not deployed** —
the earlier migration has not shipped either, so the next deploy carries both.

Three things landed: the order-time quote refresh, the streaming ticker, and the
fixes from the Kalshi-platform review of the first one.

### The review found a defect I introduced, and it was the repo's own first rule

**Re-sizing at the live ask is one-sided.** An adverse move shrinks the order to
zero and refuses; a *favourable* move just buys more, up to what the engine
authorised. `size_position` is monotonic in price, so the re-derivation had a
refusal branch in one direction and none in the other — and the direction with
none is the one *"a large apparent edge is a bug until proven otherwise"* exists
for. An ask that fell six cents since the row was written is not six cents of
found money.

Fixed: `suppression.edge_ceiling_tenths` now runs at order time against the live
edge, using the engine's own config rather than a second constant.

**And the runner's in-play drop only covers rows it has not written yet.** A row
recorded ten minutes before kickoff keeps its size and stays inside the 900s
odds window well into the first quarter — and the refresh makes that worse, not
better, because the ask becomes a live in-play price while the fair value beside
it is a pre-game consensus. Measured in-play edges ran −200 to +68 tenths.
`recommendation_freshness` now carries the **sportsbook's** kickoff (joined
through `link_id`, never `kalshi_events.commence_ms`, which runs three hours
late) and the order path refuses a started game.

Three smaller ones, all from the same review:

- **Kalshi sends `"0.0000"`, not a missing field**, so the `live_ask is None`
  branch could never fire on a real one-sided book and the refusal that reached
  the screen said *"the price moved. Recorded 45c, live 100c"*. Now
  `is_valid_price`, with a message about there being no offer.
- The depth refusal claimed a fill guarantee the order does not have — plain GTC
  limit, no `time_in_force`, no cancel path anywhere in the repo. Reworded, and
  the thinness is logged.
- A 404 for an unknown ticker was served as 503, telling whoever is holding the
  phone to retry something that will never work.

**Still open from that review, recorded rather than fixed:**

- **The CLV price and the fill price are now different numbers.** CLV scores off
  `entry_ask_tenths`; the order goes out at the live ask. Nothing joins them
  because `orders` is still never written. The gate that arms real money is
  built entirely on CLV, so its evidence base and its executed bets would
  describe different prices. This is an argument for persisting orders *before*
  anything is armed, not after.
- **`_current_exposure_dollars` always returns `0.0`** for the same reason, so
  `max_exposure_dollars` does not currently bind in production even though it
  binds in the tests.
- One assumption still strictly unverified: no fixture ties `yes_ask_size_fp` to
  an orderbook NO-bid quantity *directly*. One call closes it —
  `GET /markets/{ticker}/orderbook`, compare the NO side's quantity against
  `yes_ask_size_fp`.

### Found while deciding whether to deploy — fixed, and it was the same shape

The hub's loop had no `except` around it, and `_load_subscriptions` opens the
database. `open_db` refuses an unrecognised schema version, **which is exactly
the state on the first boot after this deploy's migration** if the API comes up
before the runner has migrated. The task would have died, nothing would have
restarted it, and `/api/health` would have gone on reporting the ticker
available — because that checked `hub is not None`, a claim about construction.

A dead hub still answers `/api/stream/quotes` with snapshots and heartbeats,
both empty, which renders as a quiet market. That is the exact failure a ticker
introduces and the one the heartbeat exists to prevent, arriving through the
door nobody was watching.

Now: the cycle is wrapped, the failure is broadcast as `down` rather than only
logged, the loop retries, and health reports `is_running`.

### What to look at once it is live

- `live_quotes_available` on `/api/health` says whether the ticker is running —
  the loop, not the object. If it is `false` on the live instance, the hub died
  and the log has the reason.
- The feed header on the Board: `LIVE`, `FEED DOWN`, `FEED SILENT`, `NO LIVE
  ROWS`. `NO LIVE ROWS` is the expected state for most of the day.
- **The rewrite destination is read at Next's start, not at build**, and it
  defaults to `127.0.0.1:8000`. Both processes share a host in the image, so
  this is only a trap when running the halves on non-default ports locally — it
  presents as "Backend unreachable" or a 500 on the stream.

---

## HANDOFF (2026-08-08, earlier — the 30-second window is fixed)

**State:** 998 tests, `dbt build` 11 nodes green, frontend builds, all five
pages fit 320/390px. **Not yet deployed** — see "Deploying this" below, because
this one carries a schema migration and the boot order matters.

### What changed

The previous handoff's item 1 — *"the window is 30 seconds, not 15 minutes"* —
is done, by the two fixes it proposed as composing. They do compose, and neither
works alone.

**1. A second cadence.** `backend/runner.run_quote_pass` re-reads Kalshi,
re-prices against the odds already stored, and spends nothing. The loop now runs
a **full pass every 900s** and a **quote pass every 15s while the window is
open** (`backend/scheduler.Tempo`). Kalshi REST is unmetered; the 900s interval
was The Odds API's limit applied to a leg that never needed it.

**2. `last_confirmed_ms`.** A quote pass that re-derives an identical decision
stamps the existing row instead of writing a duplicate, so `persist_if_changed`
keeps the record clean *and* freshness stops measuring from `created_ms`. Three
new columns, all nullable: the instant, and **both** ages at that instant.

Measured on a simulated 930 seconds of passes (61 quote, 1 full) against a real
database with fake clients:

    recommendation rows      4        (not 248 — the dedupe still holds)
    confirmed                4/4
    quote age at the end     0.0s     (limit 30s)
    odds age at the end      1354s    (limit 900s — correctly expired)

That last line is the point as much as the others. **This does not widen the
window.** Fifteen minutes twice a day is `MAX_ODDS_AGE_S` and the credit budget,
and no amount of Kalshi polling changes it. What changes is that the fifteen
minutes are now usable throughout rather than for the first thirty seconds —
about 30 min/day of actionability instead of about 1.

Item 3 from the last handoff — **refresh the quote at order time** — is still
open and is still the real fix for execution. It closes the gap between "this
row was true 15 seconds ago" and "this row is true now", which confirmation
narrows and cannot close.

### Deploying this

**The migration must run before uvicorn.** `docker/entrypoint.sh` now does that
(`scripts/migrate_db.py`), and a test asserts the ordering. The reason it
matters: the API opens read-only and `open_db` refuses an unrecognised schema
version, so on the first boot after this change the live instance would 500 on
every page until the runner happened to call `init_db` — while `/api/health`
stayed green throughout, because it touches no database.

Verified against a synthetic v1 database with 128 rows: refused before, migrated
v1 → v2, 128 rows kept, all three columns present, second run a no-op.

`RUNNER_FAST_INTERVAL_S` defaults to 15. Do not raise it past 18 and do not
raise `MAX_KALSHI_QUOTE_AGE_S` — the loop refuses to start if the composed
worst-case gap exceeds the limit, and 30s is the right number for a venue quoted
by sub-200ms market makers.

### What to look at once it is live

- `pass` and `took_s` are now on every loop log line. If `took_s` on a quote
  pass approaches 8s the fast cadence stops keeping rows inside the limit;
  `Tempo.observe_pass_duration` logs a warning and counts it as
  `passes_over_quote_budget`.
- **`surfaced` should stop being structurally zero during a window.** It has
  always been 0, and part of that was that nothing could survive 30 seconds. If
  it is still 0 after a full window with the fast cadence running, that is the
  honest no-edge result rather than an artefact — which is the first time that
  sentence has been true.

---

## HANDOFF (2026-08-08, earlier)

**State:** 935 tests, `dbt build` 11 nodes green, **both instances deployed and
verified**. The four items from the last handoff are done — sweep timing, the
window on the Board, Discord wiring, and the scored-ratio investigation, which
turned up a defect rather than a transient.

First live pass on the new image:

    dropped_game_started: 9          the in-play guard firing on real data
    clv_scored: 34                   up from 8 at the start of the session
    sweep decision: no sweep -- 24 of 16 credits spent since 10:00Z

The odds budget for today was already spent by the old scheduler (plus 6 on a
local smoke test), so **the first sweep the new timing chooses will be after
10:00Z on the 8th.** That is the thing to look at first: whether it lands
20–45 minutes before a cluster of kickoffs rather than wherever the process
restarted.

`clv_scored` answers the last handoff's item 4. The 100%-unscoreable reading was
a transient: closing lines only exist for games that have started, so early in a
run every joined row is a late one. 34 rows are now scored and the count is
climbing.

  demo  https://kalshi-cockpit-demo.fly.dev   (public, no credentials)
  live  https://kalshi-cockpit.fly.dev        (login: APP_AUTH_TOKEN)

### ~~Pick this up first — the window is 30 seconds, not 15 minutes~~

**Done 2026-08-08.** Fixes 1 and 2 below are both implemented; see the handoff
at the top of this file. Fix 3 — refresh the quote at order time — is still
open. The original write-up is kept because it is the clearest statement of the
problem.

The premise of the last handoff was wrong and the fix exposed it. **Two limits
bound the actionable window and the tighter one decides it:**

    MAX_ODDS_AGE_S         900   the sportsbook consensus
    MAX_KALSHI_QUOTE_AGE_S  30   the price you would actually pay
    loop interval          900   how often a row is written

A row is bettable for **thirty seconds after each pass**, then the server
refuses it. Two sweeps a day, so the tool is actionable for about a minute a
day, not half an hour. Every document in this repo said fifteen minutes,
including this one. The Board now states it rather than hiding it — expired rows
are struck through and labelled — but stating a problem is not fixing it.

Three candidate fixes, cheapest first. They compose; the first two together are
probably enough.

1. **Poll Kalshi fast while the window is open.** Kalshi REST is unmetered — the
   15-minute interval exists for the odds budget alone. A short pass (Kalshi
   quotes + re-price only, no sweep) every ~20s during the ~15 minutes after a
   sweep would cost nothing and keep a row inside its 30s limit for the whole
   window. `run_ingest_pass` already separates the odds leg, so this is mostly
   scheduler work.
2. **An unchanged row goes stale even though the market has not moved.**
   `persist_if_changed` deliberately does not rewrite a row whose ask and fair
   are unchanged — correct for the record, wrong for freshness, because
   `recommendation_freshness` measures from `created_ms`. A `last_confirmed_ms`
   column, updated on every pass that re-derives the same numbers, separates
   "this observation is old" from "this price is old". Needs a schema column and
   a change in `gate.recommendation_freshness`; the record semantics do not
   change.
3. **Refresh the quote at order time.** The real fix for execution, and the
   biggest: the ticket sheet reads a live Kalshi quote before confirming. Also
   closes the "the price moved between recording and ordering" gap that (2)
   leaves open.

Do not raise `MAX_KALSHI_QUOTE_AGE_S`. 30s is the correct number for a venue
quoted by sub-200ms market makers; the poll rate is what is wrong.

### And read this before touching the gate

The first live Discord digest (2026-08-08 02:39Z, one budget day) says:

    Surfaced 0   Suppressed 319   No edge 201   Scored on CLV 16 / 300

    stale_odds                                × 196
    stale_odds,suspicious_edge                ×  66
    stale_odds,too_few_books,no_market_width  ×  16
    too_few_books,no_market_width             ×  11

**`stale_odds` is on 278 of 319 suppressions — 87%.** `tasks/lessons.md` already
has the rule this breaks: *"before adding something to a rejection log, ask what
fraction of inputs will trigger it. If the answer is 'most of them', it is a
state, not an exception, and logging it as an exception destroys the log's value
as a diagnostic."* That has now happened. The suppression summary is one code
and a long tail, so it can no longer surface a miscalibrated rule — which is the
only reason it exists. Stale odds are the *normal* condition for 23.5 hours a
day; they are a state.

**And the gate is counting the wrong population.** `clustered_clv` pools every
row with a `clv_tenths`, with no filter on `suppressed_reason` or
`suggested_contracts`. So "16 / 300" is 16 games of CLV drawn overwhelmingly
from rows the strategy explicitly *rejected*. That measures the closing-line
behaviour of "any Kalshi market we happened to poll", not of this strategy.

The dilution is conservative — it drags a real edge toward zero rather than
inventing one — so nothing unsafe has happened. It is still the wrong number
under a label that says "our edge", and the 66 `suspicious_edge` rows are
exactly the population most likely to carry a *systematic* CLV in one direction,
which would move the pooled mean rather than merely blunt it. The repo's own
rule: **a pooled number is not a finding until the parts agree, and the
per-group view goes beside every aggregate.**

The sharp version, and the reason this is item 2 rather than item 5: **rows
become eligible only when they are actionable, and nothing has been actionable
yet.** Surfaced is 0 and has always been 0. So the two findings are one finding
— the 30-second window starves the only population the gate should be measuring,
while the counter reads 16 because it is counting a different one. Fixing the
window is what makes the gate's number mean anything.

Do not simply add `WHERE suggested_contracts > 0`. That is the correct
population and it is currently empty, so the gate would read 0/300 forever and
the change would look like a regression. Report both groups first —
actionable and rejected, side by side, with n for each — then decide which one
the floor counts.

### Then

- [x] ~~**Turn on Discord**~~ — **done 2026-08-08 02:41Z.** `DISCORD_WEBHOOK_URL`
  is a repo secret and a Fly secret; live reports
  `notifications_configured: true`; the workflow posted a real message and
  Discord replied 204. `tasks/PHONE.md` item 4 has the steps if it ever needs
  redoing — and note the GitHub mobile *app* is unreliable for workflows with
  inputs, so use the browser URL or ask me.
  **The bug that made this necessary:** the code read
  `DISCORD_BOT_TOKEN`/`DISCORD_CHANNEL_ID` while `PHONE.md` had said
  `DISCORD_WEBHOOK_URL` since it was written, so following the documented phone
  path would have configured nothing and reported nothing wrong.

- **Watch the first scheduled sweep**, some time after 10:00Z on the 8th. The
  log line to look for is `sweep decision: <sport> (scheduled): N game(s) from
  HH:MMZ, sweeping 45-15 min before first kickoff`. A `bootstrap` trigger there
  would mean no sportsbook fixtures were stored, which is a different problem.
- **Decide what to do with the in-play rows already in the live record.** They
  cannot be scored and they inflate the Ledger and the suppression summary.
  Deleting rows from the live evidence database is your call, not mine.

### What changed this session

- `backend/odds/timing.py` — clusters the day's kickoffs, scores each cluster by
  games covered, and fires a sweep only in a 30-minute window before one.
  Anchored on the **sportsbook's** kickoff; Kalshi's runs 3h late. Budget day
  rolls at 10:00Z, not UTC midnight. `plan_sweep` deleted, not left beside it.
- `/api/window` + `WindowBanner` — open/closed, time left, next sweep and why,
  credits left. Same planner as the runner, not a second implementation.
- `/api/board` splits `surfaced` from `expired`, recomputing both ages with the
  arithmetic the order endpoint uses.
- `backend/notify/alerts.py` — the caller `discord.py` never had. Dedupe lives
  in a `notifications` table so a restart cannot re-announce the slate.
- `runner` drops fixtures whose game has started. 36 of 104 rows on a live pass
  were in-play, with edges spanning −200 to +68 tenths against −39 to −18 for
  the pre-game rows on the same slate.
- `tests/test_has_callers.py` — the orphaned-code grep from `lessons.md`, run by
  CI and parsed with `ast` rather than matched as text.

### Running this in parallel

`docs/adr/0003-parallel-sessions-and-subagents.md` defines the file-ownership
lanes, the three integrator-only documents, and the shared state that no VCS
will protect — the odds budget (~16 credits/day, 6 a sweep), deploys, `data/`,
and the live instance. Workers use `Agent(isolation: "worktree")` and write
findings to `tasks/inbox/<lane>.md`.

**One addition, learned the hard way:** running `scripts/run_loop.py` locally
spends from the same monthly odds quota as the live instance, and neither
instance's `api_credits` table can see the other's. One local smoke test cost 6
of ~500 monthly credits. Reconciliation against `x-requests-remaining` catches
the drift after the fact; nothing prevents it.

### Still waiting on the user (both pre-authorised)

- **Fee-calibration trades** — four minimum-size orders at ~10c/30c/50c/80c in
  the Kalshi app. Clears a gate condition and retires the conservative fee hedge
  that suppresses essentially every longshot.
- **One combo price lookup** — `POST .../lookup`, no money, yields a measured
  same-game correlation.

---


Tick these off as you go. `tasks/todo.md` is the build log; this is the
actionable list.

State as of 2026-08-07: **653 tests passing**, `dbt build` green (10 nodes),
Docker image builds, cockpit renders clean at 320/390/430px, live WebSocket
verified against real markets.

---

## 1. Blocked on you

Four things I can't do without you. Each is a few minutes.
**All four are doable from your phone — see `tasks/PHONE.md` for the exact
taps.** Deployment used to need a laptop because `flyctl` has no mobile
client; `.github/workflows/deploy.yml` now runs it from a GitHub "Run workflow"
button.

- [x] ~~**Deploy the demo instance to Fly**~~ — **done 2026-08-07.**
      **https://kalshi-cockpit-demo.fly.dev** — one machine in `ord`, scales to
      zero, no credentials, no execution path. Deployed via the `Deploy`
      workflow (`gh workflow run Deploy -f instance=demo`); `FLY_API_TOKEN` is
      set as a repo secret. Verified: all five pages 200 with no error text over
      20 consecutive requests, `/api/health` reports `instance_mode=demo`, and
      `POST /api/orders` with a forged bearer answers **403**.
      **The first deploy was broken and looked fine.** It served "Backend
      unreachable" on 9 of 15 requests while `/api/health` stayed green — the
      API's SQLite connection was thread-bound and FastAPI runs the sync
      dependency and the sync endpoint on different threadpool workers. 758
      local tests and a local container run all missed it, because an idle
      threadpool reuses one worker. See `tasks/lessons.md`.
      Added `.github/workflows/ops.yml` (read-only `logs`/`status`/`machines`)
      because there was otherwise no way to read the deployed instance's logs —
      `flyctl` has no mobile client and needs a token nobody holds locally.
- [x] ~~**Deploy the live instance**~~ — **done 2026-08-07.**
      **https://kalshi-cockpit.fly.dev** — 1GB machine in `ord`, volume
      `cockpit_data`, never scales to zero. Gate verified locked: all four
      conditions unmet, `live_trading_enabled=false`, `POST /api/orders` 401s
      with and without a forged token.
      **The record is now growing.** First pass: 184 events discovered, 32
      linked, 3,612 odds quotes, 1,549 markets quoted, **128 recommendations
      recorded, 0 surfaced**. 64 markets awaiting a closing line.
      Two blockers were found and fixed by pre-flighting the image, neither
      findable by any test: the private-key materialisation was documented in
      `fly.live.toml` and never implemented, and `scripts/` was excluded from
      the image so `run_loop.py` — the entrypoint's own process — was absent
      from the filesystem.
- [ ] **Say yes/no to one combo price lookup.** `POST .../lookup` returns a
      Kalshi combo's price but *creates a market on the exchange* if that
      combination is new. No money moves; it's what the app does every time you
      tap a leg. I've left it refusing by default. This is the only way to get
      a real combo quote and back out an implied same-game correlation.
- [ ] **Decide on fee-calibration trades.** The fee model is still a hedge
      between two sources that disagree, and it can only be settled by real
      fills. Four minimum-size orders at ~10c/30c/50c/80c would close a
      year-old open question for a few dollars. This is real money, so it's
      your call.

- [ ] **`ODDS_API_KEY` is exposed — rotation deliberately deferred
      (2026-08-07).** A live run put the key into a terminal transcript: httpx
      logs full request URLs at INFO and The Odds API takes its key as a *query
      parameter*, so making a request was enough. Nothing logged it
      deliberately. **The cause is fixed** —
      `backend/logging_setup.py` redacts at the root logger and pins httpx to
      WARNING — but the leaked value is still valid.
      Judged not worth rotating for now: it is a free-tier key, 500
      credits/month, no money and no account access attached, and Kalshi's
      credentials were never exposed (they sign headers, not URLs). The residual
      risk is someone draining the quota, which would silently stop the record
      accumulating once the live instance is running. Revisit if the odds path
      is ever put on a paid tier.

---

## 1b. Found by deploying live

- [x] ~~**The live cockpit is fully public**~~ — **done 2026-08-07.** A
      shared-token login now gates every page and every proxied API route on
      the live instance; the demo stays open, because it is the portfolio link.

      **Gated in Next, not in the backend.** uvicorn binds `127.0.0.1:8000` and
      is never published — `/api/*` is reachable only because `next.config.ts`
      rewrites it, and middleware runs *before* rewrites. So one gate covers
      pages and API together, and server components keep calling the backend
      over loopback with no token to thread through.

      **The cookie is not the token.** `APP_AUTH_TOKEN` authorises
      `POST /api/orders`; the cookie carries `<expiry>.<HMAC(token, expiry)>`,
      so a stolen cookie costs read access and cannot be replayed as order
      authority. Tampered signatures and expired cookies both 401.

      **The switch is the token's presence**, not `INSTANCE_MODE` — the backend
      already refuses to boot in live mode without `APP_AUTH_TOKEN`, so
      "live but unauthenticated" is unreachable rather than merely unlikely.

      Three traps caught by testing the built image rather than the dev server:
      `/api/health` must stay public or Fly's check fails and the machine
      crash-loops; `process.env` in middleware had to be verified as
      *runtime*-read, since the same image must gate with the token set and not
      without; and `NextResponse.redirect` built its URL from the container's
      bind address, which would have sent the browser to
      `https://0.0.0.0:3000/ledger` — now a relative `Location`.

---

## 2. Fix before any real money

- [x] ~~**`clv.py` does not require the entry to precede the close**~~ — **done
      2026-08-07** (audit item 11). The closing line is read at
      `commence - horizon` and the runner records right up to kickoff, so at a
      1h horizon every recommendation made in the final hour was scored against
      a quote observed **before the decision existed**. Whether that flatters or
      punishes depends purely on which way the market drifted in between, so it
      put drift straight into the number built to detect edge — and the live
      instance starts scoring tonight, so it was contaminating a record that
      cannot be repaired retroactively.
      Now `created_ms <= observed_ms`, in `score_recommendations` *and* in
      `horizons_agree`, where it matters more: the 6h line is observed five
      hours earlier, so without it the two horizons compared different
      populations and part of the measured "drift" was just a change in which
      rows were counted. Excluded rows are counted
      (`skipped_entry_after_close`) and stay unscored rather than consumed, so
      they remain candidates for a shorter horizon.
      **The cost is stated, not hidden:** late recommendations go unscored at a
      given horizon, so the scored sample skews early.
      Verified by disabling (4 red). Adding it also turned 5 `test_scoring`
      tests red, because their fixtures created recommendations *after* the
      closing line — the rule catching unrealistic test timing on its first run.


- [x] ~~**`devig.market_width` reports `0.0` for a single book**~~ — **done
      2026-08-07** (audit item 10). "No disagreement measurable" rendered as
      "perfect agreement", so the least-evidenced consensus in the system passed
      the width suppression most easily. Now `Optional[float]`: `None` when
      fewer than two books contributed, and suppression **refuses** on it under
      a distinct `no_market_width` code — "books disagree" and "there was no
      second book to disagree with" call for different fixes.
      A measured `0.0` (two books quoting identically) still passes, and that
      pair is the test that matters: if `None` and `0.0` ever behave the same
      again, the states have been collapsed back together.
      **The larger finding underneath it:** sharp anchoring *causes* the
      single-book case. Three books agreeing to within 3.1 points, one of them
      sharp, yields `book_count = 1` and no measurable width — the anchoring
      discards the agreement evidence, which was the strongest signal the line
      was trustworthy. `usable_book_count` is now reported so the log can tell
      "only one book quotes this" from "five did and we kept the sharp one".
      Both guards verified by disabling. It had been masked by
      `min_book_count = 2` catching the same rows — a working guard hiding a
      broken one.

These are open defects from the 2026-08-07 audit. Full detail with file:line in
`tasks/audit-2026-08-07.md`. Ordered by how much they'd distort a money
decision.

- [x] ~~**The gate's `n` counts non-independent observations**~~ — **done
      2026-08-07.** Rows are now clustered by **game** (`kalshi_markets.
      event_ticker`, not ticker — a game's moneyline, spread and total resolve
      from one final score) and the standard error is the cluster-robust
      sandwich estimator. The 300 floor counts independent games; the Ledger
      shows games over the floor with the row count beside it, so the two
      screens cannot disagree. Two anchors chosen so a wrong implementation
      differs: singleton clusters reproduce the classical `s²/n` exactly, and
      duplicating every observation `k` times leaves the standard error
      bit-identical (the old estimator returned `stderr/√k`). Verified by
      disabling it two ways — clustering by row turned 5 tests red, dropping the
      finite-cluster correction turned the other 2 red. **Found on the way:**
      the test helper's `INSERT OR IGNORE INTO kalshi_markets` had been silently
      inserting nothing since the file was written (`first_seen_ms` is `NOT
      NULL`), so every gate test's join matched nothing. Both in
      `tasks/lessons.md`.
- [x] ~~**Continuous monitoring with no peeking correction**~~ — **done
      2026-08-07.** The noise guard now uses an always-valid bound (Robbins
      normal mixture, `m` tied to the 300-game floor) instead of two standard
      errors. Measured on 1,200 pure-noise sequences looked at 100 times each:
      the old rule fires on **13.7%**, the new one on **0%**. The cost is stated
      rather than buried — 3.66 standard errors at the floor instead of 2, about
      1.8x the effect size, and the gate's detail string reports the multiplier
      it used. Verified by disabling it (returning 2.0) and watching the
      simulation and the boundary test go red. Compounds with the clustering fix
      above: both corrections apply to the same statistic.
- [x] ~~**`margins.fit()` destroys the published standard deviation on a thin
      sample**~~ — **done 2026-08-07.** `fit` no longer overwrites `sd` from a
      sample too thin to estimate it: `MIN_GAMES_FOR_SD = 30`, deliberately
      separate from `MIN_GAMES_FOR_EMPIRICAL = 200` because "can this sample
      show me the shape?" and "can it tell me the width?" are different
      questions. Below it the league's `PUBLISHED_SD` is kept and
      `sd_is_measured` says so. The count alone was never sufficient — 300
      identical margins clears n≥30 and still estimates zero — so the check is
      on the estimate too. `_normal_survival` now **raises** on a non-positive
      width instead of returning 1.0/0.0, and a zero-width distribution cannot
      be constructed at all. Verified by restoring the old `max(1, n-1)`
      computation and watching 4 tests go red.
- [x] ~~**`backtest.beats_close` contradicts its own verdict**~~ — **done
      2026-08-07.** Both now derive from one `PairedComparison`, so there is no
      second path to disagree with; the invariant *"`beats_close is True` iff
      the verdict claims an edge"* is asserted across twelve seeds, because the
      two paths agreed whenever the gap was large and diverged exactly on the
      marginal cases. It also respects `min_games` now — a 50-game backtest
      could previously report `True` beside a verdict saying "No verdict".
      **Fixed audit item 14 in the same change:** the noise band used
      `sqrt(0.25/n)`, the null for a *single* proportion, where the gap is a
      difference of two accuracies on the *same* games. Now McNemar's
      `sqrt(b+c)/n`. The two coincide at exactly 25% discordance — which is why
      it looked right — and above it the old form is too narrow, 1.55x too small
      at 60% discordance, in the direction that manufactures significance.
      Verified by restoring each old implementation in turn.
- [x] ~~**Refresh the Kalshi quote at order time**~~ — **done 2026-08-08.**
      Item 3 of the three window fixes, and the last of them.
      `POST /api/orders` now re-reads `GET /markets/{ticker}` inside the
      request and **prices, sizes and caps the order against what comes back**;
      the recorded ask is provenance from that point on. `backend/kalshi/
      quotes.py`; wire format pinned by `tests/fixtures/market_single.json`,
      which stores the same ticker as `/events` returns it beside the
      single-market payload so a rename in one and not the other fails a test.
      Size is re-derived through `size_position` rather than against a new
      "how far may a price move" threshold, so a price that erased the edge
      returns zero contracts without anyone choosing a tolerance — and a
      *better* price still cannot exceed what the engine authorised.
      **Two things fell out of it that were not in the plan.** The route's
      portfolio-cap re-check became unreachable — the sizer now applies the same
      caps at the same instant against the same exposure, at a fee-inclusive
      price strictly above the one the re-check compared — so it was deleted
      rather than left looking like protection, with the caps now verified *at
      order time* instead. And `/api/board` had to change: with the quote
      re-read at order time, a stale recorded quote no longer stops an order, so
      splitting `surfaced`/`expired` on both clocks was striking through
      everything between 30s and 15 minutes after a pass — nearly the whole
      window — while the server would have sold it. `actionable` is now the odds
      clock and `price_is_current` is the Kalshi one; the card says "still
      bettable, but this price was read 4m ago and will move".
      17 guards verified by disabling; two were decoration on the first pass and
      both were real defects rather than missing tests.
- [x] ~~**Deci-cent asks can't fill.**~~ — **done 2026-08-08.** Checking it
      against Kalshi's write API turned a rounding fix into an endpoint
      migration, and found a second defect on the way. `docs/adr/0007`.
      **Prices now snap to the market's own `price_ranges`**, which Kalshi
      documents as the source of truth and explicitly tells clients not to infer
      from `price_level_structure`. No default grid: unreadable resolves to
      `None` at ingest and the order path refuses, because assuming whole cents
      is the bug.
      **The order goes to `POST /portfolio/events/orders` (V2)**, because the
      legacy path takes integer cents and cannot express 50.5c at all. It is
      also absent from Kalshi's current API reference — we had been posting to a
      deprecated endpoint for the whole project, invisibly, because nothing has
      ever posted. V2 quotes the **YES leg only** (`bid`/`ask`), so buying NO at
      `p` is selling YES at `1 - p`; `time_in_force` and
      `self_trade_prevention_type` are required and were absent.
      **The response defect found in the same change:** V2 emits no `status`
      field, and the old parser read `response["order"]["status"]` defaulting to
      `"resting"` — so every live order would have been recorded as resting with
      a null order id. Status is now derived from the fill counts and an
      unreadable response is `unrecognised_response`, which nothing can mistake
      for success.
      **Measured before believing the size of it:**
      `scripts/capture_price_grids.py` walked the live exchange —
      **1,426 game markets, all `linear_cent`.** So this costs no fills today;
      the "~25%" is a fact about all Kalshi markets, not about the ones we
      price. That does **not** mean sub-cent game markets don't exist (60 of
      2,145 on 2026-08-06, and a market's grid can change while it is open).
      6 guards verified by disabling; one of them was decoration on the first
      pass — a redundant bound check — and was deleted rather than kept.
      1,139 tests.
      **Dividend:** the V2 response carries `average_fee_paid` per contract, so
      the fee-calibration trades will read the true fee out of the order
      response itself rather than needing a `/portfolio/fills` poll.
- [x] ~~**Calibration panel leaks the number it suppresses**~~ — **done
      2026-08-07.** It rendered `implied` and `actual` on every row, and
      `gap = actual - implied`, so the suppressed finding sat one subtraction
      away in two adjacent columns. Censoring now happens in the mart
      (`actual_display`, `pnl_display`, `beat_close_display`, `clv_display`),
      so the presentation layer never receives an uncensored result; raw
      columns stay for analysis. `implied` and `n` stay visible because neither
      is a result. The dbt test that was meant to catch this was a tautology
      (`(A∧B) ∧ ¬(A∧B)`) and now recomputes from raw inputs; a source guard
      stops the frontend rebinding a raw column. Both verified by
      re-introducing the leak and watching them fail. 7 noise cells, 0
      reconstructable.
- [x] ~~**`mart_multiple_comparisons` undercounts tests**~~ — **done
      2026-08-07.** It counted `mart_calibration` alone while
      `mart_clv_by_bucket` and `mart_suppression_audit` ran their own
      two-standard-error tests uncounted. Measured on the seeded no-edge
      history: 8 tests instead of 11 moves p from **0.401 to 0.311** — a 29%
      improvement in apparent significance bought by forgetting to count. The
      model that exists to catch multiplicity was committing it.
      Findings are read from each mart's **own published conclusion** rather
      than recomputed, because a counter that disagrees with the thing it counts
      is worse than no counter. Both directions count in the suppression audit —
      "REVIEW" and "protective" each cleared the bar; only "neutral" did not.
      `generate_series(0, 200)` replaced with a series to `n_findings - 1`, so
      the sum can no longer truncate (which pushed p toward 1 — the bug that
      hides findings sat one edit from the bug that invents them).
      `tests_by_source` is a column now and renders under the verdict, so the
      total is checkable rather than asserted. A new dbt test names the three
      sources independently and fails if one is dropped — verified by dropping
      `suppression_audit` and watching it go red. `dbt build` 11 nodes green.
      **Deliberately still not counted:** `gate.py`'s noise guard, which is
      multiplicity along the *time* axis and already carries its own
      always-valid bound (folding it in would apply two corrections to one
      test), and `validate.py`, which tests the same observations these marts
      do.
- [x] ~~**Capture an Odds API fixture**~~ — **done 2026-08-07.** The capture
      already existed (`tests/fixtures/odds_mlb_h2h_spreads_totals.json`, 15
      events, 30 books) and **no test loaded it**, so the wire format was still
      pinned only by hand-written payloads. A capture nothing reads is
      decoration. Eight tests now parse the real bytes, including a drift test
      asserting every market key present is explicitly classified.
      **Closed the `h2h_lay` SEV 1 in the same change:** the API returns
      `h2h_lay` from Betfair and Matchbook without being asked, and `_parse`
      stored any key it was given. Lay quotes are now dropped at ingest, so no
      downstream grouping can pool them. Measured on the fixture: back
      `2.24/1.79` sums to 1.00509, lay `2.28/1.81` sums to 0.99108 — devig
      removes an overround, and an underround gives it nothing to remove.
- [ ] **Wire up the agent fleet.** `backend/agents/*` is imported by nothing —
      `skeptic.apply_verdict` is never called from the engine or the API. ~40
      green tests imply a safety layer that can't block anything.
      `tests/test_has_callers.py` now asserts this is *still* true, so wiring it
      up turns that test red and points at the list the entry should join.

~30 more findings are triaged in `tasks/audit-2026-08-07.md`.

- [x] ~~**The odds sweeps fire at the wrong time of day**~~ — **done 2026-08-08.**
      `backend/odds/timing.py`. See the handoff at the top of this file.
- [x] ~~**Surface the window on the Board**~~ — **done 2026-08-08.** And it
      immediately contradicted the page under it, which is how the 30-second
      window was found.
- [x] ~~**Wire up Discord**~~ — **done 2026-08-08.** `backend/notify/alerts.py`
      is the caller. Secrets still need setting on the live app.

---

## 3. Ready to build (no blockers)

- [x] ~~**The chain runner**~~ — **done 2026-08-07.** `backend/runner.py` joins
      discovery → odds sweep → link → devig → engine → `recommendations`.
      Nothing joined them before: `persist_recommendation` was called only by
      `seed_demo.py` and tests, `odds_snapshots` had a writer and no reader, and
      `fair_prices` had neither. **Verified against the live API**, not just
      fixtures: 175 events discovered, 19 linked, 2,746 odds quotes, 76
      recommendations recorded, **0 surfaced** — no edge, which is the expected
      and honest result. `scripts/run_chain.py` runs one pass; `--no-odds`
      spends no credits.
      Quotes ride on the `/events` payload (`yes_bid_dollars`,
      `yes_ask_size_fp`) rather than a second orderbook call — no extra request,
      and no second wire format to guess at.
      **Three defects found by running it live**, all in `tasks/lessons.md`:
      the credential leak above; Kalshi's `occurrence_datetime` running exactly
      3h late, which blocked *every* link; and the same offset then blocking
      every candidate at a second, unconnected limit in `suppression`.
      Still moneyline-only — spreads and totals are ingested and not yet priced.

- [x] ~~**Run it on a schedule**~~ — **done 2026-08-07.** `backend/scheduler.py`
      + `scripts/run_loop.py`. Jittered interval (default 900s), and it **dies
      loudly**: a transient failure is retried, but `MAX_CONSECUTIVE_FAILURES`
      in a row re-raises, killing the process, tripping `wait -n` in
      `entrypoint.sh` and taking the container down. A loop that swallowed its
      errors would leave the cockpit serving a record that had silently stopped
      growing, which reads as a quiet slate. Started by the entrypoint on
      **live only** — the demo holds no credentials. Smoke-tested live for two
      passes.
- [x] ~~**CLV scoring pass**~~ — **done 2026-08-07.** `backend/scoring.py`
      fetches closing lines from candlesticks and calls `score_recommendations`,
      which had existed since the evidence layer was built and had **never been
      called by anything** — so no row could ever be scored and the gate's
      counter was structurally pinned at zero.
      **The anchor is the sportsbook's commence time, not Kalshi's.** Kalshi's
      runs 3h late, so a "1h before close" reading against it lands *two hours
      into the game* — a quote from after the outcome is partly known, which
      would have produced a strong and entirely fake CLV signal in the one
      measurement this project exists to make. Lines are stored at both
      horizons for `horizons_agree`, but only the primary is scored, so
      `clv_tenths` is never a silent mixture. Four guards verified by disabling.

- [x] ~~**The record accumulates near-duplicate rows**~~ — **done 2026-08-07.**
      `engine.persist_if_changed` skips a row identical in derived ask *and*
      fair probability to the previous row for that `(ticker, side)`. Measured
      on a real two-pass run: 152 rows carried 77 distinct combinations, so half
      the record was repetition after two passes and would have been ~98% at 96
      passes a day.
      **Consecutive, not global** — a price moving 47 → 48 → 47 records three
      observations, because the return to 47 is a genuine second opportunity and
      global dedupe would thin the record exactly where the market is moving.
      Both directions verified by disabling: removing the check re-records an
      unchanged slate, and comparing against the oldest row instead of the
      latest swallows the return.
      Settled **before** live recording starts, deliberately: changing what gets
      recorded mid-stream puts two regimes in one dataset. The rule is part of
      the strategy config, so it mints a version and the record segments on it.

- [ ] **Is in-play betting viable? — measured, and the answer was NOT accepted.**
      `docs/adr/0006-in-play-scope.md` proposed closing it as out of scope;
      **Joe rejected that on 2026-08-08.** The question stays open. The
      measurements below were not disputed — they are kept in
      `docs/adr/0006-in-play-evidence.md` and should not be re-derived.

      **The three guards stay on while it is open**, and none of them came from
      the rejected ADR: the runner still drops started games, the order path
      still refuses one, and **no in-play row enters the evidence record**.
      Reopening the scope means designing the in-play regime — starting with
      what replaces the closing line — not letting rows in and separating the
      populations afterwards.

      All four questions were answered against the live exchange; **zero odds
      credits were spent** and no POST was made.

      **Joe was right about the product, and that is the part to say first.**
      Kalshi keeps the game market open in-play — `can_close_early: true`, and
      20 of 20 games measured (14 MLB, 6 WNBA) had a two-sided quote in *every*
      minute after the true start. In-play volume is **7.7x** (MLB) and
      **14.7x** (WNBA) the pre-game rate, and 98% of in-play minutes trade. The
      liquidity is real and it is where the action is.

      **It is out of scope because we cannot see it in time, not because it
      isn't there.** Two independent reasons, either sufficient:

      - **Cost.** Half-spread rises from 0.50c to 0.75c (MLB) / 0.89c (WNBA),
        and the mid moves ≥1c on ~half of in-play minutes against ~0.5%
        pre-game. Crossing plus 40s of unavoidable staleness is **1.34–2.28c
        against 0.38c of fee headroom** — 3.5x to 6x. Both leagues agree in
        direction and magnitude.
      - **Budget.** The Odds API refreshes in-play every 40s regardless of
        plan, so one league at the current market/region fan-out is ~7,020
        credits/day against a budget of 16. The realistic tier is $119/month,
        needing $31,316 of monthly notional to break even on the data bill
        alone.

      **And CLV has no in-play substitute that is the same statistic.**
      Settlement price is a win-rate measurement, which puts back the
      ~1,000-observation variance `clv.py` exists to avoid; entry-plus-delta is
      exactly what stale-quote picking optimises. Reopening needs a substitute
      argued *before* any row is recorded, plus a regime column, `closing_lines`
      keyed per recommendation rather than per `(ticker, horizon)`, and a gate
      that never pools the two regimes.

      Also from that work, unaffected by the rejection: `dropped_game_started`
      stays a **drop**, not a suppression — a
      suppression entry claims we considered it. Maker is *unreachable* rather
      than refuted: the headroom is 1.94 points there, but a resting order in a
      market moving ≥1c half the time is being adversely selected and this repo
      has **no cancel path at all**. Recorded as missing infrastructure, not as
      a measurement.

- [ ] **Verify what `occurrence_datetime` actually is.** Raised by the in-play
      research and **not yet established** — it is recorded here rather than in
      `lessons.md` because I could not confirm it.
      The claim: the field is not a timezone-shifted start but an *expected
      end*, so the −3h that reproduces MLB kickoffs works only because MLB games
      run about three hours, and it would be wrong for a period series such as
      `KXMLBF5`.
      What I checked directly in `events_sports_nested.json`:
      **`occurrence_datetime == expected_expiration_time` on 198 of 200
      markets**, differing on two (an NFL game, by exactly 3h). That is real
      and it is a reason to doubt the timezone framing.
      What it does **not** settle: `tasks/lessons.md` records +180 min on *both*
      MLB (~3h games) and WNBA (~2h games), and a genuine end-time field could
      not produce the same offset for both. Both facts cannot be explained by
      either story alone, so neither is established.
      **Why it matters now:** nothing in scope today uses a period series, so
      this is not currently live — but `match.linker` and `core.suppression`
      both bound this quantity, and if the offset is game-length-dependent then
      a fixed tolerance is wrong for any sport that is not three hours long.
      One measurement settles it: compare `occurrence_datetime` against the
      sportsbook start across leagues of different durations, and against
      `expected_expiration_time` on a period series.

      What has to be answered before any of it is buildable, cheapest first:

      1. **Does Kalshi keep the game market open in-play, or list separate
         period markets?** One `/events` walk during a live game settles it —
         read `status` and `close_time` on a game whose kickoff has passed, and
         look for half/quarter series alongside `KX*GAME`. Free, no credentials
         beyond what is already exercised.
      2. **Can the odds side even follow?** The Odds API charges per call and
         the free tier is ~16 credits a day. In-play needs a refresh every
         minute or two per game, not twice a day, so this is a **paid-tier
         question, not a code question** — price it before building anything.
         If the answer is no, the honest result is "out of scope until the odds
         budget changes", recorded as such.
      3. **What replaces the closing line?** CLV is the only measurement this
         project trusts, and it anchors on a quote read before kickoff. An
         in-play bet has no such anchor — the natural substitute is the price
         at settlement or at the end of the period, and it is *not* obviously
         the same statistic. Nothing may enter the evidence record until this
         is settled, or the two populations pool into one number the way the
         in-play rows already nearly did.
      4. **Is the edge plausibly there?** In-play is where the venue's latency
         story is worst — this is the corner most contested by bots, and
         `tasks/lessons.md` already records that stale-quote picking lives at
         ~400ms. Expect the answer to be no, and design the check so a no is
         reportable.

      Do **not** simply remove the in-play drop to find out. That would put both
      populations in one record with nothing to tell them apart afterwards,
      which is the failure `tasks/lessons.md` names as "two populations in one
      record, told apart by dispersion".

- [ ] **Research screen** — Scout findings with sources and timestamps, model-
      vs-market disagreements, steam moves.
- [ ] **Playbook screen** — lessons, config versions, proposed changes awaiting
      your approval. The flywheel's UI.
- [ ] **Ticket bottom sheet** on the Board — contracts, worst-case cost,
      predicted fee, resulting exposure. The order path behind it is built and
      gated.
- [ ] **README** — the portfolio piece. Architecture diagram, the OLTP→Parquet→
      DuckDB story, and an honest statement of what the tool does and does not
      establish.
- [x] ~~**GitHub Actions** — tests, `dbt build`, and secret scanning on push.~~
      — **this line was wrong in both directions, 2026-08-08.** CI was built in
      the first commit and has been running pytest, `seed_demo` → `publish` →
      `dbt build`, and `next build` green throughout. This checklist said it did
      not exist.
      **And the part nobody was reading was red.** The secret scan failed on
      **36 consecutive pushes** since 2026-08-07 19:17Z, because it grepped for
      the *phrase* `BEGIN … PRIVATE KEY` and two files legitimately contain it —
      `docker/entrypoint.sh` validating a decoded key's format, and
      `tests/test_logging_redaction.py` proving the redactor strips a PEM block.
      It fired on the hygiene. A check that is always red carries no
      information: the run that finds a real key looks identical to the 36 that
      found a comment about one, and red becomes the resting state.
      Now matches **material**: a header alone on its line, a header followed by
      a base64 body, and a header immediately after a quote that then ends the
      line. That third one was added on merge — narrowing to material had
      dropped `KEY = """-----BEGIN RSA PRIVATE KEY-----`, which the broken
      pattern did catch. The `:!*.yml` exclusion is gone, so a key pasted into
      `warehouse/profiles.yml` is now scannable.
      **Verified by running the step, not by reading it:** extracted from the
      YAML and run under bash — clean tree exits 0, five planted shapes each
      exit 1 (own line, after a triple-quote in `.py`, escaped in `.json`,
      inside a `.yml`, and a tracked `.p12`). Random bodies, never key material.
      The exclusions are asserted against the two real files, so a future
      widening fails loudly instead of turning CI red again.
      Also note what gitleaks does **not** do: it scans only the commits in the
      push, never the tree and never history. A key committed last week and
      still present is invisible to it.

- [ ] **Three CI follow-ups**, all outside the lane that found them:
      - `.gitignore` ignores `*.pfx` but not `*.p12`. A PKCS#12 bundle can be
        `git add`ed today with no warning; CI now refuses it, so the two
        disagree. Make them agree.
      - `ruff~=0.9` is a dev dependency that nothing configures and nothing
        runs — no `pyproject.toml`, no `ruff.toml`, **491** findings on the
        default ruleset. Either pick a ruleset and wire it, or drop the
        dependency. Deliberately *not* added as a job: it would be red on the
        first push, which is the failure just removed.
      - Node 20 deprecation warnings on `actions/checkout@v4`,
        `setup-python@v5`, `setup-node@v4`, `gitleaks-action@v2`. Needs one
        throwaway branch push to verify, since an Action cannot run locally.
- [ ] **Write `orders` rows.** The endpoint currently dry-runs without
      persisting, so nothing accumulates exposure for the cap to read.

---

## 4. Verified working

So you know what's actually solid:

- **Live WebSocket** — 6/6 books populated from real MLB markets, derived-ask
  identity holds on every one, subscription registry complete, sequence gaps
  handled at the connection level.
- **Kalshi REST + auth** — signing verified against the live API; discovery
  pinned by drift tests over real captures.
- **Devig** — four methods, worst-of-four for money decisions, Shin verified
  not to degenerate.
- **Suppression + engine** — every candidate recorded, suppressed or not, with
  its config version.
- **Measurement** — noise guard under the null, pooling check, multiple-
  comparisons mart. On seeded no-edge data the dashboard correctly reads
  *"NOT EVIDENCE: 1 finding from 10 tests, 37% by chance."*
- **Builder** — parlays priced against devigged consensus; same-game legs
  refused rather than guessed; Wong teasers priced from bucketed empirical
  margins and correctly coming out negative at −120.
- **Combos** — 1,389 collections mapped; a combo quote inverts to an implied
  correlation.
- **Gate** — five conditions, one shared implementation, locked by default.
- **Cockpit** — Board, Builder, Dashboards, Ledger, Gate. Clean at 320px.

---

## The honest status

No bet has been placed and no edge has been demonstrated. The tool is built to
find out whether one exists, and every measurement in it is built to avoid
flattering the answer. The gate is locked and correctly reports that it has
zero scored recommendations, no verified fee model, and no evidence.

That's the expected state. The premise was always that Kalshi's advantage is
cost, not information — it lowers the break-even bar from 52.38% to ~52.00%
taker, and does not clear it for you.
